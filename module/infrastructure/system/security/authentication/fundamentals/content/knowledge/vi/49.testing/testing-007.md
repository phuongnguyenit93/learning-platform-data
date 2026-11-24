# Abuse prevention test

## 1. Abuse prevention test là gì?

**Abuse prevention test** là hoạt động kiểm thử có chủ đích để xác minh các kiểm soát chống lạm dụng trong hệ thống xác thực hoạt động đúng dưới cả traffic bình thường, hành vi tự động và tình huống đối kháng. Mục tiêu là bảo đảm attacker khó đoán credential, thử hàng loạt password, làm cạn tài nguyên, chiếm session, lạm dụng recovery hoặc ép người dùng chấp thuận MFA; đồng thời người dùng hợp lệ vẫn có thể đăng nhập và khôi phục tài khoản.

Authentication là điểm tiếp xúc công khai của nhiều hệ thống. Các endpoint login, password reset, OTP, passkey, token refresh, account registration, session validation và device enrollment có thể bị gọi tự động với tốc độ cao. Nếu chỉ kiểm thử happy path, nhóm phát triển có thể bỏ sót rate limit sai phạm vi, race condition, account enumeration, lockout gây DoS, MFA fatigue, token replay hoặc bypass qua nhiều IP/client.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, abuse prevention test kết nối password authentication, MFA, passkey, certificate, token, session, credential lifecycle, recovery, API authentication và monitoring. Bài kiểm thử cần đánh giá cả hiệu lực bảo mật lẫn tác động tới người dùng hợp lệ: kiểm soát phải chặn abuse mà không biến cơ chế bảo vệ thành công cụ khóa nhầm tài khoản hoặc làm gián đoạn dịch vụ.

Sau bài học, người học có thể:

- Xây dựng threat model cho abuse trên authentication endpoints.
- Phân biệt brute force, password spraying, credential stuffing, enumeration và MFA fatigue.
- Kiểm thử rate limit theo account, IP/network, device, client và toàn hệ thống.
- Kiểm tra lockout, progressive delay, CAPTCHA/challenge và recovery behavior.
- Phát hiện race condition, distributed bypass và giới hạn sai cửa sổ thời gian.
- Kiểm thử OTP, reset token, refresh token, session và replay protection.
- Đánh giá bot mitigation và API abuse mà không dựa vào một tín hiệu duy nhất.
- Đo false positive, latency, availability và khả năng khôi phục.
- Xây dựng test matrix, synthetic identities, telemetry và release criteria.
- Thực hiện kiểm thử an toàn trong môi trường được phép, có giới hạn và có thể tái lập.

## 2. Threat model: attacker có thể lạm dụng điều gì?

Abuse không chỉ là một password sai nhiều lần. Attacker có thể lạm dụng bất kỳ chức năng nào tiêu thụ tài nguyên, thay đổi trạng thái hoặc tiết lộ thông tin.

Các mục tiêu thường gặp:
- Đoán password hoặc kiểm tra danh sách credential bị rò rỉ.
- Xác định email/username có tồn tại.
- Gửi OTP hoặc push prompt liên tục để làm phiền hoặc gây chi phí.
- Lạm dụng password reset, account recovery hoặc resend verification.
- Tạo nhiều account để né quota hoặc abuse controls.
- Chiếm session qua token theft, replay hoặc refresh race.
- Tạo tải lên password hash, MFA provider, database hoặc identity provider.
- Bypass rate limit bằng nhiều IP, IPv6 address, proxy hoặc client identifier.
- Khai thác lockout để khóa account của nạn nhân.
- Lạm dụng endpoint API không đi qua login UI hoặc gateway.
- Thử lại request song song để vượt giới hạn.
- Dùng flow hợp lệ nhưng sai mục đích, như device enrollment hoặc account linking.

### 2.1. Phân biệt các kiểu tấn công

| Kiểu abuse | Đặc điểm | Tín hiệu thường thấy |
| --- | --- | --- |
| **Brute force** | Thử nhiều password cho một account | Nhiều lần thất bại trên cùng identifier |
| **Password spraying** | Thử một vài password phổ biến trên nhiều account | Một password hoặc pattern xuất hiện trên nhiều identifier |
| **Credential stuffing** | Thử cặp username/password từ nguồn rò rỉ | Nhiều cặp khác nhau, phân tán IP/device |
| **Account enumeration** | Tìm account tồn tại hoặc trạng thái account | So sánh response, timing, reset delivery |
| **MFA fatigue** | Gửi nhiều push challenge để ép approve | Prompt lặp, timeout/deny tăng |
| **OTP brute force** | Thử mã OTP trong cửa sổ hiệu lực | Nhiều code sai trên một challenge/account |
| **Recovery abuse** | Lạm dụng reset, resend hoặc support recovery | Nhiều request hoặc thay đổi contact bất thường |
| **Session/token replay** | Dùng lại cookie/token/assertion đã bị lấy | Token family reuse hoặc nonce đã consume |
| **Resource exhaustion** | Làm cạn CPU, database, SMS/email budget hoặc worker | Latency, queue, provider cost tăng |
| **Automation abuse** | Bot tạo account hoặc gọi API theo kịch bản | Request pattern lặp, tốc độ cao, client giả |
| **Lockout DoS** | Cố ý làm account nạn nhân bị khóa | Nhiều failed attempts nhắm vào một số account |
| **Race/concurrency abuse** | Gửi request song song để vượt limit hoặc dùng lại token | Counter sai, double success, duplicate side effect |

