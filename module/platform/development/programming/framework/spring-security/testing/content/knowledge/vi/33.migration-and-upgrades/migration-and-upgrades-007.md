# Chuyển `@MockBean`, `@SpyBean` sang API mới khi nhánh mục tiêu yêu cầu

Trong chương **Di chuyển và nâng cấp** của module **SPRING_SECURITY_TESTING**, một thay đổi có thể ảnh hưởng trực tiếp tới bộ kiểm thử là việc chuyển từ các annotation Mockito tích hợp của **Spring Boot Test** sang cơ chế **bean override của Spring Framework Test**. Các bài test trước đây dùng `@MockBean` hoặc `@SpyBean` có thể cần đổi sang `@MockitoBean` hoặc `@MockitoSpyBean` khi nhánh nâng cấp đã hỗ trợ API mới và chính sách dependency yêu cầu. Đây **không phải thao tác đổi tên tìm–thay hàng loạt**: package, thuộc tính, điều kiện tồn tại của bean, lựa chọn bean theo tên/`@Qualifier` và cách cache `ApplicationContext` đều cần được xét.

Đối với **SPRING_SECURITY_TESTING**, nhiệm vụ quan trọng hơn việc test compile là **giữ nguyên bằng chứng xác thực, phân quyền và bảo vệ HTTP**. Sau nâng cấp, các test Servlet/`MockMvc` và Reactive/`WebTestClient` phải tiếp tục kiểm tra request anonymous, người dùng thiếu quyền, người dùng đủ quyền, principal JWT/OAuth2/OIDC đúng kiểu và những tác dụng phụ không được phép xảy ra. Một test chỉ nhận `200 OK` vì vô tình mock luôn security filter, method security hoặc service cần kiểm chứng là một ca nâng cấp sai dù mọi annotation đã đổi thành công.

## 1. Khi nào thực sự cần chuyển annotation?

Hai họ annotation có nguồn gốc khác nhau:

| API | Package | Ý nghĩa |
| --- | --- | --- |
| `@MockBean` | `org.springframework.boot.test.mock.mockito.MockBean` | Mock một bean trong Spring Boot test context (API cũ) |
| `@SpyBean` | `org.springframework.boot.test.mock.mockito.SpyBean` | Spy bean thật trong Spring Boot test context (API cũ) |
| `@MockitoBean` | `org.springframework.test.context.bean.override.mockito.MockitoBean` | Ghi đè/tạo bean Mockito mock bằng Spring Framework Test |
| `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito.MockitoSpyBean` | Bọc bean đang tồn tại bằng Mockito spy qua Framework Test |

**Mốc phiên bản cần biết:** Spring Framework **6.2** giới thiệu cơ chế test bean override với `@MockitoBean` và `@MockitoSpyBean`. Spring Boot **3.4** sử dụng Framework 6.2 và đánh dấu `@MockBean`/`@SpyBean` là deprecated, dự kiến loại bỏ trong Boot **4.0**. Vì vậy nhánh nâng cấp lên hệ có Spring Framework Test hỗ trợ API mới có thể chuyển dần; nhánh cũ chưa có API này **không thể chỉ đổi import rồi compile**. Đối với bất kỳ nhánh mục tiêu nào, hãy kiểm tra BOM/dependency thực tế, chính sách deprecation của phiên bản đó và kết quả compile; không tự suy từ số phiên bản Java.

| Nhánh mục tiêu | Quyết định hợp lý |
| --- | --- |
| Nhánh bảo trì vẫn dùng Boot/Framework cũ, chưa có `@MockitoBean` | Giữ `@MockBean`/`@SpyBean` cho đến khi nâng dependency hoặc có chiến lược tương thích |
| Nhánh Boot 3.4+ với Framework 6.2+, API mới đã có | Có thể chuyển từng nhóm test, đặc biệt nếu mục tiêu là dọn deprecated API |
| Nhánh chuyển sang thế hệ Boot không còn API cũ | Chuyển sang API Framework tương thích trước khi hoàn tất nâng cấp |
| Codebase đa nhánh đang giữ hai baseline dependency | Tránh cherry-pick import mới sang nhánh chưa hỗ trợ; lập kế hoạch tách commit hoặc abstraction test nếu cần |

**Thông điệp của tiêu đề bài:** chỉ chuyển **khi nhánh mục tiêu yêu cầu và có khả năng hỗ trợ**. Không thay đổi một nhánh ổn định chỉ vì thấy deprecation ở nhánh khác, và không sửa dependency/build ngoài phạm vi công việc được phê duyệt.

