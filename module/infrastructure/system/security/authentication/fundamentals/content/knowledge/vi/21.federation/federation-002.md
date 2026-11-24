# Identity provider

> **Chương:** Federation  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Vai trò của Identity Provider trong xác thực liên kết và SSO, cách thiết lập niềm tin với ứng dụng nhận dạng, phát hành assertion/token, ánh xạ danh tính, quản lý vòng đời và xử lý rủi ro tập trung.

## 1. Identity Provider là gì?

**Identity Provider (IdP — nhà cung cấp danh tính)** là một hệ thống có thẩm quyền xác thực một chủ thể và cung cấp bằng chứng về danh tính hoặc kết quả xác thực cho một ứng dụng/dịch vụ khác. Thay vì mỗi ứng dụng tự quản lý mật khẩu và MFA riêng, tổ chức có thể dùng một IdP để xác thực người dùng rồi chia sẻ kết quả đó với các ứng dụng được tin cậy.

Ví dụ, nhân viên đăng nhập vào cổng nhân sự bằng tài khoản công ty. Cổng nhân sự chuyển người dùng đến IdP của tổ chức. IdP xác minh mật khẩu hoặc passkey, áp dụng MFA và phát hành kết quả xác thực theo giao thức đã thỏa thuận. Cổng nhân sự kiểm tra kết quả đó rồi tạo phiên ứng dụng của riêng mình.

IdP thường quản lý một phần hoặc toàn bộ:

- Tài khoản và định danh người dùng.
- Credential như mật khẩu, passkey, khóa bảo mật, chứng chỉ hoặc phương thức MFA.
- Chính sách xác thực, risk-based authentication và step-up.
- Phiên đăng nhập tại IdP.
- Việc phát hành assertion hoặc token cho ứng dụng nhận dạng.
- Khóa ký, metadata và thông tin tin cậy của các bên liên kết.

IdP **không tự động quyết định mọi quyền trong ứng dụng**. Ứng dụng nhận kết quả xác thực vẫn cần ánh xạ danh tính, áp dụng authorization và kiểm tra quyền trên tài nguyên cụ thể.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt IdP, relying party (RP), service provider (SP), authorization server và resource server.
- Giải thích federation và Single Sign-On (SSO).
- Mô tả cách IdP và ứng dụng thiết lập niềm tin, trao đổi assertion/token qua SAML hoặc OpenID Connect.
- Kiểm tra issuer, subject, audience, signature, nonce, state và thời hạn theo giao thức.
- Thiết kế ánh xạ danh tính, provisioning, offboarding và liên kết tài khoản.
- Nhận diện rủi ro khi IdP hoặc luồng federation bị chiếm quyền.

## 2. IdP, RP và các bên tham gia

Trong một hệ thống liên kết, mỗi bên có vai trò riêng:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **User / Subject** | Chủ thể muốn truy cập dịch vụ | Nhân viên Lan |
| **Identity Provider (IdP)** | Xác thực chủ thể và phát hành thông tin danh tính | IdP doanh nghiệp |
| **Relying Party (RP)** | Ứng dụng dựa vào kết quả xác thực từ IdP | Cổng nhân sự |
| **Service Provider (SP)** | Thuật ngữ thường dùng trong SAML cho dịch vụ nhận assertion | Ứng dụng SaaS |
| **Authorization Server** | Cấp token theo OAuth 2.0 | Máy chủ OAuth/OIDC |
| **Resource Server** | API bảo vệ dữ liệu/chức năng bằng access token | API báo cáo |
| **Browser / client** | Điều phối chuyển hướng và trao đổi thông điệp | Trình duyệt của người dùng |

Trong OpenID Connect, ứng dụng thường được gọi là **Relying Party (RP)** và hệ thống cung cấp xác thực là **OpenID Provider (OP)**, thường triển khai cùng vai trò IdP. Trong SAML, dịch vụ nhận assertion thường được gọi là **Service Provider (SP)**.

Các tên gọi phụ thuộc giao thức; không nên giả định mọi IdP đều là một sản phẩm duy nhất hoặc mọi RP đều có cùng kiến trúc.

### IdP và ứng dụng không cùng trách nhiệm

IdP có thể xác nhận rằng người dùng đã đăng nhập và cung cấp subject, phương thức xác thực hoặc một số thuộc tính. Ứng dụng vẫn cần trả lời:

- Subject này được ánh xạ vào tài khoản cục bộ nào?
- Tài khoản cục bộ còn hoạt động không?
- Người dùng thuộc tenant, nhóm hoặc tổ chức nào?
- Họ có quyền thực hiện hành động cụ thể không?
- Thuộc tính từ IdP có được phép dùng cho quyết định đó không?

Nếu IdP gửi claim **department=Finance**, ứng dụng không nên mặc nhiên trao quyền xem toàn bộ dữ liệu tài chính. Cần kiểm tra nguồn, độ tin cậy, tính cập nhật và chính sách phân quyền của ứng dụng.

## 3. Federation và Single Sign-On

**Identity federation** là mô hình trong đó một bên chấp nhận thông tin danh tính hoặc kết quả xác thực do một bên khác phát hành theo một thỏa thuận tin cậy và giao thức xác định.

**Single Sign-On (SSO)** cho phép người dùng xác thực một lần tại IdP rồi truy cập nhiều ứng dụng mà không phải nhập lại credential ở từng ứng dụng, miễn là phiên IdP còn hợp lệ và chính sách cho phép.

~~~mermaid
flowchart LR
    U["Người dùng"] --> B["Browser"]
    B --> A["Identity Provider"]
    A -->|"Xác thực + MFA"| A
    A -->|"Assertion / ID token"| B
    B --> R1["Ứng dụng A / RP"]
    B --> R2["Ứng dụng B / RP"]
    B --> R3["Ứng dụng C / RP"]
    R1 --> D1["Phiên ứng dụng A"]
    R2 --> D2["Phiên ứng dụng B"]
    R3 --> D3["Phiên ứng dụng C"]
~~~

Trong SSO, IdP có thể duy trì phiên đăng nhập của riêng nó. Mỗi RP vẫn có thể tạo session riêng. Do đó:

- Đăng xuất khỏi một ứng dụng không nhất thiết đăng xuất khỏi IdP.
- Đăng xuất khỏi IdP không tự động xóa mọi session tại các RP nếu không có cơ chế phối hợp.
- Một phiên IdP còn hiệu lực không có nghĩa mọi ứng dụng đều phải cho phép truy cập; RP có thể yêu cầu step-up hoặc từ chối theo chính sách.
- Khi tài khoản bị vô hiệu hóa tại IdP, các RP cần có cơ chế cập nhật trạng thái và thu hồi phiên/token với độ trễ chấp nhận được.

### SSO không phải chia sẻ mật khẩu

Ứng dụng không cần nhận mật khẩu IdP. Người dùng được chuyển đến IdP hoặc dùng luồng xác thực theo giao thức; RP nhận assertion/token có thể kiểm chứng. Nếu ứng dụng yêu cầu người dùng nhập lại mật khẩu công ty vào một biểu mẫu tự dựng để “kết nối SSO”, đó là một dấu hiệu thiết kế nguy hiểm và có thể tạo cơ hội phishing.

## 4. Thiết lập niềm tin giữa IdP và RP

Federation chỉ an toàn khi các bên biết rõ **ai đang phát hành**, **ai được phép nhận** và **bằng chứng nào được chấp nhận**.

Các bước thiết lập thường gồm:

1. **Định danh các bên:** xác định entity ID/issuer của IdP và identifier/client ID của RP.
2. **Trao đổi metadata/cấu hình:** endpoint, redirect URI, certificate hoặc JWKS, thuật toán và giao thức hỗ trợ.
3. **Thiết lập khóa tin cậy:** RP biết khóa công khai/chứng thư dùng xác minh assertion/token; IdP biết client và endpoint hợp lệ của RP.
4. **Cấu hình ràng buộc:** audience, recipient, destination, redirect URI, response mode và scope.
5. **Kiểm thử:** xác minh đúng issuer, chữ ký, thời hạn, nonce/state và trường hợp lỗi.
6. **Vận hành:** xoay vòng khóa, cập nhật metadata, giám sát thay đổi và thu hồi tích hợp.

### Trust metadata không phải một URL tùy ý

Metadata có thể được trao đổi thủ công hoặc tải từ endpoint đã cấu hình. Không cho phép request tự chọn issuer hoặc URL metadata rồi server tải khóa từ nguồn không tin cậy. Điều đó có thể mở ra SSRF, key substitution hoặc chấp nhận IdP giả.

Với OIDC, issuer thường có discovery document và JWKS URI. RP phải bắt đầu từ issuer đã đăng ký/cấu hình, kiểm tra issuer trong discovery, rồi lấy khóa từ JWKS endpoint thuộc nguồn đó. Trường **kid** trong JWT chỉ là gợi ý chọn khóa trong tập JWKS tin cậy; không được dùng nó để tạo URL hoặc đường dẫn tùy ý.

