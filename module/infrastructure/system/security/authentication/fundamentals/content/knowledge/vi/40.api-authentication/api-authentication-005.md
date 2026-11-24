# Gateway authentication — Xác thực request tại cổng API

Một ứng dụng di động gọi API qua một API gateway. Gateway tiếp nhận HTTPS, định tuyến request tới các service phía sau và áp dụng giới hạn lưu lượng. Nếu gateway chỉ kiểm tra rằng request có header Authorization mà không xác minh token, bất kỳ client nào cũng có thể tự gửi một chuỗi giả. Nếu gateway xác minh token nhưng chuyển nguyên các header X-User, X-Role do client gửi tới backend, attacker có thể giả danh người dùng khác. Nếu backend có thể truy cập trực tiếp từ Internet, attacker còn có thể bỏ qua gateway hoàn toàn.

**Gateway authentication** là việc xác minh danh tính của client, workload hoặc người dùng tại API gateway trước khi request được chuyển tiếp tới upstream. Gateway có thể xác minh API key, OAuth access token, JWT, opaque token hoặc client certificate; sau đó gắn kết quả xác minh vào ngữ cảnh request nội bộ theo một cơ chế đáng tin cậy.

Gateway là một điểm thực thi quan trọng ở ranh giới API, nhưng xác thực tại gateway không thay thế mọi quyết định bảo mật ở backend. Gateway có thể xác minh caller và áp dụng policy chung; backend vẫn cần kiểm tra quyền trên đối tượng, trạng thái nghiệp vụ, tenant và hành động cụ thể. Nếu backend không thể tin cậy đường truyền hoặc metadata từ gateway, danh tính đã xác minh có thể bị giả mạo trên chặng tiếp theo.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học thiết kế xác thực tại API gateway, phân biệt API key với access token và mTLS, kiểm tra JWT/opaque token đúng cách, bảo vệ header identity propagation, thiết lập trust giữa gateway và upstream, xử lý multi-tenant, cache/revocation, lỗi xác thực và vận hành key an toàn. Mục tiêu là tạo một ranh giới xác thực rõ ràng từ client tới API mà không làm suy yếu kiểm soát ở các service phía sau.

## 1. Gateway authentication là gì?

API gateway thường đứng trước một hoặc nhiều API service. Nó có thể kết thúc TLS, xác minh credential, định tuyến, áp dụng rate limit, ghi access log và chuyển tiếp request. Trong vai trò authentication enforcement point, gateway cần trả lời:

- Ai đang gọi API: user, ứng dụng, service hay workload?
- Bằng chứng xác thực có hợp lệ và được phát hành bởi issuer tin cậy không?
- Credential có dành cho API này không?
- Credential còn hiệu lực, chưa bị thu hồi và đáp ứng phương thức được yêu cầu không?
- Danh tính đã xác minh sẽ được truyền tới upstream như thế nào?
- Backend có thể xác minh request thực sự đến từ gateway tin cậy không?

Gateway authentication không chỉ là “có token hay không”. Một request phải được kiểm tra theo trust configuration và policy trước khi được chấp nhận.

### 1.1. Phân biệt authentication và authorization

| Hoạt động | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Caller là ai hoặc chứng minh quyền kiểm soát credential nào? | Xác minh JWT, introspect opaque token, kiểm tra client certificate |
| Coarse-grained authorization | Caller có quyền gọi API hoặc nhóm endpoint này không? | Scope invoice.read, role billing-service |
| Resource authorization | Caller có quyền với bản ghi/tài nguyên cụ thể không? | User A chỉ đọc invoice thuộc tenant A |
| Business policy | Hành động có hợp lệ theo trạng thái nghiệp vụ không? | Không cho sửa hóa đơn đã khóa |

Gateway có thể thực hiện authentication và một phần authorization tổng quát. Backend thường có ngữ cảnh dữ liệu và business rules để quyết định resource authorization. Không coi việc token hợp lệ là bằng chứng caller được phép đọc mọi object.

### 1.2. Gateway là điểm thực thi, không phải nguồn danh tính

Gateway xác minh credential được phát hành bởi identity provider, authorization server, CA hoặc một nguồn tin cậy khác. Gateway không tự biến header do client khai thành danh tính đáng tin.

Ví dụ, client gửi X-User-Id: admin không làm caller trở thành admin. Gateway phải bỏ header identity do client tự gửi, xác minh credential thực, rồi tạo metadata nội bộ theo hợp đồng bảo mật. Backend chỉ tin metadata đó khi request đến qua một kênh gateway đã xác thực.

## 2. Ranh giới tin cậy và kiến trúc

Một kiến trúc phổ biến có các thành phần:

- **External client:** browser, mobile app, partner hoặc service bên ngoài.
- **Edge/load balancer:** tiếp nhận kết nối, lọc lưu lượng và chuyển request tới gateway.
- **API gateway:** xác minh credential, áp dụng policy chung và định tuyến.
- **Identity provider / authorization server:** phát hành token, quản lý client và cung cấp introspection/JWKS.
- **Upstream API:** thực hiện nghiệp vụ và kiểm tra quyền trên tài nguyên.
- **Internal service mesh:** bảo vệ kết nối east-west giữa các workload.
- **Audit/monitoring:** ghi nhận kết quả xác thực, policy và request reference.

