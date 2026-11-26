# Context cache và tác động của cấu hình mock khác nhau

Trong một bộ kiểm thử Spring Security, hai lớp test có thể cùng chạy `MockMvc`, cùng gọi `GET /api/reports/r-1` và cùng giả lập Alice bằng `@WithMockUser`, nhưng một lớp khởi động Spring rất nhanh trong khi lớp còn lại mất nhiều thời gian tạo `ApplicationContext`. Một nguyên nhân thường gặp là **hai lớp có cấu hình mock bean khác nhau**, nên Spring TestContext không thể dùng cùng context đã cache. Ở chiều ngược lại, **hai test dùng lại cùng context** có thể vô tình chia sẻ trạng thái của mock, singleton bean, database hoặc HTTP session và tạo ra kết quả không ổn định.

Bài thuộc chương **Bộ kiểm thử và CI** của module **SPRING_SECURITY_TESTING**. Chúng ta sẽ phân tích cơ chế cache của Spring TestContext, cách `@MockitoBean`/`@MockBean` ảnh hưởng đến cache key, cách tổ chức test Servlet và Reactive bằng `spring-security-test`, `MockMvc`, `WebTestClient`, `@WithMockUser`, mock JWT/OAuth2/OIDC, và cách đo đạc trước khi tối ưu CI.

Mục tiêu không phải ép mọi lớp test dùng chung một context. **Cache hit chỉ có lợi nếu cấu hình thực sự tương đương và state giữa các test được cô lập**. Test kiểm tra sai policy để tiết kiệm vài giây khởi động là một tối ưu hóa không chấp nhận được.

## 1. Spring TestContext cache điều gì?

Khi một test dùng `@SpringBootTest`, `@WebMvcTest` hoặc `@WebFluxTest`, Spring TestContext Framework tạo `ApplicationContext` dựa trên cấu hình của test. Sau khi context khởi động thành công, framework có thể lưu nó trong một **static context cache** để lớp test khác có cấu hình tương đương dùng lại.

Ví dụ:

~~~text
ReportReadMvcTest         -> cấu hình A ─┐
                                        ├── context A (reuse nếu cùng cache key)
ReportRejectMvcTest       -> cấu hình A ─┘

ReportAuditMvcTest        -> cấu hình B ───── context B (mock thêm AuditGateway)

ReportJwtIntegrationTest  -> cấu hình C ───── context C (Resource Server profile)
~~~

Giới hạn quan trọng:

- Cache **tồn tại trong phạm vi một JVM/test process**. Các Gradle test worker, Maven Surefire fork hoặc CI job khác nhau không chia sẻ nguyên một Spring `ApplicationContext` in-memory.
- Cache dùng **khóa cấu hình**, không phải so tên lớp test hay đoán rằng hai test “trông giống nhau”.
- Khi một test method kết thúc, context được cache **không tự bị hủy**. Các singleton Spring bean trong context còn tồn tại để những test tiếp theo tái sử dụng.
- Cache có giới hạn dung lượng và cơ chế loại bỏ mục ít dùng gần đây. Khi quá nhiều cấu hình khác nhau, context có thể bị đóng rồi phải khởi động lại.
- `@DirtiesContext` có thể yêu cầu loại context ra khỏi cache; đó là công cụ cho test thật sự thay đổi trạng thái context, không phải cách dọn mock mặc định cho mọi test.

Spring TestContext mặc định dùng cache kích thước tối đa **32 context** (có thể cấu hình bằng `spring.test.context.cache.maxSize`). Con số này là **số context trong một JVM**, không phải số test method hay số request. Việc tăng giới hạn có thể giảm reload khi có rất nhiều tổ hợp cấu hình, nhưng cũng tăng mức dùng heap; cần đo trước khi thay đổi.

## 2. Cache key được hình thành từ những gì?

Theo mô hình cache của Spring TestContext, cấu hình context bao gồm các thành phần như:

| Thành phần cấu hình | Ví dụ | Khi nào có thể tạo context khác |
| --- | --- | --- |
| Configuration classes / locations | `@SpringBootTest(classes=...)`, `@ContextConfiguration` | Chọn class cấu hình khác |
| Context initializer/loader/parent | `@ContextConfiguration(initializers=...)`, context hierarchy | Test dùng cách khởi động hoặc cây context khác |
| Active profiles | `@ActiveProfiles("test")` so với `@ActiveProfiles("jwt")` | Bộ bean/properties hoạt động khác nhau |
| Test properties | `@TestPropertySource`, `@SpringBootTest(properties=...)` | Giá trị hoặc nguồn property cấu hình khác |
| Context customizers | Bean override từ `@MockitoBean`, `@MockitoSpyBean`, `@MockBean`; `@DynamicPropertySource` | Khác mock/spy hoặc phương thức cấu hình động |
| Web resource base path | `@WebAppConfiguration` và Servlet web context | Web test dùng path tài nguyên khác |
| Test slice/bootstrap | `@WebMvcTest`, `@WebFluxTest`, `@SpringBootTest` | Cấu hình bean và bộ lọc context khác nhau |

Đây là **khóa logic gồm nhiều phần**, không đơn thuần là một checksum của source test. Các annotation meta, bean qualifiers và cơ chế bootstrap cũng có thể đóng góp vào cấu hình tương đương.

~~~mermaid
flowchart TD
    A["Test class"] --> B["Merged context configuration"]
    B --> C["Classes, profiles, properties, customizers"]
    C --> D{"Context cache có cùng key?"}
    D -->|Có| E["Tái sử dụng ApplicationContext"]
    D -->|Không| F["Khởi tạo ApplicationContext mới"]
    F --> G["Lưu context vào cache"]
    G --> H["Thực thi test"]
    E --> H
    H --> I{"Context marked dirty?"}
    I -->|Có| J["Đóng/loại context khỏi cache"]
    I -->|Không| K["Giữ lại cho test tiếp theo"]
~~~

**Giá trị `@WithMockUser` không phải lý do thông thường để tạo context mới.** `@WithMockUser(username="alice")` và `@WithMockUser(username="bob")` thiết lập Authentication cho từng test qua Spring Security Test listener; chúng không thêm một định nghĩa bean mới vào `ApplicationContext`. Tương tự, `mvc.perform(...).with(user("alice"))` hay `webTestClient.mutateWith(mockUser("bob"))` chỉ thiết lập danh tính ở ranh giới request.

Ngược lại, `@MockitoBean` thay đổi **các bean có mặt trong Spring context** và được đưa vào context customization, nên cấu hình mock khác có thể tạo cache key khác.

## 3. @Mock, @MockitoBean, @MockBean và sự khác nhau quan trọng

