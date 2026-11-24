# Notification flooding — Ngăn dội thông báo trong khôi phục tài khoản

## 1. Notification flooding là gì?

Một người dùng chỉ cần nhập email vào chức năng quên mật khẩu. Nếu mỗi lần gửi biểu mẫu đều tạo một email mới, kẻ tấn công có thể dùng chính hệ thống hợp lệ để dội hàng trăm thông báo đến nạn nhân.

**Notification flooding** là việc tạo ra quá nhiều email, SMS, cuộc gọi hoặc push notification khiến người nhận bị quấy rối, khó nhận ra sự kiện thật hoặc không thể tiếp tục khôi phục tài khoản bình thường.

Trong khôi phục tài khoản, hậu quả không chỉ là tốn tài nguyên:

- Người dùng bỏ qua cảnh báo vì đã nhận quá nhiều thông báo giống nhau.
- Thư báo đổi mật khẩu hoặc gắn MFA trái phép bị chìm giữa các thư yêu cầu khôi phục.
- Kẻ tấn công giả danh hỗ trợ, đề nghị người dùng cung cấp OTP để “dừng thông báo”.
- Hạn mức email hoặc SMS bị tiêu thụ, ảnh hưởng những người dùng khác.
- Người dùng bị mắc kẹt nếu mọi liên kết hoặc mã trước đó bị thay thế liên tục.

Thiết kế cần hạn chế số thông báo thực sự được gửi, đồng thời duy trì khả năng khôi phục hợp lệ và phát hiện thay đổi tài khoản trái phép. Bài học này tập trung vào các thông báo phát sinh từ quy trình recovery, kể cả khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực.

## 2. Phân biệt các dạng lạm dụng

| Hiện tượng | Điều bị lợi dụng | Điểm cần bảo vệ |
| --- | --- | --- |
| Recovery email bombing | Biểu mẫu công khai tạo email đặt lại mật khẩu | Số thư đến một người nhận |
| SMS hoặc voice flooding | Mỗi yêu cầu làm phát sinh tin nhắn hay cuộc gọi có phí | Người nhận, chi phí và năng lực gửi |
| Push fatigue | Nhiều yêu cầu chấp thuận khiến người dùng bấm đồng ý để hết phiền | Ý định xác thực và sự gắn kết với đúng giao dịch |
| Che lấp cảnh báo | Nhiều thư yêu cầu khôi phục làm chìm thư báo thay đổi thật | Độ nổi bật và khả năng chuyển phát cảnh báo quan trọng |
| Retry storm | Hệ thống gửi lại quá nhiều do lỗi hoặc phản hồi chậm | Logic gửi, hàng đợi và trạng thái chuyển phát |
| Flood nhiều tài khoản | Mỗi tài khoản bị gửi ít nhưng tổng số rất lớn | Ngân sách tenant, nhà cung cấp và toàn hệ thống |

Notification flooding rộng hơn push fatigue. Thư báo một yêu cầu quên mật khẩu không nhất thiết có nút chấp thuận; nó vẫn có thể gây hại khi được gửi quá nhiều.

NIST SP 800-63B-4 mô tả authentication fatigue và khuyến nghị giới hạn tốc độ hoặc tổng số push notification từ lần xác thực thành công gần nhất trong ngữ cảnh xác thực ngoài băng. Đây là hướng dẫn cho cơ chế đó, không phải một hạn mức số lượng chung cho mọi email khôi phục. [Nguồn: NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html).

Một kẻ tấn công không cần vượt qua kiểm tra token để gây flood. Chức năng tạo và gửi thông báo có thể đã đủ tạo ra tác động.

## 3. Những nguyên tắc phải giữ đồng thời

Một chính sách chống flood phù hợp cần cân bằng các yêu cầu sau:

| Yêu cầu | Ý nghĩa |
| --- | --- |
| Giới hạn đầu ra | Số request không trực tiếp biến thành số thông báo |
| Không khóa tài khoản theo lời khai | Người lạ không được làm nạn nhân mất quyền đăng nhập chỉ bằng yêu cầu recovery |
| Không lộ sự tồn tại của tài khoản | Phản hồi công khai không tiết lộ email có được đăng ký hoặc đã chạm hạn mức riêng hay không |
| Không hạ yêu cầu xác minh | Bị flood không phải lý do bỏ qua MFA hoặc đổi kênh khôi phục tùy ý |
| Bảo vệ cảnh báo quan trọng | Thông báo về thay đổi thật không bị bỏ vì hàng đợi thư yêu cầu đã đầy |
| Không kéo dài bí mật vô hạn | Yêu cầu bị gộp không tự gia hạn token hoặc mã |
| Có trạng thái gửi rõ ràng | Đã xếp hàng, nhà cung cấp đã nhận và người nhận đã nhận không phải cùng một việc |

