# Kiểm tra ma trận bật, công bố và bảo mật endpoint

Một endpoint Actuator có thể được bật trong cấu hình nhưng chưa có đường dẫn HTTP. Đường dẫn đã được công bố cũng có thể chỉ cho phép một số người gọi. Khi kiểm thử, hãy thay đổi từng điều kiện để biết lớp nào quyết định kết quả.

## Ba lớp cần kiểm tra

| Lớp | Câu hỏi cần trả lời | Ví dụ với endpoint `info` |
| --- | --- | --- |
| Bật endpoint hoặc cho phép thao tác | Actuator có cho phép thao tác cần gọi không? | Spring Boot 3.3 dùng `management.endpoint.info.enabled`. Từ 3.4, có thể dùng `management.endpoint.info.access=none` để tắt hoặc `read-only` để cho phép thao tác đọc. |
| Công bố qua HTTP (exposure) | Endpoint có được đưa ra qua HTTP không? | Thêm `info` vào `management.endpoints.web.exposure.include`. Nếu `exclude` cũng có `info`, cấu hình loại trừ được ưu tiên. |
| Bảo mật HTTP | Người gọi đã xác thực và có quyền thực hiện thao tác không? | Chuỗi bảo mật Spring Security có thể yêu cầu người gọi mang vai trò `OPS` khi truy cập `/actuator/info`. |

Các lớp này giải quyết những việc khác nhau. Chẳng hạn, `access=read-only` cho phép Actuator cung cấp thao tác đọc của endpoint. Vai trò `OPS` quyết định ai được thực hiện thao tác đó qua HTTP trong bài thử. Trần `management.endpoints.access.max-permitted` ở các phiên bản có cấu hình `access` có thể giới hạn thêm thao tác của mọi endpoint. Phạm vi công bố qua JMX dùng cấu hình riêng. [Endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) · [Endpoint trong Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)

## Lập ma trận cho cùng một đường dẫn

Dùng `GET /actuator/info` làm đối tượng kiểm thử và giữ `GET /actuator/health` làm đối chứng. Cấu hình mẫu dùng HTTP Basic. Quy tắc bảo mật khớp trực tiếp với đường dẫn `/actuator/info` và yêu cầu vai trò `OPS`, kể cả khi Actuator chưa ánh xạ đường dẫn này.

| Trạng thái `info` | Có trong `include` | Có trong `exclude` | Người gọi | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Tắt | Có | Không | `ops` | `404`. Người gọi qua được bảo mật, nhưng MVC không có ánh xạ endpoint. |
| Tắt | Có | Không | Chưa xác thực | `401`. Bộ lọc yêu cầu xác thực trước khi MVC tìm ánh xạ. |
| Chỉ đọc | Không | Không | `ops` | `404`. Endpoint không được công bố qua HTTP. |
| Chỉ đọc | Có | Có | `ops` | `404`. `exclude` thắng `include`. |
| Chỉ đọc | Có | Không | Chưa xác thực | `401`. Cần xác thực. |
| Chỉ đọc | Có | Không | `reader` | `403`. Đã xác thực nhưng thiếu vai trò `OPS`. |
| Chỉ đọc | Có | Không | `ops` | `200` và JSON có trường `lab` với giá trị `matrix`. |

Cặp ca đầu minh họa vì sao `401` không đủ để kết luận endpoint đã được công bố. Muốn kiểm tra bật và công bố, gửi yêu cầu với danh tính đã biết là được phép. Muốn kiểm tra quyền truy cập, giữ endpoint bật và đã công bố, rồi thay đổi người gọi. Mã phản hồi cụ thể phụ thuộc chuỗi bảo mật, cách khớp yêu cầu và cấu hình xử lý lỗi của ứng dụng. [Bảo mật endpoint Actuator](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.security)

## Chạy ma trận bằng MockMvc

Ví dụ dùng Java 17 trở lên, Gradle, Spring Boot 3.5.9 và Spring Security. MockMvc gọi bộ lọc bảo mật và bộ điều phối MVC trong tiến trình. Mỗi dòng ma trận tạo một ngữ cảnh riêng để cấu hình Actuator được áp dụng từ lúc khởi tạo. Cấu hình người dùng trong bộ nhớ và mật khẩu `{noop}` chỉ thuộc bộ dữ liệu kiểm thử.

**`build.gradle`**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.9')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
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

**`src/test/java/demo/actuator/ActuatorAccessMatrixTest.java`**