| Công cụ | Tạo gì? | Có làm thay đổi Spring context? | Cách sử dụng phù hợp |
| --- | --- | --- | --- |
| Mockito `@Mock` | Mock trong test instance, do Mockito/JUnit quản lý | Không tự thêm/thay Spring bean | Unit test thuần, không cần Spring |
| Mockito `@InjectMocks` | Đối tượng thử được inject các mock theo Mockito | Không thay Spring context | Test business class đơn lẻ |
| Spring `@MockitoBean` | Bean override dùng Mockito trong Spring TestContext | **Có**, ảnh hưởng cấu hình context/cache key | Spring Framework 6.2+ và các bản Spring Boot tương thích |
| Spring `@MockitoSpyBean` | Spy của bean thật trong Spring context | **Có**, tùy bean và vị trí override | Cần quan sát hoặc stub một phần bean |
| Spring Boot `@MockBean` | Mock/bean replacement theo cơ chế Spring Boot cũ | **Có** | Dự án Spring Boot cũ trước khi chuyển sang `@MockitoBean` |
| `@WithMockUser`, `user()`, `mockJwt()` | Authentication cho test/request | Không tự thay bean cấu hình | Test quy tắc Security với identity giả lập |

**Lưu ý phiên bản:** `@MockitoBean` và `@MockitoSpyBean` thuộc Spring Framework Test từ **6.2**. Spring Boot **3.4** bắt đầu deprecate `@MockBean`/`@SpyBean` để hướng sang cơ chế mới; những ứng dụng còn dùng Spring Boot cũ hơn phải kiểm tra API hỗ trợ trước khi sao chép ví dụ. Đừng vừa khai báo cả `@MockBean` lẫn `@MockitoBean` cho cùng mục đích rồi cho rằng đó là hai cách tương đương hoàn toàn trong cache key.

Ví dụ unit test thuần Mockito, **không cache ApplicationContext**:

~~~java
@ExtendWith(MockitoExtension.class)
class ReportFacadeUnitTest {

    @Mock
    ReportStore store;

    @InjectMocks
    ReportFacade facade;

    @Test
    void returnsReportFromStore() {
        when(store.findById("r-1"))
            .thenReturn(Optional.of(new Report("r-1", "alice")));

        assertThat(facade.findById("r-1")).isPresent();
    }
}
~~~

`@Mock` là một mock bình thường của Mockito. Nếu chuyển đúng test này sang `@WebMvcTest` và muốn controller nhận mock từ dependency injection của Spring, chỉ `@Mock` không đủ: cần một bean override như `@MockitoBean` hoặc một test configuration tạo bean thích hợp.

## 4. Ứng dụng Servlet nhỏ dùng để nghiên cứu cache

Tạo một API có một dependency bên ngoài được giả lập trong HTTP slice test:

~~~java
public record Report(String id, String owner) {}

