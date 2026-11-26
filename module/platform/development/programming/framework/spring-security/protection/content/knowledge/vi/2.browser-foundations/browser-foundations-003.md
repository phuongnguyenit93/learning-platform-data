# Same-Origin Policy và ranh giới đọc dữ liệu

## Mục tiêu bài học

**Same-Origin Policy (SOP)** là cơ chế nền tảng giúp trình duyệt giới hạn quyền đọc dữ liệu và tương tác giữa các website có origin khác nhau. Bài thuộc chương **Nền tảng trình duyệt**, trong module **SPRING_SECURITY_HTTP_PROTECTION**: áp dụng các lớp bảo vệ HTTP và trình duyệt bằng Spring Security, từ CORS, CSRF, security headers, CSP, HSTS đến bảo vệ session và HTTP firewall trên cả **Servlet** lẫn **Reactive (WebFlux)**.

Sau khi hoàn thành, bạn có thể:

1. Xác định origin của một URL và phân biệt **same-origin**, **cross-origin** với **same-site**.
2. Giải thích ranh giới đọc của SOP trong **fetch/XHR**, **iframe DOM**, **Web Storage** và **canvas**.
3. Phân biệt **gửi request**, **nhúng tài nguyên**, **thực thi script** và **đọc phản hồi**.
4. Giải thích **CORS** mở quyền đọc có kiểm soát như thế nào, và vì sao SOP/CORS không tự chống **CSRF**, **XSS**.
5. Áp dụng kiến thức vào cấu hình CORS và chẩn đoán lỗi Spring Security Servlet/WebFlux, đặc biệt khi frontend và API khác origin.

## 1. Bài toán bảo mật: một website có được đọc dữ liệu của website khác?

Một người dùng đang đăng nhập tại **https://bank.example** và đồng thời truy cập trang không đáng tin cậy **https://attacker.test**. Nếu mã JavaScript của attacker.test có thể tự ý đọc trang tài khoản, nội dung API hoặc vùng dữ liệu của bank.example, thông tin riêng tư của người dùng sẽ bị lộ chỉ vì hai trang cùng mở trong trình duyệt.

**Same-Origin Policy** đặt ranh giới giữa những ngữ cảnh có origin khác nhau. Với website attacker.test:

- Script không được tự do đọc **DOM** của một iframe từ bank.example.
- Script không thể đọc **body của phản hồi fetch** từ bank.example nếu thiếu cơ chế cho phép phù hợp như CORS.
- Script không được đọc **localStorage** của bank.example.
- Nhưng trình duyệt có thể cho phép **khởi tạo một số request** hoặc **nhúng một số tài nguyên** cross-origin, tùy loại thao tác và các chính sách liên quan.

Đây là nguyên tắc trung tâm:

> **Không cho JavaScript đọc dữ liệu cross-origin không đồng nghĩa với việc mọi request cross-origin đều bị ngăn không cho gửi.**

Không nên dùng câu “SOP cấm mọi truy cập đến domain khác”: cách diễn đạt đó không mô tả đúng hành vi của trình duyệt.

## 2. Xác định origin: scheme, host và port

Với các địa chỉ HTTP/HTTPS thông thường:

**Origin = (scheme, host, port)**

~~~text
https://app.example.com:8443/account?tab=profile#top
└─┬──┘  └──────┬──────┘ └┬─┘
scheme        host       port

Origin = https://app.example.com:8443
~~~

**Path, query và fragment không tham gia so sánh origin.** HTTP có cổng mặc định 80, HTTPS có cổng mặc định 443; cổng mặc định được chuẩn hóa.

Giả sử trang đang chạy tại **https://app.example.com:443/dashboard**:

| URL được truy cập | Same-origin? | Giải thích |
| --- | --- | --- |
| https://app.example.com/api/me | Có | Cùng scheme, host và cổng HTTPS 443 mặc định. |
| https://APP.example.com:443/settings | Có | Host HTTP/HTTPS được chuẩn hóa không phân biệt chữ hoa/thường. |
| https://app.example.com:8443/api/me | Không | Khác cổng. |
| http://app.example.com/api/me | Không | Khác scheme HTTP/HTTPS. |
| https://api.example.com/api/me | Không | Khác host/subdomain. |
| https://example.com/api/me | Không | Host khác. |
| https://app.example.com.evil.test/api/me | Không | Đây là host bên dưới evil.test. |
| https://app.example.com/api/me?limit=2#result | Có | Path, query, fragment không thay đổi origin. |

Trong trình duyệt:

~~~javascript
console.log(window.location.origin);
// Ví dụ: "https://app.example.com"

console.log(new URL("https://api.example.com/v1/users").origin);
// "https://api.example.com"

console.log(new URL("https://app.example.com:443/profile").origin);
// "https://app.example.com"
~~~

Một tên miền và một địa chỉ IP có thể trỏ về cùng server nhưng vẫn là hai host khác nhau. **localhost**, **127.0.0.1** và **[::1]** cũng không tự trở thành same-origin chỉ vì cùng một máy.

**Lưu ý về ngoại lệ:** Công thức bộ ba áp dụng trực tiếp với origin HTTP/HTTPS thông thường. Một số tài liệu có **opaque origin**, chẳng hạn tài liệu dùng URL data: hoặc iframe sandbox nhất định. Origin kiểu đó không biểu diễn được bằng bộ ba HTTP/HTTPS quen thuộc; header Origin đôi khi có thể mang giá trị **null**. Không được mặc định tin cậy Origin: null.

### 2.1. Origin khác site

Đối với chính sách **schemeful same-site** hiện đại, site được xác định theo scheme và miền có thể đăng ký (*registrable domain*, dựa trên Public Suffix List) đối với host miền thông thường. Site không dùng port làm ranh giới.

~~~text
https://app.example.com
https://api.example.com

=> Thường same-site: https://example.com
=> Cross-origin: khác host app.example.com / api.example.com
~~~

Vì vậy **same-site không đồng nghĩa same-origin**. Quy tắc cookie **SameSite** sử dụng cách xét site, còn SOP và CORS xét origin. Hai subdomain cùng site vẫn có thể cần CORS khi frontend đọc JSON của API.

## 3. SOP hạn chế hành vi nào?

Các thao tác cross-origin thường thuộc ba nhóm, với quy tắc bảo vệ khác nhau:

| Nhóm | Ví dụ | Kết quả thường gặp |
| --- | --- | --- |
| **Đọc cross-origin** | fetch đọc JSON; đọc DOM của iframe; đọc pixel canvas; truy cập storage khác origin | Bị SOP hoặc quy tắc tương ứng hạn chế nếu không có cơ chế cấp phép hợp lệ. |
| **Gửi hoặc ghi cross-origin** | Điều hướng; gửi HTML form; một số yêu cầu HTTP | Nhiều trường hợp có thể khởi tạo request; quy tắc về preflight, cookie, CSP và server vẫn được áp dụng. |
| **Nhúng cross-origin** | Ảnh, iframe, script, stylesheet, video | Có thể được tải hoặc hiển thị theo quy tắc riêng; không đồng nghĩa JavaScript được đọc mọi dữ liệu nội bộ. |

Ví dụ trang có thể hiển thị ảnh từ CDN:

~~~html
<img src="https://cdn.example.net/logo.png" alt="Logo">
~~~

Nhưng việc ảnh hiển thị không tự cho phép JavaScript đọc pixel của ảnh đó từ canvas.

Một trang cũng có thể nhúng iframe từ website khác nếu website đích cho phép, nhưng mã của trang cha không vì thế được đọc document của iframe.

### 3.1. Tại sao một request gây tác dụng phụ có thể vẫn được gửi?

Xét form:

~~~html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="amount" value="100">
  <input type="hidden" name="to" value="attacker">
  <button type="submit">Continue</button>
</form>
~~~

