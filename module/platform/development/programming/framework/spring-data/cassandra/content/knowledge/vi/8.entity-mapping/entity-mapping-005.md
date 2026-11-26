# equals, hashCode và tính bất biến của đối tượng khóa trong Spring Data Cassandra

## 1. Vấn đề cần giải quyết

Trong **Spring Data Cassandra**, một entity Java có thể dùng một thuộc tính `@PrimaryKey` đơn giản hoặc một **đối tượng khóa tổng hợp** được ánh xạ bằng `@PrimaryKeyClass` và `@PrimaryKeyColumn`. Khi khóa gồm nhiều cột, lớp Java biểu diễn khóa phải trả lời chính xác câu hỏi: **hai đối tượng khóa có đại diện cho cùng một hàng Cassandra hay không?**

Các phương thức `equals()` và `hashCode()` được Java sử dụng để kiểm tra tính bằng nhau theo giá trị và định vị đối tượng trong `HashMap`, `HashSet` hoặc những cấu trúc dựa trên băm. Cassandra lại sử dụng các thành phần **primary key** để định danh hàng, tính token từ **partition key** và sắp xếp hàng theo **clustering columns**. Hai cơ chế ở hai tầng khác nhau, nhưng phải thống nhất về ý nghĩa định danh.

Nếu một đối tượng khóa thiếu trường trong `equals()`, hai hàng Cassandra khác nhau có thể bị ứng dụng xem như một. Nếu `hashCode()` phụ thuộc vào thuộc tính bị thay đổi sau khi đối tượng được đưa vào `HashSet`, chương trình có thể không tìm lại được khóa đó. Nếu sửa đối tượng khóa rồi gọi `repository.save(...)`, Cassandra có thể ghi **một hàng mới** mà không tự xóa hàng cũ.

Sau bài này, bạn cần:

1. Phân biệt **định danh hàng Cassandra**, **giá trị của đối tượng khóa Java** và **identity của entity Java**.
2. Viết `equals()` và `hashCode()` đúng hợp đồng Java, bao gồm **tất cả** thành phần khóa.
3. Xây dựng **đối tượng khóa bất biến**, hiểu cách Spring Data Cassandra tạo đối tượng từ dữ liệu đọc lên.
4. Nhận diện lỗi từ setter, Lombok, định dạng thời gian, giá trị `null` và tập hợp dựa trên băm.
5. Kiểm thử sự bằng nhau, round-trip mapping và xử lý đúng trường hợp nghiệp vụ phải đổi partition key hoặc clustering key.

Bài học thuộc chương **Ánh xạ entity** của mô-đun `SPRING_DATA_CASSANDRA`. Dù ứng dụng dùng repository, `CassandraTemplate` hay truy vấn CQL trực tiếp, thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng phân tán vẫn cần được xem xét riêng.

## 2. Primary key của Cassandra và đối tượng khóa Java

Ví dụ ứng dụng cần lấy sự kiện của một người dùng theo từng ngày. Mẫu truy vấn luôn biết tenant, ngày và cần duyệt các sự kiện trong partition đó:

~~~sql
CREATE TABLE events_by_user_day (
    tenant_id uuid,
    user_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((tenant_id, user_id, event_day), occurred_at, event_id)
);
~~~

| Cột | Vai trò trong khóa | Tác động |
| --- | --- | --- |
| `tenant_id` | Thành phần partition key | Phân biệt dữ liệu giữa các tenant |
| `user_id` | Thành phần partition key | Phân biệt dữ liệu giữa những người dùng |
| `event_day` | Thành phần partition key | Giới hạn kích thước partition theo ngày |
| `occurred_at` | Clustering column thứ nhất | Tham gia định danh và thứ tự các sự kiện trong partition |
| `event_id` | Clustering column thứ hai | Phân biệt những sự kiện trùng thời điểm |
| `event_type` | Cột dữ liệu thông thường | Có thể đổi mà không làm đổi primary key |

**Khóa chính đầy đủ** gồm cả năm cột đầu. Hai hàng có cùng `tenant_id`, `user_id` và `event_day` nhưng khác `event_id` là **hai hàng khác nhau**. Vì vậy, khi ánh xạ sang Java, đối tượng khóa phải bao gồm cả các cột partition lẫn các clustering columns. Nếu chỉ so sánh ba cột partition, ứng dụng sẽ gộp nhầm mọi sự kiện cùng người dùng trong cùng ngày.

