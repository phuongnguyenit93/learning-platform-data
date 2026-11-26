# Gọi Spring bean có proxy để đi qua lớp kiểm tra quyền

## 1. Mục tiêu bài học

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Khi dùng @PreAuthorize hoặc các annotation bảo mật tương tự, chỉ nhìn thấy annotation trong source code chưa đủ để kết luận phương thức đã được bảo vệ. Điều quyết định là **lời gọi có đi qua Spring bean đã được áp dụng method-security interceptor hay không**.

Sau bài này, bạn có thể:

- Giải thích vai trò của Spring AOP proxy, target và method-security interceptor.
- Phân biệt lời gọi từ bean khác qua dependency injection với lời gọi trực tiếp trên đối tượng tạo bằng new hoặc qua this.
- Viết service và controller có ranh giới bảo mật rõ ràng, xử lý self-invocation, private/final method và các kiểu proxy thường gặp.
- Dùng @WithMockUser kiểm tra bean thật, kết hợp MockMvc hoặc WebTestClient để xác minh đường đi từ HTTP đến service và các ca được phép/bị từ chối.
- Đọc kết quả kiểm thử đúng tầng: exception của Java method khác với HTTP status 401/403; mock JWT/OAuth2/OIDC không kiểm tra chữ ký token thật.

**Bối cảnh phiên bản:** Các ví dụ Servlet bên dưới sử dụng Spring Security 6.x và import test quen thuộc ở Spring Boot 3.x. Spring Security 7.x cũng sử dụng cơ chế method security hiện đại, nhưng một số package test auto-configuration của Boot 4.x khác Boot 3.x. Khi dự án dùng phiên bản khác, cần đối chiếu dependency đã resolve và import phù hợp. Với Spring Security 5.x đời cũ, có thể thấy @EnableGlobalMethodSecurity(prePostEnabled = true); từ Spring Security 5.6 đã có @EnableMethodSecurity và cách cấu hình hiện đại thường dùng annotation này.

## 2. Proxy đứng ở đâu trên đường gọi phương thức?

Giả sử API GET /reports/42 gọi service đọc báo cáo, và phương thức service yêu cầu authority report:read. Trong proxy mode thông dụng, Spring Security tạo hoặc tham gia vào hạ tầng AOP của Spring để chặn các lời gọi tới phương thức đã khai báo chính sách.

~~~mermaid
flowchart TD
    A["Client hoặc bài test"] --> B["Controller / bean gọi"]
    B --> C["Bean đã inject: AOP proxy"]
    C --> D{"Method-security interceptor: đủ quyền?"}
    D -- "Có" --> E["Target: chạy business method"]
    D -- "Không" --> F["AccessDeniedException"]
    E --> G["Trả kết quả"]
    H["new Service() / this.securedMethod()"] -. "Bỏ qua proxy" .-> E
~~~

Ba khái niệm quan trọng:

| Thành phần | Trách nhiệm | Dấu hiệu trong bài test |
|---|---|---|
| Target | Đối tượng thực thi logic nghiệp vụ. | Gọi trực tiếp target có thể bỏ qua advice. |
| Proxy | Điểm vào do Spring cung cấp; đưa lời gọi qua các advisor/interceptor. | Bean lấy từ ApplicationContext được gọi thông qua dependency đã inject. |
| Method-security interceptor | Đánh giá @PreAuthorize, @PostAuthorize hoặc chính sách đã bật dựa trên Authentication và dữ liệu lời gọi. | Người thiếu quyền phải bị từ chối trước khi thân phương thức chạy đối với @PreAuthorize. |

Spring AOP proxy thường có hai dạng:

- **JDK dynamic proxy:** đại diện cho các interface của target. Inject interface là cách ổn định khi sử dụng dạng này; cố inject kiểu implementation có thể không tương thích.
- **Class-based proxy (CGLIB):** tạo subclass của target. Vì vậy final class hoặc final method không thể được override để chèn advice theo cách thông thường; private method cũng không phải điểm chặn proxy.

