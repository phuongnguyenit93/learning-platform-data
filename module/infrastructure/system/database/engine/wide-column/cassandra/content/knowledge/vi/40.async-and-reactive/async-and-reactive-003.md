# hasMorePages/fetchNextPage và kết hợp các trang bất đồng bộ

> **Chương:** Bất đồng bộ và reactive  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu wide-column phân tán, partition key, thiết kế bảng theo truy vấn, consistency level, replication, compaction, repair, lỗi và tích hợp ứng dụng Java.

## 1. Vì sao cần phân trang bất đồng bộ?

Giả sử dịch vụ Java đọc lịch sử hoạt động của một khách hàng theo ngày. Mỗi ngày có thể có hàng nghìn sự kiện. Nếu chương trình tải hết mọi row vào một danh sách rồi mới phản hồi, RAM, thời gian chờ và số lượng request đang bay (*in-flight*) đều có thể tăng mạnh. Khi nhiều khách hàng đồng thời truy vấn, ứng dụng còn gây thêm áp lực lên coordinator và những replica chứa partition tương ứng.

Apache Cassandra trả dữ liệu theo **các trang (pages)** qua native protocol. Java Driver 4.x hỗ trợ đọc bất đồng bộ bằng **executeAsync**, kết quả ban đầu là **AsyncResultSet** của trang hiện tại. Chương trình tự quyết định **có tiếp tục lấy trang kế tiếp không**, xử lý dữ liệu mỗi trang và kết hợp chúng bằng **CompletionStage**.

Ba tên API cần nhớ:

- **currentPage():** tập các row của **trang hiện tại**.
- **hasMorePages():** cho biết còn trang tiếp theo để lấy hay không.
- **fetchNextPage():** khởi tạo việc lấy **trang tiếp theo một cách bất đồng bộ**, trả về một stage của **AsyncResultSet mới**.

Mục tiêu của bài:

1. Hiểu một lời gọi **executeAsync** không đồng nghĩa toàn bộ kết quả đã được tải.
2. Duyệt nhiều trang với **hasMorePages/fetchNextPage** đúng thứ tự, không chặn thread đợi I/O.
3. **Kết hợp các trang** thành tập kết quả có giới hạn hoặc thống kê gộp có bộ nhớ hằng số.
4. Kết hợp xử lý bất đồng bộ cho từng row với việc yêu cầu trang kế tiếp đúng thời điểm.
5. Tránh truy vấn/quá nhiều trang làm tăng tải Cassandra và xử lý đúng timeout, cancel, retry.
6. Phân biệt phân trang async và **Reactive Streams**, cùng giới hạn của paging state khi dữ liệu thay đổi.

Ví dụ dùng **Java Driver 4.x** (package **com.datastax.oss.driver.api**), **CompletionStage** và **CompletableFuture**. Các đoạn code là minh họa cần chạy thử với bản driver/JDK/Cassandra đang sử dụng; những trường hợp yêu cầu cấu hình TLS/auth đã được ghi rõ.

## 2. Page là gì trong Cassandra?

### 2.1. Một truy vấn có thể trải qua nhiều lần lấy dữ liệu

Trong Cassandra, một statement trả về nhiều row có thể được server chia thành nhiều page. Kích thước trang cấu hình ở driver/statement là một **mức yêu cầu (page-size hint)** về lượng row cần trả mỗi lần, **không phải bảo đảm mỗi trang có đúng bấy nhiêu row**.

~~~mermaid
sequenceDiagram
    participant J as Java service
    participant D as Java Driver
    participant C as Cassandra coordinator
    J->>D: executeAsync(statement)
    D->>C: CQL request + page size
    C-->>D: Trang 1 + trạng thái phân trang
    D-->>J: AsyncResultSet trang 1
    J->>J: currentPage()
    J->>J: hasMorePages() == true
    J->>D: fetchNextPage()
    D->>C: Yêu cầu trang kế tiếp
    C-->>D: Trang 2 + trạng thái phân trang
    D-->>J: AsyncResultSet trang 2
    J->>J: Xử lý trang 2
~~~

**Trang đầu** được nhận qua stage do **executeAsync** trả về. **Trang sau** chỉ được yêu cầu khi mã ứng dụng gọi **fetchNextPage** trên result set thích hợp. Mỗi stage hoàn thành khi kết quả trang tương ứng có thể xử lý, không phải khi toàn bộ truy vấn hoàn tất.

### 2.2. Những điều không nên giả định

- **currentPage()** không đại diện cho toàn bộ các row của truy vấn nếu **hasMorePages() = true**.
- **hasMorePages() = true** không có nghĩa trang kế tiếp chắc chắn chứa số row bằng page size; một trang có thể ngắn hoặc trong một số đường truy vấn có thể rỗng nhưng vẫn còn khả năng lấy tiếp.
- **fetchNextPage()** không phải thao tác thuần xử lý bộ nhớ: nó có thể tạo I/O, tốn tài nguyên coordinator/replica và gặp lỗi.
- **page size** khác **CQL LIMIT**: page size điều khiển cách chia kết quả thành các lần lấy; LIMIT giới hạn tổng số row mà truy vấn được yêu cầu trả về.
- **Page tiếp theo** không phải “trang số 2” dùng offset theo kiểu SQL truyền thống. Cassandra dùng trạng thái phân trang, không nên xây API offset vô hạn trên mô hình này.
- Kết quả của nhiều page **không phải snapshot transactionally consistent** nếu dữ liệu đang thay đổi trong khi duyệt.

### 2.3. Bảng đối chiếu API

| API | Trả về | Ý nghĩa và thời điểm gọi |
|---|---|---|
| **session.executeAsync(statement)** | **CompletionStage<AsyncResultSet>** | Bắt đầu truy vấn và nhận **trang đầu tiên** |
| **result.currentPage()** | **Iterable<Row>** | Duyệt row đã có trong trang hiện tại |
| **result.hasMorePages()** | **boolean** | Hỏi liệu còn trang để yêu cầu tiếp |
| **result.fetchNextPage()** | **CompletionStage<AsyncResultSet>** | Lấy trang mới nếu hasMorePages là true |
| **statement.setPageSize(n)** | Statement mới | Đặt page size cho request |
| **statement.setConsistencyLevel(CL)** | Statement mới | Đặt yêu cầu phản hồi replica |
| **statement.setExecutionProfileName(name)** | Statement mới | Chọn profile chứa mặc định timeout/CL/page-size... |

Trong Java Driver 4.x, statement theo hướng **immutable**: phải dùng giá trị **trả về** của các setter. Gọi setter rồi bỏ kết quả là một lỗi phổ biến khi cấu hình page size hoặc consistency.

## 3. Mô hình CQL phù hợp để thử nghiệm phân trang

Thiết kế bảng theo truy vấn **“liệt kê sự kiện của một tenant trong một ngày, từ mới đến cũ”**:

