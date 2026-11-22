# Credentials, cookie và giới hạn của origin ký tự đại diện trong CORS

Giả sử giao diện ở `https://portal.example.test` gọi API tại `https://api.example.test`. Người dùng đã đăng nhập bằng cookie, nhưng trình duyệt vẫn báo CORS khi API trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`. **Tổ hợp hai header đó không hợp lệ cho một request có Fetch credentials mode `include`**: JavaScript chỉ được đọc phản hồi khi server xác nhận **một origin cụ thể được tin cậy** và cho phép credentials.

Ba thành phần phải hiểu riêng:

- **CORS (Cross-Origin Resource Sharing)**: chính sách để browser quyết định script của một origin có thể đọc response từ origin khác hay không.
- **Credentials**: cookie, HTTP authentication, chứng chỉ TLS client và cách browser gửi/tiếp nhận các thông tin đó. Với Fetch, `credentials` quyết định hành vi.
- **Cookie policy**: `SameSite`, `Secure`, `Domain`, `Path`, `HttpOnly`, chính sách chặn hoặc phân vùng third-party cookies. CORS cho phép không bảo đảm cookie được gửi hoặc lưu.

Trong Spring Security Servlet, cần tích hợp CORS trước bước kiểm tra xác thực để preflight không bị từ chối oan, đồng thời giữ đúng chính sách authentication, authorization và CSRF cho API sử dụng cookie. Bài học tập trung vào cách đánh giá, cấu hình và sửa lỗi CORS liên quan đến **credentials, cookie và wildcard origin**.

## 1. Origin khác nhau khi nào?

Một **origin** được xác định bởi **scheme, hostname, port**. Chỉ cần khác một thành phần là cross-origin:

| Frontend | API | Cùng origin? |
|---|---|---|
| `https://portal.example.test` | `https://portal.example.test/api` | Có |
| `https://portal.example.test` | `https://api.example.test` | Không — hostname khác |
| `http://localhost:5173` | `http://localhost:8080` | Không — port khác |
| `http://app.example.test` | `https://app.example.test` | Không — scheme khác |
| `https://app.example.test` | `https://app.example.test:8443` | Không — port khác |

Giá trị trong request thường là `Origin: https://portal.example.test`, **không chứa path**. Không cấu hình `allowedOrigins` bằng URL `https://portal.example.test/dashboard` hoặc thiếu scheme. Nếu nhiều origin được phép, server chọn đúng **một origin** khớp vào response ACAO; không ghi một danh sách ngăn bằng dấu phẩy vào cùng header.

**Same-origin khác same-site.** `portal.example.test` và `api.example.test` có thể thuộc cùng *site* nhưng vẫn khác origin. Vì vậy `SameSite=Lax` có thể cho cookie ở một request same-site, trong khi Fetch cross-origin vẫn cần `credentials: "include"`. Không kết luận từ “cùng tên miền chính” rằng CORS là không cần thiết.

CORS là cơ chế browser áp dụng cho script và một số tài nguyên trong bối cảnh cross-origin. Các HTTP client như `curl`, Java `RestClient` hoặc service backend thông thường **không thi hành CORS như browser**, vì vậy CORS không phải lớp authentication/authorization bảo vệ tài nguyên trước mọi client.

## 2. CORS cấp quyền đọc response, không cấp quyền đăng nhập

Tại tầng HTTP, API có thể trả:

```http
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

- `Access-Control-Allow-Origin` (ACAO) cho biết origin được phép đọc response. Với credentials, giá trị phải là origin cụ thể phù hợp với request, không dùng `*`.
- `Access-Control-Allow-Credentials` (ACAC) với giá trị chính xác `true` cho browser biết phản hồi có thể dùng trong chế độ credentials, sau khi đáp ứng các kiểm tra khác.
- `Vary: Origin` giúp cache hiểu rằng response/header ACAO có thể thay đổi theo request Origin. Quan trọng khi có CDN/proxy caching.

**CORS không tạo cookie, không xác thực user, không trao quyền nghiệp vụ và không bảo vệ endpoint khỏi client không phải browser.** API vẫn phải xác thực token/cookie, kiểm quyền truy cập và không để lộ dữ liệu tài khoản khác.

Cũng cần phân biệt **request đã gửi** và **response được JavaScript đọc**. Một HTML form POST thuộc loại request đơn giản có thể được browser gửi đến server trước khi browser chặn script truy cập response do CORS. Nếu server đã cập nhật dữ liệu, CORS error không đảo ngược side effect. Đây là cơ chế khiến CORS **không thay thế CSRF protection**.

## 3. Fetch credentials mode: omit, same-origin, include

Mã frontend thường gọi API bằng `fetch`. Trường `credentials` ảnh hưởng tới việc browser gửi cookie/HTTP credentials và xử lý cookie được đặt trong response:

| Chế độ | Hành vi |
|---|---|
| `omit` | Không tự gửi credentials và không tiếp nhận credentials từ response theo quy tắc Fetch |
| `same-origin` | Giá trị mặc định; credentials chỉ được gửi và sử dụng trong request cùng origin |
| `include` | Yêu cầu xét gửi credentials kể cả cross-origin, đồng thời browser vẫn áp dụng `SameSite`, giới hạn third-party cookie và CORS |

Ví dụ frontend khác origin và muốn browser đính cookie của API:

```javascript
const response = await fetch("https://api.example.test/api/me", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("API status: " + response.status);
}

const user = await response.json();
console.log(user);
```

Nếu frontend gọi từ `https://portal.example.test`, browser cần ACAO phù hợp (ví dụ origin đó) và ACAC `true`. Dù CORS đúng, cookie vẫn có thể **vắng mặt** vì không có cookie cho API hostname, sai `Domain`/`Path`, `SameSite`, `Secure` hoặc third-party cookie blocking.

Đừng hiểu `credentials: "include"` là **tạo cookie đăng nhập** hoặc **ép browser vượt chính sách cookie**. Nó là yêu cầu ở phía JavaScript, không bảo đảm session hoặc cookie hợp lệ ở server.

Với `XMLHttpRequest`, API tương ứng là `xhr.withCredentials = true` trước khi gửi request.

### Có Bearer token trong header thì sao?

```javascript
await fetch("https://api.example.test/api/me", {
  headers: { Authorization: "Bearer EXAMPLE_ACCESS_TOKEN" }
});
```

Một header `Authorization` do script tự đặt thường làm request cross-origin cần **preflight**. Tuy nhiên, quy tắc chặn ACAO wildcard với credentials liên quan **Fetch credentials mode `include`**, không chỉ sự hiện diện của chữ `Authorization`: khi mode không include và không có cookie browser tự gửi, wildcard ACAO có thể được browser chấp nhận nếu preflight/header policy đúng. Resource server vẫn phải xác minh access token và phân quyền.

Khi thiết kế API private, chỉ cấp origin được tin cậy nếu có dữ liệu cá nhân hoặc frontend được quản lý riêng; không hiểu wildcard như cơ chế bảo vệ tokens khỏi XSS.

## 4. Vì sao không thể dùng origin `*` với credentials?

Response sau **không hợp lệ cho JavaScript gửi `credentials: "include"`**:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"name":"Demo","role":"member"}
```

Browser từ chối cho script đọc response vì ACAO là `*`. Giá trị ACAC `true` **không khắc phục**. Trong Spring Framework, cấu hình `allowedOrigins("*")` với `allowCredentials(true)` cũng bị xem là tổ hợp không hợp lệ; framework có thể ném `IllegalArgumentException` khi kiểm tra cấu hình.

**Response hợp lệ về cú pháp CORS**, giả sử request Origin là `https://portal.example.test`:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"name":"Demo","role":"member"}
```

Đây chỉ là điều kiện cho browser đọc response theo CORS. API vẫn cần login và authorization, request chính phải được gửi, preflight nếu có phải đạt, và cookie vẫn phải được gửi theo chính sách riêng.

Ma trận sau giả sử các điều kiện khác đều hợp lệ:

| Fetch mode | ACAO | ACAC | Script đọc response? |
|---|---|---|---|
| `include` | `*` | `true` | **Không** |
| `include` | `https://portal.example.test` | `true` | **Có** |
| `include` | `https://portal.example.test` | Thiếu | **Không** |
| `include` | `https://another.example.test` | `true` | **Không** |
| `omit` | `*` | Thiếu | **Có**, nếu endpoint công khai và CORS khác hợp lệ |
| `same-origin` khi gọi cross-origin | `*` | Thiếu | **Có**, nhưng browser không tự gửi credentials theo mode mặc định |

