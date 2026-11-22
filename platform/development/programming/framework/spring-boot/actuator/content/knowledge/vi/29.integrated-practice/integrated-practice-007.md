# Tạo endpoint quản trị có thao tác ghi và bộ kiểm thử bảo mật

## 1. Mục tiêu và ranh giới bài thực hành

Endpoint quản trị có thao tác ghi không chỉ cung cấp thông tin. Nó thay đổi trạng thái của ứng dụng, vì vậy cần kiểm chứng ai được gọi, phương thức nào được phép, dữ liệu nào được chấp nhận và trạng thái có giữ nguyên khi request bị từ chối hay không.

Trong bài này, ta tạo endpoint Actuator để bật/tắt một **cờ bảo trì trong bộ nhớ**:

```text
GET  /actuator/maintenance
     Đọc enabled và revision
     Yêu cầu quyền maintenance:read

POST /actuator/maintenance
     Ghi enabled từ JSON
     Yêu cầu quyền maintenance:write và CSRF token hợp lệ
```

Kèm theo:

- Một API mô phỏng công việc để thấy ảnh hưởng của cờ.
- Một đường lấy CSRF token cho client quản trị.
- Bộ kiểm thử đi qua Spring Security và ánh xạ HTTP thật trong application context.

Ví dụ dùng Spring Boot 3.3.x, Spring Security 6, Servlet stack và Java 17+. Các thao tác chỉ thay đổi đối tượng trong JVM, không shutdown tiến trình, không sửa file hay hệ thống bên ngoài. Khi JVM khởi động lại, trạng thái trở về mặc định.

Đây là mô hình thực hành. Nếu chuyển thành cơ chế bảo trì thật, cần thiết kế thêm lưu trữ/chia sẻ trạng thái, quyền vận hành và nhật ký thao tác phù hợp với hệ thống nhiều instance.

## 2. Phân biệt đăng ký, exposure, xác thực và quyền ghi

Có bốn câu hỏi độc lập:

| Câu hỏi | Cơ chế trong bài |
| --- | --- |
| Endpoint có tồn tại không? | Bean được gắn @Endpoint, có các operation |
| Endpoint có đường HTTP không? | HTTP exposure include maintenance |
| Request đại diện cho ai? | HTTP Basic |
| Danh tính đó có được thao tác không? | Authority theo phương thức, kèm kiểm tra CSRF cho POST |

`@WriteOperation` không tự cấp quyền quản trị. Bật exposure cũng không tự bật bảo mật.

Trong Actuator theo mô hình của Spring Boot 3.3.x:

| Annotation | Phương thức HTTP thông thường |
| --- | --- |
| @ReadOperation | GET |
| @WriteOperation | POST |
| @DeleteOperation | DELETE |

Tên phương thức Java không tự trở thành một đoạn URL. Phương thức `update` có `@WriteOperation` của endpoint id `maintenance` được gọi bằng POST vào `/actuator/maintenance`, không phải tự động vào `/actuator/maintenance/update`.

Bài không khai báo thao tác DELETE. Không tạo chức năng thay đổi trạng thái bằng GET chỉ để client dễ gọi.

## 3. Chuẩn bị dependency và cấu hình

Dùng một dự án Spring Boot 3.3.x đã có Gradle wrapper, Boot plugin và cơ chế quản lý phiên bản dependency của Boot.

Phần cấu hình cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'maintenance-endpoint-lab.jar'
}
```

Đây là phần cấu hình cho dự án đã có plugin, không phải build file độc lập. Nếu build conventions đã bật `-parameters`, giữ cơ chế sẵn có; mục tiêu là các tên tham số operation được lưu trong bytecode.

Actuator cần tên tham số để ánh xạ JSON vào operation. Không mặc định compiler nào cũng giữ tên khi thiếu cấu hình tương ứng.

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    maintenance:
      enabled: true
  endpoints:
    web:
      exposure:
        include: maintenance
```

Bài dùng chung listener cục bộ cho ứng dụng và Actuator, không đổi base path mặc định. Các endpoint Actuator khác không cần được expose cho mục tiêu này.

Kiểm tra không có nguồn cấu hình khác đặt exposure exclude hoặc đổi cổng/đường dẫn. Khi dùng cổng quản trị riêng trong hệ thống khác, phải điều chỉnh đường lấy CSRF token, cookie và kiểm thử theo đúng kiến trúc đó.

## 4. Tách trạng thái nghiệp vụ khỏi lớp Actuator

### 4.1. Lớp khởi động

