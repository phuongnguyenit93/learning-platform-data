# Mô hình đe dọa: giả mạo IdP, đánh cắp assertion và chiếm phiên

> **Module:** Spring Security – Federation. **Nhóm:** Ranh giới tin cậy. Bài này phân tích mô hình đe dọa cho ứng dụng Java/Spring Security làm **SAML 2.0 Service Provider (SP)** khi dùng đăng nhập SSO qua Identity Provider (IdP). Những khác biệt với OpenID Connect (OIDC) được chỉ rõ ở phần tương ứng; không được đánh đồng SAML assertion với OIDC ID token hay OAuth access token.

## 1. Mục tiêu học tập và nguyên tắc cốt lõi

Sau bài này, người học cần có thể:

1. Vẽ đường đi của SAML Response, xác định bên kiểm soát từng điểm và dữ liệu nào cần được xác minh trước khi tin.
2. Phân biệt **IdP spoofing / trust substitution** (giả mạo nguồn đáng tin), **assertion theft / replay** (đánh cắp bằng chứng đăng nhập đã ký) và **session hijacking / fixation** (chiếm phiên ứng dụng).
3. Đặt từng biện pháp phòng vệ đúng vị trí: cấu hình trust/certificate, xác thực SAML Response và assertion, ràng buộc một phiên đăng nhập, chống replay, bảo vệ phiên HTTP và authorization.
4. Áp dụng các nguyên tắc vào `saml2Login()`, `RelyingPartyRegistration` và cấu hình phiên của Spring Security mà không bỏ các validation mặc định.
5. Thiết kế thử nghiệm âm tính, nhật ký giám sát và quy trình xử lý khi có dấu hiệu sự cố.

**Quy tắc nền tảng:** Một assertion có chữ ký hợp lệ chỉ chứng minh chữ ký đúng với **khóa dùng để kiểm tra**. Điều SP thực sự cần biết là: *đó có phải khóa của IdP mà SP chủ động tin cậy, assertion có được phát cho chính SP, trong đúng login transaction, tại đúng thời điểm, chưa bị tái sử dụng, rồi gắn với một phiên ứng dụng được bảo vệ hay không?*

## 2. Mô hình hệ thống, tài sản và ranh giới tin cậy

### 2.1. Luồng SAML Web SSO tối giản

Trong luồng **SP-initiated** dùng HTTP Redirect/POST binding:

```text
┌───────────────┐                     ┌──────────────────────┐
│ Trình duyệt   │                     │ Ứng dụng Spring (SP) │
│ người dùng    │                     │ ACS + HttpSession    │
└───────┬───────┘                     └──────────┬───────────┘
        │ GET /dashboard                         │
        ├────────────────────────────────────────>│
        │   redirect tới IdP cùng AuthnRequest   │
        │<────────────────────────────────────────┤
        │                                        │
        │         ┌──────────────────────┐       │
        └────────>│ IdP / trang đăng nhập │       │
                  │ ký Response/Assertion│       │
        ┌─────────┴──────────────────────┘       │
        │ HTML form POST SAMLResponse            │
        └────────────────────────────────────────>│ ACS
                                                 │
                   [1] Trust IdP + ký XML       │
                   [2] Ràng buộc người nhận     │
                   [3] Thời gian + chống replay │
                   [4] Tạo SecurityContext      │
                   [5] Tạo/đổi session ID       │
        │<────────────────────────────────────────┤
        │ Set-Cookie JSESSIONID + redirect       │
        │                                        │
        ├──── Cookie JSESSIONID; GET /dashboard ->│
        │                          [6] Authorization
```

**ACS** (Assertion Consumer Service) là endpoint của SP nhận `SAMLResponse` từ browser. Trình duyệt là **kênh vận chuyển không đáng tin**: người dùng/attacker có thể tự tạo HTTP request. SP không được vì “POST đến ACS” mà tin payload. IdP được tin cậy theo cấu hình chủ động của SP; không phải theo bất kỳ tên miền/certificate nào người gửi tự khai.

### 2.2. Tài sản cần bảo vệ

| Tài sản | Tại sao quan trọng | Bên thường quản lý |
| --- | --- | --- |
| Trust configuration: IdP entity ID, SSO endpoints, public signing keys, metadata | Quyết định ai có quyền khẳng định danh tính user | SP administrator / cấu hình triển khai |
| Khóa ký SAML riêng của IdP | Nếu bị chiếm, attacker có thể tạo assertion được ký hợp lệ | IdP/HSM/nhà vận hành |
| `AuthnRequest` và state tương quan | Ràng buộc response với lần login mà SP thực sự khởi tạo | SP, kho session/request |
| `SAMLResponse` / `Assertion` / `NameID` / attributes | Bằng chứng xác thực và claims mang qua browser | IdP phát; SP tiêu thụ |
| `entityID`, ACS URL, `Audience`, `Recipient`, `Destination` | Ngăn sử dụng nhầm cho SP/service khác | Cấu hình SP và dữ liệu ký |
| ID assertion/response và replay cache | Ngăn chấp nhận lại cùng một bằng chứng | SP / cache dùng chung |
| Principal, `SecurityContext`, roles | Quyết định user nào được gắn với request | Spring Security / application |
| Session ID, session store, cookie | Credential phiên sau SSO, có vòng đời riêng | SP và trình duyệt |
| Audit events, secret/config distribution | Phát hiện giả mạo, phục hồi sau sự cố | Đội vận hành |

### 2.3. Các ranh giới phải bảo vệ

- **Biên A – Cấu hình tin cậy:** IdP metadata/khóa ký từ bên ngoài đi vào danh sách IdP mà SP chấp nhận. Không để request tùy ý chọn nguồn tin cậy hoặc thay public key.
- **Biên B – Browser → ACS:** XML/SAMLResponse do browser gửi vào SP. Phải xác thực toàn bộ ý nghĩa bảo mật của thông điệp trước khi tạo `Authentication`.
- **Biên C – Claims → account/quyền:** `NameID`/email/groups đi vào mô hình user nội bộ. Phải ánh xạ đúng issuer/tenant và kiểm tra authorization riêng.
- **Biên D – Authentication → HttpSession:** Login thành công biến bằng chứng SSO ngắn hạn thành phiên ứng dụng có cookie. Phải đổi session ID sau login, bảo vệ cookie và quản lý timeout/logout.
- **Biên E – Session → dữ liệu:** Một phiên đã xác thực chưa có nghĩa được đọc/sửa mọi dữ liệu. Bắt buộc kiểm tra quyền theo endpoint, tenant, object và hành động.

