# WAF log và request ID

> **Chương:** Web application firewall  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Kết hợp log của Web Application Firewall (WAF) với request ID, reverse proxy, ứng dụng, danh tính, firewall, VPN, IDS/IPS, DNS và hệ thống giám sát để truy vết sự cố, phát hiện xâm nhập và xây dựng kiến trúc mạng an toàn.

## 1. WAF log và request ID giải quyết vấn đề gì?

**WAF log** là bản ghi về một yêu cầu HTTP/HTTPS được WAF quan sát hoặc xử lý, gồm ngữ cảnh request, chính sách khớp, hành động và các thuộc tính hữu ích cho vận hành. **Request ID** là mã định danh dùng để phân biệt hoặc truy vết một request trong một hệ thống hay qua nhiều thành phần, tùy cơ chế tạo và lan truyền ID.

Ví dụ người dùng nhận lỗi **403 Forbidden** khi gọi API, trong khi dashboard WAF hiển thị nhiều sự kiện Block. Chỉ dựa trên mã 403 và số lần Block, ta chưa biết đó có phải request của người dùng hay không; 403 cũng có thể do API gateway hoặc chính ứng dụng trả về. Nếu mỗi thành phần lưu request ID hoặc correlation ID nhất quán, đội vận hành có thể đối chiếu:

1. **Request nào?** Thời gian, host, path, method, nguồn kết nối và mã định danh.
2. **Bị xử lý ở đâu?** WAF đã chặn, reverse proxy gặp lỗi hay ứng dụng từ chối?
3. **Vì sao?** Rule ID nào khớp, hành động cuối cùng là gì và bằng chứng ở các log liên quan?

**Giới hạn quan trọng:** Không có một chuẩn duy nhất buộc mọi WAF, CDN, proxy và framework phải dùng cùng một tên trường hoặc cùng một request ID. Có nhiều định danh với mục đích khác nhau. Thiết kế tốt phải nêu rõ **ai tạo ID, ID tồn tại trong phạm vi nào, được truyền qua ranh giới nào và ánh xạ bằng trường nào**.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Nhận diện các trường quan trọng của WAF access/security event và giải thích cách đọc.
- Phân biệt **WAF event ID, request ID, correlation ID, trace ID, span ID, rule ID** và session/user ID.
- Thiết kế cách tạo và truyền ID an toàn qua CDN, WAF, load balancer, API gateway và ứng dụng.
- Phân tích **Allow/Block/Count/Challenge/Rate limit** cùng mã HTTP và log từ origin.
- Xác minh độ phủ logging, tránh ghi bí mật hoặc dữ liệu cá nhân vào SIEM.
- Thực hiện quy trình điều tra false positive, API abuse, origin bypass và lỗi tương quan log.

## 2. Một sự kiện WAF thường chứa những gì?

Các sản phẩm WAF có schema khác nhau. Bảng dưới mô tả **các trường thường hữu ích**, không phải trường bắt buộc ở mọi nhà cung cấp.

| Nhóm | Trường thường gặp | Dùng để trả lời |
|---|---|---|
| **Thời gian** | timestamp, event_time, timezone, ingest_time | Request xảy ra lúc nào, log đến SIEM lúc nào? |
| **Định danh** | request_id, event_id, trace_id, transaction_id | Ghép sự kiện nào với lần truy cập nào? |
| **Đường truy cập** | hostname, URI path, HTTP method, scheme, protocol version | Endpoint và giao thức nào bị tác động? |
| **Nguồn** | socket/peer IP, trusted client IP, proxy chain, geo/ASN nếu có | Client được xác định từ đâu và độ tin cậy ra sao? |
| **Tài nguyên** | WAF policy/web ACL ID, listener, route, edge region, origin pool | Chính sách nào và điểm thực thi nào xử lý? |
| **Kết quả WAF** | matched rule ID, managed group/version, rule action, final action, score, labels | Điều kiện nào khớp và quyết định sau cùng là gì? |
| **Kết quả HTTP** | edge response status, origin response status, upstream latency | 403/429/5xx do thành phần nào trả về? |
| **Ngữ cảnh** | content type, request size, header hoặc field đã được xử lý an toàn | Hành vi request có phù hợp API contract không? |
| **Vận hành** | logging pipeline, sampling flag, policy version, collection status | Log có đủ độ phủ, đúng phiên bản không? |

Một WAF có thể ghi **một bản ghi tổng cho request**, nhiều bản ghi cho từng rule khớp, hoặc event dành riêng cho challenge/bot. Vì thế **một dòng log chưa chắc tương đương một request**, và số dòng match không nên tự xem là số request đã bị chặn.

### 2.1. Request log và security event

**Access/request log** tập trung vào những lần truy cập và kết quả trả về. **Security event** tập trung vào tín hiệu bảo mật: matched rule, hành động, điểm bất thường, nhóm luật hoặc nhãn rủi ro. Một hệ thống có thể dùng cùng một bản ghi chứa cả hai, hoặc ghi chúng vào hai nguồn riêng.

Không nên thiết kế báo cáo “số request bị chặn” bằng cách đếm tất cả dòng của **security event**, bởi một request có thể tạo nhiều rule match và nhiều event. Nếu nền tảng có bản ghi **final disposition** theo từng request, hãy dùng nó để tính tần suất chặn thực sự.

## 3. Phân biệt các loại ID để tránh ghép nhầm

| Định danh | Đại diện cho | Ai thường tạo? | Có nên dùng thay thế ID khác? |
|---|---|---|---|
| **WAF event ID** | Một bản ghi/sự kiện WAF; đôi khi là ID giao dịch của engine | WAF hoặc hệ thống log | **Không** mặc định đồng nhất với request ID ứng dụng |
| **WAF request ID** | Request theo phạm vi và định nghĩa của WAF | Edge/WAF | Có thể dùng tra log WAF, nhưng chưa chắc được origin nhận |
| **Application request ID** | Request đi vào một instance hay ingress của ứng dụng | Proxy/API gateway/app | Không bảo đảm giống WAF ID nếu không thiết kế truyền ID |
| **Correlation ID** | Khóa dùng để ghép các bản ghi thuộc cùng giao dịch/luồng logic | Điểm vào được tin cậy hoặc hệ thống điều phối | Có thể liên kết nhiều request hoặc nhiều span, tùy quy ước |
| **Trace ID** | Một trace phân tán, thường gồm nhiều span | Hệ thống tracing/điểm khởi tạo trace | Không nhất thiết là một HTTP request duy nhất |
| **Span ID** | Một đơn vị công việc trong trace | Thành phần tracing | Một trace có thể có nhiều span ID |
| **Rule ID** | Một quy tắc phát hiện hoặc kiểm soát | Người vận hành/nhà cung cấp WAF | **Không** định danh request; nhiều request có thể khớp cùng rule |
| **Session/user/tenant ID** | Phiên, danh tính hoặc chủ thể nghiệp vụ | Hệ thống xác thực/ứng dụng | Không thay request ID và phải bảo vệ dữ liệu nhạy cảm |

