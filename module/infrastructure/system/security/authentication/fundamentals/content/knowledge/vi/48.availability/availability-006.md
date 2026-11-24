# Dependency outage

**Dependency outage** là tình trạng một dịch vụ mà luồng xác thực phụ thuộc vào không thể đáp ứng đúng chức năng, độ trễ hoặc mức sẵn sàng đã cam kết. Sự cố có thể nằm ở identity provider, kho tài khoản, session store, MFA provider, token endpoint, KMS/HSM, DNS, mạng, hệ thống gửi email/SMS hoặc chính dịch vụ nội bộ. Khi một dependency ngừng hoạt động, người dùng có thể không đăng nhập được, không refresh được token, không hoàn tất MFA, không khôi phục được tài khoản hoặc không thể kết thúc phiên theo cách mong đợi.

Khả năng sẵn sàng của xác thực không chỉ là giữ trang login hoạt động. Hệ thống phải duy trì đúng ranh giới bảo mật khi một thành phần lỗi: không cấp quyền trái phép để giữ trải nghiệm, không làm mất khả năng thu hồi credential, không tạo retry storm và không khiến một lỗi cục bộ lan thành outage toàn hệ thống. Mỗi luồng cần có chính sách rõ về timeout, retry, fallback, cache, fail-open/fail-closed và phục hồi.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn. Trong chương **Availability**, bài này tập trung vào Dependency outage và cách giữ luồng xác thực an toàn khi dịch vụ phụ thuộc gặp sự cố.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Vẽ dependency graph cho login, MFA, token issuance, token refresh, session validation và account recovery.
2. Phân biệt lỗi của authentication dependency với lỗi của ứng dụng hoặc resource API.
3. Xác định dependency critical, optional, synchronous và asynchronous trong từng luồng.
4. Đặt timeout, retry, exponential backoff, jitter, circuit breaker và bulkhead phù hợp.
5. Quyết định khi nào dùng cache, offline verification hoặc degraded mode mà không vượt ranh giới bảo mật.
6. Phân biệt fail-closed, fail-open và graceful degradation theo loại hành động.
7. Thiết kế fallback cho MFA, identity provider, token endpoint, session store và KMS/HSM.
8. Định nghĩa SLI/SLO, error budget, RTO, RPO và dependency availability target.
9. Xây dựng incident response, failover, recovery và reconciliation sau outage.
10. Kiểm thử dependency failure, retry storm, stale cache, split brain, key rotation và phục hồi dịch vụ.

## 2. Dependency outage trong xác thực là gì?

Một authentication flow thường đi qua nhiều thành phần. Mỗi thành phần có thể hoạt động riêng lẻ nhưng tổng thể vẫn thất bại nếu một dependency quan trọng không đáp ứng.

Ví dụ, một lần đăng nhập bằng password và MFA có thể cần:
- Web/mobile client và DNS để tìm đúng endpoint.
- API gateway hoặc load balancer để nhận request.
- Identity service để điều phối xác thực.
- Account database hoặc credential store để tra password verifier.
- Password hashing service/runtime để xác minh password.
- MFA provider hoặc TOTP verification service.
- Session store để tạo session.
- KMS/HSM để dùng encryption/signing key.
- Event pipeline để ghi audit event quan trọng.
- Email/SMS/push provider nếu flow gửi challenge hoặc thông báo.

Nếu một dependency không sẵn sàng, hệ thống phải biết luồng nào bị ảnh hưởng và hành động nào có thể tiếp tục an toàn.

### 2.1. Không phải mọi dependency có cùng mức criticality

| Dependency | Luồng thường phụ thuộc | Ảnh hưởng khi outage |
| --- | --- | --- |
| Identity provider / federation | SSO, external login | Không thể hoàn tất login mới qua provider đó. |
| Account/credential database | Password verification, account state | Không thể xác minh credential hoặc trạng thái tài khoản. |
| MFA service/provider | OTP, push, SMS, challenge | Người dùng không hoàn tất được factor tương ứng. |
| Token endpoint | Authorization code exchange, refresh | Không cấp hoặc làm mới token được. |
| JWKS/metadata endpoint | JWT signature verification, OIDC discovery | Có thể xác minh bằng cache hợp lệ; key mới có thể chưa dùng được. |
| Session store | Tạo, đọc, revoke session | Có thể không xác định được session hiện tại hoặc không tạo phiên mới. |
| KMS/HSM | Decrypt secret, sign token/assertion | Không thể thực hiện thao tác mật mã cần key. |
| DNS/network/TLS | Kết nối tới dependency | Nhiều dependency có thể cùng mất kết nối. |
| Email/SMS provider | Recovery, notification, OTP delivery | Một số flow bị chậm hoặc không thể hoàn tất. |
| Audit/event pipeline | Audit, detection, investigation | Có thể thiếu bằng chứng nếu event không được buffer bền vững. |
| Time service | Token expiry, TOTP, certificate validity | Clock skew có thể làm xác minh sai hoặc tạo quyết định không nhất quán. |

Một dependency có thể critical cho một hành động nhưng optional cho hành động khác. Ví dụ, email provider không cần cho passkey login thông thường, nhưng có thể cần cho một recovery flow. Đừng gắn một nhãn criticality duy nhất cho cả hệ thống; hãy đánh giá theo từng use case.

### 2.2. Dependency graph

Sơ đồ minh họa các phụ thuộc của login và các luồng liên quan:

~~~mermaid
flowchart TD
    C[Web / Mobile Client] --> DNS[DNS + Network + TLS]
    DNS --> GW[API Gateway]
    GW --> ID[Identity Service]
    ID --> DB[(Account + Credential Store)]
    ID --> MFA[MFA Provider]
    ID --> SESS[(Session Store)]
    ID --> KMS[KMS / HSM]
    ID --> IDP[External Identity Provider]
    ID --> EVT[Durable Audit Buffer]
    ID --> TOK[Token Service]
    TOK --> JWKS[Signing Key / JWKS]
    TOK --> API[Resource API]
    REC[Account Recovery] --> EMAIL[Email / SMS Provider]
    REC --> DB
    REC --> MFA
    SESS --> EVT
    TOK --> EVT
~~~