Tệp `src/main/java/demo/maintenance/MaintenanceApplication.java`:

```java
package demo.maintenance;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MaintenanceApplication {
    public static void main(String[] args) {
        SpringApplication.run(MaintenanceApplication.class, args);
    }
}
```

### 4.2. Trạng thái và số phiên bản thay đổi

Tệp `src/main/java/demo/maintenance/MaintenanceState.java`:

```java
package demo.maintenance;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceState {

    public record Snapshot(boolean enabled, long revision) {
    }

    private final AtomicReference<Snapshot> state =
            new AtomicReference<>(new Snapshot(false, 0));

    public Snapshot snapshot() {
        return state.get();
    }

    public Snapshot setEnabled(boolean enabled) {
        return state.updateAndGet(current ->
                current.enabled() == enabled
                        ? current
                        : new Snapshot(enabled, current.revision() + 1));
    }
}
```

Một Snapshot bất biến chứa cả enabled và revision. Đọc một đối tượng như vậy giúp hai giá trị thuộc cùng một ảnh chụp trạng thái.

`AtomicReference.updateAndGet` cập nhật nguyên tử trong phạm vi JVM. Hàm cập nhật có thể được gọi lại khi tranh chấp, nên nó chỉ tính trạng thái mới, không gửi thông báo hoặc thực hiện tác động phụ bên ngoài.

Revision chỉ tăng khi giá trị enabled thật sự thay đổi:

```text
Ban đầu:       enabled=false, revision=0
Ghi true:      enabled=true,  revision=1
Ghi true nữa:  enabled=true,  revision=1
Ghi false:     enabled=false, revision=2
```

Gửi lại cùng giá trị có tính lũy đẳng ở mức trạng thái: nó không tạo thêm thay đổi. Điều này không biến phương thức POST nói chung thành một phương thức HTTP được mọi hạ tầng tự xem là idempotent.

Revision trong bài là thông tin quan sát, chưa phải điều kiện chống ghi đè bằng expectedRevision. Nếu hai người ghi hai giá trị khác nhau, các cập nhật được tuần tự hóa nguyên tử và lần ghi sau quyết định trạng thái cuối. Một hệ thống cần chống ghi đè quyết định vận hành phải thiết kế thêm kiểm soát phiên bản phù hợp.

### 4.3. Endpoint Actuator

Tệp `src/main/java/demo/maintenance/MaintenanceEndpoint.java`:

```java
package demo.maintenance;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "maintenance")
public class MaintenanceEndpoint {
    private final MaintenanceState state;

    public MaintenanceEndpoint(MaintenanceState state) {
        this.state = state;
    }

    @ReadOperation
    public MaintenanceState.Snapshot read() {
        return state.snapshot();
    }

    @WriteOperation
    public MaintenanceState.Snapshot update(boolean enabled) {
        return state.setEnabled(enabled);
    }
}
```

JSON body hợp lệ:

```json
{"enabled":true}
```

Actuator ánh xạ trường enabled vào tham số đơn giản của operation rồi thực hiện chuyển đổi kiểu. Bài không dùng `@RequestBody` DTO như một MVC controller.

Tham số boolean bắt buộc giúp loại trường hợp thiếu đầu vào. Với request đã vượt qua bảo mật, body thiếu enabled hoặc không chuyển đổi được thành boolean phải bị từ chối, thay vì âm thầm coi là false.

Việc dùng kiểu boolean không đồng nghĩa mọi kiểu validation phức tạp đã được giải quyết. Nếu operation tương lai có miền giá trị hoặc ràng buộc nghiệp vụ khác, cần kiểm tra rõ; không giả định mọi annotation validation của MVC DTO tự áp dụng giống hệt cho operation Actuator.

## 5. Tạo API quan sát ảnh hưởng của cờ

Tệp `src/main/java/demo/maintenance/WorkController.java`:

```java
package demo.maintenance;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final MaintenanceState state;

    public WorkController(MaintenanceState state) {
        this.state = state;
    }

    @GetMapping("/lab/work")
    public ResponseEntity<String> work() {
        if (state.snapshot().enabled()) {
            return ResponseEntity.status(503).body("maintenance");
        }
        return ResponseEntity.ok("accepted");
    }
}
```

Controller sử dụng service trạng thái, không gọi HTTP vào chính endpoint quản trị và không phụ thuộc annotation của Actuator.

