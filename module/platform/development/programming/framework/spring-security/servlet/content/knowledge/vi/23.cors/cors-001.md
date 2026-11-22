# Same-origin policy và phạm vi mà CORS giải quyết

> **Ngữ cảnh:** Ứng dụng Spring Security trên **Servlet stack**, Spring Boot 3.x / Spring Security 6.x, Java 17+. Bài học làm rõ cơ chế bảo vệ của trình duyệt, cách CORS cho phép chia sẻ phản hồi có kiểm soát, cách cấu hình CORS đúng vị trí trong Spring Security và những ranh giới bảo mật mà CORS không thay thế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định hai URL **cùng origin hay khác origin** dựa trên scheme, hostname và port; phân biệt `same-origin` với `same-site`.
- Giải thích vì sao JavaScript từ một origin thường **không được đọc** phản hồi của origin khác dù request có thể đã được gửi.
- Mô tả vai trò của các header `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, và hai bước **preflight** / **actual request**.
- Phân biệt CORS với xác thực, phân quyền, CSRF, việc chặn tải tài nguyên, và kiểm soát truy cập giữa server với server.
- Cấu hình CORS cho API Servlet có `SecurityFilterChain` để preflight được xử lý trước các filter xác thực, rồi kiểm chứng bằng trình duyệt và `curl`.

## 2. Same-origin policy (SOP): trình duyệt đang giới hạn điều gì?

**Origin** là bộ ba **(scheme, host, port)** của một URL. Path, query và fragment không góp phần xác định origin. Với các scheme HTTP(S), port mặc định được chuẩn hóa khi so sánh.

Giả sử trang đang chạy tại `http://localhost:5173/index.html`:

| URL đích | So với trang | Lý do |
|---|---|---|
| `http://localhost:5173/api/data` | Cùng origin | Cùng scheme, host và port |
| `http://localhost:5173/other/path?x=1` | Cùng origin | Path/query khác không đổi origin |
| `http://localhost:8080/api/data` | Khác origin | Khác port |
| `https://localhost:5173/api/data` | Khác origin | Khác scheme |
| `http://127.0.0.1:5173/api/data` | Khác origin | `127.0.0.1` và `localhost` là hai host khác nhau |
| `http://api.localhost:5173/api/data` | Khác origin | Subdomain khác |

**Same-origin policy** là nhóm quy tắc do **user agent (trình duyệt)** áp đặt để mã của một origin không tùy tiện truy cập dữ liệu, DOM và trạng thái của origin khác. Ví dụ, script tại `https://shop.example.test` không được tự đọc DOM bên trong iframe đăng nhập của `https://bank.example.test`. Với `fetch` / `XMLHttpRequest`, JavaScript không được xem response body/headers của một origin khác nếu không đáp ứng quy tắc CORS.

Điểm dễ nhầm: **SOP không có nghĩa mọi request cross-origin đều bị chặn gửi đi.** Trình duyệt đã cho phép nhiều hành vi tải/gửi xuyên origin từ lâu, chẳng hạn:

- `<img src="https://...">` tải ảnh từ origin khác; trang thường **không được đọc pixel** của ảnh cross-origin qua canvas nếu thiếu điều kiện CORS.
- `<script src="https://...">` dạng classic script có thể tải từ nguồn khác theo quy tắc tải script; JavaScript module và nhiều API hiện đại có yêu cầu CORS riêng.
- HTML form có thể gửi request sang origin khác. Đây là một lý do phải xem xét **CSRF**.
- `fetch` có thể phát sinh request tới origin khác. Nếu server không cho phép chia sẻ qua CORS, script bị ngăn đọc phản hồi; một số request đã có tác động trên server trước khi script nhận lỗi.

Cũng cần phân biệt **same-site** (khái niệm liên quan registrable domain và scheme, đặc biệt trong chính sách cookie `SameSite`) với **same-origin** (đòi hỏi cả port giống nhau). Hai ứng dụng `https://app.example.test` và `https://api.example.test` có thể cùng site nhưng vẫn **khác origin**, nên JavaScript đọc API phải xét CORS. Ngược lại, API cùng origin không cần mở CORS chỉ vì path khác.

## 3. CORS giải quyết điều gì, và không giải quyết điều gì?

**Cross-Origin Resource Sharing (CORS)** là cơ chế để **server đích công bố cho trình duyệt** những origin nào được phép truy cập phản hồi cross-origin bằng các API chịu kiểm tra CORS, ví dụ `fetch`. Server phát header CORS; **trình duyệt** kiểm tra và quyết định có cho JavaScript nhìn thấy phản hồi hay không.

