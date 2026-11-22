# Phân biệt lưu lượng từ bên ngoài với lưu lượng nội bộ trong Microservices

## 1. Mở đầu: hai con đường vào cùng một hệ thống

Khi khách hàng mở website bán hàng và đặt đơn, trình duyệt gửi request đến một địa chỉ công khai như https://api.shop.example/orders. Request đi qua những thành phần ở biên mạng trước khi đến Ordering Service. Sau đó Ordering Service lại gọi Inventory, Pricing và Payment Service, hoặc gửi sự kiện sang broker cho Notification Service.

Các kết nối đó đều dùng mạng, nhưng có sự khác biệt rất lớn về nguồn gọi, phạm vi tin cậy, yêu cầu bảo mật, định tuyến và khả năng chịu lỗi.

- **Lưu lượng bên ngoài vào (north–south ingress)**: browser, mobile app, đối tác hoặc client ở ngoài vùng mạng được quản lý đi đến public endpoint của hệ thống.
- **Lưu lượng nội bộ ngang (east–west)**: các service, worker, database client và thành phần hạ tầng trong một môi trường dịch vụ trao đổi với nhau.
- **Lưu lượng bên trong đi ra ngoài (north–south egress)**: service gọi cổng thanh toán, hãng vận chuyển, email provider hoặc API của bên thứ ba.

Từ north–south và east–west là phép ẩn dụ theo ranh giới kiến trúc, **không phải hướng địa lý**. Cùng một request có thể trải qua cả ba loại khi xử lý.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích north–south, east–west, ingress, egress và trust boundary.
2. Phân biệt Public DNS, Load Balancer, Ingress Controller, API Gateway, Service Discovery, Kubernetes Service, BFF và Service Mesh.
3. Vẽ đường đi request từ client đến API nội bộ, từ service này đến service khác và từ service ra provider.
4. Thiết kế endpoint public/internal mà không vô tình công khai dữ liệu và thao tác quản trị.
5. Phân biệt user identity, service identity, authentication và authorization.
6. Áp dụng các chính sách timeout, retry, rate limit, observability và network access đúng boundary.
7. Thử nghiệm định tuyến trong Kubernetes với ClusterIP, Ingress và NetworkPolicy.
8. Phát hiện những giả định sai như “mạng nội bộ mặc định đáng tin” hoặc “gọi gRPC là east–west còn HTTP là north–south”.

## 2. Định nghĩa rõ các loại traffic

### 2.1. North–south: đi qua ranh giới hệ thống

Một người dùng gọi API công khai:

~~~text
Internet / browser / mobile
             |
             v
       Public DNS
             |
             v
      Edge LB / WAF
             |
             v
        API Gateway
             |
             v
       Order Service
~~~

Đây là lưu lượng **north–south inbound**. Người gọi có thể ở bất kỳ đâu, dùng thiết bị và phần mềm mà ta không quản lý. Boundary cần xác thực, phân quyền, giới hạn tốc độ, bảo vệ request và kiểm soát dữ liệu ra vào.

Một ví dụ khác: Payments Service gọi API thanh toán do tổ chức ngoài cung cấp qua HTTPS. Traffic đi **ra khỏi boundary** nên được xem là egress. Dù nó bắt nguồn từ service nội bộ, destination bên ngoài vẫn có yêu cầu trust, secret, timeout, idempotency và giám sát riêng.

### 2.2. East–west: giữa các workload hoặc service

~~~text
Ordering Service ---> Inventory Service
        |
        +-----------> Pricing Service
        |
        +-----------> Payment Service
        |
        +-----------> Message Broker
~~~

Đó là lưu lượng **east–west** nếu các thành phần nằm trong môi trường service được quản lý theo cùng một mô hình nội bộ. Giao thức có thể là HTTP/JSON, gRPC, TCP, AMQP, Kafka protocol hoặc kết nối database.

East–west không nhất thiết nằm trong một máy. Nó có thể chạy qua nhiều node, availability zone, VPC hoặc cluster nếu topology và trust policy cho phép. Khi vượt qua nhiều vùng quản trị, phải ghi rõ các trust boundary bổ sung.

### 2.3. Ingress, egress và góc nhìn tương đối

**Ingress** có nghĩa là traffic đi vào boundary đang xét. Trong Kubernetes, Ingress còn là tên một tài nguyên khai báo quy tắc HTTP/HTTPS route đến Service; hai nghĩa liên quan nhưng không hoàn toàn đồng nhất.

**Egress** có nghĩa là traffic đi ra khỏi boundary đang xét. Có thể có egress từ một pod đến database nội bộ, hoặc từ toàn cluster ra Internet; phân loại cụ thể tùy boundary được chọn.

Ví dụ một request từ namespace shop đến namespace finance là nội bộ ở cấp cluster nhưng đi qua boundary tổ chức/namespace giữa hai nhóm. Vì thế luôn hỏi “bên ngoài của cái gì?” thay vì chỉ gán nhãn public hoặc private.

## 3. Bảng phân biệt nhanh

