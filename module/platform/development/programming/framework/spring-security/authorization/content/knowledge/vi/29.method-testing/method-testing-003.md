# @WithAnonymousUser cho tình huống không có người dùng đăng nhập

> **Phạm vi:** kiểm thử **method security** của Spring Security trên ứng dụng Java dùng Spring Framework/Spring Boot. Bài tập trung vào việc gọi các method của Spring bean có `@PreAuthorize`, cách biểu diễn người dùng **anonymous** trong test, và cách khẳng định quyền truy cập hoặc từ chối. Ví dụ dùng Java 17+, JUnit 5 và Spring Security 6.x.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **anonymous không đồng nghĩa với `SecurityContext` hoàn toàn trống**.
2. Dùng `@WithAnonymousUser` để chạy riêng một method test trong vai người chưa đăng nhập, kể cả khi cả test class đang mang `@WithMockUser`.
3. Kiểm tra các biểu thức `isAnonymous()`, `isAuthenticated()`, `permitAll()` và `hasRole(...)` trên method đã được Spring Security bảo vệ.
4. Nhận biết exception đúng khi gọi service trực tiếp, tránh nhầm exception method security với mã HTTP 401/403.
5. Tránh các test "pass giả" do quên bật `@EnableMethodSecurity`, gọi trực tiếp object tạo bằng `new` hoặc bỏ qua Spring AOP proxy.

## 2. Anonymous trong Spring Security là gì?

Một request chưa có người đăng nhập vẫn có thể cần được áp dụng quy tắc bảo mật: cho phép xem phần nội dung công khai, nhưng chặn đọc hồ sơ cá nhân hoặc sửa dữ liệu. Để xử lý nhất quán, Spring Security có cơ chế **anonymous authentication**.

Trên Servlet stack, khi không có `Authentication` từ các cơ chế đăng nhập trước đó, `AnonymousAuthenticationFilter` thường đặt một `AnonymousAuthenticationToken` vào `SecurityContext`. Cấu hình mặc định thường biểu diễn chủ thể là `anonymousUser` với authority `ROLE_ANONYMOUS`. Đây **không phải tài khoản đăng nhập đã được xác minh**.

`@WithAnonymousUser` trong module `spring-security-test` đưa một `AnonymousAuthenticationToken` vào `SecurityContextHolder` của test thông qua `WithSecurityContextTestExecutionListener`. Vì thế:

- `SecurityContextHolder.getContext().getAuthentication()` **có thể khác `null`** trong test anonymous.
- `authentication.getPrincipal()` mặc định là `anonymousUser`; authority anonymous mặc định là `ROLE_ANONYMOUS`.
- `AnonymousAuthenticationToken.isAuthenticated()` có thể trả `true` theo nghĩa **trạng thái nội bộ của token**. Điều này **không có nghĩa người dùng đã đăng nhập**. Spring Security dùng `AuthenticationTrustResolver` để xác định đây vẫn là anonymous; biểu thức phân quyền `isAuthenticated()` **không coi anonymous là người đăng nhập**.
- `@WithAnonymousUser` chỉ chuẩn bị security context cho bài test; annotation **không thực hiện HTTP login/logout**, không gọi `AnonymousAuthenticationFilter` qua HTTP và không chứng minh cơ chế session/token production đã chạy.

**Không nên** kiểm tra login bằng `authentication != null` hoặc chỉ bằng `authentication.isAuthenticated()` khi ứng dụng có anonymous token. Đối với phân quyền hãy ưu tiên biểu thức `isAnonymous()`/`isAuthenticated()`; khi cần phân loại trong Java, có thể sử dụng `AuthenticationTrustResolver`.

### Anonymous khác với một ngữ cảnh chưa được nạp

