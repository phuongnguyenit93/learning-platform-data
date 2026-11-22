# failureUrl, failureHandler và thông báo không tiết lộ trạng thái tài khoản trong Spring Security

## 1. Mục tiêu và phạm vi

Trong ứng dụng **Spring Boot/Spring Security Servlet** dùng **form login**, người dùng thường gửi username/password qua biểu mẫu `POST /login`. Đăng nhập có thể thất bại do nhiều nguyên nhân: sai mật khẩu, không tồn tại username, tài khoản bị khóa, bị vô hiệu hóa, hết hạn tài khoản, hết hạn credentials hoặc lỗi trong hệ thống xác thực. Spring Security cần xử lý thất bại phù hợp với trải nghiệm người dùng **mà không vô tình tiết lộ trạng thái nội bộ của tài khoản** cho người chưa xác minh danh tính.

Hai điểm mở rộng liên quan trực tiếp:

- **`failureUrl(...)`**: cách khai báo đơn giản một URL mà trình duyệt sẽ được chuyển tới sau khi **authentication thất bại**.
- **`failureHandler(...)`**: cung cấp một `AuthenticationFailureHandler`, cho phép tự quyết định response (redirect, status, thông điệp chung), audit/metrics hoặc xử lý khác trong khuôn khổ bảo mật.

Ví dụ thường thấy:

~~~java
http.formLogin(form -> form
    .loginPage("/login")
    .failureUrl("/login?error")
    .permitAll()
);
~~~

Hoặc dùng handler riêng:

~~~java
http.formLogin(form -> form
    .loginPage("/login")
    .failureHandler(authenticationFailureHandler)
    .permitAll()
);
~~~

Đây là **hai phương án thay thế**, không phải yêu cầu phải khai báo đồng thời. Các snippet chỉ là phần cấu hình; dự án chạy được ở phần 7.

**Nguyên tắc bảo mật của bài:** phân biệt lý do thất bại **nội bộ** với thông tin hiển thị **công khai**. Một biểu mẫu đăng nhập không nên trả các thông báo có thể dùng để dò tài khoản như “username này có thật nhưng đang bị khóa” hoặc “tài khoản của bạn đã hết hạn” cho một người chưa chứng minh được quyền sở hữu account. Giao diện thường nên dùng **một thông điệp chung**; hệ thống có thể ghi nhận lý do chi tiết trong kênh audit được bảo vệ.

Bài tập trung vào form login trong **Servlet stack** với `SecurityFilterChain`, `HttpSecurity`, `UsernamePasswordAuthenticationFilter` và Spring Security 6.x. API không dùng biểu mẫu, chẳng hạn resource server xử lý JWT, có quy trình khác và không nên mặc định áp dụng redirect của form login cho API client.

## 2. Luồng đăng nhập biểu mẫu và điểm xử lý thất bại

Một mô hình điển hình:

~~~text
Browser
  |
  | GET /login
  v
Trang HTML có form username/password + CSRF token
  |
  | POST /login (username, password, CSRF token)
  v
Spring Security FilterChainProxy
  |
  v
UsernamePasswordAuthenticationFilter
  |
  +-- tạo Authentication chưa xác thực
  |
  v
AuthenticationManager -> AuthenticationProvider
  |
  +-- xác thực thành công
  |      |
  |      v
  |   Success handler: session/context, saved request, redirect...
  |
  +-- ném AuthenticationException
         |
         v
    AuthenticationFailureHandler
         |
         +-- mặc định/đơn giản: redirect tới failureUrl
         |
         +-- tùy chỉnh: response chung, audit, metrics...
                |
                v
         Browser nhận kết quả mà không thấy trạng thái nội bộ
~~~

Đây là sơ đồ khái niệm. Với cấu hình session, success flow còn có xử lý CSRF/session fixation/security context theo cách Spring Security đã cấu hình. Không nên viết lại toàn bộ flow chuẩn chỉ để thay một dòng thông báo lỗi.

### Authentication failure khác authorization failure

- **Authentication failure**: trình xác thực không chấp nhận username/password hoặc account state. Thường do `AuthenticationException` trong quy trình login, kích hoạt `AuthenticationFailureHandler`.
- **Authorization failure**: người dùng đã đăng nhập nhưng không có quyền gọi một URL hoặc thực hiện hành động. Ví dụ thiếu `ROLE_ADMIN`. Việc từ chối lúc truy cập tài nguyên thường do `AccessDeniedHandler`/`ExceptionTranslationFilter`, **không phải** `formLogin().failureHandler(...)`.
- **CSRF failure**: thiếu/sai CSRF token trong POST có thể bị từ chối trước khi `UsernamePasswordAuthenticationFilter` xác thực credentials. Lỗi 403 từ CSRF **không nhất thiết** đi qua failure handler dành cho authentication.

Vì thế không nên kỳ vọng một `failureUrl` sẽ xử lý mọi lỗi 401/403 của ứng dụng.

## 3. failureUrl: cách đơn giản để redirect khi login thất bại

Với form login:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/public").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .failureUrl("/login?error")
            .permitAll()
        )
        .build();
}
~~~

Snippet được đặt trong một lớp Spring `@Configuration` và cần import tương ứng; chưa bao gồm lớp ứng dụng hay template.

Giải thích các URL:

- `loginPage("/login")` chỉ định trang HTML mà browser tải bằng `GET /login`. Khi bạn khai báo login page tùy chỉnh, **bạn chịu trách nhiệm tạo controller/view** cho URL đó. Spring Security không tiếp tục sinh trang login mặc định cho URL tùy chỉnh.
- `loginProcessingUrl("/login")` cho biết filter nhận request đăng nhập ở `POST /login`. Thông thường **không cần** viết MVC controller `@PostMapping("/login")` nếu dùng form login chuẩn; filter xử lý trước MVC.
- `failureUrl("/login?error")` là URL điều hướng sau khi authentication thất bại.
- `permitAll()` cho phép truy cập các URL liên quan trang login/lỗi đăng nhập phù hợp; đồng thời quy tắc `authorizeHttpRequests` nên nhất quán với đường dẫn custom.
- Chuỗi `?error` chỉ là **cờ chung để giao diện biết hiển thị lỗi**. Nó không nói “locked”, “disabled” hay “usernameNotFound”.

### failureUrl phản hồi thế nào?

Trong luồng browser thông thường, authentication thất bại khiến handler redirect (thường HTTP **302**) tới `/login?error`. Trình duyệt sau đó gọi `GET /login?error` và xem lại trang biểu mẫu. Với view tùy chỉnh, bạn có thể hiển thị:

> Tên đăng nhập hoặc mật khẩu không hợp lệ. Vui lòng kiểm tra và thử lại.

Dòng thông báo này **được giữ nguyên cho mọi nguyên nhân thất bại phù hợp**, kể cả tài khoản bị khóa/hết hạn hoặc username không tồn tại. Một thông báo chung tránh nhiều dạng user enumeration, dù không đảm bảo phòng hết mọi kênh rò rỉ (ví dụ timing).

### failureUrl là cấu hình tiện ích cho failure handler

Về mặt hành vi, `failureUrl(...)` thiết lập xử lý thất bại theo kiểu redirect, thường thông qua `SimpleUrlAuthenticationFailureHandler`. Nó không phải filter độc lập được thêm riêng vào chain.

Spring Security có thể lưu `AuthenticationException` trong request/session cho một số cách xử lý failure/redirect. **Đừng đưa `exception.message`, `SPRING_SECURITY_LAST_EXCEPTION.message` hoặc tên class của ngoại lệ ra HTML** chỉ vì chúng có trong server-side context. Thông điệp từ exception có thể nói rõ tài khoản bị khóa, disabled, hết hạn hoặc không tồn tại.

Không nên đưa lý do thất bại vào query string như:

~~~text
/login?error=ACCOUNT_LOCKED
/login?error=USER_NOT_FOUND
/login?error=CREDENTIALS_EXPIRED
~~~

Đó là anti-pattern cho màn hình login công khai. Query string có thể lộ qua lịch sử trình duyệt, URL được chia sẻ, log của reverse proxy và analytics, đồng thời giúp kẻ tấn công phân loại tài khoản.

## 4. failureHandler: mở rộng hành vi có kiểm soát

`AuthenticationFailureHandler` có phương thức chính:

~~~java
void onAuthenticationFailure(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException exception
) throws IOException, ServletException;
~~~

Interface nằm trong package `org.springframework.security.web.authentication`. Handler được gọi khi **quy trình authentication của filter liên quan thất bại**. Tham số `exception` chứa nguyên nhân ở mức kỹ thuật, thường có thể phân biệt `BadCredentialsException`, `LockedException`, `DisabledException`, `CredentialsExpiredException`... Nhưng chi tiết này **không nên được phản ánh nguyên xi** trong response cho người chưa xác minh danh tính.

Bạn chọn custom handler khi cần:

- Ghi **audit/metric nội bộ** có phân quyền và bảo vệ dữ liệu nhạy cảm.
- Chuẩn hóa response thất bại theo giao diện công ty.
- Lựa chọn redirect chung, xử lý yêu cầu ajax hoặc client đặc thù.
- Tích hợp bộ đếm nỗ lực đăng nhập/rate limit theo thiết kế riêng.
- Chuyển sang luồng hỗ trợ khôi phục tài khoản **sau bước xác minh danh tính**, thay vì thông báo nguyên nhân công khai.

### Handler đơn giản dùng lại logic redirect có sẵn

~~~java
@Bean
AuthenticationFailureHandler formFailureHandler() {
    SimpleUrlAuthenticationFailureHandler redirect =
        new SimpleUrlAuthenticationFailureHandler("/login?error");

    return (request, response, exception) -> {
        // Audit/metrics nội bộ nếu thực sự cần; tránh log password.
        redirect.onAuthenticationFailure(request, response, exception);
    };
}
~~~

Đây là snippet Spring bean; project đầy đủ ở phần 7. `SimpleUrlAuthenticationFailureHandler` xử lý redirect và có thể quản lý exception phục vụ flow tùy cấu hình. Handler ở trên vẫn chỉ chuyển về **cùng một URL chung**, không phân biệt trạng thái tài khoản.

Khi cần response JSON **thực sự** cho client không dùng browser form:

~~~java
// Mẫu minh họa cho một authentication endpoint được thiết kế riêng.
AuthenticationFailureHandler jsonFailureHandler =
    (request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write(
            "{\"error\":\"AUTHENTICATION_FAILED\"}");
    };
~~~

Đây là snippet thay thế, **không** đồng thời gắn vào form login browser của phần 7. Nó chỉ xử lý ngoại lệ authentication, không tự giải quyết invalid CSRF token hay mọi lỗi authorization. Với API, thường ưu tiên cơ chế xác thực/entry point dành riêng cho API hơn là cố dùng form login redirect.

