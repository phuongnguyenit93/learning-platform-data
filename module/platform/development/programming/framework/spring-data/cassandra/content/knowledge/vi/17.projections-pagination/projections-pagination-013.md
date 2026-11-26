# Giải phóng tài nguyên khi sử dụng Stream hoặc dừng đọc sớm trong Spring Data Cassandra

## 1. Tình huống: cần 10 sự kiện, bảng có hàng triệu sự kiện

Một ứng dụng Spring Boot lưu lịch sử sự kiện bằng **Spring Data Cassandra**. Giao diện chỉ cần hiển thị **10 sự kiện mới nhất** của một tenant trong một ngày, nhưng partition tương ứng có thể chứa hàng chục nghìn sự kiện. Lập trình viên có thể viết:

~~~java
List<EventRow> all = repository.findAll();
return all.stream().limit(10).toList();
~~~

Đoạn code dễ đọc nhưng có thể đã **đọc và tạo đối tượng cho rất nhiều hàng** trước khi `limit(10)` được thực thi. `Stream` của Java không thể quay ngược thời gian để ngăn những lượt đọc Cassandra **đã xảy ra**.

Một cách khác là dùng repository trả `Stream<EventRow>` hoặc đọc từng hàng từ `ResultSet` của Java driver rồi dừng sau 10 hàng. Cách này đặt ra những câu hỏi quan trọng:

- Nguồn dữ liệu **thực sự lazy** hay danh sách đã được materialize?
- Khi dừng sớm, **trang tiếp theo** có còn được fetch không?
- Có cần gọi `Stream.close()` không? Gọi nó có đóng `CqlSession` không?
- `ResultSet` của Java driver Cassandra có phải một server-side cursor cần `close()` như JDBC không?
- Khi client ngắt kết nối HTTP hoặc hủy `Flux`, request đã gửi tới Cassandra có tự dừng ngay không?

Đây là bài học thuộc chương **Chiếu và phân trang**, tập trung vào **giải phóng tài nguyên khi sử dụng Stream hoặc dừng đọc sớm**. Nội dung áp dụng cho module `SPRING_DATA_CASSANDRA`: sử dụng entity mapping, repository, `CassandraTemplate` và CQL trong khi tôn trọng thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng của hệ phân tán.

**Sau bài này, bạn sẽ có thể:**

1. Phân biệt **giới hạn trên server** với `Stream.limit(...)` trên client.
2. Sử dụng `try-with-resources` đúng cách đối với **Stream có tài nguyên cần đóng**.
3. Hiểu rằng `ResultSet` của Java driver 4.x **không có phương thức đóng từng kết quả**; `CqlSession` mới là tài nguyên sống lâu cần quản lý vòng đời.
4. Dừng lặp sớm mà không tự động tải phần kết quả còn lại, đồng thời nhận biết **prefetch** và những request đã bay trên mạng.
5. Chọn projection, `LIMIT`, page size, paging state và reactive cancellation phù hợp với yêu cầu.
6. Viết test kiểm tra số hàng trả, tài nguyên được đóng và tình huống lỗi/hủy giữa chừng.

## 2. Phân biệt năm thứ dễ bị coi là “streaming”

| Khái niệm | Thực chất | Có đảm bảo tiết kiệm I/O Cassandra không? |
| --- | --- | --- |
| `List<T>.stream()` | Java Stream đọc từ **List đã có trong bộ nhớ** | **Không**: dữ liệu có thể đã được fetch hết |
| Repository query trả `Stream<T>` | Luồng kết quả do Spring Data cung cấp **nếu module/phiên bản hỗ trợ** | **Tùy cách triển khai**; phải xác minh việc fetch và đóng |
| Java driver `ResultSet` | Kết quả đồng bộ hỗ trợ **tự động phân trang khi duyệt** | **Có thể** không fetch trang chưa cần, nhưng có buffering/prefetch |
| Driver `AsyncResultSet` | Kết quả bất đồng bộ theo trang, có `fetchNextPage()` | Có thể quyết định **không gọi trang tiếp** |
| Reactive `Flux<T>` | Publisher có cơ chế subscription/demand/cancellation | Có thể giảm demand, nhưng **không đảm bảo thu hồi ngay request đã gửi** |

**Stream không đồng nghĩa server-side cursor.** Cần phân biệt ba lớp:

~~~mermaid
flowchart TD
    A[HTTP request / Service] --> B[Repository hoặc Template hoặc CqlSession]
    B --> C[CQL được gửi tới Cassandra]
    C --> D[Trang kết quả đã fetch vào driver]
    D --> E[Java object / Stream / Flux]
    E --> F{Consumer còn cần dữ liệu?}
    F -->|Có| G[Tiếp tục đọc hoặc fetch trang kế]
    F -->|Không| H[Không chủ động fetch phần còn lại]
    H --> I[Giải phóng tham chiếu, đóng resource thuộc sở hữu]
~~~

**Điều kiện để dừng sớm có lợi:** ứng dụng phải dừng **trước khi** thực hiện những lần fetch không cần thiết. Dừng ở bước `List.stream().limit(10)` sau khi toàn bộ kết quả đã thành `List` không tiết kiệm được những lần fetch trước đó.

## 3. Bảng theo truy vấn trước, Stream sau

Giả sử API cần lấy sự kiện mới nhất của **một tenant trong một ngày**:

~~~sql
CREATE TABLE events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò | Hệ quả |
| --- | --- | --- |
| `tenant_id` và `event_day` | **Partition key tổng hợp** | Cần xác định đủ để đọc một partition |
| `occurred_at` | Clustering column thứ nhất, `DESC` | Sự kiện mới hơn xuất hiện trước trong partition |
| `event_id` | Clustering column thứ hai, `ASC` | Phân biệt những sự kiện cùng timestamp |
| `event_type` | Cột thường | Có thể chiếu vào kết quả |
| `payload` | Cột thường, có thể lớn | Không cần truyền khi chỉ hiển thị tóm tắt |

Câu CQL phục vụ trực tiếp màn hình top 10:

~~~sql
SELECT event_id, occurred_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 10;
~~~

Đây là phương án thường **tốt hơn** so với truy vấn không giới hạn rồi tạo Stream để cắt 10 phần tử:

1. `WHERE` định vị đúng partition.
2. Thứ tự clustering đã đặt **mới nhất trước**, không cần tải mọi hàng rồi sort ở Java.
3. `SELECT` chỉ lấy **ba cột cần thiết**, bỏ `payload` có thể lớn.
4. `LIMIT 10` đặt **giới hạn tổng số hàng của câu truy vấn tại Cassandra**.

Nếu màn hình chỉ yêu cầu 10 sự kiện, đây là cách bắt đầu. Stream hữu ích khi cần **xử lý tuần tự tập kết quả lớn có kiểm soát**, chứ không phải cách thay thế những giới hạn server-side.

## 4. Projection tiết kiệm dữ liệu nhưng không giới hạn số hàng

**Projection** là chọn những cột/thuộc tính cần thiết cho use case. Có hai khía cạnh khác nhau:

- **Projection phía CQL:** `SELECT event_id, occurred_at, event_type` làm Cassandra và driver không phải gửi/đọc cột `payload`.
- **Projection phía Java:** ánh xạ những cột đó thành DTO/interface thay vì entity đầy đủ, tùy cách Spring Data query/mapping được cấu hình.

Một DTO minh họa:

~~~java
import java.time.Instant;
import java.util.UUID;

public record EventSummary(
    UUID eventId,
    Instant occurredAt,
    String eventType
) {}
~~~

Khi dùng Java driver trực tiếp, có thể tạo `EventSummary` từ các cột đã select. Khi dùng Spring Data repository, cần xác minh khả năng projection của phiên bản và cách câu CQL thực tế được tạo; **không mặc định chỉ vì Java trả DTO mà server chắc chắn không đọc các cột khác**.

| Kỹ thuật | Giảm số cột? | Giảm tổng số hàng? | Có giúp quản lý vòng đời? |
| --- | --- | --- | --- |
| `SELECT` chỉ cột cần | **Có** | Không | Gián tiếp giảm dữ liệu truyền và object mapping |
| `LIMIT 10` | Không | **Có** | Truy vấn hoàn tất sau tối đa 10 hàng |
| Page size 100 | Không | Không | Phân kết quả thành các lượt fetch |
| `Stream.limit(10)` trên List | Không thay đổi CQL | **Không ở server** | Chỉ giới hạn việc xử lý List |
| Dừng duyệt `ResultSet` sau 10 hàng | Không | Không nhất thiết: đã fetch ít nhất trang đầu | Có thể tránh fetch các trang chưa cần |

**Thứ tự ưu tiên:** thiết kế bảng theo truy vấn → select cột phù hợp → giới hạn số hàng trên server nếu biết trước → mới chọn cơ chế xử lý và đóng phía Java.

## 5. Java Stream có AutoCloseable, nhưng terminal operation không tự đóng

Trong Java, `java.util.stream.Stream<T>` mở rộng `AutoCloseable`. Vì vậy ta có thể sử dụng `try-with-resources`:

~~~java
try (Stream<EventSummary> stream = openEventStream()) {
    return stream
        .filter(this::isRelevant)
        .limit(10)
        .toList();
}
~~~

`openEventStream()` ở đây là **hàm minh họa** trả một `Stream`. Nếu stream có `onClose` handler giữ tài nguyên thực, `try-with-resources` đảm bảo `close()` được gọi cả khi khối xử lý kết thúc bình thường lẫn khi có exception.

**Điều rất dễ nhầm:** những terminal operation như `count()`, `findFirst()`, `forEach()`, `collect(...)` hoặc `toList()` **không tự động gọi `Stream.close()`**. Ngay cả một operation ngắn mạch như `limit(10)` hoặc `findFirst()` cũng không đồng nghĩa stream đã được đóng.

~~~java
Stream<EventSummary> stream = openEventStream();
EventSummary first = stream.findFirst().orElse(null);
// Nếu stream có tài nguyên bên dưới, thiếu close() có thể gây rò rỉ.
~~~

Với nguồn stream giữ tài nguyên, hãy dùng `try-with-resources` hoặc `finally` có chính sách sở hữu rõ ràng.

### 5.1. Stream.close() thực sự làm gì?

`close()` đánh dấu stream là đã đóng và chạy các `onClose` handlers đã đăng ký. Bản thân Java Stream **không biết** tài nguyên Cassandra, JDBC, network hay session nào cần đóng nếu nguồn stream **không cung cấp** cách dọn dẹp.

Ví dụ Java thuần để hiểu semantics:

~~~java
AtomicBoolean closed = new AtomicBoolean();

try (Stream<Integer> numbers = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true))) {
    List<Integer> firstTwo = numbers.limit(2).toList();
}

assertTrue(closed.get());
~~~

Ví dụ cần import `AtomicBoolean`, `Stream`, `List` và assertion. Handler chứng minh `close()` đã được gọi; **không chứng minh có tài nguyên database nào đã được giải phóng**.

### 5.2. Không return Stream rồi đóng ngay trước khi caller sử dụng

**Sai:**

~~~java
public Stream<EventSummary> events() {
    try (Stream<EventSummary> stream = openEventStream()) {
        return stream;
    }
}
~~~

Stream bị đóng khi thoát `try`, trước khi caller có cơ hội duyệt. Nếu stream đọc từ nguồn cần đóng, đây là lỗi về **ownership và lifetime**.

Cách an toàn hơn là **duyệt và đóng trong cùng phạm vi service** hoặc tuyên bố rõ caller sở hữu stream và phải đóng:

~~~java
public List<EventSummary> firstTenEvents() {
    try (Stream<EventSummary> stream = openEventStream()) {
        return stream.limit(10).toList();
    }
}
~~~

**Với repository streaming:** chỉ dùng mẫu này nếu Spring Data Cassandra **thật sự hỗ trợ kiểu trả `Stream<T>` ở phiên bản của dự án** và stream đó được cấu hình đúng. Các module Spring Data không nhất thiết có cùng semantics về streaming, lifecycle hoặc conversion.

## 6. Repository trả Stream: kiểm tra khả năng hỗ trợ và hợp đồng close

Một phương thức trong repository có thể được diễn đạt ở mức ý định:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.stream.Stream;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    // Ví dụ khai báo cần kiểm chứng trên phiên bản Spring Data Cassandra.
    @Query("SELECT * FROM events_by_tenant_day " +
           "WHERE tenant_id = ?0 AND event_day = ?1")
    Stream<EventRow> streamForDay(UUID tenantId, LocalDate eventDay);
}
~~~

