# Chuyển antMatchers, mvcMatchers và RequestMatcher theo dòng phiên bản Spring Security

## 1. Mục tiêu và bối cảnh

Spring Security phân quyền HTTP bằng cách **so khớp request** với một mẫu đường dẫn, phương thức HTTP hoặc điều kiện tùy biến, sau đó kiểm tra vai trò/quyền của người gọi. Khi chuyển phiên bản, nhiều dự án phải thay antMatchers(...) và mvcMatchers(...) bằng requestMatchers(...). Đến Spring Security 7, cơ chế so khớp mặc định tiếp tục chuyển sang PathPatternRequestMatcher. Việc thay đúng tên phương thức chỉ là bước đầu: cùng một chuỗi pattern có thể được diễn giải khác bởi Ant, Spring MVC hoặc PathPattern.

Giả sử hệ thống báo cáo yêu cầu:

- GET /api/reports/42: phải có authority report:read.
- POST /api/reports/42/publish: phải có authority report:publish.
- Người đã đăng nhập nhưng chỉ có report:read không được xuất bản.
- Các đường dẫn và HTTP method chưa khai báo không được tự động mở.

Nếu một migration vô tình biến rule dành cho publish thành authenticated(), kết quả biên dịch có thể thành công trong khi chính sách nghiệp vụ đã sai. Cần **kiểm tra cả khả năng match lẫn quyết định allow/deny**.

Sau bài này, bạn có thể giải thích sự khác nhau giữa RequestMatcher interface, các phương thức DSL cũ antMatchers/mvcMatchers, DSL mới requestMatchers, bộ chọn chain securityMatcher và các hiện thực AntPathRequestMatcher, MvcRequestMatcher, PathPatternRequestMatcher. Bạn cũng có thể viết mã Java 17+ và kiểm thử hồi quy để đi từ Spring Security 5.8 qua 6.x tới 7.x.

**Phạm vi:** Spring MVC/Servlet. Ứng dụng Spring WebFlux sử dụng SecurityWebFilterChain và ServerWebExchangeMatcher, không dùng trực tiếp các matcher Servlet được minh họa ở đây.

## 2. Bản đồ phiên bản từ 5.x đến 7.x

| Phiên bản | API/implementation chính | Việc cần làm |
| --- | --- | --- |
| 5.7 và trước | antMatchers, mvcMatchers, regexMatchers thường gặp trong authorizeRequests; nhiều ứng dụng còn WebSecurityConfigurerAdapter | Kiểm kê cấu hình legacy, thứ tự rule, servlet path và các matcher tùy chỉnh |
| **5.8** | antMatchers/mvcMatchers/regexMatchers được deprecated; requestMatchers mới có mặt | Chuyển từng rule sang requestMatchers trên dòng 5.8 trước khi nâng 6.0, so sánh hành vi |
| **6.0–6.4** | Phương thức DSL antMatchers/mvcMatchers đã bị bỏ; dùng SecurityFilterChain, authorizeHttpRequests, requestMatchers | Sửa code và Jakarta Servlet imports; phân biệt suy luận MVC/Ant trong các quá tải nhận String |
| **6.5** | PathPatternRequestMatcher có sẵn; AntPathRequestMatcher và MvcRequestMatcher bị deprecated for removal | Chuyển dần sang PathPatternRequestMatcher tường minh, chạy kiểm thử ở phiên bản 6.5 |
| **7.x** | AntPathRequestMatcher và MvcRequestMatcher không còn hỗ trợ; matcher từ Java DSL mặc định dùng PathPatternRequestMatcher | Loại bỏ import/lớp cũ, kiểm tra URL bắt đầu bằng /, servlet prefix, wildcard và chính sách quyền |

**Phân biệt sự kiện lịch sử:** Phương thức cấu hình **antMatchers(...)** không còn trong Spring Security 6.0, nhưng **lớp AntPathRequestMatcher** vẫn tồn tại trong phần lớn dòng 6.x và chỉ bị ngừng hỗ trợ khi lên 7. Tương tự, **RequestMatcher** là một **interface** vẫn tồn tại; chỉ những cách tạo matcher và một số implementation thay đổi.

Khi nâng từ Spring Security 5.x lên 6.x, phải xét cả Spring Framework 6, **javax.servlet → jakarta.servlet** và bộ phụ thuộc Spring Boot 3.x. Việc chuyển matcher không thay thế đầy đủ kế hoạch nâng framework; bài này giới hạn trọng tâm vào kiểm soát truy cập Servlet.

## 3. Mô hình quyết định: một request đi qua hai cấp matcher