### Chọn failureUrl hay failureHandler?

| Nhu cầu | Nên bắt đầu với |
| --- | --- |
| Form login bình thường, chỉ cần `/login?error` và thông báo chung | `failureUrl("/login?error")` |
| Redirect chung + audit/metrics không nhạy cảm | `failureHandler(...)` ủy quyền cho `SimpleUrlAuthenticationFailureHandler` |
| Response JSON từ endpoint authentication chuyên biệt | Custom `AuthenticationFailureHandler` hoặc cơ chế API authentication phù hợp |
| Phân biệt exception để hiển thị “account locked” cho người lạ | **Không nên**; thiết kế luồng phục hồi đã xác minh danh tính |
| Phản hồi authorization 403 cho endpoint đã đăng nhập | `AccessDeniedHandler`/authorization policy, không phải login failure handler |

**Đừng cấu hình cả `failureUrl(...)` lẫn `failureHandler(...)` rồi mong hai thứ “chạy nối tiếp”.** Cả hai ảnh hưởng tới nơi xử lý authentication failure. Nếu cần thêm việc ngoài redirect, dùng một handler chủ động ủy quyền redirect. Giữ chính sách phản hồi rõ ràng, có test.

## 5. Không tiết lộ trạng thái tài khoản: điều gì được phép hiển thị?

### 5.1. Các trạng thái nội bộ khác nhau nhưng kết quả công khai giống nhau

Ví dụ nguồn user trong database/Spring Security có thể có:

| Nguyên nhân nội bộ | Exception thường gặp (provider dựa trên UserDetails) | Phản hồi công khai đề xuất |
| --- | --- | --- |
| Username không tồn tại | `UsernameNotFoundException` có thể bị che thành `BadCredentialsException` | “Tên đăng nhập hoặc mật khẩu không hợp lệ.” |
| Sai password | `BadCredentialsException` | Cùng thông điệp chung |
| User bị khóa | `LockedException` | Cùng thông điệp chung |
| User bị disabled | `DisabledException` | Cùng thông điệp chung |
| Account hết hạn | `AccountExpiredException` | Cùng thông điệp chung |
| Credentials hết hạn | `CredentialsExpiredException` | Cùng thông điệp chung |

`DaoAuthenticationProvider`/`AbstractUserDetailsAuthenticationProvider` thường kiểm tra account status trước/sau xác minh password theo quy trình của nó. Các exception nói trên là **chi tiết của cơ chế username/password**, không áp dụng tự động cho mọi `AuthenticationProvider` hoặc bearer token.

Trạng thái bên trong giúp vận hành và support xử lý đúng; phản hồi bên ngoài nên tránh xác nhận tài khoản nào có thật hoặc tình trạng cụ thể.

### 5.2. Vì sao lỗi chi tiết tạo kênh user enumeration?

Giả sử login công khai trả:

~~~text
alice@example.com  -> "Sai mật khẩu"
bob@example.com    -> "Tài khoản không tồn tại"
admin@example.com  -> "Tài khoản đang bị khóa"
~~~

Attacker có thể gửi nhiều username và phân loại: account nào tồn tại, ai đang bị khóa và tài khoản nào dùng mật khẩu có thể đang đúng. Phần này bổ sung cho những kênh rò rỉ khác như khác biệt HTTP status, body, redirect location, thời gian xử lý hoặc response size.

**Mục tiêu thực tế:** với những thất bại cần được che giấu, hãy thống nhất thông điệp, mã trạng thái và tuyến redirect công khai; hạn chế sai khác không cần thiết trong timing/side effects, bổ sung rate limiting, giám sát và chính sách chống credential stuffing. **Thông điệp chung một mình không đảm bảo chống enumeration qua timing.**

Khi user thật cần biết tài khoản bị khóa/hết hạn hoặc cần đổi password, nên thiết kế **luồng hỗ trợ/khôi phục sau khi xác minh quyền sở hữu**: ví dụ gửi email out-of-band với nội dung phù hợp, MFA/step-up khi có thể hoặc liên hệ helpdesk theo quy trình có xác minh. Không đưa email tồn tại/trạng thái tài khoản ra giao diện trước khi xác minh.

### 5.3. Đừng dùng trực tiếp exception.message trong template

Một ví dụ **không nên dùng**:

~~~html
<!-- Anti-pattern: tiết lộ lý do thất bại từ exception nội bộ -->
<p th:text="${session.SPRING_SECURITY_LAST_EXCEPTION.message}"></p>
~~~

Mẫu **nên dùng**:

~~~html
<p th:if="${param.error}" role="alert">
  Tên đăng nhập hoặc mật khẩu không hợp lệ.
</p>
~~~

Hai snippet sử dụng cú pháp Thymeleaf và cần đặt trong template; `param.error` chỉ kiểm tra cờ chung. Không hiển thị, không chuyển tiếp và không phản chiếu text exception trực tiếp từ `AuthenticationFailureHandler`.

Một số hướng dẫn cũ có thể đề xuất hiển thị `SPRING_SECURITY_LAST_EXCEPTION.message` để dễ debug; cách đó không phù hợp với yêu cầu **không tiết lộ trạng thái tài khoản** ở trang đăng nhập công khai.

### 5.4. Audit nội bộ nhưng không log bí mật

