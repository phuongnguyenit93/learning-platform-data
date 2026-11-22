# Phát hiện đăng nhập bất thường và quy trình thu hồi truy cập

## 1. Vì sao đăng nhập thành công vẫn có thể là sự cố bảo mật?

Spring Security có thể xác thực đúng mật khẩu, OTP, passkey hoặc Bearer token, nhưng điều đó **không tự chứng minh người đang thao tác là chủ tài khoản hợp pháp**. Ví dụ: attacker có credential bị lộ, refresh token bị đánh cắp hoặc session cookie bị chiếm; bước kiểm tra chữ ký/token có thể vẫn thành công. Ứng dụng cần một lớp **giám sát rủi ro** (anomalous login detection) và một **quy trình containment/thu hồi truy cập** độc lập với logic kiểm tra credential.

Bài học thuộc nhóm **Vận hành** của module **Spring Security - authentication**, tập trung vào hành vi **sau và trong quá trình xác thực**:

1. Thu thập tín hiệu từ những điểm kiểm soát đúng: login thành công/thất bại, MFA challenge, token refresh, session activity và các thay đổi bảo mật.
2. Phát hiện bất thường có cân nhắc false positive: thiết bị mới, tốc độ thử sai, IP/ASN rủi ro, travel bất khả thi, MFA fatigue, refresh token reuse, account takeover signals.
3. Đánh giá rủi ro để chọn **quan sát, thông báo, yêu cầu re-auth/step-up, giới hạn thao tác hoặc thu hồi**; không tự động khóa mọi account chỉ vì IP mới.
4. Khi cần thu hồi, xử lý **tất cả cơ chế truy cập liên quan**: local session, remember-me, refresh-token family, access token, device grants, passkeys/credentials nghi ngờ và phiên SSO ở identity provider (nếu có thể).
5. Phân biệt thực tế **JWT offline validation**, **opaque introspection**, OAuth token revocation, session invalidation và thay password/MFA.
6. Thiết kế transaction, audit/outbox, multi-node propagation, test race và runbook vận hành để có thể chứng minh một sự cố đã được containment.
7. Đảm bảo người dùng hợp pháp có đường recovery an toàn, không tạo denial-of-service hoặc user enumeration qua thông báo và tự động khóa.

**Giả định kỹ thuật:** Java 17+, Spring Boot 3.x / Spring Security 6.5.x Servlet, HTTP session và/hoặc OAuth2 Resource Server. Các phần WebFlux/IdP có lưu ý riêng. Mã Java ở mục 8 là mô phỏng domain **độc lập JDK**, còn ví dụ Spring Security là snippet tích hợp được ghi rõ phạm vi, không phải hệ thống bảo mật hoàn chỉnh.

### Phân biệt bốn khái niệm

| Khái niệm | Nội dung | Giới hạn |
| --- | --- | --- |
| **Authentication event** | Có yêu cầu xác thực thành công hoặc thất bại | Không chứng minh hành động là hợp pháp |
| **Risk/anomaly signal** | Dữ kiện có thể bất thường so với lịch sử hoặc chính sách | Không phải bằng chứng kết luận account takeover |
| **Risk decision** | Quyết định allow, step-up, restrict, revoke, review | Cần đo false positive và quyền override |
| **Revocation/invalidation** | Làm credential/session/grant không còn được chấp nhận | Phải áp dụng ở đúng resource server và node; không tự xảy ra cho mọi loại token |

Đổi mật khẩu **không mặc nhiên** đăng xuất tất cả session và cũng không làm JWT đã cấp hết hiệu lực nếu verifier chỉ kiểm tra chữ ký/`exp`. Đăng xuất trình duyệt hiện tại **không tương đương** thu hồi các session khác, refresh tokens hoặc phiên IdP. Hãy coi đây là các việc khác nhau trong incident playbook.

## 2. Nguồn sự kiện và mô hình telemetry

Một pipeline vận hành điển hình:

~~~text
Login / MFA / token refresh / API activity / account settings
           |
           v
Spring Security hooks + application domain events
           |
           v
Normalize (loại credential, gắn request/trace/account refs)
           |
           v
Message queue / transactional outbox / security event store
           |
           v
Risk rules, velocity windows, device/session correlations
           |
        +--+--+
        |     |
      low    medium/high
        |     |
     audit  step-up / restrict / alert / revoke
              |
              v
       Incident record + immutable audit
              |
              v
       Notification + user recovery + review
~~~

Không có một filter duy nhất nhìn thấy **mọi** sự kiện. Login password, OAuth2 Login, OTP, JWT Resource Server, refresh token endpoint (thường nằm ở Authorization Server), WebAuthn, logout và thay mật khẩu đi qua các thành phần khác nhau. **Phải kiểm kê thực tế** từng endpoint và đơn vị sở hữu: service nào phát hành session/token, service nào xác minh, service nào có quyền revoke.

### Các trường sự kiện nên cân nhắc

| Trường | Ví dụ | Mục đích và bảo vệ |
| --- | --- | --- |
| `event_type` | `AUTH_SUCCESS`, `AUTH_FAILURE`, `REFRESH_REUSE` | Phân biệt tình huống |
| `time_utc` | Timestamp server | Phân tích chuỗi và velocity |
| `request_id`, `trace_id` | UUID/opaque | Tìm request/trace liên quan |
| `account_ref` | Stable nội bộ ID hoặc pseudonym HMAC | Correlate nhiều sự kiện, tránh ghi email thô |
| `session_ref` / `token_jti_ref` | Hash/opaque reference, không phải raw token | Tìm session/token liên quan |
| `factor_type` | PASSWORD, PASSKEY, TOTP | Phân biệt assurance của phương thức |
| `result` / `reason_internal` | SUCCESS, BAD_CREDENTIAL, LOCKED, SERVICE_ERROR | Reason chỉ cho vận hành |
| `network_context` | ASN, IP risk band, country coarse | Có thể hỗ trợ cảnh báo; là dữ liệu cá nhân cần chính sách |
| `device_context` | Device registration ID tin cậy hoặc signal có giới hạn | Không biến browser fingerprint thành chứng cứ xác thực |
| `risk_decision` | ALLOW, STEP_UP, RESTRICT | Có thể đánh giá chất lượng rule |
| `incident_id` | Opaque case ID | Liên hệ investigation, rollback/appeal |

