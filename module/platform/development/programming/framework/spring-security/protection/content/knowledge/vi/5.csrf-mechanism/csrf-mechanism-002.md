# Vai trò của thông tin xác thực được trình duyệt tự gửi

## Mục tiêu học tập

Sau bài học trong chương **Cơ chế CSRF**, người học có thể:

- Giải thích vì sao **thông tin xác thực được trình duyệt tự động đính kèm** (*automatically included credentials*, đôi khi gọi là *ambient authority*) là tiền đề của nhiều cuộc tấn công CSRF.
- Phân biệt **cookie phiên**, **cookie chứa access token/JWT**, thông tin xác thực HTTP do trình duyệt lưu, chứng chỉ TLS phía khách và **bearer token được mã ứng dụng chủ động gắn vào header**.
- Dự đoán khi nào cookie được gửi dựa trên `Domain`, `Path`, `Secure`, `SameSite`, site/origin và loại yêu cầu (điều hướng, form, `fetch`).
- Phân tích tại sao server nhận diện đúng phiên đăng nhập vẫn có thể xử lý một thao tác **không do người dùng chủ ý thực hiện**.
- Đánh giá nhu cầu phòng vệ CSRF cho Spring Security **Servlet** và **Reactive**, bao gồm trường hợp API được mô tả là “stateless”, và kiểm thử các giả định trên trình duyệt.

## 1. Điểm cốt lõi: trình duyệt có thể mang quyền của người dùng vào yêu cầu không do họ chủ động gửi

Khi một người dùng đăng nhập vào trang web, ứng dụng thường cần nhận diện họ ở những yêu cầu tiếp theo. Cách phổ biến nhất là máy chủ phát một **cookie phiên**. Từ đó, khi trình duyệt gửi request đến đích phù hợp, nó tự quyết định cookie nào cần đính kèm theo các quy tắc cookie; mã của trang đang hiển thị **không nhất thiết phải gọi thao tác “đăng nhập” hay đọc giá trị cookie**.

Ví dụ minh họa:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=None
~~~

Khi một request được trình duyệt gửi đến `https://account.example` trong bối cảnh mà cookie trên được phép gửi, request có thể mang:

~~~http
POST /profile/email HTTP/1.1
Host: account.example
Cookie: JSESSIONID=opaque-session-id
Content-Type: application/x-www-form-urlencoded

email=somebody@example.test
~~~

Máy chủ tra phiên tương ứng và nhận ra người dùng đã đăng nhập. **Nhận diện được phiên không chứng minh người dùng cố ý đổi email.** Đó chính là khoảng trống bảo mật mà kiểm tra chống CSRF cần lấp đầy.

> **Cốt lõi của CSRF:** Kẻ tấn công lợi dụng việc trình duyệt tự mang thông tin xác thực đến ứng dụng đích, khiến máy chủ dễ nhầm một request do bên thứ ba kích hoạt với một thao tác hợp lệ từ chính người dùng.

Giá trị cookie ví dụ chỉ mang tính minh họa, không phải một session ID thực tế. Việc đặt `SameSite=None` ở đây nhằm cho thấy một trường hợp có thể gửi cookie cross-site; trình duyệt vẫn có thể áp dụng chính sách hạn chế cookie bên thứ ba.

## 2. “Thông tin xác thực được tự gửi” nghĩa là gì?

Ta phân biệt hai hành vi:

1. **Tự đính kèm:** Trình duyệt nắm một credential từ trước và có thể thêm nó vào request đến đích phù hợp mà trang nguồn không cần đọc credential đó.
2. **Chủ động đính kèm:** Mã ứng dụng phải lấy token từ một nguồn và đặt rõ ràng vào request, chẳng hạn header `Authorization`.

Với hành vi thứ nhất, một trang khác có thể **kích hoạt request** bằng form, điều hướng hoặc cơ chế trình duyệt được phép. Nếu credential vẫn được tự gửi và không có biện pháp xác minh mục đích của request, CSRF có thể xuất hiện.

Với hành vi thứ hai, một trang độc hại thường **không có token** và không thể chỉ dùng form HTML để yêu cầu trình duyệt tự gắn header bearer của ứng dụng đích. Điều này thường làm giảm nguy cơ **CSRF truyền thống dựa vào credential tự động**, dù ứng dụng vẫn phải đối phó với XSS, lộ token và sai cấu hình khác.

### 2.1. Phân loại các cơ chế xác thực thường gặp

