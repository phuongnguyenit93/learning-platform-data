# Xác minh dữ liệu nhạy cảm được che theo từng vai trò

Actuator có thể giúp đội vận hành kiểm tra ứng dụng đã nhận cấu hình nào. Cùng một phản hồi có thể chứa tên vùng triển khai, giá trị token và thông tin về nguồn cấu hình. Khi kiểm thử, hãy xác minh hai quyết định độc lập. **Ai được gọi endpoint?** Và **người gọi được thấy giá trị gốc nào trong phản hồi?**

## Các lớp kiểm soát

| Lớp | Cấu hình liên quan | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Mở endpoint qua HTTP | `management.endpoints.web.exposure.include` | Endpoint có được đăng ký trên đường dẫn và cổng quản trị mong đợi không? |
| Quyền gọi endpoint | Luật của `SecurityFilterChain` | Với HTTP Basic trong ví dụ, chưa xác thực nhận 401, đã xác thực nhưng thiếu vai trò nhận 403. |
| Quyền xem giá trị | `management.endpoint.<id>.show-values` và `management.endpoint.<id>.roles` | Hai người có thể cùng nhận HTTP 200 nhưng thấy giá trị khác nhau. |
| Quy tắc che từng giá trị | Bean `SanitizingFunction` | Dữ liệu nhạy cảm vẫn được che với người có quyền xem giá trị gốc. |

`env` báo thông tin từ `Environment`. `configprops` báo thông tin của các bean `@ConfigurationProperties`, gồm giá trị sau khi liên kết cấu hình (`properties`) và dữ liệu đầu vào (`inputs`) khi có. Nếu cùng một giá trị xuất hiện ở nhiều vị trí, phép kiểm thử phải bao phủ từng vị trí có thể lộ.

Trong Spring Boot 3.3 và 3.5, hai endpoint này mặc định che giá trị bằng `******`. `show-values=never` giữ chế độ che cho mọi người gọi. `show-values=when-authorized` cho phép hiện giá trị với người có vai trò được cấu hình nếu quy tắc che tùy chỉnh cho phép. Hãy khai báo `roles` rõ ràng khi bật chế độ này vì theo mặc định, mọi người dùng HTTP đã xác thực đều đủ điều kiện xem giá trị. `show-values=always` bỏ điều kiện kiểm tra vai trò ở lớp hiển thị giá trị, trong khi luật truy cập HTTP và quy tắc che tùy chỉnh vẫn áp dụng. JMX là kênh riêng với quy tắc phân quyền hiển thị khác HTTP. Nếu có mở JMX, hãy kiểm thử kênh đó riêng.

## Ma trận kiểm thử

Mẫu dùng hai giá trị giả. `lab.region` là thông tin được phép hiện cho `OPS`. `lab.api-token` là chuỗi đánh dấu dùng để phát hiện rò rỉ. Hàm che giữ nguyên giá trị cho khóa `lab.region` và che các khóa còn lại. Vì vậy, một vai trò có quyền xem giá trị gốc vẫn chỉ thấy những trường có tên nằm trong danh sách cho phép của ví dụ.

| Người gọi | Mã HTTP | Giá trị vùng | Giá trị token |
| --- | --- | --- | --- |
| Chưa xác thực | 401 | Yêu cầu bị chặn | Yêu cầu bị chặn |
| Đã xác thực, vai trò `OTHER` | 403 | Yêu cầu bị chặn | Yêu cầu bị chặn |
| Vai trò `VIEWER` | 200 | `******` | `******` |
| Vai trò `OPS` | 200 | `ap-southeast-1` | `******` |

## Ví dụ tích hợp với MockMvc

Ví dụ dùng Java 17, Spring Boot 3.5.9 và Spring Security. `@SpringBootTest` nạp cấu hình Actuator. `@AutoConfigureMockMvc` gửi yêu cầu mô phỏng qua Spring MVC và chuỗi lọc bảo mật. Mỗi ca có xác thực gửi header HTTP Basic bằng tài khoản giả để chuỗi lọc thực hiện xác thực và phân quyền.

Tạo `pom.xml` trong thư mục dự án.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.9</version>
        <relativePath/>
    </parent>
    <groupId>demo.actuatorsafe</groupId>
    <artifactId>actuator-sanitization-demo</artifactId>
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

Tạo `src/main/resources/application.properties`.

```properties
management.endpoints.web.exposure.include=env,configprops
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=OPS
management.endpoint.configprops.show-values=when-authorized
management.endpoint.configprops.roles=OPS
lab.region=ap-southeast-1
lab.api-token=DEMO-ONLY-SECRET-7f21
```

Tạo `src/main/java/demo/actuatorsafe/SanitizationApp.java`. Mật khẩu dạng `{noop}` và token đánh dấu chỉ phục vụ bài thực hành. Chính sách `denyAll()` ở cuối chuỗi lọc dành cho ứng dụng mẫu chuyên kiểm thử hai endpoint này.

```java
package demo.actuatorsafe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableConfigurationProperties(LabProperties.class)
public class SanitizationApp {
    public static void main(String[] args) {
        SpringApplication.run(SanitizationApp.class, args);
    }

    @Bean
    SanitizingFunction exposeOnlyLabRegion() {
        return data -> "lab.region".equals(data.getKey()) ? data : data.withSanitizedValue();
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
        return http.authorizeHttpRequests(auth -> auth
                        .requestMatchers(EndpointRequest.to("env", "configprops"))
                        .hasAnyRole("VIEWER", "OPS")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@ConfigurationProperties("lab")
record LabProperties(String region, String apiToken) {
}
```

