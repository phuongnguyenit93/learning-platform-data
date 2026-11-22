# REST API hoặc cấu hình stateless không tự loại bỏ mọi nguy cơ CSRF

Một suy luận khá phổ biến khi bảo vệ API là: “Đây là REST API, không dùng server-side session, đặt `SessionCreationPolicy.STATELESS` rồi, nên chắc chắn không có CSRF.” **Kết luận đó không đúng nếu trình duyệt vẫn tự động gửi credential xác thực trong những request mà trang web bên ngoài có thể kích hoạt.** Chuyển từ session ID sang JWT lưu trong cookie không thay đổi bản chất này: browser vẫn có thể tự gắn cookie.

Để đánh giá nguy cơ Cross-Site Request Forgery (CSRF), câu hỏi trọng tâm là **“Trong một request bị trang khác kích hoạt, trình duyệt có thể tự đính kèm credential đủ để server chấp nhận hành động hay không?”** chứ không phải API có tên `/api`, trả JSON hay không lưu trạng thái ở server.

Bài này thuộc nhóm **CSRF** của Spring Security fundamentals, tập trung vào cách đánh giá rủi ro trong REST API, ứng dụng stateless và cấu hình Spring Security Servlet. Sau khi học, bạn cần giải thích được vì sao cookie JWT và HTTP Basic vẫn có thể gặp CSRF, khi nào một API Bearer-only ít có nguy cơ CSRF cổ điển, vai trò của SameSite/CORS/CSRF token, và cách chọn `SecurityFilterChain` hợp lý.

## 1. Cơ chế CSRF không phụ thuộc server có session hay không

**CSRF (Cross-Site Request Forgery)** là tình huống kẻ tấn công khiến trình duyệt của người dùng đã có trạng thái xác thực **gửi một request thực hiện hành động ngoài ý muốn** tới website/API đích. Kẻ tấn công thường không cần biết mật khẩu hoặc đọc được credential; họ lợi dụng việc browser tự gắn thông tin xác thực vào request hợp lệ theo quy tắc của trình duyệt.

Ví dụ giả định:

1. Người dùng đã đăng nhập `https://bank.example.test`, có cookie xác thực phù hợp với trang này.
2. Người dùng mở `https://attacker.example.org`, nơi chứa biểu mẫu gửi dữ liệu sang `https://bank.example.test/account/change-email`.
3. Browser có thể gửi request do trang lạ kích hoạt. **Cookie có được đính kèm hay không phụ thuộc `SameSite`, domain, path, scheme và những chính sách browser khác**.
4. Nếu cookie hợp lệ được gửi và server chỉ kiểm tra xác thực mà **không kiểm tra bằng chứng chống CSRF**, request thay đổi email có thể được chấp nhận như thể người dùng chủ động thực hiện.
5. Kẻ tấn công có thể không đọc được response do Same-Origin Policy (SOP), nhưng việc đổi trạng thái đã xảy ra.

Đây là sơ đồ mô tả điều kiện rủi ro:

```text
Người dùng đã đăng nhập ở bank.example.test
     |
     | browser có cookie xác thực thuộc bank.example.test
     v
Mở trang attacker.example.org
     |
     | trang này kích hoạt POST đến bank.example.test
     v
Browser kiểm tra chính sách cookie (SameSite/Domain/Path/Secure)
     |
     | nếu cookie được gửi tự động
     v
API đích nhận request + cookie xác thực
     |
     | API chỉ kiểm tra credential, không kiểm bằng chứng CSRF
     v
Hành động đổi trạng thái có thể được thực hiện
```

**Điểm gốc:** CSRF lợi dụng **quyền mà browser tự mang sang request**. Server có lưu `HttpSession` hay không chỉ là một chi tiết của phương thức xác thực, không phải điều kiện quyết định duy nhất.

### Mẫu HTML minh họa request bị lợi dụng

Ví dụ sau dành để hiểu mối đe dọa trên một website thử nghiệm được phép kiểm tra; `example.test` không phải website thật:

```html
<form method="post"
      action="https://bank.example.test/account/change-email">
  <input type="hidden" name="email" value="unwanted@example.test">
  <button type="submit">Submit</button>
</form>
```

Nếu browser cho phép gửi cookie xác thực và endpoint chấp nhận `application/x-www-form-urlencoded` **mà không có CSRF protection**, thao tác có thể thành công khi người dùng nhấn nút. Một trang lạ cũng có thể tự submit form bằng JavaScript tùy hạn chế browser; việc server chỉ dùng `POST` không tự ngăn tình huống này.

Mẫu này **không bảo đảm khai thác được mọi endpoint**: `SameSite` có thể chặn cookie, endpoint có thể chỉ chấp nhận media type khác, và CSRF filter có thể từ chối request. Nó minh họa **điều kiện cần đánh giá** thay vì kết luận mọi form cross-site đều thành công.

## 2. “Stateless” chính xác có nghĩa là gì?

