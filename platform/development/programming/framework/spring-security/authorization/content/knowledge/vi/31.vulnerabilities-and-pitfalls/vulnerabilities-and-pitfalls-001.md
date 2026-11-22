# Đăng nhập thành công nhưng thiếu kiểm tra quyền trên chức năng

## 1. Vấn đề: đã xác thực nhưng vẫn có thể làm việc không được phép

Một người dùng nhập đúng tên tài khoản và mật khẩu chỉ chứng minh hệ thống **đã xác thực (authentication)** được danh tính của họ. Việc người đó có quyền sử dụng một **chức năng (function)** cụ thể — phê duyệt hóa đơn, xuất dữ liệu, khóa tài khoản, cập nhật giá hoặc xóa báo cáo — là quyết định **phân quyền (authorization)** riêng biệt, phải được máy chủ thực hiện cho từng thao tác nhạy cảm.

Lỗ hổng xuất hiện khi ứng dụng kiểm tra “đã đăng nhập chưa?” nhưng bỏ qua “người này có được thực hiện thao tác này không?”. Ví dụ: người dùng chỉ được **xem** báo cáo vẫn gọi thành công thao tác **xuất bản** báo cáo vì cả hai chức năng nằm sau cùng một quy tắc **authenticated()**. Việc giao diện đã ẩn nút “Xuất bản” không ngăn được yêu cầu HTTP được gửi trực tiếp.

Đây là một dạng **Broken Function Level Authorization (BFLA)**, được OWASP xếp vào **API5:2023** của API Security Top 10. Hậu quả phụ thuộc vào chức năng bị bỏ sót: nâng quyền, đọc/xuất dữ liệu, thay đổi cấu hình, phê duyệt trái phép, xóa dữ liệu hoặc gián đoạn hoạt động.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt đăng nhập thành công với quyết định cho phép thực thi một chức năng.
2. Nhận biết các điểm dễ bỏ sót quyền: controller, endpoint quản trị lẫn trong API thường, HTTP method mới, service được tái sử dụng và thao tác chạy không qua giao diện.
3. Thiết kế bảng quyền theo **chủ thể – thao tác – tài nguyên – điều kiện** và xác định mặc định từ chối.
4. Bảo vệ chức năng ở tầng HTTP bằng Spring Security và ở tầng service bằng method security.
5. Kiểm thử cả **được phép** lẫn **bị từ chối**, kể cả yêu cầu đến từ tài khoản đã đăng nhập hợp lệ.
6. Phân biệt lỗi thiếu quyền trên chức năng với lỗi thiếu quyền trên một đối tượng dữ liệu cụ thể.

**Phạm vi:** Ứng dụng Java 17+, Spring Boot 3.x, Spring Security 6.x trên Servlet/Spring MVC. Cú pháp và bộ lọc cho ứng dụng Reactive/WebFlux khác về cách cấu hình, dù nguyên tắc phân quyền giống nhau.

## 2. Mối liên hệ giữa xác thực, quyền chức năng và quyền dữ liệu

Xét hệ thống báo cáo có hai hành động:

- **Đọc báo cáo:** yêu cầu authority **report:read**.
- **Xuất bản báo cáo:** yêu cầu authority **report:publish**.

Một tài khoản chỉ có report:read đăng nhập hợp lệ thì **được xem** nhưng **phải bị từ chối** khi xuất bản.

~~~text
Yêu cầu HTTP
  │
  ├── Có xác thực hợp lệ không?
  │     ├── Không → cơ chế authentication entry point xử lý
  │     └── Có
  │          │
  │          ├── Có quyền thực hiện chức năng? (report:publish)
  │          │      ├── Không → từ chối, không chạy nghiệp vụ
  │          │      └── Có
  │          │          │
  │          │          ├── Có quyền với đối tượng này? (nếu áp dụng)
  │          │          │      ├── Không → từ chối
  │          │          │      └── Có → thực thi nghiệp vụ
  │          │          │
  │          │          └── Ghi nhận kết quả để kiểm toán
~~~

| Kiểm tra | Câu hỏi | Minh họa |
| --- | --- | --- |
| Xác thực | Ai đang gửi yêu cầu? | Người dùng Alice đã đăng nhập |
| Quyền chức năng | Alice có được gọi thao tác publish không? | Alice có report:publish? |
| Quyền đối tượng | Alice có được publish **báo cáo 42** không? | Báo cáo thuộc tenant/phòng ban Alice được phép? |
| Điều kiện ngữ cảnh | Có điều kiện bổ sung tại thời điểm gọi không? | Báo cáo còn ở trạng thái DRAFT? |

