# Load test, fault injection và kiểm thử phục hồi

## 1. Tại sao REST API cần kiểm thử vượt qua happy path?

Trong module **INTEGRATION_API_REST**, hợp đồng REST không chỉ được đánh giá qua response 200 của một request đơn lẻ. Khi nhiều người dùng cùng gọi **GET, POST, PATCH**, API phải giữ được **ngữ nghĩa HTTP, xác thực, phân quyền, tính nhất quán, idempotency, giới hạn tài nguyên và thời gian phản hồi** ngay cả khi upstream chậm, một node lỗi hoặc kết nối DB bị gián đoạn.

Tình huống xuyên suốt: **Order API** viết bằng Spring Boot cung cấp:

- **GET /api/v1/products?limit=...&cursor=...**: truy vấn catalog có phân trang và cache.
- **POST /api/v1/orders**: tạo đơn bằng Idempotency-Key, kiểm tra giá/tồn kho rồi ghi transaction.
- **GET /api/v1/orders/{id}**: đọc đơn theo **tenant/owner ACL**, hỗ trợ ETag.
- **PATCH /api/v1/orders/{id}**: sửa thông tin trong trạng thái cho phép, dùng If-Match.
- **GET /api/v1/export-jobs/{id}**: xem job bất đồng bộ và tải kết quả khi được phép.

Hệ thống phụ thuộc **PostgreSQL**, Inventory API, Payment API, Redis cache/rate limiter và gateway. Thử nghiệm phải bảo đảm **một lần POST không tạo hai đơn**, dữ liệu của tenant A không xuất hiện với tenant B, và request bị 429/503/504 phải được diễn giải đúng, không đẩy lỗi ứng dụng thành một response 200 giả.

**Kết quả học tập:** bạn sẽ biết thiết kế workload và SLO, dùng k6 hoặc công cụ tương đương để tạo tải; tiêm lỗi mạng/dependency an toàn; kết hợp Java/Spring, Testcontainers/MockWebServer với kịch bản phục hồi; xác nhận correctness, security, observability, recovery time và viết báo cáo quyết định triển khai.

### 1.1. Ba nhóm thí nghiệm không đồng nghĩa

| Nhóm | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Load/performance test** | Với arrival rate và dữ liệu đại diện, API đáp ứng latency/throughput/SLO ra sao? | RPS, p95/p99, failure ratio, saturation, queue wait |
| **Fault injection / resilience test** | Khi network, DB, cache hoặc upstream lỗi, hệ thống có fail-fast, không cascade và giữ bất biến không? | Error classification, circuit/bulkhead, fallback, trạng thái DB |
| **Recovery test** | Sau khi dừng lỗi hoặc restart thành phần, bao lâu hệ thống trở lại trạng thái ổn định và có mất dữ liệu không? | Recovery time, backlog drain, RPO, orphan operations, cache correctness |

**Không coi "ứng dụng vẫn trả HTTP 200" là thành công**: API có thể trả sai giá, trùng đơn, lọt dữ liệu cross-tenant hoặc lặng lẽ bỏ qua lỗi trong lúc load test.

## 2. Đặt SLO và điều kiện đạt trước khi chạy

Ví dụ một **test plan giả định** cho Order API; các mức này là mục tiêu để minh họa, không phải ngưỡng khuyến nghị mọi sản phẩm:

| API hoặc chỉ số | Mục tiêu ở tải kỳ vọng | Điều kiện đi kèm |
| --- | --- | --- |
| **GET /products** | p95 dưới 250 ms; p99 dưới 600 ms | Limit ≤100, đúng tenant/filter, cache warm/cold được tách |
| **GET /orders/{id}** | p95 dưới 300 ms | Không rò tenant, ETag/304 đúng |
| **POST /orders** | p95 dưới 800 ms | Không tạo đơn trùng, không giảm xác minh giá/tồn kho |
| **Unexpected server/transport errors** | Dưới 0,5% | Tách 429 được dự tính và 4xx do input thử nghiệm |
| **Recovery sau Inventory outage 60 s** | Ổn định trở lại trong 30 s sau khi upstream khỏe | Không retry storm, backlog drain, đúng trạng thái đơn |
| **DB restart đã được kiểm soát** | Không mất bản ghi đã commit | RPO=0 trong giới hạn mô hình lưu trữ/thử nghiệm |

Điều kiện đạt phải bao gồm **latency + tỷ lệ kết quả đúng + giới hạn tài nguyên + bảo mật + thời gian phục hồi**. Nếu workload có 40% request cố ý gửi token sai, 401 là expected behavior; không cộng 401 ấy vào **unexpected error rate** rồi tuyên bố dịch vụ lỗi. Tuy nhiên không được dùng cách lọc metric để che 500/503 do hệ thống quá tải.

### 2.1. Các khái niệm đo quan trọng

- **Arrival rate:** số request mới đến mỗi giây, không phải số request kết thúc mỗi giây.
- **Throughput:** số operation/request hoàn tất theo thời gian.
- **Latency:** thời gian client quan sát từ gửi request đến hoàn tất phần response được đo; tách **time-to-first-byte** và body download khi streaming.
- **p95/p99:** percentiles của latency trong đúng window, đúng endpoint/operation và nhóm outcome.
- **Saturation:** CPU, memory, GC, active threads, DB connections, pool pending, queue depth, retries, file descriptors, network.
- **Error rate:** số lỗi không kỳ vọng trên số attempts/operations thích hợp; phân biệt HTTP 4xx, 5xx, timeout/connection reset và business failure.
- **Availability:** khả năng đáp ứng **mức tối thiểu đúng**; không chỉ là có bất kỳ response HTTP.
- **RTO/RPO:** Recovery Time Objective / Recovery Point Objective: thời hạn mong muốn phục hồi và mức mất dữ liệu có thể chấp nhận; cần xác định phạm vi đo và giả định dữ liệu.

**Percentiles cần đủ mẫu.** Một bài test 20 request không thể cung cấp kết luận đáng tin về p99. Cân nhắc khoảng tin cậy, số request mỗi operation, test windows, warm-up và biến động CI infrastructure trước khi quyết định đạt/không đạt.

## 3. Thiết kế workload sát hành vi sử dụng

