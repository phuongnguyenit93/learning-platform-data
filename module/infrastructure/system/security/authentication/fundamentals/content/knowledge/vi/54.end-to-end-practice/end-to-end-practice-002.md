# Xác định identity và factor: mô hình hóa chủ thể và yếu tố xác thực trong một luồng end-to-end

Một hệ thống xác thực an toàn bắt đầu bằng hai câu hỏi tưởng đơn giản: **ai đang yêu cầu truy cập, và bằng chứng nào cho thấy yêu cầu đó thực sự đến từ chủ thể ấy?** Câu hỏi thứ nhất xác định identity và principal. Câu hỏi thứ hai xác định authenticator và authentication factor. Nếu trộn lẫn các khái niệm này, hệ thống có thể nhận nhầm email là danh tính, coi địa chỉ IP là yếu tố xác thực, hoặc cho rằng hai bước nhập mã đều tạo thành MFA.

Bài thực hành này hướng dẫn người học xây dựng mô hình identity và factor cho một luồng xác thực hoàn chỉnh. Người học sẽ xác định chủ thể, chọn định danh ổn định, phân loại authenticator, đánh giá tính độc lập của các yếu tố, gắn mức bảo đảm với hành động và thiết kế các bước đăng ký, đăng nhập, xác thực tăng cường, khôi phục và thu hồi.

Phạm vi thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**: tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Trọng tâm của bài là mô hình hóa identity và factor trước khi lựa chọn công nghệ hoặc viết luồng đăng nhập.

## Mục tiêu học tập

Sau bài thực hành, người học có thể:

- Phân biệt thực thể ngoài đời, digital identity, account, identifier, principal, subject, credential, authenticator và factor.
- Xác định loại principal cần xác thực: người dùng, quản trị viên, workload hoặc danh tính liên kết.
- Chọn định danh nội bộ ổn định và liên kết danh tính bên ngoài theo issuer và subject.
- Phân loại bằng chứng theo knowledge, possession và inherence; nhận biết tín hiệu ngữ cảnh không phải factor.
- Đánh giá một hoặc nhiều authenticator có thực sự tạo thành MFA hay không.
- So sánh khả năng chống phishing, replay và chiếm đoạt của password, OTP, push, passkey và chứng chỉ.
- Xác định mức bảo đảm phù hợp với từng hành động và rủi ro.
- Mô hình hóa đăng ký, xác thực, step-up, recovery và thu hồi authenticator.
- Tạo được bảng quyết định, sơ đồ luồng, mô hình dữ liệu và bộ kiểm thử cho một hệ thống xác thực.

## 1. Bài toán thực hành

Hãy hình dung một cổng học tập trực tuyến có người học, giảng viên và nhân viên vận hành. Người dùng có thể đăng nhập bằng tài khoản nội bộ hoặc tài khoản từ một identity provider đã được tổ chức chấp nhận. Hệ thống hỗ trợ mật khẩu, passkey và một phương thức MFA dự phòng. Một số thao tác nhạy cảm yêu cầu xác thực lại gần đây.

Các hành động chính:

| Hành động | Ví dụ | Điều hệ thống cần xác minh |
|---|---|---|
| Truy cập thông thường | Xem trang học tập, xem lịch học | Chủ thể có account hợp lệ và đã xác thực |
| Thay đổi thông tin | Đổi email, số điện thoại khôi phục | Đúng chủ tài khoản; phiên đủ mới và có thể cần step-up |
| Quản lý credential | Thêm hoặc xóa passkey, đổi mật khẩu, đăng ký MFA | Người thực hiện kiểm soát tài khoản bằng bằng chứng hiện có |
| Truy cập dữ liệu nhạy cảm | Tải bảng điểm, xuất dữ liệu cá nhân | Principal được phép và mức xác thực đáp ứng policy |
| Quản trị | Thay đổi quyền, quản lý người dùng | Danh tính quản trị được xác minh với mức bảo đảm cao |
| Tích hợp hệ thống | Một workload gọi API đồng bộ dữ liệu | Danh tính workload và quyền của workload được xác minh |

Bài toán không yêu cầu chọn ngay một nhà cung cấp xác thực. Trước tiên hãy trả lời:

1. Có những loại chủ thể nào?
2. Mỗi chủ thể được nhận diện bằng identifier nào?
3. Hệ thống dựa vào authenticator nào để xác minh chủ thể?
4. Những yếu tố đó thuộc loại nào và có độc lập không?
5. Hành động nào yêu cầu mức bảo đảm cao hơn?
6. Khi credential bị mất hoặc bị chiếm đoạt, hệ thống khôi phục và thu hồi ra sao?

## 2. Phân biệt identity, account và credential

Các thuật ngữ liên quan chặt chẽ nhưng không thể dùng thay thế cho nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Thực thể (entity) | Người, tổ chức, thiết bị hoặc workload tồn tại trong phạm vi nghiệp vụ | Một học viên hoặc dịch vụ đồng bộ |
| Digital identity | Tập hợp thuộc tính và quan hệ mà hệ thống dùng để biểu diễn một thực thể | Hồ sơ người học có mã nội bộ và trạng thái |
| Account | Bản ghi và tập quyền của thực thể trong một dịch vụ cụ thể | Tài khoản trên cổng học tập |
| Identifier | Giá trị dùng để tìm hoặc tham chiếu một identity/account | Email, username, mã nhân viên, subject ID |
| Principal | Thực thể đã được hệ thống đưa vào ngữ cảnh bảo mật để đánh giá quyền | Người dùng sau khi xác thực thành công |
| Subject | Định danh principal trong token hoặc quyết định truy cập | Claim subject nội bộ |
| Credential | Bí mật hoặc bằng chứng được dùng trong một cơ chế xác thực | Password verifier, private key, TOTP secret |
| Authenticator | Thiết bị, ứng dụng hoặc cơ chế tạo bằng chứng xác thực | Passkey trên điện thoại, security key, ứng dụng TOTP |
| Authentication factor | Nhóm thuộc tính/bằng chứng mà người xác thực dựa vào | Knowledge, possession, inherence |
| Claim | Phát biểu về principal được truyền hoặc suy ra | Email đã xác minh, nhóm, vai trò, thời điểm xác thực |
| Session | Trạng thái tương tác được duy trì sau khi xác thực | Phiên trình duyệt có session cookie |

### 2.1. Email không phải identity

Email thường là identifier hoặc thuộc tính liên hệ. Nó có thể thay đổi, được chuyển tiếp, bị thu hồi, được tái cấp cho người khác hoặc chưa được xác minh. Hai hệ thống cũng có thể dùng cùng một email cho hai account khác nhau.

Vì vậy:

- Không dùng email làm khóa chính bất biến cho identity.
- Không tự động hợp nhất hai account chỉ vì email giống nhau.
- Phân biệt email người dùng khai báo với email đã được xác minh.
- Khi email thay đổi, cập nhật thuộc tính/identifier theo quy trình có kiểm soát.
- Ghi nhận nguồn và thời điểm xác minh thuộc tính nếu policy cần.

Một người có thể có nhiều email hoặc đổi email theo thời gian nhưng vẫn là cùng một identity nội bộ. Ngược lại, một email có thể được tái sử dụng sau khi chủ cũ rời tổ chức.

### 2.2. Chọn subject nội bộ ổn định

