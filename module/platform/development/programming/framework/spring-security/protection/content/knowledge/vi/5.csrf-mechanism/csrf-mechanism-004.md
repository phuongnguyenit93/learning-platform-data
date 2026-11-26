# Mẫu double-submit cookie, biến thể có ký và điều kiện kiểm soát cookie

## Mục tiêu học tập

Sau bài học trong chương **Cơ chế CSRF**, người học có thể:

- Mô tả **Double-Submit Cookie Pattern**: gửi cùng một CSRF token qua **cookie** và **trường form hoặc HTTP header**, sau đó đối chiếu chúng.
- Phân biệt phiên bản **naive double-submit** với **signed double-submit cookie ràng buộc phiên**, hiểu lý do chỉ so hai chuỗi chưa đủ an toàn.
- Phân tích các đường **cookie injection/cookie tossing**, phạm vi `Domain`, `Path`, thuộc tính `Secure`, `HttpOnly`, `SameSite` và tiền tố `__Host-`.
- Thiết kế token dùng **nonce ngẫu nhiên** và **HMAC theo định danh bí mật/đáng tin cậy của phiên**, kiểm tra token cùng ngữ cảnh xác thực.
- Xác định khi nào nên dùng `CookieCsrfTokenRepository`, `CookieServerCsrfTokenRepository` hoặc phương án token lưu theo session trong Spring Security **Servlet** và **Reactive**.
- Lập kế hoạch kiểm thử CSRF, kiểm tra duplicate cookie, token sai phiên, vòng đời sau đăng nhập và sự tương tác với SPA/CORS.

## 1. Vấn đề cần giải quyết

Ứng dụng web dựa vào cookie để xác thực thường không tự phân biệt được một yêu cầu do người dùng bấm nút trong trang hợp lệ với một yêu cầu do website ngoài kích hoạt. Khi trình duyệt được phép gửi cookie phiên trong một ngữ cảnh cross-site, máy chủ có thể nhìn thấy credential hợp lệ ngay cả khi yêu cầu thay đổi trạng thái là giả mạo.

**CSRF token** bổ sung một giá trị mà trang hoặc mã client hợp lệ phải **chủ động đưa vào yêu cầu**. Kẻ tấn công bên ngoài có thể khiến trình duyệt gửi cookie tự động, nhưng thường không thể đọc token từ ứng dụng đích hoặc tự gắn một header tùy chỉnh mang token đúng.

Ở bài này, ta nghiên cứu cách **double-submit cookie** tận dụng sự khác nhau giữa **cookie được trình duyệt tự gửi** và **token được client gửi thêm**. Nội dung thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, nơi các lớp bảo vệ CSRF được triển khai cùng CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session cho cả Servlet lẫn Reactive.

## 2. Double-submit cookie hoạt động ra sao?

Trong mẫu đơn giản, ứng dụng tạo một token ngẫu nhiên, lưu vào cookie riêng (ví dụ `XSRF-TOKEN`) và cung cấp để trang hợp lệ đưa giá trị đó vào hidden field hoặc header. Khi nhận yêu cầu làm thay đổi trạng thái, máy chủ đọc **hai bản sao**:

1. Bản sao trong **cookie CSRF** do trình duyệt gửi đến endpoint.
2. Bản sao trong **header hoặc trường form** mà client chủ động gửi.

Nếu cả hai giá trị tồn tại và khớp nhau thì yêu cầu **có thể** vượt qua bước đối chiếu của mẫu đơn giản.

Ví dụ một yêu cầu hợp lệ:

~~~http
POST /settings/email HTTP/1.1
Host: app.example.com
Cookie: SESSION=opaque-session; XSRF-TOKEN=random-csrf-value
X-XSRF-TOKEN: random-csrf-value
Content-Type: application/json

{"email":"new@example.test"}
~~~

Trong request này, `SESSION` xác định phiên đăng nhập; `XSRF-TOKEN` là cookie chuyên dùng cho CSRF; `X-XSRF-TOKEN` là bản sao được client gửi chủ động.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt / client hợp lệ
    participant S as Máy chủ
    participant A as Website tấn công

    U->>B: Mở trang của app.example.com
    B->>S: GET /settings
    S-->>B: Set-Cookie: XSRF-TOKEN=T, HTML hoặc JS truy cập T
    U->>B: Gửi form / gọi API hợp lệ
    B->>S: POST + Cookie XSRF-TOKEN=T + header/form token=T
    S->>S: So sánh hai bản sao (và kiểm chứng chữ ký nếu có)
    S-->>B: Tiếp tục xác thực, phân quyền và xử lý
    A-->>B: Trang ngoài dụ gửi một request
    B->>S: POST + cookie có thể tự gửi, thiếu token chủ động
    S-->>B: Từ chối nếu kiểm chứng CSRF đúng
~~~

**Điều kiện quan trọng:** Một website ngoài có thể tạo form HTML đến `app.example.com`, nhưng không vì thế mà đọc được cookie của `app.example.com` hoặc đặt được header tùy chỉnh theo ý muốn. Ngược lại, nếu attacker **có thể kiểm soát giá trị cookie CSRF mà trình duyệt gửi đến server**, chỉ so sánh hai bản sao sẽ mất hiệu lực. Đây là vấn đề trung tâm của bài học.

### 2.1. Khác synchronizer token ở đâu?

| Tiêu chí | Synchronizer token | Double-submit cookie |
|---|---|---|
| Nơi lưu **token kỳ vọng** | Phía server, thường gắn với `HttpSession`/`WebSession` | Trong cookie; ở biến thể có ký, server kiểm tra chữ ký thay vì phải tra token gốc trong session |
| Client gửi token bằng | Hidden field hoặc header | Cookie **và** hidden field/header |
| Cách server xác minh | So token request với token được lưu cho phiên | So hai bản sao; **biến thể mạnh** còn xác minh HMAC gắn với phiên |
| Có cần lưu từng token trong session? | Thường có | Không bắt buộc nếu dùng HMAC đúng cách |
| Nguy cơ cần chú ý | Đồng bộ phiên, token hết hạn, session store | **Cookie injection**, phạm vi cookie, token không ràng buộc phiên, quản lý khóa ký |

