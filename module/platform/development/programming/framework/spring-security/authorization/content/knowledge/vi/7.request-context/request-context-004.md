# CORS preflight, OPTIONS và quan hệ với quy tắc phân quyền trong Spring Security

## 1. Bài toán: vì sao OPTIONS bị 401/403 trước khi PATCH được gửi?

Giả sử giao diện của một hệ thống quản lý dự án chạy tại `https://app.example.test`, còn API Spring Boot chạy tại `https://api.example.test`. Một người dùng đã đăng nhập muốn sửa dự án bằng JavaScript:

```javascript
await fetch("https://api.example.test/api/projects/p7", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <access-token>"
  },
  body: JSON.stringify({ name: "Project Seven" })
});
```

Trình duyệt nhận thấy đây là **request cross-origin**, dùng phương thức `PATCH` và các header không thuộc nhóm *CORS-safelisted*. Trước khi gửi PATCH thật, nó thường tự động hỏi server bằng một request **OPTIONS preflight**. Preflight không mang access token trong `Authorization` và cũng không mang cookie phiên người dùng theo cơ chế CORS. Nếu Spring Security yêu cầu `authenticated()` hoặc `hasAuthority("project:edit")` **trước khi** xử lý CORS, OPTIONS có thể bị từ chối. Trình duyệt sẽ không gửi PATCH thật và hiển thị lỗi CORS.

Người lập trình đôi khi sửa sai bằng cách thêm:

```java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

Rule này có thể cho tất cả OPTIONS đi qua authorization, nhưng **không tự cấu hình** allowed origins, allowed methods, allowed headers, credentials hoặc response CORS. Nó còn khiến OPTIONS thông thường trên mọi endpoint nhận một quy tắc quá rộng. Cách đúng trong Spring Security Servlet là **tích hợp xử lý CORS phù hợp ở trước bước authorization**, rồi tiếp tục yêu cầu quyền cho **request thực**.

Bài học này hướng dẫn:

1. Phân biệt **origin**, cross-origin, preflight, OPTIONS thông thường và actual request.
2. Đọc đúng `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` và các header response.
3. Hiểu thứ tự Spring Security xử lý CORS, authentication và authorization.
4. Cấu hình `CorsConfigurationSource`/`CorsFilter` hoặc Spring MVC CORS với `http.cors(...)`.
5. Biết tại sao cho phép CORS **không** đồng nghĩa được phép truy cập resource hay bỏ qua CSRF.
6. Xây test tách riêng: preflight được chấp nhận; request thực đủ quyền được xử lý; thiếu quyền vẫn bị từ chối.
7. Xử lý nhiều SecurityFilterChain, gateway, session cookie, Bearer token, Vary và cache preflight.

**Phạm vi:** Spring Security trên **Servlet/Spring MVC**, Java 17+, ví dụ dùng `SecurityFilterChain` thay cho API `WebSecurityConfigurerAdapter` đã lỗi thời. Spring WebFlux dùng `SecurityWebFilterChain`/`CorsWebFilter` và cần cấu hình riêng. Khi copy code, phải đối chiếu version Spring Security/Spring Framework thực tế trong project.

## 2. Origin là gì? Cross-origin khác cross-site

### 2.1. Một origin gồm scheme, host và port

Theo mô hình bảo mật web, origin được xác định bởi bộ ba **scheme + hostname + port**. Ví dụ:

| Địa chỉ truy cập | So với `https://app.example.test` |
| --- | --- |
| `https://app.example.test/dashboard` | Same-origin — path khác không làm đổi origin |
| `https://api.example.test/projects` | Cross-origin — hostname khác |
| `http://app.example.test/dashboard` | Cross-origin — scheme khác |
| `https://app.example.test:8443/dashboard` | Cross-origin — port khác |
| `https://app.example.test:443/dashboard` | Thường cùng origin với URL HTTPS dùng port mặc định 443 |
| `https://another.example.test` | Cross-origin — hostname khác |

**CORS** (*Cross-Origin Resource Sharing*) là cơ chế cho trình duyệt quyết định JavaScript từ origin này có được truy cập response của origin khác hay không. Server công bố chính sách bằng response headers. Browser là bên thực thi phần lớn cơ chế đó.

**Cross-origin không đồng nghĩa cross-site.** Hai subdomain có thể là cross-origin nhưng same-site theo quy tắc site hiện đại; ngược lại, cookie `SameSite` và CSRF liên quan tới khái niệm site. Đừng suy rằng "khác origin" luôn cần cookie `SameSite=None` trong mọi tình huống, hoặc chỉ cần CORS là đã giải quyết CSRF.

### 2.2. CORS không phải cơ chế xác thực

Ba câu hỏi độc lập:

- **CORS:** JavaScript chạy từ `https://app.example.test` có được browser cho phép gửi/đọc một cross-origin request tới API theo chính sách server?
- **Authentication:** Request thực có bằng chứng đăng nhập hợp lệ không? Cookie phiên, Bearer token hoặc cơ chế khác.
- **Authorization:** Chủ thể đã xác thực có quyền `project:edit` trên dự án `p7` của tenant hiện tại hay không?

Có thể có:

```text
CORS allow origin/method/headers = true
Authentication hợp lệ          = false
Authorization project:edit      = false

=> Preflight hợp lệ, nhưng request thực vẫn bị từ chối.
```

Ngược lại, người dùng có role ADMIN nhưng origin không được CORS chấp nhận thì **trình duyệt** có thể chặn ứng dụng frontend đọc response. Một client không bị ràng buộc bởi CORS như `curl` vẫn có thể gọi server; **không coi Origin là một loại vai trò bảo mật**.

## 3. Preflight là gì và khi nào trình duyệt gửi?

Preflight là một request HTTP `OPTIONS` có các CORS-specific headers để hỏi server **trước khi gửi actual request** có phương thức/header không nằm trong tập điều kiện đơn giản. Trình duyệt thường tự tạo preflight; JavaScript frontend không cần gửi `OPTIONS` thủ công.

### 3.1. Dấu hiệu nhận diện CORS preflight

Ví dụ:

```http
OPTIONS /api/projects/p7 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Ý nghĩa:

| Trường | Vai trò |
| --- | --- |
| HTTP method `OPTIONS` | Phương thức của **preflight**, chưa phải thao tác sửa |
| `Origin` | Origin của trang/script đang yêu cầu cross-origin |
| `Access-Control-Request-Method` | Phương thức của request **sẽ** gửi, ví dụ PATCH |
| `Access-Control-Request-Headers` | Danh sách tên header không đơn giản sẽ xuất hiện trong actual request |
| `Authorization` | **Không gửi Bearer token ở preflight** chỉ vì actual request có Authorization |
| `Cookie` | Preflight không mang cookie user theo cơ chế thông thường, kể cả khi actual request cần cookie |

Đặc biệt: `Access-Control-Request-Headers: authorization` chỉ nói “request sau dự định có header Authorization”, **không chứa giá trị token**. Nó cũng không có nghĩa người dùng đã có permission `project:edit`.

Một request `OPTIONS` **không có** `Origin` và `Access-Control-Request-Method` có thể chỉ là OPTIONS HTTP thông thường, không phải CORS preflight. Không được suy “mọi OPTIONS đều là preflight được phép vô điều kiện”.

### 3.2. Những request thường kích hoạt preflight

Các ví dụ phổ biến:

- `PATCH`, `PUT`, `DELETE` cross-origin.
- `POST` với `Content-Type: application/json`.
- `GET` có header `Authorization: Bearer ...` do JavaScript thêm.
- Request có header tùy chỉnh như `X-Request-Id`, `X-CSRF-TOKEN` hoặc `X-Tenant-Id`, tùy điều kiện safelist.
- Một số hành vi của Fetch/CORS bổ sung khác theo chuẩn và chính sách trình duyệt.

Ví dụ `GET` không mặc nhiên bỏ preflight nếu nó gửi header `Authorization`. Và `POST` không mặc nhiên đòi preflight: một số POST có header, content type và điều kiện thuộc nhóm CORS-safelisted có thể được gửi trực tiếp.

### 3.3. Request đơn giản không qua preflight vẫn chịu CORS

Ví dụ JavaScript cross-origin:

```javascript
await fetch("https://api.example.test/api/public/catalog");
```

Request GET không có custom headers có thể **không cần preflight**, nhưng response vẫn phải có CORS headers phù hợp để JavaScript ở origin gọi được đọc response. Nếu thiếu `Access-Control-Allow-Origin`, browser có thể chặn script đọc kết quả; **server có thể đã nhận và xử lý GET**.

Vì vậy, không thể đo độ an toàn của backend bằng “trình duyệt hiển thị CORS error”. Đặc biệt với các request có side effect, một request không preflight có thể đến server trước khi browser quyết định không cho frontend đọc response. Authentication, authorization và CSRF vẫn bắt buộc.

## 4. Hai bước HTTP: preflight và actual request

### 4.1. Bước 1 — Preflight OPTIONS

Giả sử server chỉ cho origin `https://app.example.test` gọi `GET`/`POST`/`PATCH`, dùng các header `Authorization`, `Content-Type`, `X-CSRF-TOKEN`.

