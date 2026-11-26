# HPKP, Feature-Policy và các chính sách trình duyệt đã thay đổi

> **Chương:** Nâng cấp và tương thích  
> **Phạm vi:** Bảo vệ HTTP và trình duyệt trong Spring Security (Servlet và Reactive/WebFlux).  
> **Mục tiêu:** Nhận diện các cơ chế đã lỗi thời, hiểu sự khác biệt về cú pháp và tác dụng của các chính sách thay thế, chuyển cấu hình an toàn và kiểm tra hành vi thực tế trên trình duyệt.

## 1. Vì sao nâng cấp Spring Security còn phải kiểm tra chính sách trình duyệt?

Ứng dụng có thể vẫn khởi động thành công sau khi nâng cấp Spring Security nhưng các HTTP response header lại không còn ý nghĩa như trước. Một số trình duyệt đã **bỏ hỗ trợ** cơ chế cũ; một số header được **đổi tên kèm đổi cú pháp**; các cơ chế khác vẫn tồn tại nhưng không được Spring Security tự cấu hình vì phải biết đặc thù của ứng dụng.

Phải phân biệt ba lớp:

1. **Máy chủ gửi header:** Spring Security, reverse proxy, CDN hoặc gateway có thể cùng tham gia tạo response.
2. **Trình duyệt hiểu và thực thi:** Header xuất hiện trong Network tab chưa đủ chứng minh trình duyệt đang áp dụng chính sách.
3. **Ứng dụng vận hành đúng:** Một chính sách quá chặt có thể chặn camera, bản đồ nhúng, thanh toán, script, iframe hoặc làm hỏng luồng đăng nhập.

Bảng dưới giúp xác định hướng xử lý khi kiểm tra cấu hình cũ:

| Cơ chế | Tình trạng và ý nghĩa hiện nay | Hướng xử lý |
|---|---|---|
| `Public-Key-Pins` (HPKP) và `Public-Key-Pins-Report-Only` | Cơ chế pin khóa công khai qua HTTP đã lỗi thời; Chrome đã bỏ hỗ trợ và Firefox bỏ từ phiên bản 72. | Ngừng phát header; quản trị chứng chỉ, HTTPS/HSTS, Certificate Transparency (CT) và giám sát phát hành chứng chỉ. |
| `Feature-Policy` | Được thay thế bởi **Permissions Policy**; đổi cả cú pháp của HTTP header. | Di chuyển sang `Permissions-Policy` và kiểm tra chỉ thị được hỗ trợ trên trình duyệt mục tiêu. |
| `Expect-CT` | Đã lỗi thời; Chromium bỏ từ phiên bản 107 khi CT được thực thi theo chính sách trình duyệt. | Không triển khai mới; giám sát CT và quy trình cấp/thu hồi chứng chỉ. |
| `X-XSS-Protection` | Bộ lọc XSS lịch sử có thể gây tác dụng phụ; trình duyệt hiện đại không dựa vào cơ chế này. | Dùng encode/escape đầu ra và CSP phù hợp. Giá trị `X-XSS-Protection: 0` trong mặc định Spring Security là chủ ý. |
| `X-Frame-Options` | Vẫn hữu ích cho tương thích; CSP `frame-ancestors` biểu đạt chính sách nhúng linh hoạt hơn. | Giữ cơ chế phù hợp với đối tượng trình duyệt, thống nhất với `frame-ancestors`. |
| `Referrer-Policy`, CSP, COOP/COEP/CORP | Các chính sách đang được dùng để kiểm soát lộ thông tin, tải tài nguyên và cô lập ngữ cảnh. | Thiết kế theo nghiệp vụ và khả năng hỗ trợ; thử nghiệm trước khi bật hạn chế mạnh. |

**Không có một header mới nào thay thế toàn bộ HPKP, Feature-Policy và các header cũ.** Mỗi chính sách bảo vệ một ranh giới khác nhau.

## 2. HPKP: vì sao cơ chế pin khóa công khai bị loại bỏ?

