# Hành vi bảo mật Actuator khi có hoặc không có Spring Security

## 1. Bắt đầu từ hai câu hỏi khác nhau

Actuator cung cấp các điểm truy cập phục vụ giám sát và vận hành ứng dụng Spring Boot. Một điểm truy cập, hay endpoint, có thể cho biết tình trạng hoạt động, thông tin ứng dụng, chỉ số hoặc hỗ trợ một thao tác quản trị.

Khi kiểm tra một endpoint, cần tách hai câu hỏi:

1. **Ứng dụng có cung cấp endpoint này qua HTTP không?**
2. **Nếu có, ai được phép gọi nó và với điều kiện nào?**

Spring Boot Actuator giải quyết việc cung cấp chức năng quản trị. Spring Security bổ sung cơ chế xác thực, phân quyền và các bộ lọc bảo vệ yêu cầu HTTP. Có Actuator không đồng nghĩa ứng dụng đã yêu cầu đăng nhập; thêm Spring Security cũng không đồng nghĩa mọi quyết định bảo mật đã phù hợp nhu cầu vận hành.

Bài này dùng **Spring Boot 3.3.x, Spring MVC và Spring Security 6.x**. Bài thực hành cố định Spring Boot 3.3.13, Java 21 và Maven 3.9+ để có một cấu hình dễ tái lập. Đây là phiên bản dùng để học hành vi, không phải khuyến nghị chọn phiên bản mới nhất khi triển khai sản phẩm.

Lộ trình đọc: phân biệt các lớp kiểm soát → so sánh có/không có Spring Security → hiểu lúc cấu hình mặc định rút lui → chạy ba tình huống → giải thích kết quả HTTP.

## 2. Ba lớp không được đánh đồng

### 2.1. Bật chức năng của endpoint

Trong Spring Boot 3.3, thuộc tính dạng `management.endpoint.<id>.enabled` điều khiển việc bật endpoint. Nếu endpoint cần thêm thư viện hoặc bean hỗ trợ thì các điều kiện đó cũng phải được đáp ứng.

Ví dụ, việc yêu cầu công bố một endpoint không thể tự tạo thư viện tích hợp mà endpoint đó cần.

### 2.2. Công bố qua HTTP

`management.endpoints.web.exposure.include` chọn các endpoint được công bố qua HTTP; `exclude` loại bỏ và được ưu tiên nếu một ID đồng thời có trong cả hai danh sách.