~~~sql
-- Tạo trên môi trường lab; cần đủ node/DC phù hợp RF.
CREATE KEYSPACE IF NOT EXISTS event_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS event_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

**Giải thích primary key:**

- **(tenant_id, event_day)** là **composite partition key**. Truy vấn nên bind đủ hai thành phần để xác định partition; driver có thể tính routing key và chọn coordinator gần các replica sở hữu token.
- **happened_at, event_id** là **clustering columns**. Thứ tự do clustering order xác định; hai row cùng timestamp vẫn có **event_id** để phân biệt.
- **event_day** là bucket theo ngày, giới hạn lịch sử trong một partition. Nếu một tenant ghi quá nhiều sự kiện/ngày, cần xét bucket theo giờ hoặc thêm shard; **paging không cứu được một partition quá lớn**.
- **event_type/payload** là dữ liệu đọc từ bảng theo access pattern. Không đưa payload nhạy cảm vào log ví dụ.

Dữ liệu fixture:

~~~sql
INSERT INTO event_lab.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED',
    '{"id":"demo-1"}'
);

INSERT INTO event_lab.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:01:00Z',
    33333333-3333-4333-8333-333333333333,
    'PAYMENT_PENDING',
    '{"id":"demo-1"}'
);
~~~

Muốn nhìn thấy **nhiều trang**, tạo thêm nhiều fixture trên môi trường thử nghiệm rồi chọn page size nhỏ. Không cần dùng **ALLOW FILTERING** hoặc quét toàn bảng để học phân trang.

### 3.1. Prepared query có LIMIT

~~~sql
SELECT happened_at, event_id, event_type
FROM event_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

CQL trên dùng **bind markers** nên dành cho prepared statement trong Java. Với cqlsh trực tiếp, thay marker bằng literal hợp lệ.

**LIMIT 300** nghĩa là truy vấn tối đa 300 row theo ngữ nghĩa CQL, **không** nghĩa 300 row được trả trong một trang. Nếu **setPageSize(40)**, driver có thể cần nhiều lần lấy trang trước khi đạt giới hạn, nhưng số trang thực không nhất thiết bằng chính xác **ceil(300/40)**.

## 4. Ví dụ tối thiểu với hasMorePages/fetchNextPage

Đoạn sau lấy tối đa 300 event và in thống kê số row **trên từng page**. Phần xử lý chỉ làm việc nhẹ; đây là ví dụ mô tả luồng, không phải cách dựng dịch vụ dài hạn.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public class AsyncPageBasics {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Đoạn main này dùng join ở RANH GIỚI chương trình demo,
        // không dùng join/get bên trong xử lý page bất đồng bộ.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM event_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement statement = query
                .bind(tenantId, day, 300)
                .setPageSize(40)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            session.executeAsync(statement)
                .thenCompose(page -> visitPages(page, 1))
                .toCompletableFuture()
                .join();
        }
    }

    private static CompletionStage<Void> visitPages(
            AsyncResultSet page, int pageNumber) {

        int rowsInPage = 0;
        for (Row row : page.currentPage()) {
            if (row.getUuid("event_id") == null) {
                throw new IllegalStateException(
                    "Event fixture thiếu event_id");
            }
            rowsInPage++;
        }

        System.out.println("Page " + pageNumber +
                           ": " + rowsInPage + " rows");

        if (!page.hasMorePages()) {
            return java.util.concurrent.CompletableFuture
                .completedFuture(null);
        }

        return page.fetchNextPage()
            .thenCompose(next ->
                visitPages(next, pageNumber + 1));
    }
}
~~~

**Diễn giải theo thứ tự:**

1. **executeAsync(statement)** trả stage cho trang đầu.
2. **thenCompose** nhận một **AsyncResultSet** sau khi stage hoàn thành.
3. **currentPage()** được duyệt một lần để xử lý row của trang đó.
4. **hasMorePages()** quyết định có cần I/O lấy trang mới hay không.
5. **fetchNextPage()** trả stage cho trang tiếp; **thenCompose** tiếp tục chuỗi khi trang mới đến.
6. Kết quả ngoài cùng chỉ hoàn thành khi **trang cuối đã được xử lý**, hoặc hoàn thành thất bại nếu bất kỳ stage nào gặp lỗi.

Trong ví dụ, **join()** chỉ ở cuối **main** nhằm giữ session sống tới khi demo hoàn tất. **Không gọi join/get** trong callback, thread I/O của driver, event loop hoặc một HTTP handler bất đồng bộ.

**Hạn chế:** Hàm **visitPages** dùng cách gọi đệ quy bất đồng bộ để minh họa rõ API. Với số lượng trang cực lớn, cần tránh callback quá nặng, giữ danh sách/reference không cần thiết, hoặc xây chuỗi đồng bộ quá sâu nếu stage hoàn thành ngay. Có thể dùng processor/trampoline, bounded executor hoặc Reactive Streams để xử lý dòng rất dài một cách có kiểm soát. **Không coi ví dụ console là bộ điều phối production hoàn chỉnh.**

## 5. Gộp các trang thành danh sách có giới hạn

Nhu cầu thường gặp: tạo một endpoint trả **tối đa N event ID** để hiển thị. Ta có thể kết hợp nhiều trang thành một list, nhưng phải có **giới hạn bộ nhớ**.

### 5.1. Hàm thu thập tối đa N phần tử

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class BoundedPageCollector {
    public static CompletionStage<List<UUID>> collect(
            CompletionStage<AsyncResultSet> firstPage,
            int maxRows) {

        if (maxRows <= 0) {
            throw new IllegalArgumentException(
                "maxRows must be positive");
        }

        return firstPage.thenCompose(page ->
            append(page, new ArrayList<>(), maxRows));
    }

    private static CompletionStage<List<UUID>> append(
            AsyncResultSet page,
            List<UUID> collected,
            int maxRows) {

        for (Row row : page.currentPage()) {
            if (collected.size() >= maxRows) {
                break;
            }
            collected.add(row.getUuid("event_id"));
        }

        if (collected.size() >= maxRows ||
                !page.hasMorePages()) {
            return CompletableFuture.completedFuture(
                java.util.Collections.unmodifiableList(
                    new ArrayList<>(collected)));
        }

        return page.fetchNextPage()
            .thenCompose(next ->
                append(next, collected, maxRows));
    }
}
~~~

Sử dụng:

~~~java
BoundStatement statement = prepared.bind(tenantId, day, 1000)
    .setPageSize(64)
    .setIdempotent(true);

CompletionStage<List<UUID>> ids =
    BoundedPageCollector.collect(
        session.executeAsync(statement), 150);
~~~

**Bất biến quan trọng:** chỉ một nhánh continuation cập nhật **collected**, và trang tiếp theo chỉ được yêu cầu **sau** khi đã xử lý trang hiện tại. Nếu tự chạy nhiều nhánh ghi chung vào ArrayList, sẽ có race condition và thứ tự không còn xác định.

