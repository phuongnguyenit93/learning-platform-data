# Thiết lập cổng quản trị riêng và kiểm thử quyền truy cập

## 1. Mục tiêu và mô hình thực hành

Trong bài này, ta tách HTTP phục vụ nghiệp vụ khỏi HTTP quản trị của Spring Boot Actuator, rồi kiểm tra cả hai mặt:

1. Request có đi đúng cổng, đúng đường dẫn không?
2. Người gửi có được xác thực và được cấp đúng quyền không?

Cổng quản trị riêng giúp đặt đường truy cập vận hành trên một listener khác, thuận tiện cho định tuyến và giới hạn mạng. **Đổi cổng không tự tạo cơ chế xác thực hoặc phân quyền.** Một endpoint nhạy cảm trên cổng khác vẫn có thể bị truy cập nếu mạng và bảo mật cho phép.

Mô hình thử nghiệm dùng Spring Boot 3.3.x, Servlet stack, Spring Security 6 và Java 17+:

```text
Ứng dụng Spring Boot, cùng một tiến trình JVM
|
+-- 127.0.0.1:8080
|      GET /api/hello
|      Tài khoản app, quyền ROLE_APP
|
+-- 127.0.0.1:9091
       GET /manage/health
       Tài khoản operator, quyền ROLE_OPS

       GET /manage/prometheus
       Tài khoản scraper, quyền ROLE_METRICS
```

Cả hai listener chỉ bind vào loopback để bài thực hành chạy cục bộ. Trong triển khai nhiều máy/container, cần thiết kế địa chỉ lắng nghe và đường mạng phù hợp; không thay loopback thành mọi địa chỉ rồi mặc định vẫn có cùng mức giới hạn truy cập.

### Kết quả mong đợi

- Tài khoản nghiệp vụ không đọc được dữ liệu quản trị.
- Tài khoản vận hành đọc được health nhưng không mặc nhiên đọc metrics.
- Tài khoản thu thập metrics chỉ được đọc endpoint Prometheus.
- Request chưa xác thực bị từ chối.
- Đường dẫn ngoài danh sách cho phép bị từ chối.
- Các endpoint Actuator khác không được đưa vào danh sách HTTP exposure của bài thực hành.
- Kiểm thử xác nhận hành vi thực tế, thay vì chỉ kiểm tra rằng file YAML có đúng các key.

Bài này dùng HTTP Basic trên loopback để dễ quan sát. Với đường truyền vượt ra ngoài máy cục bộ, cần bảo vệ thông tin xác thực bằng TLS hoặc một kênh truyền đã được bảo vệ tương đương theo thiết kế hạ tầng. Base64 của HTTP Basic chỉ là mã hóa biểu diễn, không phải mã hóa bảo mật.

## 2. Phân biệt bốn lớp kiểm soát

| Lớp | Trách nhiệm | Ví dụ trong bài |
| --- | --- | --- |
| Listener và mạng | Request có kết nối được tới địa chỉ/cổng không? | Management bind 127.0.0.1:9091 |
| Endpoint và exposure | Endpoint nào có đường HTTP được công bố? | Chỉ health và prometheus |
| Xác thực | Request đại diện cho danh tính nào? | HTTP Basic, tài khoản app/operator/scraper |
| Phân quyền | Danh tính đó được đọc tài nguyên nào? | ROLE_OPS đọc health, ROLE_METRICS đọc Prometheus |

Một firewall chặn cổng không thay thế rule cấp quyền trong ứng dụng. Ngược lại, Basic authentication không làm một cổng public trở thành mạng riêng.

Health được tạo và expose cũng không có nghĩa mọi người đều được đọc. Trong bài này, cả health cũng yêu cầu xác thực; ta chủ động lựa chọn như vậy để kiểm tra quyền rõ ràng.

Các cấu hình phía dưới dành cho Spring Boot 3.3.x. Không chép thuộc tính endpoint của thế hệ Spring Boot khác vào bài rồi giả định có cùng ngữ nghĩa.

## 3. Chuẩn bị dự án và dependency