### 2.4. Khả năng của đối thủ và giới hạn giả định

Mô hình hóa ít nhất các đối thủ sau:

- Người ngoài có thể gửi request tùy ý đến ACS, dựng trang giả, quan sát URL/redirect của mình và thử dùng lại payload có được.
- Người dùng/thiết bị bị xâm nhập có thể làm lộ assertion từ browser, proxy, log, tiện ích mở rộng hoặc công cụ giám sát.
- Người có quyền chỉnh cấu hình/metadata hoặc kẻ tấn công chuỗi cung ứng có thể chèn IdP/key không mong muốn.
- Một tenant bị kiểm soát có thể cố đưa identity của tenant A vào tenant B nếu SP hỗ trợ nhiều IdP.
- XSS, CSRF, cookie theft, session fixation hay reverse proxy cấu hình sai có thể làm phiên ứng dụng bị chiếm, **dù SAML validation hoàn toàn đúng**.

Giả định **IdP signing private key chưa bị lộ** khi phân tích giả mạo thông thường. Nếu khóa ký thật đã bị đánh cắp, chỉ xác minh chữ ký sẽ không phân biệt được assertion do attacker ký; lúc đó cần incident response, thu hồi/đổi khóa và biện pháp giảm thiểu ngoài việc validate bình thường.

## 3. Bản đồ mối đe dọa

| Đe dọa | Năng lực/điểm vào của attacker | Hậu quả | Biện pháp chặn trọng tâm |
| --- | --- | --- | --- |
| Giả mạo IdP | Chèn metadata/khóa ký, đổi `Issuer`, đăng ký IdP giả | SP tin người không có quyền phát hành identity | Allowlist IdP/entity ID; public signing keys xác thực out-of-band; kiểm tra signature trên dữ liệu đúng |
| Đổi ngữ cảnh multi-IdP | Nhầm registration/tenant, chọn key theo payload không kiểm soát | User từ IdP A được nhận như thuộc IdP B | Ràng buộc registration với transaction và tenant; kiểm tra issuer/key/audience |
| XML signature wrapping | Tạo XML nhiều assertion, lợi dụng khác biệt giữa phần đã ký và phần code đọc | Identity đã xác minh khác identity được sử dụng | Parser/validator đáng tin; signature-reference binding; chỉ dùng assertion đã được verify |
| Đánh cắp assertion | Lấy `SAMLResponse` từ browser/log/proxy/telemetry | Dùng lại bằng chứng xác thực trước khi hết hạn | HTTPS, giảm lộ credential, `Recipient`/`Audience`/`InResponseTo`, hạn ngắn, cache chống replay |
| SAML replay | POST lại assertion còn thời hạn | Login mạo danh hoặc chiếm phiên nếu SP xử lý lại | Cache ID được tiêu thụ theo cách atomic; chống replay kể cả trường hợp `OneTimeUse` |
| Session fixation | Buộc nạn nhân dùng session ID attacker đã biết trước login | Attacker tái dùng session sau khi nạn nhân xác thực | Đổi session ID ở thời điểm authentication thành công |
| Session hijacking | Đánh cắp cookie hoặc thực hiện hành động qua XSS/CSRF | Điều khiển tài khoản sau login, không cần assertion | `Secure`, `HttpOnly`, `SameSite` phù hợp, CSRF, chống XSS, timeout, logout/revoke |
| Confused deputy/leo quyền | Mapping groups/email sai, thiếu object authorization | User đã login làm vượt quyền | Phân biệt authentication/authorization, mapping issuer+subject, RBAC/ABAC/object checks |

Không gán mức độ rủi ro tuyệt đối cho mọi hệ thống. Ưu tiên theo khả năng khai thác và hậu quả cụ thể: đăng nhập quản trị, thông tin khách hàng, multi-tenant, mức phơi lộ ACS, mức kiểm soát metadata và phương pháp lưu session.

## 4. Đe dọa 1 – Giả mạo IdP (IdP spoofing / trust substitution)

### 4.1. “Giả mạo IdP” có nhiều lớp

**Lớp 1: phishing IdP** – attacker dựng trang đăng nhập trông giống IdP, dụ user nhập mật khẩu. SP có thể vẫn xác minh đúng IdP khi nhận assertion, nhưng thông tin đăng nhập phía IdP đã bị lộ. Cần bảo vệ tên miền, MFA chống phishing, phát hiện trang giả và user awareness; kiểm tra chữ ký SAML ở SP không chặn riêng hoạt động đánh cắp mật khẩu này.

**Lớp 2: giả mạo SAML issuer/signing key** – attacker tự tạo assertion có `Issuer=https://trusted-idp...`, đính kèm `ds:KeyInfo`/chứng chỉ của mình và ký bằng khóa riêng của mình. Nếu SP lấy **khóa xác minh từ payload không đáng tin** hoặc chấp nhận issuer không được pin theo registration, nó có thể xác thực sai. Chữ ký toán học đúng với khóa attacker vẫn phải **bị từ chối**.

**Lớp 3: thay nguồn metadata** – một URL metadata, file cấu hình, môi trường CI/CD hay quyền quản trị bị kiểm soát; attacker thêm khóa ký của mình vào tập khóa tin cậy của SP. Đây là vấn đề **bootstrap trust và vận hành**. Nếu cấu hình trust của SP bị sửa hợp lệ theo cơ chế quản trị, validation thông thường không tự phát hiện ý đồ xấu.

**Lớp 4: nhầm IdP/tenant** – SP có IdP cho tenant A và tenant B. Attacker cố dùng assertion từ IdP A nhưng khiến SP ánh xạ account/registration của tenant B (issuer mix-up, sai bộ khóa hoặc sai account mapping). Đúng IdP nhưng **sai tenant** cũng là một ranh giới tin cậy bị vượt.

### 4.2. Chuỗi tấn công minh họa

```text
Attacker -> ACS: SAMLResponse chứa NameID=admin
                Issuer="https://idp.trusted.example"
                ds:KeyInfo = khóa do attacker kiểm soát
                Signature = chữ ký tạo bằng private key attacker

SP yếu: "XML signature valid" (với chính khóa từ thông điệp)
        -> dùng NameID=admin -> tạo SecurityContext cho admin

SP đúng: issuer chỉ là claim; khóa kiểm tra lấy từ
         IdP registration đã tin và đối chiếu độc lập
         -> signature không khớp -> REJECT
```

