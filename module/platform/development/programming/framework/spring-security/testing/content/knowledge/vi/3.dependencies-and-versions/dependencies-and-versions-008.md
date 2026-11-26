# `@MockitoBean` và `@MockitoSpyBean` khi phiên bản hỗ trợ

Từ Spring Framework 6.2, Spring Test cung cấp `@MockitoBean` và `@MockitoSpyBean` để thay thế hoặc bọc bean trong `ApplicationContext` bằng Mockito mock/spy. Hai annotation này hữu ích khi kiểm thử controller, service và chính sách Spring Security: ta có thể thay repository hoặc dịch vụ bên ngoài để cô lập test, đồng thời giữ lại bean thật đang cần kiểm tra.

Tuy nhiên, không phải mọi phiên bản Spring đều có các annotation này. Spring Boot 3.4 là thế hệ đầu tiên đưa Spring Framework 6.2 vào hệ sinh thái Boot; Boot 3.0–3.3 vẫn dùng Framework 6.0/6.1 và cần API cũ hoặc cách tạo mock khác. Boot 3.4 cũng đánh dấu `@MockBean`/`@SpyBean` của Boot là deprecated để chuyển sang annotation Framework mới; Boot 4 đã loại bỏ hai annotation cũ.

Bài thuộc chương **Phụ thuộc và phiên bản** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun hướng dẫn kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và các ca được phép hoặc bị từ chối.

Mục tiêu của bài là giúp bạn **xác định phiên bản có hỗ trợ**, chọn đúng cách khai báo mock/spy, và tránh làm mất cơ chế bảo mật mà test đang muốn chứng minh.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định khi nào `@MockitoBean` và `@MockitoSpyBean` có mặt trong classpath.
2. Chọn đúng annotation theo Spring Boot/Spring Framework đang dùng.
3. Phân biệt mock thay thế bean với spy bọc bean thật.
4. Sử dụng field-level và type-level declaration, `@Qualifier`, bean name, `types`, `enforceOverride` và `contextName` đúng với patch version hỗ trợ.
5. Dùng mock/spy trong test Servlet hoặc Reactive mà vẫn giữ Security filter chain.
6. Hiểu tác động của bean override lên Spring AOP, `@PreAuthorize`, `@Transactional`, `@Cacheable` và context cache.
7. Chuyển dần từ `@MockBean`/`@SpyBean` mà không giả định hai thế hệ có toàn bộ semantics giống nhau.

## 2. Kiểm tra phiên bản trước khi import

Các annotation mới thuộc **Spring Framework Test**, không thuộc `spring-security-test` và cũng không phải annotation riêng của Spring Boot.

| Nền tảng | Spring Framework thường đi kèm | API có thể sử dụng |
|---|---|---|
| Spring Boot 3.0–3.3 | Framework 6.0–6.1 | Chưa có `@MockitoBean`/`@MockitoSpyBean`; dùng `@MockBean`/`@SpyBean` của Boot hoặc Mockito thủ công |
| Spring Boot 3.4–3.5 | Framework 6.2.x | Có `@MockitoBean`/`@MockitoSpyBean`; `@MockBean`/`@SpyBean` deprecated từ Boot 3.4.0 |
| Spring Boot 4.0 | Framework 7.0.x | Dùng `@MockitoBean`/`@MockitoSpyBean`; annotation Boot cũ đã bị loại bỏ |
| Spring Framework thuần 6.2+ | Framework 6.2.x | Có annotation mới trong `spring-test`, không cần Spring Boot |
| Spring Framework thuần 6.0/6.1 | Framework 6.0/6.1 | Chưa có bean override annotations mới |

Bảng cho biết **dòng tương thích**, không thay thế việc kiểm tra dependency đã resolve. Một dự án có thể tự override `spring-test` hoặc dùng BOM riêng; hãy xác minh version thực tế thay vì chỉ nhìn số phiên bản trong plugin Boot.

### 2.1. Package và artifact

Hai annotation nằm trong package:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Artifact cung cấp chúng là:

```text
org.springframework:spring-test
```