~~~mermaid
flowchart LR
    A[EventKey Java] --> B[Partition key]
    A --> C[Clustering key]
    B --> D[tenant_id]
    B --> E[user_id]
    B --> F[event_day]
    C --> G[occurred_at]
    C --> H[event_id]
    B --> I[Token và replica Cassandra]
    C --> J[Định danh/thứ tự bên trong partition]
~~~

**Phân biệt hai loại băm:**

- `EventKey.hashCode()` là giá trị băm **Java**, phục vụ các collection hoặc cấu trúc dữ liệu trong JVM.
- Cassandra tính **token của partition key** bằng partitioner của cluster để phân bố dữ liệu giữa replica.

Việc triển khai `hashCode()` trong Java **không điều khiển token Cassandra**, không cải thiện cân bằng partition và không làm thay đổi đường định tuyến CQL. Ngược lại, token Cassandra không thay thế cho quy tắc `equals/hashCode` của Java.

## 3. Hợp đồng equals và hashCode

### 3.1. Hợp đồng của equals

Với các đối tượng `a`, `b`, `c` không thay đổi về những giá trị dùng để so sánh:

| Thuộc tính | Điều kiện cần đúng |
| --- | --- |
| **Phản xạ** | `a.equals(a)` luôn là `true` |
| **Đối xứng** | `a.equals(b)` có cùng kết quả với `b.equals(a)` |
| **Bắc cầu** | Nếu `a.equals(b)` và `b.equals(c)` thì `a.equals(c)` |
| **Nhất quán** | Khi trạng thái liên quan không đổi, gọi lại `equals` cho cùng kết quả |
| **So với null** | `a.equals(null)` phải trả `false` |

Đối với lớp khóa Cassandra, điều quan trọng nhất là **so sánh theo toàn bộ giá trị primary key**, không theo địa chỉ đối tượng, cột thường hoặc chỉ một phần khóa.

### 3.2. Hợp đồng của hashCode

- Nếu `a.equals(b)` là `true` thì **bắt buộc** `a.hashCode() == b.hashCode()`.
- Hai đối tượng **khác nhau** vẫn **có thể** có cùng hash code; va chạm băm không có nghĩa `equals` được phép trả về `true`.
- Khi các trường tham gia tính băm không đổi, `hashCode()` phải ổn định trong quá trình dùng đối tượng.
- `hashCode()` cần sử dụng **cùng tập thuộc tính** để thể hiện định danh như `equals()`. Nếu thêm cột khóa vào `equals` nhưng quên cập nhật `hashCode`, cấu trúc băm có thể hoạt động sai.

Các phương thức tiện ích `Objects.equals(...)` và `Objects.hash(...)` giúp xử lý so sánh nhất quán và tránh viết lại logic tính băm thủ công. Với khóa chỉ gồm các giá trị bất biến như `UUID`, `LocalDate`, `Instant`, việc triển khai tương đối trực tiếp.

## 4. Ví dụ lớp khóa tổng hợp bất biến

Ví dụ dưới dùng **Spring Data Cassandra với Java driver 4.x**. Lớp khóa được tạo bằng constructor, giữ thuộc tính `final`, không cung cấp setter và dùng constructor binding để Spring Data tạo đối tượng khi đọc dữ liệu.