Hệ thống nên cấp một mã định danh nội bộ ổn định, không mang ý nghĩa nghiệp vụ dễ thay đổi. Ví dụ minh họa:

~~~text
principal_id = usr_01J8M7K4...
~~~

Mã này dùng để liên kết account, credential, session, audit event và quyền. Không nên đưa email hoặc username có thể thay đổi vào mọi quan hệ dữ liệu như thể chúng là định danh vĩnh viễn.

Đối với workload, dùng subject riêng cho workload hoặc service account, không giả làm người dùng. Một service có thể có nhiều deployment identity tùy môi trường và quyền cần thiết.

### 2.3. Xác thực khác với phân quyền

Xác thực (authentication) trả lời: “Bằng chứng có đủ để tin rằng principal là chủ thể được khai báo không?”

Phân quyền (authorization) trả lời: “Principal này được phép thực hiện hành động nào trên tài nguyên nào?”

Đăng nhập thành công không có nghĩa người dùng được phép xem bảng điểm của mọi người. Tương tự, việc token chứa một claim role không thay thế việc kiểm tra quyền trên từng tài nguyên. Identity và factor cung cấp ngữ cảnh cho quyết định truy cập; authorization policy vẫn phải được đánh giá riêng.

## 3. Xác định loại principal

Trước khi chọn factor, hãy xác định ai hoặc cái gì đang truy cập.

| Principal | Ví dụ | Cơ chế nhận diện thường gặp | Điều cần chú ý |
|---|---|---|---|
| Người dùng cuối | Học viên, giảng viên | Account nội bộ, passkey, password, MFA hoặc federation | Cần trải nghiệm recovery và bảo vệ chống phishing |
| Quản trị viên | Nhân viên vận hành | Identity workforce, passkey/security key, MFA mạnh | Quyền cao, cần step-up và audit rõ |
| Workload | Dịch vụ đồng bộ, job nền | Workload identity, certificate, managed identity hoặc key ngắn hạn | Không dùng password cá nhân; quản lý vòng đời machine credential |
| Client ứng dụng | Web app, mobile app, CLI | Client ID và cơ chế client authentication thích hợp | Client ID tự nó không chứng minh danh tính hoặc quyền |
| Identity liên kết | Người dùng được xác thực bởi IdP ngoài | Issuer và subject của IdP, ánh xạ sang principal nội bộ | Phải xác minh token/assertion và quy tắc liên kết |
| Principal được ủy quyền | Ứng dụng hành động thay mặt người dùng | Token có actor/delegation context | Phải phân biệt người dùng gốc và ứng dụng đang hành động |

### 3.1. Người dùng và workload không dùng chung mô hình credential

Người dùng có thể dùng password, passkey, OTP hoặc chứng chỉ người dùng. Workload thường dùng certificate, managed identity, workload federation hoặc credential ngắn hạn.

Không nên:

- Nhúng mật khẩu của nhân viên vào cron job.
- Dùng chung một API key cho nhiều dịch vụ.
- Cấp cho workload quyền tương đương tài khoản quản trị cá nhân.
- Dùng email người vận hành làm subject của một service account.
- Để token của người dùng được tái sử dụng làm danh tính máy mà không có delegation policy.

Với workload, câu hỏi chính là workload nào, chạy ở đâu, được phát hành credential bởi trust domain nào và được phép gọi API nào.

## 4. Liên kết identity từ nhiều nguồn

Một người dùng có thể đăng nhập bằng tài khoản nội bộ hôm nay và tài khoản federation ngày mai. Hệ thống cần liên kết hai phương thức với cùng principal mà không tạo cơ hội chiếm tài khoản.

### 4.1. Dùng issuer và subject cho external identity

Trong OIDC, cặp issuer và subject xác định một danh tính trong phạm vi issuer:

~~~text
external_identity_key = (issuer, subject)
~~~

Ví dụ:

~~~text
issuer  = https://idp.example.edu
subject = 00u8abc123
~~~

Một subject chỉ có ý nghĩa trong trust domain của issuer đó. Không giả định subject của hai issuer khác nhau là cùng một người dù chuỗi giống nhau.

Đối với SAML, cần dùng định danh NameID hoặc subject theo quy tắc của federation agreement và xét phạm vi/độ bền của định danh được phát hành. Không lấy một thuộc tính hiển thị bất kỳ làm khóa liên kết nếu hợp đồng federation không bảo đảm tính duy nhất và ổn định.

### 4.2. Vì sao không tự động liên kết chỉ bằng email?

Giả sử account nội bộ có email learner@example.edu. Một IdP bên ngoài gửi assertion có cùng email. Nếu hệ thống tự động liên kết chỉ theo email, một lỗi xác minh email, domain tái cấp hoặc cấu hình IdP có thể cho phép account ngoài chiếm account nội bộ.

Quy trình liên kết an toàn nên:

1. Người dùng đã đăng nhập vào account đích bằng một authenticator hiện có.
2. Người dùng chủ động chọn liên kết một IdP hoặc account khác.
3. Hệ thống chuyển đến IdP chính thức và xác minh response.
4. Hệ thống kiểm tra issuer, audience, chữ ký, thời hạn, state/nonce và các điều kiện federation.
5. Hệ thống xác nhận identity ngoài chưa bị liên kết với principal khác theo policy.
6. Hệ thống ghi liên kết và phát thông báo.
7. Người dùng có thể xem và thu hồi liên kết trong trang quản lý account.

Nếu cần quy trình hỗ trợ liên kết khi người dùng không còn authenticator cũ, phải dùng quy trình recovery/identity proofing có assurance tương ứng. Không biến email trùng thành bằng chứng đủ.

### 4.3. Thuộc tính identity cần có nguồn gốc

Với mỗi claim hoặc thuộc tính, hãy ghi:

- Ai phát hành?
- Đã xác minh bằng cách nào?
- Có thể thay đổi không?
- Có hết hạn hoặc cần xác minh lại không?
- Dùng cho đăng nhập, liên hệ, phân quyền hay chỉ hiển thị?
- Có được phép ghi đè thuộc tính nội bộ không?

Ví dụ, email do IdP gửi có thể chỉ là thuộc tính liên hệ. Role quản trị phải đến từ nguồn phân quyền được tin cậy, không tự động lấy từ một claim không nằm trong hợp đồng federation.

## 5. Nhận diện các loại authentication factor

Mô hình phổ biến chia yếu tố xác thực thành ba nhóm:

| Nhóm factor | Câu hỏi | Ví dụ |
|---|---|---|
| Knowledge — điều người dùng biết | Chủ thể biết bí mật nào? | Password, PIN, passphrase |
| Possession — thứ người dùng sở hữu/kiểm soát | Chủ thể kiểm soát thiết bị hoặc khóa nào? | Security key, private key, authenticator tạo OTP |
| Inherence — đặc điểm sinh trắc học | Chủ thể có đặc điểm sinh học nào? | Vân tay, khuôn mặt, giọng nói trong cơ chế xác minh phù hợp |

Cách phân loại cần xem xét cơ chế thực tế, không chỉ tên sản phẩm. Một điện thoại có thể chứa passkey và yêu cầu PIN hoặc sinh trắc học để mở khóa. Trong trường hợp này, authenticator có thể kết hợp possession với user verification tại thiết bị.

### 5.1. Knowledge factor

Knowledge factor là bí mật người dùng phải nhớ hoặc biết:

- Password.
- Passphrase.
- PIN được dùng để xác minh ở một hệ thống cụ thể.
- Một số shared secret được dùng trong quy trình xác thực.

Điểm mạnh là dễ triển khai và không đòi hỏi thiết bị đặc biệt. Điểm yếu là có thể bị phishing, đoán, tái sử dụng, keylogging hoặc rò rỉ qua dữ liệu khác.

Câu hỏi bảo mật như tên trường học, ngày sinh hoặc tên thú cưng thường có entropy thấp, dễ tìm trên mạng xã hội và khó thay đổi. Không nên dùng chúng làm yếu tố xác thực độc lập cho tài khoản quan trọng.

### 5.2. Possession factor

Possession factor dựa trên việc kiểm soát một thiết bị, khóa hoặc vật mang credential:

- Security key FIDO2.
- Private key trong authenticator.
- Ứng dụng tạo TOTP bằng shared secret.
- Smart card hoặc certificate token.
- Điện thoại nhận OTP qua SMS, với mức bảo đảm thấp hơn và phụ thuộc mạng di động.

Sự hiện diện của một thiết bị trong hồ sơ account chưa đủ chứng minh người dùng đang kiểm soát thiết bị đó ở thời điểm đăng nhập. Hệ thống cần challenge-response hoặc một cơ chế xác minh possession khác, có ràng buộc với giao dịch và chống replay.

### 5.3. Inherence factor

Inherence factor dùng đặc điểm sinh học như vân tay hoặc khuôn mặt. Trong các nền tảng passkey, sinh trắc học thường được dùng cục bộ để mở khóa authenticator hoặc xác minh user verification.

Cần phân biệt:

- Website nhận được kết quả xác minh từ authenticator theo giao thức.
- Website thường không nhận và không cần lưu ảnh vân tay/khuôn mặt thô.
- Sinh trắc học có thể không thay đổi được như password nếu bị lộ.
- Cảm biến và quy trình kiểm tra sinh trắc học có giới hạn, false accept và false reject.
- Sinh trắc học không tự động chống phishing nếu không gắn với giao thức xác thực ràng buộc origin.

Không gọi mọi thao tác Face ID hoặc fingerprint là một MFA độc lập ở phía server. Nếu sinh trắc học chỉ mở khóa private key trên thiết bị, hãy mô tả đúng vai trò local user verification của authenticator.

### 5.4. Những tín hiệu không phải factor

| Tín hiệu | Vai trò đúng | Vì sao không tự là factor |
|---|---|---|
| Địa chỉ IP | Context/risk signal | Có thể thay đổi, dùng chung qua NAT/VPN hoặc bị giả mạo ở một số lớp |
| Vị trí địa lý | Context/risk signal | Không chứng minh chủ thể kiểm soát một bí mật hoặc authenticator |
| User-agent/browser | Context/risk signal | Có thể giả mạo hoặc giống nhau giữa nhiều người |
| Device fingerprint | Tín hiệu nhận diện/rủi ro | Không phải bằng chứng possession đủ mạnh; có thể biến đổi và xâm phạm riêng tư |
| Email address | Identifier/thuộc tính liên hệ | Biết địa chỉ không chứng minh kiểm soát mailbox |
| Số điện thoại | Identifier/kênh liên hệ | Biết số không chứng minh kiểm soát SIM hoặc thiết bị |
| CAPTCHA | Chống lạm dụng tự động | Không chứng minh danh tính người dùng |
| Cookie phiên | Session bearer credential | Đại diện trạng thái phiên; bị đánh cắp có thể bị replay |

Context có thể làm policy yêu cầu step-up hoặc từ chối truy cập. Nhưng không nên cộng IP, browser và vị trí thành “ba yếu tố MFA”.

## 6. Authenticator không đồng nghĩa với factor

Authenticator là thiết bị hoặc cơ chế tạo ra bằng chứng. Một authenticator có thể sử dụng một hoặc nhiều factor.

| Authenticator | Factor hoặc thuộc tính thường liên quan | Lưu ý |
|---|---|---|
| Password | Knowledge | Bí mật được xác minh từ verifier phía server |
| TOTP app | Possession | Ứng dụng giữ seed; mã có thời hạn nhưng có thể bị phishing/relay |
| SMS OTP | Possession theo kiểm soát số điện thoại/SIM | Có rủi ro SIM swap, chuyển tiếp, SS7 và phishing |
| FIDO2 security key | Possession; có thể có user verification | Chữ ký được ràng buộc với RP ID/origin và challenge |
| Passkey trên điện thoại | Possession; có thể kết hợp local PIN/biometric UV | Có thể đồng bộ hoặc gắn thiết bị tùy loại credential |
| Smart card + PIN | Possession + knowledge | PIN mở khóa private key; mức bảo đảm phụ thuộc triển khai |
| Client certificate + private key | Possession | Cần xác minh chain, purpose, subject mapping và trạng thái chứng chỉ |
| Biometric unlock của passkey | Inherence tại thiết bị kết hợp authenticator possession | Server nhận assertion, không nhất thiết nhận dữ liệu sinh trắc học |

Không đếm số màn hình, số lần nhấn nút hoặc số mã nhập vào để xác định số factor. Hãy xác định loại bằng chứng độc lập mà mỗi bước thực sự yêu cầu.

## 7. Khi nào một luồng thực sự là MFA?

MFA (multi-factor authentication) yêu cầu ít nhất hai yếu tố thuộc các nhóm khác nhau, được dùng để xác minh cùng một phiên hoặc giao dịch theo một policy có ý nghĩa.

Ví dụ:

| Luồng | Có phải MFA? | Giải thích |
|---|---|---|
| Password + PIN dùng cùng kho password | Không mặc định | Cả hai có thể đều là knowledge |
| Password + TOTP app | Có, nếu TOTP authenticator được kiểm soát độc lập | Knowledge kết hợp possession |
| Password + SMS OTP | Thường được xem là hai nhóm, nhưng possession qua SMS có rủi ro cao | Cần đánh giá SIM swap, phishing và recovery |
| Password + security key | Có | Knowledge + possession |
| Passkey yêu cầu user verification trên authenticator | Có thể đáp ứng nhiều thuộc tính trong một ceremony | Cần đánh giá cách authenticator thực hiện UV và policy assurance |
| Hai mã OTP gửi qua hai kênh | Không tự động là MFA | Cả hai thường là possession qua kênh; phải xem có factor độc lập thực sự không |
| Password + địa chỉ IP quen thuộc | Không | IP là context, không phải factor |
| Password + CAPTCHA | Không | CAPTCHA là anti-automation control |
| Security key + cùng security key được mở bằng PIN | Có thể là possession + knowledge trong một authenticator | Cần dựa trên đặc tính và chứng nhận của authenticator |
| Password + câu hỏi bí mật | Không nên coi là MFA mạnh | Cả hai đều là knowledge và câu hỏi thường yếu |

### 7.1. Factor independence

Hai yếu tố cần có tính độc lập đủ để việc mất một yếu tố không tự động làm lộ yếu tố còn lại.

Hãy hỏi:

- Hai yếu tố có được lưu trong cùng một nơi không?
- Kẻ tấn công kiểm soát một thiết bị có thể lấy cả hai không?
- Cùng một phishing page có thể lấy cả hai bằng chứng không?
- Một quy trình recovery yếu có thể bỏ qua cả hai không?
- Có cùng một khóa hoặc cùng một kênh bảo vệ cho cả hai không?
- Một thao tác mở khóa có làm lộ cả password và OTP không?

