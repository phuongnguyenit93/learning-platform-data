# Password manager support: thiết kế luồng đăng nhập tương thích và an toàn

Password manager là công cụ giúp người dùng tạo, lưu, điền và đồng bộ thông tin đăng nhập. Công cụ có thể tích hợp trong trình duyệt, hệ điều hành, thiết bị di động hoặc hoạt động dưới dạng ứng dụng và tiện ích mở rộng độc lập. Khi được hỗ trợ tốt, password manager giúp người dùng sử dụng mật khẩu dài, duy nhất cho từng dịch vụ, giảm việc tái sử dụng mật khẩu và hạn chế lỗi nhập liệu.

Với hệ thống xác thực, hỗ trợ password manager là một phần của trải nghiệm đăng nhập an toàn. Một biểu mẫu không có nhãn rõ ràng, trường nhập liệu bị tạo động, autocomplete bị tắt, nút paste bị chặn hoặc luồng đăng nhập nhiều bước thiếu ngữ nghĩa có thể khiến công cụ không nhận diện được trường thông tin. Người dùng khi đó có xu hướng đặt mật khẩu dễ nhớ hơn, dùng lại mật khẩu hoặc lưu bí mật ở nơi kém an toàn.

Bài học này giải thích cách thiết kế biểu mẫu, luồng đăng ký, đăng nhập, đổi mật khẩu, MFA và passkey để các password manager phổ biến có thể hoạt động thuận lợi. Trọng tâm là giữ cho trình duyệt và công cụ quản lý mật khẩu nhận biết đúng ngữ cảnh, đồng thời bảo vệ ranh giới tin cậy, credential và phiên của hệ thống SECURITY_AUTHENTICATION_FUNDAMENTALS.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò và giới hạn của password manager trong vòng đời credential.
- Thiết kế biểu mẫu đăng nhập, đăng ký, đổi mật khẩu và khôi phục với ngữ nghĩa HTML phù hợp.
- Sử dụng thuộc tính autocomplete, name, type và label đúng mục đích.
- Cho phép tạo, dán, điền tự động và sử dụng mật khẩu dài, phức tạp hoặc có Unicode.
- Tích hợp trải nghiệm password manager với MFA, OTP và passkey.
- Nhận diện các thiết kế làm hỏng autofill hoặc khiến người dùng tiết lộ bí mật.
- Kiểm thử khả năng tương thích trên trình duyệt, thiết bị di động và các luồng xác thực khác nhau.
- Đánh giá trải nghiệm dựa trên khả năng hoàn thành tác vụ và bảo vệ người dùng, không dựa vào việc phát hiện họ đang dùng công cụ nào.

## 1. Password manager là gì?

Password manager là phần mềm quản lý bí mật xác thực thay cho trí nhớ của người dùng. Tùy sản phẩm, nó có thể:

- Tạo mật khẩu ngẫu nhiên có độ dài và tập ký tự phù hợp.
- Lưu username, password, địa chỉ website và metadata tài khoản.
- Điền thông tin đăng nhập vào biểu mẫu.
- Đồng bộ kho mật khẩu giữa các thiết bị.
- Cảnh báo mật khẩu yếu, trùng lặp hoặc xuất hiện trong dữ liệu rò rỉ.
- Lưu passkey, mã OTP, recovery code hoặc ghi chú bảo mật.
- Hỗ trợ chia sẻ credential có kiểm soát trong nhóm hoặc gia đình.

Password manager có thể là tính năng tích hợp của trình duyệt, hệ điều hành, thiết bị di động hoặc ứng dụng của bên thứ ba. Một số công cụ dùng extension để nhận diện trường biểu mẫu; một số dựa vào cơ chế autofill của nền tảng. Cách hoạt động khác nhau, vì vậy website nên cung cấp ngữ nghĩa tiêu chuẩn thay vì phụ thuộc vào hành vi riêng của một nhà cung cấp.

### 1.1. Password manager nằm ở đâu trong ranh giới tin cậy?

Một luồng điển hình:

1. Người dùng mở website hoặc ứng dụng chính thức.
2. Trình duyệt hoặc hệ điều hành nhận diện origin và biểu mẫu.
3. Password manager chọn credential phù hợp với website và điền vào trường.
4. Người dùng xác nhận đăng nhập.
5. Ứng dụng gửi thông tin xác thực qua kênh TLS đến máy chủ.
6. Máy chủ xác minh credential và tạo phiên hoặc trả kết quả xác thực.

Password manager thường lưu bí mật ở kho riêng của người dùng hoặc dịch vụ đồng bộ của nhà cung cấp. Website không cần biết người dùng đang dùng sản phẩm nào và không được yêu cầu quyền truy cập vào kho đó.

Ranh giới quan trọng:

- Password manager kiểm soát việc lưu và điền credential ở phía người dùng.
- Website kiểm soát origin, biểu mẫu, truyền dữ liệu, xác minh credential và tạo phiên.
- Identity provider có thể thực hiện xác thực trong một origin riêng.
- Trình duyệt và hệ điều hành quyết định cách hiển thị, gợi ý và điền thông tin.
- Máy chủ phải giả định rằng mọi dữ liệu gửi lên đều không đáng tin cậy cho đến khi được xác minh.

Không có cơ chế chuẩn đáng tin cậy để website xác định chính xác người dùng đang dùng password manager nào. Đừng xây dựng chính sách bảo mật dựa trên việc phát hiện extension, user-agent hoặc hành vi autofill.

### 1.2. Password manager giúp giảm rủi ro nào?

| Rủi ro | Password manager hỗ trợ như thế nào | Giới hạn cần hiểu |
|---|---|---|
| Tái sử dụng mật khẩu | Tạo và lưu mật khẩu riêng cho từng dịch vụ | Người dùng vẫn có thể tự chọn mật khẩu trùng hoặc không dùng công cụ |
| Mật khẩu yếu | Tạo chuỗi ngẫu nhiên dài | Chính sách server vẫn phải chấp nhận mật khẩu tốt và không cắt ngắn |
| Quên mật khẩu | Lưu và tìm lại credential | Mất quyền truy cập kho mật khẩu vẫn cần quy trình recovery của dịch vụ |
| Phishing | Có thể gắn credential với website/origin và từ chối điền ở origin khác | Không phải công cụ nào cũng có cùng mức bảo vệ; người dùng vẫn có thể tự nhập vào trang giả |
| Lỗi nhập liệu | Điền tự động và hỗ trợ paste | Biểu mẫu không có ngữ nghĩa hoặc luồng bất thường có thể làm autofill thất bại |
| Rò rỉ mật khẩu | Một số công cụ cảnh báo mật khẩu bị lộ hoặc trùng | Không thay thế giám sát rò rỉ, MFA, bảo vệ server hoặc ứng phó sự cố |

### 1.3. Password manager không thay thế xác thực phía máy chủ