**Không lưu token trong session** không đồng nghĩa với **không ràng buộc token vào phiên**. Với signed double-submit, token có thể được xác thực nhờ HMAC chứa một thông tin gắn với phiên hiện tại, dù server không giữ bản sao token CSRF theo phiên.

## 3. Naive double-submit cookie: thiết kế đơn giản và điểm yếu

Mô hình tối giản:

~~~text
Cấp token:
  token = secureRandom()
  Set-Cookie: XSRF-TOKEN=token

Kiểm tra POST:
  cookieToken = request.cookies["XSRF-TOKEN"]
  submitted = request.header["X-XSRF-TOKEN"] hoặc form["_csrf"]

  nếu cả hai tồn tại và cookieToken == submitted:
      qua bước đối chiếu CSRF
  ngược lại:
      từ chối
~~~

Cách kiểm tra này chỉ trả lời: **hai nơi gửi có cùng giá trị không?** Nó **không chứng minh** server đã phát hành token cho người dùng/phiên đang được xác thực.

Nếu kẻ tấn công chỉ có một website hoàn toàn độc lập, không đọc/ghi được cookie của ứng dụng đích, việc đoán token ngẫu nhiên đủ dài thường không khả thi. Nhưng mô hình trở nên yếu khi attacker có **khả năng can thiệp vào cookie CSRF** trên trình duyệt nạn nhân.

### 3.1. Cookie injection từ subdomain

Giả sử:

- Ứng dụng đích ở `https://bank.example.com`.
- Một subdomain `https://blog.example.com` bị chiếm quyền hoặc cho người dùng tự triển khai nội dung.
- Ứng dụng dùng cookie CSRF tên `XSRF-TOKEN`, server chỉ kiểm tra cookie và form/header có giá trị giống nhau.

Một máy chủ chạy tại `blog.example.com` có thể thử đặt cookie có phạm vi cha:

~~~http
Set-Cookie: XSRF-TOKEN=attacker-chosen; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

Nếu trình duyệt nhận cookie đó, nó có thể gửi cookie cho `bank.example.com` khi các điều kiện khác cho phép. Attacker cũng biết `attacker-chosen` để đưa vào form giả mạo:

~~~html
<form method="post" action="https://bank.example.com/settings/email">
  <input type="hidden" name="email" value="attacker@example.test">
  <input type="hidden" name="_csrf" value="attacker-chosen">
</form>
<script>document.forms[0].submit();</script>
~~~

Nếu **request mang cả cookie xác thực hợp lệ** và server **chọn cookie CSRF do attacker đặt**, phép kiểm tra “cookie bằng field” sẽ đạt dù giá trị không đến từ ứng dụng ngân hàng. Việc khai thác thực tế còn phụ thuộc `SameSite`, cookie đã tồn tại, thứ tự/ưu tiên cookie trùng tên, trình duyệt và cách server parse cookie; không phải mọi hệ thống dùng naive double-submit đều mặc nhiên khai thác được bởi ví dụ này.

**Điểm thất bại:** Server không biết token đó **đã được mình phát hành cho phiên nạn nhân** hay chưa.

### 3.2. Cookie trùng tên, Path và Domain

Browser có thể gửi nhiều cookie cùng **tên** nhưng khác `Domain` hoặc `Path`. Header `Cookie` **không chứa các thuộc tính Domain/Path** của từng cookie, nên server có thể gặp tình huống khó xác định “bản sao nào là đúng”:

~~~http
Cookie: XSRF-TOKEN=attacker-chosen; XSRF-TOKEN=legitimate-value; SESSION=...
~~~

Parser có thể chọn giá trị đầu, cuối hoặc xử lý khác. Không được dựa vào thứ tự cookie như một ranh giới bảo mật. Nên kiểm soát **phạm vi cookie**, tên cookie và xử lý rõ trường hợp trùng tên, đặc biệt ở ứng dụng có nhiều subdomain hoặc ứng dụng legacy.

### 3.3. Những đường attacker có thể ảnh hưởng cookie

| Khả năng của attacker | Ý nghĩa với naive double-submit |
|---|---|
| Kiểm soát subdomain có thể đặt cookie `Domain=example.com` | Có thể cố gắng tiêm cookie được gửi tới host ứng dụng chính |
| Lỗ hổng HTTP response splitting/CRLF hay cookie tossing | Có thể khiến trình duyệt lưu cookie attacker chọn |
| Ứng dụng/hostname không dùng HTTPS nhất quán | Có thể làm tăng nguy cơ tiêm/thay cookie trong những hoàn cảnh cụ thể |
| XSS tại origin của ứng dụng | Có thể đọc/đưa token vào request; CSRF token **không thay thế phòng vệ XSS** |
| Chỉ kiểm soát website khác site, không có đường ghi cookie | Khó hơn nhiều để đặt giá trị cookie CSRF cho ứng dụng đích |

Biện pháp **đáng tin cậy hơn** là tạo **chữ ký phía server gắn với phiên**, khiến attacker không thể biến một cookie tùy chọn thành token hợp lệ, kể cả khi họ biết rõ giá trị cookie đã tiêm.

## 4. Signed double-submit: HMAC và ràng buộc phiên

Biến thể được ưu tiên khi dùng double-submit dựa vào hai tính chất:

1. Token có **chữ ký HMAC** được tạo bằng khóa bí mật chỉ server biết, nên attacker không thể tự tạo token hợp lệ.
2. Chữ ký bao gồm **dữ liệu gắn với phiên đăng nhập hiện tại**, nên token do attacker lấy ở phiên của họ **không hợp lệ cho phiên nạn nhân**.

Một dạng token minh họa:

~~~text
nonce = 32 byte ngẫu nhiên từ CSPRNG
sessionBinding = định danh bí mật/đáng tin cậy, thay đổi theo phiên đăng nhập
message = frame(sessionBinding, nonce)
mac = HMAC-SHA256(serverSecret, message)
csrfToken = base64url(nonce) + "." + base64url(mac)
~~~

`frame` là cách mã hóa **không nhập nhằng** hai thành phần, ví dụ ghép **độ dài + byte nội dung**. Không nên nối hai chuỗi tùy ý không có phân định rõ ràng.

**Khóa `serverSecret` phải chỉ nằm phía server**; không ghi vào JavaScript, HTML, cookie hoặc repository công khai. `sessionBinding` phải được lấy từ **ngữ cảnh phiên đã được server xác thực hoặc tin cậy**, không lấy tùy ý từ trường form, header do client chọn, hoặc chỉ từ username có thể đoán. Có thể dùng session ID phía server hoặc bí mật ngẫu nhiên riêng cho phiên, tùy kiến trúc.

### 4.1. Phát hành và xác minh

Khi người dùng tải trang hợp lệ, server xác định `sessionBinding`, tạo `nonce`, tính HMAC, và cấp cùng một token qua cookie và kênh để client chủ động gửi lại (ví dụ render trong form, meta tag hoặc API trả JSON cùng origin).

Khi nhận POST, server phải kiểm tra **cả ba** điều kiện:

- **Bản sao**: token trong cookie CSRF và token gửi trong header/form đều có mặt và bằng nhau.
- **Tính toàn vẹn**: HMAC hợp lệ theo khóa bí mật server.
- **Đúng phiên**: HMAC được tính lại theo `sessionBinding` của **request hiện tại**, không dùng binding do client khai báo.

~~~mermaid
flowchart TD
    A[POST thay đổi trạng thái] --> B{Có cookie CSRF và token form/header?}
    B -- Không --> X[Từ chối]
    B -- Có --> C{Hai bản sao khớp?}
    C -- Không --> X
    C -- Có --> D[Tra sessionBinding đáng tin cậy]
    D --> E{Định dạng và HMAC hợp lệ với phiên này?}
    E -- Không --> X
    E -- Có --> F[Tiếp tục authentication, authorization và nghiệp vụ]
~~~

Lưu ý: Authentication/session cần được xác định bằng nguồn tin cậy trước khi kiểm chứng HMAC gắn phiên. Trong thực thi Spring Security, thứ tự filter và cách lấy session binding phải được thiết kế phù hợp; sơ đồ mô tả **điều kiện logic**, không hàm ý viết mọi bước trực tiếp trong controller.

### 4.2. Vì sao chỉ “ký token” vẫn chưa đủ?

Giả sử server tạo `HMAC(serverSecret, nonce)` nhưng **không bao gồm session binding**. Attacker có thể đăng nhập tài khoản của chính họ, nhận một token có chữ ký hợp lệ, rồi cố tiêm **chính token đó** vào cookie CSRF của nạn nhân. Nếu server chỉ kiểm tra HMAC mà không ràng buộc phiên, token attacker là một token **hợp lệ toàn hệ thống** và có thể bị tái sử dụng.

Bởi vậy:

| Thiết kế | Chống đoán token | Chống dùng token hợp lệ từ phiên khác |
|---|---|---|
| Hai bản sao ngẫu nhiên, không ký | Có nếu attacker không thể tiêm/đọc cookie | **Không bảo đảm** khi attacker kiểm soát cookie |
| HMAC chỉ theo nonce | Có | **Không bảo đảm** nếu attacker có token hợp lệ của họ |
| HMAC theo nonce **và binding phiên riêng** | Có | **Có**, nếu binding/khóa được bảo vệ và xác minh đúng |
| HMAC theo username cố định | Có | **Yếu hơn ràng buộc phiên**, không xử lý đúng nhiều phiên và vòng đời xác thực |

### 4.3. Mã Java minh họa tạo và kiểm tra token có ký

Ví dụ Java sau tập trung vào **lõi mật mã**, không tự thay thế filter HTTP, session management hoặc bảo vệ cookie trong Spring Security. Khóa ứng dụng phải được cấp từ hệ thống quản lý bí mật, có độ mạnh phù hợp (ví dụ ít nhất 32 byte ngẫu nhiên), và giữ nhất quán giữa các instance cần xác minh token.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedDoubleSubmitTokens {
    private static final int NONCE_BYTES = 32;
    private static final int MAC_BYTES = 32; // HMAC-SHA256
    private static final int MAX_TOKEN_CHARS = 256;
    private final SecureRandom random = new SecureRandom();
    private final SecretKeySpec signingKey;

    public SignedDoubleSubmitTokens(byte[] serverSecret) {
        if (serverSecret == null || serverSecret.length < 32) {
            throw new IllegalArgumentException("Khóa ký phải là bí mật đủ mạnh");
        }
        signingKey = new SecretKeySpec(serverSecret.clone(), "HmacSHA256");
    }

    public String issue(String trustedSessionBinding) {
        requireBinding(trustedSessionBinding);
        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);
        return encode(nonce) + "." + encode(sign(trustedSessionBinding, nonce));
    }

    public boolean verify(
            String trustedSessionBinding,
            String cookieToken,
            String submittedToken) {

        if (trustedSessionBinding == null || trustedSessionBinding.isEmpty()
                || cookieToken == null || submittedToken == null
                || cookieToken.length() > MAX_TOKEN_CHARS
                || submittedToken.length() > MAX_TOKEN_CHARS) {
            return false;
        }

        // Header/form PHẢI mang chính token trong cookie.
        byte[] cookieBytes = cookieToken.getBytes(StandardCharsets.US_ASCII);
        byte[] submittedBytes = submittedToken.getBytes(StandardCharsets.US_ASCII);
        if (!MessageDigest.isEqual(cookieBytes, submittedBytes)) {
            return false;
        }

        String[] parts = cookieToken.split("\\.", -1);
        if (parts.length != 2) {
            return false;
        }

        try {
            byte[] nonce = Base64.getUrlDecoder().decode(parts[0]);
            byte[] mac = Base64.getUrlDecoder().decode(parts[1]);
            if (nonce.length != NONCE_BYTES || mac.length != MAC_BYTES) {
                return false;
            }
            byte[] expected = sign(trustedSessionBinding, nonce);
            return MessageDigest.isEqual(expected, mac);
        } catch (IllegalArgumentException badBase64) {
            return false;
        }
    }

    private byte[] sign(String binding, byte[] nonce) {
        byte[] sessionBytes = binding.getBytes(StandardCharsets.UTF_8);
        // Định dạng message chứa độ dài của từng trường để tránh nhập nhằng.
        ByteBuffer framed = ByteBuffer.allocate(
                4 + sessionBytes.length + 4 + nonce.length);
        framed.putInt(sessionBytes.length);
        framed.put(sessionBytes);
        framed.putInt(nonce.length);
        framed.put(nonce);

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(signingKey);
            return mac.doFinal(framed.array());
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("Không khởi tạo được HMAC", ex);
        }
    }

    private static String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private static void requireBinding(String binding) {
        if (binding == null || binding.isEmpty()) {
            throw new IllegalArgumentException("Thiếu binding của phiên");
        }
    }
}
~~~

