# 429, pool cạn và giới hạn cấu hình không đồng nhất

## 1. Tình huống sự cố: thấy 429 nhưng chưa chắc client gọi quá nhanh

Một REST API tên **Orders API** tiếp nhận yêu cầu đặt hàng, gọi Inventory API và dùng PostgreSQL. Hệ thống có API gateway, nhiều pod Spring Boot, Redis giữ quota phân tán và HikariCP quản lý JDBC connections.

Một buổi sáng, đối tác nhận các response:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 20

{"type":"https://api.example.test/problems/rate-limit",
 "title":"Too Many Requests","status":429}
~~~

Đội hỗ trợ kết luận ngay: “Đối tác gọi quá nhiều, bảo họ giảm request”. Nhưng dashboard cho thấy tổng request/s không tăng; p99 latency tăng từ 150 ms lên 4 giây và các pod có `hikaricp.connections.pending` tăng cao. Sau một lần chỉnh cấu hình, một số client lại nhận 503, còn những client khác vẫn nhận 429.

Các giả thuyết có thể đồng thời đúng:

- **Quota thật:** API key của đối tác đã dùng hết 100 requests/phút, gateway trả 429 đúng hợp đồng.
- **Pool database bị chiếm hết:** HikariCP có 12 connections, toàn bộ bị giữ vì transaction đang chờ HTTP downstream; request mới bị chờ và timeout. Đây không phải bằng chứng client vượt quota.
- **Pool HTTP tới Inventory bị cạn:** 30 connections per route đều leased, request xếp hàng chờ acquire. Một adapter hoặc gateway có thể đang ánh xạ sai lỗi này thành 429.
- **Giới hạn không đồng nhất:** Gateway cho 100 requests/phút theo client, service giới hạn 50/10 giây theo tenant, Redis dùng key sai, và downstream giới hạn 200 requests/phút theo **một credential chia sẻ**.
- **Nhiều replica:** Mỗi pod áp quota in-memory riêng; autoscaling hoặc sticky routing khiến quota thực tế thay đổi theo số pod và đường đi traffic.
- **Retry storm:** Client nhận 503/timeout rồi retry không có jitter; những request retry nhanh chóng vượt cả quota, sinh thêm 429 dù điểm khởi phát là sự cố dependency.

**Không chữa sự cố bằng cách tăng mọi giới hạn.** Tăng pool có thể đẩy tải vượt khả năng database; tăng rate limit có thể làm downstream quá tải; kéo dài timeout có thể giữ connection lâu hơn và tạo hàng đợi lớn hơn.

Bài này thuộc chương **Chẩn đoán sự cố** của module **INTEGRATION_API_REST**. Ta sẽ dùng HTTP status, tài nguyên REST, Java/Spring, quota, phân quyền, kết nối, tracing, thử tải và kiểm thử để trả lời ba câu hỏi: **Ai từ chối request? Vì sao từ chối? Giới hạn nào thực sự bị chạm?**

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `429 Too Many Requests` với `503 Service Unavailable`, `502/504` và lỗi transport.
2. Đọc đúng dấu hiệu HikariCP, HTTP client pool, upstream connection limits và limiter phân tán.
3. Phát hiện mismatch về **key, phạm vi, đơn vị thời gian, cấu hình, số pod và deadline** giữa gateway, ứng dụng và downstream.
4. Xây runbook có thứ tự: xác nhận trải nghiệm → xác định tầng phát lỗi → đo pool/quota → cô lập nguyên nhân → giảm tác động → kiểm chứng.
5. Thực hiện các ví dụ Java/Spring Boot, Micrometer, SQL, HTTP response và kiểm thử tích hợp/lỗi đồng thời.
6. Thiết kế quota, concurrency và timeout có giới hạn tổng, không làm tăng retry storm hoặc tác dụng phụ trùng.

## 2. Đọc HTTP status cho đúng trước khi mở dashboard

### 2.1. 429 là quyết định quota của consumer

**RFC 6585** định nghĩa `429 Too Many Requests` cho tình huống user/client gửi quá nhiều request trong một khoảng thời gian. Server quyết định cách đếm, key và giới hạn theo policy; có thể trả `Retry-After`.

~~~http
GET /api/orders?page=0 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token

HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 18
Cache-Control: no-store
X-Request-Id: req-4d92

{
  "type": "https://api.example.test/problems/client-rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Đã dùng hết số lượt gọi API được phép.",
  "code": "CLIENT_RATE_LIMITED",
  "requestId": "req-4d92"
}
~~~

Trong ví dụ, `Retry-After: 18` nghĩa là số **giây**, không phải mili giây. `Retry-After` cũng có thể chứa một HTTP-date theo RFC 9110. Header có thể vắng mặt khi server không biết thời điểm hợp lệ tiếp theo. 429 **không được lưu bởi HTTP cache** theo RFC 6585; `Cache-Control: no-store` làm rõ ý định và tránh cấu hình cache tùy biến sai.

**Điều cần xác minh:** `quota_subject` có phải consumer hợp lệ đã xác thực không, `policy_id` nào quyết định từ chối, current usage có vượt đúng ngưỡng/window không, và request đó đã bị chặn **trước** khi thực hiện tác dụng phụ chưa. 429 không có nghĩa CPU/database cạn tài nguyên.

### 2.2. 503 là service không phục vụ được request hợp lệ

Nếu Orders API không lấy được kết nối database vì pool đầy hoặc dependency làm service tạm không thể xử lý, nó có thể trả **503 Service Unavailable** theo hợp đồng, thay vì đổ lỗi cho consumer.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-79c2

{
  "type": "https://api.example.test/problems/service-busy",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Dịch vụ tạm thời không thể xử lý yêu cầu.",
  "code": "DATABASE_CONNECTION_CAPACITY",
  "requestId": "req-79c2"
}
~~~

Không tự gán `Retry-After: 5` khi chưa có ước lượng đáng tin về lúc phục hồi. Việc trả 503 **không chứng minh** mọi node hoặc mọi route đều hỏng: có thể chỉ endpoint dùng Inventory/Database bị ảnh hưởng. Trong sự cố nặng, server thậm chí không đủ tài nguyên để phát HTTP response; client có thể chỉ thấy timeout hoặc reset.

### 2.3. Mã khác liên quan

| Tín hiệu | Phân biệt nguyên nhân | Hành động ban đầu |
|---|---|---|
| **429** | Caller/quota key vượt chính sách sử dụng | Xác minh key, limit, window, `Retry-After`; throttle |
| **503** | Service tạm không thể xử lý do overload/maintenance/dependency | Xem resource saturation, load shedding, retry budget |
| **502** | Gateway/proxy nhận phản hồi upstream không hợp lệ | Kiểm giao thức, reset, proxy/upstream logs |
| **504** | Gateway/proxy không nhận phản hồi kịp thời từ upstream | Xem timeout budget, p99, queue và trace |
| **500** | Lỗi server không được phân loại cụ thể hơn | Xem stack trace có lọc bí mật, exception và deployment |
| **408** | Server không nhận đủ request của client trong thời gian cho phép | Kiểm client/network và request completion |
| **401/403** | Chưa xác thực/không có quyền | Kiểm token/scope/policy; không tăng quota để chữa |
| **Transport timeout/reset** | Không có HTTP response đáng tin ở phía caller | Xác định request đã tới đâu, side effect có thể UNKNOWN |

**Điểm dễ nhầm:** Inventory trả 429 vì Orders dùng hết hạn mức chung của provider. Không nhất thiết được **truyền nguyên 429** cho end user của Orders, vì user đó có thể chưa hề vượt một quota nào của Orders. Nếu đây là hạn mức **toàn dịch vụ** hoặc credential dùng chung, Orders có thể cần trả 503 hoặc trạng thái suy giảm đã tài liệu hóa, kèm code như `INVENTORY_PROVIDER_THROTTLED`. Nếu API chỉ làm proxy minh bạch và chính quota thuộc consumer đang gọi, 429 có thể phù hợp. Chính sách phải xác định theo **chủ thể hạn mức**, không chỉ copy status từ upstream.

### 2.4. Lỗi “đúng HTTP” vẫn có thể ảnh hưởng chất lượng

Một loạt 429 là kết quả **đúng** nếu client thực sự vượt quota được công bố. Nhưng 429 cho các request dưới quota vì cấu hình sai là sự cố chất lượng, dù vẫn là 4xx. Tương tự, 404 sau deploy sai routing và 403 do scope mapping hỏng có thể là incident. Khi đo SLO, cần phân biệt expected rejections với request hợp lệ bị thất bại, không tự loại **mọi 4xx** khỏi phân tích.

## 3. Sơ đồ đường đi của request và vị trí áp giới hạn

~~~mermaid
flowchart TD
    C[Browser / Partner / Batch client] --> E[CDN / WAF / API Gateway]
    E -->|quota key, IP, clientId| Q{Gateway quota}
    Q -->|vượt| R429[429 do gateway]
    Q -->|hợp lệ| A[Spring Orders API - nhiều pods]
    A -->|identity + tenant| R{App limiter / bulkhead}
    R -->|quota user/tenant| APP429[429 do ứng dụng]
    R -->|global workload full| APP503[503 load shedding]
    R --> S[Service / @Transactional / repositories]
    S --> H[HikariCP / JDBC]
    H --> DB[(PostgreSQL)]
    S --> P[Apache HTTP Pool / RestClient]
    P --> I[Inventory API]
    I --> UPQ{Provider quota}
    UPQ -->|shared key hết quota| U429[429 từ provider]
~~~

**Một request có thể gặp nhiều bộ giới hạn**: WAF IP throttle, gateway quota theo client, application quota theo tenant, concurrency bulkhead, Hikari maximumPoolSize, HTTP max connections per route, database `max_connections`, Inventory per-account quota. Chúng khác nhau về **đơn vị, key, đối tượng chịu trách nhiệm và semantics khi vượt**.

### 3.1. Ma trận những giới hạn cần kiểm

