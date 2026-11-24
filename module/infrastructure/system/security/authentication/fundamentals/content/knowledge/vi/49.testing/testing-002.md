# Authentication negative test — Kiểm thử các trường hợp xác thực bị từ chối

Một hệ thống đăng nhập có thể vượt qua happy-path test: người dùng nhập đúng password, hoàn tất MFA và nhận session. Nhưng phần lớn lỗi bảo mật lại nằm ở những trường hợp không bình thường: password sai vẫn tạo session, token hết hạn vẫn được chấp nhận do cache, certificate sai audience được dùng cho API khác, refresh token đã bị tiêu thụ lại có thể tạo token mới, hoặc lỗi của identity provider khiến service tự động bỏ qua bước xác minh. Vì vậy, kiểm thử xác thực phải chứng minh cả những điều hệ thống **không được phép làm**.

**Authentication negative test (kiểm thử âm tính xác thực)** là tập hợp kiểm thử xác minh hệ thống từ chối an toàn khi credential, proof, trạng thái phiên, ngữ cảnh giao thức hoặc điều kiện policy không hợp lệ. Một negative test tốt không chỉ kiểm tra response là lỗi; nó còn kiểm tra không có session/token được tạo, không có side effect trái phép, không lộ thông tin nhạy cảm và trạng thái bảo mật không bị thay đổi ngoài ý muốn.

Bài học thuộc chương **Testing** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối negative testing với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập; đồng thời xây dựng bộ kiểm thử có thể phát hiện fail-open, bypass, account enumeration, race condition và lỗi thu hồi trong hệ thống xác thực.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt positive test, negative test, abuse test, resilience test và security regression test.
- Xác định security invariant cho login, MFA, passkey, certificate, token, session, federation và recovery.
- Thiết kế test case cho credential sai, thiếu, hết hạn, bị thu hồi, giả mạo hoặc dùng sai ngữ cảnh.
- Kiểm tra fail-closed và deny-by-default khi identity provider, KMS, revocation store hoặc replay cache lỗi.
- Xác minh request bị từ chối không tạo session, token, grant, credential hay side effect không mong muốn.
- Kiểm tra account enumeration qua message, status, response shape, timing và hành vi phụ.
- Kiểm tra replay, refresh token reuse, nonce reuse, concurrent requests và race condition.
- Kiểm thử issuer, audience, signature, algorithm, scope, subject, actor và tenant boundary.
- Thiết kế negative test cho OIDC/OAuth, mTLS, WebAuthn, TOTP, recovery và workload identity.
- Dùng contract, integration, property-based, fuzz và fault-injection test đúng phạm vi.
- Tổ chức test fixture, secret handling và CI pipeline an toàn, có thể lặp lại.
- Đánh giá kết quả qua security invariant và bằng chứng trạng thái, không chỉ dựa vào HTTP status.

## 2. Vì sao phải kiểm thử các trường hợp bị từ chối?

Happy-path test chứng minh một luồng hợp lệ có thể hoàn thành. Nó không chứng minh hệ thống sẽ từ chối một request gần giống nhưng thiếu một điều kiện bảo mật. Trong authentication, một sai sót nhỏ ở nhánh lỗi có thể biến thành account takeover hoặc privilege escalation.

Ví dụ:

- Password sai nhưng code vẫn gọi hàm tạo session do nhánh kiểm tra account status bị đặt sai.
- JWT chữ ký hợp lệ nhưng audience không đúng vẫn được API chấp nhận.
- TOTP code đúng nhưng challenge đã hết hạn vẫn được dùng lại.
- Refresh token đã consumed được chấp nhận lần hai khi hai request chạy song song.
- Certificate hết hạn vẫn được proxy cache kết quả xác minh cũ.
- Authorization server timeout làm gateway chuyển sang chế độ bỏ qua authentication.
- Password reset token hợp lệ nhưng không bị ràng buộc với purpose, nên có thể dùng để đổi email.

Negative test cần kiểm tra cả **từ chối** và **hệ quả của từ chối**. Một response 401 không đủ nếu backend đã tạo session, gửi payment request hoặc ghi nhận MFA enrollment trước khi trả lỗi.

### 2.1. Security invariant

Security invariant là điều kiện phải luôn đúng dù request thành công, thất bại, bị retry hoặc hệ thống gặp lỗi. Ví dụ:

- Không có session authenticated nếu password/MFA/passkey proof chưa được xác minh đầy đủ.
- Token chỉ được chấp nhận bởi đúng issuer, audience, thời hạn và policy.
- Credential revoked không thể tạo quyền mới sau khi revoke có hiệu lực theo SLA.
- Một one-time challenge không thể được consume hai lần.
- Client không thể tự khai subject, role hoặc tenant để nâng quyền.
- Lỗi dependency không tự động biến thành authentication success.
- Public error không tiết lộ principal có tồn tại hay không khi policy yêu cầu chống enumeration.
- Mọi side effect nhạy cảm chỉ xảy ra sau authentication và authorization thành công.

### 2.2. Negative test không phải chỉ gửi dữ liệu rác

Một test có giá trị cần chỉ ra điều kiện bảo mật đang được kiểm tra, điểm chấp nhận credential và trạng thái mong đợi sau khi từ chối. Gửi chuỗi ngẫu nhiên vào mọi endpoint có thể tìm crash, nhưng không thay thế được test cho protocol semantics, lifecycle và trust boundary.

## 3. Phân loại kiểm thử xác thực

| Loại kiểm thử | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Positive/authentication success | Luồng hợp lệ hoạt động | Password đúng và MFA hợp lệ tạo session |
| Negative/authentication denial | Credential hoặc context không hợp lệ bị từ chối | Token hết hạn không được chấp nhận |
| Authorization negative | Principal đã xác thực nhưng không có quyền | User A không đọc resource của tenant B |
| Abuse/security test | Kiểm tra chống lạm dụng | Password spraying bị rate limit |
| Replay test | Proof/token one-time bị phát lại không thành công | DPoP jti đã dùng bị từ chối |
| Concurrency/race test | Trạng thái không bị phá khi request đồng thời | Hai refresh request không tạo hai nhánh token |
| Resilience/fault-injection | Dependency lỗi không làm fail-open | Revocation store timeout khiến thao tác nhạy cảm bị từ chối |
| Privacy/enumeration test | Response không tiết lộ dữ liệu | Unknown account và wrong password có public response tương đương |
| Regression test | Lỗi bảo mật cũ không tái xuất hiện | Token sai audience vẫn bị từ chối sau refactor |

Một test suite đầy đủ kết hợp nhiều loại. Không phải mọi negative test đều cần chạy ở mọi tầng: unit test kiểm tra decision logic nhanh; integration test xác minh ranh giới với IdP/KMS/database; end-to-end test chứng minh hành vi thực tế; fault-injection test kiểm tra khi dependency không hoạt động.

## 4. Xác định test boundary và test oracle

Trước khi viết test, xác định:

- **System under test:** authentication service, gateway, IdP integration, API, service mesh hay toàn flow.
- **Trust boundary:** client, browser, gateway, backend, identity provider, resource server, device hoặc workload.
- **Credential under test:** password, OTP, passkey assertion, certificate, API key, access token, refresh token hay session.
- **Invalid condition:** sai chữ ký, hết hạn, revoked, sai audience, thiếu scope, sai issuer, replay hoặc binding mismatch.
- **Expected decision:** reject, challenge, throttle, retryable error hoặc temporary unavailable.
- **Expected state:** không tạo session/token/grant; không thay credential; không thực hiện side effect.
- **Observable evidence:** response, database state, audit event, downstream call count, cache state và propagation acknowledgement.

### 4.1. Test oracle

Test oracle là căn cứ xác định kết quả đúng. Với authentication, oracle không nên chỉ là “status != 200”. Hãy xác minh:

1. Request bị từ chối theo contract.
2. Không có authenticated session mới.
3. Không có access/refresh token hoặc delegated grant mới.
4. Không có thay đổi credential/account ngoài ý muốn.
5. Không có downstream operation trái phép.
6. Audit ghi đúng event/reason category nhưng không chứa secret.
7. Retry cùng request không làm phát sinh side effect thứ hai.

### 4.2. State trước và sau test

Chụp trạng thái fixture trước khi gửi request: account status, credential references, session count, token family state, recovery challenges và downstream mock call count. Sau test, so sánh với expected state. Đây là cách phát hiện lỗi “response từ chối nhưng side effect đã xảy ra”.

## 5. Test matrix cho password authentication

Password login cần kiểm tra cả credential verification, account state, rate limiting và session creation.