~~~mermaid
flowchart LR
    C[External client] -->|HTTPS + credential| E[Edge / Load balancer]
    E --> G[API gateway]
    G <-->|JWKS / introspection| I[Authorization server]
    G -->|mTLS + trusted identity context| U[Upstream API]
    U --> D[(Business data)]
    G --> A[Audit / monitoring]
    U --> A
~~~

Các ranh giới cần được xác định:

1. Client không đáng tin; mọi header, query, body và credential đều cần validate.
2. Gateway chỉ tin issuer, CA, JWKS endpoint và introspection endpoint đã cấu hình.
3. Upstream chỉ tin identity metadata đến từ gateway đã xác thực, không tin header có cùng tên từ bất kỳ nguồn nào.
4. Network policy phải ngăn client bên ngoài truy cập trực tiếp upstream nếu kiến trúc yêu cầu gateway là điểm vào duy nhất.
5. Gateway-to-upstream cần TLS, thường là mTLS trong môi trường có nhiều workload hoặc rủi ro cao.
6. Mỗi upstream vẫn xác minh quyền trên resource và tenant.

### 2.1. Không để lộ upstream bypass

Nếu gateway kiểm tra token nhưng service backend có public ingress riêng, attacker có thể gọi trực tiếp backend và bỏ qua gateway policy. Cần:

- Đặt upstream trong private network hoặc chỉ cho phép ingress từ gateway/service mesh.
- Dùng firewall, security group, Kubernetes NetworkPolicy hoặc cơ chế tương đương.
- Xác thực gateway ở chặng upstream bằng mTLS hoặc workload identity.
- Không xem địa chỉ IP nội bộ là bằng chứng xác thực.
- Kiểm thử đường truy cập trực tiếp, alternate hostname, port và ingress controller.

Một kiến trúc có gateway nhưng vẫn để backend mở công khai không có ranh giới xác thực rõ.

## 3. Chọn cơ chế xác thực tại gateway

Không có một cơ chế phù hợp cho mọi caller. Chọn theo loại client, mức assurance, khả năng quản lý credential và nhu cầu delegation.

| Cơ chế | Caller thường gặp | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| API key | Partner integration, service đơn giản hoặc định danh ứng dụng | Dễ cấp, dễ phân biệt client/project | Thường là bearer secret; không tự biểu diễn user hoặc scope chi tiết |
| OAuth 2.0 access token | User-facing app, partner, service-to-service | Scope, audience, issuer và lifetime rõ | Cần quản lý issuer, token lifecycle và validation |
| JWT access token | API cần xác minh cục bộ | Có thể kiểm tra chữ ký/claims không cần introspection mỗi request | Revocation tức thời khó; token bearer vẫn có thể bị đánh cắp |
| Opaque access token | API cần trạng thái tập trung | Introspection có thể cập nhật trạng thái nhanh | Phụ thuộc authorization server hoặc cache |
| mTLS client certificate | Partner/service/workload | Xác minh possession của private key tại tầng TLS | PKI, rotation và mapping identity cần quản lý |
| DPoP hoặc sender-constrained token | Client có khả năng giữ key riêng | Giảm khả năng sử dụng token bị copy độc lập | Gateway phải kiểm tra proof và replay state |

### 3.1. API key

API key thường định danh một ứng dụng, project hoặc partner. Nó không mặc nhiên xác minh người dùng cuối. Nếu key là bearer secret, ai lấy được key đều có thể dùng nó trong phạm vi quyền được cấp.

Khi dùng API key:

- Sinh bằng CSPRNG với entropy đủ cao.
- Lưu hash/HMAC hoặc bản tham chiếu an toàn phía server; không lưu raw key nếu không cần.
- Gắn key với client, tenant, environment, scope và quota.
- Có expiry hoặc rotation policy; hỗ trợ overlap ngắn khi chuyển key.
- Cho phép revoke và theo dõi lần sử dụng cuối.
- Chỉ truyền qua HTTPS trong header chuyên dụng; không đặt trong URL.
- Không ghi raw key vào access log, tracing hoặc analytics.
- Không dùng một key chung cho nhiều ứng dụng, developer hoặc môi trường.

API key có thể phù hợp để nhận diện client và áp quota, nhưng nếu API cần xác thực user, delegation, audience hoặc assurance thì dùng OAuth/OIDC hoặc cơ chế phù hợp hơn. Không biến API key thành một mật khẩu user thay thế.

### 3.2. OAuth 2.0 access token

Gateway có thể nhận access token do authorization server phát hành. Với user-facing API, token có thể đại diện user và client; với service-to-service, token có thể đại diện workload/service principal.

Gateway cần xác minh:

- Issuer đúng với trust configuration.
- Audience dành cho API hoặc resource tương ứng.
- Token còn hiệu lực theo exp và nbf.
- Chữ ký hợp lệ nếu token là JWT.
- Scope/role đáp ứng endpoint policy.
- Client/tenant/subject phù hợp với API.
- Sender binding nếu token được ràng buộc với certificate hoặc DPoP key.

Không nhận ID token thay cho access token chỉ vì cả hai đều là JWT. ID token được phát hành để client xác minh kết quả đăng nhập; access token được phát hành để resource server truy cập API. Cần kiểm tra token type, audience và profile theo protocol.

### 3.3. JWT và opaque token

JWT có thể được xác minh tại gateway bằng public key đã tin cậy. Opaque token cần introspection hoặc tra cứu state. Cả hai đều cần kiểm tra audience, expiry, scope và trạng thái caller.

JWT thường không được mã hóa. Payload có thể đọc được bởi người sở hữu token; không đưa secret hoặc PII không cần thiết vào claims. Chữ ký JWT bảo vệ integrity/authenticity của token, không tự chống replay hay ngăn bearer token bị copy.

## 4. Xác minh JWT access token đúng cách

Khi gateway nhận JWT, không chỉ decode phần header/payload rồi tin claims. Gateway phải xác minh chữ ký và toàn bộ điều kiện của token profile.

### 4.1. Các kiểm tra cần thiết

1. Chỉ chấp nhận thuật toán nằm trong allowlist của issuer/client policy.
2. Lấy signing key từ JWKS endpoint đã cấu hình hoặc cache tin cậy.
3. Dùng kid để chọn key phù hợp; không tải URL tùy ý từ token header.
4. Xác minh chữ ký trên nguyên token.
5. Kiểm tra iss thuộc issuer được phép.
6. Kiểm tra aud khớp chính xác API/resource này.
7. Kiểm tra exp, nbf và clock skew nhỏ.
8. Kiểm tra token type/profile để không nhầm ID token, refresh token hoặc JWT khác.
9. Kiểm tra scope/roles, client, tenant và subject theo endpoint policy.
10. Kiểm tra cnf/certificate/DPoP binding nếu token sender-constrained.

Không chấp nhận alg=none, thuật toán ngoài policy hoặc key được lấy từ URL do token tự khai. Không dùng cùng một validation rule quá rộng cho mọi loại JWT trong hệ thống.

### 4.2. JWKS và key rotation

Authorization server có thể xoay signing key. Gateway cần:

- Cache JWKS với TTL hợp lý và hỗ trợ refresh khi gặp kid mới.
- Chỉ lấy JWKS từ endpoint đã cấu hình, qua TLS và trust chain hợp lệ.
- Có timeout, retry/backoff và bảo vệ chống request storm khi nhiều request cùng gặp key mới.
- Duy trì overlap giữa key cũ và key mới đủ để token hợp lệ cũ hết hạn.
- Không xóa key cũ quá sớm nếu còn token hợp lệ được ký bằng key đó.
- Khi key bị compromise, có quy trình khẩn cấp để loại key khỏi trust và từ chối token tương ứng.

Không cho mỗi request kid không biết kích hoạt một lần fetch JWKS không giới hạn; attacker có thể gây DoS cho issuer hoặc gateway. Dùng single-flight, cooldown và giới hạn refresh.

### 4.3. Claim và policy

| Claim | Vai trò | Lưu ý tại gateway |
| --- | --- | --- |
| iss | Issuer | Exact allowlist |
| sub | Subject | Ánh xạ principal, không tự suy role từ chuỗi |
| aud | Resource được phép nhận | Kiểm tra audience API |
| exp / nbf | Thời hạn | Kiểm tra bằng server clock |
| scope | Quyền OAuth | Parse theo profile, không substring match |
| client_id / azp | Client | Ràng buộc với registration khi áp dụng |
| tenant | Tenant/realm | Kiểm tra tenant được API hỗ trợ |
| jti | Token identifier | Dùng audit/denylist khi có state; không tự chống replay |
| cnf | Confirmation key | Kiểm tra proof-of-possession tương ứng |

Không chấp nhận tenant từ query/header để ghi đè tenant đã xác minh trong token hoặc identity mapping. Nếu user có quyền trên nhiều tenant, phải có policy chọn tenant rõ và backend vẫn kiểm tra resource thuộc tenant đó.

## 5. Opaque token và introspection

Opaque token không chứa claims có thể tự xác minh. Gateway gửi token tới introspection endpoint đã cấu hình và nhận kết quả như active, scope, client_id, sub, aud hoặc expiry tùy profile.

Gateway cần:

- Xác thực chính gateway với introspection endpoint.
- Chỉ gọi endpoint tin cậy qua TLS.
- Kiểm tra active=true.
- Kiểm tra audience, scope, client, subject và tenant theo policy.
- Đặt timeout và giới hạn concurrency.
- Không gửi token tới endpoint do client chọn.
- Cache kết quả theo token fingerprint trong thời gian phù hợp với expiry/revocation policy.

### 5.1. Cache introspection và revocation