| Trạng thái | `SecurityContext` | Ý nghĩa trong test |
| --- | --- | --- |
| `@WithAnonymousUser` | Có `AnonymousAuthenticationToken` | Giả lập một anonymous principal có ý nghĩa với `isAnonymous()` |
| `@WithMockUser` | Có `UsernamePasswordAuthenticationToken` của user giả | Giả định người dùng đã xác thực, có các authority/role mà test cấp |
| Test không có annotation và không được cấp auth bằng cách khác | Có thể không có `Authentication` | Không đảm bảo tương đương anonymous; tùy biểu thức/cấu hình có thể ném `AuthenticationCredentialsNotFoundException` |
| Request Servlet thực qua filter chain | `AnonymousAuthenticationFilter` có thể bổ sung token nếu chưa có auth | Kiểm tra đường chạy web cần test web/HTTP riêng |

Vì vậy, test `@WithAnonymousUser` hữu ích khi yêu cầu là **kiểm tra phân quyền ở tầng method trong ngữ cảnh anonymous một cách tường minh và ổn định**.

## 3. Cách @WithAnonymousUser được áp dụng trong test

Annotation được gắn lên **test method** hoặc **test class**:

~~~java
@Test
@WithAnonymousUser
void guestCannotReadPrivateData() {
    // Gọi service bean đã được bảo vệ bởi method security.
}
~~~

Nó dựa trên Spring TestContext, chẳng hạn JUnit 5 `SpringExtension` hoặc `@SpringBootTest`. Spring Security Test sử dụng `WithSecurityContextTestExecutionListener` để chuẩn bị `SecurityContextHolder` cho mỗi test rồi dọn context sau đó. Không phải tự gán principal vào biến ThreadLocal hay gọi `SecurityContextHolder.clearContext()` trong các test thông thường.

Trường hợp dùng nhiều nhất là **class mặc định chạy như người đã đăng nhập** nhưng muốn kiểm thử một vài ca ngoại lệ không đăng nhập:

~~~java
@WithMockUser(username = "member", roles = "USER")
class ExampleTests {

    @Test
    void memberCanReadOwnProfile() {
        // Nhận Authentication của "member".
    }

    @Test
    @WithAnonymousUser
    void guestCannotReadOwnProfile() {
        // Annotation trên method ghi đè bối cảnh @WithMockUser của class.
    }
}
~~~

Nếu bạn không gắn `@WithAnonymousUser` tại method thứ hai, nó vẫn được chạy với user `member` do annotation ở class và có thể không thử được trường hợp anonymous.

Mặc định context được thiết lập ở pha `TestExecutionEvent.TEST_METHOD`, tức trước callback `@BeforeEach` của JUnit. Nếu cần thiết lập **sau** `@BeforeEach` nhưng trước thân `@Test`, dùng:

~~~java
@WithAnonymousUser(setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

Chỉ đổi thời điểm này khi setup của test thực sự phụ thuộc thứ tự khởi tạo security context. Với các test thông thường hãy giữ mặc định.

## 4. Ví dụ hoàn chỉnh: kiểm thử phân quyền method với anonymous

Ta xây dựng một Spring bean `ResourceService` có bốn hành vi:

- `help()`: ai cũng xem được, kể cả anonymous và người đã đăng nhập.
- `guestWelcome()`: chỉ anonymous được gọi; người đã đăng nhập sẽ không thỏa `isAnonymous()`.
- `dashboard()`: cần một người đã xác thực.
- `adminPanel()`: cần authority `ROLE_ADMIN`.

Mục đích bài test là chứng minh các **quyết định authorization khi gọi method của Spring bean**, không cần mở HTTP server.

### 4.1. Dependencies

Trong project Java 17+ dùng Spring Boot quản lý phiên bản dependency, cần các dependency tương ứng (trích đoạn `build.gradle`):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-security-test` cung cấp `@WithAnonymousUser`/`@WithMockUser`. `spring-boot-starter-test` cung cấp JUnit Jupiter và Spring Test. Cấu hình `@EnableMethodSecurity` trong ví dụ là bắt buộc để các `@PreAuthorize` thực sự được thực thi.

### 4.2. Toàn bộ file test

Đặt file tại `src/test/java/com/example/authorization/AnonymousMethodSecurityTest.java`:

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = AnonymousMethodSecurityTest.TestConfig.class)
@WithMockUser(username = "member", roles = "USER")
class AnonymousMethodSecurityTest {

    @Autowired
    ResourceService service; // Bean lấy từ Spring context, đã qua AOP proxy.

    @Test
    @WithAnonymousUser
    void anonymousCanReadPublicHelp() {
        assertEquals("public help", service.help());
    }

    @Test
    @WithAnonymousUser
    void anonymousCanCallGuestOnlyMethod() {
        assertEquals("welcome guest", service.guestWelcome());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotAccessAuthenticatedMethod() {
        assertThrows(AccessDeniedException.class,
                () -> service.dashboard());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotAccessAdminMethod() {
        assertThrows(AccessDeniedException.class,
                () -> service.adminPanel());
    }

    @Test
    @WithAnonymousUser
    void anonymousContextHasTokenButIsNotLoggedIn() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertInstanceOf(AnonymousAuthenticationToken.class, authentication);
        assertEquals("anonymousUser", authentication.getPrincipal());

        AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        assertTrue(trustResolver.isAnonymous(authentication));
        assertTrue(authentication.isAuthenticated());
        // isAuthenticated() của token KHÔNG đồng nghĩa login thực.
    }

    @Test
    void classLevelMockUserMayAccessAuthenticatedMethod() {
        assertEquals("member dashboard", service.dashboard());
    }

    @Test
    void classLevelMockUserIsNotAnonymous() {
        assertThrows(AccessDeniedException.class,
                () -> service.guestWelcome());

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        assertFalse(trustResolver.isAnonymous(authentication));
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminMayAccessAdminMethod() {
        assertEquals("admin panel", service.adminPanel());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class TestConfig {
        @Bean
        ResourceService resourceService() {
            return new ResourceService();
        }
    }

    public static class ResourceService {

        @PreAuthorize("permitAll()")
        public String help() {
            return "public help";
        }

        @PreAuthorize("isAnonymous()")
        public String guestWelcome() {
            return "welcome guest";
        }

        @PreAuthorize("isAuthenticated()")
        public String dashboard() {
            return "member dashboard";
        }

        @PreAuthorize("hasRole('ADMIN')")
        public String adminPanel() {
            return "admin panel";
        }
    }
}
~~~

Chạy (trên macOS/Linux; Windows dùng `gradlew.bat`):

~~~bash
./gradlew test --tests com.example.authorization.AnonymousMethodSecurityTest
~~~

**Kết quả kỳ vọng:** 8 test thành công và không có stdout nghiệp vụ cố định. Các method bị từ chối ném một ngoại lệ thuộc họ `AccessDeniedException`; những method được phép trả lại chuỗi chính xác mà assertion kiểm tra.

| Context của test | Lời gọi | Kỳ vọng |
| --- | --- | --- |
| Anonymous | `help()`, `permitAll()` | Cho phép, trả `public help` |
| Anonymous | `guestWelcome()`, `isAnonymous()` | Cho phép, trả `welcome guest` |
| Anonymous | `dashboard()`, `isAuthenticated()` | `AccessDeniedException` |
| Anonymous | `adminPanel()`, `hasRole('ADMIN')` | `AccessDeniedException` |
| `member / ROLE_USER` | `dashboard()` | Cho phép |
| `member / ROLE_USER` | `guestWelcome()` | `AccessDeniedException` |
| `root / ROLE_ADMIN` | `adminPanel()` | Cho phép |

**Vì sao test có ý nghĩa:** `@WithMockUser` đặt ở cấp class làm mặc định cho những ca người đã đăng nhập. Chỉ các test được gắn `@WithAnonymousUser` chuyển hẳn sang anonymous. Cùng một bean chịu sự kiểm soát của `@PreAuthorize` cho thấy sự khác biệt giữa "công khai cho mọi người", "chỉ cho guest" và "cần quyền sau đăng nhập".

**Một giới hạn cần nhớ:** Test dùng class-level `@WithMockUser` xác minh phân quyền sau khi danh tính đã tồn tại; nó không kiểm password, đăng nhập, nguồn dữ liệu người dùng hay token thật. `@WithAnonymousUser` cũng không yêu cầu browser, session hay HTTP header; giá trị ở đây nằm ở method authorization.

## 5. Đọc đúng các biểu thức khi chưa đăng nhập

| Biểu thức trên method | Anonymous được phép? | User đã đăng nhập được phép? | Khi nào dùng |
| --- | --- | --- | --- |
| `@PreAuthorize("permitAll()")` | Có | Có | Tài nguyên dùng chung, không cần danh tính |
| `@PreAuthorize("isAnonymous()")` | Có | Không | Hành vi chỉ nên hiển thị/hoạt động trước khi đăng nhập |
| `@PreAuthorize("isAuthenticated()")` | Không | Có, khi được Spring Security nhận là đã xác thực | Hồ sơ cá nhân, dashboard |
| `@PreAuthorize("hasRole('ADMIN')")` | Không theo cấu hình role mặc định | Chỉ khi có `ROLE_ADMIN` | Quản trị |
| `@PreAuthorize("denyAll()")` | Không | Không | Chặn hoàn toàn một hành vi |

**Phân biệt `permitAll()` và `isAnonymous()`:** `permitAll()` cho cả khách và người đã đăng nhập; `isAnonymous()` chỉ cho khách. Chẳng hạn "đọc FAQ" có thể `permitAll()`, còn "hiển thị gợi ý đăng ký dành cho khách" có thể `isAnonymous()` nếu nghiệp vụ thật sự muốn chặn người đã đăng nhập.

**Không nhầm role/authority:** `hasRole("ADMIN")` thường kiểm quyền có tên `ROLE_ADMIN`. `@WithMockUser(roles="ADMIN")` tạo quyền tương ứng. `ROLE_ANONYMOUS` của anonymous token **không phải** `ROLE_USER` hay `ROLE_ADMIN`.

**Không tự suy kết luận từ `Authentication.isAuthenticated()`:** Anonymous token có thể có cờ đó là `true`, nhưng `isAuthenticated()` trong expression phân quyền dùng cách phân loại của Spring Security để không coi anonymous là user đăng nhập.

## 6. Ngoại lệ trong method test và mã HTTP khác nhau

Khi test gọi trực tiếp `service.dashboard()` qua Spring AOP proxy, `@PreAuthorize` được đánh giá trước thân method. Nếu anonymous không đạt điều kiện, Spring Security thường ném `AccessDeniedException` (hoặc subclass). Tại đây **không có HTTP response** nên không thể assert 401/403 bằng việc chỉ gọi method Java.

Khi cùng method được gọi phía sau một HTTP endpoint, `ExceptionTranslationFilter` và cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` có thể chuyển kết quả thành 401, 403 hoặc redirect đến trang đăng nhập, tùy bối cảnh anonymous và kiểu authentication. Kiểm tra HTTP status cần viết **MockMvc hoặc integration test HTTP riêng**, gửi request không credential qua `SecurityFilterChain`.

Một nhầm lẫn hay gặp là khẳng định "anonymous gọi service luôn trả 403". Khi gọi method trực tiếp, cái thấy được là **exception Java**; status HTTP chỉ phát sinh khi chạy toàn bộ đường web và có handler chuyển đổi exception.

### Khi cần kiểm cả HTTP, bổ sung test khác

Ví dụ phác thảo **không phải chương trình độc lập** (chỉ áp dụng khi project đã có controller/chain/MockMvc tương ứng):

~~~java
// Kiểm thử việc một HTTP request không mang credential bị chặn.
// Expected status phụ thuộc cấu hình entry point / login của ứng dụng.
mockMvc.perform(get("/private"))
       .andExpect(status().isUnauthorized());
~~~

Assertion 401 trên phù hợp nếu endpoint thực sự dùng authentication entry point trả 401 (ví dụ nhiều cấu hình HTTP Basic/API). Với form login, 302 redirect đến login page có thể là kết quả đúng. Đừng chép nguyên status từ method test sang HTTP test.

## 7. Vì sao test có thể "pass" nhưng thực tế method không được bảo vệ?

### 7.1. Quên bật method security

Chỉ có `@PreAuthorize` trên method chưa đủ nếu không bật hỗ trợ method security, ví dụ:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
    // Các @PreAuthorize trên Spring bean được áp dụng.
}
~~~