~~~java
import java.beans.ConstructorProperties;
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public final class EventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id",
        ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private final UUID tenantId;

    @PrimaryKeyColumn(name = "user_id",
        ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private final UUID userId;

    @PrimaryKeyColumn(name = "event_day",
        ordinal = 2, type = PrimaryKeyType.PARTITIONED)
    private final LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at",
        ordinal = 3, type = PrimaryKeyType.CLUSTERED)
    private final Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id",
        ordinal = 4, type = PrimaryKeyType.CLUSTERED)
    private final UUID eventId;

    @PersistenceCreator
    @ConstructorProperties({
        "tenantId", "userId", "eventDay", "occurredAt", "eventId"
    })
    public EventKey(
            UUID tenantId, UUID userId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
        this.userId = Objects.requireNonNull(userId, "userId");
        this.eventDay = Objects.requireNonNull(eventDay, "eventDay");
        this.occurredAt = Objects.requireNonNull(occurredAt, "occurredAt");
        this.eventId = Objects.requireNonNull(eventId, "eventId");
    }

    public UUID getTenantId() { return tenantId; }
    public UUID getUserId() { return userId; }
    public LocalDate getEventDay() { return eventDay; }
    public Instant getOccurredAt() { return occurredAt; }
    public UUID getEventId() { return eventId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof EventKey)) {
            return false;
        }
        EventKey that = (EventKey) other;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(userId, that.userId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(occurredAt, that.occurredAt)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
            tenantId, userId, eventDay, occurredAt, eventId
        );
    }
}
~~~

### 4.1. Vì sao ví dụ này dùng final và constructor?

Đây là **bất biến ở mức đối tượng Java**:

1. Lớp `final` ngăn subclass làm thay đổi ngữ nghĩa `equals`.
2. Các thuộc tính `private final` được gán đúng một lần qua constructor.
3. Không có setter hoặc phương thức “đổi `eventDay`”.
4. `UUID`, `LocalDate` và `Instant` đều là kiểu bất biến, nên trả về trực tiếp từ getter không làm lộ nội trạng có thể sửa.
5. Constructor từ chối `null`, vì các thành phần primary key của hàng Cassandra không thể bị bỏ trống.

**Spring Data cần biết cách tạo đối tượng khi đọc row.** Ví dụ dùng `@PersistenceCreator` và `@ConstructorProperties` để chỉ định constructor và tên thuộc tính. Khi triển khai, hãy kiểm chứng khả năng constructor binding, quy ước đặt tên và hỗ trợ reflection của đúng **phiên bản Spring Data Cassandra**; nếu dự án có cấu hình ánh xạ tùy chỉnh, AOT/native image hoặc cơ chế mapping riêng, cần kiểm tra thêm. Một số dự án dùng lớp khóa có constructor rỗng cùng setter để tương thích framework, nhưng khi đó **phải giữ khóa bất biến về mặt sử dụng** sau khi đã gán giá trị.

### 4.2. Khớp giữa Java class và bảng CQL

| Annotation/thành phần | Ý nghĩa |
| --- | --- |
| `@PrimaryKeyClass` | Khai báo lớp ánh xạ khóa tổng hợp |
| `@PrimaryKeyColumn(name = "...")` | Liên kết thuộc tính Java với **tên cột CQL** |
| `type = PARTITIONED` | Chỉ rõ cột tham gia partition key |
| `type = CLUSTERED` | Chỉ rõ cột tham gia clustering key |
| `ordinal` | Thứ tự các thành phần khóa tương ứng với định nghĩa bảng |
| `@PersistenceCreator` | Chọn constructor cho cơ chế tạo đối tượng của Spring Data |
| `equals/hashCode` | Định nghĩa bằng nhau của **đối tượng Java**, không thay đổi schema Cassandra |

Nếu bảng dùng thứ tự clustering hoặc kiểu dữ liệu khác, mapping phải được đối chiếu với **DDL thực tế**. Một đối tượng khóa có `equals` đúng nhưng `ordinal` hoặc `type` sai vẫn có thể gây lỗi truy vấn hoặc ánh xạ.

## 5. Đặt đối tượng khóa vào entity

Entity dùng `@PrimaryKey` để gắn đối tượng khóa và một cột thường `event_type`:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_user_day")
public class UserEvent {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    protected UserEvent() { }

    public UserEvent(EventKey key, String eventType) {
        this.key = key;
        this.eventType = eventType;
    }

    public EventKey getKey() { return key; }
    public String getEventType() { return eventType; }
    public void setEventType(String eventType) {
        this.eventType = eventType;
    }
}
~~~

Repository có thể dùng **toàn bộ lớp khóa** làm kiểu ID:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface UserEventRepository
        extends CassandraRepository<UserEvent, EventKey> {
}
~~~

Khi tạo `UserEvent`, ứng dụng cần cấp đủ năm thành phần khóa. Ví dụ:

