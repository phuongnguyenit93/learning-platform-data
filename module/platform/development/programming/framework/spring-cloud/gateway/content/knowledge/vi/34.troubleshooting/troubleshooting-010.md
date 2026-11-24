# Retry gây thao tác trùng hoặc circuit breaker mở ngoài dự kiến

## 1. Triệu chứng: request lỗi một lần nhưng hệ thống thực hiện nhiều lần

Một API Gateway có thể tự động **retry** khi upstream timeout hoặc trả lỗi tạm thời. Điều này giúp GET phục hồi sau một lần lỗi mạng. Nhưng nếu cùng cơ chế được áp dụng cho thao tác ghi dữ liệu, một request của client có thể tạo ra nhiều lần thực thi nghiệp vụ:

- Khách hàng nhấn “Thanh toán” một lần nhưng thấy hai giao dịch.
- BFF gọi `POST /orders` một lần, Gateway retry, backend tạo hai order.
- Một service đã trừ tồn kho nhưng response bị mất; lần retry tiếp tục trừ tồn kho.
- Nhiều lớp Gateway, LoadBalancer và WebClient cùng retry làm số lần gọi backend tăng theo cấp số nhân.
- Circuit breaker liên tục chuyển sang **OPEN** dù backend đã phục hồi, vì cấu hình đếm lỗi/slow calls hoặc health probe chưa phù hợp.

Ở chiều ngược lại, circuit breaker có thể **mở quá sớm** trong một đợt traffic thấp, hoặc fallback trả HTTP 200 khiến dashboard tưởng hệ thống khỏe trong khi thao tác thật chưa được thực hiện.

Bài **“Retry gây thao tác trùng hoặc circuit breaker mở ngoài dự kiến”** thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_GATEWAY**. Ta sẽ phân tích retry, idempotency, circuit breaker, thứ tự filter và retry budget xuyên các tầng. Mục tiêu là tìm được **lý do thật của một thao tác trùng hoặc một breaker OPEN**, thay vì tăng số lần retry hay nới ngưỡng một cách cảm tính.

Sau bài, bạn có thể:

1. Phân biệt retry do client, Gateway, Spring Cloud LoadBalancer và downstream WebClient.
2. Giải thích vì sao timeout không chứng minh backend chưa commit.
3. Thiết kế idempotency key và lưu kết quả chống thực thi trùng.
4. Chỉ retry những lỗi tạm thời và thao tác có semantics phù hợp.
5. Đọc state CLOSED/OPEN/HALF_OPEN và cấu hình Resilience4j theo traffic.
6. Phân tích ảnh hưởng của filter order giữa Retry và CircuitBreaker.
7. Dùng metrics/events/traces để tìm nguyên nhân breaker mở bất thường.
8. Viết test chứng minh số lần thực thi nghiệp vụ, không chỉ số HTTP requests.

> **Nguyên tắc cốt lõi:** Retry có thể gửi lại request; nó không thể tự biết thao tác trước đã commit hay chưa. Circuit breaker ngăn gọi vào upstream đang có vấn đề; nó không tự hoàn tác side effect và không thay thế idempotency.

## 2. Phân biệt Retry và Circuit Breaker

| Cơ chế | Câu hỏi mà nó trả lời | Hành vi | Không đảm bảo |
| --- | --- | --- | --- |
| Retry | “Lỗi này có thể tạm thời, thử lại được không?” | Gửi lại request theo policy/attempt budget | Không đảm bảo thao tác chưa chạy lần trước |
| Circuit breaker | “Upstream đang có dấu hiệu không khỏe, có nên tạm ngừng gọi?” | Đếm outcomes/slow calls, mở mạch và từ chối sớm | Không sửa lỗi backend, không tự retry |
| Timeout | “Chờ tối đa bao lâu cho một call?” | Hủy/chấm dứt chờ khi quá deadline | Không chứng minh server đã dừng xử lý |
| Bulkhead/concurrency limit | “Cho phép bao nhiêu calls đồng thời?” | Giới hạn tài nguyên/độ đồng thời | Không bảo đảm kết quả nghiệp vụ đúng |
| Idempotency | “Cùng một ý định được gửi nhiều lần thì kết quả là gì?” | Nhận diện và trả lại kết quả đã xử lý | Không thay authorization hoặc transaction design |

### 2.1. Ví dụ request timeout nhưng order đã được tạo

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as Orders service
    participant DB as Database
    C->>G: POST /orders
    G->>O: POST /orders
    O->>DB: INSERT order
    DB-->>O: COMMIT OK
    O--xG: Response bị mất trên mạng
    G->>G: Timeout → Retry
    G->>O: POST /orders (lần 2)
    O->>DB: INSERT order lần nữa
    DB-->>O: COMMIT OK
    O-->>G: 201 Created
    G-->>C: 201 Created
~~~

Client chỉ thấy một response thành công, nhưng DB có thể có **hai orders**. Nếu retry tiếp tục ở client vì response lần đầu không đến được client, số lần thực thi còn tăng.

### 2.2. Timeout là trạng thái không chắc chắn

Khi Gateway nhận timeout, có ít nhất ba khả năng:

1. Backend chưa nhận request.
2. Backend đã nhận nhưng chưa commit và có thể đã hủy.
3. Backend đã commit side effect, nhưng response không quay về kịp.

Gateway không thể phân biệt ba trường hợp chỉ từ exception timeout. **Không được suy luận “timeout = chưa thực hiện”** rồi retry một lệnh ghi không idempotent.

## 3. Retry ở những tầng nào?

Một hệ thống microservices có thể retry tại nhiều nơi:

~~~text
Browser / Mobile
    │  client retry (mất response)
    ▼
Ingress / Load Balancer
    │  proxy retry (nếu được cấu hình)
    ▼
Spring Cloud Gateway
    │  Retry GatewayFilter
    ▼
Spring Cloud LoadBalancer
    │  retry instance selection (nếu bật)
    ▼
BFF / Orders service
    │  WebClient / Resilience4j Retry
    ▼
Database / Message broker / Payment provider
~~~

### 3.1. Số lần thực thi có thể nhân lên

Giả sử mỗi tầng cho phép tối đa:

| Tầng | Attempts tối đa (ví dụ) |
| --- | ---: |
| Client | 2 |
| Gateway Retry | 3 |
| LoadBalancer | 2 |
| BFF WebClient | 3 |

Worst-case lý thuyết có thể lên tới:

\[
2 \times 3 \times 2 \times 3 = 36
\]

**36 là phép nhân minh họa khi các tầng độc lập và đều retry đủ lần**, không phải mặc định Spring Cloud Gateway. Thực tế còn phụ thuộc exception, timeout, filter order, cancellation, LoadBalancer policy và các nhánh fallback. Tuy nhiên nó cho thấy không thể đánh giá retry từng lớp tách biệt.

### 3.2. Retry budget xuyên các tầng

Một request nên có **một ngân sách retry tổng thể**: deadline, số attempts tối đa và nhóm lỗi cho phép. Nếu Gateway đã dùng hai attempts, BFF không nên tự động mở thêm ba attempts mà không tính tổng deadline/tải.

Khuyến nghị:

- Chọn **một tầng sở hữu retry chính** cho từng hop hoặc operation.
- Tầng ngoài truyền deadline/correlation/idempotency key, không tạo key mới mỗi attempt.
- Các tầng trong tôn trọng deadline còn lại.
- Không retry lại lỗi validation, authentication, authorization hoặc business rejection.
- Giới hạn attempts và có backoff/jitter khi phù hợp.
- Theo dõi **attempts per logical operation**, không chỉ requests per second.

## 4. Xác định loại request trước khi cấu hình Retry

| HTTP method/operation | Mặc định suy nghĩ | Điều kiện để retry |
| --- | --- | --- |
| GET đọc dữ liệu | Thường idempotent theo contract | Lỗi transient, timeout budget còn, không có side effect ẩn |
| HEAD/OPTIONS | Thường an toàn | Backend semantics đúng |
| PUT thay toàn bộ trạng thái theo resource/key | Có thể idempotent theo contract | Cùng resource, cùng payload, semantics không tạo side effects phụ |
| DELETE resource đã định danh | Có thể idempotent theo contract | DELETE lặp không tạo tác dụng phụ mới |
| POST tạo order/payment | Không retry mù quáng | Có idempotency key/deduplication bền vững |
| PATCH tăng số lượng/cộng tiền | Thường không idempotent | Cần command ID/operation ID và transaction semantics |
| POST gửi email/notification | Có thể gây gửi trùng | Deduplication/outbox/provider idempotency |