**Không được viết `Access-Control-Allow-Origin: https://a.example, https://b.example`.** Header ACAO là một origin cụ thể hoặc ký tự `*` trong trường hợp cho phép. Server cần so khớp `Origin` với allow-list và trả lại đúng một origin được phép.

Đừng tùy tiện cho phép `Origin: null` với credentials trên API nhạy cảm. Giá trị `null` có thể xuất hiện từ ngữ cảnh opaque origin như sandboxed iframe, không chứng minh nguồn request là đáng tin.

## 5. Preflight request khác request chính

Khi browser muốn gửi `POST` cross-origin với `Content-Type: application/json`, `Authorization` hoặc custom header `X-CSRF-TOKEN`, browser thường gửi `OPTIONS` trước:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://portal.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Server có thể phản hồi:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Access-Control-Max-Age: 1800
Vary: Origin
```

Sau khi preflight hợp lệ, browser mới gửi **request chính** theo chính sách Fetch/cookie. Preflight **không gửi cookie chứng thực session của request chính theo quy tắc Fetch**. Vì vậy Spring Security nên xử lý CORS trước authentication; nếu đòi cookie trên `OPTIONS` thì có thể bị `401 Unauthorized` mặc dù request thật của user có cookie hợp lệ.

`Access-Control-Allow-Methods` liệt kê **method của request chính**, không bắt buộc có `OPTIONS` chỉ vì preflight dùng OPTIONS. Spring CORS filter sẽ nhận diện preflight khi tích hợp đúng.

Với requests có credentials, nên giới hạn cụ thể **methods** và **headers**, không mặc định dùng wildcard. Tiêu chuẩn CORS có hạn chế đối với wildcard ở `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Expose-Headers` trong credentialed requests. Spring Framework có thể đáp ứng wildcard allowed methods/headers bằng cách phản ánh method/header được yêu cầu; dù vậy allow-list rõ ràng thường dễ kiểm toán và hạn chế rủi ro hơn.

**Request không preflight không có nghĩa vô hại.** HTML form có thể gửi POST với `application/x-www-form-urlencoded` và browser vẫn tự đính cookie; CORS có thể chặn đọc response nhưng không chắc chặn server thực hiện thay đổi trạng thái.

## 6. Cookies: các điều kiện gửi vẫn độc lập với CORS

| Cookie policy | Ý nghĩa | Điều không nên suy diễn |
|---|---|---|
| `Domain` và host-only cookie | Host/phạm vi cookie được gửi | Cookie do portal tạo không mặc nhiên áp dụng cho API hostname khác |
| `Path` | Request path cần thuộc phạm vi cookie | Không phải policy thay thế quyền truy cập API |
| `Secure` | Hạn chế gửi cookie qua HTTPS theo trình duyệt | Không tự xác thực user hoặc ngăn CSRF |
| `HttpOnly` | Script thông thường không đọc được cookie qua `document.cookie` | Browser vẫn có thể tự gửi cookie |
| `SameSite=Strict` | Hạn chế gửi cookie cross-site mạnh | Không đồng nghĩa chặn mọi request cross-origin nhưng same-site |
| `SameSite=Lax` | Hạn chế nhiều unsafe cross-site requests, có các ngoại lệ liên quan navigation/mặc định browser | Không phải CSRF token |
| `SameSite=None; Secure` | Cho phép cookie tham gia cross-site contexts khi các điều kiện khác phù hợp | Không vượt được third-party cookie restrictions |
| Chặn/phân vùng third-party cookies | Browser có thể ngăn hoặc phân vùng cookie từ site thứ ba | ACAO và ACAC không ghi đè chính sách privacy |

Hai trường hợp dễ nhầm:

**A. Khác origin, cùng site:** Frontend `https://portal.example.test` và API `https://api.example.test` khác host nên khác origin, nhưng có thể cùng site. `SameSite=Lax` thường vẫn cho cookie đúng phạm vi trong same-site requests. Dù vậy, Fetch cần `credentials: "include"` vì khác origin.