**Đây là ví dụ về mong muốn API, không phải cam kết mọi phiên bản Spring Data Cassandra đều hỗ trợ repository streaming.** Cần thử khởi tạo repository và thực thi trên Cassandra test để biết: framework có nhận kiểu `Stream` không, có lazy fetch không, và `close()` có cleanup thực tế gì.

Nếu kiểu trả `Stream` được hỗ trợ, tầng service nên giữ lifetime rõ ràng:

~~~java
public List<EventSummary> firstTen(UUID tenantId, LocalDate day) {
    try (Stream<EventRow> rows =
             repository.streamForDay(tenantId, day)) {
        return rows
            .limit(10)
            .map(row -> toSummary(row))
            .toList();
    }
}
~~~

Đoạn này giả định Java hỗ trợ `Stream.toList()`, DTO/entity đã được định nghĩa và `toSummary(...)` là hàm chuyển đổi của service.

**Những điều không được giả định:**

- `Stream` nhất định có nguồn **lazy**; có thể framework đã materialize kết quả.
- `limit(10)` nhất định chỉ fetch 10 row từ Cassandra; driver có thể đã fetch một trang lớn hơn.
- `close()` của repository stream sẽ đóng `CqlSession`; session dùng chung phải tiếp tục phục vụ những request khác.
- Repository stream có thể đưa sang thread khác và dùng lâu dài tùy ý; vòng đời context, mapper và tài nguyên nền có thể không còn hợp lệ.

Nếu phiên bản không hỗ trợ streaming repository, **không cố ép bằng cast**. Hãy sử dụng `CqlTemplate`, `CqlSession` với `ResultSet`/`AsyncResultSet` hoặc truy vấn có giới hạn và page theo API thực tế.

## 7. Java driver 4.x ResultSet: không có close() cho từng kết quả

Trong **DataStax/Apache Cassandra Java driver 4.x**, `CqlSession` là tài nguyên dài hạn cần đóng khi ứng dụng ngừng sử dụng, còn `com.datastax.oss.driver.api.core.cql.ResultSet` đồng bộ **không cung cấp `close()` theo kiểu JDBC ResultSet**.

Một truy vấn đồng bộ:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT event_id, occurred_at, event_type " +
    "FROM app_ks.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ?"
);

BoundStatement stmt = ps.bind(tenantId, day)
    .setPageSize(50);

ResultSet result = session.execute(stmt);
~~~

`session` là `CqlSession` đã được khởi tạo đúng cluster/local datacenter và tồn tại lâu hơn request. Ví dụ cần import các kiểu CQL driver 4.x. `setPageSize(50)` là cấu hình **kích thước trang**, không phải giới hạn tổng số row.

### 7.1. Dừng sau 10 hàng

~~~java
List<EventSummary> summaries = new ArrayList<>();
Iterator<Row> rows = result.iterator();

while (summaries.size() < 10 && rows.hasNext()) {
    Row row = rows.next();
    summaries.add(new EventSummary(
        row.getUuid("event_id"),
        row.getInstant("occurred_at"),
        row.getString("event_type")
    ));
}

return summaries;
~~~

Đoạn code nằm trong method trả `List<EventSummary>`, cần import `ArrayList`, `Iterator`, `List`, `Row`. Vòng lặp **không chủ động duyệt các hàng còn lại** và không gọi `result.all()`.

**Nhưng lưu ý:** `session.execute(...)` thường đã nhận **trang đầu**. Với page size 50, lấy 10 hàng **không đồng nghĩa server chỉ gửi đúng 10 hàng**. Driver còn có thể **prefetch** trang tiếp theo tùy thời điểm và cấu hình; việc dừng lặp làm giảm nhu cầu fetch, nhưng **không có cam kết tuyệt đối rằng chỉ một lượng byte đúng bằng 10 row đã đi qua mạng**.

### 7.2. Không được gọi ResultSet.close() hoặc đóng session giữa request

**Sai về API/vòng đời:**

~~~java
// Pseudocode sai - ResultSet của Java driver 4.x không có close():
result.close();

// Sai khi session là bean Spring dùng chung:
session.close(); // Không đóng session sau mỗi lần lấy 10 hàng.
~~~

Đoạn trên cố ý minh họa **mã không hợp lệ và anti-pattern**, không được sao chép để biên dịch.

Khi không cần các trang còn lại, **ngừng duyệt**; thả tham chiếu tới `ResultSet`/`Row`/collection không còn sử dụng. Driver có trách nhiệm quản lý bộ nhớ và kết nối nền; ứng dụng phải đóng **`CqlSession` theo vòng đời của nó**, không theo vòng đời một `ResultSet`.

**Cassandra paging không giống JDBC server cursor:** thông thường paging state mô tả vị trí tiếp tục truy vấn, không có một cursor server-side lâu dài phải gửi lệnh `CLOSE` sau mỗi lần dừng đọc. Tuy nhiên request/page đã gửi và bộ đệm client vẫn có chi phí cho tới khi hoàn tất hoặc được thu hồi.

## 8. Không gọi ResultSet.all() khi chỉ cần vài hàng

Java driver có những cách duyệt:

| API/kiểu xử lý | Hành vi | Khi nào dùng |
| --- | --- | --- |
| `result.one()` | Lấy một row kế tiếp hoặc `null` khi hết | Lookup một hàng, hoặc đọc từng row theo vòng lặp |
| `for (Row row : result)` | Duyệt hết nếu không `break` | Khi thật sự cần toàn bộ kết quả |
| `result.iterator()` + điều kiện dừng | Chỉ yêu cầu các phần tử tiếp theo khi cần | Xử lý tuần tự có thể dừng sớm |
| `result.all()` | Thu thập **toàn bộ phần kết quả còn lại** vào List | Chỉ khi số hàng được giới hạn nhỏ |
| `StreamSupport.stream(result.spliterator(), false)` | Bọc iterator thành Java Stream tuần tự | Có thể dùng nhưng **không bổ sung cơ chế close driver** |

Một anti-pattern:

~~~java
List<Row> everyRow = result.all();
List<EventSummary> firstTen = everyRow.stream()
    .limit(10)
    .map(this::toSummary)
    .toList();
~~~

