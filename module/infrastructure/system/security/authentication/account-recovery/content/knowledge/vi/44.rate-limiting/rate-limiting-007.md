# Rate limit user feedback: Phản hồi khi người dùng bị giới hạn tần suất khôi phục

Rate limiting trong khôi phục tài khoản có thể chặn gửi yêu cầu, gửi lại mã, thử OTP hoặc gọi một bước xác minh quá nhiều lần. Người dùng bị giới hạn có thể đang mất mật khẩu, điện thoại, MFA hoặc passkey và không biết phải làm gì tiếp theo.

Phản hồi tốt cần giúp họ hiểu **thao tác nào đang tạm dừng, khi nào có thể thử lại và còn lựa chọn an toàn nào**. Đồng thời, phản hồi không được tiết lộ sự tồn tại của tài khoản, nội dung chính sách chống lạm dụng hoặc bí mật xác thực.

Bài học tập trung vào hợp đồng phản hồi giữa backend, frontend và người dùng. Các mã ứng dụng, trường JSON, thời gian chờ và mẫu câu dưới đây là ví dụ thiết kế; không phải cấu hình bắt buộc cho mọi dịch vụ.

## 1. Giới hạn tần suất không đồng nghĩa tài khoản bị khóa

Cần phân biệt các trạng thái có thể trông giống nhau trên giao diện:

| Tình trạng | Ý nghĩa | Người dùng cần biết |
| --- | --- | --- |
| Giới hạn tạo yêu cầu | Chưa được gửi thêm một yêu cầu khôi phục | Cần chờ trước khi thử lại thao tác này |
| Giới hạn gửi lại mã | Chưa được gửi thêm thông báo hoặc mã | Không nhất thiết phải dừng nhập mã hiện có |
| Giới hạn thử mã tạm thời | Bước xác minh đang tạm dừng | Khi nào có thể thử lại, nếu biết |
| Challenge hết lượt hoặc bị hủy | Challenge hiện tại không còn dùng được | Chờ đơn thuần có thể không khôi phục challenge |
| Flow hết hạn | Hành trình khôi phục hiện tại đã hết hiệu lực | Cần quay lại điểm bắt đầu phù hợp |
| Lỗi dịch vụ tạm thời | Hệ thống chưa thể xử lý | Đây không phải lời kết luận rằng người dùng đã gửi quá nhiều |
| Tài khoản bị hạn chế vì sự cố bảo mật | Có một quyết định bảo mật riêng | Cần đi theo quy trình được phép thay vì chỉ đợi bộ đếm |

Nếu backend chỉ chặn nút “Gửi lại mã”, không nên hiển thị “Tài khoản của bạn đã bị khóa”. Câu đó làm người dùng hiểu sai phạm vi tác động và có thể tìm đến hỗ trợ giả mạo vì tưởng không còn đường khôi phục.

Cũng không nên khẳng định “Bạn đã nhập sai quá nhiều lần” nếu request bị chặn trước khi hệ thống kiểm tra mã. Phản hồi cần phản ánh điều hệ thống thực sự biết.

## 2. Một thông báo hữu ích có bốn thành phần

Một mẫu thông báo nên trả lời:

1. **Trạng thái hiện tại:** chưa thể thực hiện thao tác.
2. **Phạm vi:** gửi yêu cầu, gửi lại mã hay thử xác minh.
3. **Thời gian:** khoảng chờ trước lần thử tiếp theo, nếu có thông tin đáng tin cậy.
4. **Bước tiếp theo:** chờ, dùng bước hiện tại còn hợp lệ hoặc tìm hỗ trợ chính thức.

Ví dụ cho thao tác gửi lại mã:

> Hiện chưa thể gửi thêm mã. Bạn có thể thử gửi lại sau ít nhất 60 giây. Nếu mã hiện có vẫn còn hiệu lực, bạn có thể tiếp tục nhập mã đó.

Chỉ dùng câu cuối nếu hệ thống thực sự cho phép tiếp tục xác minh và giao diện có quyền hiển thị trạng thái tương ứng. Giới hạn gửi thông báo và giới hạn thử mã là hai chính sách riêng.

Ví dụ khi chưa có thời điểm thử lại đáng tin cậy:

> Hiện chưa thể xử lý thêm lần xác minh này. Vui lòng thử lại sau hoặc mở mục Trợ giúp khôi phục từ ứng dụng hay website chính thức.