Audit hữu ích cho phát hiện nỗ lực đăng nhập bất thường, điều tra sự cố và đối chiếu chính sách. Tuy nhiên audit phải được phân quyền, giữ dữ liệu tối thiểu và có chính sách retention. Không log:

- Raw password hoặc giá trị trường `password`.
- Header `Authorization`, session cookie, token, CSRF token.
- Nội dung đầy đủ authentication exception/message khi có thể chứa thông tin nhạy cảm.
- Username/IP đầy đủ ở mức log rộng nếu chưa có căn cứ về privacy và phân quyền.

Nếu cần metric theo loại lỗi, sử dụng nhãn nội bộ được chuẩn hóa, giới hạn cardinality, tránh cho người dùng cuối xem. Đừng tự gắn một nhãn khác nhau theo username và vô tình tạo log/metrics có cardinality cực lớn hoặc kho dữ liệu nhạy cảm mới.

## 6. Liên hệ với CSRF, saved request, session và đường dẫn

### 6.1. Form login cần POST và CSRF token hợp lệ

Form login của Spring Security trên Servlet thường nhận `POST /login` qua `UsernamePasswordAuthenticationFilter`, với tham số mặc định `username` và `password`. Khi CSRF đang bật (mặc định trong cấu hình web thông thường), request POST cần token CSRF hợp lệ.

Nếu token thiếu/sai, request có thể bị **403 Forbidden** từ CSRF filter và **không** chạy `AuthenticationFailureHandler`. Đây không phải bằng chứng username bị khóa hoặc sai mật khẩu. Đừng tắt CSRF chỉ để “sửa” lỗi biểu mẫu; kiểm tra form có hidden field CSRF và cookie/session phù hợp hay không.

Trong Thymeleaf tích hợp Spring MVC, có thể dùng:

~~~html
<form th:action="@{/login}" method="post">
  <input type="text" name="username">
  <input type="password" name="password">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Đoạn này cho thấy rõ CSRF field. Khi dùng `th:action` với Spring MVC/Thymeleaf integration, framework có thể tự thêm hidden CSRF field; nếu template tạo trường CSRF tường minh, cần tránh hai nguồn giá trị khác nhau. Ví dụ đầy đủ ở phần 7 dùng biểu mẫu và thuộc tính `_csrf` phù hợp.

### 6.2. Trang login phải được truy cập không cần đăng nhập

Nếu cấu hình `loginPage("/login")` nhưng `GET /login` cũng bị policy yêu cầu authenticated, browser có thể bị vòng lặp redirect. Dùng `formLogin(...).permitAll()` và bảo đảm authorization matcher cho trang login/asset/`/error` phù hợp.

Khi tùy chỉnh `loginProcessingUrl`, form HTML phải gửi đúng action/method. Nếu gửi nhầm `POST /signin` trong khi filter chỉ bắt `POST /login`, request có thể vào MVC/CSRF/error handler thay vì authentication filter; lúc ấy `failureHandler` không được gọi.

### 6.3. Success redirect khác failure redirect

Sau login thành công, Spring Security có thể đưa user tới **saved request** trước đó hoặc default target URL. Khi thất bại, `failureUrl` chuyển tới một trang lỗi chung. Không nhầm `defaultSuccessUrl(...)` hoặc `successHandler(...)` với handler thất bại.

Nếu dùng URL redirect do client gửi, cần kiểm tra open redirect; với form login phổ biến, dùng một **đích lỗi cố định trong ứng dụng** như `/login?error` là cách đơn giản hơn.

### 6.4. Session exception không phải thông báo public

Một số failure handler có thể lưu exception trong session/request. Điều này có ích cho tùy chỉnh nội bộ, nhưng không có nghĩa thông điệp ấy an toàn để render ra UI. Việc giữ exception hoặc thông tin account state lâu hơn cần thiết còn có thể tạo dữ liệu stale trong session và tăng diện tích nhạy cảm. Nếu cần thông điệp cho người dùng, UI chỉ cần dựa trên **một cờ lỗi chung** hoặc một mã lỗi không tiết lộ.

### 6.5. Rate limit và khóa tài khoản có thể bị lạm dụng

Khóa account sau quá nhiều lần sai có thể giảm brute-force nhưng cũng có thể bị kẻ xấu lạm dụng để gây **denial of service** cho tài khoản người khác. Kết hợp throttling theo nhiều tín hiệu đáng tin cậy, risk-based controls, giám sát, MFA và chính sách mở khóa/khôi phục. `failureHandler` có thể góp phần ghi sự kiện, nhưng nó **không tự có** chính sách đếm lỗi/khóa tài khoản nếu ứng dụng chưa triển khai.

## 7. Ví dụ Spring Boot 3 / Spring Security 6 chạy được

Ví dụ dưới đây minh họa **một custom `AuthenticationFailureHandler`** luôn chuyển về `/login?error`, trong khi một trang Thymeleaf chỉ hiển thị **thông báo chung**. Mẫu hoạt động với người dùng hợp lệ, sai mật khẩu, user không tồn tại, bị khóa, disabled và hết hạn. Nó giữ CSRF mặc định, không công bố chi tiết ngoại lệ, và bổ sung kiểm thử với MockMvc.

**Các điểm thiết kế:**

