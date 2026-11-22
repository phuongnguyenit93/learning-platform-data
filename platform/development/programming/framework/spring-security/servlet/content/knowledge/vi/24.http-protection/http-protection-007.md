# Referrer-Policy, Permissions-Policy và lựa chọn theo nhu cầu ứng dụng

**Bối cảnh:** Spring Security **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, Spring Security 6.x. Hai HTTP response header `Referrer-Policy` và `Permissions-Policy` giúp giảm rò rỉ thông tin điều hướng và giới hạn khả năng dùng API nhạy cảm của trình duyệt. Chúng giải quyết **hai vấn đề bảo mật khác nhau**: một bên là **thông tin về trang nguồn được gửi đi**, một bên là **tính năng trình duyệt được phép sử dụng**.

## 1. Bức tranh tổng thể

Khi người dùng mở trang `https://app.example.com/account?tab=security` rồi bấm liên kết sang website khác, trình duyệt có thể gửi request chứa header `Referer` cho biết trang trước đó. Nếu gửi toàn bộ URL, phần path/query có thể tiết lộ thông tin không nên được chia sẻ.

Cũng trên trang ấy, JavaScript hoặc iframe có thể muốn truy cập camera, micro, vị trí, fullscreen hay một số khả năng web platform khác. Không phải tính năng nào cũng nên được bật ở mọi trang.

Hai header xử lý hai luồng:

| Header phản hồi | Tác động chính | Ví dụ |
| --- | --- | --- |
| `Referrer-Policy` | Điều khiển lượng thông tin URL nguồn trong header **`Referer`** khi trình duyệt điều hướng hoặc tải resource. | Sang đối tác chỉ gửi origin `https://app.example.com/` thay vì URL có query. |
| `Permissions-Policy` | Giới hạn những browser features mà tài liệu hiện tại và các tài liệu nhúng có thể dùng. | Trang quản trị không cần webcam: `camera=()`. |

**Dễ nhầm tên:** Header yêu cầu HTTP truyền thống đánh vần `Referer` (một chữ **r** giữa *refe* và *er*) vì lý do lịch sử; header cấu hình phản hồi là `Referrer-Policy` (đánh vần đầy đủ). Trong JS còn có `document.referrer`.

Hai policy được **trình duyệt hỗ trợ và thực thi**. HTTP client không phải browser có thể bỏ qua chúng. Chúng **không thay thế authentication, authorization, CSRF, XSS/CSP, CORS hoặc mã hóa HTTPS**.

## 2. Referrer-Policy: browser gửi gì trong Referer?

Một **origin** là bộ ba `scheme + host + port`. Ví dụ:

- `https://app.example.com/user/42` và `https://app.example.com/reports` **cùng origin**.
- `https://app.example.com` và `https://api.example.com` **khác origin** vì host khác.
- `http://localhost:8080` và `http://localhost:3000` **khác origin** vì port khác.
- `https://example.com` và `http://example.com` **khác origin** vì scheme khác.

Giả sử tài liệu nguồn là:

```text
https://app.example.com/orders/123?view=detail
```

Trang này điều hướng tới `https://partner.example.net/pay`:

- Một policy cho phép **full URL** có thể làm destination nhận `Referer: https://app.example.com/orders/123?view=detail`.
- Một policy chỉ cho **origin** sẽ khiến destination nhận `Referer: https://app.example.com/`.
- Policy `no-referrer` không gửi header `Referer`.

**URL fragment** như `#section` không nằm trong `Referer`; username/password trong URL cũng bị loại bỏ theo quy tắc xử lý referrer. Dù vậy, path và query có thể chứa ID, từ khóa tìm kiếm, tham số nghiệp vụ; tốt nhất là **không nhét session token, password hay dữ liệu bí mật vào URL** ngay từ đầu.

### 2.1 Những giá trị quan trọng