Đây là mô hình về **sai lầm lựa chọn khóa**; không phải chỉ dẫn khai thác. SP không được coi `Issuer`, `KeyInfo` hay redirect parameter là thẩm quyền để thêm mới IdP.

### 4.3. Bảo vệ biên A và B

1. **Tin cậy từ cấu hình độc lập:** duy trì `RelyingPartyRegistration` cho IdP được duyệt, kiểm tra `entityID` và khóa ký tương ứng. Chỉ nhận metadata qua kênh được xác thực; xác minh chủ sở hữu/độ tin cậy của metadata ngoài giao dịch login. SAML signing certificate thường là trust anchor ứng dụng, không mặc nhiên được bảo vệ chỉ nhờ chuỗi CA.
2. **Không trust-on-first-use từ request đăng nhập:** không tự động nhận issuer mới, metadata URL trong query, certificate trong `KeyInfo` hay tùy chọn thuật toán do client đề xuất. Khi metadata có nhiều signing keys để rollover, mọi khóa phải đến từ **nguồn đã tin** và theo policy thay khóa.
3. **Kiểm tra chứng thực đúng dữ liệu:** xác minh chữ ký XML của Response/assertion bằng khóa được liên kết với đúng IdP; không dùng XML element khác với phần thực sự được ký (**XML Signature Wrapping**). Chặn XML entity expansion/XXE, schema fetching ngoài ý muốn, cấu trúc mơ hồ; dùng OpenSAML do Spring Security tích hợp và cập nhật bản vá.
4. **Kiểm tra issuer/recipient theo registration:** `Issuer` của Response/assertion, `Destination` của Response, `AudienceRestriction` của assertion, `SubjectConfirmationData.Recipient` phải khớp giá trị được cấu hình trong bối cảnh. Không chỉ so miền con hoặc bỏ qua scheme/host/path.
5. **Ràng buộc tenant → IdP → principal:** user key nên phân biệt issuer/tenant cùng subject ổn định; không liên kết hai IdP bằng email hiển thị một cách tự động. Groups/roles trong assertion chỉ trở thành quyền khi đi qua mapping cho phép của ứng dụng.
6. **Quản trị thay đổi trust:** hạn chế quyền sửa metadata/keys; theo dõi audit, phê duyệt key rollover, kiểm tra danh sách khóa tại triển khai, cảnh báo IdP lạ hoặc signing key thay đột ngột.
7. **Nếu IdP thật bị chiếm khóa ký:** khóa có thể tạo assertion được chấp nhận; phải nhanh chóng đổi khóa, cập nhật trust của SP, điều tra phiên đã tạo, vô hiệu hóa phiên bị ảnh hưởng và rà log. Chỉ dựa vào `NotOnOrAfter` không đủ.

**Lưu ý:** Metadata có certificate hợp lệ là dữ liệu cần dùng để xác minh; còn *quyết định tin metadata đó của ai* là bài toán trust độc lập.

## 5. Đe dọa 2 – Đánh cắp assertion và replay

### 5.1. Vì sao một assertion hợp lệ vẫn nguy hiểm nếu bị lộ?

SAML Web Browser SSO thường dùng **bearer subject confirmation**. Khi attacker cầm được SAML Response/assertion còn được chấp nhận, họ có thể thử POST lại tới ACS. Khác với giả mạo IdP, trong trường hợp này assertion **được IdP thật ký**. Kiểm tra chữ ký và issuer có thể đều PASS.

Các nguồn lộ thông thường:

- Browser extension độc hại, máy trạm bị nhiễm, XSS trong vùng có quyền nhìn form hoặc dữ liệu xác thực.
- Reverse proxy/WAF/APM/tracing ghi nguyên HTTP body ở ACS hoặc ghi `SAMLResponse` Base64 vào log.
- Ghi request vào hệ thống analytics, ticket hỗ trợ, ảnh chụp màn hình, bản dump crash, test fixture thật.
- TLS termination, proxy hoặc back-channel vận chuyển nội bộ yếu; cấu hình log/request capture quá rộng.
- RelayState hoặc URL sau login bị dùng sai để chuyển credential tới đích attacker; không tự đưa assertion vào URL/redirect.

**Không thể chỉ “mã hóa Base64” để bảo vệ:** `SAMLResponse` thường được Base64 encode để vận chuyển, **không phải mã hóa bảo mật**. Encryption ở lớp SAML có thể bảo vệ tính bí mật của nội dung assertion, nhưng không thay thế validation, hạn chế log hay chống replay.

### 5.2. Các điều kiện chống tái sử dụng phải đi cùng nhau

| Kiểm tra | Ý nghĩa | Ví dụ cần từ chối |
| --- | --- | --- |
| XML signature trên đúng đối tượng | Bảo đảm dữ liệu sử dụng nằm trong vùng đã được ký bằng IdP key tin cậy | Assert user A nhưng đọc user B từ một assertion khác |
| `Issuer` | Khẳng định đến từ IdP đã cấu hình cho registration | Issuer của tenant/IdP khác |
| `AudienceRestriction` | Assertion cấp cho đúng SP `entityID` | Assertion cấp cho SP A nhưng gửi SP B |
| `Destination` / ACS | Response phải tới đúng endpoint SP mong đợi | POST sang host/path ACS khác |
| `SubjectConfirmationData.Recipient` | Bằng chứng bearer được gửi đúng nơi nhận | Recipient không khớp ACS của SP |
| `InResponseTo` khi SP-initiated | Response/confirmation phải gắn với `AuthnRequest` chưa tiêu thụ | Không có request tương ứng; request ID sai/đã dùng |
| `NotBefore`, `NotOnOrAfter`, `IssueInstant` | Chỉ chấp nhận trong cửa sổ thời gian chính sách | Chưa hợp lệ, hết hạn hoặc phát hành bất thường |
| Assertion/Response ID + replay store | Không cho cùng bằng chứng thành công nhiều lần | POST lần hai cùng assertion ID |
| `OneTimeUse` nếu có | Bổ sung hạn chế một lần theo protocol | Assertion đã được chấp nhận trước đó |
| Login state và session binding | Không để assertion từ login A lẫn với phiên chờ login B | Request của browser/tenant khác |

Một policy mẫu (giá trị là **minh họa**, không phải cấu hình chuẩn bắt buộc):

```text
issuer = https://idp.company.example/saml
spEntityId = https://portal.example/saml/sp
acs = https://portal.example/login/saml2/sso/corp
maxClockSkew = 60 seconds
requestLifetime = 5 minutes
replayCacheKey = (trustedIssuer, assertionId)
replayCacheTTL >= thời gian assertion còn có thể được chấp nhận
```