Ví dụ, password và TOTP trên cùng điện thoại có thể tiện lợi nhưng rủi ro phụ thuộc vào cách ứng dụng lưu secret và bảo vệ thiết bị. Việc chúng nằm trên một thiết bị không tự động phủ nhận MFA, nhưng phải phân tích sự độc lập và khả năng chiếm đoạt chung.

### 7.2. MFA không đồng nghĩa phishing-resistant

MFA có thể giảm rủi ro khi password bị lộ nhưng vẫn bị tấn công qua phishing thời gian thực. Một trang phishing kiểu adversary-in-the-middle có thể chuyển tiếp password và OTP đến website thật rồi lấy session cookie hoặc token.

Phishing-resistant authentication cần ràng buộc bằng chứng với verifier/origin hoặc kênh tin cậy, chẳng hạn FIDO/WebAuthn đúng cấu hình. SMS OTP, email OTP và TOTP thường không có khả năng chống phishing ở mức tương đương passkey/WebAuthn.

## 8. Đánh giá authenticator theo khả năng chống tấn công

| Phương thức | Phishing | Replay | Khả năng thu hồi/thay thế | Ghi chú |
|---|---|---|---|---|
| Password | Dễ bị trang giả thu thập | Có thể phát lại nếu bị lộ | Đổi password và thu hồi phiên | Cần password hashing, rate limit và blocklist |
| SMS OTP | Có thể bị relay/phishing | Mã dùng một lần và ngắn hạn giảm replay sau khi dùng, nhưng vẫn có thể bị relay trước khi hết hạn | Đổi số hoặc thay phương thức; quy trình SIM có rủi ro | Không nên là phương thức duy nhất cho hành động rủi ro cao |
| Email OTP | Có thể bị phishing nếu mailbox bị chiếm | Phải dùng một lần và có TTL | Đổi kênh email và thu hồi token | Mailbox thường là kênh recovery, không mặc định là factor độc lập |
| TOTP | Có thể bị relay theo thời gian thực | Time step giới hạn nhưng server phải ngăn reuse theo policy | Reset enrollment và thay seed | Bảo vệ seed và chống brute force |
| Push approval | Có thể bị lừa chấp thuận | Challenge/number matching giảm một số kiểu lạm dụng | Hủy thiết bị hoặc enrollment | Chống push fatigue; hiển thị rõ giao dịch |
| Passkey/WebAuthn | Có khả năng chống phishing mạnh nhờ origin/RP ID binding | Challenge mới, one-time và chữ ký ràng buộc request | Thu hồi credential ID; đăng ký authenticator khác | Cần xác minh challenge, origin, RP ID, chữ ký và UV |
| Client certificate | Khó phishing hơn password nếu private key được bảo vệ và TLS binding đúng | TLS handshake có freshness; phải kiểm tra policy và trạng thái | Thu hồi certificate/rotate key | Cần quản lý PKI, mapping danh tính và revocation |

Bảng là so sánh khái quát. Cấu hình, triển khai, thiết bị, giao thức và quy trình recovery có thể làm mức bảo đảm thực tế thay đổi đáng kể.

### 8.1. Challenge và chống replay

Với cơ chế challenge-response, server tạo challenge ngẫu nhiên, gắn với phiên hoặc giao dịch, có thời hạn và chỉ được chấp nhận một lần. Authenticator ký hoặc tạo response cho challenge đó.

Một challenge tốt cần:

- Đủ ngẫu nhiên và không thể đoán.
- Gắn với đúng principal hoặc credential context.
- Có TTL ngắn phù hợp với giao thức.
- Được đánh dấu đã tiêu thụ một cách nguyên tử.
- Không được dùng lại giữa các giao dịch.
- Được kiểm tra cùng origin, RP ID hoặc audience theo giao thức.

TOTP dùng thời gian thay challenge riêng cho từng request. Server cần giới hạn time window, rate limit và cân nhắc lưu trạng thái để ngăn cùng mã được chấp nhận nhiều lần trong cùng cửa sổ nếu policy yêu cầu.

### 8.2. Phishing-resistant không loại bỏ mọi rủi ro

Passkey có thể chống phishing ở luồng xác thực vì assertion được ràng buộc với RP ID/origin. Tuy vậy, vẫn cần bảo vệ:

- Thiết bị và hệ điều hành chứa authenticator.
- Quy trình enrollment và account recovery.
- Khóa đồng bộ và tài khoản cloud của nhà cung cấp passkey.
- Session cookie và access token sau khi đăng nhập.
- Quy trình hỗ trợ khách hàng và thay đổi yếu tố.
- Chính sách authorization cho hành động nhạy cảm.

Nếu session token bị đánh cắp sau khi passkey xác thực thành công, attacker có thể tiếp tục sử dụng session cho đến khi bị thu hồi hoặc hết hạn. Phishing-resistant login không thay thế session security.

## 9. Chọn mức xác thực theo hành động

Không phải mọi thao tác đều cần cùng mức bảo đảm. Xác định mức yêu cầu dựa trên tác động nếu tài khoản bị chiếm, dữ liệu liên quan, khả năng đảo ngược và bối cảnh sử dụng.

| Hành động | Mức yêu cầu tham khảo | Ví dụ policy |
|---|---|---|
| Xem nội dung học tập công khai | Thấp | Session hợp lệ, account không bị khóa |
| Xem nội dung cá nhân | Cơ bản | Đăng nhập thành công, session còn hiệu lực |
| Đổi email hoặc số khôi phục | Trung bình/cao | Step-up bằng authenticator hiện có; thông báo thay đổi |
| Thêm hoặc xóa passkey/MFA | Cao | Xác thực lại gần đây; xác nhận bằng yếu tố hiện có; thông báo |
| Tải dữ liệu nhạy cảm | Cao | MFA hoặc passkey với user verification; session freshness |
| Thay đổi quyền quản trị | Rất cao | Phishing-resistant authenticator, step-up, audit và approval nếu cần |
| Workload truy cập API nhạy cảm | Theo trust policy | Workload identity, credential ngắn hạn, audience và scope giới hạn |

Đây là ma trận minh họa, không phải chuẩn assurance được chứng nhận. Tổ chức phải đặt policy dựa trên threat model, yêu cầu pháp lý và mức bảo đảm cần thiết.

### 9.1. Context ảnh hưởng quyết định nhưng không tạo thêm factor

Risk engine có thể dùng:

- Thiết bị mới hoặc chưa từng thấy.
- IP/ASN và vị trí bất thường.
- Hành vi đăng nhập khác baseline.
- Thời điểm hoặc tốc độ request bất thường.
- Phiên đã quá lâu kể từ lần xác thực gần nhất.
- Tài khoản vừa thay đổi email, password hoặc recovery factor.
- Tín hiệu từ threat intelligence hoặc endpoint protection.

Các tín hiệu này giúp quyết định yêu cầu step-up, giới hạn quyền hoặc từ chối. Không gọi chúng là factor thứ hai. Nếu IP quen thuộc, điều đó không biến password-only thành MFA.

### 9.2. Freshness và step-up

