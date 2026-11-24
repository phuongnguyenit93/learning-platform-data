# Phishing

> **Chương:** Threat model  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Mô hình hóa và phòng chống phishing trong xác thực danh tính, từ đánh cắp credential và chiếm phiên đến lạm dụng MFA, khôi phục tài khoản và thao tác sau đăng nhập.

## 1. Phishing là gì trong một hệ thống xác thực?

**Phishing (lừa đảo giả mạo)** là hình thức tấn công thao túng người dùng để họ tiết lộ thông tin, thực hiện hành động hoặc cấp quyền cho kẻ tấn công bằng cách giả danh một thực thể đáng tin cậy. Trong hệ thống xác thực, mục tiêu thường là lấy mật khẩu, mã OTP, mã khôi phục, cookie phiên, token, hoặc khiến người dùng chấp thuận một yêu cầu đăng nhập do kẻ tấn công khởi tạo.

Phishing khai thác sự tin tưởng và hành vi của con người. Nó có thể xuất hiện qua email, SMS, cuộc gọi, mạng xã hội, QR code, thông báo push, trang web giả, tài liệu chia sẻ hoặc ngay trong một quy trình hỗ trợ khách hàng. Một thông điệp có thể rất thuyết phục vì dùng đúng tên tổ chức, logo, ngôn ngữ nội bộ và thời điểm người dùng đang chờ một giao dịch.

Trong ngữ cảnh xác thực, cần phân biệt ba mục tiêu thường bị đánh đồng:

1. **Credential theft:** kẻ tấn công lấy mật khẩu, OTP hoặc bí mật khôi phục.
2. **Session/token theft:** kẻ tấn công chiếm bằng chứng đã xác thực để sử dụng phiên hiện có.
3. **Authorization/transaction abuse:** kẻ tấn công khiến người dùng hoặc ứng dụng thực hiện hành động trái ý định, dù quá trình xác thực ban đầu có thể hợp lệ.

Một thiết kế chống phishing tốt cần bảo vệ cả ba giai đoạn. Chỉ đào tạo người dùng nhận biết email đáng ngờ hoặc chỉ bật MFA không đủ để giải quyết mọi kịch bản.

### Kết quả học tập

Sau bài này, người học có thể:

- Xác định tài sản, chủ thể, ranh giới tin cậy và đường tấn công trong một kịch bản phishing.
- Phân biệt phishing lấy mật khẩu, phishing chuyển tiếp OTP, adversary-in-the-middle và chiếm phiên.
- Giải thích vì sao MFA dạng OTP/push có thể bị lừa trong thời gian thực và vì sao WebAuthn/passkey chống phishing tốt hơn.
- Thiết kế kiểm soát kỹ thuật, quy trình và phản ứng sự cố để giảm xác suất cũng như tác động của phishing.
- Kiểm thử luồng đăng nhập, đăng ký authenticator, khôi phục và thao tác nhạy cảm trước các kịch bản lừa đảo.

## 2. Tài sản và ranh giới tin cậy cần bảo vệ

Phishing không chỉ nhắm đến mật khẩu. Hãy xác định tài sản có thể giúp kẻ tấn công duy trì hoặc mở rộng quyền truy cập:

| Tài sản | Giá trị đối với kẻ tấn công | Tác động khi bị chiếm |
|---|---|---|
| Mật khẩu / passphrase | Đăng nhập bằng danh tính nạn nhân | Mạo danh, truy cập dữ liệu và chức năng |
| Mã OTP / bí mật TOTP | Vượt qua bước MFA | Chiếm tài khoản trong lúc mã còn hiệu lực hoặc sao chép bí mật lâu dài |
| Passkey / khóa riêng | Tạo bằng chứng xác thực | Mạo danh nếu khóa hoặc thiết bị bị kiểm soát; thường khó lấy khóa riêng trực tiếp hơn |
| Recovery code / liên kết đặt lại | Bỏ qua hoặc thay thế credential đã mất | Đặt lại mật khẩu, đăng ký phương thức xác thực mới |
| Cookie phiên / refresh token | Tiếp tục sử dụng trạng thái đã xác thực | Chiếm phiên mà không cần biết mật khẩu |
| Quyền OAuth / consent | Cho ứng dụng bên ngoài truy cập dữ liệu | Truy cập kéo dài qua token hoặc quyền đã cấp |
| Thông tin giao dịch | Sửa người nhận, số tiền hoặc nội dung hành động | Gian lận dù người dùng đã đăng nhập đúng |
| Danh bạ và thông tin nội bộ | Tạo thông điệp giả mạo đáng tin hơn | Phishing lan rộng sang đồng nghiệp, khách hàng và đối tác |

### Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart LR
    A["Kẻ tấn công / hạ tầng giả mạo"] -->|"Email, SMS, QR, trang giả"| U["Người dùng"]
    U -->|"Nhập credential / chấp thuận"| C["Client hoặc browser"]
    C -->|"Yêu cầu qua TLS"| V["Dịch vụ xác thực thật"]
    V -->|"Phiên / token"| R["API / tài nguyên"]
    A -->|"Trang trung gian / proxy"| C
    A -->|"Token hoặc cookie bị lấy"| R
    R --> D["Dữ liệu / giao dịch"]
