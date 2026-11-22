# Thử nghiệm yêu cầu có token đúng, token sai và thiếu token

> **Module:** Spring Security – fundamentals  
> **Nhóm kiến thức:** CSRF  
> **Trọng tâm:** Xây dựng và chạy ba tình huống kiểm thử **CSRF token hợp lệ**, **CSRF token không hợp lệ** và **request không gửi CSRF token**; chứng minh request ghi dữ liệu bị chặn trước khi vào controller khi token sai/thiếu. Ví dụ dùng Spring MVC/Servlet và Spring Security 6.5 với Java 17+.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích CSRF và lý do cookie phiên đăng nhập tự được browser gửi có thể trở thành rủi ro.
2. Phân biệt **token được server kỳ vọng** với **token client gửi lại**.
3. Thiết kế ba test case trên **cùng một HTTP method và cùng endpoint**, chỉ khác trạng thái CSRF token.
4. Dự đoán kết quả: token hợp lệ cho request đi tiếp; token sai và token thiếu bị từ chối (mặc định thường là **HTTP 403**).
5. Dùng Spring Security Test `csrf()`, `csrf().asHeader()` và `csrf().useInvalidToken()` trong `MockMvc`.
6. Kiểm tra **side effect có xảy ra hay không**, không chỉ khẳng định response status.
7. Thực hành với client HTTP: lấy token từ server, lưu cookie phiên, gửi POST đúng/sai/thiếu token trong cùng phiên.
8. Phân biệt lỗi CSRF với **401 chưa xác thực**, **403 thiếu quyền**, **session hết hạn**, **CORS**, lỗi validation và lỗi nghiệp vụ.
9. Hiểu giới hạn của các test: MockMvc helper không thay thế browser/integration test kiểm tra token gắn với session và chính sách cookie.

## 2. Vấn đề: có cookie đăng nhập vẫn chưa đủ cho POST an toàn

Giả sử Alice đã đăng nhập vào website thanh toán. Browser giữ session cookie:

~~~http
Cookie: JSESSIONID=opaque-session-id
~~~

Khi Alice thực hiện POST từ trang chính thức, browser thường tự đính kèm cookie theo chính sách cookie. Nhưng một website khác cũng có thể tìm cách khiến browser của Alice gửi request đến trang thanh toán. Nếu backend chỉ dựa vào cookie mà không kiểm tra nguồn gốc/CSRF token, hành động có thể bị thực hiện ngoài ý muốn của Alice.

**Cross-Site Request Forgery (CSRF)** là kiểu tấn công lợi dụng browser mang sẵn credentials theo cơ chế tự động (ví dụ session cookie). Attacker không nhất thiết cần biết session ID. Điều quan trọng là browser nạn nhân có thể **gửi request với credentials hợp lệ** dù hành động được khởi phát từ nguồn không đáng tin.

CSRF token là một trong những biện pháp phòng vệ. Server cung cấp một giá trị mà client chính thức có thể lấy và gửi lại trong request thay đổi trạng thái. Một site khác không thể tùy ý đọc token đó nếu các ranh giới same-origin/CORS và bảo vệ ứng dụng được cấu hình đúng.

### Ví dụ ý tưởng

~~~text
Alice đăng nhập trên shop.example.test
  |
  +-- Browser tự gửi Cookie phiên đến shop.example.test
  |
  +-- GET /transfer-form
  |      Server đưa CSRF token hợp lệ vào form
  |
  +-- POST /transfer
         Cookie: JSESSIONID=...
         _csrf=<token từ form>
         |
         v
      CsrfFilter:
         - kiểm tra request có cần CSRF không?
         - lấy token kỳ vọng từ repository
         - lấy token thực tế từ request
         - so sánh / xác thực
         - đúng -> vào controller
         - sai/thiếu -> từ chối
~~~

Không tự dựng chính sách “cứ có header Origin hoặc Referer là đủ” nếu chưa có threat model và thiết kế kiểm tra chặt chẽ. Token phù hợp, SameSite, Origin/Referer checks và các biện pháp khác có thể bổ trợ nhau.

## 3. Ba trường hợp cần thử nghiệm

Với cùng endpoint `POST /api/counter/increment` và cùng user đã xác thực, chỉ thay đổi phần CSRF:

| Ca kiểm thử | CSRF token trong request | Kết quả với bảo vệ CSRF mặc định | Controller có chạy? |
| --- | --- | --- | --- |
| **Token đúng** | Giá trị hợp lệ, khớp cơ chế repository/handler của phiên | Request **được qua CsrfFilter**; nếu authz/business hợp lệ thì **200** trong demo | **Có** |
| **Token sai** | Có token nhưng bị sửa, giả hoặc không khớp phiên | Thường **403 Forbidden** | **Không** |
| **Thiếu token** | Không có parameter/header CSRF | Thường **403 Forbidden** | **Không** |

**Quan trọng:** “Token đúng” chỉ là **điều kiện để đi tiếp**, không bảo đảm toàn bộ request sẽ nhận 200. Sau CsrfFilter, Spring Security còn kiểm tra user có đăng nhập/đủ quyền không; controller còn có thể trả 400, 404, 409, 500. Vì vậy nên thực hiện ba test chính với **cùng một user đã xác thực và cùng quyền**, để chỉ cô lập biến CSRF.

