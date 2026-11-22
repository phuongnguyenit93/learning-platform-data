# BasicAuthenticationFilter và cách gọi AuthenticationManager

> **Phạm vi:** HTTP Basic trong **Spring Security Servlet** (Spring Security 6.x, Spring Boot 3.x, Java 17+). Bài học tập trung vào việc `BasicAuthenticationFilter` lấy thông tin xác thực từ HTTP request, quyết định khi nào gọi `AuthenticationManager.authenticate(...)`, xử lý kết quả và chuyển request đến bước phân quyền. Đây là cơ chế của Servlet `SecurityFilterChain`; WebFlux sử dụng các thành phần khác.

## 1. Vấn đề mà BasicAuthenticationFilter giải quyết

HTTP Basic cho phép client gửi tên người dùng và mật khẩu trong header:

```http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic YWxpY2U6c2VjcmV0MTIz
```

Phần sau chữ `Basic` là Base64 của chuỗi `alice:secret123`. **Base64 chỉ là mã hóa biểu diễn, không bảo mật mật khẩu.** HTTPS/TLS là bắt buộc trong ứng dụng thực tế; không đưa credential vào URL, log hoặc công cụ giám sát.

Một `HttpServletRequest` chứa header trên chưa có nghĩa là người dùng đã được xác thực. `BasicAuthenticationFilter` phải chuyển credential thành một đối tượng `Authentication` ban đầu, nhờ `AuthenticationManager` xác minh nó rồi đặt kết quả xác thực thành công vào `SecurityContextHolder` để các filter phía sau biết danh tính người dùng.

**Phân biệt trách nhiệm:**

| Thành phần | Trách nhiệm |
| --- | --- |
| `BasicAuthenticationFilter` | Nhận diện header `Authorization: Basic ...`, chuyển thành yêu cầu xác thực, gọi manager, cập nhật/xóa context và xử lý lỗi xác thực. |
| `BasicAuthenticationConverter` | Chuyển header Basic hợp lệ thành `UsernamePasswordAuthenticationToken` chưa xác thực; trả `null` nếu không có Basic header. |
| `AuthenticationManager` | Hợp đồng `authenticate(Authentication)`; trả `Authentication` đã xác thực hoặc ném `AuthenticationException`. |
| `ProviderManager` | Triển khai `AuthenticationManager` thường gặp; thử các `AuthenticationProvider` phù hợp. |
| `DaoAuthenticationProvider` | Xác thực username/password nhờ `UserDetailsService` và `PasswordEncoder`. |
| `SecurityContextHolder` | Giữ `SecurityContext`/`Authentication` hiện tại trong phạm vi xử lý request. |
| `AuthorizationFilter` | Quyết định quyền truy cập dựa trên `Authentication` và các rule như `authenticated()`, `hasRole(...)`. |
| `AuthenticationEntryPoint` | Khởi tạo phản hồi khi client cần xác thực, thường trả HTTP 401 và challenge `WWW-Authenticate` cho Basic. |

`BasicAuthenticationFilter` **không tự kiểm tra password bằng cách so sánh chuỗi**, không tự truy vấn database, không quyết định `hasRole(...)` và không phải một controller xử lý `/login`.

## 2. Sơ đồ luồng gọi AuthenticationManager

```text
Client
  | GET /private
  | Authorization: Basic base64(username:password)
  v
Spring Security FilterChainProxy (Servlet SecurityFilterChain)
  |
  v
BasicAuthenticationFilter
  |-- BasicAuthenticationConverter.convert(request)
  |     -> UsernamePasswordAuthenticationToken(username, password)
  |        (chưa authenticated)
  |
  |-- nếu cần xác thực:
  |     AuthenticationManager.authenticate(token)
  |       -> ProviderManager
  |            -> DaoAuthenticationProvider
  |                 -> UserDetailsService.loadUserByUsername(...)
  |                 -> PasswordEncoder.matches(raw, encoded)
  |            <- Authentication đã xác thực + authorities
  |
  |-- thành công: tạo SecurityContext, đặt Authentication,
  |                gọi remember-me hook nếu có, có thể lưu context
  |-- thất bại:  xóa context, gọi failure hook,
  |                kích hoạt AuthenticationEntryPoint (thường 401)
  v
Các filter tiếp theo, trong đó có AuthorizationFilter
  |-- đủ quyền -> Controller -> 200
  |-- thiếu quyền -> AccessDeniedHandler -> 403
```