Trong ví dụ này, danh sách kết quả có tối đa **150 UUID**; server có thể đã trả một page chứa nhiều row hơn số cần dùng, nhưng **không tiếp tục fetch** khi đạt giới hạn. Mức giới hạn nên do tầng service/API phê duyệt, thay vì để client truyền vô hạn.

### 5.2. Vì sao không luôn trả List của toàn bộ dataset?

Giả sử endpoint có 100.000 row; mỗi row ứng dụng giữ lại một object 1 KiB:

~~~text
100.000 row × 1 KiB ≈ 97,7 MiB dữ liệu thô

Chưa tính:
- Java object headers / reference arrays;
- chuỗi, UUID, DTO, buffers của driver;
- nhiều request đồng thời;
- hàng đợi và dữ liệu trung gian cho serialize response.
~~~

Khi 100 request cùng giữ danh sách lớn, khả năng OOM tăng rất nhanh. Nếu nghiệp vụ cần xử lý toàn bộ dữ liệu, nên **tổng hợp số liệu**, **stream ra nơi nhận có backpressure** hoặc chạy **batch job có giới hạn** thay vì trả một list vô hạn cho HTTP request.

## 6. Gộp nhiều page thành một kết quả thống kê

Một cách tránh tích lũy row là **fold/reduce**: xử lý mỗi trang và giữ vài biến thống kê. Ví dụ đếm tổng số event theo kiểu dữ liệu/kiểu thao tác.

### 6.1. Bản tối giản: cộng tổng số row

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

static CompletionStage<Long> countPages(
        AsyncResultSet page, long previousCount) {

    long total = previousCount;
    for (Row ignored : page.currentPage()) {
        total++;
    }

    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(total);
    }

    final long nextTotal = total;
    return page.fetchNextPage()
        .thenCompose(next -> countPages(next, nextTotal));
}
~~~

Ý tưởng là **O(1) bộ nhớ cho bộ tổng hợp**, không phải O(số hàng) như collector. Tuy nhiên, code đếm ở client này phải đọc toàn bộ row, tốn băng thông và I/O; **không phải giải pháp thay thế cho chỉ số/counter nghiệp vụ** nếu hệ thống cần đếm thường xuyên ở quy mô rất lớn. CQL **COUNT(*)** trên tập lớn cũng cần cân nhắc chi phí. Hãy thiết kế bảng tổng hợp theo access pattern nếu đây là yêu cầu thường xuyên.

### 6.2. Tách xử lý CPU khỏi callback của driver

Nếu mỗi trang cần tính toán đáng kể hoặc chuyển đổi nhiều DTO, đừng làm công việc nặng trong callback có thể chạy trên thread I/O của driver. Có thể đưa xử lý sang một **Executor** riêng có giới hạn.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

static CompletionStage<Long> countWithExecutor(
        AsyncResultSet page,
        long countSoFar,
        Executor processingPool) {

    return CompletableFuture.supplyAsync(() -> {
        long total = countSoFar;
        for (Row ignored : page.currentPage()) {
            // Giả sử tại đây còn có công việc tính toán CPU.
            total++;
        }
        return total;
    }, processingPool).thenCompose(total -> {
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(total);
        }
        return page.fetchNextPage()
            .thenCompose(next ->
                countWithExecutor(next, total, processingPool));
    });
}
~~~

Mỗi page chỉ được yêu cầu tiếp **sau khi page hiện tại xử lý xong**. Điều này giúp tạo một dạng backpressure tự nhiên giữa Cassandra và downstream.

**Lưu ý:** Executor cần cấu hình **số thread/queue hữu hạn**; việc đưa mọi page vào một thread pool có hàng đợi không giới hạn vẫn có thể gây OOM. Tránh làm blocking disk/HTTP gọi bên ngoài trong driver callback; nếu cần I/O downstream, kết hợp các stage bất đồng bộ của downstream và chỉ fetch trang kế khi downstream xác nhận đã xử lý.

### 6.3. Một lỗi hay gặp: thenApply thay cho thenCompose

Khi lambda trả về một **CompletionStage**, **thenApply** có thể tạo stage lồng nhau:

~~~java
// Kết quả mang dạng CompletionStage<CompletionStage<Long>>:
 CompletionStage<CompletionStage<Long>> nested = session.executeAsync(statement)
    .thenApply(firstPage ->
        countPages(firstPage, 0L));
~~~

Dùng **thenCompose** để “làm phẳng”:

~~~java
// Kết quả là CompletionStage<Long>:
CompletionStage<Long> flat = session.executeAsync(statement)
    .thenCompose(firstPage ->
        countPages(firstPage, 0L));
~~~

Quy tắc:

- **thenApply:** chuyển một giá trị thành một giá trị khác, ví dụ **AsyncResultSet → Integer**.
- **thenCompose:** khi hàm chuyển đổi **trả về một CompletionStage khác**, cần nối phần công việc bất đồng bộ bên trong.

## 7. Chỉ fetch sau khi downstream xử lý xong

Giả sử cần ghi từng event vào một dịch vụ xử lý khác, và phương thức downstream trả về **CompletionStage<Void>** sau khi một row đã được chấp nhận. Khi đó cần duy trì **thứ tự xử lý tuần tự** để không làm tràn downstream.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.function.Function;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

static CompletionStage<Void> drain(
        AsyncResultSet page,
        Function<Row, CompletionStage<Void>> sink) {

    CompletionStage<Void> chain =
        CompletableFuture.completedFuture(null);

    for (Row row : page.currentPage()) {
        chain = chain.thenCompose(ignored -> sink.apply(row));
    }

    return chain.thenCompose(ignored -> {
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(null);
        }
        return page.fetchNextPage()
            .thenCompose(next -> drain(next, sink));
    });
}
~~~

**Đặc điểm:**

- **sink** cần cung cấp xử lý bất đồng bộ; nếu nó **block** hoặc chạy CPU nặng, phải dùng executor thích hợp và cơ chế giới hạn công việc.
- Các row trong cùng page được chuyển vào chuỗi stage theo thứ tự lặp. Trang kế tiếp **chỉ được yêu cầu sau khi sink xử lý xong tất cả row của trang này**.
- Nếu một row thất bại, stage chain hoàn thành thất bại và **không fetch trang tiếp theo** theo luồng bình thường.
- Trong một hệ thật, cần chính sách cho row lỗi: dừng cả job, lưu checkpoint, dead-letter, retry có giới hạn hoặc bù nghiệp vụ. Không tự động bỏ qua mọi exception.
- Cấu trúc stage chain có thể tạo nhiều đối tượng khi page size lớn; kiểm thử bộ nhớ và dùng một worker/processor riêng hoặc thư viện reactive khi cần xử lý luồng rất dài.
- Đừng suy ra từ việc sink trả thành công rằng dữ liệu downstream đã bền vững, trừ khi **hợp đồng của sink** bảo đảm điều đó.