~~~

Các thành phần ở phía người dùng không tự động là đáng tin cậy chỉ vì chúng hiển thị thương hiệu quen thuộc. Tên miền, nội dung email và giao diện có thể bị giả mạo. Server xác thực phải kiểm tra bằng chứng; resource server phải xác minh phiên/token và quyền. Người dùng cần có cách xác nhận **đúng dịch vụ, đúng hành động và đúng ngữ cảnh**.

### Những câu hỏi threat modeling

Khi rà soát một luồng đăng nhập, hãy hỏi:

- Kẻ tấn công có thể gửi thông điệp đến người dùng qua kênh nào?
- Người dùng có thể bị dẫn đến tên miền giả, deep link giả hoặc QR code giả không?
- Credential nào có thể bị người dùng nhập vào một trang không đáng tin?
- Bằng chứng có gắn với origin, challenge, phiên hoặc giao dịch cụ thể không?
- Có cách lấy cookie, token hoặc mã khôi phục sau khi đăng nhập không?
- Kẻ tấn công có thể thêm authenticator, thay email khôi phục hoặc cấp OAuth consent bằng phiên đã chiếm không?
- Khi phát hiện, hệ thống có thể thu hồi credential, phiên và quyền đã cấp nhanh đến đâu?

## 3. Chuỗi tấn công phishing thường gặp

Một cuộc phishing có thể gồm nhiều bước:

1. **Chuẩn bị:** kẻ tấn công thu thập thương hiệu, tên miền gần giống, thông tin nhân sự, lịch làm việc hoặc sự kiện người dùng đang chờ.
2. **Tiếp cận:** gửi email, SMS, tin nhắn, QR code hoặc gọi điện với nội dung tạo cảm giác cấp bách.
3. **Dẫn dụ:** yêu cầu người dùng đăng nhập, xem tài liệu, xác minh thanh toán hoặc chấp thuận một thông báo.
4. **Thu thập bằng chứng:** lấy mật khẩu, OTP, mã phục hồi, token OAuth hoặc cookie.
5. **Sử dụng:** đăng nhập, chuyển tiếp yêu cầu MFA, chiếm phiên hoặc cấp thêm credential cho kẻ tấn công.
6. **Duy trì và mở rộng:** thay thông tin khôi phục, tạo phiên mới, thêm passkey, tạo token ứng dụng, tìm dữ liệu hoặc giả mạo nạn nhân để tấn công người khác.
7. **Ẩn dấu vết:** xóa email cảnh báo, thay đổi thông tin liên hệ hoặc dùng tài khoản hợp lệ để trộn hoạt động độc hại vào lưu lượng bình thường.

~~~mermaid
flowchart TD
    P["Chuẩn bị mạo danh"] --> L["Gửi thông điệp lừa đảo"]
    L --> U{"Người dùng tương tác?"}
    U -->|"Không"| X["Báo cáo / chặn / kết thúc"]
    U -->|"Có"| C["Nhập credential hoặc chấp thuận"]
    C --> T{"Bằng chứng lấy được là gì?"}
    T -->|"Mật khẩu / OTP"| A["Đăng nhập hoặc chuyển tiếp MFA"]
    T -->|"Cookie / token"| S["Chiếm phiên hiện tại"]
    T -->|"OAuth consent"| O["Dùng quyền ứng dụng đã cấp"]
    A --> M["Duy trì: thêm authenticator / đổi khôi phục"]
    S --> M
    O --> M
    M --> R["Truy cập dữ liệu / hành động trái phép"]
~~~

**Điểm quan trọng:** phishing không nhất thiết kết thúc ở lần đăng nhập đầu tiên. Nếu kẻ tấn công có thể thay đổi phương thức khôi phục hoặc thêm authenticator của họ, họ có thể duy trì quyền kiểm soát ngay cả sau khi nạn nhân đổi mật khẩu.

## 4. Các kiểu phishing nhắm vào xác thực

| Kiểu tấn công | Cách hoạt động | Bằng chứng bị đe dọa |
|---|---|---|
| **Trang đăng nhập giả** | Dùng tên miền/giao diện giống dịch vụ thật để thu mật khẩu | Password |
| **Phishing qua OTP** | Yêu cầu nhập mã SMS/TOTP vào biểu mẫu giả | Mã dùng một lần |
| **Adversary-in-the-middle (AiTM)** | Proxy giữa nạn nhân và dịch vụ thật, chuyển tiếp yêu cầu và phản hồi | Mật khẩu, OTP, cookie phiên |
| **Push fatigue / MFA bombing** | Gửi liên tục yêu cầu push để người dùng bấm chấp thuận | Phê duyệt MFA |
| **QR phishing (quishing)** | Dùng QR code dẫn đến trang giả hoặc luồng đăng nhập trên thiết bị khác | Credential hoặc phiên |
| **OAuth consent phishing** | Dụ người dùng cấp quyền cho ứng dụng độc hại | Authorization grant / access token |
| **Help-desk/social engineering** | Giả danh nhân viên, quản lý hoặc chủ tài khoản để yêu cầu reset MFA | Quy trình khôi phục và quyền hỗ trợ |
| **Session hijacking** | Lấy cookie hoặc token sau khi đăng nhập | Phiên đã xác thực |
| **Business email compromise (BEC)** | Giả danh đối tác/quản lý để thay đổi thông tin thanh toán hoặc yêu cầu hành động | Ý định giao dịch và quyền nghiệp vụ |