- Spring Boot 3.3.x, Java 17+, Spring MVC + Thymeleaf + Spring Security.
- `/login` là trang HTML tự cung cấp; `POST /login` do Spring Security filter xử lý.
- Form login dùng `failureHandler` riêng, ủy quyền redirect chung cho `SimpleUrlAuthenticationFailureHandler("/login?error")`.
- Trang login không in exception/message; chỉ hiện một chuỗi không phân biệt nguyên nhân khi URL có `?error`.
- `InMemoryUserDetailsManager` chỉ dùng cho demo; các trạng thái account để kiểm tra hành vi, không phải cách quản lý user production.
- Test kiểm tra nhiều lỗi đều tới cùng redirect và cùng thông điệp. HTTP status ở response POST thường là **302**, sau đó GET trang login là **200**.

### 7.1. Cấu trúc thư mục

~~~text
form-login-failure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/loginfailure/
    │   │   ├── LoginFailureApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── LoginController.java
    │   │   └── HomeController.java
    │   └── resources/templates/login.html
    └── test/java/com/example/loginfailure/LoginFailureTests.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>form-login-failure</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

**`src/main/java/com/example/loginfailure/LoginFailureApplication.java`:**

~~~java
package com.example.loginfailure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginFailureApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFailureApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/loginfailure/SecurityConfig.java`:**

~~~java
package com.example.loginfailure;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class SecurityConfig {

    private static final Logger log =
        LoggerFactory.getLogger(SecurityConfig.class);

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler formFailureHandler
    ) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .failureHandler(formFailureHandler)
                .permitAll()
            )
            .build();
    }

    @Bean
    AuthenticationFailureHandler formFailureHandler() {
        SimpleUrlAuthenticationFailureHandler redirect =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, exception) -> {
            // Ví dụ tối thiểu: không log username/password/exception.
            // Production có thể gửi event nội bộ không nhạy cảm.
            log.warn("Form sign-in failed");
            redirect.onAuthenticationFailure(request, response, exception);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("active")
                .password(hash)
                .roles("USER")
                .build(),

            User.withUsername("disabled")
                .password(hash)
                .roles("USER")
                .disabled(true)
                .build(),

            User.withUsername("locked")
                .password(hash)
                .roles("USER")
                .accountLocked(true)
                .build(),

            User.withUsername("accountExpired")
                .password(hash)
                .roles("USER")
                .accountExpired(true)
                .build(),

            User.withUsername("credentialsExpired")
                .password(hash)
                .roles("USER")
                .credentialsExpired(true)
                .build()
        );
    }
}
~~~

**Lưu ý code:** tất cả các user có cùng password demo đã BCrypt encode; user `active` có bốn cờ trạng thái hợp lệ, bốn user còn lại bị từ chối theo lý do riêng. Handler không phân biệt status trong response. Demo không có cơ chế đếm sai password hay khóa tự động; các cờ được đặt sẵn để kiểm thử.

**`src/main/java/com/example/loginfailure/LoginController.java`:**

~~~java
package com.example.loginfailure;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginController {
    @GetMapping("/login")
    public String login() {
        return "login";
    }
}
~~~

Controller này chỉ xử lý **GET** trang login; POST do Spring Security filter thực hiện. `@Controller` trả tên view Thymeleaf, không phải `@RestController` trả body string.

**`src/main/java/com/example/loginfailure/HomeController.java`:**

~~~java
package com.example.loginfailure;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HomeController {

    @GetMapping("/public")
    public String publicPage() {
        return "public OK";
    }

    @GetMapping("/")
    public String home(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile: " + authentication.getName();
    }
}
~~~

`/public` có thể xem khi chưa đăng nhập; `/` và `/profile` yêu cầu authentication. Khi login thành công mà không có saved request từ trước, Spring Security thường redirect về `/`.

**`src/main/resources/templates/login.html`:**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}" role="alert">
        Tên đăng nhập hoặc mật khẩu không hợp lệ.
    </p>

    <form method="post" th:action="@{/login}">
        <label for="username">Tên đăng nhập</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password" required>

        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
~~~

Trang HTML **không lấy `exception.message`**, không nhận exception class từ query string; nó chỉ kiểm tra có cờ `error` hay không và hiển thị một thông điệp cố định. `th:action="@{/login}"` được Thymeleaf xử lý theo context path; CSRF token lấy từ request attribute của Spring Security. Trong một số cấu hình Thymeleaf/Spring MVC, cơ chế `RequestDataValueProcessor` còn có thể tự thêm hidden CSRF field khi dùng `th:action`; hãy kiểm tra HTML render thực tế để tránh trường trùng với giá trị khác nhau. Cả hai cùng token hợp lệ thì không làm thay đổi nguyên tắc bảo vệ CSRF.

### 7.2. Test bằng Spring Security MockMvc

Kiểm thử hồi quy rất cần thiết vì thông điệp generic có thể bị vô tình thay bằng thông báo exception trong một lần sửa template sau này.

**`src/test/java/com/example/loginfailure/LoginFailureTests.java`:**

~~~java
package com.example.loginfailure;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFailureTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allAccountFailuresUseSameRedirect() throws Exception {
        for (String username : List.of(
                "disabled",
                "locked",
                "accountExpired",
                "credentialsExpired",
                "unknown-user"
        )) {
            mvc.perform(formLogin()
                    .user(username)
                    .password("demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
        }

        mvc.perform(formLogin()
                .user("active")
                .password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void publicPageOnlyShowsGenericFailureMessage() throws Exception {
        mvc.perform(get("/login?error"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Tên đăng nhập hoặc mật khẩu không hợp lệ.")))
            .andExpect(content().string(
                not(containsString("LockedException"))))
            .andExpect(content().string(
                not(containsString("DisabledException"))));
    }

    @Test
    void validUserCanSignIn() throws Exception {
        mvc.perform(formLogin()
                .user("active")
                .password("demo-pass"))
            .andExpect(authenticated().withUsername("active"));
    }
}
~~~

**Giải thích test:**

- `SecurityMockMvcRequestBuilders.formLogin()` dựng POST login theo Spring Security, hỗ trợ các tham số/CSRF thích hợp, nên không bị nhầm lỗi 403 do thiếu CSRF với lỗi credentials.
- Sáu trường hợp gồm sai password, user không tồn tại, disabled, locked, hết hạn account và hết hạn credentials đều phải trả **cùng redirect `/login?error`**.
- GET trang lỗi phải render thông điệp cố định và không xuất exception class. Đây là test cơ bản về output, **không chứng minh phòng được mọi kênh side-channel**.
- User `active` với password đúng phải xác thực thành công.
- Nếu chính sách của ứng dụng có API auth khác, thêm test riêng cho status/JSON và không bắt API client tự xử lý redirect của web form.

### 7.3. Chạy và quan sát

Cần Maven, JDK 17+ và khả năng tải dependency ở lần chạy đầu. Tại thư mục có `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Kết quả kỳ vọng: `mvn test` kết thúc với **BUILD SUCCESS** nếu dự án được tạo đúng và phụ thuộc được tải; số lượng test/log phụ thuộc máy chạy. Ví dụ này là mã thiết kế để chạy, **không phải kết quả Maven đã thực thi tại đây**.

