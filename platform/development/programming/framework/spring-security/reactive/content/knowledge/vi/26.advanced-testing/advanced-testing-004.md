# Kiểm thử @PreAuthorize, @PostAuthorize và lời gọi qua Spring proxy trong Spring Security Reactive

## Mục tiêu và phạm vi

Bài học thuộc **Spring Security – reactive / Kiểm thử chuyên sâu**. Sau bài này, bạn có thể: (1) kiểm tra quyền truy cập **trước** khi phương thức được thực thi bằng `@PreAuthorize`; (2) kiểm tra **giá trị trả về** bằng `@PostAuthorize`; (3) xác thực rằng lời gọi thực sự đi qua Spring AOP proxy; (4) phát hiện đường gọi nội bộ `this.method()` bỏ qua advice; và (5) kiểm tra tín hiệu `onNext`, `onError`, `onComplete` của `Mono` bằng `StepVerifier`, thay vì chỉ kiểm tra việc tạo publisher.

Đây là kiểm thử **method security của WebFlux/reactive**. Phần minh họa dùng Java 17+, Spring Boot 3.x / Spring Security 6.x, Reactor và JUnit Jupiter. Không thay thế bằng `@EnableMethodSecurity` của phía servlet: cấu hình tương ứng ở đây là `@EnableReactiveMethodSecurity`.

## 1. Hiểu đúng ba điểm kiểm tra

| Điểm kiểm tra | Thời điểm, điều kiện | Điều cần khẳng định trong test |
| --- | --- | --- |
| `@PreAuthorize("hasRole('EDITOR')")` | Kiểm quyền trước khi cho phép phương thức chạy; trong pipeline reactive, lỗi thường hiện ra khi subscribe | Người đủ quyền nhận giá trị; người thiếu quyền nhận `AccessDeniedException`; logic nhạy cảm không được thực thi |
| `@PostAuthorize("returnObject.owner == authentication.name")` | Kiểm đối tượng kết quả trước khi cho caller nhận đối tượng đó | Đúng chủ sở hữu nhận kết quả; sai chủ sở hữu gặp `AccessDeniedException`, không nhận được đối tượng |
| Spring AOP proxy | Advice method security chạy khi lời gọi đi **vào bean thông qua proxy** | Lời gọi từ bean khác qua bean được inject có kiểm quyền; `this.securedMethod()` bên trong cùng target có thể bỏ qua kiểm quyền |

Luồng khái niệm của một lời gọi hợp lệ: **caller → Spring proxy → kiểm `@PreAuthorize` → target trả về `Mono` → publisher phát dữ liệu → kiểm `@PostAuthorize` (nếu có) → subscriber**. Với reactive method security, danh tính người dùng thường được lấy từ **Reactor Context** qua `ReactiveSecurityContextHolder`, không dựa vào việc gán `SecurityContextHolder` ở một thread rồi kỳ vọng tự truyền qua mọi scheduler.

`hasRole('EDITOR')` so khớp authority `ROLE_EDITOR` theo tiền tố mặc định; `hasAuthority('document:read')` so trực tiếp với chuỗi authority. `@WithMockUser(roles = "EDITOR")` sẽ cung cấp `ROLE_EDITOR`. Người có `ROLE_USER` không tự nhiên có `ROLE_EDITOR`.

**Đặc biệt với `@PostAuthorize`:** quyền được quyết định **sau khi logic tạo ra kết quả đã diễn ra**. Giá trị trái phép bị chặn trước khi gửi tới caller, nhưng truy vấn hoặc tác dụng phụ phía target có thể đã chạy. Không dùng `@PostAuthorize` làm rào bảo vệ duy nhất cho thao tác ghi/xóa hoặc hành động không thể đảo ngược; kiểm quyền trước khi thay đổi trạng thái.

## 2. Chuẩn bị môi trường kiểm thử

