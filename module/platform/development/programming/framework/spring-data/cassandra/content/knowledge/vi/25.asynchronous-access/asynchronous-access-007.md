# Luồng chạy callback và cô lập công việc chặn hoặc tốn CPU

Khi truy cập **Apache Cassandra bằng Spring Data Cassandra** hoặc **Java Driver 4**, ứng dụng có thể sử dụng API bất đồng bộ để gửi câu lệnh CQL mà **không phải chờ đồng bộ** tại luồng đang gọi. Nhưng *gửi request bất đồng bộ* không đồng nghĩa mọi đoạn code xử lý kết quả đều chạy trên một worker thread an toàn để chờ lâu.

Trong Java Driver, callback gắn với `CompletionStage<AsyncResultSet>` thường được kích hoạt trên **luồng I/O nội bộ** của driver khi response hoàn tất. Nếu callback thực hiện truy vấn đồng bộ, gọi HTTP blocking, `Thread.sleep`, `join()` hoặc tính toán CPU kéo dài, nó có thể chiếm I/O thread đang phục vụ **nhiều request Cassandra khác**. Hậu quả không chỉ là request hiện tại chậm: độ trễ của các truy vấn không liên quan cũng tăng, throughput giảm và thậm chí xuất hiện lỗi do driver phát hiện lệnh đồng bộ từ callback.

Bài học thuộc chương **Truy cập bất đồng bộ** của module **SPRING_DATA_CASSANDRA**. Trọng tâm là **luồng chạy callback và cách cô lập công việc chặn hoặc tốn CPU**. Ta sẽ dùng CQL, `CqlSession.executeAsync`, `CompletionStage`, `Executor`, `AsyncCassandraOperations`, `CassandraTemplate`, repository, paging, consistency và các biện pháp vận hành phù hợp với mô hình dữ liệu phân tán.

> **Nguyên tắc:** callback I/O nên làm rất ít việc. Nếu cần CPU lớn hoặc gọi thư viện blocking, chuyển phần đó sang **executor chuyên dụng, có giới hạn**. Nếu cần truy vấn Cassandra tiếp, dùng **API async và `thenCompose`**, không chờ kết quả bằng `get()/join()` trong callback.

## 1. Kết quả mong đợi

Sau bài học, bạn có thể:

1. Mô tả đường đi của request từ luồng ứng dụng tới I/O thread của Java Driver và executor nghiệp vụ.
2. Phân biệt `thenApply`, `thenCompose`, `thenApplyAsync`, `whenComplete`, `handle`, `exceptionally` theo cả **ngữ nghĩa** lẫn **luồng thực thi**.
3. Nhận diện vì sao `session.execute(...)`, `CompletableFuture.join()` hay xử lý CPU lâu **không được đặt trong callback I/O**.
4. Thiết lập hai pool có giới hạn riêng cho **CPU-bound** và **blocking I/O**; giải thích queue, rejection và backpressure.
5. Dùng `AsyncCassandraOperations` trong Spring Data Cassandra mà không nhầm với `@Async` trên repository hoặc reactive API.
6. Phân trang bất đồng bộ bằng `AsyncResultSet.currentPage()` và `fetchNextPage()`, đồng thời kiểm soát lượng công việc đang chờ.
7. Kiểm thử thread boundary, lỗi callback, timeout, cancellation và độ trễ p95/p99.

## 2. Ba loại luồng có vai trò khác nhau

Một service truy cập Cassandra bất đồng bộ thường liên quan ít nhất ba nhóm:

| Luồng/Executor | Vai trò | Những việc không nên thực hiện |
|---|---|---|
| Luồng gọi từ HTTP/job | Tạo request, xác thực input, trả `CompletionStage` | `join()` để giả lập sync nếu muốn giữ request non-blocking |
| **Driver I/O event loop** | Gửi/nhận response, decode mạng, hoàn tất async stage | Blocking HTTP/JDBC, `Thread.sleep`, CPU nặng, truy vấn Cassandra sync |
| **Executor nghiệp vụ** | Xử lý CPU hoặc thư viện blocking sau khi đã offload | Queue không giới hạn, không có deadline, chia sẻ vô tình với driver I/O |

Java Driver còn có nhóm **admin event loop** cho tác vụ metadata, topology, schema và lifecycle. Callback hoàn tất việc tạo session hoặc tác vụ quản trị có thể chạy trên luồng admin; không được mặc định *mọi* callback đều chạy cùng một nhóm I/O.

~~~mermaid
flowchart LR
    A[HTTP request / service] --> B[CqlSession.executeAsync]
    B --> C[Driver Netty I/O]
    C --> D[CompletionStage complete]
    D --> E{Callback làm gì?}
    E -->|Mapping rất nhẹ| F[thenApply / thenCompose]
    E -->|CPU nặng| G[thenApplyAsync CPU executor]
    E -->|I/O blocking| H[thenApplyAsync blocking executor]
    F --> I[Trả kết quả / async query tiếp]
    G --> I
    H --> I
~~~

**Điều kiện quan trọng:** các stage *không có hậu tố* `Async` (`thenApply`, `thenCompose`, `whenComplete`) **không bảo đảm chạy trong một executor riêng**. Chúng thường chạy trên luồng hoàn tất stage; với response Cassandra đó có thể là driver I/O thread. Nếu stage đã hoàn tất trước khi callback được đăng ký, callback cũng có thể chạy ngay trên **luồng đang đăng ký**. Vì vậy không dựa vào tên thread cụ thể để quyết định code có an toàn hay không.

