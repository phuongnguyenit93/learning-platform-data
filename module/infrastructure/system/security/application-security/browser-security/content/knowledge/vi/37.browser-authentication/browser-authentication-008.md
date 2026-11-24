# Authentication UI — giao diện xác thực giữa website và browser

> **Chương:** Authentication browser  
> **Mục tiêu:** Phân biệt giao diện đăng nhập do ứng dụng xây dựng với giao diện xác thực do browser/hệ điều hành quản lý; hiểu cách password manager, autofill, HTTP authentication, passkey/WebAuthn và FedCM hiển thị lựa chọn cho người dùng; thiết kế form tương thích với browser; giảm phishing, clickjacking và UI redressing; kiểm thử luồng xác thực trên browser thực tế.

## 1. Authentication UI là gì?

Authentication UI là phần giao diện người dùng tương tác với một cơ chế xác thực. Trong ứng dụng web, trải nghiệm này có thể gồm nhiều giao diện khác nhau:

- Form đăng nhập do website xây dựng.
- Gợi ý autofill và lưu mật khẩu do password manager của browser cung cấp.
- Hộp thoại xác thực HTTP do browser hiển thị sau response challenge.
- Bộ chọn passkey hoặc xác nhận bằng authenticator do browser/hệ điều hành điều phối.
- Account chooser hoặc consent UI của FedCM trong luồng đăng nhập bằng identity provider.
- Giao diện nhập mã OTP, xác nhận thiết bị hoặc khôi phục tài khoản do ứng dụng xây dựng.

Các giao diện này có ranh giới tin cậy khác nhau. Website kiểm soát form HTML và nội dung trang. Browser kiểm soát thanh địa chỉ, một số popup credential, password manager và quá trình WebAuthn. Hệ điều hành hoặc authenticator có thể hiển thị bước xác nhận sinh trắc học/PIN.

Một ứng dụng an toàn cần làm rõ phần nào là giao diện của website và phần nào là giao diện do browser/OS cung cấp. Không giả lập giao diện browser để khiến người dùng tưởng một trang web là hộp thoại đáng tin cậy của hệ thống.

## 2. Ba lớp giao diện trong một lần đăng nhập

Một luồng xác thực thường có ba lớp:

| Lớp | Ai kiểm soát? | Ví dụ |
| --- | --- | --- |
| Application UI | Website/app | Form username/password, nút đăng nhập, thông báo lỗi, trang MFA |
| Browser-mediated UI | Browser | Password autofill, lưu mật khẩu, chọn passkey, HTTP auth dialog, FedCM |
| Platform authenticator UI | OS hoặc thiết bị xác thực | Face/fingerprint, PIN thiết bị, security key confirmation |

Ví dụ với passkey:

1. Website hiển thị nút “Đăng nhập bằng passkey” hoặc ô username có hỗ trợ conditional mediation.
2. Website yêu cầu backend tạo challenge.
3. Browser tìm credential phù hợp với relying party.
4. Browser/OS hiển thị giao diện chọn passkey và xác minh người dùng.
5. Authenticator ký dữ liệu xác thực.
6. Website gửi assertion về backend để xác minh.

Website không nhận dữ liệu sinh trắc học thô. Nó nhận kết quả mật mã và các thông tin xác thực cần thiết để server kiểm tra.

## 3. Ranh giới tin cậy của giao diện

Người dùng cần nhận biết họ đang tương tác với website nào và loại hành động nào đang được yêu cầu.

Các nguyên tắc:

- Thanh địa chỉ và origin indicator thuộc quyền kiểm soát của browser.
- Website không thể đọc hoặc thay đổi nội dung thanh địa chỉ bằng JavaScript.
- Browser UI và OS prompt có thể khác nhau theo hệ điều hành, browser, phiên bản và thiết bị.
- Website không được giả vờ rằng một modal HTML là hộp thoại bảo mật của browser.
- Password manager hoặc passkey picker chỉ nên được kích hoạt qua flow API/HTML được hỗ trợ.
- Server phải xác minh credential; giao diện đẹp hoặc trạng thái “đã xác thực” ở client không phải bằng chứng.

Không đặt icon ổ khóa giả cạnh form rồi dùng nó để tuyên bố kết nối an toàn. HTTPS và trạng thái certificate do browser thể hiện; website chỉ nên giải thích rõ rằng kết nối được bảo vệ bằng HTTPS.

## 4. Form đăng nhập tương thích với password manager

