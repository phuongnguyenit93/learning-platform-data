# API authentication boundary

## 1. Ranh giới xác thực trong API là gì?

**API authentication boundary** là ranh giới tin cậy tại đó một API nhận request từ client hoặc service khác, xác minh danh tính của caller và quyết định bằng chứng nào đủ tin cậy để tiếp tục xử lý. Caller có thể là ứng dụng web, mobile app, backend service, automation job, partner integration hoặc một người dùng thông qua ứng dụng đại diện cho họ.

Khi request đi qua mạng, API không thể mặc định tin những gì client tự khai. Một request có thể mang username, user ID, role, tenant ID, API key, cookie, access token, certificate hoặc chữ ký. API phải phân biệt dữ liệu nhận diện do caller cung cấp với credential đã được xác minh bởi một issuer hoặc trust anchor đáng tin cậy.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, ranh giới xác thực API kết nối credential, token, certificate, session, service identity, authorization và replay protection. Một API an toàn cần biết ai đang gọi, họ đang đại diện cho ai, token hoặc credential được cấp cho audience nào, bằng chứng có còn hiệu lực không và quyền nào được phép thực hiện trên resource cụ thể.

Sau bài học, người học có thể:

- Xác định trust boundary giữa client, gateway, API và backend service.
- Phân biệt user identity, client identity, service identity và delegated identity.
- Phân biệt authentication với authorization.
- Chọn phương thức phù hợp: session cookie, bearer token, API key, mTLS hoặc request signature.
- Xác minh access token theo issuer, audience, thời hạn, chữ ký và profile.
- Thiết kế ranh giới tin cậy giữa API gateway và backend.
- Tránh tin header nhận diện do client tự gửi.
- Áp dụng scope, object-level authorization, tenant isolation và least privilege.
- Bảo vệ request khỏi token theft, replay, CSRF và confused deputy.
- Kiểm thử các trường hợp token sai, quyền sai, credential bị lộ và trust propagation lỗi.

## 2. API xác thực ai?

Trước khi chọn credential, cần xác định chủ thể mà API cần xác minh. Một request có thể có nhiều lớp danh tính cùng lúc.

| Chủ thể | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **End user** | Người đang sử dụng sản phẩm | Khách hàng mở trang đơn hàng |
| **Client application** | Ứng dụng gửi request | Mobile app hoặc web frontend |
| **Service principal** | Backend/workload gọi API | order-service gọi inventory API |
| **Delegated actor** | Service hành động thay mặt user | Backend gọi API khác với quyền được ủy quyền |
| **Device/workload** | Thiết bị hoặc môi trường chạy code | Managed laptop, Kubernetes workload |
| **Tenant/organization** | Phạm vi tổ chức mà caller thuộc về | Công ty A trong SaaS đa tenant |

Không phải API nào cũng cần xác minh tất cả các chủ thể. API public có thể không yêu cầu authentication; API nội bộ có thể xác minh workload; API thao tác dữ liệu cá nhân thường cần user context cùng client/service context. Điều quan trọng là xác định đúng principal cần được tin cho từng loại hành động.

### 2.1. User identity và client identity khác nhau

Mobile app có thể có client ID được đăng ký với authorization server. Client ID nhận diện ứng dụng trong giao thức, nhưng không chứng minh request cụ thể đến từ người dùng nào hoặc ứng dụng đang chạy trên thiết bị đáng tin nào.

Người dùng đăng nhập có thể nhận access token đại diện cho user và client. API cần hiểu token đó được phát hành cho ai, client nào, audience nào và scope nào. Không lấy client ID rồi coi đó là user identity.

### 2.2. Service identity và delegated identity

Khi order-service gọi inventory API bằng Client Credentials, token đại diện cho order-service. Nó không tự chứng minh người dùng cuối đã yêu cầu hành động đó.

Nếu service gọi API thay mặt user, hệ thống cần giữ rõ:
- Subject là người dùng được ủy quyền.
- Actor là service thực hiện request.
- Client/workload identity là thành phần gửi request.
- Audience và scope giới hạn API được gọi.
- Delegation chain hoặc token exchange được xác minh theo giao thức.

Không tự thêm user ID vào header hoặc claim do service tự tạo rồi coi đó là bằng chứng user đã xác thực.

## 3. Trust boundary của một request API

Một request có thể đi qua browser/mobile client, CDN/WAF, API gateway, authentication service, backend API, message broker và database. Mỗi lần chuyển qua một thành phần là một ranh giới cần xác định dữ liệu nào được tin và ai chịu trách nhiệm xác minh.

~~~mermaid
flowchart LR
    A[Browser / Mobile / Partner] -->|TLS + credential/token| B[Edge / WAF]
    B --> C[API Gateway]
    C -->|Verified identity context| D[Backend API]
    D --> E[Authorization policy]
    E --> F[Resource / Database]
    G[Identity Provider] -->|Signed token / keys| C
    G -->|JWKS / metadata| C
    H[Workload identity] -->|Service token or mTLS| C