### 2.1. HPKP từng giải quyết vấn đề gì?

Trong HTTPS thông thường, trình duyệt tin vào chứng chỉ khi chuỗi xác thực dẫn đến một CA đáng tin cậy và thỏa các quy tắc TLS. HPKP (RFC 7469) bổ sung một ràng buộc: sau khi nhận header `Public-Key-Pins` qua kết nối HTTPS hợp lệ, trình duyệt ghi nhớ các mã băm khóa công khai (SPKI) được chấp nhận cho máy chủ trong khoảng `max-age`.

Mục đích là giảm rủi ro kẻ tấn công dùng chứng chỉ cấp sai nhưng vẫn được một CA tin cậy ký. Tuy nhiên, pin khóa sai hoặc mất quyền truy cập khóa dự phòng có thể làm **người dùng không vào được website**, kể cả khi máy chủ đang có chứng chỉ TLS hợp lệ. Cơ chế này còn tạo nguy cơ *hostile pinning*: kẻ có quyền kiểm soát nhất thời đối với máy chủ có thể khiến trình duyệt ghi nhớ pin gây gián đoạn lâu dài.

Vì tỉ lệ sử dụng thấp và rủi ro vận hành, Chrome đã loại bỏ HPKP; Firefox 72 (07/01/2020) cũng ngừng xử lý cả hai header `Public-Key-Pins` và `Public-Key-Pins-Report-Only`.

### 2.2. Di chuyển khỏi HPKP

**Không sao chép cấu hình HPKP cũ sang dự án Spring Security mới.** Tài liệu tham khảo của Spring Security vẫn có thể hiển thị API HPKP cho Servlet nhằm tương thích với ứng dụng cũ, nhưng chính Spring Security không khuyến nghị sử dụng. Việc một phương thức cấu hình còn tồn tại **không chứng minh header được trình duyệt thực thi**.

Các biện pháp nên phối hợp:

- **HTTPS và HSTS:** chuyển hướng HTTP sang HTTPS; dùng `Strict-Transport-Security` để trình duyệt tránh truy cập HTTP ở các lần sau. HSTS chống hạ cấp giao thức, **không** pin chứng chỉ và **không** thay HPKP theo tỉ lệ 1:1.
- **Quản trị chứng chỉ:** tự động gia hạn, quản lý khóa riêng, kiểm tra hạn, chuỗi CA, tên miền và kế hoạch xoay khóa; xử lý nhanh khi thu hồi chứng chỉ.
- **Certificate Transparency:** theo dõi log CT để nhận diện chứng chỉ bất thường được phát hành cho tên miền. Đây là giám sát/phát hiện, **không phải** cơ chế pin khóa cho máy khách.
- **DNS CAA (nếu phù hợp):** giới hạn CA được phép cấp chứng chỉ theo chính sách DNS; không thay cho CT hay kiểm tra chứng chỉ ở phía trình duyệt.
- **Bỏ `Expect-CT` nếu còn tồn tại:** tài liệu cũ từng giới thiệu `Expect-CT` như phương án thay HPKP; hiện header đó cũng đã lỗi thời nên không nên dùng làm đích di chuyển mới.

Ví dụ HSTS do Spring Security thường phát trên **response HTTPS**:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

`includeSubDomains` chỉ phù hợp khi **mọi subdomain liên quan đều phục vụ HTTPS đúng cách**. Đối với HSTS preload, cần đánh giá thêm điều kiện tham gia và khả năng hoàn tác, tránh bật như một thao tác máy móc. Response HTTP thuần không phải nơi browser học chính sách HSTS đáng tin cậy.

## 3. Từ Feature-Policy sang Permissions-Policy

### 3.1. Cú pháp header thay đổi

`Feature-Policy` từng quản lý quyền sử dụng các browser API như geolocation, camera, microphone, autoplay hoặc fullscreen. Chính sách kế thừa tên **Permissions Policy** với cú pháp HTTP header mới theo dạng `directive=(allowlist)`.

