# PathPatternRequestMatcher và điều kiện áp dụng theo phiên bản

> **Phạm vi:** Spring Security trên **Servlet stack**, Java 17+, Spring Boot 3.x/Spring Security 6.x và quá trình chuyển sang các phiên bản mới. Bài tập trung vào `org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher`: chức năng, cú pháp đường dẫn, cách tạo bằng builder, phân biệt với `AntPathRequestMatcher` / `MvcRequestMatcher`, ranh giới `contextPath`–`servletPath`, điều kiện tương thích phiên bản, những thay đổi trong hệ thống match URL và cách kiểm thử. **Không coi PathPatternRequestMatcher là API hiện diện trong mọi Spring Security 6.x.** Ví dụ Spring là mã cho một project có dependency đầy đủ; ví dụ Java 17 ở mục cuối chạy độc lập.

## 1. RequestMatcher nằm ở đâu trong bảo mật HTTP?

`RequestMatcher` trả lời một câu hỏi hẹp: **HTTP request hiện tại có thỏa một điều kiện nhận diện hay không?** Điều kiện có thể liên quan tới path, HTTP method, servlet path hoặc thành phần request khác tùy implementation.

Trong Spring Security Servlet, matcher được dùng ở ít nhất hai cấp:

~~~text
Client HTTP request
         |
         v
FilterChainProxy
   |-- SecurityFilterChain #1  -- securityMatcher: /api/**
   |         |
   |         +-- CSRF, authentication, authorization, ...
   |               |
   |               +-- authorizeHttpRequests
   |                   GET  /api/orders/{id} -> ORDER_READ
   |                   POST /api/orders/{id} -> ORDER_WRITE
   |                   anyRequest()         -> denyAll
   |
   |-- SecurityFilterChain #2  -- match còn lại
   |         |
   |         +-- web/session/fallback policy
   |
   v
Controller nếu vượt qua security filters
~~~

Hai mức này rất khác:

- `http.securityMatcher(...)` quyết định **SecurityFilterChain nào** bao phủ request. Nếu không chain nào match, request có thể đi qua mà không chịu các filter của Spring Security, tùy cấu hình.
- `authorizeHttpRequests(...).requestMatchers(...)` quyết định **rule authorization nào** được dùng **bên trong chain đã được chọn**.
- Một `RequestMatcher` có thể được dùng cho cả hai cấp, nhưng đặt ở cấp nào làm thay đổi tác động. Thay `securityMatcher` bằng `requestMatchers` không chỉ là đổi tên API.
- Một `RequestMatcher` **không tự xác thực người dùng**, không tự kiểm tra role/scope và cũng không bảo đảm controller route tồn tại. Authorization manager mới xét `Authentication` và rule khi request đã khớp.

Ví dụ, nếu HTTP URL `/api/orders/42` match matcher nhưng user không có `ORDER_READ`, matcher vẫn hoạt động đúng; **authorization** mới trả lời có được đi tiếp hay không.

## 2. Tại sao Spring Security có nhiều kiểu path matcher?

Hệ sinh thái Spring từng sử dụng cách khớp đường dẫn theo ký tự (`AntPathMatcher` và `AntPathRequestMatcher`) và cách dùng routing của Spring MVC (`MvcRequestMatcher` với `HandlerMappingIntrospector`). Spring Framework hiện đại có `PathPatternParser` / `PathPattern` để parse mẫu URL trước, sau đó match theo cấu trúc path segment thay vì chỉ so chuỗi kiểu cũ.

`PathPatternRequestMatcher` là thành phần thuộc **Spring Security Web Servlet** dựa trên cơ chế `PathPattern` của Spring Framework. Lợi ích của hướng này:

- Dùng mô hình path pattern đã được parse và tối ưu cho request-path matching.
- Cú pháp segment rõ ràng, xử lý wildcard và path variables theo quy tắc nhất quán hơn.
- Dễ khai báo matcher rõ **HTTP method + path** để authorization không vô tình mở các method ghi dữ liệu.
- Phù hợp hướng tiến hóa của Spring MVC/Spring Security khi chuyển khỏi các matcher dạng Ant cũ.

**Điều không đúng:** “Đổi sang PathPatternRequestMatcher sẽ tự làm mọi endpoint an toàn”. Vẫn phải có chain match đúng, rule đúng, nguồn `GrantedAuthority` đáng tin, CSRF/session policy phù hợp và kiểm tra quyền theo đối tượng ở service layer.

## 3. Điều kiện áp dụng theo phiên bản: phải kiểm tra trước khi viết import

Đây là điểm cốt lõi của bài.

| Môi trường | Tình trạng / hướng xử lý |
| --- | --- |
| Spring Security 6.0–6.4 | Không nên giả định có class `PathPatternRequestMatcher`. Dùng API matcher **được phiên bản đó hỗ trợ**, ví dụ cấu hình `requestMatchers(...)` phù hợp MVC/Servlet; khi di trú cần đánh giá lại semantics. |
| Spring Security 6.5.x | `PathPatternRequestMatcher` có mặt trong các bản Spring Security mới thuộc nhánh 6; có thể dùng **explicit matcher** cùng builder theo API tương ứng. Kiểm tra đúng bản 6.5.x và dependency resolve thực tế. |
| Spring Security 7.x | Hướng API mới ưu tiên matcher theo `PathPattern`; các matcher cũ có thể đã bị thay thế hoặc không còn được hỗ trợ như ở 6.x. Khi nâng major, đọc migration guide của bản cụ thể và chạy regression tests. |
| Spring Boot 3.x | Boot 3.x **không đồng nghĩa** “Security 6.5”. Minor Boot khác nhau quản lý các bản Security 6.x khác nhau. Ví dụ dùng `PathPatternRequestMatcher` chỉ biên dịch khi dependency Security thực sự chứa class. |
| Spring Boot 4.x hoặc project quản lý dependency riêng | Không suy ra API từ version Boot một cách mù quáng; xác minh version thực của `spring-security-web` và `spring-security-config`. |