Đoạn trên chỉ nhận `trustedSessionBinding` đã được tầng xác thực/session xác định; **không lấy giá trị này trực tiếp từ input của người dùng**. Khi tích hợp HTTP thật còn phải giải quyết cookie trùng tên, lỗi parse, mã hóa, giới hạn kích thước request, thời hạn và vòng đời phiên. Để kiểm chứng thành công, không được chỉ gọi `verify` với bất kỳ binding do client gửi lên.

Cũng cần đảm bảo không có đường code nào **chấp nhận token cũ sau khi session binding thay đổi**. Nếu ứng dụng dùng hệ thống token stateless, có thể dùng định danh phiên xác thực đủ ngẫu nhiên, ổn định trong một lần đăng nhập và thay đổi sau các biến cố cần vô hiệu hóa; chỉ sử dụng username hoặc role để ký là không đủ.

### 4.4. Vòng đời chữ ký, nonce và khóa bí mật

- **Nonce** nên do nguồn ngẫu nhiên mật mã tạo; có thể cấp một token theo mỗi phiên hoặc làm mới theo chính sách ứng dụng. HMAC không yêu cầu server lưu riêng nonce.
- **Session binding** nên đổi khi phiên xác thực bị thay, đăng nhập lại hoặc bị vô hiệu hóa. Không đặt session ID thô vào giá trị token công khai.
- **Khóa HMAC** cần bảo mật, được quản lý/luân chuyển có kiểm soát. Khi xoay khóa, token ký bằng khóa cũ có thể hết hiệu lực; cần thiết kế khả năng chuyển đổi và làm mới token.
- **Nhiều node** phải dùng khóa ký/chính sách phiên thống nhất để tránh lỗi CSRF lúc request được chuyển qua node khác.
- **Token bị lộ** do XSS hoặc log sai cách vẫn nguy hiểm dù có chữ ký; không đưa token vào URL hoặc dữ liệu telemetry không được kiểm soát.

## 5. Điều kiện kiểm soát cookie và mức độ bảo vệ

Một HMAC đúng thiết kế làm giảm tác động của cookie injection, nhưng **cookie scope vẫn là ranh giới cần bảo vệ**. Nên kết hợp biện pháp mật mã với cấu hình cookie và hostname phù hợp.

### 5.1. Bảng các thuộc tính quan trọng

| Thuộc tính | Cấu hình/vai trò | Ý nghĩa trong double-submit |
|---|---|---|
| **`Domain`** | Không khai báo thì cookie thường là **host-only** | Thu hẹp phạm vi nhận cookie và nguy cơ subdomain tiêm cookie dùng chung |
| **`Path`** | Chẳng hạn `Path=/` | Chọn các request được gửi cookie; **không phải** biên giới bảo mật mạnh |
| **`Secure`** | Cookie chỉ gửi qua kênh an toàn phù hợp, thường là HTTPS | Giảm nguy cơ rò rỉ/ảnh hưởng từ đường truyền không mã hóa; là điều kiện dùng `SameSite=None` và `__Host-` |
| **`HttpOnly`** | JavaScript không đọc cookie qua `document.cookie` | Phù hợp với cookie **xác thực**; với cookie **CSRF** mà SPA cần tự đọc thì có thể phải tắt |
| **`SameSite=Strict`** | Chặn cookie trong ngữ cảnh cross-site | Giảm các đường CSRF phụ thuộc cookie nhưng có thể ảnh hưởng luồng đăng nhập/điều hướng hợp lệ |
| **`SameSite=Lax`** | Thường chặn cross-site POST, cho phép một số điều hướng top-level an toàn | Lớp bổ sung; không xử lý hết tình huống same-site cross-origin hoặc endpoint GET thay đổi trạng thái |
| **`SameSite=None; Secure`** | Cho phép cookie trong nhiều ngữ cảnh cross-site nếu browser cho phép | Dùng khi có yêu cầu tích hợp cross-site hợp lệ; **tăng nhu cầu** kiểm tra token đúng cách |
| **Tiền tố `__Host-`** | Tên cookie bắt đầu bằng `__Host-`, phải có `Secure`, `Path=/`, **không có `Domain`** trong trình duyệt hỗ trợ | Ngăn subdomain đặt cookie tiền tố đó cho host cha bằng cách dùng `Domain` |

**Ví dụ cookie CSRF** cho frontend chạy cùng host, cần đọc token bằng JavaScript:

~~~http
Set-Cookie: __Host-XSRF-TOKEN=<signed-token>; Path=/; Secure; SameSite=Lax
~~~

