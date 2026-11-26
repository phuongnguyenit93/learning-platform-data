# Không mock chính phương thức đang cần kiểm tra phân quyền

## 1. Vì sao mock nhầm đối tượng làm test bảo mật mất ý nghĩa?

Trong module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive. Một test method security cần chứng minh rằng Spring thực sự đánh giá quyền trước khi cho phép phương thức nghiệp vụ chạy.

Lỗi phổ biến là mock chính service đang chứa annotation bảo mật. Ví dụ ReportService.read() có @PreAuthorize, nhưng test thay ReportService bằng Mockito mock rồi cấu hình when(read(...)).thenReturn(...). Khi đó test chủ yếu kiểm tra hành vi của mock hoặc cách controller gọi dependency. Nó không còn chứng minh rằng thân phương thức thật đã đi qua method-security interceptor và chính sách đã được thực thi.

Nguyên tắc quan trọng:

- **Giữ bean chứa phương thức được bảo vệ là bean thật do Spring quản lý.**
- **Mock dependency bên dưới** như repository, gateway hoặc client HTTP để kiểm soát dữ liệu và tránh phụ thuộc hạ tầng.
- Gọi service qua Spring proxy trong test; dùng @WithMockUser hoặc request post-processor để cung cấp Authentication.
- Có cả test được phép và test bị từ chối. Ca bị từ chối phải chứng minh phương thức nghiệp vụ không chạy, chẳng hạn repository không được gọi.

Sau bài này, bạn có thể:

- Phân biệt mock service được bảo vệ với mock repository mà service sử dụng.
- Giải thích vì sao @Mock, @InjectMocks, @MockBean hoặc @MockitoBean trên service có thể làm test bỏ qua logic bảo mật.
- Viết @SpringBootTest giữ service thật và thay dependency bằng @MockitoBean.
- Kiểm tra ca đủ authority, thiếu authority và anonymous bằng @WithMockUser/@WithAnonymousUser.
- Kiểm thử đường HTTP với MockMvc mà vẫn giữ controller và service thật.
- Áp dụng cùng nguyên tắc cho WebFlux, Mono và WebTestClient.
- Biết khi nào mock service là hợp lý cho controller slice test, và vì sao test đó không thay thế authorization integration test.

> **Phiên bản ví dụ:** Các ví dụ Servlet chính dùng Spring Boot 3.4+ / Spring Framework 6.2+ để minh họa @MockitoBean từ Spring Test. Với Spring Boot 3.3 trở xuống, dùng @MockBean của Spring Boot. Ví dụ Reactive cần WebFlux và Reactive Method Security được bật riêng. Hãy dùng API tương ứng với phiên bản dependency của dự án.

## 2. Ranh giới giữa đối tượng thật và dependency giả lập

Một service được bảo vệ thường có cấu trúc:

~~~mermaid
flowchart LR
    A["Test / Controller"] --> B["Spring proxy của ReportService"]
    B --> C["Method-security interceptor"]
    C --> D["ReportService thật"]
    D --> E["ReportRepository mock"]
    E --> D
    D --> B
    B --> A
~~~

Test cần giữ nguyên đường đi từ caller qua proxy và interceptor đến service thật. Repository mock chỉ cung cấp kết quả dữ liệu có thể dự đoán.

| Thành phần | Trong test method security | Lý do |
|---|---|---|
| ReportService có @PreAuthorize | Bean thật, được Spring inject | Đây là đối tượng cần kiểm tra interceptor và chính sách. |
| ReportRepository | Mockito mock | Kiểm soát dữ liệu, xác minh truy vấn có chạy hay bị chặn. |
| Controller | Bean thật trong HTTP integration test | Xác minh request thực sự gọi service được bảo vệ. |
| Authentication | @WithMockUser hoặc request post-processor | Tạo principal và authority xác định. |
| Database, remote API | Có thể thay bằng mock/fake phù hợp | Không cần hạ tầng thật để kiểm tra quyết định method security. |

Ví dụ service:

~~~java
import java.util.Optional;

public interface ReportRepository {
    Optional<Report> findById(String id);
}
~~~

~~~java
public record Report(String id, String title) {
}
~~~

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Report read(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "Report not found: " + id
            ));
    }
}
~~~

Cấu hình method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Khi test ReportService.read(), không mock ReportService. Thay vào đó, mock ReportRepository và gọi ReportService thật thông qua field được @Autowired.

## 3. Anti-pattern: mock chính service đang cần kiểm tra

Ví dụ không phù hợp cho mục tiêu kiểm tra method security:

~~~java
@SpringBootTest
class ReportControllerTest {