Browser và password manager dựa vào cấu trúc HTML, label, name và autocomplete để nhận diện form đăng nhập.

Ví dụ form cơ bản:

```html
<form method="post" action="/login">
  <label for="username">Tên đăng nhập hoặc email</label>
  <input
    id="username"
    name="username"
    type="text"
    autocomplete="username"
    required
  >

  <label for="password">Mật khẩu</label>
  <input
    id="password"
    name="password"
    type="password"
    autocomplete="current-password"
    required
  >

  <button type="submit">Đăng nhập</button>
</form>
```

Những thuộc tính có ích:

- Label được liên kết đúng với input.
- Mỗi field có name ổn định để server nhận dữ liệu.
- Username dùng `autocomplete="username"`.
- Password đăng nhập dùng `autocomplete="current-password"`.
- Form dùng POST qua HTTPS và server xử lý xác thực.
- Không chặn paste hoặc autofill.

Không dựa vào việc ẩn field hoặc đổi tên input liên tục để ngăn password manager. Những thủ thuật này thường làm trải nghiệm kém và khuyến khích người dùng tạo mật khẩu yếu hoặc tự lưu ở nơi không an toàn.

## 5. Autocomplete token thường dùng

HTML định nghĩa các token autocomplete giúp browser hiểu mục đích field:

| Token | Mục đích |
| --- | --- |
| `username` | Tên tài khoản/email dùng đăng nhập |
| `current-password` | Mật khẩu hiện tại khi đăng nhập |
| `new-password` | Mật khẩu mới khi đăng ký/đổi mật khẩu |
| `one-time-code` | Mã xác minh dùng một lần |
| `webauthn` | Gợi ý credential WebAuthn/passkey trong flow hỗ trợ |

Ví dụ đổi mật khẩu:

```html
<form method="post" action="/account/password">
  <label for="current-password">Mật khẩu hiện tại</label>
  <input
    id="current-password"
    name="currentPassword"
    type="password"
    autocomplete="current-password"
    required
  >

  <label for="new-password">Mật khẩu mới</label>
  <input
    id="new-password"
    name="newPassword"
    type="password"
    autocomplete="new-password"
    required
  >

  <button type="submit">Cập nhật mật khẩu</button>
</form>
```

Token autocomplete không cấp quyền và không tự xác minh người dùng. Nó là gợi ý ngữ nghĩa cho browser, password manager và công nghệ hỗ trợ.

## 6. Không dùng autocomplete=off như một biện pháp bảo mật

Một số ứng dụng cố tắt password manager bằng:

```html
<input type="password" autocomplete="off">
```

Đây không phải biện pháp bảo vệ đáng tin cậy. Browser hoặc password manager có thể vẫn cung cấp khả năng lưu/autofill trong một số trường hợp, và việc cản trở người dùng dùng password manager có thể làm giảm chất lượng mật khẩu.

Hãy bảo vệ mật khẩu bằng:

- HTTPS.
- CSRF protection cho form session-based.
- Password hashing phù hợp ở server.
- Rate limiting và phát hiện credential stuffing.
- MFA/passkey khi phù hợp.
- Không log password hoặc request body nhạy cảm.
- Session rotation sau khi đăng nhập.

Autocomplete chỉ mô tả ý nghĩa field. Nó không thay thế bảo mật server.

## 7. Password manager UI và hành vi lưu mật khẩu

Browser/password manager có thể:

- Gợi ý tài khoản đã lưu.
- Điền username/password.
- Hỏi người dùng có muốn lưu credential sau đăng nhập.
- Đề nghị cập nhật mật khẩu đã lưu sau khi đổi mật khẩu.
- Tạo mật khẩu ngẫu nhiên khi người dùng đăng ký hoặc thay đổi mật khẩu.

Website không kiểm soát chính xác thời điểm hoặc hình thức prompt lưu mật khẩu. Các browser khác nhau có thể nhận diện form và hiển thị UI khác nhau.

Thiết kế để hỗ trợ password manager:

- Dùng form HTML chuẩn.
- Giữ field username/password có label và name ổn định.
- Dùng autocomplete token chính xác.
- Không chia mật khẩu thành nhiều input trừ khi có yêu cầu đặc biệt đã được đánh giá.
- Không chặn paste, autofill hoặc password generation.
- Sau khi đổi mật khẩu, phản hồi thành công rõ ràng để browser có thể nhận diện flow cập nhật.

Không yêu cầu người dùng copy password vào clipboard hoặc gửi mật khẩu qua chat/email để hoàn tất đăng nhập.

