# FilterSecurityInterceptor so với AuthorizationFilter trong Spring Security

## 1. Mục tiêu và bối cảnh chuyển đổi

Trong Spring Security dành cho **Servlet**, cả **FilterSecurityInterceptor** và **AuthorizationFilter** đều là các thành phần kiểm soát **authorization ở cấp HTTP request**: trước khi chuyển request tới controller, chúng xác định request có được phép đi tiếp không. Điểm khác biệt cốt lõi nằm ở **mô hình đưa ra quyết định**, **API cấu hình**, **cách lấy Authentication** và **cách áp dụng quyền trên các lần dispatch**.

- **FilterSecurityInterceptor (FSI)** thuộc mô hình cũ dựa trên **SecurityMetadataSource → ConfigAttribute → AccessDecisionManager / AccessDecisionVoter**.
- **AuthorizationFilter (AF)** thuộc mô hình hiện đại dựa trên **AuthorizationManager**, thường được cấu hình bằng **authorizeHttpRequests**. Mô hình này thống nhất hơn với phương thức ủy quyền trong các phần khác của Spring Security.
- Khi chuyển từ cấu hình **authorizeRequests** sang **authorizeHttpRequests** trong Spring Security 6.x, việc kiểm quyền HTTP được thực hiện bởi **AuthorizationFilter** thay cho **FilterSecurityInterceptor**.
- Cả hai đều thuộc hệ thống Servlet filter, khác với method security qua **@PreAuthorize**. Thay đổi filter HTTP không tự tạo quyền chi tiết theo user, tenant, owner hay đối tượng dữ liệu trong service.

Bài này giải thích cơ chế, đối chiếu hai lớp, quy tắc migrate an toàn trong Spring Security 6.x/Spring Boot 3.x, ví dụ Java chạy được, cách đọc filter chain và những lỗi hay gặp khi đổi phiên bản.

**Phạm vi phiên bản:** các ví dụ chạy dùng **Java 17+, Spring Boot 3.3.x, Spring Security 6.x**. API có thể bị deprecated hoặc điều chỉnh ở các major version mới; khi nâng cấp sang Spring Security 7+, xem migration guide chính thức của phiên bản dự kiến thay vì giả định mọi đoạn legacy vẫn còn hoạt động.

## 2. Vị trí của hai filter trong Spring Security

Với ứng dụng Spring MVC, request đi qua servlet filter do container gọi. **DelegatingFilterProxy** chuyển vào bean **springSecurityFilterChain**; bean này là **FilterChainProxy**, nơi chọn **SecurityFilterChain** đầu tiên khớp request theo thứ tự ưu tiên. Mỗi SecurityFilterChain chứa nhiều Security Filter dành cho authentication, CSRF, xử lý exception và authorization.

~~~text
HTTP request
    |
    v
Servlet container / DelegatingFilterProxy
    |
    v
FilterChainProxy ("springSecurityFilterChain")
    |
    +-- Chọn SecurityFilterChain phù hợp theo securityMatcher
            |
            +-- CSRF, authentication, security context, ...
            +-- ExceptionTranslationFilter
            +-- AuthorizationFilter  [authorizeHttpRequests]
            |            hoặc
            +-- FilterSecurityInterceptor [authorizeRequests legacy]
            |
            v
        DispatcherServlet -> Controller -> Service
~~~

Sơ đồ là **logic đơn giản hóa**, không phải danh sách đầy đủ của mọi filter và thứ tự chính xác của một ứng dụng bất kỳ. Những filter được kích hoạt phụ thuộc cấu hình (HTTP Basic, form login, OAuth2, custom filter...). **AuthorizationFilter thường nằm cuối chuỗi Spring Security** theo cấu hình chuẩn của mô hình mới, sau các filter xác thực và bảo vệ khác. **ExceptionTranslationFilter** có nhiệm vụ chuyển các exception bảo mật thành cơ chế bắt đầu xác thực hoặc phản hồi truy cập bị từ chối.

Có **hai cấp matching khác nhau**:

1. **FilterChainProxy chọn chuỗi** bằng **securityMatcher** và thứ tự các bean **SecurityFilterChain**.
2. **Filter kiểm quyền bên trong chuỗi** áp dụng rule **requestMatchers** từ **authorizeHttpRequests** (hoặc cơ chế legacy tương ứng).