### Phishing bằng trang giả

Người dùng nhận email “Tài khoản sẽ bị khóa trong 15 phút” và nhấp liên kết. Trang giả có thể sao chép logo, màu sắc, bố cục và biểu mẫu. Nếu người dùng nhập mật khẩu, kẻ tấn công có thể thử credential đó trên dịch vụ thật hoặc nhiều dịch vụ khác.

Mật khẩu tái sử dụng làm tăng phạm vi tác động. Nếu cùng một cặp username/password được dùng ở nhiều nơi, một lần lộ có thể mở khóa các tài khoản khác (**credential stuffing**). Trình quản lý mật khẩu giúp giảm nguy cơ dùng chung mật khẩu và thường chỉ autofill khi tên miền khớp, nhưng không thay thế việc kiểm tra miền hoặc dùng xác thực chống phishing.

### AiTM: proxy trung gian chuyển tiếp đăng nhập

Trong một cuộc tấn công AiTM, kẻ tấn công dựng một proxy ngược. Nạn nhân truy cập trang do kẻ tấn công kiểm soát; proxy chuyển yêu cầu đến trang đăng nhập thật và chuyển phản hồi về nạn nhân. Người dùng có thể nhìn thấy nội dung của dịch vụ thật và hoàn tất MFA, trong khi proxy quan sát được lưu lượng ở lớp ứng dụng mà nó trung gian.

Nếu luồng xác thực dựa trên mật khẩu và OTP có thể chuyển tiếp, kẻ tấn công có thể lấy **cookie phiên sau khi xác thực**. Cookie đó có thể cho phép truy cập mà không cần biết mật khẩu hoặc mã OTP. TLS vẫn được dùng giữa từng cặp kết nối, nhưng nó không ngăn được việc người dùng chủ động kết nối đến proxy giả.

### MFA bombing và push fatigue

Kẻ tấn công đã có mật khẩu hoặc đang cố đăng nhập, sau đó gửi nhiều yêu cầu push đến điện thoại nạn nhân. Người dùng mệt mỏi, nhầm lẫn hoặc muốn thông báo dừng lại nên bấm Approve. Nếu push chỉ hỏi “Bạn có muốn đăng nhập không?” mà không hiển thị ngữ cảnh rõ ràng, người dùng khó nhận biết yêu cầu nào do mình khởi tạo.

Giảm rủi ro bằng cách giới hạn số lần push, yêu cầu number matching hoặc xác nhận ngữ cảnh, phát hiện chuỗi yêu cầu bất thường và cung cấp lựa chọn từ chối/báo cáo. Number matching giảm việc bấm nhầm nhưng vẫn cần quy trình chống social engineering.

### OAuth consent phishing

Không phải phishing nào cũng yêu cầu mật khẩu. Một ứng dụng giả có thể yêu cầu quyền đọc email, tệp hoặc danh bạ. Người dùng đăng nhập qua IdP thật và chấp thuận consent; kẻ tấn công nhận token hoặc quyền truy cập được cấp cho ứng dụng. Vì vậy, màn hình consent cần nêu rõ **tên ứng dụng, nhà phát hành, quyền và tác động**; tổ chức có thể hạn chế ứng dụng chưa được phê duyệt và rà soát grant bất thường.

## 5. Vì sao OTP/MFA có thể bị phishing?

MFA tăng độ khó vì kẻ tấn công cần thêm bằng chứng ngoài mật khẩu. Nhưng “có MFA” không đồng nghĩa “chống phishing”.

### OTP không gắn với origin

Mã SMS hoặc TOTP thường là một giá trị ngắn, có thời hạn. Verifier kiểm tra mã đó có khớp bí mật chung và cửa sổ thời gian không. Mã không tự chứng minh người dùng đang ở đúng tên miền. Kẻ tấn công có thể:

1. Thu mật khẩu qua trang giả.
2. Bắt đầu đăng nhập vào dịch vụ thật.
3. Chuyển yêu cầu OTP đến nạn nhân.
4. Nạn nhân nhập mã vào trang giả.
5. Proxy chuyển mã đến dịch vụ thật trước khi hết hạn.
6. Kẻ tấn công nhận phiên đã xác thực hoặc token tiếp theo.

Một mã chỉ dùng một lần vẫn có thể bị **chuyển tiếp đúng một lần** trong thời gian còn hiệu lực. “One-time” giúp chống tái sử dụng sau khi tiêu thụ; nó không tự chống relay thời gian thực.