**B. Khác site:** Frontend `https://client.other.test` gọi API `https://api.example.test`. Khi cookie cần dùng cross-site, thường phải có `SameSite=None; Secure`, nhưng browser có thể vẫn chặn third-party cookies. Ngay cả khi ACAO, ACAC và Fetch đã đúng, cookie vẫn có thể không xuất hiện.

**HttpOnly không làm cookie bị bỏ qua trong fetch.** Nó ngăn JavaScript truy cập trực tiếp cookie, nhưng browser có thể gửi cookie theo policy. Điều này bảo vệ tính bí mật của cookie trước một số đường XSS đọc `document.cookie`, song vẫn cần phòng XSS/CSRF phù hợp.

### Cookie từ response có được lưu không?

`Set-Cookie` được browser quản lý theo chính sách Fetch và cookie. Với cross-origin Fetch, `credentials: "include"` ảnh hưởng việc browser có xét nhận cookie từ response hay không; sau đó vẫn phải qua Domain, Path, Secure, SameSite, third-party policy. `Access-Control-Allow-Credentials: true` không tự tạo hay bắt buộc lưu cookie.

Một điểm quan trọng: **`Set-Cookie` là forbidden response-header name** nên JavaScript không đọc được bằng `response.headers.get("Set-Cookie")` ngay cả khi server thử thêm `Access-Control-Expose-Headers: Set-Cookie`. Hãy xem Network/Storage trong Developer Tools để kiểm chứng.

Response dùng ACAO `*` không phải giải pháp cho credentialed cookie flow; browser chặn response CORS và không xử lý cookie theo cách frontend mong muốn.

## 7. Spring Security: cấu hình origin được tin cậy cùng credentials

Trong Spring Boot 3 / Spring Security 6 (Servlet + Spring MVC), cách thường dùng là đăng ký `UrlBasedCorsConfigurationSource` và bật `http.cors(...)`. Ví dụ cho frontend portal/admin được tổ chức kiểm soát:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CredentialedCorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
                "https://portal.example.test",
                "https://admin.example.test"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .anyRequest().authenticated())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Đây là **mã cấu hình trong một ứng dụng Spring Boot có Spring Web MVC, Spring Security**, không phải class Java độc lập. `example.test` là tên miền dùng minh họa; để chạy thật phải đăng ký origin chính xác, cấu hình cơ chế authentication, controller và việc cấp/kiểm CSRF token.

Giải thích:

1. `setAllowedOrigins` là allow-list origin rõ ràng. Không truyền `List.of("*")` khi `allowCredentials=true`.
2. `setAllowedMethods` giới hạn method dùng ở request chính; `setAllowedHeaders` cho các header cần thiết ở preflight. Nếu API thật dùng `Authorization`, cần thêm header ấy vào allow-list có kiểm soát.
3. `setAllowCredentials(true)` cho browser dùng credentialed CORS khi Origin được cho phép; **nó không tự tạo cookie hoặc session**.
4. `registerCorsConfiguration("/api/**", cors)` giới hạn policy đến đường dẫn API. Các endpoint khác cần đánh giá riêng.
5. `http.cors(Customizer.withDefaults())` giúp xử lý CORS trước security authentication trong chain phù hợp.
6. `csrf(Customizer.withDefaults())` giữ cơ chế chống CSRF cho kịch bản browser sử dụng cookie. Cần thiết kế token delivery/handler tương ứng cho SPA.
7. `setMaxAge(1800L)` cho phép browser cache kết quả preflight trong khoảng chính sách tối đa, không phải lifetime của cookie hoặc session.

Khi Spring MVC đã cấu hình CORS và không có `CorsConfigurationSource` riêng, Spring Security có thể tích hợp cấu hình MVC. Nếu có nhiều source và nhiều `SecurityFilterChain`, cần chỉ định source cho chain thích hợp. Tránh chồng chéo `@CrossOrigin`, global MVC CORS, gateway CORS và custom `CorsFilter` mà không kiểm response thực tế.

## 8. Wildcard origins và `allowedOriginPatterns` trong Spring