Một phiên được tạo từ xác thực mạnh cách đây nhiều giờ không nhất thiết đủ cho thao tác thay đổi khóa hoặc chuyển quyền. Policy có thể yêu cầu:

- Xác thực lại trong khoảng thời gian nhất định.
- Dùng authenticator cụ thể cho thao tác.
- Xác minh transaction details.
- Kiểm tra session chưa bị đánh dấu rủi ro.
- Tạo audit event có liên kết với request và principal.

Freshness là thuộc tính thời gian của lần xác thực, không phải factor mới.

## 10. Thiết kế vòng đời authenticator

Một authenticator không chỉ xuất hiện ở màn hình đăng nhập. Nó có vòng đời từ enrollment đến sử dụng, thay thế, thu hồi và xóa.

### 10.1. Enrollment — đăng ký authenticator

Một quy trình enrollment an toàn cần:

1. Xác định principal và account đích.
2. Yêu cầu xác thực hiện có hoặc identity proofing phù hợp.
3. Tạo challenge hoặc enrollment transaction mới.
4. Gắn credential mới với đúng account.
5. Xác minh response trước khi lưu trạng thái active.
6. Lưu metadata cần thiết, không lưu private key hoặc secret ở dạng lộ.
7. Thông báo cho chủ tài khoản về authenticator mới.
8. Cung cấp cách thu hồi nếu enrollment không phải do họ thực hiện.

Không nên cho phép một phiên yếu hoặc vừa recovery bằng kênh dễ chiếm đoạt thêm một authenticator có assurance cao mà không có kiểm soát bổ sung.

### 10.2. Authentication — sử dụng authenticator

Ở mỗi lần đăng nhập, hệ thống cần:

- Xác định principal/account dự định truy cập.
- Chọn authenticator được policy chấp nhận.
- Phát challenge hoặc tạo giao dịch xác thực mới khi giao thức yêu cầu.
- Xác minh bằng chứng, trạng thái credential và ràng buộc giao dịch.
- Kiểm tra account còn active và authenticator chưa bị thu hồi.
- Tạo authentication context cho session.
- Phát hành session/token với thời hạn, scope và assurance context phù hợp.

Không phát hành session chỉ vì client gửi lên một cờ như authenticated=true. Server phải tự xác minh kết quả từ authenticator hoặc trust provider.

### 10.3. Step-up — xác thực tăng cường

Khi người dùng thực hiện hành động nhạy cảm:

1. Policy đánh giá principal, hành động, tài nguyên, session freshness và risk context.
2. Nếu assurance hiện tại chưa đủ, server yêu cầu step-up.
3. Step-up challenge gắn với đúng session và hành động.
4. Người dùng hoàn tất bằng authenticator được chấp nhận.
5. Server xác minh response và ghi nhận thời điểm, phương thức, assurance.
6. Chỉ hành động đã được ràng buộc mới được tiếp tục.

Không dùng một lần step-up để mở quyền vô thời hạn cho mọi thao tác khác. Có thể cần transaction binding hoặc giới hạn quyền theo một hành động cụ thể.

### 10.4. Recovery — khôi phục authenticator

Khi người dùng mất thiết bị hoặc authenticator:

- Xác minh danh tính theo quy trình recovery được thiết kế riêng.
- Đánh giá recovery factor có yếu hơn factor ban đầu không.
- Áp dụng thời gian chờ hoặc giới hạn hành động rủi ro cao khi phù hợp.
- Thông báo qua kênh đã xác minh trước đó.
- Thu hồi authenticator cũ nếu mất hoặc nghi bị chiếm.
- Đăng ký authenticator mới theo quy trình enrollment.
- Kiểm tra session, token và phương thức recovery còn tồn tại.
- Ghi audit event và lưu bằng chứng quyết định.

Recovery là một phần của ranh giới xác thực. Một hệ thống có passkey rất mạnh nhưng cho phép đổi email recovery chỉ bằng một câu hỏi bí mật sẽ có đường vòng yếu hơn.

### 10.5. Revocation — thu hồi authenticator

Cần cho phép thu hồi khi:

- Thiết bị bị mất hoặc bị đánh cắp.
- Người dùng không còn kiểm soát private key/seed.
- Credential có dấu hiệu bị sao chép hoặc sử dụng bất thường.
- Nhân viên rời tổ chức hoặc workload bị ngừng.
- Certificate hết hạn, bị thu hồi hoặc khóa riêng có nguy cơ bị lộ.
- Người dùng chủ động xóa authenticator.

Sau thu hồi, xác minh mọi verifier, session và token liên quan đã cập nhật trạng thái. Xóa credential khỏi giao diện người dùng không nhất thiết làm credential ngừng hoạt động ở server.

## 11. Mô hình dữ liệu identity và authenticator

Một mô hình dữ liệu rõ ràng giúp tránh nhầm identifier, credential và factor.

### 11.1. Principal và external identity

Ví dụ cấu trúc khái niệm:

~~~yaml
principal:
  id: usr_01J8M7K4
  type: human
  status: active
  created_at: 2026-01-12T09:00:00Z
  identifiers:
    - type: email
      value: learner@example.edu
      verified: true
      primary: true
  external_identities:
    - issuer: https://idp.example.edu
      subject: 00u8abc123
      linked_at: 2026-02-02T10:30:00Z
~~~

Đây là mô hình minh họa. Trong triển khai thực tế, email và subject phải được lưu theo schema, ràng buộc uniqueness và chính sách thay đổi phù hợp. Không lưu token IdP như định danh lâu dài thay cho cặp issuer/subject.

### 11.2. Authenticator registry

Ví dụ cấu trúc metadata:

~~~yaml
authenticators:
  - id: authn_001
    principal_id: usr_01J8M7K4
    type: webauthn_passkey
    factor_categories:
      - possession
    user_verification: true
    phishing_resistant: true
    status: active
    created_at: 2026-02-02T10:35:00Z
    last_used_at: 2026-03-10T08:12:00Z

  - id: authn_002
    principal_id: usr_01J8M7K4
    type: totp
    factor_categories:
      - possession
    user_verification: false
    phishing_resistant: false
    status: active
    created_at: 2026-02-02T10:40:00Z
~~~

Không lưu private key của passkey trong registry ứng dụng. Với WebAuthn, lưu credential public key, credential ID và metadata cần thiết theo giao thức. Với TOTP, shared secret cần được bảo vệ bằng cơ chế mã hóa và kiểm soát truy cập; không đưa seed vào log hoặc bản ghi hiển thị.

### 11.3. Lưu verifier, không lưu bí mật thô

| Credential | Dữ liệu phía server thường cần | Không được làm |
|---|---|---|
| Password | Password hash/verifier với salt và tham số KDF | Lưu password plaintext |
| Passkey/WebAuthn | Credential ID, public key, counter/metadata cần thiết | Yêu cầu hoặc lưu private key |
| TOTP | Secret được bảo vệ, trạng thái enrollment và replay policy | Ghi seed hoặc OTP vào log |
| Client certificate | Trust chain, mapping subject/SAN, trạng thái certificate theo policy | Tin certificate chỉ vì client gửi một chuỗi subject |
| SMS/email OTP | Hash/verifier của mã tạm thời, TTL, attempt count, purpose | Lưu mã ở dạng lộ hoặc tái dùng không giới hạn |
| Recovery code | Verifier của mã, trạng thái used/revoked | Lưu hoặc hiển thị lại mã sau khi tạo |