| Giá trị `Referrer-Policy` | Điều hướng/tải cùng origin | Chuyển sang origin khác | Từ HTTPS xuống HTTP | Khi nên cân nhắc |
| --- | --- | --- | --- | --- |
| `no-referrer` | Không có `Referer` | Không có `Referer` | Không có `Referer` | Trang rất nhạy cảm; ưu tiên giảm lộ nguồn. |
| `same-origin` | Gửi URL nguồn (không fragment) | Không gửi `Referer` | Không gửi khi khác origin | Muốn thông tin referrer phục vụ các luồng nội bộ. |
| `strict-origin-when-cross-origin` | Gửi URL nguồn (không fragment) | Chỉ gửi **origin** | Không gửi `Referer` | Lựa chọn cân bằng cho nhiều ứng dụng. |
| `strict-origin` | Chỉ origin | Chỉ origin | Không gửi `Referer` | Muốn giảm path/query cả trong nội bộ. |
| `origin` | Chỉ origin | Chỉ origin | Policy không tự chặn khi hạ cấp | Phân tích nguồn ở mức domain, cần cân nhắc downgrade. |
| `no-referrer-when-downgrade` | Gửi URL nguồn | Gửi URL nguồn | Không gửi khi downgrade | Di sản; có nguy cơ lộ path/query sang site HTTPS khác. |
| `unsafe-url` | Gửi URL nguồn | Gửi URL nguồn | Có thể gửi cả khi downgrade | Tránh dùng cho URL chứa thông tin nhạy cảm. |

**`strict-origin-when-cross-origin`** là mặc định của nhiều trình duyệt hiện đại khi không có policy tường minh. Tuy nhiên, ứng dụng vẫn nên **cấu hình chủ động** theo nhu cầu bảo mật và kiểm thử của mình để tránh phụ thuộc vào mặc định của môi trường.

Ví dụ với `strict-origin-when-cross-origin`:

```text
Tài liệu nguồn: https://app.example.com/orders/123?view=detail

→ https://app.example.com/help
  Referer: https://app.example.com/orders/123?view=detail

→ https://analytics.partner.example/collect
  Referer: https://app.example.com/

→ http://legacy.partner.example/collect
  (Không có Referer vì HTTPS → HTTP)
```

Đây là **minh họa hành vi browser theo policy**; `Referer` cũng có thể vắng mặt vì thuộc tính của phần tử, thiết lập quyền riêng tư hoặc môi trường triển khai.

### 2.2 Đặt policy ở đâu?

Đặt response header trên **tài liệu nguồn** mà browser tải, chẳng hạn trang HTML:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Referrer-Policy: strict-origin-when-cross-origin
```

Policy kiểm soát **các request tiếp theo phát sinh từ tài liệu đó**. Nếu chỉ đặt header vào response JSON của API mà HTML chính được một CDN/ứng dụng khác phục vụ, chưa chắc bạn đã đặt đúng policy cho liên kết điều hướng của trang. Cần xem **response HTML thật sự** trong DevTools.

Có các điểm cấu hình hẹp hơn, được sử dụng khi cần:

```html
<!-- Policy cho toàn tài liệu nếu chưa/không đặt response header phù hợp. -->
<meta name="referrer" content="no-referrer">

<!-- Chỉ riêng một liên kết không gửi referrer. -->
<a href="https://external.example/path" rel="noreferrer">Trang ngoài</a>

<!-- Chính sách referrer riêng cho một tài nguyên/element hỗ trợ. -->
<img src="https://images.example/photo.png"
     referrerpolicy="no-referrer"
     alt="Ảnh minh họa">