**Ghi nhớ về mốc:** class này được đưa vào nhánh **Spring Security 6.5**; vì vậy code mẫu `PathPatternRequestMatcher.withDefaults()` có thể **không biên dịch trên Spring Security 6.4 hoặc cũ hơn**. Nếu build báo `cannot find symbol: PathPatternRequestMatcher`, trước hết kiểm tra version/dependency thay vì tự sửa package dựa trên một snippet trên mạng.

Cách kiểm tra dependency đã resolve trong dự án Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

Ví dụ Gradle với Java plugin:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Có thể lọc output theo các artifact `spring-security-web`, `spring-security-config` và `spring-security-core`. Output command thay đổi theo dự án; không đưa ra một transcript cố định. Nếu dùng Spring Boot dependency management/BOM, ưu tiên quản lý **đồng bộ toàn bộ Spring Security artifacts**. Tránh nâng riêng `spring-security-web` lên 6.5 rồi giữ `spring-security-config` cũ, vì sẽ tạo tổ hợp không được thiết kế cùng nhau.

Cũng cần phân biệt **deprecation** với **removal**:

- “Deprecated trong nhánh 6.x” có nghĩa IDE khuyến nghị chuyển dần; không đồng nghĩa API đột ngột biến mất trên chính bản đang chạy.
- “Removed trong major mới” đòi sửa import/cấu hình khi nâng cấp.
- Chọn đường di trú theo **migration guide đúng phiên bản** thay vì đoán dựa trên bài viết dành cho bản khác.

### Vấn đề thư viện và Java version

PathPatternRequestMatcher nằm trong artifact Spring Security Web (Servlet). Một class không tìm thấy có thể do:

1. Security version thấp hơn mốc hỗ trợ.
2. Chưa kéo đúng dependency `spring-security-web`.
3. IDE cache/language server chưa cập nhật dependency.
4. BOM hoặc dependency override tạo version mismatch giữa các module.
5. Đang code cho WebFlux reactive stack thay vì Servlet.

`PathPatternRequestMatcher` nói ở đây là API Servlet. Với Spring WebFlux, security chain và matcher là API khác (`ServerWebExchangeMatcher`); không copy nguyên import Servlet vào reactive stack.

## 4. Cú pháp PathPattern: hiểu theo từng segment

Spring Framework `PathPatternParser` hỗ trợ các dạng mẫu hữu ích:

| Pattern | Ý nghĩa dự kiến |
| --- | --- |
| `/api/orders` | Khớp path cụ thể. |
| `/api/orders/{id}` | Có một segment đại diện cho biến `id`. |
| `/api/orders/*` | Một đoạn wildcard trong cùng một path segment. |
| `/api/orders/**` | Phần đường dẫn còn lại; được dùng **cuối pattern**. |
| `/api/orders/{*rest}` | Bắt phần còn lại vào biến path (khi cần). |
| `/files/{name:[a-z0-9-]+}` | Path variable có regex constraint. |
| `/docs/?.pdf` | `?` đại diện một ký tự trong một segment theo cú pháp hỗ trợ. |

Điểm khác biệt quan trọng với Ant-style patterns: **`**` và `{*variable}` chỉ được đặt ở cuối pattern** trong `PathPattern`; mô hình này tránh một số kiểu match nhập nhằng ở giữa đường dẫn.

Ví dụ có vấn đề khi chuyển từ Ant-style:

~~~text
/archives/**/download
~~~

Không mặc định chuyển nguyên chuỗi đó sang `PathPatternRequestMatcher`. Trong cú pháp `PathPattern`, `**` không được dùng giữa pattern như trên. Hãy thiết kế lại route/matcher, có thể bằng nhiều pattern cụ thể hoặc cấu trúc path rõ ràng, rồi test dữ liệu thực tế.

### Phân biệt `*`, `**` và `{id}`

- `{id}` đại diện một path variable; với `/orders/{id}`, giá trị id không phải tự động chứng minh quyền sở hữu đơn hàng.
- `*` match ký tự trong phạm vi một segment, không có ý nghĩa tùy ý băng qua nhiều dấu slash giống `**`.
- `**` ở cuối có thể match các path segment nằm bên dưới prefix; độ chính xác ở ranh giới slash/trailing slash tùy parser settings phải được kiểm tra.
- `{*rest}` lấy nhiều segment còn lại cho mục đích pattern, nhưng application code vẫn phải xác minh/tách quyền phù hợp.
- `?` bên trong pattern là wildcard **một ký tự**, không phải query string; dấu hỏi thực trong URL sau phần path là query delimiter và không được đưa vào path pattern theo cách dùng thông thường.

Ví dụ:

~~~text
Request: GET /api/orders/42?tab=history

Path dùng cho matching: /api/orders/42
Query string: tab=history

Pattern: /api/orders/{id}
=> phù hợp về path (nếu method cũng đúng)
~~~

Dùng query parameter để điều khiển quyền là vấn đề riêng: nếu token/key chỉ có quyền xem đơn hàng của bản thân, việc path khớp và query đúng cú pháp **chưa đủ** để cho đọc một resource khác.

### Encoding, dấu slash và case

Với path encoded, dấu `%2F`, dấu `;` (matrix parameters), Unicode normalization, repeated slashes, dấu backslash và ký tự bất thường, **không tự đoán kết quả match từ string URL raw**. Servlet container, firewall, proxy và PathPatternParser có thể canonicalize, chặn hoặc parse theo lớp khác nhau. Khi cấu hình strict firewall, một số request nguy hiểm có thể bị từ chối **trước khi matcher chạy**.

Do đó, các test cần xác minh trên đúng môi trường triển khai và không dựa vào một ý tưởng đơn giản như “decode một lần là đủ”. Với hệ thống có custom `HttpFirewall`, path normalization và proxy rewriting, phải test end-to-end.

## 5. Tạo PathPatternRequestMatcher bằng builder

