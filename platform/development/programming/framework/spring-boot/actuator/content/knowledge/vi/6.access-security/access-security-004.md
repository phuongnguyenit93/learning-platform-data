# Sử dụng EndpointRequest để khớp endpoint trong ứng dụng Servlet

## 1. Vấn đề: bảo vệ chức năng Actuator hay một chuỗi URL?

Giả sử ứng dụng cần cho phép công cụ kiểm tra tình trạng hoạt động đọc health, nhưng chỉ người vận hành được xem các endpoint quản trị khác.

Một cách dễ nghĩ đến là viết quy tắc cho `/actuator/**`. Tuy nhiên, đó là quy tắc khớp một tiền tố URL. Nếu đường Actuator đổi thành `/manage`, nếu health được ánh xạ sang tên khác, hoặc nếu ứng dụng dùng cổng quản trị riêng, việc giữ những chuỗi đường dẫn rải rác trong mã bảo mật sẽ khó kiểm soát hơn.

`EndpointRequest` giúp diễn đạt ý định theo **endpoint Actuator**: health, info hoặc tất cả endpoint đã được ánh xạ, thay vì tự ghép URL theo trí nhớ.

Bài này dùng **Spring Boot 3.3.x, Spring MVC và Spring Security 6.x**. Bài thực hành cố định Spring Boot 3.3.13 với Java 21; các API được dùng thuộc nhánh Servlet. Không áp dụng nguyên code này cho WebFlux.

Sau bài học, cần giải thích được ba việc:

- Matcher đang nhận diện tập yêu cầu nào.
- Matcher được đặt để chọn cả chuỗi bảo mật hay chỉ chọn một quy tắc quyền trong chuỗi.
- Yêu cầu không khớp sẽ đi đâu.

## 2. EndpointRequest là gì và không tự làm những gì?