`all()` có thể buộc driver tải các trang còn lại rồi materialize tất cả row trước khi `limit(10)` chạy. Với hàng triệu kết quả, hậu quả có thể là **heap pressure, GC, độ trễ dài và timeout**.

Nếu thật sự chỉ cần 10 hàng, cách thích hợp nhất vẫn là **`LIMIT 10` ở CQL**. Nếu cần lựa chọn theo điều kiện chỉ có thể áp dụng ở Java, hãy duyệt tuần tự và dừng khi đã tìm đủ, đồng thời giới hạn phạm vi/khối lượng dữ liệu có thể quét.

## 9. Bọc ResultSet thành Stream: close() không tự có phép màu

Có thể tạo Java Stream từ `ResultSet`:

~~~java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Stream<Row> rows =
    StreamSupport.stream(result.spliterator(), false);

List<EventSummary> firstTen;
try (rows) {
    firstTen = rows
        .limit(10)
        .map(this::toSummary)
        .toList();
}
~~~

Đoạn mã giả định `result` và `toSummary(...)` đã có, dùng Java hỗ trợ `toList()`. `try-with-resources` đóng **Java Stream**, nhưng stream tạo từ `ResultSet.spliterator()` thông thường **không được gắn một close handler sở hữu kết nối**. Vì vậy:

- `rows.close()` không trở thành `result.close()`, bởi `ResultSet` driver 4.x không có API đó.
- `rows.close()` không được đóng `session` dùng chung.
- Việc dừng sớm đến từ **short-circuit operation và không duyệt tiếp**, không phải từ một lệnh “hủy mọi công việc Cassandra” ẩn bên dưới.
- Không nên dùng `parallel()` trên nguồn `ResultSet` có state phân trang và I/O. Duyệt tuần tự giúp kiểm soát tiêu thụ và thứ tự một cách rõ ràng.

Đây cũng là lý do phải kiểm tra **nguồn và ownership** của Stream thay vì áp dụng máy móc câu “mọi Stream đều cần close để giải phóng connection”. Nhiều Stream từ `List` thuần Java không giữ tài nguyên gì; các Stream do database/file cung cấp **có thể** giữ tài nguyên cần đóng.

## 10. Phân biệt LIMIT, page size, paging state và Stream.limit

| Kỹ thuật | Đặt ở đâu? | Ảnh hưởng quan trọng |
| --- | --- | --- |
| `LIMIT 10` | CQL/server | Tối đa 10 hàng cho **toàn truy vấn** |
| `setPageSize(50)` | Statement/driver | Nhắm tới kích thước **mỗi đợt fetch**; không giới hạn toàn bộ |
| Paging state | Driver/protocol | Điểm tiếp tục của một truy vấn có nhiều page |
| `Stream.limit(10)` | Java/client | Ngừng nhận thêm phần tử sau 10, tùy nguồn có lazy hay không |
| `SELECT` chỉ ba cột | CQL/server | Giảm lượng dữ liệu trên **mỗi row** |

Ví dụ muốn top 10:

~~~sql
SELECT event_id, occurred_at, event_type
FROM app_ks.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 10;
~~~

Giới hạn kết quả nên đặt ở **CQL**, không chỉ bên Java. Trong code driver:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT event_id, occurred_at, event_type " +
    "FROM app_ks.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 10"
);

BoundStatement stmt = ps.bind(tenantId, day).setPageSize(10);
ResultSet result = session.execute(stmt);
~~~

Nếu `LIMIT 10` đi cùng page size 10, ý định giới hạn rõ ràng ở cả hai phía; **page size vẫn là tùy chọn fetch** và có thể chịu hạn chế/cấu hình thực tế của driver/server.

### 10.1. Khi cần nhiều trang, không khóa cứng LIMIT 10 cho tất cả dữ liệu

Một API “xem 10 sự kiện mới nhất” có thể dùng `LIMIT 10`. Một API “duyệt lịch sử, mỗi trang 10 sự kiện” lại cần **thiết kế paging** phù hợp, thường sử dụng paging state hoặc cursor, không phải cứ giữ `LIMIT 10` rồi gọi lại để mong nhận “10 hàng kế tiếp”.

**`LIMIT` hạn chế tổng số hàng của câu truy vấn**, còn **page size** chia các hàng của cùng truy vấn thành lượt fetch. Với Cassandra, không dùng `OFFSET` tùy ý như SQL quan hệ để nhảy đến trang thứ N.

Paging state là dữ liệu phụ thuộc truy vấn và tham số; nếu chuyển ra API, phải **ràng buộc nó với tenant, điều kiện lọc, thứ tự và quyền truy cập**, không để token của request này dùng cho request khác.

## 11. Driver async: chủ động không fetch trang tiếp theo

Khi sử dụng `CqlSession.executeAsync(...)` của Java driver 4.x, kết quả `AsyncResultSet` tách từng trang rõ ràng. Ví dụ một service chỉ muốn đọc **trang đầu** và không cần thêm:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public CompletionStage<List<EventSummary>> firstPage(
        UUID tenantId, LocalDate day) {
    BoundStatement query = prepared.bind(tenantId, day)
        .setPageSize(25);

    return session.executeAsync(query).thenApply(page -> {
        List<EventSummary> summaries = new ArrayList<>();
        for (Row row : page.currentPage()) {
            summaries.add(new EventSummary(
                row.getUuid("event_id"),
                row.getInstant("occurred_at"),
                row.getString("event_type")
            ));
        }
        return summaries;
        // Không gọi page.fetchNextPage(): chỉ xử lý trang đầu.
    });
}
~~~

`session` và `prepared` là field của service đã khởi tạo; `prepared` tương ứng câu CQL `SELECT ... WHERE tenant_id = ? AND event_day = ?` không có tổng `LIMIT 25` bắt buộc. Cần import `UUID`, `LocalDate` và Spring/driver classes theo dự án; ví dụ biểu diễn Java driver 4.x.

**Ưu điểm:** code quyết định rõ có gọi `fetchNextPage()` hay không. Nếu chỉ xử lý trang đầu, **không phát lệnh chủ động yêu cầu trang kế**.

**Giới hạn:** thao tác `executeAsync(...)` đầu tiên đã gửi request và nhận page đầu; nó không thể bị “thu hồi” chỉ bằng việc code không gọi trang tiếp. Cũng không nên giả định kích thước trang trả về luôn **chính xác** 25 row trong mọi điều kiện query/server.

