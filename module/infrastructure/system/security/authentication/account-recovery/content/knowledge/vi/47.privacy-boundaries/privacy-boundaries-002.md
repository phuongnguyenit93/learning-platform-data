# Contact detail privacy: bảo vệ thông tin liên hệ trong khôi phục tài khoản

## 1. Vì sao thông tin liên hệ cần một ranh giới riêng?

Email và số điện thoại vừa giúp người dùng khôi phục tài khoản, vừa có thể trở thành dữ liệu để dò tìm, theo dõi hoặc giả mạo họ. Luồng khôi phục thường hoạt động trước khi người yêu cầu đăng nhập, nên không thể mặc định người nhập đúng tên tài khoản có quyền xem các kênh liên hệ đã đăng ký.

**Contact detail privacy** là việc kiểm soát thông tin liên hệ nào được thu thập, sử dụng, hiển thị, truyền đi và lưu lại trong từng bước khôi phục. Mục tiêu là giúp người dùng hợp lệ tiếp tục quy trình mà không biến chức năng quên mật khẩu thành công cụ tra cứu dữ liệu cá nhân.

Ví dụ, một người biết tên đăng nhập của Linh thử chức năng khôi phục. Nếu hệ thống trả về email công việc, đuôi số điện thoại và địa chỉ email dự phòng, họ có thể liên kết tài khoản với nơi làm việc và danh tính của Linh dù chưa chứng minh bất kỳ quyền truy cập nào.

Thông tin bị lộ không chỉ là địa chỉ đầy đủ. Một miền email hiếm, mã quốc gia, vài chữ số cuối, số lượng kênh khôi phục hoặc việc một tài khoản tồn tại đều có thể hữu ích khi kết hợp với dữ liệu bên ngoài.

## 2. Phân biệt bốn loại thông tin

Một thiết kế rõ ràng cần tách dữ liệu dùng để nhận diện, dữ liệu dùng để chuyển phát, gợi ý hiển thị và bằng chứng xác minh.

| Loại | Ví dụ | Mục đích | Giới hạn |
| --- | --- | --- | --- |
| Định danh người dùng nhập | Tên đăng nhập hoặc email được khai báo | Tìm quy trình phù hợp | Chưa chứng minh người nhập là chủ tài khoản |
| Địa chỉ chuyển phát | Email hoặc số điện thoại đầy đủ đã đăng ký | Gửi thông điệp tới kênh được phép | Không cần trả lại đầy đủ cho trình duyệt |
| Gợi ý nhận biết | Một phần địa chỉ đã được che | Giúp chọn đúng kênh khi được phép | Vẫn có thể tiết lộ thông tin |
| Bằng chứng kiểm soát | Kết quả xác minh một challenge hợp lệ | Hỗ trợ quyết định khôi phục | Chỉ có giá trị trong phạm vi chính sách và giao dịch |

Một người đọc được gợi ý “số điện thoại kết thúc bằng 42” chưa chứng minh họ kiểm soát số đó. Việc đọc lại đúng địa chỉ mà hệ thống vừa tiết lộ cũng không tạo ra bằng chứng độc lập.

Ngược lại, một kết quả xác minh hợp lệ không tự cấp quyền xem toàn bộ hồ sơ liên hệ. Người dùng có thể chỉ được phép hoàn tất một hành động đặt lại mật khẩu, chưa được phép xem hoặc thay mọi kênh khôi phục.

## 3. Ai được xem gì ở từng giai đoạn?

Có thể xây dựng chính sách tiết lộ theo trạng thái và mục đích của phiên. Bảng sau là một thiết kế minh họa, cần điều chỉnh theo mức bảo đảm và loại tài khoản.