### 7.1. Backpressure nội bộ và tốc độ truy vấn

Nếu downstream chỉ xử lý được 200 row/giây nhưng Cassandra trả page chứa 1.000 row, ứng dụng sẽ giữ trang đó cho tới khi xử lý hết. Đây vẫn là **bộ đệm hữu hạn** nếu page size và số query đồng thời có giới hạn.

Không nên gọi **fetchNextPage()** ngay khi vừa nhận page, rồi yêu cầu liên tục nhiều page để “đẩy trước” trong khi sink chậm. Prefetch vô hạn có thể làm dữ liệu tồn đọng ở client, tăng bộ nhớ và khiến coordinator/replica chịu nhiều tải không cần thiết.

## 8. Không lấy nhiều trang của một cursor bằng cách chạy song song

Một câu query phân trang có **trạng thái nối tiếp**: trang sau phụ thuộc vào paging state của trang trước. Mẫu an toàn là:

~~~text
executeAsync()
  → xử lý currentPage()
  → hasMorePages()?
       → fetchNextPage()
       → xử lý currentPage() của AsyncResultSet mới
       → ...
~~~

**Không nên** gọi nhiều lần **fetchNextPage()** trên cùng đối tượng rồi coi chúng là “trang 2, 3, 4” khác nhau. Đây không phải API cấp phát offset/trang độc lập để xử lý song song. Không có cơ sở để giả định mỗi lời gọi lặp trên cùng page sẽ trả một page tiếp khác biệt theo ý muốn.

Nếu cần song song để tăng thông lượng, hãy tách thành **nhiều truy vấn độc lập** theo partition key/bucket/token-range mà mô hình dữ liệu hỗ trợ; mỗi truy vấn tự quản lý chuỗi page và số truy vấn đồng thời phải có giới hạn.

### 8.1. Hai partition độc lập và thenCombine

Ví dụ ứng dụng cần đọc tối đa 100 event ID của **hai ngày khác nhau**. Mỗi partition có thể được truy vấn độc lập:

~~~java
CompletionStage<List<UUID>> dayOne =
    BoundedPageCollector.collect(
        session.executeAsync(statementForDayOne), 100);

CompletionStage<List<UUID>> dayTwo =
    BoundedPageCollector.collect(
        session.executeAsync(statementForDayTwo), 100);

CompletionStage<List<UUID>> combined =
    dayOne.thenCombine(dayTwo, (left, right) -> {
        List<UUID> merged = new ArrayList<>(
            left.size() + right.size());
        merged.addAll(left);
        merged.addAll(right);
        return java.util.Collections.unmodifiableList(merged);
    });
~~~

Đoạn này giả định hai statement đã được bind đủ khóa cho hai partition. **thenCombine** đợi cả hai công việc hoàn thành, rồi hợp nhất hai list. Tuy nhiên:

- Kết quả **left + right** là nối danh sách, **không tự sắp xếp toàn cục theo timestamp**. Nếu cần thứ tự thời gian toàn cục, đọc cả timestamp, dùng comparator rõ ràng rồi giới hạn số row.
- Chỉ nên chạy **số lượng truy vấn song song có giới hạn**. Không tạo hàng nghìn partition query cùng lúc mà không admission control.
- Hai partition có thể đang thay đổi ở các thời điểm khác nhau, nên không có snapshot atomic toàn bộ hai truy vấn.
- Nếu một stage thất bại, **combined** cũng thất bại trừ khi ứng dụng có chính sách xử lý partial results được định nghĩa rõ.

## 9. Bounded concurrency trên nhiều truy vấn

Đọc từng page tuần tự **trong một query** không giới hạn số query có thể được phát đồng thời. Ví dụ 1.000 HTTP requests mỗi request đang giữ một trang vẫn có thể gây 1.000 request tới Cassandra.

Có thể giới hạn **số pipeline truy vấn đang hoạt động** bằng semaphore:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class BoundedPagedQueries {
    private final CqlSession session;
    private final Semaphore permits;

    public BoundedPagedQueries(CqlSession session, int maxActive) {
        if (maxActive <= 0) {
            throw new IllegalArgumentException(
                "maxActive must be positive");
        }
        this.session = session;
        this.permits = new Semaphore(maxActive);
    }

    public CompletionStage<List<UUID>> query(
            BoundStatement statement,
            int maxRows) {

        if (!permits.tryAcquire()) {
            CompletableFuture<List<UUID>> failed =
                new CompletableFuture<>();
            failed.completeExceptionally(
                new RejectedExecutionException(
                    "Paged-query concurrency limit reached"));
            return failed;
        }

        try {
            return BoundedPageCollector.collect(
                    session.executeAsync(statement), maxRows)
                .whenComplete((result, error) ->
                    permits.release());
        } catch (RuntimeException error) {
            permits.release();
            throw error;
        }
    }
}
~~~

**Ưu điểm:** permit được giữ cho **toàn bộ chuỗi page**, không chỉ request lấy trang đầu. Nếu downstream chậm, số pipeline đồng thời bị giới hạn.

**Giới hạn cần biết:**

- Đây là giới hạn **trên một Java process**; 20 instance × 50 permit có thể tạo tới 1.000 pipeline đồng thời. Cần cân nhắc quota toàn dịch vụ/tenant.
- **RejectedExecutionException** là tín hiệu từ **client-side admission**, không phải **OverloadedException** do Cassandra trả về.
- Không giữ permit nếu người gọi bỏ qua việc hoàn thành pipeline hoặc tạo stage không bao giờ hoàn thành; cần timeout/cancellation strategy theo môi trường.
- **maxRows** phải có giới hạn từ API và cấu hình tin cậy; không nhận giá trị vô hạn từ client.
- Nếu một pipeline lấy rất nhiều page, nó chiếm permit lâu; cần chia workload batch và áp fair scheduling khi có nhiều loại khách hàng.
- Để kiểm soát tốc độ I/O thực sự, kết hợp giới hạn pipeline với timeout, retry budget và page-size phù hợp.

## 10. Lỗi khi fetch trang thứ N

Một chuỗi paged query có thể trả thành công **trang 1, 2, 3**, rồi **trang 4 thất bại** vì read timeout, read failure, unavailable, overloaded hoặc lỗi mạng/driver. Như vậy:

- Những row từ trang 1–3 đã được ứng dụng **xem hoặc xử lý** không có nghĩa toàn bộ query đã hoàn tất.
- Nếu sink đã phát sinh side effect, không thể “tự động rollback” chỉ vì fetch trang 4 thất bại.
- Retry toàn bộ query có thể đọc lại các row trước đó. Nếu sink không idempotent, dữ liệu downstream có thể bị xử lý hai lần.
- Nếu dữ liệu Cassandra đang thay đổi, chạy lại query từ đầu có thể thấy tập dữ liệu khác với lượt trước.

