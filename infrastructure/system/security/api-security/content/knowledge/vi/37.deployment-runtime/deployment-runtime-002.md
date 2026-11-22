# API gateway, service mesh và network policy

Một API production thường không chỉ có một ứng dụng nhận request trực tiếp từ Internet. Traffic có thể đi qua CDN, load balancer, API gateway, ingress controller, service mesh sidecar hoặc proxy node, rồi mới đến service xử lý nghiệp vụ. Các service cũng gọi lẫn nhau qua mạng nội bộ, message broker hoặc egress gateway. Mỗi lớp có thể xác thực caller, mã hóa kết nối, giới hạn traffic hoặc áp dụng policy; nhưng nếu các lớp không có trust boundary rõ ràng, attacker có thể đi đường vòng để bỏ qua kiểm soát.

**API gateway** quản lý traffic đi vào hệ thống và thường là điểm thực thi policy cho north-south traffic. **Service mesh** quản lý giao tiếp service-to-service, thường tập trung vào east-west traffic, workload identity, mTLS, routing và telemetry. **Network policy** giới hạn workload nào có thể kết nối đến workload/port nào ở tầng mạng. Ba cơ chế bổ sung nhau, nhưng không cơ chế nào tự thay thế authentication, authorization trên function/object hoặc validation trong ứng dụng.

Trong phạm vi `SECURITY_API_SECURITY`, cần thiết kế bảo mật theo endpoint, object và luồng nghiệp vụ qua toàn bộ đường đi của request. Gateway có thể xác thực token và chặn request không hợp lệ; mesh có thể xác minh workload identity; network policy có thể giới hạn kết nối. Service đích vẫn phải kiểm tra caller, tenant, permission và business invariant trước khi đọc hoặc thay đổi dữ liệu.

## 1. Vai trò và ranh giới của từng lớp

| Lớp | Phạm vi chính | Kiểm soát thường đặt tại đây | Không nên coi là |
|---|---|---|---|
| CDN/WAF/edge | Traffic Internet trước gateway | DDoS mitigation, TLS edge, coarse filtering, bot/rule signals | Nơi duy nhất xác thực user hoặc kiểm tra object permission |
| API gateway/ingress | North-south API traffic | Route, TLS, token validation, coarse authorization, rate limit, body/header limits, request logging | Thay thế authorization trong service |
| Service mesh | East-west service traffic | Workload identity, mTLS, service-to-service authorization, retries/timeouts, telemetry | Bằng chứng user cuối cùng có quyền trên object |
| Network policy/firewall | Kết nối giữa network endpoint/workload | Allow-list source/destination/port/protocol, segmentation, egress restriction | Kiểm tra JSON field, business rule hoặc user permission |
| Application/service | Endpoint và business operation | Authentication context validation, function/object/field authorization, validation, transaction, audit | Có thể tin mọi header do proxy hoặc client gửi |

### 1.1. North-south và east-west traffic

- **North-south** là traffic từ client/Internet vào hệ thống hoặc từ hệ thống ra bên ngoài. API gateway thường quản lý route public, authentication entry point, rate limit và contract ở biên.
- **East-west** là traffic giữa các service trong hệ thống. Service mesh và network policy thường quản lý workload identity, mã hóa và segmentation.

Một request có thể đi qua nhiều lớp:

~~~mermaid
flowchart LR
    C[Browser / Partner] --> E[Edge / WAF]
    E --> G[API Gateway]
    G --> M[Service Mesh Proxy]
    M --> A[Orders API]
    A --> P[Payments Service]
    A --> D[(Orders Database)]
    P --> X[External Provider]
    N[Network Policy] -. constrains .-> G
    N -. constrains .-> A
    N -. constrains .-> P
~~~

Sơ đồ thể hiện các lớp kiểm soát khái niệm. Deployment thực tế có thể đặt gateway trong mesh, dùng ingress gateway của mesh hoặc có nhiều proxy. Cần vẽ đúng traffic path đang chạy để biết policy được thực thi ở đâu và có đường bypass nào.

### 1.2. Defense in depth nhưng policy phải nhất quán