| Điều kiện | Kết quả mong đợi | Trạng thái cần xác minh |
| --- | --- | --- |
| Password sai | Từ chối theo public error contract | Không tạo session/token |
| Principal không tồn tại | Từ chối, không tiết lộ existence | Public response tương đương password sai |
| Password rỗng/thiếu | Từ chối input | Không gọi KDF vô hạn hoặc tạo session |
| Password vượt giới hạn đầu vào | Từ chối an toàn | Không cắt ngắn âm thầm, không gây resource exhaustion |
| Password Unicode/normalization khác | Xử lý theo policy nhất quán | Không tạo ambiguity giữa register và login |
| Verifier format hỏng | Từ chối và ghi diagnostic | Không fallback sang hash yếu |
| KDF algorithm không được phép | Từ chối/đưa vào migration flow | Không tự chọn thuật toán do DB chỉ định tùy ý |
| KDF parameters vượt giới hạn | Từ chối parser | Không cấp phát CPU/RAM không giới hạn |
| Password đúng nhưng account disabled | Không tạo session | Account state không bị lộ trước khi xác minh |
| Password đúng nhưng account locked | Không tạo session theo policy | Lockout không bị bypass qua endpoint khác |
| Password đúng nhưng password reset required | Yêu cầu flow đổi password | Chưa cấp session quyền đầy đủ |
| Password đúng nhưng cần MFA | Chỉ tạo trạng thái pre-auth/challenge | Chưa tạo authenticated session |
| Password sai liên tục | Rate limit/throttle theo policy | Không khóa tài khoản vĩnh viễn dễ bị DoS |
| Legacy verifier | Xác minh theo migration policy | Rehash chỉ sau thành công, không ghi đè password mới |

### 5.1. Kiểm tra timing và enumeration

Chạy nhiều lần với:

- Principal không tồn tại.
- Principal tồn tại nhưng password sai.
- Principal tồn tại nhưng disabled/locked.
- Verifier legacy và verifier hiện hành.

So sánh status, body, headers, response length và phân bố latency. Không yêu cầu mọi request có thời gian tuyệt đối giống nhau; cần chứng minh không có khác biệt ổn định đủ để phân loại account. Dùng dummy KDF cho principal không tồn tại và rate limit để cân bằng rủi ro.

### 5.2. Kiểm tra password reset

- Reset token sai, hết hạn, revoked hoặc đã dùng phải bị từ chối.
- Token reset password không được dùng để đổi email/MFA.
- Token phải gắn principal và purpose.
- Hai request consume cùng token đồng thời chỉ có một transaction thành công.
- Response không tiết lộ email có tồn tại hay không.
- Password mới phải được lưu bằng KDF hiện hành và salt mới.
- Session/refresh family cũ được xử lý theo policy sau reset.

## 6. Test matrix cho MFA và passkey

### 6.1. TOTP và challenge

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| OTP sai | Từ chối; không tạo session |
| OTP hết cửa sổ thời gian | Từ chối theo clock-skew policy |
| OTP đúng nhưng challenge hết hạn | Từ chối |
| OTP đã được dùng trong challenge one-time | Từ chối replay |
| Challenge thuộc principal khác | Từ chối |
| Challenge purpose không khớp | Từ chối |
| Challenge bị revoke/cancel | Từ chối |
| Nhiều lần đoán OTP | Rate limit/throttle và audit |
| TOTP seed chưa được xác minh enrollment | Không dùng làm factor active |
| Hai request consume cùng challenge | Atomic consume chỉ cho một request thành công |

Test clock skew bằng clock giả/frozen clock thay vì sleep trong test. Kiểm tra cả biên trước/sau cửa sổ thời gian.

### 6.2. Push MFA

- Challenge ID không tồn tại hoặc thuộc user khác bị từ chối.
- Approval từ thiết bị không gắn với challenge không được chấp nhận.
- Challenge hết hạn hoặc đã bị cancel không thể approve.
- Approval lặp lại không tạo nhiều session hoặc side effect.
- Challenge number matching sai bị từ chối.
- Push provider timeout không được coi là approval.
- Nhiều challenge trong thời gian ngắn kích hoạt abuse policy.

### 6.3. Passkey/WebAuthn

Kiểm tra các trường hợp:

- Signature không hợp lệ.
- Credential ID không tồn tại hoặc không thuộc principal.
- Challenge sai, hết hạn hoặc đã dùng.
- RP ID hoặc origin không khớp.
- Type của client data không đúng.
- User presence/verification không đáp ứng policy.
- Authenticator counter/backup state bất thường theo policy và semantics authenticator.
- Assertion được gửi lại.
- Credential đã bị disable/revoke.
- Credential mới được thêm từ flow chưa đủ re-authentication.

