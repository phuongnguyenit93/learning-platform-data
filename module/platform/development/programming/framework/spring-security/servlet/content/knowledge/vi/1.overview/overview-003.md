# Người dùng, principal, credentials, role và authority: bản đồ thuật ngữ

> **Bối cảnh:** Spring Security trên ứng dụng Servlet, dùng cách gọi và API phổ biến của Spring Security 6 / Spring Boot 3 (Java 17+). Mục tiêu của bài là đọc đúng ý nghĩa từng thuật ngữ khi xem cấu hình bảo mật, xử lý đăng nhập và kiểm tra quyền.

## 1. Năm khái niệm thường bị đánh đồng

| Thuật ngữ | Trả lời câu hỏi | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- | --- |
| **User / người dùng** | Hệ thống biết ai? | Đối tượng nghiệp vụ đại diện cho người dùng trong cơ sở dữ liệu; có thể tồn tại dù chưa đăng nhập. Không bắt buộc là class bảo mật của Spring. | Bản ghi `id=42, username=lan, email=...` |
| **Principal** | Danh tính nào đang được trình bày/xác nhận? | Danh tính gắn với một `Authentication`. Kiểu dữ liệu tùy cơ chế xác thực: chuỗi username, `UserDetails`, `Jwt`, `OAuth2User` hoặc kiểu tự định nghĩa. | `UserDetails` của `lan` sau khi đăng nhập |
| **Credentials** | Dùng bằng chứng gì để chứng minh danh tính? | Bí mật hoặc vật mang bằng chứng đưa vào quá trình xác thực: mật khẩu, Bearer token, v.v. Không phải quyền truy cập. | Mật khẩu nhập khi đăng nhập, access token gửi kèm request |
| **Role** | Người này thuộc nhóm quyền nào? | Tên nhóm quyền ở mức khái quát, thường dùng `ADMIN`, `USER`. Theo quy ước mặc định của Spring Security, role `ADMIN` thường được biểu diễn thành authority `ROLE_ADMIN`. | `ADMIN`, `SUPPORT` |
| **Authority** | Người này được cho phép làm gì? | Một quyền/nhãn cụ thể, được biểu diễn qua `GrantedAuthority#getAuthority()`. Có thể là role đã gắn tiền tố hoặc quyền nghiệp vụ chi tiết. | `ROLE_ADMIN`, `orders:read`, `reports:export` |

Hai đối tượng bổ trợ cần nhớ:

- **`Authentication`** là đối tượng Spring Security mô tả một yêu cầu xác thực hoặc kết quả xác thực: chứa `principal`, `credentials`, danh sách `authorities` và trạng thái `isAuthenticated()`. Nó không đồng nghĩa với đối tượng người dùng nghiệp vụ.
- **`SecurityContext`** là nơi giữ `Authentication` hiện hành; trong luồng Servlet thông thường, mã ứng dụng lấy qua `SecurityContextHolder`. Context gắn với thời điểm xử lý request, không phải một biến global đại diện cho mọi người dùng.

Cách nhớ ngắn: **user** là thực thể nghiệp vụ; **principal** là danh tính được hệ thống bảo mật nhìn thấy; **credentials** chứng minh danh tính; **role** gom quyền; **authority** là thông tin thực tế được luật phân quyền đối chiếu.

## 2. Trước và sau khi xác thực: các trường thay đổi thế nào?

Ví dụ với đăng nhập username/password:

1. Client gửi username `lan` và password qua cơ chế đăng nhập/HTTP Basic trên kết nối HTTPS.
2. Một filter của Spring Security tạo hoặc chuyển tiếp đối tượng `Authentication` *chưa được xác thực*. Lúc này `principal` có thể chỉ là chuỗi `"lan"`, `credentials` là mật khẩu vừa nhận và `isAuthenticated() == false`.
3. `AuthenticationManager` chuyển yêu cầu tới `AuthenticationProvider` phù hợp. Với tài khoản lưu trong hệ thống, `DaoAuthenticationProvider` thường sử dụng `UserDetailsService` để tải thông tin đăng nhập và `PasswordEncoder.matches(rawPassword, storedPasswordHash)` để đối chiếu mật khẩu.
4. Khi hợp lệ, kết quả `Authentication` đã xác thực mang danh tính (ví dụ một `UserDetails`) và các `GrantedAuthority` đã được cấp. Provider/manager thường xóa credentials nhạy cảm khi phù hợp; **không giả định `getCredentials()` luôn còn mật khẩu hoặc luôn là `null` với mọi cơ chế**.
5. `Authentication` được đặt vào `SecurityContext`; các bước authorization tiếp theo đọc danh tính và authorities để quyết định cho phép hay từ chối request.