~~~text
HTTP request
     |
     v
FilterChainProxy
     |
     +-- securityMatcher của mỗi SecurityFilterChain theo thứ tự @Order
     |       |
     |       +-- chain đầu tiên khớp được chọn
     |       +-- không chain nào khớp: request không được chain Spring Security bảo vệ
     |
     v
AuthorizationFilter trong chain đã chọn
     |
     +-- requestMatchers(...) theo thứ tự khai báo
     |       |
     |       +-- rule khớp đầu tiên: hasAuthority / hasRole / permitAll / denyAll
     |       +-- anyRequest(): chính sách cho phần còn lại
     |
     v
Controller / nghiệp vụ (nếu được cho phép)
~~~

**securityMatcher** là bộ lọc xem **cả SecurityFilterChain** có áp dụng cho request không. **requestMatchers** bên trong authorizeHttpRequests chỉ chọn **quy tắc phân quyền** khi chain đó đã được chọn. Đặt anyRequest().denyAll() bên trong một chain chỉ match /api/** **không có nghĩa** các request /admin/** đều bị chặn, vì chain ấy không xử lý /admin.

**RequestMatcher** là interface với phương thức matches(HttpServletRequest), xác định request có khớp điều kiện không. Nó không tự đánh giá người dùng có authority gì. **AuthorizationManager** hoặc rule hasAuthority/hasRole đưa ra quyết định quyền sau khi matcher chọn đúng vùng.

Cần chú ý hai loại thứ tự: **thứ tự các SecurityFilterChain** và **thứ tự các requestMatchers** trong từng chain. Một matcher quá rộng đặt trước matcher nhạy cảm có thể làm rule phía sau không được xét.

## 4. Chuyển API cũ ở Spring Security 5.8 và 6.x

### 4.1. Nhận diện mã cũ

Trong dự án Spring Security 5.7, cấu hình này có thể xuất hiện:

~~~java
// Trích đoạn Spring Security 5.x legacy, không dành cho 6.x/7.x.
http.authorizeRequests(auth -> auth
    .antMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .antMatchers(HttpMethod.POST, "/api/reports/*/publish")
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

Trong dòng 5.8, các phương thức cũ đã được đánh dấu deprecated. Có thể thay bằng requestMatchers trước khi nâng lên 6.x:

~~~java
// Trích đoạn dành cho 5.8+ / 6.x.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .requestMatchers(HttpMethod.POST, "/api/reports/*/publish")
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

Phần quyền report:read và report:publish được giữ nguyên. Tuy nhiên **loại matcher mà requestMatchers(String...) chọn ở 6.x có thể khác** loại Ant mà antMatchers cũ từng dùng. Theo tài liệu Spring Security 6.x, khi có Spring MVC trên classpath, bộ dựng matcher từ String có thể chọn MvcRequestMatcher; nếu không có MVC, có thể chọn AntPathRequestMatcher. Khi có nhiều servlet hoặc cơ chế tự suy luận không đủ chính xác, cần truyền một RequestMatcher tường minh.

**Không mặc định:** requestMatchers("/foo/**") bằng antMatchers("/foo/**") về mọi chi tiết path normalization, dấu gạch chéo, servlet prefix hoặc biến đường dẫn. Các khác biệt phải được đo bằng test trên từng ứng dụng.

### 4.2. authorizeRequests và authorizeHttpRequests

Nhiều migration còn đổi cấu hình authorizeRequests sang **authorizeHttpRequests**, dùng AuthorizationManager và AuthorizationFilter. Ví dụ:

~~~java
// Cấu hình mới: phần bên trong phương thức SecurityFilterChain.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Trong ví dụ, rule /api/admin/** bắt buộc đứng **trước** rule /api/**. Nếu đảo lại, một người dùng đăng nhập thông thường có thể đi qua rule authenticated() trước khi rule ADMIN được xét. Đổi DSL không tự sửa lỗi thứ tự này.

**hasRole("ADMIN")** thường được hiểu là authority ROLE_ADMIN; **hasAuthority("report:read")** kiểm tra chuỗi authority chính xác. Không thay quyền bằng authenticated() chỉ để đơn giản hóa migration.

### 4.3. Ánh xạ cũ → mới theo mục đích

