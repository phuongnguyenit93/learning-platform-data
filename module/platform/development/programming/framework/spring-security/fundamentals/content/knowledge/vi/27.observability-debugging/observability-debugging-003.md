# Bật DEBUG hoặc TRACE có kiểm soát trong môi trường phù hợp — Spring Security

> **Chủ đề:** Spring Security - fundamentals → **Quan sát và gỡ lỗi**. Mục tiêu là sử dụng log DEBUG/TRACE **đúng thời điểm, đúng thành phần, đúng môi trường** để chẩn đoán 401/403, security filter chain, authentication, authorization và các thành phần phụ thuộc mà **không làm lộ thông tin nhạy cảm, gây quá tải hoặc để logging chi tiết bật vĩnh viễn**. Ví dụ thực hành dùng Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring MVC/Servlet, SLF4J/Logback và JUnit 5/MockMvc. WebFlux và Spring Security phiên bản khác cần đối chiếu logger/hành vi thực tế.

## 1. Logging bảo mật: càng nhiều chưa chắc càng tốt

Một lỗi truy cập **401 Unauthorized** hoặc **403 Forbidden** hiếm khi được giải thích đầy đủ trong response gửi cho client: trả quá nhiều chi tiết có thể giúp kẻ tấn công suy đoán hệ thống. Nhưng phía vận hành lại cần biết request dừng ở đâu — filter nào, matcher nào, provider nào, decision nào — để sửa cấu hình hoặc khắc phục sự cố.

Spring Security có log chi tiết ở mức `DEBUG» và `TRACE». Đây là công cụ điều tra hiệu quả, nhưng log có thể chứa dữ liệu liên quan tới tài khoản, URL, thông tin authorization, lỗi nội bộ hoặc những thông tin do extension tự viết ghi ra. Khi tăng log level trên toàn hệ thống, mỗi request có thể tạo rất nhiều dòng, tăng tải CPU/I/O, chi phí lưu trữ và thời gian tìm manh mối.

**Nguyên tắc thực hành:** ưu tiên giữ `INFO» trong vận hành bình thường; chỉ tăng `DEBUG» khi có giả thuyết cụ thể, tăng `TRACE» trong phạm vi hẹp và ngắn khi `DEBUG» không đủ; sau đó **khôi phục mức cũ** và kiểm tra không còn rò rỉ dữ liệu trong log.

### Ba câu hỏi trước khi bật DEBUG hoặc TRACE

1. **Cần chẩn đoán điều gì?** Request không khớp filter chain, credential bị từ chối, thiếu authority, CSRF token lỗi, Bearer token không hợp lệ hay gateway trả 403?
2. **Ở đâu và trong bao lâu?** Local/test/staging, một instance canary, một pod, hoặc một cửa sổ sự cố production có phê duyệt và thời hạn.
3. **Ai được xem log và log có thể chứa gì?** Secrets, header Authorization, cookie, query token, username/email/tenant, đường dẫn nội bộ, stack trace, dữ liệu PII. Kiểm soát log pipeline, retention và truy cập là điều kiện trước khi tăng verbosity.

Đừng bật TRACE toàn hệ thống chỉ vì “không tìm thấy lỗi”: việc này thường làm tín hiệu cần tìm bị chìm trong nhiễu và có thể tạo rủi ro mới.

## 2. Hiểu các mức log và cách kế thừa logger

| Mức | Công dụng | Khi nào phù hợp |
| --- | --- | --- |
| `ERROR» | Sự cố nghiêm trọng cần xử lý | Theo dõi lỗi hoạt động, không đủ để giải thích mọi 401/403 |
| `WARN» | Tình trạng bất thường cần chú ý | Cảnh báo phụ thuộc/cấu hình, tránh xem mỗi login sai là lỗi hệ thống |
| `INFO» | Sự kiện vận hành mức tổng quan | Mặc định phần lớn môi trường, ưu tiên thông tin vừa đủ |
| `DEBUG» | Thông tin giúp phân tích luồng và quyết định | Bước đầu tiên khi điều tra một vấn đề security cụ thể |
| `TRACE» | Bước xử lý rất chi tiết, ví dụ filter được gọi theo thứ tự | Chỉ khi DEBUG chưa đủ; phạm vi và thời gian thật hẹp |
| `OFF» | Tắt log cho logger xác định | Rất thận trọng; có thể mất tín hiệu điều tra |

Logger thường có **tên theo package hoặc class**. Với Spring Boot + Logback, logger con có thể kế thừa mức từ logger cha khi không đặt mức riêng.

Ví dụ:

```properties
# Logging ở trạng thái bình thường
logging.level.root=INFO
logging.level.org.springframework.security=INFO
```

Đặt logger con cụ thể:

```properties
# Chỉ theo dõi chọn SecurityFilterChain cho request
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG

# Khi cần thấy thứ tự invoke filter ở mức TRACE
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Đây là **hai lựa chọn thay thế nhau**, không nên giữ cả hai dòng cùng key trong một file rồi hy vọng thứ tự cho ý nghĩa bảo mật. Khi class logger đặt `TRACE», nó có thể ghi nhiều hơn, còn các logger Spring Security khác vẫn theo mức kế thừa `INFO» nếu chưa được chỉnh riêng.

### DEBUG khác TRACE ở thực tế ra sao?

Trong Servlet, `FilterChainProxy» có thể ghi log kiểu “Securing GET /private” ở DEBUG. Ở TRACE, các log có thể bổ sung “Invoking [tên filter] (i/n)”. `DefaultSecurityFilterChain» có thể in danh sách filter lúc khởi động ở DEBUG. Từng phiên bản/filter cụ thể có thông điệp khác nhau; **không** viết parser dựa trên nguyên văn một câu log nội bộ rồi coi đó là API ổn định.

Ví dụ minh họa định dạng log (không phải output cố định):

```text
DEBUG ... FilterChainProxy : Securing GET /admin
TRACE ... FilterChainProxy : Invoking SecurityContextHolderFilter (...)
TRACE ... FilterChainProxy : Invoking BasicAuthenticationFilter (...)
TRACE ... FilterChainProxy : Invoking AuthorizationFilter (...)
DEBUG ... AccessDeniedHandlerImpl : Responding with 403 status code
```

**Phân biệt logger framework và ứng dụng:** `logging.level.org.springframework.security=TRACE» tăng log Spring Security nhưng **không mặc nhiên** tăng một logger do bạn tự tạo dưới `com.example.auth». Nếu đoạn code custom dùng `LoggerFactory.getLogger(MyAuthorizationService.class)», cần đặt mức cho logger ứng dụng đó — và phải kiểm tra nó có ghi secrets hay không trước khi bật.

## 3. Biết chỗ cần quan sát trong Spring Security Servlet

Một HTTP request đi qua `FilterChainProxy», rồi vào một trong các `SecurityFilterChain» khớp request và các security filter được cấu hình. Việc chọn chain, authentication và authorization là những nơi hữu ích để chẩn đoán.

```text
Client request
    |
    v
Servlet container / proxy / gateway
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |  Chọn SecurityFilterChain theo RequestMatcher
    |
    +--> Filter bảo vệ request / session / CSRF / CORS ...
    |
    +--> Authentication filter (Basic, form login, Bearer ...)
    |       |
    |       +--> AuthenticationManager / AuthenticationProvider
    |               |
    |               +--> UserDetailsService / IdP / token decoder
    |
    +--> AuthorizationFilter / AuthorizationManager
    |       |
    |       +--> Authentication đã có quyền hay chưa?
    |
    +--> Controller / method security
    |
    +--> ExceptionTranslationFilter / entry point / denied handler
              (tùy vị trí và loại exception)
```

**Cần nhớ:** CORS có thể được xử lý sớm hoặc bởi filter ở những vị trí cấu hình khác nhau; CSRF có thể trả 403 ngay khi request đổi trạng thái thiếu token; một API gateway có thể từ chối request **trước khi Spring Security nhìn thấy**. Đừng áp một sơ đồ lý thuyết thay cho việc xác minh chain đang chạy.

### Logger thường có ích

| Mục tiêu điều tra | Logger/package có thể thử | Mức khởi đầu |
| --- | --- | --- |
| Request có đi vào security chain không? | `org.springframework.security.web.FilterChainProxy» | DEBUG |
| Muốn biết từng filter được gọi theo thứ tự | `org.springframework.security.web.FilterChainProxy» | TRACE ngắn |
| Kiểm tra quyết định phân quyền URL | `org.springframework.security.web.access.intercept.AuthorizationFilter» | TRACE khi cần |
| Quy tắc `AuthorizationManager» | `org.springframework.security.authorization» | DEBUG, rồi TRACE chọn lọc |
| Xác thực HTTP Basic/form | `org.springframework.security.authentication» và nhóm `org.springframework.security.web.authentication» | DEBUG |
| CSRF 403 | `org.springframework.security.web.csrf» | DEBUG |
| Xử lý access denied/entry point | `org.springframework.security.web.access» | DEBUG |
| JWT Resource Server | `org.springframework.security.oauth2.server.resource» | DEBUG sau khi rà soát nội dung log |
| OAuth2 client/login | `org.springframework.security.oauth2.client» | DEBUG theo phạm vi |
| Filter/controller do ứng dụng tự viết | Package riêng, ví dụ `com.example.security» | DEBUG, tự kiểm soát format |

Tên logger và mức phát log có thể thay đổi giữa các phiên bản Spring Security; kiểm tra đúng dependency và class có mặt trong dự án. Không bật tất cả package cùng lúc nếu có thể thu hẹp.

### Đọc 401 và 403 bằng chuỗi sự kiện

- **401**: request chưa có authentication, credential sai hoặc token không hợp lệ; cần kiểm tra entry point, filter xác thực, provider và exception. Không kết luận 401 luôn là “người dùng nhập sai mật khẩu”: kho danh tính hoặc cấu hình có thể gặp sự cố.
- **403**: đã xác thực nhưng thiếu quyền, CSRF không hợp lệ, hoặc cơ chế bảo vệ khác; kiểm tra loại exception và filter gây lỗi thay vì chỉ đoán dựa vào status.
- **404 hoặc request không có log Security**: có thể URL không đến ứng dụng, `securityMatcher» không khớp, bị reverse proxy trả response, endpoint không có hoặc trace ở instance khác.

**Thứ tự chẩn đoán:** xác định request ID, nơi nhận request, chain nào xử lý, filter nào quyết định, authentication/authority/CSRF, và cuối cùng response HTTP. Ghi lại kết luận kèm bằng chứng, không chỉ ảnh chụp một dòng log.

## 4. Cấu hình an toàn theo môi trường bằng Spring Boot profile

Thay vì sửa mức log production mặc định rồi quên hoàn nguyên, dùng profile riêng **chỉ bật chủ động**:

```text
src/main/resources/
├── application.properties
└── application-diagnostics.properties
```

`application.properties» — mức bình thường:

```properties
# Mặc định không tạo TRACE chi tiết cho toàn bộ framework
logging.level.root=INFO
logging.level.org.springframework.security=INFO
```

`application-diagnostics.properties» — một cấu hình gỡ lỗi có phạm vi:

```properties
# Chỉ bật khi chủ động kích hoạt profile diagnostics
logging.level.root=INFO

# Luồng vào và lựa chọn filter
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG

# Quyết định authorization cần quan sát kỹ hơn
logging.level.org.springframework.security.web.access.intercept.AuthorizationFilter=TRACE
logging.level.org.springframework.security.authorization=DEBUG

# Phân tích authentication/CSRF khi liên quan vấn đề
logging.level.org.springframework.security.authentication=DEBUG
logging.level.org.springframework.security.web.csrf.CsrfFilter=DEBUG

# Log cho service custom chỉ nếu service không ghi bí mật
# logging.level.com.example.myapp.security=DEBUG
```

Ở đây `root» vẫn INFO; TRACE chỉ áp dụng một class logger. Nếu cần thấy từng lần invoke filter, **tạm thời** chuyển `FilterChainProxy» thành TRACE, sau đó trả về DEBUG/INFO. Không cho rằng `application-diagnostics.properties» an toàn tuyệt đối: extension và log message của framework vẫn cần được đánh giá theo dữ liệu thật của ứng dụng.

### Kích hoạt profile

Từ shell có Maven và Java 17:

```bash
# Chạy bình thường (INFO)
mvn spring-boot:run

# Chạy ở chế độ chẩn đoán có kiểm soát:
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
```

Với ứng dụng được đóng gói thành JAR:

```bash
java -jar target/security-logging-demo-1.0.0.jar --spring.profiles.active=diagnostics
```

**Không coi profile là quyền truy cập:** ai có thể thay đổi cách khởi động ứng dụng, command line, environment hoặc file config đều có thể làm thay đổi mức log. Quản lý các quyền đó theo quy trình deploy/ops.

### Đặt logger qua tham số khởi động

Khi cần một class rất cụ thể mà không muốn thêm profile cố định:

```bash
java -jar target/security-logging-demo-1.0.0.jar \
  --logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Đây là **cấu hình lúc khởi động**, không phải lệnh thay đổi log của process đang chạy. Muốn đổi runtime, dùng cơ chế quản trị/Actuator hoặc logging framework theo chính sách bảo mật. Khi lệnh được dùng trong container/CI, kiểm tra đối tượng nào có thể đọc command line và deployment manifest.

### Không nhầm “debug mode” của Spring Boot

`--debug» hoặc `debug=true» của Spring Boot chủ yếu tăng một tập log và báo cáo auto-configuration ở Boot; **không đồng nghĩa** `logging.level.org.springframework.security=TRACE». Tương tự, `@EnableWebSecurity(debug=true)» bật cơ chế debug của web security và có thể tạo logging đặc biệt, tiềm ẩn thông tin nhạy cảm; không phải lựa chọn mặc định cho production. Nếu muốn truy vết filter/authorization, thường nên bắt đầu từ **logger cụ thể**.

## 5. Một dự án Java 17 chạy được để điều tra 401/403

Ví dụ xây dựng một ứng dụng Servlet nhỏ có URL công khai, URL yêu cầu authentication và URL cần vai trò ADMIN. Các bài kiểm thử đảm bảo hành vi security độc lập với việc bật log. Khi chạy profile `diagnostics», có thể quan sát các logger đã cấu hình rồi đối chiếu với trạng thái 401/403/200.

### 5.1 Cấu trúc

```text
security-logging-demo/
├── pom.xml
└── src/
    ├── main/resources/
    │   ├── application.properties
    │   └── application-diagnostics.properties
    ├── main/java/com/example/securitylogging/
    │   └── SecurityLoggingDemoApplication.java
    └── test/java/com/example/securitylogging/
        └── SecurityLoggingDemoApplicationTest.java
```

### 5.2 Maven

Tạo `pom.xml»:

```xml
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
    <artifactId>security-logging-demo</artifactId>
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
```

Tạo đúng hai file properties trong mục 4. Chúng giúp giữ mức INFO bình thường và có chế độ diagnostics riêng.

### 5.3 Java application

Tạo `src/main/java/com/example/securitylogging/SecurityLoggingDemoApplication.java»:

```java
package com.example.securitylogging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityLoggingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLoggingDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo456"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class Controller {

        @GetMapping("/public")
        String publicEndpoint() {
            return "public ok";
        }

        @GetMapping("/me")
        String whoAmI(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/admin")
        String adminEndpoint() {
            return "admin ok";
        }
    }
}
```

**Giải thích:** `/public» là công khai; `/me» yêu cầu authentication; `/admin» yêu cầu `ROLE_ADMIN» mặc định. HTTP Basic giúp response anonymous là 401 thay vì redirect tới form login. `InMemoryUserDetailsManager» dùng hai user demo (chỉ trong môi trường học). BCrypt lưu hash; không ghi password vào logger hoặc response. Không thêm `@EnableWebSecurity(debug=true)» vì bài tập chọn lọc logger qua properties.

**Giới hạn:** demo chỉ dùng GET, nên không kiểm thử đầy đủ CSRF của POST. Khi điều tra 403 do CSRF trong ứng dụng thực tế, cần kiểm tra request đổi trạng thái riêng; không tắt CSRF để “làm rõ log” vì điều đó thay đổi nguyên nhân cần điều tra.

