# Di chuyển antMatchers, mvcMatchers và lựa chọn RequestMatcher tương thích — Spring Security Servlet

> **Bối cảnh:** Nâng cấp từ Spring Security 5.x / Spring Boot 2.x sang Spring Security 6.x / Spring Boot 3.x (Java 17+) trong ứng dụng Servlet/Spring MVC. Mục tiêu không chỉ làm mã biên dịch mà còn **giữ nguyên ranh giới cho phép/từ chối truy cập** khi chuyển `antMatchers` và `mvcMatchers` sang `requestMatchers`, phân biệt `securityMatcher` với authorization matching, và lựa chọn `MvcRequestMatcher`, `AntPathRequestMatcher`, `RegexRequestMatcher` hoặc matcher theo PathPattern khi phiên bản hỗ trợ.

## 1. Vì sao nâng cấp matcher là thay đổi liên quan bảo mật?

Giả sử cấu hình Spring Security 5.x:

~~~java
// PHONG CÁCH CŨ: không dùng trực tiếp trong project Spring Security 6.
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
~~~

Thay tên phương thức một cách cơ học:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

có thể đúng cho app đơn giản, nhưng chưa chứng minh rằng mọi request được phân loại giống trước. Khi một URL có context path, custom DispatcherServlet path, trailing slash hoặc encoded segments, **security matcher có thể hiểu path khác với MVC handler mapping**. Việc thêm nhiều SecurityFilterChain lại đặt thêm câu hỏi: request có đi vào chain bảo vệ hay không?

Một migration có chất lượng phải trả lời:
- Những URL nào vẫn public, URL nào phải authenticated, URL nào cần `ROLE_ADMIN`?
- Matcher đang kiểm **HTTP method**, servlet path và normalized path nào?
- Một `/api/admin/**` có bị rule `/api/** permitAll` đứng trước che mất không?
- Có request nào không khớp bất kỳ SecurityFilterChain nào không?
- Spring MVC hiểu đường dẫn giống security matcher không?
- Security policy có test cả người **không có quyền** chứ không chỉ test người có quyền không?

**Kết luận cốt lõi:** Thay đổi API phải đi cùng kiểm thử **authorization semantics** trên đường HTTP thật.

## 2. Từ API cũ sang API mới

| Ý định | API phong cách Spring Security 5.x | Cách phổ biến trong Spring Security 6.x |
| --- | --- | --- |
| Khai báo rule cho HTTP | `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` |
| Ant-style URL patterns | `antMatchers("/a/**")` | `requestMatchers("/a/**")` nếu lựa chọn tự động phù hợp, hoặc explicit matcher |
| MVC-style URL patterns | `mvcMatchers("/a/**")` | `requestMatchers(new MvcRequestMatcher(...))` / `MvcRequestMatcher.Builder` |
| HTTP method cụ thể | `antMatchers(HttpMethod.GET, "/a/**")` | `requestMatchers(HttpMethod.GET, "/a/**")` |
| Regex URL matching | `regexMatchers(...)` | `requestMatchers(new RegexRequestMatcher(...))` |
| Chọn phạm vi của filter chain | `antMatcher(...)`/`requestMatcher(...)` kiểu cũ ở HttpSecurity | `http.securityMatcher(...)` |
| Rule cuối | `anyRequest().authenticated()` | `anyRequest().authenticated()` hoặc `denyAll()` |
| Bỏ security chain khỏi resources | `web.ignoring().antMatchers(...)` | `WebSecurityCustomizer` theo API mới, hoặc thường tốt hơn: `permitAll` |
| Role check | `hasRole("ADMIN")` | `hasRole("ADMIN")`, nhưng cần kiểm authority prefix thực |
| Authority check | `hasAuthority("SCOPE_read")` | `hasAuthority("SCOPE_read")` |

`authorizeHttpRequests` trong Spring Security hiện đại sử dụng **AuthorizationManager** và thông thường `AuthorizationFilter`, khác với những cấu hình cũ dựa trên `FilterSecurityInterceptor` và custom voters. Nếu dự án từng dùng `AccessDecisionVoter`/`SecurityMetadataSource`/tùy biến interceptor, không được kỳ vọng toàn bộ custom behavior tự chuyển chỉ bằng thay DSL.

### 2.1. Không nhầm API requestMatchers với loại matcher cụ thể

`requestMatchers(String...)` là **overload cấu hình tiện lợi**. Nó không đồng nghĩa “luôn tạo AntPathRequestMatcher” hoặc “luôn tạo MvcRequestMatcher” trên mọi bản và mọi Servlet topology. Với một số Spring Security 6.x versions, implementation tự lựa chọn dựa trên sự hiện diện của Spring MVC và context. Khi có nhiều servlet mappings, cơ chế tự chọn có thể không đủ rõ hoặc báo ambiguity.

