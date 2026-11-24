# Authentication factor trong IAM: yếu tố xác thực và vòng đời sử dụng

> **Chương:** Authentication  
> **Bài:** Authentication factor  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Phạm vi:** Các loại yếu tố xác thực, cách kết hợp trong MFA, mức bảo đảm, cơ chế chống lừa đảo, đăng ký–thay đổi–thu hồi yếu tố trong vòng đời danh tính **Joiner–Mover–Leaver (JML)** và liên hệ với IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán.

## 1. Vì sao cần hiểu đúng authentication factor?

Giả sử một nhân viên đăng nhập hệ thống kế toán bằng mật khẩu. Kẻ tấn công lấy được mật khẩu từ một trang giả mạo. Nếu ứng dụng chỉ yêu cầu mật khẩu, kẻ tấn công có thể thử đăng nhập như nhân viên đó. Nếu có thêm một yếu tố xác thực độc lập, xác suất sử dụng thành công một mật khẩu bị lộ sẽ giảm đáng kể.

Nhưng câu hỏi không chỉ là “có bật MFA hay không”:

- Hệ thống đang kiểm tra **loại bằng chứng nào**?
- Hai bước đăng nhập có thực sự thuộc **hai nhóm yếu tố độc lập** không?
- Yếu tố đó có thể bị lừa nhập vào trang giả mạo hoặc bị chiếm qua điện thoại không?
- Nếu người dùng đổi điện thoại, chuyển vai trò hoặc nghỉ việc, ai quản lý yếu tố đã đăng ký?
- Đăng nhập thành công có đồng nghĩa người dùng được phép xem mọi dữ liệu không?

**Authentication factor (yếu tố xác thực)** là một loại bằng chứng giúp hệ thống kiểm tra một chủ thể có quyền sử dụng danh tính được khai báo. Các nhóm kinh điển là **điều chủ thể biết**, **điều chủ thể sở hữu/kiểm soát**, và **đặc điểm sinh trắc của chủ thể**. Khi phối hợp các nhóm yếu tố và cơ chế xác thực phù hợp, hệ thống có thể tăng độ tin cậy vào quá trình đăng nhập.

**Authentication (xác thực)** trả lời “chủ thể đang yêu cầu truy cập có chứng minh được danh tính theo cơ chế được chấp nhận hay không?”. **Authorization (phân quyền)** trả lời “chủ thể đã được nhận diện có được thực hiện hành động này trên tài nguyên này không?”. Đây là hai bước liên quan nhưng khác nhau.

### 1.1. Ví dụ đặt trong IAM lifecycle

Nhân viên Lan vào làm (Joiner), được xác minh danh tính và đăng ký passkey trên thiết bị được chấp thuận. Sau sáu tháng, Lan chuyển sang quản trị hệ thống (Mover): quyền mới có thể yêu cầu phương thức xác thực có độ bảo đảm cao hơn và một bước xác minh bổ sung khi thực hiện thao tác đặc quyền. Khi Lan nghỉ việc (Leaver), tổ chức cần khóa khả năng xác thực tài khoản, thu hồi hoặc làm mất hiệu lực các authenticator/credential gắn với danh tính, kiểm tra phiên hiện hành và xử lý quyền truy cập còn sót ở các ứng dụng đích.

Chỉ yêu cầu MFA vào ngày đầu mà không quản lý quá trình đổi, mất, khôi phục và thu hồi yếu tố thì IAM lifecycle vẫn chưa hoàn chỉnh.

## 2. Ba nhóm authentication factor cơ bản

| Nhóm | Câu hỏi bản chất | Ví dụ | Rủi ro điển hình |
|---|---|---|---|
| **Knowledge — Something you know** | Người dùng biết bí mật nào? | Mật khẩu, PIN dùng để xác thực từ xa, câu trả lời bí mật (không khuyến khích) | Đoán, tái sử dụng, phishing, rò rỉ dữ liệu |
| **Possession — Something you have** | Người dùng đang kiểm soát vật thể/khóa nào? | Security key FIDO, authenticator chứa khóa, thiết bị nhận token một lần, smart card | Mất cắp, chuyển quyền thiết bị, key/token bị sao chép hoặc bị lừa sử dụng |
| **Inherence — Something you are** | Thuộc tính sinh trắc nào được đối chiếu? | Vân tay, khuôn mặt, mống mắt qua cảm biến phù hợp | Giả mạo sinh trắc, giới hạn cảm biến, khó thay đổi đặc điểm khi bị lộ |

Đây là ba nhóm kinh điển dùng để phân tích MFA. Một số tài liệu còn nói về vị trí, hành vi hoặc môi trường (*somewhere you are*, *something you do*). Trong mô hình kiểm soát IAM, những tín hiệu này thường nên được phân biệt là **ngữ cảnh/rủi ro** chứ không mặc nhiên tính là một nhóm yếu tố MFA độc lập đạt chuẩn.

### 2.1. Nhóm điều người dùng biết

Mật khẩu và PIN đều là ví dụ của nhóm knowledge. Dùng **mật khẩu + một PIN tĩnh khác** không tự động trở thành MFA hai yếu tố, vì cả hai vẫn là bí mật do người dùng biết.

Kiểm soát phù hợp gồm:

- Kiểm tra bí mật bị lộ hoặc nằm trong danh sách mật khẩu phổ biến, theo khả năng của hệ thống.
- Chống thử đoán bằng rate limiting, phát hiện bất thường, bảo vệ phiên và quy trình khôi phục có kiểm soát.
- Không lưu mật khẩu dạng rõ; dùng cơ chế lưu trữ mật khẩu chuyên dụng, có salt và hàm băm thích hợp.
- Không sử dụng câu hỏi bảo mật dễ suy đoán làm cơ chế xác thực hoặc khôi phục mạnh.
- Hạn chế yêu cầu đổi mật khẩu tùy tiện khi không có lý do bảo mật; tập trung vào mật khẩu có dấu hiệu bị lộ và cơ chế bảo vệ thực tế.

Không nhầm **PIN mở khóa bộ xác thực cục bộ** với việc gửi một PIN như mật khẩu tới máy chủ. Cách PIN đóng góp cho bảo đảm xác thực phụ thuộc giao thức và cách authenticator bảo vệ khóa.

### 2.2. Nhóm điều người dùng kiểm soát

Một security key hoặc phần cứng chứa khóa riêng có thể ký thử thách do server tạo để chứng minh quyền kiểm soát khóa. Một ứng dụng OTP có thể giữ bí mật dùng tạo mã. Một SIM/điện thoại có thể nhận mã qua SMS.

