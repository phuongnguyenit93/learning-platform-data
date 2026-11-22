# Chọn MockMvc, WebTestClient hoặc HTTP client theo hạ tầng cần kiểm chứng

Một ca kiểm thử trả 200 cho `GET /actuator/health` có thể xác nhận Spring xử lý đúng yêu cầu mô phỏng, hoặc xác nhận một máy chủ thật đang trả lời qua HTTP. Phạm vi kiểm chứng do **cách ca kiểm thử đưa yêu cầu tới ứng dụng** quyết định. Hãy chọn cách kết nối theo lỗi cần phát hiện.

## Chọn theo ranh giới cần kiểm chứng

| Hạ tầng cần kiểm chứng | Cách kết nối | Ca kiểm thử đi qua |
| --- | --- | --- |
| Định tuyến, cấu hình Actuator, mã trạng thái, JSON và các bộ lọc được nạp trong ứng dụng Spring MVC | `@SpringBootTest` với môi trường web mô phỏng, `@AutoConfigureMockMvc` và `MockMvc` | Spring MVC trong tiến trình kiểm thử, qua yêu cầu và phản hồi Servlet mô phỏng. |
| Xử lý yêu cầu của ứng dụng Spring WebFlux, với cấu hình reactive đã nạp | `WebTestClient.bindToApplicationContext(context)` | Chuỗi xử lý WebFlux với yêu cầu và phản hồi mô phỏng. |
| Dùng cùng cú pháp xác nhận của `WebTestClient` để kiểm tra Spring MVC | `MockMvcWebTestClient.bindTo(mvc)` | Cùng hạ tầng mô phỏng của `MockMvc`. |
| Cổng ứng dụng, cổng quản trị riêng, hoặc hành vi của máy chủ web nhúng qua kết nối thật | `@SpringBootTest(webEnvironment = RANDOM_PORT)` và một HTTP client, như `HttpClient` của JDK, `TestRestTemplate` hoặc `WebTestClient.bindToServer()` | Máy khách kết nối tới máy chủ đang lắng nghe trên cổng được cấp. |
| DNS, TLS, định tuyến qua proxy hoặc quyền truy cập từ mạng triển khai | Một HTTP client gọi URL của môi trường đã triển khai từ vị trí mạng phù hợp | Những thành phần thực tế trên đường yêu cầu đi qua, kể cả proxy hoặc ingress nếu URL đi qua chúng. |

Với Actuator, hãy nạp cấu hình có endpoint thật. `@SpringBootTest` tạo ngữ cảnh Boot đầy đủ. Một ca `@WebMvcTest` chỉ nạp phần MVC được chọn, còn `standaloneSetup` và `bindToController` chỉ cấu hình các thành phần được chỉ định. Nếu mục tiêu là xác nhận cấu hình tự động của Actuator, cần dùng ngữ cảnh có cấu hình đó.

Khi kiểm tra phân quyền bằng `MockMvc`, giữ các bộ lọc bảo mật được nạp và xác nhận ca đi qua chuỗi lọc mong muốn. Nếu ca kiểm thử gắn sẵn danh tính giả lập, kết quả kiểm chứng luật phân quyền cho danh tính đó. Để kiểm chứng xác thực thực tế, hãy gửi thông tin xác thực qua cơ chế mà máy khách sẽ dùng.

## Ví dụ trên Spring Boot 3.3 và Java 17

Hai ca cơ bản dùng cùng đường dẫn `GET /ops/health`. Ca thứ nhất xác nhận hợp đồng HTTP và JSON trong Spring MVC. Ca thứ hai khởi động máy chủ ứng dụng và máy chủ quản trị trên hai cổng ngẫu nhiên, rồi kiểm tra kết quả khi gọi từng cổng.

Tạo `pom.xml` trong thư mục dự án.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>demo.actuatortest</groupId>
    <artifactId>actuator-client-demo</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Tạo `src/main/java/demo/actuatortest/ActuatorTestApp.java`.

```java
package demo.actuatortest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorTestApp {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorTestApp.class, args);
    }
}
```

Tạo `src/test/java/demo/actuatortest/ActuatorMvcTest.java`. Tệp chứa hai lớp kiểm thử cấp cao nhất. Maven nhận cả hai lớp vì tên lớp đều kết thúc bằng `Test`.