Sơ đồ quan hệ:

```text
HTTP request + credentials
         |
         v
Security Filter Chain
         |
         v
Authentication (chưa xác thực: principal/credentials)
         |
         v
AuthenticationManager -> AuthenticationProvider
                            |-> UserDetailsService (nếu dùng tài khoản nội bộ)
                            |-> PasswordEncoder (nếu dùng mật khẩu)
         |
         v
Authentication (đã xác thực: principal + authorities)
         |
         v
SecurityContextHolder -> SecurityContext -> Authentication
         |
         v
Authorization (hasRole / hasAuthority / quy tắc khác)
         |
         v
Controller hoặc HTTP 401/403
```

**Authentication** trả lời “bạn là ai, đã được kiểm chứng ra sao?”; **authorization** trả lời “với danh tính/quyền hiện có, bạn được thực hiện hành động này không?”. Xác thực thành công không có nghĩa mọi endpoint đều được truy cập.

Trong Servlet, Spring Security quản lý vòng đời context qua security filter chain. Context có thể được tải/lưu qua `SecurityContextRepository` (chẳng hạn tích hợp HTTP session), hoặc hệ thống có thể xác thực token trên từng request. Đừng mặc định đăng nhập một lần là mọi request sau đó có cùng context nếu chưa hiểu cơ chế session/token. Với code tự gắn `Authentication` thủ công, việc lưu context để dùng ở request sau cũng cần được xử lý đúng theo cấu hình; chỉ gán `SecurityContextHolder` chưa bảo đảm lưu phiên.

## 3. User nghiệp vụ, UserDetails và principal: ba lớp khác nhau

Một ứng dụng có thể có bảng `users` với `id`, `username`, `email`, `status`, `created_at`, cùng bảng nhóm/quyền. Đó là **mô hình domain**: phục vụ logic nghiệp vụ, quan hệ dữ liệu, hồ sơ người dùng.

Khi xác thực username/password, Spring Security thường cần `UserDetailsService#loadUserByUsername(...)` trả về `UserDetails`, cung cấp username, password đã mã hóa, trạng thái tài khoản và authorities. `org.springframework.security.core.userdetails.User` là một implementation có sẵn của `UserDetails`; **không mặc định là entity `User` của ứng dụng**. Có thể viết custom `UserDetails` hoặc chuyển dữ liệu từ domain entity sang đối tượng bảo mật.

Sau khi xác thực, `Authentication#getPrincipal()` có thể chính là `UserDetails`, nhưng điều này phụ thuộc provider. Với JWT resource server, principal thường là `Jwt` hoặc dạng đã được converter tạo; với OAuth2 login có thể là `OAuth2User`. Vì thế:

- `authentication.getName()` thích hợp khi chỉ cần tên định danh theo cơ chế hiện tại.
- `authentication.getPrincipal()` trả về object danh tính; chỉ ép kiểu `UserDetails` khi biết chắc provider đang dùng kiểu này.
- `@AuthenticationPrincipal` trong controller lấy phần `principal` từ `Authentication`; kiểu tham số phải phù hợp với thực tế.
- `HttpServletRequest#getUserPrincipal()` nói về Java `Principal` ở request; đối tượng trả về trong tích hợp Spring Security có thể là `Authentication`. Đừng nhầm object này với kết quả của `Authentication#getPrincipal()`.

Một domain user bị khóa vẫn là bản ghi người dùng tồn tại. Việc họ được xác thực hay không tùy kiểm tra account status và provider; việc họ có vào được chức năng hay không còn tùy authorization. Không nên đồng nhất ba trạng thái đó.

## 4. Role là một dạng authority theo quy ước

Trong Spring Security, `GrantedAuthority` thường cung cấp một chuỗi qua `getAuthority()`. Quy tắc `hasAuthority("X")` đối chiếu **chính xác** authority `X` (theo chính sách kiểm tra đang dùng). Quy tắc `hasRole("ADMIN")` theo cấu hình mặc định tìm authority `ROLE_ADMIN`.