Các phương án trên không có cùng khả năng chống lừa đảo. **Có thêm yếu tố possession không đồng nghĩa tự động chống phishing**: kẻ tấn công có thể dụ người dùng nhập mã OTP vào trang giả mạo ngay khi mã còn hiệu lực.

### 2.3. Nhóm sinh trắc

Vân tay hoặc khuôn mặt có thể được dùng để mở khóa một authenticator trên thiết bị. Ví dụ, passkey có khóa riêng được bảo vệ trên thiết bị; thao tác sinh trắc giúp xác minh người đang sử dụng trước khi khóa thực hiện ký.

Trong thiết kế như vậy, **server thường không nhận trực tiếp ảnh vân tay hoặc khuôn mặt** từ quá trình WebAuthn thông thường; server nhận bằng chứng mật mã từ authenticator và các cờ/thuộc tính theo giao thức.

Sinh trắc có giới hạn: sai số nhận dạng, nguy cơ giả mạo cảm biến, tính không thể thay đổi của đặc điểm sinh học và yêu cầu hỗ trợ người dùng không thể dùng cảm biến. Cần có phương án thay thế/khôi phục đủ an toàn và phù hợp.

## 3. Factor, authenticator và credential khác nhau thế nào?

Một sai lầm phổ biến là dùng ba từ này như từ đồng nghĩa.

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Factor** | Nhóm loại bằng chứng được dùng khi xác thực | Knowledge, possession, inherence |
| **Authenticator** | Thiết bị/phần mềm/cơ chế được sử dụng để chứng minh một hoặc nhiều yếu tố | Security key, ứng dụng TOTP, platform authenticator |
| **Credential** | Bí mật hoặc vật liệu xác thực được liên kết với danh tính và authenticator | Public/private key pair, TOTP seed, mật khẩu |
| **Verifier** | Thành phần xác minh bằng chứng xác thực | IdP kiểm tra TOTP; Relying Party kiểm tra WebAuthn assertion |
| **Authenticator binding** | Quan hệ đăng ký giữa authenticator/credential và một danh tính | User `emp-204` có một passkey và một security key dự phòng |
| **Authentication event** | Một lần chứng minh danh tính theo giao thức | Phiên đăng nhập bằng passkey được chấp nhận lúc 09:10 |

Một thiết bị có thể hỗ trợ nhiều loại authenticator. Ngược lại, một authenticator đa yếu tố có thể kết hợp **bằng chứng sở hữu khóa mật mã** với **xác minh người dùng cục bộ bằng PIN hoặc sinh trắc**, tùy loại thiết bị/giao thức và chính sách.

**Đếm số màn hình, số lần chạm hoặc số thông báo không phải cách xác định số yếu tố.** Phải phân tích bằng chứng nào được kiểm chứng và sự độc lập của các yếu tố đó.

### 3.1. Authentication vs verification vs identification

- **Identification:** khai báo hoặc tìm ra danh tính được yêu cầu, ví dụ username, account ID.
- **Identity proofing/enrollment verification:** kiểm tra một cá nhân có thực sự là người được ghi trong hồ sơ trước khi cấp hoặc khôi phục danh tính.
- **Authentication:** chứng minh người yêu cầu đang kiểm soát authenticator/credential gắn với danh tính.
- **Authorization:** xét quyền trên tài nguyên cụ thể.
- **Accounting/audit:** ghi nhận sự kiện, nguồn, kết quả và điều kiện đã áp dụng.

Có một tên người dùng đúng không đủ để được xác thực. Có một session hợp lệ cũng không tự cấp quyền phê duyệt thanh toán nếu principal thiếu entitlement.

## 4. Single-factor, 2FA và MFA

**Single-factor authentication (SFA)** dựa trên một nhóm yếu tố. **Two-factor authentication (2FA)** dùng hai nhóm yếu tố phù hợp. **Multi-factor authentication (MFA)** sử dụng ít nhất hai yếu tố thuộc các nhóm độc lập; số bước đăng nhập không phải số yếu tố.

| Phương pháp | Phân tích yếu tố | Có phải MFA? | Điểm cần lưu ý |
|---|---|---|---|
| Mật khẩu | Knowledge | Không | Dễ bị phishing hoặc lộ mật khẩu |
| Mật khẩu + câu hỏi bí mật | Knowledge + knowledge | Không nên coi là MFA | Hai bí mật cùng nhóm, câu hỏi dễ bị dò |
| Mật khẩu + mã từ ứng dụng TOTP | Knowledge + possession của thiết bị/secret OTP | Có thể là MFA | Mã OTP vẫn có thể bị phishing và relay |
| Mật khẩu + mã SMS | Knowledge + kênh nhận mã trên thiết bị/SIM | Có thể là MFA | Rủi ro SIM swap, chuyển tiếp số, phishing; đánh giá theo chính sách |
| Mật khẩu + PIN được hỏi từ xa | Knowledge + knowledge | Không | Thêm bước, không thêm nhóm |
| Security key với xác minh người dùng cục bộ | Possession khóa + kiểm tra PIN/sinh trắc tại authenticator | Có thể đáp ứng yêu cầu MFA tùy phương thức và chính sách | Cần kiểm tra user verification, cách quản lý khóa và mức bảo đảm |
| Passkey dùng sinh trắc trên thiết bị | Bằng chứng kiểm soát khóa + user verification tại thiết bị | Có thể cung cấp trải nghiệm MFA | Không kết luận mức bảo đảm chỉ từ chữ “passkey” |
| Mã OTP qua email đang mở trên cùng thiết bị | Phụ thuộc cách bảo vệ tài khoản email/kênh nhận mã | Không nên mặc định độc lập | Nếu email bị chiếm cùng lúc, bằng chứng bổ sung rất yếu |

### 4.1. MFA không phải bảo đảm tuyệt đối

MFA giảm nhiều nguy cơ nhưng không loại bỏ:

- Phishing thời gian thực lấy mật khẩu và mã OTP.
- Đánh cắp session cookie hoặc token sau đăng nhập.
- Push fatigue khiến người dùng chấp nhận yêu cầu trái phép.
- Khôi phục tài khoản quá yếu cho phép thay authenticator.
- Malware trên endpoint, quyền ứng dụng cấp quá rộng hoặc lạm dụng phiên đã xác thực.

Do đó cần kết hợp MFA với **bảo vệ session, giới hạn quyền, phát hiện rủi ro và kiểm toán**.

## 5. Các loại authenticator thường gặp

### 5.1. Mật khẩu và passphrase

Mật khẩu là bí mật người dùng biết. Có thể phù hợp khi hệ thống vẫn hỗ trợ nhưng cần chính sách chống đoán, bảo vệ lưu trữ và cân nhắc yếu tố bổ sung cho các tài nguyên quan trọng.