Máy chủ vẫn phải:

- Bảo vệ mật khẩu đã lưu bằng password hashing chuyên dụng, salt riêng và tham số phù hợp.
- Giới hạn tốc độ đăng nhập và chống credential stuffing.
- Xác minh MFA hoặc passkey theo policy.
- Bảo vệ session cookie, token và CSRF.
- Hỗ trợ đổi mật khẩu, thu hồi phiên và khôi phục tài khoản an toàn.
- Không ghi mật khẩu hoặc token thô vào log.

Việc trình duyệt tự động điền một mật khẩu không làm cho mật khẩu đó đáng tin cậy hơn. Mọi credential đều phải được xác minh theo cùng chính sách ở phía server.

## 2. Nguyên tắc thiết kế để tương thích

Một website hỗ trợ password manager tốt thường có những đặc điểm sau:

1. Dùng phần tử HTML chuẩn cho username và password.
2. Đặt label hiển thị, name ổn định và autocomplete đúng ngữ cảnh.
3. Giữ trường nhập liệu trong form có cấu trúc rõ ràng.
4. Cho phép paste, autofill và mật khẩu dài.
5. Không thay đổi giá trị người dùng nhập bằng cách trim, cắt chuỗi hoặc đổi ký tự ngoài policy đã công bố.
6. Không dùng JavaScript để che giấu trường hoặc làm giả một input khác.
7. Giữ origin đăng nhập ổn định và dễ nhận diện.
8. Cho phép password manager hoạt động cùng MFA và passkey.
9. Cung cấp thông báo lỗi hữu ích mà không tiết lộ tài khoản có tồn tại hay không.
10. Kiểm thử với công cụ và nền tảng thực tế.

### 2.1. Ngữ nghĩa quan trọng hơn mẹo riêng của từng công cụ

Password manager có thể dùng nhiều tín hiệu để nhận diện trường:

- Thuộc tính type.
- Thuộc tính name và id.
- Label liên kết với input.
- Placeholder và nội dung xung quanh.
- Thuộc tính autocomplete.
- Vị trí trường trong form.
- Origin, action và ngữ cảnh điều hướng.
- Lịch sử credential đã lưu cho website.

Không nên phụ thuộc vào một tín hiệu đơn lẻ. Ví dụ, chỉ đặt placeholder “Password” nhưng không có label sẽ làm trải nghiệm truy cập kém và có thể khiến autofill khó nhận diện. Một trường có tên chung chung như field1 cũng không giúp trình duyệt hiểu vai trò.

## 3. Thiết kế biểu mẫu đăng nhập

### 3.1. Dùng autocomplete đúng ngữ cảnh

Với biểu mẫu đăng nhập, các giá trị phổ biến:

| Trường | Thuộc tính gợi ý | Mục đích |
|---|---|---|
| Username hoặc email | autocomplete="username" | Cho biết đây là định danh dùng để đăng nhập |
| Mật khẩu hiện tại | autocomplete="current-password" | Cho biết trường nhận mật khẩu đã có |
| Mã OTP | autocomplete="one-time-code" | Cho phép nền tảng hỗ trợ gợi ý mã dùng một lần |

Ví dụ:

~~~html
<form action="/login" method="post">
  <label for="login-username">Email hoặc tên đăng nhập</label>
  <input
    id="login-username"
    name="username"
    type="text"
    autocomplete="username"
    required
  >

  <label for="login-password">Mật khẩu</label>
  <input
    id="login-password"
    name="password"
    type="password"
    autocomplete="current-password"
    required
  >

  <button type="submit">Đăng nhập</button>
</form>
~~~

Nếu định danh bắt buộc là email, có thể dùng type="email" cùng autocomplete="username". Nếu người dùng có thể đăng nhập bằng username hoặc email, type="text" thường phù hợp hơn để không áp đặt định dạng email.

### 3.2. Giữ form và trường nhập liệu ổn định

- Mỗi input cần id và name ổn định, có ý nghĩa.
- Label phải liên kết với input bằng for và id.
- Dùng type="password" cho trường mật khẩu.
- Dùng một form đăng nhập rõ ràng, có nút submit thật.
- Không đổi name hoặc id liên tục sau mỗi lần render.
- Không tạo nhiều trường mật khẩu giả để đánh lừa autofill.
- Không dùng hidden input chứa bản sao mật khẩu.
- Không tách input khỏi form bằng JavaScript nếu không cần thiết.
- Không thay giá trị input bằng một chuỗi đã mã hóa ở phía client rồi gửi lên, trừ khi đó là giao thức xác thực được thiết kế và phân tích riêng.

Biểu mẫu có cấu trúc nhất quán giúp công cụ nhận biết trường và giảm lỗi khi người dùng đăng nhập bằng bàn phím, trình đọc màn hình hoặc autofill.

### 3.3. Không chặn paste hoặc autofill

Không vô hiệu hóa các hành vi sau:

- Dán mật khẩu từ password manager.
- Dán mật khẩu từ clipboard.
- Chọn và điền credential do trình duyệt gợi ý.
- Sử dụng bàn phím hoặc cơ chế autofill của hệ điều hành.

Không dùng sự kiện JavaScript để chặn paste, xóa giá trị vừa được autofill hoặc bắt người dùng gõ lại từng ký tự. Các hành vi này không làm password mạnh hơn và có thể khuyến khích người dùng chọn mật khẩu dễ nhớ.

### 3.4. Tránh tắt autocomplete

Không đặt autocomplete="off" cho trường username và password với mục đích ngăn password manager. Trình duyệt có thể vẫn cho phép lưu hoặc điền mật khẩu, nhưng cấu hình này làm mất tín hiệu ngữ nghĩa và có thể ảnh hưởng đến hỗ trợ truy cập.

Hãy dùng giá trị cụ thể như username, current-password, new-password hoặc one-time-code tùy trường. Chỉ tắt autocomplete cho dữ liệu thực sự không nên được tự động gợi ý, sau khi đánh giá nhu cầu và hành vi trình duyệt.

### 3.5. Không cắt ngắn mật khẩu

Một số lỗi phổ biến:

- Đặt maxlength quá thấp.
- Cắt chuỗi ở server theo giới hạn cũ.
- Chỉ cho phép một nhóm ký tự nhỏ.
- Loại bỏ khoảng trắng ở đầu hoặc cuối một cách âm thầm.
- Chuyển chữ hoa thành chữ thường.
- Tự chuẩn hóa Unicode không nhất quán.
- Chặn ký tự được password manager tạo ra.

Nếu giới hạn độ dài để bảo vệ tài nguyên, hãy chọn giới hạn đủ lớn, công bố rõ ràng và áp dụng nhất quán ở client lẫn server. Không được âm thầm cắt mật khẩu; người dùng có thể tưởng rằng hệ thống đã lưu đúng chuỗi trong khi server xác minh một chuỗi khác.