Cache lâu làm giảm tải authorization server nhưng có thể tiếp tục chấp nhận token đã bị revoke. Cache ngắn giúp revocation nhanh hơn nhưng tăng latency và phụ thuộc hệ thống trung tâm. Chọn TTL theo rủi ro:

- Token có quyền cao hoặc thao tác nhạy cảm: cache rất ngắn hoặc introspect thường xuyên.
- API đọc ít rủi ro: có thể cache lâu hơn trong giới hạn token expiry và policy.
- Khi có revoke event, invalidate cache liên quan nếu kiến trúc hỗ trợ.
- Khi introspection unavailable, không mặc định coi token là active.

Không cache chỉ theo raw token ở loggable key. Dùng hash/fingerprint an toàn, tránh để token xuất hiện trong cache diagnostics.

## 6. Xác thực bằng mTLS tại gateway

mTLS yêu cầu cả client và server trình bày certificate trong TLS handshake. Gateway có thể dùng client certificate để xác minh partner hoặc workload.

Gateway cần kiểm tra:

- Certificate chain tới CA/trust bundle được cấu hình.
- Thời hạn notBefore/notAfter.
- Key usage và extended key usage phù hợp cho client authentication.
- SAN/URI/DNS identity được ánh xạ tới partner hoặc workload principal.
- Certificate serial/fingerprint không bị revoke hoặc denylist.
- Trust domain/CA không quá rộng.

Chỉ kiểm tra certificate chain là chưa đủ. Một certificate hợp lệ của workload A không có nghĩa nó được phép gọi mọi API hoặc giả danh workload B.

### 6.1. TLS termination và client identity

Gateway thường kết thúc TLS từ client rồi mở TLS khác tới upstream. Khi đó:

- Gateway xác minh client certificate ở chặng ngoài.
- Gateway ánh xạ certificate identity thành principal đã xác minh.
- Gateway mở mTLS tới upstream bằng identity của gateway.
- Gateway truyền client principal qua một metadata channel đã được bảo vệ và có nguồn gốc xác thực.
- Backend chỉ chấp nhận metadata đó từ gateway identity được phép.

Không chuyển tiếp raw header X-Client-Cert rồi để backend tin nó nếu client có thể tự gửi cùng header. Nếu cần chuyển certificate identity, dùng header nội bộ được gateway ghi đè, ký assertion hoặc một giao thức identity propagation đã định nghĩa.

## 7. API key, OAuth và mTLS: chọn theo use case

| Use case | Cơ chế thường phù hợp | Ghi chú |
| --- | --- | --- |
| Public API cho ứng dụng người dùng | OAuth/OIDC access token | User authentication thực hiện tại IdP; gateway xác minh access token |
| Partner server-to-server | OAuth client credentials, mTLS hoặc cả hai | Client identity, audience và scope riêng |
| Workload nội bộ trong cluster | Workload identity, mTLS/SPIFFE hoặc token exchange | Tránh static secret dùng chung |
| API đơn giản có quota theo project | API key kết hợp policy bổ sung | Không coi API key là danh tính user |
| API tài chính/đặc quyền | OAuth token có scope hẹp, mTLS/DPoP, step-up phù hợp | Defense in depth và audit |
| Webhook inbound | Signature + timestamp/event ID hoặc mTLS | Chống replay và xử lý idempotency |

Có thể kết hợp cơ chế. Ví dụ, gateway yêu cầu access token và mTLS client certificate: token cho biết subject/scope/audience; certificate chứng minh client đang nắm private key đã bind. Khi kết hợp, phải xác minh binding giữa token và certificate, không chỉ yêu cầu hai credential độc lập.

## 8. Header identity propagation tới upstream

Sau khi xác minh caller, gateway có thể cần truyền identity tới backend. Đây là khu vực dễ mắc lỗi vì header HTTP do client kiểm soát nếu không được làm sạch.

### 8.1. Nguyên tắc

1. Xóa hoặc ghi đè mọi header identity do client có thể tự gửi, ví dụ X-Authenticated-User, X-User-Id, X-Roles, X-Tenant-Id, X-Client-Cert.
2. Chỉ tạo metadata mới từ principal đã xác minh và policy mapping phía gateway.
3. Bảo vệ gateway-to-upstream bằng mTLS hoặc private network kết hợp workload identity.
4. Backend chỉ tin header identity khi kết nối được xác thực là từ gateway đúng.
5. Không cho phép upstream truy cập trực tiếp từ client không tin cậy.
6. Giới hạn nội dung header, encoding và số lượng role/scope để tránh header injection hoặc request smuggling.
7. Không truyền raw access token tới mọi upstream nếu không cần.

Ví dụ metadata nội bộ:

~~~http
X-Authenticated-Subject: user-opaque-482
X-Authenticated-Client: mobile-app-prod
X-Authenticated-Tenant: tenant-17
X-Authenticated-Scopes: invoice.read
X-Authentication-Method: oauth2
X-Authentication-Context: ctx-opaque-91
~~~