## 2. Hiểu đúng mock bean và Mockito mock thuần

`@Mock` của Mockito tạo mock trong **lớp test**, nhưng không tự thay thế bean được inject vào controller/service của Spring. `@MockitoBean` tạo hoặc ghi đè **bean trong Spring Test `ApplicationContext`**. Đây là khác biệt cốt lõi khi test HTTP:

```java
@Mock
DocumentReader reader; // Chỉ là field Mockito: chưa thay bean của Spring.

@MockitoBean
DocumentReader springReader; // Bean được dùng trong test ApplicationContext.
```

Ví dụ, `@WebMvcTest` nạp controller cần `DocumentReader`. Nếu chỉ khai báo `@Mock DocumentReader`, controller vẫn thiếu dependency hoặc dùng một bean khác, khiến test thất bại lúc khởi tạo context hay dùng sai collaborator. `@MockitoBean` giải quyết đúng vấn đề **test context**, không phải cấp một principal có quyền cho request.

Không nên mock các thành phần chính mà bài test muốn kiểm chứng:

- **Không mock** `SecurityFilterChain`, `SecurityWebFilterChain` hoặc authorization service nếu mục tiêu là kiểm tra chính rule của chúng.
- **Không mock** `JwtDecoder` rồi kết luận chữ ký/`exp`/`iss` được xác minh; `jwt()`/`mockJwt()` đã bỏ qua validation.
- **Không mock** repository khi mục tiêu là xác nhận transaction, SQL constraint và side effect thực sự được commit.
- **Có thể mock** một cổng I/O ngoài phạm vi test (email, notification, external pricing service) để response và quyền vẫn được thực thi trên pipeline thật.

## 3. Cú pháp trước và sau: trường hợp mock đơn giản

Ví dụ một slice test Servlet ở nhánh cũ:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@WebMvcTest(DocumentsController.class)
class DocumentsControllerTest {
    @Autowired MockMvc mvc;

    @MockBean
    DocumentReader reader;
}
```

Khi nhánh mục tiêu hỗ trợ Spring Framework Test Bean Override, dùng:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@WebMvcTest(DocumentsController.class)
class DocumentsControllerTest {
    @Autowired MockMvc mvc;

    @MockitoBean
    DocumentReader reader;
}
```

Ở mức đơn giản, hai test có vẻ tương đương: controller có một collaborator `DocumentReader` được thay thế bằng Mockito mock. Tuy nhiên, cần xem xét sự khác biệt nếu bean tồn tại nhiều bản, có qualifier, thuộc parent/child context, được register qua `FactoryBean`, hoặc code cũ dùng thuộc tính riêng của Boot annotation.

### Dùng spy thay vì mock

```java
// Cũ (Spring Boot Test):
@SpyBean
AuditRecorder auditRecorder;

// Mới (Spring Framework Test):
@MockitoSpyBean
AuditRecorder auditRecorder;
```

Import API mới:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Spy vẫn gọi **logic thật theo mặc định** và cho phép xác minh các lời gọi bằng Mockito. Điều này rất khác mock, nơi method thường trả giá trị mặc định nếu chưa stub. Vì spy có thể tạo **tác dụng phụ thật**, phải cẩn thận với transaction, gửi event, gửi email hoặc service truy cập mạng.

## 4. Quy tắc tạo/thay thế bean khác nhau giữa mock và spy

API Framework sử dụng những chiến lược bean override riêng:

| Tình huống | `@MockitoBean` | `@MockitoSpyBean` |
| --- | --- | --- |
| Có đúng một bean phù hợp | Thay bằng Mockito mock | Bọc bean hiện hữu bằng Mockito spy |
| Không tìm thấy bean phù hợp | Mặc định có thể tạo bean mock mới | **Không** tự tạo bean thật để spy; cần bean hiện hữu |
| Nhiều bean cùng type | Cần `@Qualifier`, tên rõ ràng hoặc cơ chế chọn bean phù hợp | Cần chọn **đúng một** bean mục tiêu |
| Cần bảo đảm bean cũ phải tồn tại | Dùng `enforceOverride = true` | Bản chất WRAP yêu cầu bean tồn tại |
| Bean prototype/không singleton | Không nên giả định có thể override tự do; cần xem quy tắc bean override | Spy yêu cầu bean đủ điều kiện, thông thường là singleton |