Sơ đồ này không có nghĩa mọi login đều gọi mọi dependency. Login bằng passkey nội bộ có thể không cần external IdP; JWT resource server có thể xác minh chữ ký bằng JWKS cache mà không gọi token endpoint. Hãy vẽ graph theo flow thực tế, đánh dấu các cạnh synchronous và asynchronous, đồng thời xác định điểm nào nằm trong critical path.

### 2.3. Synchronous và asynchronous dependency

- **Synchronous:** request phải chờ kết quả dependency trước khi tiếp tục, ví dụ password verifier lookup hoặc MFA verification.
- **Asynchronous:** hệ thống có thể ghi event vào durable queue rồi xử lý sau, ví dụ analytics hoặc một số notification.
- **Conditionally synchronous:** chỉ cần khi policy/flow được kích hoạt, ví dụ step-up MFA hoặc external federation.
- **Background reconciliation:** xử lý trạng thái sau sự cố, ví dụ đối soát event, cập nhật cache hoặc retry notification.

Đẩy một thao tác sang queue không tự động làm nó optional. Nếu đó là audit bắt buộc trước một hành động đặc quyền, hệ thống cần xác nhận durable write trước khi commit hoặc có cơ chế transaction/outbox đủ tin cậy.

## 3. Failure mode và blast radius

Dependency outage có nhiều dạng hơn một server tắt hẳn:

- **Unavailable:** connection refused, DNS failure, service không có instance khỏe.
- **Slow / degraded:** phản hồi rất chậm, timeout, queue backlog hoặc throughput giảm.
- **Partial failure:** một region, tenant, account shard hoặc một endpoint lỗi.
- **Incorrect response:** dữ liệu sai, key metadata cũ, status không nhất quán hoặc response bị lỗi định dạng.
- **Overloaded:** dependency vẫn sống nhưng không xử lý được tải hiện tại.
- **Network partition:** một số thành phần không thể liên lạc với nhau dù mỗi phía vẫn hoạt động.
- **Credential/configuration failure:** client secret, certificate, trust bundle hoặc permission bị hết hạn/sai.
- **Capacity exhaustion:** connection pool, thread pool, file descriptor, database connection hoặc quota cạn.
- **Dependency chain failure:** lỗi ở một dịch vụ làm nhiều service phía sau cùng timeout.

Một outage ngắn của dịch vụ MFA có thể gây login failure; nếu client retry liên tục, tải tăng thêm và làm dịch vụ phục hồi chậm hơn. Một lỗi DNS có thể đồng thời ảnh hưởng IdP, KMS và event broker, khiến đội vận hành nhầm là nhiều dịch vụ độc lập bị lỗi.

### 3.1. Failure mode matrix

| Failure mode | Dấu hiệu | Rủi ro chính |
| --- | --- | --- |
| Timeout tăng | p95/p99 latency tăng, request pending | Thread/connection bị giữ, retry chồng lặp. |
| DNS không phân giải | NXDOMAIN, SERVFAIL, resolver timeout | Nhiều dependency cùng mất kết nối. |
| KMS unavailable | Sign/decrypt operation lỗi | Không thể ký token hoặc giải mã shared secret. |
| Session store partition | Một số node không đọc được session | Login/logout và revoke không nhất quán. |
| IdP outage | OIDC callback/token exchange thất bại | SSO login bị gián đoạn. |
| MFA delivery outage | Challenge không tới người dùng | Người dùng không hoàn tất factor. |
| Token endpoint outage | Refresh request lỗi | App đang có access token còn hạn vẫn có thể hoạt động một thời gian. |
| JWKS rotation mismatch | Unknown key ID hoặc key cache cũ | Token mới không xác minh được; token không tin cậy không được chấp nhận. |
| Audit queue full | Event không thể ghi bền vững | Thiếu audit evidence hoặc backpressure. |
| Clock skew | TOTP/token/certificate validity lệch | False rejection hoặc kiểm tra thời hạn sai. |

### 3.2. Blast radius

Đánh giá outage theo:
- Số lượng người dùng, tenant, region và client bị ảnh hưởng.
- Luồng nào bị lỗi: login mới, refresh, API access, logout, recovery hay admin action.
- Quyền và dữ liệu nào có thể bị tác động.
- Có dependency dùng chung giữa nhiều service không.
- Có fallback nào đang được sử dụng và thời gian dữ liệu có thể stale.
- Có nguy cơ lỗi lan sang hệ thống khác do retry hoặc failover không.

Không kết luận “authentication down” chỉ từ một endpoint login. Cần đo riêng login, token refresh, session validation, logout, MFA enrollment và account recovery.

## 4. Phân loại dependency theo critical path

Với mỗi use case, liệt kê dependency cần thiết và điều kiện để có thể tiếp tục.

Ví dụ:

| Use case | Critical dependency | Có thể degraded như thế nào? |
| --- | --- | --- |
| Password login | Account store, password verifier, policy engine, session/token issuer | Chỉ dùng cache nếu freshness và revocation policy cho phép; không bỏ qua password verification. |
| Passkey login | WebAuthn verifier, credential store, challenge/state store, session issuer | Không thể bỏ challenge/origin/signature checks; có thể fallback sang factor khác đã đăng ký. |
| MFA login | Factor verifier hoặc provider, transaction state | Chỉ fallback sang factor thay thế đã được xác minh và policy cho phép. |
| SSO login | Trusted IdP, callback validation, token exchange | Dùng IdP khác đã cấu hình hoặc local credential nếu tài khoản hỗ trợ. |
| API access với JWT | Signature verification key, issuer/audience/time checks, authorization data | Dùng JWKS cache còn hợp lệ; không bỏ signature/claim validation. |
| API access với opaque token | Introspection endpoint hoặc trạng thái token cache | Có thể dùng cache ngắn theo policy; nếu không đủ freshness thì từ chối. |
| Refresh token | Authorization server/token endpoint, client binding | Giữ access token còn hạn; chờ retry an toàn hoặc yêu cầu đăng nhập lại. |
| Logout/revocation | Session/token store và issuer revocation endpoint | Chặn local session ngay; remote revoke có thể pending và cần retry. |
| Account recovery | Recovery service, account store, verified delivery/factor | Có thể cho người dùng bắt đầu yêu cầu nhưng không hoàn tất nếu không xác minh được. |
| Admin credential change | Identity store, MFA/step-up, durable audit | Thường fail-closed nếu không thể xác minh actor hoặc ghi audit bắt buộc. |

