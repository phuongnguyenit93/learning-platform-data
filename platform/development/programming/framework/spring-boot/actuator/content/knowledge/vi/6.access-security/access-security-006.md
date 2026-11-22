# Thiết kế quyền truy cập tối thiểu cho người vận hành và hệ thống giám sát

## 1. Bắt đầu từ công việc cần làm

Actuator cung cấp các điểm truy cập để quan sát và quản lý ứng dụng Spring Boot. Người vận hành cần tìm nguyên nhân sự cố; hệ thống giám sát cần thu thập tín hiệu đều đặn. Hai nhu cầu này khác nhau, nên chúng cần các quyền khác nhau.

**Quyền truy cập tối thiểu (least privilege)** nghĩa là mỗi danh tính chỉ được thực hiện những thao tác cần cho công việc, trên đúng dữ liệu, trong đúng môi trường và khoảng thời gian cần thiết.

Ví dụ, một tiến trình Prometheus cần lấy số liệu JVM mỗi 15 giây. Nếu cấp cho nó tài khoản quản trị Actuator, khi thông tin xác thực bị lộ, hậu quả có thể vượt xa việc đọc số liệu. Ngược lại, một người trực vận hành có thể cần xem trạng thái thành phần và cấu hình mức log, nhưng không mặc nhiên cần đổi mức log hay tải toàn bộ bộ nhớ.

Lộ trình của bài:

1. Chuyển nhu cầu thành ma trận danh tính – endpoint – phương thức HTTP – mức dữ liệu.
2. Tách việc bật endpoint, đưa endpoint ra HTTP và cấp quyền.
3. Dựng ví dụ có quyền riêng cho giám sát, vận hành và ứng dụng.
4. Kiểm tra cả truy cập được phép lẫn truy cập phải bị từ chối.
5. Mở rộng có kiểm soát khi đưa vào môi trường thật.

Ví dụ dùng **Java 21, Spring Boot 3.3.13, Spring MVC và Spring Security 6 do Spring Boot quản lý phiên bản**. Đây là phiên bản cố định cho bài thực hành thuộc dòng 3.3.x; không hàm ý nó là phiên bản mới nhất hay khuyến nghị triển khai sản xuất hiện tại. Cấu hình Servlet dưới đây không dùng nguyên xi cho WebFlux.

## 2. Đọc dữ liệu cũng là một đặc quyền

Đừng chỉ hỏi “ai được vào Actuator?”. Hãy hỏi bốn câu cụ thể:

- Danh tính đó là người nào hoặc tiến trình nào?
- Nó cần endpoint nào?
- Nó được dùng phương thức HTTP nào?
- Nó cần nhìn thấy dữ liệu chi tiết đến đâu?

Một thao tác không thay đổi trạng thái vẫn có thể làm lộ cấu trúc hệ thống hoặc tiêu tốn tài nguyên:

| Nhu cầu | Quyền phù hợp để xem xét | Phần không nên cấp kèm theo |
| --- | --- | --- |
| Thu thập số liệu định kỳ | Đọc endpoint Prometheus | Đọc toàn bộ cấu hình hoặc thay đổi mức log |
| Kiểm tra khả năng phục vụ | Đọc trạng thái health cần thiết | Xem mọi tên thành phần, đường dẫn và lỗi nội bộ |
| Chẩn đoán một sự cố | Đọc metrics, trạng thái thành phần, cấu hình log phù hợp | Quyền quản trị thường trực trên mọi endpoint |
| Thu thập dữ liệu chuyên sâu | Quyền riêng, được phê duyệt và có thời hạn | Tự động gộp vào quyền “chỉ đọc” thông thường |

Chẳng hạn, heap dump có thể chứa dữ liệu nghiệp vụ và thông tin xác thực trong bộ nhớ. Vì vậy, “chỉ cho GET” vẫn chưa đủ để gọi là tối thiểu: phải chọn cả tài nguyên được đọc. Số liệu giám sát cũng cần được rà soát để tránh đưa mã khách hàng, địa chỉ thư điện tử hoặc bí mật vào nhãn số liệu.

## 3. Ma trận quyền trước khi viết cấu hình

Trong bài thực hành, ta tự thiết kế chính sách sau. Đây là một phương án cho tình huống cụ thể, không phải bộ vai trò mặc định của Spring Boot.