Nhiều lớp kiểm soát không có nghĩa mỗi lớp tự định nghĩa một quyền khác nhau. Nếu gateway cho phép `POST /payments`, mesh cho phép workload gọi payment service, nhưng service không kiểm tra tenant/object, request vẫn có thể gây cross-tenant access. Ngược lại, nếu gateway chặn hết request hợp lệ do cấu hình sai, availability bị ảnh hưởng dù application policy đúng.

Hãy định nghĩa một policy model thống nhất, sau đó phân công từng lớp thực thi phần phù hợp:

- Gateway xác định client/API entry point và áp dụng policy coarse-grained.
- Mesh xác định workload caller và bảo vệ service-to-service channel.
- Network policy giới hạn khả năng mở kết nối.
- Service xác minh principal/delegation và quyết định quyền trên function/object/field.

## 2. Thiết kế API gateway an toàn

API gateway là điểm tập trung hữu ích cho traffic public và partner. Nó có thể áp dụng các kiểm soát chung, nhưng cấu hình gateway cũng là một phần của attack surface.

### 2.1. Route allow-list và method policy

Chỉ publish route cần thiết. Mỗi route nên có:

- Hostname và path template rõ ràng.
- HTTP method được hỗ trợ.
- Backend service/cluster đích.
- Authentication scheme và token audience phù hợp.
- Rate limit/quota class.
- Request/response size limit và timeout.
- Owner, API version và lifecycle state.
- Logging/audit requirements.

Tránh route wildcard quá rộng như chuyển mọi path chưa biết đến một backend chung. Route không được khai báo nên bị từ chối, không tự động fallback đến service khác. Method không hỗ trợ nên trả response phù hợp và không được rewrite thành method nhạy cảm.

### 2.2. Authentication tại gateway

Gateway có thể kiểm tra JWT hoặc opaque token trước khi chuyển request:

- Chỉ tin issuer được cấu hình.
- Kiểm tra chữ ký bằng key/algorithm trong allowlist.
- Kiểm tra `aud` dành cho API/resource server.
- Kiểm tra `exp`, `nbf` và clock skew theo policy.
- Kiểm tra token type và claim cần thiết.
- Xử lý key rotation và key revocation.
- Không log token hoặc Authorization header.

Nếu gateway xác thực token rồi chuyển request đến backend, backend cần biết gateway identity và trust model. Có hai mô hình phổ biến:

1. Backend xác minh lại access token/delegation token.
2. Gateway truyền identity context qua một kênh được xác thực mạnh, và backend chỉ tin context đó khi request đến từ gateway identity được xác minh.

Không được tin header `X-Authenticated-User`, `X-User-Role`, `X-Tenant-Id` hoặc `X-Authz-Decision` nếu caller có thể gửi trực tiếp. Gateway phải xóa header cùng tên do client cung cấp trước khi tạo giá trị nội bộ. Backend phải chặn direct access hoặc xác minh gateway/workload identity để header không thể bị giả mạo qua đường khác.

### 2.3. Coarse-grained authorization ở gateway

Gateway có thể kiểm tra scope hoặc role ở mức route, ví dụ `reports:read` để gọi nhóm endpoint báo cáo. Đây là lớp giảm traffic không hợp lệ và thực thi policy tổng quát. Nhưng scope route không chứng minh caller có quyền trên report cụ thể, customer cụ thể hoặc field cụ thể.

Ví dụ, gateway có thể cho phép user có `orders:read` gọi `GET /v1/orders/{id}`. Orders service vẫn phải tải order trong tenant của principal và kiểm tra object authorization. Không đặt logic ownership phức tạp chỉ ở gateway nếu backend có thể bị gọi từ một route khác.

### 2.4. Request limits và protocol normalization

Gateway nên giới hạn:

- Header count và header size.
- Request body size theo route.
- Upload/download size.
- URL/path/query length.
- Request timeout và idle timeout.
- Concurrent requests và connection count.
- Batch size và pagination parameters khi có thể xác định.

Gateway và backend cần thống nhất cách parse path, header và HTTP framing. Kiểm thử duplicate header, encoded path separator, trailing slash, method override và content-length/transfer-encoding handling theo stack thực tế. Nếu gateway kiểm tra một representation nhưng backend diễn giải khác, có thể xuất hiện request smuggling hoặc route bypass.

### 2.5. Rate limiting ở gateway

