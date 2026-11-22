# Lựa chọn tính năng xác thực nâng cao theo phiên bản Spring Security và những phần ứng dụng phải tự xây dựng

> **Phạm vi:** Spring Security trên **Servlet stack**. Đây là hướng dẫn chọn năng lực xác thực nâng cao, đọc đúng phạm vi hỗ trợ của **phiên bản framework thực tế**, và phân định trách nhiệm giữa Spring Security, Identity Provider (IdP), ứng dụng cùng đội vận hành. Ví dụ chính dùng Java 17, Spring Boot 3.3.x và Spring Security 6.x; những tính năng xuất hiện ở bản 6.4+ không được giả định có trong mọi phiên bản 6.x.

## 1. Bài toán: “Spring Security hỗ trợ” khác “sản phẩm đã hoàn thiện”

Một yêu cầu nghiệp vụ thường được diễn đạt bằng những câu như:

- “Cho đăng nhập bằng passkey, nhưng vẫn cần cách khôi phục nếu mất thiết bị.”
- “Tài khoản thường dùng mật khẩu; khi chuyển tiền phải xác thực thêm yếu tố.”
- “Gửi link đăng nhập một lần qua email, hết hạn nhanh và chỉ dùng được một lần.”
- “Nhân viên đăng nhập qua SSO để dùng MFA của công ty.”
- “Khi nâng Spring Security, tính năng MFA, session và giao diện có tự hoạt động không?”

Câu trả lời phải tách **ít nhất bốn tầng trách nhiệm**:

1. **Giao thức/cơ chế:** code framework tạo filter, nhận request, kiểm tra credential/token, duy trì `Authentication`, tích hợp `SecurityFilterChain`.
2. **Policy:** khi nào cần một hay nhiều yếu tố, tài nguyên nào đòi step-up, quyền nào gắn với danh tính và mức tin cậy nào; không phải chỉ “đăng nhập rồi cho phép mọi thao tác”.
3. **Trải nghiệm/vòng đời:** UI, enrolment, reset, recovery, đổi thiết bị, rate limit, thông báo và hỗ trợ người dùng.
4. **Vận hành/tin cậy:** secret storage, credential repository, email/SMS gateway, HSM/PKI, IdP, audit, monitoring, phiên bản dependency và kiểm thử bảo mật.

**Có filter hoặc DSL cho một chức năng không đồng nghĩa framework làm xong cả bốn tầng.** Ngược lại, khi công ty đã dùng IdP hỗ trợ MFA và passkey, ứng dụng thường không cần tự triển khai toàn bộ protocol xác thực; Spring Security có thể đóng vai trò client OIDC/SAML hoặc resource server để kiểm tra token đúng mục đích.

## 2. Trục phiên bản: đọc mã đang chạy trước khi chọn API

Spring Boot quản lý một bộ phiên bản Spring Security phụ thuộc theo BOM. Do đó “đang dùng Boot 3” không tự chứng minh có một API xuất hiện ở bản Spring Security mới hơn. Đặc biệt hãy phân biệt **Spring Security 6.0/6.1/6.2/6.3** với **6.4+** và các nhánh phát triển sau này.

| Nhóm phiên bản | Nền tảng/cách cấu hình | Điểm cần kiểm tra trước khi dùng tính năng nâng cao |
|---|---|---|
| Spring Security 5.x, thường đi với Boot 2.x | Nhiều code còn dùng `javax.servlet` hoặc cấu hình cũ | Khi nâng cấp phải xem migration guide; không copy class/namespace sang 6.x mà không sửa. `WebSecurityConfigurerAdapter` không còn là cách cấu hình cho 6.x |
| Spring Security 6.0–6.3, thường đi với Boot 3.x | Java 17+, `jakarta.servlet`, khai báo `SecurityFilterChain` qua bean và lambda DSL | Form login, HTTP Basic, OAuth2 client/resource server, SAML2, LDAP/X.509 và các khối xác thực quen thuộc là nền tảng; đừng mặc định có WebAuthn/one-time token login DSL của bản 6.4 |
| Spring Security 6.4+ | Vẫn thuộc thế hệ 6.x nhưng có bổ sung tính năng | Có hỗ trợ mới cho **WebAuthn/passkey** và **one-time token login**; kiểm tra chính xác minor/patch, dependencies, cấu hình repository và ví dụ tương ứng. Bộ khung chưa đồng nghĩa ứng dụng có MFA hoàn chỉnh |
| Các phiên bản lớn sau 6.x (ví dụ 7.x khi dự án lựa chọn) | Có thể đổi API, hành vi mặc định và phạm vi mô-đun | Chỉ dùng tính năng MFA/DSL/version-specific sau khi xác minh tài liệu, migration guide và dependency tree đúng bản đang triển khai; không suy diễn rằng API của 6.x giữ nguyên hoặc mọi factor policy đã tự có |