| Tiêu chí | Client bên ngoài vào | Giao tiếp nội bộ |
| --- | --- | --- |
| Caller thường gặp | Browser, mobile, đối tác, public API client | Service, job, worker, internal platform |
| Điểm vào | Public domain, Edge, Ingress, API Gateway | Internal DNS, Service Discovery, service VIP, mesh |
| Mức độ kiểm soát caller | Hạn chế, client có thể không đáng tin | Do tổ chức quản lý nhưng vẫn có thể bị xâm nhập |
| Danh tính | User token, session, API key, client credentials | Workload identity, mTLS, service token, delegated user context |
| Quyền truy cập | User/tenant/resource/operation | Service-to-service permissions và domain authorization |
| Rate limit | Theo IP, API key, user, tenant, endpoint | Theo caller service, concurrency và dependency quota |
| Khả năng phục hồi | Public timeout/response, idempotency, UX | Deadline, retry budget, circuit breaker, bulkhead |
| Quan sát | Edge request rate, WAF, auth, 4xx/5xx, p95 | RPC metrics, dependency spans, broker lag, connection pool |
| Rủi ro chính | Abuse, lộ dữ liệu, bypass, brute force | Lateral movement, lỗi lan truyền, phụ thuộc vòng |
| Thay đổi hợp đồng | Phải hỗ trợ client/đối tác nhiều phiên bản | Tương thích giữa producer/consumer triển khai độc lập |

Bảng nêu khác biệt điển hình, không phải quy tắc cứng. Một đối tác có thể dùng mTLS với public API, và một service nội bộ vẫn cần user authorization để đọc đơn hàng cụ thể.

## 4. Sơ đồ tổng quan

~~~mermaid
flowchart TB
    U[Browser / Mobile / Partner] --> E[Public DNS / CDN / WAF / LB]
    E --> G[API Gateway / BFF]
    G --> O[Ordering Service]
    G --> C[Catalog Service]
    O --> I[Inventory Service]
    O --> P[Payment Service]
    O --> B[(Message Broker)]
    B --> N[Notifications Worker]
    P --> X[Egress Proxy / Egress Policy]
    X --> PSP[External Payment Provider]
~~~

Trong sơ đồ:

- U → E → G là north–south inbound.
- G → O/C và O → I/P/B là các request hoặc thông điệp bên trong khu vực backend.
- B → N là event delivery giữa broker và consumer.
- P → X → PSP là north–south outbound.

Gateway thường chỉ là một phần của đường đi. Nó **không tự thay thế** mọi bảo vệ ở các service phía sau, cũng không tự quyết định các bất biến nghiệp vụ như đơn được hủy hay khoản tiền phải hoàn.

## 5. Theo dõi request đặt hàng

Giả sử khách đặt ORD-1001:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Customer
    participant G as Public Gateway
    participant O as Ordering
    participant I as Inventory
    participant P as Payments
    participant X as External PSP

    U->>G: HTTPS POST /orders
    G->>G: Verify credential + route + rate limit
    G->>O: Internal createOrder
    O->>O: Verify resource authorization
    O->>O: Persist Order pending
    O->>I: ReserveStock(requestId, orderId)
    I-->>O: Reservation result
    O->>P: StartPayment(operationId, orderId)
    P->>X: HTTPS payment request
    X-->>P: Provider result or timeout
    P-->>O: Payment state or pending
    O-->>G: Order response
    G-->>U: HTTP response
~~~

Điểm khác nhau giữa các hop:

1. **User → Gateway** cần client authentication và public API policy.
2. **Gateway → Ordering** cần trust chain: backend phải biết caller được phép chuyển tiếp request, không tin header do người ngoài tự đặt.
3. **Ordering → Inventory** là giao tiếp giữa workload identity, cần deadline, idempotency và quyền ReserveStock.
4. **Payments → Provider** cần xác minh TLS, giữ bí mật provider credential, dùng idempotency key và đối soát nếu không rõ kết quả.
5. **Provider → Webhook handler** sau đó là một north–south inbound khác, phải xác thực webhook độc lập với session browser.

Trong thực tế luồng thanh toán có thể bất đồng bộ, trả 202 Accepted và xử lý bằng Saga; sơ đồ này chỉ minh họa boundary, không yêu cầu giữ HTTP request mở đến khi PSP trả kết quả cuối.

## 6. Public endpoint không phải địa chỉ của pod

Ví dụ:

~~~text
External:
https://api.shop.example/orders

Internal:
http://order-service.shop.svc.cluster.local:8080
~~~

Địa chỉ công khai có thể đi đến Gateway rồi mới đến một hoặc nhiều instance Order. Địa chỉ nội bộ có thể do Kubernetes Service cung cấp, chuyển đến các pod Order đã ready. Đây là **hai hợp đồng mạng** khác nhau dù cùng phục vụ nghiệp vụ đặt hàng.

Tên cluster.local không phải firewall. Nếu một pod khác có quyền mạng đến Order Service, nó có thể thử gọi API; cần xác thực workload và quyền ở tầng ứng dụng.

Ngược lại, một hostname trông như internal-api.example.com vẫn có thể trở thành public nếu DNS, Load Balancer hoặc firewall cấu hình sai. Không suy ra khả năng truy cập chỉ từ tên miền.

### Tại sao không dùng Pod IP cứng?

Pod có thể restart, reschedule, rolling deploy hoặc scale. IP và số instance thay đổi trong khi tên dịch vụ logic cần ổn định. Service Discovery và internal load balancing che giấu danh sách endpoint khỏi consumer, không buộc Ordering cập nhật IP của từng pod Inventory.

## 7. DNS, Load Balancer, Ingress, Gateway khác nhau ở đâu?

### DNS

DNS ánh xạ tên sang địa chỉ hoặc endpoint. Public DNS và internal DNS có phạm vi và điều kiện phân giải khác nhau. DNS **không tự xác thực** người dùng hoặc quyết định có quyền gọi POST /orders.

### Load Balancer

LB phân phối connection hoặc HTTP request đến backend sẵn sàng. LB có thể là tầng 4/TCP hoặc tầng 7/HTTP; khả năng route, TLS termination và health check tùy loại.