Ví dụ sau là cấu hình **sai** cho requests dùng credentials:

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
```

Spring có thể phát sinh `IllegalArgumentException` do `allowedOrigins` chứa wildcard trong khi `allowCredentials` là true. Tự thêm HTTP response `Access-Control-Allow-Origin: *` không giải quyết được vì browser vẫn chặn credentialed response.

Spring Framework hỗ trợ:

```java
cors.setAllowedOriginPatterns(List.of("https://*.example.test"));
cors.setAllowCredentials(true);
```

Nếu pattern khớp, Spring có thể trả về **origin cụ thể đã khớp** trong ACAO, nên hợp lệ hơn về cú pháp CORS so với `ACAO: *`. Nhưng **hợp lệ về cú pháp không bảo đảm an toàn**: pattern rộng có thể bao gồm subdomain không đáng tin, tenant khác, môi trường test, hostname bị takeover hoặc nơi người dùng bên ngoài tự quản lý nội dung.

Đặc biệt, `allowedOriginPatterns("*")` đi kèm `allowCredentials(true)` có thể khiến ứng dụng phản ánh hầu như mọi Origin và cho script ở bất cứ website nào đọc dữ liệu của user nếu browser gửi cookie. Đây là cách mở quyền quá mức, không phải “mẹo chữa wildcard”.

**Không echo `Origin` tùy ý**. Trước tiên phải so khớp origin với danh sách tin cậy; sau đó trả một giá trị cụ thể và thêm `Vary: Origin` khi response có thể được cache. Ưu tiên liệt kê origin cụ thể thay vì wildcard pattern khi số lượng frontend hữu hạn.

`@CrossOrigin(origins = "*", allowCredentials = "true")` cũng không phải lựa chọn hợp lệ cho credentialed CORS; nếu dùng annotation, cần cấu hình danh sách origin hoặc pattern thực sự được kiểm soát.

## 9. Có khi nào dùng `Access-Control-Allow-Origin: *` được?

**Có**, ví dụ endpoint đọc thông tin công khai và không sử dụng browser credentials, nơi sản phẩm chủ động cho phép script mọi origin đọc response. Khi Fetch mode không phải `include`, ACAO `*` có thể hợp lệ nếu method/header/preflight khác phù hợp.

Ví dụ catalog công khai:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Content-Type: application/json

{"items":["book","pen"]}
```

Nhưng:

- Dữ liệu riêng của user vẫn phải xác thực và phân quyền.
- `Access-Control-Allow-Origin: *` không có nghĩa mọi người được bỏ qua login của server.
- Backend-to-backend requests không cần CORS; thay đổi wildcard không giải quyết lỗi token/TLS/network của service Java.
- Cross-origin request chứa header `Authorization` do JavaScript đặt có thể cần preflight ngay cả khi không dùng cookie.
- Trường hợp frontend cần cookie session, **không chuyển thành wildcard ACAO** để “đỡ lỗi”.

Nếu chung một service có public endpoints và private cookie endpoints, nên áp chính sách CORS theo path hoặc theo các `SecurityFilterChain` phù hợp. Không dùng `allowedOriginPatterns("*") + allowCredentials(true)` cho toàn bộ API.

## 10. CORS và CSRF: hai quyết định khác nhau

**CORS** kiểm soát **quyền script đọc cross-origin response**. **CSRF** bảo vệ một request đổi trạng thái khỏi việc bị trang bên ngoài kích hoạt với credential browser tự động gửi.

Ví dụ một user có cookie đăng nhập của `https://api.example.test`. Trang ngoài có thể gửi form POST tới `/api/account/change-email`. Browser không nhất thiết cho trang tấn công đọc response qua CORS, nhưng nếu cookie được gửi và API không kiểm token CSRF, thay đổi email vẫn có thể được thực hiện.

Với API dùng cookie/session, thường cần cơ chế chống CSRF như token ở header/form field, kết hợp SameSite, kiểm Origin hoặc Fetch Metadata phù hợp. `HttpOnly` không ngăn cookie tự gửi. CORS allow-list **không phải CSRF token**.

Một API thực sự **Bearer-only**, chỉ chấp nhận `Authorization: Bearer` do client chủ động gắn, không nhận cookie hoặc browser-managed authentication khác, có thể đánh giá việc tắt CSRF cho đúng phạm vi API. Nhưng kết luận đó dựa trên **cách vận chuyển credentials**, không chỉ vì `REST`, `JSON` hay `SessionCreationPolicy.STATELESS`.

