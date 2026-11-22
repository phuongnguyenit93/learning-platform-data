# Giới hạn số yêu cầu đồng thời thay vì gửi không kiểm soát

> **Chương:** Bất đồng bộ và reactive  
> **Phạm vi:** Apache Cassandra với Java Driver 4.x, `CompletionStage`, `AsyncResultSet` và ví dụ tích hợp Reactor. Nội dung tập trung vào **giới hạn số request đang thực thi**, *backpressure*, kiểm soát hàng đợi, tải replica và quy trình bảo vệ dịch vụ khi lưu lượng tăng đột biến.
>
> **Mục tiêu học tập:** Biết vì sao `executeAsync()` không tự có nghĩa là hệ thống chịu được vô hạn request; phân biệt QPS, *in-flight concurrency*, connection pool và queue; tính ngân sách ban đầu bằng Little's Law; dùng cơ chế **admission control không chặn event loop**; tích hợp Java Driver và Reactor; đo tác động lên Cassandra, điều phối retry/speculation, và triển khai quá tải có kiểm soát.

## 1. Vấn đề: “bất đồng bộ” không có nghĩa là “vô hạn”

Một API Java nhận danh sách một triệu khóa cần đọc dữ liệu. Code dưới đây có vẻ hấp dẫn vì không dùng vòng lặp chờ từng kết quả:

```java
List<CompletionStage<AsyncResultSet>> requests = new ArrayList<>();

for (UUID orderId : orderIds) {
    requests.add(
        session.executeAsync(
            prepared.bind(tenantId, orderId)
        )
    );
}
```

**Vấn đề:** vòng lặp có thể tạo hàng trăm nghìn request gần như ngay lập tức. Mỗi lần gọi `executeAsync` không block như gọi CQL đồng bộ, nhưng vẫn có chi phí:

- Tạo object cho statement, future, callback, tracing/metrics và timeout.
- Đi qua hàng đợi và luồng xử lý của driver.
- Sử dụng connection pool và giới hạn request đồng thời trên mỗi connection.
- Tạo công việc coordinator, internode messages và đọc SSTable/memtable ở replica.
- Giữ buffer/heap của ứng dụng và server.
- Tăng xác suất timeout, retry, speculative execution và nghẽn tài nguyên.

Khi Cassandra chậm, số request chưa hoàn tất càng tăng. Nếu ứng dụng vẫn tiếp tục bơm vào, ta có thể gặp **tích tụ công việc**, làm p99 tăng và cuối cùng hết bộ nhớ hoặc mất khả năng phục vụ.

**Nguyên tắc bài học:** phải quyết định **khi nào một request được phép bắt đầu** thay vì chỉ quyết định “gửi bất đồng bộ thế nào”.

## 2. Hai hệ thống cùng phục vụ một thao tác

Một request đọc theo partition key đi qua nhiều tầng:

```text
HTTP / Kafka / Scheduled job
             |
             v
     Service application
             |
       Admission control
             |
     Java Driver 4.x
             |
         Coordinator
             |
       Replica R1/R2/R3
             |
     Memtable / SSTable
             |
          Response
```

Có ít nhất **hai ngân sách độc lập**:

1. **Ngân sách ứng dụng:** heap, CPU, request threads/event loops, số future đang chờ và thời gian phản hồi API.
2. **Ngân sách Cassandra:** coordinator queues, CPU, GC, disk I/O, network, replica response theo consistency level và công việc nền như compaction/repair.

Một limit ở ứng dụng phải được chọn theo **cả hai phía**. Nếu application chạy 20 instance, mỗi instance cho 500 request đồng thời, toàn hệ có thể gửi **10.000 logical requests in-flight** dù mỗi instance tưởng mình đã “giới hạn”.

Và đó mới là logical requests: retry/speculation hoặc paging fetch có thể tạo thêm work ở tầng driver/server.

## 3. Năm con số không nên gộp chung

| Khái niệm | Định nghĩa | Đơn vị | Dễ nhầm với |
| --- | --- | --- | --- |
| **Arrival rate / QPS** | Số logical requests tới trong một giây | request/s | Số request đồng thời |
| **In-flight concurrency** | Số request đã được nhận xử lý nhưng chưa hoàn tất | request | QPS hoặc số thread |
| **Queue depth** | Số request đang chờ **chưa được nhận vào xử lý** | request | In-flight requests |
| **Service time** | Thời gian một request tiêu thụ trong hệ được đo | ms | Thời gian chờ queue |
| **Connection pool capacity** | Năng lực kết nối và request đồng thời phía driver theo host | connections/requests | Mức concurrency an toàn của Cassandra |

Thêm một lớp nữa: **resource cost per request**. Hai CQL SELECT đều được tính “một request”, nhưng một truy vấn theo partition key nhỏ khác xa một truy vấn quét partition khổng lồ nhiều tombstone.

Vì vậy `maxInFlight = 100` chỉ là giới hạn **số lượng**, không tự đảm bảo chi phí CPU, disk hoặc network nằm trong ngân sách.

### Số thread không bằng số request

Với ứng dụng blocking, 100 thread có thể chờ 100 request. Với async, **một số ít event-loop threads** có thể quản lý hàng nghìn outstanding requests.

Đổi sang async làm **giảm nhu cầu thread-per-request**, nhưng không làm những yêu cầu ngoài hệ thống biến mất. Chính vì một thread có thể khởi tạo rất nhiều request, cơ chế **admission control** càng cần thiết.

## 4. Little's Law: liên hệ throughput, latency và concurrency

Một xấp xỉ hữu ích khi hệ tương đối ổn định:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số công việc trung bình đang ở trong hệ thống được đo.
- \(\lambda\): tốc độ hoàn tất hoặc đến trung bình của các request trong trạng thái ổn định.
- \(W\): thời gian trung bình một request ở trong hệ thống đó.

Ví dụ giả định:

```text
Throughput ổn định: 800 logical reads/s
Thời gian xử lý trung bình: 60 ms = 0,060 s

L = 800 x 0,060 = 48 in-flight reads trung bình
```

**48 không phải giới hạn tối ưu được tính tự động.** Nó là ước lượng mức in-flight trung bình ở trạng thái ổn định, chưa tính burst, p99, request cost không đều hoặc công việc nền.

Nếu latency trung bình tăng gấp ba lần trong khi arrival rate giữ nguyên:

```text
800 reads/s x 0,180 s = 144 in-flight reads trung bình
```

Đó là dấu hiệu vì sao hệ thống có thể rơi vào vòng xoáy: **latency tăng → in-flight tăng → thêm áp lực → latency tiếp tục tăng**.

### Khi nào Little's Law không đủ?

- Thời gian đo quá ngắn, hệ chưa ổn định.
- Có nhiều loại query với chi phí rất khác nhau.
- Request bị queue/reject trước khi gửi.
- Workload có burst và fan-out lớn.
- Driver retry/speculative execution làm một logical request có nhiều coordinator attempts.
- Dữ liệu hot partition/tombstone khiến tail latency khác xa trung bình.

Dùng công thức để xây **giả thuyết ban đầu**, sau đó kiểm tra bằng benchmark và metrics.

## 5. Thế nào là một giới hạn đúng chỗ?

Hãy tách rõ:

```text
             REQUEST ĐẾN
                   |
                   v
          Có slot in-flight?
             /           \
           Có             Không
           |                |
           v                v
    Chạy Cassandra     Reject / Queue bounded
           |                |
           v                v
     CompletionStage   429/503 hoặc chờ
      hoàn tất          có deadline
           |
           v
      Release slot
```

**Slot nên được lấy trước khi bắt đầu gọi `session.executeAsync`.**

Nếu app gọi `executeAsync` trước rồi mới cố lấy slot, request đã có thể vào pool/queue của driver. Ta chỉ giới hạn số callback được xử lý, **không ngăn tải đã phát vào Cassandra**.

### Xác định phạm vi của slot

Trong bài này, một slot đại diện cho **một logical operation** từ lúc được nhận vào tầng repository đến khi stage cần bảo vệ hoàn tất.

Đây **không** là giới hạn tổng số RPC vật lý:

- Driver có thể retry sau một lỗi.
- Driver có thể speculative một SELECT idempotent.
- Một page fetch khác tạo logical request riêng.
- Coordinator có thể liên hệ nhiều replica.

Muốn giới hạn sát vật lý hơn, phải kết hợp driver metrics, retry/speculation policy và capacity budget ở server.

## 6. Ba chiến lược quá tải

| Cách | Khi hết slot | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- | --- |
| **Fail fast / shed load** | Trả lỗi có kiểm soát ngay | Không tạo hàng đợi lớn; bảo vệ Cassandra tốt | Client cần retry/backoff phù hợp |
| **Bounded queue** | Chờ trong hàng đợi nhỏ, có deadline | Hấp thụ burst ngắn | Thêm queue latency; cần expiry và fairness |
| **Async wait-for-permit** | Trả future chờ slot, không block thread | Không chặn event loop | Nếu không giới hạn số người chờ thì vẫn là **queue vô hạn** |

Cách nguy hiểm nhất thường là:

```text
“Không có slot thì cứ đợi”
+
không giới hạn số người đợi
+
không có deadline
+
upstream vẫn gửi liên tục
```

Nó chỉ chuyển một **unbounded driver queue** thành một **unbounded application queue**.

Với API tương tác, bắt đầu bằng **fail fast** có thể là phương án dễ quản lý. Với batch processing, một **queue có giới hạn hoặc cơ chế demand từ nguồn** thường phù hợp hơn. Không có một chính sách áp cho mọi nghiệp vụ.