| Mục đích | API trước 6.0 | 5.8/6.x | 6.5+/7.x mục tiêu |
| --- | --- | --- | --- |
| So khớp URL | antMatchers("/admin/**") | requestMatchers("/admin/**") | requestMatchers(PathPatternRequestMatcher.withDefaults().matcher("/admin/**")) |
| URL + HTTP method | antMatchers(GET, "/items/**") | requestMatchers(GET, "/items/**") | requestMatchers(path.matcher(GET, "/items/**")) |
| Spring MVC route | mvcMatchers("/orders/{id}") | requestMatchers("/orders/{id}") hoặc MvcRequestMatcher tường minh trong giai đoạn 6.x | PathPatternRequestMatcher với servlet path rõ ràng |
| Regex | regexMatchers("/x/[0-9]+") | requestMatchers(RegexRequestMatcher.regexMatcher("/x/[0-9]+")) | Có thể tiếp tục dùng RegexRequestMatcher khi cần regex |
| Custom RequestMatcher | Matcher tự cài đặt | requestMatchers(customMatcher) | Giữ interface RequestMatcher, nâng javax sang jakarta và test |
| Chọn security chain | antMatcher(...) / cách cũ trong HttpSecurity | securityMatcher(...) | securityMatcher(PathPatternRequestMatcher) khi cần tường minh |
| Default | anyRequest() | anyRequest() | Giữ denyAll hoặc authenticated theo chính sách đã phê duyệt |

**Lưu ý:** Tại Spring Security 6.x, người cần bảo toàn chính xác matcher Ant cũ có thể truyền AntPathRequestMatcher tường minh như bước chuyển tiếp. Nhưng giải pháp này **không dành cho đích Spring Security 7** vì lớp AntPathRequestMatcher không còn được hỗ trợ ở dòng đó.

### 4.4. Những điều dễ bị bỏ qua khi chỉ thay tên

- Một đoạn code cũ có thể dùng **mvcMatchers** vì cần ngữ nghĩa khớp controller/servlet path, không chỉ vì thói quen đặt tên.
- Một đoạn code có **antMatchers(HttpMethod.GET,...)** không được đổi thành requestMatchers("...") rồi vô tình bỏ ràng buộc HTTP method.
- Một matcher Regex không nên nhận mẫu Ant **/** rồi kỳ vọng regex hiểu như Ant.
- Đường dẫn admin bị rule /** hoặc /api/** che mất là lỗi phân quyền nghiêm trọng.
- Một matcher tồn tại trong **custom filter** hoặc login/logout processing URL có thể cần sửa riêng, dù authorizeHttpRequests đã được nâng cấp.

## 5. PathPatternRequestMatcher: chuẩn bị chuyển sang Spring Security 7

### 5.1. Sử dụng tường minh ở Spring Security 6.5+

Ví dụ với URL và HTTP method chính xác:

~~~java
// Trích đoạn dùng trong SecurityFilterChain của Spring Security 6.5+.
PathPatternRequestMatcher.Builder path =
        PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(path.matcher(HttpMethod.GET, "/api/reports/{id}"))
        .hasAuthority("report:read")
    .requestMatchers(
        path.matcher(HttpMethod.POST, "/api/reports/{id}/publish"))
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

PathPatternRequestMatcher đã có trong Spring Security 6.5 và được dùng mặc định trong Java DSL ở Spring Security 7. Sử dụng nó tường minh ở 6.5 giúp kiểm thử sự thay đổi trước khi nâng dependency.

Ở đây **matcher("/a")** so khớp path, **matcher(HttpMethod.POST, "/a")** còn ràng buộc HTTP method. Với builder, pattern bắt đầu bằng dấu **/** và không bao gồm context path của ứng dụng. Đường dẫn tới một servlet không phải root có thể cần thêm servlet prefix bằng basePath.

### 5.2. Ngôn ngữ PathPattern không giống hoàn toàn Ant-style

| Pattern | Ý nghĩa |
| --- | --- |
| /reports | Chỉ một đường dẫn cụ thể |
| /reports/* | Một segment bên dưới /reports |
| /reports/{id} | Một segment đặt tên id |
| /reports/** | /reports và các đường con theo ngữ nghĩa PathPattern |
| /reports/{id}/publish | Đường publish cho một id cụ thể |
| /assets/{*rest} | Bắt phần còn lại ở cuối pattern khi cần |

**Không chuyển máy móc** các mẫu Ant có ** nằm giữa đường, chẳng hạn /api/**/admin, sang PathPattern. PathPatternParser đặt hạn chế vị trí của ký tự bắt nhiều segment; cần thiết kế lại phạm vi hoặc dùng matcher phù hợp khác. Mẫu path rộng hơn cũng có thể làm thay đổi quyền: /api/reports/** sẽ bao gồm nhiều hành động hơn /api/reports/{id}.

Hành vi của **/reports** và **/reports/** (trailing slash), ký tự mã hóa URL, dấu chấm phẩy và cách xử lý path có thể khác theo Spring Framework, MVC configuration và loại matcher. Khi có khách hàng sử dụng những biến thể này, ghi expected rõ ràng và chạy test cho từng loại.

### 5.3. Context path khác servlet path

Giả sử ứng dụng triển khai tại **context path /portal**, DispatcherServlet được ánh xạ ở **/mvc**, controller có @GetMapping("/orders/{id}"). URI bên ngoài là **/portal/mvc/orders/42**.

