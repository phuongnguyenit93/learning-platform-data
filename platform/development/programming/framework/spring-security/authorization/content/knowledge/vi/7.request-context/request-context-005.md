# Phân biệt lỗi CSRF với lỗi thiếu quyền trong Spring Security

> **Ngữ cảnh:** Spring Security Servlet, Spring MVC và HTTP request. Bài học giúp phân biệt **403 do CSRF token thiếu/sai** với **403 do authorization thiếu quyền**, đồng thời lý giải **401 do chưa xác thực**, cách xác định filter gây chặn và cách viết kiểm thử có thể chứng minh nguyên nhân. Ví dụ sử dụng Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x.

## 1. Cùng là HTTP 403, vì sao nguyên nhân có thể khác hẳn?

Xem ba request tới cùng endpoint `POST /api/docs`:

| Request | Danh tính / quyền | CSRF token | Kết quả dự kiến | Nguyên nhân |
| --- | --- | --- | --- | --- |
| A | Bob đã xác thực, có `docs:write` | **Thiếu** | **403** | Bị `CsrfFilter` chặn trước |
| B | Alice đã xác thực, chỉ có `docs:read` | **Hợp lệ** | **403** | Bị `AuthorizationFilter` từ chối |
| C | Bob đã xác thực, có `docs:write` | **Hợp lệ** | **201** | Qua được cả CSRF và authorization |

Chỉ nhìn `403 Forbidden` ở hai hàng đầu là **không đủ** để suy ra lỗi quyền. Ở A, quyền đã cấp đúng nhưng request không vượt qua lớp bảo vệ chống **Cross-Site Request Forgery**. Ở B, request đã vượt qua CSRF nhưng không có authority cần thiết.

Trong HTTP Basic của ứng dụng mẫu, khi không gửi credential nhưng có CSRF token hợp lệ, request tới endpoint được bảo vệ thường bị trả **401 Unauthorized**. Tuy nhiên, nếu **vừa không đăng nhập vừa thiếu CSRF token** trên POST, `CsrfFilter` có thể chặn trước khi Spring Security xử lý xác thực và trả **403**. Do đó không thể suy luận “403 nghĩa là đã đăng nhập”.

**Ba câu hỏi chẩn đoán cần đặt ngay:**

1. Request dùng **GET/HEAD/OPTIONS/TRACE** hay **POST/PUT/PATCH/DELETE**?
2. Có CSRF protection được bật cho request đó không, và token có đúng với phiên/ngữ cảnh hiện tại không?
3. Nếu CSRF đã qua, người gọi có được xác thực và có đúng role/authority mà rule HTTP yêu cầu không?

## 2. CSRF và authorization bảo vệ hai việc khác nhau

### 2.1. CSRF chống hành động giả mạo từ một trang khác

Trong tấn công CSRF, nạn nhân đã đăng nhập vào website A. Kẻ tấn công dụ trình duyệt gửi một request thay đổi dữ liệu tới A từ website B. Trình duyệt có thể **tự đính kèm cookie phiên** (hoặc một số credential tự gửi khác) nên máy chủ A nhìn thấy phiên hợp lệ, dù nạn nhân **không chủ động yêu cầu thao tác đó**.

Ví dụ, nếu website ngân hàng cho đổi thông tin qua POST và chỉ kiểm cookie đăng nhập, một trang độc hại có thể cố tạo form gửi POST thay mặt nạn nhân. CSRF token là một tín hiệu bổ sung mà trang của kẻ tấn công không dễ có được nếu server, browser và client cấu hình đúng.

**CSRF token không phải role, permission hay access token.** Nó nhằm chứng minh rằng request không chỉ dựa vào một credential tự động đính kèm. CSRF protection không quyết định Alice có được ghi tài liệu 42 hay không.

### 2.2. Authorization kiểm tra chủ thể được làm hành động gì

Authorization là câu hỏi: danh tính được xác thực này có `docs:write`, `ROLE_ADMIN`, đúng tenant và quyền đối với tài nguyên cụ thể hay không?

Ví dụ:

~~~java
// Fragment trong authorizeHttpRequests:
.requestMatchers(HttpMethod.POST, "/api/docs")
    .hasAuthority("docs:write")
~~~

Matcher nhận diện **POST tạo tài liệu**; policy kiểm tra authority literal `docs:write`. Rule này **không** tự cấp CSRF token và cũng không thay thế `CsrfFilter`.

### 2.3. Ma trận hai lớp bảo vệ

| CSRF gate (khi áp dụng) | Authentication/authorization | Cho request tiếp tục? |
| --- | --- | --- |
| Fail | Chưa cần xét hoặc chưa được xét | **Không** |
| Pass | Chưa xác thực khi cần đăng nhập | **Không** (HTTP Basic thường 401) |
| Pass | Đã xác thực nhưng thiếu quyền | **Không** (thường 403) |
| Pass | Đã xác thực và đủ quyền | **Có**, sau đó controller/service vẫn có thể chặn theo nghiệp vụ |

CSRF là **điều kiện cần trong phạm vi áp dụng**, không phải điều kiện đủ để cấp quyền. Tương tự, có đủ quyền không cho phép bỏ qua CSRF khi ứng dụng đã bật lớp bảo vệ này.

