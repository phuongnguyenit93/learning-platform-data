# Optional, danh sách và kết quả không tồn tại trong Spring Data Cassandra Repository

## 1. Vì sao kiểu trả về của repository quan trọng?

Trong **Spring Data Cassandra**, repository giúp ứng dụng Java truy cập **Apache Cassandra** thông qua entity mapping và các câu truy vấn CQL. Chọn kiểu trả về đúng không chỉ là vấn đề cú pháp Java: nó thể hiện **truy vấn dự kiến có một hay nhiều hàng**, **không tìm thấy dữ liệu có phải tình huống bình thường không** và **ứng dụng cần phản hồi ra sao**.

Ví dụ, một hệ thống đơn hàng cung cấp hai chức năng:

- **Xem chi tiết đơn hàng theo ID:** một ID hợp lệ có thể chưa tồn tại, đã bị xóa hoặc hết hạn. Kết quả hợp lý ở Java là `Optional<OrderRow>`.
- **Xem danh sách sự kiện của khách hàng trong một ngày:** ngày đó có thể chưa có sự kiện nào. Kết quả hợp lý là `List<CustomerEventRow>` **rỗng**, không phải một bản ghi giả hay một lỗi.

Bài này thuộc chương **Repository**, chủ đề **“Optional, danh sách và kết quả không tồn tại”** của module `SPRING_DATA_CASSANDRA`. Bên cạnh repository, những nguyên tắc tương tự cần được áp dụng khi dùng `CassandraTemplate`, truy vấn CQL trực tiếp hoặc xây dựng REST API. Chúng phải đi đôi với thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng của Cassandra.

**Sau khi học, bạn cần làm được:**

1. Phân biệt `Optional<T>`, `List<T>`/`Iterable<T>`, giá trị `null` và ngoại lệ truy cập dữ liệu.
2. Chọn kiểu trả về dựa trên số lượng kết quả hợp lệ của truy vấn, thay vì đoán từ tên phương thức.
3. Xử lý đúng `Optional.empty()` và danh sách rỗng ở tầng service/API.
4. Không che giấu timeout, lỗi kết nối, thiếu quyền hoặc lỗi mapping dưới dạng “không tìm thấy”.
5. Hiểu vì sao Cassandra không thích hợp với truy vấn danh sách không giới hạn, tìm kiếm tùy ý hoặc phân trang kiểu `OFFSET`.
6. Viết được các kiểm thử cho kết quả 0, 1, nhiều hàng và trường hợp hệ phân tán gặp lỗi.

## 2. Bốn loại kết quả không nên nhầm lẫn

| Trường hợp | Kiểu/biểu hiện ở Java | Cách hiểu |
| --- | --- | --- |
| Tìm một hàng và **có** kết quả | `Optional.of(entity)` | Đã đọc được hàng phù hợp |
| Tìm một hàng và **không có** kết quả | `Optional.empty()` | Truy vấn hoàn tất, không trả về hàng theo góc nhìn của lần đọc đó |
| Truy vấn nhiều hàng và **không có** kết quả | `List.of()` hoặc danh sách rỗng tương đương | Truy vấn hoàn tất nhưng tập kết quả bằng 0 |
| Cột của một hàng có giá trị thiếu | `entity.getNote() == null` nếu field cho phép null | **Hàng tồn tại**, nhưng một trường không có giá trị |
| Lỗi mạng, timeout, truy vấn sai, mapping hỏng | **Exception** | Không có kết quả hợp lệ để kết luận dữ liệu không tồn tại |

**Kết luận:** `Optional.empty()` và một `List` rỗng là **kết quả thành công ở cấp truy vấn**. Ngoại lệ là **không thể hoàn tất thao tác như mong muốn**. Không nên biến mọi ngoại lệ thành “empty”.

Đối với repository chuẩn, `findById(id)` trả `Optional<T>`. Với phương thức đọc danh sách tự định nghĩa, có thể chọn `List<T>` hoặc kiểu collection được Spring Data Cassandra hỗ trợ trong phiên bản đang dùng. Những kiểu đó thể hiện hợp đồng cụ thể hơn so với trả `Object` hoặc `null` không rõ nghĩa.

## 3. Thiết kế bảng theo truy vấn trước khi chọn kiểu trả về

Giả sử ứng dụng cần hai access pattern:

1. `findById(orderId)`: tìm **một đơn hàng** theo khóa `order_id`.
2. `findRecentEvents(customerId, day)`: lấy tối đa 20 sự kiện **của một khách hàng trong một ngày**, mới nhất trước.

Hai nhu cầu khác nhau nên có hai bảng phù hợp:

~~~sql
-- Tra cứu một đơn hàng theo định danh duy nhất.
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    note text
);