### 10.1. CompletionStage truyền lỗi như thế nào?

~~~java
CompletionStage<List<UUID>> result =
    BoundedPageCollector.collect(
        session.executeAsync(statement), 200);

CompletionStage<List<UUID>> handled =
    result.whenComplete((ids, error) -> {
        if (error != null) {
            // Chỉ ghi operation, exception class, trace ID có kiểm soát.
            System.err.println(
                "Paged query failed: " +
                error.getClass().getSimpleName());
        } else {
            System.out.println("Collected " +
                               ids.size() + " event IDs");
        }
    });
~~~

**whenComplete** là cách quan sát trạng thái kết thúc; nó không tự sửa lỗi. Nếu muốn cung cấp fallback, phải xác định **ngữ nghĩa rõ ràng**. Ví dụ trả danh sách một phần sau khi fetch thất bại có thể khiến API nhầm kết quả thiếu là kết quả đầy đủ.

### 10.2. Xử lý partial processing

Với các pipeline ghi sang nơi khác, cần quyết định:

| Loại công việc | Khi trang N thất bại | Chính sách an toàn hơn |
|---|---|---|
| Endpoint HTTP yêu cầu danh sách đủ | Trả lỗi thay vì trả dữ liệu thiếu mà không báo | Gắn deadline, giới hạn page/row, dùng resume token hợp lệ khi được thiết kế |
| ETL idempotent | Giữ checkpoint/ID đã xử lý | Tiếp tục từ checkpoint đã xác minh và chống trùng ở sink |
| Gửi email/thanh toán theo row | Không retry từ đầu mù | Dùng business idempotency key hoặc outbox; ghi trạng thái riêng |
| Báo cáo tổng hợp | Không đánh dấu COMPLETE | Giữ kết quả tạm với trạng thái INCOMPLETE, chạy lại có kiểm soát |
| Batch phân tán nhiều partition | Không giả định các nhánh có snapshot chung | Thiết kế reconciliation và kiểm thử tính đúng đắn liên partition |

**CompletionStage hoàn thành lỗi** không nhất thiết trả lại nguyên nhân trực tiếp: trong các API như **CompletableFuture.join**, lỗi có thể được bọc bởi **CompletionException**. Khi logging hoặc phân loại, nên kiểm tra cause một cách an toàn để phân biệt timeout từ driver với lỗi domain.

### 10.3. Không lạm dụng retry

Các nguyên tắc:

1. Chỉ retry khi thao tác **idempotent** và lỗi có khả năng tạm thời, trong deadline.
2. Không tăng số retry vô hạn khi Cassandra trả **Overloaded/Unavailable**.
3. Dùng backoff/jitter và retry budget để tránh retry storm.
4. Cân nhắc chính sách retry mặc định của driver: nếu cả driver và application cùng retry, lượng tải có thể nhân nhiều lần.
5. **Không hạ LOCAL_QUORUM xuống ONE** như fallback tự động nếu API có hợp đồng nhất quán.
6. Với sink có side effect, phân biệt checkpoint **đã xử lý bền vững** với **đã thấy row trong bộ nhớ**.

## 11. Paging state và token tiếp tục: không phải OFFSET

Trong phân trang CQL, trạng thái tiếp tục được driver/server sử dụng để lấy phần kết quả kế tiếp. **Paging state là opaque**: không nên tự phân tích byte của nó thành offset, primary key hay vị trí có thể tính toán được.

### 11.1. Những ràng buộc khi lưu paging state

Nếu API muốn cho người dùng “bấm tiếp trang sau” giữa các HTTP requests, phải thiết kế một **continuation token** với các ràng buộc:

- Gắn token với **statement CQL cụ thể, đúng bind values, schema, page settings và ngữ cảnh người dùng**.
- Không nhận paging state của người dùng không tin cậy rồi đưa nguyên vào driver mà bỏ qua **xác thực và kiểm soát phạm vi truy cập**.
- Bảo vệ integrity/chữ ký của token, đặt hạn sử dụng và chính sách vô hiệu hóa khi query/schema thay đổi.
- Không suy paging state an toàn/vĩnh viễn qua mọi phiên bản driver/server hoặc thay đổi data model.
- Không log token/raw bind values vào telemetry công khai.
- Dữ liệu có thể bị INSERT/UPDATE/DELETE/TTL/compaction trong lúc phân trang; **paging state không tạo một snapshot nhất quán**.

Với yêu cầu duyệt **một partition có thứ tự clustering**, một thiết kế khác là **keyset pagination** dựa trên last-seen clustering key, được viết theo chính xác access pattern. Cách này cũng cần xử lý row mới/xóa, nhưng có thể minh bạch hơn việc trưng ra paging state thô cho client.

### 11.2. LIMIT, page size và business cutoff

Giả sử API trả các sự kiện trước một mốc thời gian:

~~~sql
SELECT happened_at, event_id, event_type
FROM event_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND happened_at <= ?
LIMIT ?;
~~~

Điều kiện trên **giới hạn phạm vi clustering** theo thời gian cho partition đã định. Nó giúp khóa cửa sổ dữ liệu cần duyệt ở mức **giá trị thời gian**, nhưng không bảo đảm snapshot transactionally consistent nếu row cũ bị cập nhật/xóa trong lúc query đang chạy. Nếu cần export có tính toàn vẹn ở một mốc, phải có **application barrier/cutoff**, backup/CDC hoặc quy trình nghiệp vụ phù hợp.

## 12. Async paging không đồng nghĩa Reactive Streams

Cả hai hướng đều tránh blocking cho I/O Cassandra, nhưng mô hình tiêu thụ khác nhau.

| Đặc điểm | AsyncResultSet + CompletionStage | Reactive Streams |
|---|---|---|
| Đơn vị lập trình | Stage của một trang và callback/continuation | Publisher/Subscriber, yêu cầu theo demand |
| Lấy trang tiếp | **hasMorePages + fetchNextPage** tường minh | Driver/reactive adapter quản lý luồng theo yêu cầu của subscriber |
| Backpressure | Do ứng dụng thiết kế: page size, sink stage, giới hạn query | Là phần của hợp đồng demand nếu triển khai đúng |
| Phối hợp async | **thenCompose, thenCombine, whenComplete** | Các phép biến đổi/ghép luồng của framework |
| Rủi ro | Fetch quá sớm, giữ danh sách lớn, callback block | Subscriber demand/cancellation sai, operator buffer không giới hạn |
| Khi phù hợp | Workflow Java dùng CompletableFuture, batch/job/HTTP async đơn giản | Pipeline streaming nhiều phép biến đổi, framework Reactor/Rx/Reactive Streams |

