# Đặt cấu hình theo môi trường mà không mở quyền ngoài ý muốn

Cùng một ứng dụng Spring Boot có thể chạy trên máy lập trình viên (local/dev), môi trường kiểm thử (test/staging) và môi trường vận hành (production). Các môi trường thường khác nhau về cổng, database, endpoint tích hợp, danh tính máy, chứng chỉ và thông số vận hành. Nhưng **chính sách phân quyền cốt lõi không được vô tình nới lỏng** chỉ vì một profile, biến môi trường hoặc cờ cấu hình thay đổi.

Bài học tập trung vào **cấu hình Spring Security hiện đại với SecurityFilterChain**, Spring Profiles, externalized configuration và feature flags. Mục tiêu là cho phép thay đổi **điều kiện vận hành và sự hiện diện của tính năng thử nghiệm**, đồng thời giữ quyền truy cập theo nguyên tắc **deny by default, least privilege, verify every environment**.

Ví dụ thực hành dùng Java 17+, Spring Boot 3.3.6 và Spring Security 6.x. Đây là bài lab trên localhost: tài khoản trong bộ nhớ chỉ được kích hoạt ở profile local; ngoài local, ví dụ cố ý **không cung cấp tài khoản đăng nhập** để mặc định từ chối API cần xác thực. Muốn dùng production, phải thay bằng cơ chế danh tính thật (chẳng hạn OAuth2 Resource Server hoặc một user store an toàn), kiểm soát hạ tầng và cập nhật phiên bản được hỗ trợ. Không lấy tài khoản demo này làm giải pháp đăng nhập cho production.

## 1. Vấn đề: môi trường khác nhau nhưng quyền phải có chủ đích

Hãy tưởng tượng ứng dụng có ba đường dẫn:

- GET /api/ping: kiểm tra phản hồi cơ bản, được công khai theo thiết kế.
- GET /api/me: trả principal hiện tại, chỉ dành cho người đã xác thực.
- GET /internal/diagnostics: hỗ trợ kiểm tra tại máy local, chỉ dành cho người có ROLE_OPS; **không tồn tại như một Controller khi chạy production**.

Trong local, đội phát triển muốn bật diagnostics và tài khoản thử nghiệm. Trong production, một operator vô tình đặt biến APP_DIAGNOSTICS_ENABLED=true. Nếu mã chỉ viết điều kiện “flag=true thì permitAll”, hoặc một cấu hình local ghi đè SecurityFilterChain production, ứng dụng có thể mở thêm API nhạy cảm.

**Thiết kế đúng** đặt những câu hỏi trước khi viết code:

1. Điểm nào thực sự công khai trong **mọi** môi trường?
2. Danh tính và quyền nào được tin cậy, kể cả khi một flag bị bật sai?
3. Điều kiện nào cho phép một route hoặc bean chẩn đoán tồn tại?
4. Nếu profile bị thiếu, đặt sai tên hoặc đồng thời bật local và prod thì ứng dụng sẽ xử lý thế nào?
5. Nếu một property bị ghi đè bởi command-line, environment variable hoặc cấu hình ngoài JAR, những hàng rào bảo vệ nào vẫn còn?
6. Làm sao kiểm chứng được **response và side effects**, không chỉ xem file cấu hình?

Một profile không phải ranh giới bảo mật tự động. Nó là điều kiện chọn cấu hình. **An toàn đến từ policy rõ ràng, tính độc lập của các hàng rào bảo vệ, thông tin danh tính đáng tin và kiểm thử trên cấu hình thực sự được triển khai.**

## 2. Phân biệt profile, property, secret và security policy

| Khái niệm | Dùng để làm gì? | Rủi ro khi dùng sai |
| --- | --- | --- |
| **Spring Profile** | Kích hoạt một nhóm bean hoặc tài liệu cấu hình theo tên như local, test, prod. | Profile local có thể vô tình kích hoạt ở môi trường thật; nhiều profile có thể cùng hoạt động. |
| **Externalized property** | Cấu hình URL đối tác, timeout, cổng, logging, feature flags từ YAML, env hoặc CLI. | Nguồn ưu tiên cao hơn có thể ghi đè giá trị an toàn trong application.yml. |
| **Feature flag** | Bật/tắt một chức năng hoặc chế độ vận hành. | Dùng flag để bỏ qua xác thực/phân quyền có thể mở quyền quá rộng. |
| **Secret** | Password, private key, client secret, token ký hoặc thông tin truy cập database. | Commit secret vào repo, in log hoặc dùng chung cho local và production. |
| **SecurityFilterChain** | Thi hành quy tắc HTTP, xác thực và phân quyền cho các request phù hợp. | Một chain có securityMatcher quá hẹp có thể để request nằm ngoài mọi chain. |
| **Authorization rule** | Quyết định ai được gọi một path/method hoặc thao tác trên tài nguyên. | permitAll() quá rộng, matcher sai thứ tự hoặc thiếu kiểm tra owner/tenant. |
| **Deployment policy** | Giới hạn cấu hình được phép chạy, danh tính runtime, mạng, secret và kiểm tra trước deploy. | Chỉ dựa vào YAML trong JAR nhưng bỏ qua giá trị cuối cùng ở Kubernetes/CI/CD. |

**Profile phù hợp để chọn tính năng hoặc adapter triển khai.** Property phù hợp với thông số vận hành hoặc feature flag. **Authorization** phải xác định hành động nào được phép bằng danh tính tin cậy; không nên có logic “nếu dev thì bỏ qua toàn bộ security”.

Điều cần tránh:

~~~java
// Anti-pattern: mảnh cấu hình KHÔNG nên đưa vào ứng dụng thật.
if (environment.acceptsProfiles(Profiles.of("dev"))) {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().permitAll());
} else {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
}
~~~

Nếu dev bị bật trên staging/production hoặc giá trị runtime không như dự kiến, toàn bộ API có thể công khai. Các endpoint vốn chỉ dành cho admin cũng bị cấp quyền quá mức. Đây là **lỗi thay đổi chính sách**, không phải chỉ là lỗi đặt tên profile.