| Cơ chế | Ai đưa credential vào request? | Liên quan đến CSRF |
|---|---|---|
| **Cookie phiên** (`JSESSIONID`, `SESSION`, hoặc tên cấu hình khác) | Trình duyệt tự chọn và gửi theo quy tắc cookie. | **Có nguy cơ** khi cookie được gửi trong request do bên thứ ba kích hoạt và endpoint thiếu bảo vệ. |
| **JWT/access token trong cookie** | Trình duyệt tự gửi cookie; server giải mã/kiểm tra token. | **Vẫn có nguy cơ** dù không có session lưu phía server: cookie là credential tự gửi. |
| **HTTP Basic đã được trình duyệt lưu/ghi nhớ** | Trình duyệt *có thể* tự thêm thông tin xác thực cho phạm vi bảo vệ thích hợp, phụ thuộc cách lưu và hành vi trình duyệt. | **Cần đánh giá**; không thể mặc định chỉ có cookie mới gây CSRF. |
| **HTTP Negotiate/Integrated Authentication** | Trình duyệt và hệ điều hành *có thể* tự tham gia xác thực theo chính sách cấu hình. | **Cần đánh giá**, đặc biệt trong môi trường nội bộ. |
| **Chứng chỉ TLS phía client (mTLS)** | Trình duyệt có thể trình chứng chỉ phù hợp trong bắt tay TLS theo cấu hình/chấp thuận. | **Có thể liên quan** nếu nguồn khác kích hoạt được request mang danh tính client. |
| **Bearer token trong `Authorization` do ứng dụng tự thêm** | JavaScript/client ứng dụng chủ động thiết lập header. | **Thông thường không dễ bị CSRF kiểu cookie** nếu trình duyệt không tự bổ sung token và không có đường xác thực tự động khác. |
| **Token chỉ nằm trong bộ nhớ ứng dụng hoặc `localStorage`** | Bản thân trình duyệt không tự chuyển token này thành header cho mọi request. | **Không tự tạo điều kiện CSRF kiểu cookie**; vẫn có rủi ro XSS và lộ token. |

**JWT, session và “stateless” mô tả cách xác thực hoặc quản lý trạng thái; chúng không quyết định cookie có được gửi tự động hay không.** Phải xem token được **vận chuyển bằng cách nào**.

Lưu ý rằng `localStorage` không có cờ `HttpOnly`. Nếu mã chạy trái phép trong origin của ứng dụng (XSS), token lưu ở đó có thể bị truy cập. Do đó, việc lựa chọn lưu bearer token ở client phải cân nhắc cả mô hình đe dọa ngoài CSRF.

## 3. Ví dụ: thông tin xác thực hợp lệ nhưng thao tác không hợp lệ về ý định

Giả sử `https://account.example` có form đổi địa chỉ email:

~~~http
POST /profile/email
Content-Type: application/x-www-form-urlencoded

email=new-address@example.test
~~~

Người dùng đã đăng nhập trên `account.example`. Kẻ tấn công điều khiển trang `https://offer.attacker.test`, nơi đặt một form:

~~~html
<form id="change-email" method="post"
      action="https://account.example/profile/email">
  <input type="hidden" name="email" value="attacker@example.test">
</form>
<script>
  document.getElementById("change-email").submit();
</script>
~~~

Form này không chứa mật khẩu hay cookie của nạn nhân. Trang tấn công cũng không nhất thiết có quyền đọc phản hồi từ `account.example`. Nhưng nếu trình duyệt **tự gửi cookie hợp lệ** kèm request, server sẽ nhận được hai tín hiệu:

- **Cookie/session:** “Đây là request gắn với phiên của người dùng A.”
- **Nội dung form:** “Hãy đổi email thành địa chỉ B.”

Nếu máy chủ chỉ dựa vào phiên để quyết định xử lý, nó có thể thực hiện yêu cầu sai. **Thẻ `Cookie` chỉ xác nhận ngữ cảnh đăng nhập; nó không thể hiện sự đồng thuận của người dùng với hành động đang thực hiện.**