Với bản Spring Security có hỗ trợ class, ví dụ Spring Security 6.5+, hãy dùng builder:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

// MẢNH MÃ bên trong method trong ứng dụng Spring Security hỗ trợ API này:
PathPatternRequestMatcher.Builder paths =
        PathPatternRequestMatcher.withDefaults();

RequestMatcher allApi = paths.matcher("/api/**");
RequestMatcher getOrder = paths.matcher(
        HttpMethod.GET, "/api/orders/{id}");
RequestMatcher postOrder = paths.matcher(
        HttpMethod.POST, "/api/orders/{id}");
~~~

Đây là **mảnh code**, không phải class Java độc lập. Phương thức builder `matcher(...)` tạo `RequestMatcher` để truyền vào DSL. Không có dependency Spring Security tương thích thì không thể chỉ dùng `javac` để biên dịch.

**Vì sao dùng matcher object explicit?**

- Nó biểu lộ lựa chọn `PathPattern` thay vì phụ thuộc cơ chế DSL tự suy luận từ string.
- Nó tái sử dụng một chính sách path/method rõ ràng ở `securityMatcher` và `authorizeHttpRequests`.
- Nó tránh việc project nâng dependency, có MVC hay không có MVC, rồi `requestMatchers("/...")` được chuyển sang matcher implementation khác mà developer không nhận ra.
- Có thể unit test matcher trước khi áp dụng vào HTTP authorization.

Tuy nhiên **explicit matcher không tự thay thế việc kiểm tra nguồn danh tính/authority**. Để bảo vệ `GET /api/orders/42`, cần authorization rule như `hasAuthority("ORDER_READ")` hoặc manager kiểm tra resource owner, không chỉ tạo matcher.

### Matcher có HTTP method và matcher không có HTTP method

~~~java
RequestMatcher anyMethod = paths.matcher("/api/orders/{id}");
RequestMatcher getOnly = paths.matcher(
        HttpMethod.GET, "/api/orders/{id}");
~~~

Đích khác nhau:

- `anyMethod` chỉ nói về path; nếu dùng cho `permitAll()` có thể mở cả POST/DELETE cùng path.
- `getOnly` chỉ phù hợp `GET` tại path đó; POST phải match rule khác hoặc fallback.
- Một matcher **không chứa method** có thể hữu ích ở **chain selection** nếu cả API GET/POST đều cần cùng một security chain.
- Với **authorization ghi dữ liệu**, dùng matcher method-specific để tránh cho quyền READ tự bảo vệ endpoint WRITE.

**Không đưa thông tin HTTP method vào path string** kiểu `"GET /api/orders/**"`; đó không phải cú pháp hợp lệ để match method. Sử dụng overload nhận `HttpMethod`.

## 6. Context path, servlet path và basePath khác nhau

Một request Java Servlet có nhiều phần khác nhau:

~~~text
URL từ client:
https://service.example.test/shop/mvc/api/orders/42?view=full

Context path: /shop              (ứng dụng được deploy dưới /shop)
Servlet path: /mvc               (DispatcherServlet có prefix /mvc)
Path còn lại: /api/orders/42     (phụ thuộc servlet mapping)
Query: view=full
~~~

Quy tắc cần nhớ:

- `contextPath` không phải phần được nhúng vào mẫu path nội bộ cho `PathPatternRequestMatcher`. Pattern thường viết **relative to context path**, ví dụ `/api/orders/{id}` khi không có servlet prefix.
- Khi DispatcherServlet được map với **servlet path prefix**, cần biết matcher đang dùng base path nào. Builder có `basePath(...)` để tạo matcher có prefix thích hợp cho servlet path.
- `basePath("/mvc")` là prefix theo servlet/URL routing, **không phải một lời mời thêm contextPath**.
- Không tự động dùng `request.getRequestURI()` rồi so `startsWith(...)` với pattern; cách so đó có thể nhầm context path, servlet path, encoding và query string.

Ví dụ minh họa khi Servlet được map ở `/mvc/*`:

~~~java
// MẢNH CẤU HÌNH minh họa:
// basePath áp dụng cho các matcher tạo từ builder này.
var mvcPaths = PathPatternRequestMatcher.withDefaults()
        .basePath("/mvc");

RequestMatcher readOrder = mvcPaths.matcher(
        HttpMethod.GET, "/api/orders/{id}");
~~~

Nếu ứng dụng không cấu hình servlet prefix, dùng builder mặc định `withDefaults()` trong ví dụ ở mục 9. **Không copy `basePath("/mvc")` vào app root một cách máy móc.**

Thực tế, một app có thể chạy dưới context path khác nhau ở dev/staging/prod, hoặc reverse proxy rewrite một số prefix. Kiểm thử nên có cả:

1. Request trong app root.
2. Request với contextPath khác root.
3. Request với Servlet path prefix nếu có cấu hình đó.
4. Request qua reverse proxy đúng trusted forwarded headers.
5. Path escaped/unicode/trailing slash thuộc yêu cầu nghiệp vụ.

Đặc biệt, context path và servlet path có thể khiến một matcher trông đúng khi test bằng `MockHttpServletRequest` đơn giản nhưng thất bại trên container thực. Dùng MockMvc/integration test với cấu hình servlet mapping càng gần production càng tốt.

## 7. Giữ PathPatternParser đồng bộ với Spring MVC

`PathPatternRequestMatcher` dùng logic parse `PathPattern`. Nếu Spring MVC/Servlet routing được cấu hình bằng một `PathPatternParser` khác mặc định (ví dụ case sensitivity hoặc một số tùy chọn path matching), security matcher và MVC handler mapping có thể **không đồng ý** về đường dẫn nào hợp lệ.

Điều này dẫn tới hai loại lỗi:

- **False deny:** Controller có thể phục vụ URL nhưng security matcher không xem đó là route hợp lệ, dẫn đến 403/401.
- **False permit:** Security cho phép vì matcher rộng/normalize khác, còn MVC có thể map request vào một handler nhạy cảm theo quy tắc riêng. Trường hợp này nguy hiểm hơn nếu rule mở quá rộng.

