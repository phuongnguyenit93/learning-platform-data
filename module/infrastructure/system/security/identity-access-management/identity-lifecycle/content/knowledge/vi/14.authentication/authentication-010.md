# Kiểm thử authentication trong quản lý vòng đời danh tính IAM

> **Chương: Authentication.** Kiểm thử authentication (kiểm thử xác thực) nhằm chứng minh rằng hệ thống chỉ tạo hoặc duy trì phiên truy cập cho **đúng chủ thể**, theo **phương thức và mức bảo đảm được chính sách cho phép**, đồng thời từ chối các luồng sai, giả mạo hoặc đã hết hiệu lực. Trong module IAM Identity Lifecycle, kiểm thử không dừng ở biểu mẫu đăng nhập: phải kiểm tra tác động của **Joiner–Mover–Leaver**, IdP, SSO, token, phiên, MFA, quá trình khôi phục và ứng dụng đích.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định phạm vi của kiểm thử xác thực, phân biệt với identity proofing, authorization và provisioning.
2. Xây dựng ma trận kiểm thử gồm luồng thành công, thất bại, biên, lạm dụng, khôi phục và kiểm soát phiên.
3. Kiểm thử an toàn các luồng mật khẩu, MFA, passkey/WebAuthn, SSO qua OIDC hoặc SAML và quản lý token.
4. Chứng minh việc kích hoạt, đổi vai trò, đình chỉ và thu hồi danh tính trong **Joiner–Mover–Leaver** có tác động đúng tới quyền đăng nhập ở cả IdP lẫn ứng dụng.
5. Tổ chức kiểm thử tự động, fault injection, quan sát audit và kiểm tra các đường truy cập không đi qua SSO.
6. Xác định tiêu chí đạt, giới hạn bằng chứng và quy trình xử lý lỗi bảo mật trước khi đưa hệ thống vào vận hành.

## 1. Authentication cần kiểm thử điều gì?

**Authentication** là quá trình kiểm tra bằng chứng rằng chủ thể đang yêu cầu truy cập có quyền kiểm soát authenticator hoặc phương thức được hệ thống tin cậy. Ví dụ: người dùng đăng nhập bằng passkey, mật khẩu kèm MFA hoặc ứng dụng doanh nghiệp chấp nhận kết quả xác thực từ IdP thông qua OIDC/SAML.

Kiểm thử tốt phải xác minh cả **đường được phép** và **đường bị cấm**, đồng thời quan sát kết quả thật tại điểm truy cập. Một thông báo “Login success” trên giao diện chưa chứng minh rằng token hợp lệ, phiên được ràng buộc đúng User, app kiểm tra token đúng hay việc thu hồi thực sự có hiệu lực.

### Không nhầm với ba khái niệm liên quan

| Hoạt động | Câu hỏi chính | Ví dụ kiểm thử |
| --- | --- | --- |
| **Identity proofing** | Danh tính khai báo ban đầu được xác minh và liên kết đúng người chưa? | Nhân viên mới có proofing hợp lệ trước khi bật tài khoản nhạy cảm. |
| **Authentication** | Người/thiết bị đang dùng luồng đăng nhập có chứng minh được chủ thể hợp lệ không? | Sai OTP hoặc assertion WebAuthn giả phải bị từ chối. |
| **Authorization** | Chủ thể đã xác thực có được thực hiện hành động trên tài nguyên này không? | User có phiên hợp lệ nhưng không được sửa dữ liệu tenant khác. |
| **Provisioning** | User, group và account cần thiết đã được tạo hoặc thu hồi ở đích chưa? | SCIM User được disabled sau Leaver, nhưng ứng dụng vẫn phải được kiểm tra đăng nhập thực tế. |

**Một test đăng nhập thành công không thay thế test phân quyền.** Và một response SCIM thành công không chứng minh token, phiên hoặc credential đã được ứng dụng ngừng chấp nhận.

### Các câu hỏi trọng tâm

- Ai là **subject** thực sự sau khi xác thực? Định danh đó có đúng namespace, issuer và tenant không?
- Phương thức được sử dụng có đáp ứng chính sách cho người dùng, tài nguyên và mức rủi ro không?
- Có thể giả mạo, phát lại, chèn, dùng sai audience hay chuyển token giữa các client không?
- Nếu tài khoản bị suspend, hết hợp đồng hoặc Leaver có hiệu lực, những luồng xác thực nào còn hoạt động?
- Phiên mới và phiên cũ có được xử lý theo thiết kế ở cả IdP và ứng dụng?
- Có log để chứng minh kết quả mà không lộ mật khẩu, OTP, session cookie hoặc token không?

## 2. Xác định phạm vi, mô hình đe dọa và tiêu chí chấp nhận

Không nên bắt đầu bằng một tập script thử mật khẩu ngẫu nhiên. Trước tiên phải lập sơ đồ **trust boundary** và những kênh xác thực thực sự tồn tại trong hệ thống.

~~~mermaid
flowchart LR
    U["Người dùng / thiết bị"] --> B["Browser hoặc mobile app"]
    B --> IDP["IdP<br/>Mật khẩu, MFA, passkey"]
    IDP --> SSO["OIDC / SAML<br/>Kết quả xác thực"]
    SSO --> APP["Ứng dụng nghiệp vụ<br/>session và token validation"]
    APP --> API["API / tài nguyên<br/>authorization"]
    HR["HR / nguồn JML"] --> IAM["IAM / IGA<br/>lifecycle & policy"]
    IAM --> IDP
    IAM --> SCIM["SCIM / connectors"]
    SCIM --> APP
    IAM --> AUD["Audit / monitoring"]
    IDP --> AUD
    APP --> AUD
~~~

Sơ đồ mang tính khái niệm. Luồng thực tế có thể có BFF, API gateway, ứng dụng native, nhiều IdP, broker hoặc federation; kiểm thử phải dựa trên thiết kế và hợp đồng tích hợp được phê duyệt.

### Ma trận rủi ro

| Nguy cơ | Ví dụ | Điều kiểm thử cần chứng minh |
| --- | --- | --- |
| **Account takeover** | Người khác chiếm luồng đặt lại mật khẩu hoặc đăng ký MFA. | Recovery xác minh đúng người và thông báo sự kiện nhạy cảm. |
| **Credential stuffing / guessing** | Thử liên tục mật khẩu đối với nhiều tài khoản. | Cơ chế chống lạm dụng hoạt động mà không gây lộ danh tính. |
| **Phishing / replay** | OTP, assertion hoặc mã xác thực bị phát lại. | Challenge/correlation được kiểm tra; bằng chứng hết hiệu lực không dùng lại được. |
| **Token substitution** | Token của client/tenant A được đưa vào client/tenant B. | Kiểm tra issuer, audience, scope và ràng buộc theo giao thức. |
| **Session fixation / hijacking** | Giữ nguyên session ID khi đăng nhập hoặc dùng cookie bị đánh cắp. | Session được tái tạo/ràng buộc và bảo vệ khi cần. |
| **Stale authentication** | User bị Leaver nhưng app vẫn chấp nhận phiên cũ. | Thời gian thu hồi, logout và kiểm soát bù đáp ứng chính sách. |
| **MFA downgrade** | Luồng fallback bỏ qua yếu tố bắt buộc. | Không thể giảm mức bảo đảm ngoài trường hợp đã được phê duyệt. |
| **Identity confusion** | Đăng nhập tenant A nhưng liên kết nhầm identity tenant B. | Subject và account mapping được kiểm chứng. |
| **Unmanaged credential** | PAT hoặc mật khẩu cục bộ dùng được dù SSO đã khóa. | Đường truy cập độc lập có test và cơ chế thu hồi riêng. |