| Yêu cầu | Chưa xác thực | Tài khoản giám sát `monitor` | Tài khoản vận hành `ops` | Tài khoản ứng dụng `app` |
| --- | --- | --- | --- | --- |
| GET `/actuator/health` | Từ chối | Trạng thái tổng hợp | Trạng thái và thành phần/chi tiết được cấu hình | Từ chối |
| GET `/actuator/prometheus` | Từ chối | Cho phép | Từ chối | Từ chối |
| GET `/actuator/metrics` và đường dẫn con | Từ chối | Từ chối | Cho phép | Từ chối |
| GET `/actuator/loggers` và đường dẫn con | Từ chối | Từ chối | Cho phép | Từ chối |
| POST `/actuator/loggers/{name}` | Từ chối | Từ chối | Từ chối | Từ chối |
| GET `/api/ping` | Từ chối | Từ chối | Từ chối | Cho phép |
| Các endpoint còn lại | Từ chối | Từ chối | Từ chối | Từ chối |

Ở hàng `GET /api/ping`, chỉ tài khoản `app` được phép truy cập. Đây là API nhỏ của ví dụ để chứng minh quyền ứng dụng tách biệt quyền quản lý.

Danh sách quyền thực tế:

| Danh tính | Các quyền được cấp |
| --- | --- |
| `monitor` | `ROLE_MONITOR`, `actuator:prometheus:read` |
| `ops` | `ROLE_OPS`, `actuator:metrics:read`, `actuator:loggers:read` |
| `app` | `ROLE_APP_USER` |

`ops` không tự động kế thừa quyền của `monitor`. Nếu công việc của một người cần cả hai, việc cấp thêm phải xuất phát từ nhu cầu rõ ràng. Cũng không có vai trò “quản trị tất cả” trong ví dụ.

Quyền xem chi tiết health được kiểm soát riêng: được gọi endpoint chưa đồng nghĩa được xem mọi trường trong phản hồi.

## 4. Ba lớp phải phân biệt

### 4.1. Bật endpoint, đưa ra HTTP và cấp quyền

Có ba quyết định độc lập:

1. **Bật (enable):** endpoint có được kích hoạt trong ứng dụng không?
2. **Đưa ra kênh truy cập (expose):** endpoint có được công bố qua HTTP hoặc JMX không?
3. **Cấp quyền (authorize):** yêu cầu đã đến endpoint có được thực hiện không?