**Cũ (chỉ để nhận diện khi kiểm tra hệ thống):**

```http
Feature-Policy: geolocation 'self'; camera 'none'; microphone 'none'
```

**Mới:**

```http
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```

Các điểm cần nhớ:

| Cú pháp mới | Ý nghĩa |
|---|---|
| `geolocation=()` | Không cấp quyền sử dụng API vị trí cho các origin trong phạm vi chính sách. |
| `geolocation=(self)` | Chỉ cho phép origin hiện tại theo chính sách này. |
| `geolocation=(self "https://maps.example")` | Cho phép origin hiện tại và origin được liệt kê có khả năng sử dụng tính năng, nếu các điều kiện khác cũng cho phép. |
| `camera=*` | Không hạn chế camera theo origin bằng directive này; **không** tự động chấp thuận quyền người dùng. |
| `camera=(), microphone=()` | Chặn cả camera và microphone bằng Permissions Policy. |

Header mới dùng **dấu phẩy** ngăn cách các directive; origin dạng URL được **đặt trong dấu ngoặc kép** trong allowlist. Không thể đổi tên header mà giữ nguyên đoạn `geolocation 'self'` của cú pháp cũ.

Một số tên directive và mức độ hỗ trợ khác nhau giữa các trình duyệt hoặc phiên bản. Đừng coi một ví dụ header là danh sách đầy đủ các API có thể khóa; hãy xác nhận directive cụ thể trên tập trình duyệt được hỗ trợ.

### 3.2. Header không tự cấp quyền cho JavaScript

Permissions Policy chỉ đặt một **giới hạn trên** cho tính năng có thể được dùng. Ví dụ, `geolocation=(self)` không thay thế hộp thoại xin quyền vị trí và không vượt qua các yêu cầu về HTTPS/secure context.

Với iframe khác origin, phải xét đồng thời:

- Header `Permissions-Policy` của tài liệu cha: origin của iframe phải nằm trong phạm vi có thể cấp quyền.
- Thuộc tính `allow` của chính phần tử `<iframe>`: phải cấp quyền tương ứng cho iframe.
- Header của tài liệu bên trong iframe, quyền của người dùng và các điều kiện của API liên quan.

Ví dụ một trang chủ động cho phép iframe bản đồ dùng geolocation:

```http
Permissions-Policy: geolocation=(self "https://maps.example"), camera=(), microphone=()
```

```html
<iframe
  src="https://maps.example/widget"
  title="Bản đồ điểm giao hàng"
  allow="geolocation https://maps.example">
</iframe>
```

Ví dụ sử dụng domain giả định; ứng dụng thật phải thay bằng origin của nhà cung cấp đã kiểm chứng. Không cho phép iframe vượt quá header của trang cha. **Đáng chú ý:** cú pháp `allow` trên phần tử HTML vẫn theo kiểu cũ, khác cú pháp `Permissions-Policy` trong HTTP header.

### 3.3. Trình duyệt bỏ qua header cũ có nguy hiểm gì?

Ứng dụng có thể phát `Feature-Policy: camera 'none'` và nhìn thấy header trong DevTools, nhưng tính năng lại không bị chặn như kỳ vọng ở trình duyệt mục tiêu. Ngược lại, một ứng dụng nhúng iframe có thể hỏng nếu chuyển sang `Permissions-Policy: geolocation=()` khiến mọi phần tử con đều bị chặn.

Do đó, nâng cấp phải xác nhận **hai loại kết quả**: giá trị response header đúng và thử nghiệm hành vi API trên trình duyệt thực.

## 4. Cấu hình Spring Security cho Servlet và Reactive

### 4.1. Biết mặc định nào đã có sẵn

