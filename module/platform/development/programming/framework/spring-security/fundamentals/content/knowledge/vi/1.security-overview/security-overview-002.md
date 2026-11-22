# Xác thực, phân quyền và bảo vệ trước tấn công: ba nhóm chức năng chính của Spring Security

Trong ứng dụng Spring sử dụng Servlet/Spring MVC, Spring Security cung cấp các cơ chế để **xác định ai đang gửi yêu cầu**, **quyết định người đó có quyền làm gì** và **giảm thiểu những kiểu tấn công phổ biến vào ứng dụng web**. Đây là ba nhóm chức năng liên quan nhưng có mục đích khác nhau: **authentication**, **authorization** và **exploit protection**.

## 1. Bức tranh tổng thể: ba câu hỏi khác nhau

| Nhóm chức năng | Câu hỏi chính | Ví dụ | Kết quả mong muốn |
| --- | --- | --- | --- |
| Xác thực (Authentication) | “Bạn là ai? Có bằng chứng đáng tin cậy không?” | Kiểm tra username/password, HTTP Basic, bearer token | Thiết lập danh tính đã xác thực cùng các quyền được cấp |
| Phân quyền (Authorization) | “Danh tính này có được thực hiện hành động này không?” | Chỉ ADMIN được gọi `/api/admin/**`; người dùng chỉ xem dữ liệu của chính mình | Cho phép hoặc từ chối truy cập tài nguyên/chức năng |
| Bảo vệ trước tấn công (Exploit protection) | “Yêu cầu hoặc phản hồi có thể bị lợi dụng theo cách đã biết không?” | Kiểm tra CSRF token, thêm security headers, hỗ trợ bảo vệ phiên | Giảm rủi ro tấn công ngay cả khi ứng dụng đã có login và rule phân quyền |

Ví dụ: Alice đăng nhập hợp lệ nhưng không phải quản trị viên. Hệ thống **xác thực thành công** Alice, sau đó **từ chối phân quyền** cho thao tác quản trị. Nếu Alice đang đăng nhập bằng cookie và một website lạ cố gửi lệnh chuyển tiền thay Alice, **CSRF protection** còn phải kiểm tra tính hợp lệ của yêu cầu thay đổi trạng thái. Ba việc này không thay thế cho nhau.

Spring Security chủ yếu áp dụng các chính sách trong **`SecurityFilterChain`** của ứng dụng Servlet. Một request đi qua các security filter phù hợp trước khi tới controller. Các filter có thể xử lý chứng thực, ngữ cảnh bảo mật, CSRF và quyết định truy cập; thứ tự chi tiết phụ thuộc cấu hình. Việc request có username hợp lệ không đồng nghĩa request được phép vượt qua mọi lớp kiểm tra.

## 2. Xác thực (Authentication): biết danh tính người gọi

### 2.1. Xác thực kiểm tra điều gì?

Xác thực là quá trình kiểm tra bằng chứng về danh tính: mật khẩu, chứng chỉ, token hoặc phương thức tương ứng với hệ thống. Nếu hợp lệ, Spring Security biểu diễn danh tính bằng đối tượng **`Authentication`**. Đối tượng này thường chứa:

- **`principal`**: người dùng hoặc chủ thể đã được xác thực;
- **`credentials`**: thông tin dùng để chứng thực, được hạn chế/loại bỏ khi thích hợp;
- **`authorities`**: danh sách `GrantedAuthority`, chẳng hạn `ROLE_ADMIN` hoặc quyền `invoice:read`;
- **`isAuthenticated()`**: trạng thái xác thực của đối tượng.

Các thành phần thường gặp:

- `AuthenticationManager` là giao diện điều phối việc xác thực; triển khai phổ biến là `ProviderManager`.
- Một hoặc nhiều `AuthenticationProvider` biết cách xử lý cơ chế xác thực cụ thể, ví dụ username/password.
- `SecurityContext` lưu `Authentication` hiện tại; `SecurityContextHolder` là điểm truy cập ngữ cảnh đó trong luồng xử lý Servlet thông thường.
- `AuthenticationEntryPoint` xử lý tình huống cần người dùng cung cấp thông tin xác thực, ví dụ trả HTTP 401 kèm `WWW-Authenticate` hoặc chuyển hướng tới trang đăng nhập.

Dòng xử lý khái niệm:

```text
Request + thông tin xác thực
        |
        v
Security Filter -> AuthenticationManager -> AuthenticationProvider
                                                |
                                    xác thực thành công/thất bại
                                                |
                   thành công -> Authentication -> SecurityContext
                                                |
                                     tiếp tục kiểm tra quyền
```

Đây là mô hình logic, không phải sơ đồ thứ tự cố định của tất cả các filter. Với session login, ngữ cảnh xác thực có thể được khôi phục từ phiên; với bearer token, hệ thống thường xác thực token theo từng request. Cách lưu hoặc tái dựng ngữ cảnh tùy cơ chế và cấu hình.

### 2.2. Ví dụ và điểm dễ nhầm

- **Đăng nhập thành công** chứng minh danh tính tại thời điểm kiểm tra; chưa đảm bảo được phép truy cập `/admin`.
- **Người dùng chưa đăng nhập** và **người dùng đã đăng nhập nhưng thiếu quyền** là hai trường hợp khác nhau.
- Password nên được lưu dưới dạng **hash thích hợp**, sử dụng `PasswordEncoder`; không lưu plaintext hoặc tự so sánh hash thủ công.
- Khi dùng HTTP Basic, thông tin đăng nhập được gửi trong header `Authorization` qua mỗi request. Phải dùng HTTPS khi triển khai thực tế; Base64 trong HTTP Basic không phải mã hóa bảo mật.
- Bearer token hợp lệ cũng không có nghĩa là được phép gọi mọi API: ứng dụng còn phải kiểm tra quyền, scope và phạm vi tài nguyên.

## 3. Phân quyền (Authorization): quyết định được làm gì

Sau khi có danh tính, hệ thống quyết định có cho phép hành động cụ thể hay không dựa trên chính sách và ngữ cảnh. Spring Security hỗ trợ nhiều mức kiểm tra:

1. **Theo HTTP request**: đường dẫn, HTTP method và rule trong `authorizeHttpRequests`, ví dụ request GET công khai, đường dẫn quản trị chỉ ADMIN, phần còn lại yêu cầu login.
2. **Theo phương thức**: `@PreAuthorize`, `@PostAuthorize` hoặc cơ chế method security khi được bật bằng `@EnableMethodSecurity`. Hữu ích khi business service cũng được gọi từ nhiều điểm vào.
3. **Theo đối tượng/tài nguyên**: kiểm tra người đang truy cập có quyền với đúng đơn hàng, hồ sơ hoặc tenant đó hay không. Role “USER” đơn thuần không chứng minh người dùng sở hữu một đơn hàng cụ thể.

### 3.1. Role, authority và phạm vi tài nguyên

`GrantedAuthority` là chuỗi quyền được cấp cho người dùng. Một **role** thường được biểu diễn dưới dạng authority có tiền tố `ROLE_`. Trong cấu hình mặc định:

- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`;
- `hasAuthority("invoice:read")` kiểm tra chính xác chuỗi `invoice:read`;
- `User.withUsername(...).roles("ADMIN")` tạo authority `ROLE_ADMIN`.

Không nên nhầm **role** với mọi loại quyền. Một người có `ROLE_USER` có thể vẫn không được phép sửa dữ liệu của người dùng khác; kiểm tra ownership/tenant thường cần logic nghiệp vụ bổ sung.

Các rule kiểm tra request được xét theo thứ tự khai báo. Vì thế rule cụ thể nên đứng trước rule bao quát:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/articles").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

`permitAll()` nghĩa là endpoint công khai về mặt **quyền truy cập**; nó không có nghĩa là request bỏ qua toàn bộ security filter. Chẳng hạn, một POST công khai vẫn có thể phải tuân thủ CSRF nếu ứng dụng đang bật cơ chế đó. Với hệ thống nhạy cảm, nên thiết kế theo nguyên tắc **ít quyền nhất** và từ chối mặc định những tài nguyên chưa công bố; rule cuối có thể là `denyAll()` nếu policy yêu cầu liệt kê tường minh mọi endpoint được phép.

### 3.2. HTTP 401, 403 và chuyển hướng đăng nhập

- **401 Unauthorized**: thường là request chưa có hoặc có thông tin xác thực không hợp lệ, đặc biệt với HTTP Basic/API.
- **403 Forbidden**: request không đủ quyền truy cập hoặc bị chặn bởi một lớp bảo vệ như CSRF.
- **302 Redirect** tới trang đăng nhập: có thể xuất hiện khi ứng dụng sử dụng form login thay vì trả 401 trực tiếp.

Không kết luận “mọi 403 đều do thiếu role”: CSRF token thiếu/sai cũng thường tạo 403. Ngược lại, không thể dùng riêng mã HTTP để suy ra toàn bộ nguyên nhân; phải xem security configuration và log phù hợp.

## 4. Bảo vệ trước tấn công (Exploit protection): gia cố request, response và phiên

Authentication và authorization là thiết yếu nhưng chưa đủ. Trình duyệt tự đính kèm cookie, mã độc có thể cố ép người dùng gửi request, ứng dụng có thể phản hồi thiếu header phòng vệ, và nhiều lỗ hổng khác có thể tồn tại trong code nghiệp vụ.

### 4.1. CSRF: ví dụ điển hình khi xác thực bằng cookie

**Cross-Site Request Forgery (CSRF)** xảy ra khi một trang độc hại khiến trình duyệt của nạn nhân đang đăng nhập gửi một request làm thay đổi trạng thái đến ứng dụng đích. Trình duyệt có thể tự gửi cookie phiên, nên server chỉ dựa trên cookie sẽ nhầm request đó là chủ ý của nạn nhân.

Ví dụ: nạn nhân đang login tại `bank.example`; trang độc hại dụ trình duyệt gửi POST chuyển tiền. Nếu ứng dụng dùng cookie phiên mà không kiểm tra tính hợp lệ của yêu cầu, login thành công và rule “người dùng đã đăng nhập được chuyển tiền” không đủ để ngăn việc giả mạo.

Spring Security mặc định bật **CSRF protection** trong cấu hình Servlet. Với các HTTP method không an toàn như POST/PUT/PATCH/DELETE, request phải cung cấp CSRF token hợp lệ theo cơ chế đang dùng. GET/HEAD/OPTIONS/TRACE thông thường không bị yêu cầu CSRF token; vì vậy ứng dụng phải tuân thủ nguyên tắc **GET không thay đổi trạng thái**.

Cần phân biệt:

- **Cookie/session login**: CSRF là một mối đe dọa quan trọng, vì trình duyệt có thể tự gửi thông tin xác thực.
- **API thực sự stateless**, chỉ chấp nhận bearer token từ header `Authorization` do client kiểm soát và không dùng thông tin xác thực tự đính kèm từ trình duyệt: có thể đánh giá việc không áp dụng CSRF cho các endpoint đó. Quyết định này phải dựa trên cách client thực sự xác thực, không dựa vào chữ “REST”.
- **CORS** quyết định JavaScript trên origin khác được đọc/gọi tài nguyên xuyên origin theo chính sách trình duyệt. CORS không phải kiểm tra danh tính, không thay thế authorization và không tự giải quyết CSRF.

Không tắt CSRF trên toàn ứng dụng chỉ để các lệnh POST thử nghiệm hết trả 403. Hãy xác định cơ chế xác thực, cách cấp CSRF token và các endpoint cần bảo vệ trước.

### 4.2. Security headers và bảo vệ phiên

Spring Security có thể bổ sung các HTTP response header tăng cường bảo vệ trình duyệt, chẳng hạn:

- `X-Content-Type-Options: nosniff`: giảm việc trình duyệt suy diễn MIME type không mong muốn;
- `Strict-Transport-Security` (HSTS) khi phục vụ qua HTTPS và cấu hình phù hợp: khuyến khích trình duyệt chỉ sử dụng HTTPS trong các lần truy cập tiếp theo;
- các chỉ thị cache và những header bảo mật khác tùy cấu hình/phiên bản.

Tùy yêu cầu, ứng dụng còn cần chính sách **Content Security Policy**, thiết lập cookie `Secure` / `HttpOnly` / `SameSite` phù hợp, HTTPS và cơ chế quản lý phiên an toàn. Không nên mặc định mọi header phòng vệ đều tự động được bật với giá trị phù hợp cho mọi hệ thống.

Spring Security cũng có các cơ chế hỗ trợ quản lý session, xử lý logout và phòng chống một số rủi ro liên quan phiên. Tuy nhiên, nó **không tự thay thế** việc validate input, encode output chống XSS, dùng truy vấn tham số chống SQL injection, kiểm soát rate limit, quản lý secret hay kiểm tra phân quyền trên đối tượng nghiệp vụ.

## 5. Ví dụ chạy được trong ứng dụng Spring Boot 3 / Java 17+

Ví dụ minh họa cả ba nhóm chức năng trong một ứng dụng **Spring MVC (Servlet)**: public endpoint, endpoint cần xác thực, endpoint cần role ADMIN và POST chịu CSRF. Cần một dự án Spring Boot 3 dùng Java 17 trở lên, đã cấu hình Spring Boot Gradle plugin, có ít nhất hai dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo `src/main/java/example/securitydemo/SecurityDemoApplication.java`:

```java
package example.securitydemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class DemoController {
    @GetMapping("/public/articles")
    Map<String, String> publicArticles() {
        return Map.of("message", "public");
    }

    @GetMapping("/account")
    Map<String, String> account(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/admin/health")
    Map<String, String> adminHealth() {
        return Map.of("status", "ok");
    }

    @PostMapping("/account/settings")
    Map<String, String> updateSettings(Principal principal) {
        return Map.of("updatedBy", principal.getName());
    }
}
```

Tạo `src/main/java/example/securitydemo/SecurityConfig.java`:

```java
package example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/articles").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails member = User.withUsername("member")
            .password(encoder.encode("demo-member-secret"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-secret"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(member, admin);
    }
}
```

Giải thích cấu hình:

1. `SecurityFilterChain` khai báo chính sách bảo mật dành cho request trong ứng dụng.
2. `GET /api/public/articles` được `permitAll()`; `/api/admin/**` yêu cầu `ROLE_ADMIN`; các request còn lại yêu cầu xác thực.
3. `httpBasic()` bật xác thực HTTP Basic, nên thử nhanh qua `curl -u`; `InMemoryUserDetailsManager` cung cấp hai user demo; mật khẩu được băm bằng BCrypt.
4. `csrf(Customizer.withDefaults())` giữ cơ chế chống CSRF mặc định, không vô hiệu hóa cho POST.
5. `@EnableMethodSecurity` cho phép bổ sung rule ở service bằng `@PreAuthorize` khi ứng dụng cần phân quyền theo phương thức. Ví dụ này chưa dùng annotation đó cho controller.

Hai tài khoản và mật khẩu trên **chỉ dùng để học trên máy cục bộ**. Ứng dụng thực tế phải dùng kho danh tính/secret được quản lý thích hợp, hạn chế thông tin đăng nhập và chỉ truyền HTTP Basic qua TLS.

Chạy trong dự án Boot đã cấu hình:

```bash
./gradlew bootRun
```

Trên Windows có thể dùng `gradlew.bat bootRun`. Kiểm tra các hành vi sau với server đang chạy tại `localhost:8080`:

```bash
# Public GET: 200, body {"message":"public"}
curl -i http://localhost:8080/api/public/articles

# Chưa có thông tin xác thực: 401 (HTTP Basic challenge)
curl -i http://localhost:8080/api/account

# member đã được xác thực: 200, body {"user":"member"}
curl -i -u member:demo-member-secret http://localhost:8080/api/account

# member không có ROLE_ADMIN: 403
curl -i -u member:demo-member-secret http://localhost:8080/api/admin/health

# admin có ROLE_ADMIN: 200, body {"status":"ok"}
curl -i -u admin:demo-admin-secret http://localhost:8080/api/admin/health

# POST chưa có CSRF token: 403, dù đã gửi đúng Basic credentials
curl -i -X POST -u member:demo-member-secret http://localhost:8080/api/account/settings
```

Phần body JSON trên là kết quả dự kiến từ các controller; status có thể khác khi thay đổi cấu hình bảo mật, thêm middleware hoặc cấu hình xác thực khác. Với endpoint POST, để cho phép request hợp lệ trong mô hình dùng CSRF, client phải nhận và gửi token CSRF đúng quy tắc của `CsrfTokenRepository`/`CsrfTokenRequestHandler` đang sử dụng. Không cần bỏ lớp CSRF chỉ để chứng minh xác thực hoặc phân quyền hoạt động.

### 5.1. Thêm kiểm tra quyền trong nghiệp vụ

URL rule chỉ là một lớp bảo vệ. Giả sử người dùng gọi `GET /api/orders/123` và đã có `ROLE_USER`, ứng dụng còn phải xác nhận đơn hàng 123 thuộc về người đó (hoặc người đó có quyền được ủy quyền). Kiểm tra này thường nằm ở service, có thể kết hợp `@PreAuthorize` với kiểm tra ownership/tenant.

Ví dụ một quy tắc method security độc lập, **chỉ minh họa annotation**:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(long invoiceId) {
    invoiceService.approveIfAllowed(invoiceId);
}
```

Đoạn trên giả định `invoiceService` đã được định nghĩa và đã kiểm tra quyền trên hóa đơn cụ thể; đây không phải một chương trình độc lập. Quyền `invoice:approve` phải thực sự nằm trong `Authentication.authorities` của chủ thể. Đừng chỉ ẩn nút trên giao diện rồi xem đó là authorization.

## 6. Phân tích request theo ba lớp

| Tình huống | Xác thực | Phân quyền | Bảo vệ tấn công | Kết quả trong ví dụ |
| --- | --- | --- | --- | --- |
| Khách GET `/api/public/articles` | Không bắt buộc | `permitAll()` | Các lớp lọc/header thích hợp vẫn hoạt động | 200 |
| Khách GET `/api/account` | Chưa có credentials | Endpoint cần người dùng đã xác thực | Không liên quan CSRF vì GET | 401 với HTTP Basic |
| `member` GET `/api/account` | Thành công | `authenticated()` chấp nhận | Áp dụng các bảo vệ phù hợp | 200 |
| `member` GET `/api/admin/health` | Thành công | Thiếu `ROLE_ADMIN` | Không liên quan CSRF vì GET | 403 |
| `admin` GET `/api/admin/health` | Thành công | Có `ROLE_ADMIN` | Áp dụng các bảo vệ phù hợp | 200 |
| `member` POST `/api/account/settings` không có CSRF token | Có credentials hợp lệ | Endpoint cần login | **CSRF từ chối request** | 403 |

Bảng giúp phân biệt **“không nhận diện được ai”**, **“nhận diện được nhưng thiếu quyền”** và **“request không vượt qua kiểm tra chống tấn công”**. Các bộ lọc có thể từ chối request trước khi những lớp khác đưa ra quyết định cuối; không phải mọi request đều đi hết ba nhóm chức năng theo đúng một thứ tự tuyến tính.

## 7. Các sai lầm thường gặp và cách tránh

1. **Coi authentication là authorization.** Login thành công không đồng nghĩa có quyền quản trị, truy cập dữ liệu người khác hoặc quyền cho mọi hành động. Cần policy rõ ràng ở request và business service.
2. **Nhầm `hasRole` với `hasAuthority`.** `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` tìm chính xác `ADMIN`. Chọn quy ước nhất quán để không mở hoặc khóa nhầm endpoint.
3. **Khai báo rule quá rộng trước rule cụ thể.** Các matcher được đánh giá theo thứ tự; hãy đặt trường hợp đặc biệt trước `anyRequest()` và kiểm thử cả quyền được phép lẫn bị từ chối.
4. **Tắt CSRF đại trà do POST bị 403.** Phải phân tích client nào tự gửi cookie/credential, request nào làm thay đổi trạng thái và cách cấp token CSRF. Với app dùng session/cookie, giữ CSRF là hướng mặc định an toàn.
5. **Cho rằng CORS hoặc HTTPS thay thế phân quyền.** HTTPS bảo vệ dữ liệu trên đường truyền; CORS là chính sách truy cập xuyên origin của trình duyệt; cả hai không quyết định tài khoản có được sửa dữ liệu không.
6. **Cho rằng Spring Security chặn mọi tấn công.** Cần thêm input validation, output encoding, truy vấn tham số, kiểm soát truy cập dữ liệu, giám sát, rate limiting và cấu hình hạ tầng. Security headers giúp giảm rủi ro nhưng không tự vá lỗi code.
7. **Chỉ kiểm tra happy path.** Tối thiểu phải thử anonymous, tài khoản đúng quyền, tài khoản thiếu quyền, sai credentials, request POST thiếu CSRF token và trường hợp truy cập tài nguyên của người dùng khác.

## 8. Ghi nhớ và tự kiểm tra

- **Authentication = xác minh danh tính** và tạo/ngữ cảnh hóa `Authentication`.
- **Authorization = ra quyết định truy cập** theo rule URL, method và quyền trên tài nguyên.
- **Exploit protection = giảm rủi ro từ cách request/response/phiên có thể bị lợi dụng**, tiêu biểu là CSRF và security headers.
- Đối với API trả HTTP Basic, **401** thường là vấn đề xác thực; **403** có thể do thiếu quyền hoặc CSRF. Với form login, ứng dụng có thể redirect.
- `permitAll()` không có nghĩa tắt hết các filter; một request có thể public về quyền truy cập nhưng vẫn cần tuân thủ những cơ chế bảo vệ khác.

Câu hỏi tự kiểm tra:

1. Một người có `ROLE_USER` đăng nhập thành công rồi gọi `/api/admin/health`. Nhóm chức năng nào giải thích việc trả 403?
2. Vì sao POST có cookie phiên hợp lệ vẫn có thể bị từ chối nếu thiếu CSRF token?
3. Vì sao `hasRole("ADMIN")` khác `hasAuthority("ADMIN")` khi sử dụng tiền tố role mặc định?
4. Nếu hai người đều có `ROLE_USER`, điều gì đảm bảo người A không xem được đơn hàng của B?
5. Vì sao không thể chỉ dùng CORS, HTTPS hoặc việc ẩn nút UI để thay thế kiểm tra quyền trên backend?

Đáp án gợi ý: (1) authorization; (2) cookie tự đính kèm chưa chứng minh ý định của người dùng, nên CSRF cần chứng minh request hợp lệ; (3) `hasRole` tự thêm tiền tố `ROLE_` theo quy ước mặc định; (4) kiểm tra ownership/tenant tại tầng nghiệp vụ; (5) những biện pháp đó giải quyết vấn đề khác, không quyết định quyền của chủ thể đối với hành động/tài nguyên.

### Tài liệu tham khảo chính thức

- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Cross-Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
