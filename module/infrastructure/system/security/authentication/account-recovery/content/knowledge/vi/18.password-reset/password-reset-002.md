# Thiết kế form đặt lại mật khẩu an toàn

## Mục tiêu và phạm vi

Trong chương **Password Reset** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, form đặt lại mật khẩu là nơi người dùng chọn bí mật đăng nhập mới sau khi hoàn thành bước xác minh được chính sách chấp nhận.

Form này nằm trong hành trình khôi phục tài khoản khi quên mật khẩu. Nó cần phối hợp với đánh giá rủi ro, token dùng một lần, chống lạm dụng và kiểm soát session. Nếu người dùng còn mất MFA, passkey hoặc thiết bị xác thực, quyền đặt mật khẩu mới không mặc nhiên bao gồm quyền thay những phương thức đó.

Sau bài học, người học cần có khả năng:

- Phân biệt form yêu cầu gửi liên kết, form đổi mật khẩu và form đặt lại mật khẩu.
- Thiết kế trường nhập, thông báo, hỗ trợ trình quản lý mật khẩu và khả năng tiếp cận.
- Giữ chính sách mật khẩu nhất quán giữa giao diện và máy chủ.
- Liên kết form với quyền khôi phục đúng tài khoản, mục đích và thời hạn.
- Xử lý gửi lặp, token hết hạn, nhiều tab và lỗi mạng mà không đặt mật khẩu hai lần.
- Xác định điều kiện chuyển sang màn hình thành công và xử lý session sau thay đổi.

Các đường dẫn, trạng thái, chính sách và mã trong bài là ví dụ thiết kế. Chúng không phải báo cáo về một hệ thống đã được triển khai hoặc kiểm thử.

## 1. Phân biệt ba form có mục đích khác nhau

| Form | Người dùng đang làm gì? | Căn cứ cho phép thao tác |
| --- | --- | --- |
| Yêu cầu khôi phục | Nhập định danh để yêu cầu hướng dẫn hoặc liên kết | Chưa đủ để thay mật khẩu |
| Đổi mật khẩu | Thay mật khẩu trong bối cảnh đã đăng nhập | Session và yêu cầu xác thực lại phù hợp |
| Đặt lại mật khẩu | Chọn mật khẩu mới sau một luồng khôi phục | Quyền đặt lại đã được máy chủ xác minh |

Form đặt lại thường không yêu cầu mật khẩu cũ, vì người dùng có thể đã quên nó. Sự thiếu vắng mật khẩu cũ phải được bù bằng quyền khôi phục hợp lệ, không phải bằng việc tin rằng người dùng đã mở đúng trang.

Form cũng không nên cho nhập tùy ý email hoặc accountId để chọn tài khoản sẽ được thay đổi. Chủ thể của thao tác phải được suy ra từ quyền khôi phục do máy chủ quản lý.

Nếu trình duyệt đang đăng nhập tài khoản A nhưng mở liên kết đặt lại cho tài khoản B, máy chủ phải xử lý đúng chủ thể của liên kết. Không lấy tài khoản trong session đăng nhập thông thường để thay thế chủ thể của quyền khôi phục.

## 2. Hợp đồng bảo mật của form

Trước khi xây giao diện, cần xác định những điều luôn phải đúng:

1. Chỉ quyền có mục đích đặt lại mật khẩu mới được mở thao tác tương ứng.
2. Tài khoản và tenant đích được lấy từ dữ liệu đáng tin cậy ở máy chủ.
3. Mỗi lần gửi phải kiểm tra lại trạng thái và thời hạn quyền.
4. Sai chính sách mật khẩu không làm thay đổi thông tin đăng nhập.
5. Hai request cạnh tranh không thể cùng tiêu thụ một quyền.
6. Thành công chỉ được thông báo khi thay đổi đã được ghi nhận bền vững.
7. Mật khẩu, token và CSRF token không được đưa vào URL, log hoặc hệ thống phân tích.
8. Hoàn tất form không tự cấp session đăng nhập đầy đủ.
9. Đặt lại mật khẩu không tự vô hiệu MFA hoặc thêm passkey.

OWASP khuyến nghị nhập lại mật khẩu để xác nhận, áp dụng cùng chính sách của ứng dụng, lưu mật khẩu an toàn, thông báo thay đổi và đưa người dùng về luồng đăng nhập bình thường. Xem [OWASP Forgot Password: User Resets Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password).

Điều quan trọng là phân biệt **trang có thể hiển thị** với **thao tác được phép thực hiện**. Việc render form không phải lần kiểm tra quyền cuối cùng.

## 3. Từ liên kết khôi phục đến form

Ví dụ trong bài dùng một reset context: trạng thái ngắn hạn phía máy chủ, chỉ phục vụ việc đặt lại mật khẩu. Trình duyệt giữ một cookie chứa định danh ngẫu nhiên để tham chiếu tới trạng thái đó.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant R as Dịch vụ khôi phục
    participant D as Kho dữ liệu

    U->>B: Mở liên kết khôi phục
    B->>R: GET liên kết có token
    R->>D: Kiểm tra token và phạm vi
    D-->>R: Trạng thái hiện tại
    R-->>B: Tạo reset context, chuyển sang URL form sạch
    U->>B: Nhập và xác nhận mật khẩu mới
    B->>R: POST form cùng context và CSRF token
    R->>D: Kiểm tra lại quyền, cập nhật và tiêu thụ nguyên tử
    D-->>R: Commit thành công
    R-->>B: Chuyển đến kết quả
    U->>B: Đăng nhập qua luồng bình thường