Mở `http://localhost:8080/login`. Thử đăng nhập:

| Username | Password | Kỳ vọng sau POST |
| --- | --- | --- |
| `active` | `demo-pass` | Thành công, vào trang được bảo vệ |
| `active` | sai | Redirect `/login?error`, thông báo chung |
| `unknown-user` | `demo-pass` | Redirect giống hệt |
| `disabled` | `demo-pass` | Redirect giống hệt |
| `locked` | `demo-pass` | Redirect giống hệt |
| `accountExpired` | `demo-pass` | Redirect giống hệt |
| `credentialsExpired` | `demo-pass` | Redirect giống hệt |

**Lưu ý:** `unknown-user` không phải tài khoản trong `InMemoryUserDetailsManager`. Mọi user còn lại là account demo. UI không nên hé lộ loại lỗi nào xảy ra.

Kiểm tra nhanh bằng curl:

~~~bash
curl -i http://localhost:8080/public
# Dự kiến HTTP 200, body: public OK

curl -i http://localhost:8080/profile
# Dự kiến HTTP 302, Location chuyển tới /login

curl -i http://localhost:8080/login
# Dự kiến HTTP 200, HTML có form username/password và CSRF token

curl -i 'http://localhost:8080/login?error'
# Dự kiến HTTP 200, trang có thông báo lỗi chung
~~~

Muốn dùng curl để **POST** login đúng cách phải lấy CSRF token và giữ cookie/session từ GET form, sau đó gửi lại đúng token. Không đưa một lệnh `curl -d username=...` không có CSRF rồi khẳng định 403 đó là lỗi mật khẩu. Với minh họa này, browser và `MockMvc` thuận tiện hơn để xác thực hành vi chuẩn.

### 7.4. Nếu chỉ cần failureUrl thì rút gọn thế nào?

Thay cấu hình handler trong `SecurityConfig` bằng:

~~~java
.formLogin(form -> form
    .loginPage("/login")
    .loginProcessingUrl("/login")
    .failureUrl("/login?error")
    .permitAll()
)
~~~

Đó là **biến thể thay thế** phần `.formLogin(...)` trong bean `SecurityFilterChain`. Khi dùng biến thể này, bean `formFailureHandler()` không còn cần được inject vào chain. Đừng đưa cả hai tùy chọn vào cùng một cấu hình với kỳ vọng cùng có hiệu lực. Trang Thymeleaf và quy tắc thông điệp chung có thể giữ nguyên.

## 8. Audit, logging và quản lý lý do thất bại bên trong

### 8.1. Tách thông điệp public với mã lý do nội bộ

Một cách chia trách nhiệm:

~~~text
AuthenticationProvider
    |
    +-- tạo AuthenticationException nội bộ
            |
            v
AuthenticationFailureHandler
    |
    +-- Audit/metrics có kiểm soát
    |      -> mã lý do chuẩn hóa, không chứa raw secret
    |
    +-- Response công khai
           -> /login?error
           -> "Tên đăng nhập hoặc mật khẩu không hợp lệ."
~~~

Có thể cân nhắc các mã sự kiện nội bộ như `BAD_CREDENTIALS`, `ACCOUNT_DISABLED`, `ACCOUNT_LOCKED`; nhưng **đừng đẩy các mã này vào URL/query/body trả về cho client chưa xác thực**, và đừng thu thập dữ liệu cá nhân quá mức trong observability.

`AuthenticationFailureHandler` không đồng nghĩa là nơi tối ưu duy nhất để triển khai toàn bộ audit; Spring Security còn có các authentication events và tích hợp event publisher. Chọn cách phát sự kiện không gây mất thông tin khi có nhiều loại provider, nhưng phải đảm bảo không tạo lỗ hổng khi log sự kiện hoặc khi hệ thống audit bị lỗi.