### Credential Management API

Một số browser hỗ trợ Credential Management API để website tương tác có kiểm soát với credential đã lưu, ví dụ `navigator.credentials.get()` hoặc `navigator.credentials.store()`. API có thể hỗ trợ lấy PasswordCredential hoặc lưu credential sau một lần đăng nhập thành công, tùy browser và platform.

Đây là tích hợp tăng cường, không phải điều kiện để password manager hoạt động. Hỗ trợ API và hành vi UI không đồng đều; hãy feature-detect, kiểm tra tài liệu browser mục tiêu và luôn giữ form HTML chuẩn làm đường cơ sở. Không yêu cầu người dùng cấp quyền rộng chỉ để bật autofill.

## 8. Hiển thị và ẩn mật khẩu

Một nút hiện/ẩn mật khẩu có thể hỗ trợ người dùng nhập chính xác, đặc biệt trên thiết bị di động. Nút này phải là button thật và không gửi form ngoài ý muốn:

```html
<label for="login-password">Mật khẩu</label>
<input
  id="login-password"
  name="password"
  type="password"
  autocomplete="current-password"
>
<button
  type="button"
  id="toggle-password"
  aria-pressed="false"
  aria-controls="login-password"
>
  Hiện mật khẩu
</button>
```

```js
const passwordInput = document.querySelector("#login-password");
const toggleButton = document.querySelector("#toggle-password");

toggleButton.addEventListener("click", () => {
  const show = passwordInput.type === "password";
  passwordInput.type = show ? "text" : "password";
  toggleButton.setAttribute("aria-pressed", String(show));
  toggleButton.textContent = show ? "Ẩn mật khẩu" : "Hiện mật khẩu";
});
```

Không ghi giá trị password vào console, analytics, telemetry hoặc DOM attribute không cần thiết. Nút hiện mật khẩu cần có trạng thái accessible và không làm lộ password qua log.

## 9. OTP và giao diện mã xác minh

Mã dùng một lần (OTP) thường được nhập trong một field:

```html
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
>
```

`autocomplete="one-time-code"` giúp browser hoặc hệ điều hành hỗ trợ autofill mã phù hợp trên nền tảng có hỗ trợ. Nó không chứng minh mã hợp lệ; server phải xác minh mã, thời hạn và số lần thử.

Thiết kế OTP UI:

- Hiển thị mục đích mã và kênh gửi (email/SMS/app xác thực).
- Không hiển thị toàn bộ số điện thoại/email nếu không cần; mask thông tin.
- Có thời hạn và hướng dẫn gửi lại rõ ràng.
- Rate limit resend và verify ở server.
- Không tiết lộ mã đã gửi trong error message hoặc log.
- Cho phép paste toàn bộ mã.
- Tránh bắt người dùng nhập từng ô nếu điều đó cản trở autofill và paste.

## 10. HTTP authentication dialog

HTTP authentication là cơ chế browser hiển thị giao diện xác thực dựa trên response challenge từ server.