Trong ứng dụng Servlet, import đúng là:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
```

Đây là lớp cung cấp các hàm tạo đối tượng `RequestMatcher` cho vị trí HTTP của endpoint Actuator. Một matcher trả lời câu hỏi: **yêu cầu hiện tại có thuộc tập mà tôi nhận diện không?**

Nó chưa trả lời người gọi có quyền gì. Quyền đến từ các quy tắc như `permitAll()`, `authenticated()`, `hasRole(...)` hoặc `denyAll()` được ghép với matcher. [EndpointRequest 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

Hãy tách trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| Cấu hình bật/công bố endpoint | Xác định chức năng nào được cung cấp qua HTTP |
| EndpointRequest | Nhận diện yêu cầu theo ánh xạ endpoint |
| SecurityFilterChain | Xác định chuỗi bộ lọc và các chính sách được áp dụng |
| Quy tắc quyền | Quyết định yêu cầu đã khớp có được đi tiếp không |
| Cơ chế xác thực | Xác minh danh tính và cung cấp thông tin quyền của người gọi |

`EndpointRequest` không tự bật endpoint, thêm dependency, công bố endpoint, tạo tài khoản, lọc IP hay mở cổng mạng. Nó cũng không phải một bộ dò tự động mọi controller nghiệp vụ.

Ví dụ, đưa `EndpointRequest.to("info")` vào cấu hình không đồng nghĩa `info` đã được công bố qua HTTP. Vẫn phải cấu hình exposure riêng. [Spring Boot 3.3: Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

## 3. Chọn matcher theo ý định

Các đoạn Java ngắn trong phần này là những biểu thức/đoạn cấu hình minh họa; chương trình đầy đủ nằm ở phần thực hành.

### 3.1. Khớp theo ID endpoint

```java
EndpointRequest.to("health")
EndpointRequest.to("health", "info")
```

Chuỗi truyền vào là **ID endpoint**, không phải URL và không phải tên phương thức Java.

Với health:

- Đúng: `"health"`.
- Sai ý định: `"/actuator/health"`.
- Sai ý định sau khi đổi tên đường: lấy tên đường mới làm ID.

Nếu health được ánh xạ thành `/manage/ready`, ID vẫn là `health`.

### 3.2. Khớp theo class endpoint

```java
EndpointRequest.to(HealthEndpoint.class)
EndpointRequest.to(HealthEndpoint.class, InfoEndpoint.class)
```

Các class tương ứng cần import:

```java
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.info.InfoEndpoint;
```

Cách này giúp trình biên dịch kiểm tra tên class. Nó vẫn hướng tới định danh endpoint, không buộc đường HTTP phải có tên giống tên class.

Class truyền vào phải là class endpoint Actuator phù hợp. Không truyền một class `@RestController` thông thường rồi mong nó trở thành endpoint Actuator.

### 3.3. Khớp tất cả endpoint và discovery

```java
EndpointRequest.toAnyEndpoint()
```

Matcher này nhận diện các đường endpoint Actuator trong ánh xạ hiện tại và còn bao gồm đường discovery tại base path. Với base path `/manage`, discovery thông thường nằm ở `/manage`.

Discovery là nơi cung cấp các liên kết tới endpoint. Không nên bỏ sót nó chỉ vì quy tắc bảo mật đã bảo vệ các URL con.

### 3.4. Khớp riêng discovery

```java
EndpointRequest.toLinks()
```

Dùng khi muốn đặt chính sách riêng cho discovery, chẳng hạn không cho truy cập trang liên kết nhưng vẫn cho công cụ gọi trực tiếp một endpoint được cấp quyền.

Nếu thay đổi cấu hình discovery hoặc base path, phải kiểm tra lại endpoint thực sự được cung cấp. Một matcher khớp đường không có nghĩa tại đường đó luôn có tài nguyên để trả thành công.

### 3.5. Loại endpoint hoặc discovery khỏi một matcher

```java
EndpointRequest.toAnyEndpoint().excluding(HealthEndpoint.class)
EndpointRequest.toAnyEndpoint().excluding("health", "info")
EndpointRequest.toAnyEndpoint().excludingLinks()
```

`excluding(...)` thay đổi tập yêu cầu mà matcher nhận diện. `excludingLinks()` loại phần discovery. Các phương thức này không xóa endpoint khỏi ứng dụng và không đồng nghĩa cho phép hay cấm người gọi.

Trong API 3.3, các phương thức loại trừ trả về matcher mới. Vì thế cần dùng kết quả trả về, chẳng hạn:

```java
var allEndpoints = EndpointRequest.toAnyEndpoint();
var endpointsWithoutHealth = allEndpoints.excluding(HealthEndpoint.class);
```

Gọi `allEndpoints.excluding(...)` rồi bỏ kết quả không phải là cách cập nhật biến `allEndpoints`. [EndpointRequestMatcher 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.EndpointRequestMatcher.html)

## 4. Hiểu phạm vi đường được khớp

### 4.1. Khớp endpoint không chỉ là khớp đúng một URL gốc

Một endpoint có thể có các đường con. Ví dụ, health có thể có các nhóm như liveness; metrics có thể có đường cho một tên chỉ số.

Khi áp dụng `EndpointRequest.to(HealthEndpoint.class)`, phải hiểu chính sách hướng đến health và các đường con mà matcher bao phủ. Nếu đặt `permitAll()`, không nên nghĩ rằng chỉ đúng một chuỗi `/manage/health` được công khai.

Bài thực hành sẽ bật nhóm health và thử một đường con để quan sát điều này. Nếu sản phẩm muốn cho phép một nhóm hoặc một thao tác hẹp hơn, cần đặt matcher bổ sung tương ứng.

### 4.2. toAnyEndpoint không phải mẫu /manage/**

Matcher dựa trên ánh xạ endpoint. Nó không coi mọi đường bất kỳ dưới tiền tố quản trị là một endpoint đã tồn tại.

Ví dụ, khi metrics chưa được công bố, không được suy luận `/manage/metrics` đã thuộc chính sách quản trị chỉ vì nó có tiền tố `/manage`. Một yêu cầu không thuộc tập endpoint được nhận diện sẽ tiếp tục được xét theo các chuỗi/quy tắc còn lại.

Điều này cũng giải thích vì sao phải có chính sách cho phần còn lại của ứng dụng. `PathMappedEndpoints` cung cấp các đường theo ID và có thể trả về không tìm thấy ID trong tập ánh xạ. [PathMappedEndpoints 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/PathMappedEndpoints.html)

### 4.3. Matcher endpoint không tự giới hạn phương thức HTTP

Một matcher nhận diện endpoint chưa phải quy tắc “chỉ được GET”. Với endpoint có thao tác đọc và thao tác thay đổi trạng thái, một chính sách rộng có thể áp dụng cho cả hai.

Nếu chỉ muốn cấp quyền cho GET của một endpoint, có thể kết hợp matcher endpoint với điều kiện phương thức. Ví dụ minh họa, cần các import của Spring Security:

```java
RequestMatcher readOnlyLoggers = new AndRequestMatcher(
    EndpointRequest.to("loggers"),
    request -> "GET".equals(request.getMethod())
);
```

Ở đây `RequestMatcher` và `AndRequestMatcher` thuộc `org.springframework.security.web.util.matcher`. Điều kiện chỉ giới hạn GET; nếu muốn cho phép HEAD hoặc phương thức khác phải quyết định rõ.

Đây mới là matcher để chọn yêu cầu. Sau đó vẫn phải ghép quyền và chính sách cho các yêu cầu không khớp. Với thao tác ghi, các kiểm tra như CSRF vẫn là lớp riêng; khớp endpoint không vô hiệu hóa chúng.

## 5. Hai nơi đặt matcher trong cấu hình bảo mật

### 5.1. securityMatcher chọn phạm vi của cả chuỗi

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
```

