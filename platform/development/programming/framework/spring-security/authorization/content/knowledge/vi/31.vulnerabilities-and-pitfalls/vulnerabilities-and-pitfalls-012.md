# Lỗi dịch vụ chính sách dẫn đến vô tình cho phép truy cập

## Mục tiêu học tập

Một hệ thống có thể xác thực người dùng đúng, cấu hình endpoint đúng, nhưng vẫn **cấp quyền nhầm** khi dịch vụ ra quyết định chính sách (policy service) bị timeout, mất kết nối, trả phản hồi không hợp lệ hoặc tạm thời chưa sẵn sàng. Lỗi cốt lõi là ứng dụng hiểu “không lấy được kết quả phân quyền” thành “được phép truy cập” — **fail-open**.

Sau bài này, bạn có thể:

1. Phân biệt kết quả **PERMIT**, **DENY** với lỗi **INDETERMINATE**, **NOT_APPLICABLE**, phản hồi rỗng và lỗi hạ tầng.
2. Chỉ ra điểm fail-open trong luồng Spring Security sử dụng policy service/PDP bên ngoài.
3. Triển khai ranh giới phân quyền **fail-closed**: chỉ cho phép khi nhận **PERMIT tường minh, hợp lệ và đúng ngữ cảnh**; trường hợp còn lại không cho chạy thao tác được bảo vệ.
4. Thiết kế timeout, retry, circuit breaker, cache, giám sát để duy trì tính sẵn sàng mà không vô tình tăng quyền.
5. Viết kiểm thử có chủ đích gây lỗi policy service, chứng minh controller/service/repository không xử lý thao tác trái quyền.

## 1. Tình huống: dịch vụ quyết định quyền tạm thời không hoạt động

Giả sử API `GET /api/documents/42` yêu cầu người dùng đã đăng nhập và còn cần quyết định theo từng tài liệu:

- **PEP (Policy Enforcement Point)**: vị trí chặn yêu cầu và thực thi quyết định, ví dụ `AuthorizationManager`, `@PreAuthorize` hoặc lớp service chuyên trách trong ứng dụng Spring.
- **PDP (Policy Decision Point)**: dịch vụ chính sách quyết định có cho chủ thể thực hiện hành động trên tài nguyên hay không, có thể là một policy engine từ xa.
- **PIP (Policy Information Point)**: nguồn thông tin để quyết định, chẳng hạn tenant, owner, phân loại tài liệu, quan hệ tổ chức, policy version; các thuộc tính quan trọng phải đến từ nguồn được server tin cậy.

Luồng bình thường:

```text
Client (đã xác thực)
    |
    v
Spring Security + PEP  -- yêu cầu quyết định: user, tenant, action, resource --> PDP
    |                                                                   |
    |<-------------------------- PERMIT / DENY -------------------------|
    |
    +-- PERMIT hợp lệ --> đọc dữ liệu / thực hiện thao tác
    |
    +-- DENY hoặc không có quyết định đáng tin --> chặn
```

Khi PDP bị lỗi, cách xử lý nguy hiểm thường xuất hiện trong một đoạn code trông vô hại:

```java
// SAI: chỉ để nhận diện lỗi; tuyệt đối không dùng trong hệ thống thực.
boolean canRead(PolicyRequest request) {
    try {
        return policyClient.evaluate(request).isPermit();
    } catch (Exception ex) {
        return true; // FAIL-OPEN: mất policy service đồng nghĩa được phép đọc!
    }
}
```

Nếu attacker hoặc sự cố mạng làm policy service không phản hồi, toàn bộ request đi qua nhánh `return true`. Khi đó một tài khoản ít quyền có thể đọc tài liệu không thuộc mình; với API ghi/xóa/xuất dữ liệu, hậu quả còn nặng hơn. Một biến thể khác là “policy service lỗi thì chỉ kiểm tra `authenticated()`” — vẫn sai khi chính sách yêu cầu owner, tenant, ACL, mức độ nhạy cảm hoặc tình trạng phê duyệt.