```java
package demo.actuatortest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "management.endpoints.web.base-path=/ops")
@AutoConfigureMockMvc
class ActuatorMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void healthContractInMvc() throws Exception {
        mvc.perform(get("/ops/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}

@SpringBootTest(webEnvironment = RANDOM_PORT, properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=0",
        "management.endpoints.web.base-path=/ops"
})
class ActuatorPortTest {
    @LocalServerPort
    int appPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    ObjectMapper json;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    void healthIsServedOnTheManagementPort() throws Exception {
        assertNotEquals(appPort, managementPort);

        var management = getHealth(managementPort);
        assertEquals(200, management.statusCode());
        assertEquals("UP", json.readTree(management.body()).path("status").asText());

        var application = getHealth(appPort);
        assertEquals(404, application.statusCode());
    }

    private HttpResponse<String> getHealth(int port) throws Exception {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/ops/health"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
```

Chạy từ thư mục chứa `pom.xml`.

```bash
mvn test
```

Khi chạy hai ca cơ bản, phần tổng kết của Surefire có các số đếm sau.

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Ca `ActuatorMvcTest` cho thấy `management.endpoints.web.base-path=/ops` được áp dụng và endpoint trả `status=UP`. Ca `ActuatorPortTest` kiểm thêm hai cổng khác nhau, HTTP 200 và JSON tại cổng quản trị, cùng HTTP 404 tại cổng ứng dụng. Mã 404 là kỳ vọng của ứng dụng mẫu với đường dẫn này. Ứng dụng có luật bảo mật hoặc định tuyến khác có thể trả mã khác ở cổng ứng dụng.

## Dùng WebTestClient trên cùng bài thực hành

Để chạy một ca tùy chọn qua cầu nối MockMvc, thêm phụ thuộc sau trong phần `dependencies` của `pom.xml`. Phạm vi `test` cung cấp các lớp máy khách WebFlux cho bài kiểm thử. Ứng dụng mẫu vẫn chạy Spring MVC.

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
    <scope>test</scope>
</dependency>
```

Tạo `src/test/java/demo/actuatortest/ActuatorWebTestClientTest.java` rồi chạy lại `mvn test` để chạy thêm ca sau.

```java
package demo.actuatortest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;

@SpringBootTest(properties = "management.endpoints.web.base-path=/ops")
@AutoConfigureMockMvc
class ActuatorWebTestClientTest {
    @Test
    void healthContractUsingWebTestClient(@Autowired MockMvc mvc) {
        var client = MockMvcWebTestClient.bindTo(mvc).build();

        client.get().uri("/ops/health").exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.status").isEqualTo("UP");
    }
}
```

Cầu nối tái sử dụng chính đối tượng `MockMvc` do Boot cấu hình. Để kiểm tra một ứng dụng reactive trong tiến trình, dùng `WebTestClient.bindToApplicationContext(context).build()` với ngữ cảnh WebFlux. Để kiểm tra kết nối thật, dùng `WebTestClient.bindToServer().baseUrl(...)` và chọn URL trỏ tới cổng quản trị hoặc địa chỉ triển khai cần xác minh. Cú pháp `expectStatus()` và `expectBody()` có thể dùng ở cả hai chế độ.

## Đọc lỗi theo phạm vi ca kiểm thử

- **Ca mô phỏng qua nhưng ca gọi cổng quản trị thất bại.** Kiểm tra cổng, địa chỉ lắng nghe, đường dẫn gốc của máy chủ quản trị, cấu hình mở endpoint và giao thức HTTP hoặc HTTPS. Với cổng ngẫu nhiên, lấy giá trị từ `@LocalManagementPort` thay vì gắn cứng một cổng.
- **Ca HTTP local qua nhưng môi trường triển khai trả lỗi.** Kiểm tra trên URL triển khai và từ đúng vị trí mạng. Ca local kiểm chứng đường tới máy chủ nhúng trong tiến trình kiểm thử. DNS, chứng chỉ, proxy, luật mạng hoặc chính sách xác thực ở môi trường triển khai cần phép kiểm trên tuyến tương ứng.
- **Cần điều tra nội dung và hạ tầng cùng lúc.** Giữ nhiều ca mô phỏng cho các biến thể JSON, trạng thái và quyền truy cập. Dùng một số ca HTTP thật để kiểm những gì cần cổng, kết nối hoặc máy chủ thực tế.

Tài liệu chính thức. [Kiểm thử ứng dụng Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) · [Cấu hình đường dẫn và cổng quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html) · [Các cách kết nối WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
