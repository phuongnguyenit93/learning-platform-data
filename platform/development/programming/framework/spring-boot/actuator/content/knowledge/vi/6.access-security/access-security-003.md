# Phân tách quy tắc bảo mật API nghiệp vụ và endpoint quản trị

## 1. Hai nhóm chức năng, hai chính sách truy cập

API nghiệp vụ phục vụ chức năng của ứng dụng: đặt hàng, đọc hóa đơn, cập nhật hồ sơ. Endpoint quản trị của Spring Boot Actuator cung cấp khả năng vận hành: xem sức khỏe, số liệu, thông tin ứng dụng hoặc điều chỉnh một số thành phần khi endpoint tương ứng được sử dụng.

Hai nhóm này có đối tượng sử dụng và mức độ ảnh hưởng khác nhau. Một tài khoản được xem đơn hàng không vì thế được xem thông tin vận hành; một tài khoản trực hệ thống cũng không tự động có quyền đọc dữ liệu nghiệp vụ.

**Phân tách quy tắc bảo mật** nghĩa là xác định rõ:

- Yêu cầu nào thuộc API nghiệp vụ, yêu cầu nào thuộc quản trị.
- Mỗi nhóm chấp nhận cách xác thực nào.
- Sau khi xác thực, người gọi cần quyền gì.
- Yêu cầu ngoài các nhóm đã định nghĩa được xử lý thế nào.

Bài này dùng **Spring Boot 3.3.x, Spring Security 6.3 và ứng dụng Servlet/Spring MVC**. Ví dụ chạy với JDK 21 và Spring Boot 3.3.0. Với WebFlux, mô hình chọn chuỗi vẫn hữu ích nhưng kiểu cấu hình là `SecurityWebFilterChain` và `ServerHttpSecurity`; không chép nguyên các import Servlet sang ứng dụng reactive.

### Chính sách sẽ xây dựng

Ví dụ có hai tài khoản độc lập về vai trò:

- `apiuser` có vai trò `API_USER`, dùng API nghiệp vụ.
- `opsuser` có vai trò `OPS`, dùng endpoint quản trị.
- Người chưa xác thực chỉ được xem health ở mức tối thiểu.

| Tài nguyên | Chưa xác thực | Có API_USER | Có OPS |
| --- | --- | --- | --- |
| Health tối thiểu | Cho phép | Cho phép | Cho phép |
| Info và các endpoint Actuator khác được công bố | Từ chối | Từ chối | Cho phép |
| API nghiệp vụ `/api/**` | Từ chối | Cho phép | Từ chối |
| Đường dẫn ngoài phạm vi đã định nghĩa | Từ chối | Từ chối | Từ chối |

Vai trò `OPS` trong ví dụ không phải một “siêu quyền” ngầm định. Nếu một người cần cả hai nhóm chức năng, việc cấp cả hai vai trò phải là quyết định rõ ràng.

## 2. Phân biệt ba lớp quyết định

### 2.1. Endpoint có được công bố hay không?

`management.endpoints.web.exposure.include` lựa chọn endpoint đưa ra HTTP. Nó không khai báo ai có quyền gọi. Ngược lại, `permitAll()` không tự tạo một endpoint chưa được bật hoặc chưa được công bố.

