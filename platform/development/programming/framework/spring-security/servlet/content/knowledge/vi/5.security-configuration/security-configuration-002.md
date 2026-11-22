# `securityMatcher` và `requestMatchers`: chọn chuỗi khác với chọn quy tắc

## 1. Vấn đề cần giải quyết

Trong ứng dụng Spring Security chạy trên **Servlet stack** (Spring MVC, Tomcat hoặc Servlet container tương đương), nhiều lập trình viên thấy `securityMatcher("/api/**")` và `requestMatchers("/api/**")` đều nhận một mẫu đường dẫn nên cho rằng chúng có thể thay thế nhau. Thực tế, **hai lời gọi kiểm soát hai giai đoạn khác nhau của request**:

- **`HttpSecurity.securityMatcher(...)`** quyết định **cả một `SecurityFilterChain` có áp dụng cho request hay không**. Nó đặt phạm vi hoạt động cho toàn bộ filter chain, bao gồm cơ chế authentication, authorization, CSRF, login/logout và các cấu hình filter tương ứng.
- **`authorizeHttpRequests(auth -> auth.requestMatchers(...))`** quyết định **quy tắc phân quyền nào áp dụng bên trong chain đã được chọn**. Nó chỉ có ý nghĩa khi `FilterChainProxy` đã chọn được chain chứa quy tắc ấy.

Nhầm lẫn này có thể dẫn tới những lỗi nghiêm trọng: endpoint nằm ngoài `securityMatcher` không được bất kỳ chain nào bảo vệ; cấu hình `permitAll` không có hiệu lực; request bị xử lý bằng cơ chế đăng nhập sai; hoặc một chain rộng che mất chain chuyên biệt.

Mục tiêu của bài:

1. Đọc được thứ tự xử lý **chọn chain → chạy filter → chọn authorization rule → cho phép/từ chối**.
2. Viết được cấu hình một chain và nhiều chain có `@Order`, matcher đúng phạm vi và quy tắc dự phòng rõ ràng.
3. Phân tích chính xác request cụ thể thuộc chain nào và rule nào, kể cả khi có rule phủ định hoặc hai chain giao nhau.
4. Nhận ra vì sao `permitAll()`, `anyRequest()`, `securityMatcher()`, HTTP method và CSRF có phạm vi khác nhau.
5. Kiểm thử để không bỏ sót route khi ứng dụng bổ sung endpoint mới.

## 2. Hai cấp chọn trong Servlet security

Request Servlet thường đi theo luồng:

```text
HTTP request
    |
Servlet container
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |-- kiểm tra SecurityFilterChain theo thứ tự ưu tiên
    |     |
    |     +-- chain đầu tiên có securityMatcher phù hợp
    |             |
    |             +-- thực thi các filter trong chain được chọn
    |                    |
    |                    +-- authentication / context / CSRF / ...
    |                    |
    |                    +-- AuthorizationFilter
    |                           |
    |                           +-- chọn requestMatchers đầu tiên khớp
    |                           +-- áp dụng permitAll/authenticated/hasRole/denyAll...
    |                                    |
    +------------------------------------+--> controller nếu được phép
```

`DelegatingFilterProxy` là cầu nối giữa Servlet container và bean Spring Security. `FilterChainProxy` chứa nhiều `SecurityFilterChain`, kiểm tra matcher của chúng theo thứ tự và dùng **chain đầu tiên phù hợp**. Khi request đã vào một chain, Spring Security **không tự thử chain tiếp theo** nếu request bị từ chối do thiếu quyền, CSRF hoặc authentication.

Bên trong chain đó, `AuthorizationFilter` sử dụng các quy tắc do `authorizeHttpRequests` cấu hình. Quy tắc **đầu tiên phù hợp** quyết định kết quả authorization. Một request có thể bị chặn **trước khi tới** authorization (ví dụ CSRF filter từ chối POST không có token). Vì vậy, bảng authorization không phải là toàn bộ các bước bảo mật của request.

### Bảng phân biệt