Trong Spring Security Servlet, cấu hình phổ biến cho một API stateless là:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
```

Ý nghĩa: **Spring Security không tạo hoặc sử dụng `HttpSession` để lấy `SecurityContext`** cho những request áp dụng chain đó. Nó hướng API đến kiểu xác thực từng request, chẳng hạn JWT Bearer token. Nó **không** quy định cách browser lưu credential, không vô hiệu hóa cookie do ứng dụng tự phát hành, cũng không ngăn mọi thành phần khác gọi Servlet API tạo session.

Ví dụ một dịch vụ xác thực JWT tự chứa trong cookie:

```http
Set-Cookie: AUTH=eyJ...; Secure; HttpOnly; SameSite=None; Path=/
```

Ở request tiếp theo, browser có thể tự gửi:

```http
POST /api/orders/confirm HTTP/1.1
Host: shop.example.test
Cookie: AUTH=eyJ...
Content-Type: application/x-www-form-urlencoded

orderId=42
```

Dù API giải mã JWT mà **không truy vấn session trong RAM/Redis**, cookie vẫn là **ambient credential**: browser tự đính kèm theo chính sách cookie. Nếu một trang khác kích hoạt request và cookie được gửi, nguy cơ CSRF vẫn có thể xảy ra.

Không được đánh đồng ba khẳng định:

- `STATELESS` → không dùng HTTP session để khôi phục Spring Security context trong chain đó.
- JWT → định dạng token có thể được kiểm tra theo chữ ký/claim; **JWT không tự gỡ CSRF**.
- `Authorization: Bearer` chỉ do JavaScript chính chủ chủ động gắn vào request → mô hình truyền credential có thể giảm điều kiện cho CSRF cổ điển, **nếu không tồn tại đường xác thực tự động khác**.

**Ngay cả khi JWT có chữ ký hợp lệ, server vẫn phải xác minh token theo issuer, audience, expiry và quyền.** Tuy nhiên, chữ ký hợp lệ chỉ chứng minh token đáng tin theo quy tắc đó; nó không chứng minh **người dùng đã chủ động khởi tạo request hiện tại**.

## 3. REST API và JSON cũng không tự chặn CSRF

**REST** là một phong cách kiến trúc cho giao tiếp tài nguyên; nó không định nghĩa “trình duyệt không có cookie”, “tất cả client chỉ gửi Bearer header”, hoặc “mọi thao tác từ browser đã được xác nhận”.

Những tên gọi sau **không phải biện pháp chống CSRF độc lập**:

- URL bắt đầu bằng `/api/`.
- HTTP body định dạng JSON.
- Tách frontend và backend thành hai hostname.
- Chỉ hỗ trợ `POST`/`PUT`/`PATCH`/`DELETE` thay vì GET để đổi dữ liệu.
- Không dùng `JSESSIONID`, nhưng dùng JWT trong cookie.
- Không tạo session trên server và đặt `SessionCreationPolicy.STATELESS`.
- Bật CORS với một danh sách origin nào đó.

**Thiết kế đúng phương thức HTTP vẫn rất quan trọng:** `GET`, `HEAD`, `OPTIONS` phải được thiết kế là các phương thức “safe” theo ngữ nghĩa, không gây thay đổi trạng thái có ý nghĩa nghiệp vụ. Nếu `GET /delete?id=42` lại xóa dữ liệu, một điều hướng hoặc tải tài nguyên có thể kích hoạt tác hại mà không cần form `POST`. `POST` không được coi là “an toàn vì là POST”; nó cần cơ chế xác thực, phân quyền và chống CSRF thích hợp.

### “API chỉ nhận application/json thì sao?”

Một form HTML cross-site thông thường gửi những content type đơn giản như `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`. Nó không thể tự cấu tạo một request tùy ý với `Content-Type: application/json` và header custom mà bỏ qua các ràng buộc của browser.

Nếu server **kiểm tra nghiêm ngặt content type, không diễn giải `text/plain` như JSON, không có endpoint thay thế nhận form và không mở CORS thiếu an toàn**, một số đường khai thác CSRF cổ điển sẽ khó hoặc bị chặn. Nhưng đây chỉ là **một lớp kiểm soát**. Có các thiết kế và triển khai parse body không chặt, endpoint chấp nhận nhiều định dạng, CORS sai, đổi trạng thái qua GET và mô hình client-side CSRF khiến kết luận “JSON = không CSRF” không đáng tin cậy.

Spring Security cũng nhắc riêng rằng các request JSON **có thể gặp CSRF** trong những cấu hình cụ thể. Chỉ dựa vào đuôi `.json` hoặc nhãn REST mà tắt CSRF là bỏ qua cơ chế thực tế của browser và server.

## 4. So sánh cách gửi credential: nơi CSRF xuất hiện

| Phương thức xác thực | Browser tự gửi credential không? | Điều cần lưu ý về CSRF |
|---|---|---|
| **Session cookie (`JSESSIONID`)** | Có, khi cookie đúng phạm vi/chính sách | Có nguy cơ nếu request đổi trạng thái không có chống CSRF |
| **JWT access token trong cookie `AUTH`** | Có, nếu cookie được phép gửi | **Vẫn có nguy cơ** dù backend không có HTTP session |
| **HTTP Basic được browser cache** | Browser có thể tự gửi lại credentials trong phạm vi xác thực theo hành vi client | Có thể có nguy cơ CSRF; không coi Basic là miễn nhiễm |
| **Client certificate / credential tự động của browser** | Có thể được browser dùng tự động tùy kết nối/chính sách | Phải đánh giá CSRF theo đường browser và identity thực tế |
| **Bearer token chỉ trong Authorization header do app JS chủ động thêm** | Trang lạ không tự có giá trị Bearer; cross-origin JS bị ràng buộc SOP/CORS | Ít nguy cơ CSRF cổ điển **nếu API tuyệt đối chỉ chấp nhận cơ chế này** |
| **API key trong header riêng do app chính chủ đặt** | Browser không tự sinh key cho trang lạ | Cần kiểm soát lộ key/XSS/CORS; nguy cơ CSRF tùy đường xác thực khác |
| **Cookie auth + header CSRF token** | Cookie auth tự gửi; CSRF header không được browser tự gắn | Có cơ chế chống CSRF khi server xác minh token/header đúng |

Dòng cuối cần phân biệt: browser có thể tự gửi **cookie chứa CSRF token**, vì vậy **chỉ yêu cầu cookie CSRF có mặt là chưa đủ**. Phải lấy token ra khỏi kênh tự động và gửi nó bằng một header hoặc form parameter do ứng dụng hợp lệ kiểm soát; server xác minh token theo cơ chế thích hợp.

### JWT trong Cookie và JWT trong Header khác nhau ra sao?

Cùng một giá trị JWT có thể được gửi bằng hai đường:

```http
Cookie: AUTH=EXAMPLE_JWT
```

hoặc:

```http
Authorization: Bearer EXAMPLE_JWT
```

**JWT giống nhau không làm rủi ro giống nhau.** Khác biệt đáng kể là ai gắn credential vào request.

- Cookie do browser quản lý được gửi tự động khi đáp ứng quy tắc cookie.
- Bearer header thường do code JavaScript trong ứng dụng hoặc HTTP client khác quyết định đặt. Trang tấn công từ origin khác không biết giá trị token để tự đặt header đúng.
- Nếu token Bearer lại được framework tự lấy từ cookie và gắn vào header cho mọi request có thể bị ép kích hoạt, hoặc API có cơ chế cookie fallback, phải đánh giá lại luồng thực tế.
- Khi token đặt trong `localStorage` hoặc biến JavaScript, CSRF cổ điển có thể ít phù hợp hơn, nhưng nguy cơ **XSS đánh cắp token** hoặc ép code cùng origin gửi request vẫn tồn tại. Không kết luận localStorage mặc nhiên “an toàn hơn”.

Cần xét thêm mô hình Backend-for-Frontend (BFF): backend giữ access/refresh token ở server, browser chỉ dùng cookie phiên để gọi BFF. Với BFF, request browser → BFF có thể cần CSRF protection, dù request BFF → downstream API dùng Bearer token trong header.

## 5. Ví dụ thực tế: một API stateless vẫn có CSRF

Giả sử `orders.example.test` sử dụng:

- Spring MVC `@RestController`, body JSON.
- JWT tự chứa trong cookie `AUTH`, backend xác minh chữ ký token.
- `SessionCreationPolicy.STATELESS` trong Spring Security.
- Endpoint `POST /api/orders/42/approve` thay đổi trạng thái đơn hàng.
- Cookie được phép gửi trong ngữ cảnh mà request bên ngoài có thể kích hoạt.
- Không có CSRF token, xác minh Origin/Fetch Metadata hoặc biện pháp chống request giả mạo tương đương.

Khi người dùng đã đăng nhập, request cross-site hoặc cross-origin thích hợp có thể khiến browser gửi `AUTH`; nếu endpoint chấp nhận kiểu request đó, server có đủ thông tin xác thực để thực hiện lệnh. **Không có bước nào của cuộc tấn công cần đọc server session.**

Rủi ro có thể giảm hoặc đường này bị chặn khi cookie `SameSite` phù hợp, API chỉ chấp nhận media type/header mà trang ngoài không thể tạo hợp lệ, server xác minh Origin/CSRF token, hoặc không có credential tự gửi. Nhưng **việc “stateless” không phải chính biện pháp ngăn chặn**.

### Trường hợp gần như ngược lại: Bearer-only API

Một API nhận từ mobile app hoặc backend:

```http
POST /api/orders/42/approve HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Content-Type: application/json

