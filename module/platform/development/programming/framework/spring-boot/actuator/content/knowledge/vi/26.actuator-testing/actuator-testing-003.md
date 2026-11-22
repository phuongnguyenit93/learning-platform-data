# Kiểm thử endpoint qua @SpringBootTest và môi trường web thực

Phương thức `health()` của một `HealthIndicator` có thể trả `UP` khi được gọi trực tiếp, trong khi hệ thống giám sát vẫn gặp `404`. Giữa hai chỗ đó còn có cổng quản trị, đường dẫn, danh sách endpoint được mở qua HTTP và các bộ lọc bảo mật. Kiểm thử bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` giúp xác nhận điều mà phía gọi thực sự thấy sau khi Spring Boot khởi động máy chủ nhúng và nhận yêu cầu qua HTTP.

## Chọn môi trường theo lỗi cần phát hiện

| Môi trường của `@SpringBootTest` | Máy chủ HTTP | Dùng khi cần kiểm tra |
| --- | --- | --- |
| `MOCK`, mặc định | Môi trường web mô phỏng. | Luồng xử lý yêu cầu trong context với công cụ như `MockMvc`, nếu đã cấu hình công cụ đó. |
| `RANDOM_PORT` | Máy chủ nhúng thật, cổng do hệ điều hành cấp. | Cổng lắng nghe, đường dẫn, việc mở endpoint qua HTTP, chuỗi bộ lọc và mã trạng thái cùng nội dung phản hồi. |
| `DEFINED_PORT` | Máy chủ nhúng thật, dùng cổng đã cấu hình hoặc mặc định. | Hợp đồng có yêu cầu cụ thể về cổng. Nhiều lần chạy cùng lúc có thể tranh cổng. |
| `NONE` | Context không có môi trường web. | Bean, thuộc tính và hành vi ở cấp ứng dụng. |

Với `RANDOM_PORT`, dùng `@LocalServerPort` để lấy cổng ứng dụng sau khi máy chủ khởi động. Nếu Actuator dùng máy chủ quản trị riêng, dùng `@LocalManagementPort` để lấy cổng thực của máy chủ đó. Giá trị `0` trong cấu hình là yêu cầu cấp cổng động. URL kiểm thử phải dùng cổng đã cấp. Khi Actuator dùng chung máy chủ ứng dụng, lấy cổng bằng `@LocalServerPort` cho cả hai nhóm đường dẫn.

Spring Boot có thể cung cấp một `TestRestTemplate` trong kiểm thử có máy chủ chạy. URL tương đối của client được cấp hướng tới cổng ứng dụng. Ví dụ dưới đây truyền `URI` đầy đủ để đích đến của từng yêu cầu rõ ràng. `TestRestTemplate` cho phép nhận phản hồi `4xx` và `5xx` dưới dạng `ResponseEntity` để kiểm tra trực tiếp mã trạng thái.

## Ví dụ Spring Boot 3.3 với cổng Actuator riêng

Ví dụ tạo một endpoint tùy chỉnh `buildcheck` bằng `@Endpoint` và `@ReadOperation`. Cấu hình kiểm thử dùng cổng ngẫu nhiên cho cả hai máy chủ, đặt tiền tố quản trị thành `/ops` và mở đúng hai ID `health`, `buildcheck` qua HTTP. Cả hai máy chủ lắng nghe ở địa chỉ vòng lặp để kiểm thử cục bộ.

Tạo dự án Gradle riêng với JDK 17 trở lên và Gradle tương thích với JDK đang dùng. Trong `settings.gradle`, đặt `rootProject.name = 'actuator-http-test'`. Lưu ba tệp dưới đây theo đúng đường dẫn.

Tệp `build.gradle`

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
}
```

Tệp `src/main/java/demo/actuator/ActuatorTestApplication.java`

```java
package demo.actuator;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ActuatorTestApplication {

    @Bean
    BuildCheckEndpoint buildCheckEndpoint() {
        return new BuildCheckEndpoint();
    }

    @Endpoint(id = "buildcheck")
    static class BuildCheckEndpoint {

        @ReadOperation
        public Map<String, String> read() {
            return Map.of("state", "ready");
        }
    }
}
```

Tệp `src/test/java/demo/actuator/ActuatorHttpTest.java`

```java
package demo.actuator;

import java.net.URI;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ActuatorTestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "server.address=127.0.0.1",
                "management.server.address=127.0.0.1",
                "management.server.port=0",
                "management.endpoints.web.base-path=/ops",
                "management.endpoints.web.exposure.include=health,buildcheck"
        }
)
class ActuatorHttpTest {

    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate http;

    @Test
    void healthRespondsOnManagementPort() {
        assertJsonField("/ops/health", "status", "UP");
    }

    @Test
    void customEndpointUsesItsHttpMapping() {
        assertJsonField("/ops/buildcheck", "state", "ready");
    }

    @Test
    void infoIsNotExposedOnManagementPort() {
        ResponseEntity<String> response = http.getForEntity(
                url(managementPort, "/ops/info"), String.class);

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void healthIsNotMappedOnApplicationPort() {
        assertNotEquals(applicationPort, managementPort);

        ResponseEntity<String> response = http.getForEntity(
                url(applicationPort, "/ops/health"), String.class);

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    private void assertJsonField(String path, String field, String expected) {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        ResponseEntity<JsonNode> response = http.exchange(
                url(managementPort, path), HttpMethod.GET,
                new HttpEntity<Void>(headers), JsonNode.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(contentType));
        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals(expected, body.path(field).asText());
    }

    private URI url(int port, String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }
}
```

