# API Gateway và vai trò tại đường biên hệ thống

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm:** Cổng API (API Gateway)  
> **Trọng tâm:** Thiết kế, vận hành và bảo vệ điểm vào của hệ thống phân tán khi nhiều ứng dụng khách cùng gọi nhiều dịch vụ phía sau.

## 1. Mục tiêu học tập

Sau khi học, người đọc có thể:

- Giải thích **API Gateway** là gì, vì sao cần một đường biên có kiểm soát và những bài toán nó giải quyết trong kiến trúc Microservices.
- Phân biệt API Gateway với **reverse proxy**, **load balancer**, **ingress controller**, **WAF**, **BFF**, **service mesh** và **identity provider**; biết các thành phần này có thể cùng tồn tại.
- Thiết kế trách nhiệm đặt tại gateway: định tuyến, xác thực ở ranh giới, TLS, chính sách lưu lượng, định dạng lỗi, khả năng quan sát và chuyển đổi contract có kiểm soát.
- Phân định đúng giữa **chính sách chung ở gateway** và **quy tắc/quyền nghiệp vụ ở service**; tránh biến gateway thành một monolith mới.
- Phân tích timeout, retry, rate limit, circuit breaker, backpressure và trường hợp dịch vụ phía sau lỗi.
- Thiết kế gateway chạy nhiều replica, có health check, định tuyến an toàn, bảo vệ header, log/trace, triển khai canary và phương án rollback.
- Đọc ví dụ Spring Cloud Gateway, thực hành kiểm thử bảo mật, tính tương thích và khả năng chịu lỗi trong một hệ thống bán hàng.

## 2. Bài toán: client không nên cần biết toàn bộ topology nội bộ

Một nền tảng thương mại có nhiều năng lực: Catalog, Cart, Order, Payment, Inventory, Customer và Notification. Nếu web/mobile gọi trực tiếp từng service:

~~~text
Mobile App
  |----> catalog-service.internal:8080
  |----> cart-service.internal:8080
  |----> order-service.internal:8080
  |----> payment-service.internal:8080
  +----> customer-service.internal:8080
~~~

Client có thể phải biết host/port, cách xác thực của từng service, cơ chế retry khác nhau, cấu trúc lỗi không đồng nhất và thay đổi mạng nội bộ. Mỗi lần tách/gộp service sẽ có nguy cơ ảnh hưởng client. Việc đưa các service nội bộ ra Internet cũng mở rộng bề mặt tấn công.

Một cấu trúc phổ biến là:

~~~text
                             Internet / Client
                                     |
                                 DNS / CDN
                                     |
                                WAF / DDoS
                                     |
                               Public Load Balancer
                                     |
                         +-----------+-----------+
                         |      API Gateway      |
                         |   (nhiều replica)     |
                         +-----+------+-----+----+
                               |      |     |
                        +------+      |     +---------+
                        |             |               |
                   Catalog API     Order API       Payment API
                        |             |               |
                   Catalog DB      Order DB       Payment DB
~~~

Gateway cung cấp **điểm vào logic** với một hệ thống contract và chính sách có thể quản lý. Các thành phần bên ngoài như CDN, WAF hoặc public load balancer có thể là những sản phẩm riêng, hoặc được kết hợp một phần tùy nền tảng.

**Ý chính:** Gateway không phải bộ phận sở hữu toàn bộ nghiệp vụ; nó là một thành phần ở ranh giới tin cậy giúp client truy cập các khả năng được công bố và áp dụng các cơ chế chung một cách nhất quán.

### 2.1. API Gateway có giải quyết tất cả không?

Không. Gateway không tự sửa lỗi trong Order Service, không bảo đảm Payment idempotent, không thay thế database ownership hoặc quy trình saga. Nó cũng không làm biến mất mọi vấn đề bảo mật: từng service phải kiểm tra quyền trên tài nguyên và bảo vệ tương tác nội bộ theo trust model.

API Gateway được đánh giá theo **giá trị ở đường biên**, không theo số lượng business rule được chuyển vào đó.

## 3. “Đường biên hệ thống” nghĩa là gì?

Ranh giới là nơi request chuyển từ một vùng có mức độ tin cậy, khả năng kiểm soát và chính sách khác sang vùng tiếp theo.

- **Client → public edge:** Internet, mobile, browser, đối tác. Không tin dữ liệu tự khai từ client.
- **Public edge → gateway:** có thể áp dụng lọc mạng, TLS, chống tấn công và forwarding có kiểm soát.
- **Gateway → internal service:** yêu cầu định danh/ủy quyền rõ, không tự động tin mọi header.
- **Service → service:** giao tiếp nội bộ vẫn cần authentication/authorization phù hợp; có thể dùng mTLS và service identity.
- **Service → database/third party:** mỗi bên có quyền sở hữu và quản lý credential riêng.

Sơ đồ tối giản:

~~~text
[Untrusted Client]
       |
       | HTTPS
       v
+---------------------+
| Edge Trust Boundary |
| API Gateway         |
+----------+----------+
           |
           | Authenticated, controlled call
           v
[Service Trust Boundary]
           |
           v
      Domain Owner
~~~

Từ **internal** không đồng nghĩa **trusted by default**. Nếu một internal service có endpoint nguy hiểm, việc chỉ kiểm Bearer token tại gateway nhưng bỏ kiểm quyền trong service có thể khiến endpoint bị lạm dụng qua đường nội bộ, đường debug hoặc một service đã bị xâm nhập.

### 3.1. Gateway là điểm vào *logic*, không phải một tiến trình duy nhất

Có thể có nhiều gateway replica sau load balancer, nhiều vùng địa lý, hoặc nhiều cổng dành cho các nhóm client. Điểm quan trọng là khả năng áp dụng một tập chính sách nhất quán, quan sát được và có con đường cập nhật an toàn.

## 4. Phân biệt API Gateway với các thành phần dễ nhầm

| Thành phần | Chức năng chính | Quan hệ với API Gateway |
| --- | --- | --- |
| **Reverse proxy** | Nhận request và chuyển tiếp tới upstream; có thể sửa header/URL/TLS | Gateway thường thực hiện reverse proxy nhưng bổ sung chính sách API |
| **Load balancer** | Phân phối traffic giữa nhiều backend/replica | Có thể đứng trước gateway hoặc bên trong lớp proxy của gateway |
| **Ingress controller** | Hiện thực quy tắc định tuyến traffic đi vào cụm Kubernetes | Có thể cung cấp một phần hoặc nhiều tính năng gateway, không luôn tương đương |
| **WAF** | Phát hiện/chặn mẫu tấn công web theo quy tắc | Thường đứng ngoài hoặc tích hợp với gateway; không thay authorization nghiệp vụ |
| **API Gateway** | Quản lý điểm vào API: routing, auth policy, traffic, quan sát, contract edge | Lớp phục vụ client và API consumers |
| **BFF** (Backend for Frontend) | Adapter/composition tối ưu cho nhu cầu một loại frontend | Có thể nằm sau gateway hoặc là gateway riêng của nhóm client |
| **Service mesh** | Quản lý giao tiếp service-to-service, identity, policy và telemetry ở nội bộ | Thường tập trung east–west; gateway thường tập trung north–south |
| **Identity provider** | Đăng nhập, cấp credential/token, quản lý identity | Gateway xác minh hoặc chuyển kiểm chứng tới dịch vụ này |
| **API management** | Portal, catalog, subscription, lifecycle, analytics, developer onboarding | Có thể đi cùng gateway nhưng phạm vi quản trị rộng hơn một proxy runtime |

