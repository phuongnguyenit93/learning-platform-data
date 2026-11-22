# Kiểm thử AuthorizationManager tùy chỉnh ở tầng phương thức: cho phép, từ chối, không quyết định và lỗi

## 1. Mục tiêu và phạm vi

Bài này kiểm thử **manager phân quyền tùy chỉnh cho lời gọi phương thức** trong Spring Security: khi nào cho phép thực thi, khi nào chặn, khi nào không đưa ra quyết định và khi nào chính sách bị lỗi. Trọng tâm là `AuthorizationManager<MethodInvocation>`, `AuthorizationResult`/`AuthorizationDecision` và `AuthorizationManagerBeforeMethodInterceptor` ở ứng dụng Java đồng bộ sử dụng Spring AOP.

Sau bài học, bạn có thể:
- Phân biệt bốn kết quả **grant**, **deny**, **abstain** (trả về `null`) và **error** (ném ngoại lệ); không gộp abstain với deny hoặc error.
- Viết unit test kiểm tra kết quả trực tiếp từ manager, đồng thời viết test đi qua proxy để chứng minh method thực sự chạy hoặc bị chặn.
- Xác minh quyền trong `Authentication`, số lần thực thi method, ngoại lệ đúng loại, và tình trạng `SecurityContext` giữa các test.
- Phát hiện rủi ro nếu một chính sách quan trọng trả về `null` mà không có chính sách khác bảo vệ.

**Giả định cho ví dụ chạy được:** Java 17+, JUnit Jupiter 5, Spring AOP, Spring Security 6.4–6.5 (chẳng hạn Spring Boot 3.5). Cách khai báo manager bằng lambda cũng tương thích với thay đổi của Spring Security 7, nhưng phiên bản dependency và cấu hình ứng dụng phải đồng bộ. Đây là thử nghiệm **method security**; không đưa ra giả định về HTTP status hay kiểm thử WebFlux.

## 2. Hợp đồng quyết định của manager

`AuthorizationManager` nhận hai dữ kiện: một `Supplier<Authentication>`, được gọi khi cần thông tin người dùng, và đối tượng đang được bảo vệ. Với method security trước khi gọi, đối tượng là `MethodInvocation`, cung cấp method, tham số và target của lời gọi.

| Tình huống | Manager trả về / ném ra | Kết quả cần kiểm thử tại interceptor trước method |
| --- | --- | --- |
| Cho phép (grant) | `new AuthorizationDecision(true)` | Lời gọi tiếp tục đến method, trả kết quả nghiệp vụ |
| Từ chối (deny) | `new AuthorizationDecision(false)` | Ném `AccessDeniedException` (có thể là lớp con `AuthorizationDeniedException`); method chưa chạy |
| Không quyết định (abstain) | `null` | Manager không đưa ra phán quyết; **không tự đồng nghĩa với từ chối**. Trong ví dụ chỉ có một interceptor, lời gọi tiếp tục; trong ứng dụng thật phải xét toàn bộ chuỗi advisor/chính sách |
| Lỗi chính sách (error) | Ví dụ `IllegalStateException` | Ngoại lệ lan ra; method chưa chạy. Đây là lỗi xử lý/quyết định, khác với kết quả deny |

Dòng chảy trước method trong ví dụ:

~~~text
Client → Spring AOP proxy → AuthorizationManagerBeforeMethodInterceptor
                                   │
                                   ├─ grant ────→ proceed() → service method
                                   ├─ deny ─────→ AccessDeniedException
                                   ├─ null ─────→ không chặn tại interceptor này → proceed()
                                   └─ error ────→ ngoại lệ chính sách, không proceed()
~~~

`verify(...)` dùng kết quả `authorize(...)` để ném `AccessDeniedException` khi kết quả phủ định; `authorize(...)` dùng để quan sát trực tiếp cả grant/deny/abstain. Từ Spring Security 6.4, `authorize(...)` là API được ưu tiên; trong nhánh 6.x, `check(...)` cũ còn tồn tại và đã deprecated, còn Spring Security 7 thay đổi hợp đồng abstract. **Dùng lambda trong ví dụ** để không phải viết thủ công một phương thức override khác nhau giữa các nhánh.