Ví dụ, request với correlation ID **req-7f91a2c4** có thể tạo WAF event **evt-001** và **evt-002** nếu engine ghi từng match. Ứng dụng có thể tạo request ID nội bộ **app-8842** và trace ID riêng. Muốn ghép chính xác, phải **lưu ánh xạ** hoặc truyền một khóa chung qua các thành phần.

### 3.1. Một request có thể tạo nhiều ID

Số lượng request và ID không luôn có quan hệ 1–1:

- **CDN cache hit:** WAF/edge có thể xử lý request nhưng origin **không nhận request đó**.
- **WAF Block:** Không có upstream application log cho request bị chặn tại edge.
- **Client retry:** Một hành động của người dùng có thể tạo **nhiều HTTP request**; mỗi lần thử có request ID riêng.
- **Redirect:** Trình duyệt có thể gửi request tiếp theo tới URL mới, sinh các bản ghi độc lập.
- **Gateway fan-out:** Một request vào có thể tạo nhiều request gọi microservice, chung trace nhưng span/request ID khác nhau.
- **Queue/async:** Một request ban đầu kích hoạt job chạy sau, thời gian và ID riêng; cần liên kết qua trace context, message metadata hoặc business operation ID được thiết kế phù hợp.

**Không ép mọi thành phần phải sử dụng cùng một chuỗi ID cho mọi cấp độ.** Có thể giữ WAF request ID, app request ID và trace ID riêng, miễn ghi được khóa liên kết rõ ràng.

## 4. Hành trình request trong hệ thống nhiều lớp

Giả sử API chạy trong cloud, người dùng truy cập qua CDN/WAF, reverse proxy, API gateway rồi ứng dụng. Mô hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant W as CDN / WAF
    participant P as Reverse proxy
    participant G as API Gateway
    participant A as Application
    participant S as SIEM / Trace backend
    C->>W: HTTPS GET /v1/orders
    W->>W: Tạo WAF event ID và correlation ID
    W->>P: Forward request và trusted correlation ID
    P->>G: Forward correlation ID; có local request ID
    G->>A: Forward context; tạo span mới nếu tracing
    A-->>G: HTTP response
    G-->>P: Response
    P-->>W: Origin response
    W-->>C: HTTP response + request ID công khai nếu phù hợp
    W-->>S: WAF event
    P-->>S: Proxy access log
    G-->>S: Gateway log / trace
    A-->>S: Application log / trace
~~~

Trong mô hình này, **WAF event ID** phục vụ tra cứu sự kiện ở edge, còn **correlation ID** được truyền xuống các thành phần được tin cậy. Mỗi tầng có thể ghi thêm **local request ID**. Nếu WAF chặn request trước khi chuyển tiếp, chuỗi dừng ở WAF; việc không thấy log ở origin lúc đó có thể **hoàn toàn đúng theo thiết kế**.

### 4.1. Bảng tương quan minh họa

| Thành phần | ID cục bộ | Correlation ID | Kết quả |
|---|---|---|---|
| WAF | waf-ev-8841 | req-7f91a2c4 | ALLOW |
| Reverse proxy | proxy-req-220 | req-7f91a2c4 | 200 từ upstream |
| API gateway | gw-req-991 | req-7f91a2c4 | Route /v1/orders |
| Application | app-req-445 | req-7f91a2c4 | Đã trả response |

Đây là **tập dữ liệu minh họa**, không phải output của một hãng. Muốn điều tra, dùng correlation ID để xem chuỗi liên quan, sau đó đối chiếu local ID khi cần tra log chuyên biệt của từng thiết bị.

## 5. Tạo và truyền request ID an toàn

Request ID tốt nên **không chứa thông tin cá nhân, đủ khó đoán, ít nguy cơ trùng**, dễ truy vấn và được giữ nhất quán trong phạm vi đã công bố. UUID ngẫu nhiên hoặc một định danh ngẫu nhiên có entropy phù hợp là những cách thường dùng. Một ID chứa timestamp thuần hoặc số đếm tăng dần có thể dễ dự đoán và gây lộ nhịp hoạt động; mức chấp nhận tùy mục tiêu, nhưng **không dùng request ID làm bí mật hay token xác thực**.

### 5.1. Chọn điểm có thẩm quyền tạo ID

Một lựa chọn đơn giản:

1. **Điểm ingress tin cậy** (CDN/WAF hoặc API gateway) sinh correlation ID cho request khi chưa có một ID đã được xác minh theo hợp đồng tin cậy.
2. Proxy truyền ID qua một header nội bộ có tên thống nhất, ví dụ **X-Request-ID**; đây là quy ước phổ biến, **không phải header bắt buộc theo chuẩn HTTP**.
3. Ứng dụng ghi ID trong mọi bản ghi liên quan request, cùng timestamp, route và service name.
4. Response có thể trả về một request ID **không nhạy cảm** để người dùng cung cấp cho support.
5. Tại ranh giới với nhà cung cấp, đối tác hoặc dịch vụ không tin cậy, quy định rõ giữ, thay mới hay liên kết ID và bảo vệ header.

**Không tin X-Request-ID do client Internet tự cung cấp** để làm ID có thẩm quyền trong log nội bộ. Client có thể gửi cùng ID cho nhiều request, tạo chuỗi dài, chèn ký tự điều khiển hoặc cố giả dấu vết của phiên khác. Phải validate chiều dài/ký tự và **ghi đè bằng ID của ingress tin cậy**, hoặc lưu ID client trong trường riêng có nhãn **untrusted** nếu cần đối soát.

### 5.2. Ví dụ HTTP

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.com
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: req-7f91a2c4
~~~

Khối trên minh họa request/response cho mục đích học tập; response thực tế còn có header và body khác. ID ở response **không chứng minh request an toàn**, chỉ giúp hỗ trợ truy vết. Nếu môi trường đã có cơ chế tracing hoặc request ID chuẩn riêng của nền tảng, nên dùng và tài liệu hóa cơ chế đó thay vì tạo thêm ID trùng chức năng.

### 5.3. Tin cậy ở từng hop