### 5.4 JUnit 5 / MockMvc kiểm tra hành vi an ninh

Tạo `src/test/java/com/example/securitylogging/SecurityLoggingDemoApplicationTest.java»:

```java
package com.example.securitylogging;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityLoggingDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceIsAvailableWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void anonymousAdminRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotBecomeAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validAdminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    void wrongPasswordIsNotAccepted() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedPrincipalIsAvailable() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }
}
```

Đây là **sáu ca kiểm thử**: public 200, anonymous 401, user thiếu quyền 403, admin đủ quyền 200, password sai 401 và principal đúng. Các status được chọn theo cấu hình HTTP Basic của ứng dụng này, không phải quy tắc bắt buộc cho mọi form login/OAuth2 system.

**Không viết test chỉ dựa vào nguyên văn log nội bộ.** Nội dung một dòng DEBUG/TRACE có thể thay đổi khi nâng cấp Spring Security. Với test chức năng, assert security behavior bằng response/side-effect; với cấu hình log, có thể kiểm tra level hiệu lực bằng API logging hoặc kiểm tra có kiểm soát trong môi trường chẩn đoán, không dựa trên một câu log cố định.

### 5.5 Chạy và quan sát

Trong thư mục `security-logging-demo» với JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
```

Gửi các request từ terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u reader:demo123 http://localhost:8080/admin
curl -i -u admin:demo456 http://localhost:8080/admin
curl -i -u admin:wrong http://localhost:8080/admin
```

| Request | HTTP kỳ vọng | Điều cần tìm trong log (không phụ thuộc nguyên văn) |
| --- | --- | --- |
| GET /public anonymous | 200 | Request đi vào chain; matcher permitAll |
| GET /admin anonymous | 401 | Không có authentication hợp lệ; entry point yêu cầu credential |
| GET /admin với reader | 403 | Đã authenticated, nhưng thiếu `ROLE_ADMIN» |
| GET /admin với admin | 200 | Authentication thành công, đủ role |
| GET /admin với sai password | 401 | Authentication thất bại; không hiển thị lý do nhạy cảm cho client |

Log chính xác phụ thuộc logger level, phiên bản và formatter. Nếu không thấy thông điệp mong đợi ở DEBUG, xem logger nào thực sự phát sự kiện rồi **chỉ tăng class đó** lên TRACE khi cần. Không tăng root logger lên TRACE một cách phản xạ.

**Sau khi thử xong:** dừng tiến trình diagnostics và khởi chạy không có profile đó, hoặc khôi phục log level bằng hệ thống quản trị; xác minh cấu hình effective đã quay về mặc định.

## 6. Đổi mức log khi ứng dụng đang chạy bằng Spring Boot Actuator

Không phải sự cố nào cũng cho phép khởi động lại. Spring Boot Actuator cung cấp **loggers endpoint** để xem và thay đổi mức logger runtime. Đây là **khả năng quản trị nhạy cảm**: người có quyền chỉnh logger có thể bật TRACE, làm tăng chi phí log và khiến dữ liệu được ghi chi tiết hơn.

**Nguyên tắc triển khai:** endpoint này thường không nên được công khai qua Internet. Dùng mạng quản trị riêng/localhost, mTLS/VPN/identity operator, phân quyền vận hành và audit, chính sách thời hạn. Chỉ bật Actuator loggers khi cần; không biến API thay đổi log thành endpoint dành cho mọi user đăng nhập.

### 6.1 Dependencies và exposure

Thêm dependency sau **vào `pom.xml» nếu thực sự dùng Actuator**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Trong **cấu hình quản trị riêng được bảo vệ**, có thể bật:

```properties
management.endpoints.web.exposure.include=health,loggers
```

Đây là **fragment cấu hình tùy chọn**, không phải phần mặc định cần chèn vào ứng dụng demo. Chỉ expose endpoint chưa đủ: **bắt buộc thêm security policy bảo vệ Actuator**. Nếu ứng dụng đã định nghĩa `SecurityFilterChain» tùy biến, đừng giả định auto-configuration sẽ bảo vệ các endpoint theo ý bạn. Cần matcher dành riêng cho management endpoint và mạng quản trị, không chỉ để `anyRequest().authenticated()».

Trong hệ thống có CSRF được bật và endpoint ghi dữ liệu qua HTTP POST, yêu cầu CSRF vẫn có thể áp dụng. Nếu dùng client automation không có cookie/browser session, thiết kế cách xác thực và CSRF cho luồng quản trị theo threat model; **không tắt CSRF toàn ứng dụng** để POST loggers hoạt động.

### 6.2 Xem, bật và khôi phục logger

Actuator sử dụng tên logger làm path, ví dụ:

```text
GET /actuator/loggers/org.springframework.security.web.FilterChainProxy
```

Response của logger có thể nêu `configuredLevel» và `effectiveLevel». Hai giá trị khác nhau: `configuredLevel = null» nghĩa là logger không có cấu hình trực tiếp và kế thừa từ cha; `effectiveLevel» là mức hiện hành sau kế thừa.

Để thay mức, gửi HTTP POST với JSON body:

```http
POST /actuator/loggers/org.springframework.security.web.FilterChainProxy
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

Muốn truy vấn chi tiết hơn trong một cửa sổ ngắn:

```http
POST /actuator/loggers/org.springframework.security.web.FilterChainProxy
Content-Type: application/json

