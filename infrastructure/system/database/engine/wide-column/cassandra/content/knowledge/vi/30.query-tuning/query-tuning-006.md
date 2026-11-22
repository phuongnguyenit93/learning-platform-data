# Page size, LIMIT và bộ nhớ phía client/server trong Apache Cassandra

## 1. Vấn đề: một câu SELECT “chạy được” vẫn có thể làm cạn bộ nhớ

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Dữ liệu được phân phối theo **partition key**, các bảng nên được thiết kế theo truy vấn, và mỗi request CQL đi qua Java Driver, coordinator rồi đến các replica theo **consistency level**. Một câu `SELECT` tưởng đơn giản có thể trả về hàng chục nghìn row, làm bận network, chiếm bộ nhớ tại node và khiến ứng dụng Java gặp GC pause hoặc `OutOfMemoryError`.

Hai tham số thường bị nhầm là **`LIMIT`** trong CQL và **page size/fetch size** của driver:

- **`LIMIT`** giới hạn **tổng số row kết quả** mà một lần thực thi truy vấn được phép trả về.
- **Page size** đặt mục tiêu **số row trong mỗi trang kết quả**, giúp client lấy dữ liệu theo nhiều lần thay vì kéo toàn bộ một lượt.
- **Bộ nhớ client/server** phụ thuộc cả kích thước thực tế từng row, số trang đang xử lý, số request đồng thời, cách client tích lũy kết quả và chi phí đọc để tạo trang.

Chúng **không** tương đương với nhau. Nếu query có `LIMIT 10000` và page size `200`, ứng dụng có thể phải xử lý nhiều trang; nếu driver gọi `all()` và giữ cả 10.000 row trong bộ nhớ, lợi ích tiết kiệm bộ nhớ client của paging phần lớn biến mất.

Bài này thuộc chương **Tối ưu truy vấn** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trọng tâm là cách chọn `LIMIT`, page size và mô hình tiêu thụ kết quả cho ứng dụng Java trong cluster phân tán, đồng thời tôn trọng replication, compaction, consistency và chi phí đọc dữ liệu.

## 2. Page size và LIMIT khác nhau ở đâu?

### 2.1. Bảng so sánh cốt lõi

| Khía cạnh | CQL `LIMIT` | Driver page size |
|---|---|---|
| Đặt tại đâu? | Bên trong câu `SELECT` | Thông số của statement/driver hoặc cấu hình driver |
| Mục đích | Chặn **số row kết quả tối đa** | Phân chia kết quả thành nhiều trang |
| Phạm vi | Toàn bộ một lần thực thi truy vấn | Mỗi lần lấy trang |
| Ví dụ | `LIMIT 500` | `setPageSize(100)` |
| Nếu kết quả có 500 row | Tối đa 500 row được trả | Có thể cần khoảng 5 trang, tùy kích thước và giới hạn khác |
| Có làm truy vấn lọc rộng trở thành hiệu quả? | **Không** | **Không** |
| Có đảm bảo lượng RAM theo MB? | **Không**: row có thể rất lớn | **Không**: số row không phản ánh bytes |
| Có thể khiến client giữ mọi kết quả? | Có, nếu code thu thập toàn bộ | Có, nếu code gọi `all()`/`collect` tất cả các trang |

### 2.2. Ba trường hợp rất khác nhau

Giả sử truy vấn chỉ nhắm tới một partition và có 20.000 row phù hợp.

**Trường hợp A: `LIMIT 50`, page size = 500**

Truy vấn trả tối đa 50 row. Thông thường chỉ cần một trang vì giới hạn kết quả nhỏ hơn page size; đây không phải bảo đảm rằng server chỉ đọc đúng 50 entry nội bộ.

**Trường hợp B: `LIMIT 1000`, page size = 200**

Truy vấn trả tối đa 1.000 row, được đưa về qua nhiều trang. Trong mô hình lý tưởng có 5 trang, mỗi trang 200 row; thực tế có thể khác do giới hạn kích thước trang tính theo byte, kích thước row, xử lý tombstone và các điều kiện runtime.

**Trường hợp C: không có `LIMIT`, page size = 200**

Server có thể tiếp tục cung cấp các trang cho tới khi hết tập kết quả hoặc client dừng tiêu thụ. **Page size 200 không có nghĩa tổng truy vấn chỉ trả tối đa 200 row**.

### 2.3. Hình dung dòng dữ liệu phân trang

~~~mermaid
sequenceDiagram
    participant A as Java service
    participant D as Cassandra Driver
    participant C as Coordinator
    participant R as Replica
    A->>D: SELECT ... LIMIT 1000, pageSize=200
    D->>C: Request trang đầu
    C->>R: Đọc dữ liệu phù hợp
    R-->>C: Kết quả đọc
    C-->>D: Trang 1 + paging state
    D-->>A: Rows của trang 1
    Note over A: Xử lý từng row; không bắt buộc giữ tất cả
    A->>D: Tiếp tục lặp kết quả
    D->>C: Request trang 2 với paging state
    C-->>D: Trang 2 + paging state
    D-->>A: Rows của trang 2
    Note over A,D: Lặp đến LIMIT hoặc hết kết quả
~~~

Sơ đồ mô tả luồng logic. Driver đồng bộ có thể **tự động lấy trang kế tiếp khi iterator cần**; với API bất đồng bộ, ứng dụng thường quyết định khi nào gọi `fetchNextPage()`.

## 3. `LIMIT` thực sự giới hạn điều gì?

### 3.1. Giới hạn kết quả, không bảo đảm giới hạn I/O

Bảng telemetry:

~~~cql
-- Giả sử keyspace telemetry đã tồn tại.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Partition key là **`(device_id, event_day)`**, clustering key là `event_time`. Truy vấn lấy 50 sự kiện mới nhất trong một ngày:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Đây là mẫu truy vấn có phạm vi tốt vì đầy đủ partition key và dữ liệu được sắp theo clustering order để lấy sự kiện mới nhất. Tuy vậy, **`LIMIT 50` chỉ giới hạn số row sống được trả về**, không bắt storage engine chỉ phải kiểm tra 50 bản ghi trên đĩa.

Trong partition có nhiều SSTable và tombstone, Cassandra có thể đọc/merge nhiều entry cũ, bỏ qua row đã xóa hoặc đã hết TTL trước khi thu được 50 row hợp lệ. Vì thế **`LIMIT` không chữa được tombstone-heavy read**.

### 3.2. `LIMIT` không thay WHERE theo partition key

Xét ví dụ không hiệu quả:

~~~cql
-- Minh họa anti-pattern; không dùng cho API production mặc định.
SELECT device_id, event_day, event_time, value
FROM telemetry.events_by_device_day
WHERE value > 80
LIMIT 50
ALLOW FILTERING;
~~~

Ở đây server có thể cần duyệt nhiều partition để tìm 50 row khớp điều kiện. Page size nhỏ và `LIMIT 50` không loại bỏ nhu cầu tìm kiếm trên phạm vi rộng.

Nếu cần tra theo `value` hoặc theo một chiều truy vấn khác, hãy **thiết kế bảng theo truy vấn**, cân nhắc data duplication có kiểm soát, hoặc đánh giá cơ chế index/search phù hợp với phiên bản và workload. Không dùng `ALLOW FILTERING` như giải pháp tối ưu chi phí đọc.

### 3.3. `LIMIT` không phải phân trang theo offset

Một số hệ SQL hỗ trợ:

~~~sql
SELECT ... LIMIT 100 OFFSET 5000;
~~~

Đây **không phải cách phân trang CQL tương đương**. Cassandra không cung cấp `OFFSET` SQL phổ thông để truy cập tùy ý “trang thứ 50” của một tập kết quả lớn.

Đối với Cassandra, có hai hướng chủ đạo:

- **Paging state**: tiếp tục cùng một truy vấn từ vị trí driver/server cung cấp.
- **Keyset/range pagination** theo clustering key: API truy vấn dữ liệu sau/before một mốc khóa đã biết, phù hợp khi cần điều hướng có thứ tự ổn định và chủ động quản lý cursor.

Không cố mô phỏng `OFFSET` bằng cách đọc bỏ 5.000 row ở client cho mỗi request: số row bỏ qua vẫn tiêu tốn network, CPU và I/O.

## 4. Page size thực sự được áp dụng như thế nào?

### 4.1. Page size thường là mục tiêu số row, không phải hạn mức bytes

Với Java Driver 4.x, có thể đặt:

~~~java
BoundStatement statement = prepared.bind(deviceId, eventDay)
    .setPageSize(200);
~~~

Đây là yêu cầu driver lấy trang với kích thước mục tiêu 200 row. Tuy nhiên:

1. Một row có thể chứa blob/collection lớn, nên 200 row có thể tương ứng hàng MB.
2. Cassandra còn có giới hạn và guardrail về kích thước thông điệp/trang, tùy phiên bản và cấu hình.
3. Một trang có thể chứa **ít hơn** số row mục tiêu; việc thiếu 200 row không đồng nghĩa kết quả đã hết.
4. Khi có tombstone, size boundary hoặc các giới hạn server, lượng công việc thực tế có thể lớn hơn lượng dữ liệu trả về.

**Không dùng page size như một RAM quota cứng.** Cần đo **bytes/page** và số page/second, không chỉ row count.

### 4.2. Cách chọn page size theo đặc tính row

| Loại dữ liệu / truy vấn | Rủi ro nếu page quá lớn | Cân nhắc |
|---|---|---|
| Row nhỏ, vài cột scalar | Nhiều row mỗi trang, buffer và allocation tăng theo concurrency | Có thể thử page tương đối lớn, đo bytes và latency |
| Row có blob/collection lớn | Một page có thể chứa nhiều MB | Bắt đầu page nhỏ và giới hạn kích thước row/data model |
| Partition rất rộng | Trang lớn kéo dữ liệu dài, server scan hoặc client memory tăng | Giới hạn clustering range và cân nhắc bucketing |
| Multi-partition/range scan | Nhiều replica/partition, tổng tập kết quả khó đoán | Giới hạn scope và concurrency, đặt stop condition |
| UI “xem thêm 20 mục” | Fetch 1.000 row dù user chỉ xem 20 gây lãng phí | Đồng bộ page size với nhu cầu UI hoặc chọn keyset |
| Batch export | Page nhỏ gây nhiều round-trip; page lớn gây áp lực memory | Thử nhiều kích cỡ, ghi kết quả và giữ streaming/bounded buffer |

Không có một giá trị page size tối ưu cho tất cả bảng. Một bài hướng dẫn không thể thay benchmark đối với row size, network RTT, CL, concurrency và RAM thực tế.

### 4.3. Quá nhỏ cũng có chi phí

Nếu cần đọc 10.000 row và mỗi trang chỉ có 10 row, về lý thuyết cần khoảng 1.000 lần trao đổi trang. Mỗi lượt có chi phí request, coordinator, network round trip, parsing và iterator/async scheduling.

Page size rất lớn giảm số vòng trao đổi nhưng có thể tăng bytes/message, thời gian phản hồi trang đầu, CPU, heap/GC và nghẽn network. Mục tiêu không phải **page càng nhỏ càng tốt**, mà là **cân bằng thời gian trả kết quả đầu, throughput toàn bộ và memory peak**.