Dùng một dự án Spring Boot 3.3.x đã có Gradle wrapper, Boot plugin và cơ chế quản lý phiên bản dependency của Boot.

Phần dependency cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}

tasks.named('bootJar') {
    archiveFileName = 'management-port-lab.jar'
}
```

Đây là phần cấu hình cho dự án đã có các plugin cần thiết, không phải toàn bộ build file độc lập. Với một repository có build orchestration, bổ sung theo cơ chế của repository; không tạo một bộ cấu hình plugin trùng lặp.

Để kết quả dễ tái hiện:

- Không đồng thời thêm WebFlux vào bài thử nghiệm Servlet này.
- Không thêm security chain, servlet filter hoặc reverse proxy khác khi chưa kiểm tra ảnh hưởng của chúng.
- Không ghi đè riêng phiên bản Spring Security/Micrometer nếu chưa có lý do tương thích đã xác minh.
- Chọn các cổng 8080 và 9091 còn trống.
- Chạy bằng Java 17+ phù hợp với target bytecode của dự án.

Không chỉ có Actuator là đủ để tự xuất bản Prometheus; bài này còn cần registry Prometheus trên runtime classpath.

## 4. Cấu hình cổng quản trị và HTTP exposure

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 9091
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,prometheus
  endpoint:
    health:
      show-details: never
      show-components: never
```

Giải nghĩa:

- `server.port` là cổng của HTTP phục vụ ứng dụng.
- `management.server.port` khác cổng ứng dụng nên Boot tạo management web server riêng.
- `management.server.address` giới hạn địa chỉ listener quản trị trong bài này.
- `management.endpoints.web.base-path` đổi tiền tố Actuator từ `/actuator` sang `/manage`.
- Exposure chỉ đưa hai endpoint được chọn ra HTTP.
- Health không xuất chi tiết và danh sách component trong bài thử nghiệm này.

Hai URL quản trị là:

```text
http://127.0.0.1:9091/manage/health
http://127.0.0.1:9091/manage/prometheus
```

Cấu hình này giả định không có context/base path bổ sung và không có proxy sửa đường dẫn. Khi management server dùng cổng riêng, không tự ghép context path của application server vào URL quản trị.

Exposure không tự tạo dependency còn thiếu, cũng không cấp quyền truy cập. Nếu một nguồn cấu hình khác đặt `management.endpoints.web.exposure.exclude`, cần kiểm tra vì exclude được ưu tiên hơn include.

## 5. Tạo ứng dụng và một API nghiệp vụ

### 5.1. Lớp khởi động

Tệp `src/main/java/demo/management/ManagementPortLabApplication.java`:

```java
package demo.management;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementPortLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementPortLabApplication.class, args);
    }
}
```

### 5.2. Controller nghiệp vụ

Tệp `src/main/java/demo/management/HelloController.java`:

```java
package demo.management;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    private final Counter acceptedRequests;

    public HelloController(MeterRegistry registry) {
        acceptedRequests = Counter.builder("lab.api.accepted")
                .description("Requests accepted by the hello handler")
                .register(registry);
    }

    @GetMapping("/api/hello")
    public String hello() {
        acceptedRequests.increment();
        return "hello from application";
    }
}
```

Counter chỉ tăng khi request đã qua bảo mật và thực sự vào handler. Request bị từ chối trước handler không làm counter này tăng.

Tên trong Micrometer là `lab.api.accepted`; bản xuất Prometheus thường có series `lab_api_accepted_total`. Không dùng tên có dấu chấm để tìm nguyên xi trong bản xuất.

Các lớp này chạy trong ứng dụng Spring Boot có dependency đầy đủ. Không thể chỉ gọi `javac` với ba tệp ứng dụng mà không cung cấp classpath của framework.

## 6. Tách security chain cho Actuator và ứng dụng

Tệp `src/main/java/demo/management/SecurityConfiguration.java`:

```java
package demo.management;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            Environment environment) {
        var app = User.withUsername("app")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_APP_PASSWORD")))
                .roles("APP")
                .build();

        var operator = User.withUsername("operator")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_OPS_PASSWORD")))
                .roles("OPS")
                .build();

        var scraper = User.withUsername("scraper")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_METRICS_PASSWORD")))
                .roles("METRICS")
                .build();

        return new InMemoryUserDetailsManager(app, operator, scraper);
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health"))
                        .hasRole("OPS")
                        .requestMatchers(EndpointRequest.to("prometheus"))
                        .hasRole("METRICS")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/hello").hasRole("APP")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }
}
```

### 6.1. Vì sao cần thứ tự và fallback?

Spring Security chọn security filter chain khớp trước tiên theo thứ tự. Các chain không cộng dồn tất cả rule của chúng cho cùng một request.

- Chain thứ nhất khớp các endpoint Actuator bằng `EndpointRequest`.
- Bên trong chain đó, health và Prometheus có quyền riêng.
- Chain thứ hai không đặt `securityMatcher`, nên làm fallback cho request còn lại.
- Fallback chỉ cho `ROLE_APP` vào `/api/hello`; đường khác bị từ chối.

Nếu đặt chain bắt mọi request lên trước, chain Actuator có thể không bao giờ được chọn. Nếu chỉ tạo chain Actuator mà không bảo đảm request còn lại có chain phù hợp, có thể để lọt vùng chưa được bảo vệ.

Khi ứng dụng cung cấp security chain riêng, cần tự thiết kế rule; không coi cấu hình bảo mật Actuator mặc định vẫn tự hoàn thiện mọi phần còn thiếu.

### 6.2. Vì sao dùng EndpointRequest?

`EndpointRequest` hiểu đường dẫn của endpoint Actuator theo cấu hình Boot, thay vì bắt buộc viết cứng tiền tố `/manage` trong rule.

Nó không phải matcher theo TCP port. Việc đưa Actuator lên management listener riêng là trách nhiệm cấu hình server của Boot; quyền truy cập endpoint là trách nhiệm security chain. Phải kiểm tra cả listener lẫn quyền.

Không diễn giải `securityMatcher(EndpointRequest.toAnyEndpoint())` thành “mọi request trên cổng 9091 đều nằm trong chain thứ nhất”. Một đường lạ trên cổng quản trị vẫn có thể rơi vào fallback.

### 6.3. hasRole và tên authority

`roles("OPS")` tạo authority `ROLE_OPS`. Vì vậy, rule tương ứng là `hasRole("OPS")`.

Không viết `hasRole("ROLE_OPS")` theo thói quen nối thêm tiền tố. Nếu sử dụng `hasAuthority`, cần đối chiếu chuỗi authority đầy đủ mà danh tính đang có.

Trong bài này, `ROLE_OPS` không bao hàm `ROLE_METRICS` hoặc `ROLE_APP`. Không có phân cấp role được khai báo; operator không tự trở thành quản trị viên có mọi quyền.

### 6.4. Phạm vi của xác thực và CSRF

Ứng dụng dùng HTTP Basic, không dùng trang đăng nhập biểu mẫu. Kiểm thử bằng curl sẽ thấy phản hồi xác thực HTTP thay vì cần theo một trang HTML đăng nhập.

Các thao tác kiểm thử đều là GET. Cấu hình không tắt CSRF toàn ứng dụng và không expose endpoint thay đổi trạng thái. Khi bổ sung thao tác POST/DELETE hoặc một cơ chế xác thực khác, phải thiết kế và kiểm thử yêu cầu CSRF tương ứng; không suy ra từ các GET đã thành công.

`STATELESS` phục vụ lựa chọn không dùng HTTP session để duy trì đăng nhập trong bài này. Nó không tự là lý do đủ để tắt CSRF cho mọi kiểu client hoặc mọi phương thức xác thực.

### 6.5. Mật khẩu chỉ là dữ liệu của phiên thực hành

Ba mật khẩu được lấy từ môi trường, không ghi trong source. Nếu thiếu một biến yêu cầu, ứng dụng không thể tạo user store và sẽ không khởi động bình thường.

User store trong bộ nhớ phù hợp cho bài thực hành; khi chuyển sang hệ thống thật, lựa chọn kho danh tính, cơ chế thu hồi/quay vòng thông tin xác thực và phân quyền theo yêu cầu hệ thống.

