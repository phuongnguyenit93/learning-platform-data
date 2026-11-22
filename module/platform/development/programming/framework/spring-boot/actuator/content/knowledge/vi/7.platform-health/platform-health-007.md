# Quản lý show-details, show-components và quyền xem health

Một hệ thống giám sát chỉ cần biết ứng dụng còn hoạt động; người vận hành lại cần biết thành phần nào gặp sự cố và dữ liệu chẩn đoán liên quan. Nếu cả hai cùng gọi `/actuator/health`, làm thế nào trả đúng lượng thông tin cho từng người?

Trong Spring Boot Actuator, cần xác định riêng **quyền gọi endpoint**, **quyền thấy các thành phần** và **quyền thấy thông tin chi tiết**. Bài này dùng Spring Boot 3.3.x, Java 21 và ứng dụng Servlet với Spring Security. Phần cấu hình hiển thị cũng có ý nghĩa tương tự trong ứng dụng reactive, nhưng mã `HttpSecurity` bên dưới dành cho Servlet.

## 1. Nhận diện ba lớp thông tin trong phản hồi

Xét một phản hồi minh họa có một thành phần `sample`:

```json
{
  "status": "UP",
  "components": {
    "sample": {
      "status": "UP",
      "details": {
        "check": "demo-only",
        "target": "sample-service"
      }
    }
  }
}
```

| Vị trí | Ý nghĩa | Cấu hình liên quan |
| --- | --- | --- |
| `status` ngoài cùng | Trạng thái tổng hợp của ứng dụng | Không bị ẩn chỉ vì tắt components/details |
| `components.sample.status` | Trạng thái của thành phần có tên `sample` | `management.endpoint.health.show-components` |
| `components.sample.details` | Dữ liệu bổ sung do thành phần cung cấp | `management.endpoint.health.show-details` |

`show-components` quyết định có cho thấy cấu trúc thành phần hay không. `show-details` quyết định có giữ các trường `details` hay không. Bật chi tiết chỉ cho phép hiển thị dữ liệu đã được bộ kiểm tra tạo ra; nó không tự sinh thêm dữ liệu chẩn đoán.

