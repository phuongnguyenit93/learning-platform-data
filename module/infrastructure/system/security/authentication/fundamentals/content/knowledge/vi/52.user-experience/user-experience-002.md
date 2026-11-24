# Accessible authentication — Thiết kế xác thực có thể tiếp cận cho mọi người dùng

Một dịch vụ yêu cầu người dùng đăng nhập bằng password, sau đó nhập mã OTP trong 30 giây. Ô nhập mã không có label cho screen reader, focus tự nhảy giữa sáu ô khiến người dùng bàn phím khó sửa lỗi, nút gửi lại bị ẩn khi phóng to màn hình và CAPTCHA chỉ có hình ảnh. Người dùng bị hạn chế thị lực, vận động hoặc nhận thức không thể hoàn tất đăng nhập dù credential của họ hoàn toàn hợp lệ. Bộ phận hỗ trợ đề xuất tắt MFA cho các trường hợp này, vô tình tạo ra một con đường truy cập yếu hơn và khó kiểm toán.

**Accessible authentication** là thiết kế và vận hành các luồng xác thực sao cho người dùng có nhiều khả năng và cách tương tác khác nhau vẫn có thể đăng nhập, xác minh bổ sung, đăng ký factor, khôi phục tài khoản và kết thúc phiên một cách độc lập, dễ hiểu và an toàn. Accessibility bao gồm giao diện, nội dung, tương tác, thời gian, phương thức xác thực, thông báo lỗi và quy trình hỗ trợ.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối trải nghiệm xác thực với credential, password, MFA, passkey, token, session và account recovery. Người học sẽ biết thiết kế cho screen reader, bàn phím, switch control, voice input, phóng to, tương phản và nhu cầu nhận thức; hỗ trợ password manager và passkey; cung cấp lựa chọn MFA/recovery có assurance phù hợp; và kiểm thử với người dùng thực tế. Mục tiêu là giảm rào cản mà không tạo bypass bảo mật hoặc yêu cầu người dùng tiết lộ thông tin nhạy cảm.

## 1. Accessibility là thuộc tính của toàn bộ authentication journey

Một trang login có thể đạt yêu cầu về màu sắc và label nhưng toàn bộ quy trình vẫn không tiếp cận được nếu:

- Người dùng không thể hoàn tất CAPTCHA.
- OTP hết hạn trước khi người dùng screen reader nghe và nhập xong.
- Nút xác nhận không nhận focus bàn phím.
- Passkey chỉ hoạt động trên một thiết bị mà người dùng không có.
- Recovery yêu cầu gọi điện trong giờ hành chính nhưng không có lựa chọn khác.
- Error message chỉ được biểu diễn bằng màu đỏ hoặc icon không có tên.
- Người dùng bị buộc phải nhớ một bí mật hoặc giải câu đố.
- Quy trình hỗ trợ yêu cầu gửi OTP hoặc recovery code cho nhân viên.

Vì vậy cần đánh giá toàn bộ journey:

1. Tìm và mở trang đăng nhập.
2. Nhập identifier hoặc chọn identity provider.
3. Nhập password hoặc chọn passwordless method.
4. Hoàn tất MFA/step-up nếu cần.
5. Xử lý lỗi, timeout, retry và session continuation.
6. Đăng ký, thay đổi hoặc xóa authenticator.
7. Khôi phục account khi mất credential hoặc thiết bị.
8. Đăng xuất và quản lý session.

### 1.1. Accessibility không phải ngoại lệ bảo mật

Người dùng có khuyết tật có quyền sử dụng cùng dịch vụ và mức bảo vệ phù hợp. Không nên mặc định rằng người cần hỗ trợ phải được bỏ MFA, dùng password yếu hơn hoặc chia sẻ credential với support. Hãy cung cấp nhiều cách hoàn tất cùng một mục đích bảo mật, với assurance và audit tương xứng.

### 1.2. Thiết kế theo khả năng, không theo nhãn người dùng

Không phải mọi người dùng screen reader đều có cùng nhu cầu; không phải mọi người có hạn chế vận động đều không thể dùng điện thoại; và nhu cầu có thể thay đổi theo môi trường, thiết bị hoặc tình trạng tạm thời. Thiết kế nhiều phương thức tương tác và cho phép người dùng chọn cách phù hợp mà không yêu cầu họ khai báo chẩn đoán y tế.

## 2. Các nguyên tắc nền tảng

- **Perceivable:** thông tin, trạng thái và hướng dẫn có thể được nhận biết bằng nhiều giác quan hoặc công nghệ hỗ trợ.
- **Operable:** mọi thao tác đều có thể thực hiện bằng phương thức phù hợp, đặc biệt là bàn phím và switch.
- **Understandable:** nội dung, thứ tự và kết quả hành động rõ ràng, nhất quán.
- **Robust:** giao diện hoạt động với trình duyệt, screen reader và công nghệ hỗ trợ phổ biến.
- **Predictable:** focus, điều hướng và trạng thái không thay đổi bất ngờ.
- **Recoverable:** lỗi có thể sửa mà không phải làm lại toàn bộ quy trình.
- **Secure by design:** lựa chọn thay thế không làm yếu xác minh danh tính hoặc mở đường bypass.

WCAG 2.2 đưa ra tiêu chí **Accessible Authentication (Minimum) 3.3.8** ở mức AA và **Accessible Authentication (Enhanced) 3.3.9** ở mức AAA. Các tiêu chí này tập trung tránh bắt buộc người dùng thực hiện cognitive function test trong quá trình authentication, với các điều kiện và ngoại lệ được tiêu chí quy định. Khi thiết kế, cần đọc đúng phiên bản WCAG áp dụng và đánh giá toàn bộ luồng, không chỉ màn hình nhập password.