Spring Boot starter security **không mặc định kích hoạt** phân quyền ở cấp method. Khi thiếu `@EnableMethodSecurity`, annotation có thể không chặn bất cứ lời gọi nào. Một bài test tốt phải có ca từ chối đối với anonymous và khẳng định `AccessDeniedException`; nếu protection bị tắt, ca đó sẽ fail.

### 7.2. Bỏ qua AOP proxy

Hai cách gọi khác nhau:

~~~java
// SAI cho mục tiêu kiểm @PreAuthorize:
ResourceService service = new ResourceService();
service.dashboard(); // Lời gọi trực tiếp, không qua Spring AOP proxy.

// ĐÚNG trong test đã @ContextConfiguration/@EnableMethodSecurity:
@Autowired
ResourceService service;
// service.dashboard() đi qua bean được Spring quản lý.
~~~

Spring method security hoạt động qua interceptor/proxy. Self-invocation (một method trong cùng object gọi method khác bằng `this.protectedMethod()`) cũng có thể bỏ qua lời gọi qua proxy. Đừng dùng trường hợp đó để kết luận `@WithAnonymousUser` không hoạt động.

### 7.3. Dùng @WithMockUser để giả anonymous

Đây **không** phải trường hợp anonymous:

~~~java
@Test
@WithMockUser(username = "anonymousUser")
void notReallyAnonymous() {
    // Đây là một UsernamePasswordAuthenticationToken của user giả,
    // không phải AnonymousAuthenticationToken.
}
~~~