**Nguyên tắc:** ở chỗ bắt buộc có quyết định phân quyền, **không có kết quả PERMIT đáng tin thì không thực hiện hành động được bảo vệ**. “Không quyết định được” không đồng nghĩa “DENY nghiệp vụ” về mặt chẩn đoán, nhưng đều phải dẫn đến **không cấp quyền** tại PEP.

## 2. Phân biệt quyết định nghiệp vụ và lỗi đánh giá chính sách

Không mọi hệ thống PDP dùng cùng tập trạng thái. Bảng sau là **hợp đồng minh họa**; ứng dụng phải ánh xạ nghiêm ngặt từ giao thức PDP thực tế.

| Kết quả/điều kiện | Ý nghĩa | PEP có được tiếp tục thao tác? |
| --- | --- | --- |
| `PERMIT` hợp lệ | Chính sách khẳng định cho phép đúng subject, tenant, action, resource, điều kiện và phiên bản | **Có**, sau khi kiểm tra mọi obligation/constraint bắt buộc |
| `DENY` | Chính sách khẳng định không cho phép | **Không** |
| `NOT_APPLICABLE` | Không có quy tắc áp dụng; **không phải** PERMIT | **Không**, trừ khi có quy tắc tổng hợp đã định nghĩa rõ và tự trả kết quả PERMIT hợp lệ |
| `INDETERMINATE` | PDP không thể đưa quyết định chắc chắn | **Không** |
| Timeout, DNS, TLS, connection reset, HTTP 5xx | Không có quyết định đáng tin | **Không** |
| HTTP 200 nhưng body trống, JSON sai schema, trạng thái lạ, `null` | Không thể xác minh kết quả | **Không** |
| Đáp án thuộc user/tenant/resource/action khác hoặc bị replay | Kết quả không đúng ngữ cảnh | **Không** |
| Cache PERMIT đã hết hạn hoặc bị thu hồi | Quyền không còn được xác nhận | **Không** |
| Chưa đăng nhập, principal không hợp lệ | Không có danh tính đủ tin cậy | **Không** |

**Chỉ kiểm tra HTTP status của PDP là không đủ.** HTTP 200 chỉ nói request gọi service thành công ở mức transport. Phản hồi phải được xác thực theo schema, result, ngữ cảnh request và các ràng buộc của chính sách; không được diễn giải kiểu `"allow"` vắng mặt thành true, `"deny": false` thành allow, hoặc giá trị bất kỳ khác `"deny"` thành PERMIT.

Nếu PDP trả PERMIT kèm obligation như “chỉ hiển thị bản đã che” hoặc “giới hạn trong khoảng thời gian được phép” thì PEP phải thực thi obligation đó. Nếu PEP không thể thực thi nghĩa vụ bắt buộc, kết quả không đủ điều kiện cấp quyền. Đối với nhiều chính sách, thứ tự kết hợp (deny-overrides, permit-overrides, v.v.) phải là **quy tắc đã được phê duyệt**; một thành phần `NOT_APPLICABLE` hoặc lỗi không được tự động nâng lên ALLOW.

### Fail-open và fail-closed

- **Fail-open:** “PDP không trả lời → cấp quyền như thể PERMIT”. Bảo toàn một phần availability bằng cách hy sinh ranh giới bảo mật.
- **Fail-closed:** “PDP không trả lời → không cho thao tác được bảo vệ đi tiếp”. Bảo toàn ranh giới quyền, có thể làm chức năng tạm thời không sẵn sàng.
- **Fail-secure theo từng phạm vi:** những endpoint thật sự công khai có quy tắc `permitAll()` **tường minh và độc lập** với PDP vẫn được phục vụ; những thao tác cần policy phải đóng khi thiếu quyết định. Đây là phân loại quyền thiết kế trước, không phải tự động nới quyền lúc có lỗi.

Ví dụ: `GET /health` được đánh dấu public từ đầu có thể tiếp tục trả trạng thái hạ tầng; `GET /api/documents/42` không được dùng sự cố PDP làm lý do bỏ kiểm tra ACL. Nếu chính sách bảo mật quy định tất cả đường đọc cần PDP, không có ngoại lệ tự đặt.

## 3. Một lỗi nhỏ trong Java có thể thay đổi toàn bộ hợp đồng

