# Runbook cho quá tải, chứng chỉ hết hạn và hệ thống đích gián đoạn

## 1. Mục đích: xử lý sự cố mà không làm hỏng hợp đồng REST

Lúc 09:00, `POST /v1/orders` bắt đầu chậm, một số khách hàng bấm thanh toán nhiều lần. Cùng thời điểm, gateway trả `503`, ứng dụng báo `SSLHandshakeException` khi gọi cổng thanh toán và số kết nối đang mở tăng cao. Người trực vận hành phải quyết định **đang quá tải, chứng chỉ TLS hết hạn, hay downstream không phản hồi**; đôi khi cả ba cùng xuất hiện theo chuỗi nguyên nhân–hậu quả.

Runbook là chuỗi **tín hiệu → xác định phạm vi → kiểm chứng giả thuyết → giảm tác động → xác nhận phục hồi → ghi nhận hậu kiểm**. Nó không phải danh sách lệnh để chạy vô điều kiện. Trong REST API, một thao tác “khôi phục nhanh” như bỏ kiểm chứng TLS, bật retry vô hạn, trả `200` với dữ liệu cache lỗi thời hoặc bỏ phân quyền có thể **đổi một sự cố availability thành sự cố bảo mật hoặc thanh toán trùng**.

Bài nằm trong chương **Triển khai và vận hành** thuộc module **INTEGRATION_API_REST**: thiết kế resource/URI, HTTP method và status, hợp đồng dữ liệu, pagination/cache, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử trên Java/Spring. Trọng tâm là một bộ runbook **thực thi được, có điều kiện dừng và rollback** cho ba tình huống thường gặp.

### 1.1. Ba tình huống trong một bảng

| Sự cố | Biểu hiện điển hình | Kiểm tra phân biệt đầu tiên | Hướng giảm tác động |
|---|---|---|---|
| **Quá tải** | p95/p99 tăng, queue/connections đầy, 429/503/timeout | CPU, DB pool, hàng đợi, retry amplification, traffic mix | Giảm tải có ưu tiên, bounded admission, scale khi có capacity |
| **Chứng chỉ hết hạn/sai TLS** | `SSLHandshakeException`, `PKIX path building failed`, gateway HTTPS lỗi | Chứng chỉ nào? Ingress/server hay client → downstream? SAN/chain/time? | Cấp/triển khai cert hợp lệ, reload/restart đúng lớp |
| **Downstream gián đoạn** | Dependency timeout, connection refused, DNS fail, 502/503/504 | Đo direct dependency health/latency và trace qua từng hop | Timeout budget, circuit breaker, bulkhead, fallback có điều kiện |

Một `503` không đủ kết luận nguyên nhân: nó có thể do ingress không còn healthy upstream, pod tự shed load hoặc một dependency lỗi. Một `SSLHandshakeException` cũng không tự chứng minh cert server hết hạn: có thể sai trust chain, hostname, client certificate, clock hoặc giao thức TLS.

### 1.2. Bất biến không được phá để khôi phục availability

1. **Không tắt xác minh certificate/hostname**, không thêm trust-all manager vào JVM.
2. **Không bỏ authentication/authorization/tenant scope** chỉ để GET thành 200.
3. **Không retry POST có side effect bằng key mới** sau timeout; giữ idempotency key và reconcile outcome.
4. **Không phát trạng thái SUCCEEDED khi tác dụng nghiệp vụ chưa commit**; `202 Accepted` phải có operation/status rõ.
5. **Không dùng cache stale cho dữ liệu/quyền cần freshness chặt**, không tiết lộ token/PII qua log, trace hoặc lỗi.
6. **Không làm nghẽn hệ thống thêm bằng chính hoạt động chẩn đoán**: đặt timeout, giới hạn tải truy vấn/trace và tránh dump vô hạn.

## 2. Khung runbook thống nhất: ai, khi nào, làm gì, dừng ở đâu?

Mỗi runbook production nên có metadata ngoài đoạn lệnh:

| Trường | Nội dung cần ghi | Ví dụ minh họa |
|---|---|---|
| Owner và người thay thế | Nhóm sở hữu API và dependency | API on-call; platform/SRE; security/PKI |
| Trigger | Alert/SLO hoặc báo cáo người dùng | 5xx vượt ngưỡng, p99 tăng, cert còn dưới 14 ngày |
| Severity/impact | Bao nhiêu request/tenant/operation ảnh hưởng? | `orders.create` lỗi trên một region |
| Thiết lập ban đầu | Env/region, version, ingress, DB, dependency map | `prod-ap-southeast-1`, release `v42` |
| Quyền thao tác | Ai có quyền scale, rotate cert, thay feature flag? | RBAC theo vai trò, change record |
| Cách đo hiệu quả | Metric người dùng và hệ thống | Success rate, p95, queue, TLS handshake |
| Rollback/stop condition | Điều gì phải dừng nếu xấu đi? | Duplicate charge, auth bypass, error tăng |
| Hậu kiểm | Timeline, nguyên nhân, corrective actions | Có owner và ngày hoàn tất |

**Tách observation với action:** không xoay cert dựa trên một ảnh chụp dashboard duy nhất nếu chưa xác định cert đang được phục vụ ở tầng nào; không tăng pod mù khi nút nghẽn là DB pool 50 connections và cluster không có capacity.

### 2.1. Vai trò khi sự cố vượt mức thông thường

Một người điều phối **incident commander** giữ timeline và ưu tiên khôi phục; người vận hành thực hiện thay đổi; người phụ trách truyền thông thông báo phạm vi/tình trạng; người bảo vệ nghiệp vụ đối soát đơn, thanh toán, quyền. Ở đội nhỏ, một người có thể kiêm vai trò nhưng vẫn cần ghi **ai phê duyệt thao tác có rủi ro**.

Không đưa secrets, raw JWT, private key, số thẻ hoặc response có PII vào chat incident/ticket công khai. Ghi **correlation ID, trace ID, route template, mã lỗi chuẩn hóa, phiên bản release**; bản ghi nhạy cảm được giữ trong hệ audit có quyền truy cập phù hợp.

### 2.2. Thứ tự chẩn đoán: từ tác động khách hàng đến dependency

~~~mermaid
flowchart TD
    A["Alert hoặc báo cáo người dùng"] --> B["Xác nhận request/error/latency theo route, region"]
    B --> C{"Chủ yếu TLS handshake fail?"}
    C -->|Có| D["Kiểm cert/chain/SAN/time: ingress hay outbound"]
    C -->|Không| E{"Capacity/pool/queue bão hòa?"}
    E -->|Có| F["Runbook quá tải; shed load an toàn"]
    E -->|Không| G["Kiểm dependency status, DNS, connect/read timeout"]
    G --> H["Runbook downstream; circuit/fallback/retry budget"]
    D --> I["Xác minh response thực & phục hồi"]
    F --> I
    H --> I
    I --> J["Đối soát nghiệp vụ, rollback nếu vi phạm"]
~~~

Các nhánh không loại trừ lẫn nhau: downstream timeout có thể làm thread pool đầy, dẫn tới `503`; cert hết hạn ở dependency tạo handshake lỗi, kéo theo retry storm. **Tìm nguyên nhân gốc nhưng trước hết giảm tác động lên người dùng** bằng biện pháp có thể đảo ngược và không phá bất biến.

## 3. Quy trình chung trong 10 phút đầu

### 3.1. Xác định phạm vi trước khi sửa

1. **Mốc phát hiện:** ghi giờ UTC, môi trường, release/feature flags gần nhất, endpoint bị ảnh hưởng, tỉ lệ 4xx/5xx/timeout và p95/p99 so với SLO. Tham chiếu cả lượng request thực tế, không chỉ phần trăm khi lưu lượng thấp.
2. **Khoanh vùng:** một instance, một availability zone, một region, một tenant hoặc toàn API? Chỉ request từ gateway hay cả nội bộ? Tương quan với deploy, certificate renewal, DNS/route change, traffic spike và dependency incident.
3. **Đối chiếu bốn tín hiệu:** traffic/error/latency/saturation, cộng dependency latency/health, Kubernetes readiness/restarts, TLS handshake category. Không dùng trace sampled để suy số 5xx toàn hệ thống.
4. **Ngừng tăng blast radius:** tạm dừng rollout nếu có tương quan; đặt chính sách rate limit/shedding có ưu tiên khi tải tăng, **không mở retry rộng hơn**.
5. **Kiểm bất biến nghiệp vụ:** với POST bị timeout, đối soát ledger/idempotency/operation status, không tự tạo lại order; với auth error, bảo đảm không có fail-open.