Tên `anonymousUser` đơn thuần không quyết định trạng thái. Test như trên thường có `ROLE_USER` (mặc định của `@WithMockUser`), và `isAuthenticated()` sẽ đánh giá khác `@WithAnonymousUser`.

### 7.4. Không có annotation không luôn tương đương @WithAnonymousUser

Trong bài test không khởi tạo `Authentication`, `SecurityContext` có thể rỗng. Method security có thể ném `AuthenticationCredentialsNotFoundException` khi biểu thức cần principal; trong khi `@WithAnonymousUser` đặt sẵn anonymous token để các biểu thức như `isAnonymous()` được đánh giá theo trạng thái anonymous. Dùng annotation này khi muốn test có **ngữ nghĩa khách chưa đăng nhập** ổn định.

### 7.5. Cấu hình anonymous production khác mặc định

Ứng dụng có thể tùy chỉnh authority của anonymous hoặc tắt anonymous authentication trên filter chain. Test `@WithAnonymousUser` biểu diễn token theo mặc định của test, không tự đọc mọi customization của production. Nếu logic phụ thuộc tên authority đặc biệt, thêm test config/mapping tương ứng và ít nhất một test web thật khi cần bảo đảm cấu hình triển khai.

### 7.6. Đọc/cài context sai thời điểm hoặc rò rỉ giữa các test