| Vị trí | Rủi ro | Quyết định thiết kế |
|---|---|---|
| Client → WAF | Client tự gửi X-Request-ID hoặc trace header giả | Tạo/chuẩn hóa ID phía trusted ingress, giới hạn chiều dài và ký tự |
| CDN → WAF riêng | Có nhiều lớp proxy và nhiều tên header | Xác nhận nguồn proxy, cơ chế forward và điều kiện tin cậy |
| WAF → Proxy → App | Header bị ghi đè hoặc không truyền ở một hop | Định nghĩa contract và có test end-to-end |
| API gateway → Microservices | Fan-out, retry, span mới | Duy trì trace/correlation context, giữ local ID khác nhau |
| WAF/Proxy → SIEM | Log không đầy đủ hoặc thay đổi schema | Chuẩn hóa trường, thêm source và policy version |

Hãy **tách trusted client IP khỏi request ID**. Khi đi qua proxy, địa chỉ client có thể được mang trong **Forwarded** hoặc **X-Forwarded-For**, nhưng chỉ được tin chuỗi do proxy đã xác minh tạo/chuẩn hóa. IP sai khiến rate limit, phân tích tấn công và điều tra nhắm sai đối tượng.

## 6. W3C Trace Context và mối quan hệ với request ID

Trong hệ thống microservice, **W3C Trace Context** định nghĩa cách truyền thông tin trace qua HTTP. Một header thường gặp là **traceparent**, gồm phiên bản, trace ID, parent/span ID và trace flags. Ví dụ minh họa theo định dạng của chuẩn:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong phiên bản 00, trace ID có 16 byte thể hiện bằng 32 ký tự hex và parent ID có 8 byte thể hiện bằng 16 ký tự hex; các giá trị toàn 0 không hợp lệ. Trường trace flags có thể mang tín hiệu như **sampled**, nhưng **không phải quyết định bảo mật** hay bảo đảm mọi span được lưu.

**Trace ID có thể liên kết nhiều HTTP request và hoạt động nội bộ**, nên không nhất thiết thay request ID ở gateway/WAF. Có thể lưu cả:

~~~json
{
  "correlation_id": "req-7f91a2c4",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "service": "orders-api"
}
~~~

Header traceparent từ client ngoài Internet cũng là **dữ liệu đầu vào không tin cậy**. Thành phần ingress phải parse/validate và áp dụng chính sách về việc tiếp tục trace hay tạo trace mới; không dùng trace ID để cấp quyền, xác định danh tính hoặc tin client IP. WAF có thể không truyền trace context hoặc không ghi trace ID: nếu vậy cần tầng proxy/gateway tạo liên kết sau WAF và lưu ánh xạ theo yêu cầu vận hành.

## 7. Ví dụ log có thể truy vết từ WAF tới ứng dụng

Giả sử request hợp lệ đến API và được trả HTTP 200. Mỗi tầng ghi JSON đã chuẩn hóa. Những trường bên dưới là **schema minh họa**, tên field và action không đại diện cho một nhà cung cấp cụ thể.

### 7.1. Log WAF khi cho qua request

~~~json
{
  "event_time": "2026-11-28T05:40:12.120Z",
  "source": "edge-waf",
  "waf_event_id": "waf-ev-8841",
  "correlation_id": "req-7f91a2c4",
  "host": "api.example.com",
  "method": "GET",
  "path": "/v1/orders",
  "trusted_client_ip": "198.51.100.25",
  "web_acl_id": "api-prod-policy",
  "matched_rule_ids": [],
  "final_action": "ALLOW",
  "edge_status": 200,
  "origin_status": 200,
  "policy_version": "waf-policy-v12"
}
~~~

Địa chỉ **198.51.100.25** và các tên miền **example.com** là dữ liệu dành cho ví dụ. Một số WAF không biết origin status, hoặc không ghi allow event đầy đủ; phải xem schema và logging configuration thực tế.

### 7.2. Log reverse proxy và ứng dụng cho cùng request

~~~json
{
  "event_time": "2026-11-28T05:40:12.135Z",
  "source": "reverse-proxy",
  "local_request_id": "proxy-req-220",
  "correlation_id": "req-7f91a2c4",
  "upstream_service": "orders-api",
  "upstream_status": 200,
  "duration_ms": 18
}
~~~

~~~json
{
  "event_time": "2026-11-28T05:40:12.152Z",
  "source": "orders-api",
  "local_request_id": "app-req-445",
  "correlation_id": "req-7f91a2c4",
  "route": "/v1/orders",
  "method": "GET",
  "status": 200,
  "duration_ms": 12
}
~~~

Điểm nối là **correlation_id**, không phải local request ID. Nếu proxy hoặc ứng dụng không nhận được correlation ID, hãy kiểm tra forwarding middleware và trust boundary trước khi suy đoán SIEM bị lỗi.

### 7.3. Request bị WAF chặn

~~~json
{
  "event_time": "2026-11-28T05:41:00.000Z",
  "source": "edge-waf",
  "waf_event_id": "waf-ev-8850",
  "correlation_id": "req-0c6f91ab",
  "host": "api.example.com",
  "method": "POST",
  "path": "/v1/orders",
  "matched_rule_ids": ["managed-example-42"],
  "rule_action": "BLOCK",
  "final_action": "BLOCK",
  "edge_status": 403,
  "origin_status": null,
  "policy_version": "waf-policy-v12"
}
~~~

**Không có log ứng dụng tương ứng có thể là kết quả mong đợi**, vì request đã bị chặn tại WAF. Kiểm tra cuối cùng vẫn cần xác minh địa chỉ origin và đường đi; không nên kết luận chắc chắn chỉ từ việc thiếu một bản ghi ở ứng dụng.

## 8. Phân biệt matched rule, rule action và final action

Trong nhiều WAF, **một request có thể khớp nhiều điều kiện**, nhưng chỉ có một kết quả cuối ở điểm thực thi. Thuật ngữ chính xác khác nhau theo engine; cần đọc cách WAF xử lý **priority, terminating action, score và override**.

