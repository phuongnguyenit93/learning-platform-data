# Sử dụng @LocalManagementPort khi cổng quản trị được tách riêng

Khi ứng dụng và Actuator dùng hai cổng HTTP khác nhau, bài kiểm thử cần gửi yêu cầu đến đúng máy chủ. Ví dụ, `GET /actuator/health` có thể trả `404` trên cổng ứng dụng trong khi endpoint vẫn hoạt động ở cổng quản trị. Với cổng cấp động, Spring Boot cung cấp hai annotation để lấy số cổng sau khi máy chủ đã khởi động. [Kiểm thử Spring Boot với máy chủ HTTP thật](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)

| Annotation | Thuộc tính lúc chạy | Dùng để gọi |
| --- | --- | --- |
| `@LocalServerPort` | `local.server.port` | Máy chủ HTTP chính của ứng dụng. |
| `@LocalManagementPort` | `local.management.port` | Máy chủ quản trị được khởi động trên cổng riêng. |

Cả hai annotation nằm trong gói `org.springframework.boot.test.web.server`. `@SpringBootTest(webEnvironment = RANDOM_PORT)` yêu cầu Spring Boot mở máy chủ ứng dụng trên cổng cấp động. Đặt thêm `management.server.port=0` để yêu cầu máy chủ quản trị riêng trên một cổng cấp động khác. Số `0` là giá trị cấu hình để hệ điều hành chọn cổng. Sau khi các máy chủ khởi động, hai trường được tiêm số cổng thật để tạo URL. [LocalServerPort](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html) · [LocalManagementPort](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html)

## Kiểm thử hai cổng trong cùng một lần chạy

Ví dụ dùng Java 17 trở lên, Gradle và Spring Boot 3.3.0. Tạo ba tệp sau trong một thư mục thử nghiệm riêng. Cấu hình bài kiểm thử giới hạn cả hai máy chủ ở địa chỉ loopback và công bố endpoint `health`. Ứng dụng mẫu dùng đường dẫn Actuator mặc định và không thêm Spring Security.

**`build.gradle`**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

**`src/main/java/demo/actuator/PortsDemoApplication.java`**

```java
package demo.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortsDemoApplication.class, args);
    }
}
```

**`src/test/java/demo/actuator/SeparateManagementPortTest.java`**

```java
package demo.actuator;

import java.net.URI;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=0",
        "management.endpoints.web.exposure.include=health"
    }
)
class SeparateManagementPortTest {

    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate rest;

    @Test
    void servesHealthOnlyOnTheManagementPort() {
        assertTrue(applicationPort > 0);
        assertTrue(managementPort > 0);
        assertNotEquals(applicationPort, managementPort);

        String healthPath = "/actuator/health";
        URI managementUrl = URI.create("http://127.0.0.1:" + managementPort + healthPath);
        URI applicationUrl = URI.create("http://127.0.0.1:" + applicationPort + healthPath);

        var health = rest.getForEntity(managementUrl, JsonNode.class);
        assertEquals(HttpStatus.OK, health.getStatusCode());
        JsonNode body = health.getBody();
        assertNotNull(body);
        assertEquals("UP", body.path("status").asText());

        var onApplicationPort = rest.getForEntity(applicationUrl, String.class);
        assertEquals(HttpStatus.NOT_FOUND, onApplicationPort.getStatusCode());
    }
}
```

Từ thư mục chứa `build.gradle`, chạy lệnh sau.

```bash
gradle test --tests demo.actuator.SeparateManagementPortTest
```

Bài kiểm thử xác nhận cả hai cổng đã được cấp, hai số cổng khác nhau và cùng đường dẫn có hai kết quả khác nhau.

- Gọi trên **cổng quản trị** trả `200 OK`. Trường `status` trong JSON là `UP` với ứng dụng mẫu đang khỏe.
- Gọi trên **cổng ứng dụng** trả `404 Not Found` vì tuyến Actuator này chỉ được ánh xạ ở máy chủ quản trị. Phép kiểm tra này xác nhận cách tách cổng trong cấu hình mẫu. Với ứng dụng có ánh xạ cùng đường dẫn hoặc quy tắc bảo mật riêng, hãy đối chiếu phản hồi với hợp đồng thực tế của ứng dụng.

Hai lệnh gọi truyền `URI` tuyệt đối cho `TestRestTemplate`. Với máy khách do `@SpringBootTest` cung cấp, một đường dẫn như `"/actuator/health"` sẽ dùng địa chỉ gốc của máy chủ chính. Lấy được `managementPort` chỉ cung cấp số cổng để tạo địa chỉ. Máy khách sẽ gửi tới cổng quản trị khi URL hoặc địa chỉ gốc được cấu hình với cổng đó.

## Chẩn đoán khi bài kiểm thử thất bại

| Dấu hiệu | Cách kiểm tra |
| --- | --- |
| Không phân giải được `local.management.port` | Xác nhận có máy chủ quản trị riêng, với `management.server.port=0` trong cấu hình kiểm thử. Khi Actuator dùng chung cổng, dùng `@LocalServerPort`. Giá trị `management.server.port=-1` tắt truy cập endpoint qua HTTP. |
| Bài kiểm thử dùng `MOCK` hoặc chỉ dùng MockMvc | MockMvc kiểm tra xử lý yêu cầu qua Spring MVC trong tiến trình. Chọn `RANDOM_PORT` và gửi HTTP thật để kiểm chứng hai máy chủ đang lắng nghe ở hai cổng. |
| Cổng quản trị trả `404` | Kiểm tra endpoint đã được công bố qua HTTP và URL dùng đúng đường dẫn. Nếu đã đổi `management.endpoints.web.base-path` sang `/ops`, đường dẫn health là `/ops/health`. Kiểm tra thêm `management.server.base-path` nếu ứng dụng có đặt thuộc tính đó. |
| Nhận `401`, `403` hoặc lỗi kết nối TLS | Kiểm tra xác thực, quyền truy cập và giao thức của cổng quản trị. Cổng quản trị riêng có thể dùng cấu hình SSL riêng. Annotation cung cấp số cổng, còn máy khách vẫn cần đúng giao thức và thông tin truy cập. |

Khi đọc kết quả, đối chiếu cả số cổng, đường dẫn và mã phản hồi. Một phép kiểm tra `200` đơn lẻ có thể xác nhận endpoint đang hoạt động. Gọi cùng đường dẫn qua cả hai cổng mới kiểm chứng được cách tuyến quản trị được tách trong ví dụ này. [Cấu hình cổng, đường dẫn và SSL của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