Không gửi mật khẩu cho dịch vụ khác để “xác nhận giúp” khi không có giao thức và mục đích bảo mật hợp lệ. Tránh chia sẻ chung một tài khoản và mật khẩu cho nhiều người; audit sẽ khó phân biệt chủ thể.

### 5.2. HOTP và TOTP

**HOTP** tạo mã một lần dựa trên bộ đếm; **TOTP** biến thể thường gặp dùng thời gian. Verifier và authenticator có thể chia sẻ một bí mật gốc để tính mã, với cơ chế chấp nhận giá trị trong cửa sổ phù hợp.

~~~text
Người dùng đăng ký ứng dụng TOTP
        |
        v
Ứng dụng lưu bí mật OTP được cấp
        |
        v
Khi đăng nhập: người dùng nhập mã hiện tại
        |
        v
Verifier tính/kiểm tra mã, thời gian, số lần thử
        |
        v
Cho phép tiếp tục hoặc từ chối
~~~

Lưu ý:

- Bí mật TOTP phải được bảo vệ; nếu bị sao chép, bên khác cũng có thể tạo mã.
- Mã có thời hạn nhưng vẫn có thể bị thu thập và chuyển tiếp bởi trang giả mạo trong thời gian hiệu lực.
- Verifier cần giới hạn số lần thử, xử lý sai lệch thời gian và cơ chế chống dùng lại trong phạm vi chính sách.
- QR dùng đăng ký seed không nên bị lưu/chụp/chia sẻ rộng; nó có thể chứa thông tin đủ để sao chép authenticator.

TOTP là biện pháp bổ sung hữu ích nhưng **không có tính chất ràng buộc origin như WebAuthn**, nên không tự được gọi là phishing-resistant.

### 5.3. SMS và cuộc gọi thoại

Mã gửi qua SMS hoặc thoại sử dụng kênh điện thoại để hỗ trợ xác minh quyền kiểm soát. Các nguy cơ gồm **SIM swap**, chuyển số, chuyển tiếp tin nhắn/cuộc gọi, phishing và phụ thuộc hạ tầng viễn thông.

Khi tổ chức có thể triển khai cơ chế chống phishing tốt hơn, nên đánh giá chuyển sang passkey/FIDO2 hoặc giải pháp phù hợp. Nếu tạm dùng SMS, cần giới hạn rủi ro, hỗ trợ khôi phục an toàn và theo dõi hành vi bất thường; không dùng số điện thoại như bằng chứng danh tính bất biến.

### 5.4. Push notification

Ứng dụng xác thực gửi một yêu cầu để người dùng chấp nhận/từ chối. Nếu người dùng chỉ cần bấm “Approve”, kẻ tấn công biết mật khẩu có thể lặp yêu cầu và gây **MFA fatigue**.

Kiểm soát có thể gồm:

- Number matching hoặc liên kết rõ thông tin giao dịch/phiên.
- Hiển thị ứng dụng, vùng địa lý xấp xỉ hoặc ngữ cảnh khi dữ liệu đủ tin cậy.
- Giới hạn số push, phát hiện nhiều lần từ chối hoặc yêu cầu bất thường.
- Đào tạo người dùng từ chối các yêu cầu không tự khởi tạo và báo sự cố.

Number matching giúp giảm nhầm lẫn/push fatigue nhưng **không biến mọi push OTP thành phương thức chống phishing tương đương WebAuthn**.

### 5.5. Smart card, chứng chỉ và hardware security key

Một smart card hoặc security key có thể chứa khóa riêng, tạo chữ ký khi xác thực và bảo vệ khỏi xuất khóa tùy thiết bị. Để sử dụng an toàn cần:

- Cấp phát và liên kết đúng người/thiết bị.
- Bảo vệ khóa riêng, PIN nếu có và chính sách thử sai.
- Kiểm tra chứng chỉ, nguồn phát hành và thời hạn khi cơ chế dùng PKI.
- Quy trình thu hồi khi mất, hỏng, nghỉ việc.
- Phương án dự phòng có kiểm soát để tránh tài khoản bị khóa vĩnh viễn.

**Không phải mọi cách dùng chứng chỉ đều tự động chống phishing ở mức tương đương FIDO2.** Đánh giá phải dựa vào giao thức và cách ràng buộc bằng chứng với phiên/đích xác thực.

## 6. Passkeys, FIDO2/WebAuthn và chống phishing

**WebAuthn** cho phép một website/service (relying party, RP) đăng ký một credential khóa công khai và sau đó yêu cầu authenticator ký một thử thách. **FIDO2** thường được dùng để nói đến hệ sinh thái WebAuthn kết hợp giao thức giữa client và authenticator. **Passkey** là cách triển khai/diễn đạt phổ biến cho credential xác thực không mật khẩu dựa trên FIDO.

### 6.1. Khái niệm cốt lõi

- **Relying party (RP):** dịch vụ yêu cầu xác thực.
- **Authenticator:** thiết bị/phần mềm giữ credential và thực hiện ký.
- **Public key:** được RP lưu để xác minh bằng chứng.
- **Private key:** do authenticator quản lý, không gửi cho RP trong luồng xác thực thông thường.
- **Challenge:** dữ liệu mới để chống tái phát lại bằng chứng.
- **Origin / RP ID:** thông tin giúp ràng buộc xác thực với đúng website hoặc miền tin cậy.
- **User presence (UP):** tín hiệu người dùng đã tương tác với authenticator khi cần.
- **User verification (UV):** tín hiệu xác minh người dùng cục bộ, ví dụ PIN hoặc sinh trắc khi cơ chế hỗ trợ.

### 6.2. Mô hình xác thực bằng passkey

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt / ứng dụng client
    participant A as Authenticator / passkey
    participant R as IdP hoặc RP
    U->>B: Chọn đăng nhập bằng passkey
    B->>R: Yêu cầu challenge
    R-->>B: Challenge + yêu cầu RP
    B->>A: Yêu cầu tạo assertion theo RP ID
    A->>U: Yêu cầu tương tác / user verification phù hợp
    U-->>A: Hoàn tất PIN / sinh trắc nếu cần
    A-->>B: Assertion đã ký bằng credential
    B->>R: Gửi assertion
    R->>R: Kiểm tra challenge, origin, RP ID, chữ ký, cờ UP/UV và chính sách
    R-->>B: Xác thực thành công hoặc từ chối
~~~

Luồng minh họa. Các bước thực tế phụ thuộc trình duyệt, nền tảng, phương thức chọn credential và yêu cầu RP.

### 6.3. Vì sao WebAuthn chống phishing tốt hơn OTP?