### 4.4. Page size không thay đổi write batch

Page size áp dụng cho **phân trang kết quả của SELECT**. Nó không giới hạn số mutation trong `BEGIN BATCH`, không chia một ghi blob lớn thành nhiều phần và không biến batch nhiều partition thành thao tác rẻ.

Nếu bài toán là ghi hàng triệu row, cần kiểm soát **batching hợp lý, prepared statements, concurrency, backpressure và data model**, không chỉnh fetch/page size rồi kỳ vọng giảm bộ nhớ đường ghi.

## 5. Bộ nhớ phía server: một page có thể đắt hơn vẻ ngoài

### 5.1. Những khoản chi phí tồn tại khi đọc

Một request đọc có thể cần:

- **Buffer** cho dữ liệu đang đọc từ SSTable, index và chunk đã nén/giải nén.
- **Iterator, merge state** khi một partition xuất hiện trên nhiều SSTable.
- Xử lý **tombstone** và TTL; có thể đọc nhiều row bị loại để tạo một trang có ít row sống.
- **Memory/serialization buffer** để tạo phản hồi CQL và gửi qua network.
- **Request concurrency**, queues, CPU và băng thông đĩa cho nhiều request song song.
- Các hoạt động nền như **compaction, repair, streaming** cùng tranh CPU/I/O.

Page size giảm số row dự kiến phải gửi trong một lần đáp ứng nhưng **không đảm bảo peak RAM phía server tỉ lệ đúng với số row**, và không ngăn một partition cực lớn hoặc collection lớn gây áp lực lưu trữ.

### 5.2. Tính toán minh họa theo lượng byte

Giả sử một row sau serialization có trung bình **4 KiB**, chưa cộng overhead khác.

| Page size | Dữ liệu payload ước tính mỗi trang | 120 trang/request đồng thời (payload lý tưởng) |
|---:|---:|---:|
| 100 row | 400 KiB ≈ 0,39 MiB | ≈ 46,9 MiB |
| 200 row | 800 KiB ≈ 0,78 MiB | ≈ 93,8 MiB |
| 1.000 row | 4.000 KiB ≈ 3,91 MiB | ≈ 468,8 MiB |
| 2.000 row | 8.000 KiB ≈ 7,81 MiB | ≈ 937,5 MiB |

Con số chỉ minh họa **payload đang đồng thời hiện hữu**, không phải heap thực tế Cassandra hoặc Java. Overhead do object, buffer, compression, codec, GC, metadata, các page được prefetch, request queue và số request song song có thể làm mức sử dụng khác đáng kể. Không suy luận mọi request đều giữ trọn một page cùng thời điểm.

### 5.3. Concurrency và page size phải được điều chỉnh cùng nhau

Một ứng dụng không chỉ có “một request đọc”. Nếu 100 HTTP request cùng chạy và mỗi request tự tải nhiều page, bytes đang được xử lý có thể tăng theo số request/phần dữ liệu đang in-flight.

Mô hình gần đúng để đặt câu hỏi:

~~~text
Page payload đang xử lý (ước tính)
≈ active_page_count × avg_serialized_bytes_per_page

Client retained results (ước tính)
≈ số row đã giữ lại × avg_in_memory_bytes_per_row

Peak memory chịu ảnh hưởng cả hai, cộng driver buffers,
application objects, cache, GC và công việc ngoài Cassandra.
~~~

**`avg_serialized_bytes_per_row` và `avg_in_memory_bytes_per_row` không bằng nhau.** Java object có header, tham chiếu, collection và vật thể trung gian; dữ liệu đã giải mã có thể chiếm nhiều hơn payload trên mạng.

Vì vậy nên đo đồng thời:

- In-flight requests và số page đang xử lý.
- Bytes trả về trên mỗi request/page.
- Heap used, GC pause, allocation rate ở Java.
- Heap/off-heap/disk I/O và read latency trên Cassandra.
- Client timeout, backpressure và p95/p99 end-to-end.

## 6. Bộ nhớ phía Java: tự động paging không đồng nghĩa tự động stream toàn bộ

### 6.1. Đồng bộ: `ResultSet` có thể lấy trang tiếp theo khi lặp

Java Driver 4.x cung cấp `ResultSet` cho đồng bộ. Driver nhận trang đầu và có thể tự lấy trang kế tiếp khi vòng lặp cần thêm row.

**Cách xử lý gia tăng, không giữ toàn bộ row:**

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.UUID;

// session được khởi tạo/quản lý bên ngoài đoạn code minh họa.
PreparedStatement ps = session.prepare(
    "SELECT event_time, value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 500"
);

BoundStatement statement = ps.bind(
        UUID.fromString("11111111-1111-1111-1111-111111111111"),
        LocalDate.of(2026, 11, 21))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

ResultSet resultSet = session.execute(statement);
int count = 0;

for (Row row : resultSet) {
    // Xử lý từng row ngay, không gom vào List lớn.
    recordMetric(row.getInstant("event_time"),
                 row.getDouble("value"));
    count++;
}

System.out.println("Processed " + count + " rows");
~~~

Ở đây:

- `LIMIT 500` bảo đảm truy vấn trả tối đa 500 row.
- `setPageSize(100)` yêu cầu mục tiêu 100 row mỗi trang; khoảng năm trang trong trường hợp lý tưởng.
- Vòng lặp chỉ giữ row đang xử lý và buffer nội bộ của driver theo hành vi của phiên bản; **không cố tích lũy 500 đối tượng Row trong một List**.
- `recordMetric` là hàm xử lý giả định; nó phải tránh giữ toàn bộ dữ liệu hoặc block quá lâu.
- Vòng lặp có thể gây fetch trang kế tiếp, vì vậy tổng thời gian vòng lặp **khác** latency của lời gọi `session.execute(statement)` ban đầu.