Không in các biến mật khẩu hoặc header Authorization vào báo cáo kiểm thử. Việc băm bằng BCrypt trong user store không bảo vệ mật khẩu đang truyền trên HTTP; đó là hai lớp khác nhau.

## 7. Chuẩn bị mật khẩu và khởi động

Nhập ba mật khẩu riêng cho phiên thực hành. Các lệnh bên dưới không in mật khẩu ra terminal. Để tránh khác biệt về charset của HTTP Basic giữa các công cụ, dùng mật khẩu ASCII không rỗng cho bài thử nghiệm này.

### 7.1. Bash

```bash
read -r -s -p "Password for app: " LAB_APP_PASSWORD
printf '\n'
export LAB_APP_PASSWORD

read -r -s -p "Password for operator: " LAB_OPS_PASSWORD
printf '\n'
export LAB_OPS_PASSWORD

read -r -s -p "Password for scraper: " LAB_METRICS_PASSWORD
printf '\n'
export LAB_METRICS_PASSWORD

./gradlew bootJar
java -jar build/libs/management-port-lab.jar
```

### 7.2. PowerShell

```powershell
$labAppSecret = Read-Host "Password for app" -AsSecureString
$env:LAB_APP_PASSWORD = [System.Net.NetworkCredential]::new("", $labAppSecret).Password

$labOpsSecret = Read-Host "Password for operator" -AsSecureString
$env:LAB_OPS_PASSWORD = [System.Net.NetworkCredential]::new("", $labOpsSecret).Password

$labMetricsSecret = Read-Host "Password for scraper" -AsSecureString
$env:LAB_METRICS_PASSWORD = [System.Net.NetworkCredential]::new("", $labMetricsSecret).Password

.\gradlew.bat bootJar
java -jar build/libs/management-port-lab.jar
```

Biến môi trường là đầu vào của tiến trình, không phải kho secret lâu dài. Giữ chúng trong phiên thực hành, không chụp/in toàn bộ môi trường và không đưa giá trị vào source.

Đọc log để xác nhận cả hai web server đã khởi động trên đúng cổng. Việc web server đầu tiên khởi động chưa đủ nếu cổng management bị chiếm và ứng dụng thất bại tiếp sau đó.

Có thể đối chiếu listener bằng công cụ hệ điều hành. Trên PowerShell:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080,9091 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

Kết quả cụ thể phụ thuộc máy đang chạy. Cần thấy listener phù hợp với `127.0.0.1` và đúng tiến trình, không chép một PID dự đoán vào báo cáo.

Nếu dùng terminal thứ hai để kiểm tra HTTP, ứng dụng vẫn phải đang chạy. Chương trình kiểm thử Java ở phần sau cũng cần có ba biến môi trường; terminal mở mới từ nơi khác có thể không kế thừa các biến được đặt trong terminal khởi động.

## 8. Ma trận quyền cần kiểm chứng

Với đúng cấu hình của bài và ứng dụng đang khỏe:

| Request | Chưa xác thực | app / ROLE_APP | operator / ROLE_OPS | scraper / ROLE_METRICS |
| --- | --- | --- | --- | --- |
| 8080/api/hello | 401 | 200 | 403 | 403 |
| 9091/manage/health | 401 | 403 | 200 | 403 |
| 9091/manage/prometheus | 401 | 403 | 403 | 200 |

Diễn giải:

- `401`: chưa có danh tính hợp lệ, chẳng hạn thiếu hoặc sai mật khẩu.
- `403`: đã xác thực nhưng không có quyền phù hợp, trong các request GET của bài này.
- `200`: đã qua bảo mật và handler trả kết quả thành công.
- Lỗi kết nối: chưa tới được lớp HTTP; không diễn giải thành lỗi role.
- `503` từ health: có thể là trạng thái sức khỏe không đạt, không đồng nghĩa sai mật khẩu hoặc sai role.

Một response `403` ở phương thức thay đổi trạng thái còn có thể liên quan CSRF. Vì vậy, không áp dụng cách diễn giải giản lược của ma trận GET cho mọi request POST/DELETE.

