# One time password presentation

## 1. OTP được trình bày như thế nào trong khôi phục tài khoản?

Trong luồng khôi phục tài khoản, *one time password presentation* gồm cách đưa mã dùng một lần đến người dùng, hướng dẫn họ nhập mã và chuyển mã đến máy chủ xác minh. Thiết kế này phải giúp người đang mất quyền truy cập hoàn thành đúng thao tác, đồng thời hạn chế việc lộ mã, nhập nhầm, gửi lại liên tục và chiếm đoạt tài khoản.

Cần phân biệt ba vị trí:

- **Kênh nhận mã:** email, SMS hoặc thiết bị xác thực đang được người dùng kiểm soát.
- **Màn hình khôi phục:** giải thích mã dùng để làm gì và nhận giá trị người dùng nhập.
- **Máy chủ xác minh:** quyết định mã còn hợp lệ, thuộc yêu cầu nào và cho phép chuyển sang bước nào.

Màn hình công khai không được nhận sẵn mã đúng từ API rồi tự so sánh trong JavaScript. Nếu người chỉ biết tên tài khoản có thể đọc mã từ phản hồi mạng, họ đã có luôn bằng chứng mà hệ thống đang yêu cầu.

**“Dùng một lần” là thuộc tính do máy chủ thực thi.** Việc xóa ô nhập, ẩn mã hoặc chạy đồng hồ đếm ngược không làm mã hết giá trị trên máy chủ.

Trong bài này, một mã đúng được xem là bằng chứng về quyền kiểm soát một phương thức đã gắn với tài khoản. Chính sách khôi phục vẫn phải quyết định bằng chứng đó có đủ để đặt lại mật khẩu, thay MFA hoặc đăng ký passkey mới hay không.

## 2. Phân biệt các loại mã trước khi thiết kế giao diện

Không phải mọi chuỗi sáu chữ số đều có cùng nguồn gốc hay cùng cách xử lý.

| Loại mã | Người dùng lấy mã ở đâu? | Giao diện cần nói rõ điều gì? | Điểm cần phân biệt |
| --- | --- | --- | --- |
| Mã khôi phục được cấp theo yêu cầu | Email hoặc SMS tới địa chỉ đã đăng ký | Mục đích, hạn sử dụng, cách xin mã khác | Máy chủ tạo mã và quản lý vòng đời của yêu cầu |
| TOTP | Ứng dụng hoặc thiết bị xác thực đã đăng ký | Nhập mã đang xuất hiện trên thiết bị | Mã thay đổi theo thời gian; không có thao tác “gửi lại TOTP” |
| HOTP | Thiết bị hoặc ứng dụng dùng bộ đếm | Nhập mã theo hướng dẫn của thiết bị | Không áp dụng máy móc đồng hồ hết hạn kiểu TOTP |
| Mã khôi phục dự phòng | Bản lưu mà người dùng đã cất giữ trước đó | Nhập một mã chưa dùng trong bộ mã | Có thể dài và chứa chữ; không ép vào biểu mẫu OTP sáu chữ số |

TOTP sử dụng thời gian làm yếu tố thay đổi; HOTP sử dụng bộ đếm. Với TOTP, cùng một giá trị có thể còn xuất hiện trong một cửa sổ thời gian, nhưng máy chủ không được chấp nhận lại mã sau khi đã xác minh thành công. Xem [RFC 6238, phần giới thiệu và mục 5.2](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2).

Nếu người dùng mất ứng dụng TOTP, yêu cầu họ nhập mã từ chính ứng dụng đó không tạo ra một đường khôi phục khả dụng. Giao diện phải đưa họ sang phương thức còn dùng được, chẳng hạn mã dự phòng hoặc quy trình xác minh khác đã được thiết kế trước.

## 3. Xác định mục đích trước khi yêu cầu nhập mã

Xét tình huống: Lan quên mật khẩu, vẫn truy cập được email đã đăng ký nhưng đã mất điện thoại chứa ứng dụng MFA.