### 11.1. Nếu cần đọc hết, phải giới hạn cả tổng công việc

Với nhiều trang, một dạng luồng xử lý:

~~~text
executeAsync(statement)
  -> currentPage()
  -> xử lý row và kiểm tra quota
  -> còn cần dữ liệu + hasMorePages() ?
       YES -> fetchNextPage()
       NO  -> kết thúc và thả tham chiếu
~~~

Không viết đệ quy không giới hạn chỉ vì `hasMorePages()` còn true. API nên đặt hạn mức số hàng, thời gian xử lý, số trang và/hoặc kích thước dữ liệu. Khi xử lý bất đồng bộ, phải quản lý cancellation, exception và concurrency để tránh tích tụ hàng nghìn page trong bộ nhớ.

## 12. Reactive Flux và cancellation: dừng nhu cầu không đồng nghĩa hủy I/O tức thì

Nếu ứng dụng dùng **Reactive Spring Data Cassandra** hoặc một publisher kết nối tới Java driver, kết quả thường được biểu diễn dưới dạng **`Flux<T>`**. Reactive Streams hỗ trợ **demand/backpressure** và **cancellation**.

Ví dụ biểu đạt ý định:

~~~java
Flux<EventSummary> summaries =
    reactiveService.findForDay(tenantId, day)
        .map(this::toSummary)
        .take(10)
        .doFinally(signal -> log.debug("Stream finished: {}", signal));
~~~

Đoạn trích giả định có `reactiveService` cung cấp `Flux<EventRow>`, `toSummary` và logger, cần import Reactor `Flux`. `take(10)` chỉ nhận tối đa 10 phần tử rồi **cancel subscription upstream** theo semantics Reactor.

**Những điều được và không được kỳ vọng:**

- Cancellation thông báo consumer **không còn yêu cầu dữ liệu** và publisher có thể ngừng fetch/emit tiếp.
- Publisher/driver **có thể đã có buffer hoặc request Cassandra đang chạy**. Cancellation không bảo đảm server hủy tức thì một request đã gửi.
- `doFinally(...)` hữu ích để quan sát tín hiệu hoàn thành, lỗi hay cancel. Nó không tự đóng `CqlSession`.
- Không sử dụng `doOnCancel(() -> session.close())` khi `session` là **bean dùng chung**; một client hủy HTTP request không được làm mất kết nối của toàn ứng dụng.
- Cơ chế reactive publisher, backpressure và lifecycle thực tế phụ thuộc phiên bản Spring Data Cassandra và driver; cần test trong môi trường giống production.

### 12.1. Chủ sở hữu tài nguyên trong reactive code

Nếu một publisher **tự tạo tài nguyên riêng cho từng subscription** (ví dụ một nguồn `AutoCloseable` riêng), nó cần dọn tài nguyên khi complete/error/cancel. Reactor có thể cung cấp các mẫu `using` hoặc `usingWhen` tùy loại tài nguyên. Tuy nhiên, một `CqlSession` dùng chung trong Spring **không phải tài nguyên riêng của subscription**, nên việc đóng nó khi cancel là sai.

Đừng đồng nhất **dispose subscription** với **đóng tất cả tài nguyên của cluster**. Cần vẽ ranh giới sở hữu rõ ràng.

## 13. Vòng đời CqlSession trong Spring Boot

Sơ đồ vòng đời đúng cho ứng dụng thông thường:

~~~mermaid
flowchart TD
    A[Spring ApplicationContext khởi tạo] --> B[Tạo 1 hoặc vài CqlSession có chủ đích]
    B --> C[Repository / CassandraTemplate / CqlTemplate / service]
    C --> D[Request A]
    C --> E[Request B]
    C --> F[Request C]
    D --> G[ResultSet / Stream / Flux của request]
    E --> H[ResultSet / Stream / Flux của request]
    F --> I[ResultSet / Stream / Flux của request]
    G --> J[Complete / stop early / cancel: xử lý tài nguyên của request]
    H --> J
    I --> J
    J --> K[CqlSession vẫn sống cho request sau]
    K --> L[Spring context đóng: CqlSession.close()]
~~~

**Quy tắc sở hữu:**

- **Spring context** sở hữu `CqlSession` do nó tạo; đóng session khi ứng dụng kết thúc.
- **Service/request** sở hữu các cấu trúc đọc cục bộ và phải ngừng tiêu thụ khi đã đủ; nếu có `Stream` được hỗ trợ với close handler, đóng stream khi xong.
- **Driver** sở hữu connection pools, metadata và các buffer nội bộ; chúng không nên bị đóng vì một kết quả đọc cụ thể đã kết thúc.
- **Ứng dụng** sở hữu quy tắc hạn mức, timeout, paging và số lượng request đồng thời.

Không tạo `CqlSession.builder().build()` cho mỗi lời gọi truy vấn; không giữ session hoặc result không còn sử dụng trong static collection. Nếu ứng dụng có nhiều keyspace/session, đặt bean rõ ràng bằng `@Qualifier` và áp dụng **cùng nguyên tắc lifecycle** cho từng session.

### 13.1. Bean session tự tạo

Nếu tự quản lý session trong cấu hình Spring (thay vì dùng auto-configuration):

~~~java
@Bean(name = "eventSession", destroyMethod = "close")
CqlSession eventSession() {
    return CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc1")
        .withKeyspace(CqlIdentifier.fromCql("app_ks"))
        .build();
}
~~~

Ví dụ cần import `@Bean`, `CqlSession`, `InetSocketAddress`, `CqlIdentifier`, đặt trong lớp cấu hình phù hợp. `dc1` là tên DC giả định, phải thay bằng giá trị thực tế. **Không đăng ký trùng session** nếu Spring Boot đã auto-configure bean tương ứng mà ứng dụng vẫn đang sử dụng.

`destroyMethod = "close"` chỉ thể hiện Spring đóng session khi context bị hủy. Nó **không** bảo rằng mọi `ResultSet` sẽ bị đóng khi Java Stream dừng, cũng không cung cấp transaction/cursor theo request.

## 14. Dừng sớm an toàn: checklist thực thi

### 14.1. Khi biết trước cần đúng tối đa N hàng

