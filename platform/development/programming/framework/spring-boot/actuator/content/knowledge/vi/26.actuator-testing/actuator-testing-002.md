# Kiểm thử nội dung, HTTP status và phân quyền của health group

Một health group gom các phép kiểm tra sức khỏe liên quan đến một mục đích vận hành. Ví dụ, nhóm `orders` chỉ tổng hợp tình trạng của thành phần phục vụ đơn hàng. Một phép kiểm thử hữu ích cần xác minh ba kết quả của cùng yêu cầu HTTP. Ai được gọi nhóm? Máy khách nhận mã HTTP nào? Phần JSON nào được hiển thị cho người gọi đó?

## Tách quyền gọi khỏi quyền xem chi tiết

- **Quyền gọi URL** do chuỗi lọc Spring Security quyết định. Trong ví dụ dùng HTTP Basic, yêu cầu thiếu thông tin xác thực nhận 401. Người dùng đã xác thực nhưng thiếu vai trò được phép nhận 403.
- **Quyền xem thành phần và chi tiết** do Actuator áp dụng cho người đã gọi được nhóm. `show-components` điều khiển trường `components`. `show-details` điều khiển thông tin `details`, chẳng hạn chi tiết bên trong một thành phần. Với giá trị `when-authorized`, danh sách `roles` của nhóm quyết định ai được xem. Vì vậy, cùng một trạng thái `UP` có thể xuất hiện trong hai phản hồi HTTP 200 với nội dung khác nhau.
- **Mã HTTP của sức khỏe** được ánh xạ từ trạng thái tổng hợp của các thành phần thuộc nhóm. Ánh xạ mặc định trả 503 cho `DOWN` và `OUT_OF_SERVICE`, còn `UP` trả 200. Hãy kiểm cả mã HTTP và giá trị `status` trong JSON. Một trạng thái chưa có ánh xạ riêng, chẳng hạn `UNKNOWN` theo mặc định, cũng có thể trả 200.

`management.endpoints.web.exposure.include=health` đưa endpoint `health` lên web. Việc mở endpoint, lọc quyền vào URL và quyết định hiển thị chi tiết là ba cấu hình cần đối chiếu riêng.

## Ma trận kiểm thử cho nhóm orders

Nhóm chỉ chứa `ordersBackend`. Mẫu thử cố tình thêm một phép kiểm tra `invoicesBackend` luôn báo `DOWN` ở ngoài nhóm. Điều này giúp phát hiện cả trường hợp gọi nhầm `GET /actuator/health` lẫn trường hợp vô tình đưa thêm thành phần vào nhóm.

| Người gọi | Trạng thái ordersBackend | HTTP | Nội dung cần kiểm |
| --- | --- | --- | --- |
| Chưa xác thực | `UP` | 401 | Bị chặn ở lớp bảo mật. |
| Đã xác thực với vai trò `OTHER` | `UP` | 403 | Bị chặn ở lớp phân quyền. |
| Vai trò `VIEWER` | `UP` | 200 | `status=UP`, không có `components` và `details`. |
| Vai trò `OPS` | `UP` | 200 | Chỉ có thành phần `ordersBackend` với chi tiết `check=ok`. |
| Vai trò `OPS` | `DOWN` | 503 | `status=DOWN`, chi tiết của `ordersBackend` là `check=unavailable`. |

## Ví dụ kiểm thử tích hợp

Ví dụ dùng Java 17, Spring Boot 3.5.9 và Spring Security. Các thuộc tính của health group và nguyên tắc ánh xạ mã HTTP ở đây cũng có trong Spring Boot 3.3. `@SpringBootTest(webEnvironment = RANDOM_PORT)` mở máy chủ nhúng trên một cổng ngẫu nhiên. `TestRestTemplate` gửi yêu cầu qua HTTP và cho phép kiểm tra phản hồi 4xx hoặc 5xx trực tiếp.

Tạo dự án Maven với `pom.xml` sau.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.9</version>
        <relativePath/>
    </parent>
    <groupId>demo.health</groupId>
    <artifactId>health-group-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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
</project>
```

Tạo `src/main/resources/application.properties`. Trong ví dụ, cả `VIEWER` và `OPS` được gọi URL, còn chỉ `OPS` được xem thành phần và chi tiết. Máy chủ chỉ lắng nghe trên loopback.

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health
management.endpoint.health.group.orders.include=ordersBackend
management.endpoint.health.group.orders.show-components=when-authorized
management.endpoint.health.group.orders.show-details=when-authorized
management.endpoint.health.group.orders.roles=OPS
```

Tạo `src/main/java/demo/health/HealthGroupApp.java`. Hai `HealthIndicator` là dữ liệu kiểm thử xác định, cho phép kiểm tra trạng thái mà không cần gọi dịch vụ phụ thuộc. Ba tài khoản trong bộ nhớ và mật khẩu dạng `{noop}` dành cho bài thực hành local.