~~~

Một cách phân chia trách nhiệm:

- **Client:** giữ credential và gửi bằng chứng theo giao thức; không tự quyết định quyền.
- **Edge/WAF:** lọc traffic, giới hạn request và chống một số kiểu automation; không mặc nhiên xác minh danh tính ứng dụng.
- **API gateway:** xác minh credential/token theo cấu hình, áp dụng policy ở mức route và truyền context đã xác minh.
- **Backend API:** kiểm tra resource, action, tenant và business authorization.
- **Identity Provider/Authorization Server:** xác thực user/client và phát token theo policy.
- **Resource server:** quyết định có chấp nhận token và cho phép request hay không.
- **Data layer:** thực thi ràng buộc dữ liệu, tenant isolation và quyền ở mức cần thiết.

Không mặc định request đã an toàn chỉ vì nó đến từ mạng nội bộ hoặc gateway. Trust phải dựa trên kênh, xác thực thành phần, integrity của context và policy cụ thể.

### 3.1. External boundary và internal boundary

External boundary nằm giữa caller không được kiểm soát hoàn toàn và hệ thống API. Internal boundary xuất hiện khi gateway chuyển request tới backend, hoặc một service gọi service khác.

Một gateway có thể xác minh access token rồi chuyển user context tới backend. Backend chỉ nên tin context này nếu:
- Kết nối gateway-backend được xác thực, ví dụ mTLS hoặc network/service identity.
- Gateway loại bỏ header identity do caller bên ngoài tự gửi.
- Context được truyền qua một cơ chế integrity-protected hoặc qua kênh nội bộ có trust rõ.
- Backend chỉ nhận request từ gateway/service được phép.
- Có contract về issuer, subject, audience, tenant và authentication context.

Nếu backend có thể bị gọi trực tiếp từ internet hoặc một workload không tin cậy, backend cần tự xác minh token hoặc context tương đương. Không để bypass gateway làm mất toàn bộ authentication.

### 3.2. Header identity không tự đáng tin

Các header như X-User-Id, X-Role, X-Tenant-Id hoặc X-Authenticated-User có thể hữu ích khi gateway đã xác minh và ghi đè chúng. Nhưng nếu API nhận trực tiếp header do client gửi, attacker có thể giả mạo danh tính hoặc nâng quyền.

Gateway cần xóa header nhạy cảm từ request bên ngoài rồi tạo lại context từ nguồn đã xác minh. Backend cần xác thực gateway và kiểm tra integrity của context theo kiến trúc. Không dùng một header plain text như bằng chứng duy nhất cho quyền admin.

## 4. Authentication khác authorization

Authentication xác minh caller là principal nào. Authorization quyết định principal đó được làm gì trên resource cụ thể. Hai bước liên quan nhưng không thay thế nhau.

| Câu hỏi | Authentication | Authorization |
| --- | --- | --- |
| Ai đang gọi? | Xác minh credential/token/certificate | Dùng principal đã xác minh |
| Bằng chứng nào? | Password, passkey, token, mTLS, signature | Role, scope, policy, relationship, attributes |
| Khi nào chạy? | Trước khi tin identity context | Sau khi identity context được xác minh |
| Kết quả điển hình | Principal/session được xác lập | Allow, deny hoặc step-up |
| Lỗi thường gặp | Chấp nhận token sai issuer hoặc hết hạn | User hợp lệ truy cập object không thuộc quyền |

Một access token có chữ ký hợp lệ không có nghĩa mọi API action đều được phép. API vẫn phải kiểm tra scope, role, tenant, ownership, trạng thái resource và business rule.

### 4.1. 401 và 403

Theo semantics HTTP thông dụng:
- **401 Unauthorized** biểu thị request thiếu credential hợp lệ hoặc authentication không thành công; response có thể kèm challenge phù hợp.
- **403 Forbidden** biểu thị server hiểu request nhưng từ chối thực hiện do policy/quyền.

Ứng dụng có thể chọn response an toàn để tránh tiết lộ resource existence. Ví dụ, API có thể trả 404 cho object không được phép nhìn thấy theo policy. Dù response bên ngoài được chọn thế nào, nội bộ vẫn cần reason code để audit.

Không dùng 401/403 như một cơ chế thay thế rate limiting hoặc error handling. Response body không nên tiết lộ token validity chi tiết, user existence hay cấu hình nội bộ cho caller chưa được tin cậy.

## 5. Các phương thức xác thực API

Phương thức xác thực cần phù hợp với loại caller, threat model, khả năng rotation và mức độ tin cậy.