Nếu **matcher type** có ảnh hưởng đến boundary bảo mật, hãy chọn explicit `RequestMatcher` theo app **và kiểm trên runtime version**, không dựa vào một bài blog viết cho minor version khác.

## 3. RequestMatcher nhận request và trả kết quả gì?

`org.springframework.security.web.util.matcher.RequestMatcher` có trách nhiệm kiểm một `HttpServletRequest` có khớp điều kiện hay không. Ý tưởng:

~~~text
GET /api/admin/users
          |
          v
RequestMatcher.matches(request)
          |
       true/false
          |
          v
Authorization rule tương ứng:
permitAll / authenticated / hasRole / hasAuthority / access(...)
~~~

Matcher có thể sử dụng:
- HTTP method;
- URI path được Servlet container và firewall chuẩn hóa;
- servlet path, path info;
- dispatcher type;
- biểu thức regex hoặc logic AND/OR/NOT kết hợp những matcher.

Matcher **chỉ chọn phạm vi áp dụng**. Nó không tự cung cấp quyết định về quyền. `.requestMatchers("/api/admin/**").hasRole("ADMIN")` gồm hai phần: **khớp request** rồi **kiểm authority**.

Một request có thể đồng thời khớp nhiều patterns. Trong cấu hình `authorizeHttpRequests` tiêu chuẩn, các rule được đánh giá **theo thứ tự khai báo**, và **rule đầu tiên khớp** quyết định chính sách. Vì vậy thứ tự rule là security contract.

## 4. Phân biệt securityMatcher và requestMatchers: hai tầng khác nhau

~~~text
Servlet request
      |
      v
FilterChainProxy
      |
      +--> SecurityFilterChain #1
      |    securityMatcher("/api/**") ? 
      |         |
      |         +-- có -> chạy filters, rồi vào authorization:
      |                   requestMatchers("/api/admin/**").hasRole("ADMIN")
      |                   requestMatchers("/api/public/**").permitAll()
      |                   anyRequest().denyAll()
      |
      +--> SecurityFilterChain #2
      |    securityMatcher("/web/**") ?
      |
      +--> fallback SecurityFilterChain (nếu có)
~~~

- **`http.securityMatcher(...)`** quyết định HTTP request **nào được chọn vào toàn bộ SecurityFilterChain**.
- **`authorizeHttpRequests(...).requestMatchers(...)`** quyết định rule **bên trong chain đã được chọn**.
- **`anyRequest().denyAll()` ở chain số 1 không bảo vệ URL không khớp `securityMatcher` của chain số 1**.

Ví dụ thiếu fallback:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **fragment minh họa** (cần imports/config). Nếu chỉ khai báo chain này thì `/web/admin` không thuộc `/api/**`. Không thể lấy rule `anyRequest()` trong apiChain để suy rằng `/web/admin` cũng bị bảo vệ.

Thêm fallback được thiết kế rõ:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Hai đoạn là fragments về **nhiều chains**, không cần thêm vào project một-chain ở mục 10. Cần test thứ tự `@Order`, phạm vi của từng chain, path login/logout và fallback; tránh một chain quá rộng chiếm quyền xử lý trước chain API.

### 4.1. Login/logout URL phải nằm trong chain nào?

Một chain UI chỉ match `/web/**` nhưng `formLogin` mặc định xử lý POST `/login`. Nếu `/login` không thuộc chain UI thì login filter ở chain đó **không nhận request**; có thể dẫn tới 404, 401 hoặc vòng redirect. Khi migrate:
- xét `loginProcessingUrl`, `loginPage`, `logoutUrl`;
- đưa endpoints vào matcher của chain đúng;
- test login/logout thực qua HTTP;
- không dùng `permitAll` toàn hệ thống để che nhầm chain.

Tương tự, OAuth2 callback, SAML endpoints, Actuator và error path cần đúng chain/Servlet mapping, không chỉ rule authorization.

## 5. Thứ tự rule và các policy mặc định

Ví dụ nguy hiểm:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
~~~

Một request `/api/admin/users` khớp `/api/**` trước: rule ADMIN ở sau **không cứu được**. Một test chỉ với ADMIN sẽ vẫn trả thành công, nên bug có thể lọt vào production.

Cách viết có chủ đích:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().denyAll())
~~~

Trong app thực, còn phải test `/api/admin`, `/api/admin/`, `/api/administrator`, path encoded và HTTP methods theo matcher/version. **Không khẳng định root path tự khớp `/**` giống nhau trên mọi thuật toán matcher.**

### 5.1. Giữ HTTP method khi di chuyển

Cấu hình cũ:

~~~java
// Cũ: chỉ mở GET.
.antMatchers(HttpMethod.GET, "/reports/**").permitAll()
~~~

Cấu hình mới giữ ý nghĩa:

~~~java
.requestMatchers(HttpMethod.GET, "/reports/**").permitAll()
~~~

