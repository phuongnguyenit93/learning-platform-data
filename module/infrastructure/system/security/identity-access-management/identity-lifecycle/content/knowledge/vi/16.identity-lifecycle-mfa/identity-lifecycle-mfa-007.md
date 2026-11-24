# Security key trong MFA và vòng đời danh tính IAM

## 1. Security key là gì?

**Security key (khóa bảo mật)** thường là một thiết bị xác thực phần cứng cầm tay hỗ trợ những giao thức như **FIDO2/WebAuthn** và, ở một số hệ thống cũ, **FIDO U2F**. Thiết bị có thể kết nối với máy tính hoặc điện thoại qua USB, NFC hoặc phương thức được nhà sản xuất hỗ trợ. Thay vì yêu cầu người dùng nhập một mã OTP có thể bị lừa lấy, security key sử dụng **cặp khóa mật mã bất đối xứng** để chứng minh quyền kiểm soát một credential đã đăng ký cho dịch vụ.

Ví dụ, nhân viên mở cổng đăng nhập công ty, nhập tên tài khoản rồi được yêu cầu xác thực bằng khóa bảo mật. Trình duyệt tương tác với security key; người dùng chạm vào thiết bị và, nếu chính sách yêu cầu, nhập PIN hoặc thực hiện xác minh sinh trắc học tại authenticator. Security key ký một thử thách do dịch vụ phát ra; máy chủ xác minh chữ ký bằng **khóa công khai đã lưu**. Khóa riêng không cần gửi tới máy chủ.

Chủ đề thuộc chương **MFA** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**: học quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)** từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi; liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư. Trong vòng đời này, security key là một **authenticator** phải được đăng ký, quản lý, khôi phục và gỡ bỏ đúng thời điểm, chứ không phải một vai trò hay quyền nghiệp vụ.

### Phân biệt các thành phần

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Identity** | Danh tính đang được quản lý | Employee ID do HRIS xác nhận |
| **Account** | Bản ghi đăng nhập ở IdP/ứng dụng | Tài khoản nhân viên trong IdP |
| **Authenticator** | Công cụ chứng minh quyền kiểm soát khi đăng nhập | Security key FIDO2, passkey |
| **Credential** | Vật liệu/định danh mật mã gắn với RP | Khóa công khai và credential ID đã đăng ký |
| **Authorization** | Quyết định được làm gì sau xác thực | Finance-Reader, quyền phê duyệt |
| **Session** | Trạng thái đăng nhập đã cấp | Cookie phiên hoặc token được cấp sau xác thực |

**Security key chứng minh quyền sử dụng một credential, không tự chứng minh danh tính pháp lý hoặc quyền truy cập của người cầm nó.** Identity proofing, authorization và kiểm soát phiên vẫn là các bước riêng biệt.

## 2. Vì sao security key hữu ích hơn nhiều phương thức MFA truyền thống?

Mật khẩu, mã OTP và thông báo push có thể bị lừa đưa vào trang giả hoặc bị tấn công theo những cách khác nhau. Với **WebAuthn**, credential được liên kết mật mã với **Relying Party (RP)**, và trình duyệt/authenticator tham gia kiểm tra ngữ cảnh nguồn gốc. Trang giả không thể đơn giản nhận một mã sáu chữ số rồi phát lại cho trang thật để hoàn thành WebAuthn cùng cách với OTP.

| Cơ chế | Người dùng thường thao tác | Khả năng chống phishing và giới hạn |
|---|---|---|
| **Mật khẩu** | Gõ bí mật | Có thể bị đánh cắp và dùng lại ở trang giả |
| **SMS/TOTP OTP** | Sao chép mã một lần | Mã có thể bị proxy hoặc người dùng cung cấp cho kẻ lừa đảo |
| **Push approval đơn giản** | Bấm chấp nhận | Có thể bị lừa phê duyệt hoặc chịu MFA fatigue nếu thiết kế yếu |
| **FIDO2 security key** | Chạm khóa, PIN/biometric khi yêu cầu | Chống phishing nhờ ràng buộc RP/origin; vẫn phải bảo vệ phiên và thiết bị |
| **Passkey đồng bộ** | Xác nhận bằng thiết bị hoặc trình quản lý thông tin xác thực | Có thể dùng WebAuthn chống phishing, nhưng đặc tính lưu/sync khóa khác security key gắn phần cứng |

Tính **phishing-resistant** của WebAuthn là ưu điểm trọng tâm, nhưng cần nhận định đúng phạm vi: nếu kẻ tấn công đã có **cookie phiên**, đã chiếm quyền endpoint hoặc lừa người dùng thực hiện một **giao dịch được phép**, chỉ sở hữu security key không đủ ngăn mọi thiệt hại. Cần kết hợp giám sát phiên, bảo vệ endpoint, RBAC/ABAC và chính sách ứng dụng.

## 3. Các thành phần trong kiến trúc FIDO2/WebAuthn

FIDO2 gồm những thành phần và giao thức cần phân biệt:

- **WebAuthn:** giao diện web/API và mô hình xác thực khóa công khai giữa trình duyệt hoặc client và **Relying Party (RP)**.
- **CTAP (Client to Authenticator Protocol):** giao thức để client giao tiếp với authenticator ngoài, chẳng hạn security key USB/NFC; FIDO2 thường gắn với **CTAP2**.
- **Authenticator:** thiết bị/phần mềm có khả năng tạo và sử dụng cặp khóa. Có **roaming authenticator** (security key rời) và **platform authenticator** tích hợp trong máy/điện thoại.
- **RP:** dịch vụ xác thực và giữ dữ liệu đăng ký cần thiết (credential ID, public key, chính sách).
- **IdP:** trong doanh nghiệp thường là RP đối với việc đăng nhập trung tâm; ứng dụng nghiệp vụ dùng SSO để nhận kết quả đăng nhập.