## 7. Không dùng `Semaphore.acquire()` trên event loop

Java có `Semaphore` để quản lý permits. Nhưng có sự khác nhau quan trọng:

```java
// Không làm thế này trên Netty/Reactor event-loop thread.
semaphore.acquire();
return session.executeAsync(statement);
```

`acquire()` có thể **block thread** đến khi có permit. Nếu thread đó là event loop đang dùng để chạy callback, mạng hoặc request handling, ta có thể gây:

- Tắc event loop.
- Thời gian phản hồi tăng cho nhiều request không liên quan.
- Deadlock/starvation khi callback cần chạy trên một thread đang bị chặn.
- Thread pool exhaustion dưới tải.

Đường async nên dùng **`tryAcquire()` không chờ** hoặc một **async semaphore có bounded waiters**.

```java
if (!semaphore.tryAcquire()) {
    // Từ chối sớm, không block event loop.
}
```

Để hấp thụ burst, đừng “sửa” bằng cách chuyển mọi request sang một thread pool vô hạn. Phải giới hạn **cả số request đang chạy và số request đang chờ**.

## 8. Java 17: bộ giới hạn bất đồng bộ có thể tái sử dụng

Ví dụ sau là một **admission gate không chờ**. Nó dùng `Semaphore.tryAcquire()` để lấy slot **trước** khi tạo Cassandra request và trả `CompletionStage` thất bại nếu quá tải.

```java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

public final class AsyncInFlightLimiter {

    public static final class BusyException extends RuntimeException {
        public BusyException(String message) {
            super(message);
        }
    }

    private final Semaphore permits;
    private final int maxInFlight;

    public AsyncInFlightLimiter(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive");
        }
        this.maxInFlight = maxInFlight;
        this.permits = new Semaphore(maxInFlight);
    }

    public <T> CompletionStage<T> submit(
            Supplier<? extends CompletionStage<T>> operation) {

        // Admission xảy ra TRƯỚC khi operation tạo request.
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new BusyException("Cassandra capacity is busy"));
        }

        final CompletionStage<T> stage;

        try {
            stage = Objects.requireNonNull(
                operation.get(), "operation must return a stage"
            );
        } catch (RuntimeException ex) {
            permits.release();
            return CompletableFuture.failedFuture(ex);
        } catch (Error fatal) {
            permits.release();
            throw fatal;
        }

        // Release cả khi thành công và thất bại; tuyệt đối
        // không release ngay sau khi gọi executeAsync.
        return stage.whenComplete(
            (value, failure) -> permits.release()
        );
    }

    public int getInFlight() {
        return maxInFlight - permits.availablePermits();
    }

    public int getAvailable() {
        return permits.availablePermits();
    }

    public int getMaxInFlight() {
        return maxInFlight;
    }
}
```

### Những bất biến của mã

1. **Không vượt quá `maxInFlight`** admission slots tại một instance limiter.
2. Không có blocking wait trên event loop.
3. Nếu `operation.get()` ném exception đồng bộ, permit được hoàn trả.
4. Khi asynchronous stage hoàn tất thành công hoặc lỗi, permit được hoàn trả.
5. Khi hết permit, request **không được tạo** và backend có thể trả lỗi quá tải có kiểm soát.
6. Mã không tạo một hàng đợi nội bộ không giới hạn.

**Quan trọng:** `whenComplete` phải gắn vào **stage bao gồm toàn bộ vùng công việc cần bảo vệ**. Nếu stage gốc chỉ biểu thị lúc driver nhận response metadata nhưng application còn xử lý thêm nhiều trang hoặc chạy tác vụ downstream, permit có thể được thả quá sớm.

### Giới hạn của ví dụ

- `Semaphore` này bảo vệ **một đối tượng limiter trong một JVM**, không phải toàn cluster Cassandra.
- Không có fairness theo tenant, priority hay weighted cost.
- Nó **không tự hủy** request đang chạy khi HTTP caller ngắt kết nối.
- Nó không bảo đảm driver không retry/speculate bên trong một logical request.
- Khi release permit sau stage, cần tránh callback nặng ngay trên I/O thread.
- Nếu lập trình viên không bao hết chuỗi xử lý vào stage hoặc không có timeout, có thể giữ permit quá lâu.

Đây là **nền tảng dễ kiểm chứng** để giải thích admission control, không phải thư viện điều phối đầy đủ cho mọi loại tải.

## 9. Không release permit ngay sau `executeAsync`

Ví dụ sai:

```java
semaphore.acquire();
try {
    return session.executeAsync(statement);
} finally {
    semaphore.release();
}
```

`executeAsync` trả một future gần như ngay lập tức, **không có nghĩa query đã xong**. `finally` chạy ngay sau khi khởi tạo request, nên slot được thả trước khi Cassandra xử lý xong.

Ví dụ đúng về nguyên tắc:

```java
if (!semaphore.tryAcquire()) {
    return CompletableFuture.failedFuture(
        new IllegalStateException("busy")
    );
}

try {
    return session.executeAsync(statement)
        .whenComplete((result, error) -> semaphore.release());
} catch (RuntimeException ex) {
    semaphore.release();
    throw ex;
}
```

Đoạn này minh họa đường đời permit. Nếu trả result cho tầng khác tự fetch thêm trang, **phải quyết định** slot có cần giữ qua các page fetch hay mỗi page có slot riêng. Đừng lẫn một `AsyncResultSet` chứa **trang hiện tại** với toàn bộ cursor nhiều trang.

## 10. Bảng Cassandra mẫu: query-first để hạn chế chi phí

Giả sử ứng dụng cần đọc một đơn theo tenant và mã đơn. Tạo bảng theo đúng truy vấn:

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    status text,
    total decimal,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Giả định keyspace `lab` đã tồn tại với replication strategy, RF/DC và security phù hợp cluster lab.

Ghi dữ liệu (bằng role có quyền):

```cql
INSERT INTO lab.orders_by_id (
    tenant_id, order_id, customer_id, status, total, updated_at
) VALUES (
    'tenant-a',
    11111111-1111-4111-8111-111111111111,
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    'PAID',
    250.00,
    '2026-11-21T10:00:00Z'
);
```

Truy vấn theo **đầy đủ partition key**:

```cql
SELECT order_id, status, total
FROM lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-4111-8111-111111111111;
```

Nếu query thiếu tenant hoặc truy vấn `status='PAID'` không có partition key, việc tăng/giới hạn in-flight **không thay cho thiết kế bảng theo truy vấn**. Một request nặng trên partition khổng lồ vẫn có thể chiếm nhiều tài nguyên.

## 11. Tích hợp limiter vào Java Driver 4.x

Repository sau giữ slot cho đến khi đã nhận **một row** và map kết quả từ `AsyncResultSet`.

```java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AsyncOrdersRepository {

    public record OrderView(
        UUID orderId, String status, BigDecimal total) {}

    private final CqlSession session;
    private final AsyncInFlightLimiter limiter;
    private final PreparedStatement byId;

    public AsyncOrdersRepository(
            CqlSession session,
            AsyncInFlightLimiter limiter) {
        this.session = Objects.requireNonNull(session);
        this.limiter = Objects.requireNonNull(limiter);
        this.byId = session.prepare(
            "SELECT order_id, status, total " +
            "FROM lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public CompletionStage<Optional<OrderView>> find(
            String tenantId, UUID orderId) {

        if (tenantId == null || tenantId.isBlank() ||
            orderId == null) {
            throw new IllegalArgumentException(
                "tenantId and orderId are required");
        }

        // Validation và authorization xảy ra trước admission.
        // Tầng API phải xác minh tenantId từ authenticated principal.
        BoundStatement statement = byId
            .bind(tenantId, orderId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        return limiter.submit(() ->
            session.executeAsync(statement)
                .thenApply(result -> {
                    Row row = result.one();

                    if (row == null) {
                        return Optional.<OrderView>empty();
                    }

                    return Optional.of(new OrderView(
                        row.getUuid("order_id"),
                        row.getString("status"),
                        row.getBigDecimal("total")
                    ));
                })
        );
    }
}
```

### Luồng thực tế

```text
HTTP request
    |
    +--> auth/tenant/resource check
    +--> prepare / bind statement
    |
    +--> limiter.tryAcquire()
            |
            +--> Không có slot -> failed stage -> 429/503
            |
            +--> Có slot
                   |
                   +--> session.executeAsync()
                   +--> map AsyncResultSet -> OrderView
                   +--> completion success/error
                   +--> release permit
```

**Điểm cốt lõi:** `session.executeAsync` chỉ được gọi **bên trong supplier** được limiter cho phép chạy. Nếu gọi nó trước `submit`, tải đã phát sinh và gate trở nên vô nghĩa.

### Giả định của code

- Java 17 cho `record`, Java Driver 4.x có `CqlSession` và `AsyncResultSet`.
- `LOCAL_QUORUM` chỉ phù hợp khi RF trong local DC đủ và replica khả dụng; môi trường một node phải chọn CL thích hợp.
- `find` chỉ đọc một partition và tối đa một row theo khóa chính nên không cần fetch trang tiếp.
- `setIdempotent(true)` thích hợp với SELECT thuần túy này, **không bật mặc định cho mọi mutation**.
- Tầng HTTP kiểm soát quyền user/tenant, không chỉ dựa vào Cassandra service-account role.
- `CqlSession` và `PreparedStatement` được tái sử dụng, không tạo lại trên mỗi request.
- Nếu chuyển mapping sang tác vụ CPU nặng, cần executor/bulkhead riêng và mở rộng phạm vi đo, tránh blocking trên driver I/O thread.