## 3. Hiểu các rào cản thường gặp

| Nhu cầu hoặc tình huống | Rào cản có thể xuất hiện | Thiết kế hỗ trợ |
| --- | --- | --- |
| Thị lực kém hoặc mù | Label thiếu, focus không rõ, CAPTCHA hình ảnh | Semantic HTML, screen reader labels, text alternatives |
| Khó phân biệt màu | Trạng thái chỉ dùng màu đỏ/xanh | Text/icon có nhãn, contrast đủ |
| Hạn chế vận động | Target nhỏ, drag-only, timeout ngắn | Target đủ lớn, keyboard/switch, thời gian linh hoạt |
| Khó nghe | OTP/challenge chỉ qua âm thanh | Kênh text tương đương |
| Khác biệt nhận thức/trí nhớ | Câu đố, ghi nhớ password, hướng dẫn dài | Password manager, passkey, nội dung ngắn và rõ |
| Khó đọc hoặc ngôn ngữ khác | Error mơ hồ, thuật ngữ khó | Ngôn ngữ đơn giản, bản dịch, ví dụ |
| Nhạy cảm với chuyển động | Focus/animation thay đổi liên tục | Tôn trọng reduced motion, trạng thái ổn định |
| Thiết bị/công nghệ hỗ trợ cũ | Control custom không tương thích | Native control, semantic, progressive enhancement |
| Tình huống tạm thời | Một tay bận, ánh sáng kém, mạng yếu | Nhiều phương thức, retry và continuation |

Một người có thể gặp nhiều rào cản đồng thời. Không giả định một giải pháp duy nhất như audio CAPTCHA sẽ giải quyết được mọi nhu cầu.

## 4. Cognitive function test và yêu cầu của WCAG

Cognitive function test là nhiệm vụ yêu cầu người dùng nhớ, tính toán, giải câu đố, nhận dạng hoặc phiên âm thông tin để chứng minh họ là người thực hiện. Ví dụ:

- Nhớ password không có password manager hoặc cơ chế hỗ trợ.
- Ghi nhớ mã rồi chuyển sang màn hình khác để nhập.
- Giải phép tính hoặc puzzle.
- Nhận dạng ký tự méo trong CAPTCHA.
- Chép mã từ hình ảnh hoặc âm thanh.
- Trả lời câu hỏi kiến thức cá nhân.

WCAG 2.2 criterion 3.3.8 đặt ra yêu cầu không bắt buộc cognitive function test trong authentication, trừ khi đáp ứng một trong các điều kiện/ngoại lệ của tiêu chí, chẳng hạn có alternative method, có mechanism hỗ trợ, dùng object recognition/personal content theo phạm vi được phép hoặc nhiệm vụ là essential. Criterion 3.3.9 ở mức AAA chặt hơn về các ngoại lệ. Đội sản phẩm nên kiểm tra văn bản tiêu chí và hướng dẫn kỹ thuật chính thức thay vì tự diễn giải ngoại lệ.

### 4.1. Các cách giảm gánh nặng nhận thức

- Cho phép password manager tự điền và tạo password.
- Cho phép paste vào password, OTP và recovery input.
- Dùng autocomplete tokens đúng mục đích.
- Không bắt người dùng nhớ hoặc chép lại thông tin giữa nhiều màn hình.
- Hiển thị tiến trình và bước hiện tại.
- Giữ dữ liệu đã nhập khi có lỗi có thể sửa an toàn.
- Dùng câu chữ trực tiếp, ngắn và nhất quán.
- Cung cấp cách thay thế CAPTCHA có thể tiếp cận.
- Hỗ trợ passkey và các phương thức xác minh phù hợp.

### 4.2. CAPTCHA và bot defense

CAPTCHA có thể tạo rào cản đáng kể cho người dùng. Nếu cần chống bot:

- Ưu tiên risk signals và rate limiting phía server trước khi bắt người dùng giải challenge.
- Không chỉ cung cấp image CAPTCHA; có lựa chọn tương đương về accessibility.
- Không yêu cầu audio challenge duy nhất vì người dùng có thể khiếm thính hoặc ở môi trường không nghe được.
- Không bắt người dùng giải puzzle phức tạp hoặc dựa vào màu sắc.
- Có phương án hỗ trợ khi challenge không thể hoàn tất.
- Đánh giá khả năng lạm dụng của từng fallback; không cho phép bypass không giới hạn.

## 5. Semantic HTML và cấu trúc form đăng nhập

Native HTML controls thường có semantics và hành vi bàn phím tốt hơn custom control. Mỗi input cần label gắn đúng, mô tả rõ và trạng thái lỗi được công bố.

### 5.1. Label, instruction và autocomplete

Ví dụ form minh họa:

~~~html
<form action="/login" method="post">
  <div>
    <label for="username">Email hoặc tên tài khoản</label>
    <input
      id="username"
      name="username"
      type="text"
      autocomplete="username"
      required
      aria-describedby="username-help"
    />
    <p id="username-help">
      Nhập email hoặc tên tài khoản đã đăng ký.
    </p>
  </div>

  <div>
    <label for="password">Mật khẩu</label>
    <input
      id="password"
      name="password"
      type="password"
      autocomplete="current-password"
      required
    />
  </div>

  <button type="submit">Đăng nhập</button>
</form>
~~~

Đây là ví dụ cấu trúc, production cần CSRF protection, server-side validation, rate limiting và error handling. Không dùng placeholder làm label duy nhất vì placeholder biến mất khi nhập và thường có contrast thấp.

Autocomplete tokens có thể giúp password manager và trình duyệt hiểu trường:

- `username` cho identifier dùng đăng nhập.
- `current-password` cho password hiện tại.
- `new-password` cho password mới.
- `one-time-code` cho mã dùng một lần.
- `email` hoặc `tel` khi trường thực sự yêu cầu địa chỉ email/số điện thoại.

Không đặt autocomplete token sai ngữ nghĩa chỉ để ép hoặc chặn password manager.

### 5.2. Group các trường liên quan

Với OTP nhiều phần, dùng một input có label rõ nếu có thể. Nếu UI dùng nhiều ô:

- Công bố tổng số ký tự và vị trí hiện tại.
- Hỗ trợ paste toàn bộ mã.
- Không tự xóa dữ liệu khi focus chuyển.
- Cho phép sửa từng ký tự bằng bàn phím.
- Không bắt buộc dùng drag hoặc touch.
- Cung cấp tên accessible cho từng ô.

Tránh tách sáu ô nếu không có lợi ích rõ ràng; một input duy nhất thường đơn giản hơn cho screen reader, paste và password manager.

## 6. Screen reader và thông báo trạng thái

Screen reader dựa vào semantics, label, role, state và thứ tự focus. Một giao diện trông rõ ràng bằng mắt vẫn có thể không sử dụng được nếu thông tin không được công bố.

### 6.1. Những điều cần kiểm tra

- Mỗi input có accessible name mô tả đúng mục đích.
- Heading phản ánh cấu trúc và thứ tự.
- Button/link có tên duy nhất, dễ hiểu.
- Required state và format instruction được công bố.
- Error message gắn với trường tương ứng.
- Status message được thông báo khi cần, không cướp focus vô cớ.
- Focus order theo thứ tự logic.
- Modal/dialog giữ focus và trả focus về control mở nó.
- Nội dung mới xuất hiện được công bố mà không làm mất context.

### 6.2. Error summary và field error

Khi submit lỗi:

1. Hiển thị summary ở đầu form.
2. Mô tả số lỗi và cách sửa.
3. Link tới từng trường lỗi.
4. Đánh dấu field bằng `aria-invalid`.
5. Liên kết mô tả lỗi bằng `aria-describedby`.
6. Đưa focus tới summary hoặc trường đầu tiên theo pattern nhất quán.

Ví dụ:

~~~html
<div id="login-errors" role="alert" tabindex="-1">
  Không thể đăng nhập. Hãy kiểm tra thông tin và thử lại.
</div>

<label for="otp">Mã xác minh</label>
<input
  id="otp"
  name="otp"
  inputmode="numeric"
  autocomplete="one-time-code"
  aria-invalid="true"
  aria-describedby="otp-error"
/>
<p id="otp-error">Mã đã hết hạn. Hãy yêu cầu mã mới.</p>
~~~

Nội dung error cần tránh account enumeration. Ví dụ, login có thể dùng thông báo chung khi identifier/password không hợp lệ; OTP hết hạn có thể được thông báo cụ thể vì người dùng đã qua bước xác định transaction, miễn là không tiết lộ thông tin nhạy cảm. Cân bằng usability, privacy và threat model.

### 6.3. Live region

Dùng live region cho thông báo trạng thái như “Đang xác minh”, “Mã đã được gửi” hoặc “Không thể kết nối”. Không đặt toàn bộ form vào live region khiến screen reader đọc lại liên tục. Tránh thông báo quá dày khi mỗi ký tự được nhập.

## 7. Bàn phím, switch control và focus

Người dùng có thể điều hướng bằng Tab, Shift+Tab, Enter, Space và các phím điều khiển của công nghệ hỗ trợ.

- Mọi chức năng phải dùng được bằng bàn phím.
- Không tạo keyboard trap.
- Focus indicator rõ ràng và không bị sticky header/modal che.
- Thứ tự focus khớp thứ tự nội dung.
- Không yêu cầu thao tác drag-only; cung cấp button hoặc control thay thế.
- Không tự chuyển focus khi người dùng chưa thực hiện hành động rõ ràng.
- Không tự submit khi người dùng vừa nhập đủ ký tự nếu việc đó gây mất cơ hội kiểm tra/sửa.
- Cho phép hiển thị/ẩn password bằng button có accessible name và trạng thái.
- Các target tương tác có kích thước phù hợp; WCAG 2.2 có tiêu chí Target Size (Minimum) với các ngoại lệ cụ thể.

### 7.1. Focus sau lỗi

Nếu submit thất bại, focus cần đưa người dùng tới nơi họ có thể hiểu và sửa lỗi. Không để focus biến mất về document body hoặc nhảy về đầu trang không rõ lý do.

### 7.2. Không phụ thuộc hover

Hướng dẫn quan trọng không chỉ xuất hiện khi hover. Tooltip cần truy cập được bằng keyboard và touch; nội dung cần thiết nên hiển thị trực tiếp.

## 8. Thị giác, tương phản và phóng to

- Text và control có contrast phù hợp tiêu chí WCAG áp dụng.
- Không dùng màu sắc làm tín hiệu duy nhất cho success/error.
- Hỗ trợ zoom và text resizing mà không mất chức năng.
- Layout reflow khi viewport hẹp hoặc zoom lớn.
- Không cắt label, error, OTP timer hoặc nút submit.
- Focus indicator đủ rõ trên cả light/dark theme.
- Không truyền đạt trạng thái chỉ qua animation hoặc icon không nhãn.
- Hỗ trợ high contrast/forced colors khi nền tảng cung cấp.

Authentication thường có nội dung ngắn, nhưng người dùng có thể cần phóng to để đọc OTP, recovery instruction hoặc thông tin thiết bị. Kiểm tra form ở zoom cao, text spacing và viewport nhỏ.