Ví dụ server:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Internal tools"
```

Browser có thể hiển thị hộp thoại nhập username/password. Giao diện này do browser kiểm soát; website không thiết kế hoặc tùy biến trực tiếp bằng HTML/CSS.

Các điểm cần biết:

- `401 Unauthorized` đi kèm challenge phù hợp có thể kích hoạt browser authentication UI.
- Basic authentication mã hóa username/password bằng Base64 trong header, không phải mã hóa mật mã; chỉ dùng qua TLS.
- Browser có thể cache credential và tự gửi lại trong request tiếp theo.
- Logout và xóa credential có hành vi khác nhau giữa browser; không nên dựa vào một redirect để bảo đảm browser quên password.
- HTTP auth dialog có trải nghiệm hạn chế và dễ gây nhầm lẫn với prompt của browser.

Với ứng dụng người dùng phổ thông, form đăng nhập hoặc passkey flow thường dễ kiểm soát trải nghiệm hơn HTTP Basic Auth. Nếu dùng HTTP authentication cho công cụ nội bộ, cần TLS, policy truy cập mạng và vòng đời credential phù hợp.

## 11. Phân biệt 401 và 403 trong UI

Hai response code thường có ý nghĩa khác nhau:

| Status | Ý nghĩa khái quát | UI phù hợp |
| --- | --- | --- |
| 401 Unauthorized | Request chưa được xác thực hợp lệ hoặc cần credential | Yêu cầu đăng nhập/xác thực lại |
| 403 Forbidden | Server hiểu request nhưng từ chối quyền truy cập | Thông báo không đủ quyền hoặc hướng dẫn liên hệ quản trị |

Không chuyển mọi lỗi thành “sai mật khẩu”. Ví dụ tài khoản bị khóa, session hết hạn, thiếu quyền hoặc yêu cầu MFA có thể cần hướng xử lý khác.

Đồng thời, không tiết lộ quá nhiều thông tin để attacker dò user enumeration. Có thể dùng thông báo chung cho sai username/password, nhưng UI sau khi đã xác thực cần giải thích đủ để người dùng khôi phục quyền truy cập an toàn.

## 12. Passkey UI do browser điều phối

Passkey là credential WebAuthn gắn với relying party (RP). Browser phối hợp với platform authenticator hoặc security key để người dùng chọn và xác minh credential.

Website không nhận mật khẩu hay dữ liệu sinh trắc học. Thay vào đó, website nhận assertion có chữ ký để gửi server xác minh.

Một flow đăng nhập:

1. Người dùng chọn “Đăng nhập bằng passkey”.
2. Client lấy challenge và request options từ backend.
3. Client gọi `navigator.credentials.get({ publicKey })`.
4. Browser/OS hiển thị passkey picker hoặc xác nhận authenticator.
5. Authenticator tạo assertion.
6. Client gửi assertion tới backend.
7. Backend xác minh challenge, origin, RP ID, chữ ký và trạng thái user verification.
8. Server tạo session mới sau khi xác thực thành công.

UI của browser/OS có thể khác nhau. Website chỉ nên giải thích hành động và xử lý kết quả; không cố bắt chước giao diện xác nhận sinh trắc học.

## 13. Relying Party ID và origin binding

WebAuthn gắn credential với RP ID và kiểm tra origin trong ceremony. Điều này giúp passkey có khả năng chống phishing tốt hơn password truyền thống.

Các khái niệm:

- **RP ID:** Domain relying party được credential gắn với.
- **Origin:** Scheme, host và port của trang thực hiện ceremony.
- **Challenge:** Giá trị ngẫu nhiên do server tạo, dùng một lần.
- **Authenticator data:** Dữ liệu về RP ID hash, flags và thông tin liên quan.
- **Client data:** Dữ liệu client gồm challenge, origin và loại ceremony.

Server phải xác minh:

- Challenge đúng với phiên đăng nhập đang chờ và chưa dùng.
- Origin đúng allowlist của ứng dụng.
- RP ID hash khớp RP ID mong đợi.
- Chữ ký hợp lệ với public key đã đăng ký.
- User verification flag phù hợp với policy nếu yêu cầu.
- Credential thuộc user/account được xác định.

Không chỉ dựa vào việc browser hiển thị passkey picker. Backend verification là bước quyết định.

## 14. Conditional UI cho passkey

Một số browser hỗ trợ conditional mediation: passkey có thể xuất hiện trong gợi ý autofill khi người dùng focus vào field username, thay vì luôn mở một modal riêng ngay khi trang tải.

HTML:

```html
<label for="passkey-username">Email</label>
<input
  id="passkey-username"
  name="username"
  autocomplete="username webauthn"
