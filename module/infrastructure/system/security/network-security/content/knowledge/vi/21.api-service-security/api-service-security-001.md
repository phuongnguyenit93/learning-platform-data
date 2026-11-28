# Bảo vệ REST API tại network boundary: thiết kế điểm kiểm soát giữa mạng và dịch vụ

**Network boundary (ranh giới mạng)** là nơi lưu lượng đi qua giữa những vùng có mức tin cậy hoặc quyền truy cập khác nhau, ví dụ Internet → vùng public edge, đối tác → API B2B, VPN → mạng nội bộ, namespace Kubernetes → dịch vụ backend, hoặc một VPC/VNet → VPC/VNet khác. **Bảo vệ REST API tại network boundary** là thiết kế và kiểm chứng những lớp kiểm soát ở các điểm này để **chỉ lưu lượng hợp lệ, đã được phân loại và được phép mới đến đúng API**, đồng thời giới hạn khả năng khai thác, lạm dụng, làm quá tải và di chuyển ngang.

REST API thường phục vụ HTTP/HTTPS với các endpoint theo tài nguyên, ví dụ GET /v1/orders hoặc POST /v1/payments. Khác với trang web chỉ dùng bởi trình duyệt, client của API có thể là **ứng dụng mobile, backend service, thiết bị IoT, đối tác hoặc trình duyệt**, nên không thể coi CORS, session cookie hay một WAF là biện pháp bảo vệ hoàn chỉnh.

Trong chương **API và network service security** của học phần **SECURITY_NETWORK_SECURITY**, bảo vệ API cần kết hợp **phân đoạn, firewall/ACL, VPN, DNS, TLS/mTLS, WAF, API gateway, chống DDoS, IDS/IPS, identity và cloud security**. Điểm then chốt: **network boundary là lớp thực thi cần thiết, nhưng không thay thế authorization theo đối tượng và logic nghiệp vụ trong ứng dụng**. Một yêu cầu đã qua TLS và qua WAF vẫn có thể là yêu cầu trái quyền nếu API không kiểm tra người gọi có được xem đối tượng cụ thể hay không.

Bài học xây dựng kiến trúc tham chiếu, mô hình đe dọa, cấu hình minh họa, kiểm thử phòng thủ và quy trình vận hành. Các tên miền có hậu tố **.example**, IP private và những số liệu trong ví dụ chỉ phục vụ học tập; các lệnh chủ động chỉ dùng trong môi trường do người học quản trị hoặc được phép kiểm thử.

## 1. Mục tiêu học tập

Hoàn thành bài này, người học có thể:

1. Nhận diện những **trust boundaries** mà request REST API phải đi qua và xác định điểm thực thi phù hợp.
2. Phân biệt vai trò của **network firewall, DDoS protection, reverse proxy, WAF, API gateway, identity provider, service mesh và application**.
3. Thiết kế **TLS/mTLS và xác thực endpoint** trên từng chặng, không suy từ HTTPS ở edge ra mã hóa toàn tuyến.
4. Áp dụng authentication/token verification ở edge nhưng vẫn giữ **object-level và function-level authorization** ở backend.
5. Kiểm soát route, HTTP method, request size, Content-Type, header, schema, timeout và những dạng input bất thường.
6. Bảo vệ trước **request flood, bot abuse, credential abuse, resource exhaustion** với rate limit, quota và backpressure.
7. Nhận biết rủi ro **spoofed client IP, forwarded headers, origin bypass, SSRF, CORS/CSRF và API shadow endpoints**.
8. Thiết kế chính sách cho REST API chạy trong cloud/Kubernetes với ingress/egress, identity và segmentation.
9. Tạo ma trận **positive/negative tests** cho phép/chặn, identity, object ownership và tải được phép.
10. Đọc telemetry để điều tra sự cố mà không làm lộ token, dữ liệu cá nhân hoặc bí mật nghiệp vụ.

## 2. Network boundary trong hệ thống REST API là gì?

Ranh giới mạng được xác định bởi **trust level và chính sách truy cập**, không đơn thuần bởi một firewall vật lý. Một request có thể đi qua nhiều ranh giới:

~~~mermaid
flowchart LR
    C[Internet / Partner Client] --> E[DDoS protection / CDN]
    E --> W[WAF / Edge reverse proxy]
    W --> G[API Gateway]
    G --> S[Service firewall / mesh]
    S --> A[REST API]
    A --> D[(Database / Internal Services)]
    I[Identity Provider] -.Issuer, keys, introspection.-> G
    G -.Auth context đã xác minh.-> A
    W -.Security logs.-> SOC[SIEM / SOC]
    G -.API audit/metrics.-> SOC
    A -.Object authorization logs.-> SOC
~~~

Không phải kiến trúc nào cũng có tất cả các khối. Một sản phẩm API gateway có thể tích hợp WAF, rate limit, routing và authentication; một CDN có thể có lớp chống DDoS. **Khả năng thực tế phụ thuộc dịch vụ, phiên bản và cấu hình**. Nhiều lớp chỉ hữu ích khi chúng xử lý **các mối đe dọa khác nhau hoặc giảm blast radius**, thay vì chồng chéo mà không có owner.

### 2.1. Ranh giới theo vị trí

| Ranh giới | Ví dụ | Câu hỏi bảo mật |
|---|---|---|
| **Internet → public edge** | Client bên ngoài vào CDN/WAF | Ai có thể kết nối, có bị flood và bypass origin không? |
| **Edge → origin** | CDN kết nối API gateway riêng | Origin chỉ nhận từ edge được duyệt? TLS origin có verify đúng? |
| **Gateway → application** | Request đã định tuyến vào service | Identity context có đáng tin, route nào được phép? |
| **Application → data/service** | API gọi DB hoặc backend khác | Có kiểm soát egress, service identity và least privilege? |
| **Partner → B2B API** | Doanh nghiệp khác dùng API | Partner identity, quota, IP range và quyền theo tenant? |
| **VPN → internal API** | Nhân viên từ xa gọi API quản trị | Có cần role, MFA, device posture, jump host hay per-app policy? |
| **Pod → Pod / VPC → VPC** | East–west service traffic | Có NetworkPolicy/SG/mTLS và chặn lateral movement? |

**Không phải cứ “nội bộ” là đáng tin.** Máy trạm, container, service hoặc tài khoản đã bị chiếm có thể gửi request độc hại từ vùng được cấp route. Chính sách nên gắn với **identity, ứng dụng, dữ liệu và mục đích truy cập**, thay vì tin mọi IP thuộc private range.

### 2.2. Phân biệt kiểm soát kết nối và kiểm soát dữ liệu

- **L3/L4 controls:** địa chỉ nguồn/đích, port, protocol, zone, route, stateful connection.
- **L7 controls:** HTTP method, path, header, payload, token, schema, API consumer, quota, status code.
- **Business controls:** quyền sở hữu order/account, role tenant, chức năng được cấp phép, điều kiện nghiệp vụ.

Firewall mạng có thể cho phép TCP/443 nhưng **không quyết định một user có quyền GET /v1/orders/42** trừ khi có đủ ngữ cảnh ứng dụng và policy tương ứng.

## 3. Biết mình đang bảo vệ API nào: API inventory

Trước khi viết rule WAF hoặc gateway, cần biết **API surface** thực tế. Nhiều rủi ro phát sinh từ endpoint cũ, staging được công khai, gateway còn route đến service đã ngừng, hoặc cloud ingress ngoài danh sách.

### 3.1. Bản ghi inventory tối thiểu

| Trường | Ví dụ | Giá trị |
|---|---|---|
| API ID / Owner | orders-api / orders-team | Xác định trách nhiệm |
| Environment | production / staging | Ngăn truy cập nhầm môi trường |
| Hostname/route | api.corp.example /v1/orders | Định tuyến và policy |
| Exposure | public, partner, VPN-only, internal | Chọn trust boundary |
| Authentication | OAuth access token, mTLS, workload identity | Không áp sai profile |
| Authorization | user, tenant, scope, object owner | Ai được gọi gì |
| HTTP methods | GET, POST, PATCH, DELETE... | Deny method ngoài hợp đồng |
| Data classification | public, internal, sensitive | Giới hạn log, rate, response |
| Upstream service | app namespace, deployment, port | Phân đoạn và ownership |
| API contract | OpenAPI version, schema ref | Kiểm tra request/response |
| Rate/budget | limit theo consumer & workload | Tránh resource exhaustion |
| Controls | WAF, API gateway, DDoS, SG/NetworkPolicy | Biết nơi enforcement |
| Lifecycle | active, deprecated, retired | Tránh shadow API |
| Telemetry | gateway + app audit + metrics | Khả năng điều tra |

**Một hostname không nhất thiết là một API**: API gateway có thể route nhiều service theo prefix; một service có nhiều versions/hosts; một IP có thể đại diện load balancer hoặc CDN.

### 3.2. Shadow API và stale routes

Một **shadow API** là API/endpoint tồn tại nhưng ngoài quản trị mong muốn. Nguyên nhân thường gồm:
- Developer mở tạm ingress và quên đóng.
- Staging/demo dùng chung hostname hoặc gateway với production.
- Đường /v0, /internal, /debug, /admin còn được publish.
- API Gateway route vẫn trỏ backend cũ.
- Một service có public IP ngoài CDN/WAF.
- Service phát hành endpoint mới nhưng OpenAPI/inventory chưa cập nhật.

Đầu tiên hãy đối soát **service catalog, OpenAPI contract, gateway config, load balancer, cloud inventory, Kubernetes ingress và DNS**. Không cần quét ngẫu nhiên toàn Internet khi đã có dữ liệu quản trị và phạm vi rõ.

## 4. Threat model của REST API tại network boundary

Một threat model hữu ích xác định **tài sản, tác nhân, điểm kiểm soát, đường đi, khả năng đối thủ và tác động**.

### 4.1. Ví dụ: hệ thống Orders API

Giả định:
- Người dùng đăng nhập ứng dụng mobile và lấy access token.
- Đối tác được cấp client credential để đồng bộ đơn.
- REST API public sau CDN/WAF/gateway.
- Orders service cần truy cập database và notification service.
- Admin API chỉ được dùng từ VPN/nhóm quản trị.

Tài sản: đơn hàng, thông tin tài khoản, token, dữ liệu thanh toán, trạng thái đơn, credential backend và khả năng sẵn sàng của dịch vụ.