Các tên header trên chỉ là ví dụ. Chúng chỉ đáng tin nếu gateway luôn xóa giá trị từ client, ghi giá trị đã xác minh, bảo vệ chặng upstream và backend xác minh caller là gateway. Nếu một service có thể nhận request từ nhiều gateway hoặc service khác, cần xác định allowlist identity rõ ràng.

### 8.2. Truyền identity bằng token nội bộ

Thay vì header rời rạc, gateway có thể:

- Dùng token exchange để đổi external access token thành token nội bộ có audience của upstream.
- Phát signed identity assertion ngắn hạn cho upstream.
- Dùng service mesh/workload identity để xác thực gateway, kết hợp metadata request đã ký hoặc gắn với context.

Token nội bộ cần có issuer, audience, subject, expiry, scope và policy rõ. Không tự ký JWT bằng một secret chung mà mọi service đều biết; nếu service nào cũng có thể ký thì service đó có thể giả danh mọi principal.

### 8.3. Không chuyển tiếp token tùy tiện

External access token có audience dành cho gateway/API A không nên tự động được chuyển tiếp tới service B, C và D. Việc chuyển tiếp làm tăng blast radius nếu một downstream service bị compromise và có thể tạo confused deputy. Dùng token exchange hoặc credential riêng theo audience; chỉ chuyển token gốc khi protocol và trust model cho phép rõ ràng.

## 9. Gateway-to-upstream authentication

Xác minh client ở edge chỉ giải quyết chặng client-to-gateway. Gateway cũng cần xác thực với upstream để backend biết request đến từ gateway/workload được phép.

Các lựa chọn:

- mTLS với certificate riêng cho gateway workload.
- Service mesh identity/SPIFFE SVID.
- OAuth client credentials token có audience của upstream.
- Signed assertion nội bộ với key được quản lý và TTL ngắn.

Backend nên:

- Xác minh gateway principal.
- Chỉ nhận route hoặc client identity được phép.
- Xác minh identity metadata được gateway tạo theo contract.
- Áp dụng authorization theo resource và business state.
- Ghi nhận cả caller gốc và gateway actor để audit.

Nếu gateway gọi upstream bằng một service account chung, backend có thể chỉ thấy gateway mà không phân biệt end-user. Khi cần user-level audit/authorization, truyền subject đã xác minh theo một cơ chế integrity-protected; phân biệt rõ subject là user và actor là gateway/service.

## 10. Multi-tenant và audience isolation

Gateway đa tenant cần ngăn token hoặc API key của tenant A truy cập dữ liệu tenant B.

Kiểm soát:

- Token/API key phải gắn tenant hoặc client registration rõ.
- Kiểm tra audience và issuer trước khi định tuyến.
- Route và upstream mapping không được cho client tự chọn tenant nội bộ.
- Tenant từ token cần được kiểm tra với resource và route.
- Không cache authorization result chỉ theo subject nếu tenant/scope khác nhau.
- Không chia sẻ API key giữa tenant.
- Backend thực hiện object-level tenant authorization.
- Log/audit giữ tenant reference nhất quán để điều tra.

Một request có token hợp lệ của tenant A nhưng URL chứa /tenants/B/... phải bị từ chối nếu principal không có quyền với tenant B. Không dựa vào route prefix do client gửi để quyết định tenant.

## 11. Lỗi xác thực và response contract

Gateway cần trả response nhất quán, không tiết lộ quá nhiều chi tiết về token hoặc account.

| Tình huống | Response thường dùng | Ghi chú |
| --- | --- | --- |
| Không có credential khi endpoint yêu cầu | 401 Unauthorized | Có thể trả WWW-Authenticate phù hợp |
| Token sai chữ ký/format | 401 Unauthorized | Không trả chi tiết key hoặc claim |
| Token hết hạn/issuer không hợp lệ | 401 Unauthorized | Client cần lấy credential mới hoặc xử lý lỗi |
| Token hợp lệ nhưng thiếu scope | 403 Forbidden | Authentication thành công, authorization không đạt |
| API key không hợp lệ/revoked | 401 Unauthorized | Không tiết lộ key có tồn tại hay không |
| Client certificate không được tin cậy | TLS handshake fail hoặc từ chối theo thiết kế | Không hạ xuống password fallback ngoài ý muốn |
| Introspection/issuer timeout | 503 Service Unavailable hoặc lỗi policy phù hợp | Không coi lỗi dependency là token hợp lệ |
| Rate limit | 429 Too Many Requests | Có thể kèm Retry-After |
| Upstream không sẵn sàng | 502/503 tùy gateway contract | Không nhầm với lỗi credential |

Không trả stack trace, signing key, raw claims nhạy cảm, introspection response đầy đủ hoặc lý do nội bộ chi tiết. Phân biệt 401 và 403 giúp client hiểu credential chưa được chấp nhận hay caller không có quyền.

### 11.1. CORS không phải authentication

CORS là policy của browser quyết định JavaScript từ origin nào được đọc response. CORS không xác minh danh tính caller và không chặn mọi client ngoài browser. Không dùng CORS allowlist thay cho token validation, mTLS hoặc authorization.

### 11.2. CSRF và cookie-based API