{"configuredLevel":"TRACE"}
```

**Hoàn nguyên** explicit override đã đặt:

```http
POST /actuator/loggers/org.springframework.security.web.FilterChainProxy
Content-Type: application/json

{"configuredLevel":null}
```

Đây là ví dụ **định dạng request quản trị**, không phải gợi ý gửi trực tiếp vào endpoint public không được bảo vệ. Một request vận hành thực sự cần xác thực của operator, chính sách CSRF phù hợp, giới hạn mạng, ghi audit và phê duyệt. Nếu mức logger trước đó là `WARN»/`DEBUG» được cấu hình rõ, phải khôi phục **mức gốc**, không máy móc đặt `null» rồi thay đổi chính sách sản phẩm.

**Đặc điểm runtime:** các thay đổi log level qua Actuator thường áp dụng lên process hiện tại, không nhất thiết được lưu bền sau restart/deploy. Mỗi instance trong một cluster có cấu hình runtime riêng; cần biết instance nào đang phát log và đảm bảo rollback trên đúng các instance đã bật.

### 6.3 Quy trình thay đổi runtime được kiểm soát

1. Ghi nhận mức cũ bằng `GET /actuator/loggers/...» và xác định **configured vs effective**.
2. Chọn một logger và một instance cụ thể; xin phê duyệt/ticket nếu production có quy trình thay đổi.
3. Đặt DEBUG, quan sát request có correlation ID. Chỉ nâng TRACE khi DEBUG không đủ.
4. Giới hạn thời gian và log volume; kiểm tra CPU, I/O, queue, lưu trữ và thông tin nhạy cảm.
5. Khôi phục đúng mức cũ, đọc lại để xác minh; đóng ticket và ghi nhận thời điểm rollback.
6. Rà soát bản ghi đã sinh ra, hạn chế truy cập/retention nếu có nguy cơ chứa dữ liệu nhạy cảm.

Cơ chế thay đổi runtime nên được giám sát như một hành động **quản trị có audit**; không giao token điều khiển Actuator cho frontend/browser thông thường.

## 7. Một playbook quan sát 401/403 theo giả thuyết

### 7.1 Một request 401 dù client cho rằng credential đúng

**Giả thuyết:** request đi vào nhầm SecurityFilterChain, Authorization header không được nhận, provider không hỗ trợ token, hoặc kho danh tính/IdP lỗi.

Các bước:

1. Gắn **request ID/trace ID không chứa PII**, kiểm tra cùng ID ở gateway và ứng dụng.
2. Mở `FilterChainProxy=DEBUG» để xác định request có được Spring Security xử lý không.
3. Nếu cần, bật `org.springframework.security.authentication=DEBUG» hoặc logger filter liên quan, sau khi đảm bảo vùng test dùng credential giả.
4. Đối chiếu loại `AuthenticationException», provider, HTTP status upstream, timeout và lý do thất bại nội bộ. Không log raw password, Authorization header hoặc JWT.
5. Tắt lại logger, lưu kết luận; không đề nghị người dùng đổi mật khẩu nếu root cause là database/IdP outage.

**Tránh suy luận sai:** Spring Security có thể cố tình không phân biệt public message cho “không có user” và “password sai” để chống dò tài khoản. DEBUG/TRACE phục vụ nội bộ, không nên chuyển nguyên văn sang API response.

### 7.2 Một request 403 dù user đã đăng nhập

**Giả thuyết:** thiếu authority, role prefix sai, CSRF token thiếu, method security khác URL rule, hoặc policy dựa trên tenant.

Các bước:

1. Xác định **HTTP method**. Với POST/PUT/DELETE, kiểm tra CSRF trước khi sửa role.
2. Đọc `FilterChainProxy=DEBUG» và `AuthorizationFilter» ở mức phù hợp.
3. Kiểm tra `hasRole("ADMIN")» đang so với authority `ROLE_ADMIN» theo cấu hình prefix; `hasAuthority("SCOPE_read")» phải so đúng chuỗi.
4. Nếu `@PreAuthorize» nằm ở service, URL có thể pass nhưng method security vẫn deny. Kiểm tra log method-security ở package authorization và những proxy cần thiết.
5. Đừng in toàn bộ `Authentication.toString()» vô điều kiện; principal/claims có thể chứa PII hoặc metadata nhạy cảm.
6. Khôi phục mức log và viết regression test cho 403/200 đúng quyền.

### 7.3 403 xuất hiện chỉ trên trình duyệt

**Giả thuyết:** CORS preflight bị từ chối, CSRF token/cookie không được gửi, SameSite/Secure/proxy khiến session thay đổi.

Cần tách:

- **Preflight OPTIONS**: kiểm tra `Origin», `Access-Control-Request-Method» và các header được yêu cầu, cấu hình CORS filter và gateway. Browser không nhất thiết gửi credential trong preflight.
- **Actual POST**: kiểm tra CSRF token, cookie, Authentication và authorization.
- **Response header**: `Access-Control-Allow-Origin» đúng hay bị gateway ghi đè?
- **Mạng/proxy**: request có thật đến ứng dụng không, hay browser chặn trước khi thấy backend?

CORS không thay thế authentication hoặc CSRF. Không sửa tạm bằng `allowedOrigins("*")» hay `csrf.disable()» chỉ để xóa 403.

### 7.4 403/401 không có log Spring Security