| Authorities trên `Authentication` | Kiểm tra | Kết quả mặc định | Lý do |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép | Spring bổ sung tiền tố `ROLE_` khi kiểm tra role |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Cho phép | So khớp chuỗi authority |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | Từ chối | `ADMIN` khác `ROLE_ADMIN` |
| `orders:read` | `hasAuthority("orders:read")` | Cho phép | Quyền nghiệp vụ khớp chính xác |
| `ROLE_USER` | `hasRole("ADMIN")` | Từ chối | Không có `ROLE_ADMIN` |
| `ROLE_ADMIN` | `hasAuthority("orders:read")` | Từ chối | Role ADMIN không tự sinh quyền `orders:read` |

Các kết quả trên giả định không có `RoleHierarchy`, policy tùy chỉnh hay cấu hình thay đổi tiền tố. `ROLE_` là **quy ước biểu diễn trong Spring Security**, không phải quy tắc bắt buộc của bảng roles ở database. Nếu bật role hierarchy, một authority cấp cao có thể kéo theo quyền theo cấu hình; không có chuyện mọi role ADMIN tự động sở hữu tất cả authority chi tiết.

**Lưu ý khi tạo `UserDetails`:**

- `User.withUsername("lan").password(...).roles("ADMIN").build()` tạo authority `ROLE_ADMIN`.
- `User.withUsername("lan").password(...).authorities("ROLE_ADMIN", "orders:read").build()` đặt trực tiếp hai authority, phù hợp khi cần cả role lẫn quyền chi tiết.
- Trên cùng một `UserBuilder`, gọi lần lượt `.roles(...)` rồi `.authorities(...)` không phải thao tác cộng dồn an toàn; phương thức sau có thể thay thế danh sách trước. Hãy truyền danh sách authority cuối cùng rõ ràng hoặc chủ động kết hợp collections.
- Khi dùng `hasRole("ADMIN")`, truyền `ADMIN` (không thêm sẵn `ROLE_` trong đối số). Khi dùng `hasAuthority(...)`, truyền chuỗi chính xác đã cấp.

Tên quyền như `orders:read` là **quy ước của ứng dụng**, không phải permission mặc định Spring Security tự nhận diện. Cần có bước nạp/chuyển authorities từ database, token claim hoặc nguồn nhận dạng tương ứng.

## 5. Ví dụ Servlet chạy với Spring Boot 3 và Java 17+

Ví dụ dùng HTTP Basic để dễ nhìn ranh giới principal/credentials/quyền. Chuẩn bị một **dự án Spring Boot 3.x** có Java 17+ và hai dependency `spring-boot-starter-web`, `spring-boot-starter-security`. Đặt ba file dưới `src/main/java/demo/security/`. Các đoạn sau là các class hoàn chỉnh trong một dự án đã có Spring Boot build configuration; không thể biên dịch bằng `javac` trần khi thiếu Spring dependencies.

**File `SecurityDemoApplication.java`:**

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

**File `SecurityConfig.java`:**

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/orders").hasAuthority("orders:read")
                .anyRequest().authenticated()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN", "orders:read")
                .build();

        UserDetails minh = User.withUsername("minh")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(lan, minh);
    }
}
```

**File `DemoController.java`:**

```java
package demo.security;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "admin report";
    }

    @GetMapping("/orders")
    public String orders() {
        return "orders";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "principalType",
                    authentication.getPrincipal().getClass().getSimpleName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList()
        );
    }
}
```

Chạy bằng `./gradlew bootRun` (hoặc lệnh chạy của dự án Spring Boot đã cấu hình). Các lệnh kiểm tra sau dành cho shell có `curl` và ứng dụng đang chạy trên cổng mặc định `8080`:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
# 200

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u lan:demo123 http://localhost:8080/me
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u lan:demo123 http://localhost:8080/admin/report
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u minh:demo123 http://localhost:8080/admin/report
# 403

curl -s -o /dev/null -w '%{http_code}\n' -u lan:demo123 http://localhost:8080/orders
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u minh:demo123 http://localhost:8080/orders
# 403
```

Dùng `curl -u lan:demo123 http://localhost:8080/me` để xem thông tin đã xác thực. Với cấu hình mẫu, `name` là `lan`, `principalType` là `User` (implementation của Spring Security), còn `authorities` chứa `ROLE_ADMIN` và `orders:read`. Thứ tự khóa JSON không phải hợp đồng; danh sách authorities được sắp xếp trong code mẫu.

Giải thích:

- `lan` có **hai authority**: `ROLE_ADMIN` và `orders:read`; `minh` chỉ có `ROLE_USER`.
- Spring tạo/kích hoạt đối tượng `Authentication` sau khi HTTP Basic kiểm chứng username/password; controller `/me` nhận thông tin của request đã đăng nhập.
- `/admin/report` được kiểm bằng role (authority `ROLE_ADMIN`); `/orders` được kiểm bằng quyền nghiệp vụ `orders:read`.
- `/public` cho phép truy cập không cần đăng nhập; các URL khác đi qua `authenticated()`.
- Giá trị `demo123` và tài khoản trong bộ nhớ **chỉ dùng minh họa**. Ứng dụng thật lấy thông tin định danh từ nguồn tin cậy, giữ mật khẩu dưới dạng hash an toàn và quản lý secrets theo quy trình riêng. Không trả về/log `credentials` trong endpoint `/me`.
- Ví dụ chỉ dùng GET; với các thao tác thay đổi trạng thái qua browser, CSRF vẫn là một lớp kiểm tra độc lập. Không suy ra mọi lỗi 403 đều do thiếu role.

## 6. Đọc người dùng hiện tại từ mã ứng dụng

Trong một controller Servlet đã được bảo vệ, nhận trực tiếp `Authentication` là cách đơn giản để truy cập danh tính và quyền của request (như `/me` ở trên). Ở tầng xử lý khác, có thể đọc `SecurityContextHolder.getContext().getAuthentication()`, nhưng phải xét khả năng chưa có xác thực hoặc đang là anonymous.

```java
// Minh họa bên trong một method đang chạy trong security filter chain.
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String displayIdentity = authentication.getName();
    // Kiểm tra tiếp anonymous/trust level nếu nghiệp vụ yêu cầu đăng nhập thật.
}
```

Các import tương ứng là `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. Đoạn trên là **fragment minh họa**, không phải một class Java chạy độc lập.

Một `AnonymousAuthenticationToken` có thể tồn tại trong context cho khách chưa đăng nhập và **`isAuthenticated()` của chính token đó có thể là `true`**. Vì vậy đừng lấy `authentication != null && authentication.isAuthenticated()` làm tiêu chuẩn tuyệt đối rằng một người đã đăng nhập thật. Trong cấu hình authorization, hãy dùng `.authenticated()`, `.anonymous()`, hoặc trust resolver/quy tắc tương ứng mà Spring Security cung cấp.

Ở mặc định Servlet, `SecurityContextHolder` sử dụng ngữ cảnh gắn với thread đang xử lý. Khi tự tạo thread/async task, đừng cho rằng security context tự động được truyền sang thread mới; dùng cơ chế truyền context được Spring hỗ trợ khi có nhu cầu. Đừng lưu `Authentication` của một request vào biến static để tái sử dụng cho request khác.

## 7. Phân quyền URL và phân quyền method

Quy tắc URL của ví dụ nằm trong `SecurityFilterChain` và áp dụng trước khi controller chạy. Đặt matcher cụ thể trước `anyRequest()` để tránh quy tắc tổng quát che mất quy tắc chi tiết.

Nếu một nghiệp vụ được gọi từ nhiều đường đi (HTTP, job, service khác), có thể bảo vệ thêm ở tầng method bằng method security. Phải bật method security trước khi dùng `@PreAuthorize`:

```java
// Fragment cấu hình bổ sung vào một class @Configuration:
@EnableMethodSecurity