### 8.2. Các mẫu logging nguy hiểm

~~~java
// KHÔNG làm như vậy:
log.warn("Login failed for {} with password {}: {}",
    username, rawPassword, exception.getMessage());

// Cách tối giản, không rò rỉ nội dung đăng nhập:
log.warn("Form sign-in failed");
~~~

Snippet này chỉ minh họa logging, không phải chương trình độc lập. Nếu cần biết tài khoản nào đang chịu tấn công, xem xét pseudonymization, truy cập có phân quyền, lưu giữ ngắn, cấu hình SIEM và trách nhiệm tuân thủ. Đừng coi log “nội bộ” là nơi có thể ghi tự do password hoặc session token.

### 8.3. Không làm lộ sự tồn tại user qua phản hồi phụ

Dù response cùng một URL, user enumeration vẫn có thể xảy ra nếu:

- User tồn tại được tính BCrypt chậm, user không tồn tại trả ngay; hoặc một trạng thái account bị từ chối trước khi password check.
- Response body/headers/cookie khác nhau đáng kể theo lý do.
- Endpoint reset password/email verification trả phản hồi khác khi username tồn tại.
- Bộ đếm rate-limit, CAPTCHA, khóa account có hành vi khác nhau dễ bị đoán.
- Lỗi account state được phản ánh trong URL khác hoặc thông điệp sau redirect.

Không thể khẳng định hệ thống đạt **constant-time login** chỉ vì dùng một failure handler. Cần phân tích threat model, giới hạn tần suất, kiểm thử response, giảm khác biệt timing không cần thiết và giám sát thực tế. Một số cơ chế provider có xử lý giảm timing leak cho username không tồn tại, nhưng không nên dựa mù vào đó cho mọi account state và mọi custom provider.

## 9. Trường hợp không nên áp dụng cùng chính sách

### 9.1. Đăng nhập sau bước xác minh danh tính

Sau khi người dùng đã qua một bước xác minh đáng tin cậy (ví dụ xác minh email/token phục hồi được ràng buộc đúng account), giao diện hỗ trợ có thể thông báo cụ thể hơn: tài khoản cần mở khóa, mật khẩu cần thay, người dùng cần liên hệ support. Đây là **luồng hậu xác minh**, không phải feedback ngay tại form login công khai. Với trạng thái nhạy cảm, cân nhắc gửi thông báo qua kênh đã được xác thực và hạn chế thời gian/token.

### 9.2. API và form login không dùng cùng kiểu response

API client thường muốn **401 + JSON** hoặc challenge phù hợp với authentication scheme thay vì `302 /login?error`. Trong hệ thống vừa web vừa API, có thể dùng các `SecurityFilterChain` khác nhau hoặc entry point/authentication filter phù hợp. `failureHandler` gắn cho `formLogin` không tự xử lý lỗi HTTP Basic/JWT ở chain API. Không dùng một handler redirect cho mọi cơ chế rồi làm client API khó debug.

### 9.3. Lỗi hệ thống khác lỗi credentials

Nếu database/identity provider bị outage, đó có thể là lỗi hệ thống chứ không phải mật khẩu sai. Phản hồi public vẫn không nên leak nội dung stack trace, SQL, user record hay secret. Tuy nhiên không nhất thiết giả vờ mọi lỗi hệ thống là `?error`: có thể dùng thông báo “Dịch vụ tạm thời không khả dụng” chung cho sự cố diện rộng, mã HTTP phù hợp và observability. Thiết kế dựa trên exception mapping/availability, không tùy tiện bắt mọi `Exception` và che bug.

### 9.4. CSRF/authorization 403

Một request `POST /login` thiếu CSRF token có thể bị `AccessDeniedHandler` xử lý và trả 403. Nó không phải tín hiệu “tài khoản disabled”. Không trộn CSRF failure vào bộ đếm sai password mà không có chủ ý, tránh khóa oan do browser thiếu token hoặc client cấu hình sai.

## 10. Checklist đưa vào dự án thật

**Cấu hình form login**

- Xác định rõ `loginPage`, `loginProcessingUrl`, `failureUrl` hoặc `failureHandler` và success behavior.
- Cho phép truy cập trang login/asset cần thiết trước đăng nhập; tránh vòng lặp redirect.
- Giữ CSRF phù hợp với form đăng nhập và session; kiểm thử hidden token.
- Nếu custom failure handler, **không** phản chiếu `AuthenticationException.message` vào public response.
- Dùng một URL lỗi cố định hoặc JSON code chung; không đưa trạng thái account vào query string.

**Bảo mật tài khoản**

- Sai password, username không tồn tại, locked, disabled, expired phải có **public feedback nhất quán** khi chưa xác minh danh tính.
- Không làm lộ user status qua response phụ, link reset, response header, size hoặc timing một cách không cần thiết.
- Thiết kế chống brute-force/credential stuffing, rate limit, MFA/step-up, kiểm soát session và cảnh báo.
- Xây luồng phục hồi sau khi **xác minh account ownership** để hỗ trợ user hợp pháp.

**Observability và kiểm thử**