~~~java
UUID tenantId = UUID.randomUUID();
UUID userId = UUID.randomUUID();
UUID eventId = UUID.randomUUID();
LocalDate day = LocalDate.of(2026, 11, 25);
Instant occurredAt = Instant.parse("2026-11-25T02:00:00Z");

EventKey key = new EventKey(
    tenantId, userId, day, occurredAt, eventId
);
UserEvent event = new UserEvent(key, "LOGIN");
repository.save(event);

UserEvent loaded = repository.findById(key).orElseThrow();
assert key.equals(loaded.getKey());
~~~

Ví dụ là trích đoạn trong một service/test đã inject `repository` và import các kiểu Java tương ứng. Cần cluster/keyspace/bảng đã chuẩn bị, và cần kiểm thử tích hợp thay vì giả định tất cả phiên bản Spring Data Cassandra sẽ ánh xạ cùng một constructor giống nhau.

Lưu ý: **entity Java** và **đối tượng khóa** không có cùng vai trò. Entity có thể thay đổi cột thường như `eventType`; **khóa** nên giữ nguyên trong suốt vòng đời đối tượng entity đã được lưu. Không tạo `equals/hashCode` của entity chỉ vì muốn “đồng bộ” với khóa nếu chưa xác định rõ cách entity được dùng trong collection, cache và các trạng thái chưa có ID.

## 6. Điều gì xảy ra nếu đối tượng khóa có thể thay đổi?

### 6.1. Lỗi trong HashMap và HashSet

Giả sử một lớp khóa có setter `setEventDay(...)` và `hashCode()` tính từ `eventDay`. Đoạn mã sau chỉ minh họa **lỗi thiết kế**:

~~~java
MutableEventKey key = new MutableEventKey(
    tenantId, userId, LocalDate.of(2026, 11, 25),
    occurredAt, eventId
);

Set<MutableEventKey> keys = new HashSet<>();
keys.add(key);

// Sai: thuộc tính dùng trong hashCode thay đổi sau khi đã add.
key.setEventDay(LocalDate.of(2026, 11, 26));

// keys.contains(key) giờ có thể trả false dù key là chính đối tượng đó.
boolean stillPresent = keys.contains(key);
~~~

`MutableEventKey` trong ví dụ là lớp giả định có setter; **không** phải class khuyến nghị triển khai. Khi đưa đối tượng vào `HashSet`, collection chọn bucket theo hash code ở thời điểm thêm. Sau khi sửa thuộc tính, hash code mới có thể dẫn đến bucket khác. Kết quả tìm kiếm/xóa bị sai hoặc không ổn định.

Đối tượng khóa dùng làm key cho `Map`, key cache hoặc phần tử của `Set` phải được xem là **value object bất biến**. Không có setter là một cách cưỡng chế hiệu quả điều này trong code.

### 6.2. Lỗi về định danh hàng Cassandra

Nếu `UserEvent` được lưu tại primary key A, sau đó bạn đổi `eventDay` thành ngày khác và gọi `repository.save(event)`, về mặt lưu trữ đó là **primary key B**. Cassandra có thể tạo/cập nhật hàng B, còn hàng A **vẫn tồn tại**.

~~~mermaid
flowchart TD
    A[Đã lưu UserEvent với EventKey A] --> B{Nghiệp vụ cần đổi cột nào?}
    B -->|Cột thường event_type| C[UPDATE hoặc save cùng key A]
    B -->|Thuộc primary key| D[Tạo EventKey B mới]
    D --> E[Ghi dữ liệu ở key B]
    E --> F[Kiểm soát đồng thời, xác minh và xóa key A]
    F --> G[Đối soát trạng thái cuối]
~~~

Nếu cần chuyển một sự kiện sang partition/ngày khác, phải **tạo đối tượng khóa mới**, ghi hàng với khóa mới và xử lý xóa hàng ở khóa cũ theo workflow có kiểm soát. Đây là các mutation riêng biệt, đặc biệt khi hai khóa thuộc những partition khác nhau. Không mặc định có transaction nhiều partition với isolation như hệ quan hệ; cần tính đến timeout, retry, ghi trùng tạm thời, mất cập nhật và consistency level.