| Phương thức | Bằng chứng | Điểm cần lưu ý |
| --- | --- | --- |
| **Session cookie** | Cookie tham chiếu session server-side | Cần Secure, HttpOnly, SameSite và CSRF defense |
| **Bearer access token** | Người giữ token có thể sử dụng token | Bảo vệ như secret; TLS, audience, scope, expiry |
| **Opaque token** | Token được introspect hoặc tra trạng thái tại AS | Cần availability và latency của introspection |
| **JWT access token** | Token có chữ ký/MAC và claims | Phải validate profile đầy đủ, không chỉ decode |
| **API key** | Giá trị bí mật nhận diện client/key | Thường bearer-like; scope, quota, expiry và rotation |
| **HTTP Basic** | Username/password trong Authorization header | Chỉ qua TLS; tránh dùng cho hệ thống mới nếu có phương án tốt hơn |
| **mTLS** | Client chứng minh giữ private key của certificate | PKI, SAN mapping, rotation và authorization |
| **Request signing** | MAC/chữ ký ràng buộc request | Canonicalization, nonce, timestamp và key management |

Không có một phương thức phù hợp cho mọi API. API browser có thể dùng cookie session; public/mobile API thường dùng OAuth access token; service-to-service có thể dùng workload identity, mTLS hoặc private_key_jwt; webhook có thể dùng request signature và event ID.

### 5.1. API key không phải authorization hoàn chỉnh

API key thường giúp nhận diện một integration hoặc client. Nếu key bị lộ, attacker có thể sử dụng trong phạm vi quyền gắn với key. Một API key không tự chứng minh danh tính người dùng cuối, không nhất thiết chống replay và không nên tự động có quyền truy cập mọi resource.

Thiết kế API key cần:
- Key riêng theo integration hoặc workload.
- Scope và resource giới hạn.
- Quota/rate limit.
- Expiry/rotation/revocation.
- Hiển thị key một lần khi tạo nếu phù hợp.
- Lưu hash hoặc representation bảo vệ khi có thể.
- Không đưa key vào URL query hoặc frontend code công khai.
- Audit lần tạo, xem lại, rotate và sử dụng.

API key nằm trong JavaScript bundle hoặc mobile binary có thể bị trích xuất. Không dùng secret client-side như thể nó là bí mật lâu dài.

### 5.2. Bearer token

Bearer token cho phép bất kỳ ai sở hữu token sử dụng token trong phạm vi được cấp. Vì vậy token cần được bảo vệ như credential:
- Chỉ truyền qua TLS.
- Không ghi vào URL, log, analytics hoặc error trace.
- Không lưu ở nơi JavaScript không cần thiết có thể đọc nếu có phương án session cookie an toàn hơn.
- Dùng audience và scope tối thiểu.
- Đặt expiry phù hợp.
- Có chiến lược revoke/rotation và xử lý compromise.
- Không chia sẻ token giữa môi trường hoặc client không liên quan.

Nếu token bị lộ, người tấn công có thể sử dụng nó cho tới khi token hết hạn hoặc resource server nhận biết trạng thái thu hồi. Với rủi ro cao, cân nhắc sender-constrained token như DPoP hoặc certificate-bound token theo khả năng hệ thống.

## 6. OAuth 2.0 và access token cho API

OAuth 2.0 là framework ủy quyền. Access token được authorization server cấp để client truy cập resource server theo quyền đã cấp. OpenID Connect bổ sung lớp xác thực người dùng và ID token cho client; ID token không phải access token dành cho API.

Các luồng phổ biến:
- Authorization Code với PKCE cho public client và ứng dụng có user interaction.
- Client Credentials cho confidential client/service truy cập dưới danh tính client.
- Token Exchange hoặc flow delegated phù hợp khi cần chuyển tiếp quyền giữa service.
- Device Authorization Grant cho thiết bị có trải nghiệm nhập liệu hạn chế theo use case được hỗ trợ.

Không dùng Resource Owner Password Credentials Grant cho ứng dụng mới; flow này buộc client thu thập password người dùng và làm suy yếu ranh giới giữa client và authorization server.

### 6.1. Access token khác ID token

| Token | Mục đích | Consumer |
| --- | --- | --- |
| **ID token** | Thông tin xác thực người dùng cho OIDC client | OIDC client đã đăng ký |
| **Access token** | Quyền truy cập resource/API | Resource server |
| **Refresh token** | Lấy access token mới theo policy | Authorization server |
| **Client assertion** | Xác thực confidential client tại token endpoint | Authorization server |

Không gửi ID token tới API rồi coi nó là access token chỉ vì cả hai đều là JWT. Resource server phải chấp nhận đúng token type/profile và audience được thiết kế cho nó.

### 6.2. Scope và audience

Scope mô tả quyền hoặc nhóm thao tác mà client được cấp theo authorization server. Audience xác định resource server dự kiến nhận token. Hai khái niệm có liên quan nhưng không đồng nghĩa.

Ví dụ:
- Audience: inventory API.
- Scope: stock:read và stock:reserve.
- Client: order-service.
- Subject: service principal của order-service hoặc user được ủy quyền theo flow.

Inventory API phải xác minh audience là chính nó và scope đủ cho action. Token dành cho reporting API không được chấp nhận tại inventory API dù chữ ký hợp lệ.

### 6.3. Token opaque và JWT