## 3. Luồng filter: vì sao request có thể bị chặn trước khi kiểm quyền?

Với một `SecurityFilterChain` Servlet có bật CSRF, HTTP Basic và `authorizeHttpRequests`, tài liệu Spring Security mô tả thứ tự khái niệm:

~~~text
HTTP request
   |
   v
CsrfFilter
   |-- Method/URL không cần CSRF -> đi tiếp
   |-- Cần CSRF + thiếu/sai token
   |       -> AccessDeniedHandler -> thường 403; DỪNG
   |-- Cần CSRF + token hợp lệ -> đi tiếp
   |
   v
BasicAuthenticationFilter (hoặc filter xác thực phù hợp)
   |-- Credential thiếu/sai -> entry point/challenge tùy cấu hình
   |-- Xác thực thành công -> Authentication
   |
   v
AuthorizationFilter
   |-- Rule có quyền -> controller/service
   |-- Rule từ chối -> AccessDeniedException -> 403
   |                      (hoặc entry point nếu anonymous)
   v
Controller / method security / domain policy
~~~

Sơ đồ cố ý chỉ nêu các filter liên quan và **không** phải danh sách đầy đủ. Thứ tự thực tế có thể có nhiều filter khác, nhiều `SecurityFilterChain` và customizations.

**Chi tiết quan trọng:**

- `CsrfFilter` kiểm tra token của request khi CSRF bắt buộc; nếu không hợp lệ, nó có thể trực tiếp giao `AccessDeniedException` cho **`AccessDeniedHandler`** và kết thúc chain.
- Các exception CSRF thường gặp là `MissingCsrfTokenException` và `InvalidCsrfTokenException`, đều thuộc nhóm từ chối truy cập. Tên exception thực tế có thể phụ thuộc trạng thái token lưu trữ và token client; **không luôn có ánh xạ một-một** giữa “header bị thiếu” và tên exception.
- Ở `AuthorizationFilter`, kết quả thiếu quyền có thể dẫn tới `AccessDeniedException`; `ExceptionTranslationFilter` tham gia xử lý/định tuyến tới entry point hoặc denied handler.
- Vì hai nhánh đều có thể kết thúc bằng status **403**, response chung có thể không phơi bày nguyên nhân để tránh lộ thông tin bảo mật.

Khi debug, điều có ý nghĩa nhất là **filter nào từ chối**, không chỉ có mã HTTP nào được trả.

## 4. CSRF mặc định áp dụng cho HTTP method nào?

Spring Security Servlet thông thường bật CSRF protection mặc định và yêu cầu token cho các method **không an toàn** (*unsafe methods*).

| HTTP method | Cần CSRF token theo cấu hình mặc định? | Ghi chú |
| --- | --- | --- |
| `GET` | Không | Phải được thiết kế chỉ đọc, không gây side effect |
| `HEAD` | Không | Semantics như GET nhưng không trả body |
| `OPTIONS` | Không | Thường liên quan CORS preflight |
| `TRACE` | Không | Được xếp vào nhóm safe theo matcher mặc định, nhưng thường không nên mở TRACE tùy tiện |
| `POST` | **Có** | Thường tạo tài nguyên, gửi form hoặc thao tác |
| `PUT` | **Có** | Thường thay thế tài nguyên |
| `PATCH` | **Có** | Thường cập nhật một phần |
| `DELETE` | **Có** | Thường xóa tài nguyên |

Đây là **mặc định**, có thể khác nếu code cấu hình `requireCsrfProtectionMatcher`, `ignoringRequestMatchers`, nhiều chain hoặc vô hiệu hóa CSRF.

Hai trường hợp rất dễ nhầm:

1. `POST /public/feedback` được cấu hình `permitAll()` **vẫn có thể cần CSRF token**, vì `permitAll` thuộc authorization, không tự vô hiệu hóa `CsrfFilter`.
2. `GET /api/docs` với Alice có quyền đọc **không cần CSRF token** theo mặc định. Gửi một CSRF header sai ở GET thường không gây từ chối CSRF vì filter không yêu cầu kiểm token cho request đó.

Nếu GET thực tế sửa trạng thái, đó là **lỗi thiết kế HTTP**. Không được viện lý do “GET không cần CSRF” để tạo thao tác xóa/chuyển tiền trên GET. Cần đổi sang method thích hợp và bảo vệ tương ứng.

## 5. Token được lưu và gửi ở đâu?

Trong Spring Security 6.5, CSRF protection có các thành phần:

- `CsrfTokenRepository`: nơi lưu/khôi phục token được mong đợi. Mặc định Servlet sử dụng `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: cách đưa token cho view/request và cách trích giá trị do client gửi.
- `CsrfFilter`: quyết định request nào cần kiểm token và so sánh token client với token dự kiến.
- `AccessDeniedHandler`: xử lý khi token thiếu/sai và không cho request tiếp tục.

Một số hình thức client:

| Kiểu client | Cách thường dùng |
| --- | --- |
| Server-rendered HTML form | Thêm hidden input `_csrf` (thường được view/framework hỗ trợ) |
| AJAX/SPA | Gửi token qua header, thường `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy cấu hình |
| Cookie-based CSRF repository | `CookieCsrfTokenRepository` có quy ước cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN` |
| `MockMvc` test | `.with(csrf())` hoặc `.with(csrf().asHeader())` sinh token hợp lệ cho test |

**Không thể gửi một chuỗi tùy tiện** như `X-CSRF-TOKEN: test` rồi coi là token hợp lệ. Giá trị client phải được đối chiếu với token server dự kiến **trong đúng ngữ cảnh**. Với session repository, cookie phiên và token phải phù hợp nhau.

Trong Spring Security 6, cơ chế token hoãn tải (*deferred CSRF token*) và bảo vệ BREACH bằng giá trị có yếu tố ngẫu nhiên được áp dụng mặc định. SPA dùng cookie, đọc token từ JavaScript và gửi lại header có thể cần cấu hình request handler phù hợp; không chỉ thêm `CookieCsrfTokenRepository` rồi giả định mọi luồng login/logout/AJAX hoạt động.

**Sau login/logout**, token cũ có thể bị xóa hoặc cần làm mới vì chiến lược CSRF thay đổi theo vòng đời xác thực. Nếu frontend giữ token cũ và POST lại, có thể nhận 403 CSRF **dù tài khoản đang đăng nhập và có đủ quyền**.

## 6. Ma trận chẩn đoán: cùng endpoint, đổi từng biến

Giả sử:

- `POST /api/docs` yêu cầu `hasAuthority("docs:write")`;
- CSRF bật cho POST;
- Bob có `docs:write`;
- Alice chỉ có `docs:read`;
- Carol chỉ có `ROLE_ADMIN`;
- Dave có `ROLE_USER`;
- HTTP Basic được dùng cho ví dụ.

| Tình huống | Credential | CSRF | Authority | Kết quả dự kiến | Lý do nổi bật |
| --- | --- | --- | --- | --- | --- |
| Bob tạo tài liệu | Hợp lệ | Hợp lệ | Có `docs:write` | **201** | Đủ cả hai điều kiện |
| Bob quên CSRF | Hợp lệ | Thiếu | Có `docs:write` | **403** | CSRF trước authorization |
| Bob gửi CSRF sai | Hợp lệ | Sai | Có `docs:write` | **403** | CSRF thất bại |
| Alice tạo tài liệu | Hợp lệ | Hợp lệ | Thiếu `docs:write` | **403** | Authorization từ chối |
| Alice quên CSRF | Hợp lệ | Thiếu | Thiếu quyền | **403** | Không thể dùng status để biết thiếu cả hai; CSRF chặn trước |
| Carol có role admin | Hợp lệ | Hợp lệ | Chỉ `ROLE_ADMIN` | **403** | Role admin không tự cấp permission literal |
| Anonymous có CSRF | Không có | Hợp lệ | Không | **401** | Sau khi qua CSRF, yêu cầu bảo vệ cần authentication |
| Anonymous thiếu CSRF | Không có | Thiếu | Không | **403** | CSRF có thể chặn trước HTTP Basic |

**Quy tắc kiểm chứng khoa học:** để chứng minh một lỗi là **thiếu quyền**, giữ các yếu tố khác hợp lệ (đặc biệt CSRF) rồi thay đổi **chỉ authority**. Để chứng minh lỗi do **CSRF**, giữ danh tính có đủ quyền rồi thay đổi **chỉ token**.

Khi cả quyền và CSRF đều sai, status đơn lẻ không đủ để chẩn đoán nguyên nhân gốc; cần tách biến trong test hoặc dùng tracing/log được phép.

## 7. Java 17 thuần: mô hình hóa thứ tự chặn

Đây là một ví dụ **độc lập**, không dùng Spring Security. Mục đích là phân biệt **lớp quyết định**: một 403 ở bước 1 khác một 403 ở bước 3.

Tạo tệp **`CsrfVsAuthDemo.java`**:

~~~java
public class CsrfVsAuthDemo {

    static String decide(
            boolean csrfRequired,
            boolean validCsrf,
            boolean authenticated,
            boolean canWrite
    ) {
        if (csrfRequired && !validCsrf) {
            return "403 CSRF";
        }
        if (!authenticated) {
            return "401 AUTHENTICATION";
        }
        if (!canWrite) {
            return "403 AUTHORIZATION";
        }
        return "201 CREATED";
    }

    public static void main(String[] args) {
        System.out.println("Bob valid: "
            + decide(true, true, true, true));

        System.out.println("Bob missing token: "
            + decide(true, false, true, true));

        System.out.println("Alice valid token: "
            + decide(true, true, true, false));

        System.out.println("Alice missing token: "
            + decide(true, false, true, false));

        System.out.println("Anonymous valid token: "
            + decide(true, true, false, false));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac CsrfVsAuthDemo.java
java CsrfVsAuthDemo
~~~

**Stdout chính xác:**

~~~text
Bob valid: 201 CREATED
Bob missing token: 403 CSRF
Alice valid token: 403 AUTHORIZATION
Alice missing token: 403 CSRF
Anonymous valid token: 401 AUTHENTICATION
~~~

Chương trình giả lập một pipeline tối giản và cố ý ghi nguyên nhân vào **chuỗi output nội bộ**. Spring Security thực không cam kết trả chuỗi `403 CSRF` hay `403 AUTHORIZATION` trong HTTP response; nó chỉ có thể trả cùng status 403. Khi có thêm filter, session, token repository hoặc chính sách ngoại lệ tùy chỉnh, thứ tự và response cụ thể phải kiểm thử theo ứng dụng.

## 8. Ví dụ Spring Boot: một API, hai kiểu 403

### 8.1. Tạo dự án

Tạo project Maven dùng **Spring Boot 3.5.x**, Java 17+ và dependencies:

- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-test` ở test scope;
- `spring-security-test` ở test scope.