Việc làm cho lớp `EventKey` bất biến **ngăn lỗi vô ý ở Java**, nhưng không tự bảo đảm hai mutation “ghi mới + xóa cũ” là nguyên tử.

## 7. Những lỗi triển khai equals/hashCode thường gặp

### 7.1. Quên clustering key hoặc tenant ID

**Sai:**

~~~java
@Override
public boolean equals(Object other) {
    if (!(other instanceof EventKey)) return false;
    EventKey that = (EventKey) other;
    return Objects.equals(userId, that.userId)
        && Objects.equals(eventDay, that.eventDay);
}
~~~

Đoạn này bỏ `tenantId`, `occurredAt` và `eventId`. Hai hàng khác nhau có thể bị coi là cùng một khóa, nhất là khi user ID được sử dụng xuyên tenant hoặc có nhiều sự kiện trong một ngày. **Đúng:** cả `equals` và `hashCode` phải dựa trên **đúng năm thành phần primary key** của bảng.

### 7.2. Thêm cột thường vào equals/hashCode của khóa

Giả sử `eventType` có thể đổi từ `LOGIN` thành `LOGOUT`. `eventType` không thuộc primary key và cũng **không nên có mặt trong `EventKey`**. Nếu vô tình cho dữ liệu thường vào tính băm, việc sửa thuộc tính nghiệp vụ có thể làm “đổi identity” của đối tượng trong Java dù cùng một hàng Cassandra.

**Nguyên tắc:** định nghĩa bằng nhau của khóa dựa trên **primary-key columns**, không dựa trên toàn bộ row hoặc thuộc tính phục vụ hiển thị.

### 7.3. Chỉ override equals nhưng không override hashCode

Trong Java, mọi lớp kế thừa `Object` có `hashCode()` mặc định. Nếu override `equals()` theo giá trị nhưng giữ `hashCode()` mặc định theo identity, hai đối tượng cùng khóa có thể mang hash khác nhau, vi phạm hợp đồng và gây lỗi trong `HashMap`/`HashSet`.

**Quy tắc:** nếu override một trong hai phương thức vì cần value equality thì phải triển khai **cả hai** một cách nhất quán.

### 7.4. Lạm dụng Lombok @Data

Lombok có thể sinh `equals/hashCode`, nhưng cần kiểm tra chính xác những thuộc tính được đưa vào. Với một **key class** chỉ chứa primary-key columns, `@EqualsAndHashCode` có thể hợp lý; vẫn phải đảm bảo không có trường phụ (cache, trạng thái tạm, cột dữ liệu thường) làm thay đổi ngữ nghĩa.

Ví dụ minh họa lựa chọn trường rõ ràng:

~~~java
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public final class EventKeyValue {
    @EqualsAndHashCode.Include private final UUID tenantId;
    @EqualsAndHashCode.Include private final UUID userId;
    @EqualsAndHashCode.Include private final LocalDate eventDay;
    @EqualsAndHashCode.Include private final Instant occurredAt;
    @EqualsAndHashCode.Include private final UUID eventId;

    // Constructor và getters; ví dụ này chỉ minh họa Lombok.
}
~~~

Đây là **một value class minh họa**, không phải key mapping đầy đủ của Spring Data Cassandra. Khi dùng Lombok thực sự với `@PrimaryKeyClass`, phải khai báo mapping, constructor và kiểm tra code được Lombok tạo. `@Data` có thể tự sinh setter nếu thuộc tính không `final`, làm khóa trở nên dễ bị sửa ngoài ý muốn.

### 7.5. Dùng kiểu dữ liệu có quy tắc bằng nhau không phù hợp

Đặc biệt chú ý **timestamp**: Cassandra lưu CQL `timestamp` ở độ chính xác **mili giây**. Java `Instant` có thể chứa nano giây. Nếu tạo key có `2026-11-25T02:00:00.123456789Z` rồi lưu/đọc lên, dữ liệu lưu có thể chỉ còn `2026-11-25T02:00:00.123Z`. Khi đó `Instant.equals` có thể trả `false` dù bản ghi đọc từ Cassandra là đúng theo độ chính xác của cột.