Không hiển thị một đồng hồ 60 giây chỉ vì sản phẩm cần có bộ đếm. Một thời gian bịa ra khiến người dùng tiếp tục bị chặn ngay khi đồng hồ về 0.

### Dùng giọng điệu trung tính

Có thể nhiều người cùng dùng một mạng hoặc một nguồn đang bị hạn chế. Câu “Bạn đang tấn công hệ thống” hoặc “Bạn đã vi phạm chính sách” không phù hợp chỉ từ một quyết định rate limit.

Nên nói về khả năng thực hiện hành động: “Chưa thể gửi thêm yêu cầu”. Giữ giải thích dài hơn trong mục có thể mở rộng, thay vì bắt người dùng đọc toàn bộ cơ chế chống lạm dụng.

## 3. Không biến phản hồi thành công cụ dò tài khoản

Một thiết kế có thể dùng cùng câu “Vui lòng thử lại sau” nhưng vẫn để lộ thông tin qua HTTP status, header hoặc thời gian xử lý.

Ví dụ có vấn đề:

~~~text
Email tồn tại, đã đạt giới hạn theo tài khoản:
  429 + Retry-After: 600

Email không tồn tại:
  202, không có Retry-After
~~~

Người gửi không cần đọc câu thông báo để phân biệt hai trường hợp.