### So sánh phương thức

| Phương thức | Khả năng chống phishing | Ghi chú |
|---|---|---|
| Mật khẩu | Thấp | Có thể nhập vào trang giả và tái sử dụng |
| SMS OTP | Thấp đến hạn chế | Có thể bị chuyển tiếp; còn có rủi ro SIM swap và kênh viễn thông |
| TOTP | Thấp đến hạn chế | Mã có thể bị proxy trong thời gian hiệu lực |
| Push approval cơ bản | Hạn chế | Dễ bị lạm dụng nếu người dùng bấm nhầm |
| Push có number matching/ngữ cảnh | Tốt hơn push cơ bản | Giảm approve nhầm, nhưng vẫn có thể bị thao túng |
| FIDO2/WebAuthn/passkey | Cao đối với phishing giả mạo origin | Bằng chứng gắn với RP ID/origin, khóa riêng không gửi tới trang giả |
| Chứng chỉ client/mTLS | Phụ thuộc cách cấp phát và ràng buộc | Phù hợp máy/dịch vụ; không thay thế bảo vệ thao tác người dùng |

Mức “cao” của WebAuthn có điều kiện: RP phải xác minh đúng challenge, origin, RP ID, chữ ký và credential; client/browser phải hoạt động theo chuẩn; quy trình đăng ký và khôi phục phải an toàn. Nếu tổ chức vẫn cho phép một đường dự phòng bằng mật khẩu/OTP yếu, kẻ tấn công có thể chọn đường yếu đó.

## 6. WebAuthn/passkey giảm phishing bằng cách nào?

WebAuthn sử dụng cặp khóa công khai/riêng. Khi đăng ký, authenticator tạo credential cho RP; server lưu credential ID và khóa công khai. Khi đăng nhập, server gửi challenge; authenticator ký dữ liệu xác thực sau khi đáp ứng điều kiện tương tác người dùng.

Một assertion gắn với:

- **Challenge:** giá trị ngẫu nhiên do server tạo, gắn với phiên và yêu cầu hiện tại.
- **Origin:** nguồn gốc trang web đang gọi API WebAuthn.
- **RP ID:** định danh relying party mà credential được tạo cho.
- **Credential:** khóa riêng tương ứng với khóa công khai đã đăng ký.
- **User presence / user verification:** tín hiệu tương tác và xác minh người dùng tại authenticator theo chính sách.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser tại miền thật
    participant A as Authenticator / passkey
    participant R as RP / server
    U->>C: Chọn đăng nhập bằng passkey
    C->>R: Xin challenge
    R-->>C: Challenge + RP ID + options
    C->>A: Yêu cầu assertion theo origin hiện tại
    A->>U: Yêu cầu xác nhận UP/UV
    U-->>A: Chạm / PIN / sinh trắc học cục bộ
    A-->>C: Chữ ký và authenticator data
    C->>R: Assertion
    R->>R: Kiểm tra challenge, origin, RP ID, credential, chữ ký, flags
    R-->>C: Cấp phiên nếu chính sách đạt
~~~

Trang phishing trên miền khác không thể yêu cầu authenticator tạo assertion hợp lệ cho RP ID của trang thật theo luồng WebAuthn chuẩn. Khóa riêng không được gửi lên trang; bằng chứng là chữ ký gắn với bối cảnh RP.

### Các kiểm tra server không được bỏ qua

1. Challenge do server tạo, đủ ngẫu nhiên, còn hiệu lực, gắn với đúng yêu cầu và chỉ tiêu thụ một lần.
2. Origin trong client data đúng với danh sách origin được phép.
3. RP ID hash đúng RP ID cấu hình cho dịch vụ.
4. Credential ID thuộc tài khoản và trạng thái hợp lệ.
5. Chữ ký được xác minh bằng khóa công khai đã đăng ký.
6. UP/UV đáp ứng yêu cầu chính sách.
7. Trạng thái tài khoản, credential và rủi ro phiên cho phép tiếp tục.

Nếu server chỉ kiểm tra chữ ký mà bỏ qua origin hoặc challenge, thiết kế có thể mất ràng buộc chống phishing và replay. Dùng thư viện WebAuthn được duy trì và cấu hình đúng; không tự triển khai parser/thuật toán xác minh tùy biến.

### Giới hạn của passkey

Passkey chống tốt việc lừa người dùng nhập bằng chứng vào **một origin giả**, nhưng không tự giải quyết:

- XSS trên origin thật, malware hoặc thiết bị người dùng đã bị kiểm soát.
- Chiếm cookie/session/access token sau khi đăng nhập.
- Người dùng bị lừa phê duyệt giao dịch hoặc cấp OAuth consent.
- Kẻ tấn công đăng ký passkey của họ sau khi chiếm phiên hoặc quy trình hỗ trợ.
- Quy trình khôi phục tài khoản yếu hơn cơ chế đăng nhập chính.
- Phân quyền sai ở API.

