# Reauthentication evidence

## Mục tiêu và phạm vi

**Reauthentication evidence** là bằng chứng đã được dịch vụ xác minh để kết luận người đang thực hiện một yêu cầu còn kiểm soát phương thức xác thực phù hợp của đúng tài khoản. Bằng chứng phải trả lời được: ai được xác thực, bằng phương thức nào, khi nào, trong context nào và kết quả đó đủ cho hành động gì.

Trong chương **Reauthentication** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bài học tập trung vào chất lượng và cách sử dụng bằng chứng khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là liên kết đánh giá rủi ro, token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát session để giảm nguy cơ chiếm đoạt tài khoản.

Sau bài này, người học cần có khả năng:

- Phân biệt dữ liệu client gửi, kết quả verifier đã kiểm tra và quyền thực hiện hành động.
- Đánh giá nguồn gốc, độ mới, mức bảo đảm, binding và khả năng chống replay của bằng chứng.
- Chuẩn hóa kết quả mật khẩu, OTP, passkey hoặc IdP mà không làm mất giới hạn của từng phương thức.
- Ngăn việc dùng credential mới tạo trong recovery để hợp thức hóa một quyết định cấp quyền thiếu căn cứ.
- Lưu bằng chứng đủ để thực thi và audit mà không lưu lại bí mật xác thực.

Các profile, trạng thái, mốc thời gian và cấu trúc dữ liệu trong bài là thiết kế minh họa của một dịch vụ giả định. Chúng không phải định dạng chuẩn bắt buộc hoặc bằng chứng một hệ thống đã đáp ứng đầy đủ một mức AAL.

## 1. Bằng chứng không phải mọi thông tin có vẻ liên quan đến người dùng

### 1.1. Tách năm lớp dữ liệu

| Lớp | Ví dụ | Giá trị thực tế |
| --- | --- | --- |
| Định danh | Username, email, account ID | Chỉ ra tài khoản cần xét |
| Tín hiệu bối cảnh | IP, User-Agent, cookie thiết bị, lịch sử hành vi | Hỗ trợ đánh giá rủi ro, với độ tin cậy khác nhau |
| Authenticator output | Mật khẩu vừa nhập, OTP, assertion WebAuthn | Dữ liệu cần được verifier kiểm tra |
| Kết quả xác minh | Credential được chấp nhận, subject, thời điểm, thuộc tính đã kiểm tra | Cơ sở tạo bản ghi bằng chứng |
| Quyết định cấp quyền | Cho action, yêu cầu thêm bằng chứng, recovery hoặc hold | Kết quả áp dụng policy lên bằng chứng và trạng thái hiện tại |

Tên hiển thị đúng không chứng minh quyền sở hữu. Một IP quen thuộc không tự chứng minh người dùng kiểm soát authenticator. Một assertion có trường `signature` chưa là bằng chứng được chấp nhận nếu server chưa kiểm tra đầy đủ.

OWASP khuyến nghị yêu cầu xác thực lại đối với tính năng nhạy cảm để giảm nguy cơ người chiếm session hoặc có quyền sử dụng trình duyệt tạm thời thay đổi thông tin tài khoản. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

Mục tiêu không phải thu thập thêm thông tin cá nhân cho đủ nhiều. Mục tiêu là xác minh một phép chứng minh có liên hệ đáng tin cậy với tài khoản và yêu cầu đang xét.

### 1.2. Phân biệt xác thực với định danh con người

Xác thực thường chứng minh quyền kiểm soát một hoặc nhiều authenticator đã gắn với tài khoản. Xác minh danh tính ngoài đời là một bài toán khác, có thể tham gia quy trình recovery nếu dịch vụ có căn cứ định danh phù hợp.

Một lần dùng passkey không tự cho RP biết họ tên pháp lý của người đang cầm thiết bị. Một ảnh giấy tờ mới gửi cũng không tự chứng minh người gửi là chủ của một tài khoản trước đó chưa từng được gắn với giấy tờ ấy.

Nhân viên hỗ trợ xác nhận nhu cầu công việc, người quản lý phê duyệt ngoại lệ và verifier kiểm tra authenticator là các hoạt động khác nhau. Không ghi chung tất cả thành `MFA_VERIFIED`.

### 1.3. Bằng chứng xác thực không phải quyền hành động

Người dùng có thể tái xác thực hợp lệ nhưng không được tạo API key, tài khoản bị security hold hoặc action còn trong thời gian hạn chế sau recovery.

