# Kiểm thử evaluator độc lập và kiểm thử tích hợp qua proxy

> **Chủ đề:** Spring Security – authorization · **Nhóm:** PermissionEvaluator. Bài học chỉ rõ hai cấp kiểm thử có mục đích khác nhau: **unit test** gọi trực tiếp `PermissionEvaluator.hasPermission(...)` để chứng minh luật quyền, và **integration test** gọi Spring-managed service **qua method-security proxy** để chứng minh biểu thức `hasPermission(...)` thực sự được thực thi. Ví dụ áp dụng cho Spring Boot 3.x, Spring Security 6.x, JUnit Jupiter, MockMvc và Java 17+; nếu nâng lên Spring Boot 4/Spring Security 7, kiểm tra lại dependency/test auto-configuration theo phiên bản.

## 1. Vì sao cần hai loại kiểm thử?

Giả sử dịch vụ cung cấp:

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Có ít nhất **hai khẳng định hoàn toàn khác nhau**:

1. Khi được truyền đúng `Authentication`, ID, loại tài nguyên và permission, **evaluator đưa ra kết quả đúng**: Alice được xem Document 1 của Alice, Bob không được xem Document 1; ID không tồn tại, sai type, sai permission đều bị deny.
2. Khi code ứng dụng gọi `service.read(1L)`, Spring **thật sự chặn lời gọi bằng `@PreAuthorize`**, lấy tham số `#p0`, gọi evaluator đã đăng ký và ném `AccessDeniedException` trước khi vào thân method nếu người gọi không đủ quyền.

Unit test thuần Java có thể chứng minh (1) nhưng **không chứng minh được (2)**. Integration test ở proxy/service mới chứng minh (2), trong khi HTTP test qua `MockMvc` bổ sung câu hỏi thứ ba: filter chain, authentication và exception translation có tạo phản hồi 401/403/200 theo contract của API không?

### Bảng phạm vi kiểm thử

| Lớp kiểm thử | Đối tượng cần gọi | Khẳng định quan trọng | Không chứng minh điều gì? |
| --- | --- | --- | --- |
| Unit evaluator | `new DocumentPermissionEvaluator(fakeStore)` | Boolean true/false đúng cho principal, object, ID/type, permission | Chưa chứng minh Spring đã đăng ký evaluator hoặc bật method security |
| Method-security integration | `@Autowired DocumentService` (Spring proxy) | `@PreAuthorize` chạy, đúng overload được gọi, thân method không chạy khi deny | Chưa kiểm tra URL matcher, CSRF hay HTTP status |
| MVC/security integration | `MockMvc` với filters, user xác thực | HTTP route, authentication, proxy service, status/JSON | Chưa chứng minh chạy qua mạng thật hay reverse proxy |
| End-to-end ngoài process | Client thật → server thật → DB/thành phần ngoài | Authentication thực, deployment config, DB/transaction | Thường chậm và không thay unit tests đầy đủ |

Đừng chọn chỉ một lớp test rồi coi đủ. Khi logic permission phức tạp, đa số case thuộc **unit evaluator** vì nhanh, độc lập; một số case đại diện phải đi qua **proxy** để phát hiện cấu hình sai; thêm vài test HTTP để xác nhận trải nghiệm client.

## 2. Hiểu chính xác các API được kiểm thử

`PermissionEvaluator` nằm trong `org.springframework.security.access.PermissionEvaluator`, có **hai overload**:

~~~java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);

boolean hasPermission(
    Authentication authentication,
    Serializable targetId,
    String targetType,
    Object permission
);
~~~

Hai dạng SpEL tương ứng:

~~~java
// Object đã có sẵn ở tham số đầu tiên.
@PreAuthorize("hasPermission(#p0, 'read')")

// Chỉ biết ID của object, cần nêu type và permission.
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
~~~

Khi gọi trực tiếp từ unit test, bạn **tự cung cấp** `Authentication`. Khi method-security proxy đánh giá SpEL, Spring Security **tự lấy** `Authentication` từ security context. `#p0` trong annotation là tham số method đầu tiên, không phải tham số evaluator đầu tiên. `targetType` là tên type do app hoặc ACL layer quy ước; không có phép tự động tìm entity của Spring chỉ nhờ literal `'Document'`.

`PermissionEvaluator` trả boolean, không trả HTTP status. **false** là quyết định từ chối; khi biểu thức `@PreAuthorize` false, method-security interceptor thông thường ném `AccessDeniedException` (hoặc subtype) trên đường gọi được bảo vệ. Nếu đi qua HTTP filter chain, Spring có thể dịch thành 403; đối với khách chưa xác thực, entry point thường trả 401 với HTTP Basic. Không khẳng định mọi lỗi đều là 403 mà bỏ qua configuration.

### 2.1. Default evaluator có thể không phải evaluator của bạn

