# 502, 503, 504 và lỗi ở gateway, ứng dụng hoặc phụ thuộc

Một client gọi `POST /api/v1/orders`, chờ bốn giây rồi nhận `504 Gateway Timeout`. Lệnh ghi đơn có bị rollback không? Không thể kết luận chỉ từ mã 504: gateway có thể ngừng chờ trong khi Spring Boot vẫn xử lý và database **đã commit**. Ở lần khác, cùng endpoint nhận `502 Bad Gateway` vì reverse proxy không kết nối được upstream hoặc nhận phản hồi HTTP không hợp lệ. Còn `503 Service Unavailable` có thể do gateway không có backend sẵn sàng, do chính API chủ động từ chối tải, hoặc do một service phụ thuộc đang bảo trì.

Trong mô-đun **INTEGRATION_API_REST**, hợp đồng HTTP quy định resource, URI, phương thức, mã trạng thái, xử lý lỗi, cache, idempotency và kiểm thử. Chương **Chẩn đoán sự cố** sử dụng hợp đồng ấy để trả lời ba câu hỏi thực tế: **Ai phát ra status? Lỗi gốc nằm ở hop nào? Việc ghi dữ liệu đã hoàn tất đến đâu?** Bài này tập trung vào chuỗi client → Nginx/Ingress/API Gateway → Java/Spring Boot → database/HTTP dependency/message broker, với ví dụ cấu hình, log, trace, runbook và test.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích chính xác ý nghĩa `502`, `503` và `504` theo ngữ nghĩa HTTP, phân biệt chúng với `500`, `429`, `408` và lỗi mất kết nối.
2. Xác định **tầng tạo response** dựa trên gateway access log, upstream status/timings, ứng dụng Spring, trace và health/endpoint state.
3. Chẩn đoán lỗi DNS/upstream address, TLS, connection refused, no healthy endpoints, read timeout, pool saturation, deadlock và dependency outage.
4. Thiết kế ngân sách timeout xuyên chuỗi gọi; hiểu tại sao timeout không đồng nghĩa transaction rollback và tại sao retry `POST` có thể gây tác dụng phụ trùng.
5. Chọn cấu hình timeout, readiness, overload response, retry/circuit breaker phù hợp mà không biến một lỗi tạm thời thành retry storm.
6. Viết test với MockMvc, WireMock/Testcontainers và E2E qua gateway, chứng minh cả **response HTTP** lẫn **trạng thái nghiệp vụ sau lỗi**.

**Nguyên tắc điều tra:** *nơi xuất hiện 502/503/504 không nhất thiết là nơi gây ra lỗi gốc*. Gateway có thể trả 504 vì một SQL query ở database chạy quá lâu, còn ứng dụng có thể trả 503 vì HTTP dependency trả 503 mà chính sách nghiệp vụ không cho fallback.

## 2. Hiểu đúng 502, 503 và 504

Theo ngữ nghĩa HTTP (RFC 9110), ba status thể hiện những tình huống khác nhau:

| Status | Ý nghĩa tổng quát | Chủ thể thường phát ra | Điều **không** thể suy ra |
| --- | --- | --- | --- |
| **502 Bad Gateway** | Server đóng vai gateway/proxy nhận phản hồi không hợp lệ từ upstream khi cố hoàn thành request | Reverse proxy, API gateway, ingress hoặc service đang đóng vai gateway | Không kết luận upstream đã rollback, không kết luận mọi 502 đều do JSON body sai |
| **503 Service Unavailable** | Server hiện không thể xử lý request, thường do quá tải hoặc bảo trì, có thể tạm thời | Gateway hoặc ứng dụng, đôi khi policy của load balancer | Không bảo đảm outage ngắn, không bảo đảm có retry an toàn |
| **504 Gateway Timeout** | Gateway/proxy không nhận được phản hồi kịp thời từ upstream cần thiết | Gateway, reverse proxy hoặc service đóng vai gateway | Không kết luận upstream chưa nhận request hoặc chưa commit |

**502** thường được ghi trong Nginx khi kết nối bị từ chối, upstream đóng kết nối quá sớm hoặc gửi header HTTP không hợp lệ; quy tắc và status cụ thể phụ thuộc loại sự cố/cấu hình proxy. **503** thường mô tả tình trạng không sẵn sàng hoặc quá tải; một gateway không có endpoint khỏe cũng có thể trả 503, nhưng trong vài triển khai lại có thể trả 502 hoặc lỗi khác. **504** thường xảy ra khi gateway đã cố gọi upstream nhưng hết thời gian chờ connect/read theo chính sách.

### 2.1. So sánh với những status dễ nhầm

| Status | Phân biệt khi triage |
| --- | --- |
| `500 Internal Server Error` | Lỗi nội bộ chung; có thể do Spring/DB/mapper. Nếu gateway chỉ chuyển tiếp 500, **không** nên gọi đó là lỗi 502 của gateway |
| `429 Too Many Requests` | Giới hạn lưu lượng/quota áp dụng cho client/tenant hoặc chính sách; khác overload chung của service |
| `408 Request Timeout` | Server không nhận được request hoàn chỉnh trong thời gian sẵn sàng chờ; không tương đương 504 chờ upstream response |
| `401 Unauthorized` / `403 Forbidden` | Lỗi xác thực/phân quyền; gateway auth có thể chặn trước ứng dụng, không phải lỗi hạ tầng |
| `404 Not Found` | Route/resource không tìm thấy hoặc chính sách che resource; không phải 502/503/504 |
| `499` trong Nginx log | **Không chuẩn HTTP**; Nginx thường dùng nội bộ để ghi client đóng kết nối trước khi server hoàn tất, không phải status gửi cho client |
| Network/TLS error, không có HTTP response | Client có thể thấy “connection reset”, “TLS handshake failure”, “DNS error”; đừng bịa status 502/504 khi chưa có response thực |

Phần thân lỗi cũng là manh mối: `502 text/html` có thể là trang lỗi mặc định của proxy, còn `503 application/problem+json` có thể do Spring `@RestControllerAdvice` phát. Tuy nhiên proxy có thể thay error page, status hoặc content type. Chỉ nhìn trang HTML/JSON **không chứng minh** nguồn lỗi; phải đối chiếu log/trace tại từng hop.

## 3. Bản đồ các hop và nơi phát sinh lỗi

Giả sử kiến trúc:

~~~mermaid
flowchart LR
    C["Client"] --> E["Edge / CDN"]
    E --> G["Ingress / API Gateway"]
    G --> A["Spring Boot Orders API"]
    A --> DB[("PostgreSQL")]
    A --> H["Shipping / Payment HTTP API"]
    A --> Q[("Broker / Outbox")]
    M["Logs · Metrics · Traces"] -.-> E
    M -.-> G
    M -.-> A
    M -.-> H
~~~

Một response `504` nhìn thấy ở client có thể do **edge chờ gateway**, **gateway chờ Spring**, hoặc **Spring như một gateway chờ shipping API và tự ánh xạ lỗi thành 504**. Cần phân biệt:

- **Response origin:** thành phần thật sự tạo status/body mà client nhận.
- **Failing hop:** kết nối/thao tác đầu tiên bị lỗi hoặc vượt timeout.
- **Root cause:** nguyên nhân khiến hop đó không đáp ứng, ví dụ SQL giữ lock, GC pause, connection pool đầy, DNS lỗi, rollout mất endpoints hay provider quá tải.
- **Business outcome:** transaction/resource có commit hay side effect ngoài hệ thống có xảy ra không.

Ví dụ có thể **response origin = Nginx**, **failing hop = Nginx → Spring read timeout**, **root cause = HikariCP pending do SQL bị lock**, còn **business outcome = chưa commit** hoặc **đã commit nhưng response quá muộn** tùy timeline.

### 3.1. Decision tree sơ bộ

~~~mermaid
flowchart TD
    A["Client nhận 502 / 503 / 504"] --> B{"Có HTTP response và status xác thực được?"}
    B -- "Không" --> C["Điều tra DNS / TLS / TCP / client timeout"]
    B -- "Có" --> D{"Gateway có upstream request tương ứng?"}
    D -- "Không" --> E["Route, local rejection, no healthy backend, cache/WAF"]
    D -- "Có" --> F{"Ứng dụng nhận request và ghi trace?"}
    F -- "Không" --> G["Connect/TLS/Service endpoints/proxy header timeout"]
    F -- "Có" --> H{"Ứng dụng tự trả 5xx?"}
    H -- "Có" --> I["Spring exception, DB/outbound client, overload policy"]
    H -- "Không" --> J["Gateway timeout/invalid response/client disconnect"]
    I --> K["Xác minh commit/side effects và retry"]
    J --> K
~~~

Đây là sơ đồ **điều tra**, không phải máy suy luận chính xác từ một status. Tracing sampling, log bị mất, gateway cache hoặc một request bị cắt kết nối có thể khiến “không thấy log” nhưng thực tế backend đã chạy. Hãy đối chiếu nhiều dấu hiệu, theo đúng request ID và timestamp.

## 4. Thu thập bằng chứng trước khi thay cấu hình

Tối thiểu cần có:

| Dữ liệu | Ví dụ | Mục đích |
| --- | --- | --- |
| Method, URL public, query đã lọc | `POST https://api.example.test/api/v1/orders` | Xác định đúng endpoint và route |
| Status/content type/body ngắn | `504 text/html` hoặc Problem Details | Phân biệt response từ các tầng |
| Thời điểm và thời lượng | UTC timestamp, 4.51 giây | So timeout budget giữa client/edge/gateway/app |
| Request/correlation ID | `X-Request-ID: diag-order-17` | Nối log giữa các hop |
| Version/instance/region | `orders-api v42, pod-3` | Tìm rollout/version skew/zone lỗi |
| Gateway `status/upstream_status` | `504 / -` hoặc nhiều giá trị | Biết gateway có chọn/gọi upstream và nhận gì |
| Timing từng hop | connect/header/response time | Xác định chậm ở connect hay sau khi kết nối |
| App spans/metrics | controller, DB, HTTP client, pool wait | Xác định điểm nghẽn |
| Trạng thái nghiệp vụ | Order ID, idempotency record, outbox | Kiểm tra commit/duplicate/partial effect |

Không ghi `Authorization`, session cookie, refresh token, API key hoặc body chứa PII vào ticket và log chẩn đoán. Nếu cần ID để đối chiếu, dùng dữ liệu test, masking hoặc quyền truy cập hạn chế; request ID không nên biến thành một metric label có cardinality cao.

### 4.1. Reproduce bằng curl, không phá TLS

~~~bash
curl --silent --show-error --include \
  --connect-timeout 2 \
  --max-time 8 \
  -H "Accept: application/json" \
  -H "X-Request-ID: diag-order-017" \
  -H "Authorization: Bearer <test-access-token>" \
  "https://api.example.test/api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"
~~~

`--connect-timeout` và `--max-time` là timeout của **lệnh curl**, không cấu hình server. Dùng token riêng môi trường test và không đưa secret thật vào shell history/CI output. Nếu cần xem TLS/connect timing, dùng `curl --write-out`:

~~~bash
curl --silent --output /dev/null \
  --write-out 'status=%{http_code} connect=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' \
  --max-time 8 \
  "https://api.example.test/actuator/health"
~~~

Lệnh trên chỉ là ví dụ đo kỹ thuật cho endpoint mà người kiểm thử **được phép truy cập**; health endpoint có thể không nằm ở public route. `time_starttransfer` gồm nhiều công đoạn đến byte đầu tiên và **không tự tách được** DB wait, outbound HTTP và gateway queue. Nếu curl hết hạn trước khi nhận HTTP response, `http_code` có thể là `000`; đó **không phải status 504**. Đừng dùng `-k/--insecure` để coi như “đã chữa” sự cố: nó bỏ kiểm tra chứng chỉ, có thể che lỗi TLS hoặc nguy cơ MITM.

Với `POST` có side effect, **không phát lại tùy tiện** chỉ để triage. Dùng dữ liệu thử riêng, `Idempotency-Key` theo hợp đồng hoặc một endpoint GET/health không thay đổi dữ liệu. Nếu buộc tái hiện thao tác ghi, phải có kế hoạch cleanup/reconciliation và không gọi hệ thống thanh toán thật ngoài chủ đích.

## 5. Nginx: đọc đúng $status, $upstream_status và thời gian

Một cấu hình access log chẩn đoán có thể ghi các biến có ý nghĩa:

~~~nginx
log_format gateway_diag
  'rid=$request_id '
  'method=$request_method host=$host uri="$uri" '
  'status=$status upstream_status="$upstream_status" '
  'request_time=$request_time '
  'upstream_connect_time="$upstream_connect_time" '
  'upstream_header_time="$upstream_header_time" '
  'upstream_response_time="$upstream_response_time" '
  'upstream_addr="$upstream_addr"';

access_log /var/log/nginx/api_access.log gateway_diag;
~~~

Đây là ví dụ trong môi trường kiểm soát. `$uri` có thể là URI đã normalize/rewrite, không phải mọi tình huống đều là path mà upstream nhận cuối cùng. `$request_uri` giữ URI gốc kèm query, có thể chứa thông tin nhạy cảm; nếu cần, phải che dữ liệu và giới hạn retention. Không log headers/auth body vô điều kiện.

Các biến cần hiểu:

- `$status`: status mà Nginx ghi cho request của client.
- `$upstream_status`: status liên quan đến upstream request, có thể có nhiều giá trị khi thử nhiều upstream; không phải lúc nào cũng có một status HTTP hợp lệ từ app.
- `$request_time`: tổng thời gian xử lý request ở Nginx theo ngữ nghĩa của module.
- `$upstream_connect_time`: thời gian thiết lập kết nối tới upstream, bao gồm handshake TLS khi áp dụng.
- `$upstream_header_time`: thời gian tới response header từ upstream.
- `$upstream_response_time`: thời gian nhận response từ upstream, có thể được ghi cho nhiều lần thử.

Các giá trị như `-` có thể xuất hiện khi không có upstream, chưa nhận đủ thông tin hoặc do trạng thái lỗi; **đừng tự suy ra “không có request tới app” chỉ bằng một dấu `-`**.

### 5.1. Ví dụ đọc log

~~~text
# Tình huống A: Gateway chờ app tới timeout; cần đối chiếu error log.
rid=diag-101 method=GET host=api.example.test uri="/api/v1/orders"
status=504 upstream_status="504" request_time=5.001
upstream_connect_time="0.002" upstream_header_time="-" upstream_response_time="5.000"

# Tình huống B: App chủ động trả 503, gateway chuyển tiếp.
rid=diag-102 method=GET host=api.example.test uri="/api/v1/orders"
status=503 upstream_status="503" request_time=0.025
upstream_connect_time="0.001" upstream_header_time="0.020" upstream_response_time="0.020"

# Tình huống C: Không kết nối được upstream; gateway trả 502.
rid=diag-103 method=GET host=api.example.test uri="/api/v1/orders"
status=502 upstream_status="502" request_time=0.003
upstream_connect_time="-" upstream_header_time="-" upstream_response_time="0.001"
~~~

Các dòng log là **tình huống minh họa**, không phải bộ giá trị bắt buộc của mọi phiên bản Nginx/ingress. Với A, cần tìm trong Nginx error log các thông điệp như `upstream timed out (...) while reading response header from upstream`. Với C, xem thông điệp `connect() failed (111: Connection refused) while connecting to upstream` hoặc dạng tương ứng trên OS; không được kết luận “ứng dụng không tồn tại” trước khi kiểm tra Service endpoints và TLS.

### 5.2. Các giai đoạn timeout của proxy

~~~nginx
location /api/ {
    proxy_pass http://orders_backend;

    proxy_connect_timeout 2s;
    proxy_send_timeout 10s;
    proxy_read_timeout 5s;
}
~~~

- `proxy_connect_timeout`: giới hạn thời gian thiết lập kết nối tới upstream, không thay cho DNS/TLS/client deadline tổng của toàn chuỗi.
- `proxy_send_timeout`: timeout giữa các lần ghi nối tiếp khi gửi request tới upstream; không phải tổng thời lượng upload.
- `proxy_read_timeout`: timeout **giữa các thao tác đọc liên tiếp** khi chờ/nhận response từ upstream; không phải deadline tổng bất biến cho một response streaming còn dữ liệu.

Do vậy một stream thỉnh thoảng gửi byte có thể tồn tại lâu hơn 5 giây với `proxy_read_timeout 5s`. Một request non-streaming không có header/body trong 5 giây có thể bị 504. Nếu có **edge/proxy nhiều lớp**, mỗi lớp còn có timeout riêng, không thể chỉ nhìn một cấu hình Nginx.

Đừng “chữa” 504 bằng cách tăng `proxy_read_timeout` từ 5 giây lên 5 phút ngay lập tức. Có thể làm số connection đang chờ tăng, khiến pool bão hòa và kéo dài trải nghiệm lỗi. Cần biết deadline sản phẩm, latency p95/p99, khả năng ứng dụng trả response và nguyên nhân thực như DB lock hoặc dependency chậm.

### 5.3. Proxy retry có thể nhân đôi POST

Nginx có cơ chế thử upstream khác theo `proxy_next_upstream` và các giới hạn retries. Các trường hợp mặc định và điều kiện được retry tùy config/module/version; **đừng giả định gateway luôn retry 502/503/504 hoặc tuyệt đối không bao giờ retry POST**.

Một thay đổi cấu hình kiểu:

~~~nginx
# CHỈ MINH HỌA CHÍNH SÁCH; không sao chép mặc định cho API ghi.
proxy_next_upstream error timeout http_502 http_503 http_504;
proxy_next_upstream_tries 2;
~~~

cần được đánh giá cùng HTTP method, khả năng body đã được gửi, buffering và điều kiện Nginx có cho retry non-idempotent request hay không. Dù gateway không retry, **client SDK và service mesh** vẫn có thể retry. Phải kiểm tra tổng số lần gửi thực tế và giữ Idempotency-Key khi thao tác ghi.

## 6. Kubernetes Ingress, Service và tình trạng “không có upstream”

Ở Kubernetes, Gateway/Ingress thường gọi một Service, còn Service dẫn tới EndpointSlice/Pod IP. Khi xuất hiện 502/503/504, kiểm tra lần lượt:

1. Ingress rule/host/path có chọn đúng backend Service hay không.
2. Service `port`/`targetPort`, protocol HTTP/HTTPS và các EndpointSlice có đúng Pod/port không.
3. Pod có **Ready** không, container có đang restart, crash loop, bị OOMKilled hoặc không listen đúng port không.
4. Ingress controller có thấy endpoint mới sau rollout không; route/canary có trỏ nhầm version không.
5. NetworkPolicy, firewall, service mesh, TLS SNI và upstream scheme có chặn kết nối không.
6. Backend có thực nhận request (inbound trace/log) hay chỉ health check.