- Audit có phân quyền, không log password/secret/token; hạn chế username/IP theo chính sách.
- Test response POST thất bại và GET trang lỗi, không chỉ test username/password đúng.
- Test CSRF missing là vấn đề riêng; test authorization 403 là vấn đề riêng.
- Test login success, saved request, logout và việc không lộ trạng thái account trong HTML.
- Nếu thay provider hoặc thêm SSO/OIDC/2FA, rà soát lại loại exception và failure path; đừng giả định cùng handler luôn bắt mọi loại lỗi.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Sửa như thế nào |
| --- | --- | --- |
| Render `exception.message` trên trang đăng nhập | Lộ disabled/locked/expired, giúp dò username | Chỉ render chuỗi lỗi chung theo cờ `?error` |
| Đặt `failureUrl("/login?locked")` theo exception | Lộ trạng thái qua URL/log | Redirect cố định `/login?error` |
| Khai báo custom `loginPage` nhưng không tạo GET view | 404/loop redirect | Tạo MVC controller + template cho trang login |
| Tạo `@PostMapping("/login")` và mong filter chuẩn không can thiệp | Flow trùng/xung đột | Chọn một cơ chế xử lý POST đăng nhập, thường để filter chuẩn xử lý |
| Quên CSRF token khi POST form | 403 không qua failure handler | Gửi CSRF token, không tắt CSRF vội |
| Cấu hình cả failureUrl và failureHandler mà không rõ ưu tiên | Hành vi dễ sai khác dự kiến | Dùng một handler duy nhất hoặc chỉ failureUrl |
| Trả message khác nhau cho username không tồn tại và password sai | User enumeration | Dùng cùng generic feedback, kiểm thử |
| Ghi raw password hoặc AuthenticationException đầy đủ vào log | Rò rỉ dữ liệu nhạy cảm | Audit tối thiểu, phân quyền, lọc secrets |
| Coi `failureHandler` xử lý mọi HTTP 403 | Không đúng với authorization/CSRF | Xem `AccessDeniedHandler` và CSRF handling riêng |
| Khóa account tự động chỉ nhờ custom handler | Thiếu state store/atomic update/rate limit | Thiết kế chính sách chống brute-force đầy đủ |
| Mặc định mọi thất bại form đều nên trả JSON | Browser UX bị phá | Form dùng redirect; API dùng response theo API contract |
| Chỉ kiểm tra status 302 mà không kiểm tra URL và HTML | Có thể vẫn lộ lý do ở query/page | Test redirect location, nội dung view và side channels |

## 12. Câu hỏi tự kiểm tra

**1. `failureUrl("/login?error")` giải quyết việc gì?**

Nó thiết lập nơi điều hướng sau khi authentication failure của form login. Browser thường nhận redirect tới URL ấy rồi tải lại trang login, nơi UI hiển thị một thông điệp lỗi chung.

**2. Khi nào cần `failureHandler(...)` thay vì `failureUrl(...)`?**

Khi cần custom response, audit/metrics hoặc nghiệp vụ xử lý thất bại bổ sung. Nếu vẫn redirect, có thể ủy quyền cho `SimpleUrlAuthenticationFailureHandler` để tránh tự viết lại chi tiết.

**3. Vì sao không dùng `exception.getMessage()` để hiển thị trên form login?**

Thông điệp có thể chứa trạng thái account, sự tồn tại username hoặc chi tiết kỹ thuật; attacker có thể dùng để dò account. Chỉ hiển thị thông điệp chung cho người chưa xác minh danh tính.

**4. Khi user bị `LockedException`, có nên chuyển tới `/login?error=locked` không?**

Không nên ở login công khai. Giữ cùng response với username/password sai; chuyển việc thông báo mở khóa sang luồng phục hồi đã xác minh người sở hữu.

**5. POST login bị 403 do thiếu CSRF token thì `failureHandler` có luôn được gọi không?**

Không. CSRF filter có thể từ chối trước bước kiểm tra credentials. Phải xác định điểm phát sinh lỗi và sửa CSRF token/request, không suy ra do account status.

**6. Đặt cùng redirect và cùng message đã chống hoàn toàn enumeration chưa?**

Chưa. Timing, response phụ, reset password endpoint, rate-limit behavior hoặc lỗi cấu hình khác vẫn có thể lộ. Cần threat modeling và các lớp phòng vệ bổ sung.

**7. Tại sao test `formLogin()` của Spring Security hữu ích?**

Nó gửi request login phù hợp và CSRF token khi cần, giúp test đúng authentication failure, không vô tình chỉ test lỗi 403 do thiếu CSRF.

**8. `failureHandler` có tự kiểm soát quyền vào `/admin` sau login không?**

Không. Nó xử lý authentication failure trong login flow, không thay `authorizeHttpRequests`, `AccessDeniedHandler` hoặc method security.

**9. Khi nào có thể đưa user đến trang đổi password?**

Sau một bước nhận diện/xác minh đáng tin cậy và theo chính sách an toàn. Đừng dùng lỗi khác biệt ở form công khai để khẳng định một tài khoản cụ thể đã hết hạn credentials.

**10. Trong ví dụ chạy được, vì sao các user disabled/locked/expired đều thấy cùng trang lỗi?**

Vì custom failure handler luôn redirect tới `/login?error`, còn Thymeleaf chỉ kiểm tra cờ `param.error` để hiển thị chuỗi cố định; lý do cụ thể của `AuthenticationException` không được công khai.

**Ghi nhớ:** **`failureUrl` là cách nhanh để redirect sau lỗi form login; `failureHandler` cho phép xử lý linh hoạt hơn. Dù dùng cách nào, hãy giữ thông báo công khai chung, không render exception hoặc trạng thái tài khoản cho người chưa xác minh, và phân biệt authentication failure với CSRF/authorization failure.**