### 8.1. Kiểm tra thủ công bằng curl

Dùng cú pháp một dòng để dễ chuyển giữa shell. Trên Windows, gọi `curl.exe` nếu `curl` đang là alias của một lệnh PowerShell khác.

Request không có thông tin xác thực:

```bash
curl -i http://127.0.0.1:9091/manage/health
```

Kỳ vọng `401` và header yêu cầu HTTP Basic. Không thêm `-L` để che mất redirect nếu có cấu hình khác làm xuất hiện redirect.

Request có tài khoản được phép:

```bash
curl -i --user operator http://127.0.0.1:9091/manage/health
curl -i --user scraper http://127.0.0.1:9091/manage/prometheus
curl -i --user app http://127.0.0.1:8080/api/hello
```

curl sẽ hỏi mật khẩu khi chỉ truyền username. Không cần đặt mật khẩu trực tiếp trong URL hoặc đối số lệnh.

Với request API thành công, body là:

```text
hello from application
```

Body không được mã controller thêm ký tự xuống dòng. Do dùng `-i`, terminal còn hiển thị header; phần header và các header động không phải output cố định của bài.

Với health, trong môi trường thử nghiệm khỏe và không có contributor tùy chỉnh:

```json
{"status":"UP"}
```

Nếu health báo khác, kiểm tra tài nguyên mà health contributor đo trước khi kết luận cấu hình xác thực sai.

Request dùng đúng mật khẩu nhưng sai quyền:

```bash
curl -i --user app http://127.0.0.1:9091/manage/health
curl -i --user operator http://127.0.0.1:9091/manage/prometheus
curl -i --user scraper http://127.0.0.1:8080/api/hello
```

Kỳ vọng cả ba đều `403`. Không chỉ kiểm tra một tài khoản được phép rồi kết luận mọi quyền đã tách đúng.

### 8.2. Kiểm tra sai mật khẩu

Chạy lại một request có username hợp lệ và nhập một mật khẩu khác mật khẩu đã cấu hình:

```bash
curl -i --user operator http://127.0.0.1:9091/manage/health
```

Kỳ vọng `401`, không phải `403`. Trường hợp này chứng minh bước xác thực khác với bước kiểm tra role.

Không ghi lại mật khẩu sai hoặc đúng trong biên bản; chỉ ghi nhãn thử nghiệm và status nhận được.

### 8.3. Kiểm tra đường ngoài danh sách cho phép

```bash
curl -i --user operator http://127.0.0.1:9091/manage/env
```

Với đúng security configuration trong bài, request này bị fallback từ chối và trả `403`. Endpoint `env` cũng không nằm trong exposure include.

Hai bằng chứng này có vai trò khác nhau: response `403` chứng minh request bị chặn; nó không tự chứng minh phía sau không có handler. Danh sách endpoint được expose phải được đối chiếu với cấu hình có hiệu lực và mapping của ứng dụng khi cần.

Đường khám phá `/manage` không được cấp quyền riêng trong ví dụ. Vì vậy, việc operator không mở được trang liên kết gốc không mâu thuẫn với việc đọc được `/manage/health`. Không dùng discovery page làm điều kiện bắt buộc để health hoặc metrics hoạt động.

## 9. Tự động hóa ma trận bằng Java 17

Chương trình dưới đây chỉ gửi GET tới hai listener cục bộ. Nó không cần dependency Spring, không in mật khẩu và không theo redirect. Nó kiểm tra status cùng một dấu hiệu trong body đối với các request được phép.

Tệp `AccessMatrixCheck.java`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.List;

public class AccessMatrixCheck {

    record Check(
            String name,
            String url,
            String username,
            String password,
            int expectedStatus,
            String bodyFragment) {
    }