Trong Spring Boot 3.3, khi tự khai báo `SecurityFilterChain`, cấu hình bảo mật web mặc định của Boot nhường quyền cho cấu hình của ứng dụng. Không được giả định rằng Boot sẽ tự thêm một chuỗi bảo vệ phần đường dẫn mà cấu hình mới bỏ sót. [Bảo mật endpoint Actuator trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

### 2.2. Chuỗi bộ lọc nào xử lý yêu cầu?

`SecurityFilterChain` là một chuỗi các bộ lọc bảo mật. `FilterChainProxy` kiểm tra những chuỗi đã đăng ký theo thứ tự ưu tiên và chọn **chuỗi đầu tiên khớp yêu cầu**.

```text
Yêu cầu HTTP
  |
  +-- Khớp endpoint Actuator? ---- có --> Chuỗi quản trị
  |                               không
  +-- Khớp /api/**? ------------- có --> Chuỗi API nghiệp vụ
  |                               không
  +-----------------------------------> Chuỗi cuối: từ chối
```

Nếu chuỗi quản trị từ chối người gọi vì thiếu vai trò, yêu cầu không được chuyển tiếp sang chuỗi API để “thử lại”. Các chuỗi không cộng dồn thành nhiều lớp phân quyền cho cùng một lần chọn chuỗi. [Cơ chế chọn SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-securityfilterchain).

### 2.3. Quy tắc nào áp dụng bên trong chuỗi?

| API cấu hình | Vai trò |
| --- | --- |
| `http.securityMatcher(...)` | Xác định yêu cầu nào thuộc phạm vi của cả chuỗi |
| `authorizeHttpRequests(...).requestMatchers(...)` | Chọn quy tắc phân quyền bên trong chuỗi đã được chọn |
| `anyRequest()` bên trong phân quyền | Phần yêu cầu còn lại trong phạm vi của chuỗi đó |
| `@Order` trên bean chuỗi | Thứ tự xét các chuỗi; số nhỏ được xét trước |

Ví dụ, `anyRequest().authenticated()` bên trong một chuỗi có `securityMatcher("/api/**")` chỉ áp dụng cho yêu cầu thuộc `/api/**`. Nó không tự bảo vệ đường dẫn quản trị hoặc phần còn lại của ứng dụng.

Nếu không chuỗi nào khớp, yêu cầu đó không được các chuỗi Spring Security bảo vệ. Vì vậy, ví dụ dùng một chuỗi cuối không giới hạn `securityMatcher`, với chính sách `denyAll()`. [Phân biệt securityMatcher và requestMatchers](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_choosing_securitymatcher_or_requestmatchers).

## 3. Nhận diện Actuator bằng EndpointRequest

Viết cứng `"/actuator/**"` khiến cấu hình phụ thuộc vào tiền tố URL. Khi tiền tố đổi thành `/manage`, quy tắc cũ có thể không còn nhận diện đúng yêu cầu.

Spring Boot cung cấp `EndpointRequest` để tạo bộ so khớp theo vị trí endpoint thực tế:

```java
EndpointRequest.toAnyEndpoint()
EndpointRequest.to(HealthEndpoint.class)
```

- `toAnyEndpoint()` nhận diện các endpoint Actuator được cung cấp qua web, gồm cả trang liên kết khám phá ở đường dẫn gốc quản trị.
- `to(HealthEndpoint.class)` chọn endpoint health; quy tắc này còn có thể khớp các đường dẫn con của health, gồm nhóm sức khỏe.
- Bộ so khớp endpoint không phải một quy tắc bảo vệ mọi URL tùy ý có cùng tiền tố. Đường dẫn không thuộc endpoint được nhận diện cần được chuỗi còn lại xử lý.

Đó là lý do có cả bộ so khớp Actuator và chuỗi cuối trong thiết kế. [API EndpointRequest của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

Đối với chính sách health công khai, phải quyết định phạm vi thật sự muốn mở. Ví dụ dưới đây chủ động cho phép health và các đường dẫn con, đồng thời ẩn chi tiết. Nếu chỉ muốn công khai một nhóm kiểm tra cụ thể, cần thu hẹp bộ so khớp tương ứng và kiểm thử riêng các nhóm còn lại.

## 4. Dựng ứng dụng minh họa

### 4.1. Dependency và cấu hình endpoint

Dùng dự án Gradle có Wrapper 8.5, JDK 21. Một `build.gradle` tối thiểu:

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

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-security-demo'
```

Tệp `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      show-components: never
```

Chỉ health và info được chọn công bố trong thí nghiệm. Không dùng `include: "*"` để kiểm tra việc phân quyền. Health ở trạng thái khỏe mạnh chỉ trả thông tin tổng quát; các chi tiết thành phần không được hiển thị trong cấu hình này.

### 4.2. API nghiệp vụ

Tệp `src/main/java/example/SplitSecurityApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SplitSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SplitSecurityApplication.class, args);
    }

    @GetMapping("/api/orders")
    public String orders() {
        return "orders-ok";
    }
}
```

API `GET /api/orders` trả chuỗi cố định để tập trung quan sát phân quyền. Đây là API minh họa, chưa thực hiện việc truy vấn đơn hàng.

### 4.3. Ba chuỗi bảo mật

Tệp `src/main/java/example/SecurityConfig.java`:

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain managementSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("API_USER"))
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().denyAll())
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var api = User.withUsername("apiuser")
            .password(encoder.encode("api-lab-pass"))
            .roles("API_USER")
            .build();
        var ops = User.withUsername("opsuser")
            .password(encoder.encode("ops-lab-pass"))
            .roles("OPS")
            .build();
        return new InMemoryUserDetailsManager(api, ops);
    }
}
```

