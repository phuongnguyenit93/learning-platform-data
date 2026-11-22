# executeAsync, CompletionStage và AsyncResultSet

## 1. Một request HTTP cần dữ liệu Cassandra nhưng không được giữ thread chờ

Giả sử ứng dụng Java nhận hàng nghìn request đọc lịch sử thiết bị mỗi giây. Mỗi request cần lấy các sự kiện từ **Apache Cassandra** bằng một `SELECT` theo partition key và khoảng thời gian. Bản đầu dùng `session.execute(statement)`, sau đó duyệt `ResultSet`. Khi tăng traffic, nhiều thread ứng dụng bị giữ trong lúc chờ network và replica trả kết quả.

Nhóm chuyển sang:

~~~java
CompletionStage<AsyncResultSet> pending =
    session.executeAsync(statement);
~~~

Đây là bước đầu của xử lý **bất đồng bộ**, nhưng chưa tự giải quyết hết vấn đề. Nếu code lập tức gọi `pending.toCompletableFuture().join()`, thread vẫn bị chặn; nếu chỉ duyệt `currentPage()` rồi trả về danh sách, API có thể **bỏ sót các trang kế tiếp**; nếu phát 100.000 `executeAsync` cùng lúc mà không admission/backpressure, ứng dụng và Cassandra vẫn có thể quá tải.

Bài thuộc chương **Bất đồng bộ và reactive** trong mô-đun Cassandra. Chủ đề trực tiếp là **`executeAsync`, `CompletionStage` và `AsyncResultSet`** trong Apache Cassandra Java Driver 4.x. Nội dung kết nối CQL, partition/clustering key, replication, consistency level, timeout, xử lý lỗi và năng lực vận hành thực tế.

**Sau bài này, bạn cần làm được:**

1. Giải thích đường đi của một `executeAsync` và sự khác nhau giữa non-blocking, concurrent và reactive.
2. Dùng `CompletionStage` với `thenApply`, `thenCompose`, `whenComplete`, `exceptionally` và `handle` đúng ngữ nghĩa.
3. Đọc **trang đầu** bằng `AsyncResultSet.currentPage()`, nhận biết `hasMorePages()` và gọi `fetchNextPage()` mà không block callback.
4. Tạo chuỗi đọc nhiều trang có **giới hạn trang/hàng, deadline và concurrency**, không giữ tất cả dữ liệu trong heap.
5. Viết đường ghi async có **admission control, khóa chính ổn định và xử lý timeout không rõ kết quả**.
6. Phân biệt lỗi client, Cassandra coordinator, replica, mapping và vấn đề data model.
7. Đo p95/p99, in-flight, queue, số page/byte, GC, retries và hiệu quả under load; nhận diện anti-pattern.

**Giới hạn phiên bản:** ví dụ sử dụng API `com.datastax.oss.driver.api.*` của **Java Driver 4.x** và Java 17 trong lab. Tên option, callback behavior, API reactive, exception và policy có thể khác theo minor version/bản phân phối; kiểm tra tài liệu đúng bộ driver/JDK/Cassandra được triển khai. Không dùng mã lab không có authentication/TLS như cấu hình production.

## 2. `execute` và `executeAsync`: giống CQL, khác cách Java chờ

### 2.1. Đường chạy chung

~~~mermaid
sequenceDiagram
    participant API as Java HTTP handler
    participant Driver as CqlSession / Driver
    participant Coord as Cassandra coordinator
    participant Replica as Natural replicas
    API->>Driver: executeAsync(boundStatement)
    Driver-->>API: CompletionStage<AsyncResultSet> (chưa có dữ liệu)
    Driver->>Coord: CQL request
    Coord->>Replica: Read/write theo token, RF và CL
    Replica-->>Coord: Đủ phản hồi hoặc lỗi
    Coord-->>Driver: Response / page đầu tiên
    Driver-->>API: Complete stage với AsyncResultSet
    API->>API: currentPage(), xử lý row
    opt Còn trang và ứng dụng cần tiếp
        API->>Driver: fetchNextPage()
        Driver->>Coord: Paging request kế tiếp
        Coord-->>Driver: Trang kế
        Driver-->>API: Complete stage tiếp
    end
~~~

**Điều không thay đổi:** cùng câu CQL, partition key, clustering range, consistency level, coordinator và replica. Async không biến một truy vấn `ALLOW FILTERING` thành partition lookup rẻ, không làm SSTable/compaction nhanh hơn và không làm quorum nhỏ đi.

| API | Kiểu kết quả | Thread gọi phải chờ dữ liệu? | Điểm dễ nhầm |
| --- | --- | --- | --- |
| `session.execute(statement)` | `ResultSet` | Có, cho tới khi nhận được kết quả theo semantics sync. | Duyệt `ResultSet` có thể chờ fetch các page kế tiếp. |
| `session.executeAsync(statement)` | `CompletionStage<AsyncResultSet>` | **Không cần chờ** nếu chỉ tạo stage và compose. | Stage hoàn tất thường là **một trang**, không phải toàn bộ tập dữ liệu. |
| `stage.toCompletableFuture().join()` | Giá trị đã hoàn tất hoặc ngoại lệ | **Có**, khi chưa hoàn tất. | Gọi trong request/event-loop/driver callback có thể gây nghẽn. |
| API reactive (nếu driver/runtime hỗ trợ) | Publisher/stream theo hợp đồng reactive tương ứng | Phụ thuộc subscription và demand. | Không đánh đồng một `CompletionStage` với Reactive Streams. |

### 2.2. Non-blocking không tự tạo thêm throughput

`executeAsync` giúp **thread Java không phải ngồi chờ I/O** trong khoảng Cassandra thực thi. Nhưng network connections, coordinator, replica, disk IOPS, tombstone scan, serialization và heap vẫn bị tiêu thụ. Khi backend đã bão hòa, tăng số futures có thể làm **latency, memory và error rate** cùng tăng.

Điều cần làm là **compose kết quả không block**, đồng thời giới hạn **lượng công việc được phép gửi**. Sự khác biệt giữa *không giữ thread chờ* và *không tốn tài nguyên* là một ý trọng tâm.

## 3. CQL lab: một partition có nhiều trang

### 3.1. Keyspace và bảng

Giả sử cluster lab có DC `dc1` với ít nhất ba full replicas, quyền tạo schema và các client được cấu hình tương ứng:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_async
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_async.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

- `(device_id, event_day)` là **partition key kép**: Cassandra hash khóa để chọn token và natural replicas; bucket ngày giúp hạn chế kích thước partition cho dữ liệu chuỗi thời gian.
- `event_time, event_id` là **clustering columns**: các hàng được sắp trong từng partition; ID phân biệt sự kiện cùng timestamp.
- `payload` có thể lớn; khi API chỉ cần timeline, **chọn ít cột hơn** sẽ giảm network và decode, bất kể sync hay async.
- `NetworkTopologyStrategy` với `dc1:3` và `LOCAL_QUORUM` cần **hai phản hồi replica trong dc1**; không có nghĩa mọi replica đã hội tụ tại cùng một thời điểm.

### 3.2. Dữ liệu thử nghiệm

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'HEARTBEAT', 'ok');

INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'TEMPERATURE', '21.6');

INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:02:00Z',
   123e4567-e89b-42d3-a456-426614174003, 'ALARM', 'high_temp');
~~~

`CONSISTENCY` là **lệnh của cqlsh**, không phải statement đưa thẳng vào Java Driver. Sau khi tạo ba hàng, có thể thử query:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

Trong Java, cấu hình **page size = 2** sẽ giúp nhìn thấy trường hợp trang đầu không chứa toàn bộ ba hàng (khi Cassandra/driver áp dụng paging theo giới hạn tương ứng). Page size là **mục tiêu số hàng mỗi page**, không phải trần byte tuyệt đối và không phải `LIMIT`.

## 4. Chuẩn bị Java Driver 4.x và một `CqlSession` dùng chung

### 4.1. Dependency minh họa

Ví dụ Maven dùng artifact Core Driver 4.x; **phiên bản dưới đây chỉ để minh họa, không có nghĩa mới nhất**:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-core</artifactId>
        <version>4.17.0</version>
    </dependency>
</dependencies>
~~~

Trong ứng dụng thật, đồng bộ driver core với các module mapper/metrics/reactive nếu dùng và kiểm tra **JDK, Cassandra version, security/TLS và native protocol** theo ma trận hỗ trợ của bản phát hành.

### 4.2. Session sống cùng service

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class AsyncSessionLifecycle {
    public static void main(String[] args) {
        // LAB: một CqlSession sống lâu cho logical cluster/identity.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            // Ứng dụng gọi nhiều executeAsync qua cùng session.
            // Đừng tạo session mới cho mỗi HTTP request hoặc mỗi page.
            System.out.println("Session ready for async operations");
        }
    }
}
~~~

`CqlSession` quản lý connections, topology, routing, prepared statements và các tài nguyên driver. Ứng dụng thông thường nên chia sẻ một session cho **một logical cluster/identity/cấu hình** trong vòng đời process và đóng khi shutdown có kiểm soát. **Đóng session khi một async request còn chạy** có thể khiến công việc chưa hoàn tất thất bại; service cần dừng nhận traffic, hoàn tất/drain các request trong deadline rồi mới đóng.

**Production:** bật TLS xác thực server, cấp CQL role ít quyền, dùng secret manager, contact points/local DC đúng, không hardcode password và không cho ứng dụng quyền JMX/OS không cần thiết. Các đoạn Java tiếp theo giả định **session đã được khởi tạo an toàn**.

