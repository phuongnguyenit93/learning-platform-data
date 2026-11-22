# PathPatternRequestMatcher, MvcRequestMatcher và AntPathRequestMatcher theo phiên bản

> **Chủ đề:** Spring Security - authorization  
> **Nhóm kiến thức:** RequestMatcher  
> **Mục tiêu:** Phân biệt ba chiến lược so khớp HTTP request trong Spring Security Servlet, hiểu vì sao ví dụ ở các phiên bản 5.x, 6.x và 7.x có API khác nhau, biết chọn matcher phù hợp với ứng dụng Spring MVC hoặc servlet tùy biến, và chuyển từ matcher cũ sang `PathPatternRequestMatcher` mà **không vô tình bỏ chặn đường dẫn**.

## 1. Vấn đề thực tế: cùng một URL, matcher khác nhau có thể cho kết quả khác nhau

Giả sử ứng dụng có HTTP endpoint:

```http
GET /portal/mvc/reports/42
Authorization: Bearer <token>
```

Giả sử:
- `/portal` là **context path** nơi ứng dụng được triển khai.
- `/mvc` là **servlet path** của `DispatcherServlet`.
- `/reports/42` là đường dẫn controller nhận.

Ứng dụng muốn áp dụng `hasAuthority("reports:read")`. Một dự án cũ có thể dùng `MvcRequestMatcher` với mẫu `/reports/**` và servlet path `/mvc`; một dự án Spring Security 7 muốn dùng `PathPatternRequestMatcher` cần mô tả URL **không gồm context path**, tức `/mvc/reports/**`, hoặc sử dụng builder có `basePath("/mvc")`.

Nếu vô tình giữ `/reports/**` nhưng không cấu hình servlet prefix, luật có thể **không khớp**. Với fallback chỉ yêu cầu đăng nhập, request có thể đi qua HTTP authorization mà không cần `reports:read`. Với nhiều `SecurityFilterChain`, nghiêm trọng hơn: matcher chọn chain sai có thể khiến toàn bộ filter authentication/authorization dự kiến **không tham gia**.

Đó là lý do bài này không xem matcher là “cách viết wildcard”, mà là **một phần của ranh giới bảo mật**.

## 2. RequestMatcher làm gì và không làm gì?

Trong Spring Security Servlet, `org.springframework.security.web.util.matcher.RequestMatcher` là một interface chiến lược dùng để xác định một `HttpServletRequest` có khớp điều kiện không.

```java
// Chữ ký tối giản của interface theo khái niệm:
boolean matches(HttpServletRequest request);
```

Một số implementation còn hỗ trợ `matcher(request)` trả `MatchResult` để truyền các biến được trích từ đường dẫn. Đó là thông tin dùng được trong bước authorization, nhưng không nên trộn lẫn với việc tải đối tượng nghiệp vụ từ database.

Hai vị trí tiêu biểu tiêu thụ matcher:

1. **Chọn filter chain:** `http.securityMatcher(...)` tạo matcher xác định request có thuộc `SecurityFilterChain` đó không.
2. **Chọn luật HTTP:** `authorizeHttpRequests(...requestMatchers(...))` dùng matcher để chọn một `AuthorizationManager` cho request bên trong chain đã chọn.

```text
HTTP request
    |
    v
FilterChainProxy
    | chọn SecurityFilterChain ĐẦU TIÊN khớp securityMatcher
    v
SecurityFilterChain
    | authentication, CSRF, các security filters ...
    v
AuthorizationFilter
    | chọn rule ĐẦU TIÊN khớp requestMatcher
    v
AuthorizationManager
    | role, authority hoặc chính sách khác
    v
ALLOW / DENY
```

**Cần phân biệt:** matcher trả lời “request có nằm trong tập đường dẫn/method này không?”, manager trả lời “danh tính này có quyền cho request đó không?”. Một matcher khớp không đồng nghĩa ALLOW; một matcher không khớp không đồng nghĩa DENY nếu có rule fallback khác.

Phạm vi bài này là **Spring Security Servlet**, không phải `ServerWebExchangeMatcher` của WebFlux. Không sao chép các type Servlet vào Reactive Security.

## 3. Bảng so sánh ba matcher

| Khía cạnh | `AntPathRequestMatcher` | `MvcRequestMatcher` | `PathPatternRequestMatcher` |
| --- | --- | --- | --- |
| Mục tiêu | So khớp URL theo kiểu Ant-style | So khớp gần với cách Spring MVC hiểu controller mapping | So khớp bằng `PathPattern`/`PathPatternParser` |
| Thành phần nền | Ant path matching | `HandlerMappingIntrospector` của Spring MVC | `PathPatternParser` |
| Phụ thuộc MVC để hoạt động? | Không bắt buộc | Có, dùng hạ tầng MVC | Không cần `HandlerMappingIntrospector` để khớp thông thường |
| Bắt buộc biết servlet path? | Phụ thuộc URL mà matcher đọc và cách cấu hình | Cần cấu hình khi có servlet path không mặc định | Dùng full application path (trừ context root) hoặc `Builder.basePath` |
| Hỗ trợ HTTP method? | Có | Có | Có |
| Có path variables? | Có qua loại matcher/hàm trích biến tương ứng | Có, theo mapping MVC | Có, thông qua `PathPattern` và `MatchResult` |
| Trạng thái trong 6.5 | Còn tồn tại; deprecated for removal | Còn tồn tại; deprecated for removal | Đã có, là hướng chuyển đổi khuyến nghị |
| Trạng thái trong 7.x | Không còn được hỗ trợ | Không còn được hỗ trợ | Matcher path mặc định và hướng tích hợp chính |
| Khi gặp trong code | Legacy compatibility, thường phải migration | Legacy MVC integration, phải migration | Lựa chọn hiện đại trong 6.5+ |

**Tính chính xác theo version quan trọng hơn việc nhớ tên class.** Một snippet dùng `AntPathRequestMatcher` có thể phù hợp ở branch Spring Security 5.x/6.4, nhưng không nên sao chép sang 7.x. Trong 6.5, tuy class legacy vẫn xuất hiện trong API, chúng được đánh dấu chuẩn bị xóa. Đây không chỉ là cảnh báo style: nâng cấp major có thể gây lỗi biên dịch hoặc sai rule nếu thay matcher bằng chuỗi mà không đối chiếu URL thực.

## 4. Dòng thời gian khi nâng cấp