### SPA cùng site không đồng nghĩa cùng origin

`https://portal.example.test` và `https://api.example.test` có thể cùng site để cookie SameSite được gửi, nhưng khác origin đối với CORS. Một subdomain bị xâm nhập có thể thuộc cùng site. Do đó chỉ dựa vào `SameSite=Strict` mà không xem xét nguồn request và CSRF là chưa đủ cho mọi thiết kế.

## 11. Cách phân biệt lỗi CORS, cookie, xác thực và CSRF

| Triệu chứng | Cần kiểm tra |
|---|---|
| ACAO wildcard bị từ chối với credentials | `credentials: "include"`, server trả ACAO cụ thể hay `*` |
| Browser báo thiếu `Access-Control-Allow-Credentials` | API có thực sự chấp nhận credentialed requests cho origin đó không |
| `OPTIONS` trả 401 | CORS có được xử lý trước Spring Security, và mapping/source có khớp không |
| Browser báo header không cho phép | `Access-Control-Allow-Headers` có `Content-Type`, `X-CSRF-TOKEN`, `Authorization` tùy request không |
| Browser nhận 401, cookie không xuất hiện | Fetch mode, cookie host/path, SameSite, Secure, third-party blocking |
| POST đã tới server nhưng frontend thấy CORS error | Side effect có thể đã chạy; kiểm network/server log và CSRF defense |
| Browser báo CORS error nhưng `curl` chạy | `curl` không áp SOP/CORS; cần test bằng browser |
| `Set-Cookie` xuất hiện nhưng cookie không lưu | Cookie attributes, Fetch mode, third-party policy, browser Issues |
| 403 trên POST khi cookie đã có | Có thể thiếu CSRF token hoặc user thiếu quyền; phải phân biệt |
| Chỉ localhost port khác bị lỗi | Origin gồm scheme, hostname và port, cần allow-list đúng `http://localhost:5173` |
| Hai ACAO headers hoặc giá trị bị lặp | Proxy/gateway và Spring cùng gắn header, cần hợp nhất trách nhiệm |
| API thay đổi origin nhưng cache trả ACAO cũ | `Vary: Origin` hoặc cấu hình cache cần sửa |

Một lỗi CORS có thể xuất hiện dưới dạng `TypeError: Failed to fetch` dù Network đã ghi status của response. Browser chặn script nhìn nội dung response, chứ không nhất thiết nói server không xử lý request. Hãy kiểm tra Network và log đã che credential.

## 12. Cách kiểm thử theo từng lớp

Trong môi trường thử nghiệm được phép:

1. Xác định **Origin** của frontend và Request URL đầy đủ của API, kể cả port/scheme.
2. Kiểm tra lệnh `fetch`: `credentials` đang là `omit`, `same-origin` hay `include`? Có header `Authorization` hoặc custom header nào kích hoạt preflight?
3. Với preflight `OPTIONS`, xem `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` và response `Access-Control-Allow-*`.
4. Kiểm tra response thực: ACAO là đúng **origin đơn lẻ** hay wildcard, ACAC true có cần không, `Vary: Origin` có phù hợp caching không.
5. Trong Developer Tools mục **Application/Storage → Cookies**, kiểm tra cookie áp dụng cho API host, Domain/Path/Secure/HttpOnly/SameSite và browser Issues.
6. Kiểm tra request chính thực sự gửi cookie hay không và API xác thực người dùng thế nào.
7. Với request đổi trạng thái có cookie, xác minh request **không có hoặc sai CSRF token** bị từ chối **trước khi thay đổi dữ liệu**.
8. Thử một origin được phép và một origin bị từ chối; không tự phản chiếu mọi Origin.
9. Nếu nhiều security filter chain, kiểm tra đường dẫn và thứ tự chain để preflight được CORS xử lý đúng.
10. Không đặt session ID, access token hoặc cookie thật trong ảnh/log được chia sẻ.

Lệnh `curl` minh họa **gửi header như preflight** để kiểm tra response server:

```bash
curl -i -X OPTIONS "https://api.example.test/api/orders" \
  -H "Origin: https://portal.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

`example.test` là placeholder tên miền, phải thay bằng endpoint test thật. `curl` chỉ đọc phản hồi HTTP, **không mô phỏng chính sách cookie, third-party restrictions hoặc quyết định CORS của trình duyệt**; xác minh cuối cùng vẫn cần browser.

## 13. Ví dụ Java 17 độc lập: wildcard và credentialed response

Ví dụ sau là **mô hình đơn giản hóa** một phần luật CORS về ACAO/ACAC. Nó không thực hiện HTTP request, không mô phỏng preflight, cookie policy, CSRF hoặc authentication; vì vậy chỉ dùng để học sự khác biệt giữa wildcard và origin cụ thể.

Tạo file `CredentialedCorsDemo.java`:

```java
public class CredentialedCorsDemo {

    static boolean mayReadResponse(
            String requestOrigin,
            String allowedOrigin,
            boolean allowCredentialsHeader,
            boolean includeCredentials) {
        boolean originMatches = "*".equals(allowedOrigin)
                || requestOrigin.equals(allowedOrigin);

        if (!originMatches) {
            return false;
        }
        if (includeCredentials) {
            return allowCredentialsHeader && !"*".equals(allowedOrigin);
        }
        return true;
    }