```

JavaScript `fetch()` cũng hỗ trợ option `referrerPolicy`:

```javascript
fetch("https://api.example.net/public", {
  referrerPolicy: "no-referrer"
});
```

Đừng coi thẻ `meta` hay option riêng lẻ là cách thay thế mặc định cho chính sách server với toàn ứng dụng. Ưu tiên một policy ở **HTTP response** của tài liệu và chỉ ghi đè tại những link/resource có lý do rõ ràng.

### 2.3 Những điều Referrer-Policy không làm

- **Không xóa** URL khỏi lịch sử trình duyệt, access log của chính server, analytics nội bộ hay thanh địa chỉ.
- **Không mã hóa** nội dung query và không bảo vệ bí mật nằm sẵn trong URL; dùng HTTPS và giữ dữ liệu nhạy cảm ngoài URL.
- **Không ngăn request** được gửi tới bên thứ ba; chỉ giới hạn mức thông tin nguồn trong `Referer`. Muốn kiểm soát địa chỉ được phép kết nối, cân nhắc CSP `connect-src`, `img-src`, v.v.
- **Không thay đổi** quy tắc CORS hoặc header `Origin` của request. Một request có thể không có `Referer` nhưng vẫn có `Origin`.
- **Không phải** bộ lọc chống CSRF. Kiểm tra CSRF cần cơ chế phù hợp riêng; không dựa vào `Referer` như một định danh đăng nhập đáng tin cậy.
- **Không xóa ngược** `document.referrer` mà trang đích đã nhận ở một điều hướng trước: cần điều khiển từ phía **tài liệu nguồn**.

## 3. Permissions-Policy: giới hạn browser capabilities

`Permissions-Policy` là HTTP response header chỉ định những **feature** mà tài liệu, và trong điều kiện thích hợp các iframe con, được phép dùng. Có thể áp dụng cho một số tính năng như:

- `camera`: API dùng camera.
- `microphone`: API dùng microphone.
- `geolocation`: vị trí.
- `fullscreen`: toàn màn hình.
- `payment`: Payment Request API ở những browser hỗ trợ.

Hỗ trợ tính năng và directive **khác nhau theo trình duyệt/phiên bản**; không suy ra rằng mọi feature name đều được thực thi đồng đều. Cấu hình chính sách theo những API thực sự được dùng và kiểm thử trên browser mục tiêu.

### 3.1 Cú pháp allowlist thường gặp

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
```

Diễn giải:

- `camera=()`: **không tài liệu nào trong phạm vi policy này** được phép dùng camera thông qua capability đang bị giới hạn.
- `microphone=()`: tương tự cho microphone.
- `geolocation=(self)`: cho phép document cùng origin trong phạm vi policy; **không tự đồng ý yêu cầu lấy vị trí của người dùng**. Browser vẫn phải thỏa điều kiện secure context, user permission và các cơ chế khác.

Cú pháp:

| Cú pháp | Ý nghĩa tổng quát | Rủi ro/lưu ý |
| --- | --- | --- |
| `camera=()` | Danh sách cho phép rỗng: chặn camera. | Chặn cả ứng dụng chính nếu thật sự cần camera. |
| `camera=(self)` | Cho tài liệu cùng origin dùng camera, nếu các điều kiện khác cho phép. | Không thay thế hộp thoại xin quyền người dùng. |
| `geolocation=(self "https://maps.partner.example")` | Thêm origin cụ thể vào danh sách được xét cho phép. | Nếu nhúng iframe khác origin, còn cần chính sách kế thừa/`allow` thích hợp. |
| `microphone=*` | Wildcard cho các origin mà cơ chế policy xét tới. | Quá rộng cho đa số ứng dụng; hạn chế dùng. |

**Chú ý cú pháp:** `self` là token không có dấu nháy; một origin cụ thể trong danh sách header được **đặt trong dấu nháy kép**. Dấu ngoặc đơn `()` nghĩa là tập rỗng, không phải ký hiệu comment. Các directive header ngăn nhau bằng dấu phẩy.

Permissions-Policy **không đồng nghĩa với “cấp quyền truy cập camera/vị trí”**. Ngay cả khi `camera=(self)`, browser vẫn yêu cầu bối cảnh bảo mật HTTPS, quyền người dùng và các điều kiện riêng của API. Ngược lại, nếu policy cấm `camera=()`, lời gọi JavaScript có thể bị từ chối ngay cả khi người dùng đã từng cấp quyền camera cho site.

### 3.2 Iframe và việc phân quyền xuống tài liệu nhúng

Giả sử dashboard ở `https://app.example.com` nhúng một widget bản đồ từ `https://maps.partner.example`:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(self "https://maps.partner.example")
```

Phía HTML của parent có thể có:

```html
<iframe
  src="https://maps.partner.example/widget"
  allow="geolocation"
  title="Bản đồ">