Java Driver 4.x có API reactive trong những cấu hình/phiên bản hỗ trợ; việc tích hợp với Reactor hoặc framework khác phụ thuộc dependency và hợp đồng của publisher. **Không kết luận rằng cứ đặt tên “reactive” thì hệ thống tự bảo đảm memory nhỏ hoặc tự retry an toàn**. Một operator buffer/collectList không có giới hạn vẫn có thể giữ toàn bộ dataset trong RAM.

Nếu dịch vụ đã dùng **CompletionStage**, việc quản lý rõ từng page thường là phương án đủ tốt cho truy vấn có giới hạn. Nếu yêu cầu điều tiết theo từng row từ downstream hoặc tích hợp một pipeline reactive lớn, hãy cân nhắc API reactive và thử backpressure/cancellation thực tế.

## 13. Cancellation, session lifecycle và timeout

### 13.1. Caller không còn đợi

Một request HTTP có thể bị hủy trước khi đọc hết các trang. Mã ứng dụng nên dừng yêu cầu **trang tiếp theo** khi biết caller không còn cần dữ liệu.

Tuy nhiên, hủy một **CompletableFuture** hoặc dừng continuation **không bảo đảm request đã gửi tới Cassandra bị thu hồi khỏi coordinator/replica**. Cũng không hoàn tác mutation hay công việc server đã chạy. Cần phân biệt:

- **Không fetch nữa:** có thể ngăn các page I/O mới từ pipeline hiện tại.
- **Hủy một stage ở client:** ảnh hưởng cách client tiếp tục xử lý; không mặc nhiên là cơ chế rollback server.
- **Driver/server timeout:** có thể xảy ra trong khi coordinator vẫn đang xử lý hoặc đã hoàn thành.
- **Hủy downstream:** phải giải phóng permit/queue/resource đúng theo vòng đời của ứng dụng.

### 13.2. Giữ CqlSession sống đủ lâu

Một lỗi phổ biến:

~~~java
CompletionStage<AsyncResultSet> stage;
try (CqlSession s = buildSession()) {
    stage = s.executeAsync(statement);
}
// Session đã đóng; chuỗi fetch các trang tiếp theo
// có thể không còn dùng được dù stage đầu từng thành công.
~~~

**Không đóng CqlSession ngay sau khi khởi động async query.** Cần cho toàn bộ chuỗi page kết thúc hoặc bị hủy có kiểm soát rồi mới đóng session. Trong web service, **CqlSession thường là resource dùng chung dài hạn**, không tạo/đóng theo từng HTTP request.

### 13.3. Deadline end-to-end

Nếu HTTP endpoint chỉ có deadline 2 giây nhưng một job phân trang dự kiến 10 giây, chạy hết chuỗi page để rồi bỏ kết quả là lãng phí. Đặt ngân sách thời gian:

~~~text
Deadline của caller
  = chờ queue / admission
  + request trang đầu
  + các lần fetch trang tiếp
  + xử lý từng trang/downstream
  + retry/backoff nếu có
  + serialization response
~~~

**Timeout của mỗi lần fetch** không tự cộng thành một **deadline end-to-end** hợp lý. Theo dõi thời gian bắt đầu request nghiệp vụ và quyết định có tiếp tục fetch hay không trước khi gọi trang kế.

## 14. Liên hệ consistency level, routing và mô hình wide-column

### 14.1. Page size không thay consistency

Với RF = 3 ở **dc1**, một **LOCAL_QUORUM read** thường cần phản hồi từ đa số replica trong local DC. Việc đặt **pageSize(32)** không làm yêu cầu CL giảm xuống ONE. Mỗi bước lấy page vẫn phụ thuộc điều kiện request/server theo ngữ nghĩa truy vấn.

Nếu một replica bị GC pause, disk I/O bão hòa hoặc có vấn đề mạng, **fetchNextPage** có thể timeout dù trang trước đọc được. Vì vậy cần quan sát **error theo từng page**, không chỉ thành công của executeAsync.

### 14.2. Paging không sửa sai partition key

Một query thiếu thành phần của **(tenant_id, event_day)** có thể không hợp lệ hoặc tạo đường truy vấn tốn tài nguyên nếu được phép bằng cơ chế khác. **Paging không tự biến truy vấn quét thành truy vấn định tuyến tối ưu**.

Khi muốn đọc nhiều ngày, có thể phát nhiều query theo các bucket ngày rồi gộp kết quả có giới hạn, nhưng:

- Mỗi query nên bind đủ partition key.
- Số query đồng thời phải giới hạn.
- Nếu cần thứ tự toàn cục, merge theo **happened_at + event_id** sau khi lấy các phần dữ liệu phù hợp, không chỉ nối list.
- Không tự suy dữ liệu đồng nhất một thời điểm giữa nhiều partition.

### 14.3. Compaction, repair và tombstone

Cassandra đọc qua memtable/SSTable; compaction và repair có thể cạnh tranh tài nguyên với fetch page. Dữ liệu nhiều tombstone, partition cực lớn hoặc collection nặng có thể khiến page chậm/rỗng bất thường và tăng timeout.

**Không giải quyết bằng cách tăng page size vô hạn.** Page lớn hơn có thể giảm số lượt round trip nhưng cũng tăng payload, buffering, CPU/GC và tail latency. Cần đo p95/p99 và kích thước dữ liệu thực để chọn page size hợp lý.

Repair giúp hội tụ các replica theo cơ chế Cassandra; không tạo snapshot cho pipeline phân trang và không làm các page đã xử lý trở thành một transaction.

## 15. Cách chọn page size và giới hạn dữ liệu

| Hoàn cảnh | Hướng lựa chọn | Rủi ro phải quan sát |
|---|---|---|
| HTTP API trả 20–100 row | Page size vừa phải, có LIMIT và giới hạn response | Tốn round trip nếu quá nhỏ, RAM nếu quá lớn |
| Query trả row rất lớn | Page size nhỏ hơn và theo dõi byte thực | Page size tính theo row, không phải giới hạn byte chính xác |
| Batch ETL có sink chậm | Process page tuần tự, chờ sink rồi fetch | Giữ page trong RAM quá lâu, timeout, checkpoint |
| UI phân trang nhiều request | Continuation token có xác thực hoặc keyset theo clustering | Paging state không phải offset/snapshot |
| Quét nhiều partition/bucket | Giới hạn concurrency, merge rõ thứ tự | Hot partition, fan-out, tổng in-flight |
| LWT hoặc ghi có side effect | Không dùng mô hình read paging để suy atomicity | Retry/timeout outcome không rõ |

**Đừng xem con số 100, 500 hay 5.000 là “page size chuẩn Cassandra”.** Hệ thống phải đo trên **row size, payload, CL, network, GC, workload và SLA**. Có thể bắt đầu từ giá trị thận trọng trong lab rồi tăng/giảm sau benchmark. Đồng thời giới hạn **số row và số page tối đa mà một request nghiệp vụ được phép tiêu thụ** nếu SLA yêu cầu.

### 15.1. Page rỗng nhưng chưa hết