Dòng này nói: chuỗi đang được xây dựng chỉ xử lý những yêu cầu khớp tập Actuator mà matcher nhận diện.

Một yêu cầu API nghiệp vụ không khớp sẽ không được chuỗi đó xử lý. Nó cần một chuỗi khác hoặc chính sách hạ tầng được xác định rõ.

### 5.2. requestMatchers chọn quy tắc quyền bên trong chuỗi

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
    .anyRequest().hasRole("OPS")
);
```

Trong đoạn minh họa này, matcher health chọn quy tắc cho health **trong những yêu cầu đã đi vào chuỗi**.

Nếu chuỗi được thu hẹp bằng `securityMatcher(EndpointRequest.toAnyEndpoint())`, `anyRequest()` ở đây nghĩa là những yêu cầu còn lại trong phạm vi chuỗi quản trị. Nó không tự bảo vệ mọi API của ứng dụng.

Nếu chuỗi không có matcher thu hẹp phạm vi, phạm vi ban đầu rộng hơn; cùng một `anyRequest()` sẽ có ảnh hưởng khác. Đây là lý do phải đọc cả cấu hình chuỗi, không chỉ một dòng quy tắc. [HttpSecurity 6.3 API](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html)

### 5.3. Thứ tự chuỗi và thứ tự quy tắc là hai tầng

```text
Yêu cầu HTTP
  → xét chuỗi theo thứ tự
  → chọn chuỗi đầu tiên có matcher phù hợp
  → xét quy tắc quyền trong chuỗi đó theo thứ tự
  → cho phép hoặc từ chối
```

Không cộng dồn tất cả chuỗi để tạo một tập quyền cuối cùng. Chuỗi bắt tất cả đặt trước có thể khiến chuỗi chuyên cho Actuator không được chọn. [Spring Security: Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)

Bên trong chuỗi, đặt health cụ thể trước quy tắc bao quát là cách thể hiện ngoại lệ rõ ràng.

## 6. Ví dụ đầy đủ: hai chuỗi, hai nhóm quyền

### 6.1. Chính sách của bài thực hành

Ứng dụng dùng base path `/manage`, công bố health và info:

| Đường/nhóm yêu cầu | Chính sách |
| --- | --- |
| Health và các đường con được cấu hình | Cho phép không đăng nhập |
| Discovery và các endpoint Actuator khác | Yêu cầu vai trò OPS |
| Yêu cầu còn lại của ứng dụng | Yêu cầu đã xác thực |

Có hai tài khoản lab:

| Tài khoản | Mật khẩu lab | Vai trò |
| --- | --- | --- |
| reader | reader-lab-only | USER |
| operator | operator-lab-only | OPS |

Các credential này chỉ phục vụ thực hành cục bộ. Bài dùng HTTP trên loopback; khi gọi qua mạng thật cần TLS và cách quản lý danh tính/bí mật phù hợp.

### 6.2. Tạo dự án độc lập

Dùng Java 21 và Maven 3.9+, với cấu trúc:

```text
endpoint-request-lab/
├── pom.xml
└── src/main/
    ├── java/lab/EndpointMatcherApplication.java
    ├── java/lab/EndpointSecurityConfig.java
    └── resources/application.yml
