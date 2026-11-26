# `@MockBean`, `@SpyBean` và các API thay thế theo thế hệ Spring

Khi viết test Spring Security, ta thường cần thay một dịch vụ phụ thuộc bằng mock để kiểm tra controller, hoặc theo dõi một bean thật bằng spy. Trong các dự án Spring Boot đời trước, hai annotation quen thuộc là `@MockBean` và `@SpyBean`. Từ Spring Framework 6.2, có thêm `@MockitoBean` và `@MockitoSpyBean`; Spring Boot 3.4 đánh dấu các annotation cũ là deprecated để chuyển sang API mới, và Boot 4.0 loại bỏ chúng.

Điều quan trọng là **chọn annotation theo phiên bản Framework/Boot thực tế**, đồng thời hiểu nó thay đổi bean nào trong `ApplicationContext`. Một mock đặt nhầm lên chính service đang được kiểm tra method security có thể làm test không còn đi qua proxy bảo mật. Bài này giúp lựa chọn API đúng thế hệ và dùng chúng có chủ đích trong test Servlet/Reactive.

Bài thuộc chương **Phụ thuộc và phiên bản** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và các ca được phép hoặc bị từ chối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt vai trò của `@MockBean`, `@SpyBean`, `@MockitoBean` và `@MockitoSpyBean`.
2. Chọn đúng annotation theo thế hệ Spring Boot/Spring Framework.
3. Biết package sở hữu annotation và dependency cần có.
4. Dùng mock để thay thế collaborator và spy để quan sát bean thật.
5. Thiết lập mock trong `@WebMvcTest`/`@WebFluxTest` mà vẫn kiểm chứng Security filter chain.
6. Tránh vô tình thay thế bean có `@PreAuthorize` hoặc proxy AOP đang cần kiểm tra.
7. Chẩn đoán lỗi do nhiều bean cùng kiểu, bean không tồn tại, context cache hoặc API đã bị deprecated/removed.

## 2. Bốn annotation và vai trò

| Annotation | Nguồn | Hành vi | Trường hợp dùng |
|---|---|---|---|
| `@MockBean` | Spring Boot Test (cũ) | Đăng ký Mockito mock vào ApplicationContext; thay bean phù hợp nếu đã tồn tại hoặc thêm mock nếu chưa có | Dự án Boot cũ hoặc giai đoạn chuyển tiếp |
| `@SpyBean` | Spring Boot Test (cũ) | Bao một bean thật bằng Mockito spy để theo dõi/làm stub một phần hành vi | Dự án Boot cũ hoặc giai đoạn chuyển tiếp |
| `@MockitoBean` | Spring Framework Test (mới) | Override bean bằng Mockito mock; mặc định thay nếu có hoặc tạo mock mới nếu chưa có | Spring Framework 6.2+, Boot 3.4+ và Boot 4.x |
| `@MockitoSpyBean` | Spring Framework Test (mới) | Wrap bean thật bằng Mockito spy | Spring Framework 6.2+, Boot 3.4+ và Boot 4.x |

**Mock** là một đối tượng giả lập có hành vi do test định nghĩa. **Spy** bọc một đối tượng thật; các method chưa được stub thường vẫn chạy logic thật. Cả bốn annotation đều tác động lên bean trong test context, nhưng **không phải** annotation xác thực của Spring Security và không tự tạo `SecurityContext`.

### 2.1. Package cần nhớ