**Tiêu chí chấp nhận phải gắn với chính sách**, chẳng hạn những quyền nào yêu cầu phishing-resistant MFA, trường hợp nào được phép fallback, session sống bao lâu, hệ thống nào bắt buộc thu hồi ngay và khoảng tồn dư nào được chấp nhận nếu kỹ thuật không hỗ trợ revoke tức thời.

Không tự đặt một con số timeout, lockout hoặc SLA áp dụng cho mọi tổ chức; cần đo theo mức nhạy cảm, nguy cơ khóa nhầm tài khoản và khả năng của từng nền tảng.

## 3. Thiết kế dữ liệu kiểm thử và môi trường an toàn

Kiểm thử authentication thường thao tác với secret, tài khoản và chính sách nhạy cảm. Nên dùng **môi trường tích hợp/staging được cô lập**, dữ liệu giả, định danh có namespace riêng, endpoint chính thức cho test và quyền truy cập giới hạn.

### Bộ dữ liệu nền

| Danh tính thử | Trạng thái vòng đời | Phương thức | Mục đích |
| --- | --- | --- | --- |
| **joiner-pending** | Chưa đến ngày kích hoạt | Chưa hoàn tất enrollment | Chứng minh không thể dùng quyền nghiệp vụ sớm. |
| **employee-active** | ACTIVE | Passkey hoặc mật khẩu + MFA | Kiểm tra đăng nhập thành công. |
| **employee-no-mfa** | ACTIVE | Chưa đăng ký yếu tố bắt buộc | Kiểm tra yêu cầu enrollment/step-up. |
| **employee-suspended** | SUSPENDED | Đã có credential trước đó | Kiểm tra chặn luồng mới và chính sách phiên cũ. |
| **employee-leaver** | TERMINATED | Đã có SSO/session/token trước sự kiện | Kiểm tra thu hồi trên các kênh. |
| **contractor-expired** | Hết hợp đồng | Tài khoản SaaS liên kết | Kiểm tra hạn truy cập và account cục bộ. |
| **privileged-admin** | ACTIVE với quyền nhạy cảm | MFA mạnh + PAM/JIT theo chính sách | Kiểm tra xác thực tăng cường. |
| **service-workload** | Workload hợp lệ | Workload federation/mTLS theo thiết kế | Kiểm tra danh tính máy, không dùng luồng đăng nhập người. |

Tạo thêm các trường hợp **cùng tên khác người, email thay đổi, tenant khác nhau, liên kết account không chắc chắn, token cũ và phiên ở nhiều thiết bị**. Cần bảo đảm test không vô tình gửi thông báo tới nhân viên thật hoặc làm thay đổi account của người dùng sản xuất.

### Kiểm soát fixture

1. Cấp tài khoản test qua cùng kênh provisioning dự kiến, giữ identityId và local account ID.
2. Tạo **authenticator test** bằng API/phương thức được IdP hỗ trợ; không đưa seed OTP hoặc private key vào mã nguồn.
3. Dùng clock giả hoặc khả năng điều khiển thời gian của hệ thống thử nghiệm cho mốc hết hạn; tránh test phụ thuộc ngủ chờ kéo dài.
4. Tách issuer, audience, client ID, redirect URI, certificate và key dùng cho test khỏi production.
5. Cleanup tài khoản, phiên và credential sau chạy; lưu log tối thiểu đã che bí mật.
6. Đảm bảo tính lặp lại: kết quả test không lệ thuộc phiên của lần chạy trước.

**Không chạy thử brute-force, enumeration hoặc thu hồi account thật trên môi trường sản xuất khi chưa có phạm vi kiểm thử, giới hạn lưu lượng và ủy quyền phù hợp.** Các case lạm dụng có thể dùng mô phỏng có kiểm soát trong staging.

## 4. Ma trận kiểm thử đăng nhập cơ bản

### Thành công và từ chối

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| AUTH-01 | User ACTIVE nhập đúng credential và hoàn tất yếu tố bắt buộc. | Xác thực thành công; subject đúng; phiên có thuộc tính phù hợp. |
| AUTH-02 | Sai mật khẩu hoặc sai bằng chứng xác thực. | Từ chối, không tạo phiên hợp lệ, không tiết lộ bí mật. |
| AUTH-03 | User không tồn tại. | Từ chối và không giúp suy ra dễ dàng User có tồn tại hay không. |
| AUTH-04 | User bị SUSPENDED/TERMINATED thử đăng nhập mới. | Từ chối theo chính sách ở tất cả kênh bị quản lý. |
| AUTH-05 | User chưa đến ngày kích hoạt thử dùng account chuẩn bị sẵn. | Không truy cập được tài nguyên nghiệp vụ; enrollment ngoại lệ nếu được cho phép vẫn bị giới hạn. |
| AUTH-06 | Credential đã bị thu hồi hoặc yếu tố MFA đã bị hủy. | Không thể sử dụng lại. |
| AUTH-07 | Đăng nhập với thuộc tính tenant/issuer sai. | Không chuyển thành session của tenant khác. |
| AUTH-08 | Hai lần đăng nhập đồng thời trên thiết bị khác nhau. | Theo chính sách session concurrency, không lẫn subject và quyền. |
| AUTH-09 | User đổi mật khẩu hoặc authenticator. | Xử lý session cũ và step-up theo chính sách, không âm thầm hạ mức bảo đảm. |
| AUTH-10 | Mất kết nối trong lúc xác thực. | Không tạo phiên “nửa thành công”; retry an toàn. |

### Các thuộc tính của một kết quả đạt

Không chỉ kiểm tra mã HTTP:

- **Subject:** đúng ID bất biến, issuer, tenant và mapping với identity IAM.
- **Authentication context:** đáp ứng phương thức và mức bảo đảm chính sách yêu cầu.
- **Session:** được tạo sau xác thực hợp lệ, thời hạn và cơ chế cookie/token đúng.
- **Authorization boundary:** chỉ truy cập được tài nguyên trong phạm vi quyền cho phép.
- **Audit:** lưu loại kết quả và mã correlation, không lộ credential hoặc token nguyên vẹn.
- **Failed attempt:** không phát hành hoặc để lộ một phiên/token có thể sử dụng.

Với đăng nhập thất bại, test phải kiểm tra **không có hiệu ứng phụ không hợp lệ**: không tự động mở khóa account, không nâng quyền, không tạo refresh token hoặc tiếp tục một session đã bị thu hồi.

## 5. Kiểm thử MFA, passkey và xác thực tăng cường