### 3.2. Bộ lệnh chẩn đoán có giới hạn

Các lệnh dưới đây là **ví dụ**; chỉ chạy trong môi trường được phép, với context/namespace chính xác và truy vấn bounded. Không dùng `kubectl get secrets -o yaml` để “kiểm tra cert”, vì lệnh đó có thể in private key.

~~~bash
# Xác minh context trước, không đoán cluster production.
kubectl config current-context
kubectl -n orders get deploy,pods,svc
kubectl -n orders get hpa
kubectl -n orders describe deploy orders-api
kubectl -n orders logs deploy/orders-api --since=10m --tail=120

# Chỉ query endpoint công khai/đã cấp phép; không in access token.
curl --silent --show-error --connect-timeout 2 --max-time 5 \
  -o /dev/null -w '%{http_code} %{time_connect} %{time_appconnect} %{time_total}\n' \
  https://api.example.com/health
~~~

Kết quả `/health` tốt **không chứng minh business operations tốt**; endpoint liveness thường cố ý không kiểm mọi dependency để tránh restart loop. Một readiness endpoint có thể phản ánh khả năng nhận lưu lượng nhưng không được phụ thuộc vào dịch vụ không thiết yếu theo cách gây rút toàn bộ pods khỏi pool. Xác minh bằng **synthetic transaction an toàn** và dashboard theo operation khi cần.

Nếu cần xem log lỗi, dùng query theo khoảng thời gian/ngưỡng, không bật debug request-body hoặc wiretap `Authorization` trên production. Nếu lượng log tăng đột ngột do lỗi lặp, ưu tiên metric/trace ID và lấy mẫu có ngân sách.

### 3.3. Trước mọi thay đổi: ghi điều kiện kiểm chứng và rollback

Ví dụ thay đổi giới hạn `GET /v1/search` hoặc tăng replicas:

~~~text
Hypothesis: request search tốn DB, làm saturate connection pool.
Action: giảm concurrency search, giữ checkout priority.
Expected within observation window:
  checkout 5xx/timeout giảm; DB active connections giảm;
  search trả 429/503 có giới hạn, không gây retry storm.
Rollback if:
  payment duplicates; JWT/tenant checks bị bypass;
  checkout p99 hoặc error tăng thêm; queue không drain.
~~~

**Một thay đổi một lần khi có thể**, hoặc đánh dấu rõ thời điểm nhóm thay đổi để không mất khả năng quy nguyên nhân. Ghi ai thực hiện, khi nào, giá trị trước/sau; không chỉnh trực tiếp một loạt resource rồi quên trạng thái cần hoàn nguyên.

## 4. Runbook A — API quá tải: ưu tiên giảm tác động và ngăn retry storm

### 4.1. Trigger và phân biệt nút nghẽn

**Kích hoạt** khi latency p95/p99, error budget burn, queue wait, thread/pool saturation hoặc request timeout tăng bất thường. Một spike RPS không nhất thiết là sự cố nếu năng lực còn đủ; ngược lại một downstream chậm có thể làm API quá tải dù RPS không tăng.

| Dấu hiệu | Giả thuyết cần kiểm | Hành động chẩn đoán bounded |
|---|---|---|
| CPU/pod bão hòa, GC pause tăng | Serialization, crypto, code CPU-bound, log quá mức | CPU usage/throttling, profile có giới hạn, triển khai gần đây |
| Tomcat busy threads/queue cao | Blocking downstream/DB, timeout thiếu | Thread pool, latency dependency và connection wait |
| HikariCP pending tăng, DB max connections chạm trần | Query chậm/N+1 hoặc pool quá lớn so DB | Pool active/idle/pending, query p95, lock contention |
| 429 tăng ở gateway | Rate/quota policy chặn | Policy version, theo route/tenant tier, false positives |
| 503 tại ingress nhưng pod không nhận request | Readiness/endpoint count/rollout/capacity | EndpointSlices, pods Ready, ingress upstream health |
| Outbound requests tăng hơn inbound nhiều lần | Retry/hedging amplification | Retry count per original request, timeout budget |
| Queue backlog/consumer lag tăng | Worker xử lý chậm, poison messages, downstream lỗi | Oldest age, processing rate, DLQ theo mã lỗi |

Với HTTP REST, phân biệt **request được chấp nhận nhưng chậm**, **bị chủ động từ chối có kiểm soát** và **không đến được ứng dụng**. Trường hợp cuối có thể không có application trace; cần telemetry của gateway/ingress và external probe.

### 4.2. Hành động trong giai đoạn giảm tải

1. **Đóng van request đắt trước:** áp limit theo route/tenant/user đã xác thực, hạn chế export/report/search nặng; bảo vệ checkout/auth có ngân sách riêng. Đảm bảo thao tác chặn không vô tình chặn toàn bộ tenant vì một client làm quá.
2. **Giới hạn đồng thời và queue:** khi service đang nghẽn, từ chối sớm thay vì nhận vô hạn vào hàng đợi. Đặt deadline/cancellation phù hợp, tránh request time-out trên client nhưng server tiếp tục chiếm slot lâu.
3. **Ngừng retry amplification:** tạm giảm số lần retry, đặt exponential backoff + jitter + retry budget, tắt hedged request không cần thiết. Không retry mù lệnh ghi có side effect.
4. **Scale khi đúng nút nghẽn:** thêm replicas nếu bottleneck CPU và hạ tầng/DB/downstream còn headroom; nếu DB pool đã tối đa, scale API có thể **nhân số connections** và làm hỏng DB nhanh hơn.
5. **Cô lập công việc nền:** giảm concurrency consumer hoặc tạm dừng job không critical có cơ chế resume; không xóa queue/operation để “reset số backlog”.
6. **Tạm rollback release mới** nếu regression tương quan rõ và rollback an toàn với schema/event version; tránh rollback mất khả năng đọc dữ liệu mới.

**Điều kiện dừng:** nếu biện pháp làm tăng duplicate business operations, bỏ auth checks, làm mất event hoặc trả dữ liệu stale trái contract, phải dừng và khôi phục policy an toàn. Không tắt audit bắt buộc để tiết kiệm CPU; thay vào đó bảo vệ luồng audit qua kênh bền vững và giới hạn log debug.

### 4.3. Chọn 429 hay 503 và Retry-After

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 15
Cache-Control: no-store

{"type":"https://api.example.com/problems/rate-limit",
 "title":"Too Many Requests","status":429,
 "code":"RATE_LIMIT_EXCEEDED"}
~~~

`429` phù hợp khi **caller/scope/operation vượt quota**. Nếu **API đang không thể phục vụ do quá tải hệ thống**, có thể trả:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 3
Cache-Control: no-store

{"type":"https://api.example.com/problems/overloaded",
 "title":"Service temporarily unavailable","status":503,
 "code":"SERVICE_OVERLOADED"}
~~~

`Retry-After` là delay-seconds hoặc HTTP-date, **không phải lệnh buộc client retry**. Với 429/503, client chỉ thử lại khi còn deadline/budget và operation retry-safe. Với POST tạo đơn, phải dùng `Idempotency-Key` scoped và outcome ledger; **không tạo key mới** khi response timeout. Nếu edge từ chối request trước khi đến app, app không tự ghi ledger; cần test để không vô tình tạo side effects sau khi đã trả 503.

Tránh trả `200 {"error":"busy"}` làm client và monitoring hiểu sai; tránh body lỗi chứa tên node, cluster capacity nội bộ, SQL, token hoặc tenant khác. `503` có thể bị gateway tự tạo, nên response schema cần đồng bộ ở **đúng tầng phát sinh**.

### 4.4. Spring Boot — giới hạn đồng thời cho operation đắt

~~~java
@Service
class ReportQueryService {
    // Local bulkhead trên MỘT instance; không phải quota toàn cụm.
    private final Semaphore slots = new Semaphore(24, true);
    private final ReportRepository reports;

    ReportQueryService(ReportRepository reports) {
        this.reports = reports;
    }

    ReportView query(Actor actor, ReportFilter filter) {
        if (!slots.tryAcquire()) {
            throw new OperationOverloadedException();
        }
        try {
            // reports.queryScoped phải giữ tenant/authorization predicates.
            return reports.queryScoped(actor, filter);
        } finally {
            slots.release();
        }
    }
}

