# Localized recovery errors

## 1. Bản địa hóa lỗi khôi phục tài khoản là gì?

Localized recovery errors là các thông báo lỗi trong luồng khôi phục được trình bày theo ngôn ngữ người dùng hiểu, trong khi kết quả xác minh và chính sách bảo mật vẫn giữ nguyên. Dịch một câu “Mã không hợp lệ” là phần dễ thấy; khó hơn là bảo đảm mọi bản dịch đều hướng dẫn đúng hành động, không tiết lộ danh tính và không khiến người dùng hiểu nhầm rằng tài khoản đã được khôi phục.

Luồng khôi phục có thể liên quan đến mật khẩu, MFA, passkey hoặc thiết bị đã mất. Người dùng cần phân biệt lỗi nhập liệu, bằng chứng không được chấp nhận, thời gian chờ và sự cố tạm thời. Hệ thống lại không được công bố toàn bộ nguyên nhân nội bộ cho người chưa xác minh.

Vì vậy, cần tách ba lớp:

| Lớp | Ví dụ | Có phụ thuộc ngôn ngữ không? |
| --- | --- | --- |
| Nguyên nhân nội bộ | Token đã dùng, challenge không tồn tại, chính sách từ chối | Không |
| Mã kết quả công khai | `RECOVERY_PROOF_REJECTED` | Không |
| Thông báo hiển thị | “Không thể xác minh mã này. Hãy kiểm tra mã hoặc yêu cầu mã mới.” | Có |

Một mã công khai có thể đại diện cho nhiều nguyên nhân nội bộ. Giao diện xử lý theo mã ổn định, không so sánh câu tiếng Việt hay tiếng Anh để quyết định bước tiếp theo.

## 2. Xác định thông tin được phép nói trước khi dịch

Ở điểm bắt đầu khôi phục, thông báo “Không tìm thấy email này” cho người ngoài biết định danh có thuộc hệ thống hay không. Dịch chính xác câu đó sang nhiều ngôn ngữ vẫn giữ nguyên lỗ hổng.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại, đồng thời chú ý thời gian phản hồi để hạn chế dò tài khoản. Nguyên tắc này phải được giữ ở mọi ngôn ngữ được hỗ trợ.

Có thể dùng phản hồi trung tính:

> Nếu thông tin phù hợp với tài khoản, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.

Đây là xác nhận xử lý yêu cầu, không phải xác nhận tài khoản tồn tại hay email chắc chắn đã được gửi. Bản tiếng Anh cũng phải giữ điều kiện tương ứng; không rút gọn thành “We sent a recovery email”.

Trong thiết kế, hãy xác định ranh giới tiết lộ theo giai đoạn:

- Trước xác minh: không công bố tài khoản tồn tại, danh sách MFA, số điện thoại hay email khôi phục đã lưu.
- Khi người dùng gửi bằng chứng: chỉ công bố chi tiết phù hợp với quyền của recovery context hiện tại.
- Sau xác minh đủ điều kiện: có thể hướng dẫn cụ thể hơn về thay đổi được phép và kết quả thực tế.

Không suy ra rằng có một `challengeId` là đã được xác minh. Challenge ban đầu có thể được cấp cho mọi yêu cầu nhằm giữ hành vi trung tính.

## 3. Hợp đồng mã lỗi công khai

Danh mục lỗi cần mô tả cả ý nghĩa và hành động được phép. Tên sau đây là ví dụ thiết kế cho module, không phải chuẩn bắt buộc.

| Mã công khai | Khi dùng | Thông báo tiếng Việt gợi ý | Hành động |
| --- | --- | --- | --- |
| `RECOVERY_INPUT_INVALID` | Định dạng dữ liệu gửi lên không hợp lệ | “Kiểm tra định dạng thông tin đã nhập.” | Sửa trường nhập |
| `RECOVERY_PROOF_REJECTED` | Không chấp nhận bằng chứng tại bước hiện tại | “Không thể xác minh mã này. Hãy kiểm tra mã hoặc yêu cầu mã mới.” | Sửa mã hoặc chọn lối tiếp tục được phép |
| `RECOVERY_REQUEST_RETRY_LATER` | Yêu cầu bị giới hạn theo chính sách có thể công bố | “Chưa thể tiếp tục lúc này. Vui lòng thử lại sau.” | Chờ hoặc dùng trợ giúp phù hợp |
| `RECOVERY_TEMPORARILY_UNAVAILABLE` | Có sự cố xử lý tạm thời | “Tạm thời chưa thể xử lý yêu cầu. Vui lòng thử lại.” | Thử lại có kiểm soát |
| `RECOVERY_CONTEXT_UNUSABLE` | Ngữ cảnh khôi phục không còn dùng được | “Phiên khôi phục không còn hiệu lực. Hãy bắt đầu lại.” | Khởi động luồng mới |