Trong dự án Boot, `spring-boot-starter-test` thường kéo Spring Test và Mockito vào test classpath. Với dự án Framework thuần, cần khai báo `spring-test` và Mockito phù hợp bằng dependency management của dự án. `spring-security-test` là dependency riêng cho `@WithMockUser`, `jwt()`, `mockJwt()`, CSRF và các tiện ích security.

**Không tìm hai annotation này trong package** `org.springframework.security.test...`. Chúng là cơ chế thay bean của Spring TestContext; Spring Security Test chỉ tham gia khi test cần tạo authentication hoặc mô phỏng request bảo mật.

### 2.2. Mốc API theo patch version của Framework 6.2

Các annotation cơ bản có từ **Spring Framework 6.2.0**. Tuy vậy, một số thuộc tính được bổ sung ở các bản maintenance sau:

| API/thuộc tính | `@MockitoBean` | `@MockitoSpyBean` | Ý nghĩa |
|---|---:|---:|---|
| Annotation cơ bản | 6.2.0 | 6.2.0 | Khai báo mock/spy trên field hoặc type |
| `types` cho type-level declaration | 6.2.2 | 6.2.3 | Chỉ rõ kiểu bean khi annotation đặt trên class/interface |
| `contextName` | 6.2.6 | 6.2.6 | Giới hạn override vào một tầng trong `@ContextHierarchy` |
| Đặt annotation trên constructor parameter | Không có trong 6.2.x | Không có trong 6.2.x | Được hỗ trợ trong Spring Framework 7.1; không áp dụng mặc định cho Boot 4.0 dùng Framework 7.0 |

Điều này có ý nghĩa thực tế: một dự án Boot 3.4.0 có thể đang quản lý Framework 6.2.0, do đó **không thể mặc định** dùng thuộc tính `types` hoặc `contextName`. Các bản Boot maintenance sau có thể quản lý Framework 6.2.x mới hơn; hãy xem version của `spring-test` trước khi copy ví dụ.

Trong Spring Framework 7.x, các annotation tiếp tục được hỗ trợ. API có thể mở rộng theo minor release; ví dụ tài liệu Framework 7.1 bổ sung khả năng đặt annotation trên constructor parameter. Không áp dụng khả năng của 7.1 cho mọi dự án Boot 4.0 đang dùng Framework 7.0.

## 3. Phân biệt `@MockitoBean` và `@MockitoSpyBean`

| Tiêu chí | `@MockitoBean` | `@MockitoSpyBean` |
|---|---|---|
| Đối tượng được tạo | Mockito mock | Mockito spy bọc instance thật |
| Chiến lược override | `REPLACE_OR_CREATE` | `WRAP` |
| Khi bean chưa tồn tại | Mặc định tạo mock mới | Không thể wrap nếu không có bean thật |
| Khi có nhiều candidate | Chọn bằng type, qualifier hoặc tên | Phải xác định đúng một candidate để wrap |
| Hành vi method chưa stub | Trả kết quả theo cấu hình mock/Mockito answer | Chạy logic thật của bean |
| Dùng để | Cô lập collaborator, đặt kết quả trả về | Quan sát lời gọi hoặc stub một phần bean thật |
| Rủi ro chính | Thay mất logic/AOP của bean thật | Method thật có thể gây side effect; stubbing qua proxy cần cẩn trọng |

### 3.1. Mock: thay bean bằng một đối tượng giả lập

```java
@MockitoBean
private ReportRepository reportRepository;
```

Spring tìm bean theo kiểu field `ReportRepository`. Nếu tìm được bean phù hợp, bean đó được thay bằng Mockito mock. Nếu không có bean phù hợp, mặc định Spring tạo mock mới và đăng ký trong context.

Đây là lựa chọn phù hợp khi test controller hoặc service cần một collaborator có kết quả do test kiểm soát:

```java
when(reportRepository.findAll()).thenReturn(List.of("Q4"));
```

Test không gọi logic truy cập database thật. Nó chỉ xác nhận lớp đang kiểm thử sử dụng collaborator đúng cách và phản hồi theo dữ liệu được cung cấp.

### 3.2. Spy: giữ logic thật và theo dõi lời gọi

```java
@MockitoSpyBean
private ReportPolicy reportPolicy;
```