```java
package demo.actuator;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.Filter;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockServletContext;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.config.Customizer.withDefaults;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class ActuatorAccessMatrixTest {

    @ParameterizedTest(name = "{0}")
    @CsvSource(textBlock = """
        disabled for ops,         none,      true,  false, ops,       404
        disabled for anonymous,   none,      true,  false, anonymous, 401
        not published,            read-only, false, false, ops,       404
        exclude overrides include,read-only, true,  true,  ops,       404
        published for anonymous,  read-only, true,  false, anonymous, 401
        published for reader,     read-only, true,  false, reader,    403
        published for ops,        read-only, true,  false, ops,       200
        """)
    void checksInfoEndpoint(String scenario, String access, boolean includeInfo,
                            boolean excludeInfo, String caller, int expectedStatus)
        throws Exception {

        try (var context = new AnnotationConfigWebApplicationContext()) {
            context.setServletContext(new MockServletContext());
            context.getEnvironment().setConversionService(new ApplicationConversionService());
            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("matrix", Map.of(
                    "management.endpoint.info.access", access,
                    "management.endpoints.web.exposure.include", includeInfo ? "health,info" : "health",
                    "management.endpoints.web.exposure.exclude", excludeInfo ? "info" : ""
                ))
            );
            context.register(Fixture.class);
            context.refresh();

            var mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(context.getBean("springSecurityFilterChain", Filter.class))
                .build();
            assertEquals(200, mvc.perform(get("/actuator/health"))
                .andReturn().getResponse().getStatus());

            var request = get("/actuator/info");
            if (!caller.equals("anonymous")) {
                String credentials = caller + ":test-password";
                String encoded = Base64.getEncoder()
                    .encodeToString(credentials.getBytes(StandardCharsets.UTF_8));
                request.header(HttpHeaders.AUTHORIZATION, "Basic " + encoded);
            }

            var response = mvc.perform(request).andReturn().getResponse();

            assertEquals(expectedStatus, response.getStatus(), scenario);
            if (expectedStatus == 200) {
                var body = context.getBean(ObjectMapper.class).readTree(response.getContentAsString());
                assertEquals("matrix", body.path("lab").asText());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    @EnableWebSecurity
    static class Fixture {

        @Bean
        InfoContributor sampleInfo() {
            return builder -> builder.withDetail("lab", "matrix");
        }

        @Bean
        UserDetailsService users() {
            return new InMemoryUserDetailsManager(
                User.withUsername("ops").password("{noop}test-password").roles("OPS").build(),
                User.withUsername("reader").password("{noop}test-password").roles("READER").build()
            );
        }

        @Bean
        SecurityFilterChain security(HttpSecurity http) throws Exception {
            return http.authorizeHttpRequests(rules -> rules
                    .requestMatchers("/actuator/health").permitAll()
                    .requestMatchers("/actuator/info").hasRole("OPS")
                    .anyRequest().denyAll())
                .httpBasic(withDefaults())
                .build();
        }
    }
}
```

`ApplicationConversionService` giúp ngữ cảnh được tạo thủ công hiểu các giá trị cấu hình như `read-only`. `addFilters` đưa chuỗi lọc của Spring Security vào MockMvc. Ca yêu cầu `200` còn kiểm tra dữ liệu do `InfoContributor` cung cấp, giúp xác nhận phản hồi thực sự đến từ endpoint cần kiểm tra. Tất cả các ca đều đòi hỏi `/actuator/health` trả `200` để phát hiện trường hợp ngữ cảnh web hoặc cấu hình Actuator chung có vấn đề.

Từ thư mục chứa `build.gradle`, chạy lệnh sau.

```bash
gradle test --tests demo.actuator.ActuatorAccessMatrixTest
```

Kỳ vọng cả bảy ca đều đạt. Với dự án Spring Boot 3.3, giữ các cột công bố và quyền truy cập, đồng thời dùng `management.endpoint.info.enabled` với `false` cho các hàng tắt và `true` cho các hàng bật. Endpoint `info` chỉ có thao tác đọc, nên các ca `GET` giữ nguyên ý nghĩa. Với endpoint có thao tác ghi, kiểm tra riêng phương thức HTTP, quyền ghi và CSRF nếu chính sách đang áp dụng. Một phản hồi `403` khi ghi có thể do CSRF hoặc do quy tắc cấp quyền. [Bật endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)