Ở cấu hình mặc định của Spring Boot 3.3, chỉ `health` được công bố qua HTTP. Vì vậy, chưa thêm Spring Security mà gọi `/actuator/info` nhận 404 không chứng minh rằng endpoint này đã được bảo vệ bằng đăng nhập. Có thể đơn giản là nó chưa được công bố. [Spring Boot 3.3: Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

Ví dụ công bố có chủ đích:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
```

Đoạn YAML này không khai báo tài khoản, mật khẩu hoặc vai trò.

### 2.3. Quyền gọi HTTP

Khi Spring Security thực sự được cấu hình cho ứng dụng web, yêu cầu có thể đi qua các bộ lọc trước khi tới endpoint. Các bộ lọc xác thực người gọi, áp dụng quy tắc quyền và thực hiện những bảo vệ như CSRF.

```text
Yêu cầu HTTP
  → các lớp mạng/proxy, nếu có
  → chuỗi bộ lọc bảo mật áp dụng cho yêu cầu, nếu có
  → ánh xạ HTTP của ứng dụng
  → endpoint Actuator
```

Vì bộ lọc chạy trước phần xử lý endpoint, một yêu cầu có thể bị từ chối trước khi ứng dụng xác định đường đó có tồn tại hay không. Đây là lý do không thể dùng riêng mã 401 để suy ra một endpoint đã được công bố. [Spring Security: Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

## 3. Trường hợp không có Spring Security

Giả sử ứng dụng chỉ có các dependency web và Actuator, không có các thư viện Spring Security cần thiết trên classpath, cũng không có cơ chế xác thực khác do ứng dụng hoặc hạ tầng cung cấp.

Khi đó, Actuator không tự tạo lớp yêu cầu đăng nhập cho những endpoint đã công bố. Nếu máy gọi kết nối được đến ứng dụng, endpoint đó có thể được gọi mà không cần credential.

Hãy xét hai cấu hình:

- **Cấu hình Actuator mặc định:** health được công bố; info chưa được công bố.
- **Cấu hình mở thêm info:** cả health và info được công bố.

Kết quả GET thông thường trong ứng dụng khỏe, không có bộ lọc riêng:

| Cấu hình | GET /actuator/health, ẩn danh | GET /actuator/info, ẩn danh |
| --- | --- | --- |
| Chỉ công bố mặc định | 200 | 404 |
| Công bố health và info | 200 | 200 |

Đây là bảng cho những giả định đã nêu. Nếu health báo tình trạng lỗi, mã trả về có thể khác 200; nếu gateway phía trước yêu cầu đăng nhập, kết quả quan sát tại gateway cũng sẽ khác.

### Những điều không tự tạo ra bảo mật ứng dụng

- Chỉ thêm `spring.security.user.name` và `spring.security.user.password` vào YAML trong khi thiếu cơ chế Spring Security tương ứng.
- Chỉ đổi đường `/actuator` thành một tên khó đoán.
- Chỉ đổi cổng quản trị.
- Chỉ ẩn bớt nội dung hoặc che giá trị nhạy cảm trong phản hồi.

Mỗi thay đổi có mục đích riêng. Muốn chứng minh có xác thực, phải kiểm tra yêu cầu thiếu credential, sai credential và đúng credential trên endpoint đang công bố.

Nếu chủ động bảo vệ bằng gateway/firewall thay cho xác thực trong ứng dụng, cần kiểm chứng cả đường bỏ qua gateway. Một lần thử qua tên miền không đại diện cho mọi đường tới backend.

## 4. Trường hợp có Spring Security và chưa có cấu hình chuỗi riêng

### 4.1. Điều kiện của bảo mật mặc định

Cách phổ biến để thêm Spring Security là dependency `spring-boot-starter-security`. Tuy nhiên, điều kiện thực tế dựa vào các lớp/bean có mặt trong ứng dụng, không chỉ việc nhìn thấy một dòng starter trong file build. Dependency khác có thể kéo Spring Security vào theo quan hệ bắc cầu.

Trong ứng dụng Servlet của Spring Boot 3.3, cấu hình bảo mật quản trị mặc định yêu cầu các lớp Spring Security tương ứng và không có bean `SecurityFilterChain` do ứng dụng cung cấp. [DefaultWebSecurityCondition 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/security/DefaultWebSecurityCondition.java)

Các phần sau giả định auto-configuration chưa bị loại bỏ và chưa có cấu hình OAuth2 hoặc cơ chế xác thực thay thế làm thay đổi tình huống.

### 4.2. Quy tắc mặc định của Actuator

Cấu hình `ManagementWebSecurityAutoConfiguration` của Spring Boot 3.3.13:

- Cho phép truy cập health mà không bắt buộc đăng nhập.
- Yêu cầu người gọi đã được xác thực đối với các yêu cầu còn lại.
- Hỗ trợ HTTP Basic và đăng nhập bằng biểu mẫu.

Quy tắc “các yêu cầu còn lại” trong chuỗi mặc định còn bao phủ yêu cầu ứng dụng thông thường; không nên hiểu đây chỉ là mật khẩu cho riêng một vài đường Actuator. [Mã nguồn cấu hình bảo mật quản trị 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/security/servlet/ManagementWebSecurityAutoConfiguration.java)

Điểm dễ nhầm: quy tắc mặc định yêu cầu **đã xác thực**, chưa tự yêu cầu một vai trò như `ADMIN` hoặc `OPS`. Nếu muốn phân biệt người dùng nghiệp vụ với người vận hành, phải đặt chính sách quyền phù hợp.

### 4.3. Tài khoản mặc định là công cụ phát triển

Trong tình huống đơn giản chưa tự cung cấp cơ chế xác thực, Spring Boot tạo một tài khoản trong bộ nhớ, tên mặc định `user`, với mật khẩu sinh khi khởi động. Có thể cấu hình tên/mật khẩu bằng `spring.security.user.*`.

HTTP Basic hay chuyển tới biểu mẫu đăng nhập được chọn theo thương lượng nội dung của yêu cầu, trong đó có header `Accept`. Vì thế trình duyệt có thể nhận chuyển hướng, còn một yêu cầu API nhận 401. [Spring Boot 3.3: Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)

Mật khẩu sinh cho phát triển không phải thiết kế quản lý danh tính cho production. Không sao chép mật khẩu từ log vào tài liệu, dữ liệu công khai hoặc kho mã.

### 4.4. Bảng so sánh khi cùng công bố health và info

Giả định: ứng dụng khỏe, endpoint tồn tại, dùng GET, chưa có chuỗi bảo mật riêng. Với yêu cầu ẩn danh cần xác thực, chọn `Accept: application/json` để quan sát theo cách gọi API.

| Yêu cầu | Không Spring Security | Spring Security mặc định |
| --- | --- | --- |
| Health, không gửi credential | 200 | 200 |
| Info, không gửi credential | 200 | 401 |
| Info, gửi tài khoản/mật khẩu sai | Không có cơ chế Spring Security để xác minh credential đó | 401 |
| Info, gửi tài khoản hợp lệ | 200, không phải do credential được xác minh | 200 |
| API nghiệp vụ /api/ping, ẩn danh | 200 nếu controller tồn tại | 401 |
| Info, tài khoản hợp lệ nhưng không có vai trò OPS | 200 | Vẫn 200 vì mặc định chưa đặt yêu cầu OPS |

Không dùng hàng “credential sai” của trường hợp không Spring Security để suy luận credential đó đã được chấp nhận. Nó có thể chỉ là dữ liệu không được dùng.

## 5. Health công khai có nghĩa gì?

Cho phép health ẩn danh giúp các công cụ kiểm tra tình trạng hoạt động gọi mà không cần tài khoản. Đây là lựa chọn mặc định thuận tiện; hệ thống cụ thể có thể muốn hạn chế thêm.

Cần tách **quyền gọi endpoint** khỏi **mức chi tiết của dữ liệu trả về**:

```yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
```

Cấu hình này giữ phản hồi health gọn; nó không yêu cầu đăng nhập và không lọc địa chỉ IP. Nếu đổi sang chế độ hiển thị chi tiết theo quyền, phải kiểm tra riêng danh tính/vai trò và dữ liệu thực tế trả về.

Một lưu ý khác: `permitAll` là quy tắc cấp quyền, không phải lệnh bỏ qua mọi bộ lọc. Nếu máy gọi chủ động gửi một header HTTP Basic sai, bộ lọc xác thực vẫn có thể trả 401 ngay cả khi đường health cho phép người ẩn danh. Vì vậy, khi thử health ẩn danh, hãy bỏ hẳn header credential thay vì gửi một tài khoản sai. [Spring Security: Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)

Trong bài thực hành, các lệnh gọi health ẩn danh đều không gửi credential.

## 6. Khi tự khai báo SecurityFilterChain: quyền sở hữu thay đổi

### 6.1. Cấu hình mặc định rút lui, không ghép thêm một lớp bảo vệ vô hình

Nếu ứng dụng khai báo bean `SecurityFilterChain` riêng, không được tiếp tục dựa vào quy tắc mặc định của Boot để bảo vệ các đường còn lại. Phải tự xác định chuỗi áp dụng cho Actuator và cho API nghiệp vụ.

Ví dụ nguy hiểm sau là **đoạn minh họa cấu hình thiếu phạm vi**, không phải chương trình đầy đủ:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
    http.httpBasic(withDefaults());
    return http.build();
}
```

Chuỗi này chỉ nhận yêu cầu khớp `/api/**`. Nếu đây là chuỗi duy nhất và không có lớp bảo vệ khác, endpoint Actuator nằm ngoài phạm vi đó không được chuỗi này bảo vệ. Việc tạo bean riêng đã khiến cấu hình mặc định rút lui; Boot không tự tạo một chuỗi bổ sung để sửa phần bỏ sót.

Phải phân biệt:

- `securityMatcher(...)`: chọn yêu cầu nào được xử lý bởi cả chuỗi.
- `requestMatchers(...)` trong `authorizeHttpRequests`: chọn quy tắc quyền bên trong chuỗi đã được chọn.

Khi có nhiều chuỗi, chỉ chuỗi đầu tiên phù hợp được áp dụng; phải thiết kế thứ tự và chuỗi bao phủ phần còn lại. [HttpSecurity 6.3 API](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html), [Spring Security: Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)

Bài thực hành dùng một chuỗi bao phủ mọi yêu cầu để làm rõ thay đổi chính sách, chưa cần chia nhiều chuỗi.

### 6.2. Tùy biến chuỗi khác với tùy biến nơi lưu tài khoản

Hai loại bean có trách nhiệm khác nhau:

| Thành phần | Câu hỏi nó giải quyết |
| --- | --- |
| SecurityFilterChain | Đường nào dùng cơ chế bảo mật nào, yêu cầu quyền gì? |
| UserDetailsService | Lấy thông tin tài khoản phục vụ xác thực từ đâu? |
| PasswordEncoder | Mã hóa/kiểm tra mật khẩu theo thuật toán nào? |

Chỉ thêm một `UserDetailsService` không đồng nghĩa mọi đường đã được cho phép. Ngược lại, chỉ thêm chuỗi riêng cũng không mặc nhiên tắt cấu hình tạo tài khoản mặc định. Auto-configuration cho nguồn tài khoản có các điều kiện rút lui riêng. [UserDetailsServiceAutoConfiguration 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/security/servlet/UserDetailsServiceAutoConfiguration.java)

## 7. Thực hành: cùng ứng dụng, ba tình huống bảo mật

Các lệnh shell bên dưới dùng Bash và `curl`; trong PowerShell có thể dùng `curl.exe` và điều chỉnh cú pháp xuống dòng. Mọi địa chỉ HTTP của lab đều là loopback. Credential ghi trong ví dụ chỉ dùng cho lab; khi đi qua mạng thật phải có TLS và cơ chế quản lý bí mật phù hợp.

### 7.1. Tạo dự án chưa có Spring Security

Cấu trúc ban đầu:

```text
actuator-security-lab/
├── pom.xml
└── src/main/
    ├── java/lab/ActuatorSecurityApplication.java
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
    <artifactId>actuator-security-lab</artifactId>
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

Nội dung `src/main/java/lab/ActuatorSecurityApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorSecurityApplication.class, args);
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong\n";
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
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
      show-components: never