Tương tự, status 403 **không đủ để kết luận lỗi CSRF**: Spring Security cũng có thể trả 403 cho một người đã xác thực nhưng thiếu authority. Cần kiểm tra test setup, exception class/trace và điểm dừng của request.

## 4. CSRF token được tạo và đối chiếu thế nào?

Trong Servlet Spring Security, thành phần chính là `CsrfFilter`, phối hợp với:

- `CsrfTokenRepository`: tạo/lưu/tải token kỳ vọng. Với cấu hình mặc định, Spring Security thường dùng `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: đưa token ra request attributes và giải mã/đọc token mà client gửi.
- `XorCsrfTokenRequestAttributeHandler`: handler mặc định phổ biến trong Spring Security 6, hỗ trợ mã hóa/masking giá trị token đưa vào response để giảm nguy cơ BREACH.
- `AccessDeniedHandler`: xử lý khi CSRF token thiếu/sai, thường trả 403.

Quy trình ở mức khái niệm:

~~~text
Request POST
   |
   v
CsrfFilter
   |
   +-- Method có cần bảo vệ? (POST thường có)
   |
   +-- CsrfTokenRepository.load/generate expected token
   |
   +-- CsrfTokenRequestHandler.resolve actual token
   |
   +-- Kiểm tra actual token với expected token
          |
          +--- hợp lệ --> filter chain đi tiếp
          |
          +--- sai/thiếu --> từ chối, không gọi controller
~~~

Từ Spring Security 6, việc tải token có thể **deferred** (chỉ tải khi cần), và token có thể được trình bày ở dạng **XOR-masked**. Vì thế không được giả định token nhìn thấy trên HTML/JSON luôn trùng byte-for-byte với giá trị thô lưu trong session. Nếu tạo ứng dụng SPA nhận token từ cookie, cần đối chiếu phần hướng dẫn xử lý token cho SPA trong tài liệu phiên bản sử dụng; không đơn giản copy cấu hình thời Spring Security 5.

### Có thể gửi token ở đâu?

Khi backend dùng convention mặc định, Spring Security nhận token từ:

~~~http
POST /api/counter/increment HTTP/1.1
Cookie: JSESSIONID=...
X-CSRF-TOKEN: <token hợp lệ>
~~~

hoặc với HTML form:

~~~http
POST /api/counter/increment HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...

_csrf=<token hợp lệ>
~~~

Tên tham số mặc định thường là `_csrf`, tên header thường là `X-CSRF-TOKEN` (và một số tích hợp dùng `X-XSRF-TOKEN` theo handler/repository). **Tên chính xác lấy từ `CsrfToken.getHeaderName()` và `getParameterName()`** nếu ứng dụng đã tùy chỉnh.

Token không nên tự động được browser đính kèm cho mọi request từ mọi nguồn giống session cookie. Client chính thức phải lấy token qua trang/form hoặc endpoint CSRF hợp lệ rồi chủ động đặt vào header/parameter. Như vậy mới tạo được ranh giới chống CSRF.

## 5. HTTP methods nào mặc định cần token?

Với cấu hình mặc định:

| HTTP method | CSRF token thường bắt buộc? | Điều cần nhớ |
| --- | --- | --- |
| GET | Không | Phải dùng để đọc, không có side effect |
| HEAD | Không | Không dùng để sửa dữ liệu |
| OPTIONS | Không | Thường dùng preflight hoặc metadata |
| TRACE | Không | Thường nên hạn chế/không sử dụng |
| POST | **Có** | Tạo/ghi dữ liệu |
| PUT | **Có** | Thay thế/cập nhật dữ liệu |
| PATCH | **Có** | Cập nhật một phần |
| DELETE | **Có** | Xóa dữ liệu |

Các rule có thể thay đổi qua `csrf.requireCsrfProtectionMatcher(...)` hoặc `csrf.ignoringRequestMatchers(...)`, nhưng nên có lý do bảo mật cụ thể. **Không thực hiện chuyển tiền, xóa tài khoản hay tạo đơn hàng qua GET** rồi dựa vào việc GET không cần token. CSRF protection mặc định không sửa được lỗi thiết kế một GET có side effect.

## 6. Chuẩn bị demo Java 17 + Spring Boot

Ta xây ứng dụng đơn giản có counter trong bộ nhớ:

- `GET /api/csrf`: trả token do Spring Security tạo cho phiên hiện tại.
- `GET /api/counter`: đọc số hiện tại, không làm thay đổi state.
- `POST /api/counter/increment`: tăng counter một lần. Phải có user role `USER` và token CSRF hợp lệ.
- HTTP Basic được dùng để kiểm thử authentication rõ ràng trong curl. Ứng dụng giữ CSRF protection **đang bật**, vì mục tiêu bài là kiểm thử CSRF.

**Tại sao dùng HTTP Basic trong demo?** Dễ gửi username/password từ curl mà không phải tự xây form login. Một browser có thể tự phát lại Basic credentials đã cache, nên CSRF vẫn cần được đánh giá khi browser có khả năng gửi ambient credentials. Với API thuần server-to-server gửi bearer token thủ công, threat model có thể khác. Đừng biến demo Basic thành khuyến nghị cấu hình mọi API.

Môi trường: **JDK 17+**, **Maven 3.9+**, **Spring Boot 3.5.7 / Spring Security 6.5.x**, ứng dụng Servlet/Spring MVC.

### Cây dự án

~~~text
csrf-three-cases/
  pom.xml
  src/main/java/com/example/csrfcases/
    CsrfCasesApplication.java
    SecurityConfig.java
    CounterService.java
    CounterController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/csrfcases/
    CsrfCasesTests.java
~~~

### 6.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>csrf-three-cases</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
  </properties>

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

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 6.2. File CsrfCasesApplication.java

~~~java
package com.example.csrfcases;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfCasesApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfCasesApplication.class, args);
    }
}
~~~

### 6.3. File SecurityConfig.java

~~~java
package com.example.csrfcases;

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

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf", "/api/counter")
                    .authenticated()
                .requestMatchers("/api/counter/increment")
                    .hasRole("USER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build()
        );
    }
}
~~~

**Giải thích:**

- **CSRF đang bật.** Không dùng `csrf.disable()` để làm test “dễ pass”.
- Mỗi request tới `/api/counter/increment` cần role `USER`, *đồng thời* phải vượt qua `CsrfFilter`.
- `HttpBasic` được dùng để curl gửi credentials dễ dàng. Test với `MockMvc` có thể dùng `user(...)` để thiết lập identity test mà không kiểm tra password encoding.
- `UserDetailsService` in-memory và mật khẩu cố định chỉ phù hợp demo; sản phẩm thật dùng user store và secret management đáng tin.
- `anyRequest().denyAll()` nhằm chặn tất cả URL không khai báo, không biến endpoint test thành public write.
- Không có config tùy chỉnh `CsrfTokenRepository` hoặc `CsrfTokenRequestHandler`, nên ví dụ theo defaults của Spring Security phiên bản đã chọn.

### 6.4. File CounterService.java

~~~java
package com.example.csrfcases;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class CounterService {

    private final AtomicInteger count = new AtomicInteger();

    public int current() {
        return count.get();
    }

    public int increment() {
        return count.incrementAndGet();
    }
}
~~~

`AtomicInteger` chỉ là trạng thái in-memory để quan sát side effect. Trong hệ thống thật, thay bằng database/transaction và business authorization phù hợp. Tài liệu cố ý dùng một thao tác đơn giản để dễ chứng minh **POST bị từ chối sẽ không tăng counter**.

### 6.5. File CounterController.java

~~~java
package com.example.csrfcases;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class CounterController {

    private final CounterService service;

    public CounterController(CounterService service) {
        this.service = service;
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName()
        );

        if (token == null) {
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "CSRF token not available"
            );
        }

        // getToken() buộc giá trị token được lấy/sinh khi cần.
        // Endpoint chỉ dành cho user đã authenticated.
        return Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        );
    }

    @GetMapping("/counter")
    public Map<String, Integer> current() {
        return Map.of("count", service.current());
    }

    @PostMapping("/counter/increment")
    public Map<String, Integer> increment() {
        return Map.of("count", service.increment());
    }
}
~~~

**Điểm cần hiểu:**

- `CsrfToken.class.getName()` là một request attribute được Spring Security cung cấp cho handler mặc định. Gọi `getToken()` sẽ làm token deferred được đánh giá khi cần.
- `/api/csrf` trả token để **client cùng origin hoặc client HTTP thử nghiệm** gửi lại ở request tiếp. Không mở CORS tùy tiện cho domain lạ hoặc trả token trong logs.
- Với default `HttpSessionCsrfTokenRepository`, token gắn với phiên; client cần giữ cookie/session tương ứng khi gửi POST.
- Token trong response có thể được **XOR-masked**; hãy gửi lại nguyên giá trị server cung cấp, không tự giải mã hoặc hardcode.
- `GET /api/counter` không đổi state, còn `POST /api/counter/increment` tạo side effect rõ ràng.

### 6.6. File application.properties

~~~properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Tại localhost, cấu hình mẫu dùng HTTP để thực hành; khi triển khai thật cần **HTTPS**, cookie `Secure` và kiểm tra proxy, domain/path/SameSite policy. Bài này không yêu cầu tạo cookie repository riêng; nó giữ mặc định session-based.

## 7. Kiểm thử tự động bằng MockMvc

Spring Security Test có `SecurityMockMvcRequestPostProcessors.csrf`. Đây là cách chuẩn để kiểm thử CSRF của Servlet application mà không cần tự tạo token/cookie cho từng test.

### Ba helper chính

~~~java
// Token hợp lệ qua request parameter mặc định:
.with(csrf())

// Token hợp lệ qua HTTP header:
.with(csrf().asHeader())

// Cố ý gửi token không hợp lệ:
.with(csrf().useInvalidToken())
~~~

Đây là các fragment, không phải Java program độc lập. Chúng được đặt trong `MockMvcRequestBuilders.post(...)`.

### 7.1. File CsrfCasesTests.java

~~~java
package com.example.csrfcases;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfCasesTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    CounterService counter;

    @Test
    void correctTokenAsParameterAllowsMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(before + 1));

        assertEquals(before + 1, counter.current());
    }

    @Test
    void correctTokenAsHeaderAlsoAllowsMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER"))
                .with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(before + 1));

        assertEquals(before + 1, counter.current());
    }

    @Test
    void wrongTokenIsForbiddenWithoutMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.current());
    }

    @Test
    void missingTokenIsForbiddenWithoutMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER")))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.current());
    }

    @Test
    void safeGetDoesNotRequireCsrfToken() throws Exception {
        mvc.perform(get("/api/counter")
                .with(user("learner").roles("USER")))
            .andExpect(status().isOk());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() throws Exception {
        mvc.perform(post("/api/counter/increment")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validCsrfDoesNotGrantMissingRole() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("reader").roles("READER"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.current());
    }
}
~~~

### Giải thích logic test

**Test token đúng:** `.with(user("learner").roles("USER"))` cố định identity/authority. `.with(csrf())` đưa token hợp lệ. Request được phép gọi controller, counter tăng **đúng một đơn vị**.

**Test token sai:** vẫn cùng user và POST endpoint, nhưng token sai. Phải trả 403 và `counter.current()` **không đổi**.

**Test token thiếu:** vẫn user có role hợp lệ, nhưng không có parameter/header token. Phải trả 403 và counter **không đổi**.

**Test token qua header:** chứng minh tích hợp API request/header cũng có thể hợp lệ; không chỉ HTML form parameter.

**Test GET:** mặc định GET không cần CSRF, bởi vì GET không có side effect.

**Test thiếu authentication:** request có token đúng vẫn phải xác thực. Trong cấu hình HTTP Basic này, kỳ vọng 401. Điều đó chỉ ra CSRF **không phải login token**.

**Test thiếu authority:** user có token hợp lệ nhưng không có role `USER` thì vẫn nhận 403; không nên gọi đó là lỗi CSRF.

### Vì sao kiểm tra state quan trọng?

Một bài test chỉ có:

~~~java
.andExpect(status().isForbidden())
~~~

chưa chứng minh state không đổi. Ví dụ một endpoint bị viết sai có thể cập nhật database rồi mới trả 403 do logic khác. Với demo, khẳng định thêm `assertEquals(before, counter.current())` bảo đảm side effect không xảy ra. Với production nên kiểm tra repository row count, audit event, queue, outgoing HTTP call và transaction theo nghiệp vụ.

### Điều MockMvc helper *không* kiểm tra

`with(csrf())` là test helper tạo token hợp lệ và ghép vào request giả. Nó **không tự chứng minh** frontend browser lấy token đúng, cookie được lưu đúng, CORS/SameSite phù hợp hoặc session không đổi sau login. Vì thế cần test HTTP/browser thực ở phần sau.

`with(user(...))` cũng không xác minh password do HTTP Basic thực hiện; nó tạo user đã xác thực cho phép cô lập biến CSRF. Đây là chủ ý để ba case có điều kiện auth giống nhau. Muốn kiểm tra Basic credentials thật, dùng curl/integration test riêng.

### Chạy test

~~~bash
mvn clean test
~~~

**Kỳ vọng:** Toàn bộ test trong `CsrfCasesTests` pass khi cấu hình và môi trường tương thích. Dữ liệu counter dùng chung Spring context, nhưng mỗi test ghi nhận `before` nên **không phụ thuộc thứ tự thực thi** của JUnit (miễn không bật parallel execution làm thay đổi cùng counter đồng thời).

Đây là code giáo dục đã cung cấp đủ file/đường dẫn/import; nội dung bài **không khẳng định đã chạy Maven hoặc thấy BUILD SUCCESS**. Khi áp dụng vào dự án thật, cần chạy test với dependency/version chính xác và chỉnh lại các phần security customization có liên quan.

## 8. Kiểm thử HTTP thật với curl: đúng, sai, thiếu token

Phần này cho thấy CSRF token gắn với session thật, không chỉ MockMvc request postprocessor.

### 8.1. Khởi động

Trong terminal thứ nhất:

~~~bash
mvn spring-boot:run
~~~

Terminal thứ hai chạy lệnh. Cần `curl`; nếu muốn tách token từ JSON bằng shell, dùng thêm `jq`. Trên Windows PowerShell, dùng `curl.exe` thay vì alias `curl`, hoặc sử dụng DevTools/Postman để nhập token thủ công.

### 8.2. Lấy token và lưu cookie session

~~~bash
TOKEN=$(curl -fsS \
  -u learner:demo123 \
  -c cookies.txt \
  http://localhost:8080/api/csrf | jq -r '.token')
~~~

Giải thích:

- `-u learner:demo123` gửi HTTP Basic credentials cho request.
- `-c cookies.txt` lưu cookie được server trả, bao gồm session cookie nếu được tạo.
- Endpoint `/api/csrf` trả token; `jq -r '.token'` chỉ lấy chuỗi token, không in toàn response.
- Biến `TOKEN` chứa credential chống CSRF để gửi tiếp. Đừng đưa nội dung biến vào logs, ticket hoặc chat.
- Mỗi POST bên dưới đều cần **cùng cookie jar**; nếu bỏ `-b cookies.txt`, token có thể không khớp session.

Nếu muốn biết tên header do server quy định, JSON trả `headerName` và `parameterName`; mặc định ví dụ dùng `X-CSRF-TOKEN`.

### 8.3. Case 1 — Thiếu token

~~~bash
curl -i \
  -u learner:demo123 \
  -b cookies.txt \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Kỳ vọng:

~~~http
HTTP/1.1 403 Forbidden
~~~

Dù đã có credentials và cookie phiên, request **không chứa `_csrf` hoặc `X-CSRF-TOKEN`**, nên `CsrfFilter` chặn trước controller.

Đọc counter:

~~~bash
curl -fsS -u learner:demo123 \
  -b cookies.txt http://localhost:8080/api/counter
~~~

Giá trị counter dự kiến **không tăng** vì request trước bị từ chối. Nội dung JSON cụ thể phụ thuộc các request hợp lệ đã thực hiện từ trước.

### 8.4. Case 2 — Token sai

~~~bash
curl -i \
  -u learner:demo123 \
  -b cookies.txt \
  -H "X-CSRF-TOKEN: deliberately-invalid" \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Kỳ vọng:

~~~http
HTTP/1.1 403 Forbidden
~~~

Có header không có nghĩa token đúng. Với handler mặc định, token client gửi phải được resolve và xác minh theo repository/session. Một chuỗi tự nghĩ ra thường không hợp lệ, nên controller không chạy và counter không tăng.

Không test bằng cách sử dụng token thật của production. Chỉ dùng môi trường thử nghiệm có credentials test.

### 8.5. Case 3 — Token đúng

~~~bash
curl -i \
  -u learner:demo123 \
  -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body chứa `{"count":...}` với count đã tăng một đơn vị. Cookie jar và token phải thuộc cùng phiên hợp lệ. Nếu response là 403, cần kiểm tra token có phải từ session hiện hành không; đây không nhất thiết là lỗi code.

**Bảng tổng hợp HTTP test:**

| Ca | Credentials | Session cookie | CSRF header | Status kỳ vọng | Counter |
| --- | --- | --- | --- | --- | --- |
| Thiếu token | Hợp lệ | Cùng jar | Không có | 403 | Không đổi |
| Token sai | Hợp lệ | Cùng jar | Giá trị giả | 403 | Không đổi |
| Token đúng | Hợp lệ | Cùng jar | Token do server cấp | 200 | Tăng 1 |
| Có token, không auth | Không có | Tùy request | Token hợp lệ | Có thể 401 theo Basic config | Không đổi |
| Có token, thiếu role | User khác được xác thực | Cùng phiên tương ứng | Token hợp lệ | 403 | Không đổi |

Đối với những ca ngoài ba ca chính, HTTP status có thể thay đổi theo entry point/filter chain. Trong demo Basic-only, mục tiêu của ba ca chính là **cô lập CSRF**: credentials và quyền luôn hợp lệ.

### 8.6. Case bổ sung — Token của phiên A dùng cho phiên B

CSRF token mặc định gắn với server session. Thử hai cookie jars tách biệt:

~~~bash
TOKEN_A=$(curl -fsS -u learner:demo123 \
  -c session-a.txt \
  http://localhost:8080/api/csrf | jq -r '.token')

curl -fsS -u learner:demo123 \
  -c session-b.txt \
  http://localhost:8080/api/csrf > /dev/null

curl -i -u learner:demo123 \
  -b session-b.txt \
  -H "X-CSRF-TOKEN: $TOKEN_A" \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Kỳ vọng **403**, vì token A không phải token kỳ vọng của session B. Đảm bảo hai jars được tạo từ môi trường sạch, không vô tình gửi lại session cookie A khi khởi tạo B. Đây là kiểm thử đặc biệt hữu ích khi nghi frontend đang tái sử dụng CSRF token từ phiên đã hết hạn.

**Lưu ý:** Một số hệ thống có `CookieCsrfTokenRepository` hoặc request handler tùy chỉnh, nên cách binding token/session cần kiểm tra theo thiết kế thực. Không coi “mọi CSRF token trên mọi ứng dụng đều nằm trong HttpSession” là định luật.

## 9. Test với trình duyệt và DevTools

Nếu ứng dụng có HTML form, quy trình quan sát là:

1. Đăng nhập trên một browser profile và mở trang có form.
2. Xem Network → response HTML có hidden input `_csrf` hay không; nếu SPA, xem nơi frontend nhận token.
3. Gửi POST hợp lệ với token. Quan sát status và side effect.
4. Trong môi trường dev, thử bỏ hidden input/header rồi gửi lại. Kỳ vọng 403.
5. Thử thay token bằng chuỗi giả. Kỳ vọng 403.
6. Thử logout/login lại hoặc làm session hết hạn; lấy token mới theo cơ chế ứng dụng, rồi gửi POST. Token cũ có thể không còn hợp lệ.
7. Dùng profile/incognito khác để tránh hiểu nhầm cookie/session giữa các users.

**Không đánh đồng DevTools thấy cookie với token đã đúng.** Cookie `JSESSIONID` và CSRF token phục vụ mục đích khác nhau. Với `HttpOnly`, JavaScript không đọc session cookie trực tiếp nhưng browser vẫn tự gửi khi phù hợp. Token CSRF phải được client gửi theo quy tắc do backend thiết kế.

Không đưa ảnh chụp chứa token/session ID thật vào báo cáo công khai. Nếu cần chia sẻ lỗi, thay secret bằng placeholder.

## 10. Những nguyên nhân gây 403 ngoài CSRF

Một request POST nhận **403** có thể do:

- CSRF token thiếu hoặc sai;
- User đã xác thực nhưng không có `ROLE_USER`/authority cần thiết;
- Method-level security như `@PreAuthorize` từ chối;
- Policy tenant/owner/relation từ chối;
- Custom filter/gateway/WAF từ chối;
- Session/identity trở nên không hợp lệ, kết hợp exception handling riêng;
- CSP/CORS/error handling khác có thông báo ở frontend, không phải cùng nguyên nhân gốc.

Vì vậy một bài test tốt cần có **control variables**:

| Biến | Ba ca chính phải giữ thế nào? |
| --- | --- |
| Endpoint | Cùng `POST /api/counter/increment` |
| HTTP method | POST cho cả ba |
| Authentication | Cùng authenticated user |
| Authorities | Cùng `ROLE_USER` |
| Session | Cùng context/session khi test HTTP thực |
| Request body | Giống nhau; demo không cần body |
| CSRF token | Chỉ biến đổi đúng / sai / thiếu |
| Kết quả nghiệp vụ | Counter tăng chỉ ở case đúng |

Nếu test token sai nhưng đồng thời đổi username, session và endpoint, status 403 không đủ chứng minh phần nào đã bị từ chối.

### 401 và 403 cần hiểu đúng

- **401 Unauthorized:** request thiếu hoặc có credentials xác thực không hợp lệ, tùy HTTP authentication entry point.
- **403 Forbidden:** request bị từ chối; có thể do CSRF hoặc đủ identity nhưng thiếu quyền.
- Một request **vừa thiếu login vừa thiếu CSRF** có thể bị `CsrfFilter` từ chối trước khi Spring Security tới authentication step. Vì vậy thí nghiệm CSRF nên đặt sẵn user hợp lệ.
- Với form login, thiếu authentication thường dẫn tới **302 redirect** thay vì 401; không áp 401 của HTTP Basic cho mọi ứng dụng.

## 11. Token đúng nhưng vẫn thất bại: các tình huống quan trọng

### 11.1. Token thuộc session đã hết hạn

Client lấy token T lúc session S1 còn hiệu lực, sau đó S1 timeout và request mới không có session tương ứng. Server có token kỳ vọng khác hoặc chưa có token hợp lệ cho phiên mới; T không còn khớp.

**Cách xử lý:** frontend phải lấy token mới sau khi login/session thay đổi. Đừng lưu mã token cũ mãi trong localStorage rồi gắn vào mọi request.

### 11.2. Logout và đăng nhập lại

Spring Security có cơ chế xóa/reset CSRF token khi authentication success hoặc logout success. Với deferred tokens, frontend có thể cần chủ động tải token mới sau khi login/logout, nhất là SPA. Gửi token trước login vào phiên đã đổi có thể nhận 403.

**Cách xử lý:** thiết kế `/csrf` hoặc trình render form lấy token mới khi cần; test luồng login → lấy token mới → POST.

### 11.3. Xor-masked token và raw cookie token

Từ Spring Security 6, default `XorCsrfTokenRequestAttributeHandler` hỗ trợ BREACH protection bằng cách thêm randomness vào token trình cho client. Nếu dùng `CookieCsrfTokenRepository` trong SPA, JavaScript có thể đọc **plain value** từ cookie, trong khi handler mặc định kỳ vọng masked token theo luồng khác. Trường hợp này cần chiến lược `CsrfTokenRequestHandler` phù hợp tài liệu SPA, không chỉ đổi tên header.

Bài demo không dùng `CookieCsrfTokenRepository`: token lấy qua request attribute và trả trong JSON, sau đó gửi lại chính giá trị đó qua header.

### 11.4. AJAX quên header hoặc tên header khác

Frontend có thể đặt `X-XSRF-TOKEN` nhưng backend đang mong `X-CSRF-TOKEN`, hoặc body JSON chứa trường "_csrf" nhưng handler không tìm ở đó. Hãy kiểm tra `CsrfToken.getHeaderName()` và `getParameterName()`, cách frontend gửi request và request handler thực sự.

Không cố nhét token vào URL query string; URL dễ vào logs/history.

### 11.5. Cookie không đến server

Browser có thể không gửi session cookie do `SameSite`, `Secure`, `Domain`, `Path`, cross-site rules hoặc credential mode của `fetch`. Khi đó token đúng về mặt chuỗi vẫn không gắn với session kỳ vọng.

Cần debug phía client qua DevTools và server-side session correlation. Không log session IDs nguyên vẹn. Chỉ thêm CORS/`credentials: include` khi có kiến trúc cross-origin được thiết kế và kiểm soát; CORS không phải cơ chế thay thế CSRF.

### 11.6. Double-submit cookie hoặc custom repository

Một số hệ thống dùng pattern cookie + header với repository khác `HttpSessionCsrfTokenRepository`. Đòi hỏi chính xác phụ thuộc cách token được ký, gắn với session/identity và request handler. Không sao chép test giả định session-bound từ ứng dụng mặc định rồi kết luận repository custom sai.

## 12. CSRF token không phải authentication token

Một CSRF token hợp lệ **không phải username/password**, cũng không phải OAuth2 access token. Nó chứng minh request có token do ứng dụng cấp theo cơ chế chống CSRF, trong phạm vi session/context thích hợp; không tự cấp danh tính hay quyền.

Ví dụ:

~~~text
POST /api/counter/increment
  Authentication = anonymous
  CSRF token     = valid

Kết quả: không được phép chỉ vì token hợp lệ.
~~~

Tương tự:

~~~text
POST /api/counter/increment
  Authentication = user:reader
  Authority      = ROLE_READER
  CSRF token     = valid

Kết quả: vẫn không có ROLE_USER -> deny.
~~~

**Ba lớp kiểm tra khác nhau:**

1. Authentication: ai là caller?
2. CSRF protection: request thay đổi trạng thái có bằng chứng chống cross-site forgery hợp lệ?
3. Authorization: caller được phép thực hiện hành động này trên tài nguyên này không?

Có thể đặt thêm business validation và data-level authorization trong service. Không bỏ những lớp này chỉ vì test CSRF đã pass.

## 13. CSRF với REST APIs dùng bearer token

Không phải mọi API đều cần đúng một chính sách CSRF giống ứng dụng session-cookie:

- **Browser session/cookie authentication:** thường cần CSRF protection vì browser tự gửi cookie.
- **HTTP Basic được browser cache:** cần xem như credential có thể tự gửi trong browser, không tự miễn trừ CSRF.
- **Server-to-server client dùng Authorization bearer token do code chủ động gắn:** nếu không có ambient browser credentials và không tiếp nhận cookie auth, nhiều hệ thống cấu hình stateless và có thể không cần CSRF token cho API chain đó.
- **JWT để trong cookie:** mặc dù token là JWT, browser vẫn có thể tự gửi cookie; **vẫn phải đánh giá CSRF**.
- **Ứng dụng lai có cả cookie và bearer:** phải đánh giá từng `SecurityFilterChain`/endpoint, không disable CSRF toàn bộ chỉ vì một tập API dùng bearer.

Nếu quyết định bỏ CSRF cho một API chain, phải có căn cứ threat model, xác nhận client và cơ chế authentication không tự gửi credential cross-site, phân tách matcher rõ và có tests bảo vệ các đường browser còn lại.

## 14. Tạo checklist kiểm thử đầy đủ

Đối với một endpoint POST/PUT/PATCH/DELETE nhạy cảm, nên có ma trận:

| Test | Token | Authentication | Authorization | Mong đợi |
| --- | --- | --- | --- | --- |
| Valid request | Đúng | Đúng | Đủ quyền | Request qua CSRF, nghiệp vụ thành công |
| Missing token | Thiếu | Đúng | Đủ quyền | 403, không mutation |
| Invalid token | Sai | Đúng | Đủ quyền | 403, không mutation |
| Header token | Đúng qua header | Đúng | Đủ quyền | Thành công như parameter nếu được hỗ trợ |
| Safe GET | Không có | Đúng | Đủ quyền đọc | Được phép, không mutation |
| Missing authentication | Đúng | Thiếu | N/A | 401/redirect theo auth mechanism |
| Missing authority | Đúng | Đúng | Thiếu | 403 do authorization |
| Expired session | Token cũ | Identity/session không hợp lệ | N/A | Không được thực hiện mutation |
| Token from session B | Không khớp A | Đúng | Đủ quyền | Bị từ chối theo repository mặc định |
| Login/logout rotation | Token cũ | Tùy trường hợp | N/A | Client phải lấy token mới |
| Cross-origin request | Không được đọc token | Cookie theo policy | N/A | Không thể thành công chỉ nhờ ambient credentials |

**Điều kiện chấp nhận (acceptance criteria):** Không có thao tác ghi dữ liệu nào xảy ra trong request thiếu/sai CSRF token, dù credentials hợp lệ. Test phải khẳng định trạng thái database/service, không chỉ response code.

## 15. Java 17 thuần: tự kiểm tra kết quả mong đợi

Đây là mô hình học tập độc lập, không phải triển khai CSRF thật. Tạo file `CsrfCaseSimulation.java`:

~~~java
import java.util.Objects;

public class CsrfCaseSimulation {
    static boolean accepted(String expected, String received) {
        return received != null && Objects.equals(expected, received);
    }

    public static void main(String[] args) {
        String sessionAToken = "demo-token-a";
        String sessionBToken = "demo-token-b";

        System.out.println("correct=" +
            accepted(sessionAToken, "demo-token-a"));
        System.out.println("wrong=" +
            accepted(sessionAToken, "invalid-token"));
        System.out.println("missing=" +
            accepted(sessionAToken, null));
        System.out.println("other-session=" +
            accepted(sessionBToken, "demo-token-a"));
    }
}
~~~

Chạy:

~~~bash
javac CsrfCaseSimulation.java
java CsrfCaseSimulation
~~~

Stdout chính xác:

~~~text
correct=true
wrong=false
missing=false
other-session=false
~~~

**Đây chỉ là phép so sánh ý tưởng.** Ứng dụng thật phải tạo token ngẫu nhiên bằng cơ chế đã được kiểm định, quản lý repository và sử dụng request handler của Spring Security, bao gồm masking/deferred loading khi thích hợp. Không tạo token từ chuỗi hằng hoặc tự viết filter thay `CsrfFilter` cho production.

## 16. Các lỗi kiểm thử phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Test POST hợp lệ nhưng quên `.with(csrf())` | Nhận 403 dù controller đúng | Thêm token hợp lệ cho positive test |
| Dùng `.with(csrf())` ở mọi test, kể cả test thiếu token | Không còn test negative case | Với missing token, tuyệt đối không thêm csrf processor |
| Chỉ thay token mà đồng thời đổi user | Không cô lập CSRF | Giữ cùng principal/authority/endpoint |
| Test invalid token bằng giá trị từ session khác nhưng không kiểm soát session | Kết quả phụ thuộc repository | Dùng `csrf().useInvalidToken()` hoặc session-bound integration test có kiểm soát |
| Chỉ kiểm tra HTTP 403 | Có thể side effect đã xảy ra | Assert state không đổi |
| Đọc 403 rồi kết luận CSRF | Có thể là access denied do role/tenant | Kiểm tra filter/exception và test setup |
| Disable CSRF để test xanh | Phá mục tiêu security | Giữ CSRF và gửi token đúng |
| GET gây mutation nhưng không cần token | CSRF protection mặc định không bảo vệ GET | Thiết kế GET chỉ đọc |
| Đưa token vào query string | Dễ lộ trong logs/history | Header hoặc form parameter |
| Hardcode CSRF token cố định | Mất tính liên kết repository/session | Lấy token từ server |
| Dùng token của session trước khi login lại | Token có thể đã bị xóa/rotate | Lấy token mới |
| Dùng raw token khi handler mong masked token | Spring Security 6 có XOR/BREACH behavior | Theo tài liệu handler/SPA của version |
| Không gửi cookie jar với curl | Token không khớp session | `-c` khi lấy, `-b` khi POST |
| Cho rằng CORS thay CSRF | CORS điều khiển việc đọc response và một số preflight, không phải CSRF defense tổng quát | Dùng CSRF protection/threat model thích hợp |
| Cho rằng SameSite đủ mọi trường hợp | Same-site subdomains và browser behaviors cần xét | Defense in depth |
| Tắt CSRF cho mọi endpoints vì JWT | JWT trong cookie vẫn ambient | Đánh giá nơi token được lưu và gửi |
| In token/session ID ra logs để debug | Credential có thể lộ | Redaction, request IDs, telemetry an toàn |

## 17. Bài tập và câu hỏi tự kiểm tra

**Bài 1:** Vì sao request POST có `JSESSIONID` hợp lệ nhưng không có CSRF token vẫn có thể trả 403? Trình bày vai trò của `CsrfFilter`.

**Bài 2:** Trong ba test cùng user `ROLE_USER`, chỉ một request thành công. Hãy mô tả chính xác cách set `with(csrf())`, `with(csrf().useInvalidToken())` và request thiếu CSRF.

**Bài 3:** Nếu cả token đúng và token sai đều nhận 403, bạn cần kiểm tra những gì trước khi kết luận CSRF config hỏng?

**Bài 4:** Tại sao phải assert counter/database không đổi ở hai ca sai/thiếu token?

**Bài 5:** Sau login, frontend dùng lại CSRF token đã lấy trước login và nhận 403. Nêu ảnh hưởng của `CsrfAuthenticationStrategy` và deferred token, và cách khắc phục.

**Bài 6:** Một user thiếu `ROLE_USER` gửi POST có CSRF token hợp lệ. Kết quả đúng là gì? Vì sao valid token không thay được authorization?

**Bài 7:** API dùng JWT trong `HttpOnly` cookie. Có nên tắt CSRF chỉ vì “đang dùng JWT” không? Giải thích.

**Bài 8:** Cho hai cookie jars A/B, token của A được dùng với B. Trong demo session-based, server phải làm gì? Vì sao?

**Bài 9:** Tại sao GET không cần token theo mặc định, nhưng GET lại không được thực hiện xóa dữ liệu?

**Bài 10:** So sánh lợi ích và giới hạn của MockMvc CSRF helpers so với curl/browser integration test.

### Gợi ý đáp án

1. Cookie chỉ chứng minh session/authentication; CSRF token là bằng chứng riêng chống request bị ép gửi cross-site.
2. Valid: `.with(csrf())`; invalid: `.with(csrf().useInvalidToken())`; missing: không có `csrf()`.
3. Authentication, authority, session, method/path, header/parameter name, repository, token lifecycle và exception source.
4. Status 403 chưa tự chứng minh mutation không xảy ra.
5. Token cũ có thể bị xóa/rotate sau authentication; cần lấy token mới từ form/endpoint sau login.
6. 403 do thiếu quyền; CSRF token không cấp quyền `ROLE_USER`.
7. Không. Browser tự gửi cookie dù chứa JWT; phải đánh giá CSRF.
8. Từ chối token không khớp session/repository, không mutation.
9. GET phải là safe/read-only; nếu dùng để ghi sẽ mở lỗ hổng CSRF và vi phạm ngữ nghĩa HTTP.
10. MockMvc cô lập/filter nhanh; HTTP/browser test còn chứng minh cookie jar, CSRF token delivery, session continuity và browser behavior.

## 18. Tổng kết

**Thử nghiệm CSRF tốt nhất bắt đầu bằng ba request giống nhau về user, quyền, method, endpoint và session; chỉ khác token: đúng, sai, thiếu.**

- **Token đúng:** được qua `CsrfFilter`; nếu các lớp auth/authz/business hợp lệ, thao tác ghi dữ liệu diễn ra.
- **Token sai:** thường **403**, controller không chạy, state không đổi.
- **Token thiếu:** thường **403**, controller không chạy, state không đổi.

Dùng `MockMvc` để cô lập logic bảo vệ của Spring Security và **test HTTP thực** để đảm bảo frontend/cookie/session/token thực sự kết nối đúng. CSRF token chỉ là một lớp bảo vệ, **không thay thế xác thực hay phân quyền**.

### Tài liệu chính thức

- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MDN — Cross-Site Request Forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