>
```

JavaScript minh họa:

```js
async function startConditionalPasskeyLogin(requestOptions) {
  if (!navigator.credentials || !window.PublicKeyCredential) {
    return null;
  }

  if (!PublicKeyCredential.isConditionalMediationAvailable) {
    return null;
  }

  const available =
    await PublicKeyCredential.isConditionalMediationAvailable();

  if (!available) return null;

  try {
    return await navigator.credentials.get({
      publicKey: requestOptions,
      mediation: "conditional",
    });
  } catch (error) {
    if (error.name === "AbortError" || error.name === "NotAllowedError") {
      return null;
    }
    throw error;
  }
}
```

`requestOptions` phải được backend tạo và trả về an toàn; ví dụ trên chỉ minh họa cách khởi chạy conditional flow. Không tự tạo challenge cố định trong JavaScript.

Conditional mediation không được hỗ trợ đồng đều trên mọi browser và platform. Hãy feature-detect, giữ đường đăng nhập thay thế và kiểm thử trên browser mục tiêu.

## 15. User verification và giao diện OS

Authenticator có thể yêu cầu xác minh người dùng bằng PIN, sinh trắc học hoặc phương thức local khác, tùy thiết bị và cấu hình.

Các điểm cần hiểu:

- Browser/OS điều phối UI xác minh.
- Website không nhận ảnh vân tay, khuôn mặt hoặc PIN thiết bị.
- Kết quả ceremony có thể cho biết user verification đã được thực hiện qua flag.
- Server phải kiểm tra flag theo policy của hệ thống.
- User verification không đồng nghĩa với authorization cho mọi thao tác nghiệp vụ.

Ví dụ một ứng dụng có thể yêu cầu user verification cho thao tác nhạy cảm như đổi email hoặc thêm phương thức thanh toán. Server phải xác minh assertion gắn với challenge của đúng thao tác, không dùng một lần đăng nhập cũ làm xác nhận vô hạn.

## 16. FedCM và account chooser do browser quản lý

Federated Credential Management (FedCM) là một API cho phép browser điều phối trải nghiệm đăng nhập liên kết giữa relying party và identity provider. Thay vì dựa hoàn toàn vào iframe hoặc third-party cookie, browser có thể hiển thị account chooser và thông tin provider theo flow được hỗ trợ.

Mục tiêu:

- Làm rõ website nào đang yêu cầu đăng nhập.
- Cho người dùng chọn tài khoản/provider qua UI do browser kiểm soát.
- Giảm một số cơ chế tracking hoặc phụ thuộc third-party cookie.
- Tạo luồng chia sẻ identity có sự tham gia của browser.

FedCM không tự xác thực user ở backend của relying party. Server vẫn phải xác minh token/assertion do identity provider phát hành: issuer, audience/client ID, chữ ký, expiry, nonce và các claim cần thiết.

API, UI và browser support của FedCM thay đổi theo thời gian và platform. Hãy xem tài liệu browser mục tiêu, feature-detect và cung cấp fallback an toàn. Không xây flow production dựa trên giả định mọi browser đều hiển thị cùng một account chooser.

## 17. Không giả lập browser hoặc OS authentication UI

Một website độc hại có thể tạo modal trông giống:

- Hộp thoại nhập password của browser.
- Cửa sổ xác nhận sinh trắc học.
- Password manager popup.
- Account chooser của identity provider.
- Thanh địa chỉ hoặc cảnh báo certificate.

Đây là kỹ thuật UI spoofing/phishing. Website hợp pháp nên tránh tạo trải nghiệm tương tự browser chrome hoặc OS prompt.

Nguyên tắc:

- Dùng API chính thức để gọi passkey, WebAuthn hoặc FedCM UI.
- Giữ brand và nội dung app UI rõ ràng là của website.
- Không vẽ thanh địa chỉ giả hoặc icon certificate giả.
- Không yêu cầu người dùng nhập lại mật khẩu vào modal giả danh browser.
- Hướng dẫn người dùng kiểm tra domain qua browser UI khi có dấu hiệu phishing.
- Không yêu cầu gửi password, OTP hoặc recovery code qua support chat.

## 18. Clickjacking và UI redressing trên trang đăng nhập

Attacker có thể nhúng trang login vào iframe rồi phủ lớp trong suốt hoặc nút giả để người dùng click nhầm. Với trang authentication, clickjacking có thể khiến người dùng:

- Bấm nút đăng nhập hoặc chấp nhận liên kết tài khoản ngoài ý muốn.
- Bật camera/microphone hoặc chấp nhận quyền không mong đợi.
- Thêm passkey hoặc thay đổi phương thức xác thực.
- Xác nhận giao dịch hoặc thay đổi bảo mật tài khoản.

Nếu trang không cần nhúng, dùng CSP:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Nếu chỉ cho phép một portal tin cậy:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
```

`frame-ancestors` kiểm soát ancestor được phép nhúng document. Đây là directive phù hợp để chống clickjacking; `frame-src` kiểm soát frame mà trang tải, không thay thế frame-ancestors.

Có thể dùng `X-Frame-Options` như lớp tương thích cho browser cũ:

```http
X-Frame-Options: DENY
```

Không dùng JavaScript frame-busting như biện pháp duy nhất. CSP header phải được gửi từ server và kiểm tra trên response cuối.

## 19. Login CSRF và xác nhận tài khoản

Login CSRF là tình huống attacker khiến browser của nạn nhân đăng nhập vào tài khoản do attacker kiểm soát. Sau đó nạn nhân có thể vô tình đưa dữ liệu cá nhân vào tài khoản đó.

Phòng vệ cho login flow:

- Dùng CSRF token hoặc cơ chế chống login CSRF phù hợp.
- Kiểm tra Origin/Fetch Metadata theo policy server.
- Không thay đổi trạng thái bằng GET.
- Rotate session ID sau khi xác thực.
- Hiển thị rõ tài khoản đang đăng nhập sau thành công.
- Cân nhắc xác nhận lại khi liên kết identity provider hoặc thay đổi account.

Một form login nhìn đúng không đủ bảo vệ CSRF. Server phải xác minh request và quản lý session đúng cách.

## 20. Phản hồi lỗi không làm lộ thông tin tài khoản

Thông báo quá chi tiết có thể giúp attacker dò email/tên tài khoản:

- “Email này tồn tại nhưng password sai.”
- “Tài khoản này chưa đăng ký.”
- “Tài khoản này bị khóa vì đã nhập sai 5 lần.”

Với bước đăng nhập, có thể dùng thông báo chung:

```text
Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra lại hoặc khôi phục tài khoản.
```

Sau khi đã xác thực danh tính ở mức phù hợp, UI có thể đưa hướng dẫn cụ thể hơn. Không tiết lộ trạng thái account cho người chưa được xác thực.

Thông báo cần hữu ích nhưng không tạo oracle cho username enumeration. Rate limit và monitoring ở server vẫn cần thiết.

## 21. Accessibility và trạng thái UI xác thực

Authentication UI thường xuất hiện trong tình huống người dùng căng thẳng hoặc cần thao tác nhanh. Giao diện cần hỗ trợ bàn phím, screen reader và thiết bị di động.

Checklist:

- Label gắn với input bằng for/id.
- Lỗi được liên kết với field qua aria-describedby.
- Focus chuyển tới lỗi tổng quát hoặc field đầu tiên cần sửa.
- Trạng thái loading và kết quả có vùng live phù hợp.
- Nút show/hide password có tên và trạng thái accessible.
- Không dùng màu sắc làm tín hiệu duy nhất.
- Cho phép paste password, OTP và recovery code.
- Không tự xóa toàn bộ field khi có lỗi không liên quan.
- Không dùng timeout quá ngắn làm mất nội dung người dùng đang nhập.

Ví dụ thông báo trạng thái:

```html
<p id="login-status" role="status" aria-live="polite"></p>
```

Không đọc password hoặc OTP qua live region, title, tooltip hoặc console.

## 22. Session UI sau khi đăng nhập

Authentication UI không kết thúc ở nút submit. Sau đăng nhập, ứng dụng cần thể hiện trạng thái session và cung cấp cách kết thúc an toàn.

Nên có:

- Tên/tài khoản hiện tại theo mức thông tin phù hợp.
- Trạng thái đăng nhập hoặc phiên hết hạn.
- Nút logout rõ ràng.
- Trang quản lý thiết bị/session nếu sản phẩm hỗ trợ.
- Thông báo khi cần xác thực lại.
- Hướng dẫn khôi phục tài khoản và cập nhật phương thức xác thực.

Logout phải được xử lý ở server để thu hồi session/cookie phù hợp; chỉ xóa nội dung UI hoặc chuyển về trang login không đủ.

Khi session hết hạn, tránh lặp redirect hoặc gửi form cũ tự động. Thông báo người dùng, giữ dữ liệu không nhạy cảm nếu có thể và yêu cầu xác thực lại theo flow an toàn.

## 23. UI cho xác thực tăng cường (step-up authentication)

Một số hành động cần xác minh lại dù người dùng đã đăng nhập:

- Thay đổi email hoặc số điện thoại khôi phục.
- Tạo hoặc xóa passkey.
- Tắt MFA.
- Xem hoặc tạo recovery code.
- Thực hiện giao dịch nhạy cảm.

UI cần nêu rõ:

1. Hành động nào đang được xác nhận.
2. Vì sao cần xác thực lại.
3. Phương thức được chấp nhận.
4. Nếu thất bại thì người dùng có thể làm gì.
5. Khi nào thao tác sẽ được hoàn tất.

Server phải gắn challenge/reauthentication result với đúng action và thời hạn. Không dùng một boolean ở frontend như `isReauthenticated = true` làm bằng chứng.

## 24. Ví dụ form login có thông báo accessible

```html
<form id="login-form" method="post" action="/login">
  <label for="login-user">Email</label>
  <input
    id="login-user"
    name="username"
    type="email"
    autocomplete="username"
    aria-describedby="login-error"
    required
  >

  <label for="login-pass">Mật khẩu</label>
  <input
    id="login-pass"
    name="password"
    type="password"
    autocomplete="current-password"
    aria-describedby="login-error"
    required
  >

  <p id="login-error" role="alert"></p>
  <p id="login-status" role="status" aria-live="polite"></p>

  <button type="submit">Đăng nhập</button>
</form>
```

