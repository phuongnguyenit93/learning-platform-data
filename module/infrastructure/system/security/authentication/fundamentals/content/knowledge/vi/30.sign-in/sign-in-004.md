# Successful login

## 1. Successful login là gì?

**Successful login (đăng nhập thành công)** là kết quả của một quy trình trong đó hệ thống đã xác minh bằng chứng xác thực của người dùng, xác định đúng principal, áp dụng các kiểm tra trạng thái và chính sách cần thiết, rồi thiết lập hoặc tiếp tục một phiên làm việc có phạm vi rõ ràng.

Một màn hình hiển thị “Đăng nhập thành công” chưa đủ để chứng minh hệ thống đã hoàn tất đúng quy trình. Ở phía server, thành công phải có nghĩa là credential hoặc authentication response đã được xác minh, tài khoản được phép đăng nhập, kết quả được gắn với đúng client/session và trạng thái phiên được tạo an toàn.

Ví dụ: người dùng đăng nhập cổng doanh nghiệp bằng passkey. Server xác minh challenge, origin, RP ID, chữ ký và trạng thái credential; kiểm tra tài khoản còn hoạt động; tạo session ID mới; lưu auth context; phát cookie phiên an toàn; rồi chuyển người dùng tới trang đích đã được kiểm tra. Chỉ sau các bước đó, ứng dụng mới có thể coi lần đăng nhập là thành công.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, successful login là điểm nối giữa credential, MFA/passkey, identity, session, token và authorization. Kết quả xác thực cần được quản lý như một sự kiện bảo mật có thể truy vết, hết hạn và thu hồi.

## 2. Phân biệt xác thực thành công với truy cập được phép

Authentication và authorization trả lời hai câu hỏi khác nhau:

| Giai đoạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Người đang trình credential có chứng minh được quyền kiểm soát phương thức đã đăng ký không? | Passkey assertion hợp lệ cho tài khoản. |
| **Account/policy checks** | Tài khoản và ngữ cảnh có được phép tạo phiên không? | Tài khoản không bị khóa, tenant còn hoạt động. |
| **Session establishment** | Server đã tạo trạng thái phiên an toàn chưa? | Session ID mới, cookie Secure/HttpOnly. |
| **Authorization** | Chủ thể có được phép thực hiện hành động trên tài nguyên cụ thể không? | Có quyền xem báo cáo của tenant hiện tại. |

Người dùng có thể đăng nhập thành công nhưng không có quyền truy cập một chức năng cụ thể. Ví dụ, nhân viên đã xác thực đúng nhưng không có role hoặc scope để quản lý người dùng. Ngược lại, giao diện ẩn nút quản trị không có nghĩa API đã thực thi authorization.

**Không cấp quyền quản trị chỉ vì login thành công.** Hệ thống phải đánh giá role, scope, tenant, resource ownership và policy ở mỗi thao tác cần bảo vệ.

## 3. Các điều kiện để kết luận login thành công

Một quy trình đăng nhập thường cần kiểm tra:

1. **Bằng chứng xác thực hợp lệ:** password hash khớp, OTP hợp lệ, passkey assertion hợp lệ, certificate được tin cậy hoặc authentication response từ IdP đã được xác minh.
2. **Ràng buộc đúng flow:** challenge, nonce, state, PKCE hoặc request correlation gắn với phiên đăng nhập đang chờ.
3. **Đúng principal:** credential được liên kết với đúng tài khoản, issuer, subject và tenant.
4. **Credential còn hiệu lực:** không bị thu hồi, hết hạn, tạm khóa hoặc thay thế.
5. **Tài khoản đủ điều kiện:** không bị disable, suspended hoặc yêu cầu bước xử lý bổ sung.
6. **Policy được đáp ứng:** mức assurance, MFA, thiết bị, rủi ro và yêu cầu xác thực gần đây phù hợp.
7. **Session được tạo an toàn:** session ID mới, trạng thái phía server được lưu và cookie/token được phát theo đúng cơ chế.
8. **Kết quả được ghi nhận:** audit event không chứa secret, token hoặc dữ liệu xác thực thô.