Criticality không chỉ là “có cần cho request thành công không”. Cần hỏi thêm: nếu dependency mất, có cách tiếp tục mà vẫn giữ được authentication assurance, authorization và revocation semantics không?

## 5. Fail-closed, fail-open và graceful degradation

### 5.1. Fail-closed

Khi không thể xác minh một điều kiện bảo mật cần thiết, hệ thống từ chối hành động. Ví dụ:
- Không thể xác minh password hoặc passkey assertion.
- Không thể kiểm tra MFA bắt buộc.
- Không xác minh được chữ ký token.
- Không thể xác định account bị disabled hay credential đã revoked trong một hành động nhạy cảm.
- Không thể xác thực administrator trước khi thay recovery factor.
- Không thể ghi audit bắt buộc cho một hành động đặc quyền nếu policy yêu cầu durable audit trước commit.

Fail-closed có thể làm giảm availability, nhưng tránh biến lỗi dependency thành cấp quyền ngoài ý muốn.

### 5.2. Fail-open

Hệ thống tiếp tục hành động dù một dependency bảo mật không phản hồi. Điều này có thể phù hợp với một số chức năng không nhạy cảm hoặc tín hiệu phụ, nhưng nguy hiểm nếu áp dụng cho credential verification, MFA bắt buộc, authorization hoặc revocation.

Ví dụ không nên fail-open:
- MFA provider timeout nên tự động bỏ qua MFA.
- KMS không ký được token nên dùng một khóa mặc định hardcoded.
- Session store không đọc được nên coi mọi session là active.
- Introspection timeout nên mặc định opaque token còn active.
- Recovery email không gửi được nên bỏ qua recovery proof.

Nếu cân nhắc fail-open, cần chứng minh hành động vẫn được bảo vệ bởi một cơ chế độc lập có mức assurance tương đương, phạm vi hẹp, thời gian ngắn và có audit.

### 5.3. Graceful degradation

Graceful degradation giữ lại phần chức năng an toàn khi một dependency lỗi. Ví dụ:
- Nếu một IdP ngoài bị lỗi, vẫn cho phép login bằng passkey/password nội bộ đã đăng ký nếu policy cho phép.
- Nếu token endpoint tạm lỗi, app tiếp tục dùng access token đã được cấp và còn hạn; không kéo dài expiry.
- Nếu JWKS endpoint không truy cập được, resource server dùng key cache còn trong freshness window đã định nghĩa.
- Nếu một kênh MFA không khả dụng, cho phép factor thay thế đã enroll và được policy chấp nhận.
- Nếu email notification chậm, vẫn ghi audit event và xếp hàng gửi lại; không bỏ qua proof của recovery.
- Nếu analytics pipeline lỗi, buffer hoặc bỏ telemetry không thiết yếu; audit đặc quyền vẫn phải theo durability policy.

Graceful degradation phải có giới hạn rõ: loại người dùng, hành động, thời gian, assurance và dữ liệu được phép truy cập. Không biến chế độ tạm thời thành policy lâu dài.

### 5.4. Decision matrix

| Hành động | Dependency bảo mật không sẵn sàng | Quyết định thường phù hợp |
| --- | --- | --- |
| Login bằng password khi credential store lỗi | Không xác minh được password | Fail-closed. |
| Login có MFA bắt buộc nhưng provider chính lỗi | Không xác minh factor | Dùng factor thay thế đã enroll hoặc từ chối. |
| API với JWT đã xác minh và còn hạn | Token signature/claims vẫn kiểm tra được bằng key cache hợp lệ | Tiếp tục theo cache policy và authorization hiện hành. |
| API với opaque token, introspection lỗi | Không biết token active hay revoked | Dùng cache rất ngắn nếu policy cho phép; nếu không, fail-closed. |
| Refresh token endpoint lỗi | Không cấp token mới | Giữ access token còn hạn; không tự gia hạn. |
| Logout local khi remote revoke lỗi | Không liên hệ được issuer | Chặn local session, ghi revoke pending và retry an toàn. |
| Password reset/recovery proof không kiểm tra được | Không xác minh quyền sở hữu account | Fail-closed cho bước hoàn tất. |
| Analytics pipeline lỗi | Telemetry không thiết yếu | Degrade hoặc buffer. |
| Admin thay MFA/recovery factor, audit store lỗi | Không đảm bảo audit bắt buộc | Thường fail-closed hoặc yêu cầu quy trình break-glass có kiểm soát. |

## 6. Timeout, retry và exponential backoff

Timeout phải nhỏ hơn thời gian tổng mà request có thể chiếm trong critical path. Nếu một request login có ngân sách 3 giây, không thể cho từng dependency timeout 5 giây rồi kỳ vọng login hoàn thành trong 3 giây.

### 6.1. Timeout budget

Xác định:
- End-to-end deadline của request.
- Connect timeout.
- Read/response timeout.
- Queue wait timeout.
- Thời gian còn lại cho bước tiếp theo.
- Số lần retry tối đa.

Truyền deadline/cancellation xuống các dependency để request đã hết thời gian không tiếp tục giữ connection hoặc thực hiện công việc không còn cần thiết. Không dùng timeout vô hạn cho authentication request.

### 6.2. Retry có kiểm soát

Retry phù hợp với lỗi transient như connection reset hoặc 503, nhưng phải xét tính idempotent:
- Không retry password hashing local như một lời giải cho database outage.
- Không blind-retry refresh token nếu rotation có thể đã commit ở server.
- Không retry recovery completion hoặc thay đổi credential nếu request có thể đã commit mà response bị mất, trừ khi có idempotency key/transaction semantics.
- Không retry vô hạn khi nhận 401/403 hoặc lỗi credential/configuration.
- Tôn trọng Retry-After nếu dependency trả về.

### 6.3. Exponential backoff và jitter

Một chiến lược minh họa:

~~~text
for attempt in 1..maxAttempts:
    result = callDependency(timeout = remainingDeadline)

    if result is success:
        return result

    if result is nonRetryable:
        failImmediately

    delay = min(maxDelay, baseDelay * 2^(attempt - 1))
    delay = randomBetween(0, delay)  // full jitter

    if now + delay >= requestDeadline:
        stopRetrying

    wait(delay)