Đối với PathPatternRequestMatcher, **/portal là context path và phải bị loại khỏi mẫu**. Có thể chỉ định servlet path bằng builder:

~~~java
// Trích đoạn Spring Security 6.5+/7.x.
PathPatternRequestMatcher.Builder mvc =
        PathPatternRequestMatcher.withDefaults().basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher(HttpMethod.GET, "/orders/{id}"))
        .hasAuthority("order:read")
    .anyRequest().denyAll()
);
~~~

Điều này so khớp đường dẫn theo cách **bao gồm servlet prefix /mvc** mà **không tính /portal vào pattern**. Nếu đặt nhầm /portal vào matcher, quy tắc có thể không áp dụng khi chạy thật. Cần test trên request có contextPath/servletPath chính xác, không chỉ chạy ở root path của MockMvc.

Trong Spring Security 5.8/6.x, một cấu hình dùng MvcRequestMatcher với HandlerMappingIntrospector và servletPath riêng có thể xuất hiện:

~~~java
// Chỉ minh họa giai đoạn 5.8/6.x, không dùng cho Spring Security 7.
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(handlerMappingIntrospector)
                .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(HttpMethod.GET, "/orders/{id}"))
        .hasAuthority("order:read")
    .anyRequest().denyAll()
);
~~~

Đây là **trích đoạn không độc lập**: biến handlerMappingIntrospector phải đến từ Spring MVC application context thích hợp, và cần import lớp MvcRequestMatcher. Cấu hình trên cho thấy vì sao việc bỏ chữ mvc trong API mà không xét servlet prefix có thể thay đổi khả năng match. Khi lên 7.x, dùng PathPatternRequestMatcher.Builder.

### 5.4. Kiểm tra mức sẵn sàng nâng lên 7 khi vẫn ở 6.5

Tài liệu migration 7 cho phép thử sử dụng PathPatternRequestMatcher mặc định bằng bean PathPatternRequestMatcherBuilderFactoryBean trên Spring Security 6.5:

~~~java
// Spring Security 6.5 - bean chuẩn bị tương thích 7.x.
@Bean
PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
    return new PathPatternRequestMatcherBuilderFactoryBean();
}
~~~

Với snippet này cần import class từ **org.springframework.security.config.web**. Bean tác động đến các matcher do **DSL tạo ra**; nó không tự thay thế mọi chỗ trong dự án đang tự khởi tạo AntPathRequestMatcher hoặc MvcRequestMatcher. Sau khi bật, chạy đầy đủ regression tests trước khi đổi runtime.

PathPatternRequestMatcher còn phải tương thích **PathPatternParser** được dùng bởi HandlerMapping của Spring MVC. Nếu dự án tùy chỉnh MVC parser, cần kiểm chứng và điều chỉnh thay vì áp mặc định một cách mù quáng.

## 6. RequestMatcher interface và matcher tùy chỉnh

### 6.1. Không đồng nhất một interface với class cũ

**RequestMatcher** vẫn là interface trong Spring Security 7. Có thể dùng implementation có sẵn, cung cấp một lambda hoặc tự viết class. Ví dụ PathPattern matcher tường minh:

~~~java
// Trích đoạn 6.5+.
RequestMatcher reports = PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.GET, "/api/reports/{id}");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(reports).hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

RequestMatcher **chỉ match**; AuthorizationManager mới quyết định phân quyền. Nếu mục tiêu là “người dùng có report:read”, hãy đặt điều kiện đó trong hasAuthority hoặc manager thay vì giấu logic kiểm tra role trong matches(...).

### 6.2. RegexRequestMatcher

Khi thực sự cần regex, có thể cung cấp đối tượng tường minh:

~~~java
// Trích đoạn, cần import RegexRequestMatcher và RequestMatcher.
RequestMatcher digits =
        RegexRequestMatcher.regexMatcher("/api/reports/[0-9]+");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(digits).hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