Các annotation Boot cũ:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
```

Các annotation Framework mới:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Các annotation Security Test có package riêng:

```java
import org.springframework.security.test.context.support.WithMockUser;
```

`@WithMockUser` thiết lập người dùng giả lập cho test. `@MockitoBean`/`@MockBean` thay một dependency của ứng dụng. **Đừng nhầm hai nhóm**: có mock service không có nghĩa request đã được xác thực, và có `@WithMockUser` không có nghĩa service phụ thuộc đã được mock.

## 3. Chọn API theo thế hệ Boot và Framework

Mốc chuyển đổi quan trọng:

| Nền tảng | Spring Framework | API mock/spy nên dùng | Trạng thái |
|---|---|---|---|
| Spring Boot 3.0–3.3 | Framework 6.0–6.1 | `@MockBean`, `@SpyBean` | API Boot cũ, chưa có `@MockitoBean` trong Framework 6.2 |
| Spring Boot 3.4–3.5 | Framework 6.2 | `@MockitoBean`, `@MockitoSpyBean` | API Framework mới; `@MockBean`/`@SpyBean` deprecated từ Boot 3.4.0, dự kiến removal ở 4.0.0 |
| Spring Boot 4.x | Framework 7.x | `@MockitoBean`, `@MockitoSpyBean` | Dùng API Framework; annotation Boot cũ đã bị loại bỏ |
| Spring Framework không dùng Boot | 6.2 trở lên | `@MockitoBean`, `@MockitoSpyBean` | Có sẵn trong Spring Test; cần cấu hình Mockito và TestContext |
| Spring Framework dưới 6.2, không Boot | Framework 6.0/6.1 hoặc cũ hơn | Mockito thủ công hoặc test configuration phù hợp | Không import annotation Framework mới |

Các dòng major ở bảng chỉ giúp định hướng. Với dự án thực tế, hãy kiểm tra **phiên bản đã resolve** của `spring-test` và `spring-boot-test`; không chỉ nhìn version plugin hoặc parent.

### 3.1. Điều gì thay đổi ở Boot 3.4?

Spring Boot 3.4 đánh dấu `@MockBean`, `@SpyBean` và các annotation container tương ứng là deprecated, for removal in Boot 4.0.0. API thay thế nằm trong Spring Framework 6.2, vì vậy Boot 3.4/3.5 có thể dùng annotation mới mà không cần chờ Boot 4.

Tuy nhiên, Boot 3.4 Release Notes lưu ý **chức năng không hoàn toàn giống nhau**. Ví dụ, annotation Framework mới không hỗ trợ một số cách đặt annotation cũ trên lớp `@Configuration`; khi chuyển đổi có thể cần đưa annotation lên field của test class hoặc dùng cách khai báo type-level được Framework hỗ trợ. Hãy kiểm tra cách dùng hiện tại trước khi thay tên annotation hàng loạt.

### 3.2. Dependency đến từ đâu?

| API | Artifact chính | Phạm vi |
|---|---|---|
| `@MockBean`, `@SpyBean` | `org.springframework.boot:spring-boot-test` (thường đi cùng starter test Boot) | Test |
| `@MockitoBean`, `@MockitoSpyBean` | `org.springframework:spring-test` | Test |
| Mockito `mock()`, `when()`, `verify()` | `org.mockito:mockito-core` (thường được starter test Boot đưa vào) | Test |
| `@WithMockUser`, `jwt()`, `mockJwt()` | `org.springframework.security:spring-security-test` | Test |
| `MockMvc`, `WebTestClient`, Spring TestContext | `org.springframework:spring-test` | Test |

Không tìm `@MockitoBean` trong `spring-security-test`: annotation này thuộc **Spring Framework Test**. Spring Security Test cung cấp cơ chế giả lập danh tính, token và request security.

## 4. Cách hoạt động của mock và spy trong ApplicationContext

### 4.1. `@MockitoBean`: thay thế hoặc tạo bean mock

Ví dụ:

```java
@MockitoBean
private ReportRepository reportRepository;
```

Spring tìm bean phù hợp với kiểu `ReportRepository` trong context. Theo mặc định, chiến lược là **REPLACE_OR_CREATE**:

- Nếu có bean phù hợp, bean đó được thay bằng Mockito mock.
- Nếu chưa có bean phù hợp, một mock mới được đăng ký trong context.

Khi muốn test thất bại nếu bean thật không tồn tại, dùng:

```java
@MockitoBean(enforceOverride = true)
private ReportRepository reportRepository;
```

Với `enforceOverride = true`, chiến lược trở thành **REPLACE**: Spring phải tìm được bean cần thay thế, nếu không sẽ báo lỗi. Điều này hữu ích trong full application context để phát hiện cấu hình thiếu bean. Trong một test slice cố ý không tải repository, dùng `enforceOverride = true` có thể làm test fail vì bean đó chưa có trong slice; hãy hiểu rõ phạm vi context trước khi bật.

### 4.2. `@MockitoSpyBean`: bọc bean thật

```java
@MockitoSpyBean
private ReportPolicy reportPolicy;
```

Spy cần có **một bean ứng viên phù hợp** để wrap. Nó không có nhiệm vụ tạo bean thay thế khi không có đối tượng thật. Nếu có nhiều bean cùng kiểu, dùng `@Qualifier` hoặc tên bean để phân biệt; nếu vẫn không xác định được một ứng viên duy nhất, quá trình tạo context sẽ thất bại.

Spy cho phép xác minh lời gọi trong khi vẫn chạy logic thật ở những method chưa được stub:

```java
verify(reportPolicy).canRead("annual-report");
```

Nếu method thật gây side effect khi thiết lập stub, tránh cú pháp `when(spy.method()).thenReturn(...)` vì lời gọi thật có thể được thực thi ngay lúc cấu hình. Dùng `doReturn(...).when(spy).method(...)` hoặc `doThrow(...)` phù hợp hơn.

### 4.3. Chọn bean bằng type, qualifier hoặc tên

Khi annotation được đặt trên field, kiểu field là căn cứ mặc định để xác định bean:

```java
@MockitoBean
private PaymentGateway paymentGateway;
```

Nếu context có nhiều bean cùng kiểu:

```java
@MockitoBean
@Qualifier("primaryPaymentGateway")
private PaymentGateway paymentGateway;
```

Tên field cũng có thể được dùng làm qualifier dự phòng nếu không có `@Qualifier`. Vì tên/qualifier tham gia việc xác định context configuration, dùng tên field **nhất quán giữa các lớp test** khi muốn Spring tái sử dụng context cache.

Có thể chỉ rõ bean bằng tên:

```java
@MockitoBean(name = "legacyPaymentGateway")
private PaymentGateway gateway;
```

Framework mới còn hỗ trợ khai báo ở cấp class bằng thuộc tính `types` (khi dùng type-level declaration), ví dụ:

```java
@MockitoBean(types = {ReportRepository.class, AuditClient.class})
class ReportControllerTest {
    // Các mock được đăng ký trong ApplicationContext của test.
}
```

Khi có nhiều candidate cùng type, cung cấp tên/qualifier rõ ràng. Với `@MockitoSpyBean`, luôn phải có bean thật tương ứng để wrap.

### 4.4. Chỉ singleton bean mới được override

Cơ chế bean override của Spring Framework chỉ hỗ trợ **singleton beans**. Cố thay thế hoặc spy một bean scope khác như prototype sẽ gây lỗi. Nếu bean được tạo qua `FactoryBean`, Spring override đối tượng do factory tạo ra theo quy tắc của bean override; không nên mặc định rằng mock đang thay chính instance `FactoryBean`.

## 5. Dùng annotation mới trong Spring Boot 3.4+ và 4.x

Ví dụ test controller MVC cần mock service layer. Giả định:

- `GET /api/reports` yêu cầu authority `SCOPE_reports.read`.
- Controller gọi `ReportService.findAll()`.
- `SecurityFilterChain` của ứng dụng được import/nạp vào test slice.
- Test dùng Spring Boot 3.4+ (Framework 6.2+) hoặc Boot 4.x.

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
@Import(SecurityConfig.class)
class ReportControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void readerCanGetReports() throws Exception {
        when(reportService.findAll()).thenReturn(List.of());

        mvc.perform(get("/api/reports"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_other")
    void wrongAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isForbidden());
    }
}
```

