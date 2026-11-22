# Ranh giới giữa kiểm thử chức năng, kiểm thử tải và thử nghiệm gây lỗi có kiểm soát

Một endpoint Spring Boot trả HTTP `200` trong 15 test cases có nghĩa là nó **đã vượt qua những kịch bản chức năng được kiểm**. Kết quả ấy **không chứng minh** endpoint duy trì p95 latency dưới 500 ms ở 100 request/giây, và càng không chứng minh ứng dụng phục hồi sau khi downstream mất kết nối, database failover hoặc một pod bị kill. Ngược lại, một load test đạt p95 tốt có thể vẫn trả dữ liệu sai, ghi đơn hàng hai lần hoặc âm thầm dùng fallback sai nghiệp vụ. Một lần ngắt mạng chủ động làm hệ thống “còn chạy” cũng không chứng minh toàn bộ hợp đồng API, an toàn dữ liệu và mục tiêu hiệu năng đều đúng.

Bài Knowledge **“Ranh giới giữa kiểm thử chức năng, kiểm thử tải và thử nghiệm gây lỗi có kiểm soát”** nằm trong phần **Hợp đồng và khả năng phục hồi** của module **Spring Boot – testing**. Ta sẽ thiết kế từng phương pháp theo *câu hỏi cần trả lời*, *tầng hệ thống được quan sát*, *dữ liệu đầu vào/tải/sự cố được kiểm soát* và *bằng chứng đủ để kết luận*. Ví dụ dùng **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2.x, JUnit Jupiter 5, Mockito, MockMvc, @RestClientTest, MockRestServiceServer, @SpringBootTest(RANDOM_PORT)**; kịch bản tải **k6** và thử nghiệm lỗi mạng **WireMock/Testcontainers Toxiproxy** được tách thành hoạt động độc lập có biện pháp bảo vệ.

**Quy tắc trung tâm:** *Functional tests chứng minh một hợp đồng cụ thể dưới các tiền điều kiện được chọn; load tests đo phân phối hành vi khi có nhiều yêu cầu và tài nguyên hữu hạn; fault/chaos experiments kiểm tính chịu lỗi và hồi phục khi một loại sự cố đã được chủ động áp đặt.* Không một phương pháp nào thay thế được hai phương pháp còn lại. Không gọi `@Test` có `Thread.sleep` là load test, và không gọi mock response `503` là đã chạy chaos trên hạ tầng thực.

## 1. Mục tiêu học tập

- Phân biệt **functional, contract, integration, performance/load, stress, soak, fault injection, chaos và disaster recovery tests**.
- Mô tả **điều kiện bắt đầu, tác động, quan sát và hậu điều kiện** cho từng loại test.
- Biết khi nào cần kiểm status/JSON chính xác, khi nào cần phân phối p95/p99/error-rate/throughput và khi nào cần thời gian phục hồi.
- Định nghĩa SLI/SLO và ngưỡng chất lượng mà không lấy một con số mẫu thành cam kết production.
- Thiết kế **đường chuẩn không có lỗi**, **đường suy giảm** và **đường hồi phục** để tránh kết luận sai.
- Hiểu khác biệt giữa `@WebMvcTest`, `@RestClientTest`, `@SpringBootTest(MOCK)` và `RANDOM_PORT`.
- Mô phỏng có kiểm soát downstream `503`/connection failures để test retry/fallback mà không chờ mạng thật.
- Viết Java service có giới hạn số lần retry, không retry lỗi hợp đồng không phục hồi và trả trạng thái suy giảm rõ ràng.
- Kiểm response fallback không bị đánh đồng với business success trong metrics.
- Hiểu closed model (VUs) và open model (arrival rate) của công cụ tạo tải.
- Dùng k6 `checks`, `thresholds`, p95 và `dropped_iterations` theo đúng ý nghĩa.
- Thiết kế thử nghiệm latency/connection reset/network partition bằng WireMock hoặc Toxiproxy trên hệ thống cô lập.
- Xây giới hạn blast radius, rollback, thời gian chạy, abort criteria và quyền phê duyệt trước khi gây lỗi.
- Nhận biết retry amplification, retry storm, overload, queue backlog, thread pool exhaustion, circuit breaker và bulkhead.
- Trình bày kết quả có căn cứ, phân biệt **đã chạy thực** với **mẫu hoặc kết quả kỳ vọng**.

## 2. Ba câu hỏi khác nhau

| Phương pháp | Câu hỏi chính | Kết quả quan sát | Ví dụ |
|---|---|---|---|
| **Kiểm thử chức năng** | “Với input và trạng thái xác định, hệ thống có làm đúng contract không?” | Status, JSON, header, dữ liệu, side effect, số lần gọi | Downstream 503 hai lần → response UNKNOWN/degraded, đúng số attempts |
| **Kiểm thử tải** | “Khi workload xác định chạy trong một thời gian, chất lượng phục vụ và mức sử dụng tài nguyên ra sao?” | Throughput, latency distribution, error ratio, saturation, queue, GC, drops | 10 RPS trong 30 giây ở isolated environment; p95 và business success rate |
| **Gây lỗi có kiểm soát** | “Khi thành phần X bị chậm/hỏng/mất kết nối, hệ thống phát hiện, giới hạn tác động và phục hồi thế nào?” | Degraded behavior, detection, retry/CB/bulkhead, recovery time, data integrity | Tiêm 1,2 giây latency lên kết nối test, sau đó gỡ toxic và xác minh hồi phục |

Các phương pháp có thể kết hợp, ví dụ **chạy workload nhỏ trong khi ngắt kết nối downstream**. Nhưng khi kết hợp phải mô tả cả *tải* và *lỗi được gây ra*. Một test chỉ request một lần không chứng minh chịu tải; một load test không inject sự cố không chứng minh phục hồi; một chaos test trả 200 nhưng mất dữ liệu cũng không đạt.

### 2.1. Một định nghĩa thực dụng về “ranh giới”

Ranh giới test là **điều mà test có quyền khẳng định**, không phải tên class hoặc framework:

- `MockMvc`: có thể kiểm Spring MVC routing/controller/filter chain trong servlet mock; **không dùng TCP thật**.
- `MockRestServiceServer`: intercept outbound `RestClient`/`RestTemplate` ở request factory; assert URL/status/headers; **không mô phỏng đầy đủ socket/TLS/redirect**.
- `@SpringBootTest(RANDOM_PORT)`: chạy HTTP server thật để client gửi request qua local TCP; nhưng nếu downstream bị Mockito mock thì **downstream network vẫn chưa được kiểm**.
- k6 tới app thật: đo kết quả end-to-end từ máy tạo tải, nhưng nếu backend dữ liệu là fake/mock thì kết luận chỉ áp dụng cho topology giả.
- Toxiproxy trước một downstream: tác động lên kết nối TCP đi qua proxy ấy; không chứng minh hành vi của DNS, control plane hoặc thành phần không đi qua proxy.

## 3. Hợp đồng chức năng không chỉ là HTTP status

Một contract API phải nói rõ ít nhất:

1. **Tiền điều kiện:** principal, dữ liệu nền, service dependencies, config và feature flags.
2. **Input:** method/path/query/headers/body và validation.
3. **Output:** HTTP status, schema, ý nghĩa từng field, headers và error code.
4. **Side effects:** DB writes, event outbox, email, idempotency key.
5. **Failure behavior:** timeout, 503, malformed response, exhausted retries, fallback.
6. **Observability:** correlation ID, trace, degraded marker và metrics quan trọng.

Ví dụ một API kiểm tồn kho trả:

```json
{
  "sku": "BOOK",
  "status": "AVAILABLE",
  "source": "REMOTE",
  "degraded": false
}
```

Khi downstream gặp sự cố, nó có thể trả:

```json
{
  "sku": "BOOK",
  "status": "UNKNOWN",
  "source": "FALLBACK",
  "degraded": true
}
```

Trong bài demo, cả hai có thể dùng HTTP `200` vì hợp đồng public cho phép thông tin “không biết” thay vì giả vờ “hết hàng”. **Tuy nhiên hai response không cùng chất lượng nghiệp vụ.** Nếu load test chỉ đo `http_req_failed` dựa trên status, degraded 200 vẫn có thể được xem là HTTP success. Phải có **business-level SLI** để đếm `degraded:true` và kiểm expected fields. Một sản phẩm khác hoàn toàn có quyền chọn HTTP `503` khi mất tồn kho; điều quan trọng là contract và SLI thống nhất, không phải áp một status mặc định cho tất cả.

## 4. Kiểm thử chức năng: tính xác định và sức diễn đạt

Functional test thường có **input và expected output rõ**. Ví dụ:

```text
Given sku=BOOK và downstream trả AVAILABLE
When GET /api/availability/BOOK
Then HTTP 200, sku=BOOK, status=AVAILABLE,
     source=REMOTE, degraded=false

Given downstream trả 503 ở lần đầu rồi 200
When GET /api/availability/BOOK
Then chỉ 2 gateway calls, status=AVAILABLE,
     không dùng fallback

Given downstream trả 503 hai lần
When GET /api/availability/BOOK
Then status=UNKNOWN, degraded=true,
     attempts giới hạn ở 2

Given downstream trả payload sku=PEN cho request BOOK
When GET /api/availability/BOOK
Then 502/contract error, KHÔNG xem như 503 retryable
```

Đây là các **functional resilience tests**: chúng dùng failure injection có kiểm soát để kiểm xử lý lỗi trong code. Chúng **không** xác nhận p95, throughput hoặc khả năng phục hồi ở network partition thực vì không đặt tải và hạ tầng tương ứng.

### 4.1. Khi nào gọi “contract test”?