### 11.4. Tách identity, authenticator và session

Một principal có thể có nhiều authenticator. Một authenticator có thể bị thu hồi mà account vẫn tồn tại. Một session được tạo từ một hoặc nhiều authenticator và có authentication context riêng.

Quan hệ khái niệm:

~~~text
Principal
  ├── Identifiers
  ├── External identity links
  ├── Authenticators
  │     ├── Credential metadata
  │     └── Factor capabilities
  ├── Sessions
  │     ├── Authentication time
  │     ├── Authentication methods
  │     └── Assurance context
  └── Authorization assignments
~~~

Không gộp toàn bộ dữ liệu vào một trường “login_type”. Cần phân biệt phương thức xác thực, factor category, authenticator ID, thời điểm xác thực, issuer và quyền được cấp.

## 12. Bảng quyết định cho bài toán cổng học tập

Giả sử cổng học tập hỗ trợ người dùng nội bộ và giảng viên. Hãy tạo policy minh họa:

| Principal/action | Authenticator được chấp nhận | Điều kiện bổ sung |
|---|---|---|
| Học viên xem nội dung | Passkey hoặc password; MFA nếu policy yêu cầu | Account active, session hợp lệ |
| Học viên đổi email | Passkey hoặc password + MFA | Xác thực gần đây, thông báo email cũ và mới |
| Giảng viên xuất bảng điểm | Passkey với UV hoặc MFA được phê duyệt | Step-up, scope phù hợp, audit event |
| Quản trị viên thay quyền | Phishing-resistant authenticator | Xác thực lại, session mới, audit và approval theo policy |
| Workload đồng bộ dữ liệu | Workload identity/certificate | Audience và scope giới hạn, credential ngắn hạn |
| Người dùng recovery | Recovery flow đã xác minh | Hạn chế thay đổi nhạy cảm trong thời gian chờ nếu policy yêu cầu |

Khi hoàn thiện bảng, cần ghi rõ phương thức nào là fallback, điều kiện nào làm fallback không còn đủ assurance và ai phê duyệt ngoại lệ.

## 13. Sơ đồ tổng quan của luồng end-to-end

~~~mermaid
flowchart TD
    A[Người dùng hoặc workload yêu cầu truy cập] --> B[Xác định principal và account]
    B --> C{Identity đã được liên kết và active?}
    C -->|Không| D[Enrollment hoặc quy trình identity proofing]
    D --> E[Liên kết identifier và authenticator]
    C -->|Có| F[Chọn authenticator theo policy]
    E --> F
    F --> G[Challenge hoặc xác minh credential]
    G --> H{Bằng chứng hợp lệ?}
    H -->|Không| I[Rate limit, ghi sự kiện và xử lý lỗi]
    H -->|Có| J[Tạo authentication context]
    J --> K{Hành động cần assurance cao hơn?}
    K -->|Có| L[Step-up bằng authenticator phù hợp]
    L --> M{Step-up thành công?}
    M -->|Không| I
    M -->|Có| N[Đánh giá authorization]
    K -->|Không| N
    N --> O{Được phép?}
    O -->|Không| P[Từ chối và audit]
    O -->|Có| Q[Thực hiện hành động và duy trì session]
~~~

Sơ đồ tách các bước xác định principal, xác minh authenticator, đánh giá assurance và authorization. Mỗi bước có thể thuộc một service khác nhau nhưng hợp đồng dữ liệu và trust boundary phải rõ ràng.

## 14. Luồng chi tiết: enrollment và login

### 14.1. Enrollment passkey

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant RP as Ứng dụng
    participant A as Authenticator
    U->>RP: Đã đăng nhập và yêu cầu thêm passkey
    RP->>RP: Step-up và tạo challenge mới
    RP-->>U: PublicKeyCredentialCreationOptions
    U->>A: Chọn authenticator và xác minh người dùng
    A-->>U: Credential response
    U->>RP: Gửi credential response
    RP->>RP: Kiểm tra challenge, origin, RP ID, user verification
    RP->>RP: Lưu credential public key và metadata
    RP-->>U: Thông báo passkey đã đăng ký
~~~

Các điểm phải xác minh:

- Challenge mới, gắn với phiên và có thời hạn.
- Origin và RP ID đúng.
- User handle gắn với principal nội bộ.
- Public key và credential ID được lưu an toàn.
- Credential không được đăng ký hai lần trái policy.
- Người dùng nhận thông báo và có cách thu hồi.

### 14.2. Login bằng passkey

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant RP as Ứng dụng
    participant A as Authenticator
    U->>RP: Bắt đầu đăng nhập
    RP->>RP: Tạo challenge ngẫu nhiên
    RP-->>U: PublicKeyCredentialRequestOptions
    U->>A: Chọn passkey và xác minh người dùng
    A-->>U: Assertion đã ký
    U->>RP: Gửi assertion
    RP->>RP: Kiểm tra challenge, origin, RP ID và chữ ký
    RP->>RP: Kiểm tra credential active và account status
    RP-->>U: Tạo session với authentication context
~~~

Nếu kiểm tra thất bại, không tạo session. Phản hồi client nên đủ hữu ích để người dùng thử lại hoặc dùng recovery, nhưng không tiết lộ dữ liệu nhạy cảm về account hoặc credential.

## 15. Phân tích threat và trust boundary

Dùng bảng sau để xác định nơi identity/factor có thể bị tấn công:

| Trust boundary | Tài sản | Threat | Kiểm soát cần xem |
|---|---|---|---|
| Người dùng ↔ trình duyệt | Password, OTP, passkey interaction | Phishing, malware, shoulder surfing | Origin rõ, WebAuthn, bảo vệ thiết bị |
| Trình duyệt ↔ website | Credential, session cookie | XSS, CSRF, form injection, session theft | TLS, CSP, CSRF, cookie flags, input semantics |
| Website ↔ IdP | Assertion, ID token, access token | Issuer/audience sai, replay, redirect abuse | Signature, issuer, audience, state, nonce, PKCE |
| Ứng dụng ↔ database | Password verifier, TOTP secret, public key | Data breach, privilege escalation | KDF, encryption, least privilege, audit |
| CI/CD ↔ artifact registry | Signing key, build credential | Dependency compromise, artifact substitution | Short-lived credentials, provenance, signature verification |
| Service ↔ service | Workload identity, certificate, token | Token theft, confused deputy, overbroad scope | Audience, mTLS/workload identity, rotation |
| Recovery channel ↔ account | Recovery token, email/phone | SIM swap, mailbox takeover, social engineering | One-time token, TTL, step-up, notification, delay |

### 15.1. Threats thường gặp

- **Account enumeration:** phản hồi khác nhau làm lộ account có tồn tại.
- **Credential stuffing:** dùng mật khẩu rò rỉ từ dịch vụ khác.
- **MFA fatigue:** gửi nhiều push để người dùng chấp thuận theo phản xạ.
- **OTP relay:** attacker chuyển tiếp OTP trong phiên phishing thời gian thực.
- **Replay:** dùng lại response hoặc mã đã được chấp nhận.
- **Account linking abuse:** liên kết identity ngoài vào account nạn nhân.
- **Authenticator enrollment abuse:** thêm factor của attacker sau khi chiếm một phiên yếu.
- **Recovery bypass:** quy trình khôi phục yếu hơn xác thực bình thường.
- **Session theft:** lấy cookie hoặc token sau khi xác thực mạnh.
- **Workload impersonation:** dùng nhầm client ID hoặc secret dùng chung để giả danh service khác.