Trong cấu hình header mặc định, Spring Security cung cấp các header như:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Frame-Options: DENY
X-XSS-Protection: 0
```

Dòng HSTS chỉ được thêm trên response HTTPS. Đây là **ví dụ của tập mặc định theo tài liệu Spring Security**; cần kiểm tra response thực tế vì proxy, nhiều filter chain hoặc cấu hình tùy chỉnh có thể thay đổi kết quả.

Spring Security **không tự chọn** `Permissions-Policy` hay CSP cho ứng dụng: chúng phụ thuộc vào nhu cầu camera, vị trí, iframe, nguồn script và tài nguyên. Giữ các mặc định an toàn; chỉ bổ sung hoặc thay đổi những directive phù hợp, tránh vô hiệu hóa toàn bộ security headers để sửa một xung đột.

### 4.2. Servlet: `HttpSecurity`

Đoạn Java sau minh họa phần cấu hình header nằm trong `SecurityFilterChain` hiện có (ví dụ dùng API kiểu lambda ở các phiên bản Spring Security hiện đại):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BrowserPolicyServletConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        // Giữ cấu hình xác thực, phân quyền, CSRF, session của ứng dụng.
        http.headers(headers -> headers
            .permissionsPolicy(permissions -> permissions
                .policy("geolocation=(self), camera=(), microphone=()")
            )
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'"
                )
            )
        );

        return http.build();
    }
}
```

Chính sách minh họa cấm nhúng trang trong iframe và chỉ cho phép script từ chính origin. Trước khi dùng trong hệ thống có CDN, widget thanh toán hoặc inline scripts, cần xây dựng CSP từ tài nguyên thực tế, có thể chạy ở chế độ `Content-Security-Policy-Report-Only` trước khi thực thi. Khi đã có cấu hình `SecurityFilterChain`, hãy tích hợp phần `headers(...)` vào bean đang tồn tại, không tạo thêm một filter chain chồng chéo ngoài ý muốn.