Hai mật khẩu trong ví dụ chỉ dùng cho thí nghiệm cục bộ. `BCryptPasswordEncoder` mã hóa trước khi lưu người dùng trong bộ nhớ. Khi xây dựng hệ thống thực tế, thay phần tài khoản minh họa bằng nguồn danh tính và cách cung cấp thông tin xác thực của hệ thống; HTTP Basic cần được bảo vệ bằng HTTPS khi truyền qua mạng.

### 4.4. Đọc cấu hình theo đúng phạm vi

**Chuỗi quản trị, thứ tự 1:**

- Chỉ khớp yêu cầu Actuator.
- Cho phép health mà không yêu cầu đăng nhập.
- Những yêu cầu còn lại trong chuỗi cần vai trò `OPS`.
- Bật HTTP Basic cho chính chuỗi này.

**Chuỗi API, thứ tự 2:**

- Chỉ khớp `/api/**`.
- Yêu cầu vai trò `API_USER`.
- Tự cấu hình HTTP Basic; nó không mượn cấu hình xác thực của chuỗi thứ nhất hoặc chuỗi cuối.

**Chuỗi cuối, thứ tự 3:**

- Không đặt `securityMatcher`, nên nhận phần yêu cầu chưa được các chuỗi trước nhận.
- Từ chối mọi yêu cầu trong phần này.
- Bật HTTP Basic để cách phản hồi khi chưa xác thực nhất quán với thí nghiệm.

`roles("OPS")` tạo authority `ROLE_OPS`; `hasRole("OPS")` kiểm tra authority đó. Không truyền `"ROLE_OPS"` vào `hasRole`. Nếu làm việc trực tiếp với chuỗi authority đầy đủ, dùng `hasAuthority("ROLE_OPS")`.

Ví dụ chia sẻ một `UserDetailsService` giữa các chuỗi để dễ tái hiện. Phân tách chuỗi không tự tạo hai kho tài khoản, hai nhà phát hành token hoặc hai miền danh tính độc lập.

## 5. Chạy và quan sát cả trường hợp được phép lẫn bị chặn

### 5.1. Khởi động ứng dụng

Trong PowerShell, tại thư mục dự án:

```powershell
.\gradlew.bat bootRun
```

Trong Bash dùng `./gradlew bootRun`. Ứng dụng cần dependency Spring nên dùng quy trình build của dự án, không gọi `javac` trực tiếp mà thiếu classpath.

Mở terminal PowerShell khác và chạy từng lệnh sau. Các mã phản hồi giả định ứng dụng minh họa đang chạy đúng cấu hình, không có bộ lọc bổ sung, health khỏe mạnh và không gửi cookie hoặc thông tin xác thực ngoài những gì lệnh thể hiện.

