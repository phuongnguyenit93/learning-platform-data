# Gateway và backend — Ranh giới xác thực và ủy quyền trong hệ thống phân tán
 
> **Chương:** Authentication trong distributed system  
> **Chủ đề:** Gateway và backend

Trong hệ thống phân tán, request thường đi qua nhiều thành phần trước khi chạm tới dữ liệu: browser/mobile app, CDN hoặc load balancer, API gateway, backend service, message broker và database. Mỗi thành phần có thể nằm ở một ranh giới tin cậy khác nhau. Vì vậy, xác thực tại gateway là một lớp kiểm soát quan trọng nhưng không tự động chứng minh mọi backend đều có thể tin request, user identity hoặc quyền truy cập mà gateway truyền xuống.

**Gateway** thường là điểm vào tập trung để kết thúc TLS bên ngoài, xác minh access token, giới hạn lưu lượng, định tuyến và áp dụng policy chung. **Backend** thực hiện nghiệp vụ, kiểm tra quyền trên resource và truy cập dữ liệu. Thiết kế an toàn phải xác định rõ gateway chịu trách nhiệm gì, backend phải tự kiểm tra điều gì, danh tính được truyền bằng cơ chế nào và service-to-service call được xác thực ra sao.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối authentication, credential, token, session, authorization boundary, tenant context, SSO và workload identity. Người học sẽ mô hình hóa trust boundary giữa gateway và backend, xác minh token đúng audience, truyền principal/delegation an toàn, bảo vệ internal API và xử lý các rủi ro như header spoofing, confused deputy, token replay, stale authorization và request forgery.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích vai trò và giới hạn của API gateway trong authentication của hệ thống phân tán.
2. Phân biệt xác thực người dùng, xác thực workload/service và authorization trên từng resource.
3. Thiết kế luồng token validation tại gateway và backend theo issuer, audience, signature, expiry và scope.
4. Chọn cách truyền identity context bằng token delegation, token exchange hoặc metadata nội bộ có xác thực.
5. Phân biệt user token, ID token, access token, service token và workload identity.
6. Thiết lập mTLS hoặc cơ chế workload identity để xác thực gateway với backend.
7. Ngăn client giả mạo identity header, tenant header hoặc forwarded header.
8. Áp dụng defense in depth mà không biến gateway thành điểm tin cậy duy nhất.
9. Xử lý authorization, revocation, cache, retry, asynchronous job và failure mode.
10. Xây dựng threat model, test plan và checklist production cho gateway/backend authentication.

## 2. Gateway và backend trong kiến trúc phân tán

API gateway là thành phần nhận request từ client và chuyển tiếp tới một hoặc nhiều backend. Nó có thể cung cấp TLS termination, routing, authentication, rate limiting, request size limits, WAF integration và observability. Backend service xử lý logic nghiệp vụ và thường là nơi biết rõ resource, tenant, ownership và điều kiện authorization.

~~~mermaid
flowchart LR
    C["Browser / Mobile / Partner"] --> E["Edge: CDN / Load balancer"]
    E --> G["API Gateway"]
    G --> A["Identity Provider / Token verifier"]
    G --> S1["Backend service A"]
    G --> S2["Backend service B"]
    S1 --> D1["Database / Resource store"]
    S2 --> D2["Database / Resource store"]
    S1 --> Q["Message broker"]
    Q --> W["Background worker"]
~~~

### 2.1. Những việc gateway thường làm

- Xác minh access token hoặc session theo policy;
- Chặn request không có authentication hợp lệ;
- Áp dụng rate limit, quota và giới hạn kích thước;
- Chuẩn hóa một số metadata của request;
- Chọn route và backend phù hợp;
- Ghi correlation ID và security telemetry;
- Chuyển tiếp identity context theo hợp đồng nội bộ.

### 2.2. Những việc backend vẫn phải làm

- Xác thực caller service hoặc gateway;
- Kiểm tra token/context được phát hành cho đúng backend;
- Kiểm tra account state, tenant membership và authorization hiện tại;
- Kiểm tra resource ownership và object-level permission;
- Xác thực input và trạng thái nghiệp vụ;
- Kiểm tra lại quyền ở điểm commit với hành động nhạy cảm;
- Ghi audit theo principal, actor, tenant và action;
- Không tin dữ liệu identity do client tự gửi.

### 2.3. Gateway không phải authorization oracle

Gateway thường không có đủ dữ liệu nghiệp vụ để biết user có được sửa một bảng điểm cụ thể, xem hồ sơ của một học viên hay phê duyệt một khoản thanh toán hay không. Gateway có thể xác minh token và áp dụng coarse-grained policy, nhưng backend vẫn cần kiểm tra quyền trên resource mà nó quản lý.

## 3. Các danh tính trong một request

Một request đi qua gateway và backend có thể liên quan tới nhiều principal:

| Danh tính | Vai trò | Ví dụ |
| --- | --- | --- |
| **End user** | Người dùng cuối đã đăng nhập | Giảng viên |
| **Client application** | Ứng dụng gửi request | Web portal hoặc mobile app |
| **Gateway workload** | Service xử lý và chuyển tiếp request | API gateway instance |
| **Backend workload** | Service nhận request | Grade service |
| **Delegated actor** | Danh tính thay mặt user thực hiện hành động | Service A gọi Service B on behalf of user |
| **Resource owner** | Chủ sở hữu tài nguyên | Tenant/trường học |

Không được gộp các danh tính này thành một trường user ID duy nhất. Backend cần biết ai là người dùng cuối, service nào đang gọi nó, service đó được phép đại diện cho user đến đâu và resource thuộc phạm vi nào.

### 3.1. Subject và actor

- **Subject:** principal mà hành động hướng tới hoặc được thực hiện thay mặt.
- **Actor:** thực thể trực tiếp gửi request hoặc thực thi hành động.
- **Client:** ứng dụng OAuth đã yêu cầu token.
- **Audience:** resource server được phép nhận token.

Trong delegated call, subject có thể là user, actor là gateway hoặc service A. Nếu backend chỉ thấy user ID mà không xác thực caller service, nó có thể bị một workload khác giả mạo user context.

## 4. Trust boundary và mô hình tin cậy

Một kiến trúc an toàn phải nói rõ thành phần nào được tin, dựa trên bằng chứng nào và trong phạm vi nào.

~~~mermaid
flowchart TD
    U["Untrusted client network"] -->|TLS + access token| G["Gateway trust boundary"]
    G -->|mTLS + backend-scoped token| B["Backend trust boundary"]
    B -->|DB identity / scoped credentials| D["Data trust boundary"]
    G -->|Authenticated workload identity| I["Identity / token service"]
    B -->|Authenticated workload identity| I
~~~

### 4.1. Không tin mạng nội bộ một cách mặc định

Một service nằm trong private subnet vẫn có thể bị compromise, misconfiguration hoặc bị gọi từ workload không mong muốn. Network location không phải bằng chứng danh tính. Backend cần xác thực service caller và token/context theo policy.

### 4.2. TLS termination ở gateway

Gateway có thể kết thúc TLS bên ngoài, sau đó tạo kết nối TLS mới tới backend. Nếu gateway gửi HTTP không mã hóa qua mạng nội bộ, request có thể bị nghe lén hoặc sửa đổi khi có kẻ tấn công chiếm được network segment. Với dữ liệu nhạy cảm, dùng TLS nội bộ và mTLS khi cần xác thực hai chiều.

### 4.3. Xác định trust theo từng hop

Client-to-gateway, gateway-to-backend và backend-to-backend là các kết nối khác nhau. Mỗi hop cần:
- Bên gọi được xác thực;
- Bên nhận được xác thực;
- Token có audience phù hợp;
- Metadata được truyền qua kênh tin cậy;
- Quyền và phạm vi được giới hạn;
- Có cơ chế revoke và rotation.

Không suy luận rằng vì hop đầu tiên đã dùng HTTPS thì mọi hop phía sau đều được bảo vệ.

## 5. Authentication tại gateway

Gateway có thể đóng vai trò OAuth2 resource server hoặc tích hợp với token introspection/JWKS. Nó cần xác minh access token trước khi định tuyến request.

### 5.1. Các kiểm tra token cơ bản

Với JWT access token, gateway cần kiểm tra:
- Chữ ký bằng key được tin cậy từ issuer đã cấu hình;
- Thuật toán nằm trong allowlist và phù hợp với key;
- Issuer đúng;
- Audience bao gồm gateway/API hoặc resource server phù hợp;
- Thời hạn exp và nbf nếu có;
- Token type/profile đúng với access token được mong đợi;
- Scope/permission phù hợp với route coarse-grained;
- Client, tenant hoặc authentication context nếu policy yêu cầu.

Không chọn thuật toán chỉ dựa trên header của token. Không lấy JWKS từ URL tùy ý do token cung cấp. Cần pin issuer và cấu hình nguồn key đáng tin cậy.

### 5.2. JWT access token và ID token

ID token chứng minh kết quả đăng nhập cho client OIDC. Access token được cấp để truy cập resource server. API gateway không nên chấp nhận ID token làm bearer credential chỉ vì nó là JWT có chữ ký hợp lệ.

Token hợp lệ về mặt mật mã nhưng sai loại hoặc sai audience vẫn phải bị từ chối.

### 5.3. Opaque token và introspection

Với opaque access token, gateway có thể gọi introspection endpoint để biết token active, subject, client, scope và audience theo hợp đồng authorization server. Cần bảo vệ kết nối tới introspection service, cache kết quả có TTL phù hợp và xử lý outage theo risk policy.

### 5.4. Token validation không thay authorization

Scope như grades:read có thể cho phép truy cập nhóm API, nhưng không chứng minh user có quyền đọc mọi gradebook. Gateway có thể kiểm tra scope thô; backend vẫn kiểm tra tenant, resource ownership, role và trạng thái hiện tại.

## 6. Token forwarding: vì sao chuyển nguyên token có thể nguy hiểm?