Đối thủ/nguồn lỗi:
- Client ngoài Internet gửi request không hợp lệ hoặc quá mức.
- User hợp lệ cố truy cập object của user/tenant khác.
- Partner bị lộ key hoặc gửi request ngoài quota.
- Workload nội bộ bị chiếm cố gọi API quản trị.
- Proxy/gateway sai cấu hình làm lộ origin hoặc tin spoofed headers.
- Ứng dụng cho phép gọi URL tùy ý, gây **SSRF**.
- Traffic DDoS làm cạn connection/CPU/backend pool.
- Deployment config drift mở thêm endpoint không được phê duyệt.

### 4.2. Phân biệt các loại kiểm soát

| Rủi ro | Network boundary có thể giảm như thế nào? | Điều backend vẫn phải làm |
|---|---|---|
| Scan/traffic không hợp lệ | ACL, WAF, route allowlist, request size limit | Tránh lộ debug/API không cần |
| Token thiếu/sai | API gateway xác minh issuer/audience/expiry | Authorization theo object/action |
| Request quá mức | Rate limit/quota/bot policy, queue/bulkhead | Giới hạn công việc DB, transaction cost |
| Injection payload | WAF và input validation schema hỗ trợ | Parameterized queries, output encoding, validation đúng ngữ nghĩa |
| BOLA/IDOR | Edge xác thực user/tenant context | So quyền truy cập **từng object** |
| SSRF | Egress proxy/network policy/destination allowlist | Không cho user điều khiển URL tùy ý; xử lý redirect/DNS |
| Origin bypass | Origin firewall/private networking/mTLS edge→origin | Không tin mọi request có đúng header |
| Data leakage | TLS, response header, logging controls | Data minimization, field-level authorization |
| Service-to-service abuse | Segmentation, mTLS, egress ACL | Xác thực workload và RBAC/ABAC nội bộ |
| API DoS | DDoS edge, connection limiting, caching | Backpressure, concurrency limits và timeouts |

**Một WAF “đang bật” không chứng minh mọi OWASP API risk đã được xử lý.** Các lỗi nghiệp vụ như truy cập object trái quyền đòi backend biết **ai sở hữu gì**, điều mà edge không luôn có.

## 5. Kiến trúc phòng vệ nhiều lớp

Có thể tổ chức thành năm lớp:

1. **Reachability:** DNS/routing/firewall đảm bảo chỉ edge được duyệt có đường vào origin.
2. **Transport:** TLS và certificate verification bảo vệ đúng chặng, mTLS khi thích hợp.
3. **Request gate:** gateway/WAF giới hạn HTTP methods/routes, authentication, quota và malformed requests.
4. **Service authorization:** ứng dụng kiểm tra role, tenant, object ownership, dữ liệu và thao tác.
5. **Operations:** logs, metrics, alert, incident response, config drift, secret rotation và SLO.

~~~mermaid
flowchart TD
    PUB[Public client] -->|HTTPS| EDGE[CDN + DDoS]
    EDGE --> WAF[WAF: managed + custom rules]
    WAF --> GW[API gateway: route/auth/quota]
    GW -->|mTLS hoặc TLS được xác thực| APP[REST application]
    APP --> AUTHZ[Object + function authorization]
    AUTHZ --> DATA[(Database)]
    GW -.Rate/error/audit events.-> SOC[SIEM / Observability]
    APP -.Identity/tenant/business audit.-> SOC
    CTRL[Policy as code + approval] -.Controls.-> WAF
    CTRL -.Controls.-> GW
~~~

Trong một triển khai nhỏ, một reverse proxy trước ứng dụng có thể là điểm kiểm soát L7. Với tổ chức lớn, nhiều thành phần đảm nhiệm các chức năng khác nhau. Dù hình thức nào, phải có **owner cho từng chính sách và phép thử chứng minh đường đi thật**.

## 6. Bảo vệ TLS tại edge và trên đường tới backend

**TLS** giảm nguy cơ nghe lén/sửa dữ liệu trên chặng được bảo vệ và giúp client xác thực server theo chứng chỉ. Nhưng nhiều kiến trúc terminate TLS tại CDN, WAF hoặc load balancer.

### 6.1. Hai hoặc nhiều phiên TLS độc lập

~~~text
Client --TLS A--> CDN/WAF --TLS B--> API Gateway --TLS C/mTLS--> Backend API
                   ^                       ^                     ^
                Giải mã A               Giải mã B              Giải mã C
~~~

Mỗi hop có **certificate trust, hostname verification, TLS versions, cipher policy, key management** riêng. Cần xác định:
- Edge đã xác minh HTTPS certificate cho origin đúng tên chưa?
- Gateway có nhận traffic từ edge qua private network hoặc mTLS không?
- Backend có certificate và identity riêng không?
- Có route đi thẳng tới origin bỏ qua WAF không?
- API logs chứa các header hoặc access token quá nhạy cảm không?
- Certificate renewal/rotation có gây downtime không?

**HTTPS trong trình duyệt không tự chứng minh TLS end-to-end tới database.** Sau termination, dữ liệu có thể được xử lý dưới dạng plaintext tại các điểm được phép, vì vậy cần giảm quyền đọc dữ liệu và audit thích hợp.

### 6.2. TLS policy

Với triển khai hiện đại:
- Ưu tiên TLS 1.3; TLS 1.2 có profile mạnh nếu cần tương thích.
- Dùng cipher suite và nhóm trao đổi khóa được tổ chức phê duyệt.
- Kiểm tra certificate chain, hostname/SAN và hiệu lực chứng chỉ.
- Không bật lại phiên bản/cipher cũ chỉ để một client legacy hoạt động mà không đánh giá rủi ro.
- Với mTLS, xác minh danh tính client/workload **và** authorization sau TLS.
- Quản lý private key, session ticket keys và rotation qua hệ thống có quyền phù hợp.
- Kiểm tra HTTP/2, HTTP/3/QUIC nếu edge hỗ trợ, vì đường vận chuyển có khác biệt.

**mTLS chứng minh hai đầu có credential được chấp nhận; không có nghĩa mọi user request bên trong được phép.** Backend vẫn cần kiểm tra nội dung token và quyền nghiệp vụ.

## 7. Authentication ở gateway và authorization trong ứng dụng

Hai câu hỏi không được gộp:

- **Authentication (AuthN):** người gọi/tác nhân là ai, bằng chứng là gì?
- **Authorization (AuthZ):** tác nhân này được gọi **chức năng nào, tài nguyên nào và trên object nào**?

### 7.1. OAuth 2.0 và access token

Một thiết kế API có thể dùng access token do Authorization Server/IdP phát hành. Gateway hoặc resource server kiểm tra token theo **định dạng và hợp đồng tin cậy**.

**Không phải mọi OAuth access token đều là JWT**. Token có thể opaque và cần introspection hoặc cơ chế xác minh do IdP hỗ trợ. Nếu access token là JWT ký số, validation thường xét:

| Kiểm tra | Vì sao cần |
|---|---|
| Chữ ký bằng khóa và thuật toán được phép | Ngăn dùng token bị sửa hoặc giả |
| **Issuer (iss)** | Chỉ chấp nhận IdP được cấp phép |
| **Audience (aud)** | Token phải dành cho API này, không phải dịch vụ khác |
| **Expiry (exp)** và not-before (nbf) khi có | Không dùng token ngoài thời hạn |
| Token type/scope/permission | Không nhầm access token với ID token hoặc loại khác |
| Key ID/JWKS rotation | Tìm đúng khóa với trust policy và cache hợp lý |
| Tenant/client identity | Ánh xạ token vào đúng miền quyền |
| Revocation/session policy | Xử lý token bị thu hồi, logout hoặc account vô hiệu |

**Không dùng ID token của OpenID Connect thay access token** trừ khi giao thức/API được thiết kế rõ cho mục đích đó. ID token nhằm cung cấp thông tin xác thực phiên người dùng cho client; resource server phải chấp nhận đúng loại credential được quy định.

### 7.2. Token validation không đồng nghĩa authorization

Ví dụ GET /v1/orders/42 với token của user Alice:
- Gateway xác minh token do IdP hợp lệ phát hành cho Orders API.
- Gateway cho phép route GET /v1/orders/{id} với scope orders:read.
- Backend kiểm tra **Order 42 có thuộc Alice hoặc tenant mà Alice được phép truy cập không**.

Nếu chỉ kiểm tra scope mà không kiểm tra owner, ứng dụng có thể gặp **Broken Object Level Authorization (BOLA/IDOR)**. Việc đổi order ID không nên giúp người dùng xem đơn của người khác.

### 7.3. Function-level authorization

Một endpoint POST /v1/admin/refunds hoặc DELETE /v1/users/{id} cần quyền chức năng chuyên biệt. Một token hợp lệ có thể chỉ đủ đọc dữ liệu, không đủ tạo hoàn tiền hoặc xóa user.

**Deny by default** cho route/method ngoài danh sách đã phê duyệt. Gateway có thể ngăn gọi admin path từ Internet, nhưng backend vẫn phải kiểm tra role/permission vì đường đi nội bộ hoặc cấu hình edge có thể thay đổi.

### 7.4. Client credentials và machine-to-machine

Đối tác hoặc workload dùng OAuth client credentials có thể nhận token đại diện cho **ứng dụng/client**, không phải một user tương tác. Policy phải giới hạn:
- Client ID và tenant/partner.
- Scopes và permitted methods.
- Audience API.
- Quota, rate limit và egress data.
- Thời hạn token, credential rotation và revoke.
- Mỗi resource/tenant mà client được phép thao tác.

**Không lưu client secret trong mobile app hoặc browser public client** như một credential bí mật dài hạn, vì những môi trường này không bảo đảm giữ được secret.

### 7.5. Sender-constrained tokens

Một số hệ thống nhạy cảm sử dụng **mTLS-bound access tokens** hoặc **DPoP** để ràng buộc việc dùng token với bằng chứng sở hữu khóa. Điều này có thể giảm nguy cơ replay của bearer token bị đánh cắp trong những điều kiện phù hợp, nhưng còn cần gateway/resource server thực thi đúng ràng buộc và bảo vệ key. Không coi mọi JWT có chữ ký là token sender-constrained.

## 8. Chính sách route và HTTP method tại boundary

API Gateway nên biết route nào được public, route nào chỉ cho partner/VPN và route nào internal-only.

### 8.1. Ma trận ví dụ

