# Recovery page autofill — Tự động điền trên trang khôi phục tài khoản

## 1. Autofill hỗ trợ nhập liệu, không xác minh quyền khôi phục

**Recovery page autofill** là việc trình duyệt, hệ điều hành hoặc trình quản lý mật khẩu hỗ trợ điền dữ liệu trên các trang khôi phục. Dữ liệu có thể là tên tài khoản, mật khẩu mới được tạo hoặc mã xác minh vừa nhận.

Tính năng này giúp người dùng giảm thao tác khi đang gặp khó khăn: quên mật khẩu, mất thiết bị xác thực hoặc cần hoàn tất phục hồi trên điện thoại. Tuy nhiên, điền nhanh không đồng nghĩa dữ liệu phù hợp với hồ sơ đang xử lý.

Ví dụ, Lan có hai tài khoản cá nhân và công việc. Trình quản lý mật khẩu đang gợi ý credential của tài khoản cá nhân, trong khi phiên khôi phục tại máy chủ thuộc tài khoản công việc. Nếu ứng dụng chọn tài khoản đích dựa vào ô vừa được điền, thao tác hỗ trợ của trình duyệt có thể trở thành lỗi thay đổi nhầm tài khoản.

Cần giữ ranh giới rõ ràng:

```text
Trình duyệt gợi ý hoặc điền một giá trị
    → Người dùng có thể xem và chỉnh sửa theo loại trường
    → Form gửi giá trị đến máy chủ
    → Máy chủ xác minh hồ sơ, bằng chứng và quyền thực hiện
```

Không có thuộc tính HTML nào thay thế được bước xác minh cuối cùng. Mật khẩu, OTP hoặc mã khôi phục được autofill vẫn là dữ liệu đầu vào cần kiểm tra.

## 2. Khai báo đúng mục đích từng trường

Thuộc tính `autocomplete` mô tả ý nghĩa dữ liệu mà trường mong đợi. HTML phân biệt tên tài khoản, mật khẩu hiện tại, mật khẩu mới và mã dùng một lần. Các loại này được định nghĩa trong [HTML Standard: Autofill](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill).

| Trường trong luồng khôi phục | Giá trị phù hợp theo ngữ nghĩa | Điều cần tránh |
| --- | --- | --- |
| Định danh dùng để đăng nhập | `username` | Coi mọi ô email là cùng một mục đích |
| Mật khẩu mới | `new-password` | Đánh dấu thành mật khẩu đang dùng |
| Nhập lại mật khẩu mới, nếu có | `new-password` | Dùng `current-password` cho ô xác nhận |
| Mật khẩu hiện tại ở bước tái xác thực riêng | `current-password` | Thêm yêu cầu này vào luồng đã mất mật khẩu mà không có nhánh thay thế |
| OTP xác minh | `one-time-code` | Coi OTP là mật khẩu dài hạn |
| Địa chỉ email liên hệ mới | `email` khi đúng là dữ liệu liên hệ | Tự thay tài khoản cần phục hồi bằng địa chỉ vừa điền |

Địa chỉ email có thể đồng thời là tên đăng nhập, nhưng thuộc tính phải phản ánh **vai trò của trường ở bước hiện tại**. Ví dụ, ô nhập định danh để bắt đầu khôi phục khác với ô đề xuất thay email liên hệ sau khi đã xác minh.

Tính năng gợi ý thực tế còn phụ thuộc trình duyệt, công cụ quản lý mật khẩu và cấu hình người dùng. Không thiết kế luồng chỉ hoạt động khi autofill xuất hiện.

## 3. Form đặt lại mật khẩu cần dùng new-password

Trang đặt lại mật khẩu đang yêu cầu người dùng tạo một credential mới. Nếu đánh dấu ô này là `current-password`, ứng dụng mô tả sai ý nghĩa và có thể khiến công cụ quản lý mật khẩu đưa ra gợi ý không phù hợp.