Chỉ khai báo `@Component class MyPermissionEvaluator implements PermissionEvaluator` **chưa đủ** để đảm bảo biểu thức method security sử dụng implementation ấy trong mọi cấu hình. Một `MethodSecurityExpressionHandler` được cấu hình đúng phải sử dụng evaluator. Nếu handler vẫn dùng deny-all default, các test unit vẫn xanh nhưng mọi request hợp lệ đều bị deny.

Khi dùng `@EnableMethodSecurity`, có thể expose handler theo mẫu:

~~~java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        PermissionEvaluator evaluator) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(evaluator);
    return handler;
}
~~~

`static @Bean` giúp publish handler sớm trước khi Spring khởi tạo cấu hình method security. Test integration phải kiểm tra thực tế thay vì chỉ nhìn thấy một bean `PermissionEvaluator` trong context.

### 2.2. @WithMockUser không tự đánh dấu một method là đã được bảo vệ

`@WithMockUser` đặt một `Authentication` giả đã xác thực vào `SecurityContextHolder` của test thread. Nó **không tự tạo proxy**, không bật `@EnableMethodSecurity`, không gọi evaluator và không thay thế request authentication cho mọi kiểu end-to-end test. Khi test HTTP thật chạy ở thread/server riêng, phải xác thực request thông qua Basic/Bearer/cookie tương ứng.

`@WithMockUser(username="alice", authorities={"document:read","tenant:alpha"})` tạo authority chính xác theo chuỗi. Ngược lại, `roles={"ADMIN"}` mặc định tạo `ROLE_ADMIN`; không dùng `roles={"document:read"}` rồi đòi matcher `hasAuthority('document:read')` tự khớp.

## 3. Thiết kế policy để unit test không cần Spring

Ví dụ ứng dụng quản lý tài liệu gồm:

~~~text
ID 1: Document tenant=alpha, owner=alice
ID 2: Document tenant=beta,  owner=bob
ID 3: Document tenant=alpha, owner=bob
~~~

Quy tắc `read`: principal phải có authority `document:read`, có authority tenant tương ứng và là owner của tài liệu được tải từ store tin cậy. `targetType` phải chính xác `Document`, `permission` phải chính xác `read`, ID phải là `Long` dương. Đối tượng client tự tạo với owner giả không được coi là nguồn tin quyền.

**Tách class policy khỏi Spring AOP:** evaluator nhận dependency `DocumentStore` qua constructor, có thể được tạo bằng `new` trong unit test. Unit không cần `ApplicationContext`, `SecurityContextHolder`, web server, database thật hoặc `@WithMockUser`.

Một input invalid không phải “abstain” hay “allow”. Với `PermissionEvaluator`, trả `false` cho type/ID/permission không hỗ trợ theo contract. Nếu store/ACL backend lỗi hạ tầng, xử lý an toàn với exception/logging phù hợp; không bắt mọi exception rồi trả `true`.

## 4. Ứng dụng Spring Boot mẫu để cả hai tầng test cùng dùng

Đây là **file Spring Boot hoàn chỉnh trong một dự án đã có dependencies**, không thể chạy bằng JDK `javac` thuần không có Spring JAR. Tạo:

~~~text
src/main/java/example/permissiontest/PermissionTestApplication.java
src/test/java/example/permissiontest/DocumentPermissionEvaluatorUnitTest.java
src/test/java/example/permissiontest/PermissionProxyIntegrationTest.java
~~~

### 4.1. Mã ứng dụng

Lưu file `src/main/java/example/permissiontest/PermissionTestApplication.java`:

~~~java
package example.permissiontest;

import java.io.Serializable;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionTestApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        // URL chỉ yêu cầu xác thực. ACL do method security quyết định.
                        .requestMatchers(HttpMethod.GET, "/api/documents/*")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "tenant:alpha").build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read", "tenant:beta").build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("document:view").build());
    }
}

record Document(long id, String tenant, String owner, String title) {
}

@Component
class DocumentStore {
    private final Map<Long, Document> data = Map.of(
            1L, new Document(1L, "alpha", "alice", "Budget A"),
            2L, new Document(2L, "beta",  "bob",   "Budget B"),
            3L, new Document(3L, "alpha", "bob",   "Budget C"));

    Optional<Document> find(Long id) {
        return Optional.ofNullable(data.get(id));
    }
}

@Component
class DocumentPermissionEvaluator implements PermissionEvaluator {
    private final DocumentStore store;

    DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(Authentication actor,
                                 Object targetDomainObject,
                                 Object permission) {
        if (!(targetDomainObject instanceof Document supplied)) {
            return false;
        }
        // Chỉ dùng ID từ candidate; KHÔNG tin owner/tenant client khai.
        return store.find(supplied.id())
                .map(saved -> canRead(actor, saved, permission))
                .orElse(false);
    }