Opaque token không chứa claims có thể đọc trực tiếp; resource server thường gọi introspection hoặc một hệ thống trạng thái tin cậy. JWT access token có thể được xác minh cục bộ bằng khóa issuer, giảm phụ thuộc runtime vào introspection nhưng làm thu hồi tức thời khó hơn nếu không có denylist/event/status check.

Chọn theo yêu cầu về latency, availability, revocation, privacy và vận hành. Không mặc định JWT luôn tốt hơn opaque token.

## 7. Xác minh JWT access token

JWT chỉ là định dạng token. Việc decode payload không chứng minh token hợp lệ. Resource server cần xác minh chữ ký và toàn bộ claim/constraint theo profile token đã thỏa thuận.

Một quy trình kiểm tra thường gồm:

1. Chọn issuer tin cậy từ cấu hình, không từ claim tùy ý.
2. Lấy key từ JWKS URI đã gắn với issuer.
3. Allowlist thuật toán được hỗ trợ; từ chối algorithm confusion.
4. Xác minh chữ ký.
5. Kiểm tra iss chính xác.
6. Kiểm tra aud chứa API hiện tại.
7. Kiểm tra exp và nbf; áp dụng clock skew nhỏ, có kiểm soát.
8. Kiểm tra token type/profile để phân biệt access token với ID token.
9. Kiểm tra scope/authorization claims theo contract.
10. Kiểm tra tenant, client, subject và trạng thái cần thiết.
11. Kiểm tra revocation/session status nếu policy yêu cầu.
12. Chỉ sau đó mới dùng claims đã xác minh cho authorization.

~~~text
claims = verify_signature(token, trusted_issuer_keys)

require(claims.iss == configured_issuer)
require(api_identifier in claims.aud)
require(server_now < claims.exp)
require(claims.nbf is absent or server_now >= claims.nbf)
require(token_profile_is_access_token(claims))
require(required_scope in claims.scope)

principal = resolve_principal(claims.iss, claims.sub)
authorize(principal, resource, action)
~~~

Đây là pseudocode khái niệm. Dùng thư viện JWT/OAuth được duy trì và cấu hình profile cụ thể. Không tự viết parser hoặc xác minh chữ ký bằng code tùy tiện.

### 7.1. JWKS và key rotation

JWKS cung cấp public keys để resource server xác minh token. Resource server nên:
- Lấy JWKS URI từ metadata của issuer đã tin cậy.
- Cache key với thời hạn hợp lý.
- Hỗ trợ key rotation và refresh khi gặp kid mới theo policy.
- Không tải key từ jku/x5u URL tùy ý trong token.
- Không chấp nhận key do caller gửi.
- Giám sát issuer metadata và TLS.
- Có kế hoạch khi JWKS endpoint tạm thời lỗi.

Không coi kid là bí mật hoặc là bằng chứng key đáng tin. kid chỉ giúp chọn key trong tập key đã được tin cậy.

### 7.2. Issuer và audience confusion

Nếu nhiều issuer phát hành token có cùng sub, không được trộn chúng thành một principal. Principal liên kết với issuer theo trust configuration. Audience sai có thể dẫn tới token được phát hành cho API A nhưng dùng tại API B.

Mỗi resource server cần có audience riêng hoặc một quy tắc audience rõ ràng. Không chấp nhận token chỉ vì chữ ký hợp lệ từ một issuer bất kỳ trong hệ thống.

### 7.3. Claims không phải lúc nào cũng là sự thật hiện tại

Role hoặc group claim trong token có thể đã cũ nếu quyền vừa bị thu hồi. Với quyền nhạy cảm, cân nhắc token ngắn hạn, introspection, policy lookup hoặc revocation event. Không dùng claim snapshot cũ để cấp quyền lâu dài mà không có giới hạn.

## 8. mTLS và xác thực service-to-service

mTLS cho phép client và server xác thực certificate trong TLS handshake. Nó phù hợp khi API cần xác định workload hoặc partner integration ở tầng kết nối.

Một certificate client cần được kiểm tra theo PKI policy:
- Chain tới trust anchor đã cấu hình.
- Validity period và trạng thái revoke.
- SAN/identity mapping phù hợp.
- Key Usage và Extended Key Usage cho client authentication.
- Proof-of-possession private key trong handshake.
- Tenant, environment và service identity tương ứng.

mTLS xác minh client ở tầng transport. Nó không tự cấp quyền gọi mọi API. Resource server vẫn phải map certificate identity tới principal và kiểm tra scope/resource/action.

### 8.1. mTLS qua reverse proxy

Nếu TLS kết thúc tại load balancer hoặc gateway, backend cần biết certificate identity đã được xác minh bởi thành phần nào. Không tin header certificate do client bên ngoài gửi.

Gateway phải:
- Xóa header identity/certificate từ caller.
- Xác minh certificate và mapping.
- Truyền context qua kết nối nội bộ được xác thực.
- Giới hạn backend chỉ nhận request từ gateway đáng tin.
- Ghi lại identity nguồn và quyết định xác minh.

