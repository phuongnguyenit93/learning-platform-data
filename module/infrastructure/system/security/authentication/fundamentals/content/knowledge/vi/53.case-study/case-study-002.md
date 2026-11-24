# Đăng nhập bằng MFA — Case study thiết kế luồng xác thực cho một nền tảng SaaS

## Bối cảnh

Công ty Sao Mai vận hành một nền tảng SaaS quản lý đơn hàng và dữ liệu khách hàng cho nhiều doanh nghiệp. Người dùng đăng nhập bằng email và password. Một số khách hàng yêu cầu bật xác thực đa yếu tố (MFA) vì tài khoản có thể xem thông tin cá nhân, xuất dữ liệu hoặc thay đổi người thụ hưởng thanh toán. Đội vận hành cũng có tài khoản quản trị có quyền cấu hình tenant, quản lý nhân viên và tích hợp dịch vụ.

Phiên bản đầu của hệ thống chỉ kiểm tra password rồi tạo session cookie. Sau một đợt credential stuffing, Sao Mai quyết định triển khai MFA. Đội dự án phải giải quyết nhiều câu hỏi cùng lúc: yếu tố thứ hai nào được chấp nhận, lúc nào yêu cầu MFA, làm thế nào tránh tạo session trước khi hoàn tất challenge, recovery ra sao khi người dùng mất điện thoại, và làm sao chứng minh các API phía sau thật sự yêu cầu mức xác thực phù hợp.

Case study này mô tả cách phân tích và thiết kế một luồng đăng nhập MFA có thể triển khai. Các tên tổ chức, endpoint, ngưỡng và dữ liệu ví dụ đều là giả định phục vụ học tập; khi áp dụng thực tế cần hiệu chỉnh theo threat model, quy mô, chính sách và nghĩa vụ tuân thủ của tổ chức.

## 1. Mục tiêu và phạm vi

Sao Mai đặt ra các mục tiêu:

1. Giảm nguy cơ account takeover khi password bị lộ hoặc tái sử dụng.
2. Không cấp session đầy đủ cho tới khi hoàn thành mọi yếu tố bắt buộc.
3. Hỗ trợ TOTP cho giai đoạn chuyển đổi và passkey cho người dùng có authenticator tương thích.
4. Yêu cầu xác thực mạnh hơn cho tài khoản quản trị và thao tác nhạy cảm.
5. Bảo vệ enrollment, replacement, recovery và revoke của authenticator.
6. Không tiết lộ tài khoản có tồn tại hay không qua login hoặc recovery error.
7. Có audit, monitoring, runbook và test chứng minh policy được thực thi.

Phạm vi gồm browser login, API session, MFA challenge, passkey, recovery code, account recovery và session lifecycle. Luồng service-to-service được đề cập ở phần liên quan, nhưng không dùng MFA người dùng cho workload; workload cần identity và credential riêng.

### Ngoài phạm vi

- Thiết kế identity proofing cho việc mở tài khoản mới.
- Định nghĩa chi tiết mọi yêu cầu pháp lý của từng quốc gia/ngành.
- Triển khai một IdP hoặc thư viện WebAuthn cụ thể.
- Quyết định một ngưỡng risk score phù hợp cho mọi tenant.

## 2. Các chủ thể và tài sản cần bảo vệ

### Chủ thể

| Chủ thể | Vai trò | Quyền điển hình |
| --- | --- | --- |
| Customer user | Nhân viên của khách hàng | Xem/tạo đơn hàng, cập nhật dữ liệu trong tenant |
| Tenant admin | Quản trị tenant | Mời/xóa user, quản lý role, cấu hình MFA |
| Sao Mai operator | Nhân viên vận hành nền tảng | Hỗ trợ và xử lý sự cố theo quyền giới hạn |
| Identity service | Thành phần xác minh credential và phát session/token | Tạo challenge, kiểm tra proof, quản lý session |
| Risk service | Phân tích tín hiệu đăng nhập | Gợi ý allow, step-up hoặc deny theo policy |
| Notification service | Gửi thông báo bảo mật | Gửi email/push sau sự kiện đã commit |

### Tài sản