**MFA (multi-factor authentication)** sử dụng ít nhất hai yếu tố xác thực độc lập theo chính sách; việc lặp lại hai lần cùng một loại yếu tố không tự tạo thành MFA mạnh. Cần phân biệt **MFA có chống phishing** (ví dụ WebAuthn/FIDO2 được triển khai đúng) với OTP hoặc push có thể bị lừa chuyển tiếp trong một số kịch bản.

### Ma trận MFA

| Kịch bản | Điều kiểm thử |
| --- | --- |
| Credential chính đúng, MFA đúng | Chỉ hoàn thành xác thực khi đủ yếu tố theo chính sách. |
| Credential chính đúng, OTP sai | Không có session/step-up thành công; kiểm soát thử lặp. |
| OTP hết hạn hoặc dùng lại | Bị từ chối theo chính sách và cơ chế chống replay. |
| Challenge bị gửi hai lần / đổi thứ tự | Không chấp nhận trạng thái cũ hoặc ghép nhầm phiên. |
| Push bị từ chối hoặc timeout | Không tự coi là chấp thuận. |
| User từ chối MFA rồi yêu cầu lại | Thử lại theo rate limit và state machine hợp lệ. |
| Không có yếu tố bắt buộc | Buộc enrollment hoặc quy trình thay thế được kiểm soát, không bỏ qua bảo mật. |
| Đăng ký MFA mới | Xác minh quyền kiểm soát danh tính hiện tại; không thêm yếu tố cho account khác. |
| Xóa yếu tố cuối cùng | Kiểm tra phê duyệt/recovery và cảnh báo theo chính sách. |
| Quyền đặc quyền yêu cầu step-up | Phiên mức thấp không thực hiện được hành động nhạy cảm. |

### Passkey/WebAuthn

Với passkey hoặc authenticator WebAuthn, nên kiểm thử:

1. Registration challenge được tạo an toàn, gắn với yêu cầu và không được tái sử dụng tùy tiện.
2. **Origin** và **Relying Party ID (RP ID)** khớp ứng dụng; không chấp nhận đăng ký hoặc assertion từ origin không được phép.
3. Assertion phải liên kết với challenge đúng phiên/chủ thể, credential public key được đăng ký cho account tương ứng và chữ ký hợp lệ.
4. **User presence/user verification** được kiểm tra theo yêu cầu của chính sách và cờ từ authenticator.
5. Credential bị xóa/thu hồi không còn đăng nhập được, kể cả khi thông tin khác về User vẫn hợp lệ.
6. Luồng đồng bộ passkey giữa thiết bị và phục hồi tài khoản không vô tình bypass chính sách.
7. Với sign counter, hiểu rằng không phải mọi authenticator có bộ đếm tăng liên tục; không thiết kế test coi một giá trị counter bằng 0 luôn là dấu hiệu xâm nhập.

**Passkey không thay thế identity proofing.** Bằng chứng sở hữu credential chỉ có ý nghĩa khi credential được đăng ký với đúng identity và quá trình recovery được bảo vệ.

### Recovery và fallback

Khôi phục tài khoản là đường tấn công thường bị bỏ qua. Cần có test cho email/số điện thoại không còn quyền kiểm soát, mã recovery dùng lại, yêu cầu đổi yếu tố từ một session lạ, reset MFA khi User đang suspended và người quản trị hỗ trợ sai thẩm quyền.

Quy trình fallback cần **đạt mức bảo đảm theo chính sách** hoặc có ngoại lệ được quản trị, hết hạn và kiểm toán. Không cho phép trả lời câu hỏi bảo mật yếu hoặc một kênh email bị chiếm quyền tự động vô hiệu hóa mọi yêu cầu MFA của tài khoản đặc quyền.

## 6. Kiểm thử SSO qua OIDC và OAuth

**OIDC (OpenID Connect)** bổ sung lớp định danh/xác thực trên nền OAuth 2.0; **OAuth 2.0** tự nó chủ yếu giải quyết ủy quyền truy cập, không nên xem một access token tùy ý là bằng chứng đăng nhập của người dùng. Ứng dụng phải kiểm tra kết quả xác thực theo **giao thức và loại token dự kiến**.

### Luồng authorization code và PKCE

Với client phù hợp, thường kiểm thử **Authorization Code Flow với PKCE**, kiểm tra trạng thái chống CSRF, redirect URI đăng ký và việc xử lý code an toàn.

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as Ứng dụng / OIDC Client
    participant I as IdP / Authorization Server
    participant A as API
    U->>C: Bắt đầu đăng nhập
    C->>C: Tạo state, nonce (nếu dùng), PKCE verifier
    C->>I: Authorization request + code_challenge
    I->>U: Xác thực và MFA theo policy
    U-->>I: Hoàn tất
    I-->>C: Redirect + authorization code + state
    C->>C: Kiểm tra state và callback
    C->>I: Đổi code với code_verifier
    I-->>C: Token response
    C->>C: Validate ID token, issuer, audience, nonce (nếu dùng)
    C->>A: Gọi API với access token phù hợp
    A-->>C: Kiểm tra token và quyền tài nguyên
~~~

Các yếu tố cần kiểm thử theo cấu hình luồng:

| Thành phần | Positive test | Negative test |
| --- | --- | --- |
| **Redirect URI** | Chỉ callback đã đăng ký hợp lệ. | Redirect khác, open redirect hoặc đổi callback ngoài allowlist bị từ chối. |
| **state** | Kết quả callback được nối đúng với phiên yêu cầu. | State thiếu/sai/dùng lại không hoàn thành login. |
| **PKCE** | Code được đổi bằng đúng verifier. | Verifier sai không đổi được code; không chấp nhận hạ cấp không được phép. |
| **Authorization code** | Mã còn hạn, dùng một lần, đúng client/redirect binding. | Code hết hạn, dùng lại hoặc của client khác bị từ chối. |
| **ID token** | Chữ ký, issuer, audience, thời hạn và các claim cần thiết hợp lệ. | Token giả/sai issuer, audience, signature, exp/nbf bị từ chối. |
| **nonce khi được sử dụng** | Giá trị trong ID token khớp yêu cầu. | Nonce sai làm thất bại login tương ứng. |
| **Token type** | API dùng access token có audience/scope phù hợp. | Không chấp nhận ID token làm access token hoặc token của resource khác. |
| **Signing keys** | Key rotation theo JWKS/trust được xử lý đúng. | Không chấp nhận thuật toán ngoài allowlist, key không tin cậy. |
| **Token refresh** | Refresh đúng hạn theo policy. | Refresh token đã rút/không đúng client hoặc reuse bị xử lý theo thiết kế. |

**Không đặt mặc định rằng mọi claim hay cơ chế nonce là bắt buộc như nhau với tất cả luồng.** Cần đọc đặc tả giao thức, profile bảo mật và hợp đồng IdP–client đang sử dụng; test phải nhất quán với chính sách đã phê duyệt.

### Những test giao thức dễ bị quên

