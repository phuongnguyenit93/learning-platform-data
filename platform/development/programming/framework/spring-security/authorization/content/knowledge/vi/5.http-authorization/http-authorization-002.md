# permitAll, denyAll và authenticated trong quy tắc truy cập HTTP

> **Module:** Spring Security – authorization  
> **Nhóm:** Phân quyền HTTP  
> **Phạm vi:** Ba quy tắc `permitAll()`, `denyAll()`, `authenticated()` trong `authorizeHttpRequests` trên Servlet stack, thứ tự match URL, tác động đến người dùng anonymous/remember-me, và cách cấu hình, kiểm thử, gỡ lỗi một cách an toàn.

## 1. Bắt đầu từ một API thật

Giả sử một hệ thống hóa đơn có các đường dẫn:

| HTTP request | Mong muốn nghiệp vụ |
|---|---|
| `GET /public/catalog` | Ai cũng được xem, kể cả chưa đăng nhập |
| `GET /account/profile` | Chỉ người dùng đã đăng nhập được xem hồ sơ |
| `GET /api/invoices/101` | Phải đăng nhập **và** có quyền đọc hóa đơn |
| `POST /api/invoices/101/approve` | Phải có quyền duyệt và đủ điều kiện nghiệp vụ |
| `GET /internal/debug` | Không cho truy cập qua web, kể cả tài khoản admin |
| Một URL không được khai báo | Mặc định từ chối để tránh bỏ sót endpoint mới |

Ba quy tắc của Spring Security giải quyết **ba yêu cầu khác nhau**:

- **`permitAll()`**: không yêu cầu quyền từ cơ chế *HTTP authorization rule* cho request khớp.
- **`authenticated()`**: yêu cầu một chủ thể được framework nhận diện là **đã xác thực, không phải anonymous**; chưa kiểm tra role hoặc permission cụ thể.
- **`denyAll()`**: từ chối mọi chủ thể theo *HTTP authorization rule*, ngay cả người có authority quản trị.

Cả ba được cấu hình trong `authorizeHttpRequests`. Chúng không tự thay thế CSRF protection, authentication filter, method security hoặc kiểm tra quyền trên từng bản ghi. Cũng không có quy tắc nào mặc nhiên bảo đảm một endpoint tồn tại hay trả HTTP 200.

Mục tiêu của bài: có thể nhìn vào một `SecurityFilterChain` và trả lời chính xác **request nào đi qua, vì sao, có những lớp bảo vệ nào vẫn hoạt động, và phải test ra sao**.

## 2. Phân biệt xác thực, phân quyền và chính sách HTTP

Trong Servlet Spring Security, có thể hình dung:

~~~text
HTTP request
    |
    v
SecurityFilterChain được chọn
    |
    +-- Các filter xử lý bảo vệ, CSRF, authentication, ...
    |
    +-- AuthorizationFilter
           |
           +-- So khớp URL/method/dispatcher theo quy tắc đã khai báo
           |
           +-- Lấy AuthorizationManager của rule khớp đầu tiên
           |
           +-- Quyết định grant / deny
    |
    v
Controller / Service / Method Security / Database
~~~

**Authentication** xác minh chủ thể và tạo `Authentication` chứa principal, authorities. **HTTP authorization** trả lời liệu request với URL, method, và chủ thể hiện hành có được tiếp tục qua `AuthorizationFilter` hay không.

Đây **không phải toàn bộ security policy**:

- Qua `authenticated()` chỉ chứng minh điều kiện *đã đăng nhập* theo trust resolver; không chứng minh có quyền `invoice:read`.
- Qua `hasRole("ADMIN")` chỉ chứng minh role ở mức chức năng; không tự chứng minh được đọc hóa đơn của tenant khác.
- Qua `permitAll()` chỉ có nghĩa **rule HTTP này không từ chối**; controller/service vẫn có thể áp dụng `@PreAuthorize`, validation và logic nghiệp vụ khác.
- Bị `denyAll()` có nghĩa request đó không thể đi tiếp qua rule HTTP, nhưng phản hồi cụ thể 401, 403 hay redirect tùy trạng thái authentication và error handler.

Spring Security không bắt buộc phải nạp Authentication cho **mọi** rule: một số quyết định không cần danh tính. Điều này giải thích hiệu năng và tác dụng của `permitAll`/`denyAll` ở các phần sau.

## 3. `permitAll()`: cho phép ở lớp HTTP authorization

Cấu hình:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated()
);
~~~

Ý nghĩa: các request khớp `/public/**` không cần có role, authority hoặc login **để vượt qua rule của `AuthorizationFilter`**. Người không đăng nhập, người đã đăng nhập hay người có role khác đều thỏa điều kiện này.

### 3.1. `permitAll` không đồng nghĩa “bỏ qua toàn bộ bảo mật”

Bởi request vẫn đi vào `SecurityFilterChain` đã được chọn, các phần phù hợp khác vẫn có thể chạy:

- Xử lý CORS và CSRF nếu được cấu hình;
- Các authentication filter và kiểm tra token nếu request mang credentials;
- Các header bảo mật của Spring Security;
- Filter chống khai thác và filter tùy chỉnh;
- Method security và kiểm tra ở tầng controller/service.

Ví dụ một `POST /public/feedback` có rule `permitAll()` **vẫn có thể bị từ chối vì thiếu CSRF token** trong ứng dụng dùng session/cookie, nếu CSRF protection đang bật và áp dụng cho endpoint đó. `permitAll` **không phải cách tắt CSRF**.

Tương tự, một request tới URL public nhưng đính kèm Bearer token sai định dạng hoặc không hợp lệ có thể bị authentication filter từ chối trước khi rule `permitAll` được đánh giá. Đừng suy ra `permitAll` bảo đảm mọi request nhận `200 OK`.

### 3.2. Vì sao nên dùng `permitAll` cho tài nguyên public?