- Với SP-initiated, nên giữ ID `AuthnRequest` cùng registration/session trong kho tin cậy, xác minh `InResponseTo` rồi đánh dấu request đã xử lý. Nếu cho phép **IdP-initiated / unsolicited response**, `InResponseTo` có thể vắng mặt; cần policy riêng, bắt buộc ràng buộc issuer/audience/ACS và **chống replay độc lập**, đồng thời hiểu rủi ro login CSRF/session confusion cao hơn.
- Kiểm tra time window có thể cho phép clock skew hợp lý; skew càng rộng càng tăng cửa sổ replay. `NotOnOrAfter` là hạn **loại trừ**.
- Cache chống replay phải có thao tác **đánh dấu lần đầu mang tính atomic** trên tất cả node SP, kết hợp TTL phù hợp. Kiểm tra “chưa thấy ID” rồi ghi trong hai bước riêng dễ có race; cache cục bộ từng replica không ngăn replay sang replica khác.
- Tránh cache vô hạn làm cạn bộ nhớ; lưu ID đã dùng trong khoảng tối thiểu bao phủ cửa sổ assertion có thể được chấp nhận. Khi mất cache, chính sách an toàn phải được quyết định trước (không âm thầm fail-open).
- `OneTimeUse` trong XML **không tự động** đảm bảo một lần; SP phải thực thi hoặc dùng validator/store thực thi nó. Cần kiểm tra behavior chính xác của phiên bản Spring Security và extension đang chạy.
- Không xem IP binding của assertion là biện pháp cốt lõi: NAT, proxy, mạng di động làm IP thay đổi. Nếu có risk signals, dùng làm tín hiệu bổ trợ thay cho việc bỏ validation giao thức.

### 5.3. Các biến thể không nên nhầm

**Response replay:** gửi lại toàn bộ SAML Response cũ. **Assertion replay:** dùng lại assertion hợp lệ trong một thông điệp khác hoặc tại SP khác. **Cross-SP replay:** assertion của SP A được trình cho SP B. **Login CSRF/session confusion:** attacker khiến browser của nạn nhân đăng nhập vào tài khoản của attacker hoặc gắn response sai phiên. Các loại này liên quan nhau nhưng không được giả định một kiểm tra sẽ bao trùm mọi loại.

**XML Signature Wrapping:** attacker khai thác chênh lệch giữa phần XML parser đưa cho kiểm tra chữ ký và phần code ứng dụng chọn để lấy `NameID`/attributes. Ngay cả assertion/Response có một chữ ký “valid” vẫn không hợp lệ nếu đối tượng được dùng để đăng nhập không nằm trong **phần được bảo vệ bởi chữ ký đã xác minh**. Tránh tự parse XML bằng regex, XPath tùy ý hoặc `getElementsByTagName(...)` để rút principal.

### 5.4. Giảm khả năng assertion bị lộ

- HTTPS/HSTS cho **toàn bộ** ứng dụng và chuỗi redirect, đặc biệt ACS; bảo vệ TLS termination đến app theo topology.
- Redact/drop `SAMLResponse`, cookies, `Authorization`, session ID khỏi access log, proxy, WAF, APM, distributed traces, analytics và bug reports. Chỉ log **metadata không nhạy cảm**: correlation ID, issuer ID (đã được xác minh), kết quả validation, mã lỗi, thời gian, fingerprint không dùng làm credential.
- Không đưa assertion, login code hoặc session ID vào query/fragment/RelayState tùy tiện; `RelayState` phục vụ liên kết navigation/state, phải ràng buộc với giao dịch và chặn open redirect.
- Dùng thời hạn ngắn phù hợp UX, hạn chế quyền truy cập bản ghi log, đặt retention và quy trình xử lý incident khi credential xuất hiện trong log.
- Trên máy người dùng, giảm XSS và phần mềm độc hại; một endpoint bảo mật phía server không thể ngăn mọi dạng lộ trong browser đã bị kiểm soát.

## 6. Đe dọa 3 – Chiếm phiên ứng dụng sau khi SSO thành công

### 6.1. Assertion hợp lệ không bảo đảm phiên an toàn về sau

```text
SAML Response hợp lệ
     -> Spring Security Authentication (principal + authorities)
     -> SecurityContext được gắn với request / lưu theo cơ chế ứng dụng
     -> HttpSession + session cookie (ví dụ JSESSIONID)
     -> các request sau chỉ mang cookie; thường không gửi lại assertion
```

Ranh giới thay đổi tại bước tạo phiên: **session ID trở thành credential của SP**. Một assertion hết hạn lúc 10:00 không tự làm `HttpSession` đã tạo hết hạn đúng 10:00. Logout IdP cũng không đương nhiên chấm dứt mọi phiên SP nếu không có cơ chế SLO/synchronization và app không xử lý đúng.

Ba lớp vấn đề:

1. **Session fixation:** attacker biết/đặt trước một session ID, nạn nhân đăng nhập trên session đó, attacker cố tái dùng ID đã biết. Phải **rotate session ID khi login thành công**.
2. **Session theft/hijacking:** attacker lấy cookie sau login (qua log, MITM, browser compromise, XSS khi cookie không `HttpOnly`) hoặc chiếm session store. Phải bảo vệ vận chuyển/lưu trữ/timeout và hủy phiên khi phát hiện bất thường.
3. **Session riding (CSRF) / XSS:** attacker có thể khiến browser nạn nhân thực hiện hành động dưới phiên hợp lệ mà **không cần biết giá trị cookie**. `HttpOnly` chống đọc cookie bằng JS, **không chặn hành động do XSS/CSRF gây ra**. Cần CSRF protection, output encoding, CSP phù hợp và kiểm tra authorization server-side.

### 6.2. Cookie và lifecycle của phiên