Các lệnh chẩn đoán, chạy trong môi trường được ủy quyền:

~~~bash
kubectl -n api get ingress
kubectl -n api describe ingress orders-api
kubectl -n api get service orders-service
kubectl -n api get endpointslice -l kubernetes.io/service-name=orders-service
kubectl -n api get pods -l app=orders-api -o wide
kubectl -n api describe pod <pod-name>
kubectl -n api logs <pod-name> -c <container-name> --since=10m
~~~

`<pod-name>` và `<container-name>` là placeholders. Không có một status cố định cho “Service không có endpoints”: ingress-nginx, cloud load balancer, service mesh và từng cấu hình có thể trả `502`, `503` hay response khác. **Dùng log của đúng controller** để xác định.

### 6.1. Readiness, liveness và rolling deployment

Một triển khai Spring Boot có thể sử dụng Actuator health probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Ví dụ Kubernetes probe với endpoint phù hợp khi Actuator chạy cùng application port và context root:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Các giá trị và path **chỉ minh họa**. Nếu có `server.servlet.context-path` hay management port riêng, cần xác minh đường probe thực tế. Readiness dùng để loại Pod khỏi tập nhận request mới khi chưa sẵn sàng; liveness dùng khi process cần restart. **Không nên buộc DB/Redis lỗi ngắn hạn làm liveness fail ở mọi replica**, khiến Kubernetes restart hàng loạt và làm outage kéo dài. Khi scale-in, cần phối hợp readiness, preStop nếu dùng, graceful shutdown và `terminationGracePeriodSeconds`; phân phối endpoint không thay đổi tức thời.

Một Pod báo Ready nhưng vẫn trả 503 có thể do overload phía application, circuit breaker đang mở hoặc một dependency dùng chung bị lỗi. Ngược lại, thiếu endpoints không chứng minh code Spring lỗi: có thể chỉ là probe path sai, rollout đang tiến hành hoặc namespace selector chưa khớp.

### 6.2. Scheme HTTP/HTTPS sai và upstream TLS

Gateway kết nối `http://service:8080` trong khi backend chỉ chấp nhận TLS hoặc ngược lại có thể gây reset/invalid header, dẫn đến 502 tùy proxy. Khi proxy dùng HTTPS tới backend, kiểm tra CA trust, chứng chỉ, hostname/SNI, mutual TLS và policy của service mesh. Đừng tắt verify TLS để làm request “đi được”; đó là thay đổi bảo mật nguy hiểm và có thể che lỗi cấu hình.

## 7. Spring Boot: 503 do ứng dụng chủ động trả hay 5xx do exception?

Một `@RestControllerAdvice` có thể trả `503` khi dependency không sẵn sàng hoặc khi ứng dụng từ chối công việc vì bão hòa. Trong trường hợp đó gateway **chỉ chuyển tiếp** response; client nhìn 503 nhưng root cause có thể là DB, broker hoặc provider.

Ví dụ ánh xạ một exception đã được **phân loại** bởi application service:

~~~java
@RestControllerAdvice
public class DependencyErrors {

    @ExceptionHandler(UpstreamUnavailableException.class)
    public ResponseEntity<ProblemDetail> unavailable(
            UpstreamUnavailableException exception) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Dịch vụ tạm thời không sẵn sàng");
        problem.setDetail("Không thể hoàn tất yêu cầu lúc này.");
        problem.setProperty("code", "DEPENDENCY_UNAVAILABLE");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .header(HttpHeaders.RETRY_AFTER, "3")
            .contentType(MediaType.valueOf("application/problem+json"))
            .body(problem);
    }
}
~~~

`UpstreamUnavailableException` là exception nội bộ do ứng dụng định nghĩa; ví dụ chưa cung cấp class và policy mapping đầy đủ. `Retry-After: 3` chỉ hợp lệ nếu service có lý do đưa ra mốc thử lại phù hợp. Không tự động dán header này cho mọi lỗi. `ProblemDetail` theo RFC 9457 giúp API trả lỗi ổn định, nhưng không nên sao chép token, hostname nội bộ, SQL, stack trace hoặc raw body provider vào response công khai.

### 7.1. Nên map lỗi dependency thành 502, 503 hay 504?

Không có quy tắc “provider trả 503 thì API bắt buộc trả 503”. Tùy vai trò API:

| Tình huống | Chiến lược có thể hợp lý | Ghi chú |
| --- | --- | --- |
| API đang làm gateway tới upstream, nhận phản hồi sai protocol | `502 Bad Gateway` | Giữ error code public ổn định, không lộ chi tiết upstream |
| API đang làm gateway, hết hạn chờ upstream | `504 Gateway Timeout` | Chỉ dùng khi phù hợp vai trò/ngữ nghĩa; client vẫn cần idempotency |
| API không thể thực hiện nghiệp vụ do dependency thiết yếu tạm unavailable | `503 Service Unavailable` | Thể hiện chính service hiện không phục vụ được |
| Lỗi domain như “không đủ hàng” | `409 Conflict` theo hợp đồng | Không nhầm với outage hạ tầng |
| Payload client không hợp lệ | `400` hoặc `422` theo hợp đồng | Không đổi thành 502/503 khi đã xác định input lỗi |
| Lỗi cấu hình/bug không dự kiến | `500 Internal Server Error` | Alert và sửa root cause, tránh che thành 503 |

Mục tiêu là định nghĩa **taxonomy lỗi** và ánh xạ HTTP nhất quán trong OpenAPI/Problem Details. Cần giữ sự khác biệt giữa lỗi client có thể sửa, lỗi trạng thái resource và lỗi service tạm không sẵn sàng. Nếu API không thật sự là gateway, một timeout gọi dependency có thể được ánh xạ thành 503 phù hợp hơn 504; điều quan trọng là hợp đồng rõ ràng và có bằng chứng.

### 7.2. Thread starvation, DB pool, GC và slow dependency

Spring Boot có thể chậm trước khi trả response vì:

- Tomcat worker threads bận chờ JDBC/HTTP client, không còn slot cho request mới;
- HikariCP `active=max`, `pending>0`, connection acquire timeout vì query chậm/transaction dài;
- SQL lock, deadlock, missing index hoặc transaction giữ connection khi gọi external API;
- HTTP client connection pool exhausted, DNS/TLS/connect/read timeout;
- executor queue bị đầy, task bị block hoặc reject;
- stop-the-world GC pause, CPU throttling, memory pressure/OOM;
- WebFlux event loop bị block bởi JDBC hay đoạn code đồng bộ.