## 4. Thiết kế đăng ký và tạo mật khẩu mới

Khi người dùng đăng ký hoặc đổi mật khẩu, password manager cần nhận ra đây là trường tạo credential mới để có thể đề xuất mật khẩu mạnh và lưu nó sau khi gửi form.

### 4.1. Dùng autocomplete="new-password"

Ví dụ:

~~~html
<form action="/register" method="post">
  <label for="new-username">Email</label>
  <input
    id="new-username"
    name="username"
    type="email"
    autocomplete="username"
    required
  >

  <label for="new-password">Tạo mật khẩu</label>
  <input
    id="new-password"
    name="password"
    type="password"
    autocomplete="new-password"
    required
  >

  <label for="confirm-password">Nhập lại mật khẩu</label>
  <input
    id="confirm-password"
    name="passwordConfirmation"
    type="password"
    autocomplete="new-password"
    required
  >

  <button type="submit">Tạo tài khoản</button>
</form>
~~~

autocomplete="new-password" cho trình duyệt biết đây là trường tạo hoặc đặt mật khẩu mới. Nó giúp password manager phân biệt mật khẩu mới với mật khẩu hiện tại.

### 4.2. Tránh quy tắc mật khẩu gây cản trở

Một chính sách tốt nên:

- Chấp nhận mật khẩu dài và passphrase.
- Cho phép các ký tự in được và khoảng trắng theo cách xử lý nhất quán.
- Không bắt buộc các quy tắc tổ hợp ký tự tùy tiện nếu không có cơ sở rủi ro rõ ràng.
- Kiểm tra mật khẩu phổ biến hoặc đã bị lộ bằng blocklist phù hợp.
- Không yêu cầu đổi mật khẩu định kỳ nếu không có bằng chứng xâm phạm hoặc yêu cầu chính sách cụ thể.
- Không đặt giới hạn tối đa quá thấp.
- Không âm thầm thay đổi chuỗi người dùng nhập.

Nếu hệ thống xử lý Unicode, cần định nghĩa rõ cách đo độ dài và cách xử lý encoding. Không tự ý normalize ở một tầng nhưng không normalize ở tầng khác. Cùng một chuỗi người dùng nhập phải được xử lý nhất quán trong đăng ký, đăng nhập, đổi mật khẩu và xác minh lại.

### 4.3. Hiển thị yêu cầu trước khi người dùng tạo mật khẩu

Cho người dùng biết yêu cầu trước khi password manager tạo mật khẩu. Nếu hệ thống có giới hạn ký tự hoặc độ dài đặc biệt, công bố ngay cạnh trường. Đừng chỉ hiển thị lỗi sau khi form gửi đi.

Tốt nhất là tránh các giới hạn không cần thiết để password manager có thể tạo chuỗi mạnh theo cấu hình thông thường. Nếu có lý do kỹ thuật phải giới hạn, cần thử với các mật khẩu rất dài và các ký tự đặc biệt để chắc chắn client và server xử lý giống nhau.

### 4.4. Trường xác nhận mật khẩu

Một số password manager có thể điền cùng mật khẩu mới vào cả hai trường nếu chúng có ngữ nghĩa phù hợp. Trường xác nhận không nên là một bài kiểm tra chống bot hoặc buộc người dùng nhập lại bằng tay.

Nếu dùng trường xác nhận:

- Dùng autocomplete="new-password" cho cả hai trường.
- Đặt label riêng và thông báo rõ khi hai giá trị không khớp.
- Không hiển thị mật khẩu trong thông báo lỗi.
- Không gửi hoặc lưu riêng bản xác nhận.
- Không dùng JavaScript để cản trở việc điền tự động.

Có thể bỏ trường xác nhận nếu trải nghiệm, khả năng hiển thị mật khẩu và cơ chế sửa lỗi đã đủ tốt.

## 5. Đổi mật khẩu và cập nhật credential

Luồng đổi mật khẩu thường có cả mật khẩu hiện tại và mật khẩu mới. Ngữ nghĩa autocomplete cần phản ánh chính xác:

~~~html
<form action="/account/password" method="post">
  <label for="current-password">Mật khẩu hiện tại</label>
  <input
    id="current-password"
    name="currentPassword"
    type="password"
    autocomplete="current-password"
    required
  >

  <label for="replacement-password">Mật khẩu mới</label>
  <input
    id="replacement-password"
    name="newPassword"
    type="password"
    autocomplete="new-password"
    required
  >

  <button type="submit">Cập nhật mật khẩu</button>
</form>
~~~

Máy chủ nên xác minh lại mật khẩu hiện tại hoặc yêu cầu step-up authentication theo mức rủi ro. Sau khi đổi mật khẩu:

- Cập nhật password verifier theo cơ chế an toàn.
- Xem xét thu hồi các phiên và refresh token khác theo policy.
- Gửi thông báo bảo mật qua kênh đã xác minh.
- Không gửi mật khẩu mới trong email hoặc thông báo.
- Cho người dùng kiểm tra thiết bị và phiên đang hoạt động.
- Giữ recovery path khả dụng nếu người dùng mất password manager.

Đổi mật khẩu không tự động đảm bảo mọi phiên đã bị hủy. Session store và token service cần thực hiện hành động thu hồi tương ứng.

## 6. Khôi phục tài khoản và password manager

Password manager giúp người dùng tránh quên mật khẩu, nhưng dịch vụ vẫn phải hỗ trợ trường hợp người dùng mất thiết bị, quên master password, mất quyền truy cập kho đồng bộ hoặc không còn credential đã lưu.

### 6.1. Phân biệt mất mật khẩu với mất kho mật khẩu

Đây là hai sự cố khác nhau:

- **Mất mật khẩu của tài khoản:** người dùng cần xác minh quyền kiểm soát tài khoản theo recovery policy của dịch vụ.
- **Mất quyền truy cập password manager:** người dùng cần khôi phục kho theo cơ chế của nhà cung cấp password manager.

Website không thể khôi phục master password của một password manager bên ngoài. Website cũng không nên yêu cầu người dùng gửi master password, export vault hoặc chia sẻ toàn bộ kho credential để chứng minh danh tính.

### 6.2. Thiết kế recovery không phụ thuộc một nhà cung cấp

- Cho phép người dùng dùng phương thức xác minh đã đăng ký và được policy chấp nhận.
- Cung cấp recovery code hoặc phương thức dự phòng có thể lưu an toàn.
- Không bắt buộc một password manager cụ thể.
- Không dùng câu hỏi bảo mật dễ đoán làm yếu tố duy nhất.
- Có thời gian chờ hoặc thông báo khi thay đổi yếu tố có rủi ro cao.
- Thu hồi token khôi phục sau khi sử dụng.
- Ghi audit event và thông báo cho chủ tài khoản.
- Kiểm tra các phiên và yếu tố MFA sau khi recovery hoàn tất.