    @MockitoBean
    ReportService reportService;

    @Autowired
    MockMvc mvc;

    @Test
    void controllerReturnsMockedReport() throws Exception {
        when(reportService.read("r-1"))
            .thenReturn(new Report("r-1", "Quarterly report"));

        mvc.perform(get("/reports/r-1")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("report:write"))))
            .andExpect(status().isOk());
    }
}
~~~

Test này có thể hữu ích nếu mục tiêu chỉ là kiểm tra controller ánh xạ response hoặc gọi đúng service. Nhưng nó không chứng minh @PreAuthorize("hasAuthority('report:read')") trên implementation thật đã được áp dụng. Mockito mock có thể trả dữ liệu đã cấu hình mà không thực thi thân ReportService.read().

Tùy cách bean được thay thế và proxy được tạo, chi tiết runtime có thể khác nhau; điểm cần nhớ là **không thể dùng mock service làm bằng chứng rằng policy trên implementation thật đã chạy**. Một test bảo mật phải giữ service thật trong application context và xác minh cả kết quả cho phép lẫn từ chối.

Các dạng sau cũng có cùng vấn đề nếu dùng để thay chính đối tượng đang kiểm tra:

~~~java
@Mock
ReportService reportService;

@InjectMocks
ReportController controller;
~~~

Hoặc:

~~~java
@MockBean
ReportService reportService;
~~~

@Mock tạo Mockito mock ngoài Spring context. @InjectMocks tạo đối tượng theo cơ chế Mockito, không tự thêm Spring method-security proxy. @MockBean/@MockitoBean thay bean trong context bằng mock. Cả ba đều không phù hợp để chứng minh interceptor của ReportService thật hoạt động.

## 4. Cách đúng: mock repository, giữ service thật

### 4.1. Dùng @MockitoBean với Spring Framework 6.2+

@MockitoBean thay thế dependency trong Spring context bằng Mockito mock. Đặt annotation trên repository, không đặt lên service cần kiểm tra:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class ReportServiceMethodSecurityTest {

    @Autowired
    ReportService reports;

    @MockitoBean
    ReportRepository repository;

    @Test
    @WithMockUser(
        username = "lan",
        authorities = "report:read"
    )
    void callerWithReadAuthorityCanRead() {
        when(repository.findById("r-1"))
            .thenReturn(Optional.of(
                new Report("r-1", "Quarterly report")
            ));

        Report result = reports.read("r-1");

        assertEquals("r-1", result.id());
        assertEquals("Quarterly report", result.title());
        verify(repository).findById("r-1");
    }

    @Test
    @WithMockUser(
        username = "lan",
        authorities = "report:write"
    )
    void callerWithoutReadAuthorityIsDeniedBeforeRepositoryCall() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.read("r-1")
        );

        verifyNoInteractions(repository);
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerIsDeniedBeforeRepositoryCall() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.read("r-1")
        );

        verifyNoInteractions(repository);
    }
}
~~~

Điểm quan trọng trong test thứ hai và thứ ba là verifyNoInteractions(repository). Nó cho thấy quyết định từ chối xảy ra trước khi thân phương thức gọi repository. Nếu service bị thay bằng mock, test không còn chứng minh được thứ tự này.

Spring Security Test thiết lập Authentication cho test thông qua @WithMockUser hoặc @WithAnonymousUser. Spring method-security proxy bao quanh ReportService thật; Mockito chỉ thay ReportRepository. @SpringBootTest phải nạp cấu hình có @EnableMethodSecurity.

### 4.2. Dùng @MockBean trên phiên bản Spring Boot cũ

Với Spring Boot 3.3 trở xuống, có thể dùng @MockBean:

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class ReportServiceMethodSecurityTest {

    @Autowired
    ReportService reports;

    @MockBean
    ReportRepository repository;

    // Các test và Mockito stubbing/assertion giống ví dụ trên.
}
~~~

Spring Boot 3.4 đánh dấu @MockBean deprecated để chuyển sang @MockitoBean của Spring Framework. Hãy theo API sẵn có trong phiên bản dự án; nguyên tắc không đổi: mock repository hoặc collaborator, giữ service có @PreAuthorize là bean thật.

### 4.3. Tại sao không chỉ dùng unit test thuần Mockito?

Một unit test thuần có thể kiểm tra logic service với repository mock:

~~~java
@ExtendWith(MockitoExtension.class)
class ReportServiceUnitTest {

    @Mock
    ReportRepository repository;

    @InjectMocks
    ReportService reports;