Không tự động kết luận mọi authenticator counter không tăng là tấn công; nhiều passkey synced có counter semantics khác nhau. Test phải theo WebAuthn profile và policy thực tế.

### 6.4. Recovery code

- Code sai, hết hạn, đã dùng hoặc thuộc account khác bị từ chối.
- Code chỉ được consume một lần, kể cả hai request đồng thời.
- Bộ code cũ bị revoke khi tạo bộ mới theo policy.
- Response không tiết lộ số code còn lại cho unauthenticated caller.
- Recovery không tự bỏ qua bước xác minh độc lập cần thiết.

## 7. Test matrix cho certificate và workload identity

Certificate authentication cần kiểm tra chain, identity binding, usage, expiry, trust domain và revocation.

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| Certificate hết hạn | Từ chối |
| Certificate chưa tới notBefore | Từ chối |
| Chain không tin cậy | Từ chối |
| Issuer/CA không được allowlist | Từ chối |
| SAN/URI SAN không đúng workload | Từ chối |
| EKU/key usage không phù hợp | Từ chối |
| Certificate revoked | Từ chối theo revocation SLA |
| Private key không khớp certificate | TLS/authentication thất bại |
| Certificate staging dùng ở production | Từ chối do trust domain/environment mismatch |
| Workload attestation stale hoặc replay | Identity issuer từ chối |
| Federation issuer/subject/audience sai | Không cấp token |
| Service account bị disable | Không cấp credential mới; credential cũ xử lý theo policy |
| Metadata endpoint lỗi | Không fallback sang secret tĩnh ngoài policy |

### 7.1. Negative test cho mTLS

Kiểm tra cả hai chiều:

- Client từ chối server certificate sai hostname/issuer/expiry.
- Server từ chối client certificate sai trust domain/identity/usage.
- Proxy không được phép tự đặt identity header.
- TLS termination không làm mất binding giữa client certificate và backend principal.
- Trust bundle rotation không vô tình chấp nhận CA cũ sau deadline.

## 8. Test matrix cho access token, refresh token và session

### 8.1. Token validation

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| Token thiếu hoặc sai format | Từ chối |
| Signature sai | Từ chối |
| Algorithm ngoài allowlist | Từ chối |
| Issuer không tin cậy | Từ chối |
| Audience không khớp API | Từ chối |
| Expiry đã qua | Từ chối |
| Not-before ở tương lai | Từ chối |
| Scope thiếu | Authentication có thể hợp lệ nhưng authorization từ chối |
| Tenant/subject mismatch | Từ chối |
| Key ID không tồn tại hoặc key đã retire | Từ chối theo key rotation policy |
| Token bị revoke | Từ chối theo cơ chế revocation đã cam kết |
| Token có claim sai kiểu/giá trị | Từ chối an toàn, không crash |

### 8.2. Refresh token rotation

- Refresh token sai/unknown bị từ chối.
- Token expired/revoked/consumed không cấp token mới.
- Reuse detection kích hoạt khi token đã consume quay lại.
- Hai request đồng thời không tạo hai descendant token hợp lệ.
- Response bị mất và retry được xử lý theo idempotency policy.
- Token family revoked không thể refresh qua descendant.
- Client binding không khớp bị từ chối.
- Account disabled hoặc session revoked không được refresh.

### 8.3. Session

- Session ID ngẫu nhiên không tồn tại bị từ chối.
- Session hết hạn hoặc revoked không được dùng.
- Session cũ bị rotate sau login/step-up theo policy.
- Cookie thiếu Secure/HttpOnly/SameSite không được phát trong production config.
- CSRF token/origin check sai bị từ chối với cookie-authenticated mutation.
- Session của user A không truy cập dữ liệu user B.
- Logout/revoke được áp dụng ở mọi node theo SLA.
- Session fixation test chứng minh session ID trước login không được giữ làm authenticated session.

## 9. Test matrix cho OAuth, OIDC và federation

Kiểm tra authorization request và callback:

- State thiếu, sai hoặc đã dùng bị từ chối.
- Nonce sai hoặc replay bị từ chối.
- Redirect URI không khớp allowlist bị từ chối.
- Authorization code hết hạn, đã dùng hoặc client binding sai bị từ chối.
- PKCE verifier sai hoặc thiếu khi bắt buộc bị từ chối.
- ID token issuer/audience/nonce/signature/expiry sai bị từ chối.
- Token exchange client không được phép bị từ chối.
- Subject token sai issuer hoặc audience không được exchange.
- Actor/delegation chain không hợp lệ bị từ chối.
- Federation subject/tenant/environment không khớp trust policy bị từ chối.
- JWK/JWKS rotation không khiến hệ thống tin key ngoài issuer đã cấu hình.