Không chỉ bắn **GET /** hoặc một ID cố định thật nhanh. Một workload tốt có **hỗn hợp methods, identity, dữ liệu, body size và cache modes**:

| Thành phần workload | Tỷ trọng minh họa | Kiểm soát |
| --- | ---: | --- |
| GET /products (có limit/cursor/filter) | 45% | Warm/cold cache, page 1/page N, filter hợp lệ |
| GET /orders/{id} | 30% | IDs nhiều tenant, size nhỏ/lớn, ETag conditional |
| POST /orders | 15% | Idempotency-Key riêng cho business operation, chỉ synthetic orders |
| PATCH /orders/{id} | 5% | If-Match thực, có cạnh tranh sửa |
| GET /export-jobs/{id} | 5% | Job authorized, polling bounded |

Tỷ trọng phải xuất phát từ **traffic/reliability requirements thật** nếu có; bảng trên chỉ là giả định phục vụ bài học. Không lấy dữ liệu sản xuất chứa PII hoặc token thật đưa vào test. Sinh **nhiều ID hợp lệ**, nhiều tenants/roles và data distributions; nếu mọi GET dùng đúng một product ID, cache có thể che DB bottleneck.

### 3.1. Các kiểu load profile

| Profile | Cách tăng tải | Mục đích |
| --- | --- | --- |
| **Baseline** | Tải nhẹ, ổn định | Lấy latency/error/saturation chuẩn |
| **Steady expected load** | Đạt arrival rate dự kiến rồi giữ đủ lâu | Kiểm SLO trong chế độ bình thường |
| **Stress/capacity** | Tăng dần đến điểm gãy có kiểm soát | Biết knee point, throttling và giới hạn |
| **Spike** | Tăng mạnh ngắn hạn rồi hạ | Kiểm queue, autoscaling, rate limit, recovery |
| **Soak/endurance** | Tải ổn định trong nhiều giờ | Leak memory/socket, TTL, connection churn |
| **Concurrent contention** | Nhiều writes lên cùng object | Kiểm CAS, idempotency, locking/transaction |
| **Fault-under-load** | Giữ tải chuẩn và gây lỗi phụ thuộc có giới hạn | Đo degrade/recovery dưới áp lực thực |

**Tăng tải có giới hạn và quyền thực hiện rõ ràng.** Stress/spike tests chỉ chạy trên môi trường được ủy quyền, có trần request, trần dữ liệu và phương án dừng; không gửi lưu lượng gây gián đoạn tới hệ thống ngoài phạm vi thử nghiệm.

### 3.2. Open model và closed model

- **Closed workload:** giữ N virtual users; mỗi user đợi response rồi mới gọi tiếp. Khi server chậm, tốc độ phát request tự giảm. Hợp với workflow có think-time, nhưng có thể **che quá tải**.
- **Open workload:** phát request theo **arrival rate** định trước, độc lập với thời gian request hoàn tất; phản ánh kịch bản traffic tới liên tục. Khi không đủ virtual users hoặc máy phát tải hết capacity, phải xem **dropped iterations/achieved rate** chứ không giả định load target đã đạt.

~~~mermaid
flowchart LR
    A[Arrival rate cố định] --> B[Gateway]
    B --> C[Order API]
    C --> D[Connection / thread pool]
    D --> E[(Database)]
    C --> F[Inventory / Payment]
    F --> C
    C --> G[HTTP result + latency]
~~~

**Coordinated omission:** nếu load generator chờ server rồi mới tạo request tiếp, các khoảng thời gian đáng ra request vẫn đến khi server bị treo có thể không được đo đúng. Dùng open-arrival model và kiểm generator capacity khi cần đánh giá latency dưới traffic độc lập. Không trộn percentiles từ các window/endpoint khác nhau rồi gọi là p99 của một operation cụ thể.

### 3.3. Tách cache và tầng đo

Load test nên ghi rõ **cold cache vs warm cache**, ETag/304, CDN/gateway cache, HTTP/2 vs HTTP/1.1, response compression, DNS/TLS reuse. Nếu có nhiều region, phân tách network RTT với server processing. Mỗi kết quả phải chỉ rõ điểm đo: client → gateway hay gateway → Spring.

Khi test HTTP/2 có multiplexing, **số connections không tương đương concurrency**. Khi test DB pool, tách **HTTP connection acquisition** khỏi **DB connection wait**.

## 4. k6: viết load test HTTP có giới hạn và assertions

Ví dụ **k6 JavaScript** dùng **constant-arrival-rate** trong một môi trường thử nghiệm được cho phép. Không hardcode password, token hay API thật vào script. Client có token test cấp sẵn và test dữ liệu không nhạy cảm:

~~~javascript
import http from "k6/http";
import { check } from "k6";
import { Rate } from "k6/metrics";

const unexpected = new Rate("unexpected_http_error");

export const options = {
  scenarios: {
    catalog_read: {
      executor: "constant-arrival-rate",
      rate: 25,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 20,
      maxVUs: 80
    }
  },
  thresholds: {
    "http_req_duration{scenario:catalog_read}": ["p(95)<250", "p(99)<600"],
    "http_req_failed{scenario:catalog_read}": ["rate<0.01"],
    "unexpected_http_error": ["rate<0.005"],
    "dropped_iterations": ["count==0"]
  }
};

const base = __ENV.API_BASE_URL;
const token = __ENV.TEST_ACCESS_TOKEN;
const ids = (__ENV.PRODUCT_IDS || "").split(",").filter(Boolean);

export function setup() {
  if (!base || !token || ids.length === 0) {
    throw new Error("Missing test URL/token/product fixtures");
  }
}

export default function () {
  const id = ids[Math.floor(Math.random() * ids.length)];
  const url = base + "/api/v1/products/" + encodeURIComponent(id);
  const res = http.get(url, {
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/json"
    },
    tags: { operation: "get_product" },
    timeout: "2s"
  });

  const ok = check(res, {
    "status 200": r => r.status === 200,
    "JSON content type": r =>
      (r.headers["Content-Type"] || "").includes("application/json"),
    "matched id": r =>
      r.status === 200 && r.json("id") === id
  });

  unexpected.add(!ok);
}
~~~

**Lưu ý:** URL/token phải do operator cấp trong môi trường test; **PRODUCT_IDS** là fixture synthetic và URL base phải được kiểm soát, không trỏ tới production ngoài chủ đích. **http_req_failed** trong k6 tuân response callback mặc định/cấu hình; các status 4xx chủ động thử có thể được đánh dấu failed, nên lập policy classification rõ cho từng scenario. Với demo này chỉ dự kiến HTTP 200, vì vậy status khác được xem là lỗi.

**Điểm cần đọc trong report:**

- Achieved RPS so với **25 req/s** thực tế, dropped_iterations và VUs được cấp.
- p95/p99 khi đã warm-up, không chỉ mean latency.
- Network/client timeouts và các 4xx/5xx được phân loại; **unexpected** là custom metric cho kiểm contract.
- CPU/load của máy phát tải: generator yếu có thể khiến kết quả quá lạc quan.
- Server CPU/GC, DB pool, thread/connection pending, retries và downstream metrics tại cùng time window.

**Không dùng một response body lớn rồi log đầy đủ body/token khi có lỗi**; masking và hạn chế cardinality tags là yêu cầu bắt buộc.

## 5. Định nghĩa correctness invariants dưới tải

Performance vượt SLO mà trả dữ liệu sai vẫn là **thất bại**. Một plan cần cả **correctness oracle** và phương pháp đo không tự phá dữ liệu:

| Hành vi | Bất biến sau load/fault |
| --- | --- |
| POST orders cùng Idempotency-Key | **Một** business order cho cùng tenant/operation/fingerprint, không duplicate charge |
| POST orders với key khác | Các requests hợp lệ tạo operations riêng, không nhầm key giữa tenant |
| PATCH với stale If-Match | **412** và không ghi đè revision mới |
| GET If-None-Match | **304** chỉ khi validator đúng selected representation và còn authorized |
| GET paginated | Không rò tenant; size ≤ limit; cursor/sort đúng hợp đồng |
| 401/403/404 | Không phát hành dữ liệu hoặc mutation trái quyền |
| Timeout sau khi gửi POST | Outcome có thể không chắc; reconcile theo operation ID/idempotency |
| 429 | Không vượt giới hạn/quota được công bố, Retry-After khi hợp đồng yêu cầu |
| Cache/recovery | Không phục vụ dữ liệu tenant khác hoặc stale quá chính sách |
| Jobs và event/outbox | Không mất công việc đã commit; at-least-once phải có dedup downstream |

Với các writes, kiểm **DB/order ledger/payment ledger**, không chỉ đếm HTTP 201. Tạo các **unique test business IDs**, kiểm dữ liệu tồn tại trước/sau và chạy cleanup an toàn. Với concurrency, dùng **barrier** để hai requests cạnh tranh cùng revision, sau đó xác nhận chỉ một update commit khi contract yêu cầu CAS.

## 6. Fault injection: thiết kế giả thuyết trước khi gây lỗi

**Fault injection** là thí nghiệm chủ động tạo điều kiện bất lợi có kiểm soát, không phải xóa ngẫu nhiên hạ tầng rồi xem log. Mỗi kịch bản phải ghi:

1. **Steady-state baseline:** trước lỗi, endpoint nào đạt SLO và resource metrics thế nào.
2. **Giả thuyết:** ví dụ Inventory timeout → checkout fail-fast, GET catalog vẫn giữ p95.
3. **Fault boundary:** chính xác container, network link, dependency, pool hoặc node nào bị ảnh hưởng.
4. **Blast radius:** tenant/namespace/environment, số request và thời gian tối đa.
5. **Safety/abort:** trigger dừng ngay nếu vượt error budget, dữ liệu sai quyền, charge trùng hoặc ảnh hưởng hệ thống ngoài scope.
6. **Đo trong lỗi:** actual error/status, latency, retry count, circuit state, backlog và invariants.
7. **Khôi phục:** bỏ fault, chờ drain, đo thời gian phục hồi và kiểm dữ liệu.
8. **Cleanup và báo cáo:** tắt proxy/flag, reset fixtures, lưu metric/traces và gắn experiment ID.

**Chỉ tiêm lỗi trên môi trường được phép, có người sở hữu và khả năng hoàn tác**. Ưu tiên staging/test namespace, data synthetic và bounded experiments; tránh tác động vào payment thật hoặc shared infrastructure khi không có quyền.

### 6.1. Các lớp lỗi cần bao phủ

| Lỗi tiêm | Cơ chế/thành phần ví dụ | Kỳ vọng đúng |
| --- | --- | --- |
| HTTP latency | Inventory response delay | Timeout/circuit/bulkhead không kéo thread vô hạn |
| Connection reset | Mạng tới Inventory | Phân loại transport error, retry có điều kiện |
| 429/503 | Upstream chủ động từ chối | Tôn trọng Retry-After/retry budget, không storm |
| DB connection pool exhaustion | Test pool cạn slot | Pool acquire timeout, 503/fail-fast, không deadlock |
| DB restart/failover | Một DB node được phép trong staging | Không mất commit theo DB guarantee; reconnect/health phục hồi |
| Redis cache outage | Cache optional | Fallback DB có giới hạn hoặc fail theo policy, không avalanche |
| Rate limiter store outage | Redis chính sách quota | **Không tự fail-open** cho endpoint nhạy cảm |
| Message broker outage | Queue async | Không báo 202 nếu chưa có guarantee nhận việc theo contract |
| Pod/node restart | Một instance trong nhóm | Readiness/load balancing/retry không rò dữ liệu |
| Packet loss/bandwidth cap | Fault proxy | Deadline và cancellation có hiệu lực |
| Certificate/token failure | TLS/JWT setup test | 401/403/TLS fail-closed, không vô hiệu security |
| Stale cache/permission revoke | Tenant/ACL fixture | Không trả dữ liệu đã bị thu hồi quyền |

**Không đánh đồng HTTP 408 với timeout ở HTTP client.** Khi Java client không nhận response, nó có thể ném exception; **504** thường do gateway khi upstream quá hạn; **503** do dịch vụ không thể phục vụ đúng contract; **429** do hạn mức. Test phải biết tầng nào tạo status.

## 7. Kiến trúc phục hồi: timeout, retry, bulkhead, circuit và idempotency

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant G as Gateway
    participant O as Order API
    participant B as Bulkhead / Circuit
    participant I as Inventory API
    participant D as DB / Outbox
    C->>G: POST /orders + Idempotency-Key
    G->>O: Authenticated request
    O->>B: Acquire bounded slot, apply deadline
    B->>I: Reserve stock (bounded attempts)
    alt Dependency unavailable
        I--xB: Timeout / 503
        B-->>O: Classified failure
        O-->>C: Controlled error/outcome unknown
    else Reservation accepted
        I-->>B: Reservation outcome
        O->>D: Commit order + outbox atomically
        O-->>C: 201 + Location
    end
~~~

- **Timeout:** giới hạn thời gian chờ kết nối, pool, response và operation; tổng deadline phải bao retries/backoff. Timeout của client **không** chứng minh upstream đã hủy side effect.
- **Retry:** chỉ retry lỗi transient khi method/operation an toàn và còn deadline, với backoff/jitter và giới hạn attempts. Retry nhiều tầng có thể nhân tải.
- **Circuit breaker:** dừng gọi dependency lỗi liên tục, cần half-open probes/restore; không thay quyền hoặc data validation.
- **Bulkhead:** giới hạn concurrent calls/queue cho dependency để Inventory chậm không làm hỏng toàn Order API.
- **Fallback/degrade:** chỉ có ở dữ liệu/tính năng thực sự optional; **không giả tồn kho/giá/thanh toán** để tạo 201.
- **Idempotency/outbox:** ngăn nghiệp vụ trùng khi response mất và bảo toàn công việc đã commit; vẫn cần kiểm downstream dedup khi delivery at-least-once.
- **Admission control/rate limiting:** 429/503 theo hợp đồng, không giữ request chờ vô hạn.

Mục tiêu fault injection không phải buộc mọi lỗi thành HTTP 200: **fail fast, fail correctly và recover cleanly** tốt hơn 200 với dữ liệu sai hoặc side effect trùng.

## 8. Đọc latency và saturation như một chuỗi nguyên nhân

Khi p99 tăng, không nên lập tức tăng timeout. Độ trễ của một HTTP request có thể gồm:

~~~text
Client total latency
  = DNS/TLS (khi có) + gateway queue/routing
  + HTTP connection acquire/connect
  + Spring servlet thread/admission
  + application logic + DB pool wait/query
  + Inventory/Payment calls + retries/backoff
  + serialization + response download
~~~

Đây là **sơ đồ phân rã để điều tra**, không phải công thức cộng chính xác cho các bước chạy song song. Với HTTP/2 và WebFlux, số streams hoặc event-loop utilization mới là số đo bổ sung cần thiết.

| Triệu chứng dưới tải | Dữ liệu cần so sánh | Giả thuyết |
| --- | --- | --- |
| p95 ổn, p99 đột biến | GC pauses, DB locks, network retransmits | Tail latency do contention hoặc pause |
| RPS không đạt target open model | dropped_iterations, generator CPU/VUs | Load generator không đủ công suất |
| p95 tăng cùng DB pending | Hikari active/idle/pending, query timings | Pool nhỏ hoặc query/transaction quá dài |
| HTTP pool pending tăng | Leased/available, upstream latency | Connection leak, max per route hoặc upstream chậm |
| Errors tăng sau retry | Attempts per logical operation, 429/503 | Retry storm, nhiều tầng retry |
| CPU thấp nhưng latency cao | Thread dumps, blocked I/O, DB locks | Chờ tài nguyên thay vì CPU-bound |
| DB/Redis khôi phục nhưng 5xx còn cao | Circuit half-open, stale sockets, queue age | Chậm phục hồi, state chưa được reset |
| GET nhanh nhưng POST thất bại | Lock contention, idempotency store, payment | Nút nghẽn theo operation, không phải toàn API |

Theo **Little's Law**, số operation in-flight trung bình xấp xỉ **throughput × latency** ở chế độ ổn định. 100 request/s với 0,2 giây trung bình cần ~20 request đang xử lý; cùng arrival rate nhưng latency lên 1 giây có thể làm concurrency lên ~100. Đây là lý do **chậm upstream có thể khiến pool và thread cạn trước khi CPU cao**.

**Không nhầm metrics:**

- **Server processing time** bỏ qua thời gian chờ gateway/network của client.
- **http_req_duration** trong k6 có phạm vi đo riêng của công cụ; DNS/TLS/blocked/connect có các timing metrics riêng. Đọc tài liệu của version đang dùng, không coi một metric duy nhất bao mọi pha.
- **Histogram p95/p99** nên xuất từ các bucket phù hợp với SLO; tránh lấy trung bình của p95 từ nhiều pod, vì trung bình percentiles không phải percentile toàn cụm.
- **429 do test quota chủ động** phải báo riêng trong kết quả; vẫn là request không được phục vụ và cần có kế hoạch quota đúng sản phẩm.

## 9. Java/Spring: giới hạn thời gian, pool và ranh giới lỗi

Sử dụng Spring Boot 3 với Apache HttpClient 5 cho **RestClient** đồng bộ. Ví dụ để minh họa cách cấu hình cả **pool wait, connect và response**; các giá trị phải được hiệu chỉnh bằng load test thật.

~~~java
@Configuration
public class InventoryHttpConfiguration {
    @Bean(destroyMethod = "close")
    CloseableHttpClient inventoryApacheClient() {
        ConnectionConfig connection = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofMilliseconds(250))
            .setSocketTimeout(Timeout.ofMilliseconds(500))
            .setTimeToLive(TimeValue.ofMinutes(5))
            .build();

        PoolingHttpClientConnectionManager pool =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(40)
                .setMaxConnPerRoute(15)
                .setDefaultConnectionConfig(connection)
                .build();

        RequestConfig request = RequestConfig.custom()
            .setConnectionRequestTimeout(Timeout.ofMilliseconds(100))
            .setResponseTimeout(Timeout.ofMilliseconds(500))
            .build();

        return HttpClients.custom()
            .setConnectionManager(pool)
            .setDefaultRequestConfig(request)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }

    @Bean
    RestClient inventoryRestClient(CloseableHttpClient inventoryApacheClient) {
        var factory = new HttpComponentsClientHttpRequestFactory(
            inventoryApacheClient);
        return RestClient.builder()
            .baseUrl("http://inventory.test.internal")
            .requestFactory(factory)
            .build();
    }
}
~~~

**Các import cần thiết** thuộc **org.apache.hc.client5.http.\***, **org.apache.hc.core5.\***, **org.springframework.web.client.RestClient** và **org.springframework.http.client.HttpComponentsClientHttpRequestFactory**. API của Apache 5 thay đổi theo minor versions; biên dịch với một tập dependency nhất quán. Host là **địa chỉ test giả định**, không phải endpoint để tự động truy cập bên ngoài.

**Các giới hạn không thay thế nhau:**

- **Connect timeout** chỉ giới hạn pha connect mới theo transport; reuse connection không chạy lại connect.
- **Connection request/acquisition timeout** chặn chờ pool vô hạn; cạn pool có thể do leak response hoặc upstream chậm, không nhất thiết do network down.
- **Response/read timeout** phụ thuộc semantics thư viện và không chắc là deadline cho cả body được stream chậm nhưng liên tục.
- **Overall operation deadline** cần đặt ở tầng orchestration để bao gồm queue, connect, body, retries và backoff.
- **Bean lifetime**: client singleton trong app; đóng response đúng cách ở các code paths; chỉ đóng client khi app shutdown.

Không cấu hình **retries tự động vô điều kiện** cho POST tạo đơn. Kiểm thư viện hoặc proxy có retry mặc định không, và bảo đảm **Idempotency-Key** được server lưu/dedup đúng scope nếu operation cần replay an toàn.

### 9.1. Spring service giữ nghiệp vụ và bảo mật trong lúc fault

Ví dụ domain logic minh họa:

~~~java
@Service
public class OrderService {
    private final AuthorizationPolicy authorization;
    private final PricingService pricing;
    private final InventoryClient inventory;
    private final OrderRepository orders;

    public OrderService(AuthorizationPolicy authorization,
                        PricingService pricing,
                        InventoryClient inventory,
                        OrderRepository orders) {
        this.authorization = authorization;
        this.pricing = pricing;
        this.inventory = inventory;
        this.orders = orders;
    }

    public OrderReceipt create(
            Caller caller, CreateOrderRequest request, String key) {
        authorization.requireCreateOrder(caller, request);

        // Giá phải lấy từ nguồn được ủy quyền, không tin body.
        Money price = pricing.requireCurrentPrice(request.sku());

        // Nếu Inventory không xác nhận: KHÔNG tạo order 201 giả.
        ReservationOutcome reservation = inventory.reserve(
            caller.tenantId(), request.sku(), request.quantity(), key);

        return orders.createOnce(
            caller.tenantId(), caller.userId(),
            request, price, reservation, key);
    }
}
~~~

**Lưu ý:** đây là skeleton kiến trúc, **không tự đảm bảo transaction nguyên tử trên Inventory và DB**. Đối với workflow nhiều dịch vụ, cần orchestration/compensation, outbox và idempotency ở từng boundary. Nếu Inventory commit nhưng response mất, kết quả **chưa xác định**; không giả ReservationOutcome thất bại để tạo reservation mới với key khác.

**Trong test dưới tải:**

- Caller thiếu JWT hoặc tenant không hợp lệ → 401/403/404, **không** bỏ qua quyền chỉ vì AuthZ service chậm.
- Inventory lỗi → không tạo order hoàn tất bằng tồn kho phỏng đoán; response phù hợp contract, có thể 503 nếu dependency quan trọng không khả dụng.
- Payment callback có thể đến lặp → dedup event/order, không charge hai lần.
- Nếu có recommendations/ratings tùy chọn, được degrade có metadata; giá/tồn kho/thanh toán **không được** degrade sang giá giả hoặc thành công giả.

## 10. Fault injection bằng MockWebServer, WireMock và Toxiproxy

Nên dùng một **dải cấp độ** thử nghiệm thay vì luôn tác động vào hạ tầng thật:

| Công cụ/kỹ thuật | Lỗi mô phỏng tốt | Giới hạn |
| --- | --- | --- |
| **MockWebServer** | HTTP status, slow headers, disconnect/body delay theo API phiên bản | Không thay thực tế DNS, LB hoặc DB failover |
| **WireMock** | Stub HTTP theo request, delay, scenario state transitions, fault responses | Không chứng minh client có behavior đúng với mọi loại network failure |
| **Toxiproxy** | Latency, bandwidth cap, connection cut qua TCP proxy | Cần route dependency qua proxy, kiểm hành vi phiên bản |
| **Testcontainers** | DB/Redis/broker thực trong container thử nghiệm | Restart container khác failover production multi-node |
| **Kubernetes staging** | Restart pod/route/liveness/ready, traffic trên cụm thử nghiệm | Cần quyền, guardrail, giới hạn blast radius |
| **Service mesh chaos support** | Delay/drop/fault trên tuyến dịch vụ đã được phép | Phụ thuộc cấu hình mesh, phải audit targeting |

### 10.1. Ví dụ JUnit: timeout headers rồi phục hồi

Đoạn test JUnit minh họa một **JDK HttpClient** gọi upstream local MockWebServer; không cần làm sập môi trường. Kết hợp test này với bài HTTP integration của Spring để kiểm full order policy.

~~~java
@Test
void slowHeadersTimeoutThenHealthyRequestSucceeds() throws Exception {
    MockWebServer upstream = new MockWebServer();
    upstream.enqueue(new MockResponse()
        .setHeadersDelay(2, TimeUnit.SECONDS)
        .setBody("{\"available\":true}"));
    upstream.enqueue(new MockResponse()
        .setBody("{\"available\":true}"));
    upstream.start();

    try {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(300))
            .build();

        URI endpoint = URI.create(
            upstream.url("/api/v1/availability").toString());

        HttpRequest slow = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofMillis(200))
            .GET()
            .build();

        assertThrows(HttpTimeoutException.class,
            () -> client.send(
                slow, HttpResponse.BodyHandlers.ofString()));

        HttpRequest recovered = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            recovered, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("available"));
    } finally {
        upstream.shutdown();
    }
}
~~~

**Imports:** JUnit Jupiter, MockWebServer/MockResponse, Java **java.net.http.\***, java.time.Duration, java.net.URI, TimeUnit. Tùy version MockWebServer, API stub và behavior khi client hủy request có thể khác; test có thể cần **latch/fault control** để tránh flaky trên CI. Việc local server trả response chậm chỉ chứng minh **request timeout**, **không chứng minh TCP connect timeout**. Fault connect cần proxy/network injection có kiểm soát.

### 10.2. Fault injection hợp đồng: không retry nhầm

Nếu một mock upstream lần lượt trả 503 rồi 200, test **GET read** có thể cho phép tối đa một retry theo budget. Với **POST tạo reservation**, phải chứng minh không retry khi unknown outcome trừ khi **upstream có idempotency contract**, và mọi retry giữ **cùng operation ID/key**.

~~~text
GET Inventory: 503 -> bounded retry (còn deadline?) -> 200
POST Reserve: bytes sent -> response lost -> UNKNOWN OUTCOME
              -> reconcile by business ID / same idempotency key
              -> never create new key blindly
~~~

Một response **503** từ upstream là HTTP response thực; **connection reset hoặc socket timeout** có thể xảy ra trước khi nhận status. Assert error mapper và audit phân biệt hai tình huống, vì client sẽ có thông tin khác nhau để quyết định retry.

### 10.3. Inject lỗi tại gateway mà vẫn bảo toàn security

Với đường public **client → gateway → Spring**:

- Gateway tự tạo **502/503/504**: kiểm response không lộ stack trace/IP nội bộ, có correlation ID và CORS headers đúng cho origin được phép.
- Nếu gateway không đến được AuthZ/JWT provider và không có policy offline được phê duyệt, **không mở quyền tùy tiện**.
- Preflight CORS OPTIONS không mang bearer token vẫn có thể được phục vụ theo allowlist, nhưng request thực luôn qua authentication/authorization.
- Gateway 429 do rate limit không nên khiến client đồng loạt retry ngay; kiểm **Retry-After** khi có trong hợp đồng.
- Khi một pod bị kill, readiness không được tiếp tục route request tới pod không còn phục vụ; đo khoảng thời gian lỗi trong lúc endpoints chuyển trạng thái.

## 11. Recovery: đo từ thời điểm nào và thế nào mới là phục hồi?

**Recovery time** không đơn giản bằng thời gian process restart. Một hệ thống có thể báo health UP nhưng DB connections chưa phục hồi, circuit breaker còn open hoặc hàng nghìn messages vẫn nằm trong queue.

Một mô hình đo:

~~~text
T0: baseline ổn định
T1: bật fault (Inventory timeout, DB restart...)
T2: lỗi được gỡ / dependency healthy
T3: service chấp nhận request và đáp ứng min contract
T4: latency/error/queue/backlog trở lại ngưỡng ổn định
T5: reconciliation/data integrity kiểm chứng hoàn tất
~~~

Có thể báo **time to minimum service = T3−T2**, **time to steady-state recovery = T4−T2**, **time to data reconciliation = T5−T2**. Không gộp các thước đo ấy vào một số "recovered in 5s" thiếu định nghĩa.

### 11.1. Định nghĩa recovery gate cụ thể

Ví dụ recovery gate cho Order API:

1. Trước fault: trong **60 giây** ổn định, p95 của GET orders dưới 300 ms, 5xx bất ngờ dưới 0,5%.
2. Inject Inventory 503 có kiểm soát trong **30 giây** tại namespace test, không ảnh hưởng Payment thật.
3. Trong fault: POST order hợp lệ fail-fast theo contract, không tạo đơn hoàn tất giả; GET orders không liên quan vẫn đạt SLO.
4. Gỡ lỗi ở T2; bắt đầu đo thời gian recover.
5. Chỉ coi **T4** đạt khi trong **hai cửa sổ liên tiếp mỗi cửa sổ 15 giây**: error/latency trở về ngưỡng, pending queue thấp và circuit về CLOSED khi phù hợp.
6. Tại T5: kiểm DB/order ledger không duplicate/missing, idempotency key không bị sử dụng chéo tenant và cleanup đúng.

Các ngưỡng **30 s/15 s** chỉ là ví dụ; chọn theo SLO và khả năng đo. Trạng thái breaker có thể phục hồi theo nửa mở và số request probe; không ép breaker lập tức CLOSED bằng reset thủ công nếu làm mất ý nghĩa test.

### 11.2. RPO và correctness

**RPO=0** chỉ có ý nghĩa với tập dữ liệu và durability guarantees được kiểm. DB đã xác nhận commit nhưng failover làm mất bản ghi là lỗi nghiêm trọng; message đã ghi outbox nhưng chưa gửi phải được delivery sau recovery và dedup downstream. Những requests đang in-flight lúc fault có thể có outcome UNKNOWN; cần đối soát bằng **operation ID/idempotency store**.

Đối với **eventual consistency**, xác định rõ thời gian hội tụ và nguồn sự thật. Không gọi API healthy chỉ vì 200 trong khi job/export/event còn stuck ở QUEUED hoặc dữ liệu chưa được lập chỉ mục đúng.

## 12. Kiểm toán bảo mật và dữ liệu khi tiêm lỗi

**Lỗi hệ thống không được biến thành đường vượt quyền.** Các ca bắt buộc nên có:

- Tenant A yêu cầu GET/PATCH order tenant B khi Redis/AuthZ bị lỗi → **không trả hoặc sửa dữ liệu tenant B**.
- Token hết hạn hoặc signature sai → vẫn từ chối, kể cả upstream identity provider mất kết nối và ứng dụng đang ở degraded mode.
- Feature flag tắt recommendations không được tắt **permission check, validation, fraud rule hoặc audit bắt buộc**.
- Cache fallback chỉ dùng dữ liệu trong **tenant/permission scope**, có TTL và invalidation khi revoke.
- Retry khi POST timeout không làm lặp charge; idempotency store không dùng shared key toàn hệ thống.
- Request bị 429/503 không được trả body chứa SQL, private hostname, token hoặc signed URLs.
- Nếu có signed download URL, fault/retry/cache không được kéo dài hiệu lực ngoài TTL hoặc trả URL cho user khác.
- Test logs/metrics không dùng **Authorization, Cookie, raw payload/PII** làm labels; load generator không dump secrets vào console.

Không có lý do hợp lệ để **disable JWT, TLS certificate validation hoặc CSRF protection** chỉ nhằm đạt throughput cao trong môi trường cần các kiểm soát ấy. Test phải đo chi phí thực của security chain.

## 13. Observability trong một fault experiment

Cần đồng bộ **experiment ID, timestamp, trace/correlation ID** giữa load generator, gateway, Spring, DB và dependencies.

| Lớp | Tín hiệu cần thu | Vì sao |
| --- | --- | --- |
| Client/k6 | Arrival rate, achieved RPS, p95/p99, 4xx/5xx, timeout, dropped iterations | Đo trải nghiệm và tải thực phát ra |
| Gateway | Upstream latency/status, retries, 429/502/504, active connections | Xác định lỗi ở biên |
| Spring HTTP | Route/method/status, busy threads, queues, request duration | Phân biệt admission và business logic |
| HTTP client pool | Active/idle/pending/connection timeout | Phát hiện kết nối cạn hoặc leak |
| JVM | CPU, heap, GC pauses, thread count | Saturation và memory/GC leak |
| PostgreSQL | Active/idle connections, slow queries, locks, replication lag | DB bottleneck/consistency |
| Redis/queue | Errors, latency, pending jobs, consumer lag | Cache/rate limit và backlog |
| Resilience layer | Circuit state, retries, bulkhead rejects, timeouts | Chứng minh guardrails hoạt động |
| Domain | Orders created, duplicates, payments charged, outbox pending | Đảm bảo correctness |
| Security | Denials, cross-tenant access attempts, auth errors | Đảm bảo fail-closed dưới lỗi |

Metrics cần nhóm theo **route template, dependency, status class, environment, experiment ID**, không dùng URL/ID người dùng làm high-cardinality labels. Không lưu bearer tokens hoặc PII trong traces. So sánh **baseline → fault window → recovery window**, giữ marker chính xác T1/T2/T3/T4.

**Red flags**: request success rate có vẻ tăng vì API bắt đầu trả 200 fallback cho lỗi bắt buộc; breaker mở nhưng retry attempts vẫn tăng; queue tiếp tục tăng sau khi fault được gỡ; DB hồi phục nhưng idempotency ledger phát sinh duplicate; canary pod ready nhưng tail latency vẫn cao.

## 14. Báo cáo thí nghiệm theo dữ liệu, không chỉ kết luận PASS

Một bảng báo cáo tối thiểu:

| Trường | Nội dung |
| --- | --- |
| **Experiment ID/date/owner** | Mã lần chạy, người chịu trách nhiệm, môi trường |
| **Git commit & config** | Version app, schema, gateway rules, client timeout/pool |
| **Traffic profile** | Arrival rate, duration, mix, tenants, payload distributions |
| **Baseline** | p95/p99, RPS, unexpected errors, saturation |
| **Fault** | Dependency/link, kiểu lỗi, thời điểm bắt đầu/kết thúc, blast radius |
| **Guardrails** | Abort threshold, rate/tenant cap, rollback path |
| **During fault** | Status/circuit/timeout/fallback, HTTP + domain invariants |
| **Recovery** | T2/T3/T4/T5, steady-state criteria, backlog drain |
| **Correctness** | Số orders, idempotency duplicates, auth breaches, data loss |
| **Decision** | PASS/FAIL/INCONCLUSIVE, links tới dashboard và follow-ups |

**Inconclusive** là trạng thái hợp lệ khi load generator không đạt traffic target, metrics thiếu, fault không thực sự được áp dụng hoặc môi trường bị nhiễu. Đừng báo PASS khi chưa tạo được lỗi hoặc chỉ đo HTTP 2xx trong lúc các checks domain thất bại.

Một kết luận mẫu: **"Ở 25 req/s trong hai phút, p95 GET catalog đạt; khi Inventory giả lập 503 trong 30 giây, POST orders fail-fast không tạo bản ghi trùng; sau khi gỡ fault, steady-state đạt trong hai cửa sổ 15 giây; không phát hiện data loss qua đối soát ID."** Đây chỉ là **mẫu cấu trúc báo cáo**, không phải kết quả đo của hệ thống thực.

## 15. Ma trận kiểm thử tải, fault và phục hồi

Một suite tốt có **baseline trước fault, bằng chứng trong fault và tiêu chí sau khi gỡ fault**. Các ca dưới đây chỉ dùng test tenant, test credentials và môi trường đã được phép.

| ID | Thử nghiệm | Kết quả HTTP và hành vi bắt buộc |
| --- | --- | --- |
| L01 | GET product 25 req/s trong 2 phút | Đạt target RPS, p95/p99, 0 dropped iterations theo plan |
| L02 | Tăng dần arrival rate | Xác định điểm saturation, không làm cạn tài nguyên ngoài scope |
| L03 | Spike rồi hạ tải | Queue drain, latency/error trở lại ngưỡng |
| L04 | Soak lâu với connection reuse | Không leak socket/thread/heap; idle pool ổn |
| L05 | 50% cold vs 50% warm cache | Đo rõ latency/tỷ lệ cache; không đưa cache hit giả |
| L06 | GET list limit/cursor nhiều tenant | Không lộ record tenant khác, page size đúng |
| L07 | GET If-None-Match cache hit | 304 chỉ khi ETag match và còn authorized |
| L08 | Hai PATCH cùng If-Match | Chỉ một commit theo policy; stale request 412 |
| F01 | Inventory headers chậm | Timeout bounded; không giữ servlet threads mãi |
| F02 | Inventory trả 503/429 | Retry budget/Retry-After, không cascade |
| F03 | Network reset sau POST reserve | Không duplicate; outcome UNKNOWN được reconcile |
| F04 | DB connection pool exhausted | Fail-fast, không deadlock, hồi phục khi connection trả |
| F05 | PostgreSQL restart/failover test | Kết nối hồi phục, kiểm không mất committed orders |
| F06 | Redis cache hỏng | Fallback/503 đúng policy; không cross-tenant cache leak |
| F07 | Redis rate limiter hỏng | Không tự vô hiệu hạn mức cho endpoint nhạy cảm |
| F08 | Message broker tạm mất | Không mất outbox/job đã commit; consumer dedup |
| F09 | One pod restart | Readiness/load-balancing đúng, không kéo dài outage |
| F10 | Gateway sinh 502/504 | Problem Details, CORS và correlation an toàn |
| F11 | JWT/ACL dependency không khả dụng | Fail-closed, không chuyển 403 thành 200 |
| F12 | Request body lớn/slow stream | Size cap, timeout và memory trong giới hạn |
| R01 | Gỡ lỗi Inventory | Steady-state recovery trong cửa sổ đã định |
| R02 | Circuit half-open/close | Không bắn burst retries khi upstream vừa khỏe |
| R03 | Queue backlog sau fault | Drain trong mục tiêu, không duplicate delivery |
| R04 | Cache sau dữ liệu/ACL đổi | Không phục vụ stale/forbidden data |
| R05 | Kill app trong POST cùng key | Replay/reconcile chỉ một order/charge |
| R06 | Recovery rồi chạy lại baseline | SLO và correctness không giảm âm thầm |

**Mỗi ca phải có expected status và authoritative data checks**, không chỉ assert test tool không crash. Nếu fault không thực sự được tạo, ca đó **INCONCLUSIVE**, không phải PASS.

### 15.1. Java + REST Assured kiểm correctness sau fault

Ví dụ test integration **minh họa** dùng WireMockServer giả lập Inventory và REST Assured qua HTTP Spring Boot RANDOM_PORT. Test fixture phải cấu hình InventoryClient trỏ đến đúng stub, token có chữ ký hợp lệ và DB độc lập.

~~~java
@Test
void inventory503NeverCreatesCompletedOrder() {
    inventoryStub.stubFor(
        post(urlEqualTo("/api/v1/reservations"))
            .willReturn(aResponse().withStatus(503)));

    String key = UUID.randomUUID().toString();
    long before = orderRepository.countByTenantId(tenantA);

    given()
        .spec(apiSpec(port))
        .auth().oauth2(tenantAToken)
        .contentType(ContentType.JSON)
        .header("Idempotency-Key", key)
        .body("""
            {"sku":"SYN-KB-001","quantity":1}
            """)
    .when()
        .post("/orders")
    .then()
        .statusCode(503)
        .contentType("application/problem+json")
        .body("code", equalTo("INVENTORY_UNAVAILABLE"));

    assertEquals(before,
        orderRepository.countByTenantId(tenantA));
}
~~~

**Cần imports/fixtures** REST Assured, JUnit, WireMock, Spring repository và API route; 503/code là **contract giả định**, phải sửa đúng hành vi app. Để test side effects mạnh hơn, kiểm ledger theo **test order ID/idempotency key**, không chỉ count (count có thể không đổi vì một row bị sửa sai). Nếu workflow tạo trạng thái **PENDING** hợp lệ khi Inventory down, không nên assert tuyệt đối "không có row"; thay bằng bất biến **không có order COMPLETED, không charge và có eventual reconciliation** theo contract.

**Chú ý transaction:** test HTTP qua RANDOM_PORT chạy trong server thread/transaction riêng; **@Transactional trên JUnit method không tự rollback các commits của endpoint**. Phải seed và cleanup bằng fixture/scope riêng hoặc DB container.

### 15.2. Kiểm tra phục hồi sau khi bỏ fault

Sau ca Inventory 503:

1. Gỡ stub lỗi, trả 200 với reservation outcome hợp lệ.
2. Gửi GET health/readiness **và** một POST tạo order test với key mới.
3. Theo dõi **nhiều cửa sổ ổn định** thay vì xem một response 200 là đã recover.
4. Reconcile orders đã xử lý trong fault, không retry bằng **key mới** cho transaction outcome UNKNOWN.
5. So p95/p99, queue length, circuit state, retries và domain ledger với baseline.
6. Dọn synthetic orders, expired idempotency entries theo fixture policy, tắt fault/proxy.

**Không retry không giới hạn** trong assertion: polling có deadline và điều kiện thất bại rõ; nếu quá thời gian thì FAIL và lưu diagnostics đã redact.

## 16. OpenAPI, HTTP contract và resilience test

OpenAPI 3.1 không mô tả toàn bộ timeouts, thread pools và recovery gates, nhưng cần công bố **status/headers** mà client thực sự sẽ thấy khi hệ thống quá tải hoặc dependency hỏng.

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      security: [{ bearerAuth: [] }]
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: { type: string, minLength: 1, maxLength: 128 }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [sku, quantity]
              properties:
                sku: { type: string }
                quantity: { type: integer, minimum: 1 }
      responses:
        '201':
          description: Tạo đơn thành công
          headers:
            Location:
              schema: { type: string }
        '400': { description: Dữ liệu không hợp lệ }
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '409': { description: Business conflict hoặc idempotency conflict }
        '429':
          description: Vượt rate quota
          headers:
            Retry-After:
              schema: { type: string }
        '503':
          description: Không thể đáp ứng do dependency không khả dụng
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
  /api/v1/orders/{id}:
    get:
      operationId: getOrder
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
        - in: header
          name: If-None-Match
          schema: { type: string }
      responses:
        '200': { description: Representation theo quyền hiện tại }
        '304': { description: ETag match, không có body }
        '404': { description: Không có order được phép xem }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string }
        title: { type: string }
        status: { type: integer }
        code: { type: string }
~~~

**Ví dụ là đoạn contract rút gọn**, cần bổ sung security scopes, 412/428 cho PATCH, 502/504 nếu public gateway phát các mã ấy, error schemas và response bodies thật. Hợp đồng **không cam kết mọi retry đều tạo response 201 giống nhau** trừ khi hệ thống xác định replay semantics như vậy. Test rate limit 429 chỉ assert Retry-After khi contract cam kết hoặc gateway thực sự phát.

## 17. CI và độ tin cậy của kết quả load test

Không chạy hàng nghìn RPS trên shared CI runner rồi so với máy staging khác hôm trước. Nên chia test thành nhiều tầng:

| Pipeline | Thời điểm | Nội dung |
| --- | --- | --- |
| **PR smoke** | Mỗi pull request | Contract/security/HTTP + fault nhỏ và nhanh, không phá hạ tầng |
| **Integration nightly** | Theo lịch | DB/container thật, timeout, retry, pool exhaustion, idempotency race |
| **Capacity/stress** | Theo lịch hoặc trước release lớn | Môi trường cô lập có cấu hình ổn định, arrival rate tăng có trần |
| **Fault-under-load** | Trước thay đổi resilience quan trọng | Kịch bản mất dependency, breaker, retry, recover, reconciliation |
| **Soak** | Theo kế hoạch | Leak/GC/connection churn trong thời gian dài |
| **Gateway staging** | Trước rollout | TLS, CORS, 429/502/504, auth, ingress/readiness |
| **Canary/monitoring** | Khi rollout được phép | So sánh SLI với baseline, có rollback gate |

**Test reproducibility:** lưu **git SHA, image digest, config, schema version, VU/generator capacity, DB size, synthetic data distribution, region, run ID, start/end timestamps** và dashboard snapshots. Không so p99 giữa lần chạy cold cache và warm cache mà không ghi nhãn.

**Gates cần đồng thời:** đạt target arrival rate, p95/p99, unexpected errors, CPU/DB pool/queue budget, correctness và recovery. Nếu **dropped_iterations > 0** hoặc load tool hết CPU, kết luận về capacity của server phải được đánh dấu **không đủ bằng chứng**.

### 17.1. Guardrails trước khi chạy trên staging

- Environment và endpoint allowlist, owner/approval, thời gian maintenance window nếu cần.
- Trần RPS/concurrency/duration, dừng khi quá error/saturation budget.
- Synthetic identities, test-only tenant/payment sandbox và cleanup.
- Fault target chính xác, blast radius nhỏ, rollback/disable route sẵn sàng.
- Tracing/metrics để đo cả **server và load generator**.
- Chống side effect thật: email/SMS/payment/provider ngoài test được mock hoặc sandbox.
- Một người chịu trách nhiệm quan sát thí nghiệm và có quyền dừng.

Đừng chạy test tới production **chỉ vì có quyền sửa source code**; vận hành cần authorization riêng của hệ thống và phù hợp cam kết với người dùng.

## 18. Những anti-pattern thường gặp

| Sai lầm | Vì sao sai | Khắc phục |
| --- | --- | --- |
| Chỉ nhìn average latency | Che tail p99 và các request kẹt | Percentiles + saturation + error distribution |
| Load test với 1 ID duy nhất | Cache che DB/ACL cost | Many IDs/tenants, cold vs warm |
| Closed VUs mà báo đạt arrival target | Tốc độ phát giảm khi server chậm | Open model và achieved-rate checks |
| Xem 200 là thành công tuyệt đối | Có thể trùng đơn/sai quyền | Domain/DB invariants |
| Retry mọi POST timeout | Duplicate reservation/charge | Idempotency + outcome reconciliation |
| Tăng pool vô hạn khi upstream chậm | Nhân số request làm upstream sập | Bulkhead, queue cap, bounded timeout |
| Inject lỗi không có abort plan | Blast radius không được kiểm soát | Scope, stop conditions, rollback |
| Gỡ fault rồi thấy một 200 | Circuit/queue/backlog chưa hồi phục | Stable windows + data reconciliation |
| Test chỉ 503 mà không đo latency | Có thể chờ rất lâu mới thất bại | Fail-fast SLO + timeout metrics |
| Bỏ filter/JWT để đạt RPS | Không đo cấu hình thật và có rủi ro | Test security chain thực |
| Bật lỗi trước khi đo baseline | Không biết thay đổi do fault hay môi trường | Baseline → fault → recovery |
| Gộp lỗi expected 4xx với lỗi hệ thống | Error rate không phản ánh SLO | Outcome classification per operation |
| Dùng sleep cố định trong async test | Flaky theo CI load | Deadline-based polling, state asserts |
| Dùng PII/token thật trong script/log | Lộ dữ liệu và khó cleanup | Synthetic data và redaction |
| Không đo tool capacity | Generator kẹt làm server trông khỏe | Check dropped iterations/CPU |

## 19. Bài thực hành: kiểm thử Order API khi Inventory lỗi

**Bối cảnh:** API được dựng trên Spring Boot 3, có PostgreSQL, Redis cache/rate limit và Inventory mock. SLO thử nghiệm: ở **25 req/s** trong **2 phút**, p95 GET products dưới **250 ms**, p95 POST orders dưới **800 ms**. Khi Inventory lỗi, POST orders không tạo order hoàn tất giả; GET catalog vẫn hoạt động; sau khi bỏ fault cần phục hồi ổn định trong giới hạn đã thống nhất.

**Bài tập (100 điểm):**

1. **Thiết kế tải – 25:** tạo k6 open-arrival scenario, phân phối IDs/tenants, đặt p95/p99/error/achieved-rate thresholds và tránh coordinated omission.
2. **Resilience – 25:** cấu hình Spring client connect/acquire/response/overall timeout; giới hạn retries/bulkhead/circuit. Chỉ ra hậu quả nếu timeout POST sau commit.
3. **Fault và recovery – 30:** dùng MockWebServer/WireMock để delay/503, Toxiproxy (nếu phù hợp) cho reset/latency; đo baseline, fault 30 giây, recovery T2→T4 qua ít nhất hai window, đối soát DB/outbox.
4. **Security/CI – 20:** hai tenant, JWT thật trong test, 401/403/BOLA, Idempotency-Key, không lộ logs; viết report PASS/FAIL/INCONCLUSIVE với links metrics.

**Gợi ý giải:** mỗi logical operation có deadline, pool và queue hữu hạn; load generator dùng synthetic test data, chỉ target staging được phép. Trong fault, xác nhận GET không phụ thuộc Inventory vẫn đạt mức tối thiểu, POST fail đúng status và không tạo transaction trùng. Sau gỡ lỗi, đo cả steady-state latency, circuit state, queue drain và số bản ghi order/outbox. Nếu generator dropped iterations hoặc fault chưa thật sự hoạt động, ghi **INCONCLUSIVE**.

## 20. Checklist và nguồn tham khảo

- [ ] Có **SLO/SLI, workload profile, target arrival rate, thời lượng, warm-up** trước khi test.
- [ ] Phân biệt baseline/stress/spike/soak và open/closed load models.
- [ ] Kiểm achieved RPS, p95/p99, error classification, saturation, generator capacity.
- [ ] Thử correctness: JWT/tenant, cursor, ETag/If-Match, POST idempotency và DB side effects.
- [ ] Fault có steady-state hypothesis, target, blast radius, thời hạn, abort và rollback.
- [ ] Timeout/acquire/retry/circuit/bulkhead không làm tăng lỗi dây chuyền.
- [ ] Không giả 200/201 khi giá/tồn kho/quyền hoặc dữ liệu bắt buộc không xác định.
- [ ] Có kịch bản 429/503/504, transport error và outcome UNKNOWN.
- [ ] Recovery được đo từ khi **gỡ fault**, theo nhiều cửa sổ ổn định và kiểm backlog.
- [ ] RPO, duplicate orders, outbox/jobs và cache/ACL được đối soát sau recovery.
- [ ] Metrics/traces/logs có experiment ID, không chứa bearer token/PII.
- [ ] CI xác nhận test đã chạy, môi trường/phiên bản có thể tái hiện và report đầy đủ.
- [ ] Không chạy stress/chaos trên mục tiêu ngoài phạm vi được ủy quyền.

**Ghi nhớ:** load test chứng minh **độ ổn định dưới mức tải xác định**; fault injection kiểm **phản ứng khi một thành phần hỏng**; recovery test chứng minh **trở lại trạng thái đúng và ổn định**. Không thể thay ba bằng một biểu đồ RPS hoặc một response 200.

### Nguồn học tập

- **RFC 9110 – HTTP Semantics**, **RFC 9111 – HTTP Caching**, **RFC 9457 – Problem Details** và **OpenAPI Specification 3.1**.
- **k6 documentation**: open-model executors, thresholds, scenario tags, dropped iterations và HTTP metrics.
- **Spring Boot Actuator / Micrometer / Spring Security**, **Apache HttpComponents Client 5**, **Resilience4j**: observability và client resilience.
- **JUnit Jupiter, REST Assured, MockWebServer, WireMock, Testcontainers, Toxiproxy**: fault/test fixtures.
- **Google SRE Workbook**: SLOs, error budgets, overload, disaster recovery; **OWASP API Security Top 10** cho BOLA và resource consumption.