Đây là ví dụ khung; các import của `@WebMvcTest` trong đoạn code dùng package Boot 3.4/3.5. Với Boot 4.x, thay bằng `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` như mục 5.2. Thay `ReportController`, `ReportService`, `SecurityConfig` và phương thức `findAll()` bằng class thật trong ứng dụng. `@MockitoBean` chỉ thay dependency service. **Authentication và authorization vẫn được thực thi bởi Security filter chain** nhờ `@WithMockUser` và cấu hình security được nạp.

### 5.1. Vì sao test slice thường cần mock bean?

`@WebMvcTest` chỉ nạp một lát cắt MVC, không tự nạp toàn bộ service/repository của ứng dụng. Nếu controller có constructor dependency là `ReportService`, test có thể không khởi động vì thiếu bean. `@MockitoBean` tạo mock để controller có thể được khởi tạo và test tập trung vào HTTP mapping/authorization.

Điều này không có nghĩa mock service sẽ kiểm tra logic service. Muốn kiểm tra logic service, hãy viết test riêng dùng bean thật trong Spring context hoặc unit test phù hợp.

### 5.2. Boot 4.x và package annotation

Trong Boot 4.x, ưu tiên các test starter theo stack (ví dụ MVC test hoặc WebFlux test) và annotation của Spring Framework:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Không cố dùng lại:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
```

Các annotation Boot cũ đã deprecated for removal trong Boot 3.4 và được loại khỏi thế hệ Boot 4. Nếu code còn dùng, thay bằng annotation Framework và điều chỉnh khác biệt về attribute/target, không chỉ thay tên class trong import.

**Package của test slice Boot cũng thay đổi ở Boot 4.** Với Boot 3.4/3.5, import:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
```