Đoạn dưới đây **chạy độc lập trên Java 17+**, mô phỏng một adapter nơi kết quả không hợp lệ hoặc exception phải không cấp quyền. Tên file phải đúng `FailClosedDemo.java`:

```java
public class FailClosedDemo {
    enum Decision {
        PERMIT, DENY, NOT_APPLICABLE, INDETERMINATE
    }

    @FunctionalInterface
    interface PolicyClient {
        Decision query();
    }

    static boolean authorized(PolicyClient client) {
        try {
            return client.query() == Decision.PERMIT;
        } catch (RuntimeException failure) {
            return false;
        }
    }

    public static void main(String[] args) {
        for (Decision d : Decision.values()) {
            System.out.println(d + " -> " + authorized(() -> d));
        }
        System.out.println("NULL -> " + authorized(() -> null));
        System.out.println("TIMEOUT -> " + authorized(() -> {
            throw new IllegalStateException("timeout");
        }));
    }
}
```

Biên dịch/chạy:

```bash
javac FailClosedDemo.java
java FailClosedDemo
```

Stdout chính xác:

```text
PERMIT -> true
DENY -> false
NOT_APPLICABLE -> false
INDETERMINATE -> false
NULL -> false
TIMEOUT -> false
```

Điểm mấu chốt không phải mọi exception trong ứng dụng đều nên bị nuốt. **Chỉ những lỗi xảy ra trong đường đánh giá policy** cần được chuyển thành “không cấp quyền”, đồng thời có log/metric/cảnh báo. Lỗi lập trình không dự kiến cũng không được khiến thao tác tiếp tục; có thể để exception nổi lên thành lỗi máy chủ và ngừng xử lý request. Trong production, phải biết **vì sao** PDP từ chối hay không sẵn sàng, không gộp hết nguyên nhân thành một kết quả log vô danh.

## 4. Tích hợp fail-closed ở ranh giới Spring Security

Spring Security quản lý authentication, request authorization và method authorization; nó **không mặc định biến mọi lỗi dịch vụ chính sách từ xa thành PERMIT**. Rủi ro phát sinh khi ứng dụng tự thêm callback, `AuthorizationManager`, SpEL, custom filter hoặc client fallback có logic cho phép sai.

Một chiến lược đơn giản là giữ lớp service được bảo vệ bởi `@PreAuthorize`, và dùng một bean chính sách chỉ trả `true` với PERMIT rõ ràng. Các snippet sau là **mã tích hợp vào một ứng dụng Spring Boot 3.x/Spring Security 6.x**, không phải một chương trình độc lập; entity, repository, HTTP client, cấu hình DI và import phải có trong dự án.

### 4.1. Adapter quyết định: chỉ PERMIT mới được phép

Ví dụ file `DocumentPolicy.java` (các kiểu hỗ trợ có thể tách thành file riêng trong dự án):

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

enum PolicyDecision {
    PERMIT, DENY, NOT_APPLICABLE, INDETERMINATE
}

record PolicyQuery(
        String subjectId, String tenantId, String action, long documentId) {}

record PolicyResult(PolicyDecision decision) {}

interface RemotePolicyClient {
    PolicyResult evaluate(PolicyQuery query);
}

interface TenantIdentity {
    String verifiedTenant(Authentication authentication);
}

@Component("documentPolicy")
public final class DocumentPolicy {
    private static final Logger log =
            LoggerFactory.getLogger(DocumentPolicy.class);

    private final RemotePolicyClient remote;
    private final TenantIdentity tenants;

    public DocumentPolicy(RemotePolicyClient remote, TenantIdentity tenants) {
        this.remote = remote;
        this.tenants = tenants;
    }