## 12. Chuyển lỗi bận thành HTTP response đúng ý nghĩa

Khi gate từ chối request, đó là **quyết định bảo vệ năng lực**, không phải Cassandra đã trả một exception.

Ví dụ khái niệm:

| Tình huống | HTTP response có thể dùng | Lưu ý |
| --- | --- | --- |
| Người dùng vượt quota tenant | `429 Too Many Requests` | Có thể kèm `Retry-After` có cơ sở |
| Service tạm hết năng lực DB | `503 Service Unavailable` | Không khiến gateway retry đồng loạt |
| Caller chưa xác thực | `401 Unauthorized` | Xử lý trước admission DB |
| Caller không được đọc tenant | `403 Forbidden` | Không tiêu thụ slot DB |
| Input sai | `400 Bad Request` | Validation trước admission |
| Driver timeout / replica unavailable | `503` hoặc `504` theo hợp đồng | Phân loại riêng, không lẫn overload admission |

`429`/`503` là lựa chọn hợp đồng API, không phải quy tắc bắt buộc duy nhất. Điều thiết yếu là **client hiểu đây là tín hiệu quá tải có kiểm soát** và không retry vô hạn ngay lập tức.

### Tín hiệu retry có thể gây “thundering herd”

Nếu 100.000 client nhận `503` và cùng retry sau đúng 1 giây, cluster có thể chịu một burst mới đúng thời điểm đó.

Cần:

- Exponential backoff + **jitter**.
- Giới hạn retries và **end-to-end deadline**.
- Cơ chế rate limit ở gateway/consumer.
- Không retry non-idempotent writes một cách mù quáng.
- Không phát retry khi request đã hết mục tiêu nghiệp vụ.

**Admission control chỉ hiệu quả nếu upstream tôn trọng tín hiệu backpressure hoặc có quyền bị từ chối.**

## 13. Tại sao `CompletableFuture.allOf` không giới hạn concurrency?

Sai lầm phổ biến:

```java
List<CompletableFuture<?>> pending = new ArrayList<>();

for (UUID id : ids) {
    pending.add(
        session.executeAsync(prepared.bind(tenant, id))
            .toCompletableFuture()
    );
}

return CompletableFuture.allOf(
    pending.toArray(new CompletableFuture<?>[0])
);
```

`allOf` là công cụ **chờ nhiều future hoàn tất**. Nó **không giới hạn số futures đã được tạo**, không tạm dừng vòng lặp khởi phát và không ngăn request tới Cassandra.

Với một triệu item, ví dụ còn tạo danh sách futures rất lớn trên heap.

### Hai cách thay thế

**Cách A — Batch/window cố định:** lấy tối đa K khóa, phát tối đa K request, đợi batch kết thúc rồi lấy batch tiếp theo. Đơn giản nhưng có thể làm giảm utilization khi một request đuôi chậm khiến batch tiếp theo phải chờ.

**Cách B — Sliding window/concurrency-limited stream:** khi một request hoàn tất, cho phép lấy thêm một item từ nguồn. Giữ tối đa K phần tử đang xử lý mà không buộc chờ request chậm nhất của batch.

Với Reactor hoặc Reactive Streams, cách B dễ mô tả qua **`flatMap(..., concurrency)`** khi nguồn phát có backpressure thực sự. Đồng thời vẫn giữ **global admission gate** vì từng stream không nhìn thấy tổng tải từ các request HTTP khác.

## 14. Reactor: dùng `flatMap` với mức concurrency hữu hạn

Ví dụ trong một tác vụ đọc nhiều đơn hàng:

```java
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveOrdersService {
    private final AsyncOrdersRepository repository;

    public ReactiveOrdersService(AsyncOrdersRepository repository) {
        this.repository = repository;
    }

    public Flux<AsyncOrdersRepository.OrderView> loadMany(
            String tenantId, List<UUID> orderIds) {

        final int maxConcurrentReadsInThisStream = 16;

        return Flux.fromIterable(orderIds)
            .flatMap(orderId ->
                Mono.defer(() ->
                    Mono.fromCompletionStage(
                        repository.find(tenantId, orderId)
                    )
                ),
                maxConcurrentReadsInThisStream
            )
            .flatMapIterable(optional ->
                optional.<List<AsyncOrdersRepository.OrderView>>
                    map(List::of)
                    .orElseGet(List::of)
            );
    }
}
```

Ý nghĩa:

- `Flux.fromIterable` phát khóa theo nhu cầu của chuỗi.
- `flatMap(mapper, 16)` giới hạn số inner publishers được subscribe đồng thời trong **stream này**.
- `Mono.defer` trì hoãn việc gọi `repository.find` đến khi có subscription/demand.
- `Mono.fromCompletionStage` chuyển kết quả bất đồng bộ thành Publisher.
- `AsyncOrdersRepository` vẫn có **limiter toàn service instance** để bảo vệ khi nhiều HTTP requests/batch streams chạy cùng lúc.
- Code bỏ qua những kết quả `Optional.empty()`; đó là lựa chọn minh họa cho batch đọc, **không nên dùng để che lỗi truy vấn**.

### Tại sao cần cả giới hạn 16 và global limiter?

Giả sử có 100 HTTP requests đồng thời, mỗi request khởi một `Flux` cho phép 16 reads:

```text
100 streams x 16 reads/stream = có thể 1.600 logical reads cùng lúc
```

`flatMap(..., 16)` chỉ kiểm soát **một pipeline**. Nếu service đặt global limit 80, chỉ 80 request được nhận vào tầng Cassandra của **instance đó**, còn requests khác bị từ chối sớm hoặc phải chờ ở một bounded queue đã thiết kế.

**Không dùng flatMap concurrency local để suy ra ngân sách toàn ứng dụng.**

### Khi cần giữ thứ tự đầu vào

`flatMap` có thể phát kết quả **khác thứ tự** `orderIds` vì các request hoàn tất không cùng lúc.

Nếu thứ tự là hợp đồng quan trọng:

- Dùng toán tử bảo toàn thứ tự phù hợp như `flatMapSequential` với concurrency hữu hạn, có lưu ý chi phí buffer; hoặc
- Gắn index/key và sắp xếp theo thứ tự mong muốn ở phạm vi giới hạn.

`concatMap` xử lý tuần tự thường dễ giữ thứ tự nhưng chỉ có một inner subscription tại một thời điểm, có thể không khai thác đủ concurrency cho batch I/O.

## 15. Backpressure của Reactive Streams là gì?

Reactive Streams định nghĩa cơ chế **demand**: downstream có thể yêu cầu một lượng phần tử nhất định từ upstream thông qua `request(n)`.

Sơ đồ khái niệm:

```text
Downstream consumer
   |
   | request(16)
   v
Upstream publisher
   |
   | chỉ phát theo demand và contract
   v
flatMap(concurrency = 16)
   |
   | tối đa 16 inner subscriptions đang hoạt động
   v
Async Cassandra repository
```

Nhưng cần phân biệt:

1. **Backpressure trên publisher:** phần tử được phát theo nhu cầu.
2. **Admission control trước `executeAsync`:** request Cassandra có được khởi tạo hay không.
3. **Hàng đợi driver/server:** sau khi request đã được gửi, backpressure trên Flux không tự thu hồi mọi công việc.

Nếu upstream vốn là một callback/event source không thể tạm dừng (ví dụ một event bus cụ thể), cần chiến lược **bounded buffer + overflow policy** hoặc cơ chế pause/poll demand từ nguồn.

**Một pipeline reactive không tự động an toàn nếu nguồn có thể bơm dữ liệu vô hạn hoặc inner work tạo request trước lúc subscribe.**

## 16. Các toán tử reactive dễ bị dùng sai

| Toán tử/kỹ thuật | Dùng đúng khi | Hiểu lầm thường gặp |
| --- | --- | --- |
| `flatMap(mapper, K)` | Giới hạn số inner publishers đồng thời trong stream | “Tổng app chỉ có K request” |
| `concatMap` | Cần thứ tự và chấp nhận xử lý tuần tự | “Mọi workload đều nên tuần tự” |
| `flatMapSequential` | Cần kết quả đúng thứ tự với concurrency | “Không tốn buffer khi phần tử đầu chậm” |
| `limitRate` | Điều tiết demand/prefetch ở chuỗi Reactor | “Chặn tổng in-flight Cassandra của mọi request” |
| `onBackpressureBuffer` | Có buffer **đã giới hạn** và chính sách overflow | “Có thể buffer vô hạn an toàn” |
| `onBackpressureDrop` | Domain chấp nhận mất phần tử | “Có thể bỏ đơn thanh toán hoặc event bắt buộc” |
| `onBackpressureLatest` | Chỉ dữ liệu mới nhất có ý nghĩa | “Được dùng cho bất kỳ queue nghiệp vụ nào” |
| `timeout` | Có deadline cho chain reactive | “Server chắc chắn đã ngừng xử lý sau cancellation” |
| `retryWhen` | Lỗi tạm và thao tác idempotent, budget rõ | “Thêm retry là đủ chống quá tải” |

**Không làm mất dữ liệu nghiệp vụ để đổi lấy throughput.** Với command thanh toán, audit event hoặc mutation bắt buộc, `drop/latest` có thể sai hoàn toàn. Dùng durable queue có backpressure/acknowledgement và xác minh nguồn khi cần không mất sự kiện.