Consumer-driven contract, schema validation, OpenAPI compatibility hoặc provider state tests kiểm **hai phía có đồng thuận về thông điệp và semantics** hay không. Một WireMock stub chỉ giả lập “provider có thể trả 503”; nó chưa chứng minh provider production thực sự tuân theo schema hoặc các trạng thái khác. Với Pact hoặc Spring Cloud Contract, cần verify provider và consumer theo setup của hệ thống.

**Nên có cả hai:** contract tests kiểm giao tiếp có cùng ý nghĩa; resilience tests kiểm hành vi consumer khi provider trả một trong các kết quả được contract cho phép.

## 5. Kiểm thử tải đo phân phối, không đo một assertion đơn lẻ

Performance/load tests tạo nhiều operations trong **một workload có định nghĩa**:

- Request rate hoặc số virtual users, arrival distribution.
- Cơ cấu endpoints và tỷ lệ read/write.
- Dataset cardinality, cache hit/miss, SKU phân bố thế nào.
- Payload sizes, authentication, cookies, connection reuse.
- Warm-up, thời gian steady-state, ramp-up/ramp-down.
- Nguồn cấp tải, độ trễ mạng, giới hạn máy client.
- Backend services và database có giống môi trường mục tiêu không.

Các số cần thu:

| Tên | Nghĩa | Bẫy |
|---|---|---|
| Throughput/RPS | Số request hoàn thành mỗi giây | Hoàn thành nhiều request không có nghĩa tất cả đúng |
| Offered arrival rate | Số request dự định bắt đầu mỗi giây | Có thể không đạt vì thiếu VUs/generator quá tải |
| p50 | Latency trung vị | Không đại diện tail |
| p95/p99 | Phân vị 95/99 latency | Cần đủ mẫu; không chọn một lần đo để suy ra SLA năm |
| Error rate | Tỷ lệ request lỗi theo phân loại | HTTP 200 degraded có thể chưa bị tính lỗi |
| Business-success rate | Tỷ lệ response đúng nghiệp vụ, không degraded | Phải tự định nghĩa checks/metric |
| Saturation | CPU, thread pool, connection pool, DB pool, queue | Đo trên system under test, không chỉ client |
| Drops | Tác vụ load generator không khởi chạy được | Có thể sai mục tiêu RPS dù p95 nhìn đẹp |
| Recovery time | Thời gian từ lỗi dừng đến SLI phục hồi | Chỉ có ý nghĩa nếu có baseline và quan sát liên tục |

**Không dùng `assertTrue(elapsedMillis < 100)` trong một JUnit test đơn lẻ để công bố p95 <100 ms.** Một lần đo chịu JIT, CPU scheduler, GC, CI contention và cache. Timings trong unit test chỉ phù hợp cho timeout/failure semantics có bound rõ, không thay load characterization.

## 6. SLI, SLO, SLA và error budget

- **SLI:** số liệu quan sát một thuộc tính dịch vụ, ví dụ tỷ lệ GET hợp lệ hoàn thành ≤500 ms **và** trả kết quả không degraded.
- **SLO:** mục tiêu nội bộ về SLI trong một khoảng thời gian, ví dụ 99,9% requests theo sliding 30-day window thành công theo định nghĩa.
- **SLA:** cam kết thỏa thuận bên ngoài, thường có hệ quả nếu vi phạm.
- **Error budget:** lượng lỗi còn được phép trong SLO window; một chaos experiment có thể tiêu hao ngân sách nếu chạy trên production.

Ví dụ mục tiêu **minh họa** cho phòng lab, KHÔNG phải chỉ tiêu hệ thống thật:

```text
Workload: GET /api/availability/BOOK, 10 RPS, 30 s, isolated local app.
Functional: 200, schema hợp lệ, sku đúng, degraded=false.
HTTP error rate: < 1%.
Business success rate: > 99%.
p95 client HTTP latency: < 500 ms.
dropped_iterations: 0.
No unauthorized data change; no persistent queue growth.
```

Ngưỡng phải đến từ product SLO/capacity requirement, không được chọn chỉ vì chúng làm test xanh. Và **30 giây x 10 RPS** chỉ là một bài load ngắn để minh họa cách đo, **không** chứng minh SLA 30 ngày hay chịu được peak traffic ở production.

## 7. Load, stress, spike, soak và capacity test khác nhau

| Kiểu | Workload | Câu hỏi |
|---|---|---|
| Smoke performance | Rất nhỏ, ngắn | Công cụ đang gọi đúng app, metrics có hợp lệ? |
| Baseline | Tải thấp, ổn định | Latency/error khi gần như không có contention |
| Load | Expected sustained traffic | Đáp ứng SLO với tải mục tiêu? |
| Stress | Tăng trên expected capacity | Ngưỡng suy giảm, backpressure, fail gracefully? |
| Spike | Tăng nhanh rồi giảm | Autoscaling, queue và connection pools phản ứng? |
| Soak/endurance | Tải trung bình trong thời gian dài | Memory leak, FD leak, GC drift, connection exhaustion? |
| Scalability | Đổi số replicas/CPU và giữ workload | Throughput/latency thay đổi ra sao? |
| Resilience under load | Workload ổn định + fault có kiểm soát | Degradation/recovery trong áp lực thực? |

**Mỗi loại cần dữ liệu và tiêu chí riêng.** Kịch bản 30s của bài demo không được gọi là soak test. Và không chạy stress/spike lên shared staging hoặc production chỉ vì có script; tải có thể chiếm CPU, DB connections, queue và tác động tới người khác.

## 8. Open model và closed model trong k6

**Closed model:** một số lượng virtual users thực hiện vòng lặp; iteration mới thường bắt đầu khi VU hoàn thành vòng cũ. Khi server chậm, tốc độ gửi request có thể **tự giảm**, tạo ra kết quả throughput thấp nhưng latency có vẻ không xấu.

**Open model:** đặt trước arrival rate độc lập thời gian response, ví dụ `10 iterations/s`. Khi service chậm, cần nhiều concurrent VUs hơn để giữ nhịp. Nếu không đủ VUs, k6 ghi `dropped_iterations`. Open model thường phù hợp để test RPS được áp từ bên ngoài, nhưng phải chuẩn bị generator capacity.

Ví dụ:

```javascript
export const options = {
  scenarios: {
    availability: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 20
    }
  }
};
```

Đây là snippet, script đầy đủ ở mục 27. Trong `constant-arrival-rate`, **không thêm `sleep(1)` cuối iteration** để “giữ nhịp 1 RPS mỗi VU”; executor đã tự sắp arrival. 10 RPS ở script không bảo đảm 10 request/s nếu có dropped iterations hoặc test logic trong một iteration gọi nhiều requests.

## 9. Gây lỗi có kiểm soát: không đồng nghĩa ngắt production tùy ý

**Fault injection test** đưa một lỗi có thể tái tạo vào boundary (HTTP 503, timeout, connection reset, Redis unavailable) để quan sát một hành vi cụ thể. **Chaos experiment** có thêm giả thuyết về steady state, phạm vi hệ thống, tác động có kiểm soát, đo lường và cơ chế dừng/khôi phục; thường gần topology thật hơn. Không nên dùng hai tên như từ đồng nghĩa hoàn toàn.

Ví dụ các mức:

1. **Unit:** Mockito ném `UpstreamUnavailableException` hai lần; kiểm retry count, fallback.
2. **HTTP stub:** WireMock trả `503` hoặc delay 1,2s trên một endpoint; client thực mở socket tới server stub.
3. **Network proxy:** Toxiproxy thêm latency/jitter hoặc cắt kết nối giữa application và test dependency.
4. **Platform fault:** Restart/kill một pod không critical trong namespace thử nghiệm, chặn egress của một replica theo policy.
5. **Production chaos:** Chỉ nếu có **ủy quyền cụ thể**, quyền sở hữu hệ thống, error budget, blast-radius/rollback và on-call trực chiến; **không** phải bước mặc định của bài học.

Một test ở mức 1 có thể kiểm code xử lý exception chính xác. Mức 3–4 mới giúp thấy connection pool behavior, autoscaler/backpressure và recovery thật ở topology phù hợp. Mức 5 mang rủi ro vận hành và cần quy trình phê duyệt riêng.

## 10. Ba giai đoạn của một thí nghiệm lỗi đáng tin

```text
A. BEFORE (steady state)
  - Kiểm baseline functional contracts
  - Đo RPS, p95/p99, errors, business success, saturation
  - Xác nhận dashboard/traces/logs sẵn sàng

B. DURING (fault active)
  - Chỉ áp một lỗi đã đăng ký trong phạm vi được duyệt
  - Ghi bắt đầu, mục tiêu, cường độ, TTL và request IDs
  - Đo degraded mode, retries, queue, pool, error budget
  - Tự dừng nếu vượt abort criteria

C. AFTER (recovery)
  - Gỡ lỗi chắc chắn (finally, TTL, operator rollback)
  - Quan sát service trở lại steady state
  - Kiểm data integrity, backlog drain, duplicate side effects
  - Lưu artifacts: config, timeline, metrics, findings
```

Nếu test chỉ kiểm system vẫn trả 200 **trong** khi lỗi mà không kiểm fallback ratio, data correctness và recovery **sau** khi gỡ lỗi, kết luận “resilient” là quá mạnh.

## 11. Ma trận lỗi cần bao phủ