HTTP method **không đủ để quyết định idempotency**. Một GET sai thiết kế vẫn có thể cập nhật trạng thái; một POST có thể được thiết kế idempotent nếu dùng operation key và lưu kết quả. Hãy dựa vào **business contract**.

### 4.1. Retry hợp lý

Ví dụ GET catalog public trả 503 trong một lần deploy:

~~~http
GET /api/catalog/items/42
~~~

Nếu upstream không có side effect, retry giới hạn một hoặc hai lần với backoff có thể phục hồi mà không nhân giao dịch.

### 4.2. Retry nguy hiểm

Ví dụ:

~~~http
POST /api/orders
Content-Type: application/json

{"productId":"P-42","quantity":1,"paymentMethod":"wallet"}
~~~

Nếu server đã trừ tiền/ghi order mà response mất, retry có thể trừ tiền lần nữa. Việc chỉ thêm `Retry` filter không giải quyết được vấn đề.

### 4.3. Những lỗi không nên retry

- 400/422: payload/validation sai; gửi lại nguyên request không thay đổi kết quả.
- 401/403: credential/quyền sai; retry không làm token có quyền hơn.
- 404: resource không tồn tại hoặc route sai; chỉ retry khi contract xác định eventual consistency và có deadline.
- 409: conflict cần đọc trạng thái/resolve, không retry mù.
- 429: chỉ retry theo `Retry-After` và budget nếu policy cho phép; retry ngay có thể làm quá tải.
- 5xx: không phải mọi 5xx đều transient; ví dụ business exception bị map 500 cần sửa logic, không retry vô hạn.

## 5. Cấu hình Retry Gateway Filter có giới hạn

Ví dụ dưới đây chỉ áp dụng cho **GET catalog** và một số lỗi upstream tạm thời. Cú pháp minh họa theo Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - name: Retry
                  args:
                    retries: 2
                    methods:
                      - GET
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                      - GATEWAY_TIMEOUT
                    backoff:
                      firstBackoff: 50ms
                      maxBackoff: 250ms
                      factor: 2
                      basedOnPreviousValue: false
                    jitter:
                      randomFactor: 0.5
                    timeout: 800ms
~~~

Giải thích:

- `retries: 2` là **số lần retry thêm** theo contract filter, không phải cam kết tổng attempts ở toàn hệ thống; xác nhận theo version và test.
- Chỉ `GET` được retry.
- Chỉ một số status transient được chọn; không retry mọi 4xx/5xx.
- Backoff tăng dần, có giới hạn trên.
- Jitter làm lệch thời điểm retries giữa các requests; timeout giới hạn thời gian retry theo cấu hình filter.
- Ví dụ không bật retry cho `POST /orders`.

**Lưu ý:** WebFlux Gateway 4.x dùng prefix `spring.cloud.gateway.routes`; WebFlux Gateway 5.x dùng `spring.cloud.gateway.server.webflux.routes`. Không đưa cả hai prefix vào cùng một cấu hình. Kiểm tra tài liệu và runtime route/filter config theo BOM thật.

### 5.1. Có thể retry theo exception

Retry factory hỗ trợ cấu hình exception classes trong những release phù hợp, ví dụ lỗi I/O hoặc timeout. Chỉ thêm exception khi hiểu rõ call path:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 1
      methods:
        - GET
      exceptions:
        - java.io.IOException
        - java.util.concurrent.TimeoutException
~~~

Danh sách exception cụ thể phụ thuộc implementation/exception wrapping ở Reactor Netty và phiên bản. **Đừng copy nguyên danh sách rồi nghĩ mọi timeout đều được nhận diện**; dùng test với lỗi thật của stack.

### 5.2. Không cấu hình retry cho mọi route bằng default filter

Nếu đưa Retry vào `default-filters`, route admin refund, checkout, create order hoặc upload cũng có thể bị retry nếu filter không được giới hạn đúng. Ưu tiên **per-route policy** với danh sách methods/status/exception cụ thể; test route mới không vô tình kế thừa retry.

### 5.3. Retry chạy lại các filters đứng sau nó

Tài liệu Gateway nêu rõ Retry filter sẽ **retry tất cả các filters nằm sau Retry trong chain**. Vì vậy vị trí filter có thể khiến một filter khác chạy nhiều lần:

~~~text
Retry
  → AddRequestHeader
  → Custom audit filter
  → CircuitBreaker
  → Netty routing
~~~

Nếu custom filter ghi audit event, tạo operation ID hoặc gọi một dịch vụ ngoài, nó có thể bị thực thi lặp theo mỗi attempt. Đặc biệt, `AddRequestHeader` có thể tạo thêm giá trị lặp nếu request đã có cùng header. Hãy:

- Không đặt side-effecting custom filters sau Retry nếu chưa có idempotency.
- Nếu cần header kỹ thuật, dùng logic ghi đè/chuẩn hóa phù hợp thay vì append nhiều lần.
- Kiểm tra route filter order thực tế; các filter được sắp xếp theo order, không chỉ theo thứ tự nhìn thấy trong YAML.
- Dùng backend/filter counters để xác minh số lần mỗi bước được thực thi.

Đây là một nguyên nhân khiến **một request có vẻ chỉ được retry ở upstream nhưng audit/log/custom behavior cũng xuất hiện nhiều lần**.

## 6. Request body, upload và memory khi retry

Để gửi lại request có body, Gateway có thể phải **cache body** để replay. Điều này tạo chi phí bộ nhớ và có thể làm Gateway chịu áp lực khi nhiều upload/request body lớn đồng thời.

Rủi ro:

- Một body lớn có thể được giữ trong memory qua nhiều attempts.
- Nhiều request đồng thời làm tăng direct/heap memory và GC pressure.
- Streaming body không thể luôn replay an toàn như một byte array đã cache.
- Request có multipart/file upload có thể tạo duplicate writes hoặc object storage uploads.
- Nếu retry một POST có side effect, cache body chỉ giúp gửi lại bytes, **không bảo đảm idempotency**.

Khuyến nghị:

- Không bật retry rộng cho upload/streaming hoặc body lớn nếu chưa có kiểm thử memory.
- Đặt request size limits ở edge/Gateway/backend.
- Nếu phải retry, có operation ID/idempotency key và backend deduplication.
- Đo memory/GC với concurrency đại diện; không chỉ test một request nhỏ.
- Dùng object storage upload session/chunk IDs và finalize operation idempotent nếu nghiệp vụ cần upload có thể tiếp tục.

## 7. Idempotency key: cách bảo vệ thao tác ghi

Một API tạo order có thể yêu cầu client gửi:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: 01J8Q2C7D8W9M3P4
Content-Type: application/json

{"productId":"P-42","quantity":1}
~~~

### 7.1. Key phải đại diện một ý định nghiệp vụ

- Client tạo **một key cho một logical operation**.
- Mọi retries của cùng operation gửi lại **cùng key**.
- Một lần người dùng thực sự muốn tạo order mới phải có key mới.
- Gateway không tự sinh key mới cho từng retry.
- Server gắn key với **authenticated principal/tenant + operation**, không chỉ key toàn cục.
- Server lưu request fingerprint để phát hiện cùng key nhưng payload khác.

Không dùng IP/User-Agent làm key; nhiều người có thể chung NAT, một người có thể đổi IP, và các trường đó không định danh một giao dịch.

### 7.2. Bảng idempotency tối thiểu

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE idempotency_record (
    principal_id       VARCHAR(160) NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(160) NOT NULL,
    request_hash       VARCHAR(128) NOT NULL,
    state              VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(160),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (principal_id, operation_name, idempotency_key)
);
~~~

`principal_id` phải đến từ identity đã xác minh; `operation_name` giới hạn phạm vi key; `request_hash` là hash canonical của payload/semantic inputs. TTL phải đủ dài cho client retry/reconciliation, có cleanup và không xóa record khi operation còn xử lý.

### 7.3. Luồng xử lý an toàn