| Cơ chế | Tác dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| `Secure` | Cookie chỉ được gửi qua HTTPS | Không tự ngăn XSS hoặc rò từ server logs |
| `HttpOnly` | JavaScript trên page không đọc được cookie qua `document.cookie` | Browser vẫn tự gửi cookie theo request; XSS vẫn có thể thao tác |
| `SameSite` | Hạn chế một số cross-site requests | Không thay CSRF token; `Lax`/`Strict` có thể ảnh hưởng SAML POST từ IdP |
| `Path` / `Domain` tối thiểu | Giảm nơi cookie được gửi | Cookie dùng chung nhiều subdomain tăng bề mặt tấn công |
| Session ID ngẫu nhiên đủ mạnh | Khó dự đoán/đoán brute-force | ID bị lộ vẫn có thể dùng được |
| Rotate ID sau authentication | Giảm session fixation | Không cứu cookie mới đã bị đánh cắp |
| Idle + absolute timeout | Giảm thời gian lạm dụng | Cần enforcement phía server và chính sách phù hợp |
| Invalidate server session khi logout | Thu hồi credential phiên | Chỉ xóa cookie phía browser không vô hiệu bản sao bị đánh cắp |
| Re-auth/MFA cho hành động nhạy cảm | Giới hạn hậu quả khi session bị đánh cắp | Phải ràng buộc lần xác thực gần đây/assurance |

**Điểm khó của SAML POST binding:** Response thường đi từ một origin IdP sang ACS origin SP bằng **cross-site POST**. Cookie session của SP được đặt `SameSite=Lax`/`Strict` có thể không đi kèm POST đó, làm SP không tìm được request/session đã lưu để so `InResponseTo`. Đừng “sửa” bằng cách bỏ kiểm tra request binding hoặc tắt toàn bộ CSRF. Chọn thiết kế state/correlation và chính sách cookie phù hợp, có thể cần `SameSite=None; Secure` cho cookie cần đi qua POST, rồi kiểm tra bằng browser thật và bổ sung CSRF defense cho endpoint khác. Tính tương thích còn phụ thuộc trình duyệt, topology, proxy và cấu hình IdP.

**Cookie prefix `__Host-`**, khi tương thích topology, yêu cầu `Secure`, `Path=/` và không có `Domain`; giảm một số rủi ro giả cookie từ subdomain. Nếu app có SSO qua nhiều domain, đừng mặc định có thể dùng cùng cookie giữa các domain; phiên mỗi SP là riêng.

### 6.3. Đừng bỏ qua authorization và giới hạn quyền

Một assertion có `groups=["admins"]` không được phép tự động cấp quyền `ROLE_ADMIN` cho mọi tenant chỉ vì tên group giống nhau. Hãy quản lý mapping theo issuer/tenant, xác minh nguồn claims, dùng nguyên tắc ít đặc quyền, kiểm tra object ownership ở từng endpoint và audit thay đổi đặc quyền.

**Nguy cơ đáng chú ý:** lộ session của user có đặc quyền cao có thể cho attacker truy cập ứng dụng mà không qua SAML/IdP lần nữa. Chính sách re-authentication cho thao tác nhạy cảm và revocation phiên là tuyến phòng thủ độc lập.

## 7. Chuỗi tấn công và điểm chặn tương ứng

### Kịch bản A – IdP giả nhưng được SP tin sai

1. Attacker kiểm soát metadata/certificate không đáng tin hoặc kích hoạt cấu hình IdP ngoài allowlist.
2. Attacker ký assertion có `NameID` của tài khoản mục tiêu.
3. SP dùng signing key do dữ liệu attack đưa tới thay vì key của registration đáng tin.
4. SP tạo session mạo danh.

**Chặn:** kiểm soát IdP enrollment, ràng buộc `RelyingPartyRegistration`, cấu hình khóa ký theo issuer đáng tin, không chọn trust anchor từ payload, chỉ sử dụng assertion đã được validate. **Dấu hiệu:** registration lạ, metadata/key thay đổi ngoài lịch bảo trì, login từ issuer không được duyệt.

### Kịch bản B – Assertion thật bị lộ trong APM

1. User đăng nhập thành công; proxy ghi nguyên form field `SAMLResponse` vào trace.
2. Attacker có quyền xem trace lấy được payload.
3. Attacker thử POST lại payload còn hạn tới ACS.
4. SP không ràng buộc request, không cache consumed ID hoặc cache theo từng node rời rạc, nên có thể tạo thêm session.

**Chặn:** redact tại mọi điểm log; kiểm tra `Recipient`/`Audience`/`InResponseTo`, TTL ngắn, one-use/replay store atomic và dùng chung. **Dấu hiệu:** assertion ID lặp, một response ID được dùng ở nhiều nguồn, lỗi request correlation bất thường. Chữ ký hợp lệ **không đủ để loại replay**.

### Kịch bản C – SAML đúng nhưng session bị chiếm

1. User đăng nhập với assertion hoàn toàn hợp lệ.
2. Ứng dụng không rotate session ID hoặc làm lộ cookie qua logs/mã JS/proxy.
3. Attacker tái sử dụng cookie ở các request ứng dụng.
4. API dựa vào phiên SP cho phép hành động dưới danh tính nạn nhân.

**Chặn:** rotate session ID, `Secure`/`HttpOnly`/`SameSite` phù hợp, hạn phiên, chống XSS/CSRF, re-auth cho thao tác nhạy cảm, revoke phía server. **Dấu hiệu:** cùng session được dùng từ thiết bị/ngữ cảnh bất thường, hành động quyền cao sau login, thay đổi risk signals. IP/User-Agent chỉ là **tín hiệu rủi ro**, không nên dùng làm ràng buộc cứng duy nhất vì mobile network, NAT và corporate proxy.

### Kịch bản D – Trust đúng nhưng cross-tenant authorization sai

1. IdP A là IdP hợp lệ, phát assertion cho user có email `admin@example.org`.
2. Ứng dụng ánh xạ account theo email toàn cục, bỏ qua issuer và tenant.
3. User được gắn với tài khoản của tenant B có cùng email.
4. App cho phép xem dữ liệu tenant B.

**Chặn:** khóa định danh theo (tenant, issuer, subject ổn định), account linking có xác nhận, authorization theo tenant/object, test trường hợp email trùng. Xác thực kỹ thuật “PASS” không thay cho isolation nghiệp vụ.

## 8. Áp dụng Spring Security 6+ với Servlet

### 8.1. Chọn đúng cơ chế và giữ validator mặc định

Với SP SAML 2.0, cần các thư viện phù hợp (`spring-security-saml2-service-provider` qua Spring Boot starter/tập dependency tương ứng) và cấu hình `RelyingPartyRegistration` liên kết IdP đã được duyệt với certificate/metadata tin cậy, SP entity ID và ACS URL.

