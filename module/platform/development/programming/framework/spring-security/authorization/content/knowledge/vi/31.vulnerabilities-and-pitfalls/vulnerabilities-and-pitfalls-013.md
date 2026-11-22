# Chính sách nhiều lớp mâu thuẫn và thiếu kiểm thử tình huống bị từ chối

## 1. Mục tiêu

Trong Spring Security, một request có thể gặp **nhiều lớp authorization**: HTTP filter chain, @PreAuthorize trên service, domain policy theo tenant/owner và truy vấn dữ liệu. Lỗ hổng xảy ra khi một lớp cho phép quá rộng, điều kiện kết hợp sai (OR thay vì AND), hoặc bộ test chỉ xác nhận **200 OK** mà không kiểm tra các tình huống **bị từ chối**.

Bài học thuộc nhóm **Sai sót và lỗ hổng** của module **Spring Security – authorization**. Sau khi thực hành, bạn sẽ:

- Phân biệt **HTTP cho phép nhưng method từ chối** và **HTTP từ chối dù method có thể cho phép**.
- Hiểu thứ tự **requestMatchers**, việc chọn **SecurityFilterChain** và giới hạn proxy của **@PreAuthorize**.
- Viết policy đúng theo **authentication AND scope AND role AND tenant AND ownership**.
- Kiểm thử riêng từng nhánh deny: anonymous, thiếu scope, thiếu role, sai owner, sai tenant, tài nguyên không tồn tại và URL chưa khai báo.
- Xác minh thân phương thức **không chạy** khi bị @PreAuthorize chặn; kiểm tra lời gọi service trực tiếp.
- Chủ động tạo mutation sai để chứng minh bộ test phát hiện việc vô tình nới quyền.

Ví dụ dùng **Java 17+, Spring Boot 3.5.7, Spring Security 6.x, Maven, JUnit Jupiter và MockMvc**, có đầy đủ mã nguồn từng file. Demo chỉ dùng GET; yêu cầu ghi dữ liệu cần test CSRF và policy riêng.

## 2. Thứ tự và trách nhiệm của mỗi lớp

~~~text
Authenticated/anonymous HTTP request
        |
        v
SecurityFilterChain khớp đầu tiên
        |
        v
authorizeHttpRequests: URL + HTTP method + SCOPE_docs.read
        | DENY -> HTTP 401/403
        v
Controller -> Spring-managed DocumentService proxy
        |
        v
@PreAuthorize: ROLE_READER AND @docPolicy.canRead(...)
        | DENY -> AccessDeniedException (service body chưa chạy)
        v
DocPolicy: member of tenant + document exists + correct owner
        | false -> từ chối ở @PreAuthorize
        v
DocumentService.read(...) -> Repository -> HTTP 200
~~~

**Không được giả định các lớp tự kết hợp theo cách mong muốn:**

1. Trong **authorizeHttpRequests**, request matcher được xét **theo thứ tự**. Rule đầu tiên khớp quyết định quyền tại tầng URL; matcher permitAll quá rộng có thể che mất rule hasAuthority hẹp phía dưới.
2. Với **nhiều SecurityFilterChain**, Spring chọn **chain đầu tiên khớp** theo securityMatcher/@Order, không áp dụng tất cả chain như một tập điều kiện AND. Chain public có độ ưu tiên cao có thể chặn chain chặt hơn khỏi việc được chọn.
3. **@PreAuthorize** là method security dựa vào Spring proxy khi bật @EnableMethodSecurity. Đối tượng tạo bằng **new**, lời gọi nội bộ **this.read(...)** hoặc đường truy cập repository trực tiếp có thể bypass method advice.
4. Với request **thực sự đi qua cả URL và method security**, cả hai phải cho phép. URL **permitAll** chỉ cho request đi tiếp, không tự tắt @PreAuthorize; method cho phép không override một HTTP deny trước đó.
5. Không mặc định policy class/interface và method annotation luôn được cộng bằng AND. Kiểm tra inheritance/override và viết rõ biểu thức khi cần đồng thời nhiều điều kiện.
6. **@PreAuthorize** chạy trước thân service, phù hợp để bảo vệ thao tác có side effect. **@PostAuthorize** chạy sau khi method trả về và không tự hoàn tác side effect.

### Role và authority

Trong thiết lập mặc định:

- **hasRole('READER')** cần authority **ROLE_READER**.
- **hasAuthority('SCOPE_docs.read')** cần authority chính xác **SCOPE_docs.read**.

Scope OAuth và role là hai dữ kiện độc lập. Một test có role nhưng thiếu scope phải bị HTTP từ chối; test có scope nhưng thiếu role phải đi tới service rồi bị method security từ chối.

### Phân biệt 401/403

| Trường hợp | Kết quả demo | Vì sao |
| --- | --- | --- |
| Anonymous gọi API bảo vệ | HTTP **401** | HTTP Basic entry point yêu cầu xác thực |
| Đã xác thực, thiếu scope HTTP | HTTP **403** | URL authorization từ chối |
| Qua HTTP, thiếu role/owner/tenant | HTTP **403** | Method/domain authorization từ chối |
| Gọi Java service trực tiếp sai quyền | **AccessDeniedException** | Lời gọi Java không có HTTP status |

Kết quả HTTP tùy cấu hình AuthenticationEntryPoint/AccessDeniedHandler và phương thức xác thực. Ví dụ này cố ý dùng Basic để minh họa 401. @WithMockUser không tự kiểm JWT signature, scope mapping hay IdP production.

## 3. Chính sách và ma trận kiểm thử

Endpoint: **GET /api/{tenant}/documents/{id}**. Chính sách được cho phép khi **tất cả** đúng:

~~~text
ALLOW =
    authenticated
    AND authority("SCOPE_docs.read")
    AND role("ROLE_READER")
    AND tenantMember(username, tenantId)
    AND exists(tenantId, documentId)
    AND owner(tenantId, documentId) == username
~~~

Mọi route khác được **anyRequest().denyAll()**. Ví dụ chọn từ chối **403** cả khi document không tồn tại, vì domain policy không chứng minh được quyền; sản phẩm thật có thể chọn 404 nhưng phải ghi hợp đồng và test nhất quán.

Dữ liệu:

| Tenant | Document ID | Owner | Body |
| --- | --- | --- | --- |
| acme | report | alice | ACME report for alice |
| acme | bob-secret | bob | ACME secret for bob |
| beta | report | alice | BETA report for alice |

Thành viên: **alice ∈ acme**, **bob ∈ acme, beta**. Tài liệu **beta/report** thuộc alice nhưng alice không phải member beta: fixture này phát hiện lỗi chỉ check owner mà quên tenant.

| Kịch bản | Điều kiện cố ý sai | Kỳ vọng |
| --- | --- | --- |
| Anonymous | Chưa đăng nhập | 401, service chưa chạy |
| Role đủ, scope thiếu | HTTP scope | 403, service chưa chạy |
| Scope đủ, role thiếu | Method role | 403, service chưa chạy |
| Alice đọc acme/report | Không có điều kiện sai | 200, body đúng |
| Alice đọc acme/bob-secret | Owner | 403, service chưa chạy |
| Alice đọc beta/report | Tenant membership | 403, service chưa chạy |
| Alice đọc acme/missing | Resource existence | 403 theo policy |
| Alice gọi /outside | Fallback URL | 403 |
| Alice gọi service.read(acme,bob-secret) | Owner, bypass HTTP | AccessDeniedException |

Một negative test tốt làm **một điều kiện sai, các điều kiện còn lại đúng**. Nếu test thiếu role đồng thời thiếu scope, HTTP chặn trước khiến test xanh mà không chứng minh @PreAuthorize hoạt động.

## 4. Ứng dụng Maven runnable

Cây thư mục:

~~~text
layered-authz/
├── pom.xml
├── src/main/java/com/example/layered/
│   ├── LayeredApplication.java
│   ├── SecurityConfig.java
│   ├── Document.java
│   ├── ResourceKey.java
│   ├── DocumentRepository.java
│   ├── DocPolicy.java
│   ├── DocumentService.java
│   └── DocumentController.java
└── src/test/java/com/example/layered/
    └── LayeredAuthorizationTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>layered-authz</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**LayeredApplication.java**: bật method security.

~~~java
package com.example.layered;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class LayeredApplication {
    public static void main(String[] args) {
        SpringApplication.run(LayeredApplication.class, args);
    }
}
~~~