Server nên trả response và error state phù hợp. Không đặt password vào query string, URL fragment hoặc client-side analytics.

Nếu dùng SPA, vẫn cần bảo đảm form semantics, keyboard submission, CSRF token và xử lý response an toàn. Không dùng JavaScript-only click handler làm mất hành vi submit chuẩn mà browser/password manager dựa vào.

## 25. Kiểm thử Authentication UI

Thực hành trên staging với tài khoản thử nghiệm. Không dùng mật khẩu hoặc OTP thật của người dùng.

### Bước 1 — Kiểm tra form semantics

Mở DevTools → Elements. Kiểm tra:

- Label và input liên kết đúng.
- Field name ổn định.
- autocomplete token chính xác.
- Form method/action dùng HTTPS và POST phù hợp.
- Không có password/token trong URL.

### Bước 2 — Kiểm tra password manager

Với browser profile thử nghiệm:

- Lưu một credential lab.
- Tải lại trang login.
- Kiểm tra gợi ý autofill.
- Đăng nhập thành công và quan sát prompt lưu/cập nhật nếu browser hỗ trợ.
- Thử paste password và password dài.

Hành vi prompt phụ thuộc browser; không coi việc không hiện prompt là lỗi xác thực.

### Bước 3 — Kiểm tra OTP

Thử autofill/paste mã lab. Xác minh server giới hạn số lần thử, expiry và resend. Không để OTP xuất hiện trong console hoặc analytics.

### Bước 4 — Kiểm tra passkey UI

Trên browser/platform hỗ trợ:

- Tạo credential lab cho RP ID.
- Chạy nút passkey hoặc conditional mediation.
- Kiểm tra browser/OS picker.
- Hủy prompt và xác minh UI xử lý AbortError/NotAllowedError.
- Gửi assertion về backend test để kiểm tra challenge/origin/RP ID/signature.

### Bước 5 — Kiểm tra iframe/clickjacking

Nhúng trang login vào một origin lab khác. Xác minh CSP frame-ancestors chặn nếu sản phẩm không cho embed.

### Bước 6 — Kiểm tra HTTP auth nếu được dùng

Quan sát response 401 và WWW-Authenticate. Kiểm tra browser dialog, credential caching và hành vi sau logout trên browser mục tiêu.

### Bước 7 — Kiểm tra accessibility

Chỉ dùng bàn phím để đi qua form, lỗi, show/hide password và OTP. Kiểm tra focus, label, aria status và screen reader.

## 26. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Password manager không nhận form | Thiếu label/name/autocomplete hoặc markup bất thường | Dùng form HTML chuẩn và token phù hợp |
| Browser không hiện save prompt | Browser policy, credential flow hoặc user settings | Kiểm tra credential lưu trong profile thử nghiệm; không ép prompt |
| Autofill điền sai field | Token hoặc field name mơ hồ | Gán username/current-password/new-password chính xác |
| OTP không autofill | Thiếu one-time-code hoặc platform không hỗ trợ | Cho phép paste và nhập thủ công |
| Passkey picker không xuất hiện | API không hỗ trợ, RP ID/origin sai hoặc request options lỗi | Feature-detect và kiểm tra backend challenge |
| WebAuthn trả NotAllowedError | User hủy, timeout, không có credential phù hợp hoặc policy | Hiển thị lựa chọn khác và không lặp prompt vô hạn |
| Conditional UI không hoạt động | Browser/platform không hỗ trợ mediation | Dùng nút passkey thông thường làm fallback |
| HTTP auth dialog xuất hiện ngoài dự kiến | Endpoint trả 401 + WWW-Authenticate | Kiểm tra server challenge và route |
| Trang login bị nhúng | Thiếu frame-ancestors hoặc allowlist quá rộng | Gửi CSP frame-ancestors phù hợp |
| UI báo login thành công nhưng API vẫn 401 | Frontend state sai hoặc cookie/session không được thiết lập | Kiểm tra response, cookie và server session |
| Lỗi tiết lộ tài khoản tồn tại | Thông báo phân biệt user/password quá chi tiết | Dùng response chung và rate limit |
| Logout nhưng vẫn đăng nhập lại ngay | Session chưa bị thu hồi hoặc credential browser tự điền | Thu hồi session ở server và giải thích autofill là credential đã lưu |