~~~

### 3.1. Mở liên kết chưa được đổi mật khẩu

Email có thể được hệ thống quét liên kết truy cập trước người dùng. Trình duyệt cũng có thể tải trước hoặc mở lại trang.

Vì vậy, GET hoặc HEAD không được đổi mật khẩu, tắt MFA hay đánh dấu quyền đặt lại đã được tiêu thụ thành công. Có thể kiểm tra và tạo trạng thái tạm để hiển thị form, nhưng việc sử dụng quyền phải gắn với thao tác xác nhận hợp lệ.

Thiết kế này phù hợp với ý nghĩa phương thức an toàn trong HTTP; xem [RFC 9110, mục 9.2.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1).

### 3.2. Không giữ token trong URL form

Một luồng minh họa:

~~~text
GET  /account/password-reset/start?token=<reset-token>
     -> kiểm tra token
     -> tạo reset context mới, không dùng lại định danh do client chọn
     -> chuyển tới /account/password-reset/form

POST /account/password-reset/complete
     -> gửi mật khẩu, xác nhận và CSRF token
     -> cookie tham chiếu reset context
     -> không cần gửi email hoặc accountId để chọn tài khoản
~~~

Reset context tham chiếu đến quyền gốc; nó không kéo dài thời hạn của quyền đó. Nếu token chỉ còn hiệu lực một phút, tạo context mới không được biến thời hạn thành mười phút.

Chuyển tới URL sạch giúp giảm khả năng token tiếp tục xuất hiện trong các liên kết và tài nguyên sau đó. Nó không xóa bản sao đã có ở email, lịch sử hay log của request đầu tiên. Cần cấu hình che dữ liệu ngay tại proxy, ứng dụng và tracing.

### 3.3. Context chỉ có quyền hẹp

Một context hợp lệ có thể liên kết với:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Tài khoản và tenant | Xác định chủ thể duy nhất |
| Quyền khôi phục gốc | Kiểm tra trạng thái thực tế khi gửi form |
| Mục đích PASSWORD_RESET | Không dùng cho đổi email, MFA hoặc passkey |
| Thời hạn | Không cho sử dụng sau thời điểm hết hiệu lực |
| CSRF token | Liên kết request với form và context tương ứng |
| Trạng thái hoàn tất | Ngăn context tiếp tục ghi sau khi thành công |

Cookie của context không được hệ thống xác thực coi là cookie đăng nhập. Sau khi hoàn tất, phải chấm dứt quyền ghi của context; nếu giữ biên nhận chỉ đọc để xử lý lỗi mạng, biên nhận đó không được mở lại quyền đặt mật khẩu.

## 4. Trạng thái giao diện cần được thiết kế trước

| Trạng thái | Nội dung người dùng thấy | Hành vi của form |
| --- | --- | --- |
| Đang kiểm tra | Đang kiểm tra liên kết | Chưa cho gửi |
| Có thể đặt lại | Hai ô mật khẩu và hướng dẫn | Cho nhập và gửi |
| Dữ liệu chưa hợp lệ | Lỗi cụ thể tại trường cần sửa | Không tiêu thụ quyền chỉ vì lỗi nhập |
| Đang gửi | Đang cập nhật mật khẩu | Hạn chế gửi lặp tại giao diện |
| Liên kết không dùng được | Hướng dẫn yêu cầu liên kết mới | Không cho tiếp tục cập nhật |
| Chưa xác định kết quả | Hướng dẫn kiểm tra trạng thái hoặc thử lại có kiểm soát | Không tự tuyên bố thành công hoặc thất bại |
| Thành công | Mật khẩu đã được đặt lại, nút đến đăng nhập | Không hiển thị lại mật khẩu |

Ví dụ thông báo:

- “Hai mật khẩu chưa trùng nhau. Hãy kiểm tra lại.”
- “Mật khẩu này quá phổ biến hoặc đã xuất hiện trong dữ liệu rò rỉ. Hãy chọn mật khẩu khác.”
- “Liên kết này không còn sử dụng được. Bạn có thể yêu cầu liên kết mới.”
- “Chưa nhận được kết quả cập nhật. Hãy kiểm tra trạng thái trước khi gửi lại.”

Không dùng một thông báo “Có lỗi” cho mọi tình huống. Người dùng cần phân biệt lỗi có thể sửa trong form với trường hợp phải bắt đầu yêu cầu khôi phục mới.

Cũng không cần công khai chi tiết như token có tồn tại trong cơ sở dữ liệu hay đã bị thu hồi bởi thao tác nào. Các trạng thái không hợp lệ có thể được gom vào cùng thông báo phù hợp với người dùng.

## 5. Thành phần của một form rõ ràng

Một form cơ bản gồm:

| Thành phần | Mục đích |
| --- | --- |
| Tiêu đề “Đặt mật khẩu mới” | Xác định đây là bước tạo bí mật đăng nhập mới |
| Hướng dẫn chính sách | Cho biết yêu cầu trước khi người dùng nhập |
| Ô mật khẩu mới | Nhận mật khẩu sẽ được lưu |
| Ô xác nhận | Giảm lỗi nhập và nhầm giá trị |
| Điều khiển hiện mật khẩu | Cho người dùng tự kiểm tra tại nơi phù hợp |
| Vùng lỗi tại từng trường | Chỉ rõ cần sửa gì |
| Nút “Đặt lại mật khẩu” | Xác nhận một hành động cụ thể |
| Liên kết yêu cầu khôi phục mới | Hướng xử lý khi context hết hạn |

Không thêm câu hỏi bảo mật, ngày sinh hay địa chỉ cũ vào form để tự động cho phép đi tiếp khi token không hợp lệ. Những dữ kiện đó không thay thế quyền đặt lại đã được chính sách yêu cầu.

Nếu cần hiển thị tài khoản đích để tránh nhầm lẫn, chỉ hiển thị thông tin phù hợp với mức xác minh hiện tại, chẳng hạn định danh đã che một phần. Việc hiển thị phải lấy từ máy chủ; không lấy nhãn tài khoản từ query string.

### Hỗ trợ trình quản lý mật khẩu

Cả ô mật khẩu mới và ô xác nhận nên khai báo autocomplete="new-password". Không dùng current-password cho một mật khẩu sắp tạo mới. Chuẩn HTML định nghĩa new-password cho trường hợp tạo hoặc thay mật khẩu; xem [HTML Standard: autofill](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill).

Cho phép dán vào cả hai ô và hỗ trợ mật khẩu do trình quản lý tạo. Chặn clipboard không chứng minh người dùng ghi nhớ tốt hơn; nó có thể khiến họ chọn mật khẩu ngắn hoặc dễ gõ hơn.

Không tự động ghi giá trị đang nhập vào localStorage, sessionStorage, URL hoặc công cụ ghi lại phiên sử dụng. Việc trình quản lý mật khẩu của người dùng hoạt động là chức năng khác với việc ứng dụng tự lưu bản nháp mật khẩu.

## 6. Chính sách mật khẩu phải đến từ máy chủ

Form đặt lại cần dùng cùng hợp đồng mật khẩu với các luồng tạo, đổi và đăng nhập tương ứng. Không để nhánh khôi phục trở thành nơi có chính sách yếu hơn hoặc biến đổi chuỗi khác đi.

NIST SP 800-63B-4 yêu cầu tối thiểu 15 ký tự khi mật khẩu dùng như yếu tố duy nhất; nếu chỉ dùng trong MFA, có thể cho phép ngắn hơn nhưng tối thiểu tám ký tự. Tài liệu khuyến nghị hỗ trợ độ dài tối đa ít nhất 64 ký tự và không áp đặt quy tắc pha trộn loại ký tự. Xem [NIST, mục 3.1.1.2](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver).

Ví dụ của bài chọn chính sách sản phẩm **15 đến 128 Unicode code point**, kiểm tra giá trị phổ biến hoặc bị lộ và hỗ trợ passphrase. Mốc 128 là lựa chọn minh họa, không phải yêu cầu chung của NIST.

Cần phân biệt:

| Quy tắc | Vai trò |
| --- | --- |
| Độ dài tối thiểu và tối đa | Xác định miền đầu vào được hỗ trợ |
| Danh sách giá trị bị chặn | Loại mật khẩu phổ biến, dễ đoán hoặc đã bị lộ theo chính sách |
| Thanh đánh giá độ mạnh | Hướng dẫn người dùng, không quyết định thay máy chủ |
| Giới hạn kích thước request | Kiểm soát tài nguyên trước khi xử lý sâu |
| Quy tắc Unicode và mã hóa | Bảo đảm đăng ký, đặt lại và đăng nhập dùng cùng giá trị |
| Kiểm tra xác nhận | Phát hiện hai ô không biểu diễn cùng mật khẩu theo hợp đồng |