    @Test
    void returnsReportWhenRepositoryFindsIt() {
        when(repository.findById("r-1"))
            .thenReturn(Optional.of(
                new Report("r-1", "Quarterly report")
            ));

        assertEquals("r-1", reports.read("r-1").id());
    }
}
~~~

Test này không có Spring context, không có @EnableMethodSecurity và không có proxy. Nó kiểm tra thân phương thức Java; nó không phải method-security test. Nếu chạy với SecurityContext trống, tùy cách gọi và cơ chế, method vẫn có thể chạy như Java object thông thường.

Giữ unit test thuần cho logic nghiệp vụ nếu cần, nhưng bổ sung integration test với Spring proxy để xác minh annotation bảo mật.

## 5. Test phải chứng minh cả hai nhánh

Một test chỉ kiểm tra user hợp lệ có thể xanh ngay cả khi method security chưa được bật. Vì thế cần negative test: caller thiếu quyền phải bị chặn.

| Tình huống | Authentication | Kết quả mong đợi | Repository |
|---|---|---|---|
| Được phép | report:read | Trả Report | Được gọi |
| Thiếu quyền | report:write | AccessDeniedException | Không được gọi |
| Anonymous | AnonymousAuthenticationToken | AccessDeniedException trong test method | Không được gọi |
| Không tìm thấy dữ liệu sau khi được phép | report:read | Lỗi nghiệp vụ/not found | Được gọi |
| Không có Authentication trong context | Context trống | Bị từ chối theo cấu hình method security hiện đại | Không được gọi |

Ca “không tìm thấy dữ liệu” khác với ca “thiếu quyền”: người dùng đã vượt qua authorization, thân phương thức được chạy, rồi repository mới không tìm thấy bản ghi. Không assert AccessDeniedException cho lỗi nghiệp vụ này.

Có thể thêm test cho SecurityContext trống:

~~~java
import org.springframework.security.core.context.SecurityContextHolder;

@Test
void emptySecurityContextDoesNotReachRepository() {
    SecurityContextHolder.clearContext();

    assertThrows(
        AccessDeniedException.class,
        () -> reports.read("r-1")
    );

    verifyNoInteractions(repository);
}
~~~

Với Spring Security hiện đại dùng authorization manager, biểu thức không được cấp quyền có thể tạo AccessDeniedException/AuthorizationDeniedException. Một interceptor hoặc cấu hình legacy có thể ném AuthenticationCredentialsNotFoundException khi context trống. Nếu dự án có hành vi khác, assert exception theo đúng interceptor/version đang dùng; điều quan trọng của test là xác minh repository không được gọi.

## 6. Kiểm thử HTTP bằng MockMvc mà không mock service

Khi kiểm tra HTTP, giữ cả controller và ReportService thật. Chỉ thay repository:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/{id}")
    public Report read(@PathVariable String id) {
        return reports.read(id);
    }
}
~~~

Cấu hình HTTP test cho phép request đi tới controller để method security quyết định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TestHttpSecurityConfig {

    @Bean
    SecurityFilterChain testSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình permitAll() chỉ để cô lập method security trong bài thực hành. Ứng dụng thật phải định nghĩa URL authorization phù hợp.

Test MockMvc:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportControllerSecurityTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportRepository repository;

    @Test
    void authorizedRequestUsesRealServiceAndReturnsReport() throws Exception {
        when(repository.findById("r-1"))
            .thenReturn(Optional.of(
                new Report("r-1", "Quarterly report")
            ));

        mvc.perform(get("/reports/r-1")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("r-1"));
    }

    @Test
    void unauthorizedRequestIsRejectedBeforeRepositoryCall()
            throws Exception {
        mvc.perform(get("/reports/r-1")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("report:write"))))
            .andExpect(status().isForbidden());

        verifyNoInteractions(repository);
    }
}
~~~

Đây là integration test có ý nghĩa: request đi qua MockMvc, controller thật gọi service thật, proxy method security kiểm tra authority, và repository mock giúp xác minh thân service không chạy khi bị từ chối.

Nếu test chỉ dùng @WebMvcTest(ReportController.class) rồi @MockitoBean ReportService, đó là controller slice test. Nó vẫn hữu ích để kiểm tra JSON mapping hoặc HTTP contract, nhưng không kiểm tra @PreAuthorize trên ReportService. Hãy đặt tên test theo đúng mục tiêu để người bảo trì không nhầm phạm vi bảo đảm.

## 7. Khi nào mock service là hợp lý?

Mock service không phải lúc nào cũng sai. Nó sai khi test được dùng làm bằng chứng cho chính sách method security nằm trên service đó.

Các trường hợp phù hợp:

- Controller slice test chỉ kiểm tra request mapping, validation đầu vào, status/response và việc controller gọi service.
- Test một client hoặc adapter khác gọi service interface và chỉ cần kiểm tra orchestration.
- Test UI/API contract độc lập với triển khai service.

Các trường hợp không phù hợp:

- Muốn chứng minh @PreAuthorize trên service thực sự chặn user thiếu authority.
- Muốn kiểm tra @PostAuthorize trên giá trị trả về của service thật.
- Muốn xác minh @PreFilter/@PostFilter đã lọc tham số hoặc kết quả.
- Muốn chứng minh method-security proxy được kích hoạt trên đường gọi production.

| Mục tiêu test | Service | Repository/gateway | Công cụ phù hợp |
|---|---|---|---|
| Logic Java thuần | Đối tượng thật tạo bằng Mockito | Mock | JUnit + Mockito |
| Method security | Bean thật qua Spring proxy | Mock | @SpringBootTest + @WithMockUser |
| Controller mapping | Có thể mock | Không liên quan | @WebMvcTest |
| HTTP + method security | Bean thật | Mock | @SpringBootTest + MockMvc |
| Reactive method security | Bean Reactive thật qua proxy | Mock | @SpringBootTest + WebTestClient |

## 8. Cẩn trọng với @SpyBean và Mockito spy

Mockito spy gọi method thật theo mặc định khi method không được stub. Tuy nhiên, kết hợp spy với Spring AOP proxy có thể tạo nhiều lớp proxy hoặc khiến thứ tự advice khó nhìn thấy. Cách stub như when(spy.read(...)).thenReturn(...) còn có thể gọi method thật ngay trong lúc thiết lập stub.

Nếu mục tiêu là kiểm tra method security, không cần spy service để xác minh method được gọi. Hãy mock collaborator và dùng verify trên collaborator. Nếu cần quan sát side effect của service, có thể dùng repository mock, event publisher mock hoặc một recorder test riêng.

Với Spring Framework 6.2+, @MockitoSpyBean có thể thay thế một bean bằng spy; Spring Boot cũ có @SpyBean. Các công cụ này phù hợp cho một số integration test, nhưng không nên dùng để thay thế test với bean method-security thật và đường gọi proxy rõ ràng. Khi buộc phải dùng spy, viết test âm tính xác minh caller thiếu quyền vẫn bị từ chối trước khi collaborator chạy.

## 9. Reactive WebFlux: giữ service thật, mock reactive repository

Nguyên tắc tương tự áp dụng cho WebFlux. Không mock service Reactive có @PreAuthorize nếu đang kiểm tra reactive method security. Hãy giữ service thật và mock repository trả Mono.

Reactive repository:

~~~java
import reactor.core.publisher.Mono;

public interface ReactiveReportRepository {
    Mono<Report> findById(String id);
}
~~~

Service Reactive:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReportService {

    private final ReactiveReportRepository repository;

    public ReactiveReportService(ReactiveReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<Report> read(String id) {
        return repository.findById(id);
    }
}
~~~

Bật Reactive Method Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveTestSecurityConfig {

    @Bean
    SecurityWebFilterChain reactiveTestFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .anyExchange().permitAll())
            .build();
    }
}
~~~

Controller Reactive:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/reactive/reports")
public class ReactiveReportController {

    private final ReactiveReportService reports;