| Rule action / chế độ | Ý nghĩa thường gặp | Kết luận không nên tự suy |
|---|---|---|
| **ALLOW** | Cho request qua tại một bước/chính sách | Không chứng minh origin sẽ trả 2xx hoặc request an toàn |
| **BLOCK** | WAF từ chối request ở điểm thực thi | Không chứng minh đây chắc chắn là tấn công; có thể false positive |
| **COUNT / LOG / MONITOR** | Ghi nhận match và thường cho pipeline xử lý tiếp | **Không** đồng nghĩa request bị chặn |
| **CHALLENGE / CAPTCHA** | Yêu cầu client hoàn thành bước kiểm tra theo engine | Không đồng nghĩa client đã thành công hay thất bại; cần xem kết quả challenge |
| **RATE LIMIT** | Giới hạn request theo ngưỡng và khóa đếm | Không tự chứng minh nguồn là bot; client dùng NAT có thể bị ảnh hưởng |
| **EXCEPTION / OVERRIDE** | Điều chỉnh phạm vi hoặc hành động của một rule | Có thể tạo điểm mù nếu quá rộng hoặc kết thúc kiểm tra sớm |

### 8.1. Cần phân biệt ba lớp kết quả

1. **Rule matched:** tín hiệu/rule nào đã nhận diện request.
2. **WAF final disposition:** request được đi tiếp, bị block, challenge hay xử lý khác tại WAF.
3. **HTTP status cuối cùng:** client nhận 200, 401, 403, 429, 502, 504... tùy toàn bộ chuỗi.

**HTTP 403 không chắc do WAF trả.** Nó có thể là phản hồi từ ứng dụng khi thiếu quyền, từ API gateway khi token không hợp lệ hoặc từ proxy khi policy từ chối. Tương tự, HTTP 429 có thể do WAF, gateway hoặc backend áp quota.

Nếu log chỉ có **matched_rule_ids** nhưng thiếu **final_action**, không nên lập bảng thống kê “blocked” bằng cách đếm mọi match. Hãy dùng nguồn dữ liệu có quyết định cuối hoặc ghi rõ đây là **số lượt match**.

## 9. WAF log với managed rule và custom rule

Chính sách WAF thường có **managed rule group** do nhà cung cấp/cộng đồng duy trì và **custom rule** theo API hoặc tổ chức. Log phải giúp phân biệt chúng:

| Thuộc tính | Managed rule | Custom rule |
|---|---|---|
| **Rule ID / group ID** | Cho biết rule và nhóm được cung cấp | Tên/ID do đội vận hành định nghĩa |
| **Version** | Quan trọng khi nhà cung cấp cập nhật chữ ký hoặc engine | Quan trọng khi triển khai thay đổi chính sách |
| **Matched field** | URI, header, query, body hoặc score theo hỗ trợ | Đối tượng và điều kiện tự xác định |
| **Action override** | Có thể chuyển một rule sang COUNT hoặc dùng exclusion | Có thể allow, block, rate limit hoặc challenge tùy engine |
| **Người chịu trách nhiệm** | Chủ dịch vụ WAF và người quản lý rollout của group | Chủ custom rule và ứng dụng bị ảnh hưởng |

Một false positive sau cập nhật managed group nên được truy theo **phiên bản, rule ID, endpoint, matched field, final action và thời điểm bắt đầu**. Cần lưu lịch sử thay đổi rule và exception để so với biến động 403/429 và lỗi ứng dụng.

**Cẩn trọng với custom ALLOW ở ưu tiên cao:** trong engine mà ALLOW kết thúc đánh giá, request match có thể không được kiểm tra bởi managed rules ở phía sau. Log chỉ thể hiện ALLOW cuối cùng mà thiếu event managed rule không tự chứng minh request không có dấu hiệu nguy hiểm.

## 10. Logging và giới hạn của nguồn dữ liệu

### 10.1. Những trường hợp có thể không thấy log như kỳ vọng

- Request bị lọc **trước điểm WAF** bởi CDN/DDoS/edge policy khác.
- Request đi thẳng tới **origin**, qua IP/hostname/route khác hoặc IPv6, bỏ qua WAF.
- Request bị WAF chặn, nên **không có log app**.
- Request trả từ **cache CDN**, nên origin không có log.
- WAF cấu hình chỉ xuất event **Block/Challenge**, không xuất mọi Allow.
- Sampling, giới hạn ingest, mất kết nối đến log destination, retry export hoặc pipeline lỗi khiến log đến chậm hay thiếu.
- Một số giao thức **HTTP/2, HTTP/3, WebSocket, gRPC** hoặc body quá lớn không được parse/log đầy đủ theo sản phẩm.
- Trường ID bị đổi tên, bị bỏ khi qua gateway hoặc không tương thích với log schema trong SIEM.

Điều tra cần **đối chiếu số đếm request ở từng hop** trong cùng khoảng thời gian, thay vì suy từ “không có log” rằng “không có traffic”.

### 10.2. Đồng bộ thời gian và thời điểm log đến

Hãy phân biệt **event_time** (lúc request xảy ra) và **ingest_time** (lúc hệ thống nhận log). Export log thường bất đồng bộ; một bản ghi có thể đến sau các bản ghi xảy ra muộn hơn. Nên chuẩn hóa timestamp ở UTC, đồng bộ đồng hồ thiết bị và lưu thông tin nguồn/múi giờ khi cần.

Khi truy vấn sự cố, cho phép **khoảng đệm thời gian** phù hợp với độ trễ và sai số đồng hồ đã đo. Nếu hệ thống có nhiều region, không chỉ dựa vào thứ tự xuất hiện của dòng log để suy ra thứ tự request.

### 10.3. Fan-out, retry và bản ghi trùng

Proxy có thể retry tới backend khác, hoặc một request tạo nhiều event theo rule. Vì thế ghép log cần **source, local ID, correlation ID, timestamp và quan hệ hop**, tránh đếm mỗi dòng là một yêu cầu mới. Nếu SIEM ingest lại cùng event sau retry, nên có cơ chế **deduplicate theo event ID và nguồn** khi cơ chế xuất log bảo đảm định danh phù hợp.

## 11. Bảo vệ dữ liệu và tính toàn vẹn của WAF log

WAF có thể nhìn thấy header, query string và body chứa dữ liệu nhạy cảm nếu đứng tại điểm TLS termination. Log bảo mật vì vậy cũng là **tài sản cần bảo vệ**.

### 11.1. Không nên ghi những gì?

- **Mật khẩu, access token, refresh token, API key, session cookie, Authorization header** còn hiệu lực.
- Dữ liệu cá nhân không cần thiết cho điều tra: thông tin liên hệ, số giấy tờ, thông tin thanh toán, nội dung sức khỏe hoặc dữ liệu người dùng nhạy cảm khác.
- Toàn bộ request body, file upload hoặc query parameter chứa secret nếu không có mục đích và quyền xử lý rõ ràng.
- Dữ liệu vô hạn do client kiểm soát, có thể khiến log phình to hoặc tạo nhiễu và rủi ro **log injection**.