</iframe>
```

Các điểm cần nhớ:

1. Parent response header phải cho phép origin của iframe trong **feature allowlist** thích hợp.
2. Với iframe **khác origin**, cần cơ chế delegation qua thuộc tính `allow` của iframe, theo chính sách của browser/feature. Chỉ có header cho phép origin chưa chắc đủ.
3. Chính sách hữu hiệu chịu sự **giao nhau của các ràng buộc** từ ancestor, iframe container và policy của document nhúng; con không thể tự tăng quyền bị cha từ chối.
4. Một số feature đòi hỏi secure context, user gesture hoặc quyền người dùng, kể cả sau khi policy cho phép.

**Phân biệt với chống clickjacking:** `Permissions-Policy` kiểm soát **khả năng web platform**, không quyết định site có được nhúng trong iframe hay không. Để kiểm soát bên nào **được nhúng trang của bạn**, xem CSP `frame-ancestors`, `X-Frame-Options` và các ràng buộc liên quan. Để kiểm soát iframe của bạn được tải từ đâu, dùng CSP `frame-src` và chính sách ứng dụng.

Header cũ `Feature-Policy` là cơ chế tiền nhiệm; với ứng dụng mới nên ưu tiên `Permissions-Policy` và xác minh hỗ trợ thực tế trên browser mục tiêu. Đừng dựa vào một thẻ `<meta http-equiv="Permissions-Policy">` như cấu hình thay thế HTTP header: việc hỗ trợ khai báo policy kiểu này không tương đương response header.

## 4. Chọn policy theo nhu cầu ứng dụng, không dùng một cấu hình cho tất cả

Không nên copy nguyên cấu hình của một hệ thống khi chưa biết sản phẩm có dùng camera, micro, geolocation hoặc analytics ra ngoài hay không.

| Kiểu ứng dụng | Referrer-Policy gợi ý | Permissions-Policy gợi ý | Lý do và điều cần thử |
| --- | --- | --- | --- |
| Website giới thiệu / docs có link ngoài | `strict-origin-when-cross-origin` | `camera=(), microphone=(), geolocation=()` nếu không dùng các API đó | Giữ attribution ở mức origin; giảm bề mặt API. |
| Dashboard nội bộ có URL chứa thông tin nhạy cảm | `same-origin` hoặc `no-referrer` | Chặn camera/mic/geo nếu không dùng | Tránh lộ path/query ra bên thứ ba; kiểm tra luồng analytics/SSO có phụ thuộc referrer không. |
| Ứng dụng y tế/tài chính có nhiều liên kết ra ngoài | Thường cân nhắc `no-referrer` | Mặc định chặn feature không cần | Giảm tối đa thông tin nguồn; kiểm tra nghiệp vụ cần referrer nội bộ. |
| Ứng dụng bản đồ cần định vị | `strict-origin-when-cross-origin` hoặc chính sách chặt hơn | `geolocation=(self), camera=(), microphone=()` | Cho phép đúng feature cần; browser vẫn hỏi quyền vị trí. |
| Ứng dụng họp video cùng origin | Chọn theo luồng điều hướng thực tế | `camera=(self), microphone=(self)` | Chặn tất cả sẽ làm họp video không thể hoạt động. |
| Portal nhúng widget đối tác | Xem URL nào có thể lộ qua điều hướng tới đối tác | Chỉ thêm **origin đối tác tin cậy** cho feature cần + iframe `allow` | Kiểm tra delegation và sự hỗ trợ browser; không cho toàn bộ wildcard. |

**Cách ra quyết định:**

1. Liệt kê trang nào dùng tính năng nào (camera, microphone, geolocation, fullscreen, payment, iframe) và các dịch vụ ngoài mà người dùng điều hướng tới.
2. Chọn `Referrer-Policy` dựa vào **mức tối đa thông tin nguồn có thể chia sẻ**. Nếu không cần gửi referrer đi đâu, `no-referrer` hợp lý; nếu cần analytics mức origin, `strict-origin-when-cross-origin` thường cân bằng hơn.
3. Với Permissions-Policy, **chặn rõ ràng tính năng không dùng**, cho phép những origin thực sự cần, tránh wildcard khi không có lý do.
4. Kiểm thử hành vi thật với trang cùng origin, trang khác origin, iframe, trình duyệt đích, HTTPS và quyền người dùng. Theo dõi lỗi tính năng sau khi triển khai.

Ví dụ website có tính năng thanh toán nhưng không có camera: không suy ra cứ là ứng dụng thanh toán thì phải cho phép `payment`. Chỉ bật nếu thật sự dùng Payment Request API; thanh toán qua redirect/iframe của nhà cung cấp có thể có yêu cầu khác và phải kiểm tra chính sách tích hợp cụ thể.

## 5. Spring Security Servlet: cấu hình hai header trên SecurityFilterChain

Spring Security có thể quản lý nhiều response security headers qua `HttpSecurity.headers`. Các header `Referrer-Policy` và `Permissions-Policy` nên được **cấu hình tường minh**; không giả định rằng bộ header mặc định đã cung cấp đúng policy ứng dụng mong muốn.

Ví dụ dưới đây sử dụng các API DSL của **Spring Security 6.x**, chạy trong Spring Boot 3.x. Ứng dụng minh họa:
- Dùng `strict-origin-when-cross-origin` cho outbound navigation.
- Chặn camera/micro, chỉ cho phép geolocation của chính origin.
- Cho phép GET demo để kiểm tra header; trong ứng dụng thực tế, đặt rules xác thực/phân quyền theo nhu cầu.

**`src/main/java/com/example/httpheaders/SecurityConfig.java`**

```java
package com.example.httpheaders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth ->
                auth.anyRequest().permitAll());

        http.headers(headers -> {
            headers.referrerPolicy(referrer -> referrer.policy(
                ReferrerPolicyHeaderWriter.ReferrerPolicy
                    .STRICT_ORIGIN_WHEN_CROSS_ORIGIN
            ));

            headers.permissionsPolicy(permissions -> permissions.policy(
                "camera=(), microphone=(), geolocation=(self)"
            ));
        });

        return http.build();
    }
}
```

**`src/main/java/com/example/httpheaders/DemoController.java`**

```java
package com.example.httpheaders;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/demo/info")
    public Map<String, String> info() {
        return Map.of("status", "ok");
    }
}
```

**`src/main/java/com/example/httpheaders/HttpHeadersApplication.java`**

```java
package com.example.httpheaders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpHeadersApplication.class, args);
    }
}
```

Các file trên **không biên dịch bằng `javac` thuần** vì phụ thuộc Spring. Tạo một project Spring Boot 3.x bằng Spring Initializr, chọn **Java 17+**, Spring Web, Spring Security. Đặt package đúng như trên và dùng Gradle wrapper được project tạo sẵn:

```bash
./gradlew bootRun
```

Trên Windows PowerShell, chạy `.\gradlew.bat bootRun`. Với cấu hình mặc định, ứng dụng nghe cổng `8080` và trả JSON từ `GET /demo/info`.

Kiểm tra:

```bash
curl -i http://localhost:8080/demo/info
```

Phần header và body liên quan sẽ tương đương:

```http
HTTP/1.1 200
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
Content-Type: application/json