Một lựa chọn khác là cấu hình Spring Security **bỏ qua hoàn toàn** URL (ví dụ `web.ignoring()`). Khi đó các filter bảo mật do Spring Security quản lý cho URL bị ignore có thể không chạy, kể cả logic thêm security headers. Tài liệu chính thức khuyến nghị ưu tiên `permitAll` hơn `ignoring` cho đa số tài nguyên tĩnh/public, để tiếp tục hưởng cơ chế bảo vệ của security chain.

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                "/css/**",
                "/js/**",
                "/images/**",
                "/login",
                "/about"
        ).permitAll()
        .anyRequest().authenticated()
);
~~~

Ở đây tài nguyên public vẫn nằm trong hệ thống bảo vệ; chỉ **ràng buộc đăng nhập ở HTTP authorization** được bỏ qua.

### 3.3. Đừng đặt quy tắc public quá rộng

Cấu hình sau nguy hiểm nếu ứng dụng vô tình để lộ dữ liệu dưới `/api/**`:

~~~java
// CẢNH BÁO: minh họa rule quá rộng.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
);
~~~

Rule `/api/**` đã khớp trước nên rule admin **không được xét đến**. Không nên tạo “ngoại lệ public” bằng một prefix bao trùm nhiều endpoint nhạy cảm.

Cách sửa là chỉ cho phép các URL public **cụ thể**, và bảo vệ endpoint nhạy cảm trước các matcher rộng:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
);
~~~