## 9. Thời gian, timeout và OTP

Timeout ngắn có thể làm người dùng screen reader, switch control hoặc người cần thêm thời gian thất bại dù họ nhập đúng.

### 9.1. Session timeout

- Cảnh báo trước khi session hết hạn nếu có thể.
- Cho phép kéo dài session bằng thao tác rõ ràng khi policy cho phép.
- Giữ nội dung chưa gửi nếu an toàn.
- Khi session hết hạn, giải thích cách đăng nhập lại và giữ context không nhạy cảm.
- Không để người dùng mất dữ liệu chỉ vì form bị timeout.
- Với thao tác đặc quyền, có thể yêu cầu reauthentication thay vì giữ session vô hạn.

### 9.2. OTP expiry

- Chọn TTL dựa trên threat model và khả năng nhập thực tế.
- Hiển thị thời gian còn lại bằng text dễ hiểu nếu có countdown.
- Không chỉ dùng vòng tròn hoặc màu sắc để báo expiry.
- Có resend path với rate limit và abuse detection.
- Không tạo nhiều OTP đồng thời nếu server chỉ chấp nhận một mã; giải thích mã mới thay mã cũ.
- Hỗ trợ paste và autofill.
- Không xóa input hoặc chuyển focus quá nhanh.
- Khi mã hết hạn, cho phép yêu cầu mã mới mà không phải bắt đầu lại toàn bộ login.

### 9.3. Countdown và motion

Countdown không nên cập nhật live announcement mỗi giây. Thông báo các mốc hữu ích, ví dụ “Mã còn hiệu lực khoảng một phút” và “Mã đã hết hạn”. Tôn trọng reduced motion và tránh animation gây mất tập trung.

## 10. Password manager và password UX

Password manager giúp người dùng tạo và lưu password dài, duy nhất, giảm việc nhớ và tái sử dụng password. Chặn password manager thường làm giảm cả accessibility lẫn security.

- Cho phép paste vào password field.
- Không chặn autofill hoặc browser credential manager.
- Dùng `autocomplete="username"` và `current-password` đúng ngữ nghĩa.
- Dùng `new-password` cho đăng ký/đổi password.
- Cho phép password dài và passphrase.
- Không ép quy tắc ký tự phức tạp khó nhớ nếu không có căn cứ; ưu tiên length và breached-password screening.
- Không cắt ngắn password âm thầm.
- Không tự trim hoặc normalize password theo cách thay đổi secret mà người dùng nhập.
- Có nút show/hide password truy cập được.
- Không bắt người dùng nhập password hai lần nếu không cần thiết.

### 10.1. Paste và clipboard

Không disable paste chỉ để chống copy/paste password. Người dùng password manager, switch control hoặc công nghệ hỗ trợ có thể cần thao tác này. Nếu cần chống credential theft, dùng MFA chống phishing, rate limit, device security và detection thay vì cấm paste.

### 10.2. Password reveal

Nút show/hide phải:

- Có tên như “Hiển thị mật khẩu” và “Ẩn mật khẩu”.
- Công bố trạng thái hiện tại.
- Không làm mất focus hoặc xóa password.
- Không bật mặc định trên thiết bị công cộng nếu có risk.
- Giữ nguyên label và autocomplete.

## 11. MFA UX có thể tiếp cận

MFA có nhiều hình thức và mỗi hình thức tạo rào cản khác nhau. Cung cấp lựa chọn đã được đánh giá bảo mật, phù hợp thiết bị và nhu cầu người dùng.

| Phương thức | Rào cản có thể gặp | Cải thiện |
| --- | --- | --- |
| TOTP app | Chuyển app, chép mã, hết hạn | Paste/autofill, một input, timer rõ, alternative factor |
| Push notification | Khó nghe/nhìn prompt, fatigue | Hiển thị context, approve/deny rõ, rate limit |
| SMS/voice OTP | Phụ thuộc mạng, hearing/accessibility, SIM swap | Có phương thức khác, không xem SMS là factor mạnh nhất |
| Security key | Cổng USB/NFC, thao tác vật lý | Hỗ trợ nhiều connector và phương thức thay thế |
| Passkey | Thiết bị/OS/provider không tương thích | Cross-device flow và fallback có assurance |
| Recovery code | Phải lưu/nhớ/nhập mã | Password manager/secure storage và regeneration có kiểm soát |

### 11.1. TOTP

- Dùng một ô nhập cho mã nếu có thể.
- Cho phép paste toàn bộ mã.
- Dùng input mode numeric nhưng không ép keyboard layout sai trên mọi locale.
- Có label, hướng dẫn và error rõ.
- Không tự chuyển focus hoặc submit khi người dùng chưa sẵn sàng.
- Có phương thức thay thế phù hợp; TOTP không có resend nhưng có thể dùng time sync/help flow.
- Không hiển thị seed TOTP sau enrollment.

### 11.2. Push MFA

- Hiển thị app, location/device context ở mức phù hợp.
- Nút Approve và Deny có label rõ, target đủ lớn.
- Không dùng chỉ màu xanh/đỏ.
- Hạn chế số prompt và có cooldown.
- Không yêu cầu người dùng approve để “thử xem”.
- Cho phép report prompt không yêu cầu.

### 11.3. Fallback MFA

Fallback không được yếu đến mức trở thành đường bypass. Ví dụ, nếu primary factor là passkey, fallback SMS có thể tạo risk SIM swap; cần xem account sensitivity và recovery assurance. Có thể cung cấp nhiều factor độc lập, nhưng không ép người dùng chỉ có một phương thức không phù hợp.

## 12. Passkey và WebAuthn UX