Bảng này **không thay thế release notes**. Tính năng, class, DSL và mặc định có thể khác giữa các bản nhỏ, bản patch hoặc gói dependency. Trong bài, những cấu hình cụ thể thuộc baseline 6.x phổ biến được tách khỏi khả năng 6.4+ để tránh dạy sai API.

### 2.1. Xác định phiên bản thực sự

Với dự án Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.security
```

Kiểm tra **resolved version**, không chỉ số phiên bản được ghi trong một ví dụ trên mạng. Ghi lại Boot version, Java version và các artifact bổ sung như `spring-security-oauth2-client`, `spring-security-oauth2-resource-server`, `spring-security-saml2-service-provider`, `spring-security-ldap`. Các module tùy chọn không tự tồn tại chỉ nhờ `spring-boot-starter-security`.

Khi đánh giá tính năng mới, đọc tài liệu **đúng version** cho mô-đun Servlet, xem migration guide, release notes, mẫu test và dependency requirement. Nếu hệ thống đang ở bản chưa có tính năng, lựa chọn là **nâng cấp có kiểm thử**, **dùng IdP đã có năng lực đó**, hoặc **tự xây có đánh giá rủi ro** — không gọi DSL chưa tồn tại.

## 3. Ma trận: Spring Security có sẵn gì, ứng dụng còn phải làm gì?

| Nhu cầu | Khối Spring Security / nền tảng có thể dùng | Phần ứng dụng/đơn vị khác vẫn chịu trách nhiệm |
|---|---|---|
| Username/password | `formLogin`, `AuthenticationManager`, `AuthenticationProvider`, `PasswordEncoder`, session và CSRF | Đăng ký user, mật khẩu an toàn, xác minh email, reset password, chống brute-force, lockout/chống enumeration, UX, audit |
| SSO doanh nghiệp | `oauth2Login` hoặc `saml2Login` và các module tương ứng | Đăng ký client/RP, IdP, MFA policy, account linking, role mapping, recovery, session/logout |
| API bearer token | `oauth2ResourceServer`, JWT/opaque token validation | Authorization server/IdP, audience/scope contract, entitlement checks, token issuance/revocation strategy |
| Xác thực certificate | `x509`, cơ chế pre-auth cùng Servlet/TLS infrastructure | PKI, CA, client cert lifecycle/revocation, TLS termination, cert-to-account mapping |
| LDAP | `spring-security-ldap`, LDAP authentication/provider | Directory schema, LDAPS/trust store, group-to-authority mapping, timeout/availability, password policy |
| Passkey/WebAuthn | Hỗ trợ tích hợp WebAuthn ở các bản phù hợp (ví dụ 6.4+) | Credential store, registration UX, quản lý thiết bị, recovery, relying party/origin đúng, chống chiếm tài khoản |
| One-time token login | Năng lực one-time token login ở các bản phù hợp (ví dụ 6.4+) | Sinh/gửi link ngoài ứng dụng, email provider, người nhận, chống lạm dụng, lưu trữ/TTL, delivery UX và kiểm thử |
| TOTP authenticator app | Có thể tích hợp provider/filter/DSL tùy phiên bản | Enrollment QR, secret TOTP, storage bảo mật, giới hạn retry, time skew, replay prevention, recovery codes, policy MFA |
| SMS/email code | Dùng thành phần chung hoặc logic riêng theo thiết kế | Gửi OTP, anti-abuse, rate limit, risk engine, TTL, chống replay, nhận diện người dùng, fail-safe; SMS dễ bị SIM swap |
| MFA và step-up | Các authentication/authorization primitives; tính năng factor-based có thể xuất hiện ở phiên bản mới hơn | Chọn yếu tố, điều kiện bắt buộc, trust level, lúc nào re-auth, session factor state, giao dịch nào nhạy cảm, recovery |
| Session protection | Session management, concurrent session controls, CSRF, logout, security context | Cookie policy thực tế, distributed session, device inventory, revoke, HA và sự cố |
| Remember-me | Cơ chế remember-me có hỗ trợ | Chọn phù hợp threat model, token store, rotation, revoke, không coi remember-me là yếu tố MFA |
| Audit và hành vi bất thường | Events/logging/extension points | Business audit, chống credential stuffing, phát hiện rủi ro, alert, bảo vệ PII và vận hành incident response |

Nhìn ma trận theo ba câu hỏi: **Có cơ chế xác minh credential không? Có chính sách kiểm soát quyền và bước xác thực bổ sung không? Có đầy đủ vòng đời thực tế không?** Nếu một câu trả lời là “chưa”, việc “bật hỗ trợ” vẫn là chưa hoàn thành sản phẩm.

## 4. MFA: yếu tố, chính sách và step-up

### 4.1. Thế nào là nhiều yếu tố?

MFA yêu cầu bằng chứng từ **ít nhất hai nhóm yếu tố độc lập** theo mô hình bảo mật thích hợp:

- **Something you know:** mật khẩu hoặc PIN.
- **Something you have:** authenticator, thiết bị khóa bảo mật, private key được kiểm soát.
- **Something you are:** đặc trưng sinh trắc học nếu hệ thống xác thực đúng theo mô hình hỗ trợ.

Hai mật khẩu khác nhau hoặc mật khẩu cộng câu hỏi bí mật **không tự tạo MFA**. Email OTP có thể là bước xác minh bổ sung nhưng độ độc lập và mức bảo đảm tùy cách bảo vệ hộp thư; không được mặc định tương đương khóa bảo mật chống phishing. TOTP cũng có thể bị phishing theo thời gian thực, khác với WebAuthn được ràng buộc origin.

**Passkey** (WebAuthn/FIDO2) dùng mật mã khóa công khai và ràng buộc với relying party/origin, có thể là phương thức đăng nhập mạnh với xác minh người dùng trên authenticator. Việc nó được tính là một hay nhiều yếu tố theo chính sách assurance phụ thuộc loại authenticator và điều kiện user verification, **không phải cứ đăng nhập bằng passkey là mọi chính sách MFA đều tự thỏa**.

### 4.2. Step-up là chính sách, không chỉ là trang đăng nhập thứ hai

Ví dụ người dùng đã đăng nhập để đọc báo cáo nhưng thao tác chuyển tiền đòi **xác thực lại bằng yếu tố mạnh trong khoảng thời gian gần đây**:

```text
GET /dashboard
   |
   +--> Session đã xác thực --> cho xem dashboard
   |