Nếu không có SecurityFilterChain nào khớp, request có thể **không được bảo vệ bởi Spring Security**. Nếu có chuỗi nhưng rule quá rộng hoặc sai thứ tự, kết quả authorization có thể khác chính sách mong đợi. Điều này đúng với cả mô hình cũ lẫn mới; nâng cấp filter không tự khắc phục cấu hình matcher sai.

## 3. Cách FilterSecurityInterceptor hoạt động

### 3.1. Các thành phần legacy

Trong mô hình cũ, **FilterSecurityInterceptor** kế thừa cơ chế chặn secure object và kiểm tra quyền qua nhiều thành phần:

1. Nhận **HttpServletRequest, HttpServletResponse, FilterChain** trong một **FilterInvocation**.
2. Đọc **Authentication** từ **SecurityContextHolder**.
3. Hỏi **FilterInvocationSecurityMetadataSource / SecurityMetadataSource** để lấy **ConfigAttribute** tương ứng với request, chẳng hạn yêu cầu role hoặc biểu thức điều kiện.
4. Đưa Authentication, secure object và ConfigAttribute cho **AccessDecisionManager**.
5. **AccessDecisionManager** dùng chiến lược quyết định, có thể kết hợp các **AccessDecisionVoter**. Ví dụ trong các cấu hình cũ có **AffirmativeBased**, **RoleVoter**, **WebExpressionVoter**.
6. Nếu từ chối, ném **AccessDeniedException**; nếu chấp nhận, tiếp tục FilterChain.

~~~mermaid
flowchart TD
    A["HTTP request / FilterInvocation"] --> B["FilterSecurityInterceptor"]
    B --> C["SecurityContextHolder: Authentication"]
    B --> D["SecurityMetadataSource: ConfigAttribute"]
    C --> E["AccessDecisionManager"]
    D --> E
    E --> F{"Quyết định"}
    F -->|Allow| G["Tiếp tục FilterChain"]
    F -->|Deny| H["AccessDeniedException"]
~~~

Những class, voter và chiến lược trên là cơ chế có thực của hệ thống cũ; **không nên tùy tiện tự đăng ký thêm AccessDecisionManager** trong một cấu hình AuthorizationManager mới. Khi migrate custom voter, cần làm rõ chính sách ban đầu và chuyển cách biểu diễn quyết định.

### 3.2. Cấu hình HTTP theo DSL cũ

Trong những bản Spring Security còn giữ API tương thích, **authorizeRequests** cấu hình quy tắc web theo mô hình legacy. Đoạn sau dùng để **nhận diện và so sánh**, không phải lựa chọn cho code mới:

~~~java
// Legacy: chỉ dùng trong project/phiên bản còn hỗ trợ authorizeRequests.
http.authorizeRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
        .anyRequest().denyAll()
);
~~~

Ở cấu hình mới, thay bằng **authorizeHttpRequests**:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
        .anyRequest().denyAll()
);
~~~

**Không sửa bằng cách tìm và thay mỗi tên method rồi bỏ qua kiểm thử.** Cần kiểm tra matcher cụ thể, thứ tự rule, custom access logic, dispatch types, nhiều SecurityFilterChain, trạng thái anonymous/authenticated và các phần custom filter.

API **antMatchers/mvcMatchers** của cấu hình cũ đã thay đổi qua các phiên bản Spring Security; khi migrate từ code 5.x, không copy nguyên các phương thức matcher đã bị loại khỏi 6.x. Dùng **requestMatchers** có kiểu phù hợp và test đường dẫn thực tế.

## 4. Cách AuthorizationFilter hoạt động

Trong mô hình mới, **AuthorizationFilter** sử dụng **AuthorizationManager** để đưa ra kết quả:

1. Tạo một **Supplier<Authentication>** đọc danh tính từ **SecurityContextHolder** khi thực sự cần.
2. Gọi **AuthorizationManager** với supplier và request hiện tại; các rule cấu hình bởi **authorizeHttpRequests** được phân giải qua cơ chế request matcher.
3. Nếu bị từ chối, ném **AccessDeniedException** (hoặc loại từ chối tương thích của phiên bản); **ExceptionTranslationFilter** xử lý theo bối cảnh authentication.
4. Nếu được cho phép, filter gọi bước tiếp theo trong chuỗi.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["AuthorizationFilter"]
    B --> C["Supplier of Authentication"]
    B --> D["AuthorizationManager: match request + apply rule"]
    C --> D
    D --> E{"Được phép?"}
    E -->|Có| F["Tiếp tục FilterChain"]
    E -->|Không| G["AccessDeniedException"]
    G --> H["ExceptionTranslationFilter: entry point hoặc 403"]
~~~

**Lazy authentication lookup** là khác biệt đáng chú ý: với quy tắc **permitAll**, hệ thống có thể không cần tra Authentication để ra quyết định. Điều đó không có nghĩa bỏ qua toàn bộ security filter chain; các filter xác thực, CSRF hoặc custom filter ở vị trí trước có thể vẫn chạy tùy cấu hình.

### 4.1. AuthorizationManager là gì?

**AuthorizationManager** diễn tả hành vi kiểm quyền dựa trên **Supplier<Authentication>** và một secure object hoặc request context. Trong Spring Security 6.x có các thành phần chuẩn như:

- **AuthorityAuthorizationManager**: kiểm authority/role.
- **AuthenticatedAuthorizationManager**: kiểm trạng thái authenticated.
- **RequestMatcherDelegatingAuthorizationManager**: chọn quy tắc phù hợp với HttpServletRequest.
- **WebExpressionAuthorizationManager**: hỗ trợ chuyển biểu thức SpEL HTTP legacy trong trường hợp cần.
- Các **AuthorizationManager** tùy chỉnh để kiểm dữ liệu quyền chuyên biệt.

Đặt rule thông qua **authorizeHttpRequests**:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers(HttpMethod.GET, "/reports/**").hasAuthority("REPORT_READ")
        .anyRequest().denyAll()
);
~~~

Khi dùng đoạn này trong class Java thật cần import **org.springframework.http.HttpMethod**. **hasRole("ADMIN")** theo quy ước thông thường kiểm authority **ROLE_ADMIN**, còn **hasAuthority("REPORT_READ")** kiểm tên authority chính xác. Đừng suy ra rằng user có ROLE_ADMIN tự động có REPORT_READ nếu cấu hình authorities của bạn không cấp quyền đó.

Trong **authorizeHttpRequests**, các rule thường được xét theo thứ tự đã khai báo và **rule đầu tiên khớp sẽ quyết định**. Đặt **/admin/** trước một rule quá rộng **/**, tránh để **permitAll** bao trùm tài nguyên cần bảo vệ, và dùng **anyRequest().denyAll()** khi chính sách yêu cầu đóng mặc định.

## 5. Bảng so sánh FilterSecurityInterceptor và AuthorizationFilter

| Tiêu chí | FilterSecurityInterceptor (legacy) | AuthorizationFilter (hiện đại) |
| --- | --- | --- |
| Nhóm chức năng | Authorization của Servlet request | Authorization của Servlet request |
| Cách cấu hình phổ biến | **authorizeRequests** / XML legacy | **authorizeHttpRequests** |
| API quyết định | **AccessDecisionManager** và các **AccessDecisionVoter** | **AuthorizationManager** |
| Dữ liệu policy | **SecurityMetadataSource / ConfigAttribute** | Các AuthorizationManager và request matcher |
| Đối tượng làm việc | **FilterInvocation** | **HttpServletRequest** được đánh giá qua manager |
| Authentication | Thường được đọc ngay trong luồng chặn legacy | **Supplier<Authentication>**, có thể truy xuất muộn |
| Quy tắc public | Có cơ chế permitAll | Có cơ chế permitAll, lazy lookup hữu ích |
| Biểu thức và rule | Legacy expression voter/metadata | Built-in manager, **WebExpressionAuthorizationManager** nếu cần SpEL |
| Custom rule | Voter, decision manager, security metadata | Custom **AuthorizationManager** |
| Dispatch | Có các lựa chọn/thiết lập kiểm một lần theo request trong legacy | **Mặc định xét các dispatch đi qua filter**, kể cả FORWARD/ERROR; cấu hình dispatcher type cần kiểm |
| Hướng phát triển ở 6.x | Tương thích/migration legacy | Hướng cấu hình được khuyến nghị |