- Callback xuất hiện mà trước đó không có phiên đăng nhập tương ứng.
- Người dùng mở hai tab đăng nhập khác nhau rồi hoàn tất sai thứ tự.
- Một người đã đăng nhập IdP nhưng ứng dụng chuyển nhầm sang account được link bằng email cũ.
- JWKS key rotation diễn ra khi phiên đăng nhập đang hoạt động; client vẫn từ chối key lạ và hỗ trợ key hợp lệ.
- Đồng hồ lệch ngoài biên độ cho phép; token quá hạn không còn dùng được.
- Login thành công nhưng user bị disable trước khi đổi code; kết quả phải theo semantics và chính sách an ninh được xác định.
- Token còn hiệu lực nhưng user đổi tenant hoặc trạng thái Leaver; ứng dụng phải áp điều kiện quyền phù hợp ở nơi sử dụng.

## 7. Kiểm thử SSO qua SAML

Với **SAML 2.0**, Service Provider (SP) nhận assertion hoặc response từ Identity Provider (IdP). Test cần tập trung vào kiểm tra chữ ký và **ràng buộc assertion với đúng giao dịch, chủ thể, SP và khoảng hiệu lực**.

| Nội dung | Kỳ vọng kiểm thử |
| --- | --- |
| **Chữ ký** | Chỉ chấp nhận chữ ký hợp lệ trên đúng thành phần mà SP dựa vào; xử lý an toàn việc chọn phần tử đã ký. |
| **Issuer / trust metadata** | IdP phát hành đúng entityID và certificate/key tin cậy. |
| **Audience / recipient / destination** | Assertion dành cho đúng SP, endpoint và audience dự kiến. |
| **InResponseTo** | Khi dùng SP-initiated flow, response được ràng buộc với request phù hợp. |
| **NotBefore / NotOnOrAfter** | Không chấp nhận assertion ngoài khoảng hiệu lực, với clock skew được giới hạn. |
| **SubjectConfirmation** | Subject và recipient phù hợp với ngữ cảnh giao thức. |
| **Replay** | Assertion ID đã sử dụng không tạo thêm session không hợp lệ. |
| **RelayState** | Không tạo open redirect hoặc thay đổi đích ngoài phạm vi cho phép. |
| **Account mapping** | NameID/thuộc tính được ánh xạ tới đúng User trong tenant, không dựa duy nhất vào email có thể tái sử dụng. |
| **Certificate rotation** | Chuyển certificate theo metadata và chính sách trust mà không bỏ kiểm tra chữ ký. |

**IdP-initiated SSO** có thể không có request SP-initiated để so InResponseTo; nếu được tổ chức chấp nhận, phải có chính sách và biện pháp bảo vệ phù hợp với mô hình tin cậy đó. Không bỏ qua các kiểm tra xác thực assertion chỉ để làm một luồng IdP-initiated “chạy được”.

### Đừng nhầm SSO với quyền truy cập

Assertion xác thực hợp lệ không đồng nghĩa User có quyền vào mọi tài nguyên. Sau khi SP tạo phiên, ứng dụng phải tiếp tục kiểm tra tenant, trạng thái account và quyền nghiệp vụ. Trong bài kiểm thử, cần có case **SSO thành công nhưng thao tác nhạy cảm vẫn bị từ chối** do RBAC/ABAC.

## 8. Kiểm thử session, cookie, token và logout

Ứng dụng có thể sử dụng cookie session riêng, token của API hoặc cơ chế lưu phiên khác. Đây là nơi **Leaver** và các sự kiện bảo mật có thể bị bỏ sót.

### Vòng đời session

~~~text
UNAUTHENTICATED
    -> AUTHENTICATING
    -> AUTHENTICATED
    -> STEP_UP_REQUIRED (khi gặp tài nguyên nhạy cảm)
    -> AUTHENTICATED_WITH_REQUIRED_ASSURANCE
    -> EXPIRED / REVOKED / LOGGED_OUT
~~~

Đây là mô hình minh họa, không phải trạng thái chuẩn áp đặt cho mọi IdP. Các bước chuyển phải có kiểm soát; đặc biệt, từ **REVOKED** không được chuyển lại thành authenticated bằng cách phát lại cookie hoặc yêu cầu refresh cũ.

### Ma trận phiên

| Test | Điều cần quan sát |
| --- | --- |
| Đăng nhập mới | Session ID được thiết lập an toàn; không kế thừa phiên chưa xác thực gây fixation. |
| Cookie web | Secure, HttpOnly, SameSite phù hợp với kiến trúc và các kênh CSRF được bảo vệ. |
| Idle timeout | Phiên không hoạt động quá thời hạn bị xử lý theo chính sách. |
| Absolute lifetime | Không kéo dài vô hạn bằng hoạt động liên tục nếu chính sách có hạn tuyệt đối. |
| Logout | Session của ứng dụng bị hủy; refresh token/session IdP được xử lý theo hỗ trợ và kỳ vọng đã định. |
| Logout một thiết bị / mọi thiết bị | Phạm vi logout đúng tuyên bố sản phẩm. |
| Password/MFA reset | Quy tắc vô hiệu hóa phiên cũ và step-up được thực thi. |
| Refresh token rotation | Token cũ/reuse được phát hiện hoặc từ chối theo cơ chế đã triển khai. |
| Access token hết hạn | API không chấp nhận token đã hết hạn. |
| Token khác audience/scope | Không truy cập được resource khác hoặc vượt phạm vi. |
| CORS/CSRF trên browser | Endpoint trạng thái có bảo vệ phù hợp, không mở credentialed cross-origin tùy tiện. |
| Session tại nhiều ứng dụng SSO | Không suy ra logout toàn hệ sinh thái nếu từng ứng dụng chưa có cơ chế tương ứng. |

### Revocation không phải lúc nào cũng tức thời

**Refresh token** thường có thể bị từ chối khi xin token mới; điều đó không nhất thiết hủy **access token tự chứa đã cấp và còn hạn**. Với API kiểm tra token offline, việc đổi trạng thái User tại IdP có thể chưa tác động ngay tới token cũ.

Thiết kế test cần xác định:

1. API xác minh token offline hay sử dụng introspection/trạng thái trung tâm?
2. Token lifetime và biên chấp nhận clock skew là bao nhiêu?
3. Session cục bộ có bị xóa khi account tại IdP bị vô hiệu hóa không?
4. Có cơ chế thu hồi/denylist hoặc policy lookup tại thời điểm sử dụng không?
5. Nếu không thể revoke tức thời, tổ chức có kiểm soát bù và giới hạn tồn dư nào?

Không đánh dấu “REVOKED_VERIFIED” cho mọi đường truy cập chỉ vì một lời gọi logout hoặc SCIM update trả 200.

## 9. Kiểm thử authentication gắn với Joiner–Mover–Leaver

Đây là trọng tâm đặc thù của hệ thống **Identity Lifecycle**: cùng một User và credential có thể đổi trạng thái truy cập theo thời gian mà không cần đổi danh tính nghiệp vụ.

### Ma trận theo sự kiện