@RestControllerAdvice
class OverloadErrorAdvice {
    @ExceptionHandler(OperationOverloadedException.class)
    ResponseEntity<ProblemDetail> overloaded() {
        var p = ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        p.setTitle("Service temporarily unavailable");
        p.setProperty("code", "SERVICE_OVERLOADED");
        return ResponseEntity.status(503)
            .header(HttpHeaders.RETRY_AFTER, "3")
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Đây là **mẫu Java/Spring MVC đơn giản**, `ReportRepository`, `Actor`, `ReportFilter`, `ReportView` và exception là kiểu của ứng dụng. Nó chỉ bảo vệ **concurrency ở service method trong một JVM**; nếu có 10 pods thì tối đa lý thuyết 240 queries đồng thời. Bổ sung quota/rate limit theo tenant ở gateway/shared store và giới hạn DB thực nếu cần.

Đặt bulkhead **sau authentication và authorization thích hợp**, không thay kiểm tra quyền của `queryScoped`. Nếu operation có async stages, giữ slot đến khi tác dụng thực hoàn tất; với `Mono`/`CompletableFuture` không thể release ngay khi tạo pipeline như đoạn đồng bộ trên. `Semaphore.tryAcquire()` từ chối ngay, không tích lũy queue ngầm; capacity 24 phải được chọn từ đo đạc, không coi là mặc định hợp lý.

### 4.5. Xác minh phục hồi và rollback

Sau khi shed load, so sánh theo cửa sổ quan sát:

- Error rate/timeout và p95/p99 cho **operation critical** giảm, không chỉ dashboard trung bình.
- Số connection chờ/GC/queue lag và retry amplification giảm; request rate 429/503 có chủ đích không tăng vô hạn.
- Không tăng **business duplicates**, 401/403/404 vẫn đúng, cache không trả private data sai caller.
- Synthetic POST an toàn với idempotency, GET ngay sau write và downstream flow hoàn tất theo contract.

Nếu tải được giải phóng, **mở hạn mức theo từng bước**, tránh thả toàn bộ backlog một lúc. Sau sự cố, xác định root cause: autoscaling, capacity, index N+1, timeout, rate limit hoặc retry storm; viết action item và game-day test.

## 5. Vận hành Kubernetes khi quá tải: readiness, autoscaling, rollout

Một bản triển khai Spring Boot có thể dùng Actuator probe riêng và Kubernetes resource limits:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels: {app: orders-api}
  template:
    metadata:
      labels: {app: orders-api}
    spec:
      containers:
        - name: api
          image: registry.example.com/orders-api:1.8.0
          ports: [{containerPort: 8080}]
          resources:
            requests: {cpu: "500m", memory: "512Mi"}
            limits: {memory: "1Gi"}
          readinessProbe:
            httpGet: {path: /actuator/health/readiness, port: 8080}
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet: {path: /actuator/health/liveness, port: 8080}
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Đây là **manifest minh họa**, không phải bộ cấu hình production hoàn chỉnh: còn cấu hình Spring `management.endpoint.health.probes.enabled`/port, graceful shutdown, startup probe khi khởi động chậm, PodDisruptionBudget, anti-affinity, security context, limits/requests, HPA, config/secrets và policies. **Readiness** thể hiện liệu pod có nên nhận traffic; **liveness** không nên probe mọi dependency bên ngoài vì một downstream outage có thể khiến tất cả pods bị restart liên tục.

Lệnh kiểm tra theo đúng cluster/namespace đã xác minh:

~~~bash
kubectl -n orders get pods -o wide
kubectl -n orders get hpa
kubectl -n orders get endpointslices
kubectl -n orders rollout status deployment/orders-api --timeout=120s
kubectl -n orders describe pod <pod-name>
~~~

Lệnh `<pod-name>` là placeholder. `kubectl describe` có thể in environment/config metadata; không copy output chưa rà soát vào nơi công khai. Khi scale/rollback, dùng change record và quyền RBAC được duyệt; **không tự chạy `kubectl scale` chỉ vì request đang chậm**. Kiểm HPA có pending pods/node capacity, CPU throttling, DB max connections, downstream QPS limit và startup time.

**Cạm bẫy quan trọng:** nếu ingress chỉ có một service nhưng rollout làm mọi pods NotReady vì readiness gọi downstream và downstream đang lỗi, điều chỉnh readiness theo dependency quan trọng thay vì đổi ngay thành “luôn Ready”. Cần giữ khả năng từ chối/shed request an toàn, không để pod nhận traffic khi thật sự không thể phục vụ.

## 6. Runbook B — chứng chỉ TLS hết hạn hoặc handshake thất bại

### 6.1. Nhận diện điểm TLS bị lỗi

HTTPS thường có **nhiều chặng TLS độc lập**:

~~~text
Browser/partner
  | TLS #1: public certificate, SAN api.example.com
  v
CDN / Load balancer / Ingress
  | TLS #2: ingress -> service (nếu dùng TLS/mTLS)
  v
Spring REST API
  | TLS #3: API -> payment.example.net
  v
Downstream payment provider
~~~

**Không mặc định `api.example.com` hết hạn** khi log Spring báo outbound `PKIX path building failed`. Lỗi có thể nằm ở chặng API → payment, private CA, certificate chain thiếu intermediate, SAN không khớp hostname, clock lệch hoặc truststore/JDK thiếu CA mới. Một `502` ở ingress cũng có thể do TLS handshake giữa ingress và pod, dù chứng chỉ trình duyệt vẫn hợp lệ.

| Triệu chứng | Nơi kiểm trước | Lưu ý |
|---|---|---|
| Trình duyệt/curl báo certificate expired của `api.example.com` | Public edge/CDN/ingress đang **phục vụ cert nào** | Secret mới chưa chắc đã được ingress load |
| Java `CertificateExpiredException` khi gọi đối tác | Cert peer outbound hoặc client mTLS cert đang dùng | Kiểm thời gian, chain, host, mTLS |
| Java `PKIX path building failed` | Issuer chain, CA/truststore, TLS interception | Không kết luận ngay “cert expired” |
| `No subject alternative DNS name matching ...` | Endpoint/SNI/hostname configuration | Không bỏ hostname verification |
| `bad_certificate`, `certificate_required` | Mutual TLS client cert | Server có thể từ chối client cert |
| Handshake fail đồng loạt sau ngày rollover | Cert/trust bundle version, key usage, protocol/cipher | So trước/sau triển khai ở đúng chặng |

### 6.2. Lệnh xác minh cert được phục vụ, không đọc private key

Trên máy chẩn đoán được cấp phép:

~~~bash
# Lấy leaf certificate qua đúng SNI; không truyền bearer token.
echo | openssl s_client \
  -connect api.example.com:443 -servername api.example.com \
  -showcerts 2>/dev/null |
  openssl x509 -noout -dates -subject -issuer -ext subjectAltName

# Kiểm chain/hostname trên peer thật (phụ thuộc bản OpenSSL).
echo | openssl s_client \
  -connect api.example.com:443 -servername api.example.com \
  -verify_return_error -verify_hostname api.example.com \
  -brief

# TLS handshake/HTTP timing, không gửi auth header hay body nhạy cảm.
curl --silent --show-error --connect-timeout 2 --max-time 5 \
  -o /dev/null -w '%{http_code} %{time_appconnect} %{time_total}\n' \
  https://api.example.com/health
~~~

Đọc **Not Before**, **Not After**, SAN, issuer, full chain/trust và SNI; đừng chỉ xem `Not After` của một file cert cũ trong kho. `curl` có thể thất bại trước khi HTTP được trả, khi đó `http_code=000` chỉ cho biết chưa có response HTTP, **không phải status 000 thật**. Kiểm certificate chain với đúng trust roots và DNS được sản phẩm hỗ trợ; đừng thêm `-k`/`--insecure` để “test cho xong”.

Với nhiều edge nodes/regions, kiểm từng ingress/POP đại diện: load balancer có thể phục vụ các versions khác nhau trong quá trình rotate. Nếu cùng host dùng nhiều loại cert theo SNI, probe thiếu `-servername` có thể nhìn **default certificate** và kết luận sai.

### 6.3. Quy trình phục hồi inbound certificate

1. **Xác nhận impact:** client nào fail TLS, host/SNI nào, region nào, chứng chỉ nào đang phục vụ? Ghi serial/fingerprint và expiry **không lưu private key**.
2. **Kiểm issuer/CA:** ACME/cert-manager/enterprise PKI có lỗi renew do DNS/HTTP challenge, DNS record, rate limits, IAM, time skew hay CA chain update? Không retry yêu cầu cấp cert vô hạn làm chạm quota CA.
3. **Cấp/chọn chứng chỉ hợp lệ:** đúng SAN, key usage, algorithm/key policy, chain và độ dài hiệu lực; dùng private key được sinh/lưu trong secret manager/HSM/PKI theo chính sách.
4. **Triển khai đúng điểm termination:** cập nhật secret/bundle được ingress/CDN/server dùng; xác minh controller thực sự reload hoặc rollout theo cơ chế hỗ trợ, **không mặc định mount file mới là listener đã đọc lại**.
5. **Xác minh từ bên ngoài:** chạy TLS verify và request synthetic qua host thật từng region; kiểm handshake success, HTTP status, SNI, full chain và certificate fingerprint đã chuyển.
6. **Rút cấu hình cũ:** khi đủ kiểm chứng và rollback policy cho phép, ngừng phục vụ cert expired, rà node chưa được cập nhật, ghi ticket và bổ sung alert trước expiry.

**Điều kiện không được phá:** không bật HTTP plaintext thay HTTPS cho endpoint có credential/PII; không tắt hostname verification; không gửi private key qua chat/ticket; không dùng cert của tenant khác để “tạm thay”. Nếu cert mới có lỗi nhưng cert cũ **vẫn còn hợp lệ và không bị compromise**, rollback có thể khả thi. Nếu cert/key **bị lộ hoặc revoke**, không rollback sang nó.

### 6.4. Kubernetes/cert-manager: kiểm trạng thái mà không lộ bí mật

~~~yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: orders-api-tls
  namespace: orders
spec:
  secretName: orders-api-tls
  dnsNames:
    - api.example.com
  issuerRef:
    name: trusted-issuer
    kind: ClusterIssuer
  renewBefore: 336h # 14 ngày; giá trị minh họa
~~~

Đây là ví dụ **khi cluster đã cài cert-manager CRDs và issuer thực được cấu hình**. TTL/duration, `renewBefore`, validation method và Secret access phải tương thích chính sách CA. Certificate resource kiểm vòng đời cert, không tự cấu hình Ingress; `Ingress.spec.tls[].secretName` phải trỏ đúng secret và đúng namespace.

~~~bash
kubectl -n orders get certificate orders-api-tls
kubectl -n orders describe certificate orders-api-tls
kubectl -n orders get certificaterequests
kubectl -n orders get challenges,orders.acme.cert-manager.io
kubectl -n orders describe ingress orders-api
~~~

`challenges`/`orders.acme.cert-manager.io` chỉ tồn tại với ACME và có thể không có resource ở cluster dùng enterprise CA. **Không chạy `kubectl get secret orders-api-tls -o yaml`**, vì dữ liệu base64 **không mã hóa bí mật** và có thể chứa private key. Khi cần kiểm expiry/fingerprint của cert trong Secret, dùng tooling được duyệt chỉ trích **public certificate** và không in `tls.key`; kiểm lại cert **đang phục vụ** mới là điều kiện kết thúc sự cố.

### 6.5. Cảnh báo trước khi sự cố xuất hiện

Theo dõi **remaining validity** ở certificate endpoint và cả nguồn quản lý cert; đặt nhiều ngưỡng trước hạn (ví dụ 30/14/7 ngày theo quy trình). Có thêm alert khi auto-renew lỗi, challenge pending lâu, Secret không đổi trước hạn, ingress phục vụ serial cũ, tỷ lệ TLS handshake error tăng. Giám sát **chain CA/intermediate và mTLS client certificate**, không chỉ leaf public cert.

Tránh đặt ngưỡng chỉ 24 giờ trước expiry: thời gian phê duyệt PKI, DNS propagation, nhiều region và rollback có thể dài hơn. Diễn tập renewal ít nhất trên staging, kiểm cả **clock skew** và cửa sổ `Not Before` của cert mới để tránh “triển khai thành công nhưng chưa có hiệu lực”.

## 7. Java/Spring: TLS termination, client trust và rotation an toàn

### 7.1. Chọn điểm termination rõ ràng

Trong Kubernetes, TLS public thường kết thúc ở ingress/CDN; Spring Boot có thể nhận HTTP nội bộ trong network policy **hoặc TLS/mTLS tới service** tùy threat model. Không mặc định mạng cluster là tin cậy tuyệt đối. Nếu ứng dụng tự terminate TLS, có thể dùng SSL bundle trên Spring Boot hỗ trợ tính năng này:

~~~yaml
# Spring Boot 3.x với SSL bundle (xác nhận phiên bản áp dụng).
spring:
  ssl:
    bundle:
      pem:
        api:
          keystore:
            certificate: file:/etc/orders/tls/tls.crt
            private-key: file:/etc/orders/tls/tls.key
server:
  ssl:
    bundle: api
  port: 8443
~~~

Các đường dẫn là **file mount với quyền truy cập tối thiểu**, không commit key vào image/Git. **Không coi mọi phiên bản Boot đều tự động reload SSL bundle**: kiểm release/docs, nếu không hỗ trợ thì rollout/restart graceful để listener đọc key/cert mới; kiểm chính xác cert served sau khi rollout. Nếu dùng ingress TLS, đừng “sửa” cert ingress bằng cách đổi `server.ssl` của pod không phải điểm termination.

### 7.2. Outbound TLS: xác minh peer và truststore

Một lời gọi Java qua `RestClient`, `WebClient` hoặc JDK `HttpClient` phải xác minh **chain và hostname** mặc định. Với enterprise CA, cấu hình **trust bundle cụ thể**/SSLContext hoặc connector certificate bundle theo chính sách; việc thêm một CA mới phải qua review và rotation. Không dùng:

~~~java
// PHẢN MẪU — tuyệt đối không đưa vào production:
// TrustManager tin mọi certificate;
// HostnameVerifier trả true cho mọi hostname;
// WebClient / HttpClient dùng insecure TLS.
~~~

Khi gặp `SSLHandshakeException`, phân biệt server certificate và **mTLS client certificate** bằng log lỗi an toàn, chain/SAN, key usage, trust anchors, clock, SNI và TLS negotiation. Chỉ ghi **loại lỗi, hostname dịch vụ đã cho phép, request ID và cert fingerprint** nếu policy cho phép; không log private key/PKCS12 password, full keystore hoặc bearer token.

**Mốc xác nhận phục hồi outbound:** kiểm handshake thật tới endpoint đối tác trên mỗi route/region, call synthetic read-only hoặc sandbox transaction, xác minh p95/error quay về chuẩn, circuit breaker hồi phục và hàng đợi được xử lý. Nếu certificate issue gây timeout hàng loạt, giảm retry trước khi khôi phục để tránh vừa cấp cert xong đã bị request backlog làm quá tải.

## 8. Runbook C — hệ thống đích gián đoạn, timeout hoặc trả lỗi hàng loạt

### 8.1. Xác định downstream hỏng hay caller đang gây nghẽn

API đặt hàng có thể gọi Inventory, Payment, Fraud, Shipping. Người dùng chỉ thấy một lệnh `POST /v1/orders`; nguyên nhân có thể nằm ở một dependency. Đầu tiên xác định **operation nào dùng dependency nào**, có fallback hợp lệ hay không, và có tác dụng đã xảy ra nhưng client chưa biết hay không.

| Lỗi quan sát | Kiểm tra | Điều không được suy diễn |
|---|---|---|
| DNS failure / unknown host | DNS resolver, record, network policy, service discovery | Không phải chứng chỉ hết hạn |
| Connection refused/reset | Destination listener, service endpoints, LB, network | Không chắc request chưa được xử lý nếu reset sau khi gửi |
| Connect timeout | Network/firewall/routing/saturation phía nhận | Không chắc hệ đích “down” toàn bộ |
| Read/response timeout | Upstream latency, queue, database, slow response | **Không chắc side effect chưa commit** |
| `SSLHandshakeException` | Cert peer/client, chain, SAN, SNI, trust, time | Không tự tắt TLS để khắc phục |
| `429` từ downstream | Đã chạm quota provider/client | Không spam retry, tôn trọng budget và policy |
| `503` từ downstream | Provider tạm không phục vụ | Không assume provider không nhận request |
| `400/403/404` từ downstream | Input/quyền/resource thật có thể sai | Không tự retry như transient error |
| Circuit breaker OPEN | Lỗi gần đây vượt threshold hoặc bị isolate | Không kết luận dependency hiện tại vẫn hỏng, cần half-open probe |

Xem **số request gốc** và **số request outbound**. Nếu một request gọi 3 downstream và mỗi layer retry 3 lần, dưới sự cố có thể tạo **lưu lượng nhân cấp số**. Đừng coi 200 RPS incoming là “nhẹ” nếu outbound vượt 1.000 RPS do retries.

### 8.2. Quy trình giảm tác động

1. **Chứng minh loại lỗi:** phân loại DNS/connect/TLS/read timeout/HTTP 429/5xx/business 4xx bằng metrics và một số request ID đã kiểm soát; truy dependency status page/đội sở hữu qua kênh được phép, không lấy thông tin public chưa xác nhận làm kết luận duy nhất.
2. **Giảm áp lực lên dependency:** giới hạn concurrency, queue depth và retry; bật/tinh chỉnh circuit breaker theo số liệu, tránh hơn một lớp retries không phối hợp.
3. **Phân loại thao tác theo tính an toàn:** GET catalog có thể cache stale có giới hạn nếu contract cho phép; `POST /payments` không được fail-open thành `SUCCEEDED` khi upstream không xác nhận.
4. **Giữ operation state bền vững:** với lệnh tạo side effect, lưu idempotency key/outbox/operation status; khi timeout ambiguous, kiểm provider reconciliation thay vì gửi lại với key mới.
5. **Trả lỗi đúng HTTP:** client cần phân biệt tạm thời không sẵn sàng với sai quyền/input, có `Retry-After` khi có căn cứ, không lộ nội bộ.
6. **Phục hồi từng bước:** cho circuit half-open probes có giới hạn, tăng concurrency/rate dần, drain backlog theo budget và xác minh business outcomes trước khi kết thúc incident.

**Ngưng rollback tự động** nếu phiên bản cũ không hiểu event/operation schema mới hoặc sẽ phát lại charge. Khi dùng failover sang provider B, phải kiểm **idempotency có được chia sẻ giữa hai providers không**: thông thường mỗi provider có ledger riêng, chuyển cùng logical payment sang provider khác sau timeout ở A có thể **charge hai lần**.

### 8.3. Fallback chỉ được dùng khi không đổi kết quả nghiệp vụ

| Endpoint và tác dụng | Fallback có thể hợp lệ | Fallback nguy hiểm |
|---|---|---|
| `GET /v1/catalog` public | Cache stale ≤ SLA, gắn freshness metadata khi cần | Trả catalog của tenant khác |
| `GET /v1/orders/{id}` private | Đường primary/replica đáp ứng RYW và auth | Trả cached order theo URL không kiểm lại quyền |
| `GET /v1/shipping-rates` | Ước lượng có cờ “estimate” nếu contract cho phép | Trả giá cũ như đã chốt thanh toán |
| `POST /v1/payments` | Durable PENDING/202 + reconciliation | `200 PAID` khi gateway timeout hoặc thử provider B mù |
| `POST /v1/exports` | Queue bounded + operation `202` nếu enqueue đã durable | 202 khi queue publish thất bại, job không tồn tại |
| Auth/permission validation | Deny/fail closed theo policy | Bỏ auth hoặc dùng ACL cache stale vô thời hạn |

Fallback phải có **nguồn dữ liệu hợp lệ, giới hạn độ mới, quyền truy cập, khả năng hủy và observable counter**. Một circuit breaker chuyển sang fallback mà tăng `200` có thể làm SLO availability trông đẹp; do đó còn phải đo **degraded mode ratio** và domain correctness.

### 8.4. Lệnh kiểm tra một hop thực tế

Không gửi token thật trong shell history. Khi xác minh endpoint công khai hoặc synthetic read-only đã được cấp phép:

~~~bash
# DNS và route chỉ giúp khoanh vùng, không chứng minh nghiệp vụ OK.
nslookup inventory.example.internal

# Bounded HTTP probe trên endpoint không tạo side effect.
curl --silent --show-error --connect-timeout 2 --max-time 5 \
  -o /dev/null -w '%{http_code} %{time_connect} %{time_appconnect} %{time_total}\n' \
  https://inventory.example.internal/health
~~~

Nếu endpoint nội bộ yêu cầu mTLS/auth, dùng **cơ chế credential an toàn của môi trường**, không ghi ví dụ key/password trực tiếp trong lệnh. Probes dùng sai identity có thể trả 401/403 **dù dịch vụ khỏe**; 200 từ `/health` cũng không chứng minh truy vấn inventory hoạt động đúng. Kiểm synthetic business request có quyền và không side effect trong sandbox khi cần.

## 9. HTTP contract khi downstream lỗi và ngân sách timeout/retry

### 9.1. Định nghĩa status theo vai trò tầng đang trả lời

| Mã HTTP | Nghĩa trong REST/gateway | Ví dụ |
|---|---|---|
| **400/422** | Request caller sai hoặc dữ liệu không hợp lệ theo contract | Không retry tự động |
| **401/403** | Caller chưa xác thực/không được phép | Không dùng 503 để che policy error |
| **409/412** | Business conflict/optimistic precondition | Không coi là transient |
| **429** | Scope caller vượt rate/quota | `Retry-After` theo budget |
| **502 Bad Gateway** | Gateway/proxy nhận response không hợp lệ từ upstream | TLS/protocol failure được gateway map theo policy |
| **503 Service Unavailable** | Dịch vụ hiện không sẵn sàng/đang shed load/breaker OPEN | Bounded retry nếu safe |
| **504 Gateway Timeout** | Server làm gateway/proxy không nhận response upstream kịp | Timeout có thể ambiguous với side effects |
| **500** | Lỗi không dự kiến ở service | Public Problem Details trung tính, alert |

Không có ánh xạ duy nhất cho mọi ứng dụng: một REST API đóng vai gateway có thể map dependency failure sang 502/503/504, trong khi service tự gọi provider có thể có domain error riêng. **Chính sách status và error code phải được document trong OpenAPI**, đồng bộ giữa gateway và ứng dụng. Không trả `200` kèm `{"error":"upstream_timeout"}` làm cache, retry, monitoring hiểu nhầm.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 5
Cache-Control: no-store
X-Request-Id: req-71f

{"type":"https://api.example.com/problems/dependency-unavailable",
 "title":"Service temporarily unavailable",
 "status":503,"code":"DEPENDENCY_UNAVAILABLE",
 "requestId":"req-71f"}
~~~

`requestId` chỉ phục vụ tra log, có kiểm tra độ dài/ký tự hoặc do server phát. Không trả URL private của provider, mTLS details, stack trace, payment reference bí mật, raw JWT hoặc lỗi SQL. Với lỗi auth trước MVC, Spring Security filters có thể viết response ngoài `@RestControllerAdvice`; kiểm cả entry point và gateway.

### 9.2. Timeout là ngân sách toàn chuỗi, không phải tùy ý tăng từng hop

Ví dụ client có deadline **4 giây**; API còn ngân sách để auth, DB và response về client. Không thể cho mỗi downstream `readTimeout=10s`, retry 3 lần và vẫn hứa trả trong 4 giây.

~~~text
Client total deadline:             4.0 s
  Gateway / network overhead:      0.3 s
  Authentication / domain checks:  0.3 s
  Inventory upstream attempt:      1.5 s
  DB/commit + response reserve:    1.1 s
  Margin / jitter:                 0.8 s
----------------------------------------
Tổng ngân sách:                    4.0 s
~~~

Các số là **ví dụ để học cách phân bổ**, không phải thông số production. Connect timeout, TLS handshake timeout, response timeout, total request timeout và deadline của client **khác nhau**; tùy HTTP client/framework, nhiều timeout có thể không bao gồm queue wait hoặc DNS. Đặt timeout sau khi đo p95/p99 dependency và retry budget, không chỉ tăng để “hết timeout” vì connection pool sẽ giữ request lâu hơn.

### 9.3. Quy tắc retry an toàn

~~~text
Retry khi:
  - Lỗi được phân loại transient (connect/read timeout, 429/503/504
    theo contract) VÀ operation retry-safe hoặc có dedupe.
  - Chưa hết deadline, còn retry budget và concurrency capacity.
  - Delay = backoff + jitter, giới hạn số attempts.

KHÔNG retry mù khi:
  - 401/403, 400/422 do input/quyền, 409 business conflict.
  - Payment/order POST không có idempotency/reconciliation.
  - Circuit OPEN hoặc downstream overload đang cần shed load.
  - Client đã hủy thao tác và không còn yêu cầu tiếp tục xử lý.
~~~

**Retry xảy ra ở tầng nào?** Nếu gateway, SDK và application đều tự retry, tổng attempts có thể bị nhân lên. Quy định một **retry owner**, propagate deadline/correlation ID và đo `attempts_per_original_request`. Chỉ nên dùng hedged GET khi operation an toàn, tài nguyên downstream đủ và không nhân đôi dữ liệu nhạy cảm/log; hedged POST không được bật mù.

### 9.4. Idempotency với side effect bên ngoài

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant D as DB + ledger
    participant P as Payment
    C->>A: POST /v1/orders + Idempotency-Key K
    A->>D: Commit order PENDING + outbox + K
    D-->>A: COMMIT
    A-->>C: 202 + operation URI
    A->>P: Charge with stable provider key P-K
    P--xA: Timeout; outcome chưa biết
    Note over A,P: Reconcile hoặc retry cùng P-K
    A->>P: Query status / retry idempotent
    P-->>A: CHARGED once
    A->>D: Commit PAID, outbox event idempotent
~~~

Một `202 Accepted` chỉ nói request đã được nhận để xử lý, **chưa hứa thanh toán hoàn tất**. Operation state phải bền vững và có đường query đã phân quyền. Nếu provider không hỗ trợ idempotency/reconciliation, API không thể bảo đảm không charge hai lần bằng một ledger ở nội bộ; cần business safeguard và quy trình xử lý bất định rõ. Với queue/outbox delivery at-least-once, consumer phải idempotent và test duplicate event.

## 10. Java/Spring: outbound timeout, circuit breaker và lỗi công khai

Ví dụ sau dùng **Java 17+, Spring Boot 3.x/Spring WebFlux WebClient + Reactor Netty, Resilience4j Reactor**. Nó áp dụng cho một service Spring MVC **gọi WebClient theo kiểu bất đồng bộ**, hoặc Spring WebFlux; không gọi `.block()` trên event loop. Những class domain là minh họa, cần imports/dependencies phù hợp phiên bản Spring Boot đang dùng.

### 10.1. HTTP client có timeout rõ, không tắt TLS

~~~java
@Configuration
class InventoryHttpConfig {
    @Bean("inventoryClient")
    WebClient inventoryClient(WebClient.Builder builder) {
        HttpClient netty = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
            .responseTimeout(Duration.ofSeconds(2));

        return builder
            .baseUrl("https://inventory.example.internal")
            .clientConnector(new ReactorClientHttpConnector(netty))
            .build();
    }
}
~~~

`connect timeout=500ms` và `response timeout=2s` là số ví dụ; không nên dùng y nguyên trên mọi network/region. `Mono.timeout` ở caller phía dưới thêm deadline tổng của logical call, nhưng **không bao gồm mọi queue wait ở mọi nơi** nếu caller lấy connection từ pool, chờ scheduler hoặc có DNS timeout không được cấu hình. Test phân loại lỗi connect, handshake, response timeout, client cancellation riêng.

Netty mặc định phải được cấu hình để **xác minh TLS peer**, không thêm `InsecureTrustManagerFactory` hay vô hiệu hostname verification. Nếu doanh nghiệp dùng private CA/mTLS, cấu hình SSL bundle/trust manager được phê duyệt; **không gửi chứng chỉ/secret qua URI query**. Đồng thời giới hạn connection pool/pending acquisition ở HTTP client theo capacity dependency để tránh tự làm đầy memory.

### 10.2. Circuit breaker chỉ tính lỗi phù hợp, không trừng phạt 404 nghiệp vụ

~~~java
@Configuration
class InventoryResilienceConfig {
    @Bean
    CircuitBreakerRegistry inventoryCircuitBreakers() {
        CircuitBreakerConfig policy = CircuitBreakerConfig.custom()
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(15))
            .permittedNumberOfCallsInHalfOpenState(3)
            .recordException(error ->
                error instanceof DependencyUnavailableException
                || error instanceof WebClientRequestException
                || error instanceof TimeoutException)
            .build();
        return CircuitBreakerRegistry.of(policy);
    }
}

@Component
class InventoryGateway {
    private final WebClient webClient;
    private final CircuitBreaker breaker;