| Bối cảnh | Dữ liệu có thể cần trả về | Dữ liệu cần hạn chế |
| --- | --- | --- |
| Chưa xác minh, mới nhập định danh | Thông báo tiếp nhận chung và hướng dẫn công khai | Danh sách kênh, địa chỉ đầy đủ, miền email riêng, số kênh thật |
| Có quyền tiếp tục một giao dịch khôi phục | Những lựa chọn được chính sách cho phép trong giao dịch đó | Các kênh không liên quan hoặc dữ liệu hồ sơ khác |
| Đang xác minh một kênh đã chọn | Loại phương thức, trạng thái challenge và gợi ý tối thiểu nếu được phép | Danh sách địa chỉ còn lại hoặc thông tin chủ kênh |
| Đã xác thực để quản lý bảo mật | Thông tin cần thiết trong trang cài đặt của chính tài khoản | Dữ liệu vượt mục đích và quyền hiện tại |
| Nhân viên hỗ trợ xử lý một hồ sơ | Thông tin tối thiểu theo vai trò và hồ sơ được giao | Tra cứu hàng loạt, xuất danh sách hoặc xem rõ không có lý do nghiệp vụ |
| Dịch vụ chuyển phát | Địa chỉ đầy đủ của thông điệp được phép gửi | Toàn bộ danh bạ hoặc lịch sử không cần thiết |

“Đã qua một bước xác minh” không phải trạng thái cấp mọi quyền. Backend nên đánh giá quyền cụ thể như VIEW_RECOVERY_OPTIONS, SEND_RECOVERY_CHALLENGE hoặc CHANGE_RECOVERY_CONTACT.

Nếu chính sách yêu cầu một bằng chứng độc lập trước khi hiển thị lựa chọn khôi phục, việc tạo một transactionId không thay thế bằng chứng đó. Một định danh giao dịch chỉ giúp tìm giao dịch; quyền truy cập còn phụ thuộc vào cơ chế bảo vệ và trạng thái của nó.

## 4. Phản hồi công khai phải hạn chế dò tài khoản

OWASP khuyến nghị thông điệp nhất quán cho tài khoản tồn tại và không tồn tại, xử lý thời gian phản hồi để hạn chế dò tìm và chống gửi yêu cầu tự động quá mức. Đây là nền tảng cho việc bảo vệ quan hệ giữa định danh và thông tin liên hệ. [OWASP, Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request)

Ví dụ phản hồi công khai:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Nếu thông tin phù hợp, hướng dẫn sẽ được gửi qua phương thức đã đăng ký."
}
~~~

Thông báo này mô tả việc tiếp nhận yêu cầu, không khẳng định thư đã gửi hoặc tài khoản có tồn tại. Backend không cần trả thêm accountExists, contactCount hoặc recoveryEmail để giao diện hiển thị thông báo chung.

Cần xem cả hành vi của các endpoint liên quan. Nếu bước đầu trả thông báo chung nhưng endpoint kiểm tra trạng thái trả “email không tồn tại”, dữ liệu vẫn bị tiết lộ. Khác biệt ở mã lỗi, chuyển hướng, cấu trúc JSON hoặc trạng thái gửi lại cũng có thể làm lộ kết quả tra cứu.

Sử dụng xử lý bất đồng bộ có thể giúp tách phản hồi công khai khỏi tác vụ tra cứu và chuyển phát. Tuy nhiên, thêm một khoảng chờ cố định không tự làm mọi đường xử lý có phân bố thời gian giống nhau. Cần thiết kế nhất quán cả nhánh lỗi và tác vụ phụ.

Giới hạn tốc độ nên hỗ trợ chống dò tìm mà không biến chính phản hồi giới hạn theo tài khoản thành dấu hiệu xác nhận tài khoản tồn tại. Cũng cần tránh cho phép người ngoài làm nghẽn hộp thư hoặc chặn người dùng hợp lệ chỉ bằng cách gửi nhiều yêu cầu khôi phục.

## 5. Che một phần địa chỉ chưa đủ để bảo vệ quyền riêng tư

Giả sử địa chỉ minh họa là linh.nguyen@example.net. Gợi ý l***@example.net vẫn tiết lộ miền và ký tự đầu. Với email ở một tổ chức nhỏ, miền có thể là phần nhạy cảm nhất.

Tương tự, bốn chữ số cuối của điện thoại có thể giúp người ngoài đối chiếu với danh sách bị lộ. Mã quốc gia còn có thể cho biết khu vực liên hệ. Rủi ro phụ thuộc dữ liệu bên ngoài mà người quan sát đã có.