```

Nội dung `pom.xml`:

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
    <groupId>lab</groupId>
    <artifactId>endpoint-request-lab</artifactId>
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

Maven lấy phiên bản Spring Security phù hợp từ quản lý dependency của Boot; không tự ghim thêm một phiên bản Security khác trong bài lab.

Nội dung `src/main/java/lab/EndpointMatcherApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class EndpointMatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointMatcherApplication.class, args);
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "api-pong\n";
    }
}
```

Nội dung `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      show-components: never
```

Bật probes để có đường health con dùng trong phép thử. Đợi ứng dụng khởi động xong trước khi kiểm tra readiness hoặc tình trạng tổng hợp.

### 6.3. Cấu hình bảo mật Servlet

Nội dung `src/main/java/lab/EndpointSecurityConfig.java`:

```java
package lab;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class EndpointSecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain managementEndpoints(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
            .requestMatchers(EndpointRequest.toLinks()).hasRole("OPS")
            .anyRequest().hasRole("OPS")
        );
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-lab-only"))
            .roles("USER")
            .build();

        var operator = User.withUsername("operator")
            .password(encoder.encode("operator-lab-only"))
            .roles("OPS")
            .build();

        return new InMemoryUserDetailsManager(reader, operator);
    }
}
```

Giải thích theo hai tầng:

1. `@Order(1)` được xét trước. Matcher của chuỗi nhận diện Actuator, bao gồm discovery.
2. Trong chuỗi đó, health được cho phép trước; discovery và phần quản trị còn lại yêu cầu OPS.
3. API nghiệp vụ không khớp chuỗi thứ nhất nên tới `@Order(2)`.
4. Chuỗi thứ hai không bị thu hẹp phạm vi và yêu cầu đã xác thực cho phần còn lại.
5. Cả hai chuỗi đều khai báo HTTP Basic nên phép thử không phụ thuộc trang đăng nhập bằng biểu mẫu.

Dòng `toLinks()` hiện có cùng quyền với `anyRequest()`, nhưng được viết riêng để cho thấy vị trí đặt một chính sách discovery độc lập.

`roles("OPS")` tạo quyền theo quy ước `ROLE_OPS`; dùng `hasRole("OPS")`, không ghép tiền tố `ROLE_` thêm lần nữa.

Khi tự khai báo các bean chuỗi, cấu hình bảo mật mặc định của Boot rút lui. Bài vì thế khai báo cả đường Actuator lẫn phần còn lại, thay vì chờ Boot tự bù một chuỗi bị thiếu. [ManagementWebSecurityAutoConfiguration 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/ManagementWebSecurityAutoConfiguration.html)

### 6.4. Đóng gói và khởi động

Chạy tại thư mục gốc dự án:

```bash
mvn clean package
java -jar target/endpoint-request-lab-1.0.0.jar
```

Đây là chương trình Spring Boot có dependency, nên dùng Maven để biên dịch/đóng gói thay vì `javac` độc lập trên một file. Lần đầu cần tải dependency từ kho Maven.

Giữ JVM chạy trong terminal thứ nhất. Bảo đảm không có ứng dụng khác dùng cổng 8080. Các lệnh kiểm tra tiếp theo dùng Bash và curl; trong PowerShell có thể gọi `curl.exe` với cú pháp phù hợp.

## 7. Kiểm chứng tập yêu cầu và quyền

### 7.1. Hàm gọi chỉ in HTTP status

Trong terminal thứ hai, khai báo hàm:

```bash
http_status() {
  curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
    -H 'Accept: application/json' "$@"
}
```

Hàm giữ nguyên các tham số truyền vào, bỏ body và in status. Nó không theo chuyển hướng và không tự gửi credential nếu chưa có `-u`.

### 7.2. Thử health, info, discovery và API nghiệp vụ

```bash
http_status http://127.0.0.1:8080/manage/health

http_status http://127.0.0.1:8080/manage/health/liveness

http_status http://127.0.0.1:8080/manage/info

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage/info

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage/info

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage

http_status http://127.0.0.1:8080/api/ping

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/api/ping
```

Với ứng dụng khỏe, đúng credential và đã khởi động xong, stdout dự kiến theo đúng thứ tự:

```text
200
200
401
403
200
403
200
401
200
```

Ý nghĩa của từng nhóm:

- Hai yêu cầu health cho thấy matcher health bao phủ cả đường gốc và đường nhóm liveness.
- Info ẩn danh nhận 401; reader xác thực được nhưng thiếu OPS nhận 403; operator nhận 200.
- Discovery không bị bỏ quên: reader nhận 403, operator nhận 200.
- API nghiệp vụ được chuỗi thứ hai bảo vệ: ẩn danh nhận 401, reader hợp lệ nhận 200.

Có thể kiểm tra body của API bằng lệnh:

```bash
curl --noproxy '*' -sS -u reader:reader-lab-only \
  http://127.0.0.1:8080/api/ping
```

Stdout:

```text
api-pong
```

Health có thể trả mã khác nếu ứng dụng không khỏe; khi gặp lỗi kết nối và curl in `000`, đó không phải HTTP status do endpoint trả về. Kiểm tra tiến trình, cổng và lỗi curl trước khi kết luận về matcher.

### 7.3. Thêm một endpoint được công bố mà không sửa matcher

Ở cấu hình ban đầu, metrics chưa nằm trong include. Với tài khoản hợp lệ, thử:

```bash
http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage/metrics
```

Stdout dự kiến:

```text
404
```

Yêu cầu không được chuỗi Actuator nhận diện như một endpoint đang được công bố; chuỗi còn lại vẫn xác thực reader, rồi ứng dụng không có ánh xạ HTTP tương ứng.

Dừng JVM, sau đó khởi động lại bằng danh sách exposure mới:

```bash
java -jar target/endpoint-request-lab-1.0.0.jar \
  --management.endpoints.web.exposure.include=health,info,metrics
```

Không sửa Java. Đợi ứng dụng sẵn sàng rồi thử:

```bash
http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage/metrics

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage/metrics
```

Stdout dự kiến:

```text
403
200
```

Metrics lúc này đã được công bố, nên nằm trong tập quản trị được nhận diện. Quy tắc OPS của chuỗi thứ nhất áp dụng cho nó mà không cần viết thêm một URL metrics vào mã bảo mật.

Điều này không phải lý do mở `include: "*"` một cách tùy tiện. Chọn tập endpoint cần cung cấp và chọn ai có quyền gọi vẫn là hai quyết định riêng.

## 8. Kiểm chứng khi đổi base path và tên đường endpoint

Dừng JVM của phần trước. Lần này khởi động lại với base path khác và ánh xạ health sang tên `ready`:

```bash
java -jar target/endpoint-request-lab-1.0.0.jar \
  --management.endpoints.web.base-path=/ops \
  --management.endpoints.web.path-mapping.health=ready
```

Mỗi lần khởi động chỉ dùng các tham số ghi trong lệnh hiện tại; tham số CLI của tiến trình cũ không tự lưu lại. File YAML vẫn công bố health và info.

Cấu trúc đường HTTP trong lần chạy này:

| Chức năng | Đường mới | ID dùng trong matcher |
| --- | --- | --- |
| Health | /ops/ready | health |
| Nhóm liveness | /ops/ready/liveness | Vẫn thuộc health |
| Info | /ops/info | info |
| Discovery | /ops | Dùng toLinks hoặc toAnyEndpoint |

Việc đổi base path/path mapping là hợp đồng cấu hình của Spring Boot; code dùng ID/class không phải đổi theo tên đường mới. [Spring Boot 3.3: Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Dùng lại hàm `http_status`:

```bash
http_status http://127.0.0.1:8080/ops/ready

