# Tài nguyên tĩnh, trang công khai và endpoint quản trị trong Spring Security

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot có cả trang HTML, CSS, JavaScript và các API nghiệp vụ. Người chưa đăng nhập cần mở được trang chủ, trang đăng nhập và ảnh/logo để giao diện hiển thị; người dùng đã đăng nhập được vào trang cá nhân; chỉ quản trị viên mới được truy cập trang và API quản trị. Nếu cấu hình quyền HTTP thiếu chặt chẽ, hai vấn đề trái ngược dễ xảy ra:

- **Chặn nhầm dữ liệu công khai:** trang đăng nhập tải được nhưng CSS/JS bị trả 401/403, khiến trang vỡ giao diện; favicon bị chặn; người chưa có tài khoản không thể mở trang đăng ký.
- **Mở nhầm dữ liệu nội bộ:** đặt `/api/**.permitAll()` quá rộng; để `/admin/**.hasRole("ADMIN")` sau một matcher `/****` dễ dãi; hoặc bỏ hẳn filter chain đối với cả thư mục chứa file người dùng tải lên.

Bài học tập trung vào ba nhóm cần phân biệt:

1. **Tài nguyên tĩnh** (*static resources*): CSS, JavaScript, ảnh, font, favicon… được server công bố công khai.
2. **Trang/endpoint công khai** (*public pages/endpoints*): trang chủ, About, GET login, GET register, một số API public có chủ đích.
3. **Trang/endpoint quản trị** (*administrative endpoints*): xem người dùng, thay đổi cấu hình, duyệt/xuất báo cáo, thao tác nhạy cảm; yêu cầu quyền ở server.

Sau bài này, bạn sẽ biết cách dùng `authorizeHttpRequests`, `requestMatchers`, `permitAll`, `authenticated`, `hasRole` và `hasAuthority` một cách có thứ tự; chọn `permitAll` thay vì bỏ qua chuỗi filter khi phục vụ static asset; xử lý login/CSRF/CORS; bảo vệ endpoint quản trị, nhiều filter chain và quyền trên đối tượng; đồng thời viết test bảo đảm không vô tình mở API nhạy cảm.

**Ngữ cảnh:** ví dụ dùng Spring Security trên **Servlet/Spring MVC**, Java 17+, cú pháp `SecurityFilterChain` và `HttpSecurity` phổ biến ở Spring Security 6.x/7.x. Spring WebFlux dùng API khác; khi tích hợp, đối chiếu đúng phiên bản Spring Security được project thực sự giải quyết bằng BOM/Gradle/Maven.

## 2. Bảng phân loại và nguyên tắc thiết kế

| Loại request | Ví dụ | Quyết định HTTP cơ sở | Lưu ý |
| --- | --- | --- | --- |
| CSS/JS/ảnh/font công khai | `GET /css/site.css`, `GET /js/app.js`, `GET /images/logo.svg` | `permitAll()` | Giữ request trong security filter chain |
| Trang công khai | `GET /`, `GET /about` | `permitAll()` | Chỉ những method/path đã công bố |
| Trang đăng nhập | `GET /login` | `permitAll()` | Controller/view phải tồn tại nếu dùng custom login page |
| Đăng ký công khai | `GET /signup`, `POST /signup` | Có thể `permitAll()` theo API contract | POST vẫn cần kiểm tra CSRF khi áp dụng, validation và chống lạm dụng |
| Trang người dùng | `GET /app/profile` | `authenticated()` | Đã đăng nhập chưa đủ để đọc hồ sơ của người khác |
| Trang quản trị | `GET /admin/users` | `hasRole("ADMIN")` | Theo prefix mặc định cần `ROLE_ADMIN` |
| API quản trị | `GET /api/admin/users` | `hasRole("ADMIN")` và policy phù hợp | UI ẩn nút không thay thế server authorization |
| Export có độ nhạy cao | `GET /api/admin/reports/export` | Role + permission khi policy đòi cả hai | Điều kiện nên được kết hợp bằng **AND** |
| URL không nằm trong danh mục | `GET /internal/debug` | `denyAll()` | Mặc định từ chối thay vì tự mở |

Một hệ thống thường không nên mặc định tất cả `/api/**` cần `authenticated()` rồi coi như đã bảo vệ xong: route quản trị và các hành động nhạy cảm cần quyền cụ thể. Cũng không nên dùng role ADMIN để mặc nhiên bỏ qua ranh giới tenant hoặc owner.

### 2.1. Public khác anonymous-only

`permitAll()` cho phép cả **người chưa đăng nhập lẫn người đã đăng nhập** đi qua điều kiện authorization đó. Nếu nghiệp vụ chỉ muốn người chưa xác thực mở một route (ví dụ trang giới thiệu đăng nhập), có thể cân nhắc `anonymous()`, nhưng đừng nhầm nó với `permitAll`. Trong nhiều sản phẩm, trang giới thiệu vẫn công khai cho tất cả, còn UI có thể tự chuyển hướng khi đã đăng nhập.

### 2.2. Được phép đi qua rule không có nghĩa nội dung chắc chắn tồn tại

`permitAll()` chỉ cho phép qua **authorization check**, không tự tạo file `site.css` hoặc controller `/about`. Nếu asset không được đóng gói hay mapping sai, HTTP có thể trả 404 dù phân quyền đúng. Nếu request có filter khác chặn (CSRF, CORS, rate limit...), nó vẫn có thể bị từ chối.

## 3. Tài nguyên tĩnh: vì sao nên dùng permitAll thay cho ignoring?