| Lỗi đưa vào | Functional expectation | Load/fault observation |
|---|---|---|
| Upstream HTTP `503` | Retry có giới hạn, fallback/503 đúng contract | Retry amplification, degrade rate |
| Upstream HTTP `404` | Không retry mù quáng; map domain/error | Không tạo retry storm với dữ liệu không có |
| Kết nối bị reset | Có timeout, exception mapping và cleanup | Connection pool có recover không? |
| Latency tăng vượt timeout | Không chờ vô hạn | p95/p99, thread exhaustion, backlog |
| DNS fail | Không leak token/secret; fail có bound | Cache DNS và recovery |
| TLS lỗi/cert hết hạn | Fail closed, không tắt certificate validation | Số request lỗi, alert đúng |
| Database pool đầy | Không treo thread vô hạn | Pending connections, RPS collapse |
| Redis unavailable | Cache miss/fallback có policy | DB load tăng bao nhiêu? |
| Pod restart | Request đang xử lý có semantics đúng | Readiness/liveness, retry, zero-downtime |
| Queue lag | Eventual status và backpressure | Lag drain/recovery time |
| Rate limit `429` | Respect Retry-After/policy | Throttling/retry storm |
| Invalid downstream JSON | 502/contract failure, không silent false | Bad-contract counts |
| Time skew | Expiry/lease/idempotency đúng | Split-brain/duplicate processing |

Không cố gây toàn bộ lỗi trong một test rồi không biết triệu chứng đến từ đâu. Bắt đầu với **một fault, một giả thuyết, một metric chính**, sau đó tăng độ phức tạp nếu có lý do.

## 12. Spring Boot test annotations: chúng chứng minh gì?

| Công cụ/annotation | Dùng cho | Không tự chứng minh |
|---|---|---|
| JUnit thuần/Mockito | Domain policy, retry count, idempotency unit | HTTP socket, TLS, capacity |
| `@WebMvcTest` + `MockMvc` | Routing, schema, status, headers, validation | Network stack hoặc tải thật |
| `@RestClientTest` + `MockRestServiceServer` | Outbound URL/headers/status mapping, 503 stub | TCP timeout, connection reset thật |
| `@SpringBootTest` (default MOCK) | App context, bean wiring, MockMvc nếu cấu hình | Embedded server socket |
| `@SpringBootTest(RANDOM_PORT)` | Real inbound TCP + servlet filters | Downstream thật nếu vẫn mocked |
| WireMock/MockWebServer | Real stub HTTP socket, delay/reset/retry | True production downstream capacity |
| Testcontainers/Toxiproxy | Container/service networking có fault | Production network, cloud control plane |
| k6/Gatling | Tải theo workload profile, aggregate metrics | Business correctness nếu checks yếu |
| Chaos platform/cluster experiment | Failure behavior/topology recovery | Mọi API contract, mọi vùng dữ liệu |

**RANDOM_PORT** tạo server và cổng thật; client gửi qua HTTP. **MockMvc** không mở TCP, dù chạy trong `@SpringBootTest`. Khi HTTP client của bài được thay bằng Mockito bean trong full-context test, hãy ghi rõ điều đó.

## 13. Demo chạy được: hợp đồng của dịch vụ kiểm tồn kho

Ứng dụng mẫu cung cấp:

- `GET /api/availability/{sku}`.
- SKU chỉ cho phép chữ hoa, số và dấu gạch ngang; độ dài 1–24.
- Gọi downstream `GET {demo.stock.base-url}/stock/{sku}`.
- Downstream JSON trả `sku` và `stock` trong tập `AVAILABLE`/`OUT_OF_STOCK`.
- Khi downstream trả 503 hoặc connection IO failure, thử tối đa **2 lần** rồi trả `UNKNOWN` + `degraded=true`.
- Nếu downstream trả JSON sai SKU hoặc stock status không hợp lệ, **fail closed** bằng error `502`, không coi là transient 503.
- Nếu SKU do client cung cấp sai định dạng, trả `400` trước khi gọi gateway.
- Khi success trả JSON `source=REMOTE, degraded=false`.
- Khi fallback trả JSON `source=FALLBACK, degraded=true`; HTTP 200 chỉ là quyết định contract của demo.
- Không có DB, transaction, payment/order side effects; demo cố tình dùng GET idempotent.

**Chú ý vận hành:** Code retry hai lần **ngay lập tức, không backoff** để JUnit tests deterministic. Đây là **cơ chế minh họa**, không phải retry policy production. Với hệ thống thật cần timeout tổng thể, exponential backoff/jitter, retry budget, circuit breaker, idempotency và giám sát retry amplification; không copy vòng retry đơn giản này vào hệ thống tải cao.

## 14. Sơ đồ demo và các đường test

```text
GET /api/availability/BOOK
     |
     v
InventoryController
     |
     v
InventoryService
  - validate sku
  - call gateway at most twice on transient failure
  - AVAILABLE / OUT_OF_STOCK / UNKNOWN
     |
     v
StockGateway (interface)
     |
     +-- HttpStockGateway (RestClient) ---> GET /stock/BOOK
     |                                  -> backend or stub
     +-- Mockito fake in service tests
     
Test paths:
1) Unit JUnit: InventoryService + mocked StockGateway
2) @RestClientTest: HttpStockGateway + MockRestServiceServer
3) @WebMvcTest: InventoryController + mocked InventoryService
4) @SpringBootTest RANDOM_PORT: real inbound HTTP + mocked gateway
5) k6 (separate): real app + configured isolated downstream
6) WireMock/Toxiproxy (separate): real outbound network fault
```

Mỗi đường test có một “điểm nhìn”. Không được cộng 1+2+3+4 và tuyên bố “đã đo performance dưới network partition”. Điểm 5 và 6 phải được chạy, đo và lưu evidence riêng.

## 15. Cây source project

```text
functional-load-fault-boundaries/
  settings.gradle
  build.gradle
  src/main/java/com/example/testboundary/
    TestBoundaryApplication.java
    RemoteStock.java
    InventoryResponse.java
    StockGateway.java
    UpstreamUnavailableException.java
    UpstreamContractException.java
    InvalidSkuException.java
    HttpStockGateway.java
    InventoryService.java
    InventoryController.java
    InventoryErrorAdvice.java
  src/test/java/com/example/testboundary/
    InventoryServiceTest.java
    HttpStockGatewayTest.java
    InventoryControllerTest.java
    InventoryHttpIntegrationTest.java
  load/
    availability.js
```

**Phạm vi runnable:** Các file `src/main`, `src/test` và Gradle tạo một project biên dịch/test với Java 17, Spring Boot 3.5.x. K6 cần chương trình `k6` riêng và một **downstream stub/environment đã được cô lập, đang chạy** để đo business-success thực. File `load/availability.js` không phải test JUnit và không được tự chạy bởi `./gradlew test`.

## 16. Gradle files

**`settings.gradle`**

```groovy
rootProject.name = 'functional-load-fault-boundaries'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` có MVC/RestClient/Jackson; `spring-boot-starter-test` có JUnit Jupiter, Mockito, MockMvc và MockRestServiceServer. Actuator mang nền tảng Micrometer/observability cho môi trường cần metrics, **không tự động xuất mọi endpoint ra công khai**. Không thêm k6/WireMock/Toxiproxy vào Gradle vì k6 là tool tách rời và bài core tests dùng Spring mock server. Nếu triển khai thêm network-fault integration, bổ sung test dependencies/phần Docker có chủ đích ở mục 30–31.

## 17. Application và DTO

**`src/main/java/com/example/testboundary/TestBoundaryApplication.java`**

```java
package com.example.testboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                TestBoundaryApplication.class, args);
    }
}
```

**`src/main/java/com/example/testboundary/RemoteStock.java`**

```java
package com.example.testboundary;

public record RemoteStock(
        String sku,
        String stock) {
}
```

**`src/main/java/com/example/testboundary/InventoryResponse.java`**

```java
package com.example.testboundary;

public record InventoryResponse(
        String sku,
        String status,
        String source,
        boolean degraded) {
}
```

Đây là DTOs có contract JSON rõ. `status=UNKNOWN` nghĩa là **không có chứng cứ xác nhận tồn kho**; nó **không** đồng nghĩa `OUT_OF_STOCK`. Frontend có thể hiển thị “tồn kho chưa xác định” hoặc chặn checkout theo policy. Load test sẽ kiểm điều này: response 200 nhưng degraded true không được tính business healthy.

## 18. Port và exception types: tách transient khỏi contract failure

**`src/main/java/com/example/testboundary/StockGateway.java`**

```java
package com.example.testboundary;

public interface StockGateway {
    RemoteStock fetch(String sku);
}
```

**`src/main/java/com/example/testboundary/UpstreamUnavailableException.java`**

```java
package com.example.testboundary;

public class UpstreamUnavailableException
        extends RuntimeException {

    public UpstreamUnavailableException(String message) {
        super(message);
    }

    public UpstreamUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

**`src/main/java/com/example/testboundary/UpstreamContractException.java`**

```java
package com.example.testboundary;

public class UpstreamContractException
        extends RuntimeException {

    public UpstreamContractException(String message) {
        super(message);
    }
}
```

**`src/main/java/com/example/testboundary/InvalidSkuException.java`**

```java
package com.example.testboundary;

public class InvalidSkuException
        extends RuntimeException {

    public InvalidSkuException() {
        super("Invalid SKU");
    }
}
```

**Tại sao cần tách lỗi?** Retry `IOException/503` có thể hữu ích khi transient, nhưng payload không hợp lệ, 401/403 do auth, hoặc 404 theo domain có thể không phục hồi chỉ vì gọi lại. Dùng một `catch(Exception ex)` bao tất cả rồi trả fallback sẽ che lỗi lập trình và làm contract sai. Mẫu chỉ coi **503** và **ResourceAccessException** là unavailable. Các status khác bị xem là downstream contract failure trong demo để dễ quan sát; sản phẩm thật cần policy chi tiết hơn.

## 19. RestClient adapter: từ HTTP status sang lỗi có ý nghĩa

**`src/main/java/com/example/testboundary/HttpStockGateway.java`**

```java
package com.example.testboundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