**BFLA** chủ yếu xảy ra khi thiếu kiểm tra **hành động/chức năng**. **Broken Object Level Authorization (BOLA/IDOR)** xảy ra khi một hành động vốn hợp lệ nhưng người dùng có thể thao tác trên **đối tượng không thuộc quyền của họ**, ví dụ đổi id từ báo cáo của mình sang báo cáo người khác. Hai loại lỗ hổng có thể xuất hiện đồng thời: có quyền report:publish không có nghĩa được xuất bản mọi báo cáo.

Tương tự, Spring Security phân biệt **roles** (thường ánh xạ thành authority có tiền tố ROLE_) với các **authorities** như report:publish. Khi dùng hasAuthority('report:publish'), kiểm tra đúng chuỗi authority đó; framework không tự suy luận một vai trò bất kỳ cũng có quyền xuất bản.

## 3. Dấu hiệu và nguyên nhân phổ biến

### 3.1. Cấu hình chỉ yêu cầu đăng nhập

Đoạn sau chỉ là **ví dụ cấu hình sai về mặt phân quyền chức năng**:

~~~java
// Minh họa anti-pattern, không phải cấu hình khuyến nghị.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports/**").authenticated()
    .anyRequest().authenticated()
);
~~~

Quy tắc này bảo vệ tính xác thực nhưng **không phân biệt** GET xem báo cáo với POST xuất bản. Nếu controller không có bước phân quyền khác, một người dùng đã đăng nhập dù chỉ có quyền đọc vẫn có thể gọi chức năng xuất bản.

Cần tránh suy diễn rằng cấu hình như trên **luôn** có lỗ hổng: service/controller có thể có kiểm tra quyền riêng. Điểm sai là dựa vào authenticated() như thể nó đã chứng minh quyền cho mọi thao tác.

### 3.2. Chỉ ẩn nút trên giao diện

~~~javascript
// Minh họa phía frontend; điều này chỉ điều khiển giao diện.
if (!currentUser.permissions.includes("report:publish")) {
    publishButton.hidden = true;
}
~~~

Dữ liệu quyền ở trình duyệt có thể bị thay đổi, và một HTTP client không cần tương tác với nút. Frontend có thể giúp trải nghiệm người dùng tốt hơn, nhưng **máy chủ** phải kiểm tra quyền ở điểm thực hiện tác vụ.

### 3.3. Cùng một URL nhưng phương thức HTTP khác nhau

GET /api/reports/42 có thể là thao tác đọc, còn POST /api/reports/42/publish hoặc DELETE /api/reports/42 là thay đổi dữ liệu. Nếu rule chỉ dựa trên tiền tố đường dẫn hoặc bỏ sót HTTP method, thay đổi từ yêu cầu đọc sang yêu cầu ghi có thể vượt quy tắc dự kiến.

Chức năng nhạy cảm không phải lúc nào có tiền tố /admin. Các đường dẫn /api/reports/export, /api/users/bulk-update hoặc /api/orders/approve có thể nằm trong controller thông thường. Phải kiểm kê theo **hành động nghiệp vụ**, không chỉ nhìn tên URL.

### 3.4. Một đường gọi được kiểm tra, đường khác thì không

Một thao tác có thể được gọi từ controller HTTP, xử lý hàng đợi, lịch chạy, lệnh quản trị hoặc service khác. Kiểm tra quyền duy nhất ở một controller chưa đủ để bảo vệ mọi đường gọi qua cùng một service. Cần xác định điểm thực thi có trách nhiệm kiểm tra danh tính/quyền của từng loại người gọi, đặc biệt với tác vụ nền sử dụng danh tính dịch vụ.

### 3.5. Mở rộng chức năng mà không cập nhật chính sách

Thêm endpoint, API version, alias hoặc HTTP method mới nhưng vẫn dựa vào rule authenticated() chung. Đây là lý do quy tắc **deny by default** và kiểm thử hồi quy cho đường dẫn chưa khai báo mang lại giá trị lớn.

## 4. Xác định chính sách trước khi viết mã

Với một ứng dụng báo cáo nhỏ, quy định quyền minh họa như sau:

| Chủ thể | GET /api/reports/42 | POST /api/reports/42/publish | DELETE /api/reports/42 |
| --- | --- | --- | --- |
| Chưa đăng nhập | Từ chối | Từ chối | Từ chối |
| READER có report:read | Cho phép | Từ chối | Từ chối |
| PUBLISHER có report:publish | Từ chối nếu không có report:read | Cho phép | Từ chối |
| Người dùng đã đăng nhập nhưng không có hai quyền | Từ chối | Từ chối | Từ chối |

Bảng này cố tình tách **report:read** và **report:publish**: trong một sản phẩm thật, một vai trò có thể được cấp cả hai quyền hoặc kế thừa theo chính sách, nhưng không nên tự động giả định người có quyền xuất bản đương nhiên có quyền đọc.

Thực hành thiết kế quyền:

1. **Liệt kê chức năng** từ các nghiệp vụ: xem, tạo, sửa, duyệt, xuất, xóa, khôi phục, mời người, thay đổi quyền, thao tác hàng loạt.
2. **Định nghĩa quyền tối thiểu** theo hành động, ví dụ report:read và report:publish; chỉ cấp cho người hoặc vai trò cần dùng.
3. **Gán chính sách vào mọi điểm vào**: URI + HTTP method ở request layer; phương thức nghiệp vụ ở service layer khi cần bảo vệ khỏi đường gọi khác.
4. **Mặc định từ chối** những endpoint/method không khai báo quyền rõ ràng. Khi bổ sung chức năng mới, phải chủ động bổ sung policy.
5. **Kiểm tra thêm điều kiện đối tượng** sau khi có quyền chức năng: owner, tenant, phân loại dữ liệu, trạng thái quy trình hoặc chính sách pháp lý, nếu nghiệp vụ yêu cầu.
6. **Viết test âm tính theo từng quyền**: một tài khoản có thể đăng nhập hợp lệ nhưng vẫn phải bị từ chối ở chức năng không được cấp.

Chính sách phải được kiểm tra phía máy chủ bằng Authentication đáng tin cậy và dữ liệu quyền do hệ thống quản lý. Không dùng header tự khai báo như X-Role: ADMIN hoặc trường role trong JSON request làm nguồn quyền nếu không có bước kiểm chứng an toàn.

## 5. Cấu hình Spring Security: kiểm tra chức năng ở HTTP và service

### 5.1. Tầng HTTP: match đường dẫn, method và quyền cụ thể

Cấu hình an toàn hơn phải phân biệt read/publish, kiểm tra authority và từ chối các đường còn lại:

~~~java
// Trích đoạn minh họa; ví dụ hoàn chỉnh và test ở mục 6.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/*")
        .hasAuthority("report:read")
    .requestMatchers(HttpMethod.POST, "/api/reports/*/publish")
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

Spring Security đánh giá các request matcher theo thứ tự khai báo và áp dụng **matcher đầu tiên phù hợp**. Nếu đưa .requestMatchers("/api/**").authenticated() lên trước rule phân quyền cụ thể, quy tắc quá rộng có thể che mất quy tắc phía sau. Giữ rule cụ thể trước, quy tắc mặc định ở cuối; kiểm thử cả thứ tự và sự giao nhau của các pattern.

Trong ví dụ, dấu * đại diện cho một đoạn đường dẫn. Quy tắc mặc định denyAll() không đồng nghĩa ứng dụng không bao giờ có endpoint công khai; nếu cần health-check hoặc đăng nhập công khai, định nghĩa ngoại lệ có chủ ý và kiểm thử tương ứng. Với nhiều SecurityFilterChain, bảo đảm chain chứa chính sách thật sự được chọn cho endpoint cần bảo vệ.

### 5.2. Tầng service: bảo vệ hành động nghiệp vụ

~~~java
// Trong một Spring-managed service, có @EnableMethodSecurity.
@PreAuthorize("hasAuthority('report:publish')")
public String publish(long reportId) {
    return "published:" + reportId;
}
~~~

@EnableMethodSecurity kích hoạt các interceptor method security; @PreAuthorize kiểm tra quyền **trước khi gọi thân phương thức**. Điều này đặc biệt có giá trị khi service được sử dụng bởi nhiều controller hoặc đường gọi khác mà vẫn có ngữ cảnh Authentication phù hợp.