~~~mermaid
sequenceDiagram
    actor U as Người dùng A
    participant B as Trình duyệt
    participant W as Trang do attacker kiểm soát
    participant S as Ứng dụng account.example

    U->>S: Đăng nhập hợp lệ
    S-->>B: Set-Cookie: session
    U->>W: Mở trang ngoài
    W-->>B: HTML form tự submit
    B->>B: Áp dụng Domain, Path, Secure, SameSite
    alt Cookie được phép gửi
        B->>S: POST /profile/email + Cookie phiên
        S->>S: Xác thực ra người dùng A
        alt Không kiểm tra CSRF hiệu quả
            S-->>B: Đổi email cho tài khoản A
        else Kiểm tra CSRF hợp lệ
            S-->>B: Từ chối request thiếu/sai token
        end
    else Cookie bị chặn theo chính sách
        B->>S: POST /profile/email không có cookie phiên
        S-->>B: Không xử lý dưới danh tính A
    end
~~~

Điểm quyết định trong sơ đồ là bước **trình duyệt chọn credential và máy chủ chấp nhận thao tác**. Form chỉ là phương tiện kích hoạt request; trong môi trường khác, trang tấn công có thể dùng điều hướng, tải tài nguyên hoặc API trình duyệt, tùy phương thức HTTP mà endpoint chấp nhận.

## 4. Trình duyệt quyết định gửi cookie như thế nào?

Không phải cookie nào cũng được gửi trên mọi request. Khi phân tích CSRF, cần kiểm tra các điều kiện cụ thể:

| Thuộc tính / chính sách | Tác động đến việc gửi cookie | Tác động đối với CSRF |
|---|---|---|
| **Tên miền (host-only / `Domain`)** | Cookie không có `Domain` thường chỉ gửi đến đúng hostname đã đặt; cookie có `Domain=example.com` có thể gửi đến hostname đó và các subdomain phù hợp. | Xác định endpoint nào có thể nhận cookie. |
| **`Path`** | Giới hạn đường dẫn request có thể nhận cookie. | Giúp chọn cookie theo đường dẫn, **không phải ranh giới bảo mật đủ mạnh** để tách các ứng dụng cùng origin. |
| **`Secure`** | Chỉ gửi cookie qua kết nối an toàn thích hợp, thông thường HTTPS. | Bảo vệ việc truyền cookie; **không tự chống CSRF**. |
| **`HttpOnly`** | Ngăn JavaScript thông thường đọc cookie qua `document.cookie`. | Giảm một số nguy cơ lộ cookie do XSS; **không ngăn trình duyệt gửi cookie**. |
| **`SameSite`** | Kiểm soát gửi cookie trong một số ngữ cảnh cross-site. | Trực tiếp ảnh hưởng khả năng khai thác các yêu cầu giả mạo. |
| **Thời hạn và trạng thái cookie** | Cookie đã hết hạn, bị xóa, bị chặn hoặc không còn hợp lệ sẽ không cung cấp phiên xác thực. | Một request có thể được gửi nhưng không được xử lý dưới danh tính nạn nhân. |
| **Chính sách cookie của trình duyệt** | Trình duyệt có thể chặn/giới hạn cookie bên thứ ba hoặc áp dụng cookie phân vùng. | Kết quả phụ thuộc trình duyệt và ngữ cảnh điều hướng cụ thể. |

### 4.1. Host-only và Domain có ý nghĩa gì?

Ví dụ:

~~~http
Set-Cookie: SESSION=abc; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: SHARED=xyz; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giả sử hai cookie được đặt từ một hostname thuộc `example.com` phù hợp với quyền đặt domain:

- `SESSION` không có `Domain`: cookie **host-only**, chỉ gửi tới hostname đã đặt cookie.
- `SHARED` có `Domain=example.com`: có thể được gửi cho `example.com` và các subdomain phù hợp, theo những thuộc tính khác.
- Một trang nguồn trên `other.example.com` có thể khác **origin** với `account.example.com` nhưng cùng **site**. Nếu nó kích hoạt request tới `account.example.com`, việc cookie có được gửi vẫn do hostname đích và các quy tắc cookie quyết định.

Không được đánh đồng **“trang nguồn có đọc được cookie không?”** với **“trình duyệt có gửi cookie cho hostname đích không?”**. Trang nguồn bên ngoài không cần đọc giá trị cookie để khai thác cơ chế tự gửi.

### 4.2. SameSite: site không phải origin

**Origin** được xác định bởi *scheme + hostname + port*; ví dụ `https://app.example.com` và `https://api.example.com` là hai origin khác nhau.

**Site** theo cách phân loại hiện đại là *scheme + registrable domain* (nếu có). Vì vậy hai subdomain cùng đăng ký miền và cùng scheme thường là **same-site nhưng cross-origin**. Đây là lý do `SameSite` không nên được hiểu là “chỉ trang cùng origin mới gửi được cookie”.

