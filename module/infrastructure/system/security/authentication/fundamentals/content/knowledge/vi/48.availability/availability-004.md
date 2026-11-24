# Fail-open và fail-closed

## 1. Fail-open và fail-closed là gì?

**Fail-open** và **fail-closed** mô tả cách hệ thống xử lý request khi không thể hoàn tất một bước kiểm tra hoặc dependency bảo mật không hoạt động.

- **Fail-open:** hệ thống tiếp tục cho request đi qua khi không thể xác minh đầy đủ điều kiện.
- **Fail-closed:** hệ thống từ chối hoặc tạm dừng request khi không thể xác minh điều kiện bắt buộc.

Trong authentication, ví dụ fail-open là API gateway không liên lạc được với session store nhưng vẫn cho request truy cập vì “có vẻ đã đăng nhập”. Ví dụ fail-closed là gateway từ chối request được bảo vệ vì không thể kiểm tra session hoặc token status.

Hai cách xử lý có tác động khác nhau đến confidentiality, integrity, availability và safety. Fail-open có thể giữ dịch vụ hoạt động nhưng mở đường cho truy cập trái phép. Fail-closed giữ ranh giới bảo mật nhưng có thể khiến người dùng hợp lệ không đăng nhập hoặc không hoàn thành giao dịch.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, fail-open và fail-closed liên quan tới password verification, MFA, passkey, certificate, session, token introspection, revocation, authorization policy và service-to-service authentication. Thiết kế đúng không chỉ chọn một chế độ cho toàn hệ thống; nó xác định kiểm tra nào là bắt buộc, lỗi nào có thể được xử lý bằng dữ liệu cache đáng tin cậy, hành động nào cần dừng và phạm vi degraded mode được giới hạn ra sao.

Sau bài học, người học có thể:

- Giải thích fail-open và fail-closed trong authentication.
- Phân biệt lỗi xác minh với credential không hợp lệ.
- Đánh giá tác động bảo mật và availability theo từng endpoint/action.
- Xác định dependency nào là security-critical.
- Thiết kế cache, timeout, circuit breaker và retry an toàn.
- Đặt giới hạn freshness cho session, revocation và policy data.
- Xây dựng degraded mode có phạm vi, thời hạn và audit rõ.
- Tránh fail-open do lỗi session store, IdP, JWKS, MFA hoặc policy engine.
- Theo dõi outage, fallback, stale decision và security correctness.
- Kiểm thử failure mode, recovery và failover trước khi production.

## 2. Security decision cần bằng chứng đáng tin cậy

Một request được bảo vệ thường cần nhiều bước:
1. Xác minh credential hoặc session.
2. Xác định principal, client, actor và tenant.
3. Kiểm tra issuer, audience, expiry, signature hoặc session state.
4. Đánh giá authentication context, assurance và freshness.
5. Đánh giá authorization cho resource/action.
6. Thực hiện hành động và ghi audit.

Nếu một bước bắt buộc không thể đưa ra quyết định đáng tin, hệ thống phải xác định có thể dùng bằng chứng đã cache hay không, có thể yêu cầu retry/step-up không hoặc phải từ chối.

~~~mermaid
flowchart TD
    A[API request] --> B[Verify credential or session]
    B --> C{Evidence valid and fresh?}
    C -- No --> X[Deny / reauthenticate]
    C -- Yes --> D[Resolve principal and context]
    D --> E[Evaluate authorization]
    E --> F{Decision available and valid?}
    F -- No --> Y[Fail-safe outcome]
    F -- Yes --> G{Permit?}
    G -- No --> X
    G -- Yes --> H[Execute action]
    H --> I[Audit result]
~~~

Không được nhầm lẫn hai trường hợp:
- Credential được xác minh và kết luận không hợp lệ.
- Hệ thống không thể xác minh vì dependency lỗi hoặc timeout.

Cả hai có thể dẫn tới deny, nhưng reason code, metric, thông báo và cách điều tra phải khác nhau. Timeout của IdP không chứng minh password sai; ngược lại, timeout cũng không phải lý do để coi password đúng.

## 3. Fail-open không đồng nghĩa graceful degradation

Graceful degradation là giảm một phần chức năng để hệ thống tiếp tục cung cấp những dịch vụ vẫn có thể vận hành an toàn. Fail-open là bỏ qua một điều kiện kiểm soát khi không xác minh được.

Ví dụ graceful degradation:
- Khi hệ thống risk scoring lỗi, API vẫn cho đọc nội dung ít nhạy cảm nếu authentication và authorization cơ bản đã được xác minh, nhưng tạm dừng thay đổi recovery method.
- Khi email notification provider lỗi, hệ thống vẫn ghi nhận recovery request và đưa notification vào queue, nhưng chưa hoàn tất thay đổi email.
- Khi dashboard metrics lỗi, authentication vẫn hoạt động vì metrics không nằm trên đường quyết định quyền.

Ví dụ fail-open:
- Session store lỗi nhưng API chấp nhận mọi request có cookie bất kỳ.
- Policy engine timeout nhưng gateway mặc định permit.
- Không lấy được JWKS nên verifier chấp nhận JWT mà không kiểm tra chữ ký.
- MFA provider không phản hồi nhưng hệ thống coi challenge đã thành công.