## 16. Bài tập thực hành theo từng bước

Hãy hoàn thành bài tập như một buổi design review. Không cần viết ứng dụng hoàn chỉnh; cần tạo ra các quyết định có thể kiểm tra được.

### Bước 1 — Liệt kê principal

Viết danh sách các chủ thể có thể truy cập hệ thống. Tối thiểu gồm:

- Học viên.
- Giảng viên.
- Quản trị viên.
- Workload đồng bộ dữ liệu.

Với mỗi principal, ghi loại (human/workload), account owner, nguồn identity và phạm vi quyền.

### Bước 2 — Chọn identifier

Với từng principal:

- Chọn internal principal ID bất biến.
- Liệt kê identifier đăng nhập và thuộc tính liên hệ.
- Ghi nguồn phát hành và trạng thái xác minh.
- Xác định thuộc tính nào có thể đổi.
- Chọn external identity key nếu có federation.

Không dùng email làm khóa chính. Nếu dùng OIDC, ghi cặp issuer/subject.

### Bước 3 — Phân loại authenticator

Tạo danh sách authenticator được hỗ trợ:

- Password.
- TOTP.
- SMS OTP hoặc email OTP nếu policy cho phép.
- Passkey/WebAuthn.
- Client certificate hoặc workload identity cho service.

Với mỗi loại, ghi factor category, khả năng chống phishing, replay, cách thu hồi và recovery.

### Bước 4 — Xác định assurance theo hành động

Liệt kê ít nhất năm hành động. Đánh dấu hành động nào yêu cầu session freshness, MFA, phishing-resistant authentication hoặc approval.

### Bước 5 — Vẽ luồng enrollment và login

Vẽ sơ đồ hoặc viết sequence cho:

- Người dùng đăng ký passkey.
- Người dùng đăng nhập bằng password + TOTP.
- Người dùng thực hiện step-up để thay email.
- Workload gọi API bằng certificate/managed identity.

### Bước 6 — Thiết kế recovery

Mô tả cách xử lý khi:

- Người dùng mất điện thoại chứa passkey.
- Người dùng mất TOTP seed.
- Email khôi phục bị thay đổi.
- Quản trị viên mất security key.
- Workload certificate bị lộ.

Với mỗi trường hợp, xác định bằng chứng thay thế, người phê duyệt, thời gian chờ, thông báo và hành động thu hồi.

### Bước 7 — Tạo test matrix

Viết ít nhất tám test case dương và âm. Phải có:

- Credential đúng và sai.
- Challenge hết hạn.
- Challenge đã dùng.
- Token sai issuer hoặc audience.
- Passkey sai origin/RP ID.
- Account bị khóa hoặc authenticator bị revoke.
- Liên kết identity bằng email trùng nhưng chưa xác minh.
- Recovery sau khi mất factor.

### Bước 8 — Review tính nhất quán

Kiểm tra xem identifier, factor, session và authorization có bị trộn lẫn không. Một quyết định tốt phải giải thích được vì sao bằng chứng đủ, hành động nào được phép và cách thu hồi khi có sự cố.

## 17. Worksheet để ghi kết quả

Dùng bảng sau làm bản ghi quyết định.

| Trường | Giá trị cần ghi |
|---|---|
| Principal type | Human / workload / client / delegated |
| Internal principal ID | Mã ổn định, không phụ thuộc email |
| Account source | Internal / federated / provisioned |
| Identifier | Username, email, employee ID hoặc subject |
| Identifier issuer | Hệ thống phát hành identifier |
| Identifier verified | Cách và thời điểm xác minh |
| Authenticator | Password, TOTP, passkey, certificate... |
| Factor category | Knowledge / possession / inherence |
| Factor independence | Phân tích phụ thuộc chung |
| Phishing resistance | Có/không/mức giới hạn và lý do |
| Replay protection | Challenge, TTL, one-time consume, counter hoặc policy |
| Enrollment proof | Bằng chứng trước khi gắn authenticator |
| Recovery method | Phương thức dự phòng và assurance |
| Revocation path | Cách vô hiệu hóa authenticator/session |
| Allowed actions | Tài nguyên và hành động được phép |
| Step-up requirement | Điều kiện và freshness |
| Audit evidence | Event ID, actor, thời điểm, kết quả |

### 17.1. Mẫu ghi một principal

~~~yaml
principal:
  id: usr_learner_1042
  type: human
  account_status: active
  identifiers:
    - kind: email
      value: learner@example.edu
      verified: true
      issuer: internal-account-service
  authenticators:
    - kind: webauthn_passkey
      factor_categories:
        - possession
      user_verification: true
      phishing_resistant: true
      status: active
    - kind: password
      factor_categories:
        - knowledge
      status: active
  policy:
    normal_access: passkey_or_password_plus_mfa
    sensitive_action: recent_phishing_resistant_authentication
~~~

Mẫu trên minh họa cách diễn đạt, không phải schema chuẩn. Hệ thống thực tế cần xác định kiểu dữ liệu, kiểm tra uniqueness, mã hóa, quyền đọc/ghi và quy tắc migration.

## 18. Bộ test chấp nhận

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| IDF-01 | Người dùng đăng nhập bằng principal ID nội bộ hợp lệ | Server ánh xạ đúng account |
| IDF-02 | Hai account có cùng email chưa xác minh | Không tự động hợp nhất |
| IDF-03 | Hai issuer có cùng subject string | Tạo hai external identity khác nhau |
| IDF-04 | Email thay đổi sau khi xác minh | Principal ID không đổi; identifier cập nhật theo policy |
| IDF-05 | Password đúng nhưng account bị khóa | Không tạo session |
| IDF-06 | Password + TOTP hợp lệ | MFA hoàn tất theo policy |
| IDF-07 | Password + IP quen thuộc | Không được tính là MFA |
| IDF-08 | OTP đã dùng được gửi lại | Bị từ chối theo replay policy |
| IDF-09 | Passkey assertion có origin sai | Bị từ chối |
| IDF-10 | Challenge hết TTL | Bị từ chối |
| IDF-11 | Authenticator đã revoke | Không thể xác thực |
| IDF-12 | Người dùng thêm passkey từ session cũ | Yêu cầu step-up theo policy |
| IDF-13 | Người dùng recovery bằng email vừa thay đổi | Áp dụng delay/kiểm soát theo policy, không tự bỏ qua factor |
| IDF-14 | Workload dùng credential của workload khác | Bị từ chối do subject/audience/scope không khớp |
| IDF-15 | ID token được gửi đến API như access token | API từ chối nếu audience/token type không đúng |
| IDF-16 | User role claim đến từ issuer không tin cậy | Không cấp quyền dựa trên claim đó |

### 18.1. Kiểm thử factor independence

Ngoài test chức năng, hãy thử các câu hỏi sau:

- Nếu điện thoại bị chiếm, attacker có lấy được cả password và TOTP không?
- Nếu mailbox bị chiếm, attacker có thể reset password và MFA không?
- Nếu session cookie bị đánh cắp, attacker có thêm authenticator mới không?
- Nếu recovery code bị lộ, nó có thể được dùng nhiều lần không?
- Nếu một IdP bị xâm phạm, account nội bộ có bị liên kết tự động không?