**Điểm tương đồng:** cả hai đều quyết định truy cập trước khi controller xử lý request; đều dựa vào danh tính/authorities do tầng authentication cung cấp; đều có thể đưa tới **AccessDeniedException**; đều cần đúng security chain, matcher và chính sách. Cả hai không thay thế kiểm soát **object-level authorization** như owner/tenant/ACL khi nghiệp vụ cần.

**Không kết luận một lớp an toàn hơn tuyệt đối chỉ từ tên class.** Một cấu hình AuthorizationFilter sai matcher hay permitAll quá rộng vẫn dễ làm lộ dữ liệu; một hệ thống FilterSecurityInterceptor có rule đúng có thể đang bảo vệ hợp lệ. Lợi ích của mô hình mới là API gọn hơn, dễ mở rộng hơn và được Spring Security định hướng sử dụng lâu dài; việc chuyển đổi vẫn cần đánh giá chính sách.

## 6. Khác biệt dễ gây lỗi khi migrate: DispatcherType

Trong Servlet, một request có thể đi qua nhiều lần **dispatch**. Ví dụ:

- **REQUEST**: lần nhận HTTP ban đầu.
- **FORWARD**: server nội bộ forward sang controller/view khác.
- **ERROR**: container xử lý đường lỗi, thường **/error**.
- **INCLUDE** và **ASYNC**: tùy ứng dụng và đăng ký filter tại servlet container.

Theo tài liệu Spring Security 6.x, **AuthorizationFilter kiểm quyền trên mỗi dispatch mà nó nhận được** theo hành vi mặc định, không chỉ lần REQUEST ban đầu. Nếu request được phép ở **/reports/7** rồi ứng dụng forward sang một URL khác, rule có thể được áp dụng lần nữa theo đường dẫn và dispatcher type hiện hành. Một số hệ thống legacy có cấu hình kiểm một lần trên request, nên sự khác biệt có thể xuất hiện sau migration.

### 6.1. Ví dụ lỗi sau nâng cấp

Giả sử user đã được phép truy cập **GET /documents/7**. Controller forward sang **/WEB-INF/views/document.jsp**, nhưng rule mới chỉ cho phép **/documents/** và **anyRequest().denyAll()**. Nếu lần FORWARD đi qua Spring Security filter chain, forward có thể bị từ chối, khiến view không hiển thị.

Tương tự, một lỗi backend xảy ra rồi container dispatch tới **/error**; nếu **/error** cũng bị chặn, người dùng có thể thấy trang lỗi hoặc status khó hiểu, làm che giấu lỗi gốc.

### 6.2. Cách xử lý có chủ đích