~~~mermaid
flowchart LR
    U[Người dùng] --> B[Trình duyệt / WebAuthn client]
    B <-->|CTAP2 khi áp dụng| K[Security key / authenticator]
    B <-->|WebAuthn ceremony| I[IdP hoặc ứng dụng RP]
    I --> V[Kho public key và trạng thái credential]
    I --> S[SSO / federation]
    S --> A[Ứng dụng doanh nghiệp]
    A --> P[RBAC / ABAC và điều kiện truy cập]
~~~

Sơ đồ thể hiện cấu trúc phổ biến, không bắt buộc mọi doanh nghiệp phải dùng một IdP. Một ứng dụng có thể trực tiếp triển khai WebAuthn. **SCIM** chủ yếu phục vụ provisioning người dùng/nhóm và không tự thực hiện đăng ký khóa FIDO2; đăng ký/gỡ khóa thường qua API hoặc quy trình của **RP/IdP**.

### RP ID và origin

**RP ID** thường là một miền hợp lệ của dịch vụ. Trình duyệt kiểm tra quan hệ giữa origin đang sử dụng và RP ID; server cũng phải kiểm tra **origin được phép** trong phản hồi. Credential được ràng buộc với RP ID, nên một trang phishing trên miền khác không thể tùy ý dùng credential đã đăng ký cho miền thật.

Triển khai không nên chỉ “nhìn thấy chữ ký hợp lệ” rồi cho phép đăng nhập. Phải kiểm tra **challenge, origin, RP ID hash, chữ ký, credential ID, user verification/presence, trạng thái credential** và các điều kiện protocol liên quan.

## 4. Bên trong security key lưu gì?

Khi đăng ký WebAuthn, authenticator tạo hoặc quản lý một **cặp khóa** gắn với RP. Trong mô hình key-bound thông thường, **private key được bảo vệ bởi authenticator** và **public key được RP lưu** để xác minh. Credential ID giúp RP nhận diện bản ghi tương ứng; chi tiết cách authenticator lưu nội bộ phụ thuộc sản phẩm và loại credential.

### Dữ liệu của từng phía

| Nơi lưu | Ví dụ dữ liệu | Nguyên tắc |
|---|---|---|
| **Security key** | Vật liệu khóa riêng và cơ chế bảo vệ, trạng thái PIN/biometric nếu hỗ trợ | Không xuất khóa riêng để đăng nhập qua kênh thông thường |
| **IdP/RP** | Credential ID, public key, RP ID, chủ thể gắn với khóa, trạng thái, chính sách | Khóa công khai không phải mật khẩu; metadata vẫn cần bảo vệ |
| **Trình duyệt/client** | Challenge, dữ liệu ceremony, thông tin origin | Không tự thay server validation |
| **IAM/IGA** | Trạng thái đăng ký, nguồn phê duyệt, owner, ticket, mốc lifecycle | Không lưu private key trong bảng nghiệp vụ |
| **Hệ thống kiểm toán** | Event ID, phương thức, thời điểm, kết quả, cảnh báo | Không ghi bí mật hay thông tin sinh trắc học thô |

Với security key vật lý, nhiều loại credential được thiết kế **gắn với authenticator** và private key không được trích xuất qua giao diện thông thường. Tuy nhiên không nên khẳng định mọi sản phẩm, mọi firmware hoặc mọi passkey đều có cùng tính chất. **Passkey đồng bộ** có thể có cơ chế sao lưu/đồng bộ khóa trong hệ sinh thái quản lý credential; nó không giống một credential buộc nằm trên đúng một security key vật lý.

### Credential ID, user handle và private key

Ba khái niệm khác nhau:

- **Credential ID:** định danh opaque để RP tìm public key và bản ghi credential.
- **User handle:** định danh tài khoản ở RP được dùng trong các luồng WebAuthn, đặc biệt với discoverable credential.
- **Private key:** bí mật mật mã mà authenticator sử dụng để ký thử thách, không nên được cung cấp cho RP.

Không được xem credential ID hay user handle là bí mật thay thế cho **chữ ký hợp lệ**; chỉ biết một ID không đủ để xác thực.

## 5. Quy trình đăng ký (registration/enrollment)

Đăng ký security key phải diễn ra **sau khi hệ thống đã có căn cứ liên kết khóa với đúng chủ thể**. Với tài khoản đang tồn tại, RP nên yêu cầu phiên đủ mạnh hoặc **step-up** trước khi cho thêm authenticator mới. Với Joiner, luồng enrollment cần kiểm soát lời mời, proofing và người nhận.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / WebAuthn client
    participant K as FIDO2 security key
    participant I as RP / IdP
    U->>I: Đăng ký authenticator
    I->>I: Kiểm tra identity, phiên, quyền thêm khóa
    I-->>B: Registration options + challenge + RP
    B->>K: Tạo credential cho RP
    K->>U: User presence / verification theo chính sách
    U-->>K: Chạm / nhập PIN hoặc biometric khi cần
    K-->>B: Attestation object + public key data
    B->>I: Registration response
    I->>I: Kiểm tra challenge, origin, RP ID và yêu cầu
    I->>I: Liên kết credential ID/public key với identity
    I-->>U: Xác nhận đã đăng ký và hướng dẫn backup
~~~

### Những bước quan trọng