POST /payments/confirm
   |
   +--> Có quyền thực hiện giao dịch?
   |      +-- Không --> 403
   |
   +--> Mức xác thực / factor còn hiệu lực theo policy?
          +-- Không --> chuyển sang luồng step-up
          |             (IdP hoặc cơ chế factor đã kiểm chứng)
          +-- Có --> tiếp tục kiểm tra CSRF, business validation,
                        transaction binding khi phù hợp, rồi xử lý
```

Spring Security có các primitive như `Authentication`, `GrantedAuthority`, authorization rules, `AuthenticationManager` và provider/filter chain. Nhưng ứng dụng **phải định nghĩa** chính sách: đối tượng nào cần step-up, mức tin cậy nào, có yêu cầu user-present không, thời gian gần nhất xác minh, điều kiện rủi ro và cách hạn chế retry/rollback.

Nếu dùng IdP hỗ trợ mức xác thực, ứng dụng có thể yêu cầu thêm assurance qua giao thức (chẳng hạn OIDC `acr_values`/`max_age` theo khả năng IdP), rồi **kiểm tra bằng chứng đã được IdP ký và hợp lệ** theo hợp đồng. `amr`/`acr` không luôn có, tên/giá trị không đồng nhất giữa IdP. **Không tin header tự khai kiểu `X-MFA-Passed: true` hoặc một claim không được xác minh.**

Không chỉ đặt cờ Boolean “MFA passed” trong JavaScript/localStorage. Trạng thái factor phải được ràng buộc với principal, phiên đăng nhập, thời điểm, method và policy; cập nhật/thu hồi an toàn khi logout, đổi mật khẩu, rủi ro phiên hoặc account recovery.

### 4.3. Tính năng built-in không đồng nghĩa MFA end-to-end

Ở các bản có **one-time token login**, cơ chế tạo/sử dụng token một lần không tự chuyển một luồng password login thành “hai yếu tố độc lập”. Nếu một link email có thể dùng **thay** mật khẩu để đăng nhập, đó là **passwordless/magic link**, không phải tự động là bước thứ hai. Nếu một factor đã xác thực vẫn cần thêm factor, ứng dụng phải xây policy và buộc người dùng đi hết luồng đó.

Ở các bản có **WebAuthn**, framework có thể cung cấp endpoint/DSL và xử lý nghi thức ở một mức độ; nhưng đăng ký khóa, lưu credential, xử lý đổi thiết bị, mất thiết bị, recovery, nguy cơ account takeover và UX vẫn phải được phân tích trong phạm vi ứng dụng/IdP thực tế.

## 5. One-time token login, OTP và magic link: ba điều không nên trộn

Thuật ngữ “OTP” đôi khi bị dùng cho nhiều cơ chế:

| Cơ chế | Cách người dùng sử dụng | Điểm khác biệt |
|---|---|---|
| One-time token login / magic link | Nhận link chứa token, mở một lần để đăng nhập | Token là một **bằng chứng truy cập/đăng nhập**; phải được tạo, lưu, chuyển giao và consume an toàn |
| TOTP theo RFC 6238 | Nhập mã thay đổi theo thời gian từ authenticator app | Dựa trên shared secret và đồng hồ; cần chống replay, giới hạn thử, quản lý secret |
| Email/SMS code | Nhập mã server gửi theo kênh ngoài | Phụ thuộc an toàn email/điện thoại và giới hạn chống lạm dụng |

Bản Spring Security mới hơn có thể cung cấp flow cho loại đầu tiên, nhưng **đừng suy ra** có provider TOTP chuẩn, recovery codes, gửi email hoặc MFA policy tự động trong tất cả phiên bản. Chọn giải pháp theo threat model; nếu tổ chức đã có IdP hỗ trợ những flow trên, ứng dụng thường nên nhận kết quả từ IdP thay vì sở hữu cả hệ thống OTP.

### 5.1. Yêu cầu tối thiểu khi tự triển khai mã/link một lần

Nếu bài toán buộc ứng dụng tự xử lý token một lần:

1. Sinh token bằng nguồn ngẫu nhiên mật mã (`SecureRandom`), có đủ entropy; **không dùng timestamp, username hoặc số tăng dần** để dự đoán token.
2. Chỉ lưu **hash/biểu diễn kiểm chứng an toàn** thay vì token thô nếu mô hình hỗ trợ; thiết kế lookup phù hợp và tránh log token.
3. Có **thời hạn ngắn**, một lần dùng, và thao tác consume **atomic** để chống hai request đồng thời sử dụng một token.
4. Ràng buộc token với user, mục đích (login/reset/step-up) và điều kiện dùng; token reset password không tự được dùng làm token xác thực MFA.
5. Giới hạn gửi lại, lần thử, IP/thiết bị theo threat model; giảm khả năng đoán tài khoản qua message khác nhau.
6. Gửi qua kênh tin cậy, hạn chế rò qua referrer, logs, browser history, analytics; sau khi consume, chuyển về URL không chứa token.
7. Có phương án phục hồi tài khoản, hủy token chưa dùng, khóa đường abuse và audit an toàn.

Link email có rủi ro bị **email security scanner hoặc link preview** truy cập trước người dùng. Thiết kế giao thức không nên đặt hành động nhạy cảm/đăng nhập không thể đảo ngược vào một HTTP GET tự động mà scanner có thể kích hoạt; cân nhắc bước xác nhận có chủ đích và chính sách consume thích hợp.

### 5.2. TOTP cần gì?

Mã TOTP thường dựa trên một secret chia sẻ và bước thời gian. Bên cạnh thuật toán, sản phẩm cần:

- Enrollment/verify secret ban đầu; chỉ kích hoạt factor sau khi user chứng minh đã cấu hình authenticator.
- Bảo vệ secret ở trạng thái lưu trữ, không đưa lại secret cho người ngoài sau enrollment; backup/rotation có kiểm soát.
- Cửa sổ chấp nhận lệch thời gian giới hạn, **chống dùng lại mã** trong khoảng xác thực, và giới hạn retry.
- Recovery codes có entropy cao, lưu dạng bảo vệ, dùng một lần; support flow tránh trở thành con đường vượt MFA.
- Quy tắc kết hợp với primary authentication: mật khẩu + TOTP là hai yếu tố khi độc lập và áp dụng đúng, còn một mã TOTP tự nó không đủ minh chứng mọi chính sách.

Đừng so sánh “có một mã 6 chữ số” với WebAuthn rồi kết luận cả hai chống phishing như nhau. Khả năng chống phishing và khả năng phục hồi phải đánh giá riêng.

## 6. Passkey/WebAuthn: phiên bản framework và trách nhiệm credential store

WebAuthn sử dụng **public-key credential** được đăng ký với một relying party. Phía authenticator giữ private key; ứng dụng/IdP kiểm chứng challenge response với public key và metadata cần thiết.

```text
Đăng ký passkey
 Browser + authenticator -> tạo credential key pair
            |
            +--> Spring Security / WebAuthn server component
            |       kiểm chứng challenge, origin, rpId
            v
     Credential repository -> lưu public key, credential ID,
                              user binding, metadata cần thiết