Nếu ứng dụng dùng forward/render và lỗi nội bộ đáng tin, có thể cân nhắc rule dispatcher type:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(authorize -> authorize
        .dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
            .permitAll()
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/documents/**").authenticated()
        .anyRequest().denyAll()
);
~~~

**Đây là một lựa chọn chính sách, không phải quy tắc bắt buộc cho mọi ứng dụng.** Cho phép mọi FORWARD/ERROR dispatch có thể thay đổi bề mặt truy cập; cần xét các đường forward nội bộ, cách container đăng ký filter, endpoint có side effect và mô hình trust. Nếu yêu cầu chặt hơn, cấu hình URL cụ thể/dispatcher type hoặc custom rule phù hợp. Đừng dùng **permitAll()** toàn bộ **/error**, **/** chỉ để test xanh mà không đánh giá tác động bảo mật.

Với ASYNC/ERROR/FORWARD, **chỉ các dispatcher type thực sự được servlet container chuyển qua security filter** mới áp dụng rule. Hãy test trên cấu hình đăng ký filter và container thực tế, không chỉ dựa vào một mô tả tổng quát.

## 7. Ví dụ Spring Boot 3.3.x chạy được với AuthorizationFilter

Dựng một ứng dụng **Java 17**, Spring Boot **3.3.5**, Spring Security 6.x, Spring MVC và HTTP Basic. Chính sách:

- **GET /public/ping**: công khai.
- **GET /reports/{id}**: chỉ user có authority **REPORT_READ**.
- **GET /admin/panel**: chỉ user có **ROLE_ADMIN**.
- Mọi đường còn lại: **DENY**.
- Test xác nhận SecurityFilterChain chứa **AuthorizationFilter**, không chứa **FilterSecurityInterceptor** trong ví dụ mới.

Ví dụ dùng tài khoản giả với **{noop}** chỉ để chạy local/test; ứng dụng thật phải sử dụng mã hóa mật khẩu thích hợp, cấu hình identity provider và không chứa credential cố định.

### 7.1. Cấu trúc

~~~text
authorization-filter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/security/
    │   ├── AuthorizationFilterDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/security/
        └── AuthorizationFilterTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'authorization-filter-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/security/AuthorizationFilterDemoApplication.java**

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationFilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationFilterDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/security/SecurityConfig.java**

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/reports/**")
                            .hasAuthority("REPORT_READ")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader-pass")
                        .authorities("REPORT_READ")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}viewer-pass")
                        .authorities("VIEWER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-pass")
                        .roles("ADMIN")
                        .build()
        );
    }
}
~~~

Chính sách được áp dụng bởi **authorizeHttpRequests** nên hệ thống tạo **AuthorizationFilter**. Mặc định CSRF của Spring Security vẫn hoạt động: demo chỉ có endpoint GET; khi kiểm thử các method ghi, cần đưa token CSRF hợp lệ nếu ứng dụng sử dụng session/cookie. CSRF là một lớp độc lập với authorization và có thể trả 403 trước khi rule authorization được đánh giá.

**src/main/java/demo/security/DemoController.java**

~~~java
package demo.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/reports/{id}")
    public String report(@PathVariable long id) {
        return "report:" + id;
    }

    @GetMapping("/admin/panel")
    public String admin() {
        return "admin";
    }
}
~~~

Đây là controller cố ý trả chuỗi tĩnh để tập trung vào **HTTP route authorization**; nếu report thực tế có owner/tenant, **hasAuthority("REPORT_READ")** chưa đủ để kiểm quyền trên từng report. Hãy kiểm thêm tại service/repository hoặc custom AuthorizationManager phù hợp với chính sách tài nguyên.

### 7.2. Kiểm thử security filter chain và hành vi HTTP

**src/test/java/demo/security/AuthorizationFilterTest.java**

~~~java
package demo.security;

import jakarta.servlet.Filter;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.access.intercept.FilterSecurityInterceptor;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationFilterTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy springSecurityFilterChain;

    @Test
    void usesAuthorizationFilterInsteadOfLegacyInterceptor() {
        List<Filter> filters = springSecurityFilterChain
                .getFilterChains()
                .stream()
                .flatMap(chain -> chain.getFilters().stream())
                .toList();

        assertTrue(filters.stream()
                .anyMatch(AuthorizationFilter.class::isInstance));
        assertFalse(filters.stream()
                .anyMatch(FilterSecurityInterceptor.class::isInstance));
    }

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void anonymousUserMustAuthenticateForReport() throws Exception {
        mvc.perform(get("/reports/7"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void userWithoutReportAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/reports/7")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void reportReaderCanAccessReport() throws Exception {
        mvc.perform(get("/reports/7")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("report:7"));
    }

    @Test
    void readerCannotAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    void unlistedPathIsDeniedByDefault() throws Exception {
        mvc.perform(get("/not-listed")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void reportPostIsDeniedAfterValidCsrfCheck() throws Exception {
        mvc.perform(post("/reports/7")
                        .with(httpBasic("reader", "reader-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy trong thư mục project, với JDK 17+ và Gradle phù hợp (ví dụ Gradle wrapper 8.5 nếu project có sẵn):

~~~bash
gradle test
~~~

Kỳ vọng **9 test PASS** khi tạo đúng các file. Đây là kết quả thiết kế và phân tích source, không phải bản ghi stdout của một lần build đã thực thi. Bạn có thể chạy app bằng **gradle bootRun** rồi dùng HTTP Basic thử các endpoint trên **localhost:8080**. Mật khẩu mẫu chỉ dùng để học.

**Vì sao test POST có .with(csrf())?** Nếu thiếu CSRF token, **CsrfFilter** có thể chặn trước **AuthorizationFilter** với HTTP 403. Khi thêm token hợp lệ, test thực sự đi tới rule **GET /reports/** rồi **anyRequest().denyAll()**, chứng minh POST không được cấp quyền. **403** tự nó chưa nói filter nào đã ra quyết định: cần biết đường xử lý và dùng cả test hiện diện filter.

Kiểm tra danh sách filter giúp xác minh cấu hình tạo đúng lớp dự kiến, trong khi test 401/403/200 chứng minh hành vi; **chỉ kiểm class mà không kiểm policy là chưa đủ**.

## 8. Chuyển từ các thành phần legacy sang AuthorizationManager

### 8.1. Quy trình migration

1. **Kiểm kê policy hiện hành:** ghi lại mọi route, HTTP method, role, authority, biểu thức, thứ tự rule, bất kỳ custom voter/AccessDecisionManager, security chain và config XML.
2. **Xác định phiên bản framework đang nâng cấp:** các DSL và matcher của Spring Security 5.x, 6.x, 7.x có khác biệt. Đừng chọn API chỉ vì một bài blog dùng được ở phiên bản khác.
3. **Chuyển sang authorizeHttpRequests** trong từng SecurityFilterChain được migrate, ánh xạ rule đơn giản sang **permitAll**, **authenticated**, **hasRole**, **hasAuthority**, **access**.
4. **Chuyển custom policy:** thay phụ thuộc vào **ConfigAttribute**, **AccessDecisionVoter** hoặc AccessDecisionManager tùy biến bằng **AuthorizationManager** tương đương theo nghiệp vụ. Không có phép đổi tên một-một cho mọi custom voter.
5. **Kiểm tra matching và thứ tự:** securityMatcher chọn chuỗi; requestMatchers chọn quyền trong chuỗi. Thứ tự có thể quyết định endpoint công khai hay bị chặn.
6. **Kiểm tra dispatcher types** (FORWARD/ERROR/ASYNC) và đường **/error**, view rendering nếu app dùng forward.
7. **Tạo regression tests** cho user anonymous, authenticated đủ và thiếu role, nhiều tenant, HTTP methods, URL có dấu slash/encoded path và custom security chain.
8. **Quan sát filter chain và logs:** đảm bảo đúng filter đang hoạt động; loại trừ cấu hình legacy không còn cần và xem kỹ mọi custom filter dựa trên vị trí cũ.
9. **Chạy test trên runtime tương ứng production**, gồm reverse proxy/path rewriting và error dispatch nếu có; chỉ rollout sau khi so khớp hành vi mong đợi.

### 8.2. Ví dụ chuyển kiểm role đơn giản

**Trước — biểu thức legacy (dạng minh họa):**

~~~java
// Hệ thống cũ: dùng AccessDecisionManager, expression voter.
http.authorizeRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

**Sau — AuthorizationManager:**

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Cả hai có thể biểu diễn chính sách tương tự trong phiên bản còn hỗ trợ. Nhưng migration vẫn phải xác minh **user anonymous**, user role USER, ADMIN và các dispatcher có liên quan. Với các rule phức tạp trước kia dựa trên SpEL, có thể dùng **WebExpressionAuthorizationManager** để chuyển bước đầu, sau đó cân nhắc AuthorizationManager type-safe riêng.

### 8.3. Custom AuthorizationManager ở cấp request

Mẫu sau minh họa viết rule ngoài các built-in manager. Đây là **snippet tích hợp**, không phải chương trình độc lập; cần import đúng kiểu tương ứng phiên bản Spring Security và cung cấp **HttpSecurity** trong bean SecurityFilterChain:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Spring Security 6.x: rule chỉ cho phép authority REPORT_READ.
AuthorizationManager<RequestAuthorizationContext> readReport =
        (authentication, context) -> new AuthorizationDecision(
                authentication.get().getAuthorities().stream()
                        .anyMatch(a -> a.getAuthority().equals("REPORT_READ"))
        );

http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").access(readReport)
        .anyRequest().denyAll()
);
~~~