- Dữ liệu khách hàng, đơn hàng và thông tin thanh toán.
- Password verifier và credential metadata.
- TOTP secret, passkey public key/credential record và recovery code verifier.
- Pre-authentication state, MFA challenge và session cookie.
- Access token, refresh token và token family.
- Email/phone recovery và liên kết external identity.
- Audit log, risk signal, policy configuration và signing key.

### Mức tác động

Tài khoản customer user có thể truy cập dữ liệu trong một tenant. Tenant admin có thể thay đổi quyền của nhiều người. Sao Mai operator có thể tác động nhiều tenant nên cần kiểm soát đặc quyền riêng, phishing-resistant MFA và quy trình approval. Không áp dụng cùng một mức session và recovery cho mọi nhóm.

## 3. Threat model

Đội dự án xác định các mối đe dọa chính:

| Mối đe dọa | Kịch bản | Kiểm soát chính |
| --- | --- | --- |
| Credential stuffing | Attacker thử password từ các vụ rò rỉ khác | MFA, breached-password defense, rate limit, bot detection |
| Password phishing | Người dùng nhập password vào trang giả | Passkey/WebAuthn, domain education, risk controls |
| OTP phishing/relay | Attacker lấy TOTP rồi chuyển tiếp trong thời gian mã còn hiệu lực | Passkey ưu tiên, challenge binding, rate limit, short window |
| MFA fatigue | Attacker gửi nhiều push để người dùng bấm approve | Không dùng push approval đơn giản làm phương thức chính; number matching và giới hạn challenge |
| Session theft | Malware lấy cookie sau login | Secure/HttpOnly/SameSite, short lifetime phù hợp, revoke, device/risk monitoring |
| Replay | Challenge hoặc OTP đã dùng được gửi lại | One-time consume, nonce, atomic state transition |
| Recovery abuse | Attacker chiếm email hoặc lừa support để reset MFA | Recovery proofing, hold, notification, dual control |
| Account enumeration | Error khác nhau tiết lộ email có tài khoản | Response parity, timing controls, generic public errors |
| Privilege escalation | User thường tự khai role/tenant hoặc dùng session yếu cho admin API | Authorization server-side, step-up, tenant binding |
| Dependency outage | IdP/MFA provider timeout khiến hệ thống bỏ qua MFA | Fail closed hoặc trạng thái retryable, không fail-open |

### Ranh giới tin cậy

~~~mermaid
flowchart TD
    B[Browser / user device] -->|TLS| G[Web gateway]
    G --> I[Identity service]
    I --> P[Password verifier]
    I --> M[MFA verifier]
    I --> R[Risk policy]
    I --> S[(Session store)]
    I --> A[Audit event pipeline]
    B -->|Authenticated cookie| G
    G --> API[Application APIs]
    API --> Z[Authorization policy]
    Z --> D[(Tenant data)]
    A --> MON[Monitoring / incident response]
    I --> N[Notification outbox]
    N --> NS[Email / push provider]
~~~

Browser, email inbox và mạng người dùng không được coi là trusted environment. Gateway phải xóa các identity header do client tự gửi. API phải xác minh session/token và áp dụng authorization; không tin rằng request đã đi qua gateway thì mặc nhiên hợp lệ.

## 4. Yêu cầu xác thực theo nhóm người dùng và hành động

Sao Mai xác định policy mẫu:

| Nhóm/hành động | Yêu cầu |
| --- | --- |
| Customer user đăng nhập | Password + một MFA factor đã đăng ký, hoặc passkey theo profile được chấp nhận |
| Tenant admin đăng nhập | MFA bắt buộc; ưu tiên passkey/security key chống phishing |
| Sao Mai operator | Phishing-resistant MFA, tài khoản đặc quyền riêng và privileged access workflow |
| Xem dữ liệu thông thường | Session hợp lệ và authorization theo tenant/role |
| Export dữ liệu lớn | Step-up gần thời điểm thao tác, risk check và audit |
| Thêm/xóa authenticator | Re-authentication đủ mạnh, notification và audit |
| Đổi email/phone recovery | Step-up, kiểm tra risk và thông báo tới kênh cũ/mới |
| Tạo API key hoặc OAuth client | Step-up; giới hạn scope và hiển thị secret một lần theo policy |
| Service gọi service | Workload identity/mTLS hoặc token federation; không dùng MFA tương tác |