### 6.2. Anti-pattern: `all()` biến truy vấn phân trang thành tập kết quả giữ trong RAM

Đoạn này nguy hiểm nếu không có giới hạn kết quả nhỏ:

~~~java
ResultSet resultSet = session.execute(statement);

// Cẩn thận: có thể fetch hết các trang và gom mọi row còn lại.
List<Row> allRows = resultSet.all();
~~~

Khi truy vấn không có `LIMIT` hoặc giới hạn rất lớn, `all()` có thể tạo List rất lớn, tăng object allocations, GC pause và nguy cơ `OutOfMemoryError`.

**Page size vẫn có tác dụng ở đường truyền**, nhưng client lại chủ động **thu thập kết quả**. Không có gì ngăn 50.000 row từ nhiều trang cùng nằm trong Java heap.

Nếu nghiệp vụ thật sự cần toàn bộ dữ liệu để sắp xếp/tổng hợp, hãy hỏi liệu phép tính có thể:

- Được mô hình hóa theo truy vấn và pre-aggregate trước.
- Xử lý streaming thành từng phần mà không giữ row cũ.
- Ghi từng nhóm ra sink có backpressure.
- Chạy dưới dạng job riêng với giới hạn concurrency và memory.

### 6.3. `getAvailableWithoutFetching()` không phải tổng số row

`ResultSet.getAvailableWithoutFetching()` có thể cho biết số row đang sẵn có ở client mà không phải fetch thêm; `isFullyFetched()` cho biết liệu driver đã nhận đầy đủ các trang của query chưa.

Không nhầm các API này với **`COUNT(*)`** hay tổng số row của query. Khi một trang đã tiêu thụ hết, vẫn có thể có trang kế tiếp; số row đang available bằng 0 **không có nghĩa truy vấn đã hoàn tất**.

## 7. Bất đồng bộ: dùng `AsyncResultSet` để kiểm soát nhịp lấy trang

Trong Java Driver 4.x, `executeAsync(statement)` trả về `CompletionStage<AsyncResultSet>`. `AsyncResultSet.currentPage()` cung cấp các row của trang hiện tại; `hasMorePages()` cho biết còn trang; `fetchNextPage()` yêu cầu trang tiếp.

Ví dụ **xử lý từng trang một**, không gửi đồng thời hàng trăm yêu cầu fetch:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class PagedEventReader {
    private final CqlSession session;
    private final PreparedStatement ps;

    public PagedEventReader(CqlSession session) {
        this.session = session;
        this.ps = session.prepare(
            "SELECT event_time, value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 500"
        );
    }

    public CompletionStage<Void> read(
            UUID deviceId, LocalDate day) {
        BoundStatement statement = ps.bind(deviceId, day)
            .setPageSize(100)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        return session.executeAsync(statement)
            .thenCompose(this::consumePage);
    }

    private CompletionStage<Void> consumePage(AsyncResultSet page) {
        for (Row row : page.currentPage()) {
            // Demo: xử lý nhỏ, không block thread driver.
            recordMetric(row.getInstant("event_time"),
                         row.getDouble("value"));
        }
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(null);
        }
        return page.fetchNextPage().thenCompose(this::consumePage);
    }

    private void recordMetric(java.time.Instant at, double value) {
        // Thay bằng thao tác nhanh hoặc pipeline có backpressure.
    }
}
~~~

**Giới hạn của ví dụ:** `recordMetric` ở đây là thao tác nhanh, đồng bộ và không chặn thread driver. Nếu ghi file, gọi HTTP hay thao tác lâu, phải chuyển sang executor/sink phù hợp và chỉ fetch tiếp sau khi phần xử lý trước đã hoàn tất. Không chạy I/O nặng trực tiếp trên callback thread của driver.

Các page vẫn được lấy **tuần tự**, tránh hiện tượng tự nạp tất cả các page trước khi downstream tiêu thụ. Với workload lớn, cần thêm cơ chế hủy request, deadline, giới hạn concurrency và kiểm soát lỗi `CompletionStage`.

### Khi nào chọn đồng bộ hay bất đồng bộ?

| Tiêu chí | Sync `ResultSet` | Async `AsyncResultSet` |
|---|---|---|
| Mã nguồn | Vòng lặp đơn giản | Pipeline/completion stage cần xử lý |
| Fetch trang | Driver tự fetch khi iterator cần | Ứng dụng chủ động `fetchNextPage()` |
| Blocking | Có thể chặn thread ứng dụng khi đợi trang | Không cần block thread ứng dụng trong lúc chờ |
| Backpressure | Tự nhiên nếu xử lý từng row tuần tự, nhưng chiếm thread | Có thể gắn với trạng thái xử lý downstream rõ ràng |
| Rủi ro | `all()`, thread pool quá lớn, chờ I/O lâu | Fetch quá nhiều trang cùng lúc, callback block, pipeline giữ dữ liệu |

## 8. Paging state là cursor tiếp tục, không phải số trang

### 8.1. Khái niệm

Khi kết quả chưa hết, server/driver có thể cung cấp **paging state** để request tiếp theo tiếp tục từ vị trí phù hợp. Token này là dữ liệu **opaque** phục vụ giao thức phân trang: không nên tự diễn giải nó thành token ring, offset hay timestamp.