    public static void main(String[] args) {
        String origin = "https://portal.example.test";

        System.out.println("Wildcard + credentials: " +
                mayReadResponse(origin, "*", true, true));
        System.out.println("Exact origin + credentials: " +
                mayReadResponse(origin, origin, true, true));
        System.out.println("Missing ACAC: " +
                mayReadResponse(origin, origin, false, true));
        System.out.println("Wildcard + no credentials: " +
                mayReadResponse(origin, "*", false, false));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac CredentialedCorsDemo.java
java CredentialedCorsDemo
```

Kết quả chính xác:

```text
Wildcard + credentials: false
Exact origin + credentials: true
Missing ACAC: false
Wildcard + no credentials: true
```

Khi `includeCredentials=true`, hàm chỉ cho đọc response nếu origin khớp cụ thể và ACAC được bật. Trong ứng dụng thật, cần kiểm tra thêm preflight, cookies, third-party policy, authorization và CSRF. Không dùng chương trình này thay thuật toán xác minh origin của browser hay `CorsConfiguration` Spring.

## 14. Tình huống thực hành

**Tình huống A — React localhost gọi Spring Boot localhost.** Frontend `http://localhost:5173`, backend `http://localhost:8080` khác origin. Nếu dùng cookie, frontend cần `credentials: "include"`, server allow-list đúng `http://localhost:5173` và ACAC true. Đồng thời kiểm tra cookie policy localhost và CSRF; không sao chép cấu hình HTTP dev vào production.

**Tình huống B — public catalog.** Endpoint GET trả danh mục công khai không cá nhân hóa. `Access-Control-Allow-Origin: *` có thể hợp lý nếu mục tiêu là mọi origin đọc response mà không dùng credentials. Authentication và rate limiting vẫn là lựa chọn riêng của API.

**Tình huống C — portal và admin cùng gọi private API.** Dùng hai origin tin cậy rõ ràng và ACAC true khi cần cookie. Dù origin đúng, user không có role admin vẫn phải bị từ chối ở endpoint admin; CORS không thay quyền nghiệp vụ.

**Tình huống D — frontend và API khác site, cookie bị chặn.** Ngay cả khi ACAO cụ thể, ACAC true, cookie `SameSite=None; Secure` và Fetch `include`, browser có thể chặn third-party cookies. Cần điều chỉnh kiến trúc cookie/BFF hoặc giải pháp phù hợp, không nới wildcard.

**Tình huống E — request qua reverse proxy.** Proxy đã thêm ACAO còn Spring cũng thêm ACAO. Browser có thể báo lỗi do header trùng hoặc cache trả ACAO cũ. Quy định rõ tầng thực thi CORS và kiểm thực tế ở cả preflight/actual response.

**Tình huống F — Java backend gọi API.** Java client không bị browser SOP/CORS; nếu request thất bại, cần kiểm network/TLS/auth/quyền, không sửa ACAO để làm backend call hoạt động.

## 15. Các lỗi suy luận cần tránh

- **“ACAC true sẽ buộc browser gửi cookie.”** Sai. Fetch mode, cookie attributes và chính sách third-party quyết định chuyện này.
- **“ACAO '*' và ACAC true cùng nhau sẽ mở mọi frontend.”** Sai với credentialed Fetch; browser chặn đọc response.
- **“Echo Origin là cách chữa mọi CORS error.”** Nguy hiểm khi API có dữ liệu người dùng và credentials; phải allow-list origin thật sự tin cậy.
- **“Cookie HttpOnly không đi qua fetch.”** Sai. HttpOnly chỉ hạn chế JavaScript đọc cookie.
- **“SameSite=Lax ngăn tất cả cross-origin requests.”** Sai vì cross-origin có thể same-site.
- **“CORS error chắc chắn ngăn thay đổi dữ liệu.”** Sai: simple request có thể đã chạy ở server trước khi response bị chặn.
- **“Preflight phải mang session cookie.”** Sai theo quy tắc Fetch; xử lý CORS trước authentication.
- **“REST API chỉ có Bearer token cũng phải bật allowCredentials true.”** Không nhất thiết; phụ thuộc Fetch mode và có browser-managed credentials hay không.
- **“Cookie Set-Cookie đọc được nếu expose header.”** Sai. `Set-Cookie` là forbidden response header với script.
- **“CORS bảo vệ API khỏi mọi client.”** Sai. Backend/curl không tuân SOP; server phải kiểm authentication và authorization.
- **“allowedOriginPatterns('*') luôn an toàn vì Spring trả một origin cụ thể.”** Sai: pattern quá rộng vẫn cho mọi origin đọc dữ liệu được xác thực.
- **“Bật đúng CORS thì khỏi chống CSRF.”** Sai: hai cơ chế xử lý các nguy cơ khác nhau.

## 16. Tự kiểm tra

1. **Tại sao `Access-Control-Allow-Origin: *` không dùng với `credentials: "include"`?** Vì browser yêu cầu ACAO là một origin cụ thể phù hợp và ACAC true để script đọc credentialed response.
2. **Fetch mặc định gửi cookie cho API khác origin không?** Không theo mặc định `same-origin`. Cần `include`, nhưng cookie policy vẫn có quyền chặn.
3. **Spring Security cần CORS trước authentication vì sao?** Preflight thường không mang credentials; nếu yêu cầu login trước CORS, server có thể từ chối OPTIONS.
4. **CORS thành công có chứng minh user đã đăng nhập không?** Không; authentication và authorization là nhiệm vụ riêng.
5. **allowedOriginPatterns có thể dùng với credentials không?** Có thể về mặt cú pháp nếu phản ánh origin khớp, nhưng pattern phải giới hạn đến các origin đáng tin, không mở quá rộng.
6. **SameSite và CORS kiểm cùng một khái niệm không?** Không. SameSite liên quan site của cookie, CORS liên quan origin và quyền script đọc response.
7. **Tại sao curl chạy nhưng browser không đọc được response?** Curl không thực thi SOP/CORS và thường không mang cùng cookie policy như browser.
8. **Một API dùng session cookie và form POST có thể bỏ CSRF chỉ vì ACAO được giới hạn không?** Không; form/request có thể được gửi và có side effect dù script tấn công không đọc được response.

**Ghi nhớ:** Khi frontend cần gửi cookie cross-origin, cấu hình chính xác thường là **Fetch `credentials: "include"` + server ACAO một origin tin cậy + ACAC `true`**, đồng thời đáp ứng các chính sách cookie và CSRF. Ký tự đại diện `*` không hợp lệ cho việc script đọc credentialed response. Trong Spring Security, xử lý CORS trước authentication, giới hạn origin cẩn thận và bảo vệ tài nguyên bằng authentication/authorization độc lập.

## Tài liệu tham khảo

- [Spring Security — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS trước Security, `CorsConfigurationSource`, filter chains và preflight.
- [Spring Framework — Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `allowedOrigins`, `allowedOriginPatterns`, `allowCredentials` và wildcard.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, credentialed requests, wildcard, third-party cookies.
- [MDN — Fetch Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `omit`, `same-origin`, `include`.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): thuộc tính cookie và giới hạn browser.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): phân biệt CSRF với các chính sách nguồn và kiểm soát request dùng cookie.