## 17. Reactive Cassandra: phân biệt từng trang và toàn bộ result

Java Driver 4.x có khả năng truy vấn bất đồng bộ và các phiên bản/distribution hỗ trợ Reactive Streams theo API tương ứng. Khi dùng `AsyncResultSet`, phải nhớ:

- `currentPage()` chỉ duyệt trang hiện tại.
- `hasMorePages()` cho biết liệu còn trang sau.
- `fetchNextPage()` chủ động yêu cầu trang kế.
- `setPageSize(50)` không giới hạn **tổng số row** của query.
- Một request API có thể cần nhiều protocol pages nếu thiết kế yêu cầu.

### Giới hạn in-flight cho từng page fetch

```java
CompletionStage<AsyncResultSet> first =
    limiter.submit(() -> session.executeAsync(statement));

CompletionStage<AsyncResultSet> next =
    first.thenCompose(result -> {
        if (!result.hasMorePages()) {
            return CompletableFuture.completedFuture(result);
        }

        // Trang kế là một thao tác DB mới:
        // phải đi qua limiter nếu muốn kiểm soát riêng.
        return limiter.submit(result::fetchNextPage);
    });
```

Đoạn code chỉ minh họa **hai page fetches**, không gom toàn bộ rows vào một kết quả hay lặp tất cả pages. Cần import `CompletionStage`, `CompletableFuture` và `AsyncResultSet` như trong phần Java trước.

### Hai cách đặt phạm vi permit

**Cách 1 — Mỗi page fetch một permit.** Hữu ích khi trang được gửi qua nhiều HTTP requests có cursor; permit được giữ chỉ trong lúc một page fetch hoạt động. Có thể có nhiều request khác xen vào giữa các trang.

**Cách 2 — Một permit cho cả chuỗi fetch + xử lý cuối.** Hữu ích cho batch có ngân sách nhỏ cần bảo đảm cả workflow bounded. Nhưng nếu giữ permit trong khi downstream tiêu thụ chậm hoặc user ngừng cuộn, có nguy cơ giữ slot quá lâu.

**Không giữ một permit DB xuyên nhiều phút chờ người dùng bấm trang kế.** API cursor có TTL nhưng DB permit chỉ nên bảo vệ công việc thực đang diễn ra.

## 18. Không chạy CPU nặng trên driver I/O thread

Một đoạn Java callback kiểu:

```java
return session.executeAsync(statement)
    .thenApply(result -> expensiveJsonSerialization(result));
```

có thể được thực thi trong thread hoàn tất future, tùy implementation/scheduling. Nếu callback làm CPU nặng hoặc block I/O, nó có thể làm chậm driver event loops/hoàn tất request khác.

Hướng xử lý:

- Chỉ làm mapping nhỏ, không chặn, trong callback đơn giản.
- Dùng **executor riêng có queue và concurrency limit** cho công việc CPU nặng, nếu thật sự cần.
- Phân biệt limit **Cassandra I/O** với limit **CPU/serialization**.
- Đo latency từ khi nhận request đến khi response được serialize xong, không chỉ thời gian driver có result.

### Nếu dùng `thenApplyAsync`

```java
CompletionStage<ResponseDto> response =
    session.executeAsync(statement)
        .thenApplyAsync(
            result -> toResponseDto(result),
            boundedMappingExecutor
        );
```

`boundedMappingExecutor` là một executor do ứng dụng quản lý, **có giới hạn threads/queue**. Đoạn mã không định nghĩa executor này; không dùng một executor mặc định không kiểm soát rồi tin rằng đã giới hạn đủ mọi tầng.

Cần quyết định permit DB được release sau driver completion hay sau mapping: nếu mục tiêu là bảo vệ **tổng request service**, giữ qua mapping; nếu mục tiêu chỉ Cassandra in-flight, tách metrics và permits theo tầng.

## 19. Throttle QPS khác limit in-flight

Một API chỉ cho 1.000 QPS không có nghĩa số request đồng thời luôn nhỏ. Nếu latency tăng, in-flight tăng dù QPS không đổi.

Ví dụ:

| Arrival rate | Service time trung bình | In-flight trung bình giả định |
| ---: | ---: | ---: |
| 100 req/s | 50 ms | 5 |
| 500 req/s | 50 ms | 25 |
| 500 req/s | 300 ms | 150 |
| 1.000 req/s | 300 ms | 300 |

Bảng minh họa bằng Little's Law trong trạng thái ổn định. Con số thực tế phải đo.

### Kết hợp nhiều lớp

- **Token bucket/rate limit:** giới hạn tốc độ đầu vào trung bình và burst.
- **In-flight limit:** giới hạn số request đang sử dụng tài nguyên.
- **Queue limit:** giới hạn công việc đang chờ.
- **Deadline:** giới hạn thời gian một request được phép chiếm tài nguyên.
- **Retry budget:** giới hạn các request phụ do lỗi.
- **Circuit breaker:** giảm việc gửi khi downstream không thể đáp ứng.

Không có lớp nào hoàn toàn thay thế các lớp khác.

## 20. Hàng đợi có giới hạn: chờ bao lâu là hợp lý?

Một queue nhỏ có thể hấp thụ burst vài chục mili giây. Nhưng một queue dài khiến request hết deadline **trước khi có slot chạy DB**.

Ví dụ:

```text
Max in-flight:        80
Max waiting:          40
Max queue wait:       50 ms
End-to-end deadline:  500 ms
Nếu cả chạy + chờ đã đầy -> reject ngay
```

Các con số chỉ là mẫu để hiểu thiết kế, không phải ngưỡng Cassandra chính thức.

### Bốn ràng buộc cần có ở queue

1. **Max queue length** — không thể đưa request vô hạn vào RAM.
2. **Max queue wait** — request đã chờ quá lâu phải rời queue.
3. **Request deadline** — không nhận request khi thời gian còn lại không đủ.
4. **Fairness/priority** — một tenant/workload không chiếm sạch queue của tenant khác.

Nếu một request hết hạn trong lúc chờ, **xóa nó khỏi queue và không tạo CQL request**. Nếu đã gửi vào Cassandra rồi, huỷ future phía client không bảo đảm server dừng công việc ngay.

### Cảnh báo về “async semaphore”

Một implementation dùng `CompletableFuture` chờ permit nhưng không giới hạn số futures chờ chỉ là **hàng đợi vô hạn khoác áo async**.

Nếu thiết kế async waiters, phải có cơ chế hoàn thành/thất bại khi timeout, removal khi cancel, xử lý race giữa release và expiry, và release đúng một lần. Việc này đủ phức tạp để ưu tiên một thư viện đã kiểm thử hoặc fail-fast gate đơn giản trong giai đoạn đầu.

## 21. Deadline và cancellation: tránh hiểu nhầm

Có các thời hạn khác nhau:

```text
HTTP client deadline
     |
API budget, auth/rate/queue wait
     |
Java driver request timeout
     |
Cassandra coordinator/replica timeout
```

Ví dụ HTTP có deadline 500 ms; request chờ queue 450 ms. Dù Cassandra có thể xử lý SELECT trong 100 ms, **không còn đủ thời gian** để hoàn tất API.

Một thiết kế tốt phải:

- Kiểm tra ngân sách còn lại **trước admission**.
- Không giữ request quá hạn trong queue.
- Phát request với timeout phù hợp ngân sách còn lại theo API/driver version.
- Không retry khi deadline đã hết.
- Release permit khi **công việc thật sự được tính trong scope hoàn tất**.
- Ghi rõ cancellation có thể **không rollback hoặc không dừng ngay server-side work**.

### Không “giải phóng sớm” permit để tăng throughput giả

Nếu HTTP client cancel sau 30 ms nhưng driver request vẫn chưa được cancel/hoàn tất, thả slot ngay rồi nhận request khác có thể làm **physical work đang chạy vượt budget**.

Cách bảo thủ là buộc slot gắn với completion của driver stage. Nhưng vẫn phải dùng request timeout và theo dõi leaked/long-running operations.

**Client timeout không tương đương server không còn xử lý.** Điều này đặc biệt quan trọng với writes.

## 22. Retry và speculative execution làm tăng số attempts

Giả sử limiter chỉ cho 100 logical requests. Nếu driver policy cho phép một speculative attempt trên 15% reads và có retry trên lỗi, coordinator/replica vẫn có thể thấy **hơn 100 physical attempts**.

```text
100 logical requests đã admitted
    |
    +--> 100 primary execution attempts
    +--> ~15 speculative attempts (minh họa)
    +--> retries sau một số lỗi
    |
    v
>100 coordinator attempts có thể cùng phát sinh
```

Do đó:

- Limiter ở tầng service **không thay** `RetryPolicy` và `SpeculativeExecutionPolicy`.
- Một statement chỉ nên `setIdempotent(true)` sau khi xác minh ngữ nghĩa lặp an toàn.
- Với counter increments, list append, side effects và LWT cần đặc biệt thận trọng.
- Một request timeout không chứng minh mutation chưa được ghi ở replica.
- Nếu nhiều tầng HTTP/message gateway cùng retry, cần **ngân sách end-to-end**.

### Giới hạn concurrency chưa đủ để chặn retry storm

Khi cluster đã chậm, 100 slots có thể được giữ lâu hơn. Nếu vừa tăng maxInFlight để “hết BusyException” vừa bật nhiều retry, có thể làm cluster tệ hơn.

