# Đo độ trễ Key-Value, truy vấn, lỗi và số thao tác đang chờ

## 1. Vì sao ứng dụng đã có health check vẫn cần đo latency, lỗi và hàng đợi?

Dịch vụ Spring Boot có `/actuator/health` trả `UP`, Couchbase SDK kết nối được và `findById` thành công. Nhưng người dùng báo màn hình lịch sử đơn hàng mất nhiều giây; ở giờ cao điểm một số request timeout, trong khi CPU của ứng dụng không quá cao. Chỉ nhìn trạng thái health không đủ để biết hệ thống đang gặp **nút thắt nào**.

Để vận hành đúng tầng truy cập **SPRING_DATA_COUCHBASE**, cần phân biệt bốn tín hiệu:

1. **Độ trễ (latency):** một thao tác Key–Value (KV), SQL++ hoặc request HTTP mất bao lâu?
2. **Tỷ lệ lỗi (error rate):** bao nhiêu thao tác thất bại, thất bại vì nguyên nhân nào?
3. **Số thao tác đang thực thi (in-flight):** hiện có bao nhiêu yêu cầu đã bắt đầu nhưng chưa kết thúc?
4. **Số thao tác đang chờ (queued/pending):** có bao nhiêu yêu cầu đang đợi chỗ trong pool/semaphore, đợi SDK gửi đi, hoặc đợi Query/Index Service xử lý?

Bài học nằm trong chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**: tầng truy cập Spring Data với document mapping, Repository, `CouchbaseTemplate` và SQL++; có liên hệ tới bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch, lựa chọn API reactive, nhất quán và hiệu năng.

**Kết quả cần đạt:** Bạn sẽ biết thiết kế bộ đo không làm thay đổi business semantics, instrument code Java/Spring với Micrometer, sử dụng counter–gauge–histogram đúng loại, hiểu queueing và Little's Law trong giới hạn hợp lệ, dựng dashboard/SLO, phân tích p95/p99 và thực hiện benchmark có kiểm soát.

> Nguyên tắc: Một con số “Couchbase latency = 100 ms” chỉ có ý nghĩa khi chỉ ra **thao tác**, **ranh giới thời gian**, **nguồn đo**, **thời điểm** và **workload**.

## 2. Ví dụ xuyên suốt: Orders API

Ứng dụng Spring Data Couchbase sử dụng:

~~~text
Bucket       : shop
Scope        : sales
Collection   : orders
Document ID  : order::o-1001
~~~

Body minh họa:

~~~json
{
  "customerId": "c-1001",
  "status": "PAID",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 365000
}
~~~

Các đường đọc/ghi:

| Endpoint | Đường tầng dữ liệu | Đặc điểm chính |
| --- | --- | --- |
| `GET /orders/{id}` | Repository `findById` → KV get | Biết document ID, thường không cần GSI |
| `POST /orders` | `save` / SDK KV mutation | Cần biết ACK, durability và lỗi ambiguous |
| `GET /customers/{id}/orders` | Derived query/Template → SQL++ | Phụ thuộc Query Service, thường cả GSI |
| `GET /orders/search` | Search nếu ứng dụng có | API/index và latency riêng |
| `GET /orders/{id}` có cache | Có thể cache hit mà không gọi Couchbase | Phải đo hit/miss riêng |
| Transaction nhiều Order/Inventory | Nhiều KV/query/transaction steps | Không bằng thời gian một operation đơn lẻ |

Một metric duy nhất cho tất cả các đường trên có thể che mất việc KV rất nhanh nhưng SQL++ p99 quá chậm. Ít nhất nên gắn thẻ **service=kv/query** và **operation=get/insert/query** với số lượng giá trị thấp.

## 3. Bản đồ đo: từ browser tới Data, Query và Index Service

~~~mermaid
flowchart TD
    C["Client / browser"] --> H["HTTP Controller"]
    H --> G["App queue / concurrency gate"]
    G --> S["Service + Repository / Template"]
    S --> CACHE{"Cache hit?"}
    CACHE -->|Có| RESP["Response từ cache"]
    CACHE -->|Không| SDK["Java SDK: dispatch, retry, transport"]
    SDK --> KV[("Data Service: KV")]
    SDK --> Q[("Query Service: SQL++")]
    Q --> IDX[("Index Service: GSI")]
    Q --> KV
    KV --> SDK
    IDX --> Q
    Q --> SDK
    SDK --> RESP
    RESP --> H
    H --> C
~~~

**Các lớp có thể đo riêng:**

- HTTP end-to-end: từ khi server nhận request tới lúc trả response theo instrumentation.
- Service method: authorization, mapping, cache, SDK call, xử lý kết quả.
- SDK/client operation: thời gian SDK nhìn thấy, có thể gồm queueing, retries/network tùy meter/phiên bản.
- KV server-side: thời gian phục vụ thao tác KV theo metric Couchbase.
- SQL++: admission/queue, planning, index scan, fetch, sort/aggregate, response.
- Index Service: tốc độ update/scan, backlog, CPU/memory và các chờ liên quan.
- Cache/transport: cache hit/miss, pool/network/TLS và thời gian phản hồi.

**Không cộng bừa các số đo**: chúng có thể chồng lấn. Nếu HTTP timer đã bao gồm SDK timer thì cộng hai giá trị sẽ tính hai lần một phần thời gian.

## 4. Ranh giới đo latency: phải đặt điểm bắt đầu và điểm kết thúc

Xét một request đọc lịch sử Orders:

~~~text
t0  HTTP request đến server
t1  Service bắt đầu xử lý
t2  Bắt đầu chờ application concurrency permit
t3  Có permit, gọi Repository/SDK
t4  SDK gửi operation tới network
t5  Server tiếp nhận/xử lý và trả dữ liệu
t6  SDK đã nhận/parsing kết quả ở mức API
t7  Application mapping và chuẩn bị response xong
t8  HTTP response được ghi hoàn tất theo metric server
~~~

Một số thời gian:

\[
L_{\text{http}} = t_8-t_0
\]

\[
W_{\text{app-queue}} = t_3-t_2
\]

\[
L_{\text{app-db-call}}=t_6-t_3
\]

\[
L_{\text{app-postprocess}}=t_7-t_6
\]

**Quan trọng:** Thời điểm network send/receive và server execution thường không quan sát đầy đủ bằng một `System.nanoTime()` bọc Repository. Những mốc `t4`, `t5` cần SDK tracing/server metrics tương ứng. Một SQL++ operation có thể có streaming hoặc parsing deferred tùy API/phiên bản; phải xác định timer đã bao gồm **materialization/mapping** hay chưa.

### 4.1. Dùng monotonic clock cho duration

Trong Java, `System.nanoTime()` dùng để đo khoảng thời gian trong một process; không lấy chênh lệch `LocalDateTime.now()` vì đồng hồ wall-clock có thể bị điều chỉnh.

~~~java
long startNs = System.nanoTime();
try {
    return repository.findById(documentId).orElseThrow();
} finally {
    long elapsedNs = System.nanoTime() - startNs;
    // Ghi elapsedNs vào Timer/histogram, không log body.
}
~~~

Nếu muốn nối các event giữa nhiều pod, dùng timestamp UTC và trace ID; tính duration cục bộ bằng monotonic clock.

### 4.2. Không đo “lần đầu” chung với kết quả warm-up

Lần request đầu có thể gồm bootstrap, TLS, JVM JIT, connection warm-up hoặc prepared query plan. Hãy ghi và phân tích **cold-start latency** riêng so với **steady-state latency**, thay vì trộn mọi mẫu và suy nguyên nhân sai.

## 5. KV latency khác SQL++ latency

| Thuộc tính | KV get theo ID | SQL++ query theo field |
| --- | --- | --- |
| Đầu vào chính | Document key | Query text + parameters |
| Dịch vụ liên quan | Data/KV | Query; thường GSI Index và đôi khi Data fetch |
| Kích thước kết quả | Một document | Từ 0 tới nhiều rows |
| Nguồn biến thiên | Key partition, network, payload, contention | Plan/index, selectivity, scan/fetch, sort, consistency, row count |
| Rủi ro SLO | Timeout hoặc retry của KV | Queue, scan chậm, Index lag, result lớn |
| Cách kiểm chứng | SDK KV operation metrics | SDK Query + Query/Index metrics + `EXPLAIN` |