Khi trình duyệt gửi form, request chịu các quy tắc cookie, điều hướng và bảo mật tương ứng. Nếu cookie xác thực được gửi và server không có phòng vệ CSRF phù hợp, request có thể gây tác dụng phụ dù mã ở website nguồn không được đọc phản hồi.

**SOP/CORS không thay thế CSRF protection.** Hạn chế quyền đọc là vấn đề khác với xác nhận một thao tác có được người dùng cho phép hay không.

## 4. SOP với fetch và XMLHttpRequest

Ví dụ frontend tại **https://app.example.com** và API tại **https://api.example.com**.

### 4.1. Fetch cùng origin

~~~javascript
const response = await fetch("/api/me");
if (!response.ok) throw new Error("HTTP " + response.status);
const profile = await response.json();
~~~

Nếu URL tương đối này nằm trên cùng origin, trình duyệt không yêu cầu CORS để JavaScript đọc phản hồi. Tuy vậy, server vẫn có thể trả **401/403** do authentication hoặc authorization.

### 4.2. Fetch khác origin

~~~javascript
const response = await fetch("https://api.example.com/api/me");
const profile = await response.json();
~~~

Trong trường hợp này, JavaScript muốn đọc phản hồi cross-origin; trình duyệt kiểm tra chính sách **CORS**. Nếu API không cho phép origin của frontend, trình duyệt chặn mã đọc response body.

Một request có thể xuất hiện trong DevTools **Network** và được server xử lý trước khi browser thông báo lỗi CORS. Cũng có trường hợp request thực tế chưa gửi vì **preflight** thất bại. Phải kiểm tra từng giai đoạn, không suy đoán từ một thông báo lỗi.

Giả sử server cho phép frontend **https://app.example.com**:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Phản hồi có thể bao gồm:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

{"displayName":"Minh"}
~~~

Header **Access-Control-Allow-Origin** cho trình duyệt biết origin nào được phép đọc phản hồi CORS. Giá trị **Origin** chỉ chứa scheme, host và port, không có path. Header **Vary: Origin** giúp cache trung gian phân biệt phản hồi CORS khi server trả khác nhau theo Origin.

Một API công khai không cần credentials có thể sử dụng wildcard CORS trong phạm vi hợp lý, nhưng không nên mở quyền đọc các phản hồi nhạy cảm cho mọi origin.

### 4.3. Preflight: OPTIONS trước request thực

Một số request cross-origin buộc trình duyệt gửi **OPTIONS preflight**. Ví dụ POST với Content-Type: application/json và custom header X-CSRF-TOKEN thường cần preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Phản hồi cho phép có thể là:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Vary: Origin
~~~

Sau khi preflight hợp lệ, trình duyệt mới gửi POST theo quy tắc CORS. Không phải request cross-origin nào cũng preflight; các yêu cầu thuộc nhóm được CORS safelist có thể được gửi trực tiếp.

**Preflight không phải xác thực người dùng.** Nó thường không kèm cookie phiên. Nếu security filter yêu cầu phiên đăng nhập trước khi xử lý OPTIONS, preflight có thể bị 401/403.

### 4.4. Request có cookie/session và credentials

Fetch cross-origin với cookie thường yêu cầu cấu hình credentials rõ ràng:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
const profile = await response.json();
~~~

Ví dụ header phản hồi khi máy chủ cho phép đọc với credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng tổ hợp wildcard với credentials:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Trình duyệt không chấp nhận wildcard Allow-Origin cho phản hồi CORS có credentials. Cũng không nên phản chiếu mọi Origin do client gửi rồi bật credentials: chính sách đó có thể mở quyền đọc dữ liệu có cookie cho website không đáng tin.

**credentials: "include" không vượt qua cookie policy.** Cookie chỉ được gửi nếu thỏa Domain, Path, Secure, SameSite và các giới hạn của trình duyệt. CORS cấp quyền đọc phản hồi, còn cookie/session quyết định yêu cầu có dữ liệu phiên hay không.