Nếu backend có thể bị gọi trực tiếp, phải có cơ chế bảo vệ tương đương tại backend.

### 8.2. mTLS không thay user authentication

Một mobile app có thể dùng certificate để xác thực thiết bị hoặc app instance, trong khi user vẫn cần đăng nhập bằng passkey/MFA. Hai bằng chứng có mục đích khác nhau. Certificate của thiết bị không tự chứng minh người đang cầm thiết bị là đúng user.

## 9. Session cookie và browser API

Browser thường tự gửi cookie theo domain/path và policy. Nếu API dùng cookie session, cần bảo vệ cookie và chống request giả mạo từ site khác.

Cookie session nên cân nhắc:
- Secure để chỉ gửi qua HTTPS.
- HttpOnly để JavaScript không đọc trực tiếp.
- SameSite phù hợp với luồng đăng nhập và cross-site.
- Path/Domain giới hạn cần thiết.
- Session ID ngẫu nhiên, không chứa dữ liệu nhạy cảm.
- Rotation sau login hoặc privilege change.
- Idle và absolute timeout.
- Server-side invalidation khi logout/revoke.

### 9.1. CSRF

Vì browser tự gửi cookie, attacker có thể dụ browser gửi request tới API nếu ứng dụng không có CSRF defense. Dùng CSRF token, Origin/Referer validation hoặc Fetch Metadata theo kiến trúc; cấu hình SameSite phù hợp là lớp bổ sung.

HttpOnly không ngăn XSS thực hiện request trong browser context. Cần output encoding, CSP và bảo vệ ứng dụng khỏi script injection.

### 9.2. CORS không phải authentication

CORS là chính sách browser kiểm soát JavaScript origin nào được đọc response cross-origin. Nó không xác minh caller ở tầng server và không ngăn curl, script hoặc server-to-server client gọi API.

API vẫn phải xác minh credential và authorization cho mọi request. Không coi việc origin nằm trong allowlist CORS là bằng chứng người dùng hoặc ứng dụng hợp lệ.

## 10. API gateway và backend enforcement

Gateway có thể tập trung token validation, route-level scope, rate limit và telemetry. Tuy nhiên, gateway không biết đầy đủ mọi business rule hoặc quyền trên object trong backend.

Phân công hợp lý:
- Gateway: TLS, client authentication, token validation, coarse scope, request size/rate limit và routing.
- Backend: object-level authorization, tenant isolation, ownership, business state và transaction policy.
- Data layer: ràng buộc tenant/resource và quyền truy cập khi cần.
- Identity/authorization service: issuer, token issuance, policy và key lifecycle.

Không chỉ kiểm tra role tại gateway rồi để backend tin mọi resource ID. Attacker có thể đổi object ID trong request để truy cập dữ liệu người khác (BOLA/IDOR).

### 10.1. Context propagation

Nếu gateway truyền user context tới backend:
- Xác thực gateway bằng mTLS hoặc workload identity.
- Xóa các header tương ứng từ external request.
- Tạo context từ token đã xác minh.
- Giới hạn context theo service và audience.
- Bảo vệ integrity của dữ liệu chuyển tiếp.
- Backend kiểm tra tenant, resource và action.
- Giữ correlation ID riêng với identity claims.

Không để backend nhận context từ bất kỳ workload nào trong private network. Network location không phải trust proof.

### 10.2. Gateway không phải điểm kiểm tra duy nhất

Nếu một API có nhiều đường truy cập, ví dụ gateway public, internal load balancer, message consumer và admin endpoint, mọi đường phải có authentication/authorization tương ứng. Tắt auth ở một route nội bộ vì “chỉ gateway gọi” có thể tạo đường bypass khi network rule thay đổi.

## 11. Tenant isolation và object-level authorization

Trong SaaS đa tenant, token có thể chứa tenant context hoặc API xác định tenant từ membership đã xác minh. Không tin tenant ID do client tự gửi mà không kiểm tra caller có membership và quyền trong tenant đó.

Một request đọc invoice cần kiểm tra:
- Principal đã được xác minh.
- Client/issuer phù hợp.
- Tenant thuộc phạm vi principal.
- Invoice thực sự thuộc tenant đó.
- Principal có quyền đọc invoice.
- Trạng thái invoice cho phép action.
- Purpose hoặc workflow phù hợp nếu dữ liệu nhạy cảm.

~~~text
allow =
    authenticated(principal)
    AND client_is_trusted(client)
    AND tenant_membership(principal, tenant)
    AND resource.tenant_id == tenant
    AND permission(principal, "invoice:read")
    AND business_policy_allows(resource)
~~~

Không chỉ kiểm tra token có scope invoice:read rồi trả mọi invoice theo ID. Scope là một phần của policy; object-level authorization vẫn cần thiết.

### 11.1. Least privilege