Do đó, triển khai passkey cần đi kèm bảo vệ client, phiên, giao dịch, quy trình enrollment/recovery và quyền tài nguyên.

## 7. Kiểm soát phòng ngừa theo từng lớp

Không có một biện pháp đơn lẻ ngăn được mọi cuộc phishing. Hãy xây nhiều lớp sao cho thất bại của một lớp không lập tức dẫn đến chiếm tài khoản.

### Lớp 1 — Danh tính dịch vụ và kênh giao tiếp

- Dùng HTTPS ở mọi trang đăng nhập, callback, API và trang khôi phục.
- Công bố tên miền chính thức và cung cấp lối truy cập quen thuộc qua bookmark hoặc ứng dụng chính thức.
- Dùng HSTS và cấu hình TLS phù hợp; hạn chế subdomain không được quản lý và nguy cơ chiếm subdomain.
- Bảo vệ email tên miền tổ chức bằng SPF, DKIM và DMARC phù hợp để giảm giả mạo người gửi; các cơ chế này không chứng minh một liên kết trong email là an toàn.
- Hạn chế redirect URL tùy ý và kiểm tra callback URI trong luồng SSO/OAuth.

### Lớp 2 — Phương thức xác thực

- Ưu tiên passkey/WebAuthn hoặc khóa bảo mật FIDO cho tài khoản và thao tác rủi ro cao.
- Nếu dùng MFA push, giới hạn số yêu cầu, thêm number matching và ngữ cảnh dễ hiểu.
- Tránh dùng SMS làm yếu tố duy nhất cho tài khoản có tác động cao khi có phương án mạnh hơn.
- Kiểm tra mật khẩu bị lộ và ngăn credential stuffing; hỗ trợ password manager để giảm tái sử dụng.
- Không cho phép downgrade âm thầm từ passkey sang mật khẩu/OTP yếu mà không có chính sách và bằng chứng bổ sung.

### Lớp 3 — Phiên và token

- Cookie phiên web nên có Secure, HttpOnly và SameSite phù hợp; bảo vệ chống XSS, CSRF và session fixation.
- Không đưa token vào URL, log, analytics hoặc thông báo lỗi; bảo vệ kho token trong ứng dụng native.
- Giới hạn thời hạn và phạm vi token; dùng refresh token rotation/reuse detection khi kiến trúc hỗ trợ.
- Có khả năng thu hồi phiên và token sau khi phát hiện phishing hoặc thay đổi credential.
- Cân nhắc xác thực lại trước thao tác nhạy cảm, kể cả khi phiên vẫn hợp lệ.

### Lớp 4 — Tài khoản và khôi phục

- Bảo vệ việc thêm passkey, thay MFA, đổi email khôi phục và liên kết IdP bằng xác thực lại phù hợp.
- Mã khôi phục có entropy cao, một lần, thời hạn và lưu trữ phù hợp; không gửi mật khẩu hiện tại qua email.
- Nhân viên hỗ trợ không được yêu cầu người dùng đọc mật khẩu, OTP hoặc recovery code.
- Thay đổi phương thức xác thực phải có thông báo qua kênh phù hợp và dấu vết kiểm toán.
- Không tự động ghép tài khoản chỉ vì email trùng; xác minh đúng issuer/subject và quyền kiểm soát.

### Lớp 5 — Người dùng và tổ chức

- Huấn luyện bằng tình huống thực tế: đường link giả, QR phishing, push fatigue, cuộc gọi giả danh và OAuth consent.
- Cung cấp nút/bộ phận báo cáo phishing dễ tìm và quy trình phản hồi rõ.
- Không tạo văn hóa gây áp lực khiến nhân viên phải bỏ qua bước xác minh yêu cầu khẩn cấp.
- Dùng xác nhận ngoài băng (out-of-band) cho thay đổi thanh toán hoặc yêu cầu chuyển tiền có rủi ro cao, theo danh bạ đã xác minh trước.
- Diễn tập phishing có mục tiêu đào tạo, tôn trọng người dùng và tập trung cải thiện kiểm soát hệ thống.

## 8. Kiểm soát hành động sau đăng nhập

Một cuộc phishing có thể thành công mà người dùng không nhận ra. Vì vậy hệ thống cần giảm tác động ngay cả khi kẻ tấn công đã có phiên.

### Kiểm tra quyền ở server

Mọi yêu cầu tài nguyên cần kiểm tra:

- Phiên/token có hợp lệ, còn hạn và đúng issuer/audience?
- Danh tính trong phiên là ai, tài khoản còn hoạt động không?
- Chủ thể có quyền thực hiện **hành động này trên tài nguyên cụ thể** không?
- Ngữ cảnh có bất thường hoặc vượt mức rủi ro cho phép không?

Không coi “đã đăng nhập” là quyền quản trị. Token có chữ ký hợp lệ cũng không có nghĩa mọi claim về vai trò luôn còn phù hợp nếu quyền đã thay đổi.

### Ràng buộc giao dịch