**Quy tắc:** khi p99 và pending queue tăng, trước hết xem nguồn tải, query shape, retries/speculation và downstream health. Không tăng cap như một phản xạ.

## 23. Consistency level thay đổi mức công việc trên replica

Trong Cassandra, coordinator chọn replica theo partition key/token và RF/DC của keyspace. Consistency level quy định bao nhiêu replica phải phản hồi trước khi request được xem là thành công.

Ví dụ RF=3 trong một local datacenter:

| CL | Ý nghĩa khái niệm | Hệ quả với in-flight |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica local phản hồi | Có thể nhanh hơn nhưng thấy phiên bản dữ liệu khác trong một số trường hợp |
| `LOCAL_QUORUM` | Hai replica local phản hồi | Nhu cầu phản hồi và độ trễ phụ thuộc ít nhất quorum |
| `ALL` | Yêu cầu phản hồi của mọi replica theo RF | Nhạy với replica chậm/offline hơn |
| `QUORUM` | Quorum tổng theo replication | Trong nhiều DC có thể khác đường phản hồi |
| `EACH_QUORUM` | Dùng cho write theo quorum từng DC | Chi phí và availability khác |

**Không hạ CL chỉ để “giảm in-flight”** khi ứng dụng yêu cầu bảo đảm nhất quán cao hơn. Đó là thay đổi correctness contract, không đơn thuần là tuning hiệu năng.

### Local DC quan trọng

Ứng dụng Java ở `dc1` nhưng driver local DC lại trỏ sang `dc2` có thể làm tăng round-trip WAN, giữ slot lâu hơn và tăng in-flight ở cùng QPS.

Kiểm tra:

- `withLocalDatacenter(...)` hoặc effective driver configuration.
- RF trong keyspace với `NetworkTopologyStrategy`.
- Coordinator/DC thực tế của request.
- Replication/repair/streaming health.
- CL của từng statement.

**Admission budget phải được đo lại sau thay đổi CL, RF, DC hoặc topology.**

## 24. Một “request” có thể tốn rất nhiều CPU và I/O

Nếu cho phép 80 concurrent SELECT, nhưng 10 query thuộc loại đọc một partition có 100.000 row và nhiều tombstone, hệ vẫn có thể bão hòa.

Một số yếu tố chi phối chi phí:

- Partition key có đủ và chọn đúng bảng theo truy vấn?
- Có hot partition hoặc bucket quá lớn?
- Số SSTable phải đọc, compaction backlog?
- Tombstone/TTL đã hết hạn hoặc delete-heavy?
- Số row/byte được trả và paging behavior?
- SAI/secondary index hoặc `ALLOW FILTERING` có mở rộng phạm vi đọc?
- Driver có fetch nhiều trang liên tiếp?
- Query có UDF/UDA tốn CPU?
- Network giữa coordinator và replica/DC?

### Ưu tiên phân loại workload

| Loại request | Ví dụ | Admission strategy |
| --- | --- | --- |
| Đọc nhỏ theo PK | `orders_by_id` | Global cap và tenant cap |
| Đọc page có giới hạn | `orders_by_customer_day`, 25 row/page | Cap theo page fetch, page-size max |
| Batch import/write | Nhiều sự kiện theo khóa | Producer demand/queue bounded, cap riêng |
| Repair/maintenance | Tác vụ node/operator | Không đi qua Java driver limiter, nhưng cạnh tranh cùng server budget |
| Analytics/quét rộng | Nhiều partition/token ranges | Bulkhead riêng, concurrency thấp hơn |
| LWT/counter write | Mutation nhạy idempotency | Cap và retry policy chuyên biệt |

Một cap đồng nhất cho mọi truy vấn có thể bị “một số query cực nặng” chiếm sạch. Hệ lớn có thể dùng **weighted permits** hoặc nhiều bulkheads theo lớp chi phí.

## 25. Bulkhead: không để một luồng nghiệp vụ chiếm hết capacity

*Bulkhead* mượn khái niệm vách ngăn tàu: nếu một khoang gặp vấn đề, không làm toàn bộ hệ bị ngập.

Ví dụ service có:

- API đọc trạng thái đơn hàng.
- Batch đồng bộ báo cáo.
- API cập nhật đơn.
- Reconciliation background job.

Nếu mọi thứ dùng chung cap 100 mà batch có thể chiếm đủ 100 slots, user-facing reads sẽ bị từ chối.

### Phân ngân sách minh họa

```text
Global Cassandra in-flight cap per instance: 100

Interactive reads:          tối đa 50
Business writes:            tối đa 30
Batch/reconciliation:       tối đa 20

Mỗi nhóm có cap riêng; tổng được kiểm soát
ở một tầng admission chung khi cần.
```

**Không đơn giản tạo ba semaphore không liên quan** rồi giả định tổng luôn bằng 100 nếu chúng còn được dùng ở nơi khác. Cần thiết kế thứ tự lấy permits và release nhất quán (chẳng hạn lấy global trước, rồi category, hoặc một admission controller phân phối quota).

Những số 50/30/20 là minh họa; phải đo QPS, deadline và chi phí query trước khi phân ngân sách thật.

### Ưu tiên không đồng nghĩa bỏ đói

Một service ưu tiên read người dùng tuyệt đối có thể khiến write hoặc reconciliation không bao giờ được thực hiện. Đặt **tối thiểu và tối đa** theo SLO, deadline và nhu cầu vận hành; không làm mất sự kiện bắt buộc chỉ vì ưu tiên UI.

## 26. Multi-tenant: cap theo tenant và toàn service

Giả sử một tenant khởi chạy 50 job, mỗi job đọc hàng nghìn partition. Nếu chỉ có global cap, tenant đó có thể dùng hết capacity của các tenant khác.

Mô hình hai lớp:

```text
Request của tenant A
        |
        v
  Global capacity?
        |
        v
  Tenant A capacity?
        |
        v
   Cassandra query
        |
        v
 Release cả hai slots
```

Một thiết kế cần giải quyết:

- Giới hạn tổng toàn service instance.
- Giới hạn theo tenant/principal/job.
- Quota khác nhau giữa batch và interactive.
- Dọn state của tenant không hoạt động để tránh map of semaphores tăng vô hạn.
- Không tạo/giữ permit khi request validation/authentication đã thất bại.
- Nếu lấy global permit thành công nhưng tenant permit thất bại, **phải release global ngay**.
- Tránh leak hoặc double-release khi gặp cancellation/error/race.

### Không tin tenant ID do client tự gửi

Nếu API chấp nhận một tham số `tenantId` không được xác thực, người dùng có thể chuyển qua tenant khác để né rate limit. Tenant scope phải lấy từ authenticated principal hoặc được kiểm chứng bằng authorization.

**Tenant limiter là ranh giới tài nguyên, không phải cơ chế cấp quyền đọc dữ liệu.** Cả quota và CQL WHERE theo tenant vẫn cần thiết.

## 27. Nhiều instance: cap trên JVM không phải cap toàn cluster

Ví dụ:

```text
10 application instances
mỗi instance có 80 in-flight slots

Tổng logical in-flight tối đa lý thuyết:
10 x 80 = 800 requests
```

Nếu autoscaling tăng lên 30 instances mà vẫn giữ 80:

```text
30 x 80 = 2.400 logical in-flight requests
```

Cassandra cluster không tự tăng capacity theo số pod Java. Do đó deployment phải xem **max replicas của application**, QPS, retry/speculative rate và năng lực Cassandra.

### Các phương án quản lý

1. **Per-instance cap được tính theo max app replicas**, giữ headroom cho tăng quy mô.
2. **Gateway rate limit/concurrency** để kiểm soát tổng đầu vào, cộng với per-instance cap.
3. **Distributed quota coordinator** nếu thật sự cần global cap nghiêm ngặt, chấp nhận overhead và failure modes của quota store.
4. **Autoscaling theo backlog và downstream headroom**, không chỉ CPU của app.
5. **Per-tenant quotas** dùng cùng định danh trên mọi instance hoặc một dịch vụ quota tập trung.

Không dùng một semaphore Java rồi công bố “Cassandra tối đa 80 requests toàn hệ”.

### Distributed semaphore cũng có failure modes

Một store giữ lease permit có thể mất kết nối hoặc client crash; cần TTL/lease và tránh double grant. Việc lock/lease hết hạn **không chắc** đã dừng Cassandra request đang thực thi.

Nếu yêu cầu là bảo vệ server khỏi tải, đôi khi **local fail-fast cap + global rate limit + monitoring** an toàn, đơn giản và ít phụ thuộc hơn một distributed semaphore có semantics phức tạp.

## 28. Retry phía HTTP, Kafka và batch jobs

Backpressure phải được nhìn xuyên từ nguồn sự kiện:

### HTTP API

- Khi quá tải, trả 429/503 theo hợp đồng.
- Caller áp backoff/jitter và deadline.
- Không để gateway retry `POST` không idempotent vô hạn.
- Có circuit breaker/bulkhead để bảo vệ các tầng downstream.

### Kafka/queue consumer

- Điều chỉnh số record poll và concurrency của handler.
- Pause/giảm demand khi DB limit đầy; resume khi có khả năng xử lý.
- Chỉ acknowledge/commit offset sau khi nghiệp vụ cần thiết hoàn tất theo thiết kế.
- Không drop mutation quan trọng vì overflow mà không có cơ chế bù/durable retry.
- Cẩn trọng rebalancing/duplicate consumption; idempotency key và event ID vẫn cần.

### Scheduled batch