## 4. `denyAll()`: từ chối vô điều kiện tại HTTP rule

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/internal/**").denyAll()
        .anyRequest().authenticated()
);
~~~

Bất kỳ request nào khớp `/internal/**` sẽ bị từ chối tại quy tắc HTTP, kể cả nếu `Authentication` chứa `ROLE_ADMIN`.

Các trường hợp hữu ích:

1. **Cấm đường dẫn nội bộ** không được công khai qua ứng dụng web.
2. **Chặn endpoint đã ngừng dùng** nhưng vẫn còn route trong source.
3. **Chặn các đường dẫn đang được xử lý chuyển đổi** để giảm bề mặt truy cập.
4. **Fail closed**: với `anyRequest().denyAll()`, mọi URL không được khai báo sẽ mặc định bị chặn.

Ví dụ nguyên tắc allowlist:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
);
~~~

Trong đoạn này, các URL ngoài `/public/**` và `/api/**` đều bị từ chối; tuy nhiên `/api/**` chỉ yêu cầu đăng nhập nên **chưa đủ an toàn** nếu chứa API cần permission riêng. `denyAll` ở cuối hạn chế nguy cơ quên khai báo route ngoài tập đã biết, chứ không sửa được một matcher quá rộng đặt trước đó.

### 4.1. `denyAll()` không phải “chỉ admin được vào”

Đây là hai quy tắc đối lập:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
// ADMIN được phép nếu không có quy tắc/lớp bảo vệ khác từ chối.

.requestMatchers("/internal/**").denyAll()
// Không ai được phép qua rule này.
~~~

Nếu endpoint thực sự cần cho công việc vận hành, đừng đặt `denyAll` rồi tìm cách “bỏ qua” bằng một header đặc biệt. Nên thiết kế một policy quản trị rõ ràng, authentication mạnh, network policy và audit nếu cần.

### 4.2. “Từ chối” không đồng nghĩa một status code cố định

Với người dùng đã xác thực nhưng bị từ chối, ứng dụng thường trả **403 Forbidden**. Với người chưa đăng nhập, `ExceptionTranslationFilter` có thể kích hoạt `AuthenticationEntryPoint`: HTTP Basic thường trả **401**; form login thường **redirect** đến trang login. Chính sách handler có thể tùy biến.

Vì vậy, **`denyAll` có nghĩa là quyết định truy cập âm tính**, không phải lời hứa rằng mọi caller luôn nhận đúng 403. Trong test, cần xác định cả authentication mechanism và exception-handling configuration.

## 5. `authenticated()`: cần đăng nhập, chưa đủ để xác định chức năng

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/account/**").authenticated()
        .anyRequest().denyAll()
);
~~~

Spring Security cho phép request qua rule này khi chủ thể được nhận diện là **đã xác thực** theo cơ chế trust resolver mà rule sử dụng, **không phải anonymous**. Mặc định:

- Người dùng đăng nhập đầy đủ: **được phép**;
- Người dùng được nhận diện qua remember-me: **thường được phép**;
- Người dùng anonymous/chưa đăng nhập: **không được phép**.

**Điểm rất dễ nhầm:** `AnonymousAuthenticationToken.isAuthenticated()` có thể trả `true`. Nhưng `authenticated()` trong Spring Security không đơn giản là bạn tự gọi `authentication != null && authentication.isAuthenticated()`; framework có logic phân biệt anonymous. Không được suy ra anonymous sẽ vượt `authenticated()` chỉ vì cờ của token là true.

### 5.1. So với `fullyAuthenticated()`, `anonymous()` và `rememberMe()`

Các rule liên quan (khi được API/cấu hình hỗ trợ) có mục tiêu khác nhau:

| Rule | Mục đích |
|---|---|
| `permitAll()` | Không yêu cầu đăng nhập hoặc authority ở rule HTTP |
| `authenticated()` | Người dùng được xác thực, không phải anonymous; **có thể bao gồm remember-me** |
| `fullyAuthenticated()` | Người dùng xác thực đầy đủ, không dựa trên remember-me |
| `rememberMe()` | Kiểm tra trạng thái remember-me theo cách framework diễn giải |
| `anonymous()` | Chỉ những request được coi là anonymous |
| `denyAll()` | Không cho ai đi qua rule HTTP |

Ứng dụng giao dịch nhạy cảm có thể cần `fullyAuthenticated()` hoặc step-up authentication, nhưng đừng nghĩ đây là điều kiện tự động có thêm MFA; chính sách xác thực mạnh/MFA là trách nhiệm riêng.

### 5.2. `authenticated()` không kiểm tra permission

Ví dụ:

~~~java
.requestMatchers("/api/invoices/**").authenticated()
~~~

Điều này cho phép **mọi người dùng đã xác thực** đi qua ở cấp HTTP, kể cả người không có `invoice:read`. Nếu logic nghiệp vụ yêu cầu permission, hãy áp dụng rule phù hợp:

~~~java
.requestMatchers(HttpMethod.GET, "/api/invoices/**")
    .hasAuthority("invoice:read")
.requestMatchers(HttpMethod.POST, "/api/invoices/**")
    .hasAuthority("invoice:write")
~~~

Và kiểm tra **đối tượng cụ thể** ở service/repository: người có quyền đọc hóa đơn nói chung chưa chắc được đọc hóa đơn của user hoặc tenant khác.

**Phân biệt:** `authenticated()` không phải thứ tự “vào phòng ban nào”, cũng không mặc định áp dụng role hierarchy. Nó chỉ là một ngưỡng danh tính cơ bản.

## 6. Bảng quyết định trọng tâm

Xét ba trạng thái đại diện: anonymous, nhớ đăng nhập (remember-me), và đăng nhập đầy đủ. Giả sử không có filter khác ngăn request, không có custom trust resolver hoặc policy bổ sung, và URL đã khớp rule được nói đến.

| Trạng thái chủ thể | `permitAll()` | `authenticated()` | `fullyAuthenticated()` | `denyAll()` |
|---|---|---|---|---|
| Anonymous/chưa login | Cho phép | Từ chối | Từ chối | Từ chối |
| Remember-me | Cho phép | Cho phép | Từ chối | Từ chối |
| Đã login đầy đủ | Cho phép | Cho phép | Cho phép | Từ chối |
| Admin đã login đầy đủ | Cho phép | Cho phép | Cho phép | Từ chối |

**Bảng chỉ mô tả kết quả của quy tắc HTTP được nêu**, không phải kết quả cuối cùng của cả request. Một request `permitAll` vẫn có thể bị CSRF protection chặn, một request `authenticated` vẫn có thể bị method security từ chối, và request tới route không tồn tại vẫn có thể trả 404.

## 7. Cấu hình Servlet SecurityFilterChain hoàn chỉnh về mặt rule

Ví dụ dưới đây dành cho **dự án Spring Boot 3.x + Spring Security 6.x trên Servlet stack** có Spring Web và cơ chế authentication đã được cấu hình. Nó minh họa các rule đầy đủ trong một `SecurityFilterChain`, nhưng **không phải chương trình Java độc lập**: dự án phải cung cấp `UserDetailsService`/authentication provider, controller và các dependency tương ứng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                // 1. Nội dung public: không cần login.
                .requestMatchers(
                        HttpMethod.GET, "/public/**").permitAll()

                // 2. Public POST vẫn có thể cần CSRF token.
                .requestMatchers(
                        HttpMethod.POST, "/public/feedback").permitAll()

                // 3. Hồ sơ: có login là đủ ở tầng HTTP.
                .requestMatchers(
                        HttpMethod.GET, "/account/profile").authenticated()

                // 4. Dữ liệu nghiệp vụ: cần permission cụ thể.
                .requestMatchers(
                        HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("invoice:read")

                .requestMatchers(
                        HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("invoice:write")

                // 5. Chức năng quản trị.
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")

                // 6. Đóng endpoint nội bộ.
                .requestMatchers("/internal/**").denyAll()

                // 7. URL còn lại: từ chối.
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### Phân tích tuần tự

**Request A: `GET /public/catalog` không có credential.** Rule GET `/public/**` khớp → `permitAll`. Request vượt HTTP authorization, sau đó controller quyết định kết quả. Không có nghĩa endpoint nhất định tồn tại.

**Request B: `GET /account/profile` của user Lan có authentication hợp lệ.** Rule profile khớp → `authenticated`. Không cần authority `ROLE_ADMIN`. Nếu user chưa login, entry point xử lý yêu cầu xác thực.

**Request C: `GET /api/invoices/101` với authority `invoice:read`.** Rule GET invoices khớp và authority đáp ứng. Vẫn cần kiểm tra Lan có được đọc hóa đơn 101 cụ thể không.

**Request D: `POST /api/invoices/101` với user chỉ có `invoice:read`.** Rule POST invoices đòi `invoice:write` → từ chối nếu không có permission. Với CSRF bật, request browser có thể bị từ chối sớm hơn nếu thiếu token.

**Request E: `GET /api/admin/users` với user có `ROLE_ADMIN`.** Rule `/api/admin/**` đòi role ADMIN. `hasRole("ADMIN")` mặc định đối chiếu authority `ROLE_ADMIN`, không phải chuỗi `ADMIN` thô.

**Request F: `GET /internal/debug` của admin.** Rule `denyAll` khớp → từ chối dù admin có quyền rộng.

**Request G: `GET /undocumented` của user đã login.** `anyRequest().denyAll()` áp dụng → từ chối theo allowlist.

### Chi tiết quan trọng của đoạn code

- Đường `/public/feedback` chỉ được công khai cho **POST**. GET cùng đường dẫn không tự động công khai.
- `GET /public/**` được public; POST `/public/new-item` không mặc nhiên public.
- Rule **đầu tiên khớp** được dùng; vì thế thứ tự khai báo phải có chủ đích.
- `httpBasic` chỉ là một ví dụ authentication mechanism; không phù hợp cho mọi kiến trúc. Production phải dùng HTTPS và account/credential policy phù hợp.
- Rule `permitAll` không tự tắt CSRF. Không tắt CSRF toàn cục chỉ để ví dụ POST thành công; hãy thiết kế theo nguồn credential và tình huống browser.
- Với ứng dụng cần cho truy cập health/metrics hoặc login UI, phải **khai báo những endpoint đó một cách có chủ đích**, vì fallback `denyAll` chặn toàn bộ đường chưa liệt kê.
- Không lấy ví dụ `invoice:read` làm bằng chứng Spring Security tự cấp permission; application cần map/cấp `GrantedAuthority` đó từ nguồn đáng tin.

## 8. Quy tắc nào được xét trước? “First match wins”

Trong `authorizeHttpRequests`, Spring Security xét các rule theo **thứ tự khai báo**, và áp dụng **rule đầu tiên khớp request**. Những rule phía sau không tiếp tục “nâng cấp” hoặc “siết thêm” cùng request.

Đặt rule rộng ở đầu dễ làm vô hiệu rule cụ thể:

~~~java
// SAI nếu admin phải được bảo vệ bằng ROLE_ADMIN.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
);
~~~

`GET /api/admin/users` đã khớp `/api/**` → chỉ yêu cầu đăng nhập, **không bao giờ chạm** rule admin phía sau.

Sửa:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
);
~~~

Đây là ví dụ về ưu tiên rule, **không có nghĩa `/api/**` luôn an toàn nếu chỉ yêu cầu đăng nhập**. Trong ứng dụng nghiêm ngặt, khai báo permission cụ thể theo các nhóm API và dùng fallback `denyAll` thường an toàn hơn.

### 8.1. Phương thức HTTP cũng là phần của matcher

~~~java
.requestMatchers(HttpMethod.GET, "/documents/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/documents/**").hasRole("ADMIN")
.anyRequest().denyAll()
~~~

GET và DELETE có yêu cầu khác nhau. Nếu viết `.requestMatchers("/documents/**").authenticated()` trước, cả DELETE cũng có thể bị matcher tổng quát bắt trước và vượt qua mà không cần role ADMIN.

Đừng quên PUT, PATCH, HEAD, OPTIONS hoặc method custom nếu ứng dụng hỗ trợ. Một số framework/API có hành vi xử lý HEAD hoặc preflight riêng; hãy kiểm thử behavior thực tế thay vì suy luận rằng chỉ cần bảo vệ GET và POST.

### 8.2. Path matcher không tự đánh giá query parameter

Rule `.requestMatchers("/reports/**").authenticated()` thường so khớp phần đường dẫn theo RequestMatcher được dùng, **không** phân quyền dựa trên `?tenantId=...` hoặc `?owner=...`. Nếu controller nhận ID tài nguyên, cần kiểm tra owner/tenant tại policy thực tế. Không coi path pattern là giải pháp object-level authorization.

### 8.3. Thứ tự rule không giống thứ tự filter

- **Thứ tự rule:** xác định rule URL nào được `AuthorizationManager` chọn.
- **Thứ tự filter:** xác định các bước như CSRF, xác thực, authorization diễn ra ở đâu trong request lifecycle.
- **Thứ tự SecurityFilterChain:** nếu nhiều chain, quyết định **chain nào** áp dụng cho request trước khi xét rule bên trong chain.

Đây là ba cấp lựa chọn riêng, không thể dùng một cấp để kết luận cấp khác.

## 9. `anyRequest().authenticated()` hay `anyRequest().denyAll()`?

Hai fallback thường gặp:

~~~java
// Phong cách 1: các endpoint chưa liệt kê vẫn cần login.
.anyRequest().authenticated()
~~~

~~~java
// Phong cách 2: các endpoint chưa liệt kê đều đóng.
.anyRequest().denyAll()
~~~

| Tiêu chí | Fallback `authenticated()` | Fallback `denyAll()` |
|---|---|---|
| Endpoint mới chưa thêm rule | User đã login có thể vào HTTP layer | Mặc định không vào HTTP layer |
| Phù hợp | Ứng dụng có chủ đích bảo vệ toàn bộ nội dung bằng login | API nhạy cảm, yêu cầu allowlist rõ |
| Nguy cơ | Quên permission cụ thể khiến tài nguyên mở cho mọi user đã login | Quên rule khiến chức năng mới bị chặn cho tới khi bổ sung |
| Tư duy | “Mọi thứ là của người đăng nhập trừ ngoại lệ” | “Không được phép trừ khi cấp quyền rõ ràng” |

**Không có fallback nào bù cho rule sai đặt trước đó.** Nếu `/api/**` đã được `permitAll` hoặc `authenticated` quá rộng thì `anyRequest().denyAll()` sẽ không chặn request khớp rule trước.

Với API nhạy cảm, nguyên tắc **deny by default** và test thêm endpoint mới thường được khuyến nghị. Với trang chỉ cần login, fallback `authenticated` có thể phù hợp nếu đó là chính sách chủ đích, không phải do bỏ sót.

## 10. `permitAll` và việc đọc `Authentication`: tối ưu không phải bỏ bảo mật

Kiến trúc `authorizeHttpRequests` thường dùng `AuthorizationFilter` và `AuthorizationManager`. Thay vì luôn lấy `Authentication` ngay từ đầu, filter xây dựng một `Supplier<Authentication>` và để rule gọi khi cần.

~~~text
AuthorizationFilter
     |
     +-- Supplier<Authentication> (lấy từ SecurityContextHolder khi cần)
     |
     +-- Matcher chọn rule
              |
              +-- permitAll --> cho phép không cần supplier.get()
              |
              +-- denyAll   --> từ chối không cần supplier.get()
              |
              +-- authenticated --> cần trạng thái Authentication
              |
              +-- hasRole/hasAuthority --> cần authorities
~~~

Hệ quả:

1. `permitAll` và `denyAll` **không cần tra cứu Authentication** cho chính quyết định này.
2. Điều này tránh tải session không cần thiết ở nhiều trường hợp, có lợi cho tài nguyên public.
3. Không được suy ra authentication filter không chạy. Nếu request gửi credentials hỏng, filter có thể báo lỗi **trước** authorization.
4. Không được suy ra `SecurityContextHolder` trong controller chắc chắn trống sau `permitAll`. Nếu authentication đã được thiết lập bởi phần khác của chain, controller vẫn có thể nhìn thấy.
5. Không tự lưu một kết quả “current user” vào singleton bean khi ứng dụng xử lý nhiều request. Phải lấy ngữ cảnh đúng request/invocation.

Đối với custom `AuthorizationManager`, API cho phép nhận `Supplier<Authentication>`. Chỉ gọi `supplier.get()` nếu policy cần danh tính. Với constant decision, không nhất thiết phải truy vấn.

## 11. Không được nhầm `permitAll` với `securityMatcher` và nhiều filter chain

Một ứng dụng có thể khai báo nhiều `SecurityFilterChain`, mỗi chain có một `securityMatcher(...)` và `@Order`. Spring Security chọn **chain đầu tiên có matcher phù hợp**, sau đó mới xét `authorizeHttpRequests` bên trong chain đó.

Ví dụ khái niệm:

~~~text
FilterChainProxy
  1. SecurityFilterChain A: matcher /api/**
         rule bên trong: /api/public/** -> permitAll
                         còn lại        -> authenticated
  2. SecurityFilterChain B: matcher /**
         rule bên trong: /docs/**       -> permitAll
                         còn lại        -> denyAll
~~~

Nếu request `/api/public/faq` khớp chain A, `permitAll` chỉ xảy ra **trong chain A**; chain B không tự đánh giá lại request.

Quan trọng hơn, nếu tất cả filter chain đều có `securityMatcher` quá hẹp và một URL không khớp **bất kỳ** chain nào, URL đó có thể không được Spring Security bảo vệ. Vì vậy khi chia chain theo nhóm API, cần có chiến lược fallback bao phủ ứng dụng, chứ không chỉ đặt `anyRequest().denyAll()` trong một chain vốn không bao giờ nhận URL đó.

Các trường hợp cần đặc biệt xem lại: actuator endpoints, path admin, CORS preflight, tài nguyên tĩnh, error handler và đường dẫn đăng nhập.

## 12. Xác thực không có nghĩa được thao tác trên mọi bản ghi

Giả sử:

~~~java
.requestMatchers(HttpMethod.GET, "/api/invoices/**").authenticated()
~~~

Lan và Bình đều login. Lan gọi `GET /api/invoices/102`, nhưng hóa đơn 102 thuộc Bình. HTTP rule vẫn cho Lan đi qua vì điều kiện chỉ là “đã đăng nhập”.

Lỗ hổng **horizontal unauthorized access/BOLA** xuất hiện nếu service lấy invoice bằng ID rồi trả thẳng mà không check owner/tenant.

Sử dụng kiểm soát nhiều lớp:

~~~text
HTTP authorization:
    Có đăng nhập? Có permission invoice:read?
         |
         v
Service / use-case policy:
    Đúng tenant? Là owner? Được share? Đúng trạng thái?
         |
         v
Repository:
    Query/UPDATE giới hạn đúng phạm vi dữ liệu
~~~

Một method Spring-managed service minh họa:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "hasAuthority('invoice:read') " +
    "and @invoicePolicy.canRead(authentication, #id)"
)
public InvoiceDto readInvoice(long id) {
    return invoiceQueryService.read(id);
}
~~~

Đây chỉ là **method minh họa**, cần bật `@EnableMethodSecurity` và cung cấp `invoicePolicy`, `InvoiceDto`, `invoiceQueryService`, đồng thời đảm bảo `#id` được nhận diện đúng. Không thể chạy bằng JDK thuần. Nó nhắc rằng `authenticated` là điều kiện tối thiểu, không phải chính sách cho tài nguyên nhạy cảm.

Ngược lại, `permitAll` ở HTTP layer không ép service bỏ `@PreAuthorize`. Nếu service có policy riêng, nó vẫn có thể từ chối sau khi request đi qua HTTP rule. Tránh tình trạng cấu hình HTTP và service mâu thuẫn không có chủ đích: hãy thống nhất chính sách bằng test.

## 13. CSRF, CORS và protected resources: những lớp khác vẫn tồn tại

### 13.1. POST public và CSRF

Giả sử:

~~~java
.requestMatchers(HttpMethod.POST, "/public/feedback").permitAll()
~~~

Người dùng anonymous gọi `POST /public/feedback`. Ở cấu hình Servlet có CSRF protection đang bật cho unsafe methods, request không có CSRF token phù hợp có thể bị từ chối.

Điều đó **không chứng minh `permitAll` bị lỗi**. Nó cho thấy CSRF là một lớp bảo vệ **khác** với rule HTTP authorization.

Quyết định xử lý dựa trên kiến trúc:

- Ứng dụng browser dựa trên cookie/session: cần giữ CSRF protection phù hợp và cung cấp token khi cần.
- API dùng Bearer token ở header và không sử dụng credentials tự gửi bởi browser: có thể thiết kế CSRF khác, nhưng phải đánh giá kỹ cách client thực sự xác thực và nguy cơ request bị giả mạo.
- Nếu một endpoint cần ngoại lệ CSRF, cấu hình phạm vi ngoại lệ hẹp, có giải thích rủi ro và test âm tính. **Không tắt CSRF toàn cục chỉ vì muốn `permitAll` cho POST.**

### 13.2. CORS preflight

Trình duyệt có thể gửi `OPTIONS` preflight trước request cross-origin. Nếu rule/chain từ chối OPTIONS mà không có cấu hình CORS hợp lệ, frontend có thể báo lỗi dù GET/POST chính đã có rule đúng.

Dùng tích hợp CORS phù hợp với Spring Security và cấu hình origin/method/header có chủ đích. Đừng tùy tiện `permitAll` mọi OPTIONS để “chữa” lỗi mà chưa xem xét chính sách CORS. Và **CORS không phải authorization**: một request không phải browser vẫn có thể gửi trực tiếp đến server.

### 13.3. Static assets và security headers

Nên ưu tiên `permitAll` cho CSS/JS/image được công khai để vẫn nhận các security headers thích hợp. Đưa URL vào ignore list hoặc bỏ nó khỏi toàn bộ filter chain có thể mất những bảo vệ đó.

### 13.4. Chuyển tiếp `FORWARD`, `ERROR` và dispatcher

Ở Servlet, `AuthorizationFilter` có thể được áp dụng cho nhiều dispatcher type, không chỉ request gốc. Spring MVC view forward và trang xử lý lỗi có thể phát sinh dispatch mới cần xem xét rule.

Có thể cấu hình `dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()` **khi ứng dụng thật sự cần**, nhưng việc mở toàn bộ dispatcher theo loại cần được cân nhắc để không tạo đường truy cập vòng vào nội dung nội bộ nhạy cảm. Không tự động xem mọi forwarding đều vô hại.

## 14. 401, 403, redirect hay 404: đọc kết quả cho đúng

| Tình huống | Hành vi thường gặp | Lưu ý |
|---|---|---|
| User chưa login gặp `authenticated()`, dùng HTTP Basic | `401 Unauthorized` + challenge | Tùy authentication entry point |
| User chưa login gặp `authenticated()`, dùng form login | Redirect sang login | Không nhất thiết trả 401 JSON |
| User đã login thiếu `hasAuthority`/`hasRole` | `403 Forbidden` | Tùy access-denied handler |
| User đã login gặp `denyAll()` | Thường 403 | Không thể qua rule chỉ bằng role cao hơn |
| User anonymous gặp `denyAll()` | Có thể kích hoạt entry point/401/redirect | Không buộc luôn 403 |
| `permitAll()` trên route không tồn tại | Có thể 404 | Authorization cho phép không tự tạo controller |
| `permitAll()` với POST thiếu CSRF token | Có thể 403 | Chặn bởi CSRF trước authorization |
| `authenticated()` nhưng service từ chối vì owner/tenant | Có thể 403 hoặc 404 | Quyết định ở tầng nghiệp vụ |

Muốn gỡ lỗi cần biết **lớp nào** đã từ chối. Một `403` không tự chứng minh lỗi đến từ `denyAll`; nó cũng có thể do thiếu CSRF hoặc method security.

## 15. Kiểm thử bằng Spring Security Test và MockMvc

Ở một dự án Spring Boot MVC có Spring Security Test, cấu hình endpoint được bảo vệ và controller hợp lệ, nên thử cả **được phép** và **bị từ chối**.

Ví dụ template cho các đường `GET`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void profileRejectsAnonymous() throws Exception {
        mvc.perform(get("/account/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void profileAllowsUser() throws Exception {
        mvc.perform(get("/account/profile").with(user("lan")))
            .andExpect(status().isOk());
    }

    @Test
    void internalPathRejectsAdmin() throws Exception {
        mvc.perform(get("/internal/debug")
                    .with(user("admin").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownPathIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/unknown")
                    .with(user("admin").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Giới hạn của template:** cần có controller trả 200 tại `/public/catalog` và `/account/profile`; cần Spring Boot Test/Spring Security Test, authentication entry point HTTP Basic đúng như ví dụ cấu hình và security filter đã áp dụng cho MockMvc. Nếu thiếu controller, có thể thấy 404 dù authorization cho phép. Hãy sửa import bị xuống dòng để mỗi câu lệnh `import static` nằm **một dòng** trong source thực; ở đây chúng được ngắt dòng để minh họa package.

Với `POST`, test cần xem xét CSRF:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;

// Khi CSRF protection được bật trong ứng dụng:
mvc.perform(post("/public/feedback"))
    .andExpect(status().isForbidden());

mvc.perform(post("/public/feedback").with(csrf()))
    .andExpect(status().isOk());
~~~

Đây là đoạn minh họa trong test method; endpoint phải tồn tại và trả 200 sau khi request hợp lệ. **Không hiểu rằng mọi POST `permitAll` đều trả 403 khi thiếu CSRF**: điều đó phụ thuộc CSRF configuration và loại request.

### 15.1. Ma trận test nên có

| Request | Principal / trạng thái | Expected HTTP authorization |
|---|---|---|
| `GET /public/catalog` | Anonymous | Allow |
| `GET /public/catalog` | User đã login | Allow |
| `GET /account/profile` | Anonymous | Deny |
| `GET /account/profile` | User đã login | Allow |
| `GET /account/profile` | Remember-me, nếu bật | Allow theo mặc định |
| `GET /api/invoices/1` | User thiếu `invoice:read` | Deny |
| `GET /api/invoices/1` | User có `invoice:read` | Allow ở HTTP, vẫn cần object policy |
| `POST /api/invoices/1` | User chỉ có `invoice:read` | Deny |
| `GET /api/admin/users` | User chỉ có `ROLE_USER` | Deny |
| `GET /api/admin/users` | User có `ROLE_ADMIN` | Allow ở HTTP |
| `GET /internal/debug` | Admin | Deny |
| `GET /unknown` | Admin | Deny do fallback |
| `POST /public/feedback` thiếu CSRF | Anonymous, CSRF đang áp dụng | Bị CSRF từ chối dù HTTP rule là Allow |
| `GET /api/admin/users` với rule rộng đặt trước | User bình thường | Test âm tính phải phát hiện sai thứ tự |

Đừng viết test chỉ với admin. Khi kiểm tra thứ tự matcher, cần có user không có quyền admin thử trực tiếp endpoint admin. Khi xác minh quyền object-level, cần hai user cùng role nhưng khác owner/tenant.

## 16. Chương trình Java 17 độc lập: mô phỏng ba quyết định và thứ tự rule

Ví dụ sau là **mô phỏng bằng Java thuần** để dễ chạy và quan sát. Nó **không phải implementation của Spring Security**, không mô phỏng authentication filter, CSRF, role hierarchy, exception handler hay toàn bộ RequestMatcher. Nó chỉ biểu diễn logic của những rule đã học, mô phỏng `fullyAuthenticated` để so sánh, và việc **dừng ở rule đầu tiên khớp**.

Tạo tệp `HttpRuleDemo.java`:

~~~java
import java.util.List;

public class HttpRuleDemo {

    enum Identity {
        ANONYMOUS, REMEMBERED, FULL
    }

    enum Policy {
        PERMIT_ALL, DENY_ALL, AUTHENTICATED, FULLY_AUTHENTICATED
    }

    record Request(String method, String path, Identity identity) {
    }

    record Rule(String method, String prefix, Policy policy) {
        boolean matches(Request request) {
            return ("*".equals(method) || method.equals(request.method()))
                    && request.path().startsWith(prefix);
        }
    }

    static boolean allowed(Identity identity, Policy policy) {
        return switch (policy) {
            case PERMIT_ALL -> true;
            case DENY_ALL -> false;
            case AUTHENTICATED -> identity != Identity.ANONYMOUS;
            case FULLY_AUTHENTICATED -> identity == Identity.FULL;
        };
    }

    static boolean authorize(Request request, List<Rule> rules) {
        for (Rule rule : rules) {
            if (rule.matches(request)) {
                return allowed(request.identity(), rule.policy());
            }
        }
        return false;
    }

    static void show(String label, Request request, List<Rule> rules) {
        System.out.println(label + ": " + authorize(request, rules));
    }

    public static void main(String[] args) {
        List<Rule> rules = List.of(
                new Rule("GET", "/public/", Policy.PERMIT_ALL),
                new Rule("GET", "/account/", Policy.AUTHENTICATED),
                new Rule("GET", "/finance/", Policy.FULLY_AUTHENTICATED),
                new Rule("*", "/internal/", Policy.DENY_ALL),
                new Rule("*", "/", Policy.DENY_ALL)
        );

        show("public anonymous",
                new Request("GET", "/public/catalog", Identity.ANONYMOUS),
                rules);

        show("account anonymous",
                new Request("GET", "/account/me", Identity.ANONYMOUS),
                rules);

        show("account remembered",
                new Request("GET", "/account/me", Identity.REMEMBERED),
                rules);

        show("finance remembered",
                new Request("GET", "/finance/pay", Identity.REMEMBERED),
                rules);

        show("finance full",
                new Request("GET", "/finance/pay", Identity.FULL),
                rules);

        show("internal full",
                new Request("GET", "/internal/debug", Identity.FULL),
                rules);

        show("unmatched full",
                new Request("GET", "/other", Identity.FULL),
                rules);

        show("post public anonymous",
                new Request("POST", "/public/catalog", Identity.ANONYMOUS),
                rules);

        List<Rule> badOrder = List.of(
                new Rule("*", "/", Policy.AUTHENTICATED),
                new Rule("GET", "/public/", Policy.PERMIT_ALL)
        );

        show("bad order public anonymous",
                new Request("GET", "/public/catalog", Identity.ANONYMOUS),
                badOrder);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 HttpRuleDemo.java
java HttpRuleDemo
~~~

Kết quả chuẩn:

~~~text
public anonymous: true
account anonymous: false
account remembered: true
finance remembered: false
finance full: true
internal full: false
unmatched full: false
post public anonymous: false
bad order public anonymous: false
~~~

Giải thích kết quả:

- **`public anonymous: true`**: GET public gặp `PERMIT_ALL`.
- **`account anonymous: false`**: chưa login không đạt `AUTHENTICATED`.
- **`account remembered: true`**: mô phỏng remember-me được chấp nhận bởi `AUTHENTICATED`.
- **`finance remembered: false`**: remember-me không đạt `FULLY_AUTHENTICATED`.
- **`finance full: true`**: login đầy đủ đạt yêu cầu.
- **`internal full: false`**: `DENY_ALL` áp dụng cả khi đã login đầy đủ.
- **`unmatched full: false`**: fallback `DENY_ALL` chặn URL ngoài danh sách.
- **`post public anonymous: false`**: rule public chỉ dành cho GET; POST rơi vào fallback.
- **`bad order public anonymous: false`**: catch-all `AUTHENTICATED` đứng trước, nên rule public phía sau không được xét đến.

**Lưu ý quan trọng:** ở đây `path.startsWith(prefix)` chỉ là cách minh họa một prefix đơn giản; Spring Security sử dụng những implementation `RequestMatcher` cụ thể với semantics đường dẫn phù hợp, không phải hàm Java đơn giản này. Bài tập giúp nắm **first match wins** và ba trạng thái quyền, không thay thế integration test Spring.

## 17. Những lỗi cấu hình phổ biến

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Đặt `/api/**.permitAll()` trước rule admin | Rule quá rộng khớp trước | Thu hẹp public URL và sắp xếp đặc thù trước |
| Đặt `/api/**.authenticated()` rồi nghĩ GET/POST tài nguyên đều an toàn | Có login chưa đủ permission | Dùng `hasAuthority`/`hasRole` và object policy |
| Dùng `permitAll` để “tắt CSRF” | CSRF là filter bảo vệ khác | Quản lý CSRF token hoặc exception hẹp theo kiến trúc |
| Dùng `web.ignoring()` cho mọi public route | Bỏ cả security chain cho route đó | Ưu tiên `permitAll` khi có thể |
| Dùng `denyAll` rồi mong admin vẫn được vào | Deny là vô điều kiện ở rule | Dùng rule role/permission đúng nếu cần admin |
| Nghĩ `denyAll` luôn trả 403 | Chưa login có thể kích hoạt entry point | Test status/redirect theo auth mechanism |
| Nghĩ `authenticated` loại bỏ remember-me | Nhầm với fully-authenticated | Dùng `fullyAuthenticated` khi thực sự yêu cầu |
| Tự so `isAuthenticated()` và cho anonymous qua | Anonymous token có thể mang cờ true | Dùng `authenticated()`/trust resolver của framework |
| Đặt `anyRequest().authenticated()` ở cuối mà không review API mới | API nhạy cảm có thể lộ cho mọi user đã login | Cân nhắc allowlist `denyAll` và tests |
| Chỉ bảo vệ URL nhưng quên method security | Service có thể được gọi qua entry point khác | Policy tại service/use case |
| Chỉ match một `SecurityFilterChain` quá hẹp | URL ngoài mọi chain có thể không được bảo vệ | Tạo chain fallback bao phủ |
| Bỏ qua `ERROR/FORWARD` dispatch | View/error flow có thể bị chặn hoặc mở sai | Thiết kế dispatcher policies và test |
| Chỉ xem HTTP status, không kiểm tra dữ liệu rò rỉ | Có thể bị chặn sau khi đã lộ thông tin | Test response body, owner/tenant, logs |
| Coi CORS là authorization | Non-browser client bỏ qua CORS | Dùng authentication và authorization thật |
| Chỉ test happy path admin | Không phát hiện rule rộng/thứ tự sai | Test anonymous, user thường, user thiếu quyền |

## 18. Checklist thực hành khi review cấu hình

Trước khi đưa `SecurityFilterChain` lên môi trường thật, hãy lần lượt trả lời:

1. **Phạm vi chain:** request có chắc khớp ít nhất một security filter chain? Có `securityMatcher` hoặc `@Order` làm mất coverage không?
2. **Đường public:** chính xác method + path nào không cần login? Có vô tình mở rộng cho đường con nhạy cảm?
3. **Các API cần login:** `authenticated` có đủ theo yêu cầu nghiệp vụ, hay còn cần role/permission?
4. **Các API đặc quyền:** `hasRole`/`hasAuthority` có dùng đúng chuỗi authority mà authentication thực sự được cấp?
5. **Đối tượng dữ liệu:** service có check owner, tenant, relation và workflow state không?
6. **Các endpoint không công khai:** có `denyAll` rõ ràng khi cần? Fallback đóng hay chỉ yêu cầu login?
7. **Thứ tự rule:** đã đọc từ trên xuống và xác định rule khớp đầu tiên cho từng endpoint chưa?
8. **Method khác:** có thử GET, POST, PUT, PATCH, DELETE và các dispatch cần thiết không?
9. **CSRF/CORS/filter khác:** POST public có thể cần CSRF; preflight xử lý đúng mà không mở authorization quá rộng?
10. **Hành vi lỗi:** 401/403/redirect/404 phù hợp với authentication mechanism và chính sách che dữ liệu?
11. **Kiểm thử âm tính:** có user thường thử endpoint admin, anonymous thử profile, admin thử internal, user thiếu permission thử API?
12. **Kiểm soát thay đổi:** thêm một controller mới có được review rule và test bao phủ ngay không?

Một cách đọc cấu hình đơn giản:

~~~text
[Chain nào khớp?]
        |
        v
[Rule đầu tiên khớp method + path?]
        |
        +-- permitAll      -> Không cần login tại rule HTTP
        +-- authenticated  -> Cần user không phải anonymous
        +-- hasAuthority   -> Cần authority cụ thể
        +-- hasRole        -> Cần role theo quy ước tiền tố
        +-- denyAll        -> Luôn từ chối tại rule HTTP
        |
        v
[Filter bảo vệ khác, method policy, object policy còn tác dụng?]
        |
        v
[Controller/service trả kết quả]
~~~

## 19. Tự kiểm tra kiến thức

**1. `permitAll()` có nghĩa mọi request tới endpoint đó luôn trả 200 không?**  
Không. Authentication filter, CSRF, controller, method security và business policy vẫn có thể từ chối hoặc trả 404/5xx.

**2. Admin có qua được `denyAll()` không?**  
Không. Rule từ chối vô điều kiện; nếu admin cần vào, phải dùng rule đặc quyền thích hợp thay vì deny.

**3. `authenticated()` có kiểm tra `ROLE_USER` hay `invoice:read` không?**  
Không. Nó chỉ kiểm tra trạng thái xác thực theo semantics framework, không yêu cầu role/permission cụ thể.

**4. Anonymous authentication token có thể `isAuthenticated() == true`, vậy có vượt `authenticated()` không?**  
Thông thường không, vì `authenticated()` có cơ chế loại anonymous qua trust resolver.

**5. Remember-me có vượt `authenticated()` không?**  
Thông thường có; nếu yêu cầu đăng nhập đầy đủ thì cân nhắc `fullyAuthenticated()`.

**6. Tại sao `/api/admin/**` đặt sau `/api/**.authenticated()` lại nguy hiểm?**  
Rule rộng khớp trước khiến rule admin không được xét, biến điều kiện quản trị thành “chỉ cần login”.

**7. `anyRequest().denyAll()` ở cuối có cứu được rule `/api/**.permitAll()` đặt trên không?**  
Không, vì request đã khớp rule rộng trước và không đi tới fallback.

**8. `POST /public/feedback` có `permitAll` nhưng thiếu CSRF token bị 403. Có nên đổi thành `authenticated` không?**  
Không. Đây là hai trách nhiệm khác nhau: authorization và CSRF protection; cần thiết kế/test CSRF đúng.

**9. Nếu `securityMatcher("/api/**")` của chain A không khớp `/admin/**` và không có chain khác, `anyRequest().denyAll()` của A có chặn admin không?**  
Không. Request không vào chain A nên fallback bên trong A không được áp dụng.

**10. Qua `authenticated()` rồi có được đọc mọi dữ liệu theo ID không?**  
Không. Phải còn kiểm tra role/permission nghiệp vụ, owner/tenant và các ràng buộc tài nguyên.

## 20. Tài liệu tham khảo

- Spring Security – **Authorize HttpServletRequests** (rule order, `permitAll`, `denyAll`, deferred authentication lookup): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – **Anonymous Authentication** (đánh giá anonymous và authentication trust resolver): https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security – **Authorization Architecture** (các authorization manager, phân biệt fully authenticated/remember-me): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **Cross Site Request Forgery (CSRF)**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – **Servlet Architecture and Filters**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