{"approved":true}
```

Nếu API **chỉ chấp nhận token trong header `Authorization`**, không xử lý session/cookie/Basic/integrated auth làm đường xác thực thay thế, không cho phép các credential tự gửi khác, và trang lạ không biết token, thì việc trang lạ tạo form hoặc navigation sẽ **không có Bearer token hợp lệ**. Trong mô hình đó, CSRF cổ điển ít có khả năng thành công, nên có thể cân nhắc tắt Spring Security CSRF cho phạm vi Bearer-only sau khi xác minh giả định.

**Giới hạn:** Điều này không có nghĩa API đã an toàn trước XSS, mất token, CORS cấu hình nhầm, lỗ hổng phân quyền, request replay hoặc client-side CSRF. Nếu sau này thêm cookie auth “cho tiện” vào API, quyết định tắt CSRF phải được xét lại.

## 6. SameSite, HttpOnly và Secure giúp gì?

Cookie có nhiều thuộc tính bảo vệ khác nhau; mỗi thuộc tính xử lý một vấn đề:

| Thuộc tính | Ý nghĩa | Điều nó không bảo đảm |
|---|---|---|
| `HttpOnly` | Giảm việc JavaScript đọc cookie thông qua `document.cookie` | **Không ngăn browser tự gửi cookie**; không tự ngăn CSRF |
| `Secure` | Yêu cầu gửi cookie qua kết nối HTTPS theo chính sách browser | Không chống CSRF nếu cookie được gửi qua HTTPS trong request bị giả mạo |
| `SameSite=Strict` | Hạn chế gửi cookie trong các tình huống cross-site | Không tự giải quyết request **same-site nhưng cross-origin**, XSS hoặc client-side CSRF |
| `SameSite=Lax` | Hạn chế nhiều request cross-site unsafe, vẫn cho phép một số điều hướng top-level dạng safe | Không phải bằng chứng người dùng chủ động xác nhận mọi thao tác; không xử lý unsafe GET |
| `SameSite=None; Secure` | Cho phép cookie trong ngữ cảnh cross-site phù hợp, phụ thuộc chính sách browser | Có thể tạo điều kiện gửi cookie trên các request có khả năng CSRF |
| `Domain`, `Path` | Giới hạn phạm vi host/path được gửi cookie | Không phân biệt người dùng chủ động nhấn hay bị trang ngoài kích hoạt |

**Same-site khác same-origin.** Ví dụ `https://shop.example.test` và `https://promo.example.test` là **khác origin** vì host khác, nhưng thường cùng *site* theo quy tắc schemeful site/registrable domain. Một subdomain không đáng tin có thể kích hoạt request cùng-site, khi đó `SameSite=Strict` hoặc `Lax` không nhất thiết ngăn cookie. Cần cẩn trọng khi toàn bộ các subdomain có mức tin cậy khác nhau.