`@MockitoBean` dùng chiến lược **REPLACE_OR_CREATE** mặc định: nếu không tìm thấy bean, nó có thể **tạo mới** mock. Điều này hữu ích với `@WebMvcTest`/ `@WebFluxTest` vì các slice thường loại service/repository ra khỏi context. Nhưng ở **integration test**, nó có thể che mất lỗi bean cần có lại không được nạp do thay đổi cấu hình.

Muốn phát hiện tình huống bị thiếu bean ở integration context:

```java
@SpringBootTest
class ExternalGatewayIntegrationTest {
    // Nếu bean ExternalGateway không tồn tại, test context phải fail.
    @MockitoBean(enforceOverride = true)
    ExternalGateway gateway;
}
```

`enforceOverride = true` chuyển mục đích thành **REPLACE**: không có bean thì báo lỗi thay vì âm thầm tạo. **Không dùng cờ này máy móc trong controller slice test**, nơi collaborator chủ ý không được quét vào context. `@MockitoSpyBean` dùng chiến lược **WRAP**: phải có đúng một bean hiện hữu để bọc, nên nếu test cũ vô tình phụ thuộc hành vi Boot tạo bean mới từ spy, cần thiết kế lại fixture.

### Hệ quả với bean được tạo bởi FactoryBean

Framework bean override có các quy tắc riêng cho bean xuất phát từ `FactoryBean`. Mock thường thay **đối tượng do factory tạo** bằng mock của type tương ứng; spy cần đối tượng thật để bọc. Vì vậy cần kiểm tra kết quả với các bean như client proxy, persistence proxy hoặc bean qua factory thay vì chỉ tin rằng tên annotation mới có hành vi y hệt. Đừng cấu hình spy vào một bean phải có side effect nhưng không thể khởi tạo an toàn trong test.

## 5. Chọn bean bằng tên, qualifier và field name

Nếu context có nhiều bean cùng interface:

```java
interface NotificationGateway {
    void deliver(String message);
}

@Bean("emailGateway")
NotificationGateway emailGateway() {
    return message -> { /* Fixture: không gửi email thật. */ };
}

@Bean("smsGateway")
NotificationGateway smsGateway() {
    return message -> { /* Fixture: không gửi SMS thật. */ };
}
```

Field `@MockitoBean NotificationGateway gateway` có thể **mơ hồ**, vì Spring không biết phải thay bean nào. Hãy khai báo cụ thể:

```java
@MockitoBean(name = "emailGateway")
NotificationGateway emailGateway;
```

Hoặc kết hợp field và qualifier:

```java
@MockitoBean
@Qualifier("smsGateway")
NotificationGateway smsGateway;
```

Tên field có thể được dùng như qualifier **dự phòng** khi có nhiều candidate. Điều đó cũng ảnh hưởng khả năng **tái sử dụng `ApplicationContext` cache**: hai test tương đương về ý định nhưng đặt tên field khác nhau có thể có bộ qualifier/cache key khác nhau và khiến Spring tạo thêm context. Nên thống nhất tên field theo bean mục tiêu, không đặt tùy tiện `mock1`, `mock2` trong một suite lớn.

Với `@MockitoBean` ở **cấp lớp** thay vì field, dùng `types`:

```java
@MockitoBean(types = {ExternalPricingClient.class, NotificationGateway.class})
@SpringBootTest
class BulkOverrideTest {
    // Có mock bean theo các type khai báo, không cần field.
}
```

Khi định danh bean bằng **tên** ở class-level, cần bảo đảm cú pháp `name` và `types` tuân thủ ràng buộc của phiên bản Framework Test (một tên chỉ xác định một bean/type). Không sao chép thẳng `@MockBean(classes = ...)` nếu tham số `classes` không tồn tại trên annotation mới.

### Context hierarchy

Trong ứng dụng dùng `@ContextHierarchy`, override có thể ảnh hưởng nhiều mức context nếu không giới hạn. API Framework có cơ chế `contextName` để ràng buộc override vào mức context cụ thể. Nếu application có parent context chứa authentication provider và child context chứa MVC controller, hãy xác định rõ **bean cần mock thuộc tầng nào**. Thay nhầm parent security bean có thể làm cả bộ test authorization trở nên vô nghĩa.

## 6. So sánh thuộc tính: không được đổi tên máy móc

Một số thuộc tính được gọi khác nhau giữa API Spring Boot Test cũ và Spring Framework Test mới. Bảng sau là **điểm bắt đầu để review**, không thay thế việc xem signature annotation đúng với dependency đã khóa trong nhánh:

| Ý định cấu hình | Boot `@MockBean`/`@SpyBean` cũ | Framework `@MockitoBean`/`@MockitoSpyBean` mới |
| --- | --- | --- |
| Mock một field bean | `@MockBean` | `@MockitoBean` |
| Spy một field bean | `@SpyBean` | `@MockitoSpyBean` |
| Chọn bean theo tên | `name` hoặc tên field/qualifier | `name`, `@Qualifier` hoặc tên field dự phòng |
| Chọn nhiều type ở cấp lớp | `classes`/`value` (tùy annotation cũ) | `types` |
| Mockito default `Answers` | `answer` với mock | `answers` với mock |
| Tự động reset giữa các test | `reset` | `reset` với kiểu enum của package/framework tương ứng |
| Mock chỉ khi bean đã tồn tại | Tùy semantics API cũ | `@MockitoBean(enforceOverride = true)` |
| Proxy handling riêng của Boot spy | Có một số option như `proxyTargetAware` ở API cũ | Không giả định có option một-một; review AOP/proxy |
| Kiểu ghi đè spy | Theo hỗ trợ của Spring Boot Test | WRAP bean hiện hữu, không tạo bean thật khi vắng mặt |

Ví dụ yêu cầu Mockito dùng câu trả lời thông minh cho mock:

```java
// Nhánh cũ:
@MockBean(answer = Answers.RETURNS_SMART_NULLS)
RemoteDirectory directory;

// Nhánh dùng Spring Framework Test:
@MockitoBean(answers = Answers.RETURNS_SMART_NULLS)
RemoteDirectory directory;
```

Các enum reset có thể có cùng tên như `AFTER`, `BEFORE`, `NONE`, nhưng **package Java khác nhau**. Nếu code cũ import `org.springframework.boot.test.mock.mockito.MockReset`, cần chuyển sang type `org.springframework.test.context.bean.override.mockito.MockReset` khi annotation mới yêu cầu. Nếu test có custom meta-annotation chứa `reset` hoặc `proxyTargetAware`, phải sửa chính meta-annotation cho nhánh mới; chỉ sửa field tại các test callsite là chưa đủ.

## 7. Reset, test isolation và lifecycle của context

Mock trong Spring Test thường được **reset theo cấu hình mặc định sau mỗi method test**. Dù vậy, đừng đặt kỳ vọng bộ test chỉ pass nếu method A chạy trước method B hoặc một stubbing từ bài trước còn tồn tại:

```java
@MockitoBean
DocumentReader reader;

@Test
void documentIsReturned() {
    given(reader.read("doc-a")).willReturn("fixture-a");
    // Chạy request và kiểm tra body trong chính test này.
}
```

Nếu chủ động dùng reset `NONE` để giữ stubbing giữa nhiều request trong **cùng method test**, phải dọn trạng thái đúng cách và giải thích lý do. Đừng dùng `@DirtiesContext` bừa bãi chỉ để che việc fixture mock/spy rò state; nó làm suite chậm đáng kể. Việc test class đổi `@MockitoBean` theo tên/qualifier/metadata có thể làm cache key khác nhau, kéo theo nhiều application context mới trên CI.

Với parallel tests, **không sử dụng chung mock mutable để các test đồng thời stub lại**. Nếu test dùng context cache chứa cùng mock instance, hai method chạy song song có thể ghi đè stubbing hoặc interaction verification của nhau. Cần cô lập context, tránh chạy parallel các test sửa cùng mock, hoặc thiết kế fixture chỉ đọc/tách được theo test.

## 8. Servlet/MockMvc: giữ HTTP security thật khi nâng cấp mock

Xét một endpoint đọc tài liệu từ `DocumentReader`:

```java
interface DocumentReader {
    String read(String id);
}

@RestController
class DocumentsController {
    private final DocumentReader reader;

    DocumentsController(DocumentReader reader) {
        this.reader = reader;
    }

    @GetMapping("/api/documents/{id}")
    String getDocument(@PathVariable String id) {
        return reader.read(id);
    }
}
```

Security chain của **API bearer JWT** yêu cầu `SCOPE_documents.read`:

```java
@Configuration
class DocumentsHttpSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ví dụ test sử dụng **annotation mới để mock đúng collaborator**, còn filter chain và luật bảo mật là bean thật:

```java
@WebMvcTest(controllers = DocumentsController.class)
@Import(DocumentsHttpSecurity.class)
class DocumentsControllerSecurityTest {

    @Autowired MockMvc mvc;

    // Slice test không scan service thật: mock được tạo trong context.
    @MockitoBean DocumentReader reader;

    // Resource server config cần decoder bean để dựng chain.
    // jwt() bỏ qua decoder này; đây KHÔNG phải decoder-validation test.
    @MockitoBean JwtDecoder decoder;