Với SAML, metadata thường chứa entity ID, endpoint và thông tin chứng thư ký/mã hóa. RP cần quản lý metadata như cấu hình tin cậy có kiểm soát phiên bản, nguồn và phê duyệt.

## 5. SAML và OpenID Connect

Hai giao thức liên kết phổ biến là SAML 2.0 và OpenID Connect (OIDC). Chúng có mô hình thông điệp khác nhau nhưng đều cho phép ứng dụng nhận kết quả xác thực từ IdP.

| Đặc điểm | SAML 2.0 | OpenID Connect |
|---|---|---|
| Dữ liệu chính | XML assertion/response | JSON claims trong ID token (JWT) |
| Cơ chế phổ biến | Browser SSO qua HTTP Redirect/POST binding | OAuth 2.0 authorization flow |
| Định danh bên phát hành | Entity ID | Issuer (iss) |
| Định danh subject | NameID hoặc subject/attribute theo profile | sub trong phạm vi issuer |
| Bên nhận | SP | OIDC client/RP |
| Chữ ký | XML Signature theo profile/cấu hình | JWS hoặc cơ chế token được giao thức quy định |
| Kiểm soát request/response | InResponseTo, Destination, Recipient, Audience và điều kiện assertion | state, nonce, redirect URI, issuer, audience và token validation |
| Sử dụng thường gặp | SSO doanh nghiệp và SaaS | Ứng dụng web/mobile và đăng nhập liên kết hiện đại |

Không nên chọn giao thức chỉ dựa trên định dạng dễ đọc. Hãy xem khả năng hỗ trợ của đối tác, threat model, thư viện đã được duy trì và yêu cầu vận hành.

### SAML Response và Assertion

Trong SAML, IdP có thể gửi một SAML Response chứa một hoặc nhiều Assertion. RP cần xác minh chữ ký theo profile, issuer, audience, recipient, destination, thời hạn và request correlation khi có yêu cầu SP-initiated.

Các trường thường cần chú ý:

- **Issuer:** entity ID của IdP được tin cậy.
- **Subject / NameID:** định danh chủ thể theo quy tắc đã thỏa thuận.
- **Conditions / NotBefore / NotOnOrAfter:** điều kiện và cửa sổ thời gian assertion hợp lệ.
- **AudienceRestriction:** assertion chỉ dành cho SP được chỉ định.
- **Recipient / Destination:** response được gửi tới endpoint hợp lệ.
- **InResponseTo:** liên kết response với AuthnRequest tương ứng trong luồng SP-initiated.
- **AuthnStatement:** thông tin về lần xác thực và ngữ cảnh xác thực.

RP phải dùng thư viện SAML đáng tin cậy, xử lý XML Signature đúng profile và chống XML Signature Wrapping. Không tự viết parser XML bảo mật hoặc chỉ tìm một node có chữ ký hợp lệ rồi tin các node khác trong tài liệu.

### OpenID Connect ID token

OIDC xây dựng trên OAuth 2.0 và bổ sung lớp xác thực. **ID token** mang claim về kết quả xác thực người dùng cho client/RP. Các claim quan trọng có thể gồm:

- **iss:** issuer.
- **sub:** subject ổn định trong phạm vi issuer.
- **aud:** client ID hoặc các audience được phép.
- **exp, iat:** thời điểm hết hạn và phát hành.
- **nonce:** liên kết ID token với yêu cầu xác thực của client khi được sử dụng.
- **auth_time:** thời điểm xác thực người dùng.
- **acr, amr:** ngữ cảnh/mức hoặc phương thức xác thực, tùy profile và chính sách.

RP phải xác minh chữ ký, issuer, audience, thời hạn, nonce và các quy tắc OIDC khác. **ID token không phải access token**; API/resource server không được nhận ID token thay access token chỉ vì cả hai đều có thể là JWT.

## 6. Luồng OIDC Authorization Code với PKCE

