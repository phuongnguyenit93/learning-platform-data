# Kiểm thử đường dẫn không dự kiến để phát hiện khoảng trống bảo vệ

Trong **Spring Security Servlet**, một ứng dụng có thể bảo vệ đúng mọi URL mà developer đã nhớ khai báo, nhưng vẫn để hở một URL phụ: đường dẫn có thêm segment, endpoint cũ, HTTP method khác, route dưới context path, hoặc đường dẫn đi vào một `SecurityFilterChain` không được dự tính. Khi đó authentication hoạt động tốt nhưng **request matching hoặc authorization coverage** lại sai.

**Kiểm thử đường dẫn không dự kiến** (negative-path testing) là chủ động gửi những request ngoài danh sách được phép rồi chứng minh chúng bị chặn tại ranh giới bảo mật thích hợp. Không chỉ kiểm tra phản hồi khác 200. Ví dụ, HTTP **404** do Spring MVC không tìm được controller không tự chứng minh `AuthorizationFilter` đã từ chối request; HTTP **403** từ `CsrfFilter` không chứng minh quy tắc role đã chạy; HTTP **401** với anonymous có thể là authentication entry point của một rule deny. Phải biết **lớp nào** đã đưa ra kết quả.

Bài hướng đến **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/MVC**. Nội dung gồm hai tầng matcher, chính sách deny-by-default, các nhóm path và method cần thử, ví dụ cấu hình hai SecurityFilterChain, test MockMvc có danh tính/CSRF thật, test server HTTP thật, kiểm tra URL normalization, proxy/context/servlet path, route manifest và checklist phòng ngừa regression. Các matcher cụ thể (MvcRequestMatcher, AntPathRequestMatcher, PathPatternRequestMatcher) có semantics phụ thuộc version/configuration, nên không thể suy ra mọi raw URL được xử lý giống nhau.

## 1. Khoảng trống bảo vệ là gì?

Khoảng trống bảo vệ xuất hiện khi có ít nhất một request có thể tới chức năng đáng lẽ phải kiểm tra quyền mà **không đi qua điều kiện authentication/authorization mong muốn**.

~~~text
Ý định ban đầu:
  GET /api/reports/{id} -> cần REPORT_READ

Những đường request cần kiểm tra thêm:
  GET    /api/reports/10
  GET    /api/reports/10/export
  GET    /api/reports/10.json
  GET    /api/reports/10/
  POST   /api/reports/10
  GET    /api/report-old/10
  GET    /admin/reports
  GET    /api
  GET    /public/../api/reports/10
~~~

Các URL có dấu chấm, encoded separators hoặc dot segments chỉ là **dữ liệu để thiết kế test phòng vệ**: proxy, servlet container và `StrictHttpFirewall` có thể normalize hoặc từ chối request **trước** khi tới matcher. Không được xem chúng là các dạng tương đương trên mọi hệ thống.

| Loại thiếu sót | Ví dụ | Nguy cơ |
| --- | --- | --- |
| Public matcher quá rộng | `/api/**` được permitAll đặt trước rule protected | Mở nhầm endpoint nhạy cảm |
| Protected matcher quá hẹp | Chỉ check một URL chính xác, bỏ export/alias | Endpoint phụ không có rule |
| Thiếu catch-all chain | Chỉ khai báo `securityMatcher("/api/**")` | Controller ngoài /api không qua Spring Security |
| Không ràng buộc method | Bảo vệ GET nhưng quên POST/DELETE cùng URL | Phát sinh quyền ghi ngoài ý định |
| Dispatcher/servlet path lệch | Ứng dụng mount dưới /portal | Rule test khác production |
| Path normalization khác nhau | Encoded slash, double slash, semicolon | Gateway và app có thể hiểu khác path |
| Legacy route còn sống | `/v1/report-export` | Alias cũ bypass rule mới |
| Nhiều filter chains | API chain và web chain có thứ tự khác | Chọn chain không mong muốn |
| Controller mapping mới | Auto-config route, actuator nếu được bật | Có route mới chưa được phân loại |
| Object-level policy thiếu | User có quyền READ nhưng không sở hữu record | Không phải path bug nhưng vẫn lộ dữ liệu |

**Tiêu chí thành công:** Những route hợp lệ hoạt động với quyền đúng; những route/identity/method ngoài hợp đồng bị chặn; không có một đường khác tới cùng nghiệp vụ mà bỏ kiểm tra quyền.

## 2. Hai tầng matching cần kiểm thử riêng

Khi request đi vào Spring Security Servlet, `FilterChainProxy` tìm **SecurityFilterChain đầu tiên khớp**. Trong chain đó, các filters thực thi và `AuthorizationFilter` áp dụng chính sách từ `authorizeHttpRequests(...)`.

~~~text
HTTP request
     |
     v
FilterChainProxy
     |
     +-- Chain #1: securityMatcher("/api/**")
     |      |
     |      +-- GET /api/records/{id} -> RECORD_READ
     |      +-- POST /api/records/{id} -> RECORD_WRITE
     |      +-- anyRequest().denyAll()
     |
     +-- Chain #2: catch-all (không đặt securityMatcher hẹp)
            |
            +-- GET /public/ping -> permitAll()
            +-- anyRequest().denyAll()
~~~

Nếu request khớp chain #1 thì **không chạy tiếp chain #2** để xin một quyết định khác. Nếu không khớp chain nào, request có thể không được Spring Security xử lý, dù Spring MVC có controller thật.