Tùy cấu hình Spring Boot, Spring AOP và chính sách auto-proxy của ứng dụng, runtime có thể chọn một trong hai dạng. @EnableMethodSecurity có tùy chọn proxyTargetClass để chủ động dùng proxy theo lớp khi cần. Dù vậy, **thay đổi loại proxy không giải quyết self-invocation** trong proxy mode. Bài này tập trung vào proxy mode, không bàn sâu về weaving AspectJ.

Một số phương thức có thể được chặn trước khi thực thi, ví dụ @PreAuthorize; @PostAuthorize kiểm tra sau khi phương thức trả kết quả. Không dựa hoàn toàn vào kiểm tra sau để bảo vệ thao tác có tác dụng phụ như xóa dữ liệu hoặc chuyển tiền: thân phương thức có thể đã thực hiện tác vụ trước khi bị từ chối.

## 3. Bật đúng cấu hình và chuẩn bị Spring test context

Trong dự án Spring Boot Servlet, cần web, security và dependency thử nghiệm thích hợp. Ví dụ Maven với BOM của Spring Boot quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Không tự đặt version của spring-security-test khác với nhóm Spring Security do BOM quản lý. Với dự án Gradle, dependency tương ứng là implementation cho starter web/security và testImplementation cho spring-boot-starter-test/spring-security-test.

Bật method security trong một @Configuration được nạp bởi Spring context:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Trong Spring Security hiện đại, @EnableMethodSecurity mặc định bật @PreAuthorize và @PostAuthorize. Nếu cần @Secured hoặc Jakarta @RolesAllowed, phải chủ động bật cờ tương ứng:

~~~java
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
~~~

Chỉ thêm starter security hoặc @PreAuthorize lên một class tự tạo bằng new không đủ để kích hoạt chặn quyền. Để annotation có hiệu lực, cấu hình method security và bean nghiệp vụ phải nằm trong ApplicationContext, đồng thời lời gọi phải đi qua đường chặn thích hợp.

## 4. Tạo đường gọi an toàn: controller → interface bean → service

Ta xây một ví dụ nhỏ trong đó controller không trực tiếp khởi tạo service. Định nghĩa interface giúp code làm việc cả khi proxy là JDK dynamic proxy:

~~~java
// ReportOperations.java
public interface ReportOperations {
    String readReport(String id);
    String deleteReport(String id);
}
~~~

Implementation là Spring bean có các annotation phân quyền:

~~~java
// ReportService.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService implements ReportOperations {

    @Override
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport(String id) {
        return "REPORT-" + id;
    }

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    public String deleteReport(String id) {
        // Dự án thật sẽ xóa bằng repository.
        return "DELETED-" + id;
    }
}
~~~

Controller inject interface qua constructor:

~~~java
// ReportController.java
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {

    private final ReportOperations reports;

    public ReportController(ReportOperations reports) {
        this.reports = reports;
    }

    @GetMapping("/{id}")
    public String read(@PathVariable String id) {
        return reports.readReport(id);
    }

    @DeleteMapping("/{id}")
    public String delete(@PathVariable String id) {
        return reports.deleteReport(id);
    }
}
~~~

Dòng reports.readReport(id) gọi trên **tham chiếu do Spring cung cấp**. Khi bean đã được áp dụng method security, proxy có thể kiểm tra chính sách trước khi gọi ReportService thực sự.

Trong ví dụ này:

- hasAuthority('report:read') đòi đúng chuỗi authority report:read.
- hasRole('ADMIN') mặc định đòi authority ROLE_ADMIN.
- @WithMockUser(authorities = "report:read") cung cấp quyền đọc; @WithMockUser(roles = "ADMIN") cung cấp ROLE_ADMIN.
- Nếu ứng dụng là JWT resource server, scope như reports.read thường được chuyển thành SCOPE_reports.read theo converter mặc định. Biểu thức phân quyền cần khớp converter thật, không mặc nhiên coi role, scope và custom authority tương đương.

Đối với code thực tế, nên đặt ranh giới kiểm soát quyền ở service công khai theo nghiệp vụ. Chỉ bảo vệ URL có thể thiếu kiểm soát khi service được gọi từ scheduler, message consumer hoặc một bean khác ngoài controller.

