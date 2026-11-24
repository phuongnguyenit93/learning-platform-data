# Chọn session hay stateless token

## Mục tiêu

Khi thiết kế xác thực cho một ứng dụng hoặc API, đội phát triển phải quyết định trạng thái đăng nhập sẽ được giữ ở đâu. Với **server-side session**, server lưu trạng thái phiên và client giữ một session identifier. Với **stateless access token**, token mang claims đã được ký để resource server có thể xác minh mà không phải tra một session record cho mọi request.

Hai cách tiếp cận có trade-off khác nhau về thu hồi, khả năng mở rộng, độ trễ, vận hành và bề mặt tấn công. Chọn JWT chỉ vì muốn scale, hoặc chọn session chỉ vì muốn an toàn, đều có thể dẫn đến thiết kế không phù hợp.

Sau bài này, bạn có thể:

- Phân biệt session, JWT access token và opaque access token.
- Chọn mô hình dựa trên yêu cầu logout, revoke, scale, độ trễ và kiến trúc client.
- Đánh giá rủi ro CSRF, XSS, token theft, replay và stale authorization.
- Thiết kế mô hình hybrid kết hợp session, access token ngắn hạn và refresh token.
- Xác định trạng thái nào cần lưu phía server dù access token là JWT.
- Viết decision record có tiêu chí, trade-off và kế hoạch kiểm thử rõ ràng.

## 1. Trạng thái xác thực được giữ ở đâu?

Trước hết, cần tách ba khái niệm:

- **Authentication state:** bằng chứng và trạng thái cho biết chủ thể đã đăng nhập, phiên còn hiệu lực và có thể tiếp tục sử dụng hay không.
- **Access credential:** thông tin client gửi trong mỗi request để chứng minh quyền truy cập, ví dụ session cookie hoặc bearer access token.
- **Authorization state:** quyền, vai trò, membership, trạng thái tài khoản và policy quyết định chủ thể được làm gì trên tài nguyên nào.

Session và stateless token chủ yếu khác nhau ở nơi lưu trạng thái đăng nhập và cách xác minh credential.

### Server-side session

Server tạo một session record sau khi xác thực thành công. Browser nhận một session identifier ngẫu nhiên, thường được gửi qua cookie. Mỗi request tiếp theo gửi cookie; server tra session store để biết phiên có còn hiệu lực và chủ thể nào đang đăng nhập.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Application
    participant S as Session Store
    B->>A: Login credentials
    A->>A: Xác thực người dùng
    A->>S: Tạo session record
    S-->>A: Session ID
    A-->>B: Set-Cookie: session ID
    B->>A: Request + session cookie
    A->>S: Lookup session
    S-->>A: Principal + trạng thái
    A->>A: Authorization
    A-->>B: Response
~~~

Cookie chỉ nên chứa một định danh ngẫu nhiên khó đoán, không chứa toàn bộ session object hoặc dữ liệu nhạy cảm. Session store phía server giữ principal, thời điểm tạo, thời điểm hết hạn, trạng thái, thông tin rotation và dữ liệu cần thiết theo policy.

### Stateless access token

Authorization server phát hành token có chữ ký, chứa claims như issuer, subject, audience, scope và thời hạn. Client gửi token đến resource server. Resource server xác minh chữ ký và claims bằng cấu hình tin cậy; không cần tra một session record cho mỗi request nếu kiến trúc không yêu cầu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: Authorization Code + PKCE
    AS-->>C: Access token
    C->>API: Request + Bearer access token
    API->>API: Verify signature, iss, aud, exp, scope
    API-->>C: Response
~~~

JWT thường được dùng cho mô hình này vì claims có thể được đọc và xác minh cục bộ. Chữ ký bảo vệ tính toàn vẹn, không che giấu payload. Không đưa secret hoặc PII không cần thiết vào JWT.

### Opaque token và introspection

Opaque access token là chuỗi không mang claims có thể tự đọc theo định dạng chuẩn hóa. Resource server gọi introspection endpoint của authorization server hoặc một dịch vụ tin cậy để biết token có active không và token thuộc chủ thể, audience, scope nào.