Với thao tác như chuyển tiền, thay người nhận, cấp quyền hoặc xuất dữ liệu hàng loạt:

1. Hiển thị rõ chi tiết hành động và tài nguyên đích.
2. Yêu cầu xác thực tăng cường nếu mức rủi ro đòi hỏi.
3. Ràng buộc xác nhận với đúng chi tiết giao dịch khi giao thức/kiến trúc hỗ trợ.
4. Phát hiện thay đổi nội dung sau bước xác nhận.
5. Ghi nhận người thực hiện, thời điểm, tài nguyên, kết quả và tín hiệu rủi ro.
6. Cung cấp cách hủy hoặc báo cáo ngay khi người dùng nhận ra hành động bất thường.

Một mã OTP được nhập đúng trước khi trang hiển thị số tài khoản nhận tiền không chứng minh người dùng đã chấp thuận chính số tài khoản đó.

## 9. Phát hiện dấu hiệu phishing và lạm dụng

Không nên dựa vào một tín hiệu như IP lạ để kết luận chắc chắn tài khoản bị chiếm. Kết hợp nhiều tín hiệu, so sánh với hành vi trước và điều chỉnh phản ứng theo rủi ro.

| Tín hiệu | Điều cần xem xét | Phản ứng có thể phù hợp |
|---|---|---|
| Nhiều lần đăng nhập thất bại trên nhiều tài khoản | Password spraying hoặc bot | Rate limit, challenge, giám sát nguồn và tài khoản |
| Đăng nhập thành công ngay sau chuỗi OTP thất bại | Relay/phishing hoặc người dùng gặp khó khăn | Step-up, cảnh báo, rà soát phiên |
| Push MFA liên tục nhưng người dùng không tương tác | MFA bombing | Chặn push tạm thời, yêu cầu phương thức khác, hướng dẫn báo cáo |
| Thêm authenticator mới rồi thay email khôi phục | Dấu hiệu duy trì chiếm quyền | Xác thực lại, trì hoãn thay đổi rủi ro nếu chính sách quy định, cảnh báo |
| Refresh token xuất hiện ở môi trường bất thường | Token bị đánh cắp hoặc đồng bộ thiết bị | Thu hồi token/phiên liên quan, yêu cầu đăng nhập lại |
| OAuth grant mới yêu cầu quyền rộng | Consent phishing hoặc ứng dụng mới | Kiểm tra nhà phát hành, quyền, thu hồi grant đáng ngờ |
| Thay người nhận thanh toán ngay sau đăng nhập | Gian lận giao dịch | Xác minh ngoài băng và tạm dừng theo chính sách |
| Tạo rule chuyển tiếp email hoặc xóa cảnh báo | Duy trì quyền kiểm soát hộp thư | Điều tra mailbox, xóa rule trái phép, thu hồi phiên |

Log cần hữu ích cho điều tra nhưng không lưu bí mật. Không ghi mật khẩu, OTP, recovery code, khóa riêng, cookie hoặc bearer token nguyên vẹn. Sử dụng định danh sự kiện, session ID không mang quyền và metadata đã giảm thiểu.

## 10. Ứng phó khi người dùng đã nhập credential vào trang giả

Phản ứng cần nhanh, có thứ tự và theo mức độ bằng chứng. Nếu nghi ngờ mật khẩu bị lộ, không chỉ yêu cầu người dùng “đổi mật khẩu” rồi kết thúc.

### Quy trình xử lý tham khảo

1. **Tiếp nhận và xác định phạm vi:** hỏi kênh nhận thông điệp, thời điểm, trang/ứng dụng đã mở, loại thông tin đã nhập và hành động đã chấp thuận. Không yêu cầu người dùng gửi lại mật khẩu hoặc OTP.
2. **Ngăn truy cập tiếp diễn:** nếu có bằng chứng đáng tin cậy, khóa hoặc giới hạn tài khoản theo quy trình; thu hồi phiên, refresh token và grant đáng ngờ.
3. **Đổi hoặc thu hồi credential:** đặt lại mật khẩu từ trang/ứng dụng chính thức; thu hồi TOTP secret, passkey hoặc chứng chỉ bị nghi lộ khi phù hợp.
4. **Kiểm tra phương thức khôi phục:** rà soát email, số điện thoại, recovery code, authenticator mới và liên kết IdP đã thay đổi.
5. **Điều tra hành động:** xem lịch sử đăng nhập, API, thay đổi quyền, mailbox rule, consent và giao dịch sau thời điểm nghi lộ.
6. **Khôi phục có kiểm soát:** xác minh lại chủ tài khoản qua kênh tin cậy; đăng ký credential mới và cấp lại quyền phù hợp.
7. **Thông báo và theo dõi:** cung cấp cách nhận hỗ trợ, cảnh báo hoạt động còn rủi ro và theo dõi dấu hiệu tái xâm nhập.