return dependencyUnavailable
~~~

Backoff giảm tần suất retry; jitter tránh nhiều client retry đồng loạt sau khi dependency phục hồi. Đặt retry budget tổng thể và giới hạn số request retry ở mọi tầng. Nếu gateway, service và SDK đều retry ba lần, một request có thể tạo nhiều lần gọi downstream hơn dự kiến.

### 6.4. Retry storm

Retry storm xảy ra khi nhiều client cùng retry dependency đang quá tải, làm tải tăng thêm và kéo dài outage. Biện pháp:
- Exponential backoff + jitter.
- Retry budget theo service/client.
- Circuit breaker.
- Rate limit và load shedding.
- Bulkhead/connection pool riêng.
- Giảm fan-out trong request critical path.
- Không retry lỗi không thể phục hồi bằng retry.

## 7. Circuit breaker, bulkhead và load shedding

### 7.1. Circuit breaker

Circuit breaker ngăn gọi một dependency liên tục khi nó đang lỗi:
- **Closed:** request được phép đi qua; theo dõi failure/latency.
- **Open:** tạm ngừng gọi dependency và trả lỗi nhanh hoặc dùng fallback đã định nghĩa.
- **Half-open:** cho một số probe giới hạn để kiểm tra dependency đã phục hồi chưa.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Failure threshold reached
    Open --> HalfOpen: Cooldown elapsed
    HalfOpen --> Closed: Probe succeeds
    HalfOpen --> Open: Probe fails
~~~

Circuit breaker không phải cache và không tự tạo fallback. Khi breaker open, caller phải có hành vi được thiết kế: dùng dữ liệu cache hợp lệ, chuyển sang provider khác đã tin cậy hoặc trả lỗi có kiểm soát. Không chuyển sang bỏ qua authentication.

### 7.2. Bulkhead

Bulkhead cô lập tài nguyên để một dependency lỗi không chiếm hết thread, connection hoặc worker của service:
- Connection pool riêng cho IdP, KMS, session store và notification.
- Giới hạn concurrent request tới MFA provider.
- Queue riêng cho email/SMS thay vì dùng chung worker với login.
- Giới hạn số tác vụ recovery nền.
- Tách critical authentication path khỏi analytics/telemetry.

Nếu SMS provider treo, worker gửi SMS không nên chiếm hết thread phục vụ password verification.

### 7.3. Load shedding

Khi quá tải, hệ thống có thể từ chối sớm request ít ưu tiên để bảo vệ chức năng cốt lõi:
- Giới hạn login attempt theo account/client/source/risk.
- Ưu tiên session validation hoặc token operations quan trọng theo policy.
- Tạm hoãn analytics và notification không thiết yếu.
- Trả 429/503 có Retry-After phù hợp.
- Không tăng tài nguyên vô hạn hoặc tiếp tục nhận request mà service không thể xử lý.

Load shedding phải công bằng và không tạo đường vòng cho attacker. Không dùng một IP đơn lẻ làm tiêu chí duy nhất vì NAT/VPN và botnet.

## 8. Cache và offline verification

Cache có thể tăng availability nhưng tạo rủi ro stale data. Cần xác định dữ liệu nào được cache, freshness window, invalidation, nguồn gốc và hành vi khi quá hạn.

### 8.1. JWKS và JWT verification

Resource server có thể xác minh JWT access token offline bằng public key đã cache. Nếu JWKS endpoint tạm lỗi:
- Dùng key cache đã lấy từ issuer tin cậy, còn trong freshness window.
- Kiểm tra signature, issuer, audience, expiry, not-before và token profile như bình thường.
- Chỉ chấp nhận key ID đã biết và key algorithm được cho phép.
- Không chấp nhận token chỉ vì JWKS fetch lỗi.
- Nếu token dùng key mới chưa có trong cache, không thể xác minh an toàn; trả lỗi tạm thời hoặc thử refresh JWKS theo policy.
- Khi cache vượt max-stale, quyết định fail-closed cho resource/action cần đảm bảo trust freshness.

JWKS cache cần xử lý key rotation. Cache quá ngắn có thể làm API phụ thuộc IdP thường xuyên; cache quá dài làm key bị thu hồi/rotation chậm được nhận biết. Định nghĩa TTL, max-stale, refresh-ahead và cách xử lý unknown kid.

### 8.2. Introspection và opaque token

Opaque access token thường cần introspection hoặc trạng thái tập trung. Nếu introspection outage:
- Cache kết quả active/inactive trong thời gian ngắn theo risk.
- Không biến timeout thành active.
- Cache inactive có thể tiếp tục từ chối trong một khoảng ngắn an toàn.
- Cache active phải có TTL phù hợp với revocation SLA.
- Với API nhạy cảm, fail-closed khi không kiểm tra được trạng thái mới nhất.

### 8.3. Account và authorization cache

Cache account status, role hoặc membership có thể khiến tài khoản đã disabled vẫn truy cập hoặc quyền đã bị thu hồi vẫn còn. Cần:
- TTL ngắn hơn với quyền nhạy cảm.
- Version/epoch để invalidate cache.
- Event-driven invalidation có retry và reconciliation.
- Recheck online cho hành động đặc quyền.
- Không dùng stale account state vô thời hạn.

### 8.4. Cache không phải nguồn chân lý

Cache là bản sao có thời hạn. Khi cache và source of truth không đồng bộ, phải biết bên nào thắng và trong bao lâu. Ghi rõ max-stale, consistency model và cách xử lý khi không thể xác minh freshness.

## 9. Availability của từng authentication dependency

### 9.1. External Identity Provider

Khi IdP ngoài outage:
- Không khởi tạo login mới qua provider đang lỗi nếu không thể xác minh callback/token.
- Dùng local passkey/password hoặc IdP dự phòng chỉ khi đã đăng ký, liên kết identity an toàn và policy cho phép.
- Cache discovery metadata/JWKS theo chuẩn và freshness policy; không dùng endpoint do client tùy ý cung cấp.
- Giữ transaction state/nonce đúng thời hạn; không replay callback sau outage.
- Không tự tạo local account mới chỉ vì provider trả lỗi.
- Thông báo trạng thái gián đoạn rõ ràng và cung cấp đường hỗ trợ phù hợp.