Graceful degradation giữ nguyên các điều kiện bảo mật cốt lõi và giảm chức năng ở phần có thể trì hoãn. Không dùng thuật ngữ này để che một quyết định fail-open.

## 4. Fail-closed cũng cần được thiết kế

Fail-closed không có nghĩa mọi lỗi trong toàn hệ thống đều phải làm toàn bộ ứng dụng ngừng hoạt động. Nó có nghĩa request không được thực hiện khi điều kiện bảo mật bắt buộc chưa được xác minh.

Có thể:
- Từ chối một action nhạy cảm nhưng vẫn cho phép người dùng xem trang trợ giúp.
- Cho phép đọc dữ liệu công khai nhưng dừng truy cập dữ liệu cá nhân.
- Giữ một session đã xác minh trong thời gian cache được policy cho phép, nhưng từ chối khi cache quá hạn.
- Trả trạng thái retryable khi IdP hoặc policy service tạm thời lỗi.
- Queue một thao tác có thể trì hoãn nhưng không thực hiện side effect trước khi authorization hoàn tất.

Fail-closed cần timeout hợp lý, thông báo rõ ràng và đường khôi phục. Nếu chỉ trả lỗi 500 không phân biệt, người dùng không biết nên thử lại, đăng nhập lại hay liên hệ hỗ trợ. Nếu mọi request đều retry vô hạn, hệ thống có thể tạo retry storm và làm outage nặng hơn.

## 5. Phân loại dependency theo vai trò bảo mật

Không phải mọi dependency đều cần cùng chế độ lỗi. Phải biết dependency đang cung cấp bằng chứng gì và điều gì xảy ra nếu bằng chứng đó không có.

| Dependency | Vai trò | Khi lỗi cần cân nhắc |
| --- | --- | --- |
| Password verifier/database | Kiểm tra password và trạng thái credential | Không thể xác minh password thì không tạo session |
| Identity Provider | Xác thực/federation và phát assertion/token | Không giả định login thành công; dùng session đã có chỉ theo policy |
| JWKS endpoint | Cung cấp public key xác minh chữ ký | Dùng key cache còn tin cậy trong freshness policy hoặc từ chối |
| Session store | Tra session, TTL, revoke và state | Không chấp nhận session không thể xác minh |
| Token introspection | Kiểm tra opaque token active/revoked | Chỉ dùng cached result trong giới hạn rõ; quá hạn thì deny |
| MFA provider | Gửi hoặc xác minh factor | Không coi timeout là factor success |
| Risk engine | Cung cấp risk signal | Có thể dùng degraded policy theo action và baseline |
| Authorization PDP | Quyết định quyền | Không permit khi không có decision đáng tin |
| Membership/tenant service | Xác minh quan hệ principal-tenant | Không truy cập dữ liệu tenant nếu membership không xác minh được |
| Audit pipeline | Lưu bằng chứng hành động | Có thể buffer theo thiết kế; action quan trọng có thể cần durable audit trước commit |
| Metrics/dashboard | Quan sát vận hành | Có thể giảm observability; không thay quyết định authentication |
| Email/SMS notification | Gửi thông báo hoặc OTP | Không hoàn tất action yêu cầu xác minh nếu delivery/verification chưa xong |
| Secret manager/HSM | Cung cấp signing/decryption key | Không tự tạo key thay thế hoặc bỏ chữ ký khi key không khả dụng |

### 5.1. Security-critical và operational dependency

Security-critical dependency cung cấp dữ liệu cần thiết để xác minh identity hoặc quyền. Operational dependency hỗ trợ giám sát, hiển thị hoặc thông báo nhưng không nhất thiết nằm trên đường cho phép request.

Ví dụ, metrics backend bị lỗi không nên làm gateway bỏ xác minh token. Ngược lại, session store lỗi có thể khiến server không biết session đã bị revoke, vì vậy cần chặn những request phụ thuộc vào trạng thái đó.

### 5.2. Dependency graph

Vẽ dependency graph để biết failure lan tới đâu. Một login flow có thể phụ thuộc vào password database, rate limiter, MFA provider, session store, signing key và audit pipeline. Một API request có thể phụ thuộc vào JWT verifier, JWKS cache, policy engine, membership service và data store.

Đánh giá từng dependency theo:
- Security decision nào phụ thuộc vào nó?
- Có thể xác minh bằng dữ liệu đã cache không?
- Cache có expiry/version/revocation không?
- Mức stale tối đa chấp nhận được là bao lâu?
- Action nào phải dừng khi dependency lỗi?
- Có thể queue hoặc retry an toàn không?
- Có nguy cơ retry storm hoặc failover split-brain không?

## 6. Ma trận quyết định theo action và rủi ro

Một ứng dụng có nhiều loại endpoint. Chọn fail behavior theo tác động nếu request bị cho phép sai và tác động nếu request hợp lệ bị từ chối.