Gateway là vị trí tốt để chặn burst trước khi request tiêu thụ tài nguyên ứng dụng. Có thể giới hạn theo client ID, API key ID, principal, tenant, route hoặc IP tùy độ tin cậy của identity.

- Ưu tiên identity đã xác thực cho quota theo client/user/tenant.
- Dùng IP như tín hiệu phụ, vì NAT/CGNAT có thể gom nhiều user.
- Tách rate limit cho endpoint đắt khỏi endpoint đọc nhẹ.
- Kết hợp rate limit, concurrency, payload/query complexity và quota dài hạn.
- Trả `429` và `Retry-After` theo contract khi phù hợp.
- Không để client tạo key mới hoặc thay header để né tenant-level budget.

Rate limit ở gateway không thay hard limit trong service/worker. Async job, internal call hoặc đường gọi khác có thể không đi qua cùng gateway.

## 3. TLS termination và bảo vệ kết nối qua nhiều hop

TLS ở edge chỉ bảo vệ kết nối giữa client và điểm TLS termination. Nếu gateway chuyển tiếp request qua mạng nội bộ bằng HTTP, dữ liệu có thể bị đọc/sửa trên đường đi và workload identity không được xác minh bằng TLS.

Các câu hỏi cần trả lời:

- TLS kết thúc tại CDN, load balancer, gateway hay application?
- Từ edge đến gateway/backend có mã hóa không?
- East-west traffic có mTLS không?
- Certificate được cấp, rotate và revoke thế nào?
- Service có xác minh hostname/SAN và trust chain không?
- Có đường plaintext hoặc port phụ không?

### 3.1. TLS ở edge

Dùng TLS hiện đại, certificate hợp lệ và cấu hình cipher/protocol theo baseline của tổ chức. Redirect HTTP sang HTTPS có thể hữu ích cho browser, nhưng endpoint API nhạy cảm nên ưu tiên chỉ expose HTTPS; không xử lý credential qua plaintext rồi mới redirect.

### 3.2. TLS giữa gateway và backend

Nếu gateway và backend ở các host/container khác nhau, dùng TLS hoặc mTLS theo threat model. Nếu backend chỉ nhận traffic từ gateway, giới hạn network path và xác minh identity gateway. Không giả định private subnet đủ an toàn để truyền token hoặc dữ liệu nhạy cảm ở plaintext.

### 3.3. mTLS trong service mesh

mTLS xác thực workload ở tầng kết nối và mã hóa traffic east-west. Service mesh có thể cấp certificate ngắn hạn cho workload identity và tự động rotate. Cần kiểm tra:

- Identity được gắn với service account/workload nào.
- Trust domain và namespace mapping.
- Certificate issuance, rotation và revocation.
- Có workload nào chạy ở chế độ plaintext/permissive ngoài dự kiến không.
- Traffic đi qua proxy có bị bypass do host networking, port exclude hoặc cấu hình đặc biệt không.

mTLS chứng minh workload sở hữu identity ở phía kết nối; nó không chứng minh user cuối cùng được phép xem object. Nếu service A gọi service B thay mặt user, cần delegation context hoặc user token phù hợp và B phải kiểm tra authorization theo hợp đồng.

## 4. Service mesh: workload identity và service authorization

Service mesh thường cung cấp proxy data plane và control plane quản lý certificate, routing, telemetry và policy. Tên sản phẩm/cách triển khai khác nhau, nhưng trust model cần rõ ràng.

### 4.1. Workload identity

Mỗi workload nên có identity riêng, thường gắn với service account, namespace, trust domain hoặc SPIFFE ID. Không dùng một shared identity cho mọi service nếu chúng có quyền khác nhau.

Ví dụ về identity khái niệm:

~~~text
spiffe://prod.example/ns/orders/sa/orders-api
spiffe://prod.example/ns/payments/sa/payments-api
spiffe://prod.example/ns/reporting/sa/report-worker
~~~

Identity phải phản ánh workload thực, được cấp từ control plane tin cậy và có vòng đời quản lý. Không lấy service name từ header do caller tự gửi để quyết định workload identity.

### 4.2. Authorization theo source workload, destination và operation

Mesh policy có thể giới hạn:

- Workload nào được gọi service nào.
- Namespace/service account nào được gọi port nào.
- HTTP method/path nào được gọi khi mesh hỗ trợ L7 authorization.
- JWT claims nào được yêu cầu nếu mesh đã xác minh token.