{"status":"ok"}
```

Server thực tế có thể thêm các header khác và thay đổi thứ tự hiển thị. Giá trị hai header trên là kết quả cấu hình cần kiểm tra; `200` và JSON là kết quả endpoint demo.

**Lưu ý về phạm vi SecurityFilterChain:** Các header trên được phát cho response đi qua filter chain này. Nếu ứng dụng có nhiều `SecurityFilterChain` với matcher/`@Order` khác nhau, cần xác nhận **chain áp dụng cho HTML, API và các đường dẫn liên quan**. Nếu HTML do nginx/CDN phục vụ, cấu hình backend Spring không tự chèn header cho trang HTML ở CDN: phải cấu hình ở tầng thực sự trả response đó.

### 5.1 Biến thể policy theo môi trường

Với dashboard cực kỳ nhạy cảm, thay phần Referrer-Policy bằng:

```java
headers.referrerPolicy(referrer -> referrer.policy(
    ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER
));
```

Nếu website không dùng geolocation, thay policy thành:

```java
headers.permissionsPolicy(permissions -> permissions.policy(
    "camera=(), microphone=(), geolocation=()"
));
```

Nếu chính ứng dụng cần camera và microphone:

```java
headers.permissionsPolicy(permissions -> permissions.policy(
    "camera=(self), microphone=(self), geolocation=()"
));
```

Những đoạn trên là **biến thể thay thế** một phần cấu hình trong `SecurityConfig`, **không phải** các lệnh thêm vào sau cấu hình hiện tại để tạo nhiều giá trị header xung đột.

Trong hệ thống lớn, policy có thể được chọn theo profile hoặc theo nhóm route/ứng dụng, nhưng hãy đảm bảo **không phát nhiều bản Referrer-Policy/Permissions-Policy trái nhau** từ Spring, gateway và CDN; kiểm tra **HTTP response cuối cùng** thực sự tới trình duyệt.

### 5.2 Tránh tắt các security header mặc định

`http.headers(...)` là vị trí tích hợp policy; trong ví dụ này **không gọi** `defaultsDisabled()` và không tắt `headers` toàn bộ. Nếu sử dụng `defaultsDisabled()` rồi chỉ bật hai policy mới, bạn có thể vô tình bỏ những security headers mặc định khác (ví dụ những header hỗ trợ chống MIME sniffing hoặc framing). Chỉ thay đổi những giá trị cần thiết, không làm giảm lớp bảo vệ sẵn có.

Một số browser có thể bỏ qua directive Permissions-Policy mà chúng không hỗ trợ. Header xuất hiện trong Network **chưa đủ** để kết luận tính năng bị chặn: phải thử API hoặc iframe thực tế trên browser mục tiêu.

## 6. Kiểm chứng bằng automated test và trình duyệt

Kiểm tra ở **hai tầng**: (1) server có phát đúng header không, (2) browser có thực thi đúng hành vi mong muốn không.

### 6.1 Spring MVC test cho header

Với dependency kiểm thử `spring-boot-starter-test`, thêm file:

**`src/test/java/com/example/httpheaders/SecurityHeadersTest.java`**

```java
package com.example.httpheaders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTest {

    @Autowired
    MockMvc mvc;

    @Test
    void sendsSecurityPolicyHeaders() throws Exception {
        mvc.perform(get("/demo/info"))
           .andExpect(status().isOk())
           .andExpect(header().string(
               "Referrer-Policy", "strict-origin-when-cross-origin"))
           .andExpect(header().string(
               "Permissions-Policy",
               "camera=(), microphone=(), geolocation=(self)"));
    }
}
```

Dùng project Gradle đã có wrapper:

```bash
./gradlew test
```

Windows: `.\gradlew.bat test`. Test chỉ xác minh **filter chain phát đúng header ở endpoint được thử**. Nó không chứng minh browser có gửi `Referer` đúng hoặc chặn camera/geo đúng trong mọi browser; cần test thủ công/integration phù hợp.

### 6.2 Thử Referrer-Policy đúng cách

1. Phục vụ một **trang HTML nguồn** `https://app.example.com/page` và bảo đảm **response HTML** có header Referrer-Policy đang kiểm thử.
2. Đặt link từ trang đó tới một origin thử nghiệm khác mà bạn kiểm soát, ví dụ `https://receiver.example.net/inspect`. Receiver nên ghi nhận request `Referer` một cách an toàn trong môi trường test (không thu thập dữ liệu thật).
3. Với `strict-origin-when-cross-origin`, ở request cross-origin HTTPS → HTTPS, receiver nên thấy **chỉ origin** của trang nguồn. Với `no-referrer`, receiver không nên thấy `Referer`.
4. Đặt thêm link **same-origin** để xác minh sự khác nhau giữa `same-origin` và `strict-origin-when-cross-origin`. Nếu kiểm tra trường hợp HTTPS → HTTP downgrade, dùng môi trường thử nghiệm phù hợp và chú ý browser có thể ngăn/mang thêm hạn chế khác.
5. Trong DevTools → **Network → Request Headers**, xem `Referer` của **request điều hướng đi**, thay vì chỉ xem response header ở trang đích. Nếu không có header, kiểm tra thêm `rel=noreferrer`, thuộc tính `referrerpolicy`, privacy settings và browser.