| Action | Ví dụ | Failure policy thường phù hợp |
| --- | --- | --- |
| Nội dung public | Đọc trang trợ giúp | Có thể tiếp tục nếu không cần identity |
| Đọc dữ liệu cá nhân | Xem hồ sơ hoặc hóa đơn | Cần authentication và authorization đã xác minh |
| Cập nhật hồ sơ | Đổi địa chỉ hoặc tùy chọn | Từ chối nếu session/policy không xác minh được |
| Thay đổi credential | Đổi password, thêm passkey/MFA | Fail-closed và reauthentication khi cần |
| Thay đổi recovery | Đổi email/phone khôi phục | Fail-closed, step-up và notification policy |
| Thanh toán/chuyển tiền | Tạo giao dịch | Fail-closed với transaction authorization |
| Quản trị quyền | Cấp role hoặc revoke access | Fail-closed và audit bền vững |
| Service-to-service write | Reserve stock hoặc cập nhật ledger | Fail-closed nếu workload identity/authorization không xác minh được |
| Telemetry | Gửi metrics không nhạy cảm | Có thể buffer/drop theo policy; không mở quyền |
| Notification | Gửi email cảnh báo sau action | Có thể queue sau khi action đã commit nếu policy cho phép |

Không áp dụng bảng này máy móc. Một endpoint đọc dữ liệu cũng có thể rất nhạy cảm; một action nội bộ có thể ảnh hưởng trực tiếp tới tiền hoặc quyền. Phân loại dựa trên threat model và business impact.

### 6.1. Fail behavior theo mức độ nhạy cảm

Có thể xác định ba nhóm:
- **Low impact:** có thể dùng cache hoặc degraded mode với freshness giới hạn.
- **Sensitive:** cần bằng chứng hiện tại hoặc cache rất ngắn, có kiểm tra bổ sung.
- **Critical:** cần online verification hoặc bằng chứng mới; dependency bắt buộc lỗi thì từ chối.

Ghi rõ nhóm và owner của policy. Không để mỗi service tự suy diễn cách xử lý outage.

## 7. Session store unavailable

Server-side session thường cần session store để tra session state, idle expiry, revoke và principal binding. Nếu store timeout hoặc unavailable, hệ thống không biết cookie đang gửi có đại diện cho session hợp lệ hay không.

Các phản ứng nguy hiểm:
- Nếu không tìm thấy session thì tự tạo session mới từ cookie.
- Chấp nhận mọi cookie có định dạng đúng.
- Dùng principal ID do client gửi thay session lookup.
- Bỏ qua revoke check vì Redis không phản hồi.
- Coi lỗi store là session hợp lệ để tránh làm người dùng logout.

Thiết kế an toàn:
1. Đặt timeout ngắn, có giới hạn cho session lookup.
2. Phân biệt not found, expired, revoked và store unavailable.
3. Không tạo authenticated session nếu lookup không thể hoàn tất.
4. Với thao tác nhạy cảm, không dùng stale session state ngoài policy.
5. Có thể dùng cache session đã xác minh trong thời gian tối đa được định nghĩa nếu cache có integrity và revoke freshness phù hợp.
6. Từ chối request sau khi cache hết freshness.
7. Hiển thị lỗi tạm thời hoặc yêu cầu retry, không báo password sai.
8. Theo dõi store error, cache age và request bị từ chối do dependency.

### 7.1. Cache session và giới hạn stale

Cache có thể giữ snapshot session đã xác minh để giảm phụ thuộc vào store. Nhưng snapshot có thể không biết logout hoặc revoke mới xảy ra.

Cần quy định:
- TTL tối đa.
- Invalidation channel.
- Version hoặc revoke epoch.
- Behavior khi event invalidation bị mất.
- Kiểm tra online cho action critical.
- Maximum stale window được risk owner chấp thuận.

Không gọi cache là source of truth nếu nó có thể chấp nhận session revoked lâu hơn policy.

## 8. Token introspection và JWT/JWKS outage

### 8.1. Opaque token introspection

Resource server có thể gọi authorization server để kiểm tra token active, expiry, scope và principal. Nếu introspection endpoint lỗi:
- Không coi token active chỉ vì request trước đó thành công.
- Có thể dùng cached introspection result trong TTL được giới hạn.
- Cache key phải gắn với token reference, issuer và audience.
- Không cache active vô thời hạn.
- Từ chối khi cache quá hạn hoặc token bị biết là revoked.
- Dùng circuit breaker để tránh dồn request vào authorization server đang lỗi.

Với action nhạy cảm, có thể yêu cầu introspection online hoặc cache cực ngắn. Với action ít rủi ro, policy có thể chấp nhận cache trong cửa sổ được phê duyệt, nhưng phải đo stale acceptance.

### 8.2. JWT và JWKS unavailable

JWT có chữ ký có thể được xác minh cục bộ bằng public key đã cache. JWKS endpoint tạm thời lỗi không nhất thiết làm mọi token lập tức không thể xác minh, nếu verifier đã có key đúng từ issuer tin cậy và cache còn trong policy.