| Route | Method | Consumer | Policy tại boundary | Policy backend |
|---|---|---|---|---|
| /health/live | GET | Load balancer/monitor | Chỉ nguồn monitor đã duyệt nếu không public | Không lộ cấu hình/secret |
| /v1/products | GET | Public | Rate/cache, request size, bot policy | Chỉ dữ liệu public |
| /v1/orders | POST | User đã đăng nhập | Token hợp lệ, body size, quota | Kiểm tra user, input, transaction |
| /v1/orders/{id} | GET | User hoặc service được cấp | Token + orders:read | Kiểm tra object owner/tenant |
| /v1/partner/reconcile | POST | Partner B2B | mTLS/token + quota riêng | Quyền theo partner và dữ liệu |
| /v1/admin/config | PATCH | Admin qua kênh được quản lý | Không public; VPN/ZTNA + MFA/role | Kiểm tra permission và audit thay đổi |
| /internal/debug | Bất kỳ | Không có | Deny tại public boundary | Không bật trong production |

**Một route có tên /internal không tự trở thành private.** Quyền riêng tư do network path, service identity và enforcement quyết định, không do tên prefix.

### 8.2. Deny method ngoài hợp đồng

Nếu một API chỉ hỗ trợ GET/POST, gateway có thể từ chối những method không dùng. Tuy nhiên cần biết:
- **HEAD** có thể được ứng dụng/framework hỗ trợ theo ngữ nghĩa của GET.
- **OPTIONS** có thể phục vụ CORS preflight khi có client trình duyệt.
- Method override qua header/query cần được quản lý nếu framework hỗ trợ.
- Các method custom có thể hợp lệ với API riêng, phải nằm trong contract.
- Reverse proxy/backend có thể diễn giải request khác nhau nếu parsing không đồng nhất.

**Không loại bỏ OPTIONS bừa bãi** nếu browser client thực sự cần CORS preflight. Cần đồng thời bảo đảm OPTIONS không cung cấp một đường gọi business logic bị bỏ qua auth.

### 8.3. Versioning và endpoint cũ

API v1 và v2 có thể tồn tại song song. Phải có:
- Owner và lịch deprecation.
- Danh sách routes public/internal đúng.
- Chính sách auth và WAF nhất quán.
- Metrics chứng minh client còn sử dụng phiên bản cũ.
- Kế hoạch chặn/remove route sau ngày ngừng hỗ trợ.

**Không xóa v1 ngay khi v2 deploy thành công**, nhưng cũng không giữ một route legacy vô thời hạn chỉ vì sợ ảnh hưởng client không rõ nguồn.

## 9. Chuẩn hóa HTTP và giới hạn request

Một rủi ro tại boundary là **edge và backend hiểu request khác nhau**. HTTP request có path, method, headers, framing và body. Nếu proxy, WAF và app parse/normalize không nhất quán, một số kiểm soát L7 có thể bị vượt qua.

### 9.1. Những nhóm kiểm tra

| Đầu vào | Policy cần cân nhắc | Lỗi có thể xảy ra |
|---|---|---|
| URL path và percent-encoding | Chuẩn hóa và đối chiếu route bằng một cách hiểu nhất quán | WAF match path khác với backend |
| HTTP method | Allowlist theo route, xử lý HEAD/OPTIONS | Method ngoài contract đi vào backend |
| Host/authority/SNI | Xác minh host hợp lệ và route theo host được duyệt | Request tới virtual host sai |
| Headers | Kích thước/số lượng, ký tự hợp lệ, loại bỏ header không tin | Parser ambiguity, identity spoofing |
| Content-Type | JSON hoặc media type đã công bố | Backend parse sai định dạng |
| Content-Length/framing | Một parser thống nhất cho từng hop | Request desynchronization/smuggling |
| Body size | Giới hạn theo route và nghiệp vụ | Memory/CPU exhaustion |
| JSON nesting/arrays | Depth/collection limits | Parsing cost quá lớn |
| Query parameters | Kiểu, độ dài, số lượng, encoding | Query amplification |
| Timeout/deadline | Giới hạn kết nối và upstream request | Slow clients giữ tài nguyên |
| Compression | Giới hạn kích thước sau giải nén | Decompression/resource abuse |

### 9.2. Không chỉ lọc bằng regex WAF

WAF có thể chặn một số mẫu input, nhưng các giá trị như order_id, tenant_id, discount_code và business state cần được validate **theo schema và ngữ nghĩa** tại ứng dụng. Backend phải dùng parameterized queries và safe APIs; network boundary không thay thế an toàn truy vấn database.

### 9.3. Request smuggling và sự bất đồng parser

**HTTP request smuggling/desynchronization** có thể phát sinh khi các hop không thống nhất về ranh giới request, đặc biệt trong một số tổ hợp HTTP/1.1 framing, chuyển đổi HTTP/2↔HTTP/1.1 và triển khai proxy/backend. Phòng vệ trọng tâm:
- Dùng các phiên bản reverse proxy/gateway và HTTP stack được vá.
- Từ chối request framing không hợp lệ/không rõ ràng.
- Cấu hình các hop thống nhất cách xử lý headers và message length.
- Hạn chế những chuyển đổi protocol không cần thiết.
- Dùng kiểm thử chuyên biệt **có quyền trong lab** và xác minh bản vá từ vendor.
- Giám sát dấu hiệu parse errors, 400/502 bất thường và backend request mismatch.

Không nên tự viết bộ lọc dựa trên một chuỗi ký tự và tuyên bố đã loại bỏ mọi request smuggling. Đây là vấn đề **tương tác giao thức giữa nhiều thành phần**.

## 10. Ranh giới tin cậy của IP client và proxy headers

**X-Forwarded-For, Forwarded, X-Real-IP, X-Forwarded-Proto** và những header tương tự có thể được reverse proxy gửi để chuyển thông tin của client gốc tới backend. Nhưng đây là **HTTP headers**, và client Internet cũng có thể tự gửi giá trị cùng tên.

### 10.1. Tấn công nhầm nguồn trong log hoặc policy

Nếu API dùng giá trị X-Forwarded-For đầu tiên do request cung cấp để áp IP allowlist/rate limit, một caller có thể làm hệ thống **tin vào IP giả** nếu gateway không xác minh hoặc viết đè header đúng cách.

~~~mermaid
flowchart LR
    CLIENT[Client ngoài Internet] -->|TCP tới edge| EDGE[Trusted edge proxy]
    EDGE -->|Header client identity do edge xác định| GW[API Gateway]
    GW --> APP[Backend]
    CLIENT -.Header tự khai báo không đáng tin.-> EDGE
    EDGE -.Giới hạn upstream bằng network ACL/mTLS.-> APP
~~~

### 10.2. Thiết kế trust proxy chain

1. Xác định **danh sách proxy/hop được tin** theo mạng, mTLS hoặc identity.
2. Chỉ tin forwarded metadata khi request tới từ **proxy được phép**.
3. Ở ingress đầu tiên, **loại bỏ hoặc tái tạo** các identity headers mà client có thể tự khai báo.
4. Cấu hình trusted proxy count/CIDR theo sản phẩm, tránh tin toàn bộ Internet.
5. Dùng **network peer IP đã xác minh** và chuỗi proxy được kiểm soát để chọn client IP.
6. Ghi đồng thời ingress peer, client IP đã chuẩn hóa và chuỗi proxy phục vụ điều tra theo chính sách.
7. Kiểm tra cả đường trực tiếp tới origin: nếu có, client có thể bypass logic proxy.

**Địa chỉ IP không phải danh tính người dùng.** NAT/CGNAT, proxy và VPN có thể khiến nhiều user chia sẻ cùng IP, còn IP của user có thể thay đổi khi roaming.

### 10.3. Identity headers từ gateway

Một số gateway gửi user/role vào các header nội bộ sau khi xác thực. Backend chỉ nên tin các header đó khi:
- Không có đường client ngoài gửi thẳng tới backend.
- Gateway xóa dữ liệu header do client tự cung cấp.
- Kênh gateway→backend được giới hạn bằng identity/mTLS/ACL.
- Có định dạng/protocol xác thực context phù hợp và khả năng audit.
- Backend tiếp tục xác minh quyền theo object và nghiệp vụ.

Không lấy header **X-User-Role: admin** từ client làm bằng chứng quyền.

## 11. WAF: tác dụng và giới hạn trước REST API

**Web Application Firewall (WAF)** giúp kiểm tra HTTP traffic và áp một số rule/bộ phát hiện ở lớp ứng dụng. Với REST API, WAF có thể hỗ trợ:
- Chặn các mẫu request bất thường và một số loại injection phổ biến.
- Giới hạn method/path/content type đã biết.
- Phát hiện traffic automation và một số tín hiệu bot.
- Phân loại nguồn rủi ro theo reputation/geo nếu hợp quy định.
- Áp challenge/rate policy trong những trường hợp phù hợp.
- Phát sinh log hữu ích cho SOC/incident response.

### 11.1. WAF không thay thế authentication và object authorization

WAF không tự biết user Alice có quyền đọc Order 42 hay không nếu không có mapping business. Nó cũng không tự xác minh JWT trừ khi sản phẩm/policy được cấu hình cho tác vụ đó.

**WAF managed rules có false positive và false negative.** Một request JSON hợp lệ có thể chứa chuỗi giống mẫu SQL/HTML; một request gây lạm dụng nghiệp vụ có thể không chứa chuỗi nghi vấn nào.

### 11.2. Chính sách rollout

Một quy trình phòng vệ hợp lý:
1. Bật **log/monitor mode** khi đánh giá rule mới theo điều kiện sản phẩm.
2. Đo tác động lên client thật, đặc biệt mobile/partner.
3. Xác định rule/path/consumer gây false positive.
4. Tạo ngoại lệ **hẹp** theo endpoint, field, rule và thời hạn thay vì tắt cả WAF.
5. Chuyển sang enforce theo change window/canary.
6. Theo dõi denied legitimate requests và security alerts.
7. Review ngoại lệ/managed rules khi API hoặc vendor cập nhật.

**Chỉ dựa vào WAF action=block không đủ để xác định một cuộc tấn công đã bị ngăn toàn diện.** Có thể origin vẫn công khai trên địa chỉ khác, hoặc request đi từ mạng nội bộ bypass WAF.

## 12. Rate limiting, quota và fairness theo consumer

Một API có thể bị làm quá tải bởi **request hợp lệ về định dạng nhưng quá nhiều hoặc quá tốn tài nguyên**. Rate limiting hạn chế tốc độ tiếp nhận theo một chiều; **quota** giới hạn tổng sử dụng trong khoảng thời gian; **concurrency limits** giới hạn số công việc đang xử lý.