    @Test
    void readerWithAuthorityCanRead() throws Exception {
        given(reader.read("doc-10")).willReturn("fixture-content");

        mvc.perform(get("/api/documents/doc-10")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_documents.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("fixture-content"));

        verify(reader).read("doc-10");
    }

    @Test
    void anonymousIsRejectedBeforeReader() throws Exception {
        mvc.perform(get("/api/documents/doc-10"))
            .andExpect(status().isUnauthorized());

        verifyNoInteractions(reader);
    }

    @Test
    void authenticatedButMissingAuthorityIsRejected() throws Exception {
        mvc.perform(get("/api/documents/doc-10")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_other.read"))))
            .andExpect(status().isForbidden());

        verifyNoInteractions(reader);
    }
}
```

Các static import thường dùng đến từ `SecurityMockMvcRequestPostProcessors.jwt`, `MockMvcRequestBuilders.get`, `MockMvcResultMatchers`, Mockito `given`, `verify`, `verifyNoInteractions`, JUnit 5 `@Test`. Với Boot test slice, cần dependency `spring-security-test`, `spring-test` và Spring Security MVC đang được cấu hình phù hợp. Nếu bạn tự tạo `MockMvcBuilders` thay vì dùng Spring Boot test auto-config, phải áp dụng đúng `springSecurity()` để filter chain thật sự tham gia request.

Vì endpoint chỉ yêu cầu GET, không có tác động CSRF lên các test trên. Nếu chuyển sang POST với cookie/session authentication, cần giữ hoặc kiểm tra CSRF đúng policy; **không tắt CSRF chỉ để migration test xanh**.

### Điều test này chưa chứng minh

`@MockitoBean JwtDecoder` chỉ giải quyết dependency khởi tạo context; vì `.with(jwt())` đã thiết lập JWT principal giả, test không đi qua chữ ký JWT, `exp`, `nbf`, issuer/audience validation. Để kiểm tra decoder thật, dùng test khác có `JwtDecoder` thật và gửi `Authorization: Bearer <signed-test-JWT>`. Không dùng `@MockitoBean` thay decoder trong chính bài test này.

Một cảnh báo khác: nếu `@PreAuthorize` nằm **trên method của `DocumentReader` hoặc một service đang bị mock**, lời gọi mock có thể không đi qua đúng logic/interceptor mà bộ test muốn kiểm chứng. Ví dụ trên cố tình đặt **URL authorization rule trên SecurityFilterChain thật**, giúp 401/403 có ý nghĩa; test method security phải giữ bean/service được bảo vệ thật và chỉ mock collaborator bên dưới.

## 9. Reactive/WebTestClient: giữ WebFilter chain và Mono thật

Với WebFlux, logic tương tự nhưng dùng `SecurityWebFilterChain`, `WebTestClient` và service trả `Mono`:

```java
interface ReactiveDocumentReader {
    Mono<String> read(String id);
}

@RestController
class ReactiveDocumentsController {
    private final ReactiveDocumentReader reader;

    ReactiveDocumentsController(ReactiveDocumentReader reader) {
        this.reader = reader;
    }