Không phải mọi ứng dụng đều có cùng bước kiểm tra, nhưng quyết định thành công phải được thực hiện ở server dựa trên bằng chứng đã xác minh. Client không thể tự đặt cờ `authenticated=true` trong request để tạo phiên.

## 4. Luồng successful login tổng quát

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser / Client
    participant A as Authentication service
    participant P as Policy / Account service
    participant S as Session store
    U->>C: Gửi credential hoặc hoàn tất challenge
    C->>A: Authentication response
    A->>A: Xác minh credential, challenge và flow
    A->>P: Kiểm tra principal, account và policy
    P-->>A: Cho phép tạo session
    A->>S: Tạo session ID mới + auth context
    S-->>A: Session được lưu
    A-->>C: Set-Cookie hoặc token response
    C-->>U: Điều hướng tới trang đích hợp lệ
~~~

Luồng thực tế có thể khác theo password login, WebAuthn, OIDC, SAML hoặc client native. Tuy nhiên, nguyên tắc chung là chỉ phát hành session/token sau khi xác minh xong bằng chứng và các điều kiện bắt buộc.

Nếu session store không ghi được hoặc policy service không trả được quyết định cần thiết, hệ thống không nên hiển thị thành công rồi để client tiếp tục với trạng thái không nhất quán. Với hệ thống nhạy cảm, hãy fail closed và cho người dùng thử lại sau khi dịch vụ phục hồi.

## 5. Xác minh credential trước khi tạo phiên

### 5.1. Password

Với password, server tra tài khoản theo định danh đã chuẩn hóa theo policy, lấy password verifier và so sánh bằng password hashing scheme phù hợp như Argon2id, scrypt hoặc một cấu hình bcrypt được duy trì. Không lưu mật khẩu plaintext và không so sánh bằng cách tự viết thuật toán hash.

Khi password đúng, server vẫn phải kiểm tra:

- Tài khoản có đang hoạt động không.
- Có yêu cầu MFA hoặc step-up không.
- Password có bị yêu cầu đổi do chính sách hoặc sự cố không.
- Có dấu hiệu credential stuffing, brute force hoặc đăng nhập bất thường không.
- Có phải luồng đăng nhập được bắt đầu từ browser/session hợp lệ không.

Password đúng chỉ xác minh một yếu tố knowledge. Nếu policy yêu cầu MFA, chưa được kết luận login thành công cho tới khi factor bổ sung cũng được xác minh.

### 5.2. OTP/MFA

Với TOTP, server kiểm tra mã dựa trên secret đã đăng ký và cửa sổ thời gian cho phép. Với push approval hoặc security key, server xác minh phản hồi theo giao thức tương ứng.

Mã OTP cần được kiểm soát replay: sau khi một mã được chấp nhận, không nên chấp nhận lại cùng mã trong cùng cửa sổ theo policy. Challenge push cần gắn với đúng lần đăng nhập, tránh chấp thuận nhầm prompt hoặc bị fatigue attack.

MFA thành công chỉ khi tất cả yếu tố bắt buộc đã được xác minh. Ghi nhận chính xác phương thức đã dùng và mức assurance; không gộp mọi loại OTP, push, passkey và security key thành cùng một mức bảo đảm.

### 5.3. Passkey/WebAuthn

Với passkey, server cần xác minh challenge, origin, RP ID hash, credential ID, chữ ký assertion và các cờ user presence/user verification theo policy. Credential phải thuộc đúng tài khoản và còn trạng thái Active.

Không coi việc browser trả về một object WebAuthn là bằng chứng thành công. Server phải xác minh dữ liệu đã ký bằng public key đã đăng ký và bảo đảm challenge chưa dùng, chưa hết hạn, gắn với đúng flow.

### 5.4. Federation

Với OIDC hoặc SAML, ứng dụng không tự tin vào việc browser được chuyển hướng về callback. RP/SP phải xác minh chữ ký, issuer, audience, thời hạn, nonce/state hoặc request correlation và các điều kiện của giao thức trước khi tạo local session.