| Cấu hình `SameSite` | Hành vi liên quan đến request cross-site |
|---|---|
| `Strict` | Cookie không được gửi trong ngữ cảnh cross-site. |
| `Lax` | Thông thường không gửi cùng **cross-site form POST**; có thể được gửi trong **điều hướng cấp cao bằng phương thức an toàn**, chẳng hạn người dùng đi theo liên kết `GET`. |
| `None; Secure` | Cookie đủ điều kiện được gửi trong nhiều ngữ cảnh cross-site, tùy chính sách cookie hiện hành của trình duyệt. |

Ví dụ cùng một phiên đăng nhập nhưng hành vi khác nhau:

- Site ngoài gửi **form POST** và cookie có `SameSite=Lax`: cookie thường bị loại khỏi request cross-site.
- Site ngoài tạo **điều hướng cấp cao bằng GET** và cookie có `SameSite=Lax`: cookie có thể được gửi.
- Site ngoài tạo **form POST** và cookie có `SameSite=None; Secure`: cookie có thể được gửi nếu các chính sách khác cho phép.
- Trang tại subdomain cùng site kích hoạt form POST đến một subdomain khác: `SameSite=Lax` hoặc `Strict` không nhất thiết chặn, vì ngữ cảnh **có thể là same-site**; còn phải xem cookie có khớp hostname đích không.

Một số trình duyệt có ngoại lệ tương thích khi cookie **không khai báo** `SameSite`, nhất là cookie vừa được tạo. Vì vậy không suy luận bằng tên thuộc tính đơn thuần; hãy xác nhận chính sách cookie thực tế và thử trên trình duyệt mục tiêu.

**Hệ quả quan trọng:** `GET` không được thay đổi trạng thái, kể cả khi cookie đã dùng `SameSite=Lax`. Một thao tác xóa/đổi dữ liệu qua `GET` vẫn có thể chịu CSRF do điều hướng liên trang.

### 4.3. Cookie trong form, điều hướng và fetch khác nhau ra sao?

**Điều hướng và HTML form:** Trình duyệt có thể gửi request tới một origin khác. Nếu quy tắc cookie cho phép, cookie tương ứng với **đích request** có thể được đính kèm. Không cần trang tấn công biết cookie, và form HTML đơn giản thường không cần cơ chế CORS preflight.

**JavaScript `fetch`:** Có thêm tùy chọn `credentials` ảnh hưởng đến việc đính kèm credential:

~~~javascript
// Cùng origin: fetch mặc định dùng credentials: "same-origin".
fetch("/profile", { method: "GET" });

// Gọi cross-origin: chỉ cân nhắc gửi cookie khi khai báo "include",
// nhưng vẫn chịu SameSite và các chính sách cookie của trình duyệt.
fetch("https://api.example.com/profile", {
  method: "GET",
  credentials: "include"
});

// Không gửi credential theo cơ chế credentials của fetch.
fetch("/public", {
  method: "GET",
  credentials: "omit"
});
~~~

`credentials: "include"` **không vô hiệu hóa** `SameSite`, `Secure` hay chính sách chặn cookie bên thứ ba. Đổi lại, `credentials: "same-origin"` trong `fetch` không có nghĩa là *mọi* cơ chế gửi request của trình duyệt đều không mang cookie cross-site: **form HTML và điều hướng có quy tắc riêng**.

CORS kiểm soát việc JavaScript cross-origin được truy cập phản hồi và một số request cần preflight. **Không đọc được phản hồi không đồng nghĩa request không được gửi**, càng không đồng nghĩa server chưa thực hiện thao tác. Đây là điểm cần kiểm tra khi điều tra CSRF.

## 5. Khi credential tự gửi trở thành lỗ hổng CSRF

Để từ hiện tượng “trình duyệt tự gửi credential” hình thành một CSRF có tác động, chuỗi điều kiện thường là:

1. Người dùng có credential hợp lệ mà trình duyệt có thể tự mang đến ứng dụng.
2. Bên thứ ba có thể kích hoạt một request mà server chấp nhận về **phương thức, URL và định dạng dữ liệu**.
3. Credential được gửi vào **đúng request đó** theo chính sách trình duyệt.
4. Request thực hiện thao tác có tác động (đổi mật khẩu, cập nhật email, thanh toán, xóa nội dung, liên kết tài khoản…).
5. Server chấp nhận request chỉ dựa trên xác thực và các kiểm tra nghiệp vụ, **thiếu một cơ chế chống CSRF có hiệu lực**.