Đối với ứng dụng web/mobile hiện đại, Authorization Code Flow với PKCE là lựa chọn phổ biến. PKCE giúp bảo vệ authorization code khỏi bị chặn và sử dụng bởi một client khác, đặc biệt với ứng dụng công khai.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client / RP
    participant B as Browser
    participant OP as OpenID Provider
    participant API as Resource API
    C->>C: Tạo state, nonce, code_verifier
    C->>B: Chuyển hướng authorization request + code_challenge
    B->>OP: Authorization request
    OP->>U: Đăng nhập / MFA / consent nếu cần
    U-->>OP: Hoàn tất xác thực
    OP-->>B: Redirect URI + authorization code + state
    B-->>C: Callback
    C->>C: Kiểm tra state
    C->>OP: Token request + code_verifier
    OP->>OP: Kiểm tra PKCE và code
    OP-->>C: ID token + access token (+ refresh token nếu cấp)
    C->>C: Xác minh ID token
    C->>API: Request + access token
    API->>API: Kiểm tra access token và quyền
    API-->>C: Resource response
~~~

### Các ràng buộc quan trọng

1. **Redirect URI:** phải khớp chính xác với URI đã đăng ký theo quy tắc của nhà cung cấp; không dùng wildcard tùy tiện.
2. **state:** ràng buộc callback với yêu cầu đã khởi tạo, giúp chống CSRF và response injection.
3. **nonce:** ràng buộc ID token với yêu cầu đăng nhập cụ thể, chống replay/substitution trong OIDC.
4. **PKCE:** client tạo code_verifier ngẫu nhiên và gửi code_challenge; token endpoint kiểm tra verifier khi đổi code.
5. **Issuer:** RP chỉ chấp nhận issuer đã cấu hình.
6. **Audience:** ID token phải dành cho đúng client.
7. **Code:** authorization code ngắn hạn, dùng một lần và gắn đúng client/redirect URI.

Không lưu state, nonce hoặc code_verifier trong nơi có thể bị ứng dụng khác đọc; không đặt token trong URL callback. Dùng thư viện OIDC đã được duy trì và tuân thủ cấu hình của issuer.

## 7. Ánh xạ danh tính: iss + sub

Sau khi xác minh assertion/token, RP cần xác định tài khoản nội bộ tương ứng. Đây là bước **identity mapping**.

Trong OIDC, cặp **issuer (iss) + subject (sub)** là định danh phù hợp trong phạm vi nhà phát hành. sub thường chỉ duy nhất trong phạm vi issuer; không nên giả định giá trị đó là duy nhất toàn cầu.

Ví dụ:

| Issuer | Subject | Ý nghĩa |
|---|---|---|
| https://id.example.org | user-824 | Một subject tại IdP công ty |
| https://login.partner.net | user-824 | Một subject khác tại IdP đối tác |

Hai giá trị sub giống nhau không có nghĩa là cùng một người. RP cần dùng issuer cùng subject làm khóa liên kết và lưu mapping rõ ràng.

### Vì sao email không phải khóa liên kết mặc định?

Email có thể:

- Thay đổi khi người dùng đổi tên hoặc tổ chức đổi domain.
- Được tái cấp cho nhân viên mới sau khi người cũ nghỉ việc.
- Chưa được xác minh tại một IdP.
- Được chia sẻ hoặc đại diện cho hộp thư nhóm.
- Có cách chuẩn hóa khác nhau giữa các hệ thống.

Nếu tự động ghép tài khoản chỉ vì email trùng nhau, kẻ tấn công có thể lợi dụng việc tái cấp email hoặc claim chưa được xác minh để chiếm tài khoản cũ.

### Liên kết tài khoản có kiểm soát

Khi người dùng muốn liên kết một IdP mới với tài khoản hiện tại:

1. Yêu cầu xác thực lại tài khoản cục bộ ở mức phù hợp.
2. Khởi tạo luồng federation tới issuer mới với state/nonce riêng.
3. Xác minh đầy đủ assertion/token từ IdP mới.
4. Hiển thị rõ tài khoản/nhà cung cấp sắp được liên kết và yêu cầu xác nhận ý định.
5. Kiểm tra mapping chưa bị liên kết với tài khoản khác theo chính sách.
6. Lưu cặp issuer/subject và audit.
7. Thông báo qua kênh đã xác minh.

Không cho phép callback federation tự động ghi đè mapping hiện có hoặc chuyển quyền sở hữu tài khoản chỉ vì claim email trùng.

## 8. Provisioning và vòng đời tài khoản liên kết

Xác thực liên kết trả lời “người này đã chứng minh danh tính với IdP chưa?”. **Provisioning** trả lời “ứng dụng có nên tạo/cập nhật tài khoản và quyền của họ không?”.

Hai việc này liên quan nhưng khác nhau. Một assertion SAML hoặc ID token không nhất thiết có nghĩa ứng dụng phải tự tạo mọi quyền. Tổ chức cần quy định nguồn dữ liệu có thẩm quyền và cách cập nhật vòng đời.

