# Kiểm chứng status, phản hồi lỗi và việc nghiệp vụ không bị thực thi

Khi kiểm thử một HTTP endpoint được bảo vệ bởi Spring Security, chỉ thấy mã **401** hoặc **403** là chưa đủ. Một bài kiểm thử có ý nghĩa cần chứng minh đồng thời ba điều: **HTTP status đúng**, **phản hồi lỗi đúng hợp đồng API**, và **đường xử lý nghiệp vụ không được gọi khi truy cập bị từ chối**. Đây là bài kiểm thử ở ranh giới HTTP của module **Spring Security – authorization**, với ví dụ Servlet/Spring MVC dùng MockMvc, JUnit 5 và Mockito.

## 1. Ba bằng chứng độc lập cần kiểm tra

| Bằng chứng | Kiểm tra | Tại sao cần thiết |
| --- | --- | --- |
| HTTP status | 401, 403, 200, 204 theo từng trường hợp | Cho client biết kết quả yêu cầu theo giao thức. |
| Phản hồi lỗi | Content-Type, mã lỗi ứng dụng, thông điệp, header cần thiết | Client nhận được cấu trúc ổn định; tránh lộ stack trace hoặc dữ liệu nhạy cảm. |
| Không thực thi nghiệp vụ | Không gọi service/command/repository ở nhánh bị chặn | Ngăn thay đổi trạng thái, truy vấn không được phép và tác dụng phụ. |

**401 Unauthorized** thường cho biết yêu cầu chưa được xác thực hợp lệ. **403 Forbidden** thường cho biết danh tính đã được xác thực nhưng không đủ quyền; 403 cũng có thể do thiếu/sai CSRF token. Hành vi thực tế còn phụ thuộc cơ chế xác thực: ứng dụng form-login có thể trả **302** về trang đăng nhập, còn REST API dùng Basic/Bearer thường trả **401**. Vì vậy, test phải bám theo hợp đồng API đang cấu hình, không áp một mã status cho mọi ứng dụng.

Với HTTP Basic, phản hồi 401 cần có header **WWW-Authenticate** phù hợp. Với ứng dụng dùng Bearer token, kiểm thử xác thực JWT, token hết hạn và header challenge là một lớp kiểm thử khác; một user giả lập bằng @WithMockUser không chứng minh việc xác minh token thật.

## 2. Điểm chặn trong luồng xử lý HTTP

Một yêu cầu Servlet đi qua **SecurityFilterChain** trước khi đến **DispatcherServlet/Controller**. Khi luật của **authorizeHttpRequests** từ chối yêu cầu, HTTP handler thông thường chưa chạy. Spring Security đưa lỗi xác thực hoặc thiếu quyền đến thành phần xử lý lỗi thích hợp, ví dụ **AuthenticationEntryPoint** (401) hoặc **AccessDeniedHandler** (403). Nếu yêu cầu được chấp nhận, controller mới gọi service nghiệp vụ.

~~~mermaid
flowchart LR
    A[HTTP request] --> B[SecurityFilterChain]
    B -->|Chặn| C[HTTP 401/403 + error response]
    B -->|Cho phép| D[Controller]
    D --> E[Business service]
    E --> F[HTTP success]
~~~

Đây là lý do nên dùng MockMvc **có tích hợp Spring Security filters** để chứng minh quyền truy cập ở lớp HTTP. Gọi trực tiếp phương thức controller hoặc dựng MockMvc kiểu standalone mà không gắn bộ lọc security có thể khiến bài kiểm thử bỏ qua đúng lớp cần kiểm tra.

Cần phân biệt vị trí chặn: với **@PreAuthorize trên service**, controller có thể đã chạy, nhưng thân service bị từ chối trước khi thực thi; với **@PostAuthorize**, phương thức có thể đã thực thi rồi mới bị từ chối. Bởi vậy, không được suy diễn “403 nghĩa là chắc chắn không có tác dụng phụ”. Phải xác định biên bảo vệ và kiểm tra chính xác collaborator/state tương ứng.