@Component
public class HttpStockGateway implements StockGateway {

    private final RestClient client;

    public HttpStockGateway(
            RestClient.Builder builder,
            @Value("${demo.stock.base-url:http://127.0.0.1:9099}")
            String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public RemoteStock fetch(String sku) {
        try {
            RemoteStock stock = client.get()
                    .uri("/stock/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .onStatus(
                            HttpStatusCode::isError,
                            (request, response) -> {
                                if (response.getStatusCode()
                                        .value() == 503) {
                                    throw new UpstreamUnavailableException(
                                            "Downstream unavailable");
                                }
                                throw new UpstreamContractException(
                                        "Unexpected downstream HTTP status");
                            })
                    .body(RemoteStock.class);

            if (stock == null) {
                throw new UpstreamContractException(
                        "Empty downstream response");
            }

            return stock;
        } catch (ResourceAccessException networkFailure) {
            throw new UpstreamUnavailableException(
                    "Cannot access downstream service",
                    networkFailure);
        }
    }
}
```

**Điều đoạn này kiểm:** 

- URL downstream được cấu hình cố định, không lấy từ input của client.
- `Accept: application/json` được đặt rõ.
- `503` chuyển thành lỗi transient để retry.
- Network I/O error mà RestClient bọc thành `ResourceAccessException` chuyển thành transient.
- Các HTTP errors khác chuyển thành contract failure (không retry trong demo).
- Empty JSON body được xem là contract failure.
- Kiểm schema và SKU matching vẫn ở service, không tự tin mọi JSON deserialize thành công là hợp lệ nghiệp vụ.

**Giới hạn quan trọng:** Code **chưa cấu hình connect/read/overall timeouts** trên HTTP request factory. Nó là bản demo để nhìn rõ test boundaries, **không đủ an toàn để dùng production**. Trước khi thử latency/blackhole fault trong môi trường có network thật, phải cấu hình timeout hữu hạn cho HTTP client/request factory của dự án, kiểm hành vi cancel/connect/read và retry budget. Không đưa traffic thật vào một client có thể chờ vô hạn rồi coi đó là chaos test an toàn. Nếu test slice `@RestClientTest` thêm request factory riêng, bảo đảm mock server vẫn được bind đúng — đừng vô tình ghi đè factory mà `MockRestServiceServer` dùng.

## 20. Service: retry có giới hạn, fallback trung thực

**`src/main/java/com/example/testboundary/InventoryService.java`**

```java
package com.example.testboundary;

import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private static final Pattern SKU =
            Pattern.compile("^[A-Z0-9-]{1,24}$");

    private static final Set<String> STOCK_VALUES =
            Set.of("AVAILABLE", "OUT_OF_STOCK");

    private final StockGateway gateway;

    public InventoryService(StockGateway gateway) {
        this.gateway = gateway;
    }

    public InventoryResponse check(String sku) {
        if (sku == null || !SKU.matcher(sku).matches()) {
            throw new InvalidSkuException();
        }

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                RemoteStock remote = gateway.fetch(sku);
                if (remote == null
                        || !sku.equals(remote.sku())
                        || !STOCK_VALUES.contains(
                                remote.stock())) {
                    throw new UpstreamContractException(
                            "Invalid downstream stock payload");
                }

                return new InventoryResponse(
                        sku, remote.stock(),
                        "REMOTE", false);

            } catch (UpstreamUnavailableException transientError) {
                if (attempt == 2) {
                    return new InventoryResponse(
                            sku, "UNKNOWN",
                            "FALLBACK", true);
                }
            }
        }

        throw new IllegalStateException(
                "Unreachable retry loop state");
    }
}
```

**Vì sao không giả unavailable thành OUT_OF_STOCK?** “Không biết” khác “không còn”. Một fallback sai về dữ liệu có thể gây từ chối bán hàng hoặc checkout sai. Một hệ thống có cached last-known-good data có thể trả giá trị stale với freshness metadata và policy riêng; không được khẳng định stale luôn an toàn.

**Vì sao chỉ retry một loại exception?** `UpstreamContractException` (bad schema/unknown status) không có lý do chắc chắn để gọi lại ngay. Nếu production cần retry 500/502/504 hoặc 429 theo policy thì thêm test tương ứng, không mở rộng thành `catch(RuntimeException)`. **Lưu ý:** Đây là retry **không backoff**, tối đa 2 attempts, chỉ để test logic trong vài mili giây. Trong outage lớn, retry ngay có thể nhân đôi RPS tới downstream.

## 21. Controller và error advice

**`src/main/java/com/example/testboundary/InventoryController.java`**

```java
package com.example.testboundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/availability")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public InventoryResponse check(
            @PathVariable String sku) {
        return service.check(sku);
    }
}
```

**`src/main/java/com/example/testboundary/InventoryErrorAdvice.java`**

```java
package com.example.testboundary;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InventoryErrorAdvice {

    public record ErrorBody(String code) {
    }

    @ExceptionHandler(InvalidSkuException.class)
    public ResponseEntity<ErrorBody> invalidSku() {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("INVALID_SKU"));
    }

    @ExceptionHandler(UpstreamContractException.class)
    public ResponseEntity<ErrorBody> downstreamContract() {
        return ResponseEntity.status(502)
                .body(new ErrorBody("UPSTREAM_CONTRACT"));
    }
}
```

Controller không chứa retry loop; error mapping riêng. Endpoint luôn trả 200 cho `InventoryResponse`, kể cả degraded=true, bởi đó là contract minh họa. Một production API có thể trả 503 khi không biết tồn kho; khi đó functional tests, k6 checks và SLO phải cùng đổi.

**Error privacy:** Không trả stack trace, private host, credential hay exception message thô cho người dùng. Với lỗi bất ngờ không được advice này xử lý, Spring Boot error handling vẫn cần cấu hình sanitize phù hợp. Không map mọi exception thành 200/fallback rồi vô tình che security/contract bugs.

## 22. Pure JUnit: đúng/sai theo từng request và số attempts

**`src/test/java/com/example/testboundary/InventoryServiceTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryServiceTest {

    @Mock
    StockGateway gateway;

    InventoryService service;

    @BeforeEach
    void setUp() {
        service = new InventoryService(gateway);
    }

    @Test
    void healthyDownstreamReturnsBusinessData() {
        when(gateway.fetch("BOOK")).thenReturn(
                new RemoteStock("BOOK", "AVAILABLE"));

        InventoryResponse result = service.check("BOOK");

        assertEquals("AVAILABLE", result.status());
        assertEquals("REMOTE", result.source());
        assertFalse(result.degraded());
        verify(gateway).fetch("BOOK");
    }

    @Test
    void oneTransientFailureThenSuccessUsesTwoAttempts() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamUnavailableException(
                        "temporary 503"))
                .thenReturn(new RemoteStock(
                        "BOOK", "OUT_OF_STOCK"));

        InventoryResponse result = service.check("BOOK");

        assertEquals("OUT_OF_STOCK", result.status());
        assertFalse(result.degraded());
        verify(gateway, times(2)).fetch("BOOK");
    }

    @Test
    void repeated503UsesExplicitUnknownFallback() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamUnavailableException(
                        "temporary 503"));

        InventoryResponse result = service.check("BOOK");

        assertEquals("UNKNOWN", result.status());
        assertEquals("FALLBACK", result.source());
        assertTrue(result.degraded());
        verify(gateway, times(2)).fetch("BOOK");
    }

    @Test
    void contractErrorIsNotRetried() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamContractException(
                        "invalid JSON semantics"));

        assertThrows(UpstreamContractException.class,
                () -> service.check("BOOK"));

        verify(gateway).fetch("BOOK");
    }

    @Test
    void mismatchedRemoteSkuFailsClosed() {
        when(gateway.fetch("BOOK")).thenReturn(
                new RemoteStock("PEN", "AVAILABLE"));

        assertThrows(UpstreamContractException.class,
                () -> service.check("BOOK"));

        verify(gateway).fetch("BOOK");
    }

    @Test
    void invalidSkuNeverCallsDownstream() {
        assertThrows(InvalidSkuException.class,
                () -> service.check("book/../admin"));

        verifyNoInteractions(gateway);
    }
}
```

**Sáu methods** này chạy mà **không có Spring context hay HTTP socket**. Chúng chứng minh policy cụ thể: first-success, one retry, exhausted retries, contract fail-closed, response SKU matching, input validation. Không có assertion latency/RPS. Không cần dùng `Thread.sleep` hoặc network outage để kiểm chính xác retry count.

**Test `repeated503UsesExplicitUnknownFallback` là một functional resilience test, không phải load test.** Nó không chạy đồng thời nhiều requests và không đo saturation. Nếu ai đó báo “server chịu được 1.000 RPS vì test này pass”, cần sửa nhận định ấy ngay.

## 23. `@RestClientTest`: HTTP contract và status mapping

**`src/test/java/com/example/testboundary/HttpStockGatewayTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(HttpStockGateway.class)
@TestPropertySource(properties =
        "demo.stock.base-url=http://stock.example.test")
class HttpStockGatewayTest {

    private static final String URL =
            "http://stock.example.test/stock/BOOK";

    @Autowired
    HttpStockGateway gateway;

    @Autowired
    MockRestServiceServer server;