### 2.2. Xác định tài sản và trust boundary

Vẽ đường đi của request:
- Browser/mobile client.
- CDN, WAF và reverse proxy.
- API gateway.
- Authentication service.
- Password verifier/database.
- MFA provider.
- Session/token service.
- Risk engine.
- Email/SMS provider.
- Recovery/support system.
- Audit, metrics và SIEM.

Với mỗi thành phần, hỏi:
- Ai có thể gửi request trực tiếp?
- Header nào được tin cậy và do ai thiết lập?
- Rate limit đặt ở đâu?
- Request có thể bypass gateway không?
- Có state được chia sẻ giữa region không?
- Dependency nào có chi phí hoặc tài nguyên hữu hạn?
- Sự kiện nào phải audit?
- Khi dependency lỗi, kiểm soát có fail-open không?

### 2.3. Abuse case cần viết rõ

Mỗi abuse case nên có actor, prerequisite, endpoint, action, expected control, observable signal và impact. Ví dụ:

~~~text
Actor: automated client without account access
Target: password reset endpoint
Action: submit many identifiers and repeat requests concurrently
Expected: generic response, per-identifier and network controls,
          delivery cooldown, bounded queue and no account enumeration
Signals: request rate, reset-send count, provider cost, response class
Impact to measure: legitimate recovery success and delivery latency
~~~

Mô tả này giúp test tập trung vào hiệu quả kiểm soát và tác động thay vì chỉ đếm HTTP 429.

## 3. Nguyên tắc kiểm thử an toàn và có thể tái lập

Abuse prevention test có thể tạo tải hoặc thay đổi trạng thái account. Cần có phạm vi được phê duyệt và môi trường test phù hợp.

Nguyên tắc:
- Dùng staging hoặc isolated test environment có cấu hình gần production.
- Chỉ dùng synthetic account, synthetic credential và dữ liệu giả.
- Không thử credential của người dùng thật hoặc danh sách rò rỉ thật.
- Không gửi traffic tới dịch vụ bên thứ ba nếu chưa có phê duyệt và quota test.
- Đặt giới hạn tốc độ, thời gian, concurrency và số account.
- Có kill switch, test window và owner giám sát.
- Dùng SMS/email sandbox hoặc mock provider để tránh phát sinh chi phí và làm phiền người dùng.
- Dọn session, lockout state, challenge và test account sau khi hoàn tất.
- Ghi test run ID để phân biệt traffic thử nghiệm với abuse thật.
- Không đưa password, OTP hoặc token test vào log.

### 3.1. Test environment phải đại diện đủ

Một mock thuần túy có thể bỏ qua lỗi distributed rate limit, cache, proxy hoặc provider latency. Nên có:
- Unit tests cho policy/counter.
- Integration tests cho database/cache/queue.
- Multi-instance tests cho distributed limits.
- Staging tests qua CDN/WAF/gateway thật.
- Load/fault tests với dependency giả lập.
- Synthetic production monitoring chỉ dùng account và endpoint được cho phép.

Không dùng production traffic làm nơi thử lockout hoặc flood. Nếu cần xác minh production control, dùng canary account và rate rất thấp theo change approval.

### 3.2. Giữ test deterministic

Để test có thể lặp lại:
- Dùng clock injection hoặc controllable time.
- Reset counter/state giữa test.
- Gán test run ID.
- Dùng deterministic provider response trong unit/integration test.
- Kiểm tra cả boundary time window.
- Cô lập account, IP range và device identity test.
- Ghi version policy/config đang chạy.

Test không deterministic thường tạo false positive và khiến nhóm vô hiệu hóa control để “cho pipeline xanh”.

## 4. Rate limiting: kiểm tra đúng phạm vi

Rate limiting giới hạn số request trong một khoảng thời gian. Một limiter chỉ theo IP thường không đủ vì nhiều người dùng có thể chia sẻ NAT, attacker có thể phân tán IP hoặc dùng IPv6 address khác nhau.

Các dimension có thể kết hợp:
- Account/principal identifier.
- IP hoặc network prefix.
- Device-bound key hoặc app instance reference.
- Client/application ID.
- Tenant/organization.
- Endpoint/action.
- Global service budget.
- Provider cost budget, ví dụ SMS/email.

Không dùng raw email hoặc IP làm metric label. Rate-limit key có thể cần identifier chuẩn hóa và keyed hash trong storage; cần bảo vệ dữ liệu và retention.

### 4.1. Per-account limit

Kiểm thử nhiều lần sai trên cùng account:
- Counter tăng đúng.
- Success/failure behavior theo policy.
- Counter reset hoặc decay đúng.
- Không thể reset bằng cách đổi capitalization/whitespace nếu identifier normalization coi chúng tương đương.
- Account unknown không tạo state vô hạn dễ bị DoS.
- Attacker không thể khóa nạn nhân chỉ bằng cách gửi password sai.

Per-account limit cần cân bằng giữa chống brute force và lockout DoS. Progressive delay, risk-based step-up hoặc temporary throttling có thể phù hợp hơn khóa account cứng lâu dài.