Không có log **chưa chứng minh request an toàn hoặc không an toàn**. Có thể bật sai logger, đang xem nhầm instance, request đến gateway khác, log bị lọc, `securityMatcher» không khớp hoặc một filter không phát event ở mức đã bật. Xác minh access log của proxy/ingress, trace ID, cấu hình filter chain, logger effective level và routing trước khi tăng root lên TRACE.

## 8. Giảm nguy cơ lộ dữ liệu nhạy cảm trong DEBUG/TRACE

### 8.1 Những thông tin tuyệt đối không chủ động ghi ra

- Password/PIN/OTP, raw Basic Authorization header, raw JWT access/refresh token, API key, session cookie, CSRF token, OAuth authorization code, client secret.
- Private key, secret signing key, connection string chứa credential hoặc môi trường secret.
- Query parameters chứa token, reset link, số định danh nhạy cảm; request/response body có dữ liệu cá nhân, thông tin thanh toán hoặc y tế.
- Toàn bộ object `Authentication», `SecurityContext», `Principal», `UserDetails» hoặc claims nếu chưa review toString/serialization và trường dữ liệu.

Các logger framework có thể không cố ý in password, nhưng **extension, custom filter, HTTP client wire logs, access logs và thư viện bên thứ ba** vẫn có thể ghi chi tiết khác. Không thể bảo đảm log sạch chỉ bằng việc chọn category `org.springframework.security».

### 8.2 Cách viết log custom đúng

Phản ví dụ:

```java
// SAI — credential hoặc toàn bộ request object có thể bị lộ.
log.debug("Login request: {}", loginRequest);
log.trace("Authorization: {}", request.getHeader("Authorization"));
log.debug("Principal: {}", authentication.getPrincipal());
```

Các đoạn là **fragment** và `loginRequest», `request», `authentication» là biến do ứng dụng định nghĩa; không nên thực thi kiểu log này.

Thay bằng sự kiện có cấu trúc, ít dữ liệu:

```java
// Fragment dùng SLF4J; requestId đã được tạo, kiểm tra và giới hạn format.
log.debug("auth outcome={} requestId={} route={}",
    "DENIED", requestId, "/api/reports");
```

Không nhận route trực tiếp từ URL chứa query token. Nếu cần định danh user để điều tra, dùng identifier nội bộ/băm theo chính sách, không ghi email/username thô theo mặc định. Khi ghi exception, chỉ giữ loại lỗi và correlation ID đủ cho vận hành; stack trace chi tiết chỉ ở nơi được bảo vệ phù hợp.

### 8.3 Không log payload trong auth filter một cách tùy tiện

Một custom `OncePerRequestFilter» có thể nhận `HttpServletRequest». Nếu dùng `ContentCachingRequestWrapper» rồi in toàn body ở TRACE, bạn có thể ghi password, token và dữ liệu nhạy cảm. Nếu cần biết route, dùng **route template** hay whitelist path đã chuẩn hóa; tránh ghi URL query đầy đủ.

Dùng redaction theo **allowlist** tốt hơn blacklist: chỉ ghi những trường đã kiểm tra an toàn, không ghi mọi field rồi cố xóa một vài key như `password». Bí mật cũng có thể xuất hiện trong nested JSON, header tùy biến hoặc token ở URL.

### 8.4 Quyền truy cập log và retention

Log của hệ thống bảo mật là nguồn dữ liệu nhạy cảm. Khi bật TRACE cần kiểm tra:

| Kiểm soát | Cần thực hiện |
| --- | --- |
| Người xem | RBAC/mTLS/VPN; tách quyền xem log và quyền chỉnh mức logger |
| Môi trường | Ưu tiên local/staging dữ liệu giả hoặc đã khử định danh |
| Phạm vi | Logger, instance, request path và cửa sổ sự cố cụ thể |
| Thời hạn | Thời điểm bật/tắt ghi nhận; auto rollback nếu hạ tầng hỗ trợ |
| Dung lượng | Giới hạn volume; không khiến sink quá tải hoặc mất log audit quan trọng |
| Retention | TTL/xóa theo chính sách; mã hóa at-rest và in transit |
| Công cụ phụ | Reverse proxy, APM, distributed tracing và body capture cũng phải áp dụng redaction |
| Bằng chứng | Lưu kết luận và request ID; không đính kèm token/password vào ticket hoặc chat |

Nếu phát hiện secret trong log: giảm quyền truy cập, đánh giá mức độ lộ, kích hoạt quy trình xử lý sự cố, xoay/thu hồi credential khi cần và xử lý retention theo chính sách. **Chỉ tắt TRACE chưa xóa dữ liệu đã đẩy sang hệ thống log tập trung.**

## 9. Chi phí hiệu năng, độ tin cậy và dấu hiệu quá tải

Khi log thêm vào mỗi filter và mỗi request, kích thước và số lượng sự kiện có thể tăng mạnh:

- **CPU**: format chuỗi, stack trace, JSON serialization, regex redaction.
- **I/O và networking**: console/file appenders, log shipper, queue và backpressure.
- **Storage**: tăng chi phí index, lưu trữ và tìm kiếm.
- **Độ trễ**: synchronous appender hoặc sink bị chậm có thể kéo dài thời gian xử lý request.
- **Tính khả dụng**: disk đầy hoặc logging pipeline nghẽn có thể ảnh hưởng ứng dụng; tăng log đúng lúc lượng traffic đang cao có thể làm nặng outage.

Đừng dựa vào các con số quy ước như “TRACE tăng x% CPU” nếu chưa đo ở kiến trúc cụ thể. Quan sát p95/p99 latency, log events/s, backlog shipper, disk utilization, JVM CPU, network egress, error rate và lượng dữ liệu nhạy cảm được ghi.

**Mẹo quan trọng:** logger level khác với log sampling. Có thể dùng sampling ở pipeline để giảm volume, nhưng đừng sampling một cách mù quáng các event audit bắt buộc hoặc những sự kiện hiếm cần điều tra. Nếu dùng async appender, vẫn phải xử lý queue capacity/drop policy và dữ liệu nhạy cảm, không coi async là giải pháp vô hạn.

## 10. Khác biệt giữa Servlet, WebFlux và các lớp quan sát khác

| Thành phần | Servlet/Spring MVC | WebFlux/Reactive |
| --- | --- | --- |
| Security chain | `SecurityFilterChain», `FilterChainProxy» | `SecurityWebFilterChain», reactive web filters |
| Security context | Thường `SecurityContextHolder»/ThreadLocal | `ReactiveSecurityContextHolder»/Reactor Context |
| Truy vết lỗi | Filter, `ExceptionTranslationFilter», entry point/denied handler | Reactive authentication/authorization và error handler |
| Tracing theo request | Servlet request/MDC với propagation thích hợp | Reactor Context, context propagation |
| Nguy cơ khi tăng TRACE | Volume, PII, log I/O | Những rủi ro trên **và** nguy cơ làm chậm event-loop nếu appender/formatting blocking |

Không copy nguyên danh sách logger class của Servlet sang WebFlux rồi kết luận TRACE không hoạt động. WebFlux dùng các package liên quan `org.springframework.security.web.server» và các reactive components. Đồng thời, MDC không tự động theo subscriber khi Reactor đổi thread nếu chưa cấu hình context propagation phù hợp.