    @Test
    void maps200JsonAndChecksRequestContract() {
        server.expect(requestTo(URL))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"stock\":\"AVAILABLE\"}",
                        MediaType.APPLICATION_JSON));

        RemoteStock reply = gateway.fetch("BOOK");

        assertEquals("BOOK", reply.sku());
        assertEquals("AVAILABLE", reply.stock());
        server.verify();
    }

    @Test
    void maps503ToRetryableDomainException() {
        server.expect(requestTo(URL))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        assertThrows(UpstreamUnavailableException.class,
                () -> gateway.fetch("BOOK"));

        server.verify();
    }

    @Test
    void doesNotConfuse404With503() {
        server.expect(requestTo(URL))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(UpstreamContractException.class,
                () -> gateway.fetch("BOOK"));

        server.verify();
    }

    @Test
    void emptySuccessfulBodyIsContractFailure() {
        server.expect(requestTo(URL))
                .andRespond(withSuccess(
                        "", MediaType.APPLICATION_JSON));

        assertThrows(UpstreamContractException.class,
                () -> gateway.fetch("BOOK"));

        server.verify();
    }
}
```

**Bốn methods** chứng minh adapter đặt đúng URL/GET/Accept và map 503/404/body rỗng theo contract của demo. `MockRestServiceServer` gắn vào request factory của RestClient, **không mở kết nối tới `stock.example.test`**. Server mock không thực hiện một network timeout/TLS/connection reset thật, nên `503` được trả về ngay không cho biết thread pool bị tắc thế nào khi downstream treo 30 giây.

Nếu test cần kiểm client connection timeout, DNS, redirect, TLS hoặc pool reuse, chuyển sang một real mock HTTP server hoặc Toxiproxy với request factory đúng production, không suy ra từ test trên.

## 24. `@WebMvcTest`: contract của public API

**`src/test/java/com/example/testboundary/InventoryControllerTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InventoryController.class)
@Import(InventoryErrorAdvice.class)
class InventoryControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    InventoryService service;

    @Test
    void successfulResultKeepsBusinessFields()
            throws Exception {
        when(service.check("BOOK"))
                .thenReturn(new InventoryResponse(
                        "BOOK", "AVAILABLE",
                        "REMOTE", false));

        mvc.perform(get("/api/availability/BOOK"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.status").value("AVAILABLE"),
                        jsonPath("$.source").value("REMOTE"),
                        jsonPath("$.degraded").value(false));

        verify(service).check("BOOK");
    }

    @Test
    void degradedResponseIsNotMisrepresentedAsStockAvailable()
            throws Exception {
        when(service.check("BOOK"))
                .thenReturn(new InventoryResponse(
                        "BOOK", "UNKNOWN",
                        "FALLBACK", true));

        mvc.perform(get("/api/availability/BOOK"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.status").value("UNKNOWN"),
                        jsonPath("$.source").value("FALLBACK"),
                        jsonPath("$.degraded").value(true));
    }

    @Test
    void invalidSkuMapsTo400WithoutLeakingDetails()
            throws Exception {
        when(service.check("bad"))
                .thenThrow(new InvalidSkuException());

        mvc.perform(get("/api/availability/bad"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_SKU"));
    }

    @Test
    void badDownstreamContractMapsTo502()
            throws Exception {
        when(service.check("BOOK"))
                .thenThrow(new UpstreamContractException(
                        "do not expose private backend detail"));

        mvc.perform(get("/api/availability/BOOK"))
                .andExpectAll(
                        status().isBadGateway(),
                        jsonPath("$.code").value(
                                "UPSTREAM_CONTRACT"));
    }
}
```

**Bốn methods** kiểm Spring MVC routing/JSON/errors, nhưng `InventoryService` đã bị mock. Việc controller trả đúng payload không chứng minh retry loop chạy. Đó là lý do cần `InventoryServiceTest` ở mục 22, và không dùng một MVC test để suy ra downstream/network capacity.

## 25. `@SpringBootTest(RANDOM_PORT)`: real inbound HTTP, mocked downstream

**`src/test/java/com/example/testboundary/InventoryHttpIntegrationTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @MockitoBean
    StockGateway gateway;

    @Test
    void actualInboundHttpReturnsHealthyContract() {
        when(gateway.fetch("BOOK")).thenReturn(
                new RemoteStock("BOOK", "AVAILABLE"));

        ResponseEntity<InventoryResponse> result =
                http.getForEntity(
                        "/api/availability/BOOK",
                        InventoryResponse.class);

        assertEquals(200, result.getStatusCode().value());
        assertEquals("BOOK", result.getBody().sku());
        assertEquals("AVAILABLE", result.getBody().status());
        assertFalse(result.getBody().degraded());

        verify(gateway).fetch("BOOK");
    }

    @Test
    void actualInboundHttpPreservesDegradedMarker() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamUnavailableException(
                        "transient fault"));

        ResponseEntity<InventoryResponse> result =
                http.getForEntity(
                        "/api/availability/BOOK",
                        InventoryResponse.class);

        assertEquals(200, result.getStatusCode().value());
        assertEquals("UNKNOWN", result.getBody().status());
        assertTrue(result.getBody().degraded());

        verify(gateway, times(2)).fetch("BOOK");
    }
}
```

**Hai methods** chạy server thật trên random port và TestRestTemplate gọi qua localhost HTTP. Chúng kiểm serialization và inbound transport tốt hơn MockMvc. Tuy nhiên `@MockitoBean StockGateway` thay thế downstream port, vì vậy **không có HTTP tới stock service** trong hai test này. Đừng viết kết luận “network fault recovered” từ suite này.

Đặc biệt, Spring Boot lưu ý nếu dùng `@Transactional` ở một test `RANDOM_PORT`, client và server chạy ở các threads/transactions khác nhau nên rollback ở test thread **không tự rollback các thay đổi server**. Demo không có DB nên không vướng, nhưng workload/performance tests cần fixtures và cleanup tách biệt.

## 26. Chạy JUnit suite và phạm vi kết quả

| Class | Số `@Test` | Cái được kiểm |
|---|---:|---|
| `InventoryServiceTest` | 6 | Domain validation, retry count, fallback semantics |
| `HttpStockGatewayTest` | 4 | Outbound HTTP request và status mapping qua mock factory |
| `InventoryControllerTest` | 4 | Public HTTP JSON/errors qua MockMvc |
| `InventoryHttpIntegrationTest` | 2 | Real inbound HTTP, mocked downstream |
| **Tổng** | **16** | Functional/API và một số controlled failure branches |

Chạy với Gradle wrapper đã tạo:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Kết quả dự kiến:** Với JDK 17, Spring Boot 3.5.16 và dependencies giải quyết được, 16 tests dự kiến pass. Nếu chưa có wrapper, tạo wrapper theo convention trước. JUnit report ở `build/reports/tests/test/index.html`. Đây là **đánh giá mã mẫu**, **không phải kết quả tôi đã chạy Gradle**. Không có stdout business cố định; cổng ngẫu nhiên, timing CI và request logs không phải kết quả nên hard-code.

**Đánh giá chính xác:** Khi cả 16 tests pass, có thể nói “functional contracts và controlled 503 handling theo các test đã kiểm được thỏa mãn”. **Không thể** nói “SLO 99.9% đã đạt” hoặc “chaos recovery đã được xác nhận”, vì chưa có workload/real fault experiment.

## 27. K6: script tải tách riêng và có safety guard

**`load/availability.js`** — file JavaScript dành cho công cụ k6, **không** chạy bởi JUnit:

```javascript
import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const businessHealthy = new Rate('business_healthy');
const base = __ENV.BASE_URL || 'http://127.0.0.1:8080';

// Guard cố ý chỉ cho loopback trong ví dụ.
// Chỉ thay sau khi có duyệt môi trường isolated.
if (!/^http:\/\/(127\.0\.0\.1|localhost):[0-9]+$/.test(base)) {
  throw new Error('This training load script only targets loopback');
}

export const options = {
  scenarios: {
    availability: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 20
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{route:availability}': ['p(95)<500'],
    business_healthy: ['rate>0.99'],
    dropped_iterations: ['count==0']
  }
};

export default function () {
  const response = http.get(
    base + '/api/availability/BOOK',
    { tags: { route: 'availability' } }
  );

  let payload = null;
  try {
    payload = response.json();
  } catch (_error) {
    // JSON parse errors are counted as business failures below.
  }

  const valid =
    response.status === 200 &&
    payload !== null &&
    payload.sku === 'BOOK' &&
    payload.status === 'AVAILABLE' &&
    payload.source === 'REMOTE' &&
    payload.degraded === false;

  businessHealthy.add(valid);

  check(response, {
    'HTTP status 200': (r) => r.status === 200
  });
}
```

**Trước khi chạy:** Khởi động Spring Boot app ở cổng 8080 và một **test downstream** trả `{"sku":"BOOK","stock":"AVAILABLE"}` ở `http://127.0.0.1:9099/stock/BOOK`, hoặc cấu hình `demo.stock.base-url` đến stub cô lập. Nếu không có downstream, code demo sẽ trả `UNKNOWN/degraded=true`; script **cố ý fail business_healthy**, dù HTTP status có thể vẫn là 200.

Lệnh gợi ý, sau khi cài k6 riêng và đã cấp quyền test môi trường cục bộ:

```bash
k6 run load/availability.js
```

Đổi cổng ứng dụng local:

```bash
BASE_URL=http://127.0.0.1:8081 k6 run load/availability.js
```

Dòng gán biến trước command là cú pháp shell POSIX; trên PowerShell, đặt `$env:BASE_URL="http://127.0.0.1:8081"` rồi chạy `k6 run load/availability.js`. **Không chạy** khi chưa có upstream stub và readiness ổn định, vì kết quả sẽ đo đường fallback chứ không đo đường khỏe như thiết kế.