    public ReactiveReportController(ReactiveReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/{id}")
    public Mono<Report> read(@PathVariable String id) {
        return reports.read(id);
    }
}
~~~

Test WebTestClient với @MockitoBean trên repository:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest
class ReactiveReportMethodSecurityTest {

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReactiveReportRepository repository;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void authorizedCallerReceivesReport() {
        when(repository.findById("r-1"))
            .thenReturn(Mono.just(
                new Report("r-1", "Quarterly report")
            ));

        client.mutateWith(mockUser("lan").authorities(
                new SimpleGrantedAuthority("report:read")))
            .get().uri("/reactive/reports/r-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("r-1");
    }

    @Test
    void callerWithoutReadAuthorityIsDeniedBeforeRepositoryCall() {
        client.mutateWith(mockUser("lan").authorities(
                new SimpleGrantedAuthority("report:write")))
            .get().uri("/reactive/reports/r-1")
            .exchange()
            .expectStatus().isForbidden();

        verifyNoInteractions(repository);
    }
}
~~~

Ví dụ yêu cầu ứng dụng chạy WebFlux, nạp ReactiveTestSecurityConfig, controller và service thật. WebTestClient subscribe publisher và cung cấp Authentication qua Reactive SecurityContext. Repository mock trả Mono để service giữ mô hình reactive; không gọi block() trong service hoặc policy.

Nếu dùng Spring Boot 3.3 trở xuống, thay @MockitoBean bằng @MockBean từ Spring Boot Test. Vẫn giữ ReactiveReportService thật trong application context.

## 10. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| User thiếu quyền vẫn nhận dữ liệu trong test. | Service có @PreAuthorize đã bị thay bằng mock. | Giữ service thật; chỉ mock repository/gateway. |
| Test @WithMockUser chạy xanh nhưng không chứng minh method security. | Test gọi đối tượng tạo bằng new hoặc @InjectMocks. | Dùng Spring context, inject bean proxy và có negative test. |
| Test controller slice trả 200 cho user sai quyền. | @WebMvcTest đang dùng mock service, nên method annotation trên implementation không chạy. | Dùng @SpringBootTest + MockMvc cho authorization integration test. |
| Repository được gọi dù caller thiếu authority. | Method security chưa bật, đường gọi bypass proxy hoặc test đang gọi mock service. | Kiểm tra @EnableMethodSecurity, bean thật và verifyNoInteractions. |
| @MockitoBean không tìm thấy annotation. | Spring Framework/Spring Boot của dự án quá cũ. | Dùng @MockBean theo phiên bản; nâng framework nếu muốn dùng @MockitoBean. |
| @MockitoBean đặt trên ReportService làm test chỉ trả dữ liệu stub. | Bean được thay bằng mock; thân method thật và policy không được kiểm chứng. | Chuyển mock sang ReportRepository. |
| Spy gọi method thật ngay khi stubbing. | Dùng when(spy.method()) trên spy. | Tránh spy service; nếu thực sự cần spy, hiểu doReturn và kiểm tra proxy riêng. |
| Test âm tính nhận lỗi database thay vì AccessDeniedException. | Repository mock chưa được stub hoặc method body đã chạy. | Stub dữ liệu cho ca được phép; với ca từ chối, xác minh repository không được gọi. |
| WebFlux test không từ chối user sai quyền. | Service bị mock hoặc Reactive Method Security chưa bật. | Giữ service thật, bật @EnableReactiveMethodSecurity và dùng WebTestClient mockUser. |
| Mockito mock reactive repository trả null. | Chưa stub Mono/Flux cho ca được phép. | Trả Mono.just(...), Mono.empty() hoặc publisher phù hợp. |
| Chỉ có test user hợp lệ. | Nếu interceptor tắt, happy path vẫn có thể xanh. | Bắt buộc có test thiếu authority và xác minh collaborator không chạy. |

## 11. Bài thực hành và tiêu chí hoàn thành

1. Tạo ReportRepository, ReportService có @PreAuthorize("hasAuthority('report:read')") và bật @EnableMethodSecurity.
2. Viết một test sai mục tiêu bằng cách thay ReportService bằng Mockito mock. Quan sát rằng test này chỉ chứng minh mock trả dữ liệu, không chứng minh policy trên implementation.
3. Viết lại với @SpringBootTest, @Autowired ReportService thật và @MockitoBean ReportRepository.
4. Dùng @WithMockUser(authorities = "report:read") để xác minh người được phép đọc nhận dữ liệu từ repository mock.
5. Dùng @WithMockUser(authorities = "report:write") để xác minh caller thiếu quyền nhận AccessDeniedException và repository không có tương tác.
6. Dùng @WithAnonymousUser để kiểm tra anonymous bị chặn.
7. Tạo controller thật, dùng MockMvc và chỉ mock repository; kiểm tra request được phép trả 200, request thiếu quyền trả 403.
8. Trên WebFlux, tạo ReactiveReportService trả Mono, giữ service thật và mock ReactiveReportRepository; dùng WebTestClient kiểm tra authority đúng/sai.
9. Đổi repository mock thành implementation test fake nếu cần kiểm thử truy vấn phức tạp; không thay service đang được bảo vệ.
10. Đặt tên test theo phạm vi: unit test nghiệp vụ, controller slice test hoặc method-security integration test để reviewer hiểu chính xác điều đã được chứng minh.

**Tiêu chí hoàn thành:** Test phải gọi method trên bean Spring thật có annotation bảo mật. Dependency được mock để điều khiển dữ liệu. Người có authority phù hợp được phép; người thiếu authority hoặc anonymous bị từ chối trước khi repository chạy. Với HTTP, controller và service đều là bean thật; với Reactive, publisher được subscribe trong Reactor SecurityContext qua WebTestClient.

## Tài liệu tham khảo

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html)
- [Spring Framework 6.2 — MockitoBean API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
- [Spring Boot 3.4 — MockBean API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)