~~~mermaid
flowchart TD
    A["POST + authenticated principal + idempotency key"] --> B["Validate key, hash request"]
    B --> C{"Record đã tồn tại?"}
    C -->|"Chưa"| D["Atomic insert PROCESSING"]
    D --> E["Thực hiện business transaction"]
    E --> F["Commit result + response snapshot"]
    F --> G["Trả response"]
    C -->|"Có, cùng hash + COMPLETED"| H["Replay stored result"]
    C -->|"Có, hash khác"| I["409 Conflict"]
    C -->|"Có, PROCESSING"| J["Wait/poll hoặc 409/202 theo contract"]
~~~

Phần insert/lock phải **atomic**. Nếu hai request cùng key đến đồng thời, unique constraint/transaction phải bảo đảm chỉ một request thực hiện nghiệp vụ; request còn lại đọc kết quả hoặc trả trạng thái đang xử lý.

### 7.4. Không chỉ dùng ConcurrentHashMap trong production

Một map trong memory:

~~~java
Map<String, OrderResponse> results = new ConcurrentHashMap<>();
~~~

chỉ có thể minh họa ý tưởng. Nó không bảo vệ giữa nhiều replicas, mất dữ liệu khi process restart, không đồng bộ transaction với DB và không xử lý crash giữa side effect với lưu response. Dùng **database unique constraint/transaction** hoặc một idempotency store có semantics nhất quán.

### 7.5. Side effect ngoài database cần Outbox hoặc provider idempotency

Nếu order service:

1. ghi order trong DB;
2. gọi payment provider;
3. phát event;

thì idempotency record trong DB không tự đảm bảo payment/event chỉ xảy ra một lần. Cần:

- Provider idempotency key cho payment nếu được hỗ trợ.
- Transactional outbox để commit domain state + event record cùng transaction.
- Consumer deduplication/inbox theo event ID.
- Saga/compensation cho workflow nhiều service, không giả định transaction phân tán tự rollback.

**Exactly-once end-to-end** không được tạo chỉ bằng một header. Thiết kế thường là at-least-once delivery + idempotent processing/deduplication ở từng side effect.

## 8. Circuit breaker: hiểu state trước khi chỉnh ngưỡng

Circuit breaker theo dõi kết quả các calls tới một dependency và chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate / slow-call rate vượt ngưỡng\nvà đủ minimum calls
    OPEN --> HALF_OPEN: Hết wait duration
    HALF_OPEN --> CLOSED: Probe calls đạt policy
    HALF_OPEN --> OPEN: Probe calls thất bại / quá chậm
~~~

| State | Ý nghĩa | Hành vi |
| --- | --- | --- |
| **CLOSED** | Mạch bình thường | Calls được phép; kết quả được ghi vào sliding window |
| **OPEN** | Dependency đang bị coi là không khỏe | Calls bị từ chối nhanh, thường phát sinh `CallNotPermittedException` |
| **HALF_OPEN** | Đang thử phục hồi | Chỉ cho phép một số probe calls; kết quả quyết định đóng lại hay mở tiếp |

### 8.1. Failure rate và slow-call rate khác nhau

- **Failure rate:** tỷ lệ calls bị coi là thất bại trong cửa sổ thống kê.
- **Slow-call rate:** tỷ lệ calls vượt `slowCallDurationThreshold`.
- **Minimum number of calls:** số lượng tối thiểu trước khi tính threshold; tránh mở breaker từ một mẫu quá nhỏ.
- **Sliding window:** số lượng calls gần nhất (`COUNT_BASED`) hoặc khoảng thời gian (`TIME_BASED`) được dùng để tính.

Ví dụ:

~~~text
slidingWindowSize = 20
minimumNumberOfCalls = 10
failureRateThreshold = 50%

Trong một cửa sổ đủ 10 calls:
  5 calls bị record failure → failure rate = 50%
  breaker có thể chuyển OPEN theo policy
~~~

Đây là **ví dụ số học**, không phải giá trị mặc định của Resilience4j hay Gateway. Một số lần timeout ở traffic thấp có thể không đủ `minimumNumberOfCalls`; ngược lại, threshold thấp và traffic dồn dập có thể làm breaker mở rất nhanh.

### 8.2. Vì sao HALF_OPEN không phải health check hoàn hảo?

Probe calls trong HALF_OPEN là **request thật** được cho phép đi tới dependency. Nếu một probe là POST không idempotent, nó vẫn có thể gây side effect. Vì vậy:

- Không để breaker probe thực hiện thao tác ghi nguy hiểm nếu không có idempotency.
- Ưu tiên read-only health/diagnostic operation riêng nếu mô hình breaker cho phép, nhưng nhớ rằng Gateway CircuitBreaker thường bảo vệ calls của route chứ không tự gọi health endpoint.
- Giới hạn `permittedNumberOfCallsInHalfOpenState`.
- Theo dõi trạng thái và số probe thực tế; tránh một đợt probe lớn gây quá tải backend vừa phục hồi.

## 9. Cấu hình CircuitBreaker Gateway Filter và Resilience4j

Để dùng CircuitBreaker GatewayFilter với Reactor/WebFlux, project cần Spring Cloud CircuitBreaker Reactor Resilience4j starter tương thích BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Ví dụ route catalog/orders:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - name: CircuitBreaker
                  args:
                    name: orders-read
                    fallbackUri: forward:/fallback/orders
                    statusCodes:
                      - 500
                      - 502
                      - 503
                      - 504
~~~

`fallbackUri` dạng `forward:` chuyển tiếp nội bộ trong Gateway application tới handler fallback. Fallback **không phải một backend khác tự động được bảo vệ**; code fallback phải có timeout, không gọi lại cùng upstream đang OPEN và không biến lỗi thành dữ liệu thành công giả.

### 9.1. Cấu hình Resilience4j theo workload

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      orders-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Các giá trị trên là **giá trị lab để minh họa**, không phải production recommendation. Ví dụ đang coi một call trên 2 giây là slow; nếu SLO thực của orders là 300 ms, threshold đó quá rộng. Nếu upstream thường mất 3 giây trong batch export, cùng threshold lại có thể quá chặt.

Các property quan trọng:

| Property | Ý nghĩa | Sai cấu hình thường thấy |
| --- | --- | --- |
| `slidingWindowType` | COUNT_BASED hoặc TIME_BASED | Chọn cửa sổ không hợp với traffic |
| `slidingWindowSize` | Số calls hoặc độ dài window theo type | Quá nhỏ, kết quả dao động |
| `minimumNumberOfCalls` | Mẫu tối thiểu trước khi tính rate | Quá thấp khiến vài lỗi mở breaker |
| `failureRateThreshold` | Tỷ lệ failures để mở | Quá thấp với dependency có lỗi transient |
| `slowCallRateThreshold` | Tỷ lệ slow calls để mở | Nhầm slow threshold với request timeout |
| `slowCallDurationThreshold` | Thời gian phân loại một call là slow | Không khớp SLO/timeout thực tế |
| `waitDurationInOpenState` | Thời gian ở OPEN trước khi thử HALF_OPEN | Quá ngắn tạo probe liên tục |
| `permittedNumberOfCallsInHalfOpenState` | Số calls được probe | Quá nhiều làm backend vừa phục hồi bị dồn tải |
| `automaticTransitionFromOpenToHalfOpenEnabled` | Tự chuyển state sau wait duration | Hiểu nhầm không cần probe traffic |

### 9.2. Record và ignore exceptions có chủ đích

Resilience4j CircuitBreaker có thể cấu hình exception được ghi nhận là failure và exception bị bỏ qua. Cần phân biệt:

- Lỗi upstream như connection failure, timeout hoặc 5xx có thể là failure.
- `CallNotPermittedException` nghĩa breaker **đã OPEN trước khi call upstream**, không phải một lỗi mới của upstream.
- Lỗi validation/authorization ở tầng caller không nên làm dependency breaker mở.
- Một fallback exception có thể phát sinh sau khi breaker đã mở; không nên tính nó như backend failure nếu metric/record policy đang đo sai tầng.

Không copy `recordExceptions`/`ignoreExceptions` nếu chưa biết exception thật đang được wrap bởi Reactor/Netty. Dùng traces/logs để xác định class cause chain rồi cấu hình theo version. Khi cấu hình explicit `recordExceptions`, cần kiểm tra semantics của các exception không nằm trong danh sách và kiểm thử cả success, ignored, recorded failures.

## 10. Fallback: đừng biến lỗi thành thành công giả

Ví dụ fallback controller WebFlux:

~~~java
package demo.gateway.fallback;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersFallbackController {

    @GetMapping("/fallback/orders")
    public Mono<ResponseEntity<Map<String, Object>>> ordersFallback() {
        return Mono.just(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .header("Retry-After", "5")
                        .body(Map.of(
                                "code", "ORDERS_TEMPORARILY_UNAVAILABLE",
                                "message", "Vui lòng thử lại sau",
                                "retryable", true)));
    }
}
~~~

Ví dụ trả 503 có mã lỗi rõ và không giả lập một order rỗng như thành công. Nếu BFF có thể trả **stale cached catalog** trong fallback, phải ghi rõ thời điểm dữ liệu và không dùng cách này cho quyền, tồn kho, số dư hoặc trạng thái payment cần chính xác.

### 10.1. Fallback không tự retry

Nếu fallback gọi lại `lb://orders-service` bằng WebClient mà không có budget riêng, nó có thể gọi chính dependency đang OPEN, tạo vòng lặp:

~~~text
Route → CircuitBreaker OPEN → fallback
  → WebClient orders-service
  → cùng dependency đang lỗi
  → fallback/error handler
~~~

Fallback nên trả degraded response đã định nghĩa, đọc cache an toàn hoặc chuyển sang queue/job theo contract. Không đặt logic fallback tạo order/payment mới.

### 10.2. Tránh trả 200 cho thao tác chưa hoàn tất

Với POST tạo order, fallback:

~~~json
{"status":"accepted","orderId":"unknown"}
~~~

trả 200/202 có thể làm client nghĩ giao dịch đã thành công. Nếu thao tác chưa commit hoặc chưa biết kết quả, trả trạng thái **pending/unknown** theo contract, cung cấp operation ID để tra cứu và tránh client gửi lệnh mới với key khác. Không tự khẳng định thất bại nếu backend có thể đã commit; dùng idempotency key để reconcile.

## 11. Circuit breaker mở ngoài dự kiến: đọc số liệu trước khi chỉnh ngưỡng

Khi breaker OPEN, hỏi theo thứ tự:

1. Breaker instance nào đang OPEN? Tên có được chia sẻ bởi nhiều routes không?
2. Có đủ `minimumNumberOfCalls` chưa?
3. Failure rate hay slow-call rate đã vượt ngưỡng?
4. Exceptions/statuses nào được record?
5. Timeout ở Gateway/HTTP client có ngắn hơn latency bình thường?
6. Retry có làm một logical request tạo nhiều samples/failures?
7. Fallback có lỗi riêng và bị hiểu nhầm là lỗi upstream?
8. Sau OPEN, HALF_OPEN probes có thành công hay lập tức fail?

### 11.1. Các nguyên nhân phổ biến

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| Breaker OPEN sau vài requests đầu | `minimumNumberOfCalls` thấp hoặc cấu hình window nhỏ |
| Backend trả 200 nhưng breaker vẫn tăng failures | Exception ở filter trước/sau upstream, response status mapping hoặc exception record policy |
| Backend phục hồi nhưng breaker không đóng | `waitDurationInOpenState` dài, probe calls không thành công, hoặc traffic chưa tới HALF_OPEN |
| Breaker liên tục CLOSED→OPEN→HALF_OPEN | Backend chập chờn, probe quá nhiều, threshold sát ranh giới |
| Breaker OPEN chỉ trên route này | Route dùng breaker name/config khác, upstream target/timeout khác |
| Nhiều route cùng OPEN khi một service lỗi | Cùng chia sẻ breaker name/instance hoặc cùng dependency |
| OPEN sau đợt retry | Mỗi attempt được breaker quan sát và record; filter order ảnh hưởng số samples |
| Breaker mở vì 404/401/403 | Status/exception policy đang coi response nghiệp vụ/client là failure |
| Breaker không mở dù backend quá chậm | Slow-call threshold quá lớn hoặc không đo đúng duration |
| Circuit breaker mở khi không có traffic lớn | Cửa sổ nhỏ, lỗi nền/health probes, hoặc metric aggregation sai |

### 11.2. Không giảm threshold chỉ để dashboard xanh

Nếu breaker mở vì `minimumNumberOfCalls=2`, tăng lên 20 có thể làm giảm false positive nhưng cũng **làm chậm phát hiện outage**. Nếu breaker mở vì timeout 200 ms trong khi SLO 1 giây, tăng timeout có thể làm request treo lâu và giữ connection/thread. Chỉnh mỗi lần một tham số, dùng traffic replay/stub test và so cả false-open lẫn detection time.

## 12. Thứ tự Retry và CircuitBreaker thay đổi điều gì?

Khi một route gắn cả hai filter, điều quan trọng là **mỗi retry attempt có được breaker quan sát như một call riêng hay không**.

Hai cách ghép khái niệm:

~~~text
Mô hình A — Retry bao quanh CircuitBreaker:
Logical request
  → Retry
      → CircuitBreaker → upstream (attempt 1)
      → CircuitBreaker → upstream (attempt 2)
      → CircuitBreaker → upstream (attempt 3)

Mô hình B — CircuitBreaker bao quanh Retry:
Logical request
  → CircuitBreaker
      → Retry
          → upstream (attempt 1)
          → upstream (attempt 2)
          → upstream (attempt 3)
~~~

Hệ quả có thể khác:

| Khía cạnh | Retry ngoài breaker | Breaker ngoài retry |
| --- | --- | --- |
| Samples trong breaker | Có thể ghi từng attempt | Có thể ghi kết quả cuối của logical call |
| Breaker mở giữa retry | Attempt kế tiếp có thể bị từ chối sớm | Breaker có thể chỉ đánh giá sau khi retry hoàn tất |
| Failure rate | Có thể tăng nhanh hơn vì nhiều attempts | Ít samples hơn theo logical request |
| Latency | Retry tiếp tục cho đến khi budget hết hoặc breaker chặn | Retry nằm trong một lần breaker call, latency dài hơn |
| Ý nghĩa vận hành | Breaker phản ánh upstream attempts | Breaker phản ánh trải nghiệm logical operation |

Đây là **mô hình khái niệm**. Tài liệu Gateway nêu Retry filter chạy lại các filters nằm sau nó; do đó nếu Retry đứng trước CircuitBreaker, mỗi attempt có thể đi qua breaker riêng. Nếu breaker đứng trước Retry, breaker có thể quan sát kết quả cuối của chuỗi retry. Không suy ra thứ tự thực chỉ từ thứ tự dòng YAML: Spring Cloud Gateway kết hợp GlobalFilters và route GatewayFilters, rồi sắp xếp theo `Ordered`; mỗi filter factory có thể tạo filter với order riêng. **Phải kiểm tra runtime chain của version đang chạy**, hoặc viết integration test có counter để thấy breaker ghi nhận bao nhiêu calls.

### 12.1. Cách điều tra filter order

1. Xem route definition và effective filters qua Actuator được bảo vệ.
2. Kiểm tra implementation/docs của release Gateway đang dùng; không copy order number từ blog phiên bản khác.
3. Bật debug/trace logging trong môi trường test, tránh ghi token/body ở production.
4. Dùng stub backend có counter và trả chuỗi status có kiểm soát (503, 503, 200).
5. So số backend attempts, breaker event counts và số response client nhận.
6. Kiểm tra fallback có được gọi một lần hay nhiều lần.

### 12.2. Không để một breaker name dùng chung ngoài ý muốn

Nếu nhiều routes cùng dùng `name: orders`, tùy cách tạo/caching circuit breaker trong integration, chúng có thể dùng chung một breaker instance/config. Khi một route admin/batch có latency dài làm breaker OPEN, route GET orders khác có thể bị từ chối theo cùng state.

Thiết kế:

- Dùng breaker name thể hiện **dependency + latency class/use case** (ví dụ `orders-read`, `orders-command`).
- Không tạo breaker riêng cho từng user/request.
- Chỉ chia sẻ khi routes thực sự cùng upstream, SLO và failure semantics.
- Kiểm tra `CircuitBreakerRegistry`/metrics để xác nhận số instances thực tế.

Tên khác nhau không tự tạo isolation mạng; chỉ tạo breaker policy/state riêng trong process.

## 13. LoadBalancer retry và service discovery

Route `uri: lb://orders-service` dùng Spring Cloud LoadBalancer để chọn service instance. Nếu có retry ở cả Gateway Retry filter và LoadBalancer:

- Một Gateway attempt có thể được chuyển đến instance A.
- Lỗi connection có thể khiến LoadBalancer chọn instance B.
- Gateway Retry có thể gửi lại logical request và tiếp tục qua một lần chọn instance khác.
- Nếu instance A đã commit nhưng response bị mất, instance B có thể thực hiện side effect lần nữa.

**Retry instance không đồng nghĩa operation idempotent.** Hai replicas cùng dùng database vẫn có thể tạo duplicate row nếu backend không có unique key/idempotency transaction.

### 13.1. Kiểm tra LoadBalancer retry riêng

Đối chiếu:

- Spring Cloud LoadBalancer version và retry configuration đang được áp dụng.
- Retry có chỉ xảy ra với `onNext`/`onError` hay status response cụ thể?
- Có retry on same instance hay next instance?
- Có exclude `POST`/non-idempotent methods theo policy?
- Gateway Retry có đang bao thêm attempts bên ngoài?
- Có health-check/load-balancer policy làm instance bị loại nhưng vẫn nhận traffic ở replica khác?

Không giả định property `spring.cloud.loadbalancer.retry.*` giống nhau qua mọi release train. Xác minh effective config bằng Actuator/config metadata và test trên đúng BOM.

### 13.2. Đừng để nhiều replicas cùng retry một dependency đang chết

Nếu 50 Gateway replicas cùng retry 3 lần ngay lập tức, backend vừa phục hồi có thể nhận một burst lớn. Dùng:

- Backoff tăng dần và jitter ở tầng sở hữu retry.
- Circuit breaker để fail-fast khi dependency có dấu hiệu outage.
- Bulkhead/concurrency limits để giới hạn in-flight requests.
- Rate limiting/admission control cho traffic vượt khả năng.
- Staggered rollout/probe budget khi service vừa trở lại.

Retry làm tăng tải đúng lúc dependency đang yếu; cần **retry budget** và **load shedding**, không chỉ tăng số attempts.

## 14. Timeout và deadline: không đặt các tầng mâu thuẫn

Một request có nhiều timeout:

~~~text
Client deadline:              3.0 s
Gateway route/client timeout: 2.5 s
Retry attempt + backoff:      2.0 s tổng
Backend processing timeout:   1.5 s
DB statement timeout:         1.0 s
~~~

Đây là timeline **minh họa**, các deadline thực phải có khoảng đệm cho network/serialization và cancellation. Nguyên tắc:

- Deadline của caller phải lớn hơn tổng budget nội bộ mà caller chờ, nếu muốn nhận response.
- Mỗi downstream call nhận **remaining deadline**, không bắt đầu lại một timeout đầy đủ cho từng retry.
- DB statement timeout phải phù hợp với transaction deadline.
- Backoff phải nằm trong tổng deadline, không cộng thêm vô hạn.
- Khi client hủy request, downstream calls nên được cancel nếu semantics an toàn; cancellation vẫn không rollback transaction đã commit.

### 14.1. Retry budget ví dụ

Giả sử tổng deadline 2 giây:

| Thành phần | Budget |
| --- | ---: |
| Attempt 1 | tối đa 500 ms |
| Backoff | 100 ms |
| Attempt 2 | tối đa 500 ms |
| Response/serialization margin | 300 ms |
| Reserve | 600 ms |

Nếu attempt 1 đã tiêu 1.2 giây, không còn đủ budget cho attempt 2. Một retry bắt đầu khi caller đã hết deadline chỉ làm tăng tải và tạo response vô ích.

### 14.2. Không nhầm HTTP client timeout với CircuitBreaker slow threshold

Ví dụ HTTP client timeout 1 giây, còn `slowCallDurationThreshold=2s`: request bị timeout ở 1 giây và được record là exception failure, nên slow-call threshold 2 giây có thể **không bao giờ được kích hoạt** cho call này. Nếu muốn slow-call rate phản ánh SLO, threshold phải được thiết kế tương ứng với client timeout và latency objective.

## 15. Quan sát Retry và CircuitBreaker

### 15.1. Metrics Resilience4j

Khi có Micrometer/Actuator integration phù hợp, các metric Resilience4j thường bao gồm:

| Metric | Điều cần xem |
| --- | --- |
| `resilience4j.circuitbreaker.state` | State CLOSED/OPEN/HALF_OPEN theo instance |
| `resilience4j.circuitbreaker.calls` | Số calls theo kind success/failed/not_permitted |
| `resilience4j.circuitbreaker.failure.rate` | Failure rate hiện tại |
| `resilience4j.circuitbreaker.slow.call.rate` | Tỷ lệ slow calls |
| `resilience4j.circuitbreaker.not.permitted.calls` | Số calls bị breaker từ chối |

Metric names/tags có thể khác theo registry/version. Xác nhận tại `/actuator/metrics` hoặc Prometheus scrape của đúng ứng dụng; không assume mọi metric đã được bật chỉ vì dependency có mặt.

### 15.2. Gateway route metrics và downstream metrics

Kết hợp:

- Gateway request metrics theo route ID, method, status và outcome.
- Resilience4j state/call metrics theo breaker name.
- HTTP client connection/response timeout metrics.
- Backend business metrics: orders created, payment captures, inventory decrements.
- Idempotency store: duplicate key hits, hash conflicts, in-progress waits.
- Distributed tracing: logical trace ID, attempt span, downstream service/instance.

**Chỉ Gateway request count không đủ**: một request Gateway có thể tạo nhiều downstream attempts. Để chẩn đoán duplicate order, cần so sánh **client logical operations, Gateway attempts, backend handler executions và committed business records**.

### 15.3. Log an toàn và có thể liên kết

Một log structured hữu ích:

~~~json
{
  "traceId": "trace-test-42",
  "routeId": "orders-read",
  "operation": "GET /api/orders/{id}",
  "attempt": 2,
  "upstream": "orders-service",
  "upstreamInstance": "orders-2",
  "status": 503,
  "durationMs": 420,
  "breakerState": "CLOSED"
}
~~~

`attempt` là trường instrumentation do hệ thống triển khai; Gateway không tự cung cấp một attempt header chuẩn cho mọi retry filter. Không log raw Authorization, cookie, body payment, idempotency key đầy đủ hoặc PII. Nếu cần correlation cho idempotency key, dùng hash/partial fingerprint theo chính sách.

### 15.4. Actuator phải ở management plane được bảo vệ

Ví dụ expose metrics/health:

~~~yaml
management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

`/actuator/circuitbreakers` hoặc endpoint của Spring Cloud Gateway **không mặc định được expose trong mọi release**. Chỉ expose endpoint cần thiết, bảo vệ bằng authentication/network policy và tránh public write/refresh operations. Có thể dùng JMX/metrics registry nội bộ thay vì public Actuator.

### 15.5. Phân biệt failure ở Gateway và failure nghiệp vụ

Dashboard nên phân loại:

- **Upstream transport failure:** connection refused/reset, DNS, TLS, timeout.
- **Upstream HTTP failure:** status được CircuitBreaker config record.
- **Business rejection:** validation/conflict/quota/authz — thường không nên mở dependency breaker.
- **Breaker rejection:** `CallNotPermittedException`, upstream không được gọi.
- **Fallback failure:** lỗi trong fallback handler/cache/serialization.

Nếu gộp tất cả thành “5xx”, bạn có thể tăng breaker threshold để che lỗi fallback hoặc mở breaker vì client gửi sai dữ liệu.

## 16. Runbook: điều tra thao tác trùng

Khi khách hàng báo tạo hai order/charge hai lần, đừng bắt đầu bằng cách tắt Retry ngay lập tức. Trước hết bảo toàn dữ liệu để xác định **cùng một logical operation đã được gửi bao nhiêu lần và side effect nào đã commit**.

### 16.1. Truy vấn theo operation/idempotency key

Một báo cáo nội bộ nên có:

| Dữ liệu | Câu hỏi |
| --- | --- |
| Principal/tenant đã xác minh | Hai record có cùng người dùng/tenant không? |
| Operation name | Cùng là create-order hay hai thao tác khác nhau? |
| Idempotency key/fingerprint | Có cùng một key/ý định không? |
| Gateway trace IDs | Một hay nhiều client requests? |
| Gateway retry attempts | Mỗi logical request đã forward bao nhiêu lần? |
| Backend handler executions | Backend thực sự chạy bao nhiêu lần? |
| DB committed rows | Có bao nhiêu orders/payments/inventory changes? |
| Provider transaction IDs | Payment provider có capture nhiều lần không? |