```

Ứng dụng dùng dependency Spring Boot, nên biên dịch và đóng gói bằng Maven thay vì chạy `javac` độc lập trên một file:

```bash
mvn clean package
java -jar target/actuator-security-lab-1.0.0.jar
```

Lần đầu cần truy cập kho Maven. Đợi ứng dụng khởi động thành công, bảo đảm không có tiến trình khác dùng cổng 8080. Giữ ứng dụng chạy trong một terminal và dùng terminal khác để gọi.

### 7.2. Tình huống A: không có Spring Security

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/ping
```

Với ứng dụng khỏe và đúng cấu hình, stdout của ba lệnh lần lượt:

```text
200
200
200
```

Gọi API lấy nội dung:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8080/api/ping
```

Stdout:

```text
pong
```

Để phân biệt không công bố với yêu cầu xác thực, thử một endpoint chưa nằm trong danh sách include:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/env
```

Stdout dự kiến là `404`. Lý do trong lab này là env chưa được công bố qua HTTP, không phải Spring Security đã bảo vệ nó.

### 7.3. Tình huống B: thêm Spring Security, giữ bảo mật mặc định

Dừng JVM bằng Ctrl+C. Thêm dependency sau **bên trong phần `<dependencies>` của POM hiện có**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Chưa tạo bất kỳ class cấu hình bảo mật nào. Đóng gói lại rồi khởi động với một tài khoản lab cố định:

```bash
mvn clean package
java -jar target/actuator-security-lab-1.0.0.jar \
  --spring.security.user.name=observer \
  --spring.security.user.password=lab-observer-only \
  --spring.security.user.roles=VIEWER
```

Các tham số này chỉ giúp tái lập bài thực hành. Không dùng mật khẩu thật trên dòng lệnh hoặc ghi credential triển khai vào kho mã.

Thử năm yêu cầu:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:wrong-password \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:lab-observer-only \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/ping
```

Stdout dự kiến, theo đúng thứ tự:

```text
200
401
401
200
401
```

Điều quan sát được:

1. Health vẫn gọi được khi không gửi credential.
2. Info đã công bố nhưng yêu cầu xác thực.
3. Gửi credential sai không vượt qua xác thực.
4. Tài khoản hợp lệ với vai trò VIEWER vẫn đọc info vì cấu hình mặc định chỉ yêu cầu đã xác thực.
5. API nghiệp vụ cũng bị bảo vệ bởi chuỗi mặc định.

Để xem header, dùng `-i` thay cho việc bỏ body. Không thêm `-L` khi muốn quan sát chuyển hướng ban đầu; tùy chọn đó có thể đưa người đọc tới trang đăng nhập và che mất mã 302 đầu tiên.

### 7.4. Tình huống C: tự đặt quyền OPS cho Actuator

Dừng JVM. Giữ dependency security của tình huống B, rồi tạo file mới `src/main/java/lab/LabSecurityConfig.java`.

Chính sách của ví dụ:

- Health cho phép người ẩn danh.
- Những endpoint Actuator còn lại yêu cầu vai trò OPS.
- Những yêu cầu khác phải có người dùng đã xác thực.
- Dùng HTTP Basic; giữ bảo vệ CSRF mặc định.
- Dùng hai tài khoản trong bộ nhớ để so sánh kết quả.

```java
package lab;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class LabSecurityConfig {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
            .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
            .anyRequest().authenticated()
        );
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(PasswordEncoder encoder) {
        var observer = User.withUsername("observer")
            .password(encoder.encode("lab-observer-only"))
            .roles("VIEWER")
            .build();

        var operator = User.withUsername("operator")
            .password(encoder.encode("lab-operator-only"))
            .roles("OPS")
            .build();

        return new InMemoryUserDetailsManager(observer, operator);
    }
}
```

`roles("OPS")` tạo authority `ROLE_OPS`; `hasRole("OPS")` kiểm tra authority theo quy ước này. Trong ví dụ, không viết `hasRole("ROLE_OPS")`.

Các matcher của health phải đứng trước matcher bao quát Actuator để chính sách cho health được chọn trước. `EndpointRequest` nhận diện đường của endpoint; `toAnyEndpoint()` còn bao gồm đường discovery ở base path. Cách này biểu đạt ý định rõ hơn việc lặp lại chuỗi đường dẫn trong nhiều chỗ. [EndpointRequest 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

`http` trong ví dụ không có `securityMatcher` thu hẹp phạm vi. Vì thế `anyRequest().authenticated()` bao phủ phần còn lại, tránh lỗ hổng bỏ sót API khi tùy biến Actuator. Đây là chính sách của bài lab; sản phẩm có thể cần quyền chi tiết hơn cho từng endpoint hoặc API.

Hai tài khoản này được tạo bởi `labUsers`, không phải bởi cấu hình tài khoản mặc định của Boot. Bỏ các tham số `spring.security.user.*` khi khởi động tình huống C:

```bash
mvn clean package
java -jar target/actuator-security-lab-1.0.0.jar
```

Kiểm tra lại:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:lab-observer-only \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u operator:lab-operator-only \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:lab-observer-only \
  http://127.0.0.1:8080/api/ping
```