OWASP nêu nguy cơ nhiều yêu cầu đặt lại mật khẩu làm ngập hộp thư hoặc SMS và khuyến nghị biện pháp chống tự động hóa, gồm giới hạn theo tài khoản. Tài liệu cũng yêu cầu phản hồi nhất quán để hạn chế dò tài khoản và không thay đổi tài khoản chỉ vì có yêu cầu chưa được xác minh. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Không có một ngưỡng số lượng duy nhất phù hợp cho mọi dịch vụ. Người dùng, giá gửi, loại tài khoản, phạm vi quốc gia và năng lực hỗ trợ đều ảnh hưởng lựa chọn.

## 4. Phân loại thông báo theo nguồn sự kiện và quyền hạn

Không dùng một bộ đếm duy nhất rồi tắt mọi thông báo khi bộ đếm hết.

| Lớp thông báo | Sự kiện kích hoạt | Cách kiểm soát |
| --- | --- | --- |
| Thông điệp khởi tạo recovery | Yêu cầu chưa xác minh từ biểu mẫu công khai | Giới hạn chặt theo người nhận, nguồn và chi phí |
| Gửi lại mã hoặc liên kết | Thao tác tiếp tục một luồng đang mở | Cooldown, chống lặp và kiểm tra trạng thái luồng |
| Nhắc việc chưa hoàn tất | Tác vụ theo lịch của hệ thống | Ít lần, có thời hạn, có thể gộp theo chính sách |
| Cảnh báo thay đổi thật | Mật khẩu đã đổi, recovery hoàn tất, authenticator được gắn | Đường gửi được bảo vệ, chống gửi trùng cùng sự kiện |
| Cảnh báo chiến dịch lạm dụng | Hệ thống phát hiện flood | Tổng hợp phù hợp, tránh biến cảnh báo thành đợt flood mới |

Lớp cảnh báo phải được xác định từ sự kiện nội bộ đáng tin cậy. Không cho request công khai tự đặt priority=CRITICAL để vượt hạn mức.

Phân biệt **gửi trùng một sự kiện** với **hai sự kiện khác nhau**. Hai bản sao của cùng sự kiện đổi mật khẩu có thể dùng một khóa chống trùng. Hai lần thay đổi authenticator độc lập không nên bị gộp mất chỉ vì diễn ra gần nhau.