Một cách triển khai đơn giản là gateway chuyển tiếp access token do client gửi tới mọi backend. Cách này có thể hoạt động, nhưng cần xem token được cấp cho ai và chứa quyền gì.

Rủi ro:
- Token có audience dành cho API A nhưng bị gửi sang API B;
- Backend B chấp nhận token quá rộng;
- Token của client bị lộ qua log hoặc tracing;
- Một backend bị compromise có thể dùng token để gọi service khác;
- Token chứa scope lớn hơn nhu cầu của downstream;
- Backend không thể phân biệt user gọi trực tiếp hay gateway đại diện.

### 6.1. Khi nào forwarding có thể chấp nhận?

Nếu token được cấp cho đúng resource server, mọi backend nhận token đều thuộc cùng trust boundary và policy cho phép, forwarding có thể phù hợp. Cần giới hạn audience, scope, TTL, network path và secret handling; mỗi backend vẫn xác minh token theo hợp đồng.

### 6.2. Khi nào cần token exchange?

Khi gateway hoặc service A gọi backend B thay mặt user, có thể dùng OAuth 2.0 Token Exchange hoặc cơ chế on-behalf-of đã được IdP hỗ trợ. Token mới có:
- Audience dành riêng cho backend B;
- Scope tối thiểu cho nghiệp vụ cần thực hiện;
- Subject là user gốc;
- Actor/client thể hiện service gọi;
- Thời hạn ngắn;
- Context/tenant được ràng buộc theo policy.

Không tự tạo token giả hoặc tự ký identity header bằng secret dùng chung nếu đã có cơ chế token exchange/workload identity chuẩn.

## 7. Token exchange và delegation

Delegation cho phép một service thực hiện hành động thay mặt user trong phạm vi giới hạn. Nó phải giữ được cả danh tính user gốc và service caller.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant AS as Authorization Server
    participant B as Backend B
    C->>G: Request + user access token
    G->>G: Validate issuer, audience, expiry, scope
    G->>AS: Token exchange: subject token + target audience
    AS-->>G: Token giới hạn cho Backend B
    G->>B: Request + delegated token qua mTLS
    B->>B: Validate token và gateway workload
    B->>B: Authorize user + actor + resource
    B-->>G: Response
    G-->>C: Response
~~~

### 7.1. Subject token

Subject token đại diện user hoặc principal ban đầu. Authorization server xác minh token và policy trước khi phát token mới. Gateway không nên tự tin rằng mọi subject token client gửi đều có thể được exchange.

### 7.2. Actor token hoặc actor claim

Token exchange có thể biểu diễn actor service. Backend cần biết service nào đang thực hiện hành động thay mặt user. Claim actor phải đến từ issuer đáng tin cậy và được xác minh, không phải trường JSON do gateway tự gửi mà backend không kiểm tra.

### 7.3. Giới hạn delegation

- Chỉ cho phép target audience đã đăng ký;
- Scope tối thiểu;
- TTL ngắn;
- Không cho delegation chain kéo dài không kiểm soát;
- Giới hạn số hop hoặc ghi lại delegation chain;
- Không cho service tự nâng quyền subject;
- Kiểm tra tenant và resource scope ở backend;
- Ghi audit actor và subject.

### 7.4. Impersonation và delegation khác nhau

Impersonation thường khiến downstream thấy service như thể nó là user. Delegation giữ được thông tin service actor và user subject. Nếu audit cần biết cả người yêu cầu lẫn service thực thi, delegation thường cung cấp ngữ cảnh rõ hơn.

## 8. Xác thực gateway với backend bằng mTLS

mTLS xác thực cả client và server trong TLS handshake. Gateway xác minh certificate của backend; backend xác minh certificate của gateway hoặc workload identity tương ứng.

### 8.1. Lợi ích

- Xác thực workload caller dựa trên certificate;
- Mã hóa dữ liệu trên từng hop;
- Giảm khả năng workload lạ gọi internal endpoint;
- Có thể gắn certificate identity với service account/namespace;
- Hỗ trợ rotation và short-lived certificate trong service mesh/PKI.

### 8.2. Những gì mTLS không tự làm

mTLS không chứng minh user cuối được phép truy cập resource. Nó chỉ xác thực workload/client certificate và bảo vệ kênh. Backend vẫn cần kiểm tra delegated user context và authorization.

### 8.3. Certificate identity mapping

Backend nên ánh xạ certificate identity/SPIFFE ID/SAN vào allowlist service principal hoặc policy. Không chỉ kiểm tra certificate chain tới một CA chung rồi cho mọi certificate trong CA gọi mọi API.

### 8.4. TLS termination và re-encryption

Nếu gateway kết thúc TLS client-facing, nó phải mở kết nối TLS/mTLS mới tới backend. Backend không thể coi certificate client ban đầu là peer certificate của kết nối nội bộ nếu gateway đã terminate TLS, trừ khi có một cơ chế proxy attestation riêng được thiết kế và xác minh.

