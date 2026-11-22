# Tập trung xác thực, định tuyến và giới hạn lưu lượng tại API Gateway trong Microservices

## Mục tiêu học tập

Trong một hệ thống Microservices, các dịch vụ Order, Inventory, Payment, Catalog, Customer và Notification có thể chạy trên nhiều tiến trình, nhiều máy chủ, namespace hoặc cluster. Nếu mọi ứng dụng di động, trình duyệt và đối tác đều truy cập trực tiếp đến từng service, mỗi client phải biết địa chỉ, hợp đồng, cơ chế xác thực, quota, phiên bản API và cách xử lý lỗi của nhiều backend. Điều này làm tăng coupling, khó áp dụng chính sách nhất quán và mở rộng bề mặt tấn công.

**API Gateway (cổng API)** là một điểm vào logic cho những lời gọi API thuộc một phạm vi xác định. Gateway tiếp nhận request, xác minh các điều kiện ở biên, tìm upstream phù hợp, áp dụng chính sách traffic và chuyển request đến backend. Nó giúp tập trung các trách nhiệm **xuyên suốt** nhưng không nên thay thế quyền sở hữu logic nghiệp vụ của các microservice.

Bài học tập trung vào ba trách nhiệm:

1. **Tập trung xác thực (authentication ở biên):** Kiểm tra ai đang gọi, bằng chứng danh tính có hợp lệ không, token hay credential có phù hợp môi trường và API không.
2. **Định tuyến (routing):** Dựa vào hostname, đường dẫn, phương thức, header, phiên bản, tenant hoặc metadata được tin cậy để chọn service logic và endpoint chạy phù hợp.
3. **Giới hạn lưu lượng (rate limiting/traffic control):** Bảo vệ hệ thống trước lỗi sử dụng, khách hàng quá nhiều request, bot hoặc overload; duy trì công bằng và đáp ứng SLO trong khả năng hiện có.

Sau bài học, người học có thể:

- Phân biệt API Gateway với **load balancer, ingress/reverse proxy, WAF, service discovery và service mesh**.
- Vẽ đường đi một request qua **DNS/TLS → gateway → xác thực → route → upstream → response**.
- Giải thích **authentication, authorization, OAuth 2.0, OpenID Connect, JWT, API key, mTLS, identity propagation** và nơi nên thực thi từng lớp.
- Phân biệt kiểm tra token tập trung với **phân quyền dựa trên tài nguyên/thuộc tính nghiệp vụ** ở backend.
- Thiết kế routing theo host/path, version, canary, tenant và service discovery, hiểu nguy cơ lộ dịch vụ nội bộ hoặc route sai môi trường.
- Chọn giới hạn lưu lượng theo **IP, user, API key, tenant, route và global capacity**; giải thích token bucket, sliding window, concurrency limit, admission control và backpressure.
- Đọc và thiết kế phản hồi **401, 403, 404, 429, 503**, Retry-After và error contract không gây hiểu nhầm.
- Tổ chức gateway để không trở thành điểm nghẽn, điểm lỗi duy nhất hoặc nơi tích tụ logic nghiệp vụ.
- Viết test matrix cho route, xác thực, quota, failover, audit và quan sát SLO.
- Diễn đạt một quyết định kiến trúc bằng ADR với các trade-off giữa bảo mật, latency, vận hành và khả năng phát triển độc lập.

**Phạm vi:** Đây là bài trong nhóm **Cổng API** của Software Design / System Architecture / Microservices. Các ví dụ URL, mã định danh, request và cấu hình là minh họa cho nguyên tắc. Hợp đồng thực tế phụ thuộc kiến trúc, nhà cung cấp identity, chính sách bảo mật và công nghệ gateway đang dùng.

---

## 1. API Gateway giải quyết vấn đề gì?

Giả sử ứng dụng thương mại có sáu dịch vụ:

~~~text
Catalog Service      → thông tin và tìm kiếm sản phẩm
Order Service        → vòng đời đơn hàng
Inventory Service    → giữ hàng, tồn kho
Payment Service      → yêu cầu và kết quả thanh toán
Customer Service     → hồ sơ khách hàng
Notification Service → gửi thông báo
~~~

Nếu không có một điểm vào hợp lý, ứng dụng web có thể phải gọi trực tiếp sáu địa chỉ; mỗi địa chỉ cần CORS, TLS, auth, logging và error handling. Mobile client cũng phải biết thay đổi hạ tầng hoặc endpoint. Khi Inventory đổi từ IP A sang IP B, hoặc Order chuyển từ v1 sang v2, thay đổi dễ lan ra client.

Một lựa chọn phổ biến:

~~~mermaid
flowchart LR
    C["Web / Mobile / Partner"] --> E["DNS / TLS / Edge"]
    E --> G["API Gateway"]
    G -->|"/api/products"| CAT["Catalog"]
    G -->|"/api/orders"| ORD["Order"]
    G -->|"/api/customers"| CUS["Customer"]
    G -->|"/api/payments"| PAY["Payment"]
    ORD --> INV["Inventory"]
    ORD --> NOT["Notification"]
~~~

Gateway có thể cung cấp một giao diện công khai tương đối ổn định:

~~~text
https://api.example.test/api/products
https://api.example.test/api/orders
https://api.example.test/api/customers
https://api.example.test/api/payments
~~~

**Mấu chốt:** Client gọi một public contract; gateway chọn service logic và định tuyến qua cơ chế discovery/load balancing, thay vì client phải biết Pod IP hay tên máy của từng backend.

### 1.1. Những việc phù hợp để tập trung

- Kết thúc hoặc chuyển tiếp TLS theo trust model đã thiết kế.
- Xác minh thông tin danh tính ở biên: chữ ký token, issuer, audience, thời hạn, scheme.
- Chính sách sơ bộ: API key, scope mang tính API, denylist khi có nhu cầu.
- Định tuyến host/path/method sang service logic tương ứng.
- Giới hạn request rate, burst, payload size và một phần concurrent requests.
- Xác định request ID, correlation ID và phát metrics/tracing chung.
- Kiểm soát CORS, request/response headers theo chính sách.
- Áp đặt timeout, request size, connection/idle limits.
- Chuyển đổi đơn giản tại boundary khi có lý do rõ.
- Hỗ trợ canary/weighted rollout, API version migration.
- Một số cache cho **GET** an toàn theo cache contract.

### 1.2. Những việc không nên đưa hết vào gateway

- Quy tắc tính giá, giảm giá, thuế hoặc hoàn tiền;
- Quyết định đơn hàng nào được hủy;
- Kiểm tra tồn kho trong transaction thuộc Inventory;
- Quyền xem/sửa **một đơn cụ thể** dựa trên dữ liệu Order chưa có tại gateway;
- State machine saga, compensation hoặc reconciliation thanh toán;
- Ghi trực tiếp database của các domain service;
- Xử lý giao dịch tài chính chỉ bằng route/filter;
- Bản sao model nghiệp vụ và schema nội bộ của mọi service.

**Gateway nên là lớp chính sách và phân phối lưu lượng**, không phải “siêu service” sở hữu mọi nghiệp vụ.

## 2. Phân biệt Gateway, Ingress, LB, Reverse Proxy, WAF và Mesh

Các thuật ngữ dễ chồng lên nhau vì một sản phẩm có thể đảm nhận nhiều chức năng.

| Thành phần | Trách nhiệm nổi bật | Đặc điểm cần phân biệt |
|---|---|---|
| **API Gateway** | Public/API entry, auth, routing, quota, API policy | Thường quan tâm **contract API**, caller/tenant, endpoint và cross-cutting policies |
| **Reverse proxy** | Nhận request và chuyển tới upstream | Chức năng kỹ thuật cơ sở; có thể là thành phần của gateway |
| **Load balancer** | Phân phối traffic tới các instance | Có thể ở L4 hoặc L7, không nhất thiết hiểu danh tính user hay API quota |
| **Ingress** | Cơ chế cấu hình traffic đi vào cluster (tùy nền tảng) | Có thể hiện thực qua controller/proxy; không tự hàm ý đầy đủ API management |
| **WAF** | Kiểm tra/lọc mẫu tấn công ở lớp ứng dụng | Bổ sung phòng vệ, không tự quyết business authorization |
| **Service discovery** | Ánh xạ service logic tới endpoint đang phục vụ | Không tự xác minh user hay sở hữu API contract |
| **Service mesh** | Policy và traffic management giữa workload | Tập trung service-to-service; không thay public API gateway |
| **BFF (Backend For Frontend)** | API tối ưu cho một loại client, có thể tổng hợp | Có logic composition/presentation có chủ đích, khác cross-cutting gateway |
| **Identity Provider** | Đăng nhập, cấp token hoặc cung cấp identity | Gateway **xác minh** credential; không phải luôn trực tiếp xác thực mật khẩu |

Trong triển khai thực tế, một reverse proxy có thể được cấu hình thành API Gateway; một ingress controller có thể tích hợp các bộ lọc auth và rate limit; mesh có thể xử lý gateway/egress. Quan trọng là **trách nhiệm, điểm thực thi chính sách và ranh giới tin cậy**, không phải tên thương mại của thành phần.

### 2.1. Gateway không chỉ là load balancer

Một LB có thể chuyển request đến Pod Order-1, Order-2 hoặc Order-3; gateway quyết định request POST /api/orders thuộc Order Service và có cần token/scope/quota nào. Sau khi chọn service logic, tầng dataplane có thể tiếp tục dùng LB để chọn instance.

### 2.2. Gateway không thay thế IdP

OpenID Connect/OAuth 2.0 có thể liên quan IdP/authorization server. Gateway thường nhận token được cấp trước, kiểm tra token, rồi tiếp tục request. Không tự phát triển màn hình login và kho mật khẩu trong gateway nếu hệ thống đã có IdP đúng vai trò.

### 2.3. Gateway không đồng nghĩa public internet ingress

Một tổ chức có thể có:

- **Public gateway:** Nhận request từ browser/mobile/đối tác.
- **Internal gateway:** Quản lý API dùng giữa nhiều domain hoặc network segments.
- **Partner gateway:** Hợp đồng và quota riêng cho đối tác.
- **Regional gateway:** Điều phối traffic trong một region.
- **BFF riêng cho mobile/web:** Biến đổi dữ liệu để tối ưu trải nghiệm từng client.