### 12.1. Chọn khóa giới hạn phù hợp

| Khóa | Lợi ích | Giới hạn |
|---|---|---|
| Source IP | Đơn giản ở bước chưa xác thực | NAT/CGNAT gây chung IP, IP đổi, proxy spoofing nếu sai |
| Authenticated user ID | Công bằng theo user | Cần xác minh token trước |
| Client ID/partner ID | Quota theo hợp đồng B2B | Một client có thể đại diện nhiều user |
| Tenant ID | Bảo vệ công suất cho tenant | Tenant lớn cần mức phân bổ riêng |
| Route/method | Giới hạn endpoint đắt tiền | Phải biết cost khác nhau theo tham số |
| Device/session ID | Hỗ trợ hạn chế abuse theo device | Identifier có thể bị thay đổi hoặc giả |
| API key | Dễ tính quota cho consumer | API key là secret, có thể bị lộ/chia sẻ |
| Global concurrency | Bảo vệ backend pool | Không tự đảm bảo fairness theo client |

**Không dùng IP làm khóa rate-limit duy nhất** cho tất cả trường hợp. Một IP của doanh nghiệp hoặc nhà mạng có thể đại diện hàng trăm người dùng hợp lệ.

### 12.2. Token bucket, sliding window và quota

Một số thuật toán thường gặp:
- **Token bucket:** cho phép burst hữu hạn rồi refill với tốc độ cố định.
- **Fixed window:** dễ thực hiện nhưng có thể có burst ở ranh giới cửa sổ.
- **Sliding window:** giảm một số hiệu ứng biên, cần cân nhắc bộ nhớ/tính phân tán.
- **Leaky bucket/queue:** điều tiết lưu lượng/công việc theo tốc độ.
- **Concurrency semaphore:** giới hạn số request cùng lúc.
- **Daily/monthly quota:** giới hạn mức tiêu thụ dài hạn.

Không có một thuật toán phù hợp mọi endpoint. **GET /v1/products** có thể cache tốt, trong khi **POST /v1/reports** tạo truy vấn DB nặng nên cần chính sách cost/concurrency khác.

### 12.3. Phản hồi và trải nghiệm client

Khi vượt rate limit, REST API thường trả **429 Too Many Requests**, có thể kèm **Retry-After** hoặc metadata giới hạn nếu được hỗ trợ và chính sách cho phép. Client nên:
- Tôn trọng Retry-After khi có.
- Dùng exponential backoff với jitter cho lỗi có thể retry.
- Không retry vô hạn.
- Cẩn thận với thao tác **không idempotent** như tạo thanh toán/đơn hàng.
- Sử dụng idempotency key theo thiết kế nếu API hỗ trợ để tránh tạo giao dịch trùng.

**429 là tín hiệu rate/quota, không phải bằng chứng attacker.** Một consumer hợp lệ cũng có thể vượt mức do bug hoặc đợt cao điểm.

### 12.4. Giới hạn phân tán và độ chính xác

Khi API gateway có nhiều instance/region, local counters không tự cho một quota toàn cục chính xác. Cần quyết định:
- Shared store hoặc distributed limiter có độ nhất quán phù hợp.
- Cách xử lý khi store limiter mất kết nối (fail open/fail closed có điều kiện).
- Giới hạn tại edge và backend để tránh một điểm bảo vệ duy nhất.
- Key cardinality, memory, hot tenants và tránh lạm dụng nguồn tài nguyên limiter.
- Kịch bản HA và failover khi một region down.

Không để rate limiter trở thành một **single point of failure** gây ngừng toàn API.

## 13. Chống application-layer DoS/DDoS tại boundary

Một request HTTP nhỏ vẫn có thể tiêu tốn tài nguyên lớn: tìm kiếm thiếu giới hạn, tổng hợp báo cáo, export file, truy vấn liên kết nhiều bảng hoặc thao tác tới dịch vụ bên ngoài. Vì vậy phòng vệ L7 không chỉ đếm số request/giây.

### 13.1. Những tài nguyên cần bảo vệ

- Connection và TLS handshakes.
- Worker threads/event loop, CPU và memory.
- DB connection pool, query time và locks.
- Cache capacity và cache miss rate.
- Queue/broker, external API quota và storage I/O.
- Số lượng file upload hoặc bytes sau giải nén.
- Downstream dependencies như payment/notification services.

### 13.2. Defense in depth cho DoS

~~~mermaid
flowchart TD
    IN[Client requests] --> DDOS[Upstream DDoS/L3-L4 filtering]
    DDOS --> WAF[WAF/bot & route policy]
    WAF --> RATE[Rate/quota/concurrency limit]
    RATE --> GW[Gateway timeouts, payload bounds]
    GW --> APP[Application budgets/backpressure]
    APP --> DB[(DB pool, query cost limits)]
    APP -.SLO/error/queue metrics.-> OBS[Monitoring]
~~~

Nhiều lớp cần **mục tiêu khác nhau**:
- Upstream chống lưu lượng lớn trước khi nghẽn đường.
- Edge giảm traffic HTTP không hợp lệ.
- Gateway thực thi quota/consumer fairness.
- Backend giới hạn chi phí thật, queue, retry và timeout.
- Network/firewall giữ reachability policy, không để origin bị gọi thẳng.

### 13.3. Circuit breaker, retry và bulkhead

- **Timeout/deadline:** ngăn request treo vô hạn.
- **Circuit breaker:** giảm việc tiếp tục gọi dependency đang lỗi.
- **Bulkhead:** cô lập tài nguyên giữa nhóm request/tenant.
- **Backpressure:** từ chối/điều tiết khi backend sắp quá tải.
- **Queue bounds:** tránh hàng đợi tăng vô hạn.
- **Retry budget:** tránh nhiều tầng tự retry cùng lúc làm khuếch đại tải.

Tất cả cần đo trên hệ thống thực. Một timeout quá thấp có thể chặn request hợp lệ; một timeout quá cao có thể làm cạn worker pool.

### 13.4. HTTP status khi quá tải

- **413 Payload Too Large:** body vượt mức được áp.
- **429 Too Many Requests:** vượt giới hạn consumer/route.
- **503 Service Unavailable:** backend/gateway tạm không phục vụ, có thể do quá tải hoặc maintenance.
- **504 Gateway Timeout:** gateway không nhận phản hồi upstream kịp thời.
- **408 Request Timeout:** một số trường hợp request client chưa hoàn chỉnh trong giới hạn thời gian.

**Không dùng status code thay cho điều tra.** 503 có thể do deployment lỗi hoặc DB down chứ không nhất thiết bị DDoS; log, latency và resource metrics quyết định nguyên nhân.

## 14. Bot abuse, credential stuffing và các API nhạy cảm

Các endpoint như login, password reset, OTP, token issuance, voucher redemption và search có thể bị lạm dụng dù request có định dạng hợp lệ.

### 14.1. Bảo vệ login/credential endpoints

- Rate limit theo **account/user và nguồn đã chuẩn hóa**, không chỉ IP.
- Chặn hoặc điều tiết theo anomaly/velocity và tín hiệu rủi ro.
- MFA phù hợp với use case.
- Phản hồi không làm lộ account existence ngoài mức được policy chấp nhận.
- Kiểm soát reset/OTP resend và chi phí gửi email/SMS.
- Giới hạn lockout để tránh attacker khóa hàng loạt tài khoản hợp lệ.
- Giám sát tỷ lệ login failure/success, token issue và unusual client patterns.
- Đảm bảo credential không bị ghi vào access logs.

### 14.2. Bot challenge không phải giải pháp cho mọi API

Challenge trình duyệt có thể phá vỡ client API machine-to-machine hoặc mobile app. Với partner API, dùng client identity, mTLS/sender-constrained token, quotas và policy doanh nghiệp sẽ phù hợp hơn CAPTCHA đặt trên mọi request.

### 14.3. Enumeration và data scraping

REST API public có thể bị truy vấn lặp để trích xuất dữ liệu. Cần kết hợp:
- Object-level authorization và field-level access.
- Pagination limits và query cost budget.
- Consumer quotas, anomaly detection.
- Cache policy và dữ liệu public/private rõ ràng.
- Data minimization: không trả quá nhiều trường chỉ vì API schema có chúng.
- Audit và giới hạn export/bulk endpoints.

**Bảo vệ khỏi scraping không đồng nghĩa chặn mọi crawler**: xác định dữ liệu công khai, quyền sử dụng và chính sách sản phẩm trước khi áp rule.

## 15. CORS và CSRF: bảo vệ đúng lớp client

**CORS (Cross-Origin Resource Sharing)** là chính sách do **trình duyệt** thực thi để quyết định liệu JavaScript từ origin khác có thể đọc response. CORS **không phải firewall** và không ngăn curl, backend service hoặc mobile client gửi request.

### 15.1. Các lỗi CORS thường gặp

- Cho phép tất cả origins cho API nhạy cảm mà không đánh giá dữ liệu.
- Phản chiếu Origin tùy ý rồi bật credentials.
- Sai cấu hình Access-Control-Allow-Credentials với wildcard origin.
- Đưa API bảo vệ bằng cookie vào cross-origin mà không có chính sách CSRF phù hợp.
- Chỉ test từ browser rồi cho rằng API không thể bị gọi từ client khác.

**Một token bị lộ** vẫn có thể được dùng bởi client ngoài browser tùy thiết kế; CORS không thay thế authentication.

### 15.2. CSRF khi dùng cookie/session

Nếu API sử dụng **cookie tự gửi tự động** bởi trình duyệt, các thao tác thay đổi trạng thái có thể cần CSRF defenses như token, SameSite cookie và kiểm tra Origin/Referer phù hợp. Khi dùng bearer token trong Authorization header do client chủ động thêm, mô hình CSRF khác, nhưng vẫn phải phòng **XSS/token theft** và những đường browser credentials khác.

Đánh giá CORS/CSRF dựa trên **cách client gửi credential thật**, không áp một mẫu bất biến cho mọi REST API.

## 16. SSRF và kiểm soát egress từ API

**Server-Side Request Forgery (SSRF)** xảy ra khi một API khiến server thực hiện yêu cầu đến một đích mà attacker có thể ảnh hưởng vượt quyền dự kiến, ví dụ chức năng nhập URL, webhook, fetch image hoặc chuyển đổi tài liệu.

**Network boundary không chỉ có ingress.** Tại API/backend cần cả **egress boundary**, ngăn service truy cập metadata service, mạng management, DB hoặc endpoint không thuộc nhiệm vụ.