Luồng phía trên tóm tắt hành vi của phiên bản Spring Security 6.x, không phải bản chép nguyên mã nguồn. Các filter khác, ví dụ `SecurityContextHolderFilter`, `ExceptionTranslationFilter`, còn tham gia toàn bộ chuỗi. Thứ tự cụ thể do cấu hình `SecurityFilterChain` quyết định.

### Bước 1 — Đọc header và tạo token chưa xác thực

`BasicAuthenticationFilter` dùng `BasicAuthenticationConverter` để nhận header có scheme Basic, giải mã credential và tách username/password tại dấu `:` đầu tiên. Với `alice:secret123`, token khái niệm tương đương:

```java
Authentication requestAuthentication =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "secret123");
```

Đây là **một đoạn minh họa bên trong luồng filter**, không phải chương trình Java độc lập. Token mang `principal` (ở đây là username) và `credentials` (password), nhưng chưa có chứng cứ rằng thông tin là đúng. Đừng dùng `UsernamePasswordAuthenticationToken.authenticated(...)` để tự tuyên bố request đã xác thực.

Nếu header vắng mặt hoặc sử dụng scheme khác (ví dụ Bearer), converter không tạo Basic token và filter đi tiếp. Nếu header khai báo Basic nhưng sai định dạng, conversion có thể ném `AuthenticationException` để xử lý như lỗi xác thực. Header Basic hợp lệ **không đồng nghĩa** password hợp lệ.

### Bước 2 — Quyết định có cần gọi authenticate

Khi converter tạo được token, filter kiểm tra `authenticationIsRequired(username)`. Thông thường chưa có người dùng đã xác thực trong context, nên nó thực hiện:

```java
Authentication authenticated =
        authenticationManager.authenticate(requestAuthentication);
```

Đây cũng là **đoạn trích minh họa**, trong đó biến `authenticationManager` là dependency của filter. Nếu context đã có một người dùng thực sự được xác thực với cùng username, filter có thể bỏ qua việc gọi manager lặp lại. Đừng suy ra rằng header Basic luôn kéo theo chính xác một lần truy vấn user/password: điều đó phụ thuộc context và provider/cache.

`http.httpBasic(...)` cấu hình filter bằng `AuthenticationManager` mà `HttpSecurity` đang sử dụng. Vì vậy trong cấu hình thông thường, **không cần tự tạo hay thêm `BasicAuthenticationFilter`**. Tự `new BasicAuthenticationFilter(...)` rồi `addFilter...` khi chưa kiểm soát vị trí/manager có thể gây xử lý hai lần hoặc làm sai chuỗi bảo mật.

### Bước 3 — AuthenticationManager ủy quyền cho provider

`AuthenticationManager` là interface:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

`ProviderManager` thường là triển khai phía sau. Nó chọn các `AuthenticationProvider` có `supports(...)` phù hợp với kiểu token; trong ví dụ username/password, `DaoAuthenticationProvider` dùng `UserDetailsService.loadUserByUsername("alice")` để lấy tài khoản, rồi `PasswordEncoder.matches(rawPassword, encodedPassword)` để xác minh mật khẩu. Provider xử lý trạng thái tài khoản như bị khóa/vô hiệu hóa nếu dữ liệu `UserDetails` yêu cầu. Khi nhiều provider tham gia, kết quả/ngoại lệ phụ thuộc cách `ProviderManager` ủy quyền.

Manager **không trả `true`/`false`**. Nó trả một đối tượng `Authentication` (thường có `isAuthenticated()==true`, `principal` đã xác minh và tập `GrantedAuthority`) hoặc ném `AuthenticationException`; ví dụ `BadCredentialsException` khi password sai. Không dựa vào thông báo lỗi chi tiết để phân biệt tài khoản tồn tại hay không.

### Bước 4 — Thành công: đưa kết quả vào SecurityContext

Khi `authenticate(...)` thành công, `BasicAuthenticationFilter` tạo một `SecurityContext`, đặt `Authentication` trả về vào context rồi đưa context vào `SecurityContextHolder`. Nó cũng gọi `RememberMeServices.loginSuccess(...)` nếu có cấu hình và sử dụng `SecurityContextRepository` được cấp để lưu context theo chính sách của ứng dụng. Sau đó request tiếp tục qua filter chain.

