# Phân biệt xác thực truy cập endpoint với quyền xem chi tiết dữ liệu

## 1. Đăng nhập thành công chưa quyết định toàn bộ nội dung phản hồi

Một endpoint quản trị có thể phục vụ nhiều nhóm người dùng. Nhân viên hỗ trợ chỉ cần biết ứng dụng còn hoạt động; người vận hành cần thêm tình trạng từng thành phần; một bộ kiểm tra tự động chỉ cần trạng thái tổng quát.

Nếu chỉ có lựa chọn “cho gọi hoặc cấm gọi”, ứng dụng sẽ khó phục vụ các nhu cầu đó. Spring Boot Actuator còn có cơ chế điều chỉnh mức dữ liệu hiển thị. Vì vậy cần phân biệt ba câu hỏi:

| Quyết định | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Xác thực (authentication) | Người gọi là ai? | Tên đăng nhập và mật khẩu có hợp lệ không? |
| Phân quyền truy cập endpoint | Danh tính đó được gọi endpoint này không? | Có vai trò `ENDPOINT_READER` để gọi health không? |
| Quyền xem dữ liệu chi tiết | Khi được gọi, người đó được thấy phần dữ liệu nào? | Có vai trò `HEALTH_DETAILS` để thấy chi tiết health không? |

**Quyền truy cập quyết định có được đi tới endpoint; chính sách hiển thị quyết định phần dữ liệu được trả về.** Một người có thể gọi thành công nhưng chỉ thấy trạng thái tổng quát. Ngược lại, có vai trò dùng cho kiểm tra dữ liệu chi tiết không tự cấp quyền gọi URL.

Bài dùng **Spring Boot 3.3.x**. Ví dụ chạy bằng Java 21, Spring Boot 3.3.0 và Spring Security 6.3 trong ứng dụng Servlet/Spring MVC. Các khái niệm về độ hiển thị vẫn có giá trị khi dùng WebFlux, nhưng cấu hình chuỗi bảo mật của WebFlux dùng các kiểu Reactive tương ứng.

## 2. Hình dung đường đi của một yêu cầu

```text
Endpoint đã đủ điều kiện và được công bố qua HTTP
    |
    v
Bộ lọc bảo mật xác thực danh tính
    |
    v
Quy tắc truy cập cho phép gọi endpoint?
    | Không -> phản hồi lỗi truy cập
    v Có
Endpoint lấy thông tin cần trả về
    |
    v
Chính sách hiển thị + ngữ cảnh bảo mật
    |
    +-- Chỉ trạng thái tổng quát
    +-- Tên/trạng thái thành phần, không có chi tiết
    +-- Các dữ liệu chi tiết được phép hiển thị
```

Việc bật endpoint và công bố endpoint cũng là điều kiện riêng. `exposure.include` không cấp quyền đăng nhập; quy tắc bảo mật không làm một endpoint chưa được công bố tự xuất hiện.

Với HTTP Basic trong ví dụ:

- **401:** chưa có thông tin xác thực hợp lệ để đi qua yêu cầu bảo vệ.
- **403:** đã xác thực nhưng không có quyền truy cập endpoint.
- **200 với dữ liệu rút gọn:** được phép gọi và chính sách hiển thị chủ động không đưa chi tiết vào phản hồi.

Một phản hồi health có trạng thái sức khỏe xấu còn có thể dùng mã HTTP khác. Đừng coi mọi mã khác 200 là lỗi đăng nhập, hoặc mọi phản hồi 200 là bằng chứng rằng người gọi được xem toàn bộ dữ liệu.

## 3. Health có chính sách hiển thị riêng