Không coi chuỗi Ant **/** và regex là cùng cú pháp. Phải kiểm tra cách matcher so khớp path, query string và method trong phiên bản cụ thể; nếu biểu thức regex chưa quy định method, một quy tắc GET có thể vô tình mở thêm các method khác. Có thể dùng matcher tích hợp method hoặc xây dựng một RequestMatcher rõ cả path lẫn method.

### 6.3. Kết hợp điều kiện query parameter

Với đường GET /api/reports/42?print=true, người dùng có thể cần thêm report:print. Path matcher đơn thuần chỉ so khớp path; có thể kết hợp thêm điều kiện query:

~~~java
// Trích đoạn Spring Security 6.5+, cần import AndRequestMatcher.
PathPatternRequestMatcher.Builder paths =
        PathPatternRequestMatcher.withDefaults();

RequestMatcher printRequest = new AndRequestMatcher(
        paths.matcher(HttpMethod.GET, "/api/reports/{id}"),
        request -> "true".equals(request.getParameter("print"))
);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(printRequest).hasAuthority("report:print")
    .requestMatchers(paths.matcher(HttpMethod.GET, "/api/reports/{id}"))
        .hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

Điều kiện print phải đứng **trước** rule đọc thông thường; nếu đảo thứ tự, yêu cầu có print=true có thể khớp rule read trước và bỏ qua yêu cầu report:print. Đây là ví dụ cho thấy **thứ tự matcher** liên quan trực tiếp đến phân quyền.

Không tin role, userId hoặc tenantId do client tự gửi làm nguồn quyền nếu chưa được xác thực. Nếu nghiệp vụ print là hành động nhạy cảm, cần cân nhắc endpoint riêng và kiểm tra ở service.

## 7. Ví dụ JUnit 5 hoàn chỉnh cho Spring Boot 3.5/Security 6.5

Bộ test sau có SecurityFilterChain và controller nằm trong cùng một lớp để kiểm chứng **PathPatternRequestMatcher + HTTP method + quyền + denyAll**. Đây là fixture cho **Spring Boot 3.5.x và Spring Security 6.5.x**, Java 17+; khi lên Boot 4/Security 7, cần đối chiếu starter, package kiểm thử và cấu hình mới. Không khẳng định một tệp viết cho Boot 3.5 sẽ biên dịch nguyên vẹn ở mọi bản khác.

### 7.1. Dependencies

Trong một dự án Spring Boot 3.5 đã có Gradle plugin, repository và test JUnit Jupiter, cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đặt tệp ở **src/test/java/demo/authorization/MatcherMigrationTest.java**:

~~~java
package demo.authorization;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(classes = MatcherMigrationTest.App.class)
@AutoConfigureMockMvc
class MatcherMigrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class App {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            PathPatternRequestMatcher.Builder path =
                    PathPatternRequestMatcher.withDefaults();

            http.authorizeHttpRequests(auth -> auth
                .requestMatchers(path.matcher("/public/ping"))
                    .permitAll()
                .requestMatchers(path.matcher(
                        HttpMethod.GET, "/api/reports/{id}"))
                    .hasAuthority("report:read")
                .requestMatchers(path.matcher(
                        HttpMethod.POST, "/api/reports/{id}/publish"))
                    .hasAuthority("report:publish")
                .anyRequest().denyAll()
            ).httpBasic(Customizer.withDefaults());

            // CSRF mặc định vẫn bật; test POST dùng with(csrf()).
            return http.build();
        }

        @Bean
        ReportController controller() {
            return new ReportController();
        }
    }

    @RestController
    static class ReportController {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/reports/{id}")
        String read(@PathVariable("id") long id) {
            return "report:" + id;
        }

        @PostMapping("/api/reports/{id}/publish")
        String publish(@PathVariable("id") long id) {
            return "published:" + id;
        }
    }

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanCallExplicitPublicRoute() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(authorities = "other")
    void loggedInUserWithoutReadAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherCanPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("published:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCannotPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherWithoutReadAuthorityCannotRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void deeperPathNotMatchedByIdPattern() throws Exception {
        mvc.perform(get("/api/reports/42/export"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void postToReadOnlyRouteIsDenied() throws Exception {
        mvc.perform(post("/api/reports/42").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void unrelatedRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/admin/settings"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void queryParameterDoesNotAlterPathPattern() throws Exception {
        mvc.perform(get("/api/reports/42").param("view", "compact"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void getCannotInvokePublishRoute() throws Exception {
        mvc.perform(get("/api/reports/42/publish"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Chạy** trong một dự án Gradle Spring Boot 3.5/Security 6.5 đã cấu hình Java 17+:

~~~bash
./gradlew test --tests "demo.authorization.MatcherMigrationTest"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "demo.authorization.MatcherMigrationTest"
~~~

**Kết quả dự kiến:** **12 bài test thành công** khi cấu hình và phiên bản tương thích. Không có stdout cố định từ các test; JUnit/Gradle báo trạng thái chạy. Đây là **dự kiến từ logic mẫu**, chưa phải kết quả chạy Gradle thực tế. Hai endpoint đúng quyền trả 200; anonymous gọi endpoint có yêu cầu quyền nhận 401 khi HTTP Basic được bật; các người dùng đã đăng nhập nhưng thiếu authority hoặc gọi đường chưa khai báo nhận 403.

**Vì sao POST phải có with(csrf())?** Spring Security có thể trả 403 vì thiếu CSRF token **trước khi kiểm tra authority**. Nếu không gửi token hợp lệ, test readerCannotPublish vẫn có thể xanh nhưng không chứng minh rule report:publish chạy đúng. Vì vậy test POST kèm CSRF token nhằm tách lỗi phân quyền khỏi lỗi CSRF.

**Giới hạn:** @WithMockUser tạo Authentication/authority giả; test không chứng minh mapping từ OAuth2/OIDC token, IdP hoặc database thực tế. Cần test riêng authentication converter hoặc user provisioning, cũng như quyền trên tài nguyên riêng lẻ nếu nghiệp vụ yêu cầu. Ví dụ này không có servlet prefix tùy biến; hãy thêm integration test nếu app thật có context path/servlet path.

## 8. Nhiều SecurityFilterChain và phạm vi bảo vệ

Hai phương thức sau minh họa cách chọn chain. Chúng là **trích đoạn trong một @Configuration**, cần import @Order, @Bean và các lớp Spring Security tương ứng:

~~~java
@Order(1)
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    PathPatternRequestMatcher.Builder path =
            PathPatternRequestMatcher.withDefaults();

    http.securityMatcher(path.matcher("/api/**"))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(path.matcher(
                    HttpMethod.GET, "/api/reports/{id}"))
                .hasAuthority("report:read")
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Order(2)
@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

Trong ví dụ, chain API chỉ chọn request /api/**. Chain fallback dùng default matcher khớp mọi request chưa được chain API chọn. Vì vậy **/admin/settings** vẫn đi qua một chain có denyAll thay vì thoát hoàn toàn khỏi Spring Security.