IdP dự phòng cần được thiết kế trước: mapping subject, account linking, assurance, MFA policy, issuer trust và account recovery. Không chuyển tự động sang một IdP khác chỉ vì nó phản hồi nhanh hơn.

### 9.2. Account database và credential store

Nếu credential database không sẵn sàng:
- Không thể xác minh password hoặc account state một cách đáng tin.
- Không dùng password hash cache cũ làm bằng chứng account vẫn active nếu policy không cho phép.
- Có thể failover sang replica đồng bộ/được kiểm soát nếu đảm bảo consistency và freshness.
- Hạn chế retry và connection pool để không làm database quá tải.
- Không cho phép login bằng một default account hoặc bypass credential verification.

Nếu database read-only nhưng đọc được dữ liệu nhất quán, một số flow chỉ đọc có thể tiếp tục; thay đổi password, enroll factor, recovery và revoke có thể phải tạm dừng.

### 9.3. MFA provider

Nếu push/SMS provider lỗi:
- Cho phép TOTP/passkey/security key đã enroll nếu policy chấp nhận.
- Không tự động bỏ qua MFA.
- Không gửi vô hạn challenge mới.
- Có rate limit, resend cooldown và thông báo trạng thái.
- Nếu factor duy nhất không khả dụng, dừng flow và dùng account recovery có xác minh.
- Không chuyển sang email link yếu hơn chỉ vì email provider đang hoạt động, trừ khi policy assurance cho phép.

Tách outage của delivery provider khỏi verifier. Ví dụ SMS gateway lỗi không nhất thiết làm TOTP verifier lỗi; passkey local có thể vẫn hoạt động.

### 9.4. Token endpoint và refresh token

Nếu token endpoint outage:
- Access token còn hạn có thể tiếp tục dùng theo audience/scope và resource server policy.
- Không kéo dài exp hoặc sửa claim ở client.
- Không gửi refresh token tới resource server.
- Dùng backoff/jitter và single-flight để tránh nhiều refresh request.
- Xử lý timeout mơ hồ theo contract của issuer, đặc biệt khi refresh token rotation.
- Khi access token hết hạn, yêu cầu retry sau hoặc login lại nếu không thể refresh an toàn.

### 9.5. Session store

Nếu session store lỗi:
- Không mặc định session không tìm thấy nghĩa là active.
- Không tạo session giả hoặc dùng session ID mặc định.
- Có thể failover sang replica/quorum theo consistency policy.
- Nếu session validation không thể hoàn tất, từ chối request cần authentication.
- Với logout, chặn local session và ghi revoke pending nếu remote store/IdP không truy cập được.
- Khi store phục hồi, đối soát session revoke, expiry và rotation để không hồi sinh phiên cũ.

### 9.6. KMS/HSM

Nếu KMS/HSM lỗi:
- Không dùng hardcoded fallback key hoặc key không rõ nguồn.
- Dừng thao tác cần decrypt/sign nếu không có key operation hợp lệ.
- Có thể tiếp tục xác minh JWT bằng public key đã cache; việc ký token mới có thể vẫn không khả dụng.
- Cache public key khác với cache private key; không export private signing key chỉ để tăng availability.
- Dùng multi-region KMS/HSM hoặc key replica theo thiết kế, có policy và audit.
- Theo dõi quota, throttling, latency và certificate/key expiry.

### 9.7. Email/SMS và account recovery

Nếu email/SMS provider outage:
- Cho phép bắt đầu recovery request và trả thông báo trung tính nếu policy cho phép.
- Không đánh dấu recovery hoàn tất trước khi proof được xác minh.
- Xếp hàng notification với TTL, retry budget và idempotency.
- Cung cấp factor recovery thay thế đã đăng ký, nếu assurance tương đương.
- Không chuyển sang support override không có xác minh độc lập.
- Giám sát queue backlog và thông báo khi delivery bị chậm.

### 9.8. Audit/event pipeline

Nếu event pipeline không sẵn sàng:
- Phát event vào durable local buffer/outbox khi có thể.
- Phân loại event bắt buộc trước commit và event telemetry có thể trễ.
- Không làm login path phụ thuộc SIEM analytics nếu event đã được ghi bền vững ở audit buffer.
- Với admin action, factor reset hoặc recovery thay đổi có rủi ro cao, cần audit durable theo policy trước commit.
- Sau phục hồi, replay và deduplicate; ghi nhận coverage gap nếu có event mất.

## 10. Degraded mode có kiểm soát

Degraded mode là chế độ vận hành được thiết kế trước cho tình huống dependency lỗi. Mỗi mode cần có:
- Trigger và điều kiện kích hoạt.
- Dependency nào đang lỗi.
- User/client/tenant/action nào được áp dụng.
- Cơ chế thay thế và assurance tương đương.
- Thời gian tối đa và điều kiện tự tắt.
- Audit event cho việc kích hoạt/tắt.
- Owner có quyền phê duyệt.
- Metric để theo dõi số người dùng và hành động bị ảnh hưởng.

Ví dụ:
- External IdP A outage: cho phép local passkey login đối với account đã liên kết và policy đã xác nhận.
- Push provider outage: cho phép TOTP hoặc security key đã enroll; không bỏ MFA.
- Token endpoint outage: chỉ tiếp tục API request bằng access token chưa hết hạn.
- Notification provider outage: queue notification; không bỏ recovery proof.
- Analytics outage: tắt dashboard enrichment; giữ audit event bền vững.

Không để degraded mode chạy vô thời hạn. Đặt expiry/lease và yêu cầu re-evaluation. Khi dependency phục hồi, chuyển về normal mode và xác minh mọi trạng thái phát sinh trong degraded mode.

## 11. Circuit breaker và fallback không được tạo bypass

Fallback phải được đánh giá theo mức assurance và authorization. Ví dụ:
- Passkey có thể là fallback tốt nếu đã enroll và RP ID/origin/challenge validation vẫn đầy đủ.
- TOTP có thể là fallback nếu factor đã enroll và policy chấp nhận, nhưng không tương đương mọi mức phishing resistance.
- Email recovery link thường không tương đương MFA mạnh.
- SMS OTP có rủi ro SIM swap và không nên tự động thay thế factor chống phishing.
- Admin break-glass account cần bảo vệ riêng, phê duyệt, thời hạn, MFA và audit độc lập.