Cần:
- Chỉ dùng key đã lấy từ issuer/JWKS URI tin cậy.
- Cache key theo kid và issuer.
- Kiểm tra cache age và key status policy.
- Không tải key từ jku/x5u tùy ý trong token.
- Không chấp nhận thuật toán hoặc key không được allowlist.
- Khi gặp kid mới và không lấy được JWKS, từ chối token cần key chưa biết.
- Không chấp nhận token chỉ vì payload decode được.

### 8.3. Key rotation trong outage

Nếu issuer xoay signing key trong khi verifier không thể lấy JWKS mới, token ký bằng key mới có thể bị từ chối. Token ký bằng key cũ chỉ được chấp nhận nếu key cũ vẫn nằm trong trust set và còn trong rotation overlap policy.

Không giữ key cũ vô hạn để tránh login failure. Điều đó làm mất khả năng thu hồi key bị compromise. Đặt maximum stale period và quy trình emergency key revoke.

## 9. Identity Provider outage và federation

Khi IdP không khả dụng:
- Không hoàn tất login mới bằng cách tự tin vào callback chưa được xác minh.
- Không bỏ kiểm tra signature, issuer, audience, state, nonce hoặc redirect binding.
- Có thể giữ session RP hiện tại nếu session đó vẫn hợp lệ theo local policy.
- Không tự gia hạn session vô hạn chỉ vì IdP outage.
- Khi session hết hạn, cung cấp trạng thái retryable hoặc fallback đã được phê duyệt.
- Với account có credential local độc lập, có thể cung cấp phương thức login thay thế nếu policy cho phép và không làm yếu assurance.

### 9.1. Session đã xác minh trước đó

Một RP có thể duy trì session đã được tạo từ lần federation thành công trước đó. IdP outage không nhất thiết phải đăng xuất mọi user ngay lập tức. Nhưng cần xem xét:
- Local session expiry.
- Absolute lifetime.
- Revocation/logout event propagation.
- Account disable hoặc credential compromise.
- Risk/action hiện tại.
- Yêu cầu reauthentication/step-up.

Nếu RP không nhận được IdP logout hoặc account disable event, có thể còn session stale. Định nghĩa maximum stale window và kiểm tra trạng thái cho action critical.

### 9.2. Break-glass account

Một số hệ thống cần tài khoản khẩn cấp độc lập với IdP để khôi phục vận hành. Break-glass không phải bypass thông thường:
- Credential lưu và kiểm soát riêng.
- Số lượng rất hạn chế.
- MFA mạnh và access scope tối thiểu.
- Chỉ dùng theo incident procedure.
- Có dual control/approval khi khả thi.
- Alert tức thời khi sử dụng.
- Audit bất biến và review sau incident.
- Rotate credential sau khi sử dụng.

Không để break-glass password trong runbook hoặc shared log.

## 10. MFA provider unavailable

Nếu SMS, email, push hoặc external MFA provider không hoạt động, timeout không phải bằng chứng factor thành công.

Hành vi phù hợp:
- Không cấp session hoặc step-up grant nếu factor chưa được xác minh.
- Cho phép retry có giới hạn.
- Cung cấp authenticator khác đã đăng ký và được policy chấp nhận.
- Cho phép recovery flow riêng với proofing phù hợp.
- Không tự hạ từ phishing-resistant MFA xuống SMS chỉ vì provider lỗi.
- Không hiển thị chi tiết account/factor cho người chưa xác minh.
- Theo dõi provider outage và factor-specific failure.

### 10.1. TOTP khác external delivery

TOTP có thể được xác minh cục bộ bởi server nếu secret và clock window sẵn sàng; không phụ thuộc SMS gateway. Tuy nhiên, nếu database chứa TOTP secret hoặc key-encryption service unavailable, không thể coi code là hợp lệ. Cần kiểm tra clock skew và replay counter theo policy.

### 10.2. Push fatigue và timeout

Timeout của push challenge có nghĩa chưa nhận được kết quả trong thời gian cho phép. Không coi timeout là approve. Nếu user nhận nhiều prompt do retry, cần rate limit và hiển thị transaction context để tránh push fatigue.

## 11. Authorization policy engine unavailable

PDP quyết định request có được phép thực hiện không. Nếu PDP lỗi, PEP không nên tự cho phép vì principal đã authenticated.

Các lựa chọn:
- Từ chối action cần PDP.
- Dùng decision cache có policy version, context binding và TTL.
- Cho phép một tập action public/read-only được policy định nghĩa độc lập.
- Queue action có thể trì hoãn, nhưng chỉ thực hiện sau khi decision được xác minh.
- Trả retryable error và ghi event.

### 11.1. Cached authorization decision

Cache decision phải gắn với:
- Principal/subject và issuer.
- Client/actor.
- Tenant.
- Resource/action.
- Policy version.
- Relevant attributes và relationship version.
- Authentication assurance/freshness.
- Expiry và revocation state.

Nếu user bị thu hồi role hoặc resource đổi owner, decision cache có thể stale. Cần invalidation, version check hoặc TTL ngắn. Không cache permit tổng quát kiểu “user là admin” rồi áp dụng cho mọi resource.

### 11.2. Indeterminate không phải permit