Một query SQL++ `SELECT RAW 1` có thể nhanh dù query theo `customerId` chậm. Nó kiểm tra Query Engine cơ bản, **không** đo Index Service path của nghiệp vụ.

### 5.1. Keyspace và query plan là một phần benchmark

Khi đo SQL++, ghi bucket/scope/collection, index, query shape và `EXPLAIN`. Nếu plan chuyển sang primary index/scan lớn, p99 thay đổi có thể do query plan thay vì chỉ do số client đang chờ.

### 5.2. Result size làm thay đổi latency

Query trả 10 rows và query trả 100.000 rows không nên gộp chung vào một histogram rồi kết luận “Query Service thất thường”. Cần pagination, projection, query shape tags và phân tách workload.

## 6. Tỷ lệ lỗi: không chỉ có timeout

Các nhóm kết quả hữu ích:

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Success** | KV get trả document, SQL++ hoàn thành | Operation được thực hiện thành công |
| **Not found / empty** | KV không có key; SQL++ 0 rows | Có thể là kết quả nghiệp vụ hợp lệ |
| **Validation/query error** | Query syntax/parameter sai | Lỗi code/schema, không hẳn outage |
| **Authentication/authorization** | Sai credential hoặc thiếu RBAC | Cần sửa cấu hình/quyền |
| **Timeout** | KV/SQL++ không hoàn tất trong deadline | Cần xem service, queue, retry, capacity |
| **Ambiguous mutation** | Write timeout, không biết mutation đã áp dụng chưa | Bảo vệ idempotency, xác minh source |
| **CAS conflict** | Hai update cạnh tranh | Tùy nghiệp vụ là conflict dự kiến hay lỗi |
| **Durability failure** | Không đạt mức durable acknowledgement | Không tự gộp vào latency/Index |
| **Service/network failure** | Endpoint unavailable/TLS | Phân tích đường kết nối và retry |
| **Cancellation** | Client hủy request/stream | Không tự coi là success hoặc server error |

### 6.1. Tỷ lệ lỗi phải có mẫu số rõ

Nếu trong cửa sổ có `N_total` operation đã hoàn thành theo định nghĩa, `N_failed` thất bại:

\[
\text{errorRate}=\frac{N_{\mathrm{failed}}}{N_{\mathrm{total}}}
\]

Nhưng phải thống nhất cách tính `not_found`, CAS conflict, cancellation và ambiguous write. Với `findById`, không tìm thấy key có thể trở thành HTTP 404 hợp lệ; với một API đòi key chắc chắn có, nó có thể là lỗi nghiệp vụ. Đừng gán mọi 404 vào “Couchbase outage”.

### 6.2. Chia nhỏ theo operation và outcome

Một đường KV get có thể đạt 99,99% success trong khi SQL++ query chỉ đạt 93%. Một global error rate trung bình có thể che điểm nóng. Dashboard nên có series theo **route template, operation, service, outcome** với cardinality được kiểm soát.

## 7. Timer, Counter, Gauge và histogram: chọn đúng dụng cụ

| Micrometer meter | Phản ánh | Không dùng để |
| --- | --- | --- |
| **Timer** | Số lần và phân phối duration | Đếm hiện tại đang chờ |
| **Counter** | Số sự kiện tăng dần | Mô tả instant queue depth |
| **Gauge** | Snapshot giá trị biến đổi, có thể tăng/giảm | Thay cho histogram latency |
| **Distribution summary** | Phân phối đại lượng không phải duration, ví dụ bytes | Đo số request in-flight trực tiếp |
| **Long task timer** | Duration/đếm tác vụ dài còn chạy theo API phù hợp | Thay tự động mọi metrics SDK |
| **Server/SDK metrics** | Đường service, retry, queue, backlog tùy version | Khẳng định chỉ số không được expose |

### 7.1. Counter là số tích lũy, không phải tốc độ

Counter `app.couchbase.operations.total` liên tục tăng. Để tính operations/sec trong dashboard, lấy **rate** trên một cửa sổ thời gian. Counter có thể reset khi pod restart, nên không dùng trực tiếp chênh lệch tổng qua reset mà không xử lý.

### 7.2. Histogram khác percentile đã tính sẵn

Histogram buckets cho phép tổng hợp qua nhiều instance trong giới hạn thiết kế. Percentile tính trực tiếp trên một JVM/series **không thể lấy trung bình** để có p95/p99 toàn hệ thống. Nếu dùng Prometheus, thường cần histogram buckets cùng `histogram_quantile` thay vì average các p95 của pod.

### 7.3. Gauge in-flight là ảnh chụp

Một Gauge `inflight=42` nói tại thời điểm scrape có 42 operation ở phạm vi instrument đó. Nó không cho biết bao nhiêu operation đang *đợi permit*, *đợi SDK dispatch* hay *đang chạy trên server* trừ khi đã được định nghĩa rõ.

## 8. Những gì Micrometer/Actuator có thể cung cấp

Một ứng dụng Spring Boot thường dùng Actuator và Micrometer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cấu hình ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: orders-api
~~~

Tên dependency/thuộc tính hợp lệ phụ thuộc Spring Boot/Micrometer version; thêm registry phù hợp hệ thống quan sát đang dùng. **Đừng công khai `/actuator/prometheus` cho Internet**; giới hạn truy cập từ monitoring network và RBAC/security policy.

### 8.1. Có phải tự động có đầy đủ metric Couchbase?

Không nên mặc định. Spring Boot, Couchbase Java SDK và Micrometer có các điểm tích hợp/auto-configuration phụ thuộc phiên bản. Trước khi xây dashboard:

1. Xem meter/trace nào thật sự tồn tại từ SDK.
2. Kiểm tra meter names, tags, units và version.
3. Tìm cách tích hợp SDK request metrics/tracing đúng API hiện tại nếu cần.
4. Bổ sung **application-level metrics** cho nghiệp vụ, không trùng tên/khái niệm với SDK metrics.
5. Đo overhead của histogram/tracing/sampling.

Không tự bịa tên metric SDK/Server rồi tạo alert dựa trên tên đó.

## 9. Cấu trúc tên metric và nhãn an toàn

Ví dụ **metric của chính ứng dụng**, không phải tên mặc định SDK:

~~~text
app.couchbase.operation.duration
app.couchbase.operation.result
app.couchbase.operations.inflight
app.couchbase.admission.waiting
app.couchbase.admission.rejected
~~~

Nhãn gợi ý có số lượng giá trị hữu hạn:

~~~text
service   = kv | query
operation = get | insert | replace | query
outcome   = success | error | cancelled
query     = orders_by_customer | order_summary
~~~

**Không đưa các giá trị sau vào metric labels:**

- `documentId`, `customerId`, UUID/order key cụ thể.
- Raw SQL++ statement hoặc query parameters.
- URL thật chứa email/user ID.
- Error message đầy đủ có cardinality cao.
- Host tạm thời liên tục sinh mới nếu không có nhu cầu và kiểm soát.

Nhãn `query` nên là **tên template cố định**, không phải query string. Vì số series bằng tổ hợp các nhãn, tăng cardinality có thể làm Prometheus/storage quá tải.

## 10. Ví dụ đo sync Repository và SDK bằng Micrometer

Tạo một wrapper dùng lại cho KV và Query. Ví dụ sau theo API Micrometer thông dụng; tùy framework version hãy xác minh imports và registry setup.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public final class CouchbaseOperationMetrics {
    private final MeterRegistry registry;
    private final AtomicInteger inFlight = new AtomicInteger();

    public CouchbaseOperationMetrics(MeterRegistry registry) {
        this.registry = registry;

        Gauge.builder(
                "app.couchbase.operations.inflight",
                inFlight,
                AtomicInteger::get)
            .description("Operations currently inside this wrapper")
            .register(registry);
    }

    public <T> T record(
            String service,
            String operation,
            Supplier<T> work) {

        // service/operation do code chọn từ tập nhãn cố định.
        String outcome = "success";
        Timer.Sample sample = Timer.start(registry);
        inFlight.incrementAndGet();

        try {
            return work.get();
        } catch (RuntimeException failure) {
            outcome = "error";
            throw failure;
        } finally {
            inFlight.decrementAndGet();

            Timer duration = Timer.builder(
                    "app.couchbase.operation.duration")
                .description("Application wrapper DB operation latency")
                .tags("service", service,
                      "operation", operation,
                      "outcome", outcome)
                .publishPercentileHistogram()
                .register(registry);

            sample.stop(duration);

            Counter.builder("app.couchbase.operation.result")
                .tags("service", service,
                      "operation", operation,
                      "outcome", outcome)
                .register(registry)
                .increment();
        }
    }
}
~~~

