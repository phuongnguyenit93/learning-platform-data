# Tự gọi phương thức trong cùng đối tượng và giới hạn của proxy

## 1. Vì sao annotation bảo mật có thể không chạy?

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Khi một method có @PreAuthorize nhưng caller vẫn thực thi được dù thiếu authority, một nguyên nhân cần kiểm tra là **self-invocation**: một phương thức trong object gọi trực tiếp phương thức khác của chính object đó.

Trong proxy mode, Spring Security áp dụng method security thông qua Spring AOP interceptor. Caller bên ngoài gọi bean đã được Spring bọc proxy; proxy kiểm tra chính sách rồi mới chuyển lời gọi tới target. Nhưng khi target gọi this.securedMethod(), lời gọi nội bộ không quay lại proxy. Interceptor không có cơ hội đánh giá annotation của phương thức được gọi.

Đây là một giới hạn có ý nghĩa bảo mật: code có thể nhìn thấy @PreAuthorize trong source nhưng đường gọi thực tế lại bỏ qua chính sách đó.

Sau bài học, bạn có thể:

- Mô tả đường đi caller → proxy → interceptor → target.
- Phân biệt lời gọi bean từ bên ngoài với lời gọi this.method() trong cùng object.
- Tạo test chứng minh self-invocation bỏ qua @PreAuthorize và test chứng minh cách sửa.
- Hiểu các giới hạn của JDK dynamic proxy và class-based proxy (CGLIB).
- Chọn cách tổ chức bean để mọi đường gọi nhạy cảm đi qua proxy.
- Nhận biết vấn đề tương tự với @PostAuthorize, @PreFilter, @PostFilter, @Transactional và các advice Spring AOP khác.
- Kiểm chứng nguyên tắc tương tự trong WebFlux, nơi SecurityContext được truyền qua Reactor Context.

> **Phạm vi:** Ví dụ Servlet dùng Spring Security 6.x, Spring Boot 3.x và JUnit 5; phần Reactive dùng WebFlux và Reactor. Nội dung tập trung vào proxy-based method security được bật bằng @EnableMethodSecurity hoặc @EnableReactiveMethodSecurity.

## 2. Proxy mode hoạt động như thế nào?

Spring tạo một proxy đại diện cho bean được áp dụng advice. Khi một bean khác gọi phương thức qua tham chiếu proxy, lời gọi đi qua interceptor trước khi tới target.

~~~mermaid
sequenceDiagram
    participant Caller as Controller / bean khác
    participant Proxy as Spring AOP proxy
    participant Interceptor as Method-security interceptor
    participant Target as Target object

    Caller->>Proxy: readDocument("doc-42")
    Proxy->>Interceptor: Kiểm tra @PreAuthorize
    Interceptor->>Interceptor: Đọc Authentication và authority
    alt Có quyền
        Interceptor->>Target: Gọi phương thức
        Target-->>Interceptor: Kết quả
        Interceptor-->>Proxy: Kết quả
        Proxy-->>Caller: Kết quả
    else Thiếu quyền
        Interceptor-->>Proxy: AccessDeniedException
        Proxy-->>Caller: Ngoại lệ
    end
~~~

Trong một bean có hai phương thức, lời gọi nội bộ có đường đi khác:

~~~mermaid
flowchart TD
    A["Caller bên ngoài"] --> B["Proxy của ReportService"]
    B --> C["Target.preview()"]
    C --> D["this.readInternal()"]
    D --> E["Target.readInternal()"]
    E --> F["Thân phương thức chạy"]
    G["Method-security interceptor"] -. "Không được gọi lại" .-> E
~~~

Ở đây proxy chỉ chặn lời gọi đi vào từ bên ngoài. Khi target đang chạy, this trỏ tới chính target object; this.readInternal() là lời gọi Java thông thường. Nó không đi qua proxy một lần nữa.

Điều này không riêng Spring Security. Các tính năng dựa trên Spring AOP proxy như @Transactional, @Cacheable, @Async hoặc custom aspect cũng có thể bị bỏ qua khi một phương thức tự gọi phương thức khác trong cùng bean. Mỗi tính năng có cấu hình và điều kiện riêng, nhưng nguyên nhân self-invocation trong proxy mode là giống nhau.

## 3. Tái hiện lỗi với @PreAuthorize

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Service cố ý có lỗi thiết kế:

~~~java
// UnsafeReportService.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class UnsafeReportService {

    public String preview(String reportId) {
        // Self-invocation: lời gọi không quay lại Spring proxy.
        return readInternal(reportId);
    }

    @PreAuthorize("hasAuthority('report:read')")
    public String readInternal(String reportId) {
        return "REPORT-" + reportId;
    }
}
~~~

Nếu caller gọi trực tiếp bean proxy từ bên ngoài:

~~~java
unsafeReportService.readInternal("42");
~~~

method security được áp dụng và caller phải có report:read.

Nhưng nếu caller gọi:

~~~java
unsafeReportService.preview("42");
~~~

proxy chặn preview(), sau đó target.preview() gọi this.readInternal(). Lời gọi thứ hai chạy trên target và không đi qua interceptor. Vì preview() không có chính sách bảo vệ riêng, caller thiếu report:read vẫn nhận kết quả.

### 3.1. Test chứng minh self-invocation bỏ qua proxy

Test phải nạp Spring context và inject bean thật:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class SelfInvocationSecurityTest {

    @Autowired
    UnsafeReportService reports;

    @Test
    @WithMockUser(username = "lan", authorities = "report:write")
    void externalCallToSecuredMethodIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> reports.readInternal("42"));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "report:write")
    void selfInvocationBypassesMethodSecurity() {
        assertEquals(
            "REPORT-42",
            reports.preview("42")
        );
    }
}
~~~

Hai test tạo ra bằng chứng đối chiếu:

- Gọi readInternal() trực tiếp qua bean proxy: caller thiếu report:read bị từ chối.
- Gọi preview(): cùng caller vẫn nhận kết quả vì lời gọi nội bộ đã bỏ qua proxy.

Test thứ hai cố ý ghi nhận một lỗi bảo mật để người học hiểu cơ chế. Không giữ thiết kế này trong production nếu preview() làm lộ dữ liệu nhạy cảm. Khi kiểm thử ứng dụng thật, có thể xác minh thêm một collaborator như repository hoặc audit recorder đã được gọi để chứng minh thân phương thức thực sự chạy; dùng dữ liệu test cô lập để tránh trạng thái dùng chung giữa các test.

**Không dùng Mockito @InjectMocks để chứng minh method security.** Đối tượng được Mockito tạo không phải bean đã được Spring áp method-security proxy. Unit test đó có thể hữu ích để kiểm tra logic Java, nhưng không xác minh interceptor.

## 4. Cách sửa ưu tiên: tách phương thức bảo mật sang bean riêng

Giải pháp dễ đọc và dễ kiểm thử nhất là đặt ranh giới bảo mật trong một bean khác. Bean gọi phải inject dependency qua Spring; lời gọi sẽ đi qua proxy của bean được bảo vệ.

~~~java
// SecuredReportReader.java
public interface SecuredReportReader {
    String read(String reportId);
}
~~~

~~~java
// SecuredReportReaderService.java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SecuredReportReaderService implements SecuredReportReader {

    @Override
    @PreAuthorize("hasAuthority('report:read')")
    public String read(String reportId) {
        return "REPORT-" + reportId;
    }
}
~~~

~~~java
// ReportPreviewService.java
import org.springframework.stereotype.Service;

@Service
public class ReportPreviewService {

    private final SecuredReportReader reader;

    public ReportPreviewService(SecuredReportReader reader) {
        this.reader = reader;
    }

    public String preview(String reportId) {
        // Gọi qua bean được inject; tham chiếu này là proxy của reader.
        return reader.read(reportId);
    }
}
~~~

Bây giờ đường gọi là:

~~~mermaid
flowchart LR
    A["Controller"] --> B["ReportPreviewService"]
    B --> C["SecuredReportReader proxy"]
    C --> D["Method-security interceptor"]
    D --> E["SecuredReportReaderService target"]
~~~

Viết test cho cả hai kết quả:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class RefactoredReportSecurityTest {

    @Autowired
    ReportPreviewService previews;

    @Test
    @WithMockUser(username = "lan", authorities = "report:write")
    void callerWithoutReadAuthorityIsDeniedThroughFacade() {
        assertThrows(AccessDeniedException.class,
            () -> previews.preview("42"));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "report:read")
    void callerWithReadAuthorityCanPreview() {
        assertEquals(
            "REPORT-42",
            previews.preview("42")
        );
    }
}
~~~