Spring lấy instance bean thật và bọc nó bằng Mockito spy. Những method chưa được stub tiếp tục chạy logic thật; test có thể xác minh lời gọi:

```java
verify(reportPolicy).canRead("annual-report");
```

Spy chỉ phù hợp khi bean thật đã được đăng ký trong context và có đúng một candidate phù hợp. Nếu bean không tồn tại hoặc có nhiều bean cùng kiểu mà không có qualifier/name đủ rõ, quá trình tạo context sẽ thất bại.

Khi stub một spy, `when(spy.method()).thenReturn(...)` có thể gọi method thật ngay trong lúc cấu hình stub. Nếu method có side effect, dùng:

```java
doReturn(true).when(reportPolicy).canRead("annual-report");
doThrow(new IllegalStateException()).when(reportPolicy).refresh();
```

## 4. Khai báo trên field: lựa chọn dễ dùng nhất

Field-level declaration được hỗ trợ từ Framework 6.2.0 và là cách đơn giản nhất để bắt đầu:

```java
@SpringJUnitConfig(TestConfig.class)
class ReportServiceTest {

    @MockitoBean
    private ReportRepository reportRepository;

    @MockitoSpyBean
    private ReportPolicy reportPolicy;
}
```

Spring suy ra kiểu bean từ kiểu field. Nếu có nhiều candidate, dùng `@Qualifier`:

```java
@MockitoBean
@Qualifier("archiveRepository")
private ReportRepository repository;
```

Khi không có `@Qualifier`, **tên field** có thể được dùng làm qualifier dự phòng. Có thể chọn bean bằng tên rõ ràng:

```java
@MockitoBean(name = "archiveRepository")
private ReportRepository repository;
```

Với annotation trên field, không khai báo `types`; kiểu field đã cho biết bean type. Nếu một test suite có nhiều lớp test cùng override một bean, hãy giữ tên field và qualifier nhất quán. Qualifier tham gia tạo context cache key; tên khác nhau không cần thiết có thể khiến Spring tạo thêm context và làm suite chậm hơn.

## 5. Type-level declaration: chỉ dùng khi patch version hỗ trợ

Đặt annotation ở cấp class hữu ích khi nhiều test cần cùng một tập mock. Tuy nhiên, type-level declaration phải chỉ rõ loại bean qua thuộc tính `types`, và thuộc tính này được bổ sung sau bản 6.2.0.

### 5.1. `@MockitoBean(types = ...)`

Từ **Spring Framework 6.2.2**:

```java
@SpringJUnitConfig(TestConfig.class)
@MockitoBean(types = {
    ReportRepository.class,
    AuditClient.class
})
class ReportControllerTest {
    // Hai bean mock được đăng ký cho context của lớp test.
}
```

Nếu muốn chọn một bean theo tên:

```java
@MockitoBean(
    name = "archiveRepository",
    types = ReportRepository.class
)
class ArchiveControllerTest {
}
```

Khi chỉ định `name`, `types` chỉ được chứa **một kiểu**. Type-level declaration cũng có thể dùng lặp lại nhiều lần hoặc được đóng gói thành meta-annotation để tái sử dụng.

### 5.2. `@MockitoSpyBean(types = ...)`

Thuộc tính `types` của `@MockitoSpyBean` có từ **Spring Framework 6.2.3**:

```java
@SpringJUnitConfig(TestConfig.class)
@MockitoSpyBean(types = {
    ReportPolicy.class,
    AuditTrail.class
})
class ReportPolicyTest {
}
```

Khác với mock, mỗi kiểu spy phải tương ứng với bean thật có trong context. Không dùng type-level spy để tạo một bean chưa tồn tại. Nếu có nhiều bean cùng kiểu, cung cấp tên bean rõ ràng và đảm bảo chỉ có một candidate phù hợp.

### 5.3. Dùng meta-annotation để chia sẻ cấu hình