Không chuyển tiếp certificate subject trong header rồi tin nó như bằng chứng mTLS. Header chỉ là dữ liệu; backend phải xác thực gateway và kiểm tra metadata có nguồn gốc đáng tin.

## 9. Workload identity giữa các service

Trong hệ thống phân tán, service cần danh tính riêng thay vì dùng một API key dùng chung hoặc tin network IP.

### 9.1. Workload identity

Workload identity có thể được cấp dựa trên:
- Service account/namespace;
- Platform identity của container/VM;
- SPIFFE ID hoặc hệ thống tương đương;
- Certificate ngắn hạn;
- Cloud workload identity federation.

Credential cần được cấp tự động, giới hạn audience và có khả năng rotate/revoke.

### 9.2. Least privilege cho service

Service A chỉ nên có quyền gọi các operation cần thiết trên service B. Không cấp một token nội bộ có scope admin cho mọi microservice.

### 9.3. Không dùng IP làm danh tính service

IP/hostname có thể thay đổi, được tái sử dụng hoặc chia sẻ qua NAT. Network policy hữu ích như lớp bảo vệ bổ sung, nhưng không thay thế xác thực workload identity.

## 10. Identity context và internal headers

Một số gateway thêm header như user ID, tenant ID, role hoặc scope để backend đọc. Đây là cách dễ triển khai nhưng có thể nguy hiểm nếu backend không biết header do ai tạo.

### 10.1. Header spoofing

Client có thể gửi trước header:
- X-User-Id;
- X-Role;
- X-Tenant-Id;
- X-Authenticated-User;
- X-Forwarded-User.

Nếu gateway chỉ thêm giá trị mới mà không xóa giá trị do client gửi, backend có thể đọc nhầm header attacker kiểm soát.

### 10.2. Quy tắc an toàn

- Gateway phải xóa/ghi đè toàn bộ identity header nhận từ client;
- Backend chỉ nhận traffic từ gateway/service đã xác thực;
- Kênh nội bộ dùng mTLS hoặc workload identity;
- Metadata phải theo schema/hợp đồng rõ ràng;
- Backend xác minh issuer/signature nếu metadata là token/signed assertion;
- Không coi header tenant/user là bằng chứng duy nhất nếu không có authenticated channel và trust contract;
- Không cho client gửi role hoặc permission để backend sử dụng.

### 10.3. Không tự thiết kế signed header tùy tiện

Một header ký bằng HMAC có thể tạo ra một giao thức mới với vấn đề key distribution, rotation, replay, canonicalization, audience, timestamp và downgrade. Ưu tiên access token có audience, token exchange, mTLS hoặc cơ chế assertion tiêu chuẩn. Nếu phải dùng signed context, cần thiết kế và review chuyên môn riêng.

## 11. Tenant context qua gateway/backend

Trong SaaS multi-tenant, tenant selector thường đến từ host, path hoặc request. Gateway có thể resolve tenant sơ bộ, nhưng backend vẫn phải kiểm tra membership và resource ownership.

### 11.1. Tenant context không phải quyền

Header tenant đã xác minh chỉ cho biết request đang chọn tenant nào. Nó không chứng minh user là member hoặc resource thuộc tenant đó. Backend cần kiểm tra:
- Principal subject;
- Tenant active;
- Membership active;
- Role/permission trong tenant;
- Resource tenant ownership;
- Action được phép.

### 11.2. Ràng buộc token với tenant

Nếu token chứa tenant claim, backend phải xác minh token và freshness. Một user có thể có role khác nhau trong tenant A và B; không dùng role claim của A khi request nhắm B.

### 11.3. Tenant switching

Khi client đổi tenant, gateway/backend phải resolve lại tenant và kiểm tra membership. Không dùng lại cache authorization của tenant trước. Với request song song, context phải được gắn vào từng request hoặc token/session scope cụ thể để tránh lẫn tenant.

## 12. Authorization defense in depth

Gateway có thể chặn request không có token hợp lệ hoặc scope coarse-grained. Backend là nơi hiểu domain resource nên cần quyết định object-level.

~~~mermaid
flowchart TD
    R["Request đến gateway"] --> G1["Validate access token"]
    G1 --> G2["Coarse route/scope policy"]
    G2 --> M["mTLS + workload identity"]
    M --> B1["Backend validate delegated token"]
    B1 --> B2["Check account + membership"]
    B2 --> B3["Check resource tenant + ownership"]
    B3 --> B4["Check action/role/ABAC"]
    B4 --> D{"Allowed?"}
    D -->|"Có"| X["Thực hiện nghiệp vụ"]
    D -->|"Không"| N["DENY + audit"]
~~~

### 12.1. Authentication và authorization là hai bước riêng

Gateway xác minh token không có nghĩa request được phép. Backend không nên suy luận quyền từ việc request đến qua gateway. Backend cũng không nên chỉ kiểm tra user ID mà bỏ qua action và resource.

### 12.2. Policy enforcement ở backend