### Các mô hình provisioning

| Mô hình | Cách hoạt động | Điểm cần kiểm soát |
|---|---|---|
| **JIT (Just-in-Time)** | Tạo tài khoản cục bộ khi người dùng đăng nhập liên kết lần đầu | Chỉ tạo khi issuer/subject được tin cậy; quyền mặc định tối thiểu |
| **Pre-provisioning** | Tài khoản được tạo trước bởi quản trị viên hoặc hệ thống nhân sự | Đối soát định danh và trạng thái trước khi cho đăng nhập |
| **SCIM provisioning** | IdP hoặc hệ thống nguồn gửi sự kiện tạo/cập nhật/vô hiệu hóa qua SCIM | Xác thực API, quyền, idempotency, audit và xử lý lỗi đồng bộ |
| **Import/sync theo lô** | Đồng bộ định kỳ danh sách tài khoản/nhóm | Phát hiện dữ liệu cũ, xung đột và tài khoản không còn trong nguồn |

### Thuộc tính và nhóm

RP có thể nhận claim như tên, email, department, group hoặc role. Chỉ nên dùng những thuộc tính cần thiết; mỗi claim cần có:

- Nguồn phát hành và mức tin cậy.
- Quy tắc chuẩn hóa và kiểu dữ liệu.
- Ý nghĩa và phạm vi (toàn tổ chức, tenant hay ứng dụng).
- Quy tắc cập nhật và xử lý khi claim bị thiếu.
- Quyền nào được suy ra từ thuộc tính đó, nếu có.

Không tự động chuyển mọi group từ IdP thành role quản trị. Group membership có thể được cập nhật chậm hoặc chứa nhóm rộng hơn phạm vi ứng dụng.

### Offboarding

Khi nhân viên nghỉ việc hoặc tài khoản bị đình chỉ:

1. Nguồn nhân sự/IdP cập nhật trạng thái tài khoản.
2. IdP ngăn xác thực mới theo chính sách.
3. Sự kiện provisioning hoặc cơ chế đồng bộ thông báo cho RP.
4. RP vô hiệu hóa tài khoản cục bộ, thu hồi session và refresh token.
5. Các API/resource server cập nhật quyền và trạng thái cache.
6. Kiểm tra service account, API key, OAuth grant hoặc tài nguyên mà người đó sở hữu.

SSO không tự giải quyết offboarding. Nếu RP chỉ kiểm tra assertion lúc đăng nhập và giữ session nhiều ngày, tài khoản có thể tiếp tục truy cập sau khi IdP đã vô hiệu hóa người dùng.

## 9. MFA và step-up tại IdP

IdP thường là nơi tập trung chính sách xác thực. Nó có thể quyết định khi nào cần mật khẩu, passkey, MFA hoặc step-up dựa trên ứng dụng, nhóm người dùng, thiết bị và rủi ro.

Ví dụ:

- Ứng dụng xem lịch có thể chấp nhận phiên IdP hiện tại.
- Cổng lương yêu cầu MFA chống phishing.
- Bảng điều khiển quản trị yêu cầu xác thực lại gần thời điểm thao tác.
- Một yêu cầu từ thiết bị mới có thể kích hoạt challenge bổ sung.

### RP yêu cầu mức xác thực

OIDC có thể dùng các tham số như acr_values, max_age và claim auth_time để diễn đạt yêu cầu/ngữ cảnh xác thực theo profile. SAML có AuthnContext để mô tả ngữ cảnh xác thực. RP và IdP cần thống nhất ý nghĩa cụ thể; không chỉ dựa vào tên chuỗi mà không có mapping chính sách.

Claim amr có thể mô tả phương thức xác thực đã dùng, nhưng RP phải hiểu cách IdP phát hành và liệu nó có đáng tin trong hệ thống đó hay không. Một giá trị mfa không tự chứng minh yếu tố độc lập hoặc khả năng chống phishing.

### Xác thực tập trung làm tăng tác động khi IdP bị chiếm

IdP là điểm có quyền phát hành bằng chứng cho nhiều ứng dụng. Nếu tài khoản quản trị IdP hoặc khóa ký bị chiếm, tác động có thể lan đến nhiều RP. Vì vậy:

- Tài khoản quản trị IdP cần phương thức chống phishing và phân tách quyền.
- Thay đổi chính sách, issuer, redirect URI, certificate/JWKS cần phê duyệt và audit.
- Bảo vệ tài khoản break-glass và kiểm thử quy trình khẩn cấp.
- Giám sát tạo client mới, consent bất thường, thêm yếu tố MFA và thay đổi metadata.
- Có kế hoạch xoay vòng khóa ký và xử lý sự cố.