OWASP cũng nêu các kiểm soát độ mạnh, hỗ trợ mật khẩu dài và chặn mật khẩu bị lộ trong [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#implement-proper-password-strength-controls).

### Không tự sửa mật khẩu

Không tự trim khoảng trắng, chuyển chữ thường, bỏ dấu hoặc cắt ngắn để đạt giới hạn. Người dùng có thể chủ ý dùng các giá trị đó.

Nếu hợp đồng mật khẩu sử dụng chuẩn hóa NFC, phải áp dụng nhất quán khi đặt lại và đăng nhập. Việc so sánh hai ô cũng cần theo cùng quy tắc đã công bố; không chuẩn hóa một ô nhưng giữ nguyên ô còn lại.

Giới hạn giao diện không thay thế kiểm tra máy chủ. Đặc biệt, không mặc định độ dài chuỗi của trình duyệt, số Unicode code point và số byte UTF-8 luôn giống nhau.

### Không đưa mật khẩu ra dịch vụ phân tích

Không gửi mật khẩu từng gõ tới hệ thống analytics hoặc endpoint kiểm tra độ mạnh không được thiết kế để xử lý bí mật.

Nếu kiểm tra giá trị đã bị lộ bằng dịch vụ ngoài, phải có thiết kế bảo vệ dữ liệu riêng; không gửi mật khẩu nguyên văn cho một dịch vụ bất kỳ. Hành vi kiểm tra cũng không được đưa bí mật vào query string.

## 7. Ví dụ HTML có hỗ trợ khả năng tiếp cận

Đây là mẫu cấu trúc cho trạng thái form hợp lệ. Giá trị {{csrfToken}} là chỗ giữ chỗ để template phía máy chủ render bằng cơ chế mã hóa thuộc tính phù hợp; nó không phải giá trị cố định để dùng thật.

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Đặt mật khẩu mới</title>
  <script src="/assets/password-reset.js" defer></script>
</head>
<body>
  <main>
    <h1>Đặt mật khẩu mới</h1>

    <p id="password-policy">
      Dùng từ 15 đến 128 ký tự theo chính sách của hệ thống.
      Bạn có thể dùng cụm từ dài hoặc mật khẩu do
      trình quản lý mật khẩu tạo.
    </p>

    <div id="error-summary" role="alert" tabindex="-1" hidden>
      <p>Chưa thể đặt lại mật khẩu. Hãy kiểm tra các mục được báo lỗi.</p>
      <ul>
        <!-- Máy chủ render liên kết tới trường có lỗi. -->
      </ul>
    </div>

    <form method="post"
          action="/account/password-reset/complete"
          accept-charset="UTF-8">
      <input type="hidden"
             name="_csrf"
             value="{{csrfToken}}">

      <div>
        <label for="new-password">Mật khẩu mới</label>
        <input id="new-password"
               name="newPassword"
               type="password"
               autocomplete="new-password"
               autocapitalize="none"
               spellcheck="false"
               aria-describedby="password-policy new-password-error"
               required>
        <p id="new-password-error"></p>
      </div>

      <div>
        <label for="confirm-password">Nhập lại mật khẩu mới</label>
        <input id="confirm-password"
               name="confirmPassword"
               type="password"
               autocomplete="new-password"
               autocapitalize="none"
               spellcheck="false"
               aria-describedby="confirm-password-error"
               required>
        <p id="confirm-password-error"></p>
      </div>

      <button id="toggle-passwords"
              type="button"
              aria-controls="new-password confirm-password"
              aria-pressed="false">
        Hiện mật khẩu
      </button>

      <button type="submit">Đặt lại mật khẩu</button>
    </form>

    <p>
      Liên kết không còn sử dụng được?
      <a href="/account/recovery">Yêu cầu hướng dẫn khôi phục mới</a>
    </p>
  </main>
</body>
</html>
~~~

Chính sách hiển thị trong ví dụ phải được render từ cùng cấu hình mà máy chủ dùng để kiểm tra, không sao chép con số sang nhiều nơi rồi cập nhật thủ công.

Mẫu không thêm minlength hoặc maxlength cố định để tránh biến cách đếm của trình duyệt thành nguồn quyết định. Có thể bổ sung kiểm tra sớm nếu cách đếm và chính sách được đồng bộ; máy chủ vẫn phải kiểm tra độc lập.

Khi render lỗi:

- Bỏ hidden khỏi vùng tổng hợp và đưa tiêu điểm tới đó khi phù hợp.
- Liên kết từng lỗi đến trường cần sửa.
- Đặt aria-invalid="true" cho trường tương ứng.
- Mô tả lỗi bằng chữ, không chỉ đổi màu viền.
- Không render lại mật khẩu người dùng vừa gửi vào thuộc tính value.

WCAG yêu cầu nhận diện mục nhập có lỗi và mô tả lỗi bằng văn bản khi hệ thống tự phát hiện. Xem [W3C: Error Identification](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html).

### Điều khiển hiện mật khẩu

Đoạn JavaScript minh họa cho script cùng origin được tham chiếu ở trên:

~~~javascript
const toggle = document.getElementById("toggle-passwords");
const fields = [
  document.getElementById("new-password"),
  document.getElementById("confirm-password")
];

toggle.addEventListener("click", () => {
  const reveal = toggle.getAttribute("aria-pressed") !== "true";

  for (const field of fields) {
    field.type = reveal ? "text" : "password";
  }

  toggle.setAttribute("aria-pressed", String(reveal));
});
~~~

Nhãn nút được giữ ổn định; trạng thái nhấn biểu thị chế độ hiện mật khẩu. Không gửi nội dung hai ô khi chuyển trạng thái này.

Nếu JavaScript không chạy, form vẫn gửi bằng POST và máy chủ vẫn xử lý được. Tính năng hiện mật khẩu là hỗ trợ nhập liệu, không phải điều kiện để hoàn tất thao tác.

## 8. Bảo vệ request gửi form

### 8.1. Kiểm tra phía client phục vụ trải nghiệm

Client có thể phát hiện ô trống, hai ô khác nhau hoặc đầu vào chưa đạt một số yêu cầu. Tuy nhiên, người gửi có thể bỏ qua JavaScript và gửi request trực tiếp.

Backend vẫn phải kiểm tra:

1. Request có cấu trúc, mã hóa và kích thước được hỗ trợ.
2. Reset context còn hợp lệ và có đúng mục đích.
3. CSRF token hoặc cơ chế bảo vệ tương ứng hợp lệ.
4. Ngân sách thao tác chưa bị vượt.
5. Hai mật khẩu khớp theo hợp đồng.
6. Mật khẩu đạt chính sách hiện tại.
7. Quyền khôi phục vẫn chưa dùng, chưa hết hạn và chưa bị thu hồi.
8. Tài khoản vẫn đủ điều kiện cho thao tác này.

Không dùng các cờ client gửi như tokenVerified=true, passwordStrong=true hoặc mfaRecovered=true làm bằng chứng.

### 8.2. CSRF vẫn quan trọng khi form chưa có session đăng nhập

Trong thiết kế này, trình duyệt tự gửi cookie reset context. Cookie đó mang quyền hạn hẹp nhưng vẫn liên quan đến một thao tác nhạy cảm.

Cần dùng cơ chế CSRF của framework khi có, hoặc triển khai mẫu phù hợp như synchronizer token. Token trong hidden field phải gắn với context và được kiểm tra ở backend. SameSite và kiểm tra Origin là các lớp bổ sung theo thiết kế; không mặc định có cookie SameSite là đủ cho mọi trường hợp. Xem [OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Nếu trình duyệt mở liên kết khác làm context thay đổi, CSRF token của form cũ phải bị từ chối khi không còn khớp. Không ghép mật khẩu từ form cũ với tài khoản của context mới.

CSRF không giải quyết việc token khôi phục đã bị đánh cắp. Người giữ bearer token có thể tự mở một context mới; đó là lý do token, luồng xác minh và đường truyền vẫn phải được bảo vệ.

### 8.3. Hạn chế lạm dụng trước bước băm tốn tài nguyên

Các bước rẻ như kiểm tra cấu trúc, context, CSRF và giới hạn tốc độ cần diễn ra trước thao tác băm mật khẩu tốn chi phí.

Giới hạn nên phối hợp theo context, quyền khôi phục, tài khoản, nguồn gửi và toàn dịch vụ. Không chỉ giới hạn theo IP hoặc chỉ theo một cookie có thể tạo lại.

Sai chính sách mật khẩu không cần tự tiêu thụ quyền đặt lại. Người dùng có thể sửa lỗi trong thời hạn còn lại. Tuy nhiên, phải giới hạn các lần thử để tránh lạm dụng; không kéo dài thời hạn vì người dùng tiếp tục nhập.

Các request chưa được xác minh cũng không được tự khóa mọi phương thức đăng nhập hợp lệ của tài khoản.

## 9. Cập nhật mật khẩu và tiêu thụ quyền phải thống nhất

Lỗi thường gặp là kiểm tra token, cập nhật mật khẩu và đánh dấu token đã dùng bằng ba thao tác độc lập.

~~~text
Request A: thấy token chưa dùng
Request B: thấy token chưa dùng
Request A: ghi mật khẩu X
Request B: ghi mật khẩu Y
Request A/B: đánh dấu đã dùng
~~~

Cả hai request có thể được báo thành công trong khi chỉ mật khẩu ghi cuối cùng còn hiệu lực.

Thiết kế cần bảo đảm cập nhật mật khẩu và tiêu thụ quyền có hiệu lực cùng nhau. Có thể dùng transaction với khóa hoặc cập nhật có điều kiện tùy kho dữ liệu. Việc vô hiệu các quyền đặt lại khác của cùng tài khoản cũng phải được xét trong cùng chính sách.

### Mã giả theo cú pháp Java

Ví dụ sau giả định tài khoản, grant, context và outbox có thể phối hợp trong cùng transaction. Các API là mô tả trách nhiệm, không phải lớp thư viện có sẵn.

~~~java
ResetResult completeReset(ResetRequest request, HttpRequest http) {
    ResetContext context = contexts.requireFromCookie(http);

    csrf.requireValid(context, request.csrfToken(), http);
    limits.requireAllowed(context, http);

    // Biên nhận chỉ đọc không mở lại quyền ghi.
    if (context.hasCompletionReceipt()) {
        return context.completedResult();
    }

    ResetSnapshot snapshot = recovery.requirePasswordReset(context);

    PasswordCandidate candidate = passwordPolicy.requireAcceptable(
            request.newPassword(),
            request.confirmPassword(),
            snapshot.passwordPolicyId());

    // Băm trước để tránh giữ khóa DB trong suốt bước tốn chi phí.
    EncodedPassword encoded = passwordHasher.hash(candidate);

    return transaction.run(() -> {
        Account account = accounts.lock(snapshot.accountId());
        ResetGrant grant = grants.lock(snapshot.grantId());

        // Kiểm tra lại bằng trạng thái và thời gian có thẩm quyền.
        recovery.requireStillAllowed(
                context, grant, account,
                database.currentTime(),
                snapshot.passwordPolicyId());

        account.replacePassword(encoded);
        account.incrementCredentialVersion();

        grant.consume();
        grants.invalidateOtherPasswordResetGrants(account.id());

        ResetResult result = context.completeWithReadOnlyReceipt();

        // Không chứa mật khẩu, token hay hash mật khẩu.
        outbox.appendPasswordResetCompleted(account.id());

        return result;
    });
}
~~~

Lần kiểm tra trong transaction cần bao gồm tài khoản, tenant, mục đích, thời hạn, trạng thái chưa tiêu thụ, trạng thái tài khoản và các điều kiện chính sách liên quan. Không coi snapshot trước bước băm là dữ liệu còn đúng mãi.

Nếu quyền hết hạn trong lúc người dùng nhập hoặc trong lúc băm, thao tác ghi phải bị từ chối theo chính sách. Không gia hạn tự động chỉ vì form được mở trước đó.

Nếu transaction thất bại, không được để mật khẩu đã thay nhưng grant vẫn dùng lại được, hoặc grant đã mất trong khi mật khẩu chưa đổi.

Mật khẩu mới phải được lưu bằng cơ chế băm mật khẩu có salt và tham số phù hợp, qua thư viện được duy trì; không dùng hash nhanh đơn thuần hoặc mã hóa có thể giải ngược làm phương án lưu thông thường. Xem [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## 10. Gửi lặp, nhiều tab và lỗi mạng

### Nhấn nút hai lần

Có thể vô hiệu nút gửi khi đang xử lý để giảm nhầm lẫn, đồng thời thông báo trạng thái cho công nghệ hỗ trợ. Đây chỉ là cải thiện giao diện.

Backend vẫn phải bảo đảm một quyền chỉ tạo ra một thay đổi. Request đến sau có thể nhận lại biên nhận của cùng thao tác hoặc bị từ chối vì quyền không còn hiệu lực; nó không được ghi mật khẩu thêm lần nữa.

### Mở hai tab với cùng liên kết

Nếu cả hai tab có thể hiển thị form, lần gửi hợp lệ đầu tiên sẽ tiêu thụ quyền. Tab còn lại phải kiểm tra lại trạng thái khi gửi.

Không tự cấp token mới hoặc mở lại grant để “giúp tab thứ hai hoạt động”. Nếu tab thứ hai đang nhập mật khẩu khác, nó không được ghi đè kết quả đã commit.

### Mở liên kết của tài khoản khác trong cùng trình duyệt

Cookie dùng chung có thể làm context hiện tại thay đổi. Form cũ phải bị từ chối nếu binding không còn phù hợp.

Muốn hỗ trợ nhiều luồng đồng thời cần thiết kế định danh luồng và binding riêng. Một hidden field chứa accountId không giải quyết được vấn đề vì client có thể sửa trường đó.

### Timeout sau khi máy chủ đã commit

Không nhận được response không có nghĩa cập nhật thất bại. Request có thể đã commit nhưng kết nối bị ngắt trước khi trang nhận kết quả.

Một phương án là cung cấp endpoint trạng thái chỉ đọc, gắn với context hoặc biên nhận:

~~~text
GET /account/password-reset/status
    -> nhận trạng thái của chính thao tác trong context đó
    -> không gửi lại mật khẩu
    -> không kéo dài quyền
    -> không cung cấp cách tra cứu trạng thái tài khoản tùy ý
~~~

Nếu không xác định được trạng thái, hướng dẫn người dùng đăng nhập qua luồng bình thường hoặc yêu cầu hướng dẫn khôi phục mới. Không tự động gửi lại mật khẩu đã cất vào bộ nhớ lâu dài.

Sau POST thành công có thể dùng redirect 303 tới trang kết quả để giảm việc trình duyệt gửi lại body khi tải lại. Redirect không thay thế transaction và chống phát lại phía máy chủ.

## 11. HTTP, cookie và tránh rò rỉ bí mật

Trang nhận token, trang form, phản hồi lỗi và trang kết quả cần có chính sách bảo vệ dữ liệu phù hợp.

Ví dụ header cho ứng dụng minh họa:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'
~~~

Chính sách CSP phải tương thích với tài nguyên thực tế và được kiểm tra khi triển khai. Không thêm nguồn bên thứ ba rộng rãi chỉ để một tiện ích phân tích tiếp tục chạy trên trang đặt mật khẩu.

Các header trên hỗ trợ hạn chế lưu cache, rò referrer, nhúng trang và nguồn tải tài nguyên; chúng không thay thế kiểm soát XSS hay che dữ liệu trong log. Xem [OWASP HTTP Headers](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html).

Cookie tham chiếu context có thể dùng cấu trúc minh họa:

~~~http
Set-Cookie: __Host-reset_ctx=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=600
~~~

Tên có tiền tố __Host- đòi hỏi Secure, Path=/ và không có Domain. Dù cookie được gửi tới nhiều đường dẫn cùng host, máy chủ chỉ chấp nhận nó trong chức năng khôi phục tương ứng, không dùng để đăng nhập. Giá trị 600 giây là ví dụ; thời hạn thực tế vẫn phải bị chặn bởi thời hạn quyền gốc.

Cần bảo đảm thêm:

- Chỉ phục vụ qua HTTPS và tạo redirect trên origin tin cậy.
- Không lấy đích gửi form hoặc đích redirect từ tham số tùy ý.
- Không lưu body chứa mật khẩu trong access log, APM, tracing hoặc báo cáo lỗi.
- Không ghi token trong log request đầu tiên, kể cả ở proxy.
- Không nhúng công cụ ghi lại thao tác hoặc script quảng cáo vào trang này.
- Không gửi mật khẩu qua GET, query string hoặc fragment.
- Không đưa mật khẩu mới vào email thông báo hoặc trang kết quả.

Cache-Control: no-store không phải lệnh xóa mọi lịch sử hoặc bản sao do người dùng hay phần mềm khác đã tạo. Cần thiết kế toàn bộ đường đi của bí mật, thay vì chỉ thêm một header ở trang form.

## 12. Hợp đồng lỗi giữa giao diện và máy chủ

Một hợp đồng minh họa cho form đã có context:

| Kết quả | HTTP gợi ý | Mã ứng dụng | Cách xử lý |
| --- | --- | --- | --- |
| Mật khẩu hoặc xác nhận chưa hợp lệ | 422 | PASSWORD_INPUT_INVALID | Hiển thị lỗi trường để sửa |
| Context không còn dùng được | 400 | RESET_CONTEXT_INVALID | Ngừng gửi, hướng dẫn yêu cầu mới |
| CSRF không hợp lệ | 403 | REQUEST_NOT_ALLOWED | Không cập nhật; hướng dẫn mở lại luồng |
| Vượt ngân sách thử | 429 | RESET_RATE_LIMITED | Thông báo thời gian chờ thích hợp |
| Lỗi tạm thời trước khi xác định kết quả | 503 | RESET_TEMPORARILY_UNAVAILABLE | Không khẳng định thành công, hỗ trợ kiểm tra trạng thái |
| Hoàn tất bền vững | 303 | Chuyển trang kết quả | Hiển thị thành công, liên kết đăng nhập |

Các mã HTTP là một lựa chọn thiết kế, không phải bộ mã bắt buộc cho mọi hệ thống. Quan trọng là client không phải đoán trạng thái từ nội dung lỗi tự do.

Ví dụ phản hồi lỗi sau khi đã xác thực context:

~~~json
{
  "code": "PASSWORD_INPUT_INVALID",
  "fieldErrors": {
    "confirmPassword": "Hai mật khẩu chưa trùng nhau."
  }
}
~~~

Không trả lại giá trị mật khẩu trong JSON. Không kèm token, hash, email đầy đủ hoặc chi tiết kho dữ liệu.

Trước khi context hợp lệ, không cung cấp lỗi trường riêng có thể giúp phân biệt tài khoản hay nhánh khôi phục. Việc yêu cầu liên kết mới ở bước trước vẫn cần phản hồi phù hợp để chống dò tài khoản.

Nếu chính sách thay đổi trong lúc form đang mở, máy chủ phải áp dụng quy tắc có thẩm quyền và trả hướng dẫn cập nhật. Không chấp nhận chính sách cũ chỉ vì client gửi passwordPolicyId cũ.

## 13. Màn hình thành công và kiểm soát session

Màn hình thành công chỉ được hiển thị dựa trên kết quả commit hoặc biên nhận đáng tin cậy. Không dùng một query string như success=true làm bằng chứng rằng mật khẩu đã thay đổi.

Nội dung có thể gồm:

~~~text
Mật khẩu đã được đặt lại.

Hãy đăng nhập bằng mật khẩu mới.
Nếu tài khoản có MFA, bạn vẫn cần hoàn tất bước xác thực đó.

[Đến trang đăng nhập]
~~~

Không tự đăng nhập bằng reset context. Khi người dùng đăng nhập sau đó, hệ thống tạo session mới qua cơ chế thông thường, không nâng cấp nguyên trạng cookie khôi phục thành session xác thực.

### Session cũ không tự biến mất khi đổi hash

Đổi hash mật khẩu không làm mọi session hoặc refresh token đang tồn tại tự hết hiệu lực. Cần chính sách rõ ràng về thu hồi sau đặt lại.

Trong ví dụ, tăng credentialVersion trong transaction giúp ghi nhận mốc thay đổi. Cơ chế này chỉ có tác dụng nếu các thành phần xác thực thật sự kiểm tra và thực thi phiên bản. Nếu cache hoặc access token tự chứa còn được chấp nhận, cần thiết kế cơ chế thu hồi hay giới hạn thời gian tương ứng.

Không hiển thị “mọi thiết bị đã đăng xuất ngay” nếu hệ thống chỉ mới phát một sự kiện bất đồng bộ mà chưa bảo đảm hiệu lực đó.

Với khôi phục sau nghi ngờ chiếm đoạt, còn cần xem xét quyền đặt lại cũ, thay đổi trái phép ở kênh khôi phục và phương thức xác thực. Form đặt mật khẩu không được tự xử lý tất cả bằng cách tắt MFA hoặc khôi phục một số điện thoại đã bị thay thế trước đây.

### Thông báo sau thay đổi

Gửi thông báo qua kênh đã đăng ký phù hợp, kèm cách báo cáo nếu người dùng không thực hiện thao tác. Nội dung không chứa mật khẩu hoặc token có thể tiếp tục đặt lại.

Nếu gửi thông báo gặp lỗi sau khi transaction đã commit, không thông báo rằng mật khẩu chưa đổi. Có thể dùng outbox để gửi lại sự kiện một cách kiểm soát; lỗi hệ thống thông báo là vấn đề vận hành riêng với kết quả cập nhật mật khẩu.

## 14. Ví dụ xuyên suốt

Minh quên mật khẩu nhưng vẫn giữ phương thức MFA. Anh mở liên kết khôi phục trên điện thoại, nhập mật khẩu do trình quản lý tạo và dán vào ô xác nhận.

Luồng đúng diễn ra như sau:

1. GET kiểm tra liên kết và mở form, chưa thay mật khẩu hay tiêu thụ quyền.
2. Form hỗ trợ dán, hiển thị chính sách và cho Minh tự bật hiện mật khẩu.
3. Lần gửi đầu bị từ chối vì hai ô không khớp; quyền chưa bị tiêu thụ chỉ vì lỗi này.
4. Minh sửa lại rồi gửi. Backend kiểm tra context, CSRF, chính sách và giới hạn thao tác.
5. Một transaction ghi mật khẩu mới, tiêu thụ quyền, xử lý các quyền đặt lại khác và ghi sự kiện hoàn tất.
6. Kết nối bị ngắt trước khi điện thoại nhận response.
7. Trang kiểm tra trạng thái bằng context chỉ đọc và xác nhận thao tác đã hoàn tất; không đặt lại thêm lần nữa.
8. Minh đến trang đăng nhập, nhập mật khẩu mới và vẫn hoàn tất MFA.

Nếu Minh đồng thời mất thiết bị MFA, màn hình phải đưa anh tới quy trình khôi phục phương thức xác thực phù hợp. Không thêm checkbox “Bỏ MFA vì tôi đã đặt lại mật khẩu” vào form.

Nếu email của Minh có dấu hiệu bị chiếm đoạt, chỉ việc mở được liên kết trong email chưa chắc đáp ứng chính sách khôi phục cho tài khoản đó. Hệ thống có thể phải yêu cầu bằng chứng bổ sung trước khi cho phép thao tác đặt mật khẩu.

## 15. Các tình huống cần kiểm chứng khi triển khai

Bảng dưới là yêu cầu kiểm chứng cho thiết kế, không phải kết quả kiểm thử đã chạy.

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Hệ thống quét email truy cập GET hoặc HEAD | Không đổi mật khẩu, không tiêu thụ quyền |
| Người dùng gửi trực tiếp, bỏ qua JavaScript | Backend vẫn kiểm tra đầy đủ |
| Hai ô mật khẩu khác nhau | Không cập nhật, chỉ rõ lỗi cần sửa |
| Mật khẩu không đạt chính sách | Cho sửa trong thời hạn còn lại, không tự gia hạn quyền |
| Người dùng dán mật khẩu từ trình quản lý | Không bị chặn chỉ vì thao tác dán |
| Người dùng dùng bàn phím hoặc trình đọc màn hình | Đọc được nhãn, trạng thái và lỗi; tới được trường cần sửa |
| Token hết hạn sau khi form đã mở | Lần gửi bị từ chối trước khi ghi |
| Sửa email hoặc accountId trong request | Không đổi tài khoản đích của quyền khôi phục |
| Thiếu hoặc sai CSRF token | Không cập nhật |
| Có quyền đổi email nhưng gọi endpoint đặt mật khẩu | Bị từ chối vì sai mục đích |
| Hai request cùng tiêu thụ một quyền | Chỉ một thay đổi có hiệu lực |
| Hai tab gửi hai mật khẩu khác nhau | Tab đến sau không ghi đè kết quả đã hoàn tất |
| Context đổi sang tài khoản khác | Form cũ không cập nhật tài khoản mới |
| Timeout sau commit | Có cách nhận biết kết quả mà không đặt lại lần nữa |
| Transaction thất bại giữa chừng | Không có trạng thái nửa cập nhật, nửa tiêu thụ |
| Email thông báo gửi thất bại | Không đổi kết luận về transaction đã thành công |
| Đặt lại thành công khi tài khoản còn MFA | MFA tiếp tục được yêu cầu khi đăng nhập |
| Kiểm tra proxy log, APM và báo cáo lỗi | Không có mật khẩu, reset token hoặc CSRF token |
| Dùng Back, reload hoặc gửi lại request cũ | Không khôi phục quyền ghi đã tiêu thụ |
| Dùng session cũ sau mốc thu hồi | Bị xử lý đúng chính sách thực thi đã công bố |

Form đặt lại mật khẩu hoàn chỉnh cần nối được trải nghiệm nhập liệu với một giao dịch thay đổi thông tin xác thực có quyền hạn rõ ràng. Hai ô mật khẩu và nút gửi chỉ là phần nhìn thấy; tính an toàn phụ thuộc vào binding của quyền khôi phục, kiểm tra khi ghi, tiêu thụ một lần và việc thực thi chính sách session sau đó.