Nếu PDP trả indeterminate vì PIP timeout, attribute missing hoặc policy evaluation error, không tự chuyển thành permit. Phải định nghĩa outcome rõ: deny, challenge, retry hoặc degraded action đã được phê duyệt.

## 12. Risk engine và device intelligence unavailable

Risk scoring thường bổ sung tín hiệu về IP, device, behavior hoặc threat intelligence. Không phải mọi endpoint đều phải phụ thuộc vào một risk vendor để xác thực cơ bản.

Có thể thiết kế:
- Authentication cơ bản vẫn cần credential/session hợp lệ.
- Action low impact có thể tiếp tục theo baseline policy nếu risk service lỗi.
- Action sensitive yêu cầu step-up hoặc tạm từ chối.
- Action critical fail-closed khi risk signal là điều kiện bắt buộc.
- Ghi nhận rõ risk service unavailable để không nhầm với risk score thấp.

Không biến “không có risk score” thành “risk thấp”. Missing, stale và low-risk là ba trạng thái khác nhau.

### 12.1. Không khóa account vì risk dependency outage

Nếu risk vendor outage, khóa mọi account có thể gây availability incident. Tốt hơn là áp dụng degraded policy theo action, giới hạn quyền nhạy cảm và theo dõi số request bị chuyển sang chế độ này.

Không cho phép thao tác thay recovery email, reset MFA hoặc chuyển tiền chỉ vì risk engine không trả lời.

## 13. Secret manager, HSM và signing key unavailable

Signing key, encryption key hoặc HSM là dependency bảo mật. Khi key service lỗi:
- Không ký token bằng key giả hoặc key mặc định.
- Không bỏ signature validation.
- Không dùng key cũ đã bị revoke chỉ để duy trì availability.
- Không lưu private key plaintext tạm thời vào disk/log.
- Có thể tiếp tục xác minh bằng public key đã cache nếu trust policy cho phép.
- Dừng phát hành token mới nếu không thể ký an toàn.
- Queue tác vụ có thể retry sau khi key service phục hồi.

### 13.1. Key rotation và overlap

Trong rotation bình thường, issuer có thể phát token bằng key mới và giữ public key cũ trong một khoảng overlap để verifier xác minh token còn hạn. Khi key compromise, overlap thông thường có thể không còn an toàn; cần emergency revoke và chấp nhận gián đoạn có kiểm soát.

Metric cần phân biệt key service unavailable, unknown kid, signature invalid và revoked key. Không gộp thành một lỗi chung khiến đội vận hành bỏ qua compromise signal.

## 14. Circuit breaker, timeout và retry

Khi dependency lỗi, request retry không giới hạn có thể làm hệ thống sụp đổ theo dây chuyền. Authentication path thường nằm trên nhiều request; một outage nhỏ có thể tạo lượng retry rất lớn.

### 14.1. Timeout

Đặt timeout theo budget tổng của request. Không để login request chờ vô hạn session store, IdP, MFA provider và PDP. Timeout cần ngắn đủ để bảo vệ thread/connection pool nhưng phù hợp latency thực tế.

### 14.2. Circuit breaker

Circuit breaker tạm ngừng gọi dependency đang lỗi sau một ngưỡng failure, chuyển sang trạng thái half-open để kiểm tra phục hồi. Nó bảo vệ dependency khỏi retry storm nhưng không tự quyết định cho phép request.

Khi circuit open:
- Security-critical check vẫn không được bỏ qua.
- Dùng cache chỉ nếu policy cho phép và cache còn fresh.
- Nếu không có bằng chứng đủ, trả retryable deny.
- Ghi metric circuit state và fallback outcome.

### 14.3. Retry với backoff và jitter

Retry chỉ phù hợp với lỗi tạm thời và thao tác idempotent. Dùng exponential backoff, jitter, giới hạn số lần thử và deadline tổng. Không retry password verification hoặc OTP submit vô hạn vì có thể gây lockout hoặc abuse.

Không retry side effect như chuyển tiền nếu không có idempotency key. Với session creation, tránh tạo nhiều session do client retry sau timeout không rõ kết quả.

### 14.4. Bulkhead

Tách connection pool/thread pool cho IdP, MFA, session store và analytics để một dependency chậm không chiếm hết tài nguyên của authentication service. Analytics outage không nên làm nghẽn login verification.

## 15. Degraded mode có kiểm soát

Degraded mode là trạng thái dịch vụ tiếp tục hoạt động với một số giới hạn được xác định trước.

Một degraded mode an toàn cần:
- Điều kiện kích hoạt rõ.
- Action/endpoint được phép và bị cấm.
- Dependency nào đang lỗi.
- Dữ liệu cache được sử dụng và maximum age.
- Thời gian tối đa.
- Người/automation có quyền kích hoạt.
- Audit và metric riêng.
- Cơ chế tự thoát khi dependency phục hồi.
- Runbook và rollback.

Ví dụ:

| Dependency outage | Có thể duy trì | Nên dừng hoặc hạn chế |
| --- | --- | --- |
| Metrics backend | Login và API auth tiếp tục; buffer metric nếu có | Không bỏ auth vì metrics không có |
| Email notification | Tạo request và queue notification | Không hoàn tất thay đổi recovery nếu cần verification |
| Risk engine | Public/low-risk action theo baseline | High-risk action hoặc step-up phụ thuộc risk |
| JWKS endpoint | Verify bằng cached trusted key còn fresh | Token dùng kid chưa biết hoặc key cache stale |
| Session store | Có thể dùng cache đã xác minh trong TTL hẹp nếu policy cho phép | Session không xác minh được, revoke-sensitive action |
| PDP | Cached decision đúng context/version còn fresh nếu cho phép | Action không có decision đáng tin |
| MFA provider | Phương thức factor thay thế đã đăng ký | Không cấp step-up khi chưa có proof |
| HSM/signing service | Verify bằng public key tin cậy | Không phát token nếu không ký được an toàn |

### 15.1. Degraded mode không được âm thầm bật

Khi vào degraded mode:
- Ghi sự kiện bắt đầu/kết thúc.
- Ghi dependency và policy version.
- Theo dõi số request bị ảnh hưởng.
- Alert owner.
- Hiển thị trạng thái phù hợp cho operator.
- Đặt deadline và tự quay về chế độ bình thường khi an toàn.

Không để một fallback tạm thời trở thành đường xử lý vĩnh viễn mà không được review.

## 16. Availability của audit và side effect

Một câu hỏi quan trọng là action có được phép commit nếu audit service không hoạt động không.

Không phải mọi telemetry đều cần durable synchronous write. Metrics có thể buffer/drop theo policy. Nhưng một số hành động bảo mật hoặc tài chính cần audit record bền vững để điều tra và đáp ứng nghĩa vụ.

Có thể:
- Ghi audit event vào durable local/outbox trước hoặc cùng transaction.
- Dùng transactional outbox để commit business state và audit intent nhất quán.
- Publish event bất đồng bộ sau khi commit.
- Retry delivery idempotently.
- Giám sát queue lag và dead-letter queue.

Với action critical, nếu không thể bảo đảm audit intent được lưu bền vững, policy có thể từ chối action. Với action ít rủi ro, có thể tiếp tục nếu outbox local đã durable.

### 16.1. Không đánh đồng audit với metrics

Metrics pipeline có thể bị mất một số điểm dữ liệu mà không làm mất bằng chứng kiểm toán. Audit record quan trọng cần schema, access control, integrity và retention riêng. Không để dashboard outage tự động làm login fail, cũng không bỏ audit bắt buộc vì SIEM đang chậm.

## 17. Fail-open/fail-closed cho sign-out và revocation

Sign-out thường cần vô hiệu hóa session ở server. Nếu revoke service hoặc session store lỗi:
- Không hiển thị “đã đăng xuất hoàn toàn” nếu server chưa ghi nhận revoke.
- Có thể xóa cookie local để browser ngừng gửi session, nhưng session server có thể vẫn active.
- Hiển thị trạng thái hoặc retry phù hợp.
- Revoke refresh token family khi có thể.
- Ghi logout intent vào durable queue/outbox nếu kiến trúc hỗ trợ.
- Theo dõi propagation tới mọi verifier.

Với token self-contained, xóa token ở client không thu hồi token đã bị sao chép. Nếu revoke registry không khả dụng, resource server có thể tiếp tục chấp nhận token tới expiry theo semantics đã thiết kế. Cần access token lifetime ngắn và policy cho action critical.

### 17.1. Logout local và logout global

Phân biệt:
- Local sign-out: xóa credential/session material ở thiết bị hiện tại.
- Server session revoke: vô hiệu session cụ thể.
- Revoke all sessions: vô hiệu các session của account.
- IdP logout: kết thúc session tại identity provider.
- Credential revoke: vô hiệu key/passkey/certificate hoặc refresh grant.

Metric và response cần phản ánh đúng phạm vi đã hoàn thành. Không tuyên bố revoke all nếu chỉ xóa cookie trên browser hiện tại.

## 18. Monitoring và alert cho failure policy

Theo dõi:
- Dependency timeout/error rate.
- Circuit breaker state.
- Cache hit và cache age.
- Stale decision sử dụng.
- Fail-closed denial do dependency.
- Degraded mode start/end.
- Fallback method được chọn.
- Session store outage.
- Introspection/JWKS failure.
- MFA delivery/verification failure.
- PDP indeterminate.
- Revoke propagation delay.
- Requests accepted using cached evidence.
- Requests bị từ chối vì evidence stale/unknown.
- Retry count và queue lag.

Không chỉ đo availability của dependency; đo cả quyết định bảo mật trong thời gian dependency lỗi.

### 18.1. Alert có ý nghĩa

Một số alert:
- Security-critical check bị bypass hoặc fallback permit ngoài policy.
- Cache vượt maximum stale age.
- Revoked session vẫn được chấp nhận.
- Circuit breaker open quá lâu.
- Degraded mode tồn tại quá deadline.
- Unknown signing key tăng bất thường.
- MFA timeout tăng sau deployment.
- PDP indeterminate tăng.
- Audit outbox/queue lag vượt SLA.
- Retry storm hoặc connection pool saturation.