### 4.3. Chuẩn bị query một lần

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class Queries {
    public static PreparedStatement prepareWindow(CqlSession session) {
        return session.prepare(
            "SELECT event_time, event_id, event_type " +
            "FROM telemetry_async.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");
    }
}
~~~

Trong service, giữ `PreparedStatement` và tái sử dụng với các `BoundStatement` được bind theo request. Ví dụ `prepareWindow` được gọi lúc startup, **không gọi lại mỗi request**. Khi đo benchmark async, tách cold-start/prepare khỏi request latency steady state.

## 5. `CompletionStage<T>`: một kết quả sẽ có trong tương lai

`CompletionStage<T>` mô tả một phép tính **có thể hoàn tất thành công với giá trị `T` hoặc thất bại với ngoại lệ**. `session.executeAsync(statement)` trả `CompletionStage<AsyncResultSet>`, cho phép xây pipeline xử lý tiếp khi trang trả về mà không chặn thread gọi.

~~~mermaid
flowchart LR
    A["executeAsync"] --> B["CompletionStage<AsyncResultSet>"]
    B --> C{"Stage đã hoàn tất?"}
    C -->|Thành công| D["thenApply / thenCompose"]
    C -->|Lỗi| E["exceptionally / handle / whenComplete"]
    D --> F["CompletionStage<Output>"]
    E --> F
~~~

### 5.1. Những phương thức quan trọng

| Phương thức | Vai trò | Bẫy thường gặp |
| --- | --- | --- |
| `thenApply(x -> y)` | Biến đổi **đồng bộ một giá trị** sau khi stage thành công, cho kết quả stage mới. | Gọi query async bên trong rồi trả về stage lồng nhau `CompletionStage<CompletionStage<T>>`. |
| `thenCompose(x -> nextStage)` | Ghép **một bước bất đồng bộ phụ thuộc kết quả bước trước**, làm phẳng stage. | Dùng `join()` thay vì compose sẽ block. |
| `thenCombine(other, (a,b) -> c)` | Kết hợp hai stage độc lập khi cả hai thành công. | Phát hai query không cần thiết hoặc vượt concurrency budget. |
| `whenComplete((value,error) -> ...)` | Quan sát kết quả/lỗi để metrics, cleanup; bình thường **giữ outcome gốc**. | Dùng nó như hàm “bắt lỗi rồi tự phục hồi” hoặc block trong callback. |
| `exceptionally(error -> fallback)` | Phục hồi **một giá trị thay thế** khi stage lỗi. | Trả danh sách rỗng với mọi lỗi, che `Unavailable` thành “không có dữ liệu”. |
| `handle((value,error) -> output)` | Xử lý cả hai trường hợp thành công/thất bại. | Nuốt ngoại lệ nếu return thành công vô điều kiện. |
| `toCompletableFuture()` | Chuyển sang đối tượng `CompletableFuture` cho các thao tác cần thiết. | Gọi `join/get` trong event loop hoặc callback sẽ chặn thread. |

`CompletionStage` **không có nghĩa code tự chuyển sang một thread mới** cho từng phép `thenApply`. Callback không dùng hậu tố `Async` có thể chạy trên thread hoàn tất stage hoặc thread đăng ký, tùy timing/implementation. Vì thế phải giữ callback **nhanh, không block**.

### 5.2. `thenApply` cho biến đổi giá trị nhẹ

~~~java
CompletionStage<Integer> countFirstPage =
    session.executeAsync(statement)
        .thenApply(result -> {
            int rows = 0;
            for (Row ignored : result.currentPage()) {
                rows++;
            }
            return rows;
        });
~~~

Đây là **số hàng ở trang hiện tại**, không phải tổng số hàng của query nếu `hasMorePages()` là `true`. Đoạn minh họa nằm trong method, cần imports `CompletionStage`, `Row` và các biến `session/statement` sẵn có.

### 5.3. `thenCompose` cho thao tác bất đồng bộ kế tiếp

~~~java
CompletionStage<AsyncResultSet> first =
    session.executeAsync(statement);

CompletionStage<AsyncResultSet> nextOrSame =
    first.thenCompose(page -> {
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(page);
        }
        return page.fetchNextPage();
    });
~~~

`fetchNextPage()` đã trả về `CompletionStage<AsyncResultSet>`; vì vậy **`thenCompose`**, không phải `thenApply`, là cách nối trực tiếp cho stage có phụ thuộc. Với ví dụ này, biến `nextOrSame` là **trang thứ hai nếu có**, không chứa tất cả hàng của trang thứ nhất; muốn tổng hợp phải xử lý và lưu kết quả từ các trang trước.

### 5.4. Stage thành công không đồng nghĩa ứng dụng đã xử lý hết dữ liệu

~~~text
executeAsync hoàn tất
    -> nhận một AsyncResultSet (trang đầu)
    -> ứng dụng duyệt currentPage()
    -> nếu hasMorePages(), cần fetchNextPage()
    -> ứng dụng xử lý kết quả/page cuối
    -> toàn bộ workflow nghiệp vụ mới hoàn tất
~~~

Khi xây API trả lịch sử có nhiều trang, cần **một stage đại diện cho cả workflow đã chọn**, chứ không đo p99 chỉ tới lúc `executeAsync` trả trang đầu.

## 6. `AsyncResultSet`: trang hiện tại và khả năng lấy trang tiếp

### 6.1. Các thành phần chính

| API | Nội dung | Cách hiểu đúng |
| --- | --- | --- |
| `currentPage()` | Các `Row` của **trang hiện tại**. | Không tự động truy xuất tất cả trang tiếp theo. |
| `hasMorePages()` | Cho biết còn trang có thể fetch theo cơ chế paging. | `false` nghĩa đã đến trang cuối của query đó, không nói toàn bộ cluster đã nhất quán. |
| `fetchNextPage()` | Khởi tạo truy vấn lấy trang tiếp theo và trả `CompletionStage<AsyncResultSet>`. | Cần `thenCompose`/pipeline để tiếp tục không block. |
| `getExecutionInfo()` | Thông tin thực thi của trang tương ứng (coordinator, warnings, tracing ID nếu có). | Không phải nhật ký đầy đủ của mọi replica. |
| `getColumnDefinitions()` | Schema các cột trả về trong kết quả. | Không phải toàn bộ schema table hay reflection metadata của entity. |
| `wasApplied()` | Trạng thái áp dụng cho thao tác có conditional semantics phù hợp. | Với LWT cần xem `[applied]` và dữ liệu đi kèm theo đúng statement; không dùng để kết luận read có hàng. |

Đừng suy rằng `AsyncResultSet` giống `ResultSet` đồng bộ: `ResultSet` có thể giúp iterator fetch thêm page khi duyệt; còn với **async**, bạn chủ động xử lý `currentPage()` và gọi `fetchNextPage()`.

### 6.2. Ví dụ chỉ đọc trang đầu, có đánh dấu còn trang

~~~java
// FirstPageRead.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.concurrent.CompletionStage;

public final class FirstPageRead {
    public static CompletionStage<String> read(
            CqlSession session, PreparedStatement query) {

        BoundStatement statement = query.bind(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                Instant.parse("2026-11-21T10:00:00Z"))
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(2);

        return session.executeAsync(statement)
            .thenApply((AsyncResultSet result) -> {
                int rows = 0;
                for (Row row : result.currentPage()) {
                    rows++;
                    // Chỉ đọc metadata nhẹ, không block/ghi file tại đây.
                    row.getInstant("event_time");
                    row.getString("event_type");
                }
                return "first_page_rows=" + rows
                    + " has_more=" + result.hasMorePages();
            });
    }
}
~~~

**Kỳ vọng trên ba row lab:** trang đầu thường có hai hàng khi page size 2 và `hasMorePages()` có thể là `true`; paging behavior cụ thể phụ thuộc server/driver và lượng dữ liệu. Code chỉ tạo kết quả **preview trang đầu**. Nếu API hứa trả đủ 100 rows mà dùng kết quả này, nó đang **mất dữ liệu ở phần trình bày** chứ không phải Cassandra làm mất dữ liệu trên disk.

### 6.3. `LIMIT` và page size khác nhau

~~~text
SELECT ... LIMIT 100
driver page size = 20
=> nếu có đủ dữ liệu, kết quả thường phân thành nhiều page.

LIMIT 100       : giới hạn số row logic toàn statement.
page size 20    : mục tiêu row/page, không phải byte/page.
currentPage()   : chỉ các row đã về trong trang hiện tại.
fetchNextPage() : cần thêm round-trip theo trạng thái paging.
~~~

Với row 100 KiB, một page 20 hàng có thể mang **cỡ 2 MiB payload** chưa tính overhead; 100 futures cùng giữ page lớn có thể khiến heap/direct memory/GC tăng mạnh. `LIMIT 100` cũng không bảo đảm replica chỉ quét 100 cell vật lý: tombstone, SSTable versions và clustering ranges có thể làm số cell phải xét cao hơn.

## 7. Đọc nhiều trang không block và giới hạn tổng công việc

Trả về toàn bộ danh sách 10 triệu row từ một `CompletionStage` sẽ chiếm heap, dù mọi thao tác I/O đều bất đồng bộ. Ví dụ sau **đếm** hàng và số trang trong tối đa năm page, không giữ collection lớn, bằng chuỗi `thenCompose`. Đây là phương án an toàn để hiểu mechanics trước khi thiết kế streaming API thực tế.

~~~java
// LimitedPageScan.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CompletableFuture;

public final class LimitedPageScan {
    public static final class Summary {
        public final int pages;
        public final long rows;
        public final boolean stoppedWithMore;

        public Summary(int pages, long rows, boolean stoppedWithMore) {
            this.pages = pages;
            this.rows = rows;
            this.stoppedWithMore = stoppedWithMore;
        }
    }