### 16.1. Kiến trúc egress an toàn

~~~mermaid
flowchart LR
    API[REST API] --> EGRESS[Egress policy / proxy]
    EGRESS --> ALLOW[Approved partner endpoint]
    EGRESS -.Deny.-> META[Cloud metadata / control-plane]
    EGRESS -.Deny.-> MGMT[Management / internal sensitive subnets]
    EGRESS -.Deny.-> OTHER[Unapproved destinations]
    EGRESS -.Logs.-> SOC[SIEM]
~~~

### 16.2. Những biện pháp kết hợp

1. Không để request client tự quyết định URL tùy ý khi không cần.
2. Chọn destination theo **allowlist ứng dụng** hoặc partner IDs được quản trị.
3. Giới hạn scheme/protocol, port, redirects và các URL forms được phép.
4. Kiểm tra DNS resolution và nguy cơ **DNS rebinding** trong luồng kết nối.
5. Chặn private/link-local/metadata endpoints theo policy, đặc biệt trong cloud.
6. Áp **network egress ACL, Kubernetes NetworkPolicy, security group, proxy** theo đường thực tế.
7. Dùng IAM tối thiểu, tránh metadata credential có quyền quá rộng.
8. Giới hạn timeout, response size, redirect count và chi phí tải nội dung.
9. Audit outbound requests và alert trên destination khác baseline.

**Chỉ kiểm tra chuỗi URL bằng cách tìm từ khóa không đủ chống SSRF**. DNS có thể thay đổi, redirect chuyển đích, định dạng IP có nhiều biểu diễn và mạng có các đường đi khác nhau. Cần kiểm tra destination kết nối thực và egress policy độc lập.

## 17. Bảo vệ origin: không cho gọi trực tiếp bỏ qua WAF/gateway

Một sai lầm thường gặp: API public qua CDN có WAF, nhưng origin load balancer vẫn có public IP và chấp nhận kết nối trực tiếp từ Internet.

### 17.1. Những lớp chống origin bypass

- Origin ở **private subnet** khi kiến trúc cho phép.
- Firewall/security group chỉ cho **CDN/edge/gateway** được phê duyệt kết nối, cập nhật IP ranges theo cơ chế nhà cung cấp.
- **mTLS** hoặc chứng minh caller identity trên đường edge→origin khi phù hợp.
- Kiểm tra Host/SNI và certificate ở origin, không dựa vào header có thể giả.
- Không có đường public cũ/alternate hostname/IP chưa quản lý.
- Origin không cho truy cập admin/debug routes trực tiếp.
- Kiểm thử network path từ những nguồn **không được phép** trong lab/phạm vi được duyệt.

**Một custom secret header do CDN gửi có thể bổ sung lớp kiểm soát**, nhưng nếu bị lộ hoặc origin vẫn nhận từ Internet, nó không mạnh bằng network isolation và peer authentication. Không coi một header hardcoded là bằng chứng mTLS.

### 17.2. Không chỉ bảo vệ inbound 443

Các management ports, health endpoints, metrics endpoints, SSH/RDP và database ports phải được bảo vệ riêng. Không đặt API admin tại cùng route public nếu không có policy rõ; không cho các dịch vụ backend lắng nghe trên mọi network interface ngoài nhu cầu.

## 18. REST API trong Kubernetes và cloud

### 18.1. Tách ingress, service và workload

Một triển khai Kubernetes có thể gồm:
- **Cloud LB** nhận traffic.
- **Ingress controller hoặc Gateway API** áp route/TLS/auth plugins.
- **Service** phân phối đến Pods.
- **NetworkPolicy/CNI** điều khiển luồng Pod↔Pod và egress nếu được hỗ trợ/thực thi.
- **Service mesh** cung cấp workload identity/mTLS/policy tùy kiến trúc.
- **Application** xác thực object và business permissions.

~~~mermaid
flowchart TD
    INTERNET[Client] --> LB[Cloud LB]
    LB --> ING[Kubernetes Gateway / Ingress]
    ING --> SRV[Service]
    SRV --> POD[REST API Pods]
    POD --> DB[(DB / downstream)]
    NP[NetworkPolicy + Cloud SG] -.Ingress/Egress controls.-> POD
    MESH[Mesh identity / mTLS] -.Workload policy.-> POD
    OBS[Logs / Metrics / Tracing] -.Observe.-> ING
    OBS -.Observe.-> POD
~~~

**Ingress/Gateway resources không tự thay thế NetworkPolicy**, và **NetworkPolicy không tự thực thi** nếu CNI không hỗ trợ semantics được yêu cầu. Cũng cần hiểu cloud load balancer/security group, host networking, IPv6 và các đường admin/service khác.

### 18.2. Các vấn đề cần kiểm chứng

| Vùng | Kiểm chứng |
|---|---|
| Cloud WAF/CDN | Policy gắn đúng hostname/route và origin không bypass |
| Load balancer | Listener TLS, security policy, healthy targets, client IP handling |
| Kubernetes Gateway/Ingress | Route/hostname/method, TLS termination, auth và defaults |
| NetworkPolicy | Chỉ cho namespace/service được phép vào Pod và outbound cần thiết |
| Service mesh | mTLS peer identity, authorization và đường bypass |
| API Pods | Không chạy quyền admin không cần thiết, secret từ cơ chế an toàn |
| Database | Không public, chỉ API identity được phép, auth bắt buộc |
| DNS | Public/private zones, không nhầm backend route |
| CI/CD | Image scan, secrets, policy as code, provenance |
| Cloud audit | IAM thay đổi LB/WAF/route/SG, API key và token key rotation |

### 18.3. Multi-region và failover

Một WAF/gateway có thể hoạt động tốt ở region A nhưng khi failover tới region B, backend mới có thể thiếu:
- Policy allow/deny tương đương.
- JWT issuer/JWKS cache/IdP connectivity.
- mTLS cert và CA trust bundle.
- Rate limit counters/quota nhất quán.
- DNS/private endpoints, database route và firewall.
- Log forwarding/SIEM collectors.
- DDoS capacity hoặc connection limits.

Cần test **security parity khi failover**, không chỉ test khả năng 200 OK. Luồng bị cấm phải tiếp tục bị cấm ở region dự phòng.

## 19. Cấu hình minh họa ở reverse proxy và gateway

Các ví dụ sau là **mẫu học tập**, không phải cấu hình production hoàn chỉnh. Không sao chép vào hệ thống thật trước khi xác định sản phẩm/version, trust chain, backend route và policy bảo mật.

### 19.1. Nginx: giới hạn tải và proxy request cơ bản

~~~nginx
# Ví dụ rút gọn: limit_req_zone thường đặt trong khối http
http {
    limit_req_zone $binary_remote_addr zone=public_api:10m rate=20r/s;

    upstream api_backend {
        server 10.30.20.15:8080;
    }

    server {
        listen 443 ssl;
        server_name api.lab.example;

        ssl_certificate     /etc/tls/lab/fullchain.pem;
        ssl_certificate_key /etc/tls/lab/private.key;

        client_max_body_size 1m;
        client_header_timeout 10s;
        client_body_timeout 15s;
        send_timeout 15s;

        # Ví dụ cơ bản: chưa phải chính sách đủ cho authenticated API.
        location /v1/ {
            limit_req zone=public_api burst=40 nodelay;
            limit_req_status 429;

            proxy_set_header Host $host;
            proxy_set_header X-Request-ID $request_id;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Dùng địa chỉ peer trực tiếp thay vì nối mù header từ client.
            # Chain nhiều trusted proxies cần cấu hình real_ip riêng.
            proxy_set_header X-Forwarded-For $remote_addr;

            proxy_connect_timeout 5s;
            proxy_read_timeout 20s;

            proxy_pass http://api_backend;
        }

        # Không public quản trị/debug.
        location /internal/ {
            return 404;
        }
    }
}
~~~

Giới hạn cần hiểu:
- Đây là ví dụ **rate limit theo IP**, không có identity-aware quota, OAuth/JWT validation hoặc WAF.
- **proxy_pass http://...** chỉ phù hợp lab/backend tin cậy trong ví dụ; production có thể cần **HTTPS/mTLS và xác minh chứng chỉ upstream**.
- Nginx config ở đây không tự giới hạn mọi URL ngoài /v1; cần có **default deny/default route policy** đúng.
- Nếu có CDN đứng trước, **$remote_addr có thể là IP CDN**, làm rate limit sai theo consumer; cần cấu hình trusted proxy chain, không nhận X-Forwarded-For tùy ý.
- Cần thêm TLS profile, request logging an toàn, header-size limits, health checks, HA và upstream/backpressure.
- **return 404** cho một route không chứng minh một origin khác không có đường truy cập đó.

### 19.2. Pseudopolicy của API gateway

~~~yaml
# Ví dụ policy logic; không phải schema chính thức của một gateway.
api: orders
version: v1
public_hosts:
  - api.lab.example
routes:
  - path: /v1/products
    methods: [GET]
    authentication: optional
    rate_limit:
      key: verified-client-ip
      budget: low-cost-public-read
    body_limit_bytes: 16384

  - path: /v1/orders
    methods: [POST]
    authentication:
      type: oauth2-access-token
      issuer: https://id.lab.example/
      audience: orders-api
    authorization:
      required_scope: orders:write
      backend_object_check: required
    rate_limit:
      key: authenticated-subject-and-tenant
      budget: write-operation
    body_limit_bytes: 65536

  - path: /v1/admin/config
    methods: [PATCH]
    exposure: private-only
    authentication: managed-admin-identity
    authorization:
      role: platform-admin
      backend_permission_check: required

defaults:
  unknown_route: deny
  unknown_method: deny
  client_identity_headers: strip-and-rebuild
  upstream_tls: verify-peer
~~~

Cần **chuyển pseudopolicy thành cấu hình đúng của sản phẩm** và kiểm tra backend thực thi object authorization. Một số gateway không hỗ trợ mọi chức năng nêu trên; một policy có tên giống nhau chưa chắc có cùng semantics.

### 19.3. OpenAPI giúp gì?

**OpenAPI** có thể mô tả routes, request/response schemas, authentication schemes và những yêu cầu security chung. Nó giúp:
- Phát hiện API drift ngoài contract.
- Tạo test cases chính xác cho method/path/content type.
- Phân loại route cần token, scope hoặc mTLS.
- Xác định input size/schema và response fields.