Một trang giả mạo có thể yêu cầu người dùng nhập mã TOTP vào form và chuyển mã đó sang website thật. Với WebAuthn triển khai đúng, authenticator tạo bằng chứng cho **RP ID/origin hợp lệ**; trang giả mạo ở miền khác không thể đơn giản dùng chữ ký đó như một bằng chứng hợp lệ cho website thật.

Tuy vậy, WebAuthn không bảo đảm ứng dụng miễn nhiễm mọi kiểu tấn công. Hệ thống vẫn phải xử lý session hijacking, thiết bị bị chiếm quyền, khôi phục tài khoản không an toàn, đăng ký credential độc hại hoặc sai cấu hình RP.

### 6.4. Device-bound và syncable passkeys

Passkey có thể gắn với một authenticator/thiết bị hoặc có thể được đồng bộ qua một hệ sinh thái quản lý credential. Điều này tạo đánh đổi giữa **khả năng khôi phục và tính sẵn sàng** với **mô hình bảo vệ khóa, đồng bộ và quản trị thiết bị**.

- Khóa phần cứng chuyên dụng có thể tạo ràng buộc mạnh với một thiết bị; phải quản lý cấp phát, mất/hỏng và dự phòng.
- Passkey đồng bộ giúp người dùng sử dụng nhiều thiết bị, nhưng tổ chức cần đánh giá bảo vệ tài khoản đồng bộ, chính sách thiết bị và bằng chứng mức bảo đảm.
- Không khẳng định **mọi passkey đều đạt một mức bảo đảm cao nhất** chỉ vì đều dùng FIDO/WebAuthn; tính phù hợp phụ thuộc cách triển khai và chính sách.

## 7. MFA, độ bảo đảm xác thực và chính sách theo rủi ro

Các tổ chức có thể phân loại phương thức xác thực theo **mức bảo đảm (authentication assurance)**. Một số chuẩn tham chiếu dùng các cấp Authentication Assurance Level (AAL), nhưng **không nên suy ra mức đạt được chỉ từ tên công nghệ**. Yêu cầu có thể bao gồm loại authenticator, khả năng chống phishing, chống phát lại, cách đăng ký, bảo vệ credential, recovery và chính sách phiên.

| Tình huống | Mục tiêu xác thực | Ví dụ kiểm soát cần cân nhắc |
|---|---|---|
| Xem cổng thông tin nội bộ ít nhạy cảm | Xác thực đủ theo chính sách cơ sở | SSO, xác minh tài khoản active, MFA theo đánh giá rủi ro |
| Truy cập thông tin khách hàng | Giảm nguy cơ phishing/chiếm quyền | MFA phù hợp, hạn chế session và kiểm tra thiết bị |
| Phê duyệt thanh toán | Độ tin cậy cao hơn, có thể step-up | MFA chống phishing khi hỗ trợ, tái xác thực và kiểm tra quyền giao dịch |
| Quản trị IdP/cloud production | Giảm nguy cơ chiếm đặc quyền | Phương thức mạnh, PAM/JIT, thiết bị tin cậy và audit |
| Khôi phục authenticator bị mất | Ngăn chiếm quyền qua helpdesk | Xác minh danh tính độc lập, phê duyệt/giám sát theo mức rủi ro |

### 7.1. Adaptive/risk-based authentication

**Risk-based authentication** có thể xem xét các tín hiệu như thiết bị đã đăng ký, hành vi đăng nhập, vị trí bất thường, mức độ nhạy cảm tài nguyên hoặc trạng thái phiên. Hệ thống có thể yêu cầu xác thực bổ sung, hạn chế hoặc từ chối truy cập theo policy.

Lưu ý: địa chỉ IP, vị trí, thiết bị và mẫu hành vi thường là **tín hiệu ngữ cảnh**. Không tự coi chúng là yếu tố MFA độc lập chỉ vì hệ thống thu thập được chúng.

### 7.2. Step-up authentication

Một người dùng có thể đăng nhập vào portal bằng phương thức cơ sở nhưng khi nhấn “Duyệt khoản thanh toán lớn”, API/ứng dụng yêu cầu **step-up**: chứng minh lại danh tính bằng phương thức đủ mạnh và đủ mới.

Bước step-up nên gắn với **hành động nhạy cảm**, chính sách và thời gian xác thực. Xác thực lại không thay thế quyền nghiệp vụ: người không có role `payment.approver` vẫn phải bị từ chối ngay cả khi vượt qua MFA mạnh.

## 8. Authentication factor trong IdP, SSO và OAuth/OIDC

IdP thường là điểm trung tâm để người dùng đăng ký authenticator và thực hiện MFA. Ứng dụng dựa vào kết quả xác thực qua giao thức được hỗ trợ, ví dụ OIDC hoặc SAML. Tuy nhiên **SSO không tự bảo đảm mọi ứng dụng đều yêu cầu cùng mức xác thực**, đặc biệt với phiên ứng dụng đã tồn tại hoặc ứng dụng có local login riêng.

### 8.1. Đường đi của một yêu cầu đăng nhập

~~~mermaid
flowchart LR
    U[Người dùng] --> A[Ứng dụng / Relying Party]
    A --> I[IdP / Authorization Server]
    I --> P[Chính sách xác thực và risk]
    P --> F[Authenticator đã đăng ký]
    F --> V[Verifier kiểm tra bằng chứng]
    V --> I
    I --> S[Phát kết quả xác thực / phiên theo giao thức]
    S --> A
    A --> Z[Authorization tại ứng dụng / API]
~~~

Khi ứng dụng cần mức bảo đảm cao, nó có thể đưa yêu cầu xác thực vào giao thức theo khả năng hỗ trợ và kiểm tra kết quả thật sự do IdP xác nhận. Không nên giả định rằng việc dùng SSO đồng nghĩa đã có MFA tại thời điểm thao tác.

### 8.2. AMR, ACR và auth_time

Trong một số triển khai OIDC, token hoặc thông tin từ IdP có thể chứa:

- **`amr` (Authentication Methods References):** thông tin về phương thức xác thực đã được sử dụng, theo ngữ nghĩa của issuer.
- **`acr` (Authentication Context Class Reference):** giá trị lớp/ngữ cảnh xác thực theo hợp đồng của IdP và RP.
- **`auth_time`:** thời điểm xác thực người dùng theo giao thức.

Các claim này **không được coi là một từ điển phổ quát với giá trị giống nhau trên mọi IdP**. API/ứng dụng phải xác minh token/nguồn tin cậy, hiểu chính sách ánh xạ và bảo đảm rằng mức xác thực thực sự đáp ứng yêu cầu nghiệp vụ.

### 8.3. ID token, access token và quyền

