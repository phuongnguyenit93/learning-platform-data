# Chẩn đoán CORS: preflight bị từ chối, thiếu header và cấu hình lặp ở proxy — Spring Security Servlet

## 1. Hiểu vấn đề cần chẩn đoán

Khi trình duyệt báo lỗi **Cross-Origin Resource Sharing (CORS)**, nguyên nhân có thể nằm ở nhiều lớp: request **OPTIONS preflight** bị Spring Security hoặc proxy trả 401/403, phản hồi preflight/actual request thiếu header cần thiết, origin không khớp, hoặc nhiều tầng cùng thêm `Access-Control-Allow-Origin`. Chỉ nhìn thông báo trong Console rồi thêm `Access-Control-Allow-Origin: *` thường che khuất nguyên nhân và có thể tạo lỗi mới.

Bài này tập trung vào ứng dụng **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**, có thể chạy sau Nginx/Ingress/CDN. Mục tiêu là xác định request nào thất bại, response được tạo ở tầng nào, header nào thực sự sai và cách sửa đủ hẹp để không ảnh hưởng authentication, authorization hoặc CSRF.

Một **origin** được xác định bởi *scheme + hostname + port*, ví dụ `http://localhost:5173` khác `http://localhost:8080` dù cùng máy. Path không thuộc origin. CORS là chính sách mà **trình duyệt** dùng để cho phép JavaScript từ origin A đọc phản hồi từ origin B; nó **không** phải cơ chế xác thực/phân quyền của API. `curl` không tự chặn response theo CORS, nhưng có ích để kiểm tra HTTP status/header.

## 2. Preflight là gì, điều kiện nào khiến browser gửi OPTIONS?

Trước một số request cross-origin không thuộc nhóm CORS-safelisted, browser gửi một request **OPTIONS** để hỏi server có chấp nhận method và header dự kiến hay không. Những tác nhân thường gây preflight:

- Method `PUT`, `PATCH`, `DELETE`.
- Header do JavaScript thêm như `Authorization`, `X-Tenant`, `X-Request-Id`.
- `POST` có `Content-Type: application/json` (không thuộc nhóm Content-Type safelisted).

Một GET cross-origin thông thường không có custom header có thể **không cần preflight** nhưng actual response vẫn phải đáp ứng CORS. Bởi vậy, không thấy OPTIONS **không đồng nghĩa** CORS hoạt động tốt.

Ví dụ frontend `http://localhost:5173` dự định gọi GET `http://localhost:8080/api/hello` với header Authorization. Browser có thể gửi:

```http
OPTIONS /api/hello HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Đây là request **xin phép**. `Access-Control-Request-Headers: authorization` báo request thật sẽ mang header `Authorization`, nhưng OPTIONS **không chứa giá trị Authorization của người dùng**. Browser thông thường không gắn cookie/credential vào preflight; do đó, bắt OPTIONS phải xác thực như actual request rất dễ gây 401.

Một phản hồi preflight hợp lệ có thể có dạng:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Status **200 hoặc 204** có thể hợp lệ. Đây là ví dụ định dạng, không phải output cố định của mọi Spring/proxy. `Vary` có thể thành nhiều dòng hoặc một dòng liệt kê tên header; thứ tự header không quyết định tính đúng đắn.

Nếu preflight bị từ chối, **actual request thường không được browser gửi**. Nếu OPTIONS qua được nhưng actual GET/POST trả 401/403/500, điều đó phải được điều tra riêng.

### 2.1. Bảng đọc header theo đúng vai trò

| Header | Trong request/response nào? | Ý nghĩa và lỗi hay gặp |
| --- | --- | --- |
| `Origin` | Browser request | Origin frontend; phải nằm trong allowed origins |
| `Access-Control-Request-Method` | OPTIONS request | HTTP method browser muốn gửi ở request thật |
| `Access-Control-Request-Headers` | OPTIONS request | Các tên request header cần được cho phép, ví dụ `authorization,content-type` |
| `Access-Control-Allow-Origin` | Response preflight và actual | **Một** origin được phép hoặc `*` khi phù hợp; không nhận danh sách origin cách dấu phẩy |
| `Access-Control-Allow-Methods` | Preflight response | Các method được phép; không cần thêm OPTIONS chỉ vì request kiểm tra là OPTIONS |
| `Access-Control-Allow-Headers` | Preflight response | Những **request header** browser được phép gửi |
| `Access-Control-Allow-Credentials` | CORS response | Phải là `true` khi cho phép browser đọc response của request có credentials |
| `Access-Control-Expose-Headers` | Actual response | Những **response header** bổ sung JavaScript được phép đọc; không thay cho Allow-Headers |
| `Access-Control-Max-Age` | Preflight response | Gợi ý browser cache preflight; giới hạn do browser quyết định |
| `Vary` | Response/cache | Ngăn cache dùng kết quả của origin/method/header này cho kết quả khác |

**Phân biệt rõ:** `Access-Control-Allow-Headers` xử lý `Authorization` hay `Content-Type` được **gửi lên**; `Access-Control-Expose-Headers` quyết định client script có đọc được response header như `X-Request-Id` hay không.

## 3. Quy trình chẩn đoán ở DevTools

Mở Network, chọn **All**, bật Preserve log nếu có điều hướng. Ghi lại frontend origin, URL API cuối cùng, method request thật, header thực sự dự định gửi, trạng thái OPTIONS và actual request. Dựa vào Network entry chứ không chỉ đọc Console vì trình duyệt có thể ẩn nội dung phản hồi vi phạm CORS.

### Trường hợp A — OPTIONS trả 401

Tìm `WWW-Authenticate` hoặc redirect về login. Rất thường gặp khi Spring Security authentication chạy **trước** CORS processing, hoặc proxy/gateway bắt mọi request `/api/**` đều phải mang credential. Preflight thường không mang cookie/Authorization; nó phải được đánh giá theo **origin + method + requested headers**, còn authentication áp cho request thật.

Cách xử lý ưu tiên ở Spring Security Servlet là tích hợp CORS xử lý trước authentication bằng `http.cors(Customizer.withDefaults())` và một `CorsConfigurationSource` thích hợp. Đừng mở `permitAll()` cho toàn bộ API để che 401 của OPTIONS.

### Trường hợp B — OPTIONS trả 403

Phân biệt **CORS policy từ chối** với **WAF/proxy hoặc security rule từ chối**. Spring có thể trả 403 với nội dung tương tự `Invalid CORS request` khi origin, method hoặc requested header không được phép. Kiểm tra:

1. `Origin` có đúng cả scheme/host/port với whitelist?
2. `Access-Control-Request-Method` có thuộc allowed methods?
3. Tất cả tên trong `Access-Control-Request-Headers` có nằm trong allowed headers?
4. URL sau reverse proxy rewrite có đúng path gắn CORS mapping?
5. OPTIONS có bị chặn trước khi tới Spring hay không?

Đừng vội kết luận 403 là CSRF. Spring Security mặc định không áp CSRF cho các method an toàn như OPTIONS, nhưng filter, gateway và rule tự viết có thể gây lỗi riêng.

### Trường hợp C — OPTIONS 200/204 nhưng Console vẫn báo CORS

Status 2xx **không đủ**. So sánh request và response headers:

- Thiếu `Access-Control-Allow-Origin` hoặc giá trị không khớp origin? Kiểm tra mapping/cấu hình/response bị proxy thay đổi.
- Dùng `Access-Control-Allow-Origin: *` cùng request credentials? Browser không chấp nhận trường hợp đó; cần origin cụ thể được cho phép.
- Thiếu `Access-Control-Allow-Methods` cho method dự kiến? Bổ sung đúng method.
- Thiếu `Access-Control-Allow-Headers` cho `authorization`, `content-type` hay custom header? Cho phép đúng request headers thực sự cần thiết.
- Có **hai dòng** `Access-Control-Allow-Origin` hoặc một dòng chứa nhiều origin phân tách bằng dấu phẩy? Kiểm tra layer thêm header trùng.
- OPTIONS redirect 301/302/307/308? Tránh redirect preflight, dùng URL canonical cuối cùng và để OPTIONS được trả trực tiếp.

### Trường hợp D — OPTIONS qua được, actual request thất bại

Đọc **actual** status và response: 401 có thể do chưa đăng nhập, 403 có thể do thiếu quyền hoặc CSRF token, 404 do route, 500 do server. Actual response vẫn cần có CORS headers phù hợp để JavaScript có thể quan sát lỗi. Nếu proxy tạo error response không kèm CORS headers, browser có thể báo như lỗi CORS dù root cause là lỗi upstream.

### Trường hợp E — Không thấy OPTIONS

Một GET hoặc POST safelisted có thể đi thẳng đến server. Kiểm tra `Origin` và `Access-Control-Allow-Origin` trên actual response. Nếu dùng DevTools filter chỉ một loại request, hãy chuyển sang All và kiểm tra preflight entry. Không xem việc thiếu OPTIONS là lỗi cần “sửa” bằng cách gửi thêm OPTIONS thủ công từ frontend.

## 4. Reproduce bằng curl: so sánh backend và proxy

Đặt ví dụ backend ở `http://localhost:8080`, reverse proxy ở `http://localhost:8081`, frontend origin ở `http://localhost:5173`. Gửi cùng một preflight giả lập vào backend:

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/hello' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Sau đó chỉ thay đích thành proxy, giữ nguyên header:

```bash
curl -i -X OPTIONS 'http://localhost:8081/api/hello' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

`curl -i` giúp xem nguyên status và header. Nếu backend trả 200 với **một** allowed origin, nhưng proxy trả hai dòng hoặc giá trị ghép dấu phẩy, vấn đề xuất hiện ở proxy hoặc tầng sau backend. Nếu backend đã thiếu header, hãy sửa từ cấu hình Spring. Nếu proxy 401 nhưng backend 200, tìm authentication rule tại proxy/ingress.

Trên Windows PowerShell dùng `curl.exe`; dấu xuống dòng `\` là cú pháp shell kiểu Bash, không phải PowerShell. Có thể viết lệnh trên một dòng để tránh khác biệt shell.

Kiểm tra actual request (khi API có HTTP Basic demo ở phần sau):

```bash
curl -i -u learner:demo-password \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/hello'
```

CORS headers cũng phải hợp lệ trên actual response. `curl` **không thay thế** kiểm thử trong browser vì nó không áp quy tắc CORS hoặc cookie của browser.

## 5. Cấu hình Spring Security Servlet đúng thứ tự

Ví dụ chạy được sử dụng **Java 17+**, Spring Boot 3.x, `spring-boot-starter-web` và `spring-boot-starter-security`. Controller demo chỉ xử lý GET để minh họa preflight với `Authorization` trong khi tách riêng câu chuyện CSRF cho các endpoint POST có cookie.

Cấu trúc source:

```text
src/main/java/com/example/cors/
  CorsDiagnosisApplication.java
  SecurityConfig.java
  HelloController.java
```

**`CorsDiagnosisApplication.java`**

```java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDiagnosisApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

**`HelloController.java`**

```java
package com.example.cors;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Xin chào từ API");
    }
}
```

Trong ví dụ, `.cors(Customizer.withDefaults())` dùng bean `CorsConfigurationSource` cho `/api/**` để CORS được xử lý trước bước authentication của Spring Security. Preflight GET với `authorization` nhận được phản hồi CORS **mà không cần** `-u` hay header Authorization thực tế; actual GET vẫn phải qua HTTP Basic.

Tài khoản cố định chỉ dùng để thử trên máy cục bộ. Không nhúng mật khẩu HTTP Basic vào frontend production. Cấu hình này **giữ nguyên CSRF mặc định của Spring Security**. Nếu bổ sung POST thực hiện thay đổi trạng thái, vẫn phải phân tích CSRF theo cơ chế credential thực tế; không tắt CSRF toàn cục chỉ vì nhìn thấy lỗi 403.

### 5.1. Chạy và kiểm tra

Trong project Gradle Spring Boot đã tạo:

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`.

Gửi preflight từ phần 4: dự kiến 2xx, một `Access-Control-Allow-Origin: http://localhost:5173`, allowed method GET, allowed header authorization, `Access-Control-Allow-Credentials: true`. Không coi đây là cam kết về thứ tự các header hoặc nội dung response body của mọi Spring version.

Gửi preflight yêu cầu một header **không được khai báo**:

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/hello' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-unknown-header'
```

Với cấu hình mẫu, dự kiến bị từ chối (thường 403). Nếu một header thực sự cần cho nghiệp vụ, thêm chính xác tên header vào `allowedHeaders`, không mở hết mọi header mà không xem xét.

Thử origin ngoài whitelist:

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/hello' \
  -H 'Origin: http://evil.example.test' \
  -H 'Access-Control-Request-Method: GET'
```

Với policy trên, origin đó phải bị từ chối.

## 6. Header thiếu: bảng đối chiếu triệu chứng → nguyên nhân

| Dấu hiệu | Giải thích khả dĩ | Chẩn đoán/sửa |
| --- | --- | --- |
| OPTIONS 401 và `WWW-Authenticate` | Auth filter/proxy bắt preflight đăng nhập | CORS trước authentication, không bắt OPTIONS mang credential |
| OPTIONS 403, body `Invalid CORS request` | Whitelist origin/method/header không khớp | Đối chiếu chính xác ba request header preflight với policy |
| OPTIONS 302 về `/login` | Login redirect thay vì CORS response | Chỉnh filter/proxy route để xử lý preflight trực tiếp |
| `No 'Access-Control-Allow-Origin' header` | Route không có CORS mapping, response lỗi do proxy, hoặc Origin không được forward | So sánh backend và proxy với cùng `Origin`, kiểm tra status thực |
| Origin không khớp | Sai scheme, host, port hoặc môi trường | Whitelist đúng origin, không dùng URL path |
| `Request header field authorization is not allowed` | Thiếu Authorization trong Allow-Headers | Thêm request header này nếu API thật sự dùng |
| `Request header field content-type is not allowed` | JSON request preflight cần Content-Type | Thêm Content-Type vào allowed headers |
| Method PUT/DELETE không được cho phép | Allowed methods chưa có method dự kiến | Bổ sung method đúng API/authorization |
| Thiếu Allow-Credentials | Frontend gửi credential, response không cho phép | Nếu thiết kế cần credential, dùng `allowCredentials(true)` và origin cụ thể |
| `Access-Control-Allow-Origin: *` cùng credential | Wildcard không hợp lệ với credentialed response | Trả **một** origin khớp whitelist, không `*` |
| Hai dòng Access-Control-Allow-Origin | Proxy và app cùng thêm header hoặc nhiều layer trùng | Chỉ giữ một chủ sở hữu CORS |
| OPTIONS pass nhưng actual POST 403 | Có thể là CSRF/authorization của nghiệp vụ | Kiểm tra actual response và log, không nới CORS vô cớ |
| Browser không gửi cookie | Sai credentials mode, `SameSite`, `Secure`, Domain/Path hoặc third-party policy | Sửa cookie/fetch policy, không sửa bằng Allow-Headers |
| `Access-Control-Expose-Headers` không có | JS không đọc được một custom **response** header | Đặt exposed headers đúng nếu client cần đọc |
| Có CORS header ở response 200 nhưng thiếu ở 500 | Proxy/gateway tạo error response thiếu CORS | Kiểm tra chính xác tầng tạo response lỗi và policy tại đó |

**Lưu ý:** `Access-Control-Allow-Origin` không nhận nhiều origin phân tách dấu phẩy. Với credentialed request, `*` là không hợp lệ, ngay cả khi response chứa `Access-Control-Allow-Credentials: true`. Một số cấu hình Spring còn từ chối kết hợp `allowedOrigins("*")` và `allowCredentials(true)` khi validate.

## 7. Cấu hình trùng ở reverse proxy, ingress hoặc CDN

Chuỗi phổ biến:

```text
Browser -> CDN/WAF -> Ingress/Nginx -> Spring Security -> Spring MVC
```

Giả sử Spring trả:

```http
Access-Control-Allow-Origin: http://localhost:5173
```

nhưng Nginx cũng có:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    add_header Access-Control-Allow-Origin "http://localhost:5173" always;
    add_header Access-Control-Allow-Credentials "true" always;
}
```

Proxy có thể làm response xuất hiện **hai** dòng Access-Control-Allow-Origin, hoặc gộp thành:

```http
Access-Control-Allow-Origin: http://localhost:5173, http://localhost:5173
```

Cả hai dạng đều không hợp lệ cho `Access-Control-Allow-Origin`; browser không tự suy ra hai giá trị giống nhau là một.

### 7.1. Cách sửa khi Spring là chủ sở hữu CORS

Nếu Spring đã cấu hình policy thống nhất và có thể xử lý OPTIONS, để **Spring là tầng duy nhất tạo CORS response headers**. Proxy thực hiện định tuyến/forward:

```nginx
server {
    listen 8081;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Bỏ các `add_header Access-Control-Allow-*` ở Nginx và các quy tắc tương tự ở Ingress/CDN/Gateway. Kiểm tra cấu hình **hiệu lực** và reload phù hợp trước khi thử qua proxy. Đây chỉ là trích đoạn minh họa phần CORS/forward, không phải cấu hình reverse proxy production hoàn chỉnh.

Nếu kiến trúc chọn **proxy** làm chủ sở hữu CORS, nó phải xử lý đầy đủ whitelist origin, OPTIONS, allowed method/header, credentials, error responses và cache; đồng thời backend không được phát một bộ header khác gây trùng. Không chọn nửa app, nửa proxy cho cùng một endpoint mà thiếu kiểm soát.

### 7.2. Truy nguyên layer gây trùng

So sánh cùng request từ **backend trực tiếp → ingress/proxy → endpoint sau CDN**:

1. Đếm dòng `Access-Control-Allow-Origin` ở mỗi response, kể cả trường hợp bị gộp thành CSV.
2. Đọc status: 200 ở backend nhưng 401 ở proxy chứng tỏ auth/proxy policy tham gia.
3. Kiểm tra `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` có được forward qua từng hop hay không.
4. Kiểm tra rewrite path: cấu hình CORS chỉ cho `/api/**` nhưng proxy chuyển thành route khác có thể làm policy không khớp.
5. Xem những rule tương đương `add_header ... always`, Ingress annotations và CDN Response Header Rules: chúng có thể thêm header cả trên 401/403/500.
6. Kiểm tra cache key, TTL và `Vary` nếu có nhiều frontend origins hoặc kết quả preflight thay đổi theo method/header.

Chỉ thêm header khác tại proxy không chữa được response đã sai; nó có thể làm lỗi trầm trọng hơn. Một chính sách nhất quán với đúng một tầng sở hữu giúp việc debug và audit dễ hơn.

## 8. Quan hệ giữa Spring Security CORS, Spring MVC và filter order

Một ứng dụng Servlet có thể khai báo CORS qua:

- `CorsConfigurationSource` + `http.cors(...)` trong `SecurityFilterChain`.
- Spring MVC `WebMvcConfigurer#addCorsMappings`.
- `@CrossOrigin` ở controller hoặc handler method.
- `CorsFilter` được đăng ký riêng với filter order cụ thể.
- Header tự tạo ở ingress/proxy/CDN.

**Không có nghĩa** cứ dùng hai cách của Spring là tự động tạo duplicate header: framework có thể kết hợp policy hoặc bỏ qua việc xử lý lần hai. Tuy vậy, chính sách đặt rải rác khiến matcher, allowed methods, credentials và filter order khác nhau. Chọn cơ chế được quản lý thống nhất, kiểm tra đúng `SecurityFilterChain` xử lý URL API, đặc biệt nếu ứng dụng có **nhiều** filter chain.

Nếu `CorsConfigurationSource` chỉ đăng ký `/api/**`, request chuyển thành `/other/**` sau proxy rewrite có thể không tìm thấy policy. Khi thấy endpoint A có header còn B không có, đọc mapping và matcher của **đúng request** trước khi sửa origin whitelist.

## 9. Kiểm thử MockMvc cho đúng luồng

Thêm test dependencies `spring-boot-starter-test` và `spring-security-test`. Đặt file **`src/test/java/com/example/cors/CorsDiagnosisTests.java`**:

```java
package com.example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsDiagnosisTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void permittedPreflightDoesNotNeedAuthentication() throws Exception {
        mockMvc.perform(options("/api/hello")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "http://localhost:5173"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void unlistedRequestHeaderIsRejected() throws Exception {
        mockMvc.perform(options("/api/hello")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "x-unknown-header"))
            .andExpect(status().isForbidden());
    }

    @Test
    void untrustedOriginIsRejected() throws Exception {
        mockMvc.perform(options("/api/hello")
                .header("Origin", "http://evil.example.test")
                .header("Access-Control-Request-Method", "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualGetKeepsCorsHeaders() throws Exception {
        mockMvc.perform(get("/api/hello")
                .with(user("learner"))
                .header("Origin", "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "http://localhost:5173"));
    }
}
```

Chạy `./gradlew test`; trên Windows dùng `.\gradlew.bat test`.

Các test giúp xác minh Spring filter logic trong JVM: preflight hợp lệ **không cần authentication**, requested header/origin sai bị từ chối và actual response có allowed origin. Nhưng **MockMvc không đi qua Nginx/Ingress/CDN**: lỗi double header ở proxy chỉ lộ rõ khi kiểm tra HTTP qua hạ tầng thật. Với ứng dụng lớn, bổ sung test cho origin được phê duyệt thứ hai, method PUT/DELETE bị cấm, request có nhiều requested headers, actual 401/403 và các policy khác trên từng security chain.

## 10. Không nhầm CORS với auth, CSRF, cookie và cache

**Authentication** kiểm tra ai gọi API; **authorization** kiểm tra người đó được làm gì; **CSRF** ngăn các request thay đổi trạng thái bị giả mạo khi browser tự gửi credential như session cookie; **CORS** điều khiển khả năng JavaScript ở origin khác đọc kết quả theo chính sách trình duyệt. Preflight phải được xử lý phù hợp mà không buộc mang credential của actual request, nhưng actual request vẫn phải được xác thực và phân quyền.

Một OPTIONS pass không bảo đảm actual POST pass: Spring có thể trả 403 vì CSRF token thiếu, hoặc vì user không đủ quyền. Đừng chữa 403 của actual POST bằng cách nới rộng CORS. Đồng thời, `Access-Control-Allow-Credentials: true` không ép trình duyệt gửi cookie. Cookie còn chịu `SameSite`, `Secure`, Domain/Path, `fetch` credentials mode và third-party cookie policy. API chạy qua HTTPS khác với `http://` về origin và cookie policy.

Với cache/CDN, origin được phản chiếu từ whitelist cần `Vary: Origin`. Với preflight phụ thuộc method/request headers, xem thêm `Vary: Access-Control-Request-Method, Access-Control-Request-Headers`. `Access-Control-Max-Age` là cache preflight của browser, không thay thế cache key và cấu hình an toàn ở proxy.

Nếu tự gọi curl mà **không có `Origin`**, response có thể không có header CORS vì server không nhận diện đây là request cross-origin. Tương tự, OPTIONS thiếu `Access-Control-Request-Method` không mô phỏng đúng một browser preflight. JavaScript `fetch` không nên và thường không thể tự đặt `Origin` — browser quản lý header này.

## 11. Checklist áp dụng vào incident thật

1. Ghi chính xác frontend origin, API URL, method, request headers, bản ghi OPTIONS/actual, status và redirect chain.
2. Với OPTIONS 401/302, kiểm tra Spring Security/proxy auth và đặt CORS xử lý trước authentication.
3. Với OPTIONS 403, đối chiếu origin, requested method, requested headers và path với policy thật; tách lỗi WAF/gateway khỏi lỗi Spring.
4. Với status 2xx nhưng browser vẫn chặn, kiểm tra `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Allow-Credentials` **và số lượng các header**.
5. Nếu actual request lỗi, đọc status/body/log của actual request; kiểm tra authorization, CSRF, exception và CORS header trên error response.
6. Nếu thấy duplicate header, so sánh backend và từng hop proxy/CDN; chỉ giữ một tầng làm chủ chính sách CORS.
7. Xác nhận bằng MockMvc cho logic Spring, bằng curl với cùng bộ request trước/sau proxy, và bằng DevTools trong browser sau khi làm mới preflight cache phù hợp.

**Nguyên tắc cốt lõi:** luôn xác định **request nào** thất bại, **header nào** không hợp lệ và **tầng nào** tạo response. Sửa chính sách CORS tại đúng tầng; không tắt authentication/CSRF, không thêm wildcard hoặc header trùng lặp để che triệu chứng.