Không chia sẻ raw token/card data/customer PII trong ticket. Dùng identifiers được kiểm soát, masked values và trace IDs.

### 16.2. Đọc timeline theo thứ tự

1. Client gửi request lúc nào? Có client retry sau timeout không?
2. Gateway nhận bao nhiêu logical requests? Có cùng correlation ID hay không?
3. Gateway Retry tạo bao nhiêu attempts? Status/exception nào kích hoạt?
4. LoadBalancer chọn instance nào ở từng attempt?
5. Backend đã commit trước timeout hay chưa?
6. DB/provider có idempotency/deduplication không?
7. Client có tạo key mới khi retry thay vì giữ key cũ không?

Nếu Gateway nhận **hai logical requests** với hai idempotency keys khác nhau, Gateway Retry không phải nguyên nhân duy nhất; client có thể đã submit lại như hai operations mới. Nếu một logical request tạo ba backend attempts nhưng chỉ một business record, idempotency đang hoạt động; tiếp tục tìm vì sao retries vượt budget.

### 16.3. Khắc phục tức thời và dài hạn

**Tức thời:**

- Tạm ngừng retry trên route ghi không có idempotency, theo change control.
- Giữ nguyên trace/DB/provider evidence; không xóa idempotency records để “thử lại”.
- Reconcile giao dịch với payment provider trước khi hoàn tiền hoặc xóa record.
- Chặn retry storm và giảm concurrency nếu dependency đang bị quá tải.
- Thông báo rõ operation đang `pending/unknown` nếu không biết backend đã commit hay chưa.

**Dài hạn:**

- Thêm idempotency key và unique constraint/transaction ở nơi tạo side effect.
- Chọn một tầng retry sở hữu, thêm deadline/backoff/jitter và attempts budget.
- Tách status lỗi transient với business rejection.
- Instrument attempts, dedupe hits, backend commits và breaker states.
- Thêm regression tests mô phỏng response bị mất **sau commit**.

### 16.4. Tránh “sửa dữ liệu trùng” bằng xóa row mù

Hai order có thể cùng sản phẩm nhưng là hai ý định mua khác nhau; hai payment captures có thể cần refund/reconciliation. Đừng xóa row theo timestamp hoặc customer ID mà chưa kiểm tra operation key, ledger, outbox, payment provider và downstream events. Dữ liệu giao dịch cần **reconciliation có audit**.

## 17. Runbook: breaker OPEN ngoài dự kiến

### 17.1. Checklist chẩn đoán trong vài phút đầu

1. Xác định **instance name** của breaker và routes dùng instance đó.
2. Đọc state hiện tại, failure rate, slow-call rate, not-permitted count.
3. Kiểm tra minimum calls/window size và thời điểm bắt đầu OPEN.
4. Xem exception cause chain/status code được record.
5. So backend latency với Gateway/client timeout.
6. Kiểm tra số retry attempts trước khi breaker OPEN.
7. Kiểm tra fallback errors và fallback downstream calls.
8. Kiểm tra backend health/connection pool/DB saturation.
9. Quan sát HALF_OPEN probe results và `waitDurationInOpenState`.
10. Chỉ đổi một cấu hình mỗi lần; canary và ghi revision.

### 17.2. Các câu hỏi giúp phân biệt nguyên nhân

| Quan sát | Diễn giải có thể |
| --- | --- |
| Failure rate tăng, backend 5xx tăng | Dependency thật sự lỗi hoặc downstream dependency của nó lỗi |
| Failure rate tăng, backend status vẫn 200 | Exception có thể xảy ra ở proxy/decoder/filter, hoặc status/metrics không cùng route |
| Slow-call rate tăng, failure rate thấp | Backend quá chậm; xem SLO, timeout, connection pool, DB |
| Not-permitted tăng sau OPEN | Caller vẫn gửi traffic trong thời gian breaker mở; không phải thêm backend failures |
| HALF_OPEN probe thất bại ngay | Backend chưa sẵn sàng, probe quá lớn hoặc lỗi network/config |
| Chỉ một Gateway replica báo OPEN | State là local per process/instance hoặc traffic phân bố khác; kiểm tra breaker registry/replica metrics |
| Mọi replica OPEN cùng lúc | Shared config, traffic burst, dependency outage hoặc alert aggregation |
| Breaker OPEN sau deploy route mới | Tên breaker dùng chung, timeout mới, statusCodes rộng, filter order thay đổi |

**Lưu ý về state phân tán:** Resilience4j CircuitBreaker thường quản lý state trong process; không mặc định là một breaker state được đồng bộ giữa mọi Gateway replicas. Dashboard cần gắn instance/Pod/route để tránh nhìn một replica rồi kết luận toàn cluster.

### 17.3. Đừng ép breaker CLOSED để khôi phục traffic

Nếu backend vẫn lỗi, ép CLOSED hoặc reset liên tục có thể đẩy thêm tải vào dependency đang suy kiệt. Chỉ reset state sau khi:

- Root cause đã được xử lý hoặc dependency xác nhận phục hồi.
- Concurrency/traffic có thể kiểm soát.
- Probe an toàn đã thành công.
- Có rollback nếu failure rate/latency tăng lại.

Breaker là cơ chế bảo vệ tài nguyên, không phải cảnh báo cần “xóa cho xanh”.

## 18. Lab: quan sát retry và circuit breaker với backend stub

Mục tiêu lab:

1. Tạo route GET chỉ retry khi upstream trả 503.
2. Dùng backend stub trả 503 một lần rồi 200.
3. Xác minh Gateway tạo đúng số downstream attempts.
4. Thêm circuit breaker với threshold nhỏ trong profile test và quan sát OPEN/fallback.
5. Xác nhận một route POST không có Retry filter không bị gửi lại.

### 18.1. Backend stub có thể kiểm soát response

Dùng MockWebServer hoặc WireMock trong test; không cần public backend. Ví dụ ý tưởng dispatcher:

~~~java
AtomicInteger calls = new AtomicInteger();

server.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest request) {
        int attempt = calls.incrementAndGet();
        if (attempt == 1) {
            return new MockResponse().setResponseCode(503);
        }
        return new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"status\":\"ok\"}");
    }
});
~~~

Đoạn này là **test fixture**, chỉ áp dụng khi test class có khởi tạo `MockWebServer` và imports tương ứng. Reset counter/queue giữa test cases; không chia sẻ state không đồng bộ giữa tests chạy song song.

### 18.2. Route Retry test

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: retry-read-test
              uri: http://127.0.0.1:${test.backend.port}
              predicates:
                - Path=/test/read
                - Method=GET
              filters:
                - name: Retry
                  args:
                    retries: 1
                    methods:
                      - GET
                    statuses:
                      - SERVICE_UNAVAILABLE
~~~

Kỳ vọng với stub trả 503 rồi 200:

| Điều cần assert | Kết quả |
| --- | --- |
| Client response | 200 |
| Backend request count | 2 |
| Request method | GET ở cả hai attempts |
| Body | Không có body cần replay |
| Trace | Cùng logical request/correlation, attempt index khác nhau nếu đã instrument |

Không assert rằng mọi deployment đều tự thêm attempt header. Gateway Retry filter không cam kết một header attempt chuẩn.

### 18.3. Kiểm tra POST không bị retry

Thêm route riêng:

~~~yaml
- id: create-order-test
  uri: http://127.0.0.1:${test.backend.port}
  predicates:
    - Path=/test/orders
    - Method=POST
~~~

Gửi POST khi stub trả 503. Nếu route không gắn Retry, **backend count phải là 1** (một downstream attempt từ Gateway). Nếu test có thêm client retry, phải tắt client retry hoặc đếm riêng; không suy ra Gateway đã retry từ hai requests tổng.

### 18.4. Kiểm thử idempotency khi response mất sau commit

Một test nghiệp vụ quan trọng:

~~~text
Given:
  principal = user-123
  idempotency key = op-001
  payload hash = H1

When:
  request thứ nhất commit order O-42
  response bị drop trước khi client nhận
  client gửi lại cùng key op-001 và cùng payload H1