### 6.3. Recovery code và password manager

Người dùng có thể lưu recovery code trong password manager, nhưng hệ thống nên cung cấp lựa chọn tải xuống hoặc ghi lại an toàn theo policy. Recovery code phải có entropy đủ lớn, hiển thị một lần khi tạo, lưu verifier an toàn ở server và vô hiệu hóa sau khi sử dụng.

Không nên buộc người dùng lưu recovery code trong một sản phẩm cụ thể. Hãy giải thích rằng mã khôi phục là bí mật có quyền cao, cần bảo vệ như credential.

## 7. Hỗ trợ MFA và OTP autofill

Password manager và hệ điều hành có thể lưu hoặc gợi ý mã OTP. Trên nền tảng hỗ trợ, thuộc tính autocomplete="one-time-code" giúp nhận diện trường mã dùng một lần.

Ví dụ:

~~~html
<form action="/mfa/verify" method="post">
  <label for="otp-code">Mã xác minh</label>
  <input
    id="otp-code"
    name="oneTimeCode"
    type="text"
    inputmode="numeric"
    autocomplete="one-time-code"
    pattern="[0-9]{6}"
    required
  >
  <button type="submit">Xác minh</button>
</form>
~~~

Ví dụ trên minh họa mã sáu chữ số; độ dài và alphabet phải khớp với phương thức OTP thực tế. Không ép mọi loại mã MFA thành số sáu chữ số nếu giao thức hoặc nhà cung cấp dùng định dạng khác.

### 7.1. Tránh giao diện OTP gây lỗi autofill

- Nếu mã gồm nhiều chữ số, ưu tiên một trường nhập liệu thay vì sáu ô tách rời.
- Nếu thiết kế nhiều ô vì lý do UX, phải hỗ trợ paste toàn bộ mã và phân phối ký tự đúng thứ tự.
- Không tự động submit ngay khi autofill đang điền từng ký tự nếu có nguy cơ gửi mã chưa đầy đủ.
- Không xóa giá trị khi focus hoặc khi trình duyệt điền.
- Không chặn bàn phím hoặc paste.
- Cho phép nhập mã bằng bàn phím, paste và autofill.
- Hiển thị thời hạn mã và cách yêu cầu mã mới.
- Không ghi OTP vào log, analytics hoặc thông báo lỗi.

### 7.2. MFA vẫn phải được xác minh ở server

Autofill chỉ là tiện ích nhập liệu. Server vẫn phải kiểm tra:

- Mã đúng với tài khoản và giao dịch.
- Mã còn hiệu lực theo cửa sổ thời gian.
- Mã chưa được sử dụng nếu policy yêu cầu one-time.
- Số lần thử và tốc độ gửi lại được giới hạn.
- Trạng thái enrollment và recovery phù hợp.
- Challenge gắn với đúng phiên hoặc giao dịch.

Không xem việc password manager điền OTP là bằng chứng người dùng đã vượt qua MFA. Chỉ kết quả xác minh phía server mới có giá trị.

## 8. Password manager và passkey

Passkey là credential mật mã khóa công khai, thường được tạo và lưu trong authenticator hoặc credential manager của nền tảng. Passkey có thể đồng bộ giữa các thiết bị theo cơ chế của nhà cung cấp hoặc được giữ trong security key.

Password manager hiện đại có thể hỗ trợ cả mật khẩu và passkey. Website nên cho phép các phương thức này cùng tồn tại khi policy hỗ trợ.

### 8.1. Thiết kế lựa chọn phương thức đăng nhập

- Hiển thị rõ lựa chọn dùng passkey hoặc mật khẩu.
- Dùng WebAuthn API và xử lý kết quả theo chuẩn.
- Cho phép authenticator nền tảng, security key và cross-device authentication nếu được hỗ trợ.
- Không buộc người dùng dùng một thương hiệu password manager hoặc một hệ điều hành.
- Cung cấp fallback phù hợp với assurance policy.
- Không hạ cấp âm thầm sang mật khẩu yếu hơn khi passkey thất bại.
- Giải thích lỗi theo hướng dẫn người dùng có thể thực hiện.

### 8.2. Ngữ nghĩa và trải nghiệm passkey

Passkey không phải trường mật khẩu. Không đặt passkey vào input password hoặc yêu cầu người dùng copy private key. Trình duyệt và hệ điều hành quản lý thao tác chọn authenticator, xác minh người dùng và trả về assertion.

Website cần:

- Gọi đúng WebAuthn flow và xác minh challenge.
- Kiểm tra origin, RP ID, chữ ký và user verification theo policy.
- Ràng buộc credential với đúng tài khoản trong enrollment.
- Cho phép người dùng quản lý và thu hồi passkey.
- Hỗ trợ nhiều authenticator hoặc phương thức recovery phù hợp.
- Không coi một nhãn “đã dùng passkey” là bằng chứng đủ nếu assertion không được xác minh.

### 8.3. Password manager không đồng nghĩa passkey provider

Một password manager có thể lưu passkey, nhưng không phải mọi công cụ đều hỗ trợ mọi nền tảng hoặc cách đồng bộ. Trải nghiệm phải dựa trên khả năng của browser/platform API và thông báo lỗi rõ ràng, không giả định người dùng có một sản phẩm nhất định.

## 9. Origin, phishing và nhận diện website

Một lợi ích của autofill theo origin là password manager có thể gợi ý credential cho website đã lưu. Điều này có thể giúp người dùng nhận ra trang đăng nhập giả mạo nếu công cụ không điền thông tin ở origin khác.

Tuy nhiên, website cần thiết kế để người dùng dễ xác định đúng origin:

- Dùng domain đăng nhập ổn định và được công bố rõ.
- Tránh chuyển qua nhiều domain không cần thiết.
- Không nhúng biểu mẫu mật khẩu vào iframe từ origin không rõ.
- Nếu dùng identity provider bên ngoài, giải thích rõ người dùng sẽ được chuyển đến domain nào.
- Giữ TLS và hostname verification đúng.
- Không yêu cầu người dùng nhập mật khẩu của website A vào form của website B.
- Không yêu cầu copy credential sang trang khác để tiếp tục đăng nhập.

### 9.1. Luồng liên kết danh tính và domain của IdP

Với đăng nhập liên kết, người dùng có thể đi qua origin của ứng dụng, identity provider và callback. Password manager thường gắn credential với origin nơi người dùng nhập nó. Vì vậy:

- Nếu người dùng tạo credential trên domain IdP, họ có thể thấy credential được lưu dưới domain IdP.
- Không nên cố ép password manager lưu cùng credential dưới nhiều origin bằng JavaScript.
- Hướng dẫn domain phải chính xác và tránh gây nhầm lẫn.
- Không nhận credential trực tiếp ở RP nếu thiết kế yêu cầu IdP xác thực.
- Xác minh state, nonce, redirect URI và issuer trong callback.

