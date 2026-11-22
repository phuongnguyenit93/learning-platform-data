# Áp dụng SessionAuthenticationStrategy trong cơ chế đăng nhập JSON tự viết

## Mục tiêu và bối cảnh

Giả sử ứng dụng **Spring Boot Servlet** cung cấp endpoint \`POST /api/login\`, nhận JSON gồm \`username\` và \`password\`. Người dùng đăng nhập thành công thì trình duyệt gửi cookie phiên ở các request tiếp theo, và server nhận biết người dùng đã đăng nhập. Để tự triển khai luồng này an toàn với Spring Security, chỉ gọi \`AuthenticationManager.authenticate(...)\` là **chưa đủ**.

Sau bài này, bạn có thể:

1. Giải thích vai trò của **SessionAuthenticationStrategy**, thời điểm gọi và điểm khác với \`AuthenticationManager\` cùng \`SecurityContextRepository\`.
2. Chủ động áp dụng bảo vệ **session fixation** khi xác thực thành công qua controller hoặc filter JSON do bạn viết.
3. Hiểu vì sao giới hạn phiên đồng thời và xoay vòng CSRF token cũng cần được xét trong luồng tự viết.
4. Viết và thử một ví dụ **Java 17+ / Spring Boot 3.x / Spring Security 6.x** lưu xác thực qua \`HttpSession\`, có CSRF và đăng xuất.
5. Phát hiện các lỗi như lưu context trước khi kiểm tra session strategy, chỉ đặt \`SecurityContextHolder\` mà quên lưu, hoặc kỳ vọng session strategy tự chạy.

## 1. Vấn đề xuất hiện khi tự làm đăng nhập JSON

Một luồng JSON đăng nhập tối giản thường được viết như sau:

~~~java
// Đoạn minh họa CHƯA đầy đủ, không phải một endpoint độc lập.
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Đoạn này có thể xác thực đúng mật khẩu và thiết lập danh tính **trong request hiện tại**, nhưng còn thiếu hai nhóm trách nhiệm:

- **Xử lý chính sách phiên khi có phiên đăng nhập mới:** đổi ID phiên để chống **session fixation**, kiểm tra số lượng phiên đồng thời, đăng ký phiên, vô hiệu hóa CSRF token cũ, v.v. Đây là nơi **SessionAuthenticationStrategy** tham gia.
- **Lưu trạng thái xác thực cho request sau:** phải gọi \`SecurityContextRepository.saveContext(...)\` nếu muốn khôi phục \`Authentication\` từ phiên. \`SecurityContextHolder\` thông thường chỉ giữ context cho luồng xử lý request hiện tại.

Trong Spring Security 6, \`SecurityContextHolderFilter\` thường **đọc** context từ repository; nó không tự lưu mọi thay đổi của bạn. \`SessionManagementFilter\` cũng **không còn là filter mặc định** để phát hiện một request vừa xác thực và gọi session strategy. Do đó, với cơ chế JSON tự viết, **cơ chế xác thực của bạn phải chủ động thực hiện các bước cần thiết**.

So sánh trách nhiệm:

| Thành phần | Làm gì? | Không tự làm gì? |
| --- | --- | --- |
| \`AuthenticationManager\` | Kiểm tra credential và trả \`Authentication\` đã xác thực hoặc ném \`AuthenticationException\` | Không tự đảm bảo xoay session ID hoặc lưu context cho controller |
| \`SessionAuthenticationStrategy\` | Chạy các quy tắc liên quan tới phiên khi **vừa xác thực thành công** | Không kiểm tra mật khẩu và không mặc nhiên lưu \`SecurityContext\` |
| \`SecurityContextHolder\` | Cho code trong request hiện tại truy cập \`Authentication\` | Không phải kho lưu trạng thái giữa request |
| \`SecurityContextRepository\` | Lưu/đọc \`SecurityContext\` giữa request, ví dụ từ \`HttpSession\` | Không quyết định có chấp nhận phiên đăng nhập mới theo chính sách cạnh tranh hay không |
| \`SessionCreationPolicy\` | Định hướng Spring Security tạo/dùng session | Không thay thế lệnh gọi \`SessionAuthenticationStrategy.onAuthentication(...)\` |

**Nguyên tắc:** Nếu đăng nhập tạo một phiên được tin cậy lâu dài, hãy coi \`authenticate\`, **session strategy**, **set context** và **save context** là những bước riêng biệt, chạy đúng thứ tự.

## 2. Hợp đồng của SessionAuthenticationStrategy

Interface chính nằm trong package:

\`org.springframework.security.web.authentication.session.SessionAuthenticationStrategy\`

Phương thức:

~~~java
void onAuthentication(
    Authentication authentication,
    HttpServletRequest request,
    HttpServletResponse response
) throws SessionAuthenticationException;
~~~

Trong ứng dụng thực tế:

- \`authentication\` phải là kết quả **đã xác thực thành công**, chẳng hạn từ \`AuthenticationManager.authenticate(...)\`; không truyền token username/password chưa xác thực.
- \`request\` và \`response\` là cặp servlet của **request đăng nhập thật**. Strategy có thể cần \`HttpSession\` hoặc thay đổi session ID/cookie.
- Gọi **một lần cho mỗi lần đăng nhập thành công**, sau bước kiểm tra credential và **trước khi lưu context hoặc trả response thành công**.
- \`SessionAuthenticationException\` báo phiên mới không được chấp nhận, ví dụ vượt hạn mức phiên. Khi đó **không lưu \`Authentication\` mới**, không trả phản hồi “login thành công”. Cần map ngoại lệ sang phản hồi API thích hợp và tránh lộ thông tin nội bộ.

Chiến lược không phải thứ nên gọi ở mọi request đã đăng nhập. Nếu gọi lại trên mỗi \`GET /api/me\`, session ID có thể bị đổi liên tục, còn logic đếm/đăng ký phiên có thể bị thực hiện sai thời điểm.

### Thứ tự thành công

~~~text
POST /api/login + JSON credential + CSRF token hợp lệ
    |
    +--> SecurityFilterChain / CsrfFilter kiểm tra request
    |
    +--> Controller hoặc custom authentication filter
           |
           +--> AuthenticationManager.authenticate(...)
           |      |
           |      +-- SAI --> AuthenticationException --> 401, không lưu context mới
           |      |
           |      +-- ĐÚNG --> Authentication đã xác thực
           |
           +--> SessionAuthenticationStrategy.onAuthentication(...)
           |      |
           |      +-- TỪ CHỐI --> SessionAuthenticationException --> không lưu context mới
           |      |
           |      +-- CHẤP NHẬN --> áp dụng quy tắc phiên
           |
           +--> tạo SecurityContext mới
           +--> đặt Authentication vào SecurityContext
           +--> SecurityContextHolder.setContext(context)
           +--> SecurityContextRepository.saveContext(context, request, response)
           +--> trả JSON thành công, client giữ cookie phiên
~~~

Dùng **context mới** sau khi xác thực thành công giúp tránh sửa trực tiếp context cũ được tải từ phiên trước. Đặc biệt với session đã tồn tại, việc gắn principal mới vào một context dùng chung rồi mới kiểm tra giới hạn phiên có thể dẫn đến lưu nhầm danh tính nếu request thất bại.

## 3. Các SessionAuthenticationStrategy quan trọng

### 3.1. Bảo vệ session fixation

**Session fixation** là trường hợp kẻ tấn công biết hoặc kiểm soát một session ID trước khi nạn nhân đăng nhập, rồi lợi dụng việc server tiếp tục sử dụng chính ID đó sau xác thực.

Với Servlet container hiện đại, cách thông dụng là:

~~~java
SessionAuthenticationStrategy fixation =
    new ChangeSessionIdAuthenticationStrategy();
~~~

Khi login thành công, strategy dùng khả năng **\`HttpServletRequest.changeSessionId()\`** của container để thay ID của phiên **nếu phiên hợp lệ đã tồn tại**. Các thuộc tính phiên vẫn được giữ khi thay ID; cookie phiên cần được client nhận và gửi ở các request tiếp theo.

Điều kiện cần nhớ:

- Nếu trước login **chưa có HttpSession**, có thể chưa có ID cũ để đổi. Repository có thể tạo một session mới khi lưu context. Vì vậy không nên kiểm thử bằng quy tắc cứng “mọi request login phải phát hai session ID”.
- Nếu cookie phiên trước login tồn tại, hãy so sánh ID phiên trước/sau xác thực: ID phải được đổi khi strategy thực sự bảo vệ phiên đã có.
- Không nhầm \`changeSessionId\` với \`invalidate()\`: invalidate thủ công có thể làm mất dữ liệu phiên và CSRF token theo cách không mong muốn.
- \`SessionFixationProtectionStrategy\` là cách khác, có thể tạo phiên mới/migrate thuộc tính. \`ChangeSessionIdAuthenticationStrategy\` phù hợp Servlet 3.1+; Spring Boot 3.x dùng Jakarta Servlet hiện đại.

**Lưu ý:** Cấu hình DSL \`sessionManagement(session -> session.sessionFixation(...))\` thường được tích hợp cho các authentication filter chuẩn mà Spring Security quản lý; một controller JSON tự viết không được bảo đảm sẽ tự chạy hành động đó. Controller phải gọi strategy được thiết kế cho mình.

### 3.2. Kiểm soát số phiên đăng nhập đồng thời

Ba lớp thường phối hợp:

- \`ConcurrentSessionControlAuthenticationStrategy\`: kiểm tra hạn mức session của principal dựa trên \`SessionRegistry\`; có thể từ chối phiên mới hoặc đánh dấu phiên cũ đã hết hiệu lực.
- \`ChangeSessionIdAuthenticationStrategy\` hoặc \`SessionFixationProtectionStrategy\`: bảo vệ session ID sau khi được phép xác thực.
- \`RegisterSessionAuthenticationStrategy\`: ghi nhận phiên mới vào \`SessionRegistry\` sau khi có ID cuối cùng.

Thứ tự đúng trong **CompositeSessionAuthenticationStrategy** là:

~~~text
[Kiểm tra giới hạn phiên] -> [Bảo vệ session fixation] -> [Đăng ký session]
~~~

Lý do: nếu bị từ chối vì quá số phiên, không nên đổi/tạo phiên rồi mới từ chối. Khi đăng ký, phải đăng ký ID **sau khi** bảo vệ fixation.

Muốn triển khai đầy đủ giới hạn phiên cần thêm quản lý sự kiện hủy/hết hạn session (thường \`HttpSessionEventPublisher\`), các filter phù hợp để xử lý phiên bị đánh dấu hết hạn và cơ chế chia sẻ session/registry nếu ứng dụng có nhiều instance. **Chỉ thêm một strategy vào controller không tự hoàn tất toàn bộ quản lý concurrent sessions.**

### 3.3. CSRF khi đăng nhập dựa trên cookie/session

JSON **không** tự động loại bỏ rủi ro CSRF. Nếu trình duyệt gửi \`JSESSIONID\` tự động, các request thay đổi trạng thái vẫn phải được bảo vệ theo threat model.

\`CsrfAuthenticationStrategy\` dùng \`CsrfTokenRepository\` để **xóa CSRF token cũ khi xác thực thành công**. Sau login, client lấy CSRF token mới trước thao tác POST/PUT/PATCH/DELETE tiếp theo. Strategy này khác với \`CsrfFilter\`, vốn kiểm tra token trên **request đang đến**.

~~~java
CsrfTokenRepository tokens = new HttpSessionCsrfTokenRepository();
SessionAuthenticationStrategy csrfRotation =
    new CsrfAuthenticationStrategy(tokens);
~~~

Nếu dùng strategy này trong custom login, **\`CsrfFilter\` và \`CsrfAuthenticationStrategy\` phải dùng đúng cùng một \`CsrfTokenRepository\`**. Đừng vô hiệu hóa CSRF toàn ứng dụng chỉ để POST JSON login thành công.

### 3.4. Ghép chiến lược theo thứ tự

\`CompositeSessionAuthenticationStrategy\` gọi các delegate tuần tự; nếu một bước ném \`SessionAuthenticationException\` thì các bước sau không chạy.

Ví dụ nhỏ cho phiên đăng nhập cookie, chưa áp dụng giới hạn đồng thời:

~~~java
SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        new ChangeSessionIdAuthenticationStrategy(),
        new CsrfAuthenticationStrategy(csrfTokenRepository)
    ));
~~~

Ví dụ hoàn chỉnh dưới đây dùng đúng cấu hình này. Với giới hạn phiên đồng thời, thêm các strategy liên quan theo thứ tự ở mục 3.2, kèm hạ tầng registry và filter tương ứng.

## 4. Ví dụ Java 17+: JSON login có session fixation protection và CSRF

**Môi trường:** một project **Spring Boot 3.5.x / Spring Security 6.5.x**, Java 17+, loại **Servlet**. Tạo project bằng Spring Initializr với hai starter \`Spring Web\` và \`Spring Security\`. Nếu dùng Gradle, dependencies cần có là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đặt file Java dưới đường dẫn:

\`src/main/java/com/example/jsonlogin/JsonLoginApplication.java\`

~~~java
package com.example.jsonlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationException;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("change-me"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokenRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(csrfTokenRepository)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository,
            CsrfTokenRepository csrfTokenRepository) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .securityContext(context -> context
                .securityContextRepository(securityContextRepository)
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfTokenRepository)
            )
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED))
            )
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT))
            );

        return http.build();
    }

    public record LoginRequest(String username, String password) {}
    public record LoginResponse(String username) {}
    public record MeResponse(String username) {}
    public record ErrorResponse(String error) {}

    @RestController
    public static class Api {
        private final AuthenticationManager authenticationManager;
        private final SessionAuthenticationStrategy sessionStrategy;
        private final SecurityContextRepository securityContextRepository;

        public Api(AuthenticationManager authenticationManager,
                   SessionAuthenticationStrategy sessionStrategy,
                   SecurityContextRepository securityContextRepository) {
            this.authenticationManager = authenticationManager;
            this.sessionStrategy = sessionStrategy;
            this.securityContextRepository = securityContextRepository;
        }

        @GetMapping("/csrf")
        public CsrfToken csrf(CsrfToken token) {
            return token;
        }

        @PostMapping("/api/login")
        public ResponseEntity<?> login(@RequestBody LoginRequest body,
                                       HttpServletRequest request,
                                       HttpServletResponse response) {
            try {
                Authentication authentication = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                        body.username(), body.password()
                    )
                );

                // Chỉ chạy sau khi credential đã được xác thực.
                sessionStrategy.onAuthentication(authentication, request, response);

                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(authentication);
                SecurityContextHolder.setContext(context);

                // Bắt buộc nếu muốn khôi phục đăng nhập ở request tiếp theo.
                securityContextRepository.saveContext(context, request, response);

                return ResponseEntity.ok(new LoginResponse(authentication.getName()));
            } catch (SessionAuthenticationException ex) {
                SecurityContextHolder.clearContext();
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(new ErrorResponse("session_rejected"));
            } catch (AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(new ErrorResponse("invalid_credentials"));
            }
        }

        @GetMapping("/api/me")
        public MeResponse me(Authentication authentication) {
            return new MeResponse(authentication.getName());
        }
    }
}
~~~

### 4.1. Tại sao ví dụ phải khai báo những bean này?

**\`AuthenticationManager\` và \`DaoAuthenticationProvider\`:** nhận username/password của JSON login, dùng \`UserDetailsService\` và \`PasswordEncoder\` xác thực. \`InMemoryUserDetailsManager\` cùng tài khoản \`demo/change-me\` chỉ để chạy bài học. Đây không phải hệ thống người dùng production.

**\`HttpSessionSecurityContextRepository\`:** là repository được dùng **cả khi SecurityFilterChain tải context và khi controller lưu context**. Nếu dùng repository A để lưu nhưng filter đọc từ repository B, login có thể trả 200 mà request sau vẫn là anonymous.

**\`SessionAuthenticationStrategy\`:** composite chạy bảo vệ fixation rồi xóa token CSRF cũ. Controller **phải gọi trực tiếp** \`onAuthentication\`; bean tồn tại một mình không có nghĩa controller tự chạy nó.

**\`SessionCreationPolicy.IF_REQUIRED\`:** phù hợp với cơ chế đăng nhập giữ phiên qua cookie. Không dùng \`STATELESS\` cho ví dụ này, vì nó làm thay đổi chính sách khôi phục SecurityContext qua HttpSession.

**\`CsrfTokenRepository\`:** đồng nhất giữa kiểm tra request và xoay CSRF token sau xác thực. Endpoint GET \`/csrf\` trả token để client đưa vào header của POST login. Token được lưu ở server trong session và gắn với cookie cùng trình duyệt.

**\`formLogin(...disable())\` và \`httpBasic(...disable())\`:** ví dụ tập trung vào một endpoint JSON do ứng dụng sở hữu. Có thể bật các cơ chế khác trong hệ thống thực, nhưng cần phân biệt chính sách riêng của từng cơ chế.

**\`requestCache(...disable())\`:** tránh lưu URL yêu cầu được bảo vệ để điều hướng lại sau đăng nhập; ví dụ API trả 401/JSON và tự quyết định request tiếp theo. Đây là lựa chọn API, không phải yêu cầu bắt buộc của \`SessionAuthenticationStrategy\`.

**\`logoutUrl("/api/logout")\`:** dùng logout support của Spring Security thay vì chỉ \`SecurityContextHolder.clearContext()\`. Logout mặc định xử lý làm sạch context và vô hiệu hóa phiên; POST logout vẫn cần CSRF token hợp lệ.

**\`SecurityContextHolder\`:** dùng API tĩnh cho ví dụ nhỏ để dễ đọc. Trong ứng dụng có cấu hình chiến lược holder đặc biệt hoặc nhiều application context, có thể tiêm \`SecurityContextHolderStrategy\` và sử dụng nhất quán.

### 4.2. Chạy ví dụ

Trong thư mục project Spring Boot chứa \`build.gradle\`, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows, dùng \`.\gradlew.bat bootRun\`; nếu project được tạo bằng Maven, dùng \`./mvnw spring-boot:run\`. File Java này cần classpath Spring Boot/Spring Security do build tool quản lý, nên **không** chạy bằng \`javac JsonLoginApplication.java\` độc lập.

Ví dụ mặc định lắng nghe \`http://localhost:8080\`. Các lệnh dưới đây dùng **Bash + curl + jq**; trên Windows có thể dùng Git Bash/WSL, hoặc dùng \`curl.exe\` và đọc token JSON bằng PowerShell.

**Bước 1: Lấy CSRF token và lưu cookie trước khi đăng nhập.**

~~~bash
csrf=$(curl -sS -c cookies.txt http://localhost:8080/csrf | jq -r .token)
printf 'CSRF token loaded: %s\n' "$([ -n "$csrf" ] && echo yes || echo no)"
# CSRF token loaded: yes
~~~

Việc \`GET /csrf\` truy cập token khiến repository tạo hoặc đọc token và có thể tạo HttpSession; \`cookies.txt\` giữ \`JSESSIONID\`. Không in token/credential vào log trong production.

**Bước 2: POST JSON login với cùng cookie và CSRF token.**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $csrf" \
  --data '{"username":"demo","password":"change-me"}' \
  http://localhost:8080/api/login
~~~

Kết quả mong đợi là **HTTP 200** và body JSON:

~~~json
{"username":"demo"}
~~~

Nếu session ID trước login hợp lệ, \`ChangeSessionIdAuthenticationStrategy\` đổi ID khi login thành công. Tùy container và cookie policy, response có thể gửi lại \`Set-Cookie: JSESSIONID=...\`. Tùy lệnh curl, \`-c cookies.txt\` lưu lại cookie được cập nhật.

**Bước 3: Kiểm chứng context được khôi phục trong request kế tiếp.**

~~~bash
curl -sS -b cookies.txt http://localhost:8080/api/me
# {"username":"demo"}
~~~

\`/api/me\` không nhận username/password và không gọi \`authenticate\` lại. Spring Security tải context đã lưu từ session dựa vào cookie.

**Bước 4: Không gửi cookie thì không có đăng nhập được khôi phục.**

~~~bash
curl -i http://localhost:8080/api/me
# HTTP/1.1 401 Unauthorized (trích dòng trạng thái)
~~~

Đó là kết quả của entry point đã cấu hình: request thiếu danh tính hợp lệ.

**Bước 5: Lấy CSRF token mới rồi logout.**

~~~bash
csrf=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r .token)

curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8080/api/logout
# HTTP/1.1 204 No Content (trích dòng trạng thái)

curl -i -b cookies.txt http://localhost:8080/api/me
# HTTP/1.1 401 Unauthorized (trích dòng trạng thái)
~~~

Sau login, CSRF token trước login đã bị \`CsrfAuthenticationStrategy\` xóa, vì vậy client phải lấy token mới trước các request ghi dữ liệu tiếp theo. Khi logout, session được vô hiệu hóa; cookie cũ không còn cung cấp Authentication hợp lệ.

### 4.3. Các trường hợp thất bại cần phân biệt

| Trường hợp | Phản hồi mong đợi | Điểm cần kiểm chứng |
| --- | --- | --- |
| POST login **không có CSRF token** | **403**, request bị chặn trước controller | Cơ chế chống CSRF hoạt động |
| POST login có CSRF token nhưng sai password | **401** với \`invalid_credentials\` | \`onAuthentication\` không được chạy; không lưu context mới |
| POST login thành công | **200**, tạo/lưu context và cookie phiên | Strategy chạy trước \`saveContext\` |
| POST login bị strategy từ chối (khi cấu hình giới hạn phiên) | **401** với \`session_rejected\` trong ví dụ | Không tạo/lưu phiên đăng nhập mới |
| GET /api/me với cookie phiên còn hợp lệ | **200** | Đọc được context từ \`HttpSession\` |
| GET /api/me không có cookie | **401** | Không có context xác thực |
| POST logout có cookie nhưng thiếu/CSRF sai | **403** | CSRF bảo vệ cả logout |
| POST logout hợp lệ | **204** | Phiên và context được hủy |

Mã HTTP cho lỗi session policy là lựa chọn thiết kế API; ví dụ dùng **401** để đơn giản. API thực tế có thể dùng mã và error body khác theo hợp đồng với client. Phân biệt lỗi credential và lỗi giới hạn phiên trong log nội bộ, nhưng đừng phản hồi thông tin có thể giúp dò tài khoản.

## 5. Mở rộng: giới hạn một phiên mỗi người dùng

Nếu yêu cầu chỉ cho một session đăng nhập hoạt động, có thể tạo composite mạnh hơn. Đoạn sau **chỉ minh họa cách ghép strategy**, chưa phải cấu hình ứng dụng hoàn chỉnh:

~~~java
// Ví dụ thành phần cấu hình; cần SessionRegistry và
// hạ tầng quản lý lifecycle/concurrency tương ứng.
ConcurrentSessionControlAuthenticationStrategy concurrency =
    new ConcurrentSessionControlAuthenticationStrategy(sessionRegistry);
concurrency.setMaximumSessions(1);
concurrency.setExceptionIfMaximumExceeded(true);

SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        concurrency,
        new ChangeSessionIdAuthenticationStrategy(),
        new RegisterSessionAuthenticationStrategy(sessionRegistry),
        new CsrfAuthenticationStrategy(csrfTokenRepository)
    ));
~~~

Để dùng, còn cần import hai class \`ConcurrentSessionControlAuthenticationStrategy\` và \`RegisterSessionAuthenticationStrategy\` từ package \`org.springframework.security.web.authentication.session\`, cùng một \`SessionRegistry\` được cấu hình đúng. Thường dùng \`SessionRegistryImpl\` với \`HttpSessionEventPublisher\` để cập nhật khi session hết hạn/hủy; khi dùng chính sách loại phiên cũ, cần cấu hình filter nhận biết phiên đã bị đánh dấu hết hạn. Với nhiều instance, phải xét đồng bộ dữ liệu session/registry và \`Spring Session\` hoặc hạ tầng tương đương.

Nếu dùng \`UserDetails\` tùy biến làm principal cho session registry trong bộ nhớ, cần triển khai \`equals/hashCode\` nhất quán để cùng một người dùng được nhận diện đúng. Không coi \`.sessionManagement(s -> s.maximumSessions(1))\` là đủ cho **controller JSON tự viết** nếu bạn không gọi composite strategy đúng cách; cơ chế chuẩn và custom controller có vòng đời xác thực khác nhau.

**Trật tự xử lý rất quan trọng:** \`concurrency\` có thể từ chối ngay từ đầu; chỉ khi được chấp nhận mới đổi ID, đăng ký session, xóa CSRF token cũ, rồi tạo và lưu context.

## 6. Nếu đăng nhập bằng custom filter thay vì REST controller

Bạn có thể tự làm một filter đọc JSON từ request:

- Nếu kế thừa \`AbstractAuthenticationProcessingFilter\`, thiết lập \`setSessionAuthenticationStrategy(...)\` để filter gọi strategy sau \`attemptAuthentication\` thành công; đồng thời cấu hình \`setSecurityContextRepository(...)\` để lưu context trên success. Định nghĩa success/failure handler trả JSON thay vì redirect.
- Nếu viết filter độc lập trực tiếp từ \`OncePerRequestFilter\`, bạn phải tự phối hợp mọi bước: đọc credential, authenticate, gọi strategy sau success, set/save context, xử lý ngoại lệ, trả status và kết thúc filter chain phù hợp.
- Không tự tạo thêm \`SessionManagementFilter\` chỉ để bù cho lời gọi thiếu. Trong Spring Security 6, đường đi khuyến nghị là authentication mechanism chủ động gọi strategy; ép filter kiểu cũ có thể gây chạy hai lần hoặc cấu hình khó hiểu.

Cũng cần nhớ **CSRF filter chạy trước endpoint login**, và endpoint login tự viết phải được match đúng SecurityFilterChain. Nếu ứng dụng có nhiều chain, kiểm tra security matcher của từng chain; rule \`permitAll()\` không bảo đảm request đi qua chain mà bạn dự kiến.

## 7. Chính sách phiên, lưu context và bảo mật thực tế

| \`SessionCreationPolicy\` | Tác động cho JSON login có cookie |
| --- | --- |
| \`ALWAYS\` | Spring Security chủ động tạo phiên; thường không cần thiết cho API JSON |
| \`IF_REQUIRED\` | Cho phép tạo phiên khi lưu context; phù hợp ví dụ |
| \`NEVER\` | Spring Security không chủ động tạo session nhưng có thể tận dụng session đã có; khó bảo đảm luồng login tạo phiên khi chưa có |
| \`STATELESS\` | Spring Security không dùng session để khôi phục SecurityContext; không hợp luồng “login một lần, dùng JSESSIONID ở request sau” |

\`SessionAuthenticationStrategy\` không biến một API stateless thành API có session. Hãy chọn mô hình có trạng thái hoặc không trạng thái trước, rồi cấu hình policy, repository và strategy cho **cùng một mô hình**.

Những điểm cần kiểm soát thêm trong hệ thống thật:

- **HTTPS/TLS và cookie:** chỉ gửi credential và session cookie qua TLS; cấu hình \`Secure\`, \`HttpOnly\`, \`SameSite\`, domain/path và thời hạn cookie theo client và threat model. Không để session ID/CSRF token lộ trong URL hoặc log.
- **Đăng nhập sai liên tiếp:** rate limit, chống brute force và thông báo lỗi không tiết lộ user tồn tại hay không. Dùng \`PasswordEncoder\` mạnh; không nhúng tài khoản thật trong source.
- **Logout, revoke, timeout:** phân biệt xóa \`SecurityContextHolder\` của request với hủy session. Cần xử lý hết hạn phiên, invalidation, session registry và đồng bộ nếu triển khai cluster.
- **CSRF:** request dựa trên cookie trình duyệt cần đánh giá nguy cơ CSRF kể cả khi request body là JSON. Client phải lấy CSRF token mới sau login/logout khi áp dụng \`CsrfAuthenticationStrategy\`.
- **Dùng \`SessionAuthenticationStrategy\` sau đúng thời điểm:** nếu có MFA, chỉ coi phiên đăng nhập đầy đủ thành công khi các bước bắt buộc đã đạt điều kiện; đừng đánh dấu phiên hoàn tất quá sớm.
- **Đăng nhập lại trên cùng browser:** có thể đang có \`Authentication\` cũ trong session. Không sửa trực tiếp context cũ khi chưa xác thực và chưa được strategy chấp nhận.
- **Quan sát lỗi:** log loại lỗi, kết quả, correlation ID và session lifecycle bằng dữ liệu đã ẩn danh; không ghi mật khẩu, raw CSRF token hoặc \`JSESSIONID\`.

## 8. Những sai lầm thường gặp

**Sai 1 — Chỉ set Authentication vào SecurityContextHolder.** Request login trả 200 nhưng GET sau đó nhận 401. Nguyên nhân thường là quên \`SecurityContextRepository.saveContext(...)\` hoặc cấu hình filter đọc repository khác.

**Sai 2 — Gọi strategy trước khi kiểm tra mật khẩu.** Điều này có thể đổi ID/tạo phiên cho một yêu cầu chưa đủ tin cậy. Hãy lấy \`Authentication\` thành công rồi mới chạy strategy.

**Sai 3 — Lưu context trước rồi mới gọi strategy.** Nếu session limit từ chối, bạn có nguy cơ đã lưu Authentication đáng lẽ không được phép. Hãy gọi strategy trước khi set/save context mới.

**Sai 4 — Chỉ cấu hình \`sessionFixation().changeSessionId()\` nhưng custom controller không gọi strategy.** DSL cấu hình hỗ trợ framework nhưng không tự chèn lời gọi vào controller do bạn viết.

**Sai 5 — Tự \`request.getSession().invalidate()\` sau login mà không hiểu tác động.** Có thể hủy CSRF token, saved request hoặc dữ liệu phiên đang cần. Dùng chiến lược fixation do Spring Security cung cấp.

**Sai 6 — Dùng \`STATELESS\` đồng thời mong cookie phiên khôi phục đăng nhập.** Hai quyết định này mâu thuẫn với mục tiêu ví dụ. Đọc chính sách phiên và repository thực tế.

**Sai 7 — Dùng \`NullAuthenticatedSessionStrategy\` rồi mặc nhiên nghĩ có bảo vệ fixation.** Strategy này không thực hiện hành động; chỉ dùng khi bạn có lý do rõ ràng, chẳng hạn mô hình không dùng session.

**Sai 8 — Chỉ gọi \`RegisterSessionAuthenticationStrategy\` mà không dùng cùng registry/filter lifecycle.** Sổ theo dõi phiên có thể sai hoặc không thực thi được chính sách loại phiên khi hết hạn.

**Sai 9 — Tắt CSRF để POST login thuận tiện.** JSON login dùng cookie vẫn cần CSRF theo threat model. Hãy lấy token hợp lệ, rồi refresh token sau login/logout.

**Sai 10 — Xem \`SessionAuthenticationException\` như lỗi mật khẩu.** Cần xác định lỗi phiên và chính sách ứng dụng; không cho thấy đăng nhập đã thành công, nhưng cũng không biến nó thành lý do để báo sai hệ thống xác thực.

## 9. Bài tập tự kiểm tra

1. **Người dùng nhập mật khẩu đúng, nhưng tài khoản đã đạt giới hạn session và cấu hình từ chối phiên mới.** Bạn đặt lời gọi nào trước \`saveContext\`?  
   **Đáp án:** \`sessionAuthenticationStrategy.onAuthentication(authentication, request, response)\`; nếu strategy ném \`SessionAuthenticationException\` thì không lưu context đăng nhập mới.

2. **Controller login trả 200, nhưng request sau gửi \`JSESSIONID\` vẫn nhận 401.** Hai điểm đầu tiên cần kiểm tra?  
   **Đáp án:** \`saveContext(...)\` đã được gọi chưa, và \`SecurityFilterChain\` có đọc từ cùng \`SecurityContextRepository\` không.

3. **Vì sao session ID có thể không đổi ở lần login đầu khi trước đó chưa có session?**  
   **Đáp án:** Không có session ID cũ để xoay. \`ChangeSessionIdAuthenticationStrategy\` xử lý phiên đã tồn tại; repository có thể tạo phiên mới khi lưu context.

4. **Vì sao thứ tự \`ConcurrentSessionControlAuthenticationStrategy\` → fixation → \`RegisterSessionAuthenticationStrategy\` quan trọng?**  
   **Đáp án:** Từ chối sớm trước khi phát sinh phiên mới, sau đó bảo vệ ID và đăng ký chính ID cuối cùng.

5. **POST login mang JSON, trình duyệt dùng cookie phiên; có thể tắt CSRF chỉ vì request là JSON không?**  
   **Đáp án:** Không. Cần đánh giá việc browser tự gửi cookie; thường phải giữ CSRF và sử dụng token trong header.

6. **Sau login, client gửi token CSRF cũ và nhận 403. Đây có thể là hành vi đúng không?**  
   **Đáp án:** Có. \`CsrfAuthenticationStrategy\` xóa token cũ khi xác thực; client cần gọi \`GET /csrf\` để nhận token mới.

## Tài liệu chính thức

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SessionAuthenticationStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html)
- [Spring Security — CompositeSessionAuthenticationStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/CompositeSessionAuthenticationStrategy.html)
- [Spring Security 6.5 — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