### 4.2. Per-IP và network limit

Kiểm tra:
- Nhiều account từ một IP.
- Một account từ nhiều IP.
- IPv4 và IPv6.
- Shared NAT/corporate proxy.
- Trusted proxy chain.
- Header X-Forwarded-For giả từ client.
- CDN/WAF và origin direct access.

Chỉ tin forwarded IP header khi request đến từ proxy được cấu hình tin cậy và proxy đã loại/ghi đè header do client gửi. Nếu không, attacker có thể đổi IP bằng cách sửa header.

### 4.3. Per-device và per-client limit

Device ID do client tự khai có thể bị giả mạo hoặc reset. Nếu dùng device signal, cần đánh giá nguồn gốc và integrity. Device-bound public key có thể đáng tin hơn một UUID trong local storage, nhưng vẫn có lifecycle, revoke và recovery.

Client ID giúp tách ứng dụng hoặc integration, nhưng public client ID không phải secret. Không cho rằng mỗi client ID tương ứng một client đáng tin.

### 4.4. Global limit và resource budget

Một attacker có thể phân tán request qua nhiều account/IP. Global limiter bảo vệ password verifier, MFA provider và database khỏi quá tải.

Đo:
- Tổng login attempt rate.
- Password hash CPU utilization.
- Queue depth.
- Provider send rate/cost.
- Database connection pool.
- Latency và rejection rate.
- Tỷ lệ traffic hợp lệ bị ảnh hưởng.

Global limit quá chặt có thể biến một cuộc tấn công thành outage cho mọi người. Cần capacity model, burst allowance và circuit breaker.

## 5. Thuật toán và boundary của rate limit

Các thuật toán phổ biến:
- Fixed window counter.
- Sliding window log.
- Sliding window counter.
- Token bucket.
- Leaky bucket.

Mỗi loại có trade-off giữa độ chính xác, memory, burst và concurrency.

| Thuật toán | Đặc điểm | Test cần có |
| --- | --- | --- |
| Fixed window | Đếm theo cửa sổ cố định; có thể burst ở ranh giới | Gửi sát cuối và đầu hai cửa sổ |
| Sliding window log | Chính xác hơn nhưng giữ timestamp từng request | Memory/cleanup dưới tải |
| Sliding window counter | Ước lượng bằng hai cửa sổ | Boundary và sai số |
| Token bucket | Cho burst có giới hạn, refill theo thời gian | Burst, refill, clock và parallel request |
| Leaky bucket | Làm phẳng tốc độ xử lý | Queue growth, latency và overflow |

### 5.1. Boundary test

Với limit N trong T giây, kiểm tra:
- N request trong cửa sổ được xử lý theo policy.
- Request N+1 bị throttle.
- Hết cửa sổ thì quota phục hồi đúng.
- Request gửi đúng tại ranh giới không tạo gấp đôi quota.
- Clock skew không làm counter reset sớm.
- Retry không làm tăng counter sai semantics.
- Nhiều instance không cấp N quota riêng cho mỗi instance nếu policy là global.

### 5.2. Atomicity và race condition

Hai request đồng thời có thể đọc cùng counter rồi cùng ghi N+1, khiến limit bị vượt. Dùng atomic increment/transaction hoặc script phù hợp trong shared store.

Kiểm thử:
1. Đặt counter ở N-1.
2. Gửi nhiều request đồng thời.
3. Xác minh chỉ request được policy cho phép vượt qua.
4. Đối chiếu counter trong store và event.
5. Lặp lại qua nhiều instance/region.

Không chỉ test tuần tự vì race condition thường chỉ xuất hiện khi concurrency cao.

### 5.3. Distributed limiter

Nếu mỗi application instance giữ counter riêng, tổng limit có thể nhân với số instance. Distributed limiter cần consistency và failure behavior rõ.

Kiểm tra:
- Nhiều instance dùng chung state.
- Region replication delay.
- Store timeout.
- Atomic script failure.
- Failover và lost counter.
- Counter eviction.
- Clock drift.
- Retry sau timeout không rõ kết quả.

Nếu limiter unavailable, không tự động bỏ mọi limit trên login endpoint. Có thể dùng emergency local cap rất thấp hoặc từ chối tạm thời theo policy; phải đo và cảnh báo.

## 6. Brute force, spraying và credential stuffing tests

### 6.1. Brute force

Dùng synthetic account trong test:
- Thử số lượng password sai dưới limit.
- Thử vượt limit.
- Thử đúng password sau các lần sai.
- Kiểm tra delay/lockout và recovery.
- Kiểm tra counter theo account và network.
- Kiểm tra attacker không thể khóa account lâu dài chỉ bằng failed request từ bên ngoài.

Expected result:
- Request bị throttle theo policy.
- Không tạo session từ credential sai.
- Response không tiết lộ account state.
- Người dùng hợp lệ có đường đăng nhập/recovery an toàn.
- Security event và metric được ghi đúng.

### 6.2. Password spraying

Mô phỏng một vài password giả trên nhiều synthetic account:
- Phân tán theo account nhưng dùng chung network/client.
- Thử từ nhiều network test được phép.
- Kiểm tra detection theo pattern tổng thể.
- Kiểm tra không chỉ khóa từng account khi chưa có bằng chứng đủ.
- Kiểm tra global limit và alert.