1. **Xác định chủ thể:** account và quan hệ nhân sự phải được liên kết đúng, không dựa duy nhất vào tên hoặc email do người dùng tự khai.
2. **Xác thực quyền thêm khóa:** nếu đã có tài khoản, yêu cầu xác thực hiện tại theo chính sách rủi ro; không cho người chỉ có liên kết email không đủ bảo đảm tự thêm security key vào tài khoản đặc quyền.
3. **Server sinh challenge khó đoán:** challenge phải mới, gắn với phiên enrollment và có thời hạn hợp lý.
4. **Authenticator tạo credential:** khóa được tạo hoặc quản lý theo đặc tính thiết bị và yêu cầu WebAuthn.
5. **User presence / user verification:** tùy chính sách, người dùng chạm khóa và thực hiện PIN/sinh trắc tại authenticator.
6. **Server xác minh kết quả:** không chỉ tin cờ “success” từ client; phải kiểm tra cấu trúc, chữ ký attestation khi có yêu cầu, origin/RP/challenge và các chính sách cần thiết.
7. **Lưu liên kết:** credential ID, public key và metadata cần thiết được gắn với đúng identity, RP và trạng thái.
8. **Ghi kiểm toán:** sự kiện thêm khóa, thời gian, phiên, phê duyệt và thông báo cho chủ tài khoản; không lưu PIN/private key.
9. **Khuyến nghị dự phòng:** người dùng nên có phương án khôi phục được phê duyệt, thường là security key thứ hai hoặc phương thức dự phòng đủ mạnh theo chính sách.

**Không coi “đã đăng ký khóa” là kết luận nhân viên được cấp mọi quyền ứng dụng.** MFA enrollment, account provisioning, authorization và account activation là những trạng thái riêng.

## 6. Quy trình xác thực (authentication assertion)

Khi người dùng đăng nhập lại, RP tạo một **challenge mới**. Authenticator ký dữ liệu được WebAuthn quy định; RP kiểm tra chữ ký và các điều kiện. Không truyền một mật khẩu dùng chung hoặc một OTP để RP phát lại.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / WebAuthn client
    participant K as Security key
    participant I as RP / IdP
    U->>I: Yêu cầu đăng nhập
    I-->>B: Challenge + RP ID + policy
    B->>K: Yêu cầu assertion
    K->>U: Chạm / PIN / biometric nếu yêu cầu
    U-->>K: Xác nhận thao tác
    K-->>B: Authenticator data + signature
    B->>I: Assertion response
    I->>I: Xác minh credential, chữ ký, origin, RP ID
    I->>I: Kiểm tra challenge, UP/UV và trạng thái
    I-->>U: Tạo phiên nếu chính sách đạt
~~~

### Những kiểm tra phía server không được bỏ qua

- **Challenge:** đúng challenge vừa phát cho luồng này, còn hợp lệ và chưa bị dùng trái phép.
- **Origin:** đúng nguồn gốc trình duyệt/RP được phép; không tin giá trị client tự khai mà không kiểm tra.
- **RP ID hash:** khớp RP ID mong đợi.
- **Credential ID/public key:** thuộc tài khoản/quan hệ được phép và credential vẫn active.
- **Signature:** hợp lệ trên dữ liệu cần ký bằng public key đã đăng ký.
- **User Presence (UP):** yêu cầu có dấu hiệu tương tác người dùng khi chính sách đòi hỏi.
- **User Verification (UV):** yêu cầu và xác minh cờ UV khi chính sách đòi hỏi xác minh PIN/biometric hoặc phương thức tương đương.
- **Counter/metadata khi có:** xử lý tín hiệu rủi ro theo đặc tính authenticator; không giả định mọi key đều có sign counter tăng đáng tin cậy.

Một **chữ ký hợp lệ** chứng minh quyền kiểm soát credential tại thời điểm assertion, **không tự có nghĩa account vẫn là nhân viên active hoặc có quyền mở tài liệu mật**. Quyết định cấp phiên phải tiếp tục xét trạng thái lifecycle, risk policy và các điều kiện liên quan.

## 7. Chạm khóa, PIN và sinh trắc: một yếu tố hay nhiều yếu tố?

Security key không phải lúc nào cũng được sử dụng theo cùng một chế độ. Cần phân biệt:

| Cơ chế | Chứng minh điều gì? | Có đủ để gọi MFA không? |
|---|---|---|
| **User presence (UP): chạm khóa** | Có tương tác với authenticator tại thời điểm thao tác | **Không tự chứng minh hai yếu tố**; chạm không phải một yếu tố độc lập |
| **Khóa + PIN được xác minh tại authenticator** | Sở hữu khóa và yếu tố biết PIN theo cơ chế được triển khai | Có thể đáp ứng MFA theo tiêu chuẩn/chính sách phù hợp |
| **Khóa + sinh trắc tại authenticator** | Sở hữu khóa và xác minh đặc tính sinh trắc trên thiết bị | Có thể là authenticator đa yếu tố nếu đáp ứng yêu cầu |
| **Khóa làm yếu tố thứ hai sau mật khẩu** | Sở hữu khóa + mật khẩu của người dùng | Có thể là MFA khi hai yếu tố được xác minh đúng |
| **Passkey đồng bộ với local user verification** | Bằng chứng khóa công khai và phương thức UV | Mức assurance tùy đặc tính khóa, lưu trữ và tiêu chuẩn áp dụng |

**PIN của security key không phải mật khẩu website.** Thông thường, PIN được nhập qua giao diện client để authenticator xác minh hoặc sử dụng trong cơ chế được hỗ trợ; không gửi PIN đến RP như một credential web thông thường.

**Dấu vân tay dùng để mở khóa** cũng không có nghĩa ảnh vân tay được truyền tới trang web. Trong mô hình WebAuthn, RP thường nhận được **kết quả xác minh UV** và chữ ký, không cần nhận dữ liệu sinh trắc thô.

### Phân loại mức assurance

Khi đánh giá theo **NIST SP 800-63B**, cần kiểm tra phiên bản tiêu chuẩn và **toàn bộ điều kiện AAL**, khả năng chống phishing, cách bảo vệ khóa, cơ chế UV, kênh và chính sách vận hành. Một security key được quảng cáo “FIDO2 certified” không tự động khiến mọi triển khai đạt một mức **AAL** cụ thể; kết quả phụ thuộc cấu hình và bối cảnh xác thực.

