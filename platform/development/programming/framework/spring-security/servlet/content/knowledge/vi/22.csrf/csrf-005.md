# CookieCsrfTokenRepository và việc gửi lại CSRF token qua header

**Phạm vi:** Spring Security cho ứng dụng **Servlet/Spring MVC** (Spring Security 6.x, Java 17+), đặc biệt là frontend JavaScript/SPA giao tiếp với backend bằng cookie phiên. Bài này tập trung vào cách cấp token bằng `CookieCsrfTokenRepository`, đọc cookie và gửi lại token trong HTTP header; WebFlux dùng cơ chế và API khác.

## 1. Vì sao cần gửi token qua header?

Với ứng dụng đăng nhập bằng session, trình duyệt tự đính kèm cookie phiên (ví dụ `JSESSIONID`) vào request cùng site, và trong một số trường hợp cả request được khởi tạo từ site khác. Kẻ tấn công có thể lợi dụng hành vi tự gửi cookie để khiến trình duyệt nạn nhân thực hiện hành động thay đổi trạng thái như POST chuyển tiền hoặc DELETE dữ liệu. Đó là **Cross-Site Request Forgery (CSRF)**.

CSRF protection yêu cầu request thay đổi trạng thái mang thêm một giá trị mà trang của kẻ tấn công không thể tùy ý lấy được. Trong Spring Security Servlet, `CsrfFilter` tìm token đã lưu bằng `CsrfTokenRepository` và so sánh với token phía client gửi lên. Thiếu hoặc sai token thường dẫn tới **HTTP 403** trước khi request tới controller.

- Cookie xác thực phiên chứng minh **trình duyệt đang có phiên đăng nhập**; nó không tự chứng minh người dùng chủ động tạo request.
- CSRF token là bằng chứng bổ sung cho request thay đổi trạng thái. Header `X-XSRF-TOKEN` phải chứa **giá trị token**, không phải tên cookie và cũng không phải cookie phiên.
- CSRF protection **không thay thế xác thực, phân quyền, chống XSS hoặc kiểm tra nghiệp vụ**. Nếu ứng dụng có XSS, script độc hại trong cùng origin có thể đọc token khi cookie không `HttpOnly`.

Spring Security mặc định kiểm tra CSRF với các phương thức **không an toàn** (điển hình `POST`, `PUT`, `PATCH`, `DELETE`); `GET`, `HEAD`, `OPTIONS`, `TRACE` được coi là an toàn theo mặc định. Endpoint GET phải thực sự không đổi trạng thái.

## 2. CookieCsrfTokenRepository lưu gì, client gửi gì?

`CookieCsrfTokenRepository` lưu giá trị token trong cookie của trình duyệt; mỗi request cần bảo vệ phải gửi **cùng giá trị đó** qua header hoặc tham số form để backend đối chiếu.

| Thành phần | Mặc định thường dùng | Vai trò |
| --- | --- | --- |
| Cookie CSRF | `XSRF-TOKEN` | Nơi lưu token để client nhận sau response. |
| Header CSRF | `X-XSRF-TOKEN` | Nơi JavaScript gửi lại token khi gọi POST/PUT/PATCH/DELETE. |
| Tham số form | `_csrf` | Cách gửi token cho HTML form truyền thống. |
| Cookie phiên | `JSESSIONID` (nếu dùng session) | Xác thực phiên; **khác** CSRF token. |

Tên cookie, header và parameter có thể tùy chỉnh trên repository; frontend phải dùng chính xác các tên đã thống nhất. `withHttpOnlyFalse()` tạo repository cho phép JavaScript đọc cookie `XSRF-TOKEN` bằng `document.cookie`. Khi backend render form và tự chèn CSRF token vào HTML, thường không cần bật đọc cookie bằng JavaScript.

**Luồng cùng origin:**

1. Client gọi `GET /api/csrf`. Bộ xử lý token yêu cầu Spring Security tạo/đọc token, rồi phản hồi có `Set-Cookie: XSRF-TOKEN=...` nếu cần.
2. Trình duyệt lưu cookie trong phạm vi domain/path thích hợp. JavaScript cùng origin đọc `XSRF-TOKEN`; script không thể đọc cookie có cờ `HttpOnly`.
3. Khi gọi `POST /api/notes`, client gửi cookie phiên theo cơ chế cookie bình thường, đồng thời đặt `X-XSRF-TOKEN: <giá trị đọc từ XSRF-TOKEN>`.
4. `CsrfFilter` lấy giá trị token do repository quản lý, đọc token từ request qua `CsrfTokenRequestHandler`, so sánh và chỉ cho request đi tiếp khi hợp lệ.