Sử dụng một `SecurityFilterChain` cho toàn bộ demo để dễ chỉ ra filter gây lỗi. HTTP Basic phục vụ test credential; môi trường thật phải dùng **HTTPS**. Không dùng mật khẩu demo trong production.

### 8.2. Mã ứng dụng hoàn chỉnh

Tạo tệp **`src/main/java/com/example/csrfdiag/CsrfDiagnosisApplication.java`**:

~~~java
package com.example.csrfdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfDiagnosisApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfDiagnosisApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/info").permitAll()
                .requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/docs")
                    .hasAuthority("docs:read")
                .requestMatchers(HttpMethod.POST, "/api/docs")
                    .hasAuthority("docs:write")
                .requestMatchers(HttpMethod.POST, "/api/admin/review")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("docs:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("docs:read", "docs:write")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();

        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    @RestController
    static class Api {

        @GetMapping("/public/info")
        String publicInfo() {
            return "public info";
        }

        // Dù permitAll, POST vẫn chịu kiểm tra CSRF.
        @PostMapping("/public/submit")
        String publicSubmit() {
            return "public submitted";
        }

        @GetMapping("/api/docs")
        String docs() {
            return "docs";
        }

        @PostMapping("/api/docs")
        ResponseEntity<String> createDoc() {
            // Demo không ghi database.
            return ResponseEntity.status(HttpStatus.CREATED)
                .body("doc created");
        }

        @PostMapping("/api/admin/review")
        String review() {
            return "reviewed";
        }

        @GetMapping("/api/profile")
        String profile(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/api/unlisted")
        String unlisted() {
            return "must not be reached";
        }
    }
}
~~~

**Giải thích cấu hình:**

1. `.csrf(Customizer.withDefaults())` bật rõ cơ chế CSRF mặc định. Trong cấu hình web Servlet này, CSRF vốn đã bật nếu không bị tắt/chỉnh khác.
2. `GET /public/info` là endpoint công khai, không cần CSRF vì GET mặc định được xem là safe.
3. `POST /public/submit` được `permitAll()` nhưng **vẫn cần CSRF token hợp lệ**: đây là ca phân biệt quan trọng.
4. `GET /api/docs` cần authority `docs:read`, không cần CSRF token mặc định.
5. `POST /api/docs` cần **cả CSRF hợp lệ lẫn `docs:write`**.
6. `POST /api/admin/review` cần CSRF và `ROLE_ADMIN` do `hasRole("ADMIN")`.
7. `GET /api/profile` cần đăng nhập nhưng không thêm permission nghiệp vụ khác.
8. `anyRequest().denyAll()` chặn route chưa liệt kê, bao gồm `GET /api/unlisted` dù controller tồn tại.
9. User builder `roles("ADMIN")` cấp `ROLE_ADMIN` cho Carol; điều đó **không** cấp `docs:write`.
10. Tất cả POST chỉ trả phản hồi demo, không ghi dữ liệu. Nếu controller có DB, vẫn cần kiểm tra authorization theo tài nguyên, input validation, transaction và audit phù hợp.

### 8.3. Kỳ vọng khi gửi request GET

Chạy bằng Maven wrapper:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Khi server mở `http://localhost:8080`:

~~~bash
curl -i http://localhost:8080/public/info
curl -i http://localhost:8080/api/docs
curl -i -u alice:demo123 http://localhost:8080/api/docs
curl -i -u dave:demo000 http://localhost:8080/api/docs
curl -i -u dave:demo000 http://localhost:8080/api/profile
curl -i -u bob:demo456 http://localhost:8080/api/unlisted
~~~

| Request | Kỳ vọng |
| --- | --- |
| Public GET, anonymous | `200`, body `public info` |
| Docs GET, anonymous | `401` (HTTP Basic) |
| Docs GET, Alice | `200`, body `docs` |
| Docs GET, Dave | `403` do thiếu `docs:read`, **không phải CSRF** |
| Profile GET, Dave | `200`, body `dave` |
| Unlisted GET, Bob | `403` do `denyAll()`, **không phải CSRF** |

**GET cũng có thể bị 403 vì thiếu quyền** trong khi CSRF mặc định không kiểm tra nó. Vì vậy, “mọi 403 là CSRF” cũng sai như “mọi 403 là role”.

### 8.4. Vì sao lệnh curl POST đơn giản chưa chứng minh quyền?

~~~bash
curl -i -u bob:demo456 -X POST http://localhost:8080/api/docs
~~~

Request trên **không có CSRF token**, nên mặc dù Bob có `docs:write`, kết quả thông thường là **403 từ CsrfFilter**. Không được khắc phục bằng cách cấp thêm `ROLE_ADMIN` hoặc `docs:write` cho Bob: anh ta đã có quyền cần thiết!

Với repository mặc định lưu token trong session và cơ chế bảo vệ token của Spring Security 6, việc dùng curl phải đi theo quy trình client/server lấy token, giữ session/cookie tương ứng và gửi token đúng cách. Không thể kết luận lệnh `curl -u ... -X POST` là test authorization hoàn chỉnh nếu thiếu CSRF.

Để **tách riêng các biến**, phần tiếp theo dùng `MockMvc` và `spring-security-test`. Helper `csrf()` cấp token hợp lệ trong test, không phải cách bypass CSRF trong ứng dụng thật.

## 9. Spring Security Test: chứng minh nguyên nhân bằng thí nghiệm đối chứng

### 9.1. Dependency test

Trong `pom.xml`, đảm bảo có:

~~~xml
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
~~~

Các phần tử trên thuộc `<dependencies>` trong POM. Nếu `spring-boot-starter-test` đã có, không thêm trùng. Spring Boot parent/BOM nên quản lý phiên bản của các artifact liên quan.

### 9.2. Test class hoàn chỉnh

Tạo tệp **`src/test/java/com/example/csrfdiag/CsrfDiagnosisTests.java`**:

~~~java
package com.example.csrfdiag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDiagnosisTests {

    @Autowired
    MockMvc mvc;

    @Test
    void writerWithValidCsrfCanCreate() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("doc created"));
    }

    @Test
    void sameWriterWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void sameWriterWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithValidCsrfStillCannotCreate() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("alice", "demo123"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWithValidCsrfNeedsAuthentication() throws Exception {
        mvc.perform(post("/api/docs")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousWithoutCsrfCanGetCsrfForbiddenFirst() throws Exception {
        mvc.perform(post("/api/docs"))
            .andExpect(status().isForbidden());
    }

    @Test
    void permitAllDoesNotSkipCsrf() throws Exception {
        mvc.perform(post("/public/submit"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/public/submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("public submitted"));
    }

    @Test
    void correctAuthorityAndInvalidCsrfHeaderStillFail()
            throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf().asHeader().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfHeaderAndCorrectAuthoritySucceed()
            throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf().asHeader()))
            .andExpect(status().isCreated());
    }

    @Test
    void getDoesNotNeedCsrfButStillNeedsReadAuthority()
            throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/docs")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isForbidden());
    }

    @Test
    void badPasswordWithValidCsrfIsUnauthorized() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "wrong-password"))
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRoleDoesNotImplyDocsWritePermission()
            throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("carol", "demo789"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/admin/review")
                .with(httpBasic("carol", "demo789"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("reviewed"));
    }

    @ParameterizedTest
    @CsvSource({
        // principal,password,method,path,expected HTTP status
        "anonymous,none,GET,/public/info,200",
        "anonymous,none,GET,/api/docs,401",
        "anonymous,none,POST,/public/submit,200",
        "anonymous,none,POST,/api/docs,401",
        "alice,demo123,GET,/api/docs,200",
        "alice,demo123,POST,/api/docs,403",
        "bob,demo456,GET,/api/docs,200",
        "bob,demo456,POST,/api/docs,201",
        "carol,demo789,GET,/api/docs,403",
        "carol,demo789,POST,/api/docs,403",
        "carol,demo789,POST,/api/admin/review,200",
        "dave,demo000,GET,/api/profile,200",
        "dave,demo000,GET,/api/docs,403",
        "dave,demo000,POST,/api/docs,403",
        "bob,demo456,GET,/api/unlisted,403"
    })
    void expectedAuthorizationWhenCsrfIsValid(
            String principal, String password,
            String method, String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder request =
            "POST".equals(method) ? post(path) : get(path);

        if (!"anonymous".equals(principal)) {
            request.with(httpBasic(principal, password));
        }

        // Giữ CSRF hợp lệ để cô lập kiểm tra quyền.
        if ("POST".equals(method)) {
            request.with(csrf());
        }

        mvc.perform(request)
            .andExpect(status().is(expected));
    }
}
~~~