**Với distributed tracing**, trace/span ID cho phép tìm sự kiện mà không cần bật log toàn framework. Tuy nhiên trace attributes/baggage cũng có thể chứa dữ liệu nhạy cảm nếu thiết kế sai; không đưa token hay thông tin cá nhân vào span.

## 11. Quy trình gỡ lỗi có thể lặp lại, có điểm dừng

Một quy trình chuẩn cho nhóm phát triển và vận hành:

1. **Mô tả sự cố:** endpoint, method, thời điểm, môi trường, HTTP status, correlation ID, tần suất, ảnh hưởng. Không ghi password/token vào ticket.
2. **Xác lập giả thuyết:** CSRF, quyền, provider, matcher, gateway/IdP hay session. Chọn logger tương ứng.
3. **Kiểm tra mặc định:** metrics/audit/access log/sẵn có trước khi bật DEBUG.
4. **Chọn phạm vi nhỏ nhất:** local/staging trước; production chỉ khi có lý do và quyền, một instance hoặc phạm vi tách biệt.
5. **Ghi nhận mức ban đầu:** cấu hình profile/Actuator `configuredLevel»/`effectiveLevel», mức kế thừa, thời gian và người phê duyệt.
6. **Bật DEBUG và tái hiện:** dùng user demo, dữ liệu giả hoặc request đã khử nhạy cảm; xác minh request đến đúng instance.
7. **Chỉ nâng TRACE khi chưa đủ:** bật một class/package rất hẹp, giám sát volume và rủi ro; đặt thời điểm hết hiệu lực.
8. **Phân tích:** nối theo correlation ID, quyết định security, exception, response và upstream event; chứng minh root cause.
9. **Rollback ngay:** khôi phục **mức cũ**, kiểm tra effective level, tắt profile/nâng cấp deployment hoặc POST lại Actuator theo quy trình.
10. **Xác nhận sau thay đổi:** log volume, CPU, latency trở lại bình thường; kiểm tra không lộ secrets; viết regression test cho lỗi đã tìm.
11. **Đóng sự cố:** ghi kết luận, biến cố và cách ngăn tái phát, không lưu bản dump raw token/password trong tài liệu chia sẻ.

**Điểm dừng rõ ràng:** đủ bằng chứng xác định vấn đề thì tắt TRACE. Không giữ mức cao “để phòng lần sau”.

## 12. Các lỗi phổ biến khi bật DEBUG/TRACE

### Lỗi 1 — Đặt `logging.level.root=TRACE»

Mọi thư viện/SDK có thể đổ log rất lớn, gồm HTTP client, ORM, network và object do ứng dụng tự in. **Sửa:** bắt đầu từ logger Spring Security cụ thể và mở rộng từng bước khi có bằng chứng.

### Lỗi 2 — Nghĩ `--debug» là security TRACE

Flag debug của Spring Boot và logger Spring Security là hai cơ chế khác nhau. **Sửa:** kiểm tra effective logger level và chọn category chính xác.

### Lỗi 3 — Bật `@EnableWebSecurity(debug=true)» trong production

Chế độ debug đặc biệt có thể tạo nhiều thông tin request/security không phù hợp production. **Sửa:** ưu tiên DEBUG/TRACE logger hẹp ở môi trường an toàn, tắt sau khi xong.

### Lỗi 4 — Thấy 403 liền nâng TRACE rồi tắt CSRF

Một POST thiếu CSRF token bị 403 là hành vi đúng. **Sửa:** phân loại nguyên nhân bằng `CsrfFilter» và regression test, không thay đổi chính sách chỉ để request thành công.

### Lỗi 5 — In toàn bộ Authentication/Authorization header

Principal/token có thể chứa dữ liệu nhạy cảm, `toString()» có thể tiết lộ field không chủ đích. **Sửa:** structured log allowlist, không in credential, hash/mask khi chính sách yêu cầu.