Alert cần owner, severity, runbook và hành động cụ thể.

## 19. Ví dụ: session store outage trong ứng dụng tài chính

Ứng dụng tài chính dùng server-side session trong Redis. Redis cluster bị mất kết nối ở một region.

Thiết kế:
1. Gateway đặt timeout ngắn cho session lookup.
2. Session service phân biệt store unavailable với session not found.
3. Session đã xác minh có thể dùng local cache trong maximum stale window rất ngắn cho một số thao tác đọc ít rủi ro, nếu policy cho phép.
4. Các thao tác chuyển tiền, thay đổi recovery, thêm MFA và quản trị quyền yêu cầu kiểm tra session/revocation hiện tại; khi không thể xác minh thì từ chối tạm thời.
5. Circuit breaker ngăn request dồn vào Redis đang lỗi.
6. Không tạo session mới dựa trên cookie không xác minh.
7. Metrics ghi store failure, cache age, request denied và degraded mode.
8. Alert gửi tới owner; runbook chuyển traffic hoặc failover.
9. Sau phục hồi, synthetic check tạo, validate, revoke và xác nhận session bị từ chối.
10. Đối chiếu session state giữa primary/replica và kiểm tra không có session revoked bị hồi sinh.

~~~mermaid
flowchart TD
    A[Request có session cookie] --> B[Session store lookup]
    B --> C{Store available?}
    C -- Yes --> D[Validate current session state]
    C -- No --> E[Check approved cache]
    E --> F{Cache fresh and action allowed?}
    F -- Yes --> G[Limited degraded read path]
    F -- No --> H[Fail-closed response]
    D --> I{Session active and authorized?}
    I -- Yes --> J[Execute allowed action]
    I -- No --> H
    G --> K[Record degraded event and alert]
    H --> K
    J --> L[Audit result]
~~~

Không phải mọi request đọc đều có thể dùng cache. Dữ liệu tài chính hoặc dữ liệu cá nhân nhạy cảm có thể cần revoke freshness chặt hơn. Policy phải phân loại endpoint cụ thể.

## 20. Kiểm thử fail-open và fail-closed

| Test case | Kết quả mong đợi |
| --- | --- |
| Session store timeout | Không chấp nhận session chưa xác minh |
| Session store trả not found | Từ chối session; không nhầm với outage |
| Session store trả revoked | Từ chối ngay theo policy |
| Cache session còn fresh trong degraded mode | Chỉ action được allowlist mới tiếp tục |
| Cache session vượt maximum age | Fail-closed |
| JWKS endpoint lỗi, key đã cache còn tin cậy | Verify theo cache policy và freshness |
| JWT có kid chưa biết khi JWKS lỗi | Từ chối |
| JWT signature invalid | Từ chối, không fail-open |
| Introspection timeout | Chỉ dùng cache còn fresh theo policy; quá hạn thì deny |
| MFA provider timeout | Không coi challenge thành công |
| MFA factor thay thế đã đăng ký | Chỉ dùng nếu policy cho phép |
| IdP outage với session RP hiện tại | Áp dụng local expiry/revocation policy |
| IdP outage với login mới | Không bỏ xác minh federation |
| PDP timeout | Không permit mặc định |
| Cached permit có policy version cũ | Invalidate/deny theo policy |
| PIP trả attribute unknown | Không biến unknown thành allow |
| Risk engine outage | Degraded behavior theo action, không coi missing là low risk |
| HSM/signing service lỗi | Không phát token bằng key giả hoặc bỏ signature |
| Audit backend lỗi | Outbox/durable audit hoặc từ chối action theo policy |
| Metrics backend lỗi | Authentication vẫn giữ nguyên kiểm soát |
| Email provider lỗi trong recovery | Không hoàn tất thay đổi cần email verification |
| Circuit breaker open | Không bỏ security check |
| Retry storm | Backoff, jitter, bounded attempts và bulkhead hoạt động |
| Logout revoke timeout | Không tuyên bố server revoke hoàn tất |
| Multi-region revoke outage | Đo propagation; action nhạy cảm bị chặn nếu stale |
| Dependency phục hồi | Half-open/recovery và synthetic checks thành công |
| Degraded mode quá deadline | Alert/escalation và tự thoát theo policy |
| Fail-open config regression | Test phát hiện permit khi security dependency unknown |

### 20.1. Fault injection

Trong môi trường test/staging, chủ động:
- Ngắt kết nối session store.
- Làm chậm IdP hoặc MFA provider.
- Trả JWKS với key mới chưa cache.
- Làm PDP timeout hoặc trả indeterminate.
- Mất event invalidation.
- Tạo clock skew.
- Làm queue/audit outbox đầy.
- Làm metrics collector unavailable.
- Gửi duplicate/reordered revoke event.

Kiểm tra response, side effect, audit, metric và khả năng phục hồi. Không thử fault injection trực tiếp trên production nếu chưa có change control và phạm vi được phê duyệt.

