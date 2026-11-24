# Possession factor trong MFA: chứng minh quyền kiểm soát thiết bị và quản lý vòng đời

Trong **Multi-Factor Authentication (MFA)**, **possession factor** là **yếu tố sở hữu**: người dùng chứng minh rằng họ đang kiểm soát một **authenticator** hoặc một **bí mật/khóa xác thực** được gắn với tài khoản theo quy trình tin cậy. Ví dụ, người dùng nhập mã do ứng dụng authenticator trên điện thoại tạo ra, chạm vào khóa bảo mật FIDO2 hoặc ký một thử thách bằng khóa riêng được bảo vệ trong thiết bị.

Khái niệm này thường được diễn đạt là **“something you have”** — thứ bạn có. Tuy nhiên, **có thiết bị vật lý không tự động đồng nghĩa đã chứng minh yếu tố sở hữu**. Hệ thống phải kiểm tra **bằng chứng mật mã hoặc bằng chứng kiểm soát authenticator** gắn với một yêu cầu xác thực cụ thể. Một số phương thức, như OTP qua SMS hoặc ứng dụng tạo mã, có giới hạn bảo mật khác với khóa FIDO2/WebAuthn.

Bài học nằm trong chương **MFA** của module **Identity Lifecycle trong IAM**, nơi danh tính và quyền truy cập được quản lý xuyên suốt **Joiner–Mover–Leaver (JML)**. Ngoài cơ chế sở hữu, bài giải thích cách **đăng ký, ràng buộc, thay thế, khôi phục và thu hồi authenticator** khi HRIS cập nhật trạng thái nhân sự, IdP/SSO xác thực người dùng, SCIM provisioning account, và các chính sách RBAC/ABAC thay đổi quyền. Mục tiêu là bảo vệ cả **tính xác thực** lẫn **vòng đời thiết bị/credential**, tránh để những yếu tố MFA cũ trở thành đường truy cập tồn dư.

## 1. Possession factor là gì?

MFA yêu cầu **ít nhất hai yếu tố thuộc những loại độc lập khác nhau** theo mô hình xác thực được sử dụng. Ba loại kinh điển là:

| Nhóm yếu tố | Câu hỏi cần chứng minh | Ví dụ | Điều cần phân biệt |
| --- | --- | --- | --- |
| **Knowledge — điều bạn biết** | Người dùng biết một bí mật đã đăng ký? | Mật khẩu, PIN theo ngữ cảnh phù hợp. | Hai mật khẩu hoặc mật khẩu cộng câu hỏi bí mật thường vẫn chỉ thuộc loại knowledge. |
| **Possession — điều bạn sở hữu/kiểm soát** | Chủ thể kiểm soát authenticator hoặc khóa được hệ thống tin cậy? | Khóa FIDO2, thiết bị tạo OTP, smart card. | Chỉ khai “tôi có điện thoại” không đủ chứng minh possession. |
| **Inherence — đặc điểm của bạn** | Một đặc điểm sinh trắc có được kiểm chứng theo cơ chế thiết kế? | Vân tay, khuôn mặt, khi được dùng đúng cách. | Biometric mở khóa thiết bị không nhất thiết được IdP nhận trực tiếp; cần hiểu vị trí kiểm chứng. |

**Ví dụ so sánh:**

- **Mật khẩu + mã TOTP từ ứng dụng authenticator** thường đại diện cho knowledge và possession, nếu secret TOTP được bảo vệ, đã đăng ký đúng người và hệ thống kiểm chứng phù hợp.
- **Mật khẩu + PIN của cùng một account** vẫn là hai bí mật người dùng biết; không tự trở thành MFA độc lập.
- **Khóa bảo mật có PIN hoặc user verification phù hợp** có thể cung cấp xác thực nhiều yếu tố bằng một authenticator, nếu giao thức và chính sách thực sự bảo đảm cả quyền sở hữu khóa lẫn bước xác minh người dùng.
- **Một passkey** có thể dùng user presence đơn thuần hoặc user verification (PIN/biometric cục bộ); không nên coi mọi passkey đều tự động đáp ứng cùng một mức bảo đảm MFA khi chưa kiểm tra thuộc tính xác thực.

### 1.1. Authenticator, credential và factor không hoàn toàn giống nhau

- **Authenticator:** thiết bị hoặc phần mềm cung cấp bằng chứng xác thực; ví dụ khóa bảo mật USB/NFC, ứng dụng tạo OTP, passkey provider.
- **Credential:** dữ liệu giúp verifier nhận ra hoặc kiểm tra authenticator; ví dụ khóa công khai gắn với tài khoản, một OTP seed được đăng ký, chứng chỉ.
- **Possession factor:** loại bằng chứng cho thấy chủ thể có quyền kiểm soát authenticator/khóa.
- **Verifier:** thành phần thực hiện kiểm tra bằng chứng; thường là IdP, authentication server hoặc ứng dụng.
- **Authenticator binding:** quan hệ đã xác minh giữa một identity/account và authenticator cụ thể.

Một chiếc điện thoại có thể chứa **nhiều authenticator**: ứng dụng TOTP, passkey đồng bộ, khóa riêng dành cho push xác thực, hoặc chứng chỉ trong kho khóa. Vì vậy **mất điện thoại** cần đánh giá các authenticator đã đăng ký và các credential khác nhau, chứ không chỉ một dòng “phone = lost”.

## 2. Các phương thức possession factor thường gặp

| Phương thức | Bằng chứng được kiểm tra | Điểm mạnh | Giới hạn/rủi ro điển hình |
| --- | --- | --- | --- |
| **HOTP** | Mã một lần tính từ shared secret và counter. | Có thể hoạt động không cần mạng ở thiết bị tạo mã; cơ chế đã được chuẩn hóa. | Secret có thể bị sao chép; người dùng có thể bị lừa nhập mã vào trang giả. |
| **TOTP** | Mã tính từ shared secret và thời gian. | Dễ triển khai, nhiều ứng dụng hỗ trợ. | Phụ thuộc bảo vệ seed và đồng hồ; mã có thể bị phishing, proxy hoặc malware lấy cắp. |
| **Hardware OTP token** | Mã OTP sinh bởi thiết bị chuyên dụng. | Giảm phụ thuộc điện thoại, có thể phù hợp quy trình doanh nghiệp. | OTP vẫn có thể bị phishing; mất token hoặc hỏng thiết bị phải được xử lý. |
| **Push authenticator** | Phê duyệt challenge tại ứng dụng/thiết bị đã đăng ký, đôi khi có chứng minh bằng khóa. | Trải nghiệm nhanh, có thể hiển thị thông tin ngữ cảnh và number matching. | MFA fatigue, prompt spoofing hoặc chấp thuận nhầm; mức bảo vệ phụ thuộc cơ chế và thiết kế. |
| **SMS/voice OTP** | Chứng minh có thể nhận mã qua kênh số điện thoại. | Dễ tiếp cận khi không có authenticator chuyên dụng. | SIM swap, chuyển số, mạng viễn thông, phishing; mức độ tin cậy cần đánh giá kỹ. |
| **FIDO2/WebAuthn security key** | Chữ ký challenge bằng khóa riêng trong authenticator, ràng buộc với RP ID/origin khi triển khai đúng. | Có khả năng chống phishing cao, không gửi shared secret hoặc OTP cho website. | Mất khóa, enrollment sai, chính sách attestation/user verification và hỗ trợ thiết bị cần quản lý. |
| **Passkey trên thiết bị** | WebAuthn credential dùng khóa riêng được bảo vệ bởi thiết bị hoặc nhà cung cấp passkey. | Không cần nhớ mật khẩu; có thể chống phishing bằng ràng buộc origin. | Cần phân biệt device-bound với synced passkey, trạng thái user verification và recovery. |
| **Smart card / certificate credential** | Ký challenge hoặc chứng minh kiểm soát khóa riêng và chứng chỉ tương ứng. | Có thể đáp ứng yêu cầu doanh nghiệp/quản lý chứng chỉ. | Cần PKI, cấp phát/thu hồi chứng chỉ, reader, PIN và quản lý khóa cẩn thận. |