**Bài học từ từng thí nghiệm:**

- **Bob + token hợp lệ = 201**, cùng Bob đó **thiếu token = 403** và **token sai = 403** → chứng minh lớp CSRF có tác dụng độc lập với `docs:write`.
- **Alice + token hợp lệ = 403** → khi loại bỏ lỗi CSRF, vẫn thiếu `docs:write`, nên là lỗi authorization.
- **Anonymous + token hợp lệ = 401** đối với endpoint được bảo vệ → giúp tách tình huống chưa xác thực.
- **`permitAll` + POST thiếu CSRF = 403**, nhưng `permitAll` + POST CSRF hợp lệ = 200 → `permitAll` không tắt `CsrfFilter`.
- **GET Alice = 200, GET Dave = 403** dù không gửi CSRF → tình huống phân quyền thuần ở method safe.
- **Carol `ROLE_ADMIN`** chỉ truy cập POST admin, không có `docs:write` → không trộn role với permission.
- Test ma trận đưa **token hợp lệ** vào mọi POST để so sánh policy công bằng; các test thiếu/sai token được tách riêng.

`@SpringBootTest` và `@AutoConfigureMockMvc` dùng cấu hình web/security thật của ứng dụng trong môi trường test. `httpBasic` tạo header Basic cho request; `csrf()` là `RequestPostProcessor` hỗ trợ tạo token phù hợp với test. Test này không mở TCP server như curl, và kết quả sẽ chịu ảnh hưởng nếu project thêm filter chain, exception handler hoặc cấu hình khác.

