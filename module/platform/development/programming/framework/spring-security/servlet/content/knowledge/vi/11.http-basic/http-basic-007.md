# Kết hợp HTTP Basic cho API với đăng nhập biểu mẫu ở SecurityFilterChain khác

## 1. Mục tiêu và bài toán

Một ứng dụng Spring Security Servlet đôi khi có **hai đối tượng khách hàng rất khác nhau**:

- **API client** gọi `/api/**` bằng HTTP Basic, gửi header `Authorization: Basic ...` trên mỗi request. Khi chưa xác thực, client nên nhận **HTTP 401** cùng cơ chế challenge phù hợp, không phải HTML redirect tới form login.
- **Trình duyệt** truy cập các trang web thông thường, được chuyển tới `/login` nếu chưa đăng nhập, sau đó xác thực bằng **form login**, lưu trạng thái đăng nhập bằng session và tiếp tục sử dụng website.

Nếu cấu hình một chuỗi filter chung bật cả `httpBasic` và `formLogin` mà không xác định ranh giới, response cho browser và API có thể khác kỳ vọng. Giải pháp rõ ràng trong Spring Security Servlet là định nghĩa **nhiều `SecurityFilterChain`**, mỗi chain có `securityMatcher`, authentication mechanism, entry point và session policy phù hợp.

Mục tiêu sau bài học:

1. Hiểu `FilterChainProxy` chọn **một chain đầu tiên khớp request**, không ghép hoặc chạy tuần tự tất cả chain.
2. Định tuyến API `/api/**` vào chain HTTP Basic, phần web vào chain form login.
3. Phân biệt **`securityMatcher` chọn chain** và **`requestMatchers` chọn quy tắc authorization bên trong chain**.
4. Đặt `@Order`, một chain fallback, và các URL login/logout đúng phạm vi.
5. Thiết kế session, request cache và CSRF cho từng nhóm request, không nhầm “stateless” với “an toàn trước CSRF”.
6. Kiểm chứng HTTP 401/403/302, headers, login/session và ranh giới chain bằng Spring Boot 3 + Java 17 + MockMvc.

Ví dụ triển khai ở phần 8 là **một ứng dụng Servlet hoàn chỉnh phục vụ học tập**. Nó dùng tài khoản trong bộ nhớ để giữ trọng tâm ở nhiều filter chain; sản xuất cần database/identity provider, TLS, secret management, rate limiting và các kiểm soát bảo mật thích hợp.

## 2. Hai chain có nghĩa gì trong cấu trúc Servlet?

Đường xử lý khái niệm:

```text
HTTP request
     |
     v
Servlet container Filter chain
     |
     v
DelegatingFilterProxy (springSecurityFilterChain)
     |
     v
FilterChainProxy
     |
     +-- SecurityFilterChain @Order(1)
     |     securityMatcher("/api/**")
     |     |-- matches?
     |     |    YES -> chỉ chain API:
     |     |       SecurityContext handling
     |     |       HTTP Basic authentication
     |     |       AuthorizationFilter
     |     |       ...
     |     |-- NO -> thử chain tiếp theo
     |
     +-- SecurityFilterChain @Order(2)
           matcher mặc định: mọi request còn lại
           |-- Form login filters
           |-- Session-based SecurityContext
           |-- AuthorizationFilter
           |-- ...
     |
     v
Controller/Servlet nếu vượt qua kiểm tra
```

`DelegatingFilterProxy` giúp Servlet container gọi một bean Spring phù hợp; `FilterChainProxy` quản lý các `SecurityFilterChain`. Mỗi chain bao gồm những security filters do cấu hình của chain đó tạo ra, cùng matcher riêng.

**Quan trọng nhất:** Với mỗi request, `FilterChainProxy` tìm **SecurityFilterChain đầu tiên có matcher phù hợp**, rồi dùng các filter của chain đó. Nó **không** tự chuyển tiếp request sang chain web sau khi chain API đã xác thực xong. Vì vậy:

- `GET /api/orders` phải đi chain API.
- `GET /web/profile` phải đi chain web.
- `GET /login` và `POST /login` cũng phải được xử lý bởi chain web nếu muốn sử dụng endpoint login mặc định của Spring Security.
- `GET /some-other-page` cần chain fallback đủ rộng, nếu ứng dụng muốn route này vẫn được bảo vệ.

Bất kỳ request nào **không khớp một SecurityFilterChain nào** có thể không được Spring Security bảo vệ. Đây là lý do không nên vô tình tạo khoảng trống khi tách chain.

### 2.1. Authentication và authorization trong từng chain

**Authentication** trả lời “client này là ai?”, và với HTTP Basic thường đến từ `BasicAuthenticationFilter`; với form login thường đến từ `UsernamePasswordAuthenticationFilter`.

**Authorization** trả lời “người này có được vào endpoint không?”, được cấu hình bằng `authorizeHttpRequests`. Trong cấu hình hiện đại nó sử dụng `AuthorizationFilter` và các `AuthorizationManager` tương ứng.

API và web có thể chia sẻ `UserDetailsService`, `PasswordEncoder` hoặc `AuthenticationProvider` để dùng chung kho tài khoản, nhưng **không có nghĩa** chúng phải chia sẻ session, request cache hay cách challenge chưa đăng nhập.

## 3. securityMatcher khác requestMatchers ra sao?

Hai API này trông giống nhau nhưng áp dụng **ở các tầng khác nhau**.