Luồng đơn giản:

```text
Trang: http://localhost:5173         API: http://localhost:8080
          |                                     |
          | GET /api/public                     |
          | Origin: http://localhost:5173 ----> |
          |                                     |
          | <---- 200 OK                        |
          |       Access-Control-Allow-Origin: |
          |         http://localhost:5173       |
          |       {"message":"hello"}           |
          |                                     |
    Trình duyệt đối chiếu policy
          |
    Cho JavaScript đọc JSON
```

Nếu server không gửi header phù hợp, phía trình duyệt báo lỗi CORS / network-level failure cho mã `fetch`, dù server có thể đã xử lý và trả HTTP response. Không nên kết luận “request chưa đến server” chỉ dựa vào thông báo Console: cần phân biệt **request thực tế** với **preflight** (mục 4).

Ranh giới CORS:

| CORS có thể hỗ trợ | CORS không làm |
|---|---|
| Cho JavaScript từ origin được duyệt đọc response của API | Không xác thực người dùng hay chứng minh client đáng tin |
| Giới hạn origin, method và header có thể dùng trong request CORS | Không thay thế rule authorization của Spring Security |
| Kiểm tra trước một số request qua preflight | Không ngăn mọi form/simple request cross-origin được gửi |
| Giới hạn cách trình duyệt tiết lộ response cho JavaScript cross-origin | Không chặn `curl`, Postman, ứng dụng mobile hay server-to-server |
| Cho phép chia sẻ response có điều kiện kèm credentials | Không tự phòng chống CSRF hoặc XSS |
| Làm rõ contract giữa frontend và backend thuộc các origin khác nhau | Không cho JavaScript vượt SOP để đọc DOM của iframe cross-origin |

**CORS không phải cơ chế bảo vệ tài nguyên khỏi mọi client.** Một chương trình ngoài browser có thể đặt tùy ý header `Origin` hoặc không đặt header này. Vì thế, backend vẫn phải xác thực token/session, kiểm tra quyền trên từng endpoint và bảo vệ dữ liệu nhạy cảm. Chỉ whitelist một origin có frontend “chính thức” không biến API public thành API private.

## 4. Hai dạng request CORS: gửi thẳng và preflight

### 4.1. Request không cần preflight

Trình duyệt có thể gửi luôn **actual request** đối với các request thỏa điều kiện “CORS-safelisted”, điển hình `GET`, `HEAD` hoặc một số `POST` với header và `Content-Type` thuộc tập an toàn được chuẩn hóa (ví dụ `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`, cùng các giới hạn bổ sung của chuẩn). Response vẫn phải được duyệt theo CORS trước khi JavaScript đọc.