Passkey giảm gánh nặng nhớ password và có khả năng chống phishing nhờ credential gắn với RP ID/origin. Tuy nhiên, trải nghiệm enrollment và sử dụng cần hỗ trợ nhiều thiết bị, nền tảng và công nghệ hỗ trợ.

### 12.1. Enrollment

- Giải thích passkey là gì bằng ngôn ngữ dễ hiểu.
- Nói rõ passkey sẽ được lưu/sync ở đâu theo nền tảng.
- Không yêu cầu user hiểu thuật ngữ private/public key.
- Cho phép hủy mà không khóa account.
- Xác minh lại user trước khi thêm credential.
- Đặt tên credential theo thiết bị/ngày hoặc cho phép người dùng tự đặt.
- Cung cấp cách quản lý, xem và xóa passkey.
- Thông báo khi passkey mới được đăng ký.

### 12.2. Sign-in

- Nút “Đăng nhập bằng passkey” có accessible name rõ.
- Hỗ trợ conditional mediation/autofill khi platform/browser hỗ trợ.
- Không giả định thiết bị có biometric hoặc màn hình cảm ứng.
- Cung cấp cross-device authentication qua QR/Bluetooth khi được hỗ trợ và có hướng dẫn text.
- Có đường quay lại phương thức khác mà không reset toàn bộ form.
- Giải thích lỗi như “Không tìm thấy passkey cho tài khoản này” mà không tiết lộ account existence ở nơi cần bảo vệ enumeration.

### 12.3. Biometric UX

Sinh trắc học thường được xác minh cục bộ trên authenticator/device; server nhận kết quả WebAuthn assertion chứ không nhận vân tay hoặc khuôn mặt. Giao diện nên giải thích điều này chính xác, không hứa rằng website lưu biometric. Cũng cần lựa chọn thay thế khi người dùng không thể hoặc không muốn dùng biometric.

### 12.4. Fallback và account recovery

Passkey không loại bỏ nhu cầu recovery. Người dùng có thể mất thiết bị, mất quyền truy cập cloud account hoặc đổi nền tảng. Cung cấp quy trình phục hồi được xác minh, có audit, thông báo và kiểm tra session/factor cũ. Không dùng một link email yếu làm fallback cho account có assurance cao.

## 13. Error messages và privacy

Thông báo lỗi phải hữu ích mà không tiết lộ dữ liệu cho attacker.

### 13.1. Login errors

Với identifier/password, thông báo chung như “Không thể đăng nhập với thông tin này” có thể giảm account enumeration. Nhưng vẫn cần hướng dẫn rõ cách sửa: kiểm tra bàn phím, thử password manager, dùng recovery hoặc liên hệ support. Không dùng lỗi chỉ có mã số.

### 13.2. MFA errors

Thông báo cụ thể có thể phù hợp khi người dùng đã bắt đầu một challenge:

- “Mã không đúng. Hãy kiểm tra mã mới nhất trong ứng dụng.”
- “Mã đã hết hạn. Yêu cầu mã mới.”
- “Thông báo xác minh đã hết hạn. Bắt đầu lại để nhận yêu cầu mới.”
- “Thiết bị không hỗ trợ phương thức này. Chọn một cách xác minh khác.”

Không hiển thị seed, token, recovery code hoặc lý do chi tiết có thể giúp attacker vượt policy.

### 13.3. Không đổ lỗi cho người dùng

Tránh thông báo như “Bạn nhập sai” hoặc “Bạn làm sai quy trình”. Dùng câu mô tả trạng thái và hành động tiếp theo. Người dùng có thể gặp lỗi do mạng, đồng hồ thiết bị, server hoặc authenticator.

## 14. Recovery UX và support-assisted authentication

Recovery thường là điểm yếu nhất của authentication. Một luồng dễ tiếp cận nhưng identity proofing yếu sẽ cho attacker chiếm account.

### 14.1. Recovery journey

1. Cho người dùng biết các phương thức khôi phục hiện có.
2. Giải thích thông tin nào cần chuẩn bị và thời gian dự kiến.
3. Cho phép chọn phương thức phù hợp với khả năng/thiết bị.
4. Xác minh danh tính bằng assurance tương xứng với account.
5. Hiển thị trạng thái pending và cách tiếp tục.
6. Thông báo qua kênh đã xác minh trước đó.
7. Sau recovery, revoke session/factor/token theo policy.
8. Cung cấp cách đăng ký lại passkey/MFA và xem lịch sử bảo mật.

### 14.2. Không phụ thuộc một kênh duy nhất

Nếu SMS không hoạt động hoặc người dùng không thể nghe cuộc gọi, cần lựa chọn thay thế có assurance phù hợp. Nếu email bị compromise, không dùng chính email đó làm bằng chứng độc lập. Có thể kết hợp recovery code, thiết bị tin cậy, identity proofing hoặc support workflow với dual control.

### 14.3. Support agent

- Giao diện support có hướng dẫn rõ và accessible.
- Không yêu cầu người dùng đọc OTP hoặc gửi recovery code.
- Agent không được xem password, private key hoặc secret.
- Reset factor cần xác minh actor/subject và approval.
- Các thao tác hỗ trợ được audit.
- Người dùng được thông báo sau thay đổi bảo mật.
- Có escalation khi người dùng không thể hoàn tất phương thức tiêu chuẩn.

## 15. Localization và ngôn ngữ dễ hiểu