Nếu một API HTTP muốn trả 50 row mỗi lần gọi, nó có thể phải lưu hoặc chuyển một continuation token được tạo từ paging state. Tuy nhiên cần:

- Gắn token với **cùng truy vấn, cùng bind values và bối cảnh dữ liệu phù hợp**.
- **Validate** token trước khi sử dụng; không chấp nhận bytes tùy ý từ người dùng như một paging state đáng tin.
- Có chính sách bảo vệ token khi truyền ra ngoài client (ký/HMAC, mã hóa hoặc quản lý phía server tùy thiết kế).
- Dùng TTL/expiration và xử lý token sai/hết hiệu lực có kiểm soát.
- Không cam kết token sẽ tương thích vĩnh viễn qua thay đổi phiên bản, query shape hoặc topology.
- Không tùy tiện dùng state của truy vấn A cho truy vấn B hay thay page size mà không kiểm tra cơ chế/driver tương ứng.

**Paging state không phải primary key của một row**, cũng không phải cách điều hướng ngẫu nhiên tới “trang 100” mà không đi qua các trang trước đó.

### 8.2. Paging không tạo snapshot cố định giữa các request

Các trang có thể được lấy ở **những thời điểm khác nhau**. Trong lúc phân trang, những mutation mới, DELETE hoặc TTL có thể thay đổi tập dữ liệu. Vì vậy không mặc định các page là một snapshot giao dịch duy nhất.

Hệ quả có thể gồm row xuất hiện/biến mất giữa các trang hoặc số lượng trang thay đổi, tùy thứ tự clustering, timestamp và mutation. Với API yêu cầu hành trình phân trang ổn định:

- Chọn truy vấn theo **partition key và clustering key** có thứ tự rõ ràng.
- Cân nhắc **keyset pagination** dựa trên cursor nghiệp vụ (ví dụ event timestamp kèm khóa xác định duy nhất), nếu phù hợp.
- Đặt ranh giới thời gian/phiên dữ liệu có thể chấp nhận được, hoặc dùng snapshot/export ở hệ thống chuyên dụng nếu cần nhất quán giao dịch mạnh.
- Kiểm tra deduplication khi pagination trải qua dữ liệu thay đổi liên tục.

### 8.3. Keyset pagination theo clustering key

Với bảng `PRIMARY KEY ((device_id, event_day), event_time)` và thứ tự `event_time DESC`, lần đầu:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Lần tiếp theo có thể dùng **mốc `event_time` cuối đã trả**:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 50;
~~~

Mốc `10:00:00Z` là ví dụ; ứng dụng cần lấy chính xác clustering key cuối của trang trước để tránh lặp. Kiểu khóa clustering phải đủ biểu diễn thứ tự và tính duy nhất mà sản phẩm cần; nếu hai event có thể cùng thời điểm, thiết kế clustering key bổ sung phù hợp.

**Keyset pagination và server paging state giải quyết những mục tiêu liên quan nhưng khác nhau**. Keyset dễ gắn vào nghiệp vụ “xem mục trước đó” và điều kiện WHERE; paging state tiếp tục việc thực thi CQL theo cơ chế driver/server. Cần kiểm thử khi dữ liệu được ghi/xóa đồng thời.

## 9. Kiểm soát số lượng row ở nhiều partition

### 9.1. Global LIMIT và PER PARTITION LIMIT

Với truy vấn quét qua nhiều partition, `LIMIT` chung giới hạn **tổng row trả về**, không đảm bảo mỗi partition chỉ đóng góp vài row. Trong những loại truy vấn được Cassandra hỗ trợ, `PER PARTITION LIMIT` giới hạn số row **trong mỗi partition**, còn `LIMIT` giới hạn toàn bộ kết quả.

Ví dụ **minh họa cú pháp trên bảng nhiều partition**:

~~~cql
SELECT device_id, event_day, event_time, value
FROM telemetry.events_by_device_day
PER PARTITION LIMIT 10
LIMIT 100;
~~~

Mỗi partition có thể đóng góp tối đa 10 row, tổng kết quả tối đa 100 row. Nhưng vì truy vấn **không có WHERE giới hạn partition key**, server vẫn phải tiến hành một phạm vi quét rộng để tìm các partition/row phù hợp. Đây là ví dụ giải thích semantics, **không phải truy vấn production nên áp dụng làm mặc định**.

`PER PARTITION LIMIT` được hỗ trợ theo cú pháp/phiên bản Cassandra tương ứng; hãy kiểm tra khi sử dụng với điều kiện `IN`, `ORDER BY` hoặc các hạn chế truy vấn đặc biệt.

### 9.2. Đừng dùng một query lớn để xuất toàn bộ bảng tương tác

Nếu muốn xuất dữ liệu hàng triệu partition, một query không WHERE chạy lâu cùng auto-paging từ Java có thể:

- Tạo tải read I/O đáng kể trên cluster.
- Tranh tài nguyên với traffic online và compaction.
- Gây tắc nghẽn driver, network và bộ nhớ ở sink.
- Nhận dữ liệu không đồng nhất về thời điểm khi quá trình kéo dài.

Với batch export/backup hoặc migration, ưu tiên công cụ/quy trình phù hợp, chia phạm vi token/partition có kiểm soát và giữ concurrency nhỏ có giám sát. **Paging không biến full scan thành truy vấn rẻ**.

## 10. Page size và consistency level: đừng nhầm hiệu năng với tính đúng

Page size chủ yếu điều khiển lượng kết quả mỗi lần fetch; consistency level điều khiển yêu cầu phản hồi của replica.