ID Token OIDC là bằng chứng authentication dành cho client theo OIDC; access token dành cho resource server. Không dùng ID Token thay access token để gọi API.

## 6. Xác định principal và liên kết danh tính

Sau khi credential được xác minh, hệ thống phải ánh xạ kết quả sang một principal nội bộ ổn định. Trong federation, định danh an toàn thường là cặp issuer và subject, không chỉ là email hoặc display name.

Các điểm cần kiểm tra:

- Credential thuộc đúng account record.
- Issuer là nguồn danh tính đã được cấu hình tin cậy.
- Subject được liên kết với đúng tài khoản nội bộ và tenant.
- Không tự động ghép hai tài khoản chỉ vì email giống nhau nếu chưa có quy trình account linking an toàn.
- Tài khoản không bị xóa, khóa hoặc đánh dấu cần xử lý.
- Thông tin profile được cập nhật theo chính sách nguồn dữ liệu, không dùng profile claim làm quyền truy cập.

Ví dụ: cùng một địa chỉ email có thể xuất hiện ở hai IdP hoặc hai tenant. Nếu hệ thống chỉ dùng email để xác định principal, người dùng có thể bị liên kết nhầm tài khoản. Cặp issuer/subject và quy tắc linking rõ ràng giúp tránh nhầm danh tính.

## 7. Tạo session mới sau đăng nhập

Sau khi xác minh thành công, ứng dụng web thường tạo session mới ở server và phát một session cookie cho browser.

Các yêu cầu quan trọng:

- Tạo session ID ngẫu nhiên bằng CSPRNG, đủ entropy và không suy ra từ user ID hoặc timestamp.
- **Xoay session ID sau authentication** để giảm session fixation.
- Vô hiệu hóa session ID trước đăng nhập nếu flow yêu cầu thay thế.
- Lưu session ở server-side store hoặc dùng cơ chế token được thiết kế phù hợp.
- Gắn principal, tenant, authentication time, assurance và factor đã dùng vào auth context.
- Đặt idle timeout và absolute timeout theo mức rủi ro.
- Có cơ chế revoke session khi logout, đổi credential hoặc phát hiện chiếm tài khoản.

Ví dụ cookie phiên:

~~~http
Set-Cookie: __Host-SessionID=opaque-random-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`Secure` yêu cầu browser chỉ gửi cookie qua kênh an toàn; `HttpOnly` ngăn JavaScript thông thường đọc cookie; `SameSite` hạn chế một số request cross-site. Cookie cần host-only scope phù hợp; prefix `__Host-` yêu cầu Secure, Path=/ và không có Domain trên browser hỗ trợ prefix.

Không đưa session ID vào URL, query string, log hoặc analytics. Cookie chỉ là phương tiện mang session identifier; server vẫn phải kiểm tra trạng thái session ở mỗi request được bảo vệ.

## 8. Auth context: ghi nhận cách người dùng đã đăng nhập

Một lần đăng nhập thành công không chỉ cần biết principal là ai. Hệ thống còn cần biết lần xác thực diễn ra khi nào và bằng phương thức nào để áp dụng policy về freshness và assurance.

Ví dụ session context:

~~~json
{
  "principalId": "user-42",
  "tenantId": "tenant-a",
  "authTime": "2026-11-22T10:00:00Z",
  "amr": ["webauthn"],
  "assurance": "phishing-resistant",
  "credentialRef": "credential-9",
  "sessionCreatedAt": "2026-11-22T10:00:02Z",
  "sessionVersion": 4
}
~~~

Đây là schema ứng dụng minh họa, không phải định dạng chuẩn. Chỉ lưu các thuộc tính có nguồn đáng tin và cần cho policy:

- `authTime`: thời điểm xác thực thực sự đã được xác minh.
- `amr`: phương thức authentication đã dùng theo profile/issuer.
- `acr` hoặc assurance: mức/ngữ cảnh xác thực do issuer hoặc hệ thống xác nhận.
- `credentialRef`: tham chiếu credential đã sử dụng nếu cần điều tra/thu hồi.
- `sessionVersion`: hỗ trợ vô hiệu hóa session cũ.

Không cập nhật `authTime` khi chỉ refresh token, tải trang, gia hạn cookie hoặc có hoạt động người dùng thông thường. Những sự kiện này không chứng minh người dùng vừa xác thực lại.

## 9. Trả kết quả thành công cho client

Phản hồi cần phù hợp với loại client:

### 9.1. Browser session

Với ứng dụng web dùng session cookie, server phát `Set-Cookie` và chuyển hướng tới trang đích hợp lệ. Không gửi session ID trong response body hoặc URL.

~~~http
HTTP/1.1 303 See Other
Location: /account
Set-Cookie: __Host-SessionID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Pragma: no-cache
~~~

`Location` phải được xác định từ route nội bộ hoặc redirect URI đã allowlist. Không phản chiếu tham số `returnUrl` tùy ý từ request vì có thể tạo open redirect.

### 9.2. OAuth/OIDC client

Trong Authorization Code Flow, đăng nhập tại OP thường trả authorization code về redirect URI đã đăng ký. Client đổi code lấy token qua token endpoint, xác minh ID Token theo OIDC và thiết lập session cục bộ nếu là confidential web client.

Không trả access token hoặc refresh token vào URL fragment/query của trang web thông thường. Với public client, dùng Authorization Code + PKCE; bảo vệ token theo nền tảng và không nhúng client secret vào ứng dụng native/browser.

### 9.3. API hoặc native client

API có thể trả token theo giao thức đã thỏa thuận. Native client cần lưu token trong secure storage của nền tảng, hạn chế thời gian sống và bảo vệ refresh token. Không ghi token vào console, crash report, clipboard hoặc log HTTP.

## 10. Điều hướng sau đăng nhập

Sau khi thành công, ứng dụng thường chuyển người dùng tới trang họ yêu cầu trước đó hoặc trang mặc định. Redirect phải được kiểm soát:

- Chỉ chấp nhận đường dẫn nội bộ hoặc URI đã đăng ký.
- Chuẩn hóa và kiểm tra host, scheme, path theo allowlist.
- Không cho phép scheme không mong muốn hoặc host ngoài danh sách.
- Ràng buộc return target với login transaction/state để tránh thay đổi giữa các bước.
- Không dùng thông tin redirect để quyết định principal hoặc quyền.

Nếu người dùng mở một trang cần đăng nhập, ứng dụng có thể lưu đường dẫn đích trong session login transaction. Sau khi authentication thành công, server kiểm tra lại route và authorization trước khi điều hướng. Người dùng không được tự động cấp quyền chỉ vì họ đã yêu cầu một URL.

## 11. Phản hồi lỗi và tránh account enumeration

Thông báo đăng nhập nên cung cấp đủ thông tin để người dùng khắc phục nhưng không tiết lộ trạng thái tài khoản cho attacker.

Ví dụ, khi username không tồn tại hoặc password sai, có thể dùng phản hồi chung như “Thông tin đăng nhập không hợp lệ”. Tránh thông báo phân biệt “email không tồn tại”, “mật khẩu sai”, “tài khoản có MFA” nếu những khác biệt đó cho phép enumeration.

Tuy nhiên, sau khi đã xác minh danh tính trong một kênh đáng tin, ứng dụng có thể hiển thị hướng dẫn cụ thể hơn, ví dụ tài khoản cần đổi password hoặc liên hệ quản trị viên. Cần phân biệt phản hồi trước và sau authentication.

Các lỗi như credential sai, account disabled, factor revoked, challenge hết hạn hoặc policy từ chối cần được ghi nhận nội bộ với mã lý do phù hợp, nhưng không đưa chi tiết nhạy cảm ra client.

## 12. Kiểm soát sau khi xác thực thành công