Ví dụ HTTP **minh họa** (giá trị token chỉ là giả định):

```http
GET /api/csrf HTTP/1.1
Host: app.example.com

HTTP/1.1 204 No Content
Set-Cookie: XSRF-TOKEN=token-123; Path=/

POST /api/notes HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=session-abc; XSRF-TOKEN=token-123
X-XSRF-TOKEN: token-123
Content-Type: application/json

{"text":"hello"}
```

Header được thêm **tường minh bởi code frontend** (hoặc cơ chế XSRF của framework); trình duyệt không tự lấy token từ cookie `XSRF-TOKEN` rồi chuyển thành `X-XSRF-TOKEN`.

## 3. Điểm dễ sai ở Spring Security 6: deferred token và BREACH

Chỉ cấu hình `csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())` có thể **chưa đủ cho SPA** trong Spring Security 6:

- **Deferred loading:** token được tải/tạo khi thực sự được truy cập. Một request GET không đụng đến token có thể không tạo cookie như frontend mong đợi. SPA nên có endpoint bootstrap và request handler chủ động truy cập token.
- **BREACH protection:** handler mặc định `XorCsrfTokenRequestAttributeHandler` có thể phơi bày một **giá trị token đã được mask** cho HTML/thuộc tính request. Chuỗi mask đó khác với token gốc được lưu trong cookie `XSRF-TOKEN`. Nếu dùng handler mặc định để giải mã mọi đầu vào, header chứa giá trị **thô** đọc từ cookie có thể bị từ chối.
- **Cách xử lý SPA:** khi token đến từ header `X-XSRF-TOKEN`, dùng `CsrfTokenRequestAttributeHandler` để đọc giá trị thô; khi token đến từ parameter/form, giữ `XorCsrfTokenRequestAttributeHandler` để xử lý biểu diễn đã mask. Khi xử lý request, chủ động gọi `csrfToken.get()` để kích hoạt cơ chế tạo/ghi cookie.

Không được tùy tiện bỏ BREACH protection hay nghĩ rằng token trong cookie luôn bằng chuỗi `_csrf.token` render ra HTML. Hai đường sử dụng có thể có biểu diễn khác nhau.

## 4. Ví dụ cấu hình Servlet với Spring Security 6

Các file sau thuộc **một ứng dụng Spring Boot 3.x Servlet** dùng `spring-boot-starter-web` và `spring-boot-starter-security`. Chúng không phải các chương trình `javac` độc lập vì cần thư viện Spring trên classpath. Đặt chúng chung package `com.example.csrf` và chạy như ứng dụng Spring Boot; Java 17 trở lên đáp ứng cú pháp.

**`SpaCsrfTokenRequestHandler.java`** — xử lý token raw từ header và token mask từ form:

```java
package com.example.csrf;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.function.Supplier;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        // Cho HTML/form dùng token đã mask (BREACH protection).
        xor.handle(request, response, csrfToken);
        // Ép deferred token được nạp/tạo để có cookie cho SPA.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        CsrfTokenRequestHandler handler =
                StringUtils.hasText(header) ? plain : xor;
        return handler.resolveCsrfTokenValue(request, csrfToken);
    }
}
```

**`SecurityConfig.java`** — dùng cookie CSRF; cho phép gọi endpoint bootstrap khi chưa đăng nhập, còn API nghiệp vụ yêu cầu login:

```java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        CookieCsrfTokenRepository repository =
                CookieCsrfTokenRepository.withHttpOnlyFalse();

        http
            .csrf(csrf -> csrf
                .csrfTokenRepository(repository)
                .csrfTokenRequestHandler(
                    new SpaCsrfTokenRequestHandler()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

**`DemoController.java`** — endpoint GET không thay đổi trạng thái, POST trả dữ liệu minh họa:

```java
package com.example.csrf;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/csrf")
    public ResponseEntity<Void> csrf() {
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/notes")
    public Map<String, String> createNote(
            @RequestBody Map<String, String> body) {
        return Map.of("saved", body.getOrDefault("text", ""));
    }
}
```

**`DemoApplication.java`** — điểm khởi động Spring Boot:

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Với project Gradle đã cài `org.springframework.boot` và có hai starter trên, chạy `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`). Để có ví dụ project độc lập, file `build.gradle` tối thiểu có thể dùng:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Gradle wrapper (`gradlew`) phải có sẵn; nếu tạo project bằng Spring Initializr thì chọn Spring Web, Spring Security, Java 17+ và dùng wrapper được tạo. Trong ví dụ, Spring Security tạo tài khoản demo `user` với mật khẩu in ra log khởi động nếu chưa cấu hình tài khoản riêng. Login form mặc định ở `/login` đã tích hợp CSRF token cho form. **Không triển khai tài khoản demo mặc định ở production.**

## 5. JavaScript: đọc cookie và đặt đúng header

Ví dụ frontend **cùng origin** với backend (như `https://app.example.com` gọi `/api/...`):