- **ID token** trong OIDC phục vụ việc diễn đạt kết quả xác thực người dùng cho client phù hợp.
- **Access token** được dùng để API đánh giá yêu cầu truy cập theo audience, scope/role, thời hạn và chính sách.
- **Session** là trạng thái đăng nhập/ủy quyền được duy trì bởi IdP hoặc ứng dụng tùy kiến trúc.

Không dùng ID token như giấy phép gọi mọi API, không tin claim do client tự gửi và không kết luận người dùng đủ quyền chỉ vì họ vừa hoàn thành MFA.

### 8.4. SCIM làm gì với yếu tố xác thực?

**SCIM** hỗ trợ provisioning danh tính/nhóm giữa hệ thống tương thích. Nó không mặc nhiên đăng ký passkey, xoay vòng TOTP seed, thu hồi security key hoặc hủy session theo mọi ứng dụng.

Một Leaver có thể yêu cầu **SCIM/connector** vô hiệu hóa account tại SaaS và **IdP/authenticator-management** gỡ credential, khóa đăng nhập mới; còn ứng dụng đích phải xử lý session/tokens đang tồn tại theo cơ chế riêng.

## 9. Đăng ký authentication factor: Joiner

Đăng ký một yếu tố xác thực là thao tác nhạy cảm: nếu kẻ tấn công có thể thêm authenticator của mình vào tài khoản nạn nhân, MFA sẽ không còn bảo vệ như mong đợi.

### 9.1. Quy trình enrollment điển hình

1. **Identity proofing:** nguồn có thẩm quyền xác nhận danh tính người mới và ngày hiệu lực.
2. **Xác thực lần đầu:** người dùng đi qua luồng khởi tạo có kiểm soát; hạn chế liên kết đăng ký và thời gian hiệu lực.
3. **Chọn phương thức:** theo loại tài khoản, mức rủi ro, thiết bị và chính sách của tổ chức.
4. **Bind credential:** authenticator/credential được liên kết với identity ID ổn định trong IdP.
5. **Kiểm chứng sở hữu:** yêu cầu người dùng hoàn tất thử thách xác thực để chứng minh authenticator hoạt động.
6. **Đăng ký dự phòng:** cung cấp cơ chế dự phòng hợp lệ phù hợp rủi ro và chính sách.
7. **Thông báo/kiểm toán:** ghi thời điểm, phương thức, ID credential theo metadata và sự kiện enrollment.
8. **Xác minh tại ứng dụng:** thử đăng nhập hợp lệ và từ chối trường hợp thiếu yếu tố hoặc sai mức assurance.

**Không gửi OTP seed, private key hoặc mã dự phòng nguyên dạng vào log hoặc ticket.** Nếu cần hỗ trợ, chỉ lưu metadata tối thiểu đủ truy vết, không lưu bí mật.

### 9.2. Vì sao cần authenticator dự phòng?

Người dùng có thể làm mất điện thoại hoặc hỏng security key. Khi đó nếu không có phương án dự phòng, tổ chức có thể phải thực hiện khôi phục tài khoản rủi ro cao. Phương án dự phòng có thể là security key thứ hai, passkey hợp lệ ở thiết bị khác hoặc quy trình recovery có xác minh mạnh.

Tuy nhiên không thể tạo một “cửa hậu” quá yếu: nếu người dùng có thể vô hiệu hóa passkey mạnh chỉ bằng trả lời câu hỏi dễ đoán, toàn bộ chính sách bị kéo xuống mức yếu của recovery.

### 9.3. Ví dụ metadata cho một yếu tố đã đăng ký

~~~json
{
  "identityId": "emp-204",
  "authenticatorId": "auth-7f42",
  "kind": "WEBAUTHN_CREDENTIAL",
  "registrationStatus": "ACTIVE",
  "registeredAt": "2026-11-23T09:00:00+07:00",
  "verified": true,
  "usageScope": "corporate-idp",
  "ownerTeam": "identity-security",
  "lastReviewRequired": false
}
~~~

Dữ liệu là **schema minh họa**, không phải thông tin từ một IdP thực tế; cần lưu đủ dữ liệu công khai/metadata phục vụ xác thực và audit theo giao thức nhưng không tùy tiện công khai thông tin nhạy cảm hoặc private key.

## 10. Mover: thay yếu tố và mức xác thực khi vai trò thay đổi

**Mover** có thể là chuyển bộ phận, thay thiết bị, đổi số điện thoại, được cấp chức năng đặc quyền hoặc đổi phương thức xác thực theo chính sách.

### 10.1. Nâng lên vai trò đặc quyền

Kỹ sư Nam trước đây chỉ đọc log. Khi được cấp quyền quản trị production, chính sách có thể yêu cầu:

- Đăng ký phương thức xác thực chống phishing đáp ứng yêu cầu mới.
- Sử dụng thiết bị được quản lý/đạt điều kiện truy cập.
- Kích hoạt quyền PAM/JIT trong khoảng thời gian đã duyệt.
- Step-up khi thực hiện thao tác nhạy cảm.
- Kiểm tra role/entitlement thực tế trên cloud và API.

**Điểm quan trọng:** thêm security key mạnh không tự cấp quyền admin. Ngược lại, cấp role admin mà không thỏa điều kiện xác thực chỉ nên tạo trạng thái chưa được phép sử dụng quyền đó theo chính sách.

### 10.2. Đổi điện thoại hoặc mất authenticator

Một người dùng đổi điện thoại cần quy trình:

1. Xác minh danh tính và quyền thực hiện thay đổi theo mức rủi ro.
2. Gắn authenticator mới, hoàn tất kiểm chứng.
3. Xác định authenticator cũ còn do người dùng kiểm soát không.
4. Thu hồi authenticator cũ khi không còn đáng tin hoặc không cần thiết.
5. Cân nhắc chấm dứt session, refresh token hay thay các kênh recovery nếu có rủi ro.
6. Thông báo sự kiện và lưu bằng chứng; giám sát hành động bất thường ngay sau khi thay.

Không nên mặc định **đổi số điện thoại** tự chứng minh người dùng vẫn kiểm soát danh tính. Quy trình thay đổi số có thể là điểm yếu cho social engineering và SIM swap.

### 10.3. Chuyển vai trò không nên giữ cơ chế xác thực đặc biệt quá hạn

Nếu một nhóm được phép dùng cơ chế emergency bypass trong thời gian xử lý sự cố, khi dự án/ca trực kết thúc phải thu hồi bypass và kiểm chứng trạng thái. Quyền ngoại lệ xác thực tồn dư có thể nguy hiểm ngang quyền quản trị tồn dư.