    public static CompletionStage<Summary> countUpToFivePages(
            CqlSession session, BoundStatement statement) {
        return session.executeAsync(statement)
            .thenCompose(first -> countPages(first, 1, 0, 5));
    }

    private static CompletionStage<Summary> countPages(
            AsyncResultSet page, int pages, long rows, int maxPages) {

        long accumulated = rows;
        for (Object ignored : page.currentPage()) {
            accumulated++;
        }

        if (!page.hasMorePages() || pages >= maxPages) {
            return CompletableFuture.completedFuture(
                new Summary(pages, accumulated, page.hasMorePages()));
        }

        final long nextRows = accumulated;
        return page.fetchNextPage().thenCompose(
            next -> countPages(next, pages + 1, nextRows, maxPages));
    }
}
~~~

**Tại sao mã này có giới hạn?**

- Chỉ gọi `fetchNextPage()` **sau khi hoàn tất** xử lý trang hiện tại; không chủ động fetch hàng trăm page song song.
- Không tích lũy `List<Row>` hoặc `List<DTO>` toàn bộ query, chỉ giữ `rows/pages`.
- `maxPages = 5` tạo **điểm dừng**; `stoppedWithMore = true` thông báo dừng do giới hạn khi còn dữ liệu.
- Một chuỗi đệ quy **được giới hạn độ sâu** minh họa dễ hiểu; nếu xử lý hàng triệu page, cần state machine/publisher có kiểm soát, không dùng đệ quy vô hạn.
- Một request chưa có **deadline tổng** chỉ vì mỗi page có driver timeout riêng; service phải quản lý deadline toàn workflow.

**Quan trọng:** `countUpToFivePages` **không phải COUNT chính xác của cả partition** khi còn page, và cũng không phải bản sao snapshot. Không dùng kết quả để đối soát đầy đủ dữ liệu hoặc tính tổng số sự kiện thật.

### 7.1. Khi cần đưa từng trang ra downstream

Một lựa chọn kiến trúc là nhận một trang, chuyển thành DTO nhỏ, gửi tới consumer có **ack/backpressure**, rồi mới gọi `fetchNextPage()`. Nhưng nếu “gửi trang” ở đây dùng HTTP/file I/O blocking, **không làm trực tiếp trong callback trên thread driver I/O**; chuyển xử lý tốn CPU hoặc blocking sang **executor riêng có giới hạn** và trả về stage hoàn tất của consumer trước khi fetch tiếp.

~~~text
fetch page 1
  -> xử lý row nhẹ / map DTO
  -> downstream xử lý page và ACK
  -> fetch page 2
  -> ... đến giới hạn rows/bytes/deadline
~~~

Ngược lại, `fetch page 2,3,4... song song không hạn chế` để tăng throughput có thể tiêu thụ heap/connection capacity vượt kiểm soát và không duy trì thứ tự hiển thị mong muốn.

## 8. `thenCompose` so với `thenApply`: tránh stage lồng nhau

Giả sử API trước tiên đọc metadata của thiết bị rồi mới đọc sự kiện. Bước thứ hai **phụ thuộc** kết quả bước đầu:

~~~java
CompletionStage<DeviceInfo> infoStage = loadDeviceInfo(deviceId);

// ĐÚNG: thenCompose làm phẳng CompletionStage được trả từ readEventsAsync.
CompletionStage<EventPage> pageStage =
    infoStage.thenCompose(info -> {
        if (!info.isEnabled()) {
            return CompletableFuture.completedFuture(EventPage.empty());
        }
        return readEventsAsync(info.getDeviceId(), day);
    });
~~~

Trong ví dụ cấu trúc này, `DeviceInfo`, `EventPage`, `loadDeviceInfo` và `readEventsAsync` là các **hàm/kiểu do ứng dụng tự định nghĩa**. Nếu dùng `thenApply(info -> readEventsAsync(...))`, kết quả sẽ là **stage chứa stage**, khó quản lý outcome và pipeline.

### 8.1. Hai truy vấn độc lập và `thenCombine`

Nếu hai partition độc lập và API cần kết hợp kết quả, có thể:

~~~java
CompletionStage<EventPage> today = readEventsAsync(deviceId, todayDate);
CompletionStage<EventPage> yesterday =
    readEventsAsync(deviceId, yesterdayDate);

CompletionStage<Timeline> timeline =
    today.thenCombine(yesterday, (a, b) -> mergeByTime(a, b));
~~~

Nhưng **đăng ký hai stages không tự đảm bảo đủ capacity**. Nếu API fan-out 1.000 ngày/bucket hoặc 1.000 tenants, phải giới hạn **số truy vấn đang chạy**, số partition, byte/page và deadline tổng. Kết quả của hai truy vấn không tạo **snapshot nguyên tử chung** giữa hai partition.

### 8.2. Không block trong callback

~~~java
// PHẢN MẪU: chờ một query khác ngay trong callback.
return session.executeAsync(statement)
    .thenApply(page -> {
        return session.executeAsync(otherStatement)
            .toCompletableFuture()
            .join(); // Có thể block thread hoàn tất stage!
    });
~~~

Hãy viết `thenCompose(page -> session.executeAsync(otherStatement))`, cộng với validation, timeout/deadline và giới hạn concurrency. Nếu cần thao tác CPU-intensive, dùng `thenApplyAsync(..., boundedExecutor)` hoặc đường xử lý riêng được điều tiết; hậu tố `Async` **không bảo đảm “miễn phí thread”**.

## 9. Lỗi và biến đổi outcome trong pipeline async

### 9.1. `whenComplete` để quan sát, không giấu lỗi

~~~java
CompletionStage<AsyncResultSet> observed =
    session.executeAsync(statement)
        .whenComplete((page, error) -> {
            if (error == null) {
                metrics.recordSuccess("read_device_events");
            } else {
                metrics.recordFailure(
                    "read_device_events",
                    error.getClass().getSimpleName());
            }
        });
~~~

`metrics` là công cụ ứng dụng giả định; callback ở đây chỉ tăng counter/ghi event nhẹ. **Không ghi raw CQL có dữ liệu nhạy cảm hoặc payload**. `whenComplete` thông thường giữ thành công/thất bại của stage gốc, vì vậy dễ dùng để đo mà không che exception.

### 9.2. `exceptionally` và cạm bẫy “trả danh sách rỗng”

~~~java
// PHẢN MẪU: mọi lỗi DB đều biến thành 'không có dữ liệu'.
CompletionStage<EventPage> unsafe =
    readEventsAsync(deviceId, day)
        .exceptionally(error -> EventPage.empty());
~~~

Nếu Cassandra không đủ quorum hoặc credential bị thu hồi, trả `List.of()` có thể khiến API trả 200/404 sai. Chỉ dùng fallback khi **nghiệp vụ định nghĩa rõ** và có metric/trace, ví dụ trả cache có hạn dùng cho dữ liệu không quan trọng; không biến dữ liệu thiếu do lỗi thành kết quả chính xác.

### 9.3. Xử lý đúng loại lỗi

| Loại lỗi | Cần xem | Có nên retry? |
| --- | --- | --- |
| `Unavailable` | RF/CL, node/DC, replica health. | Không retry vô hạn; có thể cần chờ recovery hoặc trả lỗi tạm thời. |
| `ReadTimeout` | Replica chưa đáp ứng trong timeout, GC/disk/network/tombstones. | Chỉ retry có budget nếu query an toàn và deadline cho phép. |
| `WriteTimeout` | Mutation có thể đã tới một số replica. | Chỉ retry khi định danh/mutation idempotent theo semantics nghiệp vụ. |
| Driver request timeout | Deadline client, queue, mạng và tổng công việc. | Không tăng timeout mù; đo nguyên nhân. |
| `Unauthorized`/authentication | Role, secret, TLS và session identity. | Không retry liên tục với credential sai hoặc đổi sang superuser. |
| Invalid query/schema | CQL hoặc deployment/schema drift. | Sửa query/schema, không retry cùng input vô hạn. |
| Mapping/codec error | CQL type và Java mapping. | Sửa code/codec, không xem là lỗi replica. |

**Không nhầm `CompletionException` với nguyên nhân sâu nhất.** Nhiều pipeline `CompletionStage` có thể bọc root cause; khi logging cần giải gói thận trọng, giữ stack trace và tránh nuốt lỗi. Tên class lỗi thực theo version driver.

### 9.4. Ví dụ `handle` có trạng thái thành công/thất bại tường minh

~~~java
// Một record giả định của Java 17:
record ReadOutcome(boolean success, int firstPageRows, String errorType) {}

CompletionStage<ReadOutcome> outcome =
    session.executeAsync(statement).handle((page, error) -> {
        if (error != null) {
            return new ReadOutcome(
                false, 0, error.getClass().getSimpleName());
        }
        int rows = 0;
        for (Row ignored : page.currentPage()) {
            rows++;
        }
        return new ReadOutcome(true, rows, "");
    });
~~~

`handle` **chuyển lỗi thành giá trị** có trạng thái; người gọi phải thực sự kiểm tra `success`. Nếu API cần phát tán exception để infrastructure trả lỗi phù hợp, giữ stage thất bại thay vì convert vô điều kiện sang object trông thành công.

## 10. `executeAsync` trên write: thành công, timeout và tính idempotent

Đọc dữ liệu async và ghi dữ liệu async có điểm chung về API, nhưng **write timeout có rủi ro đúng/sai riêng**. Cassandra có thể đã áp dụng mutation trên một số replica trước khi driver hoặc coordinator báo timeout. Vì vậy:

~~~text
Async INSERT được gửi
  -> coordinator chuyển mutation tới natural replicas
  -> có thể một hoặc nhiều replica đã ghi
  -> không nhận đủ ACK trước deadline
  -> stage hoàn tất với lỗi

Không suy: "stage lỗi" == "chưa replica nào ghi".
~~~

### 10.1. Khóa sự kiện ổn định trong mọi retry

Với bảng lab:

~~~sql
INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (?, ?, ?, ?, ?, ?);
~~~

`(device_id, event_day, event_time, event_id)` là full primary key; nếu producer có **event ID bất biến**, việc gửi lại *cùng giá trị* có thể tránh tạo **hàng trùng do sinh ID mới**. Tuy nhiên:

- Nếu payload/update cạnh tranh, timestamp Cassandra quyết định bản thắng theo semantics mutation, không phải event-time của domain.
- Nếu dùng `USING TTL` hoặc default TTL, ghi lại có thể **gia hạn thời gian sống**.
- Với `counter`, LWT hoặc workflow nhiều bảng, retry có hợp đồng khác; không gọi mọi statement là idempotent.
- Một request nhận `WriteTimeout` cần **reconciliation hoặc durable retry** phù hợp, không chỉ `exceptionally(error -> success)`.

### 10.2. Java: admission control trước khi gọi driver

Đây là mẫu **fail-fast khi hết slot** cho một lớp ghi sự kiện của lab. Nó có tối đa 32 request Cassandra đang chạy **trong một instance đối tượng**, không tạo queue vô hạn, và trả slot dù stage thành công hay lỗi.

~~~java
// BoundedAsyncWriter.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

public final class BoundedAsyncWriter {
    public record Event(
            String deviceId, LocalDate day, Instant time,
            UUID id, String type, String payload) {}

    private final CqlSession session;
    private final PreparedStatement insert;
    private final Semaphore permits = new Semaphore(32);

    public BoundedAsyncWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO telemetry_async.events_by_device_day " +
            "(device_id, event_day, event_time, event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)");
    }

    public CompletionStage<UUID> insertAsync(Event event) {
        // Không block event-loop/request thread khi tất cả slot đã bận.
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new RejectedExecutionException("DB concurrency limit"));
        }

        try {
            BoundStatement statement = insert.bind(
                    event.deviceId(), event.day(), event.time(),
                    event.id(), event.type(), event.payload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            return session.executeAsync(statement)
                .thenApply(ignored -> event.id())
                .whenComplete((id, error) -> permits.release());
        } catch (RuntimeException dispatchError) {
            // Bao gồm cả lỗi bind/dispatch xảy ra trước khi có stage.
            permits.release();
            return CompletableFuture.failedFuture(dispatchError);
        }
    }
}
~~~

**Điểm cần hiểu về sample:**

1. `Semaphore.tryAcquire()` chỉ quyết định **nhận hoặc từ chối** request ngay; không đưa request vào queue bất tận. Ở API, `RejectedExecutionException` nên được ánh xạ sang overload response hợp lý, không trả 404.
2. `whenComplete` trả slot khi stage hoàn tất **thành công hoặc thất bại**; callback chỉ thao tác nhẹ, không block driver I/O.
3. `PreparedStatement` được chuẩn bị một lần. `BoundStatement` được tạo riêng cho mỗi request, có khóa ổn định do caller cung cấp.
4. Giới hạn 32 có phạm vi **writer instance**; nếu tạo writer theo request, giới hạn mất ý nghĩa. Nên có writer sống cùng service hoặc gate chung cho workload.
5. Không tự bật retries/speculative execution; muốn retry phải chứng minh idempotency và có retry budget.
6. Ví dụ không có durable queue, kiểm soát mốc mutation, cancellation hay global rate limit. Production cần xử lý điều gì xảy ra nếu process chết sau khi một write đã gửi nhưng trước khi nhận ACK.
7. Không dùng `MAX_IN_FLIGHT=32` làm lời khuyên chung. Benchmark trên số pod, số replica, page size, kích thước payload và SLO thực.

### 10.3. Một stage cho một statement không phải transaction của workflow

~~~java
CompletionStage<?> writeA = session.executeAsync(statementA);
CompletionStage<?> writeB = session.executeAsync(statementB);
~~~

Hai write trên có thể thành công/thất bại độc lập; `thenCombine` hay `allOf` chỉ **đợi kết quả Java**, không biến chúng thành atomic transaction đa bảng/đa partition. Nếu một event phải vào hai bảng phục vụ hai query, cần **durable mutation log, dual-write reconciliation/CDC hoặc cơ chế nhất quán nghiệp vụ phù hợp**.

## 11. Backpressure: API, driver và Cassandra phải có ngân sách chung

Không thể giải quyết overload bằng cách “gọi async nhanh nhất có thể”. Để hiểu hệ thống có kiểm soát, phân biệt **ba nơi queue**:

~~~mermaid
flowchart TD
    A["HTTP / queue consumer"] --> B{"Admission: còn budget?"}
    B -->|Không| X["429/503/defer theo hợp đồng"]
    B -->|Có| C["App concurrency gate"]
    C --> D["Java Driver throttler / connection pools"]
    D --> E["Coordinator request queues"]
    E --> F["Replica disk/GC/compaction"]
    F --> G["Stage success / failure"]
    G --> H["Release app permit, update metrics"]
~~~

| Lớp | Ngưỡng tiêu biểu | Sai lầm |
| --- | --- | --- |
| **Gateway/API** | Concurrent user requests, request size, deadline. | Nhận vô hạn request và để chúng chờ trong heap. |
| **Worker/consumer** | Poll batch size, concurrency, durable offset/ack. | ACK message trước khi mutation có kết quả/đường retry bền. |
| **Java app** | Semaphore, bounded executor queue, per-tenant/query budgets. | Dùng `join()` hoặc `Thread.sleep()` trong callback. |
| **Driver** | Request throttler, in-flight, pooling, request timeout/retry. | Tăng queue/pool khi replica đã bão hòa. |
| **Cassandra** | Coordinator queues, CL deadlines, disk/GC, guardrails. | Nới server timeout để né CQL/query model sai. |

### 11.1. In-flight không phải connection count

Cassandra native protocol cho phép **nhiều request được multiplex trên một connection**. Một `CqlSession` quản lý pools tới các node, không phải mỗi `executeAsync` tạo kết nối riêng.

Nếu service chạy 25 pod, mỗi pod cho tối đa 40 statements in-flight:

~~~text
Trần lý thuyết theo gate: 25 × 40 = 1.000 statements đồng thời

Chưa tính:
  - request từ service khác
  - retry hoặc speculative attempt
  - batch/backfill jobs
  - fan-out nhiều partition cho mỗi API
~~~

Đây là **số statement đang chờ hoàn tất**, không phải 1.000 TCP connections hoặc 1.000 statements/s. Thêm pool khi disk/replica nghẽn thường chỉ đẩy thêm tải vào nút thắt.

### 11.2. Little's Law để nhận biết nguy cơ queue

Ở trạng thái ổn định:

~~~text
L ≈ λ × W
L = số request tồn tại trung bình
λ = throughput hoàn tất mỗi giây
W = thời gian tồn tại trung bình (giây)

Ví dụ 800 CQL statements/s:
  mean W = 0,05 s -> L ≈ 40
  mean W = 0,50 s -> L ≈ 400
~~~

Khi latency tăng 10 lần với cùng arrival rate, số request chưa hoàn tất có thể tăng rất mạnh. Nhưng trong overload, hệ có thể không ở trạng thái ổn định; **không thay p99 vào công thức như thể là mean W**. Phải đo queue age, in-flight và completion rate thật.

### 11.3. Bounded queue không giống ngừng mọi tải

Giới hạn queue/in-flight không làm Cassandra nhanh hơn ngay lập tức; nó **bảo vệ khỏi mất kiểm soát** và cho hệ thống khả năng tự hồi phục. Nếu dữ liệu không thể mất, overload từ Kafka/message broker phải đi kèm **pause consumption, không ACK trước khi có kết quả bền vững, retry/DLQ và offset tracking**, không đơn giản “drop events”.

## 12. AsyncResultSet và reactive streams: liên quan nhưng không đồng nhất

Tên chương là “Bất đồng bộ và reactive”, song **`CompletionStage<AsyncResultSet>` không phải `Publisher<Row>`**. Hai kiểu lập trình có những điểm khác:

| Đặc trưng | Async Core (`executeAsync`) | Reactive Streams/driver reactive API nếu hỗ trợ |
| --- | --- | --- |
| Kết quả | Stage cho một trang `AsyncResultSet`. | Publisher/subscriber xử lý luồng kết quả theo subscription. |
| Tín hiệu luồng | `hasMorePages` + `fetchNextPage`. | `request(n)`/demand, `onNext`, `onError`, `onComplete`. |
| Backpressure | Ứng dụng quyết định khi nào fetch page tiếp theo và bao nhiêu workflow in-flight. | Được biểu diễn bằng **demand** qua protocol reactive; vẫn cần policy concurrency. |
| Mapping | `thenApply`, `thenCompose`, chuyển `Row`/page. | Các operator stream theo framework/reactive API tương thích. |
| Lỗi | Exceptional completion của stage. | Terminal `onError` hoặc semantics publisher. |
| Ranh giới đọc | Page-level rõ ràng. | Framework có thể che paging; phải đo request/page/bytes thực. |

Một số bản của Java Driver 4.x cung cấp **reactive execution API** tích hợp Reactive Streams. Khi dùng Reactor/RxJava hoặc framework tương tự, phải kiểm tra **version-specific method/return type và demand behavior**. Không tự viết:

~~~java
// SAI VỀ Ý NGHĨA: một stage của trang đầu != stream của mọi row.
Mono.fromCompletionStage(session.executeAsync(statement))
    // Mono này cho một AsyncResultSet, KHÔNG tự phát từng Row
    // của tất cả các trang thành Flux<Row>.
~~~

Ví dụ là **minh họa conceptual, không phải class Java hoàn chỉnh**. Muốn chuyển thành `Flux<Row>`, phải có pipeline **fetchNextPage đúng thứ tự và theo demand** hoặc dùng API reactive của driver đã kiểm tra. Một `Flux` được tạo từ một `List` khổng lồ đã đọc xong không có backpressure end-to-end thực sự trong giai đoạn fetch.

### 12.1. Reactive không miễn phí tài nguyên

Nếu subscriber `request(Long.MAX_VALUE)`, hay dùng operator `flatMap` concurrency quá lớn, backend vẫn có thể nhận lượng việc vượt khả năng. Dù có Publisher, vẫn phải:

- Giới hạn concurrency, demand và buffer theo **bytes/rows**.
- Đặt timeout/deadline tổng và xử lý cancellation.
- Cẩn thận với `collectList()` hoặc `block()` trong event-loop.
- Giữ query bounded theo partition/range và tránh `ALLOW FILTERING` tràn lan.
- Đo memory/GC và số read operations thật trên Cassandra.

**Điểm phân biệt:** async giúp bỏ chờ blocking khỏi thread; reactive là mô hình composition và demand của một **luồng**. Cả hai đều cần kiểm soát overload.

## 13. Deadline, timeout và cancellation trong nhiều trang

### 13.1. Có nhiều đồng hồ thời gian

| Thời gian | Scope | Thường bao gồm |
| --- | --- | --- |
| **API deadline** | Toàn nghiệp vụ từ lúc request vào. | Admission, nhiều CQL statements, paging, mapping và serialize HTTP. |
| **Driver request timeout** | Request/attempt theo semantics của phiên bản. | Chờ Cassandra trả response cho một công việc driver. |
| **Coordinator read/write timeout** | Request Cassandra tại coordinator. | Chờ replica phù hợp CL, phụ thuộc query type. |
| **Per-page latency** | Mỗi lần fetch trang. | Network + coordinator/replica cho trang đó. |
| **Downstream timeout** | Đưa page/DTO sang hệ khác. | Network/API nội bộ hoặc I/O ứng dụng. |

Giả sử mỗi page mất 250 ms, và endpoint phải đọc **10 pages** tuần tự. Một driver timeout 2 giây cho từng page (theo implementation tương ứng) **không có nghĩa toàn endpoint hoàn tất trong 2 giây**. Ngay cả khi tất cả trang đều thành công, tổng thời gian có thể hơn 2,5 giây chưa tính queue và mapping.

### 13.2. `orTimeout` không phải lệnh hủy truy vấn trên replica

Java 17 có thể đặt một thời hạn lên `CompletableFuture`:

~~~java
// Minh họa; TimeUnit/CompletableFuture cần import tương ứng.
CompletableFuture<AsyncResultSet> firstPage =
    session.executeAsync(statement).toCompletableFuture();

firstPage.orTimeout(800, TimeUnit.MILLISECONDS);
~~~

Điều này giới hạn **quan sát/cách hoàn tất future phía Java** theo API Java; **không bảo đảm coordinator/replica ngay lập tức dừng công việc**. Nó cũng không tự tạo một deadline tổng cho các stage `fetchNextPage()` khởi chạy sau đó. Production nên có **mốc thời gian deadline thống nhất**, kiểm tra trước khi gửi từng trang và cơ chế release tài nguyên/admission khi complete.

### 13.3. Cancellation trong async pipeline

Nếu HTTP client ngắt kết nối:

1. Ứng dụng có thể **dừng việc gọi `fetchNextPage()`**; đây là cách trực tiếp để tránh gửi thêm công việc không còn cần thiết.
2. Một request đã gửi tới Cassandra **có thể vẫn đang chạy** dù future phía client bị cancel/hết hạn; không giả định hủy nguyên tử trên server.
3. Phải giải phóng **app permit, timeout state, downstream subscription** theo đường complete/cancel/error phù hợp.
4. Với write, cancellation **không đồng nghĩa dữ liệu chưa được ghi**; cần reconciliation nếu mutation outcome quan trọng.

### 13.4. Budget theo số hàng, byte, page và thời gian

~~~text
API query budget (ví dụ):
  maximum buckets            = 3
  maximum rows in response    = 200
  maximum pages to fetch      = 10
  maximum serialized bytes    = 2 MiB
  total request deadline      = 700 ms
  concurrency per instance    = 40
  queue limit                 = 80
~~~

Các con số chỉ để minh họa; **page size tính theo rows không bảo đảm byte cap**, và deadline phải bao gồm cả waiting time. Một bảng có payload cực lớn cần giới hạn ở tầng mô hình dữ liệu/ứng dụng chứ không chỉ client page size.

## 14. `ExecutionInfo`, tracing và quan sát từng page

`AsyncResultSet.getExecutionInfo()` có thể cho biết coordinator và cảnh báo của request tương ứng, cũng như trace ID nếu tracing được bật. Khi có nhiều page, **mỗi page có thể có thông tin thực thi riêng**, và nhìn một trang không đủ mô tả toàn bộ workflow.

~~~java
// Nằm trong callback thenApply của AsyncResultSet:
var info = page.getExecutionInfo();
var coordinator = info.getCoordinator();
var warnings = info.getWarnings();
var traceId = info.getTracingId();

System.out.println("coordinator="
    + (coordinator == null ? "unknown" : coordinator.getEndPoint())
    + " warnings_count=" + warnings.size()
    + " tracing_id=" + traceId);
~~~

Đây là **ví dụ quan sát cho lab**, không nên `System.out.println` từng row/page ở production vì logging có thể trở thành bottleneck hoặc lộ metadata. `getTracingId()` thường không có giá trị khi không bật tracing; không suy “null là driver bỏ mất dữ liệu”. Tên getter/kiểu trả về cần được kiểm tra theo bản Java Driver.

### 14.1. Metrics hữu ích cho async paging

| Metric | Vì sao cần |
| --- | --- |
| API end-to-end p50/p95/p99 | Thể hiện SLO của người dùng, gồm nhiều page và xử lý Java. |
| First-page latency | Thể hiện thời gian tới dữ liệu đầu tiên; không đại diện whole-result latency. |
| Full-consume latency | Cho biết thời gian duyệt xong số rows cần thiết. |
| Pages fetched/request | Phát hiện endpoint vô tình đọc quá nhiều page. |
| Rows/bytes decoded/request | Phát hiện payload lớn, page size không phù hợp. |
| In-flight stages/driver requests | Phát hiện quá tải phía client hoặc coordinator. |
| Permit wait/rejections | Đo hiệu quả admission/backpressure. |
| Driver retries/errors/throttler backlog | Phát hiện retry storm hoặc client queue phình. |
| Java heap, allocation, GC pauses | Phát hiện callbacks/DTO/list làm tăng memory và p99. |
| Cassandra read/write latency, `tpstats`, disk, tombstones | Phân biệt bottleneck server với async pipeline. |

**Không lấy trung bình p99 từng node làm p99 toàn cluster.** Gắn metrics theo `query_name`, `environment`, `local_dc`, `status`, `profile`, không gắn `device_id`, `event_id` hoặc request UUID làm label có cardinality vô hạn.

### 14.2. Trace chỉ vài câu truy vấn mẫu

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

Tracing giúp kiểm tra coordinator/replica và thời gian các bước xử lý Cassandra. Nó **không đo trực tiếp** thời gian Java `thenApply`, CPU mapping, heap allocations hoặc thời gian đợi app semaphore. Tracing toàn bộ traffic khi cluster đang quá tải có thể tạo thêm chi phí.

### 14.3. `nodetool` cần đặt cạnh client metrics

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_async.events_by_device_day
~~~

Phân biệt: `status` cho membership, không chứng minh replica còn headroom; `tpstats` cho queue/dropped tasks, không phải câu trả lời cho mọi timeout; `compactionstats` chỉ một phần áp lực I/O; logs/metrics/trace cần xem theo **UTC timeline** và baseline.

## 15. Một ngày có hai bucket: composition nhưng không có snapshot nguyên tử

Query theo ngày là một partition lookup, nhưng API đôi khi cần khoảng từ 23:45 UTC ngày trước tới 00:15 UTC ngày sau. Ứng dụng phải đọc **hai partition**:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:45:00Z'
  AND event_time < '2026-11-21T00:00:00Z';

SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-21T00:15:00Z';
~~~

Từ Java có thể phát hai `executeAsync` có concurrency budget rồi dùng `thenCombine` để merge theo `event_time` và `event_id`, giới hạn rows/bytes. Tuy nhiên:

1. **Tính đúng của bucket:** `event_day` phải được tính từ cùng quy ước UTC. `LocalDate.now()` theo timezone server không nhất thiết bằng UTC day của `event_time`.
2. **Thứ tự:** Cassandra chỉ sắp xếp trong từng partition; merge ở Java phải xác định tie-breaker nhất quán.
3. **Độ nhất quán:** hai SELECT tại hai mốc khác nhau **không phải một distributed transaction snapshot**.
4. **Deadline:** nếu một nhánh chậm, toàn `thenCombine` có thể chờ; cần time budget và policy trả kết quả một phần hay lỗi rõ ràng.
5. **Bounded fan-out:** với request 5 năm, không phát 1.826 future ngày song song không giới hạn. Giới hạn window và/hoặc dùng bảng projection/rollup phù hợp.

**Async không thay data modeling**: một partition nóng hoặc quá lớn vẫn có thể là nút thắt dù callback Java rất nhẹ.