Một 504 ở gateway có thể xuất hiện **trước khi** app ghi exception vì app vẫn xử lý. Vì thế cần đối chiếu tổng latency và các metric saturation, không chỉ đọc stack trace.

| Metric | Tín hiệu | Điều tra tiếp |
| --- | --- | --- |
| `http.server.requests` p95/p99 và 5xx | API đang chậm/lỗi từ góc nhìn Spring | App có nhận request không, status cuối có bị gateway thay không? |
| Tomcat busy/current/max threads | Request worker bão hòa | Thread dump, chờ DB/HTTP client, GC |
| Hikari active/max/pending/acquire | DB connection pool pressure | Slow SQL, lock, transaction, leak |
| HTTP client latency/connection pending | Phụ thuộc HTTP chậm | Provider logs, timeout, retry, DNS/TLS |
| Executor active/queued/rejected | Hàng chờ tác vụ quá tải | Policy overload, job age, worker throughput |
| JVM GC pauses, allocation, CPU | JVM bị dừng hoặc thiếu tài nguyên | JFR, heap, limits, CPU throttling |
| Broker lag/outbox oldest age | Công việc async chưa hoàn tất | Consumer/backlog/retry/DLQ, không kết luận từ status 202 |

Không “tăng Tomcat maxThreads” khi HikariCP đang đợi connection: điều đó có thể chỉ làm nhiều thread hơn cùng chờ DB, làm hệ thống tệ hơn.

## 8. Ngân sách timeout từ client đến phụ thuộc

Giả sử:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Orders API
    participant D as PostgreSQL
    participant S as Shipping provider
    C->>G: POST /orders
    G->>A: Forward
    A->>D: Transaction / query
    D-->>A: Result
    A->>S: GET /quote
    Note over A,S: Outbound read timeout/retry
    S-->>A: 503 hoặc response trễ
    Note over C,G: Client/gateway có deadline riêng
    A-->>G: 201 / Problem Details nếu còn thời gian
    G-->>C: Response nếu client vẫn chờ
~~~

**Deadline** là thời điểm kết thúc tối đa cho cả use case; các **timeout theo hop** giới hạn từng giai đoạn connect/read/acquire. Nếu mỗi hop tự chờ 10 giây và có hai lần retry, tổng thời gian có thể vượt client timeout từ lâu.

Ví dụ ngân sách minh họa:

| Lớp | Giới hạn đề xuất trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Client | 5 giây tổng | Người dùng không chờ vô hạn; có thể timeout dù server đã commit |
| Gateway overall budget | Khoảng 4,5 giây | Có biên trước khi client bỏ cuộc |
| Application use-case deadline | Khoảng 4 giây | Dành thời gian để ánh xạ lỗi và trả response |
| Outbound dependency | 1 giây cho một attempt, tối đa hai attempt | Retry + backoff phải nằm trong deadline còn lại |
| DB acquire/query | Nhỏ hơn budget còn lại | Không chiếm trọn request; kiểm tra DB cancellation thực tế |

Các con số **không phải cấu hình chuẩn**, cần đo SLO, p99, tải, network và số hop để chọn. Gateway có thể chỉ hỗ trợ idle/read timeout chứ không có tổng deadline đúng như bảng; phải phân biệt hai khái niệm trong cấu hình thực tế. Một hệ thống không dùng retry có thể dành ngân sách khác.

### 8.1. Vì sao tăng timeout không chắc sửa được 504?

Nếu truy vấn DB giữ lock 30 giây, tăng gateway read timeout 5→60 giây có thể khiến mỗi request giữ thêm một worker/connection lâu hơn. Với tải liên tục, queue và số connection đang chờ có thể phình ra. Nếu một service phụ thuộc đã chết, chỉ chờ lâu hơn sẽ kéo dài lỗi.

Thứ tự xử lý nên là: **đo nguyên nhân**, giới hạn concurrency/queue, tối ưu query hoặc chữa dependency, đặt timeout ở đúng hop, rồi điều chỉnh deadline theo hành vi thực. Mọi retry phải có max attempts và budget, tránh nhân tải lên upstream.

### 8.2. Timeout không hủy tác dụng phụ đã hoàn tất

Tình huống nghiêm trọng nhất của API ghi:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Replica A
    participant D as Database
    C->>G: POST /orders + Idempotency-Key: req-77
    G->>A: Forward
    A->>D: INSERT order + idempotency record
    D-->>A: COMMIT OK
    Note over G,A: Gateway đã hết thời gian chờ
    G-->>C: 504 Gateway Timeout
    A--xG: 201 đến sau, không còn người nhận
    C->>G: Retry POST cùng key/payload
    G->>A: Forward tới một replica bất kỳ
    A->>D: Đọc kết quả đã commit theo key
    D-->>A: Order cũ
    A-->>C: Kết quả tương ứng, không tạo đơn thứ hai
~~~

Nếu client dùng **key khác** khi retry, có thể tạo đơn thứ hai. Nếu gateway tự retry `POST` mà backend không idempotent, cũng có thể nhân đôi. Ngược lại, `502` do connection reset sau khi provider đã thu tiền không chứng minh payment chưa xảy ra. Với những side effect như charge, cần khóa idempotency/reconciliation theo hợp đồng provider, không chỉ theo transaction local.

### 8.3. Hợp đồng retry và Retry-After

Chỉ retry khi:

1. Lỗi thuộc nhóm có khả năng tạm thời theo contract và có ích khi gửi lại.
2. Thao tác an toàn hoặc có idempotency được bảo đảm từ nguồn xử lý side effect.
3. Còn overall deadline, số lần thử và retry budget.
4. Có backoff/jitter phù hợp; xử lý `Retry-After` khi được cung cấp, không tạo retry storm.
5. Trạng thái giao dịch sau timeout không bị giả định là rollback.

`Retry-After` có thể là số giây hoặc HTTP-date; không phải lời hứa rằng request thử lại chắc chắn thành công. `429` thường gắn với quota, `503` có thể gắn với overload/bảo trì, còn `502`/`504` không tự đi kèm thời gian thử lại đúng đắn.

## 9. Instrumentation: metric, trace và log phải nối cùng request

### 9.1. Correlation ID và trace context