Opaque token có thể cần tra cứu mạng giống session, nhưng mô hình quyền sở hữu và giao thức khác nhau: authorization server quản lý token; resource server xác minh qua introspection thay vì đọc claims JWT cục bộ.

| Mô hình | Credential phía client | Nguồn trạng thái chính | Cách kiểm tra |
| --- | --- | --- | --- |
| Session | Session ID ngẫu nhiên, thường trong cookie | Session store của ứng dụng | Lookup session |
| JWT access token | JWT bearer token | Claims đã ký và policy/config phía resource server | Xác minh chữ ký và claims |
| Opaque access token | Chuỗi opaque bearer token | Authorization server/token store | Introspection hoặc lookup tin cậy |

Không đồng nhất ba khái niệm: **session là mô hình quản lý phiên**, **JWT là định dạng token**, còn **opaque là cách biểu diễn token không tự mô tả claims**. Một ứng dụng có thể dùng JWT trong một session hoặc dùng opaque token có trạng thái phía server.

## 2. Khi nào session là lựa chọn phù hợp?

Session thường phù hợp với ứng dụng web first-party, nơi browser và backend do cùng tổ chức kiểm soát, và ứng dụng cần quản lý phiên tập trung.

Các tình huống session có lợi:

- Logout phải có hiệu lực ngay ở request kế tiếp.
- Quản trị viên cần khóa một phiên cụ thể hoặc đăng xuất thiết bị.
- Quyền, trạng thái tài khoản hoặc membership thay đổi thường xuyên.
- Ứng dụng chủ yếu là browser gọi backend, không cần phát token cho nhiều resource server độc lập.
- Muốn giữ access credential phía browser ở dạng cookie HttpOnly và quản lý session ở server.
- Cần điều tra và kiểm soát session theo thiết bị, thời điểm đăng nhập, MFA hoặc risk signal.

Session store cho phép server thay đổi trạng thái ngay: xóa session, đánh dấu revoked, giảm quyền, yêu cầu re-authentication hoặc rotate session ID. Đây là lợi thế khi yêu cầu thu hồi tức thời.

### Session vẫn scale được

Session không bắt buộc ứng dụng phải chạy trên một server duy nhất. Có thể lưu session trong Redis, database hoặc session service dùng chung để nhiều application instance tra cứu.

Các lựa chọn vận hành:

- **Shared session store:** mọi instance dùng cùng một store. Dễ đồng bộ trạng thái nhưng thêm dependency và network lookup.
- **Sticky session:** load balancer cố gắng gửi client về cùng instance. Có thể giảm chia sẻ state nhưng gây phụ thuộc routing, failover và rebalance; không nên là cơ chế duy nhất để bảo đảm tính sẵn sàng.
- **Replicated/local cache:** giảm latency nhưng phải giải quyết invalidation, consistency và thời gian thu hồi.
- **Session service tập trung:** tách quản lý phiên khỏi application, đổi lại thêm service và operational dependency.

Nếu session store bị lỗi, hệ thống cần policy rõ ràng. Với endpoint yêu cầu xác thực, thường nên fail closed khi không xác định được session; không được tự chuyển sang cho phép request chỉ vì store unavailable.

### Cookie session cần bảo vệ thế nào?

Ví dụ header:

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `Secure`: chỉ gửi cookie qua HTTPS.
- `HttpOnly`: JavaScript không đọc được cookie qua API trình duyệt thông thường.
- `SameSite`: giảm một số request cross-site tự động mang cookie; chọn `Lax`, `Strict` hoặc `None` theo luồng ứng dụng.
- Prefix `__Host-`: yêu cầu Secure, Path=/ và không có Domain, giúp giới hạn phạm vi cookie trên host.
- Không đặt session ID vào URL, query string hoặc log.