Không chỉ test JWT parser riêng. Cần test end-to-end để xác minh callback state, session creation và token storage không xảy ra khi protocol validation thất bại.

## 10. Test matrix cho account linking và recovery

- Không tự động link hai account chỉ vì email string giống nhau.
- External issuer/subject đã liên kết với principal khác không thể chiếm liên kết.
- Link request thiếu re-authentication hoặc proof-of-control bị từ chối.
- Unlink credential cuối cùng không làm account mất mọi recovery path ngoài policy.
- Recovery challenge sai purpose/subject/tenant bị từ chối.
- Support override không thể bỏ qua approval/audit.
- Thay email/phone recovery yêu cầu step-up và notification theo policy.
- Account bị disable không thể tạo link hoặc recovery grant mới.
- Recovery session có quyền hạn giới hạn và không tự trở thành full session trước khi hoàn tất.
- Hai thao tác link/unlink đồng thời không tạo mapping mâu thuẫn.

## 11. Fail-closed và fault-injection test

Một negative test quan trọng là làm dependency lỗi có kiểm soát để xác minh hệ thống không tự bỏ qua authentication.

| Dependency/failure | Hành vi cần kiểm chứng |
| --- | --- |
| Identity provider timeout | Không tạo authenticated session; trả lỗi tạm thời theo contract |
| JWKS endpoint unavailable | Dùng cache key còn hợp lệ theo policy hoặc fail closed; không bỏ signature check |
| KMS/HSM unavailable | Không bỏ qua ký/xác minh hoặc chuyển sang secret yếu |
| Revocation store unavailable | Hành động nhạy cảm fail closed hoặc dùng cache trong SLA đã phê duyệt |
| Replay cache unavailable | One-time proof không được accept nếu không thể kiểm tra replay |
| Session database unavailable | Không tạo session giả hoặc trả success khi state chưa commit |
| MFA provider timeout | Không coi timeout là approval |
| Email/SMS provider lỗi | Recovery request có trạng thái retryable; không báo đã gửi nếu chưa được commit theo contract |
| Message broker unavailable | Không mất security event/alert; dùng outbox hoặc retry bền vững |
| Clock skew | Token/challenge validation theo tolerance hữu hạn; không mở cửa sổ vô hạn |
| Network partition giữa region | Không có hai token family/session state trái ngược được chấp nhận |

### 11.1. Fail closed có chọn lọc

Fail closed nghĩa là không cấp quyền khi không thể xác minh điều kiện cần thiết. Nó không có nghĩa mọi tính năng phải dừng hoàn toàn. Có thể trả 503, yêu cầu retry hoặc dùng cache còn hợp lệ với giới hạn rõ. Điều cấm là coi “không kiểm tra được” tương đương “đã xác thực”.

### 11.2. Kiểm tra partial failure

Ví dụ: password KDF xác minh thành công, nhưng session store commit thất bại. Hệ thống phải không trả success token nếu session/grant chưa commit theo kiến trúc. Nếu token đã phát ra trước khi transaction thất bại, cần kiểm tra cleanup/compensation và không để credential mồ côi còn hiệu lực.

## 12. Replay, concurrency và race condition

Authentication thường có thao tác stateful: consume challenge, rotate refresh token, create session, register passkey hoặc update recovery method. Các thao tác này cần test đồng thời.

### 12.1. One-time consume

Chạy N request đồng thời với cùng một nonce, OTP challenge hoặc recovery code. Kết quả mong đợi là tối đa một lần consume thành công; các request còn lại bị từ chối hoặc nhận kết quả idempotent đã commit theo thiết kế.

### 12.2. Refresh race

Hai request dùng cùng refresh token cùng lúc:

- Chỉ một state transition ACTIVE → CONSUMED thành công.
- Không tạo hai nhánh descendant token.
- Retry được phân biệt bằng operation ID/client binding.
- Reuse policy không bị bypass bởi cache stale.
- Family revoke lan tới các node liên quan.

### 12.3. Account state race

Chạy đồng thời:

- Admin disable account trong lúc login.
- User đổi password trong lúc login rehash.
- Revoke session trong lúc refresh.
- Xóa passkey trong lúc assertion verification.
- Unlink IdP trong lúc callback.

Hệ thống cần có thứ tự commit và kiểm tra version/state để thao tác cũ không ghi đè trạng thái mới. Không cấp session nếu account đã bị disable trước điểm commit cuối cùng.