**Ghi đủ bằng chứng, không ghi tất cả dữ liệu.** Có thể lưu method, route đã chuẩn hóa, policy/rule ID, action, kích thước, hash hoặc metadata phù hợp và một phần field đã redacted. Nếu phải lưu mẫu payload phục vụ điều tra, cần áp dụng quy trình và quyền truy cập giới hạn, tránh đưa raw payload nhạy cảm vào dashboard rộng rãi.

### 11.2. Kiểm soát tại pipeline

1. **Chuẩn hóa cấu trúc:** dùng JSON/structured events với schema ổn định, escape ký tự điều khiển để tránh log forging và parser confusion.
2. **Mask/redact trước khi xuất:** che token, cookie và dữ liệu cá nhân; không chỉ dựa vào việc ẩn trường ở giao diện SIEM.
3. **Giới hạn trường do client kiểm soát:** chiều dài, encoding, số lượng header và dữ liệu request không đáng tin.
4. **Phân quyền truy cập:** tách nhóm vận hành, SOC, ứng dụng; dùng RBAC, MFA và audit truy cập.
5. **Bảo vệ truyền tải và lưu trữ:** mã hóa phù hợp, quản lý khóa, chính sách retention và xóa dữ liệu.
6. **Chống sửa/xóa trái phép:** lưu log tập trung, quản lý quyền ghi và cơ chế bất biến hoặc lưu dấu kiểm toán khi thích hợp.
7. **Giám sát chính pipeline:** tỷ lệ drop, lag, schema parsing errors và tình trạng collector.

Request ID **không phải một credential** nhưng vẫn có thể được coi là metadata nhạy cảm trong một số hệ thống: nó cho phép người có quyền tìm một chuỗi hoạt động cụ thể. Không đưa trace ID, request ID vào đường truy cập dữ liệu mà thiếu kiểm tra quyền.

## 12. Thiết kế schema log thống nhất cho SOC

Ở kiến trúc có nhiều lớp WAF, firewall, VPN, DNS, IDS/IPS và hạ tầng cloud, cách đặt tên field thống nhất giúp giảm thời gian điều tra.

### 12.1. Trường cơ bản nên chuẩn hóa

| Field quy ước | Ví dụ | Ghi chú |
|---|---|---|
| event_time | 2026-11-28T05:41:00Z | Thời gian sự kiện UTC |
| ingest_time | 2026-11-28T05:41:03Z | Thời gian SIEM nhận |
| source | edge-waf | Tên hệ thống phát event |
| service | orders-api | Tài sản/dịch vụ có owner |
| correlation_id | req-0c6f91ab | Dùng ghép qua các hop khi có |
| local_request_id | proxy-req-220 | ID do nguồn log tự tạo |
| waf_event_id | waf-ev-8850 | Định danh event trong WAF |
| http.host / http.route | api.example.com / /v1/orders | Ưu tiên route/template khi có để giảm PII và cardinality |
| http.method | POST | Method request |
| network.peer_ip | 198.51.100.25 | IP kết nối quan sát được; phân biệt với trusted client IP |
| waf.rule_id | managed-example-42 | ID nhóm luật và version nếu cần |
| waf.final_action | BLOCK | Hành động sau cùng ở WAF |
| http.status_code | 403 | Mã HTTP tại đúng điểm ghi log |
| policy_version | waf-policy-v12 | Bằng chứng config có hiệu lực |

Đây là **schema khuyến nghị minh họa**, không phải tên field của một hệ thống tiêu chuẩn bắt buộc. Có thể ánh xạ vào OpenTelemetry, Elastic Common Schema hoặc chuẩn log nội bộ nếu được áp dụng; giữ nguyên nghĩa của **rule action** và **final action**, tránh gộp mất thông tin.

### 12.2. Tách IP quan sát được và IP client đã xác minh

Khi WAF đứng sau CDN, IP socket có thể là proxy. Header **X-Forwarded-For** do client gửi không đáng tin nếu chưa được proxy tin cậy chuẩn hóa. Log nên cho thấy **observed peer IP**, **trusted client IP** theo chính sách, cùng **độ tin cậy nguồn** khi có. Điều này ảnh hưởng trực tiếp tới rule rate limit theo IP, bot detection và điều tra sự cố VPN/cloud.

## 13. Truy vấn để truy vết một request

Sau khi có request ID, trình tự hữu ích là:

1. Xác định **ID do tầng nào cấp** và tên trường trong từng nguồn log.
2. Tìm event ở **tầng ghi nhận gần client nhất** trong khoảng thời gian có đệm hợp lý.
3. Kiểm tra **final action, matched rules, policy version, host/path và edge status**.
4. Nếu WAF cho qua request, tìm log reverse proxy/gateway bằng correlation ID; xác minh mapping nếu chỉ có local ID.
5. Tìm application trace, authn/authz và upstream call; nối với rule, session và user ID **chỉ khi danh tính được xác thực**.
6. So với firewall flow log, DNS, VPN, IDS/IPS nếu tình huống liên quan tới đường đi, nguồn kết nối hoặc hành vi bất thường.

### 13.1. Truy vấn mẫu dạng SQL minh họa

Đây là **SQL tham khảo theo schema giả định**; các hệ SIEM thực tế dùng cú pháp, tên bảng và hàm khác nhau:

~~~sql
-- Tìm đúng correlation ID trong cửa sổ thời gian
SELECT event_time, source, correlation_id, waf_event_id,
       waf_final_action, http_status_code, policy_version
FROM normalized_security_events
WHERE correlation_id = 'req-0c6f91ab'
  AND event_time >= '2026-11-28T05:35:00Z'
  AND event_time <  '2026-11-28T05:50:00Z'
ORDER BY event_time;
~~~

Nếu muốn tìm 403 từ WAF theo policy thay đổi, phải tách **số event** khỏi **số request**:

~~~sql
-- Đếm số request ID khác nhau có final BLOCK tại WAF
SELECT policy_version, waf_rule_id,
       COUNT(DISTINCT correlation_id) AS blocked_requests
FROM normalized_security_events
WHERE source = 'edge-waf'
  AND waf_final_action = 'BLOCK'
  AND event_time >= '2026-11-28T05:00:00Z'
  AND event_time <  '2026-11-28T06:00:00Z'
GROUP BY policy_version, waf_rule_id;
~~~

Trong hệ thống thật, cần định nghĩa cách xử lý event có **thiếu ID**, ID trùng giữa nhiều hop, request khớp nhiều rule và WAF có nhiều event một request. Đếm **DISTINCT correlation_id** chỉ hợp lệ nếu ID đúng là duy nhất trong phạm vi thời gian/nguồn đang truy vấn. Nếu chưa bảo đảm điều đó, dùng khóa định danh request theo nguồn và schema riêng của engine.