Một chi tiết thực tế: trình duyệt hiện đại áp các mặc định/ngoại lệ SameSite khác nhau theo hoàn cảnh, phiên bản và thời điểm tạo cookie. Vì vậy hãy **kiểm chứng behavior trên browser được hỗ trợ**, đừng coi cookie thiếu thuộc tính SameSite đương nhiên có một chính sách cố định giống nhau ở mọi client.

`HttpOnly` là lựa chọn phù hợp cho **cookie xác thực** khi có thể. Khi sử dụng mô hình **CSRF token cookie cho SPA**, đôi khi một cookie **khác** tên `XSRF-TOKEN` được phép đọc bằng JavaScript để gửi lại qua header. Đừng nhầm cookie CSRF được phép đọc với cookie đăng nhập phải giữ bí mật; hai cookie có vai trò khác nhau.

## 7. CORS và Same-Origin Policy không phải lá chắn CSRF tổng quát

**Same-Origin Policy (SOP)** chủ yếu hạn chế script của một origin đọc/truy cập dữ liệu của origin khác. **CORS** là cơ chế để server cho phép một số tương tác cross-origin dưới kiểm soát của browser. CSRF lại có thể dựa trên **việc gửi request và thực hiện side effect** mà không cần đọc response.

Một biểu mẫu HTML cross-site có thể được browser submit mà không cần API cho phép đọc response qua CORS. Nếu credential tự gửi và server thực thi, người dùng vẫn chịu tác động dù script ở site lạ không thấy JSON trả về.

**Preflight giúp giới hạn một số kiểu request**, ví dụ JavaScript muốn gửi `Authorization` hoặc custom header `X-CSRF-TOKEN` cross-origin thường phải qua preflight theo cơ chế CORS. Tuy nhiên:

- Form POST với content type đơn giản không cần preflight theo kiểu yêu cầu đó.
- API có thể cho phép credentialed CORS với origin quá rộng hoặc không đáng tin; việc phản chiếu `Origin` và trả `Access-Control-Allow-Credentials: true` bừa bãi là rủi ro.
- Việc không có header `Access-Control-Allow-Origin` ở response **không có nghĩa server đã từ chối thực thi request**.
- `Origin`/`Referer` và Fetch Metadata (`Sec-Fetch-Site`, `Sec-Fetch-Mode`...) có thể hỗ trợ chính sách chống giả mạo, nhưng phải kiểm tra nguồn và tình huống các header vắng mặt, proxy, client không phải browser.

**Kết luận kỹ thuật:** CORS là chính sách chia sẻ cross-origin; CSRF cần được đánh giá theo credential tự gửi, request có side effect và chứng cứ nguồn request. CORS cấu hình chặt là lớp hỗ trợ, không thay thế toàn bộ CSRF protection cho ứng dụng cookie-authenticated.

## 8. Spring Security Servlet: cấu hình CSRF mặc định