Không có phương thức “tốt nhất” cho mọi trường hợp. Tổ chức phải chọn theo **mức rủi ro**, môi trường sử dụng, sự hỗ trợ của IdP/ứng dụng, khả năng phục hồi khi mất thiết bị và chính sách xác thực. Với tài khoản đặc quyền hoặc dữ liệu nhạy cảm, **phishing-resistant authentication** thường là mục tiêu quan trọng.

### 2.1. HOTP và TOTP hoạt động ra sao?

**HOTP** sử dụng một shared secret cùng giá trị counter; **TOTP** dựa trên ý tưởng tương tự nhưng biến thời gian thành giá trị tính toán. Server và authenticator có thông tin cần thiết để tạo/kiểm tra mã, thường là một chuỗi số có thời gian sử dụng ngắn.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng TOTP
    participant I as IdP / Verifier
    U->>I: Đăng nhập bằng yếu tố thứ nhất
    I-->>U: Yêu cầu mã TOTP
    U->>A: Mở authenticator
    A-->>U: Mã tính từ seed và thời gian
    U->>I: Gửi mã
    I->>I: Kiểm tra mã, thời gian, giới hạn thử/replay
    alt Hợp lệ
        I-->>U: Xác thực bước MFA hoàn thành
    else Không hợp lệ
        I-->>U: Từ chối/chờ thử lại theo chính sách
    end
~~~

**Điểm cốt lõi:** possession được suy ra từ việc bên gửi có khả năng tạo mã đúng bằng secret đã đăng ký. Nhưng **mã TOTP có thể bị người dùng vô tình đưa cho bên thứ ba** hoặc bị lấy qua trang phishing. Vì vậy TOTP không nên được mô tả là chống phishing tương đương WebAuthn.

**Seed/secret TOTP phải được bảo vệ** trong lúc enroll và lưu trữ; không ghi QR provisioning, seed, mã OTP hoặc recovery code vào log/ticket. TOTP còn cần đồng bộ đồng hồ và kiểm soát thử lại. Một số ứng dụng authenticator hỗ trợ đồng bộ seed giữa thiết bị; tính năng này thay đổi giả định về số nơi có thể tạo mã và cần được đánh giá theo chính sách.

### 2.2. SMS/voice OTP có phải possession factor mạnh?

Việc nhận SMS cho thấy người yêu cầu đang có khả năng truy cập **kênh chuyển mã đến số điện thoại** tại thời điểm đó, nhưng không chứng minh chắc chắn họ là người sở hữu chính thức số hoặc thiết bị vật lý. Số có thể bị chuyển sang SIM khác, bị tái sử dụng, chuyển tiếp hoặc bị chiếm qua quy trình nhà mạng.

Do đó, khi chọn SMS/voice làm yếu tố bổ sung, phải đánh giá **rủi ro chuyển số, SIM swap, phishing, mất sóng và khả năng khôi phục**. Không mặc nhiên coi SMS và khóa FIDO2 là hai phương thức có sức chống phishing ngang nhau. Một tổ chức có thể cho phép SMS ở phạm vi thấp hơn nhưng yêu cầu phương thức mạnh hơn cho hành động đặc quyền.

**Email OTP** càng phải được đánh giá cẩn thận: nếu cùng một phiên đăng nhập email có thể nhận mã hoặc email được bảo vệ bằng cùng credential bị đánh cắp, sự độc lập giữa yếu tố sẽ yếu. Không suy ra một mã đến email luôn là possession factor độc lập trong mọi kiến trúc.

### 2.3. Push MFA và nguy cơ MFA fatigue

Push MFA cho phép xác nhận yêu cầu trong ứng dụng đã đăng ký. Một thiết kế tốt có thể cung cấp **số đối chiếu (number matching)**, tên ứng dụng, vị trí tương đối và nội dung challenge; một số cơ chế còn dùng khóa riêng để ký bằng chứng thay vì chỉ gửi trạng thái “Approve”.

Tuy nhiên, nếu kẻ tấn công có mật khẩu và liên tục phát push, người dùng có thể **chấp thuận nhầm vì mệt mỏi**. Hệ thống nên giảm rủi ro bằng:

- Number matching hoặc ràng buộc challenge, theo khả năng sản phẩm.
- Hiển thị thông tin yêu cầu đủ rõ, không tiết lộ quá mức.
- Giới hạn số yêu cầu, giám sát push bất thường và cảnh báo.
- Cho phép người dùng **từ chối và báo cáo** yêu cầu mình không khởi tạo.
- Không coi một lần người dùng bấm “Approve” là bằng chứng tuyệt đối không có social engineering.

**Push không tự động là phishing-resistant** chỉ vì được gửi tới một thiết bị. Mức độ chống phishing phụ thuộc cách challenge được ràng buộc với phiên, origin và verifier.

## 3. WebAuthn/FIDO2: possession dựa trên khóa mật mã

Trong **WebAuthn**, authenticator thường tạo một cặp khóa công khai/riêng cho một **relying party (RP)**. RP lưu khóa công khai, còn khóa riêng được authenticator bảo vệ. Khi đăng nhập, RP gửi challenge; authenticator tạo assertion có chữ ký để RP kiểm chứng. Cơ chế WebAuthn đúng cách ràng buộc credential với **RP ID** và kiểm tra **origin**, giúp chống nhiều kiểu phishing chuyển tiếp mật khẩu/OTP.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / Client
    participant K as Authenticator
    participant R as RP / IdP
    U->>B: Bắt đầu đăng nhập
    B->>R: Yêu cầu challenge WebAuthn
    R-->>B: Challenge + RP parameters
    B->>K: Yêu cầu tạo assertion
    K->>K: Kiểm tra user presence / user verification theo yêu cầu
    K-->>B: Credential ID + signed assertion
    B->>R: Gửi assertion
    R->>R: Kiểm tra challenge, origin, RP ID, chữ ký, policy
    R-->>U: Chấp nhận hoặc từ chối
~~~

**Khác biệt với OTP:** người dùng không đọc một mã để nhập vào website; authenticator ký challenge dưới sự kiểm soát của RP. Trang giả mạo ở origin khác không thể đơn giản yêu cầu authenticator tạo assertion hợp lệ cho RP thật nếu trình duyệt, authenticator và server thực thi các kiểm tra đúng.

### 3.1. Possession, user presence và user verification

