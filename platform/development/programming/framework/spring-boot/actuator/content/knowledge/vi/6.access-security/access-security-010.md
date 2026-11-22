# Che dữ liệu bằng show-values, roles và SanitizingFunction

## 1. Che dữ liệu để phục vụ chẩn đoán có giới hạn

Khi ứng dụng gặp sự cố, người vận hành có thể cần biết một cấu hình đã được nạp từ đâu, giá trị nào đang có hiệu lực hoặc một nhóm thuộc tính đã được liên kết đúng hay chưa. Nhưng phản hồi chẩn đoán cũng có thể chứa mật khẩu, khóa truy cập và thông tin nội bộ.

Trong Actuator, **che giá trị (sanitization)** là thay giá trị trong dữ liệu trả ra bằng một biểu diễn an toàn hơn, thường là `******`. Ứng dụng vẫn có thể sử dụng giá trị gốc ở bên trong.

Có ba câu hỏi cần tách biệt:

1. **Ai được gọi endpoint?** Đây là quyết định kiểm soát truy cập.
2. **Người gọi được xem giá trị gốc hay chỉ giá trị đã che?** Đây là chính sách `show-values`, có thể kết hợp `roles`.
3. **Có trường nào phải che ngay cả khi người gọi được xem giá trị gốc?** Đây là nơi dùng `SanitizingFunction`.

Một người có thể gọi endpoint thành công với mã 200 nhưng chỉ nhận các giá trị đã che. Ngược lại, một người có vai trò xem giá trị gốc vẫn có thể bị chặn ở lớp HTTP nếu chưa có quyền gọi endpoint.

Bài thực hành dùng **Java 21, Spring Boot 3.3.13 và Spring MVC** để kiểm chứng ba câu hỏi này. Phiên bản 3.3.13 được cố định cho ví dụ thuộc dòng 3.3.x, không hàm ý đó là phiên bản mới nhất hay lựa chọn triển khai sản xuất hiện tại.

## 2. Cần che cái gì, và cơ chế này không làm gì?

`env` mô tả dữ liệu từ môi trường cấu hình Spring; `configprops` mô tả các bean thuộc nhóm `@ConfigurationProperties`. Đó là hai góc quan sát khác nhau của cấu hình.

Ví dụ:

```yaml
demo:
  region: lab-east
  api-token: synthetic-token-not-real
```

Ta muốn người có quyền chẩn đoán thấy `region=lab-east`, nhưng vẫn chỉ thấy `api-token=******`. Chuỗi token trong bài hoàn toàn là dữ liệu giả.

| Cách xử lý | Dữ liệu trả ra | Giá trị bên trong ứng dụng |
| --- | --- | --- |
| Che giá trị | Có thể vẫn có tên trường, thay giá trị bằng dấu che | Giữ nguyên |
| Bỏ trường khỏi phản hồi | Không trả trường đó | Có thể vẫn giữ nguyên |
| Mã hóa dữ liệu lưu trữ | Phụ thuộc nơi lưu và cách giải mã | Có thể được giải mã để sử dụng |
| Chặn truy cập endpoint | Người gọi không nhận được tài liệu endpoint | Không thay đổi |

Che giá trị không có nghĩa tên thuộc tính, tên nguồn, vị trí khai báo hay các siêu dữ liệu khác đều biến mất. Nó cũng không tự che cùng bí mật trong log, thông báo lỗi, endpoint tự viết hoặc heap dump.

Vì vậy, việc phản hồi chứa `******` không chứng minh bí mật đã được mã hóa, đã bị xóa khỏi bộ nhớ hay không còn xuất hiện ở nơi nào khác.

## 3. show-values chọn mức hiển thị ban đầu