### 4.3. Reactive/WebFlux: `ServerHttpSecurity`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class BrowserPolicyWebFluxConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        // Giữ cấu hình xác thực, phân quyền, CSRF của ứng dụng WebFlux.
        http.headers(headers -> headers
            .permissionsPolicy(permissions -> permissions
                .policy("geolocation=(self), camera=(), microphone=()")
            )
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'"
                )
            )
        );

        return http.build();
    }
}
```

Servlet dùng `SecurityFilterChain/HttpSecurity`, còn WebFlux dùng `SecurityWebFilterChain/ServerHttpSecurity`. Cú pháp cấu hình header gần giống nhau nhưng không tráo lẫn các kiểu, filter hoặc công cụ kiểm thử của hai stack. API `permissionsPolicy(...).policy(...)` được mô tả trong tài liệu Spring Security của cả hai stack.

**Chú ý về reverse proxy:** Nếu nginx, API gateway hoặc CDN cũng ghi `Permissions-Policy`/CSP, cần kiểm kê các response ở ranh giới public. Header trùng hoặc bị ghi đè có thể tạo chính sách khác dự kiến, dù cấu hình trong ứng dụng hoàn toàn đúng.

## 5. Các chính sách liên quan cần rà soát khi nâng cấp

Không nên gom mọi HTTP security header vào một cơ chế “bảo vệ trình duyệt” chung:

| Chính sách | Bảo vệ chính | Lưu ý nâng cấp |
|---|---|---|
| `Strict-Transport-Security` (HSTS) | Giảm nguy cơ bị kéo về HTTP sau khi đã biết host HTTPS. | Header chỉ có ý nghĩa trên HTTPS đáng tin cậy; chú ý subdomain và preload. |
| `Content-Security-Policy` (CSP) | Hạn chế nguồn script, tài nguyên, đối tượng, hành vi nhúng. | Nên thử `Report-Only`, sau đó nâng mức thực thi; CSP không thay thế encode/escape và xử lý XSS tại ứng dụng. |
| CSP `frame-ancestors` | Giới hạn origin được nhúng trang. | Có thể đi kèm `X-Frame-Options` cho trình duyệt cũ; chính sách phải nhất quán. `frame-ancestors` không được hỗ trợ qua `<meta http-equiv>`. |
| `Referrer-Policy` | Hạn chế thông tin URL được gửi trong Referer. | Ví dụ `strict-origin-when-cross-origin`; chọn mức phù hợp luồng SSO/analytics, không phụ thuộc ngầm vào mặc định mỗi trình duyệt. |
| `X-Content-Type-Options: nosniff` | Giảm nguy cơ trình duyệt tự đoán MIME type của một số tài nguyên. | Đặt Content-Type đúng khi phục vụ JS/CSS/file; nếu sai có thể làm tài nguyên bị chặn. |
| `Cross-Origin-Opener-Policy` (COOP) | Cô lập quan hệ cửa sổ/nhóm duyệt giữa các origin. | Kiểm tra popup SSO, OAuth, thanh toán, chức năng cần `window.opener`. |
| `Cross-Origin-Embedder-Policy` (COEP) và `Cross-Origin-Resource-Policy` (CORP) | Điều khiển việc nhúng/tải tài nguyên cross-origin trong các tình huống cần cô lập. | Có thể làm hỏng ảnh, font, script bên thứ ba; kết hợp với CORS và thử nghiệm trên tài nguyên thực tế. |

### Những nhầm lẫn thường gặp

- **“Bật Permissions-Policy là hết cần CORS.”** Sai: CORS điều khiển quyền đọc response cross-origin của JavaScript; Permissions Policy giới hạn sử dụng các browser feature. Đây là hai quyết định độc lập.
- **“CSP `frame-ancestors 'none'` tương đương `camera=()`.”** Sai: một chính sách liên quan đến nhúng trang; chính sách kia liên quan đến khả năng dùng camera.
- **“HSTS thay được HPKP.”** Sai: HSTS bảo đảm đường truyền HTTPS theo cơ chế trình duyệt; HPKP từng ràng buộc khóa công khai được chấp nhận.
- **“Cứ thêm lại `X-XSS-Protection: 1; mode=block` để tăng bảo mật.”** Không nên: bộ lọc XSS cũ có vấn đề tương thích và đôi khi gây lỗ hổng. Spring Security gửi `0` theo mặc định; CSP và xử lý dữ liệu đầu ra là hướng chủ đạo.
- **“Server đã gửi header thì coi như được bảo vệ.”** Sai: cần xác nhận trình duyệt hỗ trợ directive, không có chính sách mâu thuẫn và hành vi thật sự bị giới hạn.

## 6. Quy trình di chuyển một ứng dụng thực tế

Giả sử cổng quản trị đã sử dụng HPKP, `Feature-Policy`, widget bản đồ iframe và một số JavaScript từ CDN.

**Bước 1 — Kiểm kê response bên ngoài ứng dụng.** Kiểm tra các URL đại diện: trang HTML, đăng nhập, API, chuyển hướng, 403/500, tệp tĩnh và response từ proxy. Ghi nhận header hiện diện và tầng chịu trách nhiệm phát chúng. Có thể dùng:

```bash
curl -sSI https://app.example.test/
curl -sSI https://app.example.test/login
```

`-I` gửi yêu cầu HEAD: nếu endpoint có hành vi khác GET, hãy dùng GET với `-D -` để kiểm tra header. Đường dẫn `example.test` chỉ là ví dụ; dùng URL staging thật khi kiểm tra.

**Bước 2 — Phân loại và thay đổi chính sách.** Bỏ cấu hình phát HPKP/Expect-CT lỗi thời ở mọi tầng liên quan; di chuyển cú pháp `Feature-Policy` sang `Permissions-Policy`. Chỉ cho phép geolocation với origin được phê duyệt; chỉ bật camera/microphone tại nơi thực sự cần. Không vô tình làm mất các mặc định như HSTS và `nosniff`.

**Bước 3 — Xác minh tác động nghiệp vụ.** Widget bản đồ cần `allow` của iframe phù hợp. Trang login và luồng OAuth có thể bị COOP hoặc `frame-ancestors` ảnh hưởng; hệ thống cần bên thứ ba nhúng trang sẽ không phù hợp với `frame-ancestors 'none'`. Điều chỉnh chính sách theo luồng thực tế.

**Bước 4 — Quan sát trước khi chặn mạnh.** Với CSP mới, cân nhắc `Report-Only` và phân loại vi phạm từ các trang quan trọng trước khi bật enforcement. Không có nguyên tắc “bật report-only là an toàn” chung cho tất cả header: `Permissions-Policy` cần được đánh giá qua kịch bản trình duyệt và kết quả API.

**Bước 5 — Triển khai từng nhóm và đo lỗi.** Theo dõi lỗi console (permissions policy violation, CSP violation), tỉ lệ lỗi frontend, chức năng iframe/camera/vị trí và thay đổi tại CDN/proxy. Có phương án hoàn tác nếu policy cắt đứt tính năng thiết yếu.

### Bộ kiểm tra tối thiểu

| Kịch bản | Kiểm chứng cần đạt |
|---|---|
| Trang HTTPS bình thường | Có `Permissions-Policy` đúng cú pháp; HSTS, `nosniff` và header mặc định mong đợi được giữ. |
| Request HTTP ban đầu | Được điều hướng về HTTPS theo kiến trúc triển khai; không kỳ vọng trình duyệt ghi nhận HSTS từ response HTTP. |
| Camera bị chặn | JavaScript của trang không truy cập được camera vì policy; kiểm tra trên trình duyệt hỗ trợ directive. |
| Vị trí same-origin | Vẫn hoạt động khi người dùng đồng ý và API đủ điều kiện; không nhầm lỗi từ chối quyền với lỗi policy. |
| Bản đồ cross-origin trong iframe | Đúng origin ở header cha và trong `allow`; hành vi geolocation được kiểm thử trực tiếp. |
| Trang cố nhúng không được phép | `frame-ancestors`/`X-Frame-Options` chặn đúng bên nhúng. |
| Trang dùng CDN, popup SSO, OAuth | Script, ảnh, popup và đăng nhập vẫn chạy với CSP/COOP đã chọn. |
| Firefox và Chromium mục tiêu | Không trông chờ HPKP; test giá trị header lẫn hành vi thay vì chỉ xác nhận response. |

Một ví dụ kiểm thử response header trong Servlet dùng Spring Security Test/MockMvc:

```java
mvc.perform(get("/"))
    .andExpect(header().string(
        "Permissions-Policy",
        "geolocation=(self), camera=(), microphone=()"
    ));