Với `occurredAt` là một phần primary key, ứng dụng cần **chuẩn hóa độ chính xác trước khi tạo khóa** và dùng cùng quy tắc ở mọi đường ghi/đọc:

~~~java
import java.time.temporal.ChronoUnit;

Instant normalizedOccurredAt =
    rawOccurredAt.truncatedTo(ChronoUnit.MILLIS);

EventKey key = new EventKey(
    tenantId, userId, eventDay, normalizedOccurredAt, eventId
);
~~~

Tránh những loại key có trạng thái nội bộ thay đổi, định dạng tùy vùng thời gian hoặc so sánh không thống nhất. Một ví dụ khác là `BigDecimal.equals` có tính đến scale ở Java trong khi một số phép xử lý dữ liệu có thể coi các biểu diễn số là tương đương; nếu số thập phân tham gia khóa, hãy có quy tắc chuẩn hóa cụ thể và test round-trip. Trong bảng ví dụ, dùng `UUID`/`LocalDate`/`Instant` giúp hạn chế phần lớn vấn đề đó.

### 7.6. Dùng collection hoặc array làm thành phần khóa

Nếu một lớp giá trị chứa `byte[]` hoặc danh sách có thể thay đổi, `Objects.equals` mặc định trên array là so sánh tham chiếu, và nội dung array có thể bị chỉnh sửa sau khi gán. Khi bắt buộc cần kiểu như vậy trong value object, phải thực hiện **defensive copy** và dùng so sánh/băm nội dung phù hợp. Đối với khóa Cassandra, nên ưu tiên các kiểu giá trị mà mapper hỗ trợ và có ngữ nghĩa bằng nhau đơn giản.

## 8. Immutable key với Java record hoặc @Value: cân nhắc gì?

Java `record` có sẵn constructor, `equals`, `hashCode` và accessor theo thành phần, đồng thời các component của record không có setter. Về mặt **Java value object**, record rất phù hợp với ý tưởng khóa bất biến:

~~~java
public record EventIdentity(
    UUID tenantId,
    UUID userId,
    LocalDate eventDay,
    Instant occurredAt,
    UUID eventId
) {
    public EventIdentity {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(userId);
        Objects.requireNonNull(eventDay);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(eventId);
    }
}
~~~

**Tuy nhiên:** `EventIdentity` ở đây là ví dụ **value object thuần Java**. Không được mặc định rằng thêm `@PrimaryKeyClass` lên mọi record sẽ được Spring Data Cassandra hỗ trợ như lớp khóa có annotation trên field ở mọi phiên bản. Khả năng mapping record, annotation target, constructor binding và AOT cần được xác minh với **bộ Spring Boot/Spring Data Cassandra/Java driver thực tế** bằng test tích hợp.

Tương tự, Lombok `@Value` có thể giúp tạo lớp bất biến, nhưng annotation mapping và đường tạo đối tượng vẫn phải được khai báo đúng. **Tính bất biến của Java** và **khả năng ánh xạ của framework** là hai điều kiện cần kiểm tra riêng.

## 9. Kiểm thử equals/hashCode và mapping

### 9.1. Unit test kiểm tra hợp đồng Java

Các bài test tối thiểu:

~~~java
@Test
void keysWithSameValuesAreEqual() {
    UUID tenant = UUID.randomUUID();
    UUID user = UUID.randomUUID();
    UUID event = UUID.randomUUID();
    LocalDate day = LocalDate.of(2026, 11, 25);
    Instant at = Instant.parse("2026-11-25T02:00:00Z");

    EventKey a = new EventKey(tenant, user, day, at, event);
    EventKey b = new EventKey(tenant, user, day, at, event);

    assertNotSame(a, b);
    assertEquals(a, b);
    assertEquals(b, a);
    assertEquals(a.hashCode(), b.hashCode());

    Set<EventKey> keys = new HashSet<>();
    keys.add(a);
    assertTrue(keys.contains(b));
}

