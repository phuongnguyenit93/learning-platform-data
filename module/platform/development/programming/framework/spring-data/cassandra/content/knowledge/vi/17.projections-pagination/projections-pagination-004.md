# Fetch size và lượng dữ liệu được lấy trong một lần

Khi một phương thức **Spring Data Cassandra** trả về hàng nghìn bản ghi, Java driver không nhất thiết tải tất cả dữ liệu trong một phản hồi mạng. Nó có thể chia kết quả thành **nhiều trang (pages)** rồi tải dần khi ứng dụng duyệt. Tham số thường được gọi là **fetch size** trong tài liệu/công cụ cũ, hoặc **page size** trong Apache Cassandra Java driver 4.x, quyết định **số hàng mục tiêu của mỗi lượt lấy dữ liệu**.

Điểm dễ nhầm nhất: **`pageSize(100)` không có nghĩa câu truy vấn chỉ trả 100 hàng.** Nếu truy vấn có 50.000 hàng và ứng dụng duyệt tới cuối, driver vẫn có thể tải đủ 50.000 hàng qua nhiều lượt mạng. Muốn giới hạn tổng số hàng, cần ràng buộc **partition key**, **clustering columns**, `LIMIT` và/hoặc dừng duyệt đúng lúc. Để chỉ lấy một trang cho HTTP API, dùng **`Slice` + `CassandraPageRequest`**, không materialize toàn bộ kết quả rồi cắt danh sách trong Java.

Bài học thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_CASSANDRA**, nơi ứng dụng làm việc với entity mapping, repository, `CassandraTemplate` và truy vấn CQL trên hệ thống Cassandra phân tán. Các ví dụ dựa trên **Java driver 4.19** và **Spring Data Cassandra 4.5**, đồng thời giải thích cách gọi API trong các phiên bản trước.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **fetch size/page size** kiểm soát điều gì trong một lượt giao tiếp client–Cassandra.
2. Phân biệt **`LIMIT`, page size, số row của một `Slice`, tổng số row và kích thước byte** của response.
3. Đặt page size ở cấp **Java driver configuration**, từng **`Statement`**, hoặc qua **`QueryOptions`** của Spring Data Cassandra.
4. Nhận biết vì sao vòng lặp trên `ResultSet` hoặc gọi `all()` có thể lấy **nhiều trang**, dù page size nhỏ.
5. Phân trang ở tầng repository/`CassandraTemplate` với `CassandraPageRequest` và paging state.
6. Hiểu **`AsyncResultSet.currentPage()`** khác với kết quả đồng bộ thế nào.
7. Giảm dữ liệu bằng **projection** (chỉ chọn cột cần thiết), `LIMIT` và truy vấn đúng partition.
8. Chọn page size từ kết quả đo latency, network, row width và heap, không theo một con số “chuẩn” cố định.

## 2. Bốn đại lượng hay bị nhầm

| Khái niệm | Điều khiển | Không bảo đảm |
|---|---|---|
| **CQL `LIMIT 20`** | Số hàng **tối đa** được trả bởi một statement | Truy vấn chỉ đọc 1 partition; 20 hàng mới nhất toàn cluster; chỉ tốn 1 lượt mạng |
| **Driver page size = 20** | Mục tiêu số hàng trong **một trang kết quả mạng** | Toàn bộ truy vấn chỉ trả 20 hàng; mỗi trang đúng 20 hàng |
| **`Slice<T>` size = 20** | Lượng dữ liệu một lần API Spring Data trả về, kèm khả năng đi tiếp | Tổng số trang hoặc tổng số hàng toàn query |
| **Danh sách Java trả về** | Những object ứng dụng đã chọn giữ trong RAM | Driver/Cassandra chỉ đọc từng ấy hàng; không có prefetch |

Một phân biệt nữa: `pageSize(20)` nói về **số row**, không phải **20 KiB/20 MB dữ liệu**. Nếu mỗi row có một cột `payload` rất lớn, một trang 20 row có thể nặng hơn nhiều so với một trang 200 row chỉ chứa ba cột nhỏ.

### 2.1. Ví dụ tư duy

Giả sử truy vấn hợp lệ có **350 hàng** trong một partition.

- Với `pageSize = 50`, về mặt trực giác kết quả được chia thành **khoảng bảy trang**. Đây chỉ là ước lượng; server có thể trả số hàng khác mục tiêu.
- Nếu Java duyệt **toàn bộ** `ResultSet`, ứng dụng sẽ xử lý **350 hàng** chứ không dừng ở 50.
- Nếu CQL có `LIMIT 20`, ứng dụng nhận **tối đa 20 hàng** cho statement đó, dù page size là 50.
- Nếu Spring Data trả một `Slice` với kích thước 20, caller lấy một phần kết quả và có thể yêu cầu **slice tiếp theo** bằng paging state, thay vì đếm toàn bộ.

**Kết luận:** page size điều khiển cách *chuyển dữ liệu*, `LIMIT` và partition restriction điều khiển phạm vi *truy vấn*, còn code tiêu thụ kết quả quyết định tổng lượng dữ liệu thực sự được lấy về.

### 2.2. Sơ đồ cách phân trang

```mermaid
sequenceDiagram
    participant App as Java / Spring Data
    participant Driver as Cassandra Java driver
    participant Node as Cassandra node
    App->>Driver: SELECT theo partition key (pageSize=3)
    Driver->>Node: Request trang đầu
    Node-->>Driver: Row 1..3 + paging state
    Driver-->>App: Trang đầu
    Note over App: Dừng ở đây nếu chỉ cần 3 row
    App->>Driver: Tiếp tục duyệt / next slice
    Driver->>Node: Request tiếp + paging state
    Node-->>Driver: Row 4..6 + paging state
    Driver-->>App: Trang tiếp theo
    App->>Driver: Tiếp tục khi còn dữ liệu
    Driver->>Node: Request sau cùng
    Node-->>Driver: Row còn lại; hết trang
```

Sơ đồ biểu diễn các lượt xử lý logic. Driver có thể chủ động lấy trang kế để tối ưu trải nghiệm khi code đồng bộ duyệt kết quả; không nên suy ra mỗi lệnh gọi Java `next()` luôn tương ứng đúng một request mạng.

## 3. Chuẩn bị bảng mẫu để quan sát