Đây là phép mô phỏng: một request đang thực thi không bị hủy khi cờ đổi; không có cơ chế drain traffic, đóng queue hay ngắt transaction. Đọc cờ tại một thời điểm chỉ quyết định nhánh xử lý của request ở thời điểm đọc đó.

Không dùng cờ này để thay thế máy móc liveness/readiness của hệ điều phối. Những tín hiệu đó cần được thiết kế theo khả năng phục vụ thực tế.

## 6. Bảo mật: tách quyền đọc/ghi và giữ CSRF

Tạo ba tài khoản:

| Tài khoản | Authority | Quyền |
| --- | --- | --- |
| reader | maintenance:read | Đọc trạng thái, lấy CSRF token |
| writer | maintenance:read, maintenance:write | Đọc, ghi khi có CSRF hợp lệ |
| app | app:use | Gọi API công việc; không có quyền quản trị |

Đây là authority đầy đủ, nên code dùng `hasAuthority`, không tự nối tiền tố ROLE_.

Mật khẩu của ứng dụng được lấy từ môi trường. Các mật khẩu giả ở test phía sau chỉ là dữ liệu kiểm thử, không phải mật khẩu triển khai.

Tệp `src/main/java/demo/maintenance/SecurityConfiguration.java`:

```java
package demo.maintenance;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            Environment environment) {
        var reader = User.withUsername("reader")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_READER_PASSWORD")))
                .authorities("maintenance:read")
                .build();

        var writer = User.withUsername("writer")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_WRITER_PASSWORD")))
                .authorities("maintenance:read", "maintenance:write")
                .build();

        var app = User.withUsername("app")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_APP_PASSWORD")))
                .authorities("app:use")
                .build();

        return new InMemoryUserDetailsManager(reader, writer, app);
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        RequestMatcher endpoint =
                EndpointRequest.to(MaintenanceEndpoint.class);

        RequestMatcher read = new AndRequestMatcher(
                endpoint,
                request -> "GET".equals(request.getMethod()));

        RequestMatcher write = new AndRequestMatcher(
                endpoint,
                request -> "POST".equals(request.getMethod()));

        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(read)
                        .hasAuthority("maintenance:read")
                        .requestMatchers(write)
                        .hasAuthority("maintenance:write")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/ops/csrf")
                        .hasAnyAuthority(
                                "maintenance:read", "maintenance:write")
                        .requestMatchers(HttpMethod.GET, "/lab/work")
                        .hasAuthority("app:use")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
```

### 6.1. Chọn chuỗi bộ lọc và giới hạn phương thức

Chuỗi bộ lọc Actuator có thứ tự trước và khớp các endpoint Actuator. Bên trong, matcher kết hợp endpoint cụ thể với phương thức HTTP, nên quyền đọc không tự biến thành quyền ghi.

Chuỗi bộ lọc fallback bảo vệ các request còn lại. Nếu chỉ cấu hình một chuỗi bộ lọc khớp Actuator mà không xem request ngoài đó được bảo vệ thế nào, có thể để sót bề mặt HTTP khác.

Các rule của nhiều chuỗi bộ lọc không được cộng dồn cho cùng request; chuỗi bộ lọc khớp đầu tiên theo thứ tự được chọn. Nếu đặt một chuỗi bộ lọc bắt mọi request lên trước, nó có thể che chuỗi bộ lọc quản trị.

EndpointRequest giúp bám đường endpoint theo cấu hình Boot. Nó không thay thế cơ chế xác thực và cũng không phải bộ kiểm tra TCP port.

### 6.2. Vì sao Basic authentication vẫn cần nghĩ đến CSRF?

CSRF là nguy cơ trình duyệt gửi request có thông tin xác thực được tự động đính kèm theo một ngữ cảnh đã có. HTTP Basic không tự loại bỏ nguy cơ này, vì trình duyệt có thể giữ và gửi lại thông tin xác thực.

Bài giữ CSRF mặc định của Spring Security trên cả hai chuỗi bộ lọc. Không có `csrf.disable()` hoặc bỏ qua toàn bộ đường Actuator.

CSRF token và authority giải quyết hai câu hỏi khác nhau:

- Token hợp lệ không cấp quyền maintenance:write cho reader.
- Có quyền maintenance:write không làm POST thiếu token trở thành hợp lệ.

CORS cũng là cơ chế khác. Một phép thử curl thành công không kiểm tra chính sách CORS của trình duyệt; bật/tắt CORS không phải cách thay thế kiểm tra CSRF.

### 6.3. Thứ tự filter ảnh hưởng mã lỗi