- Dùng ngôn ngữ người dùng đã chọn và giữ lựa chọn xuyên suốt flow.
- Tránh dịch máy các thuật ngữ bảo mật quan trọng mà không review.
- Dùng câu ngắn, động từ trực tiếp và hướng dẫn theo từng bước.
- Không phụ thuộc idiom, màu sắc hoặc biểu tượng văn hóa.
- Format ngày, giờ, số và số điện thoại theo locale.
- Không giả định mọi tên người hoặc email tuân theo một format cụ thể.
- Cho phép text resize và không cắt nội dung khi dịch dài hơn.
- Giải thích thuật ngữ như passkey, authenticator và recovery code bằng ví dụ.

Không đưa thông tin kỹ thuật quá mức vào lỗi đăng nhập. Có thể cung cấp link “Tìm hiểu thêm” tới tài liệu hỗ trợ accessible.

## 16. Mobile, responsive và assistive technology

### 16.1. Mobile

- Target đủ lớn và có khoảng cách phù hợp.
- Hỗ trợ screen reader và switch control của hệ điều hành.
- Không phụ thuộc gesture phức tạp.
- Hỗ trợ paste/autofill và bàn phím phù hợp.
- Không yêu cầu chuyển app nhiều lần mà mất transaction state.
- QR cross-device flow có hướng dẫn text và lựa chọn khác.
- Orientation change không làm mất dữ liệu.
- Keyboard mở không che nút tiếp tục hoặc error.

### 16.2. Desktop

- Toàn bộ flow dùng được bằng keyboard.
- Browser password manager/autofill hoạt động.
- Zoom/reflow không làm mất nút hoặc thông tin.
- Dialog, popup và external identity provider có focus management rõ.
- Không mở tab mới bất ngờ mà không thông báo.

### 16.3. Công nghệ hỗ trợ

Kiểm thử với tổ hợp đại diện:

- NVDA/JAWS với trình duyệt desktop phổ biến.
- VoiceOver trên macOS/iOS.
- TalkBack trên Android.
- Keyboard-only.
- Switch control hoặc voice control khi nền tảng hỗ trợ.
- Browser zoom và OS text scaling.
- High contrast/forced colors và reduced motion.

Không cần tuyên bố hỗ trợ mọi tổ hợp có thể tồn tại. Cần định nghĩa support matrix, test theo nhóm người dùng thực và ghi giới hạn đã biết.

## 17. Security và accessibility cùng lúc

Accessibility không đòi hỏi giảm assurance. Thường có thể cải thiện cả hai bằng cách giảm thao tác dễ sai, tăng lựa chọn và dùng xác minh mạnh hơn.

| Vấn đề | Cách làm gây rào cản | Thiết kế tốt hơn |
| --- | --- | --- |
| Password manager | Chặn paste/autofill | Cho phép manager, breached-password screening và MFA |
| CAPTCHA | Puzzle hình ảnh duy nhất | Risk-based defense và lựa chọn accessible |
| OTP | Sáu ô khó paste, timeout quá ngắn | Một input, autofill, retry/rate limit |
| MFA | Chỉ một factor không phù hợp | Nhiều factor có assurance được đánh giá |
| Recovery | Email link duy nhất | Nhiều recovery path có identity proofing |
| Session | Timeout bất ngờ | Warning, extension có kiểm soát và reauth |
| Passkey | Bắt buộc một platform | Hỗ trợ cross-device và fallback an toàn |
| Support | Agent đọc/nhận OTP | Agent xác minh qua quy trình, không xem secret |

### 17.1. Alternative method phải có assurance tương xứng

Khi cung cấp alternative:

- Xác định threat model và assurance cần đạt.
- Đánh giá possession, user verification, phishing resistance và replay.
- Ràng buộc alternative với đúng account/transaction.
- Giới hạn rate, TTL và số lần thử.
- Audit enrollment, use, reset và recovery.
- Có step-up/approval cho account hoặc action nhạy cảm.

Không tạo accessibility bypass dùng chung hoặc câu hỏi dễ đoán. Một phương thức thay thế cần là một luồng xác thực được thiết kế và kiểm thử riêng.

### 17.2. Không biến accessibility thành device fingerprinting

Không theo dõi hoặc phân loại người dùng theo suy đoán disability. Device signal có thể phục vụ security nếu có mục đích và consent/policy phù hợp, nhưng không nên dùng để từ chối dịch vụ vì người dùng dùng assistive technology, browser extension hoặc thiết bị khác thường.

## 18. Ví dụ: form OTP có thể tiếp cận

Một form OTP tốt cần label, paste/autofill, error association và thông báo trạng thái rõ.

~~~html
<form id="verify-form" action="/verify" method="post">
  <h1>Xác minh đăng nhập</h1>
  <p id="otp-instructions">
    Nhập mã 6 chữ số từ ứng dụng xác thực. Bạn có thể dán toàn bộ mã.
  </p>

  <label for="otp">Mã xác minh</label>
  <input
    id="otp"
    name="otp"
    type="text"
    inputmode="numeric"
    autocomplete="one-time-code"
    pattern="[0-9]{6}"
    maxlength="6"
    required
    aria-describedby="otp-instructions otp-error"
  />
  <p id="otp-error" hidden></p>

  <button type="submit">Xác minh</button>
  <button type="button" id="use-another-method">
    Dùng phương thức khác
  </button>
  <p id="status" role="status" aria-live="polite"></p>
</form>
~~~

Ví dụ minh họa cần được bổ sung server-side validation, CSRF protection, throttling và transaction binding. Nếu mã không hợp lệ, bỏ hidden, đặt aria-invalid=true, cập nhật nội dung lỗi và đưa focus theo pattern nhất quán. Không tự động gửi form chỉ vì đủ sáu ký tự; người dùng cần có cơ hội kiểm tra và chủ động xác nhận.

### 18.1. Server-side validation