- Chia dữ liệu thành pages/chunks có kích thước hữu hạn.
- Giữ tối đa K tasks active, không dựng một triệu futures.
- Có checkpoint để tiếp tục sau restart.
- Có deadline và “stop on overload” thay vì tăng concurrency.
- Theo dõi progress và giới hạn tốc độ để không ảnh hưởng SLO online.

**Nếu upstream có hỗ trợ demand/pause thực, hãy sử dụng nó.** Chỉ chuyển sự tích tụ sang queue vô hạn trong app không phải backpressure.

## 29. Graceful shutdown và draining

Khi ứng dụng được yêu cầu dừng (deployment/restart):

1. Ngừng nhận work mới vào admission gate.
2. Trả kết quả/chặn request đến mới theo gateway lifecycle.
3. Đợi in-flight hợp lệ hoàn tất **trong shutdown deadline**.
4. Xử lý hoặc lưu lại những batch chưa ack theo hợp đồng.
5. Close `CqlSession` sau khi work đã drain đến ngưỡng cho phép.
6. Ghi số operations còn dở và retry/recovery policy.

Nếu đóng session ngay khi còn nhiều futures, application có thể mất khả năng nhận kết quả; mutation ở Cassandra vẫn có thể đã thực thi. Với write cần xử lý **outcome unknown**, không giả định tất cả bị hủy.

### Số in-flight phải về 0 theo cách nào?

Với limiter không queue, sau khi chặn admissions mới, số active sẽ giảm khi các stages hoàn tất hoặc timeout. Nếu không giảm, cần xem:

- Có operation không hoàn thành stage không?
- Có I/O/callback block event loop?
- Driver request timeout có cấu hình và hoạt động không?
- Có future bị giữ sau HTTP cancellation không?
- Có leak/double-release ở code wrapper không?

**Không tự cộng permit để gauge về 0** nếu các Cassandra requests vẫn đang chạy; làm vậy khiến metrics đẹp nhưng admission không còn đúng.

## 30. Metrics tối thiểu cho admission control

| Metric | Ý nghĩa | Tín hiệu nguy hiểm |
| --- | --- | --- |
| `in_flight` hiện tại | Số logical requests đang dùng slot | Bám max lâu dài |
| `in_flight_max` | Cấu hình cap | Không tương xứng số app instances |
| `admitted_total` | Số requests được nhận | QPS cao liên tục so capacity |
| `rejected_total{reason}` | Số requests bị từ chối | Tăng đột biến hoặc kéo dài |
| `queue_depth` nếu có | Số requests chờ | Chạm giới hạn |
| `queue_wait_ms` | Thời gian chờ trước DB | P95 gần deadline |
| `db_execution_ms` | Thời gian stage DB/mapping | P99 tăng trước rejection |
| `request_end_to_end_ms` | Từ ingress đến response | SLO vượt dù DB p99 có vẻ thấp |
| `driver_in_flight` nếu có | Số request driver đang quản lý | Khác đáng kể với app logical count |
| `retry/speculative_count` | Request amplification | Tăng khi cluster chậm |
| `coordinator/DC` | Nơi request được điều phối | Lệch DC, hotspot |
| `tpstats pending/dropped` | Queue/stage phía server | Tăng khi saturation |
| CPU/GC/disk await/network | Ngân sách thực của node | Gần giới hạn trước khi full outage |
| Compaction/repair/streaming | Work nền tranh tài nguyên | Trùng thời điểm p99 xấu |

Không dùng `tenant_id` hàng triệu giá trị làm metric label; có thể tính quota theo tenant trong store nhưng dashboard nên tập trung nhóm top tenants/capacity tiers và kiểm soát cardinality.

### Alert không chỉ dựa vào rejection

Nếu service chưa từ chối request nhưng p99 đang tăng và driver in-flight tăng liên tục, đó là tín hiệu **sắp quá tải**.

Một hệ giữ cap đúng có thể có rejection tăng khi burst; đây đôi khi là **hành vi bảo vệ dự kiến**, cần xem cùng SLO và demand. Alert cần phân biệt:

- Burst ngắn được kiểm soát.
- Rejection kéo dài vì capacity thiếu.
- DB đang chậm bất thường khiến permit giữ quá lâu.
- App scaling làm tải thực vào cluster tăng.
- Một tenant hoặc query shape chiếm hết slots.

## 31. Ví dụ tính ngân sách cho nhiều ứng dụng

Giả sử toàn cluster lab đã kiểm thử chịu được **2.000 logical reads/s** của query nhỏ với resource headroom yêu cầu. Có bốn service instances, workload trộn reads và writes.

Một phép tính minh họa:

```text
Observed healthy mean latency:   40 ms
Observed logical arrival rate:   1.500 req/s

Little's Law:
  Average in-flight ~ 1500 x 0,040 = 60

Ứng dụng có 4 instances:
  trung bình ~ 15 in-flight mỗi instance nếu chia đều

Thử cap ban đầu:
  40 per instance = 160 logical in-flight toàn hệ
```

**Cap 40 không suy trực tiếp từ công thức**. Nó là giá trị canary cần kiểm thử với burst, p99, SLO, số instance tối đa và retry amplification. Khi 4 instances tăng thành 12, 40 mỗi instance thành **480 logical in-flight**; cần tính lại.

### Nên giữ bao nhiêu headroom?

Không có tỷ lệ phổ quát. Với Cassandra có compaction/repair, node failure hoặc traffic peak, headroom cần đủ cho các tình huống xấu. Đặt mục tiêu qua load test:

- CPU/heap/GC ổn trong burst.
- Disk I/O latency không tăng không kiểm soát.
- CQL p99 và error rate đạt SLO.
- Không có retry storm.
- Một node/rack bị gián đoạn trong phạm vi RF/CL cho phép vẫn chịu được tải cần thiết.
- Background repair/streaming không làm latency vượt budget.

Một ngưỡng số lượng requests được chọn bằng cách “CPU chưa cao trong 1 phút test” không đủ.

## 32. Load test: tìm vùng ổn định chứ không chỉ điểm cực đại

### Thử nghiệm A — Tăng QPS theo bước

1. Khởi động với mức thấp, cache warm-up.
2. Tăng arrival rate từng mức với **cùng query shape**, RF/CL và tỷ lệ key nóng.
3. Ghi in-flight, rejection, queue wait, p50/p95/p99, retries.
4. Theo dõi CPU/GC, disk/network, `tpstats`, compaction.
5. Tìm mức mà latency tăng nhanh nhưng throughput không còn tăng tương xứng.
6. Chọn cap thấp hơn vùng nguy hiểm, có headroom cho burst/failure.

### Thử nghiệm B — Burst

```text
Bình thường: 300 req/s
Burst 5 giây: 1.800 req/s
Sau burst: 300 req/s
```

Đánh giá:

- Có giới hạn requests thực sự khởi phát không?
- Rejections/queue depth có ở trong chính sách không?
- Hết burst, latency và in-flight có **phục hồi** không?
- Có spike retry từ upstream sau khi bị reject không?
- Heap có tăng do tích tụ futures không?

### Thử nghiệm C — Node chậm

Trong **staging/lab**, gây một replica/coordinator chậm có kiểm soát. Xem:

- Thời gian giữ permit tăng thế nào?
- Admission có ngăn thêm requests trước driver không?
- Timeout/retry/speculation có vượt resource budget không?
- API có degrade an toàn hay tạo retry storm?
- Khi node khỏe lại, queue/backlog có xả gây quá tải lần hai không?

### Thử nghiệm D — Tenant ồn ào

Cho tenant A tải lớn và tenant B tải nhỏ. Kiểm tra B vẫn đạt tối thiểu SLO theo chính sách fairness; không để tenant A chiếm toàn bộ permit/queue.

**Chỉ làm fault injection trên môi trường được cho phép.** Không gây áp lực chủ động lên Cassandra production ngoài kế hoạch.

## 33. Vì sao công cụ benchmark có thể làm kết luận sai?

Một load generator cũng phải có mô hình arrival rate rõ:

- **Closed-loop:** client gửi request mới khi request cũ xong. Khi server chậm, arrival rate tự giảm, có thể che saturation.
- **Open-loop:** client giữ arrival schedule độc lập với latency, mô phỏng burst dễ làm queue phình.
- **Coordinated omission:** nếu tool chỉ đo những request đã được gửi hoặc đã thành công, có thể bỏ qua thời gian chờ/rejected requests và đánh giá p99 quá đẹp.

Báo cáo cần ghi:

- Offered QPS và **admitted/completed/rejected QPS**.
- Queue wait và end-to-end latency, không chỉ DB execution.
- Các request bị timeout/cancel.
- Số extra attempts do retry/speculation.
- Kích thước row/partition và phân bố key.
- Số app instances và driver pools.
- RF/CL, local DC, compaction/repair state.

**Không so throughput chỉ trên tập requests thành công mà bỏ qua 30% request bị từ chối.**

## 34. Sự cố A — Gửi một triệu `executeAsync` rồi OOM

**Triệu chứng:** heap tăng, futures/callback chiếm RAM, latency toàn bộ requests tăng, cuối cùng ứng dụng OOM.

**Nguyên nhân:** producer tạo requests nhanh hơn downstream hoàn tất, không có admission/queue bound.

**Hướng xử lý:**

1. Ngừng/bớt producer, bảo vệ service trước burst.
2. Chuyển sang demand-driven stream hoặc sliding window K.
3. Đặt global limiter trước `executeAsync`.
4. Đặt cap queue và deadline nếu cần chờ.
5. Đo heap, in-flight, driver queues và server load.
6. Sau khi ổn định mới tăng K từng bước theo canary.