### 27.1. Ý nghĩa ngưỡng

- `http_req_failed: rate<0.01`: tỷ lệ HTTP requests mà k6 coi là failed nhỏ hơn 1%.
- `http_req_duration{route:availability}: p(95)<500`: 95% các request có tag route tương ứng dưới 500 ms (giá trị mẫu).
- `business_healthy: rate>0.99`: >99% requests trả đúng JSON **không degraded**.
- `dropped_iterations: count==0`: load generator không bỏ qua iteration vì thiếu VUs/capacity.

**Một `check(...)` đơn lẻ không tự làm k6 exit nonzero** khi fail; `thresholds` quyết định overall pass/fail. Rate custom giúp đo **business SLI** chứ không chỉ status. Trên request 200 nhưng `UNKNOWN`, `http_req_failed` thường không coi là lỗi, nhưng `business_healthy` sẽ false.

### 27.2. Những giới hạn của kịch bản

Script **30 giây x 10 iterations/s** là một lab sanity load, không phải chứng cứ cho production SLO. Nếu gateway có latency/timeout, backlog/caching/hệ thống tạo tải không đủ capacity, phải lưu actual iteration rate và dropped iterations. K6 chạy trên máy developer với app/stub cùng host có bottleneck rất khác cluster production. Không suy ra CPU headroom, DB pool hoặc autoscaling từ kết quả localhost.

## 28. Đọc k6 report mà không tự lừa mình

Giả sử báo cáo *minh họa*:

```text
http_req_duration...........: p(95)=120ms
http_req_failed.............: 0.00%
business_healthy............: 50.00%
dropped_iterations..........: 0
```

**Không kết luận PASS chỉ vì p95 120 ms và HTTP errors 0%.** Một nửa responses đã degraded, nên business target >99% fail. Cần điều tra backend và lý do fallback. K6 threshold đã mã hóa điều đó thành failing exit code.

Trường hợp khác:

```text
http_req_duration...........: p(95)=150ms
business_healthy............: 100.00%
dropped_iterations..........: 80
```

Có thể các requests **đã được khởi chạy** đều nhanh, nhưng generator không phát được tất cả offered arrivals; workload mục tiêu chưa đạt. Không lấy p95 từ lưu lượng thấp hơn rồi kết luận hệ thống chịu đủ tải.

### 28.1. Percentile có sample size và filter

Khi tỷ lệ 503 cao, đo p95 chỉ trên success responses có thể làm p95 **đẹp giả**. Báo cáo cả overall và segmented metrics (success, degraded, errors) với sample sizes. Cần đo từ load generator lẫn server observability; cái nào không được đo phải ghi rõ. Percentile từ một test có vài samples hoặc chạy một lần trên CI bận không đủ mạnh để làm SLO dài hạn.

## 29. Kỹ thuật gây lỗi HTTP thật bằng WireMock

`MockRestServiceServer` trong mục 23 không dùng socket. Nếu cần kiểm read timeout, connection reset hoặc redirect behavior của **RestClient request factory thật**, chạy một **local WireMockServer** hoặc MockWebServer trên random port và trỏ `demo.stock.base-url` tới nó.

Ví dụ **snippet** WireMock Java (cần thêm `wiremock` test dependency phù hợp; không nằm trong runnable core project):

```java
// Snippet minh họa cho local HTTP stub; yêu cầu imports WireMock.
WireMockServer stub = new WireMockServer(
        wireMockConfig().dynamicPort());

stub.start();
try {
    stub.stubFor(get(urlEqualTo("/stock/BOOK"))
            .willReturn(aResponse()
                    .withStatus(503)));

    // Khởi tạo app/client thật trỏ baseUrl đến stub.baseUrl().
    // Assert retry budget/fallback via actual HTTP requests.
    // stub.verify(2, getRequestedFor(urlEqualTo("/stock/BOOK")));
} finally {
    stub.stop();
}
```

Để tiêm latency:

```java
// Snippet WireMock; test client phải cấu hình timeout hữu hạn.
stub.stubFor(get(urlEqualTo("/stock/BOOK"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(1200)
                .withHeader("Content-Type", "application/json")
                .withBody(
                    "{\"sku\":\"BOOK\",\"stock\":\"AVAILABLE\"}")));
```

Nếu client read timeout được cấu hình 500 ms, độ trễ 1.200 ms có thể kích hoạt timeout rồi vào failure path; nhưng **đừng khẳng định kết quả trước khi test với đúng request factory**. Một số HTTP libraries có khác biệt về connect/read/overall timeout, retry tự động, connection pooling và xử lý interrupted response. Một test thật nên assert số attempts, elapsed bounded, no leaked connections, fallback và recovery khi stub trở về healthy.

**Không dùng `withFixedDelay(1200)` rồi coi đó là thí nghiệm overload production.** Nó kiểm đúng một kiểu server delay ở local stub; không mô phỏng CPU throttling, TCP packet loss hay DB locking.

## 30. Toxiproxy: lỗi ở ranh giới TCP/network

Testcontainers Toxiproxy tạo proxy giữa app/client và một downstream test container. Có thể điều khiển toxic, ví dụ:

```java
// Snippet, cần Testcontainers Toxiproxy module + Docker.
// proxy là ContainerProxy đã tạo cho test upstream.
proxy.toxics()
        .latency(
                "latency-test",
                ToxicDirection.DOWNSTREAM,
                1100)
        .setJitter(100);

try {
    // Gọi real HTTP client tới host/port proxy.
    // Quan sát timeout, retries và degraded SLI.
} finally {
    proxy.toxics().get("latency-test").remove();
}
```

**Kỹ thuật khác mức với WireMock status stub:** Toxiproxy đặt tác động vào dòng TCP (latency, bandwidth, timeout, connection cut), giúp kiểm network behavior thật hơn. Nhưng chỉ những connections **đi qua proxy** bị ảnh hưởng; nếu RestClient giữ một direct base URL hoặc một connection đã đi đường khác, test không đánh vào ranh giới đúng.

Chạy Docker/Testcontainers trong test environment có quyền, **không** chèn proxy vào hệ thống khách hàng. Khi fail phải tháo toxic trong `finally`; trong thí nghiệm dài/remote cần TTL và operator rollback ngoài process vì Java `finally` không chạy sau `kill -9`.

### 30.1. Những câu hỏi tốt cho network fault test

- Khi downstream bị trễ 1.200 ms mà timeout là 500 ms, API có trả theo contract trong một **tổng thời gian bị chặn** không?
- Khi timeout xảy ra, số retries có bị giới hạn không?
- Connection pool có bị đầy/không trả connections không?
- Cắt downstream 10 giây làm business SLI/queue thay đổi bao nhiêu?
- Khi gỡ toxic, hệ thống phục hồi đến mức baseline trong thời gian dự kiến không?
- Trạng thái degraded có được đánh dấu trong response/metrics không?
- Retry GET có an toàn nhưng retry POST có idempotency key không?

## 31. Timeout, retry budget, exponential backoff và jitter

Một retry policy production cần cùng lúc:

1. **Connect timeout** và **read/response timeout** phù hợp từng downstream.
2. **Overall deadline** của request, kể cả tất cả attempts và delays.
3. **Số attempts tối đa**, phân biệt retryable exception/status.
4. **Backoff và jitter** giảm đồng bộ thác lũ requests.
5. **Retry budget** kiểm tổng lưu lượng retry theo người dùng/service.
6. **Idempotency semantics**: GET thường an toàn hơn POST thanh toán, nhưng GET vẫn có thể kích hoạt backend side effects bất thường.
7. **Cancellation** khi caller disconnect/deadline hết.
8. **Observability**: số attempts, retries exhausted, fallback rate, circuit state.

Ví dụ với retry hai attempts và arrival rate 100 RPS:

```text
Input to API:               100 requests/s
If each downstream call fails and is retried once:
Potential outbound attempts: ~200 calls/s
If 3 service layers each retry 2 times:
Worst-case attempt multiplication can grow dramatically.
```

Đó là **retry amplification**. Một unit test assert đúng 2 calls là cần, nhưng không chứng minh 2 calls này an toàn dưới tải. Phải kiểm network/worker capacity và retry rate trong load/fault experiment.

### 31.1. Không retry lỗi không phục hồi

Không retry tùy tiện:

- `400` input invalid.
- `401` token sai/hết hạn nếu không có authorized refresh logic.
- `403` thiếu quyền.
- `404` khi contract xác nhận resource không tồn tại.
- JSON schema sai/response SKU không khớp.
- Non-idempotent POST đã có thể commit mà client chưa nhận response.

HTTP 429 có `Retry-After` cần policy riêng. Bài demo chỉ retry 503 và IO failure vì đó là scope rõ, không suy diễn mọi 5xx đều giống nhau.

## 32. Circuit breaker, bulkhead và fallback: đúng nghĩa từng cơ chế

**Retry:** thử lại một thao tác có thể thất bại thoáng qua. Không làm service “khỏe” hơn nếu upstream đang quá tải và mọi retry cùng đổ vào.

**Circuit breaker:** theo dõi lỗi trong một cửa sổ, tạm chặn call khi vượt ngưỡng, thường có trạng thái CLOSED/OPEN/HALF_OPEN. Test phải kiểm transitions theo policy, không chỉ verify một exception.

**Bulkhead:** giới hạn concurrent tasks/connections để một integration không chiếm hết thread/connection pool, giúp bảo vệ phần còn lại.

**Rate limiter:** hạn chế lưu lượng, khác circuit breaker (phản ứng với lỗi). **Timeout:** hạn chế thời gian chờ, khác retry (số lần cố gắng).