Ví dụ policy: chỉ `orders-api` được gọi `payments-service` trên route tạo payment; `report-worker` chỉ được gọi endpoint đọc dữ liệu báo cáo. Dù mesh cho phép kết nối, payments service vẫn phải kiểm tra user/tenant permission, payment state và amount/business rules.

### 4.3. Không đồng nhất namespace với authorization

Namespace có thể là một boundary tổ chức/deployment, nhưng không tự chứng minh mọi workload trong namespace có cùng mức tin cậy. Một namespace có thể chứa nhiều service account và workload khác nhau. Dùng workload identity cụ thể và policy least privilege; tránh rule rộng kiểu “mọi pod trong namespace được gọi mọi service”.

### 4.4. Fail-closed và failure behavior

Nếu mesh proxy hoặc policy control plane lỗi, cần xác định data plane behavior. Không để policy enforcement chuyển sang allow-all khi control plane mất kết nối. Certificate đã cấp có thể tiếp tục hợp lệ trong một khoảng thời gian theo thiết kế; policy mới có thể chưa được cập nhật. Cần hiểu:

- Proxy xử lý thế nào khi không lấy được policy mới?
- Workload có tiếp tục dùng certificate hết hạn không?
- Có chế độ permissive/strict TLS không?
- Policy update có atomic không?
- Proxy restart hoặc injection failure có mở đường bypass không?

Với service nhạy cảm, chọn failure mode không mở quyền khi không xác minh được caller. Kiểm thử cả outage control plane, certificate rotation và pod restart.

## 5. Network policy và segmentation

Network policy giới hạn workload nào có thể mở kết nối đến workload nào trên protocol/port nhất định. Đây là lớp giảm khả năng di chuyển ngang sau khi một service bị xâm nhập.

Network policy thường hoạt động ở L3/L4 (IP, protocol, port). Nó không biết user nào đang đăng nhập, request JSON chứa object ID gì hoặc action có hợp lệ theo workflow không. Vì vậy, network allow không có nghĩa application allow.

### 5.1. Default deny và allow-list

Một chiến lược phổ biến:

1. Bắt đầu bằng policy mặc định chặn ingress/egress cho namespace hoặc nhóm workload.
2. Cho phép ingress từ gateway/mesh identity hoặc workload cần thiết.
3. Cho phép egress đến DNS, database, broker và downstream cụ thể.
4. Giữ management plane riêng.
5. Kiểm tra policy enforcement của CNI/network platform.

Default deny làm lộ các dependency chưa được khai báo. Cần inventory trước và rollout có kiểm soát để tránh vô tình làm gián đoạn service.

### 5.2. Ví dụ Kubernetes NetworkPolicy

Policy sau minh họa chặn ingress mặc định cho pod trong namespace `orders`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-default-deny-ingress
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Sau đó cho phép ingress từ gateway workload trong namespace `edge` đến pod có label `app: orders-api`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-edge-to-orders
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

Trong một peer item, `namespaceSelector` và `podSelector` cùng được áp dụng (AND): pod có label `app: gateway` trong namespace `edge`. Nếu đặt thành hai item riêng trong danh sách `from`, chúng là hai lựa chọn (OR), có thể mở rộng quyền ngoài ý muốn.

Đây là ví dụ minh họa. Cần kiểm tra label thực tế, namespace labels, port container, CNI và các policy khác. Kubernetes NetworkPolicy có semantics allow-list theo tập policy áp dụng; nhiều policy có thể cộng gộp rule được phép. Không phải mọi CNI đều hỗ trợ mọi tính năng mở rộng giống nhau.

### 5.3. Egress policy

Chặn egress mặc định giúp giảm khả năng service bị xâm nhập gọi metadata endpoint, database tùy ý hoặc Internet. Sau đó mở đúng dependency cần thiết:

- DNS resolver đã được cấu hình.
- Database/broker endpoint và port cụ thể.
- Service nội bộ cần gọi.
- Egress gateway hoặc proxy cho external API.

Egress policy cần tính đến DNS, IPv4/IPv6, service discovery, node-local DNS và CNI behavior. Nếu cho phép mọi egress chỉ vì service cần gọi một provider, segmentation gần như mất tác dụng. Dùng egress proxy hoặc gateway để áp dụng hostname policy và SSRF controls ở lớp cao hơn.