Ba khái niệm phải được phân biệt:

- **Possession:** kiểm soát được authenticator/khóa riêng.
- **User presence (UP):** authenticator có tín hiệu tương tác, ví dụ chạm một khóa.
- **User verification (UV):** authenticator kiểm tra một yếu tố cục bộ như PIN hoặc sinh trắc trước khi dùng khóa, theo chính sách và khả năng thiết bị.

**Chạm khóa** không nhất thiết tương đương **xác minh PIN hoặc biometric**. Nếu chính sách yêu cầu xác thực nhiều yếu tố ngay trong một authenticator, RP/IdP phải kiểm tra trạng thái **UV** theo thiết kế và không chấp nhận cơ chế chỉ user presence khi không đủ điều kiện.

Khi dùng passkey mở khóa bằng vân tay, vân tay thường được **kiểm tra cục bộ trên thiết bị**; website nhận bằng chứng WebAuthn thích hợp, **không cần và không nên nhận ảnh vân tay**. Tùy cơ chế, việc mở khóa thiết bị và chính sách UV có những mức bảo đảm khác nhau.

### 3.2. Device-bound và synced passkey

| Thuộc tính | Device-bound credential | Synced passkey |
| --- | --- | --- |
| Vị trí khóa riêng | Được thiết kế gắn với một authenticator/thiết bị cụ thể. | Có thể được đồng bộ/khôi phục qua hệ sinh thái passkey provider. |
| Thuận tiện khi đổi thiết bị | Cần đăng ký thêm hoặc quy trình recovery phù hợp. | Thường dễ tiếp tục sử dụng trên thiết bị khác trong cùng hệ sinh thái. |
| Kiểm soát vòng đời | Quản lý từng credential/thiết bị; cần kế hoạch khóa dự phòng. | Ngoài RP còn phải đánh giá chính sách bảo vệ đồng bộ, account provider và recovery. |
| Rủi ro | Mất/hỏng thiết bị, thiếu khóa dự phòng, quản lý enrollment. | Phụ thuộc bảo vệ account đồng bộ và quy trình khôi phục/đồng bộ nhiều thiết bị. |

Không nên kết luận **synced passkey luôn không an toàn**, cũng không mặc định rằng mọi passkey trên một điện thoại là **device-bound**. Doanh nghiệp phải xác định loại authenticator nào được cho phép theo độ nhạy account, khả năng xác minh thuộc tính cần thiết và chính sách của nền tảng.

Khi nhân viên mất thiết bị, **xóa passkey khỏi thiết bị cũ** có thể không xóa bản đồng bộ hoặc ràng buộc server. Quy trình cần **thu hồi credential binding tại RP/IdP** và đánh giá các phiên có hiệu lực. Việc khóa account đồng bộ của một nhà cung cấp cũng không nên được xem là bằng chứng duy nhất rằng tất cả credential đăng ký tại RP đã bị thu hồi.

### 3.3. Attestation và chính sách thiết bị

Một số tổ chức cần biết loại/cấp bảo đảm của authenticator, đặc biệt với quyền đặc quyền. **Attestation**, metadata thiết bị hoặc tính năng quản trị của IdP có thể hỗ trợ quyết định, nhưng chỉ khi hệ thống thật sự kiểm chứng đúng và có chính sách riêng tư phù hợp. **Không phải mọi trình duyệt, authenticator hoặc hệ sinh thái passkey đều cung cấp cùng mức dữ liệu**; không suy ra loại thiết bị chỉ từ tên hiển thị.

## 4. Possession factor không thay thế identity proofing

Một thiết bị xác thực có thể chứng minh rằng **người đang thao tác sở hữu credential đã đăng ký**, nhưng điều đó **không tự chứng minh credential được đăng ký cho đúng người ngay từ đầu**.

Ví dụ, trong quá trình Joiner, kẻ gian có thể cố đăng ký điện thoại của mình vào hồ sơ nhân viên mới nếu quy trình enrollment cho phép dùng duy nhất employee number hoặc một email chưa được xác minh. Về sau, TOTP/FIDO2 được sử dụng đúng kỹ thuật vẫn có thể thuộc **người sai**.

Ba bước khác nhau là:

1. **Identity proofing / nguồn danh tính đáng tin:** xác định đúng người và quan hệ hợp lệ theo quy trình.
2. **Authenticator binding:** liên kết credential cụ thể với đúng account đã được xác minh và có thẩm quyền.
3. **Authentication:** kiểm tra bằng chứng ở mỗi lần đăng nhập hoặc step-up.

**Không dùng employee identifier làm mã bí mật** để đăng ký MFA. Mã HR là dữ liệu nhận diện theo phạm vi được quy định, không thay thế kiểm tra danh tính và quyền kiểm soát account.

## 5. Vòng đời authenticator: đăng ký đến thu hồi

Một possession factor không “sống mãi” cùng tài khoản. Phải quản lý các trạng thái như **chưa đăng ký, đang chờ kích hoạt, hoạt động, bị treo, bị báo mất, đã thu hồi** và lưu lịch sử theo chính sách.

~~~mermaid
stateDiagram-v2
    [*] --> UNREGISTERED
    UNREGISTERED --> ENROLLMENT_PENDING: Yêu cầu đăng ký
    ENROLLMENT_PENDING --> ACTIVE: Xác minh + binding thành công
    ENROLLMENT_PENDING --> UNREGISTERED: Hủy/không đủ bằng chứng
    ACTIVE --> SUSPENDED: Tạm chặn có kiểm soát
    SUSPENDED --> ACTIVE: Khôi phục sau xác minh
    ACTIVE --> REVOKED: Leaver / mất / thay thế / nghi ngờ lộ
    SUSPENDED --> REVOKED: Thu hồi
    REVOKED --> [*]
~~~

Các tên trạng thái là **mô hình tham khảo**, không phải enum chuẩn của IdP. Nhiều IdP cung cấp các sự kiện như register/add/delete authenticator hoặc device state, còn quản lý **credential** và quản lý **thiết bị vật lý** có thể là hai danh mục riêng.

### 5.1. Đăng ký yếu tố sở hữu an toàn

Một enrollment flow nên:

1. Kiểm tra **account/identity được xác định đúng** và quan hệ đang có hiệu lực hoặc được phép chuẩn bị theo chính sách.
2. Kiểm tra người đang yêu cầu enrollment được xác thực/định danh ở mức phù hợp; lần đăng ký đầu tiên có thể cần quy trình identity proofing hoặc onboarding bảo đảm.
3. Khởi tạo ràng buộc với **yêu cầu và account cụ thể**, có challenge/thời hạn và cơ chế chống replay thích hợp.
4. Kiểm chứng authenticator mới thực sự hoạt động: TOTP code hợp lệ, WebAuthn attestation/assertion/registration theo giao thức, hoặc push challenge tương ứng.
5. Lưu **credential ID/metadata cần thiết**, thời điểm, phương thức, số lượng credential và trạng thái; **không log seed/secret**.
6. Thông báo enrollment qua kênh đáng tin theo chính sách; tạo dấu vết audit cho người thực hiện.
7. Kiểm tra có **phương thức dự phòng** hợp lệ không, tránh tình huống mất thiết bị một lần là không thể tiếp tục công việc.