### 4.5. mode: "no-cors" không giải quyết lỗi đọc JSON

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  mode: "no-cors"
});

console.log(response.type);   // Thường "opaque"
console.log(response.status); // 0 đối với opaque response
~~~

Trong ngữ cảnh ví dụ, no-cors giới hạn request có thể gửi và phản hồi thường là **opaque response**. JavaScript không đọc được nội dung JSON hoặc trạng thái HTTP thực từ phản hồi opaque.

Nếu thực sự muốn frontend đọc dữ liệu API cross-origin, cần **CORS đúng trên server** hoặc một kiến trúc proxy cùng origin được thiết kế phù hợp. Thay mode thành no-cors để “tắt CORS” là sai bản chất.

## 5. Iframe: nhúng được nhưng không đọc được DOM

Giả sử trang **https://app.example.com** nhúng iframe:

~~~html
<iframe id="report" src="https://reports.example.net/summary"></iframe>
~~~

Nếu trang đích cho phép nhúng, iframe có thể hiển thị. Nhưng JavaScript ở trang cha không được tự do đọc DOM của iframe khác origin:

~~~javascript
const frame = document.getElementById("report");

try {
  console.log(frame.contentWindow.document.body.innerText);
} catch (error) {
  console.error(error.name); // Thường là "SecurityError"
}
~~~

SOP cũng giới hạn quyền đọc DOM theo hướng từ iframe sang trang cha. Một số thao tác giới hạn với cửa sổ cross-origin vẫn có thể được phép; đừng đồng nhất “không được đọc DOM” với “không thể giao tiếp”.

### 5.1. Kiểm soát quyền nhúng bằng security headers

Ứng dụng có trang quản trị nhạy cảm thường không muốn bị nhúng vào iframe bởi website bên ngoài. Server có thể gửi:

~~~http
Content-Security-Policy: frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
~~~

**frame-ancestors** thuộc CSP quyết định các ancestor nào được phép nhúng trang; **X-Frame-Options** là cơ chế cũ với khả năng biểu đạt hạn chế hơn. Chúng bảo vệ khỏi các kịch bản như **clickjacking** bằng cách hạn chế khả năng nhúng.

SOP và frame-ancestors giải quyết hai câu hỏi khác nhau: **đã nhúng thì có đọc được DOM không?** và **có được phép nhúng trang không?**.

### 5.2. postMessage để trao đổi thông tin có kiểm soát

Nếu trang cha và iframe khác origin cần trao đổi dữ liệu hợp lệ, có thể dùng **window.postMessage**.

Bên gửi trong iframe ở **https://reports.example.net**:

~~~javascript
window.parent.postMessage(
  { type: "REPORT_READY", reportId: "r42" },
  "https://app.example.com"
);
~~~

Bên nhận ở **https://app.example.com**:

~~~javascript
const expectedOrigin = "https://reports.example.net";
const reportFrame = document.getElementById("report");

window.addEventListener("message", (event) => {
  if (event.origin !== expectedOrigin) return;
  if (event.source !== reportFrame.contentWindow) return;

  const data = event.data;
  if (!data || data.type !== "REPORT_READY") return;
  if (typeof data.reportId !== "string") return;

  console.log("Report ready:", data.reportId);
});
~~~

Cần kiểm tra **event.origin**, **event.source** nếu thích hợp và cấu trúc payload. Bên gửi nên đặt **targetOrigin** cụ thể thay vì dấu sao khi gửi dữ liệu nhạy cảm. **postMessage không tắt SOP**; nó là kênh trao đổi thông tin do các bên chủ động cho phép.

## 6. Ranh giới SOP trong canvas, script và storage

### 6.1. Ảnh cross-origin và canvas bị taint

Một ảnh từ CDN khác origin có thể hiển thị; nhưng nếu JavaScript vẽ ảnh đó vào canvas khi chưa có quyền CORS phù hợp, canvas có thể bị **taint** và không thể đọc pixel:

~~~javascript
const image = new Image();
image.src = "https://cdn.example.net/chart.png";

image.onload = () => {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;

  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);

  try {
    context.getImageData(0, 0, 1, 1);
  } catch (error) {
    console.error(error.name); // "SecurityError" nếu canvas bị taint
  }
};
~~~

Nếu cần đọc pixel một cách hợp lệ, server nguồn phải cấp quyền CORS và client cần tải ảnh với chế độ phù hợp, ví dụ đặt **image.crossOrigin = "anonymous"** trước khi gán src. Việc hiển thị ảnh **không đồng nghĩa có quyền xuất ảnh hoặc đọc pixel**.

### 6.2. Script tải từ origin khác chạy với quyền của trang nhúng

~~~html
<script src="https://cdn.example.net/widget.js"></script>
~~~

Khi được phép tải và thực thi, script này thường chạy trong ngữ cảnh origin của trang nhúng. Vì vậy, chọn một URL script bên ngoài là **quyết định tin cậy mã thực thi**, không chỉ quyết định tải file. Nếu CDN bị kiểm soát bởi kẻ tấn công, script độc hại có thể thực hiện các hành động theo quyền của trang đã nhúng nó.

SOP **không tự ngăn XSS** khi mã độc đã chạy trong origin đáng tin. Cần xử lý dữ liệu không tin cậy an toàn, CSP phù hợp và xem xét **Subresource Integrity (SRI)** đối với tài nguyên tĩnh bên thứ ba.

### 6.3. Web Storage khác cookie

**localStorage** gắn với origin, nên script từ **https://app.example.com** không thể đọc localStorage của **https://api.example.com**:

~~~javascript
// Đọc vùng storage của origin trang hiện tại.
const token = localStorage.getItem("token");
~~~

**sessionStorage** còn phụ thuộc ngữ cảnh duyệt/tab bên cạnh origin.

**Cookie** có quy tắc riêng: Domain, Path, Secure, SameSite, HttpOnly và các thuộc tính khác. Cookie có Domain=example.com có thể đủ điều kiện gửi cho nhiều subdomain, nhưng **không vì thế cấp quyền đọc localStorage hoặc DOM giữa các subdomain**. Cookie HttpOnly không được đọc bằng document.cookie trong những ngữ cảnh thông thường.

### 6.4. Opaque origin và iframe sandbox

Một iframe có sandbox và không bật allow-same-origin thường được gán origin riêng biệt:

~~~html
<iframe
  src="/untrusted-preview"
  sandbox="allow-scripts"
  title="Preview">
</iframe>
~~~

Dù URL có đường dẫn cùng host với trang cha, iframe sandbox có thể bị xem là khác origin. Cẩn trọng với tổ hợp **allow-scripts** và **allow-same-origin** dành cho nội dung cùng origin không đáng tin: tổ hợp này có thể làm suy yếu ranh giới sandbox mong muốn.

## 7. SOP, CORS, CSRF và những lớp phòng vệ khác

Giả sử ứng dụng dùng:

~~~text
Frontend: https://app.example.com
API:      https://api.example.com

