# Quản lý cấu hình theo môi trường và kiểm tra toàn bộ bề mặt endpoint trong Spring Security Servlet

**Ngữ cảnh:** Java 17+, Spring Boot 3.x, Spring Security 6.x và Jakarta Servlet. Bài học thuộc mục **Cấu hình bảo mật**. Hai năng lực đi cùng nhau: quản lý cấu hình dev/staging/prod mà không làm sai lệch chính sách bảo mật, và kiểm tra toàn bộ endpoint thật sự có thể được truy cập, gồm controller, filter, Actuator, Servlet riêng và các tuyến qua gateway.

Một ứng dụng có thể chặn đúng API quen thuộc nhưng vẫn để hở URL quản trị do một profile bật nhầm, một SecurityFilterChain không bao phủ URL mới, hay Actuator được expose ngoài dự định. Vì vậy **cấu hình hiệu lực, phạm vi SecurityFilterChain và danh mục endpoint thực tế** phải được kiểm chứng bằng những bài test có thể lặp lại.

## 1. Phân biệt giá trị môi trường với chính sách bảo mật

**Giá trị môi trường** là thông tin thay đổi theo nơi triển khai: tên miền cho CORS, cổng management, URL downstream, mức ghi log, TLS/forwarded headers, nguồn bí mật, cấu hình cookie, profile được kích hoạt.

**Chính sách bảo mật** là quyết định ai được truy cập cái gì: endpoint công khai, authentication, role/scope, ownership của tài nguyên, CSRF, session, security headers, quyền trên các method GET/POST/PUT/DELETE.

Một số khác biệt hợp lý:
- Dev có thể bật DEBUG logging để hiểu cơ chế filter chain, còn production chỉ ghi log cần thiết.
- Origin frontend được phép khác giữa dev và prod, nhưng phải là allowlist chính xác và đều được kiểm soát.
- Production bắt buộc bảo vệ TLS và cookie phù hợp; dev có thể chạy HTTP ở localhost.
- Debug endpoint chỉ xuất hiện ở môi trường đã chủ động cho phép và phải có xác thực/mạng bảo vệ riêng.

Những bất biến nên có **ở tất cả môi trường**: quản trị cần quyền ADMIN, dữ liệu thuộc user/tenant chỉ được user có thẩm quyền sử dụng, request thay đổi trạng thái có phòng vệ CSRF thích hợp, endpoint mới không mặc nhiên public, và mọi listener/management port được kiểm soát.

| Hạng mục | Có thể thay đổi theo môi trường? | Phải kiểm chứng |
| --- | --- | --- |
| Logging level | Có | Không lộ token, cookie hoặc bí mật vào log |
| Domain CORS | Có | Chỉ origin đáng tin, không xem CORS như authorization |
| TLS, cookie Secure | Cấu hình kỹ thuật có thể khác | Production bắt buộc cấu hình đúng thực tế |
| Role của API quản trị | Thông thường giữ nhất quán | User không có ADMIN luôn bị từ chối |
| Actuator exposure | Chỉ đổi có chủ đích | Health tối thiểu, endpoints nhạy cảm không public |
| Client secret/password | Giá trị khác | Không commit, lấy từ nguồn secret được bảo vệ |
| URL chưa phân loại | Không nên tự động mở | Deny mặc định và cảnh báo review |

Đừng dùng profile dev làm lý do bật <code>permitAll("/**")</code> trên toàn ứng dụng: khi đó test dev không còn phản ánh security policy của staging/prod.

## 2. Spring Profiles và nguồn cấu hình hiệu lực

Spring Boot hỗ trợ <code>application.yml</code> cùng các file <code>application-dev.yml</code>, <code>application-staging.yml</code>, <code>application-prod.yml</code>. Profile có thể kích hoạt bằng <code>SPRING_PROFILES_ACTIVE</code> hoặc tham số chạy, thậm chí nhiều profile đồng thời. Các cấu hình còn được ghi đè bởi biến môi trường, system properties, command-line arguments, config imports và nguồn bên ngoài theo quy tắc ưu tiên của Spring Boot.

Cấu trúc tham khảo:

~~~text
src/main/resources/
  application.yml          # Phần chung, giới hạn an toàn
  application-dev.yml      # Cấu hình quan sát và test local
  application-staging.yml  # Hạ tầng staging
  application-prod.yml     # Production