Policy này là quyết định sản phẩm giả định. Nếu tổ chức có yêu cầu assurance cụ thể từ tiêu chuẩn hoặc hợp đồng, phải ánh xạ policy tới đúng profile và phiên bản áp dụng.

## 5. Chọn phương thức MFA

Sao Mai hỗ trợ hai hướng:

### TOTP trong giai đoạn chuyển đổi

TOTP có ưu điểm là tương thích với nhiều ứng dụng authenticator và không cần push provider. Tuy nhiên, mã TOTP có thể bị phishing hoặc relay. Vì vậy Sao Mai dùng TOTP như một phương thức MFA được chấp nhận cho nhóm phù hợp, nhưng không gọi nó là phishing-resistant.

Các yêu cầu:

- TOTP secret được sinh ngẫu nhiên, mã hóa khi lưu và chỉ hiển thị trong enrollment một lần.
- Enrollment chỉ active sau khi người dùng xác minh một mã hợp lệ.
- Challenge gắn với principal, purpose, pre-auth session và expiry.
- Một time-step đã được chấp nhận không được dùng lại cho cùng factor.
- Rate limit theo account, source và challenge.
- Không ghi seed hoặc OTP vào log, trace hay support ticket.

### Passkey/WebAuthn

Passkey được khuyến nghị cho user có thiết bị tương thích và bắt buộc cho một số nhóm đặc quyền theo policy. WebAuthn ràng buộc proof với RP ID/origin và challenge nên chống phishing tốt hơn OTP khi được triển khai đúng.

Các yêu cầu:

- Server tạo challenge ngẫu nhiên, ngắn hạn và one-time.
- Kiểm tra origin, RP ID hash, challenge, credential ID, chữ ký và user verification theo policy.
- Credential phải được gắn với đúng principal.
- Enrollment/replacement yêu cầu re-authentication đủ mạnh.
- Private key không được gửi về server; server lưu public key và metadata cần thiết.
- Revocation phía server được áp dụng cho credential record và session liên quan.

### Push MFA không phải mặc định

Sao Mai chưa chọn push approval một chạm làm phương thức chính vì nguy cơ MFA fatigue. Nếu bổ sung trong tương lai, phải có number matching, context hiển thị rõ, giới hạn challenge và telemetry phát hiện approve sau chuỗi deny/timeout.

## 6. Trạng thái của luồng đăng nhập

Luồng login được mô hình hóa thành state machine để tránh cấp session quá sớm:

~~~mermaid
stateDiagram-v2
    [*] --> ANONYMOUS
    ANONYMOUS --> PASSWORD_VERIFIED: password hợp lệ
    ANONYMOUS --> PASSKEY_VERIFIED: passkey assertion hợp lệ
    ANONYMOUS --> DENIED: password sai / account không đủ điều kiện
    PASSWORD_VERIFIED --> MFA_PENDING: policy yêu cầu MFA
    MFA_PENDING --> AUTHENTICATED: proof MFA hợp lệ và consume thành công
    PASSKEY_VERIFIED --> AUTHENTICATED: policy và assurance của passkey đã đáp ứng
    MFA_PENDING --> DENIED: proof sai / hết hạn / replay / bị revoke
    MFA_PENDING --> EXPIRED: challenge hết hạn
    AUTHENTICATED --> SESSION_ACTIVE: session commit thành công
    SESSION_ACTIVE --> REVOKED: logout / incident / policy revoke
    SESSION_ACTIVE --> EXPIRED: idle hoặc absolute lifetime
    DENIED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
    SESSION_ACTIVE --> [*]
~~~

Điểm quan trọng: PASSWORD_VERIFIED chưa phải session authenticated đầy đủ nếu policy yêu cầu MFA. Có thể tạo pre-authentication state giới hạn để tiếp tục challenge, nhưng state đó không được truy cập API dữ liệu.

### Invariant