Không áp dụng công thức “mọi request chưa đăng nhập đều trả 401” cho mọi POST. CsrfFilter có thể từ chối một request dùng phương thức không an toàn như POST trước khi tới bước xác thực, nên POST không token có thể trả 403 dù chưa có danh tính.

Bộ kiểm thử sẽ tách:

- GET không xác thực để kiểm tra 401.
- POST có CSRF hợp lệ nhưng không xác thực để kiểm tra 401.
- POST của writer thiếu/sai CSRF để kiểm tra 403.
- POST của reader có CSRF hợp lệ để kiểm tra thiếu quyền ghi.

Cách tách này tránh lấy một mã 403 rồi suy đoán sai rằng tài khoản đã được xác thực.

## 7. Cấp CSRF token cho client quản trị

Bài dùng CSRF repository mặc định lưu token trong HTTP session. Client lấy token, giữ cookie session và gửi lại token qua đúng header khi POST. Đây là lý do bài không đặt chính sách session STATELESS.

Tệp `src/main/java/demo/maintenance/OpsCsrfController.java`:

```java
package demo.maintenance;

import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OpsCsrfController {

    @GetMapping("/ops/csrf")
    public ResponseEntity<Map<String, String>> token(CsrfToken csrfToken) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", csrfToken.getHeaderName(),
                        "token", csrfToken.getToken()));
    }
}
```

Endpoint này là controller hỗ trợ client, không phải operation Actuator. Nó được bảo vệ bởi chuỗi bộ lọc dự phòng và chỉ cho danh tính quản trị được phép lấy token.

Token là giá trị động và có thể được che theo cơ chế xử lý token của Spring Security. Client dùng token và headerName đã nhận, không tự đoán định dạng token hoặc hardcode một chuỗi cố định.

Không log token/cookie. Token không thay thế thông tin xác thực; các request ví dụ vẫn gửi HTTP Basic. Nếu session hết hạn hoặc token không còn hợp lệ, client phải lấy lại token theo luồng đã thiết kế.

Khi triển khai vượt ra ngoài loopback, bảo vệ đường truyền bằng TLS hoặc kênh phù hợp. HTTP Basic dùng Base64 không cung cấp tính bí mật trên đường truyền.

## 8. Bộ kiểm thử tích hợp bảo mật

Dùng `@SpringBootTest` và MockMvc có security filter để kiểm tra cả ánh xạ Actuator, binding đầu vào và security chuỗi bộ lọc. Không dùng `addFilters=false`, vì làm vậy sẽ bỏ mất chính đối tượng cần kiểm thử.

Tệp `src/test/java/demo/maintenance/MaintenanceSecurityTest.java`:

```java
package demo.maintenance;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "LAB_READER_PASSWORD=reader-test-pass",
        "LAB_WRITER_PASSWORD=writer-test-pass",
        "LAB_APP_PASSWORD=app-test-pass"
})
@AutoConfigureMockMvc
class MaintenanceSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MaintenanceState state;

    @Autowired
    ObjectMapper objectMapper;

    @BeforeEach
    void startWithMaintenanceDisabled() {
        state.setEnabled(false);
    }

    @Test
    void readAccessIsSeparatedAndGetDoesNotWrite() throws Exception {
        var before = state.snapshot();

        mvc.perform(get("/actuator/maintenance"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/actuator/maintenance")
                        .with(httpBasic("reader", "reader-test-pass"))
                        .param("enabled", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false))
                .andExpect(jsonPath("$.revision").isNumber());

        mvc.perform(get("/actuator/maintenance")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isForbidden());

        assertEquals(before, state.snapshot());
    }

    @Test
    void csrfAndWritePermissionAreIndependent() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf().useInvalidToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("reader", "reader-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("app", "app-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        assertEquals(before, state.snapshot());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "wrong-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isUnauthorized());

        assertEquals(before, state.snapshot());
    }

    @Test
    void writerCanChangeStateAndRepeatTheSameValue() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true));

        var changed = state.snapshot();
        assertEquals(before.revision() + 1, changed.revision());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk());

        assertEquals(changed, state.snapshot());

        mvc.perform(get("/actuator/maintenance")
                        .with(httpBasic("reader", "reader-test-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true));
    }

    @Test
    void invalidInputNeverChangesState() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":\"not-a-boolean\"}"))
                .andExpect(status().isBadRequest());

        assertEquals(before, state.snapshot());
    }

    @Test
    void realTokenAndSessionRoundTripAllowsWrite() throws Exception {
        var tokenResult = mvc.perform(get("/ops/csrf")
                        .with(httpBasic("writer", "writer-test-pass")))
                .andExpect(status().isOk())
                .andReturn();

        var json = objectMapper.readTree(
                tokenResult.getResponse().getContentAsString());

        String headerName = json.get("headerName").asText();
        String token = json.get("token").asText();

        var session = (MockHttpSession)
                tokenResult.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/actuator/maintenance")
                        .session(session)
                        .with(httpBasic("writer", "writer-test-pass"))
                        .header(headerName, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true));

        assertEquals(true, state.snapshot().enabled());
    }

    @Test
    void workApiFollowsTheAuthorizedStateChange() throws Exception {
        mvc.perform(get("/lab/work")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("accepted"));

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk());

        mvc.perform(get("/lab/work")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().string("maintenance"));

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":false}"))
                .andExpect(status().isOk());

        mvc.perform(get("/lab/work")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("accepted"));
    }
}
```