### 3.1. Cách làm được Spring Security khuyến nghị

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/css/**",
        "/js/**",
        "/images/**",
        "/fonts/**",
        "/favicon.ico"
    ).permitAll()
    .anyRequest().authenticated()
);
```

Đây là **mảnh cấu hình** dùng trong `SecurityFilterChain`, không phải file Java chạy độc lập. Các pattern phải tương ứng với URL static asset thực tế của ứng dụng.

Với `permitAll`, request **vẫn đi qua security filter chain**, nhưng không bị yêu cầu một quyền truy cập riêng ở bước HTTP authorization. Các chức năng trong chain như security headers và các cơ chế bảo vệ được cấu hình vẫn có thể hoạt động. Theo tài liệu Spring Security, từ dòng 6 trở đi, `permitAll` không cần truy xuất `Authentication` từ session cho trường hợp không yêu cầu quyền, giúp giảm lý do tối ưu hóa bằng cách bỏ filter.

**Vì vậy, với tài nguyên tĩnh công khai, mặc định hãy ưu tiên `permitAll()`.**

### 3.2. Vì sao `web.ignoring()` không tương đương?

Một cấu hình `WebSecurityCustomizer` kiểu cũ có thể chứa:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
            .requestMatchers("/css/**", "/js/**");
}
```

Đây là **ví dụ để nhận diện hành vi**, không phải cấu hình được khuyến nghị cho tình huống thông thường. Khi request bị `ignoring`, Spring Security **bỏ qua các security filter** với request đó. Nếu ứng dụng dựa vào chain để thêm security headers, chúng có thể không được áp dụng cho tài nguyên bị bỏ qua.

Không nên lập luận "CSS không bí mật nên bỏ filter hoàn toàn luôn an toàn". Các header bảo mật, cấu hình response và các filter chuyên biệt của ứng dụng có thể vẫn có ý nghĩa với nội dung công khai. Chỉ bỏ qua filter cho một tập request khi có yêu cầu kiến trúc đặc biệt được phân tích, chứ không dùng như cách chữa lỗi CSS 403.

| Phương án | Authorization rule | Security filter chain | Khi nào cân nhắc |
| --- | --- | --- | --- |
| `permitAll()` | Bỏ yêu cầu xác thực/quyền ở rule này | **Vẫn chạy** các filter được cấu hình | **Mặc định** cho static asset và public page |
| `web.ignoring()` | Không được xử lý bởi Spring Security | **Bỏ qua** chain cho matcher | Trường hợp ngoại lệ rất cụ thể, có đánh giá bảo mật |
| `securityMatcher` giới hạn chain | Rule chỉ có hiệu lực trong chain khớp | Request ngoài chain có thể không được chain đó bảo vệ | Chỉ khi thiết kế nhiều chain và có fallback rõ ràng |

### 3.3. Nguồn static thường gặp trong Spring Boot

Khi sử dụng cấu hình phục vụ static resources mặc định của Spring Boot/Spring MVC, tài nguyên thường được phục vụ từ các vị trí classpath như:

```text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
```

Ví dụ file `src/main/resources/static/css/site.css` thường được truy cập qua URL `/css/site.css`, **không phải** qua `/static/css/site.css`. Tuy nhiên, nếu app thay đổi static path pattern, resource handler, context path hoặc servlet mapping, URL thực có thể khác. Hãy lấy URL từ cấu hình đang dùng và test request thực.

**Không nhầm đường dẫn thư mục và đường dẫn URL.** Việc có thư mục tên `static` không đảm bảo matcher `/static/**` sẽ bảo vệ đúng các request đến `/css/**`.

### 3.4. Dùng tiện ích PathRequest trong Spring Boot khi phù hợp

Trong **Spring Boot Servlet** có tiện ích `PathRequest.toStaticResources().atCommonLocations()` để nhận diện các vị trí static phổ biến:

```java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Trong authorizeHttpRequests:
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
```

Tiện ích này **thuộc Spring Boot**, không phải API độc lập của Spring Security core. Nó chỉ áp dụng các loại địa điểm được tiện ích xác định; có thể không bao phủ đường dẫn resource handler tùy chỉnh, file upload hay CDN của dự án. Nếu cần kiểm soát rõ từng URL, dùng matcher cụ thể như `/css/**`, `/js/**`, `/images/**` và kiểm thử.

### 3.5. Không đưa file riêng tư vào vùng public

Nếu hệ thống có:

```text
/uploads/
  ├─ invoices/customer-17.pdf
  └─ employee-profiles/private-photo.jpg
```

**Không** đưa `/uploads/**` vào danh sách `permitAll` chỉ vì file được truy cập bằng URL giống tài nguyên tĩnh. File do người dùng tải lên có thể chứa thông tin nhạy cảm và cần quyền theo user/tenant/resource. Sử dụng service tải file có object-level authorization, lưu trữ private hoặc URL được ký có thời hạn và giới hạn phù hợp.

Lỗ hổng phổ biến: ẩn một đường link trên giao diện nhưng vẫn cho bất kỳ người nào gọi URL trực tiếp để tải dữ liệu. Tên file khó đoán/UUID không thay thế kiểm tra quyền. Quy tắc tài nguyên tĩnh public chỉ áp dụng với asset **được công bố công khai có chủ đích**.

## 4. Trang công khai: cấu hình theo path và HTTP method

Trang công khai không đồng nghĩa mọi hành động trên cùng path đều public theo nghĩa nghiệp vụ. Một trang `GET /signup` hiển thị form, còn `POST /signup` tạo tài khoản: cả hai có thể không yêu cầu login nhưng POST vẫn cần chống CSRF khi ứng dụng dùng cookie/session, kiểm tra input, rate limit và chống lạm dụng.

### 4.1. Công khai đúng những trang cần công khai

```java
.requestMatchers(HttpMethod.GET,
    "/", "/about", "/help", "/login", "/signup"
).permitAll()

.requestMatchers(HttpMethod.POST, "/signup").permitAll()
```

Các matcher trên minh họa:

- Khách chưa đăng nhập được xem trang chủ và trang login/register.
- Mở công khai **POST signup là quyết định nghiệp vụ rõ ràng**; nó không có nghĩa bỏ validation, CSRF hay chống spam.
- Các method không được liệt kê trên `/signup` không tự động được cấp quyền từ matcher GET/POST nếu có fallback `denyAll`.

### 4.2. Custom login page cần cả GET lẫn xử lý POST

Khi dùng form login, trang `GET /login` do ứng dụng render có thể được khai báo public, còn request xử lý thông tin đăng nhập `POST /login` thông thường do Spring Security authentication filter nhận. Ví dụ:

```java
http.formLogin(form -> form
    .loginPage("/login")
    .permitAll()
);
```

- `loginPage("/login")` chỉ định URL trang đăng nhập tùy chỉnh. **Ứng dụng phải có controller/view** để trả trang này; nếu không có, có thể gặp 404 hoặc redirect loop.
- `permitAll()` trong cấu hình form login cho phép truy cập các URL liên quan đến đăng nhập theo cách cấu hình đó.
- Authentication filter xử lý thông tin xác thực; `permitAll` **không đồng nghĩa** user đã được xác thực.
- Khi CSRF đang bật, form POST login cần token CSRF hợp lệ. Hãy dùng template/tag hỗ trợ hoặc gửi token đúng cơ chế repository, đừng tắt CSRF để login thử cho dễ.

Nếu thay `loginProcessingUrl`, đồng bộ HTML `action` và test route mới. Khi form login chưa được cấu hình mà dùng default login page, Spring Security có thể sinh trang đăng nhập mặc định; đừng gán giả định đó cho custom login page.

### 4.3. Public API vẫn phải có policy nghiệp vụ

Ví dụ `GET /api/catalog` công khai đọc sản phẩm; `POST /api/catalog` yêu cầu quản trị viên tạo sản phẩm. Sai lầm thường thấy là:

```java
.requestMatchers("/api/catalog/**").permitAll()
```

Cấu hình này có thể mở **mọi HTTP method** cùng nhánh URL, tùy matcher; không bảo đảm chỉ GET public. Cấu hình an toàn hơn:

```java
.requestMatchers(HttpMethod.GET, "/api/catalog", "/api/catalog/*")
    .permitAll()
.requestMatchers(HttpMethod.POST, "/api/catalog")
    .hasAuthority("catalog:create")
```

Nguyên tắc: phân quyền theo **hành động thật**, không chỉ theo tiền tố URL. Nếu cần công khai GET nhưng không muốn public HEAD/OPTIONS hay các route con, phải có chính sách và test riêng cho method/URL đó.

## 5. Endpoint quản trị: role, authority và phạm vi quyền

### 5.1. Dùng role cho nhóm chức năng quản trị

```java
.requestMatchers("/admin", "/admin/**")
    .hasRole("ADMIN")

.requestMatchers("/api/admin", "/api/admin/**")
    .hasRole("ADMIN")
```

Với convention mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`. Một user chỉ có `ADMIN` sẽ **không** qua nếu dùng default prefix; hãy kiểm tra `Authentication.getAuthorities()` thực được cấp.

Những rule này dành cho chức năng quản trị theo nhóm URL, không tự suy ra người có role ADMIN có thể truy cập tất cả tài nguyên của **mọi tenant**.

### 5.2. Authority cho hành động nhạy cảm hơn

Trong `/api/admin/**` có thể có các hành động khác nhau:

| Request | Điều kiện ví dụ | Vì sao |
| --- | --- | --- |
| `GET /api/admin/users` | Role ADMIN | Xem danh sách quản trị |
| `POST /api/admin/users` | Role ADMIN và `user:create` khi policy yêu cầu | Thêm user là hành động ghi |
| `DELETE /api/admin/users/u9` | Role ADMIN và `user:delete` | Nguy cơ xóa dữ liệu |
| `GET /api/admin/reports/export` | Role ADMIN và `report:export` | Dữ liệu xuất có thể nhạy cảm |
| `POST /api/admin/config/reload` | Permission và điều kiện mạnh hơn, có audit | Ảnh hưởng vận hành |

Nếu chỉ yêu cầu role ADMIN cho **mọi** thao tác, phân quyền có thể quá rộng. Ngược lại, nếu route nhạy cảm chỉ yêu cầu một permission mà business còn đòi role ADMIN, bạn cần **kết hợp hai điều kiện trong một policy**.

### 5.3. Tránh lỗi first-match khi bảo vệ endpoint đặc biệt

**Sai** nếu export phải có role ADMIN **và** permission:

```java
.requestMatchers(HttpMethod.GET, "/api/admin/reports/export")
    .hasAuthority("report:export")
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Bộ matcher của `authorizeHttpRequests` áp dụng **rule đầu tiên khớp**. Request export được xử lý bởi rule `report:export`; rule role ADMIN phía sau **không tự cộng thêm**. Người có permission export nhưng không có role ADMIN có thể qua HTTP authorization.

**Đúng khi cần AND**: dùng kết hợp `AuthorizationManager` trong một rule:

```java
import static org.springframework.security.authorization.AuthorizationManagers.allOf;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasAuthority;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasRole;

// Trong authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/admin/reports/export")
    .access(allOf(hasRole("ADMIN"), hasAuthority("report:export")))
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Đây là fragment tích hợp, yêu cầu API `AuthorizationManagers` phù hợp với phiên bản ứng dụng. `allOf` đòi cả hai điều kiện. Nếu muốn **ADMIN hoặc SUPER_ADMIN**, có thể dùng `hasAnyRole` theo convention; đừng dùng OR khi nghiệp vụ cần AND.

### 5.4. Role ADMIN không phải toàn quyền trên mọi đối tượng

Trong hệ thống nhiều tenant, `ROLE_ADMIN` có thể nghĩa là **tenant admin**. Với `DELETE /api/admin/users/u9`, service còn cần xác minh:

- Người thực hiện thực sự có quyền quản trị tenant của tài khoản `u9`.
- Tài khoản đích có nằm trong phạm vi được quản lý không?
- Có cấm tự xóa chính mình hoặc xóa tài khoản cuối cùng giữ quyền quản trị không?
- Có cần phê duyệt kép, xác thực lại/MFA hoặc lý do thao tác không?

Các điều kiện owner/tenant/state/SoD nằm ở domain policy, không tự xuất hiện chỉ nhờ `hasRole("ADMIN")`. Bảo vệ ở HTTP là một **cổng**, không phải toàn bộ quyết định.

## 6. Thứ tự matcher và mặc định từ chối

### 6.1. Quy tắc first-match-wins

Trong một khối `authorizeHttpRequests`, Spring Security duyệt từng cặp matcher/rule theo **thứ tự khai báo** và áp dụng **matcher đầu tiên khớp**. Nó không kết hợp mọi rule có path giao nhau.

Sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Request `/api/admin/users` đã khớp `/**` và được công khai; rule ADMIN sau không có hiệu lực cho request đó.

Đúng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/", "/login").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

### 6.2. Tại sao cần `anyRequest().denyAll()`?

`denyAll()` từ chối request không được khai báo trong allowlist. Điều này giúp:

- URL debug/test mới không vô tình thành public.
- Endpoint admin mới không chỉ dựa vào `authenticated()` chung.
- Các HTTP method ít dùng (PUT/DELETE/PATCH) không tự mở do cùng path với GET.
- Các route nested hoặc version mới buộc phải được bổ sung policy và test.

Một số ứng dụng muốn mọi đường dẫn còn lại yêu cầu `authenticated()` để nhanh triển khai. Đây là lựa chọn có thể dùng khi **đã review toàn bộ route**; không nên hiểu là mặc định an toàn tương đương deny-by-default.

### 6.3. Không phải mọi URL bắt đầu bằng /admin đều giống nhau

`/admin`, `/admin/`, `/administrator` và `/api/admin` không mặc nhiên được bao phủ giống nhau. Dùng matcher cụ thể cho `/admin` và `/admin/**` nếu hệ thống cần cả hai. Đừng dựa vào cách đoán pattern của framework; kiểm thử path thật, context path và servlet path theo phiên bản matcher được sử dụng.

### 6.4. Nhóm static nên đứng ở đâu?

Trong cấu hình allowlist, có thể đặt matcher static/public ở đầu để dễ nhìn. Nhưng nếu ứng dụng có đường dẫn **đè lên nhau** như `/assets/admin/secret`, hãy kiểm tra cách matcher quyết định. Không đặt wildcard public quá rộng che URL quản trị; tốt nhất tách namespace static public khỏi namespace dữ liệu có quyền.

## 7. Cấu hình tham khảo cho một ứng dụng Spring Boot MVC

Đoạn dưới là **một class cấu hình Java** dùng trong dự án Spring Boot có Spring Web, Spring Security và Java 17+. Nó giả định đã có nguồn xác thực, controllers và các tài nguyên được phục vụ theo URL minh họa. CSRF **không bị vô hiệu hóa**. Đây không phải chương trình có thể chạy trực tiếp chỉ bằng `javac`; nó cần dependency và runtime Spring.

Tạo `WebAuthorizationConfig.java` trong package `com.example.security`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebAuthorizationConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth

            // Tài nguyên được chủ đích công bố public.
            .requestMatchers(
                "/css/**",
                "/js/**",
                "/images/**",
                "/fonts/**",
                "/webjars/**",
                "/favicon.ico"
            ).permitAll()

            // Chỉ các trang GET công khai được liệt kê.
            .requestMatchers(
                HttpMethod.GET,
                "/", "/about", "/help", "/login", "/signup"
            ).permitAll()

            // Đăng ký không cần login nhưng vẫn qua CSRF/validation.
            .requestMatchers(HttpMethod.POST, "/signup")
                .permitAll()

            // Hành động nhạy cảm: phải là admin VÀ có quyền export.
            .requestMatchers(
                HttpMethod.GET,
                "/api/admin/reports/export"
            ).access(AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasRole("ADMIN"),
                AuthorityAuthorizationManager.hasAuthority("report:export")
            ))

            // Trang và API quản trị.
            .requestMatchers(
                "/admin", "/admin/**",
                "/api/admin", "/api/admin/**"
            ).hasRole("ADMIN")

            // Phần dành cho mọi người dùng đã đăng nhập.
            .requestMatchers("/app", "/app/**")
                .authenticated()

            // Không tự mở endpoint mới.
            .anyRequest().denyAll()
        );

        http.formLogin(form -> form
                .loginPage("/login")
                .permitAll()
        );

        return http.build();
    }
}
```

### 7.1. Đọc cấu hình theo thứ tự

1. Request GET `/css/site.css` khớp static matcher → `permitAll`.
2. GET `/about` được xem không cần login; POST `/about` không có public rule → bị từ chối bởi fallback.
3. GET `/login` vào trang đăng nhập public; cấu hình form login khai báo URL login riêng.
4. GET `/api/admin/reports/export` khớp **đầu tiên** với rule đòi `ROLE_ADMIN` và `report:export`.
5. GET `/api/admin/users` vào rule admin → `hasRole("ADMIN")`.
6. GET `/app/profile` → `authenticated()`.
7. GET `/internal/debug` → `denyAll()`.

**Không suy rằng một rule `permitAll` sẽ khiến request POST tự bỏ CSRF**. Với phiên dựa trên cookie và CSRF đang bật, `POST /signup`/`POST /login` vẫn cần xử lý token phù hợp. `permitAll` chỉ liên quan đến quyền trong bước authorization, không bỏ qua bảo vệ CSRF.

### 7.2. Những chỗ cần điền theo project thực tế

- **Nguồn Authentication**: form login dùng user/password từ `UserDetailsService` hoặc provider tương ứng; admin phải có authority `ROLE_ADMIN`.
- **Gán permission xuất báo cáo**: `report:export` phải được cấp rõ ràng cho người có quyền, không mặc định sinh từ `ROLE_ADMIN`.
- **Controller/View**: custom `GET /login` và `GET /signup` cần handler/template; nếu không, có thể trả 404.
- **AuthenticationEntryPoint/AccessDeniedHandler**: API có thể muốn JSON 401/403, còn web app có thể redirect tới login.
- **Tài nguyên static**: đúng URL thư mục thực tế, không mở public thư mục lưu dữ liệu riêng tư.
- **Method/object policy**: export, thay đổi tài khoản và truy cập tài nguyên cụ thể cần check thêm tenant/scope và trạng thái.

### 7.3. Hai cách tổ chức permission nhất quán

Lựa chọn A: gán role và permission trong nguồn xác thực:

```text
GrantedAuthorities:
  ROLE_ADMIN
  report:export
```

Lựa chọn B: role chỉ mô tả chức danh, một lớp mapping được quản lý tập trung chuyển role hoặc membership tin cậy sang các permission ứng dụng. Cần kiểm thử mapping đó; Spring Security **không tự suy ra** `report:export` từ `ROLE_ADMIN`.

Với JWT Resource Server, một scope như `reports.export` thường được converter mặc định ánh xạ thành `SCOPE_reports.export`, **khác** `report:export`. Nếu dùng scope token, thống nhất rule/mapper ở nơi cấp Authentication; không đọc claim tùy ý từ header để gán role.

## 8. Login, logout, CSRF và CORS: public không phải bỏ bảo vệ

### 8.1. CSRF vẫn áp dụng cho request có thay đổi trạng thái

Ví dụ `POST /signup` không cần đăng nhập nhưng vẫn **thay đổi dữ liệu**. Với ứng dụng web có session/cookie, CSRF là mối đe dọa riêng với authorization. Spring Security thường bật CSRF protection mặc định trong cấu hình Servlet; các method không an toàn như POST/PATCH/DELETE cần token phù hợp trong mô hình cookie.

- `permitAll` không đồng nghĩa tắt `CsrfFilter`.
- Khi test `POST /signup` bằng MockMvc, dùng `.with(csrf())` nếu ứng dụng đang bật CSRF.
- Với ứng dụng Bearer token thuần túy không dựa vào cookie tự gửi, mô hình CSRF có thể khác; phải quyết định dựa trên threat model, không phải vì thấy lỗi 403.
- Custom login form POST cần token CSRF khi cơ chế bảo vệ yêu cầu.
- Không mở tất cả CSRF exclusions vì một trang đăng ký không gửi token đúng cách.

### 8.2. Logout không phải một GET public tùy ý

Trong cấu hình Servlet Spring Security mặc định khi CSRF bật, Spring Security thường dùng **POST /logout** để thực hiện logout, giúp tránh một website khác ép user tự đăng xuất thông qua link/ảnh GET. Đừng tạo `GET /logout` có side effect chỉ vì muốn “logout là trang public”. Nếu cần nút logout, dùng form POST với CSRF token.

### 8.3. CORS preflight

Trình duyệt có thể gửi request `OPTIONS` trước khi gọi API cross-origin. Preflight thường không chứa authentication giống request thực. Nếu cấu hình CORS không đúng, có thể gặp 401/403 trước khi request thực đến API.

- Cấu hình CORS theo danh sách origin/method/header được cho phép.
- Đảm bảo preflight được xử lý đúng qua cơ chế tích hợp CORS với Spring Security.
- Không biến toàn bộ `/api/admin/**` thành `permitAll` để khắc phục lỗi CORS.
- Sau preflight hợp lệ, request thực đến endpoint admin **vẫn cần** authentication, role, permission và object policy.

### 8.4. Header và cache cho tài nguyên public

Tài nguyên công khai không có nghĩa bỏ qua security headers: `X-Content-Type-Options`, chính sách CSP, cache-related headers và header khác có thể quan trọng. Với JS/CSS version theo hash, caching dài hạn có thể phù hợp; với HTML hoặc response cá nhân hóa, cache phải thận trọng. Quyết định cache và content security **khác** với việc gán `permitAll`.

Không lưu access token hoặc secret trong JS/CSS static, không phơi source map chứa bí mật hoặc file cấu hình environment. Một endpoint public đúng quyền vẫn có thể nguy hiểm nếu nội dung của nó vốn không nên công khai.

## 9. Các vị trí dễ bị bỏ sót

### 9.1. /error và dispatcher types

Khi ứng dụng trả trang lỗi hoặc view qua `FORWARD`, `ERROR` dispatch, Spring Security có thể chạy authorization ở dispatch khác. Một số dự án cần cho phép dispatch loại này để render trang lỗi/view, ví dụ:

```java
import jakarta.servlet.DispatcherType;

// Bên trong authorizeHttpRequests nếu phù hợp:
.dispatcherTypeMatchers(
    DispatcherType.FORWARD,
    DispatcherType.ERROR
).permitAll()
```

Đây **không phải quy tắc bắt buộc cho mọi app**. Chỉ áp dụng khi hiểu đường forward/error thực tế và kiểm thử không tạo đường vòng truy cập dữ liệu. Không mặc định `/error` hoặc các view nhạy cảm phải public chỉ để xử lý 403/404 dễ dàng. Hãy tách trang lỗi hiển thị thông tin tối thiểu khỏi hành động nghiệp vụ có quyền.

### 9.2. /actuator/** không tự nên public

Spring Boot Actuator có thể cung cấp endpoint sức khỏe/metric/thông tin vận hành; những endpoint được expose và cơ chế bảo vệ phụ thuộc cấu hình Actuator, cổng quản trị riêng và chính sách ứng dụng.

- Có thể công khai **một phần health** được kiểm soát, nếu sản phẩm yêu cầu monitoring public.
- Không công khai toàn bộ `/actuator/**` theo thói quen.
- Bảo vệ metrics, environment, heap dump, loggers hoặc những actuator endpoints khác dựa trên mức độ nhạy cảm.
- Nếu management server dùng port/context riêng, cần kiểm tra security chain đúng runtime đó, không chỉ URL trong ứng dụng chính.

### 9.3. Tài liệu API và console nội bộ

Các đường dẫn như `/swagger-ui/**`, `/v3/api-docs/**`, `/h2-console/**` hoặc `/internal/**` cần policy riêng theo môi trường. Công khai tài liệu API có thể là quyết định có chủ đích của public API, nhưng console CSDL và debug endpoints không nên được mở public chỉ vì "dùng trong quá trình phát triển".

### 9.4. Frontend SPA route và file asset

Một ứng dụng SPA có thể cần `GET /app-shell` hoặc `GET /` trả HTML public, nhưng dữ liệu API bên dưới vẫn bảo vệ riêng. Việc JS bundle tải được công khai không đồng nghĩa API do bundle gọi cũng được phép đọc. Đừng gom route client-side `/admin` cùng rule API admin mà không hiểu server có thực sự phục vụ nội dung gì; phân biệt public app shell với dữ liệu nhạy cảm trả từ API.

### 9.5. File download, object storage và hình ảnh riêng tư

File invoice, ảnh hồ sơ riêng, attachment ticket thường **không** nên được phục vụ từ static public path. Dùng endpoint download có authorization theo object, hoặc signed URL ràng buộc thời gian/đối tượng/phạm vi theo thiết kế. Kiểm tra không thể bỏ qua chỉ vì file có đuôi `.png` hay `.pdf`.

## 10. Nhiều SecurityFilterChain: giới hạn chain khác với phân quyền trong chain

Hai khái niệm rất dễ nhầm:

- `http.securityMatcher("/api/**")` chọn **những request mà cả filter chain áp dụng**.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...).hasRole(...))` đặt rule **bên trong chain đã được chọn**.

Khi có nhiều chain với `@Order`, Spring Security chọn chain đầu tiên có `securityMatcher` phù hợp. Các chain sau không tự được ghép thêm. Nếu không chain nào khớp request, request đó có thể không được Spring Security bảo vệ.

### 10.1. Ví dụ cấu trúc

```java
@Bean
@Order(1)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"))
        .build();
}

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/css/**", "/js/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/", "/about", "/login")
                .permitAll()
            .anyRequest().denyAll())
        .build();
}
```

Đây là **hai bean fragment** trong class `@Configuration` với các import cần thiết và cấu hình authentication/form login thích hợp. Nó minh họa phạm vi chain; chưa xử lý mọi tình huống của ứng dụng. Với Spring Boot, các cấu hình `@Order`, `securityMatcher`, login và endpoint khác cần review chung.

Bẫy lớn:

```java
http.securityMatcher("/api/admin/**")
    .authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
```

Rule `denyAll` trên **không** bảo vệ URL ngoài `/api/admin/**` nếu không có chain fallback phù hợp.

### 10.2. Form login và nhiều chain

Khi custom chain chỉ match `/admin/**` nhưng bạn lại dùng endpoint login mặc định `/login`, request `/login` có thể **nằm ngoài phạm vi chain đó**. Nếu không có chain hỗ trợ login, authentication filter hoặc trang đăng nhập có thể không hoạt động như kỳ vọng. Đảm bảo request tới login/logout endpoints thực sự được chain cấu hình các filter tương ứng xử lý.

### 10.3. Context path và RequestMatcher strategy

Khi app chạy ở context path `/myapp`, URL bên ngoài có thể là `/myapp/admin/users` nhưng matcher Servlet thường không đơn giản là thêm `/myapp` vào mọi pattern. Cách matching phụ thuộc servlet path, MVC mapping và chiến lược `RequestMatcher` theo phiên bản. Không dựa vào suy đoán URL; kiểm thử với `MockMvc` hoặc integration environment tương ứng.

## 11. Ví dụ Java 17 chạy độc lập: nhóm static/public/admin và mặc định từ chối

Chương trình Java thuần sau mô phỏng **thứ tự rule** và kiểm tra role/authority để người học thấy khác biệt giữa public, authenticated và admin. Nó **không sử dụng Spring Security**, không thay thế `RequestMatcher` thật, không mô phỏng CSRF/CORS/filter chain và không trả HTTP status. Các giả định của demo được ghi rõ trong code.

Tạo file `EndpointPolicyDemo.java`:

```java
import java.util.Set;

public class EndpointPolicyDemo {

    record User(boolean authenticated, Set<String> authorities) {
        User {
            authorities = authorities == null
                    ? Set.of() : Set.copyOf(authorities);
        }
    }

    static boolean hasAuthority(User user, String authority) {
        return user != null
                && user.authenticated()
                && user.authorities().contains(authority);
    }

    static boolean hasRole(User user, String role) {
        return hasAuthority(user, "ROLE_" + role);
    }

    static boolean isStatic(String path) {
        return path.equals("/favicon.ico")
                || path.startsWith("/css/")
                || path.startsWith("/js/")
                || path.startsWith("/images/");
    }

    static String check(String method, String path, User user) {
        // Public static assets: không cần xác thực.
        if (isStatic(path)) {
            return "ALLOW";
        }

        // Chỉ các GET public được khai báo.
        if (method.equals("GET")
                && (path.equals("/") || path.equals("/about")
                    || path.equals("/login") || path.equals("/signup"))) {
            return "ALLOW";
        }

        // Signup POST cho phép ở lớp authorization của demo.
        if (method.equals("POST") && path.equals("/signup")) {
            return "ALLOW";
        }

        // Action đặc biệt trước nhóm admin chung: yêu cầu AND.
        if (method.equals("GET")
                && path.equals("/api/admin/reports/export")) {
            return hasRole(user, "ADMIN")
                    && hasAuthority(user, "report:export")
                    ? "ALLOW" : "DENY";
        }

        // Nhóm admin chung.
        if (path.equals("/admin") || path.startsWith("/admin/")
                || path.equals("/api/admin")
                || path.startsWith("/api/admin/")) {
            return hasRole(user, "ADMIN") ? "ALLOW" : "DENY";
        }

        // App route chỉ dành cho user đã xác thực.
        if (path.equals("/app") || path.startsWith("/app/")) {
            return user != null && user.authenticated()
                    ? "ALLOW" : "DENY";
        }

        // Deny-by-default.
        return "DENY";
    }

    public static void main(String[] args) {
        User guest = new User(false, Set.of());
        User member = new User(true, Set.of("ROLE_USER"));
        User admin = new User(true, Set.of("ROLE_ADMIN"));
        User exporter = new User(true, Set.of("report:export"));
        User adminExporter = new User(
                true, Set.of("ROLE_ADMIN", "report:export"));

        System.out.println("guest-css="
                + check("GET", "/css/site.css", guest));
        System.out.println("guest-home="
                + check("GET", "/", guest));
        System.out.println("guest-login="
                + check("GET", "/login", guest));
        System.out.println("guest-admin="
                + check("GET", "/admin/users", guest));
        System.out.println("member-app="
                + check("GET", "/app/profile", member));
        System.out.println("member-admin="
                + check("GET", "/api/admin/users", member));
        System.out.println("admin-admin="
                + check("GET", "/api/admin/users", admin));
        System.out.println("admin-export-without-permission="
                + check("GET", "/api/admin/reports/export", admin));
        System.out.println("export-permission-without-admin="
                + check("GET", "/api/admin/reports/export", exporter));
        System.out.println("admin-export-with-permission="
                + check("GET", "/api/admin/reports/export", adminExporter));
        System.out.println("public-signup-post="
                + check("POST", "/signup", guest));
        System.out.println("post-about="
                + check("POST", "/about", guest));
        System.out.println("unlisted-route="
                + check("GET", "/internal/debug", admin));
    }
}
```

Chạy với JDK 17+:

```bash
javac EndpointPolicyDemo.java
java EndpointPolicyDemo
```

Kết quả stdout:

```text
guest-css=ALLOW
guest-home=ALLOW
guest-login=ALLOW
guest-admin=DENY
member-app=ALLOW
member-admin=DENY
admin-admin=ALLOW
admin-export-without-permission=DENY
export-permission-without-admin=DENY
admin-export-with-permission=ALLOW
public-signup-post=ALLOW
post-about=DENY
unlisted-route=DENY
```

**Ý nghĩa:**

- Static resources và GET pages đã công bố không đòi authentication.
- Member đăng nhập được vào `/app/profile` nhưng không tự trở thành admin.
- Export đòi **role ADMIN và authority report:export**. Thiếu một điều kiện vẫn bị chặn.
- `POST /signup` được công khai **trong mô phỏng authorization**, không hàm ý request được miễn CSRF/validation trong ứng dụng Spring.
- `POST /about` và route không khai báo bị từ chối; pattern GET public không mở mọi method.

Demo tự viết `startsWith`/`equals` để đơn giản hóa. Khi triển khai, **phải dùng matcher của Spring Security và test thực tế**, vì context path, servlet path, URL encoding, Spring MVC mapping và lựa chọn matcher có thể thay đổi kết quả.

## 12. Kiểm thử với Spring Security Test và MockMvc

### 12.1. Ma trận hành vi nên có

| Request | Chủ thể/authorities | Mục tiêu ở lớp authorization |
| --- | --- | --- |
| `GET /css/site.css` | Chưa đăng nhập | Được đi qua rule public |
| `GET /js/app.js` | Chưa đăng nhập | Được đi qua rule public |
| `GET /about` | Chưa đăng nhập | Được đi qua rule public |
| `GET /login` | Chưa đăng nhập | Được đi qua rule public |
| `GET /app/profile` | Chưa đăng nhập | Bị từ chối/chuyển tới login tùy cấu hình |
| `GET /app/profile` | User đã xác thực | Qua rule authenticated; vẫn có thể bị policy khác chặn |
| `GET /admin/users` | `ROLE_USER` | DENY |
| `GET /admin/users` | `ROLE_ADMIN` | Qua role rule |
| `GET /api/admin/users` | `ROLE_ADMIN` | Qua role rule |
| `GET /api/admin/reports/export` | Chỉ `ROLE_ADMIN` | DENY |
| `GET /api/admin/reports/export` | Chỉ `report:export` | DENY |
| `GET /api/admin/reports/export` | `ROLE_ADMIN` + `report:export` | Qua rule AND |
| `POST /signup` | Guest, có CSRF token hợp lệ | Qua authorization, còn validation |
| `POST /signup` | Guest, thiếu CSRF khi CSRF bật | Có thể bị từ chối bởi CsrfFilter |
| `POST /about` | Guest | DENY theo rule còn lại |
| `GET /internal/debug` | Kể cả `ROLE_ADMIN` | DENY theo fallback |
| `GET /uploads/private.pdf` | Guest | DENY nếu không được khai báo public |

"Qua rule" **không luôn bằng HTTP 200**. Controller có thể không tồn tại, trả 404, hoặc service có policy khác chặn. Test authorization nên phân biệt đường đi đến filter/controller với kết quả cuối của nghiệp vụ.

### 12.2. @WithMockUser: roles khác authorities

```java
@WithMockUser(roles = "ADMIN")
```

thường tạo một `Authentication` trong test có authority `ROLE_ADMIN`, không tự có `report:export`.

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "report:export"})
```

cấp hai authority chính xác. Với config export yêu cầu AND, đây là cách mô phỏng principal có đủ hai quyền trong test. Tuy nhiên mock user không thay thế test mapping từ identity provider/JWT hoặc nguồn user thật; nếu production thêm permission qua converter, nên test converter đó độc lập và tích hợp.

### 12.3. Mảnh MockMvc test hữu ích

Các đoạn sau là **test fragments**, yêu cầu project có `MockMvc`, Spring Security Test, controller/fixture, imports và cấu hình security tương ứng; chúng không chạy độc lập bằng `javac`:

```java
@Test
@WithMockUser(roles = "USER")
void ordinaryUserCannotEnterAdmin() throws Exception {
    mockMvc.perform(get("/api/admin/users"))
           .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminWithoutExportPermissionIsDenied() throws Exception {
    mockMvc.perform(get("/api/admin/reports/export"))
           .andExpect(status().isForbidden());
}

@Test
@WithMockUser(authorities = {"ROLE_ADMIN", "report:export"})
void adminWithExportPermissionCanReachHandler() throws Exception {
    mockMvc.perform(get("/api/admin/reports/export"))
           .andExpect(status().isOk());
}
```

Test thứ ba chỉ có thể assert `200` nếu controller phù hợp tồn tại, dữ liệu fixture hợp lệ, handler trả 200 và không có policy bổ sung từ chối. Một test chuyên về permission nên dùng endpoint/handler trong môi trường test có hành vi rõ ràng, không mặc định `hasAuthority` đạt là request phải có status 200.

Test trang public, tài nguyên tĩnh cần có file/controller thực, nếu không sẽ trả 404 dù rule `permitAll` đúng. Với form POST và CSRF đang bật:

```java
mockMvc.perform(post("/signup")
        .with(csrf())
        .param("email", "demo@example.test"))
       .andExpect(/* assertion đúng với contract signup của project */);