```java
package demo.health;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class HealthGroupApp {
    public static void main(String[] args) {
        SpringApplication.run(HealthGroupApp.class, args);
    }

    @Bean
    HealthIndicator ordersBackend(@Value("${demo.orders.up:true}") boolean up) {
        return () -> (up ? Health.up() : Health.down())
                .withDetail("check", up ? "ok" : "unavailable")
                .build();
    }

    @Bean
    HealthIndicator invoicesBackend() {
        return () -> Health.down().build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer").password("{noop}lab-only").roles("VIEWER").build(),
                User.withUsername("ops").password("{noop}lab-only").roles("OPS").build(),
                User.withUsername("other").password("{noop}lab-only").roles("OTHER").build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health/orders", "/actuator/health/orders/**")
                        .hasAnyRole("VIEWER", "OPS")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Tạo `src/test/java/demo/health/HealthGroupTest.java`. Tệp chứa hai lớp kiểm thử cấp cao nhất. Lớp thứ hai khởi động một ngữ cảnh riêng với `demo.orders.up=false`, nhờ đó trạng thái `DOWN` không cần thay đổi dữ liệu dùng chung giữa các ca.

```java
package demo.health;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class HealthGroupTest {
    static final String PATH = "/actuator/health/orders";
    static final String PASSWORD = "lab-only";

    @Autowired
    TestRestTemplate client;

    @Test
    void anonymousGets401() {
        var response = client.getForEntity(PATH, String.class);
        assertEquals(401, response.getStatusCode().value());
    }

    @Test
    void authenticatedWithoutRoleGets403() {
        var response = client.withBasicAuth("other", PASSWORD)
                .getForEntity(PATH, String.class);
        assertEquals(403, response.getStatusCode().value());
    }

    @Test
    void viewerGets200WithoutComponentsOrDetails() {
        var response = client.withBasicAuth("viewer", PASSWORD)
                .getForEntity(PATH, JsonNode.class);
        assertEquals(200, response.getStatusCode().value());

        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals("UP", body.path("status").asText());
        assertFalse(body.has("components"));
        assertFalse(body.has("details"));
    }

    @Test
    void opsGetsOnlyTheGroupsComponentAndItsDetails() {
        var response = client.withBasicAuth("ops", PASSWORD)
                .getForEntity(PATH, JsonNode.class);
        assertEquals(200, response.getStatusCode().value());

        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals("UP", body.path("status").asText());
        JsonNode components = body.path("components");
        assertEquals(1, components.size());
        assertEquals("UP", components.at("/ordersBackend/status").asText());
        assertEquals("ok", components.at("/ordersBackend/details/check").asText());
    }
}

@SpringBootTest(webEnvironment = RANDOM_PORT, properties = "demo.orders.up=false")
class HealthGroupDownTest {
    @Autowired
    TestRestTemplate client;

    @Test
    void unhealthyGroupReturns503AndDownBody() {
        var response = client.withBasicAuth("ops", HealthGroupTest.PASSWORD)
                .getForEntity(HealthGroupTest.PATH, JsonNode.class);
        assertEquals(503, response.getStatusCode().value());

        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals("DOWN", body.path("status").asText());
        assertEquals("unavailable", body.at("/components/ordersBackend/details/check").asText());
    }
}
```

Chạy từ thư mục chứa `pom.xml` bằng Maven và JDK 17 trở lên.

```bash
mvn test
```

Khi các phép kiểm tra đạt, dòng tổng kết của Surefire có dạng sau. Thời gian chạy và các dòng nhật ký khởi động phụ thuộc máy.

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Các ca 200 và 503 đọc JSON theo từng trường nên vẫn đúng khi thứ tự trường thay đổi. Ca của `VIEWER` kiểm tra **trường thực sự vắng mặt**. Ca của `OPS` kiểm tra đúng một thành phần và đúng tên của thành phần đó, để phát hiện cả lỗi lộ dữ liệu lẫn lỗi cấu hình thành viên nhóm.

## Khi kết quả lệch kỳ vọng

| Kết quả | Kiểm tra tiếp |
| --- | --- |
| Người dùng đúng vai trò vẫn nhận 401 hoặc 403 | Kiểm tra thông tin xác thực, đường dẫn thực tế, thứ tự của các luật phân quyền và vai trò mà Spring Security gán. Với tiền tố mặc định, `roles("OPS")` cấp quyền `ROLE_OPS`. |
| `VIEWER` thấy thành phần hoặc chi tiết | Kiểm tra riêng `show-components`, `show-details` và `roles` ở cấp nhóm. Kiểm tra thêm URL con như `GET /actuator/health/orders/ordersBackend` nếu hệ thống cũng mở đường dẫn đó. |
| Đã qua lớp bảo mật nhưng nhóm không truy cập được | Kiểm tra tên nhóm, cổng quản trị, đường dẫn gốc và cấu hình mở endpoint. Nếu ứng dụng không khởi động, kiểm tra tên thành phần trong `include` có khớp ID Actuator nhận hay không. |
| JSON báo `DOWN` nhưng HTTP khác 503 | Đối chiếu cấu hình ánh xạ toàn cục và cấu hình riêng của nhóm. Khi cấu hình ánh xạ tùy chỉnh, khai báo lại `DOWN` và `OUT_OF_SERVICE` nếu vẫn muốn giữ mặc định 503, rồi kiểm thử từng mã thuộc hợp đồng của nhóm. |

Nếu triển khai Actuator trên cổng quản trị riêng, hãy kiểm thử qua cổng quản trị thực tế. Bộ kiểm thử trên cùng cổng ứng dụng kiểm chứng đường đi trong cấu hình mẫu. Triển khai có cổng quản trị, proxy hoặc cơ chế xác thực khác cần chạy lại cùng ma trận trên đường truy cập tương ứng.

Tài liệu chính thức. [Health group và ánh xạ HTTP trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) · [Kiểm thử với máy chủ đang chạy](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html) · [Phân quyền HTTP trong Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