**Fallback:** trả cách ứng xử thay thế (cached read, unknown, async receipt) theo domain. Một fallback business sai có thể còn tệ hơn HTTP 503. Không dùng fallback `available=false` để che sự cố hàng tồn kho nếu UI cần phân biệt “hết hàng” và “không xác định”.

Trong Spring Boot thực tế có thể dùng Resilience4j/Spring Cloud CircuitBreaker hoặc client-specific policies. Tests cần dùng real configured aspects/interceptors; **Mockito ném exception vào service không tự chứng minh circuit breaker annotation hoặc bulkhead wiring đã chạy**.

## 33. Lỗi tác động rộng hơn API: dữ liệu, idempotency và side effects

Với GET chỉ đọc tồn kho, fallback UNKNOWN khá an toàn. Nhưng các tác vụ **có side effect** như thanh toán, gửi email, đặt vé cần fault tests nghiêm hơn:

- Network timeout có thể xảy ra **sau** khi downstream đã commit.
- Retrying POST không idempotency key có thể tạo hai giao dịch.
- Message broker `at-least-once` có thể deliver trùng.
- Khi DB failover, transaction có thể commit nhưng client chưa biết.
- Circuit breaker/fallback có thể che “payment pending” thành “payment failed”, khiến user retry sai.
- Transaction rollback của test thread không tự undo server-side commit trong real HTTP test.
- Một load test ghi dữ liệu không có cleanup có thể làm bẩn dataset và ảnh hưởng capacity đo.

Đối với mutation API, kiểm state **trước/sau** lỗi, idempotency key, outbox/unique constraints và hậu điều kiện trên DB/queue. Không chỉ assert response code rồi coi business integrity được bảo đảm.

## 34. Quan sát hệ thống: bốn golden signals và business SLI

Trong Spring Boot 3.5 với Actuator/Micrometer, HTTP server observations tạo metrics như `http.server.requests` theo cấu hình. Để diễn giải đúng một thí nghiệm, nên theo dõi:

- **Latency:** p50/p95/p99 từ client lẫn server, phân tách endpoint/status/degraded.
- **Traffic:** incoming RPS, outbound attempts/RPS, concurrency.
- **Errors:** 4xx/5xx, connection failures, timeouts, malformed responses, retry exhausted.
- **Saturation:** CPU, memory, GC pauses, thread pools, HTTP connection pool, DB pool, event backlog.
- **Business SLI:** availability results `REMOTE` vs `FALLBACK`, checkout success, stale cache age.
- **Recovery:** thời gian từ remove fault đến p95/error/business SLI trở lại baseline.
- **Integrity:** duplicate payments/orders, missing events, orphan records, retry side effects.

**Đừng chỉ xem average latency.** Outliers kéo trải nghiệm tail; p95 và p99 quan trọng nhưng phải ghi sample count. Với nhiều tags, tránh gắn user IDs/high-cardinality request IDs vào metrics labels — tốn memory và chi phí, dễ làm metrics backend quá tải. Correlation/request IDs phù hợp hơn trong structured logs/traces.

### 34.1. Quan hệ p95 và throughput

Một p95 tốt ở tải 10 RPS không hứa p95 tốt ở 100 RPS. Khi system saturation tăng, queueing có thể làm tail latency tăng đột ngột trong khi throughput bắt đầu chững. Một load run cần **cùng lúc** kiểm achieved RPS, drops, latency, business success, saturation, rồi mới kết luận capacity tại workload ấy.

## 35. Thiết kế thí nghiệm: hypothesis, blast radius, abort, rollback

Một fault experiment cần có “thẻ thí nghiệm”:

| Trường | Ví dụ có thể kiểm |
|---|---|
| Giả thuyết | Khi stub stock 503 trong 10 s, GET trả UNKNOWN/degraded trong overall deadline và phục hồi sau gỡ fault |
| Phạm vi | Local Docker network, một application instance, một stub URL |
| Workload | 5 RPS, tối đa 30 s, test SKU BOOK, no persistent writes |
| Fault | HTTP 503 10 s, hoặc 1,2 s network latency |
| Baseline | Healthy 200, business success 100%, p95 đo được trước |
| During condition | Retry bounded, fallback observed, no runaway connections |
| Abort | CPU/heap/queue vượt giới hạn test hoặc tác động ngoài allowlist |
| Rollback | Stub reset/remove toxic, containers dừng, connections phục hồi |
| Recovery criteria | Tỷ lệ healthy và p95 trở về khoảng baseline theo cửa sổ đo định nghĩa |
| Evidence | Config commit, tool version, metrics, request logs, timeline, result, remaining risks |

**Không bịa “recovery trong 3 giây”** nếu chưa quan sát thực. Trước khi thực nghiệm, định nghĩa mục tiêu; sau đó lưu actual results và khác biệt. Chỉ chỉnh threshold sau khi phân tích requirement, không giảm tiêu chuẩn để đổi đỏ thành xanh.

## 36. Quyền và an toàn trước khi gây lỗi

Một fault/chaos experiment không có quyền phê duyệt có thể làm gián đoạn người dùng hoặc phá dữ liệu. Quy trình tối thiểu:

1. **Môi trường cô lập** theo mặc định; không target production/shared system.
2. Có **người chịu trách nhiệm**, phạm vi dịch vụ, dữ liệu synthetic và thời hạn rõ.
3. Bảo đảm test account/credentials, network allowlist và namespaces chỉ có quyền tối thiểu.
4. Giới hạn RPS/concurrency/CPU, không dùng unbounded stress hoặc loops không thể dừng.
5. Preflight dashboards/alerts/runbook và rollback trước khi tiêm fault.
6. Có **abort trigger** được đo liên tục; khi vượt giới hạn, dừng workload/gỡ lỗi.
7. Dọn test resources/containers/records; giữ bản ghi evidence và phát hiện orphan objects.
8. Nếu team yêu cầu production chaos, chỉ thực hiện qua quy trình change/incident approval riêng, canary nhỏ và SLO/error-budget safeguards. Bài này **không cấp quyền** làm điều đó.

**Test không nên tự thử “giết pod production để xem sao”.** Kỹ thuật chi tiết cần đúng môi trường và quyền. Load script của bài có guard chỉ target loopback; khi muốn nhắm staging phải làm rõ scope và phê duyệt trước khi thay guard.

## 37. CI/CD: pipeline theo tín hiệu và mức rủi ro

| Tầng CI | Khi nào | Loại kiểm tra | Fail conditions |
|---|---|---|---|
| PR mỗi commit | Nhanh | Unit/contract/controller/client slices | Status/schema/retry count sai |
| PR hoặc merge | Vài phút | Full Spring integration + isolated dependencies | Wiring/HTTP/DB side effects sai |
| Nightly | Môi trường ổn định | Baseline load có thresholds | p95, business success, RPS không đạt |
| Scheduled resilience | Tách khỏi shared CI | WireMock/Toxiproxy failures under bounded load | Không degrade/không recover/duplicate |
| Release candidate | Gần topology thực | Soak/stress/controlled failover | Capacity/availability/integrity |
| Production operations | Có approval riêng | Synthetic probes/chaos canary nếu được phép | Runbook abort/rollback |

**Không nhất thiết chạy stress/chaos mọi PR.** Chúng có thể quá đắt, gây tranh chấp tài nguyên, và đòi preflight/rollback. PR nên bảo vệ functional behavior ở giá thành thấp nhất; nightly/pre-release tăng fidelity. Cần lưu **test configuration và environment version** để so sánh công bằng giữa các lần chạy.

## 38. Những sai lầm khi kết luận từ kết quả test

| Kết luận sai | Vì sao sai | Cách nói đúng |
|---|---|---|
| “JUnit test pass nên hệ thống chịu 1.000 RPS” | Không có workload | “Contract pass ở test inputs” |
| “MockRestServiceServer trả 503 nên đã test mạng lỗi” | Không có socket | “Kiểm response/error handling bằng mock factory” |
| “Load test HTTP errors 0% nên user không bị ảnh hưởng” | 200 degraded không được tính | Đo business SLI và dữ liệu |
| “p95 tốt nên không có issue” | Throughput/drops có thể thấp | Báo achieved RPS và dropped iterations |
| “Một 200 response đủ chứng minh p99” | Không có phân phối | Đo đủ mẫu và thời gian |
| “Stress test staging giống production” | Topology/dataset khác | Nêu điều kiện tương đồng và sai khác |
| “Chaos test xong vẫn 200 nên recovered” | Có thể fallback mãi | Kiểm healthy rate sau gỡ fault |
| “Retry hai lần luôn giúp availability” | Retry storm khi outage | Retry budget/backoff/circuit breaker |
| “AT_LEAST_ONCE có nghĩa exactly once” | Duplicates có thể xuất hiện | Idempotency/outbox tests |
| “Test DB rollback nên network HTTP không ghi thật” | Transactions khác threads | Kiểm server side state |
| “Chạy k6 từ laptop là capacity của cluster” | Load generator/network khác | Ghi topology, đo saturation |
| “503 lỗi là permission issue” | Status riêng của upstream | Contract-specific error mapping |
| “Bật chaos không cần rollback vì cuối test cleanup” | Process kill có thể không chạy finally | TTL + external recovery |
| “Đổi p95 target cho phù hợp kết quả” | Test threshold thành vanity metric | Đặt target từ SLO trước run |
| “Circuit breaker test bằng exception Mockito đủ” | Aspect/wiring có thể không chạy | Test configured circuit state và runtime |
| “K6 checks fail nên k6 tự return nonzero” | Checks đơn lẻ không fail run | Dùng thresholds |

## 39. Bài tập và gợi ý lời giải

### A — Functional hay load?