| Tầng | Key/đơn vị | Kiểu giới hạn | Tín hiệu khi vượt | Người sở hữu |
|---|---|---|---|---|
| WAF/edge | IP/network, request/s, policy bot | Chống abuse | 429/403 hoặc connection drop theo cấu hình | Security/edge |
| API gateway | Verified client ID/API key, req/min | Rate/quota | Thường 429 | API platform |
| Service limiter | Tenant/user/route, token/s hoặc requests/window | Quota nghiệp vụ | 429 nếu chính caller vượt | API team |
| Bulkhead app | In-flight jobs/route/service | Concurrency | 503 khi capacity chung cạn | API team |
| HikariCP | Physical JDBC connections/pod | Pool capacity | Acquire timeout/exception, thường ánh xạ 503 nếu không phục vụ được | API team/DBA |
| PostgreSQL | DB connections/cluster, locks, CPU/IO | Capacity thật của DB | Reject connect, SQL exception/slow query | DBA/platform |
| HTTP connection manager | Connections/route/pod, pending acquire | Transport capacity | Acquire timeout; không phải quota caller | API team |
| Inventory provider | Credential/account/merchant, req/min hoặc concurrency | Downstream quota | 429 ở **Inventory**, có thể khác HTTP trả cho caller | Integration/provider |

Không có một con số “rate limit của API” đủ mô tả tất cả. Ví dụ một client hợp lệ bị chặn ở app bulkhead mà gateway quota còn dư: đó không nên được gắn mã `CLIENT_RATE_LIMITED`. Chẩn đoán phải truy vết **source layer**.

### 3.2. Cẩn thận với đồng nhất IP, user, client và tenant

- **IP**: nhiều user phía sau NAT/corporate proxy có thể cùng một IP. Nếu quota theo IP thấp, người dùng hợp lệ sẽ bị ảnh hưởng vì người khác cùng mạng.
- **Client/app ID**: phải đến từ access token đã xác minh, mTLS principal hoặc API key đã được kiểm tra; không tin header `X-Client-Id` do browser tự đặt.
- **User ID**: cùng user có thể dùng nhiều app; cùng `sub` tại các issuer khác nhau không được gộp nhầm. Dùng `issuer + subject` và các chiều đã được xác minh khi cần.
- **Tenant**: một tenant có nhiều user; quota tenant và quota user phục vụ mục tiêu khác nhau. ID tenant trong URL phải khớp membership/quyền, không trở thành “quyền sử dụng” chỉ vì client gửi.
- **Provider account**: toàn bộ pod có thể dùng **một credential**; quota của provider là **tổng toàn cụm**, không phải quota từng tenant trừ khi provider cam kết như vậy.

Với reverse proxy, chỉ tin `X-Forwarded-For`/`Forwarded` từ **proxy tin cậy được cấu hình**, không nhận IP thật từ header do Internet tự cung cấp. Đây vừa là vấn đề rate limiting vừa là an toàn truy cập.

## 4. Ba mẫu triệu chứng: quota thật, pool cạn và cấu hình lệch

| Quan sát | Quota caller thực sự vượt | Hikari/HTTP pool cạn | Giới hạn không đồng nhất |
|---|---|---|---|
| HTTP nhìn từ client | 429 có policy rõ | 503/504/timeout; đôi khi 429 **do map sai** | Xen kẽ 429/503/504 tùy pod/route |
| Request/s toàn dịch vụ | Có thể bình thường | Có thể bình thường hoặc tăng | Có thể gần như không đổi |
| Lưu lượng của một key | Vượt policy | Có thể dưới quota | Có thể dưới quota được công bố, nhưng vượt policy khác |
| Hikari active/idle/pending | Thường bình thường | Active≈max, idle≈0, pending tăng | Có thể khác giữa pod |
| HTTP pool leased/pending | Thường bình thường | Leased=max, pending tăng nếu hết slot | Mỗi pod/route có cấu hình khác |
| Retry attempts | Có thể tăng nếu client sai | Tăng sau timeout/503 | Spike khi một tầng retry gây 429 tầng khác |
| Scope/tenant/IP | Một hoặc vài quota keys | Có thể nhiều callers cùng bị ảnh hưởng | Chỉ một region/version/pod/tenant tier |
| Thời gian tới phản hồi | 429 thường sớm | Timeout, p99 tăng, queue dồn | Bimodal: pod nhanh từ chối, pod khác xử lý |
| Remediation đầu tiên | Giảm tốc, sửa client/budget hoặc review quota | Giảm giữ connection, backpressure, kiểm DB/downstream | Đồng bộ manifest và config/runtime, sửa key/units |

Đây là **heuristic**, không phải phương trình suy luận duy nhất. Nếu 429 được phát ở gateway trước khi vào app, Hikari phía backend có thể đang cạn **cùng lúc** nhưng không phải nguyên nhân trực tiếp của 429 cụ thể. Cần correlation để tránh quy hai sự cố độc lập thành một chuỗi nhân quả.

## 5. Runbook điều tra: theo dấu một request trước khi thay cấu hình

### Bước 0 — Khoanh phạm vi và bảo vệ hệ thống

Xác nhận thời điểm, vùng, route, method, API version, các cohort consumer và mức độ ảnh hưởng. Nếu checkout bị lỗi hàng loạt, ưu tiên giảm tải/rollback bản phát hành đáng nghi theo runbook; không chờ hoàn tất nghiên cứu mới bảo vệ người dùng. Đặt ngưỡng dừng cho mọi thử tải chẩn đoán, không tự phát các request thanh toán/tạo đơn vào production.

Thu dữ liệu **không nhạy cảm**: `requestId`/`traceId`, route template, status, error code, release, source layer, thời gian xử lý, policy ID và thông tin quota dạng thống kê. Không dán raw JWT, API key, cookie hoặc PII vào ticket.

### Bước 1 — Xác định **ai** đã phát 429

Với một request cụ thể, đối chiếu:

1. Edge/gateway access logs: đã từ chối trước khi forward hay đã gửi vào service?
2. Spring ingress logs/traces: request có đến Orders không? Có `@ControllerAdvice`/limiter record không?
3. Outbound logs: Orders có nhận 429 từ Inventory không? Có adapter **relay** thành 429 ra ngoài không?
4. Headers/body do tầng nào tạo: `code`, `requestId`, `Via`/gateway annotations nếu hạ tầng công bố. Không kết luận chỉ từ tên server header, vì proxy có thể rewrite.
5. Telemetry: số 429 tại edge, app, outbound theo **cùng thời điểm và route**. Tránh cộng double-count từ ba tầng rồi coi đó là ba request.

**Câu hỏi quyết định:** Request đã dừng ở đâu? Nếu 429 phát ở gateway, sửa Hikari không trực tiếp làm request đó được thông qua. Nếu provider trả 429, phải tìm **provider quota key** thay vì quy lỗi cho user phía ngoài.

### Bước 2 — Kiểm quota key và cấu hình có hiệu lực

Kiểm policy ID, key đã xác thực, limit, refill/window, route cost, remaining/reset và thời điểm. So cấu hình **effective runtime** của từng pod/gateway/region, không chỉ giá trị trong Git.

- Cửa sổ là 60 giây **sliding** hay **fixed**? Có cho burst qua token bucket không?
- `100/min` theo tenant khác `100/min` theo user; hai policy chồng nhau cần có thứ tự và thông báo đúng.
- Config có bị override bởi env variables, feature flag, Helm values, config server hay emergency rule?
- Redis key có namespace gồm môi trường, version policy, account, tenant, client hay không?
- Time units có bị nhầm `ms` với `s`, `req/min` với `req/s`, số giây reset với epoch?
- Những pod vừa deploy có policy version khác; clock skew/wall time ảnh hưởng fixed windows và `Retry-After`?
- Gateway có quota theo route nhưng service tính theo nhóm routes dùng chung? Quota backend có tổng cho API key provider shared?
- Limiter store mất kết nối đã **fail-open** hay **fail-closed**? Không gán 429 cho mọi lỗi Redis nếu chưa biết caller vượt quota.

Nếu có rule cấu hình sai, rollback/thống nhất rule theo quy trình; không “nới tất cả quota” rồi mất khả năng chống noisy neighbor.

### Bước 3 — Kiểm Hikari/JDBC pool

Quan sát cùng thời điểm:

- `active`: số connections đang được mượn;
- `idle`: số connections sẵn;
- `pending`: số threads chờ mượn;
- `max`: `maximumPoolSize` thực tế;
- acquisition wait/timeout, transaction duration, query latency và DB locks;
- PostgreSQL `max_connections`, số connection đang mở, active sessions, blocking queries và CPU/IO.

**Dấu hiệu đáng nghi:** active=maximum, idle=0, pending tăng, JDBC acquisition timeout. Tuy nhiên đó có thể do **connection leak, transaction dài, SQL lock hoặc downstream HTTP bị chờ ngay trong transaction**, không chỉ max pool quá nhỏ.

### Bước 4 — Kiểm HTTP connection pool tới target

Quan sát `leased/active`, `available/idle`, `pending`, max per-route, acquire duration, response timeout, connection resets và HTTP/2 active streams. Phân biệt:

- **Acquire timeout**: chưa lấy được connection, request có thể chưa tới Inventory.
- **Connect timeout**: mở TCP/TLS mới không xong; target/network có thể lỗi.
- **Response timeout**: lệnh có thể đã tới và tạo side effect, kết quả có thể **UNKNOWN**.
- **HTTP 429 từ Inventory**: provider từ chối vì quota của credential/account, không chứng minh pool hết slot.

Nếu response body/stream không được đọc hoặc đóng, lease có thể không trở về pool. Nếu upstream chậm, leased có thể bị giữ lâu dù pool code đúng.

### Bước 5 — Phân tích retry và deadline

Đếm số attempts ở **mọi tầng**: SDK → gateway → Orders → Inventory. Một request từ client có thể sinh nhiều outbound requests qua retry. Kiểm `Retry-After`, jitter, backoff, total deadline, circuit breaker/bulkhead và concurrency.