### 9.3. Chạy và xác minh

~~~bash
# macOS/Linux
./mvnw test

# Windows PowerShell / Command Prompt
mvnw.cmd test
~~~

Kỳ vọng: các test đều vượt qua, Maven trả exit code 0, không có failure/error. Output log, timestamp và thời lượng phụ thuộc môi trường. Không nên bịa log thành công nếu chưa thực sự chạy.

**Một test 403 đơn lẻ chưa xác minh nguyên nhân.** Giá trị ở chỗ cặp test chỉ khác **một biến** (token hoặc authority), cộng với kiến thức về thứ tự filter và thông tin log.

## 10. Vì sao không thể kết luận từ response body hoặc header?

Một ứng dụng có thể tùy chỉnh `AccessDeniedHandler`, `AuthenticationEntryPoint`, error controller, reverse proxy hoặc API error envelope. Khi đó cả CSRF và authorization đều có thể trả:

~~~json
{"status":403,"message":"Forbidden"}
~~~

Body trên **không nói nguyên nhân**. Ngược lại, nếu một ứng dụng chủ động trả mã lỗi nội bộ như `CSRF_MISSING` hoặc `PERMISSION_DENIED`, điều này chỉ đáng tin nếu được thiết kế và kiểm thử trên server. Không suy luận từ tên trường do frontend tự đặt hoặc một error body chung.

### Phân biệt 401 và 403 đúng ngữ cảnh

- **401**: thường là chưa có/không hợp lệ authentication và server có thể gửi `WWW-Authenticate` với HTTP Basic.
- **403**: request đã đến một cơ chế từ chối; có thể do CSRF, thiếu quyền, role, account policy, method security hoặc filter khác.
- **302 redirect**: thường gặp với form login khi cần xác thực.
- **404 hoặc 403**: ứng dụng có thể cố tình che giấu sự tồn tại của tài nguyên nhạy cảm tùy thiết kế.
- **5xx**: lỗi kỹ thuật của service kiểm quyền cần được xử lý fail-closed; không tự đổi thành ALLOW.

HTTP status giúp định hướng, **không thay thế điều tra ở server**.

## 11. Quy trình debug 403 trên ứng dụng thực

Khi frontend báo “đăng nhập rồi mà POST vẫn 403”, chẩn đoán theo thứ tự sau:

1. **Chụp thông tin request** trong môi trường phù hợp: method, URL sau reverse proxy, context path, content type, có cookie/session không, có header CSRF không, loại xác thực, timestamp/correlation ID. **Không log plaintext password, session ID hay token thực tế.**
2. **Xác định SecurityFilterChain** đầu tiên khớp URL. Nếu có nhiều chain, mỗi chain có thể cấu hình `csrf`, `httpBasic`, `formLogin` và authorization khác nhau.
3. **Kiểm tra request có thuộc nhóm cần CSRF không.** Mặc định POST/PUT/PATCH/DELETE cần token; GET không cần, nhưng custom matchers có thể thay đổi.
4. **Đọc log có kiểm soát** tại `org.springframework.security.web.csrf.CsrfFilter` và package `org.springframework.security`. Chỉ bật DEBUG/TRACE tạm thời trong môi trường phù hợp; không để log rò rỉ bí mật.
5. **Nếu nghi CSRF:** kiểm tra token repository (session/cookie), header/parameter name, session cookie đi cùng request, token được làm mới sau login/logout, SPA request handler và BREACH/XOR handling nếu có.
6. **Nếu CSRF đã qua:** kiểm tra authentication (principal, xác thực thành công hay chưa) và **authorities thực tế** trong `Authentication#getAuthorities()`. So sánh với policy `hasRole/hasAuthority`, đúng prefix và HTTP method.
7. **Kiểm tra rule khớp đầu tiên** của `authorizeHttpRequests`, bao gồm `denyAll` fallback. Rule rộng đặt trước rule nhạy cảm có thể gây kết quả sai.
8. **Kiểm tra tầng method/domain:** `@PreAuthorize`, tenant, ownership, trạng thái bản ghi, policy service, CORS, CSRF và custom filters có thể từ chối độc lập.
9. **Viết test đối chứng:** giữ user đủ quyền nhưng thiếu/sai token; giữ token hợp lệ nhưng dùng user thiếu quyền; test anonymous với token hợp lệ; test GET không cần token.
10. **Không sửa bằng cách tắt CSRF hoặc đổi `permitAll`** nếu chưa xác định threat model và nguyên nhân thật.