Nếu người dùng chỉ nhập mật khẩu vào trang giả nhưng chưa nhập OTP, kẻ tấn công vẫn có thể thử mật khẩu hoặc dùng nó ở dịch vụ khác. Nếu người dùng nhập OTP vào proxy, cần xem xét khả năng phiên đã bị lấy. Nếu người dùng chấp thuận OAuth, đổi mật khẩu có thể không thu hồi quyền ứng dụng; phải rà soát và thu hồi grant.

### Cây quyết định phản ứng

~~~mermaid
flowchart TD
    I["Báo cáo phishing"] --> Q{"Đã nhập thông tin hoặc chấp thuận?"}
    Q -->|"Chưa"| B["Chặn URL / báo cáo / kiểm tra thiết bị"]
    Q -->|"Có"| T{"Đã nhập loại nào?"}
    T -->|"Mật khẩu"| P["Đổi mật khẩu qua kênh chính thức"]
    T -->|"OTP / push"| M["Giả định có thể đã bị relay; rà soát phiên"]
    T -->|"Cookie / token"| S["Thu hồi phiên và token liên quan"]
    T -->|"OAuth consent"| O["Thu hồi grant và token ứng dụng"]
    P --> R["Rà soát authenticator, recovery, quyền và log"]
    M --> R
    S --> R
    O --> R
    R --> F["Xác minh chủ thể và khôi phục có kiểm soát"]
~~~

## 11. Ví dụ threat model: cổng nhân sự

**Bối cảnh:** Nhân viên dùng email công ty để truy cập cổng nhân sự. Đăng nhập hỗ trợ mật khẩu + TOTP; một số tài khoản đã có passkey. Sau đăng nhập, nhân viên có thể xem bảng lương, cập nhật thông tin cá nhân và gửi yêu cầu thay đổi tài khoản nhận lương.

### Tài sản, đe dọa và kiểm soát

| Thành phần | Mô tả |
|---|---|
| Tài sản cần bảo vệ | Bảng lương, thông tin định danh, email khôi phục, phiên đăng nhập, thay đổi tài khoản nhận lương |
| Đối thủ | Kẻ gửi phishing bên ngoài, người có tài khoản bị chiếm, ứng dụng OAuth độc hại |
| Điểm vào | Email, SMS, QR, trang đăng nhập, trang MFA, luồng reset, consent OAuth |
| Điểm yếu tiềm tàng | Mật khẩu tái sử dụng, TOTP có thể relay, push fatigue, phiên sống lâu, reset yếu |
| Tác động | Lộ dữ liệu, mạo danh nhân viên, gian lận lương, mở rộng phishing nội bộ |

### Kịch bản tấn công

1. Kẻ tấn công gửi email giả thông báo “Cập nhật chính sách lương”, kèm liên kết đến tên miền gần giống cổng nhân sự.
2. Nhân viên nhập mật khẩu và mã TOTP.
3. Proxy AiTM chuyển tiếp cả hai đến cổng thật và lấy cookie phiên.
4. Kẻ tấn công dùng cookie để truy cập bảng lương và thay đổi thông tin khôi phục.
5. Kẻ tấn công yêu cầu thay đổi tài khoản nhận lương hoặc dùng mailbox bị chiếm để gửi email phishing tiếp theo.

### Thiết kế giảm thiểu

- Chuyển tài khoản có quyền truy cập nhạy cảm sang passkey/WebAuthn; rà soát và giới hạn đường dự phòng OTP/mật khẩu.
- Giới hạn thời hạn phiên, phát hiện refresh token bất thường và hỗ trợ thu hồi nhanh.
- Thêm step-up và xác minh ngoài băng với thay đổi tài khoản nhận lương, sử dụng số liên hệ đã xác minh trước đó.
- Yêu cầu xác thực lại và cảnh báo khi thêm authenticator, đổi email hoặc số điện thoại khôi phục.
- Phân quyền ở API theo nhân viên, quản lý và bộ phận; không cho phép xem bảng lương chỉ vì có phiên hợp lệ.
- Giám sát thay đổi quyền, mailbox forwarding, OAuth grant và giao dịch lương.
- Đào tạo người dùng nhận biết tên miền giả, QR lạ và yêu cầu xác thực không do họ khởi tạo; cung cấp kênh báo cáo dễ sử dụng.

**Tiêu chí thành công:** khi người dùng nhập mật khẩu/OTP vào trang giả, thiết kế giảm khả năng kẻ tấn công tạo phiên hợp lệ; nếu phiên vẫn bị chiếm, họ không thể tự thay thông tin khôi phục hoặc thay tài khoản nhận lương mà không vượt qua kiểm soát bổ sung.

## 12. Kế hoạch kiểm thử chống phishing

Các kiểm thử nên thực hiện trong môi trường được phép, dùng tài khoản và dữ liệu thử nghiệm. Mục đích là xác nhận kiểm soát, không thu thập bí mật thật của người dùng.