```javascript
async function bootstrapCsrf() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Cannot initialize CSRF: " + response.status);
  }
}

function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const entry = document.cookie
    .split("; ")
    .find((part) => part.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}

async function createNote(text) {
  const token = readCookie("XSRF-TOKEN");
  if (!token) {
    throw new Error("XSRF-TOKEN missing; call bootstrapCsrf first");
  }

  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify({ text })
  });

  if (!response.ok) {
    throw new Error("Request failed: " + response.status);
  }
  return response.json();
}

// Gọi bootstrapCsrf() sau khi trang được tải và sau khi login;
// khi đã có phiên xác thực hợp lệ thì gọi createNote("hello").
```

Giải thích những phần quyết định:

- `bootstrapCsrf()` khiến server trả cookie token (nhờ `csrfToken.get()` trong handler); không lấy token từ body JSON hay response header tự chế.
- `readCookie("XSRF-TOKEN")` chỉ lấy được cookie có phạm vi domain/path phù hợp và `HttpOnly=false`. Nếu token chứa ký tự được percent-encode, `decodeURIComponent` khôi phục giá trị.
- `credentials: "same-origin"` bảo đảm cookie phiên và CSRF cookie được gửi trong request cùng origin. Token còn được chép vào **header riêng**, vì chỉ gửi cookie `XSRF-TOKEN` là chưa đủ.
- Header `Content-Type: application/json` chỉ mô tả body; bản thân nó không phải token. Backend lấy token từ `X-XSRF-TOKEN` thông qua handler.
- Sau login/logout, Spring Security có thể xóa token cũ để phòng session fixation/CSRF. Khi phiên thay đổi, hãy **gọi lại endpoint bootstrap** trước request thay đổi trạng thái; đừng giữ token trong biến/ứng dụng quá lâu.

Lưu ý: Nếu SPA ở origin khác (`app.example.com`) còn API ở `api.example.com`, JavaScript phía SPA **không thể đọc cookie host-only của API** bằng `document.cookie`. Đây là vấn đề khác với bật `credentials: "include"`: còn phải thiết kế cùng site/cùng origin hoặc BFF, phạm vi cookie, CORS chính xác và cách cấp token an toàn. Không mở `Access-Control-Allow-Origin: *` với credentials hoặc nới cookie domain tùy tiện.

## 6. Kiểm chứng trên trình duyệt và bằng HTTP client

1. Truy cập `GET /api/csrf`; quan sát trong DevTools **Network → Response Headers** (có `Set-Cookie` khi server cấp/đổi token) và **Application/Storage → Cookies** (tên `XSRF-TOKEN`). Lời gọi này thường cho **204 No Content** ở controller ví dụ; token nằm trong cookie, không nằm trong body.
2. Đăng nhập qua `/login` để có phiên hợp lệ; sau đăng nhập gọi `GET /api/csrf` lần nữa vì token có thể bị xóa khi xác thực thành công.
3. Gọi `POST /api/notes` với cookie phiên và header `X-XSRF-TOKEN` đúng: ví dụ trả **200 OK**, body `{"saved":"hello"}`. Kiểm tra trong tab Network rằng **Request Headers** có `X-XSRF-TOKEN` đúng giá trị cookie.
4. Thử request tương tự nhưng bỏ header hoặc đổi token: khi session vẫn hợp lệ, kỳ vọng **403 Forbidden**, không chạy controller. Gửi đúng token nhưng chưa đăng nhập thì vẫn có thể nhận **302 chuyển đến login** hoặc phản hồi từ cơ chế xác thực; CSRF và authentication là hai lớp kiểm tra khác nhau.
5. Thử `GET /api/csrf` nhiều lần: token có thể được tái sử dụng theo vòng đời repository; không giả định mỗi GET cấp token mới. Sau logout/login, kiểm tra và bootstrap lại.