`@WithAnonymousUser` được Spring TestContext gắn trước test và dọn sau test. Nếu tự chỉnh `SecurityContextHolder` trong `@BeforeEach`, `@AfterEach`, luồng mới hoặc code async, phải hiểu context có thể bị thay thế hay không truyền sang thread mới. Nếu cần annotation thiết lập sau `@BeforeEach`, xem `setupBefore = TestExecutionEvent.TEST_EXECUTION`. Đừng bật kế thừa ThreadLocal chỉ để làm một test pass.

## 8. Checklist thiết kế ca test anonymous ở tầng method

Với mỗi method được bảo vệ, xác định hành vi **public**, **guest-only**, **authenticated** hay **role-specific**. Bảng ca test tối thiểu sau giúp kiểm tra cả hai chiều:

| Nhóm test | User context | Khẳng định |
| --- | --- | --- |
| Guest có thể sử dụng chức năng công khai | `@WithAnonymousUser` | Gọi thành công và kiểm kết quả |
| Guest bị chặn khỏi dữ liệu riêng | `@WithAnonymousUser` | Ném `AccessDeniedException` |
| User đã login có thể dùng dữ liệu riêng | `@WithMockUser` hoặc `@WithUserDetails` | Gọi thành công |
| User đã login không thể dùng chức năng guest-only | `@WithMockUser` | Ném `AccessDeniedException` nếu `isAnonymous()` |
| User không đủ role bị chặn | `@WithMockUser(roles="USER")` | Ném `AccessDeniedException` đối với `hasRole('ADMIN')` |
| Admin được phép | `@WithMockUser(roles="ADMIN")` | Gọi thành công |
| Cơ chế không đăng nhập trên HTTP | MockMvc/Web integration, request không credential | Assert status/redirect theo entry point thực tế |

Các test nên assert **cả kết quả và quyền truy cập**, tránh chỉ kiểm rằng method "không ném lỗi" ở happy path. Khi method tạo side effect, xác minh nhánh bị từ chối **không thay đổi dữ liệu**.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Trong test có `@WithAnonymousUser`, `SecurityContextHolder.getContext().getAuthentication()` trả về đối tượng khác `null`. Có thể kết luận user đã đăng nhập không?

**Đáp án:** Không. Đây là `AnonymousAuthenticationToken`; `AuthenticationTrustResolver`/biểu thức phân quyền coi nó là anonymous.

**Câu 2.** Cả class có `@WithMockUser(roles="ADMIN")`. Vì sao test kiểm guest cần thêm `@WithAnonymousUser` ở method?

**Đáp án:** Để ghi đè bối cảnh admin được cấp bởi annotation ở class. Nếu không, test vẫn chạy như admin và không kiểm trường hợp chưa đăng nhập.

**Câu 3.** Một test gọi `service.secret()` dưới `@WithAnonymousUser` thấy `AccessDeniedException`. Có thể kết luận HTTP endpoint trả 403?

**Đáp án:** Chưa. Test đã xác nhận method authorization từ chối. Cần kiểm thử request qua web chain và entry point/exception translation mới biết status/redirect cụ thể.

**Câu 4.** `@WithMockUser(username="anonymousUser")` có tương đương `@WithAnonymousUser`?

**Đáp án:** Không. Tên giống nhau nhưng loại `Authentication` và ngữ nghĩa trust khác nhau.

## 10. Ghi nhớ

`@WithAnonymousUser` cho test một **anonymous principal có thể dự đoán**, rất phù hợp để chứng minh method cho phép khách truy cập phần công khai và từ chối truy cập phần cần đăng nhập. Kết hợp các ca **anonymous được phép**, **anonymous bị chặn**, **user hợp lệ được phép** và **user thiếu quyền bị chặn**; đồng thời luôn gọi **Spring-managed bean đã được proxy** và bật `@EnableMethodSecurity`. Khi muốn xác nhận request không login có HTTP status nào, hãy viết test web riêng.

### Tài liệu chính thức

- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — `@WithAnonymousUser` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithAnonymousUser.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Anonymous Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — `AuthenticationTrustResolver` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html