Nếu thay bằng `requestMatchers("/reports/**").permitAll()`, bạn **có thể mở cả POST, PUT, PATCH, DELETE** trên cùng URL khi sau này controller hỗ trợ những phương thức ấy. Đây là một lỗi migration rất nghiêm trọng.

Nếu endpoint ghi dữ liệu, cần rule cho methods cụ thể và kiểm **CSRF** độc lập. POST trả 403 có thể là do CSRF, không phải RequestMatcher không khớp; đừng disable CSRF chỉ để làm test qua.

### 5.2. Đừng đánh đồng hasRole và hasAuthority

`hasRole("ADMIN")` thường yêu cầu authority `ROLE_ADMIN` khi dùng default role prefix. `hasAuthority("ADMIN")` yêu cầu chuỗi chính xác `ADMIN`. JWT scopes thường chuyển thành `SCOPE_xxx` theo converter mặc định. Đổi matcher không nên kèm thay đổi authority strings ngoài kế hoạch đã test.

## 6. AntPathRequestMatcher: khi phải giữ Ant semantics

`AntPathRequestMatcher` trong các bản Spring Security Web **còn cung cấp lớp này** dùng Ant-style matching. Một ví dụ explicit:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

AntPathRequestMatcher matcher =
    new AntPathRequestMatcher("/api/admin/**");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(matcher).hasRole("ADMIN")
    .anyRequest().denyAll());
~~~

Đây là **fragment**, không phải class compile độc lập. Chọn explicit Ant matcher khi cần **giữ hành vi cũ và đã xác minh version hỗ trợ**, ví dụ hệ Servlet không dùng MVC hoặc migration tạm thời cần tương thích pattern cũ.

Những điểm phải test:
- `*` và `**` là wildcards theo Ant style, **không phải regex**.
- Pattern kết thúc `/**` có thể có tối ưu semantics đặc biệt ở một số bản; kiểm root/trailing slash.
- HTTP method có thể được ràng buộc nếu bạn tạo matcher với method cụ thể.
- Matching dựa trên path representation của Servlet request, thường liên quan `servletPath + pathInfo`, **không phải nguyên URL client gồm context path và query**.
- Case sensitivity, percent decoding, semicolon segments, firewall normalization là những khác biệt cần test.
- Với các bản Spring Security mới nơi matcher này bị deprecate hoặc có hướng thay bằng PathPattern, lên kế hoạch migration. **Không ép mọi version Security 6.x phải dùng lớp cũ vĩnh viễn.**

### 6.1. Khi nào không nên dùng explicit Ant matcher?

Nếu Spring MVC routing sử dụng PathPatternParser hoặc servlet path phức tạp, một Ant matcher bảo vệ URL theo cách khác MVC controller. Lỗ hổng có thể xuất hiện nếu security cho rằng path không khớp rule restricted nhưng MVC lại định tuyến vào handler nhạy cảm.

Trong app MVC, cần nhất quán matcher/handler semantics. Nếu tự chọn Ant để “hết exception ambiguity”, phải bảo đảm pattern thực sự đại diện cho servlet nhận request, không chỉ né exception.

## 7. MvcRequestMatcher: đồng bộ với Spring MVC HandlerMapping

`MvcRequestMatcher` dựa trên `HandlerMappingIntrospector` để áp dụng hiểu biết về Spring MVC path mapping. Nó có ích khi URL thực sự được Spring MVC DispatcherServlet xử lý, nhất là khi có custom servlet path và yêu cầu cùng interpretation với MVC.

Ví dụ explicit:

~~~java
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;