Không dùng cách gọi `curl -H "Referer: ..."` để khẳng định một policy Referrer-Policy được thực thi: curl chỉ gửi header do bạn tự khai báo, không mô phỏng chính sách trình duyệt.

### 6.3 Thử Permissions-Policy đúng cách

Dùng DevTools → **Network → Response Headers** để xác nhận header. Sau đó kiểm tra browser feature thực tế:

```javascript
async function tryCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true
    });
    console.log("Camera available for this document");
    stream.getTracks().forEach(track => track.stop());
  } catch (error) {
    console.log(error.name, error.message);
  }
}

tryCamera();
```

Khi chính sách `camera=()` đang có hiệu lực, browser hỗ trợ feature này sẽ không cấp quyền camera cho tài liệu, dù API JavaScript có mặt. Lỗi cụ thể và thông báo console phụ thuộc browser; `NotAllowedError` là một khả năng thường gặp. Trong môi trường **HTTP thường không an toàn**, `navigator.mediaDevices` có thể không tồn tại; do đó để xác minh chính sách thật sự, dùng **HTTPS** (hoặc `localhost` được browser coi là trustworthy trong các trường hợp phù hợp).

Đối với geolocation, sau khi thay `geolocation=(self)`:

```javascript
navigator.geolocation.getCurrentPosition(
  pos => console.log("Got position", pos.coords.latitude),
  err => console.log("Position error", err.code, err.message)
);
```