| API | Phạm vi | Tác dụng | Ví dụ |
| --- | --- | --- | --- |
| `http.securityMatcher("/api/**")` | Toàn bộ `SecurityFilterChain` | Quyết định request **có được đưa vào chain này không** | API chain chỉ nhận `/api/...` |
| `authorizeHttpRequests(auth -> auth.requestMatchers("/api/public").permitAll())` | Quy tắc authorization của chain đã được chọn | Cho phép/kiểm tra quyền với đường dẫn khớp **bên trong chain** | Route công khai của API |
| `anyRequest().authenticated()` | Quy tắc cuối của chain đã chọn | Đòi authentication với các request còn lại **của chain đó** | Tất cả API khác `/api/public` |
| `@Order(1)`, `@Order(2)` | Thứ tự các bean `SecurityFilterChain` | Quyết định chain nào được xét trước | API trước, web fallback sau |

Một hiểu nhầm thường gặp:

```java
// Minh họa KHÔNG đúng yêu cầu tách chain:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().authenticated()
);
```

Đoạn trên chỉ nói về **authorization**. Nó không khiến HTTP Basic tự động được bật riêng cho `/api/**` hoặc form login được bật riêng cho web. Nếu `httpBasic` và `formLogin` cùng có trong chain này, các filter và entry point vẫn nằm trong cùng cấu hình trừ khi được tùy chỉnh thích hợp.

### 3.1. Vì sao @Order quan trọng?

Giả sử đặt chain web match mọi request ở `@Order(1)`, rồi API chain ở `@Order(2)`. Khi `GET /api/orders` đến, chain web đã match trước. API chain dù cấu hình chính xác sẽ **không có cơ hội được chọn**.

Thứ tự an toàn trong bài:

```text
@Order(1): /api/**    -> HTTP Basic
@Order(2): any request -> form login
```

Không mặc định `@Order` nhỏ nhất là chain “có quyền cao nhất”; nó chỉ biểu thị **ưu tiên kiểm tra matcher**. Thực tế có thể chia thêm chain cho actuator, admin hoặc OAuth2, nhưng mỗi chain cần có phạm vi rõ ràng và phân tích trường hợp trùng match.

### 3.2. securityMatcher không phải phép kiểm tra quyền

Nếu API chain có `securityMatcher("/api/**")`, request `/api/admin` được đưa vào chain ngay cả khi chưa xác thực. Nó sẽ được **xác thực/phân quyền bên trong chain**, không phải được cấp quyền chỉ vì matcher đúng.

Tương tự, một `requestMatchers("/api/public").permitAll()` không bỏ qua toàn bộ filter chain. Request công khai vẫn có thể đi qua security filters theo cấu hình, với các hệ quả về headers, CSRF và diagnostics.

## 4. HTTP Basic trong API chain

HTTP Basic mô tả một authentication scheme mà client gửi username/password ở dạng mã hóa Base64 trong header:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic <Base64(username:password)>
```

**Base64 không phải mã hóa bảo mật.** Cần HTTPS để bảo vệ credentials trên đường truyền. Không đặt username/password thật vào URL hoặc log, không dùng HTTP Basic trên mạng không mã hóa cho hệ thống thực.

Luồng phổ biến:

```text
GET /api/me
     |
     +-- Không có Authorization header
     |      -> cần xác thực: HTTP 401
     |         WWW-Authenticate: Basic ...
     |
     +-- Header Basic hợp lệ
     |      -> BasicAuthenticationFilter
     |      -> AuthenticationManager/Provider
     |      -> UserDetailsService + PasswordEncoder
     |      -> Authentication hợp lệ
     |      -> AuthorizationFilter
     |      -> Controller trả 200 nếu có quyền
     |
     +-- Credentials sai
     |      -> Authentication failed
     |      -> HTTP 401
     |
     +-- Credentials đúng nhưng thiếu authority
            -> HTTP 403 ở tài nguyên yêu cầu quyền cao hơn
```

Mã trạng thái ở trên là kết quả kỳ vọng **với cấu hình bài thực hành**; handler/entry point tùy biến có thể thay đổi. Không diễn giải rằng 401 luôn do “user không tồn tại” và 403 luôn do “password sai”. Password sai thường là lỗi authentication và dẫn đến 401 trong API Basic; authenticated user thiếu quyền thường dẫn đến 403.

### 4.1. Client gửi lại Basic trên từng request

Trong ví dụ API stateless, client phải tiếp tục gửi `Authorization` trên các request cần bảo vệ. Việc đã đăng nhập website bằng form login **không** khiến API chain mặc nhiên sử dụng cookie/session của website.

Một số browser có thể tự gửi lại Basic credentials sau khi đã xác thực challenge; vì vậy phải cân nhắc CSRF và cache credentials khi API có request làm thay đổi trạng thái. Đừng suy luận rằng “không dùng session cookie” đồng nghĩa browser không tự gắn credential.

### 4.2. HTTP Basic không cung cấp phiên logout kiểu form login

Logout của website thường invalidate/clear session. Nhưng một client Basic có thể gửi lại cùng `Authorization` trên request kế tiếp và được xác thực lại. Muốn vô hiệu hóa credential phải có chính sách quản lý password/account/token ở hệ thống xác thực; chỉ xóa `SecurityContextHolder` một lần không đủ.

Do đó Basic thường phù hợp hơn cho client đơn giản, môi trường nội bộ hoặc kết nối cần tương thích, với TLS và kiểm soát lạm dụng; không tự động là lựa chọn tối ưu cho mọi API hiện đại.

## 5. Form login trong chain web

Form login phục vụ browser:

```text
GET /web/me chưa có session xác thực
    |
    -> SecurityFilterChain web
    -> chưa authenticated
    -> 302 Location: /login
    |
GET /login
    -> form mặc định hoặc trang login tùy chỉnh
    |
POST /login
    -> username/password + CSRF token phù hợp
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager
    -> thành công: lưu SecurityContext vào session theo policy
    -> redirect về saved request hoặc default target
    |
GET /web/me với session cookie sau login
    -> khôi phục Authentication từ session
    -> 200 nếu được cho phép