Mỗi backend cần xác định:
- Những issuer/client nào được chấp nhận;
- Audience nào dành cho service;
- Service caller nào được gọi endpoint;
- User subject nào đang được đại diện;
- Action/resource/tenant nào được phép;
- Authentication freshness/assurance có đủ không.

### 12.3. Internal endpoint không mặc nhiên an toàn

Endpoint nội bộ có thể bị gọi qua SSRF, compromised workload, misconfigured ingress hoặc service mesh bypass. Mọi endpoint nhạy cảm cần authentication và authorization phù hợp dù không public Internet.

## 13. API gateway và backend theo mô hình BFF

Backend-for-Frontend (BFF) có thể giữ token ở server-side và cung cấp cookie session cho browser. Browser không nhất thiết nhận access token dùng trực tiếp với mọi API.

### 13.1. Lợi ích

- Giảm exposure của access/refresh token trong browser;
- Có thể quản lý session server-side;
- Giới hạn token theo backend và audience;
- Kiểm soát CSRF, cookie và session lifecycle tập trung.

### 13.2. Rủi ro

- BFF trở thành thành phần nhạy cảm cần harden;
- Cookie session cần CSRF protection;
- BFF phải xác thực downstream service và scope;
- Không biến BFF thành proxy có quyền rộng không kiểm soát;
- Session revocation và logout cần đồng bộ.

### 13.3. BFF vẫn phải bảo vệ backend

Nếu BFF gọi backend bằng service token rộng, backend có thể mất ngữ cảnh user. Dùng delegation hoặc policy context có xác thực để backend biết hành động được thực hiện thay mặt ai.

## 14. Request context, tracing và audit

Observability metadata giúp theo dõi request nhưng không phải bằng chứng authentication.

### 14.1. Correlation ID và trace context

Trace ID, span ID và correlation ID phục vụ liên kết log/tracing. Chúng có thể đến từ client và cần được validate/normalize theo policy. Không dùng trace ID làm identity, tenant authorization hoặc secret.

### 14.2. Security audit context

Audit event có thể ghi:
- Subject/user reference;
- Actor/workload identity;
- Client application;
- Tenant;
- Action và resource reference;
- Authentication method/context cần thiết;
- Gateway/backend service;
- Decision và reason code;
- Correlation ID;
- Timestamp và policy version.

Không ghi access token, refresh token, session cookie, password hoặc private key vào log.

### 14.3. Giữ actor chain

Trong call chain A -> B -> C, audit nên giữ được:
- User gốc;
- Service A là actor đầu tiên;
- Service B là actor tiếp theo;
- Token audience và scope được sử dụng;
- Request/correlation reference.

Không ghi đè subject thành service account rồi làm mất user gốc nếu nghiệp vụ cần accountability.

## 15. Replay, token theft và sender constraint

Bearer token có thể được dùng bởi bất kỳ ai nắm giữ nó cho tới khi hết hạn hoặc bị revoke. Gateway/backend cần giảm khả năng token bị lấy và tái sử dụng.

### 15.1. Giảm rủi ro bearer token

- TLS trên mọi hop;
- Không log token hoặc đưa token vào URL;
- TTL ngắn và scope tối thiểu;
- Bảo vệ secret store và process memory;
- Revoke token/session khi compromise;
- Hạn chế audience;
- Tránh chuyển token tới service không cần nó.

### 15.2. Sender-constrained token

Có thể dùng mTLS-bound access token hoặc DPoP theo khả năng hệ sinh thái. Token gắn với key của client/caller khiến việc đánh cắp token đơn lẻ khó tái sử dụng từ một client khác. Resource server phải xác minh proof và binding đúng chuẩn; chỉ bật claim mà không kiểm tra proof là không đủ.

### 15.3. Replay trong service-to-service

Với request có tác động tài chính hoặc thay đổi trạng thái, có thể cần idempotency key, request nonce hoặc transaction reference. Idempotency không thay thế authentication, nhưng giúp tránh thực hiện cùng một nghiệp vụ nhiều lần khi retry hoặc replay.

## 16. Revocation, freshness và cache

Trong distributed system, trạng thái token/membership/role có thể thay đổi trong khi request vẫn đang chạy.

### 16.1. JWT và stale authorization

JWT tự chứa có thể được backend xác minh offline đến exp. Nếu user bị khóa hoặc membership bị revoke sau khi token phát hành, backend có thể tiếp tục chấp nhận claim cũ nếu không có freshness mechanism.

### 16.2. Cơ chế cập nhật

- Access token TTL ngắn;
- Introspection cho token opaque hoặc action nhạy cảm;
- Session/authorization version;
- Revocation event và cache invalidation;
- Online membership/role check;
- Token exchange với audience/scope ngắn hạn.

### 16.3. Cache policy

Cache token validation hoặc authorization decision cần key chứa principal, audience, tenant, action/resource và version liên quan. TTL phải phù hợp với SLA revoke. Không dùng cache key chỉ theo user ID cho mọi backend hoặc tenant.

### 16.4. In-flight request