public interface ReportStore {
    Optional<Report> findById(String id);
}

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportStore store;

    public ReportController(ReportStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Report> get(@PathVariable String id) {
        return store.findById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Các import cần thiết gồm `Optional`, các annotation Spring MVC và `ResponseEntity`. Controller cố ý không chứa logic authentication; chúng ta sẽ kiểm tra bảo vệ HTTP bằng SecurityFilterChain:

~~~java
@Configuration
@EnableWebSecurity
class ReportHttpSecurity {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
~~~

Ví dụ dùng API Servlet với Spring Security hiện đại, HTTP Basic và request GET nên không phải xử lý CSRF ở ca đọc. Các import gồm `HttpMethod`, `@Configuration`, `@EnableWebSecurity`, `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `Customizer` và `AbstractHttpConfigurer`.

Đây là cấu hình dành cho mô hình test; trong ứng dụng thực, nếu `SecurityFilterChain` còn giới hạn các URL khác, cần bảo đảm test dùng đúng bean/config chính thức thay vì một chain lược bỏ chính sách cần kiểm chứng. Với test resource server JWT, phải dùng chain có `oauth2ResourceServer(...)` khi mục tiêu là xác minh token thật.

## 5. Hai lớp @WebMvcTest chia sẻ cùng cấu hình mock

Spring MVC slice nạp controller, MVC infrastructure và các bean được lựa chọn theo slice. Để kiểm tra security chain, có thể import cấu hình `ReportHttpSecurity`. Hai lớp dưới đây khai báo **cùng controller, cùng import và cùng bean override**:

~~~java
@WebMvcTest(controllers = ReportController.class)
@Import(ReportHttpSecurity.class)
class ReportReadMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportStore reportStore;

    @Test
    @WithMockUser(username = "alice",
                  authorities = "SCOPE_reports.read")
    void scopedUserCanReadReport() throws Exception {
        when(reportStore.findById("r-1"))
            .thenReturn(Optional.of(new Report("r-1", "alice")));

        mvc.perform(get("/api/reports/r-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }
}
~~~

~~~java
@WebMvcTest(controllers = ReportController.class)
@Import(ReportHttpSecurity.class)
class ReportDeniedMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportStore reportStore;

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void authenticatedUserWithoutScopeGetsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports/r-1"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/reports/r-1"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Trong dự án Spring Boot 3.4+/Spring Framework 6.2+, `@MockitoBean` có thể thay `ReportStore` mà controller yêu cầu. Nếu ứng dụng đang ở phiên bản khác, chọn cơ chế bean override đúng phiên bản.

Hai lớp **có thể cache-hit** vì cấu hình tương đương; việc Alice/Bob khác nhau qua `@WithMockUser` không tạo một bean override khác. Đây không phải cam kết 100% cache hit trong mọi project: nếu có meta-annotation, test properties, cấu hình động hoặc customizer khác nhau, khóa context vẫn có thể khác. Hãy xác minh bằng log thống kê cache, không suy luận chỉ từ đoạn source.

Lưu ý: `@MockitoBean` field trong hai lớp đều mang tên `reportStore` và cùng kiểu. Tên field/qualifier có thể tham gia xác định target bean, thậm chí ảnh hưởng cache key ở các trường hợp bean override. Giữ định danh nhất quán giúp tránh tạo context khác chỉ vì cách khai báo mock không đồng nhất.

## 6. Chỉ một mock bean khác cũng có thể tạo context thứ hai

Giả sử một lớp test khác cũng dùng `@WebMvcTest(ReportController.class)` nhưng khai báo thêm mock:

~~~java
interface AuditGateway {
    void recordAccess(String reportId);
}

@WebMvcTest(controllers = ReportController.class)
@Import(ReportHttpSecurity.class)
class ReportWithAuditMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportStore reportStore;

    // Khác biệt so với hai lớp trước:
    @MockitoBean
    AuditGateway auditGateway;

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void canReadReport() throws Exception {
        when(reportStore.findById("r-1"))
            .thenReturn(Optional.of(new Report("r-1", "alice")));

        mvc.perform(get("/api/reports/r-1"))
            .andExpect(status().isOk());
    }
}
~~~

Trong ví dụ, `AuditGateway` thậm chí **chưa được controller sử dụng**. Nhưng sự hiện diện của `@MockitoBean AuditGateway` vẫn là một phần của context customization. Cấu hình mock không còn tương đương với `ReportReadMvcTest`, nên framework có thể cần tạo context riêng. Đây là lý do nên khai báo **chỉ những mock thực sự cần**.

~~~text
Key A:
  @WebMvcTest(ReportController.class)
  @Import(ReportHttpSecurity.class)
  @MockitoBean ReportStore reportStore

Key B:
  @WebMvcTest(ReportController.class)
  @Import(ReportHttpSecurity.class)
  @MockitoBean ReportStore reportStore
  @MockitoBean AuditGateway auditGateway

=> Key A != Key B về tập bean overrides
=> Không dùng chung ApplicationContext.
~~~

Tương tự, thay một mock bằng `@MockitoSpyBean` không chỉ đổi hành vi Mockito: nó thay đổi chiến lược override và những bean được tạo/lấy từ context. Không nên coi `@MockitoBean` và `@MockitoSpyBean` là giống nhau ở cache key.

### Thêm mock không phải lúc nào cũng cải thiện tốc độ

Một test có nhiều mock có thể giảm số dependency thật phải khởi tạo, nhưng lại tạo thêm **một biến thể context** nếu những lớp khác dùng tập mock khác. Vì vậy tối ưu cần cân bằng:

- `@WebMvcTest`/`@WebFluxTest` giúp giới hạn bean theo slice, thường rẻ hơn một `@SpringBootTest` lớn.
- Mỗi mock cần thiết giúp cô lập dependency ngoài và chủ động tạo các phản hồi lỗi.
- Mock thêm một service không được gọi chỉ để “cho chắc” có thể phá cơ hội reuse context.
- Gộp tất cả test vào một `@SpringBootTest` khổng lồ để có cache hit không nhất thiết nhanh hơn test slice gọn và có thể làm giảm chất lượng kiểm chứng dependency thật.

## 7. Khác biệt tên field, qualifier và tên bean trong @MockitoBean

Khi override bean theo kiểu, `@MockitoBean` cần xác định **bean mục tiêu**. Nếu ứng dụng có nhiều bean cùng kiểu, qualifier hoặc tên bean có vai trò quan trọng. Spring Test bean override cũng sử dụng thông tin field name làm fallback qualifier trong một số trường hợp.

Ví dụ hai cách viết trông gần tương tự:

~~~java
@MockitoBean
ReportStore reportStore;
~~~

~~~java
@MockitoBean
ReportStore store;
~~~

Nếu project có bean override bằng qualifier fallback, hai field trên có thể tạo **context cache key khác nhau** hoặc nhắm vào target khác. Đừng tự khẳng định đổi tên field luôn luôn tạo context mới trong mọi trường hợp; yếu tố này phụ thuộc cách resolve bean, annotations và phiên bản Spring Framework. Nhưng để tối đa hóa tính nhất quán, hãy đặt **cùng tên field cho cùng dependency** trong các test có ý định chia sẻ context.

Nếu app định nghĩa bean theo tên, có thể ghi rõ:

~~~java
@MockitoBean(name = "reportStore")
ReportStore reportStore;
~~~

Điều này hữu ích khi cần chọn bean cụ thể, nhưng **không phải cách gộp hai cấu hình khác nhau thành một**. Nếu class A mock `reportStore` và class B mock `archiveStore`, chúng thực sự cần môi trường dependency khác; ép hai lớp dùng chung một mock không làm test chính xác hơn.

`@MockitoBean` còn hỗ trợ chế độ buộc phải có bean mục tiêu, chẳng hạn:

~~~java
@MockitoBean(enforceOverride = true)
ReportStore reportStore;
~~~

Tùy contract phiên bản, chế độ mặc định của `@MockitoBean` có thể **tạo bean mới nếu không tìm thấy bean để thay thế**. `enforceOverride = true` yêu cầu việc thay bean đã tồn tại; nếu bean không có, context sẽ không thể khởi động. Dùng tùy chọn này khi muốn test **bảo đảm đang thay đúng dependency thật**, không vô tình tạo thêm mock cho dependency bị cấu hình thiếu. Tuy vậy, trong test slice như `@WebMvcTest`, dependency ngoài slice thường **không có sẵn**, nên áp dụng `enforceOverride = true` cho `ReportStore` có thể làm test thất bại có chủ đích. Đây không phải cấu hình mặc định nên sao chép cho mọi test.

## 8. Mock được reset không có nghĩa Spring tạo context mới

Một điểm thường bị nhầm:

> Nếu Spring tái sử dụng `ApplicationContext`, tại sao test sau không giữ lại toàn bộ các lời gọi `when(...)` và interaction của test trước?

Spring Test/Mockito integration có cơ chế **reset mock theo lifecycle test**, với `@MockitoBean` thông thường có chính sách reset sau mỗi test method. Bean mock **vẫn nằm trong cùng context** nhưng lịch sử tương tác và stubbing được reset theo cấu hình.

Điều này khác hoàn toàn với:

1. **Reset mock**: xóa interaction/stubbing trên mock, không hủy context.
2. **Reset state trong singleton thật**: dọn collection/cache/database do bean chứa; mock reset không làm thay.
3. **Đánh dấu dirty context**: đóng/loại context và tạo lại nếu test sau cần cùng key.
4. **Tạo context khác**: khi cache key khác do cấu hình, không phải do test vừa gọi Mockito.

Ví dụ hai test cùng dùng `@MockitoBean ReportStore`:

~~~java
@Test
@WithMockUser(authorities = "SCOPE_reports.read")
void firstTestStubsOneReport() throws Exception {
    when(reportStore.findById("r-1"))
        .thenReturn(Optional.of(new Report("r-1", "alice")));

    mvc.perform(get("/api/reports/r-1"))
        .andExpect(status().isOk());

    verify(reportStore).findById("r-1");
}

@Test
@WithMockUser(authorities = "SCOPE_reports.read")
void secondTestStubsIndependently() throws Exception {
    when(reportStore.findById("r-1"))
        .thenReturn(Optional.empty());

    mvc.perform(get("/api/reports/r-1"))
        .andExpect(status().isNotFound());
}
~~~

Đưa các phương thức vào lớp test có `MockMvc mvc` và `@MockitoBean ReportStore reportStore`. Test thứ hai không cần dựng lại `ApplicationContext` chỉ vì stub khác; nó thiết lập expectation **của chính test đó**. Mỗi test nên tự stub đủ dữ liệu và không giả định một method chạy trước sẽ cung cấp behavior.

### Thận trọng với test chạy song song

Nếu hai method dùng cùng `ApplicationContext` và **cùng mock bean**, test A có thể đang gọi mock trong khi test B reset hoặc sửa stub trên mock đó. Mockito reset theo lifecycle giúp test tuần tự sạch hơn, **không tự giải quyết race condition khi thao tác trên cùng mock đồng thời**.

Các biện pháp khả thi:

- Giữ các test chia sẻ mock không chạy đồng thời khi chúng thay stubbing/interaction của cùng bean.
- Dùng `@ResourceLock` của JUnit Jupiter với một khóa tài nguyên chung khi cần đồng bộ những ca có shared state.
- Tách những nhóm cần dependency state hoàn toàn khác nhau vào test context riêng một cách có chủ đích.
- Ưu tiên unit test với `@Mock` ở mỗi test instance nếu mục tiêu chỉ là logic thuần, không cần HTTP/security filter.
- Tránh `Mockito.reset(...)` thủ công trong một test đang chạy đồng thời với test khác dùng cùng mock.

Nếu dùng `@ResourceLock` ở nhiều lớp, các test liên quan phải sử dụng **cùng tên khóa**; chỉ đặt lock ở một lớp không đồng bộ với lớp khác nếu lớp kia không tham gia cùng quy tắc. `@Execution(SAME_THREAD)` chỉ nên hiểu trong phạm vi hành vi chạy của JUnit đối với test node được annotate, không mặc định là khóa toàn bộ test suite.

## 9. @DirtiesContext: đúng khi thay đổi context, tốn khi dùng tràn lan

Spring Test cho phép:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class ContextMutatingIntegrationTest {
    // Chỉ dùng nếu mỗi method thật sự làm bẩn ApplicationContext.
}
~~~

Với annotation trên, sau mỗi method context có thể bị loại khỏi cache, nên test sau phải xây dựng lại context. Chi phí đó có thể rất cao khi khởi động web server, datasource, SAML/OAuth2 configuration, JWT decoder, filter chain hoặc kết nối Testcontainers.

**Không dùng `@DirtiesContext` chỉ vì test đặt `when(...)` lên `@MockitoBean`.** Mock thường đã có reset lifecycle. Chỉ cân nhắc dirty context khi test làm thay đổi một phần trạng thái **không thể reset đáng tin cậy** trong Spring context, ví dụ tác động cấu hình singleton hoặc nội bộ bean không khôi phục được.

`@DirtiesContext` cũng **không xóa toàn bộ dữ liệu bên ngoài**:

- Dữ liệu đã commit trong PostgreSQL/Redis có thể vẫn tồn tại.
- `static` mutable state và cache toàn JVM ngoài Spring context có thể vẫn còn.
- Các service/process ngoài JVM không bị reset.
- Những thread pool tự tạo mà không gắn lifecycle Spring vẫn có thể tồn tại.

Nên thiết kế fixture độc lập, transaction/cleanup phù hợp và key namespace cho storage test. Với HTTP test chạy ở server thread và transaction riêng, `@Transactional` trên test method không chắc rollback những thay đổi đã commit ở request; phải hiểu đường transaction thật.

## 10. Properties và profile khác cũng phân mảnh cache

Giả sử hai lớp sử dụng cùng mock nhưng cấu hình khác:

~~~java
@SpringBootTest(properties = "app.reports.mode=strict")
@ActiveProfiles("test")
class StrictModeTest { /* ... */ }
~~~

~~~java
@SpringBootTest(properties = "app.reports.mode=legacy")
@ActiveProfiles("test")
class LegacyModeTest { /* ... */ }
~~~

Hai lớp có **khác biệt thực sự về property**, vì vậy không nên chia sẻ context. Tương tự, `@ActiveProfiles("jwt-test")` so với `@ActiveProfiles("basic-test")` có thể chọn các bean SecurityFilterChain/AuthenticationProvider khác; ép chung context sẽ làm sai mục tiêu kiểm thử.

Một số điều kiện làm cache key thay đổi:

~~~text
@TestPropertySource(properties = "feature.authz.enabled=true")
@TestPropertySource(properties = "feature.authz.enabled=false")

@SpringBootTest(properties = "server.error.include-message=always")
@SpringBootTest(properties = "server.error.include-message=never")

@ActiveProfiles("mvc-security")
@ActiveProfiles("oauth2-resource-server")

@Import(BasicSecurityConfig.class)
@Import(JwtSecurityConfig.class)
~~~

Không cần “chuẩn hóa” những cấu hình trên nếu chúng đại diện cho các đường sản phẩm cần được kiểm tra thật. Chỉ giảm các property/override **vô nghĩa hoặc khác nhau do copy-paste**.

### @DynamicPropertySource và bẫy khác giá trị nhưng cùng method

Spring Test đưa **định nghĩa method `@DynamicPropertySource`** vào phần context customizers. Giá trị property được tính ở runtime từ supplier, nên không nên giả định **mọi thay đổi giá trị từ cùng method** luôn tạo cache key mới.

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
        () -> postgres.getJdbcUrl());
    registry.add("spring.datasource.username",
        () -> postgres.getUsername());
    registry.add("spring.datasource.password",
        () -> postgres.getPassword());
}
~~~

Khi các test subclass kế thừa cùng method này nhưng chạy với database/container khác nhau, context có thể bị tái sử dụng mặc dù **nguồn giá trị động đã thay đổi**. Cần thiết kế container lifecycle nhất quán hoặc đánh dấu context dirty ở ranh giới thích hợp. Không đưa một URL database ngẫu nhiên vào log rồi kết luận Spring đã tự đổi cache key theo URL.

## 11. @WithMockUser, mockJwt và OAuth2/OIDC fixture thường không phân mảnh context

Một chiến lược hiệu quả với Spring Security là **giữ nguyên cấu hình bean**, rồi thay identity **ở phạm vi từng test/request**:

~~~java
@Test
@WithMockUser(username = "alice",
              authorities = "SCOPE_reports.read")
void readerWithScopeSucceeds() throws Exception {
    when(reportStore.findById("r-1"))
        .thenReturn(Optional.of(new Report("r-1", "alice")));

    mvc.perform(get("/api/reports/r-1"))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(username = "bob", roles = "USER")
void sameContextWithDifferentPrincipalGetsForbidden()
        throws Exception {
    mvc.perform(get("/api/reports/r-1"))
        .andExpect(status().isForbidden());
}
~~~

Việc đổi username, roles hoặc authorities qua `@WithMockUser` không tạo thêm bean. Nó không cần `@DirtiesContext`. Trong Spring Security Test, listener quản lý test `SecurityContext` theo lifecycle; nếu test tự `SecurityContextHolder.setContext(...)`, vẫn phải dọn đúng cách và không chia sẻ context khả biến giữa các method.

Với MockMvc, có thể thay identity **ngay trong request**:

~~~java
mvc.perform(get("/api/reports/r-1")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports/r-1")
        .with(user("bob").roles("USER")))
    .andExpect(status().isForbidden());
~~~

Các ví dụ cần import `SecurityMockMvcRequestPostProcessors.user` và `SimpleGrantedAuthority`. Khi kiểm tra SAML2 hoặc custom Authentication, dùng `authentication(customAuthentication)` trên request cũng là dữ liệu ở mức request, không thay bean graph.

### JWT giả lập: thay token claims chứ không thay decoder bean

~~~java
mvc.perform(get("/api/reports/r-1")
        .with(jwt()
            .jwt(builder -> builder
                .subject("alice")
                .claim("tenant_id", "tenant-a"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

`jwt()` trong `spring-security-test` tạo JWT authentication giả cho servlet request, thuận tiện kiểm tra quyền theo subject/scope. `oauth2Login()`, `oidcLogin()`, `oauth2Client()` và `opaqueToken()` cũng cung cấp các fixture theo mục tiêu riêng. Chúng không tự bắt Spring tạo context mới chỉ vì identity/claim khác ở hai request.

Nhưng **không nhầm với JWT integration test**: `jwt()` bỏ qua quá trình `JwtDecoder` xác minh chữ ký, issuer và thời hạn. Nếu test nhằm xác minh Bearer token thật, cần chạy security filter và decoder thật, có thể là một context khác với cấu hình Resource Server hoặc verification keys test tương ứng. Không làm yếu test bằng cách thay decoder bằng mock chỉ để cùng cache key.

### Tại sao không dùng @MockitoBean JwtDecoder cho mọi lớp?

Một lớp test Resource Server có thể khai báo:

~~~java
@MockitoBean
JwtDecoder jwtDecoder;
~~~

Khi làm vậy, cấu hình context có thêm bean override, và `JwtDecoder` **không còn xác minh JWT cryptographically** trừ khi test chủ động stub logic như mong muốn. Nó có thể phù hợp để kiểm tra phản ứng HTTP với decoder trả `Jwt` hoặc ném `JwtException`, nhưng không chứng minh trust boundary thật.

Vì vậy nên phân tách rõ:

| Test | Authentication đầu vào | Được phép kết luận |
| --- | --- | --- |
| `MockMvc.with(jwt())` | JWT principal giả lập | Phân quyền sau khi identity có sẵn |
| `@MockitoBean JwtDecoder`, stub decode | Decoder giả lập | Filter xử lý response/exception từ decoder theo stub |
| Bearer JWT thật + decoder/key test | Token qua filter và xác minh thật | Chữ ký, claim validation và phân quyền liên quan |

Chúng có thể dùng các context khác nhau vì **nội dung bảo mật thực sự đang được kiểm tra khác nhau**, không phải do thiếu tối ưu cache.

## 12. WebFlux và WebTestClient: cùng nguyên tắc, context khác nhau

Trong WebFlux, `WebTestClient` có thể gắn vào application context hoặc gửi HTTP thật tới server. Khi test Reactive authorization, `mockUser()`/`mockJwt()` thiết lập danh tính cho request; không tự thêm mock service bean vào Spring context.

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
@AutoConfigureWebTestClient
class ReactiveReportSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void aliceIsAllowed() {
        client.mutateWith(mockUser("alice")
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports.read")))
            .get().uri("/api/reactive/reports/r-1")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void bobWithNoScopeIsDenied() {
        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/api/reactive/reports/r-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đoạn này **giả định** một ứng dụng WebFlux có endpoint `GET /api/reactive/reports/{id}` và `SecurityWebFilterChain` cho phép `SCOPE_reports.read`. Nó minh họa mẫu test danh tính; không lấy controller Servlet của mục 4 áp vào WebFlux. Các import cần thiết gồm `@SpringBootTest`, `@AutoConfigureWebTestClient`, `@Autowired`, `WebTestClient`, `mockUser` và `SimpleGrantedAuthority`.

Khi một test dùng `@WebFluxTest` và test khác dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, chúng thường có cấu hình context khác nhau và **không nên ép dùng chung**. Một test Reactive context-bound cũng chưa chứng minh transport qua TCP socket dù dùng cùng lớp `WebTestClient`.

~~~java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice")
            .claim("tenant_id", "tenant-a"))
        .authorities(new SimpleGrantedAuthority(
            "SCOPE_reports.read")))
    .get().uri("/api/reactive/reports/r-1")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ `mockJwt()` dành cho test context có cơ chế Resource Server Reactive và chính sách tương ứng. Nó không chạy `ReactiveJwtDecoder`; vì vậy nội dung bằng chứng khác test Bearer thật. Khi mô hình hóa OIDC/OAuth2 ở WebFlux, `mockOAuth2Login()`, `mockOidcLogin()` hoặc `mockOAuth2Client()` cũng cần được chọn theo cơ chế mà endpoint sử dụng.

## 13. Mối liên hệ giữa context cache và dữ liệu độc lập

**Cùng context không đồng nghĩa cùng Authentication.** Ngược lại, **khác context không bảo đảm mọi dữ liệu đều độc lập**.

| Dữ liệu/đối tượng | Cấp vòng đời phổ biến | Giải pháp cô lập |
| --- | --- | --- |
| `@WithMockUser` identity | Test method | Listener Spring Security Test và không chia sẻ custom principal khả biến |
| `MockMvc.with(user(...))` | HTTP request | Tạo mới theo request |
| `WebTestClient.mutateWith(mockUser(...))` | HTTP request/test client | Không mutate một principal chung |
| `@MockitoBean` | Bean của cached Spring context | Reset mock và tự stub đầy đủ mỗi test; kiểm soát song song |
| Singleton `@Bean` thật | Cached Spring context | Thiết kế stateless hoặc reset dữ liệu test được quản lý |
| HTTP session/WebSession | Theo session/cookie | Tạo session/cookie riêng, đừng reuse giữa test vô tình |
| Database/Redis | Ngoài context | Transaction/cleanup/schema/container/namespace theo test |
| `SecurityContextHolder` ThreadLocal | Thread thực thi | Setup/cleanup theo scope; không để auth cũ trên pool |
| Reactor Context | Reactive subscription | Gắn context theo subscription, không dùng chung Authentication mutable |
| `static` mutable field | JVM | Tránh giữ dữ liệu danh tính/quyền ở static, không trông chờ `@DirtiesContext` |

Một ví dụ test method A stub `ReportStore` trả báo cáo Alice, test method B stub lại mock trả báo cáo Bob. Reset mock giúp các stub không tích lũy. Nhưng nếu service thật còn giữ cache `Map<String, Report>` dạng singleton, cache ấy vẫn có thể giữ report từ test A. Test B có thể được `200` với dữ liệu cũ hoặc gặp `403` sai do owner không đúng.

Vì vậy khi thấy test phụ thuộc thứ tự, đừng vội đánh dấu `@DirtiesContext` trên mọi lớp. Hãy xác định **nguồn trạng thái nào được đọc/ghi**: mock stubs, bean cache, session, database, ThreadLocal, Reactor Context hay một dịch vụ ngoài.

### Một bài test có @WithMockUser không cần context riêng cho từng user

Test với:

~~~java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanAccess() { /* ... */ }

@Test
@WithMockUser(username = "bob", roles = "USER")
void userCannotAccess() { /* ... */ }
~~~

không nên thêm `@DirtiesContext(AFTER_EACH_TEST_METHOD)` chỉ vì Alice và Bob có role khác. Spring Security Test thiết lập authentication ở vòng đời test; ApplicationContext chứa SecurityFilterChain và các bean dùng chung vẫn có thể được cache.

Đối với integration test sử dụng session thực hoặc Authentication được lưu trong database, cần tạo dữ liệu riêng và cleanup phù hợp. Giả lập identity theo test không dọn mọi thứ một request khác đã ghi.

## 14. Đo cache hit/miss thay vì đoán từ thời gian chạy

Spring Test có logger `org.springframework.test.context.cache`. Bật mức DEBUG cho suite khi chẩn đoán:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Trong một số môi trường test, có thể cấu hình logging trực tiếp (ví dụ `logback-test.xml`) để bảo đảm logger của Spring TestContext hiển thị:

~~~xml
<configuration>
  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="org.springframework.test.context.cache" level="DEBUG"/>
  <root level="INFO">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
~~~

Hai đoạn này là **các lựa chọn cấu hình log mẫu**, không cần đồng thời áp dụng nếu môi trường đã có logging phù hợp. Không sửa cấu hình log production chỉ để đo cache test; bật tạm trong test environment/CI diagnostics.

Một thống kê cache thường có các thông tin:

~~~text
size=3, maxSize=32, parentContextCount=0,
hitCount=..., missCount=..., failureCount=...
~~~

Các con số là cấu trúc minh họa, không phải kết quả đo của dự án. Không suy ra “đã cache hit” chỉ vì test sau chạy nhanh: JVM class loading, JIT, connection pool, daemon và IO cache cũng có thể làm thay đổi thời gian.

Khi đọc log:

1. **Cache hit**: test dùng được context đã có, không phải dựng lại toàn bộ bean graph.
2. **Cache miss**: framework không tìm thấy key tương ứng hoặc context cũ đã bị loại khỏi cache.
3. **Cache eviction**: số context khác nhau vượt giới hạn hoặc lifecycle đóng context.
4. **Context dirtied**: test đánh dấu context không còn được reuse.
5. **Context load failure**: lỗi khởi động là vấn đề cấu hình; không tự động coi là cache miss bình thường.

Spring Framework còn có **failure threshold** để tránh thử khởi tạo lặp lại một context đã xác định lỗi trong cùng bộ test; đừng diễn giải những test fail nhanh sau lỗi boot đầu tiên thành bằng chứng context cache hoạt động tốt.

## 15. Tối ưu CI: không phải càng nhiều test worker càng nhanh

Trong CI, một cấu hình thường có hai cấp song song:

1. **Nhiều JVM/test process** (Gradle test worker, Maven fork, nhiều CI jobs).
2. **Nhiều test class/method chạy đồng thời trong cùng JVM** (ví dụ JUnit Jupiter parallel execution).

Cache `ApplicationContext` không được chia sẻ giữa các JVM. Vì vậy tăng số fork có thể giúp dùng nhiều CPU nhưng đồng thời khiến mỗi process phải **khởi động lại context tương tự**, nhân bộ nhớ và số kết nối database. Nếu một full Spring Boot context nặng, tốc độ có thể giảm khi tăng quá nhiều fork.

Ví dụ Gradle Kotlin DSL để điều chỉnh **số JVM worker**, không phải bật JUnit parallel trong cùng JVM:

~~~kotlin
tasks.test {
    useJUnitPlatform()

    // Minh họa: đo thử 1, 2, ... dựa trên CPU/heap của CI.
    maxParallelForks = 2

    // 0 = không tự tạo fork mới sau mỗi N test class.
    forkEvery = 0

    // Giới hạn context cache trong mỗi JVM test worker.
    systemProperty("spring.test.context.cache.maxSize", "32")
}
~~~

Đây là cấu hình tham khảo, **không phải đề xuất cố định cho mọi runner**. Với dự án có rất ít lõi CPU, RAM hạn chế hoặc nhiều Testcontainers, `maxParallelForks = 1` có thể hiệu quả và ổn định hơn. Ngược lại, suite nhiều unit test độc lập có thể hưởng lợi từ song song cao hơn.

Trong Maven Surefire, `forkCount` và `reuseForks` cũng ảnh hưởng đến số JVM và cơ hội reuse context. Một context được cache bởi fork A không thể được fork B lấy lại. Khi phân tích CI, cần so sánh **tổng thời gian, số lần load context và peak memory**, không chỉ tổng số test chạy mỗi giây.

### Tổ chức các cấp test theo mục tiêu

| Cấp test | Công cụ | Context cache | Vị trí thường hợp lý trong pipeline |
| --- | --- | --- | --- |
| Unit test thuần | JUnit + Mockito `@Mock` | Không cần Spring context | Chạy thường xuyên, parallel khi dữ liệu độc lập |
| Servlet controller/security slice | `@WebMvcTest` + `@MockitoBean` + `MockMvc` | Reuse trong cùng nhóm cấu hình | Pull request, phản hồi nhanh |
| WebFlux slice/security | `@WebFluxTest` + `WebTestClient` | Reuse trong cùng nhóm Reactive config | Pull request |
| Application integration | `@SpringBootTest` + database/test resources | Cache nếu cấu hình tương đương, start đắt hơn | PR hoặc pipeline tích hợp |
| Auth protocol thật | JWT decoder, OAuth2/OIDC/SAML endpoint và IdP test | Thường có cấu hình/key/container riêng | Pipeline integration hoặc nightly theo mức rủi ro |
| E2E triển khai | HTTP socket, cookie/browser, proxy/TLS | Không phụ thuộc Spring in-process cache | Staging/release gate |

Các lớp test bảo mật không nên **chỉ** nằm trong suite chạy nightly: những chính sách truy cập cốt lõi như `401` khi chưa xác thực, `403` khi thiếu scope, và `200` với user hợp lệ nên có trong suite PR nhanh. Các case E2E đắt hơn bổ sung bằng chứng về transport và protocol thật.

### Một quy trình đo có kiểm soát

1. Chạy cùng một bộ test ổn định với **một JVM fork**, bật thống kê cache và ghi tổng thời gian/heap.
2. Nhóm các lớp test cùng `@WebMvcTest`/`@SpringBootTest`, cùng import/profile/properties và cùng tập bean overrides.
3. Đếm những biến thể chỉ khác mock không cần thiết hoặc tên field/qualifier thiếu nhất quán.
4. Loại bỏ mock thừa, chuẩn hóa cấu hình test được chia sẻ **mà không bỏ coverage**.
5. Chạy lại suite và so sánh số context load, thời gian, peak memory cùng tỷ lệ fail.
6. Sau đó mới thử tăng `maxParallelForks` hoặc JUnit parallel và đo lại trên cùng mức tài nguyên CI.

Nếu cache hit tăng mà bài test security bị thay bằng việc mock luôn policy/decoder, tối ưu đó **không hợp lệ**. Hiệu quả CI phải đi cùng chất lượng bảo mật.

## 16. Những anti-pattern đặc biệt nguy hiểm trong Spring Security Testing

### Tắt security filters để test chạy nhanh

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Khi dùng cấu hình này, Spring Security filters không còn bảo vệ request của MockMvc. Một test `GET /api/private` trả `200` **không chứng minh SecurityFilterChain cho phép đúng người**. Tùy mục tiêu, có thể tắt filters để chỉ test controller thuần; nhưng phải đặt tên và mô tả đúng: nó **không phải HTTP security test**.

Nếu muốn kiểm chứng authorization, dùng `@AutoConfigureMockMvc` mặc định với filters hoặc `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` trong setup tương ứng.

### Mock luôn thành phần cần kiểm chứng

Các ví dụ có thể làm mất ranh giới bảo mật:

~~~java
@MockitoBean
AuthorizationManager<?> authorizationManager;

@MockitoBean
JwtDecoder jwtDecoder;
~~~

Nếu test chủ đích kiểm tra policy của `AuthorizationManager`, một mock “cho phép tất cả” sẽ không kiểm tra policy thật. Nếu test nhằm kiểm tra JWT signature, mock `JwtDecoder` khiến không có xác minh mật mã thật. Chỉ mock những thành phần **ngoài phạm vi điều đang được chứng minh** và ghi rõ giới hạn trong test case.

### Mỗi class có một @TestConfiguration hơi khác

~~~java
@TestConfiguration
class ReportTestBeansA {
    @Bean
    Clock clock() {
        return Clock.fixed(Instant.parse("2030-01-01T00:00:00Z"),
            ZoneOffset.UTC);
    }
}
~~~

~~~java
@TestConfiguration
class ReportTestBeansB {
    @Bean
    Clock clock() {
        return Clock.fixed(Instant.parse("2030-01-02T00:00:00Z"),
            ZoneOffset.UTC);
    }
}
~~~

Nếu hai lớp import hai configuration classes khác nhau, context key có thể khác. Không nhất thiết là lỗi: thời gian cố định khác nhau có thể phục vụ các ca token expired/not-before quan trọng. Nhưng nếu các lớp dùng hai cấu hình giống nhau về ý nghĩa chỉ vì mỗi người copy một bản, nên hợp nhất một test configuration ổn định.

Với fake clock **có thể sửa thời gian** trong singleton, phải cẩn thận: dùng một context để tăng cache hit có thể làm test ảnh hưởng lẫn nhau. Tốt hơn là một fixture bất biến theo lớp, hoặc reset hoàn toàn trạng thái clock sau mỗi test và không chạy các test sửa cùng clock đồng thời.

### Đặt @DirtiesContext cho cả suite như cách reset mock

~~~java
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
~~~

Nếu chỉ cần reset stub của `@MockitoBean`, đây thường là cách làm quá mức. Nó khiến mỗi method có thể nạp lại context, làm tăng thời gian CI và khiến nguyên nhân shared state trong database/session khó thấy rõ. Hãy xác định state cần reset và để cơ chế reset mock làm đúng phần việc của nó.

### Dùng chung custom principal/Authentication khả biến

Một test có thể để lại một `Authentication` có authorities hoặc principal custom thay đổi được trong singleton. Cache context khiến bean đó tồn tại ở test sau, có thể làm Bob nhận role Alice. `@WithMockUser` tạo identity theo test nhưng **không sửa được việc bean ứng dụng đang giữ một principal mutable sai thiết kế**.

### Dùng log “không có 403” làm bằng chứng quyền

Mỗi security test quan trọng cần có **đối chứng dương và âm**: user có scope được `200`, user thiếu scope bị `403`, anonymous bị `401` hoặc redirect theo entry point. Nếu mọi request đều trả `403` do lỗi CSRF, các case âm tính vẫn “xanh”. Với request thay đổi state, thêm CSRF token khi cấu hình yêu cầu để không nhầm lý do chặn.

## 17. Bảng quyết định: cần cùng hay khác context?

| Tình huống hai test | Có thể tái sử dụng context? | Lý do |
| --- | --- | --- |
| Khác `@WithMockUser` Alice/Bob | Thường có | Identity là dữ liệu test, không phải bean config |
| Khác `with(user(...))` trong MockMvc | Thường có | Authentication gắn cho request |
| Khác `jwt()` subject/authorities | Thường có | JWT principal giả lập theo request |
| Khác `mockUser()` trong WebTestClient | Thường có | Identity gắn cho request Reactive |
| Khác `when(reportStore.findById(...))` | Có thể | Stub reset theo lifecycle; phải tránh race khi parallel |
| Một class thêm `@MockitoBean AuditGateway` | Thường không | Khác tập bean overrides/customizers |
| Một class `@MockitoBean`, class kia `@MockitoSpyBean` | Thường không | Khác chiến lược bean override |
| Khác qualifier/name của bean override | Có thể không | Khác target resolution/cache customization |
| Khác `@ActiveProfiles` | Thường không | Khác cấu hình bean/properties |
| Khác `@TestPropertySource` | Thường không | Khác properties trong cache key |
| Cùng method `@DynamicPropertySource` nhưng giá trị container đổi | Có thể reuse **sai** | Key có thể chưa phản ánh thay đổi runtime value |
| `@WebMvcTest` so với `@SpringBootTest` | Thường không | Khác test bootstrap/bean graph |
| `@WebFluxTest` so với `@WebMvcTest` | Thường không | Khác web stack và slice |
| Một test làm dirty Spring context | Không reuse context đã bị loại | Context cần khởi động lại |
| Hai CI jobs độc lập | Không | Context cache trong từng JVM/test process |

Các ô “thường” và “có thể” phản ánh thực tế cache key có nhiều thành phần; **chỉ log cache thống kê mới xác nhận cache hit cụ thể**. Hai context có cùng tên bean hoặc cùng số mock chưa chắc tương đương nếu profile, bean qualifier, property hoặc bootstrap khác nhau.

## 18. Bài tập thực hành

1. **Hai lớp cùng mock:** triển khai `ReportReadMvcTest` và `ReportDeniedMvcTest` cùng `@WebMvcTest`, `@Import` và `@MockitoBean ReportStore`. Chạy trong cùng JVM với cache DEBUG; ghi lại hit/miss trước và sau khi thêm lớp thứ hai.
2. **Thêm một mock:** bổ sung `@MockitoBean AuditGateway` chỉ ở lớp thứ hai. So sánh số context tạo ra, giải thích vì sao một mock không được controller dùng vẫn ảnh hưởng cấu hình.
3. **Đổi field name:** đổi `reportStore` thành `store` trong một lớp, kiểm tra log cache ở phiên bản Spring đang dùng. Nếu bean selection dựa vào qualifier fallback, xác nhận thay đổi và chuẩn hóa tên.
4. **Mockito unit vs Spring slice:** chuyển một bài test chỉ kiểm tra `ReportFacade` sang `@Mock`/`@InjectMocks` không dùng Spring. So sánh thời gian chạy và loại bằng chứng kiểm tra được.
5. **Đổi identity, giữ context:** viết test Alice có `SCOPE_reports.read`, Bob không có scope, anonymous. Không thêm `@DirtiesContext`. Kiểm tra các response `200`, `403`, `401`.
6. **Mock reset:** test A stub báo cáo `r-1` tồn tại, test B stub `r-1` không tồn tại. Chạy cả hai theo thứ tự ngược lại; mỗi test phải tự đủ stubbing.
7. **Test parallel:** cố ý cho hai test sửa cùng `@MockitoBean` đồng thời. Xác nhận hiện tượng không ổn định, rồi dùng cấu trúc test/synchronization phù hợp để loại race; không chỉ tăng timeout.
8. **Profiles khác nhau:** tạo một lớp test HTTP Basic và một lớp test JWT Resource Server dùng profile hoặc bean configuration khác nhau. Chứng minh chúng cần context khác để kiểm tra đúng authentication mechanism.
9. **Decoder thật vs giả:** viết test `with(jwt())` cho scope, và test Bearer JWT ký bằng khóa test đi qua `JwtDecoder` thật. Ghi rõ từng test chứng minh điều gì.
10. **Dynamic property:** dùng một method `@DynamicPropertySource` lấy URL từ container; thử kịch bản container thay đổi giữa các subclass và xác định có cần `@DirtiesContext` hay test environment thống nhất không.
11. **So sánh CI:** chạy suite với một và hai test worker JVM, đo tổng thời gian, cache stats và peak memory. Không kết luận số worker nào tốt hơn nếu chưa có số liệu.
12. **Test Servlet và Reactive:** viết `MockMvc` security test và `WebTestClient` Reactive security test với principal giả lập. Phân tích vì sao không nên ép chung một Spring context giữa hai web stack.
13. **Phát hiện cấu hình lọt quyền:** thêm `@AutoConfigureMockMvc(addFilters=false)` vào một test security và quan sát hậu quả; khôi phục filters để các ca anonymous/thiếu scope hoạt động.
14. **Đánh giá @DirtiesContext:** tìm một lớp chỉ dùng `@MockitoBean` nhưng đang có `@DirtiesContext`. Loại bỏ annotation trong nhánh thử nghiệm, kiểm tra lại mock isolation và cache hit; chỉ giữ dirty context nếu thật sự có state cần tái khởi tạo.

## 19. Checklist trước khi kết luận đã tối ưu CI

1. **Phạm vi:** Test nào chứng minh authentication, HTTP authorization, method/domain authorization, JWT/OAuth2/OIDC protocol, Servlet hay Reactive?
2. **Context key:** Các lớp cùng mục tiêu có cùng test slice, imports, profiles, properties và bean overrides không?
3. **Mock:** Mỗi `@MockitoBean` có thật sự cần không? Có mock nhầm bean chứa chính policy cần kiểm tra không?
4. **Tên/qualifier:** Bean overrides tương đương có dùng cách đặt tên nhất quán không?
5. **Reset:** Test nào cần reset Mockito stubs, test nào cần dọn singleton/database/session, test nào thực sự cần `@DirtiesContext`?
6. **Danh tính:** `@WithMockUser`, `jwt()`, `mockUser()` có được tạo theo test/request, không dùng chung principal mutable không?
7. **Parallel:** Có hai test cùng sửa mock, bean singleton hoặc session trong lúc chạy đồng thời không?
8. **CI process:** Có bao nhiêu JVM worker/fork? Mỗi worker khởi tạo bao nhiêu context? Có CPU/RAM đủ để tăng parallel không?
9. **Bằng chứng:** Cache hit/miss, thời gian chạy, peak memory và các test `200`/`401`/`403` đều được kiểm tra chưa?
10. **Ranh giới thật:** Các ca JWT signature, OAuth2/OIDC/SAML flow, cookie/TLS/HTTP socket có test tích hợp riêng nếu hệ thống yêu cầu không?

### Kết quả cần đạt

Người học cần hiểu rằng **Spring TestContext cache theo cấu hình, không theo tên test hoặc danh tính Alice/Bob**. `@MockitoBean`, `@MockitoSpyBean`, profile, properties, test slice và các customizer có thể làm phân mảnh cache; còn `@WithMockUser` hoặc fixture authentication ở mức request thường không đòi context mới. **Reset mock** khác với **đóng ApplicationContext**, và cả hai đều không thay thế cô lập session/database/singleton state. Một chiến lược CI tốt giữ test security nhanh nhờ reuse đúng chỗ, nhưng không mock bỏ các ranh giới xác thực/phân quyền mà dự án cần kiểm chứng.

### Tài liệu tham khảo

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Security — Servlet MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — Reactive WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [JUnit 5 — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution)