~~~

Không nên đoán giá trị đang có hiệu lực chỉ bằng cách mở một file YAML. Hãy kiểm tra profile thực sự active, nguồn nào đã ghi đè, và hiệu quả của policy qua integration test. Nếu dùng công cụ quan sát <code>Environment</code> hay Actuator, không in hoặc expose bí mật ra log/web.

Cần quản lý rõ ba lớp:
1. **Rule bảo mật có kiểm thử:** SecurityFilterChain, authorization và chiến lược CSRF/session, ưu tiên chung giữa môi trường.
2. **Giá trị không bí mật:** CORS allowlist, port, URL, mức log, health details.
3. **Secret:** khóa ký, password, client secret, certificate/private key; cung cấp từ secret manager hoặc nguồn cấu hình được quản lý. Tránh commit mật khẩu thật vào YAML hay code.

Một profile có tên <code>prod</code> không tự động an toàn: điều quan trọng là bean được tạo, thuộc tính hiệu lực, endpoint được đăng ký/expose và security matcher nào xử lý request.

## 3. Cơ chế Spring Security cần nhớ trước khi kiểm kê URL

Trên Servlet, <code>DelegatingFilterProxy</code> thường chuyển request sang bean <code>springSecurityFilterChain</code>, là <code>FilterChainProxy</code> quản lý nhiều <code>SecurityFilterChain</code> nếu ứng dụng khai báo. Nó **chọn SecurityFilterChain đầu tiên có RequestMatcher khớp request**, rồi chỉ chạy các security filter của chuỗi đó.

Vì vậy phải kiểm tra hai tầng:
- <code>http.securityMatcher(...)</code> quyết định **request có thuộc toàn chain không**; nhiều chain có thể chồng lấn, nhưng chỉ chain khớp đầu tiên theo thứ tự được chọn.
- <code>authorizeHttpRequests(...requestMatchers(...))</code> quyết định **quyền bên trong chain đã chọn**. <code>anyRequest().denyAll()</code> chỉ bao phủ request thuộc chain đó.

Ví dụ một chain có <code>securityMatcher("/api/**")</code> và <code>anyRequest().denyAll()</code> **không tự chặn** <code>/internal/export</code>. Nếu không có SecurityFilterChain nào khớp <code>/internal/export</code>, Spring Security không áp dụng các security filter của các chain đó cho request. Cần một chain bao phủ phần còn lại hoặc cấu hình phạm vi đúng.

Trong bài này ví dụ chạy được chỉ dùng **một chain có matcher mặc định là mọi request**, để việc kiểm tra toàn bộ bề mặt dễ chứng minh.

## 4. Dự án Spring Boot minh họa chính sách chung

Ví dụ dùng Java 17+, Maven, **Spring Boot 3.3.5** và Spring Security 6.x. Chính sách:
- GET <code>/public/info</code> công khai.
- GET/POST <code>/api/reports</code> cho ANALYST hoặc ADMIN; POST còn chịu bảo vệ CSRF mặc định.
- GET <code>/api/admin/audit</code> chỉ cho ADMIN.
- Health của Actuator được phép công khai với thông tin tối thiểu.
- Những URL khác bị <code>denyAll</code> theo chính sách mẫu.

**Mục đích học tập:** tài khoản demo được tải từ cấu hình bên ngoài và lưu in-memory; production cần giải pháp quản lý danh tính, secret, MFA/audit phù hợp. Demo này chủ yếu chứng minh phạm vi endpoint và policy giữa các profile.

~~~text
security-surface-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/securitysurface/
    │   │   ├── SecuritySurfaceApplication.java
    │   │   └── SecurityConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-dev.yml
    │       └── application-prod.yml
    └── test/java/com/example/securitysurface/
        └── SecuritySurfaceTest.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>security-surface-demo</artifactId>
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
      <artifactId>spring-boot-starter-actuator</artifactId>
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

### 4.2. Controller

Tạo <code>src/main/java/com/example/securitysurface/SecuritySurfaceApplication.java</code>:

~~~java
package com.example.securitysurface;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecuritySurfaceApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecuritySurfaceApplication.class, args);
    }

    @GetMapping("/public/info")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "reports";
    }

    @PostMapping("/api/reports")
    public ResponseEntity<String> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED).body("created");
    }

    @GetMapping("/api/admin/audit")
    public String adminAudit() {
        return "audit";
    }
}
~~~

Một URL có thể có **nhiều HTTP method**. Các rule authorization của sample áp dụng theo path, còn CSRF bảo vệ method không an toàn, cho thấy chỉ test GET không đủ.

### 4.3. SecurityConfiguration.java

Tạo <code>src/main/java/com/example/securitysurface/SecurityConfiguration.java</code>:

~~~java
package com.example.securitysurface;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/public/info")
                    .permitAll()
                .requestMatchers("/api/admin", "/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/reports", "/api/reports/**")
                    .hasAnyRole("ANALYST", "ADMIN")
                .anyRequest()
                    .denyAll())
            .httpBasic(Customizer.withDefaults())
            // CSRF mặc định vẫn bật.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(Environment env, PasswordEncoder encoder) {
        String analystName = env.getRequiredProperty("app.demo-users.analyst-name");
        String analystPass = env.getRequiredProperty("app.demo-users.analyst-password");
        String adminName = env.getRequiredProperty("app.demo-users.admin-name");
        String adminPass = env.getRequiredProperty("app.demo-users.admin-password");

        return new InMemoryUserDetailsManager(
            User.withUsername(analystName)
                .password(encoder.encode(analystPass))
                .roles("ANALYST")
                .build(),
            User.withUsername(adminName)
                .password(encoder.encode(adminPass))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Điểm then chốt:
- Không khai báo <code>securityMatcher</code> nên chain này khớp mọi request và <code>denyAll()</code> ở cuối thực sự xử lý những URL chưa được cấp quyền.
- Rule health dùng <code>EndpointRequest</code> của Spring Boot Actuator, tránh dựa hoàn toàn vào một chuỗi URL hardcode khi base path management có thể thay đổi. Sample giả định Actuator cùng application port; management port riêng phải audit riêng.
- Rule <code>/api/admin/**</code> đứng trước rule rộng hơn. Với các matcher phân quyền, quy tắc khớp đầu tiên quyết định quyền.
- <code>hasRole("ADMIN")</code> tương ứng authority <code>ROLE_ADMIN</code>, do <code>.roles("ADMIN")</code> tạo ra trong ví dụ.
- CSRF mặc định vẫn bật. Với API dùng browser cookie/session, không được tắt CSRF chỉ vì URL bắt đầu bằng <code>/api</code>. API bearer token thuần có thể cần chiến lược khác, nhưng phải phân tích cách credentials được gửi.
- Dùng <code>Environment.getRequiredProperty</code> để yêu cầu đủ thuộc tính người dùng khi khởi động. Password được băm bằng BCrypt trước khi đưa vào kho demo. Trong sản phẩm thật, không thiết kế kho danh tính bằng hai tài khoản tĩnh này.

### 4.4. Cấu hình YAML

Tạo <code>src/main/resources/application.yml</code>:

~~~yaml
app:
  demo-users:
    analyst-name: ${DEMO_ANALYST_NAME}
    analyst-password: ${DEMO_ANALYST_PASSWORD}
    admin-name: ${DEMO_ADMIN_NAME}
    admin-password: ${DEMO_ADMIN_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Tạo <code>src/main/resources/application-dev.yml</code>:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Tạo <code>src/main/resources/application-prod.yml</code>:

~~~yaml
logging:
  level:
    org.springframework.security: WARN
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Cả hai profile dùng **cùng SecurityConfiguration** và cùng danh sách endpoint có quyền. Phần YAML chỉ thay mức log và thuộc tính cookie. Cookie configuration sẽ có tác dụng nếu ứng dụng phát hành session cookie; ví dụ dùng HTTP Basic để thử role, không phải hệ thống login dùng session hoàn chỉnh.

Những biến <code>DEMO_*</code> là bắt buộc. Không tạo fallback mật khẩu yếu trong file cấu hình hoặc đưa secret production vào repository. Khi triển khai production, dùng secret manager, quyền truy cập tối thiểu và cơ chế luân chuyển credential. Nếu thiếu cấu hình bắt buộc, ứng dụng nên dừng khởi động thay vì chạy sai chính sách.


## 5. Khởi động theo profile và quan sát policy

Ở máy Windows dùng PowerShell, mở thư mục chứa <code>pom.xml</code>:

~~~powershell
$env:DEMO_ANALYST_NAME = "analyst"
$env:DEMO_ANALYST_PASSWORD = "local-analyst-pass"
$env:DEMO_ADMIN_NAME = "admin"
$env:DEMO_ADMIN_PASSWORD = "local-admin-pass"
$env:SPRING_PROFILES_ACTIVE = "dev"
mvn spring-boot:run
~~~

Đây chỉ là credential giả cho demo local. Không nhập secret thật vào shell history hoặc log của pipeline. Ở terminal khác, dùng <code>curl.exe</code> trên Windows (tránh alias <code>curl</code> trong Windows PowerShell):

~~~powershell
curl.exe -i http://localhost:8080/public/info
curl.exe -i http://localhost:8080/api/reports
curl.exe -i -u "analyst:local-analyst-pass" http://localhost:8080/api/reports
curl.exe -i -u "analyst:local-analyst-pass" http://localhost:8080/api/admin/audit
curl.exe -i -u "admin:local-admin-pass" http://localhost:8080/api/admin/audit
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i -u "admin:local-admin-pass" http://localhost:8080/api/unknown
~~~

Kết quả dự kiến khi ứng dụng hoạt động bình thường:

| Yêu cầu | Dự kiến | Lý do |
| --- | --- | --- |
| GET <code>/public/info</code> anonymous | 200 và body <code>public</code> | Công khai có chủ đích |
| GET <code>/api/reports</code> anonymous | 401 | HTTP Basic yêu cầu xác thực |
| GET <code>/api/reports</code> với ANALYST | 200, <code>reports</code> | Đủ vai trò |
| GET <code>/api/admin/audit</code> với ANALYST | 403 | Thiếu ROLE_ADMIN |
| GET <code>/api/admin/audit</code> với ADMIN | 200, <code>audit</code> | Đủ vai trò |
| GET <code>/actuator/health</code> anonymous | 200 nếu health UP | Chỉ expose health tối thiểu |
| GET <code>/api/unknown</code> với ADMIN | 403 | Rule <code>denyAll</code> từ chối URL ngoài danh sách |

Một URL chưa được đăng ký controller vẫn có thể trả **403** vì Spring Security từ chối trước khi Spring MVC kiểm tra route. Vì vậy, một kết quả 403 không chứng minh endpoint tồn tại; audit cần cả mapping inventory và HTTP behavior.

Thử chuyển profile bằng <code>$env:SPRING_PROFILES_ACTIVE = "prod"</code> rồi khởi động lại và chạy cùng ma trận. Kiểm thử ở local qua HTTP không chứng minh mọi thuộc tính TLS/cookie Secure ở production đã hoạt động; kiểm tra đó phải thực hiện qua domain và hạ tầng triển khai thật.

### POST và CSRF

Request GET/POST cùng đường dẫn có thể bị xử lý khác nhau. Demo giữ CSRF bật, vì vậy POST bằng HTTP Basic mà **không có CSRF token** trả 403:

~~~powershell
curl.exe -i -u "analyst:local-analyst-pass" -X POST http://localhost:8080/api/reports
~~~

Đây là hành vi của cấu hình hiện tại. Với trình duyệt dùng session cookie, token CSRF phải được cấp và gửi theo cơ chế được chọn. Với API không dùng cookie hoặc cơ chế credential tự động gửi, cần đánh giá đúng threat model trước khi quyết định scope cần CSRF; không nên tắt trên toàn app chỉ để test POST thành công.

## 6. Viết integration test cho security surface

Tạo <code>src/test/java/com/example/securitysurface/SecuritySurfaceTest.java</code>:

~~~java
package com.example.securitysurface;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo-users.analyst-name=analyst",
    "app.demo-users.analyst-password=test-analyst-pass",
    "app.demo-users.admin-name=admin",
    "app.demo-users.admin-password=test-admin-pass"
})
@AutoConfigureMockMvc
class SecuritySurfaceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RequestMappingHandlerMapping mvcMappings;

    @Test
    void publicEndpointAndHealthAreIntentional() throws Exception {
        mvc.perform(get("/public/info"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk());
    }

    @Test
    void reportsRequireAuthentication() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "test-analyst-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));
    }

    @Test
    void roleBoundaryIsEnforced() throws Exception {
        mvc.perform(get("/api/admin/audit")
                .with(httpBasic("analyst", "test-analyst-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/audit")
                .with(httpBasic("admin", "test-admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit"));
    }

    @Test
    void postRequiresCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("analyst", "test-analyst-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports")
                .with(httpBasic("analyst", "test-analyst-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }

    @Test
    void unknownRouteIsNotAccidentallyPublic() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("admin", "test-admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void importantControllerMappingsExist() {
        Set<String> paths = mvcMappings.getHandlerMethods()
            .keySet()
            .stream()
            .flatMap(info -> info.getPatternValues().stream())
            .collect(Collectors.toSet());

        assertThat(paths).contains(
            "/public/info",
            "/api/reports",
            "/api/admin/audit"
        );
    }
}
~~~

Các test dùng dữ liệu giả được cấp trong <code>@SpringBootTest</code>; chúng không cần credential từ hệ thống thật. Kiểm tra HTTP Basic, role, CSRF và default deny, đồng thời đối chiếu một tập đường dẫn với controller mapping đăng ký trong context.

Chạy cùng suite với từng môi trường:

~~~powershell
mvn test "-Dspring.profiles.active=dev"
mvn test "-Dspring.profiles.active=prod"
~~~

Với staging, thêm file <code>application-staging.yml</code> và chạy profile tương ứng cùng suite. Kết quả test xanh nghĩa là chính sách của **Spring context tại thời điểm test** đã thỏa ma trận; nó không tự kiểm tra listener TLS, firewall, proxy, DNS hoặc management port khác. Sau deploy cần smoke/integration test trên những tuyến đã được cho phép thực tế.

Đoạn test lấy <code>RequestMappingHandlerMapping</code> là một cách đọc inventory MVC, **không phải cách đầy đủ để thống kê mọi endpoint**. Nó không bao gồm hết endpoint được xử lý bởi Servlet riêng, Spring Security filter, Actuator management context hay ingress/gateway. HTTP method cũng phải được lấy từ mapping condition nếu muốn inventory có phương thức cụ thể, thay vì chỉ chuỗi path.

## 7. Bề mặt endpoint gồm nhiều lớp hơn controller

**Bề mặt endpoint** là mọi tuyến mà client hoặc một thành phần khác có thể kích hoạt. Để audit đầy đủ, cần thu thập từ nhiều nguồn và xác định đường truy cập thật ở mỗi môi trường.

| Nguồn | Ví dụ | Việc cần kiểm tra |
| --- | --- | --- |
| Controller Spring MVC | GET/POST/PUT/DELETE trong <code>@RequestMapping</code> | HTTP method, path, role, tenant/ownership |
| HandlerMapping khác | Functional endpoint, resource handler, error handler | Route có tồn tại và nhận security policy nào |
| Spring Security filter | Login, logout, OAuth callback, CSRF, request cache | URL do filter xử lý có thể không xuất hiện trong controller |
| Actuator | Health, info, env, metrics, mappings, heapdump | Exposure, thông tin trả về, role, port |
| Servlet/filter đăng ký thủ công | <code>ServletRegistrationBean</code>, filter từ thư viện | Có nằm trong security chain dự kiến không |
| Developer tooling | H2 console, Swagger/OpenAPI UI, debug controller | Chỉ expose có chủ đích, không public nhạy cảm |
| Giao thức/luồng khác | WebSocket handshake, SSE, file upload | Xác thực kết nối, authorization các thao tác |
| Hạ tầng | Gateway, ingress, proxy, management listener | Domain, path rewrite, port, TLS, đường nội bộ/công khai |

Khi Spring Boot Actuator được bật, cần phân biệt **endpoint được khởi tạo**, **expose trên HTTP**, và **người được phép truy cập**. Cấu hình <code>management.endpoints.web.exposure.include</code> chỉ quyết định phần exposure; security và mạng vẫn là lớp riêng.

Trong demo chỉ expose health qua HTTP. Không mở công khai <code>/actuator/env</code>, <code>/actuator/configprops</code>, <code>/actuator/heapdump</code>, <code>/actuator/mappings</code> để tiện quan sát. Nếu cần endpoint quản trị phục vụ vận hành, dùng mạng nội bộ hoặc lớp xác thực/ủy quyền rõ ràng.

Nếu đặt <code>management.server.port</code> khác cổng chính, management có thể hoạt động trong một application context riêng. **Không thể suy ra** SecurityFilterChain của application port đã đủ bảo vệ management port. Cần audit cả hai listener và quy tắc network/ingress. Spring Security custom bean cũng khiến bạn không nên giả định toàn bộ cấu hình bảo vệ Actuator mặc định của Boot tiếp tục được tạo tự động.

## 8. Xây dựng inventory có cấu trúc

Mỗi endpoint nên có ít nhất các trường:

| Trường | Mục đích |
| --- | --- |
| HTTP method + URL/matcher | Nhận diện chính xác đường vào, tránh bỏ sót POST hoặc OPTIONS |
| Nguồn đăng ký | Controller, filter, Actuator, Servlet, gateway |
| Env và cổng expose | Dev/staging/prod, application/management port |
| Authentication | Anonymous, session, Basic, bearer token, OAuth/OIDC |
| Authorization | Vai trò, scope và quyền trên tài nguyên cụ thể |
| CSRF/CORS | Có cần token, origin/method/header nào được phép |
| Owner | Nhóm chịu trách nhiệm endpoint và thay đổi |
| Test/expected status | Test cho anonymous, role đúng, role sai và trường hợp biên |
| Rủi ro dữ liệu | Public, cá nhân, nội bộ, nhạy cảm |

Lấy snapshot inventory đã xác minh của phiên bản đang chạy, so với lần trước khi thêm controller, thư viện, Actuator hoặc cấu hình gateway. Đừng lấy danh sách OpenAPI làm nguồn duy nhất: tài liệu có thể thiếu filter endpoint, Servlet riêng, route ngoài MVC và những path chưa được document. Logs cũng chỉ chứng minh **request từng quan sát được**, không chứng minh endpoint không tồn tại.

Có thể sử dụng Spring MVC <code>RequestMappingHandlerMapping</code> và method condition của <code>RequestMappingInfo</code> để thu thập các route MVC. Khi cần Actuator mappings, chỉ bật ở môi trường kiểm soát được và giới hạn quyền/mạng; không công khai endpoint quan sát hệ thống ra Internet. Đối chiếu với Servlet registration, các SecurityFilterChain, gateway và cấu hình phát hành thật.

## 9. Kiểm thử ma trận access: không chỉ thấy 403 là đủ

Ma trận tham khảo cho demo:

| Endpoint | Anonymous | ANALYST | ADMIN |
| --- | --- | --- | --- |
| GET <code>/public/info</code> | 200 | 200 | 200 |
| GET <code>/api/reports</code> | 401 | 200 | 200 |
| GET <code>/api/admin/audit</code> | 401 | 403 | 200 |
| POST <code>/api/reports</code> thiếu CSRF | 403 | 403 | 403 |
| POST <code>/api/reports</code> có CSRF | 401 | 201 | 201 |
| GET <code>/actuator/health</code> nếu UP | 200 | 200 | 200 |
| GET <code>/api/unknown</code> | Bị từ chối | 403 | 403 |

Phân biệt:
- **200** nghĩa request thành công, nhưng nếu tài nguyên private trả 200 anonymous thì đó là dấu hiệu sai policy.
- **401** thường là authentication entry point yêu cầu credentials; với HTTP Basic thường có <code>WWW-Authenticate</code>.
- **403** có thể do thiếu role, thiếu CSRF hoặc rule denyAll; không tự chứng minh route MVC tồn tại.
- **404** có thể vì route không tồn tại, nhưng không chứng minh đường dẫn thiếu authentication guard.
- **302** có thể đến từ web form login, trong khi một API kỳ vọng Basic/JWT có thể mong 401. Kiểm tra security chain thực sự được chọn.

Ma trận ứng dụng thật phải kiểm tra thêm role thông thường truy cập dữ liệu user/tenant khác. Một user được quyền gọi <code>GET /api/reports/{id}</code> chưa chắc được đọc báo cáo của mọi user. Authorization theo URL phải kết hợp kiểm tra quyền trên tài nguyên cụ thể.

## 10. Các tình huống môi trường dễ sai

### Chain đặc thù che lấp hoặc bỏ trống URL

Nếu có nhiều SecurityFilterChain, <code>@Order(1)</code> được xét trước <code>@Order(2)</code>. Một chain matcher tổng quát đứng đầu có thể khiến chain hẹp phía sau không bao giờ chạy. Ngược lại, chỉ tạo chain cho <code>/api/**</code> có thể để URL khác không khớp bất kỳ chain nào. Phải kiểm thử đủ các matcher và có chain bao phủ các URL cần bảo vệ.

### CORS cross-origin

CORS quản lý việc JavaScript từ origin khác đọc response; **không thay thế authentication/authorization**. Frontend ở domain khác có thể cần preflight OPTIONS, danh sách origin, method và header được phép. CORS sử dụng credentials không thể kết hợp wildcard origin <code>*</code> cho response kiểu đó. Profile có thể cấp allowlist khác nhau nhưng phải được quản lý chặt và có test.

### CSRF và session

Browser tự gắn cookie phù hợp theo ngữ cảnh, nên app dùng cookie/session có nguy cơ CSRF. SameSite hỗ trợ phòng vệ nhưng không thay thế việc kiểm tra CSRF cần thiết. API dùng bearer token gắn chủ động có thể dùng chiến lược khác, nhưng cần xét cả khả năng app chấp nhận cookie và các endpoint form/login trong cùng deployment.

### TLS, reverse proxy và URL rewrite

Production cần TLS cho đường public; khi có proxy, thông tin host/scheme/path của client và backend có thể khác. Chỉ tin cậy forwarded headers do proxy đáng tin cậy cấp. Test matcher thực tế sau khi gateway thêm/bỏ path prefix; không giả định URL nhìn thấy từ client luôn là URL Spring Security dùng để so khớp.

### Static, error và HTTP dispatch

Static resources, <code>/error</code>, forward/error dispatch, multipart upload và WebSocket handshake cũng thuộc bề mặt request. Có thể cần <code>permitAll</code> có chủ đích cho static/error để không phá hoạt động của app, nhưng không được bật <code>web.ignoring()</code> rộng chỉ để sửa lỗi màn hình. <code>permitAll</code> trong chain vẫn đi qua security filters, còn đường dẫn bị bỏ qua hoặc không có chain khớp có đặc tính khác.

### Dev-only endpoint

Bean <code>@Profile("dev")</code> có thể khiến controller chỉ tồn tại ở dev; inventory của dev phải ghi nó, test production phải xác minh nó không hiện diện và không có URL tương đương do thư viện khác tạo ra. Một profile không phải là cơ chế authentication: endpoint dev cũng cần kiểm soát mạng/quyền nếu nó chứa dữ liệu nhạy cảm.


## 11. Quy trình review bề mặt endpoint khi thay đổi hệ thống

1. **Phát hiện** mọi route mới/đổi/xóa: MVC mappings, Servlet/filter registrations, các Actuator endpoint, gateway/ingress và profile bean mới.
2. **Gắn chủ sở hữu, độ nhạy dữ liệu và quyền tối thiểu** cho từng method + route. Với resource ID, xác định ownership/tenant rule.
3. **Xác định SecurityFilterChain được chọn** bằng thứ tự matcher; tìm vùng chồng lấn hoặc thiếu catch-all. Sau đó mới phân tích rule authorization trong chain.
4. **Lập access matrix:** anonymous, user hợp lệ, user thiếu role, admin, sai tenant, thiếu/sai CSRF và method khác. Ghi expected response/body, không chỉ status.
5. **Chạy test cho từng profile** ở CI. Một thay đổi làm endpoint mới công khai hoặc thay đổi status bảo mật phải được review trước khi release.
6. **Kiểm tra sau triển khai** trên các domain/port thực: TLS, proxy, management listener, CORS preflight, cookie và network policy. Đối chiếu inventory của artifact/commit đang chạy.
7. **Theo dõi drift** giữa chính sách được phê duyệt và cấu hình runtime. Khi phát hiện endpoint chưa phân loại, giữ nguyên nguyên tắc deny mặc định và xử lý theo quy trình review.

Không cần mở Internet scanner để làm được bước đầu: phần lớn các kiểm tra ban đầu có thể làm trong MockMvc/integration test và danh mục route đã export từ runtime kiểm soát. Kiểm tra bên ngoài cần thực hiện trên hệ thống, domain và quyền truy cập được cho phép.

## 12. Bảng lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dev có chain <code>permitAll("/**")</code> | Test local che giấu sai quyền | Chạy chung baseline policy ở mọi profile |
| Default password/secret trong file | Dễ lọt credential yếu khi deploy | Yêu cầu secret ngoài repository, fail-fast nếu thiếu |
| Chỉ có chain <code>/api/**</code> và nghĩ <code>denyAll</code> bảo vệ cả app | Có URL không nhận security filter của chain ấy | Bổ sung chain đúng phạm vi/catch-all |
| Để matcher <code>/**</code> trước chain hẹp | Chain đặc thù không được chọn | Sắp xếp chain hẹp trước, test overlap |
| Chỉ tìm <code>@RestController</code> | Bỏ sót Actuator, filter login/logout, Servlet riêng | Tổng hợp inventory từ mọi nguồn |
| Bật thêm Actuator endpoint nhưng không kiểm tra role/cổng | Lộ config, heapdump hoặc thông tin vận hành | Audit exposure, security, network |
| Coi CORS như quyền truy cập | Client khác vẫn gọi API | Authorization server-side độc lập |
| Tắt CSRF toàn app để POST thành công | Cookie session có thể bị tấn công CSRF | Thiết kế CSRF theo threat model và từng chain |
| Test chỉ với anonymous | Không thấy user thường đọc/sửa dữ liệu admin/tenant khác | Test role, ownership và negative cases |
| Coi 403 nghĩa endpoint tồn tại | Kết luận sai mapping | Kiểm tra route registry và response |
| Chỉ test một port hoặc một profile | Bỏ lỡ management context/prod drift | Test tất cả profile và listener cần thiết |
| Tin vào một YAML thay vì runtime config | Bỏ qua environment overrides | Xem giá trị hiệu lực an toàn và chạy test |

## 13. Tự kiểm tra

**Tình huống 1:** Profile dev cho tất cả endpoint <code>permitAll</code>, profile prod yêu cầu authentication. Dev test đều xanh có đủ để bảo đảm prod an toàn không?  
**Trả lời:** Không. Test dev không còn phản ánh baseline bảo mật; cần kiểm thử đúng rule cho mỗi role trên cả hai profile.

**Tình huống 2:** Chain duy nhất có <code>securityMatcher("/api/**")</code> và <code>anyRequest().denyAll()</code>. Endpoint <code>/internal/export</code> có chắc bị Spring Security chặn không?  
**Trả lời:** Không. URL này không thuộc phạm vi matcher của chain; cần một chain khác phù hợp hoặc thay đổi thiết kế để mọi endpoint cần bảo vệ đều có chain xử lý.

**Tình huống 3:** Bật <code>management.endpoints.web.exposure.include=health,env</code> có đồng nghĩa <code>/actuator/env</code> public không?  
**Trả lời:** Không tự động; exposure và authorization/network là hai lớp. Tuy vậy bề mặt mới được mở rộng, phải audit và bảo vệ trước khi triển khai.

**Tình huống 4:** Vì sao lấy tất cả path từ <code>RequestMappingHandlerMapping</code> chưa phải là toàn bộ endpoint?  
**Trả lời:** Nó tập trung vào MVC handler mappings; filter endpoint, Actuator ở context/port riêng, Servlet đăng ký khác và gateway có thể không nằm trong đó.

**Tình huống 5:** MockMvc xanh dưới dev/prod có thay được kiểm tra TLS, ingress và management port thật không?  
**Trả lời:** Không. Nó kiểm tra hành vi của Spring context trong test; security ở các listener và đường vào hạ tầng phải được kiểm tra bổ sung sau deploy.

**Ghi nhớ:** môi trường quyết định các giá trị vận hành, còn chính sách quyền cần một baseline an toàn và được kiểm thử liên tục. Liệt kê **mọi method + endpoint + cổng + profile**, xác định chain thực sự xử lý, áp dụng quyền tối thiểu và test cả trường hợp bị từ chối. Endpoint mới hoặc chưa phân loại phải được phát hiện trước khi trở thành đường vào công khai.