Một fallback chỉ hợp lệ nếu nó đã được thiết kế, đăng ký, kiểm thử và policy chấp nhận trước outage. Không tạo phương thức xác thực mới trong lúc incident mà chưa đánh giá rủi ro.

## 12. Multi-region, failover và consistency

Multi-region có thể tăng availability nhưng tạo bài toán consistency:
- Session store có thể replication asynchronous; revoke ở region A chưa đến region B.
- Token family state có thể bị ghi đồng thời ở hai region.
- KMS key replica cần cùng trust policy và audit.
- DNS failover có thể chuyển client tới region có state cũ.
- IdP callback/redirect URI phải được đăng ký cho endpoint failover.
- Clock skew giữa region ảnh hưởng expiry, TOTP và certificate validation.

### 12.1. Active-active và active-passive

| Mô hình | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- |
| Active-active | Phục vụ nhiều region, chịu lỗi một vùng tốt hơn | Conflict, replication lag, token/session state consistency phức tạp. |
| Active-passive | Mô hình write owner rõ hơn, dễ kiểm soát một số state | Failover có thể lâu; standby phải được cập nhật và kiểm thử. |
| Regional isolation | Giới hạn blast radius theo tenant/region | Người dùng di chuyển region có thể cần routing/session strategy rõ. |

Không chọn active-active chỉ vì muốn “HA”. Với refresh token rotation, recovery code consume và session revoke, cần atomicity hoặc consistency guarantees phù hợp để tránh token bị dùng hai lần ở hai region.

### 12.2. Revocation consistency

Đối với session/token revoke:
- Định nghĩa maximum revocation propagation delay.
- Dùng version/epoch hoặc revocation event có thể đối soát.
- Xác định failover region có thể chấp nhận stale state trong bao lâu.
- Với admin/high-risk API, có thể cần online check hoặc fail-closed nếu state không fresh.
- Sau failover, đối soát revoke/rotation trước khi nhận toàn bộ traffic.

Availability không có nghĩa chấp nhận credential đã bị thu hồi vô thời hạn.

## 13. SLO, SLI, error budget, RTO và RPO

### 13.1. SLI/SLO

Không dùng một SLO duy nhất cho mọi authentication flow. Đo riêng:
- Login success availability, loại trừ credential sai của người dùng.
- MFA challenge/verification availability theo factor.
- Token endpoint success rate và latency.
- Session validation availability.
- Logout/revocation propagation latency.
- Account recovery completion availability.
- Audit event durability/ingestion latency.

Một SLI cần định nghĩa numerator, denominator, exclusion, measurement window và source. Ví dụ login availability không nên tính password sai là outage; nhưng timeout do credential database phải tính là dependency failure.

### 13.2. Error budget

Error budget biểu thị mức lỗi cho phép trong SLO window. Khi budget bị tiêu hao nhanh:
- Hạn chế release thay đổi auth critical path.
- Ưu tiên reliability work.
- Giảm retry amplification và fan-out.
- Tạm hoãn tính năng không thiết yếu.
- Review dependency provider và capacity.

Không dùng error budget để hợp thức hóa bỏ qua kiểm tra bảo mật. SLO availability và security policy là hai ràng buộc cần cùng đáp ứng.

### 13.3. RTO và RPO

- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau outage.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất theo thời gian khi khôi phục.

Với authentication, RPO đặc biệt quan trọng cho:
- Password/credential changes.
- Factor enrollment/removal.
- Session/token revocation.
- Recovery code consumption.
- Refresh token rotation lineage.
- Audit record của hành động đặc quyền.

Nếu restore database từ snapshot cũ làm sống lại refresh token đã revoke hoặc recovery code đã dùng, hệ thống có thể mở lại quyền truy cập. Cần revocation ledger hoặc reconciliation với state có thẩm quyền sau restore.

## 14. Monitoring và alert cho dependency outage

Theo dõi cả dependency và tác động lên authentication flow:
- Availability, latency p50/p95/p99 và error rate của mỗi dependency.
- Connection pool, thread pool, queue depth, retry count và circuit breaker state.
- DNS resolution, TLS handshake, certificate expiry và clock drift.
- KMS/HSM quota, throttling, sign/decrypt latency.
- IdP/JWKS/token endpoint failure và key cache age.
- MFA delivery delay, challenge failure và resend count.
- Session store read/write/revoke error và replication lag.
- Refresh success, invalid_grant, reuse detection và token endpoint timeout.
- Audit event drop, queue backlog và end-to-end durability.
- Tỷ lệ login/recovery bị ảnh hưởng theo region, client, tenant và auth method.

Alert nên phản ánh tác động. Ví dụ, “MFA SMS provider latency tăng” hữu ích hơn “login success giảm” nếu có thể xác định dependency. Alert cần owner, severity, runbook và điều kiện clear. Tránh tạo một alert cho mỗi request lỗi; aggregate theo service, region và time window.

## 15. Incident response khi dependency outage

Một quy trình phản ứng điển hình:

1. **Detect:** xác nhận SLI/alert và phạm vi lỗi.
2. **Triage:** xác định dependency, flow, region, tenant và user impact.
3. **Contain:** giảm retry, mở circuit breaker, load shed hoặc cô lập dependency lỗi.
4. **Choose mode:** áp dụng degraded mode đã phê duyệt; không bỏ kiểm tra bảo mật.
5. **Communicate:** thông báo đúng phạm vi, trạng thái và hướng xử lý cho người dùng/đội vận hành.
6. **Recover:** failover hoặc phục hồi dependency theo runbook.
7. **Reconcile:** đối soát token rotation, session revoke, recovery state, event buffer và transaction chưa rõ kết quả.
8. **Validate:** kiểm tra login, MFA, token, session, logout, recovery và audit.
9. **Close:** tắt degraded mode, đóng breaker có kiểm soát, cập nhật status page và lưu timeline.
10. **Learn:** post-incident review, root cause, contributing factors và action items.

### 15.1. Không làm tình hình xấu hơn