Nguyên tắc triển khai:

- Nếu MVC dùng parser chuẩn mặc định, `withDefaults()` là điểm bắt đầu hợp lý cho bản Spring Security hỗ trợ.
- Nếu MVC có parser tùy chỉnh, hãy xem API tạo matcher với cùng `PathPatternParser` của phiên bản đang dùng và bảo đảm cấu hình được chia sẻ một cách **có chủ ý**.
- Không cần bịa một factory method hoặc `@Bean` không tồn tại ở bản Security đang chạy; kiểm tra Javadoc/source của **đúng version**.
- Viết test để chứng minh request **được phép bởi security** khớp controller handler đúng và request **bị chặn bởi policy** không lọt vào handler nhạy cảm.

Một matcher path không kiểm tra query string hay request body. Nếu các field đó quyết định quyền truy cập, kiểm tra ở service/application policy riêng, không cố hack một pattern path để diễn đạt mọi điều kiện.

## 8. Kết hợp với authorizeHttpRequests: thứ tự rule

Giả sử ta muốn:

- GET `/api/orders/{id}`: cần `ORDER_READ`.
- POST `/api/orders/{id}`: cần `ORDER_WRITE`.
- GET `/api/status`: public.
- Các request `/api/**` khác: deny-all.

~~~java
// MẢNH CẤU HÌNH bên trong SecurityFilterChain:
var path = PathPatternRequestMatcher.withDefaults();

http.securityMatcher(path.matcher("/api/**"))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(path.matcher(
            HttpMethod.GET, "/api/status")).permitAll()
        .requestMatchers(path.matcher(
            HttpMethod.GET, "/api/orders/{id}"))
            .hasAuthority("ORDER_READ")
        .requestMatchers(path.matcher(
            HttpMethod.POST, "/api/orders/{id}"))
            .hasAuthority("ORDER_WRITE")
        .anyRequest().denyAll());
~~~

Đọc từng tầng:

1. `securityMatcher("/api/**")` về ý nghĩa giúp chọn chain cho API, không tự cấp mọi request trong prefix.
2. Những matcher trong `authorizeHttpRequests` nhận cả HTTP method.
3. `anyRequest().denyAll()` áp dụng với các request đã match chain nhưng chưa có authorization rule trước đó.
4. Nếu URL **không match** security chain này, `anyRequest()` bên trong chain ấy **không bao phủ** URL đó. Phải có chain khác hoặc fallback policy.

### Thứ tự security chain

Với nhiều bean `SecurityFilterChain` có `@Order`, chain đầu tiên có matcher phù hợp được chọn. Một chain `/**` quá rộng đứng trước `/api/**` có thể khiến request API dùng policy browser không mong muốn.