Không giải quyết gốc bằng việc tăng heap 4 lần mà vẫn để vòng lặp gửi một triệu requests.

## 35. Sự cố B — Dùng `Semaphore.acquire()` trong WebFlux

**Triệu chứng:** CPU app có thể chưa cao nhưng request handlers bị đứng, Reactor event loop threads blocked, p99 tăng với cả endpoint không dùng Cassandra.

**Nguyên nhân:** blocking wait trên event loop.

**Hướng xử lý:** dùng `tryAcquire()` + fail fast hoặc async waiters với queue hữu hạn. Nếu bắt buộc chạy code blocking khác, isolate trong scheduler/executor phù hợp nhưng **vẫn giới hạn queue/concurrency**.

Không chuyển cả service sang một thread pool vô hạn.

## 36. Sự cố C — Limit mỗi request là 16 nhưng DB vẫn quá tải

**Triệu chứng:** mỗi `flatMap` đã `concurrency=16`, song Cassandra nhận hàng nghìn requests.

**Nguyên nhân:** có hàng trăm HTTP requests/streams chạy đồng thời. Concurrency 16 là **mỗi stream**, không phải **toàn JVM**.

**Hướng xử lý:** thêm global admission cap ở repository/gateway, tính theo max app instances, kiểm soát rate/tenant, và đặt query-class bulkheads.

## 37. Sự cố D — Rejection tăng trong lúc compaction

**Triệu chứng:** service giữ cap cố định nhưng nhiều requests trả `BusyException`, cùng lúc disk await và compaction backlog tăng.

**Nguyên nhân:** Cassandra xử lý chậm hơn nên mỗi request giữ permit lâu; arrival rate cao hơn throughput ổn định.

**Hướng xử lý:**

- Không tự tăng cap ngay.
- Xem compaction schedule, disk headroom, tombstones và query shapes.
- Điều tiết batch/analytics, ưu tiên query critical.
- Giảm upstream rate/burst và dùng retry backoff/jitter.
- Quan sát khi compaction giảm, permit và p99 có phục hồi không.

Nếu cap đang bảo vệ Cassandra thành công, rejection là tín hiệu **cần giảm tải hoặc tăng capacity đúng cách**, không nhất thiết là bug limiter.

## 38. Sự cố E — Cancellation làm “lọt” thêm tải

**Triệu chứng:** người dùng đóng trình duyệt, app release permit ngay, nhưng server vẫn tiếp tục xử lý query. New requests được admitted, gây physical concurrency vượt dự kiến.

**Nguyên nhân:** nhầm **HTTP cancellation** với **Cassandra RPC đã ngừng**.

**Hướng xử lý:** đo completion stage của driver, gắn permit tới thời điểm scope công việc thật hoàn tất; cấu hình timeout và cancellation theo driver version; đặt thêm server-side headroom, không dựa vào cancellation như một phương pháp thu hồi tài nguyên chắc chắn.

Với mutation, cancellation **không phải rollback**.

## 39. Sự cố F — Retry storm sau `503`

**Triệu chứng:** gateway trả `503` cho tải dư, client retry cùng một thời điểm, làm số request tăng theo đợt.

**Nguyên nhân:** nhiều tầng retry không có shared budget, backoff/jitter hoặc max attempts.

**Hướng xử lý:** rate limiting, exponential backoff với jitter, Retry-After có chính sách, giảm số layers retry và đặt end-to-end deadline. Không retry writes không idempotent một cách mù quáng.

## 40. Sự cố G — Một tenant làm người khác timeout

**Triệu chứng:** batch của tenant A giữ gần như toàn bộ global permits; tenant B dù ít QPS vẫn bị reject.

**Nguyên nhân:** không có per-tenant/per-class bulkhead hoặc scheduling fairness.

**Hướng xử lý:** quotas theo tenant, global cap, priority có minimum capacity, TTL cleanup của quota state và monitoring theo nhóm tenant. Không giảm RBAC hoặc dùng tenant ID từ client để phân chia quota.

## 41. Sai lầm thường gặp

**“Async tự động backpressure.”** Sai. `executeAsync` không ngăn producer gửi vô hạn futures.

**“Có 8 Netty threads tức là chỉ có 8 Cassandra requests đồng thời.”** Sai. Một event loop có thể quản lý nhiều requests.

**“Giới hạn `flatMap(16)` là giới hạn toàn hệ.”** Sai. Nó chủ yếu áp dụng trong phạm vi stream cụ thể.

**“`CompletableFuture.allOf` làm các requests chạy theo batch.”** Sai. Nó chỉ đợi các futures đã được khởi phát.

**“`Semaphore.acquire()` không vấn đề gì vì DB async.”** Sai nếu thread gọi là event loop.

**“Đã dùng queue thì an toàn dù queue vô hạn.”** Sai. Queue vô hạn vẫn tích tụ bộ nhớ và độ trễ.

**“Thả permit ngay sau `executeAsync` vẫn giới hạn concurrency.”** Sai. Driver mới chỉ trả future.

**“Timeout client đã cancel hết server work.”** Không được giả định.

**“Bảo vệ 100 logical requests nghĩa là tối đa 100 replica RPC.”** Sai. Coordinator có thể liên hệ nhiều replica và driver có retry/speculation.

**“Đặt QPS cap là không cần in-flight cap.”** Sai. Latency tăng có thể khiến concurrency tăng khi QPS không đổi.

**“Tăng in-flight đến khi CPU đạt 100% là tối ưu.”** Sai. Cassandra còn disk/network/GC, tail latency và khả năng chịu lỗi.

**“`LOCAL_ONE` luôn tốt vì giảm áp lực.”** Không phải lựa chọn chỉ về hiệu năng; đổi CL thay đổi consistency semantics.

**“Chạy theo partition key nào cũng nhẹ.”** Sai. Hot partition, large collection và nhiều tombstone có thể tốn tài nguyên.

**“Chỉ đọc 10 row nên không cần page limit.”** Sai nếu query/driver auto-fetch nhiều trang, hoặc server phải scan tombstone/SSTable để tìm row sống.

**“Ứng dụng autoscale gấp đôi là Cassandra cũng tăng capacity.”** Sai. Tổng in-flight từ nhiều instances tăng.

**“Mọi tenant dùng chung quota global là công bằng.”** Không đúng nếu một tenant có thể chiếm hết slots.

**“Reject là lỗi cần che bằng retry vô hạn.”** Sai. Reject là tín hiệu tải cần được phản hồi có kiểm soát.

**“Hạ CL hoặc bật speculation sẽ khắc phục queue overload.”** Không có bảo đảm và có thể làm correctness/tải tệ hơn.

**“Dùng Reactor là không thể có blocking code.”** Sai. Callback có thể gọi `block()`, `Thread.sleep` hoặc `Semaphore.acquire`.

**“Đặt timeout 30 giây sẽ tránh request thất bại.”** Sai. Nó có thể làm permit bị giữ lâu và queue tăng.

**“Backpressure cho phép drop mọi event.”** Sai đối với mutation, thanh toán, audit hoặc workflow bắt buộc.

**“Đã có limiter thì không cần quan sát server.”** Sai. Driver và replica có những công việc/chi phí riêng.

## 42. Ma trận kiểm thử trước khi rollout

| Case | Đầu vào/điều kiện | Kỳ vọng |
| --- | --- | --- |
| T1 | Max=2, có 2 stages chưa hoàn tất | Request thứ 3 bị từ chối trước executeAsync |
| T2 | Một stage hoàn tất thành công | Đúng một permit được trả |
| T3 | Một stage hoàn tất exceptionally | Permit vẫn được trả |
| T4 | Supplier ném exception đồng bộ | Không leak permit |
| T5 | Supplier trả null stage | Không leak permit, báo lỗi rõ |
| T6 | 1000 requests cùng tranh max=20 | Không quá 20 admitted in-flight ở instance |
| T7 | Request malformed | Validation fail trước admission |
| T8 | Unauthorized tenant | Không gửi query, không tiêu thụ DB slot |
| T9 | Reactor stream có concurrency 16 | Không quá 16 inner subscriptions của stream |
| T10 | 100 Reactor streams chạy cùng lúc | Global limiter vẫn giữ cap |
| T11 | Page fetch nhiều trang | Không `all()` vô hạn, mỗi page qua gate phù hợp |
| T12 | Application callback CPU nặng | Không block driver I/O event loop |
| T13 | Client HTTP cancel | Permit/lifecycle đúng khi DB stage chưa hoàn tất |
| T14 | Driver timeout | Stage hoàn tất lỗi, permit được trả |
| T15 | Queue 40 đã đầy | Request mới bị từ chối, không phình queue |
| T16 | Queue wait quá 50 ms | Request bị expiry trước DB |
| T17 | Tenant A cao tải, tenant B thấp | Tenant B có quota/fairness như thiết kế |
| T18 | 10 app instances | Tổng cap được tính theo deployment |
| T19 | Autoscale lên 30 instances | Không làm vượt ngân sách Cassandra bất ngờ |
| T20 | Retry/speculation bật | Physical attempts được đo riêng logical cap |
| T21 | Một replica chậm | Admission không tạo feedback loop vô hạn |
| T22 | Compaction/repair nền | p99/error/rejection và disk headroom được giám sát |
| T23 | Node restart | Hệ degrade an toàn, retries không storm |
| T24 | Rate limit + concurrency limit | Hai chính sách cùng hoạt động, không xung đột |
| T25 | Graceful shutdown | Chặn admission mới, drain và close đúng thứ tự |
| T26 | Empty batch | Không tạo Cassandra requests |
| T27 | Batch một triệu IDs | Không tạo một triệu futures cùng lúc |
| T28 | Dữ liệu hot partition | Budget riêng hoặc reject theo cost khi cần |
| T29 | HTTP client retry `503` | Backoff/jitter, deadline và max attempts |
| T30 | Thử maxInFlight=20/40/80 | Chọn dựa trên SLO và tài nguyên, không chỉ throughput |