## 16. Tính sẵn sàng và consistency level của request bất đồng bộ

### 16.1. CL là số phản hồi, không phải “async consistency”

Với `NetworkTopologyStrategy {'dc1': 3}`:

| Consistency level | Số replica local DC cần phản hồi (RF=3) | Tác động thường gặp |
| --- | --- | --- |
| `LOCAL_ONE` | Một full replica. | Latency thấp hơn trong nhiều trường hợp nhưng khả năng thấy dữ liệu mới phụ thuộc replication/repair. |
| `LOCAL_QUORUM` | Hai full replicas trong dc1. | Chịu được một full replica không sẵn sàng trong phạm vi DC và tác vụ/phân vùng phù hợp. |
| `ALL` | Cả ba full replicas cho keyspace chỉ có dc1. | Nhạy với một replica mất khả dụng; không phù hợp mọi workload. |

Khi có nhiều DC, `ALL` yêu cầu phản hồi theo tổng replica thuộc operation và có thể phụ thuộc remote DC; `LOCAL_QUORUM` chỉ xét local DC. Các đặc tính về transient replication/loại operation/phiên bản có thể thay đổi; bảng trên chỉ dành cho ví dụ **ba full replicas một DC**.

**Không gọi `LOCAL_ONE` là “bất đồng bộ” hoặc `LOCAL_QUORUM` là “đồng bộ”**. `executeAsync` là **cách Java chờ I/O**, còn CL quyết định coordinator cần mức xác nhận nào của replica. Hai trục hoàn toàn độc lập.

### 16.2. Retry và speculative execution trong async

Một số policy driver có thể retry request hoặc thực hiện speculative attempts theo thiết lập và tính idempotent. Điều đó có thể tăng số request thực gửi tới Cassandra so với số `executeAsync` ở code ứng dụng. Vì vậy:

- **Đo retries/speculative attempts** và traffic thực theo node; không chỉ đếm HTTP requests.
- Không coi mọi `INSERT`/counter/LWT idempotent theo cùng một cách.
- Một read timeout có thể được retry nếu đáp ứng policy, nhưng retry khi disk/GC quá tải có thể thành **vòng khuếch đại tải**.
- Không bật speculative execution toàn bộ traffic chỉ để giảm p99 trong một benchmark ngắn.

### 16.3. Không tự đổi CL khi gặp lỗi

Nếu request `LOCAL_QUORUM` trả `Unavailable`, chuyển âm thầm sang `LOCAL_ONE` để “cứ trả 200” là **thay đổi hợp đồng nhất quán**. Chỉ cân nhắc downgrade CL nếu nghiệp vụ và policy explicitly cho phép, có monitoring/audit và đánh giá khả năng đọc dữ liệu cũ. Tăng driver timeout cũng không thể tạo replica đang bị mất.

## 17. Case study: chỉ đọc trang đầu và trả thiếu sự kiện

### 17.1. Biểu hiện

Một API Java được chuyển từ:

~~~java
ResultSet result = session.execute(bound);
for (Row row : result) {
    // consume qua các page cần thiết
}
~~~

sang:

~~~java
session.executeAsync(bound).thenApply(result -> {
    List<EventView> values = new ArrayList<>();
    for (Row row : result.currentPage()) {
        values.add(EventView.from(row));
    }
    return values;
});
~~~

Phần code dưới là **đoạn nằm trong service, không phải một class hoàn chỉnh**; `EventView` là DTO ứng dụng và `from` là hàm mapping giả định.

Ở môi trường dev có ba row và page size 100, hai cách trả cùng kết quả. Trong production, mỗi partition có hàng nghìn row và page size 100. API async **chỉ trả tối đa số row ở trang đầu** và âm thầm bỏ phần còn lại.

### 17.2. Tại sao lỗi khó phát hiện?

| Quan sát | Kết luận vội | Giải thích đúng |
| --- | --- | --- |
| Query async trả thành công, không có exception. | “Cassandra đã trả đủ.” | Stage chỉ hoàn tất cho **trang đầu**. |
| CQL `LIMIT 500` nhưng nhận 100 row. | “Replica thiếu 400 row.” | Có thể còn page chưa fetch, cần `hasMorePages`. |
| `nodetool status` đều `UN`. | “Không còn vấn đề.” | Membership không sửa lỗi pagination của client. |
| Bật `LOCAL_QUORUM` vẫn nhận 100 row. | “Consistency không đủ.” | CL không thay cơ chế `fetchNextPage`. |
| Nâng page size lên 500 khiến dev/prod trả đủ. | “Đã sửa triệt để.” | Chỉ **che lỗi** tới khi kết quả lớn hơn page size, đồng thời tăng bytes/GC. |

**Nguyên nhân gốc:** luồng xử lý cũ dựa trên iterator đồng bộ có paging, trong khi luồng async chỉ duyệt `currentPage()` rồi kết thúc. **Cách sửa** là chủ động fetch page tiếp theo với `thenCompose` hoặc dùng API reactive có demand đúng, đồng thời định nghĩa limit/deadline tổng và test nhiều page.

### 17.3. Mẫu bài test bắt buộc

1. Tạo dữ liệu lab có **nhiều row hơn page size**.
2. Chạy query `LIMIT 100`, page size 2 và một pipeline đọc đủ kết quả.
3. Xác minh **tập event IDs, thứ tự và số row** theo CQL query.
4. So trang đầu và trang cuối; kiểm tra `hasMorePages` được xử lý.
5. Kiểm tra API không cố đọc vô hạn khi client chỉ yêu cầu 20 row.
6. Đo memory/GC và request count khi page size giảm hoặc payload tăng.

## 18. Lab tích hợp: đọc đủ ba hàng nhưng chỉ block tại ranh giới CLI

Ví dụ dưới dùng `CompletionStage` để đọc mọi trang của một **query lab có LIMIT 10**. Nó gom `UUID` vào list chỉ vì tập kết quả rất nhỏ và có giới hạn chặt. Trong một CLI test/khởi tạo thử nghiệm, ta **được phép chờ ở ranh giới `main`** để chương trình không đóng `CqlSession` trước khi stage hoàn tất. Không đưa kiểu `get()` đó vào callback/request/event-loop.

~~~java
// AsyncPagingLab.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public final class AsyncPagingLab {
    private static CompletionStage<List<UUID>> collect(
            AsyncResultSet page, List<UUID> eventIds) {
        for (Row row : page.currentPage()) {
            eventIds.add(row.getUuid("event_id"));
        }
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(eventIds);
        }
        return page.fetchNextPage().thenCompose(
            next -> collect(next, eventIds));
    }

    public static void main(String[] args) throws Exception {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_id FROM telemetry_async.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? LIMIT 10");

            BoundStatement query = prepared.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(2);

            CompletionStage<List<UUID>> pipeline =
                session.executeAsync(query)
                    .thenCompose(first -> collect(first, new ArrayList<>()));

            // CHỈ ở ranh giới main/test: chờ một workflow async có giới hạn.
            List<UUID> actual = pipeline.toCompletableFuture()
                .get(10, TimeUnit.SECONDS);

            if (actual.size() != 3) {
                throw new IllegalStateException(
                    "Expected 3 sample rows, got " + actual.size());
            }
            System.out.println("ASYNC_PAGING_OK rows=" + actual.size());
        }
    }
}
~~~

**Phạm vi của ví dụ:** giả định bảng lab chỉ chứa **ba hàng trong partition ngày đó** và đã được chèn ở mục 3; nếu có dữ liệu test khác, `actual.size() == 3` không còn là kỳ vọng đúng. `get(10, TimeUnit.SECONDS)` chỉ giới hạn thời gian chờ ở CLI; khi hết hạn vẫn phải hiểu **cancellation và tài nguyên driver** theo bản triển khai, không giả định server ngừng xử lý ngay.

### 18.1. Vì sao không dùng `collect()` này trong production cho một query vô hạn?

- Nó giữ tất cả `UUID` trong `ArrayList`; với hàng triệu row có thể cạn heap.
- Đệ quy không có giới hạn page riêng ngoài `LIMIT 10` của query; không nên sao chép mẫu cho `SELECT` không giới hạn.
- Nó không có per-page log/metrics, global deadline, admission/backpressure và API cancellation.
- Tính bất biến/snapshot của kết quả nhiều page **không được bảo đảm** khi có write/delete đồng thời.

Muốn xử lý kết quả lớn, dùng **bounded page processor/consumer** ở mục 7, giữ từng page vừa đủ và chỉ fetch trang kế sau khi downstream đã xử lý xong. Nếu cần export dữ liệu cấp cluster, sử dụng kiến trúc batch/token-range/backup phù hợp, không dùng một API query để quét mọi partition.

## 19. Case study: chuyển tất cả sang `executeAsync` và hết heap

**Bối cảnh giả lập:** 16 instance Java, mỗi instance nhận 400 API requests/s. Mỗi API tạo ba câu `SELECT` theo bucket ngày, `executeAsync` ngay lập tức và gom tất cả rows vào `List`. Một phần queries dùng `payload` 100 KiB; Cassandra đang compaction làm latency tăng.

| Mốc | Quan sát | Diễn giải |
| --- | --- | --- |
| Trước đổi | Sync requests giữ nhiều thread, p99 cao nhưng số request gửi có giới hạn tự nhiên bởi thread pool. | Có vấn đề tài nguyên/thread chờ cần cải thiện. |
| Sau đổi | Thread chờ giảm, số futures/in-flight tăng mạnh. | Đã bỏ một dạng giới hạn mà chưa thay bằng admission. |
| Trong compaction | Mean latency DB tăng, request tồn tại lâu hơn. | In-flight tăng ở cùng arrival rate. |
| Khi page trả về | Hàng trăm page payload lớn được giữ trong `List` đồng thời. | Heap/GC pressure lớn. |
| Sau retry | Driver/gateway phát thêm attempts. | Có thể tạo retry storm lên replica nghẽn. |
| Sự cố | OOM hoặc p99 tăng gấp nhiều lần. | “Async” không phải nguyên nhân duy nhất; **unbounded work** mới là lỗi thiết kế. |