Nếu chỉ có chain API và không có chain nào khác, request ngoài /api/** **có thể không được bảo vệ**. Cần kiểm tra cả chain selection trước và sau migration, đặc biệt khi thay http.antMatcher(...) bằng http.securityMatcher(...).

Trong **một chain**, requestMatchers được xét **theo thứ tự**. Không đặt .requestMatchers("/api/**").authenticated() trước .requestMatchers("/api/admin/**").hasRole("ADMIN"); tài khoản thông thường có thể khớp rule rộng trước.

## 9. Ma trận kiểm thử hồi quy nên chạy ở cả phiên bản cũ và mới

| Ca | Request | Người gọi | Kỳ vọng | Sai sót phát hiện |
| --- | --- | --- | --- | --- |
| R1 | GET /api/reports/42 | report:read | Allow | Đường đọc không còn match |
| R2 | GET /api/reports/42 | Anonymous | Reject | Thiếu chain hoặc authentication |
| R3 | GET /api/reports/42 | Logged in, không có report:read | Reject | Rule quá rộng chỉ cần đăng nhập |
| R4 | POST /api/reports/42/publish + CSRF | report:publish | Allow | Matcher POST sai |
| R5 | POST /api/reports/42/publish + CSRF | report:read | Reject | Quyền đọc bị cho phép publish |
| R6 | GET /api/reports/42/publish | report:read | Reject | Không giới hạn HTTP method |
| R7 | POST /api/reports/42 + CSRF | report:read | Reject | POST bị trộn với GET |
| R8 | GET /api/reports/42/export | report:read | Reject nếu chưa cấp export | /** rộng ngoài ý định |
| R9 | GET /admin/settings | report:read | Reject | Không có chain fallback |
| R10 | GET /public/ping | Anonymous | Allow | Public rule bị khóa sau chuyển |
| R11 | GET /api/reports/42?view=compact | report:read | Allow | Nhầm query thành path |
| R12 | GET /api/reports/42/ | report:read | Theo chính sách về trailing slash | Path parser khác |
| R13 | GET /portal/mvc/orders/42 | order:read | Theo policy và servlet prefix | Nhầm context/servlet |
| R14 | GET đường dẫn chứa ký tự URL-encoded | report:read | Theo policy chuẩn hóa URL | Sai URL decoding |
| R15 | GET /api/admin/erase | Người dùng thường | Reject | Rule bao phủ đứng trước ADMIN |

**Không hiểu sai các status:** 401 thường phản ánh chưa xác thực trên ứng dụng dùng Basic/Bearer; 403 phản ánh thiếu quyền (hoặc CSRF); 404 có thể chỉ là thiếu controller. Khi cần xác nhận đúng matcher, kết hợp test HTTP với kiểm tra handler/service thật sự được gọi và trạng thái dữ liệu không đổi khi bị từ chối.

Nếu ứng dụng dùng Servlet prefix, reverse proxy hoặc nhiều SecurityFilterChain, integration test trên server thật cần kiểm tra thêm context path, forwarded headers, path normalization, URL encoding và matcher do filter trực tiếp tạo. Không dựa vào một MockMvc test ở context root để chứng minh mọi deployment path đều an toàn.

## 10. Những lỗi migration thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| antMatchers/mvcMatchers không biên dịch trên 6.x | Phương thức DSL cũ bị bỏ | Chuyển requestMatchers cùng HTTP method, URL và quyền |
| AntPathRequestMatcher/MvcRequestMatcher không còn khi lên 7.x | Lớp implementation bị bỏ | Chuyển PathPatternRequestMatcher hoặc matcher vẫn được hỗ trợ |
| Ứng dụng lỗi parse pattern | Mẫu Ant chứa ** ở vị trí PathPattern không chấp nhận | Thiết kế lại pattern, test phạm vi, không mở /** rộng hơn |
| User thường gọi được /api/admin | requestMatchers("/api/**") đứng trước rule ADMIN | Đổi thứ tự, test authenticated-but-forbidden |
| Request ngoài /api/** không chịu security | Chỉ có chain với securityMatcher("/api/**") | Tạo catch-all chain hợp chính sách |
| 403/404 khác sau đổi servlet path | Đưa nhầm context root vào pattern, quên /mvc | Dùng basePath và test đúng deployment |
| Custom matcher biên dịch lỗi sau lên 6 | javax.servlet.HttpServletRequest cũ | Chuyển sang jakarta.servlet và kiểm tra dependency |
| Test POST thiếu quyền vẫn xanh khi bỏ rule | 403 xuất phát từ CSRF | Thêm with(csrf()) để kiểm tra authorization |
| Matcher regex không đúng | Nhầm regex với Ant hoặc bỏ HTTP method | Test rõ đối tượng RegexRequestMatcher |
| Login/logout flow thay đổi | Filter đặc biệt tạo matcher mặc định khác | Kiểm tra setter nhận RequestMatcher, chạy test flow |
| Có thêm endpoint nhưng chưa cập nhật policy | anyRequest được đặt authenticated quá rộng | Quản lý danh sách route và denyAll phù hợp |

**Lưu ý về quyền nghiệp vụ:** Matcher phân biệt đường HTTP; nó không quyết định người dùng có được xem tài liệu id=42 hay thuộc tenant nào. Khi cần, vẫn phải kiểm tra owner/tenant/ACL ở tầng service hoặc data access. Migration matcher đúng không tự ngăn BOLA/IDOR hoặc sửa mọi trường hợp thiếu kiểm tra quyền trên đối tượng.

## 11. Quy trình nâng cấp thực tế

1. **Kiểm kê** mọi lời gọi antMatchers, mvcMatchers, regexMatchers, antMatcher, securityMatcher, requestMatchers, custom RequestMatcher, SecurityFilterChain và filter dùng URL riêng. Ghi rõ route, method, quyền và servlet.
2. **Đóng băng bảng expected** cho allow/deny, đặc biệt đã đăng nhập nhưng không có quyền, route nhạy cảm, URL ngoài phạm vi, HTTP method khác và public endpoint.
3. **Nâng lên 5.8 trước 6.0** nếu đang ở 5.x, thay DSL deprecated và sửa các cảnh báo liên quan khi công cụ vẫn hỗ trợ cả hai API. Chạy test sau từng nhóm thay đổi.
4. **Nâng Spring Security 6.x** cùng Spring Framework/Jakarta phù hợp, chuyển bean SecurityFilterChain/authorizeHttpRequests và kiểm tra custom matcher với kiểu jakarta.servlet.
5. **Ở Spring Security 6.5**, dùng PathPatternRequestMatcher tường minh hoặc cơ chế opt-in mặc định, thử các pattern và servlet prefix trước khi nâng 7.
6. **Ở Spring Security 7**, bỏ các lớp Ant/MVC matcher không được hỗ trợ, đối chiếu nguyên tắc URI tuyệt đối bắt đầu bằng dấu / nhưng loại context path.
7. **Nghiệm thu** bằng test allow/deny trên cả HTTP method, route, servlet path, chain selection và quyền đối tượng. Đừng chấp nhận chỉ vì ứng dụng biên dịch hoặc khởi động được.
8. **Theo dõi sau triển khai** các bất thường 401/403, endpoint không khớp security chain và thay đổi hành vi login/logout; đối chiếu với bảng quyền đã phê duyệt.

Với hệ thống quan trọng, thay đổi matcher nên được review như một thay đổi **bảo mật**. Hãy giữ cả kết quả từ chối hợp lệ trong regression suite, vì khi matcher mới vô tình mở rộng một rule, các test chỉ kiểm tra truy cập thành công rất dễ bỏ sót lỗ hổng.

## 12. Bài thực hành

**Bài A — thay antMatchers:** Cho rule legacy antMatchers(GET,"/reports/**"), viết lại bằng requestMatchers ở 5.8 và bằng PathPatternRequestMatcher ở 6.5. So sánh kết quả GET /reports/42, GET /reports/42/export, POST /reports/42. Xác định thay đổi nào chỉ là cú pháp, thay đổi nào thay phạm vi.

**Bài B — servlet prefix:** Ứng dụng chạy ở /portal (context) và /mvc (servlet), controller mapping /orders/{id}. Viết matcher sử dụng basePath("/mvc"), test /portal/mvc/orders/42 trong môi trường có contextPath phù hợp và bảo đảm đường ngoài servlet bị chặn.

**Bài C — custom matcher:** GET /reports/42?print=true phải có report:print, còn GET /reports/42 chỉ cần report:read. Viết AndRequestMatcher và đặt quy tắc print lên trước; viết test người chỉ có report:read không thể dùng print.

**Bài D — nhiều filter chain:** Tạo API chain với @Order(1) và fallback @Order(2), chứng minh /api và /admin đều được bảo vệ, sau đó chủ động gỡ fallback trong fixture để quan sát tại sao phải kiểm tra chain selection.

**Bài E — đối chiếu 6.5 và 7:** Chạy ma trận R1–R15 trên nhánh 6.5 dùng PathPatternRequestMatcher rồi nâng 7. Ghi khác biệt do parser, biến đường dẫn, servlet path; chỉ thay đổi expected khi chính sách nghiệp vụ chủ động thay đổi.

## 13. Checklist nghiệm thu

- [ ] Không còn antMatchers/mvcMatchers ở mã dùng Spring Security 6+.
- [ ] Không còn AntPathRequestMatcher/MvcRequestMatcher ở mã dùng Spring Security 7.
- [ ] Phân biệt rõ securityMatcher chọn chain và requestMatchers chọn rule.
- [ ] Có catch-all chain hoặc một cơ chế bảo vệ tất cả request dự kiến.
- [ ] HTTP method, role/authority và thứ tự rule không bị mất khi thay API.
- [ ] PathPattern bắt đầu bằng /, không đưa context path vào pattern.
- [ ] Servlet prefix, trailing slash, wildcard và URL encoding đã được kiểm thử.
- [ ] Các matcher custom chuyển Jakarta và tương thích phiên bản.
- [ ] Cả trường hợp cho phép lẫn trường hợp từ chối được xác minh.
- [ ] Test POST dùng CSRF token hợp lệ khi muốn đo authorization.
- [ ] Các filter login/logout, dispatcher type và endpoint công khai được kiểm tra.
- [ ] Kết quả migration được đánh giá bằng **hành vi** chứ không chỉ bằng biên dịch.

## 14. Tài liệu tham khảo

- Spring Security 5.8 AbstractRequestMatcherRegistry API: https://docs.spring.io/spring-security/site/docs/5.8.x/api/org/springframework/security/config/annotation/web/AbstractRequestMatcherRegistry.html
- Spring Security 6 Migration: https://docs.spring.io/spring-security/reference/6.5/migration/index.html
- Spring Security 6.5 Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 AntPathRequestMatcher API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/util/matcher/AntPathRequestMatcher.html
- Spring Security 6.5 MvcRequestMatcher API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/MvcRequestMatcher.html
- Spring Security 6.5 PathPatternRequestMatcher.Builder API: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html
- Spring Security Prepare for 7, Web Migrations: https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html
- Spring Security 7 Java Configuration: https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html
- Spring Security 7 PathPatternRequestMatcher API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html