### 5.2. Health không cần thông tin xác thực

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

Kết quả:

```text
200
```

Nếu xem thân phản hồi, ứng dụng khỏe mạnh trả `{"status":"UP"}`. Một hệ thống có thành phần kiểm tra sức khỏe báo lỗi có thể trả mã trạng thái khác; quyền truy cập và trạng thái sức khỏe là hai vấn đề riêng.

### 5.3. Tài khoản API gọi đúng nhóm chức năng

```powershell
curl.exe -s -u "apiuser:api-lab-pass" http://localhost:8080/api/orders
```

Thân phản hồi:

```text
orders-ok
```

Khi tài khoản đó gọi info quản trị:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "apiuser:api-lab-pass" http://localhost:8080/actuator/info
```

Kết quả:

```text
403
```

Thông tin xác thực đúng không thay thế vai trò quản trị.

### 5.4. Tài khoản vận hành cũng bị giới hạn phạm vi

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "opsuser:ops-lab-pass" http://localhost:8080/actuator/info
```

Kết quả:

```text
200
```

Nhưng khi gọi API nghiệp vụ:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "opsuser:ops-lab-pass" http://localhost:8080/api/orders
```

Kết quả:

```text
403
```

Nếu yêu cầu thật sự cần cho phép vận hành gọi nghiệp vụ, phải thể hiện điều đó bằng việc cấp quyền hoặc thay chính sách; không nên dựa vào tên vai trò để suy ra quyền.

### 5.5. Ma trận kiểm tra đầy đủ

| Yêu cầu GET | Không gửi xác thực | apiuser | opsuser |
| --- | --- | --- | --- |
| `/actuator/health` | 200 khi khỏe mạnh | 200 khi khỏe mạnh | 200 khi khỏe mạnh |
| `/actuator/info` | 401 | 403 | 200 |
| `/actuator` — trang liên kết | 401 | 403 | 200 |
| `/api/orders` | 401 | 200 | 403 |
| `/unmapped` — đường dẫn ngoài hai nhóm | 401 | 403 | 403 |

Trong thí nghiệm:

- **401** xuất hiện khi cần xác thực mà yêu cầu không có thông tin hợp lệ.
- **403** xuất hiện khi người dùng đã xác thực nhưng không đáp ứng chính sách.
- Một yêu cầu ghi cũng có thể nhận **403 do CSRF** trước bước phân quyền; không được kết luận mọi 403 đều do sai vai trò.

`permitAll()` là quyết định phân quyền. Nó không yêu cầu bộ lọc xác thực bỏ qua thông tin xác thực sai: gửi mật khẩu sai bằng HTTP Basic tới health vẫn có thể nhận 401, dù gọi health không kèm thông tin xác thực được cho phép.

## 6. Kiểm tra độ bền khi đổi vị trí quản trị

### 6.1. Đổi tiền tố thành /manage

Thêm vào nhánh `management.endpoints.web` của YAML:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

Đây là phần cấu hình thay thế cho nhánh tương ứng; không tạo khóa `management` trùng lặp trong cùng một tài liệu YAML. Giữ nguyên cấu hình health đã có rồi khởi động lại.

Đổi các URL quản trị trong ma trận sang `/manage/health`, `/manage/info` và `/manage`. Quy tắc vai trò vẫn phải giữ nguyên mà không sửa chuỗi Java, vì `EndpointRequest` nhận diện vị trí endpoint thay vì phụ thuộc vào chuỗi `"/actuator/**"`. [Tích hợp EndpointRequest với đường dẫn quản trị](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#mvc-security).

### 6.2. Khi tiền tố quản trị nằm trong tiền tố API

Thử `management.endpoints.web.base-path=/api/manage`.

Lúc này, `/api/manage/info` vừa nằm dưới `/api/**`, vừa là vị trí endpoint info. Do chuỗi Actuator có `@Order(1)`, yêu cầu được xử lý bởi chuỗi quản trị:

- `apiuser` vẫn bị từ chối.
- `opsuser` vẫn được gọi info.
- Yêu cầu không tiếp tục sang chuỗi API sau khi chuỗi quản trị đã khớp.

Đây là một phép kiểm tra hữu ích cho **thứ tự ưu tiên khi các phạm vi giao nhau**. Nếu đảo thứ tự để một chuỗi API quá rộng chạy trước, endpoint quản trị có thể bị áp dụng nhầm chính sách.

Khi triển khai thật, nên chọn đường dẫn thể hiện rõ hai nhóm chức năng. Phép thử giao nhau giúp phát hiện lỗi cấu hình, không phải lý do phải cố ý đặt chúng chồng lên nhau.

### 6.3. Đổi cổng không thay thế phân quyền

Cổng quản trị riêng, địa chỉ lắng nghe và quy tắc mạng giúp kiểm soát đường truy cập. Chúng không tự tạo yêu cầu `OPS` hoặc loại bỏ quyền của người dùng nghiệp vụ.

Ví dụ chạy cùng một cổng để quan sát cơ chế chọn chuỗi. Nếu chuyển sang `management.server.port` riêng hoặc thêm proxy, cần kiểm thử lại trên cổng và đường dẫn triển khai thật, bao gồm cả ứng dụng chính và ngữ cảnh quản trị. Không suy ra rằng kiểm tra cùng cổng đã chứng minh mọi cấu hình triển khai khác.

Các chuỗi Servlet này bảo vệ yêu cầu HTTP đi qua chúng. Chúng không tự phân quyền cho JMX; nếu sử dụng JMX, phải xác định chính sách của kênh đó riêng.

## 7. CSRF, phiên và cách xác thực không được vô tình dùng chung

Trong ví dụ, cả ba chuỗi đặt `SessionCreationPolicy.STATELESS`: Spring Security không dùng phiên HTTP để lấy hoặc lưu `SecurityContext` theo chính sách này. Mỗi yêu cầu bảo vệ bằng HTTP Basic cần cung cấp thông tin xác thực phù hợp.

**Stateless không đồng nghĩa với không cần CSRF.** Trình duyệt có thể tự gửi thông tin xác thực trong một số cơ chế, gồm HTTP Basic. Vì vậy ví dụ giữ nguyên bảo vệ CSRF mặc định, tập trung vào các yêu cầu GET để quan sát vai trò. [CSRF và ứng dụng trình duyệt không lưu phiên](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html#csrf-and-stateless-browser-applications).

Với yêu cầu thay đổi dữ liệu, chẳng hạn một thao tác ghi của Actuator khi endpoint đó được bật và công bố, người dùng có đúng vai trò vẫn cần đáp ứng chính sách CSRF đang áp dụng. Không tắt CSRF trên toàn ứng dụng chỉ để làm mất một lỗi 403. [Bảo vệ CSRF trong ứng dụng Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

Nếu mở rộng cấu hình thành API dùng Bearer token và quản trị dùng HTTP Basic:

1. Đặt cơ chế xác thực token trong chuỗi API.
2. Đặt HTTP Basic hoặc cơ chế quản trị được chọn trong chuỗi Actuator.
3. Xem xét CSRF, phiên, CORS và cách phản hồi lỗi trong từng chuỗi.
4. Kiểm thử rằng thông tin xác thực dành cho nhóm này không được vô tình chấp nhận như quyền của nhóm kia.

Chuỗi được chọn phải có đủ cấu hình cần thiết. Cấu hình `httpBasic()` ở chuỗi cuối không cung cấp HTTP Basic cho những yêu cầu đã được chuỗi Actuator nhận trước đó.

Nếu cùng cơ chế xác thực, cùng chính sách phiên và cùng các yêu cầu bảo vệ khác, một chuỗi với các quy tắc phân quyền riêng cũng có thể đáp ứng thiết kế. Nhiều chuỗi hữu ích khi cần tách cả phạm vi bộ lọc và cách xử lý bảo mật, không phải vì cứ có hai vai trò thì bắt buộc có hai chuỗi.

## 8. Những lỗi cấu hình cần nhận ra

### Chuỗi quản trị thiếu securityMatcher

Nếu chuỗi có `@Order(1)` chỉ đặt `anyRequest().hasRole("OPS")` mà không giới hạn phạm vi, nó có thể khớp mọi yêu cầu trước chuỗi nghiệp vụ. Khi đó người dùng API bị yêu cầu vai trò quản trị.

Cần kiểm tra bộ so khớp của **cả chuỗi**, không chỉ đọc quy tắc bên trong `authorizeHttpRequests`.

### Chỉ dùng authenticated cho toàn bộ Actuator

`authenticated()` chấp nhận mọi danh tính đã xác thực đáp ứng cơ chế của chuỗi. Trong ví dụ, điều đó cho phép `apiuser` đi qua quy tắc quản trị dù người này không có vai trò `OPS`.

Phân biệt xác thực “người gọi là ai” với phân quyền “người đó được làm gì”.

### Đặt chuỗi khớp mọi yêu cầu lên trước

Một chuỗi nhận mọi yêu cầu đặt trước chuỗi Actuator sẽ che khuất chuỗi Actuator. Tên phương thức `managementSecurity` không tạo độ ưu tiên; phạm vi và `@Order` mới quyết định việc chọn chuỗi.

### Chỉ bảo vệ Actuator rồi bỏ quên phần còn lại

Sau khi tự khai báo chuỗi Actuator, không trông chờ cấu hình mặc định tự bảo vệ API nghiệp vụ. Phải có chuỗi hoặc quy tắc xử lý API và những đường dẫn còn lại.

Không dùng `web.ignoring()` để thể hiện health công khai nếu mục tiêu chỉ là không yêu cầu đăng nhập. `permitAll()` vẫn cho yêu cầu đi qua cơ chế bảo mật của chuỗi; bỏ qua bộ lọc là quyết định khác.

### Hiểu nhầm mã phản hồi của endpoint chưa công bố

Trong ví dụ, `env` không nằm trong danh sách công bố. Yêu cầu `/actuator/env` có thể bị chuỗi cuối từ chối trước khi đến bước tìm handler. Vì vậy, thấy 401 hoặc 403 không chứng minh endpoint đó đã được công bố.

Muốn xác định nguyên nhân, kiểm tra riêng: cấu hình bật endpoint, tập công bố, chuỗi khớp, kết quả xác thực, quyền và các bộ lọc bảo vệ khác.

## 9. Bài thực hành kiểm tra ranh giới

1. Giữ nguyên hai tài khoản, gọi cả API nghiệp vụ và info bằng từng tài khoản. Xác nhận mỗi tài khoản chỉ được sử dụng nhóm chức năng đã cấp.
2. Đổi tiền tố quản trị thành `/manage`, lặp lại cùng ma trận và xác nhận không cần sửa matcher Java.
3. Thử tiền tố `/api/manage` để quan sát vai trò của thứ tự chuỗi khi hai phạm vi giao nhau.
4. Trên bản cấu hình thí nghiệm riêng, thay `hasRole("OPS")` bằng `authenticated()`, rồi kiểm tra tài khoản API đã đi qua quy tắc quản trị như thế nào. Khôi phục chính sách sau khi quan sát.
5. Giải thích vì sao yêu cầu đã khớp chuỗi quản trị và bị từ chối sẽ không được chuyển sang chuỗi API.

Khi đánh giá một cấu hình, cần chỉ ra được **chuỗi nào nhận yêu cầu, cơ chế nào xác thực người gọi và quy tắc nào quyết định quyền truy cập**. Kiểm tra cả trường hợp bị chặn giúp chứng minh ranh giới giữa API nghiệp vụ và endpoint quản trị.