Với Boot 4.x, dùng package theo module web tương ứng:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
```

Đây là hai lựa chọn theo phiên bản, không import cả hai nhóm trong cùng một lớp. Boot 4 tách test auto-configuration theo stack; ngoài việc cập nhật package, phải có starter test MVC/WebFlux tương ứng trong test classpath.

## 6. Dự án Boot 3.0–3.3: dùng `@MockBean`/`@SpyBean`

Ở Boot 3.0–3.3, Spring Framework chưa có `@MockitoBean`/`@MockitoSpyBean` (được thêm từ Framework 6.2). Dùng annotation Boot cũ:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

@WebMvcTest(ReportController.class)
class LegacyReportControllerTest {

    @MockBean
    ReportService reportService;

    @SpyBean
    ReportPolicy reportPolicy;
}
```

Đoạn trên chỉ minh họa vị trí khai báo; test slice phải có bean thật `ReportPolicy` để spy, và controller/service phải phù hợp với cấu hình test. Nếu chỉ cần mock một dependency không được nạp trong slice, `@MockBean` sẽ tạo mock để thỏa mãn injection.

Khi nâng Boot 3.3 lên 3.4, có thể chuyển từng lớp test sang annotation Framework mới. Nếu cần duy trì code cũ trong thời gian chuyển tiếp, annotation Boot vẫn có thể hoạt động ở Boot 3.4 nhưng compiler sẽ cảnh báo deprecated.

## 7. Khác biệt API cần xem khi migrate

Không phải mọi thuộc tính của hai thế hệ có thể đổi tên máy móc.

| API cũ (Boot) | API mới (Framework) | Ghi chú chuyển đổi |
|---|---|---|
| `@MockBean` | `@MockitoBean` | Mock bean trong ApplicationContext |
| `@SpyBean` | `@MockitoSpyBean` | Spy/wrap bean thật |
| `classes = {...}` | `types = {...}` | Khai báo type khi dùng annotation ở cấp class |
| `name = "beanName"` | `name = "beanName"` | Chọn bean theo tên |
| `value = SomeType.class` (alias tùy cách dùng) | Field type hoặc `types` | Nên ưu tiên field để dễ hiểu |
| `answer = Answers...` | `answers = Answers...` | Tên thuộc tính mới ở dạng số nhiều |
| `reset = MockReset.AFTER` | `reset = MockReset.AFTER` | Cả hai hỗ trợ reset mock/spy |
| `extraInterfaces`, `serializable` | Có thuộc tính tương ứng trên `@MockitoBean` | Kiểm tra Javadoc theo Framework minor đang dùng |
| Cách đặt trên `@Configuration` của Boot cũ | Không hoàn toàn tương đương | Chuyển annotation về test class/field hoặc dùng cách khai báo mới được hỗ trợ |

Khi migrate, tìm toàn bộ import:

```text
org.springframework.boot.test.mock.mockito.MockBean
org.springframework.boot.test.mock.mockito.SpyBean
org.springframework.boot.test.mock.mockito.MockBeans
org.springframework.boot.test.mock.mockito.SpyBeans
```

Sau đó thay từng trường hợp và kiểm tra:

1. Annotation nằm ở field, class hay `@Configuration`?
2. Bean được xác định bằng type hay name?
3. Có nhiều candidate cùng kiểu không?
4. Mock có đang được dùng để thay bean mà test cần kiểm chứng logic thật không?
5. Test context có còn load cùng security chain không?
6. Dependency Framework `spring-test` có ít nhất 6.2 để cung cấp API mới không?

