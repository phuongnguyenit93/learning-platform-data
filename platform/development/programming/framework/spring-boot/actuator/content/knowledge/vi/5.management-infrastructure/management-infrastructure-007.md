# Cấu hình CORS cho endpoint quản trị khi truy cập từ trình duyệt

## 1. CORS giải quyết vấn đề gì?

Một trang quản trị ở `http://127.0.0.1:5173` cần đọc `http://127.0.0.1:8080/actuator/health`. Máy chủ có thể hoạt động và tài khoản có thể đúng, nhưng JavaScript vẫn không đọc được phản hồi vì hai địa chỉ khác nguồn. CORS (Cross-Origin Resource Sharing, chia sẻ tài nguyên giữa các nguồn) giúp máy chủ công bố những nguồn trình duyệt được phép đọc phản hồi.

Trong hạ tầng quản trị, hãy xác định có thực sự cần gọi chéo nguồn không, endpoint nào được công bố qua HTTP, ai có quyền gọi, rồi cấu hình CORS vừa đủ cho trang quản trị. Thêm một nguồn vào CORS không cấp tài khoản hay vai trò cho người dùng.

Bài dùng **Spring Boot 3.3.13, Java 21, Spring MVC/Servlet và Spring Security đi kèm Boot**. Đây là phiên bản cố định cho thí nghiệm, không phải tuyên bố về phiên bản mới nhất. Nhóm thuộc tính CORS của Actuator cũng dùng được với WebFlux; mã `HttpSecurity` trong bài chỉ dành cho Servlet. Ứng dụng reactive cần dùng API bảo mật tương ứng.

## 2. Nhận diện đúng nguồn của trang gọi

Với URL HTTP/HTTPS thông thường, nguồn (origin) gồm **giao thức + tên máy chủ + cổng hiệu lực**; đường dẫn không tham gia so sánh. Lấy nguồn máy chủ `http://127.0.0.1:8080` làm mốc:

| Địa chỉ trang đang mở | Quan hệ với nguồn máy chủ |
| --- | --- |
| `http://127.0.0.1:8080/admin/index.html` | Cùng nguồn, dù đường dẫn khác |
| `http://127.0.0.1:5173` | Khác cổng, khác nguồn |
| `http://localhost:8080` | Khác tên máy chủ, khác nguồn |
| `https://127.0.0.1:8080` | Khác giao thức, khác nguồn |