## 3. Ma trận kịch bản tối thiểu

Dùng API minh họa: GET /api/payments/{id} đọc thông tin, POST /api/payments/{id}/approve thực hiện duyệt; cả hai yêu cầu role **APPROVER**. Security bật CSRF mặc định cho yêu cầu thay đổi trạng thái.

| Request | Người dùng / điều kiện | Status kỳ vọng | Bằng chứng nghiệp vụ |
| --- | --- | --- | --- |
| GET /api/payments/p-100 | Không đăng nhập | 401 + AUTH_REQUIRED | Không gọi PaymentService. |
| GET /api/payments/p-100 | Đã đăng nhập, role VIEWER | 403 + ACCESS_DENIED | Không gọi PaymentService. |
| GET /api/payments/p-100 | Role APPROVER | 200 + nội dung hợp lệ | findById được gọi một lần. |
| POST /api/payments/p-100/approve | Role APPROVER nhưng thiếu CSRF token | 403 | Không gọi PaymentService. |
| POST /api/payments/p-100/approve | Role APPROVER và có CSRF token hợp lệ | 204 | approve được gọi một lần. |

Không trộn các điều kiện: muốn kiểm tra **thiếu quyền trên POST**, trước hết cấp CSRF token hợp lệ để CSRF filter không chặn sớm; muốn kiểm tra **CSRF**, giữ role hợp lệ để cô lập nguyên nhân. Status 400 (dữ liệu không hợp lệ), 404 (không tìm thấy tài nguyên) hoặc 500 (lỗi server) không tự chứng minh service chưa chạy; nhiều trường hợp cần thực thi nghiệp vụ rồi mới trả các mã đó.

## 4. Ví dụ có thể chạy với Java 17 và Spring Boot 3.3

Dự án mẫu dùng Spring MVC + Spring Security 6.x. Đặt các tệp theo đường dẫn hiển thị dưới đây. Gradle đã được cài hoặc dự án có Gradle Wrapper.

**settings.gradle**

~~~groovy
rootProject.name = 'http-security-test-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '0.0.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/httpsecurity/DemoApplication.java**

~~~java
package demo.httpsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/httpsecurity/PaymentService.java**

~~~java
package demo.httpsecurity;

public interface PaymentService {
    String findById(String id);
    void approve(String id);
}
~~~

**src/main/java/demo/httpsecurity/InMemoryPaymentService.java**

~~~java
package demo.httpsecurity;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
class InMemoryPaymentService implements PaymentService {
    private final Set<String> approvedIds = ConcurrentHashMap.newKeySet();

    @Override
    public String findById(String id) {
        return approvedIds.contains(id) ? "approved:" + id : "pending:" + id;
    }

    @Override
    public void approve(String id) {
        approvedIds.add(id);
    }
}
~~~

Phần triển khai bộ nhớ chỉ giúp dự án chạy độc lập. Ở lớp test HTTP bên dưới, service sẽ được thay bằng Mockito mock để phát hiện việc gọi nghiệp vụ. Trong hệ thống thật, service có thể cập nhật database, gọi API hoặc gửi sự kiện; đó là những tác dụng phụ cần được kiểm chứng thêm ở test tích hợp khi thích hợp.

**src/main/java/demo/httpsecurity/PaymentController.java**

~~~java
package demo.httpsecurity;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/payments")
public class PaymentController {
    private final PaymentService service;