### Bảng dấu hiệu thường gặp

| Quan sát | Điều nên kiểm tra đầu tiên | Không được kết luận vội |
| --- | --- | --- |
| GET với user đủ quyền 200, POST với user đó 403 | CSRF token và quyền của action POST | “Do role không được cấp” |
| POST với Bob thiếu token 403, thêm token hợp lệ 201 | Lỗi CSRF | “Bob có quyền không ổn định” |
| POST với Alice có token hợp lệ vẫn 403 | `docs:write`, owner/tenant, rule order | “CSRF chắc chắn bị lỗi” |
| POST tới `permitAll` vẫn 403 | CSRF filter chạy độc lập | “permitAll không hiệu lực” |
| POST anonymous thiếu token 403 nhưng thêm token được 401 | CSRF trước authentication | “403 luôn là authenticated” |
| Chỉ SPA sau login/logout gặp 403 | token cũ, cookie/session, handler, token rotation | “Tăng quyền cho user” |
| Cả GET và POST đều 403 với tài khoản | Authorization, chain selection, custom filter | “CSRF là nguyên nhân duy nhất” |
| POST thiếu token vẫn 201 | CSRF đã tắt/bị ignore? chain khác? | “Vậy hệ thống chắc an toàn” |

## 12. Không tắt CSRF tùy tiện — nhưng cũng không áp dụng máy móc

CSRF đặc biệt quan trọng khi **trình duyệt tự gửi credentials** tới server, như cookie phiên. Một REST API dùng bearer token do client chủ động đính kèm trong `Authorization` header có mô hình rủi ro khác; tuy vậy không nên nói “REST không cần CSRF” hoặc “JWT thì chắc chắn miễn CSRF” nếu JWT được lưu cookie và tự động gửi theo request.

### 12.1. Trường hợp có thể cân nhắc ngoại lệ hẹp

Một webhook server-to-server đã được xác minh bằng chữ ký HMAC, không dùng credential browser tự gửi, có thể được xem xét **không cần CSRF** tại đúng endpoint đó. Cần thẩm định threat model, kiểm tra signature, replay protection và chặn request không hợp lệ.

Ví dụ **fragment** cấu hình ngoại lệ hẹp:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/api/webhooks/provider-a")
);
~~~

Đoạn này **không** được áp dụng vô điều kiện và không đủ để bảo vệ webhook nếu chưa có chữ ký/mã xác thực độc lập. Trong ứng dụng có nhiều chain, phải chắc request đi vào chain nào. Không dùng matcher quá rộng như `/api/**` để bỏ CSRF nếu trong đó có endpoint được gọi từ browser với cookie.

### 12.2. Những cách sửa sai nguy hiểm

~~~java
// Không dùng như một "cách sửa 403" phổ quát:
http.csrf(csrf -> csrf.disable());

// Không dùng để né thiếu quyền:
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll()
);
~~~

Hai biện pháp trên thay đổi **lớp bảo vệ khác nhau** và có thể gây lỗ hổng. Khi CSRF token lỗi, cần sửa đường phát hành/lưu/gửi token hoặc xác định chính xác loại request được phép bỏ CSRF. Khi thiếu quyền, cần đánh giá chính sách và cấp quyền đúng theo nghiệp vụ, không mở toàn bộ endpoint.

### 12.3. Các bảo vệ khác không thay CSRF hay authorization

- **CORS** kiểm soát đọc response và một số loại cross-origin request theo browser; cấu hình CORS đúng **không tự thay thế** CSRF protection.
- Cookie `SameSite`, `Secure`, `HttpOnly` giúp giảm rủi ro trong một số mô hình, nhưng không thay thế chính sách quyền và phải đánh giá tương tác với browser/client.
- **HTTPS** bảo vệ kênh truyền, không chứng minh request được nạn nhân chủ động gửi.
- **Password/OTP/MFA** bảo vệ authentication; có đăng nhập hợp lệ không chứng minh mọi request thay đổi dữ liệu là chủ ý.
- **CSRF token** không phòng IDOR/BOLA: với mỗi object ID vẫn cần permission, tenant/ownership và scope dữ liệu.

## 13. Mở rộng ma trận cho ứng dụng có dữ liệu thật

Sau khi đã phân biệt CSRF và authorization tại HTTP, ứng dụng thực cần kiểm tra quyền trên **tài nguyên cụ thể**:

| Request | CSRF | Authentication | Permission | Domain constraint | Kết quả |
| --- | --- | --- | --- | --- | --- |
| Bob POST tài liệu mới | Hợp lệ | Bob | `docs:write` | Tenant hợp lệ | ALLOW |
| Bob POST tài liệu mới | Thiếu | Bob | `docs:write` | Tenant hợp lệ | DENY tại CSRF |
| Alice POST tài liệu mới | Hợp lệ | Alice | Thiếu `docs:write` | Không cần xét tiếp | DENY tại authorization |
| Bob PATCH tài liệu của tenant khác | Hợp lệ | Bob | Có `docs:write` | Khác tenant | DENY tại domain |
| Anonymous GET tài liệu riêng | Không bắt buộc | Anonymous | Chưa xác thực | Không cần xét | Thường 401/redirect |
| Bob GET tài liệu riêng nhưng bị thu hồi quyền | Không bắt buộc | Bob | `docs:read` | Ownership/share grant đã thu hồi | DENY tại domain |