-- Tra cứu danh sách sự kiện trong một partition đã biết.
CREATE TABLE events_by_customer_day (
    customer_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((customer_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**Giải thích các khóa:**

- `orders_by_id.order_id` là partition key của bảng đơn hàng; một ID khớp tối đa một hàng.
- `events_by_customer_day` có **partition key tổng hợp** `(customer_id, event_day)`; mỗi ngày của mỗi khách hàng là một partition logic.
- `occurred_at` và `event_id` là **clustering columns**, xác định từng sự kiện và thứ tự bên trong partition.
- `event_id` giúp phân biệt các sự kiện có cùng thời điểm.
- Việc chia partition theo ngày chỉ là lựa chọn minh họa: cần đo lưu lượng và kích thước partition. Khách hàng có hàng triệu sự kiện mỗi ngày có thể cần bucket nhỏ hơn.

Truy vấn tương ứng:

~~~sql
-- Không tồn tại: trả 0 hàng; tồn tại: tối đa 1 hàng.
SELECT * FROM orders_by_id
WHERE order_id = ?;

-- Không có sự kiện: trả 0 hàng; có thể trả nhiều hàng, tối đa 20.
SELECT * FROM events_by_customer_day
WHERE customer_id = ? AND event_day = ?
LIMIT 20;
~~~

**Không được suy luận** rằng vì một phương thức Java trả `List<T>` nên Cassandra có thể quét, lọc hoặc sắp xếp tùy ý. Truy vấn CQL vẫn cần đường truy cập dựa trên khóa hoặc một khả năng lập chỉ mục cụ thể đã được lựa chọn và kiểm chứng. Repository chỉ tạo một lớp trừu tượng lập trình trên Cassandra, không biến nó thành cơ sở dữ liệu quan hệ có `JOIN` và `OFFSET` tùy ý.

## 4. Optional<T>: kết quả một hàng có thể vắng mặt

### 4.1. Entity và repository đơn giản

Lớp entity ánh xạ bảng `orders_by_id`:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRow {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("state")
    private String state;

    @Column("note")
    private String note;

    protected OrderRow() { }

    public OrderRow(UUID orderId, UUID customerId, String state, String note) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.state = state;
        this.note = note;
    }

    public UUID getOrderId() { return orderId; }
    public UUID getCustomerId() { return customerId; }
    public String getState() { return state; }
    public String getNote() { return note; }
}
~~~

Repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderRepository
        extends CassandraRepository<OrderRow, UUID> {
    // findById(UUID id) được kế thừa từ repository CRUD.
}
~~~

`findById(...)` biểu thị **lookup theo toàn bộ primary key**. Ví dụ:

~~~java
UUID orderId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

Optional<OrderRow> result = orderRepository.findById(orderId);

if (result.isPresent()) {
    System.out.println(result.get().getState());
} else {
    System.out.println("Order not found");
}
~~~

Đoạn trích giả định có `orderRepository` được inject và import `java.util.Optional`. Đây là ví dụ giải thích trạng thái; trong code service thường dùng `map(...)`, `orElseThrow(...)` hoặc `orElseGet(...)` thay vì gọi `get()` không kiểm tra.

### 4.2. Các phép xử lý Optional nên biết

| Cách viết | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `optional.map(OrderRow::getState)` | Chuyển giá trị nếu có; nếu vắng mặt vẫn là `Optional.empty()` | Lấy một thuộc tính hoặc chuyển entity sang DTO |
| `optional.flatMap(...)` | Chuyển sang một `Optional` khác mà không lồng hai lớp Optional | Thao tác tiếp có thể không có kết quả |
| `optional.filter(predicate)` | Giữ giá trị nếu thỏa điều kiện | Kiểm tra điều kiện sau khi lookup |
| `optional.orElse(defaultValue)` | Dùng giá trị mặc định nếu rỗng | Giá trị dự phòng rẻ, đã sẵn có |
| `optional.orElseGet(supplier)` | Tạo giá trị mặc định **lười** nếu rỗng | Giá trị dự phòng tốn chi phí |
| `optional.orElseThrow(supplier)` | Phát sinh ngoại lệ nghiệp vụ nếu rỗng | Trường hợp bắt buộc phải có đơn hàng |
| `optional.ifPresent(consumer)` | Chạy hành động khi có giá trị | Side effect đơn giản, không cần trả kết quả |

Ví dụ chuyển sang DTO ở tầng service:

~~~java
public Optional<OrderSummary> findSummary(UUID orderId) {
    return orderRepository.findById(orderId)
        .map(row -> new OrderSummary(
            row.getOrderId(), row.getState()
        ));
}
~~~

`OrderSummary` là DTO của ứng dụng. Khi đơn hàng không tồn tại, `findSummary` trả `Optional.empty()` mà không phải tạo DTO giả với `orderId = null`.

**Lưu ý về `orElse`:** tham số của `orElse(expensiveFallback())` được tính **ngay cả khi Optional có giá trị**, vì Java đánh giá biểu thức truyền vào phương thức trước khi gọi. Nếu fallback tốn chi phí, dùng `orElseGet(() -> expensiveFallback())`.

### 4.3. Không lạm dụng get(), null hoặc dữ liệu giả

Các cách làm không nên áp dụng:

~~~java
// Dễ gây NoSuchElementException khi thiếu hàng:
OrderRow a = orderRepository.findById(orderId).get();

// Che mất ý nghĩa "không tồn tại" bằng một hàng giả:
OrderRow b = orderRepository.findById(orderId)
    .orElse(new OrderRow(orderId, null, "UNKNOWN", null));

// Nếu dùng Optional cho hợp đồng một hàng, tránh trả null:
Optional<OrderRow> c = null;
~~~

`NoSuchElementException` do `Optional.get()` trên Optional rỗng không nên là cách mặc định để tạo thông báo “đơn hàng không tồn tại”. Một hàng giả cũng dễ bị ghi ngược vào Cassandra hoặc khiến ứng dụng tưởng dữ liệu thật đã tồn tại.

**Nguyên tắc:** dùng `Optional` cho **giá trị trả về có thể vắng mặt**, không dùng nó như cách giấu dữ liệu không hợp lệ. Với entity được Spring Data mapping, tránh tự chọn `Optional<T>` cho mọi field lưu trữ; xử lý `null`/trạng thái vắng mặt của từng cột theo đúng ngữ nghĩa domain và converter.

## 5. List<T>: kết quả nhiều hàng có thể là danh sách rỗng

### 5.1. Lớp khóa tổng hợp cho bảng sự kiện

Với bảng `events_by_customer_day`, một row cần đủ partition key và clustering columns:

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
public class CustomerEventKey implements Serializable {
    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;

    protected CustomerEventKey() { }

    public CustomerEventKey(
            UUID customerId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {
        this.customerId = Objects.requireNonNull(customerId);
        this.eventDay = Objects.requireNonNull(eventDay);
        this.occurredAt = Objects.requireNonNull(occurredAt);
        this.eventId = Objects.requireNonNull(eventId);
    }

    public UUID getCustomerId() { return customerId; }
    public LocalDate getEventDay() { return eventDay; }
    public Instant getOccurredAt() { return occurredAt; }
    public UUID getEventId() { return eventId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CustomerEventKey)) return false;
        CustomerEventKey that = (CustomerEventKey) other;
        return Objects.equals(customerId, that.customerId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(occurredAt, that.occurredAt)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(customerId, eventDay, occurredAt, eventId);
    }
}
~~~

**Cần đủ bốn thành phần khóa** trong `equals/hashCode` vì mọi hàng trong cùng partition có thể khác `occurred_at` hoặc `event_id`. Với CQL `timestamp`, chuẩn hóa độ chính xác của `Instant` đến **mili giây** trước khi dùng làm khóa nếu cần so sánh round-trip Java ↔ Cassandra.

### 5.2. Entity và repository trả danh sách

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_customer_day")
public class CustomerEventRow {
    @PrimaryKey
    private CustomerEventKey key;

    @Column("event_type")
    private String eventType;

    protected CustomerEventRow() { }

    public CustomerEventRow(CustomerEventKey key, String eventType) {
        this.key = key;
        this.eventType = eventType;
    }

    public CustomerEventKey getKey() { return key; }
    public String getEventType() { return eventType; }
}
~~~

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface CustomerEventRepository
        extends CassandraRepository<CustomerEventRow, CustomerEventKey> {

    @Query("SELECT * FROM events_by_customer_day " +
           "WHERE customer_id = ?0 AND event_day = ?1 LIMIT 20")
    List<CustomerEventRow> findRecentEvents(
        UUID customerId, LocalDate eventDay
    );
}
~~~

Annotation `@Query` ở đây minh họa **truy vấn CQL cụ thể có đầy đủ partition key**. Hai tham số `?0` và `?1` được bind theo vị trí; Spring Data Cassandra hỗ trợ các cách khai báo truy vấn phụ thuộc phiên bản, vì vậy cần kiểm tra đúng API của dòng Spring Data trong dự án và chạy test tích hợp.

Vì bảng sắp xếp `occurred_at DESC`, truy vấn trên trả về các sự kiện mới nhất **trong partition của khách hàng và ngày được chỉ định**. `LIMIT 20` hạn chế tổng số hàng của truy vấn, tránh vô tình tải toàn bộ lịch sử vào danh sách Java. Nó **không** lấy toàn bộ lịch sử và cũng **không** tạo chức năng đọc trang thứ hai.

### 5.3. Danh sách rỗng là kết quả hợp lệ

~~~java
List<CustomerEventRow> events =
    customerEventRepository.findRecentEvents(customerId, day);

if (events.isEmpty()) {
    // Không có sự kiện phù hợp tại thời điểm đọc.
    return List.of();
}

return events.stream()
    .map(row -> toResponse(row))
    .toList();
~~~

Ví dụ nằm trong một method trả `List<EventResponse>`, đã có biến `customerId`, `day` và hàm `toResponse(...)`; `Stream.toList()` yêu cầu phiên bản Java hỗ trợ. Khi truy vấn danh sách hợp lệ nhưng không có hàng, repository Spring Data thông thường trả **collection rỗng**; API của bạn nên giữ hợp đồng đó thay vì trả `null`.

Với code service chung:

- **Một bản ghi:** `Optional<OrderRow>`, không tìm thấy là `Optional.empty()`.
- **Nhiều bản ghi:** `List<CustomerEventRow>`, không tìm thấy là `[]`.
- Tránh `Optional<List<CustomerEventRow>>` cho tình huống danh sách bình thường: vừa có “không có danh sách” vừa có “danh sách rỗng”, nhưng đa số nghiệp vụ không cần hai trạng thái này.
- Tránh biến danh sách rỗng thành một entity “placeholder” có khóa `null`.

**Lưu ý phiên bản:** những CRUD method kế thừa có thể trả `Iterable<T>` thay vì `List<T>` tùy repository interface và phiên bản Spring Data. Ví dụ phương thức `findAllById(ids)` thường trả `Iterable<T>`, và những ID không có dữ liệu không được biểu diễn thành phần tử `Optional.empty()` tương ứng trong kết quả. Khi muốn giữ chính xác thứ tự/khả năng thiếu từng ID, phải tự xây dựng cấu trúc kết quả bằng định danh ở tầng service.

## 6. Không tồn tại khác với cột null, dữ liệu hết hạn hoặc lỗi truy cập

### 6.1. Hàng không tồn tại

Với truy vấn:

~~~sql
SELECT order_id, state, note
FROM orders_by_id
WHERE order_id = ?;
~~~

Nếu Cassandra trả **0 hàng**, repository trả `Optional.empty()`. Nhưng kết quả đó chỉ phản ánh **lần đọc theo consistency level đã dùng**. Không nên kết luận rằng ID đó “chưa từng tồn tại ở bất kỳ replica nào” hoặc “không bao giờ có thể xuất hiện”.

### 6.2. Hàng tồn tại, một trường null

Ví dụ đơn hàng đã tồn tại nhưng chưa có ghi chú:

~~~text
order_id = 11111111-1111-4111-8111-111111111111
state    = CREATED
note     = null
~~~

Kết quả có thể là **`Optional.of(OrderRow)`**, và `order.getNote() == null`. Đây là hai mức ý nghĩa khác nhau: một ở cấp **hàng**, một ở cấp **cột**.

Nếu cần biểu diễn “ghi chú chưa có” ở API, có thể thiết kế DTO với trường nullable hoặc kiểu trạng thái nghiệp vụ rõ ràng. Không nên suy rằng chỉ vì một cột `null` thì cả hàng phải thành `Optional.empty()`.

### 6.3. TTL, DELETE và tombstone

Cassandra hỗ trợ **TTL** và thao tác xóa. Sau khi dữ liệu hết hạn hoặc bị xóa, các lần đọc theo điều kiện thích hợp có thể không còn trả hàng đó; phía repository nhận kết quả rỗng. Trong hệ lưu trữ, các dấu xóa (**tombstone**) có thể vẫn tồn tại một thời gian và được xử lý qua compaction theo quy tắc Cassandra.

Điều này không đồng nghĩa repository phải hiển thị tombstone như một entity “đã xóa”. Nếu nghiệp vụ cần phân biệt **chưa từng tạo**, **đã xóa**, **đã hết hạn**, hãy thiết kế thông tin trạng thái/audit riêng thay vì kỳ vọng `Optional.empty()` tự cho biết nguyên nhân.

### 6.4. Lỗi và kết quả không chắc chắn trong hệ phân tán

| Tình huống | Cách xử lý đúng hướng |
| --- | --- |
| Truy vấn hợp lệ trả 0 hàng | `Optional.empty()` hoặc danh sách rỗng |
| Query CQL sai khóa/kiểu hoặc bảng không tồn tại | Sửa truy vấn/schema; ghi nhận ngoại lệ |
| Client không kết nối được node phù hợp | Xử lý lỗi hạ tầng, không báo “không tìm thấy” |
| `ReadTimeout` hoặc `Unavailable` | Xử lý theo chính sách retry/timeout và tính nhất quán |
| Lỗi mapping/converter | Sửa entity mapping/dữ liệu hoặc migration; không biến thành rỗng |
| Không đủ quyền đọc | Xử lý lỗi phân quyền, không thay bằng kết quả giả |
| `WriteTimeout` khi vừa ghi rồi đọc | Trạng thái lần ghi trước có thể chưa rõ; phải xét idempotency/đối soát |

**Sai lầm nghiêm trọng:** bắt mọi `Exception` rồi trả `Optional.empty()`. Cách làm này che giấu sự cố cluster và có thể khiến HTTP trả **404 Not Found** trong khi dữ liệu thực sự tồn tại. Service nên để các lỗi kỹ thuật đi qua cơ chế phân loại/log/response thích hợp.

## 7. Tầng service: thống nhất hợp đồng dữ liệu

Repository truy cập dữ liệu, còn **service** diễn giải ý nghĩa nghiệp vụ. Có hai cách hợp lý cho lookup một hàng.

### 7.1. Trả Optional để caller quyết định

~~~java
@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<OrderRow> findById(UUID id) {
        Objects.requireNonNull(id, "id");
        return orders.findById(id);
    }
}
~~~

Đoạn code cần import `@Service`, `Optional`, `Objects`, `UUID`. `Objects.requireNonNull` làm rõ rằng **ID null là input không hợp lệ**, không được biến thành `Optional.empty()`. Thông thường, truyền ID null vào repository có thể gây `IllegalArgumentException` theo hợp đồng API Spring Data.

### 7.2. Ném ngoại lệ nghiệp vụ khi trường hợp bắt buộc

~~~java
public OrderRow requireOrder(UUID orderId) {
    return orders.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));
}
~~~