Điều được đặt vào context là **kết quả từ manager**, không phải token chưa xác thực ban đầu. `AuthenticationManager` chỉ xác thực; **filter chịu trách nhiệm cập nhật context**. Các filter phân quyền đọc thông tin này để xét quyền, còn controller có thể nhận tham số `Authentication` đã xác thực.

Điểm dễ nhầm: đưa vào `SecurityContextHolder` cho request hiện tại **không mặc nhiên có nghĩa là ghi vào HTTP session**. `BasicAuthenticationFilter` mặc định không lưu context bền qua session; muốn lưu phải cấu hình repository phù hợp. Với API stateless, client thường gửi lại Basic header ở mỗi request.

### Bước 5 — Thất bại: xóa context và yêu cầu xác thực lại

Khi converter/manager ném `AuthenticationException`, filter xóa context, gọi `RememberMeServices.loginFail(...)` nếu có và, với chế độ mặc định không bỏ qua lỗi, gọi `AuthenticationEntryPoint.commence(...)`. Với HTTP Basic, phản hồi điển hình là **401 Unauthorized** kèm challenge như `WWW-Authenticate: Basic realm="Realm"` (realm/header thực tế phụ thuộc cấu hình và loại request). Filter không chuyển tiếp tới controller sau nhánh xử lý 401 này.

Đường đi của một request **không hề có Basic header** hơi khác: Basic filter chỉ cho đi tiếp; nếu URL yêu cầu authenticated, `AuthorizationFilter` từ chối và `ExceptionTranslationFilter` sử dụng entry point để trả challenge 401. Một request **đã xác thực nhưng thiếu quyền** thường nhận **403 Forbidden** qua `AccessDeniedHandler`.

Lưu ý: một số cấu hình HTTP Basic mặc định có hành vi đặc biệt với `X-Requested-With: XMLHttpRequest` (có thể bỏ body/challenge trong phản hồi 401), nên khi debug cần kiểm tra request headers và entry point thực tế.

## 3. Ví dụ runnable: Spring Boot 3.3.5, Java 17

Ví dụ cố định tại Spring Boot 3.3.5 (nhánh Spring Security 6.x). Chạy bằng Maven 3.9+ và JDK 17+. Demo có hai người dùng: `alice` mang `ROLE_READER`, `bob` mang `ROLE_VIEWER`, cả hai dùng mật khẩu demo `secret123`. Mật khẩu chỉ nằm trong cấu hình demo, không đưa giá trị này vào sản phẩm thực.

Cấu trúc:

```text
basic-auth-demo/
├── pom.xml
└── src/main/java/com/example/basicauth/BasicAuthDemoApplication.java
```

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>basic-auth-demo</artifactId>
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
```

**`src/main/java/com/example/basicauth/BasicAuthDemoApplication.java`:**

```java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BasicAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicAuthDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").hasRole("READER")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
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
            .password(encoder.encode("secret123"))
            .roles("READER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("secret123"))
            .roles("VIEWER")
            .build();
        return new InMemoryUserDetailsManager(alice, bob);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello, " + authentication.getName();
        }
    }
}
```

Giải thích các dòng cấu hình quan trọng:

1. `httpBasic(Customizer.withDefaults())` bật cơ chế Basic và đăng ký `BasicAuthenticationFilter` trong chuỗi Servlet.
2. Bean `UserDetailsService` và `PasswordEncoder` cung cấp dữ liệu để Spring Security cấu hình xác thực username/password thông qua provider/manager. Demo dùng `InMemoryUserDetailsManager`; có thể thay bằng repository hoặc nguồn khác qua provider phù hợp.
3. `hasRole("READER")` yêu cầu authority `ROLE_READER`. `roles("READER")` tạo authority đó; không truyền `"ROLE_READER"` vào `hasRole`.
4. `SessionCreationPolicy.STATELESS` cho biết ứng dụng không tạo/sử dụng session để lấy `SecurityContext` cho các request. Nó giúp quan sát rõ mỗi request Basic xác thực theo credential gửi kèm.
5. `/public` không yêu cầu quyền, nhưng Basic header **nếu được gửi lên** vẫn có thể được Basic filter xử lý trước bước kiểm tra `permitAll`.
6. Demo chỉ dùng GET, vì thế không cần tắt CSRF. Với endpoint thay đổi dữ liệu trong ứng dụng thật, phải đánh giá CSRF theo kiểu client và cơ chế credential trước khi cấu hình chính sách.

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Trong terminal khác, thử lần lượt (PowerShell Windows dùng `curl.exe` nếu `curl` là alias):

```bash
curl -s http://localhost:8080/public
# public

