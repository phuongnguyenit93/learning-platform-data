# Kiểm chứng truy cập ẩn danh, sai quyền và đúng quyền trên cả cổng quản trị

## 1. Mục tiêu: chứng minh chính sách bằng một yêu cầu cụ thể

Một cấu hình bảo mật có thể trông đúng nhưng vẫn bảo vệ sai tài nguyên, sai đường dẫn hoặc chỉ được kiểm tra trên cổng ứng dụng. Khi Actuator chạy ở cổng quản trị riêng, kiểm thử phải gửi yêu cầu đến **đúng máy chủ quản trị**, không chỉ nạp một chuỗi bộ lọc rồi suy ra mọi cổng đều an toàn.

Mỗi phép kiểm chứng cần xác định đủ:

- Đích đến: giao thức, địa chỉ, cổng và đường dẫn.
- Phương thức HTTP.
- Danh tính: không đăng nhập, đăng nhập hợp lệ nhưng thiếu quyền, hoặc có đủ quyền.
- Kết quả mong đợi: mã trạng thái, header cần thiết và dấu hiệu nhận diện đúng tài nguyên.

Bài này xây dựng một dự án Java 21, Spring Boot 3.3.13, Spring MVC/Servlet. Nó có cổng ứng dụng 8080 và cổng Actuator 9090. Bộ kiểm thử dùng hai cổng được hệ điều hành cấp thật, gửi HTTP qua mạng loopback và xác minh cả nội dung JSON.

Kiểm thử HTTP tại máy chạy ứng dụng chứng minh hành vi của hai máy chủ và cấu hình bảo mật tại đó. Việc truy cập từ Internet, từ một namespace khác, qua reverse proxy hoặc qua TLS vẫn cần kiểm tra ở môi trường triển khai tương ứng.

## 2. Phân biệt ba trường hợp bằng danh tính và quyền

### 2.1. Truy cập ẩn danh

Người gọi không gửi thông tin đăng nhập, chẳng hạn không có header Authorization và không dùng phiên đã đăng nhập.

Với endpoint yêu cầu xác thực bằng HTTP Basic, mẫu này trả **401 Unauthorized**, kèm header `WWW-Authenticate` bắt đầu bằng `Basic`. Kết quả đó cho biết yêu cầu chưa có danh tính được chấp nhận.

### 2.2. Sai quyền

Người gọi dùng tài khoản có thật, mật khẩu đúng, nhưng không có authority hoặc vai trò mà endpoint yêu cầu. Trong mẫu, kết quả là **403 Forbidden**.

Không dùng mật khẩu sai để kiểm tra trường hợp “sai quyền”. Mật khẩu sai khiến xác thực thất bại, nên không chứng minh quy tắc phân quyền đã được áp dụng cho một danh tính hợp lệ.

### 2.3. Đúng quyền

Tài khoản được xác thực và có quyền cần thiết. Với hai thao tác GET được chọn trong bài, kết quả mong đợi là **200 OK** và nội dung JSON của đúng endpoint.

200 đơn lẻ chưa đủ. Một proxy có thể trả trang HTML, một client có thể đi theo chuyển hướng hoặc người viết test có thể gọi nhầm API cũng trả 200. Vì vậy, cần kiểm tra thêm kiểu nội dung và một giá trị đặc trưng trong phản hồi.

| Tình huống | Tài khoản/mật khẩu | Quyền cần thiết | Kết quả trong mẫu |
| --- | --- | --- | --- |
| Ẩn danh | Không gửi | Chưa có | 401 |
| Sai mật khẩu | Tên đúng, mật khẩu sai | Chưa xác thực được | 401 |
| Sai quyền | Đúng | Thiếu | 403 |
| Đúng quyền | Đúng | Có đủ | 200 và đúng nội dung |

Các mã trên là kỳ vọng cho endpoint và cơ chế Basic đã chọn. Không áp dụng máy móc cho mọi thao tác: POST có thể bị CSRF từ chối; health có thể trả 503 do trạng thái không tốt; cấu hình lỗi hoặc proxy cũng có thể tạo phản hồi khác.

## 3. Hai cổng là hai đích HTTP cần kiểm tra độc lập

Sơ đồ của bài thực hành:

```text
HTTP client
  |
  +-- http://127.0.0.1:8080/api/report
  |       Máy chủ ứng dụng
  |       Yêu cầu vai trò REPORT_READER
  |
  +-- http://127.0.0.1:9090/actuator/info
          Máy chủ quản trị
          Yêu cầu vai trò ACTUATOR

Ngoại lệ có chủ ý:
http://127.0.0.1:9090/actuator/health
    Cho phép ẩn danh, chỉ trả tình trạng tổng quát
```