### 12.4. Idempotency

Retry của request hợp lệ không nên tạo side effect lặp. Tuy nhiên, idempotency key không thay thế authentication. Key phải gắn với principal/client, operation, payload hash và TTL; dùng lại key với payload khác phải bị từ chối.

## 13. Privacy và account enumeration trong negative tests

Negative test phải kiểm tra những thông tin có thể quan sát từ bên ngoài:

- Message/error code.
- HTTP status, headers, redirects.
- Response body size/schema.
- Timing distribution.
- Email/SMS/push side effect.
- Rate-limit behavior.
- Thay đổi trạng thái qua endpoint khác.

### 13.1. Response parity

Với các tình huống cần giữ kín như principal không tồn tại và password sai, so sánh public response theo contract. Internal diagnostic vẫn được phép phân biệt reason code để điều tra.

### 13.2. Không chỉ so sánh một lần

Timing test cần nhiều lần chạy, phân bố và kiểm soát noise của CI/network. Dùng test environment ổn định, warm/cold cache scenarios và cùng profile KDF. Đặt ngưỡng thống kê phù hợp; không tuyên bố timing-safe chỉ vì hai request mẫu gần bằng nhau.

### 13.3. Secret redaction

Gửi test credential marker duy nhất qua request rồi kiểm tra log/trace/error/queue không chứa marker ở dạng raw. Kiểm tra cả Authorization header, cookie, OTP, reset token, client secret và private key fixture. Không dùng credential production thật để làm test marker.

## 14. Property-based, fuzz và protocol mutation

Ngoài test case viết tay, có thể tạo input biến đổi để kiểm tra invariant:

- Token claim thiếu, sai kiểu, quá dài, duplicate hoặc không chuẩn.
- JWT header có algorithm/key ID bất thường.
- Certificate chain sâu, extension lạ hoặc SAN format không hợp lệ.
- JSON body có field lặp, Unicode edge case hoặc payload quá lớn.
- URL/redirect URI có encoding khác, fragment hoặc host confusion.
- WebAuthn client data/challenge có encoding lỗi.
- OIDC state/nonce/code có giá trị rỗng, duplicate hoặc replay.
- HTTP header trùng lặp, whitespace hoặc casing bất thường.

Fuzz test nên nhắm parser/validator trong môi trường cô lập, có giới hạn CPU/memory/time. Một test fuzz thành công không được tạo session hoặc gọi hệ thống thật. Seed corpus cần có case hợp lệ và không hợp lệ để tránh chỉ test crash.

### 14.1. Property/invariant examples

- Với mọi token không thỏa issuer/audience/expiry policy, authorization decision không thể là allow.
- Với một one-time challenge ID, số lần consume thành công không vượt quá một.
- Với principal disabled, mọi login/refresh mới đều bị từ chối theo policy.
- Với tenant mismatch, không có dữ liệu tenant khác được trả.
- Với invalid proof, downstream side effect count bằng không.
- Với secret marker, không có telemetry sink nào lưu marker nguyên vẹn.

## 15. Test fixture và môi trường an toàn

Test authentication dễ vô tình tạo credential có thể sử dụng hoặc gửi notification thật. Cần quản lý fixture như một tài sản bảo mật.

### Nguyên tắc

- Dùng identity provider sandbox hoặc test tenant riêng.
- Tạo user/service account giả lập, không dùng account nhân viên thật.
- Dùng certificate/key/token test có thời hạn ngắn và scope hạn chế.
- Không dùng password, OTP seed, recovery code hoặc private key production.
- Mock email/SMS/push; không gửi tới số điện thoại/email thật trừ test được phê duyệt.
- Không để test token vào snapshot, golden file, CI artifact hoặc log.
- Reset database/fixture có kiểm soát và tránh tái sử dụng token family cũ.
- Dùng clock injection để test expiry, không thay clock hệ thống CI.
- Tách test secret khỏi source code và rotate khi lộ.

### 15.1. Test data

Fixture có thể mô tả trạng thái:

| Fixture | Mục đích |
| --- | --- |
| active-user | Kiểm tra luồng hợp lệ |
| disabled-user | Kiểm tra account status |
| user-with-mfa | Kiểm tra MFA challenge |
| user-with-passkey | Kiểm tra WebAuthn assertion |
| revoked-session | Kiểm tra session denial |
| consumed-refresh-family | Kiểm tra refresh reuse |
| expired-certificate | Kiểm tra certificate expiry |
| wrong-audience-token | Kiểm tra resource boundary |
| tenant-a-user / tenant-b-resource | Kiểm tra tenant isolation |
| workload-with-limited-scope | Kiểm tra service authorization |