## 14. Quy trình điều tra sự cố: từ request ID tới nguyên nhân

### Tình huống A — Người dùng nhận 403 ngay sau khi bật managed rule

**Dữ kiện:** nhóm ứng dụng vừa phát hành API nhận mô tả sản phẩm; người dùng báo request ID **req-0c6f91ab** và mã 403.

**Thao tác:**

1. Tìm request trong WAF log, xác định 403 xuất phát từ **final_action = BLOCK** hay từ origin.
2. Nếu WAF BLOCK: đối chiếu **managed group ID, rule ID, policy version, matched field**, thời gian phát hành và tỷ lệ 403 tăng.
3. Đánh giá dữ liệu hợp lệ theo API contract và xác nhận đây là **false positive**, không dựa vào cảm nhận của người dùng.
4. Áp dụng **override/exclusion hẹp** đúng rule, field, endpoint, có owner và hạn review; tránh ALLOW quá rộng bỏ qua các rule khác.
5. Kiểm thử lại với request hợp lệ và mẫu kiểm thử an toàn do đội ứng dụng/phòng vệ xác nhận, kiểm tra log cuối cùng và theo dõi sau rollout.

**Kết luận cần bằng chứng:** Rule cụ thể đã chặn request hợp lệ; exception đã giải quyết nhưng giữ các lớp kiểm tra khác. Một dòng “WAF trả 403” là chưa đủ để kết luận nguyên nhân.

### Tình huống B — 403 do ứng dụng, WAF cho qua

**Dữ kiện:** WAF ghi **ALLOW**, origin status 403; ứng dụng ghi “permission denied”.

**Cách hiểu:** WAF không phải thành phần ra quyết định chặn cuối. Cần kiểm tra token, tài khoản, resource/tenant và chính sách **authorization** ở API. Không vô hiệu hóa WAF rules để khắc phục lỗi quyền.

### Tình huống C — Origin ghi traffic lạ, WAF không có event

**Dữ kiện:** server origin có request bất thường nhưng không có event WAF trong cùng khoảng thời gian.

**Giả thuyết cần kiểm tra:** IP/hostname origin công khai, route riêng qua VPN/peering, IPv6, health check, internal API hoặc pipeline WAF log đang lỗi. Kiểm tra DNS phụ, route table, security group/ACL, điểm TLS termination và đối chiếu thời gian. **Thiếu WAF log không tự chứng minh bypass**; phải có bằng chứng đường đi và logging coverage.

### Tình huống D — Rate limit chặn nhiều nhân viên sau NAT

**Dữ kiện:** Nhiều người dùng từ một văn phòng cùng nhận 429 và chia sẻ IP public.

**Điều tra:** xem rate key, trusted client IP, số danh tính thực, request pattern theo route và lưu lượng hợp lệ cao điểm. Nếu nhiều người cùng bị gộp vì NAT, đánh giá quota theo tenant/user/API key đã xác thực hoặc ngưỡng phù hợp. Tránh whitelist toàn bộ IP công ty khỏi mọi lớp phòng vệ.

### Tình huống E — Một request ID xuất hiện ở nhiều dịch vụ, thời gian không theo thứ tự

**Dữ kiện:** API gateway, ứng dụng và worker đều ghi correlation ID giống nhau; worker xuất hiện trong SIEM trước log WAF.

**Giải thích có thể:** request fan-out, queue bất đồng bộ, đồng hồ sai hoặc thời gian ingest lệch. Phân biệt **event_time**, **ingest_time**, **trace/span ID**, và quan hệ cha-con. Không suy rằng ID chung bắt buộc là một HTTP request đơn lẻ hoặc mọi sự kiện xảy ra theo thứ tự hiển thị.

## 15. Giám sát WAF log ở cấp hệ thống

Để WAF logs trở thành bằng chứng giám sát có ích, cần đo **độ bao phủ và độ tin cậy của pipeline**, song song với các chỉ số phát hiện.

| Nhóm chỉ số | Ví dụ | Ý nghĩa vận hành |
|---|---|---|
| **Coverage** | Số hostname/route public có WAF policy và event log | Biết dịch vụ nào thực sự có khả năng quan sát |
| **Security actions** | Tỷ lệ final ALLOW/BLOCK/CHALLENGE/RATE LIMIT | Theo dõi tác động chính sách |
| **Rule quality** | False positive theo rule/endpoint, exception hết hạn | Đo nhu cầu tuning và rủi ro rule lỗi thời |
| **Request correlation** | Tỷ lệ request có ID xuyên WAF → proxy → app | Đo khả năng truy vết end-to-end |
| **Log delivery** | Tỷ lệ event đến collector, ingest lag, export errors | Phát hiện sự cố pipeline |
| **Incident telemetry** | Sự kiện 403/429/5xx theo policy version, host và origin | Phân biệt lỗi ứng dụng với thay đổi WAF |
| **Bypass indicators** | Origin có request không qua ingress được cấp phép | Phát hiện sai route/policy hoặc đường truy cập ngoài WAF |

**Không dùng request ID làm nhãn (label/tag) cho mọi metric thời gian thực**: mỗi ID thường khác nhau, làm nổ **cardinality** và tăng chi phí/độ trễ hệ thống metrics. Giữ request ID trong log và trace; dùng các nhãn tổng hợp ổn định như service, endpoint template, action và rule group cho dashboard.

### 15.1. Các cảnh báo đáng thiết kế

- Tỷ lệ **BLOCK/403 tăng bất thường** ngay sau khi đổi policy hoặc managed rule version.
- Một rule tạo nhiều match/Block trên endpoint nghiệp vụ quan trọng, kéo theo 4xx tăng hoặc tỷ lệ thành công giảm.
- **Origin có request trực tiếp** từ nguồn không thuộc đường proxy tin cậy.
- Mất log WAF, ingest lag tăng, schema parsing errors hoặc collector hết dung lượng.
- Nhiều request rate limited nhưng xuất phát từ ít IP NAT chứa nhiều người dùng hợp lệ.
- Rule action bất ngờ đổi từ BLOCK sang COUNT hoặc custom ALLOW quá rộng được đưa vào production.

Thiết lập ngưỡng từ **baseline và mục tiêu vận hành thực tế**; không kết luận mọi đợt tăng Block là tấn công. Một bản cập nhật managed rule, thay đổi routing hoặc đợt kiểm thử có phép cũng có thể tạo biến động.