Không sử dụng password phổ biến thật hoặc credential của người dùng. Mục tiêu là xác minh detection logic với fixture được tạo cho test.

### 6.3. Credential stuffing

Mô phỏng cặp identifier/password tổng hợp với tỷ lệ thành công được kiểm soát. Kiểm tra:
- Rate limit theo account, IP/network và client.
- Breached-password signal nếu có.
- Risk-based step-up.
- Session creation anomaly.
- Device/key enrollment sau login bất thường.
- Notification và revoke behavior.
- False positive với người dùng hợp lệ.

Không tải hoặc replay danh sách credential bị rò rỉ thật. Dùng synthetic corpus có account/password giả và kết quả đã biết.

### 6.4. Lockout DoS

Attacker có thể gửi nhiều password sai nhắm vào account của nạn nhân để khóa họ. Kiểm thử:
- Temporary lockout có thời hạn.
- Progressive delay.
- Step-up thay vì khóa cứng.
- Rate limit theo nhiều dimension.
- Recovery không dễ bị abuse tiếp.
- Thông báo không tiết lộ trạng thái account cho attacker.
- Người dùng hợp lệ có cách lấy lại quyền truy cập.

Không tạo lockout vĩnh viễn chỉ vì failed attempts do người khác gửi.

## 7. Account enumeration tests

Enumeration có thể xảy ra qua login, registration, password reset, resend verification, MFA recovery, account linking và SSO discovery.

Kiểm thử các identifier synthetic:
- Account tồn tại với password sai.
- Account không tồn tại.
- Account disabled.
- Account pending verification.
- Account locked/temporarily throttled.
- Account yêu cầu MFA.
- Account liên kết IdP khác.

So sánh:
- HTTP status.
- Response body và length.
- Header.
- Redirect.
- Timing distribution.
- UI behavior.
- Email/SMS delivery side effect.
- Rate-limit response.

Expected result là thông tin bên ngoài không tạo oracle dễ khai thác. Không cần phản hồi byte-for-byte giống nhau nếu có khác biệt kỹ thuật không nhạy cảm, nhưng không được tiết lộ trạng thái account qua một nhánh dễ đoán.

### 7.1. Timing test

Thu nhiều mẫu ở cùng điều kiện test, so sánh median và percentile giữa identifier tồn tại/không tồn tại. Kiểm soát network noise, warm cache và password hash cost. Không kết luận từ một request đơn lẻ.

Nếu có khác biệt đáng kể, xem lại fake verifier, lookup path, MFA lookup, cache và notification side effect.

## 8. MFA và OTP abuse tests

MFA có thể bị lạm dụng để gây chi phí, spam hoặc ép người dùng chấp thuận.

### 8.1. OTP guessing

Kiểm tra:
- Số lần thử trên mỗi challenge.
- Số lần thử theo account và network.
- OTP hết hạn.
- OTP đã dùng không thể dùng lại.
- Challenge mới có invalidation behavior rõ.
- Code sai không làm lộ thông tin factor.
- Concurrent verification chỉ cho một lần consume.
- Clock skew và TOTP window theo policy.

### 8.2. SMS/email bombing

Dùng sandbox provider để kiểm tra:
- Resend cooldown.
- Per-account và per-destination limit.
- Global provider budget.
- Idempotency của resend.
- Không gửi tới destination chưa xác minh ngoài flow hợp lệ.
- Response không xác nhận destination/account tồn tại.
- Queue có bounded capacity và retry có giới hạn.

Đo cả delivery success, queue lag, provider cost estimate và legitimate user impact.

### 8.3. Push fatigue

Mô phỏng nhiều challenge đến synthetic device:
- Giới hạn số push prompt.
- Hiển thị context đủ để người dùng nhận ra giao dịch.
- Có deny/report action.
- Không tự approve khi timeout.
- Không tạo challenge mới vô hạn khi client retry.
- Alert khi prompt rate tăng.
- Có thể tạm dừng push và yêu cầu phương thức khác sau ngưỡng.

### 8.4. MFA downgrade

Kiểm thử attacker chọn fallback yếu hơn:
- Phishing-resistant factor bị bỏ qua để dùng SMS.
- TOTP được chấp nhận ở action yêu cầu passkey.
- Device credential bị ghi nhận nhầm là biometric.
- Recovery bypass MFA mà không có proofing.
- Factor vừa bị revoke vẫn được chấp nhận.

Expected result phải khớp assurance policy của action. Không âm thầm downgrade khi provider lỗi.

## 9. Password reset và account recovery abuse

Recovery là đường chiếm account phổ biến nếu token hoặc flow yếu.

Kiểm tra:
- Reset request response không tiết lộ account existence.
- Token có entropy đủ, expiry và one-time use.
- Token gắn đúng account, purpose và transaction.
- Token bị consume atomically.
- Resend có cooldown và giới hạn.
- Token cũ bị vô hiệu theo policy khi token mới phát hành.
- Password reset revoke session/refresh token phù hợp.
- MFA reset yêu cầu proofing/step-up phù hợp.
- Recovery contact change có notification tới kênh cũ.
- Support override có approval, audit và delay khi cần.
- Recovery endpoint có chống bot và resource exhaustion.

### 9.1. Token replay và concurrent redemption