**Không log** password, OTP, recovery code, Bearer/access/refresh token, ID token, cookie `JSESSIONID`, private keys, TOTP secret hoặc toàn bộ request headers/body. `Authentication.getCredentials()` có thể chứa credential nhạy cảm, **không serialize trực tiếp cả Authentication object vào event bus**. Một `principal.getName()` từ login thất bại có thể là chuỗi do attacker nhập; không sử dụng như account ID đáng tin trước khi tra cứu/chuẩn hóa và kiểm soát log injection.

**Dữ liệu vị trí/IP không phải chân lý tuyệt đối**: VPN, CGNAT, mobile handoff, NAT doanh nghiệp, du lịch, proxy/CDN và shared device có thể tạo sự kiện trông bất thường. Tuân thủ nguyên tắc tối thiểu dữ liệu, retention, phân quyền truy cập, minh bạch và privacy risk assessment theo NIST SP 800-63B-4. Đừng giám sát gõ phím/sinh trắc hành vi nếu không có cơ sở pháp lý, đánh giá tác động và điều kiện bảo vệ phù hợp.

### Sự kiện cần thêm ngoài login

- Nhiều lần thất bại trên **nhiều account** cùng một nguồn, hoặc nhiều nguồn cùng thử **một account** (credential stuffing/spraying).
- `MFA_CHALLENGE_SENT`, `MFA_CHALLENGE_FAILED`, `MFA_CHALLENGE_APPROVED`, số lần push bất thường (MFA fatigue).
- Phát hành/đổi refresh token và **reuse của refresh token đã rotate**, nếu authorization server hỗ trợ detection.
- Một session hoạt động đồng thời trong bối cảnh nghi vấn hoặc thay đổi device/token binding bất thường.
- Thêm/xóa passkey, TOTP, đổi email/số nhận recovery, phát lại recovery codes, thay password, API key creation, liên kết IdP mới.
- Yêu cầu export dữ liệu nhạy cảm, thay quyền admin, thay phương thức thanh toán hoặc mở endpoint rủi ro cao ngay sau login lạ.

**Hạn chế quan trọng:** không dựa đơn thuần vào bộ đếm thất bại trong RAM một node để bảo vệ toàn hệ thống có nhiều node/region. Velocity counters cần store chung và chiến lược expiry/consistency phù hợp, có biện pháp tránh attacker ép khóa hàng loạt người dùng.

## 3. Phát hiện bất thường: tín hiệu, ngữ cảnh và quyết định

Không có một ngưỡng thần kỳ dùng cho mọi sản phẩm. Khung đánh giá rủi ro thường kết hợp **mức độ đáng tin của tín hiệu**, **giá trị dữ liệu/khả năng tác động**, **lịch sử hợp lệ của account** và **sự kiện sau đăng nhập**. Một user đi công tác và đổi IP là một false positive thường thấy; trái lại refresh token reuse sau rotation là tín hiệu mạnh hơn nhiều nhưng vẫn cần quy trình điều tra.

| Signal | Diễn giải | Nguy cơ false positive | Phản ứng điển hình |
| --- | --- | --- | --- |
| Thiết bị chưa thấy trước đây | Device registration chưa có hoặc môi trường browser khác | Private browsing, đổi điện thoại | Notify + step-up khi thao tác nhạy cảm |
| Geo-velocity bất khả thi | Hai sự kiện gần nhau ở vùng cách xa | VPN, mạng di động, IP geolocation sai | Đánh dấu xem xét, kết hợp yếu tố khác |
| IP/ASN rủi ro cao | Tor/proxy/botnet/reputation | NAT công ty hoặc traffic hợp pháp | Rate limit, step-up, điều tra |
| Nhiều lần sai password | Failed attempts theo account/IP/window | Lỗi người dùng, password manager | Throttle/risk challenge; không lộ account existence |
| MFA push spam và phê duyệt khác thường | Nhiều yêu cầu rồi accept | User thực bấm nhiều lần | Có thể restrict/revoke, yêu cầu factor phishing-resistant |
| Refresh token reuse | Token đã rotate bị tái trình diện | Race của client lỗi, retry sau mạng kém | Quarantine token family, bảo vệ account và điều tra |
| Thay yếu tố MFA ngay sau login mới | Pattern takeover | User vừa đổi máy | Fresh re-auth, delay/notify trusted channels |
| Đăng nhập mới rồi tải lượng dữ liệu lớn | Data exfiltration signal | Công việc hợp pháp | Step-up/limit theo mức nhạy cảm |
| Local/IdP account disabled nhưng còn access | Lệch trạng thái identity | Đồng bộ trễ | Từ chối theo policy, kiểm tra propagation |

### Hai tầng quyết định

1. **Detection** thu tín hiệu và chấm mức rủi ro: low/medium/high/critical. Đây là một **ước lượng** cần được đo lường; không nên trộn trực tiếp thành boolean `isBadUser`.
2. **Enforcement** ánh xạ sang một hành động phù hợp assurance: tiếp tục cho phép, yêu cầu re-auth, step-up MFA/WebAuthn, khóa tạm chức năng nhạy cảm, revoke từng session, revoke toàn account, cô lập giao dịch hay chuyển manual review.

Một policy ví dụ minh họa, **không phải tiêu chuẩn bắt buộc**:

~~~text
if verified_refresh_token_reuse:
    RESTRICT account and revoke affected token family immediately
else if credential_compromise_confirmed:
    revoke all sessions/grants; force secure recovery
else if known_bad_network && repeated_failures_above_threshold:
    rate limit / challenge / investigate; avoid blind lockout
else if new_device && sensitive_operation:
    demand fresh phishing-resistant step-up
else if new_device or unusual_location:
    notify and raise monitoring
else:
    allow subject to normal authorization and risk controls
~~~

Không biến `MFA_FAILED` thành `ACCOUNT_LOCKED` ngay nếu user có thể bị người khác spam OTP. Dùng cơ chế kháng brute force phân tầng: per IP/device/account, backoff, quota, abuse intelligence; bảo vệ privacy và không tạo đường DoS. Khi chấm điểm, những yếu tố như geolocation nên có trọng số thấp nếu độ tin cậy của dữ liệu thấp.

### Đánh giá chất lượng rule