### 9.2. Tránh iframe chứa form đăng nhập

Autofill trong iframe có thể bị giới hạn theo trình duyệt, chính sách quyền hoặc origin. Iframe cross-origin còn làm ranh giới tin cậy phức tạp hơn.

Nếu có thể, dùng chuyển hướng đến trang đăng nhập chính thức của IdP thay vì nhúng trường mật khẩu từ domain khác. Nếu kiến trúc buộc phải dùng iframe, cần đánh giá origin, sandbox, permissions policy, clickjacking, autofill behavior và kiểm thử trên các nền tảng mục tiêu.

## 10. Tương thích trên thiết bị di động và ứng dụng native

Trên thiết bị di động, autofill có thể do hệ điều hành, trình duyệt hoặc password manager cung cấp. Trải nghiệm tốt cần tận dụng API chuẩn của nền tảng.

### 10.1. Website trên trình duyệt di động

- Giữ label và autocomplete chuẩn.
- Dùng input type phù hợp để hiện bàn phím đúng.
- Tránh layout làm trường bị che khi bàn phím hoặc autofill suggestion xuất hiện.
- Đảm bảo nút submit không bị che hoặc quá nhỏ.
- Không xóa focus khi người dùng chọn suggestion.
- Kiểm thử ở chế độ xoay màn hình, zoom và kích thước chữ lớn.
- Không phụ thuộc vào hover hoặc thao tác chuột.

### 10.2. Ứng dụng native

Ứng dụng native cần khai báo semantic content type hoặc autofill hint tương ứng cho username, password, new password và one-time code. Tên API cụ thể tùy hệ điều hành và framework.

Các nguyên tắc:

- Dùng API autofill chính thức của nền tảng.
- Đánh dấu trường đúng loại thay vì chỉ đổi placeholder.
- Không chặn paste hoặc accessibility action.
- Không dùng WebView tự chế để thay thế trình quản lý credential của nền tảng nếu không có lý do rõ ràng.
- Kiểm thử trên thiết bị thật và phiên bản OS được hỗ trợ.
- Bảo vệ dữ liệu nhạy cảm trong log, crash report và analytics.

### 10.3. Ứng dụng hybrid và WebView

WebView có thể không có cùng hành vi autofill với trình duyệt đầy đủ. Trước khi chọn giải pháp:

- Kiểm tra khả năng autofill của phiên bản nền tảng mục tiêu.
- Xác định credential được nhập ở origin nào.
- Kiểm tra bridge JavaScript/native có vô tình đọc hoặc log mật khẩu không.
- Không chuyển password qua deep link, query string hoặc clipboard để nối các màn hình.
- Ưu tiên cơ chế đăng nhập hệ thống hoặc browser-based flow được nền tảng hỗ trợ khi phù hợp.

## 11. Khả năng truy cập và trải nghiệm sử dụng

Hỗ trợ password manager cần đi cùng accessibility. Người dùng có thể dùng bàn phím, trình đọc màn hình, zoom, switch control hoặc công nghệ hỗ trợ khác.

### 11.1. Label và thông báo

- Dùng label hiển thị cho mỗi trường.
- Không chỉ dùng placeholder làm label.
- Gắn lỗi với trường liên quan qua cơ chế hỗ trợ truy cập như aria-describedby.
- Giữ focus hợp lý khi có lỗi.
- Không thông báo mật khẩu hoặc OTP trong nội dung live region.
- Dùng ngôn ngữ rõ ràng, ngắn gọn và có hướng dẫn sửa lỗi.
- Đảm bảo trạng thái show/hide password có tên truy cập được.

### 11.2. Nút hiển thị mật khẩu

Nút show/hide có thể giúp người dùng kiểm tra giá trị vừa nhập. Hãy dùng button thật, có label rõ và không submit form ngoài ý muốn.

Ví dụ:

~~~html
<label for="password">Mật khẩu</label>
<div class="password-field">
  <input
    id="password"
    name="password"
    type="password"
    autocomplete="current-password"
  >
  <button type="button" aria-pressed="false">
    Hiện mật khẩu
  </button>
</div>
~~~

Ví dụ chỉ minh họa cấu trúc. Logic chuyển type phải giữ nguyên giá trị, focus và trạng thái trợ năng. Không gửi giá trị mật khẩu đến analytics khi người dùng bật hoặc tắt chế độ hiển thị.

### 11.3. Không gây bất ngờ khi autofill

Một số biểu mẫu dùng màu nền hoặc style riêng cho trường autofill. Đảm bảo text vẫn đọc được và không che nút, label hoặc thông báo. Không dùng script xóa giá trị chỉ vì trường có trạng thái autofill.

## 12. Bảo vệ clipboard và dữ liệu nhập

Clipboard là một kênh thuận tiện nhưng cũng có rủi ro. Hệ thống nên cho phép người dùng dán credential, đồng thời không tự sao chép hoặc lưu bí mật ngoài ý muốn.

- Không chặn paste password, OTP hoặc recovery code.
- Không tự động copy mật khẩu sang clipboard khi người dùng không yêu cầu.
- Nếu có nút copy recovery code, giải thích rõ và cho người dùng chủ động kích hoạt.
- Không ghi nội dung clipboard vào log hoặc telemetry.
- Không giữ bản sao credential trong biến toàn cục hoặc local storage không cần thiết.
- Xóa dữ liệu nhạy cảm khỏi state/UI khi kết thúc tác vụ nếu phù hợp với kiến trúc.
- Không yêu cầu người dùng paste mật khẩu vào chat hỗ trợ hoặc biểu mẫu bên ngoài origin chính thức.

Đối với ứng dụng native, hành vi clipboard có thể khác nhau theo OS. Nếu sản phẩm cung cấp tính năng copy, cần đánh giá thời gian lưu clipboard, cảnh báo hệ điều hành và khả năng ứng dụng khác đọc dữ liệu.

## 13. Bảo vệ server và giao thức khi hỗ trợ autofill

Hỗ trợ password manager không làm giảm yêu cầu bảo mật server. Một số nguyên tắc:

### 13.1. Truyền dữ liệu

- Chỉ gửi credential qua HTTPS/TLS.
- Dùng POST cho form đăng nhập và không đặt mật khẩu trong URL.
- Không đưa password, OTP, recovery code hoặc token vào query string.
- Không gửi credential đến origin không được xác minh.
- Bảo vệ CSRF theo kiến trúc session và cookie.
- Không để redirect chuyển header Authorization hoặc dữ liệu nhạy cảm đến host ngoài dự kiến.

### 13.2. Xác minh và lưu trữ

- Dùng password hashing chuyên dụng và tham số được quản lý.
- Giới hạn tốc độ, phát hiện credential stuffing và bảo vệ thông tin đăng nhập.
- Xử lý lỗi chung để tránh account enumeration.
- Không log request body đăng nhập.
- Không trả password hash, salt hoặc secret trong API.
- Quản lý session rotation, idle timeout, absolute lifetime và logout.
- Hỗ trợ thu hồi token/phiên khi credential bị thay đổi hoặc tài khoản có dấu hiệu bị chiếm.