Tạo một reset token test hợp lệ rồi gửi hai request redeem đồng thời. Chỉ một request được phép thành công. Request thứ hai phải bị từ chối mà không tạo side effect thứ hai.

Tương tự kiểm tra magic link, email verification token, enrollment token và invitation token.

### 9.2. Recovery abuse không được làm lộ dữ liệu

Không trả thông báo “email không tồn tại” hoặc “account đã có MFA”. Dùng response chung, destination masking phù hợp và delivery status chỉ hiển thị sau khi người dùng chứng minh quyền kiểm soát.

## 10. Session và token abuse tests

Kiểm thử session/token lifecycle:
- Session ID rotation sau login và privilege elevation.
- Session fixation: session trước authentication không được giữ làm session authenticated nếu policy yêu cầu rotate.
- Logout local và server-side revoke.
- Revoke all sessions sau password/MFA reset theo policy.
- Expired token bị từ chối.
- Revoked token bị từ chối trong SLA.
- Wrong issuer/audience/token type bị từ chối.
- Refresh token rotation và reuse detection.
- Concurrent refresh race.
- Device-bound/sender-constrained token không dùng từ key khác.
- JWT key rotation và unknown kid.
- Cookie Secure/HttpOnly/SameSite và CSRF behavior.
- Session idle/absolute timeout.

### 10.1. Refresh token reuse

Nếu refresh token rotation được bật, reuse token cũ có thể báo hiệu token theft. Kiểm thử:
1. Refresh token R1 được dùng và đổi thành R2.
2. Gửi lại R1.
3. Xác minh server phát hiện reuse theo policy.
4. Kiểm tra token family có bị revoke đúng phạm vi không.
5. Đảm bảo retry race hợp lệ được phân biệt nếu protocol/client hỗ trợ.
6. Ghi event không chứa raw token.

### 10.2. Session fixation và hijack signal

Dùng test session để xác minh ID thay đổi sau login, MFA step-up hoặc privilege elevation theo policy. Kiểm tra cookie không bị ghi vào log và session bị revoke sau sự kiện compromise.

Không dùng một session ID thật của người dùng hoặc cố chiếm phiên production trong bài test.

## 11. Passkey, WebAuthn và certificate abuse tests

Passkey giảm phishing nhưng enrollment và recovery vẫn có thể bị lạm dụng.

Kiểm thử:
- Registration challenge one-time.
- Authentication challenge one-time.
- Challenge hết hạn và replay.
- Origin/RP ID mismatch.
- Signature invalid.
- Credential ID không thuộc account.
- User verification requirement.
- Attestation policy nếu được sử dụng.
- Credential revoke/deletion.
- Sign counter/backup state theo semantics authenticator, không giả định mọi authenticator tăng counter giống nhau.
- Account linking không tự động chỉ dựa email.
- Enrollment mới cần authentication context phù hợp.

Với certificate/client authentication:
- Certificate hết hạn.
- Certificate revoked.
- Wrong SAN/subject mapping.
- Wrong trust chain.
- Private key mismatch.
- Key rotation overlap.
- mTLS identity không được phép dùng API.
- Revocation service unavailable theo failure policy.

Không coi certificate hợp lệ về chữ ký là quyền truy cập tự động. Authorization vẫn phải kiểm tra principal, client, audience, tenant và action.

## 12. API và service-to-service abuse tests

Không chỉ kiểm thử login UI. Attacker có thể gọi endpoint trực tiếp, bỏ qua frontend validation hoặc gateway nếu origin backend exposed.

Kiểm tra:
- Authentication middleware áp dụng trên mọi route cần bảo vệ.
- Rate limit theo route/action và principal/client.
- Scope/audience/object-level authorization.
- Tenant isolation.
- Idempotency cho side effect.
- Request signing và nonce nếu API dùng HMAC.
- Webhook signature và replay protection.
- Header spoofing như X-User, X-Role, X-Tenant.
- Service identity và workload permission.
- Bulk export và pagination abuse.
- Expensive search/filter parameter.
- GraphQL batching/depth nếu có.
- Upload/body size và parsing limits.

### 12.1. Gateway bypass

Thử truy cập backend trực tiếp trong staging qua network path được phép. Expected result:
- Backend vẫn xác minh identity hoặc chỉ nhận traffic từ gateway đã authenticate.
- Header identity do client tự gửi bị strip/ignore.
- Internal route không public ngoài ý muốn.
- Rate limit và authorization không chỉ tồn tại ở frontend.

### 12.2. Business logic abuse

Một request có thể authenticated và authorized ở cấp route nhưng vẫn lạm dụng workflow:
- Tạo quá nhiều recovery request.
- Liên kết nhiều external identity.
- Thêm/xóa MFA factor liên tục.
- Gửi quá nhiều invitation.
- Revoke session của user khác.
- Thực hiện action lặp bằng retry.
- Đổi destination sau step-up.

Test phải kiểm tra quota, ownership, state transition và transaction binding.

## 13. Bot mitigation và challenge

CAPTCHA, proof-of-work, device signal hoặc behavioral detection có thể tăng chi phí automation, nhưng không phải bằng chứng danh tính và không thay authentication.