@Test
void eachPrimaryKeyComponentAffectsEquality() {
    UUID tenant = UUID.randomUUID();
    UUID user = UUID.randomUUID();
    UUID event = UUID.randomUUID();
    LocalDate day = LocalDate.of(2026, 11, 25);
    Instant at = Instant.parse("2026-11-25T02:00:00Z");
    EventKey original = new EventKey(tenant, user, day, at, event);

    assertNotEquals(original, new EventKey(
        UUID.randomUUID(), user, day, at, event));
    assertNotEquals(original, new EventKey(
        tenant, UUID.randomUUID(), day, at, event));
    assertNotEquals(original, new EventKey(
        tenant, user, day.plusDays(1), at, event));
    assertNotEquals(original, new EventKey(
        tenant, user, day, at.plusSeconds(1), event));
    assertNotEquals(original, new EventKey(
        tenant, user, day, at, UUID.randomUUID()));
}
~~~

Các đoạn test cần import JUnit 5, `java.util.Set`, `HashSet`, `UUID`, `LocalDate`, `Instant` và các assertion thích hợp. Chúng kiểm tra **logic value object** nhưng chưa chứng minh Spring Data Cassandra ánh xạ đúng thành phần khóa.

### 9.2. Test tích hợp đọc/ghi Cassandra

Tạo keyspace/bảng `events_by_user_day` theo schema đã khai báo, dùng Cassandra thật trong môi trường thử nghiệm hoặc môi trường test tương đương. Sau đó:

1. Khởi tạo `EventKey` với timestamp đã chuẩn hóa đến mili giây.
2. Lưu entity qua repository hoặc `CassandraTemplate`.
3. Đọc lại bằng `findById(key)`; kiểm tra `equals` và `hashCode` của khóa trước/sau đọc.
4. Truy vấn trực tiếp CQL bằng đầy đủ thành phần khóa để xác thực mapping `PARTITIONED`/`CLUSTERED`, `ordinal` và tên cột.
5. Ghi sự kiện thứ hai có cùng partition key nhưng khác `event_id`; kiểm tra cả hai cùng tồn tại và hai đối tượng khóa **không bằng nhau**.
6. Thử timestamp có nano giây, quan sát vòng chuyển đổi rồi áp dụng quy tắc chuẩn hóa thống nhất.
7. Đảm bảo thay đổi `eventType` không làm đổi khóa hoặc khiến logic tìm kiếm theo ID thất bại.

Test với **mock repository** không kiểm tra được tính tương thích constructor binding, codec Cassandra, độ chính xác timestamp, mapping cột hay hành vi upsert. Đây là lý do test tích hợp cần có đối với cấu trúc khóa tổng hợp.

### 9.3. Bảng kiểm tra nhanh

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai instance khác địa chỉ nhưng cùng đủ thành phần khóa | `equals == true` và `hashCode` bằng nhau |
| Khác một thành phần partition key | `equals == false` |
| Khác một clustering column | `equals == false` |
| So sánh với `null` hoặc loại đối tượng khác | `equals == false` |
| Lưu khóa trong `HashSet` và truy vấn lại bằng instance cùng giá trị | Tìm thấy |
| Đổi cột thường của entity | Khóa không đổi |
| Đổi khóa nghiệp vụ | Tạo key mới, xử lý chuyển và xóa hàng cũ theo quy trình |
| Lưu/đọc từ Cassandra | Giá trị khóa đọc lại bằng giá trị khóa đầu vào đã chuẩn hóa |

## 10. Liên hệ với thiết kế dữ liệu phân tán

Một đối tượng khóa có `equals/hashCode` đúng **không đủ** để bảo đảm một hệ thống Cassandra hiệu quả. Khi thiết kế bảng theo truy vấn vẫn cần:

- **Partition key:** chọn đủ độ phân tán, không tạo hot partition, không để partition tăng không giới hạn.
- **Clustering key:** phản ánh thứ tự dữ liệu thực sự cần đọc, phù hợp với truy vấn CQL và paging.
- **Tính nhất quán:** hiểu số replica được yêu cầu theo consistency level và nguy cơ timeout/kết quả chưa chắc chắn.
- **Đổi khóa:** nếu một thuộc tính nghiệp vụ thay đổi thường xuyên, cân nhắc có nên dùng nó làm partition key hay phải có bảng tra cứu theo ID ổn định và các bảng phục vụ truy vấn riêng.
- **Paging:** paging state gắn với truy vấn; khóa và thứ tự cần được thiết kế ổn định để phân trang có ý nghĩa.
- **Hiệu năng:** ghi/xóa khi đổi khóa có chi phí và sinh tombstone; khóa bất biến trong Java giúp tránh thao tác sai nhưng không xóa được chi phí hệ phân tán.