Các thuộc tính thường dùng:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: HEALTH_DETAILS
```

- `show-details` điều khiển việc đưa dữ liệu chi tiết vào kết quả health.
- `show-components` điều khiển việc hiển thị các thành phần của cây sức khỏe.
- `roles` chỉ định những vai trò đủ điều kiện theo chính sách `when-authorized`.

Hai mức “thấy tên/trạng thái thành phần” và “thấy dữ liệu chi tiết của thành phần” khác nhau. Có thể chủ động cho phép mức thứ nhất nhưng ẩn mức thứ hai. Đây là các thuộc tính của endpoint và nhóm health, không phải khai báo vai trò cho tài khoản. [API thuộc tính health của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/health/HealthProperties.html).

### Các giá trị hiển thị

| Giá trị | Ý nghĩa khi yêu cầu đã được phép truy cập |
| --- | --- |
| `never` | Không hiển thị phần dữ liệu được thuộc tính đó kiểm soát |
| `when-authorized` | Chỉ hiển thị khi người gọi đủ điều kiện theo kiểm tra của endpoint |
| `always` | Hiển thị mà không yêu cầu vai trò xem chi tiết của cơ chế này |

`always` không vô hiệu hóa bộ lọc bảo mật. Một người vẫn có thể bị chặn ở URL trước khi endpoint tạo phản hồi.

Với `when-authorized`, người gọi cần được xác thực và có ít nhất một vai trò trong danh sách `roles`. Khi không cấu hình danh sách vai trò, mọi người dùng đã xác thực được coi là đủ điều kiện xem theo cơ chế này. Mặc định `show-details` là `never`. [Thông tin health và điều kiện hiển thị](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Do đó, `when-authorized` không tự mang ý nghĩa “chỉ quản trị viên”. Muốn giới hạn cho một nhóm cụ thể, phải cấu hình danh sách vai trò tương ứng và cấp đúng vai trò cho danh tính.

## 4. Thí nghiệm: hai loại quyền độc lập

### 4.1. Ba tài khoản

| Tài khoản | Vai trò | Mục đích |
| --- | --- | --- |
| `reader` | `ENDPOINT_READER` | Được gọi health, không có quyền xem chi tiết |
| `details` | `HEALTH_DETAILS` | Có vai trò dùng cho độ hiển thị, nhưng thiếu quyền gọi health |
| `operator` | Cả hai vai trò trên | Được gọi health và được xem chi tiết |

Tên hai vai trò do thí nghiệm lựa chọn. Spring Boot không tự tạo mối quan hệ giữa chúng.

### 4.2. Chuẩn bị dự án

Dùng dự án Gradle có Wrapper 8.5 và JDK 21. Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-visibility-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

### 4.3. Một HealthIndicator chứa dữ liệu giả lập

Tệp `src/main/java/example/DetailVisibilityApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DetailVisibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(DetailVisibilityApplication.class, args);
    }

    @Bean
    HealthIndicator lab() {
        return () -> Health.up()
            .withDetail("sample", "synthetic")
            .withDetail("pendingJobs", 2)
            .build();
    }
}
```

Thành phần `lab` luôn báo `UP`. Hai chi tiết `sample` và `pendingJobs` là dữ liệu giả lập cố định, giúp quan sát phần nào bị ẩn mà không sử dụng thông tin nhạy cảm thật.

### 4.4. Cấu hình công bố và độ hiển thị

Tệp `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  health:
    defaults:
      enabled: false
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: HEALTH_DETAILS
```

Trong thí nghiệm, `management.health.defaults.enabled=false` tắt các bộ kiểm tra sức khỏe mặc định để phản hồi chỉ tập trung vào bean `lab` do ứng dụng khai báo. Đây là thiết lập phục vụ việc quan sát, không phải đề xuất tắt các phép kiểm tra sức khỏe của hệ thống thật.

YAML chỉ chọn health để công bố qua HTTP và đặt chính sách hiển thị. Nó chưa thiết lập quy tắc `ENDPOINT_READER` cho URL.

### 4.5. Cấu hình quyền gọi endpoint

Tệp `src/main/java/example/VisibilitySecurityConfig.java`:

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class VisibilitySecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .hasRole("ENDPOINT_READER")
                .anyRequest().denyAll())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-lab-pass"))
            .roles("ENDPOINT_READER")
            .build();
        var details = User.withUsername("details")
            .password(encoder.encode("details-lab-pass"))
            .roles("HEALTH_DETAILS")
            .build();
        var operator = User.withUsername("operator")
            .password(encoder.encode("operator-lab-pass"))
            .roles("ENDPOINT_READER", "HEALTH_DETAILS")
            .build();
        return new InMemoryUserDetailsManager(reader, details, operator);
    }
}
```

