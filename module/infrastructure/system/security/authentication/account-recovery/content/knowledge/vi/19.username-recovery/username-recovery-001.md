# Username recovery request — Tiếp nhận yêu cầu tìm lại tên đăng nhập

## 1. Mục tiêu và phạm vi

Trong chương **Username Recovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này giải thích cách tiếp nhận yêu cầu tìm lại tên đăng nhập mà vẫn bảo vệ thông tin tài khoản và hạn chế lạm dụng.

Người dùng có thể nhớ email hoặc số điện thoại liên hệ nhưng quên username đã dùng để đăng nhập. Hệ thống cần giúp đúng người tìm lại thông tin phù hợp mà không trở thành công cụ kiểm tra xem một cá nhân có tài khoản, thuộc tổ chức nào hoặc nắm vai trò gì.

Sau bài học, người học có thể:

- Phân biệt yêu cầu tìm username với đăng nhập và khôi phục credential.
- Thiết kế biểu mẫu, API và phản hồi chống liệt kê tài khoản.
- Xác minh quyền kiểm soát kênh liên hệ trước khi cung cấp thông tin.
- Xử lý một liên hệ gắn nhiều tài khoản hoặc nhiều tenant.
- Tổ chức hàng đợi, token, giới hạn gửi và dữ liệu yêu cầu an toàn.

Các API, schema, thời hạn và mã Java dưới đây là **thiết kế tham khảo của bài học**. Chúng không phải cấu hình bắt buộc cho mọi ứng dụng.

Điểm cần giữ xuyên suốt: **nhận yêu cầu không đồng nghĩa tìm thấy tài khoản; tìm thấy tài khoản không đồng nghĩa được tiết lộ username; biết username không đồng nghĩa được đăng nhập.**

## 2. Username recovery thực sự khôi phục điều gì?

### 2.1. Tên đăng nhập, tên hiển thị và định danh nội bộ

| Thành phần | Mục đích | Quan hệ với recovery |
| --- | --- | --- |
| Username | Giá trị người dùng nhập khi đăng nhập | Có thể được nhắc lại hoặc cung cấp theo chính sách |
| Display name | Tên hiển thị trong giao diện | Không nhất thiết duy nhất và không tự chứng minh tài khoản |
| Account ID nội bộ | Định danh ổn định cho quan hệ dữ liệu | Không nên dùng làm thông tin công khai trong phản hồi |
| Email hoặc số điện thoại | Kênh liên hệ, đôi khi cũng là username | Chỉ dùng cho recovery theo trạng thái đã thiết lập |
| Tenant hoặc realm | Không gian tài khoản hoặc cơ quan xác thực | Phải được xác định và giới hạn rõ |

Một ứng dụng có thể cho đăng nhập bằng email và không có username riêng. Khi đó, sản phẩm nên giải thích cách đăng nhập phù hợp thay vì tạo một cơ chế truy vấn tài khoản không cần thiết.

Nếu username là email công khai, quan hệ “email này có tài khoản trong dịch vụ này” vẫn có thể là thông tin nhạy cảm. Một chuỗi không phải bí mật không có nghĩa mọi mối liên hệ với chuỗi đó đều được phép tiết lộ.

### 2.2. Các thao tác không nằm trong quyền tìm username

Yêu cầu tìm username không được tự:

- Đổi mật khẩu hoặc gửi một password reset token kèm theo.
- Xóa MFA, passkey hoặc trusted device.
- Đổi email recovery.
- Mở lại tài khoản disabled.
- Tạo session đăng nhập hoặc API token.
- Gộp các tài khoản có cùng email thành một tài khoản.

Sau khi tìm được username, người dùng quay lại luồng đăng nhập bình thường. Nếu họ quên mật khẩu hoặc mất MFA, dùng luồng tương ứng và đáp ứng các điều kiện riêng.

### 2.3. Một số cách triển khai thực tế