| Dòng phiên bản | Điều cần biết về matcher | Hành động phù hợp |
| --- | --- | --- |
| Spring Security 5.x và nhiều ứng dụng 6.0–6.4 | Tài liệu và code cũ thường dùng `AntPathRequestMatcher`, `MvcRequestMatcher` và API DSL tự lựa chọn matcher theo môi trường MVC/classpath | Khi duy trì branch cũ, kiểm tra version cụ thể và hành vi matcher thực; tránh đoán |
| Spring Security **6.5** | Thêm `PathPatternRequestMatcher` (Javadoc ghi `Since: 6.5`); `AntPathRequestMatcher`, `MvcRequestMatcher` được đánh dấu `@Deprecated(forRemoval = true)` | Bắt đầu dùng `PathPatternRequestMatcher` tường minh, bổ sung test cho context/servlet path |
| Spring Security **7.0+** | Các matcher Ant/MVC cũ không còn được hỗ trợ; `PathPatternRequestMatcher` được dùng mặc định cho path matching trong Java DSL | Đổi API legacy, chuyển các mẫu về đường dẫn absolute bắt đầu bằng `/` và **không chứa context root**, xét servlet prefix |
| Nâng cấp giữa các patch release | Có thể có sửa lỗi về cách xác định servlet path và matcher builder | Đọc release notes/security advisory, chạy regression test trên bản patch dự kiến triển khai |

Từ “theo phiên bản” ở đây không đồng nghĩa rằng mọi dự án cùng major đều có default matcher y hệt. Ở 6.x, overload DSL, bean `PathPatternRequestMatcher.Builder` do ứng dụng đăng ký, MVC classpath, và lựa chọn cấu hình ảnh hưởng implementation được tạo. **Để tránh bất ngờ, truyền một `RequestMatcher` tường minh khi hành vi path là ranh giới bảo mật quan trọng.**

Nguồn tra cứu trọng tâm:
- Hướng dẫn chính thức **Spring Security 6.5 → 7, Web Migrations**: `https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html`.
- Javadoc `PathPatternRequestMatcher` 6.5/7.0: `https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html`.
- Javadoc matcher legacy trong nhánh 6.5 để đối chiếu deprecation.

## 5. AntPathRequestMatcher: đọc URL kiểu Ant trong code cũ

Một cấu hình legacy có thể viết:

```java
import static org.springframework.security.web.util.matcher
    .AntPathRequestMatcher.antMatcher;

// Snippet cho branch Spring Security 6.x có class này;
// KHÔNG dùng cho Spring Security 7.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(antMatcher("/api/admin/**")).hasRole("ADMIN")
    .requestMatchers(antMatcher("/api/reports/**")).hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

Trong Java, static import nên viết liền một dòng ở file thật:

```java
import static org.springframework.security.web.util.matcher.AntPathRequestMatcher.antMatcher;
```

**Cơ chế:** `AntPathRequestMatcher` so khớp pattern kiểu Ant với URL dựa trên `servletPath + pathInfo` (hoặc cơ chế path helper tùy cấu hình). Query string không thuộc phần path được so khớp. Có thể giới hạn HTTP method; một mẫu `/**` có thể là universal match.

Ví dụ ý tưởng về pattern Ant:
- `/admin/**`: vùng con của admin.
- `/api/users/*`: segment con theo wildcard Ant.
- `/assets/*.css`: pattern cho file CSS, cần kiểm tra path thật và cấu hình.
- `/api/users/{name}`: một biến segment, khi matcher hỗ trợ extract variables.
- Một số mẫu `**` ở giữa đường dẫn có thể từng được chấp nhận bởi Ant nhưng **không có nghĩa** có thể sao chép nguyên sang `PathPatternParser` của mọi version.

Tài liệu cũ có thể chứa:

```java
// Giới hạn phương thức GET trên legacy matcher.
new AntPathRequestMatcher("/api/reports/**", "GET");
```

**Điểm cần chú ý:** khi chuyển sang PathPattern, không chỉ thay tên class và giữ mọi giả định pattern. Với Ant, nhiều wildcard/chi tiết phân tách dựa trên string path; với PathPattern, đường dẫn được phân tích theo cấu trúc segment và parser có quy tắc riêng.

### AntPathRequestMatcher có còn dùng được trong 6.5 không?

Có, ở branch 6.5 API vẫn tồn tại nhưng được đánh dấu deprecated for removal và khuyên chuyển sang `PathPatternRequestMatcher`. Vì vậy:
- Duy trì một branch 6.5 ngắn hạn có thể tiếp tục chạy legacy code nếu đã kiểm thử.
- Không thiết kế code mới phụ thuộc API chuẩn bị bị xóa nếu đang chuẩn bị nâng lên 7.x.
- Không bật “suppress deprecation warnings” rồi coi như đã thực hiện migration.
- Nếu có thư viện bên thứ ba tự tạo Ant matcher, cần kiểm tra phiên bản thư viện và khả năng tương thích với Security 7.

## 6. MvcRequestMatcher: dùng Spring MVC HandlerMappingIntrospector

Một snippet legacy Spring MVC:

```java
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;

// Chỉ minh họa cho nhánh 6.x còn cung cấp MvcRequestMatcher.
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(handlerMappingIntrospector);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern("/reports/**"))
        .hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

`handlerMappingIntrospector` là bean `HandlerMappingIntrospector` của Spring MVC mà cấu hình cần có. Một cách phổ biến là inject bean này vào method cấu hình `SecurityFilterChain`. Snippet chưa có đủ class/import/wiring nên **không phải chương trình standalone**.

Vì sao MVC matcher từng hữu ích?

- Nó sử dụng cách Spring MVC ánh xạ controller để ra quyết định, thay vì so path bằng cơ chế khác biệt lớn.
- Với hệ thống MVC, giúp tránh tình huống controller và security filter hiểu wildcard theo hai cách không tương thích.
- Có thể trích biến đường dẫn, hỗ trợ kiểm tra biểu thức có điều kiện.
- Đường dẫn MVC được hiểu tương đối với servlet path. Nếu `DispatcherServlet` được ánh xạ dưới `/mvc`, matcher cần biết điều này để chọn controller đúng.

Trong cấu hình cũ cho servlet path riêng:

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(handlerMappingIntrospector)
        .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern("/reports/**"))
        .hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

Với request `/portal/mvc/reports/42`:
- Context root là `/portal`.
- Servlet path là `/mvc`.
- MVC controller mapping là `/reports/42`.
- Mẫu `/reports/**` có thể khớp đúng khi builder được cấu hình servlet path phù hợp.

**Không được suy ra rằng `MvcRequestMatcher` luôn tương đương `PathPatternRequestMatcher` nếu chỉ giữ nguyên chuỗi pattern.** Spring Security 7 bỏ cơ chế suy diễn servlet prefix này; URL trong matcher phải được biểu diễn theo đường dẫn từ gốc ứng dụng, trừ context root.

Trong 6.5, `MvcRequestMatcher` vẫn còn ở API nhưng deprecated for removal, với khuyến nghị chuyển sang `PathPatternRequestMatcher`.

## 7. PathPatternRequestMatcher: chiến lược mới từ 6.5

Import:

```java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
```

Tạo matcher bằng builder:

```java
PathPatternRequestMatcher.Builder paths =
    PathPatternRequestMatcher.withDefaults();

RequestMatcher readReport =
    paths.matcher(HttpMethod.GET, "/api/reports/{reportId}");

RequestMatcher manageReports =
    paths.matcher("/api/reports/admin/**");
```

Đây là snippet API; cần import `org.springframework.http.HttpMethod` và `org.springframework.security.web.util.matcher.RequestMatcher`. `PathPatternRequestMatcher.withDefaults()` dùng `PathPatternParser.defaultInstance`; builder có overload nhận `HttpMethod` để giới hạn method.

Khi dùng trong `authorizeHttpRequests`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
class ReportHttpSecurity {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                paths.matcher(HttpMethod.GET, "/api/public/**")
            ).permitAll()
            .requestMatchers(
                paths.matcher("/api/admin/**")
            ).hasRole("ADMIN")
            .requestMatchers(
                paths.matcher(HttpMethod.GET, "/api/reports/{id}")
            ).hasAuthority("reports:read")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Đây là cấu hình **một phần**: chưa khai báo cách xác thực (form, JWT, session, HTTP Basic...), CSRF, ứng dụng MVC hoặc policy trên từng report. Trong dự án thật, tạo bean security chain cần phù hợp với runtime đang dùng.

Một số điểm:
- `paths.matcher(HttpMethod.GET, "/api/reports/{id}")` chỉ match GET và một segment ID.
- Biến `id` có thể có mặt trong `RequestMatcher.MatchResult` để phục vụ một `AuthorizationManager` cần trích biến.
- `paths.matcher("/api/admin/**")` không giới hạn method, áp dụng mọi method trong vùng admin.
- `anyRequest().denyAll()` đóng các URL còn lại **bên trong filter chain đang chọn**.
- Thứ tự vẫn là **first-match**, không tự lấy rule “có pattern dài nhất”.

Với các ứng dụng có custom `PathPatternParser`, matcher và MVC controller cần hiểu cùng kiểu pattern. Javadoc lưu ý `HandlerMapping` chứa URI mapping liên quan nên dùng `PathPatternParser.defaultInstance` nếu dùng `withDefaults()`; nếu dự án cấu hình parser khác, hãy cung cấp parser tương thích cho matcher và viết test.

## 8. Không đưa context path vào mẫu PathPattern

Một quy tắc migration quan trọng: `PathPatternRequestMatcher` nhận URI path **tương đối với context path**, tức **không** chứa context root.

Giả sử:

```text
External URL: https://example.com/portal/api/reports/42
contextPath: /portal
servletPath: (default servlet mapping)
application path: /api/reports/42
```

Matcher đúng thường là:

```java
PathPatternRequestMatcher.withDefaults()
    .matcher(HttpMethod.GET, "/api/reports/{id}");
```

Matcher **không đúng với ý định**:

```java
PathPatternRequestMatcher.withDefaults()
    .matcher(HttpMethod.GET, "/portal/api/reports/{id}");
```

Mẫu trên có nguy cơ không match request thực vì `/portal` là context path bị loại khỏi path match. Không vì external URL bắt đầu bằng `/portal` mà đưa nó vào mọi rule.

Cũng lưu ý reverse proxy có thể rewrite URL. Browser thấy `https://site.example/gateway/api/...` không bảo đảm Servlet container cũng thấy prefix `/gateway`. Hãy đo actual `request.getContextPath()`, `request.getServletPath()`, `request.getPathInfo()` trong môi trường test an toàn và xác định đường dẫn ứng dụng sau khi proxy xử lý.

## 9. Có servlet path riêng: dùng Builder.basePath

Nếu `DispatcherServlet` chạy ở `/mvc`:

```text
External URL       /portal/mvc/reports/42
Context path       /portal
Servlet path       /mvc
MVC mapping        /reports/42
Pattern cần match  /mvc/reports/{id}
```

Có thể viết full application path:

```java
var paths = PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        paths.matcher(HttpMethod.GET, "/mvc/reports/{id}")
    ).hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

Hoặc dùng builder gắn servlet prefix để tránh lặp:

```java
var mvc = PathPatternRequestMatcher.withDefaults()
    .basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        mvc.matcher(HttpMethod.GET, "/reports/{id}")
    ).hasAuthority("reports:read")
    .requestMatchers(
        mvc.matcher("/admin/**")
    ).hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

`basePath("/mvc")` là cách khai báo **servlet prefix** để builder tạo full application path tương ứng. Mẫu con `/reports/{id}` **vẫn bắt đầu bằng dấu `/`**. Khi có nhiều servlet, tạo các builder có base path khác nhau hoặc chỉ rõ matcher cho từng servlet; không dựa vào “MVC sẽ tự đoán URL”.

**Không cấu hình đồng thời basePath("/mvc") và matcher("/mvc/reports/**")** nếu mục đích chỉ có một prefix `/mvc`; phải hiểu kết quả builder ghép path trước khi dùng. Nếu contextPath `/portal`, cũng không viết `basePath("/portal/mvc")` vì context path không phải servlet prefix.

## 10. Ví dụ chuyển cùng một rule qua ba thế hệ

Giả sử ứng dụng có:
- `GET /api/public/info` cho khách.
- `GET /api/documents/{id}` cho user có `document:read`.
- `DELETE /api/documents/{id}` cho user có `document:delete`.
- `/api/admin/**` chỉ cho `ROLE_ADMIN`.

### A. Mẫu legacy dùng Ant (chỉ nhánh còn class)

```java
import static org.springframework.security.web.util.matcher.AntPathRequestMatcher.antMatcher;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(antMatcher("/api/public/**")).permitAll()
    .requestMatchers(antMatcher("/api/admin/**")).hasRole("ADMIN")
    .requestMatchers(
        new AntPathRequestMatcher("/api/documents/**", "DELETE")
    ).hasAuthority("document:delete")
    .requestMatchers(
        new AntPathRequestMatcher("/api/documents/**", "GET")
    ).hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

Cần import `AntPathRequestMatcher`. Vì `antMatcher("/api/public/**")` không giới hạn method, **đừng sử dụng đúng snippet này cho một public GET-only endpoint mà không sửa thành GET-specific matcher**. Đây là minh họa migration từ legacy code, không phải khuyến nghị security policy.

### B. Mẫu legacy dùng MVC (chỉ nhánh còn class)

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(HttpMethod.GET, "/api/public/**"))
        .permitAll()
    .requestMatchers(mvc.pattern("/api/admin/**"))
        .hasRole("ADMIN")
    .requestMatchers(mvc.pattern(HttpMethod.DELETE, "/api/documents/{id}"))
        .hasAuthority("document:delete")
    .requestMatchers(mvc.pattern(HttpMethod.GET, "/api/documents/{id}"))
        .hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

`introspector` cần do ứng dụng cung cấp; chữ ký `MvcRequestMatcher.Builder.pattern(HttpMethod, String)` thuộc nhánh tương thích và không nên copy sang Spring Security 7.

### C. Mẫu 6.5+/7.x bằng PathPattern

```java
var paths = PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(paths.matcher(
        HttpMethod.GET, "/api/public/**"
    )).permitAll()
    .requestMatchers(paths.matcher(
        "/api/admin/**"
    )).hasRole("ADMIN")
    .requestMatchers(paths.matcher(
        HttpMethod.DELETE, "/api/documents/{id}"
    )).hasAuthority("document:delete")
    .requestMatchers(paths.matcher(
        HttpMethod.GET, "/api/documents/{id}"
    )).hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

Ở cách C, giữ được ý nghĩa request method/path nhưng thay matcher bằng loại đang được hỗ trợ. Cách sửa từ A/B sang C phải **được test trên URL thật**, đặc biệt:
- Path root so với path con.
- Servlet path khác mặc định.
- Wildcard cũ và biến `{id}`.
- HTTP method GET/HEAD/POST/PATCH/DELETE.
- Path có slash cuối hoặc đã được proxy rewrite.

**Không chỉ sửa import để hết warning.** Hãy kiểm tra tập URL mà mỗi rule nhận trước và sau migration.

## 11. requestMatchers(String) là gì? Vì sao không nên đoán loại matcher?

Trong DSL phổ biến, developer thường viết:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Đây là overload nhận **chuỗi**, không phải lời gọi trực tiếp constructor của `AntPathRequestMatcher`, `MvcRequestMatcher` hay `PathPatternRequestMatcher`. Spring Security **tự xây RequestMatcher dựa trên phiên bản và môi trường cấu hình**.

Các điểm đáng nhớ:

- Trong các nhánh cũ, Spring Security có thể chọn kiểu MVC nếu Spring MVC hiện diện; hoặc dùng Ant matcher trong ngữ cảnh khác. XML namespace cũng có tùy chọn `mvc`/`ant`/`regex` theo version.
- Trong 6.5, ứng dụng có thể cấu hình builder cho DSL chọn `PathPatternRequestMatcher`. Tài liệu migration giới thiệu `PathPatternRequestMatcherBuilderFactoryBean` như một cách chuẩn bị lên 7.
- Trong 7.x, matcher path được DSL dùng mặc định là `PathPatternRequestMatcher`, yêu cầu mẫu path theo quy tắc mới.
- Nếu truyền **một đối tượng RequestMatcher tường minh** vào overload nhận matcher, bạn xác định rõ loại matcher dùng, không phụ thuộc suy diễn của DSL.

Vì thế, khi audit route quan trọng, hãy viết hoặc kiểm tra rõ implementation thay vì tranh luận rằng “`requestMatchers("/api/**")` chắc chắn là Ant” trên mọi version.

## 12. Opt-in sớm khi còn Spring Security 6.5

Hướng dẫn migration Spring Security 6.5 → 7 nêu khả năng đăng ký bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.PathPatternRequestMatcherBuilderFactoryBean;

@Configuration
class MatcherMigrationConfiguration {

    @Bean
    PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
        return new PathPatternRequestMatcherBuilderFactoryBean();
    }
}
```

Bean này hướng DSL tạo path matcher theo `PathPatternRequestMatcher`, giúp phát hiện các rule không tương thích trước khi nâng major. Đây là **snippet Spring 6.5 migration**; không phải cấu hình bắt buộc cho mọi ứng dụng Spring Security 7.0, và phải xác nhận method/package trong dependency version thực dùng.

Khi opt-in:
- Không chỉ nhìn ứng dụng khởi động không lỗi; thực hiện **positive và negative security tests** cho từng đường dẫn.
- Nếu ứng dụng có custom servlet mapping, rà soát servlet path; mục tiêu là explicit application path.
- Các matcher do filter của bên thứ ba tự khởi tạo có thể chưa tuân theo builder bean; cần audit cấu hình của chúng.
- Cần đối chiếu matcher trong `securityMatcher` và `requestMatchers`, không chỉ các annotation ở controller.

**Lưu ý:** nếu không dùng opt-in bean, vẫn có thể truyền `PathPatternRequestMatcher.withDefaults().matcher(...)` trực tiếp vào những rule quan trọng của nhánh 6.5.

## 13. Những khác biệt ngôn ngữ pattern cần xét khi migration

### Literal path, wildcard và path variables

| Mẫu | Ý định thường thấy | Điểm cần test |
| --- | --- | --- |
| `/api/health` | Chỉ một path cụ thể | Có khớp slash cuối không? |
| `/api/users/*` | Một segment con | URL có nhiều segment, slash và ký tự encode |
| `/api/users/{id}` | Một segment được đặt tên | Có extract đúng `id` và route của controller không? |
| `/api/files/**` | Cây resource | Root `/api/files` có khớp không? |
| `/api/files/{*rest}` | Bắt phần path còn lại với `PathPattern` ở version hỗ trợ | Mapping thật, biến trích được, case root |
| `/**/admin/**` | Wildcard ở giữa đường dẫn | **Không giả định portable** giữa Ant, Framework 6 và Framework 7 |

`PathPatternParser` là parser có cú pháp/chi tiết version riêng. Ở Spring Framework 6, `**` và `{*var}` nhìn chung bị giới hạn ở cuối pattern để giảm ambiguity; Spring Framework 7 đã có cải tiến về matching nhiều segment trước một literal. Không nên tuyên bố một pattern “luôn không hợp lệ” hoặc “luôn tương đương” qua mọi phiên bản. Nếu dùng mẫu phức tạp, **xác nhận bằng parser và test của đúng version đang chạy**.

Ant style có thể chấp nhận những pattern đặc biệt mà PathPattern không chấp nhận hoặc diễn giải khác. Những mẫu chứa wildcard ở giữa, dấu chấm, dấu phân cách URL không chuẩn, encoded slash hoặc semicolon nên được audit từng case. Tránh viết security matcher quá mơ hồ kiểu `/**/admin/**` chỉ để bắt vài endpoint cụ thể; thường dễ review hơn nếu route nhạy cảm có prefix rõ.

### Case sensitivity

`AntPathRequestMatcher` có lựa chọn case sensitivity theo constructor. `PathPatternParser` cũng có cấu hình tương ứng. Không coi URL `/Admin` và `/admin` luôn đồng nhất hoặc luôn khác nhau khi chưa xác nhận MVC router, reverse proxy, servlet container và matcher cùng cách xử lý.

### URL encoding và path normalization

Vì các implementation không luôn xử lý path cùng cách, cần test:
- `/api/users/42` và `/api/users/42/`.
- `/api/users/%34%32` (URL-encoded segment).
- `/api/files/a%2Fb` hoặc dấu phân cách được encode, nếu container/proxy chấp nhận.
- Dấu `;` và matrix variables, nếu ứng dụng sử dụng.
- Chuỗi có `..` hoặc các dạng normalize gây nhầm.
- Case, duplicate slash, context root, servlet prefix.

Không đưa pattern mơ hồ vào production dựa trên một thử nghiệm thủ công duy nhất.

## 14. Path variables: match được không có nghĩa resource được phép

Ví dụ:

```java
var paths = PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        paths.matcher(HttpMethod.GET, "/api/documents/{id}")
    ).hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

Một request `GET /api/documents/42` có thể match và người dùng có `document:read` vượt HTTP authorization. **Nhưng request ID 42 vẫn do client chọn.** URL matcher không tra `Document#ownerId` hoặc tenant ở database.

Trong service:

```java
// Snippet tích hợp: repository, Actor và DocumentPolicy do ứng dụng định nghĩa.
@PreAuthorize("hasAuthority('document:read')")
public DocumentDto readDocument(long id) {
    Actor actor = actorResolver.requireActorFromAuthentication();

    Document entity = repository
        .findByIdAndTenantId(id, actor.tenantId())
        .orElseThrow(DocumentNotFoundException::new);

    if (!policy.canRead(actor, entity)) {
        throw new AccessDeniedException("Not allowed");
    }
    return mapper.toDto(entity);
}
```

Đây **không phải chương trình standalone**; cần khai báo các type/bean domain, transaction, import annotation và exception thật trong dự án. Cơ chế HTTP matching và domain permission là hai cấp khác nhau. Một hệ thống vẫn có thể mắc IDOR/BOLA mặc dù matcher phân quyền URL đúng.

Nếu dùng `RequestMatcher.MatchResult` để trích `id` đưa vào custom `AuthorizationManager`, vẫn phải validate kiểu ID, tenant và đối tượng thật thay vì tin path variable là resource đã xác thực.

## 15. Chọn SecurityFilterChain: tác động lớn hơn một rule bị lệch

Ứng dụng có thể có hai chain:

```java
@Bean
@Order(1)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN")
        );
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain regularApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );
    return http.build();
}
```

Snippets có thể cần cấu hình authentication cụ thể; `@Bean`/`@Order` và `SecurityFilterChain` cần import. Điều cần học:

1. `FilterChainProxy` chọn chain **đầu tiên** có `securityMatcher` match.
2. Chỉ sau khi chọn chain, `authorizeHttpRequests` bên trong mới xét `requestMatchers`.
3. Nếu matcher admin không khớp vì servlet path hoặc migration pattern sai, request có thể rơi vào regular chain và chỉ cần đăng nhập.
4. Nếu regular chain cũng không khớp, request có thể không được bảo vệ bởi Spring Security nếu không có fallback chain phù hợp.
5. `anyRequest().denyAll()` **bên trong một chain** không bảo vệ request **không thuộc chain đó**.

Một lỗi cấu hình matcher tại `securityMatcher` thường nguy hiểm hơn lỗi một rule chức năng, vì nó có thể làm mất cả authentication, CSRF và authorization filters dự kiến cho request.

Khi nâng từ 6.5 lên 7, hãy kiểm tra **mọi securityMatcher dùng chuỗi** và các builder tùy biến, không chỉ matcher trong `authorizeHttpRequests`.

## 16. Một cảnh báo bảo mật có phiên bản rất cụ thể: Spring Security 7.0.0–7.0.4

Trong năm 2026, Spring đã công bố **CVE-2026-22753** về servlet path không được đưa vào cách matching đúng trong một cấu hình nhất định của `HttpSecurity#securityMatchers(String)`.

Điều kiện liên quan theo advisory chính thức:
- Ứng dụng sử dụng `securityMatchers(String)` để chọn chain;
- Đồng thời có bean `PathPatternRequestMatcher.Builder` dùng để prepend servlet path;
- Việc chọn chain có thể không match request dự kiến, khiến các filter bảo mật của chain **không hoạt động trên những request đó**.

Các phiên bản bị ảnh hưởng: **Spring Security 7.0.0 đến 7.0.4**. Phiên bản sửa lỗi trong nhánh 7.0: **7.0.5**. Advisory nêu rõ Spring Security 6.x và trước đó không bị ảnh hưởng bởi tương tác cụ thể này.

Hành động:
1. Nâng bản bị ảnh hưởng lên patch đã sửa hoặc cao hơn trong nhánh tương ứng.
2. Trong trường hợp chưa thể nâng, tham khảo mitigation chính thức để chỉ rõ servlet prefix trong matcher pattern.
3. Test `securityMatcher` để chắc chắn chain dự kiến được chọn khi request có servlet path tùy biến.
4. Xem [Spring advisory CVE-2026-22753](https://spring.io/security/cve-2026-22753/) để đối chiếu điều kiện thực tế.

Không nên khái quát “mọi cách dùng PathPattern đều lỗi” hoặc “mọi ứng dụng 7.0 đều bị ảnh hưởng”: advisory mô tả **một tổ hợp cụ thể** của string-based chain matcher và builder. Việc nâng version và test chain chọn đúng là giải pháp quan trọng.

## 17. Trường hợp nào nên dùng Matcher kiểu nào?

### Dự án mới, Spring Security 7.x

Chọn `PathPatternRequestMatcher` hoặc DSL string matcher được version 7 hỗ trợ. Với custom servlet path:
- Khai báo full application path (bỏ context root), hoặc builder có `basePath`.
- Xác định Spring MVC đang dùng `PathPatternParser` tương thích.
- Không dùng import cũ `AntPathRequestMatcher`/`MvcRequestMatcher` đã không còn hỗ trợ.
- Test positive/negative, route public, admin, POST/PATCH, fallback chain.

### Dự án 6.5 đang nâng cấp

Khuyến nghị chuyển sớm sang `PathPatternRequestMatcher`; có thể opt-in DSL bằng migration bean chính thức. Giữ legacy class trong thời gian ngắn chỉ khi có lý do duy trì tương thích và test đủ. Chuẩn hóa servlet path và URL normalization trước khi nâng 7.

### Dự án 6.4 hoặc nhánh cũ chưa nâng

Có thể tiếp tục sử dụng matcher hỗ trợ trong version ấy. Nhưng:
- Đừng áp code từ tài liệu Spring Security 7 vào branch cũ nếu class mới chưa tồn tại.
- Ghi nhận matcher cụ thể mà DSL đang tạo (MVC/Ant).
- Không nâng một major chỉ bằng việc thay dependency mà bỏ kiểm thử security.
- Lập kế hoạch migration, đặc biệt với custom servlet mapping và wildcard phức tạp.

### Hệ thống ngoài Spring MVC

Có thể dùng `PathPatternRequestMatcher` cho Servlet endpoints khi phù hợp với đường dẫn ứng dụng, hoặc `RegexRequestMatcher`/custom matcher nếu thực sự cần biểu thức khác. Không ép `MvcRequestMatcher` vào một môi trường không có MVC `HandlerMappingIntrospector`. Nếu matcher custom, nó phải được review như mã bảo mật và có test trên actual `HttpServletRequest`.

## 18. RegexRequestMatcher và custom matcher: lựa chọn thay thế khi pattern chưa diễn đạt được

Ba matcher trong bài đều thuộc một nhóm path matcher. Nhưng có thể gặp URL không diễn đạt tốt bằng `PathPattern`, ví dụ một số endpoint của servlet khác có pattern đặc biệt.

Trong trường hợp đó, Spring Security có `RegexRequestMatcher`, dùng regex phù hợp. Ví dụ tùy version có thể dùng factory:

```java
import static org.springframework.security.web.util.matcher.RegexRequestMatcher.regexMatcher;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(regexMatcher("^/legacy/.*\\.jsp$"))
        .hasAuthority("legacy:read")
    .anyRequest().denyAll()
);
```

Snippet minh họa, cần kiểm tra chính xác path/method và biểu thức regex trên runtime. Regex dễ bị viết quá rộng (ví dụ thiếu anchor `^`/`$`) hoặc bị lách nhờ URL decoding, nên chỉ dùng khi cần và test kỹ. Một `RequestMatcher` custom có thể xét header, query hoặc một điều kiện khác, nhưng **không được tin dữ liệu do client khai làm bằng chứng cấp quyền**.

Tài liệu migration 6.5 → 7 cũng đề cập những mẫu không có thay thế PathPattern tổng quát, chẳng hạn một số cách match servlet/JSP; những trường hợp này có thể yêu cầu regex riêng. Đừng cố thay mọi legacy matcher bằng một wildcard PathPattern mở rộng hơn chỉ để build thành công.

## 19. First-match vẫn đúng bất kể matcher nào được dùng

Đổi `AntPathRequestMatcher` thành `PathPatternRequestMatcher` **không biến logic của DSL thành một biểu thức kết hợp tất cả matchers**.

Ví dụ sai:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

`/api/admin/users` khớp matcher đầu và chỉ cần authenticated; matcher admin phía sau không cộng thêm quyền admin. Cách có chủ đích:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

**Đây là quy tắc thứ tự**, không phải vấn đề riêng Ant hay PathPattern. Nếu migration làm matcher thay đổi tập path mà nó match, những rule nào **đến lượt được kiểm tra trước** cũng có thể đổi theo. Vì vậy, security regression tests phải xét cả:
- **Path semantics** (matcher nào khớp URL).
- **Rule order** (rule nào được chọn).
- **Authority** (rule đó cho ai).
- **Resource policy** (bản ghi có thuộc người gọi hay không).

## 20. Chương trình Java 17+ chạy độc lập: bẫy servlet path khi migration

Demo bên dưới không dùng Spring để dễ học và kiểm chứng đầu ra. Nó **chỉ mô phỏng prefix matching cho mẫu `/prefix/**`**, không tái tạo parser của `AntPathRequestMatcher`, `MvcRequestMatcher` hay `PathPatternRequestMatcher`. Mục tiêu là chỉ ra vì sao việc chọn **phần URL đem so** quan trọng.

Lưu thành `MatcherPathDemo.java`:

```java
public class MatcherPathDemo {

    record Request(
        String contextPath,
        String servletPath,
        String pathInfo,
        String method
    ) {
        String applicationPath() {
            return servletPath + pathInfo;
        }

        String legacyMvcPath() {
            return pathInfo;
        }
    }

    // Matcher đơn giản CHỈ dành cho mẫu kết thúc bằng "/**".
    static boolean subtreeMatch(String actualPath, String pattern) {
        if (!pattern.endsWith("/**")) {
            throw new IllegalArgumentException("Expected /** pattern");
        }
        String root = pattern.substring(0, pattern.length() - 3);
        return actualPath.equals(root)
            || actualPath.startsWith(root + "/");
    }

    public static void main(String[] args) {
        Request request = new Request(
            "/portal", "/mvc", "/reports/42", "GET"
        );

        // Mô hình cũ: mẫu nằm dưới servlet path.
        boolean oldMvc = subtreeMatch(
            request.legacyMvcPath(), "/reports/**"
        );

        // Mô hình mới: mẫu cần bao gồm servlet prefix, bỏ context.
        boolean newWithoutPrefix = subtreeMatch(
            request.applicationPath(), "/reports/**"
        );
        boolean newWithPrefix = subtreeMatch(
            request.applicationPath(), "/mvc/reports/**"
        );

        // Lỗi: đưa context root /portal vào mẫu.
        boolean newWithContext = subtreeMatch(
            request.applicationPath(), "/portal/mvc/reports/**"
        );

        // Ví dụ method restriction độc lập với path.
        boolean getOnly = request.method().equals("GET")
            && newWithPrefix;
        boolean postOnly = request.method().equals("POST")
            && newWithPrefix;

        System.out.println("Application path: "
            + request.applicationPath());
        System.out.println("Legacy MVC relative: " + oldMvc);
        System.out.println("New without servlet prefix: "
            + newWithoutPrefix);
        System.out.println("New with servlet prefix: "
            + newWithPrefix);
        System.out.println("New with context prefix: "
            + newWithContext);
        System.out.println("GET rule matches: " + getOnly);
        System.out.println("POST rule matches: " + postOnly);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac MatcherPathDemo.java
java MatcherPathDemo
```

Kết quả chuẩn:

```text
Application path: /mvc/reports/42
Legacy MVC relative: true
New without servlet prefix: false
New with servlet prefix: true
New with context prefix: false
GET rule matches: true
POST rule matches: false
```

Diễn giải:

1. Browser yêu cầu URL chứa `/portal`, nhưng sau khi loại context root, đường dẫn ứng dụng có servlet prefix `/mvc`.
2. Mô hình legacy MVC ví dụ xử lý `/reports/42` theo path dưới servlet, nên pattern tương đối `/reports/**` khớp.
3. Một PathPattern mới thiếu servlet prefix không khớp `/mvc/reports/42`.
4. Một PathPattern chứa cả context root `/portal` cũng không khớp.
5. Chỉ rõ servlet prefix một lần giúp pattern trùng đúng đường dẫn.
6. Giới hạn HTTP method là điều kiện độc lập; cùng path có thể match GET nhưng không match POST.

**Giới hạn bắt buộc phải nhớ:** demo làm việc trên các string do người viết cho trước, `pathInfo` không null, pattern chỉ có dạng subtree. HttpServletRequest thật, url decoding, path variables, reverse proxy, Spring MVC, `PathPatternParser` và Servlet mapping có hành vi phức tạp hơn. Không dùng `subtreeMatch` này như một security filter trong production.

## 21. Kiểm thử một RequestMatcher thật bằng MockHttpServletRequest

Với Spring Security dependency 6.5+/7, có thể tạo matcher và request giả trong test Spring; kiểu dưới đây là **snippet integration**, không phải `javac` standalone:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import static org.assertj.core.api.Assertions.assertThat;

class ReportMatcherTest {

    @Test
    void shouldMatchOnlyGetReportsUnderMvcServlet() {
        var paths = PathPatternRequestMatcher.withDefaults()
            .basePath("/mvc");
        var matcher = paths.matcher(
            HttpMethod.GET, "/reports/{id}"
        );

        MockHttpServletRequest get =
            new MockHttpServletRequest("GET", "/portal/mvc/reports/42");
        get.setContextPath("/portal");
        get.setServletPath("/mvc");
        get.setPathInfo("/reports/42");

        MockHttpServletRequest post =
            new MockHttpServletRequest("POST", "/portal/mvc/reports/42");
        post.setContextPath("/portal");
        post.setServletPath("/mvc");
        post.setPathInfo("/reports/42");

        assertThat(matcher.matches(get)).isTrue();
        assertThat(matcher.matches(post)).isFalse();
    }
}
```

**Cần kiểm thử snippet trên với version Spring Test/Security cụ thể**: cách `MockHttpServletRequest` biểu diễn path trong `ServletRequestPathUtils` và caching của parsed request path có thể khác test qua Servlet pipeline thật. Nếu test standalone matcher không mô phỏng đúng parser/filter chain, kiểm thử thêm bằng `MockMvc` hoặc embedded servlet container, thay vì mặc định cho rằng matcher có lỗi.

Bộ test cần đối chiếu cả context path, servlet path, pathInfo, `requestURI` và cấu hình MVC. Một matcher true trong test trực tiếp không đủ chứng minh **SecurityFilterChain** chứa matcher đó được chọn ở runtime nếu `@Order`/`securityMatcher` có vấn đề.

## 22. Test full HTTP authorization, không chỉ matches()

Giả sử cấu hình đã giới hạn:
- `GET /api/public/**` cho anonymous.
- `GET /api/reports/{id}` yêu cầu `reports:read`.
- `/api/admin/**` yêu cầu `ROLE_ADMIN`.
- Các route còn lại bị từ chối.

Ma trận test tối thiểu:

| Request | Identity | Kỳ vọng |
| --- | --- | --- |
| `GET /api/public/info` | Anonymous | Cho qua bước HTTP authorization |
| `POST /api/public/info` | Anonymous | DENY nếu không được công khai POST |
| `GET /api/reports/42` | User có `reports:read` | ALLOW HTTP |
| `GET /api/reports/42` | User chỉ có `ROLE_USER` | DENY HTTP |
| `POST /api/reports/42` | User có `reports:read` | DENY nếu chưa có rule |
| `GET /api/admin/users` | User chỉ có `reports:read` | DENY |
| `GET /api/admin/users` | User có `ROLE_ADMIN` | ALLOW HTTP |
| `GET /api/reports/42/` | User có `reports:read` | Kiểm tra theo policy phiên bản/trailing slash |
| `GET /portal/mvc/reports/42` | User có `reports:read`, context+servlet path | Match đúng chain/rule sau migration |
| `GET /api/unknown` | User đã xác thực | DENY nếu default deny |
| `GET /api/reports/999` | User có `reports:read` nhưng khác tenant | DENY ở domain policy |

**Không chỉ test “admin vào được admin”.** Test quan trọng hơn là user thường **không** vào được admin sau migration. Việc path matcher trở nên quá rộng gây bypass thường chỉ bị phát hiện bởi negative tests.

### MockMvc snippet

```java
// Snippet JUnit + Spring Security Test; cần MockMvc, controller và chain thật.
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerCannotEnterAdmin() throws Exception {
    mvc.perform(get("/api/admin/users")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isForbidden());
}

@Test
void readerCanReadReport() throws Exception {
    mvc.perform(get("/api/reports/42")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isOk());
}
```

Cần cung cấp `SimpleGrantedAuthority` và các imports phù hợp, endpoint thực có handler trả 200 khi thành công, không có policy nghiệp vụ nào khác từ chối. Nếu endpoint chưa tồn tại, lỗi 404/405 không chứng minh matcher. Nếu test POST/PATCH và CSRF đang bật, dùng CSRF token hợp lệ để tránh 403 do `CsrfFilter` che lỗi authorization.

### Test trực tiếp SecurityFilterChain

Với nhiều filter chain, thêm integration test chứng minh chain có rule admin thực sự **được chọn** ở URL có servlet prefix. Có thể quan sát behavior của chain hoặc inspection phù hợp qua `FilterChainProxy`, không chỉ status. Hãy kiểm tra request path sau khi container áp dụng context/servlet mapping; lỗi ở cấp `securityMatcher` có thể làm toàn bộ chain bị bỏ qua.

## 23. Vấn đề bảo mật khi context path/servlet path không đồng nhất

Một số cách ứng dụng bị cấu hình sai khi migration:

**Tình huống 1 — context path bị nhân đôi**

```text
Public URL = /portal/api/admin/users
Context root = /portal
Matcher sai = /portal/api/admin/**
Matcher đúng = /api/admin/**
```

**Tình huống 2 — servlet path bị thiếu**

```text
URL = /portal/mvc/api/admin/users
contextPath = /portal
servletPath = /mvc
Legacy MVC pattern = /api/admin/**
Mẫu PathPattern cần chứa servlet = /mvc/api/admin/**
hoặc basePath("/mvc") + matcher("/api/admin/**")
```

**Tình huống 3 — không có fallback chain**

```text
Chain A: securityMatcher("/mvc/api/admin/**")
Chain B: securityMatcher("/mvc/api/**")
Request: /portal/other/path
=> Nếu không chain nào khớp, các filter của hai chain không áp dụng.
```

**Tình huống 4 — legacy wildcard không tương thích**

```text
Legacy Ant matcher có mẫu phức tạp với /**/ ở giữa.
PathPattern phiên bản mới diễn giải khác hoặc parser báo lỗi.
=> Không sửa bằng /**.permitAll() hoặc /api/**.authenticated()
   để "cho chạy"; viết lại mẫu hẹp và kiểm thử theo path thực.
```

**Tình huống 5 — path rewrite ở proxy**

```text
Browser GET /gateway/api/admin/users
Proxy rewrite -> Servlet nhận /api/admin/users
Security matcher phải hiểu request mà Servlet nhìn thấy,
không phải chỉ URL bên ngoài.
```

Những lỗi trên có thể làm route nhạy cảm rơi vào rule tổng quát hoặc ngoài toàn bộ filter chain. Luôn kết hợp **matcher audit + negative authorization tests + runtime path inspection**.

## 24. Nên chọn matcher tường minh hay overload String?

| Tình huống | Lựa chọn thực tế | Lý do |
| --- | --- | --- |
| Spring Security 7, servlet mặc định, đường dẫn đơn giản | `requestMatchers("/api/**")` theo DSL 7 hoặc matcher tường minh | DSL 7 dùng PathPattern; tường minh giúp review rõ |
| Spring Security 6.5 đang chuẩn bị 7 | `PathPatternRequestMatcher.withDefaults()` hoặc opt-in builder | Kiểm tra hành vi parser trước nâng major |
| Custom servlet path `/mvc` | `withDefaults().basePath("/mvc")` | Tránh bỏ servlet prefix khi match |
| Chỉ muốn bảo vệ GET | `matcher(HttpMethod.GET, "/path")` | Không vô tình mở POST/DELETE |
| Hệ thống MVC cũ với legacy code | `MvcRequestMatcher` tạm thời nếu version còn hỗ trợ | Phù hợp branch cũ; cần kế hoạch migration |
| Servlet app cũ không MVC | `AntPathRequestMatcher` tạm thời nếu version còn hỗ trợ | Phù hợp branch legacy; không dùng ở 7 |
| Regex đặc biệt hoặc routing không theo PathPattern | `RegexRequestMatcher`/custom matcher | Khi PathPattern không biểu diễn đúng; cần test chặt |
| Quyền theo owner/tenant của bản ghi | Domain policy hoặc `AuthorizationManager` truy vấn dữ liệu đáng tin | RequestMatcher không thay thế object authorization |

Nhiều hệ thống dùng String matcher vẫn chạy đúng sau upgrade vì request nằm dưới default servlet path. Tuy nhiên, các ứng dụng dùng **non-default servlet mapping**, nhiều chain hoặc wildcard phức tạp cần test cẩn thận hơn.

## 25. Checklist migration từ Ant/MVC matcher sang PathPattern

Trước khi thay version hoặc thay API, thực hiện các bước sau:

1. **Ghi đúng dependency:** `spring-security-web`, `spring-security-config` và Spring Framework MVC đang chạy ở phiên bản nào?
2. **Liệt kê mọi vị trí tạo matcher:** `http.securityMatcher(s)`, `requestMatchers`, filter processing URL, logout/switch user, CORS, web ignoring và matcher do thư viện custom tạo.
3. **Lưu policy dự kiến:** mỗi HTTP method/path cần quyền gì, endpoint nào public, admin, fallback deny?
4. **Kiểm tra servlet setup:** context root, servlet path, MVC controller mapping và reverse-proxy rewrite.
5. **Xác định matcher thực tế trong version cũ:** Ant, MVC, custom hay DSL tự chọn?
6. **Viết PathPattern explicit:** đường dẫn bắt đầu bằng `/`, loại context root, thêm servlet prefix hoặc `basePath`.
7. **Kiểm tra pattern syntax:** wildcard, path variables, pattern phức tạp, dấu slash, encoding và parser config.
8. **Giữ đúng HTTP method:** GET public không biến thành mọi method public.
9. **Giữ đúng rule order:** request matcher cụ thể đứng trước rule tổng quát nếu hai tập path giao nhau.
10. **Giữ đúng chain order:** nếu nhiều chain, chain hẹp đúng `@Order`; có fallback chain khi cần.
11. **Chạy test positive và negative:** anonymous/user/admin/reader; cả route hợp lệ và route bị từ chối.
12. **Chạy test ở path thực:** context + servlet path khác default, reverse proxy/staging, URL edge cases.
13. **Đối chiếu advisory:** đặc biệt các patch Spring Security 7.0 liên quan servlet path.
14. **Không quên domain policy:** cùng authority nhưng khác owner/tenant vẫn phải bị từ chối.
15. **Quan sát và rollback:** có log/audit an toàn cho chain/rule denial, test baseline trước và sau migration.

### Các câu hỏi tự kiểm tra

**Câu 1.** Spring Security 6.5 mới thêm matcher path nào và khuyên di chuyển khỏi hai class cũ nào?  
→ `PathPatternRequestMatcher`; hai class legacy là `AntPathRequestMatcher` và `MvcRequestMatcher`, đang deprecated for removal.

**Câu 2.** Dự án nâng lên Spring Security 7, có thể tiếp tục import `MvcRequestMatcher` để tránh sửa cấu hình không?  
→ **Không**. Spring Security 7 không còn hỗ trợ nó; phải chọn matcher mới và kiểm thử hành vi.

**Câu 3.** App deploy ở `/portal`, Servlet ở `/mvc`, controller `/orders/42`. PathPattern cần nhìn thấy prefix nào?  
→ Match theo `/mvc/orders/42` (bỏ context root `/portal`), hoặc builder `basePath("/mvc")` + `matcher("/orders/{id}")`.

**Câu 4.** Có `requestMatchers("/api/**").authenticated()` trước `requestMatchers("/api/admin/**").hasRole("ADMIN")`. Dùng PathPattern có tự sửa thứ tự không?  
→ **Không**. First-match rule order vẫn áp dụng. Admin matcher phải đứng trước rule API chung.

**Câu 5.** Một test xác nhận matcher khớp `GET /api/documents/42` và user có `document:read`. Điều này đủ bảo vệ tenant không?  
→ **Không**. Phải kiểm tra resource thực, tenant, owner/ACL và trạng thái theo policy.

**Câu 6.** Khi 6.5 dùng `MvcRequestMatcher` trên servlet `/mvc`, sau khi đổi sang PathPattern bằng chuỗi `/reports/**` mà không thêm servlet prefix thì nguy cơ gì?  
→ Matcher có thể không khớp; URL có thể lọt sang rule/chain khác. Phải bổ sung full application path hoặc `basePath("/mvc")` và test.

**Câu 7.** Dự án dùng `securityMatchers(String)` và `PathPatternRequestMatcher.Builder` để prepend servlet path trên Security 7.0.3. Cần làm gì?  
→ Đối chiếu CVE-2026-22753, nâng lên bản patch đã sửa (7.0.5 hoặc cao hơn trong nhánh 7.0), test chain selection và áp dụng mitigation chính thức khi cần.

**Câu 8.** Một thư viện cần bắt endpoint không thể mô tả bằng PathPattern. Có nên dùng `/**.permitAll()` để thay legacy matcher?  
→ **Không**. Cần thiết kế `RegexRequestMatcher`/custom matcher đúng phạm vi, test kỹ và giữ fallback deny.

## Kết luận

`AntPathRequestMatcher` và `MvcRequestMatcher` giải thích nhiều ví dụ trong các ứng dụng Spring Security đời cũ; `PathPatternRequestMatcher` được giới thiệu ở **6.5** và là cơ chế path matching hướng tới **7.x**. Khi chuyển đổi, mấu chốt không chỉ là tên class mà là **URL nào được so khớp**, **path tương đối theo context/servlet**, **HTTP method**, **thứ tự rule**, và **SecurityFilterChain nào được chọn**. Hãy coi migration matcher là thay đổi chính sách bảo mật cần unit/integration tests, không chỉ là refactor cú pháp.

## Tài liệu tham khảo chính thức

1. [Spring Security 6.5 — Web Migrations to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html) — thay `AntPathRequestMatcher`/`MvcRequestMatcher` và xử lý servlet prefix.
2. [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — `securityMatcher`, `requestMatchers`, servlet-path examples.
3. [Spring Security 7.0 — PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html) — `withDefaults`, `PathPatternParser`, context path.
4. [Spring Security 6.5 — AntPathRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/AntPathRequestMatcher.html) — legacy semantics và deprecation.
5. [Spring Security 6.5 — MvcRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/MvcRequestMatcher.html) — `HandlerMappingIntrospector`/servlet path.
6. [Spring Security 7.0 — PathPatternRequestMatcher.Builder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html) — `basePath` và method-specific matcher.
7. [Spring Security Advisory — CVE-2026-22753](https://spring.io/security/cve-2026-22753/) — phạm vi version và bản vá cho matcher servlet path.
8. [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html) — integration tests cho authorization.