1. Không có full session trước khi mọi factor bắt buộc được xác minh.
2. MFA challenge gắn với đúng principal và pre-authentication flow.
3. Challenge chỉ được consume một lần.
4. Session chỉ được tạo sau khi policy decision và state transition commit thành công.
5. Retry không tạo nhiều session hoặc nhiều notification không cần thiết.
6. User/tenant/role lấy từ server-side identity context, không lấy từ form field tự khai.

## 7. Luồng password + TOTP chi tiết

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant G as Gateway
    participant I as Identity Service
    participant M as MFA Verifier
    participant S as Session Store
    U->>B: Nhập email và password
    B->>G: POST /login qua TLS
    G->>I: Xác minh request và rate limit
    I->>I: Kiểm tra password verifier và account state
    I-->>B: Pre-auth challenge (không phải full session)
    U->>B: Nhập mã TOTP
    B->>G: POST /mfa/verify
    G->>I: Challenge + proof
    I->>M: Kiểm tra TOTP, time-step và one-time state
    M-->>I: Proof hợp lệ
    I->>I: Đánh giá risk và authentication policy
    I->>S: Commit authenticated session
    S-->>I: Session reference
    I-->>B: Set-Cookie session an toàn
    B-->>U: Đăng nhập thành công
~~~

### Bước 1: nhận thông tin đăng nhập

Browser gửi email/password qua TLS. Gateway áp dụng request size limit, rate limit và xóa identity header do client tự gửi. Không ghi request body vào access log.

### Bước 2: xác minh password

Identity service chuẩn hóa identifier theo policy, tra principal và xác minh password bằng KDF hiện hành. Nếu principal không tồn tại, có thể chạy dummy verifier tương đương để giảm timing enumeration. Public response cho principal không tồn tại và password sai cần tương đương.

### Bước 3: đánh giá policy

Nếu principal hợp lệ, service đọc policy của account/tenant/role. Policy xác định MFA có bắt buộc hay không, factor nào được chấp nhận, risk có yêu cầu step-up hoặc deny không. Không tin lựa chọn factor do client tự khai nếu factor chưa được đăng ký với principal.

### Bước 4: tạo pre-authentication challenge

Challenge có:

- Challenge ID ngẫu nhiên/opaque.
- Principal reference.
- Pre-auth session reference.
- Purpose là hoàn tất login MFA.
- Factor reference được phép dùng.
- Thời điểm tạo và expiry.
- Trạng thái pending/consumed/revoked.
- Nonce hoặc operation reference để chống replay/idempotency.

Pre-auth state có quyền rất hạn chế: chỉ xem/hoàn tất challenge, không đọc dữ liệu tenant, không tạo API key, không thay email và không truy cập chức năng authenticated.

### Bước 5: xác minh TOTP

Verifier lấy secret từ kho bảo vệ, tính các time-step trong cửa sổ clock skew cho phép và so sánh an toàn. Khi một mã hợp lệ, transaction phải atomically consume challenge và ghi time-step đã chấp nhận để ngăn cùng mã được dùng lại. Nếu hai request đồng thời gửi cùng mã, tối đa một request được phép hoàn tất.

### Bước 6: tạo session

Sau khi factor hợp lệ, service kiểm tra lại account status, challenge state và policy version trước điểm commit. Session ID mới được tạo ngẫu nhiên, pre-auth state không được nâng quyền bằng cách giữ nguyên session identifier nếu kiến trúc yêu cầu rotation. Cookie được đặt Secure, HttpOnly, SameSite phù hợp; response authentication dùng Cache-Control no-store.

## 8. Luồng đăng nhập bằng passkey

Passkey có thể là phương thức đăng nhập không password hoặc một phương thức xác thực mạnh được policy chấp nhận. Khi passkey đáp ứng user verification và profile assurance cần thiết, không phải ghép thêm password chỉ để gọi tên flow là MFA.

### Luồng khái niệm

1. Browser yêu cầu server bắt đầu WebAuthn authentication.
2. Server tạo challenge ngẫu nhiên, lưu với expiry, RP ID và purpose.
3. Browser gọi authenticator; người dùng xác nhận bằng PIN/sinh trắc học/gesture theo thiết bị.
4. Authenticator ký assertion bằng private key gắn với credential.
5. Server xác minh origin, RP ID hash, challenge, credential ID, chữ ký, user presence/verification và trạng thái credential.
6. Server đánh giá risk, assurance và policy.
7. Server tạo session mới và audit kết quả.