Trong dòng Spring Boot 3.3, các endpoint hỗ trợ chính sách che như `env`, `configprops` và `quartz` có thể dùng `show-values`. Giá trị mặc định là `never`; các giá trị được che bằng `******`. [Chính sách che giá trị của Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

Với `env` và `configprops`, các thuộc tính sử dụng trong bài là:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Hai endpoint có cấu hình riêng. Đổi chính sách của `env` không tự đổi chính sách của `configprops`.

| Chế độ | Khi yêu cầu đã được phép gọi endpoint | Giá trị không thuộc quy tắc che bổ sung |
| --- | --- | --- |
| `never` | Không phụ thuộc vai trò xem giá trị | Bị che |
| `when-authorized` | Cần thỏa điều kiện xem giá trị của endpoint | Hiện bản gốc nếu được phép; nếu không thì che |
| `always` | Không yêu cầu thêm vai trò xem giá trị | Có thể hiện bản gốc |

Cột cuối cố ý nói “không thuộc quy tắc che bổ sung”. Một `SanitizingFunction` vẫn có thể che dữ liệu ở chế độ `always` hoặc khi người gọi đã được phép xem giá trị gốc.

`always` không tự cho phép người ngoài gọi HTTP endpoint. Tuy nhiên, nếu endpoint vốn đã được công khai, người gọi công khai cũng có thể nhận các giá trị không được hàm che bảo vệ. Không dùng `always` như một cách sửa nhanh lỗi chẩn đoán trong môi trường thật.

## 4. roles kiểm soát việc xem giá trị, không mở cửa HTTP

Cấu hình ví dụ:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: CONFIG_VIEWER
    configprops:
      show-values: when-authorized
      roles: CONFIG_VIEWER
```

Đối với HTTP, khi dùng `when-authorized`, người gọi cần được xác thực và thỏa vai trò xem giá trị mà endpoint yêu cầu. Nếu không cấu hình danh sách vai trò, mặc định người đã xác thực được coi là đủ điều kiện xem giá trị. Với JMX, cơ chế này coi người gọi là được phép; không suy ra rằng phân quyền HTTP cũng bảo vệ JMX. [Điều kiện xem giá trị qua HTTP và JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

Nếu có nhiều vai trò xem giá trị, một vai trò phù hợp là đủ; đó không phải yêu cầu người gọi phải có tất cả vai trò cùng lúc.

Trong cách ánh xạ vai trò mặc định của Spring Security dùng ở bài:

- `roles("CONFIG_VIEWER")` tạo quyền `ROLE_CONFIG_VIEWER`.
- Cấu hình endpoint dùng tên vai trò `CONFIG_VIEWER`.
- Quyền gọi endpoint sẽ được cấu hình riêng bằng vai trò `ACTUATOR_READER`.

Ta thiết kế ba danh tính độc lập:

| Tài khoản | Vai trò | Được gọi endpoint cấu hình? | Được xem giá trị gốc khi dùng when-authorized? |
| --- | --- | --- | --- |
| `reader` | `ACTUATOR_READER` | Có | Không |
| `viewer` | `ACTUATOR_READER`, `CONFIG_VIEWER` | Có | Có, trừ trường luôn phải che |
| `outsider` | `CONFIG_VIEWER` | Không | Không có phản hồi cấu hình để xem |

Đây là các vai trò do bài thực hành tự đặt. Spring Boot không tự tạo những tài khoản này.

Vai trò xem dữ liệu không thay thế `SecurityFilterChain`. Nếu một người cần cả quyền gọi và quyền xem bản gốc, phải cấu hình rõ cả hai điều kiện. Nếu dùng cơ chế token hoặc bộ ánh xạ vai trò khác, cần kiểm tra authority thực tế thay vì chỉ nhìn tên vai trò trong cấu hình.

## 5. SanitizingFunction đặt quy tắc che bổ sung

### 5.1. Hợp đồng dữ liệu

Một bean `SanitizingFunction` nhận `SanitizableData` và trả lại `SanitizableData`.

Những thành phần cần biết:

| Thành phần | Ý nghĩa khi viết hàm |
| --- | --- |
| `getKey()` | Tên khóa mà endpoint đưa vào quá trình che |
| `getValue()` | Giá trị kiểu `Object`, không nhất thiết là chuỗi |
| `getPropertySource()` | Nguồn thuộc tính nếu có; có thể là `null` |
| `withSanitizedValue()` | Tạo dữ liệu mới với giá trị `******` |
| `withValue(value)` | Tạo dữ liệu mới với giá trị thay thế do ta chọn |

`withSanitizedValue()` và `withValue(...)` không ghi đè thuộc tính nguồn; chúng tạo một đối tượng mô tả mới cho đầu ra. [Hợp đồng SanitizableData của phiên bản 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/SanitizableData.java).

Khi không áp dụng quy tắc, trả lại `data`. Không trả `null` để biểu thị “bỏ qua”. Không ép mọi giá trị thành `String`, và không ghi log giá trị gốc để theo dõi hoạt động của hàm.

### 5.2. Luồng quyết định trong Spring Boot 3.3.13

Có thể mô tả hành vi bằng mã giả:

```text
Giá trị gốc là null?
    -> Trả null.

Không được hiển thị giá trị gốc?
    -> Trả dấu che.

Được hiển thị giá trị gốc?
    -> Thử các SanitizingFunction theo danh sách đã được cung cấp.
    -> Khi một hàm làm giá trị khác giá trị gốc, trả ngay kết quả đó.
    -> Nếu không có hàm thay đổi giá trị, trả giá trị gốc.
```

Hai hệ quả dễ bị bỏ sót:

1. Ở nhánh che toàn bộ, các hàm tùy chỉnh không cần được gọi. Không dùng số lần hàm chạy để suy ra toàn bộ số trường đã bị che.
2. Nhiều hàm không mặc nhiên tạo thành một chuỗi biến đổi mà tất cả đều chạy đến cuối. Giá trị bị thay đổi đầu tiên có thể kết thúc xử lý.

Đó là hành vi trực tiếp của `Sanitizer` ở phiên bản được dùng trong bài. [Mã nguồn Sanitizer 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/Sanitizer.java).

Nếu nhiều quy tắc cần phối hợp, một hàm kết hợp với thứ tự ưu tiên rõ ràng thường dễ kiểm chứng hơn việc trông chờ mọi bean đều chạy. Việc tạo đối tượng `SanitizableData` mới nhưng giữ nguyên giá trị cũng không tự có nghĩa đã che dữ liệu.

### 5.3. Không dựa vào tên “password” để mặc nhiên an toàn

Khi cho phép xem giá trị gốc, đừng giả định một khóa có chữ `password` hoặc `token` sẽ tự động được bảo vệ bởi cơ chế nhận diện bí mật hoàn hảo.

Trong phiên bản 3.3.13, một `Sanitizer` không có hàm tùy chỉnh sẽ trả giá trị gốc nếu đối số cho phép xem giá trị là `true`. Bài có kiểm thử riêng cho trường hợp này.

Do đó, khi chuyển từ che toàn bộ sang `when-authorized` hoặc `always`, phải rà soát quy tắc che những trường cần bảo vệ cho cả người đã được phép xem. Không chỉ kiểm tra rằng các trường bình thường đã hiện lại.

## 6. Dự án thực hành độc lập

Dự án gồm các tệp sau:

```text
actuator-sanitizing-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/sanitizing/
    │   │   ├── MaskingApplication.java
    │   │   ├── DemoSettings.java
    │   │   ├── DataMaskingConfig.java
    │   │   └── EndpointSecurity.java
    │   └── resources/application.yml
    └── test/java/com/example/sanitizing/
        ├── SanitizingHttpTest.java
        └── SanitizerContractTest.java
```

Đây là ứng dụng Spring Boot cần dựng bằng Maven với JDK 21. Các lớp phụ thuộc Spring, nên không chạy riêng bằng `javac TenLop.java`. Lần dựng đầu cần truy cập kho Maven.

### 6.1. Thư viện phụ thuộc: `pom.xml`

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
    <artifactId>actuator-sanitizing-lab</artifactId>
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

### 6.2. Cấu hình: `src/main/resources/application.yml`

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
        include: env,configprops
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    env:
      enabled: true
      show-values: when-authorized
      roles: CONFIG_VIEWER
    configprops:
      enabled: true
      show-values: when-authorized
      roles: CONFIG_VIEWER

demo:
  region: lab-east
  api-token: synthetic-token-not-real

lab:
  auth:
    reader-password: ${READER_PASSWORD}
    viewer-password: ${VIEWER_PASSWORD}
    outsider-password: ${OUTSIDER_PASSWORD}
```

Cấu hình này chỉ bật và đưa hai endpoint `env`, `configprops` ra HTTP. Chúng là endpoint chẩn đoán nhạy cảm; trong bài, ứng dụng chỉ lắng nghe trên `127.0.0.1`, có xác thực và có phân quyền riêng.

Tắt JMX và loại toàn bộ endpoint khỏi exposure JMX giúp bài không có thêm kênh quản lý ngoài HTTP. Nếu hệ thống thực tế sử dụng JMX, cần thiết kế bảo vệ kênh đó riêng; không dựa vào `roles` của HTTP.

Ba biến môi trường chứa mật khẩu phải được cung cấp trước khi chạy ứng dụng. Riêng các giá trị `demo.region` và `demo.api-token` là dữ liệu giả để quan sát.

### 6.3. Điểm khởi động: `MaskingApplication.java`

Đặt tại `src/main/java/com/example/sanitizing/MaskingApplication.java`.

```java
package com.example.sanitizing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DemoSettings.class)
public class MaskingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MaskingApplication.class, args);
    }
}
```

### 6.4. Nhóm thuộc tính: `DemoSettings.java`

Đặt tại `src/main/java/com/example/sanitizing/DemoSettings.java`.

```java
package com.example.sanitizing;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public class DemoSettings {
    private String region;
    private String apiToken;

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getApiToken() {
        return apiToken;
    }

    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }
}
```

`demo.api-token` trong nguồn cấu hình được liên kết với thuộc tính Java `apiToken`. Nhờ lớp này, ta có thể quan sát cùng một dữ liệu qua `env` và `configprops`.

Không thêm một endpoint trả token gốc để “chứng minh” ứng dụng vẫn nhận được token. Kiểm thử có thể đọc bean bên trong ngữ cảnh ứng dụng mà không tạo một đường lộ bí mật mới.

### 6.5. Quy tắc che: `DataMaskingConfig.java`

Đặt tại `src/main/java/com/example/sanitizing/DataMaskingConfig.java`.

```java
package com.example.sanitizing;

import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DataMaskingConfig {
    @Bean
    SanitizingFunction hideLabSecrets() {
        return data -> {
            if (data.getKey() == null || data.getValue() == null) {
                return data;
            }
            String key = data.getKey()
                    .toLowerCase(Locale.ROOT)
                    .replaceAll("[^a-z0-9]", "");
            if (key.endsWith("apitoken") || key.endsWith("password")) {
                return data.withSanitizedValue();
            }
            return data;
        };
    }
}
```

Hàm có ba lựa chọn chủ động:

1. Không xử lý giá trị `null` và không giả định luôn có tên khóa.
2. Chuẩn hóa tên khóa để cùng nhận diện `demo.api-token`, `apiToken` và `DEMO_API_TOKEN`.
3. Che toàn bộ giá trị khi tên chuẩn hóa kết thúc bằng `apitoken` hoặc `password`; trả nguyên dữ liệu đối với khóa khác.

`Locale.ROOT` tránh việc chuẩn hóa chữ cái phụ thuộc ngôn ngữ mặc định của máy chạy. Hàm không cần đọc giá trị gốc để quyết định, không truy cập mạng và không ghi log bí mật.

Đây là quy tắc có chủ đích cho bộ dữ liệu của bài, không phải công cụ nhận diện mọi bí mật. Ví dụ, khóa `client-secret`, một URL chứa thông tin xác thực hoặc một phần tử `api-token[0]` chưa được bao phủ chỉ bằng hai hậu tố này. Việc chuẩn hóa cũng có thể làm hai tên khác nhau trở thành giống nhau và che rộng hơn mong muốn.

Trong môi trường thật, phải xuất phát từ danh mục trường nhạy cảm và các hình dạng dữ liệu thực tế: trường Java, tên nguồn môi trường, khóa lồng nhau, phần tử danh sách hoặc bản đồ. Sau đó kiểm thử trên chính phản hồi của endpoint. Không đánh giá hiệu quả chỉ bằng việc nhìn tên phương thức Java.

### 6.6. Quyền truy cập: `EndpointSecurity.java`

Đặt tại `src/main/java/com/example/sanitizing/EndpointSecurity.java`.

```java
package com.example.sanitizing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class EndpointSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var readableConfiguration = new AndRequestMatcher(
                EndpointRequest.to("env", "configprops"),
                request -> HttpMethod.GET.matches(request.getMethod()));

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(readableConfiguration)
                    .hasRole("ACTUATOR_READER")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.logout(logout -> logout.disable());
        // CSRF giữ nguyên mặc định; không cấp quyền cho thao tác ghi.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${lab.auth.reader-password}") String readerPassword,
            @Value("${lab.auth.viewer-password}") String viewerPassword,
            @Value("${lab.auth.outsider-password}") String outsiderPassword) {
        var reader = User.withUsername("reader")
                .password(encoder.encode(readerPassword))
                .roles("ACTUATOR_READER")
                .build();
        var viewer = User.withUsername("viewer")
                .password(encoder.encode(viewerPassword))
                .roles("ACTUATOR_READER", "CONFIG_VIEWER")
                .build();
        var outsider = User.withUsername("outsider")
                .password(encoder.encode(outsiderPassword))
                .roles("CONFIG_VIEWER")
                .build();
        return new InMemoryUserDetailsManager(reader, viewer, outsider);
    }
}
```

Chuỗi bảo mật này bao phủ mọi yêu cầu HTTP. Chỉ GET đến hai endpoint cấu hình được phép khi người gọi có vai trò `ACTUATOR_READER`; mọi yêu cầu còn lại bị từ chối. Hàm đối sánh `EndpointRequest` dựa vào vị trí endpoint do Actuator quản lý, thay vì mở rộng toàn bộ đường dẫn ứng dụng.

Tài khoản `outsider` có vai trò xem giá trị nhưng không có vai trò đọc endpoint. Nhờ vậy, ta chứng minh được một điều kiện không tự thay thế điều kiện còn lại.

Ví dụ giữ cấu hình CSRF mặc định và không cấp quyền cho thao tác ghi. Không cần tắt CSRF để đọc dữ liệu qua GET.

Bộ tài khoản trong bộ nhớ và BCrypt được dùng để bài tự chạy. Trong hệ thống thật, danh tính người vận hành cần được quản lý theo từng người, có khả năng thu hồi và truy vết. Việc đổi mật khẩu môi trường ở ví dụ cần khởi động lại để tạo lại tài khoản trong bộ nhớ.

## 7. Chạy và đọc kết quả

### 7.1. Khởi động

Tại thư mục chứa `pom.xml`, dùng PowerShell với `JAVA_HOME` trỏ đến JDK 21:

```powershell
$env:READER_PASSWORD = 'reader-local-demo-only'
$env:VIEWER_PASSWORD = 'viewer-local-demo-only'
$env:OUTSIDER_PASSWORD = 'outsider-local-demo-only'
mvn spring-boot:run
```

Ba mật khẩu trên là dữ liệu công khai chỉ dành cho bài thực hành cục bộ. Không dùng chúng cho máy chủ thật. Khi truyền thông tin xác thực qua mạng, dùng HTTPS với kiểm tra chứng chỉ đúng; HTTP Basic không cung cấp tính bí mật chỉ nhờ mã hóa Base64.

### 7.2. Phân biệt mã 200 có che dữ liệu với mã từ chối truy cập

Mở terminal PowerShell thứ hai:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -o NUL -w "%{http_code}\n" -u reader:reader-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -o NUL -w "%{http_code}\n" -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -o NUL -w "%{http_code}\n" -u outsider:outsider-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
```

Kết quả theo đúng thứ tự:

```text
401
200
200
403
```

Hai phản hồi 200 có mức dữ liệu khác nhau. Xem tài liệu JSON:

```powershell
curl.exe -s -u reader:reader-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/env/demo.api-token
```

Đọc trường `property.value` trong phản hồi:

| Yêu cầu | Giá trị tại property.value |
| --- | --- |
| `reader` đọc `demo.region` | `******` |
| `viewer` đọc `demo.region` | `lab-east` |
| `viewer` đọc `demo.api-token` | `******` |

Phản hồi còn có thông tin nguồn và các siêu dữ liệu khác, nên không coi toàn bộ JSON là một chuỗi cố định. Ở đây, ta kiểm tra đúng trường chứa giá trị và bảo đảm token gốc không xuất hiện trong toàn bộ phản hồi.

Mật khẩu trong các lệnh là dữ liệu giả để tiện tái hiện. Khi dùng thông tin xác thực thật, tránh đưa mật khẩu vào lịch sử shell hoặc danh sách tham số tiến trình; có thể dùng `curl.exe -u viewer` để nhập mật khẩu tương tác.

### 7.3. Đối chiếu configprops

```powershell
curl.exe -s -u reader:reader-local-demo-only http://127.0.0.1:8080/actuator/configprops
curl.exe -s -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/configprops
```

Trong `contexts`, tìm bean có `prefix` bằng `demo`, rồi đọc `properties`.

Với `reader`, phần giá trị của bean này là:

```json
{
  "region": "******",
  "apiToken": "******"
}
```

Với `viewer`, phần đó là:

```json
{
  "region": "lab-east",
  "apiToken": "******"
}
```

Các khối JSON trên chỉ là phần `properties` của bean `demo`, không phải toàn bộ tài liệu HTTP. Không cố định mã bean hoặc tên ngữ cảnh bằng cách đoán; bài kiểm thử tìm bean theo `prefix`.

Cũng cần kiểm tra dữ liệu đầu vào cấu hình được mô tả trong tài liệu, chẳng hạn `inputs`, thay vì chỉ xem các trường trong `properties`. Bài kiểm thử kiểm tra toàn bộ phản hồi không chứa token giả ban đầu.

### 7.4. Thay đổi chế độ và dự đoán trước kết quả

Dừng ứng dụng, rồi chạy lại với cả hai endpoint dùng cùng một chế độ:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.endpoint.env.show-values=never --management.endpoint.configprops.show-values=never"
```

Hoặc:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.endpoint.env.show-values=always --management.endpoint.configprops.show-values=always"
```

Đây là hai lần chạy thay thế nhau, không phải hai ứng dụng chạy đồng thời trên cổng 8080. Các biến mật khẩu phải còn trong môi trường của terminal khởi động.

Ma trận dự đoán cho `demo.region`:

| show-values | reader | viewer | outsider |
| --- | --- | --- | --- |
| `never` | HTTP 200, `******` | HTTP 200, `******` | HTTP 403 |
| `when-authorized` | HTTP 200, `******` | HTTP 200, `lab-east` | HTTP 403 |
| `always` | HTTP 200, `lab-east` | HTTP 200, `lab-east` | HTTP 403 |

Đối với `demo.api-token`, mọi phản hồi được phép của `reader` và `viewer` vẫn phải có giá trị `******`. Chính `SanitizingFunction` tạo ra sự khác biệt này.

## 8. Kiểm thử để chứng minh từng lớp hoạt động

### 8.1. Kiểm thử ba chế độ qua Spring MVC và Spring Security

Đặt tệp sau tại `src/test/java/com/example/sanitizing/SanitizingHttpTest.java`.

Kiểm thử dùng `WebApplicationContextRunner` tạo ngữ cảnh độc lập cho từng chế độ, nạp `application.yml` bằng `ConfigDataApplicationContextInitializer` và dựng MockMvc với bộ lọc Spring Security. Các yêu cầu dùng HTTP Basic qua bộ lọc xác thực.

Không cần mở cổng mạng thật cho kiểm thử này. Nó kiểm tra xử lý yêu cầu trong ứng dụng, không thay thế kiểm tra TLS, tường lửa hay cấu hình cổng truy cập trong môi trường triển khai.

```java
package com.example.sanitizing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class SanitizingHttpTest {
    private static final String MASK = "******";
    private final ObjectMapper json = new ObjectMapper();

    @ParameterizedTest
    @ValueSource(strings = {"never", "when-authorized", "always"})
    void visibilityPolicyIsEnforcedOverHttp(String mode) {
        new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(MaskingApplication.class)
                .withPropertyValues(
                        "management.endpoint.env.show-values=" + mode,
                        "management.endpoint.configprops.show-values=" + mode,
                        "lab.auth.reader-password=reader-test-only",
                        "lab.auth.viewer-password=viewer-test-only",
                        "lab.auth.outsider-password=outsider-test-only")
                .run(context -> {
                    MockMvc mvc = MockMvcBuilders
                            .webAppContextSetup(context.getSourceApplicationContext())
                            .apply(springSecurity())
                            .build();

                    assertThat(call(mvc, "/actuator/env/demo.region", null)
                            .getStatus()).isEqualTo(401);
                    assertThat(call(mvc, "/actuator/env/demo.region", "outsider")
                            .getStatus()).isEqualTo(403);

                    for (String user : new String[]{"reader", "viewer"}) {
                        boolean canSeeOriginal = mode.equals("always")
                                || (mode.equals("when-authorized")
                                        && user.equals("viewer"));
                        String expectedRegion = canSeeOriginal ? "lab-east" : MASK;

                        var region = call(mvc, "/actuator/env/demo.region", user);
                        assertThat(region.getStatus()).isEqualTo(200);
                        assertThat(json.readTree(region.getContentAsString())
                                .path("property").path("value").asText())
                                .isEqualTo(expectedRegion);

                        var token = call(mvc, "/actuator/env/demo.api-token", user);
                        assertThat(token.getStatus()).isEqualTo(200);
                        assertThat(json.readTree(token.getContentAsString())
                                .path("property").path("value").asText())
                                .isEqualTo(MASK);
                        assertThat(token.getContentAsString())
                                .doesNotContain("synthetic-token-not-real");

                        var config = call(mvc, "/actuator/configprops", user);
                        assertThat(config.getStatus()).isEqualTo(200);
                        JsonNode properties = findDemoProperties(
                                config.getContentAsString());
                        assertThat(properties.path("region").asText())
                                .isEqualTo(expectedRegion);
                        assertThat(properties.path("apiToken").asText())
                                .isEqualTo(MASK);
                        assertThat(config.getContentAsString())
                                .doesNotContain("synthetic-token-not-real");
                    }

                    assertThat(context.getEnvironment().getProperty("demo.api-token"))
                            .isEqualTo("synthetic-token-not-real");
                    assertThat(context.getBean(DemoSettings.class).getApiToken())
                            .isEqualTo("synthetic-token-not-real");
                });
    }

    private MockHttpServletResponse call(MockMvc mvc, String path, String user)
            throws Exception {
        var request = get(path);
        if (user != null) {
            request.with(httpBasic(user, user + "-test-only"));
        }
        return mvc.perform(request).andReturn().getResponse();
    }

    private JsonNode findDemoProperties(String body) throws Exception {
        for (JsonNode context : json.readTree(body).path("contexts")) {
            for (JsonNode bean : context.path("beans")) {
                if (bean.path("prefix").asText().equals("demo")) {
                    return bean.path("properties");
                }
            }
        }
        throw new AssertionError("Missing demo configuration properties");
    }
}
```

Các kiểm tra này có chủ đích khác nhau:

- 401 và 403 chứng minh lớp kiểm soát truy cập vẫn hoạt động.
- `region` chứng minh ba chế độ hiển thị có tác dụng đúng theo vai trò.
- `apiToken` chứng minh quy tắc che bổ sung vẫn được giữ khi bản gốc của trường khác đã được hiển thị.
- Kiểm tra cả `env` và `configprops` chứng minh không chỉ một góc nhìn được bảo vệ.
- Kiểm tra toàn bộ nội dung phản hồi giúp phát hiện token bị lộ ở phần khác của tài liệu.
- Đọc lại `Environment` và `DemoSettings` chứng minh che đầu ra không làm mất giá trị mà ứng dụng sử dụng.

Mật khẩu trong thuộc tính test chỉ là dữ liệu giả. Kiểm thử không cần các biến môi trường mật khẩu của phiên chạy ứng dụng.

### 8.2. Kiểm thử hợp đồng của hàm che

Đặt tệp sau tại `src/test/java/com/example/sanitizing/SanitizerContractTest.java`.

```java
package com.example.sanitizing;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.endpoint.SanitizableData;
import org.springframework.boot.actuate.endpoint.Sanitizer;

import static org.assertj.core.api.Assertions.assertThat;

class SanitizerContractTest {
    @Test
    void configuredSecretSpellingsAreMasked() {
        var sanitizer = new Sanitizer(
                List.of(new DataMaskingConfig().hideLabSecrets()));
        for (String key : new String[]{
                "demo.api-token", "apiToken", "DEMO_API_TOKEN",
                "lab.auth.viewer-password"}) {
            var data = new SanitizableData(null, key, "test-secret");
            assertThat(sanitizer.sanitize(data, true)).isEqualTo("******");
        }
    }

    @Test
    void ordinaryValueAndNullKeepTheirMeaning() {
        var sanitizer = new Sanitizer(
                List.of(new DataMaskingConfig().hideLabSecrets()));
        assertThat(sanitizer.sanitize(
                new SanitizableData(null, "demo.region", "lab-east"), true))
                .isEqualTo("lab-east");
        assertThat(sanitizer.sanitize(
                new SanitizableData(null, "demo.api-token", null), false))
                .isNull();
    }

    @Test
    void allowedOriginalHasNoAutomaticPasswordNameProtection() {
        var sanitizer = new Sanitizer();
        var data = new SanitizableData(null, "demo.password", "test-secret");
        assertThat(sanitizer.sanitize(data, true)).isEqualTo("test-secret");
        assertThat(sanitizer.sanitize(data, false)).isEqualTo("******");
    }

    @Test
    void firstChangedValueStopsLaterFunctions() {
        var data = new SanitizableData(null, "demo.api-token", "test-secret");
        var sanitizer = new Sanitizer(List.of(
                value -> value.withValue("first-mask"),
                value -> value.withValue("second-mask")));
        assertThat(sanitizer.sanitize(data, true)).isEqualTo("first-mask");
    }
}
```

Bốn kiểm thử này kiểm chứng những điều có thể bị hiểu sai khi chỉ nhìn kết quả che của một endpoint:

1. Các cách viết khóa đã chọn đều được bảo vệ, kể cả khi không có `PropertySource`.
2. Giá trị bình thường được giữ nguyên khi cho xem bản gốc; `null` không bị biến thành một bí mật giả.
3. Tên khóa có chữ `password` không tự bảo đảm được che khi cho xem bản gốc và không có hàm bổ sung.
4. Hàm thay đổi giá trị đầu tiên kết thúc xử lý; hàm sau không mặc nhiên được chạy.

Không thêm kiểm thử bằng bí mật thật. Một token thử có dấu hiệu nhận diện riêng giúp phát hiện lộ dữ liệu mà không đưa thông tin nhạy cảm vào mã nguồn hoặc báo cáo kiểm thử.

### 8.3. Chạy kiểm thử

Tại thư mục chứa `pom.xml`:

```powershell
mvn test
```

Phần kết quả cần thấy khi thành công:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Ba lần chạy tham số của `SanitizingHttpTest` cộng với bốn kiểm thử của `SanitizerContractTest` tạo thành bảy ca. Log khởi tạo Spring và thời gian chạy có thể khác giữa các máy.

Bộ kiểm thử này không kiểm chứng mọi endpoint hoặc mọi dữ liệu của một ứng dụng khác. Khi thêm trường cấu hình hoặc nâng phiên bản Spring Boot, phải kiểm tra lại hình dạng phản hồi và quy tắc che tương ứng.

## 9. Chọn chính sách cho môi trường thật

### 9.1. Ưu tiên che toàn bộ khi không cần giá trị gốc

Nếu công việc chỉ cần xác định một khóa có xuất hiện hay không, nguồn nào cung cấp nó hoặc nhóm thuộc tính nào đã được nạp, hãy xem liệu `never` đã đủ hay chưa.

Đừng chuyển sang `always` chỉ vì một phản hồi có nhiều dấu che. Trước hết, xác định công việc thật sự cần trường nào, ai cần đọc và trong khoảng thời gian nào.

Che toàn bộ cũng không thay thế phân quyền endpoint: siêu dữ liệu cấu hình có thể vẫn tiết lộ cấu trúc ứng dụng và môi trường.

### 9.2. when-authorized là quyết định mở rộng dữ liệu

Khi bật `when-authorized`, người thỏa vai trò có thể nhận bản gốc của nhiều thuộc tính không nằm trong quy tắc che. Với endpoint `env`, phạm vi có thể rộng hơn nhóm cấu hình do ứng dụng tự đặt.

Do đó cần:

1. Xác định rõ nhóm người được xem và ánh xạ vai trò thực tế.
2. Rà soát các nguồn cấu hình và danh mục trường nhạy cảm.
3. Bổ sung quy tắc che cho những trường không được phép lộ ngay cả với nhóm đó.
4. Kiểm tra cả dữ liệu chính và các phần mô tả đầu vào, nguồn, lỗi.
5. Gắn thay đổi quyền với cơ chế thu hồi, theo dõi và đánh giá lại khi nhu cầu kết thúc.

Trong thiết kế bài thực hành, nhận diện hai hậu tố là đủ để minh họa. Nó không phải cấu hình có thể sao chép nguyên trạng sang mọi hệ thống sản xuất.

### 9.3. Chọn danh sách cho phép hoặc danh sách phải che theo dữ liệu thật

Danh sách các tên phải che dễ hiểu, nhưng có thể bỏ sót một trường bí mật mới. Danh sách các tên được phép hiện có thể hạn chế rủi ro đó, nhưng cần đủ ngữ cảnh để không mở nhầm những trường trùng tên.

Ví dụ, hai bean khác nhau cùng có trường `value` hoặc `token`. Chỉ nhìn tên trường cuối có thể không đủ để xác định nội dung được phép lộ. Một quy tắc dựa vào tên nguồn cũng không được giả định `getPropertySource()` luôn tồn tại.

Nếu không xác định được ranh giới cho phép một cách đáng tin, duy trì `never` hoặc cung cấp một cơ chế chẩn đoán hẹp với dữ liệu đã được chọn rõ ràng thường dễ kiểm chứng hơn mở bản gốc của toàn bộ cấu hình.

Hàm che nên là phép biến đổi thuần: quyết định từ dữ liệu đầu vào và trả bản mô tả mới. Tránh tra cứu mạng, làm thay đổi đối tượng cấu hình hoặc quyết định theo một danh tính người dùng lấy ngầm từ nơi khác.

## 10. Những lỗi dễ gây lộ dữ liệu hoặc hiểu sai kết quả

| Lỗi | Vì sao sai | Cách kiểm chứng hoặc điều chỉnh |
| --- | --- | --- |
| Coi `roles` là danh sách người được gọi endpoint | Vai trò xem bản gốc và quyền HTTP là hai điều kiện khác nhau | Kiểm tra tài khoản có vai trò xem nhưng thiếu quyền gọi |
| Bỏ trống roles rồi tưởng không ai xem được bản gốc | Với when-authorized qua HTTP, mặc định người đã xác thực đủ điều kiện xem | Khai báo vai trò rõ ràng và kiểm tra cả người không thuộc nhóm |
| Coi `always` vẫn tự che mọi mật khẩu theo tên | Bản gốc được phép hiện nếu không có quy tắc che áp dụng | Kiểm thử khóa bí mật khi cho phép xem bản gốc |
| Chỉ cấu hình `env` | `configprops` có thể tạo một góc nhìn cấu hình khác | Kiểm tra chính sách và phản hồi từng endpoint |
| Chỉ kiểm tra `properties` trong configprops | Dữ liệu có thể còn được mô tả ở phần đầu vào | Kiểm tra toàn bộ phản hồi không chứa dấu hiệu token thử |
| Tưởng hàm che làm thay đổi Environment hoặc bean | Hàm biến đổi dữ liệu mô tả đầu ra | Kiểm tra giá trị bên trong vẫn đúng mà không mở endpoint trả bí mật |
| Trả `null` khi không muốn che | Không đáp ứng hợp đồng dữ liệu mà Sanitizer sử dụng | Trả nguyên `data` |
| Ép kiểu mọi giá trị sang String | Giá trị đầu vào có thể không phải chuỗi | Nhận diện theo khóa hoặc xử lý kiểu có kiểm soát |
| Ghi log giá trị gốc trong hàm che | Chính cơ chế bảo vệ tạo thêm nơi lộ dữ liệu | Không ghi bí mật; chỉ theo dõi thông tin không nhạy cảm cần thiết |
| Giả định mọi hàm tùy chỉnh đều chạy | Giá trị thay đổi đầu tiên có thể kết thúc xử lý | Dùng quy tắc kết hợp hoặc kiểm thử danh sách và thứ tự thực tế |
| Chỉ thử tên khóa trong YAML | Endpoint khác có thể dùng tên trường Java hoặc khóa có dạng khác | Thử cả đầu ra env, configprops và dạng khóa thực tế |
| Tin HTTP roles cũng bảo vệ JMX | Hai kênh có cơ chế truy cập khác nhau | Tắt kênh không dùng hoặc bảo vệ riêng |
| Xem dấu che là bằng chứng bí mật không còn tồn tại | Giá trị trong bộ nhớ và các đường xuất dữ liệu khác vẫn độc lập | Kiểm tra log, API tự viết và các đường chẩn đoán liên quan |

Hai lỗi về kiểm thử cũng cần tránh:

- **Chỉ thử trường bí mật với never.** Khi mọi giá trị đều bị che, một hàm tùy chỉnh bị thiếu hoặc sai vẫn có thể không bị phát hiện. Cần thử thêm chế độ cho phép hiện bản gốc.
- **Chỉ thử người được xem bản gốc.** Cần chứng minh người chỉ có quyền gọi endpoint vẫn nhận bản đã che, và người thiếu quyền gọi thực sự bị từ chối.

## 11. Bài tập mở rộng có tiêu chí rõ ràng

Giả sử bổ sung:

```yaml
demo:
  client-secret: synthetic-client-secret-not-real
```

Với quy tắc hai hậu tố hiện tại, không được tự kết luận trường mới đã được bảo vệ khi bản gốc được phép hiển thị.

Hãy thực hiện trong dự án thực hành:

1. Viết kiểm thử thể hiện trường mới phải bị che trong `env` ở cả ba chế độ.
2. Nếu trường thuộc một bean `@ConfigurationProperties`, kiểm tra cả phản hồi `configprops`.
3. Bổ sung quy tắc nhận diện tên trường với cách viết thực tế, không chỉ thêm một tên Java chưa đối chiếu.
4. Xác nhận `region` vẫn hiện đúng cho người được phép; tránh che toàn bộ chỉ để làm kiểm thử trường bí mật thành công.
5. Xác nhận ứng dụng vẫn nhận đúng giá trị gốc và token giả không xuất hiện ở bất kỳ phần nào của phản hồi kiểm thử.

Kết quả cần đạt là một chính sách có thể giải thích và kiểm chứng: người gọi phải được phép vào endpoint; mức hiển thị quyết định quyền xem bản gốc; các trường nhạy cảm đã xác định vẫn bị che bằng quy tắc bổ sung; giá trị cấu hình mà ứng dụng sử dụng không bị thay đổi.