**Các lưu ý kỹ thuật:**

- `finally` ghi duration và giảm in-flight cả khi operation throw, tránh gauge bị kẹt.
- Meter chỉ có nhãn cố định; đừng truyền ID/user input vào `service`/`operation`.
- Wrapper **đo thời gian mà caller đồng bộ chờ `work.get()`**, không thay thế server-side latency.
- Gauge này đếm **số operation đang nằm trong wrapper**, bao gồm có thể có client-side wait, không phải “SDK request queue depth”.
- Histogram có overhead/bucket memory; cấu hình histogram/SLO buckets theo số series và monitoring backend.
- Ví dụ chỉ bắt `RuntimeException`; production cần policy nhất quán về Error/fatal exceptions và event-loop. Không xử lý `Error` như lỗi nghiệp vụ.
- Timer và Counter cùng theo outcome có thể trùng phần đếm; giữ cả hai nếu dashboard/alert cần, hoặc bỏ Counter riêng vì Timer đã có count.

### 10.1. Dùng wrapper cho Repository KV

~~~java
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final OrderRepository repository;
    private final CouchbaseOperationMetrics metrics;

    public OrderReadService(
            OrderRepository repository,
            CouchbaseOperationMetrics metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }

    public OrderDocument detail(String documentId) {
        return metrics.record("kv", "get", () ->
                repository.findById(documentId)
                        .orElseThrow(NoSuchElementException::new));
    }
}
~~~

Lỗi `NoSuchElementException` trong wrapper này được tính `error` theo ví dụ. Nếu business API xem 404 là outcome hợp lệ, hãy mở rộng classification thay vì gộp 404 với connection failures.

### 10.2. Dùng wrapper cho SQL++ query

~~~java
public List<OrderDocument> customerHistory(String customerId) {
    return metrics.record("query", "orders_by_customer", () ->
            repository.findByCustomerId(customerId));
}
~~~

Nếu Repository method trả `List` hoàn chỉnh, wrapper này gồm phần xử lý trong lời gọi method. Nếu API dùng streaming/reactive, timer phải bám vào terminal signal thay vì lúc tạo Publisher.

## 11. Tránh ghi nhãn lỗi tùy tiện khi timeout và CAS conflict

Trong code mẫu, mọi `RuntimeException` được gắn `outcome=error`. Đó là **điểm bắt đầu**, chưa đủ cho phân tích root cause.

Một policy phân loại thực tế có thể là:

~~~text
outcome:
  success
  not_found
  conflict
  timeout
  permission
  unavailable
  cancelled
  other_error
~~~

Cách phân loại:

1. Xem exception type/cause **thực** từ SDK/Spring Data và HTTP mapping.
2. Không lấy raw exception message thành tag.
3. Viết hàm map vào **tập enum/nhãn hữu hạn** và unit test.
4. Phân biệt timeout write outcome ambiguous với timeout đọc.
5. Lưu exception context/redacted trace riêng cho điều tra, không đưa vào metric label.
6. Giữ semantics nhất quán: 404 có tính là lỗi trong API SLO hay không phải do contract quyết định.

### 11.1. Timeout không có nghĩa dữ liệu đã mất

Một KV write có thể đã được server xử lý nhưng client không nhận ACK. Không vì thấy counter `timeout` mà tự động retry với ID mới. Cần idempotency key, CAS/conditional write và phương án xác minh mutation khi outcome chưa rõ.

## 12. In-flight và pending: hai đại lượng khác nhau

Một trong những lỗi dashboard phổ biến nhất là gắn nhãn `pending_requests` cho mọi operation chưa hoàn thành.

**Định nghĩa rõ các trạng thái:**

| Trạng thái | Có bao gồm khi đo in-flight app wrapper? | Có phải queue đang chờ? |
| --- | --- | --- |
| HTTP request vừa vào nhưng chưa tới DB | Không, nếu wrapper chỉ bọc DB call | Có thể nằm trong app admission queue |
| Thread đang đợi semaphore permit | Có thể, tùy đặt wrapper ở đâu | **Có**, nếu gauge đo đúng gate này |
| DB call đã được chấp nhận vào SDK, chưa hoàn tất | Có | Không nhất thiết đang queue |
| SDK đã gửi request và chờ server | Có | Không phải client admission queue |
| SQL++ query đang đợi index theo REQUEST_PLUS | Có trong E2E duration | Là server/index wait, không phải app queue |
| Response đã về, app đang serialize | Không, nếu wrapper kết thúc ở DB result | Không phải DB queue |

Vì vậy cần đặt tên:

- `app.couchbase.operations.inflight`: số thao tác đang ở trong wrapper.
- `app.couchbase.admission.waiting`: số thread/task đang chờ permit của **gate do ứng dụng quản lý**.
- `sdk.*.pending`: chỉ dùng nếu SDK phiên bản hiện tại thực sự expose metric với định nghĩa rõ.
- `query.server.queue`: metric phía Query Service nếu hệ thống cung cấp.
- `index.mutation.backlog`: cập nhật GSI chưa xử lý, **không phải** số query đang chờ.

Không quy đổi một metric thành metric khác chỉ vì chúng đều có ý nghĩa “chờ”.

## 13. Đo queue của chính ứng dụng bằng semaphore có giới hạn

Ví dụ đơn giản một admission gate đồng bộ để kiểm soát concurrency. Đây là cơ chế **ứng dụng tự xây**, không phải một queue SDK có sẵn.

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class BoundedDbAdmission {
    private final Semaphore slots = new Semaphore(32);
    private final AtomicInteger waiting = new AtomicInteger();
    private final MeterRegistry registry;

    public BoundedDbAdmission(MeterRegistry registry) {
        this.registry = registry;

        Gauge.builder("app.couchbase.admission.waiting",
                waiting, AtomicInteger::get)
            .description("Callers awaiting an application permit")
            .register(registry);
    }

    public <T> T execute(Supplier<T> work)
            throws InterruptedException {

        boolean acquired = slots.tryAcquire();
        if (!acquired) {
            waiting.incrementAndGet();
            Timer.Sample sample = Timer.start(registry);
            try {
                acquired = slots.tryAcquire(
                        150, TimeUnit.MILLISECONDS);
            } finally {
                sample.stop(Timer.builder(
                        "app.couchbase.admission.wait.duration")
                    .register(registry));
                waiting.decrementAndGet();
            }
        }

        if (!acquired) {
            throw new IllegalStateException(
                    "DB admission budget exceeded");
        }

        try {
            return work.get();
        } finally {
            slots.release();
        }
    }
}
~~~

**Những giới hạn phải hiểu:**

- `waiting` chỉ đếm callers **sau khi không lấy được permit ngay**, không phải tất cả operations active.
- `32` permits và `150ms` chỉ để minh họa; cần đo workload và SLO để chọn.
- Bài mẫu là code đồng bộ; không dùng semaphore blocking như vậy trên WebFlux event loop.
- `tryAcquire` có thể bị interrupt; `finally` vẫn giảm gauge/ghi wait sample.
- Không “ẩn” admission timeout thành query trả danh sách rỗng. Map thành lỗi overload/degraded phù hợp.
- Một gate mới phải được dùng nhất quán ở những code paths cần giới hạn; nếu còn đường trực tiếp bypass, gauge không phản ánh toàn bộ tải DB.

### 13.1. Tách accepted, rejected và waiting

Nếu muốn dashboard đầy đủ, thêm counters `accepted`/`rejected` và một gauge in-flight sau khi có permit. Khi tất cả permits bị dùng, **waiting có thể bằng 0** nếu thiết kế dùng tryAcquire non-blocking và từ chối ngay; điều đó không có nghĩa hệ thống không bị saturation.

## 14. Little's Law: liên hệ throughput, thời gian và số tác vụ trung bình

Trong một hệ thống tương đối ổn định, với cùng ranh giới quan sát:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trung bình **đang ở trong hệ thống**.
- \(\lambda\): throughput đã hoàn tất trung bình (operations/second).
- \(W\): thời gian một công việc ở trong hệ thống trung bình (second).