Đăng nhập bằng passkey
 Browser + authenticator -> ký challenge cho đúng RP
            |
            v
     Server xác minh chữ ký, challenge, origin/rpId,
     user presence/verification theo chính sách
            |
            v
      Authentication -> authorization -> session
```

**Câu hỏi đầu tiên là phiên bản**: trong nhánh Spring Security 6.x, WebAuthn/passkey support được bổ sung ở **6.4+**. Ứng dụng đang chạy Boot 3.3.x được quản lý bằng một phiên bản Spring Security cũ hơn có thể **không nhận** cùng DSL/API từ tài liệu 6.4+. Trước khi áp dụng ví dụ trên mạng, kiểm tra dependency tree và phiên bản reference docs của WebAuthn.

**Câu hỏi thứ hai là kiến trúc lưu trữ.** Một flow test chạy được với repository thử nghiệm không có nghĩa đã có credential storage production: phải xét schema, backup, transaction, account ID, credential ID uniqueness, cập nhật sign counter/metadata nếu sử dụng, revoke credential và audit. Nếu passkey gắn với account nhưng còn phương án reset mật khẩu/email yếu, luồng recovery có thể hạ mức bảo mật tổng thể.

**Câu hỏi thứ ba là ranh giới origin.** RP ID, origin, HTTPS, môi trường local, reverse proxy/forwarded headers, domain staging/production và kiến trúc đa subdomain phải nhất quán. Không lấy `Host` hoặc `X-Forwarded-Host` không đáng tin làm RP ID quyết định quyền. Browser WebAuthn enforce origin/rpId; backend cũng phải validate đúng.

**Câu hỏi thứ tư là loại authenticator.** Platform authenticator và roaming security key khác nhau về trải nghiệm/khả năng sao lưu. Dự án cần định nghĩa user verification requirement, đồng bộ passkey, thay thiết bị, thu hồi và trường hợp không có authenticator.

Nếu có IdP enterprise đã quản lý passkey, ứng dụng có thể chỉ dùng `oauth2Login` và trust policy đã thương lượng với IdP, thay vì tự làm passkey server. Khi cần step-up, phải có hợp đồng xác minh mức xác thực, không chỉ tin rằng “người dùng từng sử dụng passkey”.

## 7. Chọn dùng IdP hay tự xây MFA?

### 7.1. Trường hợp ưu tiên IdP

Hệ thống có nhiều ứng dụng, người dùng doanh nghiệp, yêu cầu MFA/passkey/phân quyền tập trung, conditional access, risk-based login và quản lý thiết bị thường có lợi khi tích hợp **OIDC/SAML 2.0** với IdP có sẵn.

Ứng dụng Servlet nhận authentication từ flow của IdP và tạo session của chính ứng dụng nếu cần. Spring Security giúp xử lý protocol, validate token/assertion theo cấu hình. Nhưng ứng dụng vẫn sở hữu:

- **Account linking**: ánh xạ định danh ổn định (`issuer + subject` với OIDC) vào user nội bộ; không tự gộp chỉ theo email.
- **Authorities/permissions**: ánh xạ claims/groups có kiểm chứng sang quyền nghiệp vụ, áp dụng deny-by-default và dữ liệu quyền mới nhất.
- **Chính sách step-up**: hoạt động nhạy cảm cần assurance, auth age hoặc factor phù hợp; xác minh IdP thực sự đáp ứng.
- **Session lifecycle**: cookie, CSRF, logout, TTL, invalidation khi quyền thay đổi, các phiên hoạt động đồng thời.
- **Bảo vệ business flow**: đối soát giao dịch, authorization ở backend, audit và cảnh báo.
- **Tình trạng sự cố**: IdP downtime, signing key rotation, clock skew, redirect URI, redirect loop.

**OAuth2 login khác OAuth2 resource server**: `oauth2Login()` cho browser user login (OIDC khi sử dụng scope `openid`); `oauth2ResourceServer()` cho API nhận access token. Cả hai có thể chia sẻ một IdP nhưng không thay thế nhau.

### 7.2. Trường hợp có thể tự xây

Tự xây khi tổ chức có giao thức/thiết bị đặc thù hoặc IdP không thể đáp ứng nhưng **có đội ngũ bảo mật vận hành lâu dài**. Ranh giới trách nhiệm cần được xác nhận: ai phát token, ai chịu TTL/replay, ai giải quyết account recovery, ai bảo vệ secret và ai kiểm thử khi Spring Security nâng cấp.

Một provider custom không tự an toàn chỉ vì implement `AuthenticationProvider`. Thiết kế cần audit đúng nghiệp vụ, rate limiting, anti-enumeration, transaction-bound verification, xử lý timeout/atomic state, secure logging và các test lạm dụng.

Một cách lai thường hợp lý: **IdP xác thực người dùng**, ứng dụng **tự thực thi policy giao dịch** và gọi IdP để step-up khi cần. Không đưa toàn bộ logic duyệt thanh toán vào claim đăng nhập vốn có thể đã được cấp từ nhiều giờ trước.

## 8. Ví dụ runnable: baseline xác thực Servlet trên Spring Boot 3.3.x

Mục tiêu ví dụ: kiểm chứng những gì Spring Security 6.x phổ biến **thực sự cung cấp sẵn** trước khi thêm MFA. Ứng dụng có form login, password được BCrypt hash, endpoint cần role, CSRF/session mặc định, và test authorization. Đây là baseline **single-factor**, không tự nhận là OTP/passkey/MFA.

### 8.1. Tạo dự án

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo Java package `demo.features`. File `src/main/java/demo/features/FeatureDecisionApplication.java`:

```java
package demo.features;