Cùng site (thường https://example.com), khác origin.
~~~

| Cơ chế | Mục đích chính | Không tự giải quyết |
| --- | --- | --- |
| **SOP** | Giới hạn quyền đọc và tương tác cross-origin của mã trình duyệt. | Không ngăn mọi request gây tác dụng phụ. |
| **CORS** | Server cho phép những origin cụ thể đọc phản hồi cross-origin. | Không phải xác thực; không tự chống CSRF. |
| **CSRF protection** | Xác minh yêu cầu thay đổi trạng thái có bằng chứng hợp lệ theo thiết kế ứng dụng. | Không tự ngăn XSS chạy trong origin đáng tin. |
| **SameSite cookie** | Hạn chế cookie theo ngữ cảnh site. | Không đồng nghĩa same-origin hoặc loại trừ tấn công từ subdomain same-site. |
| **CSP** | Hạn chế các nguồn nội dung và cách thực thi, tùy chỉ thị. | Không thay thế CORS hoặc phân quyền. |
| **HSTS** | Hướng trình duyệt sử dụng HTTPS cho host theo chính sách được biết. | Không làm HTTP và HTTPS trở thành same-origin. |

Kịch bản CSRF: một website ngoài hệ thống gửi form POST đến endpoint dùng cookie phiên. SOP có thể chặn mã bên ngoài **đọc phản hồi**, nhưng request vẫn có thể tới server nếu những quy tắc khác cho phép. Nếu server không kiểm tra CSRF, endpoint có thể có rủi ro.

Kịch bản XSS: script độc hại chạy **bên trong origin của ứng dụng** có thể gọi API và đọc những phản hồi mà ứng dụng hợp lệ được phép đọc. SOP không phân biệt script “tốt” hay “xấu” trong cùng origin.

Kịch bản khác: **WebSocket** không sử dụng mô hình CORS của fetch/XHR; server cần kiểm tra Origin cùng authentication và authorization theo cách riêng. CORS cho REST API không tự bảo đảm an toàn cho WebSocket.

## 8. Tích hợp CORS vào Spring Security

Ví dụ frontend ở **https://app.example.com**, API ở **https://api.example.com**. API dùng cookie/session, cần cho phép frontend đọc phản hồi có credentials. Cấu hình bên dưới minh họa **cách xử lý SOP/CORS**, vẫn giữ CSRF protection mặc định; hệ thống thật còn cần cơ chế cấp CSRF token và cấu hình session thích hợp.

### 8.1. Servlet: Spring Security 6.x

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                // CSRF mặc định vẫn hoạt động.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Lưu ý:**

- Chỉ định origin là **https://app.example.com**, không thêm đường dẫn /dashboard vì path không thuộc origin.
- Đăng ký chính sách cho **/api/**; những URL khác không tự có cùng CORS policy.
- Điều chỉnh danh sách method/header theo API thực tế. Không mở toàn bộ origin tùy tiện.
- Preflight OPTIONS thường không có cookie; cần để xử lý CORS diễn ra trước các bước xác thực có thể từ chối preflight.

### 8.2. Reactive: Spring WebFlux

Trong WebFlux, sử dụng CORS source trong gói **org.springframework.web.cors.reactive**:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                // CSRF mặc định vẫn hoạt động.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Chỉ chọn cấu hình **Servlet hoặc Reactive** theo stack ứng dụng. Không trộn các lớp CorsConfigurationSource của hai stack; CORS đúng không tự cấp quyền sử dụng API nếu xác thực, phân quyền hoặc CSRF thất bại.

### 8.3. Frontend POST với CSRF token hợp lệ

~~~javascript
// Ví dụ: biến csrfToken đã được ứng dụng cấp hợp lệ.
const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Đoạn mã giả định **csrfToken** đã được cấp qua một cơ chế hợp lệ, chẳng hạn endpoint CSRF JSON được bảo vệ và cho phép CORS phù hợp. Server phải liên kết và kiểm tra token theo cơ chế bảo vệ CSRF thực tế.

Lệnh POST thường dẫn tới OPTIONS preflight. Nếu preflight đạt nhưng POST trả 403, cần kiểm tra **CSRF token**, session và phân quyền; đó không mặc nhiên là lỗi CORS.

## 9. Chẩn đoán theo đúng ranh giới đọc

Thực hiện kiểm tra trong **DevTools → Network** và **Console** bằng một môi trường thử nghiệm được phép.

### 9.1. GET cross-origin

~~~javascript
try {
  const r = await fetch("https://api.example.com/api/me");
  console.log(await r.json());
} catch (error) {
  console.error("Không đọc được phản hồi:", error);
}
~~~

Đối chiếu trong Network: GET có được gửi không? Server có trả phản hồi không? **Access-Control-Allow-Origin** có phù hợp với Origin thực của trang không? Có lỗi mạng TLS/DNS hoặc redirect không? Không nên kết luận chỉ từ thông báo trong Console.

### 9.2. POST preflight

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "invalid-demo-token"
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Token trên cố ý không hợp lệ và chỉ dùng cho môi trường thử nghiệm. Quan sát:

1. **OPTIONS** có xuất hiện không?
2. OPTIONS trả về CORS header phù hợp hay bị 401/403/redirect?
3. Nếu OPTIONS thành công, trình duyệt có gửi **POST** không?
4. Nếu POST bị 403, log có chỉ ra CSRF hoặc authorization không?

### 9.3. Test HTTP bằng curl

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Dùng **curl.exe** trên PowerShell nếu cần tránh bí danh curl. Lệnh này kiểm tra header do server công bố, **không thực thi SOP/CORS như trình duyệt**.

### 9.4. Bảng triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Fetch báo CORS nhưng Network có GET 200. | Phản hồi thiếu/sai Access-Control-Allow-Origin hoặc credentials header. | So Origin và các response header. |
| OPTIONS bị 401/403. | CORS xử lý sau bộ lọc bảo mật, hoặc method/header không được cho phép. | Kiểm tra thứ tự filter và cấu hình CORS. |
| OPTIONS thành công nhưng POST 403. | CSRF token hoặc authorization không hợp lệ. | Xem log bảo mật, token/session. |
| Cookie không được gửi dù credentials: include. | Domain, Path, Secure, SameSite hoặc chính sách trình duyệt. | Xem Cookies/Request Headers trong DevTools. |
| Iframe hiển thị nhưng truy cập DOM ném SecurityError. | SOP ngăn đọc iframe cross-origin. | Dùng postMessage nếu hai bên cần giao tiếp. |
| Iframe bị chặn hiển thị. | CSP frame-ancestors, X-Frame-Options hoặc lỗi tải. | Xem header và Console. |
| Ảnh hiển thị nhưng canvas ném SecurityError. | Canvas bị taint. | Kiểm tra CORS của ảnh và image.crossOrigin. |
| API dùng curl được nhưng fetch không đọc được. | curl không bị SOP/CORS ràng buộc. | Kiểm tra trên trình duyệt thực. |

## 10. Sai lầm bảo mật thường gặp

| Hiểu lầm | Vì sao sai? |
| --- | --- |
| “CORS chặn nên server chắc chắn chưa nhận request.” | Request không cần preflight có thể đã được gửi; việc đọc phản hồi mới bị chặn. |
| “Mở CORS cho mọi origin sẽ giải quyết mọi lỗi 403.” | 403 có thể do CSRF, phân quyền, HTTP firewall hoặc logic khác; mở quyền đọc bừa bãi tạo rủi ro. |
| “Origin header chứng minh client là website được tin cậy.” | HTTP client ngoài trình duyệt có thể tự đặt Origin; phải xác thực độc lập. |
| “Same-site là same-origin.” | Subdomain và port khác nhau có thể cùng site nhưng khác origin. |
| “no-cors làm fetch đọc được JSON.” | Opaque response không cho JavaScript đọc body theo cách thông thường. |
| “SOP chặn mọi XSS.” | Script độc hại chạy trong cùng origin có thể có quyền như script ứng dụng. |
| “SOP tự ngăn CSRF.” | Một số request cross-origin vẫn có thể được gửi và gây tác dụng phụ. |
| “Nhúng được iframe nghĩa là đọc được DOM.” | Chính sách nhúng khác với quyền đọc DOM cross-origin. |
| “Bật CORS cho REST đồng nghĩa WebSocket an toàn.” | WebSocket cần kiểm tra Origin, authentication và authorization theo cơ chế riêng. |

## 11. Tình huống vận dụng

### Tình huống A — Đã gửi GET hay chưa?

Script từ **https://attacker.test** dùng fetch gọi API hồ sơ của **https://bank.example**. API không trả CORS header phù hợp. Có thể kết luận GET chưa bao giờ đến server không?

**Đáp án:** Không. GET có thể đã được gửi và xử lý, nhưng mã ở attacker.test không đọc được phản hồi do CORS/SOP. Cần kiểm tra Network và log server.

### Tình huống B — Hai subdomain cùng site

**https://app.example.com** gọi **https://api.example.com**. Hai URL có thể cùng site. Frontend có tự đọc được JSON API khi API không cấu hình CORS không?

**Đáp án:** Không. Khác host nghĩa là khác origin; same-site không bỏ qua yêu cầu CORS.

### Tình huống C — Form thay đổi mật khẩu

Một website bên ngoài gửi form POST tới endpoint đổi mật khẩu dùng cookie phiên. CORS không cho website đó đọc phản hồi. Có thể tắt CSRF protection không?

**Đáp án:** Không. SOP/CORS giới hạn quyền đọc, không bảo đảm request không gây tác dụng phụ. Endpoint vẫn cần CSRF protection, authentication và authorization phù hợp.

### Tình huống D — Iframe báo SecurityError

Trang tại **https://app.example.com** nhúng iframe **https://reports.example.net**. Truy cập **iframe.contentWindow.document** bị SecurityError. Cần giải quyết thế nào?

**Đáp án:** Đây là giới hạn DOM cross-origin của SOP. Nếu hai ứng dụng hợp tác, dùng postMessage với targetOrigin cụ thể và kiểm tra event.origin/source/payload, không cố vô hiệu SOP.

### Tình huống E — Canvas đọc ảnh bị lỗi

Ảnh CDN hiện lên, nhưng sau khi vẽ vào canvas thì **getImageData** hoặc **toDataURL** ném SecurityError.

**Đáp án:** Canvas bị taint. Muốn đọc pixel cần client tải ảnh ở chế độ CORS thích hợp và server ảnh cấp CORS phù hợp; không phải do img bị lỗi hiển thị.

### Tình huống F — OPTIONS đạt, POST 403

OPTIONS trả 204 và CORS header đúng, nhưng POST JSON có X-CSRF-TOKEN vẫn bị 403.

**Đáp án:** Preflight chỉ kiểm tra chính sách CORS; request thực tế vẫn có thể thất bại do CSRF token, session hoặc quyền. Kiểm tra log Spring Security và token trước khi sửa chính sách CORS.

### Tình huống G — Script từ CDN bị chiếm quyền

Một ứng dụng đăng nhập tải script từ CDN ngoài hệ thống. CDN trả mã độc. SOP có tự ngăn mã độc đọc dữ liệu mà trang đăng nhập được phép đọc không?

**Đáp án:** Không. Script được nhúng có thể thực thi trong origin của trang. Cần kiểm soát nguồn bằng CSP, SRI khi phù hợp, và bảo vệ trước XSS/chèn script.

## 12. Ghi nhớ

- **SOP giới hạn quyền đọc và tương tác giữa các origin**, nhưng không cấm mọi request hoặc mọi dạng nhúng cross-origin.
- **Origin = scheme + host + port** với HTTP/HTTPS thông thường; path, query và fragment không tham gia. **Same-site không đồng nghĩa same-origin.**
- **Fetch/XHR, iframe DOM, canvas và Web Storage** có ranh giới đọc cụ thể. Hiển thị ảnh hoặc gửi form được không có nghĩa JavaScript được đọc dữ liệu.
- **CORS** mở quyền đọc phản hồi cross-origin một cách có kiểm soát; **no-cors không mở quyền đọc JSON**.
- **CSRF token, authentication, authorization, SameSite cookie, CSP, HSTS và bảo vệ session** bổ sung cho SOP trong hệ thống Spring Security.
- Khi triển khai trên **Servlet hoặc Reactive**, hãy phân biệt **preflight**, **CORS response**, **CSRF** và **phân quyền** để sửa đúng nguyên nhân.