`OrderNotFoundException` là lớp ngoại lệ **do ứng dụng định nghĩa**. Cách này phù hợp nếu bước nghiệp vụ tiếp theo không thể tiếp tục khi đơn hàng thiếu. Đừng dùng ngoại lệ cho **danh sách rỗng bình thường**, ví dụ khách hàng chưa có sự kiện nào trong ngày.

**Không gọi `existsById` trước `findById` một cách máy móc**: hai lượt truy vấn tách biệt tăng round-trip và vẫn có race condition (hàng có thể thay đổi giữa hai lần đọc). Nếu cần lấy dữ liệu, đọc trực tiếp bằng `findById` thường hợp lý hơn; `existsById` phù hợp khi chỉ cần kiểm tra tồn tại và đã đánh giá chi phí.

### 7.3. Hàm đọc danh sách giữ kết quả rỗng

~~~java
public List<CustomerEventRow> recentEvents(UUID customerId, LocalDate day) {
    Objects.requireNonNull(customerId, "customerId");
    Objects.requireNonNull(day, "day");
    return customerEventRepository.findRecentEvents(customerId, day);
}
~~~

Không có dữ liệu → danh sách rỗng. Nếu yêu cầu bắt buộc phải có ít nhất một sự kiện (tình huống đặc biệt), service có thể **chủ động áp đặt quy tắc**; repository không tự biết quy tắc đó.