~~~java
public VerificationResult verifyOtp(
        AuthTransaction transaction,
        String submittedCode,
        PrincipalContext principal) {

    if (!transaction.belongsTo(principal.accountRef())) {
        return VerificationResult.genericFailure();
    }
    if (transaction.isExpired(clock.instant())) {
        return VerificationResult.expired();
    }
    if (!rateLimiter.allow(principal.accountRef(), transaction.id())) {
        return VerificationResult.tryLater();
    }

    boolean valid = otpVerifier.verify(
        transaction.factorRef(),
        submittedCode
    );
    if (!valid) {
        audit.recordOtpFailure(principal.safeRef(), transaction.safeRef());
        return VerificationResult.invalid();
    }

    transactionStore.consumeOnce(transaction.id());
    audit.recordOtpSuccess(principal.safeRef(), transaction.safeRef());
    return VerificationResult.success();
}
~~~

Đây là pseudocode. Production cần chống race khi consume transaction, giới hạn retry, bảo vệ secret TOTP, xử lý clock drift theo policy và bảo đảm audit không chứa mã. Accessible UI không thay thế kiểm tra server-side hoặc replay protection.

## 19. Quy trình thiết kế và kiểm thử

Một quy trình thực tế:

1. **Map journey:** liệt kê login, step-up, enrollment, recovery, logout và error path.
2. **Identify barriers:** đánh giá thị giác, thính giác, vận động, nhận thức, ngôn ngữ và thiết bị.
3. **Threat model:** xác định assurance, attacker path và rủi ro fallback.
4. **Design alternatives:** chọn nhiều phương thức có bảo mật tương xứng.
5. **Build semantic UI:** native controls, labels, instructions, focus và error state.
6. **Automated checks:** axe/linter/accessibility tree, HTML validation và unit tests.
7. **Manual tests:** keyboard, screen reader, zoom, contrast, mobile và timeout.
8. **User testing:** mời người dùng có nhu cầu đa dạng tham gia và trả công phù hợp.
9. **Security testing:** rate limit, enumeration, replay, session binding, recovery abuse.
10. **Release and monitor:** theo dõi completion/drop-off, support cases và security signal.

### 19.1. Không chỉ đo tỷ lệ đăng nhập thành công

Metrics hữu ích:

- Completion rate theo từng bước và phương thức.
- Drop-off tại password, MFA, passkey enrollment và recovery.
- Error/retry rate và timeout rate.
- Tỷ lệ dùng alternative method.
- Thời gian hoàn tất theo luồng, không phân loại nhạy cảm không cần thiết.
- Support contact và recovery failure.
- MFA bypass/exception rate.
- Account takeover/fraud rate.
- Accessibility defect severity và thời gian khắc phục.

Không suy đoán disability từ analytics. Nếu cần phân tích theo nhóm người dùng, dùng nghiên cứu tự nguyện, privacy review và dữ liệu tối thiểu.

## 20. Ma trận kiểm thử accessible authentication

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Chỉ dùng keyboard để login | Tất cả field, button và link hoạt động; focus rõ |
| Screen reader đọc form password | Label, required state, instruction và error được công bố |
| Password manager autofill | Username/password điền đúng, không bị chặn |
| Paste password | Hoạt động bình thường |
| Zoom 200–400% | Không mất nội dung hoặc chức năng; layout reflow phù hợp |
| High contrast/forced colors | Focus, control và error vẫn nhận biết được |
| Color disabled | Error/success vẫn có text/icon/semantics |
| Screen reader nhận OTP error | Error gắn với input và được thông báo |
| Paste toàn bộ OTP | Một thao tác paste điền đúng mã |
| OTP hết hạn | Có thông báo rõ và cách lấy mã mới |
| Countdown chạy | Không spam live announcement mỗi giây |
| Keyboard điều hướng modal MFA | Focus trap hợp lý và trả focus đúng |
| Switch control chọn passkey | Control có label và target phù hợp |
| Voice control kích hoạt button | Accessible name khớp tên hiển thị |
| CAPTCHA không thể hoàn tất | Có alternative accessible với kiểm soát anti-abuse |
| Người dùng không thể dùng SMS | Có alternative factor/recovery đã đánh giá assurance |
| Passkey không có trên thiết bị | Cross-device/fallback được giải thích và không reset flow |
| Passkey enrollment bị hủy | Account vẫn dùng được phương thức hiện có |
| Recovery contact vừa bị đổi | Recovery có step-up/delay/verification phù hợp |
| Session sắp hết hạn | Warning được công bố và có lựa chọn hợp lệ |
| Session hết hạn khi đang nhập | Dữ liệu an toàn được giữ hoặc có hướng tiếp tục |
| Error identifier/password | Không tiết lộ account existence |
| Error MFA | Giải thích cách sửa mà không tiết lộ secret |
| Người dùng dùng reduced motion | Không có animation bắt buộc để hiểu trạng thái |
| Locale có text dài hơn | Không cắt label, error hoặc button |
| Mobile keyboard mở | Nút tiếp tục và error không bị che |
| Orientation change | Form state không mất ngoài ý muốn |
| Recovery qua support | Không yêu cầu đọc OTP/password; actor/approval được audit |
| Alternative MFA | Assurance tương xứng, rate limit và replay protection hoạt động |
| WebAuthn origin sai | Server từ chối assertion dù UI accessible |
| OTP replay | Server từ chối transaction đã consume |

## 21. Những lỗi thiết kế thường gặp