curl -i http://localhost:8080/private
# HTTP status: 401; thường có WWW-Authenticate: Basic realm="Realm"

curl -s -u alice:secret123 http://localhost:8080/private
# Hello, alice

curl -i -u alice:wrong http://localhost:8080/private
# HTTP status: 401

curl -i -u bob:secret123 http://localhost:8080/private
# HTTP status: 403
```

Dòng bắt đầu bằng `#` trong khối shell chỉ mô tả kết quả mong đợi. Output body của hai lệnh có `-s` lần lượt chính xác là `public` và `Hello, alice` (không nhất thiết có newline cuối); phần headers/body của các response lỗi phụ thuộc cấu hình server và version. Tùy `curl`, bạn có thể dùng `-v` để kiểm tra header `Authorization`, nhưng **không chia sẻ log chứa credential**.

## 4. Kiểm thử tự động 401 / 200 / 403

Thêm file `src/test/java/com/example/basicauth/BasicAuthDemoApplicationTests.java` (dependency test đã có trong POM):

```java
package com.example.basicauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void basicCredentialsAndAuthorities() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private").with(httpBasic("alice", "secret123")))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));

        mvc.perform(get("/private").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private").with(httpBasic("bob", "secret123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

Chạy `mvn test`. Kiểm thử này đi qua chuỗi Spring Security thực của ứng dụng trong `MockMvc`: username/password của Alice được xác thực và có đúng quyền, Bob xác thực thành công nhưng thiếu quyền, password sai khiến xác thực thất bại, còn request không credential đến endpoint bảo vệ nhận 401.

## 5. Phân biệt các nhánh thường gây nhầm

| Request/trạng thái | BasicAuthenticationFilter | Sau đó | Kết quả điển hình |
| --- | --- | --- | --- |
| Không có `Authorization`, gọi `/public` | Không tạo Basic token | `permitAll` | 200 |
| Không có `Authorization`, gọi `/private` | Bỏ qua | Phân quyền yêu cầu đăng nhập, entry point tạo challenge | 401 |
| `alice:secret123`, gọi `/private` | Manager xác thực thành công, đưa Alice vào context | Alice có `ROLE_READER` | 200 |
| `alice:wrong`, gọi `/private` | Manager ném `AuthenticationException`, filter xử lý lỗi | Không gọi controller | 401 |
| `bob:secret123`, gọi `/private` | Bob xác thực thành công | Bob thiếu `ROLE_READER` | 403 |
| `Authorization: Bearer ...`, không có Bearer filter | Basic filter không xử lý scheme này | URL bảo vệ vẫn yêu cầu xác thực | 401 |
| Header Basic lỗi định dạng | Converter có thể ném lỗi | Filter khởi động entry point | 401 |

**Vì sao 401 khác 403?** `401` thường có nghĩa client chưa trình được credential hợp lệ; `403` nghĩa server đã xác thực danh tính nhưng không cho phép thao tác. Đừng quy mọi lỗi `403` thành password sai.

**Vì sao `permitAll` vẫn có thể thấy 401?** Một request tới endpoint public nhưng chủ động gửi header Basic sai có thể bị Basic filter từ chối **trước** khi `AuthorizationFilter` kiểm tra `permitAll`. `permitAll` chỉ nói về quyết định phân quyền, không vô hiệu hóa mọi authentication filter.

**Khi có nhiều `SecurityFilterChain`:** chỉ chuỗi khớp request (do `FilterChainProxy` chọn) được dùng. Nếu `httpBasic()` nằm ở chuỗi khác, request hiện tại có thể hoàn toàn không đi qua `BasicAuthenticationFilter`. Kiểm tra `securityMatcher(...)`/thứ tự chain trước khi nghi ngờ manager.

## 6. Cách đọc và debug lời gọi thực tế

Đặt breakpoint hoặc theo dõi trace tại các điểm sau, theo thứ tự:

1. `BasicAuthenticationFilter#doFilterInternal`: request có header Basic hay không? `BasicAuthenticationConverter.convert(...)` trả `null`, token hay exception?
2. `BasicAuthenticationFilter#authenticationIsRequired`: context hiện tại có authentication nào, có bỏ qua gọi manager không?
3. `ProviderManager#authenticate`: nhận `UsernamePasswordAuthenticationToken` nào và có provider phù hợp không?
4. `DaoAuthenticationProvider` / `UserDetailsService#loadUserByUsername`: đã tìm được user? `PasswordEncoder.matches(...)` có kiểm tra bản mã hash đúng cách?
5. Quay lại filter: manager trả `Authentication` gì, `isAuthenticated` và `authorities` ra sao, context có được cập nhật?
6. `AuthorizationFilter`: rule `hasRole("READER")` có khớp `ROLE_READER` trong context không? Khi lỗi, entry point hay access-denied handler đã phản hồi?