### 5.4. NetworkPolicy không phải firewall đầy đủ

Kubernetes NetworkPolicy chuẩn thường chỉ hỗ trợ chọn pod/namespace/IP block và port/protocol với semantics allow; không có rule deny ưu tiên theo cách nhiều firewall thương mại cung cấp. Policy được thực thi bởi CNI; nếu CNI không hỗ trợ hoặc policy không được enforce, manifest tồn tại không chứng minh traffic đã bị chặn.

NetworkPolicy cũng không thay host firewall, cloud security group, gateway ACL hoặc application authorization. Cần test từ network zone thực tế và kiểm tra flow logs/telemetry của CNI.

## 6. Thiết kế đường đi chuẩn và ngăn gateway bypass

Một backend chỉ nên nhận traffic từ các nguồn đã định nghĩa. Nếu service có thể được gọi trực tiếp từ Internet hoặc workload không tin cậy, attacker có thể bỏ qua rate limit, authentication hoặc request validation ở gateway.

Kiểm tra:

- Backend service không có public LoadBalancer/NodePort ngoài chủ đích.
- Firewall/security group chỉ mở source gateway/mesh ingress cần thiết.
- Internal DNS không được resolve công khai ngoài chủ đích.
- Direct pod/service IP không thể được gọi từ network zone không được phép.
- Backend vẫn xác minh token/workload identity và authorization.
- Gateway strip các header identity do client gửi và tạo context mới.
- Không có route phụ, debug port hoặc management port mở rộng đường truy cập.

### 6.1. Gateway identity đến backend

Nếu backend tin header do gateway tạo, bảo đảm:

1. Kết nối đến backend chỉ đến từ gateway identity được xác minh.
2. Gateway xóa mọi header cùng tên do client gửi.
3. Gateway tạo header mới từ token đã xác minh, không copy claim chưa kiểm tra.
4. Header không thể bị ghi đè bởi proxy hop tiếp theo.
5. Backend chỉ chấp nhận header trên trust channel đã xác định.
6. Có test direct backend request với header giả để xác minh bị chặn.

Với hệ thống nhiều hop, ghi rõ proxy nào được tin và cách xử lý `Forwarded`/`X-Forwarded-*`. Không dùng X-Forwarded-For từ Internet client để quyết định source IP nếu edge proxy chưa overwrite/normalize header.

### 6.2. Không tin Host và forwarded headers tùy ý

Host header, forwarded host/proto và path rewrite có thể ảnh hưởng redirect URL, tenant routing, callback URL hoặc absolute link. Chỉ tin giá trị từ proxy được cấu hình; validate allowed host và scheme. Không tạo link reset password hoặc callback destination từ Host header tùy ý.

## 7. SSRF và egress control

Một service có thể bị SSRF khi nhận URL từ user rồi tự kết nối đến đó. Network policy và egress gateway có thể giảm blast radius, nhưng application vẫn cần URL validation và DNS/IP validation.

Các kiểm soát phối hợp:

- Chỉ cho phép scheme cần thiết, thường là HTTPS.
- Parse URL bằng thư viện chuẩn và canonicalize hostname.
- Chặn loopback, private, link-local, metadata, multicast và reserved IP.
- Resolve cả A/AAAA record và xử lý DNS rebinding/TOCTOU.
- Tắt redirect tự động hoặc validate từng hop.
- Pin destination đã xác minh hoặc dùng SSRF-safe egress proxy.
- Chặn metadata IP và subnet quản trị ở network layer.
- Không forward Authorization/cookie nội bộ đến destination khác.
- Giới hạn connect/read/total timeout, response size và redirect count.

Egress allowlist theo IP có thể không phù hợp với provider dùng CDN hoặc IP thay đổi. Có thể dùng egress proxy hiểu hostname/TLS SNI và policy domain, kết hợp certificate validation. Không chỉ allow toàn bộ Internet từ một service có chức năng fetch URL.

## 8. Retry, timeout và circuit breaker qua gateway/mesh

Gateway và mesh có thể tự retry request khi timeout hoặc gặp lỗi tạm thời. Nếu retry không hiểu semantics nghiệp vụ, một thao tác POST có thể tạo nhiều payment/order dù client chỉ gửi một lần.