### 8.1. Vì sao không chỉ gọi thẳng phương thức update?

Gọi `endpoint.update(true)` trực tiếp có thể kiểm tra logic thay đổi trạng thái, nhưng không kiểm tra được:

- ánh xạ HTTP của WriteOperation.
- JSON binding và Content-Type.
- Security filter chuỗi bộ lọc.
- Authentication và authority.
- CSRF.

MockMvc ở đây chạy qua các lớp đó trong application context. Nó vẫn không thay thế phép thử trên listener thật, TLS, reverse proxy hoặc firewall.

### 8.2. Vì sao cần cả csrf() và luồng token thật?

`csrf()` của spring-security-test tạo điều kiện để kiểm tra riêng authentication, quyền và binding. Nó không tự chứng minh client quản trị thật có thể lấy token và gửi lại đúng session.

Test `realTokenAndSessionRoundTripAllowsWrite` không dùng helper csrf cho POST. Nó lấy token từ controller, giữ session và đưa token vào header, nên kiểm tra thêm hợp đồng trao đổi token thực tế của bài.

Không dùng `@WithMockUser` như bằng chứng duy nhất rằng mật khẩu ứng dụng được kiểm tra. Bộ test dùng `httpBasic` để đi qua cơ chế xác thực của cấu hình này.

### 8.3. Giữ test độc lập với thứ tự chạy

BeforeEach đưa enabled về false nhưng không ép revision về 0. Các test lấy Snapshot ban đầu và so sánh chênh lệch hoặc tính bất biến.

Nhờ vậy không cần giả định JUnit chạy các phương thức theo một thứ tự cụ thể. Bộ test này dùng trạng thái chia sẻ trong application context, nên không cấu hình các phương thức của nó chạy song song mà chưa có cơ chế cô lập.

Đặc biệt, test request bị từ chối phải xác nhận Snapshot không đổi, không chỉ assert mã HTTP. Một response lỗi không phải bằng chứng đầy đủ rằng tác động phụ chưa xảy ra.

### 8.4. Chạy kiểm thử

```bash
./gradlew test
```

Trên Windows dùng `gradlew.bat test`. Với multi-project build, dùng task path của đúng module.

Kết quả cần đạt là cả bảy test thành công. Dạng console, thời gian chạy và log khởi động phụ thuộc môi trường; không coi chúng là stdout cố định. Các password chứa hậu tố test-pass trong mã trên là dữ liệu giả chỉ dành cho test.

## 9. Ma trận kết quả cần đạt

Với đúng cấu hình của bài:

| Request | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| GET maintenance | Không xác thực | 401 |
| GET maintenance | reader, mật khẩu đúng | 200, đọc Snapshot |
| GET maintenance | app, mật khẩu đúng | 403 |
| GET maintenance?enabled=true | reader | 200, không thay đổi trạng thái |
| POST maintenance | writer, thiếu CSRF | 403, trạng thái không đổi |
| POST maintenance | writer, CSRF sai | 403, trạng thái không đổi |
| POST maintenance | reader, CSRF hợp lệ | 403, trạng thái không đổi |
| POST maintenance | app, CSRF hợp lệ | 403, trạng thái không đổi |
| POST maintenance | Không xác thực, CSRF hợp lệ | 401, trạng thái không đổi |
| POST maintenance | writer sai mật khẩu, CSRF hợp lệ | 401, trạng thái không đổi |
| POST maintenance | writer, CSRF hợp lệ, body hợp lệ | 200, thay đổi theo body |
| POST maintenance | writer, CSRF hợp lệ, body thiếu/sai enabled | 400, trạng thái không đổi |