## 11. Leaver: thu hồi yếu tố xác thực và chặn các đường đăng nhập

Khi một người nghỉ việc, chỉ xóa một authenticator ở IdP có thể không đủ nếu tài khoản vẫn được phép đăng nhập bằng mật khẩu, token khác hoặc tài khoản cục bộ. Ngược lại, chỉ disable account nhưng không xử lý các phiên và credential độc lập cũng có thể giữ lại đường truy cập.

Một Leaver nên bao gồm:

1. Xác minh sự kiện có thẩm quyền và thời điểm hiệu lực.
2. Chặn đăng nhập mới tại IdP theo chính sách.
3. Thu hồi hoặc vô hiệu hóa các credential/authenticator gắn với danh tính khi phù hợp, bao gồm passkey binding, TOTP, security key, password, recovery factors.
4. Thu hồi refresh token, session, API key và quyền ứng dụng ở các hệ thống hỗ trợ.
5. Kiểm tra local account và ứng dụng không sử dụng SSO.
6. Điều phối SCIM/API để deprovision account và group/role ở ứng dụng đích.
7. Xử lý quyền trên cloud, VPN, thiết bị, tài khoản dịch vụ thuộc phạm vi cần thu hồi.
8. Đối soát trạng thái tại từng đích, ghi trường hợp chưa thể xác minh.

### 11.1. Khóa IdP có làm mất hiệu lực session cũ?

Không nhất thiết. Một số ứng dụng giữ session cookie riêng hoặc chấp nhận access token đã phát hành đến lúc hết hạn. Cần phân biệt:

- Không cho xác thực mới tại IdP.
- Không cấp token mới mang quyền cũ.
- Làm mất hiệu lực hoặc chờ hết hạn token/session cũ theo cơ chế hỗ trợ.
- Xác minh API/ứng dụng từ chối hành động không còn hợp lệ.

Đối với quyền cao, tổ chức nên có quy trình chặn khẩn cấp hoặc biện pháp giảm rủi ro theo khả năng kỹ thuật, không dựa duy nhất vào tuổi đời session.

### 11.2. Authenticator bị mất nhưng người dùng chưa nghỉ

Đó **không phải Leaver của người dùng**. Tài khoản có thể vẫn cần hoạt động; hãy thu hồi authenticator bị mất, yêu cầu đăng ký lại qua recovery được kiểm soát và đánh giá lại session. Không xóa toàn bộ identity khi chỉ một thiết bị/khóa bị mất.

## 12. Recovery: mắt xích có thể làm suy yếu MFA

Trong thực tế, tấn công thường nhắm vào việc **đăng ký lại yếu tố** hơn là phá mật mã của phương thức mạnh. Ví dụ kẻ gian gọi helpdesk giả làm lãnh đạo, yêu cầu “reset MFA ngay” để thêm điện thoại của mình.

### 12.1. Các mẫu tấn công recovery

- **Helpdesk social engineering:** thuyết phục nhân viên hỗ trợ bỏ MFA mà không xác minh danh tính đủ mạnh.
- **SIM swap/number takeover:** chiếm số điện thoại dùng nhận mã khôi phục.
- **Email account takeover:** chiếm hộp thư được dùng làm kênh recovery.
- **Session hijacking:** dùng phiên đã chiếm để đăng ký thêm authenticator.
- **Recovery code theft:** lấy mã dự phòng từ tệp hoặc tin nhắn không được bảo vệ.
- **Administrator misuse:** người có quyền helpdesk thao tác ngoài quy trình mà không được phê duyệt.

### 12.2. Thiết kế quy trình khôi phục an toàn

- Dùng bước **re-proofing/verification** tương xứng độ nhạy cảm danh tính và vai trò.
- Có cơ chế kiểm tra độc lập và phê duyệt bổ sung với tài khoản đặc quyền.
- Không để một yêu cầu qua điện thoại không được xác minh làm mất hiệu lực toàn bộ yếu tố mạnh.
- Gửi thông báo bảo mật qua kênh tin cậy khi thêm/xóa authenticator.
- Xem xét độ trễ hoặc giới hạn quyền nhạy cảm sau recovery nếu rủi ro yêu cầu.
- Ghi sự kiện, người xử lý, phương thức xác minh và correlation ID.
- Thu hồi authenticator bị mất và kiểm tra session/tokens liên quan.
- Cung cấp cơ chế hỗ trợ người dùng không có smartphone hoặc không thể sử dụng sinh trắc, nhưng không hạ chuẩn bảo mật một cách tùy tiện.

Recovery cần được thử nghiệm như một **luồng xác thực nhạy cảm**, không phải thao tác phụ của helpdesk.

## 13. MFA và phân quyền: RBAC/ABAC trong quyết định truy cập

Authentication factor chỉ giúp hệ thống xác minh danh tính. Mức đặc quyền và quyền với tài nguyên cần được xác định riêng.

### 13.1. RBAC: vai trò nghiệp vụ

Giả sử IdP xác thực một nhân viên bằng passkey mạnh, nhưng nhân viên có role `invoice.viewer`. Khi gửi yêu cầu `invoice.approve`, API phải từ chối vì role không cho phép phê duyệt.

**MFA mạnh không nâng cấp user từ viewer thành approver.**

### 13.2. ABAC: điều kiện thuộc tính và ngữ cảnh

ABAC có thể kết hợp:

| Thành phần | Ví dụ | Cần kiểm tra |
|---|---|---|
| User | `employmentStatus=active`, `department=finance` | Thuộc tính từ nguồn có thẩm quyền |
| Role | `payment-approver` | Role/entitlement được cấp thực tế |
| Authentication | Phương thức, thời điểm xác thực, mức bảo đảm | Thông tin đã được IdP xác nhận và đủ mới |
| Device | Managed, compliant, posture | Tín hiệu thiết bị được tin cậy, không tự khai báo |
| Resource | Khoản thanh toán, hạn mức, tenant | Dữ liệu thật và policy của API |
| Action | `approve`, `export` | Kiểm tra trên chính hành động được gọi |

Một pseudo-policy minh họa:

~~~text
function authorizePaymentApproval(request):
    principal = verifyAuthenticatedPrincipal(request)
    resource = loadPaymentFromTrustedStore(request.paymentId)
    assurance = getVerifiedAuthenticationContext(principal.session)

    if principal.employmentStatus != ACTIVE:
        return DENY
    if not principal.hasRole("payment-approver"):
        return DENY
    if resource.department != principal.department:
        return DENY
    if resource.amount > principal.approvalLimit:
        return DENY
    if assurance.isTooOld or not assurance.meetsPolicy:
        return REQUIRE_STEP_UP
    if resource.createdBy == principal.userId and policy.prohibitsSelfApproval:
        return DENY

    return ALLOW