Nếu role hoặc session bị revoke sau khi gateway đã xác minh nhưng trước khi backend commit, action nhạy cảm cần recheck state tại điểm commit. Định nghĩa rõ request nào được phép hoàn tất sau revoke và request nào phải bị hủy.

## 17. Failure mode và degraded operation

Gateway, identity provider, introspection endpoint, service mesh và backend có thể gặp outage. Fail mode cần dựa trên loại hành động.

| Sự cố | Hành động an toàn có thể áp dụng |
| --- | --- |
| JWKS/issuer không truy cập được | Dùng key cache còn hợp lệ theo policy; không tin key mới chưa xác minh |
| Introspection outage | Fail closed cho action nhạy cảm; chỉ dùng cache active trong TTL đã phê duyệt |
| mTLS certificate hết hạn | Từ chối kết nối workload; khôi phục qua PKI/rotation |
| Gateway unavailable | Failover gateway có cùng trust policy; không bypass authentication |
| Backend không nhận identity context | Từ chối request, không đoán user từ header khác |
| Revocation event bị mất | Reconciliation/version check phát hiện stale state |
| Policy engine outage | Fail closed cho quyền cao; degraded mode chỉ khi đã được phê duyệt |
| Clock skew | Xử lý exp/nbf với clock sync và leeway nhỏ có kiểm soát |

Không tự động cho phép mọi request khi gateway hoặc identity provider gặp lỗi. Một số thao tác ít rủi ro có thể có degraded mode, nhưng phải định nghĩa rõ phạm vi và audit.

## 18. Retry, queue và asynchronous delegation

Một request có thể chuyển thành message hoặc background job. Khi đó, HTTP connection và token gốc có thể đã hết hạn trước khi job chạy.

### 18.1. Không đưa bearer token nguyên dạng vào queue

Token có thể bị lộ qua broker, dead-letter queue, message dump hoặc replay. Thay vào đó, lưu reference tới transaction hoặc phát một delegated job credential ngắn hạn, có audience và scope cụ thể.

### 18.2. Job identity

Job cần xác định:
- Workload identity của worker;
- Actor/user đã yêu cầu;
- Tenant đã xác minh;
- Action và resource scope;
- Purpose và thời điểm hết hạn;
- Authorization policy cần recheck;
- Idempotency/correlation reference.

### 18.3. Reauthorize khi thực thi

Nếu membership hoặc quyền user thay đổi trước lúc job chạy, policy phải xác định job tiếp tục, hủy hay yêu cầu approval mới. Với export dữ liệu nhạy cảm, kiểm tra lại account, tenant, resource ownership và authorization trước khi tạo artifact.

## 19. Threat model cho gateway và backend

| Threat | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| Header spoofing | Client gửi X-User-ID/X-Role giả | Gateway xóa header; backend xác thực gateway và token |
| Wrong audience | Token của API A gửi tới API B | Backend kiểm tra aud chính xác |
| ID token misuse | API chấp nhận ID token làm access token | Kiểm tra token type/profile và audience |
| Confused deputy | Gateway/service quyền rộng làm thay caller | Delegation, actor identity và least privilege |
| Token replay | Bearer token bị đánh cắp và dùng lại | TLS, TTL, audience, sender constraint, revoke |
| Stale authorization | Role/membership đã thu hồi nhưng token/cache cũ | Version, introspection và online check |
| Internal network trust | Workload lạ gọi backend private | mTLS/workload identity và service policy |
| Tenant spoofing | Caller thay tenant header/body | Resolve tenant server-side và membership check |
| Gateway bypass | Client truy cập backend trực tiếp | Network policy + backend authentication |
| Token leakage | Token xuất hiện trong log/tracing | Redaction, secret handling và access control |
| Overbroad service token | Một service gọi mọi backend | Audience/scope riêng cho từng service |
| Replay/duplicate action | Retry thực hiện giao dịch nhiều lần | Idempotency và transaction binding |
| Queue context loss | Job thiếu actor/tenant hoặc token hết hạn | Authenticated job identity và reauthorization |
| JWKS confusion | Tin key URL hoặc kid tùy ý | Pin issuer/JWKS source, validate key selection |

## 20. Pseudocode gateway và backend

### 20.1. Gateway

~~~text
handle_external_request(request):
    remove_untrusted_identity_headers(request)
    client_token = extract_access_token(request)

    claims = validate_access_token(
        token = client_token,
        trusted_issuer = configured_issuer,
        expected_audience = gateway_resource,
        allowed_algorithms = configured_algorithms,
        required_token_type = ACCESS_TOKEN
    )
    require claims.active
    require route_scope_policy_allows(claims, request.route)

    tenant = resolve_tenant_from_trusted_selector(request)
    require membership_is_current(claims.subject, tenant)

    downstream_token = token_exchange_if_required(
        subject_token = client_token,
        target_audience = backend_resource,
        requested_scope = minimum_backend_scope,
        actor = gateway_workload_identity
    )

    return forward_over_mtls(
        request = request,
        token = downstream_token,
        verified_context = tenant_and_correlation_context
    )
~~~

### 20.2. Backend