### Kubernetes Ingress và Ingress Controller

Ingress resource khai báo host/path HTTP/HTTPS đến Kubernetes Service. Ingress Controller là implementation thực thi các quy tắc. Chỉ có file Ingress nhưng không có controller phù hợp thường chưa đủ để có đường vào.

### API Gateway

Gateway là một vai trò kiến trúc ở public/API boundary, có thể cung cấp authentication, quotas, rate limiting, request validation, routing, logging, transformation, versioning, TLS policy và tích hợp kiểm soát lạm dụng. Không phải Gateway nào cũng hỗ trợ tất cả chức năng.

### Backend for Frontend (BFF)

BFF tạo interface phù hợp nhu cầu web/mobile, ví dụ một endpoint checkout lấy thông tin từ Catalog, Pricing và Ordering. BFF có thể đứng phía sau hoặc đóng vai trò Gateway. Đừng đặt business state xuyên dịch vụ ở một BFF chỉ để thuận tiện.

### Service Discovery / Kubernetes Service

Discovery cho biết hiện có những backend nào của một dịch vụ logic. Kubernetes Service có thể cung cấp tên DNS ổn định và chọn pod qua selector/EndpointSlice. Một Kubernetes Service không đồng nghĩa một Microservice nghiệp vụ; một service logic có thể có nhiều Deployment hoặc đối tượng Service.

### Service Mesh

Mesh có thể cung cấp data plane và policy cho traffic nội bộ: mTLS, workload identity, retries, routing, telemetry và authorization tùy sản phẩm. Mesh tập trung nhiều vào east–west nhưng cũng có thể có ingress/egress gateway. Nó không thay thế domain authorization.

### Egress Gateway

Được dùng để quản lý traffic từ workload đến external destination: xác định đích được phép, quan sát, cấu hình proxy/TLS và chính sách truy cập. Không bắt buộc mọi hệ thống phải dùng nhưng hữu ích khi có nhiều nhà cung cấp ngoài tổ chức.

## 8. North–south routing: host, path và version

Một public gateway có thể định tuyến:

~~~text
api.shop.example/api/orders/*   -> Ordering backend
api.shop.example/api/products/* -> Catalog backend
admin.shop.example/*            -> Admin boundary
hooks.shop.example/payments/*   -> Payment webhook handler
~~~

Cần lưu ý:

- Admin route phải có chính sách auth và network thích hợp; tên admin không làm nó an toàn.
- Webhook của provider có cách xác thực khác browser token.
- Route theo version cần giữ public contract tương thích với client cũ.
- Header do browser tự gửi không phải chứng cứ đủ cho routing đặc quyền.
- Gateway nên chuẩn hóa lỗi công khai nhưng không đưa stack trace, service hostname, token hoặc thông tin nội bộ vào response.

Không nên để mọi internal debug endpoint được công khai bằng cách thêm một rule tiện dụng. Một route bất ngờ có thể bypass chính sách auth hoặc rate limit áp ở Gateway chính.

## 9. East–west routing và internal Load Balancing

Một service nội bộ có thể gọi:

~~~text
inventory-service.shop.svc.cluster.local
payments-service.shop.svc.cluster.local
~~~

Resolver, Service, proxy hoặc client load balancer sẽ chọn backend. Có hai cách phổ biến:

- **Server-side balancing:** client gọi một proxy, Service VIP hoặc LB ổn định; tầng mạng chọn instance.
- **Client-side balancing:** client lấy danh sách endpoint từ discovery và áp chính sách như round-robin, tùy thư viện/hạ tầng.
- **Mesh balancing:** một proxy/data plane được quản lý có thể định tuyến dựa trên chính sách và endpoint health.

Đừng mặc định một hostname tự bảo đảm request được chia đều. gRPC dùng HTTP/2 multiplexed streams trên kết nối dài; nếu kết nối đó được gắn với một backend qua một số cơ chế LB, việc tăng pod không tự chia lưu lượng cân bằng. Cần xem connection distribution và policy thực tế.

### Readiness khác liveness

- **Readiness:** backend đã sẵn sàng nhận request mới hay chưa.
- **Liveness:** process có đang ở tình trạng phải restart hay không.
- **Startup:** cho app khởi động chậm thời gian hợp lý trước khi áp kiểm tra sống.

Khi một instance bị lỗi, load balancer có thể đưa request mới đến instance khác. Nhưng một request đã commit trên instance lỗi vẫn có thể mất phản hồi; correctness phải dựa trên transaction, idempotency và reconciliation.

## 10. HTTP, gRPC và messaging đều có thể là east–west

| Protocol/cách tích hợp | Ví dụ | Điều cần quan tâm |
| --- | --- | --- |
| HTTP/JSON | Ordering GET Pricing Quote | Contract, timeout, auth, version |
| gRPC | Ordering gọi Inventory.ReserveStock | Protobuf, deadline, workload identity, stream lifecycle |
| Message broker | OrderPlaced được Notifications tiêu thụ | Message key, redelivery, offset, idempotency |
| Database connection | Order Service truy vấn Order DB | Network, credentials, locks, resource ownership |
| Cache | Service kết nối Redis | TTL, HA, data privacy, consistency |
| Object storage | Service lấy hóa đơn | Private endpoint hoặc outbound boundary |
| Provider HTTPS | Payments gọi PSP | Egress policy, secret, timeout, reconciliation |

Giao thức **không quyết định** north–south/east–west. Một API HTTP giữa hai service là east–west; một giao diện gRPC được phép phục vụ đối tác ngoài cluster đi qua gateway có thể là north–south.

Một Kafka broker có thể ở mạng khác hoặc cloud khác: phải phân loại theo topology và trust boundary thực tế, không chỉ vì nó được gọi là “internal broker”.

## 11. Bảo mật public traffic

Khi một API được mở ra ngoài, client có thể cố ý gửi dữ liệu sai, vượt hạn mức hoặc cố đọc tài nguyên của người khác. Các lớp bảo vệ thường bao gồm:

1. TLS cho kết nối public và quản lý chứng chỉ.
2. Xác thực user/session/token hoặc API client identity.
3. Phân quyền user, role, tenant và từng resource.
4. Rate limit/quota theo tài khoản, API key, endpoint và rủi ro.
5. Giới hạn kích thước request, số kết nối và timeout.
6. Input validation, content type, JSON schema và giới hạn field.
7. Chính sách CORS dành cho browser; CORS không phải authorization.
8. CSRF protection nếu dùng cookie auth cho các thao tác có tác động.
9. WAF/bot protection khi threat model yêu cầu.
10. Logging/metrics/tracing có ẩn credential và dữ liệu nhạy cảm.

Ví dụ POST /orders có JWT hợp lệ vẫn chưa đủ. Ordering cần kiểm tra user được phép đặt hàng cho customer/tenant tương ứng, giữ giá đã chốt và chống retry tạo trùng.

**Gateway xác thực không đồng nghĩa domain service được bỏ kiểm tra quyền.** Nếu có đường internal gọi vào service hoặc một caller bị xâm nhập, việc chỉ dựa vào một header X-User-Id do người gọi tự điền có thể dẫn đến lộ dữ liệu.

## 12. Bảo mật east–west và nguyên tắc không tin mặc định

“Cùng một VPC” hoặc “cùng Kubernetes cluster” không chứng minh caller được phép gọi mọi operation. Workload có thể bị khai thác, cấu hình sai hoặc bị dùng để thực hiện lateral movement.

Cần xét các lớp:

- **Network segmentation:** NetworkPolicy, security group, firewall/ACL, service endpoints.
- **Workload identity:** ServiceAccount, workload certificate, service token có thể xác minh.
- **Transport security:** TLS hoặc mTLS khi phù hợp.
- **Service authorization:** chỉ Ordering được gọi ReserveStock, chỉ role phù hợp được refund.
- **Domain authorization:** Order thuộc tenant/user nào, thao tác có hợp lệ trong trạng thái hiện tại không.
- **Secret isolation:** mỗi workload có quyền riêng, không chia một API token quyền cao cho mọi service.
- **Audit:** ai gọi thao tác nhạy cảm và kết quả ra sao.
- **Observability:** phát hiện internal auth failure, traffic bất thường, lateral movement.

### Network authentication và business authorization khác nhau

~~~text
Network:  Ordering có được kết nối TCP 8443 đến Payments?
Identity: Caller có đúng là workload ordering-service?
Service policy: Ordering có quyền gọi CreatePayment?
Domain: Khoản tiền này có hợp lệ và được phép thực hiện không?
~~~

Bốn điều kiện này cần được đánh giá riêng. mTLS giúp chứng thực workload (nếu cấu hình đúng), nhưng không tự giải thích liệu orderId thuộc tenant nào.

## 13. Truyền danh tính người dùng qua các service

Khi Gateway nhận token của user CUS-17, ứng dụng có hai loại identity quan trọng:

- **End-user identity:** user/tenant/role được xác minh ở boundary.
- **Workload identity:** service đang thực hiện lời gọi, ví dụ api-gateway hoặc ordering-service.

Một service gọi service khác “thay mặt người dùng” phải có phương án **delegation** tin cậy: token exchange, signed claims, token propagation có audience/scope phù hợp hoặc chính sách của platform. Không mặc định mọi dịch vụ đều có quyền dùng token browser như một chìa khóa chung.

Ví dụ:

~~~text
User CUS-17 -> Gateway -> Ordering -> Payments

Gateway xác minh user token.
Ordering xác minh người dùng được phép tạo đơn.
Payments xác minh service caller có quyền tạo payment.
Payments xác nhận payment reference thuộc thao tác hợp lệ.
~~~

Header do client tự đặt như X-User-Id hoặc X-Tenant-Id chỉ là dữ liệu input nếu không có cơ chế xác thực và chống giả mạo rõ. Khi gateway chuyển verified context, cần sanitize header từ ngoài và có trust boundary giữa gateway và backend.

## 14. Egress: chiều đi ra bên thứ ba

Payment Service gọi PSP, Shipping Service gọi hãng vận chuyển, Notifications gọi email provider. Các cuộc gọi này thường ra ngoài vùng hạ tầng tự quản lý.

~~~mermaid
flowchart LR
    P[Payments] --> E[Egress policy / proxy]
    E --> X[PSP API]
    S[Shipping] --> E
    E --> C[Carrier API]
    N[Notifications] --> E
    E --> M[Email API]
~~~

Điểm cần kiểm soát:

- Destination allowlist theo domain/IP/port khi có thể.
- TLS validation và bảo vệ certificate/trust store.
- Provider secrets, API keys, token rotation, scopes.
- Provider quota, rate limit và billing.
- Timeout, retry policy, circuit breaker, backoff.
- Idempotency đối với charge/refund và các lệnh có side effect.
- Reconciliation khi provider đã xử lý nhưng client mất phản hồi.
- Data minimization và chính sách chia sẻ PII.
- Logging, metrics, cảnh báo egress bất thường.

### SSRF và destination không tin cậy

Nếu một service được phép tải URL do client chỉ định, attacker có thể cố gửi URL trỏ vào internal metadata endpoint, admin API hoặc dịch vụ khác; đây là nguy cơ SSRF. Cần allowlist đích được kiểm chứng, kiểm soát redirect/DNS resolution phù hợp, hạn chế egress và quyền truy cập tối thiểu. Một regex đơn giản kiểm tra hostname không đủ bảo đảm.

## 15. Webhook inbound: khác browser request

Thanh toán thường có cả hai hướng:

~~~text
Payments -> PSP HTTPS API          : outbound egress
PSP -> Webhook Gateway -> Payments : inbound ingress
~~~

Webhook đến từ provider ngoài tổ chức, **không mang session browser** của khách, và phải được xử lý với mô hình tin cậy riêng:

1. Công bố endpoint webhook phù hợp với provider.
2. Xác minh chữ ký, timestamp, secret/certificate hoặc phương pháp provider quy định.
3. Phòng replay và dùng idempotency theo eventId/provider transaction ID.
4. Lưu payment attempt/correlation vào nguồn dữ liệu bền vững.
5. Xác minh kết quả provider trước khi chuyển business state.
6. Không ghi credential hoặc dữ liệu thanh toán nhạy cảm vào logs.
7. Phản hồi acknowledgment phù hợp, có cơ chế retry/reconciliation.

Khi khách đóng browser hoặc session hết hạn, webhook vẫn phải cập nhật được Payment/Order theo luật nghiệp vụ. Điều đó là bằng chứng business state không được phụ thuộc vào browser session.

## 16. Timeout và deadline: đừng nhân thời gian chờ qua nhiều hop

Một chuỗi đồng bộ:

~~~text
Browser -> Gateway -> Ordering -> Inventory -> Payments
~~~

Nếu browser chỉ chờ 2 giây nhưng gateway chờ Ordering 5 giây và Ordering chờ mỗi dependency 10 giây, rất nhiều công việc có thể tiếp tục sau khi client đã bỏ cuộc.

Các nguyên tắc:

- Có ngân sách end-to-end theo public API SLO.
- Mỗi hop chỉ dùng một phần thời gian còn lại, tính thêm network/queue/processing.
- Truyền deadline phù hợp nếu framework hỗ trợ.
- Hủy công việc không còn cần thiết khi an toàn, nhưng không coi cancellation là rollback.
- Với workflow kéo dài, dùng trạng thái PENDING/Saga thay vì mở HTTP request quá lâu.
- Nếu thao tác đã commit nhưng response bị mất, phải có khả năng tra cứu/đối soát.

Ví dụ minh họa:

~~~text
Public request budget: 2000 ms
Gateway validation:   ~100 ms
Ordering DB work:     ~150 ms
Inventory RPC budget: 400 ms
Remaining time:       dành cho logic khác, queue/network/response
External payment:     chuyển async nếu không thể xác nhận an toàn trong budget
~~~

Đây là số giả định để giải thích phân bổ thời gian, không phải giá trị production mặc định.

### 504 có nghĩa gì?

Gateway trả HTTP 504 vì upstream không phản hồi đúng hạn **không chứng minh** Order chưa được tạo hay Payment chưa được thực hiện. Retry POST /orders phải dùng idempotency key ổn định. Với PSP, một timeout phải được xem là **kết quả chưa rõ** đến khi kiểm tra nguồn tài chính.

## 17. Retry policy khác nhau theo operation

### GET và thao tác đọc

Một GET idempotent có thể được retry có giới hạn sau một số lỗi tạm, với deadline tổng, backoff và jitter. Tuy nhiên vẫn phải kiểm tra lỗi bảo mật, validation và trạng thái nghiệp vụ.

### Command có side effect

Với CreateOrder, ReserveStock, ChargePayment và RefundPayment, retry có thể gây trùng side effect. Cần:

- Stable idempotency key theo operation.
- Scope của key (tenant, caller, loại thao tác) và fingerprint payload.
- Atomic persistence/unique constraint để nhiều instance không cùng thực thi hai lần.
- Khả năng query kết quả sau timeout.
- Reconciliation và compensation khi operation đã xảy ra.
- Chính sách expiry key phù hợp vòng đời retry.

### Retry storm

Nếu gateway retry 3 lần, Ordering retry 3 lần và Inventory client retry 3 lần, số attempt có thể nhân lên ngoài dự kiến. Hãy phân công tầng chịu trách nhiệm retry, dùng tổng retry budget, circuit breaker/concurrency limit và không retry lỗi nghiệp vụ như thiếu hàng.

## 18. Rate limiting: điều gì khác giữa edge và internal?

### Public rate limiting

Một API Gateway thường giới hạn theo API key, user, tenant, route, device hoặc IP khi thích hợp. Ví dụ Login cần chính sách chống brute force khác GET catalog. Chỉ dùng IP có thể chặn oan người dùng chia sẻ NAT hoặc không hiệu quả với attack phân tán.

### Internal throttling

Giữa services, giới hạn theo caller/workload, concurrent RPC, queue length, downstream quota và retry budget có thể quan trọng hơn mức IP. Ví dụ Payments chỉ có một mức năng lực xử lý song song; Ordering phải backpressure thay vì retry ồ ạt.

Rate limiting bảo vệ tài nguyên nhưng **không thay thế** domain validation, idempotency hoặc authorization.

## 19. Thiết kế public Gateway thay vì mở từng Microservice

Nếu 12 domain services đều có public LoadBalancer riêng, tổ chức phải quản lý 12 đường public, dẫn đến không nhất quán auth, quota, logging, TLS và deprecation.

Một hướng thường dùng:

~~~text
Public Clients
      |
      v
API Gateway / BFF
      |
      +----> Ordering (internal)
      +----> Catalog  (internal)
      +----> Identity (internal)

Ordering -> Inventory (internal discovery)
Ordering -> Payments  (internal discovery)
~~~

Gateway chịu trách nhiệm public API boundary. Internal services có endpoint theo hợp đồng riêng, không buộc client thấy pod IP hoặc service DNS.

Điều này **không** có nghĩa mọi request giữa services phải vòng qua public API Gateway. Gọi Inventory từ Ordering bằng public hostname rồi quay vào cluster có thể tạo thêm latency, dependency edge, chính sách sai và chi phí không cần thiết. Chọn đường east–west phù hợp.

Ngoại lệ: một service có thể có public API trực tiếp vì lý do đối tác/streaming/latency, nhưng boundary đó phải có policy và owner đầy đủ. Không coi “ít gateway hơn” là lý do bỏ bảo mật.

## 20. Ví dụ Kubernetes: private Order Service và public Gateway

Manifest sau minh họa một Ordering Service nội bộ bằng ClusterIP, một Gateway Service cũng dùng ClusterIP nhưng được một Ingress public route đến. Đây là ví dụ, không phải manifest production đầy đủ.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-app
          image: registry.example.com/order-service:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: order-service
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: order-service
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: api-gateway
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: api-gateway
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: public-api
  namespace: shop
spec:
  tls:
    - hosts:
        - api.shop.example
      secretName: api-shop-tls
  rules:
    - host: api.shop.example
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-gateway
                port:
                  number: 80
~~~

Điều kiện để ví dụ có tác dụng: tồn tại Deployment api-gateway với label phù hợp; Ingress controller được cài và cấu hình; DNS, TLS Secret, gateway routes, readiness endpoint và bảo mật thực tế đều hoạt động. Namespace shop cần tồn tại. Domain và image là placeholder.

### Điều cần ghi nhớ

- order-service không có public Ingress trong manifest.
- api-gateway được expose qua Ingress nhưng Kubernetes Service của nó vẫn là ClusterIP.
- Gateway có thể gọi order-service.shop.svc.cluster.local.
- ClusterIP không đủ bảo đảm chỉ Gateway được gọi Order. Cần policy mạng và authorization.
- Một Ingress resource cần Ingress controller thực thi và policy nhất quán.

### Các lệnh quan sát

~~~bash
kubectl -n shop get deployments
kubectl -n shop get services
kubectl -n shop get ingress
kubectl -n shop get pods -l app=order-service -o wide
kubectl -n shop get endpointslices -l kubernetes.io/service-name=order-service
~~~

Dùng các lệnh trên trong môi trường được phép truy cập; không mặc định có quyền thao tác với production.

## 21. NetworkPolicy: chỉ cho caller được phép vào Order

Giả sử Gateway là workload cùng namespace có label app=api-gateway. Policy sau minh họa cách giới hạn ingress tới pod Order ở cổng ứng dụng:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-allow-gateway
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: order-service
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

Ý nghĩa:

1. Chọn các pod app=order-service.
2. Thiết lập chính sách ingress cho nhóm pod đã chọn.
3. Cho phép nguồn là pod mang app=api-gateway **trong cùng namespace**.
4. Giới hạn đến TCP 8080 theo rule.

Lưu ý:

- Network plugin/CNI phải hỗ trợ NetworkPolicy.
- Một pod có thể chịu nhiều NetworkPolicy, và tập rule cho phép có tính cộng dồn; phải xem tất cả policy.
- Policy này chưa giới hạn egress.
- Pod label không phải credential bảo mật nếu người dùng được quyền tạo/sửa pod tùy ý với label đó.
- Nếu các service khác cần gọi Order, chúng cần rule/đường truy cập phù hợp.
- Cấu hình default deny cẩu thả có thể cắt DNS, health probes, monitoring hoặc kết nối thiết yếu.
- Netpol không kiểm tra quyền xem ORD-1001 hay gọi endpoint admin; đó là nhiệm vụ auth ở tầng service/domain.

## 22. Quan sát north–south và east–west theo từng lớp

Một request checkout p95 tăng có thể do Gateway, Ordering, Inventory, DB hoặc PSP. Chỉ nhìn một biểu đồ edge latency chưa đủ để tìm nguyên nhân.

| Lớp | Tín hiệu | Câu hỏi |
| --- | --- | --- |
| Public Edge | request rate, p95/p99, HTTP 4xx/5xx, WAF/429 | Client gặp vấn đề từ đâu? |
| Gateway/BFF | route latency, auth failures, backend 502/503/504 | Routing hay backend gây lỗi? |
| Domain Services | method latency, error rate, concurrency | Service nào chậm hoặc quá tải? |
| East–west RPC | peer, deadline, retry, circuit breaker | Dependency đang lỗi hay client retry quá nhiều? |
| Broker | consumer lag, redelivery, DLQ, publish error | Event bị kẹt hoặc trùng? |
| Database | connection pool, locks, query latency | Nút nghẽn nằm ở nguồn dữ liệu? |
| Egress | provider HTTP/TLS/DNS failure, timeout | Bên thứ ba có sẵn sàng không? |
| Business Workflow | order PENDING, payment UNKNOWN, compensation | Nghiệp vụ đã hoàn tất hay chỉ network call xong? |

### Distributed Tracing

Truyền trace context từ public gateway qua các internal RPC. Mỗi hop ghi span với service.name, peer, operation và duration. Với event/Saga kéo dài, correlationId/orderId có thể nối các trace khác nhau.

Đừng dùng traceId làm idempotency key. Và không đưa JWT, session cookie, API secret hoặc payment token vào trace attributes hay logs.

### Metrics label

Các label thường phù hợp: service, method, status, environment, caller-service. Tránh gắn orderId, userId hoặc requestId làm metric label có cardinality rất cao; các ID này phù hợp hơn trong log/trace có kiểm soát.

## 23. Lỗi lan truyền và giới hạn chịu lỗi

Một hệ thống có nhiều Order replicas vẫn có thể lỗi do phụ thuộc chung:

- Public Gateway không sẵn sàng.
- DNS/Resolver sai hoặc registry mất kết nối.
- Internal LB/gRPC connection không cân bằng.
- Database đạt giới hạn connection.
- Inventory bị quá tải và tạo cascade timeout.
- Provider ngoài trả 429 hoặc 503.
- Mesh certificate/identity hết hạn.
- NetworkPolicy mới chặn một số traffic cần thiết.

### Một instance bị dừng

Khi Order A chết, load balancer có thể loại A khỏi tập ready; Order B/C phục vụ request mới. Tuy nhiên request đã xử lý trên A có thể đã commit trước khi mất phản hồi. Retry cần idempotency và tra cứu kết quả.

### Inventory unavailable

Ordering không tự được phép bỏ qua reservation nếu nghiệp vụ yêu cầu giữ tồn kho chắc chắn. Có thể chọn trả PENDING, từ chối checkout hoặc mô hình backorder/preorder nếu quy tắc cho phép. Circuit breaker là công cụ bảo vệ tài nguyên, không quyết định được chính sách nghiệp vụ.

### Payment Provider timeout

Nếu PSP đã thu tiền nhưng response mất, Payments cần tra provider transaction ID hoặc dùng reconciliation. Không biến egress timeout thành PaymentFailed cuối cùng khi chưa xác minh.

## 24. Nhiều VPC, cluster và region

Khi các service chạy ở nhiều cluster, “internal” trở nên tương đối:

~~~text
Region A / Cluster A: Ordering, Inventory
Region B / Cluster B: Catalog, Reporting
External: Browser -> Global Gateway -> Region A
External: Payments -> PSP
~~~

Cần xác định:

- Cross-cluster traffic đi private link, mesh federation hay public endpoint?
- Workload identity/certificate có được chấp nhận giữa cluster không?
- Service Discovery và DNS failover chọn backend thế nào?
- Quyền của service gọi từ vùng A sang vùng B có được giới hạn?
- Data residency/tenant isolation có cho phép chuyển thông tin đó không?
- Cross-region latency và split-brain ảnh hưởng transaction thế nào?
- Nếu failover, trạng thái idempotency và Order có còn nhất quán không?

Một đường private network không tự tạo đủ authorization. Người thiết kế phải ghi rõ network và trust boundary thực tế.

## 25. Những lỗi thiết kế thường gặp

**1. Công khai mọi service bằng LoadBalancer.** Tạo quá nhiều cổng public, dễ lệch policy và tăng attack surface. Giới hạn các entry points theo mục đích.

**2. Gọi nội bộ qua public hostname không lý do.** Tăng độ trễ, phụ thuộc edge và rủi ro policy. Dùng internal discovery khi thích hợp.

**3. Tin header X-User-Id từ browser.** Bất kỳ caller nào có thể giả mạo. Xác minh credential ở boundary và bảo vệ user context khi chuyển tiếp.

**4. Chỉ kiểm tra auth tại Gateway.** Một caller nội bộ khác có thể bypass. Backend vẫn thực thi authorization theo resource và thao tác.

**5. Xem private DNS là firewall.** Tên DNS chỉ giúp tìm endpoint; bảo vệ bằng network segmentation, identity và domain policy.

**6. Mọi service dùng một shared secret.** Workload bị xâm nhập có thể giả mạo các service khác. Dùng least-privilege credentials và rotation.

**7. Egress unrestricted.** Tăng nguy cơ SSRF và exfiltration. Kiểm soát destination và audit phù hợp.

**8. Retry POST sau 504 mà không có idempotency.** Có thể tạo đơn hoặc khoản thu trùng.

**9. Chỉ quan sát request public.** Không thấy bottleneck east–west và provider. Cần tracing/metrics dependency.

**10. Coi một endpoint internal là không cần versioning.** Consumer internal cũng có thể triển khai không cùng thời điểm.

**11. Gộp authn và authz.** Xác thực workload không chứng minh quyền thao tác lên mọi đơn/tenant.

**12. Coi browser cancellation là rollback.** Transaction đã commit và provider side effect không tự biến mất khi kết nối bị hủy.

## 26. Quy trình thiết kế từng đường traffic

Dùng bảng quyết định sau cho mỗi cặp caller–callee:

| Câu hỏi | Ví dụ cần điền |
| --- | --- |
| Nguồn gọi | Browser, Gateway, Ordering, Provider |
| Đích | Public API, Inventory, PSP |
| Boundary | North–south ingress, east–west, north–south egress |
| Địa chỉ | api.shop.example, inventory-service DNS |
| Route | Edge LB/Ingress, Service Discovery, mesh/egress |
| Authentication | User token, workload identity, provider signature |
| Authorization | Tenant, operation, resource, service caller |
| Dữ liệu | Order reference, PII, payment state |
| Reliability | Deadline, retry, idempotency, reconciliation |
| Capacity | Quota, concurrency, rate limit, backpressure |
| Observability | Logs, metrics, traces, owner/on-call |
| Change control | API version, rollout, consumer compatibility |

Một mẫu mô tả flow:

~~~yaml
name: ordering-to-inventory
classification: east-west
source: ordering-service
target: inventory-service.shop.svc.cluster.local
protocol: grpc-or-http
authentication: workload-identity
authorization: reserve-stock
deadline: within-checkout-budget
idempotency: reservation-operation-id
failureHandling: pending-or-reject-by-business-policy
observability: trace-and-rpc-metrics
owner: ordering-and-inventory-teams
~~~

YAML ở đây chỉ là tài liệu thiết kế minh họa, không phải cấu hình thực thi cho một sản phẩm cụ thể.

## 27. Bài tập tình huống

### Bài A — Phân loại đường mạng

Cho các endpoint:

~~~text
https://api.shop.example/orders
http://inventory-service.shop.svc.cluster.local:8080
https://psp.example/charge
http://redis.shop.svc.cluster.local:6379
https://admin.shop.example/reports
~~~

Hãy phân loại public API, internal service, external provider, internal infrastructure và admin boundary. Vì sao nhìn hostname một mình chưa đủ kết luận một địa chỉ thật sự public hay private?

### Bài B — Một Gateway bị bypass

Một caller đi thẳng vào Order Service, bỏ qua Gateway và đọc được đơn của tenant khác. Hãy đề xuất các lớp chặn: network exposure, workload auth, domain authorization, logging và route inventory.

### Bài C — 504 sau khi Order commit

Gateway timeout; Ordering đã ghi ORD-1001. User gửi POST /orders lần nữa. Thiết kế idempotency key, unique constraint, response và API tra cứu trạng thái.

### Bài D — Workload compromise

Notifications Service bị compromise và muốn gọi RefundPayment. Hãy nêu các lớp bảo vệ: network policy, caller identity, service authorization, domain operation checks và secret management.

### Bài E — Webhook đến sau khi logout

Browser đóng, session hết hạn, PSP gửi PaymentSucceeded. Mô tả endpoint inbound, signature verification, idempotent processing và cách Payment/Order business state được cập nhật không phụ thuộc browser.

### Bài F — gRPC traffic không đều

Inventory scale từ 1 lên 5 pod; một Order client dùng một HTTP/2 connection dài và traffic chủ yếu tới một pod. Giải thích nguyên nhân và vai trò của gRPC-aware LB/client-side discovery.

### Bài G — Cross-cluster

Cluster A gọi service ở cluster B qua private link. Có được bỏ mTLS, authz và audit vì “cùng công ty” không? Hãy phân tích threat model, identity và data isolation.

### Bài H — Egress chỉ cho PSP

Payment Service cần gọi một domain PSP. Hãy thiết kế kiểm soát destination, TLS validation, rotation credentials và xử lý DNS/redirect an toàn để hạn chế SSRF.

### Bài I — Latency tăng

Public p95 checkout tăng nhưng Gateway CPU bình thường. Traces cho thấy Inventory deadline và PSP timeout. Hãy chọn dashboard phân biệt edge, internal RPC và provider latency, rồi trình bày cách hạn chế cascade failure.

## 28. Câu hỏi tự kiểm tra

1. North–south và east–west phân biệt theo tiêu chí gì?
2. Một HTTP request từ Ordering đến Inventory trong cùng cluster thuộc loại nào?
3. Payments gọi PSP là ingress hay egress từ góc nhìn của hệ thống?
4. DNS có tự xác thực quyền của caller không?
5. Kubernetes Service ClusterIP có tự chặn tất cả pod khác không?
6. API Gateway khác BFF và domain service ở điểm nào?
7. Ingress resource có thể tự định tuyến nếu không có controller được cấu hình không?
8. Workload identity khác end-user identity ra sao?
9. mTLS có thay thế kiểm tra user được phép xem một Order không?
10. Vì sao NetworkPolicy không thay thế authorization?
11. Khi Gateway trả 504, vì sao không được kết luận Order chưa tạo?
12. Vì sao retry ở nhiều tầng có thể gây retry storm?
13. Có thể dùng gRPC nội bộ dù public API là HTTP/JSON không?
14. Khi tăng replica, vì sao gRPC trên connection dài có thể không chia đều traffic?
15. Webhook inbound khác request browser về identity và bảo mật thế nào?
16. Egress allowlist giúp giảm rủi ro gì?
17. CORS có phải cơ chế kiểm soát quyền xem dữ liệu không?
18. Khi gọi service giữa hai cluster, cần xác định thêm trust boundary nào?
19. Metrics/tracing nào giúp tìm bottleneck east–west?
20. Khi nào nên đưa workflow dài qua event/Saga thay vì chờ RPC đồng bộ?

## 29. Tổng kết

**North–south ingress** là traffic từ client hoặc đối tác bên ngoài qua boundary vào hệ thống; nó thường đi qua DNS, edge, Ingress và API Gateway và phải chịu public API policy. **East–west** là giao tiếp giữa các workload nội bộ, thường qua discovery, internal load balancing, RPC và messaging; nó vẫn cần network segmentation, workload identity, authorization và kiểm soát lỗi. **North–south egress** là chiều từ service ra bên thứ ba, cần destination policy, TLS, secret management, timeout và đối soát.

Đừng coi “internal” đồng nghĩa “trusted”, cũng đừng buộc mọi microservice gọi nhau qua public gateway. Hãy xác định nguồn–đích–boundary–hợp đồng cho từng đường đi, rồi chọn chính sách định tuyến, bảo mật và quan sát phù hợp. Thiết kế đó giúp một hệ thống Microservices mở rộng và chịu lỗi tốt mà vẫn bảo vệ tính đúng đắn của nghiệp vụ.