@Bean
SecurityFilterChain mvcSecurity(
        HttpSecurity http,
        HandlerMappingIntrospector introspector)
        throws Exception {

    MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector);

    return http.authorizeHttpRequests(auth -> auth
        .requestMatchers(mvc.pattern("/admin/**"))
            .hasRole("ADMIN")
        .requestMatchers(mvc.pattern("/public/**"))
            .permitAll()
        .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **fragment cần imports còn lại** và context Spring MVC đã cấu hình. Đừng copy fragment cùng project cấu hình khác mà tạo hai chains không chủ đích.

**HandlerMappingIntrospector phải thuộc đúng MVC application context.** Với ứng dụng root servlet context + child DispatcherServlet context, SecurityFilterChain có thể nằm sai context khiến không tìm thấy introspector hoặc không thấy handler mappings đúng. Không chữa bằng một introspector tự tạo rỗng. Cần kiểm bean `mvcHandlerMappingIntrospector`, application context và servlet mapping của DispatcherServlet thật.

### 7.1. Servlet path khác context path

Giả sử app có:
- `server.servlet.context-path=/shop`;
- `spring.mvc.servlet.path=/app` trong Boot version hỗ trợ;
- controller `@GetMapping("/orders/{id}")`.

Client có thể gọi `/shop/app/orders/42`. Nhưng:
- context path `/shop` thuộc Servlet container;
- servlet path `/app` thuộc mapping DispatcherServlet;
- Spring MVC controller pattern có thể là `/orders/{id}`.

Nếu dùng `MvcRequestMatcher` explicit:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/app");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern("/orders/**"))
        .authenticated()
    .anyRequest().denyAll());
~~~

Đây là fragment. **Không tự động thêm `/shop` vào MVC pattern**. Với Servlet mapping khác nhau, giá trị `getServletPath()` và `getPathInfo()` có thể thay đổi; phải kiểm bằng integration tests trên cấu hình thực.

### 7.2. Nhiều Servlet có thể tạo ambiguity

Một ứng dụng có DispatcherServlet MVC, H2 console servlet và servlet `/legacy/*`. `requestMatchers("/api/**")` không nhất thiết đủ để diễn đạt matcher cho cả ba. Một số bản Spring Security 6 có logic phát hiện ambiguous mappings và yêu cầu explicit RequestMatcher.

Giải pháp:
1. Xác định servlet nào thực sự xử lý request.
2. Với MVC endpoint, dùng `MvcRequestMatcher` trong context phù hợp.
3. Với non-MVC servlet, dùng matcher explicit hỗ trợ đường dẫn Servlet tương ứng, không giả định MVC introspector biết mọi Servlet.
4. Kiểm chain-level `securityMatcher` và authorization matcher cùng dựa trên vùng URL có ý nghĩa.
5. Test mọi Servlet endpoint được bảo vệ, đặc biệt console/debug endpoints chỉ dùng trong development.

## 8. PathPatternRequestMatcher: chỉ dùng khi đúng phiên bản hỗ trợ

Spring Framework mới có `PathPatternParser` cho path matching theo segments. Các nhánh Spring Security 6.x **mới hơn** có API `PathPatternRequestMatcher` hoặc cơ chế tương đương; tên builder, factory và mặc định thay đổi theo minor version.

Một đoạn **minh họa có điều kiện**, **không thuộc project Boot 3.3.5 bên dưới**:

~~~java
// Chỉ biên dịch nếu version Security của bạn có API này:
PathPatternRequestMatcher.Builder builder =
    PathPatternRequestMatcher.withDefaults();

RequestMatcher matcher =
    builder.matcher("/api/**");
~~~

Không copy vào dự án chỉ vì bài trên mạng nói “Spring Security 6” mà không nêu minor version. Phải kiểm:
- API có thực sự được công bố trên dependency hiện tại không;
- có cần `basePath` cho DispatcherServlet custom mapping không;
- Spring MVC có dùng compatible `PathPatternParser` không;
- khác biệt trailing slash, wildcard và encoded path;
- tên package, deprecation và migration guide của đúng version.

Khi nâng version, ưu tiên dùng dependency management/BOM Spring Boot tương thích. Không chỉ nâng một mình `spring-security-web` để lấy class matcher mới nếu `spring-security-config`, `spring-security-core` và Spring Framework vẫn không tương thích.

**Ý chính:** PathPattern matcher có thể là đích nâng cấp tốt cho stack phù hợp, nhưng migration phải có tests; không được thay “Ant wildcard” thành “PathPattern wildcard” rồi mặc định chúng tương đương với mọi URL.

## 9. RegexRequestMatcher và custom matcher

Đôi khi cần path theo định dạng đặc biệt:

~~~java
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

RegexRequestMatcher invoices =
    new RegexRequestMatcher("^/api/invoices/[0-9]+$", "GET");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(invoices).hasRole("FINANCE")
    .anyRequest().denyAll());
~~~

Đây là fragment minh họa. Regex nên có anchors `^`/`$` và phải test request path representation, escaping và HTTP method. Không dùng regex khi Spring MVC pattern đơn giản đã đủ. Nếu dùng custom `RequestMatcher`, viết tests cho URI biến thể, method, servlet mapping và normalization; không xây matcher bằng `requestURI.startsWith` mà bỏ qua context path và segment boundaries.

Một matcher quá rộng có thể khiến public rule chiếm path nhạy cảm; một matcher quá hẹp có thể để URL rơi vào fallback/chain khác. Cả hai đều cần được phát hiện trong regression tests.

## 10. Project runnable với Java 17, Spring Boot 3.3.5 và MockMvc

Project chứng minh migration trong **một ứng dụng Servlet/MVC đơn giản**, dùng `authorizeHttpRequests` và `requestMatchers(String, HttpMethod)`. Ví dụ `MvcRequestMatcher` explicit ở mục 7 và PathPattern ở mục 8 là **lựa chọn thay thế theo topology/version**, không phải các phần phải thêm vào project này.

### 10.1. Cấu trúc

~~~text
request-matcher-demo/
  pom.xml
  src/
    main/
      java/com/example/matcherdemo/
        MatcherDemoApplication.java
        SecurityConfig.java
        DemoController.java
    test/
      java/com/example/matcherdemo/
        MatcherPolicyTest.java
~~~

**Spring Boot 3.3.5** chỉ là bản tham chiếu để tái lập với Java 17, **không** có nghĩa là bản mới nhất. Khi dùng version khác, xem tài liệu tương ứng.

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>request-matcher-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 10.3. Application

**`src/main/java/com/example/matcherdemo/MatcherDemoApplication.java`:**

~~~java
package com.example.matcherdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatcherDemoApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig

**`src/main/java/com/example/matcherdemo/SecurityConfig.java`:**

~~~java
package com.example.matcherdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .authorities("ROLE_USER", "SCOPE_reports.read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities("ROLE_ADMIN", "SCOPE_reports.read")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            // Demo chỉ có GET endpoints; không tắt CSRF.
            .build();
    }
}
~~~

**Vì sao cấu hình này là một ví dụ migration rõ ràng?**

- `requestMatchers("/public")` cho public GET endpoint.
- `/api/admin/**` yêu cầu `ROLE_ADMIN`, USER chỉ authenticated vẫn bị 403.
- `requestMatchers(HttpMethod.GET, "/api/reports/**")` **giữ phương thức GET**; controller khác method sẽ không tự được mở.
- `SCOPE_reports.read` được cấp explicit cho alice và admin, nên role ADMIN không bị nhầm là đồng nghĩa có mọi scope.
- `anyRequest().denyAll()` chặn endpoint chưa được liệt kê, thay vì “cho qua nếu đã authenticated” theo thói quen.
- HTTP Basic được dùng để test authentication thật; form login tắt để giảm ambiguity của entry point.
- `SessionCreationPolicy.STATELESS` không phải điều kiện migration matcher; chỉ là lựa chọn của API demo.
- CSRF vẫn bật. Khi thêm POST state-changing phải thiết kế và test CSRF riêng.
- Password demo cố định trong source **chỉ được dùng trên localhost**; production phải quản lý danh tính/secret và HTTPS.

### 10.5. Controller

**`src/main/java/com/example/matcherdemo/DemoController.java`:**

~~~java
package com.example.matcherdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicRoute() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/admin/panel")
    public Map<String, String> admin(Authentication authentication) {
        return Map.of(
            "area", "admin",
            "user", authentication.getName());
    }

    @GetMapping("/api/reports/monthly")
    public Map<String, String> monthly(Authentication authentication) {
        return Map.of(
            "report", "monthly",
            "user", authentication.getName());
    }

    @GetMapping("/api/other")
    public Map<String, String> deniedByFallback() {
        return Map.of("message", "should-not-be-visible");
    }
}
~~~

`/api/other` cố ý là route **có tồn tại** nhưng không có rule cho phép, để test fallback `denyAll`. Nếu chỉ test URL không tồn tại nhận 404 thì không chứng minh access control đã hoạt động.

### 10.6. MockMvc integration tests

**`src/test/java/com/example/matcherdemo/MatcherPolicyTest.java`:**

~~~java
package com.example.matcherdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MatcherPolicyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteIsAvailableAnonymously() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void anonymousCannotEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin/panel"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin/panel")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin/panel")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.area").value("admin"))
            .andExpect(jsonPath("$.user").value("admin"));
    }

    @Test
    void userWithScopeCanReadReports() throws Exception {
        mvc.perform(get("/api/reports/monthly")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("monthly"));
    }

    @Test
    void anonymousCannotReadReports() throws Exception {
        mvc.perform(get("/api/reports/monthly"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void fallbackDeniesAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/other")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordIsNotAccepted() throws Exception {
        mvc.perform(get("/api/admin/panel")
                .with(httpBasic("admin", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Giải thích test:**
1. `@SpringBootTest` và `@AutoConfigureMockMvc` nạp Spring Security FilterChainProxy thực trong test context.
2. `httpBasic("user","password")` gửi Authorization header để provider kiểm credentials; khác `@WithMockUser` vốn giả lập Authentication.
3. USER bị 403 ở admin, ADMIN được 200, chứng minh role rule đang áp dụng thay vì chỉ chứng minh endpoint tồn tại.
4. Report chỉ cho user có scope tương ứng; đừng suy từ vai trò ADMIN là có mọi scope khi chưa cấp.
5. Route có Controller `/api/other` vẫn bị 403 do deny fallback.
6. Wrong password 401 chứng minh authentication thất bại khác với authorization deny.
7. Không khẳng định một 404 là an toàn; các tests kiểm route thực có thể truy cập khi được phép.

### 10.7. Build, chạy và kết quả kỳ vọng

Trong thư mục có `pom.xml`:

~~~bash
mvn validate
mvn test
mvn spring-boot:run
~~~

Log Maven không cố định vì Java/JUnit/Maven versions và môi trường có thể khác. Với localhost:

~~~bash
curl -i http://localhost:8080/api/admin/panel
curl -i -u alice:alice-pass http://localhost:8080/api/admin/panel
curl -i -u admin:admin-pass http://localhost:8080/api/admin/panel
curl -i -u alice:alice-pass http://localhost:8080/api/reports/monthly
~~~

Kỳ vọng HTTP statuses theo thứ tự **401, 403, 200, 200** trong cấu hình demo; JSON của admin có `area=admin` và user `admin`, JSON report có `report=monthly`.

**Chỉ chạy thông tin đăng nhập demo trên localhost.** HTTP Basic là Base64, không phải mã hóa; trên mạng thật dùng HTTPS và không ghi password/token thật trong terminal history/log.

## 11. Chẩn đoán các lỗi migration thường gặp

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
| --- | --- | --- |
| `antMatchers` không còn compile | Shortcut DSL cũ bị loại khỏi API đang dùng | Chuyển sang `requestMatchers`, explicit matcher khi cần |
| `mvcMatchers` không còn compile | Shortcut MVC legacy không có | Dùng `MvcRequestMatcher`/Builder hoặc requestMatchers theo version |
| Admin bất ngờ trả 200 với USER | Rule public rộng đứng trước admin | Sắp xếp rule, test USER bị 403 |
| GET hoạt động nhưng POST cũng public | Bỏ `HttpMethod.GET` khi migration | Khôi phục matcher theo method và fallback |
| MvcRequestMatcher thiếu introspector | Security config ở context sai | Đặt MVC/security config và introspector đúng context |
| requestMatchers(String) báo ambiguous Servlet | App có nhiều Servlet mappings | Chọn explicit matcher theo Servlet được bảo vệ |
| /app/orders không match rule /orders | Custom servlet path | Builder.servletPath hoặc matcher chính xác, integration test |
| anyRequest denyAll nhưng URL vẫn mở | URL ở ngoài securityMatcher của chain | Thêm fallback chain, test chain selection |
| Login sau migration trả 404 | Login processing URL nằm ngoài chain | Sửa chain matching và test POST /login |
| Status 401 đổi thành 302 | Authentication entry point/form login thay đổi | Kiểm chain, Basic/form, Accept header |
| Static resources mất security headers | web.ignoring thay vì permitAll | Ưu tiên permitAll và test headers |
| 403 tăng sau upgrade | Path semantics, CSRF, method hoặc dispatcher khác | So baseline, version, normalized path |
| Regex match nhầm prefix | Thiếu anchors hoặc sai escaping | Viết RegexRequestMatcher rõ, test boundaries |
| PathPattern API không compile | Code lấy từ minor version khác | Kiểm Javadocs/BOM, chọn matcher được hỗ trợ |
| /admin và /admin/ khác nhau | Trailing slash semantics thay đổi | Canonical URL và negative tests |
| 404 được hiểu là đã chặn | Controller không tồn tại, chưa chắc authorization đúng | Test route thật và matcher decisions |
| Authorized URL vẫn lộ tài nguyên người khác | Chỉ có URL-level role, thiếu object permission | Kiểm ownership/tenant ở service/method security |

### 11.1. Debug đúng cấp

Nếu **không khớp chain**, kiểm `securityMatcher` và FilterChainProxy trước. Nếu **đã vào chain nhưng rule sai**, kiểm thứ tự `requestMatchers`, HTTP method, path representation và authorities. Nếu **rule đúng nhưng controller trả lỗi**, kiểm MVC routing hoặc business logic, đừng thay security để chữa lỗi tầng khác.

Nếu 403 do CSRF, thay `antMatchers` bằng `requestMatchers` không phải nguyên nhân trực tiếp. Kiểm `CsrfFilter` và token/repository. Nếu Authentication thiếu/không hợp lệ, Basic entry point có thể trả 401 trước khi bạn thấy 403 từ authorization. Cần log đã được sanitize và integration tests, không dump Authorization header hay principal credentials.

## 12. Quy trình migration an toàn từng bước

### Bước 1 — Chụp policy baseline

Liệt kê tất cả:
- `antMatchers`, `mvcMatchers`, `regexMatchers` cũ;
- matcher ở `WebSecurityCustomizer`/`web.ignoring`;
- matcher chọn chain;
- method-specific patterns;
- role/authority/permit/deny;
- servletPath/contextPath và custom dispatcher;
- rules cho `/login`, `/logout`, OAuth2 callback, Actuator, static assets;
- custom filters/AccessDecisionVoters.

Không chỉ grep một phương thức rồi thay bằng regex text.

### Bước 2 — Khóa phiên bản hỗ trợ

Xem `mvn dependency:tree` hoặc dependency tree Gradle để biết **Spring Boot, Spring Security Web/Config, Spring Framework, Micrometer (nếu có)**. Kiểm Javadocs/reference **của chính các versions đó**. Không lấy code PathPattern matcher của release sau rồi đưa vào Security 6.3 mà không kiểm API.

### Bước 3 — Xác định topology HTTP

Tìm:
- Spring MVC có/không có trên classpath;
- một hay nhiều DispatcherServlet/Servlet;
- context path, servlet path, reverse proxy rewrite;
- MVC path matching strategy;
- StrictHttpFirewall/normalization;
- các chain matchers và thứ tự.

Nếu có nhiều Servlets, cần matcher explicit cho từng vùng thay vì trông chờ auto-selection không mơ hồ.

### Bước 4 — Chọn matcher theo semantics

- MVC đơn giản: `requestMatchers(String, HttpMethod)` thường đủ nếu tests xác minh.
- Cần đồng nhất MVC: `MvcRequestMatcher` và đúng HandlerMappingIntrospector.
- Cần giữ Ant semantics tạm thời: `AntPathRequestMatcher` khi version hỗ trợ, có lộ trình bỏ API deprecated.
- Cần PathPattern: chỉ khi version có API và parsing strategy phù hợp.
- Regex/custom: explicit matcher khi điều kiện thật sự đặc biệt.

Đừng chọn matcher chỉ vì class name có vẻ tương đồng với code cũ.

### Bước 5 — Sắp xếp rule và fallback

Đặt:
1. Endpoint nhạy cảm trước.
2. Rule theo method và authority rõ ràng.
3. Public endpoints cụ thể.
4. Fallback tường minh: thường `denyAll` hoặc `authenticated` tùy policy.
5. Fallback SecurityFilterChain nếu hệ có nhiều chains.

Không để `/api/** permitAll` đứng trước `/api/admin/** hasRole`. Không để endpoint mới tự được mở vì fallback quá rộng.

### Bước 6 — Viết ma trận test deny/allow

| Path và trạng thái | Anonymous | User | Admin |
| --- | --- | --- | --- |
| GET /public | 200 | 200 | 200 |
| GET /api/admin/panel | 401 theo Basic demo | 403 | 200 |
| GET /api/reports/monthly | 401 | 200 nếu scope đúng | 200 nếu có scope |
| GET /api/other | Theo entry point | 403 do denyAll | 403 do denyAll |
| GET /api/administrator | Không được quyền admin mặc nhiên | Không được quyền admin mặc nhiên | Chỉ theo rule thật |
| POST /api/reports/monthly | Theo auth/CSRF | Theo CSRF + method rule | Theo CSRF + method rule |

Status ở ma trận minh họa là **theo demo**, ngoại trừ hàng những path không được mở. App có form login có thể redirect 302, API sử dụng entry point khác có thể 401 hoặc JSON error; không ép một HTTP status cho mọi stack.

### Bước 7 — Kiểm boundary URL và Servlet mapping

Test:
- root vs child path;
- trailing slash, uppercase/lowercase;
- prefix tương tự `/admin` vs `/administrator`;
- encoded slash/semicolon/double slash trong môi trường cách ly;
- contextPath/servletPath thực;
- GET/POST/DELETE và HTTP method không mong đợi;
- forwarding/error dispatch nơi có yêu cầu;
- MVC endpoint và non-MVC servlet.

Không nới lỏng firewall chỉ để “cấu hình cũ tiếp tục chạy”. Một số request độc hại có thể bị từ chối ở container/firewall trước khi đến matcher; đây là hành vi nên hiểu đúng thay vì quy toàn bộ 400/403 cho RequestMatcher.

### Bước 8 — Triển khai và quan sát

Sau deploy:
- so tỷ lệ 401/403/404/302 theo route template với baseline;
- kiểm login/logout và các paths mới;
- ghi release/versions cho dashboard;
- chuẩn bị rollback nếu authorization bất ngờ mở/rút quyền;
- không bật TRACE log nhạy cảm trên production quá lâu;
- không ghi token, password, session cookie, raw Authorization header trong log/trace.

## 13. Những hiểu nhầm cần tránh

**“requestMatchers luôn là antMatchers đổi tên.”** Sai. Overload string có thể chọn matcher theo môi trường/version; khi semantics quan trọng, kiểm và khai báo rõ.

**“MvcRequestMatcher dùng được cho mọi Servlet.”** Sai. Nó dựa vào Spring MVC HandlerMappingIntrospector, không biết mọi route của custom servlet/H2 console.

**“securityMatcher kiểm quyền.”** Sai. Nó chọn SecurityFilterChain; rule bảo mật nằm bên trong chain.

**“anyRequest().denyAll bảo vệ mọi request của app.”** Chỉ đúng trong phạm vi chain tương ứng. Nếu không có fallback cho URL ngoài mọi chain, phần đó có thể không đi qua Spring Security filters.

**“Rule dưới cùng sẽ override rule trên cùng.”** Sai trong cấu hình authorization thông thường: rule khớp đầu tiên được xét.

**“Giữ pattern mà bỏ HTTP method thì vẫn tương đương.”** Sai. GET-only có thể biến thành all-method.

**“hasRole và hasAuthority luôn giống nhau.”** Sai. `ROLE_ADMIN` khác chuỗi `ADMIN` và khác OAuth2 scope authority.

**“permitAll và web.ignoring cùng là không cần login.”** Cùng cho người dùng vào tài nguyên public nhưng **khác filter-chain behavior**: ignoring bỏ qua Spring Security filters.

**“GET /admin trả 404 nghĩa rule admin bảo mật.”** Không đủ. Test route thật, paths ranh giới và principal có/không có quyền.

**“PathPatternRequestMatcher có sẵn trên toàn bộ Security 6.x.”** Không được giả định; phải kiểm minor version và API.

**“Cấu hình security matcher đủ tránh IDOR.”** Không. URL-level authorization không thay việc kiểm quyền object/tenant trong service layer.

## 14. Bài tập thực hành

1. **Từ antMatchers sang requestMatchers:** Chuyển rule `/admin/** hasRole('ADMIN')` và kiểm anonymous, USER, ADMIN, đường `/administrator`. Kết quả phải chứng minh không mở rộng phạm vi permit.
2. **Kiểm thứ tự:** Đặt `/api/** permitAll` lên trước rule admin. Test USER gọi admin. Đảo thứ tự và kiểm lại. Giải thích first-match semantics.
3. **Giữ HTTP method:** Chuyển rule chỉ cho `GET /reports/**`; test một POST giả lập cùng path và xác minh nó không tự được permit.
4. **Custom MVC servlet path:** DispatcherServlet map `/app`, controller `/orders`. Tạo `MvcRequestMatcher.Builder(introspector).servletPath("/app")` và test URL thật.
5. **Phân biệt securityMatcher:** Chỉ tạo chain `/api/**` và kiểm `/web/secret` nằm ngoài chain; thêm fallback deny và test lại.
6. **Ant so với MVC:** Với cấu hình có hai servlets, thử matcher tự chọn và explicit. Ghi lại đường nào thuộc MVC và đường nào là custom servlet, không “sửa” bằng permitAll rộng.
7. **Static resources:** Đổi `web.ignoring` thành `requestMatchers(...).permitAll()` và kiểm security headers theo cấu hình.
8. **PathPattern upgrade:** Nếu version hỗ trợ, chuyển một path và chạy toàn bộ boundary tests. Nếu compiler không có class, giải thích dependency/version mismatch thay vì override dependencies đơn lẻ.
9. **Regex path:** Bảo vệ `/api/invoices/[0-9]+` GET bằng `RegexRequestMatcher` và test path chứa ký tự khác, thiếu anchors.
10. **Migration regression:** Chạy cùng ma trận request trước/sau upgrade; nếu status khác, xác định nguyên nhân là matcher/entry point/CSRF/filter chain hay MVC mapping.

## 15. Checklist trước khi merge

- [ ] Đã kiểm version của Spring Boot, Spring Security và Spring MVC.
- [ ] Có danh mục đầy đủ các matcher/chain/ignoring rules cũ.
- [ ] Đã xác định context path, servlet path, multiple servlets và proxy rewrites.
- [ ] Đã chọn matcher theo semantics thực, không chỉ theo tên method.
- [ ] Nếu explicit Ant/MVC/PathPattern, API có thật trên version hỗ trợ.
- [ ] Rule cụ thể trước; public rule không che rule nhạy cảm.
- [ ] Giữ method restrictions, authorities, role prefix và dispatcher policies.
- [ ] Có fallback authorization và fallback chain nơi cần.
- [ ] Không đặt login/logout/callback URLs ngoài chain xử lý chúng.
- [ ] Static resources vẫn có security headers theo policy.
- [ ] Có positive và negative tests cho anonymous/USER/ADMIN.
- [ ] Có tests root/trailing slash/prefix tương tự/encoded path/HTTP method.
- [ ] Có tests trên topology Servlet thực nếu khác mặc định.
- [ ] Không tắt CSRF hoặc nới lỏng HttpFirewall chỉ để migration pass.
- [ ] Không lấy 404 đơn lẻ làm bằng chứng authorization chính xác.
- [ ] Không để URL mới tự được phép do fallback quá rộng.
- [ ] Có log/metric 401/403 theo route và rollback plan khi deploy.
- [ ] Không log credentials/token/session trong quá trình chẩn đoán.

**Tổng kết:** Migration từ `antMatchers` và `mvcMatchers` sang `requestMatchers` trong Spring Security Servlet là **thay đổi cách chọn request**, không chỉ đổi tên DSL. Hãy tách `securityMatcher` (chain-level) khỏi `requestMatchers` (rule-level), chọn explicit matcher khi Servlet/MVC semantics yêu cầu, giữ nguyên thứ tự và HTTP method, dùng fallback chặt và **chứng minh bằng negative integration tests** trên phiên bản cụ thể đang triển khai.