## 5. Nhận diện bean có proxy trong test

AopUtils là công cụ chẩn đoán hạ tầng proxy. Test sau đọc bean từ ApplicationContext thay vì tạo đối tượng mới:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ReportProxyInspectionTest {

    @Autowired
    ReportOperations reports;

    @Test
    void reportBeanIsProxy() {
        assertTrue(AopUtils.isAopProxy(reports));
    }
}
~~~

Có thể dùng AopUtils.isJdkDynamicProxy(reports) hoặc AopUtils.isCglibProxy(reports) để quan sát kiểu proxy đang dùng. Nếu không thấy proxy, kiểm tra cấu hình @EnableMethodSecurity, component scan, bean thực tế được inject, phương thức có annotation và tính tương thích của proxy.

Tuy nhiên, một proxy có thể xuất hiện vì @Transactional hoặc advisor khác, nên **assert proxy tồn tại chưa chứng minh việc phân quyền hoạt động**. Hãy kết hợp kiểm thử hành vi đối với người thiếu quyền. Nếu chỉ có test user được phép, test vẫn có thể xanh khi vô tình bỏ @EnableMethodSecurity.

## 6. Chứng minh bằng @WithMockUser trên bean thật

Dùng @SpringBootTest để nạp application context cùng bean thật. Spring Security Test thiết lập Authentication trong SecurityContext của test trước khi gọi service.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class ReportMethodSecurityTest {

    @Autowired
    ReportOperations reports;

    @Test
    @WithMockUser(authorities = "report:read")
    void correctAuthorityCanRead() {
        assertEquals("REPORT-42", reports.readReport("42"));
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void wrongAuthorityCannotRead() {
        assertThrows(AccessDeniedException.class,
            () -> reports.readReport("42"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDelete() {
        assertEquals("DELETED-42", reports.deleteReport("42"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotDelete() {
        assertThrows(AccessDeniedException.class,
            () -> reports.deleteReport("42"));
    }
}
~~~

Với @PreAuthorize, quyền bị từ chối trước khi thân phương thức thực thi. Trong dự án thật, nên kiểm tra thêm rằng thao tác nhạy cảm không ghi dữ liệu hoặc không gọi dịch vụ ngoại vi khi bị từ chối.

**@WithMockUser là authentication giả lập.** Nó giúp kiểm chứng authorization với tập quyền đã cho, không xác thực password, chữ ký JWT, issuer/audience hay việc người dùng tồn tại trong database. Spring Security Test còn có jwt(), oauth2Login(), oidcLogin() trên Servlet và mockJwt(), mockOAuth2Login(), mockOidcLogin() trên WebFlux; các helper này cũng phù hợp kiểm tra phân quyền của authentication giả lập. Nếu mục tiêu là kiểm chứng token thực, cần integration test cho cơ chế xác thực tương ứng.

Test gọi method trực tiếp thường kỳ vọng AccessDeniedException (hoặc exception authorization tương ứng), vì 401 và 403 là **mã phản hồi của HTTP**. Khi chuyển qua controller và filter chain, Spring Security HTTP exception handling mới quyết định status tùy cấu hình entry point và authentication.

## 7. Bẫy self-invocation: annotation có mặt nhưng không chạy

Xét service có hai phương thức:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class UnsafeReportFacade {

    public String download(String id) {
        return readSecured(id); // Tương đương this.readSecured(id).
    }

    @PreAuthorize("hasAuthority('report:read')")
    public String readSecured(String id) {
        return "REPORT-" + id;
    }
}
~~~

Lời gọi từ bên ngoài vào download có thể đi qua proxy. Nhưng download chạy trên target rồi gọi tiếp this.readSecured(id), **không quay lại proxy** trong Spring AOP proxy mode. Vì thế interceptor trên readSecured không được chạy ở đường gọi này.

Một test nhằm tái hiện lỗi có thể cho thấy user chỉ có report:write vẫn lấy được kết quả qua download:

~~~java
// Chỉ dùng để minh họa lỗi thiết kế, không giữ làm hành vi mong muốn.
@Test
@WithMockUser(authorities = "report:write")
void selfInvocationDemonstratesBypass() {
    assertEquals("REPORT-42", unsafeReportFacade.download("42"));
}
~~~

Giả định unsafeReportFacade là bean được inject vào test @SpringBootTest. Test trên không chứng minh hệ thống an toàn; nó chỉ phơi bày việc điều kiện trên readSecured chưa hề được kiểm tra.

**Cách sửa khuyến nghị:** tách phương thức bảo mật vào bean riêng để lời gọi từ facade phải đi qua dependency do Spring inject:

~~~java
// SecuredReportReader.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SecuredReportReader {

    @PreAuthorize("hasAuthority('report:read')")
    public String read(String id) {
        return "REPORT-" + id;
    }
}
~~~

~~~java
// SafeReportFacade.java
import org.springframework.stereotype.Service;

@Service
public class SafeReportFacade {

    private final SecuredReportReader reader;

    public SafeReportFacade(SecuredReportReader reader) {
        this.reader = reader;
    }

    public String download(String id) {
        return reader.read(id);
    }
}
~~~

Test gọi theo đúng đường đi facade → secured bean:

~~~java
@Test
@WithMockUser(authorities = "report:write")
void unauthorizedCallerCannotDownload() {
    assertThrows(AccessDeniedException.class,
        () -> safeReportFacade.download("42"));
}

@Test
@WithMockUser(authorities = "report:read")
void authorizedCallerCanDownload() {
    assertEquals("REPORT-42", safeReportFacade.download("42"));
}
~~~

Hai đoạn test này cần inject SafeReportFacade vào @SpringBootTest và dùng các import JUnit 5/Spring Security Test ở mục trước.

Không nên coi tự inject proxy của chính class hoặc dùng AopContext.currentProxy() là lời giải mặc định: chúng khiến nghiệp vụ phụ thuộc cấu hình AOP và có thể phức tạp hóa việc quản lý bean. Tách bean theo trách nhiệm rõ ràng sẽ dễ đọc, dễ test hơn.

**Những trường hợp liên quan:** gọi private method không qua advice của proxy; final method không thể bị class-based proxy override; gọi trong constructor hoặc tự tạo new Service() cũng không tạo đường gọi được Spring quản lý. Transaction advice có thể chịu ảnh hưởng self-invocation giống method security nếu cùng dùng cơ chế proxy. Có ngoại lệ khi dùng AspectJ weaving, nhưng không nên suy diễn ngoại lệ đó cho proxy mode.

## 8. Kiểm tra HTTP end-to-end bằng MockMvc

Để chứng minh controller đã gọi bean qua proxy, test request từ HTTP filter chain đến method security. Ví dụ bên dưới dùng HTTP Basic và tạm cho mọi URL qua bước authorization của filter, để chính sách report:read tại phương thức quyết định được phép hay bị từ chối.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình permitAll() toàn cục ở đây chỉ nhằm **cô lập việc kiểm thử method security**; ứng dụng triển khai thật cần định nghĩa chính sách HTTP phù hợp. CSRF trên Servlet vẫn có thể chặn POST/PUT/DELETE. Với các request thay đổi trạng thái, thêm CSRF hợp lệ trong test nếu muốn bảo đảm request thực sự tới phương thức có @PreAuthorize.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readerGets200() throws Exception {
        mvc.perform(get("/reports/42").with(user("lan")
                .authorities(new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT-42"));
    }

    @Test
    void wrongPermissionGets403() throws Exception {
        mvc.perform(get("/reports/42").with(user("lan")
                .authorities(new SimpleGrantedAuthority("report:write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousGets401WithHttpBasic() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotDeleteWithValidCsrf() throws Exception {
        mvc.perform(delete("/reports/42")
                .with(csrf())
                .with(user("lan").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanDeleteWithValidCsrf() throws Exception {
        mvc.perform(delete("/reports/42")
                .with(csrf())
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("DELETED-42"));
    }
}
~~~

**Điều kiện của những kết quả này:** ứng dụng nạp @EnableMethodSecurity, bean thật ReportService, controller và DemoHttpSecurityConfig như mô tả, đồng thời cấu hình HTTP Basic được áp dụng. Thay bằng form login có thể khiến người chưa xác thực nhận redirect, thay bằng bearer token hoặc custom exception handling có thể cho status/response khác. Nếu dùng Spring Boot 4.x, cần điều chỉnh import @AutoConfigureMockMvc theo package test auto-configuration của phiên bản đó.

Khi tự xây dựng MockMvc bằng MockMvcBuilders.webAppContextSetup(context), hãy tích hợp Spring Security qua .apply(springSecurity()) để filter chain và các request post-processor hoạt động chính xác.

**Chú ý test slice:** Với @WebMvcTest, nếu ReportOperations được thay bằng mock thì bạn đang kiểm tra controller tương tác với mock, không xác minh annotation trên service thật. Dùng @SpringBootTest nạp service thật cho bài test method security; có thể mock repository bên dưới service khi muốn cô lập dữ liệu.

## 9. Cùng nguyên tắc với WebFlux và WebTestClient

Trong stack Reactive, hạ tầng method security sử dụng @EnableReactiveMethodSecurity; SecurityContext được truyền qua Reactor Context. Đối tượng được bảo vệ vẫn phải là bean có thể đi qua hạ tầng method security.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Bean service và controller WebFlux:

~~~java
// ReactiveReportReader.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReportReader {

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> read(String id) {
        return Mono.just("REPORT-" + id);
    }
}
~~~

~~~java
// ReactiveReportController.java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/reports")
public class ReactiveReportController {

    private final ReactiveReportReader reports;

    public ReactiveReportController(ReactiveReportReader reports) {
        this.reports = reports;
    }

    @GetMapping("/{id}")
    public Mono<String> read(@PathVariable String id) {
        return reports.read(id);
    }
}
~~~

WebTestClient gửi request và subscribe publisher, nên có thể chứng minh quyền. Đây là mẫu test tích hợp dựa trên một WebFlux application context đã có SecurityWebFilterChain phù hợp để cho request đến service:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class ReactiveReportSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void correctAuthorityIsAllowed() {
        client.mutateWith(mockUser("lan")
                .authorities(new SimpleGrantedAuthority("report:read")))
            .get().uri("/reports/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("REPORT-42");
    }

    @Test
    void wrongAuthorityIsForbidden() {
        client.mutateWith(mockUser("lan")
                .authorities(new SimpleGrantedAuthority("report:write")))
            .get().uri("/reports/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Với WebFlux, lời gọi trực tiếp service trả Mono chỉ tạo publisher; test phải subscribe (ví dụ StepVerifier) để thực sự quan sát hoàn thành hay lỗi. SecurityContext Reactive không nên được lấy bằng giả định ThreadLocal servlet tồn tại trên mọi thread. Nếu ứng dụng có cả Servlet và Reactive dependency, phải xác nhận stack nào thực sự đang được Spring Boot khởi tạo; không áp configuration và test helper giữa hai stack một cách tùy tiện.

## 10. Ma trận lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Điều cần xác minh |
|---|---|---|
| Annotation @PreAuthorize có mặt nhưng user thiếu quyền vẫn đọc được. | Chưa bật method security hoặc gọi không qua proxy. | Kiểm tra cấu hình và viết test denied trực tiếp trên bean thật. |
| Test new ReportService() chạy cả khi sai quyền. | Đối tượng không do Spring quản lý. | Inject ReportOperations từ context; không tạo mới khi test interceptor. |
| Gọi từ phương thức cùng bean không bị chặn. | Self-invocation dùng this bỏ qua proxy. | Tách bean và kiểm tra lại đường gọi facade → reader. |
| Test service có proxy nhưng quyền vẫn không bị chặn. | Proxy có thể đến từ AOP khác hoặc advisor bảo mật không áp đúng phương thức. | Assert AccessDeniedException, không dựa riêng AopUtils.isAopProxy. |
| Injection implementation thất bại sau khi bật security. | Runtime sử dụng JDK dynamic proxy cho interface. | Inject interface hoặc cấu hình loại proxy phù hợp. |
| Method private/final không được kiểm soát. | Giới hạn AOP proxy. | Chuyển policy lên public service method có thể được intercept. |
| Test @WebMvcTest cho HTTP 200, không chặn method. | Service đã bị thay bằng mock trong slice test. | Dùng bean service thật hoặc cấu hình test context phù hợp. |
| DELETE trả 403 ngay cả với role ADMIN. | CSRF filter có thể chặn trước method security. | Gửi csrf() hợp lệ rồi kiểm tra hai vai trò. |
| MockMvc trả 302 thay vì 401. | Entry point dùng form login hoặc handler khác HTTP Basic. | Đối chiếu SecurityFilterChain trước khi sửa assertion. |
| Test chỉ có case 200 vẫn xanh khi xóa @EnableMethodSecurity. | Thiếu negative test. | Thêm test sai authority kỳ vọng exception/403. |
| @WithMockUser(roles = "ADMIN") không qua hasAuthority('ADMIN'). | hasRole mặc định thêm ROLE_. | So quyền thực tế trong Authentication với biểu thức. |
| Tác vụ @Async mất SecurityContext. | Context ThreadLocal không tự chuyển qua worker thread trong Servlet. | Dùng cơ chế truyền context có kiểm soát (ví dụ DelegatingSecurityContextAsyncTaskExecutor), kiểm thử đường xử lý async. |
| WebFlux test không thấy security error. | Publisher chưa subscribe hoặc Reactor Context không đúng. | Sử dụng WebTestClient tích hợp springSecurity() hay StepVerifier với context phù hợp. |

Với chính sách sở hữu tài nguyên, ngoài role và authority cần kiểm tra **chính đối tượng đang truy cập**. Ví dụ:

~~~java
@PreAuthorize("hasAuthority('report:read') and @reportPolicy.canRead(authentication, #id)")
public String readReport(String id) {
    return "REPORT-" + id;
}
~~~

Ở đây reportPolicy là Spring bean chuyên kiểm tra quyền sở hữu, và phép phân quyền được đánh giá khi lời gọi đi qua proxy. Với SpEL dùng tên tham số #id, bảo đảm project giữ được tên tham số lúc biên dịch (thường bằng -parameters) hoặc dùng cơ chế đặt tên tham số Spring Security hỗ trợ. Test cần có ba ca: đúng quyền/đúng chủ sở hữu; đúng quyền/sai chủ sở hữu; sai quyền/đúng chủ sở hữu. Đừng để policy mẫu mặc định trả true cho mọi tài nguyên.

## 11. Bài thực hành và tiêu chí hoàn thành

1. Tạo interface ReportOperations, ReportService, ReportController và MethodSecurityConfig như ví dụ. Chạy test trực tiếp service với authority report:read và report:write.
2. Dùng AopUtils xem bean được inject có proxy không. Sau đó tạm bỏ @EnableMethodSecurity để thấy **test bị từ chối** thất bại, rồi khôi phục cấu hình.
3. Dựng UnsafeReportFacade có lời gọi this.readSecured, xác nhận trường hợp bypass; tách sang SecuredReportReader và SafeReportFacade để kiểm tra lỗi đã được khắc phục.
4. Chạy MockMvc với đủ ca GET được phép, GET bị từ chối, chưa xác thực và DELETE có CSRF, so sánh status với HTTP security config đang chạy.
5. Trên WebFlux, cấu hình @EnableReactiveMethodSecurity, gọi ReactiveReportReader từ controller và dùng WebTestClient mockUser để xác minh cả 200 và 403.
6. Khi ứng dụng dùng JWT/OAuth2/OIDC, thử helper authentication giả lập phù hợp, nhưng kiểm thử token thật ở integration test riêng.

**Tiêu chí hoàn thành:** lời gọi đến service bằng bean do Spring inject phải thực sự đi qua lớp kiểm tra quyền; ca đúng authority được phép, ca sai authority bị chặn trước nghiệp vụ. Bài test HTTP cần chứng minh controller dùng đúng bean được bảo vệ, trong khi test trực tiếp method phải đủ mạnh để phát hiện việc tắt method security hoặc lỡ đi vòng qua proxy.

