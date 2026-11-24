# Email address change reversal — Đảo ngược thay đổi địa chỉ email

Trong chương **Email Address Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **email address change reversal** là quy trình xử lý một thay đổi email đã xảy ra nhưng bị chủ tài khoản phản đối hoặc cần hoàn tác. Mục tiêu là đưa kênh liên hệ về trạng thái được phép, đồng thời ngăn người đã thực hiện thay đổi trái phép tiếp tục kiểm soát tài khoản.

Email có thể là địa chỉ thông báo, định danh đăng nhập và kênh nhận token khôi phục mật khẩu. Bởi vậy, đảo email không chỉ là sửa lại một chuỗi trong hồ sơ. Nếu session, token reset hoặc phương tiện xác thực do kẻ tấn công tạo vẫn còn dùng được, hệ thống chưa khôi phục quyền kiểm soát an toàn.

Bài học xây dựng một thiết kế tham khảo cho ứng dụng quản lý email chính của tài khoản trong một tenant. Các cửa sổ thời gian, mức bằng chứng và cách giới hạn tài khoản là quyết định chính sách của sản phẩm; chúng không phải cấu hình bắt buộc cho mọi hệ thống. Với tài khoản do IdP hoặc danh bạ tổ chức quản lý, cần thực hiện thay đổi tại đúng nguồn có thẩm quyền.

## 1. Phân biệt hủy yêu cầu, đảo thay đổi và khắc phục chiếm đoạt

Giả sử tài khoản có email chính `an@example.com`, sau đó yêu cầu đổi sang `new@example.net`.

| Thao tác | Trạng thái đầu vào | Kết quả trực tiếp |
|---|---|---|
| Hủy yêu cầu đổi email | Email mới còn chờ xác nhận hoặc chờ áp dụng | Đóng yêu cầu; email chính chưa đổi |
| Đảo ngược thay đổi email | Email mới đã trở thành email chính | Tạo một thay đổi bù có kiểm soát để đưa email chính về địa chỉ lịch sử được phép |
| Khắc phục tài khoản bị chiếm đoạt | Có dấu hiệu session hoặc thông tin xác thực bị xâm phạm | Cô lập quyền truy cập, xử lý credential và kiểm tra các thay đổi liên quan |
| Sửa email nhập nhầm | Người dùng hợp lệ chủ động sửa thông tin | Thực hiện quy trình đổi email phù hợp, không mặc nhiên dùng quyền xử lý sự cố |

Hủy yêu cầu đang chờ không cần “khôi phục” email cũ vì nó vẫn là email chính. Ngược lại, khi thay đổi đã áp dụng, các email reset, session và quyết định phân quyền có thể đã dựa trên email mới.

Không triển khai một endpoint kiểu:

~~~http
POST /account/restore-email

{
  "accountId": "tài khoản bất kỳ",
  "oldEmail": "địa chỉ do người gọi lựa chọn"
}
~~~

Server phải suy ra tài khoản và email đích từ lịch sử thay đổi đáng tin cậy. Người gọi không được tự chọn một địa chỉ mới rồi yêu cầu coi đó là “email cũ”.

Một lần đảo thành công tạo ra **phiên bản mới**, không quay số phiên bản về quá khứ:

~~~text
revision 17: an@example.com
revision 18: new@example.net        -- thay đổi bị phản đối
revision 19: an@example.com         -- thay đổi bù sau xác minh
~~~

Lịch sử ở revision 18 vẫn được giữ theo chính sách lưu dữ liệu. Các token gắn với revision 17 hoặc 18 không tự sống lại chỉ vì chuỗi email ở revision 19 giống revision 17.

## 2. Mô hình đe dọa và những điều không thể suy ra từ email cũ

### 2.1. Các tình huống cần dự kiến

- Kẻ tấn công lấy được session rồi đổi email sang hộp thư của chúng.
- Kẻ tấn công reset mật khẩu qua email mới trước khi chủ tài khoản đọc cảnh báo.
- Người dùng đã đổi email hợp lệ vì hộp thư cũ bị chiếm; kẻ đang giữ hộp thư cũ bấm liên kết đảo.
- Địa chỉ công ty cũ hoặc tên miền hết hạn được cấp cho người khác.
- Một liên kết báo sự cố bị chuyển tiếp, xuất hiện trong log hoặc bị phần mềm kiểm tra email mở.
- Kẻ tấn công đổi email liên tiếp để làm liên kết cảnh báo đầu tiên không còn trỏ đến thay đổi hiện hành.
- Nhân viên hỗ trợ bị thuyết phục đổi email nhưng không xác minh đủ quyền.
- Hai request xác nhận, đảo hoặc reset mật khẩu chạy đồng thời trên các instance khác nhau.

Việc nhận được thư ở email cũ chứng minh quyền truy cập hộp thư tại thời điểm đó trong phạm vi giới hạn. Nó không tự chứng minh người nhận là chủ tài khoản, cũng không chứng minh hộp thư chưa bị chiếm quyền.

### 2.2. Tách quyền phản đối khỏi quyền khôi phục

Nên định nghĩa các quyền nghiệp vụ riêng:

~~~text
REPORT_EMAIL_CHANGE:
  Báo một thay đổi cụ thể là đáng ngờ.

CANCEL_PENDING_EMAIL_CHANGE:
  Hủy một yêu cầu chưa áp dụng theo chính sách.

REVERSE_EMAIL_CHANGE:
  Đưa email chính về đúng địa chỉ lịch sử đã được xác minh lại.

SECURE_COMPROMISED_ACCOUNT:
  Xử lý session, mật khẩu, MFA, passkey và các quyền truy cập liên quan.
~~~

Một token báo sự cố không mặc nhiên mang cả bốn quyền. Trong thiết kế tham khảo, liên kết gửi tới email cũ cho phép mở quy trình phản đối có giới hạn; đảo email cần thêm bằng chứng phù hợp với rủi ro.

Sản phẩm có thể cho phép token báo sự cố đã được xác minh kích hoạt một giới hạn an toàn, chẳng hạn tạm chặn đổi phương tiện khôi phục. Đây vẫn là quyền có thể bị lạm dụng để gây gián đoạn. Cần giới hạn phạm vi, chống lặp và có đường giải quyết bằng bằng chứng đủ mạnh.