NIST có yêu cầu thông báo độc lập đối với những sự kiện như khôi phục tài khoản và gắn authenticator. Khi áp dụng chính sách theo tiêu chuẩn này, cần bảo đảm đúng sự kiện và địa chỉ nhận theo yêu cầu; không dùng quy tắc chống flood để âm thầm bỏ thông báo bắt buộc. [Nguồn: NIST SP 800-63B-4, Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b.html#account-notifications).

Đường ưu tiên vẫn cần giới hạn tài nguyên và chống lỗi gửi lặp. Nó không phải một hàng đợi không giới hạn dành cho bất kỳ dữ liệu nào mang nhãn “bảo mật”.

## 5. Giới hạn theo nhiều chiều, đặc biệt là người nhận

### 5.1. Chặn theo IP là chưa đủ

Một botnet có thể gửi từ nhiều IP đến cùng một hộp thư. Ngược lại, nhiều người dùng thật có thể dùng chung IP tại văn phòng hoặc mạng di động.

Cần kết hợp những chiều phù hợp:

| Chiều kiểm soát | Ví dụ phạm vi | Điều nó giúp ngăn |
| --- | --- | --- |
| Nguồn request | IP, phiên công khai, tín hiệu thiết bị | Một nguồn tự động tạo nhiều yêu cầu |
| Tài khoản | ID nội bộ và loại luồng recovery | Đổi tên đăng nhập hoặc endpoint để nhắm cùng tài khoản |
| Đích nhận | Email, số điện thoại hoặc thiết bị push được phép | Flood từ nhiều nguồn vào cùng một đích |
| Kênh | SMS, email, voice, push | Dùng nhiều API cùng tạo ra đầu ra trên một kênh |
| Nhóm hành động | Các endpoint có chung tác động gửi | Đổi từ “quên mật khẩu” sang “gửi lại MFA” để né giới hạn |
| Tenant | Phạm vi tổ chức | Một tenant tiêu thụ hết khả năng gửi chung |
| Toàn hệ thống | Ngân sách gửi và chi phí | Chiến dịch phân tán qua nhiều tài khoản |

Nếu nhiều tài khoản dùng chung một số điện thoại hoặc hộp thư, chỉ giới hạn theo account_id có thể chưa bảo vệ được người nhận. Nếu một đích xuất hiện ở nhiều tenant, có thể cần một lớp bảo vệ tổng ở hạ tầng gửi; lớp này không được tiết lộ tài khoản hoặc quan hệ giữa các tenant cho nhau.

### 5.2. Xác định đích nhận một cách an toàn

Với luồng đang khôi phục tài khoản, đích nhận phải đến từ thông tin được phép của tài khoản hoặc quy trình xác minh đã được phê duyệt. Không biến trường destination trong request thành quyền gửi recovery secret đến địa chỉ bất kỳ.

Chuẩn hóa định danh theo quy tắc của hệ thống. Không tự xóa dấu chấm hoặc phần sau dấu cộng của mọi địa chỉ email: các nhà cung cấp có thể có quy tắc khác nhau. Việc chuẩn hóa quá mức có thể gộp hai người khác nhau; chuẩn hóa thiếu có thể cho phép né hạn mức.

Có thể dùng HMAC với khóa bí mật để tạo khóa đếm từ đích đã chuẩn hóa, thay vì đặt email hoặc số điện thoại rõ trong tên khóa. Đây vẫn là dữ liệu có thể liên kết cần được kiểm soát; HMAC không biến mọi dữ liệu thành vô danh. Hash thuần của số điện thoại hoặc email dễ đoán có thể bị dò ngược bằng danh sách ứng viên.

Đừng đưa khóa người nhận vào nhãn metric có số lượng giá trị quá lớn. Hệ thống quan sát cũng có thể bị quá tải bởi cách ghi số liệu.

## 6. Cooldown, ngân sách và chống đẩy lùi thời gian chờ

### 6.1. Cooldown phải dựa trên việc được cấp quyền gửi

Một chính sách minh họa có thể cho phép một thông điệp khởi tạo mỗi hai phút đến một đích, đồng thời đặt trần ba thông điệp trong ba mươi phút. Đây chỉ là số liệu để giải thích, không phải cấu hình khuyến nghị.

Với khoảng thời gian [0, 600) giây, cooldown hai phút tự nó có thể cho phép gửi tại giây 0, 120, 240, 360 và 480. Trần ba lần trong ba mươi phút sẽ giới hạn thêm tổng số được cấp trong khoảng đó.

Cần xác định rõ “một lần” tính theo:

- Một quyền gửi được cấp.
- Một thông báo logic.
- Một lần thử gọi nhà cung cấp.
- Hay một tin thực tế được nhà cung cấp tính phí.

Các lớp này có liên hệ nhưng không đồng nhất. Retry của một thông báo logic vẫn có thể tạo thêm chi phí hoặc thêm bản tin nếu nhà cung cấp không chống trùng.

### 6.2. Không gia hạn cooldown bởi mọi request bị chặn

Nếu nextEligibleAt luôn được đặt thành “bây giờ cộng hai phút” mỗi khi có request, kẻ tấn công chỉ cần gửi liên tục để nạn nhân không bao giờ hết thời gian chờ.

Nên phân biệt:

- Request bị chặn hoặc được gộp: không tự đẩy lùi thời điểm được phép gửi tiếp.
- Quyền gửi mới được cấp: cập nhật cooldown theo quy tắc.
- Quyết định hạn chế thêm do chiến dịch lạm dụng: có lý do, thời hạn và đường phục hồi riêng.

Ngay cả cooldown cố định cũng không bảo đảm người dùng thật luôn nhận được lượt gửi kế tiếp: kẻ tấn công có thể tiếp tục cạnh tranh ngân sách công khai. Cần đường tiếp tục dựa trên bằng chứng đã thiết lập hoặc hỗ trợ được xác minh, không chỉ tăng số lần gửi.

### 6.3. Bộ đếm phải chịu được nhiều instance

Logic “đọc số lần gửi, nếu còn thì tăng” có thể cấp nhiều lượt vượt trần khi request đến đồng thời.

Cơ chế cấp quyền gửi cần có tính nguyên tử phù hợp tại nguồn trạng thái dùng chung. Khi kết hợp nhiều ngân sách, phải giải quyết việc giữ chỗ, trừ hạn mức, hủy giữ chỗ và phục hồi sau lỗi; không giả định nhiều lệnh độc lập là một giao dịch.

Giới hạn theo IP tại gateway và giới hạn theo người nhận tại dịch vụ có thể là hai lớp độc lập. Tuy nhiên, kết quả đọc từ cache cũ không nên là căn cứ duy nhất cho việc cấp quyền gửi đến đích đã bị nhắm tới.

## 7. Gộp yêu cầu mà không phá vòng đời recovery

Nhiều lần bấm gửi không nhất thiết cần tạo nhiều challenge hoặc nhiều email.

Trong một khoảng chống lặp, hệ thống có thể giữ một thông báo đang chờ cho cùng đích và cùng luồng. Các request sau chỉ được ghi nhận là đã gộp. Điều đó không đồng nghĩa tất cả request có quyền đọc token, đổi đích nhận hoặc thay đổi challenge đang tồn tại.

Các quy tắc quan trọng:

- Yêu cầu bị chặn không tự làm token đang hợp lệ mất hiệu lực.
- Yêu cầu được gộp không tự gia hạn expires_at.
- Nếu cấp token mới và thay token cũ, việc thay thế phải tuân thủ chính sách rõ ràng.
- Không tạo token mới cho mọi request rồi bỏ qua bước gửi vì hết hạn mức.
- Không gửi một thông điệp đã xếp hàng nếu token trong đó hết hiệu lực hoặc hồ sơ đã hoàn tất.
- Không trộn hai hành động khác nhau chỉ vì chúng có cùng địa chỉ nhận.

Một lỗi đặc biệt nguy hiểm là: mỗi request đều hủy link cũ, nhưng chỉ request đầu được phép gửi email. Khi đó, nạn nhân nhận link đã bị hủy bởi những request bị chặn sau nó.

Nếu muốn gửi lại chính token cũ, cần có thiết kế lưu bí mật cho phép thực hiện điều đó an toàn. Không thể dựng lại token rõ chỉ từ digest. Không chọn lưu token rõ trong log hoặc hàng đợi dùng chung chỉ để thuận tiện gửi lại.

## 8. Kiểm soát cả lúc tiếp nhận và lúc phát thông báo

~~~mermaid
flowchart TD
    A[Request công khai] --> B[Kiểm tra đầu vào và kiểm soát nguồn]
    B --> C[Đánh giá nội bộ theo đích và luồng]
    C --> D{Được cấp quyền gửi mới?}
    D -->|Không| E[Gộp hoặc hạn chế, giữ trạng thái recovery phù hợp]
    D -->|Có| F[Ghi challenge và thông báo logic nhất quán]
    F --> G[Outbox và hàng đợi có giới hạn]
    G --> H[Worker kiểm tra hiệu lực và ngân sách lần thử gửi]
    H --> I[Nhà cung cấp]
    E --> J[Phản hồi công khai theo chính sách thống nhất]
    F --> J
~~~

### 8.1. Tại cửa vào

Kiểm tra dữ liệu, chống tự động hóa và giới hạn nguồn trước khi thực hiện công việc đắt tiền. Sau đó đánh giá nội bộ việc gửi đến đích được phép.

CAPTCHA có thể được dùng theo rủi ro nhưng không phải bằng chứng sở hữu tài khoản, không thay thế hạn mức người nhận và không bảo vệ khỏi mọi botnet. Cần cân nhắc khả năng tiếp cận và đường tiếp tục phù hợp cho người dùng hợp lệ.

### 8.2. Tại hàng đợi

Hàng đợi cần có giới hạn kích thước, tuổi công việc và mức ưu tiên. Không xếp mọi request bị hạn chế thành công việc “gửi sau”; cách đó chỉ biến flood hiện tại thành đợt flood muộn hơn.

Với thư có token ngắn hạn, độ trễ hàng đợi phải nằm trong chính sách sử dụng token. Trước khi gửi, kiểm tra xem challenge còn hiệu lực, chưa hoàn tất và địa chỉ nhận còn phù hợp hay không.

Thông báo về thay đổi thật cần chính sách thời hạn và chuyển tiếp riêng. Không áp dụng quy tắc “token hết hạn thì bỏ thư” cho một cảnh báo không chứa token mà tổ chức vẫn có trách nhiệm chuyển đến người dùng.

### 8.3. Tại worker gửi

Worker cần thực thi quyền gửi được cấp, kiểm tra trạng thái công việc và kiểm soát số lần gọi nhà cung cấp. Đừng cho worker tự đổi sang địa chỉ mới hoặc kênh yếu hơn khi gặp giới hạn.

Giới hạn nội bộ không thay thế giới hạn của nhà cung cấp. Ví dụ, Amazon SES có hạn mức gửi và tốc độ gửi ở cấp tài khoản, với phạm vi theo Region. Các hạn mức đó không tự giới hạn số thư đến một nạn nhân cụ thể. [Nguồn: Amazon SES sending quotas](https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html).

## 9. Retry, chống trùng và trạng thái chuyển phát

### 9.1. Một thông báo logic có thể có nhiều lần thử

| Trạng thái minh họa | Điều đã biết | Điều chưa thể kết luận |
| --- | --- | --- |
| PENDING | Đã tạo công việc gửi | Chưa chắc đã gọi nhà cung cấp |
| SENDING | Worker đang xử lý một lần thử | Chưa biết nhà cung cấp đã nhận hay chưa |
| PROVIDER_ACCEPTED | Nhà cung cấp đã nhận yêu cầu | Chưa chắc đã đến thiết bị hoặc hộp thư |
| DELIVERED | Có tín hiệu chuyển phát tương ứng | Không chứng minh người dùng đã đọc hoặc đồng ý |
| FAILED_FINAL | Không tiếp tục theo chính sách hiện tại | Không có nghĩa được bỏ yêu cầu thông báo bắt buộc |
| UNKNOWN | Kết quả lần thử chưa xác định | Không được giả định là chưa gửi để gửi lại vô hạn |

Nếu timeout xảy ra sau khi nhà cung cấp đã nhận tin, retry có thể tạo bản tin thứ hai. Dùng khóa chống trùng của nhà cung cấp khi có và kiểm tra chính xác phạm vi, thời hạn bảo đảm của nó. Không tuyên bố gửi “đúng một lần” chỉ vì nội bộ có một event_id.

Worker cũng cần quyền sở hữu công việc có thời hạn, phục hồi sau crash và khóa chống trùng ổn định. Một consumer nhận cùng sự kiện hai lần không nên tự tạo hai thông báo logic.

### 9.2. Retry cần có giới hạn

Đặt số lần thử, thời gian tối đa, backoff và jitter phù hợp. Mỗi lần thử vật lý phải được tính vào kiểm soát tài nguyên và chi phí liên quan.

Không hoàn trả ngân sách như thể chưa gửi chỉ vì ứng dụng nhận timeout. Trong trạng thái chưa biết, xử lý theo chính sách thận trọng, đối chiếu trạng thái hoặc chờ kết quả trước khi tạo thêm tải.

Không retry tự động một địa chỉ sai vĩnh viễn. Với lỗi tạm thời, xem cả thời hạn challenge và khoảng chờ để tránh gửi mã đã hết hiệu lực. Với lỗi cấu hình hoặc tài khoản gửi, chuyển việc cho vận hành thay vì tạo vòng lặp nhanh.

Nếu nhận callback chuyển phát, xác minh nguồn, tính toàn vẹn và liên kết với đúng thông báo, tenant và nhà cung cấp. Callback gửi trùng phải được xử lý an toàn; dữ liệu callback không tự cho phép chuyển tài khoản sang trạng thái đã xác minh.

### 9.3. Không khuếch đại bằng chuyển kênh

Email chậm không phải lý do lập tức gửi thêm SMS, gọi thoại và push cho mọi request. Một yêu cầu có thể tạo nhiều lần gửi vật lý nếu thiết kế fan-out không được tính đến.

Chuyển kênh phải tuân thủ chính sách và chỉ dùng các kênh đã được phép. Nếu người dùng mất thiết bị MFA, không thể coi một số điện thoại mới khai báo là đích tin cậy chỉ vì kênh cũ không nhận thông báo.

## 10. Mã giả: tách quyết định gửi khỏi phản hồi công khai

Đây là mô hình để giải thích ranh giới trách nhiệm, không phải triển khai hoàn chỉnh.

~~~text
requestRecovery(input, sourceContext):
    validateSyntaxAndSize(input)
    applySourceAbuseControls(sourceContext)

    candidate = resolveRecoveryTargetInternally(input.identifier)

    if candidate is eligible:
        transaction:
            state = lockRecipientAndRecoveryState(candidate)

            if hasEquivalentPendingNotification(state):
                recordCoalescedRequest(state)
            else if mayReserveLocalNotificationBudget(state):
                reserveLocalNotificationBudget(state)
                challenge = obtainChallengeUnderPolicy(state)
                notification = createLogicalNotification(
                    challengeRef = challenge.id,
                    destinationRef = candidate.approvedDestinationRef,
                    class = RECOVERY_REQUEST
                )
                appendOutboxOnce(notification.id)

    return genericPublicResponse()
~~~

Các điều kiện phía máy chủ cần bao gồm đúng phạm vi tài khoản, đích được phép, trạng thái challenge, thời gian chờ và hạn mức liên quan. Những request không được gửi không tự làm thay đổi mật khẩu, MFA, passkey hoặc trạng thái đăng nhập.

Trong mô hình minh họa này, trạng thái người nhận, phần ngân sách cục bộ, challenge và outbox nằm trong ranh giới giao dịch có thể bảo đảm nhất quán. Nếu tách sang nhiều kho dữ liệu, phải có thiết kế giữ chỗ, hết hạn giữ chỗ và phục hồi rõ ràng; không gọi các bước rời rạc rồi coi là nguyên tử.

Ngân sách toàn hệ thống hoặc ngân sách của nhà cung cấp có thể do thành phần gửi quản lý riêng. Cần phân biệt nó với ngân sách thông báo logic đã giữ tại cửa vào:

~~~text
dispatchNotification(notificationId):
    notification = claimPendingWork(notificationId)

    if not stillSemanticallyValid(notification):
        recordNotSentReason(notification)
        return

    if not reserveProviderAttemptBudget(notification.channel):
        rescheduleWithinDeadlineOrEscalate(notification)
        return

    result = sendUsingStableMessageIdentity(notification)
    recordAttemptAndDeliveryState(notification, result)
~~~

Quyền gửi trong ví dụ không được làm lộ token. Outbox dùng tham chiếu; thành phần có quyền phù hợp mới dựng nội dung từ dữ liệu được bảo vệ. Nếu cần giữ bí mật để gửi bất đồng bộ, cơ chế lưu trữ, mã hóa, truy cập và thời hạn phải được thiết kế riêng.

Không cho request bên ngoài tự chọn lớp cảnh báo, khóa chống trùng, ngân sách hoặc đích nhận để vượt chính sách.

## 11. Phản hồi công khai và trải nghiệm người dùng

### 11.1. Tránh biến bộ giới hạn thành công cụ dò tài khoản

Một phản hồi có điều kiện phù hợp có thể là:

> Nếu thông tin phù hợp và việc gửi được phép, hướng dẫn khôi phục sẽ được chuyển qua kênh đã đăng ký. Nếu bạn vừa gửi yêu cầu, hãy chờ trước khi thử lại. Bạn cũng có thể mở trang trợ giúp chính thức để xem các phương thức khôi phục khả dụng.

Không trả về “Tài khoản này đã nhận ba SMS trong hôm nay” cho người chưa xác minh. Khác biệt về nội dung, mã phản hồi, header, thời gian hoặc khả năng xem trạng thái cũng có thể tiết lộ thông tin.

Có thể dùng lỗi giới hạn theo nguồn như HTTP 429 theo chính sách nhất quán trước bước đối chiếu tài khoản. Không suy ra rằng mọi endpoint phải luôn trả 202 hoặc luôn giấu mọi lỗi đầu vào. Điều cần tránh là phản hồi phụ thuộc bí mật vào sự tồn tại hoặc lịch sử gửi riêng của tài khoản.

Nếu sử dụng phản hồi chấp nhận bất đồng bộ, đừng khẳng định “Email đã được gửi thành công” khi hệ thống thực tế có thể đã gộp, hạn chế hoặc chưa gọi nhà cung cấp.

### 11.2. Giúp người dùng phân biệt yêu cầu với thay đổi đã xảy ra

Nội dung cần nói rõ thông báo đang báo:

- Có người yêu cầu khôi phục.
- Có một bước cần người dùng chủ động thực hiện.
- Hay tài khoản đã có thay đổi được hoàn tất.

Không dùng tiêu đề mơ hồ khiến thư yêu cầu khôi phục trông giống xác nhận tài khoản đã bị đổi mật khẩu. Tránh lời thúc ép “bấm đồng ý để chặn cuộc tấn công”.

Nếu người nhận không khởi tạo, hướng dẫn họ không chia sẻ mã, không phê duyệt yêu cầu lạ và tự mở ứng dụng hoặc website chính thức. Đường báo cáo sự cố phải tìm được mà không cần tin vào số điện thoại hoặc liên kết do người gọi lạ cung cấp.

### 11.3. Tạm giảm thông báo không được thành quyền tắt bảo mật

Người dùng đã xác minh có thể được cung cấp tùy chọn phù hợp với loại thông báo và chính sách. Không cho một request công khai hoặc một GET từ email tắt toàn bộ cảnh báo đổi mật khẩu, đổi MFA hoặc recovery.

Nút “Tôi không yêu cầu” cũng cần xác định rõ tác động. Nó có thể ghi nhận sự việc hoặc mở trang chính thức; nếu có thay đổi trạng thái, cần cơ chế cấp quyền tương ứng. Không để nút đó tự khóa tài khoản hoặc xóa mọi authenticator chỉ vì người bấm có bản sao email.

## 12. Bảo vệ khả năng khôi phục khi đang có flood

Chống flood có thể bị biến thành từ chối dịch vụ nếu chỉ đặt trần rồi bỏ người dùng thật ở ngoài.

Các hướng tiếp tục có thể gồm:

- Cho phép dùng một authenticator còn hoạt động để đi theo luồng được cấp quyền phù hợp.
- Sử dụng recovery code hoặc recovery contact đã thiết lập, theo chính sách của tài khoản.
- Cho phép tiếp tục challenge còn hợp lệ thay vì luôn buộc tạo challenge mới.
- Có quy trình hỗ trợ với bằng chứng và thẩm quyền rõ ràng.
- Hướng dẫn người dùng đang có phiên an toàn kiểm tra sự kiện và báo cáo lạm dụng.

Mỗi đường vẫn phải đáp ứng yêu cầu xác minh tương ứng. Không tạo ngoại lệ “vì bị flood nên bỏ qua MFA” hoặc “đổi sang email mới do người gọi cung cấp”.

Nếu bộ giới hạn bị lỗi, không tự chuyển sang gửi không giới hạn. Có thể từ chối việc gửi mới chưa được xác minh hoặc dùng cơ chế dự phòng có ngân sách giới hạn. Cảnh báo thay đổi thật cần đường giữ công việc, ưu tiên và tiếp quản phù hợp, thay vì bị bỏ cùng các thư khởi tạo.

Ngân sách dự phòng phải có trần. Đồng thời, cần phân bổ công bằng để một tenant hoặc một nhóm tài khoản không tiêu thụ toàn bộ đường ưu tiên.

Nếu có bằng chứng tài khoản đã bị chiếm, đội có thẩm quyền cần xử lý phiên và phương thức xác thực liên quan. Chỉ giảm số email không giải quyết được quyền truy cập trái phép đang tồn tại.

## 13. Ví dụ xuyên suốt: flood để che một cảnh báo thật

Nam bị nhắm tới bởi nhiều nguồn tự động. Chúng liên tục gọi các endpoint quên mật khẩu và gửi lại mã.

| Diễn biến | Hành vi thiết kế mong muốn |
| --- | --- |
| Request đầu được phép gửi | Tạo một challenge và một thông báo logic theo chính sách |
| Nhiều request tiếp theo đến trong cooldown | Gộp hoặc hạn chế, không hủy challenge đang dùng, không đẩy cooldown vô hạn |
| Kẻ tấn công đổi IP hoặc endpoint | Giới hạn chung theo đích và nhóm tác động tiếp tục áp dụng |
| Nhà cung cấp phản hồi timeout | Ghi trạng thái chưa rõ, không retry dồn dập hoặc tự fan-out sang mọi kênh |
| Nam mở link còn hợp lệ | Cho phép tiếp tục theo quyền của challenge, không bắt buộc gửi mã mới vô ích |
| Có sự kiện gắn authenticator thật trong lúc flood | Tạo cảnh báo riêng từ sự kiện nội bộ, không gộp vào thư yêu cầu khôi phục |
| Nam báo không nhận ra thay đổi | Chuyển sang quy trình điều tra và xác minh, không chỉ tăng hạn mức gửi |

Ở bước cảnh báo thay đổi thật, hệ thống cần biết rõ đó là sự kiện đã commit, không phải chỉ một yêu cầu của người lạ. Ngân sách dành cho thư khởi tạo không được làm mất cảnh báo này.

Trong một biến thể, kẻ tấn công gọi điện cho Nam và nói: “Đọc OTP cho tôi để dừng tin nhắn”. Thông điệp hướng dẫn an toàn và kênh hỗ trợ chính thức phải giúp Nam nhận ra rằng chia sẻ OTP không phải cách chấm dứt flood.

## 14. Theo dõi hiệu quả và điều tra

### 14.1. Đo từng tầng

| Chỉ số | Câu hỏi nó trả lời |
| --- | --- |
| Số request theo nguồn và nhóm hành động | Có hoạt động tự động hoặc né endpoint không? |
| Số quyền gửi được cấp | Chính sách đầu vào đã cho phép bao nhiêu thông báo logic? |
| Số request được gộp hoặc hạn chế | Bao nhiêu tác động gửi đã được ngăn? |
| Số lần thử gọi nhà cung cấp | Retry có làm tăng tải và chi phí không? |
| Số thông báo được nhận bởi nhà cung cấp, chuyển phát hoặc lỗi | Công việc tiến triển đến đâu? |
| Số thông báo thực tế trên một đích trong khoảng thời gian | Người nhận có còn bị flood không? |
| Độ trễ cảnh báo thay đổi thật | Flood có che hoặc làm chậm sự kiện quan trọng không? |
| Mức hoàn tất recovery của người dùng hợp lệ | Biện pháp chống lạm dụng có gây mắc kẹt không? |

Không chỉ nhìn tỷ lệ request bị chặn cao rồi kết luận thành công. Hệ thống có thể đang chặn gần như mọi người dùng thật hoặc vẫn gửi quá nhiều bản tin do worker retry.

Khi diễn giải số liệu chuyển phát, phân biệt những gì nhà cung cấp có thể báo và những gì ứng dụng thực sự biết. Với một số kênh, không thể đo chắc chắn việc người dùng đã đọc.

### 14.2. Nhật ký đủ để giải thích quyết định

Một sự kiện nội bộ tối giản:

~~~json
{
  "eventType": "RECOVERY_NOTIFICATION_DECISION",
  "notificationClass": "RECOVERY_REQUEST",
  "decision": "COALESCED",
  "reason": "EQUIVALENT_PENDING_MESSAGE",
  "requestId": "request_example_81",
  "notificationId": "notification_example_14",
  "policyVersion": "example-policy-v3",
  "accountMutationApplied": false
}
~~~

Không ghi OTP, recovery token, raw recovery URL hoặc toàn bộ nội dung nhạy cảm vào log. Khi cần đối chiếu người nhận, dùng định danh nội bộ có kiểm soát truy cập và thời hạn lưu phù hợp.

Nhật ký nên giải thích được thông báo bị hạn chế bởi chính sách nào, có bị đẩy sang hàng đợi hay không, lần gửi nào đang chưa rõ và cảnh báo quan trọng đã được tiếp quản thế nào.

Nếu phát hiện chiến dịch flood, tránh gửi một email cảnh báo cho mỗi request bị chặn. Có thể tổng hợp sự kiện cùng chiến dịch theo chính sách, đồng thời vẫn giữ các thông báo riêng bắt buộc về thay đổi tài khoản.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ giới hạn theo IP | Nhiều nguồn vẫn dội được cùng một người nhận | Kết hợp hạn mức đích, tài khoản và nhóm tác động |
| Mỗi request bị chặn vẫn hủy token cũ | Người dùng nhận link không dùng được | Quyết định cấp và thay challenge gắn với chính sách gửi |
| Mọi request đều kéo dài cooldown | Kẻ xấu giữ nạn nhân chờ vô hạn | Không đẩy thời điểm đủ điều kiện bởi request bị gộp |
| Xếp mọi request vào hàng đợi gửi sau | Tạo flood muộn và mã hết hạn | Hạn chế ngay từ đầu, gộp và đặt tuổi công việc |
| Retry ngay khi timeout | Có thể gửi trùng và tăng chi phí | Quản lý trạng thái chưa rõ, backoff và chống trùng |
| Dùng chung một trần cho mọi loại thông báo | Cảnh báo đổi MFA thật bị mất | Phân lớp và bảo vệ yêu cầu thông báo quan trọng |
| Cho client tự chọn mức ưu tiên | Kẻ xấu đi vòng qua giới hạn | Phân loại từ sự kiện nội bộ đáng tin |
| Nhà cung cấp có quota nên bỏ limiter nội bộ | Một nạn nhân vẫn bị gửi rất nhiều | Bảo vệ theo đích và tác động nghiệp vụ |
| Tự đổi sang số điện thoại mới khi kênh cũ bị flood | Tạo đường vòng chiếm đoạt recovery | Giữ yêu cầu xác minh khi chuyển kênh |
| Báo đã gửi khi chỉ enqueue hoặc bị hạn chế | Người dùng hiểu sai trạng thái | Phản hồi phù hợp với mức thông tin thực sự có |

Ngăn notification flooding là quản lý đầu ra và vòng đời công việc gửi, đồng thời giữ nguyên ranh giới xác minh của tài khoản. Một thiết kế tốt giảm được thông báo gây hại mà vẫn duy trì cảnh báo về thay đổi thật và đường khôi phục có kiểm soát.

## Tài liệu tham khảo

- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): flood từ yêu cầu đặt lại mật khẩu, chống tự động hóa và phản hồi tránh dò tài khoản.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): giới hạn push ngoài băng, authentication fatigue và thông báo tài khoản.
- [Amazon SES — Managing sending quotas](https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html): ví dụ về hạn mức và tốc độ gửi ở lớp nhà cung cấp.