Không nên chạy thay thế chuỗi tự động toàn dự án mà không xem từng trường hợp: cách khai báo và semantics của API mới có khác biệt.

## 8. Dùng mock/spy mà vẫn kiểm chứng Spring Security

Đây là phần đặc biệt quan trọng với mô-đun Spring Security Testing. Mock và spy giúp cô lập **collaborator**, còn test security phải giữ lại **đối tượng và cơ chế đang cần kiểm tra**.

### 8.1. Mock repository/client, giữ nguyên service có method security

Giả sử `ReportService` là bean có `@PreAuthorize`, còn `ReportRepository` chỉ là dependency đọc dữ liệu:

```java
@Service
class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public List<Report> findAll() {
        return repository.findAll();
    }
}
```

Test method security nên **mock repository**, nhưng inject `ReportService` thật từ context:

```java
@SpringJUnitConfig(classes = {ServiceConfig.class, SecurityConfig.class})
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @MockitoBean
    ReportRepository repository;

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void readerCanRead() {
        when(repository.findAll()).thenReturn(List.of());
        assertEquals(0, reportService.findAll().size());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_other")
    void wrongScopeIsRejected() {
        assertThrows(AccessDeniedException.class,
                () -> reportService.findAll());
    }
}
```

Ví dụ cần các import JUnit, Spring Security Test, Mockito, `AccessDeniedException`, `assertThrows` và cấu hình bật `@EnableMethodSecurity`. Điểm mấu chốt: `ReportService` vẫn là bean thật do Spring tạo và được proxy để áp dụng `@PreAuthorize`; chỉ repository là mock.

### 8.2. Vì sao không nên mock chính bean có method security?

`@MockitoBean` thay thế bean bằng một Mockito mock. Mock được đăng ký như một đối tượng thay thế và không chạy logic thật của bean. Trong cơ chế bean override, đối tượng mock được thay trực tiếp và có thể **không được bọc trong Spring AOP proxy** như bean ban đầu.

Do đó, nếu thay `ReportService` có `@PreAuthorize` bằng `@MockitoBean ReportService reportService`, rồi gọi `reportService.findAll()`, bạn có thể đang gọi trực tiếp mock thay vì method qua proxy security. Test ấy không chứng minh `@PreAuthorize` hoạt động.

Quy tắc thực hành:

- Muốn kiểm tra method security của `ReportService`: giữ `ReportService` thật, mock `ReportRepository` hoặc API bên ngoài.
- Muốn kiểm tra controller HTTP: giữ controller và security filter chain, mock service collaborator mà controller gọi.
- Muốn kiểm tra hành vi của một service thật nhưng cần quan sát lời gọi: cân nhắc spy đúng bean, xác minh proxy/AOP vẫn hoạt động và không làm side effect.
- Nếu mục tiêu là kiểm thử bản thân mock, đó là kiểm tra orchestration của lớp gọi; không được kết luận logic của bean mock đã được kiểm thử.

### 8.3. Spy và AOP proxy

`@MockitoSpyBean` wrap một instance của bean thật. Với bean vốn được Spring AOP proxy, proxy vẫn có thể bao quanh spy theo cơ chế Framework hỗ trợ. Dù vậy, hãy kiểm tra hành vi thực tế khi có `@Transactional`, `@PreAuthorize`, `@Cacheable` hoặc advisor tùy chỉnh.

Khi spy một bean có side effect, tránh gọi thật trong lúc stubbing:

```java
doReturn(List.of()).when(reportService).findAll();
```

Không dùng spy như giải pháp mặc định cho mọi test. Mock collaborator thường dễ đọc và cô lập hơn; spy hữu ích khi cần giữ phần lớn hành vi thật nhưng phải kiểm soát một method cụ thể.

## 9. Dùng `@MockitoBean` với WebFlux

Annotation bean override mới của Spring Framework không phụ thuộc riêng vào Servlet. Nó thay bean trong `ApplicationContext`, vì vậy có thể dùng trong test context WebFlux nếu classpath và cấu hình test phù hợp.

Ví dụ khung test Reactive:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.mockito.Mockito.when;