Dùng bảng sự kiện theo **thiết bị và ngày**, vì truy vấn người dùng đã biết hai giá trị này. `event_time` được sắp xếp giảm dần để lấy sự kiện mới trước.

### 3.1. Schema CQL

```sql
-- Lab một node; không dùng cấu hình replication này cho production.
CREATE KEYSPACE IF NOT EXISTS sdc_paging_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS sdc_paging_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
        (device_id, event_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

- **Partition key**: `(device_id, event_day)`.
- **Clustering columns**: `event_time` rồi `event_id`; chúng xác định thứ tự trong partition.
- **Regular columns**: `event_type`, `payload`.
- `event_day` là CQL `date`; `event_time` là CQL `timestamp`.

Thiết kế này phù hợp việc duyệt sự kiện **trong một ngày của một thiết bị**. Nó không tự tối ưu yêu cầu “tất cả sự kiện trên toàn nền tảng” hoặc “lọc sự kiện theo type trên mọi thiết bị”.

### 3.2. Nạp dữ liệu thử

```sql
INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:08:00Z',
    00000000-0000-0000-0000-000000000008,
    'OPEN', 'small payload 8'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:07:00Z',
    00000000-0000-0000-0000-000000000007,
    'CLOSE', 'small payload 7'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:06:00Z',
    00000000-0000-0000-0000-000000000006,
    'OPEN', 'small payload 6'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:05:00Z',
    00000000-0000-0000-0000-000000000005,
    'ALERT', 'small payload 5'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:04:00Z',
    00000000-0000-0000-0000-000000000004,
    'OPEN', 'small payload 4'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:03:00Z',
    00000000-0000-0000-0000-000000000003,
    'CLOSE', 'small payload 3'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:02:00Z',
    00000000-0000-0000-0000-000000000002,
    'OPEN', 'small payload 2'
);

INSERT INTO sdc_paging_lab.events_by_device_day
(device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-25', '2026-11-25T08:01:00Z',
    00000000-0000-0000-0000-000000000001,
    'ALERT', 'small payload 1'
);
```

Tập dữ liệu gồm **tám row trong cùng một partition**. Một phần mềm khác có thể tiếp tục ghi/xóa trong lúc thực hành, nên mọi kết quả số hàng dưới đây đều giả định không có mutation xen giữa.

### 3.3. CQL mẫu theo đúng partition

```sql
SELECT device_id, event_day, event_time, event_id, event_type, payload
FROM sdc_paging_lab.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-25';
```

Truy vấn trả **tám hàng**, mới nhất trước. **Không có `LIMIT`**: nếu dữ liệu trong partition tăng lên 80.000 hàng và client duyệt hết, nó có thể xử lý 80.000 hàng mặc cho page size chỉ 50 hay 100.

Câu chỉ lấy ba sự kiện mới nhất:

```sql
SELECT device_id, event_day, event_time, event_id, event_type
FROM sdc_paging_lab.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-25'
LIMIT 3;
```

Lúc này **tổng số hàng trả về không vượt ba**. Đây là ràng buộc CQL, không phải cùng ý nghĩa với `pageSize(3)`.

## 4. Cấu hình page size trong Java driver 4.x

### 4.1. Cấu hình mặc định của driver

Java driver 4.x sử dụng tùy chọn:

```hocon
datastax-java-driver {
  basic.request.page-size = 5000
}
```

Theo tài liệu Java driver 4.19, giá trị cấu hình **mặc định là 5.000 hàng**. Đây là giá trị mặc định của driver, **không phải lời khuyên bắt mọi truy vấn phải dùng 5.000**. Một ứng dụng với row rất rộng hoặc request latency nhạy cảm có thể cần page size nhỏ hơn nhiều.

Khi dùng Spring Boot, nơi chứa cấu hình HOCON và quy tắc ưu tiên phụ thuộc cấu hình driver do Boot nạp (ví dụ `spring.cassandra.config` trong phiên bản hỗ trợ). Kiểm tra runtime config của `CqlSession` thay vì giả định sửa một tệp `application.conf` bất kỳ sẽ tác động đến mọi session.

### 4.2. Đặt page size cho từng Statement

Trong Java driver 4.x, `setPageSize(int)` đặt mục tiêu số hàng mỗi trang cho **statement đó**:

```java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public class EventReader {

    private final CqlSession session;
    private final PreparedStatement findByDeviceAndDay;

    public EventReader(CqlSession session) {
        this.session = session;
        this.findByDeviceAndDay = session.prepare("""
            SELECT device_id, event_day, event_time, event_id,
                   event_type, payload
            FROM sdc_paging_lab.events_by_device_day
            WHERE device_id = ? AND event_day = ?
            """);
    }

    public ResultSet query(UUID deviceId, LocalDate day) {
        BoundStatement statement = findByDeviceAndDay.bind(deviceId, day)
            .setPageSize(3);

        return session.execute(statement);
    }
}
```

**Chú ý tính bất biến:** `BoundStatement` của driver 4.x là immutable; `setPageSize(3)` **trả về một statement mới**. Đừng gọi setter rồi bỏ qua object trả về:

```java
BoundStatement statement = findByDeviceAndDay.bind(deviceId, day);