Thiếu một trong các điều kiện trên có thể làm đường tấn công cụ thể thất bại. Chẳng hạn:

- Trình duyệt gửi form nhưng loại bỏ cookie, server trả về trang đăng nhập.
- Credential được gửi nhưng server yêu cầu **CSRF token** hợp lệ, request bị từ chối.
- Trang ngoài không thể tạo yêu cầu hợp lệ với header hoặc định dạng mà endpoint thực sự chấp nhận.
- Endpoint không làm thay đổi trạng thái, nên đường request đang xét không tạo ra tác động CSRF theo nghĩa thay đổi hành động của tài khoản.

Vì vậy, **thông tin xác thực tự gửi là điều kiện thuận lợi rất quan trọng, nhưng tự nó không chứng minh tồn tại lỗ hổng**. Phải quan sát endpoint và cơ chế từ chối request.

### 5.1. Vì sao HttpOnly không giải quyết được vấn đề?

`HttpOnly` ngăn JavaScript của trang đọc cookie qua API thông thường. Một attacker trên website khác vốn đã không được đọc cookie của `account.example` do ràng buộc origin. Nhưng cả hai điều đó **không cấm trình duyệt gửi cookie đến `account.example`** khi request phù hợp quy tắc cookie.

Nói cách khác:

- **Bí mật của credential:** kẻ tấn công có biết giá trị cookie hay không?
- **Đường vận chuyển credential:** trình duyệt có tự gắn cookie vào request được kích hoạt từ nơi khác hay không?
- **Quyền thực hiện hành động:** server có kiểm tra request đến từ luồng hợp lệ ngoài việc xác thực cookie hay không?

Chống CSRF cần quan tâm hai câu hỏi sau; `HttpOnly` chủ yếu hỗ trợ câu hỏi đầu tiên.

### 5.2. Cookie chứa JWT có khác cookie phiên không?

Xét hai cách tổ chức backend:

~~~text
(A) Cookie: JSESSIONID=opaque-id
    Server: tìm SecurityContext / phiên tương ứng

(B) Cookie: AUTH_JWT=signed-token
    Server: xác minh chữ ký, hạn dùng và thông tin quyền trong JWT
~~~

Cách (A) thường dựa vào dữ liệu phiên phía server. Cách (B) có thể xác thực không cần lưu phiên trên server. Nhưng với **trình duyệt**, cả hai đều là cookie được tự gửi. Nếu dùng chúng để xác thực yêu cầu thay đổi dữ liệu, **cả hai vẫn phải được đánh giá CSRF**.

Ngược lại:

~~~http
Authorization: Bearer eyJ...
~~~

nếu header này chỉ xuất hiện vì **mã client hợp lệ tự đặt vào request**, một form ở website ngoài không thể tự động khiến trình duyệt gắn bearer token đó. Điều kiện then chốt là **không có phương thức xác thực tự động khác cùng được server chấp nhận**.

## 6. Liên hệ trực tiếp với Spring Security: Servlet và Reactive

Module **SPRING_SECURITY_HTTP_PROTECTION** nghiên cứu nhiều lớp phòng vệ HTTP và trình duyệt: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Riêng đối với CSRF, câu hỏi đầu tiên khi thiết kế cấu hình là: **ứng dụng xác thực các request xuất phát từ trình duyệt bằng credential nào, và credential đó được gắn tự động hay chủ động?**

### 6.1. Spring Security Servlet

Với ứng dụng Spring MVC/Servlet dùng `formLogin()` và phiên HTTP:

1. Người dùng đăng nhập thành công.
2. Security context gắn với người dùng có thể được lưu/truy xuất thông qua cơ chế phiên và `SecurityContextRepository` theo cấu hình.
3. Trình duyệt mang cookie phiên (thường là `JSESSIONID` trong môi trường servlet) vào các request phù hợp.
4. Spring Security có **`CsrfFilter`** để kiểm tra CSRF token cho các request cần bảo vệ; mặc định, các phương thức không được coi là an toàn như `POST`, `PUT`, `PATCH`, `DELETE` thuộc diện kiểm tra.

Cấu hình minh họa giữ cơ chế CSRF mặc định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        // Không vô hiệu hóa CSRF: cấu hình mặc định vẫn áp dụng.
        return http.build();
    }
}
~~~