Không cần tạo nhiều gateway nếu chưa có nhu cầu. Việc nhân bản entry point làm tăng config, secret, policy và deployment coordination.

## 3. Request đi qua gateway như thế nào?

Một đường đi đơn giản:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant ID as Token issuer / JWKS
    participant S as Order Service
    C->>G: POST /api/orders + credential
    G->>G: Kiểm tra TLS, route, request size
    G->>G: Xác minh token và policy biên
    Note over G,ID: JWKS/keys có thể được cache và refresh
    G->>G: Rate limit + admission control
    G->>S: Forward request + identity context đã tin cậy
    S->>S: Authorization nghiệp vụ + xử lý
    S-->>G: 201 / 202 / business error
    G-->>C: Response theo API contract
~~~

Đây là sơ đồ khái niệm, không bắt buộc thứ tự từng filter phải giống nhau cho mọi gateway. Một số kiểm tra có thể diễn ra trước khi resolve route; việc xác định key quota thường cần xác minh caller để không tin một header tự khai.

### 3.1. Phân chia công việc theo lớp

**Network/edge:** Chặn kết nối bất hợp lệ, TLS, giới hạn kích thước và nguồn traffic.

**Gateway:** Xác minh caller, chọn route, áp quota, timeout và headers.

**Backend:** Kiểm tra business permission và invariant, xử lý nghiệp vụ, ghi nguồn dữ liệu đúng owner.

**Downstream:** Những service khác được backend gọi theo contract có authn/authz và chính sách riêng tùy trust model.

### 3.2. Vì sao không chỉ cho phép mọi thứ ở gateway?

Gateway biết request đến /orders/O-101, token chứa subject C-7 và scope orders:read. Nhưng quyền xem **đơn O-101** có thể phụ thuộc:

- Chủ sở hữu đơn là ai?
- Đơn thuộc tổ chức nào?
- Người dùng có vai trò hỗ trợ khách hàng được ủy quyền không?
- Đơn đang ở trạng thái có thể công khai không?
- Có chính sách dữ liệu nhạy cảm hoặc quyền theo hợp đồng không?

Order Service sở hữu những sự thật này nên phải kiểm tra **object-level authorization** ở domain boundary. Gateway xác minh token và scope tổng quát không đủ để kết luận mọi order đều có thể đọc.

## 4. Authentication và Authorization là hai bước khác nhau

### 4.1. Authentication: ai đang gọi?

Authentication xác minh bằng chứng để gắn request với một identity đáng tin theo chính sách.

Ví dụ:

- JWT access token được IdP ký;
- Opaque bearer token được xác minh qua cơ chế phù hợp;
- API key định danh một client/application;
- mTLS chứng minh danh tính workload hoặc partner được cấp chứng chỉ;
- Session cookie với session state do hệ thống quản lý;
- HMAC signature của webhook kèm timestamp/nonce;
- Credential kết hợp khi quy định yêu cầu hơn một lớp.

### 4.2. Authorization: caller được phép làm gì?

Authorization quyết định caller có quyền thực hiện **operation trên resource trong ngữ cảnh hiện tại** không.

Các cấp:

- **Endpoint-level:** Token có scope orders:write để gọi POST /orders?
- **Resource-level:** User có được xem orderId O-101?
- **Tenant-level:** Request có đúng organization/tenant?
- **Attribute-based:** Có đáp ứng điều kiện trạng thái, vai trò, region, dữ liệu nhạy cảm?
- **Service-to-service:** Order workload có quyền gọi Payment Authorize?
- **Business invariant:** Một đơn đã SHIPPED có được hủy theo chính sách?

### 4.3. Ranh giới thực thi hợp lý

| Quyết định | Gateway | Service |
|---|---|---|
| Token có chữ ký hợp lệ? | Thường nên kiểm tra ở biên | Có thể kiểm tra lại hoặc tin identity đã xác minh qua kênh đáng tin |
| Issuer/audience/expiry đúng? | Có | Tùy mô hình zero trust và độ nhạy |
| Caller có scope công khai cần thiết? | Có thể kiểm tra sớm | Vẫn có thể kiểm tra theo policy |
| Order có thuộc user hiện tại? | Thường không đủ dữ liệu | **Order phải quyết định** |
| Refund có vượt hạn mức? | Không nên | **Payment/Refund domain quyết định** |
| Tenant có được gọi route này không? | Có thể chặn sơ bộ | Domain vẫn kiểm tra quyền trên resource |
| Có được chuyển tiền từ tài khoản A? | Không nên giả định | Service sở hữu tài khoản/transaction |
| Client vượt request quota? | Nên giới hạn ở biên | Service có thể có quota riêng theo dependency |

**Authentication tập trung không có nghĩa loại bỏ authorization ở service.** Một API bảo mật tốt tránh việc “qua gateway là có toàn quyền”.

## 5. Token-based authentication: OAuth 2.0, OIDC và JWT

### 5.1. Vai trò của OAuth 2.0 và OpenID Connect

**OAuth 2.0** là framework ủy quyền, thường giúp client lấy access token để truy cập protected resources. **OpenID Connect (OIDC)** bổ sung lớp danh tính/đăng nhập, trong đó ID token thể hiện thông tin authentication cho client.

Một nhầm lẫn quan trọng:

- **Access token:** Dùng để gọi resource server/API theo audience/scope và token semantics.
- **ID token:** Dùng cho client xác nhận sự kiện đăng nhập theo OIDC; không nên mặc định dùng ID token thay access token khi gọi backend API.

Gateway phải chấp nhận credential được thiết kế dành cho chính API, không chỉ vì token có định dạng JWT.

### 5.2. Những gì gateway cần kiểm tra với JWT

Với JWT access token được ký, thường cần:

1. **Cấu trúc token** hợp lệ và không vượt giới hạn size.
2. **Thuật toán ký** nằm trong allowlist của cấu hình, không tin alg do token tự chọn.
3. **Signature** hợp lệ theo key tin cậy và đúng thuật toán.
4. **Issuer (iss)** đúng authority đã cấu hình.
5. **Audience (aud)** bao gồm API/resource server đúng mục tiêu.
6. **Expiration (exp)** chưa hết hạn; **not-before (nbf)** nếu có và phù hợp.
7. **Token type/usage** phù hợp nếu issuer có nhiều loại token.
8. **Scopes/claims** có ý nghĩa trong contract API, không xem mọi claim như quyền tuyệt đối.
9. **Key selection** qua kid/JWKS có kiểm soát, không theo URL hoặc key do token tự khai không đáng tin.
10. **Clock skew và key rotation** được xử lý với giới hạn rõ.
11. **Revocation/compromise policy** được hiểu đúng theo loại token và tuổi thọ token.
12. **Identity propagation** chỉ sử dụng dữ liệu đã xác minh; không tin identity headers từ bên ngoài.

JWT là container cho claims, không phải cơ chế **mã hóa bí mật** nội dung mặc định. Payload của JWT thông thường có thể được giải mã để đọc nếu người khác sở hữu token, dù signature ngăn sửa trái phép. Tránh nhúng dữ liệu nhạy cảm không cần thiết.

### 5.3. JWKS và key rotation

Một IdP có thể công bố public keys qua JWKS endpoint. Gateway cache các keys và refresh theo policy. Khi issuer xoay key:

- Gateway phải lấy key mới đủ nhanh để xác minh token hợp lệ;
- Tránh fetch JWKS trên **mỗi request**, dễ gây phụ thuộc mạng và DDoS;
- Có cách xử lý kid chưa biết, cache miss và rate limit fetch;
- Không tin URI tùy ý nằm trong token để tải một key lạ;
- Khi JWKS/IdP tạm lỗi, cần chính sách cache, freshness và fail-open/fail-closed được quyết định theo độ nhạy.

**Vấn đề thực tế:** Gateway kiểm tra chữ ký thành công nhưng không kiểm aud. Khi đó access token cấp cho API khác có thể bị chấp nhận sai. Việc kiểm issuer/audience là nền tảng của trust boundary.

### 5.4. Opaque token

Một access token có thể là opaque string, không tự chứa claims đọc được. Gateway hoặc resource server cần validation qua cơ chế được IdP hỗ trợ (ví dụ introspection) hoặc một token validation service.

Lợi thế là kiểm tra trạng thái token tập trung dễ hơn theo thiết kế; nhưng nó có thể tạo dependency runtime lên hệ thống xác minh. Nếu dùng cache, phải quyết định TTL và ảnh hưởng khi token bị thu hồi.

Không suy luận tất cả access token đều JWT hoặc tất cả token đều có thể verify offline.

### 5.5. API keys

API key thường tiện để định danh một ứng dụng/đối tác và gắn quota, nhưng không mặc nhiên mang danh tính của **người dùng cuối**. Cần lưu key an toàn, rotate, giới hạn phạm vi, tránh log key và thu hồi khi lộ.

API key ở query string dễ xuất hiện trong logs, analytics và referrer; nên chọn kênh truyền được quy định và bảo vệ. Với endpoint nhạy cảm, API key đơn lẻ có thể không đáp ứng yêu cầu authentication/authorization.

### 5.6. mTLS và service identity

mTLS cho phép hai workload xác thực lẫn nhau qua chứng thư trong trust domain. Gateway có thể xác thực upstream hoặc caller service, nhưng cần kiểm certificate identity và authorization policy tương ứng, không chỉ “TLS handshake thành công”.

Một partner kết nối qua mTLS vẫn có thể cần quyền theo business account và rate quota; mTLS là bằng chứng danh tính chứ không quyết định được phép làm mọi operation.

## 6. Header danh tính: đặc biệt cẩn thận với spoofing

Giả sử gateway xác minh access token rồi thêm:

~~~http
X-Authenticated-User: C-7
X-Tenant-Id: TENANT-2
X-Caller-Scope: orders:read
~~~

Nếu backend tin các header này mà một client ngoài internet có thể tự gửi chúng trực tiếp hoặc gateway không xóa header trước khi thêm, attacker có thể **mạo danh** người khác.

### 6.1. Nguyên tắc bảo vệ