Có policy cho phép chỉ nghĩa là browser **có thể tiếp tục xét quyền người dùng**; người dùng vẫn có thể từ chối hoặc thiết bị không hỗ trợ định vị. Vì vậy, việc không lấy được vị trí không tự chứng minh Permissions-Policy chặn.

Với iframe đối tác, kiểm thử cả (a) header của parent, (b) thuộc tính `allow`, (c) quyền và secure context bên trong iframe. Header trên parent không thể ép một iframe dùng tính năng mà nó tự từ chối.

## 7. Các lỗi thực tế và cách xử lý

| Hiện tượng | Phân biệt nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Link từ trang nhạy cảm vẫn làm lộ path/query | Chưa đặt header trên **HTML nguồn**; policy quá thoáng; CDN ghi đè; link có override. | Kiểm tra response HTML nguồn và outgoing request, chuyển sang `same-origin`/`no-referrer` nếu phù hợp. |
| Analytics bên thứ ba không thấy URL đầy đủ | `strict-origin-when-cross-origin` chỉ gửi origin qua cross-origin. | Xem đây là hành vi đúng thiết kế; dùng cơ chế analytics được kiểm soát, không nới policy chỉ để lộ URL. |
| `document.referrer` ở trang đích có giá trị không như mong đợi | Bị chi phối bởi **trang nguồn** và cách điều hướng, không chỉ header của trang đích. | Kiểm tra policy của trang nguồn và network request liên quan. |
| Camera không bật, browser báo Permissions-Policy violation | `camera=()` hoặc policy ancestor/iframe không cho phép. | Chỉ mở `camera=(self)` hoặc allowlist origin có nhu cầu thật; vẫn giữ user permission. |
| Iframe có `allow="geolocation"` mà vẫn bị chặn | Header của parent không cho origin iframe, parent chain chặn, hoặc browser/user permission không đạt. | Kiểm tra policy giao nhau, origin chính xác, secure context và quyền người dùng. |
| Geolocation vẫn thất bại dù `geolocation=(self)` | Người dùng từ chối, trình duyệt chặn quyền, thiếu HTTPS hoặc thiết bị thiếu hỗ trợ. | Xem console/Permissions/API error riêng; đừng mặc định lỗi header. |
| Header hiển thị khi gọi API nhưng trang HTML thiếu | HTML do static server/CDN trả về, không qua SecurityFilterChain. | Đặt policy ở nơi phục vụ HTML; test response cuối cùng. |
| Header bị nhân đôi hoặc giá trị bất nhất | Cùng lúc cấu hình Spring, reverse proxy, CDN hoặc filter tùy biến. | Chọn rõ tầng chịu trách nhiệm; kiểm tra header thật và loại bỏ cấu hình xung đột. |
| Browser A chặn nhưng browser B bỏ qua directive | Hỗ trợ Permissions-Policy feature không đồng đều. | Dùng kiểm thử đa trình duyệt, thêm kiểm tra quyền và kiểm soát server; không dựa toàn bộ bảo mật vào directive chưa hỗ trợ. |

**Không tạo chính sách từ các chuỗi không tin cậy.** Nếu feature allowlist hoặc referrer policy phụ thuộc cấu hình động, chỉ đọc từ tập giá trị đã được quản trị/kiểm chứng. Không cho người dùng bên ngoài đưa tùy ý origin vào Permissions-Policy hoặc trả header xung đột.