Ví dụ giả định có các dependency Spring Security Servlet phù hợp. Khi người dùng đang đăng nhập và gửi một POST thay đổi dữ liệu **không có CSRF token hợp lệ**, request thường bị từ chối với `403 Forbidden` trước khi thực hiện hành động nghiệp vụ. Cấu hình ứng dụng thực tế có thể thay đổi nơi lưu hoặc cách gửi token.

### 6.2. Spring Security Reactive/WebFlux

Với WebFlux, luồng bảo mật thường sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và `CsrfWebFilter`. Trình duyệt vẫn có thể dùng cookie phiên (`SESSION` hoặc tên khác tùy cách cấu hình resolver), nhưng request được xử lý bằng cơ chế reactive.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
        // CSRF vẫn được bật theo cấu hình mặc định.
    }
}
~~~

Bản chất nguy cơ **không thay đổi giữa Servlet và Reactive**: browser có thể tự gửi session cookie, còn server cần kiểm tra request thay đổi trạng thái. Sự khác nhau chủ yếu nằm ở API cấu hình, filter và cơ chế quản lý phiên/token tương ứng.

### 6.3. Khi nào cần thận trọng với câu “API đã stateless nên tắt CSRF”?

Đánh giá dựa trên **credential được chấp nhận**, không chỉ dựa trên cách ứng dụng mô tả kiến trúc:

| Trường hợp | Nhận định |
|---|---|
| Endpoint dùng session cookie sau form login | Duy trì chống CSRF cho thao tác thay đổi trạng thái. |
| Endpoint giải mã JWT từ cookie `HttpOnly` | Cookie vẫn tự gửi; cần đánh giá CSRF tương tự. |
| API chỉ chấp nhận bearer token được client đặt trong `Authorization` | Có thể không cần cơ chế chống CSRF kiểu cookie cho những endpoint này, sau khi xác nhận không nhận credential tự gửi khác. |
| Cùng một endpoint chấp nhận **cả** bearer token và session cookie | Vẫn cần bảo vệ đường xác thực qua cookie; một attacker có thể nhắm vào chính đường đó. |
| API không lưu session nhưng dùng HTTP Basic hoặc xác thực tích hợp do trình duyệt tự thực hiện | Vẫn phải xét CSRF vì server stateless không loại bỏ hành vi tự gắn credential ở client. |

Không nên dùng một câu lệnh vô hiệu hóa CSRF toàn cục chỉ vì một số endpoint nhận bearer token. Trước hết cần xác định chính xác phạm vi endpoint và mọi cơ chế xác thực mà các endpoint đó chấp nhận.

## 7. Vì sao CSRF token giải được bài toán “tự gửi”?

CSRF token là giá trị do ứng dụng cấp/kiểm tra để ràng buộc request thay đổi trạng thái với luồng hợp lệ. Về nguyên lý:

- Cookie phiên được browser **tự đính kèm**, nên attacker không cần biết cookie để khiến browser gửi nó.
- CSRF token hợp lệ phải được trang hoặc client hợp lệ **lấy và đưa vào form/header theo cách server quy định**.
- Một website ở origin khác thường không được đọc nội dung chứa token trong trang ứng dụng đích; nó cũng không thể tự tạo token hợp lệ.
- Server kiểm tra token trước khi cho phép thao tác làm thay đổi trạng thái. Có cookie hợp lệ **vẫn chưa đủ** nếu token thiếu hoặc sai.

Ví dụ form hợp lệ *sau khi ứng dụng đã đưa token được phát hành vào trang*:

~~~html
<form method="post" action="/profile/email">
  <input name="email" type="email" required>
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_CAP">
  <button type="submit">Đổi email</button>
</form>
~~~

Giá trị `TOKEN_DO_SERVER_CAP` chỉ là ký hiệu giải thích; ứng dụng phải **tạo và đưa token thực** vào form. Đối với ứng dụng dùng JavaScript, cách gửi token qua header và cách lấy token phụ thuộc vào cấu hình Spring Security, phương thức lưu token và giải pháp tích hợp phía client.

Một cookie tên `XSRF-TOKEN` **không đủ để bảo vệ nếu server chỉ kiểm tra cookie tự gửi**. Với mô hình *double-submit cookie*, client hợp lệ còn phải gửi giá trị token qua header hoặc trường form và server phải đối chiếu đúng, đồng thời bảo đảm tính toàn vẹn/ràng buộc thích hợp của token. Cách này dựa trên sự khác biệt giữa **cookie trình duyệt tự gửi** và **giá trị mà mã/trang hợp lệ chủ động gửi theo quy tắc bảo vệ**.