    public PaymentController(PaymentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public String getPayment(@PathVariable String id) {
        return service.findById(id);
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<Void> approve(@PathVariable String id) {
        service.approve(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

**src/main/java/demo/httpsecurity/HttpSecurityConfig.java**

~~~java
package demo.httpsecurity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class HttpSecurityConfig {
    private static final AuthenticationEntryPoint UNAUTHORIZED =
            (request, response, exception) -> {
                response.setHeader(
                        HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo-api\"");
                writeError(response, 401, "AUTH_REQUIRED",
                        "Authentication required");
            };

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/payments/**").hasRole("APPROVER")
                .anyRequest().denyAll())
            .httpBasic(basic -> basic.authenticationEntryPoint(UNAUTHORIZED))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(UNAUTHORIZED)
                .accessDeniedHandler((request, response, exception) ->
                    writeError(response, 403, "ACCESS_DENIED",
                            "Permission denied")));
        // Giữ CSRF mặc định để kiểm thử POST có/không có token.
        return http.build();
    }

    private static void writeError(
            HttpServletResponse response, int status,
            String code, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("""
                {"code":"%s","message":"%s"}
                """.formatted(code, message));
    }
}
~~~

Hợp đồng lỗi JSON ở đây được **khai báo chủ động**. Không nên giả định Spring Security tự tạo các trường code/message này. Trong mẫu, lỗi xác thực và thiếu quyền từ nhánh authorization có JSON thống nhất; CSRF filter có đường xử lý từ chối riêng, nên ví dụ kiểm tra status 403 cho CSRF nhưng không khẳng định body của nó cũng có mã ACCESS_DENIED. Muốn tất cả lỗi bảo mật cùng cấu trúc thì phải cấu hình và kiểm thử từng điểm phát sinh lỗi.

## 5. Test HTTP: status, body, header và không gọi service

**src/test/java/demo/httpsecurity/PaymentSecurityHttpTest.java**

~~~java
package demo.httpsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PaymentController.class)
@Import(HttpSecurityConfig.class)
class PaymentSecurityHttpTest {
    @Autowired
    private MockMvc mvc;

    @MockBean
    private PaymentService service;

    @Test
    void anonymousRequestReturns401AndNeverCallsBusiness() throws Exception {
        mvc.perform(get("/api/payments/p-100"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo-api\""))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("AUTH_REQUIRED"))
            .andExpect(jsonPath("$.message").value("Authentication required"));

        verifyNoInteractions(service);
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void insufficientRoleReturns403AndNeverCallsBusiness() throws Exception {
        mvc.perform(get("/api/payments/p-100"))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.message").value("Permission denied"));

        verifyNoInteractions(service);
    }

    @Test
    @WithMockUser(roles = "APPROVER")
    void authorizedGetCallsBusinessOnce() throws Exception {
        given(service.findById("p-100")).willReturn("pending:p-100");

        mvc.perform(get("/api/payments/p-100"))
            .andExpect(status().isOk())
            .andExpect(content().string("pending:p-100"));

        verify(service).findById("p-100");
        verifyNoMoreInteractions(service);
    }

    @Test
    @WithMockUser(roles = "APPROVER")
    void missingCsrfReturns403WithoutApproval() throws Exception {
        mvc.perform(post("/api/payments/p-100/approve"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(service);
    }

    @Test
    @WithMockUser(roles = "APPROVER")
    void validCsrfAllowsApproval() throws Exception {
        mvc.perform(post("/api/payments/p-100/approve").with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));

        verify(service).approve("p-100");
        verifyNoMoreInteractions(service);
    }
}
~~~

**Tại sao cách kiểm tra này có giá trị?**

1. **@WebMvcTest** dựng phần web cần thiết, **@Import(HttpSecurityConfig.class)** dùng đúng luật URL đang minh họa, và MockMvc của Spring Boot áp dụng security filters. Nhờ đó, lời gọi HTTP thật sự đi qua kiểm tra phân quyền.
2. **@WithMockUser(roles = "VIEWER")** đưa principal đã xác thực với authority ROLE_VIEWER vào test; **hasRole("APPROVER")** yêu cầu ROLE_APPROVER. Với trường hợp anonymous, test không khai báo @WithMockUser.
3. Các assertion status, Content-Type, header và JSONPath độc lập với việc kiểm chứng service. **verifyNoInteractions(service)** thất bại nếu mock nhận **bất kỳ lời gọi nào** trong nhánh bị chặn; như vậy status đúng nhưng controller vẫn truy cập service cũng không vượt qua test.
4. Test thành công đóng vai trò **đối chứng**: với role hợp lệ, filter cho request đi tới controller và service thật sự được gọi đúng một lần. Nếu chỉ viết các test bị chặn, một cấu hình từ chối tất cả request vẫn có thể làm chúng cùng xanh.
5. Với POST, **.with(csrf())** cung cấp token hợp lệ trong MockMvc. Thiếu token sẽ bị chặn trước lời gọi approve. Điều này giúp tách kiểm thử CSRF khỏi kiểm thử role.

Trong Spring Boot 3.3, **@MockBean** là lựa chọn tương thích. Ở các dòng Spring Boot mới hơn, hãy theo API mock bean mà phiên bản đó cung cấp (ví dụ @MockitoBean); không trộn annotation/version tùy tiện. Mockito mock được Spring Boot quản lý qua test context; tránh đưa trạng thái tương tác từ test này sang test khác.

Chạy tại thư mục dự án:

~~~bash
gradle test --tests demo.httpsecurity.PaymentSecurityHttpTest
~~~

Nếu dự án đã có Gradle Wrapper thì dùng ./gradlew trên Unix/macOS hoặc gradlew.bat trên Windows với cùng các đối số. Khi cấu hình đúng, **cả năm test cần PASS**; các kết quả HTTP kỳ vọng lần lượt là **401, 403, 200, 403 và 204**. Lệnh chạy test không khởi động một HTTP server độc lập; MockMvc tạo request/response trong Spring test context.

## 6. Phân biệt “không gọi mock” và “không có tác dụng phụ”

**verifyNoInteractions(service)** chứng minh controller không gọi mock PaymentService trong các request bị chặn của chính bộ test này. Nó **không tự động** chứng minh không có ghi database, gửi message, gọi API ngoài hoặc công việc bất đồng bộ ở những thành phần khác. Chọn bằng chứng theo kiến trúc thật:

- **URL authorization trước controller:** mock service và kiểm tra verifyNoInteractions/never tại ranh giới ngay sau security.
- **@PreAuthorize ở service:** đặt phép đo tại thân nghiệp vụ hoặc repository; controller có thể đã chạy nhưng thao tác nhạy cảm phải bị chặn.
- **@PostAuthorize hoặc lỗi phát sinh sau xử lý:** không được mặc định coi tác dụng phụ đã được hoàn tác; tránh dùng post-authorization như lớp bảo vệ duy nhất cho thao tác ghi.
- **Database, queue, API ngoài:** bổ sung integration test với trạng thái trước/sau, số bản ghi, spy hoặc fake phù hợp; test rollback riêng nếu dùng transaction.
- **Async processing:** chờ/dispatch và quan sát đúng vòng đời bất đồng bộ, không kết luận chỉ từ response đến sớm.

Ví dụ một assertion đơn lẻ như **status().isForbidden()** có thể PASS dù service đã chạy và sau đó ném AccessDeniedException. Vì vậy phải kiểm tra trạng thái/collaborator sau request và xác định quyền được áp dụng ở tầng nào.

## 7. Thiết kế kiểm thử lỗi đáng tin cậy

Một hợp đồng lỗi phù hợp có thể quy định **status**, **Content-Type**, **code**, **message**, **requestId** hoặc các trường của **ProblemDetail**. Các field cụ thể cần thống nhất với API thật; không viết test dựa vào default body không được bảo đảm giữa các phiên bản/framework. Kiểm tra các giá trị có ý nghĩa lâu dài, tránh so sánh toàn bộ JSON dưới dạng chuỗi nếu thứ tự field không thuộc hợp đồng.

Để phản hồi lỗi an toàn và dễ sử dụng:

- Không trả stack trace, thông tin nội bộ, credential, token hoặc dữ liệu của tài nguyên bị từ chối.
- Giữ mã lỗi ứng dụng ổn định để client có thể xử lý; thông điệp cho người dùng có thể được bản địa hóa.
- Với Basic authentication, kiểm tra WWW-Authenticate ở 401; với Bearer, test challenge theo chuẩn và cấu hình resource server thực tế.
- Phân biệt 401/403 do xác thực, role, CSRF và quyền theo đối tượng. Trong một số API, 404 có thể được dùng có chủ ý để tránh tiết lộ sự tồn tại của tài nguyên; đó phải là hợp đồng được thiết kế và kiểm thử.
- Nếu có nhiều SecurityFilterChain, chọn đúng URL/matcher để test thực sự dùng chain cần đánh giá.

**Một lỗi thường gặp:** dùng 403 mặc định như bằng chứng “thiếu role”. Một POST không có CSRF token có thể bị chặn trước khi rule role được đánh giá. Khi cần test role bằng POST, cấp token hợp lệ bằng csrf(); sau đó mới xác minh role và không gọi nghiệp vụ.

**Một lỗi khác:** tắt filters bằng addFilters = false, gọi controller trực tiếp, hoặc tự mock kết quả 403. Các cách đó có thể hữu ích cho unit test của controller nhưng không chứng minh authorization filter. Tương tự, @WithMockUser kiểm tra quyết định dựa trên principal/authorities giả lập; nó không kiểm tra mật khẩu, JWT signature hay OAuth2 login thật.

## 8. Quy trình áp dụng cho endpoint khác

1. **Xác định chính sách:** endpoint, HTTP method, cơ chế xác thực, role/authority, owner/tenant và yêu cầu CSRF.
2. **Xác định response contract:** status từng nhánh; header; body hoặc ProblemDetail; những dữ liệu không được tiết lộ.
3. **Chọn điểm kiểm chứng nghiệp vụ:** service, command handler, repository, sự kiện hoặc trạng thái dữ liệu; mô phỏng tối thiểu để phát hiện tương tác ngoài ý muốn.
4. **Dựng ma trận negative + positive control:** anonymous, thiếu quyền, đủ quyền, thiếu/sai CSRF nếu áp dụng, quyền theo chủ sở hữu đối tượng.
5. **Chạy test qua filter chain thật:** MockMvc tích hợp Spring Security; dùng mock principal cho test authorization và thêm test riêng cho cơ chế xác thực/token.
6. **Assert ba mặt:** status, error contract, không có lời gọi/tác dụng phụ; ở positive control xác nhận nghiệp vụ thực sự chạy.
7. **Kiểm tra khi đổi policy:** thay URL matcher, role, thứ tự SecurityFilterChain hoặc handler lỗi phải khiến test liên quan phát hiện thay đổi ngoài ý muốn.

### Tự kiểm chứng cách hiểu

- Nếu GET không đăng nhập trả 401 nhưng verifyNoInteractions thất bại, ta có status đúng nhưng **chưa bảo vệ được lời gọi nghiệp vụ**.
- Nếu POST của APPROVER trả 403 khi không có csrf(), chưa đủ bằng chứng người dùng thiếu quyền; đó có thể là CSRF rejection.
- Nếu user APPROVER nhận 200 nhưng findById không được gọi, bài kiểm thử cần xem lại endpoint/đối chứng vì nó chưa chứng minh luồng xử lý đúng.
- Nếu service đã cập nhật database rồi mới trả 403, phải xem **vị trí áp dụng authorization, transaction và điểm phát sinh lỗi**; không suy luận dữ liệu tự động rollback.

## Tài liệu chính thức

- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — MockMvc setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — running as a user: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- Spring Security — CSRF testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Boot 3.3 — testing web MVC: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