Trong dòng Spring Boot 3.3, dùng `management.endpoints.enabled-by-default`, `management.endpoint.<id>.enabled` và `management.endpoints.web.exposure.include` cho hai lớp đầu. Các thuộc tính này không thay thế quy tắc Spring Security. Khi tự khai báo `SecurityFilterChain`, ta chịu trách nhiệm cấu hình bảo mật theo chính sách của mình. [Tài liệu Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Ví dụ sẽ chọn rõ bốn endpoint thay vì đưa tất cả ra HTTP. Ngoài danh sách đó, ta cũng mặc định từ chối ở lớp phân quyền. Nhờ vậy, một lần bổ sung endpoint sau này không vô tình cấp luôn quyền sử dụng.

### 4.2. Ranh giới mạng và danh tính

Luồng kiểm soát có thể hình dung như sau:

```text
Nguồn kết nối được phép
    -> Kênh truyền được bảo vệ
    -> Xác thực danh tính
    -> Chọn chuỗi bảo mật
    -> Kiểm tra endpoint + phương thức + quyền
    -> Lọc mức chi tiết dữ liệu
    -> Trả phản hồi và ghi dấu vết phù hợp
```

Mạng nội bộ làm giảm phạm vi tiếp cận, nhưng một tiến trình trong mạng đó vẫn có thể bị xâm nhập. Vì vậy, hạn chế mạng và phân quyền theo danh tính bổ sung cho nhau.

Tách cổng quản lý là một lựa chọn triển khai; đổi cổng không tự xác thực người gọi. Spring Boot cho phép cổng và địa chỉ quản lý riêng; `management.server.address` chỉ đặt địa chỉ riêng khi cổng quản lý khác cổng ứng dụng. [Cấu hình HTTP quản lý 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-port).

### 4.3. Danh tính của máy và danh tính của người

- Máy giám sát dùng tài khoản dịch vụ riêng, gắn với công việc thu thập số liệu.
- Người vận hành trong môi trường thật dùng danh tính cá nhân để có thể truy vết và thu hồi từng người.
- Không dùng chung tài khoản quản trị cho máy giám sát, nhóm trực và API nghiệp vụ.
- Tách thông tin xác thực giữa phát triển, thử nghiệm và sản xuất.
- Quyền can thiệp khẩn cấp cần thời hạn và cơ chế thu hồi rõ ràng.

Hai tên `monitor` và `ops` trong ví dụ là cách mô phỏng dễ chạy trên máy cá nhân. Đặc biệt, `ops` ở đây không phải đề xuất tài khoản dùng chung cho cả đội trong sản xuất.

## 5. Dự án thực hành đầy đủ

Tạo một thư mục dự án riêng với cấu trúc:

```text
actuator-least-privilege/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/leastprivilege/
    │   │   ├── DemoApplication.java
    │   │   ├── PingController.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/com/example/leastprivilege/
        └── AccessPolicyTest.java
```

Đây là ứng dụng Spring Boot cần các thư viện phụ thuộc bên dưới; không chạy riêng các tệp Java bằng `javac TenTep.java`. Dùng Maven với JDK 21. Lần dựng đầu cần truy cập Maven Central.

### 5.1. Thư viện phụ thuộc: `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>actuator-least-privilege</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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

`micrometer-registry-prometheus` cung cấp bộ xuất số liệu cần cho endpoint Prometheus; chỉ ghi tên endpoint vào danh sách exposure không tạo được bộ xuất còn thiếu.

### 5.2. Giới hạn bề mặt quản lý: `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,prometheus,metrics,loggers
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: when-authorized
      show-components: when-authorized
      roles: OPS
    prometheus:
      enabled: true
    metrics:
      enabled: true
    loggers:
      enabled: true

demo:
  monitor-password: ${MONITOR_PASSWORD}
  ops-password: ${OPS_PASSWORD}
  app-password: ${APP_PASSWORD}
```

Cấu hình này chủ động bật và đưa ra HTTP bốn endpoint. Không có `env`, `configprops`, `heapdump`, `shutdown` trong chính sách.

Các biến môi trường chứa mật khẩu phải có trước khi chạy. Không đặt giá trị mặc định để ứng dụng vô tình khởi động với mật khẩu yếu. Địa chỉ `127.0.0.1` giới hạn bài thực hành trong máy cục bộ; máy giám sát ở máy khác hoặc container khác sẽ không truy cập được địa chỉ vòng lặp này.

`show-details` và `show-components` đều dùng `when-authorized`, với vai trò `OPS`. Vì vậy, `monitor` được gọi health nhưng không được xem cây thành phần. Cơ chế hiển thị này là một lớp riêng sau quyết định cho phép yêu cầu. [Quyền xem health trong Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Tắt discovery chỉ bỏ tài liệu liên kết ở đường dẫn gốc Actuator; nó không thay thế xác thực hay phân quyền. Tắt JMX và loại các endpoint khỏi exposure JMX giúp ví dụ không tạo thêm kênh quản lý ngoài HTTP. Cần kiểm tra riêng cơ chế JMX của thư viện bên thứ ba hoặc tùy chọn khởi chạy JVM. [Phạm vi cấu hình JMX của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 5.3. Điểm khởi động: `DemoApplication.java`

Đặt tệp tại `src/main/java/com/example/leastprivilege/DemoApplication.java`.

```java
package com.example.leastprivilege;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 5.4. API minh họa: `PingController.java`

Đặt tệp tại `src/main/java/com/example/leastprivilege/PingController.java`.

```java
package com.example.leastprivilege;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

### 5.5. Phân quyền: `SecurityConfig.java`

Đặt tệp tại `src/main/java/com/example/leastprivilege/SecurityConfig.java`.

```java
package com.example.leastprivilege;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    private static RequestMatcher getEndpoint(String id) {
        return new AndRequestMatcher(
                EndpointRequest.to(id),
                request -> HttpMethod.GET.matches(request.getMethod()));
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(getEndpoint("health"))
                    .hasAnyRole("MONITOR", "OPS")
                .requestMatchers(getEndpoint("prometheus"))
                    .hasAuthority("actuator:prometheus:read")
                .requestMatchers(getEndpoint("metrics"))
                    .hasAuthority("actuator:metrics:read")
                .requestMatchers(getEndpoint("loggers"))
                    .hasAuthority("actuator:loggers:read")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.logout(logout -> logout.disable());
        // Giữ CSRF mặc định; không có thao tác ghi nào được cấp quyền.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/ping")
                    .hasRole("APP_USER")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.logout(logout -> logout.disable());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.monitor-password}") String monitorPassword,
            @Value("${demo.ops-password}") String opsPassword,
            @Value("${demo.app-password}") String appPassword) {
        var monitor = User.withUsername("monitor")
                .password(encoder.encode(monitorPassword))
                .authorities("ROLE_MONITOR", "actuator:prometheus:read")
                .build();
        var ops = User.withUsername("ops")
                .password(encoder.encode(opsPassword))
                .authorities("ROLE_OPS", "actuator:metrics:read",
                        "actuator:loggers:read")
                .build();
        var app = User.withUsername("app")
                .password(encoder.encode(appPassword))
                .authorities("ROLE_APP_USER")
                .build();
        return new InMemoryUserDetailsManager(monitor, ops, app);
    }
}
```

### 5.6. Đọc cấu hình theo luồng yêu cầu

**Chọn chuỗi trước, chọn quy tắc sau.** Chuỗi `@Order(1)` chỉ nhận yêu cầu khớp các endpoint Actuator. Chuỗi `@Order(2)` không giới hạn `securityMatcher`, nên bao phủ các yêu cầu còn lại. Spring Security chọn chuỗi khớp đầu tiên; một yêu cầu đã vào chuỗi Actuator và bị từ chối sẽ không chạy tiếp sang chuỗi ứng dụng để xin quyền lần nữa. Cần có chuỗi bao phủ phần còn lại khi tự cấu hình nhiều chuỗi. [Cơ chế nhiều chuỗi bảo mật](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances).

**Ghép điều kiện bằng AND.** Hàm `getEndpoint("loggers")` yêu cầu vừa khớp vị trí endpoint loggers, vừa là phương thức GET. Sau đó quy tắc kiểm tra `actuator:loggers:read`. Vì vậy, cùng tài khoản `ops` đọc được mức log nhưng không đổi được mức log.

`EndpointRequest` dựa trên vị trí endpoint do Actuator quản lý, giúp giảm phụ thuộc vào chuỗi đường dẫn viết tay khi đổi tiền tố. `toAnyEndpoint()` cũng bao gồm endpoint liên kết nếu discovery đang bật. [API EndpointRequest 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

**Mặc định từ chối.** Không có dòng “đã đăng nhập thì được xem tất cả Actuator”. Một endpoint được bật thêm sau này vẫn cần quy tắc cho phép tương ứng. Quy tắc theo thứ tự sử dụng kết quả khớp đầu tiên, nên các quyền cụ thể đứng trước `anyRequest().denyAll()`. [Quy tắc cấp quyền của Spring Security 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/docs/modules/ROOT/pages/servlet/authorization/authorize-http-requests.adoc).

**Vai trò và quyền chi tiết không có cùng cú pháp.** `hasRole("OPS")` kiểm tra quyền `ROLE_OPS` theo quy ước tiền tố mặc định. `hasAuthority("actuator:metrics:read")` kiểm tra đúng chuỗi quyền đã khai báo. Không dùng `hasRole("ROLE_OPS")` hoặc tự giả định một vai trò có mọi quyền chi tiết.

**Chỉ mở phương thức thực sự cần.** Ví dụ cố ý chỉ cấp GET, không tự cấp HEAD, OPTIONS hay POST. Nếu công cụ thật dùng HEAD, hãy đưa nhu cầu đó vào ma trận và kiểm thử riêng. Thêm quyền theo công việc cụ thể, tránh mở mọi phương thức cho thuận tiện.

**Giữ bảo vệ CSRF.** Không có thao tác ghi được phép nên ví dụ giữ cấu hình CSRF mặc định. Mã 403 của một POST thiếu token có thể xuất phát từ CSRF trước khi kiểm tra quyền. Bài kiểm thử bên dưới thêm token hợp lệ để chứng minh thao tác đổi mức log vẫn bị từ chối ở lớp phân quyền. HTTP Basic và lựa chọn không lưu phiên đăng nhập không đủ để tự kết luận rằng trình duyệt không thể gây rủi ro CSRF. [Cơ chế bảo vệ CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

`InMemoryUserDetailsManager` và BCrypt giúp bài thực hành tự chạy, nhưng không tạo cơ chế quản lý vòng đời danh tính hoàn chỉnh. Khi đổi mật khẩu môi trường trong ví dụ, cần khởi động lại để tạo lại tài khoản trong bộ nhớ.

## 6. Chạy và quan sát từ phía người gọi

### 6.1. Khởi động trên máy cá nhân

Ở thư mục chứa `pom.xml`, dùng PowerShell với `JAVA_HOME` trỏ đến JDK 21:

```powershell
$env:MONITOR_PASSWORD = 'monitor-local-demo-only'
$env:OPS_PASSWORD = 'ops-local-demo-only'
$env:APP_PASSWORD = 'app-local-demo-only'
mvn spring-boot:run
```

Ba chuỗi trên chỉ là mật khẩu công khai của bài thực hành cục bộ. Với môi trường thật, lấy thông tin xác thực từ hệ thống quản lý bí mật; không sao chép các giá trị này vào máy chủ hay lưu thông tin xác thực thật trong mã nguồn.

Ứng dụng lắng nghe tại `http://127.0.0.1:8080`. HTTP Basic trong bài chỉ dùng trên địa chỉ vòng lặp cục bộ. Khi truyền thông tin xác thực qua mạng, dùng HTTPS và kiểm tra chứng chỉ; mã hóa Base64 của Basic không cung cấp tính bí mật.