    public boolean canRead(Authentication actor, long documentId) {
        if (actor == null
                || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken
                || documentId <= 0) {
            return false;
        }

        try {
            String tenantId = tenants.verifiedTenant(actor);
            if (tenantId == null || tenantId.isBlank()) {
                return false;
            }

            PolicyQuery query = new PolicyQuery(
                    actor.getName(), tenantId, "document:read", documentId);
            PolicyResult result = remote.evaluate(query);

            return result != null
                    && result.decision() == PolicyDecision.PERMIT;
        } catch (RuntimeException policyEvaluationFailure) {
            log.warn("Policy evaluation failed; access denied (type={})",
                    policyEvaluationFailure.getClass().getSimpleName());
            return false;
        }
    }
}
```

Đây là **quy tắc deny-by-default ở PEP**, với các ràng buộc quan trọng:

- `TenantIdentity.verifiedTenant(...)` phải lấy tenant từ nguồn danh tính đáng tin (ví dụ claims JWT đã được kiểm tra chữ ký và audience/issuer, hoặc phiên đăng nhập đã được xác thực); không dùng `?tenant=...` do caller tự truyền.
- `RemotePolicyClient` chịu trách nhiệm thiết lập deadline, xử lý TLS/chứng thực với PDP, validate response schema và kiểm tra ràng buộc request–response nếu giao thức hỗ trợ; mọi parse/transport failure không được được chuyển thành PERMIT.
- PDP phải dựa trên thuộc tính tài liệu **đáng tin** (owner, tenant, classification, ACL) lấy từ source of truth. Chỉ gửi `documentId` + tenant từ caller mà không kiểm tra quan hệ resource–tenant tại PDP sẽ tạo lỗi IDOR khác.
- Chỉ trả PERMIT khi obligations bắt buộc có thể thực thi. Ví dụ trên giả định chính sách không phát sinh obligations; nếu có, kiểu `PolicyResult` phải mang thông tin và PEP phải xác nhận trước khi trả `true`.
- `catch (RuntimeException)` chỉ bao quanh đánh giá chính sách và trả không cấp quyền; trong hệ thống thực hãy thêm metric/structured audit an toàn, xử lý các lỗi đã biết tường minh và bảo đảm cả lỗi không dự kiến đều **ngừng thao tác**. Không log token, raw document hoặc bí mật của PDP.

### 4.2. Đặt chốt bảo vệ trước thao tác có side effect

Ví dụ service và controller (mỗi public class nằm trong file Java phù hợp):

```java
// DocumentService.java
@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
    public DocumentDto read(@P("documentId") long documentId) {
        Document entity = repository.findById(documentId)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
        return new DocumentDto(entity.getId(), entity.getTitle());
    }
}

// DocumentController.java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public DocumentDto read(@PathVariable long documentId) {
        return service.read(documentId);
    }
}
```

Cấu hình cần bật method security và đặt luật request rõ ràng; ví dụ:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .authenticated()
                .anyRequest().denyAll());
        return http.build();
    }
}
```

Các `import` (ví dụ `@P` từ `org.springframework.security.access.method.P`) cần có trong file thực tế. Chốt `authenticated()` đảm bảo danh tính ở mức request; `@PreAuthorize` đảm bảo quyết định **trên tài liệu cụ thể**. Không thay `@PreAuthorize` bằng `authenticated()` khi PDP lỗi. Luật `anyRequest().denyAll()` tránh vô tình để route mới mở nếu chưa được review.

Method security hoạt động qua Spring AOP proxy, nên cần gọi `DocumentService.read` qua Spring-managed bean; self-invocation như `this.read(...)` trong cùng class có thể bỏ qua interceptor. Đừng coi controller là đường gọi duy nhất: batch job, message consumer hay một service khác cũng cần tôn trọng quyền ở ranh giới nghiệp vụ thích hợp.

**Lưu ý về kết quả HTTP:** với mẫu `@PreAuthorize` trả false, một caller đã xác thực thường nhận **403** từ tầng phân quyền. Caller chưa xác thực đi vào cơ chế authentication entry point, thường là **401** đối với API, tùy cấu hình. Nếu cần phân biệt “PDP lỗi” với “PDP DENY” cho client và trả **503**, hãy thiết kế đường lỗi unavailable riêng, đảm bảo nó **ngừng** thao tác bảo vệ, không tự biến thành allow hoặc rò dữ liệu. Status code cụ thể phải được chứng minh bằng integration test với filter chain/exception handler thật.

## 5. Những mẫu code dễ gây fail-open

### 5.1. Giá trị mặc định nguy hiểm