~~~text
Order(1): /api/** -> API matcher và ORDER_READ/WRITE policy
Order(2): còn lại -> denyAll hoặc web security policy
~~~

Đừng lấy matcher `/api/**` rồi cho rằng nó khớp cả `/internal/api/**` hoặc một proxy prefix được inject vào sai chỗ. Nếu cần hai entrypoint khác nhau, khai báo rõ cả hai trong chính sách deployment và test mỗi entrypoint.

### Thứ tự requestMatchers bên trong chain

Trong request registry thông thường, **rule đầu tiên khớp request** quyết định authorization manager. Vì vậy:

~~~java
// PHẢN VÍ DỤ: quá rộng, mọi GET /api/orders/... đều được
// permitAll trước khi rule ORDER_READ được xét.
.requestMatchers(path.matcher(
    HttpMethod.GET, "/api/**")).permitAll()
.requestMatchers(path.matcher(
    HttpMethod.GET, "/api/orders/{id}"))
    .hasAuthority("ORDER_READ")
~~~

Cách đúng là rule cụ thể trước, rule chung/fallback sau. Đừng dùng `anyRequest().authenticated()` sớm rồi hy vọng các rule có role cụ thể vẫn chạy phía sau.

## 9. Dự án Spring Boot 3 + Spring Security 6.5+: ví dụ đầy đủ

Ví dụ dưới đây **yêu cầu dependency `spring-security-web` hỗ trợ `PathPatternRequestMatcher`**, cụ thể dòng Security **6.5+** hoặc version mới tương ứng. Nếu project Boot của bạn vẫn resolve Security 6.4 hoặc cũ hơn, **không copy code này rồi kỳ vọng build chạy**. Hãy nâng bộ dependency theo BOM đã được kiểm thử, hoặc dùng giải pháp matcher có sẵn trong phiên bản đó.

### 9.1. Dependencies

Dùng Spring Initializr tạo project **Servlet web** dùng JDK 17+. Cần:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-test     (test scope)
spring-security-test        (test scope)
~~~

Tùy Boot minor, chọn bản có Security 6.5+ tương thích. Đừng ghép thư viện của Spring Boot 3 với artifact Spring Security 7 một cách tùy tiện chỉ để có class. Mã ở đây dùng cấu hình không tắt CSRF trên API test để minh họa rằng **authorization của POST** và **CSRF** là hai lớp riêng.

Đặt source Java dưới `src/main/java/com/example/pathmatcher/` và test dưới `src/test/java/com/example/pathmatcher/`.

### 9.2. SecurityConfig.java

~~~java
package com.example.pathmatcher;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-demo-only"))
                .authorities("ORDER_READ")
                .build();

        UserDetails writer = User.withUsername("writer")
                .password(encoder.encode("writer-demo-only"))
                .authorities("ORDER_WRITE")
                .build();

        return new InMemoryUserDetailsManager(reader, writer);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        PathPatternRequestMatcher.Builder paths =
                PathPatternRequestMatcher.withDefaults();

        http
            // Chọn chain API trước, không cấp quyền từ matcher này.
            .securityMatcher(paths.matcher("/api/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(paths.matcher(
                    HttpMethod.GET, "/api/status")).permitAll()

                .requestMatchers(paths.matcher(
                    HttpMethod.GET, "/api/orders/{id}"))
                    .hasAuthority("ORDER_READ")

                .requestMatchers(paths.matcher(
                    HttpMethod.POST, "/api/orders/{id}"))
                    .hasAuthority("ORDER_WRITE")

                // Phủ định các request API chưa có rule rõ ràng.
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF trong ví dụ: POST phải có token.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Điểm cần học:

- `@Order(1)` và `@Order(2)` áp dụng thứ tự **các bean SecurityFilterChain**. Không phải thứ tự của những rule bên trong `authorizeHttpRequests`.
- Builder `withDefaults()` tạo matcher kiểu PathPattern explicit, không dựa vào Spring MVC `HandlerMappingIntrospector`.
- Method-specific matcher làm rõ quyền đọc/ghi, còn matcher chain nhận cả `/api/**` để tất cả request API dùng một tập filter tương ứng.
- `.anyRequest().denyAll()` là chính sách an toàn với URL/method chưa được phê duyệt.
- Bean fallback không bao gồm authentication mechanism nên các request bên ngoài `/api/**` bị từ chối; nếu ứng dụng cần web UI, phải thiết kế chain thứ hai có login/session/CSRF và authorization riêng.
- `httpBasic(...)` phục vụ demo và kiểm thử đơn giản. Production có thể dùng OAuth2 resource server/JWT nhưng phải xác thực token, issuer, audience, scopes đúng.
- `reader` chỉ có `ORDER_READ`, `writer` chỉ có `ORDER_WRITE`; một role tổng quát không mặc nhiên bao hàm permission khác.
- Chỉ dùng password demo ở localhost/test, không đặt credential có thật trong source.

### 9.3. OrderController.java

~~~java
package com.example.pathmatcher;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/status")
    public String status() {
        return "ready";
    }

    @GetMapping("/api/orders/{id}")
    public String readOrder(@PathVariable String id) {
        return "read:" + id;
    }

    @PostMapping("/api/orders/{id}")
    public String updateOrder(@PathVariable String id) {
        // Demo: không thực sự sửa DB.
        return "write:" + id;
    }
}
~~~

**Lưu ý authorization theo tài nguyên:** matcher chỉ biết path có dạng `/api/orders/{id}`, không chứng minh người đọc có quyền xem **đơn hàng id này**. Trong production, service phải kiểm tra owner/tenant/permission trước khi đọc/ghi bản ghi. Không nhận định ID do client gửi “đã đáng tin” chỉ vì nó khớp regex hay path pattern.

### 9.4. PathMatcherApplication.java

~~~java
package com.example.pathmatcher;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathMatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathMatcherApplication.class, args);
    }
}
~~~

Đặt các class trong cùng package hoặc đúng package scan của `@SpringBootApplication`. Không khai báo thêm một default chain khác có matcher rộng và `@Order` ưu tiên cao hơn chain API này.

### 9.5. Chạy demo

Với project Maven Wrapper đã resolve Security 6.5+ và Java 17+:

~~~bash
./mvnw spring-boot:run
~~~

Request public:

~~~bash
curl -i http://localhost:8080/api/status
~~~

Request quyền đọc (chỉ credential demo localhost):

~~~bash
curl -i -u reader:reader-demo-only \
  http://localhost:8080/api/orders/42
~~~

Kết quả logic mong đợi khi đã chạy server: `GET /api/status` trả `200` cùng body `ready`; `GET /api/orders/42` với reader trả `200`, body `read:42`. Writer **không tự có ORDER_READ** nên GET endpoint đọc với writer không có quyền và thông thường bị `403`.

Không đưa stdout HTTP headers cố định vì chúng còn phụ thuộc server, entry point và container. Command line `curl -u` có thể làm lộ mật khẩu trong process/history; chỉ dùng credential giả ở localhost. Trong production dùng secret handling phù hợp.

Đừng vội dùng `curl -X POST` rồi suy rằng Security rule sai khi thấy 403: POST còn phải đi qua **CsrfFilter** của ví dụ này. Bộ MockMvc ở mục tiếp sẽ tách hai điều kiện.

## 10. MockMvc: test PathPattern, HTTP method và authorization thực sự

Tạo `src/test/java/com/example/pathmatcher/PathPatternAuthorizationTest.java`:

~~~java
package com.example.pathmatcher;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PathPatternAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void statusIsPublicInsideApiChain() throws Exception {
        mvc.perform(get("/api/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void readerMayReadSingleSegmentOrderId() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("read:42"));
    }

    @Test
    void writerPermissionDoesNotImplyRead() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postUsesSeparateWritePermission() throws Exception {
        mvc.perform(post("/api/orders/42")
                .with(csrf())
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("write:42"));

        mvc.perform(post("/api/orders/42")
                .with(csrf())
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postStillNeedsCsrf() throws Exception {
        mvc.perform(post("/api/orders/42")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void extraPathSegmentCannotMatchSingleIdPattern()
            throws Exception {
        mvc.perform(get("/api/orders/42/extra")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void queryStringIsNotAnotherPathSegment() throws Exception {
        mvc.perform(get("/api/orders/42")
                .queryParam("view", "history")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("read:42"));
    }

    @Test
    void methodsOutsideDeclaredPolicyAreDenied() throws Exception {
        mvc.perform(delete("/api/orders/42")
                .with(csrf())
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCannotReadPrivateOrder() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Giải thích test:**

1. `statusIsPublic...` kiểm tra matcher trong API chain vẫn cho phép một route public.
2. `readerMayRead...` kiểm tra path có đúng một segment `id` và authority `ORDER_READ`.
3. `writerPermissionDoesNotImplyRead` chứng minh `ORDER_WRITE` không tự cấp `ORDER_READ`.
4. `postUsesSeparateWritePermission` kiểm tra **POST matcher khác GET matcher**, dùng `.with(csrf())` để chắc rằng các kết quả 200/403 đến từ authorization.
5. `postStillNeedsCsrf` cho thấy HTTP method/path/permission match chưa đủ nếu CSRF đang bật.
6. `extraPathSegment...` bảo đảm `/api/orders/{id}` không vô tình match thêm segment `/extra`; fallback `denyAll` chặn request trước MVC.
7. `queryStringIsNotAnotherPathSegment` cho thấy query parameter không phải một phần của pattern path, nhưng controller vẫn phải kiểm tra query semantics nếu nó ảnh hưởng nghiệp vụ.
8. `methodsOutsideDeclaredPolicy...` chứng minh quyền WRITE cho POST không đồng nghĩa quyền DELETE.
9. `anonymousCannotRead...` kiểm tra entry point của Basic authentication; trong app dùng form login, unauthenticated response có thể là redirect thay vì 401.

**Không nên coi một status 403 là đủ:** nếu test POST thiếu CSRF, `CsrfFilter` có thể đã từ chối trước `AuthorizationFilter`. Với test security matcher, hãy thêm CSRF để đi vào tầng authorization khi muốn khẳng định role/authority.

Khi nâng Spring Security hoặc đổi MVC path matching mode, chạy toàn bộ test này cùng các test encode/trailing slash/servlet prefix/forwarded headers. Test ở môi trường MockMvc giả lập **không chứng minh mọi proxy/container sẽ canonicalize URL giống nhau**; request end-to-end vẫn hữu ích.

Chạy:

~~~bash
./mvnw test
~~~

Không bịa stdout của Maven và không khẳng định test đã được chạy chỉ vì code trông hợp lệ. Bài cung cấp mã kiểm thử và kỳ vọng; kết quả thực tế còn phụ thuộc dependency được resolve và ứng dụng cấu hình đúng.

## 11. Di trú từ AntPathRequestMatcher và MvcRequestMatcher

### 11.1. Bước 1 — Khoanh toàn bộ matcher thực tế

Tìm trong code cấu hình:

~~~text
AntPathRequestMatcher
MvcRequestMatcher
requestMatchers("...")
securityMatcher("...")
logoutRequestMatcher(...)
csrf().ignoringRequestMatchers(...)
FilterChainProxy / SecurityFilterChain
PathPatternRequestMatcher
~~~

Không thay chỉ những rule trong `authorizeHttpRequests` mà bỏ sót `securityMatcher`, logout, CSRF exemption, request cache, web ignoring, custom filter và forwarding logic. Những nơi này có thể dùng matcher implementation khác nhau, khiến URL được xử lý không nhất quán.

### 11.2. Bước 2 — Kiểm tra phiên bản trước

Nếu đang dùng Spring Security 6.3/6.4, **chưa** được chuyển import sang `PathPatternRequestMatcher` rồi kỳ vọng IDE tự bổ sung dependency. Kiểm tra BOM, version/compatibility và quyết định:

- Giữ cấu hình matcher đang được hỗ trợ, viết regression tests.
- Hoặc nâng Spring Boot/Spring Security theo lộ trình đã kiểm thử, rồi chuyển matcher theo API mới.

Không nâng một artifact Security một cách riêng lẻ chỉ để hết lỗi import.

### 11.3. Bước 3 — Dịch semantics, không thay tên cơ học

Ví dụ quy tắc Ant-style:

~~~text
/reports/**/download
~~~