Tách cổng giúp tổ chức đường truy cập nhưng không tự tạo xác thực hay phân quyền. Cổng 9090 vẫn cần chính sách bảo mật, cấu hình địa chỉ lắng nghe và kiểm soát mạng phù hợp.

Mẫu sử dụng:

| Người dùng | Vai trò | Mục đích |
| --- | --- | --- |
| reporter | REPORT_READER | Đọc báo cáo tại cổng ứng dụng |
| operator | ACTUATOR | Đọc thông tin Actuator tại cổng quản trị |

Ma trận chính:

| Đích GET | Ẩn danh | reporter, mật khẩu đúng | operator, mật khẩu đúng |
| --- | --- | --- | --- |
| 8080 — `/api/report` | 401 | 200 | 403 |
| 9090 — `/actuator/info` | 401 | 403 | 200 |
| 9090 — `/actuator/health` | 200 | 200 | 200 |

Dòng health là ngoại lệ được thiết kế, không phải bằng chứng Actuator bị mở toàn bộ. Một tài khoản không mặc nhiên được cấp quyền ở cả hai nhóm chỉ vì đã đăng nhập thành công ở một nhóm.

Trong Boot 3.3, cổng quản trị riêng được cấu hình bằng `management.server.port`. Tham khảo [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 4. Dự án thực hành hoàn chỉnh

### 4.1. Cấu trúc tệp

```text
management-port-verification/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── PortLabApplication.java
    │   │   └── PortSecurity.java
    │   └── resources/application.yml
    └── test/java/example/
        └── PortAccessTest.java
```

### 4.2. pom.xml

Dùng JDK 21 và Maven 3.6.3+. Các phiên bản Spring được quản lý bởi Spring Boot 3.3.13.

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
    <groupId>example</groupId>
    <artifactId>management-port-verification</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 4.3. src/main/resources/application.yml

```yaml
server:
  port: 8080
  address: 127.0.0.1

management:
  server:
    port: 9090
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: true

info:
  app:
    name: management-port-verification

lab:
  reporter-password: ${REPORTER_PASSWORD}
  operator-password: ${OPERATOR_PASSWORD}
```

Các lựa chọn đáng chú ý:

- 8080 và 9090 là cổng cố định dành cho việc chạy thủ công. Khi test, chúng được thay bằng cổng ngẫu nhiên.
- Cả hai máy chủ chỉ lắng nghe ở loopback để phục vụ bài thực hành tại máy cá nhân. Không dùng địa chỉ này cho một bên thu thập hoặc người gọi ở máy/Pod khác rồi kỳ vọng họ truy cập được.
- Chỉ health và info được công bố qua HTTP.
- `management.info.env.enabled` cho phép dữ liệu `info.*` được đưa vào phản hồi info. Giá trị `info.app.name` là dấu hiệu dùng để xác nhận đúng endpoint.
- Health không trả cấu trúc thành phần hoặc chi tiết bên trong.
- Hai mật khẩu lấy từ môi trường; không có mật khẩu mặc định trong cấu hình ứng dụng.

Cấu hình công bố (exposure) chỉ quyết định endpoint nào được công bố qua HTTP. Nó không thay thế quyền truy cập. Những dữ liệu được đưa vào `info.*` cũng cần được lựa chọn trước khi công bố.

### 4.4. src/main/java/example/PortLabApplication.java

```java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PortLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortLabApplication.class, args);
    }

    @RestController
    static class ReportController {
        @GetMapping("/api/report")
        Map<String, String> report() {
            return Map.of("result", "report-ok");
        }
    }
}
```

API báo cáo trả một giá trị cố định để kiểm chứng rằng yêu cầu đã qua bảo mật và đến đúng controller. Nó là một phép thử nhỏ cho sự tách biệt giữa ứng dụng và Actuator.

### 4.5. src/main/java/example/PortSecurity.java

```java
package example;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class PortSecurity {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(rules -> rules
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .anyRequest().hasRole("ACTUATOR"));
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(rules -> rules
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/report")
                        .hasRole("REPORT_READER")
                .anyRequest().authenticated());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(
            PasswordEncoder encoder,
            @Value("${lab.reporter-password}") String reporterPassword,
            @Value("${lab.operator-password}") String operatorPassword) {
        var reporter = User.withUsername("reporter")
                .password(encoder.encode(reporterPassword))
                .roles("REPORT_READER")
                .build();
        var operator = User.withUsername("operator")
                .password(encoder.encode(operatorPassword))
                .roles("ACTUATOR")
                .build();
        return new InMemoryUserDetailsManager(reporter, operator);
    }
}
```

Cách đọc hai chuỗi:

1. Chuỗi Actuator được xét trước, chọn endpoint theo `EndpointRequest` của Servlet. Health được công khai có chủ ý; các endpoint Actuator còn lại yêu cầu vai trò ACTUATOR.
2. Chuỗi thứ hai bao phủ những yêu cầu còn lại. GET đến API báo cáo yêu cầu REPORT_READER; các đường khác yêu cầu xác thực.
3. Khi một chuỗi đã khớp, yêu cầu không chạy tiếp qua chuỗi sau để tìm quyền dễ hơn. Xem [kiến trúc SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html#servlet-securityfilterchain).
4. `roles("ACTUATOR")` tạo authority `ROLE_ACTUATOR`, tương ứng với `hasRole("ACTUATOR")`. Tương tự cho REPORT_READER.
5. Cả hai chuỗi bật Basic và không lưu SecurityContext bằng phiên HTTP. Mỗi phép kiểm chứng gửi thông tin đăng nhập của chính nó.
6. CSRF được giữ nguyên. Các kiểm tra chính dùng GET; không cần tắt CSRF để chứng minh ba tình huống truy cập này.

Quy tắc cho `DispatcherType.ERROR` cho phép quá trình xử lý lỗi nội bộ trả phản hồi lỗi gốc. Nó không cấp `permitAll()` cho mọi yêu cầu trực tiếp đến URL `/error`. Điều này giúp các phép thử 404 không bị một lần kiểm tra bảo mật trong quá trình xử lý lỗi che mất kết quả ban đầu.

Quy tắc cuối `authenticated()` là lựa chọn của dự án thực hành, giúp một người đã đăng nhập đi đến bước tìm bộ xử lý cho các đường chưa tồn tại. Khi tích hợp vào hệ thống thật, cần chính sách đầy đủ cho các API thật, không mặc nhiên dùng quy tắc cuối này cho mọi ứng dụng.

Các kiểu trong bài thuộc Servlet: `HttpSecurity`, `SecurityFilterChain` và `EndpointRequest` nhánh `.servlet`. Với WebFlux phải dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và matcher Reactive; không chép lẫn kiểu giữa hai hệ API.

## 5. Kiểm chứng thủ công bằng curl

### 5.1. Chạy ứng dụng

Trong terminal chứa dự án, đặt mật khẩu dành riêng cho bài thực hành.

Bash:

```bash
export REPORTER_PASSWORD='lab-reporter-pass'
export OPERATOR_PASSWORD='lab-operator-pass'
mvn spring-boot:run
```

PowerShell:

```powershell
$env:REPORTER_PASSWORD = 'lab-reporter-pass'
$env:OPERATOR_PASSWORD = 'lab-operator-pass'
mvn spring-boot:run
```

Hai mật khẩu này là dữ liệu minh họa công khai. Không thay chúng bằng bí mật thật trong một lệnh được lưu vào lịch sử shell hoặc đưa vào repository.

Có thể đóng gói và chạy bằng Java:

```bash
mvn package
java -jar target/management-port-verification-1.0.0.jar
```

Giữ các biến môi trường trong terminal chạy JAR. Chỉ chạy một phiên ứng dụng để tránh tranh cổng 8080 hoặc 9090. Dự án cần dependency Spring nên dùng Maven để biên dịch và dựng classpath; gọi riêng `javac` trên một tệp không tự tải các thư viện.

Chờ cả hai máy chủ khởi động xong. Nếu chỉ thấy một cổng hoạt động thì chưa đủ điều kiện kiểm tra ma trận hai cổng.

### 5.2. Sáu yêu cầu chính

Mở terminal thứ hai. Các lệnh dưới dùng Bash. Trong PowerShell dùng `curl.exe` và thay `/dev/null` bằng `NUL`.

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:lab-operator-pass http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:lab-reporter-pass http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9090/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:lab-reporter-pass http://127.0.0.1:9090/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:lab-operator-pass http://127.0.0.1:9090/actuator/info
```

Kết quả lần lượt:

```text
401
403
200
401
403
200
```

Không dùng `-L` trong lượt kiểm chứng đầu vì cần nhìn thấy phản hồi chuyển hướng gốc nếu có. Curl mặc định không coi mọi mã HTTP 4xx/5xx là lỗi tiến trình; một script phải kiểm tra mã HTTP theo kỳ vọng, không chỉ dựa vào exit code của curl.

Nếu kết nối bị từ chối hoặc timeout, có thể thấy `000` và thông báo lỗi. Đó là lỗi kết nối, không phải một phản hồi xác thực thành công hay thất bại.

### 5.3. Xem header 401 và nội dung 200

Yêu cầu chưa đăng nhập:

```bash
curl -i http://127.0.0.1:9090/actuator/info
```

Kiểm tra mã trạng thái 401 và header `WWW-Authenticate` thông báo Basic. Không đối chiếu nguyên mọi header vì Date, thông tin kết nối hoặc thứ tự header có thể thay đổi.

Hai yêu cầu được cấp quyền:

```bash
curl -sS -u reporter:lab-reporter-pass http://127.0.0.1:8080/api/report
curl -sS -u operator:lab-operator-pass http://127.0.0.1:9090/actuator/info
```

Nội dung của yêu cầu báo cáo:

```json
{"result":"report-ok"}
```

Nội dung của yêu cầu info trong cấu hình mẫu:

```json
{"app":{"name":"management-port-verification"}}
```

Đây là nội dung phản hồi HTTP; curl không tự thêm xuống dòng giữa hai lệnh. Trong kiểm thử tự động, phân tích JSON và kiểm tra giá trị cần thiết thay vì phụ thuộc cách xuống dòng hoặc khoảng trắng.

### 5.4. Mật khẩu sai và nhầm cổng

Dùng đúng tên nhưng sai mật khẩu:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:wrong-password http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:wrong-password http://127.0.0.1:9090/actuator/info
```

Cả hai trả 401. Kết quả này bổ sung kiểm tra xác thực; nó không thay cho hai phép thử sai quyền dùng mật khẩu đúng.

Để kiểm tra endpoint có bị phục vụ nhầm cổng không, dùng danh tính hợp lệ để không bị lỗi xác thực che mất bước tìm bộ xử lý:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:lab-operator-pass http://127.0.0.1:8080/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:lab-reporter-pass http://127.0.0.1:9090/api/report
```

Trong cấu hình bài thực hành, cả hai trả 404. Yêu cầu đầu xác minh info không được phục vụ tại cổng ứng dụng; yêu cầu sau xác minh controller báo cáo không được phục vụ tại cổng quản trị.

Một yêu cầu ẩn danh đến URL sai có thể bị chặn bằng 401 trước khi tìm handler. Vì vậy, chỉ nhìn 401 ở cổng 8080 không chứng minh endpoint Actuator nằm trên cổng đó.

## 6. Vì sao bộ kiểm thử phải dùng máy chủ thật?

`@SpringBootTest` mặc định dùng môi trường MOCK. Một test MockMvc có thể kiểm tra tốt quy tắc phân quyền nhưng không chứng minh máy chủ quản trị đang lắng nghe ở cổng riêng hoặc client đã gửi đến cổng đó.

Ở bài này cần:

- `webEnvironment = RANDOM_PORT` để khởi động máy chủ ứng dụng.
- `management.server.port=0` để yêu cầu cổng quản trị ngẫu nhiên.
- `@LocalServerPort` để lấy cổng ứng dụng được cấp thật.
- `@LocalManagementPort` để lấy cổng quản trị được cấp thật.
- Một assertion rằng hai số cổng đều dương và khác nhau.

Giá trị 0 là yêu cầu hệ điều hành cấp cổng, không phải cổng để client kết nối. Không dựng URL từ `management.server.port` khi giá trị cấu hình vẫn là 0.

TestRestTemplate được Boot cung cấp có thể dùng URL tương đối gắn với cổng ứng dụng. Việc gọi `"/actuator/info"` trên client đó không tự chuyển sang cổng quản trị. Bộ kiểm thử bên dưới luôn dựng URL tuyệt đối từ cổng đã xác định.

Cách khởi động máy chủ thật và hỗ trợ cổng quản trị riêng được mô tả trong [Testing Spring Boot Applications 3.3](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

## 7. src/test/java/example/PortAccessTest.java

Đây là tệp kiểm thử đầy đủ. Nó không dùng `@WithMockUser` hay chèn sẵn một đối tượng Authentication; từng yêu cầu gửi Basic tới máy chủ thật. Mật khẩu test được cấp qua thuộc tính có độ ưu tiên cao hơn YAML nên không cần các biến môi trường dành cho lượt chạy thủ công.

```java
package example;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.util.stream.Stream;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.server.port=0",
                "lab.reporter-password=test-reporter-pass",
                "lab.operator-password=test-operator-pass"
        })