Một số nguyên tắc thiết kế gợi ý:

- Chỉ hiển thị gợi ý khi người yêu cầu đã đạt điều kiện xem lựa chọn.
- Tiết lộ lượng thông tin tối thiểu giúp phân biệt các lựa chọn cần thiết.
- Không mặc định email cần giữ nguyên miền hoặc điện thoại cần giữ nguyên mã quốc gia.
- Với chuỗi ngắn hoặc dữ liệu không thể che an toàn, dùng nhãn chung như “Email khôi phục đã đăng ký”.
- Không dùng số dấu sao để vô tình mô tả chính xác chiều dài địa chỉ gốc.
- Áp dụng cùng chính sách trên web, ứng dụng di động và kênh hỗ trợ.

Nhãn chung vẫn có thể tiết lộ rằng tài khoản có email khôi phục. Vì vậy, quyết định được hiển thị lựa chọn nào phải đi trước việc áp dụng hàm che.

Không có một số lượng ký tự cố định bảo đảm riêng tư cho mọi trường hợp. Thiết kế nên bắt đầu từ nhu cầu nhận biết của người dùng và rủi ro suy luận, thay vì chỉ chọn một mẫu che trông quen thuộc.

## 6. Backend quyết định dữ liệu trả về

Một lỗi phổ biến là API trả toàn bộ danh sách liên hệ rồi JavaScript mới che trước khi hiển thị. Người quan sát vẫn có thể đọc dữ liệu trong phản hồi mạng, trạng thái ứng dụng hoặc HTML ban đầu.

Ranh giới riêng tư cần nằm ở phía máy chủ:

~~~mermaid
flowchart LR
    A["Trình duyệt với quyền giới hạn"] --> B["API khôi phục"]
    B --> C["Kiểm tra quyền và mục đích"]
    C --> D["Bản chiếu dữ liệu tối thiểu"]
    D --> A
    C --> E["Kho thông tin liên hệ được bảo vệ"]
    E --> F["Dịch vụ chuyển phát được phép"]
    F --> G["Nhà cung cấp email hoặc SMS"]
~~~

Bản chiếu dữ liệu là tập trường được chủ động cho phép trả ra. Không nên tuần tự hóa trực tiếp đối tượng hồ sơ tài khoản rồi cố loại vài trường nhạy cảm ở cuối.

Ví dụ phản hồi sau khi đã đạt điều kiện xem lựa chọn:

~~~json
{
  "options": [
    {
      "optionHandle": "opaque-handle-for-this-transaction",
      "type": "EMAIL",
      "label": "Email khôi phục đã đăng ký"
    }
  ]
}
~~~

optionHandle trong ví dụ là định danh khó đoán, chỉ dùng trong giao dịch hiện tại và có thời hạn. Nó không chứa email đã mã hóa bằng Base64 và không phải ID toàn cục có thể dùng để dò các tài khoản khác.

Tên trường hoặc cấu trúc JSON không tự tạo ra bảo vệ. Backend vẫn phải kiểm tra quyền sở hữu giao dịch, phạm vi hành động, trạng thái xác minh, thời hạn và sự ràng buộc giữa lựa chọn với tài khoản.

Một cách mô tả việc tạo phản hồi bằng mã giả:

~~~text
getRecoveryOptions(recoveryContext):
    require context is valid and unexpired
    require policy permits VIEW_RECOVERY_OPTIONS
    account = loadAccountBoundToContext(recoveryContext)

    options = []
    for channel in channelsAllowedByPolicy(account, recoveryContext):
        options.add({
            optionHandle: issueTransactionScopedHandle(
                recoveryContext.id,
                account.id,
                channel.id,
                channel.version
            ),
            type: channel.type,
            label: buildPermittedLabel(channel, recoveryContext)
        })

    return options
~~~

Đây là mã giả về quyền tiết lộ, chưa phải triển khai hoàn chỉnh. Chỉ gọi hàm buildPermittedLabel sau khi chính sách đã cho phép xem lựa chọn; một hàm che đúng không sửa được lỗi kiểm soát truy cập ở phía trước.

## 7. Chọn kênh gửi bằng ràng buộc máy chủ