Không khóa tài khoản chỉ vì một người nhập email vào biểu mẫu “tôi bị đổi email”. Một báo cáo công khai chưa có bằng chứng không được tạo ra quyền vô hiệu hóa tài khoản của người khác.

## 3. Thiết kế luồng đổi email trước khi cần đảo

Khả năng đảo phụ thuộc vào dữ liệu đã ghi ngay từ lần đổi ban đầu. Nếu hệ thống chỉ lưu email hiện tại, việc biết chính xác cần đảo sự kiện nào sẽ khó hơn.

Một luồng đổi email nên xác định rõ:

1. Ai được yêu cầu đổi, có cần xác thực lại và dùng phương tiện nào.
2. Email mới được lưu ở trạng thái chờ, chưa tự trở thành kênh recovery.
3. Cách xác nhận quyền kiểm soát email mới.
4. Thông báo tới email hiện tại và những kênh độc lập đã thiết lập, nếu có.
5. Điều kiện áp dụng, thời gian chờ và chính sách đối với tài khoản rủi ro cao.
6. Dữ liệu lịch sử, phiên bản và quyền báo thay đổi bất thường.

OWASP trình bày quy trình thay email với xác thực lại, địa chỉ mới ở trạng thái chờ và các thông báo hoặc xác nhận tùy trường hợp có MFA. Đây là nền tảng để thiết kế đường xử lý thay đổi trái phép, không phải quy định rằng mọi thư cảnh báo phải có quyền tự động đảo email. [OWASP Authentication — Changing a User’s Registered Email Address](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#changing-a-users-registered-email-address).

Email cũ có thể được giữ làm dữ liệu lịch sử hoặc đích nhận cảnh báo trong một thời gian hữu hạn. Điều này **không đồng nghĩa** nó tiếp tục là email đăng nhập hoặc địa chỉ nhận reset mật khẩu. Các vai trò phải được biểu diễn riêng.

Nếu email cũng là username, cần đồng bộ việc đổi định danh đăng nhập theo chính sách. Không giữ một alias đăng nhập hoặc alias reset ở email cũ chỉ vì backend cần lưu nó để điều tra.

## 4. Trạng thái thay đổi và trạng thái xử lý sự cố

### 4.1. Vòng đời của thay đổi email

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Yêu cầu đổi
    PENDING --> CANCELLED: Hủy trước áp dụng
    PENDING --> EXPIRED: Hết hạn xác nhận
    PENDING --> APPLIED: Đủ điều kiện và commit
    APPLIED --> REVERSED: Thay đổi bù được commit
    APPLIED --> SUPERSEDED: Có thay đổi tiếp theo
    APPLIED --> CLOSED: Đóng cửa sổ đảo tự động
    CANCELLED --> [*]
    EXPIRED --> [*]
    REVERSED --> [*]
    SUPERSEDED --> [*]
    CLOSED --> [*]
~~~

`CLOSED` chỉ nói rằng không còn áp dụng cơ chế đảo tự phục vụ cho sự kiện đó. Nó không khẳng định thay đổi ban đầu là hợp lệ và không ngăn việc tiếp nhận báo cáo sự cố.

Không đưa một bản ghi `REVERSED` trở lại `APPLIED` để “thử lại”. Nếu cần thay email lần nữa, tạo sự kiện mới với quyền và xác minh mới.

### 4.2. Hồ sơ sự cố là một thực thể khác

Một hồ sơ có thể ở các trạng thái:

~~~text
REPORTED -> AWAITING_EVIDENCE -> READY_FOR_REVERSAL
READY_FOR_REVERSAL -> REVERSED_ACCESS_RESTRICTED -> RESOLVED

REPORTED hoặc AWAITING_EVIDENCE -> REJECTED / MANUAL_REVIEW
~~~

Một thay đổi đã bị thay thế bởi thay đổi khác có thể không còn đủ điều kiện đảo trực tiếp, nhưng báo cáo về nó vẫn có giá trị điều tra.

Ví dụ:

~~~text
A -> B -> C

Liên kết cảnh báo cho A -> B không được âm thầm đổi C về A.
Nhưng B -> C cũng không được tự xóa dấu hiệu bất thường của A -> B.
~~~

Trong thiết kế đơn giản, chỉ sự kiện hiện hành được đảo tự động. Báo cáo có bằng chứng về sự kiện trước được đưa vào hồ sơ để xét chuỗi thay đổi và cân nhắc giới hạn an toàn. Nếu muốn đảo cả chuỗi, phải định nghĩa riêng điểm khôi phục, quyền và tập thay đổi được phép bù; không suy ra từ một token cũ.

## 5. Dữ liệu cần giữ và các bất biến

### 5.1. Mô hình dữ liệu tham khảo

| Thực thể | Dữ liệu chính | Ý nghĩa |
|---|---|---|
| `account_security` | `account_id`, `tenant_id`, `security_epoch`, `recovery_version`, `recovery_state` | Nguồn có thẩm quyền về quyền truy cập và trạng thái recovery |
| `primary_email` | `account_id`, `binding_id`, email, `revision`, trạng thái xác minh | Email chính hiện tại |
| `email_change` | `change_id`, tài khoản, tenant, binding trước/sau, email trước/sau, revision trước/sau, thời điểm, trạng thái | Lịch sử chính xác của một thay đổi |
| `email_change_report_token` | digest token, `change_id`, purpose, audience, hạn dùng, trạng thái | Quyền phản đối một sự kiện cụ thể |
| `email_reversal_grant` | digest, change, account, tenant, expected revision/epoch, context, hạn dùng, lần dùng | Quyền đảo đã giới hạn và đã đủ điều kiện cấp |
| `recovery_evidence` | loại bằng chứng, phạm vi, thời điểm, phiên bản chính sách, trạng thái dùng | Kết quả xác minh ở phía server |
| `security_incident` | tài khoản, sự kiện gốc, trạng thái, giới hạn đang áp dụng | Điều phối quá trình xử lý sự cố |
| `security_event`, `notification_outbox` | ID sự kiện, phiên bản, payload tối thiểu | Audit và chuyển giao thông báo sau commit |

Các bảng chỉ mô tả trách nhiệm dữ liệu, không phải schema SQL đầy đủ. Cần khóa ngoại, kiểm tra tenant, ràng buộc duy nhất và chính sách truy cập tương ứng.

Email lịch sử là dữ liệu cá nhân. Chỉ giữ trong khoảng thời gian có mục đích, giới hạn người xem và mã hóa khi phù hợp với mô hình đe dọa. Audit dùng tham chiếu nội bộ thay vì sao chép mọi địa chỉ vào log.

### 5.2. Các bất biến quan trọng

- Token và grant luôn gắn với `account_id` bất biến, tenant, sự kiện và purpose.
- Địa chỉ cần khôi phục được lấy từ lịch sử có thẩm quyền.
- Mỗi thay đổi chỉ có tối đa một kết quả đảo đã commit.
- Thay đổi bù làm revision và các phiên bản an ninh tăng lên.
- Không cấp session đăng nhập đầy đủ chỉ vì một liên kết phản đối hợp lệ.
- Email hoặc credential đã bị thu hồi không được khôi phục quyền bởi việc đọc lịch sử.
- Tác dụng của một token chỉ xuất hiện sau khi kiểm tra trạng thái hiện tại trong giao dịch.
- Hệ thống không báo hoàn tất bảo vệ tài khoản khi còn đường truy cập chưa được xử lý theo chính sách.

Nếu sản phẩm yêu cầu email duy nhất trong tenant, phải có ràng buộc thực thi ở kho dữ liệu. Kiểm tra “email còn trống” trước transaction không đủ ngăn một tài khoản khác nhận địa chỉ đó ngay sau kiểm tra.

Quy tắc chuẩn hóa email phải nhất quán với đăng ký và đăng nhập. Không tự bỏ `+tag` hoặc dấu chấm theo giả định mọi nhà cung cấp có cùng cách xử lý.

## 6. Token báo sự cố, grant đảo và trang xác nhận

### 6.1. Ràng buộc và thời hạn

Một token opaque có thể được sinh từ 32 byte ngẫu nhiên mật mã. Đây là lựa chọn minh họa có không gian đủ lớn; không dùng `change_id`, timestamp hoặc email đã mã hóa Base64 làm bí mật.

Với token có entropy cao, có thể lưu digest có domain separation:

~~~text
digest = SHA-256(encode_with_lengths(
  "email-change-report/v1",
  token_secret
))
~~~

Token ngắn như OTP có mô hình chống đoán và lưu verifier khác; không áp dụng máy móc cách lưu token dài cho mã vài chữ số.

Bản ghi server xác định:

~~~text
purpose = REPORT_EMAIL_CHANGE
audience = account-recovery
account_id, tenant_id, change_id
issued_at, expires_at
consumed_at hoặc revoked_at
policy_version
~~~

Grant `REVERSE_EMAIL_CHANGE` là bí mật khác, được cấp sau bước xác minh đủ điều kiện và gắn thêm revision, epoch, bằng chứng cùng context của quy trình. Không tái sử dụng nonce xác nhận email mới làm grant đảo.

OWASP khuyến nghị token recovery được sinh ngẫu nhiên mật mã, đủ dài, lưu an toàn, hết hạn và vô hiệu sau khi dùng. Bài này áp dụng các thuộc tính đó cho token xử lý thay đổi email; quyền nghiệp vụ của từng token do thiết kế ở đây xác định. [OWASP Forgot Password — General Security Practices](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Cửa sổ báo sự cố, thời hạn grant và thời gian chờ đổi email là ba khái niệm khác nhau. Ví dụ, sản phẩm có thể cho báo sự cố trong 24 giờ nhưng grant thực thi chỉ sống 5 phút sau xác minh. Các con số là ví dụ, không phải tiêu chuẩn.

Resend không được tự kéo dài cửa sổ báo sự cố vô hạn. Khi thay token, quản lý generation và vô hiệu bản cũ theo hợp đồng đã công bố.

### 6.2. Không thay đổi trạng thái tài khoản bằng GET

Email scanner, trình xem trước và bộ chống phishing có thể mở liên kết. Do đó:

~~~http
GET /recovery/email-change?token=<bí mật>
~~~

chỉ phục vụ trang hướng dẫn tối thiểu. Nó không tự đảo email, thu hồi session, tiêu thụ token hoặc ghi nhận quyết định “không phải tôi”.

Người dùng phải thực hiện hành động chủ đích trên trang và, nếu chính sách yêu cầu, hoàn tất xác minh độc lập. Khi dùng cookie context, áp dụng chống CSRF, kiểm tra origin phù hợp và bảo vệ việc đóng khung trang. Việc chuyển sang POST không tự chứng minh người thao tác là chủ tài khoản.

Một token báo sự cố có thể được đổi nguyên tử thành hồ sơ/context có giới hạn sau POST hợp lệ. Token chỉ bị tiêu thụ khi tác dụng được cho phép của nó đã commit. Nếu tác dụng là mở hồ sơ, nó không được diễn giải thành bằng chứng đã đủ để đảo email.

Context này chỉ cho phép tiếp tục recovery, không được đọc toàn bộ hồ sơ, thực hiện giao dịch hoặc bỏ qua MFA.

### 6.3. Bảo vệ bí mật trong liên kết

Dùng HTTPS và origin cấu hình tin cậy để dựng liên kết. Không lấy trực tiếp header `Host` do client kiểm soát hoặc `returnUrl` tùy ý để làm nơi nhận token. OWASP nêu rủi ro dựng URL reset từ Host header và khuyến nghị giới hạn đích tin cậy. [OWASP Forgot Password — URL Tokens](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#url-tokens).

Trang chứa bí mật nên có:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Tránh analytics, session replay và script bên thứ ba trên trang recovery. Che token ở access log, reverse proxy, APM và trace ngay từ điểm nhận; header của trang không xóa được một token đã bị ghi vào log trước đó.

Có thể chuyển sang URL sạch sau bước xử lý thích hợp. Việc đổi URL không thay thế quyền dùng một lần, ràng buộc context hoặc kiểm soát log.

## 7. Chọn bằng chứng để đảo email

### 7.1. Bằng chứng phải phù hợp với sự kiện bị phản đối

| Bằng chứng hoặc tín hiệu | Có thể hỗ trợ | Giới hạn |
|---|---|---|
| Token cảnh báo gửi email cũ | Quyền truy cập thông báo gắn với một thay đổi | Hộp thư có thể bị chiếm hoặc được cấp lại |
| Challenge mới gửi đúng email lịch sử | Quyền kiểm soát địa chỉ cần khôi phục lúc này | Không tự chứng minh quyền sở hữu tài khoản |
| Passkey hoặc MFA đã đăng ký trước sự kiện | Bằng chứng độc lập nếu phương tiện còn đáng tin | Phải kiểm tra nguồn gốc, tình trạng thu hồi và chính sách |
| Mật khẩu hiện tại | Một phần xác minh khi phù hợp | Có thể do kẻ tấn công vừa đặt lại hoặc đã biết |
| Thiết bị hoặc IP quen thuộc | Tín hiệu đánh giá rủi ro | Không thay thế phương tiện xác thực |
| Nhân viên hỗ trợ xác minh qua quy trình được duyệt | Đường xử lý khi mất phương tiện | Phải có bằng chứng, phạm vi và audit; không dựa riêng lời kể |

Thiết kế minh họa cho đảo tự phục vụ yêu cầu cả kiểm soát email lịch sử hiện tại và một bằng chứng độc lập đủ mạnh đã được thiết lập trước sự kiện bị phản đối. Đây là lựa chọn thận trọng của ví dụ; sản phẩm phải xác định tổ hợp cụ thể cho từng mức rủi ro.

Một passkey được thêm từ session đáng ngờ sau khi đổi email không tự trở thành bằng chứng tin cậy để xử lý chính sự cố đó. Cần biết thời điểm, nguồn đăng ký và chuỗi sự kiện liên quan, không chỉ hỏi “tài khoản hiện có passkey hay không”.

Bằng chứng xác thực lại cần gắn với tài khoản, tenant, mục đích đảo, sự kiện và context. Không dùng cờ chung `verified=true` từ một thao tác không liên quan.

### 7.2. Không tạo vòng lặp buộc dùng email mới

Nếu kẻ tấn công đã thay email và mật khẩu, việc bắt chủ tài khoản đăng nhập qua email mới để báo sự cố có thể chặn hoàn toàn đường khôi phục.

Cần một context recovery riêng, cho phép kiểm tra các bằng chứng đã thiết lập từ trước mà không cấp quyền đăng nhập thông thường. Nếu người dùng mất cả MFA, passkey hoặc thiết bị, chuyển sang quy trình recovery có mức bảo đảm phù hợp; liên kết đảo email không được tự xóa các yêu cầu đó.

Không thay yêu cầu xác minh bằng câu hỏi tên thật, ngày sinh hoặc nội dung công khai. Những thông tin này có thể giúp định vị hồ sơ cho hỗ trợ, nhưng không tự cấp quyền thay kênh recovery.

### 7.3. Email cũ không còn an toàn

Khi người dùng cho biết hộp thư cũ đã bị chiếm, không gửi grant đảo hoặc token reset vào đó chỉ vì nó xuất hiện trong lịch sử.

Có thể phải bỏ phương án đảo về email cũ, xử lý sự cố bằng bằng chứng độc lập rồi thực hiện một thay đổi email mới được xác minh. Ghi rõ đây là quyết định khác với đảo tự phục vụ; không sửa dữ liệu lịch sử để biến địa chỉ mới do người gọi nhập thành “email trước đây”.

## 8. Thực thi thay đổi bù trong một giao dịch

### 8.1. Những điều phải kiểm tra lại lúc commit

Một lần xác minh ở đầu luồng không đủ cho thao tác diễn ra vài phút sau. Khi thực thi, backend phải kiểm tra lại:

1. Grant đúng purpose, audience, tenant, tài khoản và sự kiện.
2. Grant còn hạn, chưa dùng, chưa thu hồi và đúng context.
3. Bằng chứng được cấp bởi hệ thống có thẩm quyền, còn hiệu lực và đúng phạm vi.
4. Chính sách tài khoản hiện cho phép đảo theo đường này.
5. Thay đổi cần đảo đã áp dụng và vẫn là sự kiện được phép đảo trực tiếp.
6. Email hiện tại, binding và revision khớp kết quả của sự kiện đó.
7. Email lịch sử còn được phép sử dụng và không bị tài khoản khác chiếm dụng.
8. Epoch hoặc phiên bản recovery chưa thay đổi theo cách làm grant mất hiệu lực.

Các kiểm tra phải đọc dữ liệu có thẩm quyền. Một bản sao cache chưa nhận sự kiện đổi email không đủ làm căn cứ cấp quyền.

Nếu trạng thái đã khác, không sửa lệnh thành “đưa bất kỳ email hiện tại nào về email trong token”. Trả kết quả phù hợp và chuyển sang xem xét chuỗi sự kiện khi cần.

### 8.2. Thứ tự khóa và ràng buộc

Một thứ tự minh họa cho dữ liệu của một tài khoản:

~~~text
account_security
  -> primary_email
  -> email_change
  -> reversal_grant
  -> recovery_evidence
~~~

Các đường đổi email, reset mật khẩu, thay credential và thu hồi recovery phải phối hợp bằng khóa hoặc kiểm tra phiên bản tương thích. Việc chỉ khóa hàng grant không bảo vệ được tài khoản khỏi một cập nhật email song song.

Nếu phải giữ hoặc nhận lại một email có ràng buộc duy nhất, các thao tác trên bảng quyền sở hữu địa chỉ cũng cần thứ tự khóa nhất quán, chẳng hạn theo khóa địa chỉ đã chuẩn hóa. Unique constraint vẫn là hàng rào cuối cùng; xử lý deadlock hoặc xung đột bằng retry có giới hạn và không trả thành công trước commit.

Một `synchronized` trong Java chỉ bảo vệ các thread cùng JVM. Nó không thay thế giao dịch và ràng buộc ở kho dữ liệu khi có nhiều instance.

### 8.3. Mã giả ở tầng nghiệp vụ

Ví dụ sau thể hiện ranh giới giao dịch. Các repository và policy là thành phần giả định, không phải API thư viện hay chương trình có thể chạy nguyên trạng:

~~~java
ReversalResult reverse(ReversalCommand command) {
    inputLimits.check(command);
    recoveryLimiter.check(command.publicContext());

    // Chỉ lấy khóa định tuyến từ bản ghi server.
    // Không coi snapshot này là quyết định cấp quyền.
    GrantRoute route = grants.findRouteBySecret(command.grantSecret());

    ReversalResult result = transactions.execute(tx -> {
        LockedReversalState state = store.lockInOrder(tx, route);

        // Kiểm tra lại secret, purpose, audience và context dưới khóa.
        grantPolicy.requireMatchingRequest(state, command);

        // Retry sau commit chỉ đọc receipt an toàn, không đảo lần nữa.
        if (state.hasCommittedReceipt()) {
            return receipts.safeResultForSameContext(state, command);
        }

        // Đọc thời gian sau khi đã chờ khóa.
        Instant now = tx.currentWallClockTime();

        grantPolicy.requireUnusedAndUnexpired(state, now);
        evidencePolicy.requireEligibleEvidence(state, now);
        reversalPolicy.requireCurrentChangeAndRevisions(state);
        reversalPolicy.requireAllowedHistoricalAddress(state);

        // Xung đột địa chỉ phải làm rollback toàn bộ thay đổi bên dưới.
        emailClaims.acquireForAccount(
                tx, state.accountId(), state.historicalEmail());

        PrimaryEmailBinding restored = emailBindings.restoreAsNewBinding(
                tx, state.accountId(), state.historicalEmail(),
                state.freshAddressControlEvidence());

        security.bumpEpochAndRecoveryVersion(tx, state.accountId());
        changes.markReversedAndAppendCompensation(tx, state, restored);
        credentials.applyIncidentRestrictions(tx, state);
        incidents.keepAccessRestrictedUntilSecured(tx, state.accountId());

        grants.markUsed(tx, state.grantId(), now);
        evidence.consumeForOperation(tx, state.evidenceIds());
        receipts.recordCommittedOutcome(tx, state, restored);
        audit.appendEmailReversal(tx, state, restored);
        outbox.enqueueSecurityNotifications(tx, state, restored);

        return ReversalResult.reversedAccessRestricted();
    });

    // execute chỉ trả kết quả thành công khi commit đã thành công.
    return result;
}
~~~

`grantPolicy.requireMatchingRequest` không được chỉ kiểm tra một ID ngẫu nhiên; nó còn phải xác minh bí mật và mọi ràng buộc. Đường xử lý không tìm thấy route phải có giới hạn đầu vào và phản hồi không làm lộ tài khoản.

Nhánh receipt không bỏ qua xác minh người nhận. Receipt không chứa token mới hoặc khôi phục lại quyền đã tiêu thụ. Nếu context đã hết hạn hoặc bị thu hồi, không được dùng idempotency để truy cập kết quả trái chính sách.

`restoreAsNewBinding` tạo binding và revision mới. Trong ví dụ này, trạng thái xác minh địa chỉ dựa trên bằng chứng kiểm soát địa chỉ vừa thu thập, không phải chỉ sao chép `verified_at` từ nhiều năm trước.

`applyIncidentRestrictions` cần có hành vi thực tế đối với credential và đường truy cập của sản phẩm. Một tên hàm trong mã giả không chứng minh rằng API key, session hoặc liên kết IdP đã được xử lý.

Nếu bất kỳ bước nào thất bại, rollback cả email, grant, phiên bản và sự kiện trong transaction. Không gửi email, gọi nhà cung cấp bên ngoài hoặc trả một session đăng nhập trước khi biết commit thành công.

Một giới hạn an toàn đã được thiết lập trước đó bởi quy trình phản đối không nên biến mất chỉ vì transaction đảo gặp xung đột. Đó là trạng thái đã commit riêng, cần được giải quyết qua hồ sơ sự cố.

## 9. Đảo email phải đi cùng kiểm soát quyền truy cập

### 9.1. Epoch chỉ có tác dụng khi nơi nhận thực thi

Giả sử session được cấp với `security_epoch=41`. Khi đảo email, backend tăng epoch tài khoản lên 42:

~~~text
session.epoch = 41
account.security_epoch = 42

=> session cũ không còn đủ điều kiện được chấp nhận.
~~~

Điều này chỉ đúng nếu gateway hoặc dịch vụ thực sự đối chiếu epoch theo mức nhất quán cần thiết. Việc thêm trường vào database rồi phát sự kiện thu hồi bất đồng bộ không tự làm JWT đã cấp mất hiệu lực.

Cần xác định rõ với từng đường truy cập:

| Đường truy cập | Cách xử lý cần quyết định |
|---|---|
| Session server-side | Thu hồi hoặc kiểm tra phiên bản ở điểm chấp nhận request |
| Access token tự chứa | Introspection, kiểm tra epoch/denylist hoặc cơ chế giới hạn tương đương |
| Refresh token | Thu hồi token family liên quan; không cho sinh session mới từ quyền cũ |
| Remember-me hoặc trusted-device token | Thu hồi quyền bỏ qua xác minh đã không còn đáng tin |
| API key và personal access token | Xem có bị tạo hoặc lộ trong sự cố; áp dụng cơ chế thu hồi riêng nếu không dùng epoch |
| WebSocket hoặc kết nối dài | Kiểm tra lại quyền hoặc đóng kết nối theo cơ chế của hệ thống |
| Session tại IdP hoặc dịch vụ khác | Phối hợp với bên quản lý; sửa email cục bộ không tự thu hồi phiên bên ngoài |

Với thao tác nhạy cảm, nên chặn tại nguồn có thẩm quyền cho tới khi các thành phần liên quan thực thi được trạng thái mới. Nếu có cửa sổ chậm lan truyền, cần mô tả giới hạn đó; không tuyên bố “đăng xuất toàn bộ ngay lập tức” chỉ vì đã đưa sự kiện vào hàng đợi.

OWASP coi thay đổi email và recovery là những sự kiện có thể cần xác thực lại. Cách kiểm soát epoch trong bài là một lựa chọn kiến trúc để thực thi việc thu hồi, không phải cơ chế được tự động cung cấp bởi mọi framework. [OWASP Session Management — Reauthentication After Risk Events](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#reauthentication-after-risk-events).

### 9.2. Vô hiệu token khôi phục đã phát hành

Token reset mật khẩu, magic link, xác nhận email mới hoặc grant thay MFA có thể đã được cấp trong khoảng bị chiếm quyền.

Chúng phải mất hiệu lực theo phạm vi của sự cố, chẳng hạn bằng `recovery_version` tăng đơn điệu kết hợp trạng thái từng token. Không chỉ dừng gửi thư tới email mới trong tương lai; token đã nằm trong hộp thư đó vẫn là quyền đang tồn tại.

Ví dụ:

~~~text
T1: Token reset R được cấp với recovery_version=8.
T2: Đảo email commit, recovery_version tăng thành 9.
T3: R được gửi đến endpoint đặt mật khẩu.

Endpoint phải đối chiếu version hiện tại trước khi ghi mật khẩu.
R không được dùng chỉ vì chữ ký hợp lệ và chưa hết hạn.
~~~

Nếu request dùng R đã kiểm tra version trước T2 nhưng chờ đến sau T2 mới ghi, việc kiểm tra cũ không đủ. Điểm ghi credential phải khóa hoặc cập nhật có điều kiện cùng trạng thái an ninh để không vượt qua lần thu hồi vừa commit.

### 9.3. Mật khẩu, MFA và passkey không được “rollback” như dữ liệu hồ sơ

Đưa email về giá trị cũ không chứng minh mật khẩu hiện tại còn an toàn. Ngược lại, chép lại hash mật khẩu cũ có thể làm sống lại một bí mật đã lộ và tạo vấn đề đồng bộ khác.

Khi có dấu hiệu chiếm đoạt:

- Yêu cầu thiết lập lại mật khẩu qua context đã được xác minh nếu mật khẩu không còn đáng tin.
- Xem xét và vô hiệu phương tiện xác thực, recovery code hoặc thiết bị được thêm trong khoảng sự cố.
- Giữ yêu cầu chứng minh quyền sở hữu trước khi đăng ký phương tiện thay thế.
- Không khôi phục secret MFA cũ hoặc session cũ từ bản sao dữ liệu.
- Kiểm tra quyền liên kết IdP, ứng dụng được ủy quyền và thay đổi bảo mật liên quan.

Cần một sổ sự kiện credential đủ tin cậy để biết thứ gì được thêm hoặc đổi. Nếu không thể phân biệt chính xác, áp dụng trạng thái hạn chế và quy trình khắc phục phù hợp, thay vì đoán credential nào “có vẻ của chủ tài khoản”.

Không tự xóa mọi passkey hoặc MFA chỉ vì người dùng bấm liên kết báo sự cố. Một hành động đó có thể biến quyền phản đối yếu thành quyền phá bỏ lớp bảo vệ mạnh hơn.

## 10. Email cũ đã thuộc tài khoản khác hoặc không còn dùng được

### 10.1. Không cưỡng ép chuyển quyền sở hữu địa chỉ

Sau khi email cũ được giải phóng, nó có thể đã được đăng ký cho tài khoản khác theo chính sách sản phẩm. Khi đảo:

- Không xóa liên kết của tài khoản kia.
- Không gộp tài khoản dựa trên việc cùng địa chỉ.
- Không bỏ qua unique constraint bằng một cờ “recovery đặc biệt”.
- Không cho đăng nhập hoặc reset chạy trong trạng thái hai chủ sở hữu mơ hồ.

Đưa hồ sơ vào đường xử lý xung đột. Người yêu cầu không cần được biết địa chỉ đang thuộc về ai. Thông báo có thể là:

> Chưa thể hoàn tất khôi phục địa chỉ này. Hãy tiếp tục quy trình xác minh hoặc làm theo hướng dẫn hỗ trợ.

Có thể thiết kế thời gian giữ chỗ email cũ trong cửa sổ đảo để giảm xung đột. Giữ chỗ là một trạng thái có giới hạn và có thời hạn, không phải alias đăng nhập hay địa chỉ nhận reset còn hiệu lực.

### 10.2. Địa chỉ lịch sử không còn chứng minh được

Nếu hộp thư bị đóng, được cấp lại hoặc không thể xác minh quyền kiểm soát, đừng đánh dấu email đã khôi phục là `VERIFIED` chỉ dựa vào lịch sử.

Các phương án gồm xử lý thủ công bằng bằng chứng độc lập, chọn một kênh mới qua quy trình thích hợp hoặc tiếp tục hạn chế quyền nhạy cảm cho đến khi đủ điều kiện. Không phải mọi yêu cầu đều có thể hoàn tất bằng đảo tự phục vụ.

### 10.3. Email do tổ chức quản lý

Với SSO, SCIM hoặc danh bạ tổ chức, email cục bộ có thể chỉ là bản sao thuộc tính. Sửa bản sao sẽ bị lần đồng bộ sau ghi đè và có thể tạo sai lệch định danh.

Xác định nơi quyết định liên kết tài khoản. Không liên kết tài khoản IdP chỉ bằng chuỗi email giống nhau sau khi đảo. Giữ định danh ổn định của nhà cung cấp và quy trình account linking riêng.

Khôi phục liên hệ trong ứng dụng cũng không tạo quyền truy cập trở lại một hộp thư công ty đã bị thu hồi.

## 11. Thông báo, outbox và dữ liệu audit

### 11.1. Gửi thông báo đúng mục đích

Khi có thay đổi hoặc đảo thay đổi, thông báo nên nêu sự kiện, thời gian, cách báo bất thường và hành động tiếp theo. Chỉ gửi tới các đích được chính sách cho phép.

Email mới đang bị nghi là của kẻ tấn công có thể nhận thông báo tối thiểu về việc thay đổi bị thu hồi, nếu chính sách cần. Không gửi sang đó địa chỉ đầy đủ của chủ tài khoản, token tiếp tục recovery, bằng chứng hoặc liên kết đặt lại mật khẩu mới.

Email cũ cũng không luôn là đích an toàn. Kiểm tra trạng thái kênh trước khi gửi bí mật. Nếu không còn kênh độc lập đáng tin, ưu tiên quy trình xác minh thay vì cố gửi một thông báo mang quyền mạnh.

Bản thân email cảnh báo không nên yêu cầu người nhận trả lời bằng mật khẩu, OTP hoặc recovery code. Nếu người dùng nghi thư giả, họ cần có thể vào ứng dụng qua địa chỉ tin cậy để mở quy trình xử lý.

### 11.2. Outbox giữ việc gửi nhất quán với commit

Ghi sự kiện thông báo trong cùng transaction với thay đổi bù, sau đó worker gửi khi transaction đã commit.

Một sự kiện có thể gồm:

~~~json
{
  "eventId": "evt-email-reversed-example",
  "eventType": "EMAIL_CHANGE_REVERSED",
  "accountRef": "acct-internal-17",
  "tenantRef": "tenant-internal-03",
  "changeRef": "change-internal-81",
  "primaryEmailRevision": 19,
  "securityEpoch": 42,
  "incidentState": "REVERSED_ACCESS_RESTRICTED"
}
~~~

Các giá trị là minh họa. Không đưa token, OTP hoặc địa chỉ đầy đủ vào event audit dùng chung.

Nếu worker cần gửi một token rõ, digest trong database không thể tự khôi phục token đó. Cần cơ chế chuyển giao bí mật riêng, chẳng hạn payload mã hóa, quyền truy cập hẹp và TTL ngắn. Không biến event bus audit thành kho chứa token.

Worker phải chịu được retry và sự kiện trùng. Dùng ID sự kiện để hạn chế gửi lặp; dùng revision để một sự kiện cũ không cập nhật projection mới thành email trước đó. Email đã gửi không thể thu hồi chắc chắn, nên ngay cả thông báo đến muộn cũng không được chứa một quyền đã không còn được server chấp nhận.

### 11.3. Ghi nhận điều gì đã xảy ra

Phân biệt các sự kiện:

~~~text
EMAIL_CHANGE_REPORTED
EMAIL_REVERSAL_EVIDENCE_ACCEPTED
EMAIL_CHANGE_REVERSED
ACCOUNT_ACCESS_RESTRICTED
ACCOUNT_RESECURED
~~~

“Email đã được đảo” không đồng nghĩa “tài khoản đã an toàn” và không đồng nghĩa “người dùng đã nhận được phản hồi”.

Audit nên có actor hoặc loại bằng chứng, tham chiếu sự kiện, thời gian, kết quả và lý do nội bộ cần thiết. Không ghi token, cookie, verifier, ảnh giấy tờ hoặc toàn bộ request body vào log chung.

Nếu transaction rollback, không phát sự kiện khẳng định đã đảo thành công. Có thể ghi một sự kiện thất bại tách biệt với mức dữ liệu tối thiểu, sao cho người điều tra phân biệt được ý định và kết quả đã commit.

## 12. Retry, thất bại và thời gian ngừng dịch vụ

| Tình huống | Cách xử lý cần có |
|---|---|
| Grant sai, hết hạn hoặc bị thu hồi | Không thay dữ liệu; phản hồi không tiết lộ chi tiết tài khoản |
| Hai request dùng cùng grant | Tối đa một thay đổi bù; request còn lại đọc kết quả giới hạn hoặc bị từ chối theo hợp đồng |
| Đã commit nhưng response bị mất | Retry theo receipt/context; không đảo lại và không phát quyền mạnh mới |
| Xung đột quyền sở hữu email | Rollback thay đổi bù; duy trì hồ sơ và giới hạn đã được thiết lập hợp lệ |
| Kho bằng chứng hoặc trạng thái an ninh không khả dụng | Không bỏ qua xác minh; cho tiếp tục khi khôi phục dịch vụ hoặc chuyển hỗ trợ |
| Email cảnh báo gửi chậm | Không tự gia hạn token hoặc bỏ kiểm tra phiên bản |
| Outbox giao trùng | Không nhân đôi thay đổi; thông báo được xử lý có kiểm soát |
| Projection chưa nhận epoch mới | Hạn chế thao tác theo cơ chế có thẩm quyền; không dựa riêng vào cache cũ |
| Khôi phục database từ backup cũ | Đánh giá lại token, phiên bản và thu hồi bị mất trước khi mở lại luồng |

Idempotency key chỉ nhận diện một thao tác trong phạm vi đã xác minh. Nó không phải một bí mật thay thế cho grant hoặc context, và không cho phép thay body để đảo một sự kiện khác.

Không để receipt chứa “email hiện tại” rồi vô tình tiết lộ một thay đổi mới xảy ra sau lần đảo. Receipt mô tả kết quả đã commit của thao tác đó, với dữ liệu tối thiểu được phép trả ở thời điểm retry.

Không thể giải quyết mất lịch sử thu hồi chỉ bằng việc khởi động lại ứng dụng. Nếu restore đưa epoch hoặc trạng thái token lùi về trước, cần một hàng rào khôi phục đáng tin cậy, chẳng hạn vô hiệu nhóm quyền bị ảnh hưởng và yêu cầu xác minh lại.

## 13. Ví dụ xuyên suốt: email đã bị đổi và mật khẩu đã bị reset

An có email `an@example.com`, một passkey đăng ký từ trước và revision email 17.

1. Kẻ tấn công chiếm được một session và đổi email sang `intruder@example.net`. Thay đổi commit ở revision 18; hệ thống lưu sự kiện và phát cảnh báo theo chính sách.
2. Kẻ tấn công lấy token reset qua email mới và có thể đã đặt mật khẩu khác. An đọc thông báo ở email cũ.
3. An mở liên kết. GET chỉ hiện trang hướng dẫn, chưa đổi email hoặc khóa session.
4. An chủ đích báo “Tôi không thực hiện thay đổi này”. Token báo sự cố hợp lệ mở hồ sơ và có thể kích hoạt giới hạn an toàn đã định nghĩa.
5. An xác minh quyền kiểm soát email lịch sử và dùng passkey đã đăng ký trước sự kiện. Backend cấp grant đảo có thời hạn ngắn, gắn với change, revision 18 và context hiện tại.
6. Trong transaction, backend kiểm tra lại bằng chứng, trạng thái email và grant. Nếu email cũ còn hợp lệ và không xung đột, tạo binding mới cho `an@example.com` ở revision 19.
7. Cùng transaction, backend tăng các phiên bản an ninh, ghi grant đã dùng, tạo sự kiện bù và giữ tài khoản trong trạng thái hạn chế cho tới khi hoàn tất xử lý sự cố.
8. Token reset và quyền truy cập cũ bị từ chối tại các điểm thực thi đã thiết kế. Nếu mật khẩu đã bị kẻ tấn công thay hoặc không còn đáng tin, An đặt một mật khẩu mới qua context recovery đủ quyền.
9. An rà soát phương tiện xác thực và quyền truy cập được thêm trong thời gian sự cố. Chỉ khi đủ điều kiện, hệ thống mới kết thúc hạn chế và cấp session mới qua luồng xác thực thích hợp.

Nếu bước 6 phát hiện email hiện tại đã là revision 19 do một thay đổi khác, không dùng grant của revision 18 để ghi đè. Hồ sơ được chuyển sang xem xét chuỗi sự kiện.

Nếu passkey An dùng thực ra vừa được thêm bởi kẻ tấn công sau sự kiện, bằng chứng đó không thỏa chính sách của ví dụ. Nếu An mất cả passkey và MFA, cần đường recovery riêng; không tự hạ yêu cầu chỉ để kết thúc luồng nhanh hơn.

## 14. Các tình huống cần kiểm chứng khi triển khai

Bảng dưới là yêu cầu đối chiếu thiết kế, không phải kết quả kiểm thử đã chạy trên ứng dụng.

| Tình huống | Điều cần chứng minh |
|---|---|
| Hủy một yêu cầu `PENDING` | Không tạo thay đổi bù cho email chưa từng áp dụng |
| Liên kết bị email scanner mở | GET không đổi quyền, không thu hồi session và không tiêu thụ token |
| Token báo sự cố gửi tới endpoint đảo | Không được dùng thay grant `REVERSE_EMAIL_CHANGE` |
| Nonce xác nhận email mới được dùng để đảo | Bị từ chối do sai mục đích và phạm vi |
| Client sửa account ID, tenant hoặc email đích | Không thay được đối tượng lấy từ dữ liệu server |
| Email cũ bị chiếm hoặc cấp lại | Quyền kiểm soát hộp thư không tự đủ để chiếm lại tài khoản |
| Bằng chứng từ credential mới được thêm trong sự cố | Không tự được coi là yếu tố độc lập đáng tin |
| Hai instance dùng cùng grant | Tối đa một kết quả đảo đã commit |
| Đổi tiếp email cạnh tranh với đảo | Kiểm tra revision và khóa ngăn ghi đè không đúng sự kiện |
| Reset token kiểm tra trước nhưng ghi sau lần đảo | Không vượt qua recovery version đã thay đổi |
| Token đã cấp tới email mới | Mất quyền thực tế sau thu hồi, dù thư đã được giao |
| Email cũ thuộc tài khoản khác | Không gộp tài khoản hoặc cưỡng ép chuyển liên kết |
| Session, refresh token, API key và kết nối dài | Có kết quả thu hồi hoặc hạn chế cụ thể cho từng loại |
| Commit xong nhưng mất response | Retry không tăng revision thêm hoặc mở lại grant |
| Thông báo đến trễ hoặc trùng | Không thay projection ngược phiên bản hoặc hồi sinh quyền cũ |
| Thay đổi liên tiếp A -> B -> C | Token cũ không tự đảo C về A; báo cáo gốc vẫn được xử lý theo chính sách |
| Bằng chứng không đủ hoặc dịch vụ lỗi | Không fallback sang bỏ MFA hoặc câu hỏi kiến thức |
| Backup trước lần dùng token được restore | Không chấp nhận lại token đã dùng mà chưa qua hàng rào khôi phục |
| Log, trace và analytics | Không chứa bí mật hoặc dữ liệu lịch sử ngoài nhu cầu |
| Tài khoản SSO | Không tự sửa liên kết IdP hoặc cấp mật khẩu cục bộ để vượt quy trình |

Nên kiểm chứng kết quả quyền truy cập và dữ liệu thực tế, không chỉ HTTP status. Ví dụ, response có thể trả lỗi trong khi email đã bị đổi trước đó bởi một lệnh cập nhật không nằm trong transaction.

Phân biệt ít nhất ba mốc vận hành: email đã được khôi phục, các đường truy cập nguy hiểm đã bị chặn và chủ tài khoản đã hoàn tất thiết lập lại bảo mật. Giao diện và audit cần thể hiện đúng mốc đạt được.

## 15. Tài liệu đối chiếu và phạm vi thiết kế

- [OWASP Authentication — Changing a User’s Registered Email Address](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#changing-a-users-registered-email-address): quy trình thay email, xác nhận và thông báo.
- [OWASP Forgot Password — General Security Practices](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices): các thuộc tính bảo vệ token recovery.
- [OWASP Forgot Password — URL Tokens](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#url-tokens): URL tin cậy và hạn chế rò rỉ token.
- [OWASP Session Management — Reauthentication After Risk Events](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#reauthentication-after-risk-events): xác thực lại sau thay đổi thông tin quan trọng và recovery.

Việc tách token báo sự cố khỏi grant đảo, mô hình revision/epoch, thứ tự khóa, receipt và trạng thái `REVERSED_ACCESS_RESTRICTED` là thiết kế tham khảo của bài. Khi áp dụng, cần xác định chính sách bằng chứng, nguồn quản lý email, loại session và khả năng thu hồi thực tế. Các ví dụ không tự xác nhận một triển khai đã đạt mức bảo đảm hay tuân thủ tiêu chuẩn.