Quy tắc Java yêu cầu `ENDPOINT_READER` để truy cập health. Các yêu cầu còn lại bị từ chối. Đây là cấu hình ứng dụng tối thiểu chỉ phục vụ thí nghiệm; một ứng dụng có API nghiệp vụ cần chính sách cho những API đó.

Các mật khẩu cố định chỉ dùng cục bộ. BCrypt mã hóa chúng trước khi lưu vào kho người dùng trong bộ nhớ. HTTP Basic qua mạng cần được bảo vệ bằng HTTPS và sử dụng thông tin xác thực được quản lý phù hợp.

`roles("HEALTH_DETAILS")` cấp authority `ROLE_HEALTH_DETAILS` cho người dùng trong cấu hình Spring Security này. `management.endpoint.health.roles=HEALTH_DETAILS` đọc vai trò để quyết định độ hiển thị; thuộc tính đó không cấp thêm authority cho bất kỳ tài khoản nào.

## 5. Gọi cùng endpoint bằng các danh tính khác nhau

Khởi động trong PowerShell, tại thư mục dự án:

```powershell
.\gradlew.bat bootRun
```

Trong Bash dùng `./gradlew bootRun`. Đây là ứng dụng cần dependency Spring; quy trình build của dự án sẽ chuẩn bị classpath, thay vì gọi `javac` trực tiếp mà thiếu thư viện.

### 5.1. Không gửi thông tin xác thực

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

Kết quả:

```text
401
```

Bộ lọc bảo mật chưa cho phép truy cập, nên chính sách hiển thị không tạo ra một phản hồi health thành công cho yêu cầu này.

### 5.2. Được gọi nhưng chưa được xem chi tiết

```powershell
curl.exe -s -u "reader:reader-lab-pass" http://localhost:8080/actuator/health
```

Phản hồi:

```json
{
  "status": "UP"
}
```

Mã HTTP là 200 trong trạng thái giả lập khỏe mạnh. Không có `components.lab.details` vì tài khoản không có vai trò `HEALTH_DETAILS`. Đây là kết quả dự kiến, không phải lỗi thiếu dữ liệu.

### 5.3. Có vai trò xem chi tiết nhưng thiếu quyền gọi URL

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "details:details-lab-pass" http://localhost:8080/actuator/health
```

Kết quả:

```text
403
```

Tài khoản có thông tin xác thực hợp lệ và vai trò `HEALTH_DETAILS`, nhưng quy tắc truy cập yêu cầu `ENDPOINT_READER`. Kiểm tra độ hiển thị không giúp vượt qua quy tắc này.

### 5.4. Có cả hai loại quyền

```powershell
curl.exe -s -u "operator:operator-lab-pass" http://localhost:8080/actuator/health
```

Cấu trúc phản hồi:

```json
{
  "status": "UP",
  "components": {
    "lab": {
      "status": "UP",
      "details": {
        "sample": "synthetic",
        "pendingJobs": 2
      }
    }
  }
}
```

Thứ tự thuộc tính JSON không phải một phần của quy tắc phân quyền. Khi kiểm thử, so sánh cấu trúc và giá trị cần quan tâm, không phụ thuộc cách định dạng hoặc thứ tự trường.

### Ma trận kết quả

| Người gọi | Xác thực hợp lệ | Có ENDPOINT_READER | Có HEALTH_DETAILS | HTTP | Nội dung health |
| --- | --- | --- | --- | --- | --- |
| Không xác thực | Không | Không | Không | 401 | Không nhận bản health thành công |
| reader | Có | Có | Không | 200 | Chỉ trạng thái tổng quát |
| details | Có | Không | Có | 403 | Bị chặn ở quy tắc truy cập |
| operator | Có | Có | Có | 200 | Có thành phần và chi tiết |

Ma trận này cho thấy cần kiểm tra cả mã phản hồi lẫn cấu trúc dữ liệu. Chỉ xác nhận 200 sẽ bỏ sót khác biệt giữa bản tổng quát và bản chi tiết.

## 6. Thay chính sách hiển thị mà giữ nguyên quyền URL

Mỗi thử nghiệm sau giữ nguyên Java và tài khoản, chỉ đổi các thuộc tính hiển thị rồi khởi động lại. Không giữ lẫn cấu hình của hai thử nghiệm.

| show-details | show-components | roles | reader thấy gì? | operator thấy gì? |
| --- | --- | --- | --- | --- |
| `when-authorized` | `when-authorized` | `HEALTH_DETAILS` | Chỉ trạng thái tổng quát | Thành phần và chi tiết |
| `never` | `never` | `HEALTH_DETAILS` | Chỉ trạng thái tổng quát | Chỉ trạng thái tổng quát |
| `always` | `always` | `HEALTH_DETAILS` | Thành phần và chi tiết | Thành phần và chi tiết |
| `when-authorized` | `when-authorized` | Không có vai trò cấu hình | Thành phần và chi tiết | Thành phần và chi tiết |
| `never` | `always` | `HEALTH_DETAILS` | Tên/trạng thái thành phần, không có details | Tên/trạng thái thành phần, không có details |

Trong cả năm trường hợp, người chưa xác thực vẫn nhận 401 và tài khoản `details` vẫn nhận 403. Thay chính sách hiển thị không thay thế quyền truy cập.

### Chỉ hiển thị thành phần, không hiển thị chi tiết

```yaml
management:
  endpoint:
    health:
      show-components: always
      show-details: never
      roles: HEALTH_DETAILS