    InventoryGateway(
        @Qualifier("inventoryClient") WebClient client,
        CircuitBreakerRegistry registry) {
        this.webClient = client;
        this.breaker = registry.circuitBreaker("inventory");
    }

    Mono<StockView> getStock(String sku) {
        return webClient.get()
            .uri("/v1/stocks/{sku}", sku)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                response -> Mono.error(new StockNotFoundException()))
            .onStatus(HttpStatusCode::is5xxServerError,
                response -> Mono.error(new DependencyUnavailableException()))
            .bodyToMono(StockView.class)
            .timeout(Duration.ofMillis(2500))
            .transformDeferred(CircuitBreakerOperator.of(breaker));
    }
}
~~~

`DependencyUnavailableException`, `StockNotFoundException`, `StockView` là các kiểu ứng dụng, code lược imports. Cần dependency **resilience4j-reactor** tương thích Spring/Reactor và `reactor-netty-http` nếu tự cấu hình Netty connector; dựa vào BOM/version được duyệt. `recordException` trong ví dụ cố tình **không tính business 404**, nhưng các status 429/408, DNS/TLS và wrappers cần phân loại cụ thể theo hệ thống. Không để circuit breaker đếm mọi `IllegalArgumentException`/`403` như lỗi upstream để tránh OPEN do client dùng sai.