Trong incident:
- Không tăng retry count chỉ để “thử thêm”.
- Không tắt MFA hoặc signature validation để khôi phục login.
- Không thay signing key thủ công nếu chưa hiểu key trust/rotation.
- Không failover sang database replica có thể thiếu revocation state mà không đánh giá.
- Không xóa queue/dead-letter trước khi lưu evidence.
- Không tuyên bố remote logout/revoke thành công nếu mới chỉ xóa local state.
- Không tắt audit cho hành động đặc quyền nếu chưa có phương án thay thế được phê duyệt.

### 15.2. Phục hồi sau outage

Sau khi dependency trở lại:
- Tăng traffic dần, theo dõi error rate và saturation.
- Kiểm tra circuit breaker half-open/closed đúng trạng thái.
- Drain queue có giới hạn để tránh gây tải đột biến.
- Replay event và deduplicate.
- Đối soát trạng thái token/session/recovery với nguồn chân lý.
- Làm mới cache có kiểm soát và kiểm tra key rotation.
- Xác nhận retry pending không tạo tác dụng phụ lặp.
- Tắt degraded mode và ghi event về việc chuyển trạng thái.
- Kiểm tra user/account bị khóa tạm hoặc cần re-authentication.

## 16. Bài thực hành: Dependency outage tại StudyHub

**Bối cảnh:** StudyHub có web app và mobile app, Identity Service, Account DB, Session Store, Token Service, MFA Service, External IdP, KMS/HSM và Audit Pipeline. Access token JWT sống 10 phút; refresh token rotation bật. Một số tài khoản quản trị bắt buộc MFA. Course API xác minh JWT bằng JWKS cache; một số API quản trị dùng introspection để kiểm tra trạng thái token/session mới nhất.

Trong một incident giả định:
- External IdP chậm và thỉnh thoảng timeout.
- MFA push provider không gửi challenge đúng hạn.
- Token endpoint tăng 5xx.
- Session Store có replication lag giữa hai region.
- Audit pipeline backlog tăng.
- KMS/HSM vẫn hoạt động nhưng latency cao.

### 16.1. Nhiệm vụ thiết kế

Hãy xác định:
1. Dependency nào nằm trong critical path của từng login flow.
2. Người dùng đăng nhập local bằng passkey có bị ảnh hưởng bởi External IdP không.
3. Người dùng đang có access token còn hạn có tiếp tục gọi Course API được không.
4. Course API dùng JWKS cache xử lý thế nào nếu endpoint JWKS không phản hồi.
5. API quản trị dùng introspection xử lý ra sao khi Token Service timeout.
6. MFA push provider lỗi thì factor thay thế nào được phép dùng.
7. Refresh token timeout có thể gây rotation ambiguity ra sao.
8. Session Store replication lag ảnh hưởng logout/revocation ở region khác thế nào.
9. Audit event nào phải durable trước khi admin thay recovery factor.
10. KMS latency cao thì request nào được timeout/circuit-break và request nào có thể chờ.
11. Degraded mode nào được kích hoạt, owner và expiry ra sao.
12. RTO/RPO và SLO nào cần đo trong incident.

### 16.2. Bảng quyết định degraded mode

Điền một bảng tương tự:

| Dependency lỗi | Flow bị ảnh hưởng | Fallback được phép | Hành động phải từ chối | Max degraded window |
| --- | --- | --- | --- | --- |
| External IdP | SSO login | Local passkey đã đăng ký và policy cho phép | Không bỏ callback/issuer/signature validation | Theo IdP recovery policy |
| Push MFA | MFA challenge | TOTP/security key đã enroll | Không bỏ MFA bắt buộc | Theo risk policy |
| Token endpoint | Refresh | Dùng access token còn hạn | Không kéo dài expiry hoặc replay refresh token mơ hồ | Tới access token expiry |
| Session Store | Session validation/revoke | Replica/cache trong freshness bound | Không coi session unknown là active | Theo revocation SLA |
| KMS/HSM | Sign/decrypt | Public-key verification cache nếu hợp lệ | Không dùng key mặc định hoặc bỏ ký | Theo key operation policy |
| Audit pipeline | Audit/telemetry | Durable outbox cho event critical | Không commit privileged action nếu audit bắt buộc chưa durable | Theo audit SLO |

### 16.3. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| External IdP timeout | SSO flow dừng an toàn; local auth chỉ hoạt động nếu đã cấu hình. |
| MFA push provider outage | Factor thay thế đã enroll có thể dùng theo policy; không tự bỏ MFA. |
| Token endpoint 503 | Retry có backoff/jitter; access token còn hạn vẫn theo policy. |
| Refresh timeout sau khi server có thể rotate | Client không blind-retry refresh token cũ. |
| JWKS endpoint outage với key cache còn fresh | JWT được xác minh bình thường bằng key đã tin cậy. |
| JWT có kid chưa biết khi JWKS outage | Không chấp nhận token; trả lỗi tạm thời phù hợp. |
| JWKS cache vượt max-stale | Hành động yêu cầu trust freshness fail-closed. |
| Introspection outage | Không mặc định opaque token active; cache/fail-closed theo policy. |
| Session Store một region partition | Không tạo session giả; revoke propagation lag được cảnh báo. |
| Logout khi remote revoke unavailable | Local session bị chặn; remote revoke pending được ghi nhận. |
| KMS throttling | Circuit breaker/timeout bảo vệ runtime; không fallback key hardcoded. |
| Audit queue đầy | Event critical được buffer hoặc hành động đặc quyền bị chặn theo policy. |
| Analytics pipeline outage | Login path không bị phụ thuộc vào analytics không thiết yếu. |
| Retry storm | Backoff, jitter, retry budget và load shedding giới hạn amplification. |
| Dependency phục hồi | Traffic tăng dần; queue replay không tạo tải đột biến. |
| Restore snapshot cũ | Token/session/recovery đã revoke hoặc consumed không bị hồi sinh. |
| Degraded mode hết hạn | Tự tắt hoặc yêu cầu re-approval; event chuyển trạng thái được audit. |
| Admin action trong outage | Actor được xác minh và audit durable theo policy; nếu không thì từ chối. |
| Multi-region token rotation | Một refresh token không được chấp nhận đồng thời ở hai region trái policy. |
| Clock skew | Token/TOTP/certificate validation dùng thời gian đáng tin và phát hiện drift. |