```

Khác với Basic, form login thường hoạt động nhờ **HTTP session**. `SecurityContextRepository` và session cookie quyết định request sau có khôi phục đăng nhập hay không. `RequestCache` có thể ghi nhớ URL web bị chặn trước login; đây không phải nhiệm vụ của API chain nếu API dùng `NullRequestCache`.

Ví dụ có thể dùng **generated login page** của Spring Security khi không khai báo `loginPage(...)`. Với `formLogin(Customizer.withDefaults())`, chain web cần nhận request đến đường dẫn mặc định `/login` cho cả GET hiển thị form và POST xử lý đăng nhập. Nếu chain web bị giới hạn `securityMatcher("/web/**")` mà không mở rộng đến `/login`, endpoint đăng nhập mặc định có thể không được filter xử lý.

### 5.1. Vì sao web fallback được để không có securityMatcher?

Trong ví dụ:

```text
API: @Order(1), securityMatcher("/api/**")
WEB: @Order(2), không đặt securityMatcher
```

Điều này cho phép chain web bao phủ `/login`, `/logout`, `/` và các URL web khác mà không phải liệt kê hết trong matcher của chain. `authorizeHttpRequests` của chain web vẫn quyết định endpoint nào công khai, endpoint nào yêu cầu login.

Một thiết kế khác có thể dùng matcher web riêng và một fallback thứ ba, nhưng phải chứng minh không bỏ quên login/error/static paths và không làm lộ request nằm ngoài tất cả chain.

### 5.2. Không bật httpBasic cho web nếu không cần

Nếu thêm `httpBasic` vào cả web chain, browser có thể nhận Basic challenge ở đường đi lẽ ra dùng form login; API/browser có thể có nội dung phản hồi không ổn định theo request headers. Để minh họa ranh giới rõ ràng, chain web trong bài **chỉ bật form login**, chain API **chỉ bật HTTP Basic**.

## 6. Session, SecurityContext và RequestCache: tách chính sách theo chain

Hai chain có thể dùng chung tài khoản, nhưng nên làm rõ các cơ chế tồn tại của ngữ cảnh.

| Tính chất | API chain | WEB chain |
| --- | --- | --- |
| Matcher | `/api/**` | Request còn lại (fallback) |
| Authentication mechanism | HTTP Basic | Form login |
| Chưa xác thực | 401 + Basic challenge | 302 tới `/login` |
| Lưu đăng nhập xuyên HTTP requests | Không, trong ví dụ stateless | Có, qua HTTP session |
| `SecurityContextRepository` | `NullSecurityContextRepository` tường minh | Session-aware repository theo mặc định web |
| `RequestCache` | `NullRequestCache` tường minh | Request cache phục vụ saved URL/login |
| CSRF | Không bị tự tắt chỉ vì stateless | Cần bảo vệ thao tác state-changing theo mô hình browser |
| Account lookup | Có thể dùng chung `UserDetailsService` | Có thể dùng chung `UserDetailsService` |
| Authorization | Quy tắc API | Quy tắc web |

### 6.1. STATELESS không có nghĩa không xác thực

`SessionCreationPolicy.STATELESS` thể hiện Spring Security không tạo hoặc dùng session để lấy `SecurityContext` cho API chain. Mỗi request được xử lý với thông tin authentication của chính nó (trong ví dụ là Basic header). Nó vẫn có thể tạo `Authentication` **trong phạm vi request hiện tại** và kiểm tra quyền.

Dùng `NullSecurityContextRepository` minh họa việc không lưu context vào session qua repository. Tuy vậy, cấu hình stateless **không cấm toàn bộ thư viện hoặc code nghiệp vụ** tạo session trong mọi trường hợp. Hãy kiểm thử thực tế nếu sản phẩm có yêu cầu tuyệt đối không có session/cookie.

### 6.2. Vì sao NullRequestCache cho API?

API Basic không cần ghi nhớ URL để redirect về sau form login. `NullRequestCache` bỏ việc lưu request cần xác thực vào session. Khi request API chưa xác thực, server trả HTTP 401 và client tự quyết định bước tiếp theo.

### 6.3. CSRF phải được phân tích theo loại client

**Một sai lầm phổ biến:** “API stateless dùng Basic nên có thể tắt CSRF vô điều kiện”.

CSRF liên quan đến việc browser **tự động đính kèm thông tin xác thực** vào request do một trang khác kích hoạt. Browser có thể lưu/chủ động gửi lại Basic credentials trong một số trường hợp; vì vậy chính sách CSRF của API phải dựa trên việc client có phải browser hay không, cơ chế gửi credential, cookie/challenge và các endpoint có side effect.

Trong ví dụ chạy được, **giữ nguyên CSRF protection mặc định** của Spring Security ở cả hai chain, đồng thời chỉ định nghĩa API GET để tránh giới thiệu một endpoint thay đổi dữ liệu mà chưa thiết kế CSRF. Với API máy-máy dùng header do client chủ động quản lý và đã có threat model phù hợp, có thể vô hiệu hóa CSRF **chỉ ở chain API**; khi đó cần chứng minh request không dựa vào credential được browser tự gửi và có biện pháp khác phù hợp.

Ví dụ **lựa chọn có điều kiện, không áp dụng trong SecurityConfig chạy được bên dưới**:

```java
// Chỉ trong apiSecurityChain(...), sau khi đánh giá CSRF đầy đủ:
http.csrf(csrf -> csrf.disable());
```

Không sao chép dòng này vào web chain chỉ để POST `/login` “dễ chạy”. Form login chuẩn thường yêu cầu CSRF token cho POST, và test sẽ truyền token hợp lệ.

## 7. Chọn một hay nhiều nguồn tài khoản?

Phần trọng tâm là sự độc lập giữa các **SecurityFilterChain**. Trong ứng dụng học tập, hai chain dùng chung một bean `UserDetailsService` và `PasswordEncoder`. Điều đó giúp người dùng `reader` hoặc `admin` xác thực được bằng cả Basic và form login, tùy request đi qua chain nào.

Không vì vậy mà tự suy ra hai chain phải có chung `AuthenticationManager` trong mọi ứng dụng. Khi sản phẩm cần tài khoản API riêng hoặc nhiều identity provider, có thể cấu hình `AuthenticationProvider`/`AuthenticationManager` phù hợp cho từng chain. Phải kiểm tra thứ tự provider, nguồn user, cache và hiệu ứng khi cùng username tồn tại ở nhiều nguồn.

Trong ví dụ:

```text
UserDetailsService + PasswordEncoder
        |
        +---- API chain -> HTTP Basic -> DAO authentication
        |
        +---- WEB chain -> Form login -> DAO authentication
```

**Chia sẻ kho tài khoản không đồng nghĩa chia sẻ phiên đăng nhập.** Một lần form login tạo session chỉ có tác dụng trên chain có session-backed context phù hợp; API chain dùng `NullSecurityContextRepository` không lấy session đó làm căn cứ xác thực.

### 7.1. Vì sao không tự định nghĩa hai AuthenticationManager một cách tùy tiện?

Định nghĩa hai manager/provider riêng có ích khi yêu cầu domain thực sự khác nhau, nhưng dễ tạo lỗi khó hiểu: sai password encoder, sai user store, khác authority mapping, hoặc manager của chain này được gắn nhầm vào chain kia. Bắt đầu với một kho tài khoản nhất quán để chứng minh routing; chỉ tách providers khi có yêu cầu và tests cụ thể.

## 8. Ví dụ Spring Boot 3.3.5 + Java 17 đầy đủ

Ví dụ này có thể tạo và chạy bằng Maven trên Java 17. Nó dùng đúng hai `SecurityFilterChain`:

- `@Order(1)`: `/api/**` → HTTP Basic, không lưu context ở HTTP session, không lưu saved request.
- `@Order(2)`: fallback → form login, session bình thường, login page mặc định.

### 8.1. Cấu trúc thư mục

```text
dual-chain-security/
  pom.xml
  src/
    main/
      java/example/dual/
        DualChainApplication.java
        SecurityConfig.java
        DemoController.java
    test/
      java/example/dual/
        DualChainSecurityTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>dual-chain-security</artifactId>
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

Đây là ứng dụng **Spring MVC Servlet**, không phải WebFlux. Các API trong code thuộc `org.springframework.security.config.annotation.web.builders.HttpSecurity` và `SecurityFilterChain` Servlet.

### 8.3. Lớp khởi động

File `src/main/java/example/dual/DualChainApplication.java`:

```java
package example.dual;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualChainApplication.class, args);
    }
}
```

### 8.4. SecurityConfig với hai SecurityFilterChain

File `src/main/java/example/dual/SecurityConfig.java`:

```java
package example.dual;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Giữ CSRF mặc định. Ví dụ chỉ có API GET, không POST/PUT/DELETE.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/web/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Không đặt securityMatcher("/web/**") ở đây.
        // Chain này là fallback để GET/POST /login được xử lý.
        return http.build();
    }
}
```

#### Giải thích các điểm bắt buộc

**`@Order(1)` và `securityMatcher("/api/**")`:** API matcher được xét trước. Một request `/api/me` khớp và dừng ở chain này; web chain không xử lý request đó.

**`httpBasic(Customizer.withDefaults())`:** bật Basic authentication và challenge tương ứng. API không có `formLogin` trong chain này, vì vậy một client anonymous truy cập `/api/me` không bị chuyển tới trang đăng nhập HTML.

**`SessionCreationPolicy.STATELESS` + `NullSecurityContextRepository`:** minh họa rõ API không lấy Authentication từ HTTP session giữa các request. Điều này không tắt việc xác thực trong request hiện tại; Basic header vẫn được xử lý bình thường.

**`NullRequestCache`:** API không lưu original URL vào session chỉ để chuyển hướng sau đăng nhập.

**Không tắt CSRF trong ví dụ:** API hiện tại chỉ có GET; web chain vẫn cần CSRF cho POST login. Nếu thêm endpoint API POST, cần quyết định CSRF theo mô hình client và cách credential được gửi. Stateless không phải lý do đủ để tắt CSRF.

**Web chain không có securityMatcher:** nó nhận mọi request còn lại, gồm `GET /login` và `POST /login`. Vì chỉ bật form login, anonymous web request thường được redirect thay vì Basic challenge.

**`UserDetailsService` chung:** accounts được hash bằng `BCryptPasswordEncoder`. `roles("READER")` tạo `ROLE_READER`, `roles("ADMIN")` tạo `ROLE_ADMIN`; `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` theo quy ước.

**Không hardcode credentials vào sản phẩm thật:** `reader-pass` và `admin-pass` chỉ là dữ liệu ví dụ. Database hoặc secret/identity store thật phải có cơ chế lưu an toàn, quản lý tài khoản, TLS và rate limiting.

### 8.5. Controller chứng minh route thuộc hai nhóm

File `src/main/java/example/dual/DemoController.java`:

```java
package example.dual;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    String home() {
        return "home";
    }

    @GetMapping("/api/public")
    String apiPublic() {
        return "api:public";
    }

    @GetMapping("/api/me")
    String apiMe(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "api:admin";
    }

    @GetMapping("/web/public")
    String webPublic() {
        return "web:public";
    }

    @GetMapping("/web/me")
    String webMe(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/web/admin")
    String webAdmin() {
        return "web:admin";
    }
}
```

Cả `/api/me` lẫn `/web/me` sử dụng một `Authentication` được Spring Security đưa vào controller. Điểm khác biệt **không nằm ở method Java**, mà ở filter chain đã tạo ra Authentication và cách nó được nạp cho request.

Controller chỉ định nghĩa các route GET để giữ ví dụ tập trung vào authentication và policy phân quyền, không dẫn tới hiểu nhầm rằng đã có API thay đổi dữ liệu production-safe.

## 9. MockMvc integration tests: xác minh cả hai chain và ranh giới phiên

File `src/test/java/example/dual/DualChainSecurityTest.java`:

```java
package example.dual;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
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
class DualChainSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousPublicApiWorks() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api:public"));
    }

    @Test
    void anonymousApiGetsBasicChallengeNotLoginRedirect()
            throws Exception {
        MvcResult result = mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge = result.getResponse()
            .getHeader("WWW-Authenticate");
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void validBasicCredentialsWorkOnApi() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void wrongBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiRequiresAdminAuthority() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:admin"));
    }

    @Test
    void anonymousWebRedirectsToFormLogin() throws Exception {
        MvcResult result = mvc.perform(get("/web/me"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String redirect = result.getResponse().getRedirectedUrl();
        assertNotNull(redirect);
        assertTrue(redirect.contains("/login"));
    }

    @Test
    void browserCanLogInAndUseSession() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession rawSession = result.getRequest().getSession(false);
        assertNotNull(rawSession);

        MockHttpSession session = (MockHttpSession) rawSession;
        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:reader"));
    }

    @Test
    void webLoginSessionDoesNotAuthorizeStatelessApi()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        // Một session web có Authentication; API không lấy nó làm nguồn.
        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:reader"));

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());

        // Basic header hợp lệ vẫn có thể xác thực request API này.
        mvc.perform(get("/api/me")
                .session(session)
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void basicHeaderAloneDoesNotEnableWebBasicFilter()
            throws Exception {
        MvcResult result = mvc.perform(get("/web/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String redirect = result.getResponse().getRedirectedUrl();
        assertNotNull(redirect);
        assertTrue(redirect.contains("/login"));
    }

    @Test
    void webLoginPostRequiresCsrfByDefault() throws Exception {
        mvc.perform(post("/login")
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedReaderCannotVisitWebAdmin()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/admin").session(session))
            .andExpect(status().isForbidden());
    }
}
```

### 9.1. Test có chứng minh đúng HTTP Basic không?

Có: `httpBasic("reader", "reader-pass")` trong Spring Security Test tạo Authorization header Basic để request đi vào **filter chain thực**. Nó **không** tương đương `.with(user("reader"))`, vốn dựng sẵn người dùng đã xác thực và có thể bỏ qua password verification.

Khi request `/api/me` không có credentials, test còn kiểm tra `WWW-Authenticate` bắt đầu bằng `Basic` thay vì chỉ chấp nhận HTTP 401. Nhờ vậy, nó kiểm chứng phần lớn UX/protocol mong muốn của API.

### 9.2. Test ranh giới session giải thích điều gì?

`webLoginSessionDoesNotAuthorizeStatelessApi` dùng cùng một `MockHttpSession`, nhưng so sánh ba request:

1. `GET /web/me` → 200 với user đã đăng nhập bằng form.
2. `GET /api/me` cùng session, không Basic header → **401** vì API chain không dùng SecurityContext trong session.
3. `GET /api/me` cùng session và có Basic header → **200** vì Basic được kiểm tra cho request API hiện tại.

Test này chứng minh **khác biệt cơ chế và repository theo chain trong cấu hình cụ thể**, không phát biểu rằng không thể có bất kỳ API nào cho phép login bằng cookie. Những hệ thống muốn cookie-authenticated API có mô hình riêng và phải bảo vệ CSRF/session phù hợp.

### 9.3. Test nào kiểm tra routing khi có Basic header ở web?

`basicHeaderAloneDoesNotEnableWebBasicFilter` gửi Authorization Basic tới `/web/me` nhưng vẫn kỳ vọng redirect tới login. Lý do là web chain chỉ khai báo form login và không dùng Basic filter để tự động xác thực. Test này bắt được lỗi cấu hình khi vô tình bật cả hai cơ chế trong cùng chain.

### 9.4. Các test không giả tạo thời gian hoặc session ID

Các test không assert session ID cụ thể vì Spring Security có thể thực hiện session fixation protection. Test lấy `MockHttpSession` sau request login. Cũng không assert chuỗi HTML trang login mặc định hay chi tiết realm cố định vì có thể đổi theo Spring Security version/config.

## 10. Chạy ứng dụng và các kết quả HTTP

Tại thư mục `dual-chain-security` có `pom.xml`, dùng Maven + JDK 17 trở lên:

```bash
mvn test
mvn spring-boot:run
```

Nếu dependencies và môi trường phù hợp, **11 bài kiểm thử dự kiến pass**. Không khẳng định một stdout Maven duy nhất vì build log phụ thuộc thời gian/JVM/máy.

Có thể thử bằng `curl` ở **localhost để học**:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i http://localhost:8080/web/me
```

**Không dùng `curl -u` với credential thật trong shell history hoặc HTTP không mã hóa.** Ví dụ trên chỉ chạy local với tài khoản thử. Môi trường triển khai cần HTTPS và quy trình quản lý credential/secret hợp lý.

Kết quả HTTP về mặt logic:

| Request | Kết quả dự kiến | Ý nghĩa |
| --- | --- | --- |
| Anonymous GET `/api/public` | 200, `api:public` | `permitAll` trong API chain |
| Anonymous GET `/api/me` | 401 + `WWW-Authenticate: Basic ...` | API cần Basic credentials |
| Basic reader đúng, GET `/api/me` | 200, `api:reader` | API Basic thành công |
| Basic reader sai password, GET `/api/me` | 401 | Authentication failed |
| Basic reader đúng, GET `/api/admin` | 403 | Thiếu `ROLE_ADMIN` |
| Basic admin đúng, GET `/api/admin` | 200, `api:admin` | Đúng authority |
| Anonymous GET `/web/me` | 302 tới `/login` | Web form login |
| Form POST `/login` có CSRF và đúng mật khẩu | 302 sau login | Session-backed login |
| GET `/web/me` cùng session sau login | 200, `web:reader` | Form session có hiệu lực |
| GET `/api/me` chỉ có web session | 401 | API không đọc session authentication |
| GET `/api/me` có Basic và có web session | 200 | Basic quyết định cho request API |
| POST `/login` không có CSRF | 403 | CSRF trên web chain |

Dù web form login thành công, `/web/admin` vẫn trả 403 cho reader vì authentication và authorization là hai trách nhiệm khác nhau.

## 11. Một ví dụ Java 17 độc lập: hiểu first-match routing

`FilterChainProxy` thực hiện matcher dựa trên các `RequestMatcher` của Spring Security, không phải đơn thuần `String.startsWith`. Tuy nhiên có thể minh họa logic **chọn chain đầu tiên** bằng một chương trình Java 17 không có dependencies.

Tạo file `FirstMatchChainDemo.java`:

```java
import java.util.List;

public class FirstMatchChainDemo {

    record Chain(int order, String pattern, String mechanism) {
        boolean matches(String path) {
            if ("/**".equals(pattern)) {
                return true;
            }
            // Mô phỏng đơn giản đường dẫn thuộc /api/*.
            if ("/api/**".equals(pattern)) {
                return path.startsWith("/api/");
            }
            return pattern.equals(path);
        }
    }

    static String select(List<Chain> chains, String path) {
        for (Chain chain : chains) {
            if (chain.matches(path)) {
                return chain.mechanism();
            }
        }
        return "NO_CHAIN";
    }

    public static void main(String[] args) {
        List<Chain> correct = List.of(
            new Chain(1, "/api/**", "HTTP_BASIC"),
            new Chain(2, "/**", "FORM_LOGIN")
        );

        System.out.println("/api/orders -> "
            + select(correct, "/api/orders"));
        System.out.println("/web/me -> "
            + select(correct, "/web/me"));
        System.out.println("/login -> "
            + select(correct, "/login"));

        List<Chain> wrong = List.of(
            new Chain(1, "/**", "FORM_LOGIN"),
            new Chain(2, "/api/**", "HTTP_BASIC")
        );
        System.out.println("wrong order /api/orders -> "
            + select(wrong, "/api/orders"));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac FirstMatchChainDemo.java
java FirstMatchChainDemo
```

Stdout **chính xác**:

```text
/api/orders -> HTTP_BASIC
/web/me -> FORM_LOGIN
/login -> FORM_LOGIN
wrong order /api/orders -> FORM_LOGIN
```

Mô hình này cố ý đơn giản hóa matcher và giả định danh sách đã theo đúng thứ tự ưu tiên. Nó **không mô phỏng** filter authentication, CSRF, session, Spring PathPattern, Ant matching hay exception handling. Dùng nó để giải thích vì sao **fallback chain cần đứng sau chain chuyên biệt**, còn dùng bài MockMvc để kiểm chứng hành vi Servlet thật.

## 12. Khi nào cần hai chain và khi nào không?

Hai chain là lựa chọn hợp lý khi:

- API và web có **authentication entry point** khác nhau (Basic challenge 401 so với redirect HTML).
- API cần **stateless** còn web cần session.
- Policy request cache, CSRF, header handling hoặc exception handling khác nhau theo nhóm endpoint.
- Có yêu cầu riêng về nguồn credentials hoặc authentication providers.
- Bạn cần chứng minh mỗi URL thuộc một cấu hình security nhất quán, tránh điều kiện if/else chằng chịt trong một filter tùy biến.

Có thể dùng **một chain** khi mọi endpoint cùng cơ chế authentication/session/entry point và chỉ khác quy tắc quyền truy cập. Không nhất thiết thêm chain mới chỉ vì hai controller nằm ở hai package.

Nhiều chain làm cấu hình rõ ràng hơn khi nhu cầu thực sự khác nhau, nhưng cũng tăng yêu cầu kiểm thử matcher, default endpoints và fallback. Đừng tạo hàng loạt chain không có trách nhiệm phân biệt.

## 13. Các sai lầm thường gặp và hệ quả

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Web catch-all có `@Order(1)`, API ở `@Order(2)` | `/api/**` bị chain web “nuốt”, có thể redirect login thay vì 401 | Đặt API chain trước fallback, kiểm chứng bằng MockMvc |
| Chỉ dùng `requestMatchers("/api/**")` mà không `securityMatcher` | Chỉ tạo rule authorization, không phân tách filter mechanisms | Dùng `securityMatcher` trên API chain |
| Web chain bị khóa `securityMatcher("/web/**")` nhưng vẫn dùng login URL mặc định `/login` | GET/POST `/login` không thuộc chain mong đợi; login lỗi hoặc không được bảo vệ | Đưa login URL vào matcher hoặc dùng fallback web như ví dụ |
| Chỉ tạo chain API và không có fallback | Request ngoài API có thể không qua Spring Security | Có chain fallback, test URL không thuộc API |
| Bật cả formLogin và httpBasic trong API chain | Có thể không đạt hành vi 401 JSON/Basic mong muốn | Chỉ bật HTTP Basic ở API chain theo yêu cầu |
| Bật Basic trong web chain “cho tiện” | Browser có thể nhận challenge/credential behavior không mong muốn | Chỉ bật form login ở web chain |
| Dùng session sau web login để gọi API stateless mà không gửi header | API vẫn 401, client tưởng session “lỗi” | Gửi credential hợp lệ cho API hoặc thiết kế API cookie-auth có chủ đích |
| Gọi `STATELESS` rồi kết luận mọi request không thể tạo session | Code khác vẫn có thể tạo session ngoài security context | Kiểm thử lifecycle và components khác |
| Tắt CSRF trong mọi chain vì API stateless | Web form POST có thể mất lớp bảo vệ cần thiết | Đánh giá CSRF theo authentication mechanism và client; giữ bảo vệ web |
| Nghĩ HTTP Basic Base64 đã mã hóa an toàn | Credential dễ bị đọc trên mạng không có TLS | Bắt buộc HTTPS và bảo vệ credentials |
| Dùng `roles("ROLE_ADMIN")` thay vì `roles("ADMIN")` | Sai quy ước prefix/validation | Dùng `roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")` |
| Tưởng `permitAll` nghĩa là bỏ hết filters | Thiếu hiểu biết về headers, session, CSRF và filter routing | Phân biệt authorization permit và bypass filter |
| Chỉ assert mã 401 trong test API | Có thể bỏ sót header Basic challenge | Kiểm tra `WWW-Authenticate` phù hợp |
| Dùng `.with(user(...))` và kết luận password Basic đúng | Test có thể bypass xác minh username/password | Dùng `httpBasic(...)` qua filter chain |
| Thiếu kiểm tra request chưa tồn tại | Endpoint ngoài matcher có thể bị không bảo vệ | Có fallback `anyRequest().authenticated()` và test 404/auth |
| Đưa password thật vào code/curl/log | Lộ bí mật khi commit hoặc lưu shell history | Dùng secret manager/HTTPS, không log credentials |
| Gộp API và web logout thành cùng một kỳ vọng | Web session logout không thu hồi Basic header đã lưu | Tách chính sách session, mật khẩu, token và revoke |

### 13.1. Sai lầm đặc biệt: hai chain không có quan hệ “chain trước xử lý rồi chain sau xử lý tiếp”

Đây là lỗi tư duy dễ dẫn đến thiết kế nguy hiểm: nghĩ rằng có thể viết chain 1 chỉ xác thực Basic, rồi để chain 2 xử lý form login, sau đó chain 3 phân quyền trên cùng request. **Đó không phải cách `FilterChainProxy` chọn `SecurityFilterChain`**. Mỗi chain là một cấu hình filter hoàn chỉnh cho request mà nó nhận.

Nếu cần nhiều bước authentication hoặc authorization trên **một nhóm request**, cấu hình các filter/provider trong **cùng chain** hoặc dùng cơ chế Spring Security tương ứng. Không chia những filter đó thành nhiều chain rồi hy vọng nó ghép lại.

## 14. Kiểm tra bảo mật trước khi đưa lên production

### 14.1. Boundary và route coverage

- Tất cả URL API thực tế có thuộc `/api/**` không, kể cả phiên bản `/api/v2/**`, callback, health và error endpoint?
- Có endpoint API nằm ngoài tiền tố mà lại nhận HTML form-login redirect không?
- Chain fallback có bảo vệ mọi URL còn lại theo `anyRequest().authenticated()` không?
- Có actuator endpoints hoặc management port chạy security config khác cần xét riêng không?
- Có thay đổi `servletPath`, context path hoặc reverse-proxy rewrite làm matcher khác mong đợi không?

### 14.2. Authentication và credential protection

- HTTP Basic chỉ truyền qua HTTPS và không log credentials/Authorization header.
- Password được lưu bằng password hashing chuyên dụng, không plaintext hoặc reversible encryption.
- Có rate limiting/abuse detection trước các endpoint tốn tài nguyên kiểm tra password.
- Có phân biệt authentication failure và authorization failure không tiết lộ chi tiết user.
- Nếu API cần key/token riêng, có xem xét phương án phù hợp hơn dùng password tài khoản website không?

### 14.3. Session và CSRF

- Web login có lưu session đúng, logout xóa/vô hiệu hóa session phù hợp, cookie có Secure/HttpOnly/SameSite theo chính sách.
- API stateless có thật sự không đọc Authentication từ session web?
- Nếu API có POST/PUT/DELETE và được gọi từ browser, đã đánh giá CSRF dù dùng HTTP Basic chưa?
- Không tắt CSRF toàn cục chỉ để test POST login chạy; dùng CSRF token trong test và giao diện thật.
- Cần test security context handling dưới concurrent requests và phương thức async nếu ứng dụng có.

### 14.4. Monitoring và vận hành

- Log ở dev/staging thể hiện chain nào match, mechanism nào xử lý, phản hồi 401/302/403; không ghi bí mật.
- Có metrics số request/response theo nhóm API/web và tỉ lệ authentication failures.
- Biết chính xác 401 Basic do thiếu/sai credentials, 403 do policy, 302 do form entry point, tránh xử lý mọi lỗi như “session expired”.
- Cấu hình reverse-proxy headers và HTTPS redirect đúng đường, tránh open redirect/host header poisoning ở login/redirect.

## 15. Hướng debug khi kết hợp HTTP Basic và form login không như ý

Khi một API request bị chuyển tới `/login` thay vì nhận 401:

1. Xác minh URL chính xác, bao gồm context path/servlet path.
2. Bật log Spring Security ở môi trường phát triển để xem `FilterChainProxy` và filter handling:
   
   ```properties
   logging.level.org.springframework.security=DEBUG
   ```

3. Đọc thứ tự `@Order` trên mọi bean `SecurityFilterChain`; không giả định thứ tự bean khai báo trong file Java quyết định ưu tiên.
4. Kiểm tra API chain có `securityMatcher("/api/**")` thật không. `requestMatchers` bên trong `authorizeHttpRequests` **không thay thế** nó.
5. Kiểm tra có web catch-all ở order nhỏ hơn API không.
6. Kiểm tra API chain có bật `httpBasic` và không dùng form login theo yêu cầu không.
7. Kiểm tra request chưa xác thực có `WWW-Authenticate: Basic ...` không.
8. Nếu là 403, kiểm tra CSRF trên POST và authority trên request authenticated; không khẳng định mọi 403 là sai password.
9. Nếu là web login không hoạt động, kiểm tra `GET /login`/`POST /login` đi vào chain nào, CSRF token có hợp lệ, session có được giữ sau redirect.
10. Nếu web session xác thực được API ngoài dự kiến, kiểm tra `SessionCreationPolicy`, `SecurityContextRepository` và custom filters trên API chain.
11. Nếu API Basic credential hợp lệ nhưng vẫn 401, kiểm tra `UserDetailsService`, `PasswordEncoder`, account flags và nguồn provider đang được dùng.
12. Nếu endpoint lẽ ra bị bảo vệ lại public, kiểm tra matcher chain và rule authorization. Đừng chỉ xem annotation trên controller.

**Debug không cần in ra Authorization header hoặc password.** Dùng thông tin chain, URL path, trạng thái HTTP, tên filter, trace id và mã lỗi nội bộ an toàn.

## 16. Bài tập tự kiểm tra

**Bài 1.** Có hai chain:

```text
@Order(1) securityMatcher("/**") + formLogin
@Order(2) securityMatcher("/api/**") + httpBasic
```

Anonymous gọi `GET /api/me` sẽ đi chain nào?

**Đáp án:** Chain `@Order(1)` match mọi request và được chọn trước. API chain thứ hai không được xét tiếp. Nếu policy yêu cầu Basic 401, thứ tự này sai; hãy để API-specific chain có thứ tự ưu tiên cao hơn.

**Bài 2.** Chain API có `requestMatchers("/api/**").authenticated()` nhưng **không có `securityMatcher`**. Đã tách cơ chế Basic riêng cho API chưa?

**Đáp án:** Chưa. Đó là authorization rule trong chain, không phải điều kiện chọn chain; các filter authentication của chain vẫn áp dụng theo cấu hình chung.

**Bài 3.** Đăng nhập web bằng form login thành công, browser có session cookie. Gọi `/api/me` mà không có Authorization header, với API chain của bài, nhận gì?

**Đáp án:** HTTP 401 và Basic challenge. API dùng session policy stateless và `NullSecurityContextRepository`, không lấy Authentication từ web session.

**Bài 4.** User `reader` gửi Basic header đúng tới `/api/admin` và nhận 403. Đây có phải password sai?

**Đáp án:** Không. Credentials đã xác thực, nhưng `reader` không có authority `ROLE_ADMIN`. Thiếu quyền dẫn tới authorization denied.

**Bài 5.** Vì sao mặc định `POST /login` không có CSRF token có thể nhận 403 ngay cả khi password đúng?

**Đáp án:** CSRF filter chặn request state-changing trước khi authentication filter xử lý. Form login trong bài vẫn giữ CSRF protection; test cần dùng `.with(csrf())`.

**Bài 6.** Bạn đặt `securityMatcher("/web/**")` trên web chain nhưng vẫn dùng URL form login mặc định. Điều gì cần kiểm tra?

**Đáp án:** `/login` không thuộc `/web/**`; request GET/POST login có thể không đi qua web login filters. Mở rộng matcher để bao gồm login URL hoặc dùng fallback web chain và kiểm thử đầy đủ.

**Bài 7.** Khi dùng HTTP Basic stateless, có thể tắt CSRF mà không cần đánh giá gì không?

**Đáp án:** Không. Browser có thể tự gửi lại Basic credentials. Cần đánh giá client, cơ chế credential, endpoint có side effect và threat model. Ví dụ giữ CSRF mặc định.

**Bài 8.** Một HTTP request có thể chạy filter chain API rồi filter chain web theo thứ tự như middleware nhiều lớp không?

**Đáp án:** Không theo cơ chế `FilterChainProxy` chọn `SecurityFilterChain`: nó chọn chain đầu tiên khớp. Mọi filter cần cho request phải nằm trong chain được chọn.

**Bài 9.** Chỉ test GET `/api/me` với `.with(user("reader"))` có chứng minh Basic username/password và header hoạt động chưa?

**Đáp án:** Chưa. `user(...)` cung cấp security context thử nghiệm và có thể bypass Basic authentication. Test thực tế phải gửi header bằng `httpBasic(...)` hoặc HTTP client.

## 17. Ghi nhớ trọng tâm

- **Nhiều `SecurityFilterChain`** giúp tách chính sách HTTP Basic cho API và form login cho website trong cùng một Spring Security Servlet application.
- **`securityMatcher` chọn chain**, **`requestMatchers` chọn authorization rule trong chain**, **`@Order` quyết định thứ tự first-match**.
- Đặt `/api/**` với HTTP Basic ở chain ưu tiên cao hơn; để chain web catch-all ở sau để bao phủ `/login`, `/logout` và các URL khác.
- API Basic thường trả **401 + `WWW-Authenticate`** nếu thiếu/sai credentials; browser web thường nhận **302 tới login**; authenticated user thiếu quyền thường nhận **403**.
- Trong ví dụ API stateless dùng `NullSecurityContextRepository` và `NullRequestCache`; web dùng session form login. **Chia sẻ user store không có nghĩa chia sẻ session authentication**.
- Không coi HTTP Basic Base64 là mã hóa; dùng TLS. Không tự tắt CSRF chỉ vì stateless; cần đánh giá trình duyệt có tự gửi credentials không.
- Kiểm thử **cả hai nhóm request, các boundary và chain order**, đặc biệt URL login, Basic challenge, POST login + CSRF và việc web session không trở thành API authentication.