// Sai: bỏ qua BoundStatement mới.
statement.setPageSize(3);
session.execute(statement);
```

Sửa bằng `statement = statement.setPageSize(3)` hoặc chain như ví dụ đầy đủ ở trên.

### 4.3. Page size chỉ là một gợi ý

Không nên viết logic dạng “nếu cấu hình 3 thì chắc chắn trang đầu có 3 row” bởi Cassandra có thể trả **ít hơn hoặc nhiều hơn** số hàng mục tiêu trong một frame. Các trường hợp dữ liệu nhiều tombstone, row/cell lớn, giới hạn tài nguyên và cách server thực hiện query đều có thể ảnh hưởng kích thước trang.

Vì vậy:

- Page size là **tuning hint**, không phải một hợp đồng về số row chính xác.
- Nếu API phải trả tối đa N row, sử dụng ràng buộc truy vấn/logic API ở tầng phù hợp.
- **Không lấy page size làm byte cap**; số byte phụ thuộc kiểu cột, row width và số cột được chọn.
- Không suy ra số network request chính xác chỉ bằng phép chia `totalRows / pageSize`.

### 4.4. Tên gọi fetchSize còn tồn tại không?

Ở Java driver 4.x, API chuẩn là:

```java
statement = statement.setPageSize(100);
```

Các tên `setFetchSize(int)`/`getFetchSize()` còn có thể xuất hiện như **alias cũ, đã deprecated**, để hỗ trợ chuyển từ driver 3.x. Trong code driver 4.x mới, dùng `setPageSize`. Trong Spring Data Cassandra 4.5, `QueryOptions.builder().fetchSize(int)` cũng **deprecated**; dùng `pageSize(int)` thay thế.

Điều quan trọng là **ý nghĩa không đổi**: số hàng được lấy theo một trang/chunk, không phải `SELECT LIMIT`.

## 5. Kết quả đồng bộ: for-each có thể tải tất cả các trang

Đây là nguồn gốc phổ biến của lỗi “đã đặt fetch size thấp nhưng ứng dụng vẫn tốn nhiều RAM và thời gian”.

### 5.1. Vòng lặp đồng bộ bình thường

```java
ResultSet resultSet = eventReader.query(
    UUID.fromString("11111111-1111-1111-1111-111111111111"),
    LocalDate.of(2026, 11, 25)
);

int total = 0;
for (Row row : resultSet) {
    System.out.println(row.getString("event_type"));
    total++;
}
System.out.println("Processed: " + total);
```

Với tám row trong lab và `pageSize(3)`, vòng lặp **duyệt đến hết tám row**. Driver tự xử lý việc lấy các trang tiếp khi cần; ứng dụng không phải tự gọi `fetchNextPage()` trong API đồng bộ.

Theo tài liệu Java driver, việc chuyển từ trang này sang trang tiếp có thể được driver thực hiện trong nền hoặc khi iterator tiến tới cuối trang. Vì vậy không nên gắn cứng số round trip hoặc giả định không có prefetch.

### 5.2. all() có thể materialize toàn bộ kết quả

```java
ResultSet resultSet = eventReader.query(deviceId, day);
List<Row> allRows = resultSet.all();
```

`ResultSet.all()` tiêu thụ **toàn bộ các row còn lại** và đưa chúng vào một `List<Row>`. Nếu query trả hàng triệu row, thao tác này có thể gây áp lực heap/GC hoặc `OutOfMemoryError`.

Trong `CassandraTemplate` và repository, các API trả `List<T>` như `select(Query, Entity.class)` hoặc `findAll()` cũng có thể materialize lượng dữ liệu lớn. Việc driver chia trang ở network layer **không đảm bảo list cuối cùng nhỏ**.

### 5.3. Chỉ xử lý số row hiện có mà không chủ động lấy trang sau

`ResultSet.getAvailableWithoutFetching()` cho biết số row đã sẵn sàng để tiêu thụ **mà không phải chờ lấy thêm trang**:

```java
ResultSet resultSet = eventReader.query(deviceId, day);

int ready = resultSet.getAvailableWithoutFetching();
for (int i = 0; i < ready; i++) {
    Row row = resultSet.one();
    if (row != null) {
        System.out.println(row.getString("event_type"));
    }
}
```

Đây là cách minh họa sự khác nhau giữa **số row hiện sẵn** và **toàn bộ kết quả**. Nó không phải một API cursor HTTP hoàn chỉnh, cũng không cam kết chính xác bao nhiêu request mạng đã được driver gửi trong quá trình prefetch.

Nếu yêu cầu sản phẩm là “một trang, có thể đi tiếp theo lần gọi khác”, `CassandraPageRequest` hoặc cơ chế paging state của driver thích hợp hơn cách tự cắt một iterator.

## 6. Kết quả bất đồng bộ: mỗi lần nhận một page rõ ràng

Java driver 4.x trả **`AsyncResultSet`** từ `session.executeAsync(...)`. Khác với `ResultSet` đồng bộ, `AsyncResultSet.currentPage()` chỉ lộ **những row của trang hiện tại**; muốn trang kế, ứng dụng phải gọi **`fetchNextPage()`**.

Ví dụ code minh họa:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public class AsyncEventReader {

    private final CqlSession session;

    public AsyncEventReader(CqlSession session) {
        this.session = session;
    }

    public CompletionStage<Void> readAll(BoundStatement statement) {
        return session.executeAsync(statement.setPageSize(3))
                .thenCompose(this::consumePages);
    }

    private CompletionStage<Void> consumePages(AsyncResultSet page) {
        for (Row row : page.currentPage()) {
            // Thực tế chỉ nên làm xử lý ngắn, không blocking ở đây.
            String type = row.getString("event_type");
            System.out.println(type);
        }

        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(null);
        }

        return page.fetchNextPage().thenCompose(this::consumePages);
    }
}
```

Điểm cần quan sát:

- `currentPage()` không tự lặp qua tất cả trang.
- `hasMorePages()` cho biết có khả năng lấy tiếp.
- `fetchNextPage()` trả một `CompletionStage<AsyncResultSet>`, cho phép chaining.
- Code ví dụ vẫn **cố ý đọc hết** vì gọi đệ quy tới khi không còn trang; nếu chỉ cần một trang, dừng trước `fetchNextPage()`.
- Callback có thể chạy trên **I/O threads của driver**: không thực hiện JDBC blocking, gọi API HTTP đồng bộ, ngủ luồng hoặc xử lý CPU nặng trong callback. Chuyển xử lý nặng sang executor thích hợp và thiết kế backpressure.

Nếu hệ thống dùng Reactor/Reactive Cassandra, hãy kiểm tra cơ chế request/backpressure của abstraction tương ứng; không suy ra reactive stream luôn chỉ đọc đúng từng N row theo nhu cầu của HTTP client.

## 7. Spring Data Cassandra: pageSize trong QueryOptions

`CassandraTemplate`/`CassandraOperations` cho phép cấu hình query thông qua `QueryOptions`.

### 7.1. Cấu hình theo từng truy vấn

Giả sử class entity `DeviceEvent` đã được ánh xạ đúng với bảng `events_by_device_day`. Có thể tạo `Query` như sau:

```java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.cql.QueryOptions;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public class EventTemplateReader {

    private final CassandraTemplate template;

    public EventTemplateReader(CassandraTemplate template) {
        this.template = template;
    }

    public java.util.List<DeviceEvent> list(
        UUID deviceId, LocalDate day
    ) {
        QueryOptions options = QueryOptions.builder()
            .pageSize(3)
            .build();

        Query query = Query.query(
                Criteria.where("device_id").is(deviceId),
                Criteria.where("event_day").is(day)
            )
            .queryOptions(options);

        return template.select(query, DeviceEvent.class);
    }
}
```

**Cảnh báo trọng tâm:** `.pageSize(3)` ở đây chỉ điều chỉnh **mỗi chunk** mà driver nhận. `template.select(query, DeviceEvent.class)` trả `List<DeviceEvent>`, nên có thể **tiêu thụ nhiều trang để tạo list**. Nếu partition có 20.000 row, việc set page size bằng 3 **không khiến list chỉ có ba entity**.

Nếu muốn tổng số entity trả về tối đa ba, dùng:

```java
Query limited = query.limit(3);
java.util.List<DeviceEvent> firstThree =
    template.select(limited, DeviceEvent.class);
```

Ở đây `query` là object `Query` đã tạo ở đoạn code trước và `Query.limit(3)` tạo một `Query` mới (API immutable của Spring Data Cassandra). Câu CQL tương ứng cần có `LIMIT 3`. Nếu muốn lấy một slice có cursor, xem mục 8.

### 7.2. fetchSize(int) đã deprecated

Với **Spring Data Cassandra 4.5**, builder có:

```java
QueryOptions options = QueryOptions.builder()
    .pageSize(100)
    .build();
```

`fetchSize(100)` còn xuất hiện ở những bài viết cũ nhưng đã bị đánh dấu **deprecated** từ Spring Data Cassandra 3.0, và được khuyến nghị thay bằng `pageSize(100)`.

Khi đọc code cũ:

```java
// API cũ; tránh dùng trong code mới.
QueryOptions.builder().fetchSize(100).build();
```

Hãy hiểu đây vẫn là thiết lập **số row mục tiêu trên mỗi trang**.

### 7.3. Đặt QueryOptions trên repository method

Spring Data Cassandra repository query methods hỗ trợ một tham số đặc biệt `QueryOptions`. Ví dụ:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.QueryOptions;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("""
        SELECT device_id, event_day, event_time, event_id,
               event_type, payload
        FROM events_by_device_day
        WHERE device_id = ?0 AND event_day = ?1
        """)
    List<DeviceEvent> findByDeviceAndDay(
        UUID deviceId, LocalDate day, QueryOptions options
    );
}
```

Gọi:

```java
QueryOptions options = QueryOptions.builder()
    .pageSize(50)
    .build();

List<DeviceEvent> events =
    repository.findByDeviceAndDay(deviceId, day, options);