Spring Security Servlet **bật CSRF protection theo mặc định** cho các HTTP method không an toàn (thường là `POST`, `PUT`, `PATCH`, `DELETE`). Có thể thể hiện tường minh trong một `SecurityFilterChain`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BrowserSecurityConfig {

    @Bean
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Đây là ví dụ cấu hình **trong dự án Spring Boot 3 / Spring Security 6 có Spring MVC, dependency Security và các thành phần authentication cần thiết**; không phải class Java chạy riêng bằng `javac`. `csrf(Customizer.withDefaults())` làm rõ mặc định. Với `HttpSessionCsrfTokenRepository` mặc định, token kỳ vọng thường được quản lý trong `HttpSession`. HTML form cần gửi trường `_csrf` hoặc client JavaScript cần gửi token qua header thích hợp.

Một request POST chưa có CSRF token hợp lệ tới endpoint bị bảo vệ thường bị từ chối với **403 Forbidden** trước khi thực hiện logic nghiệp vụ. Tùy thứ tự filter và tình trạng xác thực, lỗi quan sát được có thể khác; không nên dùng duy nhất status 403 làm bằng chứng CSRF đang hoạt động đúng.

### CSRF token bảo vệ theo cơ chế nào?

**Synchronizer Token Pattern**:

1. Server cấp CSRF token khó đoán cho một ngữ cảnh xác thực/phiên phù hợp.
2. Ứng dụng tin cậy đặt token vào form hidden hoặc header riêng khi gửi request đổi trạng thái.
3. Browser có thể tự gửi cookie xác thực, nhưng trang tấn công không tự có **giá trị CSRF token hợp lệ trong vị trí server yêu cầu**.
4. Server so khớp giá trị gửi lên với token kỳ vọng; sai hoặc thiếu thì từ chối trước khi thực hiện hành động.

Ví dụ request hợp lệ **minh họa**:

```http
POST /account/change-email HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=EXAMPLE_SESSION
Content-Type: application/x-www-form-urlencoded

email=new%40example.test&_csrf=EXAMPLE_CSRF_TOKEN
```

Đây là giá trị giả; server phải thật sự phát token và xác minh, không sử dụng chuỗi hằng `EXAMPLE_CSRF_TOKEN`. Nếu dùng HTML template như Thymeleaf với tích hợp Spring Security phù hợp, CSRF token có thể được chèn vào form tự động. Nếu dùng SPA, phải thiết kế cách nhận token và gửi token qua `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` theo cấu hình.

Một cookie CSRF **được gửi tự động** không đủ làm “proof” nếu server chỉ kiểm cookie đó. Mô hình **double-submit cookie** cần lấy token ra và gửi ở một kênh không tự động (ví dụ custom header) để so sánh; cách triển khai nên ràng buộc token có chữ ký với phiên/identity theo kiến trúc để tránh cookie injection/fixation. Đừng tự viết hệ thống token khó đoán hoặc ký token theo ví dụ sơ sài nếu framework đã hỗ trợ cách đáng tin cậy.

## 9. Khi nào có thể tắt CSRF cho API Bearer-only?

Một ứng dụng REST API dùng OAuth2 Resource Server và chỉ nhận `Authorization: Bearer` từ client có thể áp dụng chain riêng. Ví dụ Spring Security Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BearerOnlyApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

**Giải thích chính xác điều kiện an toàn của ví dụ:** Ở `/api/**`, API **chỉ tin Bearer token trong header do client chủ động gửi**, không nhận cookie làm credential, không có HTTP Basic/browser-managed authentication, không dùng session làm authentication fallback và không có endpoint đổi trạng thái chấp nhận request ẩn danh ngoài ý muốn. JWT được xác minh đúng issuer, audience, thời hạn, signature và scope/quyền. Khi đó không có loại credential mà browser bên thứ ba có thể tự gắn vào một form request để vượt qua yêu cầu xác thực Bearer.

`csrf(AbstractHttpConfigurer::disable)` tắt `CsrfFilter` **cho filter chain này**, không chứng minh vô điều kiện “stateless thì không cần CSRF”. Nếu sau này mở tính năng browser cookie login trên `/api/**`, chấp nhận `AUTH` cookie chứa JWT hoặc bật HTTP Basic cho browser, phải **đánh giá lại và bổ sung biện pháp chống CSRF** trước khi triển khai.

Việc cấu hình `@Order(1)` và `securityMatcher("/api/**")` chỉ minh họa phạm vi. Một ứng dụng thật cần **các chain còn lại** hoặc chính sách fallback tương ứng để mọi request đều có bảo vệ. Bài này không giả định có một browser chain đang tồn tại khi chỉ hiển thị đoạn API.

### Cùng API nhưng JWT lấy từ cookie: tắt CSRF như trên có phù hợp không?

**Không, nếu cookie đó là credential tự động mà browser dùng để xác thực và có request đổi trạng thái có thể bị kích hoạt ngoài ý muốn.** Mặc dù API có thể tạo authentication từ JWT và không dùng session, browser vẫn tự gửi cookie. Giải pháp cần lựa chọn dựa trên threat model, ví dụ:

- Giữ bảo vệ CSRF cho request dùng cookie auth.
- Dùng synchronizer CSRF token nếu có trạng thái phiên phù hợp, hoặc **signed double-submit token**/cơ chế token không dùng session khi thực sự stateless.
- Gửi CSRF token qua header riêng không tự được browser thêm, kiểm tra token phía server.
- Cấu hình SameSite/Secure/HttpOnly, xác minh Origin hoặc Fetch Metadata thích hợp và giữ CORS chặt.
- Giới hạn các request có thể thay đổi trạng thái; tuyệt đối không dùng GET để thực hiện hành động nguy hiểm.

Nếu dùng `CookieCsrfTokenRepository` cho SPA Spring Security, cần hiểu **Spring Security 6 dùng token deferred loading và bảo vệ BREACH mặc định**. JavaScript thường đọc raw token từ cookie, trong khi handler mặc định mong đợi cách biểu diễn có xử lý XOR cho một số đường dẫn; tài liệu chính thức cung cấp cấu hình SPA với `CsrfTokenRequestHandler` phù hợp và cách cấp lại cookie token sau login/logout. Đừng chỉ gọi `CookieCsrfTokenRepository.withHttpOnlyFalse()` rồi cho rằng đã tích hợp SPA hoàn chỉnh trong mọi phiên bản/framework. Cookie xác thực vẫn nên có `HttpOnly` khi phù hợp, còn cookie token CSRF phục vụ đọc bằng JavaScript có thiết kế và mục đích riêng.

## 10. Ứng dụng vừa có browser session vừa có REST API

Giả sử cùng một ứng dụng cung cấp `/profile` cho browser và `/api/**` cho mobile/backend, hai luồng auth độc lập:

- `/profile`: form login, browser dùng session cookie; cần CSRF protection.
- `/api/**`: **chỉ** Bearer header, không tin cookie/session; có thể tắt CSRF riêng sau khi xác minh giả định.

Một cách cấu hình nhiều chain (mã thuộc Spring Boot, không chạy độc lập):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedCsrfSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Mẫu yêu cầu starter Spring Security, OAuth2 Resource Server và issuer/JWT decoder hợp lệ. Nó không tự cấu hình người dùng hoặc issuer; đó là việc của ứng dụng. Nếu đang dùng cấu hình `apiChain` ở phần 9, **chỉ lựa chọn một phương án phù hợp**, không khai báo cả hai bean `apiChain` chồng chéo.

Lưu ý:

1. Spring Security xét các `SecurityFilterChain` theo thứ tự và dùng chain đầu tiên khớp request.
2. Chain API phải thực sự chỉ nhận Bearer header. Nếu hệ thống có thêm cookie auth cho `/api/**`, phải đổi thiết kế.
3. Browser chain vẫn phải nhận đúng endpoint login/logout và những request cookie-authenticated; không tắt CSRF cho toàn ứng dụng vì chỉ một số API là stateless.
4. Với SPA cùng origin dùng cookie để gọi REST, API ấy **là browser cookie API**, không phải một API Bearer-only “miễn CSRF” theo mẫu này.
5. `SessionCreationPolicy.STATELESS` thuộc quản lý session của Spring Security cho chain, không mặc nhiên điều khiển các cookie tùy biến do ứng dụng gửi.

### Cách đọc hai request tương tự nhau

| Request | Cách xác thực | Điều kiện CSRF cần xét |
|---|---|---|
| `GET /api/orders`, Bearer header do mobile app đặt | Token do client quyết định | Thường không có hành động đổi trạng thái, vẫn cần xác thực/phân quyền |
| `POST /api/orders`, Bearer header từ backend service | Token do backend gắn | Có thể không cần CSRF cổ điển nếu không có credential tự gửi |
| `POST /api/orders`, `AUTH` cookie do browser gửi | Cookie tự động | **Cần CSRF protection** phù hợp |
| `POST /account/email`, session cookie của browser | Cookie tự động | **Cần CSRF protection** phù hợp |
| `POST /admin/action`, HTTP Basic browser đang cache | Browser có thể gửi credentials tự động | Phải đánh giá CSRF, không bỏ qua vì không có session |
| `GET /logout` nhưng thực tế hủy phiên | Unsafe behavior dùng GET | Cần sửa endpoint/method và đánh giá CSRF |

## 11. Login CSRF, logout CSRF và tác động của việc thay đổi trạng thái

CSRF không chỉ là “chuyển tiền” hoặc “xóa dữ liệu”. **Login CSRF** là việc ép browser sử dụng một phiên/tài khoản không mong muốn; **logout CSRF** là việc ép user đăng xuất gây gián đoạn hoặc làm rối trạng thái. Với ứng dụng dùng cookie/session, việc chống CSRF cho login/logout là một phần của thiết kế an toàn.

Trong Spring Security Servlet, CSRF mặc định bảo vệ các request unsafe. Nếu CSRF đang bật, `LogoutFilter` mặc định yêu cầu request `POST` phù hợp để logout; browser form có thể mang `_csrf` hidden input. Đừng thay bằng `GET /logout` thực hiện thao tác đổi trạng thái mà không phân tích an toàn.

Trong OAuth2/OIDC login, tham số `state` trong Authorization Code Flow giúp ràng buộc response chuyển hướng với yêu cầu ban đầu và chống các tấn công liên quan redirect/login CSRF. Nó **không phải CSRF token chung** cho mọi endpoint REST sau khi đã đăng nhập. Tương tự, PKCE bảo vệ authorization code khỏi một số kiểu bị chặn/đánh cắp; nó không làm cookie-based API miễn nhiễm trước CSRF.

Một API có `GET /admin/delete` hoặc `GET /payment/confirm` thay đổi nghiệp vụ là một lỗi cần sửa, vì browser có thể tải/điều hướng GET trong nhiều trường hợp được cookie cho phép. CSRF token cho unsafe method không chữa thiết kế đổi dữ liệu qua safe method.

## 12. XSS, client-side CSRF và CSRF cổ điển: ba vấn đề liên quan nhưng khác nhau

**CSRF cổ điển:** Trang ở origin khác cố gửi request mà browser tự gắn cookie/auth. Biện pháp phù hợp là CSRF token, cookie policies, Origin/Fetch Metadata và phân vùng trust theo threat model.

**XSS (Cross-Site Scripting):** Script của kẻ tấn công thực thi trong origin ứng dụng. Nó có thể trực tiếp gửi request bằng quyền của trang, lấy token ở nơi JavaScript truy cập hoặc thao túng UI. `HttpOnly` giúp giảm đọc cookie auth, nhưng script trong origin vẫn có thể khiến browser gửi request và không giải quyết toàn bộ tác động XSS. Cần encode output, CSP phù hợp và phòng XSS riêng.

**Client-side CSRF:** Một đoạn JavaScript hợp lệ của ứng dụng có thể bị dữ liệu không tin cậy (URL, query, message, fragment...) điều khiển để tạo request đổi trạng thái kèm credential/CSRF header mà chính JavaScript đã được phép gửi. Khi đó kẻ tấn công đang khai thác **logic client**, và SameSite hay CSRF token thông thường có thể không đủ nếu code cùng origin tự gửi token đúng. Phải kiểm tra input và hạn chế các hành động frontend cho phép dữ liệu ngoài điều khiển.

Đừng dùng nhận định “đã có CSRF token nên XSS không còn nguy hiểm” hoặc “đã dùng Bearer header nên không thể có client-side CSRF”. Đây là những lớp bảo vệ cho các vector khác nhau.

## 13. Kiểm thử an toàn: chứng minh giả định trước khi tắt CSRF

Để đánh giá một API cụ thể, nên trả lời các câu hỏi theo đúng thứ tự:

1. **Ai gọi endpoint?** Browser, mobile app, backend, dịch vụ bên thứ ba?
2. **Credential được lấy từ đâu?** Cookie/session, JWT cookie, HTTP Basic do browser nhớ, client cert, hay Bearer header được client chủ động gắn?
3. **Request có đổi trạng thái?** `POST/PUT/PATCH/DELETE` hoặc endpoint GET nào bị thiết kế sai?
4. **Trang bên ngoài có thể kích hoạt request không?** HTML form, navigation, image/link, cross-origin JS trong phạm vi SOP/CORS, URL hoặc dữ liệu điều khiển frontend?
5. **Browser có tự gắn credential khi request đó xảy ra không?** Kiểm tra cookie SameSite/Domain/Path/Secure, cache HTTP Basic, cookie auth fallback và client-specific behavior.
6. **Server kiểm tra CSRF bằng gì?** CSRF token/header, Origin/Referer, Fetch Metadata, media type, chính sách cross-site và ràng buộc token với người dùng/ngữ cảnh?
7. **Khi token sai hoặc vắng mặt thì server có từ chối trước side effect không?** Kiểm tra kết quả thực ở môi trường test được phép, không chỉ dựa vào HTTP status.
8. **Các chain có match đúng đường dẫn?** API bearer-only phải áp dụng đúng `securityMatcher`; browser chain phải giữ CSRF.
9. **Client/frontend có xử lý token mới sau login/logout không?** SPA dùng CSRF token có thể cần lấy token mới vì Spring Security làm mới trạng thái tương ứng.
10. **Nếu cấu hình thay đổi sau này thì rủi ro có trở lại không?** Thêm JWT cookie, Basic auth, endpoint hỗ trợ browser hoặc credentialed CORS phải kéo theo review CSRF.

### Ma trận kiểm thử tối thiểu

| Môi trường thử | Request | Kỳ vọng đúng hướng |
|---|---|---|
| Browser cookie app có CSRF enabled | Unsafe method + cookie hợp lệ + **thiếu CSRF token** | Bị từ chối, không có side effect |
| Browser cookie app có CSRF enabled | Unsafe method + cookie hợp lệ + token CSRF **đúng** | Có thể được xử lý nếu đủ quyền |
| Browser cookie app có CSRF enabled | Unsafe method + token **sai** | Bị từ chối, không có side effect |
| Bearer-only API | Unsafe method không có Authorization | Thường 401, không có side effect |
| Bearer-only API | Bearer hợp lệ nhưng không đủ quyền | Thường 403, không có side effect |
| Bearer-only API | Bearer hợp lệ, đủ quyền | Được phép nếu dữ liệu và nghiệp vụ cũng hợp lệ |
| Stateless JWT cookie app | Request từ trang ngoài trong ngữ cảnh cookie được gửi | Phải có phòng vệ phù hợp; stateless không đủ |
| API `GET` mang side effect | Navigation/link cross-site | Phải sửa thiết kế; không dựa vào CSRF filter cho GET |

**Kiểm thử đúng nghĩa phải quan sát dữ liệu nghiệp vụ có thay đổi hay không.** Ví dụ status 403 có thể đến từ authorization rule, nên cần tách được nguyên nhân thiếu CSRF token khỏi thiếu quyền. Trong Spring Security test, module `spring-security-test` có hỗ trợ request post processor `csrf()` cho MockMvc để kiểm tra hai nhánh có/không có CSRF token phù hợp với chain đang xét.

### Ví dụ `curl` có giới hạn

Trong môi trường test được phép và sử dụng dữ liệu giả, có thể gửi request với cookie thử nghiệm:

```bash
curl --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --cookie "JSESSIONID=EXAMPLE_SESSION" \
  --data "email=demo%40example.test" \
  https://portal.example.test/account/change-email
```

Lệnh trên chỉ là mẫu cấu trúc, **không phải kết quả kiểm thử**; cookie `EXAMPLE_SESSION` là placeholder cố ý không có hiệu lực. `curl` không thực thi chính sách browser SameSite/CORS nên **không chứng minh request từ browser cross-site sẽ có cookie**. Cần kiểm thử tương ứng trong browser thật/automation để đánh giá cookie và Origin policies. Không vô hiệu hóa xác thực TLS bằng `-k` chỉ để cho request chạy.

## 14. Ví dụ Java 17 độc lập: phân loại điều kiện CSRF

Đoạn Java dưới đây chỉ giúp luyện tư duy **kiểm tra điều kiện ban đầu**; nó không phân tích network/browser thực, không sinh CSRF token và không thay thế Spring Security. Mỗi kết quả mô tả một **giả định về mô hình credential**, không chứng minh API an toàn thực tế.

Tạo file `CsrfRiskChecklistDemo.java`:

```java
public class CsrfRiskChecklistDemo {
    enum CredentialMode {
        SESSION_COOKIE,
        JWT_COOKIE,
        BROWSER_BASIC,
        EXPLICIT_BEARER_HEADER
    }

    static String assess(CredentialMode mode, boolean changesState) {
        if (!changesState) {
            return "No state change assumed; verify endpoint behavior";
        }
        return switch (mode) {
            case SESSION_COOKIE, JWT_COOKIE, BROWSER_BASIC ->
                    "Check CSRF: browser may auto-send credentials";
            case EXPLICIT_BEARER_HEADER ->
                    "Classic CSRF condition not established; audit other paths";
        };
    }

    public static void main(String[] args) {
        System.out.println("Session: " +
                assess(CredentialMode.SESSION_COOKIE, true));
        System.out.println("JWT cookie: " +
                assess(CredentialMode.JWT_COOKIE, true));
        System.out.println("Bearer: " +
                assess(CredentialMode.EXPLICIT_BEARER_HEADER, true));
        System.out.println("GET: " +
                assess(CredentialMode.JWT_COOKIE, false));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac CsrfRiskChecklistDemo.java
java CsrfRiskChecklistDemo
```

Đầu ra chính xác:

```text
Session: Check CSRF: browser may auto-send credentials
JWT cookie: Check CSRF: browser may auto-send credentials
Bearer: Classic CSRF condition not established; audit other paths
GET: No state change assumed; verify endpoint behavior
```

Điều cần rút ra: cả session cookie và JWT cookie đều được đặt vào nhóm **browser có thể tự gửi credential**, trong khi Bearer header do client chủ động gắn phải đánh giá thêm cơ chế API có nhận cookie/Basic khác không. Dòng GET chỉ giả định **không đổi trạng thái**; nếu endpoint GET đổi dữ liệu thì không thể kết luận như dòng output.

## 15. Mười lỗi thường gặp và cách sửa

| Nhận định/lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| “`STATELESS` nên tắt CSRF ở mọi nơi” | Browser vẫn có thể tự gửi cookie/Basic | Phân loại credential và request theo filter chain |
| “JWT ký số nên tránh được CSRF” | Chữ ký chứng minh nguồn token, không chứng minh ý định request | Nếu JWT nằm trong cookie, cần phòng CSRF phù hợp |
| “REST API không có CSRF” | REST không quy định credential/browser policies | Phân tích client và cơ chế gửi credential |
| “JSON thì không thể bị CSRF” | Endpoint có thể nhận format khác hoặc có luồng bị lợi dụng | Kiểm tra media type chặt, giữ CSRF khi cookie-authenticated |
| “CORS tắt thì form request không gửi được” | CORS không chặn mọi form/navigation gửi request | Dùng CSRF token và chính sách nguồn bổ sung |
| “`HttpOnly` chặn CSRF” | Nó ngăn script đọc cookie, không ngăn browser đính cookie | Giữ `HttpOnly` nhưng bổ sung CSRF protection |
| “`SameSite=Lax` chặn mọi CSRF” | Same-site cross-origin và sai thiết kế GET vẫn có thể nguy hiểm | Kết hợp token, Origin checks và kiểm endpoint |
| “CSRF cookie tự gửi là đủ” | Attacker có thể khiến browser gửi cookie mà không biết token | Yêu cầu header/form token riêng được server xác minh |
| “Tắt CSRF một API đồng nghĩa cả app an toàn” | Có thể còn browser chain, cookie fallback hoặc endpoint khác | Giới hạn `securityMatcher`, kiểm mọi chain |
| “401/403 đã chứng minh không CSRF” | Có thể do thiếu auth/quyền chứ không phải CSRF | Kiểm side effect và tách nguyên nhân lỗi |

### Ghi nhớ cuối bài

**CSRF xảy ra khi browser có thể gửi request đổi trạng thái kèm credential tự động mà server thiếu cơ chế xác minh request chủ động/hợp lệ.** `REST`, `JSON`, `JWT` hay `SessionCreationPolicy.STATELESS` không tự loại bỏ điều kiện này.

**Quy tắc thực hành:** Giữ CSRF protection cho luồng browser dùng cookie hoặc credential tự gửi; chỉ cân nhắc tắt theo phạm vi đối với API thực sự **Bearer-only, không có browser-managed authentication**, sau khi kiểm tra mô hình request và bảo vệ các endpoint còn lại. Đồng thời duy trì HTTPS, authorization, phòng XSS, chính sách SameSite/CORS và kiểm thử thực tế.

## Tài liệu tham khảo

- [Spring Security — Cross-Site Request Forgery (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): cấu hình CSRF, session/cookie token repository, SPA, và các cân nhắc login/logout.
- [Spring Security — CSRF and Stateless Browser Applications](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): giải thích tại sao custom JWT cookie và HTTP Basic vẫn có rủi ro CSRF dù stateless.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): các mẫu token, Signed Double-Submit Cookie, SameSite, Origin/Fetch Metadata và rủi ro.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): SOP, credentialed requests và preflight.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa safe HTTP methods và lý do không thực hiện hành động thay đổi trạng thái qua GET.