Cookie ví dụ **không có `HttpOnly`**, vì SPA sẽ đọc giá trị để đưa vào `X-XSRF-TOKEN`. Đây **không phải cookie xác thực**; cookie phiên xác thực nên có `HttpOnly` nếu kiến trúc cho phép:

~~~http
Set-Cookie: __Host-SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không nên cho rằng `HttpOnly=false` ở cookie CSRF làm mất toàn bộ tác dụng CSRF: token này cố ý được trang hợp lệ đọc. Nhưng điều đó nhấn mạnh yêu cầu **chống XSS**, vì script độc hại chạy trong origin đích có thể đọc token và gửi request hợp lệ.

Nếu token được render trực tiếp trong HTML/meta hoặc trả từ endpoint cùng origin, **cookie CSRF có thể đặt `HttpOnly`** tùy thiết kế; điều bắt buộc là client hợp lệ có cách chủ động đưa giá trị vào field/header. Không dựa vào việc browser tự gửi hai cookie để coi là đã double-submit.

### 5.2. Vì sao `__Host-` đáng chú ý?

Giả sử dịch vụ chính ở `app.example.com` và attacker kiểm soát `blog.example.com`.

- Với cookie tên `XSRF-TOKEN` kèm `Domain=example.com`, subdomain có thể có đường thử tiêm cookie cùng tên vào phạm vi cha.
- Với cookie tên `__Host-XSRF-TOKEN` được browser hỗ trợ, cookie bắt buộc là **host-only** và không được khai báo `Domain`; máy chủ tại `blog.example.com` không thể dùng `Domain=example.com` để ghi đè cookie `__Host-XSRF-TOKEN` thuộc `app.example.com`.
- `__Secure-` chỉ yêu cầu `Secure`, **không cấm `Domain`**; không mang đầy đủ tính chất giới hạn host của `__Host-`.

Tuy nhiên, `__Host-` **không khắc phục XSS trên chính host ứng dụng**, không tự ràng buộc token vào session và không thay việc kiểm tra HMAC. Cần xác nhận chính sách trình duyệt hỗ trợ tiền tố này trong môi trường triển khai và không để đường xử lý cũ chấp nhận thêm cookie CSRF không có tiền tố.

### 5.3. Khi ứng dụng có nhiều subdomain

Các thiết kế frontend `https://ui.example.com` và API `https://api.example.com` **khác origin** nhưng có thể **cùng site**. Các điểm cần kiểm tra:

1. Cookie host-only của `api.example.com` **không tự hiển thị cho JavaScript ở `ui.example.com`**.
2. Nếu cố mở rộng `Domain=example.com` để JavaScript frontend đọc token, phạm vi cookie được mở rộng và nguy cơ cookie injection tăng.
3. Có thể thiết kế endpoint phát CSRF token hoặc luồng BFF/proxy phía cùng origin để client nhận token mà không cần cookie chia sẻ giữa mọi subdomain.
4. Nếu cần gọi cross-origin bằng `fetch`, phải cấu hình `credentials`, CORS, cookie và request handler khớp với kiến trúc. **CORS không thay thế CSRF token**.

Mọi ứng dụng cùng site **không mặc nhiên cùng độ tin cậy**. Tránh cấp `Domain` quá rộng chỉ để giải quyết lỗi frontend không đọc được cookie.

### 5.4. Những quy tắc bổ sung

- **Cookie name:** chọn tên riêng; không sử dụng chung tên cookie CSRF với cookie xác thực hoặc một cookie do ứng dụng khác cùng host quản lý.
- **Duplicate cookies:** xử lý rõ trường hợp hai cookie CSRF trùng tên. Không dựa vào cookie đầu tiên hay cuối cùng như chứng cứ an toàn.
- **HTTPS/HSTS:** luôn dùng HTTPS ở production; triển khai HSTS phù hợp để giảm đường truy cập HTTP. Phải lưu ý proxy/reverse proxy khi phát `Secure` cookie.
- **Kiểm soát nguồn:** `Origin`/`Referer`/Fetch Metadata có thể bổ sung phòng vệ; nếu dùng, phải xử lý các trường hợp thiếu header, proxy và danh sách origin được chấp nhận một cách có chủ đích.
- **Không dùng GET để đổi trạng thái:** mặc định bộ lọc CSRF thường không yêu cầu token đối với `GET`, `HEAD`, `OPTIONS`, `TRACE`. Endpoint an toàn phải thật sự không thay đổi trạng thái.

## 6. Ứng dụng Spring Security Servlet: repository cookie và giới hạn

Spring Security Servlet cung cấp `CookieCsrfTokenRepository`. Repository này dùng cookie (mặc định thường là `XSRF-TOKEN`), còn client có thể gửi token trong header `X-XSRF-TOKEN` hoặc form parameter `_csrf` theo cấu hình. Đây là cách triển khai **cookie-based CSRF token** phổ biến cho SPA.

**Phân biệt rất rõ:** `CookieCsrfTokenRepository` **không tự thực hiện mô hình HMAC ràng buộc phiên ở mục 4**. Nếu server chỉ tải giá trị kỳ vọng từ cookie rồi so với token mà client gửi, cần đánh giá các điều kiện cookie injection và tin cậy subdomain. Muốn có **signed double-submit gắn phiên**, phải bổ sung cơ chế ký/kiểm chứng tương ứng bằng một thành phần tích hợp đúng filter chain, không chỉ đổi tên repository.

### 6.1. Cấu hình Servlet cho cookie token

Ví dụ với Spring Security 6.1+ và ứng dụng triển khai qua HTTPS:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class CookieCsrfSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        CookieCsrfTokenRepository repository =
                CookieCsrfTokenRepository.withHttpOnlyFalse();

        repository.setCookieName("__Host-XSRF-TOKEN");
        repository.setCookiePath("/");
        repository.setCookieCustomizer(cookie ->
                cookie.secure(true).sameSite("Lax"));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf.csrfTokenRepository(repository));

        return http.build();
    }
}
~~~