**Ví dụ lý thuyết**, không phải kết quả Couchbase đo được:

- Nếu throughput duy trì 200 operations/s.
- Thời gian trung bình trong phạm vi được đo là 0,05 s.
- Khi điều kiện ổn định và định nghĩa khớp, số operation trung bình trong hệ thống xấp xỉ \(200 \times 0{,}05=10\).

### 14.1. Những sai lầm khi áp dụng công thức

- Không dùng `p99 latency` thay `W` trung bình.
- Không trộn throughput toàn HTTP với duration chỉ của KV call rồi suy queue depth SDK.
- Không áp dụng trực tiếp trong lúc traffic đang tăng đột ngột, timeout hàng loạt hoặc hệ thống chưa ổn định mà không thảo luận giới hạn.
- Không kết luận số pending từ số in-flight khi thiếu dữ liệu về queue/service stages.
- Không coi `L` là toàn bộ Index mutation backlog; backlog ấy là một loại công việc khác.

Little's Law hữu ích để **kiểm tra tính hợp lý** của metrics, nhưng không thay queue gauge/tracing và không tự xác định nơi nghẽn.

## 15. SQL++ latency: chi phí của plan, scan, consistency và kết quả

Một truy vấn lịch sử:

~~~sql
SELECT META(o).id AS documentId,
       o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Index minh họa:

~~~sql
CREATE INDEX ix_orders_customer_date
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Cần thu:

1. **Generated SQL++** thực tế từ Repository/`CouchbaseTemplate`, có thể có type discriminator.
2. `EXPLAIN`/query plan để biết index, covering/non-covering, scan/fetch/sort.
3. Số rows và payload size.
4. Query consistency mode `NOT_BOUNDED`, `REQUEST_PLUS` hoặc mutation-based nếu dùng.
5. Query latency ở SDK, Query Service và HTTP E2E nếu có.
6. Query error/timeout/cancellation/retry rate.
7. Index Service update backlog và scan pressure ở cùng thời điểm.

### 15.1. QUERY REQUEST_PLUS chậm không nhất thiết là Query Engine DOWN

`REQUEST_PLUS` có thể yêu cầu GSI theo kịp mutation trước scan. Khi Index backlog tăng, query latency có thể tăng mà Data Service vẫn phục vụ KV tốt. `NOT_BOUNDED` có thể nhanh hơn nhưng cho phép index chưa mới; không thay mode để “cứu p99” nếu nghiệp vụ bắt buộc read-after-write.

### 15.2. Không dùng Query Engine ping thay benchmark index

`SELECT RAW 1` kiểm tra một câu SQL++ đơn giản, không đi qua named GSI của Orders. Benchmark thật phải dùng query shape đại diện và ghi plan/index rõ ràng.

### 15.3. Index lag và Query queue không phải một metric

GSI mutation backlog là các cập nhật chỉ mục chưa được áp dụng; Query Service queued requests là yêu cầu query chờ xử lý; SDK pending là thao tác phía client đang chờ theo định nghĩa SDK. Ba đại lượng cần có ba nguồn số liệu/nhãn khác nhau.

## 16. Tạo dashboard bốn lớp trước khi phân tích

Một dashboard tối thiểu có thể tổ chức:

| Lớp | Biểu đồ/câu hỏi |
| --- | --- |
| **User/HTTP** | Request rate, 5xx, p95/p99 theo route; phản ánh user impact |
| **Application** | Cache hit/miss, DB wrapper latency, admission waiting, in-flight, rejected |
| **SDK** | KV/query operation latency, retries, timeouts, endpoints nếu SDK metrics expose |
| **Couchbase Server** | KV latency/throughput, Query latency/errors, Index update backlog/scan, CPU/memory/I/O |

Không dựng dashboard bằng cách chỉ hiển thị `/health UP` và một đồ thị CPU. **Latency, errors, traffic và saturation** là những chiều bổ sung, và một sự cố có thể chỉ biểu hiện ở p99 hoặc hàng đợi.

### 16.1. Một dashboard có thể có hai đường latency trông khác nhau

Ví dụ thời gian SDK client đo lớn hơn thời gian thực thi query trên server do network, chờ kết quả, retry hoặc parsing. Khoảng chênh cần được phân tích bằng tracing/endpoint metrics, **không** tự quy toàn bộ là “mạng”.

### 16.2. Dashboard phải ghi đơn vị

Timer trong Micrometer thường dùng thời gian với unit phụ thuộc backend exporter; một hệ thống có thể biểu diễn seconds trong Prometheus và milliseconds ở bảng ứng dụng. Nếu nhầm đơn vị, p99 0,25 s có thể bị đọc thành 0,25 ms hoặc 250 s.

## 17. Prometheus: ví dụ đọc histogram, error rate và in-flight

Giả sử metric **do ứng dụng tự đăng ký** ở mục 10 được xuất qua Micrometer Prometheus registry. Tên thực tế và suffix có thể khác theo version/naming conventions; hãy kiểm tra `/actuator/prometheus` trong môi trường được cấp quyền trước khi copy câu truy vấn.

Ví dụ **có điều kiện** nếu exporter sinh:

~~~text
app_couchbase_operation_duration_seconds_bucket
app_couchbase_operation_duration_seconds_count
app_couchbase_operation_result_total
app_couchbase_operations_inflight
app_couchbase_admission_waiting
~~~

### 17.1. Đếm throughput từ Timer count

~~~promql
sum by (service, operation) (
  rate(app_couchbase_operation_duration_seconds_count[5m])
)
~~~

Kết quả có đơn vị **operations/second** theo các sample đã được record. Nếu số lượng request thấp, rate và percentile có thể biến động nhiều.

### 17.2. p95 từ histogram buckets

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, operation) (
    rate(app_couchbase_operation_duration_seconds_bucket[5m])
  )
)
~~~

Với histogram mang nhãn `outcome`, câu truy vấn trên gộp mọi outcome. Nếu SLO chỉ xét success requests, cần filter có chủ đích, **đồng thời** theo dõi error rate riêng để tránh báo latency đẹp vì nhiều request timeout.

### 17.3. p99 cho một Query template

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(app_couchbase_operation_duration_seconds_bucket{
      service="query",
      operation="orders_by_customer"
    }[5m])
  )
)
~~~

Đây là p99 **ước lượng theo các bucket** và phạm vi instrument của wrapper, không phải p99 của server Query Service.

### 17.4. Error rate theo outcome

~~~promql
sum(rate(app_couchbase_operation_result_total{
  outcome="error"
}[5m]))
/
clamp_min(
  sum(rate(app_couchbase_operation_result_total[5m])),
  0.000001
)
~~~

Đây là lỗi **theo nhãn `outcome=error` trong code mẫu**, chưa phân biệt not-found, conflict, timeout, cancellation. Khi business SLO yêu cầu phân loại sâu, phải cập nhật classification trước khi áp alert.

### 17.5. Gauges hiện tại

~~~promql
sum(app_couchbase_operations_inflight)
sum(app_couchbase_admission_waiting)
~~~

Gauge là ảnh chụp vào thời điểm scrape. **Không gọi hai câu trên là SDK queue size** vì chúng đo các biến `AtomicInteger` của ứng dụng. Dùng thêm `max_over_time` khi cần xem spike ngắn:

~~~promql
max_over_time(app_couchbase_admission_waiting[5m])
~~~

Nếu scraper lấy mẫu quá thưa, spike rất ngắn có thể bị bỏ lỡ. Đây là giới hạn của cơ chế quan sát, không phải chứng cứ không có đợi.

## 18. Percentile và thống kê dưới tải: cách diễn giải có trách nhiệm

Giả sử có một thí nghiệm với 10.000 requests và histogram có độ phân giải phù hợp. p95 biểu diễn ngưỡng mà xấp xỉ 95% các **mẫu được xem xét** có duration không lớn hơn ngưỡng đó; p99 tương tự ở khoảng 99%.

**Những chú ý:**

- p99 **không phải** max latency.
- p99 của 10 request rất thiếu ổn định; cần đủ mẫu trong cửa sổ.
- p99 là đặc điểm của một phân phối theo thời điểm/workload, không phải đặc tính cố định vĩnh viễn của Couchbase.
- Histogram bucket quá thô khiến estimate p99 thiếu chính xác.
- Bỏ timeout/error khỏi mẫu latency có thể che sự cố.
- Tính trung bình p99 theo từng pod không cho p99 toàn fleet.
- Một error diễn ra ở client sau deadline có thể không nằm trong server-side latency histogram.
- Cần so p99 **đúng cùng workload/query shape** khi đánh giá trước/sau tối ưu.