```

Với người đã qua được quy tắc URL, cấu trúc nhận được là:

```json
{
  "status": "UP",
  "components": {
    "lab": {
      "status": "UP"
    }
  }
}
```

Tên thành phần cũng là một dạng thông tin về hệ thống. Vì vậy, cần chủ động chọn mức hiển thị phù hợp, thay vì chỉ kiểm tra có trường `details` hay không.

Health group có thể có cấu hình hiển thị và vai trò riêng. Nếu dùng nhóm như `/actuator/health/internal`, cần kiểm tra cấu hình hiệu lực và kết quả của đúng nhóm đó; không suy ra mọi nhóm giống endpoint tổng hợp.

## 7. Với env/configprops: quyền gọi và quyền thấy giá trị vẫn tách biệt

Một số endpoint dữ liệu có cơ chế che giá trị. Ví dụ thuộc tính của endpoint env:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: CONFIG_DETAILS
```

Đây là đoạn minh họa chính sách **hiển thị giá trị** của env, không bổ sung env vào ứng dụng thử nghiệm ở trên và không cấp quyền gọi `/actuator/env`. Cần thiết kế việc công bố và truy cập endpoint riêng nếu thực sự sử dụng nó.

`EnvironmentEndpointProperties` có các thuộc tính `showValues` và `roles` để cấu hình phần này. [API cấu hình env của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/env/EnvironmentEndpointProperties.html).

Đối với env, configprops và quartz trong Spring Boot 3.3, mặc định các giá trị trong phản hồi được che. `show-values` nhận `never` để giữ che giá trị, `when-authorized` để kiểm tra quyền xem và `always` để cho phép hiển thị cho những yêu cầu đã qua được quy tắc truy cập. Các giá trị vẫn có thể bị xử lý bởi `SanitizingFunction` tùy chỉnh; vì thế, `always` không bảo đảm mọi giá trị đều được đưa ra nguyên dạng.

Hãy phân biệt:

- Không được gọi endpoint: yêu cầu bị từ chối theo chính sách truy cập.
- Được gọi nhưng không được xem giá trị: phản hồi vẫn có thể thành công với giá trị bị che.
- Đủ điều kiện xem: giá trị còn phụ thuộc những quy tắc che dữ liệu đang áp dụng.

Không coi “đã che giá trị” là “không còn thông tin nào đáng quan tâm”. Tên thuộc tính, cấu trúc dữ liệu và nguồn cấu hình vẫn có thể tiết lộ đặc điểm hệ thống.

Cũng không có một thuộc tính `roles` chung tự bảo vệ mọi endpoint Actuator theo cùng một cách. Cần đọc cơ chế của endpoint cụ thể: `health.show-details` và `env.show-values` giải quyết hai dạng dữ liệu khác nhau.