Không thể đảm bảo chuyển nguyên pattern sang PathPattern mà parser chấp nhận, vì `**` ở giữa bị hạn chế. Thiết kế lại route để đặt wildcard cuối hoặc dùng những pattern rõ hơn. Sau đó liệt kê các URL hợp lệ/bất hợp lệ theo nghiệp vụ và test.

**Không** thay bằng `/reports/**` rồi `permitAll` để “không lỗi parser” — đó là mở rộng phạm vi truy cập, có thể tạo lỗ hổng.

### 11.4. Bước 4 — Đối chiếu servlet mapping với MVC

`MvcRequestMatcher` cũ tận dụng thông tin handler matching của Spring MVC qua `HandlerMappingIntrospector`. Khi chuyển sang `PathPatternRequestMatcher` explicit, bạn cần tự bảo đảm đúng `basePath` và parser tương thích với MVC. Nếu ứng dụng có multiple servlets, `/mvc`, `/api` hoặc servlet custom, cần test từng mapping, không giả định một builder áp dụng mọi servlet.

### 11.5. Bước 5 — Phân quyền theo method

Chuyển:

~~~java
// Cấu hình cũ quá rộng về HTTP method:
.requestMatchers("/orders/**").hasAuthority("ORDER_READ")
~~~

thành những rule riêng:

~~~java
// Ví dụ ý tưởng khi đã có builder paths:
.requestMatchers(paths.matcher(
    HttpMethod.GET, "/orders/{id}")).hasAuthority("ORDER_READ")
.requestMatchers(paths.matcher(
    HttpMethod.POST, "/orders/{id}")).hasAuthority("ORDER_WRITE")
.requestMatchers(paths.matcher("/orders/**")).denyAll()
~~~

**Đây là mảnh code trong authorizeHttpRequests**, không phải Java class độc lập. Nếu API có PATCH/DELETE, phải định nghĩa quyền riêng. Cần tính cả CSRF/authorization theo object ID.

### 11.6. Bước 6 — Kiểm thử regression trước và sau

Để đánh giá di trú, chuẩn bị một **bảng chân trị** cho matcher:

| Request | Rule | Dự kiến |
| --- | --- | --- |
| GET `/api/orders/42` | `GET /api/orders/{id}` | Match |
| POST `/api/orders/42` | `GET /api/orders/{id}` | Không match |
| GET `/api/orders/42/extra` | `GET /api/orders/{id}` | Không match |
| GET `/api/orders/42?tab=1` | `GET /api/orders/{id}` | Match phần path |
| GET `/api/status` | `GET /api/status` | Match |
| DELETE `/api/orders/42` | `POST /api/orders/{id}` | Không match |
| GET `/api/orders/42/` | `GET /api/orders/{id}` | Phụ thuộc trailing-separator policy/parser; cần test thực |
| GET `/api/orders/%2F` | `GET /api/orders/{id}` | Phụ thuộc container/firewall/parser; không suy đoán từ raw URL |