**Thứ tự điều khiển quan trọng:** circuit breaker giới hạn lưu lượng dựa trên health; bulkhead giới hạn concurrency; timeout cắt request quá lâu; retry chỉ cho lỗi/operation được phép. Nếu cần retry trong chuỗi Reactor, thêm policy bounded **có jitter/deadline** ngoài đoạn mẫu và đo tổng attempts; **đừng thêm `retryWhen(Retry.max(Long.MAX_VALUE))`** hoặc retry POST payment vô điều kiện. `CircuitBreakerOperator` có thể fail nhanh bằng `CallNotPermittedException`, cần map ra 503 an toàn.

### 10.3. Public Problem Details, không phản chiếu lỗi provider

~~~java
@RestControllerAdvice
class DependencyErrorAdvice {
    @ExceptionHandler({
        DependencyUnavailableException.class,
        CallNotPermittedException.class
    })
    ResponseEntity<ProblemDetail> unavailable() {
        ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.SERVICE_UNAVAILABLE);
        p.setTitle("Dependency temporarily unavailable");
        p.setProperty("code", "DEPENDENCY_UNAVAILABLE");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .header(HttpHeaders.RETRY_AFTER, "5")
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Ví dụ này xử lý exception khi đã tới **Spring MVC error pipeline**. Trong reactive controller, exception cần được propagate và Reactor context/cleanup đúng. Các lỗi `WebClientResponseException`, network timeout và security filter có thể cần handlers khác; không dựa vào `@RestControllerAdvice` để bao trùm mọi lỗi do ingress hay Spring Security xử lý trước MVC.

**Không trả nguyên provider error body**, certificate detail hoặc SQL text cho client. Internal telemetry giữ error category `DNS/TLS/CONNECT_TIMEOUT/RESPONSE_TIMEOUT/HTTP_5XX/BREAKER_OPEN`, route template, dependency logical name và correlation ID — không lưu outbound `Authorization`, credential, request body chứa PII, signed URL. Client nhận error code public ổn định, còn on-call dùng audit/trace có phân quyền để chẩn đoán.

### 10.4. Thời điểm trả HTTP 202 cho tác vụ bền vững

Nếu client gọi `POST /v1/exports`, application cần lưu operation và enqueue/outbox **bền vững trước khi trả `202`**. Một controller chỉ chạy `CompletableFuture.runAsync(...)` rồi lập tức trả 202 có thể **mất việc khi pod restart**. Với payment, state machine phải thể hiện `PENDING/UNKNOWN/SUCCEEDED/FAILED` theo dữ liệu đã xác minh, không biến timeout thành FAILED nếu charge có thể đã xảy ra.

Khi breaker OPEN, endpoint **không có fallback đúng** nên trả 503 phù hợp; khi có enqueue bền vững thì có thể 202 với operation URI. Việc trả 202 mà request chưa được persist/được phép xử lý là thay contract sai, không phải chiến lược phục hồi.

## 11. Xác nhận đã phục hồi: kỹ thuật, HTTP và nghiệp vụ

Một incident chỉ kết thúc khi **đã xác nhận lại từ trải nghiệm người gọi**, không chỉ thấy pod Ready hoặc cert mới đã được tạo.

### 11.1. Bộ tiêu chí theo loại sự cố

| Loại | Kiểm tra kỹ thuật | Kiểm tra nghiệp vụ |
|---|---|---|
| **Quá tải** | p95/p99, pool, queue, 5xx/timeout, retry amplification trở về mục tiêu | Checkout/auth hoạt động, không duplicate, 429 policy không khóa oan |
| **TLS** | Handshake verify từ bên ngoài nhiều edge/region; SAN/chain/date/serial đúng | Login/API GET có quyền qua HTTPS hoạt động; outbound client mTLS gọi được provider sandbox |
| **Downstream** | Breaker CLOSED hoặc half-open ổn định; latency/error/queue/fallback giảm | Operation PENDING được reconcile, không hai charge, order/item state đúng |

Để tránh kiểm tra thành công giả, synthetic test phải dùng đúng **route và principal được cấp phép**, với dữ liệu thử nghiệm có thể xóa/đối soát; test `GET /health` không đủ thay cho `POST /orders` và luồng payment. Nếu chỉ một region phục hồi, không thông báo “dịch vụ toàn bộ đã phục hồi”.

### 11.2. Tốc độ phục hồi backlog phải có ngân sách

Sau downstream outage, queue có thể giữ hàng nghìn operations. Mở breaker/consumer concurrency từ 0 lên tối đa tức thì có thể làm provider lại quá tải và 429. Phục hồi theo **ramp-up có kiểm soát**, giữ idempotency và timeout, theo dõi oldest job age, throughput, reconciliation backlog, 429/503 provider và connection saturation. Tách traffic mới khỏi replay/backlog khi chính sách ưu tiên yêu cầu.

Không xóa DLQ để “làm sạch dashboard”. Với poison messages, phải có triage phân loại input lỗi, version không tương thích, timeout transient hay authorization; replay có dedupe và audit. Nếu event đã có side effect, operator không được chạy lại bằng một key/payment intent mới.

### 11.3. Rollback không đồng nghĩa đảo ngược side effect

Rollout app version cũ có thể đảo code, **không thu hồi được một payment đã charge** hay khôi phục dữ liệu private đã lộ. Trước rollback, kiểm schema tương thích, event format, idempotency ledger, trạng thái job đang chạy và trust store/certificate version. Nếu cert cũ đã hết hạn hoặc bị lộ, **không phục hồi bằng rollback cert cũ**. Nếu lỗi do dependency, rollback app không giải quyết root cause và có thể nhân đôi traffic.

### 11.4. Mẫu cập nhật incident ngắn gọn

~~~text
09:02 UTC | Detection: orders.create lỗi 503 tăng ở region A.
09:05 UTC | Scope: 8% requests, không thấy leak/duplicate trong mẫu.
09:08 UTC | Suspected cause: inventory response timeout, retry fan-out.
09:12 UTC | Mitigation: cap outbound concurrency + giảm retries.
09:18 UTC | Result: p95 2.4s -> 0.9s; 503 giảm, queue đang drain.
09:25 UTC | Verification: synthetic order + idempotent replay OK.
Next: tiếp tục theo dõi backlog; root cause/provider timeline chờ xác minh.
~~~

Giờ, tỷ lệ và số đo ở đây **hoàn toàn minh họa**, không phải sự cố thật. Cập nhật nên nêu **đã xác minh / chưa xác minh**, hành động tiếp theo và tình trạng rollback; không khẳng định nguyên nhân gốc khi mới chỉ có tương quan. Không đưa raw request/response có PII hoặc credentials vào bản tin.

## 12. Game day và kiểm thử runbook trước khi gặp sự cố

Runbook được xem là hữu ích khi người trực có thể **thực hiện an toàn trong sandbox/staging** và hệ thống thực sự phản ứng như tài liệu mô tả. Không kiểm thử bằng cách cố làm hỏng production hoặc rút certificate thật khi không có change approval và khả năng rollback.

### 12.1. Ma trận diễn tập bắt buộc

| Ca | Fault injection hoặc điều kiện | Kỳ vọng cần xác minh |
|---|---|---|
| G01 | Tăng traffic GET/search đến giới hạn ứng dụng | `429` theo caller hoặc `503` do capacity, Retry-After đúng; checkout không bị đói |
| G02 | DB pool gần full, thêm pods | Không tạo connection storm; on-call nhận ra DB bottleneck |
| G03 | Thread pool bão hòa vì downstream chậm | Bulkhead/deadline từ chối sớm, không queue vô hạn |
| G04 | Retry multiplier tại gateway + app | Số outbound attempts bounded, error rate giảm khi giảm retry |
| G05 | Cert public hết hạn trên ingress thử nghiệm | External TLS verify thất bại; runbook định đúng chặng |
| G06 | Cert mới được lưu nhưng ingress chưa reload | Monitoring nhận biết **served serial** còn cũ |
| G07 | Outbound CA/chain/SAN sai | Java handshake fail; không bỏ verify để thành công giả |
| G08 | Clock node bị lệch trong lab | Chẩn đoán `Not Before/Not After` đúng, tránh xoay cert sai |
| G09 | Dependency trả 503 trong 5 phút | Breaker mở theo policy; API không treo hết worker |
| G10 | Dependency trả 404 hợp lệ | Không coi là lỗi transient hay mở breaker vô cớ |
| G11 | Provider nhận charge rồi mất response | Không charge hai lần; provider key ổn định, reconciliation |
| G12 | Worker restart giữa job PENDING | Operation/outbox recover, không phát event/side effect trùng |
| G13 | Dependency vừa phục hồi, backlog lớn | Ramp-up bounded, không tạo retry storm mới |
| G14 | User B GET order của tenant A khi cache nóng | Vẫn 403/404 theo policy; không lộ private representation |
| G15 | Certificate rotation trong lúc kết nối cũ còn sống | Request mới dùng cert mới, không ngắt kết nối hàng loạt ngoài SLO |
| G16 | Rollback app giữa outbox processing | Không mất job, không nhân đôi side effect, schema tương thích |

### 12.2. Spring MVC unit/integration test: quá tải phải ra 503

Giả sử service đã dùng `OperationOverloadedException` và `OverloadErrorAdvice` ở Mục 4:

~~~java
@WebMvcTest(ReportController.class)
@Import({OverloadErrorAdvice.class, ApiSecurityConfig.class})
class OverloadContractTest {
    @Autowired MockMvc mvc;
    @MockitoBean ReportQueryService reports;
    @MockitoBean JwtDecoder jwtDecoder; // Nếu security config cần