**Điểm bảo mật cần hiểu:** giả sử manager duy nhất trả về `null` cho method nhạy cảm. Nếu không có advisor nào khác từ chối, lời gọi có thể đi qua. Đối với quyền bắt buộc, một phương án an toàn là trả quyết định phủ định rõ ràng khi không đánh giá được; không dùng `null` như cách mặc định từ chối.

## 3. Chuẩn bị project và dependency

Ví dụ chạy trong project Spring Boot Java có cấu hình JUnit 5. Với Gradle Groovy DSL, các dependency liên quan là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Chọn một phiên bản Spring Boot quản lý Spring Security 6.4+ (ví dụ Boot 3.5 sử dụng dòng Security 6.5). Đoạn trên là phần `dependencies` của project đã có Spring Boot plugin và BOM; không phải một `build.gradle` độc lập. JUnit 5 và Mockito được kéo vào từ `spring-boot-starter-test`.

Tạo file **`src/test/java/example/security/DocumentMethodAuthorizationTest.java`** với toàn bộ nội dung sau. Không cần khởi động HTTP server hoặc ApplicationContext: test tạo proxy Spring AOP thật để kiểm tra interceptor. Các nhánh quyền và lỗi là **fixture giảng dạy có chủ đích**, không phải mẫu kết nối tới hệ thống phân quyền từ xa trong production.

~~~java
package example.security;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.Pointcut;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DocumentMethodAuthorizationTest {

    interface DocumentService {
        String read();
        String delete();
        String legacy();
        String unavailable();
    }

    static final class CountingDocumentService implements DocumentService {
        final AtomicInteger calls = new AtomicInteger();

        @Override
        public String read() {
            calls.incrementAndGet();
            return "read-ok";
        }

        @Override
        public String delete() {
            calls.incrementAndGet();
            return "delete-ok";
        }

        @Override
        public String legacy() {
            calls.incrementAndGet();
            return "legacy-ok";
        }

        @Override
        public String unavailable() {
            calls.incrementAndGet();
            return "unavailable-ok";
        }
    }

    // Lambda tương thích với kiểu SAM của AuthorizationManager ở 6.5/7.
    private static AuthorizationManager<MethodInvocation> manager() {
        return (authentication, invocation) ->
                switch (invocation.getMethod().getName()) {
                    case "read" -> new AuthorizationDecision(
                            hasAuthority(authentication.get(), "document:read"));
                    case "delete" -> new AuthorizationDecision(
                            hasAuthority(authentication.get(), "document:delete"));
                    case "legacy" -> null; // Chỉ để kiểm thử abstain.
                    case "unavailable" ->
                            throw new IllegalStateException("policy service unavailable");
                    default -> new AuthorizationDecision(false);
                };
    }

    private static boolean hasAuthority(Authentication authentication, String required) {
        return authentication != null
                && authentication.isAuthenticated()
                && authentication.getAuthorities().stream()
                    .anyMatch(a -> required.equals(a.getAuthority()));
    }

    private static Authentication userWith(String... authorities) {
        return new UsernamePasswordAuthenticationToken(
                "alice",
                "n/a",
                Arrays.stream(authorities)
                        .map(SimpleGrantedAuthority::new)
                        .toList());
    }

    private CountingDocumentService target;
    private DocumentService service;

    @BeforeEach
    void setUp() {
        target = new CountingDocumentService();

        ProxyFactory factory = new ProxyFactory(target);
        factory.setInterfaces(DocumentService.class);
        factory.addAdvisor(new AuthorizationManagerBeforeMethodInterceptor(
                Pointcut.TRUE, manager()));
        service = (DocumentService) factory.getProxy();

        SecurityContextHolder.getContext()
                .setAuthentication(userWith("document:read"));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    // Mockito chỉ tạo MethodInvocation cho unit test trực tiếp manager.
    private MethodInvocation invocation(String methodName) throws NoSuchMethodException {
        MethodInvocation invocation = mock(MethodInvocation.class);
        when(invocation.getMethod())
                .thenReturn(DocumentService.class.getMethod(methodName));
        return invocation;
    }

    @Test
    void unitTestObservesGrantDenyAndAbstainExactly() throws Exception {
        AuthorizationManager<MethodInvocation> policy = manager();
        Supplier<Authentication> currentUser =
                () -> SecurityContextHolder.getContext().getAuthentication();

        AuthorizationResult grant = policy.authorize(currentUser, invocation("read"));
        AuthorizationResult deny = policy.authorize(currentUser, invocation("delete"));
        AuthorizationResult abstain = policy.authorize(currentUser, invocation("legacy"));

        assertTrue(grant.isGranted());
        assertFalse(deny.isGranted());
        assertNull(abstain);
        assertEquals(0, target.calls.get()); // Gọi manager không gọi service.
    }

    @Test
    void unitTestObservesPolicyErrorExactly() throws Exception {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> manager().authorize(
                        () -> userWith("document:read"),
                        invocation("unavailable")));

        assertEquals("policy service unavailable", error.getMessage());
        assertEquals(0, target.calls.get());
    }

    @Test
    void grantRunsProtectedMethodOnce() {
        assertEquals("read-ok", service.read());
        assertEquals(1, target.calls.get());
    }

    @Test
    void denyBlocksMethodBeforeSideEffect() {
        assertThrows(AccessDeniedException.class, () -> service.delete());
        assertEquals(0, target.calls.get());
    }

    @Test
    void abstainProceedsWithOnlyThisAdvisorInstalled() {
        assertEquals("legacy-ok", service.legacy());
        assertEquals(1, target.calls.get());
    }

    @Test
    void policyErrorPropagatesBeforeSideEffect() {
        IllegalStateException error =
                assertThrows(IllegalStateException.class, () -> service.unavailable());
        assertEquals("policy service unavailable", error.getMessage());
        assertEquals(0, target.calls.get());
    }

    @Test
    void explicitDeleteAuthorityChangesDenyIntoGrant() {
        SecurityContextHolder.getContext()
                .setAuthentication(userWith("document:delete"));

        assertEquals("delete-ok", service.delete());
        assertEquals(1, target.calls.get());
    }
}
~~~