Spring Security cung cấp các cơ chế repository và filter tương ứng cho Servlet/Reactive; việc chọn chính sách token cụ thể thuộc phần cấu hình và kiểm thử chuyên sâu.

## 8. Phân tích request: phát hiện credential nào đã được gửi tự động

Khi kiểm thử một môi trường được phép, có thể dùng công cụ mạng của trình duyệt để quan sát một request thay đổi trạng thái.

### Bước 1. Xác định cách người dùng được xác thực

Quan sát request hợp lệ trong Network:

~~~http
POST /account/settings HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...
Content-Type: application/x-www-form-urlencoded

timezone=Asia/Ho_Chi_Minh
~~~

Nếu server xác thực từ `JSESSIONID`, cần điều tra luồng gửi cookie và CSRF token.

Nếu request dùng:

~~~http
POST /api/settings HTTP/1.1
Host: api.example.com
Authorization: Bearer ...
Content-Type: application/json

{"timezone":"Asia/Ho_Chi_Minh"}
~~~

cần hỏi **ai đã thêm header `Authorization`**. Header do JavaScript của ứng dụng tự thêm khác với một cơ chế xác thực do trình duyệt tự gắn.

### Bước 2. Xem cách cookie được đặt

Kiểm tra response chứa `Set-Cookie` và những đặc tính có ý nghĩa:

- Cookie có `Domain` không? Nếu không, nó là host-only.
- `Path` có bao gồm đường dẫn endpoint không?
- Request có dùng HTTPS tương ứng với `Secure` không?
- `SameSite` là `Strict`, `Lax` hay `None`? Có chính sách trình duyệt bổ sung không?
- Cookie còn hạn và phiên phía server còn hợp lệ không?

Không nên kết luận chỉ từ `Application → Cookies`. Hãy xem **cookie thực sự được gửi hay bị loại bỏ trong request cụ thể**, kể cả lý do bị loại nếu DevTools hiển thị.

### Bước 3. Thử request thay đổi trạng thái thiếu hoặc sai CSRF token

Trong môi trường kiểm thử:

| Request | Kỳ vọng khi bảo vệ CSRF hoạt động |
|---|---|
| Credential hợp lệ + POST thiếu CSRF token | Bị từ chối, thường `403` với Spring Security mặc định. |
| Credential hợp lệ + POST có token sai | Bị từ chối. |
| Credential hợp lệ + POST có token đúng và được phân quyền | Có thể qua bước CSRF; kết quả nghiệp vụ còn phụ thuộc validation, quyền và dữ liệu. |
| Không có credential + POST có token không hợp lệ | Không được thực hiện dưới danh tính người dùng đã đăng nhập. |
| Cross-site form trong trình duyệt thật | Phải kiểm tra cookie có được gửi và token có bị từ chối; không suy luận từ HTTP client. |

**Chú ý:** HTTP client như cURL/Postman có thể cố ý chèn header `Cookie` theo ý người kiểm thử. Điều đó giúp kiểm tra server có yêu cầu CSRF token hay không, nhưng **không tự chứng minh trình duyệt sẽ gửi cookie khi nạn nhân vào website ngoài**. Muốn kiểm tra khả năng khai thác trên web, phải đối chiếu với hành vi browser thực tế.

### Bước 4. Phân biệt nguyên nhân bị từ chối

Một lỗi `403` có thể do **CSRF token**, **quyền truy cập**, hoặc cơ chế bảo vệ khác. Một lỗi `401`/chuyển về trang đăng nhập có thể cho thấy credential không được gửi hoặc không còn hợp lệ. Cần kiểm tra filter/security chain và hành vi endpoint trước khi kết luận.

Trên Servlet, các ngoại lệ liên quan CSRF có thể gồm `MissingCsrfTokenException` và `InvalidCsrfTokenException`. Trên WebFlux, đối chiếu với cơ chế `CsrfWebFilter` và cấu hình bảo mật reactive. Không nên chỉ dựa vào status code để suy ra nguyên nhân.

## 9. Những trường hợp dễ đánh giá sai

### “Ứng dụng dùng JWT nên không thể có CSRF”