Ví dụ **chưa triển khai ký HMAC**. `withHttpOnlyFalse()` cho phép JavaScript phía cùng origin đọc cookie token; tên `__Host-XSRF-TOKEN` và cookie customizer nhằm giới hạn phạm vi cookie theo host trong browser hỗ trợ. Chỉ sử dụng khi ứng dụng thực sự chạy HTTPS và kiểm chứng `Set-Cookie` có đủ `Secure`, `Path=/` và **không có `Domain`**.

Trong Spring Security 6+, cơ chế **deferred token** và **BREACH protection** có thể khiến token được render trong HTML theo dạng XOR/masked, còn SPA lại đọc token **raw** từ cookie. Nếu SPA đưa giá trị raw vào header, cần cấu hình `CsrfTokenRequestHandler` phù hợp để xử lý header raw đồng thời giữ masking cho form. Ngoài ra cần đảm bảo token cookie **được cấp lại** sau login/logout, thời điểm token cũ có thể bị xóa.

### 6.2. Handler minh họa cho SPA gửi token raw qua header

Một cách tích hợp trong Spring Security Servlet 6 là dùng hai handler: XOR cho form và handler thường cho header. Đoạn dưới là **lớp tùy chỉnh của ứng dụng**, không phải class `SpaCsrfTokenRequestHandler` có sẵn trong thư viện:

~~~java
import java.util.function.Supplier;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {
    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);
        csrfToken.get(); // Tải/sinh token, bảo đảm repository có thể phát cookie.
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request, CsrfToken csrfToken) {
        boolean viaHeader = StringUtils.hasText(
                request.getHeader(csrfToken.getHeaderName()));
        return (viaHeader ? plain : xor)
                .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Cấu hình handler này trong chain cùng repository:

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(repository)
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
~~~

Đoạn `.csrf(...)` thứ hai là **phần thay thế** đoạn `.csrf(...)` trong cấu hình trước, không gọi cả hai. Khi viết ứng dụng thật, cần xác minh phiên bản Spring Security và chính sách phát lại CSRF token sau xác thực. Không được dùng handler trên để cho phép “bỏ qua HMAC”: nó chỉ giải quyết **cách đọc token raw/masked**.

Ví dụ frontend đọc cookie và gửi token:

~~~javascript
function readCookie(name) {
  const part = document.cookie.split("; ").find(v =>
    v.startsWith(encodeURIComponent(name) + "="));
  return part ? decodeURIComponent(part.split("=").slice(1).join("=")) : null;
}

const token = readCookie("__Host-XSRF-TOKEN");
if (!token) {
  throw new Error("Chưa có CSRF token; cần tải lại token");
}

await fetch("/api/preferences", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-XSRF-TOKEN": token
  },
  body: JSON.stringify({ theme: "dark" })
});
~~~

Phía server phải có endpoint chấp nhận JSON theo ví dụ; `readCookie` chỉ là phần minh họa, code production còn cần xử lý giá trị cookie/encoding và vòng đời token. Dù token cookie được JS đọc, cookie **xác thực** nên duy trì `HttpOnly`.

### 6.3. Nếu yêu cầu signed double-submit thực sự

Một lớp ký và kiểm chứng HMAC như `SignedDoubleSubmitTokens` ở mục 4 phải được tích hợp trước xử lý nghiệp vụ, theo ngữ cảnh xác thực/phiên tin cậy. Hai lựa chọn thiết kế thường gặp:

- **Custom CSRF repository/filter integration:** phát token ký, nạp cookie, xác minh chữ ký và ràng buộc phiên cho từng request thuộc phạm vi CSRF; đảm bảo filter của Spring Security vẫn thực hiện kiểm tra token đúng cách.
- **Cơ chế bảo vệ CSRF riêng được kiểm chứng toàn diện:** chỉ dùng khi thật sự cần và có thiết kế chuỗi filter, xử lý lỗi, endpoint login/logout, testing đầy đủ.

Không chỉ thêm hàm HMAC vào controller của một vài endpoint, vì có thể bỏ lọt POST khác, login/logout hoặc những phương thức như `PATCH` và `DELETE`. Tương tự, đặt một token ký trong cookie rồi dùng repository mặc định **không có nghĩa** server đã tự động xác minh chữ ký đó. Phải có **bước kiểm chứng HMAC trong code thực thi**.

Nếu ứng dụng đã dùng session phía server, `HttpSessionCsrfTokenRepository` (synchronizer token) thường là lựa chọn đơn giản, dễ kiểm chứng hơn việc tự xây signed double-submit.

## 7. Ứng dụng Reactive/WebFlux: cùng mô hình, API khác

Với Spring Security Reactive, thành phần tương ứng với `CookieCsrfTokenRepository` là `CookieServerCsrfTokenRepository`. Nó hỗ trợ token CSRF lưu bằng cookie, còn `CsrfWebFilter` bảo vệ các request theo cấu hình `ServerHttpSecurity`.

Cấu hình cơ bản minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

@Configuration
class ReactiveCsrfConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CookieServerCsrfTokenRepository repository =
                CookieServerCsrfTokenRepository.withHttpOnlyFalse();

        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .csrf(csrf -> csrf.csrfTokenRepository(repository))
            .build();
    }
}
~~~

Đây cũng là **repository cookie thông thường**, **không phải signed session-bound double-submit** theo định nghĩa mục 4. Nếu cần tên cookie có tiền tố `__Host-`, `SameSite` và cookie scope đặc thù, hãy kiểm tra API cấu hình của phiên bản `CookieServerCsrfTokenRepository` đang dùng và giá trị `Set-Cookie` thực tế. Không mặc định cấu hình Servlet và Reactive có cùng method setter.