Không nên cho phép người chưa được xác minh **tự thay đổi yếu tố MFA cũ** chỉ vì họ biết username, số điện thoại hoặc employee number.

### 5.2. Luồng xác thực bình thường

~~~mermaid
flowchart TD
    A["Người dùng bắt đầu login tại ứng dụng"] --> B["IdP xác định account, trạng thái, policy"]
    B --> C{"Account đủ điều kiện?"}
    C -->|Không| DENY["DENY và ghi audit"]
    C -->|Có| D["Kiểm tra yếu tố đầu / khởi tạo passkey theo chính sách"]
    D --> E{"Có cần possession factor / step-up?"}
    E -->|Có| F["Yêu cầu authenticator đã đăng ký"]
    F --> G{"Bằng chứng hợp lệ, binding đúng?"}
    G -->|Không| DENY
    G -->|Có| H["Ghi auth context, tạo session/token phù hợp"]
    E -->|Không theo policy| H
    H --> I["Ứng dụng kiểm chứng SSO và phân quyền tài nguyên"]
~~~

**Possession factor chứng minh một phần của Authentication**, không tự quyết định toàn bộ **Authorization**. Sau khi IdP chấp nhận MFA, ứng dụng vẫn phải kiểm tra **RBAC/ABAC, entitlement và trạng thái tài nguyên**. Tài khoản thiếu role không thể được “sửa” bằng cách thêm một khóa bảo mật.

### 5.3. Phát hiện thay đổi bất thường trong binding

Các sự kiện nên được giám sát phù hợp rủi ro: thêm nhiều authenticator liên tiếp, xóa phương thức cũ rồi thêm phương thức mới, recovery từ phiên lạ, thay đổi thông tin liên lạc gần thời điểm đăng ký, đăng nhập đặc quyền sau enrollment mới hoặc nhiều MFA challenge bị từ chối.

Đây là **tín hiệu điều tra**, không phải mọi sự kiện đều là tấn công. Nhưng với credential đặc quyền, có thể cần yêu cầu xác minh mạnh hơn, thông báo owner hoặc chặn tạm thời cho đến khi giải quyết.

## 6. Joiner–Mover–Leaver và possession factor

### 6.1. Joiner: cấp account chưa đủ, phải enroll MFA đúng lúc

Khi HRIS xác nhận nhân viên mới, IAM có thể tạo identity và provision account qua IdP, SCIM hoặc API ứng dụng. **SCIM chủ yếu quản lý User/Group và thuộc tính theo khả năng provider; nó không tự enroll khóa FIDO2, tạo TOTP seed hay xác minh possession factor**.

Ví dụ:

- HRIS tạo bản ghi nhân viên có ngày bắt đầu 01/12.
- IAM thiết lập tài khoản IdP ở trạng thái chờ hoặc có hạn chế theo chính sách.
- Người dùng thực hiện **MFA enrollment** qua quy trình có chứng minh danh tính phù hợp.
- IdP gắn passkey/khóa hoặc authenticator ứng dụng vào account đúng người.
- Khi đủ điều kiện có hiệu lực, IdP cho đăng nhập theo policy; ứng dụng kiểm tra SSO và entitlement riêng.

**Tình huống lỗi:** IdP account tồn tại nhưng nhân viên chưa đăng ký yếu tố MFA bắt buộc. Đây có thể là trạng thái **PENDING_ENROLLMENT**, không nhất thiết là sai mật khẩu. Không nên cấp ngoại lệ bỏ MFA vô thời hạn chỉ để người dùng mới vào được ứng dụng.

### 6.2. Mover: vai trò mới có thể yêu cầu yếu tố mạnh hơn

Một nhân viên chuyển từ vai trò đọc tài liệu nội bộ sang **quản trị cloud** có thể cần **phishing-resistant MFA**, user verification nghiêm ngặt hơn, thiết bị công ty được quản lý hoặc step-up cho thao tác đặc quyền.

Quy trình Mover cần phân biệt:

| Đối tượng | Có thể giữ nguyên | Cần đánh giá lại |
| --- | --- | --- |
| **Identity ID / account IdP** | Thường giữ nguyên khi người vẫn thuộc tổ chức. | Trạng thái công việc, thuộc tính HR, yêu cầu phân tách account đặc quyền. |
| **Authenticator đã đăng ký** | Có thể tiếp tục dùng nếu đáp ứng policy và owner hợp lệ. | Loại yếu tố, mức bảo đảm, điều kiện device-bound/UV, việc thiết bị có được phép trong role mới. |
| **Role / group / entitlement** | Các quyền chung còn hợp lệ. | Thu hồi quyền role cũ; cấp quyền role mới theo approval, least privilege và SoD. |
| **Session/token** | Một số phiên có thể tiếp tục trong giới hạn policy. | Yêu cầu re-auth, step-up, token revocation khi đổi đặc quyền hoặc độ nhạy. |

**Thay đổi vai trò không mặc nhiên phải xóa mọi MFA credential**; nhưng không nên giữ một authenticator không còn đáp ứng chính sách mới. Ví dụ, TOTP có thể được phép cho account thông thường nhưng không đủ cho thao tác quản trị production. Việc chuyển role có thể kích hoạt **đăng ký security key** và hạn chế đặc quyền cho tới khi đủ điều kiện.

### 6.3. Leaver: thu hồi đường đăng nhập và credential binding

Khi quan hệ làm việc kết thúc, IAM thường cần **chặn đăng nhập đúng thời điểm có hiệu lực** bằng cách disable account hoặc kiểm soát tương đương ở IdP và ứng dụng đích. Ngoài ra, cần đánh giá:

- Các authenticator đã liên kết với account IdP còn có thể tạo phiên mới không?
- Session, refresh token, personal access token, local account hoặc API key có tồn tại độc lập không?
- Các account đặc quyền thứ cấp được quản lý bởi ai và đã bị khóa chưa?
- Security key/passkey của công ty có cần thu hồi credential binding hay bàn giao phần cứng theo asset policy?
- Việc xóa/giữ hồ sơ authenticator có phù hợp chính sách lưu giữ và kiểm toán không?

**Disable IdP** là một lớp bảo vệ quan trọng nhưng **không tự đồng nghĩa các session/tokens ở mọi ứng dụng đã bị thu hồi**. Tương tự, chỉ thu lại điện thoại hoặc khóa bảo mật vật lý chưa đủ nếu server vẫn giữ credential binding và còn những phương thức khác.

Nếu passkey được đồng bộ, không nên suy ra chỉ xóa trên một thiết bị đã loại bỏ mọi bản sao hoặc vô hiệu hóa binding ở RP. Quản trị viên cần kiểm tra trạng thái **server-side credential**, account, session và các đường truy cập theo thực tế sản phẩm.

### 6.4. Nhà thầu, tái tuyển và nhiều quan hệ làm việc

Nhà thầu có thể có ngày hết hạn và sponsor riêng. MFA phải gắn với identity/quan hệ được phép và được xem lại khi nhà thầu hết hạn. Khi **rehire**, việc xác minh cùng người và quyết định có dùng lại account/authenticator phải tuân theo nguồn HR và chính sách — không tự khôi phục credential/quyền cũ chỉ vì trùng employee number hoặc email.