## 3. Spring Boot quyết định cấu hình hiệu lực như thế nào?

Spring Boot hỗ trợ **application.yml**, **application-{profile}.yml**, environment variables, system properties, command-line arguments và nhiều nguồn cấu hình ngoài JAR. Các nguồn được hợp nhất theo thứ tự ưu tiên: **nguồn có ưu tiên cao hơn có thể ghi đè nguồn thấp hơn**.

Ví dụ:

~~~yaml
# src/main/resources/application.yml
app:
  diagnostics:
    enabled: false
~~~

~~~yaml
# src/main/resources/application-local.yml
app:
  diagnostics:
    enabled: true
~~~

~~~yaml
# src/main/resources/application-prod.yml
app:
  diagnostics:
    enabled: false
~~~

Khi chạy với profile local, giá trị từ application-local.yml thường ghi đè file cơ sở, làm app.diagnostics.enabled thành true. Khi chạy với prod, giá trị false được sử dụng **nếu không bị nguồn có ưu tiên cao hơn ghi đè**.

Ví dụ command-line:

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=prod --app.diagnostics.enabled=true
~~~

Trong Spring Boot, command-line arguments theo mặc định có thể ghi đè giá trị trong file. Vì vậy **application-prod.yml đặt false chưa phải một bảo đảm tuyệt đối**. Đó là lý do chúng ta cần nhiều điều kiện độc lập, và một SecurityFilterChain không tự mở quyền theo flag.

### 3.1. Những nguồn override đáng chú ý

- File application.yml nằm trong ứng dụng.
- File application-local.yml, application-prod.yml khi profile tương ứng được bật.
- File cấu hình được đặt bên ngoài artifact, chẳng hạn do container/orchestrator mount.
- Environment variable, ví dụ APP_DIAGNOSTICS_ENABLED.
- Java system property, ví dụ -Dapp.diagnostics.enabled=true.
- Command-line property, ví dụ --app.diagnostics.enabled=true.
- Test properties hoặc cấu hình riêng của framework test trong môi trường kiểm thử.

**Không ghi nhớ một bảng ưu tiên rút gọn rồi xem là đúng cho mọi trường hợp.** Spring Boot có thứ tự PropertySource, location group và cơ chế import riêng; các phiên bản có thể có thêm nguồn cấu hình. Khi nghi ngờ, tra tài liệu đúng phiên bản và xác minh giá trị hiệu lực theo môi trường đang chạy.

Không in toàn bộ Environment hoặc endpoint /env ra client để tìm một flag: nó có thể chứa password, token, URL nội bộ hoặc metadata nhạy cảm. Nếu cần quan sát, chỉ ghi **tên profile, cờ boolean cho phép công bố và định danh bản build**, theo chính sách log an toàn.

### 3.2. Nhiều profile cùng hoạt động

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=local,prod
~~~

Spring Boot có thể kích hoạt nhiều profile cùng lúc. Với nhiều tài liệu profile-specific, thứ tự nạp và ưu tiên quyết định property cuối cùng. **Không được nghĩ “có prod thì chắc chắn mọi cấu hình local biến mất”.**

Annotation:

~~~java
@Profile("local")
~~~

chỉ kiểm tra local đang active; nó **vẫn đúng** nếu local và prod cùng được bật. Ngược lại, biểu thức:

~~~java
@Profile("local & !prod")
~~~

đòi hỏi có local và **không có prod**. Biểu thức profile dùng toán tử AND/NOT do Spring Framework hỗ trợ. Nó thích hợp cho một tính năng chỉ tồn tại trên local, nhưng chưa thay thế phân quyền và network policy.

Các tên profile phải được chuẩn hóa trong dự án: local, test, staging và prod không phải từ khóa có đặc quyền bảo mật. Chọn tên nhất quán, xác minh tại pipeline và không dựa vào chuỗi viết khác nhau như prod/production để quyết định an toàn.

## 4. Nguyên tắc an toàn khi thiết kế SecurityFilterChain

### 4.1. Một chính sách bảo vệ lõi, ít thay đổi theo môi trường

Khi API có cùng mô hình quyền ở mọi nơi, nên giữ **một SecurityFilterChain** với các luật giống nhau:

~~~java
// Mảnh cấu hình minh họa trong lớp @Configuration.
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
        .requestMatchers(HttpMethod.GET, "/internal/diagnostics")
            .hasRole("OPS")
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults()).build();
}
~~~

Bất kể profile nào:

- GET /api/ping được phép công khai, vì đó là quyết định nghiệp vụ cố ý.
- GET /api/me yêu cầu Authentication hợp lệ.
- GET /internal/diagnostics yêu cầu ROLE_OPS **ngay cả trên local**.
- Mọi method và URL không được liệt kê sẽ bị từ chối bởi denyAll().

Cấu hình trên dùng HTTP Basic cho bài lab; **cơ chế xác thực của production** cần thay bằng cấu hình được thiết kế phù hợp. Đổi cách xác minh credential không đồng nghĩa phải đổi quyền công khai/thành viên/admin.

### 4.2. Không dùng permitAll để “debug cho nhanh”

Mẫu nguy hiểm:

~~~java
// Anti-pattern: mảnh minh họa sai.
if (diagnosticsEnabled) {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/internal/**").permitAll());
}
~~~

Một biến môi trường có thể trở thành công tắc mở quyền. Nếu cần xem diagnostics, hãy sử dụng **đường riêng, quyền riêng và chỉ tạo bean ở môi trường phù hợp**, đồng thời kiểm soát mạng truy cập. Cờ feature chỉ quyết định chức năng có tồn tại, không tự cấp quyền để sử dụng.

### 4.3. SecurityMatcher khác requestMatchers

Khi dùng nhiều SecurityFilterChain:

- **securityMatcher("/api/**")** giới hạn **toàn bộ chain** chỉ áp dụng cho những request khớp phạm vi đó.
- **requestMatchers("/api/admin/**").hasRole("ADMIN")** là rule authorization **bên trong một chain đã được chọn**.
- **anyRequest().denyAll()** chỉ áp dụng cho những request thuộc chain được chọn, không bảo vệ các URL nằm ngoài securityMatcher của chain.
- Nếu **không chain nào khớp request**, Spring Security có thể **không bảo vệ request đó**.

Đây là lỗi hay xảy ra khi tạo chain riêng cho local/admin rồi quên fallback.

~~~java
// Anti-pattern: chỉ có chain /api/**, URL ngoài /api có thể không được bảo vệ.
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated())
        .build();
}
~~~

Nếu thực sự phải dùng nhiều chain, hãy giữ một **fallback SecurityFilterChain không có securityMatcher hẹp** và đặt rule chặn mọi đường không được phép. Quản lý thứ tự @Order, filter authentication của từng chain và test các path nằm ngoài scope. Nếu không cần tách chain, **một chain bao phủ toàn ứng dụng thường dễ kiểm chứng hơn**.

### 4.4. HTTP method, pattern và precedence

~~~java
.requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
~~~

cho phép **GET**, không đồng nghĩa tự cho phép POST/DELETE tại cùng path. Các matcher được xét theo thứ tự khai báo; đặt luật cụ thể trước luật tổng quát. Dùng hasRole("OPS") kiểm authority ROLE_OPS; hasAuthority("OPS") là điều kiện khác.

Tuy nhiên, SecurityFilterChain không hiểu mọi quyền nghiệp vụ: GET /api/orders/42 đã qua authenticated() vẫn cần Service kiểm tra chủ sở hữu/tenant. Một flag môi trường không được phép bỏ qua kiểm soát đó.

## 5. Bật chức năng local bằng hai điều kiện độc lập

Để một endpoint thử nghiệm chỉ tồn tại khi thực sự cần, ví dụ sử dụng **hai điều kiện**:

1. Có profile **local** và **không có prod**.
2. Flag **app.diagnostics.enabled=true** được đặt rõ ràng.

Ngoài ra, **SecurityFilterChain luôn yêu cầu ROLE_OPS** nếu route hiện diện. Điều này tạo ba hàng rào: chọn môi trường, bật tính năng có chủ đích và phân quyền khi gọi.

Ví dụ:

~~~java
@RestController
@Profile("local & !prod")
@ConditionalOnProperty(
    prefix = "app.diagnostics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class LocalDiagnosticsController {
    // GET /internal/diagnostics được khai báo ở đây.
}
~~~

**@ConditionalOnProperty** với havingValue="true" chỉ khớp khi giá trị property được xác định là true theo quy tắc của Boot; **matchIfMissing=false** khiến property vắng mặt không tự bật tính năng. Trong file application.yml, giá trị mặc định lại được đặt false để người vận hành nhìn thấy ý định an toàn ngay từ đầu.

| Active profiles | Flag hiệu lực | Controller diagnostics? | Điều kiện truy cập khi hiện diện |
| --- | --- | --- | --- |
| Không có local | false hoặc true | **Không** | Không có handler diagnostics. |
| local | false | **Không** | Không có handler diagnostics. |
| local | true | **Có** | Chỉ principal có ROLE_OPS. |
| prod | true do override nhầm | **Không** | Profile guard ngăn bean được đăng ký. |
| local và prod | true | **Không** | Biểu thức local & !prod không thỏa. |
| test/staging | true | **Không** | Không có profile local. |

Những gì cần tránh:

- @Profile("!prod") trên bean debug: nếu không có profile nào, biểu thức !prod vẫn đúng, làm debug được mở trong những môi trường không rõ tên.
- @ConditionalOnProperty(name="debug", matchIfMissing=true): property bị quên cũng bật tính năng.
- Điều kiện được dùng để **tắt bộ lọc authorization** thay vì chỉ kiểm việc bean có tồn tại.
- Đưa lại cùng một debug endpoint ở Controller khác không có guard.
- Dựa duy nhất vào profile guard nhưng không kiểm soát identity, role, mạng và rate limit.

**Lưu ý:** Nếu một deployment thực tế đặt profile local nhưng không bật prod, guard này sẽ coi đó là local. Vì thế CD/CI phải xác nhận profile dự kiến và có thể từ chối deployment không khớp; ứng dụng không thể tự biết một tên profile đang được sử dụng sai ở một cluster production.

## 6. Bài thực hành Java 17 / Spring Boot 3.3.6

Ta xây một ứng dụng có cùng file JAR chạy với profile local hoặc prod. Mã cấu hình authorization **không được nới lỏng theo profile**. Tài khoản demo chỉ tồn tại khi local và không prod; các môi trường khác có user store rỗng nên **không thể dùng tài khoản demo để đăng nhập**.

**Yêu cầu:** JDK 17+, Maven 3.9+, cổng 8080 còn trống. Mọi thử nghiệm dùng localhost và dữ liệu giả.

### 6.1. Cấu trúc dự án

~~~text
security-env-demo/
  pom.xml
  src/main/resources/
    application.yml
    application-local.yml
    application-prod.yml
  src/main/java/com/example/envdemo/
    SecurityEnvApplication.java
    ApiController.java
    LocalDiagnosticsController.java
    SecurityConfig.java
  src/test/java/com/example/envdemo/
    LocalProfileTests.java
    LocalDisabledTests.java
    ProductionProfileTests.java
    MixedProfilesTests.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-env-demo</artifactId>
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

Không cần dependency Spring WebFlux: ví dụ là Spring MVC/Servlet với SecurityFilterChain và HttpSecurity. Nếu dự án thật dùng WebFlux, cần ServerHttpSecurity và SecurityWebFilterChain tương ứng.

### 6.3. application.yml

~~~yaml
spring:
  application:
    name: security-env-demo

app:
  diagnostics:
    enabled: false
~~~

File cơ sở **không gắn spring.profiles.active=local**. Profile được chọn rõ ở lúc chạy/deploy. Khi không có profile local, tài khoản demo và diagnostics không được tạo.

### 6.4. application-local.yml

~~~yaml
app:
  diagnostics:
    enabled: true
~~~

Profile local chỉ bật **tính năng có điều kiện**, không chứa anyRequest().permitAll() và không định nghĩa một bản SecurityFilterChain yếu hơn. Khi chạy local, endpoint thử nghiệm vẫn chỉ dành cho ROLE_OPS.

### 6.5. application-prod.yml

~~~yaml
app:
  diagnostics:
    enabled: false
~~~

File production đặt false như một giá trị mong muốn nhưng **không dựa riêng vào nó**. Một property bên ngoài có thể override giá trị này; điều kiện @Profile("local & !prod") vẫn khiến bean chẩn đoán không tồn tại khi prod đang active.

### 6.6. SecurityEnvApplication.java

~~~java
package com.example.envdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityEnvApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityEnvApplication.class, args);
    }
}
~~~

Class main nằm ở package gốc com.example.envdemo để Spring Boot quét các bean nằm cùng package. Không kích hoạt profile local ở main vì điều đó có thể ảnh hưởng mọi môi trường dùng chung artifact.

### 6.7. ApiController.java

~~~java
package com.example.envdemo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

**GET /api/ping** là endpoint được công khai có chủ đích, trả JSON status=ok. Không đặt dữ liệu debug, phiên bản dependency hoặc thông tin môi trường vào đây.

**GET /api/me** cần authentication. Danh tính lấy từ Authentication do Spring Security xác thực, không tin userId do client tự gửi trong query/header. Nếu thực tế trả hồ sơ chứa dữ liệu nhạy cảm, vẫn cần kiểm quyền đối tượng và đặt cache policy thích hợp.

### 6.8. LocalDiagnosticsController.java

~~~java
package com.example.envdemo;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("local & !prod")
@ConditionalOnProperty(
    prefix = "app.diagnostics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class LocalDiagnosticsController {

    @GetMapping("/internal/diagnostics")
    public Map<String, String> diagnostics() {
        return Map.of("mode", "local", "details", "demo-only");
    }
}
~~~

Controller trả một chuỗi cố định, **không in Environment, secrets, connection strings, principal details hoặc stack trace**. Dù trong môi trường local, dữ liệu chẩn đoán vẫn nên ở mức tối thiểu.

**Hai điều kiện trên chỉ quyết định bean có tồn tại hay không.** Quyền truy cập route vẫn phải được SecurityFilterChain kiểm tra độc lập.

### 6.9. SecurityConfig.java

~~~java
package com.example.envdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
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

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET,
                    "/internal/diagnostics").hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            Environment env,
            PasswordEncoder encoder) {

        boolean localOnly =
            env.acceptsProfiles(Profiles.of("local & !prod"));

        if (!localOnly) {
            // Ví dụ cố ý không cung cấp credential demo
            // ở prod, test hoặc khi thiếu profile local.
            return new InMemoryUserDetailsManager();
        }

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-learner"))
            .roles("USER")
            .build();

        UserDetails operator = User.withUsername("operator")
            .password(encoder.encode("demo-ops"))
            .roles("USER", "OPS")
            .build();

        return new InMemoryUserDetailsManager(learner, operator);
    }
}
~~~

Phân tích các quyết định:

1. **Không đặt @Profile trên SecurityFilterChain.** Bean filter chain luôn tồn tại, kể cả profile vắng mặt. Nó không dùng securityMatcher hẹp nên mặc định bao phủ các request của ứng dụng theo cơ chế chain.
2. **GET /api/ping được public cố ý**, không có logic dựa vào env để cho phép thêm URL.
3. **GET /api/me dùng authenticated()**; profile nào cũng yêu cầu danh tính hợp lệ.
4. **GET /internal/diagnostics yêu cầu ROLE_OPS** bất kể flag, nên một người dùng USER ở local vẫn bị 403.
5. **anyRequest().denyAll()** giúp các method/path chưa được liệt kê không tự mở quyền.
6. **PasswordEncoder dùng BCrypt**, không lưu plain password trong UserDetails.
7. **UserDetailsService luôn là bean**, nhưng bên ngoài profile local & !prod trả kho user rỗng. Không có user demo có thể xác thực ở đó.
8. **Cấu hình HTTP Basic vẫn hoạt động về mặt giao thức** nhưng ngoài local không có principal demo; API cần đăng nhập sẽ trả 401 với credential demo. Đây là **mặc định từ chối để thực hành**, không phải giải pháp production identity.
9. **CSRF mặc định không bị tắt**. Bài chỉ dùng GET. Với ứng dụng có cookie hoặc credentials được trình duyệt tự gửi và các thao tác POST/PUT/PATCH/DELETE, cần đánh giá CSRF và cơ chế client theo threat model.
10. HTTP Basic chỉ Base64 credentials, **phải dùng HTTPS** khi trao đổi credentials trên mạng thật. Lab chỉ sử dụng dữ liệu giả trên localhost.

Đừng đổi nhánh ngoài local thành một user mặc định có mật khẩu cứng. Nếu sản phẩm thật cần chạy ở prod, hãy tích hợp OAuth2/OIDC, JWT Resource Server, opaque-token introspection hoặc nguồn danh tính đã phê duyệt. **Thay identity provider có thể cần cấu hình authn riêng**, nhưng chính sách quyền trong authorizeHttpRequests vẫn phải được xác minh và không được mở rộng ngầm.

## 7. Chạy cùng artifact ở các môi trường

### 7.1. Build và chạy local

Tại thư mục security-env-demo:

~~~bash
mvn test
mvn package
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=local
~~~

Dùng terminal thứ hai để thử. Trên Windows PowerShell nên dùng **curl.exe**; Linux/macOS thường dùng **curl**.

~~~powershell
curl.exe -i http://localhost:8080/api/ping
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u learner:demo-learner http://localhost:8080/api/me
curl.exe -i -u learner:demo-learner http://localhost:8080/internal/diagnostics
curl.exe -i -u operator:demo-ops http://localhost:8080/internal/diagnostics
~~~

Kết quả HTTP **dự kiến**:

| Request | Status | Nguyên nhân |
| --- | --- | --- |
| GET /api/ping ẩn danh | 200 | Route public cố ý; body JSON có status=ok. |
| GET /api/me ẩn danh | 401 | Thiếu HTTP Basic credential. |
| GET /api/me với learner/demo-learner | 200 | Đã xác thực; body user=learner. |
| GET /internal/diagnostics với learner | 403 | Credential hợp lệ nhưng thiếu ROLE_OPS. |
| GET /internal/diagnostics với operator/demo-ops | 200 | Có ROLE_OPS và bean đang tồn tại ở local. |
| POST /api/ping với operator | 403 nếu qua được CSRF | Method POST không được cấp quyền; yêu cầu thiếu CSRF còn có thể bị chặn sớm. |

Các header phụ thay đổi theo Servlet container. HTTP Basic thường có header WWW-Authenticate trong response 401. Đối với GET public, **không gửi Authorization sai** vì filter xác thực có thể xử lý credential lỗi trước khi tới authorization permitAll().

### 7.2. Chạy prod với flag cố tình bật sai

Dừng phiên local và chạy:

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=prod --app.diagnostics.enabled=true
~~~

Kết quả kỳ vọng:

- GET /api/ping không credential: **200**.
- GET /api/me với learner/demo-learner: **401** vì user demo không được tạo.
- GET /internal/diagnostics với operator/demo-ops: **401**, vì không có tài khoản demo; Controller diagnostics cũng **không được đăng ký**.
- Không có route diagnostics hoạt động trong prod, dù flag true bị ép từ command-line.

Điểm bảo vệ chính là **@Profile("local & !prod")** trên Controller. Điều kiện property của @ConditionalOnProperty là lớp bổ sung, còn policy role áp dụng nếu bean hiện diện.

Với một IdP production thật, request mang principal có ROLE_OPS có thể đi qua authorization cho URL diagnostics, nhưng do **không có handler**, ứng dụng vẫn không được trả nội dung diagnostics. Mã 404/403 của URL không tồn tại có thể phụ thuộc cách cấu hình error dispatch/handler; **đừng sử dụng riêng status để chứng minh bean vắng mặt**. Hãy test trực tiếp ApplicationContext và kiểm tra không có dữ liệu nhạy cảm bị trả ra.

### 7.3. Chạy với hai profile cùng lúc

~~~bash
java -jar target/security-env-demo-1.0.0.jar --spring.profiles.active=local,prod --app.diagnostics.enabled=true
~~~

Trong demo, điều kiện **local & !prod** không đúng nên bean diagnostics và user demo không được tạo. Đây là một hành vi **fail closed** đối với hai phần đó, dù property có thể bị override.

Trên hệ thống thật, pipeline nên **từ chối cấu hình profile mâu thuẫn trước deploy**: không cho một bản phát hành có cả local và prod xuất hiện ở cluster production. Kiểm tra manifest/Helm values hoặc thông số hệ thống thực sự đang chạy, không chỉ application-prod.yml trong source.

### 7.4. Khi không chỉ định profile

Nếu không có active profile, Spring dùng cơ chế profile mặc định của framework. Trong bài này, vì không có local nên tài khoản demo và Controller chẩn đoán **không được tạo**. Đó là cách ứng xử an toàn đối với một môi trường chưa được xác định.

Đừng cấu hình **spring.profiles.default=local** chỉ để tiện trên laptop nếu artifact được chia sẻ cho nhiều môi trường: quên set active profile ở production sẽ vô tình kích hoạt local.

## 8. Kiểm thử tự động trên nhiều profile

Đọc YAML chưa đủ: ta cần **khởi tạo ApplicationContext dưới từng tập profile** rồi xác minh bean, status và quyền thật. Bộ test bên dưới dùng Spring Boot Test, JUnit 5, MockMvc và Spring Security Test.

### 8.1. LocalProfileTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.context.ActiveProfiles;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("local")
class LocalProfileTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void privateApiRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateApiAcceptsLocalUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "demo-learner")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void diagnosticsRejectsOrdinaryUser() throws Exception {
        mvc.perform(get("/internal/diagnostics")
                .with(httpBasic("learner", "demo-learner")))
            .andExpect(status().isForbidden());
    }

    @Test
    void diagnosticsAllowsLocalOperator() throws Exception {
        mvc.perform(get("/internal/diagnostics")
                .with(httpBasic("operator", "demo-ops")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("local"));
    }

    @Test
    void arbitraryPathIsDeniedEvenForOperator() throws Exception {
        mvc.perform(get("/api/not-listed")
                .with(httpBasic("operator", "demo-ops")))
            .andExpect(status().isForbidden());
    }

    @Test
    void spoofedRoleHeaderDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/internal/diagnostics")
                .header("X-Role", "OPS"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Các test chứng minh **local không đồng nghĩa mọi thứ đều public**: anonymous bị 401 trên API riêng tư, USER thiếu role bị 403 ở diagnostics, còn header role giả không chứng minh danh tính.

### 8.2. LocalDisabledTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "app.diagnostics.enabled=false")
@ActiveProfiles("local")
class LocalDisabledTests {

    @Autowired
    ApplicationContext context;

    @Test
    void diagnosticsBeanIsAbsentWhenFlagIsFalse() {
        assertThat(
            context.getBeanNamesForType(LocalDiagnosticsController.class)
        ).isEmpty();
    }
}
~~~

Test dùng property ưu tiên cao hơn file application-local.yml để buộc false. **@Profile local vẫn đúng**, nhưng @ConditionalOnProperty từ chối đăng ký Controller. Đây là lý do hai điều kiện phải được kiểm thử riêng, không suy luận chỉ từ tên profile.

### 8.3. ProductionProfileTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "app.diagnostics.enabled=true")
@AutoConfigureMockMvc
@ActiveProfiles("prod")
class ProductionProfileTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    MockMvc mvc;

    @Test
    void diagnosticsControllerAbsentDespiteFlagOverride() {
        assertThat(
            context.getBeanNamesForType(LocalDiagnosticsController.class)
        ).isEmpty();
    }

    @Test
    void localDemoCredentialsCannotAuthenticate() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "demo-learner")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicPingRemainsExplicitlyPublic() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk());
    }
}
~~~

**Ý nghĩa:** property true có thể override file prod, nhưng không biến @Profile local & !prod thành true. Tài khoản demo cũng không được nạp vào production, nên không có đường dùng mật khẩu local để truy cập dữ liệu riêng tư.

### 8.4. MixedProfilesTests.java

~~~java
package com.example.envdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "app.diagnostics.enabled=true")
@ActiveProfiles({"local", "prod"})
class MixedProfilesTests {

    @Autowired
    ApplicationContext context;

    @Test
    void localOnlyControllerIsAbsentWhenProdAlsoActive() {
        assertThat(
            context.getBeanNamesForType(LocalDiagnosticsController.class)
        ).isEmpty();
    }
}
~~~

Test này **không thay thế** một deployment policy từ chối profile kết hợp sai. Nó chỉ chứng minh tính năng local bị ẩn khi prod cũng đang active.

### 8.5. Chạy test

~~~bash
mvn test
~~~

**Kỳ vọng:** tất cả test thành công với dự án và dependency đã khai báo. Không cố định thời gian chạy hoặc số dòng output Maven; chúng phụ thuộc máy, cache và phiên bản plugin. Nếu một test thất bại, xem active profiles, property override và nguyên nhân trước khi sửa cấu hình.

Kiểm thử MockMvc xác minh Spring Security/MVC trong ApplicationContext. Nó **chưa thay thế** kiểm thử HTTP thực qua ingress/gateway, TLS, reverse proxy, actuator trên cổng riêng hoặc identity provider production.

## 9. Ma trận rủi ro cấu hình môi trường cần kiểm tra

| Tình huống sai sót | Hậu quả có thể xảy ra | Kiểm soát cần có | Bằng chứng kiểm thử |
| --- | --- | --- | --- |
| Không set SPRING_PROFILES_ACTIVE | App chạy với profile default ngoài dự định. | Mặc định an toàn; không có demo identity hoặc debug bean ở default; kiểm deployment. | Startup test không có local; xác minh không có bean nhạy cảm. |
| Bật nhầm local trong production | Dev endpoints/users được tạo. | Kết hợp profile guard với policy deploy; chỉ cấp role hợp lệ; network restriction. | Test local+prod, review manifest, check actual active profiles. |
| Bật diagnostics flag ở prod | Tính năng thử nghiệm xuất hiện. | @Profile local & !prod AND flag; role OPS độc lập. | ProductionProfileTests với flag=true. |
| Đưa anyRequest().permitAll() vào local SecurityFilterChain | Mọi endpoint có thể công khai khi local bị bật sai. | Một policy chung, explicit permitAll cho URL công khai, denyAll fallback. | Negative tests cho /api/me, /internal và đường lạ. |
| Chỉ có SecurityFilterChain giới hạn /api/** | URL /admin hoặc /actuator có thể ngoài mọi chain. | Fallback chain hoặc một chain không có securityMatcher hẹp. | Test route ngoài /api, inspect filter chain theo runtime. |
| Thêm endpoint mới mà không thêm policy | Endpoint mới truy cập được ngoài dự định. | anyRequest().denyAll(), review matcher và test. | Test /api/not-listed với principal có quyền. |
| Đổi default role hoặc authority mapping | Cấp quyền quá rộng hoặc từ chối nhầm. | Chuẩn hóa role prefix, scope mapping, test nhiều danh tính. | Test USER 403, OPS 200; verify issuer/audience khi dùng JWT. |
| Bật management endpoints qua config | Lộ env/heapdump/loggers hoặc metrics nhạy cảm. | Exposure allowlist, chain/security network và management port policy. | Thử từ mạng không được phép; inspect actuator policy. |
| CORS wildcard + credentials | Origin không mong muốn đọc dữ liệu trong browser. | Allowlist origin cụ thể; tránh wildcard cho credentialed request. | Browser preflight/credential test theo môi trường. |
| Tắt CSRF khi đổi môi trường | Browser gửi request có cookie gây side effects ngoài ý muốn. | Duy trì CSRF theo mô hình credential; thay đổi qua threat model/review. | Test POST thiếu token bị chặn nếu CSRF áp dụng. |
| Secret lấy từ env bị log ra | Rò client secret/password/token. | Secret store, redaction và log policy. | Kiểm log/tracing trước khi phát hành. |
| Proxy rewrite path hoặc forwarded headers | Matcher trong app nhận path khác; IP/host có thể bị giả. | Kiểm trusted proxy, base path, network policy. | End-to-end test qua ingress thực. |

**Khi phát hiện cấu hình khác dự kiến, không vội sửa bằng permitAll() hoặc disable CSRF.** Xác định đúng filter chain, matcher, principal, rule, profile, property source và lớp hạ tầng đang tạo khác biệt.

## 10. Actuator và cổng quản trị: ngoài Controller cũng có bề mặt tấn công

Nếu thêm Spring Boot Actuator, quyền tiếp cận các endpoint như health, info, metrics, loggers, env, heapdump có ý nghĩa khác nhau. **Không dùng management.endpoints.web.exposure.include=* chỉ để tiện xem production**.

Những điểm phải xét:

- Endpoint nào **được tạo và expose** qua web thực sự? Một số endpoint có thể bị vô hiệu hóa hoặc không được expose dù có bean.
- Có **management.server.port** riêng không? Nếu khác cổng ứng dụng, cần xác định chính sách bảo mật nào áp dụng cho management context.
- Có custom SecurityFilterChain không? Khi khai báo chain tùy chỉnh, cấu hình bảo mật Actuator mặc định của Boot có thể **nhường quyền kiểm soát** cho ứng dụng; không giả định Boot tiếp tục bảo vệ mọi actuator thay cho mình.
- Security matcher /api/** không tự bảo vệ /actuator/**.
- Health công khai có thể hợp lý cho load balancer, nhưng cần giới hạn mức chi tiết. Không trả full exception, database URL hoặc thông tin cluster vào phản hồi công khai.
- Ngoài Spring Security, nên dùng network policy, ingress allowlist, quyền vận hành và audit.

Nếu cần bảo vệ Actuator theo role, kiểm tra **EndpointRequest** hoặc các matcher phù hợp cho đúng phiên bản Boot, thiết kế fallback chain, đồng thời test status qua **đường mạng thực tế**. Không đưa một cấu hình Actuator giả định vào demo chưa khai báo dependency actuator rồi tuyên bố đã bảo vệ chúng.

## 11. Secrets, external config và tính nhất quán vận hành

### 11.1. Secrets khác feature flags

Property app.diagnostics.enabled là boolean không nhạy cảm. Ngược lại các giá trị như DB_PASSWORD, OAuth client secret, private key và token ký phải được quản lý qua **secret store** hoặc một cơ chế triển khai kiểm soát được quyền truy cập.

Không ghi secret thật vào application-local.yml hoặc application-prod.yml trong git. Không dump toàn bộ Environment chỉ vì muốn biết flag cuối cùng, không bật log request header Authorization và không đưa credential qua query parameter.

Với production, thường cần:

- Danh tính workload/service account có quyền đọc đúng nhóm secret.
- TLS đến các dịch vụ phụ thuộc; xác minh chứng chỉ/mTLS khi thiết kế yêu cầu.
- Chính sách rotate secret và xử lý hết hạn/revocation.
- Không dùng tài khoản admin chung giữa local và production.
- Ranh giới quyền giữa người vận hành, ứng dụng và CI/CD; không để pipeline test có quyền production quá mức.

### 11.2. Override qua environment variables

Spring Boot có relaxed binding cho nhiều property. Ví dụ một runtime có thể dùng **APP_DIAGNOSTICS_ENABLED=true** để đại diện property app.diagnostics.enabled, hoặc **SPRING_PROFILES_ACTIVE=prod** để chọn profile.

Cách đặt tùy hệ điều hành:

~~~powershell
# Ví dụ PowerShell cho một tiến trình lab local.
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_DIAGNOSTICS_ENABLED = "true"
java -jar target/security-env-demo-1.0.0.jar
~~~

~~~bash
# Ví dụ shell Unix cho một lần chạy local.
SPRING_PROFILES_ACTIVE=local APP_DIAGNOSTICS_ENABLED=true \
  java -jar target/security-env-demo-1.0.0.jar
~~~

Các lệnh là minh họa với cờ không nhạy cảm. Khi chạy production, xác minh giá trị thực tế đến từ Helm/Kubernetes manifest, Docker, systemd, runtime environment và command-line; không chỉ nhìn source.

### 11.3. Đừng khóa security policy vào profile name

Cách tổ chức an toàn hơn:

- **Các rule quyền** sống trong SecurityFilterChain hoặc method security, được review như code nghiệp vụ.
- **Profile** chọn adapter hoặc thành phần được phép tồn tại; mọi bean nhạy cảm có điều kiện rõ và mặc định tắt.
- **Flag** chọn nhánh chức năng, được dùng để bật tính năng trong một tập môi trường đã cho phép, không tự cấp quyền.
- **Identity provider** phụ thuộc môi trường có thể đổi issuer, client ID, key material và endpoint; server vẫn xác minh issuer/audience/expiry, scope và quyền đối tượng.
- **Deployment gate** kiểm profile, cấu hình thiếu/hỏng, exposure, role và thử nghiệm phủ định trước khi mở lưu lượng.

Dùng cùng một artifact không đảm bảo hành vi giống nhau: cấu hình ngoài JAR, proxy và secrets có thể thay đổi quyết định runtime. Tất cả cần được kiểm định theo release.

## 12. Khi nào nên để ứng dụng không khởi động?

Có những lỗi nên **fail fast** thay vì chạy trong trạng thái không an toàn:

- Production thiếu issuer/JWK tin cậy hoặc credential nguồn danh tính hợp lệ.
- Cấu hình đánh dấu chế độ cho phép bỏ authentication trên đường nhạy cảm.
- Secret ký token bị thiếu hoặc thuộc giá trị demo.
- Profile production đi cùng local mà chính sách tổ chức cấm.
- SecurityFilterChain mong đợi không có hoặc gateway route quản trị không được bảo vệ.
- Cấu hình yêu cầu một trusted proxy hoặc TLS nhưng deployment không đáp ứng.

Các kiểm soát này nên được thực thi **trước khi mở lưu lượng** bằng validation của ứng dụng, deployment admission check, config validation hoặc startup readiness gate thích hợp. Đừng chỉ đưa cảnh báo vào log rồi tiếp tục phục vụ request nếu thiếu cấu hình bảo mật tối thiểu.

Trong bài lab, chúng ta dùng **kho user rỗng ngoài local** nên protected endpoint trả 401, để người học quan sát fail-closed. Đó **không phải** một bản prod hoạt động đầy đủ; khi đưa tính năng production vào, thay bằng nguồn danh tính thật và đảm bảo ứng dụng fail startup nếu cấu hình nguồn danh tính bắt buộc không hợp lệ.

**Không nên ép lỗi khởi động theo cách có thể để server mở port công khai trong một khoảng ngắn rồi mới dừng.** Nếu cần startup validation, chọn điểm kiểm tra đủ sớm trong lifecycle và kết hợp readiness/network gating.

## 13. Quy trình kiểm thử an toàn trước khi phát hành

Một quy trình thực dụng:

1. **Kiểm kê route và method** từ Controller, OpenAPI, gateway, message listener và management endpoints; đánh dấu public/authenticated/admin/object-level.
2. **Định nghĩa chính sách chung** trong code; chỉ public những URL có lý do nghiệp vụ; dùng denyAll fallback khi phù hợp.
3. **Liệt kê profile và property hợp lệ** cho local, test, staging, prod. Quy định các kết hợp profile bị cấm.
4. **Tách local-only feature** thành bean @Profile + @ConditionalOnProperty, vẫn giữ role/authority và giới hạn mạng.
5. **Cấu hình xác thực theo môi trường** qua provider/issuer/secrets được quản lý; không chuyển mật khẩu demo sang prod.
6. **Viết test phủ định theo ma trận**: anonymous, role thấp, credential sai, flag on/off, local/prod/mixed, method chưa khai báo và quyền theo object/tenant.
7. **Build và kiểm thử cùng artifact dự định triển khai**, sau đó kiểm actual config và proxy/ingress của từng môi trường.
8. **Kiểm tra log, cache, CORS/CSRF và Actuator**; giới hạn secret/debug data, quan sát đường đi request thật.
9. **Ràng buộc CD**: nếu profile hoặc config bảo mật sai, không cho deploy hoặc không cho bản build nhận traffic.
10. **Giám sát và rà lại** khi thêm route, đổi auth mechanism, thay secrets/issuer, cập nhật proxy hoặc mở cổng quản trị.

Có thể lưu một bảng quyền trong repo để review:

| Resource | Local | Staging | Prod | Policy thống nhất |
| --- | --- | --- | --- | --- |
| GET /api/ping | 200 anonymous | 200 anonymous | 200 anonymous | Public có chủ đích. |
| GET /api/me | Auth required | Auth required | Auth required | Không mở rộng quyền bằng flag. |
| GET /internal/diagnostics | Có thể tồn tại nếu flag=true, cần OPS | Bean không tồn tại | Bean không tồn tại | Có profile guard, property guard và role guard. |
| GET/POST route chưa khai báo | Deny | Deny | Deny | Fail closed theo rule. |
| Actuator nhạy cảm nếu có | Bảo vệ theo nhiệm vụ | Giới hạn và phân quyền | Giới hạn và phân quyền | Exposure riêng, network và audit. |

Đừng ghi “prod 404” thành bằng chứng duy nhất cho diagnostics: code có thể vẫn có route nhưng filter trả 403/404 tùy policy. **Test trực tiếp bean và kiểm response/side effect** mới chứng minh tính năng không khả dụng.

## 14. Câu hỏi tự kiểm tra

1. Vì sao đặt app.diagnostics.enabled=false trong application-prod.yml **không đủ** nếu command-line có thể override nó?
2. @Profile("!prod") có thể hoạt động khi không set profile nào không? Tại sao local & !prod chặt hơn cho endpoint chỉ dùng ở local?
3. Một SecurityFilterChain chỉ có securityMatcher("/api/**") và không có fallback sẽ có rủi ro gì với /admin hoặc /actuator?
4. Vì sao requestMatchers("/internal/**").permitAll() phụ thuộc flag là một thiết kế nguy hiểm?
5. Trong demo, vì sao cùng user learner được 200 tại /api/me nhưng 403 tại /internal/diagnostics?
6. Vì sao các tài khoản demo chỉ nên tạo khi profile local & !prod, và vì sao prod phải có identity provider thật?
7. Khi bạn thấy 403 ở POST, làm sao phân biệt lỗi CSRF với denyAll authorization?
8. Nếu cả local và prod cùng active, property cuối có thể là true. Hàng rào nào vẫn ngăn bean diagnostics? Chính sách deploy còn cần làm gì?
9. Vì sao việc trả 404 cho một endpoint không đủ để chứng minh Controller đã bị loại khỏi ApplicationContext?
10. Khi dùng JWT Resource Server, những thông số nào cần thay theo môi trường và điều gì phải giữ nguyên về kiểm tra scope, audience và quyền đối tượng?

### Checklist ghi nhớ

- **Không biến tên profile hoặc feature flag thành công tắc permitAll toàn ứng dụng.**
- **SecurityFilterChain bao phủ toàn bộ** request hoặc có chain fallback rõ ràng khi dùng nhiều chain.
- **permitAll có chủ đích, authenticated/hasRole rõ ràng, denyAll fallback** là những điểm xuất phát có thể kiểm chứng.
- **Local-only bean** nên có điều kiện cả profile và property, mặc định tắt, không lộ secret.
- **Tài khoản demo chỉ ở local**; production dùng nguồn danh tính được phê duyệt.
- **Kiểm thử mỗi tổ hợp profile và flag** bằng context + HTTP status + quyền thực tế, kể cả cấu hình sai.
- **Externalized config có thể override YAML**; xác minh giá trị runtime và không in secret.
- **Proxy, Actuator, CORS, CSRF và quyền theo dữ liệu** vẫn cần chính sách riêng.
- **CI/CD và readiness** không cho một bản cấu hình bảo mật sai nhận traffic.

## Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): permitAll, hasRole, denyAll, thứ tự matcher.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): securityMatcher, nhiều SecurityFilterChain và fallback.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): kích hoạt profile và cấu hình theo profile.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): thứ tự property source và profile-specific files.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): biểu thức profile với &, ! và |.
- [Spring Boot — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue và matchIfMissing.

**Phiên bản:** Mã thực hành nhắm tới Spring Boot 3.3.6/Spring Security 6.x để giữ ví dụ thống nhất. Với dự án đang dùng phiên bản mới hơn, hãy tra API và hành vi cấu hình trong tài liệu tương ứng, cập nhật bản vá, đồng thời chạy lại ma trận test trên đúng dependency đã chọn.

## Kết luận

Đặt cấu hình theo môi trường an toàn không chỉ là tạo application-local.yml và application-prod.yml. Cần giữ **chính sách phân quyền cốt lõi ổn định**, bảo vệ toàn bộ request bằng SecurityFilterChain, chỉ bật chức năng local khi profile/flag thích hợp và vẫn xác minh role khi gọi, sử dụng nguồn danh tính đáng tin cho mỗi môi trường và mặc định từ chối khi cấu hình còn thiếu. Quan trọng nhất, hãy **kiểm thử các tổ hợp cấu hình sai có thể xảy ra**, đối chiếu runtime/deployment với mã nguồn và ngăn bản phát hành không đạt yêu cầu bảo mật nhận lưu lượng.