Ví dụ sử dụng Gradle trong một dự án Spring Boot có quản lý phiên bản dependency. Các dependency liên quan:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-security-test` cung cấp `@WithMockUser` và test execution listeners. `reactor-test` cung cấp `StepVerifier`; `spring-boot-starter-test` cung cấp Spring Test/JUnit. Đặt ví dụ ở `src/test/java/demo/security/ReactiveMethodSecurityTest.java`. Đây là **một file Java hoàn chỉnh**, sử dụng một ApplicationContext kiểm thử nhỏ với các bean thật, không cần khởi động máy chủ HTTP hay cơ sở dữ liệu.

Cấu hình cần bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`. Cơ chế này hỗ trợ `@PreAuthorize` / `@PostAuthorize` trên bean do Spring quản lý, với phương thức reactive trả về `Mono` hoặc `Flux`. Không dùng `new DocumentService()` làm đối tượng được kiểm thử trực tiếp vì đối tượng tạo thủ công không đi qua proxy của Spring.

## 3. Ví dụ hoàn chỉnh: ba loại kiểm tra trong cùng một test class

~~~java
package demo.security;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ReactiveMethodSecurityTest.TestConfig.class)
class ReactiveMethodSecurityTest {

    @Configuration(proxyBeanMethods = false)
    @EnableReactiveMethodSecurity(useAuthorizationManager = true)
    static class TestConfig {
        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }

        @Bean
        InternalCallService internalCallService() {
            return new InternalCallService();
        }