### Lỗi 6 — Chỉ tăng logger nhưng xem nhầm instance

Trong microservice/cluster, request có thể tới pod khác. **Sửa:** trace ID, pod/instance ID, gateway access log, routing; đồng bộ/rollback ở những instance thực sự chỉnh.

### Lỗi 7 — Quên hoàn nguyên override runtime

`configuredLevel=TRACE» tồn tại trên process tới khi đổi lại hoặc restart tùy cấu hình. **Sửa:** lưu mức gốc, thông báo hết hạn, áp dụng rollback và đọc lại effective level.

### Lỗi 8 — Expose `/actuator/loggers» như endpoint public

Bất kỳ ai có quyền chỉnh logger có thể gây tăng log và lộ thông tin. **Sửa:** chỉ expose trong management network, xác thực người vận hành, phân quyền đặc biệt và audit.

### Lỗi 9 — Dùng một test kiểm tra nguyên văn message TRACE

Spring Security không cam kết mọi message theo cùng chuỗi khi nâng cấp. **Sửa:** kiểm tra hành vi security trong JUnit; log là dữ liệu quan sát, không phải hợp đồng API cho ứng dụng.

### Lỗi 10 — Giả định DEBUG/TRACE lúc nào cũng vô hại với hiệu năng

Ngay cả khi appender asynchronous, log formatter và queue vẫn tiêu tốn tài nguyên. **Sửa:** đo log rate, CPU, disk, latency; giới hạn TTL, logger và traffic.

### Lỗi 11 — Dùng environment variable cho mọi tên class

Spring Boot hỗ trợ `LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_SECURITY=DEBUG» cho package, nhưng một số cách binding environment variable viết hoa có thể không phân biệt chính xác phần tên class pha chữ hoa/thường. **Sửa:** dùng `application.properties», command-line property, `SPRING_APPLICATION_JSON» hoặc Actuator cho logger class cụ thể, và luôn kiểm tra effective level.

### Lỗi 12 — Gửi raw log vào issue hoặc công cụ AI

Dòng DEBUG/TRACE có thể chứa ID, token, URL nhạy cảm, dữ liệu tổ chức. **Sửa:** kiểm tra/khử định danh trước khi chia sẻ, tuân chính sách dữ liệu và quyền truy cập. Không chia sẻ secrets chỉ vì đang chẩn đoán lỗi.

## 13. Checklist quyết định bật mức log nào

| Tình huống | Bước đầu | Khi DEBUG chưa đủ | Điều phải xác minh |
| --- | --- | --- | --- |
| Không biết security chain nào khớp URL | `FilterChainProxy=DEBUG» | `FilterChainProxy=TRACE» | Đúng instance/RequestMatcher/filter |
| User có role nhưng nhận 403 | `AuthorizationFilter=DEBUG» hoặc package authorization | TRACE hẹp | Authority thật, role prefix, method security |
| POST bị 403 | `CsrfFilter=DEBUG» | TRACE có thời hạn | Token thiếu/sai, CSRF matcher, session/cookie |
| HTTP Basic trả 401 | Package authentication DEBUG | Logger provider/filter cụ thể | Không log password hoặc header Basic |
| Bearer JWT bị từ chối | Resource-server package DEBUG | TRACE class liên quan nếu an toàn | Issuer, audience, expiry, decoder/IdP |
| OAuth login thất bại | OAuth2 client package DEBUG | TRACE chỉ ở môi trường giả dữ liệu | Redirect, state, error code, IdP response |
| Log bị thiếu | Đối chiếu logger effective level + instance | Xem proxy/trace ID | Request có đến Spring Security không |
| Production chưa xác định nguyên nhân | Metrics và log INFO hiện có | DEBUG trong một cửa sổ, TRACE cuối cùng | Phê duyệt, TTL, rollback, log redaction |

**Quy tắc chọn mức:** một câu hỏi hẹp → một logger hẹp → một thời hạn cụ thể → rollback xác nhận.

## 14. Kết luận

- `DEBUG»/`TRACE» rất hữu ích để hiểu filter chain, authentication, authorization, CSRF và đường xử lý 401/403, nhưng **không nên được bật rộng hoặc vĩnh viễn**.
- Bắt đầu từ `INFO» khi vận hành bình thường, nâng `DEBUG» cho package/class liên quan; `TRACE» chỉ khi cần chi tiết hơn trong môi trường và thời gian đã kiểm soát.
- Dùng profile hoặc override tạm thời khi khởi chạy; nếu đổi runtime qua **Actuator loggers endpoint**, bắt buộc bảo vệ endpoint, ghi lại mức cũ, xác minh rollback và audit.
- Chẩn đoán bằng **correlation ID, root cause và hành vi security**, không chỉ status HTTP hay nguyên văn một dòng log.
- Không ghi password, token, Authorization header, cookie hoặc toàn bộ principal/request vào log; tránh để logging gây nghẽn CPU/I/O/storage.
- Sau khi có kết luận, **hoàn nguyên log level và thêm regression test** để lần sau không phải bật TRACE cho cùng lỗi.

## Tài liệu chính thức để đối chiếu phiên bản

- Spring Security — Servlet Architecture, phần Security Filters/Logging: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorization for Servlet: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Testing MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot — Actuator Loggers endpoint: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- Spring Boot — Actuator Endpoint Security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- OWASP Cheat Sheet — Logging: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html