**Phân biệt loại kiểm thử:**

- **Matcher test:** matcher trả true/false với request đã được tạo đúng.
- **Security chain test:** request thuộc chain nào và authorization rule nào được chọn.
- **Controller test:** request thực sự route tới handler nào.
- **Deployment test:** proxy, context path, servlet path, forwarded headers, URL encoding có nhất quán với dự định không.

Một bài “migrate thành công” chỉ vì build xanh nhưng rule cho phép sai URL/method vẫn là thất bại bảo mật.

## 12. Nơi dễ nhầm: regex, trailing slash, fallback và path variables

### 12.1. PathPattern không phải regex Java nguyên chuỗi

Mẫu `/orders/{id}` không tương đương trực tiếp với regex `/orders/(.*)`, bởi regex `.*` có thể ăn dấu slash. Cú pháp segment là mục tiêu của `PathPattern`. Nếu thật sự cần regex cho một variable, sử dụng định dạng `{id:...}` **theo syntax parser được hỗ trợ** và thử trên dữ liệu thực.

Khi parser có pattern invalid, nên để ứng dụng **fail fast** lúc tạo matcher thay vì catch exception rồi cho một pattern rộng hơn “để chạy được”.

### 12.2. Trailing slash không phải mặc định luôn tùy chọn

Đừng kỳ vọng `/api/orders/42` và `/api/orders/42/` luôn giống nhau. Cấu hình Spring Framework, version và parser có thể thay đổi hành vi này, đặc biệt khi chuyển từ matcher cũ. Để làm rõ UX, chọn canonical route và redirect/canonicalize có kiểm soát, tránh mở rộng policy chỉ bằng wildcard quá rộng.

### 12.3. Match path không đồng nghĩa có quyền xem object

`GET /api/orders/{id}` có thể match với `id=42`. Nhưng:

- User chỉ có `ORDER_READ` có được xem **đơn 42** không?
- Đơn thuộc tenant nào?
- Người dùng có ở đúng organization/owner không?
- Resource còn ở trạng thái được phép đọc không?

Các câu hỏi này thuộc **service/resource-level authorization**, không thể giải quyết chỉ với path matcher. Ví dụ service nhận một `Order` và principal đã xác thực, kiểm tra owner/tenant trước khi truy vấn/trao dữ liệu.

### 12.4. Không gán authority từ path variable

Một attacker có thể gọi `/api/orders/ROLE_ADMIN`. Path variable `id` là dữ liệu từ URL, **không** phải `GrantedAuthority`. Không đọc `id` để tạo principal hay roles. Authentication phải lấy từ nguồn đáng tin; authority checks phải diễn ra trên quyền đã xác minh.

### 12.5. Không dùng path matcher thay CSRF firewall

`POST /api/orders/{id}` match đúng và user có `ORDER_WRITE` vẫn có thể bị từ chối vì CSRF. Trong browser session app, đây là điều đúng nếu POST thiếu token; không tắt CSRF để "sửa" 403. Ngược lại, CSRF đúng không có nghĩa user được quyền WRITE.

### 12.6. Multiple filters và request dispatch

Một request có thể đi qua forward/error/async dispatch và URL được trình bày khác nhau tùy servlet container. Với custom filters và nhiều dispatcher types, kiểm tra matcher có xử lý đúng dispatch type và tránh một route nội bộ không được xét authorization khi forward sang handler khác. Không giải quyết một lỗi 403 bằng cách `permitAll("/**")` ở tầng broad.

## 13. Java 17 độc lập: mô phỏng ranh giới path và method

Mã `PathPolicyDemo.java` sau đây **không triển khai PathPatternParser**, không phải `RequestMatcher` thật, không giải mã URL và không khẳng định hỗ trợ mọi chi tiết cú pháp Spring. Nó chỉ giúp nhìn rõ “GET có quyền READ, POST có quyền WRITE, path chỉ có một id segment, query không phải path”.

~~~java
public final class PathPolicyDemo {

    static String choose(String method, String path) {
        if ("GET".equals(method) && "/api/status".equals(path)) {
            return "PUBLIC";
        }

        String[] segments = path.split("/", -1);

        // "/api/orders/42" -> ["", "api", "orders", "42"].
        boolean oneId = segments.length == 4
                && segments[0].isEmpty()
                && "api".equals(segments[1])
                && "orders".equals(segments[2])
                && !segments[3].isEmpty();

        if (oneId && "GET".equals(method)) {
            return "ORDER_READ";
        }
        if (oneId && "POST".equals(method)) {
            return "ORDER_WRITE";
        }
        return "NO_MATCH";
    }

    static void inspect(String method, String path) {
        System.out.println(method + " " + path
                + " -> " + choose(method, path));
    }