| Sự kiện | Chuẩn bị test | Kỳ vọng đối với authentication |
| --- | --- | --- |
| **Joiner — chưa đến ngày** | Identity/IdP User đã được tạo sẵn, account chưa kích hoạt. | Không đăng nhập được vào tài nguyên nghiệp vụ; luồng enrollment có giới hạn nếu được cho phép. |
| **Joiner — đủ điều kiện** | Ngày hiệu lực đến, proofing và MFA hợp lệ, policy đạt. | Có thể đăng nhập; subject đúng; ứng dụng kiểm tra quyền đúng phạm vi. |
| **Joiner — thiếu proofing** | Nguồn HR hợp lệ nhưng bằng chứng định danh chưa đạt. | Không mở những kênh yêu cầu proofing theo chính sách; không tự vượt qua kiểm soát vì account đã tạo. |
| **Mover — đổi bộ phận** | Đăng nhập trước và sau chuyển phòng ban. | Authentication vẫn có thể hợp lệ, nhưng quyền cũ và claims/ABAC phải phản ánh chính sách mới. |
| **Mover — nâng đặc quyền** | User chuyển sang vai trò nhạy cảm. | Yêu cầu step-up/PAM nếu chính sách đòi; session cũ không tự đủ điều kiện. |
| **Suspension** | User có session và refresh token trước khi bị khóa tạm. | Đăng nhập mới bị chặn; phiên cũ được xử lý theo giới hạn và biện pháp thu hồi được cam kết. |
| **Leaver — hiệu lực ngay** | User đăng nhập trên hai trình duyệt, có API token và app local session. | Chặn đăng nhập mới; rút hoặc hạn chế phiên/token/credential theo chính sách từng đích; không mở lại bởi retry cũ. |
| **Leaver — theo lịch** | Account đã pre-provision, có scheduled task. | Đúng thời điểm hiệu lực, không sớm và không muộn ngoài ngưỡng cho phép. |
| **Rehire** | Identity cũ disabled; hồ sơ HR mới đã được xác minh. | Không tự hồi sinh credential/session/quyền cũ; chỉ kích hoạt theo quy trình hiện tại. |
| **Contractor expiry** | Account còn trong IdP và SaaS sau hạn hợp đồng. | Cấm truy cập sau thời điểm hết hiệu lực, kể cả kênh cục bộ không qua SSO. |

### Một quy trình test Leaver xuyên hệ thống

~~~mermaid
sequenceDiagram
    participant HR as HR / nguồn có thẩm quyền
    participant IAM as IAM / Leaver Workflow
    participant IDP as IdP
    participant APP as SaaS / Application
    participant TEST as Test Harness
    TEST->>TEST: Tạo session, refresh token và account test trước Leaver
    HR->>IAM: Leaver + effectiveAt + version
    IAM->>IDP: Disable User / revoke theo hỗ trợ
    IAM->>APP: SCIM/API disable & revoke
    IDP-->>IAM: Kết quả
    APP-->>IAM: Kết quả
    TEST->>IDP: Thử đăng nhập mới
    IDP-->>TEST: Từ chối
    TEST->>APP: Thử session/token cũ theo phạm vi test
    APP-->>TEST: Từ chối hoặc bị giới hạn theo chính sách
    TEST->>IAM: Đối chiếu trạng thái và audit từng đích
~~~

Tùy hệ thống, access token còn hạn có thể không bị vô hiệu hóa ngay; test phải **đo và báo cáo thời gian tồn dư thực tế** thay vì giả định hoàn toàn không có. Với môi trường có yêu cầu thu hồi tức thời, thiết kế phải có cơ chế hỗ trợ yêu cầu ấy tại điểm sử dụng.

### Kiểm thử Mover không chỉ là đăng nhập

Khi một User chuyển phòng ban, một test chỉ xác nhận “login vẫn thành công” gần như không đủ giá trị bảo mật. Phải thêm:

- Token/claim hoặc dữ liệu profile đã được cập nhật theo cơ chế và thời hạn thiết kế.
- Role hoặc group cũ đã bị loại bỏ khỏi hệ thống thực thi quyền.
- Phiên cũ không còn được dùng để thực hiện thao tác chỉ dành cho vai trò đã mất.
- Quyền mới được cấp sau phê duyệt, không vì Mover mà tự tăng privilege.
- Các đường truy cập trực tiếp ngoài SSO được đối soát độc lập.

## 10. Kiểm thử negative, abuse case và account recovery

Negative test phải có chủ đích, giới hạn và dựa trên threat model. Một số lớp quan trọng:

| Lớp | Tình huống âm | Kỳ vọng |
| --- | --- | --- |
| **Account enumeration** | User hợp lệ và không hợp lệ cùng thao tác recovery. | Không rò rỉ tình trạng tài khoản qua thông báo không cần thiết; có rate limit và giám sát. |
| **Brute force / stuffing** | Nhiều lần sai có kiểm soát. | Cơ chế chống lạm dụng và cảnh báo, không lockout vô hạn bị lợi dụng để DoS. |
| **Password reset** | Link/token hết hạn hoặc đã dùng. | Không sử dụng lại được; reset được ràng buộc đúng User. |
| **MFA reset** | Kẻ khác có session mức thấp yêu cầu xóa yếu tố. | Step-up/recovery và phê duyệt thích hợp; ghi audit. |
| **Callback tampering** | OIDC state/sig/nonce bất hợp lệ; SAML audience sai. | Không tạo session; không chấp nhận fallback không an toàn. |
| **Cross-tenant login** | Session/token tenant A dùng ở tenant B. | Bị từ chối hoặc cách ly đúng tenant. |
| **Replay** | Sử dụng lại code, assertion hoặc challenge đã tiêu thụ. | Bị từ chối đúng hạn và scope. |
| **Session fixation** | Phiên chưa xác thực được gắn cố định rồi login. | Không bị tái sử dụng theo cách cho kẻ khác chiếm phiên. |
| **Local bypass** | SSO bị khóa nhưng local password/PAT còn hoạt động. | Được xử lý theo phạm vi Leaver và quản lý credential tương ứng. |
| **Fallback downgrade** | Chuyển từ phương thức mạnh sang phương thức yếu không được duyệt. | Bị chặn hoặc qua quy trình ngoại lệ có kiểm toán. |
| **Device loss** | Thiết bị có passkey/token bị báo mất. | Thu hồi/yêu cầu enrollment lại theo chính sách; theo dõi phiên còn tồn. |

Các test tấn công cần **dùng tài khoản kiểm thử và giới hạn lưu lượng**. Không cần thử phá mật khẩu thật hay thu thập token của người dùng để xác minh sự tồn tại của kiểm soát.

### Recovery là điểm nối giữa proofing và authentication

Nếu người dùng mất toàn bộ yếu tố MFA, quy trình recovery phải tái thiết lập niềm tin rằng **người yêu cầu chính là chủ account hợp lệ**. Tùy rủi ro, có thể yêu cầu identity proofing hoặc xác minh bổ sung.

Kiểm thử phải bao phủ cả **đường người dùng thành công hợp lệ** (không tạo rào cản vô lý) và **đường mạo danh thất bại**. Khi recovery hoàn tất, hệ thống phải xem xét hiệu lực các authenticator và phiên cũ theo chính sách, không âm thầm duy trì bí mật bị nghi lộ.

## 11. Tổ chức kiểm thử tự động