Một test về binding phải cung cấp authentication và CSRF hợp lệ; nếu không, request có thể bị chặn trước khi tới bước đọc body và test chưa kiểm tra được binding.

Tương tự, để kiểm tra quyền ghi của reader, cần CSRF hợp lệ. Nếu reader thiếu token và nhận 403, chưa thể kết luận rule authority đã được thực thi.

## 10. Chạy ứng dụng cục bộ

Ví dụ PowerShell dưới đây nhập mật khẩu không hiển thị trên terminal. Dùng các mật khẩu không rỗng; để phép thử Basic giữa các client dễ tái hiện, có thể chọn chuỗi ASCII trong phiên lab.

```powershell
$labReaderSecret = Read-Host "Password for reader" -AsSecureString
$env:LAB_READER_PASSWORD = [System.Net.NetworkCredential]::new("", $labReaderSecret).Password

$labWriterSecret = Read-Host "Password for writer" -AsSecureString
$env:LAB_WRITER_PASSWORD = [System.Net.NetworkCredential]::new("", $labWriterSecret).Password

$labAppSecret = Read-Host "Password for app" -AsSecureString
$env:LAB_APP_PASSWORD = [System.Net.NetworkCredential]::new("", $labAppSecret).Password

.\gradlew.bat bootJar
java -jar build/libs/maintenance-endpoint-lab.jar
```

Trên Bash, đặt ba biến môi trường tương ứng rồi dùng `./gradlew bootJar`. Không đưa giá trị mật khẩu thật vào source hoặc các đối số được lưu trong lịch sử lệnh.

Các class ứng dụng cần dependency của framework. Lệnh `java -jar` chạy executable JAR; không biên dịch riêng từng tệp bằng `javac` mà bỏ classpath Spring Boot.

Giữ tiến trình chạy và mở terminal khác để kiểm tra. Trên Windows, dùng `curl.exe` để tránh nhầm với alias PowerShell. Chỉ truyền username cho `--user` để curl hỏi mật khẩu.

Trên một tiến trình mới, đọc trạng thái:

```powershell
curl.exe -i --user reader http://127.0.0.1:8080/actuator/maintenance
```

Kỳ vọng HTTP 200 với JSON tương đương:

```json
{"enabled":false,"revision":0}
```

Thứ tự các trường JSON và header HTTP không phải hợp đồng cố định. Không dự đoán timestamp hoặc toàn bộ log khởi động.

Kiểm tra công việc:

```powershell
curl.exe -i --user app http://127.0.0.1:8080/lab/work
```

Khi cờ false, body là `accepted`, HTTP 200. Code không tự thêm ký tự xuống dòng vào body.

## 11. Gửi POST có CSRF qua một luồng client thật

Phần này dùng PowerShell để đọc JSON, không yêu cầu cài thêm công cụ phân tích JSON. Những tệp tạo ra chỉ dành cho client cục bộ; cookie và CSRF token cần được giữ trong phạm vi phiên thực hành.

### 11.1. Lấy token và giữ cookie

```powershell
curl.exe --fail --silent --show-error --user writer --cookie-jar maintenance-lab-cookies.txt --output maintenance-lab-csrf.json http://127.0.0.1:8080/ops/csrf

$labCsrf = Get-Content -LiteralPath maintenance-lab-csrf.json -Raw | ConvertFrom-Json
```

Nhập đúng mật khẩu writer khi curl hỏi. Nếu curl lỗi, xử lý lỗi trước khi đọc file; không tiếp tục dùng một file token cũ từ phiên khác.

Việc controller truy cập token khiến token được tạo/lưu theo repository của bài. Cookie session giúp request tiếp theo tìm lại đúng token phía server.

### 11.2. Chuẩn bị body và gửi ghi

Dùng file body để tránh khác biệt đặt dấu nháy JSON giữa các shell:

```powershell
Set-Content -LiteralPath maintenance-lab-write.json -Value '{"enabled":true}' -Encoding Ascii -NoNewline

curl.exe -i --user writer --cookie maintenance-lab-cookies.txt --header "$($labCsrf.headerName): $($labCsrf.token)" --header "Content-Type: application/json" --data-binary "@maintenance-lab-write.json" http://127.0.0.1:8080/actuator/maintenance
```

`--data-binary` làm request dùng POST. Header token được lấy từ phản hồi, không tự đặt một giá trị token đoán trước.