Test đầu rất quan trọng: caller gọi facade không có annotation, nhưng facade chuyển tiếp qua bean reader được bảo vệ. Vì lời gọi đi qua proxy của reader, method security từ chối trước khi target.read() chạy.

Tách bean cũng giúp mỗi class có một trách nhiệm rõ: facade điều phối use case; reader thực thi thao tác đọc với chính sách truy cập riêng. Khi hệ thống có nhiều đường gọi như controller, scheduler và message consumer, tất cả đều có thể inject cùng bean bảo vệ.

## 5. Các cách xử lý khác và trade-off

### 5.1. Đặt chính sách ở phương thức public bên ngoài

Nếu mọi đường vào preview() đều cần cùng quyền, có thể bảo vệ trực tiếp preview():

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String preview(String reportId) {
    return readInternal(reportId);
}
~~~

Khi proxy chặn preview(), caller thiếu report:read bị từ chối trước khi target chạy. Tuy nhiên, nếu readInternal() cũng được gọi từ các bean khác, vẫn cần bảo vệ đường gọi công khai đó. Đừng để một method public khác gọi nội bộ và vô tình tạo đường bypass.

Cách này phù hợp khi quyền áp dụng cho toàn bộ use case bên ngoài. Nó không phù hợp nếu preview() được phép rộng hơn nhưng một thao tác con cần quyền riêng.

### 5.2. Tự gọi qua proxy được inject

Một số dự án dùng self-injection để giữ lời gọi qua proxy. Có thể inject một tham chiếu lazy theo interface hoặc dùng ObjectProvider để lấy bean proxy khi cần. Cách này cần cẩn trọng:

- Có thể tạo quan hệ phụ thuộc vòng giữa bean và chính nó.
- Cấu hình proxy/interface phải đúng; gọi trực tiếp target vẫn bỏ qua advice.
- Người đọc code khó nhận ra vì sao bean gọi chính nó thông qua một dependency.
- Có thể làm unit test và lifecycle phức tạp hơn.

Chỉ cân nhắc khi không thể tách trách nhiệm sang bean riêng và đã có test chứng minh tham chiếu được inject là proxy thực sự.

### 5.3. AopContext.currentProxy()

Spring AOP có thể cho phép lấy proxy hiện tại thông qua AopContext.currentProxy() nếu proxy được cấu hình để expose. Khi đó code có thể gọi method qua proxy thay vì this.

Đây thường không phải lựa chọn đầu tiên:

- Business code bị gắn chặt với Spring AOP.
- Phải bật exposeProxy trong cấu hình proxy.
- Nếu lời gọi không chạy trong proxy context phù hợp, currentProxy() không có giá trị để sử dụng.
- Code trở nên khó đọc và khó di chuyển.

Nếu dùng cách này, phải có test chứng minh method security thực sự được kích hoạt. Không coi việc gọi currentProxy() thành công là bằng chứng đủ.

### 5.4. AspectJ weaving

AspectJ weaving có mô hình áp dụng advice khác với proxy mode và có thể xử lý một số lời gọi nội bộ mà proxy không thấy. Tuy nhiên, bật weaving cho Spring AOP không đồng nghĩa mọi annotation method security sẽ tự động chuyển sang một cơ chế weaving tương đương. Đây là thay đổi kiến trúc, đòi hỏi kiểm tra hỗ trợ của đúng tính năng và phiên bản, cấu hình weaving, build/runtime agent và test tích hợp. Với đa số ứng dụng service thông thường, tách bean là cách dễ hiểu hơn.

## 6. Giới hạn của JDK dynamic proxy và CGLIB

Spring AOP thường tạo proxy theo một trong hai kiểu:

| Đặc điểm | JDK dynamic proxy | Class-based proxy (CGLIB) |
|---|---|---|
| Cách tạo | Tạo object triển khai các interface của bean | Tạo subclass của class đích |
| Kiểu nên inject | Interface mà bean triển khai | Class hoặc interface tùy cấu hình |
| Phương thức có thể gọi qua proxy | Các phương thức được khai báo trên interface proxy | Các phương thức có thể được override và intercept |
| Giới hạn đáng chú ý | Phương thức không có trên interface không được expose qua proxy | Không thể override final class/final method; private method không phải điểm chặn có thể override |
| Self-invocation | Vẫn bỏ qua proxy | Vẫn bỏ qua proxy |

### 6.1. JDK dynamic proxy

Khi dùng JDK proxy, caller nên làm việc qua interface:

~~~java
public interface ReportReader {
    String read(String reportId);
}
~~~

~~~java
@Service
public class ReportReaderService implements ReportReader {

    @Override
    @PreAuthorize("hasAuthority('report:read')")
    public String read(String reportId) {
        return "REPORT-" + reportId;
    }
}
~~~

~~~java
@Service
public class ReportControllerFacade {

    private final ReportReader reader;

    public ReportControllerFacade(ReportReader reader) {
        this.reader = reader;
    }

    public String preview(String id) {
        return reader.read(id);
    }
}
~~~

Nếu proxy là JDK dynamic proxy, inject implementation cụ thể có thể không tương thích với kiểu object proxy đang được cung cấp. Inject interface giúp caller không phụ thuộc loại proxy. Phương thức được gọi phải nằm trên interface mà proxy expose.

### 6.2. CGLIB class-based proxy

CGLIB tạo subclass để chặn phương thức. Vì subclass cần override method, final class hoặc final method không thể được intercept theo cơ chế này; private method cũng không thể override. Với method security, hãy ưu tiên public method trên Spring bean được gọi qua proxy.

Không nên kết luận chỉ từ source code rằng ứng dụng đang dùng CGLIB hay JDK proxy. Cấu hình AOP, Spring Boot và bean/interface thực tế quyết định loại proxy. Có thể kiểm tra bằng AopUtils trong test:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ReportProxyTypeTest {

    @Autowired
    ReportReader reader;

    @Test
    void injectedBeanIsAopProxy() {
        assertTrue(AopUtils.isAopProxy(reader));
    }
}
~~~

AopUtils.isAopProxy() chỉ chứng minh object là proxy AOP. Proxy có thể được tạo bởi transaction, cache hoặc advisor khác. Để chứng minh method security, cần thêm test hành vi với principal thiếu quyền.

## 7. Những vị trí khác có thể bỏ qua proxy

Self-invocation không phải trường hợp duy nhất:

| Đường gọi | Vì sao không có method-security interceptor |
|---|---|
| Dùng new Service() | Object không do Spring quản lý và không có proxy. |
| Gọi this.securedMethod() | Lời gọi đi trực tiếp tới target, không quay lại proxy. |
| Gọi phương thức private | Không thể gọi qua proxy public/interface thông thường; class proxy cũng không override private method. |
| Gọi phương thức không có trên interface với JDK proxy | JDK proxy không expose phương thức đó cho caller. |
| Gọi final method với CGLIB proxy | Subclass không override được final method để chèn advice. |
| Gọi trong constructor hoặc quá trình khởi tạo target | Target có thể đang được tạo trước khi proxy hoàn chỉnh được công bố. |
| Gọi trực tiếp target qua một tham chiếu khác | Đường gọi bỏ qua proxy Spring. |

Với @PostAuthorize, @PreFilter và @PostFilter, vấn đề tương tự: nếu lời gọi không qua interceptor, kiểm tra kết quả hoặc lọc tham số/kết quả cũng không diễn ra. Không chỉ kiểm tra @PreAuthorize khi rà soát self-invocation.

Các annotation Spring AOP khác có thể bị ảnh hưởng tương tự. Ví dụ một method @Transactional gọi this.writeAudit() không làm writeAudit() tự mở transaction riêng như người đọc có thể kỳ vọng; một method @Cacheable gọi nội bộ method cacheable khác có thể bỏ qua cache advice. Hãy kiểm tra từng tính năng theo cơ chế proxy và cấu hình cụ thể.

## 8. Kiểm thử đường gọi qua MockMvc

Một controller có thể gọi facade, facade gọi reader qua proxy:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {

    private final ReportPreviewService previews;

    public ReportController(ReportPreviewService previews) {
        this.previews = previews;
    }

    @GetMapping("/{id}/preview")
    public String preview(@PathVariable String id) {
        return previews.preview(id);
    }
}
~~~

Trong test HTTP, cấu hình filter chain phải cho request đi tới controller để method security được quan sát. Ví dụ cấu hình học tập:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoHttpSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .build();
    }
}
~~~

Test MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
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
class ReportProxyHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void userWithReadAuthorityCanPreview() throws Exception {
        mvc.perform(get("/reports/42/preview")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT-42"));
    }