Khi các lớp test có cùng tập mock, có thể tạo annotation riêng:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@MockitoBean(types = {
    ReportRepository.class,
    AuditClient.class
})
public @interface SharedReportMocks {
}
```

Sau đó:

```java
@SpringJUnitConfig(TestConfig.class)
@SharedReportMocks
class ReportApiTest {
}
```

Cách này phù hợp với Framework 6.2.2 trở lên vì cần thuộc tính `types`. Nếu project chỉ có Framework 6.2.0/6.2.1, dùng field-level annotation hoặc nâng Framework lên patch có hỗ trợ; không copy ví dụ type-level rồi chỉ thêm dependency Mockito.

## 6. `enforceOverride`: bắt buộc bean thật phải tồn tại

Mặc định `@MockitoBean` dùng chiến lược `REPLACE_OR_CREATE`: nếu bean tồn tại thì thay thế, nếu chưa tồn tại thì tạo mock mới. Điều này rất tiện với test slice, nơi một số service/repository bị loại khỏi context.

Khi muốn bảo đảm test đang thay đúng một bean production đã được cấu hình, dùng:

```java
@MockitoBean(enforceOverride = true)
private ReportRepository reportRepository;
```

Với `enforceOverride = true`, chiến lược là `REPLACE`: nếu không tìm thấy bean cần thay, Spring báo lỗi thay vì âm thầm tạo mock mới.

| Tình huống | Nên chọn |
|---|---|
| `@WebMvcTest` không nạp repository nhưng controller cần dependency để khởi tạo | Mặc định `@MockitoBean` để tạo mock |
| Full application context phải có repository production | `@MockitoBean(enforceOverride = true)` để phát hiện thiếu bean |
| Muốn quan sát logic thật của policy bean | `@MockitoSpyBean` và bean thật phải tồn tại |
| Muốn kiểm tra cấu hình bean bị thiếu | `enforceOverride = true` trong context có chủ đích nạp bean |

`enforceOverride` thuộc `@MockitoBean`; không áp dụng cho `@MockitoSpyBean`, vì spy vốn đòi hỏi bean thật để wrap.

## 7. `contextName` khi dùng context hierarchy

Trong test có `@ContextHierarchy`, một số cấu hình tạo nhiều tầng `ApplicationContext`. Theo mặc định, bean override có thể được áp dụng lên các tầng context trong hierarchy. Điều này đôi khi khiến mock xuất hiện ở tầng không mong muốn.

Từ **Spring Framework 6.2.6**, cả `@MockitoBean` và `@MockitoSpyBean` hỗ trợ `contextName`. Giá trị phải khớp với tên khai báo ở `@ContextConfiguration(name = "...")`:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
@SpringJUnitConfig
class WebSecurityTest {

    @MockitoBean(contextName = "root")
    private IdentityClient identityClient;
}
```

Ví dụ minh họa cách gắn mock vào tầng `root`; cấu trúc test thực tế cần khai báo hierarchy và bootstrap phù hợp với dự án. Nếu Framework đang ở 6.2.0–6.2.5, không dùng thuộc tính `contextName`; cân nhắc tổ chức test context khác hoặc nâng Framework patch.

## 8. Ví dụ Spring Security: mock collaborator nhưng giữ bean được bảo vệ

Đây là quy tắc quan trọng nhất khi dùng mock/spy trong test bảo mật: **mock dependency mà bean đang dựa vào; giữ nguyên bean có chính sách Security cần kiểm chứng**.

Giả sử `ReportService` có `@PreAuthorize` và gọi `ReportRepository`:

```java
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public List<String> findAll() {
        return repository.findAll();
    }
}
```

Test method security có thể dùng `@MockitoBean` cho repository, trong khi inject `ReportService` thật từ Spring context:

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(ReportServiceSecurityTest.Config.class)
class ReportServiceSecurityTest {

    @Autowired
    private ReportService reportService;