~~~

Đây là **pseudocode**, không phải mã tích hợp sẵn. Các trường như role, authentication method hay department phải được xác minh qua nguồn đáng tin; không tin header hoặc JSON tự khai báo từ client.

### 13.3. Tài nguyên khác nhau có yêu cầu factor khác nhau

Một công ty có thể cho đọc thông báo nội bộ bằng SSO và yêu cầu MFA mạnh hơn cho xuất dữ liệu hàng loạt. Cần ghi rõ **policy nào áp dụng cho ứng dụng/hành động nào** và kiểm tra thực thi ở IdP/API, không dựa vào việc ẩn nút giao diện.

## 14. Tài khoản dịch vụ và authentication factor

Danh tính máy (*service account*, *service principal*, *workload identity*) thường không có người để nhập OTP hoặc chạm sinh trắc. Vì vậy không nên thiết kế pipeline đòi một nhân viên bấm MFA mỗi giờ để job định kỳ có thể chạy. Đây vừa là chống đối tự động hóa, vừa dẫn đến giải pháp vòng như chia sẻ tài khoản cá nhân hoặc tắt MFA.

Với workload, cần chọn cơ chế **machine authentication** phù hợp:

- Workload identity federation gắn issuer, subject, audience và trust policy để nhận credential ngắn hạn.
- OAuth 2.0 Client Credentials khi API và authorization server hỗ trợ, kết hợp xác thực client được phê duyệt.
- Chứng chỉ/mTLS để xác thực dịch vụ hoặc kênh theo thiết kế.
- Khóa/secret được bảo vệ trong secret manager khi chưa thể dùng federation, có rotation và thời hạn.
- Role/permission tối thiểu theo ứng dụng, môi trường và tài nguyên.

Những cơ chế này **không nên bị gọi là MFA của người dùng** chỉ vì có nhiều bước mật mã. Đối với thao tác **người dùng quản trị credential/service identity**, lại có thể yêu cầu MFA/step-up cho người vận hành.

### 14.1. Joiner–Mover–Leaver của workload

- **Joiner:** đăng ký principal, owner, trust source, scopes và vòng đời credential.
- **Mover:** đổi API, môi trường, owner hoặc quyền; đánh giá quyền cũ, thay trust/credential khi cần.
- **Leaver:** thu hồi principal, secret, certificates, role, API grants và trust binding; kiểm tra tại đích.

Không dùng tài khoản cá nhân của nhân viên để chạy job thường trực. Khi nhân viên nghỉ việc, quyền cá nhân và authentication factor của họ phải được thu hồi, còn workload hợp lệ cần được bàn giao owner và credential theo quy trình riêng.

## 15. Kiểm toán authentication factor và sự kiện MFA

### 15.1. Bằng chứng cần thiết

Hệ thống nên có khả năng truy vết:

- Identity ID, loại subject, trạng thái và nguồn sự kiện.
- Loại authenticator và ID liên kết (không phải credential bí mật).
- Thời điểm đăng ký, đổi, khóa, gỡ và người phê duyệt nếu cần.
- Phương thức xác thực đã dùng, policy/assurance được thỏa hay bị từ chối.
- Thời gian, ứng dụng, ngữ cảnh thiết bị và rủi ro đủ để điều tra theo chính sách.
- Các lần thất bại, push bị từ chối, recovery, bypass và thao tác helpdesk.
- Các kết quả thu hồi sau Mover/Leaver, bằng chứng tại IdP và ứng dụng đích.
- Ngoại lệ đang mở, owner, hạn xử lý và kết quả readback.

Không ghi password, OTP, TOTP seed, private key, recovery code hoặc token truy cập nguyên dạng vào log.

### 15.2. Ví dụ audit event khi xóa authenticator

~~~json
{
  "eventId": "iam-auth-2026-0418",
  "identityId": "emp-204",
  "eventType": "AUTHENTICATOR_REVOKED",
  "authenticatorId": "auth-7f42",
  "authenticatorType": "WEBAUTHN_CREDENTIAL",
  "reason": "DEVICE_LOST",
  "initiatedBy": "verified-helpdesk-workflow",
  "verificationStatus": "CONFIRMED_UNBOUND",
  "sessionReviewStatus": "COMPLETED",
  "correlationId": "INC-3127"
}
~~~

Đây là dữ liệu giả lập minh họa. `CONFIRMED_UNBOUND` chỉ nên được ghi sau khi có bằng chứng credential đã bị ngắt khỏi identity trong hệ thống có thẩm quyền; phải xử lý các phiên còn tồn tại theo chính sách riêng.

### 15.3. Một số chỉ số vận hành

| Chỉ số | Ý nghĩa | Cần tránh diễn giải sai |
|---|---|---|
| Tỷ lệ danh tính có authenticator phù hợp | Mức phủ phương thức theo từng nhóm rủi ro | Đếm số tài khoản có “một yếu tố bất kỳ” là đạt tất cả yêu cầu |
| Tỷ lệ đăng nhập dùng MFA chống phishing | Giảm rủi ro phishing theo chính sách | Gộp TOTP/SMS với WebAuthn mà không phân biệt |
| Tỷ lệ đăng ký có xác minh thành công | Chất lượng onboarding authenticator | Chỉ đếm nút “đã thêm” |
| Thời gian xử lý mất authenticator | Khả năng hỗ trợ người dùng và chặn rủi ro | Khôi phục nhanh bằng quy trình yếu |
| Số lần push bị từ chối và yêu cầu bất thường | Phát hiện khả năng MFA fatigue | Kết luận chắc chắn tấn công từ một dấu hiệu |
| Số bypass/recovery quá hạn | Điểm yếu tồn dư cần xử lý | Ngoại lệ không có owner/hạn |
| Thời gian gỡ authenticator sau Leaver | Chất lượng thu hồi ở IdP | Đồng nhất gỡ authenticator với hết toàn bộ session |

## 16. Các hiểu lầm nguy hiểm

**“Mật khẩu + PIN là MFA.”** Không, nếu cả hai đều thuộc nhóm knowledge được đưa cho hệ thống như những bí mật độc lập cùng loại.

**“TOTP là chống phishing vì mã thay đổi mỗi 30 giây.”** Không. Kẻ tấn công có thể relay mã còn hạn đến trang thật.

**“Sinh trắc có nghĩa server đang giữ ảnh vân tay.”** Không nhất thiết. Trong nhiều mô hình passkey/WebAuthn, sinh trắc được dùng cục bộ để mở khóa credential; server xác minh bằng chứng mật mã.