Cấu trúc trên là dạng JSON V3 thông thường của health. Một thành phần tổng hợp còn có thể chứa `components` lồng nhau. Khi đọc ví dụ, hãy phân biệt `status` tổng với `status` của từng thành phần. [Mô tả phản hồi health của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

## 2. Đặt các thuộc tính hiển thị vào đúng luồng xử lý

Một yêu cầu HTTP đi qua các quyết định sau:

```text
Endpoint được bật và được công bố qua HTTP
        ↓
Spring Security xác thực và xét quyền truy cập
        ↓
Health được thu thập, tổng hợp
        ↓
Xét show-components / show-details theo người đang gọi
        ↓
Trả mã HTTP và nội dung health phù hợp
```

Công bố endpoint qua `management.endpoints.web.exposure.include` không đồng nghĩa với cấp quyền gọi. Tương tự, `show-details: always` không vượt qua một quy tắc Spring Security đang chặn yêu cầu.

Với ứng dụng có Spring Security, cấu hình tự động của Boot và cấu hình do ứng dụng tự khai báo cần được phân biệt: khi ứng dụng cung cấp `SecurityFilterChain`, ứng dụng chịu trách nhiệm đặt các quy tắc truy cập thích hợp. [Endpoint exposure và security trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Ví dụ về mục tiêu thiết kế:

- Khách được gọi health để xem trạng thái tổng.
- Người dùng đã đăng nhập nhưng không vận hành hệ thống vẫn chỉ thấy trạng thái tổng.
- Người có vai trò vận hành được xem thành phần và chi tiết.
- Các endpoint quản trị khác có quy tắc truy cập riêng.

Đây là bốn yêu cầu phải được thể hiện bằng cả cấu hình health lẫn cấu hình Spring Security.

## 3. Ba chế độ hiển thị và giá trị mặc định

Hai thuộc tính nhận cùng ba giá trị:

| Giá trị | Khi nào phần thông tin tương ứng được hiển thị? |
| --- | --- |
| `never` | Không hiển thị, kể cả người gọi có vai trò vận hành |
| `when-authorized` | Hiển thị khi ngữ cảnh bảo mật của người gọi đáp ứng vai trò health |
| `always` | Hiển thị cho mọi người đã qua được bước kiểm soát truy cập |

Trong Boot 3.3:

- `management.endpoint.health.show-details` mặc định là `never`.
- Nếu không khai báo `management.endpoint.health.show-components`, Boot dùng cấu hình `show-details` cho quyết định hiển thị thành phần.
- Vì vậy, khi để cả hai ở mặc định, phản hồi gốc thường chỉ có trạng thái tổng.

Điểm kế thừa này giải thích vì sao chỉ bật `show-details: always` cũng có thể làm xuất hiện `components`. Nếu muốn chính sách khác nhau, khai báo rõ cả hai. [Danh mục thuộc tính health của Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.health.show-components).

Cấu hình cân bằng cho ví dụ của bài:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: when-authorized
      show-details: when-authorized
      roles:
        - ACTUATOR
```

Các thuộc tính thuộc `management.endpoint.health` dùng `endpoint` số ít; phần công bố qua HTTP thuộc `management.endpoints.web` dùng `endpoints` số nhiều. Đặt sai nhánh YAML là một lỗi cấu hình dễ bỏ sót.

## 4. Hai công tắc phối hợp như thế nào?

Bảng dưới áp dụng cho **endpoint gốc** `/actuator/health`, giả sử yêu cầu đã được Spring Security cho đi qua và các thành phần đang UP.

| show-components | show-details | Người gọi | Phần chính nhìn thấy |
| --- | --- | --- | --- |
| `never` | `never` | Bất kỳ | Trạng thái tổng |
| `always` | `never` | Bất kỳ | Trạng thái tổng và từng thành phần, không có details |
| `always` | `when-authorized` | Không đủ vai trò health | Trạng thái tổng và từng thành phần, không có details |
| `always` | `when-authorized` | Đủ vai trò health | Thành phần cùng details nếu thành phần có cung cấp |
| `when-authorized` | `when-authorized` | Không đủ vai trò health | Trạng thái tổng |
| `when-authorized` | `when-authorized` | Đủ vai trò health | Thành phần cùng details nếu có |
| `never` | `always` | Bất kỳ | Trạng thái tổng; cây thành phần bị ẩn |
| Không khai báo | `always` | Bất kỳ | Thành phần cùng details nếu có |

Ở trường hợp `show-components: never`, không có đối tượng thành phần trong phản hồi gốc để chứa `details` của nó. Không nên dùng cấu hình này rồi mong chi tiết của từng thành phần vẫn xuất hiện bên cạnh trạng thái tổng.

Ẩn thông tin không loại một thành phần khỏi phép tổng hợp. Một thành phần DOWN vẫn có thể làm trạng thái tổng thành DOWN dù người gọi không được xem tên hoặc chi tiết của thành phần đó. Việc tính trạng thái và việc trình bày là hai quyết định khác nhau. [Cơ chế tổng hợp và lọc hiển thị trong mã nguồn Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

## 5. “Được phép xem” khác với “đã đăng nhập”

Với `when-authorized`, `management.endpoint.health.roles` xác định vai trò được xem phần thông tin tương ứng:

- Danh sách vai trò rỗng: mọi người đã xác thực đều được xem.
- Danh sách có `ACTUATOR`: người gọi cần có vai trò đó.
- Danh sách có nhiều vai trò: khớp ít nhất một vai trò là đủ, không yêu cầu có tất cả.
- Khách chưa xác thực không tự trở thành người được phép xem chỉ vì endpoint có `permitAll()`.

Thuộc tính `roles` không tạo tài khoản, không gán vai trò và không tự thiết lập cơ chế đăng nhập. Nó cũng không có tác dụng hạn chế thông tin đang được cấu hình `always`. [Quy tắc vai trò của health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

### Tên vai trò và tiền tố ROLE_

Trong cấu hình Servlet thông thường:

```text
User builder:      .roles("ACTUATOR")
Authority tạo ra:  ROLE_ACTUATOR
Health roles:      ACTUATOR
HTTP rule:         .hasRole("ACTUATOR")
```

`roles("ACTUATOR")` và `hasRole("ACTUATOR")` dùng quy ước vai trò của Spring Security. Kiểm tra vai trò qua Servlet cũng tích hợp với quy ước tiền tố `ROLE_`. Hãy dùng tên thống nhất như ví dụ; đừng truyền `ROLE_ACTUATOR` vào `roles(...)` rồi vô tình tạo cấu hình sai. [Spring Security và Servlet API](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html#servletapi-isuserinrole).

Nếu hệ thống xác thực bằng JWT chỉ cấp các authority dạng `SCOPE_...`, cần kiểm tra cách ánh xạ authority sang vai trò trước khi dùng cấu hình health này. Có token hợp lệ chưa chứng minh người gọi có `ROLE_ACTUATOR`. Với cơ chế bảo mật đã tùy chỉnh tiền tố hoặc cách kiểm tra vai trò, phải kiểm chứng bằng chính ngữ cảnh bảo mật thực tế.

## 6. Ví dụ độc lập: khách thấy trạng thái, người vận hành thấy chi tiết

Ví dụ sau là một dự án học tập riêng, không cần cơ sở dữ liệu. Bộ kiểm tra `sample` luôn trả UP với dữ liệu cố định để tập trung quan sát quyền hiển thị; nó không chứng minh một dịch vụ bên ngoài đang hoạt động.

Chuẩn bị JDK 21 và Gradle 8.5. Tạo bốn tệp theo cấu trúc:

```text
health-visibility-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/health/HealthVisibilityApplication.java
    └── resources/application.yml
```

### 6.1. Khai báo dự án

Tệp `settings.gradle`:

```groovy
rootProject.name = 'health-visibility-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

BOM quản lý các phiên bản thư viện liên quan, nên không gán phiên bản riêng cho từng starter. Đây là cách sử dụng BOM gốc của Gradle được Boot hỗ trợ. [Quản lý dependency với Gradle trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html#managing-dependencies.gradle-bom-support).

### 6.2. Cấu hình health

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: when-authorized
      show-details: when-authorized
      roles:
        - ACTUATOR
      probes:
        enabled: false
  health:
    defaults:
      enabled: false
```

Ví dụ tắt các bộ kiểm tra mặc định để phản hồi chỉ chứa `sample`, tránh phụ thuộc dung lượng đĩa của máy. Đây là lựa chọn phục vụ thí nghiệm; ứng dụng thực tế cần giữ những bộ kiểm tra phù hợp với mục tiêu giám sát.

### 6.3. Khai báo bộ kiểm tra và bảo mật

Tệp `src/main/java/example/health/HealthVisibilityApplication.java`:

```java
package example.health;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class HealthVisibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthVisibilityApplication.class, args);
    }

    @Bean
    HealthIndicator sample() {
        return () -> Health.up()
                .withDetail("check", "demo-only")
                .withDetail("target", "sample-service")
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
                .password(encoder.encode("reader-demo"))
                .roles("USER")
                .build();

        var ops = User.withUsername("ops")
                .password(encoder.encode("ops-demo"))
                .roles("ACTUATOR")
                .build();

        return new InMemoryUserDetailsManager(reader, ops);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR")
                .anyRequest()
                    .authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Giải thích những quyết định liên quan trực tiếp đến bài:

1. Bean tên `sample` tạo thành phần `sample` với hai giá trị chẩn đoán không nhạy cảm.
2. Quy tắc health xuất hiện trước quy tắc cho mọi Actuator endpoint, nên khách được phép đến health.
3. `permitAll()` cho phép đi qua bước xét quyền HTTP. Việc xem components/details vẫn do cấu hình health quyết định.
4. Các Actuator endpoint khác, nếu được công bố thêm sau này, đòi vai trò `ACTUATOR`; cấu hình hiện tại chỉ công bố health.
5. Quy tắc cuối yêu cầu xác thực cho các yêu cầu còn lại.
6. Hai tài khoản và mật khẩu trong mã chỉ phục vụ dự án học tập chạy tại máy. Khi triển khai thực tế, dùng cơ chế quản lý danh tính và bí mật của hệ thống; HTTP Basic cần được bảo vệ bằng HTTPS.

Không cần vô hiệu hóa CSRF để thực hiện các yêu cầu GET trong bài.

### 6.4. Khởi chạy

Từ thư mục dự án, chạy:

```shell
gradle bootRun
```

Hoặc tạo Gradle Wrapper rồi dùng wrapper:

```shell
gradle wrapper --gradle-version 8.5
```

Trong PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trong Linux/macOS:

```shell
./gradlew bootRun
```

Dùng Gradle để biên dịch vì chương trình phụ thuộc các thư viện Spring. Một lệnh `javac` đơn lẻ không tự tải dependency. Ứng dụng ghi log khởi động; bằng chứng cần quan sát trong bài là mã HTTP và JSON, không phải chuỗi log cố định.

## 7. Kiểm chứng ba đối tượng gọi cùng một URL

Các lệnh dưới dùng `curl.exe` trong PowerShell trên Windows. Trên Linux/macOS, thay bằng `curl`. Chỉ thực hiện sau khi ứng dụng khởi động thành công.

### 7.1. Khách chưa xác thực

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/health
```

Kỳ vọng HTTP 200 và nội dung:

```json
{"status":"UP"}
```

Khách được gọi endpoint vì quy tắc HTTP cho phép, nhưng không được xem components/details.

### 7.2. Người dùng thông thường

```powershell
curl.exe -i -u reader:reader-demo http://127.0.0.1:8080/actuator/health
```

Kỳ vọng HTTP 200 và nội dung:

```json
{"status":"UP"}
```

`reader` đã xác thực nhưng chỉ có vai trò `USER`. Với `health.roles: ACTUATOR`, việc đăng nhập thành công chưa đủ để thấy chi tiết.

### 7.3. Người vận hành

```powershell
curl.exe -i -u ops:ops-demo http://127.0.0.1:8080/actuator/health
```

Kỳ vọng HTTP 200 và JSON tương đương:

```json
{
  "status": "UP",
  "components": {
    "sample": {
      "status": "UP",
      "details": {
        "check": "demo-only",
        "target": "sample-service"
      }
    }
  }
}
```

Thứ tự trường và cách xuống dòng JSON không phải điều kiện đúng/sai. Cần kiểm tra đúng các trường, giá trị và mã HTTP.

### 7.4. Có thông tin đăng nhập nhưng mật khẩu sai

```powershell
curl.exe -i -u ops:wrong-password http://127.0.0.1:8080/actuator/health
```

Kỳ vọng HTTP 401 trong cấu hình HTTP Basic của ví dụ. `permitAll()` không biến một lần xác thực thất bại thành thành công; bộ lọc xác thực có thể kết thúc yêu cầu trước khi health xử lý nó.

## 8. Nếu yêu cầu là chỉ người vận hành mới được gọi health

Có hệ thống không muốn công bố cả trạng thái tổng cho khách. Khi đó cần thay **quy tắc HTTP dành cho health** trong ví dụ:

```java
.requestMatchers(EndpointRequest.to(HealthEndpoint.class))
    .hasRole("ACTUATOR")
```

Đây là đoạn thay thế trong `SecurityFilterChain`, không phải một chương trình Java độc lập.

Với HTTP Basic như ví dụ:

| Người gọi | Quyền HTTP | Kết quả kỳ vọng khi hệ thống UP |
| --- | --- | --- |
| Khách | Không có danh tính hợp lệ | HTTP 401 |
| `reader` có vai trò USER | Đã xác thực, thiếu vai trò cần để gọi | HTTP 403 |
| `ops` có vai trò ACTUATOR | Được gọi | HTTP 200 và thông tin theo cấu hình hiển thị |

Nếu vẫn giữ `show-details: never`, `ops` cũng không được xem details. Quyền gọi và quyền hiển thị phải đồng thời đáp ứng mục tiêu, không thay thế cho nhau.

Kết quả 401/403 trong bảng gắn với cấu hình HTTP Basic này. Một ứng dụng dùng đăng nhập bằng biểu mẫu hoặc bộ xử lý lỗi tùy chỉnh có thể có phản hồi xác thực khác; không suy diễn mọi cơ chế đăng nhập đều trả giống nhau.

## 9. Đường dẫn thành phần, health group và mã trạng thái

### 9.1. Truy vấn trực tiếp thành phần

Trong Boot 3.3, khi người gọi không được thấy components, truy vấn trực tiếp như `/actuator/health/sample` không phải cách vượt qua giới hạn hiển thị. Nếu yêu cầu qua được lớp Security nhưng components đang bị ẩn đối với người gọi, health có thể trả 404 cho đường dẫn thành phần. Vì vậy, 404 ở đường dẫn con chưa đủ để kết luận thành phần không tồn tại.

Với cấu hình ở mục 6:

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/health/sample
curl.exe -i -u ops:ops-demo http://127.0.0.1:8080/actuator/health/sample
```

Kỳ vọng lần lượt là 404 cho khách và 200 cho `ops`. Phản hồi thành công của đường dẫn con chứa trực tiếp `status` và `details` của `sample`, không bọc thêm một lớp `components.sample`. [Điều kiện cho đường dẫn thành phần trong Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### 9.2. Health group có thể có chính sách riêng

Nếu hệ thống đã khai báo health group, cần kiểm tra cấu hình hiệu lực của chính group được gọi. Các group có thể ghi đè `show-components`, `show-details` và `roles`; đừng chỉ đọc cấu hình health gốc rồi kết luận mọi URL con giống nhau. Ví dụ, một group dành cho bộ dò trạng thái và một group dành cho người vận hành có thể cần lượng thông tin khác nhau.

Ở đây chỉ cần nhận biết phạm vi cấu hình; việc chọn thành phần cho liveness/readiness là một bài toán riêng. [Cấu hình và kế thừa của health group trong Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

### 9.3. Ẩn chi tiết không biến DOWN thành UP

Khi dùng ánh xạ mặc định, trạng thái DOWN hoặc OUT_OF_SERVICE được ánh xạ thành HTTP 503. Các công tắc hiển thị không đổi quy tắc đó. Vì vậy, phản hồi HTTP 503 với `{"status":"DOWN"}` có thể là kết quả hợp lệ: hệ thống đang có sự cố, còn người gọi chỉ được xem trạng thái tổng. [Ánh xạ trạng thái health sang HTTP trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

## 10. Lỗi thường gặp và cách kiểm tra có mục tiêu

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Mọi người đều thấy details dù đã khai báo roles | `show-details` có đang là `always` không? Roles chỉ giới hạn chế độ `when-authorized` |
| Người dùng thường chỉ thấy status và nhận 200 | Có thể hoàn toàn đúng: HTTP cho phép gọi, health không cho xem thêm |
| Người vận hành vẫn không thấy details | Xác thực thực tế, authority/role, chế độ `never`, cấu hình bị ghi đè và dữ liệu do indicator cung cấp |
| Chỉ muốn ẩn details nhưng tên thành phần vẫn xuất hiện | Kiểm tra `show-components`; đây là quyết định riêng |
| Đã đổi show-details nhưng toàn bộ yêu cầu bị 401/403 | Kiểm tra SecurityFilterChain trước khi phân tích JSON |
| Endpoint gốc trả 404 | Kiểm tra dependency Actuator, enablement, exposure và địa chỉ/base path hiệu lực |
| Endpoint gốc tồn tại nhưng đường dẫn thành phần trả 404 | Kiểm tra quyền xem components bên cạnh tên thành phần |
| Cấu hình có vẻ đúng nhưng hành vi khác | Kiểm tra profile đang chạy, biến môi trường, tham số dòng lệnh và group được gọi |

Ngay cả tên thành phần cũng có thể tiết lộ cấu trúc hệ thống; `show-components: always` cần là một quyết định chủ động. Ngoài ra, `show-details` không phải bộ tự động che mọi trường nhạy cảm theo tên khóa. Khi viết indicator, chỉ đưa dữ liệu chẩn đoán cần thiết vào `withDetail`; tránh thông tin xác thực, chuỗi kết nối chứa bí mật hoặc dữ liệu khách hàng.

Nếu có proxy hay bộ nhớ đệm đứng trước endpoint, tránh dùng chung phản hồi health có chi tiết giữa các danh tính. Kiểm tra bằng các yêu cầu độc lập để chắc chắn phản hồi của người vận hành không được phục vụ lại cho khách.

## 11. Thực hành và tự kiểm tra

Giữ nguyên ví dụ mục 6. Mỗi lần thay cấu hình, khởi động lại ứng dụng rồi gọi lại bằng khách, `reader` và `ops`.

1. Đổi `show-components` thành `always`, giữ `show-details: when-authorized`. Dự đoán ai thấy tên `sample`, ai thấy `target`.
2. Giữ cả hai ở `when-authorized`, bỏ danh sách `roles`. So sánh `reader` với khách.
3. Đặt `show-details: never`, `show-components: always`. Kiểm tra cả `ops` có bị ẩn details không.
4. Bỏ riêng `show-components`, đặt `show-details: always`. Giải thích vì sao khách có thể thấy cả components và details.
5. Khôi phục cấu hình mục 6, thay `Health.up()` bằng `Health.down()` trong bean `sample`. Quan sát mã HTTP và lượng thông tin của khách so với `ops`.
6. Khôi phục UP rồi đổi quy tắc HTTP của health sang `hasRole("ACTUATOR")`. Phân biệt 401, 403 và phản hồi health thành công.

Đối chiếu dự đoán:

- Bài 1: cả ba thấy `sample`; chỉ `ops` thấy `target`.
- Bài 2: `reader` và `ops` thấy components/details; khách chỉ thấy trạng thái tổng.
- Bài 3: cả ba thấy trạng thái của `sample`; không ai thấy details.
- Bài 4: `show-components` dùng cấu hình của `show-details`, nên người đã qua được lớp HTTP đều thấy thêm thông tin.
- Bài 5: với ánh xạ mặc định, cả khách và `ops` nhận HTTP 503; khách thấy trạng thái DOWN tổng, `ops` thấy thêm thành phần và details.
- Bài 6: với HTTP Basic trong ví dụ, khách nhận 401, `reader` nhận 403, `ops` nhận 200.

Trước khi áp dụng cho ứng dụng thực tế, hãy viết rõ chính sách mong muốn cho từng nhóm người gọi, rồi kiểm tra cả mã HTTP lẫn sự có mặt của `components` và `details`. Một phản hồi “gọi được” chưa chứng minh thông tin đã được giới hạn đúng.