    @MockitoBean(enforceOverride = true)
    private ReportRepository repository;

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void readerCanReadReports() {
        when(repository.findAll()).thenReturn(List.of("Q4"));

        assertEquals(List.of("Q4"), reportService.findAll());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_other")
    void wrongScopeIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> reportService.findAll());
    }

    @Configuration
    @EnableMethodSecurity
    static class Config {
        @Bean
        ReportRepository reportRepository() {
            return new ReportRepository() {
                @Override
                public List<String> findAll() {
                    return List.of();
                }
            };
        }

        @Bean
        ReportService reportService(ReportRepository repository) {
            return new ReportService(repository);
        }
    }
}
```

Trong ví dụ này:

1. `@SpringJUnitConfig` tạo Spring TestContext và tích hợp JUnit Jupiter.
2. `@EnableMethodSecurity` bật xử lý `@PreAuthorize`.
3. `ReportService` vẫn là bean thật do Spring quản lý và được proxy theo cấu hình method security.
4. `@MockitoBean(enforceOverride = true)` thay đúng bean repository có trong cấu hình.
5. `@WithMockUser` tạo authentication cho test; authority đúng được phép, authority sai bị từ chối.

Nếu thay chính `ReportService` bằng `@MockitoBean`, method thật có thể không chạy và Spring AOP advice như `@PreAuthorize` không còn được kiểm chứng. Test khi ấy chỉ đang gọi Mockito mock, không chứng minh chính sách method security.

## 9. Dùng trong test MVC và WebFlux

Các annotation bean override thuộc Spring TestContext, do đó không có phiên bản Servlet riêng và Reactive riêng. Chúng thay bean trong `ApplicationContext`; phần khác biệt nằm ở HTTP test client và security mutator.

### 9.1. MVC với `@WebMvcTest` và `MockMvc`

Với controller slice, service thường không được nạp. Có thể mock service để controller được khởi tạo, đồng thời import Security configuration cần kiểm tra:

Boot 3.4/3.5:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

Boot 4.x:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Chỉ dùng một import phù hợp với phiên bản đang chạy. Đoạn test bên dưới là phần thân minh họa; các import Mockito, MockMvc request builder, matcher và Spring Security Test được bổ sung theo ứng dụng.

```java
@WebMvcTest(ReportController.class)
@Import(SecurityConfig.class)
class ReportControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void readerCanCallEndpoint() throws Exception {
        when(reportService.findAll()).thenReturn(List.of("Q4"));

        mvc.perform(get("/api/reports"))
           .andExpect(status().isOk());
    }
}
```

Ở đây controller và security chain được giữ lại, còn service được mock vì mục tiêu là kiểm tra HTTP mapping/authorization ở lớp web. Nếu cần kiểm tra `@PreAuthorize` trên chính `ReportService`, hãy viết một test khác với service thật như mục 8.

### 9.2. Reactive với `@WebFluxTest` và `WebTestClient`

Cùng nguyên tắc áp dụng cho WebFlux:

Boot 3.4/3.5:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
```

Boot 4.x:

```java
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
```

Chỉ dùng một import theo phiên bản; ví dụ dưới đây dùng một WebFlux controller:

```java
@WebFluxTest(ReportController.class)
@Import(ReactiveSecurityConfig.class)
class ReportControllerTest {

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

Đoạn code minh họa cho WebFlux: `ReportController` và `ReportService` là các kiểu của ứng dụng; thêm import Reactor/Mockito/Spring Security Test phù hợp. `@MockitoBean` thay service trong context, còn `mockUser()` là mutator Reactive gắn danh tính vào request. Nếu muốn kiểm tra JWT scope, dùng `mockJwt()` theo đúng cấu hình `SecurityWebFilterChain`.

**Lưu ý khi dùng Boot 4:** package của các annotation test slice và starter MVC/WebFlux đã được tách theo module; tra Boot Reference/Javadoc của phiên bản đang dùng. Điều đó không làm thay đổi package của `@MockitoBean`, vốn vẫn thuộc `org.springframework.test.context.bean.override.mockito`.

## 10. AOP proxy, method security và spy

Bean override có tác động khác nhau đến Spring AOP:

- **`@MockitoBean`:** thay trực tiếp bean bằng mock. Mock là đối tượng thay thế và không được bọc bởi các bean post-processor như bean gốc. Vì thế các advice như `@PreAuthorize`, `@Transactional`, `@Cacheable` có thể không còn hiện diện trên bean mock.
- **`@MockitoSpyBean`:** wrap instance thật bằng spy. Nếu bean bình thường được Spring AOP proxy, proxy vẫn có thể được tạo và bọc quanh spy. Test thường nhận proxy, không nhất thiết nhận trực tiếp đối tượng spy bên trong.

Với method security, cách an toàn thường là **giữ service thật và mock repository/client**. Nếu cần spy service thật để kiểm tra lời gọi, xác minh test vẫn đi qua proxy và `@PreAuthorize` vẫn có tác dụng.

### 10.1. Stub spy có thể kích hoạt logic thật

Khi dùng:

```java
when(auditService.record(any())).thenReturn(true);
```

Mockito có thể gọi method thật trong lúc cấu hình stub. Nếu method ghi log, ghi database hoặc gửi request, side effect có thể xảy ra trước khi test bắt đầu.

Dùng `doReturn` hoặc `doThrow` để tránh gọi method thật lúc stubbing:

```java
doReturn(true).when(auditService).record(any());
doThrow(new IllegalStateException()).when(auditService).flush();
```

### 10.2. Spy nằm sau proxy có advice cache

Nếu bean có `@Cacheable`, việc stubbing trên proxy có thể khiến caching advice lưu kết quả rỗng trong lúc Mockito thiết lập stub. Khi đó các lời gọi sau có thể nhận giá trị cache thay vì đi tới spy.

Nếu gặp tình huống này:

1. Kiểm tra bean test đang inject là proxy hay spy target.
2. Cân nhắc vô hiệu hóa cache trong test bằng `NoOpCacheManager` hoặc test configuration.
3. Nếu cần stub trực tiếp target, có thể dùng `AopTestUtils.getUltimateTargetObject(...)` theo hướng dẫn Spring Framework.
4. Chỉ làm vậy khi thực sự hiểu advisor đang bọc bean; không bỏ proxy nếu mục tiêu test là method security hoặc transaction behavior.

## 11. Scope bean, FactoryBean và reset

### 11.1. Bean không phải singleton

Hành vi với bean prototype/scoped có khác biệt giữa các thế hệ Framework:

| Phiên bản | `@MockitoBean` | `@MockitoSpyBean` |
|---|---|---|
| Spring Framework 6.2.x | Chỉ override singleton bean; cố override non-singleton có thể phát sinh exception | Chỉ spy singleton bean; non-singleton không được hỗ trợ |
| Spring Framework 7.0.x | Non-singleton được thay bằng mock singleton; bean definition được chuyển thành singleton trong test | Non-singleton được chuyển thành singleton khi spy; không thể spy trực tiếp scoped proxy |

Vì vậy, nếu ứng dụng có request/session/prototype scoped bean, không suy luận rằng vòng đời của bean trong test vẫn giống production. Trong Framework 7.0, mock/spy non-singleton có thể bị chuyển thành singleton trong context test; riêng scoped proxy không thể được spy trực tiếp. Đọc đúng Reference/Javadoc theo Framework version và thiết kế test không phụ thuộc vào scope ngoài ý muốn.

### 11.2. Bean tạo bởi `FactoryBean`

Khi mock bean do `FactoryBean` tạo ra, Spring thay `FactoryBean` bằng singleton mock có kiểu của **đối tượng do factory tạo ra**. Khi spy, spy được tạo cho object do factory tạo ra, không phải bản thân `FactoryBean`. Điều này quan trọng khi test các client/adapter được tạo qua factory.

### 11.3. Reset mock/spy giữa các test

Mặc định, thuộc tính `reset` dùng `MockReset.AFTER`: mock/spy được reset sau mỗi test method. Việc reset giúp stub và invocation của test trước không rò sang test sau. Chỉ thay đổi reset mode khi có lý do rõ ràng; không viết test phụ thuộc vào lịch sử lời gọi của test khác.

## 12. Context cache, nested tests và context hierarchy

Hai annotation hỗ trợ khai báo trên field và type-level, có thể kế thừa qua superclass, enclosing class của `@Nested`, hoặc dùng như meta-annotation. Type-level declarations có thể lặp lại để đăng ký nhiều bean.

Các lưu ý:

- Dùng tên field và qualifier nhất quán giữa các test class để tránh tạo context cache key khác nhau không cần thiết.
- Khi dùng `@Nested`, kiểm tra chính sách `@NestedTestConfiguration` để biết annotation được kế thừa hay không.
- Khi dùng `@ContextHierarchy`, mặc định bean override có thể được áp dụng lên mọi tầng. Dùng `contextName` (Framework 6.2.6+) để giới hạn tầng phù hợp.
- Nếu cấu hình context thay đổi theo mock/qualifier, cache có thể tạo context mới. Tránh dùng nhiều biến thể tên bean chỉ để đặt tên field khác nhau.

## 13. Chuyển từ Boot `@MockBean`/`@SpyBean`

Spring Boot 3.4 đánh dấu `@MockBean` và `@SpyBean` là deprecated từ 3.4.0, với mục tiêu chuyển sang API của Spring Framework. Spring Boot 4 loại bỏ hỗ trợ annotation Boot cũ.

| Phiên bản | Hướng xử lý |
|---|---|
| Boot 3.0–3.3 | Giữ `@MockBean`/`@SpyBean` hoặc Mockito thủ công; Framework chưa có API mới |
| Boot 3.4–3.5 | Ưu tiên `@MockitoBean`/`@MockitoSpyBean`; API Boot cũ vẫn tồn tại nhưng deprecated |
| Boot 4.x | Bắt buộc chuyển sang annotation Framework mới hoặc giải pháp bean override khác |

Một khác biệt quan trọng: annotation cũ của Boot từng được dùng trên `@Configuration`/`@TestConfiguration` để khai báo tập mock dùng chung. Annotation Framework mới **không hỗ trợ cách đặt đó**. Thay vào đó, khai báo mock ở type-level trên test class bằng `types` (Framework 6.2.2+) hoặc tạo meta-annotation dùng `@MockitoBean`.

Ví dụ cấu hình mock dùng chung:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@MockitoBean(types = {ReportRepository.class, AuditClient.class})
public @interface SharedReportMocks {
}
```