1. Xác định **đầy đủ partition key** và thứ tự clustering phù hợp.
2. Dùng projection `SELECT` chỉ những cột cần thiết.
3. Đặt `LIMIT N` trong câu CQL.
4. Chọn page size hợp lý so với N và workload, không dùng page size cực lớn.
5. Mapping tối đa N row thành DTO và trả kết quả; không cần Stream để che vấn đề truy vấn.

### 14.2. Khi không biết trước sẽ lấy bao nhiêu hàng

Ví dụ cần dừng sau khi gặp **đủ 10 sự kiện hợp lệ** theo kiểm tra nghiệp vụ phức tạp không thể biểu diễn dễ bằng CQL:

1. Giới hạn **partition/ngày** và loại bỏ các cột không cần thiết.
2. Chọn page size vừa phải để tránh overfetch quá nhiều mỗi lần.
3. Duyệt tuần tự; tăng bộ đếm chỉ khi row thỏa điều kiện.
4. Thoát vòng lặp ngay khi đủ 10 hoặc đã đạt hạn mức số row scan/thời gian.
5. Không gọi `all()`, không giữ tham chiếu toàn bộ những row bị loại.
6. Nếu dùng Java Stream có close handler, đóng trong `finally`/`try-with-resources`.
7. Ghi metrics số row đã xét, page đã fetch, độ trễ và tỷ lệ dừng sớm.

Ví dụ tự đặt hạn mức:

~~~java
int examined = 0;
int accepted = 0;
int maxExamined = 500;
List<EventSummary> output = new ArrayList<>();

Iterator<Row> iterator = result.iterator();
while (accepted < 10
        && examined < maxExamined
        && iterator.hasNext()) {
    Row row = iterator.next();
    examined++;
    if (isRelevant(row)) {
        output.add(toSummary(row));
        accepted++;
    }
}
~~~

`isRelevant(...)` và `toSummary(...)` là các hàm nghiệp vụ. Đặt kiểm tra quota **trước** `iterator.hasNext()` để không hỏi iterator lấy thêm row khi đã đạt giới hạn. Tuy nhiên `hasNext()` vẫn có thể kích hoạt fetch trang tiếp theo khi quota chưa đạt; nếu cần kiểm soát chính xác từng lần fetch, dùng API async theo page và chỉ `fetchNextPage()` khi vẫn còn nhu cầu.

**Quan trọng:** lọc nhiều hàng tại Java chỉ là giải pháp có giới hạn cho một điều kiện đặc biệt. Nếu `isRelevant` là access pattern phổ biến, nên thiết kế bảng theo truy vấn hoặc khả năng index phù hợp thay vì đều đặn scan 500 hàng để tìm 10 hàng.

## 15. Những cách gây rò rỉ hoặc tiêu thụ tài nguyên quá mức

| Anti-pattern | Tác động | Cách sửa |
| --- | --- | --- |
| `repository.findAll().stream().limit(10)` | Có thể fetch rất nhiều hàng trước khi cắt | Query theo partition key với `LIMIT 10` |
| `result.all()` rồi lấy vài phần tử | Tải mọi trang còn lại, tăng heap/GC | Duyệt từng row hoặc server-side limit |
| Repository trả Stream nhưng caller không đóng | Có thể giữ tài nguyên của nguồn lâu hơn cần thiết | `try-with-resources` khi source stream yêu cầu |
| Return Stream ra khỏi service rồi đóng ngay trong service | Caller nhận nguồn đã đóng | Xử lý trong scope sở hữu hoặc chuyển giao ownership rõ ràng |
| `stream.close()` rồi tưởng `CqlSession` đã đóng | Sai ranh giới lifecycle | Đóng session lúc ApplicationContext dừng |
| `session.close()` sau khi đọc 10 row | Những request sau dùng session đã đóng | Tái sử dụng session theo vòng đời bean |
| Gọi `ResultSet.close()` trên Java driver 4.x | API không tồn tại | Dừng lặp, không fetch tiếp, thả tham chiếu |
| `Stream.parallel()` trên driver ResultSet | Dễ gây đọc không kiểm soát, khó giữ thứ tự | Duyệt tuần tự hoặc thiết kế xử lý phân tán riêng |
| `take(10)` trên Flux rồi đóng shared session ở `doFinally` | Hủy kết nối chung của ứng dụng | Cancel subscription, giữ session sống |
| Giữ `List<Row>` / `ResultSet` toàn cục để “cache” | Tăng bộ nhớ và kéo dài vòng đời dữ liệu | Cache DTO nhỏ có hạn mức/TTL và chính sách phù hợp |
| Page size cực lớn để “đỡ request” | Overfetch, heap lớn, tail latency xấu | Đo và đặt page size hợp lý |
| Không giới hạn số hàng có thể xét khi lọc ở Java | Scan kéo dài, tốn replica/CPU | Đặt quota và thiết kế query-first |

Không phải mọi Stream “quên close” đều gây **rò rỉ kết nối Cassandra**. Lỗi phụ thuộc **nguồn Stream có tài nguyên gì và có onClose handler không**. Đánh giá đúng sẽ tránh cả hai cực đoan: bỏ qua tài nguyên cần đóng, hoặc đóng nhầm `CqlSession` dùng chung.

## 16. Lỗi, timeout, cancellation và kết quả không đầy đủ

### 16.1. Truy vấn trả 0 hàng

Nếu câu CQL chạy thành công nhưng không có row, `ResultSet.one()` trả `null` hoặc API danh sách trả collection rỗng. Đây là kết quả hợp lệ.

### 16.2. Lỗi xảy ra trong lúc đang đọc trang sau

Ngay cả khi trang đầu thành công, một lượt fetch tiếp theo có thể thất bại vì:

- Replica/node không sẵn sàng hoặc mạng chậm.
- Request timeout hoặc chính sách retry không còn cho phép tiếp tục.
- Mapping một cột mới gặp dữ liệu/codec không tương thích.
- Ứng dụng bị hủy request hoặc hết quota.

**Không được biến lỗi thành kết quả rỗng như thể toàn bộ truy vấn đã hoàn tất.** Nếu API cho phép trả kết quả một phần, phải thiết kế rõ `partial`/cursor/trạng thái lỗi; nếu không, truyền lỗi ra handler. `try-with-resources` vẫn hữu ích vì nó chạy close handler ngay cả khi pipeline ném exception.

### 16.3. Cancellation không thể “undo” dữ liệu đã được gửi