Then:
  backend trả lại response/result của O-42
  orders table chỉ có một order O-42
  payment provider chỉ có một capture theo provider key

And:
  cùng key op-001 nhưng payload hash H2
  → 409 Conflict, không tạo order thứ hai
~~~

Đây là test ở **backend/domain service**, không thể chứng minh chỉ bằng Gateway route test. Có thể dùng fault injection/proxy test để drop response sau commit; tránh dùng môi trường payment thật.

### 18.5. Kiểm thử CircuitBreaker state transitions

Với Resilience4j unit tests, tạo breaker config trong test:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class CircuitBreakerStateTest {

    @Test
    void opensAfterHalfOfTheMinimumWindowFails() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(1))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        CircuitBreaker breaker =
                CircuitBreaker.of("orders-test", config);

        breaker.onSuccess(10, TimeUnit.MILLISECONDS);
        breaker.onSuccess(10, TimeUnit.MILLISECONDS);
        breaker.onError(20, TimeUnit.MILLISECONDS,
                new IOException("simulated upstream failure"));
        breaker.onError(20, TimeUnit.MILLISECONDS,
                new IOException("simulated upstream failure"));

        if (breaker.getState() != CircuitBreaker.State.OPEN) {
            throw new AssertionError(
                    "Expected OPEN after 2/4 failures");
        }
    }
}
~~~

Sau đó:

1. Snippet trên ghi 2 successes + 2 failures trong CLOSED.
2. Xác minh state OPEN khi threshold 50% được kích hoạt.
3. Xác minh call mới bị từ chối và tăng not-permitted count.
4. Chờ hoặc dùng controllable clock theo API/version test harness để vào HALF_OPEN.
5. Gửi số probe được phép và xác minh state đóng/mở theo kết quả.

Đây là **unit test cho Resilience4j**, không kiểm tra Gateway filter order hoặc HTTP fallback. Integration test cần gắn CircuitBreaker GatewayFilter vào route và gọi qua HTTP server thật.

### 18.6. Không dùng sleep dài để test state machine

Nếu phải kiểm tra `waitDurationInOpenState`, ưu tiên clock/time abstraction được hỗ trợ bởi phiên bản Resilience4j test API hoặc đặt duration nhỏ có giới hạn và timeout test. Không dùng sleep nhiều chục giây trong CI, không để tests chia sẻ cùng registry/state.

## 19. Bảng troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần lấy | Hướng xử lý |
| --- | --- | --- | --- |
| Một lần nhấn tạo hai orders | Gateway/client/LoadBalancer retry sau commit | Idempotency key, Gateway attempts, DB records | Deduplicate ở backend, sửa retry budget |
| Payment bị capture hai lần | Retry payment call không dùng provider key | Provider transaction IDs, request timeline | Provider idempotency/reconciliation |
| POST bị gửi lại ba lần | Retry filter áp dụng route ghi hoặc nhiều retry layers | Effective route filters, recorded requests | Tắt retry mù, per-route policy |
| GET bị retry nhưng không thấy phục hồi | Retry không match exception/status thực tế | Cause chain, status, Retry filter config | Cấu hình đúng exception/status và test |
| Retry tạo 503 liên tục | Backoff quá ngắn, dependency vẫn down | Attempts/sec, latency, breaker state | Giảm retry budget, jitter, breaker/load shed |
| Retry không dừng dù client đã cancel | Cancellation không truyền qua tầng sau hoặc side effect đã commit | Reactor traces, downstream logs | Tôn trọng cancellation/deadline; idempotency |
| Gateway báo 504 nhưng order đã có | Backend commit, response bị mất | DB commit time và gateway timeout | Query operation theo idempotency key |
| Breaker OPEN sau vài failures | Minimum calls/window quá thấp | Breaker config/events | Điều chỉnh theo sample size và SLO |
| Breaker OPEN vì 401/403 | Security/business errors bị record như dependency failures | Status/exception mapping | Ignore/không record loại lỗi caller |
| Breaker OPEN vì 404 | Route/status policy quá rộng hoặc backend 404 bình thường | Route config, downstream response | Chỉ record status thật sự là dependency failure |
| Breaker OPEN dù backend 200 | Lỗi filter/decoder, exception wrapping, metric sai | Cause chain, trace spans | Xác định failure source, sửa record policy |
| Breaker không OPEN khi backend treo | Slow threshold quá lớn hoặc call không được đo | Latency distribution, slow rate | Căn threshold với SLO/timeout |
| Breaker không đóng lại | HALF_OPEN probes fail hoặc không có traffic | State events, wait duration, probe results | Kiểm tra upstream, probe budget |
| Breaker mở/đóng liên tục | Threshold sát ranh giới, backend chập chờn | State transition timestamps, rates | Điều chỉnh window/hysteresis, xử lý backend |
| Chỉ một route bị ảnh hưởng | Route breaker name/config khác | Route ID, breaker registry | Sửa name/config hoặc timeout riêng |
| Nhiều routes cùng OPEN | Dùng chung breaker name/instance hoặc chung dependency | Instance name, registry | Chia sẻ có chủ đích hoặc tách policy |
| Backend vừa phục hồi lại quá tải | HALF_OPEN probe quá nhiều, nhiều Gateway replicas | Probe count, in-flight requests | Giảm probes, jitter/stagger, bulkhead |
| Fallback trả 200 với order chưa rõ | Fallback che trạng thái pending/unknown | Fallback response/body, business record | Trả status rõ, operation ID/reconciliation |
| Retry request body làm memory tăng | Cache body lớn/replay nhiều attempts | Heap/direct memory, GC, body sizes | Bỏ retry upload, giới hạn body/concurrency |
| CircuitBreaker không được kích hoạt | Thiếu starter hoặc route filter không bind | Dependency tree, runtime filters | Thêm starter tương thích, kiểm tra route |
| Metrics không có breaker state | Registry/Actuator chưa expose hoặc tag khác | endpoint metrics đã bảo vệ, scrape target | Bật đúng registry/endpoint bảo vệ |
| Metric not-permitted tăng mạnh | Traffic tiếp tục tới breaker OPEN | `CallNotPermittedException` logs | Không coi đó là backend failures mới |
| Test báo xanh nhưng backend count sai | Test chỉ assert HTTP status | MockWebServer recorded requests | Assert attempt count và business commits |

### 19.1. Phân biệt một logical operation với nhiều HTTP attempts

Một trace ID có thể được giữ qua retries, nhưng không nên giả định mọi client/proxy tự duy trì trace context. Cần phân biệt:

- **Logical operation ID:** định danh một ý định nghiệp vụ (ví dụ idempotency key đã hash).
- **Trace ID:** liên kết spans trong một distributed trace.
- **HTTP attempt:** một lần gửi tới upstream.
- **Business execution/commit ID:** lần nghiệp vụ thực sự được ghi nhận.

Một logical operation có thể có nhiều HTTP attempts nhưng chỉ một business commit. Một client có thể gửi hai logical operations khác nhau dù payload giống hệt nhau. Các identifiers có nhiệm vụ khác nhau và không nên thay thế cho nhau.

## 20. Checklist trước khi bật Retry/CircuitBreaker

### 20.1. Retry

- [ ] Đã xác định tầng sở hữu retry; không có retry chồng không kiểm soát ở client/Gateway/LoadBalancer/WebClient.
- [ ] Đã phân loại operation theo business idempotency, không chỉ HTTP method.
- [ ] Route ghi/payment/refund/upload không có retry mù.
- [ ] Có idempotency key ổn định qua mọi attempts của cùng logical operation.
- [ ] Backend lưu deduplication record bền vững, unique constraint và request hash.
- [ ] Cùng key khác payload được xử lý bằng conflict, không âm thầm replay.
- [ ] Side effects ngoài DB có provider key/outbox/inbox/saga phù hợp.
- [ ] Retry chỉ áp dụng lỗi transient được chọn, không retry auth/validation/business rejection.
- [ ] Có attempts cap, backoff/jitter và tổng deadline.
- [ ] Request body lớn/streaming không bị replay ngoài kiểm soát.
- [ ] Có metric/log attempts per logical operation và backend commits.

### 20.2. Circuit breaker