Ví dụ:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Accept: */*
```

Server trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: application/json

{"message":"hello"}
```

Response được hiển thị cho JavaScript bởi vì origin trả về khớp `Origin`. Không có preflight cũng **không có nghĩa** trình duyệt bỏ qua CORS.

### 4.2. Request cần preflight (OPTIONS)

Trình duyệt thường gửi preflight khi cross-origin request sử dụng method như `PUT`, `PATCH`, `DELETE`, header tự định nghĩa như `X-Client-Version`, `Authorization`, hoặc `Content-Type: application/json`. Request `OPTIONS` thông báo **method và header của actual request** để hỏi server có cho phép không:

```http
OPTIONS /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-client-version
```

Một phản hồi preflight hợp lệ có thể là:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: x-client-version
Access-Control-Max-Age: 600
```

Nếu được duyệt, browser tiếp tục gửi **actual GET** mang `X-Client-Version` và kiểm tra CORS trên **actual response**. Preflight không tự cấp quyền cho người dùng và không đảm bảo actual request sẽ thành công: API vẫn có thể trả 401, 403 hoặc lỗi nghiệp vụ.

Nếu preflight thất bại, browser **không gửi actual request tương ứng**. Trình duyệt thường không gửi cookie và thông tin xác thực trong preflight; vì thế backend không được yêu cầu preflight có phiên đăng nhập mới được trả header CORS. Cookie hoặc credentials cho **actual request** là vấn đề riêng ở mục 5.

Các trường hợp đáng nhớ:

- `GET` mang header `Authorization` thường cần preflight do header này không nằm trong nhóm safelisted.
- `POST` với `Content-Type: application/json` thường cần preflight; `POST` với `text/plain` có thể không cần, nhưng vẫn có thể gây thay đổi trạng thái server.
- `credentials: "include"` trong `fetch` **không tự nó** biến mọi request thành preflight. Yêu cầu preflight phụ thuộc method, header và các điều kiện của chuẩn CORS.
- Browser có thể cache **kết quả preflight** theo `Access-Control-Max-Age` trong giới hạn do browser quyết định. Cache preflight không đồng nghĩa cache dữ liệu API hoặc quyền truy cập.

## 5. Ý nghĩa các header CORS quan trọng

| Header | Chiều truyền | Ý nghĩa |
|---|---|---|
| `Origin` | Request | Origin nơi script/document phát sinh yêu cầu; do trình duyệt quản lý trong ngữ cảnh web |
| `Access-Control-Request-Method` | Preflight request | Method của actual request dự định gửi |
| `Access-Control-Request-Headers` | Preflight request | Những tên header không safelisted dự định gửi |
| `Access-Control-Allow-Origin` | Response | Origin được phép đọc response; hoặc `*` nếu hợp lệ cho trường hợp không dùng credentials |
| `Access-Control-Allow-Methods` | Preflight response | Các method được phép dùng |
| `Access-Control-Allow-Headers` | Preflight response | Những header mà actual request được phép mang |
| `Access-Control-Allow-Credentials` | Response | `true` nếu cho phép browser tiết lộ phản hồi cho request có credentials |
| `Access-Control-Expose-Headers` | Actual response | Những response header bổ sung JavaScript được phép đọc, ngoài nhóm safelisted |
| `Access-Control-Max-Age` | Preflight response | Gợi ý thời gian browser có thể cache kết quả preflight |
| `Vary: Origin` | Response/cache | Giúp cache phân biệt phiên bản response theo `Origin` khi giá trị allow-origin được thay đổi động |

**Không được dùng `Access-Control-Allow-Origin: *` cho request dùng credentials kiểu CORS.** Khi trình duyệt gửi request với `credentials: "include"`, response cần `Access-Control-Allow-Origin` khớp origin cụ thể cùng `Access-Control-Allow-Credentials: true`; wildcard không đáp ứng yêu cầu đó.

Ở client:

```javascript
fetch("https://api.example.test/me", {
  credentials: "include"
});
```

Cấu hình này yêu cầu browser đưa credentials phù hợp (như cookie) vào actual request nếu chính sách cookie cho phép. Nếu frontend và API khác site, cookie còn chịu `SameSite`, `Secure` và chính sách third-party cookies. **CORS cho phép chia sẻ phản hồi không tự buộc trình duyệt gửi cookie, không tạo session và không vượt qua chính sách cookie.**

Không lẫn `Access-Control-Allow-Headers` (cho phép **request headers**) với `Access-Control-Expose-Headers` (cho phép đọc thêm **response headers**). Header `Set-Cookie` là forbidden response-header name và không trở thành dữ liệu đọc được qua `fetch` chỉ vì thêm vào exposed headers.

Không phản chiếu vô điều kiện mọi giá trị `Origin` của client vào `Access-Control-Allow-Origin`. Cách làm đó gần tương đương mở quyền đọc response cho mọi website, rất nguy hiểm nếu API nhận credentials. Nếu cần nhiều origin, dùng allowlist rõ ràng, kiểm tra scheme, host và port. Tránh cho phép origin `null` một cách tùy tiện vì nhiều ngữ cảnh tài liệu có opaque origin biểu diễn bằng `null`.

## 6. Ví dụ chạy được: Spring Security Servlet và frontend khác port

Mục tiêu demo: trang `http://localhost:5173` có thể đọc API `http://localhost:8080/api/public`; một trang từ port khác không được đọc theo CORS. Endpoint `/api/private` vẫn đòi hỏi xác thực dù origin nằm trong allowlist.

### 6.1. Tạo ứng dụng Spring Boot

Dự án Gradle có Java 17+, hai starter Web MVC và Security. File `build.gradle` tối thiểu:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

Tệp `src/main/java/demo/cors/CorsLessonApplication.java`:

```java
package demo.cors;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CorsLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsLessonApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicData() {
        return Map.of("message", "hello");
    }

    @GetMapping("/api/private")
    public Map<String, String> privateData() {
        return Map.of("message", "private");
    }
}
```

Tệp `src/main/java/demo/cors/WebSecurityConfig.java`:

```java
package demo.cors;

import java.time.Duration;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class WebSecurityConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Phải khớp chính xác scheme, host và port của frontend.
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of("X-Client-Version"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(Duration.ofMinutes(10));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, CorsConfigurationSource corsSource)
            throws Exception {
        http
            // CORS xử lý trước phần xác thực/phân quyền của chain.
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // CSRF mặc định được giữ nguyên; demo chỉ dùng GET.
        return http.build();
    }
}
```

**Vì sao phải cấu hình `http.cors(...)`?** Spring Security có filter chain riêng. Preflight `OPTIONS` thường không mang cookie/credential đăng nhập; nếu bị xử lý như request API cần xác thực trước khi CORS chạy, nó có thể nhận 401/403 mà không có header CORS phù hợp. Khi tích hợp CORS với Spring Security, cơ chế CORS được đặt trước các bước xác thực của chain để xử lý preflight chính xác.

Giới hạn của demo được chọn có chủ đích:

- Chỉ cho phép origin `http://localhost:5173`, chỉ method `GET` và request header tùy biến `X-Client-Version`. `OPTIONS` dùng cho preflight có thể được xử lý dù không nằm trong danh sách method của **actual request**.
- `setAllowCredentials(false)` vì endpoint public không yêu cầu chia sẻ cookie cross-origin. Nếu muốn cookie/session, phải thiết kế riêng policy CORS, cookie, CSRF và đăng nhập; không tự bật `true` mà không xét các hệ quả đó.
- Spring Security yêu cầu đăng nhập cho `/api/private`, ngay cả khi origin nằm trong allowlist CORS. Việc một response được chia sẻ qua CORS **không** đồng nghĩa user đã được phân quyền.
- Demo không vô hiệu hóa CSRF. Khi thêm `POST`/`PUT` có cookie session, phải thực hiện đúng hợp đồng CSRF token hoặc cơ chế bảo vệ tương đương phù hợp.

Với dự án có Gradle Wrapper, chạy backend tại `localhost:8080`:

```bash
./gradlew bootRun
```

### 6.2. Tạo trang ở origin khác

Tạo file `frontend/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>CORS demo</title>
</head>
<body>
  <button id="load">Đọc API</button>
  <pre id="out"></pre>
  <script>
    document.getElementById("load").addEventListener("click", async () => {
      const out = document.getElementById("out");
      try {
        const response = await fetch("http://localhost:8080/api/public", {
          headers: { "X-Client-Version": "1" },
          credentials: "omit"
        });
        const body = await response.json();
        out.textContent = response.status + " " + JSON.stringify(body);
      } catch (error) {
        out.textContent = "Request/CORS error: " + error.name;
      }
    });
  </script>
</body>
</html>
```

Từ thư mục `frontend`, chạy một server tĩnh (ví dụ máy có Python 3):

```bash
python -m http.server 5173
```

Mở `http://localhost:5173` rồi nhấn **Đọc API**. Dòng hiển thị dự kiến:

```text
200 {"message":"hello"}
```

Do header `X-Client-Version` không nằm trong nhóm CORS-safelisted, ở tab Network của trình duyệt bạn thường thấy một request `OPTIONS` trước `GET` (trừ khi preflight đã được cache). Trình duyệt kiểm tra `Access-Control-Allow-Origin` trên response nên JavaScript được đọc JSON.

Để thấy trường hợp từ chối, phục vụ cùng trang qua `http://localhost:5500` rồi mở ở port đó. `Origin` sẽ là `http://localhost:5500`, không nằm trong allowlist: preflight bị từ chối, actual GET dùng header tùy biến sẽ không được gửi, và `fetch` không trả JSON cho JavaScript. Đừng dựa vào thông báo lỗi cụ thể; mỗi trình duyệt có cách trình bày khác nhau.

### 6.3. Kiểm tra handshake bằng curl

`curl` dùng để **quan sát HTTP headers** nhưng **không tự thực thi SOP/CORS** như trình duyệt.

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/public
```

Dự kiến status 200, body `{"message":"hello"}` và `Access-Control-Allow-Origin: http://localhost:5173`.

Gửi preflight thủ công:

```bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-client-version" \
  http://localhost:8080/api/public
```

Kỳ vọng response thành công có các header `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` phù hợp. Status và cách viết hoa header có thể khác tùy phiên bản/stack; điều kiện đúng là các giá trị CORS hợp lệ theo giao thức.

Thử thay `Origin` thành `http://localhost:5500`. Backend có thể trả phản hồi từ chối CORS, chẳng hạn 403; điểm mấu chốt là trình duyệt không cho script ở port 5500 đọc body theo cơ chế CORS. Với request thông thường không có header `Origin`, `curl` vẫn có thể gọi API mà không chịu ràng buộc cross-origin của trình duyệt.

Thử endpoint cần đăng nhập:

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private
```

Không cung cấp credentials thì Spring Security trả **401 Unauthorized** theo HTTP Basic. CORS có thể cho browser nhận biết status/response nếu origin được duyệt; nó **không** biến 401 thành 200.

## 7. Ranh giới với authentication, authorization, CSRF và XSS

### Authentication / authorization

Hãy tưởng tượng frontend ở `https://app.example.test` và API ở `https://api.example.test`:

1. CORS trả lời: “Script từ `app.example.test` có được **đọc** phản hồi của `api.example.test` không?”
2. Authentication trả lời: “Request này do người dùng hay client nào đã xác thực thực hiện?”
3. Authorization trả lời: “Danh tính đó có được phép xem dữ liệu, sửa tài nguyên, thực hiện thao tác này không?”

Ba câu hỏi **độc lập**. Một origin được CORS chấp thuận vẫn có thể nhận 401 hoặc 403. Ngược lại, thiếu header CORS có thể khiến browser chặn đọc một response mà backend đã xác thực và xử lý hợp lệ.

### CSRF

Một trang bên ngoài có thể khiến browser của nạn nhân gửi một số request tới hệ thống có cookie đăng nhập (ví dụ qua form). Một request gây thay đổi trạng thái có thể chạy trên server ngay cả khi browser không được đọc response. **Vì thế, whitelist CORS không tự ngăn CSRF.**

Với ứng dụng dùng session/cookie, cần CSRF token cho thao tác thay đổi trạng thái hoặc cơ chế phòng vệ tương đương được thiết kế đúng, cùng cấu hình cookie `SameSite` thích hợp. Không cấu hình `csrf.disable()` chỉ để “sửa CORS”, không coi việc một request không cần preflight là dấu hiệu an toàn.

### XSS

Nếu kẻ tấn công chèn được JavaScript vào chính origin được phép (XSS), mã đó có thể truy cập các API mà policy CORS của origin ấy cho phép, trong phạm vi credentials và quyền hiện có. **CORS không chặn XSS.** Cần chống injection, escape output, CSP và quản lý session/token đúng cách.

### DOM và iframe

CORS chủ yếu phục vụ truy cập tài nguyên qua các request chịu kiểm tra CORS; nó **không cho phép** script origin A thao tác DOM của iframe origin B. Để trao đổi dữ liệu giữa hai cửa sổ/iframe khác origin, dùng `window.postMessage` kèm kiểm tra chính xác `event.origin` và `targetOrigin`. Để giới hạn ai được nhúng trang, xem CSP `frame-ancestors` hoặc chính sách frame tương ứng; đó là vấn đề khác với CORS.

## 8. Áp dụng trong Spring Security Servlet thực tế

- **Xác định origin frontend chính xác** theo môi trường local, staging, production; khác scheme hoặc port là khác origin. Không dùng `*` chỉ để xóa lỗi Console, đặc biệt khi API có credential.
- **Đặt CORS trước authentication.** Với Spring Security 6, dùng `http.cors(...)` và một `CorsConfigurationSource` thích hợp (như ví dụ), hoặc tích hợp cấu hình Spring MVC nhất quán qua cơ chế CORS được Spring Security hỗ trợ. Nếu có nhiều `SecurityFilterChain`, kiểm tra chain khớp route thực tế.
- **Đặt phạm vi path, method, header tối thiểu.** Ví dụ `/api/**` cho frontend thay vì vô tình mở toàn ứng dụng. Không đồng thời cấu hình nhiều `CorsFilter`/`@CrossOrigin`/nguồn global tạo header mâu thuẫn.
- **Không dùng rule `OPTIONS permitAll` thay cho xử lý CORS.** Cho qua ủy quyền chỉ giải một phần: preflight còn cần header phản hồi đúng và allowlist origin/method/header hợp lệ.
- **Thiết kế riêng CORS khi dùng credentials.** Cần origin cụ thể, `allowCredentials(true)` nếu thực sự cần, cookie phù hợp và xác thực/phân quyền/CSRF đúng. Không gửi token hay mật khẩu trong query string để tránh preflight.
- **Nếu phản hồi thay đổi `Access-Control-Allow-Origin` theo `Origin`**, bảo đảm cơ chế cache/CDN tôn trọng `Vary: Origin`. Thư viện CORS thường tự phát header `Vary` phù hợp; vẫn nên kiểm tra trên môi trường thực.
- **Cần đọc response header tùy biến từ JavaScript?** Đặt `Access-Control-Expose-Headers` cho tên header thực sự cần. Chỉ thay đổi response headers được phép đọc; không ảnh hưởng request preflight.
- **Không tin `Origin` như danh tính đã xác thực.** Các non-browser client dễ tạo header tùy ý. Luôn giữ kiểm tra token/session và authorization tại API.
- **Kiểm tra proxy/gateway.** Nếu gateway đã xử lý CORS, định nghĩa rõ tầng sở hữu policy; kiểm tra duplicate ACAO, cache và header sau reverse proxy.

## 9. Ma trận kiểm thử và lỗi thường gặp

| Tình huống | Điều cần xác minh |
|---|---|
| Trang và API cùng origin | `fetch` đọc response không cần bật CORS cross-origin |
| `http://localhost:5173` gọi `GET /api/public` | Response 200 + allow-origin chính xác; JS đọc JSON |
| Trang `localhost:5173` gọi với `X-Client-Version` | Preflight OPTIONS hợp lệ, sau đó actual GET chạy |
| Trang `localhost:5500` gọi cùng API | Không được đọc; với custom header, preflight thất bại và actual request không chạy |
| `GET /api/private` không đăng nhập từ origin hợp lệ | Vẫn 401; CORS không thay authentication |
| Request với credential | Origin phải chính xác, allow-credentials khi cần; cookie và CSRF vẫn được kiểm soát |
| POST có side effect, đặc biệt dùng session cookie | Không ỷ lại CORS; CSRF và quyền nghiệp vụ phải được kiểm tra |
| `curl` từ bất kỳ host | Có thể gọi trực tiếp; CORS không phải firewall |
| Proxy/CDN cache response theo origin | Không dùng nhầm header allow-origin của origin khác |
| Trình duyệt báo lỗi CORS | Xem Network, xác định OPTIONS hay actual request, status và response headers thực tế |

**Sai lầm 1 — “CORS chặn request độc hại tới server.”** Nó chủ yếu là chính sách **trình duyệt kiểm soát việc chia sẻ response**. Với nhiều request, server đã nhận request trước khi JavaScript bị chặn đọc.

**Sai lầm 2 — “Cứ mở `Access-Control-Allow-Origin: *` là xong.”** Cách này mở quyền đọc phản hồi không credential cho mọi origin khi được áp dụng; và không dùng được cho response CORS kèm credentials.

**Sai lầm 3 — “Preflight OPTIONS là request API nghiệp vụ.”** OPTIONS hỏi quyền dùng method/header, thường không mang thông tin đăng nhập; đừng yêu cầu nó có phiên hợp lệ, và đừng nhầm kết quả preflight với quyền thực hiện nghiệp vụ.

**Sai lầm 4 — “Spring MVC `@CrossOrigin` đã đủ trong mọi trường hợp.”** Security filter chain có thể trả 401/403 trước controller, nên phải xác nhận CORS được tích hợp đúng với Spring Security và đúng chain.

**Sai lầm 5 — “Bật CORS là cho phép truy cập tài khoản.”** CORS, authentication và authorization trả lời những câu hỏi khác nhau; một client được phép đọc vẫn phải có quyền cho từng tài nguyên.

**Sai lầm 6 — “Không cần CSRF vì browser không cho đọc response.”** Thao tác thay đổi trạng thái có thể đã thực hiện dù response không đọc được. CSRF và chính sách cookie vẫn cần được thiết kế đúng.

## 10. Ghi nhớ

- **SOP** bảo vệ ranh giới origin trong trình duyệt; origin được xác định theo `scheme + host + port`.
- **CORS** là sự cho phép có điều kiện của **server đích** để trình duyệt tiết lộ response cho JavaScript cross-origin.
- **Preflight** là bước kiểm tra trước đối với một số method/header; không phải tất cả request cross-origin đều preflight, và actual response vẫn bị kiểm tra.
- **Spring Security Servlet** cần xử lý CORS sớm trong filter chain để OPTIONS không bị từ chối sai vì thiếu credential.
- **CORS không thay thế authentication, authorization, CSRF, XSS protection hay API access control**. Hãy xác minh cả policy trình duyệt và bảo vệ thực sự trên server.