Nếu adapter retry 3 attempts và SDK retry 3 attempts, một thao tác có thể phát tới **9 calls** downstream; nếu tăng nữa khi gặp timeout, rate limit bị chạm dù request gốc không tăng. Không retry POST/PATCH với tác dụng phụ nếu chưa có idempotency contract và key ổn định.

### Bước 6 — Cô lập thay đổi, triển khai có guardrail

Trước khi tăng pool/quota, xác định phương án ít rủi ro:

- Sửa key hoặc đơn vị quota, đưa về chính sách đã công bố.
- Giảm thời gian transaction, tách HTTP call ra khỏi transaction nếu có cách giữ bất biến nghiệp vụ.
- Thêm bounded acquisition queue, bulkhead, load shedding; ngăn retry storm trước khi mở thêm capacity.
- Điều chỉnh max JDBC pool theo **ngân sách DB cấp cụm**, không chỉ cho một pod.
- Điều chỉnh HTTP max per route theo **khả năng của upstream**, không chỉ theo RPS của Orders.
- Rollback cấu hình/phiên bản gây khác biệt giữa các replica, đồng thời đảm bảo bảo mật vẫn đúng.

Sau thay đổi, kiểm cả **HTTP response của consumer**, Hikari/HTTP pool, p95/p99, throughput thành công, retries và tác dụng phụ kinh doanh. Không tuyên bố “đã sửa” khi 429 giảm nhưng 503/timeout tăng hoặc server tạo đơn trùng.

## 6. Chẩn đoán HikariCP bằng metric và PostgreSQL

### 6.1. Cấu hình Spring Boot minh họa

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-db
      maximum-pool-size: 10
      minimum-idle: 3
      connection-timeout: 600
      validation-timeout: 400
      max-lifetime: 1500000
      idle-timeout: 600000
      keepalive-time: 300000

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Các giá trị thời gian Hikari ở đây tính theo **mili giây**. `connection-timeout: 600` nghĩa đợi tối đa ~600 ms để mượn JDBC connection, **không phải** timeout SQL query hoặc socket HTTP. Cấu hình trên chỉ là ví dụ; phải chọn theo latency budget, năng lực DB và môi trường. `validation-timeout` phải nhỏ hơn `connection-timeout`, và giới hạn Hikari cụ thể tùy version cần được xác nhận khi chạy.

Spring Boot Actuator + Micrometer với registry phù hợp thường cung cấp các metric Hikari như active, idle, pending, timeout; tên series thực tế khi export Prometheus phụ thuộc version. Cấu hình `management.endpoints.web.exposure.include` không thay việc chặn truy cập metrics bằng network/auth. Không mở `/actuator/prometheus` cho Internet công khai.

### 6.2. Mẫu SQL điều tra PostgreSQL có quyền hạn

~~~sql
-- Tổng số kết nối theo trạng thái (role cần quyền nhìn thích hợp).
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state
ORDER BY count(*) DESC;

-- Những phiên đang chờ (ẩn text query nhạy cảm trong dashboard public).
SELECT pid,
       usename,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND (wait_event IS NOT NULL
       OR state = 'idle in transaction')
ORDER BY transaction_age DESC NULLS LAST
LIMIT 25;

-- Giới hạn kết nối toàn PostgreSQL (không đồng nhất Hikari max).
SHOW max_connections;
~~~

`pg_stat_activity` hiển thị theo quyền; không cấp superuser cho monitoring vô cớ. `idle in transaction` lâu có thể giữ lock hoặc connection; SQL lock wait là nguyên nhân khác với “chưa đủ max connections”. Kiểm thêm số pod đang chạy và các ứng dụng khác dùng DB, không chỉ một instance Orders.

### 6.3. Tổng JDBC connections phải nhân theo replica

Ví dụ có 8 pod, mỗi Hikari `maximumPoolSize=10`, PostgreSQL cấu hình tối đa 70 connections; cần dành 20 cho admin, jobs và service khác.

Tính sơ bộ:

\[
C_{\text{potential}}=8 \times 10 =80,\qquad
C_{\text{app budget}}=70-20=50
\]

Như vậy chỉ riêng cấu hình Orders đã có **80 potential connections**, vượt ngân sách còn lại **50**. Đặt tối đa 6/pod cho 8 pod cho **48** connections là một hướng ban đầu, nhưng còn phải xét autoscaling surge, background workers, số pool trong mỗi pod và nhu cầu thực tế. Không nhất thiết DB sẽ lập tức mở đủ 80 connections vì Hikari chỉ tạo theo demand/config; đây là **rủi ro ở trạng thái peak**, cần được đo.

Một pool nhỏ hơn không tự chữa việc giữ connection 10 giây trong transaction; có thể cần sửa transaction boundary, query plan, lock contention hoặc upstream dependency. Trước khi tăng `maximumPoolSize`, xác minh DB CPU/IO, query time, locks và tổng số active connections.

### 6.4. Dạng code tạo pool starvation

~~~java
@Transactional
public OrderView updateAndFetchStock(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("PROCESSING");

    // Một lời gọi mạng có thể mất 2 giây; JDBC connection/lock
    // đã mượn có thể bị giữ cho đến khi @Transactional kết thúc.
    Stock stock = inventoryClient.getStock(order.getSku());

    return mapper.toView(order, stock);
}
~~~

Nếu 10 request đồng thời đi tới đoạn chờ Inventory, Hikari có thể hết slot dù DB không bận thực thi SQL. Thiết kế thay thế thường là transaction ngắn để ghi trạng thái/intent, commit, gọi downstream có timeout riêng rồi transaction ngắn khác kiểm optimistic version/state và lưu kết quả. Khi là payment/stock reservation, dùng outbox/idempotency/reconciliation để không mất tính nhất quán khi tách transaction.

**Không sửa bằng cách bỏ `@Transactional` mà không nghĩ tới lost update.** Tách transaction phải đi kèm trạng thái nghiệp vụ và điều kiện cập nhật đúng, không chỉ cải thiện metric.

## 7. HTTP connection pool cạn: khác HikariCP và khác quota

HTTP client có connection pool riêng đến target. Ví dụ Orders dùng Spring `RestClient` với Apache HttpClient 5; manager có thể giới hạn `maxTotal` và `maxPerRoute`, request chờ lease theo `connectionRequestTimeout`.

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class InventoryHttpConfig {
    @Bean(destroyMethod = "close")
    CloseableHttpClient inventoryApacheClient() {
        var manager = new PoolingHttpClientConnectionManager();
        manager.setMaxTotal(40);
        manager.setDefaultMaxPerRoute(20);
        manager.setDefaultConnectionConfig(ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofSeconds(1))
            .setTimeToLive(TimeValue.ofMinutes(5))
            .build());

        var request = RequestConfig.custom()
            .setConnectionRequestTimeout(Timeout.ofMilliseconds(250))
            .setResponseTimeout(Timeout.ofSeconds(2))
            .build();

        return HttpClients.custom()
            .setConnectionManager(manager)
            .setDefaultRequestConfig(request)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }

    @Bean
    RestClient inventoryRestClient(
            CloseableHttpClient inventoryApacheClient) {
        return RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .requestFactory(new HttpComponentsClientHttpRequestFactory(
                inventoryApacheClient))
            .build();
    }
}
~~~

Giới hạn trên **theo instance**, không phải toàn cụm. `connectionRequestTimeout` giới hạn **thời gian chờ pool**, không phải timeout network. `responseTimeout` theo semantics của Apache HttpClient, không thay thế deadline toàn nghiệp vụ. Ở các phiên bản khác nhau, cấu hình API có thể khác; cần kiểm BOM của dự án trước khi áp dụng.

Với Java `java.net.http.HttpClient`, nên dùng chung instance; tuy nhiên API công khai không cho tùy chỉnh max-per-route/pending tương đương Apache. Với HTTP/2, nhiều stream có thể chia sẻ connection: phải kiểm negotiated protocol và **stream concurrency**, không kết luận có đúng một request mỗi socket.

### 7.1. Đọc/đóng response body để tránh pool leak

~~~java
import java.io.InputStream;
import java.net.http.HttpResponse;

HttpResponse<InputStream> response =
    client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Parse/stream có giới hạn kích thước.
    // Đóng body cả khi parser ném exception.
}
~~~

Không trả raw `InputStream` ra khỏi service mà không quy định ownership/close. Response không tiêu thụ hoặc không đóng đúng có thể giữ connection leased. Tương tự, JDBC `Connection.close()` trên Hikari pooled connection thường là **trả lại pool**, phải dùng `try-with-resources` hoặc transaction manager.

### 7.2. Sơ đồ xác định điểm nghẽn

~~~text
HTTP outbound request pending:
  - chưa có pool lease?
      -> acquire timeout, xem leased/max, body leak và per-route limits
  - đang thiết lập TCP/TLS?
      -> DNS, connect timeout, TLS handshake, stale connection
  - đã gửi nhưng chưa có response?
      -> upstream latency, overload, quota, timeout và side effects
  - đã nhận 429 từ upstream?
      -> xem quota theo provider account/key, Retry-After, SDK retry
  - đã nhận response nhưng leased không giảm?
      -> body streaming/close, connection manager lifecycle
~~~

**Sự khác nhau rất quan trọng:** một acquisition timeout có thể xảy ra **trước khi request tới provider**, trong khi response timeout sau gửi có thể làm trạng thái business **UNKNOWN**. Không retry các lệnh không idempotent bằng key mới chỉ vì code bắt `IOException`.


## 8. Cấu hình không đồng nhất: một “limit” nhưng nhiều cách đếm

### 8.1. Case study: cùng khách hàng, mỗi tầng một ngưỡng

Giả sử hệ thống có các policy:

| Tầng | Cấu hình đang có | Diễn giải đúng |
|---|---|---|
| Gateway | 120 req/min **per API key**, fixed window | Một API key có 120 request trong mỗi cửa sổ gateway |
| Orders app | 50 req/10s **per tenant**, token bucket | Một tenant có refill tương đương 5 token/s, burst phụ thuộc capacity |
| Orders bulkhead | 15 requests in-flight **per pod** | Giới hạn công việc đồng thời, không phải 15 req/s |
| HikariCP | 10 JDBC connections **per pod** | Giới hạn connection đang tồn tại trong pool mỗi instance |
| HTTP Inventory | 20 connections **per route per pod** | Transport concurrency, không phải quota client |
| Inventory provider | 200 req/min **per shared merchant account** | Tất cả pod/client cùng dùng một hạn mức provider |
| PostgreSQL | 70 total connections **per cluster** | Nhiều service/jobs chia sẻ, có reserve |

Một request của Tenant A có thể:

1. Vượt gateway quota 120/min và nhận 429 ở gateway.
2. Không vượt gateway nhưng vượt 50/10s vì burst; nhận 429 ở Orders.
3. Không vượt hai quota trên nhưng bị Orders bulkhead từ chối khi 15 in-flight; nhận 503.
4. Được app nhận nhưng Hikari acquisition timeout; service không thể xử lý và có thể trả 503.
5. Được DB phục vụ nhưng Inventory provider hết **merchant-wide quota**; Orders phải quyết định có thể degrade hay trả 503/429 theo nghĩa hợp đồng.

Vì vậy, dashboard chỉ có một đường `rate_limit=120` là không đủ. Cần **manifest ranh giới** cho từng limit: `policyId`, layer, scope, key, units/window, burst, mode, config version, source, owner, effective timestamp, metric và status mapping.

### 8.2. Policy manifest minh họa

~~~yaml
policies:
  - id: gateway-partner-requests-v3
    layer: gateway
    scope: verified-client-id
    limit: 120
    window: PT1M
    algorithm: fixed-window
    statusOnExceeded: 429
    owner: api-platform
  - id: tenant-order-burst-v2
    layer: orders-api
    scope: verified-tenant-id
    capacity: 50
    refillPerSecond: 5
    algorithm: token-bucket
    statusOnExceeded: 429
    owner: orders-team

resources:
  - id: orders-hikari
    scope: pod
    maximumConnections: 10
    acquisitionTimeoutMillis: 600
    statusWhenCapacityUnavailable: 503
  - id: inventory-http-route
    scope: pod-route
    maximumConnections: 20
    acquisitionTimeoutMillis: 250
    statusWhenCapacityUnavailable: 503
  - id: inventory-provider-budget
    scope: shared-merchant-account
    limit: 200
    window: PT1M
    providerResponse: 429
    owner: integration-team
~~~

Đây là **mẫu mô tả chính sách** để thảo luận/CI, không phải cấu hình Spring hoặc gateway có thể chạy trực tiếp. Những đơn vị như ISO-8601 `PT1M`, `Millis` và `PerSecond` phải được parse/tài liệu hóa rõ. Không trộn `requests/minute`, `tokens/second` và `connections` thành cùng một con số; các tài nguyên khác nhau phải có kiểu đơn vị tương ứng.

### 8.3. In-memory limiter bị nhân với số pod

Giả sử mỗi pod giới hạn `100 req/min per client` **trong bộ nhớ của chính pod đó**. Với 6 pods, cùng một client có thể đi qua nhiều pod, làm tổng số request được cho phép trong một phút **có thể cao hơn 100**. Không có một tổng chính xác cố định: nó phụ thuộc routing, stickiness, thời điểm đến và bucket state.

- Nếu API gateway thực thi quota **tập trung** theo key được xác minh, ứng dụng có thể không cần lặp cùng một quota, nhưng vẫn cần concurrency limit để tự bảo vệ.
- Nếu nhiều pod thực thi **quota chung**, dùng kho state/limiter phân tán hoặc gateway với thao tác **atomic**. Ví dụ Redis Lua script cho check-refill-decrement trong cùng operation.
- Nếu quota theo pod có chủ đích, phải gọi đó là **per-instance capacity**, không quảng bá như giới hạn toàn dịch vụ chắc chắn 100/min.
- Autoscaling hoặc deploy canary làm số replica và cấu hình thay đổi; chạy test với một pod không chứng minh quota trên cả cluster.

Cả khi có Redis, chỉ `GET tokens` rồi `SET tokens-1` trong hai thao tác rời không atomic sẽ có race. Cần kiểm request đồng thời và bảo đảm key namespace tách env, issuer, tenant, principal và policy version phù hợp.

### 8.4. Đồng hồ, TTL và các window khác nhau

**Fixed window** 100/min có thể cho phép burst gần ranh giới phút: 100 request lúc 12:00:59 và 100 request lúc 12:01:00, dù trong hai giây có 200 calls. **Sliding window** và **token bucket** có hành vi khác. Đừng suy thời điểm reset chỉ từ `limit=100/min`.

Với token bucket capacity `B`, refill rate `r` token/giây và một request tiêu tốn `cost`:

\[
tokens_{\mathrm{new}}=\min(B,tokens_{\mathrm{old}}+r \Delta t)
\]

Nếu `tokens_new < cost`, thời gian chờ gần đúng là:

\[
wait \approx \frac{cost-tokens_{\mathrm{new}}}{r}.
\]

Đây chỉ là **ước lượng trong một bucket không có request cạnh tranh**; `Retry-After` không bảo đảm lần sau sẽ được cấp ngay. Với limiter phân tán, phải đồng bộ thời gian theo thiết kế, tránh clock skew khiến reset không ổn định.

Các lỗi cấu hình thường gặp:

- Hai tầng cùng hạn chế `50`, nhưng tầng A hiểu `per second`, tầng B hiểu `per minute`.
- TTL trên Redis ngắn hơn cửa sổ quota khiến key biến mất sớm và reset bất ngờ.
- `X-RateLimit-Reset` dùng epoch seconds ở server nhưng client tưởng số giây còn lại. Header tùy biến phải được định nghĩa trong API contract; không suy đơn vị từ tên.
- Thay quota policy nhưng vẫn dùng Redis key cũ, giữ state không tương thích giữa thuật toán/phiên bản.
- Một rule gồm API key và route group, rule khác gom toàn bộ route vào cùng bucket.
- Dùng một merchant credential cho nhiều tenant làm quota provider bị chia sẻ, trong khi catalog công bố quota “riêng cho từng tenant”.

### 8.5. Thứ tự kiểm quota, quyền và tác dụng phụ

Cần định nghĩa pipeline có chủ ý. Ví dụ quota theo tenant đã xác thực chỉ được tính sau khi principal và membership đã được kiểm chứng. Một WAF IP limiter trước authentication là cơ chế chống abuse khác.

~~~text
Inbound:
  network/edge protection -> authentication -> authorization/membership
  -> consumer quota -> concurrency admission -> business operation
  -> DB/downstream -> HTTP response
~~~

Đây là **thứ tự khái niệm**, không khẳng định mọi proxy phải tuân thủ hoàn toàn. Nếu request bị 429 **trước bước ghi**, nó không nên tạo order/payment. Nếu quota được trừ khi request đã chấp nhận nhưng worker chạy bất đồng bộ, cần công bố liệu replay/idempotent request có tính thêm quota không. Khi bất kỳ thao tác POST nào timeout **sau khi gửi**, không thể suy “không có side effect” chỉ từ status của client.

## 9. Timeout budget và retry storm làm nhiều giới hạn cùng bị chạm

### 9.1. Ba loại chờ cần đặt tên

| Pha | Ngưỡng ví dụ | Kết luận có thể rút ra |
|---|---:|---|
| Hikari acquire JDBC | 600 ms | Không có JDBC connection kịp thời; chưa chứng minh DB query chậm |
| HTTP pool acquire | 250 ms | Chưa có connection/stream slot tới Inventory; request có thể chưa gửi |
| HTTP connect | 1 s | Không thiết lập connection mới kịp; khác read timeout |
| HTTP response | 2 s | Đã tiến tới HTTP request; provider có thể đã xử lý một phần |
| Gateway upstream timeout | 2,7 s | Gateway không nhận response kịp; client có thể thấy 504 |
| Client operation deadline | 3 s | Ngân sách cho toàn bộ việc của người dùng |

Những con số **không phải các timeout được cộng tuần tự một cách tự động**; một số pha có thể chồng lấn, hoặc chỉ phát sinh trong một đường đi. Phải đo **thời gian còn lại** trước mỗi downstream call. Nếu đã chờ 1,5 giây để lấy DB connection, không nên cấp một cuộc gọi HTTP dài 2 giây khi deadline của client chỉ còn 1 giây.

Một quy tắc thiết kế: downstream attempt deadline phải nằm trong ngân sách còn lại của service và gateway, còn client deadline cần đủ để nhận response/notification theo contract. Nếu thiết kế async dùng `202 Accepted`, deadline của việc **nhận command** khác thời gian hoàn tất workflow; không được giả vờ 202 là đơn đã thanh toán.

### 9.2. Khi timeout sinh thêm 429

~~~mermaid
sequenceDiagram
    actor C as Client
    participant G as Gateway
    participant O as Orders
    participant I as Inventory
    C->>G: POST /orders (K)
    G->>O: Forward
    O->>I: Reserve(K-stock)
    Note over I: Inventory xử lý chậm
    G-->>C: 504 timeout
    C->>G: Retry ngay POST /orders (K)
    G->>O: Retry
    O->>I: Retry reserve nếu không dedupe
    Note over G: Retry tăng request count
    G-->>C: 429 vì gateway quota
~~~

Nguyên nhân ban đầu có thể là timeout, nhưng triệu chứng cuối cùng client thấy là 429. Nếu chỉ điều tra 429 sau cùng, dễ bỏ sót Inventory latency. Client nên giữ **cùng Idempotency-Key** cho một thao tác logic và không retry POST/PATCH nếu API chưa cam kết dedupe; các tầng phải dùng backoff+jitter và giới hạn tổng số attempts.

### 9.3. Retry có `Retry-After`