### 18.1. Không tự đặt số liệu Couchbase làm benchmark

Trong tài liệu và dashboard thiết kế, có thể dùng ngưỡng ví dụ để giải thích; **không công bố một con số mẫu như kết quả đo thực**. Kết luận latency phải dựa trên thí nghiệm, topology, tài nguyên, payload, consistency mode và query plan thực tế.

### 18.2. Dùng phân phối và error rate cùng lúc

Một dashboard nên hiển thị p50, p95, p99, sample count, error rate và queue depth. Nếu timeout tăng nhưng histogram latency thành công không tăng, hệ thống vẫn có vấn đề. Đừng “lọc bỏ các request lỗi” rồi công bố SLO xanh.

## 19. SDK request metrics và tracing: phân biệt với wrapper ứng dụng

Couchbase Java SDK có cơ chế thu thập request metrics/tracing và cấu hình theo `ClusterEnvironment`/SDK APIs tùy phiên bản. Spring Boot/Micrometer có thể auto-configure một phần instrumentation khi dependency và version tương thích.

**Trước khi bật thêm:**

1. Xem tên và nghĩa của metrics SDK thực sự xuất ra.
2. Kiểm tra SDK tính thời gian từ lúc operation được lên lịch, gửi mạng hay tới khi result hoàn thành.
3. Xác định retry, dispatch và server execution có span/metric riêng không.
4. Xác minh context propagation từ HTTP → Spring Data → SDK.
5. Chọn sampling để giảm tracing overhead và high-cardinality.
6. Không mặc định metrics SDK đo đúng **application admission queue** tự xây.
7. Đảm bảo không double-count khi cùng request có nhiều wrapper, retry hoặc nested calls.

### 19.1. Phân tầng một trace có ý nghĩa

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP span
    participant SVC as Service span
    participant GATE as App concurrency gate
    participant SDK as SDK operation
    participant CB as Couchbase Server

    HTTP->>SVC: GET customer history
    SVC->>GATE: wait for permit
    GATE-->>SVC: permit granted
    SVC->>SDK: SQL++ query
    SDK->>CB: request / possible retries
    CB-->>SDK: response
    SDK-->>SVC: rows or error
    SVC-->>HTTP: response
~~~

Cần gắn query template name/operation, không gắn raw customerId/document body vào spans. Không khẳng định tất cả các span trên tự động xuất hiện: **phải kiểm chứng instrumentation trên phiên bản đang chạy**.

### 19.2. Metric SDK và metric server có thể khác

Client nhìn tổng thời gian từ góc SDK, còn Query Service có metrics xử lý tại server; Index Service đo quét/cập nhật GSI. Nếu client latency lớn nhưng server execution ngắn, phân tích queue/network/retry/response size. Không tự lấy chênh lệch hai số khác clock/ranh giới làm network time chính xác.

## 20. Reactive: đo từ subscribe tới terminal signal

Với Spring WebFlux hoặc SDK reactive, **thời điểm tạo Publisher khác thời điểm thực thi**. Đo đoạn code trả `Mono` mà không subscribe có thể ghi latency gần 0 dù request chưa đi tới Couchbase.

Một wrapper minh họa cho `ReactiveCollection.get`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.couchbase.client.java.ReactiveCollection;
import com.couchbase.client.java.kv.GetResult;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public class ReactiveOrderKvMetrics {
    private final ReactiveCollection orders;
    private final MeterRegistry registry;
    private final AtomicInteger inFlight = new AtomicInteger();

    public ReactiveOrderKvMetrics(
            ReactiveCollection orders,
            MeterRegistry registry) {
        this.orders = orders;
        this.registry = registry;
    }

    public Mono<GetResult> get(String documentId) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            AtomicReference<String> outcome =
                    new AtomicReference<>("success");

            inFlight.incrementAndGet();

            return orders.get(documentId)
                    .doOnError(error ->
                            outcome.set("error"))
                    .doOnCancel(() ->
                            outcome.set("cancelled"))
                    .doFinally(signal -> {
                        inFlight.decrementAndGet();

                        sample.stop(Timer.builder(
                                "app.couchbase.reactive.get.duration")
                                .tags("service", "kv",
                                      "operation", "get",
                                      "outcome", outcome.get())
                                .register(registry));
                    });
        });
    }
}
~~~

**Cách đọc ví dụ:**

- `Mono.defer` tạo sample/inFlight **mỗi subscription**, không phải lúc service method được gọi.
- `doFinally` chạy khi complete, error hoặc cancel và giảm gauge để tránh leak.
- `doOnError` đánh dấu error trước terminal cleanup; `doOnCancel` đánh dấu cancel.
- Chưa có Gauge đăng ký cho `inFlight` trong snippet; nếu cần quan sát, đăng ký như mục 10.
- `ReactiveCollection` có thể được lấy từ collection SDK reactive theo API phiên bản; phải cấu hình bean/context phù hợp.
- Timeout và retry operator của Reactor có thể thay đổi vị trí/semantics của instrumentation; đặt wrapper **ở đúng ranh giới** muốn đo.
- Nếu cache phát kết quả trước khi gọi SDK, metric này không tăng — đó là hành vi đúng của phép đo SDK path.

### 20.1. Không block event loop để đo latency

Sai:

~~~java
// Không dùng trong WebFlux request event loop.
GetResult result = reactiveOrders.get(id).block();
~~~

Dùng non-blocking Publisher, `StepVerifier` trong test và timeouts/backpressure phù hợp. Việc `subscribe()` thủ công bên trong service để “khởi động đo” có thể làm sai thứ tự, mất propagation và che lỗi.

### 20.2. Flux streaming cần định nghĩa kết thúc

Nếu SQL++/reactive API trả `Flux<Row>`, có thể đo:

- **Time to first row**: từ subscribe đến `onNext` đầu tiên.
- **Total stream duration**: đến `onComplete` hoặc `onError`.
- **Rows consumed**: có thể ít hơn rows ở server nếu client cancel.
- **Cancellation rate**: số stream bị hủy giữa chừng.

Các metric này khác nhau. Một Flux có first row rất nhanh nhưng tổng duration lâu do client tiêu thụ chậm.

## 21. Hàng đợi ở các tầng: cách tìm nơi saturation bắt đầu

Hãy xem một thời điểm traffic tăng từ 100 lên 1.000 requests/s (chỉ là **tình huống giả định**, không phải benchmark Couchbase).

~~~text
HTTP inbound
  |
  +-- Web server connection/request queue
  |
  +-- Application concurrency gate
  |      waiting / accepted / rejected
  |
  +-- Java SDK operations
  |      request state, possible retries, network
  |
  +-- Query Service admission and execution
  |      running requests / queued requests
  |
  +-- Index Service updates and scans
         mutation backlog / scan load
~~~

Chỉ số cần phân biệt:

| Khi thấy tăng | Có thể giải thích | Kiểm tra tiếp |
| --- | --- | --- |
| App `admission.waiting` | Không lấy được permit đủ nhanh | Tải vào, permit capacity, DB response time |
| App `operations.inflight` | Nhiều DB calls chưa xong | p95/p99 và concurrency limit |
| SDK pending (nếu có metric) | Client-side request chưa hoàn tất/được dispatch theo định nghĩa | SDK queue/timeout/retry/network |
| Server Query queued | Query Service chưa xử lý kịp request | Query concurrency/capacity/plan |
| GSI mutation backlog | Index update không theo kịp write | Index resource, mutation rate |
| HTTP 5xx + no pending increase | Có thể fail-fast, RBAC hoặc lỗi mapping | Error categories và trace |
| Query latency tăng nhưng KV tốt | Query/Index path có nút thắt | `EXPLAIN`, Query/Index metrics |

**Không đồng nhất** mutation backlog với Query request queue; hai loại công việc khác nhau. Cũng không suy “queue=0” nghĩa không saturation nếu hệ thống đã chuyển sang từ chối ngay.

## 22. Thiết kế cảnh báo theo SLO, không theo một ngưỡng ngẫu nhiên