Một loop sai có thể dừng khi **currentPage()** rỗng:

~~~text
Nếu số hàng trang hiện tại == 0 thì dừng.
~~~

Cách này không bảo đảm đúng trong mọi đường truy vấn. Điều kiện điều khiển **có còn trang không** là **hasMorePages()**, không phải số lượng row của trang hiện tại. Với truy vấn có lọc/index đặc thù hoặc các tình huống server không trả đủ số row kỳ vọng, hãy kiểm thử **trang rỗng và còn trang sau** thay vì đồng nhất hai tín hiệu.

## 16. Quan sát và xử lý sự cố phân trang

### 16.1. Metric từ Java

Đối với mỗi query shape, nên ghi:

- **logical request ID** không chứa PII và loại operation;
- partition/bucket category thay vì ghi partition key thật;
- **page size**, số page thực tế, số row xử lý, tổng byte ước tính;
- thời gian **trang đầu** và thời gian **toàn bộ chuỗi page**;
- p95/p99, timeout, failure stage/page index, retry count;
- số pipeline in-flight, mức sử dụng queue/permit;
- downstream sink latency và tỷ lệ thất bại.

Nếu chỉ đo thời gian **executeAsync trang đầu**, rất dễ kết luận query nhanh trong khi người dùng thực sự phải đợi **20 trang** mới nhận đủ kết quả.

### 16.2. Quan sát Cassandra

Trên các node được phép, với cú pháp tương thích phiên bản:

~~~bash
# Health/topology: node nào đang UP/DOWN, DC/rack.
nodetool status

# Công việc nền và pending tasks.
nodetool tpstats
nodetool compactionstats

# Thống kê bảng liên quan, tùy phiên bản hỗ trợ.
nodetool tablestats event_lab.events_by_tenant_day

# Phân phối kích thước partition/row, tùy phiên bản.
nodetool tablehistograms event_lab events_by_tenant_day
~~~

Kết hợp log/metric của coordinator và replica, disk latency/IOPS, GC, network và tombstone count. Một query chậm từ page thứ N có thể liên quan đọc qua nhiều SSTable, hot partition, repair/compaction đang chạy hoặc tải request tăng; không nên chỉ nâng timeout.

### 16.3. Runbook điều tra 8 bước

1. Xác định **query CQL**, partition key đầy đủ, page size, LIMIT và CL đang dùng.
2. Đo **first-page latency** và **full-result latency**, tách riêng processing/downstream.
3. Kiểm tra số page, row/page và vị trí page thường lỗi.
4. So tải cùng thời điểm: concurrent pipelines, retry, driver queues, GC client.
5. Kiểm tra Cassandra node/DC/RF, read timeouts, overloaded/unavailable, compaction và disk.
6. Xem dữ liệu: partition size, tombstone, collection, TTL, truy vấn/guardrails.
7. Điều chỉnh có kiểm soát: page size, maxRows, in-flight, query design và sink processing.
8. Chạy lại trên fixture và tải đại diện, kiểm tra đúng dữ liệu, thứ tự và tính đầy đủ.

## 17. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Hướng khắc phục |
|---|---|---|
| Chỉ duyệt **currentPage()** của kết quả đầu | Thiếu dữ liệu ở các trang tiếp | Kiểm tra hasMorePages và fetchNextPage |
| Gọi fetch nhưng bỏ **CompletionStage** | Không biết trang mới thành công/thất bại | Nối bằng thenCompose/whenComplete |
| Gọi **join/get** trong callback I/O | Chặn thread, dễ gây ùn tắc/deadlock tùy hoàn cảnh | Trả stage và compose bất đồng bộ |
| Fetch liên tục trước khi downstream xử lý | Buffer lớn, áp lực Cassandra | Chờ sink/processor rồi fetch |
| Giữ toàn bộ row vào **List** vô hạn | Heap/GC/OOM | Thu thập giới hạn hoặc fold/stream |
| Gọi nhiều fetch song song trên cùng page | Sai giả định về thứ tự/trạng thái phân trang | Một chuỗi fetch tuần tự cho từng query |
| Gộp hai partition bằng **concat** và cho là sort thời gian | Sai thứ tự toàn cục | Merge theo comparator rõ ràng |
| Dừng khi trang rỗng | Có thể dừng trước khi hết | Dựa vào hasMorePages |
| Retry toàn query sau page N lỗi mà sink không idempotent | Xử lý trùng các row đầu | Checkpoint + idempotency/reconciliation |
| Dùng paging state như offset lưu vô hạn | Token sai/rủi ro bảo mật và dữ liệu thay đổi | Opaque token có xác thực, hạn sử dụng, keyset khi phù hợp |
| Đóng CqlSession trước khi fetch xong | Lỗi trang sau | Quản lý lifecycle theo chuỗi async |
| Không giới hạn số query đồng thời | Quá tải coordinator/replica | Admission/bounded concurrency và backpressure |
| Chỉ đo latency trang đầu | Bỏ qua thời gian trả kết quả cuối | Đo full-result latency và từng page |

## 18. Bài tập thực hành

### Bài 1 — Trang đầu không phải toàn bộ kết quả

Một SELECT có **LIMIT 180**, statement **setPageSize(40)**. **executeAsync** trả AsyncResultSet có **currentPage()** chứa 40 row và **hasMorePages() = true**.

**Câu hỏi:** Có thể trả ngay 40 row và báo kết quả đầy đủ không? Cần API nào để lấy tiếp?

**Đáp án gợi ý:** Không, nếu hợp đồng yêu cầu toàn bộ dữ liệu. Dùng **fetchNextPage()** và xử lý **AsyncResultSet mới**, lặp tới khi **hasMorePages() = false** hoặc đạt giới hạn nghiệp vụ.

### Bài 2 — thenApply hay thenCompose?

Cho hàm:

~~~java
CompletionStage<Long> countPages(
    AsyncResultSet page, long previous);
~~~

Một developer viết:

~~~java
var output = session.executeAsync(stmt)
    .thenApply(page -> countPages(page, 0L));
~~~

**Câu hỏi:** Type của output là gì, và sửa thế nào?

**Đáp án gợi ý:** **CompletionStage<CompletionStage<Long>>**. Sửa thành **thenCompose** để nhận **CompletionStage<Long>** và chờ chuỗi fetch hoàn thành.

### Bài 3 — Trang rỗng vẫn còn trang tiếp

Một query trả trang hiện tại rỗng nhưng **hasMorePages() = true**.

**Câu hỏi:** Có nên dừng để báo “đã hết dữ liệu” không?

**Đáp án gợi ý:** Không. Kiểm tra **hasMorePages()** để biết khả năng fetch tiếp. Số row trang hiện tại không thay thế trạng thái phân trang.

### Bài 4 — Bộ nhớ và số request đồng thời