Ví dụ cấu hình Java **class đầy đủ** cho một ứng dụng Servlet có Spring Security trên classpath. Nó chỉ là **lớp bảo vệ filter chain**; muốn login thực tế, ứng dụng vẫn phải có cấu hình đăng ký SAML IdP hợp lệ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()));

        return http.build();
    }
}
```

- `saml2Login()` kích hoạt SAML login flow và provider xác minh SAML Response. Trong các bản Spring Security hiện hành, validation dựa trên OpenSAML: signature, issuer, destination, assertion conditions/subject/audience theo cấu hình; **không được tự suy ra mọi chính sách replay/OneTimeUse và lưu trữ ID đã được bật tự động**.
- `changeSessionId()` làm rõ chính sách chống fixation; trên Servlet 3.1+ đây cũng là chiến lược mặc định của Spring Security. Không dùng `sessionFixation().none()`.
- `authorizeHttpRequests` là lớp phân quyền thêm sau authentication. Hãy thay quy tắc tổng quát bằng policy endpoint/role/object cụ thể của ứng dụng.
- Không thêm `csrf(csrf -> csrf.disable())` cho toàn ứng dụng để “SAML POST chạy được”. Các endpoint callback SAML cần cơ chế exemption/state correlation tương thích do framework quản lý; những POST nghiệp vụ khác vẫn phải được bảo vệ CSRF.
- Khi dùng reverse proxy, cấu hình forwarded headers và HTTPS origin **chỉ từ proxy tin cậy** để SP tính đúng public ACS URL; tránh tin `X-Forwarded-*` do client Internet trực tiếp gửi.

### 8.2. Ví dụ cookie/session trong Spring Boot

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Đây là **ví dụ cho một ứng dụng cần session cookie kiểu Lax**. Với **SAML cross-site POST**, `same-site: lax` có thể khiến session cookie của SP không được gửi tới ACS; cần kiểm tra thực tế trước khi dùng và chọn chính sách `None; Secure` hoặc thiết kế correlation riêng phù hợp. `timeout: 30m` là ví dụ idle/session timeout, không phải mức bảo đảm an toàn cho mọi môi trường. Nếu có session store dùng chung, cấu hình TTL/replication và logout/invalidation phải đồng nhất trên mọi instance.

Nên kiểm tra được ở response thật: `Set-Cookie` có `Secure` và `HttpOnly`, policy `SameSite` đúng với giao thức, không có session ID trong URL. Ở ingress, đảm bảo app biết request gốc là HTTPS khi cần. Đừng chỉ nhìn file YAML rồi kết luận browser nhận cookie như mong muốn.

### 8.3. RelyingPartyRegistration và bảo vệ nguồn IdP

Mỗi integration SAML yêu cầu cấu hình **IdP metadata có nguồn gốc rõ**, signing credentials, registration/entity ID/ACS cùng certificate rollover được kiểm soát. Spring Security dùng `RelyingPartyRegistration` để gắn thông tin SP và asserting party. Chỉ đọc metadata từ location do administrator kiểm soát; không để user nhập URL metadata tùy ý rồi lập tức trở thành một IdP được tin.

Dấu hiệu cấu hình nguy hiểm:

- Tự nhận signing certificate từ `ds:KeyInfo` trong SAMLResponse làm trust anchor.
- Tắt signature hoặc bỏ `Issuer`/`Destination`/`Audience` checks để “sửa lỗi tích hợp”.
- Chọn registration dựa duy nhất vào `Issuer` do payload gửi vào mà không ràng buộc với ngữ cảnh tenant/request.
- Đổi tên ACS/entity ID nhưng không rà validation và proxy headers.
- Gán `ROLE_ADMIN` trực tiếp vì có claim `email`/`department` trong assertion chưa xác minh mapping.
- Coi login SAML thành công là đã có quyền tất cả endpoints, hoặc dùng session SP làm bearer credential cho các API khác.

### 8.4. Replay protection là yêu cầu triển khai cần xác minh

Spring Security/OpenSAML có nhiều bước validation mặc định, nhưng **bảo đảm one-time/replay cache xuyên node** cần được kiểm tra theo phiên bản, extension, flow SP-initiated/IdP-initiated và cách triển khai. Nếu bộ validator mặc định không đáp ứng policy, bổ sung kiểm tra qua API extension chính thức của provider, **nối tiếp validation mặc định** thay vì thay toàn bộ bằng validator cho phép mọi response.

Thiết kế replay store khái niệm:

```text
sau khi cryptographic + protocol validation PASS:
    key = stableTrustedIssuer + ":" + verifiedAssertionId
    if atomicInsertIfAbsent(key, expiresAt + allowedSkew) == false:
        REJECT as replay
    else:
        continue creating Authentication/session