Microsoft mô tả luồng dùng thông tin liên hệ bảo mật, xác minh mã rồi hiển thị gợi ý username. Google mô tả luồng tìm tên đăng nhập bằng thông tin recovery cùng bước xác nhận tài khoản trước khi đưa ra kết quả. Đây là ví dụ sản phẩm, không phải một chuẩn chung về lượng dữ liệu được tiết lộ. [Microsoft Support, Forgotten your Microsoft account username](https://support.microsoft.com/en-us/accounts-billing/manage/forgotten-your-microsoft-account-username), [Google Account Help, Recover your Google Account or Gmail](https://support.google.com/accounts/answer/7682439?hl=en)

Thiết kế tham khảo của bài học chọn gửi một hướng dẫn trung tính qua kênh đã thiết lập, sau đó cấp quyền xem kết quả giới hạn. Không đưa username vào phản hồi của biểu mẫu công khai.

## 3. Mô hình đe dọa của bước gửi yêu cầu

| Mối đe dọa | Ví dụ | Ranh giới cần bảo vệ |
| --- | --- | --- |
| Liệt kê tài khoản | Gửi nhiều email để tìm ai dùng dịch vụ | Không lộ kết quả qua body, status code hoặc thời gian rõ rệt |
| Lộ tư cách thành viên | Xác định một người thuộc tenant hoặc tổ chức nhạy cảm | Không tìm và trả dữ liệu ngoài realm được phép |
| Spam email hoặc SMS | Liên tục gửi yêu cầu tới một nạn nhân | Ngân sách gửi theo liên hệ và nguồn yêu cầu |
| Chiếm hoặc tái cấp kênh liên hệ | Số điện thoại được cấp lại; hộp thư đã bị chiếm | Không coi việc nhận mã là quyền với mọi dữ liệu của mọi tài khoản |
| Nhầm chuẩn hóa địa chỉ | Tự bỏ phần +tag hoặc gộp địa chỉ không tương đương | Dùng cùng hợp đồng so sánh với dữ liệu đã đăng ký |
| Rò token | Token vào log, tracker hoặc referrer | Token và quyền xem phải được bảo vệ như bí mật |
| Nhầm mục đích token | Dùng token tìm username để reset password | Kiểm tra scope phía máy chủ |
| Lạm dụng hỗ trợ | Nhân viên tiết lộ username từ ngày sinh hoặc tên đầy đủ | Quy trình và quyền đọc hồ sơ rõ ràng |
| Đồng thời và dữ liệu cũ | Kênh liên hệ đổi sau khi yêu cầu được tạo | Kiểm tra lại quan hệ và phiên bản trước khi tiết lộ |

Tên đầy đủ hoặc mã nhân viên có thể giúp lọc dữ liệu theo chính sách, nhưng thông tin có thể công khai không tự là bằng chứng quyền sở hữu.

Yêu cầu tìm username là một bề mặt công khai có thể bị tự động hóa. Vì vậy, cần thiết kế giới hạn tài nguyên ngay từ lúc tiếp nhận, không chỉ ở bước nhập mã xác minh.

## 4. Biểu mẫu và dữ liệu đầu vào

### 4.1. Thu thập tối thiểu

Một biểu mẫu đơn giản có thể gồm:

- Loại kênh liên hệ: email hoặc số điện thoại nếu sản phẩm hỗ trợ.
- Giá trị liên hệ.
- Realm công khai hoặc đường dẫn tenant, khi sản phẩm cần.
- Ngôn ngữ giao diện.
- Tín hiệu chống tự động hóa theo chính sách.

Không yêu cầu mật khẩu, recovery code, giấy tờ hoặc một username mà người dùng đang cố nhớ chỉ để gửi yêu cầu ban đầu.

Một sản phẩm có thể cần thông tin bổ sung để giảm nhầm tài khoản. Cần giải thích mục đích và không biến dữ liệu đó thành một câu hỏi bí mật để vượt bước xác minh.

### 4.2. Kiểm tra cú pháp không phải xác minh quyền kiểm soát

Kiểm tra email giúp phát hiện dữ liệu không phù hợp với hệ thống, giới hạn kích thước và ngăn đầu vào bị diễn giải sai. Nó không chứng minh người nhập nhận được thư.

OWASP phân biệt kiểm tra định dạng email với xác minh khả năng truy cập hộp thư và khuyến nghị dùng thư viện phù hợp với hệ thống gửi thư. [OWASP Input Validation Cheat Sheet, Email Address Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html#email-address-validation)

Không thực hiện một chuỗi DNS hoặc SMTP probe đồng bộ để rồi trả thông báo “hộp thư này có tài khoản”. Khả năng nhận thư, sự tồn tại của mailbox và liên kết với tài khoản là các vấn đề khác nhau.

### 4.3. Chuẩn hóa nhất quán với lúc đăng ký

Dùng cùng chính sách so sánh liên hệ đang được áp dụng trong hệ thống tài khoản:

- Không tự gộp mọi email bằng cách bỏ dấu chấm hoặc phần +tag.
- Không tự bỏ dấu tiếng Việt hay chuẩn hóa một username như một địa chỉ email.
- Nếu hỗ trợ tên miền quốc tế hoặc email quốc tế hóa, dùng quy tắc và thư viện đã được chọn cho toàn hệ thống.
- Số điện thoại cần ngữ cảnh quốc gia và cách biểu diễn chuẩn được xác định; không tự đoán từ vị trí IP.
- Đầu vào quá dài phải bị từ chối, không bị cắt để tiếp tục tra cứu.

RFC 5321 phân biệt domain không nhạy hoa thường với local-part cần được bảo toàn theo ngữ nghĩa của hệ thống nhận. Vì vậy, lowercase toàn bộ địa chỉ không phải phép biến đổi phổ quát an toàn cho mọi nhà cung cấp. Ứng dụng phải có hợp đồng so sánh nhất quán và lưu cách phân phối đã được xác minh. [RFC 5321, Section 2.4](https://www.rfc-editor.org/rfc/rfc5321.html#section-2.4)

Đổi chính sách chuẩn hóa là một thay đổi dữ liệu, có thể gây trùng hoặc nhầm liên hệ. Không sửa riêng endpoint recovery rồi để đăng ký và đăng nhập dùng quy tắc khác.

### 4.4. Xác định realm phía máy chủ

Realm là phạm vi tra cứu, không phải bằng chứng người yêu cầu thuộc tenant đó. Máy chủ có thể lấy realm từ đường dẫn hoặc cấu hình tên miền được tin cậy, rồi kiểm tra nó có được mở cho luồng công khai hay không.

Nếu client gửi một mã tenant công khai, vẫn phải xác thực giá trị và giới hạn truy vấn. Không nhận tenant ID nội bộ tùy ý để quét dữ liệu xuyên tổ chức.

Với mô hình khám phá tài khoản toàn hệ thống, cần một chính sách riêng cho việc tiết lộ quan hệ nhiều tenant. Không mặc định rằng xác minh một email cho phép liệt kê toàn bộ tư cách thành viên.

## 5. Hợp đồng API tiếp nhận

### 5.1. Một request minh họa

~~~http
POST /public/realms/learning/username-recovery/requests
Content-Type: application/json
Idempotency-Key: 8f2c2e40-1e48-45a9-9508-6fe8f2874b02

{
  "contact": {
    "type": "EMAIL",
    "value": "minh@example.test"
  },
  "locale": "vi-VN"
}
~~~

Mục đích USERNAME_RECOVERY do endpoint phía máy chủ quy định, không lấy một scope tùy ý từ client. Giới hạn kích thước body và tập trường được chấp nhận để tránh mass assignment.

Phản hồi cho một yêu cầu hợp lệ về cấu trúc:

~~~http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Type: application/json

{
  "requestId": "urq_7mK4nR2pT9wX6aV8",
  "message": "Nếu thông tin phù hợp, hướng dẫn tìm tên đăng nhập sẽ được gửi qua kênh đã đăng ký."
}
~~~

Theo RFC 9110, 202 biểu thị đã nhận để xử lý nhưng chưa hoàn tất; bản thân status này không cam kết hành động cuối cùng sẽ xảy ra. Trong thiết kế tham khảo, nó không xác nhận đã tìm thấy tài khoản hoặc đã gửi thư. [RFC 9110, Section 15.3.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3)

Request ID được tạo độc lập với account ID, không mã hóa email hoặc số lượng kết quả. Nó phục vụ tương quan hỗ trợ; không phải một credential để xem username hoặc xác minh kênh.

### 5.2. Những gì không trả trước xác minh

Không trả các trường như:

~~~json
{
  "accountExists": true,
  "matchedCount": 2,
  "maskedUsername": "m***.nguyen",
  "deliveryTarget": "m***@company.test",
  "isAdministrator": false,
  "tenantNames": ["..."],
  "ssoProvider": "..."
}
~~~

Đoạn trên là **ví dụ phản hồi cần tránh**. Masking vẫn có thể tiết lộ một mối liên hệ mà đối tượng chưa được phép biết.

OWASP khuyến nghị phản hồi chung cho những trường hợp tài khoản không tồn tại, thông tin không đúng hoặc tài khoản bị khóa; khác biệt thời gian xử lý cũng có thể trở thành tín hiệu liệt kê. Bài học áp dụng nguyên tắc đó cho bước yêu cầu tìm username. [OWASP Authentication Cheat Sheet, Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)

Không thêm endpoint trạng thái công khai trả SENT, NO_MATCH, ACCOUNT_DISABLED hoặc số lượng tài khoản. Nếu có theo dõi tiến độ trước xác minh, chỉ cung cấp trạng thái tiếp nhận chung, không phân nhánh theo kết quả nội bộ.

### 5.3. Xử lý lỗi vẫn phải nhất quán

| Trường hợp | Cách phản hồi tham khảo |
| --- | --- |
| JSON sai hoặc contact vượt giới hạn cú pháp | 400 với lỗi định dạng chung, không tra cứu tài khoản |
| Request hợp lệ; có hoặc không có kết quả | 202 với cùng cấu trúc và thông điệp |
| Vượt hạn mức theo nguồn gửi công khai | Có thể 429, nếu quy tắc không dựa vào tài khoản có tồn tại |
| Vượt ngân sách gửi tới liên hệ | Gộp hoặc hạn chế nội bộ; vẫn giữ phản hồi tiếp nhận chung |
| Toàn hệ thống không thể nhận việc bền vững | 503 chung, không tùy theo kết quả tra cứu |
| Lỗi gửi thư xảy ra sau tiếp nhận | Xử lý nội bộ; không công khai biến thành dấu hiệu có tài khoản |

Không dùng Retry-After khác nhau theo việc email có tài khoản hay không. Đặc biệt, hạn mức theo liên hệ phải được tính cho cả đầu vào không tìm thấy tài khoản; nếu chỉ tạo bộ đếm khi tìm thấy, chính bộ đếm có thể gây rò rỉ.

Một lỗi định dạng độc lập với dữ liệu tài khoản có thể được giải thích rõ để người dùng sửa. Chống enumeration không có nghĩa phải nhận mọi chuỗi vô nghĩa rồi âm thầm thất bại.

## 6. Pipeline xử lý bất đồng bộ

### 6.1. Tách đường tiếp nhận khỏi đường tìm kiếm

~~~mermaid
sequenceDiagram
    actor U as Người gửi
    participant API as API công khai
    participant DB as Kho request và outbox
    participant W as Worker nội bộ
    participant A as Kho liên hệ tài khoản
    participant M as Kênh gửi

    U->>API: Gửi contact và realm
    API->>API: Kiểm tra đầu vào, hạn mức, idempotency
    API->>DB: Ghi tiếp nhận và công việc cần xử lý
    DB-->>API: Commit
    API-->>U: 202 với thông điệp chung
    W->>DB: Nhận công việc
    W->>A: Tra cứu liên hệ đã thiết lập trong đúng realm
    W->>W: Kiểm tra chính sách và ngân sách gửi
    alt Có đích đủ điều kiện
        W->>DB: Ghi challenge và ý định gửi có bảo vệ
        W->>M: Phân phối hướng dẫn xác minh
    else Không đủ điều kiện hoặc không khớp
        W->>DB: Kết thúc nội bộ, không lộ kết quả
    end
~~~

API không chờ SMTP hoặc SMS provider trả lời. Đường tiếp nhận vẫn cần được bảo vệ khỏi tải lớn; bất đồng bộ không tự giải quyết DoS.

Hàng đợi không phải nơi chứa plaintext tùy tiện. Có thể chỉ đưa request ID vào job, còn dữ liệu liên hệ cần thiết được lưu mã hóa, phân quyền và có hạn giữ ở kho request.

Nếu dùng transactional outbox, việc ghi request và ý định xử lý diễn ra cùng transaction. Consumer nhận lặp phải có cơ chế deduplicate hoặc cập nhật trạng thái có điều kiện.

### 6.2. Tra cứu bằng quan hệ đã thiết lập

Worker chỉ xét liên hệ đã được xác minh và được phép dùng cho mục đích tìm username. Không sử dụng một trường email giao hàng, email hóa đơn hoặc ghi chú của nhân viên như kênh recovery chỉ vì nó trùng chuỗi.

Đích phân phối cuối lấy từ bản ghi liên hệ đã thiết lập. Contact người gửi nhập chỉ dùng để tìm theo hợp đồng so sánh, không cho phép đổi đích qua một trường phụ.

Không gửi hướng dẫn tới một địa chỉ mới được thêm trong ticket để thay cho kênh mất quyền truy cập. Trường hợp mất kênh cần nhánh xác minh khác có chính sách riêng.

Một request không tìm thấy tài khoản có thể kết thúc mà không gửi email. Phản hồi công khai không tiết lộ kết quả đó. Không cần gửi một email “không có tài khoản” tới mọi địa chỉ được nhập, vì điều đó có thể làm tăng spam.

### 6.3. Trạng thái nội bộ

Một tập trạng thái tham khảo:

~~~text
RECEIVED
PROCESSING
SUPPRESSED
NO_ELIGIBLE_MATCH
PROOF_PENDING
CONTACT_PROVED
RESULT_AUTHORIZED
COMPLETED
EXPIRED
STALE
DELIVERY_FAILED
~~~

Các trạng thái này là dữ liệu nội bộ. Không xuất nguyên trạng ra trình duyệt đã gửi yêu cầu chỉ vì trình duyệt có request ID.

CONTACT_PROVED chỉ có nghĩa hoàn thành phép kiểm soát kênh cho đúng mục đích và phạm vi. RESULT_AUTHORIZED còn cần kiểm tra chính sách tiết lộ, quan hệ liên hệ hiện tại và các hạn chế tài khoản.

Không ghi COMPLETED khi nhà cung cấp vừa chấp nhận gửi thư. Trong mô hình này, hoàn tất nghĩa là người có quyền đã nhận hoặc xem kết quả theo luồng được cho phép.

## 7. Phân phối bằng chứng kiểm soát kênh

### 7.1. Thiết kế một thông báo ít tiết lộ

Thông báo ban đầu nên cho biết có yêu cầu tìm username và cách tiếp tục nếu chính người nhận đã yêu cầu. Nó không cần chứa username đầy đủ, tên tenant nhạy cảm, vai trò, số lượng tài khoản hoặc chi tiết thiết bị.

Ví dụ nội dung:

> Có yêu cầu tìm thông tin đăng nhập liên quan đến kênh liên hệ này. Nếu bạn muốn tiếp tục, hãy dùng hướng dẫn trong thư. Nếu không, bạn có thể bỏ qua; yêu cầu này không thay mật khẩu hoặc phương tiện xác thực.

Đó là mô tả của thiết kế minh họa. Hệ thống vẫn cần đánh giá việc chính tên dịch vụ hoặc tên người gửi có thể tiết lộ quan hệ nhạy cảm qua email, SMS và màn hình khóa.

Không để người gửi tự điền subject, nội dung, URL hoặc địa chỉ reply-to để biến tính năng thành công cụ gửi thư lừa đảo.

### 7.2. Challenge và quyền xem kết quả

Một lựa chọn tham khảo là liên kết chứa token opaque sinh từ 32 byte ngẫu nhiên mật mã, có hiệu lực 15 phút. DB lưu digest; token gốc chỉ tồn tại trong quá trình phân phối được bảo vệ.

Challenge gắn với:

- Request ID và mục đích USERNAME_RECOVERY.
- Realm hoặc tập phạm vi được phép.
- Liên hệ đã dùng, phiên bản quan hệ recovery và phiên bản chính sách.
- Thời điểm phát hành, hết hạn và trạng thái dùng.
- Tham chiếu tập ứng viên hoặc cách tính lại tập ứng viên được giới hạn.

Các thuộc tính ngẫu nhiên an toàn, dùng một lần và có thời hạn được OWASP nêu cho reset token. Thiết kế này vận dụng các thuộc tính đó cho token tìm username, với scope hẹp hơn và không có quyền đổi credential. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Không dùng cùng token hoặc cùng endpoint để tìm username và đặt lại mật khẩu. Nếu hỗ trợ mã ngắn, cần chính sách thử, lưu verifier và thời hạn phù hợp với entropy thấp; không suy rộng cơ chế digest của token ngẫu nhiên dài sang mọi OTP.

### 7.3. Xác minh không được mở quyền cho người khởi tạo vô danh

Một lỗi nghiêm trọng là:

1. Đối tượng gửi yêu cầu bằng email của nạn nhân.
2. Nạn nhân mở thư và xác nhận.
3. Trình duyệt của đối tượng tự nhận username do hệ thống đánh dấu request đã xác minh.

Kết quả cần được gắn với ngữ cảnh đang trình bằng chứng và được cho phép xem, không tự đẩy về mọi client giữ request ID. Nếu muốn hỗ trợ xác minh khác thiết bị, phải có giao thức ràng buộc và chấp thuận riêng.

GET từ email chỉ mở trang giải thích. Bước POST chủ động có thể trao đổi token thành một phiên chỉ có quyền USERNAME_RECOVERY_VIEW. Trao đổi token và tạo phiên phải nguyên tử.

Phiên giới hạn có thể cho đọc lại cùng kết quả trong thời gian ngắn, chẳng hạn 5 phút và không vượt hạn tuyệt đối của challenge. Tính dùng một lần áp dụng cho việc trao đổi token, không buộc người dùng chỉ được tải trang đúng một lần.

Đối với SMS code nhập trên thiết bị khác, người nhận cần hiểu mã dùng cho việc gì và không đưa mã cho người gọi. Ràng buộc kỹ thuật không loại bỏ hoàn toàn tấn công chuyển tiếp mã theo thời gian thực.

## 8. Quyết định tiết lộ khi một liên hệ gắn nhiều tài khoản

### 8.1. Quyền kiểm soát kênh không phải quyền với mọi tài khoản

Email dùng chung trong gia đình, hộp thư phòng ban hoặc số điện thoại tái cấp có thể gắn với nhiều người. Việc người yêu cầu nhận được một mã không đủ để tự liệt kê mọi tài khoản từng liên quan.

Sản phẩm cần quy định:

- Những loại tài khoản nào cho phép tìm bằng liên hệ đó.
- Phạm vi tenant và loại dữ liệu được hiển thị.
- Khi nào cần bằng chứng bổ sung.
- Có cho hiển thị username đầy đủ hay chỉ gợi ý.
- Cách xử lý tài khoản đã xóa, disabled, đặc quyền hoặc có tranh chấp.
- Giới hạn số kết quả và cách chuyển hỗ trợ an toàn khi vượt giới hạn.

Một profile minh họa cho ứng dụng thông thường có thể cho xem username của các tài khoản đang hoạt động mà liên hệ được xác nhận là kênh cá nhân được phép tìm username trong đúng realm. Profile này không tự áp dụng cho hộp thư dùng chung hoặc tài khoản đặc quyền.

### 8.2. Masking cần hữu ích và có chủ đích

Nếu chỉ hiện ký tự đầu và dấu sao, người dùng có thể vẫn không nhớ được username. Nếu hiện quá nhiều, masking không còn bảo vệ đáng kể. Cần chọn mức hiển thị theo dữ liệu và nguy cơ.

Các tài khoản có tên gần giống nhau cần được phân biệt bằng thông tin được phép, không dùng vai trò quản trị, lịch sử đăng nhập hoặc dữ liệu nhạy cảm để làm nhãn tiện lợi.

Không gửi một danh sách username hoặc account ID đầy đủ cho client rồi chỉ che ở giao diện. Dữ liệu đã tiết lộ ngay khi đến response.

### 8.3. Kiểm tra lại trước khi xem

Trong lúc request chờ, email recovery có thể bị thay, liên hệ bị thu hồi hoặc username được đổi. Trước khi cung cấp kết quả, máy chủ kiểm tra lại:

1. Challenge hoặc phiên giới hạn còn hiệu lực.
2. Liên hệ vẫn được phép cho mục đích này.
3. Version và trạng thái tài khoản không có thay đổi cần đánh giá lại.
4. Tập kết quả vẫn thuộc phạm vi đã cho phép.
5. Mức tiết lộ hiện tại phù hợp với policy.

Nếu snapshot cũ không còn áp dụng, chuyển STALE hoặc yêu cầu xác minh lại. Không gửi username lịch sử chỉ vì nó được chụp lúc tạo request.

Với SSO, thông tin phù hợp có thể là hướng dẫn đăng nhập qua IdP được cấu hình, nhưng chỉ tiết lộ mối liên hệ tổ chức khi được phép. Không tạo mật khẩu cục bộ hoặc liên kết tài khoản mới trong luồng này.

## 9. Chống lạm dụng mà không khóa người dùng hợp lệ

### 9.1. Các ngân sách khác nhau

Nên tách ít nhất các loại ngân sách:

| Ngân sách | Mục đích |
| --- | --- |
| Tiếp nhận theo nguồn | Giới hạn tài nguyên API trước lưu trữ và tra cứu |
| Tiếp nhận theo realm | Bảo vệ một tenant trước tấn công tập trung |
| Phân phối theo liên hệ | Giảm email bombing hoặc SMS bombing |
| Phân phối theo nhà cung cấp | Giới hạn chi phí và xử lý quá tải |
| Thử challenge | Ngăn dò mã hoặc token qua endpoint xác minh |
| Xem kết quả | Giới hạn truy vấn trong phiên recovery giới hạn |

Bộ đếm dùng chung giữa các instance và cập nhật nguyên tử. Không cho tạo request mới, đổi cookie hoặc chọn kênh khác để xóa mọi lịch sử thử liên quan.

Ví dụ một sản phẩm chọn tối đa ba lần phân phối tới một liên hệ trong một giờ và không quá hai challenge đang hoạt động trong một realm. Đây là con số minh họa, cần điều chỉnh theo nguy cơ và khả năng sử dụng.

Nếu hết ngân sách phân phối, giữ phản hồi chung và gộp hoặc trì hoãn công việc. Không khóa tài khoản, không làm mất khả năng đăng nhập và không thu hồi challenge hợp lệ chỉ vì có thêm yêu cầu chưa xác minh.

### 9.2. Khóa bộ đếm không nên chứa PII đọc được

Một khóa tham khảo cho hạn mức theo liên hệ:

~~~text
contact_rate_key = HMAC(
    K_rate,
    encodeLengthPrefixed(
        "username-recovery-rate/v1",
        realm_id,
        contact_type,
        normalized_contact
    )
)
~~~

HMAC làm giảm việc lưu email đọc được trong tên khóa Redis hoặc chỉ số vận hành. Nó không làm dữ liệu trở thành vô danh hoàn toàn: người có khóa và tập ứng viên vẫn có thể liên kết các giá trị.

K_rate cần được quản trị theo mục đích và phiên bản. Không dùng chung khóa ký session hoặc khóa cho mục đích không liên quan. Việc xoay khóa cần tránh vô tình xóa sạch ngân sách thử đang có hiệu lực.

Không dùng email làm label metric hoặc nhúng vào URL theo dõi. Các hệ thống giám sát thường có nhiều người đọc hơn kho tài khoản.

### 9.3. CAPTCHA và tín hiệu thiết bị

CAPTCHA có thể hạn chế một phần tự động hóa, nhưng không chứng minh người gửi là chủ tài khoản. Cần có lựa chọn tiếp cận phù hợp và không tiết lộ điều kiện hiển thị theo việc một contact có tài khoản hay không.

IP hoặc thiết bị quen có thể giúp đánh giá rủi ro. Chúng không đủ để bỏ qua phép kiểm soát kênh hoặc chính sách tiết lộ.

Một sự cố phát tán email cần được xử lý bằng ngân sách và hàng rào gửi phù hợp. Không dùng việc người dùng không mở thư làm bằng chứng rằng họ đang tấn công.

## 10. Mô hình dữ liệu và mã Java minh họa

### 10.1. Bản ghi tiếp nhận

Một bản ghi có thể chứa:

~~~text
request_id
realm_id
purpose = USERNAME_RECOVERY
contact_type
encrypted_contact_reference
contact_key_version
contact_lookup_or_rate_key
normalization_policy_version
locale
policy_version
idempotency_fingerprint
internal_status
created_at
expires_at
~~~

Không cần gắn account ID ngay lúc tiếp nhận, vì một contact có thể không khớp hoặc khớp nhiều tài khoản. Nếu lưu tập ứng viên ở bước sau, đặt nó trong vùng dữ liệu nội bộ được phân quyền, có version và hạn giữ.

Lookup key và rate key có thể có mục đích khác nhau. Nếu thiết kế dùng keyed index để tìm contact, cần khóa và hợp đồng truy vấn riêng; không mặc định khóa chống spam cũng là chỉ mục định danh của toàn bộ hệ thống.

Encrypted contact reference trỏ tới dữ liệu được mã hóa để worker sử dụng, không phải một URL công khai chứa email. Mã hóa cần cơ chế bảo vệ tính toàn vẹn phù hợp với cách lưu.

Hạn giữ request, dữ liệu liên hệ, challenge và audit có thể khác nhau. Không giữ mọi payload vô thời hạn chỉ để dễ điều tra.

### 10.2. API tiếp nhận không tra cứu tài khoản đồng bộ

Đoạn sau là mã giả Java. Các repository, policy và lớp mật mã thể hiện hợp đồng cần triển khai; không phải mã có thể chạy ngay.

~~~java
AcceptedReceipt createUsernameRecovery(
        String publicRealm,
        RecoveryRequestInput input,
        RequestMetadata metadata,
        String idempotencyKey) {

    Realm realm = realms.requirePublicRecoveryRealm(publicRealm);
    sourceLimits.requireCapacity(realm.id(), metadata.sourceSignals());

    inputRules.requireBoundedSupportedInput(input);
    NormalizedContact contact = contacts.normalizeForLookup(
        input.contact(), realm.contactPolicyVersion());

    String locale = locales.requireSupportedOrDefault(input.locale());
    byte[] contactRateKey = rateKeys.forContact(realm.id(), contact);

    RequestFingerprint fingerprint = fingerprints.forRequest(
        realm.id(), USERNAME_RECOVERY, contact, locale);

    // Hàm này ghi request và outbox trong cùng transaction.
    // Không kiểm tra accountExists và không gọi nhà cung cấp gửi.
    IntakeRecord record = intake.acceptOrReplayAtomically(
        realm.id(),
        idempotencyKey,
        fingerprint,
        protectedContactStore.seal(contact),
        contactRateKey,
        locale,
        clock.instant()
    );

    return AcceptedReceipt.generic(record.publicRequestId());
}
~~~

Hợp đồng quan trọng của ví dụ:

- Realm công khai là một tài nguyên đã được phép khám phá; nếu tư cách tổ chức cần được che, phải dùng giao diện định tuyến phù hợp hơn.
- Idempotency key được giới hạn kích thước, thời hạn và phạm vi; cùng key với payload khác bị từ chối một cách không dựa vào dữ liệu tài khoản.
- Replay chỉ trả receipt chung, không trả contact, challenge hoặc kết quả tìm kiếm.
- Dữ liệu dùng cho fingerprint được mã hóa hoặc băm có khóa theo mục đích, không lưu một hash email dễ dò như biện pháp bảo mật duy nhất.
- Protected contact store không được để lại một bản raw trong job, log hoặc exception.

Nếu seal tạo tài nguyên riêng ngoài DB, cần quản lý tài nguyên không được commit hoặc dùng một thiết kế envelope có thể lưu nguyên tử trong bản ghi. Từ “atomically” không tự làm các hệ thống khác nhau trở thành một transaction.

### 10.3. Worker tạo kế hoạch phân phối

~~~java
void processRecoveryRequest(UUID requestId) {
    RecoveryRequest request = requests.claimForProcessing(requestId);
    if (request == null) {
        return;
    }

    if (!clock.instant().isBefore(request.expiresAt())) {
        requests.markExpired(request.id());
        return;
    }

    NormalizedContact contact = protectedContactStore.open(request);
    DeliveryPermit permit = deliveryLimits.reserveForContactAndRealm(
        request.realmId(), request.contactRateKey());

    if (!permit.allowed()) {
        requests.markSuppressed(request.id());
        return;
    }

    CandidateSet candidates = directory.findByEligibleRecoveryContact(
        request.realmId(), contact, request.normalizationPolicyVersion());

    DisclosurePlan plan = disclosurePolicy.planBeforeProof(
        request, candidates, clock.instant());

    if (!plan.maySendProof()) {
        requests.finishWithoutPublicResult(request.id(), plan.reason());
        return;
    }

    // Trong transaction: kiểm tra lại claim/version, tạo challenge,
    // lưu payload phân phối được bảo vệ và ghi outbox.
    proofDelivery.prepareAtomically(request, plan, permit);
}
~~~

Claim cần lease và cơ chế thử lại sau khi worker chết. prepareAtomically phải kiểm tra request còn được sở hữu hợp lệ, chưa xử lý và còn hạn. Worker cũ quay lại sau khi lease mất không được tạo thêm challenge ngoài giới hạn.

Một delivery permit cần có vòng đời được định nghĩa: giữ chỗ, xác nhận dùng hoặc kết thúc theo chính sách. Không hoàn lại ngân sách vô hạn cho các lần dò không khớp, vì đối tượng vẫn có thể tiêu tốn tài nguyên tìm kiếm.

Đoạn mã chỉ đến bước chuẩn bị phân phối. Worker gửi riêng thực hiện retry và kiểm tra hạn của challenge. Không gọi nhà cung cấp trong transaction dài rồi giả định rollback có thể thu hồi thư đã gửi.

## 11. Độ tin cậy của hàng đợi và xử lý lỗi

| Sự cố | Hành vi an toàn trong mô hình tham khảo |
| --- | --- |
| Không ghi được tiếp nhận bền vững | Trả lỗi dịch vụ chung, không giả báo đã nhận |
| Client gửi lại sau mất response | Idempotency trả receipt chung của cùng thao tác |
| Job được nhận hai lần | Claim, unique constraint hoặc trạng thái có điều kiện ngăn tạo challenge trùng |
| Worker chết khi đang xử lý | Lease hết hạn cho phép tiếp tục bằng request đã lưu |
| Email provider timeout | Retry theo operation ID và hạn mức; chấp nhận khả năng gửi trùng được kiểm soát |
| Nhà cung cấp trả callback | Xác thực callback; không lộ trạng thái gửi qua API công khai |
| Challenge hết hạn trước khi gửi | Không gửi một quyền đã hết hạn và không tự kéo dài nó |
| Kênh recovery thay trước khi gửi hoặc xem | Kiểm tra version; đánh giá lại hoặc STALE |
| Mất khả năng giải mã contact | Không gửi sang địa chỉ khác hoặc bỏ qua xác minh |
| Hệ thống chính sách không sẵn sàng | Chưa tiết lộ kết quả; hướng dẫn thử lại phù hợp |

Không thể bảo đảm email chỉ được gửi đúng một lần nếu nhà cung cấp đã nhận nhưng response bị mất, trừ khi có giao thức hỗ trợ tương ứng. Có thể dùng idempotency của nhà cung cấp, kiểm soát retry và để các bản thư lặp tham chiếu cùng challenge còn hiệu lực.

Ngân sách gửi cần được tính ở điểm thực tế phát sinh phân phối. Retry phải có trần để một lỗi nhà cung cấp không biến thành nhiều tin nhắn và chi phí ngoài ý muốn.

Nếu request có nhiều ứng viên, một callback gửi thành công không có quyền tiết lộ tất cả. Quyền xem vẫn được kiểm tra tại bước xác minh và truy xuất kết quả.

Một lỗi tìm username không nên gây reset mật khẩu hoặc thu hồi session. Đây là luồng trợ giúp định danh; tác động của nó phải đúng phạm vi đó.

## 12. Giao diện và hỗ trợ người dùng

### 12.1. Hướng dẫn có ích mà không tiết lộ dữ liệu

Sau phản hồi chung, giao diện có thể hướng dẫn:

- Kiểm tra hộp thư, thư rác hoặc kênh mà người dùng đã chọn.
- Kiểm tra lại lỗi gõ và đúng cổng đăng nhập.
- Thử thông tin liên hệ khác mà chính người dùng đã đăng ký.
- Với tài khoản tổ chức, dùng kênh quản trị viên được công bố.
- Nếu mất luôn kênh recovery, chuyển sang quy trình được phê chuẩn.

Không hiển thị “email này không có tài khoản, hãy dùng số điện thoại kết thúc bằng 1234”. Phần gợi ý đó vừa xác nhận quan hệ tài khoản vừa tiết lộ kênh khác.

Countdown gửi lại nên dựa trên chính sách giao diện và không phản ánh việc tài khoản có tồn tại. Người dùng đổi tab hoặc tải lại không được xóa hạn mức phía máy chủ.

### 12.2. Khi người dùng báo mất kênh hoặc không nhận được thư

Nhân viên hỗ trợ cần có kịch bản rõ, quyền đọc tối thiểu và log truy cập. Không tìm rồi đọc username chỉ vì người gọi biết tên, email cũ hoặc ngày sinh.

Nếu có quy trình xác minh bổ sung, nó phải có bằng chứng và phạm vi được tổ chức chấp nhận. Không yêu cầu người dùng gửi mật khẩu, OTP hoặc reset token qua chat hỗ trợ.

Một tài khoản không có kênh đủ điều kiện có thể chưa được cung cấp username qua self-service. Điều này không chứng minh tài khoản không tồn tại và không tạo lý do để tự hạ kiểm soát.

## 13. Audit, quyền riêng tư và giám sát

Các sự kiện nội bộ nên có request ID, realm, policy version, loại kênh, giai đoạn xử lý, reason code, actor dịch vụ và các mốc thời gian cần thiết.

Không đưa token, URL có token, email đầy đủ hoặc danh sách username vào log thông thường. Dùng tham chiếu nội bộ và chỉ cho người có nhiệm vụ truy cập dữ liệu gốc.

Các chỉ số có ích gồm:

- Lưu lượng tiếp nhận, tỷ lệ bị hạn chế và mức dùng hàng đợi.
- Số lần phân phối, retry và callback lỗi.
- Tỷ lệ challenge được hoàn thành trong hạn.
- Tỷ lệ request stale do thay đổi liên hệ.
- Mức tăng bất thường của yêu cầu theo nguồn, realm hoặc liên hệ.
- Phản ánh spam và tỷ lệ người dùng vẫn không tìm được cách đăng nhập.

Không công khai các số đo này theo một địa chỉ riêng lẻ. Metric có cardinality cao theo email vừa tăng chi phí vừa phát tán PII.

Khi hết thời hạn giữ, xóa hoặc giảm dữ liệu request theo chính sách. Backup và việc phục hồi cần được xét để không làm sống lại challenge đã thu hồi hoặc liên hệ không còn được phép dùng.

## 14. Ví dụ xuyên suốt

Minh nhớ email recovery nhưng quên username của ứng dụng học tập.

1. Minh vào đúng realm công khai, nhập email và gửi yêu cầu.
2. API kiểm tra cấu trúc, ghi receipt chung và trả 202. Trình duyệt không nhận username, số tài khoản hoặc địa chỉ che.
3. Worker tìm các liên hệ đủ điều kiện trong realm; nếu không có, kết thúc nội bộ theo cùng hợp đồng công khai.
4. Nếu được phép, hệ thống gửi hướng dẫn trung tính tới đích đã thiết lập.
5. Minh mở liên kết, chủ động tiếp tục và nhận phiên chỉ có quyền xem kết quả.
6. Máy chủ kiểm tra lại trạng thái liên hệ và chính sách tiết lộ rồi hiển thị thông tin được phép.
7. Minh dùng thông tin đó ở trang đăng nhập; mật khẩu và MFA vẫn được yêu cầu như trước.

Các biến thể cần hiểu:

- Nếu một người khác tạo request bằng email của Minh, việc Minh xác nhận không tự gửi kết quả về trình duyệt của người đó.
- Nếu email gắn nhiều tài khoản, hệ thống áp dụng profile cho từng ứng viên, không trả toàn bộ dữ liệu xuyên tenant.
- Nếu email recovery bị thay trong lúc chờ, challenge cũ không mặc nhiên còn quyền xem.
- Nếu người gửi lặp nhiều lần, hệ thống hạn chế phân phối mà không khóa tài khoản hoặc phá challenge hợp lệ.
- Nếu Minh mất cả email, luồng chuyển sang hỗ trợ hoặc recovery khác; không đổi đích chỉ từ lời khai.

## 15. Các điều kiện bất biến của một request an toàn

Một thiết kế cụ thể cần bảo đảm:

1. Người chưa xác minh không phân biệt được kết quả tra cứu từ hợp đồng công khai.
2. Request ID, receipt và idempotency key không cấp quyền xem username.
3. Chỉ kênh đã thiết lập và được cho phép mới được dùng để phân phối.
4. Quyền chứng minh kênh gắn với người trình bằng chứng và phạm vi phù hợp.
5. Kết quả được lọc phía máy chủ theo realm, tài khoản, policy và trạng thái hiện hành.
6. Giới hạn gửi và thử vẫn có hiệu lực khi đổi request hoặc instance.
7. Không thay credential, session ứng dụng hoặc tư cách truy cập chỉ vì có yêu cầu tìm username.
8. Dữ liệu nhạy cảm không bị sao chép vào log, queue hoặc API trợ giúp không được phân quyền.

Tiếp nhận username recovery là thiết kế một quyền trợ giúp có giới hạn. Giá trị của luồng nằm ở việc giúp đúng người tìm lại thông tin đăng nhập trong khi giữ nguyên các ranh giới xác thực còn lại.