Khi sử dụng `@PreAuthorize` hoặc custom `AuthorizationManager` cho domain, cần giữ test theo instance và tenant, không chỉ test type-level HTTP rule. Với thao tác ghi, kiểm tra trạng thái bản ghi trong transaction phù hợp; với `LIST/SEARCH`, lọc theo phạm vi được phép ngay ở query để tránh lộ dữ liệu qua kết quả hoặc phân trang.

Bài học này tập trung vào phân biệt **nguồn gốc 403**, nên mã demo cố ý chưa triển khai tenant/ownership. Đừng diễn giải việc test qua CSRF và `hasAuthority` là bằng chứng ứng dụng đã an toàn toàn diện.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Bob có `docs:write`, gửi POST thiếu CSRF token và nhận 403. Có nên cấp thêm role?  
**Đáp án:** Không. Trước hết kiểm tra `CsrfFilter`, token repository và client; quyền đã đủ theo ví dụ.

**Câu 2.** Alice chỉ có `docs:read`, POST có CSRF token hợp lệ vẫn 403. Khả năng đầu tiên?  
**Đáp án:** Thiếu `docs:write`; cũng cần xem rule HTTP và domain policy. Không đổ lỗi cho CSRF khi token đã được xác minh.

**Câu 3.** Anonymous POST được `permitAll()` nhưng không có CSRF token; có thể trả 403 không?  
**Đáp án:** Có. `permitAll` thuộc authorization, không tự miễn CSRF.

**Câu 4.** Anonymous POST vào endpoint bảo vệ: thiếu CSRF → 403, có CSRF hợp lệ → 401. Vì sao?  
**Đáp án:** `CsrfFilter` có thể chặn trước authentication; khi qua CSRF, HTTP Basic mới cần danh tính hợp lệ.

**Câu 5.** GET với Dave đã đăng nhập nhưng thiếu `docs:read` nhận 403, có phải CSRF không?  
**Đáp án:** Thông thường không, vì GET mặc định không cần CSRF. Đây là lỗi quyền hoặc cơ chế chặn khác.

**Câu 6.** Trong MockMvc, cách làm token hợp lệ và token sai?  
**Đáp án:** `.with(csrf())` và `.with(csrf().useInvalidToken())`; cũng có thể kiểm bằng header với `csrf().asHeader()`.

**Câu 7.** Có CSRF token hợp lệ thì user được gọi mọi API không?  
**Đáp án:** Không. Vẫn phải được xác thực và có đúng quyền/role, đúng resource và tenant.

**Câu 8.** Mỗi lần SPA login/logout xong thì POST tiếp bị 403. Cần kiểm tra gì?  
**Đáp án:** Token bị làm mới/xóa, cookie/session có thay đổi, cách SPA lấy/gửi token mới, repository và request handler.

**Câu 9.** Vì sao không nên nhìn response `{"status":403}` để kết luận là CSRF?  
**Đáp án:** Cả CSRF và authorization có thể cùng dùng 403 và error envelope giống nhau. Phải dùng filter logs hoặc test đối chứng.

**Câu 10.** API bearer token độc lập cookie có bắt buộc tắt CSRF không?  
**Đáp án:** Không. Cần đánh giá browser có tự gửi credential hay không, cookie/token storage, luồng client và threat model. Không quyết định chỉ từ tên API.

**Câu 11.** Carol có `ROLE_ADMIN` nhưng không có `docs:write`, POST có CSRF hợp lệ được phép không?  
**Đáp án:** Không theo ví dụ; `hasAuthority("docs:write")` kiểm tra đúng chuỗi, không mặc định coi admin có mọi permission.

**Câu 12.** Có thể chứng minh lỗi authorization bằng một request POST thiếu CSRF không?  
**Đáp án:** Không. Hãy cung cấp token hợp lệ rồi so sánh user đủ/thiếu permission; nếu không, CSRF đã chặn trước khi quyền được đánh giá.

**Ghi nhớ:** **403 không phải một nguyên nhân**, mà là một kết quả HTTP. Đối với request thay đổi trạng thái, hãy kiểm tra **CSRF token**, rồi **authentication**, rồi **authorization** ở đúng filter/chain, và cuối cùng là chính sách tài nguyên cụ thể. Test đối chứng chỉ thay đổi **một yếu tố tại một thời điểm** là cách chắc chắn nhất để phân biệt các nguồn lỗi.

## Tài liệu chính thức

- Spring Security 6.5 — Cross Site Request Forgery (CSRF): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — Servlet Architecture (thứ tự `CsrfFilter`, authentication và authorization): https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Security 6.5 — Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — `CsrfFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfFilter.html
- Spring Security 6.5 — `MissingCsrfTokenException` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/MissingCsrfTokenException.html
- Spring Security 6.5 — `InvalidCsrfTokenException` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/InvalidCsrfTokenException.html