Ở môi trường thật, manager phải xử lý **Authentication null/anonymous** theo chính sách; nếu cần kiểm owner/tenant thì phải lấy metadata tài nguyên từ nguồn tin cậy và xử lý request path đúng cách. Đoạn minh họa trên chỉ trình bày cú pháp **AuthorizationManager** của 6.x; với Authentication null, nó cần được gia cố trước khi dùng trong production. Built-in **hasAuthority("REPORT_READ")** vẫn thích hợp hơn cho rule đơn giản như ví dụ, vì đã bao phủ các ngữ nghĩa framework thường dùng.

Điều đáng lưu ý: custom **AuthorizationManager** là nơi đặt policy thực tế và test nó như hàm quyết định bảo mật. Đừng chuyển một custom voter phức tạp sang lambda trả **true** cho mọi trường hợp chưa được đặc tả, và đừng trông chờ filter mới tự suy ra quyền sở hữu tài nguyên.

## 9. Những lỗi thường gặp khi nâng cấp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm | Cách kiểm chứng |
| --- | --- | --- |
| USER vào được URL admin sau migrate | Matcher quá rộng, rule sai thứ tự, wrong SecurityFilterChain hoặc endpoint không thuộc chain | Test HTTP quyền âm/dương, in filter chain, kiểm securityMatcher |
| 403 mới xuất hiện khi view render | FORWARD dispatch bị rule chặn | Test DispatcherType.FORWARD và path view |
| Trang lỗi không hiện hoặc lỗi 403 chồng lên lỗi gốc | ERROR dispatch hoặc **/error** bị rule chặn | Kiểm error dispatch và status/log gốc |
| Test trả 403 cho POST nên tưởng authorization đúng | CSRF chặn trước khi tới AuthorizationFilter | Test thêm CSRF token hợp lệ hoặc xác minh nguồn AccessDenied |
| 401 bị nhầm thành 403 | Request chưa xác thực; HTTP Basic cần challenge | Test anonymous và authenticated riêng |
| Custom voter không còn tác dụng | Mô hình mới dùng AuthorizationManager, không gọi voter legacy như trước | Di chuyển policy vào manager và test case cụ thể |
| Có filter mới nhưng URL không có bảo vệ | Không có SecurityFilterChain match hoặc custom filter bypass | Kiểm cấu hình chain và request thật |
| Dự đoán filter chạy hai lần là lỗi | AuthorizationFilter có thể chạy nhiều dispatch | Phân biệt REQUEST, FORWARD, ERROR, ASYNC và rule tương ứng |
| Không gọi được quyền dùng owner/tenant | Role rule không biểu diễn quyền trên đối tượng | Bổ sung policy theo resource trong service/AuthorizationManager |
| Legacy và mới cùng xuất hiện | Nhiều security chain, cấu hình trùng hoặc custom registration | Ghi lại filter theo từng request/chain, tránh thêm thủ công tùy tiện |