import java.security.Principal;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FeatureDecisionApplication {
    public static void main(String[] args) {
        SpringApplication.run(FeatureDecisionApplication.class, args);
    }

    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/account")
    public Map<String, String> account(Principal principal) {
        return Map.of("user", principal.getName(), "page", "account");
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
```

File `src/main/java/demo/features/SecurityConfig.java`:

```java
package demo.features;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder, @Value("${DEMO_PASSWORD}") String password) {
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/account").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Để chạy với Gradle Wrapper, thiết lập biến môi trường trong terminal local được kiểm soát rồi chạy:

```bash
export DEMO_PASSWORD='choose-a-long-local-demo-password'
./gradlew bootRun
```

Đây là lệnh cho Bash. Nếu dùng PowerShell, đặt biến môi trường theo cú pháp của PowerShell thay vì copy `export`. Không hardcode mật khẩu production vào file cấu hình hoặc commit secret.

Mở `http://localhost:8080/` sẽ thấy:

```text
public
```

Mở `http://localhost:8080/account` khi chưa đăng nhập: browser được chuyển đến trang đăng nhập mặc định. Đăng nhập với `learner` và mật khẩu demo sẽ trả JSON:

```json
{"page":"account","user":"learner"}
```

Thứ tự field trong JSON object không được bảo đảm; ví dụ chỉ mô tả giá trị. Người dùng `learner` không có `ROLE_ADMIN` nên truy cập `/admin` bị 403. Spring Security xử lý login/session/authorization; ứng dụng thực tế vẫn phải xây user store, đăng ký tài khoản, password reset, audit, MFA policy và cách cấp/thu hồi quyền.

**Cảnh báo về mục tiêu:** ví dụ giữ CSRF bảo vệ mặc định. Đừng tắt `csrf` để các request POST “dễ test” hơn. Mật khẩu chỉ dành cho môi trường local, không phải hệ thống danh tính production.

### 8.2. Test chính sách với MockMvc

File `src/test/java/demo/features/SecurityConfigTest.java`:

```java
package demo.features;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "DEMO_PASSWORD=local-test-secret")
@AutoConfigureMockMvc
class SecurityConfigTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPageWorksWithoutLogin() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk());
    }

    @Test
    void accountRequiresLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", endsWith("/login")));
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void accountShowsAuthenticatedUser() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void normalUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin-test", roles = "ADMIN")
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin"))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test dùng `@WithMockUser` để kiểm tra **authorization rules**, không xác thực thật bằng password. Để xác minh form login, cần test riêng request POST `/login` với CSRF token và in-memory user, hoặc kiểm thử browser; để xác minh MFA, cần **bộ test khác** chứng minh user có password-only không được phép vào endpoint yêu cầu factor thứ hai.

### 8.3. Vì sao baseline không nên được gọi là MFA?

Trong mã trên, sau một lần nhập mật khẩu, Spring Security tạo `Authentication` đã xác thực. Rule `authenticated()` ở `/account` chỉ yêu cầu principal đã login, **không mô tả số yếu tố**. Muốn bảo vệ `/payments/confirm`, dự án phải đưa ra thêm hợp đồng: factor, thời điểm, chính sách reauth, user/session binding, chặn bypass và recovery. Nếu ở version có hỗ trợ MFA framework, cấu hình policy/DSL tương ứng; nếu không, IdP hoặc custom flow có kiểm thử là lựa chọn thích hợp. Không tự quảng bá một marker authority không được kiểm chứng thành yếu tố bảo mật.

## 9. Thiết kế ranh giới khi tích hợp nhiều hình thức

Một ứng dụng có thể cùng hỗ trợ portal OIDC, passkey trực tiếp, API bearer token và một số flow OTP. Nhưng có nhiều `AuthenticationProvider`/filter **không đồng nghĩa** chúng phối hợp an toàn.

Mẫu kiến trúc:

```text
Portal browser
  +-- OIDC client / browser session
  +-- Step-up policy được IdP hoặc hệ thống nội bộ bảo đảm
  |
API machine-to-machine
  +-- Resource server (JWT/opaque access token)
  +-- Audience/scope + per-resource authorization
  |
Recovery / device management
  +-- Endpoint bảo vệ riêng, rate limit và audit
  +-- Chỉ cho phép thay đổi factor sau khi chứng minh account ownership
```

**Tách security chain theo URL** khi cần, dùng `securityMatcher(...)` và thứ tự chain rõ ràng. Giữ fallback không vô tình `permitAll` cho URL không khớp. Tránh trộn session cookie với API bearer token rồi chấp nhận mọi phiên bản Authentication cho thao tác đòi assurance cao.

Chính sách phân quyền vẫn phải kiểm tra **business permission**. Ví dụ một user có MFA pass nhưng không thuộc nhóm quản lý giao dịch thì vẫn **không được** phê duyệt chuyển tiền. MFA xác nhận bằng chứng danh tính; authorization xác nhận quyền hành động.

## 10. Phiên bản, nâng cấp và vận hành

### 10.1. Checklist trước khi bật tính năng mới

1. **Chốt yêu cầu:** login bằng gì, MFA khi nào, yếu tố nào, recovery, mức assurance và quy trình thu hồi.
2. **Đối chiếu BOM:** lấy exact resolved `spring-security-*` artifacts; kiểm tra rằng tính năng/DSL tồn tại trong minor version đó.
3. **Đọc reference docs đúng version:** API/DSls `SecurityFilterChain`, `AuthenticationProvider`, repository và filter ordering; không copy ví dụ bản mới cho dự án bản cũ.
4. **Kiểm tra module:** thêm dependency cần thiết thay vì hy vọng starter security lõi bao gồm SAML2, LDAP, OAuth2 client hay resource server.
5. **Vẽ threat model:** account enumeration, brute-force, phishing, replay, session fixation, CSRF, XSS, proxy trust, callback/redirect và account recovery.
6. **Đặt ranh giới IdP/app:** bên nào xác thực factor, kiểm chứng claim, lưu secret/cert, phát/consume token, gửi mail và có quyền reset.
7. **Test trên staging:** đăng ký factor, login hợp lệ, login sai, khóa/revoke, lost device, concurrent requests và lúc IdP/DB/email down.
8. **Đặt metrics và audit:** success/failure, step-up challenge, recovery changes, credential add/remove, auth age, cảnh báo abnormal.
9. **Có rollback và migration plan:** dữ liệu credential cũ, session/token đang còn hiệu lực, downtime, chuyển đổi factor khi phiên bản đổi.
10. **Kiểm chứng kết quả:** phân biệt test Spring Security primitives với E2E browser/TLS/IdP, không tuyên bố tính năng hoàn thành chỉ vì unit tests pass.

### 10.2. Những lỗi nâng cấp thường gặp

**Lỗi 1 — Dùng API mới cho project còn ở bản cũ.** Một bài WebAuthn/one-time token viết cho Spring Security 6.4+ không được copy nguyên vào Boot 3.3.x đang quản lý Security thấp hơn. Kiểm tra dependency tree, sau đó nâng cấp tương thích nếu cần.

**Lỗi 2 — Tự nâng duy nhất `spring-security-web` nhưng bỏ các module khác.** Trộn `spring-security-config`, `web`, `core`, OAuth2 modules ở các version không tương thích có thể gây lỗi hoặc hành vi bất ngờ. Ưu tiên BOM và quy trình dependency management được hỗ trợ.

**Lỗi 3 — Nhầm filter tạo xác thực với bước xác minh MFA.** Login một yếu tố không tự chuyển thành nhiều yếu tố; step-up phải được enforce tại endpoint và trạng thái factor đáng tin.

**Lỗi 4 — Đánh đồng OTP email với TOTP hoặc passkey.** Phương thức có threat model, independence và phishing resistance khác nhau. Cần tiêu chí chọn theo tài khoản và giao dịch nhạy cảm.

**Lỗi 5 — Chỉ kiểm tra happy path.** User mất thiết bị, mail chậm, IdP down, OTP bị dùng lại, rút quyền, hai request consume đồng thời mới là nơi dễ xuất hiện bypass.

**Lỗi 6 — Dùng recovery yếu hơn hẳn yếu tố chính.** Đường reset email hoặc support desk không kiểm tra ownership có thể làm mất giá trị passkey/MFA.

**Lỗi 7 — Bỏ mất quyền ứng dụng.** Một user vừa login qua IdP vẫn phải bị từ chối khi không đủ role/resource permission. Assurance và authorization là hai chiều độc lập.

**Lỗi 8 — Bỏ bảo vệ session vì “đã có MFA”.** CSRF, cookie, fixation, session timeout, logout, token leakage và XSS vẫn quan trọng.

## 11. Ma trận kiểm thử theo bản phát hành và trách nhiệm

| Nhóm thử nghiệm | Điều kiện PASS | Tầng chịu trách nhiệm |
|---|---|---|
| Dependency/version gate | Tính năng, DSL, module tồn tại đúng resolved version; build/test sạch | Build pipeline + framework |
| Form login + password | Đăng nhập đúng hoạt động, password sai không được login, CSRF/session đúng | Framework + ứng dụng |
| OIDC/SAML login | Issuer/signature/audience/state/nonce/redirect hợp lệ theo giao thức; unknown issuer bị từ chối | IdP + Spring Security |
| Passkey enrollment | Chủ tài khoản được kiểm chứng, RP/origin đúng, credential liên kết đúng user, có revoke/recovery | WebAuthn component + app/IdP |
| One-time token | TTL, one-use atomic, request lặp bị từ chối, không rò token ra logs, scanner không kích hoạt nhầm | Framework token service + app delivery |
| TOTP | Correct code, skew window có giới hạn, wrong/replayed code từ chối, recovery codes dùng một lần | Auth service/app/IdP |
| MFA step-up | Password-only không vào trang đòi factor; verified factor đúng policy thì mới được vào | Authorization policy + trusted factor state |
| Role/permission | MFA user không có quyền nghiệp vụ vẫn bị 403 | Application authorization |
| Revocation | Khi xóa credential/khóa user, quyền đăng nhập/tác vụ bị chặn theo SLA | App/IdP/session store |
| Downtime | Lỗi IdP/email/DB không rơi về anonymous-but-authorized hoặc tự bỏ qua factor | Service resilience |
| Multi-chain | Portal/API/recovery đi đúng filter chain; fallback an toàn | Spring Security config + tests |
| Upgrade regression | Build, login, token checks, session, step-up, recovery và audit hoạt động trên version mới | CI/E2E + vận hành |

**Ví dụ kiểm thử step-up bắt buộc:** tạo user test chỉ có password-authenticated state; yêu cầu POST đến endpoint nhạy cảm với **CSRF hợp lệ** (để không nhầm CSRF 403 thành step-up) và kiểm tra không có thay đổi nghiệp vụ, có challenge đúng. Lặp lại với factor state hợp lệ và user đủ quyền; sau đó thử factor hết hạn, chuyển principal, logout, replay và account bị khóa. Các test này phải nối với cơ chế thực hiện factor thật, không chỉ đặt flag bằng tay rồi khẳng định an toàn.

## 12. Quy tắc ra quyết định và ghi nhớ

Quy trình lựa chọn có thể tóm tắt thành bốn bước:

1. **Chọn ai thực thi xác thực.** Nếu IdP doanh nghiệp đã có MFA/passkey, ưu tiên tích hợp chuẩn với IdP; nếu cần phương thức đặc thù, đánh giá khả năng hỗ trợ của phiên bản Spring Security đang dùng.
2. **Chọn API theo exact version.** Trong 6.x, không suy ra tính năng 6.4+ có ở tất cả bản 6.x; khi lên dòng mới hơn, kiểm tra migration guide và các default trước khi copy code.
3. **Lập danh sách phần phải xây/duy trì.** Enrolment, credential store, email delivery, secret lifecycle, recovery, session, step-up, role mapping, audit và chống lạm dụng thường vượt ra ngoài cấu hình một filter.
4. **Test điều kiện thất bại.** Không chỉ “đăng nhập được”, mà phải chứng minh user chưa đạt factor/không đủ quyền bị từ chối, token không replay, recovery an toàn và session có thể bị thu hồi.

**Kết luận:** Spring Security Servlet cung cấp **những khối xây dựng xác thực và phân quyền**, với phạm vi thay đổi theo phiên bản; ứng dụng hoặc IdP phải hoàn thiện **policy, vòng đời credential, UX, recovery và vận hành bảo mật**. Một giải pháp xác thực nâng cao chỉ được xem là hoàn chỉnh khi cả hai nửa — năng lực framework đúng phiên bản **và** trách nhiệm sản phẩm — đều được xác định, triển khai và kiểm thử.