Một SLO cần định nghĩa **người dùng, endpoint, thời gian và cách tính**. Ví dụ hợp đồng *mẫu*:

~~~text
GET /orders/{id}
  - Read path theo KV
  - Latency objective: p95 dưới ngưỡng do nhóm thống nhất
  - Availability objective: success rate theo HTTP/API policy
  - Time window: rolling 5m và 1h, tránh alert nhiễu

GET /customers/{id}/orders
  - SQL++ + GSI, có giới hạn LIMIT/page
  - Query latency và timeout SLO riêng
  - Nếu read-after-write bắt buộc, ghi consistency mode
~~~

Không áp một mục tiêu p99 cho mọi operation khi query shapes và result sizes khác nhau.

### 22.1. Điều kiện cảnh báo nên kết hợp nhiều tín hiệu

Ví dụ:

- HTTP 5xx hoặc DB timeout tăng **và** KV/query p99 tăng.
- App admission waiting cao kéo dài **và** throughput không tăng.
- Query queued requests cao kéo dài **và** Index/Query CPU hoặc backlog tăng.
- Index mutation backlog tăng trong nhiều cửa sổ **và** REQUEST_PLUS latency tăng.
- Tỷ lệ rejected admissions tăng do concurrency limit đạt.

Những điều kiện này gợi ý root cause, chưa thay xác minh trực tiếp.

### 22.2. Tránh báo động từ một mẫu lẻ

Ở traffic thấp, percentile một phút rất biến thiên. Dùng đủ sample count, cửa sổ phù hợp, nhiều chu kỳ vi phạm hoặc error-budget burn-rate policy theo mức độ ưu tiên. Alert phải gắn runbook/hậu quả cụ thể, không chỉ “p99 vượt 100ms”.

### 22.3. Bảo vệ dữ liệu riêng tư trong alert

Không đưa full SQL++ query chứa parameter, document key hoặc error message có token vào thông báo alert. Dùng query template name, service, operation, stacktrace/traces đã kiểm soát quyền.

## 23. Kịch bản benchmark có kiểm soát

Đừng chạy benchmark tự phát trên production. Trên cluster lab/test cùng phiên bản và topology gần môi trường mục tiêu:

1. Xác nhận bucket/scope/collection, secondary indexes online.
2. Ghi versions: Spring Boot, Spring Data Couchbase, Java SDK, Couchbase Server, Micrometer.
3. Chuẩn bị dữ liệu có số lượng và kích thước đại diện, phân bố `customerId` thực tế.
4. Chọn query templates và index plan cố định.
5. Warm-up riêng, xác định có đo cold-start hay không.
6. Tăng concurrency/rate theo các bậc **có giới hạn**, không dùng retry vô hạn.
7. Tách KV read, KV write, SQL++ read và mixed workload.
8. Đo p50/p95/p99, error rate, in-flight, queue wait, rejection, SDK/Server metrics.
9. Thử `NOT_BOUNDED` và `REQUEST_PLUS` trong kịch bản có mục tiêu rõ, không đánh đổi freshness vô ý.
10. Hạ tải, quan sát backlog và latency phục hồi.
11. Lặp lại đủ vòng để tránh kết luận từ một đợt nhiễu.

### 23.1. Ma trận thử nghiệm mẫu

| Giai đoạn | Workload | Điều cần kiểm chứng |
| --- | --- | --- |
| KV baseline | KV get theo ID ở tải thấp | Latency floor, SDK startup đã ấm |
| KV mixed | Get + upsert/replace | Write latency, CAS conflicts, durability cost |
| Query baseline | SQL++ theo customerId, đúng GSI | Query plan, result size, p95/p99 |
| Index pressure | Mutation rate tăng có kiểm soát | Index backlog, consistency wait |
| Burst | Tăng request rate ngắn | Queue wait, in-flight, rejection |
| Recovery | Giảm rate về baseline | Queue/backlog có xả và p99 hồi phục |
| Failure test | Chỉ trong cluster lab được phép | Timeout/retry/circuit breaker và health behavior |

### 23.2. Các mẫu bị lỗi cũng là kết quả

Nếu query timeout/rejected trong lúc tải cao, đừng loại chúng khỏi báo cáo rồi tuyên bố throughput/latency tốt. Cần tổng số attempts, completions, failures, cancellations, pending-at-end và thỏa điều kiện shutdown.

### 23.3. Coordinated omission

Một load generator **chỉ gửi request mới sau khi request trước hoàn thành** có thể làm số request giảm đúng lúc server chậm, khiến histogram không thể hiện đầy đủ trải nghiệm ở mức request arrival rate đặt trước. Khi performance study nghiêm túc, xem cơ chế **open-loop vs closed-loop**, expected arrival schedule, coordinated omission và sampling bias. Không biến một bài smoke test thành capacity claim.

## 24. Kiểm thử các metric của wrapper không cần cluster thật

Dùng `SimpleMeterRegistry` để kiểm chứng bộ đếm/gauge của ứng dụng. Đây là **unit test instrumentation**, không chứng minh Couchbase latency ngoài đời.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class CouchbaseOperationMetricsTest {

    @Test
    void recordsSuccessAndReturnsInflightToZero() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new CouchbaseOperationMetrics(registry);

            String answer = metrics.record(
                    "kv", "get", () -> "OK");

            assertEquals("OK", answer);
            assertEquals(1.0,
                    registry.find("app.couchbase.operation.result")
                            .tags("service", "kv",
                                  "operation", "get",
                                  "outcome", "success")
                            .counter().count());

            assertEquals(0.0,
                    registry.find("app.couchbase.operations.inflight")
                            .gauge().value());
        }
    }

    @Test
    void recordsExceptionAndReturnsInflightToZero() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new CouchbaseOperationMetrics(registry);

            assertThrows(IllegalStateException.class, () ->
                    metrics.record("query", "orders_by_customer",
                            () -> {
                                throw new IllegalStateException("test");
                            }));

            assertEquals(1.0,
                    registry.find("app.couchbase.operation.result")
                            .tags("service", "query",
                                  "operation", "orders_by_customer",
                                  "outcome", "error")
                            .counter().count());
            assertEquals(0.0,
                    registry.find("app.couchbase.operations.inflight")
                            .gauge().value());
        }
    }
}
~~~

Trong test thực, thêm assertion cho Timer count và không tạo metric tags mới từ giá trị dữ liệu người dùng. Cần bảo đảm registry lifecycle phù hợp cấu hình Spring; nếu meter không tồn tại, kiểm tra code path có thật sự được gọi không.

## 25. Integration test: so latency KV và Query trên fixture riêng

Unit test ở mục 24 không chạy Couchbase. Để có benchmark/diagnostic thực, dùng **test cluster** và thao tác SDK rõ ràng:

~~~java
import java.time.Duration;
import java.util.UUID;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

public final class ControlledCouchbaseSample {
    private final Cluster cluster;

    public ControlledCouchbaseSample(Cluster cluster) {
        this.cluster = cluster;
    }

    public void runOnce() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String id = "order::metric-it-" + UUID.randomUUID();
        String customerId = "customer-it-" + UUID.randomUUID();
        boolean inserted = false;

        try {
            orders.insert(id, JsonObject.create()
                    .put("customerId", customerId)
                    .put("status", "CREATED"));
            inserted = true;

            long kvStart = System.nanoTime();
            orders.get(id);
            long kvElapsedNs = System.nanoTime() - kvStart;

            String sql = """
                SELECT RAW META(o).id
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                """;

            long queryStart = System.nanoTime();
            var rows = cluster.query(
                    sql,
                    QueryOptions.queryOptions()
                            .parameters(JsonObject.create()
                                    .put("customerId", customerId))
                            .scanConsistency(
                                    QueryScanConsistency.REQUEST_PLUS)
                            .timeout(Duration.ofSeconds(5)))
                    .rowsAsString();
            long queryElapsedNs =
                    System.nanoTime() - queryStart;

            // Xuất qua metrics/fixture reporter, không
            // tự coi 1 sample là benchmark có ý nghĩa.
        } finally {
            if (inserted) {
                orders.remove(id);
            }
        }
    }
}
~~~

**Lưu ý về snippet:**