Người có **nhiều assignment** có thể tiếp tục giữ một authenticator hợp lệ trong khi một phần quyền bị thu hồi. Vòng đời possession factor và vòng đời entitlement liên quan nhau nhưng **không phải một đối tượng**.

## 7. IdP, SSO, SCIM và RBAC/ABAC liên quan possession factor ra sao?

### 7.1. IdP là điểm kiểm chứng tập trung nhưng không sở hữu mọi quyền

Trong SSO, IdP có thể kiểm chứng password, passkey, TOTP hoặc push, rồi phát kết quả xác thực cho ứng dụng qua **SAML/OIDC**. Ứng dụng tin cậy phải kiểm tra issuer, signature, audience, thời gian hiệu lực và các điều kiện giao thức, sau đó ánh xạ đúng account.

**SSO thành công không có nghĩa ứng dụng chắc chắn có account, entitlement hoặc phiên đã cập nhật.** SCIM hoặc API có thể hỗ trợ provisioning; RBAC/ABAC quyết định quyền tại ứng dụng. Authenticator binding ở IdP không tự tạo user/group trên mọi ứng dụng.

### 7.2. Authentication context và step-up

Một số IdP giao tiếp **phương thức hoặc mức bảo đảm xác thực** qua claim/context được hai bên thống nhất. Ứng dụng có thể yêu cầu người dùng **step-up** khi thao tác nhạy cảm, ví dụ duyệt thanh toán hoặc thay đổi role admin.

Ví dụ pseudocode:

~~~text
REQUEST: approve-payment
REQUIRE:
    identity.employmentStatus == ACTIVE
    identity.businessRole contains PAYMENT_APPROVER
    transaction.hasRequiredSoDChecks == true
    authentication.isRecentEnough == true
    authentication.method satisfies HIGH_ASSURANCE_POLICY
    authentication.userVerificationSatisfied == true
IF ALL conditions satisfied:
    ALLOW
ELSE:
    DENY or STEP_UP according to policy
~~~

Đây là **mô hình khái niệm**. Trong thực tế, **RBAC/ABAC** và freshness/phương thức AuthN phải do hệ thống có thẩm quyền đánh giá theo thông tin đáng tin, không chỉ dựa trên một trường client tự gửi. Với OIDC, ứng dụng có thể xem những claim như **amr/acr** khi IdP và RP thống nhất ngữ nghĩa; không được tự gán một giá trị claim thành bảo đảm an ninh nếu chưa có chính sách và kiểm chứng thực tế.

### 7.3. SSO không thay thế auth của phiên ứng dụng

Sau khi IdP xác thực thành công, ứng dụng có thể tạo session riêng và giữ quyền theo role/claim tại thời điểm đó. Khi authenticator bị thu hồi hoặc nhân viên rời công ty, **session đang tồn tại có thể vẫn còn hiệu lực** nếu ứng dụng không có cơ chế cập nhật/thu hồi. Để kiểm soát residual access, cần xác định:

1. Thời hạn phiên/token và cơ chế refresh.
2. Cách ứng dụng phản ứng với thay đổi account/membership/credential.
3. Có hỗ trợ revocation, back-channel logout hoặc kiểm tra trạng thái ở backend không.
4. Chính sách re-auth/step-up khi quyền và độ nhạy thay đổi.
5. Những đường local login hoặc API token độc lập với IdP.

Không gộp “MFA đã hoàn tất” với “account có quyền vĩnh viễn”. MFA là kiểm soát AuthN; **permission và vòng đời session** cần kiểm soát riêng.

## 8. Bảo vệ possession factor trước tấn công và sử dụng sai

| Mối đe dọa | Cách possession factor có thể bị ảnh hưởng | Kiểm soát gợi ý |
| --- | --- | --- |
| **Phishing real-time/Adversary-in-the-middle** | OTP bị lấy và chuyển tiếp ngay trong thời gian hiệu lực. | Ưu tiên WebAuthn/FIDO2 phishing-resistant khi phù hợp; đào tạo và giám sát. |
| **SIM swap/port-out** | Mã SMS đến số điện thoại do kẻ gian kiểm soát. | Hạn chế dùng SMS ở trường hợp nhạy cảm, đánh giá rủi ro thay số, tăng kiểm tra recovery. |
| **MFA fatigue** | Người dùng bị spam push rồi chấp thuận nhầm. | Number matching, challenge binding, rate limiting, báo cáo yêu cầu lạ. |
| **Thiết bị bị mất/đánh cắp** | Attacker có vật lý thiết bị/khóa. | Bảo vệ user verification, revocation binding, khóa dự phòng, rà soát session. |
| **Malware/thiết bị bị xâm nhập** | Secret hoặc phiên có thể bị lấy cắp, prompt bị thao túng. | Bảo vệ endpoint, secure storage, hardening, credential rotation theo rủi ro. |
| **Replay/đoán OTP** | Cố dùng lại mã hoặc thử nhiều mã. | Kiểm tra window/counter, hạn chế thử, chống replay khi được thiết kế. |
| **Authenticator enrollment hijack** | Kẻ gian tự thêm yếu tố MFA vào account nạn nhân. | Kiểm tra danh tính mạnh trước thay đổi binding, audit, cảnh báo enrollment mới. |
| **Recovery social engineering** | Help desk bị thuyết phục gỡ MFA hoặc đăng ký thiết bị lạ. | Quy trình recovery độc lập, xác minh danh tính và tách nhiệm vụ khi cần. |
| **Token/session theft** | MFA đã hoàn tất nhưng phiên đăng nhập bị chiếm. | Bảo vệ phiên/token, giám sát, revocation và tái xác thực cho hành động nhạy cảm. |
| **Dependency outage** | Push/MFA provider hoặc IdP không sẵn sàng. | Phương án dự phòng đã duyệt, kiểm soát fail-safe, break-glass có giám sát. |

**Phishing resistance là thuộc tính của giao thức và cách triển khai, không phải chỉ của hình thức thiết bị.** Một USB OTP token vẫn có thể bị phishing qua mã, trong khi security key FIDO2 có origin binding nếu triển khai và xác minh đúng. Một giải pháp push có mật mã bảo vệ có thể mạnh hơn thao tác “Approve” đơn giản, nhưng không tự chứng minh an toàn như WebAuthn.

### 8.1. Vì sao không nên dùng “biết OTP” làm proofing?

Người nhận OTP có thể là kẻ tấn công đã kiểm soát SIM, phiên email hoặc thiết bị. OTP chỉ cung cấp bằng chứng theo giả định của kênh đã đăng ký, không phải kết luận căn cước người thực. **Enrollment và recovery** là điểm yếu thường bị bỏ qua: nếu kẻ gian đăng ký được authenticator thì các lần AuthN sau có thể hoàn toàn “hợp lệ” về kỹ thuật.

### 8.2. Fail closed và khôi phục vận hành

Khi IdP hoặc MFA provider gián đoạn, việc **bỏ qua MFA đại trà** có thể làm mất kiểm soát truy cập. Thiết kế cần xác định hành vi khi dependency không sẵn sàng. Với quyền nhạy cảm, nên từ chối yêu cầu không thể xác minh theo chính sách; đồng thời chuẩn bị phương án **break-glass** có giới hạn, bảo vệ credential, người chịu trách nhiệm, log và review sau sự kiện.