@WebFluxTest(ReportHandler.class)
@Import(ReactiveSecurityConfig.class)
class ReportHandlerTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReportService reportService;

    @Test
    void analystCanRead() {
        when(reportService.findAll()).thenReturn(Flux.empty());

        client.mutateWith(mockUser("lan").roles("ANALYST"))
              .get().uri("/api/reports")
              .exchange()
              .expectStatus().isOk();
    }
}
```

Đây là ví dụ minh họa cho WebFlux, giả định handler gọi `ReportService` trả về `Flux<Report>`, security config yêu cầu role `ANALYST` và slice đã nạp handler/config cần thiết. Cần thêm import `Flux` và các type domain của ứng dụng. `@MockitoBean` thay service; `mockUser()` của Spring Security Test thiết lập user cho **Reactive request**. Hai API có vai trò khác nhau.

Với Boot 3.0–3.3, thay import `MockitoBean` bằng `org.springframework.boot.test.mock.mockito.MockBean`. Với Boot 3.4+ và 4.x, ưu tiên Framework annotation mới.

Trong ví dụ WebFlux ở trên, import `WebFluxTest` đang minh họa theo package Boot 3.x. Với Boot 4.x, dùng `org.springframework.boot.webflux.test.autoconfigure.WebFluxTest` và starter `spring-boot-starter-webflux-test`.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không resolve được `MockitoBean` | `spring-test` đang dưới 6.2 hoặc dependency test không có | Kiểm tra Framework version và test classpath |
| Không resolve được `MockBean` sau nâng Boot 4 | Annotation Boot cũ đã bị loại bỏ | Chuyển sang `org.springframework.test.context.bean.override.mockito.MockitoBean` |
| `@MockitoSpyBean` báo không tìm thấy bean | Không có bean thật hoặc có nhiều candidate | Nạp đúng configuration, dùng qualifier/name và bảo đảm chỉ một bean được chọn |
| `@MockitoBean(enforceOverride = true)` thất bại trong `@WebMvcTest` | Service bị loại khỏi web slice nên chưa tồn tại | Bỏ enforce nếu chủ đích tạo mock cho slice, hoặc chọn test context rộng hơn |
| Controller test không khởi động | Controller có dependency chưa được cung cấp | Mock collaborator bằng annotation phù hợp |
| Test method security luôn cho phép | Mock thay chính bean được bảo vệ, làm mất đường đi qua proxy | Mock dependency bên dưới, giữ bean service thật |
| Spy chạy method thật khi stubbing | Dùng `when(spy.method())` | Dùng `doReturn`, `doThrow`, `doNothing` khi phù hợp |
| Context cache tăng bất thường | Field names/qualifiers khác nhau giữa test class hoặc mock configuration khác nhau | Dùng qualifier và tên field nhất quán, gom cấu hình dùng chung |
| Mock bị giữ trạng thái giữa các test | Reset mode bị đổi hoặc test chạy song song với state chia sẻ | Kiểm tra `reset`, tránh chia sẻ state và thiết kế test độc lập |
| Test HTTP trả status không mong đợi | Bean mock chỉ giải quyết dependency; Security chain/policy có thể chưa được nạp | Kiểm tra `@Import`, filter chain, `@WithMockUser` hoặc mutator theo stack |

### 10.1. Cảnh báo khi dùng annotation trên context hierarchy

Nếu test dùng `@ContextHierarchy`, các bean override mới mặc định có thể được áp dụng trên nhiều tầng context. Khi chỉ muốn mock bean ở một tầng cụ thể, dùng thuộc tính `contextName` trùng với tên cấu hình `@ContextConfiguration(name = "...")`. Đây là tình huống nâng cao; chỉ cấu hình khi dự án thực sự có context hierarchy.

### 10.2. Reset mock và thứ tự test

Các annotation mới mặc định reset mock/spy sau mỗi test method (`MockReset.AFTER`). Nếu thay đổi chế độ reset, hãy bảo đảm test không phụ thuộc vào lời gọi hoặc stub còn lại từ method trước. Với test chạy song song, tránh chia sẻ một mock mutable giữa các test mà không có cô lập phù hợp.

## 11. Checklist chọn và migrate API

Trước khi viết hoặc chuyển annotation, kiểm tra:

| Câu hỏi | Quyết định |
|---|---|
| Boot 3.0–3.3 / Framework 6.0–6.1? | Dùng `@MockBean`/`@SpyBean` của Boot hoặc Mockito thủ công |
| Boot 3.4–3.5 / Framework 6.2? | Ưu tiên `@MockitoBean`/`@MockitoSpyBean`; API Boot cũ còn deprecated trong giai đoạn chuyển |
| Boot 4.x / Framework 7.x? | Dùng API Framework mới; loại bỏ import Boot cũ |
| Không dùng Boot nhưng Framework 6.2+? | Dùng annotation mới từ `spring-test` và thêm Mockito test dependency |
| Cần mock bean có tồn tại bắt buộc? | `@MockitoBean(enforceOverride = true)` |
| Cần spy bean thật? | `@MockitoSpyBean`, bảo đảm đúng một candidate |
| Có nhiều bean cùng type? | `@Qualifier` hoặc tên bean rõ ràng |
| Test kiểm tra method security? | Giữ service được bảo vệ là bean thật; mock collaborator bên dưới |
| Test là Servlet hay Reactive? | Chọn `MockMvc`/Servlet mutators hoặc `WebTestClient`/Reactive mutators riêng |
| Test trả status sai? | Kiểm tra security chain và policy, không kết luận ngay do annotation mock |

## 12. Bài tập thực hành

Giả sử ứng dụng có:

- `ReportController` nhận HTTP request.
- `ReportService` có `@PreAuthorize("hasAuthority('SCOPE_reports.read')")`.
- `ReportRepository` truy xuất dữ liệu.
- `SecurityFilterChain` bảo vệ endpoint `GET /api/reports`.

Thực hiện các bước:

1. Tạo test service dùng Spring context, inject `ReportService` thật và mock `ReportRepository`. Viết một ca có `SCOPE_reports.read` được phép, một ca thiếu scope bị từ chối.
2. Tạo `@WebMvcTest(ReportController.class)`, import Security configuration, mock `ReportService` và kiểm tra anonymous/đúng scope/sai scope.
3. Nếu dự án dùng Boot 3.3, thực hiện bằng `@MockBean`; nâng test stack lên Boot 3.4/Framework 6.2 rồi chuyển sang `@MockitoBean`.
4. Tạo một spy cho bean policy không gây side effect, xác minh một method được gọi; thử stubbing bằng `doReturn(...)`.
5. Thay mock bean bằng `@MockitoBean(enforceOverride = true)` trong full context và quan sát kết quả khi bean thật tồn tại/không tồn tại.
6. Nêu rõ test nào kiểm tra HTTP filter chain, test nào kiểm tra method security, test nào chỉ kiểm tra controller orchestration.

**Tiêu chí hoàn thành:** người học chọn đúng annotation theo version, không mock mất bean cần kiểm tra security, và giải thích được vì sao mock service trong controller slice không thay thế test method security của service.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework — `@MockitoBean` và `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): chiến lược override, qualifier, context hierarchy, singleton và AOP proxy.
- [Spring Framework 6.2 — `@MockitoBean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): thuộc tính, package và điều kiện sử dụng.
- [Spring Framework 6.2 — `@MockitoSpyBean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html): spy bean và quy tắc chọn candidate.
- [Spring Boot 3.4 Release Notes — Deprecation of `@MockBean` and `@SpyBean`](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): mốc deprecated và các khác biệt khi chuyển.
- [Spring Boot 3.4 — `@MockBean` Javadoc](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): package cũ, deprecated since 3.4.0 for removal in 4.0.0.
- [Spring Boot 4 — `@WebMvcTest` Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/WebMvcTest.html) và [`@WebFluxTest` Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webflux/test/autoconfigure/WebFluxTest.html): package test slice mới theo stack.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html) và [Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): cách kết hợp bean mock với test authentication/authorization.

> **Ghi nhớ:** `@MockitoBean` và `@MockitoSpyBean` giải quyết việc thay thế hoặc quan sát **bean của ứng dụng** trong test context. `@WithMockUser`, `jwt()`, `mockJwt()` và các security mutator giải quyết **danh tính và request bảo mật**. Muốn một test Spring Security có ý nghĩa, phải chọn đúng công cụ cho từng lớp và giữ lại thành phần security mà test đang cần chứng minh.