Cookie được browser tự gửi nên ứng dụng vẫn cần phòng CSRF. `SameSite` là một lớp bảo vệ, không phải lý do để bỏ CSRF token hoặc kiểm tra Origin/Referer theo threat model. Nếu cookie dùng `SameSite=None`, bắt buộc Secure và cần đánh giá kỹ cross-site flow.

`HttpOnly` giảm khả năng script đọc cookie nhưng không ngăn XSS thực hiện request dưới phiên của người dùng. Cần CSP, output encoding, kiểm soát dependency và bảo vệ các thao tác nhạy cảm.

## 3. Khi nào stateless access token là lựa chọn phù hợp?

JWT access token hữu ích khi nhiều resource server cần xác minh credential độc lập, đặc biệt trong hệ thống API hoặc dịch vụ phân tán.

Các tình huống có lợi:

- Nhiều API cần kiểm tra token mà không gọi authorization server ở mọi request.
- API cần nhận diện issuer, subject, audience và scope theo một hợp đồng token rõ ràng.
- Có nhiều client như mobile, web backend và service-to-service.
- Cần giảm phụ thuộc vào session lookup trung tâm trong đường đi request.
- Token ngắn hạn và policy chấp nhận độ trễ thu hồi giới hạn theo thời gian sống token.
- Resource server có thể quản lý trust configuration, JWKS cache, key rotation và validation thống nhất.

Ví dụ payload access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Resource server cần xác minh chữ ký bằng khóa của issuer tin cậy, `iss` chính xác, `aud` dành cho API hiện tại, thời hạn, loại token và các claims cần thiết. Sau đó mới đánh giá scope, role, tenant membership và quyền trên tài nguyên.

### Stateless không có nghĩa là không có state ở bất kỳ đâu

Ngay cả khi API xác minh JWT cục bộ, hệ thống có thể vẫn lưu:

- Refresh token family và trạng thái rotation/reuse.
- Danh sách token hoặc phiên bị thu hồi trong trường hợp cần revoke trước `exp`.
- Membership, role, trạng thái tài khoản và policy động.
- JWKS cache, issuer registry, key version và trust configuration.
- Idempotency key hoặc trạng thái chống replay cho thao tác đặc biệt.

Vì vậy, “stateless” thường chỉ có nghĩa là **không tra session record cho mỗi access-token request**. Không nên tuyên bố toàn hệ thống hoàn toàn stateless nếu vẫn có các trạng thái bảo mật khác.

### JWT có thể làm authorization cũ đi

Nếu token chứa role `admin` và quyền đó bị gỡ ở server, JWT đã phát hành vẫn giữ claim cũ cho đến khi hết hạn, trừ khi resource server có thêm cơ chế tra cứu/revoke. Token càng dài hạn, khoảng thời gian dùng quyền cũ càng dài.

Đối với quyền thay đổi thường xuyên, không nên nhồi toàn bộ permission chi tiết vào access token sống lâu. Có thể dùng scope tổng quát, kiểm tra ownership/membership ở server hoặc rút ngắn TTL.

## 4. So sánh theo tiêu chí quyết định

| Tiêu chí | Server-side session | Stateless JWT access token |
| --- | --- | --- |
| Thu hồi một phiên | Có thể xóa/đánh dấu ngay qua store | Thường cần chờ `exp`, denylist hoặc lookup bổ sung |
| Logout tức thời | Tự nhiên nếu mọi request kiểm tra store | Cần cơ chế revoke hoặc token TTL ngắn |
| Độ trễ request | Có session lookup; có thể cache | Xác minh chữ ký cục bộ, nhưng có chi phí crypto |
| Khả năng scale | Cần shared store/replication hoặc routing | Dễ xác minh phân tán hơn; cần quản lý keys/config |
| Quyền thay đổi giữa phiên | Cập nhật session hoặc tra policy động | Claims đã ký có thể cũ đến khi token hết hạn |
| Kích thước credential | Cookie chứa session ID nhỏ | JWT có thể lớn theo số claims |
| Browser CSRF | Cần chống CSRF vì cookie tự gửi | Nếu JWT trong cookie vẫn cần chống CSRF |
| XSS và token theft | HttpOnly cookie khó bị đọc trực tiếp nhưng XSS vẫn hành động dưới phiên | Token trong localStorage dễ bị script đọc; cookie JWT vẫn có CSRF |
| Offline verification | Không, nếu không tra session state | Có thể, nếu có trust config và key |
| Multi-service | Cần session service hoặc gateway propagation | Mỗi service có thể validate audience/issuer riêng |
| Quản lý khóa | Ít phụ thuộc ký JWT cho session | Cần JWKS, rotation, algorithm allowlist và cache |
| Thu hồi khi store lỗi | Không xác định session thì thường từ chối | JWT có thể vẫn xác minh cục bộ nếu key/config còn tin cậy |
| Privacy | Cookie chỉ chứa opaque ID; server giữ dữ liệu | Claims có thể bị đọc ở mọi nơi nhận token |