Phương án khẩn cấp có thể dùng authenticator dự phòng đã đăng ký hoặc quy trình cấp quyền đặc biệt. Không nên tắt xác minh chữ ký, tự tin tưởng token hết hạn hay biến một cuộc gọi không được xác minh thành quyền đăng ký MFA mới.

## 9. Mất thiết bị, thay thiết bị và khôi phục yếu tố sở hữu

Một quy trình recovery an toàn phải phân biệt **người hợp lệ bị mất thiết bị** với **kẻ gian đang tìm cách chiếm quyền bind authenticator**.

### 9.1. Quy trình tham khảo khi người dùng báo mất điện thoại

~~~mermaid
flowchart TD
    A["Báo mất hoặc nghi bị chiếm authenticator"] --> B["Ghi yêu cầu và xác định account/identity"]
    B --> C["Xác minh yêu cầu qua kênh đã được phê duyệt"]
    C --> D{"Bằng chứng đủ theo mức rủi ro?"}
    D -->|Không| E["Từ chối thay đổi binding; chuyển review"]
    D -->|Có| F["Chặn/thu hồi authenticator bị ảnh hưởng"]
    F --> G["Đánh giá session, token, credential và dấu hiệu chiếm account"]
    G --> H["Đăng ký authenticator mới có challenge/kiểm chứng"]
    H --> I["Kiểm tra login/step-up theo policy"]
    I --> J["Ghi audit, thông báo, rà soát"]
~~~

**Bước ưu tiên** phụ thuộc nguy cơ. Nếu có dấu hiệu account bị xâm nhập, có thể phải chặn account và phiên **trước** khi người dùng hoàn tất recovery. Nếu chỉ đổi điện thoại theo lịch, tổ chức có thể yêu cầu đăng ký thiết bị mới trước rồi thu hồi thiết bị cũ trong một workflow có giới hạn và audit.

### 9.2. Không nhầm xóa ứng dụng với thu hồi credential

- **TOTP:** xóa ứng dụng khỏi điện thoại cũ có thể không vô hiệu hóa seed đã được sao lưu hoặc chép sang thiết bị khác. Nếu nghi lộ seed, cần **thay đổi secret/binding ở server**.
- **WebAuthn:** RP/IdP cần thu hồi đúng credential ID; xóa passkey cục bộ không bảo đảm server đã vô hiệu hóa mọi bản sao đồng bộ.
- **Push:** xóa thiết bị/registration hoặc khóa xác thực trong IdP theo khả năng nền tảng, rồi kiểm tra các đăng ký khác.
- **Smart card/certificate:** cần kết hợp xử lý credential binding, PKI/revocation phù hợp, vật lý thẻ và quyền người dùng.
- **SMS:** cần kiểm tra quyền kiểm soát số điện thoại và quy trình thay đổi số; chỉ việc nhập số mới chưa đủ proofing.

### 9.3. Phương thức dự phòng và nguy cơ trở thành đường yếu

Khóa bảo mật dự phòng hoặc recovery code có thể giúp người dùng tránh mất quyền khi hỏng thiết bị. Nhưng cơ chế dự phòng phải được **bảo vệ và quản lý cùng mức rủi ro**. Nếu người dùng luôn có thể bỏ qua FIDO2 bằng SMS dễ chiếm đoạt cho account quản trị, đường dự phòng có thể hạ mức bảo đảm của cả hệ thống.

Recovery code nếu được hỗ trợ cần quản lý như credential nhạy cảm; lưu trữ an toàn, giới hạn sử dụng, thu hồi/cấp lại theo quy trình và không ghi vào ticket hoặc log.

## 10. Kiểm toán authenticator binding và authentication event

Một bằng chứng tốt phải trả lời được: **ai đăng ký/thay thế/thu hồi yếu tố, vào account nào, phương thức gì, tại thời điểm nào, có căn cứ gì và trạng thái thực tế ra sao?**

| Nhóm thông tin | Trường/sự kiện nên liên kết | Mục đích |
| --- | --- | --- |
| **Identity và account** | IAM identity ID, IdP account ID, tenant | Xác định chính xác chủ thể và miền quản lý. |
| **Authenticator** | Credential ID/định danh được bảo vệ, loại, trạng thái, provider | Phân biệt nhiều khóa/thiết bị trên cùng account. |
| **Nguồn và thẩm quyền** | HR JML event, enrollment/recovery request, policy/version, approval | Giải thích vì sao phép thay đổi binding được cho phép. |
| **Thực thi** | Actor, phương thức quản trị/API, thời điểm, kết quả | Biết ai hoặc service nào đã đổi trạng thái. |
| **Xác thực** | Request/correlation ID, phương thức, user verification, outcome, thời gian | Nối chuỗi đăng nhập và hành động nhạy cảm. |
| **Kiểm chứng** | Trạng thái binding sau thay đổi, login/step-up test, session/token review | Chứng minh thao tác có hiệu lực theo mục tiêu. |
| **Khắc phục** | Ticket/incident, owner, deadline, thời điểm verified | Tránh credential bị báo mất nhưng không ai thực sự thu hồi. |

Dưới đây là **JSON minh họa nội bộ** cho một sự kiện thu hồi authenticator; không phải schema chuẩn của OIDC, WebAuthn hay SCIM:

~~~json
{
  "eventId": "iam-mfa-event-8802",
  "correlationId": "recovery-flow-2814",
  "eventType": "POSSESSION_AUTHENTICATOR_REVOKED",
  "identityId": "person-2048",
  "idpAccountId": "idp-user-581",
  "authenticator": {
    "credentialRef": "cred-fido2-19",
    "type": "WEBAUTHN_SECURITY_KEY",
    "statusBefore": "ACTIVE",
    "statusAfter": "REVOKED"
  },
  "reason": {
    "category": "LOST_DEVICE",
    "requestRef": "IAM-REQ-2410",
    "verificationMethodRef": "approved-recovery-flow"
  },
  "execution": {
    "actorId": "iam-recovery-operator",
    "executedAt": "2026-11-23T09:12:00+07:00",
    "result": "SUCCEEDED"
  },
  "verification": {
    "checkedAt": "2026-11-23T09:12:40+07:00",
    "bindingIsActive": false,
    "sessionReview": "COMPLETED",
    "status": "VERIFIED"
  }
}
~~~

**Không ghi** TOTP seed, OTP, mã khôi phục, khóa riêng, mật khẩu, full token, dữ liệu sinh trắc hoặc private attestation material không cần thiết vào audit log. Nếu cần định danh credential, sử dụng tham chiếu được bảo vệ hoặc fingerprint phù hợp. Thời gian, quyền truy cập log và retention phải tuân theo chính sách bảo mật và riêng tư.

### 10.1. Xác minh không chỉ dựa vào HTTP success

Một API revoke trả thành công không chứng minh mọi phiên đã hết hiệu lực hoặc người dùng không còn authenticator khác. Với Leaver, tiêu chí cần đạt có thể là **account disabled và các đường truy cập bắt buộc đã chặn**; việc mỗi credential bị xóa riêng có thể phục vụ hygiene/retention nhưng không thay thế đối soát access. Với lost device, tiêu chí cần đạt là **credential bị ảnh hưởng không còn được chấp nhận**, đồng thời các phiên/tokens rủi ro được xử lý theo chính sách.