~~~text
handle_internal_request(request, peer_identity):
    require peer_identity in allowed_gateway_workloads

    token = extract_backend_access_token(request)
    claims = validate_access_token(
        token,
        trusted_issuer = configured_issuer,
        expected_audience = this_backend,
        allowed_algorithms = configured_algorithms
    )

    require claims.actor identifies allowed caller
    require claims.subject is valid principal
    require token_scope_allows(claims, request.action)

    tenant = resolve_and_validate_tenant_context(request, claims)
    require current_membership(claims.subject, tenant)

    resource = load_resource(request.resource_id)
    require resource.tenant_id == tenant.id
    require authorization_policy_allows(
        subject = claims.subject,
        actor = claims.actor,
        tenant = tenant,
        action = request.action,
        resource = resource
    )

    return execute_with_audit_context()
~~~

Pseudocode mô tả nguyên tắc. Thực tế cần thư viện OAuth/OIDC đã được kiểm chứng, kiểm tra token profile, clock skew, key rotation, parsing limits, transaction boundary, error mapping và policy version. Không tự triển khai mật mã hoặc JWT verification bằng code tự viết.

## 21. Kiểm thử gateway và backend authentication

Test trong staging với issuer, gateway, backend và workload identity giả lập. Không dùng token production hoặc secret thật.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Valid token | Access token đúng issuer/audience/expiry | Gateway chấp nhận nếu scope hợp lệ |
| Wrong issuer | Token từ IdP không tin cậy | Gateway từ chối |
| Wrong audience | Token cho API A gửi API B | Backend từ chối |
| ID token | Dùng ID token gọi API | Từ chối |
| Expired token | Token hết hạn | Từ chối |
| Wrong algorithm | Token dùng alg ngoài allowlist | Từ chối |
| Unknown key | kid không có trong JWKS tin cậy | Từ chối hoặc refresh JWKS theo policy |
| JWKS outage | Identity provider tạm lỗi | Dùng cache hợp lệ hoặc fail closed theo policy |
| Header spoof | Client gửi X-User-ID/X-Role giả | Gateway xóa/ghi đè; backend không tin |
| Direct backend | Client gọi thẳng internal backend | Network/workload authentication từ chối |
| mTLS identity | Certificate gateway hợp lệ | Backend xác minh đúng workload |
| Untrusted workload | Certificate từ workload không allowlist | Backend từ chối |
| Token forwarding | Token audience API A chuyển sang B | B từ chối |
| Token exchange | Delegated token audience B, scope tối thiểu | B chấp nhận nếu actor/user/policy hợp lệ |
| Actor mismatch | Actor claim không khớp workload peer | Từ chối |
| Confused deputy | Service A yêu cầu quyền ngoài delegation | Từ chối |
| Tenant spoof | Thay tenant header/body | Membership/resource check từ chối |
| Stale membership | Membership bị revoke sau token issue | Bị từ chối trong SLA |
| Replay | Dùng lại request/transaction đã tiêu thụ | Idempotency/nonce ngăn xử lý lặp |
| Cache leakage | Decision của user/tenant A dùng cho B | Cache key/version ngăn tái sử dụng |
| Queue token | Message chứa bearer token nhạy cảm | Kiểm tra policy; ưu tiên credential reference |
| Background job | Actor mất membership trước khi job chạy | Reauthorize hoặc hủy theo policy |
| In-flight revoke | Revoke xảy ra trước commit action | Recheck tại commit theo SLA |
| Log redaction | Bật debug/trace | Không log token, cookie hoặc private key |
| Gateway failover | Chuyển sang gateway instance khác | Trust policy và key configuration nhất quán |

### 21.1. Bất biến bảo mật

- Gateway không chuyển tiếp identity header do client tự kiểm soát;
- Backend xác thực workload caller trên từng hop;
- Token có đúng issuer, audience, type, expiry và scope;
- ID token không được dùng thay access token;
- Backend kiểm tra subject, actor, tenant, resource và action;
- Token exchange không mở rộng quyền ngoài policy;
- Direct backend access không bypass gateway/backend authentication;
- Stale membership, session hoặc role không được dùng vô thời hạn;
- Log và queue không chứa bearer secret không cần thiết.

## 22. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ xác thực ở gateway | Backend bị gọi trực tiếp hoặc caller giả mạo | Backend authentication và network policy |
| Backend tin X-User-ID | Client giả danh người dùng | Authenticated context/token |
| Forward mọi token tới mọi service | Token có audience/scope quá rộng | Token exchange và audience riêng |
| Chấp nhận ID token làm API token | Nhầm mục đích token | Validate token type/profile và aud |
| Tin private network | Workload compromise có thể gọi API | mTLS/workload identity |
| mTLS được xem là user auth | Service hợp lệ truy cập sai user/resource | Delegated user token và authorization |
| Chỉ kiểm tra scope tại gateway | Không kiểm tra resource ownership | Backend object-level authorization |
| Không giữ actor chain | Audit không biết service nào thực thi | Subject + actor context |
| Forwarded header không được làm sạch | Header spoofing | Strip/overwrite ở gateway |
| Token trong log | Credential leakage | Redaction và secret scanning |
| Không xử lý token revoke | Token/session cũ còn dùng được | TTL/version/introspection/revocation |
| Dùng shared service secret | Blast radius lớn và khó attribution | Workload identity riêng |
| Queue giữ bearer token | Token bị lộ hoặc replay | Job identity và token exchange |
| Fail open khi IdP outage | Authentication bypass | Risk-based fail mode |