// Fragment trên method của một Spring-managed bean:
@PreAuthorize("hasAuthority('orders:read')")
public OrderSummary viewOrders() {
    // xử lý nghiệp vụ
}
```

Đây là **hai fragment vị trí khác nhau**, không phải một file Java đầy đủ; `OrderSummary` chỉ là tên kiểu nghiệp vụ minh họa. Các annotation tương ứng là `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity` và `org.springframework.security.access.prepost.PreAuthorize`. Method security thường dựa trên Spring AOP/proxy; lời gọi nội bộ trực tiếp trong cùng bean có thể không đi qua proxy. Cần kiểm thử ở đường gọi thật.

## 8. Tránh nhầm authorization với các khái niệm lân cận

- **Danh tính không tương đương quyền:** biết `authentication.getName() == "lan"` không cho phép suy luận người đó có role ADMIN. Quyền phải lấy từ authority hoặc chính sách được kiểm chứng.
- **Mật khẩu hash không phải authority:** hash trong `UserDetails#getPassword()` là dữ liệu phục vụ kiểm chứng mật khẩu, không cho biết tài khoản được phép làm gì. Với mật khẩu, so khớp bằng `PasswordEncoder.matches(raw, encoded)`, không so sánh chuỗi thô.
- **Role không tự chứa permission:** `ROLE_ADMIN` không tự làm đúng `hasAuthority("orders:read")`; việc liên kết phải do hệ thống cấp quyền/hierarchy/policy định nghĩa.
- **Không phải mọi principal đều là `UserDetails`:** đổi sang JWT/OAuth2 có thể đổi kiểu principal; ép kiểu không kiểm tra sẽ dẫn tới `ClassCastException`.
- **Authority của token không tự sinh theo ý ứng dụng:** claim `scope`, `roles`, `permissions` phải được chuyển sang `GrantedAuthority` đúng theo converter. Ví dụ resource server JWT mặc định thường chuyển scope thành dạng `SCOPE_...`; đó không phải `ROLE_...` nếu chưa cấu hình mapping.
- **HTTP 401 khác 403:** 401 thường là request thiếu xác thực hợp lệ và cần đăng nhập/chứng minh danh tính; 403 là request đã có danh tính nhưng bị từ chối theo chính sách. Một số filter (như CSRF) cũng có thể tạo 403; hãy xem filter chain và log có kiểm soát trước khi kết luận.
- **Dữ liệu phân quyền cần có nguồn đáng tin:** không lấy `role=ADMIN` từ query param/request body rồi biến thẳng thành `GrantedAuthority`. Quyền phải đến từ nguồn đã xác thực và cơ chế cấp quyền của hệ thống.
- **Không lộ credentials:** dùng HTTPS, mã hóa password bằng encoder phù hợp, tránh in token/password vào logs, metrics, URL hoặc JSON trả về; cân nhắc vòng đời/revocation của token và session.
- **Kiểm thử cả đường từ chối:** kiểm tra quyền admin với user thường, endpoint cần auth với anonymous, quyền chi tiết với người chỉ có role, và các trường hợp tài khoản bị khóa.

## 9. Bài tập tự kiểm tra

1. Một `Authentication` có `ROLE_USER` và `orders:read`. `hasRole("USER")`, `hasAuthority("orders:read")`, `hasRole("ADMIN")` lần lượt thế nào? **Đáp án:** cho phép, cho phép, từ chối (theo cấu hình mặc định).
2. `Authentication#getPrincipal()` trả về `Jwt` thay vì `UserDetails`. Có sai không? **Không.** Principal phụ thuộc cách xác thực; code đọc danh tính phải xử lý kiểu phù hợp.
3. Vì sao `ROLE_ADMIN` có thể qua `hasRole("ADMIN")` nhưng không qua `hasAuthority("orders:read")`? **Vì** hai rule kiểm tra các authority khác nhau, trừ khi bạn cấu hình thêm chính sách/hierarchy phù hợp.
4. Người dùng gửi đúng password nhưng vào `/admin/report` nhận 403. Bước kiểm tra đầu tiên? **Xem authorities thực tế của `Authentication` và matcher/policy**; đừng kết luận sai mật khẩu chỉ từ 403.
5. `isAuthenticated() == true` có chắc là phiên đăng nhập của người thật? **Không.** Anonymous token có thể có cờ đó; dùng cách phân biệt anonymous theo cơ chế Spring Security.

## 10. Bản đồ ghi nhớ khi đọc code

```text
Domain User (bản ghi nghiệp vụ)
   | ánh xạ/tải thông tin đăng nhập
   v
UserDetails (một dạng dữ liệu cho provider; không phải principal duy nhất)
   | kết hợp với credentials do client trình bày
   v
AuthenticationManager/Provider -> Authentication
                                  | principal: ai
                                  | credentials: bằng chứng (xử lý an toàn)
                                  | authorities: các quyền thực có
                                  v
                        SecurityContext (request hiện hành)
                                  |
                         hasRole / hasAuthority
                                  |
                            ALLOW hoặc DENY
```

Khi gặp một lỗi “đăng nhập được nhưng không truy cập được”, hãy đi theo thứ tự: **kiểm tra danh tính `principal` → danh sách `authorities` thực tế → quy tắc `hasRole/hasAuthority` → đường đi filter/method security**. Trình tự này giúp phân biệt lỗi xác thực, lỗi ánh xạ quyền và lỗi chính sách phân quyền trong ứng dụng Spring Security Servlet.