Fixture cần tạo mới theo test run hoặc namespace cô lập. Không để một test làm thay đổi trạng thái khiến test khác pass/fail không ổn định.

## 16. CI pipeline và tiêu chí release

Một pipeline có thể chia:

1. **Unit tests:** password verifier policy, token claim validation, state transition, error mapping.
2. **Component tests:** authentication service với fake IdP/KMS/session store.
3. **Integration tests:** test tenant với IdP, database, cache, message broker và service mesh.
4. **Contract tests:** issuer/consumer token claims, error schema, mTLS identity và event schema.
5. **Security regression tests:** các bug cũ, replay, enumeration, audience confusion, privilege escalation.
6. **Fault injection:** timeout, unavailable dependency, partial commit, stale cache và clock skew.
7. **End-to-end tests:** browser/mobile login, MFA, logout, recovery và sensitive operation.

### 16.1. Release gate

Không release nếu:

- Invalid credential có thể tạo authenticated session.
- Sai issuer/audience/signature hoặc expired token được chấp nhận.
- Replayed one-time proof/challenge tạo side effect lần hai.
- Refresh race tạo nhiều descendant token hợp lệ.
- Dependency outage khiến authentication fail-open ngoài policy.
- Cross-tenant access test thành công.
- Error response tiết lộ account existence hoặc secret.
- Revoked credential vẫn được chấp nhận vượt SLA.
- Test log/artifact chứa credential marker hoặc secret.

Không yêu cầu mọi test phải có cùng thời gian chạy. Chạy test nhanh ở mỗi commit; test phân tán/fault-injection nặng hơn có thể chạy ở pipeline phù hợp, nhưng các release gate quan trọng phải được tự động hóa và có owner.

## 17. Pseudocode: kiểm thử negative authentication

Ví dụ minh họa một test kiểm tra cả response lẫn side effect:

~~~ts
test("expired token is denied without side effects", async () => {
  const fixture = await testIdentity.createPrincipal({
    status: "ACTIVE",
    scopes: ["orders.read"]
  });
  const expiredToken = await testTokens.issue({
    subject: fixture.subject,
    audience: "orders-api",
    expiresAt: testClock.nowMinusSeconds(30)
  });

  const before = await testState.snapshot({
    subject: fixture.subject,
    includeSessions: true,
    includeTokenFamilies: true,
    includeDownstreamCalls: true
  });

  const response = await api.get("/orders", {
    headers: { Authorization: "Bearer " + expiredToken }
  });

  const after = await testState.snapshot({
    subject: fixture.subject,
    includeSessions: true,
    includeTokenFamilies: true,
    includeDownstreamCalls: true
  });

  expect(response.status).toBe(401);
  expect(after.sessions).toEqual(before.sessions);
  expect(after.tokenFamilies).toEqual(before.tokenFamilies);
  expect(after.downstreamCalls).toBe(before.downstreamCalls);
  expect(await telemetry.containsSecret(expiredToken)).toBe(false);
});
~~~

Đây là pseudocode; cú pháp cụ thể phụ thuộc test framework. Trong test thực tế, không in token khi assertion fail. Test helper phải so sánh reference/trạng thái mà không đưa secret vào output. Với API có introspection/revocation, kiểm tra thêm decision ở resource server và propagation SLA.

## 18. Ví dụ kiểm thử: MFA chưa hoàn tất nhưng session được tạo

Một bug được phát hiện: sau khi password đúng, endpoint login tạo session cookie trước khi MFA challenge hoàn tất. Nếu người dùng bỏ qua MFA endpoint nhưng vẫn giữ cookie, họ có thể gọi API như đã đăng nhập.

### Test case

1. Tạo fixture user yêu cầu TOTP.
2. Gửi password đúng tới login endpoint.
3. Nhận pre-auth challenge và kiểm tra trạng thái chưa authenticated.
4. Không gửi OTP; thử dùng mọi cookie/token nhận được để gọi protected API.
5. Xác minh protected API từ chối.
6. Kiểm tra session store không có session authenticated; nếu có pre-auth session, scope của nó chỉ cho phép hoàn tất MFA.
7. Gửi OTP sai/hết hạn và lặp challenge; không tạo full session.
8. Gửi OTP đúng; chỉ lúc này mới tạo authenticated session theo policy.
9. Kiểm tra session ID được rotate từ pre-auth sang authenticated nếu kiến trúc yêu cầu.
10. Kiểm tra audit và telemetry không chứa password/OTP/token.