### 13.3. Chống brute force và credential stuffing

Không dùng việc chặn paste, autofill hoặc password manager như biện pháp chống bot. Các biện pháp phù hợp nằm ở phía server và lớp chống lạm dụng:

- Rate limit theo tài khoản, nguồn, thiết bị hoặc tín hiệu rủi ro.
- Phát hiện nhiều lần thử credential trên nhiều tài khoản.
- Theo dõi IP/ASN và hành vi mà không dựa vào một tín hiệu đơn lẻ.
- Dùng MFA hoặc step-up theo rủi ro.
- Giới hạn thông tin trong phản hồi lỗi.
- Có quy trình xử lý tài khoản bị tấn công và thu hồi phiên.

Không khóa tài khoản vĩnh viễn chỉ dựa vào số lần nhập sai dễ bị kẻ tấn công lợi dụng để gây từ chối dịch vụ.

## 14. Các lỗi UX thường làm password manager thất bại

| Lỗi thiết kế | Hệ quả | Cách sửa |
|---|---|---|
| autocomplete="off" trên password | Mất gợi ý ngữ nghĩa, có thể cản autofill ở một số môi trường | Dùng current-password hoặc new-password |
| Chặn paste | Người dùng không thể dán mật khẩu mạnh | Cho phép paste và autofill |
| maxlength quá thấp | Mật khẩu do manager tạo có thể bị cắt hoặc từ chối | Đặt giới hạn đủ lớn, nhất quán và được công bố |
| Không có label | Khó truy cập và khó nhận diện trường | Thêm label liên kết với input |
| name/id thay đổi liên tục | Công cụ khó nhận diện trường qua các lần render | Dùng name/id ổn định, có ý nghĩa |
| Input tạo động hoặc bị thay thế sau autofill | Giá trị đã điền bị mất | Giữ input ổn định và không ghi đè state vô cớ |
| Chia OTP thành nhiều ô không hỗ trợ paste | Mã tự điền không hoàn chỉnh | Dùng một trường hoặc xử lý paste toàn mã |
| Dùng iframe cross-origin cho form mật khẩu | Autofill bị giới hạn, ranh giới tin cậy phức tạp | Dùng redirect đến origin xác thực chính thức nếu phù hợp |
| Buộc nhập từng ký tự | Tăng lỗi và giảm khả năng dùng manager | Cho phép paste và autofill |
| Tự trim hoặc biến đổi password | Mật khẩu được lưu khác với chuỗi người dùng dự kiến | Xử lý chuỗi nhất quán, không âm thầm biến đổi |
| Chỉ hỗ trợ một password manager | Loại trừ người dùng trên nền tảng khác | Dựa trên HTML và API tiêu chuẩn |
| Không hỗ trợ mật khẩu dài | Làm giảm lợi ích của mật khẩu ngẫu nhiên | Chấp nhận độ dài lớn và kiểm thử giới hạn |

## 15. Kiểm thử password manager support

Kiểm thử phải xác nhận hành vi thực tế, không chỉ xác nhận HTML có thuộc tính autocomplete.

### 15.1. Ma trận nền tảng

Tối thiểu nên kiểm tra:

- Các trình duyệt desktop chính trong phạm vi hỗ trợ.
- Trình duyệt di động trên iOS và Android.
- Password manager tích hợp của trình duyệt hoặc hệ điều hành.
- Ít nhất một password manager độc lập phổ biến nếu nhóm có điều kiện.
- Ứng dụng native hoặc hybrid nếu sản phẩm có phiên bản tương ứng.
- Trình duyệt ở chế độ riêng tư hoặc profile mới nếu đó là môi trường được hỗ trợ.

Không cần kiểm thử mọi sản phẩm trên thị trường. Hãy chọn ma trận đại diện theo nhóm người dùng và ghi rõ giới hạn tương thích.

### 15.2. Các luồng phải kiểm thử

1. Đăng nhập bằng credential đã lưu.
2. Đăng nhập bằng username/email và password được điền tự động.
3. Tạo tài khoản và đề xuất mật khẩu mới.
4. Đổi mật khẩu với current-password và new-password.
5. Khôi phục mật khẩu và lưu credential mới.
6. Điền mã OTP hoặc TOTP.
7. Đăng nhập bằng passkey.
8. Đăng nhập qua IdP bên ngoài và quay về callback.
9. Chuyển đổi giữa nhiều tài khoản trên cùng origin.
10. Đăng xuất và đăng nhập lại sau khi credential thay đổi.
11. Paste mật khẩu dài, Unicode và ký tự đặc biệt.
12. Hoàn thành luồng bằng bàn phím và công nghệ hỗ trợ.

### 15.3. Test case và kết quả mong đợi

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| PM-01 | Trường username có autocomplete đúng | Trình duyệt nhận diện được trường định danh |
| PM-02 | Trường đăng nhập có current-password | Manager có thể đề xuất credential đã lưu |
| PM-03 | Form đăng ký có new-password | Manager có thể đề xuất mật khẩu mới |
| PM-04 | Mật khẩu được paste | Giá trị không bị chặn hoặc xóa |
| PM-05 | Mật khẩu dài hơn 64 ký tự | Không bị cắt nếu nằm trong giới hạn policy đã công bố |
| PM-06 | Mật khẩu có Unicode hoặc khoảng trắng | Client/server xử lý nhất quán |
| PM-07 | OTP được autofill | Giá trị được giữ nguyên và server xác minh đúng |
| PM-08 | OTP được paste toàn bộ | Mã được nhập đúng thứ tự, không mất ký tự |
| PM-09 | Password manager điền trước khi JS hydrate | Ứng dụng không ghi đè giá trị đã điền |
| PM-10 | Có nhiều tài khoản cùng origin | Người dùng chọn được credential phù hợp |
| PM-11 | Đăng nhập qua IdP khác origin | Người dùng hiểu domain nhận credential |
| PM-12 | Người dùng bật/tắt show password | Focus, giá trị và accessibility được giữ đúng |
| PM-13 | Đổi mật khẩu thành công | Manager có cơ hội cập nhật credential mới |
| PM-14 | Đăng xuất sau khi đổi mật khẩu | Phiên cũ bị xử lý theo policy server |
| PM-15 | Autofill không có sẵn | Người dùng vẫn có thể nhập thủ công và paste |

### 15.4. Kiểm thử bảo mật bổ sung