## 8. Security key vật lý, passkey và platform authenticator

Các thuật ngữ thường được dùng lẫn nhau:

- **Security key vật lý:** thiết bị xác thực ngoài, thường mang theo, có thể dùng trên nhiều máy; nhiều thiết bị hỗ trợ USB/NFC.
- **Platform authenticator:** authenticator tích hợp trong máy tính/điện thoại, có thể dùng TPM/secure element và xác minh người dùng tại thiết bị.
- **Passkey:** thuật ngữ thường dùng cho credential FIDO/WebAuthn hỗ trợ trải nghiệm không mật khẩu; có thể là **device-bound** hoặc **synced** tùy cách quản lý khóa.
- **Discoverable credential:** credential mà authenticator có thể tìm cho RP mà không cần RP chỉ định trước một credential ID; hỗ trợ nhiều luồng đăng nhập chọn tài khoản/không cần username.
- **Non-discoverable credential:** luồng có thể cần RP cung cấp credential ID thích hợp; phù hợp một số triển khai yếu tố thứ hai.

| Tiêu chí | Security key vật lý | Platform authenticator | Passkey đồng bộ |
|---|---|---|---|
| Vị trí thông thường | Thiết bị rời | Thiết bị người dùng | Hệ sinh thái quản lý credential trên nhiều thiết bị |
| Khả năng mang sang máy khác | Có thể, qua giao diện được hỗ trợ | Phụ thuộc cơ chế và thiết bị | Thường thuận tiện qua sync được hỗ trợ |
| Phụ thuộc phần cứng cụ thể | Thường có với credential gắn khóa | Tùy nền tảng | Không nhất thiết bị buộc vào đúng một phần cứng |
| Khả năng chống phishing WebAuthn | Có khi triển khai đúng | Có khi triển khai đúng | Có khi triển khai đúng |
| Quản lý doanh nghiệp | Cấp phát, thu hồi, giữ khóa dự phòng | Quản lý thiết bị/OS/IdP | Cần chính sách về nhà cung cấp đồng bộ và khôi phục |

**Không phải mọi security key đều cho trải nghiệm passwordless giống nhau.** Một số khóa hỗ trợ discoverable credentials và user verification bằng PIN/biometric; một số cách tích hợp chỉ sử dụng nó như yếu tố thứ hai sau mật khẩu.

## 9. Attestation: có cần xác minh model khóa không?

Trong registration, **attestation** có thể giúp RP nhận biết loại/authenticator hoặc nguồn của credential thông qua dữ liệu mật mã phù hợp. Tuy nhiên, **attestation không nhất thiết bắt buộc cho mọi ứng dụng**, và việc xác minh được model thiết bị cũng không chứng minh người dùng đã được identity proofing hoặc không thể bị chiếm phiên.

### Một số quyết định thiết kế

- **Chỉ cần WebAuthn thành công:** ứng dụng phổ thông có thể cho phép authenticator phù hợp mà không đòi enterprise attestation.
- **Chính sách thiết bị được phê duyệt:** một số tổ chức yêu cầu danh sách model, cơ chế khóa không xuất và đặc tính bảo vệ nhất định; cần xác minh khả năng attestation thực tế.
- **Enterprise attestation:** có thể cung cấp dữ liệu định danh authenticator ở mức có khả năng ảnh hưởng riêng tư, do đó cần phê duyệt, giới hạn phạm vi và căn cứ phù hợp.
- **AAGUID/metadata:** hữu ích cho nhận diện dòng authenticator hoặc chính sách tương thích, nhưng không dùng một trường metadata không được kiểm chứng làm bằng chứng bảo mật duy nhất.

Không tự kết luận **“attestation accepted = user identity verified”**. Attestation liên quan đến thông tin authenticator; identity proofing xác minh con người và quan hệ với danh tính được khai.

## 10. Thiết kế chính sách enrollment security key

Một tổ chức nên xác định rõ **ai được đăng ký, đăng ký khi nào, yêu cầu bao nhiêu khóa, phương pháp dự phòng và điều kiện cấp quyền**.

| Hạng mục | Câu hỏi thiết kế |
|---|---|
| **Điều kiện ban đầu** | Joiner đã được xác minh đúng danh tính và có tài khoản IdP hợp lệ chưa? |
| **Kênh enrollment** | Người dùng vào cổng chính thức hay dùng lời mời có giới hạn? |
| **Thêm khóa thứ hai** | Có bắt buộc xác thực bằng authenticator hiện có hoặc step-up không? |
| **PIN/UV** | Mỗi loại quyền cần UP hay UV? Thiết bị có hỗ trợ không? |
| **Thiết bị hỗ trợ** | Khóa USB/NFC/platform nào được chấp nhận; có kiểm soát attestation không? |
| **Backup key** | Ai giữ, cách đăng ký và kiểm tra định kỳ? |
| **Lost key** | Làm thế nào báo mất, khóa credential tại RP và phát hành khóa mới? |
| **MFA coverage** | Account admin, helpdesk, người dùng thường có chính sách khác nhau không? |
| **Audit/notification** | Người dùng có được báo khi thêm/xóa khóa hay không? |
| **External identity** | Nhà thầu/đối tác đăng ký ở IdP nào và khi chấm dứt quan hệ xử lý thế nào? |

### Mẫu policy minh họa (giả mã)