Cấp scope nhỏ nhất cần cho API. Tách read, write, delete, export và admin. Với service-to-service, mỗi workload có principal riêng. Với user token, tránh scope quá rộng chỉ để frontend không cần xin thêm token.

### 11.2. Delegation và confused deputy

Một backend có quyền cao có thể bị lợi dụng để truy cập tài nguyên thay cho caller không đủ quyền. Đây là confused deputy. API phải giữ rõ actor, subject, client và delegation context; kiểm tra quyền của người dùng cuối nếu hành động được thực hiện thay họ.

Không dùng service token quyền rộng để biến mọi request user thành hành động có quyền của service.

## 12. Request signing, nonce và replay protection

Một số API, webhook hoặc giao thức partner dùng HMAC/chữ ký để bảo vệ request. Chữ ký cần ràng buộc method, target URI, timestamp, nonce và body digest theo profile đã thống nhất.

Timestamp giới hạn freshness window nhưng không ngăn replay trong window. Cần nonce/request ID và replay cache có thao tác consume-once nguyên tử. Với nghiệp vụ có side effect, cần idempotency key riêng.

Các nguyên tắc:
- Dùng TLS kể cả khi request đã được ký.
- Ký đúng canonical representation.
- Xác minh key thuộc đúng client.
- Kiểm tra timestamp và clock skew.
- Consume nonce trước side effect.
- Lưu replay record đủ lâu.
- Xử lý retry idempotent.
- Rotate/revoke key khi compromise.

Không tự phát minh canonicalization không rõ ràng. Dùng chuẩn hoặc profile đã được review, có test vectors cho header, URI, body và encoding.

## 13. Webhook và partner API

Webhook thường là request từ hệ thống bên ngoài tới endpoint của bạn. Receiver cần xác minh nguồn gửi và tính toàn vẹn của event, không chỉ tin IP hoặc JSON body.

Có thể dùng:
- HMAC signature trên raw body và metadata theo giao thức.
- Timestamp ký để giới hạn freshness.
- Event ID để deduplicate.
- TLS và secret riêng theo partner.
- IP/network controls như lớp bổ sung, không phải bằng chứng duy nhất.
- Rate limit, request size limit và schema validation.
- Idempotent processing cho retry.

Webhook signature hợp lệ chỉ chứng minh request được tạo bởi bên giữ secret tương ứng theo thiết kế; nó không chứng minh nội dung nghiệp vụ là đúng hoặc partner có quyền trên mọi resource. Backend vẫn cần kiểm tra event type, tenant, resource và trạng thái.

## 14. Error handling và information disclosure

Authentication endpoint có thể trở thành oracle để attacker dò account, token validity, issuer hoặc trạng thái hệ thống. Response cần đủ thông tin cho client hợp lệ nhưng không tiết lộ dữ liệu nội bộ không cần thiết.

Nguyên tắc:
- Dùng status code và error format nhất quán.
- Không trả stack trace, key ID nhạy cảm hoặc chi tiết verifier.
- Không phân biệt account không tồn tại với password sai nếu điều đó làm lộ account.
- Không trả token hoặc credential trong error body.
- Có correlation ID để support tra cứu nội bộ.
- Ghi reason code chi tiết trong audit an toàn.
- Rate limit login/token/introspection endpoint.
- Tránh timing differences rõ ràng giữa các trường hợp account tồn tại và không tồn tại.

Không che lỗi tới mức client không thể phục hồi. Có thể cung cấp error code tổng quát và hướng dẫn hành động an toàn như đăng nhập lại, refresh token hoặc liên hệ support.

## 15. Logging, monitoring và incident response

API authentication cần telemetry để phát hiện token theft, credential stuffing, client giả mạo và quyền bất thường.

Nên ghi:
- Thời điểm và endpoint.
- Principal/client/service reference đã được bảo vệ.
- Issuer, audience, client ID và scope cần thiết.
- Authentication method/context ở mức phù hợp.
- Kết quả authentication và authorization.
- Reason code và correlation ID.
- Resource/action reference đã giảm nhạy cảm.
- Source/device/network signal theo policy.
- Token ID hoặc keyed reference nếu cần tương quan.

Không log:
- Password, OTP, TOTP seed hoặc recovery code.
- Client secret, private key, HMAC secret.
- Raw access token/refresh token/ID token.
- Session cookie hoặc Authorization header.
- Toàn bộ request body nhạy cảm.
- Certificate private material.

Khi nghi token bị lộ:
1. Xác định issuer, client, subject, audience và token scope.
2. Xác định API/resource đã bị gọi.
3. Revoke token/grant hoặc disable client/credential theo khả năng.
4. Thu hồi session liên quan khi cần.
5. Rotate secret/key/certificate nếu compromise.
6. Kiểm tra log và side effect.
7. Thu hẹp scope/audience và sửa trust configuration.
8. Thông báo owner và người dùng bị ảnh hưởng theo policy.