## 8. Mối quan hệ với các HTTP security headers khác

Đặt đúng hai policy mới chỉ là một phần của hardening:

- **Content-Security-Policy (CSP):** giới hạn nguồn script, style, image, network và frame. Giúp giảm một số đường khai thác XSS; `frame-ancestors` kiểm soát ai có thể nhúng trang của bạn. `Permissions-Policy` không thay thế CSP.
- **X-Frame-Options / CSP `frame-ancestors`:** chống clickjacking bằng cách hạn chế embedding; không tương đương `camera=()` hay `microphone=()`.
- **Strict-Transport-Security:** chỉ đạo browser tiếp tục kết nối HTTPS khi đã học chính sách HSTS; không quyết định thông tin referrer được gửi.
- **X-Content-Type-Options: nosniff:** giảm nguy cơ xử lý MIME sai, không liên quan quyền camera/vị trí.
- **Cache-Control** với dữ liệu riêng tư: giảm rủi ro lưu cache sai; không thay thế Referrer-Policy.
- **CORS:** điều khiển website khác có được đọc response cross-origin không; **khác** việc quyết định browser feature nào hoạt động và URL nguồn lộ bao nhiêu.

Đối với ứng dụng xác thực bằng cookie, vẫn cần chống CSRF phù hợp; đối với dữ liệu riêng tư, vẫn cần server-side authorization. Các header browser có thể giảm bề mặt tấn công, nhưng **không biến một endpoint không được bảo vệ thành endpoint an toàn**.

## 9. Bài tập lựa chọn và kiểm tra nhanh

**Tình huống A — admin console:** Dashboard có URL `/customers/123?view=billing`, chỉ điều hướng ra trang tài liệu hỗ trợ; không cần camera/mic/geo. Có thể chọn:

```http
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Sau triển khai, test mở link hỗ trợ từ trang nhạy cảm và kiểm tra outgoing `Referer`; xác minh tính năng tìm kiếm nội bộ và analytics còn hoạt động như yêu cầu.

**Tình huống B — sản phẩm có bản đồ nội bộ:** Trang có định vị người dùng, không dùng camera/microphone, và cần ghi nhận domain giới thiệu từ các liên kết ngoài:

```http
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```

Test trên HTTPS với người dùng đã/ chưa cấp quyền vị trí và theo nhiều browser. **Policy cho phép geolocation không tự lấy được tọa độ**.

**Tình huống C — call center họp video:** Trang cùng origin cần camera và microphone. Có thể chọn `camera=(self), microphone=(self)`; kiểm tra browser prompt và thiết bị. Đặt `camera=()` theo template của trang admin sẽ làm hỏng nghiệp vụ gọi video.

**Tình huống D — nhúng map đối tác:** Có iframe của `https://maps.partner.example` cần geolocation. Header cần cho phép đúng origin đối tác; iframe cần `allow` thích hợp; quyền người dùng và secure context vẫn bắt buộc. Đừng mở `geolocation=*` chỉ để làm demo hoạt động.

### Checklist trước khi phát hành

- Đã xác định chính xác **HTML source** của ứng dụng và tầng phát response header (Spring/CDN/proxy).
- `Referrer-Policy` phù hợp với thông tin URL được phép tiết lộ **cùng origin, khác origin và khi downgrade**.
- Không chứa dữ liệu bí mật trong path/query mà chỉ dựa vào policy để giấu.
- Mỗi Permissions-Policy directive có lý do nghiệp vụ, origin được tin cậy, không mở wildcard vô cớ.
- Các luồng camera/microphone/location/iframe thực sự được thử trên browser mục tiêu và HTTPS.
- Header không bị nhân đôi, không làm mất các security headers mặc định khác.
- Authentication, authorization, CSRF, CSP, cookie và HTTPS vẫn được kiểm soát riêng.

**Ghi nhớ:** `Referrer-Policy` điều khiển **lượng thông tin nguồn của request**; `Permissions-Policy` điều khiển **tập browser features có thể được sử dụng**. Chọn cả hai dựa trên sản phẩm: mặc định chia sẻ referrer ít nhất cần thiết, đóng những API không dùng, mở rõ ràng những API cần thiết và đo hiệu quả ở **response HTML + hành vi trình duyệt thực tế**.