`new-password` được dùng cho cả ô nhập mật khẩu mới và ô xác nhận mật khẩu mới nếu sản phẩm có ô xác nhận. Đây là cách sử dụng được mô tả trong [MDN: autocomplete](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/autocomplete#new-password).

Ví dụ markup cho bước đã có ngữ cảnh khôi phục hợp lệ:

```html
<form id="reset-password-form"
      action="/recovery/password"
      method="post">
  <input type="hidden"
         name="csrf_token"
         value="{{ csrf_token }}">

  <label for="recovery-username">Tài khoản đang khôi phục</label>
  <input id="recovery-username"
         name="username"
         type="text"
         autocomplete="username"
         value="{{ verified_username }}"
         readonly>

  <label for="new-password">Mật khẩu mới</label>
  <input id="new-password"
         name="new_password"
         type="password"
         autocomplete="new-password"
         required>

  <label for="confirm-new-password">Nhập lại mật khẩu mới</label>
  <input id="confirm-new-password"
         name="new_password_confirmation"
         type="password"
         autocomplete="new-password"
         required>

  <button type="submit">Đặt lại mật khẩu</button>
</form>
```

Các giá trị trong `{{ ... }}` là chỗ để template phía máy chủ sinh dữ liệu và escape đúng ngữ cảnh HTML. Đây là ví dụ cấu trúc form, không phải một endpoint hoàn chỉnh.

Một số giới hạn của ví dụ cần hiểu đúng:

- `verified_username` chỉ được đưa vào trang khi mức xác minh và chính sách riêng tư cho phép hiển thị định danh đó. Không nhét email thật vào input ẩn ở trang công khai chỉ để hỗ trợ autofill.
- `readonly` hỗ trợ cách trình bày tài khoản cố định; máy chủ vẫn phải bỏ qua mọi ý định đổi tài khoản đích từ trường này.
- `required` hỗ trợ trải nghiệm nhập, nhưng máy chủ vẫn kiểm tra mật khẩu, sự khớp nhau và chính sách đặt lại.
- Không trả lại mật khẩu người dùng vừa gửi bằng thuộc tính `value` khi render một thông báo lỗi.
- Token CSRF trong ví dụ không thay cho quyền khôi phục đã được máy chủ xác lập.

Nếu sản phẩm dùng một ô mật khẩu kèm khả năng xem giá trị thay cho ô xác nhận, ngữ nghĩa của ô đó vẫn là `new-password`. Bài học không yêu cầu mọi sản phẩm phải có hai ô.

## 4. Không dùng autocomplete=off như một hàng rào bảo mật

Ví dụ sau không chứng minh rằng trình quản lý mật khẩu sẽ ngừng can thiệp:

```html
<form autocomplete="off">
  <input type="password" name="password">
</form>
```

Các trình duyệt có thể không tuân theo `autocomplete="off"` cho trường đăng nhập nhằm tiếp tục hỗ trợ quản lý mật khẩu. Ngay cả một giá trị khai báo đúng cũng là hướng dẫn cho trình duyệt, không phải quyền cưỡng chế mọi công cụ. Xem [MDN: Managing autofill for login fields](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Turning_off_form_autocompletion#managing_autofill_for_login_fields).

Trong thiết kế tham khảo:

- Mật khẩu mới được khai báo đúng là mật khẩu mới.
- Trường bí mật chỉ có ích trong một tương tác được cân nhắc riêng.
- Trường không có mục đích chuẩn phù hợp không được gán một token tự chế rồi coi như đã có bảo vệ.
- Máy chủ không hạ yêu cầu xác minh dựa vào việc trang đã bật hoặc tắt autofill.

Không dùng tên như `autocomplete="recovery-password-never-fill"` để tạo cảm giác rằng đây là một loại dữ liệu có ý nghĩa chuẩn.

Một ví dụ rủi ro khác là dùng nhiều input giả để “hứng” mật khẩu được điền. Trong phạm vi luồng của bài học, cách tổ chức này không được chọn: nó làm quan hệ giữa trường hiển thị, dữ liệu gửi và trạng thái giao diện khó hiểu hơn. Form cần mô tả đúng dữ liệu mà người dùng thật sự đang cung cấp.

## 5. OTP là một chuỗi mã, không phải số để tính toán

Giả sử sản phẩm phát hành OTP gồm sáu chữ số. Một trường nhập tham khảo:

```html
<form id="recovery-otp-form"
      action="/recovery/verify-code"
      method="post">
  <input type="hidden"
         name="csrf_token"
         value="{{ csrf_token }}">

  <label for="recovery-otp">Mã xác minh gồm 6 chữ số</label>
  <input id="recovery-otp"
         name="otp"
         type="text"
         inputmode="numeric"
         autocomplete="one-time-code"
         pattern="[0-9]{6}"
         maxlength="6"
         aria-describedby="otp-help"
         required>

  <p id="otp-help">
    Nhập mã được gửi cho yêu cầu khôi phục hiện tại.
  </p>

  <button type="submit">Xác minh mã</button>
</form>
```

Cặp `type="text"` và `inputmode="numeric"` phù hợp khi dữ liệu là chuỗi chữ số còn bàn phím mong muốn là bàn phím số. Hướng dẫn [SMS OTP form best practices](https://web.dev/articles/sms-otp-form#use_the_input_element) trình bày cách dùng này cùng `autocomplete="one-time-code"`.

Mã `004271` có sáu ký tự. Nếu code ứng dụng ép thành số, nó có thể biến thành `4271`. Vì vậy, ví dụ giữ OTP dưới dạng chuỗi từ lúc nhận form đến lúc đối chiếu.

`pattern` và `maxlength` trong markup trên chỉ đúng với giả định sáu chữ số. Nếu sản phẩm dùng độ dài khác hoặc có chữ cái, phải thay hợp đồng dữ liệu tương ứng; không cắt mã hợp lệ để vừa một component có sẵn.

Ở thiết kế này, sản phẩm dùng một input cho toàn bộ mã để giữ đường nhập và dán đơn giản. Nếu giao diện hiển thị thành nhiều ô, vẫn cần giải quyết việc nhập toàn bộ mã, sửa một ký tự và dùng công cụ hỗ trợ một cách nhất quán.

## 6. Tự động điền mã không đồng nghĩa mã thuộc đúng hồ sơ

Lan có thể vừa yêu cầu khôi phục trên hai tab. Mã cũ và mã mới có thể cùng xuất hiện trên thiết bị. Việc công cụ nhập liệu đề xuất một mã không chứng minh mã đó:

- Thuộc tài khoản hiện tại.
- Thuộc lần gửi đang có hiệu lực.
- Chưa hết hạn.
- Chưa được sử dụng.
- Cho phép hành động đang yêu cầu.

Máy chủ cần đối chiếu bằng ngữ cảnh của hồ sơ khôi phục. Ví dụ mã giả:

```text
verifyRecoveryCode(recoverySession, submittedCode):
    requireValidRequestProtection()
    requireAttemptBudget(recoverySession.challengeId)

    challenge = loadChallenge(recoverySession.challengeId)
    require challenge.accountId == recoverySession.accountId
    require challenge.purpose == recoverySession.purpose
    require challenge is active and not expired
    require submittedCode matches challenge

    atomically consume challenge and advance permitted recovery state
```

Đây là mô tả ranh giới trách nhiệm, không phải code triển khai đầy đủ. Cơ chế đối chiếu, lưu mã và chống tranh chấp phải phù hợp hệ thống thực tế.

Khi gửi lại mã, chính sách cần xác định rõ mã cũ còn được chấp nhận hay đã bị thu hồi. Giao diện nên giải thích điều đó bằng lời dễ hiểu. Không để màn hình nói “dùng mã mới nhất” nhưng máy chủ lại không phân biệt được lần phát hành.

Autofill từ SMS cũng không bắt buộc phải hoạt động giống nhau trên mọi nền tảng. Vẫn cần đường nhập tay hoặc dán mã. Khi mã hết hạn, yêu cầu gửi lại phải chịu cùng giới hạn chống lạm dụng như các đường yêu cầu khác.

## 7. Gợi ý OTP từ SMS và ràng buộc miền

Nếu dùng SMS OTP, sản phẩm có thể áp dụng định dạng gắn mã với miền để công cụ hỗ trợ nhận diện ngữ cảnh tốt hơn.

Ví dụ minh họa:

```text
Ma khoi phuc cua ban la 004271.
Khong chia se ma nay voi nguoi khac.

@accounts.example.com #004271
```

Dòng cuối gắn miền và mã theo mô tả của [WICG: Origin-bound one-time codes delivered via SMS](https://wicg.github.io/sms-one-time-codes/#authoring). Đây là tài liệu đề xuất cộng đồng; khả năng hỗ trợ phụ thuộc nền tảng.

Đây là lớp hỗ trợ cách nhận và gợi ý mã. Nó không làm SMS OTP trở thành một bằng chứng chống mọi hình thức lừa đảo, và không thay thế kiểm tra ở endpoint xác minh.

Thiết kế của bài học không tự gửi form chỉ vì ô mã vừa đủ độ dài. Người dùng có thể xem bước đang diễn ra rồi chủ động xác minh. Với luồng có tự động tiếp tục, sản phẩm phải quyết định rõ hành động nào chỉ kiểm tra mã và hành động nào thật sự thay đổi credential.

Không coi thao tác chọn mã từ gợi ý là đồng ý gỡ MFA, thay email khôi phục hoặc tạo passkey mới. Mỗi quyền cần giữ đúng phạm vi mà hồ sơ đã được cấp.

## 8. Mã khôi phục dự phòng cần được phân biệt với mật khẩu và OTP vừa gửi

Mã dự phòng được cấp từ trước có thể gồm chữ cái, chữ số và dấu phân cách. Nó khác trải nghiệm của mã SMS ngắn vừa được phát hành.

Một lựa chọn giao diện minh họa:

```html
<label for="backup-code">Mã khôi phục dự phòng</label>
<input id="backup-code"
       name="backup_code"
       type="text"
       autocomplete="off"
       autocapitalize="off"
       spellcheck="false"
       aria-describedby="backup-code-help"
       required>

<p id="backup-code-help">
  Nhập một mã dự phòng chưa dùng mà bạn đã lưu trước đây.
</p>
```

Trong ví dụ, `autocomplete="off"` thể hiện mong muốn không dùng dữ liệu nhập cũ để gợi ý. Nó không bảo đảm trình duyệt, extension hoặc công cụ bên ngoài không lưu hay điền dữ liệu.

Không áp bàn phím số nếu mã có chữ cái. Cũng không tự đổi hoa/thường, xóa dấu hoặc thay ký tự gần giống nhau nếu quy tắc phát hành mã không cho phép chuẩn hóa theo cách đó.

Mã dự phòng có thể là bằng chứng dùng một lần dù không phải OTP vừa được gửi. Nếu sản phẩm chọn hỗ trợ điền mã từ công cụ quản lý bí mật, cần mô tả rõ cách tương tác. Không gán mã dự phòng thành `current-password` chỉ để tận dụng một gợi ý đang có.

Máy chủ vẫn quyết định mã còn hiệu lực, thuộc tài khoản nào và đã được sử dụng chưa. Giá trị hiển thị trong input không tự chọn được tài khoản đích.

## 9. Hỗ trợ password manager và dán dữ liệu

Người dùng có thể cần dán mật khẩu mới hoặc mã phục hồi từ công cụ đã lưu. Chặn thao tác dán không chứng minh người nhập là chính chủ và có thể khiến việc dùng bí mật dài, ngẫu nhiên trở nên khó khăn hơn.

OWASP khuyến nghị cho phép dán vào các trường tên đăng nhập, mật khẩu và MFA, đồng thời dùng các thành phần form HTML phù hợp. Xem [Authentication Cheat Sheet: Password Managers](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#password-managers).

Đối với form khôi phục của ví dụ:

- Nút xác nhận không phụ thuộc vào việc người dùng đã phát sinh một số lượng phím gõ nhất định.
- Việc dán hoặc autofill không tự bị phân loại thành hành vi bot.
- Giao diện không xóa một giá trị hợp lệ chỉ vì nó được điền mà không có thao tác bàn phím mà ứng dụng mong đợi.
- Nút xem mật khẩu, nếu có, dùng `type="button"` để không vô tình gửi form.
- Trạng thái nhập và thông báo lỗi cần phản ánh giá trị thật mà form sẽ gửi.

Nếu ứng dụng dùng framework để giữ state của form, không nên giả định rằng mọi đường điền dữ liệu đều giống một chuỗi phím gõ. Cách đọc và kiểm tra dữ liệu lúc submit phải thống nhất với input hiện tại, thay vì chỉ dựa vào một cờ “đã gõ” do frontend tự suy ra.

Một người nhập tay vẫn có thể cung cấp mã bị đánh cắp. Ngược lại, một người dùng password manager vẫn có thể là chủ tài khoản hợp lệ. Quyết định xác minh phải dựa vào bằng chứng và chính sách rủi ro phù hợp.

## 10. Giữ đúng tài khoản qua các bước và thông báo kết quả chính xác

Trong ví dụ của bài học, máy chủ xác định tài khoản đích từ phiên hoặc grant khôi phục đã xác minh. Trường `username` trên form giúp người dùng nhận biết ngữ cảnh và hỗ trợ công cụ quản lý credential; nó không phải nguồn cấp quyền.

Nếu Lan đang khôi phục tài khoản công việc nhưng nhìn thấy gợi ý tài khoản cá nhân, cần có cách nhận biết sự khác biệt. Không tự chuyển hồ sơ khôi phục chỉ vì người dùng chọn một mục từ danh sách gợi ý.

Nếu cần đổi tài khoản, luồng có thể yêu cầu quay lại bước khởi tạo và xây dựng hồ sơ phù hợp. Không cho một token đã cấp cho tài khoản A tác động sang tài khoản B qua cách sửa ô email.

Sau khi mật khẩu thực sự được cập nhật, giao diện chuyển sang trạng thái hoàn tất rõ ràng. Việc điều hướng hoặc loại bỏ form mật khẩu sau thành công có thể giúp công cụ quản lý mật khẩu nhận biết thay đổi; hướng dẫn này được nêu trong [web.dev: Sign-in form best practices](https://web.dev/articles/sign-in-form-best-practices#ensure_successful_form_submission).

Phải phân biệt hai kết quả:

```text
Máy chủ đã chấp nhận và cập nhật mật khẩu
    ≠
Trình quản lý mật khẩu đã lưu thành công giá trị mới
```

Ứng dụng không kiểm soát được mọi quyết định lưu credential của trình duyệt hoặc extension. Thông báo nên mô tả kết quả máy chủ thật sự biết, thay vì khẳng định mọi bản lưu trên thiết bị đã được đồng bộ.

## 11. Bảo vệ dữ liệu đã được điền và giữ nguyên mức bảo đảm

Mật khẩu mới, OTP và mã dự phòng trong form đều là dữ liệu nhạy cảm. Thuộc tính `type="password"` che cách hiển thị, nhưng không phải một lớp mã hóa bảo vệ dữ liệu khỏi mọi script chạy trong trang.

Trong thiết kế tham khảo:

1. Không đưa giá trị các trường bí mật vào analytics, session replay hoặc báo cáo lỗi.
2. Không lưu bản nháp mật khẩu và mã khôi phục trong localStorage chỉ để tự khôi phục form.
3. Khi yêu cầu thất bại, không ghi bí mật vào thông báo lỗi hoặc log.
4. Không gửi form đến endpoint do tham số URL tùy ý quyết định.
5. Khi phiên khôi phục hết hạn, dữ liệu còn được điền trên màn hình không làm phiên hợp lệ trở lại.
6. Khi hoàn tất hoặc hủy, đóng quyền của hồ sơ khôi phục theo chính sách; việc xóa input ở giao diện không thay cho bước này.

Với người mất MFA, passkey hoặc thiết bị xác thực, autofill có thể giúp nhập bằng chứng phục hồi còn lại. Nó không tự tạo thêm bằng chứng, không thay thế xác minh danh tính và không cho phép bỏ qua yêu cầu của hành động nhạy cảm.

Giá trị của autofill nằm ở việc giúp người dùng cung cấp đúng dữ liệu dễ hơn. Giá trị của cơ chế khôi phục nằm ở việc máy chủ chỉ chấp nhận dữ liệu đó trong đúng tài khoản, đúng mục đích và đúng phạm vi quyền.
