# Đăng ký phương thức MFA trong Identity enrollment

**Đăng ký phương thức MFA (Multi-Factor Authentication enrollment)** là quá trình gắn một hoặc nhiều **authenticator** (phương tiện xác thực) với một danh tính đã được thiết lập, sao cho Identity Provider (IdP) có thể yêu cầu người dùng chứng minh quyền kiểm soát chúng khi đăng nhập hoặc thực hiện thao tác nhạy cảm. Quy trình này quan trọng không kém bước kiểm tra MFA lúc đăng nhập: kẻ tấn công không cần phá mật khẩu hay khóa bảo mật nếu có thể **đăng ký phương thức MFA của chính mình** vào tài khoản nạn nhân.

Bài thuộc chương **Identity enrollment** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nơi quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo tài khoản, cấp quyền, rà soát và thu hồi khi thay đổi vai trò hoặc chấm dứt quan hệ với tổ chức. Việc đăng ký MFA liên kết trực tiếp với **identity proofing**, IdP/SSO, provisioning qua SCIM, quyền RBAC/ABAC, danh tính dịch vụ, bằng chứng kiểm toán và mục tiêu giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Hạnh được tuyển vào phòng Tài chính. Sau khi HR xác nhận hồ sơ và IAM tạo tài khoản, Hạnh đăng ký một passkey công ty hoặc khóa bảo mật theo chính sách. Nếu kẻ lạ chỉ biết email và mật khẩu của Hạnh, họ không được phép dùng thông tin đó để tự gắn số điện thoại hay ứng dụng OTP mới vào tài khoản. Enrollment phải có bước xác thực/kiểm tra đủ mạnh, liên kết với phiên đúng người và ghi nhận bằng chứng.

## 1. Đăng ký MFA khác gì với xác thực MFA?

| Hoạt động | Câu hỏi | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| **Identity proofing** | Đây có đúng là người gắn với hồ sơ được khai báo? | Bằng chứng danh tính, hồ sơ HR hoặc nguồn có thẩm quyền. | Danh tính được thiết lập với mức độ tin cậy và dấu vết kiểm tra. |
| **Account provisioning** | Tài khoản nào cần tạo/kích hoạt, theo ngày và vai trò nào? | Sự kiện JML, phê duyệt, metadata IAM. | Danh tính trong IdP và các ứng dụng đích. |
| **MFA enrollment** | Authenticator nào được phép liên kết với danh tính này, theo cơ chế nào? | Phiên enrollment đáng tin, chính sách, bằng chứng sở hữu authenticator. | Bản ghi authenticator được ràng buộc với tài khoản và trạng thái quản lý. |
| **MFA authentication** | Tại thời điểm truy cập, chủ thể có chứng minh được quyền kiểm soát authenticator đã đăng ký không? | Challenge hoặc thông tin xác thực của phiên hiện tại. | Xác thực thành công/thất bại theo phương thức và điều kiện bảo đảm. |
| **Authorization** | Chủ thể này được làm gì trên tài nguyên cụ thể? | Vai trò, thuộc tính, hành động, tài nguyên, ngữ cảnh. | Quyết định allow/deny, kể cả sau MFA thành công. |

Đăng ký MFA **không đồng nghĩa đã hoàn tất lần xác thực tương lai**. Người dùng có thể đăng ký phương thức hôm nay, nhưng phiên đăng nhập ngày mai vẫn cần được kiểm tra theo policy hiện hành. Ngược lại, một phiên SSO còn hợp lệ cũng không tự cho phép đăng ký phương thức mới nếu yêu cầu bảo đảm của thao tác thay đổi authenticator cao hơn mức phiên hiện tại.

**Nguyên tắc gốc:** mức bảo vệ của quy trình **enrollment, reset và recovery** không được yếu tới mức phá vỡ bảo đảm của phương thức MFA mạnh đã triển khai.

## 2. Hiểu đúng các yếu tố và loại authenticator

Ba nhóm yếu tố xác thực cơ bản:

- **Something you know – điều biết:** mật khẩu, PIN hoặc bí mật ghi nhớ.
- **Something you have – điều sở hữu/kiểm soát:** khóa bảo mật vật lý, thiết bị có khóa mật mã riêng, ứng dụng OTP được ràng buộc đúng cách.
- **Something you are – đặc điểm sinh trắc:** vân tay hoặc khuôn mặt, sử dụng theo thiết kế của hệ thống.

**MFA** đòi hỏi ít nhất hai **yếu tố thuộc các nhóm độc lập** theo chính sách và định nghĩa của cơ chế xác thực; yêu cầu người dùng nhập hai mật khẩu khác nhau không tạo thành hai yếu tố. Một authenticator có thể kết hợp nhiều yếu tố (ví dụ thiết bị giữ khóa riêng được mở bằng xác minh người dùng cục bộ). Cần kiểm tra khả năng thực tế và cấu hình, không suy đoán chỉ qua tên “passkey” hoặc “MFA”.

| Phương thức | Cách vận hành khái quát | Khả năng chống phishing | Điểm cần cân nhắc khi enrollment |
| --- | --- | --- | --- |
| **FIDO2/WebAuthn passkey/khóa bảo mật** | Khóa riêng ký challenge; server lưu khóa công khai; có thể yêu cầu user verification (PIN/sinh trắc tại authenticator). | **Tốt khi triển khai đúng** nhờ ràng buộc với RP/origin và giao thức mật mã. | Kiểm tra origin, RP ID, challenge, user verification, loại thiết bị và khả năng sao lưu/đồng bộ theo chính sách. |
| **TOTP authenticator app** | Ứng dụng và server chia sẻ secret, sinh OTP theo thời gian. | Không chống phishing theo đặc tính OTP: mã có thể bị đánh cắp và dùng lại kịp thời. | Giữ bí mật seed, kiểm tra mã thử và hạn chế sử dụng lại một mã. |
| **HOTP** | Sinh OTP dựa trên bộ đếm và secret chia sẻ. | Không chống phishing. | Quản lý đồng bộ counter và giới hạn cửa sổ chấp nhận; ít dùng hơn TOTP trong nhiều ứng dụng. |
| **Push approval** | Ứng dụng đã đăng ký nhận yêu cầu phê duyệt; có thể hiển thị số đối chiếu. | Phụ thuộc thiết kế; push đơn giản dễ bị fatigue/giả mạo ngữ cảnh. | Ràng buộc thiết bị/ứng dụng, number matching, thông tin phiên và giới hạn gửi push. |
| **SMS/voice OTP** | Mã gửi tới số điện thoại qua mạng viễn thông. | Yếu trước phishing; thêm rủi ro SIM swap và chuyển số. | Chỉ dùng khi policy cho phép; cần xác minh số, phương án nâng cấp và kiểm soát thay số. |
| **Recovery codes** | Mã sử dụng một lần để khôi phục theo chính sách. | Không tự có khả năng chống phishing. | Phát hành an toàn, lưu bản hash hoặc cơ chế bảo vệ phù hợp, dùng một lần và vô hiệu hóa mã cũ khi thay thế. |