## 21. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Security-critical dependency được liệt kê? | Có dependency graph và owner |
| Credential invalid khác dependency unavailable? | Reason code và response tách biệt |
| Mỗi action có failure policy? | Phân loại theo impact/risk |
| Unknown có bị coi là allow? | Không; default-deny cho điều kiện bắt buộc |
| Cache có freshness bound? | TTL, version, invalidation và maximum stale |
| Session store outage được xử lý? | Không chấp nhận cookie không xác minh |
| JWKS outage có policy? | Chỉ dùng trusted cached key còn fresh |
| MFA timeout có bị coi là success? | Không |
| PDP/PIP outage có fallback? | Cached decision có binding/version hoặc deny |
| Risk missing khác low risk? | Missing/stale/low được phân biệt |
| Circuit breaker có giữ security check? | Không tự biến outage thành permit |
| Retry có bounded? | Timeout, backoff, jitter và deadline |
| Degraded mode có giới hạn? | Endpoint, thời gian, owner và audit rõ |
| Audit có bền vững? | Outbox/durable record cho action cần thiết |
| Logout/revoke có đo hiệu lực? | Propagation và synthetic validation |
| Break-glass được kiểm soát? | MFA, approval, alert, audit và rotation |
| Monitoring có theo dõi fallback? | Cache age, degraded mode và stale acceptance |
| Recovery đã được test? | Failover, cache refresh và revoke consistency |
| Có fault injection? | Session, IdP, MFA, PDP, HSM, queue và metrics |

### Tình huống tự kiểm tra

**Tình huống 1:** Session store không phản hồi. Gateway có nên chấp nhận cookie vì người dùng đã login trước đó không?

**Trả lời:** Không mặc định. Chỉ có thể dùng cache session đã xác minh nếu cache còn trong maximum stale window và action nằm trong degraded policy. Nếu không thể xác minh, từ chối tạm thời.

**Tình huống 2:** JWKS endpoint lỗi nhưng verifier có public key đã cache từ issuer tin cậy. Có phải luôn từ chối mọi JWT không?

**Trả lời:** Không nhất thiết. Có thể xác minh bằng key cache còn fresh theo policy. Token có kid chưa biết hoặc cache vượt maximum age phải bị từ chối.

**Tình huống 3:** MFA provider timeout. Có thể coi người dùng đã approve để giữ trải nghiệm không?

**Trả lời:** Không. Timeout không phải proof. Cần retry có giới hạn hoặc factor thay thế đã đăng ký và được policy chấp nhận.

**Tình huống 4:** Risk engine unavailable. Có thể cho phép mọi action vì không phát hiện rủi ro không?

**Trả lời:** Không. Missing risk signal không phải low risk. Áp dụng degraded policy theo action; hạn chế action nhạy cảm hoặc yêu cầu step-up.

**Tình huống 5:** PDP lỗi nhưng JWT chứa scope write. API có thể tự cho phép không?

**Trả lời:** Chỉ khi policy đã định nghĩa scope đó đủ cho đúng action/resource và backend có thể tự đánh giá toàn bộ điều kiện còn lại. Nếu PDP là dependency bắt buộc cho decision, phải deny hoặc dùng cached decision còn hợp lệ.

**Tình huống 6:** Metrics backend lỗi. Có nên từ chối login để bảo đảm có telemetry không?

**Trả lời:** Không nhất thiết. Metrics thường không phải security decision dependency. Có thể buffer/drop metrics theo policy nhưng authentication vẫn phải giữ các kiểm soát cốt lõi. Audit bắt buộc cần được xử lý riêng.

**Tình huống 7:** API revoke trả thành công nhưng một region vẫn chấp nhận session cũ. Có thể báo logout global hoàn tất không?

**Trả lời:** Không. Cần đo propagation tới mọi verifier và chỉ báo phạm vi đã hoàn thành. Action nhạy cảm phải áp dụng policy khi revoke state chưa nhất quán.

**Tình huống 8:** Break-glass account được dùng khi IdP outage. Có nên để password tĩnh trong runbook để cả đội dùng không?

**Trả lời:** Không. Credential phải được kiểm soát riêng, MFA, access scope hẹp, approval, alert, audit và rotation sau sử dụng.

## 22. Ghi nhớ

**Fail-closed từ chối request khi không thể xác minh điều kiện bảo mật bắt buộc; fail-open cho request tiếp tục dù bằng chứng chưa được xác minh đầy đủ.** Fail-open có thể tạo bypass; fail-closed có thể làm giảm availability. Quyết định phải dựa trên loại dependency, action, dữ liệu, impact và khả năng dùng cache đáng tin cậy.

Không coi timeout là credential hợp lệ, missing risk là low risk, PDP indeterminate là permit hoặc MFA timeout là approval. Cache phải có TTL, version, invalidation và maximum stale window. Circuit breaker, timeout, backoff, jitter và bulkhead bảo vệ availability nhưng không được bỏ qua security check. Degraded mode cần endpoint allowlist, thời hạn, owner, audit và monitoring. Kiểm thử fault injection, session revoke, JWKS rotation, IdP/MFA/PDP outage và recovery để chứng minh hệ thống vừa duy trì availability hợp lý vừa giữ trust boundary.