    @Test
    void userWithoutReadAuthorityIsDeniedByReaderProxy()
            throws Exception {
        mvc.perform(get("/reports/42/preview")
                .with(user("lan").authorities(
                    new SimpleGrantedAuthority("report:write"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Cấu hình permitAll() toàn cục ở đây chỉ dùng để cô lập method security. Ứng dụng thật cần URL authorization phù hợp. Test cần nạp ReportPreviewService, SecuredReportReaderService và controller thật; nếu mock reader hoặc facade thì không còn kiểm chứng được proxy của service.

## 9. WebFlux: self-invocation vẫn là giới hạn của proxy

Reactive method security dùng @EnableReactiveMethodSecurity và Reactor Context để đánh giá Authentication. Nhưng lời gọi nội bộ trong cùng target vẫn là lời gọi Java trực tiếp; nó không tự quay lại Spring proxy chỉ vì method trả Mono hoặc Flux.

Ví dụ không an toàn:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class UnsafeReactiveReportService {

    public Mono<String> preview(String id) {
        return readInternal(id);
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> readInternal(String id) {
        return Mono.just("REPORT-" + id);
    }
}
~~~

Nếu caller gọi preview() qua proxy, target.preview() gọi this.readInternal(). Phương thức được bảo vệ có thể chạy mà không qua reactive method-security interceptor.

Cách sửa cũng là tách bean:

~~~java
public interface ReactiveReportReader {
    Mono<String> read(String id);
}
~~~

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReportReaderService implements ReactiveReportReader {

    @Override
    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> read(String id) {
        return Mono.just("REPORT-" + id);
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReportPreviewService {

    private final ReactiveReportReader reader;

    public ReactiveReportPreviewService(ReactiveReportReader reader) {
        this.reader = reader;
    }

    public Mono<String> preview(String id) {
        return reader.read(id);
    }
}
~~~

WebFlux configuration:

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
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .anyExchange().permitAll())
            .build();
    }
}
~~~

Controller WebFlux:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveReportController {

    private final ReactiveReportPreviewService previews;

    public ReactiveReportController(ReactiveReportPreviewService previews) {
        this.previews = previews;
    }

    @GetMapping("/reactive/reports/{id}/preview")
    public Mono<String> preview(@PathVariable String id) {
        return previews.preview(id);
    }
}
~~~

WebTestClient kiểm tra hai tập quyền:

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
class ReactiveReportProxyTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void readAuthorityCanPreview() {
        client.mutateWith(mockUser("lan").authorities(
                new SimpleGrantedAuthority("report:read")))
            .get().uri("/reactive/reports/42/preview")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("REPORT-42");
    }

    @Test
    void writeOnlyAuthorityCannotPreview() {
        client.mutateWith(mockUser("lan").authorities(
                new SimpleGrantedAuthority("report:write")))
            .get().uri("/reactive/reports/42/preview")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các test yêu cầu ứng dụng thực sự chạy WebFlux, nạp controller, facade, reader bean và ReactiveSecurityConfig. WebTestClient subscribe Mono và thiết lập mock Authentication trong Reactive SecurityContext. Nếu test trực tiếp service trả Mono, dùng StepVerifier với Reactor Context phù hợp; không chỉ tạo publisher rồi kết luận interceptor đã chạy.

## 10. Checklist rà soát self-invocation trong codebase

Khi review một service có annotation bảo mật, hãy lần theo đường gọi thay vì chỉ tìm annotation:

1. Tìm method có @PreAuthorize, @PostAuthorize, @PreFilter hoặc @PostFilter.
2. Tìm tất cả caller của method đó, kể cả caller cùng class.
3. Xác định caller đang gọi qua bean được inject hay dùng this.method().
4. Kiểm tra bean được tạo bởi Spring hay tự tạo bằng new.
5. Kiểm tra method có được expose qua interface nếu ứng dụng dùng JDK proxy không.
6. Kiểm tra method/class có final hoặc method private trong trường hợp dùng CGLIB không.
7. Kiểm tra lời gọi có xảy ra trong constructor hoặc callback khởi tạo trước khi proxy sẵn sàng không.
8. Viết test thiếu authority cho đường gọi thực tế, không chỉ gọi trực tiếp method được annotate.
9. Nếu đã tách bean, kiểm thử facade → secured bean để bảo đảm lời gọi qua proxy.
10. Nếu dùng workaround self-injection hoặc AopContext, ghi rõ lý do và có test chứng minh interceptor được gọi.

Có thể dùng AopUtils để kiểm tra object được inject là proxy, nhưng điều đó chưa đủ. Proxy có thể tồn tại vì một advisor khác. Phép thử hành vi với principal thiếu quyền mới chứng minh method security đang bảo vệ đúng đường gọi.

## 11. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| @PreAuthorize có mặt nhưng lời gọi nội bộ vẫn chạy. | Self-invocation dùng this và bỏ qua proxy. | Tách phương thức được bảo vệ sang bean riêng hoặc bảo vệ use case public bên ngoài. |
| Gọi trực tiếp service trong unit test không bị chặn. | Test tạo đối tượng bằng new hoặc @InjectMocks. | Dùng @SpringBootTest và inject bean thật. |
| Controller gọi facade, facade gọi method nhạy cảm nhưng thiếu quyền vẫn qua. | Facade và method nhạy cảm ở cùng target, lời gọi nội bộ không qua proxy. | Inject một bean bảo vệ riêng vào facade. |
| Inject implementation thất bại khi bật AOP. | Bean đang được cung cấp dưới dạng JDK interface proxy. | Inject interface được proxy expose hoặc cấu hình proxy theo yêu cầu. |
| Method private/final không được advice với CGLIB. | Class proxy không thể override điểm gọi đó. | Đưa policy lên method phù hợp, thường là public method của bean được inject. |
| Chỉ kiểm tra AopUtils.isAopProxy() rồi kết luận an toàn. | Proxy có thể do transaction/cache hoặc advisor khác tạo. | Thêm negative test chứng minh thiếu authority bị từ chối. |
| @PostAuthorize hoặc @PostFilter cũng bị bỏ qua. | Lời gọi không qua method-security interceptor. | Kiểm tra mọi annotation method security trên đường gọi, không chỉ @PreAuthorize. |
| @Transactional không chạy khi method tự gọi. | Cùng giới hạn proxy-based AOP. | Tách transactional operation sang bean khác hoặc đặt transaction ở ranh giới use case. |
| WebFlux trả kết quả dù method có @PreAuthorize. | Reactive self-invocation hoặc reactive method security chưa được bật. | Kiểm tra proxy và @EnableReactiveMethodSecurity; gọi qua bean Reactive riêng. |
| Dùng AopContext.currentProxy() nhưng lỗi runtime. | Proxy chưa expose hoặc code không chạy trong proxy invocation context. | Ưu tiên tách bean; nếu buộc dùng, cấu hình exposeProxy và test kỹ. |

## 12. Bài thực hành và tiêu chí hoàn thành

1. Tạo UnsafeReportService với preview() gọi readInternal() bằng this; gắn @PreAuthorize("hasAuthority('report:read')") lên readInternal().
2. Dùng @SpringBootTest và @WithMockUser(authorities = "report:write") để chứng minh gọi readInternal() trực tiếp bị từ chối nhưng gọi preview() lại chạy. Giải thích chính xác lời gọi nào đi qua proxy.
3. Tách readInternal() sang SecuredReportReader bean riêng; inject interface này vào ReportPreviewService.
4. Viết lại test để caller report:write bị từ chối khi gọi qua facade, còn report:read được phép.
5. Kiểm tra AopUtils.isAopProxy() trên bean được inject, sau đó chứng minh bằng negative test hành vi; giải thích vì sao chỉ kiểm tra proxy chưa đủ.
6. Thử cấu hình JDK proxy và class-based proxy nếu dự án hỗ trợ; kiểm tra cách inject, interface method, final method và giới hạn private method.
7. Tìm một method @Transactional hoặc @Cacheable tự gọi method khác trong cùng bean; dự đoán advice nào bị bỏ qua và viết test phù hợp.
8. Trên WebFlux, tạo reactive facade gọi reactive reader qua bean riêng; dùng WebTestClient mockUser để kiểm tra authority đúng/sai.
9. Review codebase theo checklist và ghi lại các đường gọi có nguy cơ bypass method security.

**Tiêu chí hoàn thành:** Người học giải thích được vì sao this.method() không đi qua Spring proxy, chứng minh được bypass bằng test có principal thiếu quyền, sau đó sửa bằng cách tách bean và chứng minh đường gọi qua proxy từ facade. Bộ test phải xác minh hành vi thực tế trên Servlet hoặc Reactive stack được ứng dụng sử dụng.

## Tài liệu tham khảo

- [Spring Framework — Understanding AOP Proxies and Self Invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html)