## 10. Logout và Single Logout

Logout trong federation phức tạp vì có nhiều session độc lập:

- Session tại IdP.
- Session tại từng RP/SP.
- Token access/refresh đang được client giữ.
- Phiên tại API gateway hoặc resource server.

**Single Logout (SLO)** là nhóm cơ chế để phối hợp kết thúc các phiên liên quan giữa IdP và RP/SP. SLO không phải lúc nào cũng được triển khai đầy đủ hoặc đồng bộ ngay lập tức.

### Các trường hợp cần phân biệt

| Hành động | Điều thường xảy ra | Giới hạn |
|---|---|---|
| Logout tại RP | RP hủy session cục bộ | IdP có thể vẫn đăng nhập |
| Logout tại IdP | IdP hủy session của mình | RP khác có thể vẫn còn session nếu không nhận SLO |
| OIDC RP-Initiated Logout | RP chuyển hướng đến endpoint logout của OP theo cấu hình | Cần kiểm tra post_logout_redirect_uri và trạng thái |
| SAML Single Logout | Các bên gửi logout message theo profile | Hỗ trợ và độ tin cậy phụ thuộc triển khai |
| Thu hồi refresh token | Ngăn cấp access token mới bằng refresh token đó | Access token tự chứa đã cấp có thể còn hạn |

RP nên có session timeout riêng, cơ chế thu hồi phiên và kiểm tra trạng thái tài khoản. Không giả định rằng logout ở một màn hình đã kết thúc mọi phiên ở mọi ứng dụng.

## 11. Rủi ro và lỗi cấu hình federation

| Rủi ro | Cách xảy ra | Kiểm soát |
|---|---|---|
| Issuer spoofing | RP chấp nhận token từ IdP không tin cậy | Allowlist issuer/entity ID, xác minh chữ ký và nguồn khóa |
| Audience confusion | Assertion/token dành cho ứng dụng khác được chấp nhận | Kiểm tra audience/recipient chính xác |
| Redirect URI manipulation | Authorization code bị gửi đến callback không được phép | Exact redirect URI matching, state và PKCE |
| Login CSRF / response injection | Kẻ tấn công gắn response vào phiên người khác | state, nonce, request correlation và ràng buộc browser session |
| Replay assertion/token | Response cũ được gửi lại trong cửa sổ hợp lệ | Thời hạn ngắn, InResponseTo/nonce/jti, replay cache |
| Signature wrapping (SAML) | Parser xác minh node này nhưng ứng dụng dùng node khác | Thư viện SAML chuẩn, xác minh đúng signed element và profile |
| Key rotation lỗi | RP dùng khóa cũ hoặc chấp nhận khóa giả | Metadata/JWKS trust, overlap có kiểm soát, audit |
| Email auto-linking | Tài khoản ghép chỉ dựa trên email trùng | Dùng issuer+subject, xác minh và xác nhận liên kết |
| Claim overtrust | Role/group từ IdP được tin quá mức | Mapping allowlist, authorization server-side |
| IdP compromise | Kẻ tấn công phát hành assertion/token hợp lệ | Bảo vệ IdP admin, khóa ký, MFA chống phishing, incident response |
| Stale RP session | IdP disable nhưng RP vẫn giữ phiên | SCIM/event sync, session revocation và timeout phù hợp |
| Misconfigured SLO | Logout không lan truyền hoặc callback không an toàn | Kiểm thử logout, xác minh request và redirect allowlist |

### Token substitution và confused deputy

Một RP có thể nhận token được phát hành cho một client hoặc API khác. Nếu chỉ kiểm tra chữ ký mà bỏ qua audience, type hoặc issuer, RP có thể trở thành **confused deputy**: sử dụng quyền của mình dựa trên bằng chứng không dành cho nó.

Luôn kiểm tra token đúng loại, đúng issuer, đúng audience, đúng client và đúng mục đích. ID token dành cho OIDC client không được dùng như access token cho API.

## 12. Quản lý khóa ký và metadata

IdP ký assertion hoặc token để RP xác minh nguồn phát hành và tính toàn vẹn. Khóa ký là tài sản trọng yếu.

### Vòng đời khóa