Nếu browser tự gửi session cookie tới gateway, các endpoint thay đổi trạng thái cần CSRF protection phù hợp. Bearer token được JavaScript gắn vào Authorization header có mô hình CSRF khác nhưng vẫn có rủi ro XSS/token theft. Không coi SameSite cookie là kiểm soát duy nhất trong mọi flow.

## 12. Rate limiting, abuse controls và pre-authentication

Gateway có thể áp rate limit trước và sau authentication:

- Trước authentication: giới hạn theo nguồn mạng, kết nối, kích thước request và endpoint để bảo vệ tài nguyên.
- Sau authentication: giới hạn theo client, subject, tenant, scope, route hoặc operation.
- Với endpoint cấp token, recovery hoặc introspection: dùng policy riêng để chống enumeration, brute force và DoS.

Không chỉ rate limit theo IP vì NAT, proxy và mobile carrier có thể gom nhiều người dùng hợp lệ. Cũng không chỉ rate limit theo subject vì attacker có thể thử nhiều account. Kết hợp nhiều chiều và baseline.

Rate limit không thay thế authentication. Một request dưới ngưỡng rate limit vẫn phải có credential hợp lệ nếu endpoint yêu cầu.

## 13. Cache, availability và fail-closed behavior

Gateway có thể cache JWKS, introspection result, API key metadata và policy để giảm latency. Cache cần được thiết kế theo rủi ro:

- JWKS cache chỉ từ issuer tin cậy, có refresh và key rotation overlap.
- Introspection cache không vượt expiry token và phải phù hợp revocation SLA.
- API key metadata cache có cơ chế invalidate khi key bị revoke.
- Authorization cache phải chứa tenant, audience, scope và resource context cần thiết.
- Cache key không chứa raw token hoặc secret dễ lộ trong diagnostics.
- Có single-flight và backoff để tránh thundering herd.

Nếu identity provider/introspection unavailable:

- Không tự động chấp nhận token chưa từng xác minh hoặc token không rõ trạng thái.
- Có thể dùng JWT đã verify và còn hiệu lực nếu policy cho phép xác minh offline.
- Không dùng opaque token stale vượt TTL cache đã định nghĩa cho endpoint nhạy cảm.
- Trả lỗi tạm thời nếu không thể đưa ra quyết định tin cậy.
- Ghi metrics và alert dependency failure.

Fail closed không có nghĩa mọi outage đều phải chặn mọi endpoint. Có thể định nghĩa public health endpoint hoặc tài nguyên ít rủi ro riêng, nhưng không được để degraded mode mở quyền ngoài policy.

## 14. Java/Spring: kiểm tra token ở gateway

Ví dụ dưới đây minh họa ý tưởng với Spring Cloud Gateway và Spring Security Resource Server. Tên cấu hình, phiên bản dependency và cách triển khai cần khớp ứng dụng thực tế; ưu tiên thư viện chuẩn đã được duy trì thay vì tự viết JWT parser.

### 14.1. Cấu hình resource server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.org/realms/prod
~~~

Issuer configuration giúp framework discovery metadata/JWKS theo issuer đã cấu hình. Vẫn cần thêm audience validator, scope mapping và policy phù hợp với API.

### 14.2. Audience validator minh họa

~~~java
OAuth2TokenValidator<Jwt> audienceValidator(String expectedAudience) {
    return jwt -> {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Token audience is not accepted by this API",
            null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };
}
~~~

Kết hợp validator này với issuer/time validators của framework, algorithm allowlist, scope mapping và sender-binding validator nếu dùng DPoP/mTLS. Không thay toàn bộ validation mặc định bằng một validator chỉ kiểm tra audience.

### 14.3. Gateway filter và identity propagation

Pseudocode filter:

~~~java
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpRequest original = exchange.getRequest();

    // Loại bỏ header identity do external client tự gửi.
    ServerHttpRequest sanitized = original.mutate()
        .headers(headers -> {
            headers.remove("X-Authenticated-Subject");
            headers.remove("X-Authenticated-Client");
            headers.remove("X-Authenticated-Tenant");
            headers.remove("X-Authenticated-Scopes");
        })
        .build();

    return authenticationService.authenticate(sanitized)
        .flatMap(principal -> {
            ServerHttpRequest trustedRequest = sanitized.mutate()
                .headers(headers -> {
                    headers.set("X-Authenticated-Subject", principal.subjectRef());
                    headers.set("X-Authenticated-Client", principal.clientId());
                    headers.set("X-Authenticated-Tenant", principal.tenantRef());
                    headers.set("X-Authenticated-Scopes",
                        String.join(" ", principal.scopes()));
                })
                .build();

            return chain.filter(
                exchange.mutate().request(trustedRequest).build()
            );
        });
}
~~~

Đây là pseudocode để minh họa thứ tự xử lý. Production cần:

- Chạy authentication trong security filter chain chuẩn và xử lý 401/403 đúng contract.
- Chỉ tạo principal sau khi credential đã được xác minh đầy đủ.
- Dùng mTLS/workload identity trên gateway-to-upstream; nếu backend có thể bị gọi trực tiếp thì header không đáng tin.
- Hạn chế scope/claim được truyền và tránh header quá dài.
- Không ghi raw token vào log.
- Không để filter tùy ý chuyển tiếp header từ client có tên trùng metadata nội bộ.
- Backend vẫn kiểm tra resource authorization và tenant ownership.

### 14.4. Không tự triển khai JWT verification thủ công

Một JWT parser tự viết dễ bỏ sót algorithm confusion, key rotation, issuer, audience, expiry, token type và canonicalization. Dùng Spring Security Resource Server hoặc thư viện JOSE/OAuth đã được duy trì; cấu hình rõ issuer, audience, allowed algorithms và clock skew. Unit test cần xác minh cả token hợp lệ lẫn các trường hợp sai.

## 15. Audit và monitoring tại gateway

Gateway là vị trí phù hợp để ghi nhận kết quả authentication và policy, nhưng log không được chứa credential.

### Trường audit

| Trường | Mục đích |
| --- | --- |
| Request/correlation ID | Liên kết edge, gateway và upstream |
| Timestamp | Điều tra theo thời gian |
| Client/subject reference | Principal đã xác minh, pseudonymize khi cần |
| Tenant reference | Phân tích tenant isolation |
| Authentication method | API key, OAuth, JWT, mTLS, DPoP |
| Issuer/audience/key ID | Xác định trust configuration |
| Route/resource/action | Biết API nào được gọi |
| Outcome/reason code | Success, invalid token, expired, scope denied |
| Upstream identity | Gateway principal hoặc service mesh identity |
| Policy version | Tái dựng quyết định đã áp dụng |

Không ghi Authorization header, API key, raw JWT, opaque token, private key, client secret, cookie hoặc DPoP proof đầy đủ. Có thể ghi token fingerprint/jti đã được xử lý an toàn nếu cần correlation, nhưng không biến fingerprint thành bearer secret.

### Metrics và alert

- Authentication success/failure theo route, client, tenant và method.
- Token signature/issuer/audience/expiry failure.
- API key invalid/revoked và rotation event.
- mTLS handshake failure, certificate expiry và SAN mismatch.
- Introspection latency/failure và cache hit/miss.
- JWKS refresh, unknown kid và signing-key rollover.
- 401/403 spike theo client hoặc tenant.
- Header spoof attempt và direct-to-upstream access.
- Sender-binding/DPoP replay failure.
- Gateway-to-upstream mTLS failure và identity mapping error.

Không tạo metric label có raw user ID, email, token hoặc request ID không giới hạn cardinality. Dùng aggregate label và trace reference có kiểm soát.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Chỉ kiểm tra có header Authorization | Token giả vẫn được chuyển tiếp | Verify credential theo protocol |
| Decode JWT nhưng không verify chữ ký | Attacker tự tạo claims | Dùng resource server validator chuẩn |
| Không kiểm tra audience | Token của API khác được dùng tại gateway | Exact audience validation |
| Chấp nhận ID token làm access token | Token sai mục đích được dùng để gọi API | Kiểm tra token type/profile và audience |
| Tin X-User/X-Role từ client | User/role spoofing | Strip client headers, tạo metadata sau authentication |
| Backend mở public ingress | Bypass gateway | Network isolation và mTLS gateway-to-upstream |
| Gateway-to-upstream không xác thực | Caller nội bộ giả gateway | mTLS/workload identity |
| Chuyển tiếp external bearer token tới mọi service | Tăng blast radius, confused deputy | Token exchange hoặc token audience riêng |
| Cache introspection quá lâu | Token revoked vẫn được chấp nhận | TTL theo revocation SLA và invalidate |
| JWKS fetch không giới hạn | DoS khi kid lạ | Trusted URL, single-flight, cooldown |
| Chỉ dùng API key cho user authentication | Không có user identity/assurance rõ | OAuth/OIDC hoặc cơ chế user auth |
| API key dùng chung nhiều tenant | Khó revoke và audit, cross-tenant impact | Key riêng theo client/tenant/environment |
| Tin IP nội bộ là identity | Lateral movement hoặc bypass | Workload identity và mTLS |
| CORS được xem là authentication | Non-browser client bỏ qua được | Credential validation độc lập |
| Gateway làm mọi authorization | Bỏ sót object-level/business policy | Backend kiểm tra resource và tenant |
| Log raw token để debug | Rò rỉ bearer credential | Redaction và safe correlation |