### Những lỗi phải từ chối

- Challenge sai, hết hạn hoặc đã dùng.
- Origin/RP ID không đúng.
- Credential không thuộc principal hoặc đã bị revoke.
- Signature không hợp lệ.
- User verification bắt buộc nhưng assertion không đáp ứng.
- Credential được đăng ký từ flow không đủ re-authentication.

Không tự động coi authenticator counter không tăng là compromise trong mọi trường hợp; synced passkey có semantics khác nhau. Đánh giá theo WebAuthn implementation và policy đã chọn.

## 9. Session và mức xác thực sau login

Sau khi MFA hoàn tất, session lưu context tối thiểu:

- Principal reference và tenant context đã xác minh.
- Authentication time.
- Authenticator class/factor method.
- Assurance/policy version.
- Session created-at, idle expiry và absolute expiry.
- Session/device reference và revoke state.
- Risk decision reference nếu cần.

Không lưu OTP, TOTP seed, password hoặc raw authenticator proof trong session. API kiểm tra session hợp lệ rồi vẫn áp dụng authorization theo resource/action.

### Session freshness

Sao Mai yêu cầu step-up khi:

- Người dùng export lượng dữ liệu lớn.
- Tenant admin thêm/xóa người dùng hoặc thay đổi role.
- Người dùng thay email, phone, password hoặc authenticator.
- Người dùng thêm người thụ hưởng hoặc thực hiện thao tác tài chính nhạy cảm.

Freshness window cần được định nghĩa theo action. Một MFA vừa hoàn tất không cấp quyền step-up vô hạn cho mọi thao tác.

### Cookie và CSRF

- Cookie có Secure và HttpOnly.
- SameSite được chọn theo kiến trúc cross-site/SSO.
- Cookie-authenticated mutation cần CSRF protection và kiểm tra origin phù hợp.
- Session ID được rotate sau authentication/privilege elevation.
- Logout/revoke phải được áp dụng ở session store và validator liên quan.
- Không đặt token/session secret trong URL hoặc analytics.

## 10. Recovery khi người dùng mất điện thoại

MFA chỉ an toàn nếu recovery không trở thành đường vòng yếu hơn. Sao Mai thiết kế recovery theo mức rủi ro:

### Trường hợp A: còn một authenticator tin cậy

Người dùng đăng nhập bằng passkey/security key còn lại, thực hiện step-up, gỡ authenticator bị mất và đăng ký phương thức mới. Hệ thống gửi notification tới contact đã xác minh, thu hồi session của thiết bị mất và ghi audit.

### Trường hợp B: còn recovery code

Recovery code được lưu dưới dạng verifier/hash phù hợp, chỉ hiển thị khi tạo bộ code và mỗi code dùng một lần. Khi dùng code:

1. Kiểm tra principal, purpose, expiry và trạng thái code.
2. Atomically consume code.
3. Tạo recovery-limited session hoặc challenge.
4. Yêu cầu thiết lập authenticator mới.
5. Revoke bộ code cũ và cấp bộ mới sau khi hoàn tất.
6. Gửi notification và áp dụng hold/risk check nếu hành động nhạy cảm.

### Trường hợp C: mất mọi authenticator

Yêu cầu identity proofing hoặc support-assisted recovery theo quy trình có kiểm soát. Support agent không được chỉ dựa vào thông tin dễ tìm trên mạng hoặc câu trả lời bảo mật. Tài khoản admin/operator cần dual control, approval và audit. Nếu email chính bị nghi chiếm, email đó không được dùng làm bằng chứng độc lập duy nhất.

### Recovery state

Recovery session chỉ được phép hoàn tất recovery. Nó không được đọc dữ liệu tenant hoặc tạo API credential trước khi policy cho phép. Sau recovery, revoke session/refresh family cũ và yêu cầu re-authentication.

## 11. Error handling và account enumeration

Login và recovery không được tiết lộ principal có tồn tại hay không. Ví dụ, các trường hợp password sai và email không đăng ký có cùng public response:

~~~text
Không thể hoàn tất đăng nhập với thông tin đã cung cấp.
Hãy kiểm tra thông tin hoặc sử dụng phương thức khôi phục chính thức.
~~~

Các nguyên tắc:

- Public status/body/response shape tương đương cho các trường hợp cần giữ kín.
- Dùng dummy KDF khi principal không tồn tại để giảm timing signal.
- Rate limit theo nhiều chiều; không khóa account vĩnh viễn chỉ dựa vào request chưa xác thực.
- Không trả danh sách MFA factor, email/phone đầy đủ hoặc trạng thái account.
- Internal audit vẫn phân biệt principal-not-found, password mismatch, MFA invalid và policy denial.
- Không log password, OTP, cookie, recovery code hoặc token.
- Dùng correlation ID opaque để support điều tra theo quyền.

## 12. Rate limiting và chống MFA abuse

Sao Mai áp dụng rate limit theo account reference, source/network, tenant, device/session và challenge. Các ngưỡng trong production phải được tuning theo traffic và risk; không hard-code một giá trị dùng cho mọi tenant.

### Password guessing

- Throttle theo account và nguồn.
- Phát hiện password spraying trên nhiều account.
- Kiểm tra breached password và credential stuffing signals.
- Không tạo account lockout dễ bị attacker lợi dụng để khóa hộ nạn nhân.

### OTP guessing

- Giới hạn số lần thử theo challenge/factor/account.
- Challenge hết hạn và không thể consume lặp.
- Thông báo generic khi proof sai/hết hạn.
- Theo dõi tỷ lệ failure và pattern theo source.

### Push fatigue

Nếu triển khai push:

- Number matching hoặc context confirmation.
- Giới hạn challenge và cooldown.
- Không cho approval từ một challenge không khớp login attempt.
- Alert khi deny/timeout liên tục rồi approval.

## 13. Audit và monitoring

Sao Mai ghi các event:

- LOGIN_ATTEMPT và LOGIN_DENIED.
- PASSWORD_VERIFIED.
- MFA_CHALLENGE_CREATED, MFA_CHALLENGE_FAILED và MFA_CHALLENGE_CONSUMED.
- PASSKEY_ASSERTION_ACCEPTED/DENIED.
- SESSION_CREATED, SESSION_ROTATED, SESSION_REVOKED và SESSION_EXPIRED.
- AUTHENTICATOR_ENROLLED, AUTHENTICATOR_REMOVED và RECOVERY_COMPLETED.
- STEP_UP_REQUIRED/COMPLETED/DENIED.

Event chứa event ID, timestamp, principal reference, tenant reference, factor type, result, reason category, correlation ID và policy version. Không ghi password, OTP, TOTP seed, private key, bearer token hoặc cookie.

### Detection

- Password failure tăng trên nhiều account: password spraying/credential stuffing.
- Nhiều MFA challenge bị từ chối rồi có approval: MFA fatigue suspicion.
- MFA/passkey được thêm ngay sau recovery hoặc login risk cao: account takeover suspicion.
- Refresh token cũ bị dùng lại: token family reuse detection.
- Session mới từ context bất thường theo sau thay đổi recovery: correlate thành một alert.

Alert cần có severity, confidence, evidence reference và runbook. Một event bất thường không tự động chứng minh compromise; phải xem context và false positive.

## 14. Pseudocode: hoàn tất MFA và tạo session an toàn

Ví dụ khái niệm cho TOTP. Đây không phải API hoặc thư viện production:

~~~ts
async function completeLoginMfa(preAuthRef, challengeRef, submittedCode) {
  const preAuth = await preAuthStore.get(preAuthRef);
  if (!preAuth || preAuth.state !== "MFA_PENDING") {
    return deny("AUTHENTICATION_FAILED");
  }

  const challenge = await challengeStore.get(challengeRef);
  if (!challenge ||
      challenge.principalRef !== preAuth.principalRef ||
      challenge.preAuthRef !== preAuth.ref ||
      challenge.purpose !== "LOGIN_MFA" ||
      challenge.expiresAt <= clock.now()) {
    return deny("MFA_VERIFICATION_FAILED");
  }

  const factor = await factorStore.getActiveTotp(challenge.factorRef);
  if (!factor) return deny("MFA_VERIFICATION_FAILED");

  const proof = await totpVerifier.verifyWithoutLogging(
    submittedCode,
    factor.secretRef,
    challenge.allowedTimeWindow
  );
  if (!proof.valid) return deny("MFA_VERIFICATION_FAILED");

  const committed = await transaction.atomicConsumeMfaAndCreateSession({
    challengeRef: challenge.ref,
    factorRef: factor.ref,
    acceptedTimeStep: proof.timeStep,
    preAuthRef: preAuth.ref,
    principalRef: preAuth.principalRef,
    policyVersion: preAuth.policyVersion
  });

  if (!committed) return deny("MFA_VERIFICATION_FAILED");

  return issueSecureSession(committed.sessionRef);
}
~~~

Điểm cần giữ trong implementation:

- Không tin principal/factor/purpose do client tự khai.
- Secret được lấy từ kho bảo vệ qua reference; không xuất ra log.
- Challenge và time-step được consume atomically.
- Kiểm tra lại account/policy state tại transaction commit.
- Không phát session cookie trước khi commit thành công.
- Retry được xử lý idempotently, không tạo nhiều session.
- Public error không tiết lộ account existence hoặc factor inventory.

## 15. Test plan và bằng chứng chấp nhận

| Test case | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- |
| Password sai | Không có full session | Response, session-store snapshot, audit |
| Principal không tồn tại | Public response tương đương password sai | Contract test và timing distribution |
| Password đúng, MFA chưa hoàn tất | Chỉ có pre-auth state giới hạn | Protected API từ chối |
| TOTP sai/hết hạn | Từ chối | Challenge state không đổi thành consumed thành công |
| TOTP replay | Từ chối lần hai | Atomic consume/audit |
| Hai request cùng OTP đồng thời | Tối đa một lần thành công | Concurrency test |
| Challenge thuộc user khác | Từ chối | Negative integration test |
| Passkey origin/RP ID sai | Từ chối | WebAuthn validation test |
| Passkey credential revoked | Từ chối | Credential registry + validator evidence |
| Recovery code đã dùng | Từ chối | One-time state test |
| Recovery không có proof đủ mạnh | Không cấp full session | Recovery workflow test |
| IdP/MFA provider timeout | Không fail-open | Fault-injection result |
| Session store commit lỗi | Không trả authenticated success | Transaction/compensation test |
| Session cookie | Secure, HttpOnly, SameSite đúng policy | Browser integration/config test |
| CSRF/origin sai | Mutation bị từ chối | API integration test |
| Account enumeration | Không lộ principal/factor state | Response parity và timing test |
| Refresh token bị reuse | Family policy kích hoạt | Token family event và revoke evidence |
| Step-up hết freshness | Yêu cầu xác thực lại | Policy test |
| Tenant mismatch | Không truy cập dữ liệu tenant khác | Authorization negative test |
| Audit logging | Có event nhưng không có secret | Secret marker scan |

### Release gate

Không bật MFA rộng nếu:

- Có đường tạo full session trước khi hoàn tất factor bắt buộc.
- Challenge hoặc recovery code có thể replay.
- Enrollment/recovery yếu hơn login mà không có exception được phê duyệt.
- API bỏ qua session assurance hoặc tenant authorization.
- Dependency outage khiến MFA bị bỏ qua.
- Session/token cũ không được revoke theo SLA đã cam kết.
- Log hoặc alert chứa OTP, token, cookie hay secret.

## 16. Kế hoạch triển khai theo giai đoạn

### Giai đoạn 1: chuẩn bị

- Inventory account, role, session và recovery method.
- Xác định tenant và nhóm người dùng cần policy khác nhau.
- Kiểm tra email/phone đã xác minh và chất lượng notification.
- Chuẩn hóa event, audit, rate limit và error response.
- Hoàn thiện support/recovery runbook trước khi ép MFA.

### Giai đoạn 2: pilot

- Bật MFA cho nhân viên và nhóm tenant tự nguyện.
- Hỗ trợ TOTP và passkey theo policy.
- Theo dõi enrollment completion, login failure, recovery volume và support ticket.
- Chạy test negative, concurrency, outage và revoke propagation.
- Thu thập phản hồi accessibility và thiết bị.