```

Với WebFlux có thể dùng `WebTestClient` để kiểm tra header tương đương. Các kiểm thử HTTP này **chỉ xác nhận máy chủ phát header**, vì MockMvc/WebTestClient không thực thi API trình duyệt; cần bổ sung kiểm thử browser khi quyền camera, geolocation hoặc iframe ảnh hưởng nghiệp vụ.

## 7. Chẩn đoán nhanh khi chính sách gây lỗi

| Hiện tượng | Nguyên nhân cần điều tra | Cách xác minh |
|---|---|---|
| `Feature-Policy` còn trong response nhưng Chrome/Firefox không thực thi như dự kiến | Cú pháp cũ/khác mức hỗ trợ. | Xem `Permissions-Policy` trong Network, tra compatibility của directive và thử hành vi API. |
| Geolocation ở iframe không chạy | Header cha không cho origin của iframe, thiếu `allow` hoặc người dùng từ chối quyền. | Kiểm tra đồng thời header cha, `allow`, console và prompt/permission của browser. |
| Trình duyệt báo vi phạm `script-src` sau nâng cấp | CSP quá chặt đối với inline script, nonce, CDN. | Kiểm tra nguồn script thực tế, ghi nhận `Report-Only` và dùng nonce/hash khi phù hợp. |
| Trang không thể được nhúng | `frame-ancestors 'none'` hoặc `X-Frame-Options: DENY`. | Kiểm tra yêu cầu nhúng hợp lệ và thống nhất hai chính sách. |
| Tìm thấy nhiều `Permissions-Policy` khác nhau | Ứng dụng và proxy/CDN cùng thêm header. | So response ở app nội bộ với response public; thống nhất điểm tạo và quy tắc ghép header. |
| Scanner cảnh báo thiếu HPKP/Expect-CT | Bộ quy tắc kiểm tra lỗi thời. | Đối chiếu trạng thái hỗ trợ trình duyệt và tài liệu Spring Security; ghi nhận lý do bỏ cơ chế cũ. |

## 8. Bài tập áp dụng

Một ứng dụng Spring MVC cũ trả về:

```http
Public-Key-Pins: pin-sha256="(giá-trị-cũ)"; max-age=5184000
Feature-Policy: geolocation 'self'; camera 'none'
X-XSS-Protection: 1; mode=block
```

Yêu cầu mới: bản đồ nhúng từ `https://maps.example` được phép sử dụng vị trí sau khi người dùng chấp thuận; camera phải bị chặn; hệ thống phục vụ HTTPS.