- Xác nhận form chỉ gửi credential đến origin chính thức.
- Kiểm tra không có password/OTP trong URL, referrer, log hoặc analytics.
- Kiểm tra XSS không thể đọc credential ngoài phạm vi thiết kế.
- Kiểm tra CSRF và session fixation.
- Kiểm tra rate limit không phụ thuộc vào việc người dùng gõ hay autofill.
- Kiểm tra account enumeration và thông báo lỗi.
- Kiểm tra token, cookie và recovery code không bị đưa vào telemetry.
- Kiểm tra autofill không làm bỏ qua bước MFA hoặc step-up.
- Kiểm tra redirect và iframe không làm rò rỉ credential.

## 16. Ví dụ kiểm tra tự động cho biểu mẫu

Có thể dùng test DOM hoặc browser automation để kiểm tra các thuộc tính cơ bản. Ví dụ dưới đây minh họa một kiểm tra đơn giản bằng JavaScript trong môi trường test:

~~~javascript
const username = document.querySelector('input[name="username"]');
const password = document.querySelector('input[name="password"]');

if (!username || username.autocomplete !== "username") {
  throw new Error("Username field is missing expected autocomplete");
}

if (!password || password.type !== "password" ||
    password.autocomplete !== "current-password") {
  throw new Error("Password field is missing expected semantics");
}
~~~

Đối với form đăng ký, kiểm tra trường password có autocomplete="new-password". Đối với MFA, kiểm tra one-time-code nếu đó là loại mã phù hợp.

Test DOM không thể chứng minh rằng mọi password manager đều hoạt động. Cần kết hợp kiểm thử trình duyệt thật, thiết bị thật và các luồng end-to-end. Không tự động nhập một secret thật vào môi trường test; dùng tài khoản và credential giả lập.

## 17. Theo dõi chất lượng mà không xâm phạm quyền riêng tư

Có thể theo dõi chất lượng luồng đăng nhập qua các chỉ số tổng hợp:

- Tỷ lệ hoàn tất đăng nhập.
- Tỷ lệ lỗi validation theo loại lỗi.
- Tỷ lệ người dùng phải nhập lại do form reset.
- Tỷ lệ hoàn tất đăng ký và đổi mật khẩu.
- Tỷ lệ lỗi OTP hoặc timeout.
- Tỷ lệ chuyển sang phương thức fallback.
- Số lượng sự cố do credential bị gửi sai origin hoặc bị log.
- Kết quả kiểm thử tương thích theo browser/version.

Không cần ghi nhận người dùng đang dùng password manager nào. Tránh fingerprint extension, đọc danh sách extension hoặc thu thập thông tin kho mật khẩu. Không ghi giá trị password, OTP, recovery code hay token để phân tích UX.

Nếu cần điều tra một lỗi autofill, hãy thu thập metadata không nhạy cảm như browser version, OS version, loại form, trạng thái lỗi và request ID. Chỉ thu thập dữ liệu cần thiết và tuân theo chính sách quyền riêng tư.

## 18. Quy trình review hỗ trợ password manager

### Bước 1 — Kiểm kê luồng credential

Liệt kê các trang và màn hình nhận username, password, OTP, recovery code hoặc passkey. Ghi rõ origin, loại client, phương thức xác thực và owner.

### Bước 2 — Kiểm tra ngữ nghĩa biểu mẫu

Đối chiếu type, name, id, label, autocomplete, form action và phương thức gửi. Xác định trường nào bị tạo động, nằm trong iframe hoặc thay đổi sau khi autofill.

### Bước 3 — Kiểm tra chính sách mật khẩu

Xem giới hạn độ dài, ký tự, Unicode, khoảng trắng, paste, password blocklist và cách xử lý chuỗi ở client/server. Xác nhận không có truncation hoặc normalization không nhất quán.

### Bước 4 — Kiểm tra luồng MFA, passkey và recovery

Đảm bảo OTP có autocomplete phù hợp, passkey dùng WebAuthn đúng chuẩn và recovery không phụ thuộc một nhà cung cấp password manager.

### Bước 5 — Kiểm thử trên nền tảng mục tiêu

Thực hiện ma trận browser, OS, native app và password manager. Ghi lại bước tái hiện, kết quả mong đợi, kết quả thực tế và giới hạn.

### Bước 6 — Kiểm tra bảo mật và quyền riêng tư

Xác minh origin, TLS, CSRF, session, log redaction, rate limit, redirect và xử lý lỗi. Đảm bảo dữ liệu autofill không bị gửi sang telemetry.

### Bước 7 — Khắc phục và xác minh lại

Ưu tiên sửa ngữ nghĩa HTML, ổn định trường, cho phép paste/autofill và sửa giới hạn mật khẩu. Sau thay đổi, chạy lại test end-to-end và security regression test.

## 19. Ví dụ tình huống: form đăng nhập không nhận password manager

Một nhóm triển khai form đăng nhập bằng JavaScript. Mỗi lần trang render, ứng dụng tạo lại input, đặt autocomplete="off" và chặn sự kiện paste để tránh người dùng nhập nhầm. Một số người dùng báo rằng password manager không đề xuất credential; người dùng khác thấy mật khẩu được điền rồi biến mất khi giao diện cập nhật.

Cách review:

1. Kiểm tra DOM sau khi trang hoàn tất render, không chỉ source template.
2. Xác minh input có id, name và label ổn định không.
3. Xác minh username dùng autocomplete="username".
4. Xác minh password dùng autocomplete="current-password".
5. Kiểm tra ứng dụng có thay input hoặc ghi đè state sau autofill không.
6. Kiểm tra paste handler có chặn dữ liệu không.
7. Kiểm tra giới hạn độ dài và xử lý Unicode.
8. Kiểm thử lại với browser autofill và password manager độc lập.
9. Xác minh credential chỉ gửi đến origin đăng nhập chính thức.
10. Kiểm tra server vẫn xác minh mật khẩu, rate limit và session như trước.

Hướng khắc phục là giữ input ổn định, dùng ngữ nghĩa HTML đúng, bỏ chặn paste và không tắt autocomplete. Sau đó xác minh bằng các luồng đăng nhập, đổi mật khẩu và MFA. Không cần phát hiện tên password manager để giải quyết lỗi.

## 20. Ví dụ tình huống: password manager điền sai domain

Người dùng được chuyển từ ứng dụng sang identity provider trên một domain khác. Họ thấy password manager không gợi ý credential đã lưu cho ứng dụng ban đầu và nghĩ rằng autofill bị lỗi.

Điều tra cần làm rõ:

- Credential được tạo và lưu trên origin nào?
- Trang hiện tại có phải origin chính thức của identity provider không?
- Người dùng có đang nhập mật khẩu vào đúng bên phát hành credential không?
- Có redirect ngoài dự kiến hoặc trang giả mạo không?
- Luồng liên kết có thông báo rõ domain và tên nhà cung cấp không?

Nếu IdP là bên xác thực, credential thường thuộc origin của IdP. Hướng dẫn người dùng phải giải thích đúng điều này. Không yêu cầu họ copy mật khẩu của ứng dụng vào form khác để “đồng bộ” password manager.