        @Bean
        DocumentFacade documentFacade(DocumentService documents) {
            return new DocumentFacade(documents);
        }
    }

    public static class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }

    public static class DocumentService {
        private final AtomicInteger published = new AtomicInteger();

        @PreAuthorize("hasRole('EDITOR')")
        public Mono<String> publish(String id) {
            return Mono.defer(() -> {
                published.incrementAndGet();
                return Mono.just("published:" + id);
            });
        }

        @PostAuthorize("returnObject.owner == authentication.name")
        public Mono<Document> findById(String id) {
            String owner = "mine".equals(id) ? "alice" : "bob";
            return Mono.just(new Document(id, owner));
        }

        public int publishedCount() {
            return published.get();
        }

        public void reset() {
            published.set(0);
        }
    }

    // CHỈ để phơi bày lỗi self-invocation, không sao chép làm thiết kế production.
    public static class InternalCallService {
        @PreAuthorize("hasRole('ADMIN')")
        public Mono<String> secret() {
            return Mono.just("secret");
        }

        public Mono<String> throughThis() {
            return this.secret(); // Bỏ qua proxy khi gọi nội bộ.
        }
    }

    // Mẫu an toàn hơn: gọi sang một Spring bean khác đã được inject.
    public static class DocumentFacade {
        private final DocumentService documents;

        public DocumentFacade(DocumentService documents) {
            this.documents = documents;
        }

        public Mono<String> publishThroughBean() {
            return documents.publish("from-facade");
        }
    }

    @Autowired
    DocumentService documents;

    @Autowired
    InternalCallService internalCalls;

    @Autowired
    DocumentFacade facade;

    @BeforeEach
    void resetCounters() {
        documents.reset();
    }

    @Test
    void securedBeanIsReallyProxied() {
        assertTrue(AopUtils.isAopProxy(documents));
        assertTrue(AopUtils.isAopProxy(internalCalls));
    }

    @Test
    void noAuthenticationCannotPublish() {
        StepVerifier.create(documents.publish("doc-1"))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, documents.publishedCount());
    }

    @Test
    @WithMockUser(roles = "USER")
    void wrongRoleIsDeniedBeforeBusinessLogicRuns() {
        StepVerifier.create(documents.publish("doc-1"))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, documents.publishedCount());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void editorCanPublish() {
        StepVerifier.create(documents.publish("doc-1"))
                .expectNext("published:doc-1")
                .verifyComplete();
        assertEquals(1, documents.publishedCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeReturnsDocumentToOwner() {
        StepVerifier.create(documents.findById("mine"))
                .assertNext(doc -> assertEquals("alice", doc.getOwner()))
                .verifyComplete();
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeHidesDocumentFromNonOwner() {
        StepVerifier.create(documents.findById("others"))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(roles = "USER")
    void callingThroughThisBypassesSecurityAdvice() {
        StepVerifier.create(internalCalls.secret())
                .expectError(AccessDeniedException.class)
                .verify();

        // Hành vi CÓ LỖ HỔNG được ghi nhận có chủ đích.
        StepVerifier.create(internalCalls.throughThis())
                .expectNext("secret")
                .verifyComplete();
    }

    @Test
    @WithMockUser(roles = "USER")
    void crossBeanCallStillEnforcesPreAuthorize() {
        StepVerifier.create(facade.publishThroughBean())
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, documents.publishedCount());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void crossBeanCallCanSucceedWithRightRole() {
        StepVerifier.create(facade.publishThroughBean())
                .expectNext("published:from-facade")
                .verifyComplete();
        assertEquals(1, documents.publishedCount());
    }
}
~~~

Chạy từ thư mục dự án Gradle có dependencies ở trên:

~~~bash
./gradlew test --tests demo.security.ReactiveMethodSecurityTest
~~~

Trên Windows có thể dùng `gradlew.bat test --tests demo.security.ReactiveMethodSecurityTest`. Khi cấu hình đúng, các test phải thành công; không cần dựa vào chuỗi stdout cụ thể vì thông báo Gradle phụ thuộc phiên bản và chế độ log. Test `callingThroughThisBypassesSecurityAdvice` **thành công khi chứng minh được lỗ hổng** — nó không chứng minh thiết kế đó an toàn.

### Vì sao các assertion này có ý nghĩa?

- **`wrongRoleIsDeniedBeforeBusinessLogicRuns`**: chỉ `expectError` là chưa đủ để chứng minh target không gây tác dụng phụ. Bộ đếm bằng 0 kiểm tra cả điều kiện không thực thi. Phần publish đặt bên trong `Mono.defer` để tác dụng phụ gắn với lúc subscribe.
- **`editorCanPublish`**: phải subscribe bằng `StepVerifier` để quyền và luồng dữ liệu thực sự được đánh giá; gọi `documents.publish("doc-1")` mà không subscribe không phải là kiểm thử đầy đủ.
- **`postAuthorizeReturnsDocumentToOwner` / `postAuthorizeHidesDocumentFromNonOwner`**: cùng một người dùng `alice`, dữ liệu có hai chủ sở hữu khác nhau; xác minh rằng `returnObject` được kiểm trên **đối tượng kết quả** (`Document`), không phải chỉ role của người gọi.
- **`securedBeanIsReallyProxied`**: chốt giả định nền tảng. Nếu dùng Mockito mock thay cho service hoặc gọi instance tạo bằng `new`, test có thể trả đúng giá trị nhưng annotation hoàn toàn không chạy.
- **`callingThroughThisBypassesSecurityAdvice`**: kiểm soát âm cho lỗi proxy. Gọi công khai `secret()` qua bean bị từ chối, trong khi `throughThis()` gọi `this.secret()` trong target nên đi vòng qua advice.
- **`crossBeanCallStillEnforcesPreAuthorize`**: khi tách orchestration sang một bean khác và inject `DocumentService`, lời gọi lại đi vào proxy. Đây là lựa chọn thiết kế dễ kiểm thử và ít phụ thuộc vào Spring AOP internals.

## 4. Ngữ cảnh bảo mật và timing trong reactive tests

`@WithMockUser` tạo một người dùng giả (không cần bản ghi thật trong database). Trong Spring Test có `WithSecurityContextTestExecutionListener`; với reactive method security, `ReactorContextTestExecutionListener` hỗ trợ đưa security context vào Reactor Context. Khi dùng `@ExtendWith(SpringExtension.class)` và `spring-security-test`, việc subscribe bằng `StepVerifier` trong cùng test giúp mô phỏng authentication cho lời gọi reactive.

Để kiểm soát chính xác auth cho từng publisher khi không muốn dùng `@WithMockUser`, có thể cung cấp `Authentication` trực tiếp vào Reactor Context. Đây là **đoạn thêm vào phương thức test**, dùng các import tương ứng:

~~~java
Authentication editor = new UsernamePasswordAuthenticationToken(
        "alice", "unused",
        List.of(new SimpleGrantedAuthority("ROLE_EDITOR")));

StepVerifier.create(
        documents.publish("manual")
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(editor)))
        .expectNext("published:manual")
        .verifyComplete();
~~~

Các import của đoạn bổ sung: `java.util.List`, `org.springframework.security.core.Authentication`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.core.authority.SimpleGrantedAuthority` và `org.springframework.security.core.context.ReactiveSecurityContextHolder`. Trong cùng test, đừng vừa đặt `@WithMockUser` vừa ghi đè context bằng người dùng khác nếu không chủ đích kiểm tra thứ tự ưu tiên.

**Phân biệt hai thời điểm:** gọi phương thức reactive xây dựng publisher và subscribe vào publisher là hai hành động khác nhau. Kiểm tra `AccessDeniedException` trong `StepVerifier` là kiểm tra kết quả thực tế của pipeline; kiểm tra `assertThrows(..., () -> service.method())` theo thói quen của service đồng bộ thường không kiểm tra đúng thời điểm phát lỗi của reactive flow.

**Không đánh đồng method test với HTTP test:** `StepVerifier` ở đây xác minh `AccessDeniedException`. Mã HTTP 401/403 phụ thuộc vào lớp WebFlux security, authentication entry point và exception handling; muốn khẳng định status thì viết test WebFlux riêng bằng `WebTestClient` và thực sự đưa danh tính vào request (chẳng hạn `mockUser` trong Spring Security test). `@WithMockUser` trên test method thuần túy không mặc nhiên đăng nhập cho một request tới máy chủ HTTP chạy ở thread/process khác.

## 5. Những trường hợp cần bổ sung khi quy tắc thực tế phức tạp hơn

| Trường hợp | Thiết kế test nên có |
| --- | --- |
| `@PreAuthorize` kiểm thêm tham số, ví dụ `#owner == authentication.name` | Kiểm cùng role nhưng owner khớp và không khớp; nếu dùng tên tham số SpEL, bảo đảm Spring lấy được tên tham số khi build (cấu hình compiler `-parameters` hoặc dùng annotation tham số phù hợp) |
| Rule dùng `hasAuthority('document:write')` | Dùng `@WithMockUser(authorities = "document:write")`; không tự thêm `ROLE_` |
| Quy tắc `@PostAuthorize` phụ thuộc field dữ liệu | Tạo hai fixture có cùng shape nhưng khác chủ sở hữu; xác minh unauthorized không nhận `onNext` |
| Logic trả `Flux` | Xác minh thứ tự, số lượng, cả `onComplete` và `onError` bằng `StepVerifier`; trước khi áp dụng post-rule cho collection/stream hãy kiểm đúng semantic của phiên bản Spring Security đang dùng |
| Phân nhánh business trả `Mono.empty()` hoặc `Mono.error(...)` | Kiểm case empty/error riêng; không dùng test thành công có dữ liệu để suy luận quy tắc xử lý empty/error |
| Security expression gọi bean tùy biến (ví dụ `@authz.canRead(...)`) | Test unit biểu thức/bean riêng, sau đó integration test bằng Spring context thật để xác nhận interceptor gọi bean đó |
| Service có `@Transactional` hoặc ghi DB | Kiểm quyền trước side effect, kiểm dữ liệu không đổi ở nhánh denied; `@PostAuthorize` một mình không bảo đảm rollback |
| Gọi qua interface/JDK proxy hoặc class/CGLIB | Inject theo interface khi có JDK proxy; kiểm lời gọi qua bean, và lưu ý `final` / `private` / phương thức không thể bị override có thể không được advice bởi class proxy |
| Có nhiều subscriber, `publishOn` / `subscribeOn` | Kiểm Reactor Context được giữ trong chuỗi; tránh lưu identity vào biến static/ThreadLocal để giả lập auth |

## 6. Lỗi phổ biến và cách chẩn đoán

1. **Quên bật reactive method security.** Test trả dữ liệu cho mọi role vì `@PreAuthorize` chưa có advisor. Kiểm `@EnableReactiveMethodSecurity` trên `@Configuration` của context được test; đừng chỉ kiểm web route security.
2. **Kiểm sai object.** `new Service()`, Mockito mock của cả service, hoặc gọi target lấy từ `AopTestUtils.getTargetObject` có thể bỏ qua advice. Inject bean thật bằng `@Autowired`; mock repository/dependency ở bên dưới service nếu cần.
3. **Tự gọi method trong cùng class.** `this.secured()` hoặc bỏ `this.` vẫn là self-invocation. Đưa phương thức bảo vệ sang bean riêng và inject bean đó; kiểm như `DocumentFacade`.
4. **Không subscribe.** `Mono` lạnh chưa chạy hoặc chưa được kiểm quyền, nhưng test vẫn “pass” vì chỉ kiểm object không null. Dùng `StepVerifier` hoặc một subscriber thực sự.
5. **Nhầm `@PreAuthorize` và `@PostAuthorize`.** Pre kiểm trước logic; post kiểm trên kết quả. Một test “bị chặn” ở post chưa chứng minh database không bị sửa.
6. **Sai role/authority.** `hasRole('ADMIN')` mặc định cần `ROLE_ADMIN`; `hasAuthority('ADMIN')` cần chuỗi đúng `ADMIN`. Thiết lập test user khớp chính xác rule.
7. **Mất Reactor Context.** Tạo authentication trong ThreadLocal, tự subscribe bên ngoài test hoặc tách flow sang cơ chế không truyền context sẽ khiến phương thức báo thiếu quyền dù test tưởng đã đăng nhập. Kiểm luồng context và subscribe trong scope test; dùng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` khi thích hợp.
8. **Test chỉ có happy path.** Với mỗi rule, bắt buộc có trường hợp thiếu auth, sai quyền, đúng quyền, chủ sở hữu đúng/sai; ghi rõ kỳ vọng về dữ liệu và side effect.
9. **Hiểu sai lỗi tầng HTTP.** Trong method test là `AccessDeniedException`; 401/403 là quyết định của filter/handler và cần test request riêng.

Khi một test thất bại, tra theo thứ tự: (a) bean có phải proxy không; (b) annotation có nằm trên method được gọi từ ngoài proxy không; (c) context đã bật reactive method security chưa; (d) auth/authorities đúng không; (e) subscriber có chạy dưới Reactor Context mong muốn không; (f) error hoặc dữ liệu phát từ publisher có đúng kỳ vọng không. Trình tự này thường khoanh vùng nhanh lỗi cấu hình, proxy, identity và logic.

## 7. Checklist chấp nhận và tài liệu tham khảo

- Có **ít nhất một ca cho phép và một ca từ chối** cho mỗi annotation; với `@PostAuthorize` phải thay đổi chủ sở hữu của kết quả, không chỉ role.
- Dùng Spring-managed service bean và `StepVerifier` kiểm tín hiệu cuối cùng (`verifyComplete` / `expectError`).
- Test nhánh denied của `@PreAuthorize` xác minh logic nhạy cảm không chạy; nhánh denied của `@PostAuthorize` xác minh dữ liệu không lộ cho subscriber.
- Có bằng chứng self-invocation bỏ qua advice và lời gọi qua bean tách riêng vẫn thực thi advice.
- Không suy luận tính an toàn từ một test proxy-bypass “pass”: sau khi sửa thiết kế, nên biến nó thành test regression yêu cầu lời gọi đã tách bean cũng bị chặn khi thiếu quyền.

Tài liệu chính thức để đối chiếu hành vi theo phiên bản dùng trong dự án:

- Spring Security – Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – Testing Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/test/method.html
- Spring Security – Testing Method Security, test execution listeners: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework – AOP Proxying Mechanisms (self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