Nhưng OpenAPI security declaration **không tự tạo enforcement**, và khai báo không thể tự mô tả đầy đủ quyền sở hữu từng object của mỗi tenant. Cần cả gateway config và code-level authorization tests.

## 20. Quan sát, audit và bảo vệ dữ liệu log

Tại boundary, logging cần trả lời: **ai gọi API nào, qua hop nào, bị chặn/cho phép ở đâu, tại sao và backend có xử lý thành công không?**

### 20.1. Các trường telemetry hữu ích

| Trường | Vai trò | Lưu ý bảo mật |
|---|---|---|
| Event time, timezone, ingest time | Dựng timeline | Đồng bộ đồng hồ và thời gian nguồn |
| Request/correlation ID | Nối edge → gateway → app | Không coi ID do client gửi là bằng chứng danh tính |
| Edge/LB/gateway instance | Tìm điểm thực thi | Đủ metadata, không lộ secret |
| Authenticated subject/client ID | Attribution theo policy | Pseudonymization nếu cần |
| Tenant/service identity | Kiểm soát quota và điều tra | Giới hạn quyền đọc logs |
| Normalized client IP & trusted proxy path | Giải thích nguồn | Không tin forwarded headers không kiểm chứng |
| Method và route template | Phân loại request | Tránh lưu ID nhạy cảm trong raw path nếu không cần |
| AuthN/AuthZ decision | Phân biệt 401/403 và BOLA denial | Không log toàn bộ token |
| WAF rule/action | Triage false positive và threat | Log rule/version và mode |
| Rate/quota/concurrency decision | Nhận diện overload/abuse | Không phơi quota của tenant khác |
| HTTP status và upstream status | Phân biệt edge vs backend errors | 5xx không tự là tấn công |
| Latency, bytes, request cost | Giám sát sức khỏe | Giữ sampling và cardinality hợp lý |
| TLS version, peer identity khi phù hợp | Kiểm tra transport policy | Không log session secrets |
| Change/policy version | Dò cấu hình drift | Có audit actor/approval |

### 20.2. Những thứ không nên log

- Authorization bearer tokens, OAuth client secrets, API keys, private keys.
- Session cookies, OTP, password reset tokens, credentials.
- Toàn bộ payment/PII hoặc body nhạy cảm nếu không có cơ sở và kiểm soát.
- Query parameters chứa secret; URL có thể xuất hiện trong proxy logs nếu không lọc.
- Raw uploaded files không cần thiết.
- Mã truy cập admin hoặc token nội bộ trong error traces.

**Ẩn token trong response nhưng ghi lại trong access log vẫn là rò rỉ.** Cần review log ở CDN/WAF/gateway, ứng dụng, APM, traces và error reporting.

### 20.3. Giới hạn của IDS/NDR khi có TLS

NIDS trước TLS termination có thể quan sát IP, port, timing và một số handshake metadata, nhưng không đọc HTTP payload được TLS mã hóa. WAF/gateway/endpoint ở điểm giải mã có thể cho telemetry L7 phù hợp quyền.

Khi traffic chuyển sang CDN, VPN hoặc region khác, sensor coverage có thể thay đổi. **Số alert giảm sau đổi route không tự chứng minh nguy cơ giảm**; cần đánh giá lại điểm quan sát và log pipeline.

## 21. Giám sát SLI/SLO và phát hiện sai lệch chính sách

Một API có thể an toàn về authentication nhưng vẫn không đạt availability; ngược lại API trả 200 nhanh vẫn có thể lộ dữ liệu do sai authorization.

### 21.1. SLI quan trọng

- **Availability/success rate** cho business transactions.
- **Latency p50/p95/p99** theo route và consumer.
- **HTTP 4xx/5xx** phân nhóm theo edge/gateway/backend.
- **401/403** theo route, tenant và auth policy.
- **429 và limiter saturation** để phát hiện quota phù hợp hay quá chặt.
- **DDoS/WAF actions** và false-positive impact.
- **Origin bypass detections** và đường public không có owner.
- **Backend concurrency, DB pool, queue depth, retries**.
- **Certificate expiry, TLS handshake failures, mTLS policy failures**.
- **Policy drift** giữa các regions/environments.
- **Telemetry loss, log ingest delay**.
- **Denied-flow tests** định kỳ trên route nhạy cảm.

### 21.2. Không tối ưu chỉ một chỉ số

Nếu giảm error rate bằng cách **bỏ auth**, đó là thất bại bảo mật dù dashboard availability có đẹp hơn. Nếu chặn mọi user bằng WAF, số request độc hại tới backend có thể về 0 nhưng dịch vụ cũng không còn dùng được.

Đánh giá đồng thời **security decision quality, application SLO, legitimate traffic success và capacity**.

### 21.3. Xác nhận thay đổi theo từng vùng

Một cloud API có thể được triển khai sang nhiều region. Sau policy change cần kiểm tra:
- Route/method và auth rules giống ý định giữa các zones.
- JWKS issuer/audience và key rotations.
- Rate quota vẫn công bằng hoặc được định nghĩa là per-region.
- Origin chỉ nhận từ edge hoặc mạng được duyệt.
- TLS cert/trust bundle, WAF rule revisions và DNS.
- Log retention và alert routing.

## 22. Ma trận kiểm thử REST API tại network boundary

**Chỉ thử trên lab/staging hoặc endpoint được phép kiểm tra.** Các ca chủ động dưới đây phải có giới hạn tải/đường đi và không làm ảnh hưởng người dùng sản xuất.

| ID | Kịch bản | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| B01 | Client hợp lệ gọi GET public | 200/response theo contract | Edge/gateway/app logs |
| B02 | Client không token gọi route private | 401 hoặc quyết định auth phù hợp | Auth gateway logs |
| B03 | Access token hết hạn | Từ chối | Token validation logs |
| B04 | Token issuer/audience sai | Từ chối | Identity validation evidence |
| B05 | Token có scope đọc gọi method ghi | 403/deny theo policy | Gateway + backend authZ |
| B06 | User A yêu cầu object của user B | Từ chối ở backend | Object-level authorization tests |
| B07 | Partner chỉ có quyền tenant X gọi tenant Y | Từ chối | Tenant authZ audit |
| B08 | Method không có trong contract | 405 hoặc deny route theo cấu hình | Route policy |
| B09 | Path /internal/admin từ Internet | Không reachable/deny | Boundary policy + flow |
| B10 | Request body vượt ngưỡng ở lab | 413/deny và backend không cạn tài nguyên | Gateway logs, resource stats |
| B11 | Sai Content-Type hoặc JSON schema | 4xx hợp lý, không vào business logic trái ý | Validation logs |
| B12 | Forwarded client IP tự khai báo | Không dùng để vượt rate/IP policy | Ingress peer vs normalized IP |
| B13 | Origin trực tiếp từ nguồn ngoài danh sách | Bị chặn | SG/firewall/mTLS logs |
| B14 | Edge→origin certificate sai | Không bỏ verification | TLS upstream logs |
| B15 | Rate limit tại tải lab hợp lệ có kiểm soát | 429 tại ngưỡng theo thiết kế | Limiter counters, Retry-After |
| B16 | Quota của partner A và B độc lập | Không ảnh hưởng ngoài policy | Consumer quotas |
| B17 | Backend dependency chậm trong lab | Deadline/bulkhead/circuit breaker hoạt động | Queue/latency metrics |
| B18 | CORS browser với Origin không được phép | Trình duyệt không đọc response theo policy | Browser preflight/response |
| B19 | CSRF scenario với cookie session | Có cơ chế phòng vệ theo auth scheme | SameSite/token/Origin checks |
| B20 | App tính toán URL outbound | Egress chỉ tới destination allowlist | Proxy/SG/egress logs |
| B21 | IPv6 client tới API | Cùng auth/TLS/WAF policy với IPv4 | IPv6 route + policy |
| B22 | mTLS client không đúng danh tính | Từ chối | Gateway TLS + identity logs |
| B23 | CDN failover sang region B | Positive và negative cases vẫn đúng | Policy version + app transactions |
| B24 | Client mobile/partner hợp lệ | Không bị chặn sai bởi WAF/quota | Canary/false positive evidence |
| B25 | Log pipeline tạm lỗi | Có alert thiếu telemetry | Collector/ingest health |
| B26 | Unknown hostname/route | Không định tuyến vào sensitive backend | Default route/404/deny |
| B27 | API version đã retired | Không còn public access theo kế hoạch | Gateway inventory + regression |
| B28 | Backend direct service-to-service access | mTLS/authZ/NetworkPolicy đúng | CNI/mesh + app audit |

**Không đánh dấu PASS nếu chưa có kết quả thực tế.** Ghi test owner, thời điểm UTC, client identity, version config, request ID và quyết định tại từng lớp. Status có thể là **PASSED, FAILED, NOT_RUN, BLOCKED hoặc INCONCLUSIVE**.

## 23. Thực hành kiểm tra an toàn, không tạo tải

Các ví dụ chỉ dành cho API lab do người học quản trị hoặc được cấp quyền. Domain **api.lab.example** là placeholder không phải endpoint đang chạy. Không sử dụng vòng lặp gửi hàng nghìn request để “thử” rate limit khi chưa có môi trường cô lập và phê duyệt.

### 23.1. Xem TLS/certificate của API lab

~~~bash
# Thay hostname bằng API lab của bạn
openssl s_client \
  -connect api.lab.example:443 \
  -servername api.lab.example \
  -verify_hostname api.lab.example \
  -verify_return_error \
  -brief < /dev/null
~~~

**-servername** gửi SNI; **-verify_hostname** giúp kiểm tra tên theo OpenSSL, với trust store phù hợp. TLS handshake thành công **không** chứng minh upstream edge→origin được bảo vệ hoặc API authZ đúng.

### 23.2. Gửi request GET nhỏ được cấp quyền

~~~bash
# Xem header và response của route public trong lab
curl --fail-with-body --silent --show-error \
  --max-time 10 \
  -D - \
  https://api.lab.example/v1/products
~~~

Nếu bản curl không hỗ trợ **--fail-with-body**, có thể thay bằng cách dùng **curl -i** và tự xem HTTP status trong lab. Không đưa access token thật vào lệnh/traces chia sẻ công khai.

### 23.3. Quan sát method không hỗ trợ

~~~bash
# Chỉ một request trong lab; biết rằng endpoint lab có tồn tại
curl --silent --show-error \
  --max-time 10 \
  -i -X OPTIONS \
  https://api.lab.example/v1/orders
~~~