| Câu hỏi | `http.securityMatcher(...)` | `authorizeHttpRequests(...requestMatchers(...))` |
| --- | --- | --- |
| Được gọi ở đâu? | Trên `HttpSecurity` cho một bean `SecurityFilterChain` | Trong bộ quy tắc `authorizeHttpRequests` của chain |
| Mục tiêu | Chọn **có chạy chain này không** | Chọn **rule authorization nào** khi chain đã chạy |
| Đối tượng chịu ảnh hưởng | Toàn bộ security filters của chain | Quyết định cho phép/từ chối ở tầng authorization |
| Khi không khớp | `FilterChainProxy` thử chain tiếp theo | Thử rule tiếp theo **trong cùng chain** |
| Khi khớp nhưng bị từ chối | Không quay sang chain khác | Request bị từ chối; không quay sang rule sau |
| `anyRequest()` là gì? | Không phải matcher thay thế cho việc có chain bao phủ | Rule bắt mọi request **đã vào chain hiện tại** |
| Mục đích thường dùng | Phân khu API, ứng dụng web, actuator, endpoint theo protocol | Public/private, GET/POST, vai trò, authority |
| Sai lầm điển hình | Quên chain dự phòng làm endpoint không có security filters | Tưởng rule bảo vệ URL ở ngoài scope của chain |

Cả hai cơ chế đều dựa trên `RequestMatcher`; sự khác nhau ở **nơi matcher được đánh giá**. Tên hàm giống nhau không khiến chúng có cùng vai trò.

## 3. Mặc định của một `SecurityFilterChain` và `anyRequest()`

Xem cấu hình chỉ có một chain:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **đoạn cấu hình minh họa**, cần import thích hợp và đặt trong class `@Configuration`. Do không gọi `securityMatcher`, matcher ở cấp chain mặc định khớp mọi request. Những request đi vào chain sẽ được xét các rule: `/public/**` được phép; `/admin/**` cần `ROLE_ADMIN`; còn lại cần đăng nhập.

Ngược lại:

```java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Chain thứ hai **chỉ tồn tại đối với request được `/api/**` match**. `anyRequest().authenticated()` nghĩa là "mọi request còn lại **trong chain API này**", hoàn toàn không có nghĩa "mọi đường dẫn trong ứng dụng".

Một request `GET /admin/users` **không** được bảo vệ bởi chain API trên. Nếu ứng dụng không định nghĩa chain nào khác khớp nó, request đi tiếp mà **không chịu các security filters thuộc bất kỳ `SecurityFilterChain` nào**. Một dự án đã tự khai báo bean `SecurityFilterChain` cũng không nên dựa vào việc Spring Boot tự tạo hộ một fallback chain có chính sách mong muốn.

### Quy tắc nhớ nhanh

- `securityMatcher` tạo **ranh giới chain**.
- `requestMatchers` trong `authorizeHttpRequests` tạo **ranh giới rule**.
- `anyRequest()` ở cuối bộ rule bắt phần còn lại **trong phạm vi chain đang xét**.
- Matcher không khớp chain không giống với **bị từ chối**. Thiếu chain dự phòng có thể tạo lỗ hổng; `denyAll()` bên trong chain chỉ từ chối request **đã được chọn vào chain**.

## 4. Nhiều chain: chọn theo thứ tự, không chọn theo "độ đặc hiệu"

Giả sử ứng dụng cần cơ chế bảo vệ API và phần web khác nhau. Ta định nghĩa:

```text
@Order(1) API chain:
    securityMatcher("/api/**")
    - GET /api/public   -> permitAll
    - GET /api/profile  -> authenticated
    - GET /api/admin    -> hasRole("ADMIN")
    - còn lại trong /api/** -> denyAll

@Order(2) Web fallback chain:
    securityMatcher mặc định: mọi request
    - GET /home         -> permitAll
    - GET /account      -> authenticated
    - còn lại           -> denyAll
```

Khi request đến, `FilterChainProxy` kiểm tra `@Order(1)` rồi `@Order(2)`. Với `/api/profile`, chain API khớp nên chain web không còn cơ hội xử lý. Với `/home`, chain API không khớp, nên chain web tiếp nhận.

**Không nên tin framework sẽ tự chọn matcher "cụ thể hơn".** Thứ tự ưu tiên chain được quyết định bởi `@Order` (hoặc thứ tự cấu hình tương đương). Chain match mọi request đặt trước chain API có thể che mất toàn bộ API chain.

```text
SAI:
  @Order(1) chain mặc định khớp mọi request
  @Order(2) chain /api/**                 <-- không bao giờ được chọn

ĐÚNG:
  @Order(1) chain /api/**
  @Order(2) chain mặc định khớp mọi request
```

Với `@Order`, số thấp có độ ưu tiên cao hơn. Chain cuối có matcher mặc định khớp mọi request là một cách bảo đảm không có khoảng trống. Khi có nhiều chain, hãy đặt tên bean có nghĩa, viết rõ ưu tiên và kiểm thử các URL giao nhau.

## 5. Ví dụ hoàn chỉnh: Spring Boot 3.x, Spring MVC, Java 17+

Ví dụ dưới đây dùng **HTTP Basic để minh họa** trên cả hai chain, qua đó tập trung vào lựa chọn chain/rule. Ứng dụng thật có thể có cơ chế xác thực khác nhau giữa các chain. Mã dùng Java 17+, Spring Boot 3.x và Spring Security 6.x; không phải cấu hình sẵn có cho WebFlux.

Với một dự án Spring Boot đã có plugin build và dependency management, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/example/matchers/ChainMatcherDemoApplication.java`:

```java
package example.matchers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ChainMatcherDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainMatcherDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            // Không có securityMatcher -> matcher mặc định khớp mọi request.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/home").permitAll()
                .requestMatchers(HttpMethod.GET, "/account").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/api/public")
    String apiPublic() {
        return "api public";
    }

    @GetMapping("/api/profile")
    String apiProfile(Authentication authentication) {
        return "api profile: " + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "api admin";
    }

    @GetMapping("/home")
    String home() {
        return "web home";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "web account: " + authentication.getName();
    }
}
```

Để Java chấp nhận cả ba top-level class trong cùng một tệp, chỉ `ChainMatcherDemoApplication` được khai báo `public`; hai class còn lại có phạm vi package-private. Spring Boot quét package `example.matchers` và đăng ký `@Configuration`, `@RestController`.

Trong cấu hình này:

- `apiChain` có **chain matcher** `/api/**`. Mọi rule của nó chỉ xét những request đã vào phạm vi API.
- `webChain` không gọi `securityMatcher`, nên dùng matcher mặc định khớp mọi request. Nó là **chain dự phòng** cho các URL không vào API.
- Hai chain đều dùng HTTP Basic, vì vậy trong bài demo, client chưa xác thực gọi endpoint cần đăng nhập thường nhận `401`; người dùng đã đăng nhập nhưng thiếu quyền thường nhận `403`.
- `.roles("ADMIN")` tạo authority `ROLE_ADMIN`, nên khớp `hasRole("ADMIN")`. Nếu dùng `hasAuthority("ADMIN")` thay thế, phép so khớp sẽ khác.
- `PasswordEncoder` mã hóa mật khẩu demo trước khi lưu trong bộ nhớ. Username/password cố định chỉ dùng để học. Môi trường thật cần TLS/HTTPS và hệ thống quản lý danh tính phù hợp.
- Các endpoint demo đều là **GET**; CSRF protection mặc định vẫn được giữ nguyên. Đừng suy rằng cấu hình này cho phép tự do gửi POST/PUT/DELETE mà không có CSRF token khi một cơ chế đăng nhập dựa vào credential do browser tự gửi.

Để chạy trong dự án Gradle Spring Boot phù hợp, dùng:

```bash
./gradlew bootRun
```

Trên Windows PowerShell có thể chạy `./gradlew.bat bootRun`. Sau khi ứng dụng khởi động trên cổng HTTP 8080 của môi trường **local**, thử:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo-reader http://localhost:8080/api/profile
curl -i -u reader:demo-reader http://localhost:8080/api/admin
curl -i -u admin:demo-admin http://localhost:8080/api/admin
curl -i http://localhost:8080/home
curl -i http://localhost:8080/account
curl -i -u reader:demo-reader http://localhost:8080/account
```

**Kết quả dự kiến** (status/body quan trọng; bỏ qua header HTTP và thứ tự trả về header có thể khác theo phiên bản/môi trường):

| Request | Chain chọn | Rule được chọn | Kết quả |
| --- | --- | --- | --- |
| `GET /api/public`, anonymous | API | `permitAll` | 200, `api public` |
| `GET /api/profile`, anonymous | API | `authenticated` | 401 (HTTP Basic challenge) |
| `GET /api/profile`, reader | API | `authenticated` | 200, `api profile: reader` |
| `GET /api/admin`, reader | API | `hasRole("ADMIN")` | 403 |
| `GET /api/admin`, admin | API | `hasRole("ADMIN")` | 200, `api admin` |
| `GET /home`, anonymous | Web fallback | `permitAll` | 200, `web home` |
| `GET /account`, anonymous | Web fallback | `authenticated` | 401 (HTTP Basic challenge) |
| `GET /account`, reader | Web fallback | `authenticated` | 200, `web account: reader` |

Lưu ý đây là **kết quả kỳ vọng từ mã**, không phải stdout được lấy từ một lần chạy thực tế. Để chứng minh từng request vào chain nào, ngoài kiểm tra status, có thể bật logging Spring Security tạm thời trong môi trường phát triển.

## 6. Phân tích từng request: chính xác ở bước nào?

### Tình huống A — `GET /api/public`

1. `FilterChainProxy` xét chain `@Order(1)`: `/api/**` khớp `/api/public`.
2. Chain API được chọn; chain web **không được xem xét tiếp**.
3. Các security filters trong chain API xử lý request; sau đó authorization xét rule `GET /api/public`.
4. `permitAll` cho phép request không cần authentication, nhưng vẫn là request đi qua chain API.
5. Controller trả `api public`.

Nếu thêm `/api/public` vào `requestMatchers(...).permitAll()` của **web chain** mà bỏ rule tương ứng trong API chain, request này vẫn đi vào API chain trước; rule ở web chain không bao giờ tác động tới nó.

### Tình huống B — `GET /api/admin` với reader

1. Chọn chain API theo `securityMatcher("/api/**")`.
2. Authentication từ HTTP Basic thành công với authority `ROLE_USER`.
3. Rule `GET /api/admin` yêu cầu `ROLE_ADMIN`; user không đáp ứng.
4. Request bị từ chối (trong cấu hình này thường 403). **Không thử chain web**, dù chain web có matcher mặc định bao phủ mọi URL.

Điều này chứng minh "không khớp chain thì thử chain kế tiếp" là **khác** với "đã khớp chain nhưng thiếu quyền thì thử chain kế tiếp".

### Tình huống C — `GET /home`

Chain API không khớp nên `FilterChainProxy` xét chain web, nơi rule `GET /home` trả `permitAll`. Đường dẫn `/home` hoàn toàn không đi vào các bộ lọc chỉ được cấu hình riêng trong API chain.

### Tình huống D — `GET /api/unknown`

Chain API khớp, nhưng không có rule cụ thể cho `GET /api/unknown`. `anyRequest().denyAll()` **trong API chain** bắt request này. Nếu caller đã xác thực, access bị từ chối. Sự hiện diện của chain web không giúp request "thoát" chính sách denyAll của API.

### Tình huống E — `POST /api/public`

Chain API vẫn khớp `/api/**`. Tuy nhiên rule public trong ví dụ chỉ dành cho **GET**. POST không phù hợp rule đó; đồng thời CSRF filter có thể từ chối POST trước khi tới authorization nếu thiếu token. Vì vậy **không suy ra** endpoint là public đối với mọi method chỉ vì `GET /api/public` cho anonymous truy cập.

## 7. Thứ tự các `requestMatchers` quan trọng thế nào?

Trong một chain, các rule của `authorizeHttpRequests` được xét theo thứ tự định nghĩa. Rule rộng ở phía trước có thể nuốt rule cụ thể phía sau.

Ví dụ thiếu chính xác:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Vì `/api/admin/users` đã khớp `/api/**`, rule `hasRole("ADMIN")` phía sau **không được dùng**. Cách đặt đúng là ưu tiên rule hẹp:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
```

Đây là **đoạn cấu hình minh họa** để chèn vào một `HttpSecurity` có phạm vi phù hợp. Lưu ý `anyRequest()` thường phải là **quy tắc cuối**; sau khi đã khai báo rule bắt toàn bộ request, thêm rule mới phía sau là sai ý nghĩa và có thể bị framework từ chối tại thời điểm xây cấu hình.

Cách kiểm tra bằng mắt khi đọc code:

- Trước tiên xác định **chain bao phủ request không?**
- Trong chain, đọc các rule **từ trên xuống**; tìm rule đầu tiên khớp cả path, method và điều kiện matcher.
- Sau khi tìm thấy rule khớp, dừng tìm rule khác; kiểm tra authentication, authorities và các filter bảo vệ khác.
- Nếu rule cuối là `denyAll()`, một route quên khai báo sẽ bị từ chối; nếu cuối là `authenticated()`, mọi route trong chain chưa được khai báo riêng cần đăng nhập; nếu cuối là `permitAll()`, bạn phải giải thích vì sao việc mở mặc định là chủ ý.

## 8. Ranh giới matcher của Servlet: path, HTTP method và dispatcher

Cả hai API đều có thể nhận nhiều kiểu `RequestMatcher`; các overload dùng chuỗi path có thể lựa chọn matcher phù hợp với môi trường Spring MVC/Spring Security, nên không nên khẳng định mọi pattern luôn theo một cơ chế duy nhất. Khi ứng dụng có nhiều Servlet, servlet path đặc biệt hoặc cấu hình dispatcher riêng, hãy dùng matcher tường minh thích hợp và kiểm thử bằng URL thực.

Những chi tiết dễ bị bỏ sót:

1. **HTTP method:** `requestMatchers(HttpMethod.GET, "/api/profile")` khác với `requestMatchers("/api/profile")` (không giới hạn vào GET). Chính sách POST/PUT/PATCH/DELETE phải được định nghĩa có chủ ý.
2. **Context path và Servlet path:** RequestMatcher cho MVC thường đánh giá đường dẫn theo ngữ cảnh Servlet tương ứng. Đừng ghép nhầm `server.servlet.context-path` với pattern hoặc giả định `/api/**` luôn bao phủ mọi đường dẫn khi ứng dụng có nhiều servlet.
3. **Chính đường dẫn gốc:** Nếu muốn cả `/api` lẫn `/api/**`, hãy xác định và kiểm thử cả hai. Đừng tự suy luận cách mọi loại matcher xử lý dấu slash, hậu tố hay path biến.
4. **Dispatcher type:** Request có thể trải qua `REQUEST`, `FORWARD`, `ERROR`, `ASYNC`; route error view hoặc forward nội bộ có thể cần quy tắc phù hợp. Không mở toàn bộ các dispatcher type chỉ để tránh lỗi 403 mà chưa hiểu ranh giới dữ liệu.
5. **Các path do framework tạo:** Login, logout, OAuth callback, Swagger/UI, `/error`, static assets hoặc health endpoints có thể không nằm trong `securityMatcher` mà bạn dự tính. Đối với form login, URL login page và login processing phải thuộc phạm vi một chain có filter phù hợp và được cấp quyền truy cập theo thiết kế.
6. **`securityMatcher` giới hạn cả filter chain:** Nếu chain API có `httpBasic` còn chain web có `formLogin`, việc một URL rơi vào chain nào còn quyết định authentication entry point/redirect và loại security filter được áp dụng.

Riêng về request matching, Spring Security thường cung cấp các matcher tích hợp với Spring MVC và các matcher tường minh. Khi có cấu hình Servlet phức tạp, đừng dựa vào tên overload hoặc giả định chung về `Ant`/`MVC` để đảm bảo kết quả; hãy kiểm thử đường đi thực tế với stack và phiên bản của ứng dụng.

## 9. Vì sao `permitAll()` khác với bỏ qua filter chain?

Hai cách mở endpoint không tương đương:

```java
// Vẫn nằm trong chain, chỉ cho phép qua bước authorization.
.requestMatchers("/public/**").permitAll()
```

và thiết kế khiến request **không khớp chain nào** (hoặc bỏ qua security filters bằng cơ chế web ignoring). Với `permitAll`, các filter còn lại của chain vẫn có thể chạy, chẳng hạn filter thiết lập HTTP security headers, xử lý CSRF, authentication hoặc những filter tùy biến.

Vì vậy, với tài nguyên public nhưng vẫn phục vụ qua ứng dụng có Spring Security, thường ưu tiên **`permitAll()` trong một chain có bao phủ route**. Nếu dùng `securityMatcher` quá hẹp và không có fallback, một endpoint public có thể vô tình không nhận những header hoặc bảo vệ chung dự kiến. Đừng dựa vào "trang này public" để bỏ qua các lớp bảo vệ HTTP khác.

Đặc biệt, `permitAll()` **không tự vô hiệu hóa CSRF**. Một route POST được permit về authorization vẫn cần CSRF token nếu cấu hình CSRF áp dụng. Với API dùng bearer token độc lập và không dựa vào cookie browser tự gửi, CSRF có thể được thiết kế khác, nhưng cần đánh giá loại credential và client trước khi quyết định.

## 10. Nếu mỗi chain dùng cơ chế đăng nhập khác nhau?

Tách `SecurityFilterChain` có ích khi API và browser UI thực sự có **cấu hình filter khác nhau**. Ví dụ:

```text
API /api/**:
  - bearer token hoặc HTTP Basic theo yêu cầu
  - response API 401/403 thích hợp
  - chính sách session/CSRF được xem xét riêng

Browser UI /app/** hoặc fallback:
  - form login hoặc OAuth2 login
  - cookie/session và CSRF token
  - redirect tới login page và logout phù hợp
```

Khi đó, chọn chain đúng là bước quyết định **cơ chế authentication nào có mặt**. Thêm một `requestMatchers("/api/**").authenticated()` vào web chain **không tự tạo** một API chain hay chuyển sang bearer-token authentication.

Nếu API chain chỉ match `/api/**` nhưng trang login được đặt tại `/login`, phải bảo đảm một chain khác thực sự xử lý `/login` và endpoint xử lý login. Lỗi phổ biến là định nghĩa một chain scope quá hẹp nhưng lại kỳ vọng filter đăng nhập của chain đó phục vụ một path nằm ngoài scope.

Nếu cần nhiều `SecurityFilterChain`, mỗi chain nên tự mô tả rõ:

- `securityMatcher`: request nào thuộc chain;
- `@Order`: chain được xét ở vị trí nào;
- authentication: Basic, form login, OAuth2 resource server hay cơ chế khác;
- authorization: các `requestMatchers` theo thứ tự và rule cuối `anyRequest`;
- CSRF/session/CORS/headers: chính sách phù hợp với đúng loại client;
- các endpoint kỹ thuật: login, logout, error, health, static assets và callback.

## 11. Kiểm thử tự động để chứng minh chain và rule

Đừng chỉ kiểm tra `GET /api/public` trả 200. Một thay đổi nhỏ trong `@Order` có thể khiến chain sai bắt request. Với dự án ví dụ ở trên, thêm dependency test:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/test/java/example/matchers/SecurityChainsTest.java`:

```java
package example.matchers;

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
class SecurityChainsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiWorksWithoutCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api public"));
    }

    @Test
    void apiRequiresLogin() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(content().string("api admin"));
    }

    @Test
    void webFallbackStillProtectsAccount() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/account").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isOk())
            .andExpect(content().string("web account: reader"));
    }

    @Test
    void unknownApiRouteIsDeniedToAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/unknown").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isForbidden());
    }
}
```

Chạy trong dự án đã có Gradle wrapper:

```bash
./gradlew test
```

Đây là **mã test đề xuất**, không phải kết quả chạy được xác nhận trong tài liệu. `MockMvc` thực thi cấu hình Spring Security của ứng dụng trong môi trường test, giúp phát hiện lỗi rule và chain. Muốn xác minh filter chain cụ thể ở runtime, bật debug log chỉ trên môi trường phát triển:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Quan sát matcher và filter ở log, rồi tắt debug khi không cần. Log bảo mật có thể lộ metadata nhạy cảm về request; tuyệt đối không chủ động ghi raw token hoặc password để debug.

### Ma trận test cần có khi mở rộng ứng dụng

| Lớp test | Các tình huống quan trọng |
| --- | --- |
| Chọn chain | URL dưới `/api/**`; ngoài `/api/**`; URL sát ranh giới `/api`; chain fallback |
| Authorization rule | Anonymous, user thường, admin; rule hẹp và rule rộng; rule cuối |
| HTTP method | GET so với POST/PUT/DELETE; 405/403 có đúng nguyên nhân không |
| CSRF và login | Cookie/browser POST có CSRF token; API credential mode; login/logout nằm đúng chain |
| Hành vi thất bại | 401/403/redirect theo từng cơ chế authentication, không tự rơi sang chain khác |
| Tài nguyên bổ sung | `/error`, health, assets, callback, Swagger/UI nếu ứng dụng thực sự dùng |
| Quyền ở mức domain | User đã đăng nhập nhưng không được xem dữ liệu thuộc người khác |

Status 401, 403 hoặc redirect còn phụ thuộc authentication entry point, access denied handler và CSRF được cấu hình. Khi test không khớp kỳ vọng, hãy điều tra filter gây ra phản hồi trước khi sửa matcher.

## 12. Lỗi thường gặp và cách sửa

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `securityMatcher("/api/**")` nhưng tưởng `anyRequest()` bảo vệ cả web | Route ngoài API có thể không có chain bao phủ | Thêm fallback `SecurityFilterChain` match mọi request |
| Đưa chain match mọi URL lên đầu | Các chain chuyên biệt không được chọn | Dùng `@Order` để chain hẹp xét trước |
| Thêm `requestMatchers("/admin/**")` vào chain chỉ match `/api/**` | Rule không thể áp dụng cho `/admin/**` | Đặt rule vào chain thực sự bao phủ URL đó |
| Trong một chain, đặt `/api/**` trước `/api/admin/**` | Rule rộng che mất rule admin | Đặt rule hẹp ở phía trên |
| Hiểu `permitAll()` là bỏ mọi filter | Bất ngờ khi POST gặp 403 CSRF | Phân biệt authorization với bảo vệ CSRF/filter |
| Tưởng 403 ở chain đầu khiến chọn chain tiếp theo | Đánh giá sai phạm vi bảo mật và debug sai | Nhớ cơ chế chọn **chain đầu tiên khớp** |
| Không test HTTP method | GET public nhưng POST vẫn bị chặn hoặc đi vào rule khác | Đặt matcher theo method và kiểm thử độc lập |
| Dùng form login ở chain scope hẹp mà login path ở ngoài scope | Mất login page/endpoint xử lý đăng nhập | Thiết kế matcher bao gồm login hoặc dùng chain phù hợp |
| Bỏ fallback vì nghĩ Boot sẽ tự thêm | Endpoint mới không được bảo vệ như mong muốn | Định nghĩa rõ catch-all chain và policy cuối |
| Chỉ đọc tên `requestMatchers` mà không xem chain bao ngoài | Hiểu sai rule có hiệu lực với URL nào | Luôn truy từ `securityMatcher` và `@Order` trước |

## 13. Bài tập vận dụng

**Bài 1.** Hai chain được khai báo:

```text
@Order(1) securityMatcher("/internal/**")
          requestMatchers("/internal/admin/**").hasRole("ADMIN")
          anyRequest().authenticated()

@Order(2) matcher mặc định cho mọi request
          requestMatchers("/public/**").permitAll()
          anyRequest().denyAll()
```

Với `GET /internal/admin/settings` của người dùng có `ROLE_USER`, chain/rule nào được chọn? Có chuyện request được thử lại ở chain 2 không?

**Đáp án:** Chọn chain 1 và rule `hasRole("ADMIN")`; user không đủ quyền nên bị từ chối. Chain 2 không được thử lại.

**Bài 2.** Với hai chain trên, `GET /public/info` của anonymous do chain nào xử lý? **Đáp án:** Chain 1 không khớp; chain 2 khớp và `permitAll` cho `/public/**`.

**Bài 3.** Nếu đổi `@Order(1)` thành một chain bắt mọi URL và đặt `/internal/**` xuống `@Order(2)`, điều gì xảy ra? **Đáp án:** Chain bắt mọi URL chọn trước, khiến chain riêng `/internal/**` không bao giờ được sử dụng; muốn tách chính sách phải đổi thứ tự hoặc scope.

**Bài 4.** Một API chain có `securityMatcher("/api/**")` nhưng không có fallback. Nêu hai việc phải làm trước khi triển khai. **Đáp án:** Xác định và cấu hình chain bao phủ mọi URL khác cần bảo vệ; kiểm thử route ở ngoài scope và các route sát ranh giới để chứng minh chúng không bị lọt khỏi security filters.

**Bài 5.** Tại sao `requestMatchers("/api/open").permitAll()` không đủ đảm bảo browser POST thành công? **Đáp án:** Authorization `permitAll` không vô hiệu hóa CSRF; các filter khác có thể chặn POST và quy tắc matcher có thể bị giới hạn bởi HTTP method.

**Nguyên tắc cốt lõi:** `securityMatcher` chọn **cả chuỗi filter** cho request; `requestMatchers` trong `authorizeHttpRequests` chọn **quy tắc phân quyền** bên trong chuỗi ấy. Khi xem một URL có an toàn không, luôn kiểm tra hai cấp này theo đúng thứ tự và chứng minh chúng bằng test thực tế.