### 6.2. Kiểm tra mã phản hồi

Mở terminal PowerShell thứ hai. Dùng `curl.exe` để tránh nhầm với bí danh `curl` của một số bản PowerShell. Các lệnh dưới in mã HTTP, không in toàn bộ nội dung:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}\n" -u monitor:monitor-local-demo-only http://127.0.0.1:8080/actuator/prometheus
curl.exe -s -o NUL -w "%{http_code}\n" -u monitor:monitor-local-demo-only http://127.0.0.1:8080/actuator/metrics
curl.exe -s -o NUL -w "%{http_code}\n" -u ops:ops-local-demo-only http://127.0.0.1:8080/actuator/metrics
curl.exe -s -o NUL -w "%{http_code}\n" -u ops:ops-local-demo-only http://127.0.0.1:8080/actuator/prometheus
curl.exe -s -o NUL -w "%{http_code}\n" -u app:app-local-demo-only http://127.0.0.1:8080/api/ping
curl.exe -s -o NUL -w "%{http_code}\n" -u app:app-local-demo-only http://127.0.0.1:8080/actuator/health
```

Kết quả tương ứng khi ứng dụng đã khởi động bình thường:

```text
401
200
403
200
403
200
403
```

Các lệnh chứa mật khẩu minh họa để tiện tái hiện. Khi thao tác với thông tin xác thực thật, tránh đưa chúng vào lịch sử shell hoặc danh sách tham số tiến trình; có thể để `curl.exe -u tennguoidung` hỏi mật khẩu tương tác.

### 6.3. Kiểm tra dữ liệu được nhìn thấy

```powershell
curl.exe -s -u monitor:monitor-local-demo-only http://127.0.0.1:8080/actuator/health
curl.exe -s -u ops:ops-local-demo-only http://127.0.0.1:8080/actuator/health
```

Khi health đang UP, phản hồi cho `monitor` là:

```json
{"status":"UP"}
```

Phản hồi cho `ops` có thêm `components` và các chi tiết mà những thành phần sức khỏe cung cấp. Không cố định toàn bộ JSON này: tên thành phần, dung lượng đĩa, đường dẫn và số liệu phụ thuộc môi trường.

Nếu một thành phần chuyển sang DOWN, trạng thái tổng hợp và mã HTTP health có thể thay đổi; đó là kết quả kiểm tra sức khỏe, không tự động là lỗi xác thực.

Phân biệt khi chẩn đoán:

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| 401 | Thiếu hoặc sai thông tin xác thực trong chính sách Basic của ví dụ |
| 403 trên GET | Đã xác thực nhưng thiếu quyền phù hợp |
| 403 trên POST | Có thể do CSRF hoặc phân quyền; phải tách hai nguyên nhân |
| Không kết nối được | Tiến trình, địa chỉ, cổng, tường lửa, tuyến mạng hoặc TLS |
| Endpoint không dùng được dù có quyền | Thư viện phụ thuộc, trạng thái bật, kênh công bố, đường dẫn và điều kiện tạo endpoint |
| Health báo DOWN/503 | Tình trạng thành phần và chính sách ánh xạ trạng thái health |

Không suy ra “endpoint bị tắt luôn trả 404”. Trong ví dụ, tài khoản đã xác thực gọi `/actuator/env` rơi vào chuỗi còn lại và bị `denyAll()` chặn trước khi đến bộ xử lý HTTP. Vì thế phản hồi 403 vẫn phù hợp với thiết kế.


## 7. Kiểm chứng chính sách bằng kiểm thử tự động

Đặt tệp sau tại `src/test/java/com/example/leastprivilege/AccessPolicyTest.java`.

Các kiểm thử gọi qua Spring Security bằng HTTP Basic, thay vì chỉ gắn tên người dùng giả vào yêu cầu. `@AutoConfigureObservability` bật phần quan sát cần thiết trong môi trường kiểm thử để endpoint Prometheus có thể được tạo.

Bộ kiểm thử chủ động bật thêm `info` **chỉ trong ngữ cảnh test**, xác nhận endpoint thực sự tồn tại rồi kiểm tra nó vẫn bị từ chối. Nhờ đó, kết quả không thể chỉ “đúng” vì endpoint chưa được tạo.

```java
package com.example.leastprivilege;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.web.WebEndpointsSupplier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "demo.monitor-password=monitor-test-password",
        "demo.ops-password=ops-test-password",
        "demo.app-password=app-test-password",
        "management.endpoint.info.enabled=true",
        "management.endpoints.web.exposure.include=health,prometheus,metrics,loggers,info"
})
@AutoConfigureMockMvc
@AutoConfigureObservability
class AccessPolicyTest {
    @Autowired MockMvc mvc;
    @Autowired WebEndpointsSupplier endpoints;