- **Precision**: bao nhiêu alert thật sự đáng điều tra? **Recall**: bao nhiêu incident thật bị bỏ sót?
- False positive theo vùng mạng/thiết bị, nhóm người dùng hoặc bối cảnh làm việc, nhưng tránh phân biệt đối xử bằng đặc trưng nhạy cảm.
- Median/95p thời gian từ detection đến containment, số session/token còn dùng được sau containment, retry storms, tỷ lệ case bị mở nhầm.
- Thử `shadow mode` trước khi bật auto-revoke rule mới có hậu quả lớn; có kill switch/override có audit.
- Tách tín hiệu vận hành (IdP/JWK timeout) với sai credential: outage không đồng nghĩa tấn công.

## 4. Playbook từ cảnh báo tới thu hồi và khôi phục

Một quy trình cần **phân loại độ chắc chắn**, **ghi bằng chứng tối thiểu**, **contain**, **eradicate/recover** và **verify**. Tránh hai cực đoan: không thu hồi khi bằng chứng rõ; hoặc khóa người dùng vô tội vì một IP lạ.

### 4.1. Chuỗi phản ứng theo mức độ

| Mức | Ví dụ | Hành động đề xuất | Khi nào đóng case |
| --- | --- | --- | --- |
| LOW | Thiết bị mới nhưng MFA mạnh hợp lệ, không có tín hiệu khác | Ghi nhận, thông báo nếu policy | Không phát sinh thêm tín hiệu |
| MEDIUM | Thiết bị/IP lạ trước export dữ liệu nhạy cảm | Step-up đủ mới, hold chức năng high-risk | Challenge pass và hoạt động hợp lệ |
| HIGH | MFA fatigue, thay contact recovery bất thường, refresh reuse | Restrict thay yếu tố, revoke affected sessions/family, alert SOC | Chủ tài khoản xác minh, hậu kiểm quyền truy cập |
| CRITICAL | Có bằng chứng session/token bị đánh cắp, thay MFA trái phép | Contain toàn account, revoke/disable appropriate credentials và sessions, incident response | Không còn credential cũ sử dụng được, khôi phục an toàn |

NIST SP 800-63B-4 nêu rằng khi theo dõi session phát hiện nguy cơ gian lận, RP nên phối hợp để yêu cầu xác thực lại, kết thúc session hoặc báo người phụ trách phù hợp. Đây là nguyên tắc risk-based, **không yêu cầu một thuật toán chấm điểm cụ thể**.

### 4.2. Runbook phản ứng khi nghi takeover

1. **Triage**: gắn `incident_id`, thời điểm UTC, account reference, các login/session/token IDs liên quan, chứng cứ, mức tin cậy; phân quyền xem và retention.
2. **Contain**: nếu nghiêm trọng, vô hiệu thao tác nhạy cảm trước; thực hiện revoke đối với session/token phù hợp. Cân nhắc bảo vệ các tài khoản admin có quyền downstream.
3. **Thông báo kênh đã tin cậy**: email/phone cũ đã verified hoặc kênh support/thiết bị tin cậy, không chỉ contact mới do attacker vừa đổi. Không gửi link reset chứa token trong log/analytics.
4. **Kiểm soát recovery**: user phải chứng minh lại bằng yếu tố độc lập đủ assurance, ưu tiên passkey/security key; nếu mất MFA thì quy trình recovery riêng có anti-social-engineering. Không cho support mở khóa chỉ bằng `requestId`.
5. **Eradication**: đổi credential bị lộ, gỡ yếu tố giả, rotate recovery codes, thu hồi OAuth grants/API keys và thiết bị đáng ngờ, kiểm tra rule/role bị sửa.
6. **Verify**: dùng test request/token cũ từ môi trường kiểm soát để xác minh bị 401/403 hoặc step-up theo chính sách; kiểm tra mọi node/region và authorized services.
7. **Restore**: phát hành session/token mới bằng xác thực đủ mạnh, thông báo chủ tài khoản; audit ai cho phép khôi phục, lý do và quyền xem log.
8. **Post-incident**: cập nhật detection rule, chỉ số false positive, runbook, các khoảng cửa sổ JWT vẫn sống và khả năng hỗ trợ đa vùng.

**Đừng công khai lý do quá chi tiết** trong trang login anonymous: “email này tồn tại nhưng có đăng nhập từ X” có thể tạo user enumeration và lộ lịch sử. Client nên nhận response an toàn và hướng dẫn liên hệ hỗ trợ khi cần; lý do kỹ thuật nằm trong audit/log có phân quyền.

## 5. Thu hồi quyền truy cập: đúng nơi, đúng vòng đời

Một hệ thống có thể đồng thời có cookie session nội bộ, refresh token từ authorization server, JWT access token phát cho API, remember-me cookie, WebAuthn credential, OAuth authorized client và session tại IdP. **Thu hồi mỗi thứ là một thao tác khác nhau**.

| Tài sản | Cách chặn truy cập | Giới hạn thường gặp |
| --- | --- | --- |
| **Local `HttpSession`** | Invalidate session trong session store; đăng xuất từ xa hoặc kiểm tra account security version/revocation flag trên request | `SecurityContextLogoutHandler` của current request không tự thu hồi mọi session ở node khác |
| **Session registry** | `SessionRegistry` + concurrent session support có thể đánh dấu `SessionInformation.expireNow()` | In-memory registry không là global multi-node kill switch; phải có integration phù hợp |
| **Remember-me token** | Xóa persistent token phía server và cookie khi logout; rotate remembered device keys theo policy | Cookie trong thiết bị bị đánh cắp cần bị chặn server-side |
| **Refresh token/family** | Revoke grant/token family ở Authorization Server, disable reuse sau rotation | Không tự khiến JWT access token hiện tại hết hạn |
| **JWT access token offline** | Denylist `jti`/session, check `security_version`/user active tại mọi resource server, hoặc TTL ngắn và chấp nhận residual lifetime | Chỉ đổi password/xóa refresh token không vô hiệu chữ ký `JWT` đã phát |
| **Opaque access token** | Authorization Server trả `active=false` ở introspection; Resource Server kiểm tra lại theo cache TTL | Cache introspection có thể trì hoãn hiệu lực |
| **OAuth grant ở IdP** | RFC 7009 token revocation/IdP admin API hoặc client logout profile phù hợp | Provider hỗ trợ/cascade khác nhau; không đồng nghĩa xóa user tại IdP |
| **IdP SSO session** | RP-initiated logout, back-channel logout hoặc API của IdP nếu được hỗ trợ | IdP session và RP session độc lập, phải phối hợp |
| **Authenticator/passkey/TOTP** | Revoke thiết bị/credential mapping và rebind an toàn | Không chỉ reset session là đã bỏ credential bị chiếm |
| **API keys/service credentials** | Rotate/revoke keys và scope trong kho quản lý key | Nằm ngoài `HttpSession` và thường sống lâu |