### 9.1. Cách quan sát filter chain

Bật DEBUG có chọn lọc trong môi trường dev/test:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Hoặc trong test, lấy bean **FilterChainProxy** như mục 7.2 để xem các filter. Danh sách các class giúp chẩn đoán; việc một class có trong danh sách **không chứng minh class đó xử lý request cụ thể** nếu ứng dụng có nhiều chain. Khi cần, kiểm từng SecurityFilterChain và request matcher trước khi kết luận.

Không nên ghi token, session cookie, mật khẩu hoặc nội dung nhạy cảm vào log để chẩn đoán authorization.

### 9.2. Ảnh hưởng tới performance

**AuthorizationFilter** có thể trì hoãn truy xuất Authentication cho đến khi manager thực sự cần, giúp đường **permitAll** tránh thao tác tra danh tính không cần thiết. Mức cải thiện thực tế phụ thuộc cấu hình và tải; **không thể khẳng định mọi request đều nhanh hơn** chỉ bằng cách thay filter. Những rule kiểm DB/ACL vẫn có thể tốn chi phí lớn; cần profile.

Số lần kiểm quyền cũng có thể tăng do multiple dispatch. Nếu app có nhiều forward/error dispatch, cần đo request count, latency và số lần policy đánh giá. Không giải quyết performance bằng cách cho phép rộng hơn hoặc bỏ authorization. Với custom manager, có thể tối ưu truy vấn quyền, nhưng cache quyết định phải phân biệt user, tenant, resource, action và phiên bản policy/ACL nếu những yếu tố đó ảnh hưởng kết quả.