~~~text
allowAuthenticatorRegistration(request):
    require identity.lifecycleState == ACTIVE_OR_APPROVED_JOINER
    require request.origin in APPROVED_ENROLLMENT_ORIGINS
    require identity.proofingSatisfies(enrollmentRiskPolicy)
    require session.isAuthenticatedAtRequiredStrength
    require authenticator.supportsRequiredUserVerification
    require enrollmentApprovalIfPrivileged(identity)
    recordRegistrationAuditEvent()

allowPrivilegedAccess(request):
    require identity.lifecycleState == ACTIVE
    require request.session.phishingResistantAuthentication == true
    require request.session.userVerificationSatisfied == true
    require request.authorization.isAllowedByRBACandABAC
    require request.riskWithinPolicy
~~~

Đây là **giả mã định hướng**, không phải một biểu thức tiêu chuẩn của WebAuthn hoặc sản phẩm cụ thể. **Các thuộc tính do client tự khai không đủ để chứng minh** đã dùng security key chống phishing; RP/IdP phải xác minh đúng ceremony và thông tin phiên rồi mới cung cấp tín hiệu tin cậy.

### Nguyên tắc quyền tối thiểu

Có security key chỉ giúp tăng assurance của xác thực. Nó **không cho phép user tự nhận vai trò Admin** hoặc bỏ qua phê duyệt SoD. Trong một hệ thống RBAC/ABAC, MFA có thể là **điều kiện bắt buộc** để dùng quyền đã được cấp, không phải nguồn phát sinh quyền nghiệp vụ.

## 11. Recovery: mất, hỏng hoặc quên security key

**Recovery** thường là điểm yếu nhất của hệ thống xác thực mạnh. Nếu attacker có thể tự thêm khóa mới bằng câu hỏi bí mật yếu, thì phishing-resistant authentication ở luồng đăng nhập không còn bảo vệ toàn bộ vòng đời tài khoản.

### Quy trình đề xuất khi mất khóa

1. **Tiếp nhận yêu cầu:** qua kênh helpdesk, portal hoặc quy trình hỗ trợ đã công bố, không tin email bất ngờ một cách mù quáng.
2. **Xác minh chủ thể:** dùng phương thức dự phòng hoặc proofing lại theo rủi ro; với tài khoản nhạy cảm cần kiểm soát tăng cường.
3. **Xác định chính xác credential:** tra credential ID và lịch sử enrollment; không xóa nhầm khóa dự phòng hợp lệ.
4. **Vô hiệu hóa tại RP/IdP:** gỡ hoặc vô hiệu credential bị mất để assertion từ khóa đó không còn được chấp nhận.
5. **Xem lại session hiện có:** đánh giá thu hồi hoặc tăng cường xác thực đối với phiên/token theo chính sách sự cố.
6. **Đăng ký khóa mới:** qua luồng enrollment đáng tin, gắn đúng identity và thông báo cho chủ tài khoản.
7. **Đối soát và lưu bằng chứng:** xác minh khóa cũ không còn active, khóa mới hoạt động và ngoại lệ đã đóng.

**Gỡ credential khỏi IdP/RP không xóa private key vật lý trong thiết bị đã mất.** Tuy nhiên, nếu RP không còn chấp nhận public key/credential ID tương ứng thì khóa bị mất không thể tiếp tục xác thực với RP đó qua credential bị thu hồi. Nếu thiết bị đăng ký với **nhiều RP**, phải xử lý **từng RP liên quan** theo phạm vi, không giả định xóa ở IdP sẽ vô hiệu hóa credential đăng ký trực tiếp tại ứng dụng khác.

### Backup key

Nên cân nhắc một hoặc nhiều **khóa dự phòng đã đăng ký trước**, đặc biệt với tài khoản quan trọng. Cần cất giữ riêng, quản lý owner và kiểm tra theo chính sách; không gắn nhãn “đã có dự phòng” khi khóa dự phòng nằm cùng móc chìa khóa và cùng nguy cơ thất lạc với khóa chính.

### Khi mất PIN

Một số khóa có cơ chế giới hạn số lần thử PIN và reset theo nhà sản xuất. Reset có thể **xóa credential đã lưu** và cần đăng ký lại; không nên hướng dẫn người dùng thử PIN liên tục hoặc dựa vào reset như một cách khôi phục private key cũ. Quy trình phải tuân theo tài liệu của thiết bị và chính sách tổ chức.

## 12. Security key trong Joiner–Mover–Leaver

### Joiner: đăng ký khóa đúng người, đúng thời điểm

Khi HRIS phát sự kiện Joiner, IAM/IGA xác minh quan hệ và điều phối tạo account. Người dùng có thể nhận security key từ IT, sau đó đăng ký tại IdP bằng quy trình proofing/enrollment được phê duyệt. Nếu người mới chưa thể đăng nhập vào email công ty, cần có **kênh mời ban đầu đáng tin cậy**, không gửi một liên kết không được kiểm soát cho địa chỉ chưa được xác minh.

Các mốc cần phân biệt:

1. **Tài khoản được tạo** ở IdP.
2. **Danh tính người dùng được xác minh** theo yêu cầu.
3. **Security key được bàn giao/đăng ký** và liên kết với tài khoản.
4. **Chính sách xác thực được thỏa mãn** cho phạm vi ứng dụng.
5. **Quyền ứng dụng được cấp và xác minh** qua SCIM/API/connector theo RBAC/ABAC.
6. **Trạng thái hoạt động** đạt vào đúng thời điểm hiệu lực.

Không gửi “nhân viên đã có mọi quyền” chỉ vì đăng ký được khóa.

### Mover: tăng yêu cầu xác thực khi đổi vai trò

Nhân viên chuyển từ vai trò thông thường sang quản trị hệ thống có thể phải sử dụng **security key với UV** hoặc chính sách xác thực chống phishing trước khi tiếp cận quyền cao. IAM cần kiểm tra **đã enroll authenticator hợp lệ chưa**, chính sách phiên có đáp ứng không và quyền mới đã được duyệt.