- Với `429`: giảm tốc theo đúng quota key. Nếu có `Retry-After` hợp lệ, đợi **ít nhất** khoảng đó; nếu lớn hơn deadline tổng, dừng và thông báo/lên lịch lại.
- Với `503`: retry chỉ nếu lỗi thoáng qua và operation an toàn; dùng exponential backoff + jitter và ngừng khi vượt ngân sách.
- Với `504` hoặc transport timeout: request upstream có thể **đã thực thi**, nhất là POST payment; kiểm idempotency/reconciliation trước khi gửi lại.
- Với `400/401/403/409` do input/quyền/contract: retry nguyên request thường không giải quyết được.
- Không retry liên tục ở cả gateway, service và SDK. Một chủ thể nên sở hữu chính sách retry, hoặc chia budget rõ để không nhân tải.

Nếu một provider trả `Retry-After: 30` cho credential shared, Orders không nên phát lại mọi request queued cùng một lúc sau 30 giây. Cần rate-schedule có giới hạn concurrency và jitter **không sớm hơn** thời điểm tối thiểu; lưu việc đã được chấp nhận thật sự trước khi trả 202.

## 10. Java/Spring: ánh xạ lỗi đúng nguyên nhân

### 10.1. Không biến mọi lỗi kỹ thuật thành 429

Tránh anti-pattern:

~~~java
try {
    return orderService.create(request);
} catch (Exception ex) {
    // SAI: Hikari timeout, JSON bug, downstream 503 và mọi lỗi
    // đều bị gán "client quá hạn mức".
    throw new ResponseStatusException(
        HttpStatus.TOO_MANY_REQUESTS, "Too many requests");
}
~~~

Mẫu này khiến client bị đổ lỗi oan, retry sai và dashboard không biết backend đang quá tải. Hãy phân loại theo **domain reason đã được xác minh**, không dùng câu chữ của exception để quyết định status.

### 10.2. Problem Details cho quota và capacity

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

final class ConsumerQuotaExceeded extends RuntimeException {
    private final long retryAfterSeconds;
    ConsumerQuotaExceeded(long retryAfterSeconds) {
        this.retryAfterSeconds = Math.max(1L, retryAfterSeconds);
    }
    long retryAfterSeconds() { return retryAfterSeconds; }
}

final class ServiceCapacityUnavailable extends RuntimeException {
    ServiceCapacityUnavailable(String causeCode) {
        super(causeCode); // Nội bộ, không lộ ra body cho người gọi.
    }
}

@RestControllerAdvice
class ApiCapacityProblemHandler {
    @ExceptionHandler(ConsumerQuotaExceeded.class)
    ResponseEntity<ProblemDetail> rateLimited(
            ConsumerQuotaExceeded ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.TOO_MANY_REQUESTS,
            "Đã vượt hạn mức gọi API.");
        p.setTitle("Too Many Requests");
        p.setProperty("code", "CLIENT_RATE_LIMITED");

        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
            .header(HttpHeaders.RETRY_AFTER,
                Long.toString(ex.retryAfterSeconds()))
            .cacheControl(CacheControl.noStore())
            .body(p);
    }

    @ExceptionHandler(ServiceCapacityUnavailable.class)
    ResponseEntity<ProblemDetail> capacityUnavailable(
            ServiceCapacityUnavailable ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Hệ thống tạm thời không thể tiếp nhận yêu cầu.");
        p.setTitle("Service Unavailable");
        p.setProperty("code", "SERVICE_CAPACITY_UNAVAILABLE");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            // Không tự tạo Retry-After nếu không ước lượng được.
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

`ProblemDetail` do Spring Framework hỗ trợ tạo body phù hợp `application/problem+json`. `code` là extension ổn định của API; có thể bổ sung `requestId` an toàn. Không đưa password, SQL, stack trace, API key, host nội bộ hay tenant của người khác vào response. Cần test handler và mapping của các exception thực tế.

**Điểm quan trọng:** Hikari acquisition timeout thường được Spring Data/JDBC bọc qua các exception khác nhau (ví dụ `CannotGetJdbcConnectionException` hoặc các `DataAccessException` phù hợp). Không map **mọi** `DataAccessException` thành 503 mà không xác minh nguyên nhân; unique constraint conflict, lỗi SQL lập trình và authorization có semantics khác. Phân loại rõ tại adapter/service boundary theo cause và telemetry, rồi ném exception có nghĩa nghiệp vụ/kỹ thuật phù hợp. Các lỗi 401/403 phát trong Spring Security filter chain có handler riêng, `@RestControllerAdvice` không bắt mọi nhánh bảo mật.

### 10.3. Quota key từ danh tính đã kiểm chứng

Trong Spring Security Resource Server, cần xác minh chữ ký (JWKS hoặc introspection tương ứng), issuer, audience, expiry và quyền/scope. Quota theo user/tenant chỉ nên lấy từ principal đã được xác thực cùng mapping membership:

~~~java
import java.util.UUID;
import org.springframework.security.oauth2.jwt.Jwt;

final class VerifiedQuotaKeys {
    static String forUserTenant(Jwt jwt, UUID tenantId) {
        // Phải gọi service kiểm membership/tenant access TRƯỚC.
        // Đây chỉ là logic tạo key từ principal đã xác minh.
        return jwt.getIssuer().toString()
            + "|" + jwt.getSubject() + "|" + tenantId;
    }
}
~~~

Chuỗi này được dùng như **internal quota key**, không log công khai hay làm Prometheus label. Với API key/provider client khác nhau, thêm identity tương ứng. Không cho client thay đổi `tenantId` trong URL để vượt quota mà không kiểm quyền. Với gateway, `X-Forwarded-For`/`X-Client-Id` chỉ được tin khi do một trust boundary thích hợp gán.

### 10.4. Bulkhead: tài nguyên chung cạn không phải quota user

Ví dụ hạn chế tác vụ đồng thời **chung trên một pod**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
class OrderProcessingBulkhead {
    private final Semaphore slots = new Semaphore(12, true);

    <T> T execute(Supplier<T> work) {
        if (!slots.tryAcquire()) {
            throw new ServiceCapacityUnavailable(
                "ORDER_PROCESSING_BULKHEAD_FULL");
        }
        try {
            return work.get();
        } finally {
            slots.release();
        }
    }
}
~~~

Nếu 12 slot chung đầy, request hợp lệ của nhiều tenant có thể bị 503; không kết luận một tenant đã hết quota. Nếu một giới hạn đồng thời được **công bố theo từng client** như quyền sử dụng, 429 có thể là chính sách phù hợp; phải ghi rõ scope và reason. `Semaphore` trên một pod không phải concurrency limit toàn cụm. Khi job xử lý bất đồng bộ, permit phải được quản lý qua toàn bộ tác vụ thực sự hoặc qua queue admission đúng, không release quá sớm rồi nghĩ rằng đã giới hạn.

## 11. Observability: tách 429 theo tầng, pool theo tài nguyên

### 11.1. Những metric cần đi cùng nhau

| Nhóm | Gợi ý đo | Vì sao |
|---|---|---|
| HTTP edge | Request count by status, route template, source layer | Có 429 trước hay sau app? Có 504 ở gateway? |
| HTTP app | `http.server.requests` latency/status/outcome | App có thấy request không? |
| HTTP outbound | Upstream status, attempts, p95/p99, connection error | Inventory có trả 429/503 không? |
| Quota | decision allow/deny, policy ID/version, reset/bucket occupancy dạng aggregate | Quota thật hay key/config sai? |
| Redis | latency, timeout, key eviction, script errors | State limiter có nhất quán? |
| Hikari | active, idle, pending, total, acquisition timeouts | Pool DB có bị giữ hết không? |
| PostgreSQL | `max_connections`, current sessions, locks, CPU/IO | DB hết connection hay query chậm? |
| HTTP pool | leased, available, pending, acquire wait, max per route | Pool socket có nghẽn không? |
| Retry | attempts per logical operation, budget exhausted, backoff | Có amplification không? |
| Business | orders accepted/completed/unknown, duplicate effects | Hệ thống có trả 2xx sai kết quả không? |
| Deployment | config revision, pod count, canary/version/region | Có giới hạn khác giữa replica không? |

Một số metric Hikari khi xuất Prometheus có tên dạng `hikaricp_connections_active`, `hikaricp_connections_pending`, `hikaricp_connections_timeout_total`; phải kiểm **tên và labels thực tế** trên phiên bản Micrometer/exporter đang sử dụng. Apache HttpClient 5 có `PoolingHttpClientConnectionManager.getTotalStats()` để đọc leased/available/pending, nhưng không phải mọi HTTP client tự xuất các metric này vào Micrometer. Với HTTP/2 cần thêm stream-level signals khi library hỗ trợ.

**Không dùng** `userId`, `orderId`, raw API key, tenant UUID hoặc path chứa ID làm metric label. Dùng `policy_id`, `route template`, `tier`, `status`, `source_layer`, `outcome` từ tập giá trị giới hạn. Trace/log có phân quyền có thể gắn ID dùng điều tra, nhưng không đưa token hoặc PII.

### 11.2. PromQL điều tra mẫu (phải đối chiếu tên metric thực tế)

429 từ ứng dụng theo route:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="orders-api",
    status="429"
  }[5m])
)
~~~

Hikari pending connections của tất cả pod:

~~~promql
sum by (pool) (
  hikaricp_connections_pending{
    application="orders-api"
  }
)
~~~

Tỷ lệ Hikari acquisition timeout:

~~~promql
sum by (pool) (
  rate(hikaricp_connections_timeout_total{
    application="orders-api"
  }[5m])
)
~~~

Nếu app không có tag `application` hoặc exporter khác tên, hãy sửa truy vấn theo **metadata thật** chứ không để biểu đồ âm thầm trống. Không dùng tổng pending của mọi pod như “số request đang chờ toàn bộ ứng dụng” nếu một request có nhiều lần acquire/đường đi. Với 429 do edge trước khi tới app, `http_server_requests_seconds_count` trên Spring sẽ **không** tăng; phải lấy thêm metric gateway từ cùng tập request quan sát.