Một chiến lược hiệu quả dùng nhiều tầng. Mỗi tầng xác minh một hợp đồng, không cố thực hiện toàn bộ kiểm soát bằng một bài test UI cuối cùng.

| Tầng | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Unit** | Hàm xử lý state, policy, thời hạn, mapping và token validation. | Token sai issuer/audience bị từ chối; trạng thái Leaver chặn activation. |
| **Component/contract** | Hợp đồng giữa ứng dụng với IdP/SCIM/connector. | Callback state/nonce, SCIM active mapping, lỗi timeout. |
| **Integration** | Giao tiếp với hệ thống test thực và database/queue. | Đăng nhập OIDC, chuyển nhóm, readback user state. |
| **End-to-end** | Hành trình thực của chủ thể từ browser tới ứng dụng. | Joiner đủ điều kiện → MFA → SSO → resource → logout. |
| **Security regression** | Những lỗi đã phát hiện không tái xuất hiện. | Replay SAML, token substitution, local auth bypass. |
| **Resilience / chaos** | An toàn khi lỗi mạng, retry, key rotation, sự kiện trễ. | Leaver cắt ngang job cấp quyền hoặc IdP tạm lỗi. |

### Ví dụ test case đặc tả theo Given–When–Then

~~~gherkin
Feature: Authentication follows IAM lifecycle

  Scenario: Pending joiner cannot access business application
    Given identity "ID-101" is pending activation
    And the IdP account is pre-provisioned
    When the user attempts to sign in to a business application
    Then authentication is denied according to policy
    And no authorized application session is created
    And the attempt is audited without credential disclosure

  Scenario: Leaver cannot reuse an old refresh token
    Given identity "ID-102" has an existing test refresh token
    And a valid Leaver event becomes effective
    When the test client requests token renewal
    Then the request is denied by the revocation policy
    And a stale Joiner retry cannot reactivate the account
~~~

Đây là ví dụ **đặc tả hành vi**, không khẳng định mọi IdP có cùng endpoint hoặc khả năng thu hồi token. Khi triển khai, cần điều chỉnh kỳ vọng theo hợp đồng sản phẩm và mức rủi ro đã xác định.

### Pseudocode kiểm thử liên thông

~~~text
test("Leaver blocks new sign-in and limits existing access"):
    identity = createSyntheticActiveIdentity()
    session = authenticateAndCaptureTestSession(identity)
    assert session.subject == identity.id

    event = emitAuthoritativeLeaver(
        identity.sourceKey,
        effectiveAt = controlledClock.now,
        version = 12
    )
    waitForWorkflowState(event, "REVOKING_ACCESS")

    newLogin = attemptNewLogin(identity)
    assert newLogin.denied

    refresh = attemptTestTokenRefresh(session.refreshToken)
    assert refresh.deniedWhenRevocationRequired

    observed = readBackTargetAccountAndRoles(identity)
    assert observed.matchesCurrentLeaverPolicy

    legacy = probePermittedTestResourceWithOldSession(session)
    assert legacy.withinDocumentedRevocationBoundary

    assert auditContainsCorrelationId(event.id)
    cleanupSyntheticIdentity(identity)
~~~

Không tự biến điều kiện **withinDocumentedRevocationBoundary** thành một phép bỏ qua: test phải đo được giới hạn, lưu bằng chứng và fail nếu đường truy cập tồn dư vượt mức chính sách. Nếu chính sách yêu cầu chặn ngay thì assertion phải thể hiện rõ hành vi ấy.

### Thiết kế assertion không mong manh

- Kiểm tra **hành vi bảo mật**, không chỉ text giao diện hoặc thứ tự DOM.
- Dùng polling có giới hạn theo trạng thái hệ thống thay vì chờ một số giây cố định.
- Đặt trần thời gian cho convergence của IdP/SCIM, phân biệt **pending** và **failed**.
- Không hardcode token, secret hoặc credential vào repository.
- Khi test chạy song song, tách account, tenant, request ID và session giữa các test.
- Kiểm tra cả response và **absence of side effects** sau thao tác bị từ chối.
- Lưu bằng chứng audit đã lọc thông tin nhạy cảm để điều tra test fail.

## 12. Kiểm thử lỗi, race condition và khả năng phục hồi

Vòng đời IAM là hệ thống phân tán: HR phát sự kiện, IAM lập lịch, IdP thay đổi trạng thái, SCIM gửi lệnh và ứng dụng có cache/phiên riêng. Vì vậy test phải bao phủ **những hành vi sai do thứ tự sự kiện**, không chỉ đầu vào sai.

### Các kịch bản nên đưa vào fault injection

1. **Joiner đang provisioning, Leaver xuất hiện:** job Joiner cũ không được bật lại account.
2. **Mover đổi vai trò trong khi refresh token:** app không giữ quyền cũ trái chính sách; kiểm tra claims, session và policy source.
3. **IdP trả timeout sau khi thực sự xử lý:** retry không tạo account, token hoặc session trùng ngoài thiết kế.
4. **SCIM báo thành công nhưng ứng dụng chưa cập nhật:** trạng thái phải PENDING_VERIFICATION hoặc PARTIAL_FAILURE, không tự VERIFIED.
5. **Một ứng dụng ngoài SSO vẫn còn credential cục bộ:** test Leaver phải phát hiện đường này.
6. **Hai thiết bị có session cũ và mới:** logout/disable áp dụng đúng phạm vi theo chính sách.
7. **Key rotation giữa luồng login:** client xử lý key tin cậy mới mà không chấp nhận key giả.
8. **Clock skew vượt ngưỡng:** token/assertion hết hạn hoặc chưa có hiệu lực bị từ chối.
9. **Message lặp hoặc đảo thứ tự version:** không thay lifecycle state mới bằng trạng thái cũ.
10. **Ứng dụng đích không thể liên lạc:** có cảnh báo, retry giới hạn và kiểm soát bù; không âm thầm bỏ qua Leaver.

### Mô hình kiểm tra thứ tự sự kiện

~~~text
sourceVersion = 41 : JOINER, account ready
sourceVersion = 42 : MOVER, revoke old group
sourceVersion = 43 : LEAVER, disable account

Network reorders messages:
    receive(43) -> apply Leaver
    receive(41) -> must NOT re-enable
    receive(42) -> must NOT grant

expected:
    lifecycle = TERMINATED
    login.new = DENIED
    access = REVOKED or risk-tracked within enforced bounds
~~~

**Không chỉ kiểm tra trạng thái IAM nội bộ**. Phải đọc lại account ở IdP và ứng dụng, thử các kênh được phép trong môi trường test và xác định thực tế quyền đã được thu hồi tới mức nào.

## 13. Kiểm thử danh tính máy và tài khoản đặc quyền

Không phải mọi principal đều là một người đăng nhập qua browser.

### Service account và workload identity

Đối với hệ thống sử dụng **OAuth client credentials, workload identity federation, mTLS hoặc chứng chỉ**, cần kiểm thử:

| Tình huống | Kỳ vọng |
| --- | --- |
| Workload hợp lệ | Có thể lấy token/chứng thực với audience, scope và môi trường được duyệt. |
| Sai issuer/audience hoặc trust subject | Từ chối, không ánh xạ sang service principal khác. |
| Credential/secret hết hạn hoặc bị thu hồi | Không tiếp tục xác thực qua đường cũ. |
| Workload bị decommission | Không thể lấy quyền mới; đường còn tồn được xử lý theo giới hạn chính sách. |
| Owner của service nghỉ việc | Không tự xóa workload hợp lệ; credential cá nhân bị loại khỏi trust, owner được chuyển theo quy trình. |
| Workload staging dùng token production | Bị từ chối theo trust boundary và scope. |

**Không áp identity proofing bằng giấy tờ cho máy.** Thay vào đó, kiểm tra nguồn triển khai, owner, thuộc tính workload và mối quan hệ tin cậy của credential.

### Privileged account và PAM

Nếu một người có cả tài khoản thường và tài khoản admin, test phải bao phủ **cả hai** khi Leaver. Quyền đặc biệt cần kiểm tra:

- Authenticator và step-up đáp ứng chính sách cho phiên đặc quyền.
- Quyền JIT có hạn không biến thành vai trò thường trực.
- Session PAM có audit và cơ chế kết thúc như được cam kết.
- Sự kiện suspend/Leaver rút quyền đặc quyền cả khi account thường đã bị khóa.
- Break-glass được quản lý bởi chính sách riêng, người sở hữu và dấu vết kiểm toán; không thể biến thành lối bypass tùy tiện.

## 14. Quan sát, bằng chứng kiểm toán và chỉ số chất lượng

Một test bảo mật chỉ hữu ích khi biết **đã chứng minh điều gì, ở lớp nào và còn giới hạn gì**.

### Bản ghi test run tối thiểu

~~~json
{
  "runId": "auth-test-2041-v43",
  "caseId": "AUTH-JML-LEAVER-01",
  "identityId": "ID-TEST-2041",
  "sourceEvent": "LEAVER",
  "sourceVersion": 43,
  "target": "CRM",
  "expected": "DENY_NEW_LOGIN_AND_REVOKE_SESSION_AS_POLICY",
  "observed": "NEW_LOGIN_DENIED_SESSION_REVOKED",
  "observedAt": "2026-12-01T17:00:10+07:00",
  "result": "PASS",
  "auditCorrelationId": "corr-auth-9920"
}
~~~

Ví dụ này là schema nội bộ minh họa; không phải định dạng chuẩn của OIDC, SAML, SCIM hay một sản phẩm kiểm thử. Các thời điểm và ID là dữ liệu giả.

### Những gì nên log

| Dữ liệu | Mục đích |
| --- | --- |
| Case ID, run ID, build và policy version | Tái hiện đúng bản kiểm thử. |
| Identity/subject giả, issuer, tenant và target | Xác nhận đúng phạm vi và trust boundary. |
| Sự kiện JML, phiên bản, thời điểm hiệu lực | Chứng minh test dùng trạng thái vòng đời hiện hành. |
| Phương thức xác thực và loại session/token | Giải thích bối cảnh chấp nhận/từ chối. |
| Expected và observed behavior | Thấy rõ điểm lệch, tránh chỉ có PASS/FAIL chung. |
| Thời điểm kích hoạt, thu hồi và xác minh | Đo độ trễ thực tế và thời gian tồn dư. |
| Correlation ID, trạng thái từng IdP/app | Phục vụ truy vết lỗi phân tán. |
| Exception và giới hạn quan sát | Không tuyên bố bao phủ lớp chưa kiểm tra. |

**Không ghi mật khẩu, seed OTP, recovery code, private key, session cookie hoặc access/refresh token nguyên vẹn** vào log test, báo cáo CI hoặc ticket. Nếu cần chứng cứ, sử dụng reference có bảo vệ hoặc dữ liệu đã che phù hợp; hạn chế quyền truy cập và thời gian lưu giữ.

### Chỉ số quan trọng

- **Authentication success/failure theo phương thức** và môi trường.
- **MFA coverage** của tài khoản hoặc hành động thuộc phạm vi yêu cầu, không chỉ số người đã đăng ký.
- **Token/session revocation delay** từ sự kiện có hiệu lực đến khi quyền không còn sử dụng được.
- **Negative test rejection rate** cho callback sai, token giả, replay và recovery không hợp lệ.
- **Cross-tenant isolation pass rate** đối với User và API.
- **JML propagation latency** ở IdP và các ứng dụng đích.
- **Residual authentication paths** sau Leaver, gồm local login, PAT và session còn hiệu lực.
- **Flaky test rate** để nhận diện môi trường test thiếu ổn định, không che giấu lỗi thật.

Chỉ số cần phân nhóm theo mức rủi ro, hệ thống, phương thức và thời điểm. Không sử dụng tỷ lệ đăng nhập thành công cao làm bằng chứng hệ thống an toàn nếu các negative case quan trọng chưa được kiểm tra.

## 15. Tiêu chí hoàn thành kiểm thử authentication

Một bộ kiểm thử chỉ nên được kết luận **đạt trong phạm vi đã xác định** khi:

1. **Nguồn định danh và subject đúng:** các account được liên kết với đúng identity, issuer và tenant.
2. **Positive path hợp lệ:** người đủ điều kiện hoàn tất xác thực theo mức bảo đảm yêu cầu và có thể sử dụng quyền được phê duyệt.
3. **Negative path bị từ chối:** sai credential/MFA, callback, token, audience, session và replay không tạo truy cập được phép.
4. **MFA và recovery an toàn:** không có đường hạ cấp ngoài chính sách; enrollment, reset và revoke có xác minh và audit.
5. **Session/token đúng vòng đời:** thời hạn, logout, refresh, thu hồi và key rotation được kiểm tra theo hợp đồng hệ thống.
6. **Joiner–Mover–Leaver đạt chính sách:** không đăng nhập sớm, không dùng quyền cũ sai sau Mover, không tái kích hoạt quyền sau Leaver.
7. **Ứng dụng đích đã kiểm chứng:** IdP, SCIM và app local session/credential được kiểm tra riêng nơi cần; không suy ra thành công toàn cục từ một API.
8. **Lỗi phân tán được xử lý:** retry, eventual consistency, timeout, phiên bản sự kiện, partial failure và phương án kiểm soát bù có test.
9. **Bằng chứng đủ nhưng an toàn:** log, correlation ID, phạm vi kiểm thử, kết quả thực tế và giới hạn được lưu mà không lộ secret.
10. **Các lỗi nghiêm trọng đã xử lý:** không xuất bản hoặc triển khai khi lỗi xác thực có khả năng cấp truy cập trái chính sách vẫn chưa được kiểm soát theo quy trình quản lý rủi ro.

Trong hệ thống phụ thuộc nhà cung cấp, nếu không có khả năng quan sát một lớp (ví dụ ứng dụng không cung cấp API revoke session), phải **ghi rõ giới hạn và rủi ro còn lại**. Không được gắn kết quả VERIFIED tuyệt đối cho điều chưa thể chứng minh.

## 16. Tình huống thực hành