```java
// SAI: mặc định true và chỉ cập nhật khi remote call thành công.
boolean permitted = true;
try {
    permitted = remotePolicyAllows();
} catch (RuntimeException ignored) {
    // permitted vẫn true
}
return permitted;
```

Cách đúng là **giá trị mặc định không cấp quyền**, chỉ nâng thành cho phép sau khi có kết quả hợp lệ. Có thể biểu diễn nguyên tắc bằng `result != null && result.decision() == PERMIT` như phần trước.

### 5.2. Fallback rộng thành `permitAll()`

```java
// SAI: config cho phép tất cả request khi chưa tìm được policy bean.
if (!policyServiceConfigured) {
    http.authorizeHttpRequests(a -> a.anyRequest().permitAll());
}
```

Thiếu policy service là vấn đề cấu hình hoặc khả dụng, không phải lý do để bỏ security. Chỉ endpoint được thiết kế công khai ngay từ đầu mới dùng `permitAll()`. Cần review `SecurityFilterChain` theo thứ tự matcher (matcher được xét tuần tự trong DSL) và phải có test các route nhạy cảm. Cẩn trọng với nhiều filter chain, profile test/dev bị bật ở production, rule fallback sau nâng cấp, và custom filter đặt sai vị trí.

### 5.3. Coi “không có DENY” là PERMIT

```java
// SAI: null hoặc trạng thái lạ sẽ được cho phép.
return response == null || response.decision() != PolicyDecision.DENY;
```

So sánh chỉ với `PERMIT` được xác thực là an toàn hơn; `NOT_APPLICABLE`/`INDETERMINATE` không phải ALLOW. Nếu policy engine có semantics nhiều luật phức tạp, phải kết hợp các luật bên PDP trước khi phát một quyết định cuối; PEP không tự sáng tác cách hiểu trạng thái thiếu.

### 5.4. Lỗi JSON, timeout, HTTP 5xx và code client ngầm “default true”

Một số SDK/client deserialize field boolean thiếu thành `false`; đoạn khác lại dùng `Boolean.TRUE.equals(...)`; một wrapper mới có thể khai báo `Optional.orElse(true)` hoặc resilience library `fallbackMethod` trả true. Kiểm tra **toàn bộ đường đi** từ HTTP PDP response → adapter → cache → gate → security expression, không chỉ hàm ở controller. Cấm hồi phục từ timeout thành PERMIT bằng `onErrorReturn(true)`, `exceptionally(ex -> true)`, `onErrorResume(... -> Mono.just(true))` hoặc tương đương trong reactive code.

### 5.5. Khi cache PERMIT cũ trở thành đường vượt quyền

Cache theo mỗi `documentId` mà bỏ `subjectId`, `tenantId` hoặc `action` có thể trả PERMIT của người khác. Cache PERMIT quá lâu khiến quyết định tiếp tục sống sau khi bị thu hồi quyền. Khi PDP lỗi, “đọc mọi quyết định cũ” đặc biệt nguy hiểm. Cache cần key đủ ngữ cảnh, chính sách hiệu lực/phiên bản, TTL ngắn theo độ nhạy cảm và cơ chế thu hồi; cache miss/expired không được nâng thành allow. Không cache tràn qua tenant, role, mục đích truy cập hoặc phiên bản policy.

Có các thiết kế hoạt động offline theo policy đã ký và kiểm soát hạn sử dụng, nhưng phải được **đặc tả và đánh giá riêng**. Không tự coi stale PERMIT là an toàn trong mọi hệ thống.

## 6. Kiểm thử lỗi dịch vụ chính sách: chứng minh không có dữ liệu được truy cập

Không dừng ở unit test một hàm `canRead()`. Cần xác nhận toàn bộ Spring Security chain, method interceptor và lớp thực thi công việc. Với endpoint đọc, kiểm tra status, body không lộ dữ liệu và **repository không được gọi**; với thao tác ghi/xóa, kiểm tra side effect bằng database thật. Đặt fixture có user/tenant/tài liệu ngoài quyền để thấy được lỗi.