### 19.1. Phản ứng sai

**Tăng heap, tăng số connection, tăng timeout và giảm CL** mà không đo, trong khi vẫn nhận vô hạn request và giữ toàn bộ rows. Cách này có thể lùi thời điểm OOM nhưng khiến backend và SLO xấu hơn.

### 19.2. Phản ứng có bằng chứng

1. **Giảm/điều tiết traffic đầu vào**, tạm dừng batch/backfill nếu cần để cluster hồi phục.
2. Đo `in_flight`, admission queue, rejected requests, retry count, pages/request và response bytes.
3. Đối chiếu p99 client với `nodetool tpstats`, compaction, disk await, GC và timeout server.
4. Sửa code để **giới hạn concurrent statements**, không giữ `List` vô hạn, chỉ fetch page kế khi downstream sẵn sàng.
5. Kiểm tra `SELECT` đủ partition key, time bucket và column projection; giảm payload/bytes nếu API không cần.
6. Đặt deadline tổng, retry budget và error contract rõ: overload là lỗi tạm, không phải kết quả rỗng.
7. Load test trên staging có data shape/peak và chaos case, rồi canary vài instance với rollback.

**Bài học:** async thay mô hình giữ thread, không thay **giới hạn công việc/byte/replica**. Nếu chuyển từ sync sang async mà bỏ mất giới hạn concurrency ngầm của thread pool, phải thay bằng **admission/backpressure explicit**.

## 20. Cấu hình, kiểm thử và rollout cho ứng dụng bất đồng bộ

### 20.1. Một số tùy chọn driver cần xét

Ví dụ HOCON mang tính định hướng cho Java Driver 4.x, **không phải giá trị production mặc định**:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }
  advanced.connection.pool {
    local.size = 1
  }
  advanced.request-throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 200
    max-queue-size = 400
  }
}
~~~

**Đọc đúng:** request throttler của driver không thay **app admission**; `local.size` là pool parameter chứ không phải số statements in-flight; timeout là deadline phía client theo phạm vi của driver, không thay read/write timeout của server. Các tên option/class/availability và hành vi reload phải kiểm tra đúng version. Nếu cấu hình không được load hoặc class không tồn tại, **đừng kết luận hệ thống đã rate-limit** chỉ vì file chứa các dòng ấy.

### 20.2. Tách môi trường

| Thuộc tính | Dev | Staging | Production |
| --- | --- | --- | --- |
| Cluster/DC | Lab riêng có DC đúng theo snitch. | Mô phỏng RF/CL và failure modes gần production khi test. | DC/rack/seed/routing thực, network policy chặt. |
| Credential | Lab identity ít quyền. | Staging identity tách riêng. | Service identity riêng, secret manager và rotate. |
| TLS | Thử certificate/CA phù hợp. | Full TLS/hostname verification và failover tests. | TLS/peer validation, audit, bảo vệ JMX/OS riêng. |
| Page/concurrency | Nhỏ, dễ tái hiện nhiều page. | Load test với row sizes/tombstones thật hoặc mô phỏng. | SLO/capacity-driven, có global budget và dashboard. |
| Timeout/retry | Dễ debug, không che lỗi. | Test GC/disk/replica down và cancel. | Deadline/retry budget có giám sát và rollout có kiểm soát. |

**Không dùng cùng secret hoặc cùng contact point production cho dev/staging.** Một `CqlSession` tạo từ env sai có thể truy vấn nhầm cluster dù CQL hợp lệ; xác minh **cluster identity, keyspace, local DC, auth role và TLS** trước khi nhận traffic.

### 20.3. Ma trận kiểm thử quan trọng

| Test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Trang đầu | Ba row, page size 2. | Có thể nhận ít hơn tổng; không kết luận thiếu dữ liệu. |
| Multi-page | Đủ row để vượt page size. | Dùng `fetchNextPage`, đúng tập key và thứ tự. |
| Zero rows | Partition không có hàng sống. | Stage thành công với kết quả rỗng; phân biệt khỏi exception. |
| Một page cuối không đủ size | Số hàng không chia hết page size. | Không fetch vô hạn; `hasMorePages` dừng đúng. |
| Driver timeout | Làm chậm response lab có kiểm soát. | Future thất bại, không báo 404, slot được release. |
| Replica down | RF/CL thỏa hoặc không thỏa tùy tình huống. | Phân biệt `Unavailable`/timeout và quan sát retry. |
| Write timeout | Kết quả không rõ sau khi gửi. | Không tạo `eventId` mới khi retry, có reconciliation. |
| Callback lỗi | Mapper/parser ném exception. | Stage tiếp theo thất bại, không mất permit. |
| Overload | Vượt gate 32 request. | Request vượt budget bị từ chối, không queue vô hạn. |
| Client disconnect | Hủy nhu cầu đọc trước page tiếp. | Không fetch thêm nếu không cần; không giả định server dừng ngay. |
| Page lớn | Row payload lớn, concurrency cao. | Heap/GC bounded, metric bytes/page và deadline hợp lý. |
| Phân trang khi có mutation | Update/delete giữa các page. | Không tuyên bố snapshot consistency. |
| Auth/TLS sai | Credential/CA hết hạn, role thiếu SELECT. | Lỗi rõ ràng, không retry vô hạn hay trust-all. |

### 20.4. Quy trình điều chỉnh có kiểm soát

~~~mermaid
flowchart TD
    A["Chuẩn bị chuyển sync sang async"] --> B["Chốt API deadline, rows/bytes, CL/RF và SLO"]
    B --> C["Thiết kế admit/queue/in-flight và error contract"]
    C --> D["Test multi-page, timeout, cancel và write uncertain"]
    D --> E["Staging load test: CPU/GC/driver/server metrics"]
    E --> F{"Correctness và p99 đạt?"}
    F -->|Không| G["Sửa CQL/paging/backpressure, test lại"]
    G --> D
    F -->|Có| H["Canary một nhóm pods, giữ rollback flag"]
    H --> I["Giám sát retries, pages, queue, disk, p99"]
    I --> J{"Có regression?"}
    J -->|Có| K["Giảm tải / rollback có kiểm soát"]
    J -->|Không| L["Mở rộng rollout, ghi hậu kiểm"]
~~~

## 21. Các anti-pattern cần tránh

| Anti-pattern | Vì sao sai | Cách thay |
| --- | --- | --- |
| `executeAsync(...).toCompletableFuture().join()` trong HTTP handler reactive. | **Block thread** nên mất lợi ích async; có thể gây nghẽn event loop. | Trả stage/publisher và compose tới response. |
| `thenApply(page -> fetchNextPage())` và không làm phẳng. | Stage lồng nhau và không xử lý kết quả đúng. | Dùng `thenCompose`, xử lý page cũ trước page mới. |
| Duyệt một `currentPage()` rồi tuyên bố đã có tất cả rows. | Bỏ trang tiếp theo khi còn `hasMorePages`. | Chủ động fetch tiếp hoặc chỉ hứa API preview. |
| `collectList()` cho toàn bộ bảng nhiều TB. | OOM/GC, không còn backpressure end-to-end. | Giới hạn scope, page, consumer và bytes. |
| Gọi `executeAsync` vô hạn vì “không block”. | App futures, driver queues và replicas vẫn quá tải. | Admission + bounded concurrency + global budget. |
| Block file/HTTP/CPU nặng trong callback driver. | Giữ thread dùng cho completion, ảnh hưởng các request khác. | Executor riêng có queue giới hạn hoặc async downstream. |
| Mọi lỗi đều `exceptionally(e -> emptyList)`. | Timeout/Unauthorized biến thành dữ liệu rỗng sai. | Giữ lỗi và map theo hợp đồng API. |
| Retry write timeout với event ID ngẫu nhiên mới. | Có thể tạo duplicate logic. | Stable keys, idempotency và reconciliation. |
| Chỉ tăng driver timeout khi p99 tăng. | Không sửa tombstone/disk/GC/replica down. | Đo driver/client/server và sửa nguyên nhân. |
| Đổi `LOCAL_QUORUM` thành `LOCAL_ONE` ngầm. | Thay đổi consistency contract. | Chỉ khi nghiệp vụ cho phép, có phê duyệt và quan sát. |
| Dùng future cancellation để khẳng định `INSERT` bị hủy trên server. | Cancellation client không bảo đảm mutation chưa áp dụng. | Xử lý outcome unknown và đối soát. |
| Cho rằng `CompletionStage` tự bảo đảm Reactive Streams backpressure. | Một stage không có `request(n)` semantics. | Dùng page-level gate hoặc reactive Publisher phù hợp. |
| Tạo `CqlSession` mới cho mỗi future. | Connection churn, TLS/auth/metadata cost. | Tái sử dụng session và prepared statements. |
| Dùng `ALLOW FILTERING` rồi tăng concurrency. | Biến scan tốn tài nguyên thành nhiều scan song song. | Thiết kế partition/projection theo truy vấn. |
| Chỉ đo first-page latency. | Che chi phí fetch nhiều page và mapping. | Đo full-consume/API latency, pages và bytes. |

## 22. Bài tập có đáp án

**Bài 1.** `executeAsync` trả kiểu gì trên Java Driver 4.x? Tại sao không nên gọi `join()` ngay trong HTTP event-loop?