## 11. Possession factor ở tài khoản dịch vụ và workload

Các hệ thống phi con người có thể chứng minh **quyền sở hữu khóa riêng** bằng mTLS, chữ ký JWT hoặc workload federation. Tuy nhiên, **chứng minh quyền kiểm soát khóa của một workload không có nghĩa workload đang sử dụng MFA như một con người**. MFA thường dựa trên các loại yếu tố độc lập trong một nghi thức xác thực chủ thể; nhiều credential của cùng workload không tự đồng nghĩa thỏa điều kiện MFA.

Một **service account** cần:

- **Workload identity ID**, owner và mục đích rõ ràng.
- Credential hoặc trust binding được cấp theo môi trường/workload phù hợp.
- Quyền RBAC/ABAC tối thiểu để gọi API hoặc tài nguyên.
- Rotation, thời hạn, revocation và quy trình deprovisioning khi job ngừng.
- Audit chứng minh workload nào đã dùng credential và actor nào quản trị bí mật đó.

Khi nhân viên sở hữu service account rời tổ chức, cần chuyển owner, thu hồi quyền cá nhân và đánh giá credential đã biết hoặc truy cập được. **Không tự xóa credential của workload đang vận hành** chỉ vì owner đổi vai trò; nhưng không để secret do người không còn trách nhiệm tiếp tục nắm giữ.

## 12. Tình huống thực tế: đổi vai trò, mất thiết bị và nghỉ việc

**Bối cảnh:** Bình là nhân viên nhóm vận hành. Công ty dùng IdP có SSO, dùng khóa FIDO2 cho quyền đặc quyền và TOTP cho một số ứng dụng ít nhạy cảm. Account IdP liên kết với IAM identity **person-2048**; quyền ứng dụng được quản lý qua SCIM và API tùy target.

| Thời điểm | Sự kiện | Hành động IAM/MFA cần đánh giá |
| --- | --- | --- |
| **Joiner** | Bình vào tổ chức và nhận account. | Xác minh danh tính, đăng ký khóa/security key đúng người, thiết lập TOTP theo policy; ghi binding có owner. |
| **Mover** | Bình chuyển sang vai trò phân tích dữ liệu, không còn deploy production. | Gỡ quyền/nhóm deploy qua provisioning, đánh giá session; khóa MFA có thể giữ nếu còn phù hợp, không cấp lại quyền chỉ vì có khóa. |
| **Lost device** | Bình báo mất một khóa FIDO2. | Xác minh recovery, thu hồi đúng credential ID, kiểm tra phiên và đăng ký khóa mới theo policy. |
| **Leaver** | HRIS xác nhận Bình nghỉ việc. | Disable account đúng thời hạn, xử lý các authenticator/session/token và quyền ứng dụng còn hoạt động, xác minh các đường truy cập bị chặn. |

### 12.1. Sai lầm ở giai đoạn Mover

Sau khi đổi role, Bình vẫn còn được gán trực tiếp role deploy tại một ứng dụng Git, dù IdP group vận hành đã bị gỡ. Việc Bình có khóa FIDO2 **không phải nguyên nhân quyền deploy tồn tại**: nguyên nhân là **entitlement ở ứng dụng chưa được thu hồi**. IAM cần đối soát desired access/actual access và xử lý direct grant, thay vì xóa toàn bộ MFA credential để “sửa quyền”.

### 12.2. Sai lầm khi mất khóa

Help desk có thể nghĩ “chỉ cần cấp lại khóa mới”, nhưng khóa cũ vẫn là credential được IdP tin cậy nếu chưa thu hồi binding. Quy trình đúng cần kiểm chứng người yêu cầu, **revoke khóa bị mất**, xem các session rủi ro, sau đó enroll khóa thay thế. Với account đặc quyền, có thể cần kiểm soát tăng cường và ghi nhận reviewer.

### 12.3. Sai lầm khi Leaver

IdP disable khiến đăng nhập mới qua SSO thất bại — đây là hành vi mong đợi. Tuy nhiên, một ứng dụng còn nhận **personal access token** được tạo trước đó. Đây là residual access ở ứng dụng đích và cần giải quyết riêng, không thể kết luận “đã xóa MFA nên offboarding hoàn tất”.

### 12.4. Chuỗi bằng chứng mẫu

~~~text
HRIS JML event
    -> IAM identity + effective relationship
    -> IdP account + authenticator binding inventory
    -> AuthN policy / SSO result
    -> Application account and entitlement via SCIM/API
    -> Session, token and local login review
    -> Readback / reconciliation
    -> Verified closure or assigned remediation owner
~~~

Mỗi mũi tên cần có tham chiếu thực tế (identity ID, account/credential ID, request ID, thời điểm), không chỉ là ghi chú “MFA completed” hay “user disabled”.

## 13. Đo lường chất lượng possession-factor lifecycle

| Chỉ số | Định nghĩa tham khảo | Sai lầm khi đọc số liệu |
| --- | --- | --- |
| **Enrollment coverage** | Account trong phạm vi phải có possession factor hợp lệ và đã đăng ký ÷ tổng account thuộc phạm vi. | Đếm account đã có TOTP nhưng chính sách mới yêu cầu phishing-resistant. |
| **Phishing-resistant coverage** | Account/luồng nhạy cảm có authenticator và cách xác thực đáp ứng policy phishing-resistant ÷ tổng đối tượng thuộc phạm vi. | Coi mọi push hoặc OTP đều phishing-resistant. |
| **Recovery verification coverage** | Yêu cầu reset/rebind có bằng chứng xác minh phù hợp ÷ tổng yêu cầu recovery được thực hiện. | Chỉ đếm ticket đóng, không kiểm tra chất lượng identity proofing. |
| **Lost-authenticator revocation latency** | Thời gian từ mốc phải thu hồi sau khi báo mất đến khi credential bị ảnh hưởng không còn được chấp nhận. | Coi việc xóa app/thu lại phần cứng là thu hồi server-side. |
| **Leaver authenticator/access closure** | Sự kiện Leaver có chứng cứ account và các đường truy cập bắt buộc đã bị chặn ÷ tổng sự kiện đến hạn. | Coi disable IdP là đã thu hồi mọi token trong các SaaS. |
| **Unexpected MFA failure rate** | Số lần MFA không hoàn tất do nguyên nhân ngoài dự kiến trong phạm vi luồng hợp lệ. | Gộp cả yêu cầu đáng nghi bị người dùng từ chối. |
| **Authenticator inventory accuracy** | Số binding có owner, trạng thái, thời gian và policy xác định được ÷ tổng binding cần quản lý. | Không phân biệt nhiều credential trên một thiết bị hoặc synced passkey. |
| **Privileged step-up compliance** | Hành động nhạy cảm có evidence xác thực theo mức yêu cầu ÷ tổng hành động thuộc phạm vi. | Chỉ dựa vào login success, không kiểm tra freshness hoặc phương thức. |