Do đó, một evidence record không nên có ý nghĩa “được phép làm mọi việc”. Nó mô tả một sự kiện đã được xác minh; policy quyết định sự kiện đó có đáp ứng điều kiện của action hiện tại hay không.

## 2. Các thuộc tính quyết định chất lượng bằng chứng

### 2.1. Không dùng điểm tổng để thay điều kiện bắt buộc

Một mô hình khái niệm:

~~~text
Bằng chứng được chấp nhận cho action =
    nguồn và kết quả xác minh đáng tin cậy
  AND đúng account/tenant
  AND đúng ceremony và context
  AND đủ mới, đúng mốc sự kiện
  AND đạt thuộc tính xác thực yêu cầu
  AND không replay hoặc dùng ngoài phạm vi
  AND credential/trạng thái liên quan vẫn được chấp nhận
~~~

Đây là phép hội các điều kiện. Nhiều tín hiệu thuận lợi không bù được một assertion sai challenge, một token sai audience hoặc một credential thuộc tài khoản khác.

### 2.2. Bảng thuộc tính cần giữ

| Thuộc tính | Câu hỏi phải trả lời | Ví dụ lỗi nếu bỏ qua |
| --- | --- | --- |
| Nguồn gốc và tính toàn vẹn | Ai xác minh, dựa trên giao thức và trust configuration nào? | Tin vào JSON `verified=true` do client gửi |
| Subject binding | Bằng chứng thuộc account, tenant và issuer nào? | Dùng xác thực của B để đổi MFA của A |
| Ceremony/context binding | Phản hồi thuộc yêu cầu nào và client context nào? | Phát lại assertion từ một ceremony cũ |
| Độ mới | Sự kiện xác thực thực sự diễn ra lúc nào? | Dùng thời điểm refresh token làm thời điểm MFA |
| Thuộc tính bảo đảm | Có những yếu tố và khả năng chống tấn công nào đã được kiểm tra? | Coi mọi mã sáu số là tương đương passkey |
| Chống replay | Output hoặc quyền được cấp có thể bị dùng lại thế nào? | Hai request đồng thời cùng chấp nhận một OTP |
| Trạng thái hiện hành | Credential, epoch, policy và hold có thay đổi không? | Dùng bằng chứng từ trước khi credential bị thu hồi |
| Nguồn cấp credential | Authenticator đã được gắn vào account bằng quy trình nào? | Tự tạo factor mới rồi dùng nó để che lỗi recovery ban đầu |

Một bằng chứng có thể mạnh về một thuộc tính nhưng thiếu thuộc tính khác. Ví dụ, chữ ký mật mã hợp lệ chưa đủ nếu signer không thuộc tài khoản đích hoặc context không đáp ứng yêu cầu.

### 2.3. Unknown không phải true

Nếu IdP không trả một thuộc tính cần thiết, hoặc verifier không có cách xác định nó, hãy giữ trạng thái chưa biết. Không tự điền `phishingResistant=true` vì token có chữ `mfa`, và không suy ra sinh trắc học chỉ vì giao diện hiển thị biểu tượng vân tay.

Với hành động bắt buộc thuộc tính đó, dữ kiện chưa biết có thể dẫn tới yêu cầu bằng chứng khác hoặc chưa cho thực hiện. Không cần khóa mọi chức năng ít nhạy cảm chỉ vì một action chưa đủ bằng chứng.

## 3. Từng loại phương thức thực sự cung cấp gì?

### 3.1. Mật khẩu được kiểm tra lại

Mật khẩu đúng, được verifier hiện hành kiểm tra cho đúng tài khoản, chứng minh người gửi biết bí mật được chấp nhận tại thời điểm đó. Nó không tự chứng minh quyền kiểm soát thiết bị, yếu tố thứ hai hoặc khả năng chống phishing.

Nếu mật khẩu vừa được đặt lại, cần giữ thông tin về sự kiện thay đổi và context recovery liên quan. Tái nhập mật khẩu mới không tự xóa các giới hạn sau recovery.

Server không lưu bản sao mật khẩu vào evidence record. Kết quả cần lưu là sự kiện xác minh, credential version và các thuộc tính được chấp nhận, không phải dữ liệu để đăng nhập thay người dùng.

### 3.2. TOTP và các OTP

Một OTP được kiểm tra đúng chứng minh phép chứng minh tương ứng với phương thức đã triển khai. Với TOTP, verifier cần xét credential, cửa sổ thời gian và chống dùng lại; mã đúng không tự chứng minh đó là thiết bị vật lý ban đầu.