### Kiểm tra concurrency thật bằng test double

Đối với `AsyncInFlightLimiter`, có thể tạo các `CompletableFuture` **chưa complete** để chiếm slots:

```java
import java.util.concurrent.CompletableFuture;

// Minh họa test setup, ví dụ có limiter maxInFlight=2.
AsyncInFlightLimiter limiter =
    new AsyncInFlightLimiter(2);

CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();

var acceptedA = limiter.submit(() -> a);
var acceptedB = limiter.submit(() -> b);

// Request thứ ba thất bại nhanh vì không còn slot.
var rejected = limiter.submit(
    () -> CompletableFuture.completedFuture("never started")
);

// Kiểm tra getInFlight()==2 ở đây.
// Sau a.complete("ok"), một slot được giải phóng.
a.complete("ok");
```

Đây là code **minh họa một phần test**, không phải lớp JUnit hoàn chỉnh. Trong test thật, dùng assertions phù hợp, kiểm tra rejected future và đảm bảo supplier của request thứ ba **không hề chạy**.

## 43. Runbook triển khai theo từng giai đoạn

### Giai đoạn A — Chuẩn bị

1. Kiểm kê query shapes: SELECT theo PK, page reads, writes, LWT, batch, analytics.
2. Xác định Cassandra release, Java Driver 4.x version, RF/DC, CL và connection settings.
3. Đo baseline QPS, in-flight, p95/p99, timeout, retry/speculative rate.
4. Đo resource headroom của nodes: CPU, GC, disk I/O, network và compaction.
5. Ước tính concurrency bằng Little's Law và xác minh burst/peak load.
6. Chọn giới hạn theo instance, query class và tenant; tính **max app replicas**.
7. Quyết định fail fast hay bounded queue, deadline và HTTP/Kafka signaling.
8. Bảo đảm mọi `executeAsync` của đường liên quan nằm sau admission gate.
9. Viết unit/integration tests cho release permit trên success/error/cancel.
10. Chuẩn bị feature flag và rollback về cấu hình cũ an toàn.

### Giai đoạn B — Canary

11. Bật limiter trên một phần traffic/instances.
12. Xem admitted/rejected, in-flight, queue wait và end-to-end p99.
13. So driver requests, retries/speculation với logical operations.
14. Kiểm tra Cassandra `tpstats`, CPU/GC, disk await, SSTables/compaction.
15. Test burst, node slowness và tenant noisy behavior trong phạm vi được phép.
16. Quan sát upstream retry để tránh phản ứng hàng loạt sau `429/503`.
17. Không tăng cap nếu server p99/queue/disk đang xấu.
18. Đo qua nhiều chu kỳ có peak load và background jobs.

### Giai đoạn C — Vận hành

19. Theo dõi cap khi số replicas của service thay đổi.
20. Tái đánh giá khi đổi RF/CL, local DC, schema, page size hoặc driver policy.
21. Xây capacity planning riêng cho foreground/batch jobs.
22. Thực hiện graceful drain khi rolling deployment.
23. Báo cáo cả thành công, từ chối, timeout và queue wait.
24. Hạn chế log bind values, token, customer IDs hoặc PII trong metrics.
25. Đặt owner cho quota tuning và runbook overload.
26. Diễn tập rollback và khôi phục khi Cassandra đang compaction/repair nặng.

## 44. Câu hỏi và bài tập

1. Vì sao `executeAsync()` không bảo đảm chỉ có số lượng requests an toàn?
2. Phân biệt QPS, in-flight, queue depth và connection pool capacity.
3. Với 500 req/s và latency trung bình 100 ms, Little's Law dự đoán in-flight trung bình bao nhiêu?
4. Vì sao p99 tăng có thể kéo concurrency tăng khi QPS giữ nguyên?
5. Tại sao admission phải diễn ra **trước** `session.executeAsync`?
6. Phân biệt fail fast, bounded queue và unbounded async waiters.
7. Vì sao `Semaphore.acquire()` không phù hợp trên Netty/Reactor event loop?
8. `Semaphore.tryAcquire()` giúp gì và không giải quyết điều gì?
9. Vì sao phải release permit khi `CompletionStage` hoàn tất lỗi?
10. Nếu supplier ném exception đồng bộ trước khi trả future, cần làm gì?
11. Vì sao `finally {release();}` ngay sau `executeAsync` là sai?
12. `CompletableFuture.allOf` có giới hạn số requests đã được gửi không?
13. So sánh fixed batching và sliding-window concurrency.
14. `flatMap(mapper, 16)` kiểm soát phạm vi nào?
15. Nếu có 200 HTTP requests, mỗi stream cho 16 reads, tổng tải lý thuyết ra sao?
16. Vì sao cần global limiter dù đã có Reactor `flatMap`?
17. Backpressure `request(n)` có thu hồi Cassandra request đã gửi không?
18. Vì sao `onBackpressureDrop` nguy hiểm với event thanh toán?
19. Khi nào `flatMapSequential` phù hợp và chi phí buffer ở đâu?
20. Một paged SELECT có 10 trang; nên giới hạn theo page hay cả workflow?
21. Tại sao không giữ DB permit khi user chờ 5 phút để mở trang kế?
22. `timeout` của reactive chain có bảo đảm server đã ngừng mutation không?
23. Trong WebFlux, vì sao mapping CPU nặng trên callback cần executor/bulkhead riêng?
24. Rate limiting và in-flight limiting giải những vấn đề khác nhau thế nào?
25. Nếu limiter cap 80 trên 20 pods, tổng logical requests tối đa giả định là bao nhiêu?
26. Vì sao autoscaling Java không đồng nghĩa Cassandra có thêm capacity?
27. Thiết kế quota global + per-tenant mà không leak permits.
28. Vì sao service-account có SELECT không đủ để kiểm soát tenant data access?
29. Một logical request có retry và speculative attempt. Số replica RPC có chắc bằng 1 không?
30. Vì sao không tăng maxInFlight ngay khi p99/queue tăng?
31. RF=3 và `LOCAL_QUORUM` có thể ảnh hưởng thời gian giữ permit thế nào?
32. Vì sao đổi CL sang ONE là thay đổi correctness contract?
33. Vì sao một query theo PK vẫn có thể nặng nếu partition quá lớn?
34. Một batch triệu row nên dùng cơ chế demand/checkpoint thế nào?
35. Khi upstream Kafka không được phép mất event, nên làm gì thay vì drop?
36. Trong load test, vì sao phải báo rejected QPS cùng completed QPS?
37. Coordinated omission làm số đo latency bị lệch thế nào?
38. Vì sao cần test với compaction/repair cùng chạy?
39. Khi client cancel HTTP, phải quản lý permit và driver stage ra sao?
40. Thiết kế dashboard gồm in-flight, rejection, queue wait, driver attempts và server resource.
41. Phân tích nguyên nhân “limiter đúng 100 nhưng Cassandra vẫn nhận hơn 100 coordinator attempts”.
42. Với p99 giảm nhưng write timeout tăng, có nên tiếp tục tăng concurrency không?
43. Một tenant chiếm 90% slots thì nên áp bulkhead/quota ra sao?
44. Hãy mô tả flow graceful shutdown không làm mất kết quả mutation đã hoàn tất.
45. Viết một test double với CompletableFuture chưa hoàn thành để chứng minh cap không bị vượt.

## 45. Sơ đồ quyết định cuối bài

```text
        CÓ REQUEST CẦN GỌI CASSANDRA
                       |
                       v
             Input/auth/tenant hợp lệ?
                 |              |
                Không           Có
                 |              |
               Reject           v
                         Deadline còn đủ?
                            |       |
                           Không    Có
                            |       |
                          Timeout   v
                               Có slot global/
                               tenant/class?
                                  |      |
                                 Không   Có
                                  |      |
                         Bounded queue?  v
                           |      |   executeAsync()
                           |      |       |
                           |      |       v
                      Không      Có   CompletionStage
                           |      |       |
                          429/503  Wait   v
                                  bounded Success/Error
                                  deadline    |
                                              v
                                       Release permit
                                              |
                                              v
                                      Response / metrics
```

**Ghi nhớ:** **Java Driver bất đồng bộ giúp không chặn thread khi chờ Cassandra, nhưng không tự ngăn ứng dụng gửi vô hạn công việc.** Phải dùng **admission control trước `executeAsync`**, giới hạn số logical requests *in-flight*, queue và thời gian chờ; release permit khi asynchronous work thật sự hoàn tất. Với Reactor, `flatMap(..., concurrency)` giới hạn một stream, còn toàn service và nhiều instance cần ngân sách riêng. Hãy tính gần đúng bằng **Little's Law**, rồi quyết định cap bằng **load test, p95/p99, rejection, retries/speculation và CPU/GC/disk của replica**. Bảo vệ đúng nghĩa là **giữ hệ thống còn phục vụ được khi quá tải**, không phải cố đưa mọi request vào Cassandra bằng mọi giá.