    public static void main(String[] args) {
        inspect("GET", "/api/status");
        inspect("GET", "/api/orders/42");
        inspect("POST", "/api/orders/42");
        inspect("DELETE", "/api/orders/42");
        inspect("GET", "/api/orders/42/extra");
        inspect("GET", "/api/orders/");
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac PathPolicyDemo.java
java PathPolicyDemo
~~~

Stdout **chính xác**:

~~~text
GET /api/status -> PUBLIC
GET /api/orders/42 -> ORDER_READ
POST /api/orders/42 -> ORDER_WRITE
DELETE /api/orders/42 -> NO_MATCH
GET /api/orders/42/extra -> NO_MATCH
GET /api/orders/ -> NO_MATCH
~~~

Bài tập: sửa dòng `inspect("POST", "/api/orders/42")` thành `inspect("PUT", "/api/orders/42")`. Kết quả sẽ là `NO_MATCH` vì policy chưa có PUT. Đây là một ví dụ **nhận diện request**; nó không xác thực credential, không kiểm tra authority và không xử lý Spring HTTP pipeline. Quyết định `ORDER_READ`/`ORDER_WRITE` trong chương trình là **nhãn rule**, không phải tuyên bố user đã có quyền tương ứng.

## 14. Bộ câu hỏi kiểm tra kiến thức

**Q1. PathPatternRequestMatcher có sẵn trên mọi Spring Security 6.0–6.4 không?** Không. Đây là API thuộc nhánh mới hơn, bắt đầu từ 6.5; cần kiểm tra dependency `spring-security-web` thực tế.

**Q2. Khi dùng Spring Boot 3.x có thể import PathPatternRequestMatcher ngay không?** Không thể suy luận chỉ từ major Boot. Phải kiểm tra minor Boot quản lý bản Spring Security nào hoặc explicit dependency management đã resolve.

**Q3. `securityMatcher` và `requestMatchers` có cùng chức năng không?** Không. Một cái chọn security chain, cái kia chọn rule authorization bên trong chain.

**Q4. `PathPattern` cho phép `/files/**/download` như Ant pattern không?** Không được giả định. `**` theo PathPattern chỉ được dùng ở cuối pattern; cần thiết kế lại và test.

**Q5. `PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.GET, "/orders/{id}")` có match POST không?** Không. Nó ràng buộc GET; POST cần matcher riêng nếu nghiệp vụ yêu cầu.

**Q6. `/orders/{id}` có tự kiểm tra user được sở hữu đơn hàng id đó không?** Không. Nó chỉ nhận diện path/variable; quyền theo tài nguyên thuộc service/authorization sâu hơn.

**Q7. Khi app triển khai ở context path `/shop`, có nên thêm `/shop` vào mọi pattern không?** Không nên máy móc. Matcher thường so path relative to context path; cần phân biệt servlet prefix và dùng `basePath` khi phù hợp.

**Q8. Vì sao build xanh sau migration chưa đủ?** Có thể path patterns match khác trước, security chain đổi thứ tự, CSRF exemptions rộng hơn hoặc authorization rule match sai. Cần bảng chân trị và integration tests.

**Q9. `GET /api/orders/42?view=full` có query thuộc `PathPattern` không?** Query string không phải phần path matcher trong cách dùng thông thường; kiểm tra thêm business logic nếu query ảnh hưởng quyền.

**Q10. Nếu POST bị 403, có thể kết luận `PathPatternRequestMatcher` không match không?** Không. CSRF filter có thể chặn trước, hoặc matcher match nhưng `hasAuthority` từ chối. Hãy test có CSRF hợp lệ, principal đúng và matched chain.

**Q11. Khi các URL có `%2F` hoặc dấu chấm phẩy, có thể khẳng định parser cho phép dựa trên raw URL không?** Không. Container, firewall, proxy, decoder và parser có thể ảnh hưởng; cần test end-to-end.

**Q12. Vì sao matcher explicit hữu ích khi nâng version?** Nó biểu lộ implementation/path grammar dự định dùng, giảm phụ thuộc vào suy luận tự động của DSL; nhưng vẫn cần test và quản lý dependency đúng.

## 15. Checklist trước khi phát hành

- [ ] Đã xác định bản `spring-security-web`, `spring-security-config`, Spring Framework và Boot thực tế; không đoán từ tên project.
- [ ] Nếu cần `PathPatternRequestMatcher`, bản Security đang dùng thực sự hỗ trợ (nhánh 6.5+ hoặc phiên bản tương ứng).
- [ ] Đã phân biệt Servlet security với WebFlux.
- [ ] Mọi `securityMatcher` match chính xác chain cần bảo vệ, có fallback policy cho những request không thuộc API chain.
- [ ] Matcher `authorizeHttpRequests` tách GET/POST/PUT/PATCH/DELETE khi có tác động khác nhau.
- [ ] Rule cụ thể đứng trước wildcard rộng; `anyRequest().denyAll()` bảo vệ method/URL chưa được duyệt nếu phù hợp kiến trúc.
- [ ] Pattern được kiểm tra theo cú pháp `PathPattern`; không bê nguyên `**` nằm giữa pattern từ Ant.
- [ ] `contextPath`, `servletPath` và `basePath` được hiểu đúng; đã test cả khi app chạy dưới prefix.
- [ ] Nếu MVC dùng parser tùy chỉnh, matcher security và handler mapping cùng semantics hoặc được kiểm thử nhất quán.
- [ ] Có test cho path variable, extra segment, query string, trailing slash và các đường URL lạ theo threat model.
- [ ] CSRF còn được kiểm tra riêng với browser cookie session; không tắt để né test POST thất bại.
- [ ] User/authority được xác thực phía server; matcher path không dùng để cấp role hay bỏ qua resource ownership.
- [ ] Có positive/negative HTTP tests qua MockMvc và deployment tests khi dùng proxy/encoding.
- [ ] Không chỉ nhìn status 403/404 mà bỏ qua lý do: CSRF, authentication entry point, matcher, rule hoặc controller mapping.
- [ ] Không dùng URL wildcard quá rộng/permitAll để xử lý lỗi parser hay version mismatch.
- [ ] Khi nâng major Spring Security, đã review migration guide tương ứng và chạy security regression tests.

**Kết luận:** `PathPatternRequestMatcher` là cách match HTTP request theo **PathPattern** trong **Spring Security Servlet** của các phiên bản hỗ trợ API này. Giá trị lớn nhất là diễn đạt chính xác **path + method** và đồng bộ logic đường dẫn, nhưng nó **không thay thế authorization**. Trước khi sử dụng, hãy kiểm tra **version**, **cú pháp PathPattern**, **contextPath/servletPath**, **security chain order**, **CSRF** và bộ test thực tế. Đừng chuyển matcher kiểu Ant/MVC sang PathPattern bằng thao tác đổi tên class đơn thuần.