| Cấu hình | Nó thay đổi gì? | Không thay đổi gì? |
|---|---|---|
| `LIMIT 50` | Tối đa 50 row của query | Không tự chọn replica hoặc giảm CL |
| `setPageSize(50)` | Mục tiêu 50 row mỗi trang | Không giới hạn tổng số row nếu không có LIMIT |
| `LOCAL_ONE` / `ONE` | Điều kiện read ACK nhỏ hơn | Không bảo đảm dữ liệu mới nhất như quorum trong mọi tình huống |
| `LOCAL_QUORUM` | Cần quorum trong DC cục bộ | Không làm một query full-scan thành point lookup |
| `QUORUM` | Quorum theo RF phù hợp của keyspace | Không thay page size hay hạn mức bộ nhớ client |

Các trang của một query có thể đi qua các **request mạng riêng**, với paging state và yêu cầu consistency đã đặt; không coi toàn bộ chuỗi trang là một giao dịch snapshot duy nhất.

Không hạ CL từ `LOCAL_QUORUM` xuống `ONE` chỉ vì page fetch chậm, trừ khi thiết kế nghiệp vụ cho phép thay đổi bảo đảm nhất quán đọc. Tối ưu page size phải được phân tích cùng topology, RF, read latency và khả năng chịu lỗi, **nhưng không thay cho các quyết định đó**.

## 11. Tối ưu throughput mà không làm p99 hoặc RAM xấu đi

### 11.1. Thử nghiệm có kiểm soát

Chọn một query shape đại diện cho ứng dụng, cùng dataset, CL, concurrency và cách xử lý kết quả. Thử một vài page size và đo cả **time to first page**, **total consume time**, **bytes/page**, CPU/RAM và p99.

Ví dụ mẫu số liệu **giả định**:

| Page size | Time to first page p95 | Tổng thời gian đọc 5.000 row | Heap peak ứng dụng | Nhận xét |
|---:|---:|---:|---:|---|
| 50 | 28 ms | 2.400 ms | 220 MiB | Nhiều lượt network |
| 200 | 34 ms | 900 ms | 255 MiB | Cân bằng cho workload này |
| 1.000 | 95 ms | 680 ms | 430 MiB | Nhanh tổng thể nhưng page đầu và RAM tăng |
| 5.000 | 320 ms | 650 ms | 900 MiB | RAM/GC có thể không chấp nhận được |

**Đây là số liệu tự đặt để minh họa phương pháp**, không phải kết quả benchmark của Cassandra hay driver. Một ứng dụng khác, row size khác hoặc network RTT khác có thể cho kết luận trái ngược.

Đừng chọn page size `5.000` chỉ vì throughput tổng nhanh nhất nếu API cần phản hồi trang đầu trong 100 ms hoặc service có heap hạn chế. Ngược lại, không chọn 50 row cho mọi job export khi tổng thời gian thực thi quan trọng hơn time to first page.

### 11.2. Khi nào tăng page size có hại?

- Heap/GC phía Java tăng theo page payload hoặc số request đồng thời.
- Server mất nhiều thời gian tạo response trang lớn; timeout và p99 tăng.
- Một response lớn gần giới hạn message/frame hoặc gây network burst.
- Lưu lượng của một client chiếm băng thông, ảnh hưởng query khác.
- Ứng dụng hiếm khi dùng hết page đầu (ví dụ user chỉ mở 20 row nhưng fetch 2.000).

### 11.3. Khi nào giảm page size có hại?

- Mỗi query phải thực hiện nhiều request fetch hơn.
- Network RTT cao, nhất là truy vấn qua datacenter xa.
- Coordinator và driver xử lý nhiều trang nhỏ, tăng overhead.
- Tổng thời gian export dài dù peak memory giảm.
- Downstream có thể giữ page liên tục do code vẫn `collect` tất cả row.

Mục tiêu là chọn **kích thước trang đáp ứng nhu cầu tiêu thụ thật**, không dùng một con số cứng cho toàn hệ thống.

## 12. Quan sát và chẩn đoán Cassandra khi paging chậm

Các lệnh dưới đây mang tính khởi đầu; tùy phiên bản, cú pháp và tên metric có thể thay đổi.

~~~bash
# Table metrics: read/write latency, SSTable và kích thước dữ liệu.
nodetool tablestats telemetry.events_by_device_day

# Histogram theo bảng, gồm SSTables per read/latency ở bản hỗ trợ.
nodetool tablehistograms telemetry events_by_device_day

# Histogram trên đường coordinator / proxy.
nodetool proxyhistograms

# Compaction I/O và pending tasks.
nodetool compactionstats

# Thread pool, queue và dropped messages.
nodetool tpstats

# Trạng thái node, DC và rack.
nodetool status
~~~

Cũng cần kiểm tra **Java Driver metrics** như request latency, in-flight requests, retry, timeouts và bytes received (nếu hệ thống instrument), cùng heap/GC của service.

### 12.1. Những tín hiệu thường đi cùng nhau

| Triệu chứng | Giả thuyết | Bước xác minh |
|---|---|---|
| Page size tăng, heap peak và GC tăng | Payload/page và retention của client quá lớn | Heap metrics, allocation, `all()`, concurrent requests |
| Page size nhỏ, total time chậm nhưng first page nhanh | Nhiều network round trips | Số pages/query, RTT, driver metrics |
| LIMIT nhỏ nhưng read latency vẫn lớn | Tombstone scan hoặc truy vấn thiếu partition key | CQL shape, tracing, SSTables per read |
| Client p99 cao, table-local p99 thấp | Driver queue/retries, coordinator, network | Driver metrics, proxyhistograms, network |
| Một partition đặc biệt chậm | Wide/hot partition, nhiều SSTable/TTL | Kích thước partition, compaction, tombstone |
| Tăng concurrency gây timeouts | Disk, CPU, heap hoặc connection pool bão hòa | In-flight count, load, dropped messages |
| Query không LIMIT làm service OOM | `all()` hoặc danh sách kết quả giữ trong RAM | Heap dump/quy trình an toàn, code review, giới hạn kết quả |
| Trả ít row hơn pageSize và còn next page | Byte boundary hoặc cơ chế paging server | Kiểm tra paging state/hasMorePages, row size |