Tuy nhiên, **Mover không chỉ là bổ sung MFA**. Quyền cũ không còn hợp lệ vẫn phải được thu hồi; việc người dùng dùng security key mạnh không hợp thức hóa quyền CRM, VPN, cloud hoặc nhóm đặc quyền cũ.

### Leaver: thu hồi quyền và credential đúng phạm vi

Khi quan hệ chấm dứt, hệ thống phải **vô hiệu hóa đăng nhập, thu hồi phiên/token, quyền ứng dụng, nhóm và credential** theo chính sách. Với security key:

- Gỡ/vô hiệu hóa các WebAuthn credential gắn với tài khoản và RP tương ứng.
- Thu hồi khóa vật lý được công ty cấp, cập nhật asset inventory và xử lý việc bàn giao.
- Xác minh account IdP không thể đăng nhập; kiểm tra các ứng dụng có WebAuthn đăng ký trực tiếp ngoài IdP.
- Xử lý những đường truy cập độc lập với SSO như API key, local account, SSH key, VPN, certificate và phiên cũ.
- Nếu người đó từng là owner của service account/bot, chuyển owner và rà soát secret; không xóa mù quáng workload hợp lệ.

**Security key bị gỡ khỏi IdP không tự động thu hồi session hoặc token đã cấp trước đó.** Không thể tuyên bố Leaver hoàn tất nếu còn quyền truy cập tồn dư tại ứng dụng đích.

### Rejoiner

Người từng nghỉ quay lại có thể tái sử dụng identity record để giữ lịch sử, nhưng cần **quan hệ mới được xác minh**, khôi phục hoặc đăng ký security key theo quy trình hiện hành và tính lại quyền. Không tự mở lại credential cũ hoặc vai trò cũ chỉ vì cùng người sử dụng.

## 13. IdP, SSO, SCIM và ứng dụng trực tiếp dùng WebAuthn

### IdP là điểm quản lý khóa trung tâm

Trong nhiều hệ thống doanh nghiệp, người dùng đăng ký security key **tại IdP**. IdP xác minh WebAuthn và phát session/federation assertion cho ứng dụng dùng **SSO** (SAML/OIDC). Ứng dụng tiêu thụ tín hiệu xác thực theo hợp đồng tin cậy; nó không nhất thiết có hoặc cần lưu public key của người dùng.

~~~mermaid
flowchart TD
    HR[HRIS / Joiner-Mover-Leaver] --> IAM[IAM / IGA]
    IAM --> IDP[IdP / WebAuthn RP]
    USER[Security key của người dùng] --> IDP
    IDP --> SSO[SSO / federation SAML-OIDC]
    SSO --> SAAS[Ứng dụng SaaS]
    IAM --> API[SCIM / provisioning connector]
    API --> SAAS
    IAM --> AUDIT[Audit / access review]
    IDP --> AUDIT
    SAAS --> AUDIT
~~~

**SCIM** không đăng ký hoặc vô hiệu hóa security key theo một schema dùng chung mặc định. SCIM thường quản lý user/group; credential lifecycle nằm ở **IdP/RP hoặc API cụ thể**. Vì vậy, khi Leaver, connector SCIM có thể deactivate user ở SaaS nhưng cần kiểm tra thêm liệu SaaS có **WebAuthn credential và phiên đăng nhập độc lập**.

### Ứng dụng đăng ký WebAuthn trực tiếp

Nếu ngoài IdP, một ứng dụng khác cho người dùng đăng ký security key trực tiếp, sẽ tồn tại **một credential riêng cho RP của ứng dụng đó**. Gỡ khóa trong IdP **không mặc nhiên gỡ** credential tại ứng dụng. IAM cần kiểm kê RP nào đang sở hữu credential, ai làm owner, cơ chế revoke và bằng chứng readback.

### Không suy diễn mức xác thực từ nhãn

Một ứng dụng chỉ thấy người dùng đăng nhập qua SSO **không tự biết** chính xác WebAuthn với UV đã xảy ra trong phiên nào nếu IdP không cung cấp dữ liệu tin cậy hoặc tín hiệu đó không được ứng dụng kiểm tra. Điều kiện truy cập cần dùng assertion/claim đủ căn cứ theo chính sách và năng lực federation, không dùng nhãn tự khai như **mfa=true** từ phía trình duyệt.

## 14. Lỗi triển khai và các mối đe dọa còn lại

| Lỗi hoặc rủi ro | Hậu quả | Kiểm soát |
|---|---|---|
| Không kiểm tra **challenge** | Cho phép phát lại assertion | Challenge mới, gắn phiên và kiểm tra tiêu thụ hợp lệ |
| Không kiểm tra **origin/RP ID** | Mất một phần bảo vệ ngữ cảnh chống phishing | Xác minh origin, rpIdHash và RP ID chính xác |
| Bỏ qua cờ **UV** khi chính sách yêu cầu | Chỉ cần sở hữu/chạm khóa đã vào được | Yêu cầu và xác minh UV ở RP |
| Chấp nhận credential không thuộc account | Liên kết sai danh tính | Mapping credential ID → account có kiểm tra |
| Cho thêm khóa chỉ nhờ email yếu | Attacker đăng ký khóa của họ | Step-up/proofing và quy trình recovery mạnh |
| Không thu hồi khóa mất | Khóa bị mất vẫn có thể dùng | Vô hiệu hóa credential tại RP và rà soát phiên |
| Chỉ xóa khóa tại IdP | Quên WebAuthn credential trực tiếp tại SaaS | Kiểm kê nhiều RP và deprovision theo phạm vi |
| Phiên bị đánh cắp | Attacker có thể dùng cookie/token sau xác thực | Bảo vệ endpoint, phiên, device risk, token lifecycle |
| Quyền nghiệp vụ sai | Key mạnh vẫn thực hiện được hành động vượt quyền | RBAC/ABAC, SoD, access review |
| Thiết bị bị chiếm quyền | Malware có thể thao tác trong phiên đã xác thực | EDR/MDM, isolation, thiết kế giao dịch nhạy cảm |
| Authenticator giả/không đạt policy | Khác biệt đặc tính khóa và lưu trữ | Attestation/metadata khi cần và được phép |
| Quy trình backup yếu | Mất hai khóa gây lockout hoặc fallback kém bảo mật | Backup và recovery được kiểm soát, kiểm toán |