    @Override
    public boolean hasPermission(Authentication actor,
                                 Serializable targetId,
                                 String targetType,
                                 Object permission) {
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id) || id <= 0) {
            return false;
        }
        return store.find(id)
                .map(saved -> canRead(actor, saved, permission))
                .orElse(false);
    }

    private boolean canRead(Authentication actor, Document doc,
                            Object permission) {
        if (actor == null || !actor.isAuthenticated()
                || !"read".equals(permission)) {
            return false;
        }

        boolean hasFeature = actor.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));
        boolean hasTenant = actor.getAuthorities().stream()
                .anyMatch(a -> ("tenant:" + doc.tenant())
                        .equals(a.getAuthority()));
        boolean owns = doc.owner().equals(actor.getName());

        return hasFeature && hasTenant && owns;
    }
}

@Service
class DocumentService {
    private final DocumentStore store;
    private final AtomicInteger bodyExecutions = new AtomicInteger();

    DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public Document readById(Long id) {
        bodyExecutions.incrementAndGet();
        return store.find(id).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    @PreAuthorize("hasPermission(#p0, 'read')")
    public Document readLoaded(Document candidate) {
        bodyExecutions.incrementAndGet();
        return store.find(candidate.id()).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    public int bodyExecutions() {
        return bodyExecutions.get();
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Map<String, Object> read(@PathVariable Long id) {
        Document doc = service.readById(id);
        // Trả map để JSON không phụ thuộc visibility của record nội bộ.
        return Map.of("id", doc.id(), "owner", doc.owner(),
                      "title", doc.title());
    }
}
~~~

**Giới hạn của demo:** dữ liệu và authority tenant được hard-code trong bộ nhớ; mật khẩu `{noop}` chỉ để học. Production phải dùng encoder an toàn, identity/tenant được xác minh và truy vấn được scope theo tenant/ACL. `bodyExecutions` chỉ là instrumentation giúp test kiểm chứng method body chưa chạy; không phải chức năng nghiệp vụ.

### 4.2. Dependency Gradle

Trong dự án Spring Boot 3.x (ví dụ tạo từ Spring Initializr) đã bật plugin, dependency management, cấu hình Java 17+, khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây chỉ là **đoạn dependencies** của `build.gradle`, không phải build file độc lập. Test chạy qua `./gradlew test` trên macOS/Linux hoặc `gradlew.bat test` trên Windows. Code mẫu không dùng database/Redis/JWT để giữ đơn vị kiểm thử rõ ràng.

## 5. Unit test evaluator: kiểm thử một class, không cần Spring context

Lưu `src/test/java/example/permissiontest/DocumentPermissionEvaluatorUnitTest.java`:

~~~java
package example.permissiontest;

import java.io.Serializable;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPermissionEvaluatorUnitTest {
    private final DocumentPermissionEvaluator evaluator =
            new DocumentPermissionEvaluator(new DocumentStore());

    static Authentication actor(String username, String... authorities) {
        return new UsernamePasswordAuthenticationToken(
                username, "ignored",
                AuthorityUtils.createAuthorityList(authorities));
    }

    @Test
    void grantsOnlyOwnerInMatchingTenant() {
        Authentication alice = actor(
                "alice", "document:read", "tenant:alpha");
        Authentication bob = actor(
                "bob", "document:read", "tenant:beta");

        assertTrue(evaluator.hasPermission(
                alice, 1L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, 2L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, 3L, "Document", "read"));
        assertTrue(evaluator.hasPermission(
                bob, 2L, "Document", "read"));
    }

    @Test
    void rejectsMissingAuthorityOrTenant() {
        Authentication noFeature = actor("alice", "tenant:alpha");
        Authentication wrongTenant = actor(
                "alice", "document:read", "tenant:beta");

        assertFalse(evaluator.hasPermission(
                noFeature, 1L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                wrongTenant, 1L, "Document", "read"));
    }

    @Test
    void rejectsUnknownTypePermissionOrId() {
        Authentication alice = actor(
                "alice", "document:read", "tenant:alpha");

        assertFalse(evaluator.hasPermission(
                alice, 1L, "Invoice", "read"));
        assertFalse(evaluator.hasPermission(
                alice, 1L, "Document", "write"));
        assertFalse(evaluator.hasPermission(
                alice, 999L, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, Integer.valueOf(1), "Document", "read"));
        assertFalse(evaluator.hasPermission(
                alice, (Serializable) null, "Document", "read"));
        assertFalse(evaluator.hasPermission(
                null, 1L, "Document", "read"));
    }

    @Test
    void objectOverloadDoesNotTrustForgedOwner() {
        Authentication alice = actor(
                "alice", "document:read", "tenant:alpha");
        Document honest = new Document(
                1L, "alpha", "alice", "Client copy");
        Document forged = new Document(
                2L, "alpha", "alice", "Forged owner");

        assertTrue(evaluator.hasPermission(alice, honest, "read"));
        assertFalse(evaluator.hasPermission(alice, forged, "read"));
        assertFalse(evaluator.hasPermission(alice, honest, "delete"));
        assertFalse(evaluator.hasPermission(alice, (Object) null, "read"));
    }
}
~~~

### 5.1. Tại sao đây là unit test thật?

- Test tự tạo `DocumentStore` và `DocumentPermissionEvaluator`, không dùng `@SpringBootTest`, `@Autowired` hay `SecurityContextHolder`.
- `Authentication` được tạo trực tiếp bằng `UsernamePasswordAuthenticationToken` ba tham số và danh sách authority cụ thể; không cần user thật trong `UserDetailsService`.
- Test gọi **cả hai overload** của `PermissionEvaluator` với input rõ ràng.
- Test deny cho sai kiểu ID `Integer` dù giá trị số bằng `Long(1)`, vì evaluator mẫu có contract kiểu Long.
- Test object giả cho ID 2 chứng minh evaluator không tin thuộc tính owner/tenant từ đối tượng client đưa lên.

**Quan trọng:** test unit xanh chỉ cho thấy implementation trả boolean đúng với fixture này. Nó **không xác nhận `@PreAuthorize` có được Spring kích hoạt, handler có dùng evaluator này, hoặc lời gọi qua proxy thật**. Đây là điểm trọng tâm của sự phân biệt trong tiêu đề bài.

### 5.2. Dùng mock repository khi dữ liệu phức tạp

Nếu evaluator nhận một repository có DB, có thể dùng Mockito thay vì in-memory fixture. Ví dụ (trích đoạn, không phải class đầy đủ):

~~~java
DocumentStore store = mock(DocumentStore.class);
when(store.find(1L)).thenReturn(Optional.of(
        new Document(1L, "alpha", "alice", "A")));
DocumentPermissionEvaluator evaluator =
        new DocumentPermissionEvaluator(store);
~~~

Các import tương ứng: `static org.mockito.Mockito.mock`, `static org.mockito.Mockito.when` và `java.util.Optional`. Nên phân biệt:
- **Stub repository** để kiểm soát dữ liệu owner/tenant/ACL và test nhánh deny/grant.
- **Không mock chính PermissionEvaluator** khi mục tiêu là test thuật toán thực.
- Chỉ dùng `verify(...)` để kiểm tra số lần lookup hoặc argument khi có giá trị; đừng thay assert quyết định bảo mật bằng “đã gọi method”.

Một unit test tách biệt không nên bị ảnh hưởng bởi authentication còn sót từ test khác. Ở đây evaluator nhận `Authentication` trực tiếp, nên không phụ thuộc thread-local context.

## 6. Integration test qua proxy: chứng minh @PreAuthorize thực thi

Lưu file `src/test/java/example/permissiontest/PermissionProxyIntegrationTest.java`:

~~~java
package example.permissiontest;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionProxyIntegrationTest {
    @Autowired
    DocumentService service;

    @Autowired
    MockMvc mvc;

    @Test
    void serviceBeanIsActuallyProxied() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyGrantsValidDocument() {
        Document doc = service.readById(1L);
        assertEquals("alice", doc.owner());
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyDeniesOtherTenantBeforeBodyRuns() {
        int before = service.bodyExecutions();

        assertThrows(AccessDeniedException.class,
                () -> service.readById(2L));

        assertEquals(before, service.bodyExecutions());
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyDeniesOtherOwnerEvenWithinTenant() {
        assertThrows(AccessDeniedException.class,
                () -> service.readById(3L));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void proxyEvaluatesObjectOverloadUsingTrustedStore() {
        Document forged = new Document(
                2L, "alpha", "alice", "Forged");

        assertThrows(AccessDeniedException.class,
                () -> service.readLoaded(forged));
    }

    @Test
    @WithMockUser(username = "viewer",
                  authorities = {"document:view"})
    void proxyDeniesMissingFeatureAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> service.readById(1L));
    }

    @Test
    @WithAnonymousUser
    void proxyDoesNotGrantAnonymousUser() {
        assertThrows(AccessDeniedException.class,
                () -> service.readById(1L));
    }

    @Test
    void httpBasicAliceCanReadThroughFilterAndProxy() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void httpBasicBobCannotReadAliceDocument() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedHttpRequestRequiresLogin() throws Exception {
        mvc.perform(get("/api/documents/1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownIdIsDeniedByEvaluatorInThisDemo() throws Exception {
        mvc.perform(get("/api/documents/999")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isForbidden());
    }
}
~~~

### 6.1. Đọc đúng ý nghĩa mỗi test

`AopUtils.isAopProxy(service)` là một **sanity check**, chưa đủ một mình để chứng minh security advisor đúng. Test quyết định **GRANT** và **DENY** mới cung cấp bằng chứng: khi Alice gọi qua bean Spring, ID 1 được đọc; khi gọi ID 2, `AccessDeniedException` phát sinh và `bodyExecutions` không tăng. Điều đó chứng minh policy đã chặn **trước thân method** trong đường gọi thực tế của ví dụ.

`@WithMockUser` tạo security context cho lời gọi trực tiếp vào service trên test thread; `@SpringBootTest` lấy bean Spring-managed nên có proxy/interceptor. Với HTTP test, `MockMvc` chạy filter chain và `httpBasic("alice","demo")` tạo request credentials; không nhầm một unit test service đã có mock user với test đăng nhập qua HTTP thật.

**Quan trọng:** Spring Security có thể ném một subtype của `AccessDeniedException`. Test dùng superclass này để tránh phụ thuộc quá sâu vào tên exception cụ thể giữa các phiên bản.

### 6.2. Một lưu ý cú pháp Java trong import static

Java không cho tách một `import` thành hai dòng quanh dấu chấm theo kiểu tùy tiện khi copy từ renderer nếu công cụ định dạng làm lạ. Hai import tĩnh sau tương đương và có thể viết trọn trên một dòng cho dễ copy:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Trong file mẫu, các import ở trên được xuống dòng theo khoảng trắng trước dấu chấm để trình bày; cú pháp Java chấp nhận whitespace giữa tokens nhưng dạng một dòng thường thuận tiện nhất khi copy vào IDE. Import `org.springframework.http.HttpStatus` trong test mẫu không cần sử dụng, có thể để IDE xóa mà không ảnh hưởng kết quả.

### 6.3. Chính sách dùng mock user khác với đăng nhập thật

`@WithMockUser(username="alice", authorities={"document:read", "tenant:alpha"})` **không thử mật khẩu**, không xác nhận Alice có thật trong database và không kiểm tra filter chain. Ngược lại, `httpBasic("alice","demo")` qua `MockMvc` có thể kiểm tra `UserDetailsService` demo và phần xác thực Basic của `SecurityFilterChain`.

Một ứng dụng JWT có thể dùng `jwt()` request post-processor để kiểm thử authorization dựa trên claims hoặc tạo request thật với test token hợp lệ. Nếu principal là custom type và code thực hiện cast, `@WithMockUser` dùng principal kiểu `User` thông thường có thể không đại diện production; dùng `@WithUserDetails` hoặc `@WithSecurityContext` tạo đúng principal. Test phải phản ánh authentication shape thật.

## 7. Test giả thành công khi bỏ qua proxy: các phản ví dụ

### 7.1. Tự tạo service bằng new

~~~java
// Phản ví dụ: service không phải bean Spring đã được proxy.
DocumentService direct = new DocumentService(new DocumentStore());
Document doc = direct.readById(2L); // Không tự chạy @PreAuthorize.
~~~

Thân method dùng store trực tiếp và trả Document 2 mà không kiểm tra người gọi. Trong test kiểu này, ngay cả khi `@WithMockUser` hoặc `SecurityContextHolder` có người dùng Bob/Alice, annotation **không có tác dụng** vì thiếu AOP interception. Có thể dùng cách này nếu mục tiêu là test **business method không xét security**, nhưng không được coi là integration test phân quyền.

### 7.2. Self-invocation trong một bean

~~~java
@Service
class ExampleService {
    public Document internalCall(Long id) {
        return protectedRead(id); // this.protectedRead() bypass proxy.
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public Document protectedRead(Long id) {
        return loadDocument(id);
    }
}
~~~

Đây là **trích đoạn minh họa**, chưa có `loadDocument` và imports đầy đủ. Khi lời gọi từ bên trong chính target bean dùng `this`, Spring proxy mode thông thường không chặn `protectedRead`. Giải pháp: tách lời gọi bảo vệ sang **bean khác** và gọi qua bean đó, hoặc dùng cơ chế AspectJ có chủ đích và test riêng; không dựa vào gọi nội bộ qua `this`.

### 7.3. Mock cả secured service

Nếu test controller dùng:

~~~java
@MockitoBean
DocumentService service;  // Boot 3.4+; ở một số bản cũ dùng @MockBean
~~~

thì service có thể là mock thay thế, bỏ qua method body/evaluator/security advisor. Test chỉ chứng minh controller gọi mock và map response. Để kiểm tra method security, dùng bean **thật** và chỉ mock dependency mức thấp như repository/ACL provider khi cần. API `@MockBean` và `@MockitoBean` thay đổi theo Spring Boot/Spring Framework version; không trộn hai annotation mà không kiểm tra dependency.

### 7.4. Trông đợi @WithMockUser sẽ tự kết hợp với JUnit thuần

Chỉ viết:

~~~java
@Test
@WithMockUser(username = "alice")
void wrong() {
    new DocumentService(new DocumentStore()).readById(2L);
}
~~~

không kiểm thử enforcement: không có Spring context/proxy. `@WithMockUser` chỉ có tác dụng thiết lập security context khi Spring Security Test Execution Listener hoạt động với Spring Test setup; ngay cả khi có context, nó vẫn **không biến một instance new thành proxy**.

## 8. Ma trận kiểm thử nên có và các case dễ bỏ sót

| Lớp | Input hoặc tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| Unit evaluator | Alice + Document 1 + type Document + read | true |
| Unit evaluator | Alice + Document 2 tenant beta | false |
| Unit evaluator | Alice + Document 3 cùng tenant, owner Bob | false |
| Unit evaluator | Alice thiếu document:read | false |
| Unit evaluator | Alice thiếu tenant:alpha | false |
| Unit evaluator | Sai type Invoice | false |
| Unit evaluator | Permission write chưa hỗ trợ | false |
| Unit evaluator | ID null, ID Integer, ID không tồn tại | false |
| Unit evaluator | Object giả owner Alice cho Document 2 | false |
| Proxy integration | Alice gọi service thật được Spring quản lý với ID 1 | Cho phép và chạy method body |
| Proxy integration | Alice gọi ID 2 | AccessDeniedException; body không chạy |
| Proxy integration | Viewer thiếu authority | AccessDeniedException |
| Proxy integration | Anonymous | Không được cấp quyền |
| Proxy integration | Gọi object overload với forged Document | DENY |
| HTTP integration | Alice đăng nhập Basic, GET Document 1 | 200 và dữ liệu của Alice |
| HTTP integration | Bob đăng nhập Basic, GET Document 1 | 403 |
| HTTP integration | Không đăng nhập | 401 với cấu hình Basic mẫu |
| HTTP integration | ID không tồn tại | 403 trong policy mẫu (không phải luật bắt buộc) |
| Configuration | Xóa @EnableMethodSecurity | Test deny/proxy phải phát hiện |
| Configuration | Không đăng ký evaluator thật | Test grant/proxy phải phát hiện |
| Regression | Chuyển call qua self-invocation | Test security boundary phải phát hiện |
| Transaction/ACL | Quyền bị thu hồi giữa check và use | Không trả/ghi dữ liệu trái quyền |
| Concurrency | Hai người gọi cùng resource, cập nhật owner/tenant | Policy đồng nhất với data-layer scope |

Nên giữ **ít nhất một test grant và một test deny** qua proxy. Chỉ có test deny dễ tạo *false positive*: cấu hình sai dùng deny-all evaluator cũng làm tất cả case deny thành công. Chỉ có test grant cũng dễ sai: annotation không hoạt động nhưng method vẫn trả dữ liệu. Cặp kiểm thử grant/deny kết hợp instrumentation body counter mới cho tín hiệu tốt.

### 8.1. Mutation test tư duy

Thử lần lượt những sai lệch dưới đây và xem test nào phải đỏ:

- Thay `return hasFeature && hasTenant && owns;` thành `return hasFeature;` → unit test tenant/owner khác phải đỏ.
- Thay `"Document".equals(targetType)` thành `true` → unit test sai type phải đỏ.
- Thay `@PreAuthorize("hasPermission(#p0, 'Document', 'read')")` bằng `@PreAuthorize("permitAll")` → proxy deny phải đỏ.
- Bỏ `@EnableMethodSecurity` → các test proxy deny phải đỏ hoặc test proxy phải báo fail.
- Không set `PermissionEvaluator` trên handler → proxy grant phải đỏ.
- Tự tạo `new DocumentService(...)` trong test → việc kiểm chứng proxy phải đỏ.

Tư duy mutation test giúp phát hiện test chỉ kiểm tra implementation “có chạy” mà không kiểm tra invariant bảo mật quan trọng.

## 9. Java 17 thuần: mô phỏng unit decision và điểm intercept

Ví dụ này không dùng Spring hay AOP thật. Nó chỉ tách rõ **policy** và **decorator chặn quyền** để bạn thấy unit test chính sách không đồng nghĩa bảo vệ lời gọi dịch vụ. Lưu thành `PermissionBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class PermissionBoundaryDemo {
    record Actor(String name, String tenant, Set<String> authority) {}
    record Doc(long id, String owner, String tenant) {}

    static final Map<Long, Doc> DATA = Map.of(
            1L, new Doc(1L, "alice", "alpha"),
            2L, new Doc(2L, "bob", "beta"));

    static boolean allow(Actor actor, long id) {
        Doc doc = DATA.get(id);
        return actor != null && doc != null
                && actor.authority().contains("document:read")
                && actor.tenant().equals(doc.tenant())
                && actor.name().equals(doc.owner());
    }

    interface Reader {
        Doc read(long id);
    }

    static final class PlainReader implements Reader {
        public Doc read(long id) {
            return DATA.get(id); // Không tự thực hiện authorization.
        }
    }

    static final class CheckingReader implements Reader {
        private final Actor actor;
        private final Reader target;

        CheckingReader(Actor actor, Reader target) {
            this.actor = actor;
            this.target = target;
        }

        public Doc read(long id) {
            if (!allow(actor, id)) {
                throw new SecurityException("denied");
            }
            return target.read(id);
        }
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", "alpha", Set.of("document:read"));
        Actor bob = new Actor(
                "bob", "beta", Set.of("document:read"));
        Reader plain = new PlainReader();

        System.out.println("unit-alice-id1=" + allow(alice, 1L));
        System.out.println("unit-bob-id1=" + allow(bob, 1L));

        // Bỏ qua decorator: PlainReader tự nó không có kiểm tra quyền.
        System.out.println("plain-bob-reads-id1=" +
                (plain.read(1L) != null));

        Reader guarded = new CheckingReader(bob, plain);
        try {
            guarded.read(1L);
            System.out.println("guarded-bob=allowed");
        } catch (SecurityException denied) {
            System.out.println("guarded-bob=denied");
        }

        Reader aliceGuarded = new CheckingReader(alice, plain);
        System.out.println("guarded-alice-id1=" +
                aliceGuarded.read(1L).owner());
    }
}
~~~

Biên dịch bằng JDK 17:

~~~bash
javac --release 17 PermissionBoundaryDemo.java
java PermissionBoundaryDemo
~~~

**stdout chính xác:**

~~~text
unit-alice-id1=true
unit-bob-id1=false
plain-bob-reads-id1=true
guarded-bob=denied
guarded-alice-id1=alice
~~~

Ý nghĩa: `allow(bob, 1L)` đã trả false đúng trong unit test; tuy nhiên `PlainReader.read(1)` vẫn trả dữ liệu nếu caller bỏ qua decorator. Spring AOP/method-security proxy là một cách framework thực thi ranh giới này; unit test policy không thể tự chứng minh mọi đường gọi đều qua interceptor.

## 10. Độ tin cậy của test: fixture, thread, transaction và exception

### 10.1. Xử lý state giữa các test

Bộ demo trên dùng `Map.of` bất biến và body counter chỉ kiểm tra **chênh lệch tại thời điểm một test**, không assert một tổng tuyệt đối xuyên nhiều test. Nếu test thay đổi quyền, ACL, DB hoặc trạng thái tài liệu, phải tạo fixture độc lập/rollback transaction hoặc reset state. Không làm test phụ thuộc thứ tự chạy hoặc dữ liệu còn lại từ test trước.

Một transaction của `@Transactional` trong test có thể rollback dữ liệu fixture, nhưng không nên giả định nó bảo vệ mọi tác vụ async, external API hoặc thread khác. Với tích hợp persistence, kiểm thử isolation, optimistic locking và query scope riêng.

### 10.2. Lỗi trong unit test khác lỗi ở proxy

`PermissionEvaluator.hasPermission(...)` tự nó trả `false`. `@PreAuthorize` dùng kết quả này và chặn lời gọi bằng exception. Khi qua Servlet HTTP, filter/handler đổi exception thành response. Ba kết quả quan sát được khác nhau là bình thường:

~~~text
Unit:        false
Service:     AccessDeniedException (hoặc subtype)
HTTP:        403 / 401 / 404 theo security và API policy
~~~

Nếu test chỉ assert boolean trực tiếp mà mong nhận 403, test sai tầng. Nếu test HTTP mong `AccessDeniedException` ném trực tiếp ra JUnit, có thể exception đã được xử lý thành response theo filter chain, cũng sai tầng.

### 10.3. 401, 403 và 404 cần hợp đồng rõ

Trong demo, unknown ID khiến evaluator false và method không chạy; HTTP là 403 với người đã xác thực. Đó không phải cách duy nhất: một API chống enumeration có thể cố ý trả 404 đồng nhất cho tài nguyên không tồn tại và tài nguyên không nhìn thấy. Test cần bám **chính sách do ứng dụng lựa chọn**, không suy diễn trạng thái HTTP từ riêng interface `PermissionEvaluator`.

### 10.4. Null, anonymous và authenticated principal

Unit test truyền `null Authentication` để kiểm tra evaluator fail-closed. Spring method-security infrastructure thường quản lý authentication/anonymous theo cấu hình và có thể phát lỗi khác nếu security context không hợp lệ. Đừng mặc định kết quả unit với null tái hiện chính xác codepath HTTP anonymous. Viết test anonymous ở tầng integration riêng.

### 10.5. Test performance và N+1

Một `PermissionEvaluator` có thể lookup ACL mỗi lần gọi. Với `@PostFilter` trên danh sách dài, số query có thể tăng theo số phần tử; test unit nhanh không phản ánh vấn đề này. Thêm kiểm thử SQL count/pagination và tenant scoping. Nếu quyền phức tạp, cân nhắc batch ACL query hoặc predicate lọc tại DB thay vì tải cả bảng rồi lọc sau.

### 10.6. TOCTOU giữa permission check và sử dụng dữ liệu

`@PreAuthorize` có thể kiểm tra document tại t1; service thực hiện query/update tại t2; owner hoặc tenant đã đổi. Integration test proxy vẫn có thể xanh dù production có race. Với thao tác ghi, kiểm tra quyền trên dữ liệu tin cậy trong transaction/câu lệnh update có điều kiện cùng version/lock; với truy vấn đọc, giới hạn theo tenant/ACL ở data layer. Test concurrency ở phạm vi hệ thống phù hợp.

### 10.7. Lỗi hạ tầng không phải “người dùng không có quyền”

Nếu ACL service/DB timeout, đừng bắt `Exception` rồi `return true`. Tùy contract, có thể trả deny an toàn hoặc ném exception dẫn tới lỗi server, đồng thời log an toàn. Unit test nên cover các nhánh lỗi của gateway; integration test nên xác nhận **không trả dữ liệu** khi gateway thất bại. Không tiết lộ credential/token và ACL nội bộ trong response.

## 11. Một quy trình QA có thể áp dụng lại

1. **Viết contract trước:** ai, tài nguyên nào, quyền gì, tenant/owner/ACL lấy từ đâu, missing data xử lý thế nào.
2. **Unit evaluator:** table-driven test mọi combination grant/deny, null, sai type, sai ID, permission không hỗ trợ và object giả.
3. **Cấu hình method security:** bật `@EnableMethodSecurity`, đăng ký `MethodSecurityExpressionHandler` cùng evaluator thực.
4. **Integration qua bean Spring:** `@Autowired` service, kiểm tra proxy, một ca GRANT, một ca DENY và body không chạy khi deny.
5. **HTTP integration:** `MockMvc` có security filters, request authentication thực, 200/401/403 theo policy; không chỉ dùng `standaloneSetup` bỏ filter.
6. **Thử đường gọi khác:** scheduled jobs, message listeners, internal calls, self-invocation, async executor — service nhạy cảm phải được bảo vệ bất kể entrypoint.
7. **Kiểm tra hiệu năng và đồng thời:** ACL lookup, N+1, tenant scope, quyền bị thu hồi, race t1→t2, transaction/locking.
8. **Mutation check:** cố tình làm permission grant sai hoặc tắt annotation để chứng minh test phát hiện regression.

### Câu hỏi tự kiểm tra

**Câu 1:** Test gọi `new DocumentPermissionEvaluator(new DocumentStore()).hasPermission(...)` trả false cho Bob. Có chứng minh `@PreAuthorize` trên service hoạt động không?

**Đáp án:** Không. Nó chỉ kiểm tra evaluator. Phải gọi service bean Spring qua proxy với security context của Bob và assert bị từ chối.

**Câu 2:** Một integration suite chỉ có case “người không được phép bị từ chối” nhưng không có case grant. Rủi ro gì?

**Đáp án:** Handler có thể chưa dùng custom evaluator và default deny-all vẫn khiến test deny xanh. Bổ sung case grant trên tài nguyên hợp lệ.

**Câu 3:** `@WithMockUser` và `httpBasic(...)` trong MockMvc có tương đương không?

**Đáp án:** Không hoàn toàn. `@WithMockUser` thiết lập authentication test; `httpBasic(...)` tạo header để request trải qua Basic authentication và user lookup của filter chain. Chọn theo tầng muốn kiểm tra.

**Câu 4:** Gọi `this.readById(...)` từ chính một service bean có đáng tin là sẽ chạy `@PreAuthorize` không?

**Đáp án:** Không trong proxy mode mặc định. Lời gọi nội bộ bypass Spring proxy; tách secured method sang bean khác hoặc dùng interception được cấu hình riêng và test.

**Câu 5:** MockMvc trả 403 cho ID 999 nghĩa là ID 999 tồn tại nhưng người dùng không có quyền?

**Đáp án:** Không. Trong demo, evaluator trả false nếu ID không tồn tại, nên `@PreAuthorize` chặn trước method. Không thể suy ra sự tồn tại từ riêng mã 403; chính sách API phải được thiết kế nhất quán.

## Tài liệu tham khảo

- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, proxy, `PreAuthorizeAuthorizationManager`, tùy biến `MethodSecurityExpressionHandler`.
- [PermissionEvaluator Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): hai overload và contract boolean.
- [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): thiết lập `MockMvc` với Spring Security.
- [Spring Security – HTTP Basic Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html): `httpBasic(...)` request post-processor.