Không có cột nào thắng trong mọi trường hợp. Quyết định cần dựa trên tác động của từng tiêu chí đối với sản phẩm.

## 5. Thu hồi và logout: điểm quyết định quan trọng

### Session: thu hồi tập trung

Khi người dùng logout:

1. Server xác thực session hiện tại.
2. Server xóa hoặc đánh dấu session revoked trong store.
3. Server gửi cookie hết hạn về browser.
4. Request sau đó không tìm thấy session hợp lệ và bị yêu cầu đăng nhập lại.

Nếu có nhiều application instance, mọi instance phải nhìn thấy trạng thái revoke theo giới hạn consistency đã công bố. Local cache có TTL dài có thể làm chậm hiệu lực logout; cần invalidation hoặc TTL phù hợp.

### JWT: thu hồi có giới hạn theo thiết kế

JWT access token đã ký thường có thể được xác minh độc lập đến khi `exp`. Xóa refresh token không tự động vô hiệu hóa access token đã phát hành. Các phương án:

- **Short-lived access token:** giảm khoảng thời gian token bị dùng sau khi logout/revoke.
- **Denylist/revocation registry:** resource server tra `jti` hoặc token reference bị thu hồi; thêm state lookup.
- **Introspection:** resource server hỏi authorization server token còn active không; thêm network dependency và latency.
- **Key rotation:** có thể vô hiệu hóa nhiều token cùng khóa, phạm vi rộng và chịu ảnh hưởng JWKS cache; không nên dùng để revoke một user đơn lẻ.
- **Sender-constrained token:** ràng buộc token với khóa hoặc chứng thư client để giảm giá trị khi token bị đánh cắp, ví dụ DPoP hoặc mTLS; không thay thế expiry/revocation policy.

Không dùng `jti` trong denylist như một giải pháp miễn phí: registry cần lưu trạng thái đến ít nhất thời điểm token hết hạn và cần chống race, cache stale, replication delay.

### Refresh token cần có state

Dù access token là JWT, refresh token nên được quản lý như credential nhạy cảm có trạng thái. Rotation, reuse detection, revoke family, client binding và logout đều cần authorization server theo dõi vòng đời refresh token.

Một mô hình phổ biến:

- Access token JWT sống ngắn, chỉ chứa claims tối thiểu.
- Refresh token opaque, rotation và lưu hash/fingerprint an toàn ở authorization server.
- Khi logout hoặc phát hiện reuse, revoke refresh token family.
- Access token đã cấp tiếp tục có hiệu lực tối đa đến `exp`, trừ khi resource server có thêm cơ chế revoke.

Đây là mô hình hybrid: access token có thể được xác minh cục bộ, nhưng vòng đời phiên dài hạn vẫn có trạng thái.

## 6. Browser: session cookie, bearer token hay BFF?

Browser là môi trường đặc biệt vì cookie được tự động gửi, còn JavaScript có thể truy cập một số nơi lưu token.

### Server-rendered web application

Nếu browser chủ yếu gọi backend cùng site, session cookie HttpOnly thường đơn giản và dễ thu hồi. Backend giữ session state, browser không cần quản lý access token dài hạn.

Cần:

- Cookie Secure, HttpOnly và SameSite phù hợp.
- CSRF protection cho request thay đổi dữ liệu.
- Session ID rotation sau login, MFA hoặc thay đổi privilege.
- Idle timeout và absolute timeout.
- Logout/revoke phía server.
- Re-authentication cho thao tác nhạy cảm.

### SPA gọi API trực tiếp

SPA thường dùng Authorization Code Flow với PKCE. Access token có thể được giữ trong memory và gửi dưới dạng Bearer token. Tránh lưu token dài hạn trong localStorage nếu không có yêu cầu đặc biệt vì XSS có thể đọc và lấy token.

Dù access token không tự gửi như cookie, XSS vẫn có thể đọc token trong memory hoặc thực hiện API call dưới quyền của ứng dụng. PKCE bảo vệ authorization code exchange, không bảo vệ token sau khi client đã nhận.

### Backend-for-Frontend (BFF)

BFF giữ token ở server và browser chỉ giữ session cookie. Browser gọi BFF; BFF thay mặt client gọi API và giữ access/refresh token phía server.

~~~mermaid
flowchart LR
    B["Browser"] -->|"HttpOnly session cookie"| F["BFF"]
    F -->|"Access token"| A["Resource APIs"]
    F --> S["Server-side token/session store"]
    A --> D["Business data"]
~~~

BFF giảm việc đưa bearer token vào JavaScript/browser storage, nhưng không loại bỏ CSRF, XSS hoặc session hijacking. Cookie vẫn cần Secure/HttpOnly/SameSite và CSRF defenses; BFF cần bảo vệ token store, outbound authorization và session lifecycle.

### Quy tắc thực dụng cho browser

Nếu chỉ có một backend first-party phục vụ browser, session cookie thường là lựa chọn dễ vận hành. Nếu browser cần gọi nhiều API độc lập, cân nhắc BFF hoặc token architecture có audience/scope rõ ràng. Đừng đặt JWT vào cookie rồi gọi mô hình đó là stateless hoàn toàn: cookie vẫn là credential tự gửi và resource server có thể cần CSRF protection.

## 7. Mobile, desktop và service-to-service

### Native mobile / desktop

Ứng dụng native thường dùng Authorization Code Flow với PKCE qua external user-agent. Access token có thể là JWT hoặc opaque tùy authorization server và resource server. Refresh token nên được lưu trong secure storage của nền tảng, rotation và reuse detection được bật theo policy.

Không nhúng client secret dùng chung trong binary. Nếu dùng JWT access token, API vẫn cần kiểm tra issuer, audience, thời hạn, token type và scope. Nếu token opaque, ứng dụng cần introspection hoặc gateway phù hợp.

### Service-to-service

Service không có người dùng tương tác thường dùng OAuth Client Credentials hoặc cơ chế workload identity. Credential của workload cần được bảo vệ bằng secret manager, certificate hoặc platform identity; không dùng browser session cookie.

JWT access token có thể giúp các API xác minh độc lập, nhưng cần:

- Audience riêng cho resource server đích.
- Scope/permission tối thiểu.
- Token lifetime ngắn.
- Issuer và signing key được quản lý.
- Rotation/credential renewal.
- Sender-constrained credential khi threat model yêu cầu.
- Không chuyển tiếp một token có audience của gateway sang mọi service.

### Microservices và trust boundaries

Nếu gateway xác thực JWT rồi gọi service phía sau, mỗi service cần hiểu rõ nó tin gateway, tin token gốc hay nhận một token mới dành riêng cho nó. Không coi một header `X-User-Id` do client gửi là danh tính đã xác thực.

Các lựa chọn:

- Gateway forward access token có audience phù hợp với downstream API.
- Gateway dùng token exchange để lấy token cho resource server đích.
- Service-to-service dùng workload identity và truyền context người dùng theo cơ chế được ký/xác thực.
- Mỗi service tự validate token nếu nó là trust boundary độc lập.