- [ ] Có dependency name/route mapping rõ; breaker instance không bị share ngoài ý muốn.
- [ ] `minimumNumberOfCalls`, sliding window và thresholds phù hợp traffic/SLO.
- [ ] Slow-call threshold được so với HTTP client timeout và latency objective.
- [ ] Exceptions/statuses được record/ignore đúng loại.
- [ ] `CallNotPermittedException` được phân biệt với backend failure.
- [ ] HALF_OPEN probe count an toàn cho backend vừa phục hồi.
- [ ] Fallback không gọi lại chính upstream đang OPEN.
- [ ] Fallback không trả 200/202 giả cho giao dịch chưa xác định.
- [ ] Breaker state/metrics được gắn với Pod/instance/route.
- [ ] Có cách canary/rollback config thay vì reset breaker liên tục.

### 20.3. Kiểm thử và vận hành

- [ ] Test timeout xảy ra **sau commit**, client gửi lại cùng idempotency key.
- [ ] Test hai requests đồng thời cùng key để chứng minh atomic deduplication.
- [ ] Test cùng key nhưng payload khác.
- [ ] Test Retry với 503 rồi 200 và assert backend attempt count.
- [ ] Test POST route không retry.
- [ ] Test filter order Retry/CircuitBreaker với runtime counter.
- [ ] Test state CLOSED→OPEN→HALF_OPEN→CLOSED và trường hợp probe fail.
- [ ] Test fallback status/body và không có fake success.
- [ ] Test nhiều Gateway replicas/LoadBalancer instances nếu deployment scale ngang.
- [ ] Có dashboard failure rate, slow-call rate, not-permitted, retries, backend commits.
- [ ] Không log token/cookie/payment data/idempotency key raw.
- [ ] Actuator/metrics chỉ ở management plane được bảo vệ.

## 21. Bài tập thực hành

### Bài 1 — Tìm tầng gây duplicate

Một POST tạo order có timeline:

~~~text
Client sends 1 request
Gateway logs 2 attempts
Orders service logs 2 handler executions
Database contains 1 order
~~~

Giải thích vì sao database chỉ có một order dù backend chạy hai lần. Chứng minh cơ chế idempotency đang hoạt động, sau đó tìm nguyên nhân Gateway retry POST. Đề xuất cấu hình để chỉ GET được retry.

### Bài 2 — Timeout sau commit

Dùng stub/backend test: commit order rồi chủ động drop response. Client retry với cùng key. Đảm bảo:

- Chỉ một order được tạo.
- Response thứ hai replay cùng resource ID.
- Cùng key nhưng payload khác trả 409.
- Không có payment capture thứ hai.

### Bài 3 — Tìm nguyên nhân CircuitBreaker OPEN

Đặt `minimumNumberOfCalls=4`, window 4, failure threshold 50%. Gửi 2 success + 2 failures. Quan sát state, not-permitted calls và HALF_OPEN. Thay threshold rồi giải thích detection speed/false-open trade-off.

### Bài 4 — Kiểm tra filter order

Tạo route dùng Retry và CircuitBreaker. Stub trả 503 hai lần rồi 200. So sánh:

- Backend attempts.
- Breaker call/failure events.
- Client response.
- Fallback count.

Không kết luận filter order chỉ từ thứ tự dòng YAML; ghi nhận runtime chain của version thực.

### Bài 5 — Giảm retry storm

Mô phỏng 20 Gateway instances cùng gọi một stub trả 503. So sánh retry ngay lập tức với backoff/jitter + circuit breaker + concurrency limit. Ghi requests/sec, p99 và thời gian dependency phục hồi.

Không tạo tải trên production hoặc một dịch vụ không được phép thử.

### Bài 6 — Fallback cho dữ liệu optional

Mobile home cần catalog, recommendations và profile. Xác định:

- Recommendations có thể fallback stale/empty trong điều kiện nào?
- Profile/authorization có được fallback guest/admin không?
- Giá/tồn kho có thể stale không?
- Circuit breaker nào tách theo dependency?
- Response status nào thể hiện degraded nhưng không gây hiểu nhầm?

## 22. Câu hỏi tự kiểm tra

**1. Vì sao timeout không có nghĩa backend chưa thực hiện side effect?**

Vì backend có thể đã commit transaction nhưng response bị mất trước khi về Gateway/client. Gateway chỉ biết nó không nhận response đúng hạn.

**2. Retry hai lần nghĩa là tổng cộng mấy attempts?**

Thông thường `retries` là số lần thử lại thêm ngoài attempt ban đầu, nhưng cần xác nhận contract của filter/version và tính cả các tầng retry khác.

**3. POST có thể retry an toàn không?**

Có thể nếu business operation được thiết kế idempotent, key ổn định, deduplication bền vững và side effects ngoài DB cũng có cơ chế chống trùng. Không thể suy ra chỉ từ method.

**4. Vì sao cùng một Idempotency-Key nhưng payload khác phải bị từ chối?**

Vì một key đại diện một ý định. Cho phép payload khác dùng lại key sẽ khiến kết quả replay mơ hồ và có thể tạo lỗi dữ liệu/quyền.

**5. Circuit breaker OPEN có tự retry request không?**

Không. Nó từ chối call sớm; retry là một cơ chế khác và có thể bị chặn bởi breaker đang OPEN.

**6. Failure rate và slow-call rate khác nhau thế nào?**

Failure rate đếm calls được xem là thất bại; slow-call rate đếm calls vượt ngưỡng duration dù có thể vẫn trả 200.

**7. Vì sao breaker mở sau một số ít failures?**

Có thể do `minimumNumberOfCalls` thấp, window nhỏ, failure threshold thấp hoặc nhiều retries được tính như nhiều samples.

**8. `CallNotPermittedException` có phải backend vừa trả lỗi không?**

Không. Nó cho biết breaker đang OPEN nên call không được gửi tới backend.

**9. Vì sao filter order giữa Retry và CircuitBreaker quan trọng?**

Vì nó quyết định breaker có thể quan sát từng attempt hay chỉ kết quả của một logical request sau retry; điều này ảnh hưởng failure rate và thời điểm OPEN.

**10. Vì sao fallback trả 200 có thể nguy hiểm?**

Client có thể nghĩ order/payment đã hoàn tất dù backend commit chưa rõ. Fallback phải biểu diễn đúng trạng thái degraded/pending/unknown theo contract.

**11. Có nên dùng một breaker name cho mọi route tới orders service không?**

Chỉ khi các routes có cùng dependency, SLO và failure semantics. Read endpoint và command/batch có thể cần policies khác nhau; tránh chia sẻ state ngoài ý muốn.

**12. Làm sao chứng minh idempotency thực sự hoạt động?**

Gửi lại cùng key sau khi response bị mất sau commit, rồi kiểm tra chỉ một business record/provider side effect tồn tại và lần sau trả cùng kết quả.

## 23. Tài liệu chính thức và tham khảo

1. [Spring Cloud Gateway Server WebFlux — Retry GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html): retries, statuses, methods, exceptions và backoff.
2. [Spring Cloud Gateway Server WebFlux — CircuitBreaker GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/circuitbreaker-filter-factory.html): breaker name, fallback URI và status codes.
3. [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): Reactor/Resilience4j integration và configuration.
4. [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): state machine, sliding windows, failure/slow-call rates, events.
5. [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): retry attempts, interval functions và exception/result predicates.
6. [Spring Cloud LoadBalancer — Retry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): load-balancer behavior/configuration theo release.
7. [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive downstream calls, timeout/cancellation và composition.
8. [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html): method semantics, safe/idempotent methods và response behavior.
9. [Stripe — Idempotent Requests](https://docs.stripe.com/api/idempotent_requests): ví dụ provider idempotency contract, lưu/replay kết quả và conflict behavior.
10. [AWS Builders’ Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/): thiết kế idempotency cho APIs và retry.
11. [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics endpoint, Micrometer registry và exposure.

**Ghi nhớ:** Retry giúp phục hồi lỗi transient nhưng có thể **gửi lại một thao tác đã commit**. Với lệnh ghi, cần idempotency key ổn định, deduplication bền vững và xử lý side effects ngoài DB. Circuit breaker OPEN là tín hiệu dependency đang bị coi là không khỏe; hãy đọc failure/slow-call rates, minimum calls, exception policy, filter order và HALF_OPEN probes trước khi chỉnh ngưỡng. Chỉ khi đo được **logical requests, downstream attempts và business commits** cùng lúc, bạn mới phân biệt được retry storm, duplicate operation và breaker mở ngoài dự kiến.