Sau đó dùng:

```java
@SpringBootTest
@SharedReportMocks
class ReportIntegrationTest {
}
```

Trước khi migrate, tìm các import:

```text
org.springframework.boot.test.mock.mockito.MockBean
org.springframework.boot.test.mock.mockito.SpyBean
org.springframework.boot.test.mock.mockito.MockBeans
org.springframework.boot.test.mock.mockito.SpyBeans
```

Rà từng chỗ dùng annotation trên field, class hoặc configuration class. Nếu code cũ khai báo trên configuration class, phải thiết kế lại thành type-level declaration hoặc meta-annotation trên test class; không chỉ đổi tên import.

## 14. Dependency và cách xác minh phiên bản

Trong dự án Spring Boot, `spring-boot-starter-test` thường cung cấp Spring Test, JUnit Jupiter và Mockito. Với Boot 3.4+ hoặc Boot 4, dùng API Framework mới nếu version `spring-test` hỗ trợ. Với Boot 3.0–3.3, dùng API Boot cũ hoặc Mockito thủ công.

Dự án Framework thuần cần dependency test tương ứng:

```kotlin
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.mockito:mockito-core")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
```

Các version phải được quản lý bằng BOM/dependency constraints tương thích. Để xác minh version thật:

```bash
# Maven
./mvnw dependency:tree -Dscope=test

# Gradle
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
```