- Chỉ chạy trên môi trường lab có bucket/scope/collection và GSI online.
- SQL++ dùng `REQUEST_PLUS` để kiểm tra đường query phản ánh insert đã ACK; nó có thể tốn thêm thời gian đợi index.
- Đo Query bao gồm `rowsAsString()` nên không hoàn toàn tương đương một SDK query call không materialize results.
- Các biến `kvElapsedNs`/`queryElapsedNs` phải đưa vào reporter/Timer trong fixture thực; snippet minh họa ranh giới đo, không tự xuất một con số benchmark.
- Nếu insert đã được server xử lý nhưng ACK bị mất, cờ `inserted` có thể false; suite hoàn chỉnh cần cleanup các write ambiguous bằng ID/prefix.
- `finally` cleanup cũng có thể thất bại; test runner nên báo lỗi này, không bỏ qua. Không chạy trên production hoặc tạo lượng fixture lớn vô hạn.

### 25.1. Không assert NOT_BOUNDED phải thấy dữ liệu cũ

`NOT_BOUNDED` chỉ không yêu cầu GSI chờ mutation mới, không bắt buộc query phải stale. Correctness test read-after-write nên dùng `REQUEST_PLUS` hoặc `MutationState/consistentWith` với điều kiện query/index hợp lệ.

## 26. Kiểm thử reactive in-flight, error và cancellation

Với wrapper `Mono.defer(...)` ở mục 20, các tình huống cần kiểm thử bằng `StepVerifier` và publisher fake:

| Tình huống | Điều nên assert |
| --- | --- |
| Mono được tạo nhưng chưa subscribe | In-flight không tăng |
| Subscribe và success | Timer có sample, in-flight về 0 |
| Subscribe và error | Outcome error, in-flight về 0 |
| Subscription cancel | Outcome cancelled, in-flight về 0 |
| Timeout operator phía ngoài wrapper | Quy định scope đo nào bao gồm timeout/cancel |
| Retry operator tạo lại subscription | Có thể có nhiều samples; giải thích tên metric là attempts hay logical operations |
| Flux được cancel sau một vài rows | Đo stream duration tới cancel, không coi toàn bộ rows đã được xử lý |

**Cảnh báo:** Nếu instrumentation nằm **bên trong `retryWhen`**, mỗi retry subscription có thể được đếm thành một attempt; nếu đặt **bên ngoài**, timer có thể bao gồm cả chuỗi retry. Hai thiết kế đều có ích nhưng khác nghĩa. Đặt tên `attempt_duration` và `logical_operation_duration` riêng khi cần.

Trong WebFlux, không dùng blocking semaphore ở event loop để đo queue. Dùng backpressure/concurrency operators với cơ chế non-blocking và instrument queue/gate đúng vị trí.

## 27. Phân tích một incident: KV ổn, Query chậm và pending tăng

Tình huống **giả định để luyện cách suy luận**:

~~~text
10:00  HTTP rate tăng tại endpoint lịch sử Orders
10:01  app.couchbase.operations.inflight tăng
10:02  Query p99 tăng, KV p99 gần baseline
10:03  Query request timeout tăng
10:04  app.couchbase.admission.waiting tăng
10:05  Index mutation backlog cũng tăng
~~~

Bằng chứng trên cho thấy nút thắt có thể nằm ở **đường Query/Index** nhưng chưa chứng minh một nguyên nhân duy nhất.

**Trình tự điều tra:**

1. Kiểm tra route/operation/query template đang tăng tải.
2. Xem `EXPLAIN` của query thật, đúng collection/index.
3. Phân biệt query time do scan/fetch/sort với consistency wait do `REQUEST_PLUS`.
4. Kiểm tra Index backlog, Query Service CPU/memory, Query queue.
5. So thời điểm app waiting tăng với DB latency và limit permits.
6. Xác định cache hit ratio/result-size có thay đổi không.
7. Phân tích timeout/retry, liệu retries đang khuếch đại load không.
8. Giảm/constrain concurrency hoặc tối ưu query/index theo bằng chứng.
9. Đo recovery và xác nhận business freshness SLO vẫn đáp ứng.

Không đổi tất cả query sang `NOT_BOUNDED` chỉ để giảm latency nếu endpoint bắt buộc đọc sau ghi. Không tăng concurrency permit liên tục vì thấy waiting cao: nếu server đang saturation, điều đó có thể làm lỗi nặng hơn.

## 28. Runbook: đọc thứ tự Traffic → Errors → Latency → Saturation

~~~mermaid
flowchart TD
    A["Couchbase API chậm hoặc timeout"] --> B["Đo traffic/rate theo KV và Query"]
    B --> C{"Error rate tăng?"}
    C -->|Có| D["Phân loại timeout, RBAC, CAS, network, query error"]
    C -->|Không| E["Xem p95/p99 và count"]
    D --> E
    E --> F{"App admission waiting/inflight tăng?"}
    F -->|Có| G["Kiểm tra gate, SDK latency và retry"]
    F -->|Không| H["Kiểm tra Query/Index/SDK/server timeline"]
    G --> I["Tách server queued requests và Index backlog"]
    H --> I
    I --> J["Đối chiếu EXPLAIN, cache, consistency, payload"]
    J --> K["Khắc phục nguyên nhân và đo recovery"]
~~~

**Runbook thực tế:**

1. Xác định phạm vi: chỉ một route, một pod, một operation hay toàn cluster?
2. Đặt cùng time window cho HTTP latency, application Timers, SDK/client và server metrics.
3. So request rate và error rate; không chỉ nhìn p99.
4. Với lỗi, phân loại not-found, timeout, CAS conflict, RBAC, unavailable, cancellation.
5. Với latency KV, xem Data/transport/SDK retries và payload.
6. Với SQL++, xem query shape, plan, GSI, result size, consistency và server queue.
7. Đọc in-flight và **waiting** theo đúng ranh giới ứng dụng instrument.
8. Đọc SDK pending và Query queued chỉ khi version/metrics thực sự có, không tự suy từ app gauge.
9. Tách Index mutation backlog khỏi Query request backlog.
10. Kiểm tra retry storm, client cancellation và queueing ở app.
11. Đánh giá circuit breaker, load shedding, concurrency limit và pagination.
12. Sau thay đổi, đo lại throughput, p95/p99, error rate, queue depth và freshness SLO.
13. Lưu query plan/topology/version và các giới hạn kết luận.
14. Tắt logging DEBUG/TRACE nếu đã bật để điều tra.

## 29. Liên hệ CAS, durability, TTL và transaction

Đây là các yếu tố làm thay đổi cách diễn giải metrics, nhưng **không phải cùng một phép đo**.

### 29.1. CAS conflict có thể làm latency/app retries tăng

`@Version` trong Spring Data Couchbase dùng optimistic locking theo CAS. Nếu nhiều writer cạnh tranh, `save` có thể gặp conflict. Retry ở ứng dụng (khi hợp lý) làm nhiều KV attempts hơn số logical business requests. Đo **attempt count** và **logical request latency** riêng để không nhầm lưu lượng.

### 29.2. Durability làm thay đổi write acknowledgement

KV mutation dùng durability level khác nhau có thể có latency profile khác. So sánh benchmark chỉ có ý nghĩa khi ghi rõ durability options; write timeout ambiguous không tự được xem là “mutation chưa chạy”.

### 29.3. TTL/expiry ảnh hưởng data availability

Document expired có thể trả not-found dù cluster khỏe. Phân loại missing key theo domain; không biến hàng nghìn expiry hợp lệ thành availability outage.

### 29.4. Transaction là nhiều hoạt động liên quan

Một transaction có thể gồm reads/writes/retries, commit và cleanup. Latency transaction khác latency một KV operation, và transaction retry có thể tăng số SDK calls. Cần spans/counters ở mức logical transaction, không chỉ per-KV Timer.

### 29.5. Secondary index freshness không đồng nghĩa health

Một GSI online có thể còn backlog và query NOT_BOUNDED trả danh sách chưa mới. `REQUEST_PLUS` có thể chờ index và ảnh hưởng p99; đó là đánh đổi giữa freshness và latency cần đo rõ.

## 30. Lỗi thiết kế metrics thường gặp