```

Cần giải quyết đồng thời: kiểm tra toàn bộ ID liên quan, key không do người ngoài chọn tenant context, TTL và skew, concurrency, lỗi cache và test nhiều replicas. Đừng copy đoạn pseudocode này thành filter trước SAML signature verification; một payload chưa tin cậy không được quyền điều khiển quota/cache để gây DoS.

### 8.5. OIDC tương ứng nhưng không cùng thuật ngữ

Trong OIDC, app là **Relying Party**, OP phát **ID token**; đe dọa issuer mix-up/token substitution đòi `iss`, `aud=client_id`, signature/JOSE validation, `state`, `nonce` khi sử dụng, PKCE và redirect URI đúng. ID token không phải SAML assertion; không có `AudienceRestriction` XML hay `Recipient` SAML. Với OAuth API, **access token** lại cần intended audience là resource server. **Session hijacking** vẫn có thể xảy ra sau OIDC login, nên cookie, session rotation, CSRF/XSS defenses tương đương.

## 9. Kiểm thử phòng vệ: phải thử cả đường sai

Tạo fixture/test identity riêng, không sử dụng assertion/cookie thật trên hệ production. Với mỗi test, ghi rõ **input**, **kỳ vọng** và **bằng chứng** (HTTP status, event, principal/session không được tạo). Không ghi credential raw vào output test hay log.

| Test âm tính | Kỳ vọng an toàn |
| --- | --- |
| SAML Response không chữ ký hoặc chữ ký sai | Reject; không có principal mới |
| Assertion ký bằng key chưa được SP trust | Reject, kể cả `Issuer` string giống IdP thật |
| Issuer của IdP A nhưng registration/tenant B | Reject hoặc không ánh xạ sang tenant B |
| `Audience` là SP khác | Reject |
| `Destination`/`Recipient` trỏ ACS sai | Reject |
| `InResponseTo` sai/không còn request (SP-initiated) | Reject, không tạo session từ response lạc transaction |
| `NotBefore` ở tương lai hoặc `NotOnOrAfter` đã qua | Reject |
| Gửi lại cùng assertion/response ID | Lần sau reject; thử song song và cross-replica |
| XML có nhiều assertion, chỉ một phần được ký | Chỉ principal được bảo vệ đúng chữ ký mới có thể được sử dụng; trường hợp mơ hồ reject |
| `RelayState` chứa URL ngoài allowlist | Không open redirect ra domain attacker |
| Gửi response hợp lệ nhưng map role/tenant khác | Authentication không tạo quyền trái policy |
| Session ID trước và sau login | Khác nhau (chống fixation) |
| Cookie mất `Secure`/`HttpOnly` hoặc không hợp lệ `SameSite` | Phát hiện lỗi cấu hình; sửa và kiểm tra trên browser thật |
| Logout, timeout, revoke phía server | Cookie cũ không truy cập được tài nguyên được bảo vệ |
| Request state-changing thiếu CSRF token | Reject theo chính sách, ngoài callback được xử lý đặc thù |
| SAML POST cross-site trên browser được hỗ trợ | Login vẫn ràng buộc đúng request/session; không bỏ validation để pass test |
| XSS thử đọc cookie `HttpOnly` | Không lấy được giá trị cookie từ `document.cookie`; vẫn phải xử lý XSS bằng lớp khác |

**Tính chất cần test:** Các test “invalid → reject” có giá trị hơn chỉ test login bình thường “valid → 200”. Với multi-tenant, phải thêm trường hợp hai user cùng email ở hai issuer khác nhau. Với load balancer, replay test cần chạy trên **hai pod/instance khác nhau**.

### 9.1. Kiểm tra bằng log có cấu trúc

Các trường nên có khi phù hợp và sau khi xác minh/tối thiểu hóa:

```text
event=saml_auth_rejected
request_correlation_id=...
registration_id=corp
reason_code=INVALID_AUDIENCE
remote_context=...            # dữ liệu IP đã chuẩn hóa theo trusted proxy
timestamp=...
```

Chỉ đưa các giá trị từ payload chưa tin cậy vào trường có xử lý escape, kích thước giới hạn và không dùng để ra quyết định. Không log `SAMLResponse`, assertion XML, cookie, `NameID`/email nhạy cảm theo mặc định. Log rõ reason code nhưng **không trả chi tiết trust key/validator nội bộ trong HTTP error cho attacker**.

Gợi ý các chỉ số: tỉ lệ `INVALID_SIGNATURE`, `UNTRUSTED_ISSUER`, `WRONG_AUDIENCE`, `EXPIRED_ASSERTION`, `REPLAY_DETECTED`, `IN_RESPONSE_TO_MISMATCH`; thay đổi signing key ngoài lịch; tăng số session mới của cùng user/tenant; thay đổi privilege bất thường sau SSO. Một số lỗi (đồng hồ lệch/ACS config sai) có thể là sự cố vận hành thay vì tấn công; điều tra nguyên nhân trước khi kết luận.

## 10. Minh họa Java 17+: chính sách chống replay ở lớp sau validation

Ví dụ dưới đây mô hình hóa một **quy tắc chấp nhận sau khi XML signature và toàn bộ protocol validation đã được thư viện SAML thực hiện thành công**. Dữ liệu lớp `VerifiedAssertion` được tạo thủ công để demo; tên lớp **không có nghĩa** nó thực sự verify chữ ký. Đây **không phải SAML parser, provider hay cơ chế cache production**.

Lưu file `ReplayBoundaryDemo.java`:

```java
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public class ReplayBoundaryDemo {
    record VerifiedAssertion(
            String issuer,
            String audience,
            String id,
            Instant notBefore,
            Instant notOnOrAfter) {}

    static boolean acceptAfterProtocolValidation(
            VerifiedAssertion assertion,
            String trustedIssuer,
            String expectedAudience,
            Instant now,
            Set<String> consumedIds) {

        if (!trustedIssuer.equals(assertion.issuer())) {
            return false;
        }
        if (!expectedAudience.equals(assertion.audience())) {
            return false;
        }
        if (now.isBefore(assertion.notBefore())
                || !now.isBefore(assertion.notOnOrAfter())) {
            return false;
        }
        return consumedIds.add(assertion.issuer() + "|" + assertion.id());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T03:00:00Z");
        Instant from = now.minusSeconds(30);
        Instant until = now.plusSeconds(120);

        VerifiedAssertion valid = new VerifiedAssertion(
                "https://idp.example", "sp-portal", "_assertion-1",
                from, until);
        VerifiedAssertion wrongAudience = new VerifiedAssertion(
                "https://idp.example", "sp-other", "_assertion-2",
                from, until);
        VerifiedAssertion expired = new VerifiedAssertion(
                "https://idp.example", "sp-portal", "_assertion-3",
                from, now.minusSeconds(1));

        Set<String> consumed = new HashSet<>();
        System.out.println("first: " + acceptAfterProtocolValidation(
                valid, "https://idp.example", "sp-portal", now, consumed));
        System.out.println("replay: " + acceptAfterProtocolValidation(
                valid, "https://idp.example", "sp-portal", now, consumed));
        System.out.println("other SP: " + acceptAfterProtocolValidation(
                wrongAudience, "https://idp.example", "sp-portal", now, consumed));
        System.out.println("expired: " + acceptAfterProtocolValidation(
                expired, "https://idp.example", "sp-portal", now, consumed));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ReplayBoundaryDemo.java
java ReplayBoundaryDemo
```

Stdout:

```text
first: true
replay: false
other SP: false
expired: false
```

**Đọc đúng ý nghĩa demo:**

- Dòng `first: true` chỉ có nghĩa **các quy tắc đơn giản trong ví dụ PASS** với một object do code tự tạo; không phải bằng chứng assertion SAML thật hợp lệ.
- `replay: false` vì `HashSet.add` từ chối ID đã thấy. Trong production dùng **store atomic dùng chung giữa replicas**, TTL, failure policy và xử lý concurrency; `HashSet` không đủ.
- `other SP: false` vì audience không khớp; `expired: false` vì hạn `NotOnOrAfter` đã qua.
- Demo cố ý **không** xác thực signature, `Destination`, `Recipient`, `InResponseTo`, `SubjectConfirmation`, schema, `OneTimeUse` và key rotation. Không dùng class này như auth filter thực tế.

## 11. Ứng phó sự cố theo loại mối đe dọa

### 11.1. Nghi IdP bị giả mạo hoặc signing key bị lộ

1. Ngăn tiếp nhận assertion từ registration/key đáng nghi theo khả năng triển khai; bảo vệ tài khoản quản trị cấu hình và pipeline cập nhật metadata.
2. Đối chiếu trust config thực tế với danh sách IdP/key được duyệt và thay đổi gần đây. Xác minh metadata từ kênh độc lập.
3. Phối hợp IdP đổi khóa/thu hồi credential có liên quan, cập nhật SP an toàn qua quy trình rollover; lưu ý không làm gián đoạn không cần thiết các IdP khác.
4. Tìm session được tạo từ issuer/key/thời gian ảnh hưởng, đánh giá hoạt động/đặc quyền rồi revoke session có liên quan.
5. Khắc phục nguyên nhân: quyền sửa config, trust-on-first-use, dependency vulnerable, quản lý certificate và monitoring.

### 11.2. Nghi assertion bị lộ hoặc replay

1. Dừng rò rỉ tại nguồn (APM, log body, proxy, chia sẻ hỗ trợ), hạn chế truy cập bản ghi có credential.
2. Điều tra theo correlation/ID đã hash phù hợp, time window và SP/tenant; không phổ biến lại assertion gốc trong ticket/chat.
3. Kích hoạt/chỉnh cache chống replay và các ràng buộc request/recipient; nếu cần, tạm giảm hiệu lực hoặc chặn login bất thường theo chính sách.
4. Revoke session liên quan và yêu cầu login lại khi có chứng cứ bị lạm dụng.
5. Kiểm thử lại trường hợp replay song song, cross-replica và flow IdP-initiated nếu được hỗ trợ.

### 11.3. Nghi session hijacking

1. Invalidate session bị ảnh hưởng **phía server**, không chỉ yêu cầu client xóa cookie; thu hồi các token liên quan theo mô hình ứng dụng.
2. Xác định nguyên nhân rò cookie, fixation, XSS, CSRF, máy người dùng, session store hoặc proxy; khắc phục đúng lớp.
3. Rà hoạt động của phiên và endpoint bị truy cập, áp dụng re-auth/MFA cho các thao tác nhạy cảm.
4. Kiểm tra cơ chế idle/absolute timeout, cookie flags, logout, session rotation và chính sách SLO.
5. Sau khắc phục, kiểm thử browser end-to-end và theo dõi các tín hiệu lặp.

**Phân biệt cốt lõi:** Thu hồi certificate tin cậy là phản ứng liên quan trust IdP; chặn replay là phản ứng với **bằng chứng đăng nhập SAML**; revoke HttpSession là phản ứng với **phiên của SP**. Một thao tác không mặc nhiên thay thế hai thao tác kia.

## 12. Checklist review trước production

- [ ] Chỉ IdP/metadata/khóa ký được duyệt mới xuất hiện trong `RelyingPartyRegistration`; có audit và quy trình rollover.
- [ ] Validator kiểm tra signature của **chính dữ liệu được dùng**; chống XML wrapping/XXE và thuật toán yếu theo policy.
- [ ] `Issuer`, `Destination`, `Audience`, `Recipient` và time conditions đúng theo SP/tenant, không bỏ qua để sửa lỗi cấu hình.
- [ ] Với SP-initiated, `InResponseTo` và state khớp request; IdP-initiated nếu cho phép có policy/threat model riêng.
- [ ] Replay detection thực thi với store atomic dùng chung, TTL phù hợp; đã test một lần và đồng thời nhiều instance.
- [ ] Không log SAMLResponse, assertion XML, credential hoặc session cookie; HTTPS xuyên chuỗi.
- [ ] Account linking phân biệt issuer + subject + tenant; role/object authorization hoạt động độc lập với login.
- [ ] Session ID thay khi login; cookie `Secure`/`HttpOnly`/`SameSite` được kiểm tra trên browser và SAML POST binding.
- [ ] Timeout, logout, session invalidation và CSRF/XSS protection được test; không dựa vào expired assertion để kết thúc session.
- [ ] Có test âm tính, audit events, alert, phương án key compromise và session compromise.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** SP đã kiểm tra XML signature nhưng dùng public key nằm trong chính `SAMLResponse`. Vì sao vẫn nguy hiểm?  
**Trả lời:** Attacker có thể tự ký bằng khóa mình kiểm soát. SP phải kiểm tra bằng khóa của IdP được tin **độc lập**, gắn với registration/issuer đã duyệt.

**Câu 2.** Assertion ký đúng, issuer đúng, chưa hết hạn; POST lại cùng Response lần hai có an toàn không?  
**Trả lời:** Không đủ. Phải kiểm tra request correlation, recipient/audience và đánh dấu ID đã dùng một cách atomic; chữ ký đúng không chứng minh đây là lần dùng đầu.

**Câu 3.** Spring Security xác thực SAML thành công nhưng `JSESSIONID` bị lộ. Có cần giả mạo IdP để chiếm phiên không?  
**Trả lời:** Không. Cookie phiên của SP có thể được tái dùng độc lập với assertion; cần revoke session phía server và khắc phục nguồn lộ.

**Câu 4.** Bật `SameSite=Lax` có luôn là lựa chọn an toàn nhất cho SAML không?  
**Trả lời:** Không. SAML HTTP POST từ IdP có thể là cross-site, khiến cookie correlation bị chặn. Phải kiểm thử browser thực tế, chọn cookie/state strategy phù hợp và bảo vệ CSRF ở các POST khác.

**Câu 5.** User đã đăng nhập qua IdP tin cậy, claim `groups=admin` có đủ để cho sửa mọi tài khoản không?  
**Trả lời:** Không. Claims cần được mapping theo policy tenant/issuer và endpoint phải kiểm tra authorization, nhất là object ownership.

## 14. Tài liệu chuẩn và hướng dẫn thực hành

- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) – kiến trúc SAML, cấu trúc assertion, browser SSO.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – signed XML, trust, replay, recipient/issuer/audience và XML signature wrapping.
- [Spring Security: SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – luồng `AuthnRequest`/ACS và `RelyingPartyRegistration`.
- [Spring Security: Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) – mặc định OpenSAML authentication provider và tùy biến validator.
- [Spring Security: Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) – session fixation, lifecycle và phương án `changeSessionId`.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet) – cookie, timeout, hijacking/fixation, logout.
- [Spring Boot: Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) – các thuộc tính `server.servlet.session` và cookie.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) – nếu kiến trúc federation dùng OIDC, kiểm tra issuer/audience/nonce theo đúng giao thức OIDC.