### 16.4. Câu hỏi tự đánh giá

1. Vì sao dependency outage có thể làm giảm security chứ không chỉ availability?
2. Fail-closed khác graceful degradation như thế nào?
3. Khi nào một JWT resource server có thể tiếp tục hoạt động dù IdP outage?
4. Vì sao opaque token introspection timeout không nên mặc định là active?
5. Refresh token rotation tạo vấn đề gì khi response bị mất?
6. Circuit breaker khác retry và cache ở điểm nào?
7. Retry storm hình thành ra sao và jitter giúp gì?
8. Vì sao session revocation cần consistency giữa các region?
9. Tại sao không nên tự động bỏ MFA khi provider chính lỗi?
10. KMS/HSM outage có thể ảnh hưởng sign và verify khác nhau thế nào?
11. Audit event nào cần durable trước khi thực hiện admin action?
12. RTO và RPO ảnh hưởng credential lifecycle như thế nào?
13. Sau khi restore backup, cần đối soát những trạng thái nào để tránh hồi sinh token?
14. Làm thế nào kiểm thử degraded mode mà không làm giảm kiểm soát production?

**Tiêu chí hoàn thành:** Người học có thể lập dependency graph theo flow, phân loại criticality và failure mode, chọn timeout/retry/circuit breaker/cache/fallback đúng, giải thích fail-open/fail-closed, định nghĩa SLO/RTO/RPO và thiết kế recovery có đối soát để hệ thống không cấp quyền trái phép hoặc hồi sinh credential đã thu hồi.

## 17. Các lỗi thiết kế phổ biến

- **Một timeout quá dài cho mọi dependency:** request treo và giữ cạn tài nguyên.
- **Retry không giới hạn:** tạo retry storm và khuếch đại outage.
- **Mọi tầng đều retry:** một request sinh nhiều request downstream ngoài dự tính.
- **Fail-open cho MFA hoặc token validation:** dependency outage trở thành bypass authentication.
- **Dùng cache vô thời hạn:** account disabled hoặc token revoked vẫn được chấp nhận.
- **Cache JWKS không có max-stale:** key cũ có thể được tin quá lâu.
- **Introspection timeout mặc định active:** không xác minh được trạng thái nhưng vẫn cấp quyền.
- **Circuit breaker không có fallback policy:** breaker open nhưng caller vẫn xử lý sai.
- **Fallback sang factor yếu hơn không được phê duyệt:** giảm assurance trong lúc incident.
- **Không single-flight refresh:** nhiều request cùng dùng refresh token cũ.
- **Failover sang replica stale:** token/session đã revoke có thể sống lại.
- **Không đối soát sau restore:** recovery code đã dùng hoặc token đã revoke được phục hồi.
- **Dùng KMS key hardcoded khi KMS lỗi:** tạo trust root không được quản lý.
- **Dùng chung pool cho notification và login:** một provider chậm làm cạn tài nguyên authentication.
- **Không đo revocation propagation:** logout thành công ở một node nhưng nơi khác vẫn nhận token.
- **Audit phụ thuộc SIEM online:** outage analytics làm mất bằng chứng của privileged action.
- **Degraded mode không có expiry:** tạm thời trở thành cấu hình yếu kéo dài.
- **Không kiểm thử partial failure:** chỉ test service down hoàn toàn, bỏ qua timeout, lag và split brain.

## 18. Vận hành và cải tiến độ tin cậy

Sau mỗi outage, cần review:
- Dependency graph có phản ánh đúng critical path không?
- Timeout budget có hợp lý không?
- Retry amplification có làm tăng tải không?
- Circuit breaker mở/đóng có đúng không?
- Cache freshness và revocation SLA có đáp ứng không?
- Degraded mode có giữ assurance không?
- Có event loss hoặc audit gap không?
- RTO/RPO có đạt không?
- Failover có tạo state conflict không?
- Runbook có đủ thông tin và owner không?
- Người dùng nhận thông báo chính xác không?
- Có action item giảm blast radius hoặc dependency count không?

Ưu tiên loại bỏ dependency không cần thiết khỏi critical path, giảm fan-out, tách workload, dùng provider redundancy đã kiểm thử và tự động hóa reconciliation. Thêm một provider dự phòng cũng tạo thêm credential, trust relationship, contract, quota và failure mode; cần đánh giá tổng thể thay vì chỉ đếm số nhà cung cấp.

## 19. Tài liệu tham khảo và hướng đọc tiếp

- **Google SRE Workbook / Site Reliability Engineering:** SLI, SLO, error budget, incident response và graceful degradation.
- **AWS Well-Architected Reliability Pillar:** fault isolation, retry with backoff, health checks và recovery.
- **Microsoft Azure Well-Architected Reliability:** availability zones, circuit breaker, retry và failover.
- **OWASP Authentication Cheat Sheet:** authentication controls và xử lý credential.
- **OWASP OAuth 2.0 Cheat Sheet:** token handling, validation và refresh token protection.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** token endpoint và refresh grant.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation semantics.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái token.
- **OpenID Connect Core:** discovery, JWKS và identity provider flow.
- **NIST SP 800-34 — Contingency Planning Guide:** contingency, recovery planning và testing.
- **Cloud KMS/HSM provider reliability documentation:** regional availability, key replication, quota và disaster recovery.

Khi triển khai thật, hãy kiểm tra semantics của framework, IdP, KMS và cloud provider cụ thể. Fallback, cache TTL, timeout và SLO phải dựa trên threat model, dữ liệu đo được và policy của sản phẩm; ví dụ trong bài là điểm bắt đầu để thiết kế, không phải cấu hình production áp dụng máy móc.

**Kết luận:** Dependency outage là bài toán đồng thời về availability và security. Hệ thống xác thực bền vững cần biết dependency nào nằm trong critical path, đặt timeout/retry có giới hạn, cô lập lỗi, dùng cache có freshness bound, chỉ degraded theo policy đã phê duyệt và giữ khả năng revoke credential. Khi phục hồi, phải đối soát session, token, recovery state và audit event trước khi coi hệ thống đã trở lại bình thường.