Không có ngưỡng toàn cầu phù hợp mọi tổ chức. Nên phân tầng theo **quyền truy cập thực tế**, chẳng hạn các nhóm cloud admin, database admin, tài chính và dữ liệu nhạy cảm, thay vì chỉ theo tổng số account.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Coi OTP và WebAuthn có khả năng chống phishing giống nhau. | Đánh giá sai rủi ro với account nhạy cảm. | Phân biệt shared-secret OTP với chứng minh khóa theo origin/RP. |
| Cho người dùng nhập employee number để tự thêm MFA. | Kẻ gian có thể bind authenticator vào account người khác. | Bảo đảm proofing/enrollment và xác minh account có thẩm quyền. |
| Ghi TOTP seed hoặc QR provisioning vào ticket. | Secret bị sao chép; possession factor mất tính độc lập. | Bảo vệ seed, giới hạn người truy cập, không lưu trong log/ticket. |
| Chỉ xóa ứng dụng MFA trên máy cũ. | Credential binding server-side hoặc bản sao vẫn hợp lệ. | Revoke đúng credential, đánh giá synced copy và session. |
| Bỏ qua user verification khi policy yêu cầu MFA mạnh. | Chấp nhận một authenticator chưa chứng minh đủ yếu tố. | Kiểm tra UV/assurance theo cơ chế và policy thực tế. |
| Nghĩ mọi passkey đều device-bound. | Bỏ sót cơ chế sync/recovery và mở rộng nơi giữ khóa. | Phân biệt device-bound/synced, quản lý theo mức rủi ro. |
| Không có authenticator dự phòng hoặc recovery an toàn. | Người dùng bị khóa ngoài hệ thống hoặc help desk buộc bypass. | Quy trình recovery mạnh, credential dự phòng có kiểm soát. |
| Tắt MFA hàng loạt khi provider outage. | Hạ thấp bảo vệ toàn bộ hệ thống. | Fail-safe và break-glass có giới hạn/audit theo chính sách. |
| Coi IdP MFA success là đủ quyền ứng dụng. | Bỏ qua AuthZ, SCIM và residual entitlement. | Phân tách AuthN, provisioning, RBAC/ABAC và reconciliation. |
| Leaver đã disable IdP nhưng để local token/session. | Người rời tổ chức vẫn có đường truy cập. | Kiểm tra deprovisioning và token/session tại target. |
| Chủ service account nghỉ việc thì xóa bí mật workload bừa bãi. | Gián đoạn dịch vụ hoặc mất dấu owner. | Bàn giao, rotation theo rủi ro, quản lý lifecycle workload riêng. |
| Không ghi audit enrollment/revocation. | Không giải thích được ai đã đăng ký credential và quyền truy cập còn hay mất. | Lưu event, quyết định, owner, thời điểm và verified outcome. |

## 15. Checklist và bài tập thực hành

### 15.1. Checklist thiết kế possession factor trong IAM

- [ ] Phân biệt **knowledge, possession, inherence**, không dùng hai bí mật knowledge rồi gọi là MFA.
- [ ] Xác định authenticator được phép theo mức rủi ro (TOTP, push, FIDO2/passkey, smart card...), không đồng nhất độ chống phishing.
- [ ] Enrollment gắn với identity/account đã xác minh và có thời điểm hiệu lực; không dùng employee number làm secret.
- [ ] Ghi inventory **credential binding** có account, loại phương thức, trạng thái và owner phù hợp.
- [ ] Với WebAuthn/passkey, kiểm tra RP ID/origin, challenge, chữ ký, UP/UV và yêu cầu policy khi áp dụng.
- [ ] Nếu có synced passkey, đánh giá vòng đời đồng bộ/khôi phục và revocation phía RP.
- [ ] Với push, có cơ chế chống spam/chấp thuận nhầm, giám sát và báo cáo yêu cầu đáng nghi.
- [ ] Có phương thức dự phòng và recovery được proofing đúng mức, không bypass MFA tùy tiện.
- [ ] Joiner chỉ kích hoạt quyền sau khi identity/account/authenticator đạt điều kiện chính sách.
- [ ] Mover đánh giá yêu cầu assurance mới và thu hồi entitlement cũ, không nhầm credential với role.
- [ ] Leaver chặn các đường truy cập bắt buộc, xử lý authenticator/session/token và readback kết quả.
- [ ] IdP/SSO, SCIM/provisioning và RBAC/ABAC có trách nhiệm rõ ràng; không coi MFA success là authorization.
- [ ] Tài khoản dịch vụ có credential/owner và vòng đời riêng, không coi hai khóa workload là MFA của con người.
- [ ] Audit event không chứa secret; các lỗi enrollment/recovery/revocation có remediation owner và verification.

### 15.2. Tình huống A — TOTP bị phishing

Người dùng nhập đúng mật khẩu và mã TOTP vào một trang đăng nhập giả; kẻ tấn công chuyển tiếp mã gần như ngay lập tức để đăng nhập vào trang thật. Hãy giải thích vì sao **có hai yếu tố vẫn có thể bị phishing**, và một luồng WebAuthn/FIDO2 được triển khai đúng có thể giảm rủi ro bằng cách nào.

### 15.3. Tình huống B — Nhân viên đổi role sang cloud admin

Nhân viên đang dùng TOTP; role mới yêu cầu xác thực chống phishing và user verification. Hãy thiết kế bước **MFA re-enrollment/step-up** và kiểm tra policy trước khi cấp quyền admin, đồng thời thu hồi các role vận hành cũ không còn phù hợp.

### 15.4. Tình huống C — Mất điện thoại có passkey đồng bộ

Người dùng xóa app trên máy cũ và đăng ký thiết bị mới. Người quản trị tuyên bố credential cũ đã bị thu hồi. Hãy chỉ ra cần kiểm tra gì tại **IdP/RP binding**, nền tảng đồng bộ và session/token trước khi có thể xác nhận điều đó.

### 15.5. Tình huống D — Leaver còn API token

HRIS xác nhận nhân viên nghỉ việc. IdP đã disable account và FIDO2 key không còn đăng nhập được; nhưng một API token cũ vẫn gọi được dịch vụ. Hãy phân biệt trạng thái **AuthN tại IdP** với **effective access ở ứng dụng** và cách chứng minh offboarding hoàn tất.

### 15.6. Tình huống E — Recovery social engineering

Người gọi đến help desk biết tên, email và employee number, yêu cầu xóa MFA cũ để thêm điện thoại mới. Hãy giải thích vì sao các dữ liệu đó chưa đủ proofing; đề xuất chuỗi bước xác minh, phê duyệt nếu cần, thu hồi binding và ghi audit.

**Điểm cần ghi nhớ:** **Possession factor** chỉ có giá trị khi authenticator/khóa **được đăng ký đúng identity, bằng chứng sở hữu được verifier kiểm tra đúng giao thức và credential được quản lý suốt vòng đời**. TOTP, push, SMS và FIDO2/passkey có mức bảo vệ khác nhau; đặc biệt cần phân biệt khả năng **chống phishing**, **user verification** và **đồng bộ passkey**. Trong IAM Joiner–Mover–Leaver, phải nối enrollment/thu hồi MFA với IdP/SSO, account provisioning, RBAC/ABAC và kết quả kiểm chứng tại ứng dụng, nhằm **duy trì quyền truy cập hợp lệ và chặn các đường truy cập không còn căn cứ**.