    public static void main(String[] args) throws Exception {
        String appPassword = required("LAB_APP_PASSWORD");
        String opsPassword = required("LAB_OPS_PASSWORD");
        String metricsPassword = required("LAB_METRICS_PASSWORD");

        String appUrl = "http://127.0.0.1:8080/api/hello";
        String healthUrl = "http://127.0.0.1:9091/manage/health";
        String metricsUrl = "http://127.0.0.1:9091/manage/prometheus";

        List<Check> checks = List.of(
                new Check("app-anonymous", appUrl,
                        null, null, 401, null),
                new Check("app-app", appUrl,
                        "app", appPassword, 200, "hello from application"),
                new Check("app-operator", appUrl,
                        "operator", opsPassword, 403, null),
                new Check("app-scraper", appUrl,
                        "scraper", metricsPassword, 403, null),

                new Check("health-anonymous", healthUrl,
                        null, null, 401, null),
                new Check("health-app", healthUrl,
                        "app", appPassword, 403, null),
                new Check("health-operator", healthUrl,
                        "operator", opsPassword, 200, "\"UP\""),
                new Check("health-scraper", healthUrl,
                        "scraper", metricsPassword, 403, null),

                new Check("metrics-anonymous", metricsUrl,
                        null, null, 401, null),
                new Check("metrics-app", metricsUrl,
                        "app", appPassword, 403, null),
                new Check("metrics-operator", metricsUrl,
                        "operator", opsPassword, 403, null),
                new Check("metrics-scraper", metricsUrl,
                        "scraper", metricsPassword, 200,
                        "lab_api_accepted_total"),

                new Check("env-operator",
                        "http://127.0.0.1:9091/manage/env",
                        "operator", opsPassword, 403, null)
        );

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        boolean failed = false;

        for (Check check : checks) {
            try {
                HttpRequest.Builder request = HttpRequest.newBuilder()
                        .uri(URI.create(check.url()))
                        .timeout(Duration.ofSeconds(5))
                        .GET();

                if (check.username() != null) {
                    String credentials = check.username() + ":"
                            + check.password();
                    String basic = Base64.getEncoder().encodeToString(
                            credentials.getBytes(StandardCharsets.UTF_8));
                    request.header("Authorization", "Basic " + basic);
                }

                HttpResponse<String> response = client.send(
                        request.build(),
                        HttpResponse.BodyHandlers.ofString());

                boolean ok = response.statusCode() == check.expectedStatus()
                        && (check.bodyFragment() == null
                        || response.body().contains(check.bodyFragment()));

                System.out.printf("%s %s expected=%d actual=%d%n",
                        ok ? "PASS" : "FAIL",
                        check.name(),
                        check.expectedStatus(),
                        response.statusCode());

                if (!ok) {
                    failed = true;
                }
            } catch (Exception exception) {
                failed = true;
                System.out.println("FAIL " + check.name()
                        + " transport="
                        + exception.getClass().getSimpleName());
            }
        }

        System.out.println("RESULT=" + (failed ? "FAIL" : "PASS"));
        if (failed) {
            System.exit(1);
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required environment variable: " + name);
        }
        return value;
    }
}
```

Biên dịch và chạy từ terminal có ba biến môi trường đã đặt:

```bash
javac --release 17 AccessMatrixCheck.java
java AccessMatrixCheck
```

Các lệnh `javac` và `java` này cũng dùng được trên PowerShell nếu JDK nằm trên PATH.

Khi đúng cấu hình bài thực hành, mật khẩu khớp, ứng dụng khỏe và không có lớp proxy/filter bổ sung, stdout là:

```text
PASS app-anonymous expected=401 actual=401
PASS app-app expected=200 actual=200
PASS app-operator expected=403 actual=403
PASS app-scraper expected=403 actual=403
PASS health-anonymous expected=401 actual=401
PASS health-app expected=403 actual=403
PASS health-operator expected=200 actual=200
PASS health-scraper expected=403 actual=403
PASS metrics-anonymous expected=401 actual=401
PASS metrics-app expected=403 actual=403
PASS metrics-operator expected=403 actual=403
PASS metrics-scraper expected=200 actual=200
PASS env-operator expected=403 actual=403
RESULT=PASS
```

Chương trình không in toàn bộ body, nên không đưa dữ liệu metric hay trang lỗi vào stdout kiểm thử. Khi status đúng nhưng body thiếu dấu hiệu cần kiểm tra, dòng tương ứng vẫn là FAIL dù expected và actual bằng nhau.

Nếu một request lỗi hoặc sai kỳ vọng, chương trình tiếp tục kiểm tra các trường hợp còn lại rồi trả exit code 1. Với thành công, exit code là 0.

Đây là kiểm thử HTTP từ bên ngoài ứng dụng. Nó xác nhận ma trận trong phạm vi đã nêu, không thay thế kiểm thử TLS, discovery, firewall hay mọi phương thức HTTP của một hệ thống triển khai thật.

## 10. Xác minh cổng riêng và ranh giới mạng

### 10.1. Thử chéo cổng

Kiểm tra thêm:

```bash
curl -i --user operator http://127.0.0.1:8080/manage/health
curl -i --user app http://127.0.0.1:9091/api/hello
```

Các đường này không được trả dữ liệu thành công của tài nguyên đang thử ở sai listener. Trong ứng dụng đã có security filter, có thể nhận `403` trước khi đến bước tìm handler hoặc `404` sau khi qua bảo mật mà không có mapping. Không ép mọi phép thử sai cổng phải trả duy nhất `404`.

Nếu nhận `200` kèm đúng body của tài nguyên ở sai cổng, cần kiểm tra lại cấu hình port, mapping, controller hoặc lớp proxy. Chỉ nhìn vào số cổng trong file cấu hình chưa chứng minh sự tách biệt thực tế.

Đường sai cổng bị bảo mật chặn chưa đủ để một mình chứng minh không có mapping phía sau. Kết hợp kết quả này với listener thực tế, log khởi động và cấu hình quản trị có hiệu lực.

### 10.2. Tách kiểm thử mạng khỏi kiểm thử quyền

Với listener chỉ bind `127.0.0.1`, truy cập trực tiếp từ máy khác qua địa chỉ LAN của máy chạy ứng dụng không được phục vụ bởi listener loopback đó. Cần kiểm tra đúng network namespace: loopback trong container không phải loopback của host.

Trong triển khai dùng mạng quản trị riêng:

- Chọn địa chỉ interface phù hợp.
- Chỉ cho phép nguồn giám sát/vận hành cần thiết kết nối.
- Xác minh request được phép đi qua đường mạng dự kiến.
- Thử nguồn không được phép theo phạm vi kiểm thử hạ tầng.
- Vẫn kiểm tra danh tính và quyền ở lớp ứng dụng.

Nếu một nguồn bị firewall chặn, nó chưa kiểm thử được rule role trong ứng dụng. Nếu kiểm thử nội bộ nhận `403`, nó chưa chứng minh firewall bên ngoài đã đúng.

### 10.3. Container, proxy và health probe

Nếu Prometheus chạy trong container khác, `127.0.0.1:9091` của Prometheus không trỏ vào container Spring Boot. Bài cục bộ dùng loopback để giảm phạm vi; chuyển sang container cần thiết kế lại listener, mạng và tên đích một cách rõ ràng.

Không publish cổng management ra host hoặc internet theo thói quen chỉ vì nó là cổng riêng. Nếu truy cập qua proxy, phải kiểm tra cả tuyến đi thẳng tới backend để không bỏ qua quy tắc mà bạn nghĩ proxy đang thực thi.

Một health check thành công trên management listener không tự chứng minh application listener đang nhận request nghiệp vụ bình thường. Khi thiết kế readiness/liveness cho triển khai, cần chọn probe và đường kiểm tra phù hợp với khả năng phục vụ thực tế của ứng dụng.

Đồng thời, probe của hệ điều phối phải tương thích với chính sách xác thực đã chọn. Bài này yêu cầu xác thực health; nếu hệ điều phối không gửi được thông tin cần thiết, không được kết luận rằng health endpoint “tự nhiên không hoạt động”.

## 11. Chẩn đoán các kết quả không đúng kỳ vọng

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Không khởi động, báo thiếu property | Ba biến mật khẩu có trong môi trường của tiến trình Java không? |
| Port already in use | Cổng nào bị chiếm, bởi tiến trình nào? Đã dừng phiên chạy trước chưa? |
| Connection refused ở 9091 | Management server có khởi động, đúng address/port và đúng network namespace không? |
| 404 ở /actuator/health | Bài đã đổi base path sang /manage; đang gọi đúng cổng chưa? |
| Tài khoản đúng vẫn 401 | Giá trị mật khẩu trong client có khớp phiên ứng dụng đang chạy không? |
| Tài khoản app đọc được health | Chain order, matcher, rule permitAll và cấu hình Security thực tế có bị thay đổi không? |
| operator nhận 403 ở health | Authority có đúng ROLE_OPS không? Request đang vào chain nào? |
| operator không đọc được Prometheus | Đây là kỳ vọng của bài: operator không có ROLE_METRICS |
| Health 503 nhưng xác thực hợp lệ | Đọc trạng thái sức khỏe và kiểm tra tài nguyên; không đổi role để chữa DOWN |
| Scraper nhận 404 ở Prometheus | Registry có trên runtime classpath, endpoint có bật và expose không? |
| Prometheus có 200 nhưng thiếu counter | Đã dùng đúng registry, đúng tên xuất và đúng instance chưa? |
| Trả HTML hoặc redirect đăng nhập | Có form login/proxy/security chain khác đang tác động không? |
| Anonymous đọc được dữ liệu quản trị | Có rule cho phép ngoài ý muốn, listener/proxy khác hoặc artifact khác đang chạy không? |

Khi cần log chẩn đoán Spring Security, chỉ bật trong phạm vi phiên thử nghiệm và đọc chain/matcher đã được chọn. Không đưa header Authorization hoặc mật khẩu vào log. Sau mỗi thay đổi, khởi động lại nếu cần và chạy lại toàn bộ ma trận, vì thay một rule chung có thể ảnh hưởng nhiều đường.

Không sửa lỗi `401` bằng cách mở tất cả endpoint, cũng không sửa lỗi kết nối bằng cách cấp thêm role. Mỗi lớp cần bằng chứng và cách sửa tương ứng.

## 12. Tiêu chí nghiệm thu và kết thúc phiên thực hành

Bài thực hành hoàn thành khi:

1. Hai listener khởi động đúng địa chỉ và cổng được chọn.
2. API nghiệp vụ hoạt động với tài khoản app.
3. Health chỉ đọc được bởi operator trong ma trận đã thiết kế.
4. Prometheus chỉ đọc được bởi scraper trong ma trận đã thiết kế.
5. Request không xác thực và request sai quyền đều bị từ chối đúng dự kiến.
6. Thử sai mật khẩu phân biệt được lỗi xác thực với lỗi phân quyền.
7. Đường ngoài danh sách bị từ chối và HTTP exposure vẫn giới hạn đúng endpoint.
8. Thử chéo cổng không trả dữ liệu của tài nguyên ở sai listener.
9. Chương trình kiểm thử in RESULT=PASS với đúng ứng dụng và cấu hình vừa triển khai.
10. Giới hạn của bài cục bộ được ghi rõ khi chuyển sang mạng, TLS hoặc hệ thống danh tính khác.

Kết thúc phiên, dừng tiến trình thử nghiệm và xóa các biến mật khẩu khỏi terminal khi không còn dùng.

Bash:

```bash
unset LAB_APP_PASSWORD LAB_OPS_PASSWORD LAB_METRICS_PASSWORD
```

PowerShell:

```powershell
Remove-Item Env:LAB_APP_PASSWORD
Remove-Item Env:LAB_OPS_PASSWORD
Remove-Item Env:LAB_METRICS_PASSWORD
```

Xóa biến ở terminal không thay đổi môi trường của tiến trình Java đã được khởi động trước đó; vì vậy cần dừng tiến trình thử nghiệm riêng.

Điều cần chứng minh xuyên suốt bài là **cổng quản trị được tách đúng, endpoint được công bố có giới hạn, và từng danh tính chỉ có quyền đã thiết kế**. Ma trận cho phép/từ chối là bằng chứng hành vi để đối chiếu cấu hình đó.