### 11.3. Structured logs và trace theo một request

~~~json
{
  "timestamp": "2026-11-18T10:15:00Z",
  "service": "orders-api",
  "route": "POST /api/orders",
  "status": 503,
  "error_code": "SERVICE_CAPACITY_UNAVAILABLE",
  "source_layer": "application",
  "reason": "HIKARI_ACQUIRE_TIMEOUT",
  "hikari_pool": "orders-db",
  "acquire_wait_ms": 600,
  "request_id": "req-79c2",
  "trace_id": "8c47a316e5684a36b37f6d9bfad10e21",
  "deployment_revision": "orders-2026-11-18-3"
}
~~~

Lưu ý đây là **mẫu log**. `hikari_pool`, `reason` và `deployment_revision` là các trường **được hệ thống chủ động instrument**, không mặc định do Spring tự phát sinh. Error code phải được đặt theo reason đã phân loại; không lấy exception message đầy đủ làm label. Một trace nên cho thấy thời gian chờ quota decision, JDBC acquire, SQL query, outbound HTTP acquire, connect và response nếu library có instrumentation tương ứng.

Ví dụ hai trace có cùng latency 2 giây nhưng nguyên nhân khác:

~~~text
Trace A (pool DB cạn):
  Orders POST /orders               2,000 ms
    Hikari acquire wait             1,600 ms
    PostgreSQL INSERT                  30 ms
    Inventory HTTP                     90 ms

Trace B (Inventory chậm):
  Orders POST /orders               2,000 ms
    Hikari acquire wait                 4 ms
    PostgreSQL INSERT                  25 ms
    HTTP acquire wait                   2 ms
    Inventory response wait         1,850 ms
~~~

Trace A ưu tiên kiểm connection holding/DB pool; Trace B kiểm upstream latency, circuit breaker và HTTP response timeout. Không kết luận chỉ dựa vào duration tổng hoặc số status 429.

## 12. Khi phải thay cấu hình: bảng quyết định có guardrail

| Dấu hiệu đã xác minh | Hành động ưu tiên | Điều **không** nên làm |
|---|---|---|
| Một client thực sự vượt quota, mọi tầng thống nhất | Throttle client, hướng dẫn Retry-After, xem quota plan | Mở Hikari pool để “chữa 429” |
| Redis key gộp sai tenant/client | Sửa key namespace/identity, migration state và test đồng thời | Tắt authorization hoặc reset toàn bộ state tùy tiện |
| Gateway 100/min nhưng app 20/min ngoài hợp đồng | Thống nhất chính sách, priority/ownership và rollout | Tăng một tầng mà không xem tầng còn lại |
| Hikari active=max, pending cao do transaction chờ HTTP | Thu hẹp transaction, outbox/idempotency, timeout | Tăng `maximumPoolSize` vô hạn |
| Hikari max vượt ngân sách DB cấp cụm | Giảm per-pod, điều chỉnh autoscaling hoặc dùng pooler phù hợp | Tăng PostgreSQL `max_connections` không đo RAM/locks |
| HTTP pool leased=max, pending cao vì body leak | Đóng response/stream, kiểm lifecycle và load test | Chỉ tăng `maxPerRoute` để che leak |
| Upstream 429 do shared provider account | Global budget theo credential, throttle/schedule và circuit | Đổ 429 cho mọi end user không vượt quota |
| Retry storm sau 503/504 | Giảm retry levels, jitter, deadline, idempotency | Retry ngay vô hạn hoặc đổi key POST |
| Một pod khác config/version | Rollback/đồng bộ config, kiểm effective values | Dựa duy nhất vào source YAML |
| 429 giảm nhưng 503 tăng | Đo end-to-end user impact và capacity lại | Tuyên bố thành công chỉ vì status 429 ít |

Hành động mitigation có thể cần rollback, tạm giảm concurrency hoặc bật degraded mode theo contract. Mọi thay đổi production nên có người chịu trách nhiệm, dấu mốc, metric guardrail và rollback path. **Không được lách kiểm quyền** để giảm 403/429 hoặc tắt TLS verification để giải quyết connect failure.

### 12.1. Sửa cấu hình theo tầng

- **Gateway/platform:** kiểm key derivation, namespace, window/refill, policy version, Redis atomicity, region và quota docs; bảo đảm không có rule canary ngoài ý muốn.
- **Application:** kiểm limiter theo tenant/user, bulkhead, exception mapping, transaction duration, request deadline và bản phát hành.
- **Database:** kiểm budget cấp cụm, app role, sessions/locks, query plan, Hikari pool; tránh cấp connection mới vượt năng lực DB.
- **HTTP downstream:** kiểm max per route, pending, body lifecycle, shared credentials/quota, response timeout và retries.
- **Client/SDK:** giới hạn concurrency, exponential backoff+jitter, Retry-After parser, idempotency, retry budget và logging.
- **Security:** kiểm issuer/audience/scope, membership tenant và trusted proxy headers; không dùng chuỗi client tự khai làm quota key tin cậy.

Khi đồng bộ giới hạn, phải biết **giới hạn nào là hợp đồng công khai**, **giới hạn nào là tài nguyên nội bộ**, và ai có quyền quyết định nâng/hạ. Ví dụ quota 100/min theo tenant được ghi trong developer portal khác Hikari max 10/pod nội bộ: không nhất thiết công bố tài nguyên chi tiết nhưng phải vận hành đủ để đáp ứng hợp đồng.


## 13. Kiểm thử có thể tái hiện: quota, pool và cấu hình không nhất quán

### 13.1. Phân tầng kiểm thử

| Loại test | Phụ thuộc cần dùng | Điều phải chứng minh |
|---|---|---|
| Unit policy | Fake clock, in-memory state có kiểm soát | Token bucket/window, Retry-After và đúng subject |
| Spring MockMvc | Controller/Advice/Security mock | 429 khác 503; Problem Details; mã lỗi ổn định |
| PostgreSQL Testcontainers | PostgreSQL thật + Hikari | Pool có giới hạn, acquire timeout, hồi phục sau release |
| HTTP client integration | Fake Inventory server + Apache manager | Max per route, pending, timeout, response-body lifecycle |
| Redis integration | Redis container, nhiều worker/instance | Quota check-decrement atomic, không nhân hạn mức theo pod |
| Component/contract | Gateway → App → DB/downstream fake | Tầng phát status, Retry-After, tenant, idempotency |
| Staging load/fault injection | Nhiều pods, giới hạn thực có kiểm soát | Chất lượng khách hàng khi burst, deploy và retry storm |

Không dùng dữ liệu production hoặc payment provider thật trong bài thử. Testcontainers cung cấp PostgreSQL/Redis thật với fixture tổng hợp; một test chỉ dùng mock quota không chứng minh atomicity trên nhiều JVM. Ngược lại, unit test phép toán backoff không cần container.

### 13.2. JUnit 5 với HikariCP + PostgreSQL Testcontainers

Test sau cố ý giữ hai JDBC connections và chứng minh mượn connection thứ ba vượt giới hạn. Đây là **test pool**, không phải kiểm tra rate limiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.sql.Connection;
import java.sql.SQLTransientConnectionException;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class HikariAcquireTimeoutIT {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("orders_test")
            .withPassword("test-only");

    @Test
    void thirdBorrowTimesOutAndPoolRecovers() throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(postgres.getJdbcUrl());
        config.setUsername(postgres.getUsername());
        config.setPassword(postgres.getPassword());
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(300); // ms; Hikari cho phép >= 250.
        config.setPoolName("orders-it");

        try (HikariDataSource pool = new HikariDataSource(config)) {
            try (Connection first = pool.getConnection();
                 Connection second = pool.getConnection()) {

                assertThrows(SQLTransientConnectionException.class, () -> {
                    try (Connection third = pool.getConnection()) {
                        // Không được có slot thứ ba ở thời điểm này.
                    }
                });
            }

            // Hai connection đã trả pool khi thoát try.
            try (Connection recovered = pool.getConnection()) {
                assertTrue(recovered.isValid(1));
            }
        }
    }
}
~~~

Dependency test gồm `org.testcontainers:postgresql`, `org.testcontainers:junit-jupiter`, JUnit Jupiter, PostgreSQL JDBC driver và HikariCP; phiên bản được quản lý theo BOM của project. CI runner cần container runtime được Testcontainers hỗ trợ. Assertion `SQLTransientConnectionException` phù hợp với timeout acquisition thông thường của Hikari; khi framework bọc exception, kiểm **cause chain** theo stack/phiên bản thay vì assert sai class ở controller.

Để test một **REST API hoàn chỉnh**, gọi endpoint có service dùng DataSource và xác minh status theo HTTP contract. Không đặt `@Transactional` trên test method rồi tin nó rollback những request gửi qua `RANDOM_PORT`; server thread và worker async có transaction riêng. Dọn fixture hoặc dùng DB/schema riêng cho case.

### 13.3. MockMvc kiểm 429 và 503 không bị gộp

Ví dụ sau dùng chính hai exception/handler ở mục 10 nhưng không cần database:

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

class CapacityErrorHttpTest {
    private MockMvc mvc;

    @RestController
    static class DemoController {
        @GetMapping("/demo/quota")
        String quota() {
            throw new ConsumerQuotaExceeded(8);
        }