1. Sinh khóa theo thuật toán và độ dài được chính sách chấp nhận.
2. Bảo vệ private signing key bằng HSM/KMS hoặc vùng bảo vệ phù hợp.
3. Công bố public key/certificate qua metadata hoặc JWKS từ nguồn tin cậy.
4. Theo dõi thời hạn chứng thư, thuật toán và khả năng tương thích.
5. Xoay khóa có kế hoạch, cho phép giai đoạn overlap ngắn khi cần.
6. Gỡ khóa cũ sau khi RP đã cập nhật và token/assertion cũ hết hiệu lực theo chính sách.
7. Khi nghi lộ khóa, chuyển sang quy trình khẩn cấp, thu hồi tin cậy và đánh giá assertion/token đã phát hành.

### JWKS và kid

Trong OIDC, RP có thể lấy public key từ JWKS URI được công bố trong discovery metadata của issuer tin cậy. JWT header có thể chứa kid để chọn một khóa trong tập đó.

Không tải JWKS từ URL do JWT tự chỉ định; không cho kid trở thành đường dẫn file hoặc query tùy ý. Khi không tìm thấy kid, có thể refresh JWKS từ endpoint đã cấu hình theo chính sách, nhưng cần rate limit để tránh bị lạm dụng.

### Chứng thư SAML

Trong SAML, metadata có thể công bố chứng thư dùng để xác minh chữ ký. Chứng thư hết hạn hoặc thay đổi cần quy trình cập nhật được kiểm soát. Không tự động chấp nhận chứng thư mới chỉ vì nó xuất hiện trong response; phải xác minh nguồn metadata và phê duyệt thay đổi tin cậy.

## 13. Quyền riêng tư và tối thiểu hóa thuộc tính

Federation có thể truyền nhiều thuộc tính về người dùng. RP chỉ nên yêu cầu và lưu dữ liệu cần thiết cho chức năng.

Ví dụ, ứng dụng lịch có thể chỉ cần subject và tên hiển thị; không nhất thiết cần ngày sinh, số điện thoại cá nhân, nhóm nhạy cảm hoặc toàn bộ hồ sơ nhân sự.

Nguyên tắc:

- Yêu cầu scope/claim tối thiểu.
- Phân biệt thuộc tính bắt buộc với tùy chọn.
- Tránh đưa dữ liệu cá nhân nhạy cảm vào JWT nếu RP không cần đọc.
- Xác định thời hạn lưu và mục đích sử dụng thuộc tính.
- Không dùng email làm định danh nội bộ bất biến.
- Xử lý thay đổi thuộc tính và xóa dữ liệu khi liên kết kết thúc theo chính sách.

Một IdP có thể biết người dùng truy cập ứng dụng nào và khi nào. Nhật ký federation vì vậy cũng có thể nhạy cảm; cần kiểm soát quyền truy cập, retention và sử dụng đúng mục đích.

## 14. Tình huống thực hành: kết nối SaaS với IdP doanh nghiệp

**Bối cảnh:** Công ty dùng IdP tập trung cho nhân viên và muốn kết nối một dịch vụ SaaS quản lý dự án. SaaS hỗ trợ SAML SSO và SCIM provisioning. Nhân viên có thể thuộc nhóm Engineering, Finance hoặc Operations.

### Thiết lập ban đầu

1. Quản trị viên xác minh domain và quyền sở hữu tenant SaaS.
2. Hai bên trao đổi metadata: entity ID, ACS URL, certificate và các thuộc tính cần thiết.
3. IdP chỉ phát hành assertion cho SP đã đăng ký.
4. SP xác minh signature, issuer, audience, recipient, destination và thời hạn.
5. Nhóm người dùng được phép truy cập được xác định trong IdP và mapping ở SaaS.
6. SCIM được cấu hình với credential riêng, scope tối thiểu và audit.

### Nhân viên đăng nhập

1. Nhân viên mở SaaS.
2. SaaS chuyển trình duyệt đến IdP.
3. IdP xác thực bằng passkey/MFA theo chính sách.
4. IdP phát hành SAML assertion cho đúng SP.
5. SaaS xác minh assertion và ánh xạ subject vào tài khoản cục bộ.
6. SaaS kiểm tra trạng thái tài khoản và nhóm/role được phép.
7. SaaS tạo session riêng.

### Nhân viên nghỉ việc

1. Hệ thống nhân sự cập nhật trạng thái nhân viên.
2. IdP vô hiệu hóa tài khoản và ngăn đăng nhập mới.
3. SCIM gửi sự kiện deactivate đến SaaS.
4. SaaS vô hiệu hóa tài khoản, thu hồi session và quyền.
5. Tổ chức kiểm tra API token, dự án sở hữu, webhook và tài nguyên do nhân viên quản lý.