Lỗi định dạng có thể cụ thể khi chỉ phản ánh dữ liệu người dùng vừa nhập, chẳng hạn “Nhập đủ 6 chữ số”. Không chuyển nguyên thông báo từ cơ sở dữ liệu, nhà cung cấp SMS hoặc bộ xác minh token sang giao diện.

Thông tin hết hạn có thể hữu ích trong một ngữ cảnh đã đủ điều kiện tiết lộ. Nếu việc phân biệt “mã sai”, “mã đã dùng” và “mã hợp lệ nhưng hết hạn” tạo thêm tín hiệu không được phép, ánh xạ chúng về cùng mã công khai. Bản dịch không được tự chia nhỏ lại các trường hợp đã được lớp bảo mật gom chung.

Không chỉ kiểm soát câu hiển thị: `code`, HTTP status, cấu trúc JSON, header và dữ liệu ẩn cũng có thể làm lộ sự khác biệt. Ví dụ, hai tài khoản nhận cùng câu tiếng Việt nhưng một bên có `ACCOUNT_NOT_FOUND` trong JSON vẫn có thể bị phân biệt.

## 4. Chọn ngôn ngữ mà không phụ thuộc sự tồn tại của tài khoản

Một chính sách lựa chọn ngôn ngữ có thể ưu tiên:

1. Ngôn ngữ người dùng vừa chủ động chọn trên giao diện.
2. Lựa chọn giao diện đã lưu cho trình duyệt hoặc recovery context.
3. Ngôn ngữ trình duyệt đề xuất, sau khi đối chiếu danh sách hỗ trợ.
4. Ngôn ngữ mặc định của sản phẩm.

Đây là thứ tự thiết kế minh họa; cần áp dụng nhất quán trên web, ứng dụng và trang lỗi. Không yêu cầu đăng nhập mới được đổi ngôn ngữ trong khi người dùng đang mất khả năng đăng nhập.