    @Test
    void healthDetailsDependOnRole() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("monitor", "monitor-test-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.components").exists());
    }

    @Test
    void prometheusIsReservedForMonitor() throws Exception {
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("monitor", "monitor-test-password")))
                .andExpect(status().isOk());
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("app", "app-test-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void diagnosticsAreReservedForOps() throws Exception {
        for (String path : new String[]{"/actuator/metrics", "/actuator/loggers"}) {
            mvc.perform(get(path)
                            .with(httpBasic("ops", "ops-test-password")))
                    .andExpect(status().isOk());
            mvc.perform(get(path)
                            .with(httpBasic("monitor", "monitor-test-password")))
                    .andExpect(status().isForbidden());
        }
    }

    @Test
    void loggerWriteIsDeniedEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/actuator/loggers/ROOT")
                        .with(httpBasic("ops", "ops-test-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"configuredLevel\":\"DEBUG\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void applicationAuthorityIsSeparate() throws Exception {
        mvc.perform(get("/api/ping")
                        .with(httpBasic("app", "app-test-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
        mvc.perform(get("/api/ping")
                        .with(httpBasic("monitor", "monitor-test-password")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/ping")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void newlyExposedEndpointStillHasNoPermission() throws Exception {
        assertThat(endpoints.getEndpoints())
                .extracting(endpoint -> endpoint.getEndpointId().toString())
                .contains("info");
        mvc.perform(get("/actuator/info")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCredentialsAndUnexposedPathAreDenied() throws Exception {
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("monitor", "wrong-password")))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/env")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```powershell
mvn test
```

Kiểm thử đã cung cấp các mật khẩu riêng qua thuộc tính test, nên lệnh này không cần ba biến môi trường của phiên chạy ứng dụng. Đây là thông tin giả dành riêng cho kiểm thử.

Phần kết quả cần quan sát khi thành công:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Maven còn in thông tin khởi động và thời gian chạy; không coi toàn bộ log là chuỗi cố định. Mục tiêu là chính sách hoạt động đúng, không phải việc xuất hiện một dòng log cụ thể.

Các bằng chứng cần đọc từ bộ kiểm thử:

- Chưa xác thực không được đọc health.
- Giám sát và vận hành nhìn thấy health ở mức chi tiết khác nhau.
- Giám sát đọc được Prometheus nhưng không đọc chẩn đoán.
- Vận hành đọc được chẩn đoán nhưng không tự có quyền Prometheus.
- POST thay đổi mức log vẫn bị từ chối khi CSRF token hợp lệ.
- Quyền ứng dụng không được suy ra từ quyền vận hành hay giám sát.
- Thêm endpoint vào exposure không tự cấp quyền cho tài khoản đang có.

Đây là kiểm thử trong ứng dụng với MockMvc. Nó không chứng minh cấu hình ingress, tường lửa, TLS hoặc bộ ánh xạ danh tính bên ngoài đã đúng. Những ranh giới đó cần được kiểm tra trong môi trường triển khai tương ứng.

## 8. Tích hợp hệ thống giám sát mà không mở rộng quyền

### 8.1. Máy giám sát dùng danh tính riêng

Một tác vụ Prometheus nên dùng đúng danh tính thu thập số liệu. Không lấy mật khẩu người trực để đưa vào cấu hình máy giám sát.

Ví dụ dưới đây là cấu hình Prometheus cục bộ **khi Prometheus và ứng dụng cùng máy, cùng không gian mạng**. Nó minh họa đọc mật khẩu từ tệp bí mật; không phải tệp cần thêm vào dự án Maven:

```yaml
scrape_configs:
  - job_name: actuator-local
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    scheme: http
    basic_auth:
      username: monitor
      password_file: /run/secrets/actuator-monitor-password
    static_configs:
      - targets:
          - 127.0.0.1:8080
```

Tệp `/run/secrets/actuator-monitor-password` phải được cơ chế quản lý bí mật cung cấp, chứa đúng mật khẩu của `monitor`. Đường dẫn phải tồn tại trong môi trường chạy Prometheus và chỉ những tiến trình cần thiết mới được đọc. Nếu Prometheus chạy trong container, `127.0.0.1` chỉ về chính container đó; phải thiết kế lại kết nối theo môi trường, không thay địa chỉ ứng dụng thành công khai chỉ để giải quyết lỗi kết nối.

Prometheus hỗ trợ `basic_auth.password_file`; không cấu hình đồng thời `password` và `password_file`. Khi chuyển sang kết nối qua mạng, cấu hình HTTPS, đích thu thập và chuỗi tin cậy chứng chỉ phù hợp. Không bỏ kiểm tra chứng chỉ để làm cho kết nối “chạy được”. [Cấu hình HTTP của Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#http_config).

### 8.2. Quyền trong token hoặc chứng chỉ cũng phải theo ma trận

Trong môi trường thật có thể thay HTTP Basic bằng cơ chế xác thực được tổ chức sử dụng, chẳng hạn token có thời hạn hoặc chứng chỉ máy khách. Đổi cơ chế xác thực không làm mất yêu cầu phân quyền.

Nếu dùng token, cần kiểm tra chữ ký, bên phát hành, đối tượng nhận và thời hạn; sau đó ánh xạ quyền vào các authority mà ứng dụng thực sự kiểm tra. Một token có chữ “monitoring” trong nội dung không tự đáp ứng `actuator:prometheus:read`. Tên scope và tên authority còn phụ thuộc bộ chuyển đổi được cấu hình.

Nếu danh tính do cổng truy cập chuyển tiếp qua header, ứng dụng không được tin header có thể do người gọi bên ngoài tự đặt. Phải giới hạn nguồn tin cậy, loại header giả mạo ở biên và bảo vệ đường truyền giữa cổng truy cập với ứng dụng.

### 8.3. Thăm dò sức khỏe là một nhu cầu riêng

Ví dụ yêu cầu xác thực cho mọi lời gọi health. Một bộ cân bằng tải hoặc bộ thăm dò không gửi thông tin xác thực sẽ nhận 401.

Nếu nền tảng cần một đường thăm dò không xác thực:

1. Xác định chính xác đường thăm dò và dữ liệu tối thiểu mà nó trả.
2. Đặt quy tắc riêng cho đúng đường và phương thức, trước quy tắc rộng hơn.
3. Giới hạn nguồn kết nối và tần suất phù hợp.
4. Kiểm thử đường đó không kéo theo quyền xem toàn bộ health hoặc Actuator.

Không giải quyết bằng cách cho phép toàn bộ `/actuator/**`. Cũng không thêm đăng nhập cá nhân vào mọi bộ thăm dò của hạ tầng.

## 9. Khi người vận hành cần can thiệp

Trong thiết kế hiện tại, đọc loggers và đổi mức log là hai việc khác nhau. Nếu sự cố thực tế đòi hỏi đổi mức log, hãy xem đó là một thay đổi chính sách:

- Tạo quyền ghi riêng; không đổi ý nghĩa quyền `actuator:loggers:read`.
- Giới hạn tài nguyên và phương thức cần thiết, chẳng hạn chỉ thao tác đổi log đã được duyệt.
- Cấp cho đúng người, đúng môi trường và trong thời hạn xử lý sự cố.
- Xác định cơ chế bảo vệ CSRF phù hợp với cách xác thực thực tế.
- Ghi lại ai thực hiện, thao tác nào, khi nào, kết quả và mã tương quan; tránh ghi token, mật khẩu hoặc dữ liệu nhạy cảm.
- Thu hồi quyền tạm thời, khôi phục cấu hình và kiểm chứng sau xử lý.

Bài không tự bổ sung quyền ghi vào ví dụ vì nhu cầu ban đầu chỉ cần đọc chẩn đoán. Sử dụng Actuator không tự tạo đầy đủ quy trình phê duyệt, hết hạn quyền và nhật ký kiểm toán theo yêu cầu tổ chức; các phần đó phải được thiết kế riêng.

Với heap dump hoặc thread dump, cần đánh giá cả dữ liệu trả về, mức tiêu thụ tài nguyên, nơi lưu và thời hạn giữ dữ liệu trước khi quyết định mở quyền.

## 10. Lỗi thiết kế thường gặp

| Lựa chọn dễ gây sai | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Đưa mọi endpoint ra HTTP rồi yêu cầu đăng nhập | Mọi tài khoản có thể có bề mặt truy cập quá rộng nếu quy tắc cho phép rộng | Danh sách endpoint rõ ràng và mặc định từ chối |
| Dùng chung tài khoản cho Prometheus và nhóm vận hành | Lộ một bí mật ảnh hưởng nhiều công việc, khó thu hồi riêng | Tách danh tính máy và người |
| Cho tài khoản giám sát mọi endpoint GET | Đọc được dữ liệu vượt nhu cầu, có thể gây tải nặng | Chọn endpoint theo từng nhu cầu |
| Chỉ kiểm tra `/actuator/loggers` mà bỏ qua phương thức | Vô tình cho phép đổi mức log | Ghép endpoint, phương thức và quyền |
| Chỉ bảo vệ chuỗi Actuator | Phần ứng dụng còn lại có thể không được chuỗi nào bảo vệ | Có chuỗi bao phủ yêu cầu còn lại |
| Tự khai báo chuỗi bảo mật nhưng tiếp tục dựa vào mặc định cũ của Boot | Chính sách thực tế khác điều người viết tưởng | Kiểm tra rõ mọi chuỗi và thứ tự |
| Tắt CSRF chỉ vì thấy POST trả 403 | Che nguyên nhân và làm yếu bảo vệ cho luồng trình duyệt | Kiểm tra CSRF và phân quyền độc lập |
| Cho health luôn hiển thị chi tiết để tiện kiểm tra | Lộ cấu trúc và thông tin nội bộ | Kiểm soát riêng quyền gọi và quyền xem chi tiết |
| Đổi cổng hoặc tắt discovery rồi coi như đã bảo mật | Người biết địa chỉ vẫn có thể gọi trực tiếp nếu các lớp khác cho phép | Xác thực, phân quyền và giới hạn mạng |
| Chỉ kiểm thử tài khoản có quyền | Không phát hiện quyền bị cấp quá rộng | Kiểm thử ma trận các danh tính, thao tác cấm và endpoint mới |
| Tắt kiểm tra chứng chỉ khi thu thập số liệu | Không xác minh đúng máy chủ nhận thông tin xác thực | Cấu hình chứng chỉ và chuỗi tin cậy đúng |

## 11. Thực hành thiết kế lại cho một yêu cầu mới

Giả sử nhóm trực cần xem Prometheus để đối chiếu biểu đồ, nhưng không muốn mọi người vận hành có quyền này thường trực.

Hãy trả lời trước khi sửa mã:

1. Nhu cầu có thể đáp ứng bằng dashboard hiện có hay thật sự cần gọi endpoint nguồn?
2. Ai cần quyền, trên môi trường nào và trong thời gian nào?
3. Có nên cấp thêm quyền đọc Prometheus cho một danh tính cá nhân trong khoảng thời gian xử lý?
4. Khi thu hồi quyền, kiểm thử nào chứng minh quyền vận hành cũ vẫn hoạt động còn quyền bổ sung đã mất?
5. Có dữ liệu nào trong số liệu giám sát không nên cho nhóm đó xem?

Một phương án có cơ sở là giữ nguyên quyền gốc của `ops`, cấp tạm `actuator:prometheus:read` cho đúng người khi được duyệt và thu hồi sau sự cố. Khi đó cần kiểm thử cả trước khi cấp, trong thời gian được cấp và sau khi thu hồi.

Sau bài này, người học cần có thể giải thích từng ô được phép trong ma trận bằng một công việc cụ thể, chỉ ra lớp cấu hình thực thi quyền đó và đưa ra bằng chứng rằng các quyền ngoài nhu cầu đã bị từ chối.
