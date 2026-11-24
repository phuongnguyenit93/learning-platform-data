# Safe retry experience

## 1. Thế nào là trải nghiệm thử lại an toàn?

Trong khôi phục tài khoản, người dùng có thể bấm nút hai lần, mất mạng sau khi gửi mã, không nhận được email hoặc mở lại một trang đã hết hạn. Safe retry experience giúp họ tiếp tục trong các tình huống đó mà vẫn hiểu trạng thái hiện tại, đồng thời không tạo thêm tác dụng phụ hoặc làm suy yếu kiểm soát xác minh.

Một lần chờ quá lâu không đủ để kết luận thao tác thất bại. Máy chủ có thể đã đặt lại mật khẩu nhưng phản hồi bị mất trên đường về. Nếu giao diện khẳng định “Chưa có thay đổi nào” rồi gửi lại như một thao tác mới, người dùng và hệ thống có thể đi theo hai trạng thái khác nhau.

Trải nghiệm thử lại cần đạt ba mục tiêu:

- Nói đúng điều đã biết và điều chưa xác định.
- Chỉ cho phép hành động tiếp theo phù hợp với trạng thái máy chủ.
- Giữ nguyên giới hạn thử, hiệu lực token và quyền của phiên khôi phục.

Nút “Thử lại” là một phần của giao diện cho chính sách đó. Việc ẩn hoặc vô hiệu hóa nút không thay thế kiểm soát phía máy chủ.

## 2. Phân biệt các loại thử lại

Không nên gom mọi tình huống thành một hành động duy nhất.

| Tình huống | Ý định thực tế | Rủi ro nếu xử lý sai |
| --- | --- | --- |
| Mất phản hồi sau khi gửi | Gửi lại cùng một thao tác hoặc kiểm tra kết quả | Lặp thay đổi, lặp gửi thông báo |
| Mã bị từ chối và người dùng sửa mã | Gửi bằng chứng mới | Không tính đủ các lần đoán mã |
| Không nhận được mã | Yêu cầu gửi lại theo chính sách | Gửi dồn email/SMS, vô hiệu hóa mã đang đến |
| Mã hoặc ngữ cảnh hết hạn | Khởi động bước hoặc luồng mới được phép | Dùng lại bằng chứng không còn hiệu lực |
| Bị giới hạn tần suất | Chờ rồi yêu cầu tiếp tục | Vượt giới hạn bằng tải lại trang hoặc đổi tab |
| Thao tác đã hoàn tất | Xem kết quả và chuyển bước | Thực hiện lại một hành động nhạy cảm |

Sửa một ký tự của mã là thay đổi bằng chứng, không phải bản sao vận chuyển của cùng yêu cầu. Ngược lại, hai lần gửi cùng một thao tác vì kết nối chập chờn có thể cần được nhận diện là yêu cầu trùng.

[RFC 9110 về phương thức idempotent](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) lưu ý rằng client không nên tự động thử lại thao tác không idempotent nếu không có cơ sở biết việc lặp lại là an toàn hoặc thao tác ban đầu chưa được áp dụng. Vì vậy, một middleware tự thử lại mọi POST không phải mặc định thích hợp cho toàn bộ luồng khôi phục.

## 3. Giao diện phải biểu diễn cả trạng thái chưa rõ kết quả

Có thể mô hình hóa giao diện bằng các trạng thái sau:

| Trạng thái | Thông báo minh họa | Hành động |
| --- | --- | --- |
| Sẵn sàng | “Nhập mã xác minh.” | Gửi bằng chứng |
| Đang xử lý | “Đang xác minh…” | Ngăn gửi trùng trong cùng thao tác |
| Chưa xác định kết quả | “Chưa nhận được kết quả. Hệ thống sẽ kiểm tra trạng thái.” | Đối chiếu hoặc thử lại theo hợp đồng |
| Bằng chứng bị từ chối | “Không thể xác minh mã này.” | Sửa mã hoặc dùng đường tiếp tục được phép |
| Cần chờ | “Chưa thể tiếp tục lúc này. Vui lòng thử lại sau.” | Chờ theo chỉ dẫn |
| Ngữ cảnh không còn dùng được | “Phiên khôi phục không còn hiệu lực.” | Bắt đầu lại hoặc dùng trợ giúp |
| Hoàn tất | “Thay đổi đã được xác nhận.” | Chuyển sang bước tiếp theo |