    @Test
    void overloadedReportReturns503WithoutLeakingDetails()
            throws Exception {
        when(reports.query(any(), any()))
            .thenThrow(new OperationOverloadedException());

        mvc.perform(get("/v1/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isServiceUnavailable())
            .andExpect(header().string("Retry-After", "3"))
            .andExpect(jsonPath("$.code").value("SERVICE_OVERLOADED"))
            .andExpect(content().string(not(
                containsString("secret"))));
    }

    @Test
    void anonymousRequestDoesNotBypassSecurityUnderLoad()
            throws Exception {
        mvc.perform(get("/v1/reports"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(reports);
    }
}
~~~

`ReportController`, `ApiSecurityConfig`, route và test fixture là **thành phần minh họa** cần phù hợp ứng dụng thật; thêm imports JUnit, Mockito, Spring MVC/Security Test, Hamcrest. `jwt()` giả lập principal, **không kiểm tra signature/issuer/audience thật**. Test này xác nhận 503/error schema khi service từ chối và 401 vẫn được giữ; nó không chứng minh semaphore có hiệu lực dưới 100 requests đồng thời. Bổ sung integration test trực tiếp service với barrier hoặc load test để kiểm số tasks đang chạy.

### 12.3. Kiểm TLS từ client Java phải dùng endpoint thật có TLS trong lab

Tạo một test server riêng có certificate hết hạn/hostname mismatch/self-signed CA **chỉ trong môi trường test**, cho Java HTTP client kết nối qua TLS, assert handshake thất bại với truststore production-like. Sau đó đổi sang cert hợp lệ trong trust chain và đúng SAN, assert handshake thành công. **Không** coi một unit test mock ném `SSLHandshakeException` là kiểm chứng thực sự cơ chế xác minh TLS.

Trong Kubernetes staging có cert-manager, diễn tập rotation bằng CA thử nghiệm và luồng issuer đã được phê duyệt, kiểm Secret/Ingress được cập nhật và **external served certificate** đổi. Không sao chép private key production vào fixture. Dùng synthetic TLS probes từ những region/trust environments khác nhau nếu khách hàng dùng nhiều platforms/JDK versions.

### 12.4. Mock downstream để kiểm timeout và circuit state

Trong integration test, dùng một HTTP stub server hoặc network fault proxy để:

1. Trả `503`/`429` với độ trễ và `Retry-After` khác nhau; kiểm client **không retry vô hạn**, breaker hoạt động đúng error classification.
2. Làm connect timeout/read timeout/DNS fail hoặc TLS handshake fail; kiểm mã lỗi public an toàn và không log token.
3. Trả `404` nghiệp vụ; kiểm không được tính là lỗi breaker nếu policy loại trừ.
4. Chuyển từ lỗi sang thành công; kiểm half-open chỉ cho **số probe giới hạn** và chuyển CLOSED ổn định.
5. Với POST, cho provider **ghi side effect rồi cắt response**, client retry cùng key, assert **số charge thực bằng một**, không chỉ verify số HTTP calls.

**Đặt barrier sau commit trước khi drop response**, không dùng `Thread.sleep` rồi mặc định tác dụng đã xảy ra. Nếu test cần network fault, `MockMvc` không tạo TCP socket; dùng Spring Boot random-port server và proxy fault injection. Luôn có timeout/cleanup của proxy/test containers và đo concurrency; đừng để chaos test treo CI.

### 12.5. Quan sát runbook bằng metrics và alert

| Metric/alert | Vì sao cần |
|---|---|
| `http.server.requests` theo method, route template, status class | Phát hiện lỗi người dùng, không nhân cardinality theo order ID |
| `jvm.threads.*`, `hikaricp.connections.*`, queue depth/age | Tìm nút nghẽn và backpressure |
| Outbound dependency latency/error/timeout category | Phân biệt connect/read/TLS/quota/provider 5xx |
| Circuit state/open/half-open và bulkhead rejections | Biết hệ thống đang degraded mode |
| TLS certificate expiry (served cert), renewal errors | Cảnh báo trước expiry và sau reload |
| Idempotency replay/mismatch, duplicate business intent | Kiểm an toàn retry/checkout |
| Backlog age/reconciliation pending, DLQ count | Theo dõi phục hồi sau outage |
| Trace exporter/collector health, dropped spans | Biết thiếu bằng chứng; không suy rate từ sampled traces |

Không đưa raw `orderId`, `userId`, token, URL chứa query, certificate private key hoặc SQL bind values vào metric labels. Trace được lấy mẫu có thể mất đúng request lỗi; **SLO error counts phải đến từ metrics không lấy mẫu**. Alert cần có severity, owner, link runbook, điều kiện triage và một đường rollback/đưa về trạng thái an toàn.

## 13. Bài tập trực sự cố và checklist production

### 13.1. Bài tập tổng hợp

**Giả định:** 10:00 UTC, API `POST /v1/orders` có p99 từ 400 ms lên 7 giây. Dashboard cho thấy outbound `payment` timeout tăng, Tomcat busy threads đạt 98%, một phần pod bị NotReady. Một nhân viên phát hiện certificate leaf của `api.example.com` còn hạn 50 ngày nhưng `payment.example.net` được phục vụ bởi cert vừa hết hạn. Client mobile retry POST ba lần với **idempotency key khác nhau**.

Hãy đề xuất:

1. Nguyên nhân khả dĩ, việc kiểm chứng riêng chặng TLS và tác động đến quá tải.
2. Ba hành động giảm tác động **có thể đảo ngược** theo thứ tự ưu tiên và những việc tuyệt đối không làm.
3. HTTP contract trả về cho request mới khi payment chưa thể xử lý, và xử lý các order đã ở trạng thái uncertain.
4. Cách chứng minh phục hồi bằng synthetic test/metrics, tránh duplicate payment và lỗi security.
5. Hành động phòng ngừa sau sự cố, gồm certificate alert và retry policy.

### 13.2. Lời giải tham khảo

**Chẩn đoán:** cert public của orders còn hạn **không loại trừ lỗi outbound TLS**. Xác minh `payment.example.net` với đúng SNI/trust chain, kiểm logs handshake category không chứa credentials và metrics connection/read timeout. Thread pool đầy có thể là **hậu quả của retry/outbound blocking** chứ không chỉ là thiếu pods. Kiểm Pod readiness logic, Hikari pool và số attempts outbound trước khi scale.

**Giảm tác động:** (1) giảm retry/giới hạn concurrency outbound và tách backlog, (2) mở circuit breaker theo policy cho payment, trả pending/503 thay vì giữ servlet threads vô hạn, (3) phối hợp provider/PKI thay certificate đúng peer và kiểm truststore, rollout/reload có kiểm chứng. Không bật trust-all TLS, không bỏ auth, không chuyển payment timeout thành `PAID`, không xóa operations/outbox hoặc scale mù làm nhiều outbound connections hơn.

**Hợp đồng:** với API đã hỗ trợ durable operation, `202 Accepted` cùng `Location: /v1/operations/{id}` là phù hợp **chỉ sau khi operation/outbox commit**. Nếu không thể tiếp nhận/ghi job thì trả `503` trung tính và `Retry-After` khi có căn cứ. Với những request đã tới provider trước timeout, cần **reconcile qua stable payment attempt/provider key**. Nếu mobile tạo key khác cho cùng intent, request-level idempotency không đủ: thêm business uniqueness/checkout state guard và kiểm audit các lần charge.

**Xác minh:** handshake từ JVM và probe ngoài đều đúng SAN/chain/date, circuit half-open→closed, p99/5xx/pool giảm, backlog drain trong budget; sandbox payment chỉ charge **một lần cho một logical intent**; user ngoài tenant vẫn 404/403. Thực hiện synthetic checkout có idempotency replay, không chỉ GET health.

**Phòng ngừa:** alert certificate từ cả public ingress **và outbound/mTLS**, tự động renewal có diễn tập, timeouts/budget/resilience4j review, upstream retry owner, quota theo route, operation ledger/provider idempotency, readiness không gây restart loop, runbook và game-day rehearsal.

### 13.3. Checklist cuối cùng

- [ ] Runbook có owner, trigger, severity, scope, quyền thực hiện, **stop/rollback condition** và đường truyền thông.
- [ ] Bước đầu có cách xác nhận môi trường/context, dashboard error/latency/saturation và dependency trace, không rò PII.
- [ ] Quá tải: phân biệt CPU/DB/downstream/ingress; có 429/503 hợp đồng, admission/bulkhead, retry budget và capacity plan.
- [ ] Không scale API mù khi database/downstream là nút nghẽn; có kiểm HPA, readiness và queue.
- [ ] TLS: phân biệt inbound/outbound/mTLS, kiểm served cert/chain/SAN/issuer/time/clock/SNI; không trust-all.
- [ ] Rotation: certificate/secret đúng endpoint, cơ chế reload được test, probe từ bên ngoài, rollback chỉ dùng cert còn hợp lệ/chưa lộ.
- [ ] Downstream outage: DNS/connect/handshake/read timeout/429/5xx được phân loại; fallback có freshness/permission policy.
- [ ] Payment/POST retry có idempotency + ledger/outbox/provider key; timeout **không** đồng nghĩa rollback.
- [ ] `202` chỉ trả sau durable acceptance; `503/504` phản ánh không phục vụ/timeout và body RFC 9457 trung tính.
- [ ] Có timeout budget toàn request, circuit breaker/bulkhead/queue caps, jitter và hạn mức retry.
- [ ] Sau phục hồi đo lại p95/p99, business outcomes, circuit, backlog và lỗi auth/tenant, không chỉ health endpoint.
- [ ] Có game-day tests overload, cert expired, TLS handshake, downstream timeout, lost response after commit và rollback.
- [ ] Log/metrics/traces không mang credentials, private key, raw body/PII; người trực có quyền truy cập theo vai trò.
- [ ] Sau incident có timeline/impact, nguyên nhân đã xác minh, corrective actions có owner và cập nhật tài liệu.

**Tài liệu tham khảo:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585), [Spring Boot — Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/index.html), [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html), [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/), [cert-manager — Certificate Resources](https://cert-manager.io/docs/usage/certificate/), [Resilience4j](https://resilience4j.readme.io/), [OpenTelemetry — Observability](https://opentelemetry.io/docs/).

**Kết luận:** runbook tốt không chỉ giúp REST API phục vụ lại nhanh mà còn bảo toàn **HTTP semantics, TLS trust, phân quyền, idempotency và tính nhất quán nghiệp vụ**. Với quá tải hãy giảm áp lực có ưu tiên; với chứng chỉ hãy xác định đúng chặng và xoay an toàn; với downstream gián đoạn hãy giữ timeout/retry trong ngân sách và reconcile side effects. Luôn kết thúc bằng kiểm chứng từ góc nhìn người dùng, rollback có điều kiện và diễn tập định kỳ.