Một màn hình chỉ ghi “Nhập OTP để tiếp tục” khiến Lan không biết mình đang:

- Xác nhận quyền truy cập email.
- Đặt lại mật khẩu.
- Yêu cầu thay phương thức MFA.
- Hay đăng nhập vào toàn bộ tài khoản.

Thay vào đó, bước hiện tại nên có tên cụ thể: **“Xác minh email để tiếp tục khôi phục mật khẩu”**. Sau khi xác minh, màn hình tiếp theo phải phản ánh đúng quyền vừa được cấp.

Nếu email OTP chỉ đủ để tiếp tục đặt lại mật khẩu, máy chủ không được đồng thời xóa MFA của Lan. Muốn thay MFA, hệ thống cần áp dụng chính sách riêng cho hành động đó. Tương tự, OTP không khôi phục khóa riêng của passkey đã mất; một luồng đủ điều kiện chỉ có thể cho phép đăng ký phương thức mới hoặc quản lý phương thức cũ theo chính sách.

OTP nhập thủ công có thể bị lấy qua trang giả rồi chuyển tiếp tới dịch vụ thật. NIST phân biệt rõ OTP với phương thức chống phishing; một giao diện có cảnh báo không làm thay đổi giới hạn này. Xem [NIST SP 800-63B-4, mục 3.2.5](https://pages.nist.gov/800-63-4/sp800-63b.html#phishing).

## 4. Luồng minh họa từ yêu cầu mã tới quyền khôi phục

Sơ đồ dưới đây là một phương án thiết kế cho mã được gửi qua kênh đã đăng ký. Các bước và tên trạng thái là minh họa, không phải giao thức bắt buộc.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant UI as Màn hình khôi phục
    participant S as Máy chủ
    participant C as Kênh đã đăng ký

    U->>UI: Nhập thông tin tài khoản
    UI->>S: Yêu cầu bắt đầu khôi phục
    S-->>UI: Thông báo trung lập và ngữ cảnh luồng
    opt Có tài khoản và đủ điều kiện gửi
        S->>C: Gửi mã cùng mục đích và hạn sử dụng
    end
    U->>UI: Nhập mã nhận được
    UI->>S: Gửi mã trong ngữ cảnh khôi phục
    S->>S: Kiểm tra liên kết, hạn, số lần thử và mã
    alt Bằng chứng hợp lệ và đủ theo chính sách
        S->>S: Tiêu thụ mã, tạo quyền khôi phục giới hạn
        S-->>UI: Chuyển đến hành động được phép
    else Cần thêm bằng chứng
        S-->>UI: Chuyển đến bước xác minh bổ sung
    else Không thể xác minh
        S-->>UI: Thông báo và hướng xử lý phù hợp
    end
~~~

Ở bước bắt đầu công khai, một thông báo có thể là:

> Nếu thông tin khớp với tài khoản đủ điều kiện, chúng tôi sẽ gửi mã khôi phục đến kênh đã đăng ký.

Thông báo này cần đi cùng cách xử lý phản hồi và thời gian xử lý phù hợp để hạn chế dò tìm tài khoản. Không chỉ đổi câu chữ rồi trả về các mã lỗi hoặc trường dữ liệu khác nhau cho tài khoản tồn tại và không tồn tại. Đây là nguyên tắc được nêu trong [OWASP Forgot Password Cheat Sheet, phần Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

### Hiển thị địa chỉ nhận mã mà không làm lộ thông tin

Trong phương án minh họa:

- Trước khi có bằng chứng phù hợp, giao diện không công bố email hoặc số điện thoại đang lưu chỉ từ một tên đăng nhập công khai.
- Nếu cần nhắc lại email mà người dùng vừa nhập, có thể che chính giá trị họ đã cung cấp và giữ thông báo có điều kiện.
- Khi đã có ngữ cảnh được phép tiết lộ, có thể hiển thị dạng như “Email kết thúc bằng @example.com” hoặc số điện thoại đã che theo chính sách riêng tư.
- Không cho đổi đích nhận mã sang một số điện thoại mới rồi coi đó là bằng chứng sở hữu tài khoản cũ.

Địa chỉ đã che vẫn có thể tiết lộ dữ liệu. Vì vậy, cần quyết định khi nào được hiển thị, thay vì mặc định rằng thêm dấu sao đã giải quyết mọi rủi ro.

## 5. Trình bày mã trong email hoặc SMS

Thông điệp gửi mã nên trả lời được: dịch vụ nào gửi, người dùng đang làm gì, mã nào cần nhập và mã còn dùng được đến khi nào.

Ví dụ dưới đây dùng dữ liệu giả để minh họa:

~~~text
Dịch vụ Minh Họa — Khôi phục mật khẩu

Mã xác minh của bạn: 004281

Mã dùng cho yêu cầu khôi phục mật khẩu này.
Hết hạn lúc 14:35, ngày 23/11/2026, giờ Việt Nam.

Chỉ nhập mã trên trang khôi phục chính thức của Dịch vụ Minh Họa.
Không đọc hoặc chuyển mã cho người tự xưng là nhân viên hỗ trợ.

Nếu bạn không yêu cầu khôi phục, không sử dụng mã này.
~~~

Một số lựa chọn thiết kế cho thông điệp:

- Đặt mã trong nội dung văn bản thật để có thể đọc, chọn và sao chép; không chỉ nhúng mã thành ảnh.
- Dùng chữ số và khoảng cách dễ nhận diện. Nếu trình bày thành “004 281”, ô nhập phải hỗ trợ cách sao chép này theo quy tắc định dạng đã công bố.
- Tránh đặt mã trong tiêu đề email vì tiêu đề thường được lộ trong danh sách thư và thông báo.
- Không đưa thêm mật khẩu mới, mã dự phòng khác hoặc dữ liệu cá nhân không cần thiết.
- Ghi rõ thời điểm hết hạn và múi giờ khi dùng thời gian tuyệt đối.
- Nội dung phải phản ánh đúng hành động: mã khôi phục mật khẩu không được ghi thành mã xác nhận thanh toán.

Cảnh báo không chia sẻ mã hỗ trợ người dùng nhận biết lừa đảo, nhưng vẫn cần giới hạn thử mã và quyền sau xác minh ở máy chủ. Người tấn công có thể đọc được OTP trong thời gian mã còn hiệu lực.

## 6. Thiết kế biểu mẫu nhập OTP

### Một ô nhập có ngữ nghĩa rõ ràng

Một ô nhập văn bản thường là điểm xuất phát dễ triển khai cho bàn phím, thao tác dán và công cụ hỗ trợ. Nếu giao diện muốn tạo hình sáu ô, có thể trình bày trực quan như vậy nhưng vẫn giữ một trường nhập có ngữ nghĩa rõ ràng.

Ví dụ cho chính sách mã gồm đúng sáu chữ số:

~~~html
<form method="post" action="/account-recovery/verify">
  <h1>Xác minh để tiếp tục khôi phục mật khẩu</h1>

  <p id="otp-help">
    Nhập mã gồm 6 chữ số từ thông điệp khôi phục.
    Bạn có thể dán toàn bộ mã vào ô bên dưới.
  </p>

  <input type="hidden" name="challengeId"
         value="{{serverRenderedChallengeId}}">
  <input type="hidden" name="csrfToken"
         value="{{serverRenderedCsrfToken}}">

  <label for="recovery-otp">Mã xác minh</label>
  <input id="recovery-otp"
         name="otp"
         type="text"
         inputmode="numeric"
         autocomplete="one-time-code"
         minlength="6"
         maxlength="6"
         pattern="[0-9]{6}"
         aria-describedby="otp-help otp-feedback"
         required>

  <p id="otp-feedback" role="status" aria-live="polite"></p>

  <button type="submit">Xác minh mã</button>
</form>
~~~

Các giá trị trong dấu ngoặc nhọn là chỗ để máy chủ điền dữ liệu đã được escape cho thuộc tính HTML. Máy chủ phải tạo và kiểm tra CSRF token phù hợp với phiên; một hidden input tự nó không bảo vệ yêu cầu.

Thuộc tính `autocomplete="one-time-code"` biểu đạt đây là trường nhập mã dùng một lần trong [HTML Standard, bảng ý nghĩa các giá trị autocomplete](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#attr-fe-autocomplete-one-time-code). Việc trình duyệt có gợi ý hoặc tự điền được mã còn phụ thuộc thiết bị, kênh gửi và khả năng hỗ trợ.

Các thuộc tính trong ví dụ có vai trò khác nhau:

| Thành phần | Vai trò trong biểu mẫu |
| --- | --- |
| `type="text"` | Giữ OTP là chuỗi, bao gồm chữ số 0 ở đầu |
| `inputmode="numeric"` | Gợi ý bàn phím số; không tự kiểm tra dữ liệu |
| `minlength`, `maxlength`, `pattern` | Hỗ trợ nhập đúng định dạng trên trình duyệt |
| `label` | Cung cấp tên trường nhập cho người dùng và công cụ hỗ trợ |
| `aria-describedby` | Liên kết trường với hướng dẫn và phản hồi |
| Nút xác minh | Cho người dùng chủ động gửi mã |

Những ràng buộc HTML có thể bị bỏ qua bằng một yêu cầu HTTP tự tạo. Máy chủ vẫn phải kiểm tra đầy đủ.

### Cho phép dán và tự điền

Không chặn paste, không buộc ghi nhớ mã rồi gõ lại từng chữ số. Với nhiều ô nhập riêng, thao tác dán toàn bộ mã phải hoạt động và thứ tự focus phải dự đoán được.

WCAG 2.2 đề cập hỗ trợ sao chép, dán và cơ chế trợ giúp nhằm giảm yêu cầu ghi nhớ hoặc chép lại thông tin trong xác thực; hướng dẫn cũng bao gồm khôi phục tài khoản. Xem [W3C, Understanding Accessible Authentication (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html).

Khi xác minh thất bại, thông báo cần được công cụ hỗ trợ tiếp cận mà không gây lặp vô hạn. Có thể đặt `aria-invalid="true"` cho trường liên quan khi phù hợp và hướng focus có chủ đích. Không chỉ dùng màu đỏ để diễn đạt lỗi.

Không đọc to đồng hồ mỗi giây qua vùng live. Chỉ thông báo các thay đổi có ý nghĩa, như mã đã hết hạn hoặc đã có thể gửi lại.

### Hiện hay che mã?

Hiện mã giúp phát hiện lỗi nhập; che mã có thể hữu ích khi có người đứng gần. Đây là lựa chọn trải nghiệm cần cân nhắc theo môi trường sử dụng.

Nếu có nút hiện hoặc ẩn mã, nút phải có tên và trạng thái rõ ràng, dùng được bằng bàn phím và không làm mất giá trị đang nhập. Việc che ký tự không ngăn được script độc hại đọc giá trị của trường.

## 7. Giữ đúng giá trị mã từ giao diện đến máy chủ

Với ví dụ `004281`, mã phải được xử lý như chuỗi ở mọi tầng: biểu mẫu, JSON hoặc form data, DTO và hàm xác minh. Chuyển sang số nguyên sẽ làm mất hai chữ số 0 ở đầu.

Quy tắc định dạng nên được quyết định trước. Một phương án minh họa là:

1. Chấp nhận đúng sáu chữ số ASCII từ 0 đến 9.
2. Chỉ bỏ khoảng trắng ASCII được cho phép khi hỗ trợ sao chép mã có nhóm.
3. Sau chuẩn hóa, kiểm tra lại toàn bộ chuỗi có đúng sáu chữ số.
4. Từ chối ký tự khác; không lấy sáu chữ số đầu rồi bỏ phần dư.

Ví dụ với phương án này:

| Dữ liệu nhận | Kết quả định dạng |
| --- | --- |
| `004281` | Giữ nguyên |
| `004 281` | Có thể chuẩn hóa thành `004281` nếu sản phẩm hỗ trợ |
| `0042819` | Từ chối vì thừa chữ số |
| `00428A` | Từ chối vì có ký tự ngoài tập cho phép |
| `4281` | Từ chối; không tự thêm số 0 để đoán ý người dùng |

Biểu mẫu HTML tối giản ở trên dành cho chuỗi sáu chữ số liền nhau. Nếu hỗ trợ dạng có khoảng trắng, cần bổ sung xử lý dán và điều chỉnh giới hạn độ dài phù hợp trước khi áp dụng kiểm tra trên trình duyệt; không chỉ sửa máy chủ rồi để trình duyệt tiếp tục chặn thao tác.

Không tự động chuyển sang hỗ trợ mọi chữ số Unicode mà chưa xác định quy tắc. Giao diện và máy chủ phải thống nhất cách chấp nhận, chuẩn hóa và giải thích lỗi.

## 8. Trạng thái màn hình, thời hạn và thao tác gửi lại

### Tách ba loại giới hạn

Thời hạn mã, thời gian chờ gửi lại và thời hạn toàn bộ luồng là ba khái niệm khác nhau.

| Giới hạn | Câu hỏi được trả lời | Ví dụ minh họa |
| --- | --- | --- |
| Thời hạn của mã | Mã này còn được xác minh đến khi nào? | 5 phút từ lúc cấp |
| Thời gian chờ gửi lại | Khi nào được yêu cầu gửi tiếp? | Sau 60 giây |
| Thời hạn luồng | Ngữ cảnh khôi phục này còn được sử dụng đến khi nào? | 15 phút từ lúc bắt đầu |

Các con số trên chỉ phục vụ ví dụ. Không dùng chúng như tiêu chuẩn áp dụng cho mọi tài khoản hay mọi kênh.

Giao diện có thể tính thời gian còn lại từ dữ liệu thời gian máy chủ trả về. Máy chủ phải tự kiểm tra thời hạn khi nhận yêu cầu; sửa đồng hồ thiết bị hoặc tải lại trang không được kéo dài hiệu lực.

### Phản hồi theo trạng thái

| Trạng thái | Cách trình bày minh họa | Hành vi cần có |
| --- | --- | --- |
| Chờ nhập | “Nhập mã từ thông điệp khôi phục” | Cho dán mã và tìm phương thức khác |
| Đang xác minh | “Đang kiểm tra mã…” | Hạn chế gửi lặp từ giao diện, giữ ngữ cảnh |
| Không thể xác minh | “Không thể xác minh mã. Kiểm tra mã mới nhất hoặc yêu cầu mã khác khi được phép.” | Không tiết lộ tài khoản có tồn tại |
| Bị giới hạn | “Tạm thời chưa thể thử tiếp. Vui lòng chờ theo hướng dẫn.” | Tuân theo quyết định máy chủ |
| Mất kết nối | “Chưa nhận được kết quả xác minh” | Không khẳng định mã sai hoặc tự tăng lượt thử trên máy khách |
| Đủ bằng chứng | “Đã xác minh. Tiếp tục đặt lại mật khẩu” | Chuyển đúng hành động được phép |
| Cần thêm bằng chứng | “Cần hoàn thành thêm một bước xác minh” | Giải thích bước tiếp theo khả dụng |

Câu chữ được chọn theo ngữ cảnh có thể tiết lộ. Lý do nội bộ như mã đã dùng, sai, hết hạn hoặc bị thay thế có thể được ghi thành mã sự kiện riêng; không nhất thiết phản chiếu từng lý do ra màn hình công khai.

### Chính sách gửi lại cần nhất quán

Với mã cấp theo yêu cầu, một phương án là chỉ duy trì một mã đang hoạt động cho mỗi mục đích trong luồng. Khi cấp mã thay thế, máy chủ vô hiệu hóa mã cũ và giao diện nhắc dùng mã trong thông điệp mới nhất.

Phương án đó phải được xử lý nhất quán khi có yêu cầu đồng thời. Hai lần nhấn gửi lại không được vô tình tạo ra hai mã đều hợp lệ nếu chính sách chỉ cho phép một mã.

Cần cân nhắc độ trễ giao nhận: thông điệp cũ có thể tới sau thông điệp mới. Hiển thị thời điểm cấp hoặc ngữ cảnh yêu cầu trong thông điệp giúp người dùng phân biệt.

Gửi lại không được biến thành cách xóa số lần nhập sai đã tích lũy. Trong thiết kế này, giới hạn trên toàn luồng hoặc tài khoản vẫn còn hiệu lực sau khi thay mã. Đồng thời, hạn chế gửi mã cần được thực thi ở máy chủ; vô hiệu hóa nút trong 60 giây chỉ hỗ trợ trải nghiệm.

## 9. Hợp đồng giữa giao diện và máy chủ xác minh

### Dữ liệu được phép đưa ra giao diện

Một phản hồi chuẩn bị màn hình có thể gồm:

~~~json
{
  "challengeId": "opaque-random-challenge-id",
  "purpose": "PASSWORD_RECOVERY",
  "codeLength": 6,
  "expiresAt": "2026-11-23T07:35:00Z",
  "serverTime": "2026-11-23T07:30:00Z",
  "resendAvailableAt": "2026-11-23T07:31:00Z"
}
~~~

Đây là hợp đồng minh họa. Nếu dùng cùng dạng phản hồi cho yêu cầu công khai, phải thiết kế sao cho các trường này không trở thành tín hiệu phân biệt tài khoản tồn tại. Chẳng hạn, ngữ cảnh công khai có thể được tạo cho mọi yêu cầu hợp lệ về hình thức, còn việc có được gửi mã hay không là quyết định nội bộ.

Không trả `expectedOtp`, bản băm của OTP hoặc một trường “debug” chứa mã. Mã ngẫu nhiên của challenge cũng không được coi là bằng chứng đã xác minh.

Trường `purpose` trong phản hồi chỉ mô tả bước cho giao diện. Máy chủ phải dùng mục đích đã lưu, không tin một giá trị do máy khách gửi để chuyển từ khôi phục mật khẩu sang xóa MFA.

### Dữ liệu máy chủ cần liên kết

Trong phương án này, bản ghi challenge liên kết tối thiểu:

- Tài khoản nội bộ và mục đích khôi phục.
- Ngữ cảnh hoặc phiên khởi tạo được phép sử dụng challenge.
- Dữ liệu xác minh mã được bảo vệ.
- Thời điểm cấp, hết hạn và trạng thái đã dùng hoặc đã thay thế.
- Ngân sách thử mã và thông tin giới hạn gửi lại cần thiết.

Mã gửi qua kênh phải được sinh bằng bộ sinh ngẫu nhiên mật mã. Vì mã ngắn có không gian đoán nhỏ, thiết kế lưu trữ cũng phải xét nguy cơ dò ngoại tuyến: một bản băm nhanh không khóa của sáu chữ số có thể bị vét cạn. Một lựa chọn triển khai là dùng MAC có khóa máy chủ được quản lý riêng, gắn cả ngữ cảnh challenge vào dữ liệu xác minh; lựa chọn cụ thể cần được đánh giá cùng cơ chế quản lý khóa.

### Xác minh và tiêu thụ mã

Mã giả dưới đây mô tả thứ tự trách nhiệm, không phải mã có thể đưa thẳng vào production:

~~~text
verifyRecoveryCode(flowSession, challengeId, submittedCode):
    enforceServerSideRateLimits(flowSession, challengeId)
    validateInputFormat(submittedCode)

    atomically:
        challenge = loadForUpdate(challengeId)
        requireBoundFlow(challenge, flowSession)
        requireExpectedPurpose(challenge)
        requireActiveAndNotExpired(challenge)
        requireRemainingAttemptBudget(challenge)

        recordVerificationAttemptDurably(challenge)

        if not verifyProtectedCode(challenge, submittedCode):
            persistAttemptEvenWhenRejected()
            return CANNOT_VERIFY

        markChallengeConsumed(challenge)
        recordRecoveryEvidence(challenge)

        if recoveryPolicyIsSatisfied(challenge):
            createScopedRecoveryGrant(challenge)
            return ALLOWED_RECOVERY_ACTION

        return NEXT_REQUIRED_VERIFICATION
~~~

“Atomically” diễn đạt yêu cầu đồng thời: hai yêu cầu dùng cùng một challenge không được cùng tiêu thụ thành công để cấp hai quyền độc lập. Cần dùng giao dịch, khóa hoặc cập nhật có điều kiện thích hợp với hệ lưu trữ.

Lượt thử thất bại phải được lưu dù kết quả nghiệp vụ bị từ chối; không để ném lỗi rồi rollback luôn bộ đếm. Giới hạn thử theo tài khoản hoặc toàn luồng cũng cần được cập nhật nhất quán khi có nhiều yêu cầu song song.

Với mã sáu chữ số phân bố đều, có một triệu khả năng. Nếu chỉ cho phép năm lần đoán độc lập với một mã hợp lệ duy nhất, xác suất đoán trúng xấp xỉ:

~~~text
5 / 1.000.000 = 0,000005 = 0,0005%
~~~

Phép tính không bao gồm mã bị đánh cắp, phishing, nhiều cửa sổ mã hợp lệ hoặc nhiều challenge. Nó cho thấy vì sao độ dài mã phải đi cùng giới hạn trên phạm vi rộng hơn một yêu cầu đơn lẻ.

## 10. Sau OTP: chỉ cấp quyền phù hợp với bằng chứng

Với khôi phục mật khẩu, có thể cấp một phiên giới hạn chỉ cho phép đặt mật khẩu mới. OWASP mô tả cách dùng PIN để tạo loại phiên giới hạn này trong [Forgot Password Cheat Sheet, phần PINs](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#pins).

Trong thiết kế minh họa, quyền khôi phục có các thuộc tính:

- Gắn với tài khoản, mục đích và bằng chứng đã được chấp nhận.
- Có thời hạn ngắn được kiểm tra ở máy chủ.
- Không được dùng để đọc dữ liệu tài khoản hoặc thay phương thức khác ngoài phạm vi cho phép.
- Bị tiêu thụ sau khi hành động được phê duyệt hoàn tất.
- Với trình duyệt, có thể được đại diện bằng cookie phiên ngẫu nhiên, bảo vệ bằng HTTPS, Secure, HttpOnly và chính sách SameSite phù hợp; thao tác thay đổi trạng thái vẫn cần chống CSRF.

Nếu phản hồi xác minh bị mất trên đường về, người dùng có thể không biết mã đã được tiêu thụ. Có thể cung cấp cách kiểm tra tiến độ bằng phiên khôi phục đã liên kết, thay vì cho mã cũ tái sử dụng hoặc tự tạo thêm quyền từ mỗi lần gửi lại.

Khi hoàn tất, hệ thống cần xác định các phiên đăng nhập và refresh token cũ nào phải bị thu hồi theo tình huống rủi ro. Thay đổi mật khẩu, thay MFA và thay passkey không nhất thiết có cùng chính sách thu hồi. Giao diện phải giải thích hành động có ảnh hưởng đến các thiết bị đang đăng nhập khi cần.

NIST mô tả khôi phục bằng mã, liên hệ khôi phục hoặc xác minh lại danh tính, đồng thời yêu cầu thông báo sự kiện khôi phục cho chủ tài khoản. Tham khảo [NIST SP 800-63B-4, phần Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery). Những lựa chọn này cần được cụ thể hóa theo mức bảo đảm mà dịch vụ đặt ra.

## 11. Ngăn lộ mã qua các thành phần phụ

Một biểu mẫu đúng vẫn có thể làm lộ mã nếu hệ thống xung quanh ghi lại dữ liệu nhạy cảm. Trong phương án triển khai, cần xác định rõ ranh giới dữ liệu:

| Thành phần | Thiết kế cần xem xét |
| --- | --- |
| URL | Gửi OTP trong phần thân yêu cầu, không đặt vào query string hoặc fragment |
| Log HTTP, APM, trace | Che hoặc loại bỏ OTP, cookie, quyền khôi phục và dữ liệu nhận dạng không cần thiết |
| Analytics và session replay | Không ghi giá trị ô nhập; xem xét loại bỏ hoàn toàn trang khôi phục khỏi công cụ ghi phiên |
| Bộ nhớ trình duyệt | Không lưu OTP hoặc quyền khôi phục vào localStorage |
| Cache | Đặt chính sách như Cache-Control: no-store cho phản hồi chứa ngữ cảnh nhạy cảm |
| Script bên thứ ba | Giảm thành phần có khả năng đọc biểu mẫu; áp dụng chính sách nội dung phù hợp |
| Công cụ hỗ trợ nội bộ | Cho biết trạng thái xử lý mà không cung cấp chức năng xem lại mã đúng |

Một sự kiện vận hành có thể ghi loại hành động, thời điểm, kết quả tổng quát và mã tương quan đã được quản lý quyền truy cập. Không cần ghi mã người dùng vừa nhập để đo tỷ lệ lỗi.

Các chỉ số hữu ích cho luồng gồm tỷ lệ gửi mã thành công, độ trễ nhận mã, tỷ lệ xác minh hoàn tất và số lần bị giới hạn. Phân tích các chỉ số này giúp phát hiện lỗi giao nhận hoặc lạm dụng mà không phải thu thập bí mật xác thực.

## 12. Vận dụng thiết kế vào các tình huống khôi phục

| Tình huống | Cách trình bày và xử lý phù hợp trong thiết kế |
| --- | --- |
| Quên mật khẩu, còn kênh khôi phục đã đăng ký | Giải thích xác minh kênh để tiếp tục đặt lại mật khẩu; giữ nguyên các bước khác mà chính sách yêu cầu |
| Mất điện thoại chứa TOTP | Cho chuyển sang phương thức đã chuẩn bị trước; không tiếp tục yêu cầu mã từ thiết bị đã mất |
| Mất passkey trên một thiết bị | Hướng dẫn thử phương thức khác còn dùng được; chỉ cho đăng ký passkey mới khi đủ bằng chứng |
| Không còn truy cập bất kỳ kênh đã đăng ký nào | Chuyển sang quy trình khôi phục khác được phê duyệt; không gửi mã tới địa chỉ mới rồi coi là đã xác minh |
| Nhận mã nhưng không yêu cầu | Hướng dẫn không dùng, không chia sẻ mã và sử dụng kênh hỗ trợ chính thức khi cần |
| Mã cũ tới sau mã mới | Làm rõ chính sách dùng mã mới nhất nếu đã chọn cơ chế thay thế mã |
| Người dùng dùng trình đọc màn hình | Có nhãn, hướng dẫn, phản hồi và thao tác dán; không chỉ phân biệt trạng thái bằng màu |
| Kẻ tấn công gọi API trực tiếp | Giữ nguyên kiểm tra định dạng, thời hạn, giới hạn thử và liên kết challenge ở máy chủ |

Quay lại tình huống của Lan: xác minh email có thể giúp cô tiếp tục phần khôi phục mật khẩu nếu chính sách cho phép. Việc mất điện thoại MFA vẫn cần một quyết định khôi phục riêng. Giao diện tốt giúp Lan hiểu từng bước và tìm được đường đi khả dụng; máy chủ bảo đảm mỗi bước chỉ mở quyền tương ứng.

Một thiết kế OTP hoàn chỉnh phải trả lời được bốn câu hỏi: **mã chứng minh điều gì, người dùng lấy và nhập mã thế nào, máy chủ giới hạn việc sử dụng ra sao, và sau khi xác minh người dùng được làm gì**.