## 8. Kênh truy cập là một phần của thiết kế quyền

`SecurityFilterChain` trong ví dụ kiểm soát HTTP. Nó không tạo chính sách xác thực hoặc phân quyền cho JMX.

Riêng cơ chế `show-values` nêu trên, Spring Boot 3.3 coi người gọi JMX là đủ điều kiện trong kiểm tra hiển thị của endpoint. Không được dựa vào vai trò HTTP để kết luận giá trị được che tương tự qua JMX. Cần đánh giá việc bật kênh, công bố endpoint và kiểm soát người gọi JMX riêng. [Quy tắc hiển thị giá trị qua HTTP và JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitizing).

Tương tự, đưa HTTP quản trị sang cổng riêng không tự quyết định ai được xem dữ liệu chi tiết. Cổng, đường mạng, danh tính, quyền gọi và độ hiển thị cần phối hợp theo cùng một thiết kế.

## 9. Những lỗi suy luận thường gặp

### “Đăng nhập được thì phải thấy toàn bộ JSON”

Xác thực chỉ xác định danh tính. Người dùng vẫn có thể thiếu quyền gọi endpoint, hoặc được gọi nhưng thiếu điều kiện xem chi tiết. Kiểm tra từng lớp riêng.

### “health.roles đã bảo vệ URL”

Thuộc tính này phục vụ kiểm tra hiển thị của health. Muốn bảo vệ URL, phải có quy tắc bảo mật HTTP phù hợp. Nếu URL được `permitAll()`, việc khai báo `health.roles` không tự biến URL thành yêu cầu đăng nhập.

### “when-authorized luôn là chỉ dành cho admin”

Nếu không cấu hình danh sách vai trò, mọi người dùng đã xác thực được coi là đủ điều kiện theo cơ chế hiển thị này. Hãy kiểm tra cả chế độ lẫn danh sách vai trò thực tế.

### “always sẽ bỏ qua Spring Security”

Trong thí nghiệm, tài khoản chỉ có `HEALTH_DETAILS` vẫn bị chặn khi dùng `always`. Chỉ những yêu cầu qua được quy tắc truy cập mới nhận phản hồi endpoint theo chính sách đó.

### “Không thấy chi tiết thì cần nới quyền gọi endpoint”

Trước khi đổi quy tắc truy cập, kiểm tra mã phản hồi. Nếu yêu cầu đã thành công và chỉ thiếu dữ liệu, cần xem `show-details`, `show-components`, vai trò, cấu hình nhóm hoặc quy tắc che dữ liệu tương ứng.

### “Bản tổng quát và bản chi tiết đều 200 nên không cần kiểm tra thân phản hồi”

Một kiểm thử quyền dữ liệu phải xác nhận trường nào có mặt và trường nào bị ẩn. Tối thiểu nên kiểm tra không có `components.lab.details` cho `reader`, có dữ liệu giả lập đúng cho `operator`, và tài khoản thiếu quyền URL không nhận phản hồi thành công.

## 10. Bài thực hành

1. Dùng ba tài khoản gọi cùng health; giải thích kết quả bằng cả quy tắc Java và chính sách YAML.
2. Đổi cả hai thuộc tính hiển thị sang `never`; xác nhận quyền gọi URL không đổi nhưng dữ liệu của `operator` được rút gọn.
3. Đổi sang `always`; xác nhận `reader` được thấy chi tiết còn tài khoản `details` vẫn bị chặn.
4. Khôi phục `when-authorized`, bỏ cấu hình `roles`; quan sát vì sao `reader` được thấy chi tiết.
5. Bật thành phần nhưng tắt chi tiết; giải thích sự khác nhau giữa `components.lab.status` và `components.lab.details`.

Khi mô tả quyền của một người gọi, hãy ghi đủ: **được xác thực bằng cách nào, được gọi endpoint nào và được thấy phần dữ liệu nào**. Ba thông tin đó giúp đánh giá đúng hành vi mà một trạng thái “đã đăng nhập” đơn lẻ không thể thể hiện.