Không đúng nếu JWT được đặt trong cookie tự gửi. Cần xem cách vận chuyển token và endpoint có chấp nhận cookie đó khi thực hiện thao tác hay không.

### “Cookie HttpOnly khiến trang tấn công không đọc được phiên, vậy đủ an toàn”

Trang tấn công không cần đọc cookie để kích hoạt request. `HttpOnly` giúp bảo vệ bí mật cookie, còn CSRF kiểm soát **tính hợp lệ của yêu cầu thay đổi trạng thái**.

### “CORS không cấp quyền nên form từ site khác không gửi được”

Một form HTML đơn giản có thể tạo request cross-site mà không cần CORS cấp quyền đọc phản hồi. Nếu server thực hiện thao tác trước khi phản hồi bị chặn đọc, tác động đã xảy ra.

### “SameSite=Lax chặn mọi yêu cầu không do trang của mình gửi”

`Lax` vẫn có trường hợp gửi cookie, đặc biệt điều hướng top-level bằng phương thức an toàn. Hai origin khác nhau cũng có thể là cùng site. Không nên coi SameSite là biện pháp duy nhất.

### “Chỉ cần kiểm tra user đã đăng nhập”

Kiểm tra đăng nhập chỉ trả lời **ai đang được nhận diện**. Với request mang credential tự gửi, server vẫn cần xác minh **request thay đổi trạng thái có hợp lệ theo cơ chế chống CSRF hay không**.

### “Không lưu session ở server thì không còn credential tự gửi”

Một cookie chứa JWT, HTTP Basic được browser tái sử dụng hoặc hình thức xác thực tự động khác vẫn có thể mang quyền vào request. “Stateless” phía server không tự loại bỏ CSRF.

## 10. Bài tập phân tích nhanh

**Tình huống A — cookie phiên và POST từ site ngoài.** Ứng dụng có `SameSite=None; Secure`, dùng session cookie để xác thực, endpoint POST nhận form và không kiểm tra CSRF token. Trình duyệt mục tiêu thực sự gửi cookie trong request. **Nhận định:** có đủ tiền đề điển hình cho CSRF; cần bổ sung kiểm tra CSRF phù hợp.

**Tình huống B — bearer header do SPA tạo.** Ứng dụng chỉ chấp nhận `Authorization: Bearer ...` do mã client cùng origin chủ động thêm. Không có cookie/session/Basic tự gửi nào được API dùng để xác thực. **Nhận định:** trang ngoài không thể chỉ gửi form mà tự có bearer header hợp lệ; nguy cơ CSRF truyền thống thấp hơn, nhưng vẫn phải phòng chống XSS, lộ token và sai cấu hình CORS.

**Tình huống C — JSON Web Token trong cookie.** Backend được gọi là “stateless” nhưng đọc JWT từ cookie `AUTH` và xử lý `PATCH /profile`. **Nhận định:** cookie là credential tự gửi, vì vậy vẫn cần đánh giá CSRF theo loại request, chính sách cookie và biện pháp từ chối yêu cầu giả mạo.

**Tình huống D — hai subdomain.** Frontend `https://ui.example.com` và API `https://api.example.com` khác origin nhưng cùng site. API xác thực bằng cookie phù hợp với host `api.example.com`. **Nhận định:** không thể kết luận `SameSite=Strict` tự chặn mọi request từ `ui.example.com` hoặc một subdomain cùng site khác; phải xem cấu hình Domain, cơ chế request và CSRF token.

## Tổng kết

Thông tin xác thực được trình duyệt **tự đính kèm** là nền tảng của nhiều kịch bản CSRF: browser có thể mang cookie phiên, JWT trong cookie hoặc hình thức xác thực tự động khác vào một yêu cầu do bên thứ ba kích hoạt. Server có thể xác thực **đúng danh tính** nhưng vẫn xử lý **sai ý định**.

Khi thiết kế các lớp phòng vệ HTTP của Spring Security trên **Servlet** hoặc **Reactive**, hãy xác minh loại credential và đường vận chuyển của nó trước khi quyết định phạm vi CSRF. `HttpOnly`, `Secure`, `SameSite` và CORS mang lại các rào cản khác nhau; **CSRF token hoặc cơ chế xác minh request tương đương** mới là lớp bảo vệ trực tiếp giúp ứng dụng từ chối các thao tác thay đổi trạng thái bị giả mạo. Việc kiểm thử phải xem cả **request thực tế trên trình duyệt** và **quyết định của security filter chain trên máy chủ**.