Sử dụng một `request ID` nhất quán qua gateway/app, đồng thời truyền trace context chuẩn (`traceparent` theo W3C Trace Context) giữa các hop khi các bên hỗ trợ. Gateway cần **xử lý header từ client ở trust boundary**: có thể cho phép ID hợp lệ hoặc cấp ID mới; không mù quáng tin giá trị bất kỳ vì log injection/cardinality. App đưa ID vào structured log và response/header theo policy.

Ví dụ timeline:

~~~text
12:00:00.000 ingress  rid=req-17  POST /api/v1/orders started
12:00:00.012 app      rid=req-17  controller entered  replica=v42-pod-3
12:00:00.045 app      rid=req-17  Hikari acquire wait started
12:00:04.501 ingress  rid=req-17  status=504 upstream_timeout
12:00:04.800 app      rid=req-17  transaction committed orderId=TEST-17
12:00:04.807 app      rid=req-17  attempt to write HTTP 201 failed/client gone
~~~

Đây là timeline **minh họa**, không dùng ID thật trong production log công khai. Nếu chỉ nhìn ingress, có thể cho rằng đơn không tạo; nếu chỉ nhìn app, có thể cho rằng client đã nhận `201`. Cần cả hai để biết business outcome. Đồng bộ clock/NTP và phân biệt timestamp thực với elapsed monotonic time; khi trace được sample, không có span không đồng nghĩa không có request.

### 9.2. Prometheus/Micrometer: nhìn đúng tầng

Với Spring Boot Actuator/Micrometer và Prometheus registry, nhóm chỉ số thường gặp (tên/exporter phụ thuộc phiên bản):

- `http.server.requests`: request count/duration/status/route template tại app; không bao gồm request bị gateway chặn trước.
- HTTP client metrics: outbound latency, status, connect/read errors, retries, pending connections.
- `hikaricp.connections.active/pending/acquire/timeout`: saturation DB pool; xác minh tên/thẻ thật trên `/actuator/metrics` hoặc `/actuator/prometheus`.
- JVM GC pause, CPU, memory, executor saturation.
- Gateway metrics riêng: status 502/503/504, upstream connection errors, timeout, no healthy backend, queue wait.

Ví dụ PromQL cho **HTTP 5xx mà chính Spring đã quan sát**:

~~~promql
sum(rate(http_server_requests_seconds_count{
  status=~"5.."
}[5m]))
~~~

Ví dụ phần trăm 5xx theo route ở app:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/v1/orders",status=~"5.."
}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count{
  uri="/api/v1/orders"
}[5m])), 1e-9)
~~~

Những query này **không** thấy 502/504 được tạo hoàn toàn tại gateway khi Spring chưa trả HTTP status. Cần dashboard ghép **gateway errors** và **application errors**, cùng request rate, latency, pending DB connections, container restarts, downstream p95, CPU và deployment markers. Không dựa vào một số liệu 5xx tổng mà không biết nó xuất hiện ở đâu.

## 10. Ba runbook ngắn theo status

### 10.1. 502 Bad Gateway

1. Xác nhận đó là HTTP `502` (không chỉ “network error” của client).
2. Xem gateway error/access log cùng request ID: `connect() failed`, `upstream prematurely closed connection`, `invalid header` hay TLS handshake?
3. Kiểm tra upstream scheme/host/port, Service EndpointSlice, readiness, Pod restart, process listen, TLS/mTLS.
4. Nếu upstream có nhận request, xem app có crash/OOM, đóng socket sớm, gửi header không hợp lệ hoặc bị connection pool/proxy ngắt không.
5. Kiểm tra status/response qua direct backend với **cùng principal/path** trong môi trường test; không bypass bảo mật để đưa ra kết luận.
6. Sau sửa, kiểm tra lại qua public gateway; thêm alert connect failure và smoke test nếu nguyên nhân do cấu hình rollout.

Không kết luận mọi 502 đều do “server chết”. Một app sống vẫn có thể đóng kết nối trước khi gửi header vì exception, timeout, shutdown hoặc một proxy trung gian khác.

### 10.2. 503 Service Unavailable

1. Đối chiếu `$status` và `$upstream_status`: app chủ động trả 503 hay gateway không route được?
2. Nếu gateway trả 503 trước app, xem số ready endpoints, rollout, ingress controller, circuit breaker/rate limit/gateway policy.
3. Nếu app trả 503, tìm Problem Details/error code nội bộ đã được lọc, saturation, dependency/broker/DB availability.
4. Kiểm tra `Retry-After`/overload policy có căn cứ, client retry có giới hạn và chỉ retry operation an toàn/idempotent.
5. Xử lý root cause: scale worker khi downstream còn headroom, khôi phục DB/provider hoặc rollback config; **không chỉ tăng thread/pool**.
6. Đo hồi phục qua error rate, latency, pending/queue age và tỷ lệ job hoàn tất sau khi 503 hết.

503 có thể **chủ động và đúng thiết kế** để bảo vệ hệ thống khi quá tải. Mục tiêu không phải xóa mọi 503 bằng cách nhận thêm request rồi để chúng timeout.

### 10.3. 504 Gateway Timeout

1. Xác minh gateway thực đã hết deadline nào: connect/read/idle hoặc timeout ở proxy phía trước.
2. Đối chiếu `request_time`, `upstream_connect_time`, `upstream_header_time`/response time và app trace.
3. Xác định thời gian chờ ở DB connection acquire, SQL lock, HTTP dependency, executor queue, GC hoặc response streaming.
4. Kiểm tra timeout budget xuyên client → gateway → app → dependency; tìm trường hợp outer deadline ngắn hơn app.
5. Với `POST` hoặc operation ghi, **tra cứu idempotency key và transaction/side effect trước khi retry**.
6. Sửa bottleneck/limit concurrency/retry budget, chỉ điều chỉnh timeout khi phù hợp với SLO; regression test gateway timeout và response-loss.

Đừng suy ra transaction rollback vì gateway đóng kết nối. Nếu job đã được nhận qua `202`, HTTP response timeout cũng không bảo đảm job chưa được enqueue.

## 11. Kiểm thử với Java/Spring, WireMock và gateway thật

### 11.1. Controller test cho error mapping

Ở tầng MVC slice, có thể xác minh exception của service trở thành Problem Details `503` mà không cần chạy database/proxy:

~~~java
@WebMvcTest(OrderController.class)
@Import(DependencyErrors.class)
class OrderUnavailableControllerTest {
    @Autowired MockMvc mvc;
    @MockitoBean OrderService orders;

    @Test
    void dependencyUnavailableMapsTo503() throws Exception {
        when(orders.preview(any()))
            .thenThrow(new UpstreamUnavailableException());

        mvc.perform(post("/api/v1/orders/preview")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.preview")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"skuId":"11111111-1111-4111-8111-111111111111",
                     "quantity":1}
                    """))
            .andExpect(status().isServiceUnavailable())
            .andExpect(header().string("Retry-After", "3"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.valueOf("application/problem+json")))
            .andExpect(jsonPath("$.code")
                .value("DEPENDENCY_UNAVAILABLE"));
    }
}
~~~

Đây là **khung test**: giả định `OrderController`, `OrderService.preview`, DTO, Spring Security rule và exception đã được tạo đúng; import được lược bớt. `@MockitoBean` dùng ở Spring Framework 6.2+/Boot 3.4+, project Boot cũ hơn có thể dùng `@MockBean`. `with(jwt())` mô phỏng principal, **không kiểm tra JWT signature/issuer/audience**. Controller test chứng minh HTTP contract, **không chứng minh** dependency outage hoặc ingress routing thật.

### 11.2. Integration test fault injection vào dependency

Dùng WireMock/MockWebServer làm **HTTP dependency** trả lần lượt:

| Mock response | Kiểm tra ở API | Cần quan sát thêm |
| --- | --- | --- |
| `200` JSON hợp lệ | API trả dữ liệu đúng | Chỉ một request bình thường |
| `429` + `Retry-After` | Respect budget/policy, không retry dồn | Số attempt và khoảng chờ |
| `503` trong vài lần rồi `200` | Retry GET có giới hạn nếu hợp đồng cho phép | Số lần gọi/overall deadline |
| `503` kéo dài | API kết thúc bằng lỗi ổn định, không vòng lặp vô hạn | Circuit breaker/rejection counters |
| Response delay vượt read timeout | Client HTTP ném lỗi timeout và app map có chủ đích | Thread/connection không bị giữ vô hạn |
| Connection reset sau khi gửi request | Không tự tin rằng POST upstream chưa thực hiện | Idempotency/reconciliation |
| Body/header HTTP hỏng | Phân loại protocol/contract error | Không để lộ raw upstream response |

Ví dụ WireMock:

~~~java
shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
    .willReturn(aResponse()
        .withStatus(503)
        .withHeader("Retry-After", "2")));

shipping.stubFor(get(urlPathEqualTo("/v1/slow-quotes"))
    .willReturn(aResponse()
        .withStatus(200)
        .withFixedDelay(2000)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"fee":25000,"currency":"VND"}
            """)));
~~~

Code giả định test có WireMock server `shipping` và Spring HTTP client cấu hình base URL đến mock. Phải test với timeout thật của `RestClient`/`WebClient`, không chỉ mock phương thức Java. Kết quả mỗi status phụ thuộc adapter/policy, không mặc định mọi upstream 503 phải đi thẳng ra public API như 503.

### 11.3. Test gateway timeout khác test timeout trong client

`MockMvc` chạy trong Spring context, **không đi qua socket/gateway**, nên không thể tự chứng minh Nginx phát 504. Test HTTP end-to-end cần:

1. Khởi động ứng dụng thật ở port test hoặc container; có một endpoint/dependency cố ý delay dưới quyền test.
2. Khởi động gateway với timeout **ngắn hơn** delay app và cấu hình route đúng.
3. Gọi qua public/staging gateway, xác minh gateway trả 504 hoặc status do proxy được cấu hình.
4. Đối chiếu upstream request log, request ID và trạng thái DB sau khi server tiếp tục.
5. Chạy lại với app hoàn thành sớm hơn gateway timeout để xác minh đường bình thường.
6. Kiểm tra client retry cùng Idempotency-Key **không tạo side effect thứ hai**.

Không dùng môi trường production để cố ý tạo 504 với nhiều request giữ lock/connection. Chọn workload nhỏ, giới hạn thời gian và cleanup, tách tài nguyên thử nghiệm. Mỗi proxy có status mapping khác nhau, test phải assert **hợp đồng của gateway đang triển khai**, không áp đặt giả định.

### 11.4. Kiểm thử readiness và deployment

Với môi trường Kubernetes cách ly, test các tình huống:

- Chưa có Ready Pod: gateway phản hồi ổn định theo policy, không treo vô hạn.
- App đang khởi động: readiness ngăn traffic mới cho tới khi sẵn sàng.
- Pod bị restart: backend endpoints cập nhật; request đang xử lý có chính sách retry phù hợp.
- Rollout N/N+1: cả hai version dùng cùng route/health contract, không tạo 5xx ngẫu nhiên.
- HikariCP pool nhỏ và SQL chậm giả lập: quan sát pending/timeout, phân biệt 503 do app với 504 do proxy.
- Dependency không sẵn sàng: API phải fail an toàn và đo được error code/circuit breaker.

Chỉ test chặn traffic/kill Pod trên cluster được cấp quyền; không thay đổi liveness/readiness của production để tạo lỗi.

## 12. Incident mẫu: 504 sau khi đơn đã được tạo

**Triệu chứng:** Client `POST /api/v1/orders` với `Idempotency-Key: "checkout-17"` nhận `504` sau ~4,5 giây. Người dùng bấm “Thử lại”, hệ thống xuất hiện hai đơn.

**Bằng chứng cần tìm:** Gateway có `request_time≈4.5` và `upstream_status=504`; application trace cho thấy DB transaction đầu commit lúc ~4,8 giây; request thứ hai mang key mới do UI mỗi lần bấm sinh key mới. Điều này minh họa rằng gateway response timeout **không rollback** lệnh ghi.

**Giả thuyết nguyên nhân:** App chậm vì chờ DB connection/SQL lock hoặc dependency; gateway deadline ngắn hơn xử lý; idempotency policy ở UI/API không giữ cùng key giữa retry một nghiệp vụ. Cần xác minh qua metric/trace thực, không kết luận chỉ từ timestamp.

**Khắc phục có nguyên tắc:** Đưa transaction/idempotency record vào store dùng chung có unique constraint, giữ cùng key cho một ý định tạo đơn, đọc/replay kết quả khi retry; xác định budget timeout có đủ biên và giảm bottleneck. Nếu có downstream payment, bảo đảm provider idempotency hoặc reconciliation. Bổ sung test “commit rồi response mất”, test concurrent duplicate và giao diện hiển thị trạng thái request chưa rõ kết quả thay vì cho bấm tạo mới không kiểm soát.