**Giới hạn của Spring AOP:** method security thường dựa trên proxy. Gọi new Service() hoặc gọi từ một phương thức của cùng đối tượng qua this. có thể bỏ qua interceptor. Không viết test chỉ gọi đối tượng do tự khởi tạo rồi kết luận policy đã hoạt động. Với các tác vụ nền không có người dùng đăng nhập, phải thiết kế rõ danh tính dịch vụ và quy trình cấp quyền, không tùy tiện tạo quyền quản trị mặc định.

### 5.3. HTTP 401 và 403 không phải hai loại quyền

- **401 Unauthorized:** thường là yêu cầu chưa có thông tin xác thực hợp lệ trong API sử dụng HTTP Basic/Bearer authentication.
- **403 Forbidden:** thường là đã xác thực nhưng không đủ quyền thực hiện chức năng.
- **302 Redirect:** có thể xuất hiện với ứng dụng dùng form login, khi yêu cầu chưa đăng nhập được chuyển đến trang đăng nhập.
- **404 Not Found:** đôi khi dùng có chủ đích để không tiết lộ sự tồn tại của tài nguyên, nhưng bản thân 404 không chứng minh policy đã kiểm tra đúng.

Không viết test chỉ dựa vào 401/403 mà bỏ qua cấu hình xác thực thực tế. Đặc biệt với POST/PUT/PATCH/DELETE, **CSRF** là kiểm tra độc lập: thiếu token CSRF có thể trả 403 ngay cả khi quyền chức năng đúng, che lấp lỗi kiểm thử phân quyền. Khi kiểm thử thao tác POST dùng cookie/session, hãy cung cấp CSRF token hợp lệ nếu ứng dụng bật CSRF, rồi kiểm tra quyền sau đó.

## 6. Ví dụ Spring Boot 3.x / Java 17+ có thể chạy bằng JUnit 5

Ví dụ sau chứa controller, service, cấu hình bảo mật và kiểm thử ngay trong **một tệp test**. Có thể đưa vào dự án Spring Boot 3.x có Gradle và các dependency tương thích. Không có dữ liệu thật hay thao tác ghi database; mã giữ kết quả xác định để tập trung vào chính sách.

### 6.1. Dependency cần có

~~~groovy
// Bên trong dependencies của một dự án Spring Boot 3.x đã thiết lập plugins.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không cần tạo cơ sở dữ liệu hoặc tài khoản thật. @WithMockUser do Spring Security Test cung cấp Authentication giả có authorities do test chỉ định. HTTP Basic được bật riêng trong fixture để trường hợp chưa xác thực trả 401 có thể kiểm tra được.

### 6.2. Tệp kiểm thử đầy đủ

Tạo **src/test/java/demo/authorization/FunctionAuthorizationTest.java**:

~~~java
package demo.authorization;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(classes = FunctionAuthorizationTest.App.class)
@AutoConfigureMockMvc
class FunctionAuthorizationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    static class App {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports/*")
                        .hasAuthority("report:read")
                    .requestMatchers(HttpMethod.POST,
                            "/api/reports/*/publish")
                        .hasAuthority("report:publish")
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults());

            // Giữ CSRF mặc định. Test POST dùng .with(csrf()).
            return http.build();
        }

        @Bean
        ReportService reportService() {
            return new ReportService();
        }

        @Bean
        ReportController reportController(ReportService service) {
            return new ReportController(service);
        }
    }

    // Bean service được Spring tạo/proxy để kiểm tra @PreAuthorize.
    static class ReportService {

        @PreAuthorize("hasAuthority('report:read')")
        public String read(long id) {
            return "report:" + id;
        }

        @PreAuthorize("hasAuthority('report:publish')")
        public String publish(long id) {
            return "published:" + id;
        }
    }

    @RestController
    @RequestMapping("/api/reports")
    static class ReportController {
        private final ReportService service;

        ReportController(ReportService service) {
            this.service = service;
        }

        @GetMapping("/{id}")
        String read(@PathVariable("id") long id) {
            return service.read(id);
        }

        @PostMapping("/{id}/publish")
        String publish(@PathVariable("id") long id) {
            return service.publish(id);
        }
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService service;

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void loggedInReaderCannotPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherCanPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("published:42"));
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherWithoutReadPermissionCannotRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void unexpectedHttpMethodIsDenied() throws Exception {
        mvc.perform(delete("/api/reports/42").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void authenticatedUserWithoutPermissionCannotPublish()
            throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void directServiceCallCannotBypassMethodSecurity() {
        assertThrows(AccessDeniedException.class,
                () -> service.publish(42L));
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void serviceAllowsAuthorizedPublisher() {
        assertEquals("published:42", service.publish(42L));
    }
}
~~~

**Chạy trong dự án Gradle Spring Boot 3.x đã cấu hình Java 17+ và JUnit 5:**

~~~bash
./gradlew test --tests "demo.authorization.FunctionAuthorizationTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "demo.authorization.FunctionAuthorizationTest"
~~~

**Kết quả dự kiến:** **10 bài test thành công**. Đây là dự kiến từ logic fixture, không phải log chạy Gradle đã được ghi lại. Kết quả HTTP do MockMvc kiểm tra: 200 cho hai lời gọi endpoint đúng quyền, 401 cho hai lời gọi chưa xác thực, 403 cho các yêu cầu thiếu quyền hoặc HTTP method chưa được phép; hai test cuối gọi trực tiếp service và kiểm tra @PreAuthorize. Không có stdout cố định vì các test không in ra console.

**Lưu ý khi tái sử dụng:** Đây là một fixture độc lập trong mã test, sử dụng @SpringBootConfiguration cùng @EnableAutoConfiguration để tạo application context nhỏ và @Bean để đăng ký controller/service tường minh. Ứng dụng production có thể dùng @SpringBootApplication, @RestController, @Service và cấu hình SecurityFilterChain trong các tệp riêng; vẫn phải đăng ký các bean vào Spring container. Spring Boot 4 / Spring Security 7 có thể có khác biệt về starter, phiên bản Java tối thiểu hoặc cấu hình test; cần đối chiếu tài liệu đúng phiên bản trước khi sao chép nguyên tệp.

## 7. Giải thích kiểm thử: vì sao đăng nhập thành công chưa đủ?

### 7.1. Ca quan trọng nhất: tài khoản hợp lệ nhưng thiếu quyền

Test **loggedInReaderCannotPublish** cung cấp Authentication có authority report:read. Người dùng này **đã đăng nhập** và có quyền đọc hợp lệ. MockMvc gửi POST /api/reports/42/publish với CSRF token hợp lệ, nhưng rule POST yêu cầu report:publish nên nhận **403**. Test minh chứng trực tiếp việc xác thực thành công không tự cấp quyền chức năng.

Nếu thay rule POST bằng authenticated() rồi bỏ @PreAuthorize ở service, test từ chối này sẽ không còn bảo vệ được thao tác; đó là ví dụ rõ ràng của sai sót cần phát hiện. Nếu chỉ viết test anonymousCannotPublish, ứng dụng vẫn có thể mắc lỗi cho **mọi tài khoản đã đăng nhập** xuất bản, nhưng bài test anonymous vẫn xanh.

### 7.2. Kiểm thử người dùng đúng quyền

Test **publisherCanPublish** dùng authority report:publish, gửi POST kèm CSRF và kỳ vọng 200 với nội dung published:42. Quy tắc HTTP và @PreAuthorize ở service đều cho phép, nên controller gọi thành công.

Kiểm thử quyền chỉ từ chối mà không có trường hợp cho phép có thể dẫn đến hệ thống khóa toàn bộ chức năng. Cần **cả positive và negative test** để kiểm chứng chính sách đúng.

### 7.3. Kiểm thử quyền khác không được suy ra

Test **publisherWithoutReadPermissionCannotRead** minh họa một tài khoản chỉ có report:publish không tự có report:read. Việc một role ở production có cả hai authority phải đến từ cấu hình cấp quyền/role hierarchy rõ ràng, không phải giả định ngầm.

### 7.4. Kiểm thử method HTTP ngoài danh sách

Test **unexpectedHttpMethodIsDenied** gửi DELETE cùng đường dẫn cho một người đã đăng nhập. Do không có allow rule cho DELETE, **anyRequest().denyAll()** ngăn yêu cầu trước khi xử lý nghiệp vụ. Đây là kiểm tra quan trọng khi thêm endpoint hoặc vô tình tạo mapping mới.

### 7.5. Kiểm thử service để tránh bỏ sót đường gọi khác

Test **directServiceCallCannotBypassMethodSecurity** lấy ReportService từ Spring context. Nó gọi publish trực tiếp qua bean nhưng vẫn nhận AccessDeniedException khi chỉ có report:read. Kiểm thử xác nhận lớp bảo vệ service hoạt động độc lập với việc một yêu cầu HTTP có bị chặn hay không.

Nếu tự tạo **new ReportService()**, interceptor Spring AOP không có cơ hội áp dụng và thân phương thức có thể được gọi dù thiếu quyền. Vì vậy test method security phải gọi bean do Spring quản lý (hoặc kiểm tra logic quyết định quyền riêng ở unit test), không suy ra behavior bảo mật từ một đối tượng khởi tạo tay.

## 8. Bản đồ kiểm thử an toàn theo điểm vào

| Tình huống | Test mong đợi | Lỗi phát hiện |
| --- | --- | --- |
| Chưa đăng nhập gọi chức năng nhạy cảm | Chặn theo cơ chế xác thực | Thiếu authentication |
| Đã đăng nhập, chỉ có quyền đọc, gọi thao tác ghi | 403 / từ chối | **BFLA** điển hình |
| Người có quyền ghi gọi thao tác ghi | Thành công | Chứng minh chức năng vẫn dùng được |
| Cùng endpoint với HTTP method khác | Từ chối nếu chưa cấp phép | Quy tắc quá rộng / thiếu method |
| API version/alias mới của thao tác nhạy cảm | Cùng policy hoặc mặc định từ chối | Đường gọi bỏ sót |
| Gọi service qua bean từ đường đi khác | Cùng quyết định quyền | Chỉ bảo vệ controller |
| Người được gọi chức năng nhưng đổi id sang đối tượng khác | Từ chối nếu không sở hữu/được cấp quyền | **BOLA**, kiểm tra bổ sung |
| Thao tác hàng loạt chứa cả mục hợp lệ và không hợp lệ | Chặn hoặc xử lý từng mục đúng chính sách | Thiếu quyền trên phần tử hàng loạt |
| Quyền bị thu hồi trong phiên còn hiệu lực | Từ chối theo chính sách hiệu lực mới | Quyền stale trong cache/token |
| Tài khoản bị vô hiệu hóa hoặc tenant không phù hợp | Từ chối tại điểm được quy định | Bỏ sót điều kiện ngữ cảnh |

Các test đầu bài là **kiểm thử chức năng phân quyền**. Test đối tượng, đa tenant, quyền thu hồi và bulk là các lớp bổ sung cần có khi nghiệp vụ thực sự hỗ trợ chúng. Không nên gộp tất cả logic vào một biểu thức SpEL dài khó kiểm toán; có thể đưa chính sách phức tạp sang một bean kiểm tra quyền đã được kiểm thử độc lập.

## 9. Cách triển khai cho hệ thống thật

### 9.1. Xác định nguồn sự thật về quyền

Có thể quản lý permissions tại IAM, cơ sở dữ liệu quan hệ người dùng–vai trò–quyền hoặc hệ thống chính sách tập trung. Dù chọn cách nào, mỗi yêu cầu phải dùng danh tính đáng tin cậy và một quyết định quyền có thể giải thích, kiểm toán.

**Vai trò (RBAC)** phù hợp cho quyền chức năng phổ biến như ADMIN, EDITOR, APPROVER. **Authority/permission** biểu diễn hành động cụ thể như report:publish. **Kiểm soát theo thuộc tính (ABAC)** hoặc chính sách theo tài nguyên phù hợp cho tenant, chủ sở hữu, nhóm dự án, trạng thái hồ sơ. Có thể kết hợp nhưng phải ghi rõ ý nghĩa của quyền, không để mỗi controller tự hiểu một kiểu.

### 9.2. Phân quyền gần nơi tác vụ thay đổi dữ liệu

Đối với lệnh có tác động lớn, đặt một kiểm tra quyền ở biên HTTP và một kiểm tra ở điểm thực thi nghiệp vụ khi service có thể được tái sử dụng. Quy tắc phải áp dụng trước khi có hiệu ứng phụ (ghi DB, gửi thông báo, phát sự kiện, gọi dịch vụ bên ngoài). Nếu chính sách phụ thuộc trạng thái dữ liệu có thể thay đổi đồng thời, cần quyết định trong cùng giao dịch hoặc bằng thao tác cập nhật có điều kiện để tránh kiểm tra một trạng thái cũ rồi ghi vào trạng thái mới.

Ví dụ logic nghiệp vụ **mang tính minh họa**:

~~~java
// Ý tưởng thiết kế, không phải chương trình Java độc lập.
@PreAuthorize("hasAuthority('report:publish')")
public void publish(long reportId) {
    Report report = repository.findById(reportId).orElseThrow();
    policy.requireCanPublish(
        currentPrincipal(), report.getTenantId(), report.getStatus());
    repository.publishIfStillDraft(reportId, report.getVersion());
}
~~~

Đoạn này nhấn mạnh hai lớp điều kiện: **được dùng chức năng publish** và **được publish báo cáo cụ thể ở trạng thái hợp lệ**. Các hàm repository, policy và currentPrincipal là thành phần giả định, cần triển khai và kiểm thử theo dự án thực tế.

### 9.3. Không dùng quyền của hệ thống làm quyền của người gọi

Tác vụ nền hoặc service-to-service không có phiên người dùng tương tác. Chúng cần service identity và quyền tối thiểu riêng; nếu thực thi thay mặt người dùng, phải xác định ngữ cảnh ủy quyền và phạm vi được phép. Không tự động chạy lệnh nhạy cảm bằng quyền quản trị chỉ vì tác vụ không bắt nguồn từ web controller.

### 9.4. Thay đổi quyền phải có hiệu lực theo thiết kế

Nếu JWT hoặc session giữ authorities trong thời gian dài, việc thu hồi quyền không nhất thiết phản ánh ngay ở mọi yêu cầu. Thiết kế TTL, làm mới token, tra cứu quyền động, phiên bản quyền hoặc thu hồi phiên theo độ nhạy của chức năng. Thêm test cho tài khoản vừa bị thu hồi quyền xuất bản; chỉ lưu quyền trong token rồi mặc định tin vĩnh viễn là không đủ.

### 9.5. Ghi nhật ký để điều tra, không rò rỉ dữ liệu

Ghi audit theo **user/service identity, action, resource id an toàn, quyết định allow/deny, thời điểm và correlation id**. Tránh log mật khẩu, bearer token hoặc dữ liệu nhạy cảm. Theo dõi các lần từ chối lặp lại ở chức năng quản trị hoặc hành động nhạy cảm; việc phát hiện không thay thế kiểm tra quyền trên máy chủ.

## 10. Những nhầm lẫn làm bộ kiểm thử báo xanh sai

| Cách làm | Vì sao chưa đủ | Thay bằng |
| --- | --- | --- |
| Chỉ có test truy cập khi chưa đăng nhập | Không phát hiện tài khoản hợp lệ vượt quyền | Thêm test logged-in-but-forbidden |
| Chỉ dựa vào trạng thái nút frontend | Không bảo vệ endpoint | Kiểm tra authority ở backend |
| Chỉ thêm anyRequest().authenticated() | Mọi người đăng nhập có thể qua cùng điều kiện | Dùng hasAuthority/hasRole theo thao tác |
| Match /** trước các rule chi tiết | Rule đầu tiên có thể chặn mất rule sau | Đặt matcher cụ thể trước rule mặc định |
| Chỉ test GET, không test POST/DELETE | Bỏ sót thao tác thay đổi dữ liệu | Ma trận route × method × actor |
| Test POST thiếu CSRF token khi CSRF bật | 403 có thể do CSRF, không chứng minh authorization | Dùng .with(csrf()) trong MockMvc |
| Test gọi new Service() | Bỏ qua proxy, @PreAuthorize không chạy | Inject Spring bean và test trực tiếp |
| Quên @EnableMethodSecurity | Chú thích có thể không được áp dụng | Bật method security, thêm test deny |
| Kiểm tra quyền chức năng nhưng không kiểm tra owner/tenant | Có thể vẫn có BOLA/IDOR | Kiểm tra quyền ở đối tượng |
| Dùng @WithMockUser như bằng chứng quyền production | Test tự cấp authority giả, không xác minh mapping IAM | Test riêng cách ánh xạ role/claim → authority |
| Dùng mọi lỗi là HTTP 403 | Khó phân biệt chưa đăng nhập và thiếu quyền | Test đúng theo authentication entry point |
| Tin rằng chỉ đổi URL mới là vượt quyền | HTTP method, alias và đường gọi nội bộ cũng quan trọng | Kiểm kê tất cả điểm vào và tác vụ |

**Cần nhớ:** CSRF, CORS, xác thực và phân quyền là các cơ chế khác nhau. CORS không ngăn HTTP client ngoài trình duyệt gửi yêu cầu; CSRF token hợp lệ không cấp quyền publish; đăng nhập thành công cũng không cấp quyền publish. Bộ lọc bảo mật cần xử lý từng mục tiêu rõ ràng.

## 11. Quy trình rà soát một chức năng mới hoặc chức năng cũ

Có thể dùng chuỗi kiểm tra sau trong code review và trước khi phát hành:

1. **Gọi tên hành động nghiệp vụ.** Ví dụ “xuất bản báo cáo” thay vì chỉ nhìn thấy POST.
2. **Xác định chủ thể được phép.** Quyền tối thiểu là gì, thuộc vai trò nào, có điều kiện trạng thái/tenant không?
3. **Tìm mọi điểm vào hợp pháp.** Endpoint hiện hành, alias, API version, controller nội bộ, event handler và lệnh tác vụ.
4. **Kiểm tra cơ chế enforcement.** Rule đúng method/path, đúng thứ tự, service có bảo vệ khi cần, mặc định denyAll cho đường chưa khai báo.
5. **Kiểm thử cặp allow/deny.** Người có quyền thực hiện thành công; người **đã đăng nhập nhưng thiếu quyền** bị chặn trước tác động nghiệp vụ.
6. **Kiểm thử ranh giới.** URL không dự kiến, method không dự kiến, quyền vừa thu hồi, resource khác tenant và bulk.
7. **Kiểm tra vận hành.** Nhật ký từ chối, khả năng truy vết và cách thay đổi/thu hồi quyền khi cần.
8. **Gắn test hồi quy với chức năng.** Khi sửa controller hay thêm route, thay đổi kiểm thử và bảng quyền tương ứng.

Không chỉ kiểm tra mã 403; với các chức năng có hiệu ứng phụ, xác nhận **trạng thái dữ liệu không đổi** khi yêu cầu bị từ chối. Nên đo kết quả thực tế như số bản ghi, trạng thái hồ sơ hoặc số sự kiện phát ra trong fixture xác định. Một API trả lỗi sau khi đã ghi dữ liệu vẫn chưa đạt yêu cầu bảo mật.

## 12. Bài thực hành

**Tình huống A — endpoint quản trị lẫn trong API thường.** Ứng dụng có POST /api/users/{id}/disable, nhưng SecurityFilterChain chỉ yêu cầu authenticated(). Hãy xác định quyền **user:disable**, bổ sung rule chính xác và test một tài khoản USER đã đăng nhập phải bị 403, còn tài khoản được cấp quyền phải thành công. Đừng đánh giá quyền chỉ bằng việc URL có chữ admin.

**Tình huống B — chức năng xuất dữ liệu.** GET /api/reports/export có thể thực hiện tác vụ nhạy cảm dù dùng HTTP GET. Hãy tạo quyền report:export riêng, yêu cầu kiểm tra quyền trên máy chủ, và test rằng report:read không tự có quyền export. Phân loại mức độ nhạy cảm theo **hành động**, không chỉ theo HTTP method.

**Tình huống C — quyền chức năng và dữ liệu.** Người dùng có report:publish và chỉ được publish báo cáo của tenant A. Hãy thiết kế test để họ publish tài nguyên thuộc tenant A thành công, nhưng bị từ chối với báo cáo của tenant B. Đây là phần kiểm soát đối tượng bên cạnh BFLA.

**Tình huống D — đường gọi service.** Thêm một controller thứ hai cũng gọi ReportService.publish. Chứng minh rằng test gọi trực tiếp bean service vẫn từ chối nếu thiếu quyền, rồi kiểm tra endpoint mới không vô tình đi vòng qua policy.

**Tình huống E — hồi quy.** Cố tình thay rule POST bằng authenticated() **chỉ trong môi trường học tập cô lập**, giữ @PreAuthorize ở service và quan sát test nào còn chặn. Sau đó cũng gỡ chú thích @PreAuthorize trong fixture học tập và thấy test từ chối phải thất bại. Khôi phục cấu hình đúng. Bài tập này giúp phân biệt giá trị của mỗi lớp kiểm tra và tránh tưởng một test xanh đã chứng minh mọi đường gọi an toàn.

**Câu hỏi tự đánh giá:** Một tài khoản có thể đăng nhập thành công nhưng vẫn bị từ chối bởi rule nào? Nếu hệ thống thêm một HTTP method mới, rule mặc định xử lý ra sao? Nếu controller có quyền đúng nhưng service bị gọi qua đường khác, quyền còn được kiểm tra không? Bạn đã kiểm tra cả quyền trên chức năng và quyền trên đối tượng chưa?

## 13. Tài liệu tham khảo chính thức

- OWASP API Security Top 10 — API5:2023 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Spring MVC Test Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Method Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