Chẳng hạn, nếu người dùng thường xuyên đổi `event_day` hoặc chuyển sự kiện sang user khác, việc dùng các thuộc tính đó trong partition key có thể gây nhiều lần ghi mới/xóa cũ. Hãy đánh giá **access pattern** và thiết kế đường tra cứu phù hợp thay vì cố “cho phép setter” lên `EventKey`.

## 11. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Hai đối tượng khóa Java khác nhau luôn là hai hàng Cassandra khác nhau.” | Hai instance có **cùng toàn bộ primary key** mô tả cùng định danh hàng |
| “Chỉ cần so sánh partition key.” | **Clustering columns** cũng góp phần định danh hàng |
| “Có `equals` là đủ, không cần `hashCode`.” | Hai phương thức phải tuân theo hợp đồng nhất quán để collection hoạt động đúng |
| “Hash code của Java giúp Cassandra chọn replica.” | Cassandra tính **partition token** bằng thuật toán của cluster, độc lập với Java `hashCode` |
| “Thay setter của khóa rồi save sẽ tự xóa hàng cũ.” | Khóa mới dẫn tới hàng mới; cần xử lý xóa hàng cũ riêng |
| “`@Data` luôn là lựa chọn tốt nhất cho key class.” | Setter và trường phát sinh có thể phá bất biến/ngữ nghĩa định danh |
| “Record Java luôn mapping tốt trên mọi phiên bản Spring Data Cassandra.” | Khả năng mapping phải xác minh theo phiên bản và test tích hợp |
| “`Instant` nano giây đọc lại vẫn bằng nguyên giá trị khóa.” | CQL timestamp lưu ở độ chính xác mili giây, cần chuẩn hóa |
| “Dùng khóa bất biến bảo đảm transaction xuyên partition.” | Bất biến giải quyết hành vi đối tượng; transaction phân tán là vấn đề khác |

## 12. Câu hỏi tự kiểm tra

1. Trong bảng `events_by_user_day`, năm thành phần primary key là gì? Thành phần nào là partition key, thành phần nào là clustering key?
2. Vì sao hai `EventKey` khác instance nhưng cùng giá trị cần có cùng `hashCode()`?
3. Vì sao không được bỏ `event_id` khỏi `equals()` dù `event_id` không tham gia tính partition token?
4. Điều gì xảy ra khi đổi `eventDay` của một key đã được thêm vào `HashSet`?
5. `@PrimaryKeyClass` và `@PrimaryKeyColumn` chịu trách nhiệm gì, còn `equals/hashCode` chịu trách nhiệm gì?
6. Lớp `final` với field `final` và constructor binding có lợi ích gì đối với đối tượng khóa?
7. Khi nào cần `@PersistenceCreator` hoặc kiểm tra constructor binding theo phiên bản Spring Data?
8. Vì sao `@Data` hoặc việc thêm thuộc tính thường vào lớp khóa có thể nguy hiểm?
9. Vì sao khóa chứa `Instant` cần quy tắc chuẩn hóa mili giây trước khi lưu vào cột `timestamp`?
10. Vì sao cần cả unit test value equality và test tích hợp đọc/ghi Cassandra?
11. Nếu nghiệp vụ cần đổi `user_id` của một sự kiện, lệnh `save` với khóa mới có tự xóa hàng cũ không?
12. Khóa Java bất biến giúp giảm lỗi nào, và **không** giải quyết được những vấn đề phân tán nào?

**Ghi nhớ:** đối tượng khóa trong Spring Data Cassandra nên được xem là **value object bất biến**, với `equals()` và `hashCode()` dựa trên **toàn bộ primary key**. Điều đó giữ cho Java collection, mapping và logic định danh nhất quán. Cassandra vẫn lưu trữ, định tuyến và cập nhật dữ liệu theo quy tắc của partition key, clustering key và các bảo đảm phân tán của chính nó.