        @GetMapping("/demo/pool")
        String pool() {
            throw new ServiceCapacityUnavailable("HIKARI_ACQUIRE_TIMEOUT");
        }
    }

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders.standaloneSetup(new DemoController())
            .setControllerAdvice(new ApiCapacityProblemHandler())
            .build();
    }

    @Test
    void quotaIs429WithRetryAfter() throws Exception {
        mvc.perform(get("/demo/quota"))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().string("Retry-After", "8"))
            .andExpect(jsonPath("$.code")
                .value("CLIENT_RATE_LIMITED"));
    }

    @Test
    void capacityIs503WithoutInventedRetryAfter() throws Exception {
        mvc.perform(get("/demo/pool"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(header().doesNotExist("Retry-After"))
            .andExpect(jsonPath("$.code")
                .value("SERVICE_CAPACITY_UNAVAILABLE"));
    }
}
~~~

Test độc lập trên chỉ kiểm **HTTP mapping**; không chứng minh quota key đã xác thực, Hikari thật đã timeout, Redis là atomic hay gateway đã forward đúng header. Bổ sung full Spring context + auth + database/Redis integration test. Spring Security `jwt()` tạo principal giả cho authorization tests, không kiểm chữ ký/issuer/audience JWT thật; cần kiểm thêm Resource Server thật với test JWKS/token nếu security là một phần contract.

### 13.4. Ma trận lỗi cần kiểm ở gateway và service

| Kịch bản | Đầu vào | HTTP kỳ vọng / kiểm bất biến |
|---|---|---|
| API key A chạm quota, B chưa chạm | Gửi burst A và request B | A: 429; B: 2xx; B không bị tính vào quota A |
| Tenant A có 2 app dùng chung tenant quota | Burst từ cả hai app | Tổng token theo tenant, không hai bucket sai |
| Hai pods xử lý cùng key quota | Concurrent calls với Redis | Không cấp nhiều hơn policy shared đã công bố |
| Redis limiter tạm mất kết nối | Mock network/store failure | Fail-open/closed theo policy; không gán sai “đã vượt quota” |
| Gateway 100/min, app 20/min ngoài contract | 30 req/phút hợp lệ | Test phát hiện policy mismatch, không chỉ assert 429 |
| Hikari max=2, 2 connections giữ lâu | Request thứ ba | Acquire timeout; API không map thành 429 |
| Connection release sau lỗi | Exception trong transaction | Permit/connection được trả, request sau phục hồi |
| HTTP pool per route max=2 | Fake target giữ 2 response | Request thứ ba acquire timeout; chưa đến target |
| Response stream chưa đóng | Nhiều lời gọi lặp | Test/metrics chứng minh connection leak; sửa để released về 0 |
| Provider quota merchant shared | Nhiều tenant dưới quota local | Orders nhận upstream 429; không đổ lỗi cho từng tenant |
| Gateway không nhận upstream kịp | Fake delay vượt deadline | Client thấy 504; xem trace từ edge |
| JWT thiếu/sai hoặc thiếu scope | Request bảo mật | 401/403 theo contract, không thành 429/503 |
| POST timeout sau provider đã thực hiện | Fake provider ghi effect rồi cắt response | Retry dùng same-key nếu provider hỗ trợ, không duplicate |
| Retry storm sau 503 | Nhiều client đồng thời | Jitter/budget ngăn retry burst, không tăng side effect |
| Rollout hai policy versions | Một pod cấu hình cũ, một pod mới | Canary/drift alert phát hiện khác biệt |
| Cache CDN ở trước gateway | GET quota status | Không cache 429/503 sai; không rò tenant/token |

### 13.5. Thử tải có kiểm soát để phân biệt nguyên nhân

Thiết lập môi trường staging cách ly và kiểm từng biến:

1. **Baseline:** một pod, quota rất cao, pool đủ cho tải thấp. Ghi p95/p99, Hikari active/pending, HTTP leased/pending, retry attempts và throughput thành công.
2. **Quota test:** một client gửi trên ngưỡng trong khi client khác dưới ngưỡng. Kiểm 429 **chỉ** ở client vượt quota và không phát sinh tác dụng phụ khi bị từ chối.
3. **Hikari test:** giữ số JDBC connections bằng các transaction có latch/SQL wait được kiểm soát; kiểm pending/timeout và 503 theo contract, không phát 429 mơ hồ.
4. **HTTP pool test:** fake target xử lý chậm, giới hạn max per-route, đo acquire time và không gửi request đã timeout chờ pool.
5. **Distributed limiter test:** scale từ 1 lên 3 pod, cùng verified client/tenant key, kiểm tổng số request hợp lệ không thay đổi theo số pod khi policy là shared.
6. **Config drift test:** thay một replica thành policy khác để chứng minh deployment/config audit và alert phát hiện sự khác biệt.
7. **Recovery:** thả latch, đưa dependency về bình thường, kiểm pool available phục hồi và không còn request cũ chờ vô hạn.
8. **Retry storm test:** phát 503/504 từ fake upstream, so outbound attempts khi retry ngay và khi có backoff+jitter/deadline.
9. **Business correctness:** cùng operation ID/idempotency key không tạo order/payment trùng dù có timeout/retry.

Không thử bằng cách gửi hàng loạt `POST /payments` vào production. Thực thi guardrail dừng khi p99, CPU, DB connections hoặc error rate vượt ngưỡng an toàn; báo kết quả gồm **cả những request bị từ chối/timeout**, không chỉ percentile của request thành công.

## 14. Ba mini incident và cách tìm nguyên nhân gốc

### Incident A — 429 sau deploy, lưu lượng không đổi

**Triệu chứng:** 429 tăng từ gần 0 lên 25% đối với nhiều tenant; ứng dụng backend vẫn trả nhanh, Hikari bình thường.

**Bằng chứng:** Gateway access log có `source_layer=gateway`, `policy_id=partner-default-v4`. Cấu hình release đổi từ `100 req/min per API key` sang `100 req/min per source IP`. Nhiều đối tác cùng NAT bị gộp vào một bucket. Tất cả cùng vượt quota IP dù từng API key dưới ngưỡng.

**Kết luận:** Không phải lỗi Hikari hay client bỗng gọi nhanh; đó là **thay đổi key/phạm vi quota không tương thích**.

**Khắc phục:** Rollback hoặc phục hồi policy theo verified client ID, giữ một WAF/IP abuse rule riêng có tính toán cho NAT; kiểm test A/B client cùng IP nhưng key khác; bổ sung config drift gate. Theo dõi 429 giảm mà không tăng 503 và không nới quyền truy cập API.

### Incident B — Pool DB cạn gây 503 rồi 429 do retry

**Triệu chứng:** 503 và 504 xuất hiện trước, vài phút sau 429 tăng; Hikari active=max, pending tăng, DB CPU thấp.

**Bằng chứng:** Traces cho thấy `@Transactional` đã lấy JDBC connection rồi chờ Inventory 2,5 giây. Client SDK nhận 504, retry ngay 3 lần, làm số inbound requests vượt quota gateway. 429 phát sinh ở **lượt retry**, không phải nguyên nhân đầu tiên.

**Kết luận:** Chain là **Inventory chậm → transaction giữ JDBC connection → pool cạn → latency/503/504 → retries tăng → gateway 429**.

**Khắc phục:** Giảm hiệu ứng dây chuyền bằng bounded concurrency và circuit breaker, thu hẹp transaction, lưu intent/outbox và idempotency; đồng thời thêm retry budget/jitter phía SDK. Không chỉ nâng Hikari pool, vì DB connection lớn hơn có thể chuyển overload sang PostgreSQL.

### Incident C — Mỗi pod có một quota, scale làm policy thay đổi

**Triệu chứng:** Client C dưới giới hạn khi 1 pod nhưng nhận 429/200 xen kẽ khi scale 4 pod; ở lần khác client vượt limit lại vẫn nhận 200.

**Bằng chứng:** Một pod dùng sliding window từ Redis; ba pod dùng local fixed-window và policy version cũ. Routing không sticky, nên request đi qua limiter với state/thuật toán khác nhau. Gateway telemetry cho thấy toàn bộ inbound volume thấp hơn ngưỡng shared đã công bố.

**Kết luận:** **Config/state drift giữa replica**, không thể suy một quota chung từ kết quả của một pod.

**Khắc phục:** Đồng bộ chính sách nguồn, áp Redis atomic/shared limiter hoặc quota tại gateway theo authenticated subject, kiểm canary policy version và test load nhiều pods. Kiểm store failure policy, TTL/clock/window và endpoint migration trước khi bật autoscale lớn hơn.

## 15. Bài tập thực hành

### Bài 1 — Phân loại HTTP và tầng phát lỗi

Cho 7 sự kiện: (a) API key A vượt 100/min, (b) Hikari không cấp connection trong 600 ms, (c) HTTP pool không có per-route slot, (d) gateway timeout chờ Orders, (e) Inventory trả 429 vì merchant-wide quota, (f) JWT thiếu scope, (g) Spring trả 500 do bug mapping JSON.

Hãy chọn HTTP status nên trả cho **caller ngoài**, source layer và telemetry cần xem. Giải thích vì sao trường hợp (e) không tự động phải relay 429.

**Gợi ý:** (a) 429; (b)/(c) có thể 503 theo contract; (d) 504 từ gateway; (e) tùy proxy/ownership, thường service-level unavailable/degraded nếu quota shared; (f) 403; (g) 500 nếu bug server không có status cụ thể hơn. Không dùng một status duy nhất cho mọi sự cố.

### Bài 2 — Tính pool cấp cụm

Orders API có 10 pods, Hikari max 12/pod. PostgreSQL `max_connections=100`, cần dự phòng 25 connections cho admin/jobs/services khác. Tính potential connections và ngân sách còn lại cho Orders. Nếu vẫn có 10 pods, nên đặt Hikari max bao nhiêu để không vượt 75 potential connections, chưa xét surge?

**Đối chiếu:** 10×12=120 > 75. Với 10 pods, tối đa 7/pod → 70 potential connections, còn 5 dự phòng trong ngân sách ứng dụng; cần giảm thêm nếu rolling deploy có surge, background pool hoặc proxy connection khác. Đây là **upper bound**, không phải sizing tối ưu tuyệt đối.

### Bài 3 — Đo quota per-user và per-tenant

Có 3 người dùng cùng một tenant, mỗi người gửi 30 req/min. Gateway cho 50 req/min **per user**, Orders app giới hạn 60 req/min **per tenant**. Kết luận có bao nhiêu request có thể bị 429, ở tầng nào, và vì sao việc tính chỉ theo user làm bỏ sót quota tenant. Giả định cùng cửa sổ lý tưởng và không có traffic khác.

**Gợi ý:** Tổng tenant 90/min > 60/min, app có thể từ chối 30 requests theo tenant; từng user 30/min dưới gateway 50/min. Thứ tự request quyết định **ai** bị từ chối; không giả định tất cả rơi vào một user. Nếu window/algorithm khác nhau, kết quả burst có thể khác.

### Bài 4 — Tìm lỗi unit của Retry-After

Một limiter trả `Retry-After: 1500` với ý định chờ 1,5 giây; client hiểu đó là 1500 giây. Một client khác thấy `Retry-After: Wed, 18 Nov 2026 15:00:00 GMT` rồi parse như Unix epoch. Hãy sửa contract, parser và test.

**Tiêu chí:** `Retry-After` dạng số là **giây nguyên không âm**, dạng khác là HTTP-date; nếu muốn chờ xấp xỉ 1,5 giây phải làm tròn theo chính sách (ví dụ tối thiểu 2 giây), không gửi `1500` rồi ghi “ms” trong tài liệu. Có clock skew và overall deadline, không retry trước server advice.

### Bài 5 — Tái hiện connection leak

Dùng Apache HttpClient với per-route max 2. Một adapter stream response nhưng quên đóng `InputStream` khi parse JSON lỗi. Sau vài lượt, leased luôn bằng 2 và pending tăng.

Yêu cầu: viết integration test với fake target, phát exception trong parser, kiểm tài nguyên được release ở `finally`/try-with-resources và request sau vẫn chạy. Nêu khác biệt giữa stale socket reset và response stream leak.

**Tiêu chí:** Cả đường thành công lẫn đường lỗi đều đóng resource; chỉ tăng pool max không được xem là fix.

### Bài 6 — Bảo vệ order khi retry sau 504

Một client `POST /orders` với `Idempotency-Key=K` nhận 504. Provider có thể đã reserve stock và capture payment, nhưng DB Orders chưa cập nhật bằng chứng. Client retry 5 lần với khóa mới.

Hãy thiết kế lại: stable key, operation resource, outbox/inbox, trạng thái UNKNOWN, đối soát provider, deadline và bù trừ khi cần. Nêu status HTTP khi command đã được ghi bền vững và đang xử lý.

**Tiêu chí:** Không tạo nhiều capture/stock reservation cho một thao tác logic. `202 Accepted` chỉ nói command đã được nhận vào xử lý; kết quả nghiệp vụ phải được theo dõi riêng.

### Bài 7 — Viết runbook một trang

Tại `GET /api/orders`, 429 ở edge tăng, một số request trả 503, p99 tăng, Hikari pending=20, Redis quota key cardinality tăng vọt và canary pod chạy release cũ.

Hãy lập **thứ tự kiểm tra 10 phút đầu**, nêu 5 metric, 3 câu log/tracing cần truy vấn, cách chia nguyên nhân theo source layer, và một rollback/mitigation có guardrail. Không gọi 429 là “do user” nếu chưa kiểm key/policy.

**Tiêu chí:** Có owner, request ID, policy version, DB/HTTP pool signals, stop conditions, tổng retries và xác minh sau remediation.

### Bài 8 — Thiết kế integration test đa replica

Hệ thống công bố quota 100 req/min cho từng verified API key, triển khai 3 pod, Redis shared limiter, gateway và Hikari pool riêng từng pod.

Yêu cầu: đưa 200 request đồng thời cùng key qua load balancer, đồng thời gửi 20 request từ key B. Viết assertion ở **tầng contract** và kiểm state/Redis atomicity; thử thêm Redis timeout, rolling deploy policy khác nhau và một HTTP pool cạn.

**Tiêu chí:** A không được cấp vượt 100 theo cửa sổ/quy tắc burst đã xác định, B không bị gộp vào A, không rò tenant, status 429/503 phân biệt, không có side effect ở request bị quota reject. Nếu thuật toán cho phép burst, phải đặt kỳ vọng dựa trên **đúng thuật toán**, không khẳng định mọi lần chạy đều chính xác 100 thành công theo cách gửi bất kỳ.

### Bài 9 — Phân tích retry amplification

SDK retry tối đa 3 attempts, Orders adapter retry tối đa 4 attempts tới Inventory khi thấy timeout. Một request logic có thể sinh tối đa bao nhiêu outbound attempts nếu cả hai tầng cùng thực hiện đủ retry? Đề xuất ngân sách hợp lý hơn và kế hoạch đo actual attempts.

**Đối chiếu:** Tối đa 3×4 = 12 outbound attempts cho một thao tác logic trong tình huống xấu. Kết hợp deadline, jitter, một tầng sở hữu retry khi có thể, và idempotency khi thao tác có tác dụng phụ; đo `attempt_count` theo logical operation, không suy từ inbound RPS.

## 16. Câu hỏi tự kiểm tra

1. **429 có đồng nghĩa database hết kết nối không?** Không. 429 nói về quota/rate limit của caller; pool cạn là vấn đề resource capacity riêng.
2. **Hikari active=max có chứng minh connection leak?** Không. Có thể do transaction dài, lock hoặc workload thực; cần pending/acquire wait/trace.
3. **Vì sao Redis không tự bảo đảm quota toàn cụm nếu check và decrement thành hai lệnh?** Có race; cần thao tác atomic theo thuật toán.
4. **Quy tắc 100/min per pod có phải 100/min toàn cluster?** Không, nếu các pod quản lý state độc lập và traffic qua nhiều pod.
5. **Có thể đếm tổng 429 ở gateway, app và provider bằng cách cộng không?** Không; một logical request có thể được quan sát ở nhiều hop.
6. **HTTP pool acquire timeout có chứng minh Inventory đã nhận request?** Không; request có thể chưa được gửi.
7. **Response timeout có chứng minh payment chưa capture?** Không; kết quả có thể UNKNOWN.
8. **Nếu PostgreSQL max_connections=100, 10 pods Hikari max=12 có an toàn không?** Chưa; 120 potential connections đã vượt 100 trước cả reserve/service khác.
9. **Nên tăng mọi timeout để chữa p99 tăng?** Không; có thể làm giữ connection lâu và tắc queue hơn.
10. **429 từ provider merchant-wide có luôn nên relay 429 cho end user?** Không; phải xem chủ thể quota và hợp đồng proxy/ứng dụng.
11. **`Retry-After: 30` có nghĩa 30 ms?** Không, 30 giây.
12. **Vì sao quan sát quota key theo IP có thể sai?** NAT/proxy chia sẻ IP; header forwarded không tin cậy cũng dễ bị giả.
13. **Làm sao phát hiện config drift giữa pods?** Quan sát effective config/revision, canary tests, policy metrics và so giá trị thực theo replica.
14. **Vì sao 429 tăng sau sự cố 503/504?** Retry storm có thể khiến client chạm quota; cần truy dấu thời điểm và attempts.
15. **Một lệnh POST có thể retry vô điều kiện khi bị 504?** Không; cần idempotency hoặc cơ chế đối soát side effect.

## 17. Checklist điều tra và tài liệu tham khảo

### Checklist “trước khi sửa”

- Đã xác nhận client thực sự nhìn thấy `429`, `503`, `504` hay chỉ transport timeout?
- Đã tìm **source layer** của status bằng gateway/app/outbound logs và một request ID?
- Đã kiểm quota subject/key, policy ID/version, đơn vị/window, algorithm, Retry-After và state store?
- Đã so cấu hình **effective** trên mọi pod/region, kể cả canary, feature flag và gateway?
- Đã kiểm Hikari active/idle/pending/acquire timeout, DB total connections, locks và transaction durations?
- Đã kiểm HTTP pool leased/idle/pending/max per route, response-body close và HTTP/2 stream concurrency?
- Đã kiểm Redis atomicity, store failure policy, TTL/key namespace và đồng hồ?
- Đã tính tổng connection budget từ **số pods tối đa**, scheduler và các service khác?
- Đã đo số attempts/retries theo logical request, deadline, jitter và idempotency cho POST/PATCH?
- Đã kiểm auth/scope/tenant isolation và trusted forwarded headers, không mở quyền để giảm lỗi?
- Đã chọn mitigation theo **nguyên nhân đã xác minh** và có rollback/canary?
- Sau remediation, đã kiểm cả p99, 429/503/504, throughput thành công, pool metrics và side effects?

### Tài liệu đối chiếu

- **RFC 6585 — 429 Too Many Requests:** https://www.rfc-editor.org/rfc/rfc6585#section-4
- **RFC 9110 — HTTP Semantics và Retry-After:** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9457 — Problem Details for HTTP APIs:** https://www.rfc-editor.org/rfc/rfc9457
- **RFC 9111 — HTTP Caching:** https://www.rfc-editor.org/rfc/rfc9111
- **Spring Boot Actuator Metrics:** https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- **Spring Security — OAuth 2.0 Resource Server:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **HikariCP — Configuration:** https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- **Apache HttpComponents Client 5:** https://hc.apache.org/httpcomponents-client-5.4.x/
- **PostgreSQL — Monitoring statistics:** https://www.postgresql.org/docs/current/monitoring-stats.html
- **Testcontainers — PostgreSQL:** https://java.testcontainers.org/modules/databases/postgres/
- **OWASP API4: Unrestricted Resource Consumption:** https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/

**Điểm mấu chốt:** Một response `429` chỉ có ý nghĩa khi biết **policy, chủ thể quota và tầng phát lỗi**. Pool JDBC/HTTP bị cạn thường là vấn đề **năng lực tài nguyên**, còn giới hạn không đồng nhất có thể khiến cùng một request gặp các kết quả khác nhau tùy replica hoặc downstream. Chẩn đoán đúng phải đi từ **HTTP status → source layer → quota key/config → pool/connection metrics → retries/deadlines → tác động nghiệp vụ**, rồi sửa tại đúng ranh giới và xác minh bằng test có kiểm soát.