### securityMatcher và requestMatchers không đồng nghĩa

| API | Nó khớp cái gì? | Hậu quả khi không khớp |
| --- | --- | --- |
| `http.securityMatcher(...)` | Toàn bộ filter chain | Thử chain tiếp theo; có thể không có chain |
| `authorizeHttpRequests(...requestMatchers(...))` | Rule phân quyền trong chain đã chọn | Thử rule tiếp theo |
| `anyRequest().denyAll()` | Mọi request còn lại **trong chain đó** | Không bảo vệ path bên ngoài chain |
| `@GetMapping/@PostMapping` | Controller mapping của Spring MVC | Không tự quyết định security policy |

Sai lầm phổ biến:

~~~java
// Chỉ có chain API: tưởng denyAll phủ cả ứng dụng.
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().denyAll());
    return http.build();
}
~~~

Một controller `GET /admin/export` không thuộc `/api/**` có thể không được Spring Security bảo vệ nếu không có chain khác. Cần **fallback chain** hoặc xác định có chủ đích phạm vi nào được loại trừ, sau đó test route thực để xác minh.

### Thứ tự rule có thể gây bypass

~~~java
// SAI: matcher rộng được kiểm tra trước.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/private/**").hasRole("ADMIN")
    .anyRequest().denyAll());
~~~

Request `/api/private/export` có thể được rule `permitAll` rộng cho qua trước khi tới rule admin. Đặt các rule chi tiết/protected trước, khai báo public allowlist chỉ cho URL thật cần thiết, và kết thúc bằng fallback deny.

Không bao giờ cho rằng một rule viết trong file cấu hình chắc chắn đã chạy; cần test URL nằm ở **vùng giao giữa patterns**.

## 3. Ma trận kiểm thử phải có cả positive và negative

Bộ test chỉ gồm 403/401 dễ đánh lừa: cấu hình deny-all cho tất cả URL sẽ làm rất nhiều test “không cho truy cập” xanh, nhưng ứng dụng vô dụng và không chứng minh các rule cụ thể hoạt động.

Nên có ba lớp:

1. **Positive:** URL hợp lệ, method hợp lệ và user đúng quyền nhận kết quả thành công.
2. **Negative cùng URL:** anonymous hoặc user thiếu quyền bị từ chối.
3. **Negative ngoài hợp đồng:** URL phụ, method ngoài policy, namespace ngoài chain và URL gần giống bị từ chối.

Ví dụ ứng dụng ở mục 7:

| Request | Credential | Kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- |
| GET /public/ping | anonymous | 200 | Route public thực sự dùng được |
| GET /api/records/7 | reader / RECORD_READ | 200 | Protected route cho đúng user |
| GET /api/records/7 | anonymous | 401 với Basic entry point | Không có authentication |
| GET /api/records/7 | writer / RECORD_WRITE | 403 | WRITE không thay thế READ |
| POST /api/records/7 | writer + CSRF hợp lệ | 200 | Quyền WRITE và CSRF đã thỏa mãn |
| POST /api/records/7 | reader + CSRF hợp lệ | 403 | Quyền WRITE bị kiểm tra |
| POST /api/records/7 | writer thiếu CSRF | 403 | CsrfFilter chặn, khác authorization |
| GET /api/records/7/export | reader | 403 | Segment phụ không được allow |
| GET /api/records/7.json | reader | 403 | Suffix không được allow |
| GET /api/records/7/ | reader | 403 trong demo | Trailing slash không tự mở |
| GET /api/unknown | reader | 403 | API fallback deny |
| GET /api | reader | 403 | Fallback chain bảo vệ exact prefix |
| GET /admin/diagnostics | reader | 403 | Ngoài API không bị bỏ trống |
| GET /public/secret | reader | 403 | Public chỉ cho phép ping |

Các status là kỳ vọng **của cấu hình demo**, không phải một quy tắc bất biến cho mọi Spring Security application. Với form login, một anonymous request có thể nhận 302 tới login. Một custom AccessDeniedHandler có thể cố ý trả JSON/404 thay vì 403, nhưng cần kiểm tra contract thực sự.

### Vì sao dùng một identity đã authenticated cho URL lạ?

Khi một request anonymous bị authorization deny, `ExceptionTranslationFilter` có thể chuyển sang authentication entry point, trả 401/302. Khi dùng `reader` đã xác thực cho path ngoài allowlist, kết quả 403 giúp phân biệt rõ hơn việc policy deny (so với chưa login). Tuy vậy 403 cũng có thể đến từ một filter khác, vì thế cần cấu hình test đúng và dùng positive cases.

## 4. 404 không phải bằng chứng an toàn

Xét request:

~~~http
GET /api/internal/ghost
Authorization: Basic <valid-credentials>
~~~

Nếu nhận 404, có hai khả năng tiêu biểu:

- Spring Security cho request đi tiếp, nhưng Spring MVC không tìm thấy controller.
- Một thành phần cố ý trả 404 sau khi đã áp một chính sách nào đó.

Không thể chỉ nhìn 404 mà kết luận `AuthorizationFilter` đã deny. Tương tự 405 Method Not Allowed có thể do MVC từ chối method sau khi đã đi qua security.

### Cách chứng minh security enforcement