Kiểm thử:
- Challenge chỉ xuất hiện theo policy.
- Challenge response gắn với session/action và expiry.
- Token challenge one-time.
- Replay bị từ chối.
- Provider timeout không được coi là pass.
- Accessibility alternative có sẵn.
- Challenge không làm lộ account existence.
- Attacker không thể dùng một challenge token cho nhiều account/action.
- Challenge service outage có degraded policy.
- False positive không chặn quá mức người dùng hợp lệ.

Không đặt CAPTCHA ở mọi login chỉ vì có thể; đo conversion, abandonment, accessibility và abuse reduction. Challenge phải có owner, expiry và telemetry.

## 14. Resource exhaustion và resilience

Authentication có thể tiêu tốn CPU do password hashing, network do IdP/MFA, database do account lookup và storage do challenge/session. Abuse prevention test cần đánh giá hệ thống khi tải cao.

Theo dõi:
- Request rate và concurrency.
- Password hash CPU/memory.
- Thread/connection pool.
- Database latency.
- Redis/session store latency.
- MFA provider queue/cost.
- Email/SMS send rate.
- Challenge queue.
- Token introspection/JWKS latency.
- Error rate và legitimate login success.
- p95/p99 latency.

### 14.1. Load test an toàn

Dùng synthetic account và test provider. Tăng tải theo bước, có giới hạn và stop condition. Kiểm tra hệ thống giữ rate limit, không fail-open, không tạo retry storm và vẫn phục vụ traffic hợp lệ ở mức capacity đã định.

Không tạo load test lên SMS/email thật hoặc IdP bên ngoài nếu không có test tenant/quota được chấp thuận.

### 14.2. Backpressure và bounded queue

Khi provider chậm, queue không được tăng vô hạn. Kiểm thử:
- Queue max size.
- Rejection behavior.
- Retry/backoff.
- Dead-letter handling.
- Expired challenge cleanup.
- Per-account send budget.
- Circuit breaker.
- Recovery khi provider phục hồi.

### 14.3. Fail-open regression

Dependency outage có thể vô hiệu hóa abuse controls. Test session store, rate-limit store, risk engine, CAPTCHA provider và MFA provider khi không phản hồi. Unknown/missing decision không được biến thành permit hoặc challenge success.

## 15. Observability và security signal

Mỗi test cần xác định expected telemetry:
- Event type.
- Result/reason code.
- Counter/histogram.
- Alert.
- Correlation reference.
- Owner/runbook.

Metric có thể gồm:
- auth_attempts_total theo outcome/method/client class.
- auth_rate_limited_total theo reason class.
- credential_stuffing_signal_total.
- account_enumeration_probe_total.
- mfa_challenge_sent_total và mfa_challenge_denied_total.
- otp_verification_failed_total.
- recovery_request_total và recovery_throttled_total.
- refresh_token_reuse_total.
- session_revoked_request_total.
- challenge_provider_latency_seconds.
- password_verifier_duration_seconds.
- legitimate_login_success_ratio.

Không dùng raw email, password, OTP, token, session ID hoặc IP làm metric label. Dùng enum, aggregate và pseudonymous references ở audit store.

### 15.1. Detection và response

Detection rule cần có:
- Baseline.
- Threshold và minimum sample.
- Window.
- Grouping dimension.
- False positive handling.
- Severity.
- Owner.
- Runbook.

Không tự động khóa account chỉ dựa một tín hiệu như IP mới. Kết hợp failed attempts, device trust, successful login, MFA result, recovery event và action risk.

## 16. False positive và user impact

Một control chống abuse tốt không chỉ chặn attacker mà còn phải giảm tác động lên người dùng hợp lệ.

Theo dõi:
- Legitimate login success ratio.
- False lockout rate.
- MFA challenge completion.
- Recovery completion.
- CAPTCHA abandonment.
- Support ticket rate.
- Time to regain account access.
- Thời gian từ throttle đến tự phục hồi.
- Tỷ lệ user bị challenge do network/shared NAT.

Kiểm tra nhóm:
- Người dùng dùng VPN/corporate NAT.
- Người dùng chuyển mạng mobile/Wi-Fi.
- Thiết bị mới hoặc app reinstall.
- Người dùng có accessibility needs.
- Service account/workload autoscaling.
- Khu vực có network latency cao.

Không hạ control chỉ vì có false positive; điều chỉnh dimension, threshold, progressive challenge và recovery path dựa trên dữ liệu.

## 17. Privacy và dữ liệu trong abuse testing

Abuse testing có thể tạo identifier, IP, device signal và security event. Dùng dữ liệu tổng hợp và kiểm soát telemetry.

Nguyên tắc:
- Không dùng account/credential thật.
- Không log password, OTP, token hoặc reset link.
- Dùng test run ID và synthetic principal reference.
- Giới hạn retention test data.
- Không gửi test notification tới người dùng thật.
- Mask destination và không thu thập biometric.
- Dọn test account, session, key và challenge sau test.
- Phân biệt test traffic với production security event.
- Kiểm soát export và quyền đọc test evidence.

Nếu cần kiểm thử trên production bằng canary account, phải có phạm vi, thời gian, rate cap, owner, kill switch và notification plan được phê duyệt.

## 18. Test matrix tổng hợp

