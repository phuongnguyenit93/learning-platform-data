# Tách phạm vi API, giao diện và quản trị qua các filter chain

## 1. Vấn đề: cùng một ứng dụng nhưng các vùng cần bảo vệ khác nhau

Một ứng dụng Spring Boot có thể đồng thời phục vụ ba loại đường truy cập:

- **API**: `/api/**` nhận bearer access token, trả JSON, có thể phục vụ mobile app hoặc hệ thống khác, thường mong muốn xử lý theo từng request mà không dựa vào phiên đăng nhập giao diện.
- **Giao diện người dùng (UI)**: `/ui/**`, `/login`, `/logout` sử dụng form login và cookie/session; với hành động thay đổi trạng thái từ trình duyệt cần bảo vệ CSRF.
- **Quản trị**: `/admin/**` chỉ dành cho người có quyền quản trị, có thể chia sẻ phiên UI nhưng có chính sách quyền, xác thực tăng cường và kiểm toán nghiêm ngặt hơn.

Nếu đặt mọi quy tắc trong một chuỗi bảo mật duy nhất, cấu hình sẽ ngày càng phức tạp: JWT và form login có thể cạnh tranh đường xử lý; API trả redirect HTML thay vì 401; CSRF có thể bị tắt trên giao diện chỉ vì API muốn stateless; hoặc người dùng UI thông thường vô tình được gọi chức năng quản trị. Spring Security Servlet cho phép dùng **nhiều `SecurityFilterChain`**, mỗi chain có phạm vi match và tập filter riêng.

Nhưng tách chain sai cũng tạo lỗi nguy hiểm: một request rơi **ngoài mọi chain**, chain quá rộng được chọn trước chain admin, hoặc đường `/login` không thuộc chain chứa filter xử lý đăng nhập.

Mục tiêu của bài học là **chia vùng bảo vệ có chủ đích**, hiểu ngữ cảnh của mỗi request, xây cấu hình nhất quán, kiểm tra toàn bộ đường vào và các ranh giới xác thực/phân quyền.

### Luồng lựa chọn

```text
              HTTP REQUEST
       method + path + headers + ...
                    |
                    v
            FilterChainProxy
                    |
         thử theo thứ tự @Order
                    |
        +-----------+-----------+
        |                       |
    /admin/**?               không
        |                       |
       có                       v
        |                    /api/**?
        v                    /      \
    ADMIN CHAIN             có       không
    session / admin         |          |
    authority + CSRF        v          v
                       API CHAIN    UI/FALLBACK
                       bearer JWT   CHAIN
                       stateless    form login
                       API rule     session + CSRF
                          |           |
                          +-----+-----+
                                |
                                v
                        ALLOW / DENY
                                |
                                v
                    Service / object policy
                    tenant, owner, trạng thái
```

**Chỉ một `SecurityFilterChain` đầu tiên khớp được chọn cho một lượt xử lý của `FilterChainProxy`.** Các chain phía sau không chạy tiếp như những lớp phân quyền cộng dồn. Mỗi lần request được dispatch lại trong Servlet, cần hiểu filter registration và phạm vi match cho lượt đó; không tự cho rằng mọi chain đều chạy nối tiếp.

## 2. Những khái niệm phải phân biệt

| Thành phần | Vai trò | Điểm dễ nhầm |
| --- | --- | --- |
| `SecurityFilterChain` | Danh sách filter bảo mật áp dụng cho một nhóm request | Không phải một quy tắc permission duy nhất |
| `FilterChainProxy` | Thử các `SecurityFilterChain` theo thứ tự và chọn chain đầu tiên khớp | Không chạy tất cả chain khớp |
| `HttpSecurity` | DSL xây một security filter chain | Mỗi bean chain có thể khác cấu hình |
| `securityMatcher(...)` | Xác định **request nào đi vào chain này** | Khác `requestMatchers(...)` bên trong authorization |
| `authorizeHttpRequests(...)` | Định nghĩa chính sách cấp HTTP cho request đã vào chain | Không tự kiểm tra owner/tenant của mọi object |
| `requestMatchers(...)` | Chọn quy tắc HTTP trong chain | Thứ tự khai báo có thể ảnh hưởng kết quả |
| `@Order` | Định thứ tự ưu tiên các chain | Không phải ưu tiên của authority hoặc user role |
| `Authentication` | Danh tính và quyền đã được xác thực | Không nên tạo từ raw client header |
| `SessionCreationPolicy.STATELESS` | Chính sách không tạo/dùng HttpSession cho SecurityContext của chain | Không phải lời bảo đảm mọi filter ứng dụng đều stateless |
| `CsrfFilter` | Bảo vệ request thay đổi trạng thái trong mô hình có nguy cơ CSRF | Không phải kiểm tra quyền nghiệp vụ |
| `AuthenticationEntryPoint` | Phản hồi khi cần bắt đầu xác thực, ví dụ 401 hoặc redirect login | Không giống handler của thiếu quyền |
| `AccessDeniedHandler` | Xử lý từ chối quyền khi đã có xác thực phù hợp | Không nên biến mọi 403 thành redirect login |
| Method/object authorization | Kiểm tra authority và điều kiện của tài nguyên thực tế | Cần thiết dù HTTP chain đã cho qua |

### 2.1. `securityMatcher` ở ngoài, `requestMatchers` ở trong