### Tình huống A — Joiner có account nhưng chưa đến ngày kích hoạt

**Bối cảnh:** Công ty đã pre-provision User tại IdP và CRM bảy ngày trước khi nhân viên An đi làm. An đăng nhập thành công SSO và CRM hiển thị dashboard chứa dữ liệu khách hàng.

**Câu hỏi:** Test nào phát hiện vấn đề và sửa ở đâu?

**Gợi ý:** Tạo case AUTH-JML-PREACTIVATION: kiểm tra đăng nhập và truy cập nghiệp vụ trước thời điểm HR cho phép; xác định quyền phát sinh từ group, SCIM active, local account hay chính sách ứng dụng. Cần cơ chế hạn chế thật sự tại điểm truy cập, không chỉ trạng thái PENDING trong IAM.

### Tình huống B — SSO token sai audience được chấp nhận

**Bối cảnh:** API thanh toán nhận một token hợp lệ về chữ ký nhưng được phát hành cho một ứng dụng khác.

**Câu hỏi:** Vì sao token vẫn phải bị từ chối?

**Gợi ý:** Chữ ký chỉ cho biết token được một bên phát hành đáng tin ký; API còn phải kiểm tra issuer, **audience**, thời hạn, loại token, scope/quyền và policy. Một access token dành cho tài nguyên A không mặc nhiên hợp lệ ở B.

### Tình huống C — Leaver đã khóa IdP nhưng còn session CRM

**Bối cảnh:** HR phát Leaver hiệu lực 17:00. IdP từ chối đăng nhập mới, nhưng cookie CRM từ 16:45 vẫn dùng được đến 18:00.

**Câu hỏi:** Có thể kết luận Leaver hoàn tất không?

**Gợi ý:** Chưa nếu chính sách yêu cầu rút session sớm hơn. Kiểm tra logout/session revocation tại CRM, đo giới hạn tồn dư, thử đường tài khoản cục bộ và token riêng; báo trạng thái theo từng đích.

### Tình huống D — Mover giữ claim phòng ban cũ

**Bối cảnh:** An chuyển sang Finance lúc 08:00 nhưng token/session của ứng dụng báo department=Support; app dùng giá trị này để cho xem ticket.

**Câu hỏi:** Login còn hợp lệ có đồng nghĩa quyền đã đúng không?

**Gợi ý:** Không. Xác minh độ mới của claim/session, mapping HR–IdP–app, cơ chế cập nhật quyền RBAC/ABAC và cách ứng dụng chặn truy cập cũ. Cần test quyền hiệu lực sau Mover, không chỉ test login.

### Tình huống E — Khôi phục MFA bằng email bị chiếm quyền

**Bối cảnh:** Người lạ kiểm soát email liên hệ của User và yêu cầu bỏ MFA cho tài khoản quản trị.

**Câu hỏi:** Quy trình recovery phải bảo vệ điều gì?

**Gợi ý:** Không cho phép một kênh yếu thay thế toàn bộ yêu cầu tin cậy. Áp step-up, xác minh chủ thể, phê duyệt thủ công hoặc re-proofing theo rủi ro, giới hạn quyền và thông báo/audit phù hợp.

### Tình huống F — Retry Joiner sau Leaver

**Bối cảnh:** Job tạo account bị timeout, trong lúc HR phát Leaver. Scheduler chạy lại job cũ, ứng dụng mở lại account đã bị khóa.

**Câu hỏi:** Kiểm thử resilience cần khẳng định điều gì?

**Gợi ý:** Job dùng sourceVersion và lifecycle state hiện hành, không cho phép thao tác cũ cấp quyền sau Leaver; đối soát lại IdP và ứng dụng, kiểm tra không còn đường đăng nhập được phép.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao kiểm thử authentication không thể chỉ dựa trên việc biểu mẫu trả về “đăng nhập thành công”?**

Vì còn cần xác minh subject, issuer, mức bảo đảm, token/session, tenant, quyền sử dụng và hiệu lực của sự kiện vòng đời.

**2. MFA đăng nhập thành công có chứng minh identity proofing ban đầu đúng người không?**

Không. MFA chứng minh quyền kiểm soát authenticator theo quy trình; proofing xác lập liên kết giữa danh tính khai báo và người thực.

**3. OAuth access token có thể được ứng dụng dùng thay ID token để xác nhận danh tính người dùng theo cách tùy ý không?**

Không nên. Dùng đúng loại token và hợp đồng giao thức; OIDC cung cấp quy tắc ID token cho xác thực, API phải kiểm tra access token dành cho chính mình.

**4. Một SAML assertion có chữ ký hợp lệ nhưng audience dành cho SP khác thì sao?**

Phải bị từ chối vì chưa thỏa ràng buộc đối tượng nhận; còn cần kiểm tra issuer, recipient, thời hạn và các điều kiện khác.

**5. Vì sao disable User ở IdP chưa chắc làm mọi session ứng dụng mất hiệu lực ngay?**

Vì ứng dụng có thể giữ cookie/session riêng hoặc chấp nhận access token còn hạn theo kiểm tra offline; cần cơ chế thu hồi hoặc giới hạn tồn dư được xác minh.

**6. Khi Mover, đăng nhập tiếp tục thành công nhưng vai trò cũ vẫn dùng được; test nào đã thiếu?**

Test authorization và hiệu lực quyền sau Mover, bao gồm RBAC/ABAC, token/claim cũ và quyền trực tiếp tại ứng dụng.

**7. Khi cùng Leaver event được gửi hai lần, có cần tạo hai yêu cầu thu hồi độc lập không?**

Không. Cần idempotency, kiểm tra trạng thái hiện hành và readback; thao tác lặp phải an toàn.

**8. Một service account có cần test reset mật khẩu bằng giao diện nhân viên không?**

Không mặc định. Cần test phương thức xác thực máy như workload federation, secret/chứng chỉ và vòng đời owner, quyền, credential theo thiết kế.

## Ghi nhớ

- **Kiểm thử authentication** phải chứng minh đúng chủ thể, đúng phương thức, đúng điều kiện và **từ chối được đường không hợp lệ**; test login success đơn lẻ là chưa đủ.
- **MFA, passkey/WebAuthn, OIDC/SAML, session, token và recovery** đều cần positive/negative test cùng kiểm soát bảo mật thực tế.
- **IdP và SSO** quản lý xác thực liên thông; **SCIM** hỗ trợ provisioning; **RBAC/ABAC** kiểm tra quyền. Thành công ở một lớp không thay thế kiểm thử các lớp khác.
- **Joiner–Mover–Leaver** phải được thử xuyên suốt: không truy cập trước mốc, không giữ đặc quyền sai sau chuyển vai trò và không tái kích hoạt quyền sau Leaver.
- **Token còn hạn, session cục bộ, local account, PAT và credential máy** có thể là những đường truy cập riêng; cần test và xác minh giới hạn thu hồi từng đích.
- **Kiểm thử tự động, dữ liệu giả an toàn, fault injection, audit, readback và báo cáo giới hạn bằng chứng** giúp phát hiện lỗi xác thực có tác động tới vòng đời danh tính trước khi chúng trở thành sự cố.