### 8.1. Chỉ retry operation an toàn

- Retry tự động phù hợp hơn với request idempotent hoặc operation có idempotency key.
- Không retry POST có side effect nếu chưa có deduplication/idempotency semantics.
- Giới hạn retry count và tổng deadline.
- Dùng backoff/jitter để tránh retry storm.
- Không retry lỗi 401, 403, validation hoặc business conflict như thể chúng là lỗi mạng.
- Xác định retry ở client, gateway hay mesh; nhiều lớp cùng retry có thể nhân số lần gọi.

Ví dụ: client retry 3 lần, gateway retry 2 lần và mesh retry 2 lần có thể tạo tối đa nhiều lần attempt cho một operation. Cần tính retry budget end-to-end và log attempt/correlation ID.

### 8.2. Timeout budget

Tổng timeout của downstream phải nhỏ hơn hoặc bằng deadline còn lại của request gốc. Đặt timeout độc lập ở mọi hop mà không phối hợp có thể khiến worker tiếp tục chạy sau khi client đã timeout. Với async job, trả operation ID và quản lý lifecycle thay vì giữ kết nối đồng bộ quá lâu.

### 8.3. Circuit breaker không phải authorization fallback

Khi dependency lỗi, circuit breaker có thể ngừng gửi request để bảo vệ hệ thống. Không để circuit breaker làm authorization fail-open. Nếu policy engine hoặc identity verifier không khả dụng, action nhạy cảm cần bị từ chối hoặc đưa vào safe degraded mode đã được phê duyệt.

## 9. Policy consistency và configuration as code

Gateway route, mesh authorization và network policy thường nằm ở các repository hoặc pipeline khác nhau. Drift giữa các cấu hình có thể tạo lỗ hổng.

Nên quản lý:

- Owner và version cho từng policy.
- Review bắt buộc cho route public, wildcard, allow-all và policy exception.
- GitOps/IaC hoặc quy trình deploy có audit.
- Policy validation/lint trước khi apply.
- Diff và approval cho thay đổi security-sensitive.
- Rollback version rõ ràng.
- Drift detection giữa desired state và runtime state.
- Expiry cho temporary exception.

Tránh các cấu hình:

- Gateway route wildcard chuyển mọi path đến admin backend.
- Mesh authorization cho phép mọi principal trong namespace.
- TLS permissive kéo dài sau migration.
- Network policy mở toàn bộ ingress/egress để xử lý một sự cố tạm thời.
- Header identity được tin trên mọi listener.
- Exception không có owner hoặc ngày hết hạn.

### 9.1. Policy precedence

Mỗi nền tảng có semantics khác nhau khi nhiều policy cùng áp dụng: allow-list union, explicit deny precedence, default deny hoặc policy hierarchy. Không giả định tất cả gateway, mesh và CNI xử lý rule giống nhau. Tài liệu hóa precedence và test tổ hợp policy, đặc biệt khi thêm một rule allow mới.

### 9.2. Canary và rollout

Khi chuyển từ permissive sang strict mTLS hoặc default-deny network policy:

1. Inventory dependency và traffic thực tế.
2. Chạy audit/dry-run mode nếu nền tảng hỗ trợ.
3. Tạo policy allow-list tối thiểu.
4. Test positive và negative path.
5. Rollout theo namespace/service canary.
6. Theo dõi denied flow, latency và error rate.
7. Enforce strict mode.
8. Xóa temporary exception sau thời hạn.

Không để audit-only mode kéo dài vô hạn và không coi log “would deny” là bằng chứng enforcement đã hoạt động.

## 10. Quan sát và audit trên các lớp

Telemetry cần cho biết request đi qua lớp nào, identity nào được xác minh và policy nào đã quyết định.

### 10.1. Gateway telemetry

Ghi nhận route template, method, client ID/key ID đã xác minh, status, latency, upstream cluster, rate-limit decision và request ID. Không log token, cookie, API key secret hoặc raw body chứa PII.

### 10.2. Mesh telemetry

Ghi nhận source/destination workload identity, namespace/service account, mTLS status, authorization decision, response code, retry count và latency. Không dùng workload name hoặc trace header do caller tự khai làm identity.

### 10.3. Network telemetry