## 27. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Mọi authentication UI đều do website vẽ.” | Password manager, HTTP auth, passkey picker và FedCM có UI do browser/OS điều phối. |
| “Website có thể kiểm soát thanh địa chỉ.” | Browser giữ quyền kiểm soát browser chrome và origin indicator. |
| “autocomplete off bảo vệ password.” | Nó không phải biện pháp bảo mật đáng tin cậy và có thể cản password manager. |
| “Passkey gửi vân tay lên server.” | Authenticator xử lý xác minh local; server nhận assertion có chữ ký. |
| “Browser hiển thị passkey nghĩa là backend đã xác thực.” | Backend vẫn phải xác minh challenge, origin, RP ID, signature và user binding. |
| “FedCM tự tạo session cho ứng dụng.” | Relying party phải xác minh token/assertion và tự tạo session. |
| “CORS bảo vệ WebSocket authentication.” | WebSocket signaling cần Origin validation, authentication và CSWSH defense. |
| “Modal giống browser làm UI đáng tin hơn.” | UI giả browser có thể là phishing; dùng browser API chính thức. |
| “Logout chỉ cần chuyển về trang login.” | Server phải thu hồi session; browser có thể còn credential đã lưu trong password manager. |
| “Một lần reauth bảo vệ mọi hành động mãi mãi.” | Step-up result phải gắn với action, challenge và thời hạn. |

## 28. Checklist thiết kế Authentication UI

- Phân biệt application UI, browser-mediated UI và OS authenticator UI.
- Dùng HTTPS và form HTML có label/name/autocomplete rõ ràng.
- Dùng current-password, new-password, username, one-time-code và webauthn đúng mục đích.
- Không chặn password manager, autofill, paste hoặc password generation.
- Không dùng autocomplete=off như biện pháp bảo mật.
- Không log password, OTP, recovery code, access token hoặc assertion nhạy cảm.
- Dùng POST/HTTPS; không đặt credential trong URL.
- Dùng browser API chính thức cho WebAuthn/passkey và FedCM.
- Backend tạo challenge và xác minh origin, RP ID, signature, nonce/token.
- Giữ fallback khi browser/platform không hỗ trợ tính năng mới.
- Không giả lập browser chrome, password manager popup hoặc OS biometric prompt.
- Dùng CSP frame-ancestors để chống clickjacking.
- Bảo vệ login form bằng CSRF controls và session rotation.
- Dùng error message cân bằng giữa hữu ích và chống user enumeration.
- Thiết kế OTP, lỗi, focus và trạng thái accessible.
- Thu hồi session ở server khi logout hoặc account security event.
- Gắn step-up authentication với đúng hành động và thời hạn.
- Kiểm thử password manager, passkey, HTTP auth, iframe và accessibility trên browser mục tiêu.

## 29. Câu hỏi tự kiểm tra

1. Application UI khác browser-mediated UI ở điểm nào?
2. Vì sao website không thể thay đổi hoặc xác thực người dùng qua thanh địa chỉ?
3. Các autocomplete token nào phù hợp cho username, current password, new password và OTP?
4. Vì sao autocomplete=off không phải biện pháp bảo mật?
5. Browser xử lý password manager save/autofill UI như thế nào?
6. HTTP authentication dialog được kích hoạt bởi response nào?
7. Basic authentication cần điều kiện transport nào?
8. Passkey picker do thành phần nào điều phối?
9. RP ID và origin được backend dùng để xác minh điều gì?
10. Conditional mediation khác nút passkey thông thường như thế nào?
11. FedCM giúp browser tham gia vào federated login ra sao?
12. Vì sao không nên giả lập browser/OS authentication UI?
13. frame-ancestors giúp bảo vệ login UI khỏi clickjacking như thế nào?
14. Vì sao login form vẫn cần CSRF protection?
15. Step-up authentication phải gắn với action và thời hạn ra sao?

**Ghi nhớ:** Authentication UI gồm giao diện của website và giao diện do browser/OS điều phối. Form HTML chuẩn giúp password manager hoạt động; WebAuthn/passkey và FedCM dùng browser-mediated UI để giảm việc nhập credential vào trang giả mạo. Website không kiểm soát browser chrome và không nên giả lập prompt hệ thống. Backend luôn phải xác minh challenge, origin, credential và quyền; đồng thời bảo vệ login bằng HTTPS, CSRF controls, session lifecycle, chống clickjacking và thông báo lỗi phù hợp.