### Invariant

Password verification thành công chỉ chứng minh một yếu tố. Khi policy yêu cầu MFA, quyền truy cập đầy đủ chỉ được cấp sau khi challenge hợp lệ được consume và trạng thái authentication được commit.

## 19. Tiêu chí chấp nhận và kiểm thử tổng hợp

| Nhóm | Negative case bắt buộc | Bằng chứng PASS |
| --- | --- | --- |
| Password | Sai, missing, legacy, malformed verifier, account disabled | Không có full session; response an toàn; audit đúng |
| MFA | OTP sai/hết hạn/replay, push timeout, challenge mismatch | Không có authenticated session hoặc side effect |
| Passkey | Signature/challenge/origin/RP ID sai, credential revoked | Assertion bị từ chối |
| Certificate | Chain/issuer/SAN/EKU/expiry/revocation sai | TLS/client authentication thất bại |
| Access token | Signature/issuer/audience/expiry/scope sai | Resource server từ chối |
| Refresh token | Consumed/revoked/expired, family race, client mismatch | Không cấp descendant ngoài policy |
| Session | Expired/revoked/fixation/CSRF/cross-user | Protected resource bị từ chối |
| OAuth/OIDC | State/nonce/PKCE/redirect/code/issuer sai | Callback không tạo session/token |
| Recovery | Purpose/subject/expiry/replay sai | Credential/account không bị đổi |
| Account linking | External subject đã link hoặc proof thiếu | Không thay đổi mapping |
| Workload | Attestation stale, issuer/audience sai, cert revoked | Không cấp/không chấp nhận workload credential |
| Distributed | Revocation cache stale, event trễ, node partition | Validator tuân thủ SLA; không fail-open |
| Privacy | Enumeration/timing/secret logging | Public response an toàn; telemetry không chứa secret |
| Concurrency | Consume/refresh/link/update cùng lúc | State transition nhất quán, không tạo duplicate |
| Resilience | IdP/KMS/session/replay store outage | Không cấp quyền khi thiếu bằng chứng cần thiết |

### Chỉ số chất lượng test

Theo dõi coverage theo security invariant, protocol branch, credential type, trust boundary và failure mode. Đo số regression case, số test flaky, tỷ lệ test negative có state assertion, thời gian propagation được kiểm chứng và số lỗi bị phát hiện trước release. Code coverage đơn thuần không chứng minh các đường từ chối bảo mật đã được kiểm thử.

## 20. Bài tập tự kiểm tra

Một nền tảng hỗ trợ password, passkey, TOTP, OIDC login và API access token. Một bản release mới thay đổi middleware authentication và refresh token store. Sau deploy, nhóm phát triển cần chứng minh thay đổi không mở đường bypass.

Hãy:

1. Liệt kê security invariant phải giữ cho login, MFA, token và session.
2. Thiết kế negative test matrix cho password sai, MFA chưa hoàn tất, token sai audience và session revoked.
3. Tạo test cho hai refresh request đồng thời dùng cùng token.
4. Mô tả cách fault-inject khi IdP, JWKS, KMS và revocation store timeout.
5. Thiết kế test chứng minh response không tiết lộ account existence.
6. Kiểm tra không có session/token/downstream side effect khi request bị từ chối.
7. Đề xuất fixture an toàn và cách bảo vệ secret trong CI artifacts.
8. Xây dựng release gate cho các regression quan trọng.

**Gợi ý đánh giá:** câu trả lời tốt phải nêu expected decision và expected state, test cả response lẫn side effect, bao gồm race/failure/privacy và có bằng chứng tại validator. Không coi HTTP 401 là bằng chứng đầy đủ nếu hệ thống vẫn tạo session hoặc thực hiện thao tác phía sau.

---

**Ghi nhớ:** authentication negative test chứng minh hệ thống từ chối đúng khi credential hoặc trust context không hợp lệ. Với mỗi test, hãy xác định **điều kiện bị từ chối, security invariant, response contract và trạng thái sau request**. Kiểm tra cả password/MFA/passkey/certificate/token/session/federation/recovery, replay và concurrency, dependency outage, privacy và downstream side effect. Một request trả 401 vẫn có thể là lỗi bảo mật nếu session đã được tạo hoặc hành động trái phép đã chạy. Dùng fixture cô lập, không dùng secret production và biến các invariant quan trọng thành release gate tự động.