Hai phương thức thường xuất hiện gần nhau nhưng có phạm vi khác hẳn:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/reports/**")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll()
    );
```

- `securityMatcher("/api/**")`: **chỉ những request khớp mẫu này mới được thử các filter trong chain**.
- `requestMatchers("/api/reports/**")`: trong API chain đã chọn, đây là một nhánh chính sách yêu cầu scope đọc báo cáo.
- `anyRequest().denyAll()`: từ chối request API đã vào chain nhưng không khớp nhánh cho phép; **không** bảo vệ đường ngoài `/api/**` nếu không có chain khác.

Vì vậy, một cấu hình có `denyAll()` vẫn có thể để lọt `/admin/config` nếu nó **chỉ tạo chain cho `/api/**`**.

### 2.2. Phạm vi chain và phạm vi nghiệp vụ không giống nhau

Chain có thể biết đường dẫn `/admin/users/42` là route quản trị; nhưng nó chưa đủ biết user 42 thuộc tổ chức nào, thao tác là tự khóa tài khoản hay cấp quyền, và có cần người phê duyệt thứ hai không. Với hành động nhạy cảm, quyền còn phải được kiểm tra ở service và truy vấn dữ liệu.

Một người có `ROLE_ADMIN` ở tenant A không mặc nhiên được quản trị user thuộc tenant B. Nếu hệ thống có nhiều tenant/realm, cần mô hình hóa phạm vi role và luôn kiểm tra ở phía server.

## 3. Thiết kế vùng bảo vệ trước khi viết Java

### 3.1. Ma trận yêu cầu

Giả sử hệ thống đặt các endpoint:

| Vùng | Đường ví dụ | Cơ chế danh tính dự kiến | Quyền và nguyên tắc |
| --- | --- | --- | --- |
| API | `GET /api/reports/17` | JWT access token trong `Authorization: Bearer ...` | `SCOPE_reports.read` + quyền tài liệu |
| API | `POST /api/reports` | JWT access token | `SCOPE_reports.write` + quy tắc nghiệp vụ |
| UI | `GET /ui/dashboard` | Session đăng nhập từ form | Người dùng đã xác thực |
| UI | `POST /ui/profile` | Session + CSRF token | User đã đăng nhập, chỉ sửa hồ sơ của mình |
| Auth UI | `GET /login`, `POST /login` | Form authentication | Trang/đường xử lý login phải được chain phù hợp nhận |
| Auth UI | `POST /logout` | Session + CSRF | Đường logout trong chain phù hợp |
| Admin | `GET /admin/audit` | Session đăng nhập, thêm điều kiện quản trị | `ROLE_ADMIN` và chính sách audit |
| Admin | `POST /admin/users/42/disable` | Session + CSRF, quyền quản trị | `ROLE_ADMIN` + kiểm soát đối tượng/step-up nếu cần |
| Public | `GET /`, `GET /assets/...` | Không yêu cầu xác thực | `permitAll()`, nhưng vẫn chạy filter chain khi có fallback |
| Chưa định nghĩa | `/debug`, `/private/download` | Không rõ | Mặc định từ chối |

Đây là **phương án minh họa**, không phải một cấu hình Spring Security mặc định. Mỗi hệ thống phải chọn cơ chế xác thực theo hợp đồng của client.

### 3.2. Quy ước thứ tự

Một lựa chọn rõ ràng:

```text
@Order(1): ADMIN
  securityMatcher("/admin", "/admin/**")

@Order(2): API
  securityMatcher("/api", "/api/**")

@Order(3): UI + FALLBACK
  không giới hạn securityMatcher (mặc định khớp mọi request)
```

Tại sao đưa admin trước API/UI? Để nhìn thấy mức đặc quyền và ưu tiên bảo vệ rõ ràng; nếu vùng admin/API không chồng đường thì thứ tự có thể ít ảnh hưởng, nhưng ưu tiên tường minh vẫn giúp review. **Quan trọng nhất là matcher không chồng nhau ngoài ý muốn và fallback đứng cuối.**

Với các path, thường cần xét cả `/api` và `/api/**` (tương tự `/admin`) nếu root của vùng có endpoint. Đừng tự đoán rằng mọi matcher sẽ luôn coi root và pattern đệ quy giống nhau trên mọi phiên bản/path parser. Viết test cho root, slash cuối và biến thể không mong đợi.

### 3.3. Không dùng tên host hoặc header chưa kiểm chứng làm bằng chứng quyền

Nếu có `admin.example.com`, có thể thêm matcher theo host/route để chọn chain. Nhưng host/header do request mang tới có thể bị ảnh hưởng bởi client hoặc reverse proxy. Chỉ nên dựa vào host sau khi cấu hình proxy, routing và trust đúng. Dù khớp admin host, **phải kiểm tra Authentication và quyền quản trị**.

Tương tự, header `X-Internal: true` hay `X-Role: ADMIN` không được biến một user thường thành admin. Path/host có thể giúp phân loại request; authority phải đến từ nguồn danh tính đã xác minh.

## 4. Cấu hình Spring Security 6: ba SecurityFilterChain

Ví dụ này dành cho **Spring Boot 3 / Spring Security Servlet 6.x**, sử dụng cấu hình lambda DSL; không phải một file Java chạy độc lập bằng `javac` vì cần dependency, bean, controller và hệ thống xác thực. Các API bên dưới minh họa ý định tách vùng; cần kết hợp với cấu hình ứng dụng thật.

### 4.1. Java configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

@Configuration
@EnableMethodSecurity
public class MultiZoneSecurityConfig {

    // 1. Vùng quản trị: kiểm tra role, dùng phiên UI và CSRF.
    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/admin", "/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("ROLE_ADMIN")
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new LoginUrlAuthenticationEntryPoint("/login")
                )
            );
        // CSRF không bị tắt. Admin cần lớp bảo vệ nghiệp vụ.
        return http.build();
    }

    // 2. API dành cho bearer access token; không dùng UI session.
    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Chỉ tắt CSRF vì ví dụ GIẢ ĐỊNH API thuần bearer token
            // trong Authorization header, không dùng cookie auth.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }

    // 3. Giao diện, đăng nhập và fallback bảo vệ phần còn lại.
    @Bean
    @Order(3)
    SecurityFilterChain webFallbackChain(HttpSecurity http)
            throws Exception {
        http
            // Không gọi securityMatcher: mặc định khớp mọi request
            // chưa thuộc chain có ưu tiên cao hơn.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/", "/assets/**"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/error")
                    .permitAll()
                .requestMatchers("/ui/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout.permitAll());
        // CSRF mặc định được giữ cho ứng dụng form/session.
        return http.build();
    }
}
```

### 4.2. Các điều kiện để mẫu hoạt động như dự kiến

**Không chỉ copy class rồi cho rằng mọi chức năng đã chạy.** Ứng dụng cần:

- Một cơ chế xác thực UI hợp lệ, ví dụ `UserDetailsService`, `AuthenticationProvider`, hoặc cấu hình xác thực tương ứng với người dùng thực. Nếu dùng form login mặc định, Spring Security cung cấp trang đăng nhập sinh tự động khi cấu hình phù hợp.
- Một `JwtDecoder` và thiết lập trust cho resource server; thông thường cấu hình issuer đáng tin, audience API, chữ ký, thời hạn, thuật toán và claim scope phù hợp. Không chấp nhận ID token như access token API.
- User có authority tương ứng: với claim `scope`/`scp` của JWT, converter mặc định thường tạo prefix `SCOPE_`; với admin UI, principal phải có `ROLE_ADMIN` theo nguồn tin cậy. Hai loại authority này **không tự chuyển đổi**.
- Định nghĩa controller/route thật cho `/ui/**`, `/api/reports/**`, `/admin/**` và các hoạt động liên quan.
- Cách lưu session/cookie, timeout và các thuộc tính cookie phù hợp. Nếu admin yêu cầu bảo vệ mạnh hơn, cần MFA/step-up, audit hoặc chính sách riêng tại service.
- Test rằng URL `/login`, xử lý `POST /login`, logout và error page được chain đúng nhận. Với form login, `permitAll()` của login/logout là **cho phép tiếp cận đường phục vụ xác thực**, không phải cho phép thao tác quản trị.
- Cấu hình CORS, proxy và frontend phù hợp. Đừng nghĩ `csrf.disable()` thay thế CORS hay ngược lại.

### 4.3. Admin chia sẻ session với UI không đồng nghĩa chain là một

Admin chain trong ví dụ **không khai báo form login riêng**, nhưng dùng `LoginUrlAuthenticationEntryPoint("/login")` để hướng người chưa đăng nhập tới đường login thuộc web fallback chain. Sau khi user đăng nhập qua UI và có session hợp lệ, request đến admin chain có thể khôi phục `Authentication` tương ứng từ security context/session được chia sẻ theo cấu hình chuẩn, rồi kiểm tra `ROLE_ADMIN`.

Đây là lựa chọn có chủ đích: **đường xác thực UI được xử lý một nơi; yêu cầu admin vẫn chịu chain riêng**. Nhưng cùng session có nghĩa người dùng thường đã đăng nhập có thể thử URL admin; chain admin phải **kiểm tra quyền** thay vì chỉ `authenticated()`. Đăng nhập thành công qua UI không tự biến user thành quản trị viên.

Nếu yêu cầu bảo mật admin cao, có thể dùng tài khoản/danh tính khác, OIDC với assurance/MFA claim, một session tăng cường hoặc miền riêng. Những phương án này cần thiết kế cách liên kết session, login entrypoint, logout và callback riêng; không tự giả định rằng thêm `@Order(1)` đã tạo ranh giới danh tính độc lập.

### 4.4. API không dùng session UI trong trường hợp nào?

Trong cấu hình mẫu, API chain được thiết kế cho bearer token và `SessionCreationPolicy.STATELESS`. Mục tiêu là:

- Mỗi request API mang token phù hợp; không chấp nhận việc đã đăng nhập form UI như một cách tự động gọi API.
- Khi chưa có bearer token hợp lệ, API được bảo vệ trả phản hồi dành cho client API (thông thường 401) thay vì trang HTML login.
- Khi token có scope nhưng không đủ quyền, API thường trả 403.
- Không dùng HttpSession để tạo/lấy SecurityContext cho request API trong cơ chế tiêu chuẩn của chain này.

**Không suy diễn rằng từ `STATELESS` là mọi thành phần đều không tạo session hoặc hết rủi ro CSRF.** Custom filter/controller vẫn có thể tự tạo session; và nếu một API chấp nhận credential mà trình duyệt tự gửi (cookie hoặc HTTP Basic), nguy cơ CSRF cần được xem xét lại.

Lý do chỉ **tắt CSRF cho chain API bearer-only** là vì ứng dụng ví dụ yêu cầu access token chủ động trong header `Authorization`, không tự chấp nhận authentication qua cookie trên các endpoint đó. Với web UI và admin, vẫn giữ CSRF cho thao tác thay đổi trạng thái. Quyết định cuối cùng phải dựa vào **cách browser gửi credentials thực tế**.

### 4.5. Đường login có thể “biến mất” nếu đặt sai chain

Trong Spring Security, một số filter tạo endpoint xử lý nội bộ, như form login mặc định thường xử lý `GET /login` và `POST /login`. Nếu khai báo:

```java
http.securityMatcher("/ui/**")
    .formLogin(Customizer.withDefaults());
```

mà không có chain nào khác xử lý `/login`, các URL login ở ngoài phạm vi chain có thể **không được filter login tạo/xử lý**, dẫn tới 404 hoặc hành vi không mong muốn.

**Cách tiếp cận:** để form login trong fallback bao phủ `/login` như ví dụ, hoặc bảo đảm security matcher của chain chứa form login bao gồm rõ `/login` và URL xử lý đăng nhập. Với login page tùy chỉnh, phải có controller/view hợp lệ và permitAll đúng; đừng nhầm `loginPage("/login")` với việc framework tự tạo trang HTML đó khi bạn đã chuyển sang custom page.

Tương tự, `/logout`, OAuth2 authorization callback, SAML assertion consumer hoặc CSRF token endpoint, nếu có, phải nằm trong phạm vi chain chứa filter tương ứng.

## 5. Bảng phân tuyến request thật theo ba chain

Giả sử cấu hình ở mục 4 và các controller cần thiết có mặt.

| Request | Chain được chọn | Quy tắc quan trọng | Kết quả ví dụ |
| --- | --- | --- | --- |
| `GET /admin/audit` | Admin | `ROLE_ADMIN` | Admin có role được phép vào route; nghiệp vụ còn kiểm tra dữ liệu |
| `GET /admin/audit` với user UI thường | Admin | Thiếu `ROLE_ADMIN` | Từ chối (thường 403 nếu đã xác thực) |
| `GET /admin/audit` chưa đăng nhập | Admin | Cần login | Điều hướng `/login` theo entrypoint |
| `POST /admin/users/42/disable` | Admin | Role + CSRF + service policy | Không chỉ dựa vào role |
| `GET /api/reports/17` | API | Bearer JWT + `SCOPE_reports.read` | Cho phép nếu token, scope và quyền tài nguyên đúng |
| `POST /api/reports` | API | Bearer JWT + `SCOPE_reports.write` | Cho phép nếu scope và workflow đúng |
| `GET /api/reports/17` chỉ có UI cookie | API | Không có bearer token | Không tự dùng session UI để qua API |
| `GET /ui/dashboard` | UI/fallback | `authenticated()` | User UI đăng nhập được phép |
| `POST /ui/profile` | UI/fallback | Session + CSRF + object policy | Kiểm tra chủ sở hữu hồ sơ |
| `GET /login` | UI/fallback | Form login filter | Trang login theo cấu hình |
| `POST /login` | UI/fallback | Filter xử lý login + CSRF | Xác thực, không gọi API JWT |
| `GET /assets/app.css` | UI/fallback | Public static resource | Được phép |
| `GET /private/debug` | UI/fallback | `denyAll()` | Bị từ chối |
| `GET /api-admin/audit` | UI/fallback | Không khớp `/api/**` hoặc `/admin/**` | Bị từ chối |
| `GET /admin` | Admin | Role | Không vô tình lọt ra fallback |

Trong bảng, “được phép” ở HTTP không có nghĩa hoàn tất object authorization. Một user có `SCOPE_reports.read` vẫn cần quyền xem báo cáo 17 theo tenant, owner hoặc sharing.

### 5.1. Thế nào là một “khoảng hở” ngoài mọi chain?

Khi có nhiều chain, nếu **tất cả** đều khai báo `securityMatcher` hạn chế và không có fallback:

```text
Chain 1: /admin/**
Chain 2: /api/**
Chain 3: /ui/**

GET /debug
  -> không khớp chain nào
  -> FilterChainProxy không áp dụng các security filters
```

Nếu controller `/debug` tồn tại, nó có thể bị truy cập mà không qua Spring Security. Đây không phải “403 mặc định”: **không có chain để thực thi bất kỳ rule `denyAll` nào**.

Fallback không khai báo `securityMatcher`, với `anyRequest().denyAll()` sau các ngoại lệ đã được kiểm soát, giúp tránh lỗ hổng này. Ngoài ra cần kiểm tra filter registration và những trường hợp framework hoặc proxy chuyển hướng route sang đường khác.

### 5.2. Chain quá rộng đứng đầu

Ví dụ cấu hình sai:

```text
@Order(1) WEB CHAIN
  securityMatcher("/**")
  anyRequest().authenticated()

@Order(2) ADMIN CHAIN
  securityMatcher("/admin/**")
  anyRequest().hasRole("ADMIN")
```

Với `GET /admin/audit`, chain WEB đầu tiên đã match, nên chain ADMIN không chạy. Nếu đã đăng nhập thông thường, user có thể vào endpoint nếu không có chốt khác. Không thể trông chờ rule admin ở chain phía sau “đè lên” chain trước.

**Sửa:** đặt chain hẹp/nhạy cảm trước; fallback bao trùm cuối; kiểm thử thứ tự thực tế, không chỉ nhìn có `hasRole("ADMIN")` trong source code.

### 5.3. `anyRequest().authenticated()` không phải lựa chọn thay `denyAll()`

Trong fallback, nếu dùng:

```text
/ui/** -> authenticated
anyRequest -> authenticated
```

mọi URL mới như `/private/export` có thể trở thành truy cập được đối với bất kỳ user đã đăng nhập. Khi ưu tiên “mặc định từ chối”, nên khai báo các đường đã phê duyệt rồi `denyAll()` phần còn lại.

## 6. Các cơ chế xác thực và cách quản lý trạng thái khác nhau

### 6.1. API: access token và phạm vi của resource server

JWT resource server kiểm tra token qua `JwtDecoder`, bao gồm cấu hình chữ ký/issuer và các điều kiện cần thiết như audience/expiry. Sau khi xác thực, bộ chuyển đổi tạo `Authentication` và authorities, thường biến scope `reports.read` thành `SCOPE_reports.read`.

Một token hợp lệ dành cho một API khác không được xem là quyền truy cập API này chỉ vì chữ ký đúng. Không tin role từ raw `Authorization` header trước khi token được xác minh. Nếu API nhận nhiều issuer, cần chỉ rõ trust của từng issuer và mapping phù hợp.

Khi API yêu cầu quyền trên từng tài nguyên, authority chỉ là điều kiện chức năng: method/service/repository vẫn phải kiểm tra tenant, owner, trạng thái và hạn mức.

### 6.2. UI: form login và CSRF

UI thường sử dụng session cookie. Trình duyệt có thể tự gửi cookie trong request, kể cả trong một số tình huống bị kích hoạt từ trang khác; vì vậy với hành động thay đổi trạng thái cần kiểm soát CSRF theo chính sách ứng dụng.

CSRF token giúp chứng minh request xuất phát từ luồng được phép của ứng dụng; **không cấp thêm quyền nghiệp vụ**. Người có CSRF token nhưng không có quyền sửa hồ sơ vẫn phải bị service chặn. Không được kết luận `GET` luôn an toàn nếu ứng dụng lại thực hiện ghi dữ liệu qua GET; hãy thiết kế các hành động thay đổi trạng thái dùng method và bảo vệ phù hợp.

### 6.3. Admin: đăng nhập không đồng nghĩa quản trị

Một admin có thể dùng cùng form login UI nhưng phải có quyền quản trị được cấp rõ ràng, có phạm vi và thời hạn. Với thao tác nhạy cảm, còn có thể cần MFA/step-up xác thực, kiểm soát phiên mạnh hơn, ghi audit, phê duyệt độc lập và giới hạn network nếu phù hợp.

Những điều kiện ấy không tự có khi tách `/admin/**` thành một `SecurityFilterChain`. Chain admin phải được cấu hình và test theo mục tiêu đe dọa thực tế.

### 6.4. CORS, CSRF và session là những quyết định khác nhau

| Cơ chế | Nó giải quyết gì? | Nó không chứng minh gì? |
| --- | --- | --- |
| CORS | Trình duyệt được phép đọc response cross-origin theo chính sách | Không chứng minh user có permission |
| CSRF | Giảm nguy cơ request đổi trạng thái bị trình duyệt gửi ngoài ý muốn với credential tự động | Không thay object authorization |
| Authentication | Danh tính/credential được xác minh | Không tự cho phép mọi hành động |
| Authorization | User được thực hiện chức năng/tài nguyên nào | Không thay validation dữ liệu |
| Session policy | Cách sử dụng phiên cho SecurityContext | Không tự tắt mọi session logic khác |
| JWT validation | Xác minh token do issuer tin cậy cấp cho API | Không tự đảm bảo quyền với mọi object |

Việc tách chain giúp chọn các cơ chế phù hợp từng vùng, nhưng không thay thế kiểm tra lẫn nhau giữa các cơ chế.

## 7. Một ví dụ Java 17 độc lập: mô phỏng cách chọn đúng một chain

Trước khi cấu hình Spring Security, dùng Java thuần để kiểm chứng trực giác về **first matching chain**, ba nguồn danh tính và fallback. Ví dụ này **không mô phỏng toàn bộ Spring Security**, không xác thực thật token hay session, và không dùng thư viện ngoài JDK.

Lưu file `FilterChainScopeDemo.java`:

```java
import java.util.Set;

public class FilterChainScopeDemo {
    enum Chain { ADMIN, API, WEB }

    record Request(
        String method,
        String path,
        boolean sessionAuthenticated,
        boolean bearerValidated,
        Set<String> authorities
    ) {}

    static boolean inZone(String path, String zone) {
        return path != null
            && (path.equals(zone) || path.startsWith(zone + "/"));
    }

    // Mô phỏng @Order: admin -> api -> web fallback.
    static Chain selectChain(String path) {
        if (inZone(path, "/admin")) {
            return Chain.ADMIN;
        }
        if (inZone(path, "/api")) {
            return Chain.API;
        }
        return Chain.WEB;
    }

    static boolean allowed(Request request) {
        if (request == null || request.method() == null
                || request.path() == null
                || request.authorities() == null) {
            return false;
        }

        Chain selected = selectChain(request.path());

        return switch (selected) {
            case ADMIN ->
                request.sessionAuthenticated()
                    && request.authorities().contains("ROLE_ADMIN")
                    && "GET".equals(request.method())
                    && "/admin/audit".equals(request.path());

            case API ->
                request.bearerValidated()
                    && (
                        ("GET".equals(request.method())
                            && inZone(request.path(), "/api/reports")
                            && request.authorities()
                                .contains("SCOPE_reports.read"))
                        ||
                        ("POST".equals(request.method())
                            && "/api/reports".equals(request.path())
                            && request.authorities()
                                .contains("SCOPE_reports.write"))
                    );

            case WEB ->
                ("GET".equals(request.method())
                    && "/login".equals(request.path()))
                ||
                ("GET".equals(request.method())
                    && "/ui/dashboard".equals(request.path())
                    && request.sessionAuthenticated());
        };
    }

    static Request req(
            String method, String path,
            boolean session, boolean bearer,
            Set<String> authorities) {
        return new Request(
            method, path, session, bearer, authorities
        );
    }

    static void show(String label, Request request) {
        System.out.println(label + ": " + allowed(request));
    }

    public static void main(String[] args) {
        show("admin with admin session",
            req("GET", "/admin/audit", true, false,
                Set.of("ROLE_ADMIN")));

        show("admin missing role",
            req("GET", "/admin/audit", true, false,
                Set.of("ROLE_USER")));

        show("admin bearer only",
            req("GET", "/admin/audit", false, true,
                Set.of("ROLE_ADMIN")));

        show("api bearer read",
            req("GET", "/api/reports/17", false, true,
                Set.of("SCOPE_reports.read")));

        show("api UI session only",
            req("GET", "/api/reports/17", true, false,
                Set.of("SCOPE_reports.read")));

        show("api read scope cannot write",
            req("POST", "/api/reports", false, true,
                Set.of("SCOPE_reports.read")));

        show("ui session access",
            req("GET", "/ui/dashboard", true, false,
                Set.of("ROLE_USER")));

        show("ui bearer only",
            req("GET", "/ui/dashboard", false, true,
                Set.of("SCOPE_reports.read")));

        show("login page",
            req("GET", "/login", false, false,
                Set.of()));

        show("unknown route",
            req("GET", "/private/debug", true, false,
                Set.of("ROLE_ADMIN")));

        show("lookalike prefix",
            req("GET", "/api-admin/reports", true, true,
                Set.of("ROLE_ADMIN", "SCOPE_reports.read")));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac FilterChainScopeDemo.java
java FilterChainScopeDemo
```

Stdout dự kiến:

```text
admin with admin session: true
admin missing role: false
admin bearer only: false
api bearer read: true
api UI session only: false
api read scope cannot write: false
ui session access: true
ui bearer only: false
login page: true
unknown route: false
lookalike prefix: false
```

Điểm cần chú ý:

1. Người đã đăng nhập UI thông thường không vượt qua admin chain vì thiếu `ROLE_ADMIN`.
2. Dù mang chuỗi authority tên `ROLE_ADMIN`, một request chỉ có bearer identity cũng không qua được rule admin **trong mô hình này**; admin được yêu cầu session. Trong ứng dụng thật, cần xem các filter xác thực nào hoạt động trong chain và loại `Authentication` chúng chấp nhận.
3. API chỉ chấp nhận giả định `bearerValidated=true`. Đây là **cờ minh họa được xem như kết quả đã xác minh trên server**; không bao giờ đọc một cờ do client tự gửi thay cho xác thực token.
4. User có session UI không tự truy cập được API bearer-only.
5. Đường `/api-admin/reports` không thuộc `/api` hay `/admin` vì hàm `inZone` kiểm tra ranh giới `/`. Nó rơi vào fallback và bị deny.
6. Đường không biết mặc định bị từ chối. Trong Spring Security thật, điều kiện tương đương chỉ có tác dụng **nếu có chain fallback bao phủ request**.
7. Chương trình không có CSRF, JWT decoder, session persistence, proxy hoặc kiểm tra tenant/owner thật. Nó chỉ giúp luyện cách chọn chain và kiểm tra điều kiện cần.

### 7.1. Bài thực hành nhỏ trên ví dụ Java

Hãy thay đổi thứ tự `selectChain` để trả về `WEB` cho mọi request trước khi xét admin/API. Quan sát kết quả mô phỏng và giải thích vì sao một chain quá rộng đứng đầu sẽ khiến các chain sau không được chọn. Sau đó trả lại thứ tự an toàn.

Thêm `GET /admin`, `GET /api`, `POST /admin/audit`, `GET /api/reports/17?format=csv` theo cách mô hình hóa method/path rõ ràng. Với query, không ghép `?format=csv` vào path nếu đang muốn kiểm tra endpoint theo path: Servlet và Spring matcher phân biệt path với query.

## 8. Những lỗi xác thực xuyên chain và cách phòng tránh

### 8.1. Dùng lại form login cho API ngoài ý định

Nếu API chain chứa form login thay vì resource server hoặc dùng một chain fallback chưa tách đúng, API client thiếu token có thể nhận `302 Location: /login` kèm HTML. Client mong JSON lỗi 401 sẽ xử lý sai, và cũng có nguy cơ cookie phiên được dùng làm credentials ở endpoint không được thiết kế cho nó.

Giải pháp: xác định API chain bằng `securityMatcher`, cấu hình cơ chế xác thực phù hợp (bearer JWT/introspection), và test không dùng UI cookie để vượt qua API policy.

### 8.2. Đưa bearer token vào admin chain mà thiếu step-up

Có những hệ thống muốn quản trị qua API token; điều đó có thể hợp lệ, nhưng phải **thiết kế riêng** scope/audience, mức xác thực, giới hạn tài nguyên và khả năng thu hồi. Không nên tự cho phép một token phổ thông `SCOPE_reports.read` thực hiện admin chỉ vì nó có claim tên `admin` hoặc header client tự khai.

Nếu quản trị chỉ được qua web session như ví dụ, không thêm `oauth2ResourceServer` vào admin chain một cách vô thức. Nếu có yêu cầu API admin riêng, cân nhắc namespace rõ như `/api/admin/**` và permission cụ thể, kiểm tra thứ tự các chain và không nhầm với `/admin/**`.

### 8.3. Ưu tiên quyền “admin toàn cục” để chữa lỗi 403

Một user bị 403 ở admin route có thể do thiếu `ROLE_ADMIN`, sai chain, thiếu CSRF, chưa xác thực hoặc object policy. Không nên sửa bằng `.anyRequest().authenticated()` hoặc thêm `permitAll()`.

Hãy xác định request thực tế: đường nào, method nào, vào chain nào, Authentication có authority gì, CSRF có cần không, object nào đang được truy cập. Một HTTP 403 có thể là kết quả đúng của nghiệp vụ hoặc của CSRF, không đủ để chẩn đoán nếu thiếu dữ kiện.

### 8.4. Coi `@Order` là điều kiện quyền

`@Order(1)` nghĩa là chain được xét **trước**, không phải “mức quyền 1 cao hơn”. Người dùng không có “order” tương ứng; họ có Authentication/authorities do cơ chế xác thực cấp và chính sách resource. Khi tách chain, phải giữ rõ thứ tự chọn route và biểu thức permission riêng.

## 9. Ngữ cảnh request và các trường hợp không chỉ có một lượt xử lý

### 9.1. Servlet dispatch và đường đích nội bộ

Một HTTP request có thể có các lượt `REQUEST`, `FORWARD`, `ERROR`, `ASYNC` hoặc `INCLUDE` tùy Servlet flow. Nếu filter proxy được gọi lại ở một lượt dispatch, đường đích và dispatcher type có thể khác; kết quả chọn chain cũng có thể khác.

Ví dụ request ban đầu `/ui/reports` được cho phép theo UI chain, rồi MVC forward tới `/WEB-INF/views/reports.jsp`. Đích nằm ngoài `/ui/**`; nếu filter proxy xử lý lượt FORWARD, chain fallback có thể được áp dụng. Quy tắc `denyAll()` quá rộng có thể khiến view không hiển thị dù request gốc hợp lệ.

Có thể thiết kế ngoại lệ **có phạm vi** cho internal view/error dispatch, hoặc dùng `dispatcherTypeMatchers(...)` khi nghiệp vụ cho phép, nhưng phải hiểu:

- Không được dùng “mọi FORWARD đều permitAll” như cách bỏ qua quyền cho handler nghiệp vụ nhạy cảm.
- Những lượt dispatch thực sự qua filter nào phụ thuộc đăng ký filter, `OncePerRequestFilter` và cấu hình Servlet/container.
- Request trực tiếp `REQUEST` vào đường nhạy cảm không được phép chỉ vì cùng path từng là đích FORWARD.
- Method/object policy vẫn cần bảo vệ hành động nhạy cảm khi được gọi qua một entrypoint khác.

### 9.2. Reverse proxy và context path

Nếu ứng dụng được công bố tại `/portal/api/reports`, proxy có thể rewrite thành `/api/reports` trước khi chuyển tới Servlet. Hoặc ứng dụng có context path `/portal`. Matcher cần hiểu **đường mà Servlet thật nhìn thấy**, không tự suy đoán từ URL browser.

Thử các trường hợp root path, slash cuối, URL encoding, servlet mapping, proxy prefix và endpoint như `/api-admin` hoặc `/administrator`. Đừng tự làm matcher bằng `getRequestURI().startsWith("/api")`: nó có thể match cả `/api-admin` hoặc sai khi có context path.

### 9.3. Browser có thể gửi cả cookie và Authorization header

Một request từ trình duyệt có thể đồng thời mang cookie session và `Authorization: Bearer ...`. Phần nào được chấp nhận phụ thuộc **chain được chọn và các filter đã cấu hình**. Không quyết định quyền theo header thô kiểu “có Authorization nghĩa là API”, vì attacker có thể gắn header tùy ý.

Với chính sách API bearer-only, phải test rằng cookie UI không được dùng để tạo Authentication cho API. Với admin session-only, phải test bearer token không thay thế session ngoài ý định. Nếu cùng một endpoint cố hỗ trợ nhiều cơ chế auth, hãy thiết kế rõ thứ tự, ranh giới và quyền của từng cơ chế thay vì để hành vi ngẫu nhiên của filter quyết định.

## 10. Testing: chứng minh không có khoảng hở hoặc giao thoa quyền

### 10.1. Ma trận quan trọng

| Request / tình huống | Chain mong đợi | Điều phải chứng minh |
| --- | --- | --- |
| `GET /admin/audit` | Admin | Cần admin role; user thường 403 |
| `POST /admin/users/42/disable` | Admin | Role + CSRF + policy |
| `GET /api/reports/17` với access token hợp lệ | API | Scope đúng, tenant đúng |
| Cùng API chỉ mang cookie UI | API | Không tự coi session UI là bearer authentication |
| Cùng API không token | API | Không redirect HTML login ngoài ý định |
| API token sai issuer/audience | API | Decoder từ chối |
| API token chỉ có read scope gọi POST | API | Từ chối |
| `GET /ui/dashboard` chưa login | UI | Chuyển login theo cơ chế UI |
| `POST /ui/profile` thiếu CSRF | UI | Bị chặn, không sửa dữ liệu |
| `GET /login` | UI | Trang login tồn tại theo cơ chế đã chọn |
| `POST /login` hợp lệ/không hợp lệ | UI | Xử lý trong chain chứa authentication filter |
| `POST /logout` với CSRF phù hợp | UI | Đăng xuất đúng cơ chế |
| `GET /assets/app.css` | UI/fallback | Public nhưng vẫn có filter bảo vệ chung |
| `GET /unknown` | UI/fallback | Mặc định deny |
| `GET /api-admin/...` | UI/fallback | Không nhầm prefix API |
| `GET /admin` | Admin | Root vùng admin không lọt qua fallback |
| Các request FORWARD/ERROR | Chain theo lượt dispatch | Không vô tình bypass handler nhạy cảm |
| Một endpoint được gọi từ job thay vì HTTP | Không qua HTTP filter | Service/object policy vẫn áp dụng |

### 10.2. MockMvc cho ba nguồn danh tính

Dưới đây là các **mảnh ghép test tích hợp**, giả định ứng dụng đã cấu hình `MockMvc`, controller, Spring Security Test, dữ liệu và security beans phù hợp. Chúng không phải chương trình độc lập và không xác minh chữ ký JWT thật.

Ví dụ JWT test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/reports/17")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Trong đoạn test, `SimpleGrantedAuthority` cần import từ `org.springframework.security.core.authority.SimpleGrantedAuthority`. Kết quả 200 chỉ đúng nếu fixture báo cáo 17 thuộc phạm vi principal, controller tồn tại và mọi policy khác cho phép. `jwt()` mock helper **không chứng minh `JwtDecoder` đã kiểm tra chữ ký/issuer/audience**; cần test riêng tầng decoder và tích hợp xác thực thật.

Ví dụ admin session principal giả lập:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/admin/audit")
        .with(user("admin").roles("ADMIN")))
    .andExpect(status().isOk());

mockMvc.perform(get("/admin/audit")
        .with(user("reader").roles("USER")))
    .andExpect(status().isForbidden());
```

Đây là ví dụ với fixture cho phép truy cập audit; thực tế còn có thể bị chặn bởi method/data policy. Với request `POST /admin/**` hoặc `POST /ui/**` nếu CSRF bật, bổ sung `.with(csrf())` trong test **khi cần cô lập điều kiện authorization**. Tách test CSRF thiếu token thành ca riêng. Nếu không, 403 có thể do CSRF chứ chưa chứng minh role rule hoạt động.

### 10.3. Test chọn chain, không chỉ test response

Có thể dùng cơ chế quan sát Spring Security trong môi trường test để xác minh filter chain nào được chọn cho các route. Không đủ chỉ viết test “API trả 403”; nó có thể trả 403 vì **web fallback deny**, trong khi API chain dự kiến chưa từng được áp dụng. Nên kiểm tra chính xác ranh giới chain, authentication filter và response type.

Khi kiểm thử lỗi cấu hình có chủ đích:

1. Đặt fallback matcher rộng ở `@Order(1)` và chứng minh test phát hiện admin/API không còn được chọn.
2. Bỏ chain fallback và kiểm tra request ngoài mọi chain bị bỏ qua, từ đó hiểu vì sao cần fallback trong cấu hình thật.
3. Đặt form login trong một chain chỉ match `/ui/**` mà không có `/login`; kiểm tra endpoint login có hoạt động hay không.
4. Cho UI cookie đi tới API; xác minh API không chấp nhận nó khi đã thiết kế bearer-only.
5. Tạo user có `ROLE_USER`, không có `ROLE_ADMIN`, vào admin; xác minh không có side effect.
6. Kiểm tra admin root `/admin`, API root `/api` và đường trông gần giống như `/api-admin`.

**Đừng áp dụng cấu hình lỗi có chủ đích lên môi trường sản xuất.** Đây là tình huống kiểm thử ở môi trường riêng để xác nhận test suite đủ nhạy.

### 10.4. Kiểm thử nguồn và vòng đời quyền

Khi user bị thu hồi role admin, một session đã tạo trước đó có thể giữ authorities cũ tùy kiến trúc. Khi token JWT chứa scope cũ vẫn còn hạn, API có thể tiếp tục chấp nhận đến khi hết hạn hoặc có cơ chế thu hồi bổ sung.

Tách chain không tự giải quyết vấn đề quyền lỗi thời. Với quyền quản trị, cần thời hạn phiên, step-up, revocation hoặc kiểm tra quyền động thích hợp với rủi ro. Với API, cần giới hạn token, audience, scope, khóa ký, issuer và cache policy đúng cách. Test tác động của việc gỡ role ngay trước một tác vụ nhạy cảm.

## 11. Lỗi cấu hình thường gặp

| Sai lầm | Rủi ro | Cách giải quyết |
| --- | --- | --- |
| Không có fallback chain | URL không khớp chain nào có thể không qua Spring Security | Đặt fallback bao phủ cuối |
| Fallback `/**` ưu tiên cao | API/admin chain không bao giờ được chọn | `@Order` hẹp trước, fallback cuối |
| Nhầm `securityMatcher` và `requestMatchers` | Tưởng denyAll bảo vệ ngoài chain | Kiểm tra phạm vi chain riêng |
| Dùng `authenticated()` cho tất cả admin | User UI thường được vào admin | `ROLE_ADMIN` và object policy |
| Dùng cookie UI để auth API ngoài ý định | Thay đổi ranh giới xác thực, nguy cơ CSRF | Bearer-only API chain, test rõ |
| Tắt CSRF toàn ứng dụng vì API stateless | Form/admin session có thể bị CSRF | Tắt theo đúng chain bearer-only |
| Dùng `STATELESS` để tuyên bố toàn ứng dụng không có session | UI/admin cần session, custom code có thể tạo | Phân biệt policy theo chain |
| Đặt form login trong chain không match `/login` | Login handler không chạy | Chain bao phủ URL của filter |
| API không token bị redirect HTML | Client xử lý lỗi sai | Authentication entry point theo API |
| Role `ADMIN` không tương ứng `ROLE_ADMIN` | Từ chối sai hoặc cấu hình workaround nguy hiểm | Chuẩn hóa GrantedAuthority |
| Cho mọi request chưa đăng ký được `authenticated()` | Endpoint mới bất ngờ mở cho user thường | Default deny |
| Tin header `X-Role` hoặc host chưa chuẩn hóa | Giả mạo ranh giới admin | Xác thực principal và trust proxy |
| Chỉ kiểm tra quyền HTTP | IDOR/BOLA, job bypass | Method/object authorization |
| Không test endpoint login/logout/CSRF | Không thể đăng nhập, lỗi 403 khó hiểu | Test luồng xác thực thật |
| Không test root và prefix gần giống | `/api`, `/admin` hoặc `/api-admin` lọt sai chain | Test path boundary |
| Đăng ký custom filter cả ở servlet lẫn chain | Có thể chạy trùng hoặc sai thứ tự | Kiểm tra filter registration và chain |
| Dựa vào lỗi 403 để kết luận chain đúng | Fallback có thể đang chặn thay API policy | Kiểm tra chain được chọn và nguyên nhân |
| Tin rằng token/session tự thu hồi khi đổi role | Quyền cũ vẫn tồn tại đến khi refresh/revoke | Thiết kế lifecycle/revocation |

## 12. Bài tập thực hành

### Bài 1 — Vẽ bảng chọn chain

Liệt kê `/admin`, `/admin/audit`, `/api`, `/api/reports`, `/ui/dashboard`, `/login`, `/logout`, `/assets/app.css`, `/api-admin/foo` và `/unknown`. Với thứ tự admin → API → fallback, ghi chain được chọn và rule tương ứng. Giải thích vì sao `/api-admin/foo` không được coi là API.

### Bài 2 — Chạy Java 17

Biên dịch `FilterChainScopeDemo.java`, kiểm tra 11 dòng stdout. Thêm case `GET /admin`, `GET /api` và admin user có bearer token nhưng không có session. Sửa mô hình để admin phải có cả session và cờ step-up đã được server xác minh; thử case đủ/thiếu step-up.

### Bài 3 — Triển khai ba chain trong Spring

Dùng mã cấu hình mẫu làm khởi đầu, bổ sung auth provider UI, JWT decoder API và controller đơn giản. Xác nhận các chain chỉ xử lý đúng phạm vi. Tạo test cho response khác nhau khi API thiếu bearer token và UI chưa đăng nhập.

### Bài 4 — Chống lỗi lộ admin từ fallback

Cố tình đưa `@Order(1)` vào fallback rộng với `anyRequest().authenticated()`, kiểm tra test admin user thường có bắt được nguy cơ không. Khôi phục thứ tự đúng và dùng `denyAll()` cho request ngoài danh sách.

### Bài 5 — CSRF và luồng đăng nhập

Viết test `POST /ui/profile` thiếu CSRF token phải bị chặn; có CSRF nhưng thiếu quyền object cũng bị chặn. Kiểm tra `POST /login` và `POST /logout` theo cơ chế và token thực tế. Giải thích vì sao chỉ disable CSRF cho bearer-only API không nên ảnh hưởng web/admin.

### Bài 6 — Quyền theo tài nguyên

Tạo hai tenant. User admin tenant A cố sửa user tenant B; API client có `SCOPE_reports.read` đọc report của tenant khác; UI user cố sửa hồ sơ người khác. Viết service/repository policy để cả ba trường hợp bị từ chối dù HTTP chain đã khớp và có quyền chức năng.

### Bài 7 — Kiểm thử nâng cấp và triển khai sau reverse proxy

Đặt ứng dụng dưới context path hoặc proxy rewrite; kiểm tra `/api`/`/admin` root, trailing slash, route login và đường lỗi. Xác minh `FilterChainProxy` chọn cùng ý định chính sách trong môi trường gần production; không dựa hoàn toàn vào URL hiển thị ở browser.

## 13. Checklist trước khi lên production

- [ ] Có sơ đồ phạm vi API/UI/admin và các đường dành cho auth, callback, static, lỗi.
- [ ] Mọi route khớp một chain có bảo vệ; fallback luôn đứng cuối.
- [ ] `@Order` và `securityMatcher` không tạo overlap ngoài chủ đích.
- [ ] Route root và các biến thể path được kiểm thử.
- [ ] API chấp nhận đúng cơ chế token, validate issuer/audience/scope, không tự dùng UI cookie ngoài ý định.
- [ ] UI có form login/session phù hợp, CSRF vẫn hoạt động với unsafe methods.
- [ ] Admin yêu cầu role/permission riêng và kiểm soát hành động nhạy cảm/tenant.
- [ ] Login, logout, error và callback được chain chứa filter tương ứng bao phủ.
- [ ] `anyRequest().denyAll()` chặn các endpoint chưa phê duyệt trong fallback.
- [ ] Không dùng header/host/URL tự khai làm bằng chứng cấp quyền.
- [ ] Các phương thức service và truy vấn dữ liệu kiểm tra object policy.
- [ ] Có ca test cho thiếu auth, sai role, sai scope, thiếu CSRF, khác tenant.
- [ ] Đã kiểm tra FORWARD/ERROR/ASYNC dispatch nếu app sử dụng.
- [ ] Log có request correlation, path/method, chain và kết quả ở mức không rò rỉ secret.
- [ ] Có kế hoạch thu hồi token/session, key rotation, audit và review phân quyền.

## 14. Câu hỏi tự kiểm tra

1. **Có bao nhiêu chain chạy khi hai `SecurityFilterChain` cùng match một request?** Trong một lần chọn của `FilterChainProxy`, chỉ chain khớp đầu tiên.
2. **`securityMatcher` khác `requestMatchers` thế nào?** Cái đầu chọn toàn bộ chain; cái sau chọn rule trong chain.
3. **Nếu mọi chain đều giới hạn path và `/debug` không khớp, `denyAll()` ở API chain có bảo vệ nó không?** Không; cần fallback.
4. **Vì sao admin chain nên được chọn trước fallback?** Fallback quá rộng có thể chiếm request trước khi rule admin được thực thi.
5. **UI login thành công có cho quyền admin tự động không?** Không; còn phải có `ROLE_ADMIN` và policy nghiệp vụ.
6. **API bearer-only có nên chấp nhận UI cookie?** Không, nếu chính sách đã thiết kế bearer-only; phải kiểm thử thực tế.
7. **`SessionCreationPolicy.STATELESS` có nghĩa tắt CSRF mọi nơi không?** Không; CSRF phụ thuộc cơ chế browser tự gửi credential và phạm vi endpoint.
8. **Vì sao `GET /login` cần được chain thích hợp nhận?** Form login filter có thể tạo/xử lý endpoint login; matcher loại trừ nó sẽ khiến chức năng không hoạt động.
9. **Một request API thiếu token nên trả trang HTML login không?** Thường không; API nên dùng entrypoint/phản hồi phù hợp client, như 401.
10. **Có `SCOPE_reports.read` là được đọc mọi báo cáo không?** Không; còn quyền theo tenant, owner và object.
11. **Tại sao cần test `/api-admin/foo`?** Để phát hiện matcher prefix tự viết quá rộng và tránh chọn sai vùng.
12. **403 có chứng minh admin chain đúng không?** Không; có thể là fallback deny hoặc lỗi CSRF. Cần xác nhận chain/rule thật.
13. **Một `@Order(1)` có khiến người dùng mạnh quyền hơn không?** Không; nó chỉ ưu tiên chọn chain.
14. **Khi hệ thống thêm OAuth2 login callback hoặc SAML endpoint, cần xem gì?** Phạm vi chain chứa auth filter/callback, path/entrypoint, CSRF và test.
15. **Khi quyền admin bị thu hồi, có thể tin session cũ tự mất role ngay không?** Không mặc định; phải có chính sách refresh/revoke/quyền động.

**Ghi nhớ:** tách `SecurityFilterChain` là cách xác định **vùng nào chạy bộ lọc và cơ chế xác thực nào**, chứ không phải tạo ba “lớp quyền” tự động cộng dồn. Thiết kế an toàn cần **chain cụ thể trước, fallback cuối; đúng entrypoint đăng nhập; API/UI/admin dùng cơ chế phù hợp; CSRF không bị mở rộng/tắt nhầm; và quyền theo tài nguyên vẫn được kiểm tra ở service/data**.

### Tài liệu chính thức

- [Spring Security 6.5 – Java Configuration và Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security – Servlet Architecture / FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)