Với async/Flux, hủy subscription hoặc dừng duyệt giúp **không tiếp tục yêu cầu dữ liệu** khi publisher/driver hỗ trợ, nhưng:

- Request đã gửi đến Cassandra có thể đang được xử lý.
- Trang đã nhận có thể vẫn nằm trong buffer driver cho tới khi không còn tham chiếu.
- Một request ghi đã gửi **không tự bị rollback** vì client ngừng chờ.
- Không có “commit/rollback” toàn cục chỉ vì một stream đã đóng.

Vì vậy cần tách **quyết định dừng đọc** khỏi **bảo đảm tính nhất quán** của các thao tác dữ liệu.

## 17. Kiểm thử hành vi đóng và dừng sớm

### 17.1. Unit test Java Stream đóng đúng khi dừng sớm

Một bài test độc lập với Cassandra xác minh `try-with-resources`:

~~~java
@Test
void closesStreamEvenWhenLimitStopsEarly() {
    AtomicBoolean closed = new AtomicBoolean(false);
    AtomicInteger visited = new AtomicInteger();

    try (Stream<Integer> stream = Stream.of(1, 2, 3, 4, 5)
            .peek(value -> visited.incrementAndGet())
            .onClose(() -> closed.set(true))) {
        assertEquals(List.of(1, 2), stream.limit(2).toList());
    }

    assertEquals(2, visited.get());
    assertTrue(closed.get());
}
~~~

Ví dụ dùng JUnit 5, `AtomicBoolean`, `AtomicInteger`, `Stream` và `List`, Java có `Stream.toList()`. Đây là **test semantics Java Stream**, không chứng minh driver fetch đúng hai hàng và không chứng minh đóng session.

### 17.2. Unit test đóng cả khi mapping lỗi

~~~java
@Test
void closesStreamWhenMappingThrows() {
    AtomicBoolean closed = new AtomicBoolean();

    assertThrows(IllegalStateException.class, () -> {
        try (Stream<Integer> stream = Stream.of(1, 2, 3)
                .onClose(() -> closed.set(true))) {
            stream.map(value -> {
                if (value == 2) {
                    throw new IllegalStateException("Invalid item");
                }
                return value;
            }).toList();
        }
    });

    assertTrue(closed.get());
}
~~~

Test minh họa vì sao một exception giữa pipeline **không bỏ qua cleanup** khi phạm vi sở hữu được viết đúng.

### 17.3. Integration test với Cassandra

Tạo keyspace và bảng `events_by_tenant_day` trong môi trường thử nghiệm rồi:

1. Ghi **ít nhất 120 sự kiện** vào cùng tenant/ngày và một số hàng sang tenant/ngày khác.
2. Đọc top 10 bằng **CQL `LIMIT 10` với projection ba cột**; xác minh chỉ nhận tối đa 10 hàng và đúng thứ tự clustering.
3. Đọc cùng partition bằng driver, đặt page size 25 rồi **chỉ duyệt 10 hàng**; xác minh đúng 10 DTO, không gọi `result.all()`.
4. Đọc bằng `AsyncResultSet`; chỉ xử lý `currentPage()` và không gọi `fetchNextPage()`. Đo/quan sát số request mạng thực tế nếu môi trường có hỗ trợ tracing/metrics.
5. Nếu Spring Data Cassandra trong dự án hỗ trợ repository `Stream<T>`, kiểm tra stream có đọc lười không và `close()` có gọi cleanup handler hay không; không áp giả định của JDBC.
6. Thử hủy Flux hoặc dừng xử lý ngay sau 10 row; quan sát rằng không còn demand nhưng có thể có request đã gửi.
7. Xác minh **`CqlSession` vẫn sống** để phục vụ request thứ hai, thứ ba sau khi stream/result trước dừng.
8. Cố ý làm mapper ném exception giữa chừng và kiểm tra stream/resource handler tương ứng vẫn được gọi.
9. Test trường hợp không có row, timeout/failure trên trang tiếp theo và phân biệt **rỗng** với **lỗi**.
10. Đo heap, lượng row đã ánh xạ, latency, số page fetch, tải replica và số session/connection trước/sau bài thử.

**Không chạy stress test, node failure hoặc fault injection trên Cassandra production.** Dùng môi trường test phù hợp, chủ động dọn fixture và giữ page size/độ lớn dữ liệu đủ nhỏ để kiểm soát chi phí.

### 17.4. Bảng chứng cứ cần thu thập

| Quan sát | Có thể kết luận gì? | Không nên kết luận gì? |
| --- | --- | --- |
| `Stream.onClose` đã chạy | Java stream được đóng | Cassandra session/connection chắc chắn đã đóng |
| Consumer xử lý đúng 10 row | Logic dừng sớm đúng | Cassandra chỉ gửi đúng 10 row qua mạng |
| `LIMIT 10` có trong CQL | Query có tổng giới hạn 10 hàng | Partition/cluster chắc chắn khỏe và truy vấn luôn nhanh |
| Không gọi `fetchNextPage()` | Code không chủ động yêu cầu trang tiếp | Không có request nào đang bay hoặc mọi buffer đã được thu hồi ngay |
| Một Flux phát tín hiệu cancel | Upstream nhận tín hiệu ngừng nhu cầu | Query server bị hủy tức thì và không tốn thêm CPU |
| Session vẫn chạy query tiếp theo | Không đóng nhầm tài nguyên dùng chung | Không có object/stream nào đang bị giữ tham chiếu |

## 18. Quan sát vận hành và tối ưu thực tế

Một cơ chế “dừng sớm” nên được đánh giá trên cả **I/O Cassandra** và **memory pressure của JVM**:

- **CQL query shape:** có đủ partition key không, có `LIMIT`/projection không, có dùng `ALLOW FILTERING` không.
- **Số hàng đọc và materialize:** so sánh row nhận từ driver và DTO thật sự dùng ở API.
- **Page size và số fetch:** page đầu thường chứa nhiều row hơn số consumer cuối cùng sử dụng; quá lớn gây overfetch.
- **Độ trễ theo phân vị:** đặc biệt là request đầu, page tiếp theo, lúc node chậm.
- **Heap/GC:** tránh `ResultSet.all()`, `collect(toList())` trên stream lớn không giới hạn.
- **Số `CqlSession`/connections:** cần ổn định theo topology ứng dụng, không tăng theo request.
- **Reactive subscriptions:** theo dõi timeout, cancellation và số publisher chưa hoàn tất.
- **Tombstone/partition size:** một truy vấn có `LIMIT 10` vẫn có thể đọc tốn kém khi partition lớn hoặc nhiều dữ liệu đã xóa.