class PortAccessTest {
    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    ObjectMapper json;

    static Stream<Arguments> accessCases() {
        return Stream.of(
                Arguments.of("app anonymous", false, null, null,
                        HttpStatus.UNAUTHORIZED),
                Arguments.of("app wrong role", false, "operator", "test-operator-pass",
                        HttpStatus.FORBIDDEN),
                Arguments.of("app correct role", false, "reporter", "test-reporter-pass",
                        HttpStatus.OK),
                Arguments.of("management anonymous", true, null, null,
                        HttpStatus.UNAUTHORIZED),
                Arguments.of("management wrong role", true, "reporter", "test-reporter-pass",
                        HttpStatus.FORBIDDEN),
                Arguments.of("management correct role", true, "operator", "test-operator-pass",
                        HttpStatus.OK)
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("accessCases")
    void verifiesAccessMatrix(String label, boolean management,
            String username, String password, HttpStatus expected) throws Exception {
        int port = management ? managementPort : applicationPort;
        String path = management ? "/actuator/info" : "/api/report";
        ResponseEntity<String> response = get(port, path, username, password);

        assertThat(response.getStatusCode()).as(label).isEqualTo(expected);
        assertThat(response.getHeaders().getLocation()).isNull();
        if (expected == HttpStatus.UNAUTHORIZED) {
            assertThat(response.getHeaders().getFirst(HttpHeaders.WWW_AUTHENTICATE))
                    .startsWith("Basic ");
        }
        if (expected == HttpStatus.OK) {
            assertThat(response.getHeaders().getContentType())
                    .isNotNull()
                    .satisfies(type ->
                            assertThat(type.isCompatibleWith(MediaType.APPLICATION_JSON)).isTrue());
            var body = json.readTree(response.getBody());
            if (management) {
                assertThat(body.path("app").path("name").asText())
                        .isEqualTo("management-port-verification");
            }
            else {
                assertThat(body.path("result").asText()).isEqualTo("report-ok");
            }
        }
    }

    static Stream<Arguments> badPasswords() {
        return Stream.of(
                Arguments.of(false, "/api/report", "reporter"),
                Arguments.of(true, "/actuator/info", "operator")
        );
    }

    @ParameterizedTest
    @MethodSource("badPasswords")
    void rejectsWrongPassword(boolean management, String path, String username) {
        int port = management ? managementPort : applicationPort;
        var response = get(port, path, username, "wrong-password");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void usesTwoDistinctActualPorts() {
        assertThat(applicationPort).isPositive();
        assertThat(managementPort).isPositive().isNotEqualTo(applicationPort);
    }

    @Test
    void managementHealthIsPublicAndMinimal() throws Exception {
        var response = get(managementPort, "/actuator/health", null, null);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        var body = json.readTree(response.getBody());
        assertThat(body.path("status").asText()).isEqualTo("UP");
        assertThat(body.has("components")).isFalse();
        assertThat(body.has("details")).isFalse();
    }

    @Test
    void actuatorInfoIsNotServedOnApplicationPort() {
        var response = get(applicationPort, "/actuator/info",
                "operator", "test-operator-pass");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void businessControllerIsNotServedOnManagementPort() {
        var response = get(managementPort, "/api/report",
                "reporter", "test-reporter-pass");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void discoveryLinksAlsoRequireActuatorRole() {
        var forbidden = get(managementPort, "/actuator",
                "reporter", "test-reporter-pass");
        var allowed = get(managementPort, "/actuator",
                "operator", "test-operator-pass");
        assertThat(forbidden.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(allowed.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void unexposedEndpointIsNotMistakenForAnAuthorizationFailure() {
        var response = get(managementPort, "/actuator/env",
                "operator", "test-operator-pass");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    private ResponseEntity<String> get(int port, String path,
            String username, String password) {
        var factory = new SimpleClientHttpRequestFactory() {
            @Override
            protected void prepareConnection(HttpURLConnection connection,
                    String method) throws IOException {
                super.prepareConnection(connection, method);
                connection.setInstanceFollowRedirects(false);
            }
        };
        factory.setConnectTimeout(2000);
        factory.setReadTimeout(5000);
        var client = new TestRestTemplate(new RestTemplateBuilder()
                .requestFactory(() -> factory));

        var headers = new HttpHeaders();
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));
        if (username != null) {
            headers.setBasicAuth(username, password, StandardCharsets.UTF_8);
        }
        String url = "http://127.0.0.1:" + port + path;
        return client.exchange(url, HttpMethod.GET,
                new HttpEntity<Void>(headers), String.class);
    }
}
```

## 8. Đọc bộ kiểm thử theo điều nó chứng minh

### 8.1. Ma trận sáu trường hợp

`accessCases()` tạo sáu lần thực thi cho cùng một phương thức:

1. API ứng dụng, ẩn danh.
2. API ứng dụng, operator hợp lệ nhưng thiếu REPORT_READER.
3. API ứng dụng, reporter có quyền.
4. Actuator ở cổng quản trị, ẩn danh.
5. Actuator ở cổng quản trị, reporter hợp lệ nhưng thiếu ACTUATOR.
6. Actuator ở cổng quản trị, operator có quyền.

Với 401, test kiểm tra challenge Basic. Với 200, test kiểm tra Content-Type phù hợp JSON rồi đọc giá trị đặc trưng. Nó cũng yêu cầu không có header Location để tránh bỏ qua một dấu hiệu chuyển hướng bất thường.

Việc dùng cùng một đường dẫn, cùng phương thức và chỉ đổi danh tính trong từng nhóm giúp xác định sự khác biệt đến từ quyền truy cập thay vì vô tình kiểm tra hai tài nguyên khác nhau.

### 8.2. Hai trường hợp mật khẩu sai

Hai lần thực thi của `rejectsWrongPassword` kiểm tra xác thực ở cả hai cổng. Chúng tách biệt với sai quyền vì dùng một mật khẩu không hợp lệ.

Nếu một test dùng tên tài khoản không tồn tại rồi mong đợi 403, test đó đang nhầm điều kiện đầu vào. Cần một tài khoản đã xác thực được nhưng thiếu đúng quyền cần thiết.

### 8.3. Kiểm tra phản hồi đúng tài nguyên

Đối với API, JSON phải chứa `result=report-ok`. Đối với Actuator info, JSON phải chứa `app.name=management-port-verification`.

Cách này phát hiện nhiều lỗi mà điều kiện chỉ kiểm tra 200 không phát hiện được: nhầm cổng, nhầm URL, route phía trước trả trang mặc định hoặc nội dung phản hồi không thuộc tài nguyên cần kiểm chứng.

Không kiểm tra các trường không cần thiết như thời gian phản hồi chính xác, Date hoặc thứ tự thuộc tính JSON. Những chi tiết đó có thể thay đổi mà chính sách vẫn đúng.

### 8.4. Tách biệt cổng và các ngoại lệ

Hai phép thử chéo dùng danh tính hợp lệ rồi mong đợi 404:

- Actuator info không xuất hiện ở cổng ứng dụng.
- Controller nghiệp vụ không xuất hiện ở cổng quản trị.

Health ở cổng quản trị được thử riêng vì nó công khai có chủ ý. Test không coi mọi phản hồi 200 cho người ẩn danh là một lỗ hổng; phải so với chính sách của endpoint đó.

Endpoint khám phá liên kết `/actuator` cũng được kiểm tra: reporter bị từ chối, operator được đọc. Kiểm thử riêng endpoint liên kết tránh việc chỉ bảo vệ các URL con trong khi bỏ sót đường dẫn gốc.

Phép thử `env` dùng operator và mong đợi 404 do endpoint đó không được công bố trong mẫu. Nó ngăn việc diễn giải nhầm “không tồn tại/không được công bố” thành “thiếu quyền”.

### 8.5. Client không che giấu kết quả

Hàm `get` tạo client và header cho mỗi yêu cầu. Khi username là null, nó không tự gắn Basic; các danh tính không dùng chung header của lần thử trước.

`SimpleClientHttpRequestFactory` đặt timeout và tắt tự đi theo chuyển hướng. Kết quả 302 cần được nhìn thấy ở lượt kiểm chứng này, thay vì biến thành 200 của trang đăng nhập sau một lượt gọi khác.

TestRestTemplate giữ phản hồi 4xx/5xx để có thể kiểm tra mã trạng thái. Nó không đồng nghĩa một lỗi kết nối cũng sẽ biến thành ResponseEntity có mã 401. Lỗi kết nối phải làm phép thử thất bại và được điều tra riêng. Xem [TestRestTemplate 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html).

## 9. Chạy bộ kiểm thử và đánh giá kết quả

Tại thư mục dự án:

```bash
mvn clean test
```

Bộ kiểm thử tạo **14 lượt thực thi**:

| Nhóm | Số lượt |
| --- | --- |
| Ma trận truy cập ở hai cổng | 6 |
| Mật khẩu sai ở hai cổng | 2 |
| Hai cổng thực sự khác nhau | 1 |
| Health công khai và tối giản | 1 |
| Hai phép thử chéo cổng | 2 |
| Quyền đọc endpoint liên kết | 1 |
| Endpoint không được công bố | 1 |
| Tổng | 14 |

Điều kiện thành công: 14 lượt được thực thi, không có failure, error hoặc skipped. Số cổng và thời gian chạy không cố định.

Nếu chỉ test được ba trường hợp trên cổng ứng dụng, chưa đáp ứng mục tiêu kiểm chứng cổng quản trị. Nếu chỉ dùng một `@WithMockUser` trong môi trường mô phỏng, chưa kiểm tra được mật khẩu, cơ chế Basic hoặc kết nối đến cổng quản trị thật.

Các test ở đây chỉ đọc dữ liệu và không thay đổi nghiệp vụ. Khi mở rộng sang thao tác ghi trong một kiểm thử HTTP thật, lưu ý rằng giao dịch ở luồng máy chủ không tự được hoàn tác chỉ vì phương thức test có `@Transactional`.

## 10. Chẩn đoán theo lớp lỗi

| Quan sát | Điều cần xác minh |
| --- | --- |
| Kết nối bị từ chối | Máy chủ đó đã khởi động chưa; đúng địa chỉ/cổng chưa; có bị tranh cổng không |
| Timeout | Đường mạng, địa chỉ bind, firewall, proxy và trạng thái máy chủ |
| Ẩn danh nhận 200 ở info | Có cấu hình permitAll quá rộng, sai chuỗi bộ lọc hoặc đang gọi nhầm tài nguyên không |
| Mật khẩu sai vẫn nhận 200 | Có phiên/cookie hoặc header cũ, client tự xác thực hay một tài nguyên công khai không |
| Tài khoản thiếu vai trò nhận 401 | Danh tính có được xác thực thật sự chưa; mật khẩu/nguồn người dùng có đúng không |
| Tài khoản đủ vai trò nhận 403 | Authority thực tế, tiền tố ROLE_, chuỗi được chọn và các lớp proxy |
| Nhận 302 rồi 200 | Kiểm tra chuyển hướng, form login và việc client có tự theo Location không |
| Nhận 404 với đúng danh tính | Exposure, dependency, base-path, context-path, cổng và bộ xử lý |
| 200 nhưng nội dung là HTML | Có thể đang đến trang đăng nhập, gateway hoặc một tài nguyên khác |
| Chỉ cổng chính hoạt động | Kiểm tra lỗi khởi động context quản trị; không suy ra cổng quản trị dùng chung chính sách đã được xác minh |
| POST nhận 403 | Kiểm tra CSRF và chính sách của thao tác ghi; không đổi vai trò chỉ dựa vào GET thành công |

### 10.1. Quyền theo vai trò và tiền tố

`hasRole("ACTUATOR")` yêu cầu authority `ROLE_ACTUATOR`. Nếu nguồn danh tính chỉ cấp authority `ACTUATOR` thì không tự tương đương. Khi dùng `hasAuthority`, cần viết đúng giá trị authority mà hệ thống đang cấp.

Tài khoản operator trong mẫu có mật khẩu hợp lệ nhưng không có REPORT_READER, nên 403 ở cổng ứng dụng là kết quả đúng. Quyền vận hành không mặc nhiên là quyền đọc nghiệp vụ.

### 10.2. Không dùng mã trạng thái để suy ra quá mức

Một 401 ở URL `/actuator/env` chưa chứng minh env tồn tại: bảo mật có thể chạy trước bước tìm bộ xử lý. Tương tự, một 403 chưa chứng minh lỗi nằm ở vai trò; thao tác ghi hoặc lớp trung gian có thể bị chặn vì lý do khác.

Một 404 cũng cần gắn với URL và danh tính đã dùng. Trong các phép thử chéo, tài khoản được chọn đã vượt qua chính sách áp dụng để việc thiếu bộ xử lý được nhìn thấy rõ hơn.

### 10.3. Lỗi máy chủ/JDK không phải kết quả phân quyền

Nếu test chưa khởi động được máy chủ do lỗi socket, không thể báo rằng ma trận quyền đã được kiểm chứng. Chẳng hạn, lỗi `Unable to establish loopback connection` xảy ra trước khi nhận yêu cầu HTTP cần được xử lý ở môi trường JDK/hệ điều hành rồi chạy lại test.

Đừng biến một lỗi khởi động thành phép thử mô phỏng rồi vẫn kết luận rằng hai cổng HTTP thật đã qua kiểm tra. Mục tiêu và loại bằng chứng phải khớp nhau.

Trong lượt kiểm chứng bằng JDK 21.0.9 trên Windows, lỗi kết nối socket Unix nội bộ đã được xử lý cho phiên kiểm thử bằng tùy chọn JVM sau, rồi cả 14 lượt HTTP thật được chạy lại thành công:

```bash
mvn "-DargLine=-Djdk.net.unixdomain.tmpdir=./uds-directory-not-created" test
```

Trong cách xử lý này, thư mục con `uds-directory-not-created` phải không tồn tại. JDK được dùng trong lượt kiểm chứng chuyển sang cơ chế kết nối TCP nội bộ dự phòng khi không tạo được socket Unix tại thư mục đó. Hai cổng HTTP vẫn được mở thật và các yêu cầu vẫn đi qua xác thực, phân quyền.

Đây là cách xử lý đã xác minh cho môi trường JDK/hệ điều hành nói trên, không phải thuộc tính cấu hình Actuator. Nếu môi trường chạy bình thường, dùng lệnh Maven thông thường. Đối với một lỗi khởi động khác, cần tìm nguyên nhân của lỗi đó thay vì tự áp dụng cùng tùy chọn.

## 11. Kiểm chứng lại ở môi trường triển khai

Hai cổng loopback trong bài là môi trường học. Khi triển khai, dùng cùng cách lập ma trận cho các đích thật:

1. Cổng ứng dụng trực tiếp nếu có quyền kiểm tra.
2. Cổng quản trị từ mạng vận hành hoặc từ bên thu thập được cấp quyền.
3. Cửa vào công khai qua proxy/Ingress.
4. Đường đi có TLS, bao gồm việc kiểm tra tên máy và chuỗi CA.

Một test chạy ngay tại host không chứng minh máy khác đến được địa chỉ đó. Một test qua proxy cũng không chứng minh đường truy cập trực tiếp đến cổng quản trị đã bị giới hạn nếu cổng ấy còn công khai.

Với Basic, thông tin đăng nhập cần được bảo vệ khi truyền ngoài môi trường học. Không dùng bỏ qua kiểm tra chứng thư để làm một phép thử được coi là thành công. Nếu hạ tầng dùng Bearer token hoặc mTLS, giữ nguyên ba nhóm danh tính/quyền nhưng thay phần tạo thông tin xác thực và kỳ vọng challenge theo cơ chế thật.

Ghi nhận bằng chứng tối thiểu gồm đích đến, danh tính hoặc vai trò thử nghiệm, status và dấu hiệu nội dung phản hồi thuộc đúng tài nguyên. Không lưu mật khẩu, token hoặc header Authorization vào báo cáo.

Khi thay `management.endpoints.web.base-path`, `management.server.base-path`, context-path, ánh xạ endpoint hoặc thêm đường health ở cổng ứng dụng, phải cập nhật URL và các phép thử chéo tương ứng. Hai điều kiện kiểm tra 404 trong bài thể hiện cách bố trí hai máy chủ của mẫu, không phải một quy luật rằng mọi Actuator trong mọi cấu hình đều chỉ tồn tại ở cổng quản trị.

## 12. Bài tập tự kiểm tra

1. Chạy bộ 14 kiểm thử. Giải thích vì sao operator nhận 403 ở API nhưng 200 ở Actuator info.
2. Đổi mật khẩu của reporter trong một lượt gọi thủ công. Vì sao đây là phép thử xác thực, không phải phép thử sai quyền?
3. Thử gọi URL tương đối `/actuator/info` bằng client gắn với cổng ứng dụng rồi so với URL tuyệt đối dùng managementPort. Chỉ ra cách một test có thể gọi nhầm đích.
4. Thay vai trò yêu cầu của Actuator trong dự án thực hành. Bộ test nào phải thất bại trước khi cập nhật ma trận mong đợi?
5. Đổi base-path của Actuator và cập nhật các URL thật. Chứng minh cả ma trận quyền lẫn hai phép thử tách cổng vẫn đúng theo thiết kế mới.

Bạn kiểm chứng đầy đủ khi biết **yêu cầu đã tới cổng nào, danh tính nào được xác thực, quyền nào được kiểm tra và phản hồi thuộc đúng tài nguyên nào**, rồi có test thất bại rõ ràng nếu một trong các điều đó thay đổi ngoài dự kiến.