Ở bước gửi challenge, trình duyệt nên gửi lựa chọn được cấp cho giao dịch, thay vì tự cung cấp địa chỉ đích thay thế.

Ví dụ yêu cầu:

~~~json
{
  "optionHandle": "opaque-handle-for-this-transaction"
}
~~~

Máy chủ đối chiếu handle với giao dịch, tài khoản, contactId và phiên bản kênh. Dịch vụ chuyển phát chỉ nhận địa chỉ đầy đủ sau khi những kiểm tra đó thành công.

Nếu endpoint cho phép gửi tới một email bất kỳ do trình duyệt cung cấp, người yêu cầu có thể chuyển bí mật khôi phục sang địa chỉ của họ. Nếu endpoint chỉ kiểm tra contactId có tồn tại mà không kiểm tra nó thuộc đúng tài khoản và giao dịch, dữ liệu của người khác cũng có thể bị sử dụng sai phạm vi.

Nên phân biệt rõ:

- **Xác minh một địa chỉ mới:** chứng minh bên yêu cầu nhận được thông điệp ở địa chỉ đó.
- **Dùng kênh để khôi phục tài khoản cũ:** cần địa chỉ được ràng buộc hợp lệ với tài khoản theo chính sách.

Khả năng nhận email mới không tự chứng minh quyền thay email khôi phục của một tài khoản đã tồn tại.

Khi kênh thay đổi giữa lúc lựa chọn được hiển thị và lúc gửi, phiên bản ràng buộc giúp phát hiện quyết định đã cũ. Máy chủ có thể yêu cầu bắt đầu lại hoặc đánh giá lại theo chính sách; không âm thầm chuyển thông điệp sang một địa chỉ khác với lựa chọn đã được cho phép.

## 8. Bảo vệ dữ liệu khi lưu trữ và chuyển phát

Có thể tách bản ghi liên hệ thành các trường phục vụ mục đích riêng:

~~~text
RecoveryContact
  contactId
  accountId
  type
  encryptedDestination
  lookupReference
  verifiedAt
  version
  state
~~~

encryptedDestination chứa địa chỉ cần khôi phục khi gửi. lookupReference là tham chiếu phục vụ tra cứu theo thiết kế đã chọn, không phải dữ liệu để trả về công khai. verifiedAt ghi nhận thời điểm xác minh trong quá khứ, không bảo đảm kênh hiện vẫn an toàn.

Nếu dùng giá trị dẫn xuất để tra cứu email hoặc điện thoại, cần nhớ rằng không gian đầu vào có thể đoán được. Hash không khóa của số điện thoại có thể bị đối chiếu bằng danh sách ứng viên. Một phương án dùng HMAC với khóa riêng có thể giảm khả năng đối chiếu khi chỉ một bảng dữ liệu bị lộ, nhưng vẫn cần bảo vệ khóa và không biến dữ liệu thành vô danh.