Nếu `spring-test` thấp hơn 6.2, import `MockitoBean` sẽ không tồn tại. Nếu `spring-test` là 6.2.0 nhưng code dùng `types` hoặc `contextName`, kiểm tra mốc patch tương ứng ở mục 2.2.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy `MockitoBean` | Framework dưới 6.2 hoặc `spring-test` không có trong test classpath | Kiểm tra dependency tree; Boot 3.0–3.3 chưa hỗ trợ |
| Không nhận thuộc tính `types` | Framework patch cũ hơn mốc hỗ trợ | Dùng field-level declaration hoặc nâng lên 6.2.2/6.2.3 tương ứng |
| Không nhận `contextName` | Framework dưới 6.2.6 | Bỏ thuộc tính hoặc nâng patch |
| Spy không tạo được | Bean thật chưa tồn tại hoặc có nhiều candidate | Nạp đúng context, qualifier/name, chỉ rõ bean duy nhất |
| Mock không thay bean production | Dependency được đăng ký trực tiếp chứ không phải bean, hoặc type/qualifier sai | Kiểm tra ApplicationContext và bean definition |
| Mock xuất hiện cạnh dependency hiện có | Dependency không phải bean được quản lý | Dùng bean registration phù hợp hoặc mock đúng abstraction |
| Method security không chạy | Đã mock chính service có `@PreAuthorize` | Giữ service thật, mock repository/client |
| Spy gây side effect khi stub | Dùng `when(spy.method())` | Dùng `doReturn`/`doThrow` hoặc thiết kế collaborator an toàn |
| Mock/spy làm context cache tăng | Field name/qualifier khác nhau giữa test class | Chuẩn hóa tên và qualifier |
| Boot 4 báo không tìm thấy `@MockBean` | Annotation Boot cũ đã bị loại bỏ | Dùng `@MockitoBean` từ Spring Test |
| Scoped bean test có hành vi khác production | Semantics non-singleton khác theo Framework version | Đọc tài liệu đúng version; không phụ thuộc scope trong test override |

## 16. Bài tập thực hành

Giả sử một dịch vụ báo cáo có:

- `ReportService.findAll()` được bảo vệ bởi `@PreAuthorize("hasAuthority('SCOPE_reports.read')")`.
- `ReportRepository` truy xuất dữ liệu.
- `AuditTrail` ghi nhận hoạt động.
- API MVC và WebFlux đều dùng chung service layer.

Thực hiện:

1. Xác định version `spring-test` của dự án. Nếu dưới 6.2, giải thích vì sao không thể import `@MockitoBean`.
2. Với Framework 6.2.0, viết field-level `@MockitoBean` cho repository và kiểm thử method security bằng service thật.
3. Với Framework 6.2.2+, tạo type-level mock bằng `types`; với 6.2.6+, thử `contextName` trong context hierarchy.
4. Dùng `@MockitoSpyBean` cho `AuditTrail`, xác minh method được gọi và dùng `doReturn` nếu cần stub.
5. Viết một MVC slice dùng mock service để kiểm tra HTTP authorization; viết một Reactive test dùng `mockUser()` hoặc `mockJwt()`.
6. Thay thử `ReportService` thật bằng mock và giải thích tại sao test không còn chứng minh được `@PreAuthorize`.
7. Nếu dự án nâng từ Boot 3.3 lên 3.4 hoặc Boot 4, liệt kê import, annotation target và dependency cần thay đổi.

**Tiêu chí hoàn thành:** người học xác định đúng API theo version, chọn mock hay spy theo mục đích, giữ nguyên bean security cần kiểm chứng và phân biệt test HTTP với test method security.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — `@MockitoBean` và `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): cách khai báo, chọn bean, override strategy và giới hạn.
- [Spring Framework 6.2 — `@MockitoBean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): thuộc tính và mốc `Since` của `types`/`contextName`.
- [Spring Framework 6.2 — `@MockitoSpyBean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html): spy candidate, thuộc tính và mốc patch.
- [Spring Framework 7.0 — Bean overriding in tests](https://docs.spring.io/spring/reference/7.0/testing/testcontext-framework/bean-overriding.html): cơ chế bean override trong Framework 7.
- [Spring Framework 7.0 — `@MockitoBean`/`@MockitoSpyBean`](https://docs.spring.io/spring/reference/7.0/testing/annotations/integration-spring/annotation-mockitobean.html): AOP proxy và semantics scoped bean ở Framework 7.
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): deprecated `@MockBean`/`@SpyBean`.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): loại bỏ annotation Boot cũ và cách chuyển sang API Framework.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html) và [Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): kết hợp mock bean với authentication/authorization test.

> **Ghi nhớ:** chỉ dùng `@MockitoBean`/`@MockitoSpyBean` khi `spring-test` trong test classpath đã hỗ trợ chúng. Mock collaborator để cô lập test; giữ bean có `@PreAuthorize` hoặc logic cần kiểm chứng ở dạng Spring-managed bean thật.