## 23. Checklist production

1. **Trust boundary:** Mỗi hop client/gateway/backend/service có trust contract rõ?
2. **Gateway:** Token được xác minh theo issuer, audience, signature, type, expiry và scope?
3. **Backend:** Backend có xác thực caller workload và delegated token?
4. **Audience:** Mỗi resource server có audience riêng hoặc trust domain được xác định?
5. **Delegation:** Subject và actor được giữ rõ; token exchange có scope/TTL tối thiểu?
6. **mTLS:** Gateway/backend certificate được xác minh, mapping vào service identity và rotate?
7. **Headers:** Identity/tenant/forwarded headers từ client bị strip hoặc overwrite?
8. **Authorization:** Backend kiểm tra membership, tenant, resource ownership và action?
9. **Direct access:** Backend không thể bị gọi qua đường bypass không được bảo vệ?
10. **Token lifecycle:** TTL, revocation, refresh, cache và key rotation có SLA?
11. **Replay:** Sender constraint, nonce hoặc idempotency được dùng khi phù hợp?
12. **Async:** Queue/job giữ actor/tenant/purpose và reauthorize khi thực thi?
13. **Observability:** Trace/correlation không bị nhầm là identity; log redaction hoạt động?
14. **Failure mode:** IdP, JWKS, introspection, gateway hoặc policy outage không làm fail open?
15. **Tenant:** Tenant context được resolve và kiểm tra ở backend?
16. **Operations:** Có inventory workload, certificate, service scope và owner?
17. **Testing:** Có test direct backend, header spoof, wrong audience, stale token, replay và confused deputy?

## 24. Bài tập tình huống

Một nền tảng học tập có API gateway xác minh JWT từ IdP. Gateway thêm các header X-User-ID, X-Role và X-Tenant-ID rồi gọi ba backend qua HTTP trong private network. Backend chỉ kiểm tra các header này, không xác minh token hoặc caller service. Một service có thể chuyển tiếp nguyên bearer token của user tới mọi backend. JWT có audience chung và TTL 12 giờ. Khi user bị xóa membership, gateway cache role trong 30 phút.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** trong trust boundary, header propagation, token audience và authorization.
2. Thiết kế gateway-to-backend mTLS và xác thực workload identity.
3. Đề xuất token exchange hoặc delegation token có audience/scope riêng.
4. Xác định dữ liệu subject, actor, tenant và resource cần backend kiểm tra.
5. Thiết kế cơ chế loại bỏ identity header do client gửi.
6. Đề xuất xử lý JWT cũ, cache membership và request đang chạy khi revoke.
7. Xây dựng test cho direct backend access, header spoofing, wrong audience, actor mismatch và confused deputy.

**Gợi ý đối chiếu:** private network không phải identity; backend cần xác thực gateway/service; không tin header identity chưa được bảo vệ; audience riêng và token exchange giới hạn scope; backend kiểm tra tenant/resource; membership freshness và revoke có SLA; không log bearer token.

## 25. Ghi nhớ

- Gateway là điểm kiểm soát đầu vào hữu ích, nhưng không thay thế authentication và authorization ở backend.
- Mỗi hop cần xác thực caller, xác thực peer, token audience phù hợp và metadata có nguồn gốc đáng tin.
- Access token dành cho resource server; ID token dành cho client OIDC và không nên dùng thay access token.
- Forward nguyên bearer token có thể mở rộng blast radius; token exchange/delegation giúp giới hạn audience, scope và giữ actor chain.
- mTLS xác thực workload và bảo vệ kênh, không chứng minh user có quyền trên resource.
- Identity header chỉ đáng tin khi được gateway làm sạch, truyền qua authenticated channel và backend xác minh theo trust contract.
- Backend phải kiểm tra principal, actor, tenant, membership, resource ownership và action.
- JWT/cache có thể giữ quyền cũ; cần TTL, version, introspection, invalidation và recheck tại commit.
- Queue/background job cần workload identity, actor/tenant context và reauthorization khi thực thi.
- Observability metadata không phải authentication evidence; không log token hoặc secret.

Gateway và backend phối hợp an toàn khi **gateway xác minh danh tính và giới hạn request ở điểm vào, backend xác thực service caller và tự quyết định quyền trên resource, còn token/context truyền giữa chúng có audience, scope, actor và tenant rõ ràng**. Ranh giới tin cậy phải được duy trì qua mọi hop, kể cả queue và background worker, để một thành phần bị compromise không thể tự nhận danh tính hoặc quyền của thành phần khác.