### Giai đoạn 3: rollout

- Bắt buộc MFA theo tenant/role/risk tier.
- Nhắc enrollment trước deadline và hướng dẫn recovery.
- Tăng enforcement cho admin trước user thường.
- Có exception register với owner, expiry và compensating control.
- Theo dõi bypass/fallback và alert khi policy bị thay đổi.

### Giai đoạn 4: tối ưu

- Tăng adoption passkey/phishing-resistant authenticator.
- Giảm fallback yếu theo kế hoạch.
- Review session lifetime và step-up freshness.
- Kiểm tra recovery exercise và revoke drill định kỳ.
- Cập nhật policy theo threat model, incident và tiêu chuẩn mới.

## 17. Sự cố giả định: attacker biết password nhưng chưa hoàn tất MFA

Một chiến dịch credential stuffing khiến nhiều account có password đúng. Attacker thử tiếp tục bằng TOTP phishing. Một số người dùng từ chối challenge, một người vô tình nhập OTP vào trang giả.

### Phát hiện

- Login event cho thấy password verified từ source bất thường.
- MFA challenge failure tăng.
- Có một challenge được consume thành công sau nhiều lần thử.
- Session mới được tạo và một API export được gọi.

### Ứng phó

1. Correlate password, MFA, session và API event theo principal/session reference.
2. Revoke session và refresh family có dấu hiệu bị chiếm.
3. Yêu cầu người dùng recovery bằng phương thức độc lập đã xác minh.
4. Kiểm tra authenticator/recovery method có bị thêm hoặc thay không.
5. Đánh giá dữ liệu đã export và thông báo theo incident policy.
6. Tăng rate limit/risk control cho campaign nhưng tránh khóa toàn tenant tùy tiện.
7. Đánh giá chuyển tài khoản rủi ro cao sang passkey/security key chống phishing.
8. Giữ audit evidence và kiểm chứng credential cũ bị từ chối.

### Bài học

MFA giảm tác động của password compromise nhưng không loại bỏ phishing, session theft hoặc recovery abuse. Khi OTP bị relay, session sau MFA có thể đã nằm trong tay attacker. Vì vậy cần phishing-resistant authenticator, session monitoring, transaction step-up và recovery an toàn.

## 18. Bài tập tự kiểm tra

Bạn là kỹ sư IAM của Sao Mai. Hãy thiết kế và đánh giá một luồng MFA cho ba nhóm: customer user, tenant admin và platform operator.

1. Xác định tài sản và threat model của từng nhóm.
2. Chọn password, TOTP, passkey/security key và fallback nào được phép.
3. Vẽ state machine từ anonymous tới authenticated session.
4. Xác định dữ liệu pre-auth challenge và điều kiện atomic consume.
5. Thiết kế recovery khi mất một hoặc toàn bộ authenticator.
6. Xác định step-up cho export, đổi recovery channel và thao tác đặc quyền.
7. Viết test chứng minh không có full session trước MFA.
8. Thiết kế alert cho password spraying, MFA fatigue và refresh token reuse.
9. Đề xuất rollout pilot và metric để đo adoption/abuse.

**Gợi ý đánh giá:** lời giải tốt phải có policy khác nhau theo risk, phân biệt TOTP với phishing-resistant MFA, giữ pre-auth session giới hạn, chống replay/concurrency, recovery không yếu hơn login và có bằng chứng kiểm thử ở API/resource server.

---

**Ghi nhớ:** MFA chỉ bảo vệ tốt khi toàn bộ flow được thiết kế đúng. Xác minh password trước, tạo pre-auth state giới hạn, consume challenge một lần, chỉ tạo full session sau khi policy và mọi factor bắt buộc thành công. TOTP tăng bảo vệ nhưng vẫn có thể bị phishing/relay; passkey/WebAuthn cung cấp origin binding tốt hơn khi triển khai đúng. Enrollment, recovery, session, step-up, revoke, audit và authorization phải giữ cùng trust model. Một màn hình yêu cầu mã OTP không chứng minh hệ thống đã có xác thực mạnh.