### Security key không phải “lá chắn cho mọi thao tác”

Phishing-resistant authentication giúp chống lại nhiều tấn công lấy bí mật tại trang đăng nhập. Nhưng nếu ứng dụng không kiểm tra **quyền truy cập**, nếu nhân viên đã nghỉ vẫn còn **session hợp lệ**, hoặc nếu attacker chiếm được **máy đang đăng nhập**, security key không thay thế các biện pháp an ninh khác.

Với tác vụ nhạy cảm, có thể cần **step-up**, phê duyệt giao dịch, ghi audit có ngữ cảnh, giới hạn thời gian phiên, xác nhận người dùng và phát hiện rủi ro.

## 15. Logging, kiểm toán và bảo vệ riêng tư

### Những sự kiện cần lưu

- Đăng ký authenticator mới, gỡ authenticator, thay đổi policy MFA.
- Thời điểm và nguồn yêu cầu enrollment; kiểm tra step-up/proofing theo chính sách.
- ID định danh và RP liên quan, tham chiếu credential đã được bảo vệ phù hợp.
- Kết quả WebAuthn ceremony, loại phương thức được chấp nhận và điều kiện UP/UV khi được ghi nhận đáng tin cậy.
- Yêu cầu recovery, mất khóa, cấp lại, phê duyệt, ngoại lệ và người xử lý.
- Thao tác Leaver: disable account, credential revoke, session revoke, kết quả readback.
- Tín hiệu risk: nhiều lần thất bại, đăng ký khóa bất thường, thay đổi bảo mật không được mong đợi.

**Không log PIN, private key, dữ liệu sinh trắc thô, recovery code hoặc bí mật phiên.** Một số metadata về model/attestation và định danh phần cứng cũng có thể liên quan đến riêng tư; chỉ lưu mức cần thiết và bảo vệ theo chính sách.

### Đo lường hiệu quả

| Chỉ số | Ý nghĩa |
|---|---|
| **Coverage của phishing-resistant MFA** | Tỷ lệ danh tính/ứng dụng thuộc scope có khả năng và thực sự yêu cầu xác thực chống phishing |
| **Backup authenticator coverage** | Tỷ lệ người dùng có phương án dự phòng được phê duyệt |
| **Recovery success & abuse incidents** | Hiệu quả phục hồi và số tình huống có dấu hiệu lợi dụng recovery |
| **Unregistered/lost-key incidents** | Số trường hợp mất khóa chưa xử lý triệt để |
| **Time to revoke after Leaver** | Từ effectiveAt đến credential và session được xác minh bị chặn |
| **Privileged access compliance** | Phiên dùng quyền cao có đáp ứng đúng UV/phishing-resistant policy hay không |
| **Legacy/fallback exceptions** | Tài khoản còn dùng cơ chế kém hơn và hạn giải quyết ngoại lệ |
| **Direct-RP coverage** | Những ứng dụng có credential WebAuthn ngoài IdP đã được đưa vào kiểm kê |

Không đánh đồng **“đã phát security key cho nhân viên”** với **“credential đã enroll và mọi ứng dụng đều được bảo vệ đúng mức”**.

## 16. Ví dụ bản ghi quản lý security key

Ví dụ một bản ghi nội bộ tại IdP/IAM, **không phải schema WebAuthn hoặc SCIM chuẩn**, và **không chứa private key**:

~~~json
{
  "identityId": "person-2046",
  "accountId": "idp-user-2046",
  "lifecycleState": "ACTIVE",
  "credentials": [
    {
      "credentialRef": "cred-ref-a10",
      "rpId": "login.example.org",
      "authenticatorClass": "ROAMING_SECURITY_KEY",
      "registeredAt": "2026-11-23T09:10:00+07:00",
      "userVerificationPolicy": "REQUIRED",
      "status": "ACTIVE",
      "ownerType": "EMPLOYEE"
    },
    {
      "credentialRef": "cred-ref-b22",
      "rpId": "login.example.org",
      "authenticatorClass": "BACKUP_SECURITY_KEY",
      "registeredAt": "2026-11-23T09:15:00+07:00",
      "userVerificationPolicy": "REQUIRED",
      "status": "ACTIVE",
      "ownerType": "EMPLOYEE"
    }
  ],
  "lastCredentialReviewAt": "2026-11-23T09:20:00+07:00"
}
~~~

Trong triển khai thực tế, RP giữ dữ liệu public key/credential ID và thông tin cần để xác minh. Hệ thống IAM có thể chỉ cần **tham chiếu** và trạng thái. Các trường như ownerType, authenticatorClass và lastCredentialReviewAt được nêu để minh họa quản trị; không nên gắn chúng thành thuộc tính WebAuthn bắt buộc.

**Không dùng serial number hoặc tên khóa vật lý làm bằng chứng xác thực duy nhất.** Chỉ credential WebAuthn đã đăng ký và được xác minh đúng mới có thể hỗ trợ xác thực.

## 17. Tình huống xuyên suốt: Joiner → Mover → Leaver

Giả sử nhân viên **Lan** gia nhập bộ phận Finance, sau đó chuyển sang vị trí quản trị và cuối cùng nghỉ việc.