`allowed-origins` chứa **nguồn của trang gọi**, ví dụ `http://127.0.0.1:5173`, không chứa URL endpoint đích, `/admin`, `/actuator/health` hay dấu `/` cuối. `localhost` và `127.0.0.1` cùng trỏ về máy hiện tại vẫn là hai tên máy chủ khác nhau. Khái niệm nguồn được quy định trong [RFC 6454](https://www.rfc-editor.org/rfc/rfc6454#section-3.2).

Chỉ bật CORS khi trình duyệt có nhu cầu gọi chéo nguồn. Trang được phục vụ cùng nguồn và gọi đường dẫn tương đối `/actuator/health` không cần mở nguồn khác cho tình huống đó. Prometheus, ứng dụng phía máy chủ và `curl` không chịu cơ chế chặn đọc của trình duyệt; chúng vẫn chịu xác thực, phân quyền, TLS và giới hạn mạng.

## 3. CORS liên hệ với bảo mật Actuator như thế nào?

| Lớp kiểm soát | Câu hỏi phải trả lời | Ví dụ trong bài |
| --- | --- | --- |
| Bật/công bố endpoint | Endpoint có tồn tại và được ánh xạ HTTP không? | Chỉ công bố `health` |
| Mạng và TLS | Máy gọi có tiếp cận đúng địa chỉ, cổng, chứng chỉ không? | Demo chỉ lắng nghe ở loopback |
| Xác thực/phân quyền | Danh tính nào được phép thực hiện yêu cầu thật? | Vai trò `ACTUATOR_READ` |
| CORS | JavaScript từ nguồn nào được phép đọc phản hồi? | Chỉ nguồn cổng `5173` |

`management.endpoints.web.exposure.include` không thay thế cấu hình bảo mật. Khi tự khai báo `SecurityFilterChain`, ứng dụng phải tự bảo đảm quy tắc truy cập phù hợp, vì cấu hình bảo mật tự động liên quan sẽ lùi lại. Xem [Actuator endpoints và bảo mật của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Không dùng CORS như tường lửa: chương trình ngoài trình duyệt có thể bỏ hoặc tự đặt header `Origin`. Console báo lỗi CORS cũng không chứng minh yêu cầu chưa tới máy chủ. Một số yêu cầu được gửi trước khi trình duyệt quyết định cho JavaScript đọc phản hồi; các thao tác thay đổi trạng thái vẫn cần biện pháp bảo vệ riêng, bao gồm CSRF khi phù hợp.

## 4. Hiểu preflight trước khi cấu hình

Trình duyệt không gửi `OPTIONS` trước mọi `GET`. Khi yêu cầu đủ điều kiện gửi trực tiếp, nó có thể gửi yêu cầu thật ngay. Khi JavaScript tự thêm `Authorization`, trình duyệt thường cần yêu cầu thăm dò (preflight) trước, trừ khi đã có kết quả phù hợp trong bộ nhớ đệm.

Luồng của thí nghiệm có xác thực:

1. Trang cổng `5173` muốn gửi `GET /actuator/health` kèm `Authorization`.
2. Trình duyệt gửi `OPTIONS` tới endpoint với `Origin`, `Access-Control-Request-Method: GET` và `Access-Control-Request-Headers: authorization`.
3. Máy chủ kiểm tra nguồn, phương thức **dự định dùng cho yêu cầu thật** và các header đề nghị, rồi trả header cho phép nếu hợp lệ.
4. Trình duyệt gửi `GET` có thông tin xác thực; Spring Security kiểm tra danh tính và vai trò.
5. Phản hồi của `GET` cũng phải có header CORS phù hợp để JavaScript đọc được.

Preflight không mang mật khẩu/token của yêu cầu thật. Nếu lớp bảo mật đòi đăng nhập ngay ở `OPTIONS`, trình duyệt chưa thể tới bước `GET`. Chỉ thêm `permitAll()` cho `OPTIONS` cũng chưa tạo ra header CORS. Phải tích hợp CORS vào đúng chuỗi bảo mật để xử lý trước xác thực. Xem [Spring Security: tích hợp CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).

`allowed-methods: GET` nói về phương thức của yêu cầu thật. Không phải thêm `OPTIONS` chỉ để phục vụ preflight cho `GET`; thêm `OPTIONS` cũng không làm `POST` hợp lệ.

## 5. Nhóm thuộc tính CORS của Actuator

Nhóm cấu hình là **`management.endpoints.web.cors`**. Khi chưa khai báo nguồn qua `allowed-origins` hoặc `allowed-origin-patterns`, hỗ trợ CORS của Actuator chưa được bật. Với vài trang quản trị đã biết, ưu tiên danh sách nguồn cụ thể.

| Thuộc tính dưới `management.endpoints.web.cors` | Ý nghĩa | Lựa chọn cho ví dụ |
| --- | --- | --- |
| `allowed-origins` | Nguồn của trang gọi | `http://127.0.0.1:5173` |
| `allowed-methods` | Phương thức của yêu cầu thật được chấp nhận | `GET` |
| `allowed-headers` | Header yêu cầu được chấp nhận khi kiểm tra preflight | `Authorization` |
| `exposed-headers` | Header phản hồi bổ sung mà JavaScript được đọc | Không cần thêm |
| `allow-credentials` | Cho phép phản hồi dùng với chế độ gửi thông tin xác thực tự động của trình duyệt | `false` |
| `max-age` | Thời gian cho phép lưu kết quả preflight | `10m` |

Tên và kiểu thuộc tính được mô tả trong [bảng thuộc tính Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator.management.endpoints.web.cors.allowed-origins); lớp liên kết cấu hình là [CorsEndpointProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/CorsEndpointProperties.html).

Không nhầm hai hướng header: cho phép JavaScript **gửi** `Authorization` cần `allowed-headers`; cho phép nó **đọc** header phản hồi tùy chỉnh như `X-Trace-Id` liên quan tới `exposed-headers`. `exposed-headers` không tự tạo header đó. Việc máy chủ trả JSON không buộc yêu cầu `GET` phải gửi `Content-Type: application/json`; tránh thêm header không cần thiết làm phát sinh preflight.

Các thuộc tính này đặt chính sách chung cho nhóm web endpoint Actuator, không phải phân quyền riêng cho từng endpoint và không tự cấu hình CORS cho mọi controller nghiệp vụ. Không mặc định rằng `@CrossOrigin` trên controller hoặc cấu hình CORS dành cho controller đã xử lý Actuator. Nếu cần chính sách khác nhau theo endpoint, phải thiết kế phạm vi ánh xạ riêng và kiểm chứng với chuỗi bảo mật, tránh mở toàn bộ `/**` chỉ để thử.

## 6. Ví dụ độc lập: đọc health có xác thực

Đây là dự án thực hành độc lập, không yêu cầu sửa build của module đang học. Cần JDK 21, Maven 3.6.3 trở lên và kết nối tải thư viện khi chạy lần đầu. Kiểm tra `mvn -version` để chắc chắn Maven đang dùng Java 21.

Thiết kế thí nghiệm:

- Máy chủ ở `http://127.0.0.1:8080`, chỉ công bố `health`, không trả chi tiết sức khỏe.
- Trang thử ở `http://127.0.0.1:5173`; các nguồn khác không có trong danh sách.
- Yêu cầu thật dùng HTTP Basic với tài khoản `operator`, vai trò `ACTUATOR_READ`.
- JavaScript chủ động đặt `Authorization` và dùng `credentials: "omit"`, không dựa vào cookie hay thông tin đăng nhập trình duyệt tự gắn.
- Giữ CSRF mặc định, chỉ thực hiện thao tác đọc `GET`.

HTTP Basic giúp thí nghiệm nhỏ chạy độc lập. Chuỗi Basic chỉ được mã hóa Base64, không phải mã hóa bảo mật. Chỉ chạy HTTP này trên loopback; qua mạng phải dùng HTTPS và quản lý danh tính phù hợp. Trang thực hành chỉ nhận tên đăng nhập và mật khẩu ASCII để `btoa` mã hóa trực tiếp.

### 6.1. Cấu trúc thư mục

```text
actuator-cors-demo/
├── pom.xml
├── src/main/java/example/
│   ├── CorsDemoApplication.java
│   └── ManagementSecurity.java
├── src/main/resources/application.yml
└── ui/index.html
```

### 6.2. `pom.xml`

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
  <artifactId>actuator-cors-demo</artifactId>
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

Ba starter cung cấp HTTP Servlet, endpoint quản trị và bảo mật. Không cần viết controller thay thế `health`. Parent quản lý phiên bản thư viện, plugin Boot đóng gói JAR chạy độc lập; xem [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/getting-started.html).

### 6.3. `src/main/java/example/CorsDemoApplication.java`

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

### 6.4. `src/main/java/example/ManagementSecurity.java`

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurity {
    @Bean
    SecurityFilterChain managementAccess(HttpSecurity http) throws Exception {
        http.cors(Customizer.withDefaults());
        http.authorizeHttpRequests(rules -> rules
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR_READ")
                .anyRequest().denyAll());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`EndpointRequest.toAnyEndpoint()` chọn endpoint Actuator theo ánh xạ của Boot. `hasRole("ACTUATOR_READ")` kiểm tra quyền `ROLE_ACTUATOR_READ`; giá trị `spring.security.user.roles` bên dưới không thêm tiền tố `ROLE_`. Demo từ chối mọi yêu cầu ngoài Actuator; ứng dụng nghiệp vụ thật cần quy tắc riêng cho các đường dẫn của nó.

`http.cors(Customizer.withDefaults())` cho Spring Security dùng cấu hình CORS từ các ánh xạ Spring MVC khi không cung cấp nguồn CORS khác. Preflight hợp lệ nhờ đó có thể được xử lý trước xác thực. Nếu dự án đã có `CorsFilter`, `CorsConfigurationSource` hoặc nhiều `SecurityFilterChain`, cần xác định cấu hình và chuỗi thực tế được chọn; không giả định rằng thêm một dòng sẽ ghi đè mọi chính sách có sẵn.

Ví dụ dùng chung cổng ứng dụng và cổng quản trị. Khi cấu hình `management.server.port` riêng, phải thử tại đúng server/context quản trị; một chuỗi lọc ở server nghiệp vụ chưa chứng minh rằng server quản trị đã được bảo vệ đúng.

### 6.5. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  security:
    user:
      name: operator
      password: ${ACTUATOR_PASSWORD}
      roles: ACTUATOR_READ

management:
  endpoint:
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include:
          - health
      discovery:
        enabled: false
      cors:
        allowed-origins:
          - "http://127.0.0.1:5173"
        allowed-methods:
          - GET
        allowed-headers:
          - Authorization
        allow-credentials: false
        max-age: 10m
```

`ACTUATOR_PASSWORD` được cung cấp qua môi trường. Không thêm mật khẩu thật vào YAML hay mã trang. Chỉ công bố `health`, không cần dùng `exposure.include: "*"` để thử CORS. Tắt discovery giúp tập trung thí nghiệm vào URL sức khỏe.

`allow-credentials: false` không làm endpoint công khai: Spring Security vẫn đòi Basic hợp lệ. Header xác thực chủ động được kiểm tra qua `allowed-headers`. Quyết định gửi cookie/thông tin xác thực tự động là vấn đề khác, được giải thích tại mục 8.

### 6.6. `ui/index.html`

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Đọc health qua CORS</title>
</head>
<body>
  <h1>Kiểm tra health có xác thực</h1>
  <form id="reader">
    <label>Tên đăng nhập
      <input name="username" value="operator" required>
    </label>
    <label>Mật khẩu thực hành
      <input name="password" type="password" autocomplete="off" required>
    </label>
    <button type="submit">Đọc health</button>
  </form>
  <pre id="result" aria-live="polite"></pre>
  <script>
    const form = document.getElementById("reader");
    const result = document.getElementById("result");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = form.elements.namedItem("username").value;
      const password = form.elements.namedItem("password");
      result.textContent = "Đang đọc...";
      try {
        const basic = btoa(username + ":" + password.value);
        const response = await fetch("http://127.0.0.1:8080/actuator/health", {
          credentials: "omit",
          headers: { Authorization: "Basic " + basic }
        });
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        result.textContent = JSON.stringify(await response.json(), null, 2);
      } catch (error) {
        result.textContent = error.message;
      } finally {
        password.value = "";
      }
    });
  </script>
</body>
</html>
```

Trang không nhúng sẵn mật khẩu vào mã, không lưu mật khẩu vào `localStorage` và xóa ô mật khẩu sau mỗi lần gọi. `response.ok` được kiểm tra vì `fetch` không tự ném lỗi chỉ vì HTTP trả `401` hay `403`. Đây là trang thực hành, không phải cổng quản trị sản xuất hoàn chỉnh.

### 6.7. Chạy máy chủ và trang

Tại thư mục gốc dự án thực hành, mở PowerShell và nhập mật khẩu ASCII riêng cho lần thử:

```powershell
$labPassword = Read-Host 'Nhập mật khẩu ASCII cho lần thử' -AsSecureString
$env:ACTUATOR_PASSWORD = [System.Net.NetworkCredential]::new('', $labPassword).Password
mvn -q -DskipTests package
java -jar target/actuator-cors-demo-1.0.0.jar
```

Chỉ chạy JAR sau khi Maven đóng gói thành công. Ứng dụng có thư viện ngoài nên không dùng `javac` trần thay bước giải quyết phụ thuộc. Có thể dùng `mvn spring-boot:run` thay cho đóng gói và chạy JAR.

Mở terminal thứ hai tại cùng thư mục, dùng công cụ tĩnh của JDK 21:

```powershell
jwebserver -b 127.0.0.1 -p 5173 -d ui
```

Mở đúng **`http://127.0.0.1:5173/`**, nhập cùng mật khẩu rồi nhấn **Đọc health**. Không mở bằng `file://` và không đổi sang `localhost` trong lần thử này. `jwebserver` chỉ phục vụ thư mục `ui`, không phục vụ gốc dự án chứa cấu hình; xem [tài liệu jwebserver của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jwebserver.html).

Khi ứng dụng khỏe, trang hiển thị:

```json
{
  "status": "UP"
}
```

Đây là nội dung endpoint, không phải toàn bộ stdout khởi động Spring Boot. Nếu môi trường làm trạng thái sức khỏe thay đổi, hãy xem trạng thái HTTP và dữ liệu thật, không coi mọi kết quả khác `UP` là lỗi CORS. Dừng hai tiến trình bằng `Ctrl+C`; sau khi dừng máy chủ, có thể xóa biến môi trường trong terminal đó bằng `Remove-Item Env:ACTUATOR_PASSWORD`.

## 7. Kiểm chứng cả preflight và yêu cầu thật

Bảng sau áp dụng cho demo nguyên trạng, endpoint khỏe và cùng cổng `8080`:

| Tình huống | Kết quả cần kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Preflight từ nguồn `5173`, đề nghị `GET` và `authorization` | `200`, có các header CORS tương ứng | CORS chấp nhận đề nghị; chưa chứng minh đăng nhập đúng |
| `GET` từ nguồn `5173`, Basic đúng và đúng vai trò | `200`, JSON sức khỏe và header cho phép nguồn `5173` | CORS và bảo mật cùng đạt |
| `GET` từ nguồn `5173`, không có xác thực | `401`, vẫn có header cho phép nguồn `5173` | CORS hợp lệ, thiếu danh tính |
| Preflight từ nguồn `5174` | `403`, không có header cho phép nguồn đó | Nguồn bị từ chối |
| Preflight từ nguồn `5173`, đề nghị `POST` | `403` | Chính sách chỉ cho phép phương thức thật `GET` |
| Preflight chỉ đề nghị `x-admin-debug` | `403` | Không có header đề nghị nào được cho phép |
| Preflight đề nghị `authorization,x-admin-debug` | Có thể trả `200` nhưng chỉ cho phép `authorization` | Trình duyệt chặn yêu cầu thật vì chưa được phép gửi đủ header |
| `GET` không có `Origin`, Basic đúng | `200` khi endpoint khỏe | Công cụ ngoài trình duyệt không cần CORS để đọc |

### 7.1. Thử preflight không mang mật khẩu

Trong PowerShell trên Windows, dùng `curl.exe` để tránh nhầm bí danh. Mỗi lệnh dưới đây nằm trên một dòng:

```powershell
curl.exe -i -X OPTIONS "http://127.0.0.1:8080/actuator/health" -H "Origin: http://127.0.0.1:5173" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
```

Đối chiếu những phần sau trong phản hồi:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: http://127.0.0.1:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600
```

Đây là phần trích giá trị cần kiểm chứng. Thứ tự/cách viết hoa header, dòng trạng thái và header bổ sung có thể khác theo máy chủ. Không mong chờ `Access-Control-Allow-Credentials: true` vì demo tắt tùy chọn này. `10m` được biểu diễn thành `600` giây trong header.

Thử nguồn bị từ chối:

```powershell
curl.exe -i -X OPTIONS "http://127.0.0.1:8080/actuator/health" -H "Origin: http://127.0.0.1:5174" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
```

Với nguồn `5174`, bộ xử lý mặc định trả `403`, phần thân `Invalid CORS request`. Giữ nguồn đúng rồi đổi phương thức đề nghị thành `POST` cũng bị từ chối. Khi chỉ đề nghị header `x-admin-debug`, không có header đề nghị nào được chấp nhận nên Spring trả `403`. Hành vi từ chối mặc định được nêu tại [DefaultCorsProcessor](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/cors/DefaultCorsProcessor.html).

**Không chỉ nhìn mã `200` của preflight.** Với danh sách hỗn hợp `authorization,x-admin-debug`, trong cấu hình demo Spring trả `200` nhưng `Access-Control-Allow-Headers` chỉ chứa `authorization`. Trình duyệt kiểm tra toàn bộ danh sách đã đề nghị, thấy thiếu `x-admin-debug` nên không gửi yêu cầu thật. Đây là khác biệt giữa máy chủ phản hồi HTTP và trình duyệt hoàn tất kiểm tra CORS. Chỉ thêm header khi thực sự có nhu cầu, không mở rộng chính sách để làm phép thử từ chối thành công.

### 7.2. Thử yêu cầu thật và lỗi xác thực

`curl.exe --user operator` sẽ hỏi mật khẩu, không cần chép mật khẩu vào dòng lệnh:

```powershell
curl.exe -i --user operator "http://127.0.0.1:8080/actuator/health" -H "Origin: http://127.0.0.1:5173"
```

Khi nhập đúng, cần thấy `200`, header `Access-Control-Allow-Origin: http://127.0.0.1:5173` và JSON `{"status":"UP"}` nếu ứng dụng khỏe. Bỏ `--user operator` rồi chạy lại để kiểm tra `401`; header CORS ở lỗi này giúp trang thấy lỗi xác thực thay vì bị che bằng lỗi đọc phản hồi.

Tiếp theo, bỏ `Origin` nhưng giữ xác thực:

```powershell
curl.exe -i --user operator "http://127.0.0.1:8080/actuator/health"
```

`curl` vẫn đọc được phản hồi. Giới hạn nguồn không thay thế kiểm soát danh tính. `curl` chỉ kiểm tra HTTP, không thực thi thuật toán CORS như trình duyệt; thử bằng `curl` thành công chưa chứng minh JavaScript hoạt động.

### 7.3. Quan sát Network của trình duyệt

Ở lần nhấn nút đầu tiên thường thấy `OPTIONS` rồi `GET`. Nếu preflight còn được lưu, có thể chỉ thấy `GET`; dùng phiên duyệt mới hoặc chờ hết thời gian lưu khi cần quan sát lại. Không tự gọi `fetch` với `method: "OPTIONS"` để thay cho preflight do trình duyệt điều khiển.

Ở `OPTIONS`, kiểm tra URL/cổng, `Origin`, phương thức và header đề nghị. Ở `GET`, kiểm tra trạng thái và header cho phép nguồn. JavaScript không thể tự đặt `Origin` để giả lập một nguồn khác; muốn thử bằng trình duyệt, hãy phục vụ trang ở cổng khác. Không chia sẻ ảnh Network chứa `Authorization`.

## 8. Khi cần cookie, phiên đăng nhập hoặc token

### 8.1. Gửi cookie chéo nguồn

Chỉ khi cơ chế đăng nhập thực sự dựa vào cookie/thông tin xác thực tự động, mới cân nhắc `credentials: "include"` ở `fetch` và `allow-credentials: true` ở Actuator. Khi dùng chế độ này phải trả nguồn cụ thể khớp yêu cầu; không dùng `allowed-origins: "*"`. Spring kiểm tra tổ hợp này và có thể báo lỗi khi cấu hình được khởi tạo hoặc sử dụng. Xem [CorsConfiguration của Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/cors/CorsConfiguration.html).

Phần YAML sau chỉ minh họa chính sách CORS cho trang **đã có** đăng nhập bằng cookie; không tự tạo phiên, cookie hay API đăng nhập:

```yaml
management:
  endpoints:
    web:
      cors:
        allowed-origins:
          - "https://ops.example.com"
        allowed-methods:
          - GET
        allow-credentials: true
        max-age: 10m
```

Trang đã đăng nhập có thể gọi:

```javascript
const response = await fetch("https://management.example.com/actuator/health", {
  credentials: "include"
});
if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
const health = await response.json();
```

Đây là đoạn tích hợp, không thay thế toàn bộ demo mục 6. Trình duyệt còn áp dụng `SameSite`, `Secure` và chính sách chặn cookie bên thứ ba; CORS đúng chưa bảo đảm cookie được gửi. `SameSite` xét quan hệ site, CORS xét origin: khác cổng có thể khác origin nhưng chưa chắc khác site. Không tắt CSRF toàn cục để chữa lỗi cookie.

### 8.2. JavaScript chủ động gắn token

Với `Authorization: Bearer ...`, cần cho phép header `Authorization`, kiểm tra cơ chế xác thực token ở máy chủ và giữ phân quyền endpoint. Chỉ có header token không tự yêu cầu đổi `allow-credentials` thành `true`; phải xét chế độ `credentials` và việc có dùng cookie/thông tin xác thực tự động hay không.

Demo mục 6 chủ động gắn Basic cùng `credentials: "omit"` để tách hai quyết định đó. Không suy rộng thành lời khuyên lưu token quản trị lâu dài trong mã trang hay kho trình duyệt. Cơ chế credentials và các header được định nghĩa trong [Fetch Standard, phần CORS](https://fetch.spec.whatwg.org/#http-cors-protocol).

### 8.3. Mẫu nguồn và wildcard

`allowed-origin-patterns` cho phép mẫu linh hoạt hơn `allowed-origins`. Với quản trị, mẫu như `https://*.example.com` chỉ phù hợp khi mọi tên miền con khớp mẫu đều đáng tin; một tên miền con bị chiếm quyền có thể khiến chính sách quá rộng. Không dùng mẫu `"*"` để né quy tắc wildcard khi bật credentials. Vài nguồn cụ thể thường dễ kiểm toán hơn.

## 9. Cổng quản trị riêng và proxy

Nếu chuyển Actuator sang `management.server.port: 9090`, URL đích của trang phải đổi theo server quản trị thực tế. Nguồn cho phép vẫn là **nguồn của trang**, không đổi thành `http://127.0.0.1:9090` chỉ vì máy chủ đổi cổng. Kiểm tra lại địa chỉ lắng nghe, TLS, đường dẫn, tường lửa và chuỗi bảo mật của đúng server quản trị.

Trình duyệt xét URL nhìn thấy được. Nếu proxy phục vụ cả trang và `/management/health` trên cùng giao thức, tên máy chủ, cổng, trang có thể dùng đường dẫn tương đối dù proxy gọi Java nội bộ qua cổng khác. Phải bảo vệ tuyến proxy và quyền truy cập; không mở CORS cho liên lạc nội bộ chỉ vì hai tiến trình khác cổng.

Chọn rõ nơi trả header CORS. Proxy và ứng dụng cùng thêm `Access-Control-Allow-Origin` có thể tạo header lặp hoặc danh sách nguồn sai dạng. Nếu proxy/cache lưu phản hồi phụ thuộc `Origin`, phải giữ đúng `Vary` và cách phân tách cache, tránh phục vụ phản hồi của nguồn này cho nguồn khác.

Trang HTTPS gọi endpoint HTTP còn có thể bị chặn vì nội dung hỗn hợp. DNS, chứng chỉ TLS và CSP `connect-src` cũng có thể ngăn kết nối; đây là những lớp cần kiểm tra riêng, không giải quyết bằng thêm `allowed-origins`.

## 10. Chẩn đoán lỗi thường gặp

| Hiện tượng | Kiểm tra trước | Cách xử lý phù hợp |
| --- | --- | --- |
| `curl` đọc được, JavaScript không đọc được | Lệnh thử có `Origin` không? Nguồn thật của trang là gì? | Kiểm tra bằng trình duyệt và đối chiếu header phản hồi |
| Preflight trả `401` hoặc chuyển hướng đăng nhập | Chuỗi bảo mật nào nhận `OPTIONS`, CORS có tích hợp ở đó không? | Xử lý CORS trước xác thực, tránh chuyển hướng preflight tới trang đăng nhập |
| `GET` trả `401`, CORS đúng | Thông tin xác thực thật | Sửa đăng nhập/token, không mở rộng nguồn |
| `GET` trả `403` sau xác thực | Vai trò, quy tắc quyền; CSRF với thao tác ghi | Tìm đúng lớp từ chối, không coi mọi `403` là CORS |
| Nguồn bị từ chối | `localhost`/`127.0.0.1`, cổng, giao thức, đường dẫn thừa | Khai báo đúng nguồn trang gọi |
| Header bị từ chối | Danh sách `Access-Control-Request-Headers` trong Network | Chỉ thêm header có nhu cầu hợp lệ hoặc bỏ header thừa |
| Preflight đạt, yêu cầu thật thất bại | Trạng thái/header thật, proxy, xác thực | Kiểm tra cả hai phản hồi |
| Endpoint trả `404` | Exposure, base path, cổng và tuyến proxy | Xác minh HTTP mapping; bảo mật/proxy cũng có thể dùng `404` để che đường dẫn |
| Trang `file://` có nguồn `null` | Cách mở trang | Phục vụ bằng HTTP loopback, không mở nguồn `null` chỉ để thử |
| Sửa YAML nhưng thấy kết quả cũ | Khởi động lại ứng dụng, bộ nhớ đệm preflight | Xem cấu hình thực tế, thử phiên duyệt mới |
| Header cho phép nguồn có nhiều giá trị | Proxy và ứng dụng cùng thêm header? | Giữ chính sách nhất quán, không nối nhiều nguồn trong một giá trị header |

Không dùng `mode: "no-cors"` để chữa lỗi: phản hồi opaque không cho JavaScript đọc JSON như mục tiêu của bài. Không cài tiện ích tắt bảo vệ trình duyệt, thêm `@CrossOrigin("*")` khắp nơi hay công bố toàn bộ endpoint chỉ để làm thông báo biến mất.

## 11. Bài thực hành

1. Chạy demo, xác nhận preflight hợp lệ và `GET` có xác thực đều đạt. Giải thích vì sao `OPTIONS` không cần mật khẩu nhưng `GET` vẫn cần.
2. Chạy trang ở cổng `5174`, giữ YAML nguyên trạng. Dự đoán rồi xem Network. Chỉ thêm nguồn mới sau khi xác định đó là nhu cầu hợp lệ.
3. Giữ nguồn đúng nhưng nhập sai mật khẩu. Phân biệt HTTP `401` với việc trình duyệt không cho đọc phản hồi do CORS.
4. Đề nghị `POST`, chỉ `x-admin-debug`, rồi cả `authorization,x-admin-debug`. Phân biệt `403` từ Spring với trường hợp `200` nhưng thiếu header cho phép nên trình duyệt không gửi yêu cầu thật. Giữ nguyên chính sách trong các phép thử.
5. Mô tả phương án đưa trang và tuyến quản trị ra cùng nguồn qua proxy. Nêu rõ lớp xác thực/phân quyền nào vẫn phải tồn tại.

Tự kiểm tra: vì sao phải khai báo nguồn trang thay vì URL endpoint; vì sao preflight đạt chưa chứng minh quyền gọi; `allowed-headers` khác `exposed-headers` ở đâu; và khi nào mới cần `allow-credentials: true`.