Chạy từ thư mục dự án.

```bash
gradle test --tests demo.actuator.ActuatorHttpTest
```

| Ca kiểm thử | Đích đến | Kết quả mong đợi và điều được kiểm tra |
| --- | --- | --- |
| `healthRespondsOnManagementPort` | Cổng quản trị, `/ops/health` | `200`, JSON có `status=UP`. Kiểm tra endpoint tích hợp sẵn đi qua đường HTTP đã cấu hình. |
| `customEndpointUsesItsHttpMapping` | Cổng quản trị, `/ops/buildcheck` | `200`, JSON có `state=ready`. Kiểm tra thao tác đọc của endpoint tùy chỉnh được ánh xạ tới `GET`. |
| `infoIsNotExposedOnManagementPort` | Cổng quản trị, `/ops/info` | `404` theo danh sách endpoint được mở qua HTTP trong ví dụ. |
| `healthIsNotMappedOnApplicationPort` | Cổng ứng dụng, `/ops/health` | Hai cổng thực khác nhau, và cổng ứng dụng trả `404` cho đường dẫn quản trị. |

Trong một lần chạy JUnit Platform với Java 17, Spring Boot 3.3.0 và Tomcat NIO2 ở cả hai máy chủ, cổng ứng dụng là `52687`, cổng quản trị là `52688`. Kết quả là **4 ca đạt, 0 ca thất bại**. Các số cổng chỉ minh họa lần chạy đó.

Hai ca thành công gửi `Accept: application/json` để kiểm tra cả thương lượng kiểu nội dung. Đọc JSON bằng `JsonNode` và so sánh trường thuộc hợp đồng giúp ca kiểm thử ổn định khi phản hồi thêm trường. Nếu bên tiêu thụ phụ thuộc vào kiểu nội dung riêng của Actuator, hãy gửi đúng kiểu `Accept` mà bên đó sử dụng và xác nhận `Content-Type` tương ứng.

## Chẩn đoán khi bài kiểm thử thất bại

1. **Lỗi kết nối hoặc `404`.** Kiểm tra máy chủ đã khởi động, cổng được cấp và URL thực được gửi. Khi dùng chung cổng, tiền tố Actuator được ghép với context path của ứng dụng nếu có. Với máy chủ quản trị riêng, kiểm tra `management.server.base-path` và `management.endpoints.web.base-path`. Sau đó đối chiếu endpoint đã được bật và được mở qua HTTP. `management.endpoints.web.exposure.exclude` có ưu tiên hơn `include`.
2. **`401`, `403` hoặc chuyển hướng xác thực.** Nếu ứng dụng dùng Spring Security, kiểm tra bằng cùng cơ chế xác thực mà bên giám sát dùng. Viết ca cho quyền hợp lệ và ca cho quyền bị từ chối, rồi xác nhận mã trạng thái theo cấu hình thực. Với thao tác ghi qua `POST`, kiểm tra thêm chính sách CSRF nếu chuỗi bảo mật áp dụng nó. Khi cần kiểm chứng chính sách bảo mật, hãy nạp chính chuỗi bộ lọc đó trong context kiểm thử.
3. **`503` từ health.** Đọc trạng thái tổng hợp trong JSON cùng cấu hình ánh xạ trạng thái sang HTTP. Theo mặc định của Spring Boot 3.3, `DOWN` và `OUT_OF_SERVICE` ánh xạ sang `503`. Với ứng dụng có phụ thuộc ngoài, cung cấp dữ liệu kiểm thử có kiểm soát. Ví dụ, dùng `HealthIndicator` thử nghiệm với trạng thái xác định hoặc khởi động phụ thuộc dành riêng cho kiểm thử. Kiểm tra cả trường hợp hoạt động và trường hợp phụ thuộc lỗi nếu đó là hợp đồng cần bảo vệ.
4. **Kiểm thử xanh nhưng cấu hình triển khai khác.** Các thuộc tính trong ví dụ mô tả một cấu hình xác định. Để kiểm thử cấu hình đang triển khai, chọn đúng profile, giữ các thuộc tính ánh xạ và quyền truy cập cần xác minh, rồi chỉ thay những giá trị phục vụ cô lập như cổng động. `@SpringBootTest` mặc định dùng `UseMainMethod.NEVER` và tạo ứng dụng từ lớp cấu hình. Nếu ứng dụng thiết lập thuộc tính hoặc bộ khởi tạo trong `main`, chọn `useMainMethod` phù hợp để đưa thiết lập đó vào phép thử.

Yêu cầu HTTP thật có luồng xử lý phía máy chủ riêng. Nếu bài kiểm thử gọi endpoint ghi dữ liệu, transaction trên phương thức kiểm thử chỉ bao phía kiểm thử. Hãy chuẩn bị dữ liệu có thể được máy chủ nhìn thấy và dọn dữ liệu đã ghi một cách tường minh. Máy chủ nhúng xác minh hợp đồng HTTP của ứng dụng trong cấu hình đã nạp. Các lớp bên ngoài như ingress, TLS ở proxy hoặc quy tắc mạng cần phép thử từ cùng vị trí mà bên giám sát truy cập.

## Tài liệu đối chiếu

- [Spring Boot 3.3 · Kiểm thử ứng dụng với máy chủ đang chạy](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 · Cổng và đường dẫn Actuator qua HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Boot 3.3 · Mở endpoint, bảo mật và ánh xạ Health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 · API TestRestTemplate](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html)