**Joiner — nhận khóa:** HRIS tạo sự kiện gia nhập, IAM xác định danh tính và điều kiện account. IT cấp security key qua quy trình quản lý tài sản. Lan vào cổng IdP chính thức để đăng ký hai credential: khóa sử dụng hằng ngày và khóa dự phòng cất giữ theo chính sách. IdP kiểm tra WebAuthn registration, gắn public key với đúng account và ghi audit. Không có quyền Finance phát sinh chỉ vì sở hữu security key.

**Bắt đầu làm việc — đăng nhập SSO:** Lan dùng security key để đăng nhập IdP. Trình duyệt và RP kiểm tra WebAuthn; ứng dụng nhận federation assertion phù hợp. IAM đã cấp quyền Finance theo RBAC/ABAC qua SCIM/API và kiểm tra trạng thái đích, nên Lan chỉ xem được báo cáo thuộc phạm vi.

**Mover — nhận vai trò quản trị:** Lan được đề xuất vào nhóm admin. Chính sách yêu cầu xác thực chống phishing với UV, kiểm tra SoD và phê duyệt quyền. Lan đáp ứng xác thực bằng security key, nhưng nếu chưa được duyệt vai trò admin thì vẫn **không có quyền admin**. Khi chuyển vai trò, quyền Finance không còn hợp lệ phải được thu hồi; việc sử dụng key mạnh không thay thế thao tác này.

**Mất khóa — recovery:** Lan làm mất khóa chính. Hệ thống xác minh yêu cầu bằng phương thức dự phòng và quy trình hợp lệ, thu hồi credential của khóa thất lạc tại IdP, đánh giá các phiên hiện có và đăng ký khóa mới. Trạng thái của khóa dự phòng hợp lệ được giữ nguyên; các ứng dụng có WebAuthn riêng được kiểm tra nếu có.

**Leaver — đóng truy cập:** HRIS phát sự kiện chấm dứt hiệu lực. IAM vô hiệu hóa IdP account, thu hồi các WebAuthn credential, phiên/token, nhóm/quyền và những đường truy cập độc lập. IT thu hồi khóa công ty, cập nhật asset inventory. Những hệ thống SaaS có credential riêng phải được xử lý riêng và readback; chỉ khi không còn đường truy cập trái phép thuộc scope mới đóng workflow.

**Rehire — quan hệ mới:** Nếu Lan quay lại sau này, IAM xác minh lại điều kiện theo quy trình Joiner, đăng ký hoặc khôi phục authenticator hợp lệ theo chính sách và cấp lại **quyền mới**. Không tự bật account và role cũ chỉ vì Lan vẫn giữ một security key.

## 18. Checklist triển khai Security key trong IAM Lifecycle

1. **Khái niệm đúng:** security key được quản lý như authenticator chứ không bị nhầm với tài khoản, quyền hoặc chứng cứ identity proofing?
2. **Kiến trúc:** xác định RP/IdP nào sở hữu credential, ứng dụng nào dùng SSO và ứng dụng nào đăng ký WebAuthn trực tiếp?
3. **Đúng giao thức:** server kiểm tra challenge, origin, RP ID hash, credential, chữ ký, UP/UV và trạng thái account theo chính sách?
4. **Phishing resistance:** không hạ cấp vô điều kiện sang OTP/mật khẩu qua recovery dễ lạm dụng cho những quyền bắt buộc chống phishing?
5. **Enrollment:** Joiner được xác minh đúng danh tính, lời mời an toàn, việc thêm khóa có step-up/phê duyệt theo rủi ro?
6. **MFA semantics:** đã phân biệt chạm khóa (UP) với PIN/biometric (UV), không gọi mọi chế độ một yếu tố là MFA?
7. **Loại authenticator:** đã phân biệt security key gắn phần cứng, platform authenticator, passkey device-bound và passkey synced?
8. **Thiết bị hỗ trợ:** USB/NFC, trình duyệt, thiết bị dùng và yêu cầu policy có tương thích không?
9. **Backup:** người dùng và admin có phương án dự phòng không làm giảm assurance; khóa dự phòng được kiểm kê và cất giữ an toàn?
10. **Recovery:** mất/hỏng khóa có quy trình xác minh, thu hồi credential, cấp lại và cảnh báo cho người dùng?
11. **JML:** Mover đánh giá điều kiện xác thực và thu hồi quyền cũ; Leaver khóa account, credential, session/token và quyền đích?
12. **Ứng dụng đích:** SCIM provisioning không bị hiểu nhầm là đăng ký hoặc thu hồi WebAuthn credential ở mọi RP?
13. **An ninh còn lại:** có bảo vệ phiên, endpoint, RBAC/ABAC và hoạt động quản trị đặc quyền ngoài MFA?
14. **Audit/riêng tư:** logging đủ để tra cứu mà không chứa private key, PIN, biometrics hoặc secret?
15. **Đối soát:** chỉ đóng quy trình khi trạng thái credential và quyền thực tế ở đúng hệ thống đích đã được xác minh?

### Ghi nhớ

**Security key FIDO2/WebAuthn sử dụng mật mã khóa công khai và ràng buộc RP/origin để hỗ trợ xác thực chống phishing.** Touch, PIN, sinh trắc, passkey đồng bộ và security key vật lý có ngữ nghĩa khác nhau; việc đạt MFA/AAL tùy cấu hình và chính sách. Trong **IAM Identity Lifecycle**, phải đăng ký khóa đúng danh tính ở Joiner, đánh giá yêu cầu xác thực mạnh khi Mover, và thu hồi **credential, phiên/token, quyền cùng đường truy cập độc lập** khi Leaver. **Không coi security key mạnh là sự thay thế cho identity proofing, authorization, quản trị phiên hoặc đối soát quyền tồn dư.**