Không dùng một JWT audience chung quá rộng cho mọi API chỉ để đơn giản hóa cấu hình. Audience giúp ngăn token substitution giữa resource server.

## 8. Chi phí và rủi ro vận hành

### Session store

Cần theo dõi:

- Latency và availability của store.
- TTL cleanup, session expiration và memory usage.
- Replication lag và invalidation khi revoke.
- Session fixation và session ID rotation.
- Backup/restore, encryption và access control.
- Failover behavior và fail-closed policy.

Một session store dùng chung là dependency trên đường request. Nếu store chậm, xác thực session cũng chậm. Cache có thể giảm latency nhưng phải tính thời gian revoke và consistency.

### JWT trust infrastructure

Cần theo dõi:

- JWKS endpoint availability và cache freshness.
- Signing key rotation, `kid` mới và giai đoạn overlap.
- Thuật toán được phép; từ chối `alg=none` và algorithm confusion.
- Issuer allowlist và exact issuer matching.
- Audience validator của từng resource server.
- Clock synchronization và clock skew.
- Token size, header limits và claim minimization.
- Denylist/introspection latency nếu có.
- Thời hạn token và tác động khi revoke.

JWT loại bỏ session lookup cho mỗi request nhưng đưa thêm trách nhiệm quản lý khóa và policy vào từng resource server. Một cấu hình audience sai có thể khiến token dành cho API khác được chấp nhận; một issuer trust sai có thể làm mất toàn bộ ranh giới danh tính.

### Khả năng quan sát

Đo các tín hiệu phù hợp:

- Session create, active, revoke, expiration và lookup errors.
- JWT validation failures theo reason enum: issuer, audience, signature, expiry, token type.
- JWKS refresh success/failure và unknown `kid`.
- Introspection latency/error nếu dùng opaque token.
- Refresh rotation, reuse detection và family revocation.
- Không ghi raw cookie, authorization header hoặc token vào log/metric/trace.

Không dùng user ID, session ID hoặc token ID làm metric label có cardinality không giới hạn.

## 9. Mô hình hybrid thường gặp

Không cần chọn duy nhất một cơ chế cho toàn bộ hệ thống. Có thể dùng mô hình khác nhau cho từng ranh giới:

| Thành phần | Mô hình gợi ý | Lý do |
| --- | --- | --- |
| Browser → BFF | Session cookie | Quản lý logout và phiên browser tập trung |
| BFF → Resource API | JWT access token ngắn hạn | API xác minh issuer/audience/scope |
| Mobile → Resource API | Access token + refresh token rotation | Native app cần gọi API và quản lý đăng nhập dài hạn |
| Service → Service | Workload identity + short-lived access token | Không phụ thuộc user session |
| Admin console | Session + re-authentication/MFA | Quyền nhạy cảm, cần thu hồi phiên |
| API cần revoke tức thời | Opaque token/introspection hoặc JWT + revoke lookup | Kiểm tra trạng thái server-side |

Hybrid architecture có thể làm tăng số thành phần cần vận hành. Cần xác định rõ ai phát hành credential, ai giữ refresh token, ai xác minh access token và nơi nào là nguồn sự thật của session/revocation.

### Ví dụ luồng hybrid browser BFF

1. Browser đăng nhập qua OIDC Authorization Code Flow với PKCE.
2. BFF nhận callback, kiểm tra `state`, `nonce` và ID token theo OIDC.
3. BFF tạo session server-side và gửi cookie HttpOnly.
4. BFF giữ access/refresh token trong server-side store.
5. Browser gọi BFF bằng cookie; BFF áp dụng CSRF protection.
6. BFF gọi API bằng access token có audience và scope phù hợp.
7. Logout xóa session, revoke refresh token theo policy và xóa token store.
8. Access token đã phát hành có thể còn hiệu lực đến `exp` nếu downstream không có revoke lookup.

## 10. Framework ra quyết định

Dùng các câu hỏi sau để xác định mô hình:

1. **Ai là client?** Browser first-party, SPA, native app, third-party client hay service?
2. **Logout cần hiệu lực nhanh đến mức nào?** Request kế tiếp, vài phút hay trong TTL token?
3. **Có bao nhiêu resource server?** Một backend hay nhiều API độc lập?
4. **Quyền thay đổi thường xuyên không?** Role, tenant membership hoặc account status có thể bị thu hồi giữa phiên?
5. **Có chấp nhận network lookup không?** Session store/introspection có đáp ứng latency và availability?
6. **Ai vận hành trust infrastructure?** Có quy trình JWKS, key rotation, issuer registry và validator thống nhất?
7. **Browser threat model ra sao?** Cookie/CSRF hay bearer token/XSS là rủi ro chính?
8. **Có yêu cầu audit theo phiên/thiết bị không?** Cần revoke riêng từng phiên hoặc hiển thị danh sách thiết bị?
9. **Có cần offline verification không?** Resource server có thể xác minh cục bộ mà không gọi issuer?
10. **Có thể dùng hybrid không?** Session cho browser và JWT ngắn hạn cho service/API thường đáp ứng yêu cầu khác nhau.

### Ma trận định hướng

| Điều kiện ưu tiên | Hướng nên đánh giá trước |
| --- | --- |
| Browser first-party, logout/revoke tức thời | Server-side session cookie |
| Nhiều API cần xác minh độc lập | JWT access token ngắn hạn |
| Cần kiểm tra token active/revoke tập trung | Opaque token + introspection |
| Browser cần gọi API nhưng muốn giữ token phía server | BFF + session cookie |
| Mobile/desktop native | Authorization Code + PKCE, access token và refresh token có rotation |
| Quyền thay đổi nhanh, yêu cầu revoke mạnh | Session hoặc token có state lookup/introspection |
| Service-to-service | Workload identity + short-lived token theo audience |

Đây là hướng đánh giá ban đầu, không phải quy tắc cứng. Hãy kiểm chứng bằng threat model, latency budget, yêu cầu availability và khả năng vận hành.

## 11. Ví dụ decision record

Một quyết định kiến trúc nên ghi rõ bối cảnh và hậu quả. Ví dụ:

~~~text
Decision: Browser authentication dùng server-side session qua BFF.

Context:
- Ứng dụng first-party, browser chủ yếu gọi backend cùng site.
- Cần logout và revoke session nhanh.
- BFF giữ access/refresh token để gọi downstream API.
- Browser không cần tự quản lý bearer token.

Chosen approach:
- OIDC Authorization Code Flow + PKCE ở login.
- BFF tạo session ID ngẫu nhiên, lưu trạng thái phía server.
- Cookie Secure, HttpOnly, SameSite phù hợp; có CSRF protection.
- Downstream API nhận access token ngắn hạn với audience/scope riêng.
- Refresh token rotation và reuse detection ở authorization server.

Consequences:
- Cần vận hành session/token store và xử lý failover.
- Mọi instance BFF cần thấy revoke state nhất quán.
- Logout xóa session và revoke refresh token family.
- Access token downstream có thể còn hiệu lực đến exp nếu không có revoke lookup.
- Cần test CSRF, session fixation, token theft và logout propagation.

Rejected alternatives:
- Browser lưu refresh token lâu dài trong localStorage.
- JWT dài hạn làm session browser mà không có revoke policy.
- Một audience dùng chung cho mọi downstream API.
~~~

Một decision record tốt cũng nên có owner, ngày quyết định, phạm vi áp dụng, giả định, tiêu chí đánh giá lại và các phương án bị loại bỏ cùng lý do. Khi threat model hoặc yêu cầu logout thay đổi, cần xem xét lại quyết định.