Không có quy tắc “phải dùng đủ mọi thành phần”. Một hệ thống nhỏ có thể dùng reverse proxy kèm các policy cần thiết; hệ thống lớn có thể dùng nhiều lớp với ownership rõ.

### 4.1. North–south và east–west

- **North–south traffic:** request đi vào/ra hệ thống, ví dụ mobile → gateway → Order.
- **East–west traffic:** giao tiếp giữa các service nội bộ, ví dụ Order → Inventory.

API Gateway thường được dùng cho north–south. Không nên ép tất cả các lệnh Order → Inventory chạy vòng qua public gateway chỉ vì kiến trúc đã có gateway. Giao tiếp nội bộ có thể dùng service discovery, nội bộ mesh, gRPC hoặc messaging tùy contract.

### 4.2. Gateway khác “một service gọi tất cả”

Gateway nên thực hiện các việc ở cấp giao thức/chính sách hoặc chuyển đổi contract có chủ ý. Nếu nó trở thành nơi thực hiện toàn bộ quy tắc giữ hàng, tính giá, quyết định thanh toán và commit đơn, gateway đã biến thành business orchestration monolith.

Điểm ra quyết định cần rõ:

- **Gateway:** request có được vào đường biên và route tới đâu?
- **Order:** yêu cầu đặt hàng hợp lệ, trạng thái đơn được chuyển thế nào?
- **Inventory:** có được giữ hàng và có vượt bất biến tồn kho không?
- **Payment:** giao dịch đã được thu hay chưa và có thể refund không?
- **Identity/Auth:** credential và danh tính có đáng tin không?

## 5. Những nhiệm vụ phù hợp của API Gateway

### 5.1. Định tuyến (routing)

Gateway nhận URL công khai và chuyển tới upstream đúng theo cấu hình.

~~~text
GET  /api/catalog/products  → Catalog Service
GET  /api/orders/ord-1001   → Order Service
POST /api/payments          → Payment Service
GET  /api/me                → Customer Service
~~~

Client chỉ cần domain public và contract. Nếu phía sau Order Service chuyển từ một thành ba replica hoặc đổi tên DNS nội bộ, không nhất thiết phải cập nhật mobile app.

Routing có thể dựa trên:

- Path: /api/orders/**.
- HTTP method.
- Host hoặc API subdomain.
- Version/capability được công bố.
- Tenant/region nếu được xác định từ nguồn đáng tin.
- Weight/canary khi rollout.
- Readiness và service discovery để chọn upstream khả dụng.

Không nên định tuyến theo một header do client tự khai có thể làm vượt giới hạn tenant hoặc vào endpoint quản trị nội bộ.

### 5.2. TLS termination và forwarding an toàn

Gateway có thể chấm dứt kết nối TLS từ client và tạo kết nối mới đến upstream. Cần quyết định rõ:

- TLS kết thúc ở lớp nào?
- Edge → gateway và gateway → service có mã hóa/xác thực theo yêu cầu không?
- Certificate lifecycle, rotation và ciphers được quản lý ra sao?
- Có bảo vệ host header, X-Forwarded-* và Forwarded chain không?
- Ai là trusted proxy? Client có được gửi trực tiếp các header dùng để quyết định nguồn gốc request không?

Chấp nhận client tự khai X-Forwarded-For hoặc X-User-Id làm nguồn sự thật có thể dẫn đến bỏ qua rate limit, giả mạo người dùng hoặc audit sai.

### 5.3. Xác thực ở đường biên

Gateway thường:

1. Đọc credential từ request, ví dụ Bearer token.
2. Xác minh token theo issuer, audience, signature, expiry và chính sách áp dụng.
3. Áp dụng yêu cầu coarse-grained về scope/role cho route.
4. Loại bỏ các header identity không đáng tin do client tự đưa vào.
5. Chuyển ngữ cảnh đã xác thực tới service qua cơ chế đáng tin hoặc chuyển token gốc theo contract.

Một JWT có chữ ký hợp lệ **không** tự động cho phép đọc mọi Order. Service vẫn cần kiểm tra orderId có thuộc người dùng/tenant hay không. Gateway không nhất thiết có dữ liệu domain để đưa ra quyết định chi tiết này.

### 5.4. Bảo vệ lưu lượng và tài nguyên

Các policy có thể đặt tại gateway:

- Rate limiting và quota theo principal, client app hoặc tenant.
- Giới hạn kích thước request body và header.
- Giới hạn độ dài URL, số lượng connection và request đồng thời.
- Timeout phù hợp với loại API.
- Giảm tải khi upstream quá tải.
- Định tuyến traffic và áp dụng canary weight.
- Chặn request trái contract ở mức tổng quát.
- CORS policy cho browser khi phù hợp.

Những policy này giảm việc triển khai logic hạ tầng lặp đi lặp lại trong từng service. Nhưng service vẫn cần kiểm tra riêng các ràng buộc nghiệp vụ, payload cụ thể, chính sách bảo mật và quota của năng lực mình sở hữu.

### 5.5. Observability, logging và trace propagation

Gateway là một điểm tốt để ghi:

- Request method, route ID, response status.
- Thời gian tổng và thời gian upstream.
- Số request bị chặn do auth, rate limit, body size.
- Retry, timeout và connection errors.
- Correlation/request ID và trace context chuẩn.
- Version gateway, route policy và upstream service được chọn.

Không ghi raw Authorization token, cookie session, số thẻ hay dữ liệu nhạy cảm vào access log. Không dùng userId hoặc orderId làm metric label có cardinality rất cao nếu hạ tầng metrics không được thiết kế cho điều đó.

### 5.6. Chuẩn hóa một phần HTTP contract

Gateway có thể thêm response headers chung, thống nhất trace ID, chuẩn hóa một số lỗi hạ tầng, giới hạn payload, quản lý version route hoặc chuyển đổi path. Tuy vậy **không nên sửa ngầm ý nghĩa nghiệp vụ**, ví dụ biến PaymentFailed thành HTTP 200 với “success”: true chỉ để frontend dễ xử lý.

## 6. Trách nhiệm KHÔNG nên đặt ở API Gateway

| Việc | Vì sao không nên là trách nhiệm chính của gateway? |
| --- | --- |
| Tính giá, chiết khấu và thuế | Quy tắc domain thuộc Pricing/Order và thay đổi theo nghiệp vụ |
| Quyết định cho phép giữ hàng | Bất biến tồn kho thuộc Inventory |
| Ghi trạng thái thanh toán | Payment sở hữu gateway transaction và đối soát |
| Quyết định hoàn tiền hoặc hủy đơn | Cần hiểu invariant và state machine nghiệp vụ |
| Kiểm tra ownership sâu của mọi object | Service domain có dữ liệu để kiểm ABAC/record authorization |
| Transaction xuyên nhiều service | Gateway không nên thành coordinator mặc định; workflow cần chủ sở hữu riêng |
| Lưu dữ liệu phiên nghiệp vụ dài hạn | Replica gateway phải có thể scale/restart; state quan trọng nằm ở nguồn thích hợp |
| Che mọi lỗi upstream thành một response thành công | Mất semantics, khiến client retry hoặc xử lý sai |
| Đọc/ghi trực tiếp DB của nhiều service | Phá data ownership và làm gateway thành điểm coupling |

Có thể có trường hợp gateway thực hiện aggregation nhỏ hoặc BFF chuyên dụng có orchestration. Khi đó phải tách rõ **API composition** khỏi **business transaction coordinator** và có owner tương ứng.

## 7. Luồng request thực tế: GET Order

Ví dụ client gọi:

~~~http
GET /api/orders/ord-1001 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
traceparent: 00-0123456789abcdef0123456789abcdef-0123456789abcdef-01
~~~

Một luồng hợp lý:

~~~text
Client
  |
  | GET /api/orders/ord-1001
  v
Edge / WAF / Load Balancer
  |
  v
API Gateway
  |-- TLS / route matching
  |-- Authentication / coarse policy
  |-- Rate/size limits
  |-- Establish request deadline and trace context
  |
  | GET /orders/ord-1001
  v
Order Service
  |-- Fine-grained permission check for orderId
  |-- Query order data
  |-- Apply domain read semantics
  v
Gateway -> Client
~~~

Nếu token hợp lệ nhưng user không sở hữu ord-1001, Order phải từ chối theo contract. Nếu Order chậm, gateway xử lý deadline và truyền tín hiệu lỗi phù hợp, không biến một timeout thành dữ liệu Order giả.

### 7.1. Response contract có thể là

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
X-Request-Id: req-example-31

{
  "id": "ord-1001",
  "status": "CONFIRMED"
}
~~~

Cache-Control chỉ là ví dụ chính sách cho dữ liệu đơn hàng nhạy cảm. Không áp dụng cùng một header cho mọi endpoint: Catalog public có thể cache, còn profile/Order cần chính sách chặt.

### 7.2. Đường gọi khi upstream lỗi

~~~text
Client → Gateway → Order Service
                   (timeout)
         ↓
Gateway returns well-defined timeout/error response
         ↓
Client decides retry/status lookup according to operation contract
~~~

Với GET an toàn, retry có thể phù hợp trong một số giới hạn. Với POST đặt hàng, provider có thể đã commit trước khi response mất. Gateway **không được retry mù** một operation có side effect chỉ vì phát hiện timeout.

## 8. Gateway và Authentication/Authorization

### 8.1. Authentication khác Authorization

- **Authentication (AuthN):** Ai gửi request? Credential có hợp lệ và do nơi tin cậy cấp không?
- **Authorization (AuthZ):** Principal này có được thực hiện hành động trên tài nguyên cụ thể không?

Gateway có thể xử lý AuthN và một phần AuthZ ở mức route, như endpoint cần scope orders:read. Order Service vẫn phải kiểm user/tenant nào được xem đơn nào.

### 8.2. Mẫu bearer token

~~~text
Client obtains access token from Identity Provider
       |
       v
Gateway validates token:
  signature, issuer, audience, expiry, scopes
       |
       v
Order validates object-level authorization:
  order.ownerId == principal.customerId
       |
       v
Business response
~~~

Một số hệ thống cho service tự xác minh token gốc; hệ thống khác dùng token exchange hoặc identity được gateway chuyển qua kênh có xác thực mạnh. Chọn cách nào phải thống nhất **trust boundary**, tránh giả mạo.

### 8.3. Header spoofing nguy hiểm như thế nào?

Phản mẫu:

~~~http
GET /api/orders/ord-secret HTTP/1.1
X-User-Id: admin
X-Tenant-Id: tenant-high-value
~~~

Nếu gateway tin và chuyển nguyên X-User-Id làm danh tính, client có thể giả người dùng khác. Không được dùng các header identity do client tự gửi làm bằng chứng xác thực.

Một thiết kế tốt cần:

1. Loại bỏ/ghi đè header identity đặc quyền từ request không tin cậy.
2. Xác minh credential tại điểm thích hợp.
3. Truyền identity qua kênh được xác thực, có chính sách rõ.
4. Service chỉ chấp nhận trusted identity đến từ nguồn được phép.
5. Chống việc request đi vòng gateway tới endpoint nội bộ không được bảo vệ.

### 8.4. Service-to-service authentication

Không nên coi việc chạy trên cùng VPC/Kubernetes namespace là đủ tin cậy. Có thể sử dụng mTLS, workload identity, OAuth2 client credentials hoặc cơ chế phù hợp để chứng minh service đang gọi là ai. Gateway không thay thế bảo vệ east–west nếu các service gọi nhau trực tiếp.

### 8.5. CORS và CSRF không phải cùng một vấn đề

**CORS** là chính sách browser kiểm soát việc một origin đọc response từ origin khác. CORS **không** phải cơ chế xác thực người dùng và không chặn mọi client ngoài browser.

**CSRF** liên quan việc browser tự gửi credential như cookie cho request thay đổi trạng thái. Nếu gateway hoặc BFF dùng cookie-auth, cần CSRF protection phù hợp; bật CORS không tự giải quyết CSRF. Nếu dùng Bearer token do JavaScript gửi chủ động, chính sách CSRF khác nhưng vẫn phải quản lý XSS và token theft.

## 9. Routing, service discovery và phiên bản API

### 9.1. Route theo URI công khai

Một route có thể định nghĩa:

~~~text
Host: api.example.test
Path: /api/orders/**
Method: GET, POST (theo contract)
Upstream: order-service
Rewrite: strip /api
~~~

Với yêu cầu GET /api/orders/123, upstream có thể nhận GET /orders/123. Gateway phải giữ query parameters và những header cần thiết, nhưng bảo vệ các header nhạy cảm theo policy.

Không dựa vào cơ chế rewrite quá phức tạp khiến client vô tình được truy cập endpoint nội bộ như /actuator, /admin hoặc /debug.

### 9.2. Service discovery

Service phía sau có thể có nhiều replica thay đổi liên tục. Gateway tìm upstream khỏe từ DNS, Kubernetes Service, registry hoặc control plane của proxy.

~~~text
Order Service:
  - order-a:8080
  - order-b:8080
  - order-c:8080

Gateway route /api/orders/** → logical order-service
~~~

Gateway cần theo dõi readiness/destination health và kết nối an toàn. Không có lý do để hardcode mọi Pod IP vào mobile app.

### 9.3. API versioning

Client thường quan tâm **public API contract**, không cần biết cấu trúc nội bộ đã chia thành mấy service. Gateway có thể:

- Route /v1/orders đến compatibility layer.
- Route /v2/orders đến provider mới.
- Đọc media type hoặc header version theo contract.
- Giữ version cũ trong thời hạn hỗ trợ.
- Thu thập usage và thông báo deprecation.

Gateway không nên âm thầm đổi meaning của enum/field hoặc thao tác rồi cho rằng có version route là đủ. Service domain vẫn phải hỗ trợ ngữ nghĩa và kế hoạch migration phù hợp.

### 9.4. Canary traffic

~~~text
/api/orders/**
     |
     +---- 95% → order-v1
     |
     +----  5% → order-v2
~~~

Tỷ lệ ở đây chỉ để minh họa. Nếu cần giữ một phiên giao dịch nhiều request nhất quán với một version, routing có thể cần sticky policy hoặc contract tương thích giữa versions. Không được dùng điều kiện routing do client tự khai không được xác minh để truy cập bản thử nghiệm hoặc môi trường nhạy cảm.

## 10. API Gateway có nên tổng hợp dữ liệu?

Một màn hình Dashboard có thể cần Catalog, Order, Loyalty. Có hai hướng:

**Hướng A – Client gọi nhiều endpoint qua gateway:**

~~~text
Client → Gateway → Catalog
Client → Gateway → Order
Client → Gateway → Loyalty
~~~

**Hướng B – BFF/aggregation chuyên dụng:**

~~~text
Client → Gateway → Dashboard BFF
                       |--> Catalog
                       |--> Order
                       +--> Loyalty
~~~

BFF có thể hợp nhất response theo nhu cầu frontend và tránh client phải gọi nhiều lần. Nhưng mỗi lời gọi phụ thuộc tăng latency và khả năng xảy ra partial failure.

### 10.1. Khi nào aggregation ở gateway được chấp nhận?

Các phép kết hợp nhẹ, không có domain invariant phức tạp, có owner rõ và SLO hợp lý có thể nằm trong lớp edge/BFF. Ví dụ gom profile hiển thị với số đơn chưa giao.

Không nên nhồi logic:

- Tính toán thanh toán thật.
- Tự điều phối transaction đặt hàng nhiều bước.
- Sửa chéo dữ liệu của các bounded context.
- Dựa vào sự thành công của tất cả service để trả mọi màn hình nếu chỉ một phần thực sự cần.

### 10.2. Xử lý partial response

Nếu Dashboard gọi ba service và Loyalty không khả dụng, có thể trả phần còn lại kèm trường unavailable nếu product contract cho phép. Tuy nhiên với lệnh thanh toán, trả một “partial success” không có định nghĩa nghiệp vụ là nguy hiểm.

BFF/gateway phải công bố rõ **dữ liệu nào bắt buộc**, **dữ liệu nào tùy chọn**, **thời hạn chờ** và **cách thể hiện thiếu dữ liệu**.

## 11. Rate limiting, quota và bảo vệ upstream

### 11.1. Phân biệt các loại giới hạn

- **Rate limit:** số request trong một khoảng thời gian, ví dụ 100 request/phút cho một client.
- **Quota:** ngân sách theo ngày/tháng hoặc hợp đồng sử dụng.
- **Concurrency limit:** số request đang xử lý cùng lúc.
- **Connection limit:** số kết nối song song.
- **Payload limit:** kích thước body/header hoặc số bản ghi mỗi trang.
- **Budget giới hạn chi phí:** số token, truy vấn hoặc đơn vị tài nguyên được phép sử dụng.

Các chính sách có thể cùng tồn tại. Chỉ có rate limit không ngăn một request tải dữ liệu cực lớn hoặc giữ kết nối hàng phút.

### 11.2. Key của rate limiter phải đáng tin

Ví dụ giới hạn theo:

- Anonymous IP ở edge, có xét NAT/shared proxy.
- Authenticated principal.
- Client application hoặc API key được xác minh.
- Tenant hợp lệ và plan thực tế.
- Route hoặc loại thao tác có chi phí cao.

Không tin tenantId do client tự gửi nếu nó chưa được xác minh. Không coi X-Forwarded-For bất kỳ là IP thật; chỉ xử lý chuỗi proxy từ các hop được tin cậy.

### 11.3. Một replica hay toàn cụm?

Giả sử giới hạn toàn hệ thống là 100 request/phút. Nếu mỗi gateway replica có counter RAM riêng, ba replica có thể chấp nhận nhiều hơn ngưỡng mong muốn, tùy cách phân phối request.

Các lựa chọn:

- Shared limiter/counter có cập nhật nguyên tử.
- Rate limiting tại edge hoặc gateway control/data plane có semantics toàn cụm.
- Local limiter chỉ dùng để tự bảo vệ từng process, không quảng cáo là quota của tenant.

Một shared limiter như Redis có thể trở thành dependency chung; phải xác định chính sách khi unavailable: **fail-open** hay **fail-closed** tùy rủi ro. Đối với API nhạy cảm/đang bị tấn công, fail-open có thể không chấp nhận; với API read không nhạy cảm, fail-closed có thể gây outage. Quyết định cần explicit.

### 11.4. Response khi bị giới hạn

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{
  "title": "Too many requests",
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

Đây là ví dụ contract; Retry-After có thể biểu diễn theo giây hoặc thời điểm theo HTTP. Không hứa client chắc chắn sẽ được chấp nhận sau 30 giây nếu còn quota/concurrency khác.

### 11.5. Ưu tiên bảo vệ nguồn giới hạn thực sự

Nếu Payment gateway bên thứ ba chỉ cho 50 request/s, rate limit ở public gateway có thể giảm tải, nhưng Payment Service vẫn cần queue, retry budget, idempotency và khả năng đối soát. Gateway không có đủ thông tin để biết một request bị từ chối trước khi gửi hay một payment đã được đối tác xử lý sau timeout.

## 12. Timeout, retry, circuit breaker và backpressure

Một service có nhiều downstream không thể chỉ dùng “timeout mặc định” cho mọi endpoint. Cần tính deadline của cả luồng.

### 12.1. Ngân sách thời gian (deadline budget)

Giả sử hành trình người dùng có SLO khoảng 1 giây ở P95. Chặng gateway có overhead, Order có DB read, và dịch vụ ngoài có thể chậm. Nếu gateway timeout 10 giây, Order timeout 10 giây và từng client cũng retry, số request treo có thể tích lũy nhiều.

Một định hướng:

~~~text
Client deadline
  |
Gateway budget: ingress + auth + routing + upstream
  |
Order budget: business processing + DB
  |
Nested dependency budget (nếu có)
~~~

Các con số cụ thể phải dựa trên đo lường; mỗi tầng cần biết deadline còn lại, không liên tục khởi tạo timeout dài mới khiến tổng thời gian vượt ngưỡng client.

### 12.2. Cẩn thận với retry

- GET idempotent và không gây side effect thường là ứng viên retry trong giới hạn.
- PUT có semantics idempotent theo contract, nhưng vẫn cần xem các tác dụng phụ của implementation.
- POST thanh toán hoặc đặt hàng có thể đã commit trước khi response timeout.
- Retry ở cả gateway, SDK và service có thể khuếch đại tải: mỗi tầng retry 3 lần có thể tạo nhiều yêu cầu downstream trên cùng một thao tác logic.

Gateway chỉ nên retry khi **operation được chứng minh an toàn cho retry** theo contract. Các thao tác có side effect cần idempotency key, operation status và hạn mức retry phù hợp; đôi khi không retry tại gateway là lựa chọn đúng.

### 12.3. Circuit breaker

Khi một dependency trả lỗi/chậm liên tục, circuit breaker có thể tạm ngăn request mới đi vào để tránh tiêu tốn tài nguyên, rồi thử phục hồi có kiểm soát.

~~~text
CLOSED  → cho request qua, đo lỗi
   |
   | vượt điều kiện mở
   v
OPEN    → fail fast theo policy
   |
   | sau khoảng thử lại
   v
HALF_OPEN → thử một số request giới hạn
   |
   +---- thành công → CLOSED
   +---- thất bại   → OPEN
~~~

Circuit breaker không thay thế timeout hoặc bulkhead. Nếu service chỉ có một backend chung, việc ngắt toàn bộ tuyến có thể gây outage rộng; cần định nghĩa route, instance và failure classification phù hợp.

### 12.4. Backpressure và giới hạn concurrency

Khi upstream chậm, số request đồng thời đang chờ có thể tăng tới khi cạn thread, connection pool hoặc RAM. Gateway có thể áp dụng concurrency limit, queue ngắn, 503/429 hoặc shed load theo contract.

Không nên vô hạn queue tại gateway vì chỉ biến overload thành độ trễ dài và mất kiểm soát. Cần quan sát số request đang chờ và thời gian chờ.

### 12.5. Phân biệt HTTP errors

- **400/422:** request sai hoặc không đạt validation, thường không retry giống hệt.
- **401/403:** thiếu identity/quyền, không retry mù.
- **404:** tài nguyên không tồn tại hoặc được che theo bảo mật.
- **409:** conflict nghiệp vụ, client có thể cần refresh/đổi yêu cầu.
- **429:** vượt rate/quota, có chính sách backoff.
- **502:** bad gateway/upstream response không hợp lệ.
- **503:** tạm không phục vụ, có thể do overload/maintenance.
- **504:** gateway timeout khi chờ upstream.

Các status phải phản ánh failure thực tế của hệ thống, không được gán tùy ý. Không mặc định 5xx nào cũng retry an toàn, đặc biệt với mutation.

## 13. Các vấn đề protocol và dữ liệu lớn

### 13.1. Giới hạn payload

Gateway có thể giới hạn kích thước request body/header để ngăn tiêu tốn tài nguyên. Service vẫn cần validation domain về số dòng hàng, đơn vị tiền, kích thước file và content type.

Khi upload lớn, có thể dùng object storage và signed URL có thời hạn để client gửi trực tiếp, tránh proxy toàn bộ file qua gateway nhiều lần, nhưng quyền và checksum phải được kiểm theo thiết kế.

### 13.2. Pagination

API trả hàng triệu bản ghi trong một response có thể làm gateway và client tốn RAM/timeout. Gateway thường **không phải nơi quyết định logic phân trang nghiệp vụ**; provider sở hữu query và định nghĩa limit, offset/cursor, sort order, tính ổn định của trang.

Gateway có thể áp đặt max page size chung hoặc route-specific theo contract. Không được tự thay pageSize của client mà không công bố, vì client có thể hiểu nhầm dữ liệu đã trả đủ.

### 13.3. Streaming

Gateway có thể proxy WebSocket, Server-Sent Events, HTTP chunked streaming hoặc gRPC streaming nếu công nghệ được chọn hỗ trợ. Cần kiểm tra:

- Có buffer toàn bộ response hay stream từng phần?
- Read/idle timeout có phù hợp với kết nối dài?
- Connection limit và backpressure ra sao?
- Khi client disconnect, có hủy upstream request không?
- Authentication có được kiểm lúc khởi tạo và trong suốt phiên theo policy?
- Gateway có làm mất header/trailer hoặc framing của protocol?
- Khi restart gateway, client reconnect và resume thế nào?

Một gateway được cấu hình để buffer toàn bộ response có thể làm mất lợi ích streaming và tăng memory. Không nên hứa tất cả loại gateway đều hỗ trợ streaming giống nhau; cần xác minh với phiên bản sản phẩm cụ thể.

### 13.4. WebSocket không có nghĩa data session nằm mãi ở gateway

Một kết nối WebSocket cụ thể gắn với gateway replica trong khi tồn tại. Dữ liệu kết nối tạm được phép ở process; business state cần phục hồi phải tồn tại ở nguồn phù hợp. Khi gateway restart, client có thể reconnect và resume bằng cursor/sequence nếu contract hỗ trợ.

## 14. Caching tại đường biên

Caching có thể giảm tải cho Catalog hoặc content public nhưng cần phân loại tài nguyên.

**Có thể phù hợp:**

- Danh mục sản phẩm public với TTL/ETag được xác định.
- Metadata ít thay đổi và không chứa dữ liệu riêng tư.
- Response GET có cache key rõ và có chiến lược invalidation.

**Không nên cache tùy tiện:**

- Thông tin thanh toán, session, token.
- Response chứa dữ liệu tenant/người dùng mà cache key thiếu identity.
- Dữ liệu đơn hàng cần cập nhật ngay theo nghiệp vụ.
- Kết quả POST có side effect chưa được thiết kế idempotency.

Nếu cache response theo URL nhưng không tách theo Authorization/tenant, một khách có thể nhận dữ liệu của khách khác. Tránh cache dữ liệu riêng tư ở shared cache trừ khi policy và keying đủ an toàn.

### 14.1. Cache-control và ETag

ETag/If-None-Match và Cache-Control cho phép cache có điều kiện theo chuẩn HTTP; tuy nhiên gateway phải tôn trọng Vary, authorization và các header liên quan. Không ép tất cả response thành public cacheable để tăng throughput.

## 15. BFF – Backend for Frontend

Một API Gateway chung có thể là điểm vào cho web, mobile và partner, nhưng nhu cầu response khác nhau:

- Mobile cần dữ liệu ít, phù hợp băng thông và màn hình.
- Web cần nhiều phần dữ liệu cho dashboard.
- Partner cần contract ổn định, quota và error handling theo hợp đồng.

Có thể dùng mô hình:

~~~text
          API Gateway
          /    |     \
       Web    Mobile  Partner
       BFF     BFF     API adapter
        |       |          |
        +-------+----------+
                |
           Domain Services
~~~

BFF là nơi hợp lý để thực hiện composition/presentation mapping gắn với một client class; gateway chung áp dụng chính sách ở edge. Tùy quy mô có thể kết hợp hai vai trò, nhưng cần tránh một gateway chứa nhánh if/else cho mọi UI và mọi quy tắc nghiệp vụ.

### 15.1. Khi nào không cần BFF riêng?

Nếu client có cùng nhu cầu, API được thiết kế đơn giản và việc dựng thêm runtime gây chi phí lớn, một gateway cùng các service hiện có có thể đủ. Không nên tách một BFF chỉ vì tên kiến trúc nghe hấp dẫn.

## 16. Ví dụ cấu hình Spring Cloud Gateway

Ví dụ sau sử dụng cú pháp phổ biến của Spring Cloud Gateway WebFlux. **Chi tiết property và dependency có thể khác giữa các thế hệ Spring Boot/Spring Cloud**, nên phải đối chiếu tài liệu phiên bản đang dùng trước khi triển khai. Mục tiêu là hiểu cấu trúc route và policy, không phải một manifest production hoàn chỉnh.

### 16.1. Route cấu hình bằng YAML

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://catalog-service:8080
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
        - id: order-api
          uri: http://order-service:8080
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
        - id: payment-api
          uri: http://payment-service:8080
          predicates:
            - Path=/api/payments/**
          filters:
            - StripPrefix=1
~~~

Với StripPrefix=1, đường dẫn /api/orders/ord-1001 được chuyển thành /orders/ord-1001. Các upstream ở đây là DNS/host mẫu cho môi trường triển khai; có thể thay bằng địa chỉ service discovery được hỗ trợ.

**Lưu ý:** cấu hình trên chỉ làm routing. Chưa có authentication, TLS, route authorization, rate limiting, deadline, observability, health, logging protection hoặc HA. Không được coi là cấu hình sẵn sàng đưa lên Internet.

### 16.2. Một lớp bảo vệ route mức coarse-grained

Một API Gateway dùng Spring Security như OAuth2 Resource Server có thể xác minh access token và áp dụng quyền truy cập route. Ví dụ minh họa bằng Java:

~~~java
@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
                .pathMatchers("/api/orders/**").authenticated()
                .pathMatchers("/api/payments/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là mẫu định hướng cho ứng dụng dùng Bearer token; cần dependency Spring Security phù hợp, issuer/audience validation, TLS, cấu hình CSRF theo mô hình credential và kiểm tra route access thực tế. Với browser session/cookie, **không được tắt CSRF tùy tiện**. Với API có quyền chi tiết, Order/Payment vẫn phải thực hiện authorization riêng.

### 16.3. Quyền ở gateway và service

Giả sử gateway yêu cầu token cho /api/orders/**. Service có logic:

~~~java
@GetMapping("/orders/{orderId}")
public OrderView getOrder(
        @PathVariable String orderId,
        Authentication authentication) {

    String principalId = authentication.getName();

    // Query phải xét tenant/customer ownership theo mô hình thật.
    return orderApplicationService.findAccessibleOrder(
        principalId, orderId);
}
~~~

Nếu Order không kiểm quyền tài nguyên, user A có thể đoán orderId của user B. Gateway không biết ownership của mọi order và không nên được biến thành nơi phải query Order DB để tự quyết.

### 16.4. Truyền correlation ID

Gateway có thể sinh hoặc chuẩn hóa request ID, đồng thời truyền W3C trace context theo thư viện observability đã cấu hình. Không dựa hoàn toàn vào X-Request-Id do client gửi cho audit/authorization; nếu chấp nhận, phải giới hạn độ dài, ký tự và cách tin cậy.

Ví dụ một dòng log an toàn ở gateway:

~~~text
route=order-api method=GET status=200
duration_ms=74 upstream=order-service
trace_id=0123456789abcdef... request_id=req-71
~~~

Tránh log raw Authorization header hoặc thông tin payment/card. Với distributed tracing, đặt các span riêng cho gateway và upstream, không phát minh trace ID mỗi tầng khiến không ghép chuỗi được.

## 17. Thiết kế gateway không thành single point of failure

Gateway là **điểm tập trung logic** nhưng không nên chỉ có một container vật lý.

~~~text
             Public Load Balancer
             /        |         \
          Gateway A Gateway B Gateway C
             \        |         /
               Internal Services
~~~

Các replica cần:

- Config đồng bộ hoặc rollout được kiểm soát.
- Readiness/liveness phù hợp.
- Autoscaling dựa trên CPU, connection, throughput và saturation thực tế.
- Resource limits, connection pools và backpressure.
- Nơi lưu state ngoài process nếu policy cần counter toàn cụm.
- Khả năng drain connection khi deploy.
- Cơ chế phát hành cấu hình, rollback và audit thay đổi.
- Nhiều availability zone/region nếu yêu cầu sản phẩm cần.
- Không phụ thuộc một secret/key thủ công chỉ được cài tại replica A.

### 17.1. Gateway stateless ở mức phiên

Tránh lưu thông tin đăng nhập hoặc workflow session chỉ trong RAM một gateway replica. Có thể dùng token được xác minh từng request hoặc shared session store có chính sách phù hợp.

Local cache cho public keys, route config hoặc dữ liệu tối ưu hóa có thể hợp lệ khi có TTL/rotation và nguồn sự thật. Local rate limiter không mặc nhiên là quota toàn cụm.

### 17.2. Shared dependency vẫn có thể là điểm lỗi chung

Ba replica gateway cùng phụ thuộc một Redis rate-limiter hoặc một identity service. Khi dependency này hỏng, cả ba có thể ngừng nhận traffic nếu fail policy không phù hợp. HA gateway cần đánh giá **toàn bộ dependency graph**, không chỉ số replica.

### 17.3. Graceful shutdown

Trong rolling deployment:

1. Gateway cũ được đánh dấu không nhận request mới.
2. Load balancer ngừng phân phối kết nối mới.
3. Kết nối/request đang xử lý được drain theo deadline.
4. Các kết nối WebSocket/stream có chiến lược reconnect nếu bị ngắt.
5. Gateway mới đã sẵn sàng và policy tương thích.
6. Metrics quan sát được tỉ lệ lỗi/timeout trong cửa sổ đổi phiên bản.

Không bảo đảm zero downtime chỉ bằng việc đặt replicas=3. Cần thử quá trình drain, rollback, route config và dependency failover.

## 18. Thay đổi route và contract không phá client

Ví dụ một ứng dụng ban đầu có:

~~~text
/api/v1/orders/** → monolith Order module
~~~

Sau khi tách service:

~~~text
/api/v1/orders/** → new Order Service
~~~

Gateway có thể giữ nguyên public endpoint, giảm tác động cho client. Nhưng nếu contract bên dưới thay đổi về JSON, enum, thời gian hoàn tất hoặc status code, chỉ đổi upstream route không đủ.

### 18.1. Strangler migration

Một lộ trình:

- **Bước 1:** ghi contract công khai đang được sử dụng.
- **Bước 2:** triển khai Order mới hỗ trợ contract và xử lý dữ liệu có owner rõ.
- **Bước 3:** test route mới với traffic giả lập hoặc read-only shadow an toàn.
- **Bước 4:** canary nhóm request có thể rollback.
- **Bước 5:** đo lỗi, latency, sai lệch nghiệp vụ và xác nhận state migration.
- **Bước 6:** tăng traffic khi tiêu chí đạt, rồi loại bỏ route cũ có kiểm soát.

**Không mirror một lệnh thu tiền hoặc tạo đơn có side effect tới hai provider** chỉ để so sánh. Shadow traffic phải được giới hạn an toàn (read-only, fake sandbox hoặc dry-run thật sự không tạo tác dụng) và có đánh giá quyền riêng tư.

### 18.2. Khi rollback route không đồng nghĩa rollback dữ liệu

Nếu service mới đã tạo Order ở database mới, chỉ chuyển route về monolith cũ có thể khiến client “không thấy đơn” hoặc ghi lặp. Kế hoạch migration phải chỉ rõ quyền ghi, dữ liệu đồng bộ, phát hiện xung đột và cách rollback cả traffic lẫn business state.

## 19. API Gateway và lỗi cục bộ trong hệ thống phân tán

### 19.1. Một upstream chậm không được làm gateway nghẽn toàn bộ

Giả sử Payment Service chậm, nhưng Catalog vẫn khỏe. Nếu gateway dùng chung pool/threads và mọi request Payment giữ tài nguyên đến vô hạn, Catalog có thể bị ảnh hưởng.

Các biện pháp:

- Timeout theo route.
- Max in-flight requests và connection pool hợp lý.
- Bulkhead hoặc phân vùng tài nguyên cho tuyến tốn nhiều.
- Circuit breaker cho dependency có đặc tính phù hợp.
- Response error chuẩn có trace ID.
- Observability để chỉ ra tuyến upstream gây saturation.

### 19.2. Tránh retry storm

Nếu gateway timeout 3 giây và retry 3 lần; client SDK lại retry 3 lần, còn service gọi downstream cũng retry, một logical operation có thể sinh nhiều request. Tại high load, retry thêm có thể khiến hệ thống khó phục hồi.

Cần phối hợp budget giữa các lớp, retry có jitter/backoff khi thích hợp, chỉ retry request an toàn và ghi nhận số lần thực tế. Với mutation, idempotency phải được bảo vệ ở owner nghiệp vụ.

### 19.3. Gateway không nên “giấu” outcome chưa biết

Ví dụ:

~~~text
Client → Gateway → Payment
                        |
                        +-- Payment commit thành công
                        |
                        X response mất
Gateway thấy timeout
~~~

Gateway không được nói “payment failed” như kết quả cuối chỉ vì đã timeout. Phản hồi nên thể hiện kết quả chưa xác định theo contract, và client có phương thức tra cứu operationId hoặc Payment Service đối soát.

### 19.4. Đường dự phòng phải bảo toàn bảo mật

Khi gateway hoặc identity provider lỗi, không được “tạm bỏ auth” để duy trì traffic. Fallback chính sách bảo mật cần được thiết kế trước: có thể phục vụ public catalog cache, nhưng từ chối thao tác nhạy cảm nếu không có cách xác minh identity đáng tin.

## 20. Giám sát hoạt động và SLO của gateway

Các chỉ số quan trọng:

| Nhóm | Chỉ số | Vì sao |
| --- | --- | --- |
| Availability | Tỷ lệ request được xử lý theo contract, lỗi tại edge | Biết gateway có phục vụ đường vào được không |
| Latency | P50/P95/P99 toàn request và gateway overhead | Phân biệt chậm tại gateway hay upstream |
| Routing | Upstream selection, route_not_found, backend unavailable | Phát hiện config lỗi |
| Authentication | 401/403, JWT validation errors, key rotation failures | Phát hiện policy/issuer/config không nhất quán |
| Rate limiting | Allowed/denied, limiter store latency, per-route limits | Hiểu tải và tránh false positive |
| Reliability | Timeout, retry count, circuit-breaker state | Phát hiện dependency chậm/lỗi |
| Capacity | Connections, active requests, threads/event loop lag, CPU/memory | Biết khả năng scale và bottleneck |
| Security | WAF blocks, suspicious patterns, header rejects | Điều tra abuse theo chính sách |
| Deploy | Version, rollout/canary status, config change errors | Liên hệ sự cố với thay đổi mới |

### 20.1. Phân biệt lỗi do gateway và do upstream

Một HTTP 503 trả tại gateway có thể do không có upstream khỏe; một 503 từ Order Service có thể là overload riêng Order. Log/traces nên có trường phân biệt:

- Gateway tạo response hay chỉ forward response?
- Route nào?
- Upstream nào được chọn?
- Có timeout hoặc connection failure không?
- Có retry không?
- Client hay gateway chủ động hủy kết nối?

Không nên dùng tỷ lệ 5xx duy nhất để kết luận “gateway lỗi” nếu lỗi thật ở service downstream.

### 20.2. Tracing qua ranh giới

Khi client gửi traceparent, gateway có thể tiếp nối trace theo chuẩn; nếu không có, có thể tạo trace mới theo policy. Span ở gateway biểu diễn edge processing, span ở Order biểu diễn handler/DB. Correlation giúp thấy thời gian ở từng tầng.

Bảo vệ sampling, pii masking và quyền đọc log. Không đặt session token trong baggage hay trace attributes.

## 21. Bảng các lỗi thiết kế thường gặp

| Phản mẫu | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gateway chứa toàn bộ business logic | Coupling/deploy tập trung, phá ownership | Đưa quy tắc nghiệp vụ về service owner/BFF phù hợp |
| Chỉ gateway kiểm authorization | Internal bypass, IDOR/BOLA | Service kiểm object-level permission và identity đáng tin |
| Tin X-User-Id do client tự gửi | Identity spoofing | Loại bỏ header và xây trust chain |
| Retry POST Payment mù | Double charge | Operation ID, idempotency, reconciliation |
| Rate limit cục bộ nhưng quảng cáo quota toàn cụm | Vượt ngưỡng khi scale | Shared limiter hoặc policy đúng semantics |
| Gateway một replica | SPOF khi restart/incident | Nhiều replica, LB, drain, capacity test |
| Route wildcard quá rộng | Expose endpoint admin/debug | Deny by default, route allowlist, test đường dẫn |
| Buffer mọi stream | Tăng RAM, mất tính thời gian thực | Streaming proxy phù hợp và backpressure |
| Cache theo URL cho dữ liệu người dùng | Rò rỉ dữ liệu tenant | Cache key/security policy đúng, no-store khi cần |
| Timeout rất dài | Cạn connection và chậm lan truyền | Deadline budget, timeout phù hợp, shed load |
| Mỗi tầng retry độc lập | Retry storm | Ngân sách retry chung và phân loại thao tác |
| Schema rewrite quá nhiều | Client contract phụ thuộc gateway | Version rõ và mapping có owner |
| Log token/cookie/request body nhạy cảm | Rò credential/PII | Masking, sampling, log policy |
| Không đo gateway overhead | Khó tìm bottleneck | Metrics và distributed tracing |
| Thay route mà không chuyển data ownership | Đơn mất/lặp khi rollback | Migration/reconciliation và runbook |

## 22. Checklist thiết kế trước khi đưa gateway vào sản phẩm

### 22.1. Hợp đồng và trách nhiệm

- [ ] Danh sách public API và consumer đã được xác định.
- [ ] Có ranh giới trách nhiệm gateway so với service domain.
- [ ] Route, method, version và upstream được mô tả rõ.
- [ ] Không phơi endpoint nội bộ/admin/debug qua wildcard route.
- [ ] Public contract và chính sách deprecation độc lập cấu trúc service nội bộ.
- [ ] Các thay đổi body/header/error không làm sai ngữ nghĩa nghiệp vụ.

### 22.2. Bảo mật

- [ ] TLS và trust chain ở các hop được xác định.
- [ ] Gateway kiểm credential theo issuer/audience/expiry/signature/policy thích hợp.
- [ ] Service vẫn kiểm quyền trên tài nguyên và bất biến nghiệp vụ.
- [ ] Header identity từ nguồn không tin cậy bị loại bỏ/ghi đè.
- [ ] Không có đường vòng bypass gateway để truy cập dữ liệu không bảo vệ.
- [ ] CORS/CSRF được thiết kế theo mô hình browser/cookie thực tế.
- [ ] Secrets và private keys có cơ chế rotation và kiểm soát truy cập.
- [ ] Access log không chứa credential hoặc dữ liệu nhạy cảm.

### 22.3. Độ tin cậy và hiệu năng

- [ ] Timeout và deadline theo route có căn cứ.
- [ ] Retry chỉ áp dụng cho thao tác an toàn; mutation có idempotency.
- [ ] Rate limits/quota rõ scope, key đáng tin và semantics nhiều replica.
- [ ] Có backpressure, giới hạn connection/concurrency/payload.
- [ ] Circuit breaker/fallback không che outcome chưa biết.
- [ ] Caching có chính sách quyền riêng tư và invalidation.
- [ ] Streaming/WebSocket có idle timeout và khả năng reconnect hợp lý.
- [ ] Gateway có nhiều replica, drain, readiness và phương án rollback.
- [ ] Dependency dùng chung có kế hoạch khi lỗi/overload.

### 22.4. Vận hành và tiến hóa

- [ ] Route/config được quản lý thay đổi và có lịch sử audit.
- [ ] Có dashboard theo route/upstream/instance.
- [ ] Có trace propagation và request correlation.
- [ ] Có canary/mixed-version tests cho thay đổi route.
- [ ] Có runbook cho 401 bất thường, 429, 502/503/504 và upstream outage.
- [ ] Có tiêu chí giữ/ngừng rollout và phương án phục hồi dữ liệu nếu cần.
- [ ] Có owner trực vận hành gateway và từng domain service.

## 23. Bài tập thực hành

### Bài 1 – Phân định Gateway và Service

Một nhóm muốn đưa tất cả việc sau vào Gateway:

1. Xác minh JWT.
2. Kiểm orderId có thuộc user hay không bằng truy vấn Order DB.
3. Rate limit theo tenant.
4. Tính giá bán và thuế.
5. Route /api/orders đến Order.
6. Ghi PaymentAttempt vào Payment DB.
7. Tạo request ID.
8. Kiểm payload size.
9. Gửi event OrderConfirmed.

**Yêu cầu:** phân loại gateway, service nghiệp vụ hoặc vị trí cần thảo luận thêm. Nêu vì sao những quyết định liên quan đến invariant và quyền sở hữu dữ liệu không nên đặt trong proxy.

**Gợi ý:** (1), (3), (5), (7), (8) thường hợp lý tại gateway theo policy; (2), (4), (6), (9) cần owner domain. Kiểm tra tenant ở edge không thay thế ownership check ở Order.

### Bài 2 – Chẩn đoán 401 ngẫu nhiên

Gateway có ba replica. Sau khi rotate JWT signing key, một số request trả 401, các request khác thành công. Thông tin lỗi phụ thuộc gateway replica.

**Yêu cầu:** đề xuất giả thuyết và kế hoạch kiểm tra.

**Gợi ý:** so sánh trust config, JWKS/cache, key rotation timing, issuer/audience, clock skew, route versions và metrics per-instance. Đừng bắt đầu bằng việc vô hiệu hóa chữ ký token.

### Bài 3 – Rate limit đa replica

Yêu cầu nghiệp vụ là tối đa 120 request/phút cho mỗi API key trên toàn hệ thống. Gateway có 4 replica, mỗi replica dùng counter RAM riêng.

**Yêu cầu:** giải thích vì sao chính sách hiện tại không bảo đảm quota, đề xuất cơ chế chia sẻ và chính sách khi rate limiter store lỗi.

**Gợi ý:** cần semantics toàn cụm, key đã xác thực, cập nhật atomic và quyết định fail-open/fail-closed theo mức nhạy cảm.

### Bài 4 – Gateway timeout sau Payment commit

POST /payments tới Payment Service đã commit giao dịch, nhưng response mất. Gateway timeout và tự retry POST bằng một operation ID khác.

**Yêu cầu:** chỉ ra sai lầm, hậu quả và thiết kế lại contract.

**Gợi ý:** timeout không chứng minh payment failed. Dùng idempotency key/operation ID giữ nguyên qua retry, lookup kết quả và đối soát cổng thanh toán.

### Bài 5 – Tách monolith theo Strangler

Monolith có /api/v1/orders. Nhóm tạo Order Service mới và muốn gateway dần chuyển traffic sang service đó.

**Yêu cầu:** lập kế hoạch contract, route, data ownership, canary, monitoring và rollback.

**Gợi ý:** shadow POST thật có thể tạo side effect lặp. Tách quyền ghi, kiểm dữ liệu và migration trước khi đổi traffic.

### Bài 6 – Streaming qua gateway

Một endpoint phát SSE tiến độ tạo báo cáo; gateway đang buffer response đến khi hoàn tất và timeout sau 30 giây.

**Yêu cầu:** giải thích triệu chứng, quyết định buffering/idle timeout, giới hạn connection và reconnect/resume.

**Gợi ý:** kiểm tra khả năng streaming của proxy, flush data, heartbeat, cancellation propagation và cách client lấy lại state từ jobId/cursor.

### Bài 7 – Thiết kế một gateway tối thiểu

Cho ba service Catalog, Order, Payment và hai loại client Web/Mobile.

**Yêu cầu:** vẽ sơ đồ ranh giới, bảng route, chính sách auth, rate limits, timeout, error mapping và telemetry tối thiểu. Ghi cụ thể phần nào vẫn thuộc Order/Payment.

**Gợi ý:** không cố thêm BFF, mesh hoặc WAF nếu không có yêu cầu tương ứng; ưu tiên một kiến trúc ít thành phần nhưng có trách nhiệm rõ và vận hành được.

## 24. Mẫu quyết định kiến trúc (ADR)

~~~markdown
# ADR: API Gateway at Public Boundary

## Context
- Những client nào truy cập?
- Public endpoints nào đang có?
- Dịch vụ nội bộ nào được expose trực tiếp?
- Những sự cố security/routing/latency nào cần giải quyết?

## Decision
- Gateway product/runtime:
- Vị trí TLS termination:
- Route ownership:
- Authentication strategy:
- Coarse authorization:
- Identity propagation:
- Service-level authorization:
- Rate limiting/quota:
- Timeout, retry, circuit breaker:
- Log/metrics/tracing:
- HA/rollback:

## Alternatives
- Reverse proxy đơn giản:
- Ingress controller có policy:
- Managed API gateway:
- Self-hosted gateway:
- BFF riêng theo client:
- Không thêm gateway ở giai đoạn này:

## Consequences
- Lợi ích:
- Chi phí thêm một network hop:
- Chi phí vận hành:
- Shared dependencies:
- Rủi ro security:
- Rủi ro migration và rollback:

## Validation
- Mixed-version routing tests:
- Header spoofing and auth tests:
- Rate-limit concurrency tests:
- Upstream outage and timeout tests:
- Long connection/streaming tests:
- Dashboard/alerts:
- Tiêu chí dừng rollout:
~~~

ADR làm rõ rằng gateway là một quyết định kiến trúc có lợi ích, chi phí và giới hạn. Sử dụng API Gateway vì “Microservices bắt buộc phải có” là lập luận chưa đủ; hãy chứng minh nhu cầu từ client, trust boundaries, khả năng kiểm soát traffic và vận hành.

## 25. Ghi nhớ

**API Gateway là cửa vào có quản lý của hệ thống, không phải trung tâm sở hữu mọi nghiệp vụ.** Nó cung cấp một nơi hợp lý để định tuyến public API, xác minh credential ở edge, giới hạn lưu lượng, áp dụng chính sách giao thức và cung cấp telemetry xuyên service. Nó giúp giảm sự phụ thuộc của client vào topology nội bộ, nhưng đồng thời thêm một hop và một thành phần cần bảo vệ, scale và vận hành.

Bốn nguyên tắc quan trọng:

1. **Tập trung chính sách chung, không tập trung toàn bộ business logic.** Giá, thanh toán, tồn kho, quyền sở hữu đơn và state transition vẫn thuộc domain service.
2. **Bảo vệ toàn bộ trust chain.** Gateway phải loại bỏ identity header giả mạo, còn service vẫn phải xác minh quyền đối với tài nguyên và ngăn bypass.
3. **Đối xử nghiêm túc với lỗi phân tán.** Timeout chưa chắc là operation failed; retry, rate limit, circuit breaker và fallback cần dựa trên semantics.
4. **Có thể vận hành và thay đổi an toàn.** Nhiều replica, config quản lý, metrics, trace, canary, rollback và dependency failure plans phải được thiết kế ngay từ đầu.

Câu hỏi để tự đánh giá một API Gateway: **“Nếu gateway bị thay thế, một downstream chậm, một client dùng token không hợp lệ, hoặc một public route trỏ nhầm vào service mới, hệ thống có vẫn giữ được ranh giới bảo mật, tính đúng nghiệp vụ và khả năng tìm nguyên nhân sự cố không?”** Câu trả lời phải dựa trên contract và phép thử, không chỉ trên sơ đồ các box.