Trên tiến trình mới và chưa có lần thay đổi nào khác, kỳ vọng HTTP 200 với JSON tương đương:

```json
{"enabled":true,"revision":1}
```

Gửi lại cùng giá trị trên cùng trạng thái sẽ không làm revision tăng. Nếu session/token đã hết hiệu lực hoặc thay đổi sau thao tác xác thực, lấy lại token; không sửa rule bảo mật để che một lỗi quản lý session của client.

### 11.3. Kiểm tra sau thao tác

```powershell
curl.exe -i --user reader http://127.0.0.1:8080/actuator/maintenance
curl.exe -i --user app http://127.0.0.1:8080/lab/work
```

Reader vẫn đọc được trạng thái nhưng không có quyền ghi. API công việc trả HTTP 503 và body `maintenance` khi cờ bật.

Để khôi phục, đổi body thành false, dùng token/session hợp lệ rồi POST:

```powershell
Set-Content -LiteralPath maintenance-lab-write.json -Value '{"enabled":false}' -Encoding Ascii -NoNewline

curl.exe -i --user writer --cookie maintenance-lab-cookies.txt --header "$($labCsrf.headerName): $($labCsrf.token)" --header "Content-Type: application/json" --data-binary "@maintenance-lab-write.json" http://127.0.0.1:8080/actuator/maintenance
```

Nếu chỉ có hai lần chuyển false→true→false, Snapshot cuối có enabled=false, revision=2 và API công việc lại trả accepted.

### 11.4. Thử request ghi không có token

Vẫn gửi mật khẩu writer nhưng bỏ cookie/header CSRF:

```powershell
curl.exe -i --user writer --header "Content-Type: application/json" --data-binary "@maintenance-lab-write.json" http://127.0.0.1:8080/actuator/maintenance
```

Kỳ vọng 403. Đọc Snapshot trước và sau để xác nhận không có thay đổi. Request này kiểm tra CSRF, không kiểm tra rằng writer thiếu quyền ghi.

Không cố định token vào source, không đặt token trong URL và không gửi toàn bộ cookie/token vào log hoặc ảnh chụp báo cáo.

## 12. Chẩn đoán khi kết quả khác dự kiến

| Hiện tượng | Kiểm tra theo thứ tự |
| --- | --- |
| Ứng dụng không khởi động vì thiếu property | Ba biến môi trường có thuộc tiến trình Java đang chạy không? |
| 404 ở đường endpoint | Bean @Endpoint, id, enablement, exposure, base path và đúng instance |
| 404 ở /maintenance/update | Tên method Java không tự tạo URL; dùng POST vào endpoint gốc |
| 401 khi đọc với writer | Username/password và cơ chế HTTP Basic thực tế |
| 403 khi POST bằng writer | Token có hợp lệ, cookie có đúng session và request vào chuỗi bộ lọc nào? |
| 403 với reader có token hợp lệ | Kỳ vọng: reader không có maintenance:write |
| 400 dù body trông đúng | Content-Type, tên enabled, chuyển đổi kiểu và thông tin tên tham số -parameters |
| 415 | Kiểu nội dung gửi không phù hợp operation |
| 405 hoặc bị từ chối ở phương thức khác | Operation nào được khai báo và security rule cho phương thức đó |
| POST trả lỗi nhưng trạng thái đổi | Kiểm tra tác động phụ xảy ra trước bước từ chối hay lỗi sau khi ghi; cần test trạng thái |
| Ghi true thành công nhưng instance khác vẫn false | Trạng thái trong bài chỉ nằm trong bộ nhớ của một JVM |
| GET hiển thị cũ sau khi cấu hình thêm cache | Kiểm tra TTL/cache của read operation và tính nhất quán cần có |
| Test thành công nhưng curl thất bại | So sánh CSRF helper với luồng token/session thật, artifact và hạ tầng HTTP |

Một 404 từ proxy hoặc một 403 trước binding không chứng minh rằng tham số đã được kiểm tra. Xác định lớp thực sự trả lỗi bằng log có kiểm soát và phản hồi quan sát được.

Khi cần log Spring Security, chỉ bật trong phiên chẩn đoán phù hợp. Không in Authorization, mật khẩu, cookie hoặc token. Sau thay đổi về chuỗi bộ lọc/matcher, chạy lại cả test cho phép và từ chối; một rule chung có thể làm sai nhiều đường cùng lúc.

Không dùng phép gọi trực tiếp method như bằng chứng “endpoint an toàn”, và không dùng một test chỉ assert HTTP status như bằng chứng tác động phụ đã được ngăn chặn.