Flow log có thể cho biết source/destination IP, port, protocol và allow/deny. Dùng để phát hiện workload gọi dependency chưa khai báo, egress bất thường hoặc traffic đến metadata/private subnet. IP cần map về workload tại thời điểm quan sát vì pod IP có thể thay đổi.

### 10.4. Application audit

Service vẫn ghi actor/subject, tenant, action, object reference, decision và operation ID theo audit policy. Gateway/mesh log không thay audit nghiệp vụ: một kết nối mTLS thành công không chứng minh user được phép refund payment.

## 11. Kiểm thử gateway, mesh và network policy

Kiểm thử cần xác minh cả traffic được phép và traffic bị chặn, đồng thời kiểm tra đường bypass.

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Gateway route | Path/method không được khai báo | Bị từ chối, không fallback backend |
| Gateway authentication | Token sai issuer/audience/signature | Bị từ chối trước business handler |
| Gateway headers | Client tự gửi X-User-Role/X-Tenant-Id | Header bị strip; không tạo identity giả |
| Gateway bypass | Gọi trực tiếp backend từ zone không được phép | Network chặn hoặc backend xác minh caller |
| Object authorization | Token hợp lệ nhưng object khác tenant | Service từ chối |
| mTLS | Workload không có certificate tin cậy | Kết nối bị từ chối |
| Mesh authorization | Workload hợp lệ gọi service/port ngoài policy | Bị deny |
| Mesh policy outage | Control plane mất kết nối | Data plane không chuyển sang allow-all |
| Network ingress | Pod không được allow kết nối đến backend | Flow bị chặn |
| Network egress | Service thử gọi metadata/private subnet | Egress bị chặn |
| DNS/IPv6 | Egress qua AAAA hoặc DNS rebinding | Không bypass được destination policy |
| Retry | POST không idempotent gặp timeout | Không tạo side effect lặp |
| Timeout | Downstream vượt deadline | Request/job dừng theo budget |
| Management port | Anonymous truy cập metrics/config/dump | Bị chặn hoặc chỉ trả thông tin tối giản theo policy |
| Policy drift | Runtime config khác desired state | Alert/finding được tạo |
| CORS/OPTIONS | Preflight và OPTIONS nghiệp vụ | CORS xử lý đúng; route nghiệp vụ vẫn được bảo vệ |

### 11.1. Kiểm tra từ nhiều network zone

Thử từ Internet test zone, gateway zone, application namespace, workload cùng namespace, workload namespace khác và management network. Kết quả phải khớp intended flow. Không chỉ test từ bên trong cluster vì đó có thể là góc nhìn quá tin cậy.

### 11.2. Kiểm tra workload identity

Test service account đúng, service account khác trong cùng namespace, workload từ namespace khác và workload không có sidecar/mesh enrollment. Xác minh certificate principal thực tế, không chỉ label pod. Kiểm tra cả khi pod restart hoặc certificate rotate.

### 11.3. Kiểm tra policy ở runtime

Manifest đúng chưa chứng minh policy đã được thực thi. Kiểm tra CNI/mesh status, proxy config, flow logs, denied counters và kết nối thật. Với NetworkPolicy, xác minh CNI hỗ trợ enforcement; với mesh, xác minh proxy injection/ambient enrollment và không có port bypass.

## 12. Ví dụ thiết kế theo một luồng nghiệp vụ

Giả sử browser gọi `POST /v1/orders/{id}/refund`:

1. Edge chỉ nhận HTTPS và áp dụng DDoS/WAF policy.
2. API gateway match đúng route/method, xác minh JWT issuer/audience/signature/expiry, áp coarse scope `orders:refund` và rate limit.
3. Gateway strip header identity do client gửi, chuyển request đến orders service qua mTLS.
4. Mesh xác minh workload gateway và cho phép gọi orders service trên route cần thiết.
5. Network policy chỉ cho gateway/approved workload kết nối đến orders service; chỉ orders service được gọi payments service.
6. Orders service xác minh principal/delegation, tenant và quyền trên order cụ thể.
7. Service kiểm tra order state, amount, idempotency key và business invariant.
8. Orders service gọi payments service bằng workload identity; payments service xác minh caller và quyền/operation context.
9. Database transaction, outbox và audit ghi trạng thái; retry được kiểm soát.
10. Response đi ngược qua mesh/gateway, error mapping không lộ dữ liệu nhạy cảm.