Ví dụ test dựa trên `DocumentPolicy` và `DocumentService` ở trên. Giả định application đã cung cấp controller/repository và các bean; `@MockBean` dùng ở Spring Boot 3.3, kiểm thử phải có đủ imports của JUnit, Mockito, Spring Test Security và Spring MVC:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PolicyUnavailableHttpTest {
    @Autowired MockMvc mvc;

    @MockBean RemotePolicyClient remote;
    @MockBean TenantIdentity tenants;
    @MockBean DocumentRepository repository;

    @BeforeEach
    void trustedTenant() {
        when(tenants.verifiedTenant(any(Authentication.class)))
                .thenReturn("tenant-a");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void timeoutDoesNotReadProtectedDocument() throws Exception {
        when(remote.evaluate(any(PolicyQuery.class)))
                .thenThrow(new IllegalStateException("timeout"));

        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden())
                .andExpect(content().string(""));

        verifyNoInteractions(repository);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void missingResponseNeverMeansPermit() throws Exception {
        when(remote.evaluate(any(PolicyQuery.class))).thenReturn(null);

        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden());

        verifyNoInteractions(repository);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void indeterminateDecisionNeverMeansPermit() throws Exception {
        when(remote.evaluate(any(PolicyQuery.class)))
                .thenReturn(new PolicyResult(PolicyDecision.INDETERMINATE));

        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden());

        verifyNoInteractions(repository);
    }
}
```

Kiểm thử ví dụ giả định filter chain thực sự kích hoạt method security, MockMvc dùng application context thật và response 403 không có body. Nếu ứng dụng có custom `AccessDeniedHandler` tạo JSON lỗi, thay assertion body rỗng bằng kiểm tra **không xuất hiện nội dung tài liệu/canary** và cấu trúc lỗi đã thỏa thuận. Nếu `DocumentPolicy` trả false nhưng service vẫn đọc dữ liệu, phải kiểm tra Spring proxy/method security, không sửa kỳ vọng test cho qua.

Nên thêm test độc lập cho kết quả `PERMIT` hợp lệ (đi qua đúng tài nguyên), `DENY`, `NOT_APPLICABLE`, null, malformed payload, missing fields, thông tin thiếu tenant và user không xác thực. Test từ HTTP với principal/JWT thật xác minh token đã kiểm chứng và các claim không thể bị thay bằng header hoặc query do client tự gửi.

### Ma trận fault injection

| Sự cố cố ý gây ra | Kết quả bắt buộc | Điều cần xác minh |
| --- | --- | --- |
| PDP không kết nối được, DNS lỗi hoặc TLS sai | Không cấp quyền | Không đọc/ghi tài nguyên; request kết thúc hữu hạn |
| PDP trả 500/502/503 hoặc timeout | Không cấp quyền | Không fallback thành allow, có metric theo loại lỗi |
| JSON rỗng, hỏng, trường quyết định thiếu hoặc lạ | Không cấp quyền | Không diễn giải `null`/unknown là PERMIT |
| PDP trả `DENY` | Từ chối nghiệp vụ | Không biến DENY thành retry rồi PERMIT tùy tiện |
| PDP trả `NOT_APPLICABLE`/`INDETERMINATE` | Không cấp quyền | Không có đường “không DENY tức ALLOW” |
| PDP trả PERMIT sai user/tenant/resource/action | Không cấp quyền | Request–response binding và nguồn attributes đáng tin |
| User bị rút quyền khi PERMIT cũ còn cache | Không được dùng quyết định đã hết hiệu lực | Cache key, TTL, invalidation, policy version |
| Circuit breaker mở sau nhiều lỗi | Không cấp quyền | Không gọi side effect; trả lỗi có thể dự báo |
| Service khởi động khi PDP chưa cấu hình | Không cấp quyền cho API cần PDP | Startup/readiness rõ ràng; không bật `permitAll()` |
| Nhiều request đồng thời khi PDP lỗi | Không cấp quyền cho mọi request liên quan | Không có shared mutable boolean “last allow” |
| PDP phục hồi | PERMIT hợp lệ mới cho phép | Đường phục hồi không giữ “default deny” vĩnh viễn hoặc stale allow |

**Đoạn integration test mẫu** kiểm tra proxy và endpoint; một bộ acceptance test nên thêm fault injection ở HTTP client thật (mock server trả 5xx/delay/body sai), và một test dữ liệu để khẳng định không có thao tác DB/side effect. Nếu logic dùng retry/circuit breaker/cache, test riêng cho từng trạng thái có thể làm phát sinh grant sai.

## 7. Tăng độ bền mà không mở quyền

Fail-closed đôi khi làm một API tạm không khả dụng. Giải quyết tính sẵn sàng ở **hạ tầng và policy design**, không bằng cách trả true trong catch:

1. **Timeout/deadline rõ ràng:** đặt connect timeout và overall response deadline phù hợp SLA; không để request treo vô hạn. Deadline kết thúc mà không có quyết định thì chặn.
2. **Retry giới hạn:** chỉ retry lỗi có thể phục hồi, số lần nhỏ, exponential backoff/jitter, tôn trọng deadline và ngân sách tải. Nếu retry hết mà không có PERMIT, chặn. Không retry cả thao tác nghiệp vụ có side effect chỉ vì PDP chưa phản hồi.
3. **Circuit breaker:** khi PDP liên tục thất bại, ngừng gọi trong thời gian ngắn và trả kết quả unavailable/deny; không dùng fallback trả allow. Có half-open probes và metric để phục hồi.
4. **Đa bản sao và health/readiness:** tăng khả năng sẵn sàng của PDP, giới hạn tài nguyên bằng bulkhead, giám sát queue/saturation. Readiness có thể phản ánh việc không xử lý được yêu cầu cần PDP; health endpoint public không được tiết lộ secret.
5. **Caching có ranh giới:** nếu chính sách cho phép cache, cache đúng actor–tenant–resource–action–phiên bản/điều kiện, TTL nghiêm ngặt và xử lý thu hồi. Không tái sử dụng PERMIT quá hạn như cách “sửa” outage.
6. **Phân biệt lỗi với deny trong quan sát:** `policy_decision_total{outcome=permit|deny|unavailable|invalid}`, latency/timeout, circuit-breaker state và correlation ID. Không nhét token, email, raw policy input vào metric label.
7. **Chính sách ngoại lệ minh bạch:** endpoint công khai hoặc nội dung offline đã được duyệt phải được định nghĩa trước với phạm vi/hạn dùng cụ thể. Quyền “break-glass” phải có cơ chế chủ đích, xác thực mạnh, audit và hết hạn; không tự phát sinh vì policy service lỗi.

Trong hệ thống có hiệu lực quyền thay đổi theo thời gian (vừa bị khóa tài khoản, chuyển tenant, thu hồi ACL), ưu tiên freshness và khả năng thu hồi. Một cache PERMIT cũ có thể khiến thất bại fail-closed ở code vẫn **thực chất fail-open về hiệu lực quyền**.

### 403 hay 503 khi PDP outage?

Hai mục tiêu khác nhau:

- **Phân quyền:** thao tác không được thực hiện khi thiếu PERMIT.
- **Giao thức/trải nghiệm:** có thể báo 403 cho lệnh bị gate từ chối, hoặc báo 503 “authorization service temporarily unavailable” nếu tầng ngoại lệ phân biệt được sự cố và contract cho phép. Không tiết lộ chi tiết nội bộ hay xác nhận tài nguyên nhạy cảm có tồn tại.

Nếu cần 503 và client retry, vẫn không trả data và không commit transaction; tuyệt đối không đổi response sang 200 để “giữ UX”. Một kết quả 403 trong outage cũng cần alert, vì đây là sự cố hạ tầng chứ không phải đột nhiên tất cả tài khoản bị policy DENY. Đừng chỉ dựa vào HTTP code để thống kê quyết định của PDP.

## 8. Mối nguy tinh vi trong ứng dụng nhiều tầng

**TOCTOU (time-of-check/time-of-use).** Nếu PEP kiểm tra dựa trên owner/tenant của tài liệu, rồi dữ liệu được chuyển chủ sở hữu trước khi service cập nhật, quyết định có thể không còn đúng lúc thao tác thực hiện. Với thao tác quan trọng, phối hợp kiểm tra và ghi trong transaction/conditional update theo policy hoặc kiểm tra lại ở đúng ranh giới dữ liệu; đừng coi PERMIT bất biến mãi.

**Phân quyền theo đường dẫn nhưng thiếu phân quyền theo dữ liệu.** `requestMatchers("/api/documents/**").authenticated()` chỉ chặn anonymous. Nó không kiểm tra tài liệu 42 thuộc ai. Policy service lỗi càng không làm biến mất yêu cầu kiểm tra tài nguyên; phải có PDP/local decision ở mức row/object.

**Self-invocation và các đường gọi khác.** `@PreAuthorize` trên một public service method có thể không chạy khi gọi nội bộ bằng `this.method()`. Background job, message listener, GraphQL resolver, API khác có thể gọi service theo đường không qua chốt. Test luồng thực tế và giữ quyền ở tầng không dễ bị bỏ qua.

**Không đồng nhất source of truth.** PDP tin role/tenant do client gửi có thể trả PERMIT cho ngữ cảnh giả; dù PDP ổn định, đó vẫn là lỗ hổng. Subject attributes phải được chứng thực, resource attributes phải từ dữ liệu đáng tin. Một response PERMIT chỉ có ý nghĩa khi nó gắn đúng subject/action/resource/policy conditions.

**Lỗi chỉ xảy ra khi deploy.** Local mocks thường luôn trả PERMIT/DENY, trong khi cấu hình production có thể thiếu URL PDP, token hết hạn, cert rotate, DNS trục trặc, mTLS sai, schema thay đổi hoặc feature flag tắt policy. Test deploy/chaos cần dùng dữ liệu thật được cách ly và xác nhận “PDP down ⇒ no grants”.

**Reactive/asynchronous.** Nếu dùng WebFlux, một `Mono<Boolean>` mặc định `true` qua `onErrorReturn(true)`, `onErrorResume` hay empty stream xử lý sai có thể fail-open. Async jobs cũng phải await quyết định trước khi thực hiện side effect. Dù runtime khác nhau, bất biến vẫn là “không PERMIT hợp lệ ⇒ không tác động tài nguyên”.

## 9. Checklist nghiệm thu

Trước khi chấp nhận một tích hợp external policy service, cần chứng minh bằng test và review:

1. Chỉ có **PERMIT tường minh, hợp lệ, đúng ngữ cảnh** mở chốt; DENY, unknown, empty, NOT_APPLICABLE, INDETERMINATE, timeout, lỗi mạng và lỗi parse không mở chốt.
2. Authentication, tenant/owner và metadata của resource lấy từ nguồn đáng tin; client không thể giả request context hoặc tái dùng quyết định của user khác.
3. `@PreAuthorize`/`AuthorizationManager` thực sự chạy trên mọi đường dẫn nghiệp vụ quan trọng, không bị bỏ qua do self-invocation, chain/matcher sai hoặc fallback config.
4. Khi policy service lỗi, dữ liệu nhạy cảm không xuất hiện trong body, không có thao tác đọc có bảo vệ hoặc side effect được thực thi; test cả hành vi 403/503 đã định nghĩa.
5. Retry, cache, circuit breaker và trạng thái khi khởi động **không bao giờ** âm thầm biến unavailable thành allow.
6. Có log/metric/alert phân biệt policy DENY với sự cố PDP; không ghi bí mật vào telemetry và có quy trình phục hồi.
7. Khi PDP phục hồi hoặc quyền thay đổi, kết quả theo quyền mới có hiệu lực đúng, không còn cache PERMIT stale.

**Kết luận:** độ tin cậy của dịch vụ chính sách ảnh hưởng đến khả năng phục vụ, nhưng không được quyết định mức quyền mặc định của hệ thống. Trong Spring Security, mọi PEP phải bảo đảm: **chỉ quyết định PERMIT hợp lệ mới cho phép thao tác, còn lỗi đánh giá chính sách phải ngừng truy cập một cách kiểm chứng được**.

## Tài liệu tham khảo

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): cách cấu hình `authorizeHttpRequests`, `permitAll`/`denyAll` và sử dụng `AuthorizationManager`.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): cơ chế thực thi quyết định của `AuthorizationManager`.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): vị trí `AuthorizationFilter` và `ExceptionTranslationFilter` khi yêu cầu bị từ chối.