Login thành công không có nghĩa bỏ qua giám sát. Ngay sau khi tạo session, hệ thống có thể:

- Gửi thông báo đăng nhập mới nếu policy yêu cầu.
- Ghi nhận thiết bị và vị trí ở mức tín hiệu rủi ro, không coi IP là bằng chứng danh tính.
- Kiểm tra đăng nhập bất thường hoặc hành vi credential stuffing.
- Yêu cầu đổi password nếu có bằng chứng password bị lộ.
- Áp dụng hạn chế tạm thời hoặc step-up trước hành động nhạy cảm.
- Cập nhật `lastLoginAt` hoặc lịch sử đăng nhập theo chính sách.
- Cấp session assurance phù hợp với factor thực tế.

Không nên tự động tin thiết bị chỉ vì nó vừa đăng nhập thành công. Device trust cần quy trình đăng ký và đánh giá riêng.

## 13. Audit event cho successful login

Audit event cần giúp trả lời: ai đăng nhập, lúc nào, qua phương thức nào, vào tenant/client nào và quyết định dựa trên policy nào.

Ví dụ event khái niệm:

~~~json
{
  "event": "authentication.succeeded",
  "eventId": "evt-7f2a",
  "principalId": "user-42",
  "tenantId": "tenant-a",
  "clientId": "employee-portal",
  "authMethod": "webauthn",
  "assurance": "phishing-resistant",
  "credentialRef": "credential-9",
  "occurredAt": "2026-11-22T10:00:00Z",
  "sessionRef": "session-record-12",
  "policyId": "employee-login-v4"
}
~~~

Không ghi password, OTP, private key, assertion thô, session cookie, access token hoặc refresh token. IP address, user agent và thông tin thiết bị cũng cần được giới hạn theo mục đích, quyền truy cập và retention policy.

Tách audit event khỏi application debug log. Audit cần kiểm soát tính toàn vẹn, quyền truy cập, thời hạn lưu giữ và khả năng truy vấn khi điều tra sự cố.

## 14. Mối đe dọa sau login và biện pháp bảo vệ

| Mối đe dọa | Tác động | Kiểm soát |
| --- | --- | --- |
| Session fixation | Attacker tiếp tục dùng session ID được biết trước đăng nhập. | Xoay session ID sau authentication và vô hiệu hóa ID cũ. |
| Session theft | Attacker dùng cookie/token bị đánh cắp. | TLS, Secure/HttpOnly, bảo vệ thiết bị, session expiry/revoke và phát hiện bất thường. |
| Login CSRF | Nạn nhân bị đăng nhập vào tài khoản của attacker. | State/CSRF protection, ràng buộc login transaction và kiểm tra flow. |
| Open redirect | Người dùng bị chuyển tới website giả sau login. | Redirect allowlist và kiểm tra scheme/host/path. |
| Account enumeration | Attacker xác định tài khoản tồn tại. | Thông báo chung, rate limit và phản hồi có thời gian hợp lý. |
| Token leakage | Token bị lộ qua URL, log hoặc storage yếu. | Không đưa token vào URL/log; secure storage và TTL phù hợp. |
| Stale authentication context | Session cũ được coi là mới hoặc mạnh hơn thực tế. | Lưu auth time/assurance riêng, re-authentication và step-up. |
| Account linking confusion | Danh tính từ issuer khác bị gắn nhầm tài khoản. | Dùng issuer + subject và quy trình linking có xác minh. |
| Race condition | Hai flow cùng tạo hoặc thay thế session không nhất quán. | Transaction, versioning, idempotency và session state rõ. |

## 15. Login transaction và chống nhầm luồng

Một login transaction nên có định danh ngẫu nhiên, thời hạn ngắn và trạng thái rõ. Nó liên kết browser/session bắt đầu đăng nhập với callback hoặc credential response cuối cùng.

Các trường khái niệm:

- Transaction ID.
- Browser/session binding.
- Principal hoặc account hint nếu đã có.
- Client ID, redirect target và tenant.
- State, nonce, PKCE verifier/challenge khi giao thức cần.
- Challenge WebAuthn hoặc MFA flow ID.
- Thời điểm tạo, hết hạn và trạng thái đã dùng.

Mỗi callback chỉ được hoàn tất transaction tương ứng một lần. Nếu transaction đã hết hạn hoặc đã tiêu thụ, từ chối và yêu cầu bắt đầu flow mới. Không cho phép response từ flow A tạo session cho browser/session B.

Với OIDC, `state` bảo vệ tương quan authorization response; `nonce` ràng buộc ID Token với authentication request; PKCE ràng buộc authorization code với client giữ code verifier. Chúng giải quyết các mục tiêu khác nhau và không nên bỏ một giá trị chỉ vì đã dùng giá trị khác.

## 16. Ví dụ pseudocode tạo session

Đoạn mã sau minh họa các bước phía server sau khi credential đã được xác minh:

~~~ts
async function completeLogin(input) {
  const transaction = await loginTransactions.consumeOnce(input.transactionId);
  if (!transaction || transaction.expiresAt < new Date()) {
    throw new AuthenticationError();
  }

  const verified = await verifyAuthenticationEvidence(input.evidence, transaction);
  if (!verified.ok) throw new AuthenticationError();

  const principal = await resolvePrincipal(verified.issuer, verified.subject);
  if (!principal || principal.status !== "active") {
    throw new AuthenticationError();
  }

  const decision = await policyEngine.evaluateLogin({
    principal,
    tenantId: transaction.tenantId,
    clientId: transaction.clientId,
    assurance: verified.assurance,
    authMethod: verified.authMethod
  });
  if (!decision.allow) throw new AuthenticationError();

  const sessionId = generateCryptographicallyRandomSessionId();
  await sessionStore.create({
    sessionId,
    principalId: principal.id,
    tenantId: transaction.tenantId,
    authTime: verified.authTime,
    authMethod: verified.authMethod,
    assurance: verified.assurance,
    credentialRef: verified.credentialRef
  });

  await audit.write({
    event: "authentication.succeeded",
    principalId: principal.id,
    clientId: transaction.clientId,
    authMethod: verified.authMethod
  });

  return {
    sessionId,
    redirectTo: validateAllowedReturnTarget(transaction.returnTarget)
  };
}
~~~

Đây là pseudocode, không phải implementation dùng trực tiếp. `consumeOnce` cần nguyên tử; `verifyAuthenticationEvidence` phải dùng verifier phù hợp cho password, WebAuthn, MFA, OIDC hoặc SAML; session ID phải được sinh bằng CSPRNG; cookie phải được phát qua HTTPS với thuộc tính phù hợp. Không ghi session ID hoặc evidence thô vào audit.

## 17. Ví dụ: đăng nhập nhân viên bằng passkey

Một nhân viên truy cập cổng nội bộ:

1. Browser mở trang đăng nhập và server tạo login transaction cùng challenge WebAuthn ngẫu nhiên, có thời hạn.
2. Browser gọi authenticator bằng `navigator.credentials.get()`.
3. Authenticator xác minh người dùng cục bộ theo policy và ký assertion.
4. Browser gửi assertion cùng transaction ID về server.
5. Server kiểm tra transaction còn hiệu lực, challenge chưa dùng, origin/RP ID đúng, credential thuộc nhân viên, chữ ký hợp lệ và cờ UP/UV đáp ứng policy.
6. Server kiểm tra tài khoản còn hoạt động, đúng tenant và policy login cho phép.
7. Server tạo session ID mới, lưu principal và auth context, phát cookie `Secure; HttpOnly; SameSite=Lax`.
8. Server ghi audit event và chuyển người dùng tới trang nội bộ đã allowlist.