Nếu gateway cho phép route nhưng service không kiểm tra object ownership, tenant A có thể refund order B. Nếu mesh cho phép mọi workload trong namespace gọi payments, một workload bị xâm nhập có thể tạo payment action ngoài ý muốn. Nếu network policy mở egress toàn bộ, service có SSRF bug có thể kết nối đến metadata/private destination. Mỗi lớp xử lý một rủi ro khác nhau.

## 13. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gateway là lớp duy nhất kiểm tra quyền | Direct backend hoặc route khác bỏ qua policy | Service tự enforce function/object authorization |
| Tin mọi header từ gateway | Header giả mạo có thể tạo principal/tenant giả | Strip/recreate header và xác minh gateway identity |
| Private network được coi là trusted | Workload bị xâm nhập có thể gọi service nhạy cảm | Workload identity, mTLS và least privilege |
| Một service account dùng chung | Không phân biệt quyền giữa workload | Identity riêng theo workload |
| mTLS permissive vô thời hạn | Workload không có identity vẫn kết nối | Strict mode, migration deadline và drift alert |
| NetworkPolicy chỉ có default deny ingress | Egress vẫn có thể đến Internet/metadata | Đánh giá và áp egress policy |
| CNI không enforce NetworkPolicy | Manifest tồn tại nhưng traffic không bị chặn | Xác minh CNI và test runtime |
| Rule namespace quá rộng | Workload không liên quan được gọi service | Chọn service account/workload selector cụ thể |
| Gateway/mesh retry POST mù quáng | Duplicate payment/order | Idempotency key và retry budget |
| Egress allow toàn Internet | SSRF có thể truy cập destination tùy ý | Egress proxy, IP policy và application validation |
| Không test direct backend path | Gateway bypass bị bỏ sót | Test từ nhiều network zone |
| Policy drift không được phát hiện | Runtime khác desired security state | IaC/GitOps, audit và drift detection |

## 14. Checklist review gateway, service mesh và network policy

- [ ] Đã vẽ traffic path north-south và east-west thực tế.
- [ ] Mỗi route gateway có owner, method, backend, auth policy, limits và lifecycle.
- [ ] Unknown route/method bị từ chối; không fallback đến backend chung.
- [ ] JWT/opaque token được xác minh đúng issuer, audience, signature, expiry và key lifecycle.
- [ ] Header identity do client gửi bị strip; backend chỉ tin context qua trust channel xác minh.
- [ ] Gateway coarse authorization không thay object/tenant/field authorization trong service.
- [ ] TLS được bảo vệ qua các hop cần thiết; plaintext listener được kiểm kê.
- [ ] Workload identity riêng và mTLS được áp dụng theo trust boundary.
- [ ] Mesh authorization giới hạn source workload, destination, method/path/port phù hợp.
- [ ] Mesh failure không chuyển sang allow-all; strict/permissive mode có lifecycle.
- [ ] Network policy có ingress và egress allow-list phù hợp; CNI enforcement được xác minh.
- [ ] Database, broker và management plane chỉ nhận traffic từ workload cần thiết.
- [ ] Egress policy và SSRF controls chặn metadata, private và destination không được phép.
- [ ] Retry, timeout, circuit breaker và idempotency có budget end-to-end.
- [ ] Gateway, mesh, network và application logs có correlation nhưng không ghi secret.
- [ ] Có test direct backend/gateway bypass từ các network zone.
- [ ] Có test workload identity, mTLS, object authorization, egress và policy outage.
- [ ] Policy được quản lý bằng code, review, canary, audit và drift detection.
- [ ] Temporary exception có owner, lý do và expiry.

API gateway, service mesh và network policy tạo thành các lớp bảo vệ khác nhau trên đường đi của request. Gateway quản lý entry point và policy chung; mesh xác minh workload và bảo vệ giao tiếp service-to-service; network policy giới hạn khả năng kết nối ở tầng mạng. Chúng chỉ phát huy hiệu quả khi service đích vẫn tự xác minh principal, tenant, permission và business state. Khi traffic path, identity, policy precedence và failure behavior được xác định rõ, hệ thống có thể giảm gateway bypass, lateral movement và SSRF blast radius mà vẫn giữ authorization đúng tại endpoint và object.