Tạo `src/test/java/demo/actuatorsafe/SanitizationTest.java`. Ca 200 kiểm đồng thời giá trị ở đúng trường JSON và sự vắng mặt của token giả trong toàn bộ nội dung trả về từ từng URL đang kiểm thử. Phép kiểm tra đúng trường giúp phát hiện lỗi gọi nhầm URL, sai cấu trúc JSON hoặc trường bị mất. Phép kiểm tra toàn nội dung giúp phát hiện token xuất hiện ở vị trí khác ngoài trường chính.

```java
package demo.actuatorsafe;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(print = MockMvcPrint.NONE)
class SanitizationTest {
    private static final String ENV_REGION = "/actuator/env/lab.region";
    private static final String ENV_TOKEN = "/actuator/env/lab.api-token";
    private static final String CONFIG = "/actuator/configprops/lab";
    private static final String MASK = "******";
    private static final String REGION = "ap-southeast-1";
    private static final String FAKE_TOKEN = "DEMO-ONLY-SECRET-7f21";

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void anonymousGets401() throws Exception {
        mvc.perform(get(ENV_TOKEN)).andExpect(status().isUnauthorized());
        mvc.perform(get(CONFIG)).andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutEndpointRoleGets403() throws Exception {
        mvc.perform(get(ENV_TOKEN).header(HttpHeaders.AUTHORIZATION, basic("other")))
                .andExpect(status().isForbidden());
        mvc.perform(get(CONFIG).header(HttpHeaders.AUTHORIZATION, basic("other")))
                .andExpect(status().isForbidden());
    }

    @Test
    void viewerSeesOnlyMaskedValues() throws Exception {
        assertVisibleValues("viewer", MASK);
    }

    @Test
    void opsSeesRegionButTokenRemainsMasked() throws Exception {
        assertVisibleValues("ops", REGION);
    }

    private void assertVisibleValues(String user, String expectedRegion) throws Exception {
        JsonNode envRegion = readWithoutToken(user, ENV_REGION);
        assertEquals(expectedRegion, envRegion.at("/property/value").asText());

        JsonNode envToken = readWithoutToken(user, ENV_TOKEN);
        assertEquals(MASK, envToken.at("/property/value").asText());

        JsonNode config = labBean(readWithoutToken(user, CONFIG));
        assertEquals(expectedRegion, config.at("/properties/region").asText());
        assertEquals(MASK, config.at("/properties/apiToken").asText());
        assertEquals(expectedRegion, config.at("/inputs/region/value").asText());
        assertEquals(MASK, config.at("/inputs/apiToken/value").asText());
    }

    private JsonNode readWithoutToken(String user, String path) throws Exception {
        String body = mvc.perform(get(path).header(HttpHeaders.AUTHORIZATION, basic(user)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertFalse(body.contains(FAKE_TOKEN), "The response exposed the fixture token");
        return mapper.readTree(body);
    }

    private static JsonNode labBean(JsonNode body) {
        for (JsonNode context : body.path("contexts")) {
            for (JsonNode bean : context.path("beans")) {
                if ("lab".equals(bean.path("prefix").asText())) {
                    return bean;
                }
            }
        }
        throw new AssertionError("Expected a configuration properties bean with prefix lab");
    }

    private static String basic(String username) {
        return "Basic " + HttpHeaders.encodeBasicAuth(username, "lab-only", StandardCharsets.UTF_8);
    }
}
```

Chạy từ thư mục chứa `pom.xml` bằng Maven và JDK 17 trở lên.

```bash
mvn test
```

Khi cả bốn ca đạt, phần tổng kết của Surefire có các số đếm sau.

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

## Mở rộng phép kiểm theo hợp đồng triển khai

- Với endpoint có cả đường dẫn gốc và đường dẫn lọc, hãy kiểm tra cả hai nếu người dùng có thể gọi cả hai. Ví dụ trên gọi `env` theo tên thuộc tính và `configprops` theo tiền tố để tập trung vào dữ liệu mẫu. Khi có nhiều nguồn cấu hình, thêm ca để kiểm giá trị ở từng nguồn, tên khóa thay thế và các trường lồng nhau thuộc phạm vi chính sách của ứng dụng.
- Mỗi ca cho phép nhìn thấy giá trị nên có cả một giá trị được phép hiện và một giá trị bắt buộc che. Nếu mọi giá trị đều bị che do cấu hình sai, phép kiểm tra vùng triển khai của `OPS` sẽ thất bại thay vì cho kết quả đạt giả.
- Chạy kiểm thử với bí mật giả dễ nhận diện và tránh in phản hồi ra báo cáo CI. Việc che giá trị vẫn có thể để lộ tên khóa, cấu trúc hoặc nguồn cấu hình. Nếu hợp đồng yêu cầu giấu cả thông tin đó, hãy kiểm tra trường hoặc endpoint tương ứng thực sự không xuất hiện.

Tài liệu chính thức. [Quy tắc che giá trị của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization) · [REST API của env](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/env.html) · [REST API của configprops](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/configprops.html)