OWASP khuyến nghị bảo vệ thông tin riêng tư trong truyền tải và lưu trữ bằng cơ chế mật mã phù hợp cùng kiểm soát truy cập. Mã hóa cần đi cùng phân quyền: một dịch vụ có quyền giải mã toàn bộ dữ liệu vẫn có thể làm lộ dữ liệu nếu endpoint của nó bị sử dụng sai. [OWASP, User Privacy Protection — Strong Cryptography](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html#strong-cryptography)

Trong kiến trúc có hàng đợi, có thể gửi contactId và phiên bản kênh tới dịch vụ chuyển phát thay vì sao chép địa chỉ vào mọi sự kiện. Dịch vụ gửi cần kiểm tra lại quyền và trạng thái trước khi phân giải địa chỉ. Thiết kế này phải quy định rõ việc xử lý khi kênh thay đổi hoặc tác vụ retry đến muộn.

Nhà cung cấp email hoặc SMS vẫn cần dữ liệu đích để thực hiện chuyển phát. Cần giới hạn dữ liệu gửi cho họ, phạm vi truy cập vào dashboard, log trả về và bản sao lưu trong hệ thống tích hợp. Một địa chỉ đã được loại khỏi log ứng dụng vẫn có thể xuất hiện trong lỗi của SDK hoặc payload hàng đợi.

## 9. Log, trace, analytics và công cụ hỗ trợ

Thông tin liên hệ thường bị nhân bản qua các đường phụ: log request, công cụ theo dõi lỗi, ghi lại phiên giao diện, ticket hỗ trợ hoặc ảnh chụp màn hình.

OWASP lưu ý token, thông tin phiên và dữ liệu cá nhân cần được loại bỏ hoặc xử lý phù hợp trước khi ghi log; email và số điện thoại cũng có thể cần xử lý riêng. Vì vậy, việc ghi nguyên request hoặc response của API khôi phục là một lựa chọn cần tránh khi không cần dữ liệu đó. [OWASP, Logging — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)

Ví dụ một sự kiện vận hành tối thiểu:

~~~json
{
  "event": "RECOVERY_CHALLENGE_REQUESTED",
  "interactionId": "opaque-interaction-reference",
  "contactReference": "restricted-contact-reference",
  "channelType": "EMAIL",
  "result": "ACCEPTED",
  "policyVersion": "contact-policy-v3"
}
~~~

Các tham chiếu vẫn có thể liên kết với một người qua hệ thống khác. Chúng cần được phân quyền và quản lý lưu giữ; không nên gọi dữ liệu này là hoàn toàn vô danh.

Không đưa địa chỉ email hoặc số điện thoại làm nhãn metric. Việc đó vừa mở rộng dữ liệu cá nhân sang hệ thống quan sát, vừa có thể tạo số lượng nhãn rất lớn. Chỉ số tổng hợp theo loại kênh và kết quả thường đủ cho nhu cầu vận hành cơ bản.

Công cụ hỗ trợ nên hiển thị nhãn hạn chế mặc định. Khi thật sự cần xem rõ, quyền đó cần gắn với vai trò, hồ sơ xử lý, lý do và dấu vết truy cập. Việc hỗ trợ một tài khoản không đồng nghĩa nhân viên được phép tra cứu mọi địa chỉ hoặc xuất toàn bộ danh sách.

Trong trao đổi hỗ trợ, cần tránh đọc đầy đủ email dự phòng hoặc số điện thoại cho một người chưa được xác minh. Không dùng chính dữ liệu nhân viên vừa tiết lộ làm câu hỏi xác minh tiếp theo.

## 10. Những đường tiết lộ dễ bị bỏ sót

### 10.1. URL và token

Không đặt email, số điện thoại hoặc địa chỉ dự phòng trong query string chỉ để tiện chuyển trang. URL có thể xuất hiện trong lịch sử trình duyệt, log máy chủ, công cụ phân tích hoặc các thành phần trung gian.

Một token có chữ ký không mặc nhiên che nội dung. Nếu cần biểu diễn một quyền khôi phục, nên hạn chế dữ liệu trong token và chọn cơ chế bảo mật phù hợp. Định danh ngẫu nhiên tham chiếu tới trạng thái máy chủ thường giúp tránh mang trực tiếp thông tin liên hệ ra phía người dùng.

### 10.2. Cache và trạng thái giao diện

Phản hồi chứa thông tin khôi phục cần chính sách cache phù hợp, chẳng hạn Cache-Control: no-store. Đồng thời cần quản lý dữ liệu trong bộ nhớ ứng dụng, localStorage, service worker và các công cụ ghi lại phiên; một header không tự xóa các bản sao đã được ứng dụng lưu riêng.

Trên máy dùng chung, trang khôi phục không nên để lại danh sách kênh liên hệ trong lịch sử điều hướng hoặc màn hình sau khi kết thúc phiên. Giao diện cần xử lý trạng thái hết hạn và đóng phiên giới hạn rõ ràng.

### 10.3. Khả năng truy cập và nhiều giao diện

Nếu chữ trên màn hình đã che nhưng thuộc tính aria-label chứa địa chỉ đầy đủ, thông tin vẫn bị đưa tới máy khách. Các trường ẩn, tooltip, thuộc tính HTML và dữ liệu dựng trang cũng cần tuân cùng chính sách.

Không để ứng dụng di động trả email đầy đủ trong khi web chỉ trả nhãn chung. Mức tiết lộ là quyết định của dịch vụ và quyền hiện tại, không phải sở thích của từng giao diện.

### 10.4. Thông báo thay đổi kênh

Thông báo xác nhận thay email hoặc số điện thoại có thể cần đến kênh cũ và kênh mới theo chính sách an toàn. Tuy nhiên, không cần gửi toàn bộ địa chỉ cũ cho người kiểm soát địa chỉ mới hoặc liệt kê tất cả kênh khác trong một thông báo.

Nội dung thông báo nên giúp người nhận nhận ra hành động và biết cách xử lý khi không yêu cầu thay đổi, đồng thời tránh tiết lộ thêm các mối liên hệ cá nhân không cần thiết.

## 11. Tình huống thiết kế: mất điện thoại nhưng còn khóa bảo mật

Linh mất điện thoại có ứng dụng MFA, nhưng vẫn giữ một khóa bảo mật đã đăng ký. Tài khoản có email chính và email dự phòng.

Một luồng minh họa có thể thực hiện như sau:

1. Người chưa xác minh nhập định danh và nhận thông báo chung.
2. Hệ thống cung cấp đường tiếp tục bằng phương thức bảo mật còn khả dụng mà không liệt kê dữ liệu liên hệ riêng.
3. Linh thực hiện xác minh bằng khóa bảo mật theo chính sách của tài khoản.
4. Máy chủ cấp quyền giới hạn cho việc quản lý phương thức bị mất.
5. Nếu cần chọn kênh liên hệ, máy chủ chỉ trả các lựa chọn được phép với nhãn tối thiểu.
6. Thông điệp được gửi đến kênh ràng buộc trong dữ liệu máy chủ.
7. Sau khi hoàn tất, quyền khôi phục giới hạn kết thúc và các thay đổi được thông báo theo chính sách.

Trong luồng này, khóa bảo mật không tự cho phép bỏ qua mọi yêu cầu để thay MFA. Chính sách vẫn phải xác định bằng chứng và quyền cần thiết cho hành động đó. Điểm về quyền riêng tư là hệ thống không cần công khai các địa chỉ chỉ để bắt đầu xử lý yêu cầu.

Nếu Linh không còn phương thức độc lập, hệ thống cần đường hỗ trợ hoặc xác minh khác phù hợp. Việc người dùng gặp khó không phải lý do để công bố toàn bộ danh sách liên hệ cho bất kỳ ai biết tên đăng nhập.

## 12. Bài tập phân tích ranh giới dữ liệu

Một API nhận tên đăng nhập rồi trả về:

~~~json
{
  "accountExists": true,
  "email": "linh.nguyen@example.net",
  "backupEmail": "linh.private@example.org",
  "phoneHint": "Số điện thoại kết thúc bằng 42",
  "canRemoveMfa": true
}
~~~

Giao diện chỉ hiển thị “Hướng dẫn đã được gửi” và che hai email trước khi vẽ lên màn hình.

Hãy phân tích:

1. Người chưa xác minh thực sự nhận được những dữ liệu nào?
2. Che ở giao diện có ngăn việc đọc dữ liệu qua phản hồi API không?
3. Những trường nào không cần cho thông báo tiếp nhận chung?
4. Trạng thái nào mới được phép xem lựa chọn khôi phục?
5. Backend cần ràng buộc optionHandle với những đối tượng và phiên bản nào?
6. Nếu email vừa thay đổi trước lúc gửi challenge, tác vụ chuyển phát phải xử lý ra sao?
7. Log nào vẫn đủ để điều tra yêu cầu mà không ghi địa chỉ và token?
8. Công cụ hỗ trợ cần giới hạn gì để tránh đọc thông tin riêng cho người giả mạo?

Một phương án thiết kế đầy đủ phải chỉ ra quyền xem dữ liệu ở mỗi bước, dữ liệu tối thiểu trả về và các bản sao nằm ngoài giao diện. Bảo vệ thông tin liên hệ là kiểm soát xuyên suốt luồng khôi phục, từ API công khai đến dịch vụ gửi và công cụ vận hành.