[W3C Internationalization về Accept-Language](https://www.w3.org/International/questions/qa-accept-lang-locales) lưu ý rằng header này là gợi ý sở thích ngôn ngữ, không đủ để suy ra toàn bộ locale; người dùng cần được thay đổi lựa chọn. Không dùng nó để suy đoán múi giờ, quốc tịch hay quyền khôi phục.

Trước xác minh, tránh tự chuyển ngôn ngữ theo hồ sơ tra được từ email vừa nhập. Nếu tài khoản thật nhận tiếng Việt còn tài khoản không tồn tại nhận tiếng Anh, chính lựa chọn ngôn ngữ trở thành tín hiệu dò tìm.

Ví dụ fallback có kiểm soát:

```text
Yêu cầu ngôn ngữ: vi-VN
Danh sách hỗ trợ: vi, en
Kết quả chọn: vi

Yêu cầu ngôn ngữ: một thẻ không được hỗ trợ
Kết quả chọn: en, theo mặc định của sản phẩm
```

Đối chiếu locale với danh sách hỗ trợ bằng bộ phân tích phù hợp. Không nối trực tiếp giá trị do người dùng gửi vào đường dẫn tệp bản dịch hoặc tên template. Đổi ngôn ngữ chỉ đổi cách trình bày: không cấp lại token, xóa bộ đếm thử hoặc tạo phiên có quyền cao hơn.

## 5. Thiết kế catalog và phản hồi API

Catalog nên chứa nguyên câu có ý nghĩa hoàn chỉnh. Tránh nối các mảnh “Thử lại sau” + số + “phút” vì thứ tự từ và dạng số nhiều khác nhau giữa các ngôn ngữ.

Ví dụ hai bản dịch cùng một mã công khai:

```json
{
  "vi": {
    "RECOVERY_PROOF_REJECTED":
      "Không thể xác minh mã này. Hãy kiểm tra mã hoặc yêu cầu mã mới.",
    "RECOVERY_TEMPORARILY_UNAVAILABLE":
      "Tạm thời chưa thể xử lý yêu cầu. Vui lòng thử lại."
  },
  "en": {
    "RECOVERY_PROOF_REJECTED":
      "We could not verify this code. Check it or request a new one.",
    "RECOVERY_TEMPORARILY_UNAVAILABLE":
      "We cannot process this request right now. Please try again."
  }
}
```

Một phản hồi minh họa ở bước nhập mã:

```json
{
  "code": "RECOVERY_PROOF_REJECTED",
  "message": "Không thể xác minh mã này. Hãy kiểm tra mã hoặc yêu cầu mã mới.",
  "language": "vi",
  "requestId": "req_K7P4M9"
}
```

Trong hợp đồng này:

- `code` quyết định cách giao diện xử lý, chẳng hạn giữ lại bước nhập mã.
- `message` phục vụ hiển thị; không dùng làm điều kiện điều khiển nghiệp vụ.
- `language` nói ngôn ngữ thực tế của câu trả về sau fallback.
- `requestId` là mã tra cứu hỗ trợ không chứa định danh tài khoản hoặc bí mật.

Có thể để máy chủ trả thông báo đã dịch như ví dụ, hoặc để client dịch mã công khai. Cần chọn rõ bên sở hữu bản dịch để tránh client và máy chủ tạo hai câu có ý nghĩa khác nhau cho cùng kết quả.

Khi thiếu khóa dịch, dùng thông báo công khai dự phòng có chủ đích. Không in tên khóa kỹ thuật, stack trace hay nguyên nhân nội bộ thay cho câu người dùng. Nếu có thể giữ đúng ý nghĩa mã lỗi bằng bản dịch dự phòng thì giữ; nếu client chưa hiểu mã mới, dùng hành vi an toàn đã định nghĩa thay vì tự coi là thành công.

## 6. Tham số, thời gian chờ và dữ liệu Unicode

Chỉ cho phép tham số đã được định nghĩa theo từng mẫu thông báo. Ví dụ, thông báo chờ có thể nhận một khoảng thời gian do máy chủ cho phép công bố. Không nhận `reason` tự do rồi chèn vào câu dịch.

Cần phân biệt ba loại dữ liệu:

| Loại | Cách xử lý |
| --- | --- |
| Số lượng hoặc khoảng thời gian hiển thị | Định dạng và xử lý dạng số nhiều theo ngôn ngữ |
| Mã OTP, recovery code hoặc token | Giữ theo giao thức mã; không thêm dấu phân nhóm hay dịch ký tự |
| Thời điểm tuyệt đối | Hiển thị múi giờ rõ ràng theo lựa chọn thực tế |

Nếu giao thức chỉ nhận sáu chữ số ASCII, hướng dẫn phải nói rõ định dạng được nhận. Nếu sản phẩm hỗ trợ chuyển đổi một số dạng chữ số Unicode, quy tắc đó phải rõ ràng và thống nhất giữa giao diện với máy chủ. Đừng tự áp dụng chuẩn hóa của mã OTP lên mật khẩu, passkey hay token khác.

Thời hạn có hiệu lực do máy chủ quyết định. Đổi từ “1 minute” sang “1 phút” không làm thay đổi thời điểm được thử lại. Chỉ trả số giây chờ hoặc số lần còn lại khi chính sách cho phép; một giá trị lấy từ trạng thái riêng của tài khoản có thể tiết lộ thêm thông tin ở bước ẩn danh.

Với ngôn ngữ viết từ phải sang trái, một định danh gồm chữ Latin và số có thể bị hiển thị khó hiểu khi nằm trong câu dịch. [W3C hướng dẫn về văn bản hai chiều](https://www.w3.org/International/questions/qa-bidi-unicode-controls) giải thích cách cô lập các đoạn có hướng chữ khác nhau.

Trong HTML, có thể đặt một mã hỗ trợ đã được phép công bố vào phần tử có hướng chữ thích hợp, đồng thời chèn giá trị bằng thao tác văn bản an toàn. Trong email hoặc SMS văn bản thuần, cần xử lý hướng chữ theo kênh. Không “sửa” chuỗi token bằng cách chèn ký tự điều khiển vào giá trị mà máy chủ sẽ xác minh.

## 7. Giữ nguyên ý nghĩa bảo mật trong bản dịch

Người viết bản dịch cần biết thời điểm xuất hiện, mức thông tin được phép tiết lộ và hành động tiếp theo. Chỉ gửi một danh sách câu tiếng Anh rời rạc dễ tạo bản dịch đúng ngữ pháp nhưng sai ý nghĩa.

Các khác biệt sau có tác động trực tiếp:

- “Nếu thông tin phù hợp…” không tương đương với “Tài khoản của bạn…”.
- “Không thể xác minh mã” không khẳng định mã đã hết hạn.
- “Yêu cầu đã được tiếp nhận” không khẳng định thay đổi đã hoàn tất.
- “Thử lại sau” không có nghĩa là yêu cầu gửi lại sẽ bỏ qua giới hạn.
- “Khôi phục mật khẩu” không luôn đồng nghĩa với “Khôi phục MFA” hoặc “Thay passkey”.

Tránh giọng đổ lỗi như “Bạn nhập sai liên tục” khi hệ thống chỉ biết bằng chứng không được chấp nhận. Câu lỗi nên ngắn, nêu việc người dùng có thể làm và có đường trợ giúp phù hợp. Không hướng người dùng gửi OTP, mật khẩu hoặc token cho nhân viên hỗ trợ.

Nhật ký nội bộ cần mã nguyên nhân ổn định để vận hành có thể phân tích xuyên ngôn ngữ. Không dùng toàn bộ câu đã dịch làm nhãn thống kê; cũng không ghi mã khôi phục hoặc mật khẩu vào log. Người dùng có thể cung cấp mã tra cứu hỗ trợ thay vì sao chép bí mật trong thông báo.

Thông báo lỗi có thể được trình đọc màn hình đọc ra. Bản dịch phải được áp dụng cả cho lỗi cạnh trường nhập, phần tổng hợp lỗi, thông báo trạng thái và nhãn hành động. Không chỉ dịch một toast nhìn thấy rồi để phần còn lại ở ngôn ngữ khác.

## 8. Tình huống áp dụng

Minh mất điện thoại chứa ứng dụng MFA và mở trang khôi phục trên máy tính mượn có trình duyệt tiếng Anh. Minh chọn tiếng Việt trước khi nhập thông tin tài khoản; lựa chọn này không phụ thuộc hồ sơ có được tìm thấy hay không.

Yêu cầu ban đầu nhận phản hồi trung tính bằng tiếng Việt. Đến bước được phép nhập mã dự phòng, máy chủ từ chối bằng chứng và trả `RECOVERY_PROOF_REJECTED`. Giao diện giữ người dùng ở bước hiện tại, đọc thông báo tiếng Việt và cung cấp những hành động được chính sách cho phép.

Minh đổi giao diện sang tiếng Anh để nhờ người thân đọc hướng dẫn. Câu lỗi được đổi ngôn ngữ, nhưng bằng chứng đã dùng, thời hạn challenge và bộ đếm thử không đổi. Nếu hết hiệu lực, hệ thống hướng dẫn khởi động lại theo trạng thái máy chủ; nó không biến việc chuyển ngôn ngữ thành một lần thử mới ngoài chính sách.

Sau khi Minh cung cấp bằng chứng hợp lệ và hoàn thành thay đổi, hệ thống mới thông báo kết quả tương ứng. Nếu còn yêu cầu đăng nhập lại hoặc thiết lập phương thức dự phòng mới, các hành động đó phải được trình bày đúng ngôn ngữ đang chọn.

Bản địa hóa tốt giúp người dùng hiểu cùng một quyết định bảo mật ở nhiều ngôn ngữ. Mã công khai ổn định, giới hạn tiết lộ và trạng thái máy chủ là nền tảng; câu dịch giúp người dùng thực hiện bước tiếp theo chính xác.