```

Lời gọi ở trên là **pseudocode test fragment**, phần assertion phải viết theo contract thực tế. Trong code production/test hoàn chỉnh cần thay phần mô tả bằng một `ResultMatcher` cụ thể; ví dụ `status().is3xxRedirection()` nếu controller signup chuyển hướng sau khi xử lý thành công. Không dựa vào 403 để kết luận chỉ thiếu authority nếu request vốn thiếu CSRF token.

### 12.4. Những test dễ bị bỏ quên

1. **Static real URL:** `/css/site.css` và `/favicon.ico` với guest thật, xác nhận file được trả và header phù hợp.
2. **404 public:** file không tồn tại trả 404 chứ không phải chuyển sang login chỉ vì security.
3. **Login:** GET login public; POST login có CSRF; logout POST hoạt động với CSRF.
4. **Admin role:** chỉ `ROLE_ADMIN` được vào nhóm quản trị, không chấp nhận authority `ADMIN` khi prefix mặc định không cho.
5. **AND export:** role+permission; thiếu role; thiếu permission; thiếu cả hai.
6. **Fallback:** `/internal/debug` hoặc route mới không tự mở.
7. **Thứ tự:** `/api/admin/**` không bị `/api/**` hoặc `/**` public matcher che.
8. **Nhiều chain:** request ngoài `securityMatcher` của admin chain vẫn được chain khác xử lý an toàn.
9. **Object scope:** tenant admin không tác động sang tenant khác nếu policy không cho.
10. **CORS/CSRF:** kiểm thử preflight và request thực, không dùng một cấu hình mở rộng quyền để sửa lỗi CORS.

## 13. Xử lý sự cố: chặn nhầm và mở nhầm

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Login mở được nhưng CSS 403/redirect | Thiếu static `permitAll`, URL matcher sai, chain khác được chọn | Xem URL network, request matcher và filter chain thực |
| CSS 404 chứ không 403 | Không có resource/URL sai, không phải lỗi authorization đơn thuần | Kiểm tra classpath, resource handler, context path |
| Guest xem được API admin | `permitAll`/`authenticated` quá rộng đứng trước role rule | Kiểm tra first-match-wins và test đường admin |
| User có `ADMIN` vẫn bị 403 | `hasRole("ADMIN")` theo mặc định đòi `ROLE_ADMIN` | Kiểm tra authorities thực |
| Admin có `ROLE_ADMIN` nhưng export vẫn 403 | Rule export còn đòi `report:export` hoặc business policy khác | Kiểm tra kết hợp AND, source cấp permission |
| POST signup 403 dù public | CSRF token thiếu hoặc policy khác | Kiểm tra CsrfFilter, form token, test với csrf() |
| Login redirect loop | Custom `GET /login` bị bảo vệ, handler không tồn tại hoặc chain không khớp | Kiểm tra `formLogin` + public matcher + controller |
| Swagger/H2 console public ngoài ý định | Mở matcher `/**` hoặc đường dẫn dev bằng wildcard | Chỉ cho phép có chủ đích, tách theo môi trường |
| Request ngoài /api không được bảo vệ | Chỉ định `securityMatcher("/api/**")` nhưng không có fallback | Kiểm tra mọi SecurityFilterChain và @Order |
| Static mất security headers | Dùng `web.ignoring()` | Ưu tiên `permitAll` trong chain |
| Người dùng đọc invoice qua URL static | Lưu file riêng tư dưới public assets | Chuyển sang download có object authorization |
| Public GET được nhưng CORS preflight fail | CORS chưa được tích hợp đúng, preflight thiếu authentication | Cấu hình CORS và kiểm thử OPTIONS + request thực |
| ERROR/FORWARD gây 403 khi render | Authorization ở dispatcher khác không được thiết kế | Xem dispatcher types, policy lỗi, không mở bừa |
| Chỉ test bằng admin nên không thấy lỗi | Không kiểm tra guest/ordinary user | Test ma trận nhiều principal và method |

## 14. Checklist triển khai và review bảo mật

**Trước khi viết cấu hình:**

- [ ] Liệt kê nhóm URL thực tế: static assets, trang public, login/register, user area, admin UI, admin API, Actuator và các endpoint nội bộ.
- [ ] Phân biệt **tài nguyên đã công bố public** với file người dùng/tài liệu riêng tư dù cùng đuôi `.png`/`.pdf`.
- [ ] Xác định role/permission nguồn: `ROLE_ADMIN`, `report:export`; kiểm tra naming convention và nơi cấp authorities.
- [ ] Xác định policy các action nhạy cảm: cần role, permission, tenant/owner, MFA, audit hay dual approval không?
- [ ] Chọn đúng matcher theo HTTP method, path, servlet context và version.

**Trong khi cấu hình:**

- [ ] Dùng `permitAll` cho static/public pages để request vẫn ở security chain.
- [ ] Dùng `formLogin(...).loginPage(...).permitAll()` nếu chọn custom form login, có handler GET tương ứng.
- [ ] Đặt matcher admin/action đặc thù trước matcher tổng quát.
- [ ] Nếu một route cần **hai quyền đồng thời**, kết hợp AND trong policy; đừng đặt hai matcher chồng lấn rồi kỳ vọng cả hai chạy.
- [ ] Dùng `denyAll` cho URL/method chưa liệt kê khi triển khai allowlist.
- [ ] Không tùy tiện tắt CSRF hoặc mở CORS/OPTIONS để xử lý lỗi authorization.
- [ ] Khi có nhiều filter chains, có chain fallback phù hợp cho request ngoài phạm vi một chain.
- [ ] Không để `/uploads/**`, debug/Actuator nội bộ hoặc console nhạy cảm trong whitelist public.

**Trước khi phát hành:**

- [ ] Test static asset và public page với guest thật; kiểm tra status và security headers.
- [ ] Test ordinary user bị từ chối admin; admin đủ role vào được handler; export thiếu permission bị chặn.
- [ ] Test method khác GET, HTTP path nested, route không khai báo, các URL near-match và edge cases.
- [ ] Test CSRF của POST login/signup/logout và CORS preflight nếu là yêu cầu sản phẩm.
- [ ] Test các đường service/job khác không thể bỏ qua object-level policy.
- [ ] Review log/monitoring ở mức đủ điều tra mà không lộ token, secret hay dữ liệu riêng tư.
- [ ] Kiểm tra version thực của Spring Security/Boot và regression test sau nâng cấp.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Vì sao tài nguyên static công khai nên dùng `permitAll` thay vì `web.ignoring`?

**Trả lời:** `permitAll` bỏ yêu cầu quyền ở HTTP authorization nhưng request vẫn trong security filter chain; các filter/headers phù hợp vẫn có thể hoạt động. `ignoring` bỏ qua chain, có thể làm mất security headers và những bảo vệ khác.

**Câu 2.** Trang `GET /signup` public. `POST /signup` có tự trở thành public không?

**Trả lời:** Không nếu matcher bị giới hạn theo HTTP method GET. Nếu muốn cho phép đăng ký không cần login, khai báo POST theo contract riêng, nhưng vẫn cần CSRF khi áp dụng, validation và chống lạm dụng.

**Câu 3.** `hasRole("ADMIN")` cần authority `ADMIN` hay `ROLE_ADMIN` trong cấu hình mặc định?

**Trả lời:** `ROLE_ADMIN`. `hasRole` dùng prefix mặc định; nếu project cấu hình prefix khác, phải kiểm tra và test đầy đủ.

**Câu 4.** Một request GET export nằm trong `/api/admin/**` và có hai rule: export `hasAuthority("report:export")` đứng trước rule admin `hasRole("ADMIN")`. Có tự bắt buộc cả hai không?

**Trả lời:** Không. Matcher đầu tiên khớp quyết định. Nếu chính sách đòi role ADMIN **và** permission export, phải biểu diễn phép AND trong một rule hoặc một lớp kiểm tra bổ sung có chủ đích và được test.

**Câu 5.** `permitAll` cho `/css/**` có tự cho phép tải invoice ở `/uploads/invoice.pdf` không?

**Trả lời:** Không theo matcher đó. Nhưng nếu invoice nằm dưới một thư mục public được whitelist rộng, nguy cơ lộ thông tin là thật. File riêng tư phải có object-level authorization hoặc cơ chế download có quyền tương đương.

**Câu 6.** App có chain `securityMatcher("/api/admin/**")` với `anyRequest().denyAll()`. URL `/internal/debug` có chắc bị chặn không?

**Trả lời:** Không. Request ngoài `/api/admin/**` không đi vào chain đó; phải có fallback chain bảo vệ phần còn lại.

**Câu 7.** `POST /signup` đã `permitAll` nhưng nhận 403. Có nên đổi thành `permitAll` rộng hơn không?

**Trả lời:** Không. Trước tiên xác định request bị CsrfFilter, matcher, controller hay policy khác từ chối. Với CSRF bật, form phải gửi token phù hợp. Mở quyền rộng hơn không sửa gốc nguyên nhân và có thể tạo lỗ hổng.

**Câu 8.** Quản trị viên có `ROLE_ADMIN` có tự được sửa mọi tài khoản của mọi tenant không?

**Trả lời:** Không. Role vào chức năng quản trị chỉ là một điều kiện. Policy nghiệp vụ còn phải kiểm tra scope tenant, quan hệ với tài khoản đích, trạng thái và ràng buộc khác.

**Câu 9.** `GET /css/site.css` có matcher `permitAll` nhưng trả 404. Điều đó có chứng minh rule quyền sai không?

**Trả lời:** Không. `404` có thể do file không tồn tại, asset được đóng gói sai hoặc URL mapping khác. Cần phân biệt resource serving với authorization.

**Câu 10.** Vì sao không đặt `requestMatchers("/**").permitAll()` ở đầu rồi bảo vệ admin ở sau?

**Trả lời:** Quy tắc matcher đầu tiên khớp được áp dụng; `/**` che mọi rule đặc thù phía sau và có thể công khai endpoint quản trị. Hãy viết allowlist theo path/method, rule nhạy cảm trước, fallback `denyAll`.

**Tóm tắt:** Phân quyền HTTP an toàn không phải chỉ là "mở CSS, khóa admin". Cần phân loại đúng tài nguyên, đặt `permitAll` trong filter chain cho asset public, khai báo trang GET và action POST theo contract, chặn admin bằng role/permission cụ thể, không lẫn first-match với phép AND, bảo vệ tài nguyên riêng tư và kiểm thử cả HTTP lẫn nghiệp vụ.

## Tài liệu tham khảo

- Spring Security — Authorize HttpServletRequests (`permitAll`, `hasRole`, `denyAll`, first-match, static resources): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 7.0 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html
- Spring Security — Java configuration và nhiều SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Servlet architecture, filter chain và filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — CSRF considerations: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Testing MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot — Static content and Web MVC: https://docs.spring.io/spring-boot/reference/web/servlet.html