| Lỗi | Tác động | Cải thiện |
| --- | --- | --- |
| Placeholder thay label | Screen reader và người dùng dễ quên mục đích field | Label cố định, gắn đúng input |
| CAPTCHA hình ảnh duy nhất | Loại trừ người mù/thị lực kém | Alternative accessible và risk-based bot defense |
| Chặn paste/autofill | Cản password manager và assistive technology | Cho phép paste/autofill, tăng bảo vệ ở server |
| OTP nhiều ô không hỗ trợ paste | Nhập chậm và khó sửa | Một input hoặc hỗ trợ paste/focus tốt |
| OTP timeout quá ngắn | Người dùng cần thêm thời gian thất bại | TTL hợp lý, resend và alternative |
| Error chỉ dùng màu | Người không phân biệt màu không hiểu lỗi | Text, icon có tên và field association |
| Focus tự nhảy bất ngờ | Mất vị trí và khó điều hướng | Focus management có chủ đích |
| MFA duy nhất qua push | Không phù hợp một số thiết bị và dễ fatigue | Nhiều factor, context và rate limit |
| Passkey bắt buộc một thiết bị | Khóa người dùng ngoài platform đó | Cross-device flow và fallback an toàn |
| Recovery chỉ qua email | Mailbox bị chiếm có thể chiếm luôn account | Kênh độc lập và identity proofing |
| Support nhận OTP | Tạo kênh lộ credential | Agent không xem secret, audit và approval |
| Timeout không cảnh báo | Mất dữ liệu và gây lặp thao tác | Warning, continuation và reauth |
| Custom control thiếu semantics | Screen reader không hiểu role/state | Native HTML và accessibility tree test |
| Accessibility bypass yếu | Attacker chọn đường ít bảo vệ | Assurance tương xứng cho mọi alternative |
| Chỉ test bằng automated scanner | Bỏ sót focus, timing và cognitive barrier | Manual và user testing |

## 22. Tình huống thực hành

Một cổng dịch vụ yêu cầu login password, sau đó CAPTCHA hình ảnh, rồi OTP qua SMS. CAPTCHA không có alternative; OTP gồm sáu ô tự chuyển focus, mã hết hạn sau 20 giây và paste bị chặn. Người dùng có thể gọi support để bỏ MFA nhưng agent chỉ hỏi ngày sinh và email. Sau khi login, session hết hạn bất ngờ sau 5 phút mà không cảnh báo.

**Yêu cầu:** thiết kế lại luồng để tiếp cận hơn mà vẫn giữ assurance.

**Hướng phân tích:**

1. Thay CAPTCHA hình ảnh duy nhất bằng risk-based bot defense, rate limiting và challenge có alternative accessible.
2. Cho phép password manager, paste và autocomplete đúng semantics; cung cấp passkey nếu phù hợp.
3. Thay OTP sáu ô bằng một input có label, input mode, one-time-code autocomplete, paste và error association.
4. Điều chỉnh TTL theo threat model và khả năng sử dụng; cung cấp resend có rate limit, không spam countdown.
5. Bổ sung factor alternative như TOTP/passkey/security key theo assurance và thiết bị hỗ trợ; không coi SMS là fallback duy nhất.
6. Thay câu hỏi ngày sinh/email bằng identity proofing/support workflow có assurance, dual control khi cần và audit.
7. Cảnh báo trước session timeout, cho phép gia hạn có kiểm soát và giữ nội dung an toàn.
8. Kiểm thử keyboard, screen reader, zoom, mobile, reduced motion, recovery abuse, replay và account enumeration.
9. Mời người dùng có nhu cầu khác nhau tham gia usability test; sửa lỗi theo mức độ ảnh hưởng.

## 23. Câu hỏi tự kiểm tra

1. **Accessible authentication là gì?** Luồng xác thực mà người dùng có khả năng và cách tương tác khác nhau có thể hoàn tất an toàn và độc lập.
2. **Vì sao accessibility phải bao phủ recovery?** Recovery có thể là đường duy nhất để lấy lại account và thường là điểm yếu bảo mật.
3. **WCAG 2.2 3.3.8 đề cập điều gì?** Tránh bắt buộc cognitive function test trong authentication trừ các điều kiện/ngoại lệ được tiêu chí quy định.
4. **Có nên chặn paste password để chống đánh cắp không?** Không; cho phép password manager và bảo vệ bằng MFA, rate limit, phishing resistance và detection.
5. **Vì sao một input OTP thường tốt hơn sáu ô?** Dễ label, paste, autofill, sửa lỗi và điều hướng bằng screen reader.
6. **Passkey có tự động giải quyết mọi accessibility barrier không?** Không; enrollment, thiết bị, cross-device flow, fallback và recovery vẫn cần thiết kế.
7. **Có nên bỏ MFA cho người dùng cần assistive technology?** Không; cung cấp phương thức thay thế có assurance tương xứng.
8. **Error message nên như thế nào?** Rõ cách sửa, được công nghệ hỗ trợ công bố và không tiết lộ thông tin giúp enumeration.
9. **Vì sao timeout cần được xem xét?** Người dùng có thể cần thêm thời gian để đọc, nghe, chuyển app hoặc nhập thông tin.
10. **Làm sao kiểm chứng accessibility?** Kết hợp automated checks, keyboard/screen reader/manual testing và nghiên cứu với người dùng thực tế.

**Ghi nhớ:** Accessible authentication là khả năng hoàn tất toàn bộ hành trình đăng nhập, MFA, enrollment và recovery bằng nhiều phương thức tương tác. Dùng semantic controls, label và error rõ ràng, cho phép password manager/paste, thiết kế OTP và passkey dễ dùng, quản lý timeout hợp lý và cung cấp alternative có assurance tương xứng. Không giải quyết accessibility bằng cách bỏ MFA hoặc làm yếu recovery; hãy kiểm thử cùng công nghệ hỗ trợ và người dùng có nhu cầu đa dạng.