## 12. Các lỗi lựa chọn thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chọn JWT vì nghĩ stateless tự động scale tốt hơn | Bỏ qua key management, cache và revoke | So sánh toàn bộ chi phí vận hành |
| Dùng JWT sống dài để có logout đơn giản | Token có thể dùng sau logout | Short TTL hoặc revoke lookup/introspection |
| Cho rằng session chỉ scale trên một server | Bỏ qua shared store và session service | Đánh giá shared store, cache và consistency |
| Đưa session object vào cookie | Lộ dữ liệu và tăng kích thước credential | Cookie chỉ giữ opaque session ID |
| Dùng JWT trong cookie và bỏ CSRF | Browser tự gửi cookie cross-site | Áp dụng CSRF defenses |
| Lưu bearer token lâu dài trong localStorage | XSS có thể lấy token | Memory/BFF/secure storage theo client |
| Nhét toàn bộ role vào JWT sống lâu | Authorization stale | Claims tối thiểu, TTL ngắn, policy động |
| Dùng một audience cho mọi API | Token substitution giữa service | Audience riêng theo resource server |
| Xóa refresh token nhưng nghĩ access token đã mất hiệu lực | Access token cũ vẫn có thể dùng đến exp | Hiểu rõ revoke propagation |
| Dùng key rotation để revoke một user | Ảnh hưởng diện rộng và cache delay | Revoke theo token/session/family |
| Không rotate session ID sau login | Session fixation | Regenerate ID sau authentication/privilege change |
| Không có fail-closed policy | Store/IdP lỗi có thể mở đường bypass | Định nghĩa lỗi xác thực và fallback rõ ràng |

## 13. Checklist trước khi chốt thiết kế

- [ ] Đã mô tả client type và trust boundaries.
- [ ] Đã xác định nơi lưu authentication state và authorization state.
- [ ] Đã xác định yêu cầu logout, revoke và thời gian tối đa token còn dùng được.
- [ ] Đã chọn session, JWT, opaque token hoặc hybrid theo từng client/resource.
- [ ] Đã có policy cookie/CSRF hoặc bearer token/XSS phù hợp.
- [ ] Đã xác định access token TTL và refresh token lifecycle.
- [ ] Đã quy định issuer, audience, scope, token type và key rotation.
- [ ] Đã xác định cách revoke session/token/family.
- [ ] Đã có fail-closed behavior khi session store, introspection hoặc JWKS lỗi.
- [ ] Đã tính latency, availability, cache consistency và operational cost.
- [ ] Đã xác định dữ liệu nào được phép đưa vào token/log/metric/trace.
- [ ] Đã có test logout, revoke, replay, stale permission, CSRF, XSS assumptions và audience mismatch.
- [ ] Đã ghi decision record, trade-off, owner và điều kiện đánh giá lại.

## Ghi nhớ

- Session giữ trạng thái phiên phía server; JWT access token cho phép resource server xác minh claims đã ký mà không tra session record trên mỗi request.
- Opaque token thường cần introspection hoặc lookup; nó không đồng nghĩa với server-side browser session.
- Stateless không có nghĩa toàn hệ thống không có state: refresh rotation, revoke, membership và policy vẫn có thể cần state.
- Session có thể scale bằng shared store; JWT đổi session lookup lấy trách nhiệm quản lý khóa, claims và thu hồi.
- Cookie session và JWT đặt trong cookie đều cần xem xét CSRF; bearer token trong JavaScript cần bảo vệ trước XSS.
- Hybrid thường phù hợp: session cho browser/BFF, access token ngắn hạn cho API và refresh token có trạng thái.
- Quyết định đúng là quyết định đáp ứng threat model, logout/revoke, kiến trúc client và khả năng vận hành của hệ thống.

### Tiêu chuẩn tham khảo

- **RFC 6749 — OAuth 2.0 Authorization Framework:** access token, refresh token và authorization flows.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách gửi bearer token và rủi ro token bị lộ.
- **RFC 7519 — JSON Web Token:** cấu trúc JWT và claims chuẩn.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái opaque/access token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** thực hành bảo mật OAuth hiện hành.
- **RFC 7636 / RFC 8252:** PKCE và OAuth cho native applications.
- **OWASP Session Management Cheat Sheet:** quản lý session ID, cookie, timeout và session fixation.
- **OWASP CSRF Prevention Cheat Sheet:** bảo vệ request được browser tự động gửi credential.