Chạy từ thư mục project đã có Gradle wrapper:

~~~bash
./gradlew test --tests 'example.security.DocumentMethodAuthorizationTest'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.security.DocumentMethodAuthorizationTest"
~~~

Kết quả kỳ vọng: **7 test thành công** nếu project có dependency đúng và không có cấu hình test bên ngoài thay đổi proxy/security context. JUnit không yêu cầu một chuỗi stdout cố định; hãy xem test report do Gradle tạo để xác nhận từng case.

## 4. Đọc hiểu từng lớp kiểm thử

### 4.1. Unit test của manager: kiểm tra hợp đồng quyết định

`unitTestObservesGrantDenyAndAbstainExactly` gọi `manager.authorize(...)` trực tiếp với `MethodInvocation` được Mockito mô phỏng. Nó kiểm tra rõ:

- `read` + authority `document:read` → `AuthorizationResult.isGranted() == true`.
- `delete` + chỉ `document:read` → kết quả khác `null` và `isGranted() == false`.
- `legacy` → chính xác `null`, không phải `new AuthorizationDecision(false)`.
- Không phương thức service nào đã chạy khi chỉ đánh giá chính sách.

`unitTestObservesPolicyErrorExactly` buộc nhánh hỏng policy ném `IllegalStateException` và giữ nguyên thông điệp lỗi; đây không phải test từ chối quyền. Nếu viết `assertFalse(result.isGranted())` cho nhánh lỗi, test đã gộp sai hai lớp kết quả.

### 4.2. Kiểm thử đi qua proxy: kiểm tra ảnh hưởng thực tế

Test dùng `ProxyFactory` và `AuthorizationManagerBeforeMethodInterceptor`, rồi gọi **`service` là proxy**, không gọi trực tiếp `target`. Bộ đếm `target.calls` quan sát việc thân phương thức đã thực thi hay chưa:

| Test | Lời gọi qua proxy | Assertion chính | Số lần target chạy |
| --- | --- | --- | --- |
| `grantRunsProtectedMethodOnce` | `service.read()` | Trả `"read-ok"` | 1 |
| `denyBlocksMethodBeforeSideEffect` | `service.delete()` | Ném `AccessDeniedException` | 0 |
| `abstainProceedsWithOnlyThisAdvisorInstalled` | `service.legacy()` | Trả `"legacy-ok"` | 1 |
| `policyErrorPropagatesBeforeSideEffect` | `service.unavailable()` | Ném `IllegalStateException` | 0 |
| `explicitDeleteAuthorityChangesDenyIntoGrant` | `service.delete()` với quyền khác | Trả `"delete-ok"` | 1 |

Điểm quan trọng của case **abstain**: một kết quả `null` chứng minh manager không quyết định; việc method tiếp tục chạy là hành vi của cấu hình test chỉ gắn **một advisor**. Nếu ứng dụng có thêm `@PreAuthorize`, `@Secured` hoặc advisor khác, các chính sách ấy có thể chặn. Vì vậy không biến quan sát của test thành khẳng định rằng `null` luôn cho phép trong mọi ứng dụng.

Điểm quan trọng của case **deny/error**: assertion đếm bằng **0** xác minh hành động nghiệp vụ chưa có cơ hội tạo side effect, thay vì chỉ kiểm tra exception. Khi service thực hiện ghi database, gửi message hoặc gọi API, kiểm tra side effect bằng mock hoặc trạng thái test database phù hợp.

### 4.3. Kiểm thử đổi authority

`explicitDeleteAuthorityChangesDenyIntoGrant` dùng cùng method `delete` nhưng thay người dùng hiện tại bằng authority `document:delete`. Điều này kiểm tra manager dựa trên quyền thật trong `Authentication`, tránh test chỉ chọn kết quả cố định theo tên method mà bỏ qua chủ thể.

Authority so khớp chính xác chuỗi. `document:delete` không tự tương đương `ROLE_document:delete`. `roles` trong `@WithMockUser` tự thêm tiền tố `ROLE_`, còn `authorities` giữ nguyên; hãy chọn đúng kiểu khi chuyển sang Spring TestContext.

### 4.4. Cách quản lý SecurityContext

`@BeforeEach` cài một `Authentication` được xác thực để interceptor nhận diện user; `@AfterEach` gọi `SecurityContextHolder.clearContext()` nhằm tránh user của test trước rò sang test sau. Mỗi test nhận một target, proxy và bộ đếm mới nên độc lập về thứ tự chạy. Chạy method trên bean tự tạo bằng `new` mà không qua proxy sẽ bỏ qua interceptor và cho kết quả sai.

## 5. Chuyển từ fixture sang kiểm thử ứng dụng

Trong ứng dụng thật, `@EnableMethodSecurity` kích hoạt method security; sau đó bạn đăng ký advisor có **pointcut giới hạn đúng service/annotation được bảo vệ** và manager phù hợp. Không đưa `Pointcut.TRUE` của fixture vào toàn bộ ApplicationContext vì nó sẽ áp chính sách thử nghiệm cho nhiều bean ngoài phạm vi. Khi cần thay cho interceptor mặc định của `@PreAuthorize`, cần cấu hình các interceptor mặc định một cách chủ đích để tránh policy chồng nhau.

Một kiểm thử integration nên lấy service từ Spring container, gọi qua bean proxy và dùng `@WithMockUser(authorities = "document:read")` hoặc `@WithUserDetails` nếu ứng dụng đòi principal tùy chỉnh. Kiểm tra tiếp từng tình huống grant/deny/abstain/error và xác minh side effect. Cần có `testImplementation 'org.springframework.security:spring-security-test'` cho các annotation hỗ trợ test của Spring Security. Kiểm tra thứ tự nhiều advisor nếu ứng dụng có cả `@PreAuthorize`/`@PostAuthorize`; một manager trả `null` không vô hiệu hóa rào chắn của advisor khác.

Gợi ý mở rộng ma trận khi áp dụng logic production:

| Biên cần kiểm thử | Kết quả mong đợi |
| --- | --- |
| User có đúng authority | Grant |
| User thiếu authority hoặc chỉ có authority gần giống | Deny |
| Tài nguyên không thuộc sở hữu user | Deny; không gọi thao tác ghi |
| Thông tin authentication/principal không hợp lệ | Chính sách xử lý rõ ràng, thường deny thay vì NPE |
| Nhánh policy không áp dụng | Abstain **chỉ khi** có chính sách khác chịu trách nhiệm |
| Dịch vụ policy ngoài bị timeout/lỗi | Bộc lộ lỗi có kiểm soát; không vô tình cho phép |
| Có nhiều advisor | Kết quả cuối và side effect đúng theo thứ tự cấu hình |
| Gọi nội bộ `this.method()`, method không public hoặc bean không được quản lý | Đánh giá khả năng proxy bị bỏ qua; không giả định interceptor vẫn chạy |

Một `AuthorizationManager` đồng bộ không nên che mọi lỗi bằng `catch (Exception) { return new AuthorizationDecision(true); }`. Nếu hệ thống yêu cầu **fail closed**, hãy thiết kế rõ cách từ chối an toàn khi policy service không khả dụng và tách lỗi hạ tầng khỏi trường hợp thiếu quyền để logs/metrics còn chẩn đoán được.

## 6. Lỗi kiểm thử thường gặp và cách sửa

1. **Chỉ mock manager trả true/false.** Cách này kiểm tra interceptor ở mức tối thiểu nhưng không kiểm tra logic manager thật; giữ unit test trực tiếp manager và một nhóm test proxy.
2. **Đồng nhất `null` với false.** Viết hai assertion riêng: `assertNull(abstain)` và `assertFalse(deny.isGranted())`; bổ sung test mức proxy để xác định hậu quả theo cấu hình.
3. **Bắt mọi exception là AccessDenied.** Lỗi policy phải được test đúng loại ngoại lệ và nguyên nhân; `AccessDeniedException` dành cho trường hợp bị từ chối.
4. **Gọi `new ServiceImpl()` trong test tích hợp.** Lời gọi này không đi qua Spring AOP; lấy bean proxy hoặc tạo `ProxyFactory` chủ động như fixture.
5. **Chỉ kiểm tra exception mà không kiểm tra side effect.** Luôn chứng minh method không chạy ở nhánh deny/error, ví dụ bộ đếm hoặc verify mock dependency `never()`.
6. **Quên dọn `SecurityContextHolder`.** Test có thể pass/fail tùy thứ tự, nhất là khi runner dùng lại thread.
7. **Không kiểm tra kiểu authority.** `ROLE_ADMIN` và `ADMIN` là hai chuỗi khác nhau; viết test với chính xác authority mà policy đọc.
8. **Sử dụng API không tương thích phiên bản.** Trên 6.4–6.5, `authorize` có sẵn còn `check` vẫn là abstract đã deprecated; trên 7.x, `authorize` trở thành abstract và `check` bị bỏ. Lambda trong bài giải quyết khác biệt ở chỗ implement, còn `authorize` được gọi trong test nên yêu cầu ít nhất 6.4.

## 7. Checklist hoàn thành

- [ ] Có đủ **bốn trạng thái tách biệt**: grant, deny, null-abstain, exception-error.
- [ ] Unit test quan sát đúng `AuthorizationResult`/`null`, không ép lỗi thành deny.
- [ ] Test qua proxy chứng minh method được chạy khi grant và bị chặn khi deny/error.
- [ ] Test null-abstain diễn giải rõ toàn bộ advisor chain, không mặc định an toàn.
- [ ] Test đổi authority, assert không có side effect khi chặn, và dọn `SecurityContext`.
- [ ] API và dependencies cùng nhánh Spring Security; Java/test chạy được trên project đã cấu hình.
- [ ] Nếu chính sách production quan trọng mà có nhánh không quyết định, đã thiết kế explicit fallback/deny phù hợp.

## 8. Tài liệu để đối chiếu API

- [Authorization Architecture – Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): ý nghĩa grant, deny, abstain của `AuthorizationManager`.
- [Method Security – Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): Spring AOP proxy, interceptor, custom manager, multiple advisors.
- [Testing Method Security – Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` và test với authentication.
- [Javadoc AuthorizationManager (6.5)](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize`, `check`, `verify` và tương thích phiên bản.