**Email OTP** không nên mặc nhiên được xem là yếu tố thứ hai độc lập với mật khẩu, nhất là khi cùng tài khoản email có thể được truy cập bằng cùng credential/phiên. Việc một IdP gắn nhãn “MFA” không thay thế đánh giá bảo đảm thực tế.

**Sinh trắc học trên điện thoại** thường là cách **mở khóa cục bộ** để cho phép thiết bị sử dụng khóa, không phải ảnh khuôn mặt hay dữ liệu vân tay được gửi nguyên vẹn tới IdP. Cần phân biệt sinh trắc là yếu tố hỗ trợ user verification và cách server xác minh bằng chứng mật mã.

## 3. Điều kiện tiên quyết trước khi cho enrollment

Trước khi mở tính năng “Add authentication method”, hệ thống nên xác minh:

1. **Danh tính có nguồn tin cậy:** hồ sơ người dùng liên kết với đúng ID ổn định; các trường hợp cần identity proofing phải có kết quả hợp lệ cho ngữ cảnh đăng ký.
2. **Tài khoản đủ điều kiện:** trạng thái nhân sự/hợp đồng và tài khoản IdP cho phép onboarding; không còn pending review, suspended hoặc terminated.
3. **Nguồn truy cập đáng tin:** người dùng đang ở phiên khởi tạo bằng cơ chế bootstrap đã được phê duyệt, hoặc phiên đã được step-up bằng authenticator hiện hành.
4. **Chính sách phương thức:** tài khoản thông thường, quản trị viên, nhân viên xử lý dữ liệu nhạy cảm hoặc nhà thầu có thể được phép dùng các phương thức khác nhau.
5. **Thiết bị và điều kiện vận hành:** nếu policy yêu cầu thiết bị quản lý hoặc khóa bảo mật do công ty cấp, phải kiểm tra nguồn chứng thực/ownership phù hợp; không tin một chuỗi device ID tự khai.
6. **Khả năng hoàn tất:** trình duyệt/ứng dụng hỗ trợ giao thức, thiết bị còn khả dụng, đồng hồ đủ chính xác nếu dùng TOTP và có kênh hỗ trợ cho trường hợp thất bại.
7. **Truy vết:** mọi yêu cầu enrollment có transaction ID, actor, account đích, method type, policy version và thời điểm.

### Bootstrap authentication: bài toán “đăng ký yếu tố đầu tiên”

Người dùng mới chưa có authenticator MFA để chứng minh chính authenticator hiện hành. Đây là một bài toán **bootstrap trust** cần thiết kế trước:

- Có thể dùng một lần đăng nhập khởi tạo với credential giao qua kênh an toàn **kèm** bước xác minh người nhận theo quy trình onboarding.
- Có thể thực hiện đăng ký dưới sự hỗ trợ của bộ phận được phân quyền, với kiểm tra danh tính/nguồn nhân sự và nhật ký phê duyệt.
- Có thể dùng phương thức xác thực hoặc khóa phần cứng được cấp trước qua quy trình giao nhận tin cậy.
- Có thể cung cấp **temporary access credential** giới hạn thời hạn, hành động, số lần sử dụng và ràng buộc enrollment; không coi nó là quyền đăng nhập đầy đủ vào tài nguyên nhạy cảm.

Không dùng mặc định “chỉ cần biết username và ngày sinh” để đăng ký MFA đầu tiên. Dữ liệu cá nhân có thể bị lộ; một kẻ mạo danh sẽ vượt qua chính hàng rào mà tổ chức muốn xây dựng.

## 4. Luồng đăng ký MFA an toàn

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant UI as Ứng dụng enrollment
    participant IDP as IdP / Authenticator service
    participant REG as Registry / Audit
    U->>UI: Yêu cầu thêm phương thức
    UI->>IDP: Kiểm tra phiên, chính sách và trạng thái account
    IDP-->>UI: Yêu cầu step-up hoặc bootstrap nếu cần
    U->>UI: Hoàn thành bước bảo đảm danh tính/phiên
    UI->>IDP: Bắt đầu enrollment transaction
    IDP-->>UI: Challenge/registration data một lần
    U->>UI: Tương tác với authenticator
    UI->>IDP: Gửi kết quả chứng minh sở hữu
    IDP->>IDP: Kiểm tra binding, challenge, hạn dùng, anti-replay
    alt Hợp lệ
        IDP->>REG: Lưu authenticator và sự kiện đã đăng ký
        IDP-->>UI: Enrollment thành công
        UI-->>U: Thông báo và hướng dẫn backup/recovery
    else Không hợp lệ
        IDP->>REG: Ghi lý do từ chối, giới hạn retry
        IDP-->>UI: Enrollment thất bại
    end
~~~

Ở mức triển khai:

1. **Người dùng chọn phương thức** từ danh sách được policy cho phép.
2. Server kiểm tra trạng thái account, **mức xác thực của phiên** và yêu cầu step-up đối với thay đổi nhạy cảm. Session dùng để enroll phải gắn với đúng account, không cho client chỉ định account khác qua trường ID.
3. Server tạo **enrollment transaction riêng** có challenge ngẫu nhiên đủ mạnh, thời hạn ngắn, trạng thái pending và giới hạn số lần thử; mỗi transaction gắn với một subject và method cụ thể.
4. Client tương tác với authenticator để tạo khóa/secret hoặc nhận proof theo giao thức; dữ liệu nhận về phải được server xác minh **trước** khi ghi là active.
5. Server ràng buộc credential với subject, lưu metadata cần thiết và đánh dấu \`ACTIVE\` chỉ sau khi xác nhận bằng chứng sở hữu hợp lệ.
6. Server ghi audit và gửi **thông báo thay đổi bảo mật** đến kênh đã tin cậy trước đó (khi có), giúp người dùng phát hiện đăng ký trái phép.
7. Nếu có phương thức dự phòng/recovery, người dùng được hướng dẫn đăng ký và bảo vệ; quyền dùng phương thức dự phòng phải đáp ứng chính sách tương ứng.

Mọi transaction bị hủy, quá hạn, lặp hoặc trỏ sang account khác phải bị từ chối. Không được biến nút **“Save”** trên giao diện thành bằng chứng đăng ký hoàn tất nếu server chưa xác minh credential.

## 5. Đăng ký TOTP: secret, QR và mã xác nhận

TOTP thường dùng một **secret chia sẻ** giữa authenticator app và server. Hai bên tính mã dựa trên secret và thời gian. Luồng enrollment điển hình:

1. Sau khi kiểm tra phiên, server tạo secret ngẫu nhiên riêng cho **một authenticator của một tài khoản**.
2. Server chỉ đưa secret tới giao diện enrollment qua kênh HTTPS được bảo vệ, thường mã hóa dưới dạng URI cấu hình để tạo QR code.
3. Người dùng mở authenticator app, quét QR hoặc nhập secret thủ công.
4. Ứng dụng sinh mã TOTP hiện tại; người dùng gửi mã thử tới server.
5. Server kiểm tra mã, bước thời gian trong cửa sổ hợp lý, giới hạn retry và tình trạng transaction.
6. **Chỉ sau mã thử hợp lệ** mới chuyển phương thức từ pending sang active; hết hạn hoặc hủy enrollment phải vô hiệu hóa secret chưa được kích hoạt.

URI giả định có hình thức:

~~~text
otpauth://totp/ExampleIAM%3Auser-4821?secret=EXAMPLEONLY&issuer=ExampleIAM&algorithm=SHA1&digits=6&period=30
~~~

Ví dụ là **định dạng minh họa**, không phải secret an toàn hoặc QR code có thể sử dụng. Thuộc tính thuật toán, số chữ số và chu kỳ phải tuân thủ năng lực và policy của server/app. **TOTP seed là một bí mật có thể dùng để tạo mã đăng nhập**, nên cần bảo vệ nghiêm ngặt.

### Những điểm dễ làm sai với TOTP

- **Không ghi QR/secret vào log, analytics, URL lịch sử, ticket hỗ trợ hoặc ảnh chụp màn hình tự động.** Giao diện chỉ hiển thị khi giao dịch hợp lệ.
- Server cần **lưu seed có thể dùng để tính/kiểm chứng OTP** bằng cơ chế mã hóa và bảo vệ khóa phù hợp, không thể chỉ hash seed như password rồi mong tính lại TOTP được.
- Mỗi lần tái đăng ký nên phát hành seed mới; seed cũ phải được thu hồi theo quyết định thay thế.
- OTP có thể bị **phishing thời gian thực** và bị nhập vào trang giả. Nên ưu tiên phương thức chống phishing cho tài khoản nguy cơ cao.
- Hạn chế số lần thử, phát hiện sai lệch đồng hồ trong cửa sổ nhỏ được định nghĩa; chống **replay** trong phạm vi cấu hình nếu phương thức/kiến trúc yêu cầu.
- Không coi “người dùng đã nhìn thấy QR” là chứng cứ sở hữu; cần **mã thử hoặc bước xác minh tương đương** trước khi active.

## 6. Đăng ký FIDO2/WebAuthn và passkey

WebAuthn cho phép một **Relying Party (RP)** đăng ký khóa công khai gắn với authenticator, rồi xác thực bằng chữ ký của khóa riêng trên challenge. Server không cần lưu khóa riêng của người dùng. Khóa riêng thường được bảo vệ trên khóa cứng hoặc nền tảng thiết bị; một số passkey có khả năng đồng bộ trong hệ sinh thái người dùng theo cơ chế của nhà cung cấp.

Một luồng đăng ký điển hình gồm:

1. RP/IdP xác định account đang enroll và tạo **registration options** gồm challenge ngẫu nhiên, RP ID, user ID dạng ổn định, tham số thuật toán và yêu cầu user verification/attestation phù hợp.
2. Trình duyệt gọi WebAuthn \`navigator.credentials.create()\` trong ngữ cảnh origin được phép.
3. Authenticator tạo cặp khóa và trả **attestation object**, client data và public key/credential ID theo giao thức; user presence và/hoặc user verification diễn ra theo cấu hình.
4. Server xác minh **challenge**, **origin**, **RP ID hash**, cấu trúc attestation/authenticator data, credential ID và các cờ cần thiết.
5. Nếu policy yêu cầu, server đánh giá attestation hoặc nguồn authenticator; không giả định mọi loại passkey đều cung cấp attestation doanh nghiệp.
6. Server lưu **public key, credential ID, phương thức, trạng thái, metadata cần thiết** và liên kết với account đúng; không lưu private key.
7. Server cung cấp kết quả và thông báo; khi đăng nhập sau này server dùng \`navigator.credentials.get()\` để kiểm chứng chữ ký phù hợp.

~~~mermaid
flowchart LR
    IDP["IdP / RP: challenge + RP ID"] --> WEB["Browser: WebAuthn create"]
    WEB --> AUTH["Authenticator: tạo cặp khóa"]
    AUTH --> WEB
    WEB --> VER["Server: kiểm origin, challenge, RP ID, UV"]
    VER --> STORE["Registry: credential ID + public key"]
    STORE --> LOGIN["Lần đăng nhập sau: ký challenge"]
~~~

**Vì sao chống phishing tốt hơn OTP?** WebAuthn ràng buộc thông tin xác thực với RP ID/origin và chứng minh sở hữu khóa bằng chữ ký cho challenge tương ứng. Trang giả ở origin khác không thể đơn giản thu một mã rồi gửi tới trang thật như với TOTP. Tuy nhiên, cần triển khai đúng kiểm tra giao thức, bảo vệ phiên enrollment, chống chiếm account và kiểm soát recovery.

### Platform, roaming và syncable passkeys

| Loại authenticator | Đặc điểm | Tác động chính sách |
| --- | --- | --- |
| **Roaming security key** | Khóa bảo mật rời, có thể dùng trên nhiều máy; nhiều loại bảo vệ private key trong phần cứng. | Phù hợp tài khoản đặc quyền khi tổ chức yêu cầu khóa vật lý riêng; cần quản lý bàn giao, mất và thay khóa. |
| **Platform authenticator** | Authenticator gắn với thiết bị (TPM, secure enclave hoặc phần cứng/phần mềm nền tảng). | Có thể tích hợp chính sách thiết bị; cần hiểu điều kiện chuyển máy hoặc sửa thiết bị. |
| **Syncable passkey** | Credential có thể đồng bộ/khôi phục qua nhà cung cấp nền tảng. | Thuận tiện cho người dùng, nhưng cần đánh giá tài khoản đồng bộ, cơ chế recovery và chính sách thiết bị. |

**Passkey không tự động đáp ứng cùng một mức bảo đảm trong mọi cấu hình.** Có thể cần bật và kiểm tra **user verification**, khả năng bảo vệ khóa, attestation hoặc yêu cầu khóa phần cứng riêng tùy mức rủi ro và tiêu chuẩn tổ chức áp dụng.

**Sinh trắc học/PIN** là phương thức mở khóa authenticator cục bộ; RP thường nhận bằng chứng cờ user verification từ quá trình mật mã, không nhận ảnh vân tay hoặc khuôn mặt thô.

## 7. Push MFA, SMS và phương thức dự phòng

### Push approval

Push MFA có thể tiện lợi nhưng dễ bị **MFA fatigue** nếu hệ thống liên tục gửi yêu cầu “Approve/Deny” khi kẻ tấn công biết mật khẩu người dùng. Nên:

- Hiển thị rõ ứng dụng, ngữ cảnh đăng nhập và chi tiết có ích để người dùng nhận biết.
- Sử dụng **number matching** hoặc cơ chế ràng buộc request/session khi nền tảng hỗ trợ.
- Giới hạn tần suất, phát hiện chuỗi từ chối và đăng nhập bất thường.
- Yêu cầu thiết bị/ứng dụng push được đăng ký với credential đáng tin; không chỉ thêm push token do client tự gửi.
- Cho phép người dùng báo cáo yêu cầu không phải của mình; tự động cảnh báo và kiểm tra account khi có dấu hiệu tấn công.

Number matching giúp giảm phê duyệt nhầm do “mệt mỏi push” nhưng **không biến mọi push approval thành phương thức chống phishing tương đương WebAuthn**.

### SMS và gọi điện

SMS/voice OTP có thể là phương án tương thích hoặc tiếp cận người dùng không có ứng dụng authenticator, nhưng rủi ro gồm **SIM swap**, chiếm số, chặn/chuyển hướng tin nhắn và phishing. Nếu chấp nhận chúng:

1. Chỉ dùng khi policy cho phép với tài nguyên tương ứng.
2. Xác minh **quyền kiểm soát số** trong enrollment, không chỉ nhập một số điện thoại rồi lưu.
3. Yêu cầu bước kiểm tra mạnh khi **thay số điện thoại**, nhất là khi thay cả phương thức MFA duy nhất.
4. Đặt thời hạn mã ngắn, giới hạn thử và tránh tiết lộ tài khoản có tồn tại hay không.
5. Khuyến nghị chuyển sang passkey/khóa bảo mật cho giao dịch nhạy cảm khi có khả năng.

### Recovery codes và phương thức dự phòng

Người dùng có thể mất điện thoại hoặc khóa bảo mật. Nên cho phép đăng ký **phương thức dự phòng** phù hợp chính sách hoặc cấp **recovery codes một lần** với hướng dẫn lưu an toàn, tách khỏi thiết bị chính.

Recovery code cần được sinh ngẫu nhiên đủ mạnh, hiển thị theo luồng bảo mật, **lưu dưới dạng hash/kiểm chứng an toàn ở server khi phù hợp**, giới hạn số lần thử, đánh dấu dùng rồi và vô hiệu hóa mã cũ khi phát hành bộ mới. Không gửi recovery code hay secret ra kênh hỗ trợ để nhân viên đọc hộ.

Nếu tổ chức yêu cầu hai khóa bảo mật cho quản trị viên, việc đăng ký khóa dự phòng nên có kiểm tra sở hữu và ghi log riêng. Không dùng một yếu tố dự phòng yếu tới mức có thể **vượt toàn bộ** policy áp dụng cho đăng nhập đặc quyền.

## 8. Chính sách enrollment theo độ nhạy của tài khoản

| Nhóm tài khoản | Ví dụ chính sách | Điểm kiểm soát enrollment |
| --- | --- | --- |
| Nhân viên thông thường | Ưu tiên passkey hoặc authenticator app; khuyến khích phương thức dự phòng. | Bảo đảm bootstrap, kiểm tra sở hữu, thông báo thêm/xóa method. |
| Nhân viên xử lý dữ liệu nhạy cảm | Phương thức chống phishing cho ứng dụng hoặc hành động có rủi ro cao. | Step-up và xác minh phiên; đánh giá loại authenticator trước khi cấp quyền nhạy cảm. |
| Quản trị viên đặc quyền | Khóa bảo mật/credential đáp ứng policy bảo đảm cao; ít nhất một phương án recovery được kiểm soát. | Phê duyệt riêng, kiểm soát reset, ghi log/alert liên tục; tránh hạ cấp sang SMS tùy tiện. |
| Nhà thầu | Phương thức phù hợp điều kiện truy cập, thời hạn hợp đồng và khả năng thu hồi. | Ràng buộc sponsor, nguồn danh tính, expiry và trách nhiệm hỗ trợ. |
| Người dùng có nhu cầu trợ năng | Chọn phương án tương đương mức bảo đảm, có quy trình hỗ trợ phù hợp. | Không yêu cầu một thiết bị hoặc sinh trắc duy nhất cho tất cả mọi người. |

### Chính sách minh họa

~~~yaml
policyId: workforce-authenticator-enrollment
accountType: HUMAN
allowedAuthenticators:
  - WEBAUTHN_PASSKEY
  - FIDO2_SECURITY_KEY
  - TOTP
enrollment:
  requireEligibleAccount: true
  requireTrustedBootstrapOrStepUp: true
  transactionTtlMinutes: 10
  proofOfPossessionRequired: true
  notifyOnChange: true
privilegedAccount:
  requirePhishingResistantAuthenticator: true
  requireIndependentRecoveryApproval: true
  disallowSmsAsSoleRecoveryPath: true
fallback: DENY
~~~

Đây là **YAML minh họa cho yêu cầu nghiệp vụ**, không phải schema cài đặt cho một IdP cụ thể. Con số TTL chỉ minh họa; policy thực tế phải dựa trên đặc tính giao thức, rủi ro và kiểm thử. Không dùng field \`privilegedAccount: true\` do client tự gửi để điều khiển chính sách.

## 9. Trạng thái và dữ liệu cần quản lý của MFA enrollment

Quy trình nên phân biệt **giao dịch đăng ký** với **bản ghi authenticator** để tránh kích hoạt sớm hoặc sót credential chưa hoàn tất.

~~~mermaid
flowchart LR
    S["STARTED"] --> P["PENDING_PROOF"]
    P --> A["ACTIVE"]
    P --> X["EXPIRED / CANCELLED"]
    A --> Q["SUSPENDED"]
    Q --> A
    A --> R["REVOKED"]
    Q --> R
~~~

Mỗi trạng thái có ý nghĩa riêng:

- \`STARTED\`: yêu cầu được tạo nhưng chưa hoàn tất điều kiện ban đầu.
- \`PENDING_PROOF\`: đã phát challenge/secret đăng ký và chờ bằng chứng sở hữu.
- \`ACTIVE\`: đã xác minh thành công và có thể dùng theo policy.
- \`EXPIRED/CANCELLED\`: giao dịch thất bại/hủy; credential pending không được chấp nhận.
- \`SUSPENDED\`: tạm thời không cho dùng trong khi kiểm tra sự cố, nguồn rủi ro hoặc yêu cầu khóa.
- \`REVOKED\`: credential bị thu hồi, không được tiếp tục chấp nhận.

Các state là ví dụ mô hình, không đồng nghĩa tất cả IdP đều cung cấp đúng từng nhãn. Trong thiết kế thực, phải xác định rõ khác biệt giữa **vô hiệu hóa tạm thời** và **thu hồi không thể phục hồi**.

Một bản ghi quản lý có thể gồm:

~~~yaml
authenticatorId: authn-6f28
subjectId: person-4821
identityProviderRef: workforce-idp
type: WEBAUTHN_PASSKEY
registeredAt: "2026-11-23T09:30:00Z"
status: ACTIVE
credentialRef: public-key-credential-reference
policyVersion: workforce-mfa-v4
enrollment:
  transactionId: enroll-17c9
  assuranceSource: trusted-bootstrap
  proofOfPossessionVerified: true
  verifiedAt: "2026-11-23T09:30:00Z"
device:
  managementRef: device-optional
  label: "Work laptop"
lastUsedAt: null
~~~

Đây là **schema minh họa**, không phải dữ liệu cấu hình thực tế. Với WebAuthn, registry cần lưu public key và các thông tin giao thức phù hợp; với TOTP, seed phải được lưu trong kho bí mật được bảo vệ. **Không ghi TOTP seed, private key, OTP, recovery code hoặc access token vào hồ sơ dùng cho báo cáo kiểm toán.**

Nhãn người dùng tự đặt như “Work laptop” chỉ để hiển thị, không phải bằng chứng thiết bị do công ty quản lý. Muốn áp chính sách device compliance cần liên kết với nguồn MDM/IdP đáng tin và kiểm tra độ mới của tín hiệu.

## 10. MFA enrollment trong Joiner–Mover–Leaver

MFA enrollment là phần của vòng đời **authenticator**, nhưng phải phản ứng với các biến động của **danh tính người dùng** và vai trò:

| Sự kiện | Việc cần làm với MFA | Hành động IAM liên quan | Rủi ro cần ngăn |
| --- | --- | --- | --- |
| **Joiner** | Thiết lập phiên bootstrap đủ mạnh, đăng ký authenticator đầu tiên và phương thức dự phòng phù hợp. | Identity proofing, tạo/kích hoạt IdP account, entitlement theo role, SCIM provisioning. | Tự đăng ký MFA trước khi xác minh người nhận; cấp quyền sớm. |
| **Mover thông thường** | Giữ authenticator còn tin cậy; đánh giá lại chính sách nếu vai trò mới nhạy cảm hơn. | Gỡ quyền cũ, cấp quyền mới, thay nhóm/chính sách truy cập. | Dùng MFA yếu cho đặc quyền mới; tồn dư quyền vai trò cũ. |
| **Mover sang đặc quyền cao** | Yêu cầu authenticator chống phishing, step-up và kiểm tra enrollment theo policy. | Phê duyệt quyền đặc biệt, separation of duties, privileged access có thời hạn. | Nâng quyền ngay khi chưa đạt điều kiện xác thực. |
| **Leaver** | Khóa đăng nhập, thu hồi/khóa authenticator theo khả năng IdP, xử lý phiên và thiết bị đã đăng ký. | IdP disable, deprovision SCIM, gỡ role/ACL, revoke session/token và kiểm tra SaaS. | Authenticator hoặc session cũ còn cho đăng nhập ứng dụng khác. |
| **Rehire** | Kiểm tra quan hệ với hồ sơ cũ và chính sách đăng ký lại; không tự tin mọi authenticator cũ. | Xác minh nguồn HR, kiểm tra trạng thái và cấp quyền mới từ đầu. | Email hoặc tài khoản cũ bị tái sử dụng dẫn đến truy cập nhầm. |

**Ví dụ:** Phúc chuyển từ nhân viên hỗ trợ sang quản trị hạ tầng. Tài khoản và danh tính của Phúc không nhất thiết thay đổi; passkey cũ có thể vẫn hợp lệ. Nhưng nếu chính sách quản trị yêu cầu khóa bảo mật phần cứng có bảo đảm cao, IAM phải chặn quyền quản trị cho tới khi Phúc đăng ký một authenticator đáp ứng điều kiện và hoàn tất phê duyệt. Việc tăng quyền và đăng ký MFA cần có bằng chứng riêng.

**Leaver:** Không nên nghĩ rằng xóa một passkey khỏi trang quản lý tài khoản là đủ. Phải vô hiệu hóa tài khoản, thu hồi quyền và xử lý session/refresh token ở IdP và ứng dụng, đồng thời kiểm tra tài khoản cục bộ hoặc API key có thể hoạt động độc lập.

## 11. Thêm, thay thế và xóa phương thức MFA

Thao tác **thêm một authenticator mới** đặc biệt nhạy cảm: nếu kẻ tấn công nắm session bị đánh cắp, họ có thể thêm thiết bị của mình để tạo quyền truy cập lâu dài. Vì vậy:

- Yêu cầu **recent authentication hoặc step-up** bằng phương thức đã đăng ký đáng tin, hoặc quy trình khôi phục có bảo đảm tương xứng.
- Gắn thao tác với account lấy từ ngữ cảnh server; không cho phép client chỉ đổi \`subjectId\` để thao tác trên người khác.
- Thực hiện proof of possession đối với authenticator mới trước khi active.
- Gửi thông báo đến kênh liên hệ tin cậy đã tồn tại, không chỉ đến kênh vừa đăng ký.
- Nếu cần thay phương thức duy nhất, xác minh chắc chắn người yêu cầu và tránh trạng thái khóa tài khoản ngoài ý muốn.
- Với admin/helpdesk thao tác hộ, cần phân quyền quản trị, lý do/ticket, approver, audit và giới hạn phạm vi thao tác.

**Xóa phương thức** phải xét số lượng phương thức còn lại và chính sách dự phòng. Một người có thể được phép xóa thiết bị cũ sau khi đăng ký thiết bị mới. Nếu xóa **phương thức cuối cùng**, hệ thống nên yêu cầu workflow recovery hoặc enrollment lại đáng tin, không mặc nhiên bỏ MFA để “đăng nhập tạm”.

### Tránh race condition và trạng thái bị đảo ngược

Giả sử người dùng cùng lúc gửi hai request xóa/phê duyệt authenticator. Server phải xử lý nhất quán để không vô tình xóa mọi yếu tố bắt buộc hoặc làm **active** một transaction đã bị **revoked**. Cần dùng transaction, version/optimistic concurrency hoặc cơ chế đồng bộ phù hợp và xác minh trạng thái tại thời điểm commit.

Mọi thao tác enrollment nên có **idempotency và anti-replay** đối với challenge/giao dịch; request đã hoàn tất không được sử dụng lại để thêm nhiều authenticator.

## 12. Recovery: mất điện thoại, mất khóa bảo mật hoặc không còn MFA

Recovery là một trong những điểm tấn công phổ biến nhất vào MFA. Người dùng có thể mất thiết bị, xóa ứng dụng OTP, đổi số điện thoại hoặc không còn quyền truy cập nền tảng đồng bộ passkey.

Quy trình nên gồm:

1. Người dùng mở yêu cầu recovery qua kênh được công bố chính thức; gắn với danh tính ổn định.
2. Server hoặc helpdesk kiểm tra **tín hiệu rủi ro**: thiết bị mới, địa lý bất thường, nhiều lần thất bại, thay đổi gần đây, quyền đặc biệt.
3. Nếu có recovery code hoặc authenticator dự phòng, yêu cầu kiểm tra chúng theo policy; với trường hợp không còn yếu tố nào, dùng **quy trình xác minh lại người yêu cầu** có mức tin cậy phù hợp.
4. Với account đặc quyền, có thể yêu cầu phê duyệt độc lập, kiểm tra trực tiếp hoặc các biện pháp tương đương theo chính sách.
5. Tạm khóa hoặc thu hồi các authenticator bị mất/nghi lộ khi phù hợp; tạo transaction enrollment mới với TTL và giới hạn riêng.
6. Xác minh authenticator mới bằng proof of possession, ghi audit và thông báo cho kênh tin cậy.
7. Cân nhắc yêu cầu đăng nhập lại, thu hồi phiên nhạy cảm và giám sát sau recovery; đối soát các sự kiện thêm/xóa credential.

**Không dùng chỉ tên, ngày sinh, mã nhân viên, thông tin công khai hoặc một cuộc gọi không xác minh để reset MFA cho quản trị viên.** Helpdesk không được yêu cầu người dùng gửi mật khẩu, OTP hay recovery code qua chat/email.

### Trường hợp mất khóa bảo mật duy nhất

Nếu không còn yếu tố thứ hai hoặc recovery code, tổ chức cần **quy trình hỗ trợ có phê duyệt** thay vì mặc định tắt MFA toàn bộ. Có thể cấp quyền bootstrap giới hạn chỉ để đăng ký phương thức mới, với thời hạn ngắn và giám sát. Phương thức bị mất phải bị vô hiệu hóa khi phù hợp, đặc biệt nếu kẻ khác có thể chiếm được khóa và PIN.

Recovery của passkey đồng bộ còn phụ thuộc khả năng khôi phục tài khoản nhà cung cấp nền tảng. Đội IAM cần xác định mức bảo đảm của chuỗi khôi phục ngoài tổ chức trước khi dựa vào đó cho đặc quyền cao.

## 13. Liên hệ IdP/SSO, SCIM, RBAC/ABAC và service account

| Thành phần | Liên quan đến MFA enrollment |
| --- | --- |
| **IdP** | Là nơi phổ biến để lưu authenticator và thực hiện enrollment/authentication, áp policy theo nhóm, trạng thái tài khoản và rủi ro. |
| **SSO (OIDC/SAML)** | Ứng dụng dựa vào kết quả xác thực của IdP; vẫn phải kiểm tra assurance, thời điểm xác thực và điều kiện phù hợp khi thao tác nhạy cảm. |
| **OAuth 2.0/OIDC** | Token và claim có thể truyền thông tin về phiên theo giao thức; không dùng access token sai audience hoặc tự tin chuỗi claim chưa xác minh. |
| **SCIM** | Đồng bộ danh tính/nhóm sang ứng dụng; **SCIM không phải giao thức đăng ký passkey, TOTP hay MFA challenge**. |
| **RBAC** | Vai trò quản trị, tài chính, người dùng thường có thể xác định chính sách yêu cầu MFA tối thiểu cho truy cập. |
| **ABAC** | Xem xét mức xác thực, thời điểm step-up, thiết bị, rủi ro, hành động và tài nguyên trong quyết định truy cập. |
| **IGA/identity lifecycle** | Đảm bảo Joiner được enroll đúng, Mover đáp ứng yêu cầu vai trò mới và Leaver bị thu hồi quyền/phiên. |
| **Service account/workload** | Thường xác thực bằng workload identity, certificate, client assertion hoặc token ngắn hạn; không áp MFA tương tác người dùng một cách máy móc vào job tự động. |

### Step-up authentication

Ví dụ nhân viên đã đăng nhập SSO để đọc lịch làm việc. Khi phê duyệt thanh toán lớn, ứng dụng có thể yêu cầu **step-up** bằng phương thức chống phishing và một **thời điểm xác thực đủ gần**. Trạng thái đã đăng ký MFA không tự chứng minh rằng **phiên hiện tại** vừa hoàn tất bước yêu cầu.

IdP/ứng dụng cần kiểm tra các claim hoặc kết quả xác thực phù hợp và đáng tin, chẳng hạn thời điểm xác thực \`auth_time\` hay ngữ cảnh/phương thức được công bố theo hợp đồng. Không dựa vào một boolean \`mfa=true\` do frontend tự khai.

**Authorization vẫn riêng biệt:** ngay cả khi user hoàn tất step-up, API phải kiểm tra quyền hành động, tenant, đối tượng, phê duyệt và giới hạn nghiệp vụ.

### Tài khoản dịch vụ có cần MFA?

Service account chạy tự động không thể bấm push hay nhập TOTP tương tác trong mỗi lần gọi API. Với non-human identity, ưu tiên **managed identity, workload federation, mTLS, private-key client authentication** hoặc credential được bảo vệ và luân chuyển phù hợp. MFA nên áp dụng cho **con người quản trị** service account, truy cập vault, đổi trust policy hoặc cấp quyền; quyền runtime của dịch vụ phải quản trị theo cách khác.

## 14. Các lỗi và đường tấn công cần phòng chống

| Lỗi/đe dọa | Kịch bản rủi ro | Kiểm soát cần có |
| --- | --- | --- |
| **MFA enrollment hijack** | Kẻ tấn công nắm session và thêm authenticator của mình. | Step-up, reauthentication, thông báo bảo mật và xác minh chủ thể. |
| **Yếu tố bootstrap quá yếu** | Biết email/mã nhân viên là đăng ký được yếu tố đầu tiên. | Proofing và kênh bootstrap có bảo đảm theo policy. |
| **OTP phishing / adversary-in-the-middle** | Mã TOTP bị nhập vào trang giả rồi dùng ngay trên trang thật. | Ưu tiên WebAuthn/passkey; huấn luyện và phát hiện rủi ro. |
| **MFA fatigue** | Kẻ xấu gửi push liên tục để người dùng nhấn chấp nhận. | Number matching, giới hạn push, phát hiện đăng nhập bất thường. |
| **SIM swap** | Kẻ tấn công chiếm số điện thoại và nhận SMS OTP. | Không ưu tiên SMS cho hệ thống nhạy cảm; bảo vệ quy trình đổi số. |
| **TOTP seed bị lộ** | QR hoặc seed xuất hiện trong log/ảnh/ticket. | Bảo vệ secret, ẩn sau phiên có kiểm soát, revoke/rotate khi lộ. |
| **WebAuthn verify thiếu điều kiện** | Server bỏ qua origin, challenge, RP ID hoặc user verification bắt buộc. | Kiểm đầy đủ giao thức, ràng buộc phiên và policy. |
| **Thêm method vào sai account** | API tin \`userId\` do client tự gửi. | Subject lấy từ session đã xác thực, ownership check ở backend. |
| **Recovery yếu hơn login** | Helpdesk reset MFA chỉ qua cuộc gọi tự khai. | Quy trình khôi phục có bảo đảm tương xứng, approval và audit. |
| **Downgrade/dự phòng yếu** | Tài khoản admin yêu cầu security key nhưng vẫn cho dùng SMS để bỏ qua. | Chính sách assurance toàn bộ đường đăng nhập và recovery. |
| **Chỉ xóa authenticator khi Leaver** | App cũ còn session hoặc token truy cập. | Disable identity, revoke session và đối soát các hệ thống đích. |
| **Thiếu anti-replay/rate limit** | Dùng lại transaction hoặc đoán OTP nhiều lần. | Challenge TTL, transaction state, throttle, kiểm tra sử dụng một lần. |

**MFA không loại bỏ hoàn toàn chiếm tài khoản.** Một tài khoản có thể bị xâm nhập từ malware, đánh cắp phiên, lạm dụng recovery hoặc kẽ hở authorization. Enrollment an toàn là một lớp bảo vệ trong tổng thể IAM.

## 15. Thiết kế API enrollment: ví dụ logic Java

Đoạn mã sau diễn đạt **các điều kiện cần** trong backend, không phải triển khai đầy đủ giao thức WebAuthn/TOTP. Nên dùng thư viện IdP/WebAuthn đã được kiểm chứng thay vì tự viết thuật toán mật mã.

~~~java
// Pseudocode: session được server xác minh và liên kết với đúng account.
EnrollmentTransaction beginEnrollment(
        TrustedSession session,
        AuthenticatorType requestedType) {

    UserIdentity subject = identityStore.get(session.subjectId());
    if (!subject.isEligibleForEnrollment()) {
        throw new AccessDeniedException("account_not_eligible");
    }

    if (!enrollmentPolicy.allows(subject, requestedType)) {
        throw new AccessDeniedException("method_not_allowed");
    }

    // Thay đổi yếu tố đăng nhập yêu cầu bootstrap/step-up đủ mạnh.
    if (!session.satisfiesRecentEnrollmentAssurance()) {
        throw new StepUpRequiredException();
    }

    // Lưu challenge + subjectId + policyVersion phía server;
    // transaction có thời hạn và số lần thử giới hạn.
    return enrollmentService.startOneTimeTransaction(
        subject.id(), requestedType, session.id());
}

AuthenticatorRecord finishEnrollment(
        TrustedSession session,
        String transactionId,
        AuthenticatorProof proof) {

    EnrollmentTransaction tx = enrollmentService.loadForUpdate(transactionId);
    if (!tx.subjectId().equals(session.subjectId())
            || !tx.isPendingAndNotExpired()
            || !tx.isBoundTo(session)) {
        throw new AccessDeniedException("invalid_enrollment_transaction");
    }

    // Bộ xác minh chuyên dụng cho TOTP hoặc WebAuthn; kiểm tra
    // challenge, proof-of-possession, RP/origin/UV khi áp dụng.
    VerifiedAuthenticator verified =
        authenticatorVerifier.verify(tx, proof);

    // Hoàn tất atomically để transaction không active hai lần.
    AuthenticatorRecord record =
        enrollmentService.activateAndConsume(tx, verified);

    audit.logAuthenticatorAdded(session.subjectId(), record.id());
    securityNotification.sendToTrustedExistingChannel(session.subjectId());
    return record;
}
~~~

Điểm cần giữ:

- **Không nhận \`subjectId\` của người khác từ request body** như căn cứ chính để ràng buộc authenticator.
- **Không ghi trạng thái ACTIVE trước khi \`verify()\` PASS.**
- TOTP proof là mã khớp với seed pending; WebAuthn proof là dữ liệu đăng ký hợp lệ sau khi kiểm đủ quy tắc giao thức.
- Bản ghi transaction phải dùng một lần, có TTL, chống replay và xử lý tranh chấp đồng thời.
- Log không chứa QR/TOTP secret, private key, password, recovery code hoặc token.
- Việc trả lỗi phải tránh lộ sự tồn tại/tình trạng account cho người không được quyền.

## 16. Kiểm toán và đối soát enrollment

Để trả lời “ai đăng ký phương thức nào, khi nào, bằng quyền gì?”, log cần hơn một dòng “MFA enabled”.

| Nhóm sự kiện | Dữ liệu nên có | Câu hỏi kiểm toán |
| --- | --- | --- |
| Khởi tạo enrollment | Subject ID, method type, transaction ID, policy version, timestamp, nguồn yêu cầu. | Ai bắt đầu đăng ký và theo quy tắc nào? |
| Bootstrap/step-up | Loại assurance/phương thức đã dùng, thời điểm, kết quả, correlation ID. | Vì sao phiên đủ điều kiện để thêm authenticator? |
| Xác nhận credential | Credential reference (không phải secret), loại, proof result, trạng thái. | Authenticator đã chứng minh quyền kiểm soát thành công chưa? |
| Thêm/xóa/thay thế | Actor, target subject, method ID, before/after, lý do, ticket và approver nếu có. | Ai đổi phương thức, có phải helpdesk/admin thao tác hộ không? |
| Recovery/reset | Trigger, quyết định, phương thức xác minh lại, ngoại lệ, người phê duyệt. | Vì sao một người được phép lấy lại tài khoản? |
| Rà soát/thu hồi | Account lifecycle state, authenticator state, hệ thống nhận lệnh, thời điểm xác nhận. | Sau Mover/Leaver, còn authenticator hoặc session nào sử dụng được? |

Chỉ lưu tham chiếu và metadata đủ cần thiết; bảo vệ audit log chống sửa đổi trái phép, có retention phù hợp và quyền truy cập hạn chế. Tránh lưu dữ liệu sinh trắc, số điện thoại đầy đủ hoặc định danh thiết bị nhạy cảm khi không cần.

Các chỉ số vận hành hữu ích:

- **MFA enrollment coverage:** tỷ lệ tài khoản cần MFA đã có phương thức active đúng policy.
- **Phishing-resistant coverage:** tỷ lệ tài khoản nhạy cảm thực sự có authenticator chống phishing đáp ứng yêu cầu.
- **Enrollment failure/abandonment:** tỷ lệ thất bại hoặc bỏ dở, tách theo phương thức và lý do.
- **Recovery rate:** số yêu cầu reset theo nhóm account, cảnh báo tăng đột biến.
- **Unexpected authenticator additions:** thêm phương thức mới sau sự kiện đăng nhập rủi ro, từ thiết bị lạ hoặc qua helpdesk.
- **Stale/unused authenticators:** phương thức lâu không sử dụng cần đánh giá, có xét đến khóa dự phòng cố ý ít dùng.
- **Leaver revocation completeness:** tỷ lệ tài khoản rời tổ chức đã khóa authenticator, session và quyền liên quan theo SLA.

**Không dùng tỷ lệ “MFA enabled” đơn lẻ để kết luận an toàn**: phương thức yếu, recovery lỏng hoặc tài khoản admin có ngoại lệ không kiểm soát vẫn gây rủi ro đáng kể.

## 17. Tình huống triển khai theo vòng đời

### Tình huống A – Nhân viên mới đăng ký passkey

Phương nhận laptop công ty vào ngày bắt đầu làm việc. HR đã xác minh hồ sơ và IAM đã tạo IdP account ở trạng thái đủ điều kiện. Hệ thống cấp luồng bootstrap có thời hạn để Phương đăng ký passkey; trình duyệt khởi tạo WebAuthn, authenticator tạo khóa, server kiểm tra challenge/origin/RP ID rồi lưu public key. Phương được yêu cầu hoàn tất lần xác thực đầu tiên, nhận thông báo đăng ký và đăng ký phương án dự phòng theo chính sách.

**Thất bại cần xử lý:** nếu Phương quên hoàn tất bước xác nhận, transaction pending phải hết hạn; nếu có người nhận được mã bootstrap nhưng danh tính chưa xác minh, không được tự kích hoạt quyền; nếu máy không đạt chính sách bảo mật, hệ thống có thể chặn tài nguyên nhạy cảm dù passkey đã đăng ký thành công.

### Tình huống B – Chuyển sang nhóm quản trị

Minh vốn dùng TOTP cho ứng dụng thông thường, nay trở thành quản trị viên cơ sở dữ liệu. IGA chỉ cấp quyền quản trị sau phê duyệt và khi Minh đăng ký một phương thức đạt yêu cầu chống phishing. Việc thêm khóa mới cần recent step-up hoặc quy trình xác minh thay thế đủ mạnh; sau đó API quản trị kiểm tra quyền, thiết bị, tính mới của xác thực và phạm vi tác vụ.

**Điểm cốt lõi:** đăng ký khóa mạnh không tự cấp admin; cấp role admin không tự biến TOTP thành phương thức chống phishing.

### Tình huống C – Mất điện thoại đang giữ TOTP

Linh báo mất điện thoại, nhưng vẫn có khóa bảo mật dự phòng. Linh dùng phương thức dự phòng để hoàn tất step-up, vô hiệu hóa TOTP cũ và đăng ký phương thức mới theo giao thức. Hệ thống gửi thông báo bảo mật, thu hồi session bị nghi rủi ro và ghi audit. Nếu Linh **không còn** phương thức dự phòng, yêu cầu đi qua quy trình recovery có kiểm tra danh tính và phê duyệt phù hợp, không sử dụng “tắt MFA một ngày” như đường tắt.

### Tình huống D – Nhân viên nghỉ việc

Khi Hạnh nghỉ việc, HR phát sự kiện Leaver. IdP disable account; IAM gỡ nhóm, role, deprovision qua SCIM và xử lý session/token ở các ứng dụng. Registry đánh dấu các authenticator của Hạnh không còn được sử dụng cho danh tính doanh nghiệp, đồng thời đối soát những ứng dụng có đăng nhập riêng để bảo đảm không còn đường truy cập. Log giữ được chuỗi sự kiện theo retention, nhưng secret và token không được giữ trong hồ sơ kiểm toán.

## 18. Bộ kiểm thử tối thiểu

| Tình huống kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Người dùng mới có proofing hợp lệ, account eligible và bootstrap đúng policy. | Được phép bắt đầu enrollment; chỉ active sau khi có proof hợp lệ. |
| Client thay \`subjectId\` thành account người khác khi thêm MFA. | Server ràng buộc subject từ phiên đáng tin, từ chối gắn sai. |
| WebAuthn response có origin/RP ID/challenge sai. | Từ chối và không lưu credential active. |
| TOTP QR đã hiển thị nhưng chưa nhập mã thử. | Authenticator vẫn pending, không dùng đăng nhập. |
| TOTP code đúng nhưng transaction hết hạn hoặc bị dùng lại. | Từ chối giao dịch cũ, không kích hoạt lại credential. |
| Người dùng đã đăng nhập nhưng phiên quá cũ để đổi MFA. | Yêu cầu step-up hoặc recovery được phê duyệt. |
| Tài khoản admin chỉ có TOTP, truy cập thao tác yêu cầu phương thức chống phishing. | Không cho bypass; yêu cầu đăng ký/xác thực phương thức đủ bảo đảm. |
| Đăng ký push rồi nhận chuỗi yêu cầu bất thường. | Rate limit, cảnh báo và cơ chế báo cáo lạm dụng hoạt động. |
| Người dùng thay số SMS mà chỉ chứng minh số mới. | Không tự đổi; cần chứng minh quyền thay đổi account theo policy. |
| Hai request hoàn tất cùng transaction song song. | Chỉ một request thành công; không tạo hai phương thức active từ một proof. |
| Người dùng xóa authenticator cuối cùng. | Yêu cầu cơ chế thay thế/recovery phù hợp, không tự vô hiệu MFA. |
| Leaver còn session ở ứng dụng legacy sau khi IdP disable. | Đối soát báo chưa hoàn tất và xử lý đường truy cập ở ứng dụng đích. |
| Một service account chạy job cần token để gọi API. | Dùng xác thực workload phù hợp; không buộc job nhận push tương tác của nhân viên. |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng nhập đúng mật khẩu rồi quét QR TOTP. Có thể đánh dấu phương thức đã đăng ký thành công ngay chưa?

**Trả lời:** Chưa. Cần xác minh phiên đủ điều kiện và người dùng thực sự kiểm soát TOTP seed, thường bằng mã thử hợp lệ; chỉ sau đó mới chuyển thành active.

**Câu 2.** Tại sao reset MFA qua helpdesk có thể nguy hiểm hơn đăng nhập thông thường?

**Trả lời:** Nếu helpdesk chấp nhận thông tin dễ đoán rồi thay authenticator, kẻ mạo danh có thể vượt qua yếu tố mạnh vốn bảo vệ đăng nhập. Recovery cần mức bảo đảm, phê duyệt, audit và giới hạn phù hợp.

**Câu 3.** WebAuthn passkey và TOTP có khác gì về khả năng chống trang phishing?

**Trả lời:** WebAuthn gắn bằng chứng mật mã với RP/origin và challenge, nên có khả năng chống phishing tốt khi kiểm tra đúng. TOTP là mã có thể bị người dùng nhập vào trang giả và dùng lại ngay trong thời gian còn hiệu lực.

**Câu 4.** Một nhân viên đã đăng ký MFA có tự động được quyền vào dữ liệu Finance không?

**Trả lời:** Không. Enrollment/xác thực giải quyết bằng chứng truy cập, còn authorization cần role, thuộc tính người dùng, tài nguyên, hành động và phê duyệt nghiệp vụ.

**Câu 5.** Khi nhân viên chuyển sang vai trò admin, cần đăng ký lại mọi phương thức MFA cũ không?

**Trả lời:** Không mặc định. Cần đánh giá phương thức hiện tại có đạt policy mới không; nếu không, đăng ký thêm hoặc thay bằng phương thức phù hợp và chỉ kích hoạt quyền đặc biệt sau khi đủ điều kiện.

**Câu 6.** Tắt tài khoản trên IdP có bảo đảm mọi đường truy cập SaaS và API mất hiệu lực ngay không?

**Trả lời:** Không. Phải xử lý session/refresh token, tài khoản và quyền ở ứng dụng đích, các credential độc lập và đối soát kết quả thực tế.

---

**Ghi nhớ:** Đăng ký MFA là **một nghi thức bảo mật để gắn authenticator với đúng danh tính**, có điều kiện bootstrap/step-up, proof of possession, transaction một lần, kiểm toán và cơ chế khôi phục. Chất lượng MFA phụ thuộc cả **enrollment, authentication, recovery và revocation**. Trong vòng đời Joiner–Mover–Leaver, IdP và IAM phải quản lý những thay đổi này đồng bộ với cấp quyền RBAC/ABAC và thu hồi quyền ở ứng dụng đích để tránh giữ lại phương thức hoặc phiên truy cập không còn hợp lệ.