Một test gửi 100 request tuần tự và assert mỗi request có status 200. Có thể gọi đây là load test chứng minh concurrency không?

**Đáp án:** Không đủ. Có thể xem là functional repetition, chưa có arrival model, concurrency mục tiêu, measurement distributions, achieved RPS và saturation. Thêm workload generator có profile/thresholds nếu muốn đo tải.

### B — Mocked 503 và chaos

Trong `@RestClientTest`, MockRestServiceServer trả 503. Bạn nói “đã kiểm network outage recovery”. Sai ở đâu?

**Đáp án:** Mock factory không tạo TCP socket hoặc network interruption thật. Chỉ chứng minh adapter map 503 đúng. Test recovery under network outage cần WireMock/Toxiproxy/cluster fault phù hợp.

### C — Retry 503

Gateway thất bại lần 1, success lần 2. Số attempts mong đợi và degraded flag là gì?

**Đáp án:** Hai attempts, final response REMOTE và `degraded=false`. Từ chối 3+ attempts nếu retry budget là 2.

### D — Fallback 200

Một nửa requests trả `UNKNOWN/degraded=true` nhưng HTTP status 200. `http_req_failed` có bảo đảm phản ánh 50% business failures không?

**Đáp án:** Không. Cần metric/check theo domain như `business_healthy` và threshold riêng.

### E — Missing load

K6 target 100 iterations/s nhưng `dropped_iterations=1.000`. Kết luận app đáp ứng đúng 100 RPS dựa vào p95 được không?

**Đáp án:** Không. Offered rate và achieved rate khác nhau; load generator hoặc hệ thống đã không đạt workload. Đọc drops, VU allocation và request counts.

### F — Percentile

5 requests có latencies 10, 15, 20, 30, 5.000 ms. Average và p95 có thể mô tả trải nghiệm một cách ổn định không?

**Đáp án:** Không. Sample quá nhỏ, có outlier rất lớn; phải đo workload đủ dài/ổn định, báo số mẫu và tail distribution.

### G — Restore

Thí nghiệm inject 503 trong 15 s, rồi reset stub. Vì sao cần thêm phase recovery?

**Đáp án:** Circuit breaker, pool/queue, retries và cache state có thể tiếp tục lỗi sau khi upstream hồi phục. Cần đo time to healthy và hậu điều kiện.

### H — Tác dụng phụ

POST thanh toán timeout sau khi đã commit; client retry, tạo hai charge. Functional HTTP 503 test có bắt được không nếu không kiểm DB/payment state?

**Đáp án:** Không. Cần idempotency key/transaction/outbox và test side effects, không chỉ response.

### I — Load generator

Một máy k6 CPU 100% trong khi server CPU 20%, dropped iterations tăng. Bottleneck nằm ở đâu?

**Đáp án:** Chưa thể kết luận server đạt giới hạn. Cần kiểm load generator resources, network, preAllocatedVUs và thử load generation phân tán/đủ capacity.

### J — Circuit breaker

Một test gọi `@CircuitBreaker` annotated service thông qua `new Service()`, rồi assert exception. Có chứng minh AOP breaker wiring không?

**Đáp án:** Không. Annotation trên Java object tự tạo có thể không qua Spring proxy; phải kiểm bean/context và breaker state thực.

### K — Quyền chạy fault

Nhóm muốn ngắt egress trên namespace production để “xem hệ thống có bền không”, chưa có phê duyệt và rollback. Bạn nên làm gì?

**Đáp án:** Không thực hiện. Thử trên isolated test topology, lập hypothesis/guardrails/owner và xin phê duyệt riêng nếu bắt buộc thử production.

### L — Correctness vs speed

Load test p95 dưới 100 ms nhưng 10% requests trả SKU khác. Pass hay fail?

**Đáp án:** Fail về business correctness dù latency nhanh. Performance metrics không thay kiểm hợp đồng.

### M — Monitoring degraded

Nếu application cố tình trả UNKNOWN với HTTP200 khi upstream down, nên thêm metric nào?

**Gợi ý:** degraded response ratio, fallback cause, retry attempts, status by endpoint và business-success SLI.

### N — Overall timeout

Client có read timeout 500ms, 3 retries và backoff 200ms. Có thể cam kết API sẽ xong trong 500ms không?

**Đáp án:** Không. Tổng deadline có thể vượt 500 ms qua nhiều attempts/queue/connection delay. Cần overall time budget và test bounded real elapsed behavior.

### O — Load test SLO

Một PR có thể tự động chạy JUnit mỗi commit. Có nên chuyển test tải 30 phút, stress phá giới hạn và chaos network partition vào cùng stage PR mặc định?

**Đáp án:** Thường không. Chọn nightly/release isolated environment với thresholds/guardrails; PR tập trung fast deterministic contract tests.

## 40. Checklist review và nghiệm thu

- [ ] Mục tiêu của từng test được viết thành câu hỏi cụ thể.
- [ ] Functional test assert input/status/body/headers và side effects đúng.
- [ ] Contract tests kiểm đúng consumer/provider semantics, không chỉ stub JSON.
- [ ] `@WebMvcTest`/MockMvc không bị gọi là real network test.
- [ ] `@RestClientTest`/MockRestServiceServer không bị gọi là network outage test.
- [ ] `@SpringBootTest(RANDOM_PORT)` được phân biệt rõ với MockMvc/mock downstream.
- [ ] Đã có test 503 transient rồi success và 503 exhausted.
- [ ] Đã có test non-retryable contract error.
- [ ] Retry attempts bounded, không catch tất cả exceptions.
- [ ] Fallback không giả dữ liệu kinh doanh sai.
- [ ] Degraded business responses có marker và metric riêng.
- [ ] HTTP200 degraded không bị tự tính là business success.
- [ ] Timeouts/connect/read/overall được cấu hình khi chạy network faults thật.
- [ ] Có backoff/jitter/budget/circuit breaker nếu là system chịu tải production.
- [ ] Mọi retry POST/mutation có idempotency policy.
- [ ] Có kiểm DB/queue/external side effects dưới failure nếu cần.
- [ ] Workload có target RPS/VUs, duration và dataset rõ.
- [ ] Đã biết chọn open vs closed arrival model.
- [ ] K6 `checks` và `thresholds` không bị nhầm.
- [ ] Theo dõi p95/p99 và sample count, không chỉ average.
- [ ] Theo dõi achieved RPS và `dropped_iterations`.
- [ ] Theo dõi saturation của app/DB/connection pool/load generator.
- [ ] SLO/threshold được đặt trước khi chạy, có nguồn requirement.
- [ ] Có baseline trước lỗi, during fault và recovery sau lỗi.
- [ ] Fault type/intensity/TTL/target được ghi rõ.
- [ ] Fault chỉ đánh đúng network dependency đã định.
- [ ] Thử nghiệm lỗi được mặc định cô lập, dùng test data.
- [ ] Có owner, blast radius, abort criterion, rollback và cleanup.
- [ ] Không tự gây chaos vào production/shared system khi chưa được phê duyệt.
- [ ] Test không sửa/đụng dữ liệu khách hàng hoặc giữ secrets trong logs.
- [ ] Có artifacts metrics/traces/annotations/timeline cho từng run.
- [ ] Có phân biệt simulated fault với failure của hạ tầng thực.
- [ ] Có kiểm recovery metrics và data integrity, không chỉ status 200.
- [ ] Có ghi environment topology, tool version và runtime version.
- [ ] Kết quả nghiệm thu ghi rõ những gì đã chạy thật, những gì chỉ là mã mẫu.
- [ ] Không tuyên bố load/chaos pass từ JUnit contract-only suite.

**Kết luận:** Ranh giới của ba nhóm kiểm thử là **ranh giới của bằng chứng**. JUnit/MockMvc/MockRestServiceServer có thể kiểm cực kỳ chính xác *hợp đồng chức năng và hành vi xử lý lỗi đã lập trình*, nhưng không đo throughput hoặc áp lỗi mạng thật. K6 có thể đo RPS, p95 và business SLI dưới một workload xác định, nhưng không thay kiểm tính đúng của từng nhánh nghiệp vụ. WireMock/Toxiproxy và chaos experiments có thể áp sự cố có giới hạn để đo degraded mode, retry amplification và phục hồi, nhưng phải có **baseline, blast radius, abort, rollback và quan sát hậu điều kiện**. Đánh giá hệ thống vững chỉ khi các kết quả này được ghép lại với phạm vi, giả thuyết và giới hạn trung thực.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — Testing Spring Boot Applications, `@WebMvcTest`, `@RestClientTest` và `RANDOM_PORT`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `RestClient` status handlers/client factories: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Boot 3.5 — Actuator/Micrometer metrics, `http.server.requests`: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Grafana k6 — Thresholds, `checks` khác `thresholds`: https://grafana.com/docs/k6/latest/using-k6/thresholds/
- Grafana k6 — HTTP API load testing: https://grafana.com/docs/k6/latest/testing-guides/api-load-testing/
- Grafana k6 — Constant arrival rate executor: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/
- Grafana k6 — Arrival rate, preAllocatedVUs và dropped iterations: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/arrival-rate-vu-allocation/
- WireMock — Simulating Faults (delays, resets, bad responses): https://wiremock.org/docs/simulating-faults/
- WireMock — Stubbing and Verifying HTTP interactions: https://wiremock.org/docs/stubbing/
- Testcontainers for Java — Toxiproxy network faults: https://java.testcontainers.org/modules/toxiproxy/
- Principles of Chaos Engineering — hypotheses, steady state, blast radius: https://principlesofchaos.org/
- Google SRE Workbook — Service Level Objectives and error budgets: https://sre.google/workbook/implementing-slos/