**Không lấy average read latency để kết luận cả API ổn.** Cần theo dõi p50/p95/p99, timeout/error và good-request ratio của SLO. Nếu những request chậm nhất timeout và không đi vào histogram thành công, p99 có thể giảm giả.

### 12.2. Tracing có chọn lọc

~~~cql
TRACING ON;

SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
~~~

Tracing hỗ trợ xem một số bước coordinator/replica, nhưng có overhead; không bật toàn bộ production chỉ để kiểm tra page size. Phải đối chiếu trace với thời điểm tải, CL và node thực tế.

## 13. Runbook: tăng page size làm service Java hết RAM

Giả sử service đổi `setPageSize(200)` thành `setPageSize(5000)` để xuất sự kiện nhanh hơn. Một thời gian sau:

- Java heap tăng mạnh theo số job export đồng thời.
- p99 của endpoint tương tác tăng.
- GC pause và timeout xuất hiện.
- Cassandra vẫn trả request, nhưng application bắt đầu bị OOM.

**Bước 1 — Xác nhận thay đổi và phạm vi.** Kiểm tra release, query shape, page size thực tế, `LIMIT`, số job đồng thời, row size và thời điểm heap bắt đầu tăng.

**Bước 2 — Kiểm tra cách consume.** Tìm `resultSet.all()`, `collect(toList())`, accumulation qua nhiều page, hoặc queue không có giới hạn. Giảm page size mà vẫn gom toàn bộ row **có thể chỉ làm chậm OOM**, không giải quyết retention.

**Bước 3 — Đo payload và heap.** Ghi nhận bytes/page, số page đang in-flight, số object đang giữ, allocation, GC pause và timeout. Kiểm tra blobs/collections bất thường.

**Bước 4 — Khôi phục giới hạn an toàn.** Theo quy trình release/rollback, trở về page size đã được chứng minh ổn định; giới hạn concurrency và tách workload export khỏi traffic tương tác. Không tự tăng heap vô hạn hoặc đẩy gánh nặng sang Cassandra node.

**Bước 5 — Sửa thiết kế.** Chuyển sang xử lý tuần tự theo trang, tránh `all()`, áp dụng backpressure và stop condition. Nếu API chỉ cần trang UI 50 row, dùng `LIMIT` phù hợp hoặc keyset pagination thay vì SELECT không giới hạn.

**Bước 6 — Xác minh cả hai phía.** Đo client heap/GC, p99/timeout, network bytes, server read latency và compaction pressure. Coi thay đổi thành công khi **memory ổn định và SLO không suy giảm**, không chỉ vì job export hoàn thành nhanh.

## 14. Những hiểu nhầm thường gặp

| Nhận định | Đúng hay sai? | Lý do |
|---|---|---|
| “Page size 100 nghĩa là SELECT trả tối đa 100 row.” | **Sai** | Chỉ là mục tiêu mỗi trang; query có thể có nhiều trang |
| “LIMIT 100 luôn chỉ đọc 100 row ở disk.” | **Sai** | Tombstone, SSTable và lọc có thể khiến server đọc nhiều hơn |
| “LIMIT 1000 với page size 200 sẽ luôn chính xác 5 trang.” | **Sai** | Byte boundary và điều kiện runtime có thể làm số row/trang khác |
| “Dùng `all()` vẫn tiết kiệm heap vì driver paging.” | **Sai** | `all()` tích lũy các row còn lại thành List |
| “Page size là hạn mức MB của response.” | **Sai** | Row count khác byte count; một row có thể rất lớn |
| “Page size càng lớn càng nhanh ở mọi trường hợp.” | **Sai** | Có trade-off latency, RAM, network, server work |
| “Trang tiếp theo là snapshot cố định.” | **Không bảo đảm** | Mutation/TTL giữa các request có thể thay đổi kết quả |
| “Có thể nhảy tới trang 50 bằng OFFSET.” | **Không theo mô hình CQL phổ thông** | Dùng paging state hoặc keyset phù hợp |
| “LIMIT nhỏ chữa được ALLOW FILTERING.” | **Sai** | Phạm vi quét vẫn có thể rộng |
| “Chỉnh fetch size giúp batch INSERT bớt nặng.” | **Sai** | Paging thuộc đọc kết quả, không chia write batch |
| “Bảng đã có partition key nên page size không quan trọng.” | **Sai** | Một partition vẫn có thể lớn và mỗi row có payload lớn |
| “Tăng heap của app là đủ.” | **Chưa chắc** | Server I/O, network, memory và concurrency vẫn giới hạn |

## 15. Bài tập thực hành và tự kiểm tra

### Câu 1 — Phân biệt hai giới hạn

Query có `LIMIT 750`, Java Driver có page size 150. Có tối đa bao nhiêu row và khoảng bao nhiêu trang trong trường hợp lý tưởng?

**Đáp án:** Tối đa 750 row, khoảng 5 trang nếu mỗi trang đủ 150 row. Số trang thực tế có thể khác do giới hạn bytes, điều kiện server và dữ liệu.

### Câu 2 — Không LIMIT nhưng page nhỏ