Stdout dự kiến:

```text
200
401
403
200
200
```

Lần này, observer xác thực thành công nhưng bị từ chối đọc info vì thiếu OPS. Operator có OPS nên được đọc. Observer vẫn gọi API nghiệp vụ được vì chính sách ở đó chỉ yêu cầu đã xác thực.

Điểm thay đổi từ B sang C là **quy tắc quyền và nguồn tài khoản do ứng dụng sở hữu**, không phải việc info được công bố hay chưa. Danh sách exposure vẫn giữ nguyên.

## 8. Tại sao đăng nhập đúng mà POST vẫn nhận 403?

Xác thực đúng chưa đủ để mọi yêu cầu được xử lý. Một yêu cầu có thể còn phải đáp ứng vai trò, CSRF, phương thức HTTP và các điều kiện riêng của thao tác.

Spring Security bật CSRF mặc định cho các phương thức không an toàn như POST. Một request thiếu token có thể bị từ chối ngay tại bộ lọc CSRF. Vì thế, không được tự kết luận 403 luôn có nghĩa mật khẩu sai hoặc thiếu vai trò. [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)

### Thử riêng với endpoint loggers trong lab

Để kiểm chứng hiện tượng, dừng tình huống C rồi khởi động lại bằng danh sách exposure bổ sung loggers:

```bash
java -jar target/actuator-security-lab-1.0.0.jar \
  --management.endpoints.web.exposure.include=health,info,loggers
```

Trong terminal khác:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u operator:lab-operator-only \
  http://127.0.0.1:8080/actuator/loggers/lab

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -u operator:lab-operator-only \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -X POST \
  --data '{"configuredLevel":"INFO"}' \
  http://127.0.0.1:8080/actuator/loggers/lab
```

Với đúng cấu hình đã nêu, stdout dự kiến:

```text
200
403
```

GET chứng minh tài khoản có thể đọc endpoint. POST trong lab không gửi CSRF token nên bị từ chối theo cấu hình mặc định; không có thay đổi mức ghi log từ yêu cầu bị chặn đó.

Không sửa bằng cách tắt toàn bộ CSRF chỉ để làm bài thử trả 2xx. Cần xác định cách máy gọi xác thực, có dùng trình duyệt/cookie hay credential tự gửi kèm không, rồi quyết định cách cấp token hoặc phạm vi ngoại lệ có chủ đích. “API dùng Basic” hay “không lưu session” riêng lẻ chưa đủ để kết luận không có nguy cơ CSRF.

Sau thử nghiệm, dừng ứng dụng và trở lại danh sách endpoint cần dùng. Bài này chưa hướng dẫn mở quyền ghi loggers cho môi trường thật.

## 9. Đọc đúng 401, 403, 404 và 302

| Quan sát | Cách hiểu phù hợp | Không nên suy luận |
| --- | --- | --- |
| 401 với Basic/API | Yêu cầu chưa đáp ứng xác thực tại lớp trả lỗi | Endpoint chắc chắn tồn tại |
| 403 | Một lớp từ chối quyền hoặc bảo vệ như CSRF | Mật khẩu chắc chắn sai |
| 404 | Không có tài nguyên/ánh xạ tại đường đang được xử lý, hoặc lớp trước che đường đó | Đã có đăng nhập hoặc endpoint không tồn tại trong mọi cấu hình |
| 302 tới trang đăng nhập | Cơ chế đăng nhập bằng biểu mẫu đang yêu cầu tương tác | Spring Security chưa hoạt động |
| 200 | Yêu cầu hiện tại được phục vụ thành công | Mọi người gọi khác đều có cùng quyền |
| 503 từ health | Có thể phản ánh tình trạng sức khỏe của ứng dụng | Cơ chế xác thực nhất thiết bị lỗi |

Khi cần xác định endpoint chưa công bố hay chỉ đang bị bộ lọc chặn, dùng tài khoản hợp lệ với quyền phù hợp, kiểm tra cấu hình exposure và xác nhận đúng port/base path.

Ví dụ: trong tình huống B, gọi env ẩn danh có thể nhận 401 trước khi tới phần định tuyến. Sau khi xác thực hợp lệ, env vẫn chưa được công bố nên mới có thể quan sát 404. Đừng mở endpoint để “sửa” 401 khi nguyên nhân thực tế là thiếu credential.

Với health ẩn danh trong lab, gửi nhầm credential cũng thay đổi phép thử. Kiểm tra cả header mà công cụ tự thêm hoặc credential được trình duyệt/công cụ HTTP lưu lại từ lần trước.

## 10. Những thay đổi nào làm kết luận mặc định không còn áp dụng?

### 10.1. Dependency và bean thực tế

“Không khai báo starter-security trực tiếp” chưa chắc là “không có Spring Security”. Có thể kiểm tra quan hệ dependency của dự án Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security:*
```