## 13. Những điều cần quyết định trước khi dùng ngoài bài lab

### Trạng thái nhiều instance và độ bền

AtomicReference chỉ giải quyết tranh chấp trong một JVM. Nó không đồng bộ giữa các replica và không tồn tại qua restart.

Nếu cờ phải có hiệu lực toàn cụm, cần một nguồn trạng thái bền vững/chia sẻ với cơ chế cập nhật, phiên bản và xử lý lỗi rõ ràng. Phản hồi của một instance không tự chứng minh mọi instance đã cập nhật.

### Nhật ký thao tác và trách nhiệm vận hành

Một thao tác ghi có ý nghĩa vận hành nên có dấu vết ai yêu cầu, thời điểm, thay đổi trước/sau và kết quả theo chính sách hệ thống. Không đưa token hoặc credential vào bản ghi đó.

Nếu sau này thêm audit vào hàm CAS update, không đặt gửi log ra ngoài hay ghi database trong hàm cập nhật có thể được chạy lại. Thiết kế vị trí ghi nhật ký thao tác và tính nhất quán theo giao dịch thực tế.

Bài chưa triển khai nhật ký thao tác bền vững, approval workflow hoặc cơ chế rollback phân tán; các khả năng đó không được suy ra chỉ từ việc có quyền write.

### Bảo vệ đúng mọi kênh được công bố

SecurityFilterChain trong bài bảo vệ HTTP Servlet. Nếu một endpoint còn được đưa ra JMX hoặc một kênh quản trị khác, cần kiểm soát riêng kênh đó. Exposure HTTP không tự là chính sách bảo mật chung cho mọi transport.

Tương tự, quyền ở reverse proxy không tự bảo vệ một cổng backend vẫn truy cập trực tiếp được. Đối chiếu tuyến request thật khi triển khai.

### Thiết kế client và loại thao tác

Giữ CSRF trong mô hình Basic/session của bài là lựa chọn có chủ đích. Nếu chuyển sang một API quản trị dùng bearer token với mô hình client khác, phải đánh giá lại cơ chế gửi credential và nguy cơ CSRF trước khi thay cấu hình; không tắt trên mọi endpoint theo một ví dụ không cùng giả định.

Thao tác nặng hoặc kéo dài cần hợp đồng riêng về timeout, trạng thái công việc và tính lặp lại. Không đặt công việc không giới hạn trong một request quản trị đồng bộ rồi coi mã 200 là đủ.

## 14. Nghiệm thu và kết thúc

Bài hoàn thành khi:

1. GET chỉ đọc và không thay đổi trạng thái dù có tham số query trông giống lệnh ghi.
2. POST ánh xạ đúng enabled từ JSON và trả Snapshot sau thao tác.
3. Reader không ghi được dù có CSRF hợp lệ.
4. Writer không ghi được khi thiếu/sai CSRF.
5. CSRF hợp lệ không thay thế authentication.
6. Dữ liệu thiếu/sai bị từ chối mà Snapshot không đổi.
7. Ghi lại cùng giá trị không tăng revision.
8. Bộ test bao gồm cả helper CSRF và một luồng lấy token/session thực tế.
9. API mô phỏng đổi hành vi sau thao tác được cấp quyền và phục hồi khi cờ tắt.
10. Giới hạn trạng thái một JVM và phạm vi bảo vệ HTTP được ghi rõ.

Kết thúc phiên, khôi phục cờ false nếu tiến trình còn dùng, dừng ứng dụng rồi xóa những tệp client đã tạo trong thư mục thử nghiệm:

```powershell
Remove-Item -LiteralPath maintenance-lab-cookies.txt,maintenance-lab-csrf.json,maintenance-lab-write.json
Remove-Item Env:LAB_READER_PASSWORD
Remove-Item Env:LAB_WRITER_PASSWORD
Remove-Item Env:LAB_APP_PASSWORD
```

Chỉ xóa đúng những tệp của phiên lab tại thư mục đã tạo chúng. Xóa biến môi trường ở terminal không thu hồi môi trường của một tiến trình Java đã chạy trước đó; phải dừng tiến trình riêng.

Bằng chứng cốt lõi là mỗi request chỉ được gây tác động phụ sau khi vượt qua các cổng kiểm tra đã thiết kế, và request bị từ chối để lại trạng thái không đổi. Bộ kiểm thử cần xác nhận cả hai mặt đó.