Nếu credential vừa bị thu hồi hoặc tài khoản đã bị disable, server từ chối tạo session dù chữ ký assertion vẫn hợp lệ về mặt mật mã. Trạng thái credential và tài khoản là một phần của quyết định login.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tin client báo login thành công | Attacker có thể tự tạo trạng thái authenticated. | Server tự xác minh bằng chứng và quyết định. |
| Tạo session trước khi hoàn tất MFA | Session một yếu tố có thể bị dùng để truy cập tài nguyên. | Chỉ cấp session đầy đủ sau mọi factor bắt buộc; nếu cần, dùng pre-auth session giới hạn. |
| Không xoay session ID sau login | Session fixation. | Tạo ID mới và vô hiệu hóa ID cũ. |
| Dùng email làm principal duy nhất trong federation | Liên kết nhầm issuer/tenant hoặc email thay đổi. | Dùng issuer + subject ổn định và account linking có xác minh. |
| Coi login thành công là có quyền mọi chức năng | Authorization bị bỏ qua. | Kiểm tra scope, role, tenant và resource ở server. |
| Coi refresh token là lần xác thực mới | Auth time và assurance bị nâng sai. | Giữ nguyên auth context trừ khi có re-authentication thực sự. |
| Redirect tới URL tùy ý | Open redirect/phishing. | Allowlist và ràng buộc return target với login transaction. |
| Log credential hoặc token | Tạo đường lộ bí mật mới. | Redact và chỉ log metadata cần thiết. |
| Không kiểm tra credential/account status | Credential đã revoke hoặc tài khoản bị khóa vẫn đăng nhập được. | Kiểm tra registry và account state trước khi tạo session. |
| Dùng một thông báo lỗi cho mọi giai đoạn mà không audit | Khó điều tra tấn công và lỗi vận hành. | Phản hồi chung cho client, mã lý do chi tiết trong audit có kiểm soát. |
| Không xử lý callback lặp | Một response có thể tạo nhiều session hoặc side effect. | Login transaction one-time, idempotency và state machine rõ. |
| Coi cookie tồn tại là session còn hợp lệ | Session đã revoke vẫn được chấp nhận. | Kiểm tra session store/version/status ở server. |

## 19. Checklist xác nhận successful login

Trước khi đưa luồng đăng nhập vào production, hãy kiểm tra:

1. Credential hoặc authentication response có được xác minh ở server bằng verifier đúng giao thức không?
2. Challenge, state, nonce, PKCE và request correlation có được ràng buộc với đúng login transaction không?
3. Principal có được ánh xạ bằng định danh ổn định, đúng issuer và tenant không?
4. Credential có còn Active và tài khoản có được phép đăng nhập không?
5. MFA/step-up có hoàn tất đầy đủ theo policy trước khi cấp session không?
6. Freshness và assurance có được ghi nhận từ bằng chứng đã xác minh không?
7. Session ID có được tạo mới bằng CSPRNG và xoay sau authentication không?
8. Cookie có Secure, HttpOnly, SameSite và phạm vi host/path phù hợp không?
9. Token có đúng loại, audience, thời hạn và nơi lưu trữ an toàn không?
10. Redirect sau login có được allowlist và gắn với transaction không?
11. Authorization có tiếp tục được kiểm tra ở từng API/resource không?
12. Login transaction có one-time, timeout, chống replay và xử lý callback lặp không?
13. Audit event có đủ thông tin điều tra mà không ghi secret/token/evidence thô không?
14. Có thông báo login mới, giám sát bất thường, rate limit và quy trình revoke session không?
15. Có kiểm thử password sai, MFA thiếu, credential revoked, account disabled, issuer sai, callback replay, session fixation và open redirect không?

**Kết luận:** Successful login chỉ xảy ra khi server xác minh được bằng chứng, ánh xạ đúng principal, kiểm tra credential/tài khoản/policy và tạo session hoặc token an toàn. Authentication thành công không tự cấp mọi quyền; authorization vẫn phải được thực thi trên từng tài nguyên. Session cần ID mới, auth context đáng tin, thời hạn và khả năng thu hồi. Kết quả login nên được audit mà không lưu secret, đồng thời ràng buộc callback và redirect với đúng transaction để chống replay, session fixation và nhầm luồng.