NIST yêu cầu một OTP chỉ được chấp nhận một lần trong thời gian còn hiệu lực. Đồng thời, OTP nhập thủ công không được xem là chống phishing vì output không tự gắn với đúng session của verifier. [NIST SP 800-63B-4 — Authenticator and Verifier Requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/)

Trong ứng dụng, chống replay phải xử lý cả request đồng thời và nhiều node verifier. Kiểm tra “mã đúng” rồi ghi trạng thái đã dùng ở một thao tác rời rạc có thể để hai request cùng vượt qua.

Việc gắn OTP vào một form recovery ở server hữu ích cho điều phối, nhưng không tự biến TOTP thành giao thức chống relay hoặc bằng chứng được ký trên nội dung action.

### 3.3. Mã gửi qua SMS/email và push

Mã được gửi tới một kênh rồi nhập đúng chứng minh khả năng tiếp cận kênh theo những giả định của cơ chế đó. Nó không tự chứng minh danh tính ngoài đời, quyền kiểm soát thiết bị cũ hoặc tính độc lập với các bằng chứng khác.

Email dùng cho recovery, xác minh địa chỉ và xác thực thông thường không nên bị trộn thành một loại bằng chứng có cùng mức bảo đảm. Chính sách phải định nghĩa đúng vai trò của từng cơ chế, kể cả các giới hạn của chuẩn đang áp dụng.

Với push, kết quả cần gắn với giao dịch xác thực cụ thể và account đích. Một thông báo “đã bấm chấp nhận” thiếu context đáng tin cậy không đủ để mở mọi hành động.

Không coi number matching, màn hình xác nhận hoặc việc có hai thiết bị là bảo đảm chống phishing trong mọi triển khai. Cần đánh giá giao thức và thuộc tính thực sự được verifier xác nhận.

### 3.4. Passkey/WebAuthn assertion

WebAuthn cung cấp assertion để chứng minh quyền kiểm soát credential key. RP phải kiểm tra bằng thư viện phù hợp: account/credential, challenge, origin, RP ID, chữ ký và các cờ cần thiết. UP và UV có ý nghĩa khác nhau; user presence không thay user verification. [W3C WebAuthn Level 3 — Verifying an Authentication Assertion](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion)

Khi tạo evidence record, ghi thuộc tính đã kiểm tra thay vì ghi “người dùng đã quét vân tay”. RP thường không biết chính xác thao tác mở khóa cục bộ và không nhận mẫu sinh trắc học.

Một passkey được đồng bộ không chứng minh duy nhất một thiết bị vật lý. Các cờ sao lưu hay nhãn thiết bị không phải bằng chứng độc lập về danh tính hoặc lịch sử recovery của tài khoản nền tảng.

Chữ ký hợp lệ cũng không tự chứng minh người dùng đã đọc và chấp thuận một nội dung nghiệp vụ cụ thể. Nếu cần binding theo action, ứng dụng phải quản lý context và nội dung đúng cách.

### 3.5. Recovery code hoặc authenticator dự phòng

Một authenticator dự phòng đã được đăng ký có thể đáp ứng đường tái xác thực bình thường nếu đạt policy. Recovery code có thể thuộc một quy trình phục hồi với tiêu chí riêng.

NIST phân biệt các phương thức account recovery và yêu cầu phục hồi theo mức bảo đảm, thay vì coi mọi code dự phòng là quyền đăng nhập đầy đủ. [NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/)

Không mặc nhiên hạ mọi cơ chế dự phòng thành “không phải MFA”, cũng không mặc nhiên nâng mọi recovery code thành “MFA đủ cho quản trị”. Cần biết code được cấp ra sao, xác minh thế nào, có dùng một lần không, kết hợp với bằng chứng gì và được dùng cho mục đích nào.

### 3.6. Session, cookie và chứng minh thiết bị

Một session secret hợp lệ duy trì context đã được cấp trước đó. Nó không tự là sự kiện xác thực mới bằng authenticator gốc. Refresh token được dùng thành công cũng không tự tạo bằng chứng MFA mới.

IP, browser fingerprint và cookie “thiết bị quen thuộc” là tín hiệu bối cảnh. Chứng minh kiểm soát một khóa thiết bị qua giao thức phù hợp có thể mạnh hơn, nhưng vẫn cần xác định khóa được gắn với ai và profile nào chấp nhận nó.

Không dùng khả năng kiểm soát một khóa client mới tạo để tự kết luận người dùng là chủ account. Việc sở hữu khóa và việc khóa được gắn đúng tài khoản là hai điều kiện khác nhau.