## 8. REST API: 404 cho một tài nguyên, 200 [] cho danh sách

Với REST API, một cách thiết kế rõ ràng là:

| HTTP request | Trường hợp | Phản hồi minh họa |
| --- | --- | --- |
| `GET /orders/{orderId}` | Có đơn hàng | `200 OK` và JSON đơn hàng |
| `GET /orders/{orderId}` | Không tìm thấy hàng | `404 Not Found` |
| `GET /customers/{customerId}/events?day=...` | Có sự kiện | `200 OK` và JSON array |
| `GET /customers/{customerId}/events?day=...` | Không có sự kiện | `200 OK` và `[]` |
| Bất kỳ request nào | Lỗi Cassandra timeout/kết nối | Phản hồi lỗi hạ tầng thích hợp, thường thuộc nhóm 5xx; không trá hình thành 404 hoặc 200 [] |

Ví dụ controller rút gọn:

~~~java
@RestController
public class OrderController {
    private final OrderQueryService orderService;

    public OrderController(OrderQueryService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    public ResponseEntity<OrderResponse> getOrder(@PathVariable UUID id) {
        return orderService.findById(id)
            .map(row -> ResponseEntity.ok(
                new OrderResponse(row.getOrderId(), row.getState())
            ))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

`OrderResponse` là DTO do ứng dụng định nghĩa. Đoạn code yêu cầu import các annotation/controller class của Spring Web, `UUID`, `ResponseEntity`. Chuyển entity sang DTO giúp API kiểm soát dữ liệu trả về, thay vì vô tình lộ mọi cột được lưu.

Đối với endpoint danh sách:

~~~java
@GetMapping("/customers/{id}/events")
public List<EventResponse> getEvents(
        @PathVariable UUID id,
        @RequestParam LocalDate day) {
    return eventService.recentEvents(id, day).stream()
        .map(this::toResponse)
        .toList();
}
~~~

Đây là method minh họa trong một controller có `eventService` và hàm chuyển `toResponse` phù hợp. Khi đầu vào không có hàng, phương thức trả **`[]`** chứ không ném lỗi. Với API lớn, có thể trả cấu trúc gồm `items` và `nextPageToken`; khi không có item thì `items: []`, việc có token tiếp theo phụ thuộc kết quả paging thực tế.

**Lưu ý:** chính sách **404/200** là quyết định của API, không phải quy tắc do Cassandra áp đặt. Nếu yêu cầu quyền truy cập, ẩn thông tin tài nguyên hoặc trạng thái nghiệp vụ đặc biệt, API có thể có quy ước khác; cần mô tả rõ và nhất quán.

## 9. Optional và List không thay thế cơ chế phân trang

### 9.1. Vì sao cần giới hạn truy vấn?

Giả sử một khách hàng phát sinh hàng triệu sự kiện. Repository đọc danh sách **không giới hạn** có thể tăng:

- Số lượng row phải truyền qua mạng.
- Bộ nhớ và CPU dùng để giải mã entity/convert dữ liệu.
- Độ trễ endpoint và rủi ro timeout.
- Số lượng tombstone cần xử lý nếu dữ liệu có TTL/xóa nhiều.

`List<T>` là **kiểu chứa kết quả trong bộ nhớ**, không phải cơ chế truy vấn tăng dần. Câu `LIMIT 20` trong ví dụ bảo vệ một lượt đọc, nhưng nếu muốn lấy **trang kế tiếp** thì cần một cơ chế paging thực sự.

### 9.2. Cassandra paging theo trạng thái, không theo OFFSET

Java driver/Cassandra dùng **paging state** để tiếp tục một truy vấn ở vị trí còn lại. Nó không có ngữ nghĩa giống “bỏ qua 1.000.000 hàng rồi lấy trang tiếp” bằng `OFFSET`. Với Spring Data Cassandra, tùy phiên bản repository có thể hỗ trợ `Slice<T>` và các API phân trang theo trạng thái; nếu phải expose cursor cho client, cần kiểm tra đúng API driver/repository và quyền sử dụng của paging state.

~~~mermaid
flowchart LR
    A[Client yêu cầu danh sách] --> B[CQL có partition key + giới hạn]
    B --> C[Trang hiện tại: items]
    C --> D{Có paging state tiếp?}
    D -->|Có| E[Trả nextPageToken theo quy ước API]
    E --> F[Client gửi yêu cầu trang tiếp]
    F --> B
    D -->|Không| G[Kết thúc: không còn trang]
~~~

**Tránh nhầm lẫn:**

1. **Danh sách rỗng** không tự giải thích vì sao có hoặc không có trang kế; cần xem metadata paging theo API đã dùng.
2. **`LIMIT 20`** giới hạn tổng số row của *một truy vấn*, không tự phát sinh trang thứ hai.
3. **Paging state** phải gắn với cùng câu truy vấn và tham số tương ứng; không dùng token của khách hàng/ngày này cho khách hàng/ngày khác.
4. Tập dữ liệu **có thể thay đổi giữa hai lần đọc**. Paging không tự cung cấp snapshot bất biến khi có ghi/xóa đồng thời.
5. `Page<T>` có tổng số trang/tổng số phần tử thường đòi hỏi đếm dữ liệu; trên Cassandra, đếm một tập lớn có thể rất đắt. Nếu chỉ cần “còn trang tiếp không”, cân nhắc `Slice<T>` hoặc API tiếp tục bằng cursor khi được hỗ trợ.

Nếu bài toán cần tìm trang thứ N ngẫu nhiên và đếm chính xác tổng số kết quả dưới tải lớn, hãy xem lại yêu cầu sản phẩm và mô hình dữ liệu thay vì ép Cassandra hoạt động như truy vấn quan hệ có `OFFSET`.

## 10. Dễ nhầm nhất: kiểu trả về một hàng, nhiều hàng, số lượng và tồn tại

| Nhu cầu | Hợp đồng gợi ý | Ghi chú |
| --- | --- | --- |
| Tìm theo **toàn bộ primary key** | `Optional<T> findById(ID)` | Có thể rỗng; đúng đường truy cập khóa |
| Lấy nhiều hàng theo partition key | `List<T>` hoặc dạng collection phù hợp | Có thể rỗng; cần giới hạn/paging |
| Kiểm tra tồn tại theo ID | `boolean existsById(ID)` | Không thay thế `findById` khi cần chính dữ liệu |
| Đọc nhiều ID cùng lúc | `Iterable<T> findAllById(ids)` theo API repository | ID không tồn tại có thể bị bỏ qua trong collection, không tương ứng vị trí đầu vào |
| Trả một entity thẳng `T` từ query đơn | Có thể dùng theo hợp đồng/phiên bản | Xử lý `null`/quy tắc nullability và trường hợp nhiều hàng; thường ưu tiên `Optional<T>` |
| Truy vấn theo thuộc tính không nằm trong khóa | Không mặc định có API hiệu quả | Cần bảng/index/đường truy cập phù hợp |
| Đọc tập lớn theo trang | `Slice<T>`/cursor theo khả năng phiên bản | Không lấy tất cả rồi cắt list trong Java |
| Đếm toàn bộ bảng lớn | Không dùng `count()` bừa bãi | Trên Cassandra, truy vấn đếm/quét có thể rất tốn kém |

**Một truy vấn trả tối đa một hàng không phải lúc nào cũng có nghĩa truy vấn đã đúng.** Ví dụ lấy `List` rồi gọi `get(0)` sau một truy vấn quét không có partition key không biến nó thành lookup an toàn. Nếu phương thức kỳ vọng đúng một hàng nhưng truy vấn thực tế có thể trả nhiều hàng, cần thiết kế lại điều kiện, thứ tự và ranh giới kết quả; các API chọn một kết quả có thể báo lỗi khi kích thước kết quả không đáp ứng hợp đồng.

Với method derived query kiểu `findBy...`, Spring Data có thể tạo CQL dựa trên property của entity, nhưng **không bảo đảm CQL sinh ra sẽ được Cassandra chấp nhận hoặc chạy hiệu quả** cho mọi tên field. Cần xác minh partition key/clustering/index và câu CQL thực tế.

## 11. Consistency và ý nghĩa của “không tìm thấy”

Trong một hệ phân tán, “truy vấn thành công nhưng không thấy hàng” phụ thuộc **thời điểm đọc, trạng thái replica, consistency level và các mutation đã được áp dụng**. Hãy phân biệt:

- **Không có row trong kết quả đọc**: repository trả empty theo hợp đồng.
- **Đọc thất bại vì không đủ replica hoặc timeout**: ngoại lệ, chưa có kết quả hợp lệ để kết luận vắng mặt.
- **Dữ liệu vừa mới được ghi ở consistency thấp**: một lần đọc sau đó có thể chưa nhìn thấy mọi cập nhật theo mong muốn của nghiệp vụ.
- **Dữ liệu bị xóa hoặc hết TTL**: hàng có thể không còn xuất hiện; muốn biết nguyên nhân cần audit/trạng thái khác.

Ví dụ keyspace có **replication factor 3** trong một datacenter. Với `LOCAL_QUORUM`, thao tác đọc/ghi tương ứng cần số replica phản hồi theo quy tắc quorum (thường là **2 trong RF=3**). Điều này thay đổi bảo đảm và chi phí của yêu cầu, nhưng không nên mô tả mọi đọc luôn tuyến tính hoặc không bao giờ có trạng thái tạm thời. Chọn consistency cho **nghiệp vụ** rồi kiểm thử dưới tải và khi replica gặp lỗi.

**Đặc biệt đối với API:** không nên tự động retry vô hạn chỉ để biến `Optional.empty()` thành kết quả có dữ liệu; cũng không được biến `ReadTimeout` thành empty. Nếu yêu cầu phải thấy dữ liệu vừa ghi, hãy làm rõ hợp đồng read-after-write, consistency level và quy trình xác nhận ghi.

## 12. Kiểm thử đầy đủ các trạng thái trả về

Nên kiểm tra riêng **hợp đồng Java**, **mapping/CQL** và **hành vi khi Cassandra gặp lỗi**. Mock repository giúp kiểm tra logic service nhưng không chứng minh truy vấn được phép trên Cassandra.

### 12.1. Unit test service với Optional

~~~java
@Test
void missingOrderReturnsEmpty() {
    UUID id = UUID.randomUUID();
    when(orderRepository.findById(id)).thenReturn(Optional.empty());

    Optional<OrderRow> result = orderService.findById(id);

    assertTrue(result.isEmpty());
}

@Test
void existingOrderIsReturned() {
    UUID id = UUID.randomUUID();
    OrderRow row = new OrderRow(id, UUID.randomUUID(), "CREATED", null);
    when(orderRepository.findById(id)).thenReturn(Optional.of(row));

    Optional<OrderRow> result = orderService.findById(id);

    assertTrue(result.isPresent());
    assertEquals("CREATED", result.orElseThrow().getState());
    assertNull(result.orElseThrow().getNote());
}
~~~

Đây là ví dụ dùng JUnit 5 và Mockito; `orderService`/`orderRepository` cần được tạo hoặc inject phù hợp trong test. Từ `isEmpty()` trên `Optional` cần Java 11 trở lên. Ví dụ kiểm tra rõ **hàng có trường `note = null`** khác với **không có hàng**.

### 12.2. Test danh sách rỗng

~~~java
@Test
void noEventsReturnsEmptyList() {
    UUID customerId = UUID.randomUUID();
    LocalDate day = LocalDate.of(2026, 11, 25);

    when(eventRepository.findRecentEvents(customerId, day))
        .thenReturn(List.of());

    List<CustomerEventRow> events =
        eventService.recentEvents(customerId, day);

    assertNotNull(events);
    assertTrue(events.isEmpty());
}
~~~

Test dùng mock để xác nhận **service không biến danh sách rỗng thành `null` hoặc ngoại lệ**. Với controller, thêm test HTTP: GET một ID không tồn tại trả 404; GET danh sách hợp lệ không có row trả 200 và JSON `[]`.

### 12.3. Test lỗi không được biến thành không tồn tại

~~~java
@Test
void databaseFailureMustNotLookLikeMissingOrder() {
    UUID id = UUID.randomUUID();
    when(orderRepository.findById(id))
        .thenThrow(new IllegalStateException("Simulated database failure"));

    assertThrows(IllegalStateException.class,
        () -> orderService.findById(id));
}
~~~

Đây là **lỗi mô phỏng ở tầng service**, không phải lớp exception Cassandra thật. Nó kiểm tra điều quan trọng: service không bắt mọi exception rồi trả `Optional.empty()`. Ở test tích hợp/fault injection, kiểm tra cách ứng dụng chuyển lỗi driver/framework thành phản hồi lỗi hạ tầng phù hợp và không trả 404 giả.

### 12.4. Test tích hợp với Cassandra

Trên cluster/keyspace thử nghiệm:

1. Tạo hai bảng `orders_by_id` và `events_by_customer_day` với schema tương ứng.
2. Với một `orderId` chưa từng ghi, gọi `findById`: kỳ vọng `Optional.empty()`.
3. Ghi một đơn hàng có `note = null`, đọc lại: `Optional` có entity, `note` vẫn vắng mặt.
4. Tạo hai khách hàng có sự kiện trong các ngày khác nhau. Truy vấn một cặp `customer_id + event_day` không có dữ liệu: nhận danh sách rỗng.
5. Ghi 25 sự kiện trong cùng một partition, truy vấn `LIMIT 20`: nhận **không quá 20 hàng** và thứ tự phù hợp clustering; đừng giả định query đã trả tất cả sự kiện.
6. Kiểm tra hai sự kiện có cùng `occurred_at` nhưng `event_id` khác nhau vẫn tồn tại độc lập.
7. Thực hiện xóa/TTL trên dữ liệu thử nghiệm, quan sát sự thay đổi của kết quả đọc; không suy ra tombstone hiển thị trực tiếp thành entity.
8. Thử giới hạn/failure mode của cluster theo quyền kiểm soát môi trường: timeout hoặc không đủ replica phải là lỗi riêng, không thành kết quả rỗng.
9. Nếu có paging, kiểm tra cursor chỉ dùng lại cho đúng tham số truy vấn, không áp dụng nhầm giữa hai khách hàng.

Các test tích hợp kiểm tra **quy tắc CQL, mapping, partition key và kết quả thực tế**; unit test chỉ kiểm tra hợp đồng service. Chọn phiên bản Spring Boot/Spring Data Cassandra/Java driver tương thích, đặt đúng contact points/local datacenter và không chạy fault injection trên cluster production.

## 13. Các lỗi thường gặp và cách sửa

| Cách làm sai | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Gọi `findById(id).get()` mà không kiểm tra | `NoSuchElementException` khi không có row | Dùng `map`, `orElseThrow` hoặc xử lý empty rõ ràng |
| Dùng `null` để biểu thị repository không có danh sách | Caller dễ gặp NPE hoặc phải kiểm tra dư thừa | Trả collection rỗng nhất quán |
| Trả `Optional<List<T>>` cho mọi truy vấn danh sách | Hai trạng thái rỗng chồng nhau, phức tạp hợp đồng | Ưu tiên `List<T>` hoặc cursor result rõ ràng |
| Coi một cột `null` là hàng không tồn tại | Trả 404 sai với dữ liệu có thật | Phân biệt row absence và field absence |
| Bắt mọi exception rồi trả `Optional.empty()` | Che giấu lỗi DB, tạo 404 giả | Để lỗi đi qua handler/chính sách retry phù hợp |
| `existsById` rồi `findById` cho mọi request | Thêm lượt đọc, vẫn có race condition | Dùng `findById` trực tiếp khi cần entity |
| Truy vấn danh sách không `LIMIT`/paging | Nguy cơ đọc quá nhiều, tăng bộ nhớ và độ trễ | Thiết kế truy vấn giới hạn, dùng paging state |
| Derived query trên cột bất kỳ | CQL có thể bị từ chối hoặc tốn tài nguyên | Thiết kế bảng/index theo truy vấn |
| Dùng `Page` và đếm toàn bảng như RDBMS | Chi phí đếm lớn, kém hiệu năng | Ưu tiên `Slice`/cursor theo khả năng |
| Coi empty là bằng chứng dữ liệu chưa từng tồn tại | Sai trong hệ có xóa, TTL, replication | Bổ sung audit/status và hiểu consistency |
| `LIMIT 20` rồi tưởng đã có trang 2 | Mất khả năng tiếp tục kết quả | Dùng API paging phù hợp thay vì tự tăng OFFSET |

## 14. Bài thực hành tổng hợp

**Đề bài:** xây dựng API đọc một đơn hàng và liệt kê tối đa 20 sự kiện mới nhất của khách hàng theo ngày. API phải phân biệt rõ **không tồn tại**, **danh sách rỗng**, **cột null** và **lỗi database**.

Các bước:

1. Tạo bảng `orders_by_id` và `events_by_customer_day` trên keyspace thử nghiệm phù hợp topology.
2. Ánh xạ `OrderRow` và `CustomerEventRow`; cấu hình repository cho hai bảng.
3. Viết service `findById(UUID)` trả `Optional<OrderRow>` và `recentEvents(UUID, LocalDate)` trả `List<CustomerEventRow>`.
4. Áp dụng `@Query` đầy đủ partition key cho danh sách, có `LIMIT 20` và thứ tự lấy từ clustering.
5. Tạo endpoint GET một đơn hàng: có → 200; không thấy → 404. Tạo endpoint GET danh sách: có → 200 array; không có → 200 `[]`.
6. Ghi dữ liệu trong đó có đơn hàng có `note = null`, một khách hàng chưa có sự kiện, một khách hàng có nhiều hơn 20 sự kiện.
7. Test các trạng thái 0/1/nhiều hàng, cột null, xóa/TTL và lỗi hạ tầng giả lập.
8. Giải thích vì sao muốn xem các trang tiếp theo cần **paging state/cursor** và không thể lấy ngẫu nhiên trang theo `OFFSET`.
9. Ghi rõ consistency level, ý nghĩa của lần đọc rỗng và chính sách timeout/retry.

**Tiêu chí đạt:** repository và service biểu diễn đúng **một hàng tùy chọn** bằng `Optional<T>`, **nhiều hàng** bằng `List<T>` hoặc kiểu collection tương đương, và **lỗi truy cập** bằng cơ chế ngoại lệ có phân loại. Không có thao tác quét dữ liệu không giới hạn hay biến lỗi thành dữ liệu rỗng.

## 15. Câu hỏi tự kiểm tra

1. Tại sao `findById(...)` thích hợp với `Optional<T>` hơn là trả một entity giả?
2. Sự khác nhau giữa `Optional.empty()` và `entity.getNote() == null` là gì?
3. Vì sao không nên trả `Optional<List<T>>` cho truy vấn danh sách bình thường?
4. Một phương thức truy vấn danh sách không tìm thấy row nên trả gì?
5. Lỗi `ReadTimeout` có được chuyển thành 404 hay `[]` không? Vì sao?
6. Tại sao `existsById` rồi `findById` liên tiếp có thể tốn thêm chi phí và vẫn không loại được race condition?
7. `findAllById(ids)` có bảo đảm mỗi ID đầu vào sẽ xuất hiện dưới dạng một phần tử kết quả không?
8. Vì sao phương thức repository trả `List<T>` không có nghĩa CQL được phép lọc tùy ý?
9. Trong bảng `events_by_customer_day`, những cột nào cần xuất hiện trong điều kiện truy vấn để định vị partition?
10. `LIMIT 20` có nghĩa là Spring Data tự lưu lại 20 hàng tiếp theo để trả trang 2 không?
11. Vì sao `Page<T>` với total count có thể không phù hợp với Cassandra ở quy mô lớn?
12. Nếu một đơn hàng vừa bị xóa/hết TTL, `Optional.empty()` có tự cho biết lý do không?
13. Khi consistency level thay đổi, ý nghĩa của một lần đọc không có row cần được hiểu như thế nào?
14. Để kiểm chứng bài học, vì sao cần cả unit test service và integration test với Cassandra?

**Ghi nhớ:** **`Optional<T>` cho một hàng có thể không tồn tại; `List<T>` cho nhiều hàng có thể rỗng; exception cho truy vấn không hoàn tất hợp lệ.** Những lựa chọn này làm rõ hợp đồng Java/API nhưng không thay đổi bản chất Cassandra: truy vấn phải bám theo partition key, có giới hạn/paging hợp lý và được diễn giải trong điều kiện consistency, replication, TTL và lỗi hệ phân tán.