Khi đang xử lý, giữ một chỉ báo rõ ràng và tên hành động ổn định. Chặn nhấp đúp để giảm yêu cầu vô tình, nhưng vẫn xử lý trường hợp client gửi song song qua tab khác hoặc API.

Timeout và thao tác hủy chờ ở trình duyệt chỉ nói rằng client ngừng chờ kết quả. Chúng không chứng minh máy chủ đã hủy công việc. Thông báo cần phản ánh giới hạn này; không tự chuyển về một trạng thái “chưa từng gửi”.

Với trình đọc màn hình, thông báo các thay đổi quan trọng qua vùng trạng thái phù hợp. Đừng đọc đồng hồ chờ mỗi giây hoặc kéo focus khỏi trường nhập sau mọi phản hồi nền. Khi có lỗi cần sửa, cung cấp hướng dẫn gắn với đúng trường.

## 4. Hợp đồng chống lặp thao tác

Idempotency có thể giúp máy chủ nhận ra các lần gửi lại thuộc cùng ý định. [Bài viết của AWS về retry và API idempotent](https://builder.aws.com/content/3Ev0BENTyBr0XxzRk5FDZzgNYos/making-retries-safe-with-idempotent-apis) mô tả việc dùng định danh yêu cầu và trả kết quả có cùng ý nghĩa để hạn chế tác dụng phụ khi gửi lại.

Áp dụng cho khôi phục cần xác định rõ:

- Một định danh gắn với một thao tác và ngữ cảnh được phép.
- Gửi lại cùng định danh cùng dữ liệu không tạo thay đổi lần nữa.
- Cùng định danh nhưng dữ liệu khác phải được xử lý như xung đột theo hợp đồng.
- Định danh mới không làm mất hiệu lực giới hạn thử hoặc giới hạn gửi.
- Yêu cầu trùng đang xử lý có kết quả chờ rõ ràng.

Ví dụ hợp đồng giả định:

```text
Thao tác: yêu cầu gửi lại mã
Định danh thao tác: op_example_A
Ngữ cảnh: recovery context hiện tại
Khi mất phản hồi: dùng lại op_example_A theo hợp đồng retry
Khi người dùng chủ động yêu cầu một lần gửi mới: tạo thao tác mới,
nhưng vẫn phải qua kiểm tra thời gian chờ và ngân sách gửi
```

Định danh chống lặp không phải token xác minh hay quyền đăng nhập. Máy chủ vẫn kiểm tra ngữ cảnh, CSRF khi phù hợp và quyền truy cập kết quả.

Riêng token dùng một lần, tính nguyên tử của việc kiểm tra và tiêu thụ vẫn cần được bảo đảm. Chỉ thêm một khóa idempotency vào request không ngăn được hai yêu cầu cùng sử dụng token nếu phần chuyển trạng thái phía máy chủ còn có race condition.

Nếu phải đối chiếu kết quả qua một API trạng thái, chỉ trả thông tin cho ngữ cảnh có quyền xem. Không cho người ngoài tra cứu tiến độ bằng email hoặc đoán một mã thao tác. Kết quả đã có cũng không tự tái cấp quyền sau khi quyền hoặc phiên đã bị thu hồi.

## 5. Thời gian chờ và giới hạn thử

Thời gian chờ giúp giảm gửi dồn và hỗ trợ người dùng hiểu lúc nào nên tiếp tục. Máy chủ quyết định việc chấp nhận yêu cầu; đồng hồ giao diện chỉ thể hiện chỉ dẫn hiện tại.

[RFC 6585 định nghĩa HTTP 429](https://www.rfc-editor.org/rfc/rfc6585.html#section-4) cho trường hợp quá nhiều yêu cầu và cho phép phản hồi kèm `Retry-After`. [RFC 9110 mô tả Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) với giá trị là số giây chờ hoặc một thời điểm HTTP-date.

Ví dụ ở một bước được phép công bố khoảng chờ:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Cache-Control: no-store
Content-Type: application/json

{
  "code": "RECOVERY_RETRY_LATER",
  "message": "Chưa thể tiếp tục lúc này. Vui lòng thử lại sau."
}
```

Giá trị 60 chỉ là minh họa, không phải thời hạn mặc định cho mọi hệ thống.

Client cần hiểu phản hồi theo hợp đồng, không coi mọi lỗi mạng là 429. Khi nhận thời gian chờ hợp lệ, giao diện thông báo khoảng chờ và không gửi trước hạn. Nếu hết đồng hồ, người dùng được yêu cầu tiếp tục; máy chủ vẫn có thể đánh giá lại và yêu cầu chờ thêm.

Các lớp tự động thử lại nên có số lần tối đa, thời hạn tổng và khoảng nghỉ phù hợp. Với lỗi tạm thời được phép retry, có thể tăng khoảng nghỉ và thêm độ lệch ngẫu nhiên để giảm dồn tải. Chỉ chọn một nơi điều phối retry nhằm tránh vòng lặp ở client, gateway và service nhân số yêu cầu lên.

Không áp dụng retry tự động cho mọi lần mã sai. Một mã bị từ chối là kết quả xác minh, không phải sự cố mạng cần phát lại liên tục.

## 6. Gửi lại mã mà người dùng vẫn hiểu mã nào còn dùng được

“Gửi lại mã” có thể là gửi lại cùng một mã còn hiệu lực hoặc phát hành mã mới, tùy thiết kế. Nếu mã mới vô hiệu hóa mã cũ, cần giải thích rõ sau phản hồi phù hợp: “Hãy dùng mã mới nhất. Mã trước đó không còn hiệu lực.”

Một hành trình dễ hiểu gồm:

1. Giữ người dùng tại bước hiện tại khi yêu cầu gửi lại.
2. Hiển thị trạng thái đang xử lý và chặn gửi trùng vô tình.
3. Chỉ thông báo kết quả tương ứng với phản hồi máy chủ.
4. Cập nhật hướng dẫn về mã đang có hiệu lực và thời gian chờ.
5. Cung cấp đường tiếp tục nếu người dùng không còn dùng được phương thức này.

Không khẳng định mã đã đến hộp thư hoặc điện thoại chỉ vì hệ thống đã tiếp nhận yêu cầu. Có thể hướng dẫn kiểm tra kênh nhận, thư rác và thời gian chờ; không bắt người dùng bấm gửi lại liên tục.

Khi có nhiều phản hồi về không đúng thứ tự, giao diện cần tránh để phản hồi cũ ghi đè ngữ cảnh mới. Chẳng hạn, sau khi chuyển sang phương thức khác, một phản hồi gửi lại chậm không được tự kéo người dùng trở về màn hình cũ.

Đổi ngôn ngữ, tải lại trang hoặc mở tab mới không làm mới ngân sách gửi. Máy chủ cần kiểm soát theo những phạm vi thích hợp của hệ thống, đồng thời tránh làm người dùng chung mạng bị ảnh hưởng quá mức chỉ vì dùng cùng địa chỉ IP.

## 7. Không biến thử lại thành công cụ lạm dụng

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị bảo vệ khỏi yêu cầu tự động quá mức và không khóa tài khoản chỉ vì bị tấn công qua chức năng quên mật khẩu. Kẻ ngoài có thể dùng việc khóa như vậy để ngăn chủ tài khoản truy cập.

Trong thiết kế safe retry, cần tách:

- Giới hạn yêu cầu gửi hướng dẫn.
- Giới hạn các lần thử bằng chứng.
- Thời hạn của token hoặc challenge.
- Quyền và thời hạn của phiên khôi phục.
- Trạng thái đăng nhập thông thường của tài khoản.

Yêu cầu một mã mới không mặc nhiên được đặt lại toàn bộ số lần đoán. Tạo một recovery context mới cũng không nên trở thành cách vượt các giới hạn rộng hơn mà chính sách đang bảo vệ.

Tại bước công khai, phản hồi cần giữ mức tiết lộ nhất quán giữa định danh tồn tại và không tồn tại. Nội dung chờ, mã lỗi và metadata cũng cần phù hợp với mức tiết lộ đó. Không công khai “tài khoản này chỉ còn một lần thử” nếu người gửi chưa được phép biết trạng thái riêng của tài khoản.

Không hướng người dùng tắt MFA, đổi thiết bị để né giới hạn hoặc gửi token cho nhân viên hỗ trợ. Nếu không còn phương thức sử dụng được, cung cấp quy trình dự phòng có xác minh phù hợp; việc người dùng gặp khó khăn không tự trở thành bằng chứng danh tính.

## 8. Thao tác nhạy cảm đã hoàn tất nhưng phản hồi bị mất

Đặt lại mật khẩu, thay MFA hoặc thu hồi passkey có thể làm thay đổi trạng thái mà request đang dựa vào. Vì vậy, nút thử lại ở bước cuối cần được thiết kế cùng hợp đồng chuyển trạng thái.

Ví dụ: máy chủ đã chấp nhận token, lưu mật khẩu mới và đánh dấu token đã dùng. Phản hồi bị mất. Nếu client gửi lại, một câu “Token đã dùng” đơn lẻ có thể khiến chủ tài khoản tưởng khôi phục thất bại.

Một thiết kế có đối chiếu kết quả cần cho phép xác nhận cùng thao tác đã hoàn tất trong phạm vi quyền thích hợp. Điều đó không có nghĩa cho phép token đã dùng thực hiện thay đổi mới. Nếu không còn quyền xem kết quả, giao diện hướng người dùng tới lối tiếp tục an toàn, chẳng hạn đăng nhập bằng phương thức vừa thiết lập hoặc bắt đầu lại theo chính sách.

Cũng phải mô tả đúng phạm vi session. Nếu thay đổi đã hoàn tất nhưng một phần xử lý thu hồi phiên còn đang chờ, không thông báo mọi phiên đã bị đóng. Việc gửi lại request không được tự tạo phiên đăng nhập mới hoặc kéo dài phiên khôi phục.

Dữ liệu nhạy cảm không nên được lưu vào lịch sử trình duyệt, log hay bộ nhớ bền vững chỉ để thuận tiện cho retry. Giữ những thông tin tối thiểu phục vụ cùng thao tác trong phạm vi được cho phép, rồi xóa khi kết thúc.

## 9. Tình huống minh họa

Nam mất điện thoại chứa MFA và đang dùng phương thức khôi phục đã đăng ký. Mạng trên máy tính không ổn định.

| Thời điểm | Điều xảy ra | Trải nghiệm cần có |
| --- | --- | --- |
| Nam bấm xác minh | Một thao tác được gửi | Hiển thị đang xử lý, tránh nhấp đúp |
| Máy chủ xử lý nhưng phản hồi bị mất | Client chưa biết kết quả | Hiển thị chưa xác định kết quả |
| Client đối chiếu theo hợp đồng | Nhận kết quả của cùng thao tác | Chuyển đúng bước, không xác minh lại như một ý định mới |
| Nam yêu cầu mã mới ở bước khác | Tạo ý định gửi mới | Kiểm tra hạn chờ và ngân sách gửi |
| Nam mở thêm tab | Xuất hiện một giao diện khác | Vẫn chịu cùng kiểm soát máy chủ |
| Thay đổi cuối được xác nhận | Luồng đạt kết quả thực tế | Thông báo đúng thay đổi và đường đăng nhập tiếp theo |

Nếu đối chiếu không thành công, hệ thống giữ thông báo trung thực và giới hạn số lần thử tự động. Người dùng có một hành động tiếp tục rõ ràng thay vì vòng xoay vô hạn hoặc thông báo thành công không có căn cứ.

Trải nghiệm thử lại an toàn giúp người dùng tiếp tục sau gián đoạn mà vẫn bảo toàn ý định của thao tác. Giao diện giải thích trạng thái; hợp đồng API, token dùng một lần, giới hạn lạm dụng và kiểm soát session giữ cho việc tiếp tục đó an toàn.