**SecurityConfig.java**: scope bắt buộc với GET /api/**; các URL còn lại mặc định bị deny. Giữ CSRF mặc định vì chỉ thử GET.

~~~java
package com.example.layered;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/**")
                    .hasAuthority("SCOPE_docs.read")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Document.java**:

~~~java
package com.example.layered;

public record Document(String tenantId, String id, String owner, String body) {
}
~~~

**ResourceKey.java**:

~~~java
package com.example.layered;

record ResourceKey(String tenantId, String documentId) {
}
~~~

**DocumentRepository.java**: có tenantId trong key, nên hai tenant có thể có cùng document ID.

~~~java
package com.example.layered;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {
    private final Map<ResourceKey, Document> documents = Map.of(
        new ResourceKey("acme", "report"),
            new Document("acme", "report", "alice", "ACME report for alice"),
        new ResourceKey("acme", "bob-secret"),
            new Document("acme", "bob-secret", "bob", "ACME secret for bob"),
        new ResourceKey("beta", "report"),
            new Document("beta", "report", "alice", "BETA report for alice")
    );

    public Optional<Document> find(String tenantId, String id) {
        return Optional.ofNullable(documents.get(new ResourceKey(tenantId, id)));
    }
}
~~~

**DocPolicy.java**: membership, existence và ownership. Hàm public để biểu thức SpEL trên bean gọi được.

~~~java
package com.example.layered;

import java.util.Map;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("docPolicy")
public class DocPolicy {
    private final DocumentRepository repository;
    private final Map<String, Set<String>> members = Map.of(
        "alice", Set.of("acme"),
        "bob", Set.of("acme", "beta")
    );

    public DocPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication,
                           String tenantId, String documentId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        String username = authentication.getName();
        if (!members.getOrDefault(username, Set.of()).contains(tenantId)) {
            return false;
        }
        return repository.find(tenantId, documentId)
            .map(doc -> doc.owner().equals(username))
            .orElse(false);
    }
}
~~~

Tenant do client gửi phải được đối chiếu với membership/entitlement từ nguồn tin cậy, không tự tin tenantId trên URL. Tại production, repository/database cũng cần điều kiện tenant (WHERE tenant_id = ... hoặc row-level security).

**DocumentService.java**: một biểu thức @PreAuthorize bắt buộc role **AND** domain policy; #p0/#p1 lần lượt là tenantId và documentId.

~~~java
package com.example.layered;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;
    private final AtomicInteger calls = new AtomicInteger();

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasRole('READER') and @docPolicy.canRead(authentication, #p0, #p1)")
    public Document read(String tenantId, String documentId) {
        calls.incrementAndGet();
        return repository.find(tenantId, documentId)
            .orElseThrow(() -> new IllegalStateException(
                "Resource disappeared after authorization"
            ));
    }

    public int invocationCount() {
        return calls.get();
    }

    public void resetInvocationCount() {
        calls.set(0);
    }
}
~~~

**DocumentController.java**: inject Spring bean để gọi qua method-security proxy.

~~~java
package com.example.layered;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/{tenant}/documents/{id}")
    public Document read(@PathVariable String tenant,
                         @PathVariable String id) {
        return service.read(tenant, id);
    }
}
~~~

## 5. Bộ kiểm thử có 10 trường hợp cụ thể

**LayeredAuthorizationTest.java**: dùng @SpringBootTest để có controller, HTTP security, service proxy và policy thật. @AutoConfigureMockMvc giữ filters bật. @WithMockUser đặt user/authority cho từng test. Bộ đếm reset trong @BeforeEach.

~~~java
package com.example.layered;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LayeredAuthorizationTest {
    @Autowired private MockMvc mvc;
    @Autowired private DocumentService service;

    @BeforeEach
    void reset() {
        service.resetInvocationCount();
    }

    @Test
    void publicHealthIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk());
        assertEquals(0, service.invocationCount());
    }

    @Test
    void anonymousUserIsChallengedAtHttpLayer() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isUnauthorized());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_READER"})
    void readerWithoutScopeCannotPassHttpLayer() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"SCOPE_docs.read"})
    void scopeWithoutRoleCannotPassMethodLayer() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void allLayersAllowCorrectOwnerAndTenant() throws Exception {
        mvc.perform(get("/api/acme/documents/report"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("acme"))
            .andExpect(jsonPath("$.id").value("report"))
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.body").value("ACME report for alice"));
        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void bothAuthoritiesStillCannotReadOtherOwner() throws Exception {
        mvc.perform(get("/api/acme/documents/bob-secret"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void bothAuthoritiesStillCannotReadOtherTenant() throws Exception {
        // beta/report có owner alice nhưng alice không thuộc beta.
        mvc.perform(get("/api/beta/documents/report"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void unknownResourceDeniedByPolicy() throws Exception {
        mvc.perform(get("/api/acme/documents/missing"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice",
        authorities = {"SCOPE_docs.read", "ROLE_READER"})
    void unmatchedUrlDeniedByDefault() throws Exception {
        mvc.perform(get("/outside"))
            .andExpect(status().isForbidden());
        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_READER"})
    void directCallStillEnforcesMethodRule() {
        assertThrows(AccessDeniedException.class,
            () -> service.read("acme", "bob-secret"));
        assertEquals(0, service.invocationCount());
    }
}
~~~

**Bằng chứng mà mỗi nhóm test mang lại:**

- **publicHealthIsAccessibleWithoutLogin** xác nhận /health public có chủ đích.
- **anonymousUserIsChallengedAtHttpLayer** kiểm tra unauthenticated bị challenge 401.
- **readerWithoutScopeCannotPassHttpLayer** chứng minh HTTP scope hoạt động vì role/domain đều đúng.
- **scopeWithoutRoleCannotPassMethodLayer** chứng minh @PreAuthorize hoạt động vì scope và dữ liệu đều đúng.
- **allLayersAllowCorrectOwnerAndTenant** kiểm tra HTTP 200 **và đúng body, tenant, owner**, tránh 200 với dữ liệu sai.
- **bothAuthoritiesStillCannotReadOtherOwner** phát hiện IDOR/BOLA dù role/scope hợp lệ.
- **bothAuthoritiesStillCannotReadOtherTenant** phát hiện thiếu membership dù owner trùng.
- **unknownResourceDeniedByPolicy** và **unmatchedUrlDeniedByDefault** kiểm tra fail-closed của domain và URL.
- **directCallStillEnforcesMethodRule** xác nhận lời gọi Java qua Spring proxy vẫn bị chặn khi không có HTTP filter.

Mỗi nhánh deny còn có **invocationCount() == 0**, xác nhận thân method không chạy trước khi từ chối. Chỉ assert HTTP 403 không đủ: nó có thể che giấu một lỗi trong đó dữ liệu đã được đọc hoặc side effect đã xảy ra.

### Chạy và kiểm tra

~~~bash
java -version
mvn -version
mvn test
~~~

Với cấu hình và mã hoạt động đúng, kỳ vọng **10 tests run, 0 failures, 0 errors**. Log thời gian/khởi tạo Spring có thể khác. Ví dụ không cần database hoặc server HTTP thật. Các test @WithMockUser không thay thế kiểm thử token thật trong OAuth2/OIDC.

## 6. Mutation tests: cố ý làm sai, test phải đỏ

Sau khi bộ test chuẩn xanh, thử **một mutation mỗi lần**, chạy **mvn test** rồi khôi phục.

**Mutation A: permitAll rộng che rule scope.**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/health").permitAll()
    .requestMatchers("/api/**").permitAll() // SAI: matcher rộng đứng trước
    .requestMatchers(HttpMethod.GET, "/api/**")
        .hasAuthority("SCOPE_docs.read")
    .anyRequest().denyAll()
)
~~~

Test **readerWithoutScopeCannotPassHttpLayer** phải fail: alice vẫn đủ role và domain nên kết quả sẽ đổi từ 403 thành 200, dù thiếu scope. Đây là lỗi **thứ tự matcher**.

**Mutation B: bỏ @PreAuthorize ở DocumentService.read.** Các test thiếu role, sai owner, sai tenant và direct call phải fail. Test ID missing có thể ném IllegalStateException do thân service chạy; điều đó vẫn là lỗi policy, không phải deny hợp lệ.

**Mutation C: đổi phép AND thành OR.**

~~~java
@PreAuthorize("hasRole('READER') or @docPolicy.canRead(authentication, #p0, #p1)")
~~~

Người có ROLE_READER sẽ qua service dù sai owner/tenant. **bothAuthoritiesStillCannotReadOtherOwner** và **bothAuthoritiesStillCannotReadOtherTenant** phải fail.

**Mutation D: bỏ membership tenant ở DocPolicy.** **bothAuthoritiesStillCannotReadOtherTenant** phải fail, vì beta/report có owner alice dù alice không thuộc beta.

**Mutation E: đổi anyRequest().denyAll() thành anyRequest().permitAll().** **unmatchedUrlDeniedByDefault** phải fail. Đừng để route mới vô tình public.

Nếu mutation nguy hiểm vẫn để test xanh, xem lại test đã cô lập đúng lớp chưa, service có bị mock không, hoặc có rule khác deny trước khi đi tới rule cần kiểm.

## 7. Các lỗi và lỗ hổng thường gặp

| Sai sót | Hậu quả | Cách kiểm và sửa |
| --- | --- | --- |
| permitAll rộng đứng trước matcher chặt | Bỏ qua scope HTTP | Match hẹp trước; test role đủ nhưng thiếu scope |
| Nhiều SecurityFilterChain order sai | Chain public chiếm route private | Ràng securityMatcher rõ và test @Order từng chain |
| Quên @EnableMethodSecurity | @PreAuthorize bị vô hiệu | Test thiếu role/sai owner phải đỏ khi bỏ annotation |
| @WithMockUser thiếu cả role lẫn scope | Test nhận 403 nhưng sai nguyên nhân | Cho đủ mọi điều kiện trừ điều kiện muốn test |
| Dùng new hoặc this.securedMethod(...) | Bypass proxy advice | Gọi Spring bean qua proxy, test self-invocation nếu có |
| Mock chính protected service | Annotation thật không chạy | Giữ service thật, mock dependency nếu cần |
| @AutoConfigureMockMvc(addFilters = false) | Test không đi qua HTTP security | Giữ filters bật trong test policy URL |
| Chỉ test trường hợp 200 | Xóa rule mà test vẫn xanh | Test từng deny, dùng mutation |
| Dùng OR sai chỗ | Chỉ cần một quyền là được vào | Viết truth table và biểu thức AND rõ ràng |
| Chỉ check owner, bỏ tenant | Lộ tài liệu xuyên tenant | Tạo fixture owner đúng nhưng tenant sai |
| Chỉ assert exception/status | Service có thể đã chạy | Kiểm counter, DB state, audit hoặc side effects |
| Dùng @PostAuthorize cho action ghi | Có thể thay đổi dữ liệu trước khi deny | Kiểm trước ở boundary đáng tin cậy |

### Tình huống cần mở rộng trong sản phẩm thật

Cần bổ sung negative tests cho **JWT claim mapping**, role hierarchy, admin override, nhiều chain, URL alias/encoded path, IDOR/BOLA, quyền bị revoke sau khi cache nóng, truy vấn có tenant predicate, phương thức ghi dữ liệu và lỗi từ @ControllerAdvice. Với cache quyền, kiểm thử invalidation/phiên bản quyền theo hợp đồng; @WithMockUser không chứng minh JWT cũ đã bị vô hiệu. Với thao tác có side effect, kiểm DB/outbox/audit không đổi khi bị deny.

## 8. Checklist nghiệm thu

- [ ] Policy đầy đủ authentication, scope, role, tenant membership, existence và ownership.
- [ ] Request matcher hẹp trước rộng; fallback denyAll; nhiều chain có securityMatcher/@Order rõ.
- [ ] Test 401 anonymous, 403 thiếu scope, 403 thiếu role với các điều kiện khác đúng.
- [ ] Test 200 xác minh đúng dữ liệu tenant/owner/body.
- [ ] Test deny sai owner, sai tenant, ID missing và URL ngoài whitelist.
- [ ] Test gọi service trực tiếp qua Spring bean bắt AccessDeniedException.
- [ ] Test deny kiểm service body chưa chạy khi policy phải chặn trước.
- [ ] Mutation permitAll rộng, bỏ annotation, đổi AND/OR, bỏ membership đều làm test đỏ.
- [ ] Có test production tương ứng cho JWT, DB, cache, async và các thao tác ghi.

## 9. Tham khảo

- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Java Configuration / Multiple SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — MockMvc Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html

**Ghi nhớ:** đừng chỉ chứng minh rằng một user đúng quyền đọc được tài liệu. Phải chứng minh **mỗi điều kiện sai đều bị từ chối ở đúng lớp**, rule đúng thứ tự và service không chạy ngoài quyền; đó là cách phát hiện chính sách nhiều lớp mâu thuẫn trước khi thành lỗ hổng.