100 HTTP requests đang chạy; mỗi request gom 20.000 DTO, mỗi DTO giữ khoảng 1 KiB dữ liệu thô.

**Câu hỏi:** Ít nhất bao nhiêu bộ nhớ dữ liệu thô có thể bị giữ, chưa kể Java overhead? Hướng cải thiện nào phù hợp?

**Đáp án gợi ý:** Khoảng **1.953 MiB (~1,91 GiB)** dữ liệu thô. Giới hạn maxRows, xử lý theo page, bounded in-flight, giảm số request đồng thời và thử tải thực tế.

### Bài 5 — Fetch trước khi sink xử lý xong

Mỗi trang 500 row, sink chỉ chấp nhận 50 row/giây. Code gọi fetchNextPage liên tục dù sink đang xử lý page trước.

**Câu hỏi:** Rủi ro và cách khắc phục?

**Đáp án gợi ý:** Tăng bộ đệm/GC và áp lực coordinator/replica; chỉ fetch trang kế tiếp sau khi **CompletionStage** xử lý sink của trang hiện tại hoàn tất. Giới hạn số query đồng thời.

### Bài 6 — Hai ngày, một danh sách

Java service chạy hai query theo **(tenant_id, 2026-11-20)** và **(tenant_id, 2026-11-21)**, mỗi query trả danh sách đã sắp theo **happened_at DESC**. Code dùng **list1.addAll(list2)** rồi công bố kết quả sắp giảm dần toàn cục.

**Câu hỏi:** Có luôn đúng không?

**Đáp án gợi ý:** Không được suy thứ tự toàn cục chỉ từ phép nối hai list nếu quy tắc sắp xếp liên ngày chưa được chứng minh/kiểm soát. Khi cần merge chung, dùng comparator **happened_at + event_id**, đảm bảo cả hai nguồn có đủ dữ liệu trong giới hạn, rồi áp LIMIT toàn cục.

### Bài 7 — Trang N thất bại sau khi đã gửi thông báo

Một pipeline đọc 10 trang, gửi thông báo từng row và trang 7 bị ReadTimeout. Job tự retry toàn query từ đầu.

**Câu hỏi:** Có thể gây lỗi gì? Sửa thế nào?

**Đáp án gợi ý:** Các thông báo của trang 1–6 có thể gửi lại. Dùng định danh nghiệp vụ, outbox/idempotent sink/checkpoint bền vững; retry theo loại lỗi và deadline, không coi paging state là bảo đảm exactly-once.

### Bài 8 — Page size có sửa hot partition không?

Một tenant có partition dữ liệu nhiều GiB. Đội vận hành giảm page size từ 1.000 xuống 50 và tuyên bố đã xử lý thiết kế sai.

**Câu hỏi:** Nhận xét?

**Đáp án gợi ý:** Page size nhỏ có thể giảm payload của mỗi request nhưng **không giảm tổng số row cần quét**; còn tăng số round trip. Cần phân tích bucket/shard, clustering key, tombstone và truy vấn, đồng thời đo tổng thời gian/IO.

### Bài 9 — Dùng join trong callback

~~~java
session.executeAsync(statement)
    .thenApply(page -> page.fetchNextPage()
        .toCompletableFuture().join());
~~~

**Câu hỏi:** Vì sao cách này nguy hiểm và còn thiếu điều kiện gì?

**Đáp án gợi ý:** Chặn thread callback và gọi fetch mà **không kiểm tra hasMorePages()**; đồng thời bỏ qua xử lý currentPage của trang đầu. Sửa bằng **thenCompose**, xử lý page hiện tại, kiểm tra hasMorePages rồi nối stage kế tiếp.

## 19. Checklist đưa async paging vào production

- [ ] Truy vấn bind đủ partition key, được thiết kế theo access pattern.
- [ ] CqlSession/PreparedStatement được tái sử dụng, connection/TLS/auth cấu hình đúng.
- [ ] Có **setPageSize** và LIMIT/maxRows được kiểm soát theo SLA.
- [ ] Xử lý **currentPage** rồi kiểm tra **hasMorePages** trước khi **fetchNextPage**.
- [ ] Không dừng chỉ vì currentPage rỗng; không giả định page size là số row chính xác.
- [ ] Chuỗi page được **compose** bất đồng bộ, không block bằng get/join trong callback.
- [ ] Không fetch nhiều page của một cursor đồng thời khi chưa có ngữ nghĩa hỗ trợ.
- [ ] Không gom row không giới hạn vào List; dùng bounded collector, fold hoặc downstream sink.
- [ ] Downstream có backpressure/giới hạn queue, thread pool không phát triển vô hạn.
- [ ] Số query/pipeline đồng thời, request in-flight và tổng instance được giới hạn.
- [ ] Có deadline end-to-end; dừng fetch khi caller không còn cần kết quả.
- [ ] Phân biệt kết quả **partial** và **complete**, xử lý lỗi trang N đúng nghiệp vụ.
- [ ] Retry/backoff có giới hạn, kiểm soát idempotency và checkpoint nếu có side effect.
- [ ] Paging state được coi là opaque; token tiếp tục có xác thực/phạm vi/hạn dùng.
- [ ] Có kiểm thử INSERT/DELETE/TTL và thay đổi đồng thời trong lúc duyệt các page.
- [ ] Nếu gộp nhiều partition, xác định rõ thứ tự/sort toàn cục và giới hạn song song.
- [ ] Theo dõi latency trang đầu, latency toàn chuỗi, page count, row count, retry và memory.
- [ ] Khi chậm, kiểm tra replica/CL, hot partition, tombstone, compaction, repair và disk I/O.
- [ ] Không log payload, partition key thật, raw paging state hoặc secret.

## 20. Tổng kết

**AsyncResultSet** trong Java Driver 4.x đại diện cho **một trang đang sẵn sàng**, không phải toàn bộ kết quả. Đọc row qua **currentPage()**, kiểm tra **hasMorePages()**, rồi chỉ khi cần mới gọi **fetchNextPage()** và nối stage mới bằng **thenCompose**. Khi kết hợp nhiều trang, chọn giữa **thu thập có giới hạn**, **fold thống kê ít bộ nhớ** và **xử lý downstream tuần tự có backpressure**, tùy hợp đồng nghiệp vụ.

Với Cassandra, phân trang bất đồng bộ vẫn chịu những ràng buộc của mô hình wide-column: **partition key phải phù hợp truy vấn, consistency level phải phù hợp replication/topology, và partition/collection lớn cùng tombstone, compaction/repair có thể làm đọc chậm**. Bảo vệ bộ nhớ Java và tải server đòi hỏi kiểm soát đồng thời **page size, số pipeline in-flight, deadline, retry và trạng thái dữ liệu khi nhiều page được đọc ở các thời điểm khác nhau**. Chỉ khi đo và kiểm chứng cả chuỗi mới có thể coi API phân trang hoạt động đúng, ổn định và an toàn.