    @GetMapping("/api/documents/{id}")
    Mono<String> getDocument(@PathVariable String id) {
        return reader.read(id);
    }
}

@Configuration
@EnableWebFluxSecurity
class DocumentsReactiveSecurity {
    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http.authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

```java
@WebFluxTest(controllers = ReactiveDocumentsController.class)
@Import(DocumentsReactiveSecurity.class)
class ReactiveDocumentsControllerSecurityTest {
    @Autowired WebTestClient client;

    @MockitoBean ReactiveDocumentReader reader;
    @MockitoBean ReactiveJwtDecoder decoder;

    @Test
    void authorizedReactiveRequestReturnsBody() {
        when(reader.read("doc-10"))
            .thenReturn(Mono.just("fixture-content"));

        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read")))
            .get().uri("/api/documents/doc-10")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("fixture-content");

        verify(reader).read("doc-10");
    }

    @Test
    void missingScopeIsForbidden() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_other.read")))
            .get().uri("/api/documents/doc-10")
            .exchange()
            .expectStatus().isForbidden();

        verifyNoInteractions(reader);
    }
}
```

`@WebFluxTest` của Spring Boot thường cấu hình `WebTestClient` cho slice test. Khi tự tạo client từ application context, dùng `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).configureClient().build()` và nạp đúng security chain. Một client `bindToController` thuần có thể bỏ qua security filters; một request 200 lúc đó không chứng minh được quyền.

Với `WebTestClient.bindToServer()` gửi HTTP qua socket, `mockJwt()` không tự truyền principal qua mạng tới server. Cần bearer JWT fixture thực có thể được decoder server chấp nhận. Nếu service Reactive có method security, phải bật `@EnableReactiveMethodSecurity`, giữ đúng bean được proxy và dùng `StepVerifier` để xác minh `onNext`/`onError` ở tầng method; không chỉ kiểm tra `Mono` được tạo.

## 10. `@MockitoSpyBean`: kiểm tra tương tác mà vẫn chạy code thật

Một spy thích hợp khi cần theo dõi hành vi **của bean thật**, nhưng phải tránh spy các đối tượng nhiều side effect không kiểm soát. Ví dụ một recorder test:

```java
@Component
class AuditRecorder {
    private final AtomicInteger writes = new AtomicInteger();

    void record(String eventName) {
        writes.incrementAndGet();
    }

    int writeCount() {
        return writes.get();
    }
}
```

Khi `AuditRecorder` đã là bean trong test context:

```java
@MockitoSpyBean
AuditRecorder auditRecorder;

@Test
void successfulRequestRecordsOneEvent() throws Exception {
    int before = auditRecorder.writeCount();

    mvc.perform(get("/api/audit-fixture")
            .with(user("fixture-reader").roles("USER")))
        .andExpect(status().isOk());

    verify(auditRecorder).record("READ");
    assertEquals(before + 1, auditRecorder.writeCount());
}
```

Đoạn này giả định ứng dụng test có endpoint `/api/audit-fixture` thực sự gọi `auditRecorder.record("READ")`, security config cho phép `ROLE_USER`, và chưa có request khác chạm vào recorder. `verify` kiểm tra lời gọi, còn bộ đếm kiểm tra side effect của **logic thật**. Với test song song, phải cô lập bean/đếm theo request ID để tránh va chạm.

**Lưu ý stubbing spy:**

```java
// Nguy hiểm khi method thật có side effect: dòng này có thể gọi thật.
when(auditRecorder.writeCount()).thenReturn(10);

// Ưu tiên cú pháp không gọi method thật tại thời điểm stubbing:
doReturn(10).when(auditRecorder).writeCount();
```

Không spy trực tiếp `SecurityFilterChain`, `JwtDecoder` hoặc service cần kiểm tra `@PreAuthorize` chỉ để làm test pass. Spy và AOP proxy có thể tương tác phức tạp: hãy xác nhận lời gọi qua đúng Spring proxy, method security thực thi và kết quả 401/403/200 không thay đổi. Nếu không cần quan sát tương tác của bean thật, một mock collaborator rõ ràng thường đơn giản và ổn định hơn.

## 11. Bộ test thất bại ra sao khi thay annotation sai?

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| IDE không tìm được `@MockitoBean` | Spring Framework Test chưa hỗ trợ hoặc import sai | Kiểm tra version `spring-test`, import package Framework mới |
| Context báo thiếu bean khi dùng spy | `@MockitoSpyBean` cần bean hiện hữu để WRAP | Đưa bean thật vào context hoặc dùng mock cho slice không có bean |
| Context báo nhiều candidate cùng type | Bean override chưa chọn rõ tên/qualifier | Dùng `name`/`@Qualifier`, kiểm tra bean được thay đúng |
| Sau migrate, context vẫn khởi động dù bean cấu hình bị mất | `@MockitoBean` mặc định REPLACE_OR_CREATE | Dùng `enforceOverride=true` ở test tích hợp cần bean có sẵn |
| Test 200 dù user thiếu quyền | Security filter chưa nạp, mock nhầm security/service bảo vệ | Kiểm tra real security chain và negative test 401/403 |
| Test `@PreAuthorize` không chặn | Method security tắt hoặc service bị thay mock | Giữ service thật, bật method security, gọi qua proxy |
| JWT expired test vẫn xanh | Mock `JwtDecoder`/`jwt()` bỏ qua validation | Gửi JWT ký test qua decoder thật |
| Spy kích hoạt I/O thật khi stubbing | `when(spy.method())` đã gọi method thật | Dùng `doReturn/doThrow` đúng lúc và tránh spy I/O không cô lập |
| CI chậm sau migration | Bean qualifier/field name khác nhau làm thay đổi context cache | Chuẩn hóa field name/qualifier và dùng context fixture hợp lý |
| Các test ảnh hưởng nhau khi chạy song song | Shared mock/spy stubbing mutable, reset khác chính sách | Cô lập test và lifecycle hoặc tránh chạy song song cùng context |

Một kỹ thuật hữu ích là **mutation check có chủ đích trong môi trường thử nghiệm**: tạm đổi URL rule `hasAuthority("SCOPE_documents.read")` thành `permitAll()` rồi xác nhận test thiếu quyền **phải thất bại**. Nếu test vẫn xanh, bộ test chưa bảo vệ điều cần bảo vệ. Không commit code cố ý làm yếu security rule; đây là phép kiểm tra sức mạnh assertion, không phải phương án sửa.

## 12. Quy trình nâng cấp theo nhánh, không dàn trải

Một quy trình phù hợp cho project lớn:

1. **Khoanh phạm vi:** xác định nhánh target, BOM Spring Boot/Framework Test, Mockito/JUnit và chính sách deprecation. Nếu API mới không tồn tại, chưa chuyển import.
2. **Phân loại test:** Servlet `@WebMvcTest`, Reactive `@WebFluxTest`, `@SpringBootTest`, method security, decoder/introspection/OIDC integration. Mỗi nhóm có cách nạp bean khác nhau.
3. **Chuyển một slice điển hình:** đổi `@MockBean` sang `@MockitoBean` cho collaborator thuần; kiểm tra import/attribute `classes`→`types`, `answer`→`answers` nếu đang sử dụng.
4. **Chuyển spy riêng:** xác minh bean thật tồn tại, không side effect ngoài ý muốn, AOP/proxy và tương tác Mockito còn đúng.
5. **Giữ security thật:** không thay security chain hoặc bean policy cần kiểm tra; tiếp tục kiểm tra anonymous, thiếu quyền và đủ quyền.
6. **Kiểm tra bean selection:** khi nhiều bean, dùng tên/qualifier chính xác; cân nhắc `enforceOverride=true` tại integration test để phát hiện bean biến mất.
7. **Kiểm tra test isolation/cache:** reset mocks, chạy test riêng và chạy cả suite; xác minh không có lỗi do thứ tự hoặc parallelism.
8. **Chạy regression:** Servlet MockMvc, Reactive WebTestClient, `@PreAuthorize` và test token/IdP thật trong nhóm riêng. **Không** coi compile và status 200 là đủ.
9. **Review diff:** đổi đúng import/annotation/attributes; không xóa ca âm tính, không nới lỏng authorization hoặc tắt CSRF vì migration.
10. **Giữ khả năng rollback:** commit thay đổi nhỏ theo loại test/nhánh để dễ truy nguyên nếu context cache hoặc proxy behavior thay đổi.

Đối với bộ test đang có nhiều `@MockBean` class-level hay composed annotations, xem xét viết một bảng chuyển từng trường hợp trước khi thực hiện tìm–thay. Một lệnh replace rộng có thể xóa mất behavior như mock name hoặc reset policy mà compiler không phát hiện vì annotation vẫn được tạo.

## 13. Ma trận hồi quy bảo mật sau migration

| Kịch bản | Test tool | Kỳ vọng sau nâng cấp |
| --- | --- | --- |
| Anonymous vào endpoint Bearer | MockMvc hoặc WebTestClient, không mock principal | 401 hoặc entry point theo contract; collaborator không chạy |
| User có JWT principal nhưng thiếu `SCOPE_documents.read` | `jwt()`/`mockJwt()` | 403; không gọi service trả dữ liệu bảo vệ |
| User đủ authority | JWT fixture đúng, reader mock có stubbing riêng | 200 và body đúng; reader được gọi đúng một lần |
| URL rule được phép nhưng method security từ chối | Service thật có `@PreAuthorize` | Không bỏ qua method interceptor; 403 theo HTTP handling |
| Token hết hạn/sai chữ ký | Bearer JWT ký test và decoder thật | Authentication thất bại, không được dùng mock principal |
| Opaque token `active:false` | Introspection HTTP stub | Không xác thực thành công |
| OIDC nonce/issuer sai | Provider stub, callback thật | Không tạo phiên login thành công |
| Ghi dữ liệu bị từ chối | Repository/database test thật, mock ngoại vi không liên quan | Không có side effect trái phép |
| Spy collaborator chạy code thật | `@MockitoSpyBean` trên bean có sẵn | Interaction được verify và side effect phù hợp, không lặp |

Khi một test dùng `@MockitoBean` cho service chứa rule `@PreAuthorize`, bảng trên phải có **một test khác với service thật** nếu muốn bảo đảm method security chưa bị mất. Cơ chế mock là tiện ích để cô lập dependency, không phải bằng chứng thay thế pipeline bảo mật.

## 14. Bài thực hành: chuyển test Servlet và Reactive có bảo vệ HTTP

Chuẩn bị một project test sử dụng Spring Boot nhánh đã được xác minh hỗ trợ annotation mới. Có hai API mẫu `GET /api/documents/{id}`: một controller Servlet và một controller WebFlux (trong ứng dụng/test context riêng), mỗi API yêu cầu `SCOPE_documents.read`. Cung cấp `DocumentReader`/`ReactiveDocumentReader` dưới dạng collaborator có thể mock; giữ security configuration thật.

1. **Kiểm tra version:** ghi rõ target Boot và Framework Test, xác nhận package `@MockitoBean`/`@MockitoSpyBean` có thể import trước khi sửa.
2. **Chuyển một mock:** từ `@MockBean DocumentReader reader` sang `@MockitoBean DocumentReader reader`. Nếu ở `@WebMvcTest`, dùng mặc định REPLACE_OR_CREATE vì service không thuộc slice.
3. **Chạy bộ ba HTTP Servlet:** anonymous 401, JWT principal thiếu scope 403, JWT principal đủ scope 200 và body đúng; ở hai ca từ chối dùng `verifyNoInteractions(reader)`.
4. **Chuyển Reactive:** tương tự với `@WebFluxTest`, `@MockitoBean ReactiveDocumentReader`, `Mono.just(...) ` và `WebTestClient`. Xác minh filter `SecurityWebFilterChain` thật.
5. **Chọn bean theo tên:** thêm hai implementation cùng interface rồi dùng `@MockitoBean(name = "...")`; chứng minh bean không liên quan không bị thay.
6. **Kiểm tra `enforceOverride`:** ở một integration test đã có bean thật, bật `@MockitoBean(enforceOverride = true)`; thử cố ý bỏ bean và quan sát context phải fail.
7. **Chuyển spy:** dùng `@MockitoSpyBean` trên `AuditRecorder` đã tồn tại, verify lời gọi và xác nhận logic thật chạy. Dùng `doReturn` khi stub method có side effect.
8. **Kiểm tra mock không che bảo mật:** giữ một test `@PreAuthorize` trên service thật; tạm bỏ authority và xác nhận bị từ chối.
9. **Kiểm tra cơ chế xác thực thật:** test decoder/opaque introspection/OIDC callback riêng; không mock thành phần cần xác thực ở đúng bài test đó.
10. **Kiểm tra CI:** chạy toàn suite với parallelism thực tế, rà lifecycle/reset/context cache; lưu log lỗi không chứa credentials, secret hoặc raw token.

### Tiêu chí hoàn thành

- Chỉ chuyển khi nhánh mục tiêu có Spring Framework Test API tương thích.
- Không còn import Boot annotation cũ trong phạm vi đã chuyển; thuộc tính và tên/qualifier được ánh xạ đúng.
- Hiểu khác biệt **REPLACE_OR_CREATE** của `@MockitoBean` với **WRAP** của `@MockitoSpyBean`; dùng `enforceOverride` khi cần phát hiện bean thiếu.
- Bộ test Servlet và Reactive vẫn có ca **được phép và bị từ chối** (200/401/403), kiểm tra body hoặc tác dụng phụ.
- Không mock mất chính bean/security interceptor cần kiểm chứng; có test service/method security thật.
- Mock/spy được reset và sử dụng an toàn giữa test; bộ test có thể chạy lại trên CI.
- Không dùng mock decoder hay mock principal để tuyên bố đã kiểm tra signature, issuer, nonce hoặc HTTP introspection.

## Ghi nhớ

**Chuyển `@MockBean`/`@SpyBean` sang `@MockitoBean`/`@MockitoSpyBean` là một thay đổi về cách Spring Test override bean, không chỉ đổi tên annotation.** Trước tiên hãy xác định đúng nhánh và phiên bản; tiếp theo kiểm tra cú pháp, tên bean, qualifier, reset và sự khác biệt giữa tạo mock với bọc bean thật bằng spy. Trong **SPRING_SECURITY_TESTING**, giữ security filter/method security cần kiểm chứng là **thật**, mock đúng collaborator và chạy lại các ca HTTP 200/401/403 trên MockMvc/WebTestClient. Việc code compile chỉ là bước đầu; bộ kiểm thử chỉ bảo vệ được ứng dụng khi những request thiếu quyền vẫn bị chặn và những request đủ quyền vẫn có kết quả chính xác sau nâng cấp.