http_status http://127.0.0.1:8080/ops/ready/liveness

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/ops/info

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/ops/info

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/ops

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage/health
```

Stdout dự kiến, khi ứng dụng khỏe:

```text
200
200
403
200
200
404
```

Lệnh cuối dùng credential hợp lệ để quan sát đường cũ không còn ánh xạ. Nếu gọi đường cũ ẩn danh, chuỗi xử lý phần còn lại có thể trả 401 trước bước định tuyến; 401 không chứng minh đường cũ vẫn là endpoint health.

Đừng đổi matcher thành `EndpointRequest.to("ready")`: `ready` là tên đường đã ánh xạ, không phải ID endpoint.

## 9. Cẩn thận với excluding và khoảng trống giữa các chuỗi

Giả sử sửa phạm vi chuỗi thứ nhất thành:

```java
http.securityMatcher(
    EndpointRequest.toAnyEndpoint().excluding("info")
);
```

Info vẫn được công bố. Thay đổi này chỉ làm nó không còn đi vào chuỗi quản trị đó.

Với chuỗi thứ hai của lab yêu cầu `authenticated()`, reader có thể đọc info vì yêu cầu rơi xuống chính sách xác thực chung, không còn yêu cầu OPS. Nếu không có chuỗi phù hợp nào khác, yêu cầu còn có thể nằm ngoài sự bảo vệ của các chuỗi Spring Security đã khai báo.

Tương tự:

```java
http.securityMatcher(
    EndpointRequest.toAnyEndpoint().excludingLinks()
);
```

Nếu chỉ sửa như vậy, một quy tắc `toLinks()` đặt bên trong chuỗi thứ nhất sẽ không bao giờ nhận discovery: phạm vi ngoài đã loại nó trước.

Muốn cấm discovery trong cấu hình lab, cách trực tiếp là **giữ discovery trong phạm vi chuỗi**, rồi đổi riêng quy tắc quyền:

```java
.requestMatchers(EndpointRequest.toLinks()).denyAll()
```

Đây là dòng thay thế quy tắc hiện có, không phải một cấu hình độc lập để thêm sau `anyRequest()`.

Phân biệt ba hành động:

| Ý định | Loại cấu hình phù hợp |
| --- | --- |
| Không cung cấp một endpoint qua HTTP | Exposure hoặc cấu hình bật/tắt endpoint phù hợp |
| Không cho một nhóm người gọi endpoint | Quy tắc phân quyền |
| Loại endpoint khỏi tập nhận diện của matcher | excluding, rồi xác định chính sách sẽ xử lý nó tiếp |

Không dùng `excluding` như một từ đồng nghĩa với `denyAll`.

## 10. Context path, cổng quản trị và phạm vi Servlet

### 10.1. Có context path

Nếu chạy chung cổng với `server.servlet.context-path=/training`, URL bên ngoài sẽ có thêm phần context path, chẳng hạn:

```text
http://127.0.0.1:8080/training/manage/health
```

ID vẫn là `health`. Khi dùng matcher theo endpoint, không tự nối `/training` vào ID hoặc tên class.

Phải phân biệt URL mà máy gọi nhìn thấy với phần đường dùng trong ứng dụng Servlet. Nếu thêm proxy hoặc thay servlet path ngoài mô hình thông thường, hãy kiểm tra bằng yêu cầu thực tế thay vì đoán từ một chuỗi cấu hình.

### 10.2. Có cổng quản trị riêng

Khi dùng `management.server.port` khác cổng chính, Actuator có web context quản trị tương ứng. Việc nhận diện phải gắn với context đúng; không thể chỉ nhìn thấy đường `/manage` trên cổng chính rồi kết luận đó là endpoint quản trị.

Trong triển khai 3.3.13, `EndpointRequest` có xử lý context quản trị khi cổng tách riêng. Matcher cũng khởi tạo dựa trên application context, không chỉ một phép so sánh chuỗi URL thuần túy. [Mã nguồn EndpointRequest 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.java)

Nếu chuyển mô hình lab sang cổng riêng, cần kiểm tra:

- Endpoint ở đúng cổng quản trị.
- API nghiệp vụ ở cổng chính.
- Chuỗi nào được chọn ở từng context.
- Địa chỉ lắng nghe, firewall và đường qua proxy.
- Health probe/bộ thu thập đang gọi đúng địa chỉ, cổng và đường.

Không suy ra chính sách mạng từ việc matcher khớp đúng endpoint.

### 10.3. Khác biệt với WebFlux và JMX

Bài sử dụng `EndpointRequest` trong package `security.servlet`, nhận diện yêu cầu Servlet.

WebFlux có API bảo mật và matcher reactive tương ứng; không dùng nguyên `HttpSecurity`/`SecurityFilterChain` của bài. JMX là kênh khác, không được bảo vệ bằng matcher HTTP Servlet này.

## 11. Các lỗi thường gặp khi đọc hoặc viết quy tắc

| Lỗi | Hệ quả | Cách kiểm tra |
| --- | --- | --- |
| Import EndpointRequest của reactive vào cấu hình Servlet | Sai loại matcher/API | Kiểm tra package import và web stack |
| Truyền /actuator/health vào to(String...) | Nhầm URL với ID | Dùng health hoặc HealthEndpoint.class |
| Truyền class controller nghiệp vụ | Class không phải endpoint Actuator phù hợp | Xác định loại thành phần đang bảo vệ |
| Chỉ có chuỗi securityMatcher(toAnyEndpoint()) | Bỏ sót phần ứng dụng còn lại | Kiểm kê chuỗi bao phủ các yêu cầu không khớp |
| Đặt chuỗi bắt tất cả trước chuỗi Actuator | Chuỗi chuyên biệt không được chọn | Kiểm tra Order và matcher của từng chuỗi |
| Đặt quy tắc bao quát trước ngoại lệ health | Ngoại lệ không được áp dụng như dự định | Xét thứ tự quy tắc trong chuỗi |
| Coi toAnyEndpoint như /manage/** | Hiểu sai yêu cầu không phải endpoint | Thử đường chưa ánh xạ với credential hợp lệ |
| Coi excluding là cấm truy cập | Endpoint rơi sang chính sách khác | Theo dấu chuỗi được chọn tiếp theo |
| Bỏ kết quả excluding | Vẫn dùng matcher ban đầu | Dùng giá trị matcher trả về |
| Quên discovery | Lộ trang liên kết ngoài chính sách dự kiến | Thử cả base path với các danh tính |
| Cho phép health nhưng chỉ nghĩ đến URL gốc | Bỏ qua nhóm hoặc đường con | Thử các đường health thực tế được cung cấp |
| Dùng matcher như bằng chứng endpoint đã được công bố | Nhầm nhận diện với exposure | Kiểm tra endpoint/ánh xạ và cấu hình HTTP |
| Đúng matcher nên cho rằng POST chắc chắn được phép | Bỏ qua vai trò, CSRF và phương thức hỗ trợ | Kiểm tra từng lớp và từng thao tác |

Khi chẩn đoán 401/403, thử với người ẩn danh, credential sai, người hợp lệ thiếu vai trò và người đủ vai trò. Không chỉ thử bằng operator rồi kết luận toàn bộ cấu hình đúng.

Khi chẩn đoán 404, xác nhận đúng cổng, context path, base path, path mapping và exposure. Thử có credential hợp lệ để tránh một bước từ chối xác thực che mất kết quả định tuyến.

## 12. Bài tập áp dụng

### Bài tập 1: một endpoint, hai cách định danh

Viết hai matcher cùng nhắm đến health: một bằng ID, một bằng class. Sau đó ánh xạ health sang `ready`.

**Tiêu chí tự kiểm tra:** cả hai vẫn biểu đạt endpoint health; không thay ID thành `ready`. Dùng phép thử đường mới để xác nhận quyền không bị thay đổi ngoài ý muốn.

### Bài tập 2: dự đoán đường đi của yêu cầu

Giữ hai chuỗi lab, chỉ loại info khỏi matcher chuỗi thứ nhất. Reader gọi info với credential hợp lệ.

**Phân tích:** info được xét ở chuỗi thứ hai, nơi chỉ cần đã xác thực. Nếu nhu cầu vẫn là OPS mới được đọc, thay đổi loại trừ đó không đáp ứng nhu cầu.

### Bài tập 3: tách chính sách discovery

Muốn health công khai, info cho OPS và discovery bị cấm với mọi người. Cần giữ matcher ngoài và đổi quy tắc nào?

**Phân tích:** giữ `toAnyEndpoint()` để discovery đi vào chuỗi quản trị, đặt `toLinks().denyAll()` trước quy tắc còn lại. Nếu muốn tắt tài nguyên discovery thay vì chỉ từ chối HTTP theo quyền, đó là quyết định cấu hình khác.

### Bài tập 4: thiết kế ma trận khi thay đổi hạ tầng

Chuyển sang cổng quản trị riêng hoặc thêm context path. Lập bảng nguồn gọi, cổng, đường thực tế, chuỗi dự kiến và kết quả theo danh tính.

**Tiêu chí tự kiểm tra:** có cả endpoint gốc, đường con, discovery, API nghiệp vụ và một đường không tồn tại. Mọi yêu cầu không khớp chuỗi Actuator đều có chính sách tiếp theo được giải thích rõ.