## 16. Threat model cho API authentication boundary

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Token theft** | Token lộ qua log, browser storage hoặc malware | TLS, secure storage, short lifetime, revoke và sender constraint |
| **Token substitution** | Token của API/client khác được dùng | Issuer, audience, token type và client binding |
| **JWT validation bypass** | Decode-only, alg confusion hoặc key không tin cậy | Library chuẩn, algorithm allowlist, issuer-bound JWKS |
| **Header spoofing** | Caller tự gửi X-User-Id/X-Role | Strip external headers và signed/internal context |
| **BOLA/IDOR** | Thay resource ID để đọc object khác | Object-level authorization tại backend |
| **CSRF** | Browser tự gửi cookie tới API | CSRF token, SameSite, Origin/Fetch Metadata |
| **CORS confusion** | Coi allow-origin là authentication | Server-side credential validation |
| **Replay** | Request/token/signature bị gửi lại | Nonce, replay cache, sender constraint và idempotency |
| **Confused deputy** | Service quyền rộng hành động thay caller | Delegation context và downstream authorization |
| **mTLS identity confusion** | Certificate hợp lệ nhưng mapping sai service | SAN/issuer mapping, trust domain và scope |
| **API key leakage** | Key nằm trong frontend, URL hoặc repository | Secret manager, key rotation và scope |
| **Tenant confusion** | Client đổi tenant ID trong request | Membership và tenant binding phía server |
| **Gateway bypass** | Backend bị gọi trực tiếp bỏ qua gateway | Network/service identity và backend validation |
| **Webhook forgery** | Attacker gửi event giả | Signature, timestamp, event ID và schema validation |
| **Enumeration** | Response tiết lộ account/token state | Error normalization, timing review và rate limit |
| **Credential stuffing** | Credential bị lộ được thử trên API | Backoff, rate limit, MFA và breached password controls |

## 17. Ví dụ: API đọc hóa đơn trong SaaS đa tenant

Một ứng dụng web gọi API để đọc hóa đơn. Người dùng thuộc tenant A, còn API chạy sau gateway và backend invoice-service.

Luồng:
1. Người dùng đăng nhập qua OIDC Authorization Code với PKCE.
2. Client nhận access token dành cho invoice API.
3. Browser gửi request qua TLS.
4. Gateway xác minh token signature/profile, issuer, audience, expiry và scope.
5. Gateway xóa các header identity do caller tự gửi và tạo context từ claims đã xác minh.
6. Backend xác thực kết nối gateway và nhận context tin cậy.
7. Invoice-service resolve principal bằng issuer + subject.
8. Service xác minh principal có membership tenant A.
9. Service tải invoice và kiểm tra invoice thuộc tenant A.
10. Service kiểm tra action invoice:read và business policy.
11. API chỉ trả các trường caller được phép xem.
12. Audit ghi principal, tenant, resource, action và kết quả mà không log token.

~~~mermaid
sequenceDiagram
    participant U as Browser / User
    participant G as API Gateway
    participant ID as Identity Provider
    participant API as Invoice API
    participant DB as Invoice Store
    U->>ID: Đăng nhập OIDC + PKCE
    ID-->>U: Access token cho invoice API
    U->>G: GET /invoices/123 + token
    G->>G: Verify signature, iss, aud, exp, scope
    G->>API: Request + trusted identity context
    API->>API: Resolve principal và tenant membership
    API->>DB: Load invoice 123
    DB-->>API: Invoice + tenant_id
    API->>API: Check object-level authorization
    API-->>U: Chỉ trả fields được phép
~~~

Nếu người dùng thay invoice ID thành một hóa đơn của tenant B, backend phải từ chối dù access token vẫn hợp lệ và có scope invoice:read. Authentication chứng minh principal; authorization kiểm tra resource cụ thể.

## 18. Kiểm thử API authentication boundary

| Test case | Kết quả mong đợi |
| --- | --- |
| Không có credential trên endpoint bảo vệ | 401 hoặc challenge phù hợp |
| Token sai chữ ký | Từ chối |
| Token issuer không được tin | Từ chối |
| Token audience là API khác | Từ chối |
| ID token gửi tới resource API | Từ chối theo token profile |
| Token hết hạn hoặc chưa tới nbf | Từ chối |
| Token thiếu scope | 403 hoặc response policy phù hợp |
| Token hợp lệ nhưng user không có quyền object | Từ chối object-level |
| Caller gửi X-User-Id/X-Role giả | Header bị strip/ignore |
| Backend bị gọi trực tiếp | Không bypass trust boundary |
| Token của tenant A truy cập tenant B | Từ chối |
| API key bị revoke | Request bị từ chối theo trạng thái |
| mTLS certificate không tin cậy | Handshake/authentication thất bại |
| Certificate hợp lệ nhưng principal mapping sai | Từ chối |
| Cookie session thiếu CSRF proof | Request thay đổi trạng thái bị từ chối |
| CORS origin không được phép | Browser không được đọc response; API vẫn kiểm tra auth |
| HMAC timestamp bị sửa | Signature verification thất bại |
| Nonce bị replay | Request lặp bị từ chối |
| Webhook event ID bị gửi lại | Không lặp side effect |
| Token refresh sau revoke | Không được cấp quyền trái policy |
| JWKS rotation | Token mới hợp lệ được xác minh; key cũ xử lý theo policy |
| Error response | Không lộ user existence, token hoặc stack trace |
| Log inspection | Không có secret, cookie hoặc bearer token thô |