Nếu câu trả lời cho thấy một điểm lỗi đơn có thể bỏ qua toàn bộ factor, cần sửa thiết kế hoặc ghi nhận rủi ro và biện pháp giảm thiểu.

## 19. Các lỗi mô hình hóa thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Dùng email làm primary key | Thay email làm gãy quan hệ hoặc tạo nhầm identity | Dùng principal ID bất biến |
| Tự động liên kết account theo email | Account takeover qua claim không đáng tin hoặc email tái cấp | Dùng issuer+subject và xác minh account đích |
| Gọi IP là factor | Đánh giá sai MFA | Phân loại IP là context/risk signal |
| Đếm password + PIN là hai factor | MFA giả | Xem cả hai thuộc knowledge nếu cùng bản chất |
| Cho rằng mọi OTP chống phishing | Bị relay qua phishing thời gian thực | Dùng passkey/WebAuthn khi cần phishing resistance |
| Cho rằng passkey giải quyết recovery | Account vẫn có thể bị chiếm qua recovery yếu | Bảo vệ enrollment và recovery |
| Không phân biệt authenticator với factor | Ghi sai assurance và policy | Lưu loại authenticator và factor capability riêng |
| Gộp user và workload | Credential dùng chung, audit không rõ | Principal type và credential policy riêng |
| Tạo session trước khi xác minh đầy đủ | Session trái phép | Chỉ phát hành session sau khi server xác minh |
| Xóa authenticator chỉ ở UI | Credential vẫn được chấp nhận | Thu hồi ở verifier/server và kiểm tra propagation |
| Dùng một lần MFA cho mọi hành động | Quyền step-up tồn tại quá lâu | Gắn freshness và transaction context |
| Recovery yếu hơn login | Attacker bỏ qua factor mạnh | Thiết kế recovery theo threat model và assurance |

## 20. Kết quả cần nộp

Một bài thực hành được xem là hoàn tất khi có đủ các sản phẩm sau:

1. **Principal inventory:** danh sách loại principal và chủ thể.
2. **Identity map:** internal principal ID, identifier, issuer và external identity link.
3. **Authenticator matrix:** loại authenticator, factor category, independence, phishing resistance và revocation.
4. **Action assurance matrix:** hành động và mức xác thực yêu cầu.
5. **Enrollment/login flow:** sơ đồ hoặc sequence diagram có challenge và trust boundary.
6. **Recovery plan:** phương thức thay thế, delay, notification và revocation.
7. **Test matrix:** test dương/âm bao gồm replay, phishing, identity linking và recovery.
8. **Decision record:** lý do chọn, giả định, rủi ro còn lại và người chịu trách nhiệm.

Không chấp nhận kết quả chỉ liệt kê “password + OTP + passkey”. Người học phải giải thích principal nào dùng credential nào, factor thuộc nhóm gì, bằng chứng được xác minh ở đâu và policy cho phép hành động nào.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao email không nên là khóa chính bất biến của identity?

**Gợi ý:** Email có thể đổi, bị thu hồi hoặc tái cấp cho người khác. Dùng principal ID nội bộ ổn định và lưu email như identifier có trạng thái xác minh.

**Câu 2.** Trong OIDC, vì sao cần liên kết external identity bằng issuer và subject?

**Gợi ý:** Subject có ý nghĩa trong phạm vi issuer. Hai issuer khác nhau có thể phát hành cùng một chuỗi subject cho hai người khác nhau.

**Câu 3.** Password + địa chỉ IP quen thuộc có phải MFA không?

**Gợi ý:** Không. Password là knowledge factor; IP chỉ là context/risk signal, không chứng minh possession hoặc inherence.

**Câu 4.** Password + TOTP có thể được xem là MFA trong điều kiện nào?

**Gợi ý:** Khi password là knowledge, TOTP authenticator chứng minh possession, hai yếu tố được xác minh trong cùng giao dịch và policy xử lý replay, rate limit và enrollment phù hợp.

**Câu 5.** Vì sao OTP có thể bị phishing dù có thời hạn ngắn?

**Gợi ý:** Attacker có thể relay mã trong thời gian nó còn hiệu lực và lấy session từ website thật. TTL ngắn giảm cửa sổ replay nhưng không tạo origin binding.

**Câu 6.** Passkey có thể dùng sinh trắc học mà website không cần lưu sinh trắc học bằng cách nào?

**Gợi ý:** Authenticator thực hiện user verification cục bộ rồi ký assertion. Website xác minh assertion và cờ user verification theo giao thức, không cần nhận ảnh sinh trắc học.

**Câu 7.** Vì sao cần step-up khi thêm authenticator mới?

**Gợi ý:** Nếu một phiên yếu bị chiếm, attacker có thể gắn authenticator của mình vào account rồi duy trì truy cập. Step-up và thông báo giúp bảo vệ quá trình binding.

**Câu 8.** Nếu người dùng mất điện thoại chứa passkey, có nên tự động chuyển sang email là đủ không?

**Gợi ý:** Không mặc định. Recovery phải được đánh giá theo assurance và rủi ro của account; email có thể là kênh liên hệ yếu hơn và cần kiểm soát bổ sung.

**Câu 9.** Một certificate client có subject đúng tên người dùng đã đủ xác thực chưa?

**Gợi ý:** Chưa. Phải xác minh chain, issuer/trust anchor, thời hạn, key usage/EKU, proof of private-key possession, revocation policy và mapping subject sang principal.

**Câu 10.** Đăng nhập thành công có tự cấp quyền quản trị không?

**Gợi ý:** Không. Authentication xác minh principal; authorization policy quyết định principal được phép thực hiện hành động nào.

## 22. Nguyên tắc cần ghi nhớ

1. Identity là biểu diễn của chủ thể; account là quan hệ với một dịch vụ; identifier chỉ giúp tìm hoặc tham chiếu.
2. Dùng principal ID nội bộ ổn định; với federation, liên kết external identity theo issuer và subject.
3. Authenticator là thiết bị/cơ chế tạo bằng chứng; factor là nhóm thuộc tính mà bằng chứng dựa vào.
4. Knowledge, possession và inherence là các nhóm factor phổ biến; IP, vị trí, browser và CAPTCHA là context hoặc anti-abuse signal.
5. MFA cần các factor khác nhóm và đủ độc lập; nhiều bước hoặc nhiều mã không tự tạo MFA.
6. OTP có thể bị relay; passkey/WebAuthn giúp chống phishing khi challenge, origin và RP ID được xác minh đúng.
7. Enrollment, step-up, recovery và revocation là các phần của vòng đời xác thực, không phải chức năng phụ.
8. Authentication context không thay thế authorization; mọi hành động vẫn cần kiểm tra quyền và phạm vi.
9. Không lưu bí mật thô khi verifier hoặc public-key metadata là đủ; bảo vệ secret theo đúng loại credential.
10. Một mô hình identity/factor tốt phải giải thích được chủ thể, bằng chứng, trust boundary, mức bảo đảm, hành động và cách thu hồi.

Kết quả của bài thực hành là một mô hình có thể review và kiểm thử: mỗi principal có định danh rõ ràng, mỗi authenticator có factor và vòng đời cụ thể, mỗi hành động có yêu cầu assurance phù hợp, và mọi đường enrollment/recovery đều được xem như một phần của bề mặt tấn công.