Trong WebFlux, token có thể được quản lý dưới dạng reactive `Mono<CsrfToken>` và cơ chế request handler có thể xử lý biểu diễn token khác nhau theo phiên bản. Khi frontend gửi token đọc từ cookie qua header, cần xác minh **request handler được cấu hình để tiếp nhận chính biểu diễn đó**. Không tắt CSRF chỉ vì token trên SPA chưa được tạo/tải hoặc header không khớp.

Nếu ứng dụng Reactive đã dùng `WebSession` và không cần cookie token đọc từ JavaScript, giải pháp synchronizer token qua `WebSessionServerCsrfTokenRepository` có thể phù hợp hơn. **Chọn kiến trúc theo cơ chế credential của trình duyệt**, không theo việc backend dùng Servlet hay WebFlux.

## 8. Kiểm thử an toàn theo mô hình tấn công

Kiểm thử cần xác minh **tính chất bảo mật**, thay vì chỉ chứng minh một POST có token trả HTTP 200. Các bài thử nên chạy trong môi trường được phép và qua security filter chain thật.

### 8.1. Ma trận tình huống

| Tình huống | Naive double-submit | Signed + session-bound double-submit |
|---|---|---|
| Không có cookie CSRF, có token header/form | Từ chối | Từ chối |
| Có cookie CSRF, không có token header/form | Từ chối | Từ chối |
| Cookie và header khác nhau | Từ chối | Từ chối |
| Cookie và header đều là chuỗi attacker tự chọn | **Có thể vượt bước so sánh** nếu cookie bị tiêm và server chọn nó | Từ chối vì HMAC không hợp lệ |
| Token có HMAC hợp lệ của phiên attacker được đưa vào phiên nạn nhân | Mẫu naive không kiểm tra phiên | Từ chối vì HMAC không khớp binding phiên nạn nhân |
| Token hợp lệ bị sửa một byte | Có thể vượt nếu attacker sửa được cả hai bản sao | Từ chối vì HMAC sai |
| Session hết hạn/thay binding, gửi token cũ | Phụ thuộc cơ chế ứng dụng; không tự bảo đảm đúng phiên | Từ chối nếu binding được lấy từ session hiện tại |
| Có token hợp lệ nhưng người dùng thiếu quyền | Vẫn phải từ chối ở tầng phân quyền | Vẫn phải từ chối ở tầng phân quyền |
| Attacker có XSS ngay trong origin đích | Có thể đọc/sử dụng token | HMAC cũng không ngăn script cùng origin gửi request hợp lệ |

Đối với Servlet, `MockMvc` + `spring-security-test` có các helper `csrf()` và `csrf().useInvalidToken()` để kiểm tra hành vi filter thông thường. Tuy nhiên, **helper `csrf()` không chứng minh một custom signed double-submit đã kiểm tra HMAC/session binding**: cần test tích hợp riêng cho token/cookie thật và lớp kiểm chứng.

Ở WebFlux, `WebTestClient` với `springSecurity()` và `csrf()` có mục đích tương tự: xác minh behavior filter, sau đó thêm test ràng buộc chữ ký/phiên cho implementation tùy biến.

### 8.2. Các ca test tối thiểu cho lớp HMAC minh họa

~~~java
byte[] key = loadSecretFromTrustedConfiguration();
SignedDoubleSubmitTokens tokens = new SignedDoubleSubmitTokens(key);

String tokenA = tokens.issue("trusted-session-A");

// Hợp lệ: hai bản sao khớp và thuộc phiên A.
assert tokens.verify("trusted-session-A", tokenA, tokenA);

// Thiếu hoặc sai bản sao.
assert !tokens.verify("trusted-session-A", tokenA, null);
assert !tokens.verify("trusted-session-A", tokenA, "attacker-value");

// Token A không hợp lệ cho phiên B.
assert !tokens.verify("trusted-session-B", tokenA, tokenA);

// Token có HMAC bị sửa không được chấp nhận.
String forged = tokenA.substring(0, tokenA.length() - 1) + "!";
assert !tokens.verify("trusted-session-A", forged, forged);
~~~

Đây là **minh họa assertion**, không phải một test file độc lập vì `loadSecretFromTrustedConfiguration()` phụ thuộc hệ thống quản lý bí mật. Với JUnit thực tế, dùng `assertTrue`/`assertFalse` thay cho Java `assert` khi cần bảo đảm assertion luôn chạy. Quan trọng hơn, phải kiểm tra luồng HTTP qua browser/cookie và security filter thực tế.

### 8.3. Kiểm tra cookie injection trong trình duyệt

Để đánh giá khả năng khai thác thực tế:

1. Quan sát `Set-Cookie` từ ứng dụng: tên, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`.
2. Xem request thực tế có gửi **cookie xác thực** hay không trong tình huống cross-site; không giả định cookie luôn được gửi.
3. Kiểm tra cookie trùng tên: trình duyệt gửi bao nhiêu bản sao và server chọn bản nào.
4. Xác nhận cookie `__Host-` được trình duyệt chấp nhận đúng điều kiện và subdomain không thể đặt cookie cùng tên cho host cha.
5. Dùng token có ký hợp lệ từ **phiên A**, tạo request cùng token nhưng có **credential phiên B**; server phải từ chối.
6. Thử thao tác sau logout/login lại, hết hạn session, đổi khóa HMAC, chuyển node server; xác minh không có đường fallback bỏ qua kiểm chứng.

Các HTTP client như cURL/Postman có thể chủ động đặt giá trị `Cookie` tùy ý, nên chúng hữu ích cho kiểm thử logic server nhưng **không tự chứng minh** browser nạn nhân sẽ gửi cookie như vậy từ website ngoài.

## 9. Chẩn đoán các xung đột thường gặp khi triển khai

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| SPA đọc `document.cookie` không thấy CSRF token | Cookie `HttpOnly`, chưa được phát, sai host/path hoặc cookie bị chặn | Kiểm tra kênh phát token, request làm phát token và `Set-Cookie` |
| SPA đã gửi `X-XSRF-TOKEN` nhưng bị `403` | Token raw không tương thích XOR handler; token cũ sau login; header sai tên | Đối chiếu request handler, trạng thái token và vòng đời xác thực |
| Token hợp lệ ở node A nhưng lỗi ở node B | Khóa HMAC khác nhau hoặc session binding không đồng bộ | Đồng bộ khóa bí mật và quản lý phiên |
| Đổi `SameSite=Strict` làm lỗi luồng tích hợp | Cookie bị giới hạn trong cross-site navigation | Xem lại yêu cầu luồng, cookie xác thực và chiến lược tích hợp an toàn |
| Cookie `__Host-` không được lưu | Thiếu `Secure`, thiếu `Path=/`, có `Domain` hoặc không dùng HTTPS | Kiểm tra chính xác `Set-Cookie` và điều kiện của browser |
| Hai cookie CSRF trùng tên | Nhiều ứng dụng/subdomain/path cùng đặt cookie hoặc cookie injection | Tách tên, host scope, quản lý cookie cũ và parse an toàn |
| Token của account A hợp lệ ở account B | Chữ ký không ràng buộc phiên hoặc binding chọn sai | Ký theo binding phiên đã xác thực; test hoán đổi token |
| Vô hiệu hóa CSRF làm POST hoạt động | CSRF token chưa gửi/không khớp, hoặc chain cấu hình thiếu chính xác | Sửa luồng phát và xác minh token; chỉ miễn phạm vi thật sự không dùng credential tự gửi |

Khi endpoint không dựa trên credential trình duyệt tự gửi (ví dụ webhook dùng chữ ký độc lập hoặc API chỉ nhận bearer header do client chủ động đặt), có thể cân nhắc phạm vi bảo vệ CSRF riêng. Quyết định phải dựa trên **toàn bộ cách endpoint xác thực**, không phải vì endpoint được gọi là REST/JWT/stateless.

## 10. Bài tập tự đánh giá

**Tình huống 1.** Server nhận `Cookie: XSRF-TOKEN=abc` và `X-XSRF-TOKEN: abc`, sau đó cho phép đổi mật khẩu. Có thể kết luận đây là triển khai CSRF an toàn không?

**Đáp án:** Chưa thể. Hai bản sao giống nhau chỉ chứng minh equality. Cần biết cookie có bị tiêm được không, server có xác minh nguồn gốc và HMAC ràng buộc phiên hay không, bên cạnh xác thực/phân quyền nghiệp vụ.

**Tình huống 2.** Mỗi user đều nhận token ngẫu nhiên ký HMAC, nhưng chữ ký không chứa thông tin phiên. Attacker lấy token có ký của mình, đặt vào cả cookie và hidden field của nạn nhân. Có rủi ro gì?

**Đáp án:** Token của attacker có chữ ký hợp lệ ở mọi phiên nếu server chỉ xác minh HMAC theo nonce. Cần ký thêm binding phiên do server xác định để token từ phiên attacker không dùng được ở phiên nạn nhân.

**Tình huống 3.** JavaScript cần đọc token CSRF từ cookie `__Host-XSRF-TOKEN`, trong khi cookie xác thực `__Host-SESSION` phải tránh bị đọc bởi JS. Nên dùng `HttpOnly` thế nào?

**Đáp án:** Cookie xác thực thường cần `HttpOnly`; cookie CSRF được SPA đọc thì không thể đặt `HttpOnly` mà vẫn đọc qua `document.cookie`. Token CSRF không phải credential đăng nhập; tính đúng đắn nằm ở bước server so khớp và xác minh chữ ký/binding.

**Tình huống 4.** Frontend ở `ui.example.com`, API ở `api.example.com`. Nhóm muốn chuyển cookie CSRF sang `Domain=example.com` để frontend đọc được. Có hệ quả nào?

**Đáp án:** Mở rộng miền cookie làm tăng phạm vi nhận cookie, có thể mở đường cookie injection từ subdomain ít tin cậy; mất lợi thế host-only/`__Host-`. Nên cân nhắc luồng phát token qua endpoint/BFF cùng origin hoặc mô hình cookie chặt chẽ hơn, cùng bảo vệ CSRF phù hợp.

**Tình huống 5.** Dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` trong Spring Security và gọi đó là “signed double-submit”. Nhận định đúng không?

**Đáp án:** Không. Repository cookie tiêu chuẩn **không tự thêm HMAC ràng buộc phiên**. Cần tách rõ repository token bằng cookie và giải pháp signed session-bound có cơ chế xác minh chữ ký riêng.

## Tổng kết

**Double-submit cookie** yêu cầu client gửi token qua **hai kênh**: cookie trình duyệt tự mang và giá trị do trang hợp lệ chủ động gửi trong header/form. Bản tối giản chỉ so hai chuỗi có thể yếu trước **cookie injection** và token dùng chéo phiên. **Signed double-submit cookie ràng buộc phiên** kiểm tra thêm HMAC do server ký bằng khóa bí mật theo một binding đáng tin cậy của phiên hiện tại, khiến token attacker tự đặt hoặc lấy từ phiên khác không còn được chấp nhận.

Để triển khai trong **Spring Security Servlet** hoặc **Reactive**, cần chọn đúng repository/handler, bảo đảm token được phát và gửi hợp lệ, đồng thời kiểm soát `Domain`, `Path`, `Secure`, `SameSite`, `HttpOnly`, tiền tố `__Host-` và cookie trùng tên. `CookieCsrfTokenRepository`/`CookieServerCsrfTokenRepository` là công cụ cho token dựa trên cookie; khi cần **HMAC ràng buộc phiên**, phải triển khai và kiểm thử rõ bước xác minh này. Các lớp bổ sung như CORS, CSP, HSTS, security headers, HTTP firewall, quản lý session và chống XSS giúp củng cố bảo vệ tổng thể nhưng không thay yêu cầu kiểm chứng CSRF trên những request làm thay đổi trạng thái.