### 5.1. Spring Security logout chỉ giải quyết current session theo phạm vi

Trong Servlet, `POST /logout` (với CSRF token nếu bật CSRF) thường sử dụng `SecurityContextLogoutHandler` để invalidate `HttpSession`, xóa SecurityContext và xử lý thành phần logout khác. Điều này hữu ích nhưng **không có bảo đảm revoke tất cả các session, refresh token hay JWT ở mọi dịch vụ**.

Để có chức năng "Đăng xuất mọi thiết bị", phải xây kho session đáng tin, quản lý device/session IDs, expire/revoke trong shared store hoặc triển khai **account security version** được kiểm tra tại điểm nhận request. Nếu sử dụng `SessionRegistry`:

~~~java
// Pseudocode trong service đã có SessionRegistry và principal đúng:
// SessionInformation: org.springframework.security.core.session.SessionInformation
for (SessionInformation session :
        sessionRegistry.getAllSessions(principal, false)) {
    session.expireNow();
}
~~~

Đoạn này **không phải service đầy đủ**: phải có concurrent session management/filter nhận biết session đã expired, registry phải nhìn thấy các session và phù hợp multi-node; `expireNow()` chỉ đánh dấu, không bảo đảm xóa từ xa cookie đang được sử dụng ở node khác. Không quét bừa `getAllPrincipals()` để xóa bằng tên hiển thị; định danh phải ổn định và đúng tenant.

### 5.2. JWT access token và tính chất "stateless"

Nếu Resource Server chỉ kiểm tra signature + `iss`/`aud`/`exp` thì một JWT đã được ký hợp lệ có thể tiếp tục hoạt động cho tới `exp` dù account bị khóa hoặc refresh token bị thu hồi. Để có thu hồi gần thời gian thực, các Resource Server phải thực thi **một chính sách kiểm tra trạng thái**:

- Check `account.security_version`/`session_version` từ một nguồn dữ liệu tin cậy, so với giá trị được ràng buộc lúc phát token; phiên bản bị tăng thì token cũ bị từ chối.
- Hoặc denylist `jti` có TTL tới lúc token hết hạn; kiểm tra đúng audience/issuer và không làm rò raw token.
- Hoặc dùng opaque introspection, token binding hoặc cơ chế access token có thời hạn ngắn cùng refresh-token rotation; đánh đổi latency/availability/consistency.
- Với access JWT phát từ **IdP bên ngoài**, local app không tự thêm `security_version` vào token cũ được; cần giao thức hỗ trợ, denylist/claims policy riêng hoặc cơ chế remote check.

**Điều kiện quan trọng:** một Resource Server nào không kiểm tra phiên bản/denylist sẽ **không** thu hồi theo lệnh chỉ thực hiện ở user database. Cache account status quá lâu cũng tạo cửa sổ tồn tại. Hãy ghi và test **upper bound revocation lag** theo threat model. Trong sự cố cao, fail closed tại endpoint nhạy cảm nếu revocation state không thể truy vấn; tránh silent bypass vì store gặp lỗi.

### 5.3. OAuth2 token revocation và RFC 7009

RFC 7009 mô tả endpoint thu hồi token. Authorization Server được yêu cầu hỗ trợ revocation của **refresh tokens**, và được khuyến nghị hỗ trợ revocation của **access tokens**; việc revoke token có thể ảnh hưởng cả grant/các token liên quan tùy chính sách AS. Client gửi yêu cầu tới revocation endpoint HTTPS tin cậy theo cơ chế client authentication phù hợp, **không log raw token**.

**Không khẳng định rằng revoke refresh token sẽ lập tức vô hiệu mọi access token** nếu AS không hỗ trợ access-token revocation hoặc resource servers verify JWT hoàn toàn offline. NIST cũng lưu ý phiên IdP và RP độc lập: logout tại RP chưa chắc logout IdP, và ngược lại.

### 5.4. Thu hồi theo phạm vi

- **Revoke một session/device** khi có bằng chứng thiết bị bị mất nhưng các phiên còn lại đủ tin cậy.
- **Revoke một refresh token family** khi phát hiện reuse hoặc token theft ở family ấy.
- **Revoke tất cả user sessions/grants** khi account takeover nghiêm trọng, password/MFA bị chiếm hoặc chính sách pháp lý yêu cầu.
- **Disable account tạm thời** khi chưa có phương thức recovery an toàn, nhưng phải chống attacker gây khóa người dùng hợp pháp bằng giả mạo tín hiệu.
- **Rotate credentials** là bước khắc phục nguồn gốc, khác với revoke session/tokens đã phát.

Quyết định mức nào phụ thuộc độ tin cậy của tín hiệu và hậu quả nghiệp vụ. Những tác vụ như xóa factor cuối cùng, đổi email recovery và cấp quyền admin phải được bảo vệ kể cả sau khi user đã qua một lần login bình thường.

## 6. Kiến trúc thu hồi multi-node và race conditions

Giả sử login tạo hai session trên hai node, cùng một refresh-token family phát JWT access token 15 phút. Lệnh "Logout all" chỉ gọi `invalidate()` trên session của request hiện tại thì node còn lại vẫn có thể chấp nhận cookie; JWT trong thiết bị khác vẫn hợp lệ. Vì vậy phải có một **nguồn trạng thái dùng chung** hoặc kênh revocation mà **mọi verifier** tuân thủ.

### Dữ liệu tham khảo cho app-owned sessions