**Tối ưu theo thứ tự:** sửa mô hình bảng và điều kiện CQL → giảm cột/kích thước row → giới hạn tổng hàng → chọn page size và phương pháp tiêu thụ → quản lý close/cancel → đo lại. Không nên bắt đầu bằng việc chuyển mọi repository method thành Stream rồi hy vọng tự động tiết kiệm I/O.

## 19. Bài tập tổng hợp

**Đề bài:** triển khai endpoint `GET /tenants/{tenantId}/events?day=2026-11-25&limit=10`, trả tóm tắt sự kiện mới nhất trong một partition; bổ sung một chức năng xử lý tuần tự các sự kiện trong ngày và **dừng sau khi tìm đủ 10 sự kiện hợp lệ**.

Các bước:

1. Tạo bảng `events_by_tenant_day` theo schema trên và ghi 120 sự kiện thử nghiệm.
2. Viết query top N có **đủ tenant/ngày**, projection ba cột, `LIMIT` được giới hạn bởi chính sách API.
3. Dùng repository/`CassandraTemplate` cho use case entity phù hợp; đối chiếu CQL phát sinh với mục tiêu projection.
4. Viết phiên bản Java driver sử dụng `PreparedStatement`, `BoundStatement` và `ResultSet.iterator()`; dừng sau 10 DTO.
5. So sánh số row ứng dụng xử lý khi dùng `result.all().stream().limit(10)` với khi dừng iterator sớm; đo memory/latency trong môi trường test.
6. Tạo một Stream có `onClose` handler để chứng minh `try-with-resources` hoạt động cả khi `limit(...)` và khi mapping ném exception.
7. Nếu repository `Stream<T>` được phiên bản Spring Data hỗ trợ, thử dùng và xác minh close/lazy behavior bằng integration test; nếu không, dùng driver pages thay thế.
8. Dùng `AsyncResultSet` để đọc trang đầu và **chủ động không gọi `fetchNextPage()`** khi đã đủ dữ liệu.
9. Thử một Flux `take(10)`; hủy subscription và xác minh session dùng chung vẫn phục vụ request mới.
10. Mở endpoint nhiều lần, kiểm tra số session/connection không tăng theo request và không có `close()` trên shared session trong logic xử lý.
11. Mô phỏng lỗi fetch trang sau hoặc mapper lỗi để kiểm chứng cleanup và cách trả lỗi, không chuyển lỗi thành danh sách rỗng giả.
12. Viết một đoạn giải thích sự khác nhau giữa **`LIMIT`, page size, paging state, Stream limit và Flux cancellation**.

**Tiêu chí đạt:** người học biết **đặt giới hạn ngay trong CQL khi có thể**, **không materialize vô hạn**, **đóng nguồn Stream có tài nguyên ở đúng phạm vi**, **không đóng nhầm `CqlSession`**, và hiểu rằng dừng đọc sớm không thể thu hồi ngay I/O đã thực hiện.

## 20. Câu hỏi tự kiểm tra

1. Vì sao `repository.findAll().stream().limit(10)` có thể tiêu thụ nhiều bộ nhớ và mạng hơn một câu CQL `LIMIT 10`?
2. `Stream.limit(10)` có tự đóng Stream sau khi nhận đủ 10 phần tử không?
3. Khi nào dùng `try-with-resources` với Stream có ý nghĩa thật sự?
4. `Stream.close()` có mặc định đóng `CqlSession` của Spring Data Cassandra không?
5. Vì sao không được gọi `ResultSet.close()` trên Java driver Cassandra 4.x?
6. Khi dừng duyệt `ResultSet` sau 10 row, điều gì có thể đã được fetch trước đó?
7. `ResultSet.all()` khác gì vòng lặp iterator có điều kiện dừng?
8. Sự khác nhau giữa CQL `LIMIT`, driver page size và paging state là gì?
9. Vì sao `SELECT event_id, occurred_at, event_type` hữu ích hơn `SELECT *` khi chỉ tạo tóm tắt?
10. Vì sao một repository method trả `Stream<T>` cần được kiểm chứng khả năng hỗ trợ/lazy/cleanup theo phiên bản?
11. Vì sao không nên return một Stream đã bị đóng trong khối `try` của service?
12. Nếu tạo `StreamSupport.stream(result.spliterator(), false)`, gọi `close()` có đóng một server cursor của Cassandra không?
13. `AsyncResultSet.currentPage()` và `fetchNextPage()` giúp quản lý dừng sớm như thế nào?
14. Khi `Flux.take(10)` cancel upstream, có đảm bảo tất cả request Cassandra đã gửi bị hủy tức thì không?
15. Tại sao `doFinally` hoặc `doOnCancel` không nên đóng shared `CqlSession`?
16. Nếu màn hình cần duyệt toàn bộ lịch sử nhiều trang, vì sao không thể giữ nguyên `LIMIT 10` rồi mong các lần gọi tiếp tự trả trang khác?
17. Tại sao một truy vấn có `LIMIT 10` vẫn có thể chậm khi partition có nhiều tombstone hoặc node đang quá tải?
18. Những test nào chứng minh stream được đóng, những test nào mới chứng minh workload Cassandra được tiết kiệm?

**Ghi nhớ:** khi cần ít dữ liệu từ **Spring Data Cassandra**, hãy **thiết kế truy vấn có partition key đúng, projection phù hợp và giới hạn ở CQL** trước. Với `Stream`, phải hiểu nguồn có lazy và có tài nguyên cần đóng hay không; terminal operation không tự gọi `close()`. Với Java driver, **`ResultSet` đồng bộ không có `close()` riêng**, nên dừng duyệt và không yêu cầu các trang tiếp theo; **`CqlSession` chỉ đóng khi hết vòng đời ứng dụng**. Với reactive `Flux`, cancellation giảm nhu cầu tiếp tục nhưng không đảm bảo thu hồi tức thì I/O đã gửi. Quản lý đúng ranh giới tài nguyên là nền tảng để paging và xử lý dữ liệu phân tán an toàn, hiệu quả.