OWASP khuyến nghị phản hồi yêu cầu đặt lại mật khẩu nhất quán cho tài khoản tồn tại và không tồn tại, đồng thời tránh chênh lệch thời gian xử lý làm lộ thông tin. [OWASP Forgot Password: Yêu cầu đặt lại mật khẩu](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

### Tách giới hạn công khai và giới hạn nội bộ theo đích

Một lựa chọn thiết kế là phân biệt:

- **Giới hạn theo nguồn hoặc thao tác công khai:** áp dụng mà không phụ thuộc tài khoản đích có tồn tại hay không. Có thể trả phản hồi giới hạn thống nhất.
- **Giới hạn nội bộ theo tài khoản hoặc kênh nhận:** có thể ngăn phát thêm thông báo, nhưng không làm phản hồi công khai đổi theo sự tồn tại hoặc hoạt động của tài khoản.
- **Trạng thái trong ngữ cảnh khôi phục đã được cho phép:** có thể cung cấp thông tin phù hợp với quyền xem trạng thái mà người dùng đã chứng minh.

Ví dụ, endpoint tiếp nhận công khai có thể trả `202` với cùng thông báo có điều kiện dù hệ thống quyết định không gửi thêm email cho một đích đang bị hạn chế. Đây là xác nhận tiếp nhận để xử lý, không phải xác nhận đã gửi hoặc đã giao thông báo.

Mẫu câu:

> Nếu thông tin phù hợp và yêu cầu đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.

Không hiển thị “Email đã được gửi thành công” nếu dịch vụ chỉ mới tiếp nhận yêu cầu hoặc đã chủ động không gửi thêm.

Nếu giới hạn theo nguồn bị vượt, `429` cần được áp dụng nhất quán cho các đích theo cùng chính sách công khai. Không dùng nó như nhãn để phân biệt tài khoản có thật.

Có `flowId` hoặc cookie do trình duyệt nhận được chưa tự chứng minh quyền biết tài khoản đích tồn tại. Quyết định tiết lộ chi tiết phải dựa trên quyền của ngữ cảnh đó, không chỉ trên việc đã chuyển sang trang thứ hai.

## 4. Hợp đồng HTTP cho phản hồi giới hạn

HTTP `429 Too Many Requests` mô tả tình trạng có quá nhiều request trong một khoảng thời gian. RFC 6585 khuyến nghị nội dung phản hồi giải thích tình trạng và cho phép gửi `Retry-After`. [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Ví dụ cho một giới hạn công khai không phụ thuộc sự tồn tại của tài khoản:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 60

{
  "code": "RECOVERY_REQUEST_THROTTLED",
  "message": "Hiện chưa thể gửi thêm yêu cầu. Vui lòng chờ trước khi thử lại.",
  "action": "REQUEST_RECOVERY",
  "retryAfterSeconds": 60,
  "correlationId": "req-example-007"
}
~~~

Trong hợp đồng minh họa:

- `code` là mã ổn định để client xử lý.
- `message` là nội dung hiển thị đã được kiểm soát.
- `action` xác định đúng thao tác đang bị hạn chế.
- `retryAfterSeconds` dùng cùng quyết định với header, không tính lại độc lập theo một chính sách khác.
- `correlationId` hỗ trợ tra cứu; nó không có quyền xác thực.

Không trả `accountExists`, khóa bộ đếm nội bộ, đầy đủ địa chỉ nhận, số lượt sai của người khác hoặc lý do chi tiết của bộ phát hiện lạm dụng.

`Cache-Control: no-store` được đặt rõ trong ví dụ để hạn chế lưu lại phản hồi nhạy cảm. Cấu hình gateway và cache phải phù hợp với hợp đồng recovery, tránh dùng một trang chặn của người này cho người khác.

### Khi không nên dùng 429

Nếu hệ thống lỗi hoặc quá tải tạm thời, `503 Service Unavailable` có thể phù hợp hơn với bản chất sự cố. Không đổi mọi lỗi backend thành `429` rồi đổ nguyên nhân cho người dùng.

Nếu một challenge đã kết thúc và sẽ không được mở lại sau thời gian chờ, phản hồi cần mô tả trạng thái bước xác minh theo hợp đồng ứng dụng. Không gắn `Retry-After: 60` để ngụ ý challenge sẽ hồi sinh.

Các trạng thái khác nhau có thể dùng mẫu giao diện tương tự, nhưng mã ứng dụng và bước tiếp theo phải đúng.

## 5. Diễn giải Retry-After chính xác

`Retry-After` có thể chứa số giây chờ không âm hoặc một HTTP-date. RFC 9110 định nghĩa đây là thời gian client nên chờ trước request tiếp theo; nó cũng mô tả cách dùng header với phản hồi `503`. [RFC 9110, mục 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

Ví dụ:

~~~http
Retry-After: 60
~~~

Giá trị này là 60 giây, không phải 60 mili giây. Với dạng số giây, client tính khoảng chờ từ lúc nhận phản hồi.

Có ba điểm quan trọng cho nội dung hiển thị:

1. Thời gian chờ không phải thời hạn OTP.
2. Hết thời gian chờ không bảo đảm request tiếp theo sẽ được chấp nhận.
3. Thời gian chờ không kéo dài flow, token hoặc challenge đã được phát hành.

Vì vậy, nên dùng “Có thể thử lại sau…” thay vì “Tài khoản chắc chắn được mở khóa sau…”.

Nếu đồng thời có nhiều giới hạn đang có hiệu lực và có thể tính thời điểm thử lại, máy chủ cần đưa ra khoảng chờ phù hợp với các giới hạn đang chặn thao tác đó. Không chọn thời điểm ngắn nhất rồi hiển thị như đã hết mọi hạn chế.

Khi vẫn có điều kiện rủi ro không xác định được thời gian kết thúc, không hứa một thời điểm chính xác. Có thể cung cấp hướng dẫn chờ hoặc đường hỗ trợ thay vì một giá trị đếm ngược gây hiểu nhầm.

## 6. Bộ đếm trên giao diện là hướng dẫn, không phải quyền truy cập

Frontend có thể mô hình hóa trạng thái:

~~~text
READY
  |
  | người dùng chọn gửi
  v
SUBMITTING
  |                         |
  | phản hồi giới hạn       | tiếp nhận yêu cầu
  v                         v
WAITING                  ACCEPTED
  |
  | hết khoảng chờ cục bộ
  v
READY_TO_RETRY
~~~

`READY_TO_RETRY` chỉ nói giao diện cho phép thử lại. Backend vẫn phải kiểm tra giới hạn và trạng thái khôi phục trên mỗi request.

Không mở quyền xác minh chỉ vì trình duyệt đã đếm đủ giây. Đổi giờ máy, tải lại trang hoặc gọi API trực tiếp không được vô hiệu hóa quyết định phía máy chủ.

### Tính thời gian mà không tạo kỳ vọng sai

Với khoảng chờ dạng số giây:

~~~text
receivedAt = monotonicNow()
waitMs = retryAfterSeconds * 1000

remainingMs = max(
    0,
    waitMs - (monotonicNow() - receivedAt)
)

displaySeconds = ceil(remainingMs / 1000)
~~~

Đây là phác thảo cho khoảng chờ trong một phiên giao diện; cần xử lý giá trị không hợp lệ và tràn số trong triển khai.

Dùng nguồn thời gian đơn điệu giúp hạn chế ảnh hưởng của việc đổi giờ hệ thống trong cùng phiên. Không coi một mốc thời gian đơn điệu lưu lại là có thể dùng nguyên vẹn sau khi tải lại trang hoặc chuyển tiến trình.

Với HTTP-date, client phải xử lý ngày giờ đúng và cân nhắc độ lệch đồng hồ, có thể dựa thêm vào thời gian máy chủ theo hợp đồng. Không dùng thời gian cục bộ thiếu tin cậy để bảo đảm rằng hạn chế đã hết.

Khi ứng dụng được mở lại hoặc trở về từ trạng thái nền, đồng hồ hiển thị cần được tính lại phù hợp. Có thể đối chiếu trạng thái qua cơ chế được phép, nhưng không thăm dò liên tục chỉ để cập nhật từng giây.

### Chỉ hạn chế đúng hành động

Nếu đang chờ gửi lại mã, ô nhập mã có thể vẫn dùng được theo chính sách hiện hành. Nếu bước xác minh bị giới hạn, không để nút gửi OTP liên tục hoạt động như một lối thoát không được thiết kế.

Không xóa toàn bộ dữ liệu biểu mẫu hoặc bắt người dùng lập lại hồ sơ chỉ vì một lần gặp `429`. Với bí mật như mật khẩu hay OTP, việc giữ dữ liệu trong bộ nhớ giao diện cần theo chính sách bảo vệ dữ liệu; không đưa chúng vào lưu trữ lâu dài chỉ để tiện tiếp tục.

## 7. Không để cơ chế retry làm tăng lạm dụng

Một client tự gửi lại request mỗi giây trong khi hiển thị “Vui lòng chờ” làm hệ thống chịu thêm tải và có thể kéo dài tình trạng bị hạn chế.

Với thao tác có tác dụng phụ như gửi email, SMS hoặc tạo hồ sơ khôi phục, lựa chọn mặc định hợp lý thường là chờ người dùng chủ động thử lại. Không tự động gửi một mã mới ngay khi bộ đếm về 0 nếu người dùng chưa yêu cầu.

Nếu có retry tự động được thiết kế rõ, có thể dùng nguyên tắc:

~~~text
waitMs = max(serverSuggestedDelayMs, localBackoffMs)
         + nonNegativeJitterMs
~~~

Cách này không cố tình gửi sớm hơn khoảng chờ hợp lệ của máy chủ. Client cần giới hạn số lần retry và tổng thời gian, đồng thời hủy tác vụ khi người dùng rời hành trình.

Nếu máy chủ yêu cầu chờ lâu hơn giới hạn mà client hỗ trợ tự động, dừng tự retry và hiển thị hướng dẫn. Không cắt ngắn khoảng chờ để tiếp tục gửi sớm.

### Timeout khác với bị từ chối rõ ràng

Khi nhận phản hồi giới hạn trước tác vụ, client xử lý theo hợp đồng rằng lần thử chưa được thực hiện. Khi mất kết nối hoặc timeout, client có thể chưa biết tác vụ đã xảy ra hay chưa.

Không hiển thị “Chưa gửi mã” chỉ từ việc không nhận được phản hồi. Không tạo yêu cầu mới ngay lập tức để bù cho một kết quả chưa rõ.

Một dịch vụ có thể cung cấp idempotency hoặc trạng thái thao tác gắn với đúng ngữ cảnh khôi phục để xử lý trường hợp này. Việc lấy lại kết quả không được cấp quyền cho người chỉ biết mã tra cứu hoặc làm lộ sự tồn tại của tài khoản.

## 8. Phản hồi khi flow hoặc mã hết hạn trong lúc chờ

Ví dụ minh họa:

~~~text
12:00:00  Phát hành một mã, thời hạn tới 12:03:00.
12:02:30  Bước xác minh bị tạm dừng; khoảng chờ là 60 giây.
12:03:30  Giao diện hết khoảng chờ.
~~~

Lúc đó, mã cũ đã hết hạn. Không thể chỉ bật lại nút xác minh và nói “Bây giờ mã đã dùng được”.

Cần phân biệt các đồng hồ:

| Đồng hồ | Điều nó chi phối |
| --- | --- |
| Chờ gửi lại | Khi nào có thể thử yêu cầu phát thông báo tiếp theo |
| Chờ thử xác minh | Khi nào có thể thử gửi bằng chứng tiếp theo |
| Hết hạn mã/token | Bằng chứng hiện tại có còn được chấp nhận không |
| Hết hạn flow | Hành trình hiện tại có còn hiệu lực không |
| Thời gian xử lý hỗ trợ | Khi nào hồ sơ dự kiến được xem xét, nếu có cam kết |

Nếu có quyền hiển thị trạng thái challenge, giao diện có thể thông báo:

> Mã của bước này đã hết hạn. Khi có thể yêu cầu mã mới, hãy dùng chức năng Gửi lại mã để tiếp tục.

Câu đó chỉ phù hợp nếu flow còn hiệu lực và có hỗ trợ phát mã mới. Nếu flow cũng đã hết hạn, cần hướng về điểm bắt đầu chính thức.

Không tự kéo dài hiệu lực OTP hoặc đặt lại ngân sách thử chỉ để đồng bộ với bộ đếm giao diện. Điều chỉnh trải nghiệm phải đi cùng chính sách bảo mật phía máy chủ.

## 9. Khả năng tiếp cận và bản địa hóa

Người dùng công cụ hỗ trợ cần biết rằng hành động chưa thể thực hiện và khi nào trạng thái thay đổi. WCAG 2.2 mô tả yêu cầu để status message có thể được công nghệ hỗ trợ nhận biết mà không nhất thiết chuyển focus. [W3C: Hiểu tiêu chí 4.1.3 về status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

Áp dụng vào phản hồi giới hạn:

- Đặt thông báo gần hành động liên quan và có liên kết ngữ nghĩa phù hợp.
- Dùng vùng thông báo trạng thái thích hợp; không chỉ đổi màu nút.
- Thông báo khi bắt đầu chờ và khi có thể thử lại; tránh đọc lại từng giây qua screen reader.
- Không tự chuyển focus hoặc mở hộp thoại lặp lại mỗi lần bộ đếm cập nhật.
- Giữ đường truy cập bằng bàn phím đến trợ giúp và các hành động còn khả dụng.
- Nếu một nút bị vô hiệu hóa, giải thích nguyên nhân bằng nội dung vẫn đọc được.

Mẫu nội dung tĩnh:

> Hiện chưa thể gửi lại mã. Thời gian chờ còn khoảng một phút.

Mẫu khi hoàn tất khoảng chờ cục bộ:

> Bạn có thể thử gửi lại mã.

Không dùng “Đã gửi mã mới” cho trạng thái chỉ vừa cho phép thử lại.

Về bản địa hóa, nên có mã lỗi ổn định và chuỗi dịch theo ngữ cảnh. Tránh ghép các mảnh câu khiến số ít/số nhiều hoặc thứ tự từ sai. Hiển thị đơn vị thời gian rõ ràng; nếu dùng thời điểm tuyệt đối, cần chỉ rõ múi giờ hoặc diễn giải theo giao diện địa phương.

Không bắt người dùng tìm hiểu các từ như `token bucket`, `quota key` hoặc `risk score` để hiểu phải làm gì. Những chi tiết đó thuộc vận hành nội bộ.

## 10. Giữ hợp đồng nhất quán qua gateway và các kênh

Phản hồi có thể phát sinh ở CDN, API gateway, dịch vụ recovery hoặc hệ thống gửi thông báo. Nếu các lớp đưa ra các thông điệp khác nhau, người dùng sẽ gặp tình huống nút ghi “thử lại sau 30 giây” nhưng trang lỗi lại yêu cầu chờ 10 phút.

Cần thống nhất:

~~~text
quyết định hạn chế
    -> phạm vi hành động
    -> mã phản hồi công khai
    -> thời gian chờ có thể công bố
    -> nội dung theo ngôn ngữ
    -> hành động tiếp theo được phép
~~~

Header và body nên được tạo từ cùng một quyết định. Nếu hạ tầng chỉ trả HTML thay vì JSON, client phải có phản hồi dự phòng an toàn thay vì lỗi phân tích dữ liệu hoặc màn hình trống.

Không hiển thị nguyên body kỹ thuật từ upstream cho người dùng. Nội dung đó có thể chứa khóa nội bộ, đường dẫn hệ thống hoặc lý do chặn không phù hợp để công khai.

Một request bị gateway từ chối có thể chưa tới dịch vụ recovery. Hệ thống theo dõi cần phân biệt điều này để nhân viên không kết luận người dùng đã thử sai OTP chỉ vì thấy nhiều `429`.

Ứng dụng web, di động và hỗ trợ khách hàng nên dùng cùng khái niệm về thời gian chờ. Nhân viên không nên khuyên “bấm gửi lại liên tục” trong khi giao diện đang yêu cầu dừng.

## 11. Đường hỗ trợ cho người đã mất phương thức xác thực

Người dùng đang khôi phục có thể không đăng nhập được để mở mục hỗ trợ thông thường. Nếu thông báo giới hạn chỉ dẫn “hãy đăng nhập để liên hệ”, họ có thể rơi vào vòng lặp.

Một đường trợ giúp phù hợp cần:

- Có điểm vào chính thức có thể tìm được khi chưa đăng nhập.
- Giải thích các lựa chọn phù hợp với việc mất mật khẩu, MFA, passkey hoặc thiết bị.
- Thu thập thông tin tối thiểu cần thiết cho hồ sơ.
- Không yêu cầu người dùng gửi OTP, mã dự phòng hoặc liên kết khôi phục qua chat.
- Không tự bỏ yêu cầu xác minh chỉ vì người dùng đang bị rate limit.

Không yêu cầu chuyển sang một kênh yếu hơn chỉ để né thời gian chờ. Một phương thức thay thế phải đáp ứng chính sách khôi phục riêng, có giới hạn và kiểm soát rủi ro phù hợp.

Với người dùng đang dùng chung mạng, hướng dẫn không nên là “đổi IP để vượt giới hạn”. Nên cung cấp khoảng chờ, cách tiếp tục an toàn hoặc kênh xem xét tình trạng hạn chế.

Thông báo cần tránh biến hỗ trợ thành một cổng mở khóa tùy ý. Nhân viên có thể giải thích trạng thái được phép công bố hoặc xử lý hồ sơ theo quyền hạn, không xác nhận công khai tài khoản tồn tại cho bất kỳ ai biết địa chỉ email.

## 12. Ví dụ hành trình: Gửi lại mã trong khi mất điện thoại

Lan mất điện thoại chứa ứng dụng MFA và đang thực hiện một nhánh khôi phục đã được dịch vụ hỗ trợ. Cô chưa nhận được thông báo theo hướng dẫn nên bấm Gửi lại nhiều lần.

Hệ thống từ chối gửi thêm trong một khoảng ngắn. Nếu ngữ cảnh hiện tại có quyền nhận thông tin tương ứng, giao diện hiển thị:

> Hiện chưa thể gửi thêm thông báo. Bạn có thể thử lại sau ít nhất 60 giây. Không cần bấm Gửi lại trong lúc chờ.

Trong lúc chờ:

1. Chỉ chức năng gửi lại bị hạn chế theo quyết định này.
2. Giao diện không khẳng định tài khoản đã bị khóa hoặc OTP đã sai.
3. Không tự gửi request mới mỗi giây.
4. Các bước còn hiệu lực vẫn được xử lý theo chính sách của chúng.
5. Mục Trợ giúp khôi phục vẫn có thể truy cập được.

Khi đồng hồ về 0, nút chuyển sang trạng thái cho phép thử lại. Máy chủ kiểm tra lại mọi điều kiện khi Lan chọn gửi; không có bảo đảm rằng request sẽ được chấp nhận chỉ vì đã hết khoảng chờ trước đó.

Nếu flow đã hết hạn, giao diện hướng Lan bắt đầu lại đúng quy trình. Nếu hệ thống gửi thông báo đang gặp sự cố, phản hồi nói về khả năng xử lý của dịch vụ thay vì buộc tội Lan đã gửi quá nhiều.

Đối với điểm tiếp nhận công khai chưa có quyền tiết lộ trạng thái tài khoản, dùng thông điệp có điều kiện và chính sách phản hồi thống nhất, thay vì tiết lộ chi tiết từ hành trình trên.

Một phản hồi giới hạn tốt giúp người dùng tiếp tục khôi phục có chủ đích: hiểu đúng bước đang chờ, tránh gửi thêm không cần thiết và tìm được lối hỗ trợ chính thức. Quyền quyết định vẫn thuộc máy chủ, còn giao diện truyền đạt đúng những gì hệ thống có thể công bố và thực hiện.