## 16. Kiến trúc tham chiếu cho log pipeline

~~~mermaid
flowchart LR
    C[Client / Partner] --> E[CDN / WAF]
    E --> P[Reverse proxy / API Gateway]
    P --> A[Application / Services]
    E -. Structured WAF events .-> L[Log collector / Stream]
    P -. Access logs .-> L
    A -. App and auth logs .-> L
    F[Network firewall / VPN / IDS] -. Security events .-> L
    L --> R[Validation / Redaction / Normalization]
    R --> S[SIEM / Search index]
    R --> T[Trace backend]
    S --> O[SOC / Operations]
    T --> O
~~~

Ở đây, **SIEM** phục vụ tìm kiếm và phát hiện an ninh, còn **tracing backend** thể hiện quan hệ giữa các span khi ứng dụng có phát trace. Hai hệ thống có thể tách biệt hoặc tích hợp. Điều kiện tiên quyết để ghép là cùng định nghĩa correlation ID, thời gian, tên service và mapping giữa WAF event với trace nội bộ.

### 16.1. Trách nhiệm tối thiểu của các nhóm

| Nhóm | Trách nhiệm |
|---|---|
| **Network Security / WAF team** | Chính sách WAF, managed/custom rule ID, final action, log export và điểm đặt WAF |
| **Ứng dụng / API team** | Sinh hoặc nhận correlation ID theo contract, propagation, application log và authz |
| **Platform / Cloud** | Reverse proxy, TLS termination, trusted headers, log pipeline, route và origin access |
| **SOC / Detection** | Tương quan sự kiện, dashboard, alert, điều tra và review false positive |
| **IAM / Data governance** | Quyền truy cập log, dữ liệu nhạy cảm, retention và audit |

Không một nhóm riêng lẻ có thể xác nhận đầy đủ sự cố nếu request đi qua nhiều ranh giới mà mỗi bên chỉ thấy log của chính mình.

## 17. Ma trận kiểm thử logging và correlation ID

Các phép thử nên chạy **trên môi trường hoặc endpoint được phép**, dùng dữ liệu tổng hợp và tải thấp, đồng thời đối chiếu cả **WAF final action và log của hop tiếp theo**.

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| T-01 | Request HTTP hợp lệ qua WAF tới ứng dụng | WAF/proxy/app có mapping rõ ràng giữa ID; request trả đúng |
| T-02 | WAF BLOCK theo rule thử nghiệm hợp lệ trên staging | Có WAF event với final BLOCK; không kỳ vọng log origin cho request bị chặn |
| T-03 | Managed rule COUNT trên request thử | Log match rõ ràng, nhưng final action vẫn được xác định riêng |
| T-04 | Ứng dụng trả 403 do thiếu quyền | WAF có thể ALLOW, app có log authz và correlation ID tương ứng |
| T-05 | Client tự gửi X-Request-ID trùng hoặc giá trị không hợp lệ | Trusted ingress thay/validate ID; log không nhận header giả làm khóa có thẩm quyền |
| T-06 | Request đi qua CDN → proxy → gateway | ID giữ đúng contract, không bị xóa/đè ngoài dự kiến |
| T-07 | CDN cache hit | Có dấu vết edge phù hợp; không bắt buộc có log origin |
| T-08 | Client retry hoặc redirect | Mỗi HTTP request có nhận diện thích hợp; truy vết được quan hệ nghiệp vụ |
| T-09 | Request từ nhiều user chung NAT | Không gộp danh tính chỉ vì IP; correlation ID giúp tách request |
| T-10 | HTTP/2, HTTP/3, WebSocket hoặc gRPC nếu hệ thống có | Biết chính xác phần WAF inspect/log và những trường bị giới hạn |
| T-11 | Log export tạm mất hoặc đến chậm | Đo được lag/loss; pipeline phục hồi theo thiết kế và không giả dữ liệu thiếu |
| T-12 | Đổi policy/version managed group | Event mới có policy version đúng; dashboard không nhầm match với block |
| T-13 | Request tới origin qua đường không được cấp phép | L3/L4 policy chặn; có bằng chứng từ firewall/origin, không chỉ dựa vào WAF |
| T-14 | Request chứa trường nhạy cảm trong dữ liệu thử | Log được redacted; không lộ token/cookie/body ngoài quy định |

### 17.1. Lệnh thử request ID cơ bản

Chỉ dùng các lệnh kiểm tra HTTP thông thường sau đây trên website/API được phép. Thay host bằng môi trường thực tế khi vận hành; domain **example.com** là domain minh họa.

~~~bash
# Xem HTTP status và header response, gồm request ID nếu endpoint có trả
curl -sS -i https://api.example.com/health

# Gửi một giá trị do client chọn để xác minh ingress có thay/validate
# Không được tin giá trị client này là ID nội bộ có thẩm quyền.
curl -sS -i https://api.example.com/health \
  -H 'X-Request-ID: client-provided-test-id'

# Xem độ trễ và mã phản hồi, tránh đưa secret vào command/log
curl -sS -o /dev/null -w 'status=%{http_code} total=%{time_total}\n' \
  https://api.example.com/health
~~~

Nếu response trả X-Request-ID, hãy tìm giá trị ấy trong **log thực tế**. Nếu không, tra ID do CDN/WAF ghi hoặc header trace được thiết kế, đối chiếu timestamp, host, route và đường kết nối. Không yêu cầu client gửi token, cookie hoặc nội dung nhạy cảm chỉ để điều tra lỗi.

## 18. Lỗi thiết kế thường gặp