| Kiểm thử | Cách mô phỏng an toàn | Kết quả mong đợi |
|---|---|---|
| Tên miền giả | Dùng trang thử nghiệm trên domain kiểm soát và không thu credential thật | Người dùng nhận biết; passkey không tạo assertion cho RP ID thật |
| OTP relay | Dùng mã giả trong môi trường kiểm thử | Challenge và giới hạn thử được áp dụng; không cấp phiên khi bằng chứng sai/hết hạn |
| Replay challenge | Gửi lại assertion/challenge đã tiêu thụ trong lab | Server từ chối |
| Origin sai | Thay origin trong dữ liệu thử | WebAuthn verifier từ chối |
| RP ID sai | Thử assertion gắn RP ID khác | Server từ chối |
| Push fatigue | Tạo chuỗi push trong môi trường thử | Rate limit, number matching hoặc chặn yêu cầu hoạt động |
| Thêm authenticator trái phép | Thử dùng phiên có mức xác thực thấp để thêm khóa | Yêu cầu re-auth/step-up và quyền phù hợp |
| Reset tài khoản | Dùng token reset hết hạn hoặc dùng lại | Từ chối, không thay credential |
| Chiếm phiên | Dùng token thử nghiệm đã thu hồi | API từ chối |
| OAuth consent | Cấp grant thử có quyền rộng | Chính sách ứng dụng/consent chặn hoặc yêu cầu phê duyệt |
| Thay đổi giao dịch | Thay người nhận sau bước xác nhận trong lab | Giao dịch bị từ chối hoặc phải xác nhận lại chi tiết mới |

### Chỉ số theo dõi

Không nên chỉ đo “tỷ lệ nhấp phishing”. Các chỉ số có ích hơn gồm:

- Tỷ lệ đăng nhập bằng phương thức chống phishing trên nhóm tài khoản mục tiêu.
- Tỷ lệ yêu cầu MFA không do người dùng khởi tạo và tỷ lệ bị từ chối/báo cáo.
- Thời gian từ báo cáo đến thu hồi phiên/token đáng ngờ.
- Tỷ lệ tài khoản có nhiều phương thức khôi phục an toàn.
- Số thay đổi authenticator, email khôi phục hoặc OAuth grant bất thường.
- Số giao dịch nhạy cảm bị chặn hoặc xác minh lại do tín hiệu rủi ro.
- Tỷ lệ hoàn tất quy trình phản ứng mà không cần thu thập bí mật người dùng.

Chỉ số phải được diễn giải trong ngữ cảnh: tăng số báo cáo có thể phản ánh khả năng phát hiện tốt hơn chứ không nhất thiết phishing tăng.

## 13. Checklist thiết kế

- [ ] Xác định tài sản: mật khẩu, OTP, passkey, token, cookie, recovery code, OAuth grant và giao dịch.
- [ ] Liệt kê kênh phishing và các bên có thể bị mạo danh.
- [ ] Xác định điểm nào nhận credential, điểm nào xác minh và điểm nào cấp phiên.
- [ ] Ưu tiên WebAuthn/passkey cho tài khoản có rủi ro cao; xác minh challenge, origin, RP ID, chữ ký và flags.
- [ ] Nếu dùng TOTP/push, giới hạn thử và chống lạm dụng; nhận thức khả năng relay/push fatigue.
- [ ] Bảo vệ đăng ký, thêm, thay và thu hồi authenticator bằng xác thực lại phù hợp.
- [ ] Bảo vệ cookie, refresh token, access token, OAuth grant và phiên sau đăng nhập.
- [ ] Xác thực tăng cường và ràng buộc chi tiết cho thao tác nhạy cảm.
- [ ] Kiểm tra quyền ở cấp tài nguyên/hành động tại API.
- [ ] Đường khôi phục đạt mức bảo đảm tương xứng; không tạo lối vòng yếu.
- [ ] Có giám sát dấu hiệu bất thường và khả năng thu hồi phiên/token nhanh.
- [ ] Có quy trình báo cáo và phản ứng sự cố; không yêu cầu người dùng gửi mật khẩu/OTP.
- [ ] Kiểm thử phishing, AiTM, replay, OAuth consent, session theft và social engineering trong môi trường được phép.
- [ ] Log phục vụ điều tra nhưng không chứa bí mật hoặc token sử dụng được.

## Ghi nhớ

Phishing khai thác niềm tin để lấy credential, chuyển tiếp MFA, chiếm phiên hoặc khiến người dùng cấp quyền/thực hiện giao dịch. Mật khẩu và OTP có thể bị nhập vào trang giả; push có thể bị lạm dụng; passkey/WebAuthn giảm mạnh nguy cơ phishing giả mạo origin nhờ bằng chứng mật mã gắn với RP, nhưng không thay thế bảo vệ client, phiên, khôi phục và phân quyền.

Một thiết kế xác thực chống phishing cần trả lời bốn câu hỏi: **Người dùng đang xác thực với đúng dịch vụ nào? Bằng chứng có gắn với đúng origin/challenge không? Phiên hoặc quyền nào được cấp sau đó? Và nếu kẻ tấn công đã lấy được một phần bằng chứng, hệ thống có thể phát hiện, thu hồi và phục hồi an toàn đến đâu?**