| Nhóm | Test case | Kết quả mong đợi |
| --- | --- | --- |
| Password | Brute force vượt ngưỡng | Throttle/delay theo policy, không tạo session |
| Password | Spraying trên nhiều account | Detection theo pattern, global limit và alert |
| Password | Credential stuffing synthetic corpus | Abuse controls hoạt động, false positive được đo |
| Lockout | Attacker cố khóa account nạn nhân | Không có permanent lockout dễ bị kích hoạt từ ngoài |
| Enumeration | Account tồn tại/không tồn tại | Không có response/timing oracle dễ khai thác |
| Rate limit | N request trong window | Boundary đúng theo algorithm |
| Rate limit | N+1 request | Throttle đúng |
| Rate limit | Concurrent request tại N-1 | Atomic limit, không vượt ngoài policy |
| Rate limit | Nhiều instance/region | Limit đúng trên toàn phạm vi |
| Rate limit | Forwarded IP spoofing | Không bypass trusted proxy model |
| MFA | OTP brute force | Attempt limit, expiry và one-time use |
| MFA | OTP replay | Từ chối |
| MFA | Push fatigue | Prompt throttling, deny/report và alert |
| MFA | Provider timeout | Không coi là approval |
| MFA | Fallback downgrade | Chỉ factor được policy chấp nhận |
| Recovery | Reset request unknown account | Response chung |
| Recovery | Reset token replay | Chỉ một lần redeem |
| Recovery | Concurrent redemption | Atomic consume, một success |
| Recovery | Resend flood | Cooldown, budget và queue bounded |
| Session | Session fixation | ID rotation sau login/privilege change |
| Session | Logout/revoke | Session không còn được chấp nhận theo SLA |
| Token | Refresh token reuse | Detection và family action theo policy |
| Token | Wrong issuer/audience | Từ chối |
| Token | Revoked token | Từ chối |
| Passkey | Challenge replay | Từ chối |
| Passkey | Wrong origin/RP ID | Từ chối |
| Certificate | Expired/revoked/wrong SAN | Từ chối |
| API | Gateway bypass | Backend vẫn enforce authentication/authorization |
| API | Tenant/resource ID tampering | Từ chối object/tenant mismatch |
| API | Duplicate side effect | Idempotency và transaction state đúng |
| Bot | Challenge replay | Từ chối |
| Bot | Challenge provider outage | Degraded policy, không fail-open |
| Resilience | Rate-limit store outage | Không bỏ giới hạn ngoài fallback đã duyệt |
| Resilience | Password DB/MFA outage | Không tạo authenticated session giả |
| Resilience | Queue saturation | Backpressure, bounded retry và alert |
| Privacy | Log/trace/metric scan | Không có secret hoặc raw identifier ngoài policy |
| UX | Shared NAT/VPN | False positive được kiểm soát |
| Recovery | Factor reset | Proofing, notification và audit |
| Cleanup | Kết thúc test | Synthetic state được dọn theo policy |

## 19. Ví dụ: kiểm thử login abuse theo nhiều lớp

Một ứng dụng web có password login, TOTP, session cookie và password recovery. Nhóm test tạo các synthetic account A, B, C và test client được phép.

~~~mermaid
flowchart TD
    A[Prepare synthetic accounts and test run] --> B[Baseline normal login]
    B --> C[Run bounded password failures]
    C --> D[Run multi-account spray simulation]
    D --> E[Test reset and OTP throttles]
    E --> F[Test concurrent requests and replay]
    F --> G[Test store/provider outage]
    G --> H[Inspect metrics, logs and alerts]
    H --> I[Measure legitimate user impact]
    I --> J[Cleanup and report]
~~~

Kịch bản:
1. Đo baseline login success và latency.
2. Gửi số lần password sai dưới limit, rồi vượt limit.
3. Chạy spraying simulation với password giả trên account A/B/C.
4. Kiểm tra response không tiết lộ account state.
5. Gửi reset/resend request trong sandbox và xác minh cooldown.
6. Gửi OTP sai, hết hạn, đã dùng và request song song.
7. Thử session cũ sau logout và refresh token đã rotate.
8. Làm rate-limit store timeout trong staging.
9. Kiểm tra không có fail-open và queue không tăng vô hạn.
10. Kiểm tra alert, audit, redaction và false positive.
11. Dọn account, session, challenge và test data.
12. Ghi kết quả theo test run ID và policy version.

### 19.1. Kết quả cần báo cáo

Report nên nêu:
- Scope và môi trường.
- Policy/config version.
- Test case và synthetic identity set.
- Request volume/concurrency/time window.
- Expected vs actual behavior.
- Control bypass hoặc false positive.
- Latency, availability và resource impact.
- Telemetry/alert evidence.
- Data cleanup status.
- Owner, severity và remediation.

Không đính kèm password, OTP, token hoặc session cookie trong report.

## 20. Release criteria

Một thay đổi abuse prevention chỉ nên phát hành khi:
- Các abuse case critical có test và kết quả rõ.
- Rate limit atomic và hoạt động trên nhiều instance.
- Account enumeration không có oracle dễ khai thác.
- Lockout không tạo DoS dễ dàng.
- OTP/reset/session/token replay bị từ chối.
- MFA fallback không downgrade ngoài policy.
- Dependency outage không tạo fail-open ngoài degraded mode đã duyệt.
- False positive và legitimate user impact nằm trong ngưỡng chấp nhận.
- Metrics, logs và alerts có đủ tín hiệu nhưng không chứa secret.
- Recovery và support path được kiểm thử.
- Rollback/kill switch và runbook sẵn sàng.
- Synthetic test state được cleanup.