Trong shell tự mở rộng dấu `*`, đặt cả tham số `-Dincludes=org.springframework.security:*` trong dấu nháy. Đọc dependency tree và các bean đã đăng ký thay vì chỉ nhìn một file POM.

Khi chẩn đoán auto-configuration, có thể chạy lab với `--debug` rồi xem báo cáo điều kiện trong log cục bộ. Không cần mở endpoint conditions ra mạng để làm bước kiểm tra này.

### 10.2. Servlet và Reactive

Các class Java trong bài dùng Spring MVC: `HttpSecurity`, `SecurityFilterChain` và `EndpointRequest` ở package `...security.servlet`.

Ứng dụng WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và bộ matcher tương ứng ở package reactive. Không chép nguyên cấu hình Servlet vào WebFlux rồi coi như đã bảo vệ xong. Mục đích so sánh vẫn là xác định bảo mật mặc định và phần tùy biến, nhưng API/điều kiện cấu hình phải theo đúng web stack.

### 10.3. Cổng, đường dẫn và lớp hạ tầng

Dùng cổng quản trị riêng có thể giúp phân tách đường mạng; nó không tự tạo tài khoản hoặc yêu cầu vai trò. Đổi base path cũng không thay thế kiểm tra quyền. [Spring Boot 3.3: Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Nếu proxy trả 401 trước JVM, kết quả đó phản ánh chính sách proxy. Muốn kết luận cấu hình Spring Security, phải biết yêu cầu đã đi tới lớp nào; đồng thời không để tồn tại một đường backend trực tiếp bỏ qua lớp bảo vệ dự kiến.

### 10.4. Phiên bản Spring Boot

Ví dụ này dùng hợp đồng cấu hình của 3.3.x. Không trộn các thuộc tính của Boot thế hệ khác vào rồi coi mọi kết quả mặc định là tương đương.

Khi nâng phiên bản, chạy lại ma trận truy cập theo danh tính và thao tác. Việc ứng dụng khởi động thành công không đủ để chứng minh quy tắc bảo mật được giữ nguyên.

## 11. Các hiểu nhầm cần tự phát hiện

| Hiểu nhầm | Cách kiểm tra hoặc sửa tư duy |
| --- | --- |
| Có Actuator thì tự có mật khẩu | Tách dependency Actuator khỏi cơ chế xác thực; thử endpoint đang công bố khi không gửi credential |
| Không thấy info nên cho rằng đã bảo vệ | Kiểm tra danh sách exposure trước |
| Include health,info nghĩa là chỉ quản trị viên được gọi | Include chọn khả năng công bố, không chọn danh tính |
| Có Spring Security thì mọi endpoint yêu cầu ADMIN | Kiểm tra quy tắc thực tế; mặc định cơ bản yêu cầu đã xác thực ngoài health |
| Tạo chuỗi cho /api/** là Boot vẫn bảo vệ Actuator | Kiểm tra phạm vi chuỗi và việc auto-configuration rút lui |
| Thêm UserDetailsService nghĩa là tắt bảo mật HTTP | Tách nguồn tài khoản khỏi quy tắc đường dẫn |
| permitAll bỏ qua mọi bộ lọc | Nó quyết định cấp quyền; xác thực hoặc bảo vệ khác vẫn có thể từ chối |
| Đúng tài khoản thì POST phải thành công | Kiểm tra vai trò, CSRF và yêu cầu của thao tác |
| Mọi 403 đều do thiếu vai trò | Xem cả bộ lọc CSRF và lớp proxy |
| Che giá trị nhạy cảm nghĩa là có thể công bố toàn bộ endpoint | Đánh giá cả dữ liệu cấu trúc, thao tác quản trị và phạm vi người được gọi |
| Bảo vệ HTTP nghĩa là đã bảo vệ JMX | Kiểm kê kênh JMX riêng nếu được bật; SecurityFilterChain là cơ chế HTTP Servlet |
| Chỉ thử với tài khoản quản trị là đủ | Thử thêm người ẩn danh, sai mật khẩu và người xác thực nhưng thiếu quyền |

Không tái sử dụng nguyên credential hoặc chính sách rộng của lab cho production. Phần giá trị của ví dụ là cách kiểm tra và giải thích sự khác nhau giữa ba tình huống.

## 12. Bài tập kiểm tra hiểu biết

### Bài tập 1: vì sao thêm security không làm info xuất hiện?

Ứng dụng giữ exposure mặc định, sau đó thêm starter-security. Một người có tài khoản hợp lệ vẫn không đọc được info.

**Hướng phân tích:** xác thực chỉ xử lý quyền của yêu cầu; nó không bổ sung info vào danh sách HTTP exposure. Cần xác định đúng cổng/đường, danh sách endpoint và kết quả với credential hợp lệ trước khi sửa.

### Bài tập 2: người dùng nghiệp vụ đọc được info

Ứng dụng công bố health và info, có Spring Security mặc định. Người dùng mang vai trò CUSTOMER đăng nhập thành công và đọc được info.

**Hướng phân tích:** điều này có thể đúng với chính sách mặc định chỉ yêu cầu đã xác thực. Nếu nhu cầu là OPS mới được đọc, phải đặt chính sách riêng và thử lại với người thiếu OPS.

### Bài tập 3: một thay đổi nhỏ làm Actuator không còn được chuỗi bảo vệ

Nhóm phát triển thêm đúng một `SecurityFilterChain` có `securityMatcher("/api/**")`. Actuator vẫn được công bố nhưng không có chuỗi nào khác nhận yêu cầu của nó.

**Hướng phân tích:** phải xem cả việc Boot rút lui lẫn phạm vi matcher. Giải pháp là xác định đầy đủ quyền sở hữu mọi đường cần bảo vệ, bằng một chuỗi bao phủ hoặc nhiều chuỗi có thứ tự/phạm vi đúng.

### Bài tập 4: lập ma trận xác minh trước khi thay đổi cấu hình

Với mỗi endpoint cần dùng, ghi:

- Endpoint đã bật và được công bố chưa.
- Chuỗi nào nhận yêu cầu.
- Người ẩn danh, credential sai, người đúng mật khẩu nhưng thiếu vai trò, người đủ vai trò nhận kết quả gì.
- GET và thao tác ghi khác nhau ở điều kiện nào.
- Proxy/firewall có làm thay đổi điểm quan sát hay không.

**Tiêu chí tự kiểm tra:** giải thích được mỗi kết quả bằng cấu hình cụ thể. Không chỉ ghi “có Spring Security” hoặc “đã trả 403” rồi kết luận toàn bộ Actuator được bảo vệ đúng.