**“Một passkey trên mọi thiết bị đều có assurance giống nhau.”** Không. Tính đồng bộ, bảo vệ khóa, user verification, thiết bị và yêu cầu policy có thể khác.

**“MFA thành công nghĩa là có quyền truy cập mọi dữ liệu.”** Không. Authorization theo RBAC/ABAC, resource và SoD vẫn phải thực thi.

**“SSO đã bật MFA thì mọi ứng dụng và phiên hiện hành đều an toàn.”** Không. Cần kiểm tra policy, tình trạng session, local login và quyền ứng dụng.

**“Khóa user ở IdP là vô hiệu ngay mọi access token.”** Không mặc định; phụ thuộc token, giao thức, thời hạn và biện pháp revoke của mỗi hệ thống.

**“Nhân viên mất điện thoại thì tắt MFA tạm cho tiện.”** Đây là nguy cơ account takeover. Phải dùng recovery có xác minh tương xứng rủi ro.

**“Tài khoản dịch vụ cũng phải có người nhập OTP.”** Workload cần cơ chế xác thực máy riêng, còn người quản trị workload phải tuân thủ chính sách MFA phù hợp.

## 17. Tình huống tự kiểm tra

### Tình huống A: hai mật khẩu

Một ứng dụng yêu cầu nhập mật khẩu tài khoản rồi mật khẩu phụ để tải dữ liệu nhạy cảm. Nhà phát triển quảng bá là “MFA hai lớp”.

**Phân tích:** Đây vẫn là hai bằng chứng knowledge, không đương nhiên là hai yếu tố. Cần xem cơ chế xác thực độc lập hơn và kiểm soát dữ liệu theo chính sách.

### Tình huống B: TOTP bị lừa nhập vào trang giả

Nhân viên nhận đường dẫn login giống thật, nhập mật khẩu và TOTP; kẻ tấn công sử dụng ngay mã đó ở website thật.

**Phân tích:** TOTP có thể bị phishing thời gian thực. Đánh giá áp dụng WebAuthn/FIDO2 chống phishing, bảo vệ session và cơ chế phát hiện đăng nhập bất thường.

### Tình huống C: mất điện thoại và gọi helpdesk

Người gọi tự xưng là trưởng phòng, yêu cầu gỡ MFA để đăng nhập production nhưng không thể thực hiện quy trình xác minh đã định.

**Phân tích:** Không hạ bỏ xác thực chỉ từ chức danh hoặc áp lực thời gian. Dùng quy trình recovery đã phê duyệt, xác minh độc lập, cảnh báo và audit.

### Tình huống D: quản trị viên được nâng quyền

Một kỹ sư vừa hoàn thành MFA khi vào portal, sau đó muốn thay policy IAM production.

**Phân tích:** Có thể cần step-up mới hoặc phương thức mạnh hơn tùy chính sách. API vẫn kiểm tra role, SoD, thời hạn PAM/JIT, thiết bị và quyền trên tài nguyên.

### Tình huống E: nhân viên nghỉ việc nhưng phiên SaaS còn sống

IdP đã disable tài khoản, nhưng user vẫn mở một SaaS tab có session cookie hợp lệ.

**Phân tích:** Leaver phải xử lý các session và quyền đích theo khả năng nền tảng; IdP disable là cần thiết nhưng không đủ để tuyên bố chấm dứt mọi truy cập.

### Tình huống F: job không có màn hình

Job đồng bộ hóa dữ liệu cần chạy mỗi đêm, một kỹ sư đề xuất dùng tài khoản cá nhân có SMS OTP rồi cấu hình điện thoại tự đọc mã.

**Phân tích:** Dùng workload identity hoặc cơ chế machine authentication phù hợp, không tự động hóa MFA của người dùng bằng cách chia sẻ credential. Xác định owner, quyền tối thiểu, credential rotation và thu hồi theo JML.

## 18. Checklist thiết kế authentication factor

Khi triển khai hoặc rà soát xác thực trong IAM, lần lượt trả lời:

1. **Chủ thể:** user, đối tác hay workload? Có phương thức phù hợp từng loại?
2. **Factor:** các bằng chứng thuộc nhóm nào, có độc lập hay chỉ thêm bước cùng nhóm?
3. **Authenticator:** phần mềm/thiết bị nào kiểm chứng bằng chứng, ai sở hữu và ai quản lý?
4. **Chống phishing:** phương thức có ràng buộc với RP/origin hay chỉ dùng OTP có thể relay?
5. **Assurance:** chính sách yêu cầu mức bảo đảm nào cho từng tài nguyên và hoạt động?
6. **Enrollment:** người được đăng ký đã qua xác minh danh tính và chứng minh kiểm soát authenticator chưa?
7. **Dự phòng/recovery:** nếu mất thiết bị, cơ chế khôi phục có yếu hơn phương thức chính không?
8. **Mover:** nâng quyền có yêu cầu phương thức mạnh hơn, step-up, PAM/JIT và rà soát bypass không?
9. **Leaver:** đã thu hồi authenticator, credential và kiểm soát session/token ở IdP/ứng dụng đích chưa?
10. **IdP/SSO:** ứng dụng có đọc và xác minh ngữ cảnh xác thực theo đúng hợp đồng issuer không?
11. **SCIM:** có phân biệt provisioning user/group với quản lý authenticator không?
12. **Authorization:** RBAC/ABAC/SoD và resource-level permission vẫn được thực thi độc lập?
13. **Service accounts:** job có danh tính máy riêng và không lạm dụng MFA của tài khoản cá nhân?
14. **Audit:** có bằng chứng đăng ký, thay đổi, thu hồi, recovery và quyết định step-up?
15. **Ngoại lệ:** tài khoản chưa hỗ trợ phương thức mục tiêu có phương án xử lý, owner và hạn phê duyệt?
16. **Readback:** trạng thái thật đã được kiểm chứng sau Joiner/Mover/Leaver, không chỉ nhận phản hồi lệnh?

---

**Ghi nhớ:** Authentication factor là **loại bằng chứng xác thực**, không phải số bước đăng nhập. MFA hữu ích khi kết hợp các yếu tố phù hợp nhưng khả năng chống phishing và mức bảo đảm thay đổi theo authenticator/giao thức. Trong IAM lifecycle, phải quản lý đầy đủ **đăng ký, sử dụng, step-up, thay thế, recovery và thu hồi** yếu tố, liên kết với IdP/SSO mà không nhầm với SCIM provisioning hoặc quyền RBAC/ABAC. Chỉ khi xác minh cả trạng thái authenticator, phiên và quyền ở các hệ thống liên quan, tổ chức mới giảm được nguy cơ chiếm tài khoản và **quyền truy cập tồn dư**.