## 19. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Caller được xác định rõ? | User, client, service và delegated actor tách biệt |
| Trust boundary được vẽ? | Client, gateway, backend, IdP và data layer có trách nhiệm rõ |
| Authentication tách authorization? | Token hợp lệ không tự cấp quyền trên mọi resource |
| Credential phù hợp loại client? | Cookie, OAuth token, mTLS, key hoặc signature theo threat model |
| Token profile được xác minh? | Issuer, audience, expiry, signature, type và scope |
| ID token có bị dùng nhầm? | Resource server chỉ nhận access token profile |
| Header identity có được bảo vệ? | External headers bị strip; internal context có integrity |
| Gateway bypass được ngăn? | Backend chỉ tin gateway/service đã xác thực |
| Tenant isolation được kiểm tra? | Membership và resource tenant được xác minh |
| Object-level authorization có? | Mỗi resource/action được kiểm tra tại backend |
| Token/key có vòng đời? | Expiry, rotation, revocation và monitoring |
| Cookie có CSRF defense? | Secure, HttpOnly, SameSite và anti-CSRF |
| CORS có bị hiểu nhầm? | CORS không thay authentication |
| Request signing có replay protection? | Timestamp, nonce, canonicalization và cache |
| Delegation có rõ? | Actor/subject và token exchange đúng profile |
| Webhook được xác minh? | Signature, event ID, timestamp và idempotency |
| Logging có an toàn? | Không ghi credential hoặc token thô |
| Có test negative cases? | Wrong issuer/audience, spoofed header, BOLA, replay và bypass |

### Tình huống tự kiểm tra

**Tình huống 1:** Một JWT có chữ ký hợp lệ. API có thể chấp nhận token đó không cần kiểm tra audience không?

**Trả lời:** Không. Token có thể được phát hành cho API khác. Resource server phải xác minh audience của chính nó cùng issuer, thời hạn, token profile và các điều kiện khác.

**Tình huống 2:** Client gửi header X-Role: admin. Gateway đã xác minh access token user thường. Backend có nên tin header này không?

**Trả lời:** Không. Gateway phải xóa header do client gửi và tạo identity context từ claims đã xác minh. Backend chỉ tin context qua trust channel đã thiết lập.

**Tình huống 3:** API gateway xác minh token rồi. Backend có thể bỏ object-level authorization không?

**Trả lời:** Không. Gateway có thể xác minh danh tính và scope coarse-grained, nhưng backend phải kiểm tra quyền trên resource, tenant và action cụ thể.

**Tình huống 4:** API dùng CORS allowlist chỉ cho frontend chính thức. Có thể bỏ authentication vì browser lạ không đọc được response không?

**Trả lời:** Không. CORS là browser policy, không ngăn curl, script hoặc server-to-server caller. API phải xác minh credential ở server.

**Tình huống 5:** mTLS xác thực order-service. Có nghĩa request đó được phép xóa mọi đơn hàng không?

**Trả lời:** Không. mTLS xác thực workload ở tầng kết nối; API vẫn phải kiểm tra scope, resource, action và business policy.

**Tình huống 6:** Access token bị lộ nhưng còn hạn 30 phút. Chỉ xóa session cookie ở browser có đủ không?

**Trả lời:** Không. Bearer token bị lộ có thể được sử dụng độc lập với cookie. Cần revoke token/grant theo khả năng, xử lý session liên quan và kiểm tra API access.

**Tình huống 7:** Một service gọi downstream bằng token Client Credentials nhưng thêm user ID vào header. Downstream có thể coi request là hành động của user đó không?

**Trả lời:** Không. Header tự khai không chứng minh delegation. Cần flow delegated/token exchange phù hợp, giữ actor/subject và xác minh context ở downstream.

## 20. Ghi nhớ

**API authentication boundary xác định bằng chứng nào được API tin để nhận diện caller và nơi trust được chuyển giữa các thành phần.** API phải phân biệt user, client, service và delegated identity; xác minh credential/token/certificate theo đúng issuer, audience, thời hạn và profile; đồng thời giữ authentication tách biệt với authorization.

Gateway có thể kiểm tra token và áp dụng policy ở mức route, nhưng backend vẫn phải kiểm tra tenant, resource, action và business rule. Không tin header do client tự gửi, không coi CORS là authentication, không dùng ID token thay access token và không xem mTLS là quyền truy cập. Bảo vệ token/key, kiểm soát replay, CSRF, confused deputy, logging và vòng đời credential để giữ trust boundary nhất quán từ client tới data layer.