1. Đo mọi thao tác bằng một histogram Couchbase chung, che khác biệt KV và SQL++.
2. Đặt cùng tên `latency` cho HTTP, SDK và server mà không ghi ranh giới.
3. Ghi `System.currentTimeMillis()` cho duration ngắn rồi bị ảnh hưởng clock shifts.
4. Bật percentiles mà không xét đủ sample count/histogram bucket resolution.
5. Lấy trung bình p99 từ nhiều pod.
6. Loại timeout khỏi latency report nhưng không báo error rate.
7. Coi empty SQL++ rows là một lỗi DB.
8. Coi KV not-found do TTL là Data Service DOWN.
9. Gộp CAS conflict hợp lệ với transport error.
10. Coi mọi write timeout nghĩa server chưa ghi.
11. Gắn documentId/customerId/raw SQL++ vào tags.
12. Gọi in-flight là pending SDK, dù wrapper đếm cả active operations.
13. Coi Index mutation backlog là số Query requests đang đợi.
14. Không đo application admission waiting/rejected dù có concurrency limit.
15. Dùng rate từ Gauge như Counter hoặc đọc Counter thô thành QPS.
16. Gắn `REQUEST_PLUS` vào mọi health query rồi than Query p99 cao.
17. So query có LIMIT 20 với query trả 50.000 rows.
18. Không warm-up SDK rồi suy cold-start latency là steady-state.
19. Tự tạo hàng nghìn probes và làm Query/Index Service quá tải.
20. Không phân biệt nested instrumentation làm đếm hai lần.
21. Không xác minh tên metrics SDK thực sự tồn tại trong version.
22. Tạo manual metrics nhưng không kiểm thử error/cancellation cleanup.
23. Dùng blocking code trong Reactor event loop để “đo cho đơn giản”.
24. Không ghi index plan, dataset, topology, concurrency và timeout budget.
25. Bật tracing/logging quá sâu không có sampling, tăng overhead benchmark.
26. Đặt alerts trên một mẫu p99 rất ít requests.
27. Không đo recovery khi giảm tải.
28. Trả 200/danh sách rỗng sau timeout khiến error metric sai lệch.

## 31. Bài tập tình huống

### A. In-flight tăng nhưng waiting bằng 0

Có thể đã đạt saturation không?

**Gợi ý:** Có thể. Queue có thể không tồn tại, gate đã cho phép mọi operation vào SDK hoặc đang fail-fast. Kiểm tra concurrency, rejected counter, SDK latency và server load.

### B. SQL++ p99 tăng còn KV p99 ổn

Có thể kết luận Couchbase cluster toàn bộ down?

**Gợi ý:** Không. Kiểm tra Query Service, GSI, query plan, result size và consistency wait. Data Service KV có thể còn hoạt động.

### C. Histogram success đẹp nhưng timeout rate tăng

SLO có thể được coi là đạt?

**Gợi ý:** Chưa. Latency report trên success samples không loại trừ lỗi lớn. Phải báo tỷ lệ timeout/error và scope của mẫu.

### D. GSI mutation backlog cao

Đây có phải Query request queue đang dài?

**Gợi ý:** Không. Backlog index là mutation updates chờ áp dụng; Query queue là query requests đang chờ xử lý. Đo riêng.

### E. Sử dụng `@Version` thấy nhiều conflict

Conflict có phải luôn là Data Service unavailable?

**Gợi ý:** Không. Có thể do cạnh tranh cập nhật và là expected control flow. Phân loại để phân tích contentions/business policy.

### F. Reactive `Mono` tạo trước 500 ms mới subscribe

Đo latency từ lúc tạo `Mono` có đúng SDK operation duration?

**Gợi ý:** Không. Đặt sample tại subscription/`defer`; xác định first-row/terminal time và cancellation.

### G. Hai instance có p99 khác nhau

Có thể lấy average hai p99 thành fleet p99?

**Gợi ý:** Không. Hãy tổng hợp histogram buckets nếu có, với label/window/bucket tương thích; không lấy trung bình quantiles.

### H. Metadata labels có mỗi Order UUID

Điều gì xảy ra?

**Gợi ý:** High cardinality làm metric series bùng nổ, tăng chi phí và nguy cơ lộ dữ liệu. Dùng service/operation/query-shape hữu hạn.

### I. Mỗi request lịch sử gọi `REQUEST_PLUS`

Tại sao latency có thể tăng khi write rate cao?

**Gợi ý:** Query có thể chờ GSI bắt kịp mutation. Đo backlog, consistency wait và business freshness SLO trước khi thay policy.

### J. Benchmark tải tăng, generator gửi request mới chỉ sau response

Có thể đánh giá latency ở arrival rate cố định không?

**Gợi ý:** Có nguy cơ coordinated omission; cần hiểu open-loop/closed-loop và ghi actual throughput, pending, errors, latency theo workload.

## 32. Checklist trước khi triển khai production

- [ ] Đã định nghĩa rõ ranh giới đo HTTP, app service, SDK và Couchbase Server?
- [ ] KV get/insert/replace và SQL++ query có meter riêng theo operation?
- [ ] Query shapes và index plan được ghi trong benchmark?
- [ ] Timer dùng monotonic duration, có count và histogram hợp lý?
- [ ] p95/p99 có sample count, window, bucket resolution rõ?
- [ ] Không tính trung bình percentiles của từng pod?
- [ ] Error rate có mẫu số và policy not-found/conflict/cancel rõ?
- [ ] Write timeout ambiguous được ghi và xử lý idempotency?
- [ ] Counter được tính rate, Gauge được xem là snapshot?
- [ ] In-flight và waiting được đặt tên theo đúng vị trí instrument?
- [ ] Không nhầm app queue, SDK pending, Query queue, Index backlog?
- [ ] Admission gate có metrics waiting, accepted/rejected và bounded timeout?
- [ ] Không truyền document ID/customer ID/raw query vào metric tags?
- [ ] Đã kiểm tra Micrometer/SDK meters thực sự tồn tại theo phiên bản?
- [ ] Prometheus endpoint được bảo vệ đúng network/RBAC?
- [ ] Query consistency mode và result size được gắn với từng nhóm workload?
- [ ] HTTP/SDK/server metrics đồng bộ time window và thời gian quan sát?
- [ ] Có trace/correlation xuyên Controller → Repository/Template → SDK?
- [ ] Reactive instrumentation bắt đầu tại subscription, kết thúc ở terminal signal?
- [ ] Reactive cancellation/retry có scope và status được định nghĩa?
- [ ] Không block Reactor event loop hoặc gây overload bằng load generator?
- [ ] Dashboard có traffic, errors, latency, saturation và freshness?
- [ ] Alerts yêu cầu đủ samples/vi phạm kéo dài, không chỉ một spike?
- [ ] Có cảnh báo Query Index backlog riêng với Query queue?
- [ ] Benchmark có warm-up, workload matrix, recovery và limits?
- [ ] Unit tests có success/error/in-flight cleanup?
- [ ] Integration test dùng cluster lab, fixture riêng, cleanup có kế hoạch?
- [ ] CAS, durability, TTL, transaction được tính đúng khi diễn giải metrics?
- [ ] Runbook nêu rõ trách nhiệm on-call và phương án khôi phục?

## 33. Kết luận

**Đo độ trễ Key-Value, truy vấn, lỗi và số thao tác đang chờ là bài toán định nghĩa phạm vi trước khi chọn công cụ.** Một Timer quanh Repository, một histogram trong SDK, một chỉ số Query Service và một queue gauge của ứng dụng có thể cùng nói về một HTTP request nhưng không mô tả cùng ranh giới. Nếu không tách rõ, việc tối ưu rất dễ đi sai hướng: tăng permits khi server đã nghẽn, đổi `REQUEST_PLUS` chỉ để giảm p99 mà làm sai freshness contract, hoặc restart pod vì GSI đang backlog.

Trong **Spring Data Couchbase**, hãy đo **KV và SQL++ riêng**, gắn **operation/query-shape/outcome** bằng labels hữu hạn, dùng **Timer/histogram cho latency, Counter cho events, Gauge cho in-flight/waiting**, và kết hợp SDK/server metrics với tracing để biết thời gian ở đâu. Phân biệt **application admission queue, SDK pending requests, Query Service queued requests và Index mutation backlog**; đo cả p95/p99 lẫn timeout, retry, cancellation, CAS conflict và recovery.

Một dashboard tốt không chỉ cho thấy hệ thống “đang chậm”, mà giúp trả lời **đường nào chậm, có bao nhiêu thao tác bị ảnh hưởng, đang chờ ở tầng nào, tại sao và hành động nào cải thiện SLO mà vẫn giữ tính đúng đắn**.