1. **Không cho backend public trực tiếp** nếu nó chỉ tin các identity header do gateway tạo.
2. Gateway phải **xóa/ghi đè** những header định danh đến từ caller, không “nếu chưa có thì mới thêm”.
3. Backend cần xác định request đến qua **kênh tin cậy**, ví dụ mTLS giữa gateway và backend, policy mạng và quyền truy cập phù hợp.
4. Không cho các proxy khác chèn identity claims thiếu xác minh.
5. Tránh dùng các header thông dụng như X-User-Id mà không có chuẩn trust boundary rõ.
6. Khi nhiều gateway/proxy đứng nối tiếp, phải xác định tầng nào được quyền tạo và tiêu thụ từng identity header.
7. Header User/Tenant chỉ là ngữ cảnh; backend tiếp tục kiểm quyền trên resource nghiệp vụ.

### 6.2. Hai mô hình phổ biến

**Mô hình A — Forward access token:** Gateway kiểm token trước; backend cũng kiểm token hoặc kiểm theo trust model. Dễ giữ claims nguyên gốc nhưng làm nhiều service cần validator/config, đồng thời phải cẩn thận scope/audience.

**Mô hình B — Token exchange/identity context đã ký:** Gateway chuyển credential bên ngoài thành internal token hoặc context được xác thực, giới hạn audience/phạm vi dùng. Giảm phơi bày external token cho nhiều service nhưng cần token issuer/verification và vòng đời rõ.

Không có mô hình nào đúng tuyệt đối. Chọn theo zero-trust posture, độ nhạy, kiến trúc IdP, khả năng vận hành và yêu cầu audit.

### 6.3. X-Forwarded-For / Forwarded

Gateway thường quản lý IP/client chain trong các header như Forwarded hoặc X-Forwarded-For. Nếu dùng IP để rate limit hoặc audit, phải xác định **trusted proxy chain**. Không tin giá trị IP do internet client tự gắn vào header, vì attacker có thể đổi IP giả cho mỗi request để né quota.

### 6.4. Tránh biến gateway thành confused deputy

Gateway có quyền gọi backend nhưng caller không nhất thiết có quyền dùng mọi chức năng backend. Nếu gateway dùng credential quyền cao để gọi tất cả service mà không mang theo identity và permission context của caller, một route sai có thể vượt qua phân quyền.

Cần phân tách **quyền gateway gọi upstream** và **quyền người dùng/đối tác yêu cầu thao tác**, nhất là với Payment, Admin hoặc dữ liệu nhạy cảm.

## 7. Routing: từ public API đến service logic

Gateway có thể route theo nhiều tín hiệu:

- **Host:** api.example.test khác partner.example.test;
- **Path:** /api/orders/** tới Order, /api/products/** tới Catalog;
- **HTTP method:** GET và POST có thể có policy khác nhau;
- **API version:** /v1 hoặc version trong header theo contract;
- **Header đã được xác minh:** Ví dụ cohort/canary hoặc tenant từ token;
- **Geography/region:** Chỉ khi phù hợp chính sách dữ liệu;
- **Traffic weight:** Canary/blue-green;
- **API product/quota tier:** Đối tác hoặc nhóm ứng dụng có chính sách riêng.

### 7.1. Route table minh họa

| Public route | Method | Auth policy | Upstream logic | Rate policy |
|---|---|---|---|---|
| /api/products/** | GET | Có thể public cho một số dữ liệu | catalog | 100 req/s/IP, burst có giới hạn |
| /api/orders | POST | User access token + scope | order | 10 req/min/user + global |
| /api/orders/{id} | GET | Token hợp lệ; quyền tài nguyên tại Order | order | 100 req/min/user |
| /api/payments/** | POST | Token phù hợp + yêu cầu bảo mật cao | payment | Per-user/tenant + concurrency |
| /api/partner/orders | POST | Partner credentials | order-partner-adapter | Per-partner contract |
| /api/admin/** | ALL | Admin authentication | admin | Policy nghiêm ngặt và audit |

**Giá trị rate chỉ minh họa**, không phải khuyến nghị mặc định. Giới hạn thực tế cần đo capacity, cost và kỳ vọng của từng route.

### 7.2. Thứ tự ưu tiên và route conflicts

Giả sử gateway có:

~~~text
/api/orders/**
/api/orders/admin/**
/api/**
~~~

Nếu luật khớp route không rõ, một route chung có thể bắt request admin và bỏ qua chính sách nghiêm ngặt. Cần:

- Xác định specificity/priority rõ;
- Kiểm thử route matching cho mọi method/path;
- Chính sách mặc định **deny nếu không có route hợp lệ**;
- Không cho route fallback vô tình mở proxy tới mọi internal service;
- Không dùng regex quá rộng dễ bị bypass;
- Chuẩn hóa cách xử lý path encoding, case và slash;
- Kiểm tra mọi phiên bản cấu hình gateway trước khi deploy.

**Route matching khác authorization.** Một request khớp /api/admin không có nghĩa đã đủ quyền admin; cần guard đúng policy.

### 7.3. Hostname và path rewriting

Gateway có thể nhận /api/orders/O-101 và chuyển thành /orders/O-101 cho backend. Nhưng nếu rewrite không nhất quán:

- Backend tạo link redirect sai;
- Signature/canonical request bị sai vì path bị sửa;
- Client thấy 404 dù route ngoài tồn tại;
- Cache key sai khi hai path cùng dẫn tới một resource;
- Các service có thể đọc nhầm Host/X-Forwarded-Prefix.

Rewrite là một phần của API contract. Ghi rõ public path, upstream path, host forwarding, trailing slash, query handling và encoding semantics.

### 7.4. Service discovery phía sau route

Route trỏ tới **service logic**, không nên hard-code Pod IP:

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway"]
    G -->|"/api/orders"| S["Service DNS / Registry"]
    S --> L["LB / Service VIP"]
    L --> O1["Order Pod 1"]
    L --> O2["Order Pod 2"]
~~~

Khi Order scale từ 2 lên 8 Pods, gateway không cần thay public route. Discovery và dataplane cập nhật endpoint set. Tuy nhiên gateway có thể giữ connection cũ hoặc cache DNS, nên cần quản lý TTL, pool lifecycle và draining.

### 7.5. Route tới phiên bản không tương thích

Trong rollout, v1 và v2 cùng chạy. Gateway có thể gửi 5% traffic tới canary v2. Nhưng nếu v2 thay contract theo cách không tương thích với client cũ, weighted route không tự sửa lỗi. Cần API versioning, contract tests và kế hoạch migration phù hợp.

## 8. Canary, blue-green và tenant-aware routing

### 8.1. Weighted canary

Ví dụ:

~~~text
order-v1  → 95% requests
order-v2  →  5% requests
~~~

Cấu hình trọng số là mục tiêu phân phối, không cam kết chính xác 5% trên số mẫu nhỏ. Sticky connections, retry, traffic theo route hoặc LB ở L4 có thể làm tỷ lệ quan sát khác tỷ lệ đặt.

Theo dõi error rate, p95/p99, business metric và response compatibility của canary, không chỉ 200/500.

### 8.2. Tenant routing

Một số hệ thống cần route theo tenant tới region/cluster riêng. Tenant ID phải lấy từ **identity đã xác thực** hoặc mapping được tin cậy, không phải header X-Tenant-Id tự khai.

Sai sót có thể nghiêm trọng:

- User tenant A bị route tới dữ liệu tenant B;
- Tenant có residency yêu cầu region A nhưng request chuyển region B;
- Cache dùng chung nhưng không phân tách tenant;
- Một rule fallback khi tenant mapping lỗi lại đưa đến backend mặc định không đúng.

**Routing theo tenant không thay tenant isolation trong backend/database.** Backend phải kiểm domain authorization trong mọi đường đi.

### 8.3. Blue-green và rollback

Gateway có thể chuyển traffic giữa deployment xanh và deployment mới. Rollback routing giúp chuyển traffic nhanh, nhưng **không rollback tự động** DB migrations, event schema hoặc side effect đã commit. Cần áp dụng expand–migrate–contract, compatibility window và kế hoạch lỗi nghiệp vụ.

### 8.4. Shadow traffic

Một số proxy hỗ trợ mirror một bản request tới backend thử nghiệm. Điều này hữu ích để đo read-only behavior, nhưng rất nguy hiểm nếu **Payment, Order creation hoặc Email** thực thi side effect. Không mirror request ghi dữ liệu thực trừ khi có cơ chế bảo đảm side effect vô hại và đã được phép.

## 9. Giới hạn lưu lượng (rate limiting) tại cổng API

Rate limiting giúp ngăn một caller gửi request nhanh hơn mức chính sách cho phép. Mục tiêu có thể gồm:

- Bảo vệ CPU, memory, connection pools và backend capacity;
- Tránh một khách hàng chiếm hết tài nguyên của khách khác;
- Giảm bot/scraping và hành vi lạm dụng;
- Thực thi quota theo hợp đồng API;
- Bảo vệ các route đắt tiền;
- Giảm nguy cơ retry storm;
- Ổn định latency/SLO khi hệ thống vào trạng thái tải cao.

**Rate limit không phải giải pháp chống mọi loại DDoS** và không thay thế WAF, anti-bot, CDN/edge capacity hoặc network mitigation. Một lượng lớn kết nối có thể làm nghẽn trước khi request đi tới filter quota của gateway.

### 9.1. Chọn khóa giới hạn (rate-limit key)

| Khóa | Lợi thế | Rủi ro |
|---|---|---|
| Source IP | Hữu ích cho public unauthenticated endpoints | NAT chia sẻ IP, proxy chain, IPv6 rotation, spoofed forwarded headers |
| Authenticated user ID | Fairness theo người dùng | Một người dùng có nhiều clients, tài khoản bị chiếm |
| API key/client ID | Hữu ích cho đối tác/ứng dụng | Một key chia sẻ nhiều user; cần rotation |
| Tenant/organization | Bảo vệ tài nguyên theo khách hàng | Noisy user trong cùng tenant; workload chi phí khác |
| Route/API operation | Phân biệt operation nặng/nhẹ | Route cardinality và config phức tạp |
| Global capacity | Giữ backend tổng không quá tải | Cần fairness để tránh tenant nhỏ bị ảnh hưởng |
| User + route | Quota chi tiết | Tăng số bucket, chi phí state |
| Credential + IP | Hỗ trợ abuse control | Dễ vô tình chặn người dùng hợp lệ sau NAT |

Hệ thống thường kết hợp **nhiều giới hạn**: ví dụ public IP limit trước auth, user/tenant limit sau auth và global concurrency limit gần upstream.

### 9.2. Thứ tự xác minh và quota key

Một request chưa được xác thực không được tự quyết user ID hoặc tenant ID để nhận quota ưu đãi. Gateway phải xác minh identity trước khi áp quota dựa trên claims, đồng thời có thể dùng giới hạn rất sớm theo network source để bảo vệ khỏi tấn công trước bước xác thực.

Thiết kế hai tầng:

~~~text
Lớp 1: Edge/IP coarse limits, payload size, connection controls
   ↓
Lớp 2: Credential verification
   ↓
Lớp 3: Per-client/per-user/per-tenant limits
   ↓
Lớp 4: Route cost/concurrency limits
   ↓
Backend
~~~

Mọi lớp cần xác định trust source và phối hợp, tránh đếm trùng một cách bất ngờ.

## 10. Các thuật toán rate limiting

### 10.1. Fixed window

Ví dụ giới hạn 100 request mỗi phút theo user. Mỗi cửa sổ phút có counter.

**Ưu:** Dễ thực hiện và theo dõi.  
**Nhược:** Nếu user gửi 100 request ngay cuối phút và 100 ngay đầu phút tiếp theo, có thể tạo burst 200 request trong thời gian rất ngắn dù mỗi phút không vượt 100.

Phù hợp quota thô; có thể không đủ bảo vệ một dependency có burst tolerance thấp.

### 10.2. Sliding window

Đếm hoặc ước lượng số request trong 60 giây gần nhất thay vì hai cửa sổ lịch riêng.

**Ưu:** Giảm boundary burst, thể hiện quota tương đối đều.  
**Nhược:** Cần state hoặc thuật toán xấp xỉ có chi phí. Sliding log chính xác thường tốn nhiều bộ nhớ hơn counter xấp xỉ.

### 10.3. Token bucket

Bucket có:

- Tốc độ nạp **r token/giây**;
- Dung lượng tối đa **B token**;
- Mỗi request tiêu thụ số token theo cost;
- Không đủ token thì reject hoặc delay theo policy.

Ví dụ **r = 20 req/s, B = 40** với cost 1 token/request: caller có thể gửi một burst tối đa khoảng 40 request khi bucket đầy, sau đó duy trì trung bình 20/s. Bucket size phải phù hợp burst capacity của downstream.

Pseudocode:

~~~text
state:
    refillRate = 20 tokens/s
    capacity = 40 tokens
    tokens = 40
    lastUpdated = monotonicNow()

onRequest(cost):
    elapsed = max(0, monotonicNow() - lastUpdated)
    tokens = min(capacity, tokens + elapsed * refillRate)
    lastUpdated = monotonicNow()

    if tokens >= cost:
        tokens -= cost
        admit()
    else:
        rejectOrDelayAccordingToContract()
~~~

Đây là ý tưởng, không phải code production. Với nhiều gateway replicas phải quyết định per-instance hay global state, atomicity và clock behavior.

### 10.4. Leaky bucket / traffic shaping

Một bộ đệm hữu hạn có thể làm mượt tốc độ gửi ra ngoài theo nhịp nhất định. Phù hợp khi upstream/provider không chịu burst cao.

Nhược điểm: request chờ quá lâu sẽ tăng latency, giữ connection hoặc vô ích nếu đã hết deadline. **Không tạo queue vô hạn tại gateway** để giả vờ không từ chối traffic.

### 10.5. Concurrency limiting

Thay vì chỉ tính số request/s, giới hạn số request đang chạy tới backend. Ví dụ Payment chỉ cho 20 concurrent authorizations theo capacity thực.

**Rate và concurrency khác nhau:** Nếu 20 requests mất 100 ms, có thể xử lý nhiều req/s hơn khi mỗi request mất 5 giây. Khi dependency chậm, concurrency full nhanh và gateway cần admission control/timeout thay vì giữ thêm hàng nghìn request trong memory.

### 10.6. Weighted quotas theo cost

Không phải mọi operation có chi phí như nhau:

- GET /products cached: nhẹ;
- Search nhiều filter: vừa;
- POST /reports/export: nặng;
- Upload multipart: tiêu thụ bandwidth/storage;
- Payment authorization: liên quan external quota/rủi ro;
- GraphQL query sâu: có thể tạo N+1 backend calls.

Có thể tính 1 request = nhiều cost units tùy loại operation. Quota theo số request thuần túy có thể không bảo vệ được backend nếu một route nặng gấp hàng trăm lần route khác.

### 10.7. Adaptive rate limiting

Hệ thống có thể giảm intake khi upstream p95 latency tăng, 429/503 dồn nhiều, queue age vượt SLO hoặc pool đạt giới hạn. Khi phục hồi, tăng dần mức nhận.

Cần:

- **Hysteresis** để không bật/tắt liên tục;
- Controller không tăng limit chỉ vì có backlog nếu dependency đã saturation;
- Policy khi metric thiếu;
- Mức tối đa/tối thiểu an toàn;
- Tín hiệu công khai phù hợp với client khi bị throttle.

Một adaptive controller sai có thể làm overload dao động mạnh hơn chính tải ban đầu.

## 11. Distributed rate limiting khi có nhiều gateway replicas

Một API Gateway thường có nhiều replicas để scale và HA. Khi có 5 replicas, nếu mỗi replica tự cho phép 100 req/s, tổng thực tế có thể lên tới khoảng 500 req/s, chưa kể phân phối không đều. Nếu hợp đồng nói 100 req/s **toàn hệ thống**, cần cơ chế global quota hoặc cấp phát budget giữa các nodes.

### 11.1. Các mô hình state

| Mô hình | Ưu điểm | Đánh đổi |
|---|---|---|
| Counter/token bucket cục bộ | Nhanh, ít dependency | Không bảo đảm global limit nếu replicas thay đổi |
| Shared datastore (ví dụ Redis) | Tập trung quota theo key, dễ chia đều | Thêm latency/dependency, cần atomic operations và HA |
| Distributed quota service | Policy riêng, có thể hỗ trợ nhiều gateway | Thêm control/data-path dependency, phức tạp vận hành |
| Token leasing/định mức mỗi instance | Giảm số lần gọi shared state | Có thể vượt/hụt quota và không công bằng khi tải lệch |
| Edge/CDN + gateway limit | Chặn một phần abuse từ sớm | Hai lớp cần config/key nhất quán, tránh false positives |

### 11.2. Atomicity và consistency của quota

Nếu hai gateway nodes cùng đọc counter rồi cùng tăng không nguyên tử, quota có thể bị vượt. Với Redis hoặc data store khác, cần thao tác **atomic** hoặc thuật toán phân tán có semantics rõ.

Không mặc định việc dùng Redis đồng nghĩa quota chính xác tuyệt đối dưới network partition/failover. Cần xác định mức sai số chấp nhận được, độ trễ, cách đồng bộ và policy khi store không có sẵn.

### 11.3. Fail-open và fail-closed

Khi quota store lỗi, gateway nên làm gì?

- **Fail-open:** Vẫn cho request đi qua một mức bảo vệ dự phòng; tăng availability nhưng có thể vượt quota và gây overload.
- **Fail-closed:** Từ chối khi không xác minh được quota; bảo vệ hệ thống nhưng gây giảm availability ngay cả với client hợp lệ.
- **Degraded mode:** Dùng local conservative limit, ngưỡng bảo vệ đơn giản hoặc một subset endpoints.

Lựa chọn phụ thuộc route. Public read nhẹ có thể dùng fallback khác với payment, token issuance hoặc upload khối lượng lớn. Phải ghi rõ trong ADR và kiểm thử failover.

### 11.4. Key cardinality và chi phí state

Rate limit theo IP + user + tenant + route có thể tạo rất nhiều bucket. TTL/counter cleanup và memory pressure quan trọng. Tránh cho untrusted client tự tạo vô hạn key bằng header bất kỳ. Tên key nên được chuẩn hóa và giới hạn độ dài.

## 12. 429 và 503: phản hồi khi hệ thống không nhận thêm được

### 12.1. 429 Too Many Requests

Thường phù hợp khi caller vượt một quota/rate policy.

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30

{
  "code": "RATE_LIMITED",
  "message": "Request rate exceeds the allowed quota",
  "retryAfterSeconds": 30,
  "correlationId": "req-7fc1"
}
~~~

**Retry-After** có thể là khoảng giây hoặc ngày HTTP theo giao thức. Client cần hiểu quy tắc giới hạn và áp dụng backoff/jitter thay vì thử lại ngay. Khi API cung cấp rate-limit headers, phải dùng định dạng và semantics nhất quán, không hứa chính xác reset time nếu thuật toán không bảo đảm.

### 12.2. 503 Service Unavailable

Có thể phù hợp khi backend hoặc gateway không còn capacity/đang bảo trì, không nhất thiết là caller đã vượt quota cá nhân.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 10

{
  "code": "UPSTREAM_OVERLOADED",
  "message": "Service is temporarily unavailable",
  "correlationId": "req-a18b"
}
~~~

Đừng dùng 429 để che mọi lỗi runtime. Cũng đừng dùng 503 cho lỗi authorization. Các status phải giữ ngữ nghĩa nhất quán theo API contract.

### 12.3. 401 và 403

- **401 Unauthorized:** Thường biểu thị yêu cầu cần authentication hợp lệ, token thiếu/không hợp lệ/hết hạn; có thể kèm WWW-Authenticate theo scheme.
- **403 Forbidden:** Caller đã được nhận diện hoặc request được hiểu nhưng không đủ quyền theo policy, dù trường hợp thực tế có thể cần che resource bằng 404 theo thiết kế bảo mật.
- **404 Not Found:** Route hoặc resource không tồn tại hoặc cố ý không tiết lộ; không dùng để che sai config một cách tùy tiện.
- **400 Bad Request:** Payload/headers không hợp lệ, khác lỗi authentication.
- **502/504:** Gateway nhận vấn đề từ upstream hoặc timeout của đường request tùy semantics.

**Phân biệt lỗi auth với lỗi rate:** Token sai không nên trở thành 429 trừ khi request cũng chạm chính sách bảo vệ abuse sớm. Backend error không nên được gateway đổi thành 401 vì client sẽ liên tục refresh token.

### 12.4. Error contract

Các service có thể dùng định dạng lỗi thống nhất cho API public: code có ý nghĩa máy đọc, message phù hợp, correlationId, chi tiết kiểm tra input được phép công khai. Không đưa stack trace, internal hostname, database detail, access token hoặc thông tin nhạy cảm ra response.

## 13. Rate limiting không phải backpressure hoàn chỉnh

Gateway có thể giới hạn intake, nhưng hệ thống vẫn cần bảo vệ các lớp phía sau:

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway admission"]
    G --> O["Order"]
    O --> B[("Outbox / Broker")]
    B --> P["Payment Worker"]
    P --> X["Payment Provider"]
    X -. "429 / slow" .-> P
    P -. "queue age / saturation" .-> G
~~~

Khi Payment chậm, một API POST /orders có thể vẫn trả 202 và chất công việc vào queue vô hạn. Gateway rate limiting cố định chưa chắc đủ để giữ **completion SLO**.

Cần kết hợp:

- **Gateway:** Rate limit, global admissions, per-tenant fairness;
- **Backend:** Business quota và capacity-aware admission;
- **Broker:** Queue depth/oldest age, retention, publisher throttle;
- **Consumer:** Bounded in-flight, concurrency, delayed retry;
- **External provider:** Respect Retry-After, idempotency;
- **Workflow:** PENDING/REVIEW_REQUIRED/COMPENSATING và đối soát khi lỗi;
- **Observability:** End-to-end completion time, không chỉ gateway p95.

API Gateway phải hiểu khi nào “nhận thêm request” là điều không thể thực hiện đúng cam kết, dù gateway còn CPU dư.

## 14. Timeout, retry, circuit breaker và gateway

### 14.1. Overall deadline

Gateway phải giới hạn thời gian chờ upstream và hiểu ngân sách của request. Ví dụ public request có deadline 2.000 ms; nếu gateway tiêu 200 ms để auth/quota/routing, backend không nên được cấp lại toàn bộ 2 giây rồi giữ client lâu hơn SLO.

Có thể truyền deadline/timeout context qua headers/gRPC metadata theo contract tin cậy. Header do user tự gửi không nên được cho phép mở rộng thời gian vượt server policy.

### 14.2. Retry policy tại gateway

Gateway đôi khi retry **read idempotent** khi kết nối backend lỗi. Nhưng nếu Order POST /orders có thể đã commit và response bị mất, gateway retry mà không có idempotency key/semantic rõ có thể tạo đơn trùng.

Những nguyên tắc:

1. Chỉ retry loại lỗi transient được xác định.
2. Có **retry budget** và max attempts;
3. Truyền lại cùng idempotency key của logical operation;
4. Không retry khi deadline hết;
5. Backoff + jitter khi phù hợp;
6. Không để client, gateway, SDK và service cùng nhân retries mà không phối hợp;
7. Ghi rõ số attempts và chọn backend trong trace;
8. Với payment/side effects cần kết quả không rõ, query/reconciliation thay vì mù quáng thử lại với key mới.

### 14.3. Circuit breaker và outlier detection

Gateway có thể tạm tránh một upstream liên tục lỗi hoặc fail fast khi backend đang overload. Nhưng nếu tất cả Order pods dùng cùng database bị down, eject tất cả endpoints chỉ khiến gateway trả no healthy upstream; nó không giải quyết sự cố DB.

Cần theo dõi **backend-level error/latency** và **service-level SLO**, tránh tạo vòng feedback gây oscillation. Không coi 4xx do caller gửi sai là bằng chứng backend không khỏe.

### 14.4. Timeout không đồng nghĩa rollback

Client timeout tại gateway khi Payment đã commit. Gateway không được mặc định trả “payment chắc chắn thất bại” theo business status. Nếu operation outcome unknown, cần idempotency, trạng thái truy vấn hoặc đối soát. API error nên mô tả uncertainty đúng contract.

## 15. Cache, compression, CORS và request transformation

Gateway có thể làm nhiều việc khác auth/routing/rate limit, nhưng mỗi chức năng thêm coupling và rủi ro.

### 15.1. Caching

GET /catalog/products có thể cache theo TTL và invalidation policy. Nhưng cache phải xét:

- URL/query/headers tạo cache key;
- User/tenant context và authorization;
- Dữ liệu công khai so với dữ liệu cá nhân;
- Staleness chấp nhận được;
- Cache-Control và HTTP semantics;
- Ảnh hưởng tới rate limit (request vẫn đến gateway dù upstream cache hit);
- Không cache kết quả thanh toán hoặc dữ liệu đơn nhạy cảm một cách mặc định.

**Cache nhầm khóa tenant** có thể làm lộ dữ liệu giữa khách hàng dù routing và token đều hợp lệ.

### 15.2. Compression và payload size

Compression có thể giảm bandwidth nhưng tốn CPU. Gateway nên giới hạn kích thước body thực tế và trường hợp decompression bomb; không chỉ giới hạn Content-Length do client tự khai. Với upload lớn, cần streaming, body limits và auth/quota phù hợp.

### 15.3. CORS

CORS là chính sách trình duyệt kiểm soát JavaScript truy cập cross-origin; nó **không thay thế authentication/authorization** và không chặn mọi client HTTP như curl/mobile server. Không cấu hình wildcard origins cùng credentials một cách tùy tiện.

Khi gateway xử lý preflight OPTIONS, cần route và policy nhất quán; không để preflight hoặc CORS error bị hiểu nhầm thành backend outage.

### 15.4. Request transformation

Gateway có thể chuẩn hóa header, chuyển path hoặc thêm correlation ID. Nhưng chuyển đổi nhiều dữ liệu nghiệp vụ, ghép N backend responses và sở hữu trạng thái workflow thường nên được đặt trong BFF/composition service hoặc domain service có owner rõ.

**Nguyên tắc:** Chỉ đặt logic ở gateway khi nó là cross-cutting concern và có chính sách phát hành/kiểm thử tương thích phù hợp.

## 16. API Gateway và Backend For Frontend

Một mobile app có thể cần response gọn, còn web app cần nhiều trường. Nếu gateway bắt đầu gọi Catalog, Order, Payment, Recommendation rồi tạo response theo màn hình, nó đang đóng vai trò **BFF/composition layer**.

Không phải lúc nào điều đó sai. Nhưng cần tách ownership:

~~~mermaid
flowchart TD
    W["Web Client"] --> G["API Gateway"]
    M["Mobile Client"] --> G
    G --> BW["Web BFF"]
    G --> BM["Mobile BFF"]
    BW --> O["Order"]
    BW --> C["Catalog"]
    BM --> O
    BM --> C
~~~

- Gateway: xác thực, route, quota, TLS/cross-cutting policies.
- BFF: composition và presentation theo nhu cầu client.
- Domain services: business rules và nguồn sự thật.

Nếu gateway vẫn làm một số composition nhỏ theo thiết kế, cần giới hạn rõ và tránh biến mọi thay đổi UI thành thay đổi cấu hình/logic gateway toàn công ty.

## 17. Single point of failure và HA cho API Gateway

Gateway là điểm vào logic nhưng không nên là **một tiến trình vật lý duy nhất**. Nếu chỉ một instance gateway hoạt động và nó crash, mọi API public có thể ngừng dù backend vẫn khỏe.

### 17.1. Mô hình HA phổ biến

~~~mermaid
flowchart TB
    C["Clients"] --> EDGE["DNS / Edge LB"]
    EDGE --> G1["Gateway Replica A"]
    EDGE --> G2["Gateway Replica B"]
    EDGE --> G3["Gateway Replica C"]
    G1 --> ORD["Order"]
    G2 --> ORD
    G3 --> ORD
    G1 --> CAT["Catalog"]
    G2 --> CAT
    G3 --> CAT
    CONF[("Config / Policy source")] -.-> G1
    CONF -.-> G2
    CONF -.-> G3
~~~

Cần phân biệt **data plane** nhận request và **control/config plane** phát route/policy. Config plane tạm lỗi không nhất thiết làm data plane đang có cấu hình hợp lệ dừng, nhưng stale config có thể trở thành rủi ro khi backend thay đổi.

### 17.2. Gateway HA không chỉ là nhiều replicas

Còn cần:

- Load balancer/edge có HA;
- Chứng chỉ và secret rotation;
- Quota backend phân tán hoặc fallback hợp lý;
- Cơ chế rollout config an toàn;
- Health/readiness và graceful draining;
- Dung lượng dự phòng khi một replica/zone lỗi;
- Quan sát bottleneck CPU, memory, TLS, connection pools, policy store;
- Runbook khi toàn bộ route hoặc auth policy bị cấu hình sai;
- Chiến lược rollback config trong vài phút.

**Shared quota store** có thể trở thành điểm lỗi chung dù gateway có ba replicas. Identity validation endpoint cũng có thể gây lỗi dây chuyền nếu mỗi request đều phải gọi tới nó.

### 17.3. Scale-out và connnection behavior

Load balancer ở tầng TCP có thể phân phối connections, không phân phối từng request. HTTP/2 hoặc kết nối giữ lâu có thể làm tải lệch. Cần quan sát connection count và request count theo gateway replica, không chỉ số Pod.

### 17.4. Rolling config update

Một thay đổi route/auth/quota có thể ảnh hưởng toàn bộ public API. Không push config ra 100% gateway instances không kiểm thử. Có thể:

1. Validate syntax/schema và reference destinations;
2. Chạy policy tests trong CI;
3. Canary một phần gateway traffic/config;
4. Theo dõi auth denials, 4xx/5xx, latency, rate-limited count;
5. Rollback nhanh nếu sai;
6. Tránh hai phiên bản policy mâu thuẫn lâu trên cùng public contract.

## 18. Policy-as-code, sở hữu route và governance

Trong tổ chức nhiều teams, mỗi service có thể sở hữu business contract nhưng gateway là shared entry point. Nếu mọi nhóm tự sửa một file gateway mà không kiểm soát, rủi ro route conflict hoặc cấp quyền quá rộng tăng.

### 18.1. Phân chia ownership

| Quyết định | Chủ sở hữu gợi ý |
|---|---|
| Public API naming/version standards | API governance + domain owners |
| Route tới service logic | Domain owner đề xuất, platform/gateway kiểm thực thi |
| Token issuer/audience validation | Security/identity + platform |
| Scope cần ở endpoint | API/domain owner và security |
| Resource-level authorization | **Domain owner** |
| Per-tenant quota/product contract | API platform/product owner |
| Global overload limits | SRE/platform + capacity owners |
| TLS/certificate/secrets | Platform/security |
| Error schema và tracing | API standards + service teams |
| Canary/rollback | Domain owner với platform release process |
| Incident response | On-call gateway và upstream tương ứng |

### 18.2. Chính sách nên kiểm thử được

Một gateway config nên có automated tests cho:

- Path/method routing;
- Public vs protected endpoints;
- Issuer/audience/token errors;
- Scope/tenant denial;
- Rate-limit keys và quota;
- Header sanitization;
- CORS;
- Backend timeout/retry;
- Version migration;
- Không có route mặc định rộng làm lộ private services.

Policy-as-code giúp review được và truy vết ai đổi; bản thân repo config không chứng minh policy đúng. Cần staging/canary, security review và observability.

### 18.3. Tránh release coupling

Một microservice triển khai nội bộ mới không nhất thiết cần sửa gateway nếu public contract không đổi. Ngược lại, nếu public API endpoint thay đổi, cần coordination và compatibility strategy. Nên ưu tiên route ổn định theo service logic, không theo Pod IP hay tên deployment ngắn hạn.

## 19. Bảo vệ nhiều tenant và fairness

Một tổ chức SaaS có nhiều tenant:

~~~text
TENANT-A: 20 users, tải vừa
TENANT-B: 2.000 users, batch lớn
TENANT-C: 5 users, thanh toán quan trọng
~~~

Nếu chỉ có quota global, TENANT-B có thể chiếm phần lớn capacity, khiến TENANT-C chịu latency cao. Gateway có thể áp:

- Per-tenant requests/s;
- Per-user requests/s trong cùng tenant;
- Global route cost/concurrency limits;
- Reservation cho workload quan trọng;
- Weighted fairness theo gói dịch vụ được công bố;
- Separate queues hoặc pools ở backend nếu cần.

Không tự tin rằng quota tenant ở gateway đủ để chống noisy neighbor ở DB. Nếu một tenant gửi các query rất đắt, 10 req/s có thể gây tải lớn hơn 100 req/s của tenant khác. Cần đo cost/operation và resource isolation tại service/data layer.

### 19.1. Tenant ID phải được xác thực

Không tin client tự đặt X-Tenant-Id: TENANT-C để dùng quota của khách khác. Token đã xác minh có thể chứa tenant context, nhưng backend phải xác minh việc truy cập dữ liệu thực sự thuộc tenant đó.

### 19.2. Quyền của user trong tenant

Một token hợp lệ của TENANT-A không cấp quyền đọc mọi order của TENANT-A. Domain authorization có thể phân biệt admin, nhân viên, người mua và owner của từng resource. Gateway chỉ thực thi policy biên, không thay hệ thống quyền nghiệp vụ.

### 19.3. Quota công bằng khi dùng chung NAT

Giới hạn theo public IP quá thấp có thể chặn hàng nghìn người dùng hợp lệ phía sau một NAT hoặc corporate proxy. Nên áp IP coarse limit cho anonymous abuse; sau xác thực dùng user/tenant/client ID cho fairness chính. Khi dùng IP, chỉ tin chain từ các proxies đã được cấu hình là đáng tin.

## 20. Một cấu hình gateway khái niệm

Các công nghệ như NGINX, Envoy, Kong, Spring Cloud Gateway hoặc các dịch vụ cloud có cú pháp riêng. Cấu hình dưới đây chỉ là **pseudoconfiguration** để minh họa cách phân tách trách nhiệm; không có ý định chạy trực tiếp:

~~~yaml
gateway:
  publicHost: api.example.test

  authentication:
    acceptedSchemes:
      - bearer-access-token
    trustedIssuer: https://identity.example.test
    audience: commerce-api
    jwks:
      cache: enabled
      refreshOnUnknownKeyId: bounded
    stripUntrustedIdentityHeaders: true

  defaults:
    tlsRequired: true
    requestBodyMaxBytes: 1048576
    requestTimeoutMs: 2500
    rejectUnmatchedRoutes: true
    correlationId: generated-if-absent-and-sanitized

  routes:
    - id: catalog-read
      match:
        path: /api/products/**
        methods: [GET]
      upstreamService: catalog
      access: public-read
      limits:
        ip:
          ratePerSecond: 100
          burst: 200

    - id: create-order
      match:
        path: /api/orders
        methods: [POST]
      upstreamService: order
      access:
        requiredScope: orders:write
      limits:
        user:
          perMinute: 10
        tenant:
          perMinute: 1000
        globalConcurrency: 100

    - id: payment-operations
      match:
        path: /api/payments/**
        methods: [POST]
      upstreamService: payment
      access:
        requiredScope: payments:write
      limits:
        user:
          perMinute: 5
        tenant:
          perMinute: 100
      retries:
        automaticForNonIdempotentRequests: false

  upstreamSecurity:
    verifyServiceIdentity: true
    trustedNetworkPath: required

  observability:
    logRequestId: true
    recordRouteLatency: true
    recordRateLimitedCount: true
    redactSecrets: true
~~~

### 20.1. Ý nghĩa của cấu hình

- Public entry point có TLS, request size và deadline;
- Authentication kiểm token theo issuer/audience;
- Untrusted identity headers bị xóa;
- Route riêng cho public GET, Order POST và Payment POST;
- Quota phù hợp từng route và identity key;
- Non-idempotent Payment POST không bị tự động retry;
- Service identity phía upstream được xác minh;
- Logs/metrics phục vụ điều tra.

### 20.2. Những gì pseudoconfig chưa giải quyết

- Quyền xem Order cụ thể vẫn phải ở Order;
- Idempotency key và state machine thuộc service nghiệp vụ;
- Source of truth về Tenant, User permissions và subscriptions cần owner rõ;
- Distributed limiter dùng datastore/quota service nào;
- Key rotation, JWKS failure, TLS policy;
- Rate limit cost của operation đắt;
- Circuit breaker/health discovery và rollout;
- WAF/CDN DDoS mitigation trước gateway.

Đừng nhầm config minh họa với một deployment đã đủ an toàn.

## 21. Ví dụ một request hoàn chỉnh

Giả sử user C-7 muốn tạo đơn:

~~~http
POST /api/orders
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: checkout-C7-cart42-v1

{
  "customerId": "C-7",
  "items": [{"sku": "SKU-8", "quantity": 2}]
}
~~~

Đường xử lý:

1. Edge nhận TLS, áp network/security policy cơ bản.
2. Gateway tìm route POST /api/orders.
3. Gateway kiểm access token theo issuer/audience/expiry/signature.
4. Gateway kiểm scope orders:write và định danh user/tenant.
5. Gateway dùng **trusted identity** làm quota key, xem user có vượt 10 req/min và tenant có vượt limit không.
6. Gateway quyết định còn capacity/concurrency ở upstream Order không.
7. Gateway bỏ header identity do client tự gửi, chuyển context đã xác minh qua kênh tin cậy.
8. Order kiểm **customerId C-7 có thuộc người gọi/được ủy quyền không**, payload và business invariant.
9. Order tạo bản ghi PENDING và outbox trong transaction nếu xử lý async.
10. Order trả response theo contract; gateway chuyển lại cho client, bảo toàn ý nghĩa.

Ví dụ kết quả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/orders/O-101

{
  "orderId": "O-101",
  "status": "PENDING",
  "statusUrl": "/api/orders/O-101",
  "correlationId": "req-d77f"
}
~~~

Gateway không được tự kết luận OrderConfirmed chỉ vì backend trả 202. Đây mới là mốc **accepted**, không phải kết quả cuối sau Inventory/Payment.

### 21.1. Nếu token hết hạn

Gateway trả 401 theo scheme/contract; không chuyển request sang Order. Client có thể dùng quy trình refresh hợp lệ theo authorization client, không retry token hỏng vô hạn.

### 21.2. Nếu token hợp lệ nhưng scope thiếu

Gateway có thể trả 403. Nếu gateway cho qua vì policy route chưa đủ chi tiết, Order vẫn phải kiểm quyền API/business của mình. Tránh gán 401 cho mọi lỗi vì sẽ tạo refresh-token loop.

### 21.3. Nếu user vượt quota

Gateway trả 429 kèm Retry-After theo chính sách, không gọi Order. Client hạn chế retry tự động và có thông tin hiển thị phù hợp.

### 21.4. Nếu backend Order chậm

Gateway áp overall deadline và trả lỗi gateway phù hợp nếu không có kết quả. Nhưng nếu Order đã commit PENDING, client retry với cùng idempotency key và tra cứu operation. Không tạo đơn mới mù quáng sau timeout.

## 22. Sự khác biệt giữa rate limiting và authentication chống abuse

Một bot gửi 10.000 request/giây với token hợp lệ bị chiếm cắp. Authentication vẫn **thành công** vì token hợp lệ về mặt kỹ thuật. Rate limiting có thể giảm tải, nhưng cần thêm:

- Phát hiện pattern bất thường;
- Token revocation/short-lived token theo policy;
- Per-user/per-client quota;
- Device/risk signals nếu sản phẩm có;
- IP/network reputation theo quy định;
- Audit và incident response;
- Step-up authentication cho operation nhạy cảm.

Ngược lại, rate limiting không biến token giả thành hợp lệ. Mỗi lớp có mục tiêu riêng và cần được thử độc lập.

### 22.1. Tránh brute-force và enumeration

Các endpoint login, password reset, verify OTP, lookup account rất dễ bị lạm dụng. Có thể áp quota theo account, IP, device và risk context. Nhưng rate limit quá nghiêm theo account có thể bị attacker lợi dụng để khóa người dùng hợp lệ (denial of service). Cần thiết kế công bằng và phản hồi không tiết lộ sự tồn tại của tài khoản khi không cần thiết.

### 22.2. Không tiết lộ khác biệt nhạy cảm trong lỗi

Nếu GET /users/email@example.test trả 404 cho account không tồn tại nhưng 403 cho account tồn tại không đủ quyền, response có thể hỗ trợ enumeration. Cần thống nhất security semantics phù hợp use case, không chỉ gom tất cả thành 500.

## 23. Observability cho API Gateway

Để biết gateway bảo vệ và định tuyến đúng, cần đo ít nhất ba chiều: **lưu lượng và hiệu năng**, **chính sách bảo mật**, **upstream health**.

### 23.1. Metrics kỹ thuật

| Metric | Mục đích |
|---|---|
| Requests/s theo route/method | Hiểu tải vào và đường API |
| Gateway latency p50/p95/p99 | Độ trễ tại cổng, chưa bao gồm mọi xử lý downstream nếu không đo |
| Upstream latency p95/p99 | Phân biệt gateway overhead và backend chậm |
| 2xx/4xx/5xx theo route | Phát hiện lỗi API, auth, quota, upstream |
| Authentication failures | Token invalid/expired/issuer/audience mismatch theo nhóm, không log token |
| Authorization denials | Chính sách scope/endpoint và lỗi permission |
| Rate-limited count | Tần suất 429 theo route/tier, tỷ lệ false positives |
| Upstream connect/reset/timeout | Phân biệt network và application error |
| Retry count và attempts/request | Phát hiện amplification |
| Connection pool/concurrency | Chẩn đoán saturation |
| Routing distribution | Canary/zone/region backend traffic |
| Config rollout version | Liên hệ sự cố với thay đổi policy |
| JWKS/quota store availability | Shared dependency có đang ảnh hưởng request? |
| Cache hit ratio nếu có | Mức cache và ảnh hưởng upstream |
| Request/response sizes | Quota bandwidth và payload abuse |

### 23.2. Structured log

Ví dụ:

~~~text
timestamp=2026-11-11T12:00:00Z
correlationId=req-a12
routeId=create-order
method=POST
pathTemplate=/api/orders
principalType=user
tenantKeyHash=t-9bd
authDecision=ALLOW
quotaDecision=ALLOW
upstreamService=order
upstreamStatus=202
gatewayLatencyMs=13
upstreamLatencyMs=84
attempts=1
~~~

Không log nguyên access token, cookie, API key, payment card data hoặc PII không cần thiết. Tránh dùng raw userId/tenantId làm metric labels cardinality cao; có thể dùng định danh được bảo vệ trong logs/traces để điều tra, và aggregate metrics theo route/tier.

### 23.3. Distributed tracing

Trace nên thể hiện các spans:

~~~text
Client
  → Gateway: authenticate
  → Gateway: rate limit
  → Gateway: route
  → Order: create order
  → Order: persist PENDING/outbox
~~~

Nếu Order sau đó gửi async command tới Inventory, trace/correlation phải nối tiếp qua message context hoặc span links phù hợp; gateway chỉ nhìn thấy request đầu không chứng minh toàn bộ nghiệp vụ thành công.

### 23.4. SLO phân lớp

**Gateway SLO:** Request được định tuyến và xử lý policy đúng; thời gian overhead, availability của entry point.

**Service SLO:** Order/Payment xử lý nghiệp vụ đúng và kịp thời.

**Business completion SLO:** Từ client tạo order đến CONFIRMED/REJECTED theo cam kết.

Nếu gateway trả 202 trong 30 ms nhưng Payment backlog dài, gateway performance tốt không đồng nghĩa trải nghiệm đặt hàng tốt.

## 24. Kiểm thử bảo mật và chính sách API Gateway

### 24.1. Authentication cases

1. Không token vào protected route;
2. Token hết hạn;
3. Token chưa có hiệu lực;
4. Token sai issuer;
5. Token sai audience dù signature đúng;
6. Token dùng thuật toán không được phép;
7. kid lạ hoặc JWKS cache đang refresh;
8. Token bị thu hồi theo mô hình hỗ trợ;
9. API key sai/đã rotate;
10. mTLS identity không thuộc allowlist;
11. Header identity giả do client tự gửi;
12. Access token bị thay bằng ID token không đúng mục đích.

### 24.2. Authorization cases

1. User có scope orders:read nhưng gọi POST /orders;
2. User có scope orders:read và gọi GET của order người khác;
3. Tenant A cố dùng identifier của Tenant B;
4. Service account có quyền gọi Catalog nhưng không Payment;
5. Anonymous caller vào public route;
6. Route admin bị route rule chung bắt nhầm;
7. Backend bị gọi trực tiếp bỏ qua gateway;
8. Gateway cấp credential nội bộ quá rộng cho caller không đủ quyền.

### 24.3. Routing cases

1. GET /api/products/123 tới Catalog;
2. POST /api/orders tới Order;
3. Path /api/orders/admin chỉ tới route admin đã có guard;
4. Encoded path hoặc slash khác thường không bypass policy;
5. Route không tồn tại trả 404/deny theo contract;
6. Header/host không khớp không bị route vào default service nhạy cảm;
7. Canary weights và response contract đúng;
8. Rollback route không làm vỡ in-flight requests quá mức;
9. Service discovery cập nhật khi Pod churn;
10. Tenant routing không đổi environment/region ngoài policy.

### 24.4. Rate limiting cases

1. Burst ngắn trong token bucket capacity;
2. Sustained requests vượt refill rate;
3. Cùng user gửi qua nhiều IP;
4. Nhiều user sau cùng NAT;
5. Hai gateway replicas xử lý cùng rate-limit key;
6. Redis/quota store outage và failover;
7. Retry-After được trả đúng semantics;
8. Per-user, per-tenant và global limits tương tác;
9. Một route nặng không vượt giới hạn concurrency;
10. Bot gửi ngẫu nhiên X-Forwarded-For để né IP quota;
11. Gần hết deadline thì request không bị xếp chờ vô hạn;
12. Quota config change/rollback không tạo double allowance ngoài policy.

### 24.5. Reliability cases

1. Gateway replica crash khi request đang chạy;
2. Quota store chậm làm tăng p99;
3. JWKS fetch lỗi nhưng cache còn/đã hết hạn;
4. Order backend 503;
5. Payment backend timeout sau commit;
6. Backend deployment khiến endpoint cũ vẫn còn connection;
7. DNS resolve lỗi;
8. Tất cả backends unready;
9. Một availability zone chết;
10. Load cao có retries ở client và gateway;
11. Request body lớn/decompression bomb;
12. Gateway config sai route 10% traffic.

Từng ca cần định nghĩa **kết quả mong đợi**, lỗi nào trả client và metric/trace nào chứng minh không bị bypass chính sách.

## 25. Bài thực hành: thiết kế API Gateway cho thương mại điện tử

**Bối cảnh:** Có Catalog, Order, Inventory, Payment, Customer, Notification. Web/mobile gọi public API; đối tác gọi một số endpoints riêng. Identity provider cấp access token. Hệ thống chạy nhiều replicas và có traffic burst vào giờ cao điểm.

### Bước 1 — Thiết kế ranh giới

Vẽ sơ đồ client → gateway → domain services. Phân biệt traffic public và internal. Ghi rõ Inventory/Payment có được public trực tiếp không. Nếu gateway là entry point duy nhất, đưa ra cách backend kiểm tra những request thật sự đi qua boundary tin cậy.

**Sản phẩm:** Sơ đồ trust boundary và API exposure.

### Bước 2 — Lập route table

Tối thiểu có:

- GET /api/products/** → Catalog;
- POST /api/orders → Order;
- GET /api/orders/{id} → Order;
- POST /api/payments/** → Payment (hoặc qua Order theo contract);
- GET/PATCH /api/customers/me → Customer;
- /api/partner/** → partner-facing adapter.

Chỉ định method, authentication, scope, upstream service và timeout. Không đặt route chồng lấn không có priority rõ.

**Sản phẩm:** Bảng routes có độ ưu tiên và fallback behavior.

### Bước 3 — Thiết kế xác thực

Giả sử token JWT được IdP ký. Liệt kê các trường gateway phải verify; mô tả JWKS cache/key rotation. Phân biệt access token với ID token. Quyết định backend nhận forwarded token hay internal identity context và vì sao.

**Sản phẩm:** Sơ đồ authentication và policy cho unknown issuer/audience.

### Bước 4 — Phân quyền

Làm rõ:

- Scope orders:write kiểm ở gateway;
- User chỉ sửa order của mình kiểm ở Order;
- Payment hoàn tiền phải kiểm policy của Payment;
- Tenant ID lấy từ nguồn đáng tin;
- Backend không tin X-User-Id tự khai.

**Sản phẩm:** Ma trận endpoint-level và resource-level authorization.

### Bước 5 — Chọn rate policy

Đặt ba mức limit:

1. Anonymous GET theo IP;
2. Authenticated POST theo user và tenant;
3. Global concurrency theo downstream capacity.

Mô tả token bucket với refill rate, burst; định nghĩa khi over quota trả 429, khi upstream quá tải trả 503 theo contract. Xác định global limiter state nếu có ba gateway replicas.

**Sản phẩm:** Bảng policy và quyết định fail-open/fail-closed khi quota store lỗi.

### Bước 6 — Thiết kế failure handling

Giả lập:

- User token hết hạn;
- User thiếu scope;
- Client gửi identity header giả;
- Gateway route sai vì path overlap;
- Token hợp lệ nhưng đọc order người khác;
- Payment timeout sau side effect;
- Redis quota store outage;
- Gateway replica restart;
- Order scale thay Pod IP.

**Sản phẩm:** Error/status table, retry plan và xử lý idempotency.

### Bước 7 — Load test

Đưa 100, 500, 1.000 request/s với các tỷ lệ Catalog/Order/Payment khác nhau. Đo gateway CPU, p95/p99, upstream saturation, rate-limited count và completion SLO. Không chỉ nhìn 429 count; kiểm false positives khi nhiều users chung NAT.

**Sản phẩm:** Baseline capacity và điểm cần bảo vệ trước overload.

### Bước 8 — Viết ADR

So sánh:

- Cho client gọi trực tiếp nhiều service;
- Dùng một gateway cho toàn bộ public APIs;
- Dùng gateway + BFF theo client và regional entry khi thật sự cần.

Nêu business benefits, bảo mật, latency overhead, failure modes, vận hành policy, ownership và điều kiện đánh giá lại.

**Sản phẩm:** ADR có thể được review, không chỉ một sơ đồ triển khai.

## 26. Các quyết định kiến trúc cần ghi vào ADR

Một mẫu có thể dùng:

~~~text
Title: Public API Gateway for Commerce Services

Context:
- Nhóm clients và public contracts:
- Các domain services và owner:
- Identity Provider và token format:
- Latency/SLO và traffic profile:
- API risk/threat assumptions:
- Multi-tenant/partner requirements:

Decision:
- Gateway deployment model:
- DNS/TLS/edge entry:
- Route ownership and versioning:
- Authentication scheme and issuer/audience policy:
- Identity propagation to services:
- Authorization split between gateway and service:
- Rate-limit keys, algorithms and quota:
- Distributed limiter consistency/failure behavior:
- Timeout, retry and circuit breaker:
- Observability, audit and privacy:
- HA/canary/rollback strategy:

Alternatives:
- No shared gateway:
- Ingress/reverse proxy only:
- Gateway plus BFF:
- Cloud-managed vs self-hosted gateway:

Consequences:
- Positive:
- Negative:
- Operational costs:
- Security risks and mitigations:
- Metrics to validate success:
- Conditions to revisit the decision:
~~~

Một ADR hữu ích chỉ rõ **lựa chọn nào đã được chấp nhận**, còn lựa chọn nào cố ý không áp dụng. Không chọn công nghệ trước rồi viết lý do cho khớp.

## 27. Những ngộ nhận thường gặp

**1. “Qua Gateway rồi thì backend không cần kiểm quyền.”**  
Sai. Gateway kiểm identity và policy tổng quát; backend phải kiểm permission trên resource và invariant mà nó sở hữu.

**2. “JWT có signature đúng là đủ.”**  
Sai. Cần issuer, audience, thời hạn, thuật toán và policy; access token dành cho API khác không mặc nhiên được chấp nhận.

**3. “Gateway phải trực tiếp xử lý login/password.”**  
Không mặc định. IdP/authorization server là nơi chuyên trách danh tính, gateway thường kiểm credential đã cấp.

**4. “API Gateway và load balancer giống nhau.”**  
Không hoàn toàn. Load balancing chọn backend instance, gateway còn thực thi API policies và route contract.

**5. “Gateway luôn phải có một IP/process duy nhất.”**  
Không. Logical entry có thể được phục vụ bởi nhiều replicas qua HA edge/LB.

**6. “Giới hạn IP là đủ bảo đảm công bằng.”**  
Không. NAT, nhiều accounts, bot và các operation có cost khác nhau làm quota theo IP không đủ.

**7. “429 nghĩa là backend đang lỗi.”**  
Không nhất thiết. 429 thường là quota/rate limit; 503 thường là unavailable/overload theo contract.

**8. “Bật rate limit sẽ giải quyết DDoS.”**  
Không. DDoS có thể bão hòa network/edge trước gateway; cần phòng vệ nhiều tầng.

**9. “Mọi retry nên được cấu hình tại gateway.”**  
Không. Retry phải tôn trọng semantics và idempotency; POST có side effect không thể retry mù quáng.

**10. “Có 202 từ Order nghĩa là đặt hàng thành công.”**  
Không. 202 thường chỉ là accepted; trạng thái cuối do workflow nghiệp vụ quyết định.

**11. “Chỉ cần mTLS là đã phân quyền user.”**  
Không. mTLS chứng minh workload identity; user/resource authorization là bước riêng.

**12. “Gateway là chỗ thích hợp cho mọi logic dùng chung.”**  
Không. Những rule domain chồng lấn nên nằm đúng bounded context; dùng chung kỹ thuật chưa chắc là business commonality.

**13. “Tất cả private services đều có thể dùng chung một auth header tự khai.”**  
Sai. Phải kiểm nguồn header và trust boundary, tránh spoofing/confused deputy.

**14. “Một route prefix chung sẽ không gây lỗi.”**  
Sai. Path overlap, method matching, encoding và route priority có thể mở sai API.

**15. “Tăng gateway replicas sẽ giải quyết mọi bottleneck.”**  
Không. Quota store, IdP, upstream DB và external provider vẫn có thể là điểm nghẽn.

**16. “Canary 5% route sẽ an toàn cho mọi POST.”**  
Không. Cần compatibility, idempotency và đo business errors; shadow traffic có side effect càng nguy hiểm.

**17. “Gateway log càng nhiều càng tốt.”**  
Không. Token, cookie, dữ liệu thanh toán và PII có thể xuất hiện; cần redaction và quyền audit.

**18. “CORS bảo vệ API khỏi mọi caller không hợp lệ.”**  
Không. CORS là kiểm soát dành cho browser, không thay auth hoặc chống tool/server client.

**19. “Per-tenant quota tại gateway tự bảo đảm data isolation.”**  
Không. Backend/database vẫn phải thực thi đúng ranh giới dữ liệu.

**20. “Config đã qua CI thì không cần canary/rollback.”**  
Không. Config đúng cú pháp vẫn có thể sai route/security policy và gây sự cố diện rộng.

## 28. Câu hỏi ôn tập

1. API Gateway tạo ra lợi ích gì so với để web/mobile gọi trực tiếp từng service?
2. Gateway, reverse proxy, load balancer, ingress, WAF và service mesh khác nhau thế nào?
3. Khi nào logic BFF nên được tách khỏi gateway?
4. Authentication khác authorization ở điểm nào?
5. Tại sao token signature hợp lệ nhưng sai audience vẫn phải bị từ chối?
6. Access token và ID token khác mục đích sử dụng ra sao?
7. JWKS cache và key rotation có nguy cơ vận hành nào?
8. Tại sao không nên tin giá trị X-Authenticated-User do client tự gửi?
9. Khi backend bị truy cập trực tiếp bỏ qua gateway, những lớp kiểm soát nào có thể bị bypass?
10. Vì sao scope orders:read chưa đủ để đọc một Order thuộc người khác?
11. Routing theo hostname/path/header có những nguy cơ route overlap nào?
12. Canary/blue-green được gateway hỗ trợ như thế nào, vì sao contract compatibility vẫn quan trọng?
13. Một API Gateway có nhất thiết biết IP của từng Pod không?
14. Token bucket khác fixed window ở khả năng xử lý burst ra sao?
15. Concurrency limiter bảo vệ gì khác requests-per-second limiter?
16. Nếu có năm gateway replicas, per-instance rate limit 100/s có thể làm global limit sai như thế nào?
17. Khi Redis quota store lỗi, fail-open và fail-closed có lợi/hại ra sao?
18. Khi nào API nên trả 429 và khi nào nên trả 503?
19. Vì sao Retry-After không cho phép client retry cùng lúc với hàng triệu client khác?
20. Nếu gateway retry POST Payment sau timeout, hệ quả nào có thể xảy ra?
21. API Gateway p95 thấp nhưng đơn hàng mất 10 phút để xác nhận; KPI nào đang bị bỏ sót?
22. Rate limiting có thay thế WAF và anti-DDoS ở edge không?
23. Khi nhiều người dùng ở chung NAT, quota theo IP có thể gây false positives ra sao?
24. Tại sao tenant header phải được lấy từ identity đã xác minh?
25. Gateway nên log những định danh gì, và điều gì không được log?
26. Quy tắc CORS có bảo vệ API trước các HTTP client ngoài browser không?
27. Tại sao một gateway chỉ có một process là rủi ro HA?
28. Khi issuer/JWKS không khả dụng, những lựa chọn fail behavior nào có thể có?
29. Làm sao phân biệt lỗi từ gateway authentication với upstream authorization?
30. Vì sao bật cache ở gateway có thể làm lộ dữ liệu giữa tenants nếu cache key sai?
31. Route admin trùng prefix route public có thể gây bypass như thế nào?
32. Khi service discovery trả endpoint cũ, gateway cần xử lý những lỗi gì?
33. Một gateway policy change nên được triển khai và rollback theo chiến lược nào?
34. Khi nào có thể cho GET cache, và vì sao POST Payment không nên retry hoặc mirror tùy tiện?
35. Bạn sẽ đo metrics gì để chứng minh gateway có lợi ích mà không trở thành bottleneck?

## 29. Checklist triển khai

- [ ] Đã xác định public API contract và những service nào không được gọi trực tiếp.
- [ ] Gateway là điểm vào logic nhưng có HA, không phụ thuộc một process đơn lẻ.
- [ ] Route map có host/path/method rõ, priority rõ và default deny.
- [ ] Upstream trỏ tới service logic/discovery, không hard-code instance IP.
- [ ] Có quy trình version/canary/rollback không phá contract.
- [ ] Token được kiểm signature, issuer, audience, time và usage phù hợp.
- [ ] JWKS/key rotation và policy khi IdP lỗi đã được thiết kế.
- [ ] Access token và ID token không bị dùng lẫn vai trò.
- [ ] Identity headers không tin cậy bị xóa/ghi đè ở biên.
- [ ] Gateway–backend có trust channel và xác thực workload thích hợp.
- [ ] Backend vẫn thực thi resource-level và tenant-level authorization.
- [ ] Per-IP coarse, per-user, per-tenant, route-cost và global limits được cân nhắc.
- [ ] Distributed quota có semantics và failure policy rõ.
- [ ] 401, 403, 404, 429, 503 được dùng có ý nghĩa, lỗi không lộ dữ liệu nội bộ.
- [ ] Retry-After được thiết kế để tránh retry storm.
- [ ] Rate limiting phối hợp admission control/backpressure của backend khi cần.
- [ ] Timeout, retry, circuit breaker và idempotency không gây side effect trùng.
- [ ] CORS, payload limit, cache key và response headers được cấu hình theo trust model.
- [ ] Không đưa business rules, payment state hoặc direct database writes vào gateway.
- [ ] Có metrics gateway/upstream, structured logs, traces và redaction secrets.
- [ ] Có kiểm thử route overlap, header spoofing, sai issuer/audience và data isolation.
- [ ] Có kiểm thử burst, multi-replica global quota, quota store outage và upstream timeout.
- [ ] Có canary/rollback cho gateway configuration và ownership/approval rõ.
- [ ] Đã đo SLO ở gateway, backend và kết quả nghiệp vụ end-to-end.
- [ ] Đã ghi ADR về trade-off, operating costs, threat model và điều kiện đánh giá lại.

**Kết luận:** API Gateway cung cấp một nơi nhất quán để **kiểm tra danh tính ở biên, định tuyến public API tới các dịch vụ logic và giới hạn lưu lượng theo chính sách**. Nó có thể giảm coupling của client, tập trung phòng vệ và cải thiện vận hành. Tuy nhiên, gateway không thể thay thế **authorization nghiệp vụ ở service, idempotency, consistency, cơ chế phục hồi hay bảo vệ capacity phía sau**. Thiết kế đúng là phân chia trách nhiệm rõ, giữ policy kiểm thử được, triển khai gateway có HA và quan sát kết quả người dùng xuyên toàn bộ hệ thống.