Không log chuỗi `Authorization`, password thô hoặc toàn bộ `Authentication.credentials`. Khi debug bằng log, dùng thông tin tối thiểu như loại token, trạng thái và tên provider, với chính sách che dữ liệu nhạy cảm.

### Các lỗi cấu hình phổ biến

- **Quên `httpBasic(...)` khi tự khai báo `SecurityFilterChain`:** request Basic không được xử lý theo cách mong đợi. Khai báo tường minh trong chain cần dùng.
- **Không có provider hỗ trợ token username/password:** manager không tìm được đường xác thực phù hợp. Xác minh `UserDetailsService`, `AuthenticationProvider` và wiring `AuthenticationManager`.
- **Sai `PasswordEncoder` hoặc lưu password plaintext rồi so với hash:** `matches(...)` thất bại. Lưu hash thích hợp (ví dụ BCrypt), mã hóa khi tạo user và tránh `{noop}` trong production.
- **Tự trả token `authenticated` mà chưa kiểm tra credential:** tạo lỗ hổng xác thực. Chỉ tin kết quả do manager/provider xác thực.
- **Nhầm quyền với mật khẩu:** password đúng nhưng `ROLE_READER` thiếu sẽ thành 403, không phải 401.
- **Giả định một lần Basic login tạo phiên đăng nhập lâu dài:** HTTP Basic thường gửi credential cho mỗi request; việc lưu `SecurityContext`/session là một chính sách riêng.
- **Bỏ qua HTTPS:** Base64 không giấu password khỏi người có thể đọc lưu lượng.
- **Tự thêm nhiều Basic filter:** khiến luồng xử lý và manager khó kiểm soát; dùng cấu hình `httpBasic` chuẩn trước.

## 7. Tự kiểm tra kiến thức

1. Token nào đi **vào** `AuthenticationManager.authenticate(...)`? Nó có được coi là đã xác thực chưa?
2. Sau lời gọi `authenticate(...)` thành công, thành phần nào đưa `Authentication` trả về vào `SecurityContextHolder`?
3. Nếu thiếu header Basic hoàn toàn, vì sao endpoint bảo vệ vẫn trả 401 dù Basic filter bỏ qua?
4. Vì sao `bob` nhận 403 trong demo, còn `alice` sai password nhận 401?
5. Vì sao đặt `.sessionCreationPolicy(STATELESS)` không có nghĩa là bỏ qua `AuthenticationManager`?
6. Nếu đã có một `Authentication` xác thực cùng username trong context, có nên khẳng định manager luôn được gọi nữa không?

**Đáp án cốt lõi:** (1) `UsernamePasswordAuthenticationToken` chưa xác thực; (2) `BasicAuthenticationFilter`; (3) phân quyền từ chối, `ExceptionTranslationFilter` gọi entry point; (4) thiếu quyền so với sai credential; (5) stateless điều khiển chính sách session/context, không thay thế kiểm tra password; (6) không, filter có điều kiện `authenticationIsRequired`.

## Tài liệu tham khảo chính thức

- Spring Security — Basic Authentication (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — BasicAuthenticationFilter API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/www/BasicAuthenticationFilter.html
- Spring Security — Authentication Persistence / Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