Các hàm `thenApplyAsync`/**`thenComposeAsync` với `Executor` chỉ định** cho phép xác lập ranh giới rõ ràng. Không truyền executor vào overload `*Async` thường sẽ dùng executor mặc định của `CompletableFuture`, thường là `ForkJoinPool.commonPool()`; đó chưa chắc là nơi phù hợp cho blocking I/O hay tải CPU được phân lập.

## 3. Thiết kế bảng theo truy vấn trước khi tối ưu callback

Giả sử một API hiển thị sự kiện thiết bị trong một ngày và chạy phép phân tích rủi ro trên payload:

~~~text
GET /tenants/{tenantId}/devices/{deviceId}/events
    ?day=2026-11-25&pageSize=20

Yêu cầu:
- Chỉ đọc tenant và thiết bị có quyền;
- Mới nhất trước;
- Có thể tải trang tiếp;
- Tính điểm rủi ro trên mỗi sự kiện (CPU);
- Tùy chọn gọi dịch vụ enrich cũ (HTTP blocking).
~~~

Bảng truy cập theo partition:

~~~sql
CREATE TABLE device_events_by_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at, event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò | Tác động tới truy cập |
|---|---|---|
| `tenant_id` | Partition key 1 | Cô lập tenant |
| `device_id` | Partition key 2 | Đường đọc theo thiết bị |
| `event_day` | Partition key 3 | Bucket theo ngày, giới hạn partition |
| `occurred_at` | Clustering DESC | Sự kiện mới trước |
| `event_id` | Clustering ASC | Phá hòa timestamp |
| `event_type` | Cột thường | Thông tin nghiệp vụ |
| `payload` | Cột thường | Có thể lớn, nên hạn chế khi không cần |

CQL hợp lệ:

~~~sql
SELECT occurred_at, event_id, event_type, payload
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?;
~~~

**Truy cập bất đồng bộ không sửa sai mô hình khóa**. Một query thiếu `tenant_id` hoặc muốn `ORDER BY payload` vẫn có thể bị Cassandra từ chối/đọc kém hiệu quả. Chạy query trên executor khác **không** làm partition key biến mất hoặc giảm chi phí quét trên cluster.

## 4. Java Driver 4: executeAsync trả về CompletionStage

API chuẩn:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public CompletionStage<AsyncResultSet> fetchFirstPage(
        CqlSession session, UUID tenantId,
        UUID deviceId, LocalDate day) {

    SimpleStatement statement = SimpleStatement.newInstance(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ?",
            tenantId, deviceId, day)
            .setPageSize(20);

    return session.executeAsync(statement);
}
~~~

`executeAsync` trả `CompletionStage<AsyncResultSet>`. Nó cho phép **nối tiếp xử lý** mà không gọi `get()` trên thread hiện tại. `setPageSize(20)` là **kích thước fetch theo trang**, không phải `LIMIT 20` cố định cho toàn bộ kết quả.

`CqlSession` thường là singleton do Spring quản lý; **không khởi tạo và đóng session mỗi request**. Khi sử dụng Java Driver 4.18+ nên đối chiếu các trang tài liệu Apache Java Driver hiện hành thay vì dựa vào snippet Driver 3 (`ListenableFuture<ResultSet>`) đã có mô hình phân trang khác.

### 4.1. Callback ngắn có thể dùng thenApply

~~~java
CompletionStage<Integer> countOnFirstPage =
        session.executeAsync(statement)
                .thenApply(rs -> {
                    int count = 0;
                    for (var ignored : rs.currentPage()) {
                        count++;
                    }
                    return count;
                });
~~~

Đây là phép đếm nhẹ trên **trang hiện tại**. Trường hợp page size nhỏ, không có CPU nặng hoặc I/O chặn, `thenApply` có thể hợp lý. Tuy nhiên vẫn phải đo: parse một payload JSON lớn, giải nén hàng chục MB hoặc xử lý hàng nghìn dữ liệu trong callback là câu chuyện khác.

**Không suy** callback luôn chạy trên một thread tên `s0-io-1`: tên pool tùy session/driver, và callback đăng ký sau khi stage hoàn tất có thể chạy trên thread gọi.

## 5. Chống mẫu: đồng bộ hóa trong callback của Driver

Một ví dụ sai:

~~~java
// CHỐNG MẪU — không dùng trong production.
CompletionStage<String> bad =
        session.executeAsync(statement)
                .thenApply(rs -> {
                    // Nếu callback chạy trên I/O thread, đây là lời gọi
                    // synchronous driver API, nguy cơ deadlock.
                    var another = session.execute(
                            "SELECT release_version FROM system.local");

                    // Còn tệ hơn nếu gọi sleep, JDBC, HTTP sync, ...
                    return another.one().getString("release_version");
                });
~~~

Java Driver 4 có khả năng **phát hiện lời gọi API đồng bộ từ driver thread** và fail-fast bằng lỗi runtime vì nguy cơ deadlock. Không nên “sửa lỗi” bằng cách bắt exception rồi retry cùng đoạn sync code trên I/O thread.

Chống mẫu khác:

~~~java
// CHỐNG MẪU — async request nhưng chặn khi chờ:
session.executeAsync(statement)
       .toCompletableFuture()
       .join();
~~~

Gọi `join()` hoặc `get()` ngay trong callback (hay trên Netty event loop của WebFlux) có thể **chặn luồng quan trọng**. Gọi `join()` trên một thread của test hoặc một boundary **chủ đích đồng bộ** không nhất thiết sai, nhưng lúc đó đó là **lựa chọn blocking rõ ràng** và cần được kiểm soát. Không gọi nó để “làm đơn giản” chuỗi async trong code production.

### 5.1. Cách đúng: thenCompose cho query tiếp theo

Nếu cần một query Cassandra sau khi nhận ID từ query đầu, **nối stage**:

~~~java
CompletionStage<AsyncResultSet> chain =
        session.executeAsync(firstStatement)
                .thenCompose(firstPage -> {
                    var row = firstPage.one();
                    if (row == null) {
                        return java.util.concurrent.CompletableFuture
                                .<AsyncResultSet>failedFuture(
                                        new IllegalStateException(
                                                "Missing reference row"));
                    }

                    UUID referencedId = row.getUuid("referenced_id");
                    return session.executeAsync(
                            SimpleStatement.newInstance(
                                    "SELECT * FROM objects_by_id WHERE id = ?",
                                    referencedId));
                });
~~~

Ở đây `firstStatement`, `objects_by_id` và cột `referenced_id` là **một ví dụ khác cần schema đã được provision**, nhằm minh họa toán tử, không phải phần của bảng `device_events_by_day` phía trên.

`thenCompose` **làm phẳng** `CompletionStage<CompletionStage<T>>` thành `CompletionStage<T>`. Lệnh `session.executeAsync` là non-blocking nên có thể gọi trong callback ngắn. Không thay bằng `session.execute`, `toCompletableFuture().get()` hoặc `join()`.

## 6. Các toán tử CompletionStage và vị trí chạy callback

| Toán tử | Đầu vào → kết quả | Về thread |
|---|---|---|
| `thenApply(fn)` | `T → U`, ánh xạ đồng bộ | Chạy inline trên thread hoàn tất/đăng ký nếu stage đã xong |
| `thenCompose(fn)` | `T → CompletionStage<U>` | Callback inline; dùng để nối thêm async I/O |
| `thenAccept(fn)` | Tiêu thụ kết quả, trả `Void` | Inline, không phù hợp side effect blocking |
| `whenComplete(fn)` | Quan sát cả thành công và lỗi | Inline; stage mới vẫn mang lỗi nếu callback không chữa lỗi |
| `handle(fn)` | Biến đổi cả thành công/lỗi | Inline; có thể recover nếu trả giá trị |
| `exceptionally(fn)` | Fallback khi có lỗi | Inline; dễ che lỗi nếu fallback không phù hợp |
| `thenApplyAsync(fn, executor)` | `T → U` | Chủ động đưa công việc vào `executor` |
| `thenComposeAsync(fn, executor)` | `T → CompletionStage<U>` | Đưa phần callback tạo stage tiếp vào executor |
| `whenCompleteAsync(fn, executor)` | Quan sát completion | Thực thi callback trên executor đã chọn |

**Lưu ý ngữ nghĩa:** hậu tố `Async` không làm hàm `fn` bên trong tự trở thành non-blocking; nó chỉ **đổi nơi chạy**. Ví dụ `thenApplyAsync(x -> jdbcTemplate.queryForObject(...), blockingExecutor)` vẫn là thao tác blocking, nhưng không còn chặn driver I/O thread. Đó là lý do cần pool đúng loại.

### 6.1. Khi nào thenApply vs thenApplyAsync?

Giả sử cần `Row` → DTO chỉ gồm vài field: mapping nhẹ có thể thực hiện trong `thenApply`.

~~~java
import java.time.Instant;
import java.util.UUID;
import com.datastax.oss.driver.api.core.cql.Row;

public record EventInput(
        UUID eventId, Instant occurredAt,
        String eventType, String payload) {

    public static EventInput from(Row row) {
        return new EventInput(
                row.getUuid("event_id"),
                row.getInstant("occurred_at"),
                row.getString("event_type"),
                row.getString("payload"));
    }
}
~~~

Nhưng nếu cần chạy một thuật toán CPU nặng cho `EventInput`, không đặt nó trong `thenApply`. Chuyển sang executor riêng:

~~~java
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;

public CompletionStage<Integer> loadAndScore(
        CqlSession session,
        SimpleStatement statement,
        Executor cpuExecutor,
        java.util.function.ToIntFunction<EventInput> scorer) {

    return session.executeAsync(statement)
            .thenApply(rs -> {
                Row row = rs.one();
                return row == null ? null : EventInput.from(row);
            })
            .thenApplyAsync(
                    event -> event == null ? 0 : scorer.applyAsInt(event),
                    cpuExecutor);
}
~~~

`EventInput.from(row)` chỉ đọc một số field, cần nhanh và không thực hiện I/O. `scorer.applyAsInt(event)` có thể nặng, nên chạy trên **CPU executor**, không chiếm driver I/O thread. Nếu không có dữ liệu, ví dụ trả score 0 cho đơn giản; API thật nên chọn `Optional`, `404` hoặc result type rõ ràng thay vì lẫn giá trị mặc định và “không có bản ghi”.

## 7. Tách executor CPU và blocking I/O trong Spring

CPU-bound và blocking I/O có cấu hình khác nhau:

- **CPU-bound** (mã hóa, phân tích dữ liệu, tính toán): thường giới hạn gần với số CPU hữu dụng của service, hàng đợi nhỏ, kiểm soát contention.
- **Blocking I/O** (legacy HTTP/JDBC/file): thread có thể đợi network/storage; cần giới hạn theo số kết nối và SLA downstream, thường cấu hình khác CPU executor.
- **Driver I/O**: pool nội bộ của Java Driver/Netty, **không** phải nơi ứng dụng chạy CPU lâu hoặc blocking.

Một ví dụ cấu hình Spring:

~~~java
package example.telemetry;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerExecutorConfig {

    @Bean("cpuWorkExecutor")
    public ThreadPoolTaskExecutor cpuWorkExecutor() {
        int cpuCount = Runtime.getRuntime().availableProcessors();
        int workers = Math.max(1, cpuCount - 1);

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(workers);
        executor.setMaxPoolSize(workers);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("cpu-work-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean("blockingWorkExecutor")
    public ThreadPoolTaskExecutor blockingWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("blocking-work-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

**Các con số 8/16/32/64 chỉ để minh họa, không phải cấu hình mặc định nên dùng cho mọi dự án.** Điều chỉnh theo CPU quota của container, DB/HTTP connection pool, latency downstream và tải thực. Spring quản lý lifecycle của các bean executor trong ví dụ; không tạo một `ThreadPoolTaskExecutor` mới trong mỗi request.

### 7.1. Vì sao không dùng queue vô hạn?

Nếu Cassandra trả về 2.000 response/giây nhưng CPU chỉ xử lý 200/giây, một queue vô hạn tích lũy dần các DTO/payload và làm tăng latency đến mức hết memory. Tăng `maxPoolSize` với queue không giới hạn thường **không giải quyết** vì nhiều executor sẽ xếp vào queue trước khi mở rộng threads.

Một queue giới hạn tạo được **tín hiệu quá tải**, thường là `RejectedExecutionException` hoặc `TaskRejectedException` (tùy adapter). Service phải định nghĩa cách trả `429/503`, retry có backoff, hoặc giảm số request in-flight.

### 7.2. Cẩn thận với CallerRunsPolicy

`ThreadPoolExecutor.CallerRunsPolicy` thực thi task ngay trên **luồng submit** khi pool và queue đầy. Nếu `thenApplyAsync(..., executor)` được submit **từ callback hoàn tất trên driver I/O thread**, fallback này có thể **chạy chính phần CPU/blocking trên I/O thread** — phá ranh giới cần bảo vệ.

~~~text
Driver I/O thread
    -> gửi CPU task vào executor
    -> executor đầy
    -> CallerRunsPolicy
    -> CPU task chạy ngay trên Driver I/O thread  ❌
~~~

Vì vậy ví dụ chọn `AbortPolicy` và yêu cầu tầng API xử lý tín hiệu overload. **Không nuốt lỗi rejection** hay âm thầm chạy công việc nặng inline trên I/O thread.

## 8. Cô lập CPU-bound với một service cụ thể

Một service nhận event, map nhanh và tính score trên pool CPU:

~~~java
package example.telemetry;

import java.util.Optional;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;
import java.util.UUID;
import java.time.LocalDate;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class EventRiskService {

    private final CqlSession session;
    private final Executor cpuExecutor;
    private final RiskAnalyzer analyzer;

    public EventRiskService(
            CqlSession session,
            @Qualifier("cpuWorkExecutor") Executor cpuExecutor,
            RiskAnalyzer analyzer) {
        this.session = session;
        this.cpuExecutor = cpuExecutor;
        this.analyzer = analyzer;
    }

    public CompletionStage<Optional<RiskResult>> analyzeFirstEvent(
            UUID tenantId, UUID deviceId, LocalDate day) {

        SimpleStatement statement = SimpleStatement.newInstance(
                "SELECT event_id, occurred_at, event_type, payload " +
                "FROM device_events_by_day " +
                "WHERE tenant_id = ? AND device_id = ? AND event_day = ?",
                tenantId, deviceId, day)
                .setPageSize(1);

        return session.executeAsync(statement)
                .thenApply(rs -> {
                    Row row = rs.one();
                    return row == null
                            ? Optional.<EventInput>empty()
                            : Optional.of(EventInput.from(row));
                })
                .thenApplyAsync(
                        maybeEvent -> maybeEvent.map(
                                event -> new RiskResult(
                                        event.eventId(),
                                        analyzer.score(event))),
                        cpuExecutor);
    }

    public interface RiskAnalyzer {
        int score(EventInput event);
    }

    public record RiskResult(UUID eventId, int riskScore) {}
}
~~~

Đây là **service skeleton**: cần cung cấp bean `RiskAnalyzer` có thuật toán thực tế, giới hạn kích thước input và timeout. Bài chỉ minh họa ranh giới luồng, không khuyến nghị thuật toán score cụ thể.

Với `setPageSize(1)`, `rs.one()` đọc hàng đầu từ **trang hiện tại**. Nếu không có event, trả `Optional.empty()`. Nếu API cần duyệt toàn bộ lịch sử, phải sử dụng cơ chế paging riêng (phần 13), không coi một `AsyncResultSet` là danh sách vô hạn đã tải vào RAM.

### 8.1. Vì sao không tăng số I/O threads để chữa CPU chậm?

Nếu callback nặng chiếm I/O thread, việc tăng Netty I/O threads có thể che vấn đề tạm thời nhưng không thay bản chất **CPU/business work đang chạy sai nơi**. Nên đo và offload trước, sau đó mới tuning số I/O threads của driver theo số connection, CPU quota và tải thực.

## 9. Cô lập tác vụ blocking từ thư viện cũ

Giả sử cần enrich event bằng một HTTP client **chỉ có API đồng bộ**, ví dụ `LegacyGeoClient.lookup(...)`. Không gọi nó trong callback không-`Async`.

~~~java
public CompletionStage<EnrichedEvent> enrich(
        CqlSession session,
        SimpleStatement statement,
        LegacyGeoClient legacyClient,
        Executor blockingExecutor) {

    return session.executeAsync(statement)
            .thenApply(rs -> {
                Row row = rs.one();
                return row == null ? null : EventInput.from(row);
            })
            .thenApplyAsync(event -> {
                if (event == null) {
                    return null;
                }
                // Đây là lời gọi blocking, nhưng đang chạy
                // trên executor chuyên cho blocking I/O.
                String region = legacyClient.lookup(event.eventId());
                return new EnrichedEvent(event, region);
            }, blockingExecutor);
}
~~~

Các kiểu `LegacyGeoClient` và `EnrichedEvent` là **hợp đồng ứng dụng minh họa**, cần định nghĩa trong dự án. Chỉ dùng executor blocking khi không có lựa chọn non-blocking; nếu HTTP client có API async thật, nên nối bằng `thenCompose` thay vì chiếm một thread chờ response.

### 9.1. Không biến blocking thành non-blocking chỉ bằng tên Async

Một method `@Async` hoặc `CompletableFuture.supplyAsync` chạy JDBC/HTTP đồng bộ trên thread khác vẫn **blocking ở thread đó**. Điều này có thể chấp nhận khi có pool riêng và giới hạn hợp lý, nhưng nó không tương đương API network non-blocking.

Nếu downstream chậm 30 giây, 16 blocking threads chỉ cho tối đa khoảng 16 tác vụ chờ đồng thời trên pool đó; khi nhu cầu vượt khả năng, cần deadline và overload handling, không sinh thêm thread không giới hạn.

## 10. @Async của Spring khác executeAsync của Driver

Có ba khái niệm dễ bị trộn:

| Cơ chế | Thao tác diễn ra ở đâu? | Đặc điểm |
|---|---|---|
| `CqlSession.executeAsync` | Driver non-blocking I/O | Trả `CompletionStage<AsyncResultSet>` |
| Spring `@Async` | `TaskExecutor` của Spring | Đưa **method invocation** sang executor, method bên trong có thể vẫn blocking |
| Reactive `Mono/Flux` | Theo scheduler/operator của Reactor | Cần giữ nguồn non-blocking và tránh `block()` trên event loop |

Ví dụ hợp lệ khi phải gọi một thư viện blocking:

~~~java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LegacyEnrichmentService {
    private final LegacyGeoClient client;

    public LegacyEnrichmentService(LegacyGeoClient client) {
        this.client = client;
    }

    @Async("blockingWorkExecutor")
    public CompletableFuture<String> lookupAsync(UUID eventId) {
        // Đây là lời gọi blocking, nhưng Spring đã đưa
        // method invocation sang blockingWorkExecutor.
        String value = client.lookup(eventId);
        return CompletableFuture.completedFuture(value);
    }
}
~~~

Cần bật `@EnableAsync` trong Spring configuration để cơ chế proxy `@Async` hoạt động. Method phải được gọi **qua Spring proxy**, ví dụ từ bean khác; **self-invocation** (`this.lookupAsync(...)`) thường bỏ qua proxy và không tạo luồng async như mong đợi.

Không bọc method `@Async` ở trên bằng `CompletableFuture.supplyAsync(...)` một lần nữa nếu không có lý do: có thể gây **double scheduling**, khó kiểm soát executor và context.

### 10.1. Repository query @Async không đồng nghĩa native driver async

Một số Spring Data repositories có hỗ trợ phương thức `@Async` trả `Future<T>` hoặc `CompletableFuture<T>`. Theo tài liệu Spring Data, query có thể được đưa sang `TaskExecutor`; điều đó **khác với reactive queries** và không phải bằng chứng backend query dùng non-blocking driver path trong mọi cấu hình.

Muốn khai thác **native Cassandra async**, hãy dùng `AsyncCassandraOperations`/`AsyncCassandraTemplate` hoặc `CqlSession.executeAsync` và xác minh API/version. Đừng coi việc thêm annotation `@Async` lên repository là đủ để thay đổi semantics phân trang, consistency hoặc CQL.

## 11. AsyncCassandraOperations: API bất đồng bộ của Spring Data

Spring Data Cassandra cung cấp `AsyncCassandraOperations` và triển khai `AsyncCassandraTemplate`; các method async hiện hành như `selectOne`, `select`, `slice` có thể trả `CompletableFuture`.

Một entity mapping cho bảng minh họa:

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

    public DeviceEventKey() {}

    public DeviceEventKey(UUID tenantId, UUID deviceId,
            LocalDate eventDay, Instant occurredAt, UUID eventId) {
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

Entity:

~~~java
package example.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_events_by_day")
public class DeviceEvent {

    @PrimaryKey
    private DeviceEventKey id;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public DeviceEvent() {}
    public DeviceEvent(DeviceEventKey id,
            String eventType, String payload) {
        this.id = id;
        this.eventType = eventType;
        this.payload = payload;
    }

    public DeviceEventKey getId() { return id; }
    public void setId(DeviceEventKey value) { id = value; }
    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }
    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
~~~

Hai class `public` trên phải nằm trong **hai file Java riêng**, với repository/entity scan và keyspace phù hợp. `PrimaryKeyType` thuộc `core.cql`; `ordinal` được đánh liên tục từ 0 đến 4 trên toàn bộ composite key. `Instant` của clustering column map CQL `timestamp`, có độ chính xác mili giây.

### 11.1. Lấy slice async rồi offload phần tính toán

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.data.cassandra.core.AsyncCassandraOperations;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.data.domain.Slice;

public CompletableFuture<List<Integer>> analyzeOnePage(
        AsyncCassandraOperations async,
        UUID tenantId, UUID deviceId, LocalDate day,
        Executor cpuExecutor,
        java.util.function.ToIntFunction<DeviceEvent> analyzer) {

    Query base = Query.query(
            Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("device_id").is(deviceId))
            .and(Criteria.where("event_day").is(day));

    Query paged = base.pageRequest(
            CassandraPageRequest.first(20));

    return async.slice(paged, DeviceEvent.class)
            .thenApplyAsync(slice -> slice.getContent()
                    .stream()
                    .map(event -> analyzer.applyAsInt(event))
                    .toList(), cpuExecutor);
}
~~~

`Query.pageRequest(pageable)` trả một **Query đã gắn phân trang**; cần dùng giá trị trả về, không bỏ qua. `AsyncCassandraOperations.slice(...)` trả `CompletableFuture<Slice<T>>`. Tính toán score chạy trong `thenApplyAsync(..., cpuExecutor)`, không giả định implementation template luôn dùng một callback executor riêng có thể chạy CPU nặng.

Nếu cần trang 2, giữ `Slice.hasNext()` và `slice.nextPageable()` để gọi **cùng query/bind values** lần tiếp theo. Đừng tạo lại `CassandraPageRequest.first(20)` và đừng đổi tenant/day khi tái sử dụng paging state.

### 11.2. Repository/CassandraTemplate không bắt buộc thay thế driver API

Dùng `CassandraRepository`/`CassandraTemplate` synchronous cho CRUD đơn giản vẫn hợp lý trong ứng dụng đồng bộ có thread model thích hợp. Nếu muốn không chặn event loop, ưu tiên API `AsyncCassandraTemplate` hoặc Driver `executeAsync`; **đừng** gọi `cassandraTemplate.select(...)` trong callback I/O rồi hy vọng `CompletableFuture` làm nó không chặn.

## 12. Hạn chế các callback xử lý lỗi

Các exception của database **không tự in ra log** nếu bạn đăng ký callback thành công mà bỏ rơi stage thất bại:

~~~java
// Chống mẫu: chỉ đăng ký callback success, không quan sát failure.
session.executeAsync(statement)
        .thenAccept(rs -> sendNotification(rs.one()));
~~~

Nếu query thất bại, `thenAccept` không chạy; nếu ứng dụng bỏ qua stage trả về, lỗi có thể bị bỏ sót. Ngay cả callback `whenComplete` cũng có thể tự ném exception và tạo ra **một stage thất bại mới**.

Một pattern đúng ở tầng service là **trả stage về caller**:

~~~java
public CompletionStage<Integer> queryCount(
        CqlSession session, SimpleStatement statement) {

    return session.executeAsync(statement)
            .thenApply(rs -> {
                int count = 0;
                for (var row : rs.currentPage()) {
                    count++;
                }
                return count;
            })
            .whenComplete((count, error) -> {
                if (error != null) {
                    // Log/metrics ngắn, không blocking, không log PII.
                    metrics.recordQueryFailure(error);
                }
            });
}
~~~

`metrics` là dependency quan sát của service, với hàm ghi chỉ số phải **rất nhẹ và không blocking**; nếu logging sink có thể chặn (I/O đồng bộ), offload hoặc dùng asynchronous logger. Caller nhận `CompletionStage<Integer>` và chịu trách nhiệm hoàn tất HTTP/job lifecycle, thay vì “fire and forget”.

### 12.1. whenComplete, handle và exceptionally không thay thế nhau

~~~java
CompletionStage<String> observed =
        stage.whenComplete((value, error) -> logOutcome(value, error));

CompletionStage<String> recovered =
        stage.exceptionally(error -> "safe-fallback");

CompletionStage<String> normalized =
        stage.handle((value, error) ->
                error == null ? value : mapFailure(error));
~~~

- `whenComplete`: quan sát kết quả/lỗi; bản thân nó **không tự biến lỗi thành thành công**.
- `exceptionally`: tạo **giá trị thay thế** khi thất bại; chỉ dùng fallback nếu nghiệp vụ cho phép.
- `handle`: chuyển cả thành công và lỗi thành một kết quả khác; dễ **che** lỗi nếu luôn trả giá trị mặc định.

Không trả response “không có dữ liệu” khi thực chất Cassandra timeout; điều đó khiến lỗi hạ tầng bị ngụy trang thành kết quả nghiệp vụ rỗng.

### 12.2. CompletionException và nguyên nhân gốc

Các stage có thể bọc lỗi trong `CompletionException`; khi log/phân loại lỗi, unwrap có kiểm soát:

~~~java
import java.util.concurrent.CompletionException;

static Throwable unwrap(Throwable failure) {
    Throwable current = failure;
    while (current instanceof CompletionException
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

Đừng bắt mọi lỗi rồi retry vô điều kiện. Phân biệt `InvalidQueryException`, unavailable, timeout, authorization, rejection từ executor, lỗi mapping và lỗi thuật toán nghiệp vụ.

## 13. Phân trang bất đồng bộ mà không giữ I/O thread quá lâu

Khác với `ResultSet` đồng bộ, **`AsyncResultSet` chỉ cung cấp trang hiện tại**, qua `currentPage()`. Để lấy tiếp phải gọi **`fetchNextPage()`**, cũng trả `CompletionStage<AsyncResultSet>`.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public CompletionStage<Long> countAllPages(
        AsyncResultSet page, long countBefore) {

    long count = countBefore;
    for (Row ignored : page.currentPage()) {
        count++;
    }

    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(count);
    }

    long nextCount = count;
    return page.fetchNextPage()
            .thenCompose(next -> countAllPages(next, nextCount));
}
~~~

Ví dụ chỉ **đếm trong bộ test/dataset nhỏ** để minh họa API. Nó có thể duyệt rất nhiều trang và tốn nhiều request nếu không có giới hạn; không dùng làm cách tính total-count rẻ trên production. Trong Cassandra, bảng time-series nên được truy vấn **theo partition key**, và tổng số cần thiết có thể yêu cầu read model thống kê riêng.

### 13.1. Duyệt từng trang và xử lý CPU trên pool riêng

Khi mỗi hàng cần công việc CPU, nên **copy dữ liệu nhỏ ra DTO**, offload tính toán và **chỉ fetch trang kế tiếp khi trang này đã xử lý xong**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;

public CompletionStage<Long> processPages(
        AsyncResultSet page, long completed,
        Executor cpuExecutor,
        java.util.function.Consumer<EventInput> processor) {

    // Mapping tối thiểu trên callback/driver thread.
    List<EventInput> snapshot = new ArrayList<>();
    for (Row row : page.currentPage()) {
        snapshot.add(EventInput.from(row));
    }

    // Công việc CPU thực tế chạy ngoài driver I/O.
    return CompletableFuture.supplyAsync(() -> {
        for (EventInput event : snapshot) {
            processor.accept(event);
        }
        return (long) snapshot.size();
    }, cpuExecutor).thenCompose(processed -> {
        long nextCount = completed + processed;
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(nextCount);
        }

        // Backpressure: xử lý xong trang N rồi mới fetch N+1.
        return page.fetchNextPage()
                .thenCompose(next ->
                        processPages(next, nextCount,
                                cpuExecutor, processor));
    });
}
~~~

Ưu điểm: chỉ giữ một page snapshot đang xử lý; không khởi động đồng thời hàng trăm page fetches và hàng nghìn CPU tasks.

**Đánh đổi:** fetch tuần tự theo page có thể không đạt throughput tối đa, nhưng dễ kiểm soát bộ nhớ và áp lực downstream. Cần giới hạn tổng số trang/hàng, thời gian và data size nếu chạy trong request HTTP. Với pipeline quét rất lớn, thiết kế iterative state machine/streaming và checkpoint thay vì giữ một chuỗi continuation vô hạn.

### 13.2. Page size không phải giới hạn CPU

Page size 100 có thể vẫn quá lớn nếu mỗi payload vài MB hoặc mỗi score mất nhiều mili giây CPU. Cần kết hợp **giới hạn độ rộng projection**, kích thước payload, số page đồng thời và worker capacity. `LIMIT` và page size không xóa đi tombstone scan hoặc hot partition trên Cassandra.

## 14. Backpressure đầu vào: giới hạn tác vụ đang xử lý

Sử dụng async không giới hạn rất dễ dẫn tới **hàng nghìn query in-flight** nếu HTTP handler cứ gọi `executeAsync` cho mọi request.

Một semaphore không chặn cho phép admission control:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

public final class BoundedEventQueries {
    private final CqlSession session;
    private final Executor cpuExecutor;
    private final Semaphore permits = new Semaphore(64);

    public BoundedEventQueries(CqlSession session, Executor cpuExecutor) {
        this.session = session;
        this.cpuExecutor = cpuExecutor;
    }

    public CompletionStage<Integer> loadScore(
            SimpleStatement statement,
            java.util.function.ToIntFunction<EventInput> scorer) {

        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                    new RejectedExecutionException("Too many in-flight events"));
        }

        try {
            return session.executeAsync(statement)
                    .thenApply(rs -> {
                        Row row = rs.one();
                        return row == null ? null : EventInput.from(row);
                    })
                    .thenApplyAsync(
                            event -> event == null
                                    ? 0 : scorer.applyAsInt(event),
                            cpuExecutor)
                    .whenComplete((result, error) ->
                            permits.release());
        } catch (RuntimeException failure) {
            permits.release();
            return CompletableFuture.failedFuture(failure);
        }
    }
}
~~~

Cơ chế `tryAcquire()` **không block driver I/O thread**. Giới hạn 64 là ví dụ, cần tuning; permit chỉ được trả sau khi **toàn bộ chuỗi query + CPU** hoàn tất hoặc thất bại, không trả ngay khi nhận response Cassandra.

Khi executor CPU đầy, `thenApplyAsync` có thể bị từ chối, và stage chuyển sang trạng thái thất bại. Tầng HTTP/job cần map overload sang lỗi có kiểm soát (`429` hoặc `503` tùy policy), không nuốt lỗi hay chạy nặng inline trên I/O thread.

**Lưu ý ranh giới:** semaphore trên một instance giới hạn **đồng thời trong một JVM**, không phải global rate limit cho mọi pod. Với nhiều instance, cần tính capacity của cả cluster và downstream.

## 15. Timeout, cancellation và retry không tự hủy Cassandra work

Các cơ chế có phạm vi khác nhau:

| Cơ chế | Ý nghĩa | Không được mặc định |
|---|---|---|
| Driver request timeout | Giới hạn request theo cấu hình/profile | “Mutation chắc chắn chưa được áp dụng” |
| API deadline | HTTP/job ngừng chờ quá thời hạn | Cassandra đã dừng toàn bộ xử lý |
| `CompletableFuture.orTimeout` | Stage hoàn tất exceptional sau thời gian | Tự động hủy network request/cluster work |
| `cancel(true)` trên future | Tín hiệu cancel phía Java | Guaranteed rollback/reversal của mutation Cassandra |
| Retry policy | Có thể thử lại lỗi đủ điều kiện | Mọi command đều idempotent |

Ví dụ (Java 9+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

CompletableFuture<Integer> boundedResponse =
        loadAndScore(...).toCompletableFuture()
                .orTimeout(2, TimeUnit.SECONDS);
~~~

`loadAndScore(...)` ở đây tượng trưng cho method ở phần 6 với tham số đã được truyền. `orTimeout` là **deadline ở mức future**, không phải bằng chứng server đã dừng xử lý hoặc mutation chưa xảy ra. Với write có side effect, sau timeout trạng thái có thể **chưa xác định**, nên cần command ID/idempotency và kiểm tra lại bằng khóa.

**Không** gọi `get(2, SECONDS)` trong callback driver thay vì `orTimeout`: đó lại là chờ blocking trên luồng nhạy cảm.

### 15.1. Retry cần hiểu CQL và thao tác ghi

- `INSERT` với key/payload ổn định thường có thể thiết kế idempotent.
- Counter increment, list append và sinh UUID mới mỗi retry **không mặc nhiên idempotent**.
- LWT có thể đã `[applied]=true` nhưng response bị mất; retry có thể thấy `[applied]=false`.
- Consistency `LOCAL_ONE`, `LOCAL_QUORUM` không chữa query thiếu partition key hoặc callback blocking.
- Giữ `statement`/bind values và execution profile rõ ràng; đừng hạ consistency một cách tùy tiện để “giảm timeout”.

## 16. ThreadLocal, security context và distributed tracing

Đổi executor thường có nghĩa **đổi thread**. Các dữ liệu lưu trong `ThreadLocal` có thể **không tự đi theo**:

- MDC/log correlation ID.
- `SecurityContextHolder` của Spring Security theo chiến lược thread-local.
- Thông tin locale/time zone được gắn với request thread.
- Transaction/thread-bound resources của các framework khác.
- Context tracing tùy OpenTelemetry/instrumentation.

**Không** suy rằng `tenantId` có thể lấy an toàn từ một `ThreadLocal` bên trong callback sau khi offload. Truyền `tenantId` và quyền đã xác minh vào context bất biến rõ ràng, kiểm tra authorization trước khi truy vấn và tránh log payload/ID nhạy cảm.

Một ví dụ gắn MDC cục bộ cho CPU executor:

~~~java
import org.slf4j.MDC;

CompletionStage<Integer> scored = dataStage.thenApplyAsync(
        event -> {
            try (MDC.MDCCloseable ignored =
                    MDC.putCloseable("requestId", requestId)) {
                return analyzer.score(event);
            }
        },
        cpuExecutor);
~~~

`dataStage`, `requestId` và `analyzer` ở đây là context của service cần định nghĩa. Dùng `try-with-resources` giúp tránh **rò MDC sang task sau** khi pool tái sử dụng thread. Khi dùng distributed tracing, ưu tiên cơ chế context propagation của thư viện/SDK có hỗ trợ thay vì tự nhân bản tất cả `ThreadLocal`.

## 17. Reactor/WebFlux: async và scheduler phải cùng đúng

Nếu ứng dụng dùng Spring WebFlux/Reactor, có thể chuyển `CompletionStage` thành `Mono`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<EventInput> mono =
        Mono.fromCompletionStage(() -> loadInputAsync())
            .publishOn(Schedulers.parallel())
            .map(analyzer::normalize);
~~~

`loadInputAsync()` là method trả `CompletionStage<EventInput>`; `analyzer.normalize` là phần CPU-bound cần triển khai. `publishOn(Schedulers.parallel())` chuyển các toán tử phía sau sang scheduler phục vụ CPU.

Nếu phải gọi hàm blocking:

~~~java
Mono<String> external =
        Mono.fromCallable(() -> legacyClient.lookup(eventId))
            .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` phù hợp hơn cho tác vụ chờ I/O đồng bộ; `parallel()` không nên bị dùng làm blocking pool. Không gọi `block()` trên Netty/WebFlux event loop.

**Nhưng đừng trộn mô hình vô lý:** `Mono.fromCompletionStage(...)` không tự làm toàn bộ thao tác của một future blocking trở thành non-blocking. Nếu `loadInputAsync()` thực chất gọi JDBC đồng bộ ngay trước khi trả future, thì đã chặn thread trước khi tạo `Mono`.

Spring Data Cassandra còn có **reactive APIs** riêng; reactive query không giống repository `@Async` dùng TaskExecutor. Cần chọn một mô hình có chủ đích và xác minh backpressure của từng tầng.

## 18. Observability: đo cả driver và worker executor

Nếu p99 tăng khi thêm thuật toán enrichment, không kết luận ngay “Cassandra chậm”. Đo các giai đoạn:

~~~text
HTTP admission
   |
   |  t_submit
   v
Driver executeAsync
   |
   |  t_db_response
   v
Light mapping callback
   |
   |  t_cpu_queue
   v
CPU executor
   |
   |  t_cpu_complete
   v
HTTP response
~~~

Các chỉ số nên có:

| Chỉ số | Chỉ ra vấn đề |
|---|---|
| Cassandra request latency và timeout | Database/network/partition access |
| Driver in-flight requests, pool usage | Quá nhiều request trên driver |
| I/O event-loop delay / callback duration | Callback nặng hoặc có blocking |
| CPU executor active threads, queue depth, rejected tasks | CPU saturation và overload |
| Blocking executor active/queue/rejections | Downstream chậm hoặc thiếu giới hạn |
| In-flight semaphore available permits | Admission capacity |
| Async page fetch count/latency | Paging/truy vấn quá rộng |
| CPU time của scoring/enrichment | Thuật toán quá đắt hoặc payload lớn |
| p95/p99 end-to-end theo route | Trải nghiệm API thực |
| Errors phân theo Cassandra/CPU/rejection/timeout | Khoanh vùng lỗi thay vì retry mù |
| Context/correlation coverage | Có thể truy vết yêu cầu qua executor |

**Không** đo bằng cách `Thread.sleep()` trong callback driver. Dùng timer/metrics không blocking, Java Flight Recorder, profiling có kiểm soát và load test staging. Khi ghi log, tránh xuất CQL bind values nhạy cảm hoặc toàn bộ payload của tenant.

## 19. Integration test: chứng minh callback nặng chạy trên pool riêng

Một unit test mock repository chứng minh service gọi executor, nhưng không chứng minh driver thật hoàn tất stage theo đường mong muốn. Dùng Cassandra test instance đã provision, chạy query hợp lệ và kiểm tra **thread name của executor ta sở hữu**, không assert driver I/O thread luôn có một tên cố định.

### 19.1. JUnit: thenApplyAsync chạy trên executor chỉ định

~~~java
package example.telemetry;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class AsyncCallbackThreadIntegrationTest {

    @Autowired CqlSession session;

    @Test
    void expensiveStageRunsOnDedicatedExecutor() throws Exception {
        ExecutorService cpu = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "test-cpu-worker"));

        try {
            SimpleStatement query = SimpleStatement.newInstance(
                    "SELECT event_id FROM device_events_by_day " +
                    "WHERE tenant_id = ? AND device_id = ? AND event_day = ?",
                    UUID.randomUUID(), UUID.randomUUID(),
                    LocalDate.of(2026, 11, 25));

            CompletableFuture<String> callbackThread =
                    session.executeAsync(query)
                            .thenApply(rs -> rs.one()) // Mapping nhẹ
                            .thenApplyAsync(
                                    row -> Thread.currentThread().getName(),
                                    cpu)
                            .toCompletableFuture();

            assertEquals("test-cpu-worker",
                    callbackThread.get(10, TimeUnit.SECONDS));
        } finally {
            cpu.shutdownNow();
        }
    }
}
~~~

**Vì sao test hợp lý?** Tên thread `test-cpu-worker` do chính test tạo ra; `thenApplyAsync(..., cpu)` được bảo đảm lên executor đó. Không cần có event thật trong partition: test chỉ đọc tên luồng sau khi query hoàn tất, không lấy field của `row`.

**Giới hạn:** `get(10, SECONDS)` nằm trên **JUnit test thread**, không phải callback driver. Test phải có keyspace và bảng từ migration; ở STEP 4 chỉ viết tài liệu, **chưa chạy CI/test**.

### 19.2. Test failure propagation mà không cần Cassandra

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;

@Test
void callbackChainKeepsFailureVisible() {
    CompletionStage<String> failed =
            CompletableFuture.failedFuture(
                    new IllegalStateException("Cassandra unavailable"));

    CompletionStage<Integer> derived =
            failed.thenApply(String::length);

    ExecutionException thrown = assertThrows(
            ExecutionException.class,
            () -> derived.toCompletableFuture().get());

    assertTrue(thrown.getCause() instanceof IllegalStateException);
}
~~~

Bài test chứng minh stage downstream vẫn thất bại; nếu code thực tế bỏ qua stage kết quả, caller không thể nhận lỗi đó.

### 19.3. Test tải/rejection

Với executor có queue capacity nhỏ, dùng latch trong một test unit cô lập để giữ worker bận, submit thêm task, rồi xác minh rejection được báo thành **thất bại có kiểm soát**. Không dùng `CallerRunsPolicy` trong bài test này vì nó có thể chạy task trên thread submit và che lỗi cô lập.

Nếu muốn kiểm tra driver I/O không bị callback chặn, chạy **load test** nhiều query độc lập cùng lúc, so sánh p95/p99 giữa `thenApply` với CPU nặng và `thenApplyAsync` có executor. Không rút ra kết luận hiệu năng từ một lần test vài record.

### 19.4. Các test nên bổ sung

| Tình huống | Kỳ vọng |
|---|---|
| Query trả 0 hàng | Không NPE; kết quả absent theo contract |
| Query trả 1 hàng | Mapping nhẹ, CPU offload đúng executor |
| Callback CPU ném exception | Stage lỗi; metrics/caller thấy đúng |
| Executor queue đầy | Rejection/busy có kiểm soát, không chạy trên I/O |
| Driver query timeout | Phân loại lỗi khác với lỗi CPU/rejection |
| Client cancel HTTP request | Không mặc định DB request đã bị rollback |
| Nhiều trang dữ liệu | `fetchNextPage()` non-blocking, giới hạn pages/in-flight |
| Thay tenant/day giữa paging | Không dùng lại state không phù hợp |
| Legacy HTTP chậm | Blocking pool bị giới hạn, không chặn driver I/O |
| MDC/tracing qua executor | Context được truyền và dọn đúng |
| Nhiều tenant/concurrent requests | Không lẫn dữ liệu/authorization |
| Hot partition hoặc payload lớn | p99 và resource consumption được đo |
| Repository `@Async` | Không nhầm việc schedule thread với non-blocking driver |

## 20. Lỗi phổ biến và cách khắc phục

| Chống mẫu | Hậu quả | Cách sửa |
|---|---|---|
| `session.execute()` trong `thenApply` của driver | Có thể bị driver phát hiện, deadlock risk | `executeAsync` + `thenCompose` |
| `future.join()` trong callback I/O | Chặn event loop | Nối stage, không block |
| `Thread.sleep` trong callback | Kéo dài p99 cho request khác | Deadline/async timer hoặc offload |
| Parse/decompress payload lớn bằng `thenApply` | Chiếm CPU driver I/O | `thenApplyAsync(..., cpuExecutor)` |
| HTTP/JDBC sync trong `thenApply` | Chặn I/O thread | Client async hoặc blocking executor |
| `thenApplyAsync` không có executor | Dùng pool mặc định khó kiểm soát | Executor rõ, bounded |
| CPU và blocking chia một pool nhỏ | Downstream chậm chiếm hết CPU workers | Pool riêng, giới hạn riêng |
| Queue worker vô hạn | Memory/latency tăng khi overload | Bounded queue + rejection |
| `CallerRunsPolicy` để giảm rejection | CPU work rơi lại vào driver I/O thread | AbortPolicy và admission control |
| Chỉ `thenAccept`, bỏ stage trả về | Lỗi có thể mất theo callback chain | Return stage, `whenComplete`/terminal handler |
| `exceptionally` trả empty list mọi lỗi | Timeout bị che như “không có data” | Chỉ fallback khi contract cho phép |
| `@Async` gọi từ `this.method()` | Bỏ qua Spring proxy | Gọi qua bean/proxy hoặc thiết kế khác |
| `@Async` bọc API driver async vô điều kiện | Double scheduling | Dùng native async trực tiếp |
| Tưởng `cancel(true)` rollback Cassandra | Sai trạng thái write | Idempotency và reconciliation |
| Fetch mọi async page rồi collect | OOM, quá tải Cassandra | Xử lý từng trang và giới hạn |
| Bỏ qua partition key vì “async nhanh” | Query sai/scan rộng | Thiết kế bảng theo truy vấn |
| Trông chờ ThreadLocal qua executor | Mất tenant/tracing, nguy cơ lỗi quyền | Context rõ, propagation có kiểm soát |

## 21. Bài tập thực hành

### Bài tập A — nhận diện callback nguy hiểm

~~~java
session.executeAsync(statement)
        .thenApply(rs -> {
            Thread.sleep(1000);
            return rs.one();
        });
~~~

Vì sao cách làm này làm giảm throughput? Ngoài việc `Thread.sleep` ném checked exception cần xử lý, phải sửa **ranh giới luồng** thế nào? Nếu mục tiêu là chờ một tác vụ I/O khác, nên dùng một API async và `thenCompose` hay một CPU executor?

### Bài tập B — CPU executor

Một hệ thống dùng 4 CPU cores, phải tính score mất 10 ms CPU mỗi event. Hãy thiết kế `ThreadPoolTaskExecutor` với queue hữu hạn, đo throughput, active workers và rejection. Vì sao không tạo 1.000 CPU threads để tăng hiệu năng?

### Bài tập C — blocking HTTP cũ

`LegacyGeoClient.lookup` có latency p99 = 2 giây. Hãy đưa nó ra khỏi callback I/O, tạo blocking executor, đặt request timeout và overload policy. Nếu downstream tăng latency lên 20 giây, cần cơ chế gì để không dồn queue vô hạn?

### Bài tập D — truy vấn nối tiếp

Một query trả `deviceId`, query tiếp theo lấy events của device/day. Viết chuỗi `executeAsync(...).thenCompose(...)` không dùng `get()/join()`; nêu cách xử lý query đầu trả `null`.

### Bài tập E — paging và CPU

Một partition có 800 events, page size 50. Thiết kế xử lý **một page CPU xong mới `fetchNextPage()`**, không materialize 800 events trong một danh sách lớn. Khi payload tăng từ 1 KB lên 2 MB, cần đánh giá lại page size và heap như thế nào?

### Bài tập F — lỗi callback

Một `whenComplete` chỉ log success, không log failure. Khi Cassandra timeout, stage downstream trạng thái gì? Vì sao phải **return/observe** stage thay vì bỏ qua nó? Nếu callback tự ném `IllegalArgumentException`, ai phải nhận lỗi?

### Câu hỏi tự kiểm tra

1. Callback gắn vào `CompletionStage` của `executeAsync` thường chạy ở đâu?
2. Nếu stage đã hoàn tất khi đăng ký `thenApply`, callback có thể chạy trên thread nào?
3. Vì sao `session.execute()` trong callback Driver có nguy cơ deadlock?
4. `thenApply` khác `thenCompose` về kiểu giá trị trả về thế nào?
5. Khi cần CPU nặng, nên chọn toán tử/executor nào?
6. `thenApplyAsync` không chỉ định executor có tự tạo pool cách ly nghiệp vụ không?
7. `CallerRunsPolicy` nguy hiểm thế nào ở callback I/O?
8. `AsyncCassandraOperations` khác Spring `@Async` về cơ chế nào?
9. `AsyncResultSet.currentPage()` có chứa mọi hàng của truy vấn không?
10. `fetchNextPage()` có bắt buộc block luồng gọi không?
11. `CompletableFuture.orTimeout` có bảo đảm server ngừng xử lý mutation không?
12. Vì sao không nên lưu tenant context chỉ trong `ThreadLocal` rồi dùng ở pool khác?
13. `LOCAL_QUORUM` có chữa lỗi callback CPU chậm không?
14. API bất đồng bộ có cho phép `WHERE` thiếu partition key không?
15. CPU pool rejection nên được xử lý ra sao?

**Đáp án gợi ý:** (1) thường driver I/O khi response hoàn tất; (2) có thể là thread đăng ký; (3) chặn I/O event loop cần để hoàn tất request; (4) ánh xạ `T→U` vs làm phẳng `T→CompletionStage<U>`; (5) `thenApplyAsync(fn, cpuExecutor)`; (6) không; (7) fallback chạy việc nặng ngay trên driver thread; (8) native driver non-blocking vs schedule method trên TaskExecutor; (9) không; (10) không, trả stage; (11) không; (12) context có thể không propagate; (13) không; (14) không; (15) overload/busy, backoff, không chạy inline.

## 22. Checklist trước khi triển khai

- [ ] Truy vấn Cassandra có **đầy đủ partition key**, clustering/range đúng schema.
- [ ] Dùng `executeAsync` hoặc `AsyncCassandraOperations` cho đường muốn non-blocking.
- [ ] Không gọi `execute()`, `get()`, `join()` hay `sleep()` trong driver I/O callback.
- [ ] `thenApply` và `whenComplete` chỉ thực hiện thao tác rất nhẹ, có giới hạn.
- [ ] Query nối tiếp bằng `thenCompose`, không block để lấy kết quả.
- [ ] CPU work dùng `thenApplyAsync(..., cpuExecutor)` với pool giới hạn.
- [ ] Blocking legacy I/O được cô lập trên executor riêng hoặc thay bằng client async thật.
- [ ] Không dùng `CallerRunsPolicy` nếu nó có thể chạy việc nặng trên driver I/O thread.
- [ ] Executor queue hữu hạn, có metrics và chính sách reject/admission.
- [ ] Có giới hạn tổng số request/stage in-flight và throughput phù hợp Cassandra.
- [ ] Caller nhận/quan sát `CompletionStage`; exception không bị nuốt.
- [ ] Phân biệt timeout/cancel/retry với kết quả mutation chưa xác định.
- [ ] Có chính sách idempotency cho writes, counters và LWT.
- [ ] Không coi `@Async` repository là native driver async mặc định.
- [ ] `@Async` đã bật, gọi qua Spring proxy và chọn executor đúng khi sử dụng.
- [ ] Reactive pipeline dùng `parallel` cho CPU, `boundedElastic` cho blocking khi phù hợp.
- [ ] Async paging dùng `currentPage`/`fetchNextPage`, không gom mọi page không giới hạn.
- [ ] Không đổi query/bind values khi tiếp tục paging state.
- [ ] Kiểm soát payload size, projection và hot partitions.
- [ ] Tenant/security/tracing context được truyền rõ qua executor, không phụ thuộc ThreadLocal ngầm.
- [ ] Có integration test kiểm chứng offload thread, lỗi/rejection/paging.
- [ ] Đã đo driver I/O, executor queue, p95/p99, timeout và in-flight.
- [ ] Đã xác nhận phiên bản Java Driver/Spring Data và API cụ thể trước khi build.
- [ ] Bài Markdown được ghi ở STEP 4; QA học thuật/Gradle/CI là bước riêng.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.19 — Async Programming](https://apache.github.io/cassandra-java-driver/4.19.0/core/async/).
- [Apache Cassandra Java Driver 4 — Paging](https://docs.datastax.com/en/developer/java-driver/latest/manual/core/paging/).
- [Apache Cassandra Java Driver — Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/).
- [Spring Data Cassandra — AsyncCassandraOperations API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/AsyncCassandraOperations.html).
- [Spring Data Cassandra — AsyncCassandraTemplate API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/AsyncCassandraTemplate.html).
- [Spring Data Cassandra — Repositories: Query Methods](https://docs.spring.io/spring-data/cassandra/reference/repositories/query-methods-details.html).
- [Spring Framework — Task Execution and Scheduling / @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
- [Apache Cassandra — CQL Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Java SE — CompletionStage API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html).