## 10. Quan hệ với method security và bảo vệ object-level

**FilterSecurityInterceptor / AuthorizationFilter** kiểm **HTTP request**. **@EnableMethodSecurity** và **@PreAuthorize** (khi lời gọi qua Spring proxy) kiểm **method invocation**. Mỗi lớp có phạm vi riêng:

~~~text
HTTP SecurityFilterChain:
  /api/reports/** -> authenticated() / REPORT_READ
             |
             v
Controller -> @PreAuthorize / policy service
             |
             v
Repository -> report theo ID + tenant + quyền thực tế
~~~

Một user có **REPORT_READ** vẫn không tự động được đọc tài liệu thuộc tenant khác. Nếu endpoint **GET /api/reports/202** nhận reportId từ client, cần kiểm tenant/owner/ACL tại tầng policy hoặc truy vấn dữ liệu đáng tin. Tránh lỗ hổng IDOR/BOLA do nghĩ rằng migrate sang AuthorizationFilter đã giải quyết mọi quyền.

Ngược lại, bảo vệ service bằng **@PreAuthorize** cũng không thay thế hoàn toàn HTTP security: CSRF, session, authentication, dispatcher type và route matching vẫn cần cấu hình và kiểm thử riêng. Nếu gọi method có annotation bằng **this.method()** trên cùng bean ở chế độ Spring proxy, advice có thể bị bỏ qua; kiểm cả đường gọi thực tế.

## 11. Checklist nghiệm thu trước khi bỏ đường legacy

- **Cấu hình**: mọi SecurityFilterChain cần migrate đã dùng **authorizeHttpRequests**; đã tìm và đánh giá **authorizeRequests**, custom AccessDecisionManager, voters và XML cũ.
- **Đường request**: chứng minh SecurityFilterChain nào khớp cho public, admin, API, actuator, docs, error/view; không có endpoint nhạy cảm lọt khỏi chuỗi.
- **Matching**: thứ tự requestMatchers, HTTP method, path prefix, URL encoding, trailing slash, servlet path và proxy rewriting đúng chính sách.
- **Quyền**: đủ case 200/401/403 theo authentication; user thiếu role bị chặn, user đủ quyền được phép.
- **Dispatch**: FORWARD/ERROR/ASYNC được xét theo chính sách đã duyệt; test cả view rendering và đường lỗi nếu có.
- **Customizations**: mọi policy legacy đã có tương đương **AuthorizationManager** và test phản chứng; không còn phụ thuộc side effect của voter cũ.
- **Filter thực tế**: kiểm chain chạy chứa AuthorizationFilter khi dùng DSL mới; không lẫn class từ các chain khác rồi kết luận sai.
- **Tầng service**: vẫn có kiểm resource owner/tenant/ACL với nghiệp vụ có object-level authorization.
- **Vận hành**: logs, metrics, hiệu năng và cache quyền không che dấu trường hợp từ chối; kiểm giao dịch ghi để tránh side effect trước authorization.
- **Phiên bản**: chạy migration tests trên **dependency versions thực tế**; đối chiếu tài liệu của major/minor version đang dùng, không dựa vào snippet của bản khác.

## 12. Kết luận

**FilterSecurityInterceptor** là cơ chế ủy quyền request theo **SecurityMetadataSource + AccessDecisionManager/voters**. **AuthorizationFilter** là cơ chế theo **AuthorizationManager**, thường được tạo khi chuyển sang **authorizeHttpRequests**, và hỗ trợ trì hoãn truy xuất Authentication khi quy tắc không cần nó.

Khi chuyển đổi, điều quan trọng là giữ nguyên hoặc làm rõ **chính sách truy cập**, đồng thời kiểm lại matching, dispatcher, custom manager và từng loại người gọi. Chuyển thành công nghĩa là người hợp lệ tiếp tục dùng được chức năng, người không đủ quyền vẫn bị từ chối, và quyền trên tài nguyên cụ thể tiếp tục được kiểm đúng tầng.

### Tài liệu chính thức

- Spring Security 6.5 — Authorize HTTP Requests, flow và migration: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Servlet Architecture/FilterChainProxy: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Servlet Authorization Migration: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html
- Spring Security 6.5 — Multiple SecurityFilterChains, securityMatcher/requestMatchers: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
