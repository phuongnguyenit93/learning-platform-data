# Translation consistency

## 1. Nhất quán bản dịch trong khôi phục tài khoản

Translation consistency là việc các bản dịch cùng diễn đạt đúng một khái niệm, trạng thái và hành động trong luồng khôi phục tài khoản. Điều đó cần được duy trì giữa các ngôn ngữ, các bước của hành trình và các kênh như giao diện, email, SMS hoặc hướng dẫn hỗ trợ.

Người dùng có thể bắt đầu bằng tiếng Việt trên điện thoại, mở email bằng tiếng Anh và hoàn tất trên một máy tính khác. Nếu một nơi nói “mã dự phòng”, nơi khác nói “mã xác minh” cho cùng một loại bằng chứng, họ có thể nhập nhầm mã. Nếu email nói “mật khẩu đã được đặt lại” trong khi giao diện mới tiếp nhận yêu cầu, họ có thể hiểu sai trạng thái an toàn của tài khoản.

[W3C phân biệt internationalization và localization](https://www.w3.org/International/questions/qa-i18n): thiết kế quốc tế hóa tạo nền tảng để bản địa hóa nội dung và cách trình bày cho từng ngôn ngữ, khu vực. Trong bài này, trọng tâm là giữ ý nghĩa khôi phục tài khoản ổn định khi câu chữ thay đổi.

Một bản dịch tốt cần giữ được bốn thông tin:

- Người dùng đang thực hiện hành động nào.
- Hệ thống đã xác nhận điều gì.
- Thông tin nào được phép tiết lộ ở giai đoạn hiện tại.
- Người dùng có thể làm gì tiếp theo.

Văn phong có thể khác để tự nhiên trong từng ngôn ngữ. Trạng thái xác minh, quyền truy cập và hiệu lực của token phải do cùng một chính sách máy chủ quyết định.

## 2. Bắt đầu từ thuật ngữ và định nghĩa

Một glossary hữu ích cần có thuật ngữ, định nghĩa nghiệp vụ, cách dùng ưu tiên và những trường hợp dễ nhầm. Chỉ liệt kê hai cột tiếng Anh và tiếng Việt chưa đủ để người dịch phân biệt các loại mã hoặc các thao tác trên phương thức xác thực.

Bảng sau là quy ước minh họa cho một sản phẩm:

| Thuật ngữ | Cách dùng tiếng Việt | Ý nghĩa cần giữ |
| --- | --- | --- |
| Account recovery | Khôi phục tài khoản | Quy trình lấy lại quyền truy cập bằng bằng chứng được chấp nhận |
| Password reset | Đặt lại mật khẩu | Tạo mật khẩu mới; không lấy lại hoặc tiết lộ mật khẩu cũ |
| Verification code | Mã xác minh | Mã dùng cho một bước xác minh theo ngữ cảnh cụ thể |
| Recovery code | Mã dự phòng | Mã đã được cấp để dùng khi không còn phương thức thông thường |
| Passkey | Passkey | Loại thông tin xác thực; giữ tên thống nhất và có giải thích khi cần |
| Recovery session | Phiên khôi phục | Ngữ cảnh tạm thời của hành trình khôi phục, có quyền giới hạn |
| Login session | Phiên đăng nhập | Phiên đã được hệ thống cấp quyền sau đăng nhập |
| Revoke | Thu hồi hiệu lực | Làm mất khả năng sử dụng theo phạm vi chính sách |
| Resend | Gửi lại | Yêu cầu gửi hướng dẫn hoặc mã; hiệu lực mã cũ phụ thuộc chính sách |

“Mã dự phòng” và “mã xác minh gửi qua email” đều có thể dùng một lần nhưng không vì vậy mà trở thành cùng một khái niệm. Tương tự, thu hồi một passkey ở phía dịch vụ không đồng nghĩa hệ thống đã xóa bản lưu passkey trên thiết bị của người dùng.

Glossary nên nêu rõ từ nào là tên sản phẩm, từ nào được dịch và khi nào cần giải thích. Khi chọn một cách gọi, dùng nó xuyên suốt nhãn trường nhập, nút, thông báo, email và tài liệu hỗ trợ.

## 3. Giữ nguyên ý nghĩa của trạng thái bảo mật

Câu dịch phải tương ứng với sự kiện thực tế. “Đã nhận yêu cầu”, “đã gửi hướng dẫn”, “đã xác minh bằng chứng” và “đã hoàn tất khôi phục” là các trạng thái khác nhau.

| Sự kiện | Điều có thể mô tả | Suy diễn cần tránh |
| --- | --- | --- |
| Tiếp nhận yêu cầu ban đầu | Hệ thống đã xử lý yêu cầu theo luồng công khai | Tài khoản chắc chắn tồn tại |
| Chấp nhận bằng chứng của một bước | Người dùng có thể chuyển sang bước được phép | Đã hoàn tất mọi bước xác minh |
| Lưu mật khẩu mới thành công | Mật khẩu đã được đặt lại | MFA hoặc passkey cũ cũng đã bị thu hồi |
| Hoàn thành thu hồi các phiên thuộc phạm vi quy định | Những phiên đó không còn hiệu lực | Mọi thiết bị và mọi phương thức đều đã bị xóa |
| Yêu cầu gửi lại mã được tiếp nhận | Yêu cầu đã được xử lý theo chính sách | Mọi mã cũ chắc chắn đã mất hiệu lực |

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại ở bước yêu cầu khôi phục. Khi dịch, phải giữ cả điều kiện và mức thông tin được phép công bố.

Ví dụ:

```text
VI: Nếu thông tin phù hợp với tài khoản, hướng dẫn khôi phục
    sẽ được gửi qua kênh đã đăng ký.

EN: If the information matches an account, recovery instructions
    will be sent through a registered channel.
```

Nếu bản tiếng Anh bị rút gọn thành “We found your account”, ý nghĩa bảo mật đã thay đổi dù câu ngắn và dễ đọc hơn. Nếu bản tiếng Việt khẳng định “Đã gửi thành công” khi hệ thống chỉ tiếp nhận yêu cầu, bản dịch cũng đang hứa nhiều hơn kết quả có thật.

Sự nhất quán này bao gồm nhãn trợ năng, nội dung ẩn trong trang và thông báo ở API. Chỉ giữ câu nhìn thấy trung tính trong khi công bố nguyên nhân nội bộ ở dữ liệu khác vẫn để lại tín hiệu không mong muốn.

## 4. Gắn bản dịch với định danh thông điệp và ngữ cảnh

Không dùng chính câu tiếng Anh làm điều kiện xử lý nghiệp vụ. Một thay đổi dấu câu có thể làm hỏng nhánh điều hướng nếu client dựa vào việc so sánh chuỗi.

Có thể tổ chức nội dung theo ba thành phần:

1. Định danh thông điệp ổn định.
2. Hợp đồng ngữ nghĩa: sự kiện, điều kiện hiển thị, tham số và hành động.
3. Các bản dịch theo ngôn ngữ và kênh.

Ví dụ dữ liệu minh họa:

```yaml
messageId: recovery.password_reset.committed
event: PASSWORD_RESET_COMMITTED
meaning: Mật khẩu mới đã được lưu thành công.
audience: verified_recovery_context
parameters: []
translations:
  vi: Mật khẩu đã được đặt lại.
  en: Your password has been reset.
```

Ở đây, khóa và sự kiện không được dịch. Câu hiển thị chỉ được dùng khi máy chủ đã xác nhận đúng sự kiện. Một phản hồi API minh họa có thể là:

```json
{
  "event": "PASSWORD_RESET_COMMITTED",
  "messageId": "recovery.password_reset.committed",
  "nextAction": "SIGN_IN"
}
```

Client chọn câu theo ngôn ngữ nhưng không suy ra quyền đăng nhập từ câu dịch. Nếu nhận một sự kiện chưa hỗ trợ, client dùng hành vi dự phòng đã được định nghĩa; không tự coi sự kiện đó là thành công.

Người dịch cần ngữ cảnh như “xuất hiện sau khi lưu mật khẩu”, “người dùng chưa được đăng nhập tự động” hoặc “không nói về passkey”. Các ghi chú này giúp tránh bổ sung những lời hứa không có trong hợp đồng.

Chỉnh câu cho tự nhiên có thể giữ nguyên định danh khi ý nghĩa không đổi. Nếu hành vi thay đổi, chẳng hạn phạm vi thu hồi phiên khác trước, cần cập nhật hợp đồng và các thông điệp liên quan thay vì chỉ sửa một bản dịch.

## 5. Tham số và câu hoàn chỉnh

Thông điệp có biến cần giữ đúng kiểu dữ liệu, đơn vị và mục đích. Biến tên `waitSeconds` không thể được dịch thành “phút” trong khi giá trị vẫn giữ nguyên.

[Tài liệu ICU về định dạng thông điệp](https://unicode-org.github.io/icu/userguide/format_parse/messages/) giải thích cách dùng thông điệp hoàn chỉnh với placeholder, cũng như lựa chọn dạng số nhiều theo ngôn ngữ. Cách này cho phép người dịch thay đổi trật tự từ mà vẫn giữ dữ liệu có cấu trúc.

Ví dụ dưới đây dùng cú pháp ICU MessageFormat để minh họa câu chờ khi hệ thống được phép công bố thời gian:

```text
VI:
Bạn có thể yêu cầu mã mới sau {seconds, number, integer} giây.

EN:
{seconds, plural,
  one {You can request a new code in # second.}
  other {You can request a new code in # seconds.}
}
```

Đây là mẫu cho bộ định dạng tương ứng, không phải chuỗi có thể đưa nguyên trạng vào mọi thư viện Java hoặc JavaScript. Sản phẩm cần chọn cú pháp và bộ định dạng thống nhất để placeholder được hiểu đúng.

Những quy tắc cần giữ trong hợp đồng tham số:

- Khoảng chờ được lấy từ trạng thái máy chủ; bản dịch không quyết định thời điểm cho phép gửi lại.
- Ngày giờ hiển thị cần có cách xác định múi giờ phù hợp; ngôn ngữ không tự xác định nơi người dùng đang ở.
- OTP, recovery code và token giữ theo giao thức của chúng, không được định dạng như số lượng thông thường.
- Định danh và dữ liệu người dùng phải được chèn bằng cơ chế hiển thị an toàn theo kênh.
- Chỉ đưa vào thông điệp dữ liệu đã được phép công bố ở bước hiện tại.

Nếu đổi ngôn ngữ giữa lúc chờ, giá trị thời gian còn lại được tính từ cùng hạn chờ. Không khởi động lại bộ đếm hoặc tạo một lượt thử mới chỉ để dựng lại câu dịch.

## 6. Nhất quán giữa giao diện, email, SMS và hỗ trợ

Mỗi kênh có giới hạn riêng. SMS thường ngắn, email có thể cung cấp thêm giải thích và trang web có thể chứa hành động tương tác. Chúng cần giữ cùng khái niệm và kết quả, dù độ dài khác nhau.

Ví dụ khi mật khẩu đã được đặt lại:

| Kênh | Nội dung minh họa | Ý nghĩa giữ chung |
| --- | --- | --- |
| Giao diện | “Mật khẩu đã được đặt lại. Hãy đăng nhập bằng mật khẩu mới.” | Thao tác đã hoàn tất; bước tiếp theo là đăng nhập |
| Email thông báo | “Mật khẩu của tài khoản đã được đặt lại. Nếu bạn không thực hiện thao tác này, hãy mở kênh hỗ trợ chính thức.” | Thông báo thay đổi và đường xử lý nghi ngờ |
| SMS, nếu chính sách có gửi | “Mật khẩu đã được đặt lại. Nếu không phải bạn, hãy dùng kênh hỗ trợ chính thức.” | Cùng sự kiện, ít chi tiết hơn |
| Hướng dẫn hỗ trợ | Phân biệt đặt lại mật khẩu với khôi phục MFA và thu hồi passkey | Không suy rộng phạm vi thay đổi |

Các ví dụ là nội dung thiết kế, không có nghĩa mọi hệ thống phải gửi đủ cả ba kênh. Kênh thực tế và lượng thông tin gửi đi phụ thuộc chính sách cùng trạng thái đã xác minh.

Nội dung ngắn không được bỏ những điều kiện làm thay đổi ý nghĩa. Một bản SMS không nên chuyển “yêu cầu đã được tiếp nhận” thành “khôi phục đã thành công” chỉ để tiết kiệm ký tự.

Tài liệu hỗ trợ cũng cần dùng đúng thuật ngữ trên giao diện. Nếu nhân viên hướng dẫn tìm “mã dự phòng” nhưng màn hình gọi cùng thứ đó là “mã bảo mật”, người dùng có thể chọn nhầm bằng chứng. Hướng dẫn không được yêu cầu gửi mật khẩu, OTP hoặc token cho người hỗ trợ.

## 7. Thay đổi nội dung và xử lý bản dịch chưa sẵn sàng

Bản dịch có thể đầy đủ về số lượng khóa nhưng vẫn cũ về ý nghĩa. Ví dụ, hệ thống đã chuyển từ thu hồi mọi phiên sang chỉ thu hồi một phạm vi phiên xác định, trong khi email của một ngôn ngữ vẫn nói “đã đăng xuất khỏi mọi thiết bị”.

Để quản lý sự thay đổi, mỗi thông điệp có thể lưu cùng nguồn nội dung, ghi chú ngữ cảnh và phiên bản hợp đồng mà nó diễn đạt. Các kênh cùng mô tả một sự kiện cần được đối chiếu theo hợp đồng đó. Bản dịch được tái sử dụng chỉ khi phạm vi ý nghĩa vẫn phù hợp.

Cần phân biệt các tình huống dự phòng:

- Thiếu khóa nhưng hợp đồng vẫn được hỗ trợ: dùng bản dịch dự phòng được chỉ định.
- Có khóa nhưng ý nghĩa thuộc hợp đồng cũ: không coi đó là bản dịch hợp lệ chỉ vì tra cứu thành công.
- Thiếu thông điệp nhạy cảm không có câu dự phòng đúng nghĩa: dùng lối xử lý đã được sản phẩm xác định, tránh tự tạo lời khẳng định thành công.
- Tải catalog thất bại: vẫn giữ trạng thái và quyền do máy chủ xác nhận; lỗi nội dung không được làm bỏ qua bước xác minh.

Đường dự phòng cần được áp dụng nhất quán cho tài khoản tồn tại và không tồn tại ở bước công khai. Không để ngôn ngữ dự phòng phụ thuộc kết quả tra cứu tài khoản.

Có thể ghi nhận `messageId`, ngôn ngữ được chọn, ngôn ngữ thực tế và phiên bản catalog trong dữ liệu vận hành phù hợp. Không cần ghi bí mật khôi phục để tìm lỗi dịch. Mã thông điệp ổn định cũng giúp nhóm nội dung và hỗ trợ cùng nói về đúng một tình huống.

## 8. Tình huống xuyên suốt

Hà mất thiết bị có passkey, bắt đầu khôi phục bằng tiếng Việt và chọn dùng mã dự phòng đã lưu. Giao diện, hướng dẫn trong email và tài liệu hỗ trợ đều dùng cùng khái niệm “mã dự phòng”, phân biệt với mã xác minh được gửi cho một bước khác.

Sau khi một bằng chứng được chấp nhận, thông báo chỉ nói Hà có thể tiếp tục bước tiếp theo. Bản tiếng Anh mà Hà mở trên máy tính khác không được diễn đạt thành “Your account has been recovered” nếu vẫn còn bước xác minh hoặc xác nhận thay đổi.

Khi chờ được phép gửi lại mã, Hà đổi ngôn ngữ. Câu chờ thay đổi, còn hạn chờ, hiệu lực token và giới hạn thử giữ nguyên. Nếu một bản dịch chưa sẵn sàng, thông điệp dự phòng vẫn diễn đạt đúng cùng trạng thái.

Cuối cùng, máy chủ xác nhận các thay đổi đã hoàn tất. Giao diện và thông báo chỉ mô tả những thay đổi có thật: mật khẩu, passkey, MFA và các phiên được xử lý theo phạm vi thực tế. Không có bản dịch nào tự thêm lời hứa rằng mọi thiết bị đã bị loại bỏ.

Nhất quán bản dịch giúp người dùng đi qua hành trình khôi phục bằng nhiều ngôn ngữ mà vẫn hiểu cùng một hệ thống. Glossary thống nhất, hợp đồng thông điệp rõ ràng và dữ liệu trạng thái đáng tin cậy giúp câu chữ ở từng kênh giữ đúng ý nghĩa bảo mật.