Kết quả có thể là 200/204 cho CORS preflight, 405 hoặc quyết định chính sách khác. **OPTIONS không mặc nhiên đáng ngờ**; điều cần kiểm tra là nó có bị dùng để bỏ qua auth hoặc gọi business logic hay không.

### 23.4. Đọc response status thay vì đoán nguồn lỗi

Ví dụ giả định:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 5

{"error":"rate_limit_exceeded","request_id":"lab-request-42"}
~~~

Đây là **response minh họa**. Một 429 có thể do edge, gateway hoặc backend gửi; cần **request ID, policy version và log tương ứng**. Không kết luận đó là DDoS chỉ vì client vượt quota.

### 23.5. Kiểm tra quyết định trong nhiều điểm

Một test nên thu:
1. **Client:** request method/path, thời gian, response/status.
2. **Edge/WAF:** route, action, rule ID và normalized client IP.
3. **Gateway:** authentication/authorization/quota decision.
4. **Backend:** object-level permission, data access, application result.
5. **Network:** flow/SG/NetworkPolicy khi cần chứng minh segmentation.

Tránh đưa raw Authorization header, cookie, access token hoặc dữ liệu cá nhân vào bằng chứng.

## 24. Chẩn đoán lỗi khi áp chính sách boundary

### 24.1. Gateway trả 401 cho tất cả request

**Khả năng:** issuer/audience sai, JWKS không lấy được, clock skew, token type không phù hợp, client gửi thiếu header, hoặc gateway policy mới.

**Kiểm tra:** token metadata không nhạy cảm, logs auth, trust issuer, key rotation và client configuration. Không tắt signature verification để “khôi phục nhanh”.

### 24.2. Token hợp lệ nhưng nhận 403

**Khả năng:** thiếu scope/role, tenant mismatch, object ownership không hợp lệ, policy ở gateway hoặc app deny.

**Kiểm tra:** request ID và authZ decision ở cả hai lớp. Một 403 có thể là **hành vi bảo mật đúng**; không tự mở quyền nếu không có approval.

### 24.3. IP allowlist hoạt động bất thường sau khi thêm CDN

**Khả năng:** origin thấy IP của CDN thay vì client, hoặc cấu hình trusted proxy chain sai.

**Kiểm tra:** peer IP tại gateway, CIDR proxy được tin, X-Forwarded-For processing và WAF identity. Không tin mọi X-Forwarded-For từ Internet.

### 24.4. API trả nhiều 429 cho khách hợp lệ

**Khả năng:** rate limit chỉ theo IP sau CGNAT, local counters mất đồng bộ, quota chưa phù hợp hoặc retry storm từ mobile app.

**Kiểm tra:** authenticated user/client/tenant, actual load, Retry-After, log limits và error budget. Điều chỉnh theo dữ liệu và quyền, không tắt limiter toàn hệ thống.

### 24.5. API trả 502/504 khi backend còn CPU thấp

**Khả năng:** DNS/route không đúng, upstream TLS verify fail, connection pool, network policy, timeout, DB dependency hoặc policy version bị drift.

**Kiểm tra:** edge/gateway/upstream status, route, TCP/TLS logs, dependency metrics, firewall/SG. Không kết luận chỉ cần tăng CPU.

### 24.6. WAF chặn upload JSON hợp lệ

**Khả năng:** body-size/depth limit, signature false positive, content encoding hoặc rule chỉ nên áp một endpoint.

**Kiểm tra:** rule ID, payload mẫu đã redacted, route/method, schema và business need. Tạo ngoại lệ **hẹp** thay vì vô hiệu toàn WAF.

### 24.7. API chỉ lỗi trên IPv6 hoặc HTTP/3

**Khả năng:** IPv6 firewall, load balancer listener, DNS AAAA, QUIC UDP/443, TLS config hoặc gateway compatibility.

**Kiểm tra:** address family, protocol, DNS và edge logs riêng. Thành công trên IPv4/TCP không chứng minh IPv6/QUIC đã đúng policy.

### 24.8. API chạy qua edge nhưng direct-origin cũng truy cập được

**Khả năng:** origin public route/SG cho toàn Internet, alternate hostname, wrong firewall attachment hoặc mTLS không bắt buộc.

**Khắc phục:** đặt origin private khi có thể, giới hạn ingress theo edge identity, kiểm tra route dự phòng và bổ sung negative test.

## 25. Runbook phản ứng khi API bị lạm dụng hoặc có dấu hiệu vượt boundary

### Giai đoạn A — Phát hiện và phân loại

1. Xác định loại vấn đề: **availability, auth abuse, route bypass, data exposure, config drift hay nghi vấn mã độc**.
2. Ghi thời điểm, hostname, API ID, route/method, vùng cloud và policy version.
3. Tương quan WAF/gateway logs với app authZ, IdP, database và flow logs.
4. Phân biệt surge hợp lệ (sự kiện kinh doanh, deployment) với hành vi lạm dụng.
5. Xác định ảnh hưởng tới user, tenant, dữ liệu và các dependency.
6. Bảo toàn log/evidence theo quyền, tránh xuất token/secrets.

### Giai đoạn B — Giảm tác động có kiểm soát

- Nếu **request flood**: áp limit/challenge cho nhóm route/consumer phù hợp, phối hợp upstream DDoS protection; tránh chặn nhầm toàn người dùng hợp lệ.
- Nếu **credential abuse**: xem MFA/rate/account security và thông tin IdP; không lock toàn bộ user thiếu cơ sở.
- Nếu **token/credential lộ**: revoke/rotate theo capability, điều tra log, giảm quyền và kiểm tra active sessions.
- Nếu **origin bypass**: thu hẹp SG/ACL và yêu cầu edge→origin identity, xác minh đường dự phòng.
- Nếu **object-level authZ lỗi**: sửa/chặn chức năng hoặc route nhạy cảm, bảo vệ dữ liệu và điều tra phạm vi đọc/ghi.
- Nếu **SSRF**: thu hẹp egress, khóa destination không được phép, kiểm tra quyền IAM và logs của metadata/control plane.
- Nếu **WAF false positive**: tạo exception chính xác rule/route thay vì bỏ mọi policy.
- Nếu **capacity cạn**: kích hoạt backpressure/circuit breaker/điều phối lưu lượng, theo runbook.

### Giai đoạn C — Phục hồi

1. Xác định cấu hình/cause và bản vá đã được review.
2. Test positive/negative cases trong lab hoặc staging.
3. Rollout canary và theo dõi security SLI cùng application SLO.
4. Khôi phục quotas, WAF rules và routing về trạng thái đã phê duyệt.
5. Xác minh origin/private backend, TLS, JWT, route và audit logs.
6. Đóng sự cố khi có bằng chứng traffic hợp lệ phục hồi **và** quyền truy cập trái phép bị chặn.

### Giai đoạn D — Hậu kiểm

Ghi:
- Root cause và các **trust boundaries** bị thiếu kiểm soát.
- Mốc phát hiện, ứng phó và thời gian phục hồi.
- Tác động thực, không chỉ số lượng request bị block.
- Vì sao API inventory/contract/policy drift không phát hiện sớm.
- Việc cần làm: owner, hạn hoàn thành, test hồi quy và cập nhật runbook.

## 26. Tình huống phân tích và đáp án gợi ý

### Tình huống A — User có token hợp lệ xem đơn người khác

Gateway chấp nhận JWT hợp lệ và scope orders:read, nhưng User A gọi GET /v1/orders/42 và nhận dữ liệu thuộc User B.

**Phân tích:** đây là **BOLA/IDOR**. Gateway đã xác thực thành công, nhưng app thiếu object-level authorization. Cần kiểm tra owner/tenant theo object ngay trong backend, thêm test User A → object User B bị từ chối.

### Tình huống B — WAF có hiệu lực nhưng backend vẫn public

Doanh nghiệp bật WAF ở CDN. Một nhóm backend có public IP và security group cho TCP/443 từ mọi nguồn.

**Phân tích:** rủi ro **origin bypass**. Cần private network hoặc hạn chế ingress chỉ tới edge/gateway được cấp phép, kèm mTLS nếu phù hợp. Test request trực tiếp từ nguồn không được phép phải bị chặn.

### Tình huống C — Rate limit chỉ theo IP làm ảnh hưởng khách hàng lớn

Nhiều người dùng hợp lệ trong một công ty đi chung NAT IP; tất cả nhận 429 khi đạt giới hạn 20 request/giây.

**Phân tích:** IP-only limit không công bằng trong CGNAT/NAT. Cân nhắc quota theo user/tenant/client sau auth, kết hợp limit riêng cho request trước auth để chống abuse.

### Tình huống D — Client tự gửi X-Forwarded-For

API Gateway chấp nhận header X-Forwarded-For từ client mà không biết request có đến từ proxy được tin hay không; rule IP allowlist dựa vào header đó.

**Phân tích:** trust boundary bị nhầm. Phải bỏ/ghi lại header tại ingress đầu tiên, giới hạn trusted proxy chain và nhận peer IP thực từ kết nối đã được phép.

### Tình huống E — Mobile app gọi API nhưng CORS không chặn

Một đội cho rằng Access-Control-Allow-Origin chỉ cho tên miền chính sẽ ngăn mobile app hoặc script bên ngoài gọi endpoint.

**Phân tích:** CORS là policy trình duyệt về đọc response, không phải mạng hoặc authentication. Mobile app/server có thể gửi HTTP request trực tiếp. Cần token/permission/quota và validation ở server.

### Tình huống F — Browser cookie API gặp CSRF

API dùng session cookie để xác thực hành động đổi email; một trang khác có thể khiến browser gửi request theo cơ chế credential hiện hành.

**Phân tích:** cần đánh giá **CSRF** theo cookie, SameSite, token/Origin validation và cách app xử lý state change. Không dùng CORS như biện pháp duy nhất.

### Tình huống G — Partner lạm dụng endpoint export

Đối tác có client credential đúng nhưng gửi nhiều yêu cầu export dữ liệu lớn, khiến DB connection pool cạn.

**Phân tích:** authentication hợp lệ không ngăn **resource exhaustion**. Dùng quota theo partner, concurrency limit, async export queue, query budget, timeout và audit, đồng thời bảo đảm tenant-scoped authorization.

### Tình huống H — API có WAF nhưng SSRF tới network nội bộ

Một endpoint fetch-image cho phép user cung cấp URL; backend có quyền kết nối mạng management và metadata service.