Request:

```http
OPTIONS /api/projects/p7 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Response minh họa hợp lệ:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: authorization, content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

**Lưu ý:** đây là một **response minh họa**. CORS processor có thể trả `200` hoặc `204`, thứ tự/header values có thể khác, và `Access-Control-Allow-Methods`/`Access-Control-Allow-Headers` có thể phản ánh subset được yêu cầu chứ không nhất thiết in toàn bộ danh sách server cho phép. Header `Access-Control-Allow-Credentials: true` chỉ thích hợp nếu ứng dụng định dùng credentialed cross-origin requests và cấu hình đã cho phép.

Browser kiểm tra: origin có được phép? actual method dự định có được phép? các header dự định có được phép? Nếu không, nó thường **không tiếp tục gửi actual request**.

**Preflight không được cấp quyền sửa `p7`.** Nó chỉ là bước thương lượng cross-origin trong trình duyệt.

### 4.2. Bước 2 — Actual PATCH

Khi preflight hợp lệ, trình duyệt mới gửi request thực:

```http
PATCH /api/projects/p7 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{"name":"Project Seven"}
```

Spring Security cần đánh giá:

1. CORS actual request có origin được phép không?
2. Token/session có hợp lệ không?
3. Principal có `project:edit` (hoặc permission nghiệp vụ tương ứng) không?
4. Principal có quyền sửa **đúng dự án `p7`** (tenant/owner/membership/state) không?
5. Nếu ứng dụng dùng cookie/session, CSRF token có hợp lệ ở thao tác ghi không?

Request có thể bị 401/403 hoặc lỗi nghiệp vụ ngay cả khi preflight đã thành công. Với response thực, browser cũng kiểm tra CORS response headers trước khi đưa nội dung cho script.

### 4.3. Phân biệt các loại kết quả

| Tình huống | Preflight | Actual request | Kết luận |
| --- | --- | --- | --- |
| Origin được phép, method/header được phép, token hợp lệ và đủ quyền | Đạt | Được xử lý | Luồng hợp lệ |
| Origin đúng, request cần `project:edit` nhưng principal chỉ có `project:read` | Đạt | Bị từ chối bởi authorization | **Không phải lỗi preflight** |
| Origin sai | Bị CORS processor từ chối | Browser thường không gửi actual | Lỗi cấu hình/chính sách origin |
| Header `x-internal-secret` không được CORS cho phép | Bị CORS từ chối | Không gửi actual | Lỗi allowed headers |
| `PATCH` không có trong allowed methods | Bị CORS từ chối | Không gửi actual | Lỗi allowed methods |
| GET cross-origin không preflight, backend trả thiếu CORS headers | Không có preflight | Server có thể đã xử lý GET | Browser không cho JS đọc response |
| OPTIONS không có CORS preflight headers | Không phải CORS preflight đúng nghĩa | Xử lý như OPTIONS thường | Không tự mở tất cả route |
| Preflight đạt nhưng cookie không được browser gửi ở actual | Đạt | Có thể chưa xác thực | Kiểm tra `credentials`/cookie/SameSite |
| Preflight đạt nhưng POST thiếu CSRF token | Đạt | Có thể bị CsrfFilter từ chối | CORS không thay CSRF |

Một browser log thường chỉ hiện “CORS policy blocked” mà không giúp biết request thực có được gửi hay không. Trong DevTools, xem **hai dòng network riêng biệt** và response headers của từng dòng trước khi thay đổi rule.

## 5. Spring Security phải xử lý CORS trước bước yêu cầu authentication

Tài liệu Spring Security nêu rõ preflight không mang cookie phiên `JSESSIONID`. Nếu authentication/authorization xảy ra trước CORS xử lý preflight, nó có thể đánh giá OPTIONS như một request chưa đăng nhập và trả 401/403. Cách hỗ trợ trên Servlet stack là tích hợp xử lý CORS, thường thông qua `CorsFilter`/`CorsConfigurationSource` hoặc qua cấu hình CORS Spring MVC được Spring Security sử dụng.

### 5.1. Dòng xử lý mong muốn

```text
Browser OPTIONS (preflight, không có user credential)
   │
   ▼