**Đáp án:** Trả `CompletionStage<AsyncResultSet>`. `join()` chặn thread khi stage chưa hoàn tất; dùng composition/continuations và để framework chờ bất đồng bộ.

**Bài 2.** Với ba row lab, page size 2, `currentPage()` trả hai row. Cassandra đã làm mất row thứ ba?

**Đáp án:** **Không.** Page đầu không phải toàn query. Kiểm tra `hasMorePages()` và gọi `fetchNextPage()` để nhận phần còn lại.

**Bài 3.** Vì sao `thenCompose(page -> page.fetchNextPage())` phù hợp hơn `thenApply(...)`?

**Đáp án:** Vì `fetchNextPage()` tự trả `CompletionStage<AsyncResultSet>`; `thenCompose` làm phẳng stage phụ thuộc và trả cùng kiểu stage của trang tiếp, tránh stage lồng nhau.

**Bài 4.** `whenComplete` khác `exceptionally` như thế nào?

**Đáp án:** `whenComplete` chủ yếu quan sát outcome để log/metrics/cleanup và thông thường giữ lỗi gốc; `exceptionally` **thay lỗi bằng giá trị fallback** và có thể che lỗi nếu return rỗng mù quáng.

**Bài 5.** Một API nhận 100 request, mỗi request trả 20 pages. Code chỉ đo thời gian của `executeAsync` lần đầu. Nó đã đo full API latency?

**Đáp án:** **Chưa.** Nó chỉ đo tới trang đầu; phải đo cả 19 lần fetch tiếp, mapping, downstream và serialize response.

**Bài 6.** Một service có 20 pod, mỗi pod tối đa 50 statements in-flight. Trần lý thuyết toàn service?

**Đáp án:** `20 × 50 = 1.000` statements cùng lúc, chưa tính retry/speculative attempts và service khác; **không** phải 1.000 TCP connections.

**Bài 7.** Với RF = 3 trong dc1, `LOCAL_QUORUM` cần mấy replica phản hồi?

**Đáp án:** **Hai** full replicas tại dc1. Việc dùng `executeAsync` thay `execute` không đổi số lượng replica cần theo CL.

**Bài 8.** Async `INSERT` trả `WriteTimeout`. Có thể tạo `eventId` mới rồi retry mà chắc chắn không trùng?

**Đáp án:** **Không.** Mutation cũ có thể đã được một số replica áp dụng; retry với ID mới có thể tạo duplicate. Dùng stable key và chính sách idempotency/reconciliation phù hợp.

**Bài 9.** Một consumer reactive dùng `collectList()` gom 10 triệu hàng rồi mới trả response. Nó đã tận dụng backpressure toàn luồng?

**Đáp án:** **Không ở mức bộ nhớ đầu ra** nếu nó giữ toàn bộ dữ liệu. Demand của publisher không tự giới hạn heap nếu chính consumer tích lũy tất cả. Cần scope/byte/page cap và tiêu thụ từng phần.

**Bài 10.** `CompletableFuture.orTimeout(800ms)` bảo đảm replica ngừng query tại 800ms không?

**Đáp án:** **Không.** Nó tác động tới tương lai phía Java; công việc trên coordinator/replica có thể tiếp tục theo semantics. Ứng dụng phải ngừng gửi thêm page và xử lý trạng thái uncertain nếu là write.

**Bài 11.** Nếu query trả `SELECT ... LIMIT 100` với page size 20, vậy mỗi page luôn đúng 20 row và đúng 20 KiB?

**Đáp án:** **Không.** Page size đặt mục tiêu theo **row count**, không phải byte; page cuối có thể ít hàng, row size biến thiên và server/driver có giới hạn riêng.

**Bài 12.** Hai câu `executeAsync` vào hai bảng, rồi `thenCombine` chờ cả hai, có transaction atomic không?

**Đáp án:** **Không.** `thenCombine` chỉ kết hợp outcomes Java. Hai mutations có thể thành công/thất bại độc lập; cần durable retry/reconciliation hoặc cơ chế nhất quán nghiệp vụ khác.

**Bài 13.** Một `thenApply` parse JSON 10 MB và ghi file đồng bộ trong callback. Rủi ro?

**Đáp án:** Callback có thể chạy trên thread hoàn tất driver stage; CPU/I/O blocking ở đó gây chậm nhiều request. Chuyển công việc nặng sang bounded executor/async downstream và giữ demand/page budget.

**Bài 14.** Truy vấn `WHERE event_type='ALARM' ALLOW FILTERING` thiếu partition key bị chậm. Chuyển sang `executeAsync` có làm Cassandra quét ít SSTable?

**Đáp án:** **Không.** CQL/query model giữ nguyên. Cần bảng/projection/index phù hợp hoặc thay đường analytics và giới hạn scope.

**Bài 15.** Một stage hoàn tất thành công với trang đầu, `hasMorePages()=true`. API muốn tổng 100 row nhưng chỉ trả trang đầu. Lỗi nằm ở Cassandra replica hay Java pagination?

**Đáp án:** Đây là lỗi **Java pagination/workflow** chưa gọi `fetchNextPage()` và chưa xử lý đủ trang. Trạng thái stage thành công không chứng minh đã duyệt hết query.

**Bài 16.** Vì sao không nên so sánh throughput sync và async trong khi async giữ 5.000 requests in-flight còn sync chỉ có 100?

**Đáp án:** Khác biệt **concurrency budget** làm phép đo không công bằng, có thể khiến async gây overload và p99 xấu. Giữ cùng workload/data/CL/timeout và đo in-flight, queue, CPU/GC và server capacity.

## 23. Checklist và sơ đồ quyết định trước khi dùng async trong production

~~~text
CQL / DATA MODEL
[ ] Query dùng đầy đủ partition key, clustering range và LIMIT hợp lý.
[ ] Bucket size, hot partition, tombstone scan và payload/row đã benchmark.
[ ] Có RF/CL/local DC phù hợp với availability/correctness.

JAVA DRIVER / LIFECYCLE
[ ] Dùng CqlSession sống lâu, prepared statements được reuse.
[ ] Biết executeAsync trả CompletionStage<AsyncResultSet>, không phải List<Row>.
[ ] currentPage/hasMorePages/fetchNextPage được xử lý đủ theo API contract.
[ ] Không join/get trong HTTP event-loop hoặc driver callback.
[ ] thenCompose dùng khi bước sau trả CompletionStage.
[ ] Callback nhanh, việc CPU/blocking đưa tới bounded executor.

BOUNDING / ERROR SEMANTICS
[ ] Giới hạn input admission, queue, in-flight và fan-out toàn fleet.
[ ] Có trần rows/bytes/pages và deadline tổng cho request.
[ ] Retry budget, idempotency và write timeout handling rõ ràng.
[ ] Stage failure không bị chuyển thành kết quả rỗng không hợp lệ.
[ ] Cancellation không được hiểu là server đã rollback mutation.
[ ] Không đánh đồng CompletionStage với Publisher có backpressure.

SECURITY / OBSERVABILITY
[ ] TLS xác thực peer, credentials theo service và least privilege CQL.
[ ] Dev/staging/prod dùng cluster/DC/secrets tách biệt, không fallback mù.
[ ] Log redaction, không gắn device/event IDs làm metrics labels.
[ ] Đo first-page/full-consume p95/p99, pages/request, bytes và retries.
[ ] Đo client queue/GC cùng server tpstats/disk/tombstones/compaction.

VALIDATION / ROLLOUT
[ ] Test page size nhỏ hơn số row, page cuối, zero rows và large payload.
[ ] Test callback exception, timeout, cancellation, replica failure.
[ ] Test overload khi hết permit và release permit mọi outcome.
[ ] Load test đủ mẫu/canary, có stop criteria và rollback config/code.
~~~

~~~mermaid
flowchart TD
    A["Cần truy vấn Cassandra không giữ thread chờ"] --> B["Thiết kế CQL bounded theo partition/range"]
    B --> C["Dùng một CqlSession + prepared statement"]
    C --> D["executeAsync -> CompletionStage<AsyncResultSet>"]
    D --> E["Xử lý currentPage nhẹ"]
    E --> F{"Cần và được phép đọc tiếp?"}
    F -->|Có, còn budget| G["thenCompose(fetchNextPage)"]
    G --> E
    F -->|Không| H["Kết thúc workflow với kết quả/trạng thái rõ"]
    H --> I["Release permits, metrics, deadline/cancellation cleanup"]
    I --> J{"Correctness, p99, memory, replica health đạt?"}
    J -->|Không| K["Sửa query, page/byte budget, concurrency hoặc retry"]
    K --> B
    J -->|Có| L["Canary rollout và theo dõi"]
~~~

**Tổng kết:** `executeAsync` là cách **gửi CQL và nhận một `CompletionStage<AsyncResultSet>` không cần block thread Java khi đợi I/O**. `CompletionStage` giúp nối các bước bằng `thenApply`, `thenCompose` và xử lý lỗi/metrics rõ ràng; `AsyncResultSet` cho phép đọc **`currentPage()`** và chủ động tiếp tục bằng **`hasMorePages()`/`fetchNextPage()`**. Chuyển sang async **không tự làm CQL rẻ hơn, không tạo transaction/snapshot và không cấp backpressure vô hạn**. Hệ thống ổn định cần **partition key đúng, giới hạn rows/bytes/pages, admission và in-flight hữu hạn, deadline tổng, retry an toàn, cancellation đúng semantics và đo cả client lẫn replica**. Một stage thành công với trang đầu **chưa có nghĩa toàn workflow nghiệp vụ đã hoàn tất**.