**Điều kiện xác minh:** Với cùng key/payload, dù request đi qua hai replica và lần đầu bị gateway timeout, hệ thống vẫn chỉ có một đơn/reservation; kết quả có thể truy vấn được và log không lộ thông tin nhạy cảm.

## 13. Bài tập thực hành

**Bài tập 1 — Phân biệt status.** Cho ba sự cố: (a) Nginx không kết nối được cổng Tomcat, (b) Spring chủ động trả Problem Details 503 vì dependency unavailable, (c) Nginx đợi response header quá thời gian. Dự đoán status có thể xuất hiện, rồi nêu **bằng chứng cần thu thập** để xác định nơi tạo response thay vì mặc định mọi lỗi có cùng status.

**Bài tập 2 — Đọc access log.** Gateway ghi `status=504, upstream_connect_time=0.002, upstream_header_time=-, upstream_response_time=5.000`; app log thấy request vào và Hikari pending tăng. Hãy lập timeline, ba giả thuyết nguyên nhân, metric/traces cần xem và lý do không nên chỉ nâng `proxy_read_timeout`.

**Bài tập 3 — Timeout budget.** Client timeout 6 giây, gateway read timeout 4 giây, API gọi hai dependency mỗi lần có 3 retries × 2 giây và backoff. Hãy chỉ ra vì sao budget bất khả thi; thiết kế overall deadline, per-attempt timeout, max attempts và timeout DB sao cho API có thể kết thúc có kiểm soát. Giải thích giới hạn của `proxy_read_timeout` đối với streaming.

**Bài tập 4 — 503 khi rollout.** Kubernetes Ingress lúc có 0 Ready Pod trả response lỗi. Kiểm tra readiness endpoint, Service selector/EndpointSlice, targetPort và rolling update. Đề xuất cách giảm downtime và phân biệt 503 do không có backend với 503 do ứng dụng đang bận.

**Bài tập 5 — Retry và double charge.** `POST /v1/charges` của provider đã thực hiện thu tiền nhưng kết nối reset. Client nhận 502 từ gateway. Thiết kế `Idempotency-Key` hoặc API reconciliation; thử hai lần gửi cùng key nhưng khác payload và giải thích vì sao không được mặc nhiên retry bằng key mới.

**Bài tập 6 — WireMock + Spring.** Dùng WireMock trả `429 Retry-After`, `503` và response delay 2 giây; cấu hình `RestClient`/`WebClient` với timeout và retry có giới hạn. Viết assertions cho số lần gọi, deadline, response public và không tạo order khi lấy quote thất bại trước transaction.

**Bài tập 7 — E2E và telemetry.** Chạy một API test sau gateway Nginx trong môi trường cô lập. Buộc app xử lý lâu hơn gateway deadline và cho nó commit một record. Kiểm tra gateway 504, app commit, replay same key không nhân đôi. Viết dashboard với gateway 502/503/504, app p95/5xx, Hikari pending, outbound timeout và Pod readiness.

**Bài tập 8 — Viết runbook.** Soạn runbook một trang cho incident “503 tăng sau deploy”, gồm triage, bằng chứng request ID/timing, phân biệt source của status, nguyên nhân từ store/dependency/ready endpoints, quyết định rollback, kiểm chứng phục hồi và giới hạn bảo mật khi thu log.

### Tiêu chí đánh giá

Lời giải đạt yêu cầu khi: (1) phân biệt HTTP status với root cause và business outcome; (2) truy được hop phát sinh lỗi bằng log/timing/trace; (3) cấu hình timeout theo budget có giới hạn; (4) không giả định timeout làm rollback transaction hay provider side effect; (5) retry tôn trọng idempotency; (6) có test tầng MVC, HTTP dependency và gateway thật; (7) xử lý sự cố mà không làm lộ secret, không tắt TLS/auth hoặc tạo tải nguy hiểm.

## 14. Checklist xử lý 502/503/504

- [ ] Xác minh client đã nhận HTTP status thật, không nhầm với lỗi DNS/TLS/TCP/curl timeout.
- [ ] Có method, public URL, timestamp, request ID/trace ID và version/instance liên quan.
- [ ] Đã phân biệt status do gateway tạo và status app trả qua `$status`/`$upstream_status` cộng log/trace.
- [ ] Đã xác định failing hop: gateway→app, app→DB, app→HTTP dependency hay worker/broker.
- [ ] Nginx connect/read/send timeout được hiểu đúng là timeout theo giai đoạn, không luôn là deadline tổng.
- [ ] Kubernetes Ingress/Service/EndpointSlice, readiness, port, TLS/mTLS và rolling state được kiểm tra.
- [ ] Spring thread/executor, Hikari pool, DB locks/slow SQL, outbound HTTP client và JVM/GC được đối chiếu khi cần.
- [ ] App error taxonomy/Problem Details không lộ token, internal host, stack trace hoặc raw provider body.
- [ ] HTTP `503` chủ động khi overload được thiết kế cùng bounded queue/retry policy; không nhận tải vượt sức chỉ để tránh 503.
- [ ] Với `POST`, đã xác minh commit và idempotency record trước khi retry; provider side effect có reconciliation nếu cần.
- [ ] Client/gateway/app/dependency timeout và retry budgets không tạo chuỗi xử lý dài hơn deadline sản phẩm.
- [ ] Test WireMock/MockMvc/E2E bao phủ 502/503/504 theo đúng nguồn, readiness và response-loss sau commit.
- [ ] Có dashboard, alert, rollback/runbook; điều tra không tắt TLS/auth hoặc gây lỗi trên hệ thống production.

**Kết luận:** `502`, `503` và `504` là những tín hiệu quan trọng nhưng **không phải bản chẩn đoán nguyên nhân**. Phải lần theo request qua từng hop để xác định ai tạo response, đang chờ kết nối hay phụ thuộc nào, và dữ liệu nghiệp vụ đã commit hay chưa. Khi kết hợp gateway log, Spring metrics/traces, timeout budget và idempotency, nhóm vận hành có thể khôi phục API mà không biến một lỗi hạ tầng ngắn thành sự cố dữ liệu hoặc retry storm.