Nếu SCIM thất bại hoặc bị trễ, SaaS có thể vẫn giữ session cũ. Cần giám sát lỗi provisioning, đối soát định kỳ và quy định thời gian tối đa để offboarding có hiệu lực.

### Bài học thiết kế

- SAML SSO xác thực người dùng; SCIM quản lý provisioning. Hai giao thức giải quyết hai bài toán khác nhau.
- Claim group/department cần mapping có kiểm soát, không tự động cấp quyền quản trị.
- Session SaaS cần expiry/revocation riêng.
- Thay đổi metadata hoặc certificate là thay đổi trust boundary, cần phê duyệt và audit.

## 15. Kiểm thử federation

Kiểm thử trong môi trường được phép với tài khoản và IdP thử nghiệm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Token từ issuer không nằm trong allowlist | RP từ chối |
| ID token có audience sai | RP từ chối |
| ID token có nonce không khớp | RP từ chối |
| Authorization response có state sai | Client từ chối callback |
| Redirect URI không khớp đăng ký | Authorization server từ chối |
| Authorization code bị dùng lại | Token endpoint từ chối |
| PKCE verifier sai | Token endpoint từ chối |
| SAML audience/recipient sai | SP từ chối assertion |
| SAML assertion hết hạn hoặc replay | SP từ chối |
| XML có cấu trúc signature wrapping thử nghiệm | Parser/verifier từ chối hoặc xử lý đúng signed element |
| Claim email trùng nhưng issuer/subject khác | Không tự động ghép tài khoản |
| SCIM deactivate thất bại | Có cảnh báo, đối soát và quy trình xử lý |
| IdP disable nhưng RP session còn tồn tại | RP thu hồi theo cơ chế/giới hạn thời gian đã định |
| Khóa ký được xoay vòng | RP xác minh được khóa mới và ngừng tin khóa cũ đúng thời điểm |
| Logout tại IdP | Các RP xử lý SLO/session theo chính sách đã công bố |

## 16. Checklist thiết kế Identity Provider

- [ ] Xác định rõ IdP, RP/SP, authorization server và resource server.
- [ ] Có danh sách issuer/entity ID và client/SP được tin cậy.
- [ ] Metadata, redirect URI, ACS URL, certificate và JWKS được quản lý như cấu hình nhạy cảm.
- [ ] Chọn SAML/OIDC theo giao thức, thư viện và yêu cầu vận hành.
- [ ] OIDC kiểm tra state, nonce, PKCE, issuer, audience, redirect URI và thời hạn.
- [ ] SAML kiểm tra chữ ký, issuer, audience, recipient, destination, thời hạn và request correlation.
- [ ] ID token không bị dùng thay access token.
- [ ] Identity mapping dùng issuer+subject hoặc định danh ổn định theo giao thức; không auto-link chỉ bằng email.
- [ ] JIT/pre-provisioning/SCIM có nguồn dữ liệu, quyền và audit rõ.
- [ ] Group/role claim được mapping theo allowlist và chính sách ứng dụng.
- [ ] MFA/step-up có mức bảo đảm phù hợp; RP hiểu đúng claim xác thực.
- [ ] Có quy trình offboarding và thu hồi session/token tại RP.
- [ ] Logout/SLO được kiểm thử; không giả định một logout kết thúc mọi phiên.
- [ ] Khóa ký có bảo vệ, rotation, overlap và xử lý sự cố.
- [ ] Thu thập thuộc tính tối thiểu, bảo vệ log federation và thời hạn lưu.
- [ ] Có kiểm thử issuer/audience/nonce/state, replay, token substitution và provisioning delay.

## Ghi nhớ

Identity Provider xác thực chủ thể và phát hành bằng chứng để ứng dụng khác có thể dựa vào. Federation thiết lập niềm tin giữa IdP và RP/SP; SSO giúp dùng một lần xác thực cho nhiều ứng dụng, nhưng mỗi RP vẫn có session, authorization và vòng đời riêng.

Một triển khai an toàn phải xác minh đúng issuer, audience, chữ ký, thời hạn và ngữ cảnh giao thức; ánh xạ danh tính bằng định danh ổn định; quản lý provisioning/offboarding; bảo vệ khóa ký; và phối hợp logout/thu hồi phiên. **Tin cậy IdP không có nghĩa trao toàn bộ quyền cho mọi claim mà IdP gửi.**