SecurityFilterChain chọn chain phù hợp với /api/**
   │
   ▼
CORS processing xử lý trước authorization yêu cầu login
   ├─ Origin/method/header không hợp lệ → CORS rejection
   └─ Hợp lệ → trả preflight response, không gọi API action

Browser PATCH (actual request, có token/cookie khi phù hợp)
   │
   ▼
CORS actual request processing
   │
   ▼
Authentication: Bearer/session...
   │
   ▼
AuthorizationFilter: project:edit
   │
   ▼
Method/domain authorization: tenant/owner/state...
   │
   ▼
Controller/service thực hiện cập nhật
```

Sơ đồ giản lược cơ chế, không phải danh sách filter chính xác trong mọi phiên bản hoặc với mọi custom filter. Điểm bắt buộc là **preflight hợp lệ phải được xử lý mà không đòi token của user**, còn **actual request phải đi qua authentication và authorization bình thường**.

### 5.2. Không cần khai báo permitAll cho mọi OPTIONS khi CORS đã tích hợp đúng

Trong nhiều cấu hình:

```java
http
    .cors(Customizer.withDefaults())
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.PATCH, "/api/projects/*")
            .hasAuthority("project:edit")
        .anyRequest().denyAll()
    );
```

CORS processor được cấu hình đúng sẽ nhận và xử lý **CORS preflight** trước khi `AuthorizationFilter` đòi `project:edit` cho actual PATCH. Request OPTIONS hợp lệ có thể nhận response preflight dù `anyRequest().denyAll()` còn đó. Đây chính là ưu điểm của CORS integration.

Nếu ứng dụng có custom filter, nhiều chain hoặc một gateway từ chối OPTIONS trước Spring, việc chỉ thêm `http.cors(...)` vào một chain có thể không đủ. Cần kiểm tra nơi preflight bị chặn và thứ tự processing thực.

## 6. Ví dụ cấu hình Spring Boot Servlet với CorsConfigurationSource

Đây là mẫu **tích hợp trong dự án Spring Boot MVC** có `spring-boot-starter-web`, `spring-boot-starter-security` và Java 17+. Mẫu giả định API dùng một frontend cố định `https://app.example.test`; tên host là ví dụ, không phải domain sản xuất. Cần thêm nguồn authentication (JWT/session) và controllers vào project. Không chạy class này trực tiếp chỉ với `javac` thuần.

Tạo `ApiCorsSecurityConfig.java`:

```java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Cho phép chính xác origin của frontend đã được tin cậy.
        config.setAllowedOrigins(List.of("https://app.example.test"));

        // Đây là methods CỦA ACTUAL REQUEST, không phải chỉ OPTIONS.
        config.setAllowedMethods(List.of("GET", "POST", "PATCH"));

        // Cho phép frontend yêu cầu gửi các tên header này.
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));

        // Chỉ bật true khi ứng dụng cần credentialed cross-origin requests.
        config.setAllowCredentials(true);

        // Browser có thể cache kết quả preflight, đơn vị: giây.
        config.setMaxAge(1800L);

        // Một response header nghiệp vụ được JS phép đọc nếu server thực sự gửi.
        config.setExposedHeaders(List.of("X-Request-Id"));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        // CORS áp dụng cho API, không tự mở toàn bộ hệ thống.
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth

                        // Nhánh quản trị cần role.
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")

                        // Hành động đọc và sửa có permission riêng.
                        .requestMatchers(
                                HttpMethod.GET,
                                "/api/projects", "/api/projects/*")
                            .hasAuthority("project:read")
                        .requestMatchers(
                                HttpMethod.PATCH, "/api/projects/*")
                            .hasAuthority("project:edit")

                        // Không có rule thì không được truy cập.
                        .anyRequest().denyAll()
                )
                .build();
    }
}
```

### 6.1. Những điều cấu hình thực sự làm

- `UrlBasedCorsConfigurationSource` lưu chính sách CORS cho `/api/**`.
- `http.cors(Customizer.withDefaults())` yêu cầu Spring Security sử dụng tích hợp CORS; `CorsFilter` được sắp xếp đúng để preflight được xử lý trước authorization khi chọn cấu hình phù hợp.
- Origin khác `https://app.example.test` không được phép theo cấu hình này.
- Chỉ các **actual methods** `GET`, `POST`, `PATCH` được phép ở tầng CORS; **POST không tự được phép ở tầng authorization**, vì không có role/authority rule cho POST projects và fallback là deny.
- `Authorization` nằm trong allowed headers có nghĩa browser được phép gửi header này trên request thực; **không** có nghĩa token hợp lệ hoặc role đã được cấp.
- `hasRole("ADMIN")` theo convention mặc định đòi authority `ROLE_ADMIN`.
- `hasAuthority("project:edit")` đòi chính xác authority `project:edit`. Một role `ROLE_EDITOR` không tự sinh permission đó nếu app chưa map.
- `anyRequest().denyAll()` bảo vệ URL/method chưa có rule.
- `setAllowCredentials(true)` là lựa chọn của mẫu để minh họa luồng có credential; **chỉ giữ true nếu sản phẩm thật cần**. Với Bearer-only frontend không dùng cookie/credentialed fetch, cân nhắc giảm quyền này và chọn cấu hình phù hợp.

**Không bỏ qua:** mẫu không cấu hình authentication provider, resource server, session policy, CSRF hay JSON exception handler. Hãy bổ sung theo kiến trúc thật. Nếu dùng session/cookie, các thao tác ghi có thể cần CSRF token; đừng bỏ CSRF chỉ để khắc phục lỗi CORS.

### 6.2. Vì sao Bean trả về UrlBasedCorsConfigurationSource?

Tài liệu Spring Security hiện đại nêu Spring Security tự cấu hình CORS theo một `UrlBasedCorsConfigurationSource` có sẵn khi dùng DSL; nếu có **nhiều** bean `CorsConfigurationSource`, framework có thể không biết chọn bean nào và cần cấu hình nguồn tường minh cho mỗi chain.

Để tránh suy diễn, có thể chỉ rõ nguồn:

```java
http.cors(cors -> cors
        .configurationSource(corsConfigurationSource()));
```

Dòng trên nằm trong class config khi `corsConfigurationSource()` có sẵn, nhưng nếu project có cấu hình @Bean khác nhau hoặc nhiều chain, hãy ưu tiên inject một nguồn cụ thể vào method tạo chain. Không tự tạo nhiều `CorsFilter` chồng lên nhau mà không kiểm tra thứ tự và response headers.

### 6.3. Một số lựa chọn cấu hình phải xác định riêng

| Quyết định | Gợi ý |
| --- | --- |
| Frontend origin nào được phép? | Allowlist cụ thể theo scheme, host, port |
| API nào cần CORS? | `/api/**` hoặc phạm vi nhỏ hơn theo contract |
| Actual method nào cần? | Chỉ GET/POST/PATCH/PUT/DELETE thật sự hỗ trợ |
| Header nào cần? | `Authorization`, `Content-Type`, CSRF header theo app |
| Gửi cookie cross-origin? | Chỉ bật credentials khi có nhu cầu và trust rõ ràng |
| Frontend đọc custom response header? | Dùng `exposedHeaders` khi cần |
| Cache preflight? | `maxAge` cân bằng hiệu năng với khả năng thay đổi policy |
| Nhiều chain? | Cấu hình CORS cho đúng chain; có fallback chain an toàn |
| JWT Bearer? | Xác minh token/authorities ở **actual request**, không phải preflight |
| Cookie session? | Xác minh session, CSRF và thuộc tính cookie ở **actual request** |

## 7. Cấu hình CORS bằng Spring MVC hoặc @CrossOrigin

Spring MVC có hỗ trợ CORS ở `HandlerMapping`. Nếu project đã dùng Spring MVC và không cung cấp `CorsConfigurationSource` tường minh cho Spring Security, có thể bật tích hợp `http.cors(...)` để Spring Security dùng cấu hình CORS do MVC cung cấp.

### 7.1. Ví dụ cấu hình toàn cục qua WebMvcConfigurer

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST", "PATCH")
                .allowedHeaders(
                        "Authorization", "Content-Type", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
```

Để Spring Security xử lý CORS theo cấu hình MVC, cần thiết lập trong security chain:

```java
http.cors(Customizer.withDefaults());
```

**Chọn một nguồn chính sách có trách nhiệm rõ ràng.** Mẫu ở mục 6 dùng bean `UrlBasedCorsConfigurationSource`; mẫu ở mục 7 dùng MVC. Không cần dùng cả hai cùng lúc chỉ vì thấy hai tutorial. Trong ứng dụng thực, nhiều nguồn CORS không nhất quán có thể dẫn tới header bị trùng, chain chọn sai nguồn hoặc preflight chặn trước khi đến MVC.

### 7.2. @CrossOrigin ở controller

Ví dụ:

```java
@RestController
@RequestMapping("/api/catalog")
@CrossOrigin(origins = "https://app.example.test")
public class CatalogController {

    @GetMapping
    public List<ItemView> catalog() {
        return catalogService.publicItems();
    }
}
```

Đây là **fragment**, cần `ItemView` và `catalogService` thực tế. `@CrossOrigin` là cách khai báo CORS cho handler; nó **không** thay thế `hasRole`/`hasAuthority`/`@PreAuthorize` và không chứng minh catalog có thể được đọc bởi bất kỳ user nào.

Nếu vừa có global CORS config vừa có `@CrossOrigin`, Spring MVC có quy tắc **kết hợp** configuration; nhiều thuộc tính dạng danh sách có thể được cộng gộp. Review để không vô tình mở thêm origins/methods so với chủ đích.

### 7.3. Khi nào nên dùng kiểu nào?

- **Một API và một frontend ổn định:** bean `UrlBasedCorsConfigurationSource` hoặc MVC CORS global đều phù hợp nếu tích hợp đúng.
- **Controller-specific origins:** `@CrossOrigin` có thể tiện, nhưng cần review các khai báo và chính sách toàn cục.
- **Nhiều SecurityFilterChain với nhiều chính sách CORS khác nhau:** chỉ rõ nguồn CORS của từng chain khi cần.
- **CORS xử lý ở gateway:** phải biết backend vẫn nhận headers nào, proxy có tự thêm/ghi đè CORS headers không, và ai chịu trách nhiệm cuối cùng.
- **WebFlux:** không áp dụng nguyên xi `HttpSecurity`/`CorsFilter` của Servlet.

## 8. OPTIONS trong Spring Security: khi nào permitAll là đúng?

### 8.1. Không đánh đồng mọi OPTIONS với preflight

Hai request cùng dùng method OPTIONS nhưng mang ý nghĩa khác nhau:

```http
OPTIONS /api/projects/p7 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
```

Đây là một **preflight** theo CORS nếu các điều kiện còn lại hợp lệ.

```http
OPTIONS /api/projects/p7 HTTP/1.1
Host: api.example.test
```

Đây là một OPTIONS thông thường không có CORS preflight headers. Nó có thể được xử lý theo contract HTTP của server, bằng một handler `OPTIONS`, hoặc bị từ chối tùy cấu hình. Nó không mặc nhiên phải đi qua một rule public chung.

### 8.2. Vì sao mở mọi OPTIONS chưa giải quyết CORS?

Giả sử cấu hình:

```java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.anyRequest().denyAll()
```

Rule thứ nhất có thể khiến OPTIONS được phép ở **bước authorization**, nhưng browser vẫn cần:

- `Access-Control-Allow-Origin` phù hợp origin yêu cầu.
- `Access-Control-Allow-Methods` chứa actual method dự định.
- `Access-Control-Allow-Headers` chấp nhận các headers dự định gửi.
- `Access-Control-Allow-Credentials` khi là credentialed request.
- Response preflight đúng ngữ nghĩa, không bị filter/gateway chặn sai.

Nếu không có CORS processing, việc `permitAll` không tự tạo các response headers này. Kết quả vẫn có thể là lỗi CORS. Đồng thời, mở toàn bộ OPTIONS có thể che lỗi route/security thiết kế sai.

### 8.3. Khi nào cần rule OPTIONS tường minh?

Có thể cần khi:

- API **thật sự cung cấp một OPTIONS endpoint** theo contract và bạn muốn phân quyền riêng.
- Có một lớp gateway/legacy CORS xử lý preflight bên ngoài Spring Security và cần rule tương thích được kiểm thử rõ.
- Có yêu cầu HTTP protocol cụ thể được phân tích rành mạch.

Ngay cả khi đó, nên giới hạn matcher vào **đường dẫn có nhu cầu**, không mở `/**` theo thói quen. Với Spring Security Servlet tích hợp CORS hiện đại, **ưu tiên để CORS processor xử lý preflight** thay vì viết một authorization rule cho mọi OPTIONS.

### 8.4. First-match-wins và thứ tự rule

Trong `authorizeHttpRequests`, matcher đầu tiên khớp được sử dụng. Vì vậy:

```java
// NGUY HIỂM: rule rộng che nhánh admin trong actual request.
.requestMatchers("/api/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

CORS không sửa lỗi này. Nếu dùng `securityMatcher("/api/**")` để chọn filter chain, hãy đảm bảo các request admin (kể cả OPTIONS preflight lẫn actual method) vào đúng chain. Một fallback chain bảo vệ route không match chain API là cần thiết khi ứng dụng có nhiều filter chains.

## 9. CORS, authorization và CSRF là ba lớp bảo vệ khác nhau

### 9.1. Origin được phép không chứng minh user đáng tin

Một browser gửi `Origin: https://app.example.test` chỉ giúp server xác định **nguồn JavaScript** trong cơ chế CORS; nó không phải credential. Client ngoài browser có thể tự đặt `Origin`. Người dùng vẫn cần authentication hợp lệ và permission trên resource.

**Không viết policy kiểu:**

```java
// Anti-pattern: KHÔNG dùng Origin thay thế authorization.
if ("https://app.example.test".equals(request.getHeader("Origin"))) {
    // Cho phép xóa tài nguyên bất kể principal.
}
```

Đúng hơn: CORS kiểm tra origin, còn `SecurityFilterChain`/service kiểm tra role, permission, tenant, owner và trạng thái.

### 9.2. CSRF vẫn quan trọng với cookie/session

Ví dụ cross-origin frontend dùng cookie session:

```javascript
await fetch("https://api.example.test/api/projects/p7", {
  method: "PATCH",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ name: "Updated" })
});
```

Ứng dụng phải xử lý riêng:

1. **CORS:** cho phép origin đã tin cậy, PATCH, Content-Type và X-CSRF-TOKEN.
2. **Cookie/session:** browser có được phép gửi session cookie ở actual request không, xét thuộc tính cookie và chính sách browser?
3. **CSRF:** token phải được cấp/đọc/gửi theo `CsrfTokenRepository` và cơ chế Spring Security mà project chọn.
4. **Authorization:** session user có quyền sửa dự án cụ thể không?

Với request **cross-site** dùng cookie, `SameSite=None; Secure` có thể cần thiết theo mô hình browser; nhưng các trình duyệt có thể hạn chế third-party cookies. Với request cross-origin nhưng **same-site**, suy luận SameSite có thể khác. `allowCredentials(true)` của CORS **không tự bật khả năng gửi cookie** hoặc bỏ qua chính sách cookie.

### 9.3. Bearer token không đồng nghĩa CORS authorization

Với `Authorization: Bearer ...`, trình duyệt thường cần preflight do header Authorization không safelisted. Nhưng preflight không mang token. Backend chỉ kiểm tra token ở actual request; `JwtAuthenticationConverter` hoặc các provider khác phải cấp authorities thật cho `hasAuthority(...)`.

Đối với backend chỉ dùng Bearer token do JS cung cấp, xác định rõ cookie có được sử dụng ở chỗ khác không và cơ chế CSRF có cần hay không. Không tắt CSRF **chỉ vì nhìn thấy CORS error**. Nếu ứng dụng có cả session và Bearer token, threat model cần xem từng cơ chế credential.

### 9.4. Simple requests và side effect

Một request cross-origin thuộc loại không cần preflight có thể đến server, thậm chí gây thay đổi nếu server không kiểm tra CSRF/authorization. Browser ngăn script đọc response không có nghĩa server chưa làm việc. Vì vậy, không dùng CORS như hàng rào duy nhất để chặn write operations hay chống CSRF.

## 10. Credentials, wildcard và headers cần hiểu đúng

### 10.1. Access-Control-Allow-Origin không được dùng "*" với credentials

Khi server cho phép credentialed requests bằng `Access-Control-Allow-Credentials: true`, không nên và không được cấu hình `Access-Control-Allow-Origin: *` cho request credentialed theo quy tắc CORS của trình duyệt. Spring Framework cũng không cho `allowOrigins("*")` khi `allowCredentials(true)`; có thể dùng danh sách origin cụ thể hoặc `allowedOriginPatterns` được thiết kế cẩn thận.

Ví dụ tốt:

```text
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
```

Ví dụ sai cho credentialed browser access:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Với public read-only API thật sự không dùng credentials, wildcard có thể hợp lệ và đơn giản hơn; đây là quyết định riêng theo mức độ công khai của tài nguyên. Không chọn wildcard chỉ để xóa cảnh báo console.

### 10.2. Origin có thể mang giá trị "null"

Header `Origin: null` có thể xuất hiện từ sandboxed documents hoặc những nguồn opaque origin. Đừng tự thêm `"null"` vào allowlist chỉ vì thấy log có giá trị này. Cần đánh giá nguồn và mức tin cậy thực tế; `null` không phải một hostname đã xác minh.

### 10.3. Allowed headers khác exposed headers

| Thuộc tính | Hướng tác động | Ví dụ |
| --- | --- | --- |
| `allowedHeaders` | Browser có thể **gửi** các request headers được khai báo | Authorization, Content-Type, X-CSRF-TOKEN |
| `exposedHeaders` | JS có thể **đọc** một số response headers ngoài nhóm safelisted | X-Request-Id, X-RateLimit-Remaining |
| `allowedMethods` | Browser được dùng actual method nào trong cross-origin request | GET, POST, PATCH |
| `allowCredentials` | Cho phép trình duyệt dùng credentialed CORS response theo policy | true/false |
| `allowedOrigins` | Origin nào được nhận | https://app.example.test |
| `maxAge` | Thời gian browser được cache kết quả preflight | 1800 giây |

`setExposedHeaders(List.of("X-Request-Id"))` **không** đồng nghĩa server tự thêm response header `X-Request-Id`; ứng dụng phải thật sự gửi header đó. Tương tự, `setAllowedHeaders("Authorization")` không tạo authorization token.

### 10.4. Chỉ dùng allowlist đáng tin

Đừng phản chiếu mọi request `Origin` vào `Access-Control-Allow-Origin` rồi đồng thời bật credentials. Với session/cookie, điều đó có thể cho scripts ở origin không tin cậy đọc response riêng tư. Các dynamic allowlist theo tenant cần được quản lý và xác minh chặt, tránh cho user tự đăng ký một origin ác ý vào danh sách được tin.

**CORS không thay thế phân quyền dữ liệu**, nhưng một cấu hình CORS quá rộng có thể mở rộng tập website được phép tương tác và đọc thông tin nhạy cảm của user đã đăng nhập.

## 11. Cache preflight, Vary và lỗi khi đổi policy

### 11.1. Access-Control-Max-Age

`Access-Control-Max-Age` cho browser biết có thể cache kết quả preflight trong bao lâu; cache preflight của browser **tách biệt** với HTTP cache thông thường và có giới hạn riêng tùy browser. Ví dụ:

```http
Access-Control-Max-Age: 1800
```

nghĩa là server gợi ý 1.800 giây. Browser có thể áp dụng cap thấp hơn. Nếu thay origin/method/header policy, kết quả preflight được cache có thể còn ảnh hưởng trong một khoảng thời gian. Đừng nghĩ “tắt cache ở browser” tương đương thay đổi cache của reverse proxy.

**Preflight cache không cache kết quả authorization của actual request.** Quyền `project:edit` có thể được thu hồi và actual request sau vẫn phải bị từ chối dù browser không gửi lại OPTIONS trong thời gian cache.

### 11.2. Vary và shared HTTP cache

Khi CORS response thay đổi theo `Origin` hoặc preflight headers, hệ thống có thể cần:

```http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

để shared cache/CDN không dùng nhầm response header của origin/method/header này cho origin/method/header khác. Spring CORS processor thường quản lý Vary phù hợp; nếu proxy tự thay đổi cache headers, cần kiểm tra end-to-end.

Với nội dung cá nhân hóa, tránh public caching response chứa dữ liệu phiên. Đây là câu chuyện HTTP cache/security riêng, không phải do CORS tự giải quyết.

### 11.3. Response 200/204 không đủ để kết luận

Preflight `200` hoặc `204` chưa đủ nếu browser cần header allow origin/method/headers mà response thiếu. Ngược lại, actual request trả `401` hoặc `403` kèm CORS headers đúng có thể là kết quả authorization bình thường, không phải lỗi preflight.

**Cần kiểm tra cả status và header**, đúng loại request.

## 12. Nhiều SecurityFilterChain, gateway và reverse proxy

### 12.1. securityMatcher và requestMatchers khác nhau

Trong Servlet:

- `http.securityMatcher("/api/**")` quyết định **chain** có được chọn cho request hay không.
- `authorizeHttpRequests(...requestMatchers(...))` quyết định **authorization rule** trong chain đó.
- `http.cors(...)` cấu hình **CORS integration** của chain phù hợp.

Nếu ứng dụng có nhiều chain (API JWT, web session, actuator), phải bảo đảm OPTIONS và actual request đến **đúng chain**, và chain đó có CORS processing đúng. Một chain chỉ match `/api/**` không bảo vệ mặc định mọi URL ngoài phạm vi đó; cần fallback chain nếu yêu cầu bảo vệ toàn bộ ứng dụng.

### 12.2. CORS policy theo từng chain

Một thiết kế có thể là:

```java
// Fragment: SecurityFilterChain cho /api/**
http.securityMatcher("/api/**")
    .cors(cors -> cors
        .configurationSource(apiCorsConfigurationSource))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Đoạn này chỉ minh họa cách **chọn nguồn CORS tường minh** cho chain API; `apiCorsConfigurationSource` phải là bean/đối tượng đã được định nghĩa, không phải API có sẵn. Cần cấu hình authentication, các chain khác và fallback tương ứng. Nếu có nhiều bean `CorsConfigurationSource`, hãy làm rõ bean nào được dùng cho mỗi chain; không dựa vào auto detection khi ambiguous.

### 12.3. Gateway có thể chặn OPTIONS trước Spring

Một reverse proxy/WAF/API gateway có thể:

- Từ chối method OPTIONS.
- Không forward `Origin` hoặc `Access-Control-Request-*`.
- Tự trả preflight response mà backend không nhìn thấy.
- Thêm CORS headers khác với backend; tạo header trùng/mâu thuẫn.
- Cache response theo key không bao gồm Origin hoặc method.
- Redirect HTTP→HTTPS hoặc canonical URL khiến preflight gặp lỗi tùy browser/client.

Trong các hệ thống đó, sửa `SecurityFilterChain` một mình không giải quyết được mọi lỗi. Cần xác định **CORS owner** (gateway hay backend), chính sách thực và đường đi request.

### 12.4. Frontend localhost và port

Khi phát triển, origin `http://localhost:3000`, `http://localhost:5173` và `http://127.0.0.1:5173` là những origin khác nhau. Đặt `allowedOrigins("http://localhost:5173")` chỉ cấp đúng origin ấy; port khác không được cấp tự động.

Đừng nới toàn bộ `*.example.com` hoặc `*` trong production chỉ vì frontend dev server đổi port. Dùng cấu hình theo môi trường rõ ràng và review chính sách của production riêng.

## 13. Ví dụ Java 17 độc lập: preflight không cấp quyền actual request

Để nhìn thấy nguyên tắc mà không cần tải Spring, chương trình dưới đây **mô phỏng** hai loại quyết định riêng:

- `preflight(...)` chỉ kiểm tra origin, method dự định và danh sách header dự định.
- `actual(...)` kiểm tra origin cùng quyền/role thật của user cho action cụ thể.

Đây **không phải Spring CorsFilter/AuthorizationFilter**; nó không cài HTTP parser, cookie, JWT, CSRF, browser hoặc quyền trên đối tượng. Nó chỉ làm rõ vì sao preflight đạt chưa đồng nghĩa PATCH được cấp phép.

Tạo tệp `CorsAuthorizationConceptDemo.java`:

```java
import java.util.Locale;
import java.util.Set;

public class CorsAuthorizationConceptDemo {

    private static final String TRUSTED_ORIGIN =
            "https://app.example.test";

    private static final Set<String> CORS_METHODS =
            Set.of("GET", "POST", "PATCH");

    private static final Set<String> CORS_HEADERS =
            Set.of("authorization", "content-type", "x-csrf-token");

    record Preflight(
            String origin,
            String requestedMethod,
            Set<String> requestedHeaders) {}

    static String preflight(Preflight request) {
        if (request == null || !TRUSTED_ORIGIN.equals(request.origin())) {
            return "CORS_REJECT";
        }
        if (!CORS_METHODS.contains(request.requestedMethod())) {
            return "CORS_REJECT";
        }
        if (request.requestedHeaders() == null) {
            return "CORS_REJECT";
        }
        for (String header : request.requestedHeaders()) {
            if (header == null
                    || !CORS_HEADERS.contains(header.toLowerCase(Locale.ROOT))) {
                return "CORS_REJECT";
            }
        }
        return "PREFLIGHT_OK";
    }

    static String actual(
            String origin, String method,
            String path, Set<String> authorities) {

        if (!TRUSTED_ORIGIN.equals(origin)) {
            return "CORS_REJECT";
        }
        if (method == null || path == null) {
            return "AUTHZ_DENY";
        }

        String required;
        if (method.equals("PATCH") && path.matches("/api/projects/[^/]+")) {
            required = "project:edit";
        } else if (method.equals("GET")
                && path.matches("/api/projects/[^/]+")) {
            required = "project:read";
        } else if (method.equals("GET")
                && path.equals("/api/admin/users")) {
            required = "ROLE_ADMIN";
        } else {
            return "AUTHZ_DENY";
        }

        return authorities != null && authorities.contains(required)
                ? "ALLOW" : "AUTHZ_DENY";
    }

    public static void main(String[] args) {
        Preflight valid = new Preflight(
                TRUSTED_ORIGIN, "PATCH",
                Set.of("Authorization", "Content-Type"));
        Preflight wrongOrigin = new Preflight(
                "https://untrusted.example.test", "PATCH",
                Set.of("Authorization", "Content-Type"));
        Preflight wrongMethod = new Preflight(
                TRUSTED_ORIGIN, "DELETE",
                Set.of("Authorization"));
        Preflight wrongHeader = new Preflight(
                TRUSTED_ORIGIN, "PATCH",
                Set.of("X-Internal-Secret"));

        Set<String> viewer = Set.of("project:read");
        Set<String> editor = Set.of("project:read", "project:edit");
        Set<String> admin = Set.of("ROLE_ADMIN");

        System.out.println("valid-preflight=" + preflight(valid));
        System.out.println("wrong-origin-preflight="
                + preflight(wrongOrigin));
        System.out.println("wrong-method-preflight="
                + preflight(wrongMethod));
        System.out.println("wrong-header-preflight="
                + preflight(wrongHeader));

        System.out.println("viewer-patch="
                + actual(TRUSTED_ORIGIN, "PATCH",
                        "/api/projects/p7", viewer));
        System.out.println("editor-patch="
                + actual(TRUSTED_ORIGIN, "PATCH",
                        "/api/projects/p7", editor));
        System.out.println("anonymous-patch="
                + actual(TRUSTED_ORIGIN, "PATCH",
                        "/api/projects/p7", Set.of()));
        System.out.println("viewer-get="
                + actual(TRUSTED_ORIGIN, "GET",
                        "/api/projects/p7", viewer));
        System.out.println("viewer-admin="
                + actual(TRUSTED_ORIGIN, "GET",
                        "/api/admin/users", viewer));
        System.out.println("admin-admin="
                + actual(TRUSTED_ORIGIN, "GET",
                        "/api/admin/users", admin));
        System.out.println("unknown-route="
                + actual(TRUSTED_ORIGIN, "POST",
                        "/api/projects/p7", editor));
        System.out.println("untrusted-editor="
                + actual("https://untrusted.example.test", "PATCH",
                        "/api/projects/p7", editor));
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac CorsAuthorizationConceptDemo.java
java CorsAuthorizationConceptDemo
```

Stdout mong đợi:

```text
valid-preflight=PREFLIGHT_OK
wrong-origin-preflight=CORS_REJECT
wrong-method-preflight=CORS_REJECT
wrong-header-preflight=CORS_REJECT
viewer-patch=AUTHZ_DENY
editor-patch=ALLOW
anonymous-patch=AUTHZ_DENY
viewer-get=ALLOW
viewer-admin=AUTHZ_DENY
admin-admin=ALLOW
unknown-route=AUTHZ_DENY
untrusted-editor=CORS_REJECT
```

**Phân tích quan trọng:**

1. `valid-preflight=PREFLIGHT_OK` **không chứa principal**; nó chỉ xác nhận origin/method/headers phù hợp với chính sách CORS.
2. Viewer và editor dùng **cùng preflight** cho PATCH, nhưng viewer bị `AUTHZ_DENY` và editor được `ALLOW` do authorities khác nhau.
3. Admin cần `ROLE_ADMIN`; có `project:read` không đủ.
4. Một URL/method không được khai báo nhận `AUTHZ_DENY` theo chính sách demo.
5. Origin untrusted bị mô phỏng trả `CORS_REJECT` dù user có permission. Điều này không biến Origin thành credential; ở backend thật, client ngoài browser vẫn có thể gửi request tùy ý nên authorization luôn bắt buộc.
6. Chương trình chưa kiểm tra tenant, owner, trạng thái, cookie, CSRF hoặc body; mọi thao tác thực còn phải có domain policy.

Các chuỗi `PREFLIGHT_OK`, `CORS_REJECT`, `AUTHZ_DENY` là **nhãn học tập tự đặt**, không phải class hay HTTP status chuẩn của Spring Security.

## 14. Kiểm thử: phải kiểm preflight và actual request riêng biệt

### 14.1. Ma trận trường hợp

| Request | Origin | Token/session/authority | Kỳ vọng đúng lớp |
| --- | --- | --- | --- |
| OPTIONS preflight PATCH có headers hợp lệ | Trusted | **Không có credential user** | CORS chấp nhận preflight |
| OPTIONS preflight PATCH từ origin lạ | Untrusted | Không có | CORS từ chối |
| OPTIONS preflight DELETE khi CORS chỉ cho GET/POST/PATCH | Trusted | Không có | CORS từ chối method |
| OPTIONS preflight với header không được phép | Trusted | Không có | CORS từ chối header |
| PATCH actual sau preflight | Trusted | `project:edit` | Vượt qua functional authorization; object policy còn áp dụng |
| PATCH actual | Trusted | Chỉ `project:read` | **403/deny** theo cấu hình API, không phải lỗi preflight |
| PATCH actual | Trusted | Chưa đăng nhập | Authentication challenge/deny theo entry point |
| GET actual với `project:read` | Trusted | `project:read` | Vượt qua quyền chức năng |
| GET actual đến API admin | Trusted | Chỉ `project:read` | Bị role rule từ chối |
| OPTIONS thông thường thiếu preflight headers | Không có/không đầy đủ | Bất kỳ | Theo HTTP route/security policy; không tự hiểu là CORS preflight |
| POST có session nhưng thiếu CSRF | Trusted | Đã đăng nhập | Có thể bị CsrfFilter từ chối |
| Cross-origin GET đơn giản không preflight | Trusted | Phụ thuộc route | Browser vẫn kiểm tra CORS response; backend vẫn kiểm authz |
| Preflight được cache, quyền user vừa bị thu hồi | Trusted | Quyền actual đã hết | Request thực phải bị từ chối |

“Vượt qua functional authorization” chỉ là bước ở HTTP security; controller, business rules và object-level policy có thể vẫn trả lỗi. Test không nên ép mọi case thành `200` hoặc `403` nếu hệ thống đang redirect login hoặc thiếu handler.

### 14.2. MockMvc test preflight không có user

Đây là **test fragment** cần Spring Security Test, `MockMvc`, application context, CORS/security configuration ở mục 6 và imports thích hợp:

```java
@Test
void preflightPatchWorksWithoutAuthentication() throws Exception {
    mockMvc.perform(options("/api/projects/p7")
            .header("Origin", "https://app.example.test")
            .header("Access-Control-Request-Method", "PATCH")
            .header("Access-Control-Request-Headers",
                    "authorization, content-type"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.example.test"));
}
```

Với `CorsFilter`/`DefaultCorsProcessor` mặc định của cấu hình mẫu, preflight hợp lệ thường trả 200 và CORS headers. Nếu gateway hoặc custom processor trả 204 hợp lệ, test status theo contract tương ứng. Quan trọng nhất: **không cần `@WithMockUser`**, và không có controller PATCH nào được gọi khi browser chỉ preflight.

### 14.3. MockMvc test CORS rejection

```java
@Test
void preflightWrongOriginIsRejected() throws Exception {
    mockMvc.perform(options("/api/projects/p7")
            .header("Origin", "https://untrusted.example.test")
            .header("Access-Control-Request-Method", "PATCH")
            .header("Access-Control-Request-Headers", "authorization"))
        .andExpect(status().isForbidden());
}
```

Status 403 là kết quả thường gặp của Spring `DefaultCorsProcessor` khi CORS policy từ chối request, nhưng có thể khác nếu proxy/custom processor xử lý. Mục tiêu test là origin lạ **không được nhận allow-origin hợp lệ cho chính nó**, và request không đến handler nhạy cảm.

### 14.4. MockMvc test actual request thiếu quyền

```java
@Test
@WithMockUser(authorities = "project:read")
void preflightAllowedButActualPatchDenied() throws Exception {
    mockMvc.perform(patch("/api/projects/p7")
            .header("Origin", "https://app.example.test")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"name\":\"Not Allowed\"}")
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

Đoạn này giả định dự án dùng test mock user có `project:read`, không có `project:edit` và nếu CSRF đang bật thì `with(csrf())` giúp tránh nhận 403 chỉ vì thiếu token. Đây là **fragment trong project**, không phải Java độc lập. Nếu ứng dụng sản xuất dùng Bearer-only và cấu hình CSRF khác, test cần phản ánh security chain đó.

### 14.5. Test actual request đủ quyền và object policy

```java
@Test
@WithMockUser(authorities = "project:edit")
void editorCanReachPatchHandler() throws Exception {
    mockMvc.perform(patch("/api/projects/p7")
            .header("Origin", "https://app.example.test")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"name\":\"Edited\"}")
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Test `200` chỉ chính xác nếu controller PATCH tồn tại, fixture `p7` hợp lệ, policy tenant/owner/state cho phép và handler thực tế trả 200. Nếu controller trả 204, dùng `isNoContent()`; nếu service còn quy tắc từ chối, tạo fixture cho phép trước khi assert. Một bài test security tốt tách **đủ authority** khỏi **tất cả điều kiện nghiệp vụ thành công**.

### 14.6. Kiểm thử bằng curl: phân biệt hai request

Preflight mô phỏng:

```bash
curl -i -X OPTIONS "https://api.example.test/api/projects/p7" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization, content-type"
```

Actual request:

```bash
curl -i -X PATCH "https://api.example.test/api/projects/p7" \
  -H "Origin: https://app.example.test" \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  --data '{"name":"Updated"}'
```

**Hạn chế:** `curl` không phải browser CORS enforcement, nên có thể gửi actual request dù preflight fail hoặc không gửi preflight; vì thế dùng curl để **xem HTTP headers và server behavior**, không coi nó chứng minh browser sẽ chấp nhận. Không để token thật trong shell history/log; sử dụng môi trường test hoặc placeholder thay vì thông tin nhạy cảm.

## 15. Chẩn đoán lỗi CORS và 403 chính xác

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| OPTIONS trả 401/redirect login | Preflight bị authentication xử lý trước CORS | Kiểm tra `http.cors(...)`, `CorsFilter`, chain selection |
| OPTIONS trả 403 "Invalid CORS request" | Origin/method/header không thuộc allowlist | So request headers với CorsConfiguration |
| OPTIONS trả 200 nhưng browser vẫn báo CORS | Thiếu `Access-Control-Allow-Origin`/Methods/Headers hoặc credentials không khớp | Xem response headers của OPTIONS |
| OPTIONS thành công, PATCH trả 403 | User thiếu permission hoặc CSRF/object policy | Kiểm tra actual request; **không nới CORS bừa** |
| OPTIONS thành công, PATCH trả 401 | Không có token/cookie hoặc authentication không hợp lệ | Kiểm tra actual Authorization/session |
| Same-origin request tốt, cross-origin fail | Origin/port/scheme khác hoặc browser CORS enforcement | So origin chính xác và CORS headers |
| GET không preflight nhưng browser không đọc response | Response CORS headers thiếu/sai | Xem actual GET response |
| Có Bearer token ở JS nhưng preflight 401 | Backend sai khi đòi token ở preflight | Preflight chỉ nêu tên header authorization |
| Dùng `allowCredentials(true)` với `allowedOrigins("*")` lỗi | Cấu hình không hợp lệ cho credentials | Chọn exact origins/pattern được kiểm soát |
| Cookie phiên không gửi ở actual | `credentials`, cookie attributes, SameSite, third-party policies | Xem request cookies và browser policy |
| CSRF từ chối POST dù CORS đúng | Thiếu CSRF token với session/cookie | Kiểm tra repository, header, test `with(csrf())` |
| API admin được gọi từ origin lạ bằng curl | CORS không chặn nonbrowser client | Luôn kiểm tra authentication/authorization |
| Chỉ một số URL có CORS | `registerCorsConfiguration` path mapping hoặc nhiều chain khác nhau | Kiểm tra matched path và chain |
| Lỗi khi qua proxy nhưng localhost tốt | Gateway xử lý/rewrite OPTIONS hoặc CORS headers | Kiểm tra tại từng hop |
| Preflight đôi khi không xuất hiện | Browser cache `Access-Control-Max-Age` hoặc request không cần preflight | Kiểm tra DevTools và cache behavior |
| Một origin được phép nhưng API khác không | Per-handler `@CrossOrigin` và global rules kết hợp khác | Rà soát MVC/bean/CorsFilter config |

### Quy trình gỡ lỗi năm bước

1. **Xác nhận URL/origin:** gồm scheme, host, port; xem chính xác `Origin` và request-target.
2. **Tách preflight:** tìm request `OPTIONS` có `Access-Control-Request-Method`. Nếu không có, đừng tự giả định browser buộc phải gửi.
3. **Đọc CORS response:** status cùng `Access-Control-Allow-Origin`, Methods, Headers, Credentials, Vary.
4. **Đọc actual request:** bearer/cookie có gửi không; `hasRole`/`hasAuthority`/`@PreAuthorize`/CSRF/object policy chặn ở đâu?
5. **Xác minh tầng triển khai:** gateway trước backend, filter chain nào được chọn, CORS source nào có hiệu lực, có cache preflight hay không.

Không giải lỗi bằng việc thêm `permitAll("/api/**")` hoặc tự tắt toàn bộ `csrf`/`cors`. Những cách đó có thể làm mất hàng rào bảo mật mà vẫn không chữa đúng nguyên nhân.

## 16. Những lỗi thiết kế phổ biến và cách sửa

### 16.1. Sai lầm: "Preflight OPTIONS cần cùng role với PATCH"

Không đúng. Preflight không mang credential user, nên thường không thể và không nên kiểm tra role `EDITOR` tại đây. Nó chỉ hỏi **browser có được phép gửi PATCH với các header dự định từ origin này không**. Bảo vệ `project:edit` phải nằm ở actual PATCH.

### 16.2. Sai lầm: "Mở OPTIONS là đã cho CORS"

Không đúng. CORS cần response headers. Với Spring Security hiện đại, tích hợp `http.cors(...)` và nguồn cấu hình phù hợp tốt hơn rule `OPTIONS /** permitAll` tổng quát.

### 16.3. Sai lầm: "CORS là đủ để bảo vệ API"

Không đúng. CORS chủ yếu hạn chế hành vi JavaScript trong browser. Nonbrowser clients không bị ràng buộc như vậy. Kẻ tấn công có thể gửi request có `Origin` giả. Authentication/authorization phải kiểm tra ở server.

### 16.4. Sai lầm: "CORS được phép thì frontend có thể đọc mọi dữ liệu"

Không đúng. CORS chỉ cho browser sử dụng response cross-origin; domain policy vẫn kiểm tra người dùng cụ thể, tenant, owner, trạng thái, permission. Một request thực có thể bị từ chối dù preflight đã cho.

### 16.5. Sai lầm: "Sự cố 403 nào cũng là lỗi CORS"

Không đúng. `403` có thể do CORS processor, CSRF, quyền HTTP, method security hoặc object policy. Xem request nào trả lỗi và filter nào xử lý.

### 16.6. Sai lầm: "Chỉ cần set allowedOrigins trong controller"

Chưa chắc. Khi Spring Security nằm trước MVC, preflight có thể bị filter chặn trước khi đến controller. Bảo đảm CORS được xử lý sớm qua tích hợp Spring Security hoặc filter được sắp xếp đúng thứ tự.

### 16.7. Sai lầm: "Origin là danh tính của người dùng"

Không đúng. Origin mô tả nguồn trang/script theo chính sách browser, không phải user identity. Không gán quyền admin chỉ vì header Origin trùng frontend.

### 16.8. Sai lầm: "allowedMethods(GET, POST, PATCH) cấp quyền POST"

Không đúng. Nó chỉ giới hạn **actual methods ở tầng CORS**. Nếu `authorizeHttpRequests` có fallback deny cho POST, actual POST vẫn không được phép.

### 16.9. Sai lầm: "Preflight cache làm quyền user cũng được cache"

Không đúng. Cache preflight không thay thế lần kiểm tra authentication/authorization ở actual request. Nếu user mất role, actual PATCH tiếp theo vẫn cần bị từ chối.

### 16.10. Sai lầm: "Chỉ cần một chain có CORS cho tất cả requests"

Không đúng trong ứng dụng có nhiều `SecurityFilterChain`. Mỗi request được một chain phù hợp xử lý; OPTIONS và actual phải được route đúng; các URL ngoài chain phải có fallback/biện pháp bảo vệ.

## 17. Quy trình triển khai CORS và authorization bền vững

**Bước 1 — Liệt kê origins chính thức.** Gồm scheme, hostname, port của frontend ở dev/staging/production. Không nhập chung `http://localhost:3000` với `http://localhost:5173` như cùng origin.

**Bước 2 — Liệt kê actual requests.** Với từng route: HTTP method, request headers, có dùng cookie hoặc Bearer token, có CSRF, ai được phép gọi. Đây là nguồn xác định allowed methods/headers và security permission.

**Bước 3 — Chọn chủ sở hữu CORS.** CORS có thể xử lý trong Spring MVC/Spring Security hoặc gateway. Tránh hai tầng cùng sinh headers mâu thuẫn; nếu gateway xử lý preflight, backend vẫn phải xác thực/phân quyền actual request.

**Bước 4 — Cấu hình CORS rõ ràng.** Dùng `CorsConfigurationSource`/`CorsFilter` hoặc MVC CORS kết hợp `http.cors(...)`, exact origins nếu có credentials, allowed methods/headers đủ dùng, max age hợp lý.

**Bước 5 — Giữ authorization của actual request chặt chẽ.** Tách `project:read` và `project:edit`, bảo vệ `/api/admin/**` bằng role, dùng fallback deny; service kiểm tra tenant/owner/resource.

**Bước 6 — Xác định cookie/CSRF strategy.** Nếu dùng session: xử lý `credentials: "include"`, cookie flags và CSRF token. Nếu dùng Bearer-only, cần chính sách riêng cho token và đánh giá CSRF theo threat model.

**Bước 7 — Test preflight không có user.** OPTIONS hợp lệ trả CORS headers đúng; origin/method/header sai bị từ chối; không đòi role user ở OPTIONS.

**Bước 8 — Test actual requests đủ và thiếu quyền.** Có `project:edit` mới được PATCH ở tầng chức năng; thiếu quyền hoặc khác tenant phải bị chặn. Không lấy preflight pass để suy actual pass.

**Bước 9 — Test browser và gateway.** Dùng DevTools xem request/response; thử `curl` để đọc headers; xác minh CORS qua cùng proxy và context path production.

**Bước 10 — Review thay đổi policy.** Khi thêm method, header, frontend origin hoặc SecurityFilterChain, cập nhật CORS allowlist, authorization, CSRF assumptions và integration tests cùng lúc.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Preflight là `OPTIONS` nhưng actual request là `PATCH`. Rule `hasAuthority("project:edit")` nên áp dụng ở đâu?

**Đáp án:** Ở request PATCH thực (và service nghiệp vụ). Preflight chỉ được CORS processor đánh giá origin/method/headers, không mang token user để xác nhận `project:edit`.

**Câu 2.** `Access-Control-Request-Headers: authorization` trong preflight có nghĩa trình duyệt đã gửi access token chưa?

**Đáp án:** Không. Nó chỉ báo request thực **dự định** mang header Authorization. Token được gửi ở actual request khi frontend và browser thực hiện đúng cấu hình.

**Câu 3.** Thêm `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` có tự sửa mọi lỗi CORS không?

**Đáp án:** Không. Browser vẫn cần `Access-Control-Allow-Origin`/Methods/Headers và credentials policy phù hợp. Nên dùng CORS integration sớm, không chỉ mở authorization cho OPTIONS.

**Câu 4.** Preflight thành công, PATCH trả 403. Cần sửa allowedOrigins ngay không?

**Đáp án:** Không vội. Preflight đã được chấp nhận; kiểm tra authentication, `project:edit`, CSRF, tenant/owner và service policy của actual request.

**Câu 5.** Với `allowCredentials(true)`, có nên trả `Access-Control-Allow-Origin: *` không?

**Đáp án:** Không. Credentialed cross-origin requests cần một origin cụ thể được cho phép theo contract browser/Spring. Dùng exact allowlist hoặc pattern được kiểm soát cẩn thận.

**Câu 6.** `curl` gọi trực tiếp `PATCH /api/admin/data` thành công dù website lạ bị lỗi CORS. Kết luận nào đúng?

**Đáp án:** CORS không ràng buộc curl như browser. Nếu PATCH thành công khi user không đủ quyền, đó là lỗi server-side authorization; cần sửa role/permission/object policy, không dựa vào CORS.

**Câu 7.** Một GET cross-origin không preflight có nghĩa là GET không chịu CORS?

**Đáp án:** Không. Browser vẫn kiểm tra CORS headers của actual response. "Không có preflight" chỉ có nghĩa request đủ điều kiện gửi trực tiếp.

**Câu 8.** Người dùng đã đăng nhập ở `api.example.test` nhưng OPTIONS không có `JSESSIONID`. Có phải browser bị lỗi?

**Đáp án:** Không. CORS preflight thường không mang cookie user. Spring Security cần xử lý preflight mà không đòi login; cookie/session được kiểm tra trên actual request nếu cơ chế credential cho phép.

**Câu 9.** Cho phép `X-CSRF-TOKEN` trong `allowedHeaders` có nghĩa CSRF đã được xác thực chưa?

**Đáp án:** Chưa. Nó chỉ cho phép browser gửi header đó. `CsrfFilter`/repository phải kiểm tra giá trị token ở actual request theo chính sách của ứng dụng.

**Câu 10.** Browser không gửi OPTIONS lần thứ hai nhưng PATCH vẫn bị từ chối vì user mất quyền. Vì sao hợp lý?

**Đáp án:** Browser có thể cache preflight theo `Access-Control-Max-Age`, còn authorization của actual PATCH vẫn phải kiểm tra quyền hiện tại. CORS cache không phải permission cache.

**Câu 11.** Có nhiều `SecurityFilterChain`; một chain đã bật `cors()`. Vì sao preflight ở URL khác vẫn lỗi?

**Đáp án:** Vì chain được chọn theo `securityMatcher`/`@Order`. CORS của chain này không mặc nhiên áp dụng cho chain khác hoặc URL nằm ngoài phạm vi. Cần cấu hình và test chain thực tế.

**Câu 12.** `allowedMethods(List.of("GET", "POST", "PATCH"))` cho phép một user thiếu role gửi POST admin tới server không?

**Đáp án:** CORS có thể chấp nhận điều kiện cross-origin cho POST, nhưng HTTP authorization vẫn phải đánh giá role/permission admin; thiếu quyền thì request bị từ chối. Được phép dùng method theo CORS không bằng được phép thực hiện hành động.

**Kết luận:** **Preflight là cuộc thương lượng CORS của trình duyệt, không phải yêu cầu quyền nghiệp vụ.** Xử lý CORS sớm để OPTIONS hợp lệ không bị chặn do thiếu cookie/token; giữ role, authority, CSRF và quyền trên đối tượng cho request thực. Khi debugging, luôn tách origin/method/header policy khỏi authentication/authorization, rồi kiểm tra từng hop từ browser tới backend.

## Tài liệu tham khảo

- Spring Security — CORS, preflight trước authentication, CorsConfigurationSource, Spring MVC integration, multiple chains: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Authorize HttpServletRequests, hasAuthority, requestMatchers, denyAll: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Java configuration and multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Framework — CORS in Spring MVC, credentials and configuration: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Framework — CorsConfiguration Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- MDN — Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Preflight request: https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request
- MDN — CORS errors: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors
- MDN — Fetch credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