Ví dụ lệnh kiểm tra bước đầu (chạy khi ứng dụng đang chạy local):

```bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
```

Kỳ vọng trong response có `HTTP/1.1 204` và, nếu vừa tạo token, có `Set-Cookie: XSRF-TOKEN=...`. Đây là output **theo trạng thái cookie và cấu hình server**, không phải chuỗi tĩnh. File `cookies.txt` chỉ chứa cookie thử nghiệm; không lưu hoặc chia sẻ cookie phiên/token thật.

## 7. Bảo mật và lỗi thường gặp

| Dấu hiệu | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `403` dù có cookie `XSRF-TOKEN` | Frontend không đặt header, đặt sai tên hoặc chỉ gửi cookie. | Gửi `X-XSRF-TOKEN` chứa **giá trị** cookie trên unsafe methods. |
| `403` khi header bằng đúng giá trị cookie trên Spring Security 6 | Handler XOR mặc định đợi biểu diễn mask, trong khi header từ cookie là raw. | Dùng handler SPA nêu trên; giữ XOR cho form, plain cho header. |
| Không thấy `XSRF-TOKEN` sau GET | Token còn deferred hoặc endpoint không kích hoạt token; có thể sai cookie path/domain. | Gọi bootstrap endpoint và kích hoạt `csrfToken.get()` trong handler; kiểm tra scope cookie. |
| JavaScript đọc token ra `null` | Cookie có `HttpOnly`, không cùng domain/path, hoặc browser chặn. | Chỉ với SPA cần đọc cookie: `withHttpOnlyFalse()`; rà scope và chính sách cookie. |
| Chạy sau login được một lúc rồi `403` | Token bị thay hoặc xóa sau xác thực, logout hoặc thay đổi phiên. | Lấy lại CSRF cookie sau chuyển trạng thái xác thực. |
| API từ origin khác lỗi | CORS/credentials, SameSite, Secure hoặc frontend không truy cập được cookie host-only. | Thiết kế chính sách cookie và CORS theo từng origin; ưu tiên same-origin/BFF. |
| POST bị `302` về `/login` hoặc `401` | Chưa có phiên xác thực phù hợp, dù CSRF token có thể hợp lệ. | Kiểm tra đăng nhập và session trước khi kết luận lỗi CSRF. |

**Những quy tắc không nên bỏ qua:**

- Dùng HTTPS ở production, cookie `Secure` phù hợp; cấu hình `SameSite` theo kiến trúc (thường `Lax` hoặc `Strict` khi khả thi). Có thể cấu hình cookie bằng `CookieCsrfTokenRepository#setCookieCustomizer` trong Spring Security 6.1+. `SameSite` hỗ trợ giảm rủi ro CSRF nhưng **không thay thế token**.
- Đặt path/domain cookie tối thiểu cần thiết. Tránh cho subdomain không đáng tin cậy đặt hoặc đọc cookie CSRF của ứng dụng; kiểm soát CORS và các origin được phép gửi credentials.
- `HttpOnly=false` là quyết định có chủ đích để SPA đọc token; đồng nghĩa script cùng origin (bao gồm XSS) có thể đọc nó. Giữ HTML escaping, CSP và phòng XSS; không log hoặc gắn token lên URL/query string.
- Nếu backend chỉ nhận Bearer token gửi **tường minh** qua `Authorization`, không có cookie/HTTP credentials tự đính kèm, mô hình nguy cơ CSRF có thể khác; đánh giá cơ chế xác thực thực tế trước khi thay đổi bộ lọc. **Không tắt CSRF chỉ để né lỗi 403** trong ứng dụng đăng nhập bằng cookie.
- Với form HTML truyền thống, Spring có thể dùng `_csrf` làm hidden input với token được mask; không ép form dùng cơ chế đọc cookie/header của SPA.

## 8. Ghi nhớ cơ chế

`CookieCsrfTokenRepository` cấp/lưu token ở cookie `XSRF-TOKEN`; với SPA đọc cookie bằng JavaScript, request thay đổi trạng thái phải gửi lại **token raw trong header `X-XSRF-TOKEN`** bên cạnh cookie phiên. Trong Spring Security 6, cần chú ý **deferred token** và **XOR/BREACH masking**: handler SPA phải kích hoạt cấp cookie và đọc header raw đúng cách. Khi token khớp, request mới vượt qua `CsrfFilter`; quyền truy cập endpoint vẫn được quyết định riêng bởi authentication và authorization.