~~~sql
CREATE TABLE account_security (
    user_id VARCHAR(64) PRIMARY KEY,
    security_version BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE app_session (
    id_hash VARCHAR(128) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES account_security(user_id),
    security_version BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX idx_session_user_active
    ON app_session(user_id, revoked_at);

CREATE TABLE security_incident (
    incident_id UUID PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES account_security(user_id),
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    decision_reason VARCHAR(120) NOT NULL
);

CREATE TABLE security_outbox (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES security_incident(incident_id),
    event_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ
);
~~~

Schema chỉ minh họa cấu trúc; `id_hash` không chứa raw session cookie. Sản phẩm thật cần tenant isolation, unique constraints, expiry cleanup, migration, index, logging và concurrency policy phù hợp. Không giả định mọi app phải xây bảng riêng nếu đã dùng Spring Session/Redis với cơ chế index và invalidate phù hợp.

### Transaction, propagation và kiểm soát race

~~~text
Incident accepted (authorized actor / verified policy)
      |
      v
DB transaction:
  lock account security row
  increment security_version
  mark affected local sessions/grants revoked
  record incident + outbox event atomically
  commit
      |
      v
Workers deliver revocation events / clear caches / call AS & IdP APIs
      |
      v
All verifiers check new state on requests
      |
      v
Audit evidence of confirmed acknowledgments and failures
~~~

**Phân biệt local transaction và external side effects:** giao dịch DB không thể bao phủ atomic tất cả remote IdP/Authorization Server. Dùng **outbox + retry idempotent + deadline + dead-letter queue + alert** cho cleanup bên ngoài. Một request thu hồi có thể thành công ở app nhưng vẫn đang `PENDING_EXTERNAL_REVOKE`; không báo "đã thu hồi mọi thứ" khi chưa xác nhận.

**Race cần test**: Token refresh diễn ra đồng thời với revoke. Kiểm tra phiên bản account/security status **trong cùng transaction** với phát token/rotate refresh hoặc có cơ chế kiểm soát phiên bản tương đương. Nếu chỉ check trước revoke, request đang bay có thể phát **token mới sau khi tài khoản bị thu hồi**. Hệ thống nhiều region phải định nghĩa consistency/replication lag; eventual consistency tạo cửa sổ dùng lại token.

**Idempotency:** sự kiện revoke có thể được replay bởi queue; việc tăng `security_version` lặp quá nhiều có thể liên tục đá session mới sau recovery. Lưu `incident_id`/`action_id` duy nhất và đánh dấu xử lý để cùng quyết định chỉ gây tác dụng một lần. Chỉ hồi phục account sau khi đã xác thực lại và reset state theo policy.

### Xử lý khi cache/trạng thái revocation không truy cập được

Một API nên có risk-tier policy:

- Endpoint high-risk (thay password, thêm MFA, chuyển tiền, lấy PII): nếu không thể xác minh session/securityVersion đáng tin, **fail closed** hoặc chuyển trạng thái read-only/reauth.
- Endpoint low-risk: có thể áp availability policy đã được phê duyệt và TTL cache nghiêm ngặt, nhưng **không được lặng lẽ giả rằng revocation check thành công**.
- API dùng JWT offline: thiết kế sẵn maximum time-to-revoke nếu không có online check, đo lường và công bố rõ trong vận hành.
- Nếu revoke diễn ra ở nhiều hệ thống, phải có trạng thái riêng cho từng bước và alert khi quá hạn SLA.

## 7. Spring Security Servlet: điểm thu tín hiệu và ranh giới của hooks

### 7.1. Authentication events

Spring Security có `AuthenticationSuccessEvent` và các lớp `AbstractAuthenticationFailureEvent`, cùng `AuthenticationEventPublisher`. Khi có publisher phù hợp và luồng authentication sử dụng nó, ứng dụng có thể dùng `@EventListener` để nhận event. Tài liệu Spring Security lưu ý `DefaultAuthenticationEventPublisher` ánh xạ một số exception theo kiểu **exact match**, nên custom AuthenticationException/subclass có thể cần cấu hình mapping bổ sung.

Cấu hình bean (snippet đặt trong class `@Configuration` có đủ imports):

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
~~~

Nếu Spring Boot/app đã cung cấp publisher bean, **không tạo bản thứ hai trùng nhau**. Nhớ rằng một event không nhất thiết đủ cho mọi mechanism; cần đo coverage với OAuth2 login, JWT Resource Server, password, MFA và custom filters của ứng dụng.

Một listener minh họa (được biên dịch **trong project có Spring dependencies**, cùng package `example`). Nó đẩy công việc vào **sink nội bộ**, không xuất Authentication object ra event queue:

~~~java
package example;

import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public final class AuthenticationSignalsListener {

    private final AccountRefResolver resolver;
    private final SecuritySignalSink sink;

    public AuthenticationSignalsListener(
            AccountRefResolver resolver,
            SecuritySignalSink sink) {
        this.resolver = resolver;
        this.sink = sink;
    }

    @EventListener
    public void succeeded(AuthenticationSuccessEvent event) {
        String accountRef = resolver.safeRef(event.getAuthentication());
        sink.enqueue("AUTH_SUCCESS", accountRef);
    }

    @EventListener
    public void failed(AbstractAuthenticationFailureEvent event) {
        String accountRef = resolver.safeRef(event.getAuthentication());
        sink.enqueue("AUTH_FAILURE", accountRef);
    }
}

// App-defined interfaces: implement and register corresponding beans.
// Resolver returns a safe, stable internal ref only after account mapping;
// if not known, it returns an opaque UNKNOWN reference, not raw username.
interface AccountRefResolver {
    String safeRef(Authentication authentication);
}
interface SecuritySignalSink {
    void enqueue(String eventType, String accountReference);
}
~~~

**Giới hạn:** đây là snippet wiring; cần triển khai hai interface làm bean Spring, bảo vệ lỗi khi sink chậm, rate limits và queue latency. Listener không nên đồng bộ gọi API phân tích rủi ro chậm làm nghẽn login; nếu dùng async event handling thì cần propagation, retry/outbox và lựa chọn fail-open/fail-closed có chủ đích. Resolver không được log/serialize `Authentication` vì credentials/details có thể nhạy cảm; với user không tồn tại thì không gán sai local user ID.

### 7.2. Events không tự chứa network context tin cậy

`AuthenticationSuccessEvent` thường chứa Authentication, nhưng nó **không bảo đảm** có client IP, device attestation hoặc tenant canonical đã được xác minh. Lấy network context ở request boundary/gateway đáng tin, kiểm tra `Forwarded`/`X-Forwarded-For` theo danh sách trusted proxies; không tin mọi client tự gửi header này. Gắn request ID, timezone UTC và session ref có kiểm soát. Tránh dùng `request.getRemoteAddr()` không phân biệt reverse proxy.

Nếu muốn áp policy **trước khi cấp session**, phải hook tại đúng authentication pipeline hoặc access decision, không đơn thuần nghe event rồi bất đồng bộ "thu hồi sau" vì có thể đã có một khoảng truy cập. Với yêu cầu không bypass, kết hợp pre-issue decision, step-up, authorization guard và post-issue monitoring.

### 7.3. SessionManagement, SessionRegistry và Spring Session

- `SessionCreationPolicy.STATELESS` nghĩa security chain **không duy trì HTTP session**, nên revoke bằng `HttpSession.invalidate()` không có ý nghĩa cho Bearer JWT riêng.
- `SecurityContextRepository` chịu trách nhiệm lưu/đọc Authentication cho request session; với custom auth filter ở Spring Security 6.x cần hiểu `requireExplicitSave` và điểm lưu context.
- `SessionRegistry`/concurrent sessions giúp theo dõi các session đã đăng ký, nhưng không thay thế cơ chế shared revocation toàn hệ thống.
- Với Spring Session + Redis/JDBC và indexed sessions, có thể xây chức năng quản lý session từ xa theo API/cấu hình đúng phiên bản; **không đoán có thể xóa mọi session nếu hệ thống không lưu index theo user**.
- `LogoutHandler` chỉ chạy trong flow logout được cấu hình; password change/revocation ngoài băng cần gọi domain service riêng, không giả định nó tự trigger ở mọi token verifier.

### 7.4. Audit và event trace có phân quyền

Log tối thiểu gồm `incident_id`, `request_id`, `account_ref`, `event_type`, `outcome`, `action_target`, `actor_ref`, timestamp UTC, policy version và external revoke status. Các logs phải immutable/tamper-evident theo nhu cầu, có retention/least privilege, không lưu raw tokens/PII không cần thiết.

**Không truyền token/password vào error message** của `AuthenticationException` hoặc business exception sẽ được serialise/traced. Trong HTTP response, chỉ trả mã công khai chung (ví dụ `REAUTH_REQUIRED`, `AUTH_FAILED`) và correlation ID, không phơi dấu hiệu từ hệ phát hiện; bảo vệ account existence trước anonymous user.

## 8. Ví dụ Java 17 chạy độc lập: đánh giá tín hiệu và thu hồi bằng phiên bản

Đây là **mô hình giáo dục** kiểm thử hai quy tắc: tín hiệu rủi ro cần dẫn đến quyết định phù hợp; khi thu hồi toàn tài khoản, session/refresh grant cũ không còn được chấp nhận. Chương trình **không có Spring, DB hay HTTP**, không tạo JWT thật và không revoke IdP. `securityVersion` được kiểm tra trong bộ nhớ một JVM; production cần shared store, atomic transaction, bảo vệ race/replication lag.

Tạo file `LoginIncidentDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class LoginIncidentDemo {

    enum Decision { ALLOW, STEP_UP, RESTRICT }

    record Signals(boolean newDevice,
                   boolean unfamiliarLocation,
                   boolean highRiskNetwork,
                   int recentFailures) {
        Signals {
            if (recentFailures < 0) {
                throw new IllegalArgumentException("negative failures");
            }
        }
    }

    static Decision assess(Signals input) {
        Objects.requireNonNull(input);
        // Các ngưỡng chỉ là dữ liệu giả của bài học.
        if (input.highRiskNetwork() && input.recentFailures() >= 5) {
            return Decision.RESTRICT;
        }
        if (input.newDevice()
                || input.unfamiliarLocation()
                || input.recentFailures() >= 3) {
            return Decision.STEP_UP;
        }
        return Decision.ALLOW;
    }

    record Grant(String userId, long version) {}

    private final Map<String, Long> accountVersion = new HashMap<>();
    private final Map<String, Grant> sessions = new HashMap<>();
    private final Map<String, Grant> refreshGrants = new HashMap<>();

    private long currentVersion(String userId) {
        return accountVersion.getOrDefault(userId, 0L);
    }

    synchronized void issueSession(String userId, String sessionRef) {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(sessionRef);
        sessions.put(sessionRef, new Grant(userId, currentVersion(userId)));
    }

    synchronized void issueRefresh(String userId, String tokenRef) {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(tokenRef);
        refreshGrants.put(
            tokenRef, new Grant(userId, currentVersion(userId)));
    }

    synchronized boolean sessionValid(String sessionRef) {
        Grant grant = sessions.get(sessionRef);
        return grant != null
            && grant.version() == currentVersion(grant.userId());
    }

    synchronized boolean refreshValid(String tokenRef) {
        Grant grant = refreshGrants.get(tokenRef);
        return grant != null
            && grant.version() == currentVersion(grant.userId());
    }

    synchronized long revokeAll(String userId) {
        Objects.requireNonNull(userId);
        long nextVersion = currentVersion(userId) + 1;
        accountVersion.put(userId, nextVersion);
        sessions.entrySet().removeIf(
            e -> userId.equals(e.getValue().userId()));
        refreshGrants.entrySet().removeIf(
            e -> userId.equals(e.getValue().userId()));
        return nextVersion;
    }

    public static void main(String[] args) {
        System.out.println("low=" + assess(
            new Signals(false, false, false, 0)));
        System.out.println("medium=" + assess(
            new Signals(true, false, false, 1)));
        System.out.println("high=" + assess(
            new Signals(true, true, true, 7)));

        LoginIncidentDemo store = new LoginIncidentDemo();
        store.issueSession("alice", "session-old");
        store.issueRefresh("alice", "refresh-old");

        System.out.println("sessionBefore="
            + store.sessionValid("session-old"));
        System.out.println("refreshBefore="
            + store.refreshValid("refresh-old"));

        long version = store.revokeAll("alice");

        System.out.println("newVersion=" + version);
        System.out.println("sessionAfter="
            + store.sessionValid("session-old"));
        System.out.println("refreshAfter="
            + store.refreshValid("refresh-old"));

        store.issueSession("alice", "session-new");
        System.out.println("newSession="
            + store.sessionValid("session-new"));
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac LoginIncidentDemo.java
java LoginIncidentDemo
~~~

**Stdout chính xác:**

~~~text
low=ALLOW
medium=STEP_UP
high=RESTRICT
sessionBefore=true
refreshBefore=true
newVersion=1
sessionAfter=false
refreshAfter=false
newSession=true
~~~

### Cách đọc kết quả

- `low/medium/high` minh họa quyết định khác nhau khi số lần thất bại, thiết bị mới và rủi ro mạng thay đổi. Ngưỡng 3/5 chỉ để dễ hiểu, **không phải tiêu chuẩn OWASP/NIST**.
- `sessionBefore=true` và `refreshBefore=true` là grant đang active trong mô hình; sau `revokeAll`, bản ghi cũ bị xóa và phiên bản tăng.
- `sessionAfter=false`, `refreshAfter=false` cho thấy verifier **có thực hiện check state** thì có thể từ chối grant cũ.
- `newSession=true` nghĩa ứng dụng mô phỏng **đã cấp mới** sau revoke; một hệ thống thật **không được tự cấp lại session chỉ vì gọi method issue**, mà phải xác thực lại chủ tài khoản và vượt recovery/step-up policy. Đây chỉ là state simulator.
- Không có logic JWT cryptographic ở đây: JWT tự chứa đã phát ra từ issuer ngoài **không tự mất hiệu lực** vì một map `accountVersion` thay đổi.
- `synchronized` chỉ dùng cho một JVM; production cần transaction/locking, token family semantics và idempotent incident handling trên shared store.

### JUnit 5 cho domain behavior

Nếu dự án dùng JUnit Jupiter, đặt file `LoginIncidentDemoTest.java` cùng package với class demo:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LoginIncidentDemoTest {

    @Test
    void noisyUnknownContextTriggersStepUpNotAutomaticLock() {
        assertEquals(LoginIncidentDemo.Decision.STEP_UP,
            LoginIncidentDemo.assess(
                new LoginIncidentDemo.Signals(
                    true, false, false, 1)));
    }

    @Test
    void highRiskNetworkPlusManyFailuresIsRestricted() {
        assertEquals(LoginIncidentDemo.Decision.RESTRICT,
            LoginIncidentDemo.assess(
                new LoginIncidentDemo.Signals(
                    true, true, true, 7)));
    }

    @Test
    void globalRevocationInvalidatesExistingSessionAndRefresh() {
        LoginIncidentDemo store = new LoginIncidentDemo();
        store.issueSession("alice", "s1");
        store.issueRefresh("alice", "r1");
        assertTrue(store.sessionValid("s1"));
        assertTrue(store.refreshValid("r1"));

        assertEquals(1L, store.revokeAll("alice"));
        assertFalse(store.sessionValid("s1"));
        assertFalse(store.refreshValid("r1"));
    }

    @Test
    void otherUsersGrantsRemainValid() {
        LoginIncidentDemo store = new LoginIncidentDemo();
        store.issueSession("alice", "s-a");
        store.issueSession("bob", "s-b");

        store.revokeAll("alice");
        assertFalse(store.sessionValid("s-a"));
        assertTrue(store.sessionValid("s-b"));
    }
}
~~~

Mẫu test này kiểm tra domain ở memory; cần thêm test HTTP, Spring session store, OAuth token endpoint, multi-node, concurrency và IdP coordination. Chưa thể suy ra hệ thống thực sẽ revoke được remote sessions chỉ vì các unit tests này pass.

## 9. Ma trận kiểm thử tích hợp

| Scenario | Kết quả cần chứng minh |
| --- | --- |
| Login password sai nhiều lần | Phát event đã redact, rate limit phù hợp, không lộ account existence |
| Nhiều user bị thử từ một IP | Aggregate abuse signal, không tự khóa toàn bộ user hợp lệ |
| Login từ device mới | Policy step-up/notify chính xác; có xử lý VPN/private browsing |
| MFA fatigue | Phát hiện nhiều challenge/push, có giới hạn và kênh xác nhận an toàn |
| Refresh token rotation reuse | Token family bị quarantine/revoke theo policy; audit đúng ID |
| Thao tác thêm TOTP/passkey sau login lạ | Bắt fresh existing-factor re-auth; không bypass bằng session cũ |
| Revoke local session trên node A | Node B không tiếp tục accept session đó qua shared store |
| Revoke tất cả user sessions | Mọi old session refs bị từ chối, không ảnh hưởng account khác |
| Revoke refresh grant | AS không phát refresh access token mới; test race với refresh đồng thời |
| JWT access token trước revoke | Bị từ chối khi resource server có denylist/security-version enforcement; hoặc xác nhận documented residual TTL |
| Opaque token revoked | Introspection trả `active=false`; cache không cho phép cửa sổ vượt budget |
| IdP logout | RP session **không giả định** tự bị xóa; verify đúng tích hợp nếu có back-channel |
| Security store outage | Endpoint high-risk fail closed; alert rõ và retry không gây loop |
| Race revoke/issue token | Không phát token dùng được ngoài policy sau containment commit |
| Outbox event gửi lặp | Xử lý idempotent; không làm invalid session đã được recovery đúng |
| Một external revoke thất bại | Incident ở trạng thái PARTIAL/PENDING, alert và retry |
| Login anomaly false positive | User có đường step-up/recovery an toàn, không bị khóa không thể phục hồi |
| Anonymous API query account | Public response chung; reason nội bộ không phơi |
| Notification sau thay recovery contact | Kênh contact **đã xác minh trước thay đổi** vẫn nhận cảnh báo |
| Log/trace audit | Không có raw password/session/Bearer/OTP; có incident/request IDs |
| Incident đã đóng | E2E chứng minh token/session cũ bị chặn, chỉ phiên mới được re-auth |

**Kiểm thử chính sách phải chạy ở ranh giới thật.** `MockMvc .with(user(...))` hoặc `jwt()` của Spring Security Test đưa Authentication giả vào request, **không chứng minh** session revocation, JWT signature/expiry/denylist hoặc OAuth2 introspection. Khi test các cơ chế này, dùng **raw cookie/token thực của môi trường test**, filter chain được cấu hình với session store/decoder/introspector thật và kỳ vọng status/header phù hợp. Không dùng production credential trong CI.

### Kịch bản kiểm thử xấu cần có

- Concurrent logout all + refresh trong hai threads/nodes; dùng barrier/test DB real transaction để tái hiện race.
- Attacker cố ép lockout bằng nhiều failed logins giả; kiểm tra hệ thống hạn chế abuse mà không tự làm DoS user.
- Session từ site/app khác có cùng username nhưng khác tenant không bị thu hồi nhầm.
- IdP đã revoke grant nhưng Resource Server giữ JWT offline đến `exp`: metric đo cửa sổ còn dùng được.
- Redis/event bus mất kết nối: check chính sách cache/hạn mức retry, không tự mở quyền high-risk.
- Recovery account sau incident: old token family không thể được hồi sinh qua stale queue message.
- Một incident bị trigger lặp: idempotency không tăng version sau khi session mới được cấp an toàn.
- Token introspection cache: `active=false` được áp đúng thời gian chính sách, không giữ active mãi.
- Notification email tới kênh cũ không chứa reset token công khai hay log sensitive data.

## 10. Runbook vận hành ngắn gọn

### Khi alert mở

1. Nhận `incident_id` và confidence; kiểm tra nguồn dữ liệu đáng tin, correlation, blast radius.
2. Phân biệt user activity hợp lệ với dấu hiệu takeover; dùng nhiều tín hiệu nếu chưa có bằng chứng mạnh.
3. Ưu tiên chặn high-risk actions và token refresh khi cần; quyết định full-account revoke theo policy.
4. Ghi transaction quyết định và outbox; thi hành session/token revocation trên mọi service liên quan.
5. Gửi thông báo tới kênh tin cậy, không cho chủ tài khoản bị nghi chiếm dùng lại phiên cũ để tự bỏ restriction.
6. Mở recovery bằng bằng chứng đủ mạnh, xác minh/revoke mọi factor hoặc linked account lạ.
7. Verify bằng các phiên/tokens cũ trong môi trường test, không chỉ nhìn 200 ở API revoke; đánh dấu `COMPLETED` hoặc `PARTIAL_REVOKE`.
8. Đóng incident khi có bằng chứng containment và hậu kiểm quyền truy cập; ghi root cause, thời gian revocation lag và bài học.

### Chỉ số nên theo dõi

- Tỷ lệ bất thường trên login và số incident được xác nhận (precision).
- Tỷ lệ người hợp pháp bị step-up/khóa nhầm, tỷ lệ appeal/recovery thành công.
- `time_to_detect`, `time_to_contain`, `revocation_lag_p95/p99` tính theo từng loại credential/service.
- Số token refresh reuse, OAuth grants chưa revoke, stale sessions còn active.
- Số incident ở trạng thái `PENDING_EXTERNAL_REVOKE`, số lần retry và lỗi IdP/revocation store.
- Health của security event stream, phần trăm login flows phát đủ event, outbox backlog và event loss.

Không đưa email/user ID thô hoặc JWT `jti` ngẫu nhiên với cardinality rất cao làm nhãn Prometheus. Dùng aggregated labels và protected investigation logs. Bảo vệ provenance và chống tampering của audit events.

## 11. Lỗi phổ biến

1. **Chỉ nhìn login failed**, bỏ qua MFA fatigue, refresh reuse, phiên bị chiếm sau login và thay credential.
2. **Tự khóa account vì IP/geo lạ** mà không tính VPN, mobile network và false positives; tạo DoS.
3. **Cho rằng event listener áp dụng mọi auth mechanism**: một số flow dùng custom filters/AS riêng, cần instrumentation riêng.
4. **Serialize Authentication object ra event bus**: có thể chứa credential/details nhạy cảm.
5. **Tin mọi `X-Forwarded-For`**: attacker giả IP/geo; chỉ trust proxy đã biết.
6. **Chỉ logout current request** rồi báo "đã đăng xuất mọi thiết bị".
7. **Đổi password/revoke refresh** rồi báo JWT access token đã hết hiệu lực dù Resource Server verify offline.
8. **Xóa refresh token record nhưng không xử lý family/reuse**: attacker giữ token khác có thể tiếp tục đổi.
9. **Chỉ tăng securityVersion trong DB** nhưng resource servers không kiểm tra phiên bản.
10. **Cache revocation quá lâu**: token vẫn dùng sau containment; cần budget/alerts.
11. **Không kiểm soát race phát token và revoke**: có cửa sổ cấp credential mới.
12. **Giả định logout IdP cũng logout RP**: hai loại session khác nhau.
13. **Dùng account ID từ request body để revoke user khác**: cần server-side trusted principal, role/approval và audit.
14. **Không có recovery**: người dùng hợp pháp bị khóa vĩnh viễn hoặc support phải bỏ qua MFA.
15. **Tự động gửi thông báo tới contact mới**: attacker đã đổi contact có thể tự nhận, chủ account không biết.
16. **Không có outbox/retry/idempotency**: revoke xa thất bại im lặng, hoặc stale retry khóa lại account vừa recovery.
17. **Để incident response chỉ ghi “revoke success”** mà không thử credential cũ ở mỗi verifier.
18. **Không phân biệt evidence và suspicion**: analytics trở thành kết luận tội lỗi mà không có human review.
19. **Lộ public reason** “account exists/compromised” ở login anonymous: user enumeration và privacy leak.
20. **Không có kịch bản security service outage**: network lỗi làm policy tự fail-open tại endpoint nguy hiểm.

## 12. Checklist triển khai

- [ ] Có inventory của authentication flows, session stores, OAuth grants, refresh/access tokens, IdP và các verifier thực tế.
- [ ] Có event schema đã redact, UTC timestamps, request/incident IDs và privacy/retention/access control.
- [ ] Tín hiệu risk có false-positive analysis, calibration, threat model và cách appeal/restore.
- [ ] Có step-up cho hành vi nhạy cảm, không dùng session cũ để thay factor/recovery khi đang bị nghi chiếm.
- [ ] Revoke đúng scope: local session, persistent remember-me, refresh family, JWT/opaque token, IdP session khi hỗ trợ.
- [ ] Resource servers áp đặt revocation policy nhất quán; residual lifetime/lag được đo.
- [ ] DB transaction + outbox + retry idempotent, explicit PARTIAL_EXTERNAL_REVOKE status.
- [ ] Lệnh revoke có authorization, phân quyền/approval và audit; không nhận account ID do browser tự khai.
- [ ] Không lộ secrets trong logs, events, metrics, notifications và responses.
- [ ] Test race revoke/refresh, multi-node, cache lag, security store outage, false-positive recovery.
- [ ] Có runbook cho on-call/SOC, đầu mối hỗ trợ, thông báo an toàn và kiểm chứng hậu xử lý.

**Tóm tắt:** phát hiện đăng nhập bất thường là **đánh giá rủi ro có thể sai**, còn thu hồi truy cập là **thay đổi trạng thái đáng tin được mọi verifier thực thi**. Spring Security cung cấp hooks, security context và cơ chế quản lý session/token ở từng tầng; ứng dụng phải tự kết nối tín hiệu, policy, transaction, session/token revocation, IdP coordination và recovery thành một quy trình có thể kiểm chứng.

## 13. Tài liệu tham khảo chính thức

- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Logout support: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Opaque tokens and introspection: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- NIST SP 800-63B-4 (2025) — Session monitoring, reauthentication: https://pages.nist.gov/800-63-4/sp800-63b/session/
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009.html
- RFC 7662 — OAuth2 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