Nếu còn bypass có thể dẫn tới account takeover, token/session reuse hoặc privilege abuse, không đánh dấu control là đạt chỉ vì dashboard có alert. Cần xử lý finding theo severity và risk acceptance có owner.

## 21. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Threat model có đầy đủ? | Brute force, spraying, stuffing, enumeration, MFA/recovery/session/API |
| Scope test có an toàn? | Synthetic accounts, staging, rate cap và kill switch |
| Rate limit có nhiều dimension? | Account, network, client/device, endpoint và global budget |
| Counter có atomic/distributed? | Boundary và concurrency tests |
| Lockout có chống DoS? | Progressive delay, expiry và recovery |
| Enumeration được kiểm tra? | Response, timing, redirect và side effect |
| MFA có abuse controls? | OTP attempts, resend, push fatigue và downgrade |
| Recovery có one-time semantics? | Expiry, purpose binding và atomic consume |
| Session/token có replay tests? | Rotation, revoke, issuer/audience và nonce |
| Passkey/certificate được kiểm tra? | Origin/RP ID, challenge, signature, expiry/revoke |
| API có backend enforcement? | Không phụ thuộc UI/gateway duy nhất |
| Bot challenge có giới hạn? | One-time, expiry, accessibility và outage policy |
| Resource exhaustion được đo? | Hash CPU, DB, queue, provider cost và p99 |
| False positive được đo? | Legitimate login/recovery completion |
| Privacy được bảo vệ? | Không credential thật hoặc secret trong telemetry |
| Alert có owner/runbook? | Threshold, sample size, severity và response |
| Fault injection có thực hiện? | Store, IdP, MFA, risk engine và queue |
| Cleanup hoàn tất? | Account/session/challenge/key test được dọn |
| Release criteria đạt? | Critical findings xử lý hoặc risk acceptance chính thức |

### Tình huống tự kiểm tra

**Tình huống 1:** Login endpoint chỉ rate limit theo IP. Có đủ để chống credential stuffing không?

**Trả lời:** Không. Attacker có thể phân tán IP; cần kết hợp account, client/device, network và global resource budget, đồng thời tránh khóa nhầm người dùng chung NAT.

**Tình huống 2:** Hệ thống khóa account sau một số lần password sai. Attacker có thể gửi password sai cho account của nạn nhân. Rủi ro là gì?

**Trả lời:** Lockout DoS. Cần progressive delay, temporary throttling, risk-based challenge và recovery an toàn; không để người ngoài khóa account lâu dài dễ dàng.

**Tình huống 3:** OTP provider timeout. Có thể coi challenge là thành công để người dùng tiếp tục không?

**Trả lời:** Không. Timeout không phải proof. Cần retry có giới hạn hoặc factor thay thế đã đăng ký và được policy chấp nhận.

**Tình huống 4:** Hai request redeem cùng reset token cùng lúc. Kết quả đúng là gì?

**Trả lời:** Token phải được consume atomically; chỉ một request thành công và request còn lại bị từ chối.

**Tình huống 5:** Một request gửi header X-Forwarded-For với IP tùy ý. Rate limiter có nên tin header đó?

**Trả lời:** Chỉ tin forwarded header từ proxy nằm trong trusted proxy configuration và đã ghi đè giá trị client gửi.

**Tình huống 6:** Một test phát hiện refresh token reuse nhưng cũng có client retry do timeout. Có nên revoke mọi session ngay không?

**Trả lời:** Cần phân tích token family, rotation state và retry semantics. Reuse là tín hiệu mạnh nhưng policy phải phân biệt race hợp lệ; không bỏ qua detection hoặc revoke diện rộng không căn cứ.

**Tình huống 7:** CAPTCHA provider lỗi. Có nên bỏ challenge cho mọi request không?

**Trả lời:** Không mặc định. Áp dụng degraded policy theo action/risk; hạn chế request nhạy cảm hoặc dùng phương thức thay thế được phê duyệt, không biến provider outage thành allow.

**Tình huống 8:** Dashboard ghi nhận nhiều failed login. Có thể kết luận credential stuffing không?

**Trả lời:** Chưa. Cần kết hợp pattern theo account, network, client, password reuse signal nếu có, success anomaly và các event khác. Một spike cũng có thể do deployment hoặc client lỗi.

## 22. Ghi nhớ

**Abuse prevention test xác minh các kiểm soát authentication chịu được hành vi tự động, request phân tán, concurrency và dependency failure mà vẫn bảo vệ người dùng hợp lệ.** Kiểm thử cần bao phủ brute force, password spraying, credential stuffing, enumeration, lockout DoS, OTP/MFA fatigue, recovery abuse, token/session replay, passkey/certificate và API business logic.

Rate limit phải xét nhiều dimension, có atomicity và hoạt động đúng trên nhiều instance. Lockout, CAPTCHA và risk scoring cần đo false positive; timeout hoặc missing signal không được coi là authentication success. Test bằng synthetic account trong môi trường có phạm vi, rate cap và kill switch. Kết hợp metrics, audit, privacy checks, fault injection và cleanup để chứng minh control có hiệu lực trước khi release.