## 21. Những anti-pattern cần loại bỏ

- Chặn paste hoặc autofill vì muốn người dùng nhập mật khẩu bằng tay.
- Tắt autocomplete trên mọi trường đăng nhập.
- Dùng placeholder thay cho label.
- Đặt giới hạn độ dài quá thấp hoặc cắt chuỗi âm thầm.
- Ép mật khẩu chỉ gồm chữ và số.
- Tự động trim hoặc đổi hoa/thường của mật khẩu.
- Dùng JavaScript để chuyển password sang hidden field trước khi submit.
- Thay input liên tục khiến giá trị autofill biến mất.
- Chia OTP thành nhiều ô nhưng không hỗ trợ paste toàn mã.
- Yêu cầu người dùng tiết lộ master password hoặc export vault.
- Phát hiện extension hoặc fingerprint người dùng để cho phép đăng nhập.
- Nhúng form credential vào iframe cross-origin không có mô hình tin cậy rõ.
- Gửi credential trong URL, referrer, analytics hoặc log.
- Coi autofill thành công là bằng chứng MFA hoặc xác thực đã hoàn tất.
- Chỉ hỗ trợ một sản phẩm password manager.

## 22. Checklist cho reviewer

### Biểu mẫu và ngữ nghĩa

- [ ] Username có label, name/id ổn định và autocomplete="username".
- [ ] Mật khẩu đăng nhập có type="password" và autocomplete="current-password".
- [ ] Mật khẩu mới có autocomplete="new-password".
- [ ] OTP có autocomplete="one-time-code" khi phù hợp.
- [ ] Form action và origin gửi credential là chính thức.
- [ ] Input không bị thay thế hoặc xóa sau autofill.
- [ ] Không dùng placeholder thay cho label.

### Chính sách và nhập liệu

- [ ] Paste và autofill được cho phép.
- [ ] Không có maxlength quá thấp hoặc truncation âm thầm.
- [ ] Mật khẩu dài, Unicode, ký tự đặc biệt và khoảng trắng được xử lý nhất quán.
- [ ] Không tự trim, đổi hoa/thường hoặc normalize không nhất quán.
- [ ] Yêu cầu mật khẩu được hiển thị trước khi tạo.
- [ ] Nút show/hide có accessibility và không làm lộ dữ liệu qua telemetry.

### MFA, passkey và recovery

- [ ] OTP autofill và paste hoạt động.
- [ ] OTP vẫn được xác minh và giới hạn replay ở server.
- [ ] Passkey dùng WebAuthn và xác minh challenge/origin/RP ID.
- [ ] Người dùng có thể quản lý và thu hồi authenticator.
- [ ] Recovery không phụ thuộc một password manager cụ thể.
- [ ] Recovery code được bảo vệ và chỉ dùng theo policy.
- [ ] Đổi mật khẩu xử lý phiên và refresh token theo chính sách.

### Bảo mật và kiểm thử

- [ ] Credential chỉ truyền qua TLS và không xuất hiện trong URL.
- [ ] Log, tracing và analytics không chứa password, OTP hoặc recovery code.
- [ ] Có kiểm thử browser, mobile, native/hybrid và công cụ đại diện.
- [ ] Có test nhiều tài khoản, mật khẩu dài, Unicode và autofill trước/sau JavaScript hydration.
- [ ] Có test CSRF, XSS, session fixation, rate limit và account enumeration.
- [ ] Có ghi nhận giới hạn tương thích và bằng chứng kiểm thử.

## 23. Tự kiểm tra kiến thức

**Câu 1.** Vì sao trường mật khẩu đăng nhập nên dùng autocomplete="current-password"?

**Gợi ý:** Thuộc tính này cho trình duyệt biết đây là mật khẩu hiện tại đã có, giúp password manager phân biệt với trường tạo mật khẩu mới.

**Câu 2.** Vì sao chặn paste không phải là biện pháp tăng bảo mật?

**Gợi ý:** Nó làm người dùng khó sử dụng mật khẩu dài, ngẫu nhiên và duy nhất. Chống brute force và credential stuffing phải được thực hiện ở server.

**Câu 3.** Trường tạo mật khẩu mới nên dùng autocomplete nào?

**Gợi ý:** Dùng new-password để trình duyệt có thể đề xuất mật khẩu mới và cập nhật credential sau khi đăng ký hoặc đổi mật khẩu.

**Câu 4.** Vì sao không nên âm thầm cắt mật khẩu ở server?

**Gợi ý:** Password manager có thể lưu chuỗi đầy đủ trong khi server chỉ xác minh phần bị cắt, gây lỗi đăng nhập và làm suy yếu tính nhất quán của credential.

**Câu 5.** Password manager điền OTP có thay thế bước xác minh MFA không?

**Gợi ý:** Không. Autofill chỉ hỗ trợ nhập liệu. Server vẫn phải xác minh mã, thời hạn, giao dịch và trạng thái replay.

**Câu 6.** Khi đăng nhập qua IdP ở domain khác, credential nên được lưu cho origin nào?

**Gợi ý:** Credential thuộc origin nơi người dùng thực sự xác thực. Website RP cần giải thích rõ domain IdP và không yêu cầu copy credential sang origin khác.

**Câu 7.** Vì sao không nên phát hiện password manager bằng cách kiểm tra extension?

**Gợi ý:** Không có cơ chế chuẩn đáng tin cậy; việc fingerprint extension xâm phạm quyền riêng tư và tạo lỗi tương thích. Hãy hỗ trợ chuẩn HTML và API nền tảng.

## 24. Nguyên tắc cần ghi nhớ

1. Password manager là một phần của trải nghiệm xác thực an toàn vì nó giúp dùng credential mạnh và duy nhất.
2. Dùng HTML semantics, label và autocomplete đúng ngữ cảnh để trình duyệt nhận diện biểu mẫu.
3. Cho phép paste, autofill và mật khẩu dài; không âm thầm biến đổi hoặc cắt chuỗi.
4. Hỗ trợ OTP và passkey theo chuẩn nền tảng, nhưng luôn xác minh ở server.
5. Giữ origin đăng nhập rõ ràng để giảm nhầm lẫn và hỗ trợ chống phishing.
6. Recovery phải hoạt động ngay cả khi người dùng mất password manager.
7. Không phát hiện hoặc fingerprint password manager; không thu thập bí mật để đo UX.
8. Kiểm thử luồng thực tế trên browser, mobile và các phương thức xác thực được hỗ trợ.

Một hệ thống hỗ trợ password manager tốt giúp người dùng đăng nhập dễ dàng bằng credential mạnh, cho phép họ kiểm soát kho bí mật của mình và giữ nguyên các kiểm tra xác thực ở phía server. Trải nghiệm thuận tiện và ranh giới tin cậy rõ ràng phải được thiết kế cùng nhau.