**Hướng xử lý có căn cứ:**

1. Bỏ cơ chế xuất `Public-Key-Pins`, rà soát nơi phát header ở gateway/CDN; củng cố quy trình TLS, HSTS và giám sát CT.
2. Thay header cũ bằng `Permissions-Policy: geolocation=(self "https://maps.example"), camera=()`.
3. Thêm `allow="geolocation https://maps.example"` vào iframe bản đồ và thử trên browser thực; header không miễn yêu cầu xin quyền vị trí.
4. Kiểm tra mặc định `X-XSS-Protection: 0` của Spring Security và triển khai CSP thích hợp. Không giữ cấu hình bộ lọc XSS cũ theo thói quen.
5. Test response public ở cả luồng thành công/lỗi và test chức năng iframe sau khi deploy lên staging.

**Câu hỏi tự kiểm tra:** Nếu iframe có `allow="geolocation"` nhưng trang cha trả `Permissions-Policy: geolocation=()`, iframe có được phép dùng geolocation không? **Không.** `allow` của iframe không thể mở lại một tính năng đã bị header cha chặn.

## 9. Checklist trước khi kết thúc nâng cấp

- [ ] Không còn phát HPKP hoặc Expect-CT chỉ để thỏa bộ kiểm tra cấu hình cũ.
- [ ] Đã chuyển các `Feature-Policy` cần thiết sang cú pháp `Permissions-Policy` hợp lệ.
- [ ] Đã xác nhận tính năng cần trong iframe được cho phép ở cả header và `allow`.
- [ ] Đã giữ hoặc điều chỉnh có chủ đích các mặc định của Spring Security.
- [ ] Đã xác minh CSP, HSTS, frame policy và chính sách cô lập không chặn nghiệp vụ quan trọng.
- [ ] Đã so sánh response nội bộ với response public qua proxy/CDN.
- [ ] Đã kiểm tra hành vi thực trên trình duyệt hỗ trợ, không chỉ kiểm tra sự hiện diện của header.
- [ ] Đã lập kế hoạch theo dõi và phương án quay lại cấu hình an toàn trước đó.

## Tài liệu tham khảo

- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): tập header mặc định, đánh giá HPKP.
- [Spring Security — Servlet security headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): DSL cấu hình cho `HttpSecurity`.
- [Spring Security — Reactive security headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): DSL cấu hình cho `ServerHttpSecurity`.
- [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy): cú pháp header, iframe, kế thừa chính sách.
- [MDN — HPKP](https://developer.mozilla.org/en-US/docs/Glossary/HPKP) và [Firefox 72 release notes](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/72): cơ chế cũ và việc loại bỏ.
- [MDN — Expect-CT](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Expect-CT) và [X-XSS-Protection](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-XSS-Protection): tình trạng deprecated và rủi ro.
- [MDN — Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): `frame-ancestors`, chính sách tải tài nguyên và kiểm thử report-only.