Một client SELECT không có LIMIT với page size 100, sau đó gọi `all()`. Vì sao Java vẫn có thể OOM?

**Đáp án:** Driver có thể tự fetch toàn bộ các trang rồi `all()` giữ tất cả row trong một List. Page size không giới hạn tổng số row/bytes.

### Câu 3 — Tính payload đang xử lý

Mỗi row trung bình 4 KiB serialized, page size là 1.000 và 120 page đang đồng thời hiện hữu. Payload thô khoảng bao nhiêu MiB?

**Đáp án:** `1000 × 4 KiB × 120 = 480000 KiB ≈ 468,75 MiB`, chưa gồm metadata, object Java, buffer và các tác vụ khác.

### Câu 4 — Tombstone

Query có đủ partition key và `LIMIT 20` nhưng phải quét 8.000 tombstone trước khi có đủ row. Hãy nêu hai hướng kiểm tra.

**Đáp án:** Xem tombstone/TTL và dữ liệu cũ trải trên nhiều SSTable, compaction strategy/backlog, độ rộng clustering range và mô hình retention/bucket. Không chỉ tăng page size.

### Câu 5 — SELECT cho UI

UI hiển thị 20 sự kiện và có nút “xem thêm”. Đội backend chọn page size 5.000 và SELECT không LIMIT. Có rủi ro gì?

**Đáp án:** Fetch nhiều dữ liệu mà người dùng chưa xem, tốn RAM/network và thời gian trang đầu; nếu giữ mọi row còn gây OOM. Cần đặt query limit/page size hợp nhu cầu hoặc dùng keyset/paging token có kiểm soát.

### Câu 6 — Keyset và paging state

Paging state có phải số trang để lưu lâu dài và cho phép đổi WHERE hoặc đổi partition key tùy ý khi tiếp tục?

**Đáp án:** Không. Nó là token opaque cho việc tiếp tục một truy vấn tương thích, không phải offset. Phải xác thực, bảo vệ và ràng buộc với query/parameters tương ứng.

### Câu 7 — Đồng bộ và bất đồng bộ

Với `AsyncResultSet`, tại sao không tự gọi `fetchNextPage()` hàng loạt trước khi xử lý trang hiện tại?

**Đáp án:** Như vậy có thể giữ nhiều page/buffer cùng lúc, mất backpressure và tăng in-flight network/memory. Nên fetch theo khả năng consume của downstream.

### Câu 8 — Byte size khác row count

Hai bảng có cùng page size 200; một bảng row 200 B, bảng kia row 100 KiB. Liệu peak memory sẽ tương tự nhau?

**Đáp án:** Không. Payload lý tưởng khác nhau hàng trăm lần, chưa tính overhead. Page size phải được đánh giá cùng kích thước dữ liệu thực tế và số request đồng thời.

### Câu 9 — Cấu hình CL

Dịch vụ đọc `LOCAL_QUORUM` bị chậm khi network nội bộ có vấn đề. Có nên chuyển `ONE` ngay để giảm timeout?

**Đáp án:** Đó là thay đổi bảo đảm consistency, không chỉ tối ưu page size. Cần phân tích yêu cầu nghiệp vụ, RF/topology và nguyên nhân latency trước khi đổi.

### Câu 10 — Khi benchmark cho kết quả trái ngược

Page size 2.000 cho total consume time nhanh hơn page size 200 nhưng p99 time to first page và heap peak xấu hơn. Chọn cái nào?

**Đáp án:** Tùy mục tiêu. Endpoint tương tác có thể ưu tiên 200 vì latency và RAM; batch export được phân tách, có capacity và SLO riêng có thể thử 2.000. Quyết định dựa trên số liệu và giới hạn tài nguyên, không chỉ throughput.

## 16. Tổng kết

Trong Apache Cassandra:

1. **`LIMIT` giới hạn số row trả về của truy vấn; page size giới hạn mục tiêu số row trong mỗi trang.** Hai thiết lập này phục vụ hai mục đích khác nhau.
2. **LIMIT và page size không thay thế mô hình dữ liệu theo partition key**. Query thiếu khóa hoặc tombstone-heavy có thể vẫn đắt dù chỉ trả ít row.
3. **Không mặc định page size là giới hạn bộ nhớ**: row size, blob, số request đồng thời và cách client giữ kết quả quyết định peak heap.
4. **Java Driver sync và async đều có paging**, nhưng `ResultSet.all()`, collector không giới hạn hoặc prefetch quá nhiều có thể phá vỡ mục tiêu dùng ít RAM.
5. **Paging state là cursor opaque**, không phải OFFSET hay snapshot giao dịch bền vững; keyset pagination phù hợp với một số UX truy vấn có thứ tự.
6. **Chọn page size bằng benchmark có kiểm soát**, đo time to first page, total consume time, p99, bytes/page, GC, timeouts và tải server.
7. **Giữ backpressure và concurrency bounded**, nhất là với export, scan và các API cần đi qua nhiều trang.
8. **Tách performance khỏi consistency**: thay page size không thay RF/CL; hạ CL để chữa chậm là quyết định khác, có tác động tới tính đúng.

Câu hỏi đúng khi tối ưu không chỉ là “nên đặt page size bao nhiêu?”, mà là **“mỗi trang chứa bao nhiêu byte, bao nhiêu trang/request, bao nhiêu request đồng thời, client giữ dữ liệu bao lâu và server phải đọc bao nhiêu để tạo ra trang đó?”**. Trả lời được những câu hỏi này sẽ giúp tối ưu truy vấn Cassandra và kết nối Java mà không đánh đổi p99, độ ổn định bộ nhớ hay độ tin cậy dữ liệu.