**Phân tích:** WAF ingress không đủ. Cần ứng dụng cho phép đúng destination, xử lý redirect/DNS an toàn, egress network policy, IAM tối thiểu và giám sát outbound flows.

### Tình huống I — API admin chỉ “ẩn” dưới /internal

Developer đặt route /internal/admin và tin rằng người ngoài sẽ không đoán được path. Cloud LB vẫn chuyển toàn bộ request vào service.

**Phân tích:** security by obscurity. Dùng network segmentation/VPN/ZTNA, route deny-by-default, role/MFA, app authorization và audit.

### Tình huống J — Chuyển traffic sang vùng dự phòng nhưng giảm bảo mật

Region B phục vụ API thành công, nhưng WAF policy cũ và gateway cho phép một route admin từng bị chặn ở region A.

**Phân tích:** failover không đạt **security parity**. Cần policy-as-code, review drift và kiểm thử cả các luồng bị cấm khi triển khai/khôi phục.

### Tình huống K — TLS tại CDN tốt, origin TLS bị tắt verification

Client nhận HTTPS hợp lệ ở CDN, nhưng kết nối CDN→origin được cấu hình bỏ kiểm tra certificate.

**Phân tích:** TLS A không bảo vệ danh tính ở hop TLS B. Cần xác minh certificate, SNI/hostname, trust chain origin và egress/network path; không đánh dấu “end-to-end secure” từ biểu tượng khóa trình duyệt.

### Tình huống L — Backend tin header role do client gửi

Ứng dụng đọc X-User-Role để quyết định quyền, nhưng load balancer không xóa các header identity do client tự khai báo.

**Phân tích:** nguy cơ giả mạo authorization context. Gateway phải tái tạo identity từ token đã được xác minh, backend chỉ tin traffic từ gateway bảo vệ bằng network identity và tiếp tục kiểm tra quyền nghiệp vụ.

### Tình huống M — WAF chặn request hợp lệ mang nội dung JSON đặc biệt

Một request hợp lệ bị rule phát hiện injection chặn do chuỗi trong field mô tả sản phẩm.

**Phân tích:** cần triage false positive bằng rule ID, schema và request đã được redacted. Tinh chỉnh ngoại lệ đúng field/route/rule với thời hạn, không disable toàn bộ protection.

### Tình huống N — API trả 200 nhưng data leakage tiếp tục

Một endpoint trả cả những trường nhạy cảm không nằm trong hợp đồng client, dù request đã qua WAF, có token hợp lệ và trong quota.

**Phân tích:** lỗi **object/field-level authorization và excessive data exposure**. Phải thu hẹp response DTO, data classification, quyền theo field và kiểm thử dữ liệu; network boundary không tự biết trường nào được phép trả.

## 27. Sai lầm thường gặp

1. **Cho rằng HTTPS là đủ bảo vệ API.** TLS không xác minh quyền trên object.
2. **Tin private IP là trusted user.** Client nội bộ/đã kết nối VPN vẫn có thể bị chiếm.
3. **Dựa hoàn toàn vào WAF.** WAF không giải quyết mọi lỗi nghiệp vụ hoặc object authorization.
4. **JWT signature valid đồng nghĩa user được phép.** Còn issuer/audience/type/scope/tenant và authZ.
5. **Dùng ID token làm access token.** Dễ nhầm mục tiêu token.
6. **Coi OAuth access token luôn là JWT.** Có thể là opaque token cần introspection.
7. **Không kiểm tra từng object/tenant.** Gây BOLA/IDOR.
8. **Để route /admin public và chỉ đổi tên path.** Không tạo network isolation.
9. **Mở origin public ngoài WAF.** Có thể bypass rules và rate limiting.
10. **Tin mọi X-Forwarded-For.** Cho phép client tự khai báo IP giả.
11. **Dùng source IP làm danh tính người dùng.** NAT/CGNAT và VPN làm attribution sai.
12. **Dùng một limit cho mọi route.** Endpoint tạo báo cáo khác endpoint đọc dữ liệu cache.
13. **Tắt limiter khi gặp 429.** Có thể che nguyên nhân client retry storm hoặc quá tải.
14. **Chỉ chặn request/giây mà không giới hạn concurrency.** Công việc dài vẫn cạn tài nguyên.
15. **Không giới hạn size/depth của JSON/body.** Parser/backend có thể bị quá tải.
16. **Không đồng bộ HTTP parsing giữa edge và backend.** Có thể có request desync.
17. **Coi CORS là firewall cho mọi client.** CORS chủ yếu do browser thực thi.
18. **Quên CSRF với cookie-authenticated API.** Cần xem credential tự gửi.
19. **Không kiểm soát outbound khi có fetch URL/webhook.** SSRF có thể vượt vùng tin cậy.
20. **Chỉ kiểm tra ingress IPv4.** IPv6 có thể mở đường khác hoặc thiếu rule.
21. **Service mesh mTLS tự cấp quyền API.** mTLS identity khác function/object authorization.
22. **Để gateway tin token nhưng backend tin header do client sửa.** Phá trust boundary.
23. **Dùng secret header làm lớp chứng minh duy nhất giữa edge và origin.** Header có thể bị lộ/giả nếu đường không khóa.
24. **Không phân biệt 401 với 403.** Gây sai điều tra auth vs authZ.
25. **Bật bot challenge cho mọi B2B API.** Làm hỏng machine clients hợp lệ.
26. **Không giữ logs sau TLS termination.** NIDS ngoài chỉ thấy ciphertext/metadata.
27. **Log nguyên bearer token hoặc dữ liệu thanh toán.** Tăng nguy cơ rò bí mật.
28. **Không kiểm tra rate-limit state phân tán.** Quota có thể bị vượt hoặc sai khi nhiều gateway.
29. **Không có API inventory.** Shadow/staging/retired endpoints khó kiểm soát.
30. **Xem một response 200 là PASS toàn hệ thống.** Phải test cả denied paths và dữ liệu trả về.
31. **Chỉ thử môi trường primary.** Failover có thể mất WAF, auth, logs hoặc ACL.
32. **Không có rollback và owner cho rule.** Thay đổi edge có thể gây mất dịch vụ hàng loạt.

## 28. Checklist bảo vệ REST API tại network boundary

- [ ] Có API inventory với owner, environment, public/private routes, methods và data classification.
- [ ] Đã xác định trust boundaries: Internet→edge, edge→origin, gateway→app, app→downstream.
- [ ] Public exposure chỉ qua endpoint/host đã được phê duyệt; origin không dễ bypass.
- [ ] Có firewall/SG/NetworkPolicy phù hợp ở L3/L4 và cả IPv4/IPv6.
- [ ] Dùng TLS policy hiện đại; xác minh certificate và peer ở từng hop.
- [ ] Áp mTLS hoặc workload identity khi cần, không đánh đồng mTLS với authorization.
- [ ] API Gateway/WAF có route allowlist và default-deny cho unknown/admin routes.
- [ ] Authentication xác minh access token đúng loại, issuer, audience, chữ ký và expiry.
- [ ] Có JWT/JWKS rotation hoặc introspection cho token opaque theo sản phẩm.
- [ ] Object-level, tenant-level, function-level và field-level authorization ở backend.
- [ ] Có scope/role rõ cho partner, employee, admin, workload và không cấp Any→Any.
- [ ] Không tin forwarded headers từ client ngoài trusted proxy chain.
- [ ] Identity headers được strip/rebuild và backend không truy cập được ngoài đường tin cậy.
- [ ] Có Content-Type, method, path, header/body size, JSON depth và timeout limits.
- [ ] Reverse proxy/backend dùng HTTP parsing nhất quán và được cập nhật bản vá.
- [ ] WAF rules theo API contract, có điều kiện rollout, theo dõi false positives.
- [ ] Có rate limiting/quota theo consumer/tenant/route, kết hợp pre-auth IP guard.
- [ ] Có concurrency bounds, query cost budget, queue limits và retry/backpressure.
- [ ] Phân biệt 429/503/504, có Retry-After/observability hợp lý.
- [ ] Với login/OTP/reset, có chống abuse mà không gây lockout hàng loạt.
- [ ] CORS chỉ là browser policy; dùng CSRF protection khi cookie credentials yêu cầu.
- [ ] Ứng dụng có URL fetch/webhook được bảo vệ SSRF với egress policy.
- [ ] Egress tới metadata/control-plane, mạng management và service nhạy cảm bị hạn chế.
- [ ] Cloud/Kubernetes ingress, SG, Gateway API, NetworkPolicy và mesh được kiểm chứng.
- [ ] Failover region/site vẫn giữ security parity, identity, WAF, quota và logs.
- [ ] Access logs không chứa token, API key, cookie, PII/payment bodies ngoài nhu cầu có kiểm soát.
- [ ] Request correlation ID nối được edge, gateway, app, identity và DB audit.
- [ ] Có metrics p95/p99, request success, auth deny, WAF actions, 429, saturation và telemetry loss.
- [ ] Chạy positive và negative tests trên route, role, object ownership, HTTP method và origin.
- [ ] Có owner/change approval, canary, rollback và runbook ứng phó sự cố API.
- [ ] Review định kỳ shadow endpoints, v0/v1, key/cert expiry và drift giữa môi trường.
- [ ] Không coi một security control hoặc một test đơn lẻ là đủ chứng minh REST API an toàn.

## 29. Tổng kết

**Bảo vệ REST API tại network boundary** là thiết kế những ranh giới **ai được kết nối, kết nối bằng danh tính nào, gửi request nào, sử dụng bao nhiêu tài nguyên và đi tới vùng nào**, với bằng chứng kiểm chứng được ở từng hop. **CDN/DDoS protection, WAF, API gateway, TLS/mTLS, firewall, IAM và network segmentation** phối hợp để giảm rủi ro, nhưng **authorization theo chức năng, tenant, object và dữ liệu** vẫn phải được ứng dụng thực thi.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, kiến trúc đáng tin phải ngăn **origin bypass**, không tin **proxy headers** ngoài nguồn được xác thực, có **rate limit và backpressure** cho tài nguyên thực, kiểm soát **ingress lẫn egress**, bảo vệ **cloud/Kubernetes/VPN**, theo dõi **IDS/IPS/telemetry** và kiểm thử cả những request **được phép lẫn bị cấm**. Mục tiêu không phải “chặn thật nhiều”, mà là **giữ API khả dụng cho người dùng hợp lệ, hạn chế lạm dụng và bảo toàn đúng ranh giới quyền truy cập qua mọi đường mạng và trạng thái vận hành**.