## 17. Ma trận kiểm thử gateway authentication

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Request không có credential tới route bảo vệ | 401 |
| JWT hợp lệ, issuer/audience đúng và scope đủ | Cho phép tới bước authorization/backend |
| JWT chữ ký sai | 401 |
| JWT dùng thuật toán ngoài allowlist | 401 |
| JWT có issuer không tin cậy | 401 |
| JWT có audience của API khác | 401 |
| ID token được gửi thay access token | Từ chối theo token profile |
| JWT hết hạn hoặc chưa tới nbf | 401 |
| Token hợp lệ nhưng thiếu scope | 403 |
| Opaque token inactive | 401 |
| Introspection endpoint timeout | Không coi token là active; trả lỗi theo availability policy |
| Token bị revoke và cache đã invalidate/hết TTL | Từ chối |
| API key hợp lệ của tenant A gọi resource tenant B | Backend/gateway policy từ chối |
| API key đã revoke | 401 |
| Client gửi X-Authenticated-Subject giả | Gateway strip và không chuyển giá trị giả |
| Client gửi X-Authenticated-Tenant giả | Gateway strip; tenant lấy từ identity/policy tin cậy |
| Client certificate chain không tin cậy | TLS/authentication fail |
| Certificate SAN không map tới client được phép | Từ chối |
| Certificate hết hạn hoặc bị revoke | Từ chối theo PKI policy |
| DPoP proof sai method/URI hoặc replay | Từ chối |
| JWKS có kid mới hợp lệ | Refresh có giới hạn và verify thành công |
| Token có kid ngẫu nhiên liên tục | Không tạo fetch storm |
| Gateway gửi request tới upstream bằng mTLS | Upstream xác minh đúng gateway identity |
| Client gọi trực tiếp upstream | Network/authentication policy chặn |
| Upstream nhận header identity từ nguồn không phải gateway | Không tin hoặc từ chối |
| Backend user có scope nhưng không sở hữu object | Resource authorization từ chối |
| Browser dùng cookie session gọi mutation thiếu CSRF | Từ chối theo CSRF policy |
| Log được kiểm tra | Không có raw API key, JWT, cookie hoặc secret |
| Gateway restart hoặc cache flush | Không tự động mở quyền; refresh trust data an toàn |

### Tình huống thực hành

Một gateway xác minh chữ ký JWT nhưng không kiểm tra audience. Sau đó gateway chuyển các header X-User-Id, X-Role nhận từ client tới upstream. Backend chỉ kiểm tra X-Role=admin và đang có public ingress dự phòng. Attacker gửi JWT hợp lệ của một API khác, thêm header admin giả và gọi trực tiếp backend qua ingress dự phòng.

**Yêu cầu:** xác định mọi ranh giới bị phá vỡ và đề xuất sửa.

**Hướng phân tích:**

1. Gateway cần kiểm tra issuer, audience chính xác, expiry, token type, scope, tenant và chữ ký theo policy; token của API khác phải bị từ chối.
2. Gateway strip mọi identity header từ client trước authentication, rồi chỉ tạo metadata từ principal đã xác minh.
3. Backend không được coi X-Role đơn lẻ là bằng chứng; cần xác thực gateway qua mTLS/workload identity và kiểm tra nguồn metadata.
4. Đóng public ingress dự phòng hoặc bảo vệ nó bằng cùng trust policy; không để đường bypass.
5. Backend kiểm tra resource authorization, tenant ownership và business state thay vì chỉ dựa vào role chung.
6. Chỉ truyền external token tới upstream khi audience và delegation policy cho phép; cân nhắc token exchange.
7. Bổ sung test spoofed headers, wrong audience, direct upstream access và object-level authorization.
8. Ghi audit caller gốc, gateway actor, route, audience và kết quả policy mà không log raw token.

## 18. Câu hỏi tự kiểm tra

1. **Gateway authentication chứng minh điều gì?** Nó xác minh caller/client/workload dựa trên credential và trust configuration; không tự chứng minh caller được phép với mọi resource.
2. **API key có phải user authentication không?** Thông thường không; nó thường định danh ứng dụng hoặc project và là bearer secret.
3. **Vì sao phải kiểm tra audience?** Để token được cấp cho resource này không bị dùng ở API khác.
4. **Decode JWT có đủ không?** Không. Phải xác minh chữ ký, issuer, audience, expiry, token type và policy claims.
5. **Gateway có thể tin X-User-Id do client gửi không?** Không. Phải strip header đó và tạo lại từ principal đã xác minh.
6. **Vì sao cần mTLS gateway-to-upstream?** Để backend xác minh caller thực sự là gateway/workload được phép và giảm khả năng bypass bằng header giả.
7. **Gateway có thay backend authorization không?** Không. Backend vẫn kiểm tra quyền trên object, tenant và business state.
8. **Introspection cache quá lâu gây rủi ro gì?** Token đã revoke có thể tiếp tục được chấp nhận cho đến khi cache hết hạn.
9. **Có nên chuyển tiếp access token của client tới mọi upstream?** Không. Dùng audience riêng hoặc token exchange khi cần delegation.

**Ghi nhớ:** Gateway authentication là một phần của chuỗi trust từ client tới API. Xác minh credential theo đúng protocol, kiểm tra issuer/audience/expiry/scope và sender binding khi có; strip header identity do client gửi; bảo vệ gateway-to-upstream bằng mTLS/workload identity; đóng đường bypass; và để backend tiếp tục kiểm tra quyền trên tài nguyên. Gateway xác minh caller, còn toàn hệ thống phải bảo vệ đúng hành động và đúng dữ liệu.