```

**`QueryOptions` là tham số đặc biệt**, không phải bind variable của marker `?2`. Method vẫn chỉ bind `deviceId` vào `?0` và `day` vào `?1`.

Vì return type là `List`, **50 không phải giới hạn tổng số row**. Nếu cần trả về tối đa 50, hãy chọn một query có `LIMIT 50` hoặc một API `Slice`.

### 7.4. Query.pageRequest và QueryOptions có thể chồng nhau

Trong Spring Data Cassandra 4.5, `Query.pageRequest(Pageable)` lấy **page size từ Pageable** và ghi vào query options để phục vụ paging. Nếu bạn vừa gọi `.queryOptions(QueryOptions.builder().pageSize(200).build())` rồi sau đó `.pageRequest(CassandraPageRequest.first(20))`, không nên giả định kích thước mỗi trang vẫn là 200.

**Quy tắc thực hành:** dùng một **nguồn chủ đạo** cho kích thước trang của một query. Với API paging theo `Slice`, dùng `CassandraPageRequest.first(size)` và tiếp tục bằng `nextPageable()`; với thao tác driver query dài chạy theo luồng, có thể dùng page size riêng ở statement.

## 8. Phân trang bằng Slice và CassandraPageRequest

`Slice<T>` giúp ứng dụng lấy một phần kết quả, rồi tiếp tục bằng **paging state**. Nó là lựa chọn thường gặp cho endpoint “Tải thêm” hoặc “Trang tiếp theo”, bởi Cassandra **không có offset paging tùy ý theo kiểu `OFFSET 100000`**.

### 8.1. Entity và composite primary key

Giả sử Java classes ánh xạ `PRIMARY KEY ((device_id, event_day), event_time, event_id)`:

```java
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

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED
    )
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "event_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED
    )
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING
    )
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING
    )
    private UUID eventId;

    public DeviceEventKey() {}

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof DeviceEventKey key)) return false;
        return Objects.equals(deviceId, key.deviceId)
            && Objects.equals(eventDay, key.eventDay)
            && Objects.equals(eventTime, key.eventTime)
            && Objects.equals(eventId, key.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime, eventId);
    }
}
```

Entity:

```java
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

    public DeviceEvent() {}

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey value) { key = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
```

Các class trên giả định ứng dụng đã cấu hình `CqlSession` với keyspace `sdc_paging_lab`. Nếu chỉ định tên bảng trong `@Table` mà session dùng keyspace khác, query sẽ không tìm đúng schema.

### 8.2. Repository trả Slice thay vì List

Trong repository (thay hoặc thêm method cạnh method ở mục 7.3):

```java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.cassandra.repository.Query;

@Query("""
    SELECT device_id, event_day, event_time, event_id,
           event_type, payload
    FROM events_by_device_day
    WHERE device_id = ?0 AND event_day = ?1
    """)
Slice<DeviceEvent> pageByDeviceAndDay(
    UUID deviceId, LocalDate day, Pageable pageable
);
```

Với Cassandra, `Pageable` cần tương thích `CassandraPageRequest` và paging state. `CassandraPageRequest.first(3)` yêu cầu slice đầu tiên có kích thước ba:

```java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<DeviceEvent> first = repository.pageByDeviceAndDay(
    deviceId, day, CassandraPageRequest.first(3)
);

for (DeviceEvent event : first.getContent()) {
    System.out.println(event.getEventType());
}

if (first.hasNext()) {
    Slice<DeviceEvent> second = repository.pageByDeviceAndDay(
        deviceId, day, first.nextPageable()
    );
}
```

Điểm quan trọng:

- `first.getContent()` chỉ là các entity của **slice hiện tại**, không phải cả bảng.
- `first.hasNext()` cho biết có thể lấy slice kế; không cần tính tổng số hàng.
- `first.nextPageable()` mang thông tin paging state cần để tiếp tục.
- Không dùng `PageRequest.of(4, 3)` để nhảy thẳng trang 5. Cassandra paging state là **forward-only**.
- Không dùng paging state của `deviceId/day` này cho `deviceId/day` khác.

### 8.3. CassandraTemplate.slice cũng hỗ trợ paging

Nếu thích `CassandraTemplate` thay vì repository:

```java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.data.domain.Slice;

Query base = Query.query(
    Criteria.where("device_id").is(deviceId),
    Criteria.where("event_day").is(day)
);

Slice<DeviceEvent> first = template.slice(
    base.pageRequest(CassandraPageRequest.first(3)),
    DeviceEvent.class
);

if (first.hasNext()) {
    Slice<DeviceEvent> next = template.slice(
        base.pageRequest(first.nextPageable()),
        DeviceEvent.class
    );
}
```

`Query` của Spring Data Cassandra là immutable khi áp dụng các builder-like methods; biến `base` vẫn có cùng partition restrictions giữa các trang. `pageRequest(...)` tạo query mới có page size/paging state.

Trong một service thật, có thể dùng repository **hoặc** template tùy nhu cầu; không cần gọi cả hai cho cùng một request.

### 8.4. Không nhầm Slice với Page

| Đối tượng | Có tổng số phần tử không? | Hệ quả |
|---|---|---|
| `List<T>` | Không | Có thể chứa toàn bộ tập kết quả được materialize |
| `Slice<T>` | Không cần | Có nội dung của phần hiện tại và `hasNext()` |
| `Page<T>` | Có thông tin tổng số phần tử/trang | Có thể cần `COUNT(*)`, rất đắt trên Cassandra |

Một UI dạng “Load more” chỉ cần biết **còn dữ liệu hay không**. Đòi tổng số trang chỉ để hiển thị “Trang 1/12.345” thường kéo theo thao tác đếm rộng hoặc một read model thống kê riêng.

### 8.5. Bản chất của paging state

Cassandra dùng một **paging state opaque** biểu diễn vị trí tiếp tục truy vấn. Java driver có thể lấy bằng `ResultSet.getExecutionInfo().getPagingState()` hoặc `getSafePagingState()`; Spring Data gói ý niệm đó trong `CassandraPageRequest`.

Cần tuân thủ:

1. Chỉ dùng state với **cùng câu CQL, cùng bind parameters và cấu hình truy vấn tương ứng**.
2. Không xem state là offset, số thứ tự trang hoặc timestamp có thể tự sửa.
3. Không dùng state để tự ghép “trang tiếp theo” theo một partition khác.
4. Không bảo đảm snapshot bất biến khi có ghi/xóa xen giữa các lần lấy trang.
5. Nếu đưa cursor ra HTTP, nên **mã hóa/đóng gói và xác thực tính toàn vẹn**, gắn nó với truy vấn, người dùng/tenant, thời hạn và giới hạn số trang. Đừng tin một paging state nhận từ client mà chưa kiểm tra quyền truy cập.

Một cursor như `nextCursor` trên API là **contract do ứng dụng thiết kế**, không phải một trường Spring Data tự serialize an toàn mặc định.

## 9. Projection: ít cột hơn đồng nghĩa ít byte hơn

Trong chương **Chiếu và phân trang**, cần xem **số hàng trên mỗi trang** cùng với **số cột và kích thước mỗi hàng**.

### 9.1. SELECT * và SELECT cột cần thiết

Ví dụ một màn hình lịch sử sự kiện chỉ cần `event_time` và `event_type`. Truy vấn đầy đủ:

```sql
SELECT device_id, event_day, event_time, event_id, event_type, payload
FROM sdc_paging_lab.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-25';
```

Truy vấn chỉ các cột dùng để hiển thị:

```sql
SELECT event_time, event_id, event_type
FROM sdc_paging_lab.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-25';
```

Cả hai có thể trả **cùng số row** với cùng page size. Nhưng query thứ hai không gửi cột `payload` qua mạng, nên có thể giảm bytes truyền, chi phí giải mã và materialization. Nếu `payload` là vài KB/hàng, lợi ích có thể lớn.

### 9.2. Không đưa partial entity vào save vô điều kiện

Nếu repository trả `DeviceEvent` nhưng `@Query` chỉ chọn một số cột, các property bị bỏ qua có thể null hoặc không được khởi tạo, tùy mapper/constructor. Một entity nạp một phần **không nên được lưu lại bằng `save()` tùy tiện**, vì ghi lại có thể ảnh hưởng những cột chưa được tải.

Với màn hình chỉ hiển thị dữ liệu, dùng **projection/DTO phù hợp** với Spring Data Cassandra version, hoặc mapping thủ công qua `CqlSession`. Ví dụ dùng Java driver để chỉ đọc cột cần thiết:

```java
PreparedStatement summary = session.prepare("""
    SELECT event_time, event_id, event_type
    FROM sdc_paging_lab.events_by_device_day
    WHERE device_id = ? AND event_day = ?
    """);

BoundStatement statement = summary.bind(deviceId, day)
    .setPageSize(20);

for (Row row : session.execute(statement)) {
    Instant time = row.getInstant("event_time");
    UUID id = row.getUuid("event_id");
    String type = row.getString("event_type");
    // Chỉ tạo DTO hiển thị từ những cột đã SELECT.
}
```

Code trên vẫn duyệt tất cả các trang nếu câu `for` chạy tới cuối. Nếu UI chỉ cần 20 hàng, dùng `LIMIT 20` hoặc dừng đúng một trang qua cơ chế `Slice`/cursor.

### 9.3. Khi nào tăng/giảm số cột ảnh hưởng hiệu năng?

| Trường hợp | Hướng xử lý |
|---|---|
| Row hẹp, ít cột, nhiều row | Đo page size/round-trip; projection có thể ít tác động |
| Row rộng có `payload` lớn | SELECT đúng cột cần; dùng projection/DTO |
| Collection/blob lớn | Tránh `SELECT *` khi UI chỉ cần metadata |
| Partition nhiều tombstone | Giảm page size không xóa tombstone; cần xem TTL/delete/data modeling |
| Truy vấn toàn bảng | Projection có thể giảm bytes/row, nhưng **không loại bỏ scan rộng** |

Đừng tối ưu “số byte trả về” bằng cách bỏ cột **primary key** cần thiết để tạo entity đầy đủ rồi dùng object đó cho ghi lại.

## 10. LIMIT, page size, batching và backpressure không thay nhau được

### 10.1. Ví dụ so sánh có cùng schema

| CQL/API | Kết quả tối đa | Hành vi lấy dữ liệu |
|---|---|---|
| `SELECT ... WHERE partition = ... LIMIT 20` | 20 row | Có thể chia trang; câu CQL giới hạn tổng |
| `SELECT ... WHERE partition = ...` + `setPageSize(20)` + duyệt hết | Toàn bộ row phù hợp | Nhiều trang; có thể lấy hết |
| `SELECT ... WHERE partition = ...` + `setPageSize(20)` + chỉ xử lý trang hiện tại | Dữ liệu hiện có ở trang đang xét | Cần xử lý state/continuation đúng |
| Repository `Slice` size 20 | Nội dung một slice | Có thể lấy tiếp bằng paging state |
| `CassandraTemplate.select(query.limit(20), ...)` | 20 entity | `LIMIT` giới hạn tổng hàng query |
| `SELECT * FROM table LIMIT 20` | 20 row | Có thể vẫn đi qua nhiều partition; **không định nghĩa 20 row mới nhất toàn cluster** |

### 10.2. Paging không phải batch write

Trong Cassandra, **batch** là khái niệm **ghi nhiều mutation** bằng `BEGIN BATCH ... APPLY BATCH` và có semantics/chi phí riêng. `Page size` là khái niệm **đọc kết quả**. Không tăng/giảm batch size khi vấn đề thực tế là `ResultSet` tải quá nhiều row.

### 10.3. Paging cũng không thay backpressure

Nếu endpoint nhận hàng nghìn yêu cầu đồng thời, mỗi yêu cầu đều fetch nhiều trang, tổng request trên cluster vẫn có thể quá lớn, kể cả page size nhỏ. Ngoài page size cần quản lý:

- Số yêu cầu đồng thời và thời gian giữ session/stream.
- Thời gian xử lý mỗi row và điều kiện dừng đọc.
- Thời hạn cursor, quota số trang và max page size.
- Các luồng xuất dữ liệu/batch riêng với traffic tương tác.
- Cancellation khi client đóng kết nối hoặc hết deadline.

Một ứng dụng phản hồi nhanh cho 20 row khác với một job xử lý 20 triệu row, dù cả hai cùng dùng `pageSize = 20`.

## 11. Chọn page size dựa trên phép đo

Không có một kích thước phù hợp cho mọi workload. Giá trị **5.000** là mặc định lịch sử phổ biến của Java driver; người học cần đo theo dữ liệu thật trước khi tăng hoặc giảm.

### 11.1. Đánh đổi

| Page size | Thuận lợi | Rủi ro |
|---|---|---|
| **Nhỏ** (ví dụ 20–50) | Giảm lượng row mục tiêu một lượt; hợp UI nhỏ và row rộng | Nhiều round-trip hơn khi duyệt dài; overhead mạng/latency |
| **Vừa** (ví dụ 100–500) | Có thể cân bằng network và bộ nhớ | Cần kiểm tra kích thước mỗi row, tải và concurrency |
| **Lớn** (ví dụ 1.000–5.000) | Ít lượt fetch hơn nếu phải duyệt nhiều row hẹp | Trang lớn, áp lực heap/network, tăng thời gian chờ trang đầu |
| **Không phân trang** | Chỉ cân nhắc cho dữ liệu đã nhỏ và có giới hạn chắc chắn | Dễ phát sinh phản hồi khổng lồ và vượt tài nguyên |

Các mức trong bảng chỉ là **dải minh họa để thử nghiệm**, không phải ngưỡng bắt buộc của Cassandra.

### 11.2. Tư duy về bytes

Có thể ước lượng thô:

```text
Bộ nhớ/tải dữ liệu trang ~ số row trong trang × kích thước row thực tế
```

Ví dụ một row trung bình **2 KiB** và page size mục tiêu **200**, dữ liệu thô có thể ở khoảng **400 KiB/trang**. Đây không phải con số đo chính xác: protocol framing, serialization, đối tượng Java, heap, compression và server behavior có thể làm khác nhiều.

Khi chọn page size, cần phân tích **distribution của row width** (p95/p99), không chỉ giá trị trung bình. Một số row rất lớn có thể chi phối spike của heap/latency.

### 11.3. Các chỉ số nên theo dõi

- Latency của **trang đầu**, các trang tiếp và tổng request nghiệp vụ (p50/p95/p99).
- Số page fetch/round-trip và bytes nhận từ Cassandra.
- Kích thước mỗi row và số cột được projection.
- Heap allocation, GC pause và memory pressure của JVM.
- Driver in-flight requests, connection pool utilization và timeout.
- CPU, disk I/O, network, tombstone scan và SSTable ở Cassandra.
- Tỷ lệ khách hàng thực sự bấm “Tải thêm” sang trang 2, 3, v.v.

Một thử nghiệm hữu ích là so sánh `pageSize=50`, `200` và `1000` trên tập dữ liệu giống production, giữ nguyên consistency, CQL, projection và concurrency để tránh nhầm tác động từ các yếu tố khác.

### 11.4. Không chữa truy vấn sai bằng page size

Những truy vấn sau vẫn nguy hiểm khi không đúng access pattern:

```sql
-- Có thể đọc rộng khi bảng rất lớn:
SELECT * FROM sdc_paging_lab.events_by_device_day;

-- Không có đường truy cập theo event_type trong schema đã định nghĩa:
SELECT * FROM sdc_paging_lab.events_by_device_day
WHERE event_type = 'ALERT';
```

Với `pageSize(20)`, truy vấn đầu vẫn là **scan toàn bảng nếu ứng dụng duyệt hết**, còn truy vấn thứ hai vẫn có thể bị Cassandra từ chối vì `event_type` là regular column không có index phù hợp.

Đầu tiên hãy thiết kế bảng theo query: đầy đủ partition key, clustering restriction hợp lệ, bucket kích thước vừa phải; sau đó tối ưu lượng dữ liệu chuyển qua các trang.

## 12. Tránh những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Đặt `pageSize(20)` nhưng nhận `List` hàng nghìn phần tử | `select()`/`findAll()` tiếp tục tiêu thụ các trang | Dùng `LIMIT` hoặc `Slice` thay vì List không giới hạn |
| `ResultSet.all()` gây memory spike | Dồn toàn bộ row còn lại vào một list | Duyệt theo trang và xử lý/giải phóng dần |
| Trang có 17 row dù page size 20 | Page size là hint; ít row còn lại hoặc server kết thúc trang sớm | Không coi 20 là số row cam kết |
| 20 row nhưng hàng MB dữ liệu | Row rộng, blob/collection/payload lớn | Projection, giảm cột không cần, đo bytes |
| Tốc độ giảm mạnh khi page size = 1 | Quá nhiều network round-trip/overhead | Dùng giá trị vừa phải, đo latency |
| Spring `fetchSize(...)` hiện cảnh báo deprecated | API cũ | Dùng `QueryOptions.builder().pageSize(...)` |
| Java driver `setFetchSize(...)` bị deprecated | Alias chuyển từ 3.x | Dùng `setPageSize(...)` và giữ object trả về |
| Không có trang 2 mặc dù mong đợi | Query có `LIMIT` quá nhỏ, dữ liệu ít hoặc paging state không còn | Kiểm tra query, số row, `hasNext()` |
| Gọi `PageRequest.of(10, 20)` bị từ chối | Cassandra không dùng offset nhảy ngẫu nhiên | `CassandraPageRequest.first` và `nextPageable` |
| Trang 2 trả dữ liệu sai hoặc báo lỗi state | Đổi bind values/query shape giữa các trang | Giữ nguyên query và paging state tương ứng |
| Truy vấn chỉ theo regular column bị từ chối | Thiếu partition key/index | Thiết kế schema/read model đúng truy vấn |
| Async API xử lý CPU nặng trên callback | Callback trên I/O thread bị chặn | Offload sang executor, kiểm soát backpressure |
| Trang sau có dữ liệu lặp/khác trước | Ghi/xóa đồng thời; paging không là snapshot bất biến | Xác định consistency/cursor behavior, cơ chế chống trùng nếu cần |
| Tăng page size nhưng latency vẫn cao | Partition quá lớn, tombstone nhiều, coordinator quá tải | Điều tra schema, SSTable, compaction và metrics |

### 12.1. Quy trình chẩn đoán

1. Xác định **CQL thực tế** và số partition mà truy vấn có thể đọc.
2. Tách **`LIMIT`** (tổng row) khỏi **page size** (mỗi lượt fetch) trong code/config.
3. Xác định caller đang dùng **`List`, `Slice`, `ResultSet` hay `AsyncResultSet`**.
4. Kiểm tra code có vô tình gọi `all()`, `forEach` đến cuối hoặc `findAll()` không.
5. Đo **row width và danh sách cột**; so sánh `SELECT *` với projection.
6. Xem số trang đã lấy, latency mạng và bộ nhớ; điều chỉnh page size có kiểm chứng.
7. Nếu có cursor, kiểm tra đúng paging state, cùng query và phân quyền truy cập.
8. Kiểm thử với dữ liệu đủ lớn; tám row của lab chỉ chứng minh mechanics, không chứng minh hiệu năng production.

## 13. Bài tập thực hành

### Bài 1 — Dự đoán số hàng

Bảng có 130 row thuộc một partition. Không có `LIMIT`. Code dùng `setPageSize(25)` rồi `for (Row row : resultSet)` tới cuối.

**Câu hỏi:** code sẽ xử lý bao nhiêu row? Có thể nói chắc cần đúng sáu round-trip không?

**Đáp án:** Nếu dữ liệu không thay đổi và không có lỗi, code duyệt **130 row**. Không thể khẳng định số round-trip chính xác bằng phép chia vì page size là hint, server/driver có thể có prefetch và các ngưỡng thực thi khác.

### Bài 2 — Phân biệt LIMIT và page size

Một query có `LIMIT 12`, statement có `pageSize(50)`. Hỏi tối đa bao nhiêu row ứng dụng nhận từ query?

**Đáp án:** **12**. `LIMIT` giới hạn tổng kết quả, `pageSize` chỉ gợi ý kích thước một trang.

### Bài 3 — CqlTemplate/CassandraTemplate

```java
QueryOptions options = QueryOptions.builder().pageSize(10).build();
Query query = Query.query(
    Criteria.where("device_id").is(deviceId),
    Criteria.where("event_day").is(day)
).queryOptions(options);

List<DeviceEvent> events = template.select(query, DeviceEvent.class);
```

**Câu hỏi:** Nếu partition có 5.000 row, `events` có chắc chắn chỉ 10 phần tử không?

**Đáp án:** Không. `template.select` materialize tất cả row của query; `pageSize(10)` không hạn chế tổng row. Muốn tối đa 10, thêm `query.limit(10)` hoặc dùng `Slice`.

### Bài 4 — Cấu hình theo statement

Viết một `PreparedStatement` đọc theo `device_id` và `event_day`. Bind `UUID`, `LocalDate` rồi gọi `setPageSize(30)`. Giải thích vì sao phải gán hoặc chain kết quả của `setPageSize` trong Java driver 4.x.

### Bài 5 — Repository Slice

Viết repository method trả `Slice<DeviceEvent>` với `@Query` theo composite partition key, nhận `Pageable`. Gọi trang đầu bằng `CassandraPageRequest.first(3)`, sau đó lấy trang kế qua `first.nextPageable()` chỉ khi `first.hasNext()`.

**Giải thích:** Vì sao không được dùng paging state của thiết bị A cho thiết bị B?

### Bài 6 — Projection và row width

Hai query cùng page size **100**. Query A chọn `event_time, event_type`; query B chọn cả `payload` lớn.

**Câu hỏi:** Số row mục tiêu giống nhau có nghĩa bytes nhận từ server giống nhau không? Hãy đo và giải thích sự khác biệt.

### Bài 7 — Không phân trang offset

Một UI yêu cầu “nhảy trực tiếp đến trang 500” của lịch sử thiết bị. Cassandra không cung cấp offset ngẫu nhiên hiệu quả. Hãy đề xuất API **“Tải thêm” với cursor** hoặc thiết kế dựa trên clustering key/time window.

### Bài 8 — Chẩn đoán OOM

Ứng dụng có `pageSize = 100` nhưng đôi lúc `OutOfMemoryError`. Code gọi `repository.findAll()` rồi trả danh sách JSON.

**Yêu cầu:** Chỉ ra hai nguyên nhân: query quá rộng và materialize toàn bộ kết quả; sửa bằng query đúng partition + giới hạn/từng slice và giảm payload bằng projection nếu phù hợp.

### Bài 9 — So sánh sync/async

Giải thích vì sao `ResultSet` đồng bộ có thể tự lấy trang tiếp khi duyệt, trong khi `AsyncResultSet` cần gọi `fetchNextPage()` để chuyển trang. Nêu rủi ro khi làm blocking I/O trong callback async.

## 14. Câu hỏi tự kiểm tra

1. **Fetch size có giới hạn tổng row của query không?** Không. Nó chủ yếu điều khiển số row mục tiêu mỗi lượt fetch.
2. **Tài liệu Java driver 4.19 dùng tên chuẩn nào?** `page size` và `Statement.setPageSize(...)`.
3. **Default `basic.request.page-size` của Java driver 4.x là bao nhiêu?** Thường **5.000** theo cấu hình mặc định của driver; có thể được override.
4. **`pageSize(50)` có cam kết trang chứa đúng 50 row?** Không, server coi đó là một gợi ý.
5. **Khi nào `LIMIT 50` có ý nghĩa?** Khi muốn giới hạn tối đa tổng hàng trả từ statement; vẫn cần WHERE theo partition phù hợp.
6. **Điều gì xảy ra với `ResultSet.all()`?** Driver tiêu thụ các row còn lại, có thể qua nhiều trang và tạo list lớn.
7. **`AsyncResultSet.currentPage()` có duyệt hết query?** Không; chỉ trang hiện tại.
8. **Spring Data `QueryOptions.builder().fetchSize(20)` còn nên dùng không?** Không; API đã deprecated, thay bằng `pageSize(20)`.
9. **`CassandraTemplate.select(query)` + pageSize 20 có giới hạn 20 entity không?** Không; cần `LIMIT`/`Slice`.
10. **`Slice<T>` có cần `COUNT(*)` để biết tổng số trang không?** Không. Nó cung cấp thông tin có trang tiếp mà không cần tổng số row.
11. **Có thể dùng `PageRequest.of(99, 20)` để nhảy tới trang 100 không?** Không theo kiểu paging state của Cassandra.
12. **Projection giúp giảm gì?** Số cột/bytes trả về, decode và chi phí object; không tự giảm tổng số partition đọc.
13. **Fetch size có thay đổi consistency level không?** Không. Đó là hai cấu hình độc lập.
14. **Vì sao cần giữ nguyên query khi dùng paging state?** State mã hóa vị trí tiếp tục của **cùng truy vấn**, không phải offset dùng chung.
15. **Nếu UI chỉ cần 20 kết quả đầu, hướng nào phù hợp?** Query theo partition, `LIMIT 20` hoặc một `Slice` 20 row; không gọi full scan rồi cắt trong Java.

## 15. Tổng kết

- **Fetch size/page size** giới hạn *kích thước mong muốn của một lượt trả kết quả*, không giới hạn *tổng số row* trong câu query.
- **Java driver 4.x** dùng `setPageSize(...)`; các API `setFetchSize(...)` là alias cũ đã deprecated. `BoundStatement` immutable nên giữ object trả về sau khi set.
- **`ResultSet` đồng bộ** có thể tự tải trang kế trong khi duyệt; `all()` materialize toàn bộ phần còn lại. **`AsyncResultSet`** tách mỗi trang rõ ràng với `currentPage()` và `fetchNextPage()`.
- **Spring Data Cassandra** hỗ trợ `QueryOptions.builder().pageSize(...)`, `CassandraTemplate.slice(...)` và repository `Slice<T>` kết hợp `CassandraPageRequest`.
- **`LIMIT`, projection và WHERE đầy đủ partition key** giúp giảm tổng dữ liệu cần đọc/trao đổi; paging state giúp tiến về phía trước qua các lượt đọc.
- Tối ưu từ **schema và access pattern** trước, sau đó đo page size theo **row width, network, latency, concurrency và heap**; không coi một giá trị cấu hình là tối ưu cho mọi workload.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.19 — Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): page size mặc định, synchronous/async paging, paging state, offset và các cảnh báo hiệu năng.
- [Apache Cassandra Java Driver 4.19 — Statement API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): `setPageSize`, `getPageSize` và `setFetchSize` đã deprecated.
- [Apache Cassandra Java Driver 4.19 — Asynchronous Programming](https://apache.github.io/cassandra-java-driver/4.19.0/core/async/): `CompletionStage`, asynchronous callbacks và I/O threads.
- [Spring Data Cassandra 4.5 — CassandraPageRequest API](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/query/CassandraPageRequest.html): paging state và forward-only navigation.
- [Spring Data Cassandra 4.5 — QueryOptions Builder API](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/cql/QueryOptions.QueryOptionsBuilder.html): `pageSize`, `fetchSize` deprecated và các tùy chọn query.
- [Spring Data Cassandra 4.5 — Query API](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/query/Query.html): `queryOptions`, `limit`, `pageRequest`.
- [Spring Data Cassandra — Persisting Entities / CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `select`, `slice` và query builder immutable.
- [Spring Data Cassandra 4.5 — CassandraRepository API](https://docs.spring.io/spring-data/cassandra/docs/4.5.x/api/org/springframework/data/cassandra/repository/CassandraRepository.html): `findAll(Pageable)` trả `Slice`.
- [Spring Data Cassandra 4.5 — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/4.5/cassandra/repositories/query-methods.html): `Pageable`, `QueryOptions` và kiểu kết quả.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `WHERE`, `LIMIT` và yêu cầu partition/clustering.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): thiết kế bảng theo truy vấn và kích thước partition.