| Lỗi / ngộ nhận | Hậu quả | Cách cải thiện |
|---|---|---|
| “Mọi event ID là request ID.” | Ghép sai hoặc đếm quá số request | Ghi schema và phạm vi từng ID; phân biệt event/rule/request |
| “Client đưa X-Request-ID thì cứ dùng nguyên.” | Spoofing, trùng ID, log injection hoặc sai chuỗi điều tra | Tin ID từ ingress được xác minh; validate và thay giá trị không tin cậy |
| “WAF BLOCK thì chắc có origin log.” | Mất thời gian tìm event không tồn tại | Xác định điểm chặn; dùng WAF event làm nguồn chính |
| “WAF không có log nghĩa là không có request.” | Bỏ sót bypass, cache hoặc lỗi logging | Kiểm tra coverage, sampling, route và pipeline |
| “Mọi 403 đều do WAF.” | Tuning sai rule, gây suy giảm bảo vệ | So WAF final action với app/gateway response |
| “COUNT là một request đã bị chặn.” | Báo cáo sai hiệu quả | Đếm final disposition, không chỉ matched rule |
| “Có cùng correlation ID nghĩa là cùng một HTTP request.” | Đếm sai fan-out/retry | Ghi local ID, trace/span và quan hệ hop |
| “IP trong X-Forwarded-For luôn là client thật.” | Rate limit/điều tra sai nguồn | Tin chuỗi proxy đã xác minh, phân biệt peer IP |
| “Log càng nhiều body càng dễ điều tra.” | Lộ token/PII, tăng chi phí và bề mặt rủi ro | Thu thập tối thiểu, redact, RBAC, retention |
| “ID ngẫu nhiên đủ thay xác thực.” | Rò dữ liệu nếu dùng ID làm quyền truy cập | Kiểm tra identity/authorization độc lập |
| “Metric request_id giúp trace nhanh nhất.” | Cardinality quá cao, nặng hệ metrics | Đặt ID trong log/trace, metric dùng nhãn ổn định |
| “Log vào SIEM theo đúng thứ tự xảy ra.” | Đưa ra kết luận thời gian sai | Phân biệt event_time/ingest_time, đồng bộ giờ |

## 19. Checklist thiết kế và vận hành WAF log

- [ ] Xác định **điểm nào tạo ID** và ID nào là nguồn chính cho WAF, proxy, gateway và ứng dụng.
- [ ] Có schema ghi rõ **event ID, request ID, correlation ID, trace/span ID và rule ID**.
- [ ] Không tin ID hoặc địa chỉ IP do client không tin cậy tự khai; chuẩn hóa tại ingress.
- [ ] Kiểm thử propagation, override, retry, cache, fan-out và đường async khi áp dụng.
- [ ] Ghi được host, method, route/path, timestamp UTC, policy/rule ID và phiên bản có hiệu lực.
- [ ] Phân biệt **rule match/action** với **WAF final action** và HTTP response status.
- [ ] Biết WAF chỉ log Block hay cả Allow, có sampling và giới hạn body/protocol hay không.
- [ ] Đối chiếu origin traffic để phát hiện đường bypass WAF, IPv6 hoặc endpoint chưa gắn policy.
- [ ] Có khả năng liên kết WAF event với reverse proxy, app, authn/authz và flow log.
- [ ] Có request/correlation ID không nhạy cảm để support tra cứu khi cần.
- [ ] Bảo vệ log khỏi token/cookie/password/PII; có redaction, RBAC, retention và audit.
- [ ] Giám sát ingest lag, lỗi parser, log loss và vùng không có logging coverage.
- [ ] Dashboard tách final Block, Count, Challenge, Allow và số lần match.
- [ ] Metric không dùng request ID làm nhãn cardinality cao.
- [ ] Có regression test sau đổi WAF rules, TLS termination, proxy, API route và log schema.
- [ ] Các ngoại lệ policy và logging có owner, lý do, hạn review và bằng chứng vận hành.
- [ ] Xem WAF log cùng các lớp phòng vệ mạng, phân đoạn, VPN, IDS/IPS, DNS và cloud.

## 20. Câu hỏi tự kiểm tra

**1. WAF event ID có luôn là request ID của ứng dụng không?**  
Không. Event ID có thể chỉ định danh một bản ghi WAF; app thường có local request ID riêng. Cần correlation ID hoặc ánh xạ giữa các ID.

**2. Vì sao một request bị WAF Block lại không có log ở origin?**  
Vì request đã dừng tại WAF. Đây có thể là hành vi đúng; cần xác nhận final action và điểm đặt WAF.

**3. Nếu WAF ghi COUNT cho rule SQLi, có thể báo rằng WAF đã chặn request đó không?**  
Không. COUNT thường ghi nhận match rồi tiếp tục pipeline; phải xem **final action**.

**4. X-Request-ID từ client Internet có nên được xem là dữ liệu tin cậy?**  
Không. Cần validate và tạo/thay ID ở trusted ingress, hoặc lưu giá trị client ở trường riêng không tin cậy.

**5. Trace ID khác request ID như thế nào?**  
Trace ID liên kết nhiều span trong một trace phân tán và có thể bao gồm nhiều request/service call; request ID định danh request theo phạm vi đã định. Có thể lưu cả hai.

**6. Vì sao thấy HTTP 403 chưa đủ để kết luận một managed rule gây false positive?**  
403 có thể đến từ WAF, gateway hoặc app. Phải tìm rule ID, matched field, policy version, final action và log ứng dụng liên quan.

**7. Nếu origin có request nhưng WAF không có log, nên kiểm tra gì?**  
Kiểm tra đường bypass, DNS/route/IPv6, những lớp lọc trước WAF, cache và tình trạng export/sampling/log pipeline. Thiếu log chưa tự chứng minh bypass.

**8. Vì sao không dùng request ID làm nhãn metric cho mọi request?**  
Vì mỗi request tạo giá trị mới, dẫn đến cardinality cực cao và tăng chi phí/lỗi hiệu năng. ID phù hợp cho log/trace; metric nên tổng hợp theo các nhãn ổn định.

**9. Log có request body chứa token thì nên xử lý thế nào?**  
Ngăn việc xuất token, mask/redact trước khi lưu, hạn chế truy cập, áp retention và xử lý dữ liệu đã lộ theo quy trình. Không đưa raw token vào báo cáo điều tra.

## 21. Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): ghi log phục vụ an ninh, trường dữ liệu, chống log injection và bảo vệ dữ liệu nhạy cảm.
- [OWASP Web Application Firewall](https://owasp.org/www-community/Web_Application_Firewall): vai trò của WAF và các giới hạn cần lưu ý.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng traceparent, tracestate và truyền trace context giữa các dịch vụ.
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/): tracing, logs, correlation và observability cho hệ thống phân tán.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): quản lý và phân tích log bảo mật.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): phương thức, response status và ngữ nghĩa HTTP.
- [OWASP API Security](https://owasp.org/API-Security/): bối cảnh kiểm soát truy cập và lạm dụng API mà WAF log cần kết hợp với log ứng dụng.

**Ghi nhớ:** WAF log cho biết **WAF đã nhìn thấy gì và quyết định gì**; request ID và correlation ID giúp ghép bằng chứng qua nhiều hop. Điều tra đáng tin cần phân biệt **rule match với final action**, **event ID với request ID**, **log bị thiếu với request không tồn tại**, đồng thời kiểm soát ranh giới tin cậy, dữ liệu nhạy cảm và độ phủ của pipeline giám sát.