- Chạy request **cùng một URL thực sự có controller** với user được phép và user không được phép. Ví dụ reader GET record 7 trả 200, writer GET cùng URL trả 403.
- Dùng một URL ngoài allowlist với **authenticated user**; khi thiết kế deny-by-default như demo, kỳ vọng 403 thay vì 404.
- Kiểm tra chain matching: API URL vào API chain, route bên ngoài vào catch-all chain, không rơi ra ngoài toàn bộ Spring Security.
- Nếu cần bằng chứng chặt hơn, dùng test-only controller hoặc spy/service probe để xác minh request denied **trước khi controller chạy**.
- Đặt một integration test qua HTTP server/proxy thật cho những URL được rewrite hoặc normalize.

**Không đưa một endpoint dễ tổn thương ra production chỉ để làm security test.** Route probe nhạy cảm chỉ tồn tại trong test profile/test context; ở production, review route registry và policy đúng cách.

## 5. Danh sách biến thể đường dẫn nên thử

Với endpoint chuẩn `GET /api/records/7`, tạo các nhóm có ý nghĩa:

| Nhóm | Ví dụ | Cần lưu ý |
| --- | --- | --- |
| Thêm slash cuối | `/api/records/7/` | Matcher/router có thể thay đổi theo version |
| Suffix/extension | `/api/records/7.json` | Có thể bị route alias hoặc suffix matching xử lý |
| Thêm subpath | `/api/records/7/export` | Pattern `*` khác `**` |
| Thiếu ID | `/api/records` | Không khớp template /{id} |
| Thiếu slash sau prefix | `/api` | Không tự kết luận khớp `/api/**` |
| Prefix gần giống | `/api-records/7` | Có fallback bao phủ không? |
| Viết hoa | `/API/records/7` | Case sensitivity ở tầng routing |
| Slash kép | `/api//records/7` | Container/proxy/firewall có thể reject hoặc normalize |
| Dot segments | `/api/public/../records/7` | Mỗi HTTP layer có thể hiểu khác |
| Percent encoding | `/api/records%2F7`, `%2e%2e` | Server có thể từ chối hoặc decode |
| Matrix parameters | `/api/records/7;mode=view` | Semicolon có thể bị StrictHttpFirewall reject |
| Unicode | URL chứa Unicode hoặc UTF-8 encoded | Normalization, charset, matcher semantics |
| Query string | `/api/records/7?export=true` | Path matcher thường không dựa vào query; handler có thể hành xử khác |
| Fragment | `#section` | Fragment không được browser gửi trong HTTP request |

Không coi mọi biến thể là một đường tấn công được chấp nhận: một số request phải bị firewall/container trả 400 ngay. Khi test, xác định **lớp từ chối** và kiểm tra gateway/proxy có thể đổi dạng request trước khi tới container không.

### Quan trọng: khớp URL và chức năng là hai việc khác nhau

Một URL GET có query `?export=true` thường vẫn match cùng path với GET không có query, nhưng controller có thể dùng query để kích hoạt export. Do đó nếu hành vi export cần quyền riêng, kiểm tra business authorization tại service hoặc tách route/method với policy rõ; không kỳ vọng path matcher tự phân biệt mọi biến thể input nghiệp vụ.

### Routes ngoài MVC

Những đường khác cũng có thể cần test:

- Static file resources và upload/download.
- Servlet được map riêng, không qua DispatcherServlet chính.
- WebSocket handshake, SSE, GraphQL endpoints.
- Trang error/forward dispatch.
- Actuator/metrics/debug nếu dependency được bật.
- API version cũ, aliases, redirect/forward targets.
- Files serving qua CDN/web server mà Spring Security không trực tiếp kiểm soát.

Nếu một tài nguyên được phục vụ **trước khi tới ứng dụng Servlet**, chỉ test Spring Security không đủ; phải kiểm tra quyền ở web server/CDN/object storage hoặc kiến trúc cung cấp tài nguyên.

## 6. Các HTTP method không được tự kế thừa quyền

Một rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/records/{id}")
    .hasAuthority("RECORD_READ")
~~~

không tự cấp quyền cho `POST /api/records/{id}` hoặc `DELETE /api/records/{id}`. Một lỗi khác là khai báo matcher không ràng buộc HTTP method nhưng chỉ muốn cho GET.

Những method đáng cân nhắc theo API:

~~~text
GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE, TRACE
~~~

- GET thường là đọc; không nên có side effect làm thay đổi trạng thái.
- HEAD có semantics liên quan GET ở web framework nhưng path/method matcher có thể khác; test thực tế.
- OPTIONS có thể được xử lý bởi CORS preflight logic, cần policy riêng cho môi trường frontend.
- POST/PUT/PATCH/DELETE có thể bị CSRF filter từ chối trước authorization khi dùng cookie/session.
- TRACE nên bị đánh giá/chặn ở container/proxy theo policy; không mặc định test MockMvc phản ánh behavior HTTP server.

### Kiểm thử CSRF và authorization độc lập

Nếu muốn chứng minh user thiếu WRITE bị deny, gửi request với **CSRF token hợp lệ** để không bị `CsrfFilter` chặn trước khi AuthorizationFilter kiểm tra. Có hai ca test riêng:

~~~text
writer POST /api/records/7 + csrf -> 200 (đúng WRITE)
reader POST /api/records/7 + csrf -> 403 (thiếu WRITE)
writer POST /api/records/7 no csrf -> 403 (CSRF)
~~~

Không suy ra nguyên nhân chỉ từ mã HTTP 403; positive control và cấu hình test cho phép xác định rõ hơn.

## 7. Ví dụ Spring Boot: API chain và catch-all chain

Ứng dụng demo dùng:

- `/api/**` cho API chain. GET record cần `RECORD_READ`, POST record cần `RECORD_WRITE`, API route khác deny.
- Fallback chain không có securityMatcher hẹp: chỉ GET /public/ping được phép không cần login, mọi đường khác deny.
- HTTP Basic authentication để test đơn giản; **production cần HTTPS, identity model và giới hạn abuse phù hợp**.
- `PasswordEncoder` dùng BCrypt cho credentials demo.
- CSRF vẫn bật cho POST; test sử dụng `with(csrf())`.
- Không dùng controller test thay thế filter test; hai chain thực sự cần chạy.

### 7.1. Maven dependencies

Trong project Spring Boot 3.x đã có parent/BOM/plugin tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Không trộn Spring Security version khác BOM. Code framework yêu cầu classpath Boot/Security; chỉ bài Java 17 độc lập ở mục 11 chạy bằng JDK trống.

### 7.2. Main class

Tạo `src/main/java/com/example/pathguard/PathGuardApplication.java`:

~~~java
package com.example.pathguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathGuardApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathGuardApplication.class, args);
    }
}
~~~

### 7.3. Hai SecurityFilterChain với @Order

Tạo `src/main/java/com/example/pathguard/SecurityConfig.java`:

~~~java
package com.example.pathguard;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-demo-only"))
                .authorities("RECORD_READ")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("writer-demo-only"))
                .authorities("RECORD_WRITE")
                .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/records/{id}")
                    .hasAuthority("RECORD_READ")
                .requestMatchers(
                    HttpMethod.POST, "/api/records/{id}")
                    .hasAuthority("RECORD_WRITE")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // CSRF giữ nguyên; POST test phải có csrf().
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        // Không đặt securityMatcher hẹp cho chain bao phủ.
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/ping")
                    .permitAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Giải thích từng điểm:

1. `@Order(1)` cho API chain được xét trước catch-all.
2. `securityMatcher("/api/**")` giới hạn **phạm vi chain**.
3. Hai `requestMatchers(HttpMethod, pattern)` phân biệt GET/POST. Khi route nhạy cảm thêm method mới, nó không tự được allow.
4. API `anyRequest().denyAll()` bắt đường API ngoài hợp đồng.
5. Fallback chain không có securityMatcher hẹp, bảo vệ các đường ngoài namespace API, gồm /api nếu implementation không match /api/**.
6. Fallback `/public/ping` là một **allowlist entry chính xác**; không dùng `/public/**.permitAll()` rộng chỉ vì một endpoint cần công khai.
7. Cả hai chain dùng HTTP Basic, nhưng với auth system khác cần xác minh authentication/authorization filters tương ứng cho từng chain.
8. Không gọi `csrf.disable()`; điều này làm rõ sự khác nhau giữa CSRF deny và role deny.

**Caveat version:** ở Spring Security 6.x, các matcher DSL có thể chọn MvcRequestMatcher hoặc matcher loại khác theo classpath/version. Trên phiên bản mới, cách tạo PathPatternRequestMatcher và servlet-path handling có thể khác. Test được viết trên đúng version đã khóa trong dự án; đừng tự đoán semantics của encoded paths.

### 7.4. Controller

Tạo `src/main/java/com/example/pathguard/RecordController.java`:

~~~java
package com.example.pathguard;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecordController {

    @GetMapping("/api/records/{id}")
    public Map<String, Object> read(@PathVariable long id) {
        // Dữ liệu giả cho demo. App thật cần object-level security.
        return Map.of("id", id, "status", "read");
    }

    @PostMapping("/api/records/{id}")
    public Map<String, Object> write(@PathVariable long id) {
        // Demo không thay đổi database.
        return Map.of("id", id, "status", "updated");
    }
}
~~~

Tạo `src/main/java/com/example/pathguard/PublicController.java`:

~~~java
package com.example.pathguard;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

**Điểm bảo mật:** Controller không cần biết deny-all fallback cho URL chưa khai báo; việc chặn nằm ở filter chain. Trong production, quyền RECORD_READ cho cả nhóm record vẫn chưa đủ nếu mỗi record có owner/tenant: cần service-level/object-level authorization. Điều này nằm ngoài vấn đề path matching nhưng cũng phải được đánh giá.

### 7.5. Chạy local và thử request

~~~bash
./mvnw spring-boot:run
~~~

Trên máy local, dùng curl yêu cầu password qua prompt thay vì viết password vào shell history:

~~~bash
curl -i -u reader http://localhost:8080/api/records/7
curl -i -u reader http://localhost:8080/api/records/7/export
curl -i -u reader http://localhost:8080/admin/diagnostics
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng nếu nhập đúng password demo:

~~~text
reader GET /api/records/7         -> 200
reader GET /api/records/7/export  -> 403
reader GET /admin/diagnostics     -> 403
anonymous GET /public/ping        -> 200
~~~

Không dùng HTTP Basic trên mạng thật không có TLS và không đưa credentials production vào tài liệu hoặc logs.

## 8. Integration tests với MockMvc

Tạo `src/test/java/com/example/pathguard/PathCoverageIntegrationTest.java`. Bộ test cố ý có positive, missing permission, anonymous, unknown path và method cases. Nó chạy qua Spring Security filters của application context.

~~~java
package com.example.pathguard;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathCoverageIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void publicRouteWorks() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk());
    }

    @Test
    void readerCanGetAllowedRecord() throws Exception {
        mvc.perform(get("/api/records/7")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void anonymousMustAuthenticate() throws Exception {
        mvc.perform(get("/api/records/7"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void writerCannotReadWithoutReadAuthority() throws Exception {
        mvc.perform(get("/api/records/7")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanWriteWithCsrf() throws Exception {
        mvc.perform(post("/api/records/7")
                .with(httpBasic("writer", "writer-demo-only"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("updated"));
    }

    @Test
    void readerCannotWriteEvenWhenCsrfIsValid() throws Exception {
        mvc.perform(post("/api/records/7")
                .with(httpBasic("reader", "reader-demo-only"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingCsrfIsASeparateFailure() throws Exception {
        mvc.perform(post("/api/records/7")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @ParameterizedTest(name = "unexpected path {0} is denied")
    @ValueSource(strings = {
        "/api/records/7/export",
        "/api/records/7.json",
        "/api/records/7/",
        "/api/records",
        "/api/unknown",
        "/api",
        "/admin/diagnostics",
        "/public/secret"
    })
    void unexpectedPathIsDenied(String path) throws Exception {
        mvc.perform(get(path)
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

Một request lạ authenticated trong mẫu này nhận 403 nhờ rule deny-all ở chain đã chọn. Nếu thiếu catch-all chain, case `/admin/diagnostics` hoặc `/api` có thể rơi xuống MVC và trả 404, khiến test fail — đúng mục tiêu phát hiện khoảng trống.

### 8.1. Vì sao test POST với csrf() hợp lệ?

POST không token có thể bị `CsrfFilter` từ chối với 403 trước khi tới AuthorizationFilter. Nếu muốn chứng minh quyền RECORD_WRITE hoạt động, test phải gửi CSRF hợp lệ. Hai test `reader + csrf` và `writer + csrf` cung cấp bằng chứng về kiểm tra quyền; test `writer without csrf` kiểm tra một lớp bảo vệ khác.

Nếu API production dùng Bearer token stateless chứ không dùng browser cookie, CSRF policy có thể được đánh giá khác; không mặc định tắt CSRF chỉ vì body JSON.

### 8.2. Test 403 có chắc do API chain?

Không nhất thiết. Cả API chain và fallback chain đều có thể deny; response 403 không nêu chính xác chain. Nếu mục tiêu là xác nhận **chain assignment**, cần thêm integration assertion với policy instrumentation/test manager hoặc quan sát filter chain ở test profile. Việc kết hợp positive case và fallback denies vẫn xác nhận những tính chất quan trọng.

### 8.3. Không dùng standaloneSetup cho test bảo mật

`MockMvcBuilders.standaloneSetup(controller)` không mặc định gắn SecurityFilterChain; controller có thể trả 200 dù app production chặn. Dùng `@SpringBootTest + @AutoConfigureMockMvc` hoặc cấu hình springSecurity filter trong test setup. Một test `@WithMockUser` có ích cho role policies nhưng không chứng minh HTTP Basic provider/password encoder đã chạy. Ví dụ dùng credentials qua request để bao phủ cả filter authentication.

### 8.4. Nếu test trailing slash thất bại thì sao?

Hãy kiểm tra Spring Security matcher, MVC handler mapping và version thay vì ngay lập tức sửa assertion thành status 404. Mục tiêu của ví dụ là **chặn mọi đường ngoài allowlist trước MVC**. Tuy nhiên khi một matcher có semantics khác, một path có trailing slash có thể được coi là cùng route hợp lệ; product policy phải định nghĩa rõ trường hợp nào được allow. Phân loại trước, rồi cập nhật matcher và negative tests cho khớp hợp đồng.

## 9. HTTP server/proxy thật khác MockMvc

Một request thực đi qua:

~~~text
Browser / HTTP client
       |
       v
CDN, reverse proxy, gateway
       | (rewrite/normalize/path decode có thể xảy ra)
       v
Servlet container (HTTP parser, servlet path)
       |
       v
StrictHttpFirewall / FilterChainProxy
       |
       v
SecurityFilterChain + AuthorizationFilter
       |
       v
Spring MVC controller
~~~

MockMvc mô phỏng request/filter/dispatcher trong test context; nó **không** đảm bảo hoàn toàn giống HTTP parser của Tomcat/Jetty/Undertow hoặc proxy production. Với double slash, encoded separators, dot segments, semicolon, URL Unicode, context path, headers forwarded và raw request-target, cần kiểm tra trên **embedded server** và lý tưởng qua cùng loại proxy/gateway đang dùng.

### Ví dụ HTTP integration test cơ bản

Trong Spring Boot 3.x có `RestClient` và `@LocalServerPort` phù hợp:

~~~java
package com.example.pathguard;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpPathTest {

    @LocalServerPort int port;

    @Test
    void publicPathWorksThroughRealHttpServer() {
        RestClient client = RestClient.create(
            "http://localhost:" + port);
        String body = client.get().uri("/public/ping")
            .retrieve().body(String.class);

        assertEquals("pong", body);
    }
}
~~~

Đây là test HTTP server thật cho **một URL hợp lệ**, không phải bộ raw-URL fuzz tests. `RestClient` được cung cấp trong Spring Framework 6.1+; ở dự án Spring Boot 3.0/3.1 có thể cần dùng WebClient/TestRestTemplate hoặc HTTP client khác theo version. Đối với URL encoded, một HTTP client có thể tự encode lại trước khi gửi; phải biết chính xác bytes/request-target đi trên mạng.

### Kiểm thử production-like phải xem gì?

- Request bị container trả 400 hay firewall từ chối?
- Đường dẫn sau reverse proxy có giống path matcher nhìn thấy?
- HTTP method/servlet mapping có bị chuyển đổi không?
- Có chain nào bảo vệ route ngoài /api?
- Có URL alias từ gateway đi vào controller không?
- Header forwarded có đến từ proxy đáng tin hay có thể bị client tự gửi?
- Cookie/session/context path có tác động tới entry point và auth không?
- Hệ thống log có ghi cả raw request target và normalized path an toàn mà không rò credentials không?

Một status 400 do firewall/container chặn có thể là kết quả an toàn, nhưng **không phải bằng chứng AuthorizationManager đã deny**. Ghi rõ lớp chặn để việc nâng version không che giấu thay đổi.

## 10. Route inventory và test khi mở rộng sản phẩm

Một app lớn không nên dựa vào trí nhớ để liệt kê mọi URL nhạy cảm. Xây **route/policy manifest** được review:

| Route family | Method | Chính sách |
| --- | --- | --- |
| /public/ping | GET | Public |
| /api/records/{id} | GET | RECORD_READ |
| /api/records/{id} | POST | RECORD_WRITE + CSRF phù hợp |
| /api/records/{id}/export | GET | Deny cho tới khi có policy riêng |
| /admin/** | Mọi method | Deny trong demo |
| Unknown routes | Mọi method | Deny |

Khi có endpoint mới:

1. Lấy danh sách mapping thực sự được đăng ký từ MVC/actuator mapping (nếu được bật và bảo vệ phù hợp), kể cả route từ auto-config hoặc module khác.
2. So với các entry/route families đã được review.
3. Nếu route nhạy cảm mới chưa có policy, yêu cầu review hoặc fail CI.
4. Thêm test anonymous, authorized, unauthorized.
5. Thêm negative variants của route đó: subpath, extension, method khác và namespace gần giống.
6. Test proxy/context path nếu route nằm sau rewrite.
7. Giữ regression cases từ bugs đã phát hiện.

Cần chú ý không phải mỗi controller mapping có một dòng `requestMatchers` riêng: pattern rule có thể bảo vệ một nhóm route hợp lý. Điều cần xác minh là **route mới có được phân loại đúng không và rule có thực thi không**.

### Pseudocode kiểm tra drift

~~~text
registered = all MVC routes and methods in test context
reviewed = declared security policy manifest

for each route in registered:
    if not covered by reviewed policy:
        fail("UNCLASSIFIED_ROUTE")
    else:
        generate allowed and denied scenarios

for each known risky alternate path:
    execute HTTP test and verify the correct blocking layer
~~~

Đây là pseudocode, không phải Java standalone. Các matcher nhận path variables và regex phức tạp có không gian path rất lớn; tự động generate tests chỉ là hỗ trợ, **không thể chứng minh toàn bộ URL vô hạn đều an toàn**.

## 11. Java 17 độc lập: mô hình catch-all và đường không dự kiến

Chương trình sau dùng **JDK 17 thuần** để mô phỏng cách phân loại policy. Nó không dùng Spring Security, không xử lý path normalization/URL encoding, không xác thực password và không tự mô phỏng HTTP 401/403. Mục đích: nhìn thấy vì sao cả API và ngoài API cần fallback deny.

Lưu file `UnexpectedPathPolicyDemo.java`:

~~~java
public class UnexpectedPathPolicyDemo {

    static String decide(String method, String path,
                         boolean authenticated,
                         String authority) {

        if ("GET".equals(method) &&
                "/public/ping".equals(path)) {
            return "ALLOW_PUBLIC";
        }

        if (path.startsWith("/api/")) {
            if (!authenticated) {
                return "NEED_AUTHENTICATION";
            }

            if ("GET".equals(method) &&
                    "/api/records/7".equals(path) &&
                    "RECORD_READ".equals(authority)) {
                return "ALLOW_READ";
            }

            if ("POST".equals(method) &&
                    "/api/records/7".equals(path) &&
                    "RECORD_WRITE".equals(authority)) {
                return "ALLOW_WRITE";
            }

            return "DENY_API_FALLBACK";
        }

        return "DENY_GLOBAL_FALLBACK";
    }

    public static void main(String[] args) {
        System.out.println(decide("GET", "/public/ping",
            false, ""));
        System.out.println(decide("GET", "/api/records/7",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/api/records/7/export",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/admin/diagnostics",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/api",
            true, "RECORD_READ"));
        System.out.println(decide("POST", "/api/records/7",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/api/records/7",
            false, ""));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac UnexpectedPathPolicyDemo.java
java UnexpectedPathPolicyDemo
~~~

Stdout chính xác:

~~~text
ALLOW_PUBLIC
ALLOW_READ
DENY_API_FALLBACK
DENY_GLOBAL_FALLBACK
DENY_GLOBAL_FALLBACK
DENY_API_FALLBACK
NEED_AUTHENTICATION
~~~

Ý nghĩa:

- Một path con không được phép ở API nhận `DENY_API_FALLBACK`.
- URL admin nằm ngoài /api được global fallback từ chối.
- Exact prefix `/api` được xếp vào global fallback trong **mô hình đơn giản này**. Spring matcher thật có thể match khác, nhưng vẫn phải deny nếu chính sách không allow.
- POST yêu cầu RECORD_WRITE; quyền READ không đủ.
- Anonymous không có quyền đi vào một endpoint bảo vệ.

Không sao chép `path.startsWith("/api/")` thành matcher HTTP production vì Spring MVC, Servlet request và HTTP normalization phức tạp hơn chuỗi Java thuần.

## 12. Những điểm dễ làm test sai

### 12.1. Chỉ thử URL được liệt kê trong config

Nếu kiểm tra GET /api/records/7 thành công, bạn chưa thử /api/records/7/export hay /admin. Cần ít nhất một nhóm **đường gần giống và ngoài namespace** có khả năng sinh ra từ việc phát triển thêm route.

### 12.2. Tin rằng denyAll trong API chain bao phủ toàn bộ app

`anyRequest().denyAll()` ở một chain chỉ áp dụng cho request được chain đó nhận. Cần catch-all hoặc tập chains bao phủ rõ ràng, rồi test ngoài API.

### 12.3. Cho toàn bộ namespace public để sửa một test

Thêm `requestMatchers("/api/**").permitAll()` làm legitimate route chạy được nhưng có thể mở hàng trăm endpoint khác. Chỉ khai báo route public chính xác; những route còn lại dùng role/authority/deny.

### 12.4. Dùng 404 để chứng minh rule đã chặn

404 có thể do MVC không có handler sau khi security cho qua. Positive + negative trên **cùng endpoint thật**, test authenticated unknown path và chain-level instrumentation cung cấp bằng chứng mạnh hơn.

### 12.5. Bỏ qua HTTP method

Nếu policy chỉ cho GET, đừng để matcher không ràng buộc method khiến POST/DELETE cũng được allow. Test methods khác với identity và CSRF hợp lệ khi cần.

### 12.6. Nhầm CSRF 403 với thiếu authority 403

POST thiếu CSRF bị từ chối trước; không chứng minh authorization rule. Test role với `with(csrf())` và test CSRF riêng.

### 12.7. Dùng MockMvc standalone

Standalone controller setup không có full SecurityFilterChain nếu không gắn. Test controller tốt nhưng không chứng minh route security. Dùng context-backed MockMvc với Spring Security hoặc HTTP integration.

### 12.8. Tự tin vào MockMvc cho encoded paths

MockHttpServletRequest không mô phỏng tất cả container, proxy, firewall và decoding nuances. Test raw paths trên server/proxy thật. Đừng khẳng định một 400 do firewall là 403 do authorization.

### 12.9. Quên thứ tự nhiều chains

Một catch-all chain đặt trước API chain có thể nhận hết request API; policy thực tế bị thay đổi. Dùng `@Order` rõ ràng và test chính URL API với user được/không được phép.

### 12.10. Quên security của error/forward dispatch

Forward tới route nhạy cảm hoặc handler ERROR có thể chịu rule/dispatch behavior riêng theo Servlet và Spring Security version. Kiểm tra dispatcher mapping, không blanket permitAll cho mọi forward chỉ vì một trang lỗi bị 403.

### 12.11. Test chỉ với superadmin

Một user có nhiều authority có thể không bộc lộ sự khác biệt giữa READ, WRITE hay tenant. Dùng identity tối thiểu và người dùng ngoài tenant khi nghiệp vụ yêu cầu.

### 12.12. Không kiểm tra những đường ngoài MVC

Static/CDN/file/Servlet riêng có thể không đi qua cùng security chain. Phải kiểm tra ở đúng tầng nhận request, không chỉ Spring MVC mappings.

### 12.13. Đồng nhất path authorization với object authorization

GET /api/records/7 được cho vì RECORD_READ không chứng minh user có quyền trên record 7. Khi record thuộc tenant khác, cần object-level check ở service/AuthorizationManager có dữ liệu tin cậy. Negative path và negative object tests bổ sung nhau.

### 12.14. Bỏ qua hồi quy sau nâng cấp

Spring Security, Spring Framework, servlet container và reverse proxy có thể đổi cách match/normalize path. Giữ negative suite trong CI và test production-like khi nâng version.

## 13. Quy trình kiểm chứng trên dự án thật

1. Kiểm kê những URL, methods, servlets và routes mà hạ tầng thực sự phục vụ.
2. Ghi chính sách công khai/đăng nhập/role/owner-tenant/deny cho từng nhóm.
3. Đối chiếu tất cả `SecurityFilterChain` và thứ tự `@Order` với URL thực.
4. Chọn public allowlist đủ hẹp, protected rules theo method và fallback deny-all.
5. Test một case positive cho mỗi protected route quan trọng.
6. Test anonymous và identity thiếu quyền trên cùng route.
7. Test method khác và đảm bảo CSRF không che mất điều kiện authorization.
8. Test paths sát ranh giới: prefix, suffix, trailing slash, segment con, exact namespace, legacy alias.
9. Test HTTP raw URL và reverse proxy rewriting trong môi trường gần production.
10. Xác định lớp nào trả 400/401/403/404/405; không dùng status lỗi chung làm bằng chứng.
11. Xây policy review gate cho route mới và giữ regression tests với bugs đã xảy ra.
12. Kiểm tra cả non-HTTP callers của service và object-level authorization.
13. Không log credentials/token/session ID trong test output hoặc debug traces.
14. Chỉ permit thêm những route đã được phân loại; không nới wildcard để “làm test xanh”.

### Checklist review nhanh

- [ ] Có fallback chain đúng phạm vi hoặc xác định rõ các URL intentionally unprotected.
- [ ] Mọi chain nhạy cảm đều có fallback rule và tests.
- [ ] Public allowlist không khớp trước protected rules do pattern quá rộng.
- [ ] HTTP methods được phân biệt.
- [ ] Có ít nhất một test allow và một test deny cho cùng endpoint thật.
- [ ] Có test anonymous và authenticated user không đủ authority.
- [ ] Có test unknown URL cả trong và ngoài API namespace.
- [ ] Có test /api exact prefix, route suffix và segment con.
- [ ] Có test POST với CSRF hợp lệ để kiểm tra role; CSRF được test riêng.
- [ ] Raw encoded paths được test qua server/proxy thật khi nằm trong threat model.
- [ ] Context path, servlet path và proxy forwarded headers được kiểm tra.
- [ ] Route inventory được review khi có controller/module mới.
- [ ] Object-level và service-level policies không bị bỏ sót.

## 14. Câu hỏi và bài tập

**Bài 1.** Chỉ có API chain `securityMatcher("/api/**")` với `anyRequest().denyAll()`. Một controller `GET /admin/export` đang hoạt động. Có chắc được Spring Security bảo vệ không?

**Đáp án:** Không. Nếu không có chain nào khác khớp /admin/export, Spring Security có thể không xử lý request. Cần fallback chain hoặc chain admin và test đường ngoài API.

**Bài 2.** `GET /api/unknown` trả 404. Có kết luận deny-all đang chạy không?

**Đáp án:** Không. Có thể Spring Security cho qua và MVC trả 404 do không có controller. Cần test cùng route thật với quyền đúng/sai và/hoặc xác minh chain/rule từ chối trước MVC.

**Bài 3.** `GET /api/records/7`: reader nhận 200, writer nhận 403. Điều này chứng minh gì?

**Đáp án:** Route thật có rule yêu cầu READ và phân biệt identity. Vẫn phải test URL gần giống và method khác để kiểm tra coverage.

**Bài 4.** Reader POST /api/records/7 thiếu CSRF trả 403. Điều đó có chứng minh thiếu RECORD_WRITE không?

**Đáp án:** Chưa. CsrfFilter có thể chặn trước. Gửi CSRF hợp lệ rồi test reader bị deny, writer được allow.

**Bài 5.** Đặt `/api/**.permitAll()` trước rule protected. Có vấn đề gì?

**Đáp án:** Public matcher rộng khớp trước khiến protected rule có thể không chạy. Đặt route public chính xác và rule protected phù hợp trước fallback deny.

**Bài 6.** HTTP GET /api/records/7 hợp lệ có đồng nghĩa POST cùng URL hợp lệ không?

**Đáp án:** Không. HTTP method là chiều phân quyền riêng; phải có rule WRITE và CSRF policy phù hợp.

**Bài 7.** MockMvc từ chối một path encoded, server production lại xử lý khác. Vì sao?

**Đáp án:** Container, proxy, firewall, servlet mapping và test request builder có normalization/encoding khác nhau. Cần integration test trên stack thực.

**Bài 8.** Vì sao phải test `/api` nếu chain viết `/api/**`?

**Đáp án:** Semantics exact namespace prefix có thể khác theo matcher. Catch-all đảm bảo nếu không vào API chain thì vẫn có rule từ chối. Không đoán sự tương đương.

**Bài 9.** Một route mới /api/records/7/export được thêm sau khi CI chạy. Làm sao tránh quên policy?

**Đáp án:** So sánh mapping inventory với policy manifest, yêu cầu review với route mới, thêm positive/negative tests và một ca outside allowlist cho export.

**Bài 10.** User có RECORD_READ và xem được record của tenant khác. Đây có phải chỉ là request-matching bug?

**Đáp án:** Không nhất thiết. Đây có thể là object-level authorization (IDOR/BOLA). Cần kiểm tra owner/tenant từ server data và service-level enforcement.

**Bài 11.** API dùng một matcher catch-all `permitAll()` trong chain chỉ để static resources tải được. Cách sửa đúng?

**Đáp án:** Xác định chính xác static paths public, đặt `permitAll()` cho chúng, giữ các đường khác protected hoặc deny. Không bypass toàn bộ FilterChainProxy nếu cần headers/security filters.

**Bài 12.** Request GET /api/records/7/export trả 403; có biết chính xác API chain hay fallback chain đã chặn không?

**Đáp án:** Chưa. HTTP status không nói chắc chain. Khi cần xác minh thứ tự chain, dùng test instrumentation hoặc logs an toàn để khẳng định request matcher/chains được gọi; các positive cases cũng giúp kiểm tra wiring.

## 15. Kết luận

Để phát hiện **khoảng trống bảo vệ do request matching**, không chỉ kiểm thử đường hợp lệ. Hãy luôn kiểm tra:

~~~text
Public routes được khai báo tường minh
+ Protected routes/methods có điều kiện quyền rõ
+ SecurityFilterChain coverage, gồm catch-all
+ Deny-by-default ở mọi phạm vi cần bảo vệ
+ Positive và negative identity tests
+ Negative path/method/alias tests
+ Real HTTP tests cho proxy, encoded path và context/servlet path
+ Regression gate khi route mới xuất hiện
+ Service/object-level authorization nơi cần thiết
~~~

**Ghi nhớ:** `anyRequest().denyAll()` chỉ bao phủ request đã **vào đúng SecurityFilterChain**; HTTP 404 vì không tìm thấy controller **không chứng minh** authorization đã chạy. Kết hợp positive tests, negative-path tests, kiểm thử filter chain thật và HTTP/proxy thực tế sẽ giúp phát hiện những đường phụ trước khi chúng trở thành lỗ hổng.