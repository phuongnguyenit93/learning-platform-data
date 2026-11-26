# Kiểm tra phương thức Reactive với `@WithMockUser` và authorities cần thiết

## 1. Vì sao cần kiểm thử bảo mật ở tầng phương thức?

Một API Spring WebFlux có thể được bảo vệ tại `SecurityWebFilterChain`, chẳng hạn yêu cầu người dùng đã đăng nhập mới truy cập được `GET /api/reports`. Tuy nhiên, nhiều quy tắc quan trọng được đặt **trực tiếp trên phương thức nghiệp vụ** bằng `@PreAuthorize`, `@PostAuthorize` hoặc các cơ chế method security khác. Quy tắc này vẫn cần được kiểm chứng nếu phương thức được gọi từ controller, job, sự kiện hoặc một luồng Reactor khác.

Ví dụ, phương thức sau chỉ cho phép người dùng có authority `SCOPE_reports.read`:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<String> readReport() {
    return Mono.just("confidential-report");
}
~~~

Trong module `SPRING_SECURITY_TESTING`, chúng ta cần kiểm chứng **xác thực, phân quyền và bảo vệ HTTP thực tế** trên Servlet và Reactive. Bài này tập trung vào **Reactive method security**: dùng `@WithMockUser` để cấp một authentication giả cho test, rồi xác nhận phương thức trả kết quả khi đủ quyền và phát lỗi khi thiếu quyền.

`@WithMockUser` là công cụ đúng khi mục tiêu là **quy tắc phân quyền sau khi đã có authentication**. Nó không tự xác minh mật khẩu thật, không kiểm tra chữ ký JWT, không chạy OAuth2/OIDC login và không tự chứng minh HTTP filter chain đã được cấu hình đúng. Những ranh giới đó cần các ca tích hợp riêng.

Sau bài này, người học sẽ biết:

1. Bật `@EnableReactiveMethodSecurity` và bảo đảm lời gọi đi qua Spring proxy.
2. Dùng `@WithMockUser(roles = ...)` và `@WithMockUser(authorities = ...)` với đúng authority mà biểu thức yêu cầu.
3. Dùng `StepVerifier` để kiểm tra `Mono` và `Flux` được phép hoặc bị từ chối.
4. Phân biệt authority `ROLE_ADMIN`, authority `SCOPE_reports.read` và claim JWT `scope`.
5. Truy cập authentication bằng `ReactiveSecurityContextHolder` trong Reactive pipeline.
6. Viết ca đối chứng thiếu quyền, thiếu authentication, và kiểm thử HTTP bằng `WebTestClient` khi cần.

## 2. Ba lớp bảo mật cần phân biệt

Một request đến ứng dụng WebFlux có thể đi qua ba lớp liên quan:

~~~mermaid
flowchart TD
    A["Yêu cầu HTTP / lời gọi service"] --> B{"Đi từ HTTP?"}
    B -- "Có" --> C["SecurityWebFilterChain"]
    B -- "Không" --> E["Spring proxy của service"]
    C --> D["Authentication và HTTP authorization"]
    D --> E
    E --> F["@PreAuthorize / Reactive method security"]
    F --> G{"Đủ GrantedAuthority?"}
    G -- "Có" --> H["Mono / Flux nghiệp vụ"]
    G -- "Không" --> I["AccessDeniedException"]
    J["@WithMockUser trong test"] -. "Thiết lập SecurityContext giả" .-> F
~~~

- **Authentication** xác định danh tính đang được coi là người gọi, ví dụ `learner`. Trong WebFlux, `SecurityContext` được mang theo Reactor Context.
- **Authorization** quyết định danh tính đó có được gọi phương thức hay không, dựa trên `GrantedAuthority` và biểu thức bảo mật.
- **HTTP security** có thể chặn request trước khi controller gọi service. Một unit/integration test trực tiếp service chưa chứng minh HTTP route, CSRF hoặc authentication entry point hoạt động.

`@WithMockUser` tham gia vào lớp authentication của test bằng cách tạo principal giả cùng authorities đã yêu cầu. Với Reactive test, Spring Security Test có cơ chế đưa security context của test vào Reactor Context để các phương thức được bảo vệ có thể đọc được nó.

| Đối tượng/API | Vai trò trong bài |
| --- | --- |
| `@EnableReactiveMethodSecurity` | Bật cơ chế kiểm tra authorization trên phương thức Reactive |
| `@PreAuthorize` | Kiểm tra quyền trước khi chạy logic được bảo vệ |
| `@PostAuthorize` | Kiểm tra quyền sau khi có kết quả theo tính năng được hỗ trợ |
| `@WithMockUser` | Gắn username/roles/authorities giả cho một test |
| `ReactiveSecurityContextHolder` | Truy cập `SecurityContext` trong Reactor Context |
| `StepVerifier` | Subscribe và khẳng định tín hiệu `onNext`, `onError`, `onComplete` |
| `AccessDeniedException` | Kiểu lỗi thường gặp khi authentication đã có nhưng thiếu quyền |
| `WebTestClient` | Kiểm tra endpoint HTTP/WebFlux nếu phương thức được gọi qua web |

## 3. Hiểu chính xác `roles` và `authorities` của `@WithMockUser`

Spring Security kiểm tra quyền dựa trên các giá trị `GrantedAuthority`. Hai cách thường dùng trong annotation:

~~~java
@WithMockUser(username = "learner", roles = "USER")
~~~

Thường tạo authority **`ROLE_USER`**.

~~~java
@WithMockUser(
    username = "learner",
    authorities = "SCOPE_reports.read")
~~~

Tạo đúng authority **`SCOPE_reports.read`**. Không có bước tự động lấy một access token để giải mã claim `scope` trong trường hợp này.

| Biểu thức method security | Authority phải có | Cách cấu hình test đúng |
| --- | --- | --- |
| `hasRole('USER')` | `ROLE_USER` | `@WithMockUser(roles = "USER")` |
| `hasRole('ADMIN')` | `ROLE_ADMIN` | `@WithMockUser(roles = "ADMIN")` |
| `hasAuthority('ROLE_ADMIN')` | `ROLE_ADMIN` | `@WithMockUser(authorities = "ROLE_ADMIN")` |
| `hasAuthority('SCOPE_reports.read')` | `SCOPE_reports.read` | `@WithMockUser(authorities = "SCOPE_reports.read")` |
| `hasAuthority('REPORT_EXPORT')` | `REPORT_EXPORT` | `@WithMockUser(authorities = "REPORT_EXPORT")` |
| `hasRole('ADMIN') and hasAuthority('SCOPE_reports.write')` | Cả `ROLE_ADMIN` và `SCOPE_reports.write` | `@WithMockUser(authorities = {"ROLE_ADMIN", "SCOPE_reports.write"})` |

**Không viết `roles = "ROLE_ADMIN"`** rồi mặc định hệ thống sẽ xử lý như `ADMIN`. Trong mặc định của Spring Security Test, tham số `roles` nhận tên vai trò **chưa có** tiền tố `ROLE_` và tự thêm tiền tố này. Với `authorities`, phải cung cấp **chính xác chuỗi** dùng trong `hasAuthority(...)`.

### 3.1. Giá trị mặc định dễ làm test xanh ngoài dự kiến

`@WithMockUser` không tham số tạo một mock principal có username `user` và vai trò `USER` theo mặc định. Vì thế:

~~~java
@Test
@WithMockUser
void test() {
    // Principal mặc định có authority ROLE_USER.
}
~~~

Nếu mục tiêu là kiểm tra người **không có quyền**, đừng để annotation mặc định vô tình cấp đúng `ROLE_USER`. Hãy đặt rõ `authorities` hoặc `roles` cho từng test và luôn có ít nhất một ca bị từ chối.

### 3.2. `roles` và `authorities` không cộng dồn như nhiều người tưởng

Khi test cần đồng thời một role và một scope, hãy liệt kê cả hai giá trị trong `authorities`:

~~~java
@WithMockUser(
    username = "manager",
    authorities = {"ROLE_ADMIN", "SCOPE_reports.write"})
~~~

Tránh trông đợi cấu hình `roles` và `authorities` trên cùng annotation sẽ tự kết hợp thành danh sách mong muốn. Cách rõ ràng nhất là biểu diễn **danh sách `GrantedAuthority` cuối cùng** bằng `authorities` rồi assert cả nhánh đủ và thiếu từng quyền.

## 4. Thiết lập một service Reactive có method security

Ví dụ xuyên suốt dùng ba phương thức:

- `readReport()` chỉ dành cho `SCOPE_reports.read`.
- `auditEvents()` chỉ dành cho `ROLE_ADMIN`.
- `publishReport()` cần **cả** `ROLE_ADMIN` lẫn `SCOPE_reports.write`.

### 4.1. Bật bảo mật phương thức

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;

@Configuration(proxyBeanMethods = false)
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {

    @Bean
    ProtectedReportService protectedReportService() {
        return new ProtectedReportService();
    }
}
~~~

`@EnableReactiveMethodSecurity` đăng ký hạ tầng bảo mật phương thức và proxy phù hợp cho bean Spring được bảo vệ. Trong ứng dụng thực, service có thể được đăng ký bằng `@Service`; ví dụ dùng `@Bean` tường minh để tài liệu tự chứa, không phụ thuộc component scanning.

Không cần bật một HTTP server chỉ để kiểm tra `@PreAuthorize` trên service. Vì vậy, test trực tiếp bean Spring với `@SpringJUnitConfig` sẽ nhanh và tập trung hơn `@SpringBootTest` toàn ứng dụng khi mục tiêu chỉ là method security.

### 4.2. Service cần bảo vệ

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ProtectedReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<String> readReport() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .map(Authentication::getName)
                .map(username -> "report-for-" + username);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Flux<String> auditEvents() {
        return Flux.just("created", "reviewed", "exported");
    }

    @PreAuthorize(
        "hasRole('ADMIN') and hasAuthority('SCOPE_reports.write')")
    public Mono<String> publishReport() {
        return Mono.just("published");
    }
}
~~~

Ở đây, `readReport()` đọc authentication từ `ReactiveSecurityContextHolder` bên trong pipeline. Vì vậy test vừa kiểm tra điều kiện quyền, vừa nhìn thấy username của mock principal đúng với giá trị được cấp.

Phương thức `auditEvents()` trả `Flux` nhiều phần tử; `publishReport()` trả `Mono` một phần tử. `@PreAuthorize` được áp dụng bởi proxy của Spring, trước khi logic publisher được phép phát dữ liệu cho người gọi.

**Lưu ý về tính bất đồng bộ:** đối với Reactive method security, nên dùng đúng các kiểu trả về được Spring Security hỗ trợ như `Mono` hoặc `Flux`. Đừng gọi `block()` trong service để biến pipeline thành lời gọi đồng bộ chỉ nhằm giúp test dễ viết; làm vậy có thể ảnh hưởng việc truyền Reactor Context.

## 5. Cấu hình test: `@SpringJUnitConfig` + `@WithMockUser` + `StepVerifier`

Cho test method security của Spring bean, một cấu hình gọn:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

`reactor-test` cung cấp `StepVerifier`, dùng để thực sự **subscribe** một `Mono`/`Flux` và kiểm tra tín hiệu. Chỉ gọi phương thức rồi kiểm tra publisher khác `null` không đủ để chứng minh phép kiểm tra quyền đã được kích hoạt trong chuỗi Reactive.

Ví dụ test trực tiếp service:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = ReactiveMethodSecurityConfiguration.class)
class ProtectedReportServiceTests {

    @Autowired
    ProtectedReportService reports;

    @Test
    @WithMockUser(
        username = "learner",
        authorities = "SCOPE_reports.read")
    void requiredScopeCanReadReport() {
        StepVerifier.create(reports.readReport())
                .expectNext("report-for-learner")
                .verifyComplete();
    }

    @Test
    @WithMockUser(
        username = "learner",
        authorities = "SCOPE_profile")
    void missingScopeCannotReadReport() {
        StepVerifier.create(reports.readReport())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadAuditEvents() {
        StepVerifier.create(reports.auditEvents())
                .expectNext("created", "reviewed", "exported")
                .verifyComplete();
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void normalUserCannotReadAuditEvents() {
        StepVerifier.create(reports.auditEvents())
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
~~~

Đoạn này là ví dụ test dùng **Spring bean thực** (được proxy) chứ không dùng `new ProtectedReportService()`. `@SpringJUnitConfig` kích hoạt Spring TestContext cùng JUnit Jupiter; `@WithMockUser` phối hợp với Spring Security Test listeners để thiết lập authentication giả cho test và Reactor Context.

### 5.1. Cách đọc từng assertion

| Test | Authorities được cấp | Biểu thức yêu cầu | Kỳ vọng |
| --- | --- | --- | --- |
| `requiredScopeCanReadReport` | `SCOPE_reports.read` | `hasAuthority('SCOPE_reports.read')` | `onNext("report-for-learner")` rồi `onComplete` |
| `missingScopeCannotReadReport` | `SCOPE_profile` | `hasAuthority('SCOPE_reports.read')` | `onError(AccessDeniedException)` |
| `adminCanReadAuditEvents` | `ROLE_ADMIN` | `hasRole('ADMIN')` | Ba sự kiện rồi `onComplete` |
| `normalUserCannotReadAuditEvents` | `ROLE_USER` | `hasRole('ADMIN')` | `onError(AccessDeniedException)` |

`StepVerifier.create(...)` tạo một subscriber cho publisher cần kiểm tra. `expectNext(...)` chứng minh giá trị đi ra trong luồng; `verifyComplete()` chứng minh luồng kết thúc thành công. `expectError(AccessDeniedException.class)` chứng minh có tín hiệu lỗi bảo mật (hoặc lớp con phù hợp) thay vì phát dữ liệu được bảo vệ.

Trong nhiều cấu hình Reactive method security hiện đại, người dùng **đã xác thực nhưng thiếu quyền** bị từ chối bằng `AccessDeniedException` hoặc kiểu con của nó. Trường hợp **không có authentication nào** có thể được xử lý khác tùy phiên bản và cấu hình; hãy kiểm tra policy cùng loại lỗi thực tế thay vì tự áp một loại lỗi cho mọi ngữ cảnh chưa đăng nhập.

## 6. Kiểm tra quy tắc yêu cầu nhiều authorities

Biểu thức:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') and hasAuthority('SCOPE_reports.write')")
public Mono<String> publishReport() {
    return Mono.just("published");
}
~~~

cần **đồng thời** `ROLE_ADMIN` và `SCOPE_reports.write`. Test nên có cả ca đủ hai quyền và các ca thiếu từng quyền:

~~~java
@Test
@WithMockUser(
    username = "manager",
    authorities = {"ROLE_ADMIN", "SCOPE_reports.write"})
void managerWithBothAuthoritiesCanPublish() {
    StepVerifier.create(reports.publishReport())
            .expectNext("published")
            .verifyComplete();
}

@Test
@WithMockUser(
    username = "manager",
    authorities = "ROLE_ADMIN")
void adminWithoutWriteScopeCannotPublish() {
    StepVerifier.create(reports.publishReport())
            .expectError(AccessDeniedException.class)
            .verify();
}

@Test
@WithMockUser(
    username = "editor",
    authorities = "SCOPE_reports.write")
void writerWithoutAdminRoleCannotPublish() {
    StepVerifier.create(reports.publishReport())
            .expectError(AccessDeniedException.class)
            .verify();
}
~~~

Ví dụ khẳng định cả hai vế của phép `and` đều có tác dụng. Nếu chỉ test “đủ cả hai quyền thì chạy được”, một lỗi khiến một nhánh `hasRole` hoặc `hasAuthority` bị loại khỏi biểu thức có thể không được phát hiện.

### 6.1. Không nhầm claim JWT với authority

Trong một OAuth2 Resource Server, JWT chứa `scope: "reports.write"` thường được converter mặc định chuyển thành authority `SCOPE_reports.write`. Nhưng `@WithMockUser(authorities = "SCOPE_reports.write")` đã **cung cấp thẳng authority**; nó không tạo JWT có claim và không chạy `ReactiveJwtDecoder` hoặc converter.

Khi muốn kiểm tra riêng phép ánh xạ scope thành authority, dùng test converter với một `Jwt` phù hợp hoặc chạy Bearer token thật qua resource server. Khi chỉ muốn kiểm tra rule `@PreAuthorize`, cung cấp authority trực tiếp qua `@WithMockUser` là đủ và nhanh hơn.

## 7. Vì sao có test không kiểm tra được `@PreAuthorize`?

Một số lỗi thiết lập thường gặp:

1. **Quên `@EnableReactiveMethodSecurity`.** Annotation trên service vẫn tồn tại nhưng interceptor bảo mật phương thức có thể không được đăng ký.
2. **Tạo service bằng `new` hoặc Mockito thay cho Spring bean.** Lời gọi không đi qua proxy, nên method security không được áp dụng.
3. **Gọi phương thức nội bộ trong cùng instance.** Với proxy-based method security, self-invocation có thể đi thẳng tới method thay vì qua proxy.
4. **Chỉ kiểm tra publisher khác `null`.** Quy tắc Reactive được thực thi qua publisher/subscription, cần `StepVerifier` hoặc subscriber thật.
5. **Mock nhầm service đang được bảo vệ.** Nếu `@MockBean` hoặc Mockito thay thế toàn bộ bean có `@PreAuthorize`, test có thể chỉ đang gọi mock.
6. **Bảo mật HTTP chặn sớm hơn.** Nếu endpoint test bị `SecurityWebFilterChain` từ chối trước, bạn chưa chứng minh phương thức đã chạy đến interceptor.

### 7.1. Một ca đối chứng để xác minh proxy được áp dụng

Khi `ProtectedReportService` được Spring quản lý và method security bật, principal thiếu scope phải bị từ chối:

~~~java
@Test
@WithMockUser(authorities = "SCOPE_profile")
void protectedBeanMustRejectWrongAuthority() {
    StepVerifier.create(reports.readReport())
            .expectError(AccessDeniedException.class)
            .verify();
}
~~~

Nếu test này đột ngột trả `report-for-user`, cần kiểm tra bean có đi qua security proxy không, annotation đã được kích hoạt chưa, biểu thức có bị thay đổi không, và request có đang gọi đúng method. Đây là ca đối chứng quan trọng: một test chỉ có quyền đúng nhận dữ liệu có thể xanh ngay cả khi method security bị tắt hoàn toàn.

### 7.2. Self-invocation trong cùng bean

Ví dụ dễ gặp:

~~~java
public Mono<String> publicEntry() {
    // Gọi trong cùng instance có thể không đi qua proxy.
    return readReport();
}

@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<String> readReport() {
    return Mono.just("report");
}
~~~

Nếu gọi `publicEntry()` từ ngoài, việc `this.readReport()` bên trong không nhất thiết đi qua interceptor proxy của `readReport()`. Hãy đặt ranh giới method security ở phương thức được gọi qua bean proxy, hoặc tách phần nghiệp vụ cần bảo vệ sang một Spring bean khác được inject. Sau đó kiểm thử cả entry point thực sự được ứng dụng sử dụng.

## 8. Kiểm chứng Reactor Context trong service

Reactive method security không chỉ xem “roles” như một mảng tĩnh. Authentication được đặt trong `SecurityContext` của Reactor Context, và logic downstream có thể truy cập nó:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Khi `@WithMockUser(username = "learner")` thiết lập context đúng cách, `StepVerifier` có thể nhìn thấy username bên trong publisher.

Nếu muốn kiểm thử **không phụ thuộc annotation**, bạn có thể chủ động đặt authentication vào Reactor Context:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

@Test
void explicitAuthenticationInReactorContextWorks() {
    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    "direct-user",
                    "N/A",
                    List.of(new SimpleGrantedAuthority(
                            "SCOPE_reports.read")));

    StepVerifier.create(
            reports.readReport()
                    .contextWrite(ReactiveSecurityContextHolder
                            .withAuthentication(authentication)))
            .expectNext("report-for-direct-user")
            .verifyComplete();
}
~~~

Đây là lựa chọn hữu ích khi một test cần kiểm tra nhiều danh tính trong các publisher độc lập, hoặc khi không muốn dùng annotation `@WithMockUser` ở toàn phương thức test.

**Giới hạn:** constructor `UsernamePasswordAuthenticationToken` ba tham số đánh dấu authentication đã được thiết lập; nó không xác minh mật khẩu. Test này xác nhận **Reactor Context và authorization của service**, không xác nhận login.

### 8.1. Đừng dựa vào ThreadLocal của Servlet

Trong WebFlux, thay đổi scheduler hoặc composition của `Mono`/`Flux` có thể khiến chuỗi chạy trên thread khác. `ReactiveSecurityContextHolder` hoạt động theo Reactor Context, nên không nên lấy `SecurityContextHolder.getContext()` ở thread JUnit sau `verifyComplete()` rồi suy ra danh tính đã dùng trong phương thức Reactive.

Nếu ứng dụng chuyển sang một thư viện ngoài Reactor, tự gọi `subscribe()` tách biệt hoặc xử lý trên thread pool riêng, cần kiểm tra cơ chế propagation context phù hợp. Một test `@WithMockUser` đơn giản không chứng minh mọi boundary bất đồng bộ của ứng dụng đều giữ đúng identity.

## 9. Kiểm thử method security có tham số nghiệp vụ

Quyền truy cập có thể phụ thuộc cả authority lẫn đối tượng được yêu cầu. Ví dụ, một người chỉ được xem báo cáo của chính mình:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.read') and #owner == authentication.name")
public Mono<String> readOwnedReport(@P("owner") String owner) {
    return Mono.just("owned-report-" + owner);
}
~~~

Ở đây `@P` của `org.springframework.security.access.method.P` cung cấp tên tham số cho biểu thức method security. Trong dự án có compiler option `-parameters`, Spring cũng có thể đọc tên tham số trực tiếp; dùng `@P("owner")` giúp minh họa ràng buộc một cách rõ ràng.

Hai ca kiểm thử:

~~~java
@Test
@WithMockUser(
    username = "alice",
    authorities = "SCOPE_reports.read")
void ownerCanReadOwnReport() {
    StepVerifier.create(reports.readOwnedReport("alice"))
            .expectNext("owned-report-alice")
            .verifyComplete();
}

@Test
@WithMockUser(
    username = "alice",
    authorities = "SCOPE_reports.read")
void ownerCannotReadAnotherPersonsReport() {
    StepVerifier.create(reports.readOwnedReport("bob"))
            .expectError(AccessDeniedException.class)
            .verify();
}
~~~

Khi đưa đoạn ví dụ vào `ProtectedReportService`, nhớ thêm import `@P` và giữ public method được gọi qua Spring bean proxy. Đây là test về **quy tắc sở hữu** dựa trên username giả. Trong hệ thống thực có multi-tenant hoặc dữ liệu nhạy cảm, nên dùng ID danh tính ổn định và authorization logic phù hợp, thay vì dựa tùy tiện vào tên hiển thị.

### 9.1. Method security không thay thế kiểm tra dữ liệu

Một test `@PreAuthorize` xanh chỉ chứng minh policy được thỏa trong tình huống kiểm tra. Nó không tự chứng minh query database đã giới hạn tenant, tài nguyên thực thuộc về người dùng hay endpoint không có đường đi khác bỏ qua service. Vì vậy, các policy kiểm soát dữ liệu nên có integration tests cho các đường gọi thực của ứng dụng.

## 10. Từ method test sang HTTP test bằng `WebTestClient`

Test trực tiếp service xác nhận interceptor `@PreAuthorize`, nhưng không xác nhận HTTP filter, router hay endpoint mapping. Khi cần kiểm tra thêm đường đi HTTP của ứng dụng WebFlux, tạo một controller gọi service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReportController {
    private final ProtectedReportService reports;

    ReportController(ProtectedReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/api/reports/me")
    Mono<String> readMine() {
        return reports.readReport();
    }
}
~~~

Cấu hình WebFlux security yêu cầu người dùng đã đăng nhập:

~~~java
@Bean
SecurityWebFilterChain httpSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/reports/me").authenticated()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Nếu chỉ cần test policy với mock principal, gắn `WebTestClient` vào WebFlux application context, bảo đảm `springSecurity()` được áp dụng:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();

client.mutateWith(mockUser("alice")
            .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports.read")))
      .get()
      .uri("/api/reports/me")
      .exchange()
      .expectStatus().isOk()
      .expectBody(String.class).isEqualTo("report-for-alice");

client.mutateWith(mockUser("alice").roles("USER"))
      .get()
      .uri("/api/reports/me")
      .exchange()
      .expectStatus().isForbidden();
~~~

Trong ứng dụng Spring Boot WebFlux, có thể dùng `@SpringBootTest(webEnvironment = MOCK)` với context đầy đủ; để sử dụng các mutators của `spring-security-test`, kiểm tra cách client được bind như trên. Khi test context chỉ có một vài bean, phải import cả `ReportController`, service proxy, `@EnableReactiveMethodSecurity` và web security chain cần thiết. **HTTP authorization và method authorization là hai lớp độc lập**, nên test phải đi qua cả hai nếu muốn kết luận endpoint được bảo vệ đúng.

### 10.1. Phân biệt lỗi từ HTTP layer và method layer

| Request | Web security | Method security | Kết quả thường gặp |
| --- | --- | --- | --- |
| Không có authentication | `authenticated()` không thỏa | Chưa chạy | `401` nếu dùng HTTP Basic |
| Mock USER thiếu scope | Đã xác thực, được qua web filter | `@PreAuthorize` từ chối | `403` |
| Mock USER có scope | Đã xác thực | `@PreAuthorize` chấp nhận | `200` |
| Method security tắt | Đã xác thực | Không kiểm tra scope | Có nguy cơ `200` sai mong đợi |

Ở test trực tiếp service, thiếu quyền thường xuất hiện dưới dạng `AccessDeniedException` trong `Mono`/`Flux`. Khi gọi qua HTTP, Spring Security thường chuyển trường hợp đã authenticated nhưng thiếu quyền thành **403 Forbidden**. Mã HTTP có thể khác theo custom exception handling và authentication entry point của ứng dụng.

**Lưu ý khi dùng test HTTP mock:** `mockUser()` cũng bỏ qua kiểm tra password thật. Để khẳng định luồng login/HTTP Basic hoạt động, cần gửi credentials qua authentication mechanism; để kiểm tra JWT thật, phải gửi Bearer token qua `ReactiveJwtDecoder`.

## 11. `@WithMockUser` và JWT/OAuth2/OIDC: ranh giới kiểm thử

`@WithMockUser` thông thường tạo principal kiểu username/password test với authorities đã chỉ định. Nó không tạo một `JwtAuthenticationToken` có claims và không tạo `OidcUser`. Hãy chọn test support phù hợp khi code phụ thuộc **kiểu principal**:

| Mục tiêu | Công cụ phù hợp | Điều không tự được kiểm tra |
| --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | `@WithMockUser(roles = "ADMIN")` | Password, HTTP login |
| `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` | `@WithMockUser(authorities = "SCOPE_reports.read")` | JWT signature, scope converter |
| Service dùng `JwtAuthenticationToken`/JWT claims | Test có authentication JWT giả hoặc `mockJwt()` trong WebFlux HTTP test | Decoder và token signature |
| Service dùng `OidcUser`/ID token claims | `mockOidcLogin()` hoặc custom `SecurityContext` trong đúng ngữ cảnh | OIDC code flow và xác minh ID token |
| Cần kiểm tra OAuth2 login thực | Integration test authorization server/IdP | Không thể suy ra từ mock principal |
| Cần kiểm tra tài nguyên qua HTTP | `WebTestClient` với security chain | Nếu vẫn dùng mock principal thì không kiểm tra cơ chế đăng nhập |

Ví dụ, một phương thức service sử dụng `((JwtAuthenticationToken) authentication).getToken()` không nên test chỉ bằng `@WithMockUser` vì loại authentication không đúng và có thể gây `ClassCastException`. Khi thật sự cần kiểm tra các claims, hãy dựng đúng principal/authentication tương ứng, và thêm ca tích hợp decoder nếu mục tiêu bao gồm tính hợp lệ của token.

### 11.1. Không nhầm `authorities` với chính sách cấp quyền bên ngoài

Một `@WithMockUser(authorities = "ROLE_ADMIN")` có thể được phép gọi phương thức admin bất kể database role mapping, JWT converter hay LDAP group mapping ngoài thực tế có hoạt động hay không. Test này chứng minh **policy xử lý authority đã được cấp**; để chứng minh authorities được tạo đúng từ dữ liệu thực, cần test mapping/provider/converter ở một mức tích hợp khác.

## 12. Các sai sót thường gặp và cách nhận diện

| Sai sót | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `@WithMockUser(roles = "SCOPE_reports.read")` | Spring Security Test tạo `ROLE_SCOPE_reports.read`, không khớp `SCOPE_reports.read` | Dùng `authorities = "SCOPE_reports.read"` |
| Dùng `@WithMockUser(authorities = "ADMIN")` với `hasRole('ADMIN')` | Thiếu `ROLE_ADMIN` | Dùng `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"` |
| Chỉ có test đủ quyền | Method security bị tắt vẫn có thể test xanh | Thêm ca thiếu quyền phải phát `AccessDeniedException` |
| Tạo service bằng `new` | Không có Spring proxy để chặn method | Inject bean trong Spring test context |
| Method được gọi nội bộ trong cùng bean | Có thể bỏ qua proxy | Đưa phương thức bảo vệ ra ranh giới bean/proxy phù hợp |
| Không subscribe `Mono`/`Flux` | Authorization/lỗi Reactive có thể chưa được quan sát | Dùng `StepVerifier` và `verify...` |
| Đặt `@WithMockUser` nhưng gọi server HTTP thật | Principal của test không tự truyền qua network | Gửi credentials/cookie/Bearer thực qua HTTP |
| Dùng `SecurityContextHolder` ở thread JUnit để đọc identity Reactive | Dữ liệu không phản ánh Reactor Context | Dùng `ReactiveSecurityContextHolder` trong publisher |
| Dùng `@WithMockUser` để xác nhận JWT hết hạn bị từ chối | Không có JWT decoder/validator | Gửi token thật qua resource server |
| Bắt mọi lỗi là `AccessDeniedException` | Không có authentication có thể phát lỗi khác | Phân biệt ca thiếu quyền với ca thiếu authentication |
| Test `@PreAuthorize` qua web nhưng bị chặn trước bởi CSRF | Method chưa chắc đã được gọi | Dùng GET phù hợp hoặc cung cấp CSRF hợp lệ, kiểm tra hai lớp |
| Thay toàn bộ service bằng Mockito mock | Không kiểm tra annotation trên service thật | Test bean proxy, mock dependency phía dưới khi cần |
| Đặt authorities không phản ánh chính sách | Test dễ xanh với quyền cấp quá rộng | Gắn đúng từng authority cần thiết và có ca thiếu từng quyền |

## 13. Ma trận kiểm thử gợi ý

Một bộ kiểm thử method security dễ bảo trì nên phân chia các trường hợp theo điều kiện thật sự quan trọng:

| Phương thức | Danh tính test | Quyền | Kỳ vọng |
| --- | --- | --- | --- |
| `readReport()` | `learner` | `SCOPE_reports.read` | Trả `report-for-learner` |
| `readReport()` | `learner` | `SCOPE_profile` | `AccessDeniedException` |
| `auditEvents()` | `admin` | `ROLE_ADMIN` | Trả 3 phần tử Flux |
| `auditEvents()` | `learner` | `ROLE_USER` | `AccessDeniedException` |
| `publishReport()` | `manager` | `ROLE_ADMIN` + `SCOPE_reports.write` | `published` |
| `publishReport()` | `manager` | Chỉ `ROLE_ADMIN` | `AccessDeniedException` |
| `publishReport()` | `editor` | Chỉ `SCOPE_reports.write` | `AccessDeniedException` |
| `readOwnedReport("alice")` | `alice` | `SCOPE_reports.read` | Thành công |
| `readOwnedReport("bob")` | `alice` | `SCOPE_reports.read` | Bị từ chối |
| `GET /api/reports/me` | Mock principal có scope | `SCOPE_reports.read` | HTTP `200` |
| `GET /api/reports/me` | Mock principal thiếu scope | `ROLE_USER` | HTTP `403` |
| `GET /api/reports/me` | Guest, HTTP Basic entry point | Không có | HTTP `401` |

Đối với hệ thống dùng nhiều authority custom, có thể viết parameterized tests để giảm trùng lặp, nhưng cần giữ lại đủ ca minh họa cụ thể cho từng nhánh policy. Không viết test chỉ lặp lại một danh sách quyền mà không thử hành vi bị từ chối.

## 14. Bài tập thực hành

### Bài 1: Vai trò không phải scope

Viết một phương thức `@PreAuthorize("hasAuthority('SCOPE_orders.read')")` trả `Mono<String>`. Dùng `@WithMockUser(roles = "USER")` để xác nhận phương thức bị từ chối, rồi dùng `@WithMockUser(authorities = "SCOPE_orders.read")` để xác nhận phương thức cho phép. Giải thích vì sao `ROLE_USER` không tương đương `SCOPE_orders.read`.

### Bài 2: Hai authorities bắt buộc

Tạo method có biểu thức `hasRole('ADMIN') and hasAuthority('SCOPE_orders.write')`. Viết ba test với `StepVerifier`: đủ cả hai quyền, chỉ role, chỉ scope. Ca đủ quyền phải thành công; hai ca còn lại phải phát `AccessDeniedException`.

### Bài 3: Sở hữu tài nguyên

Sử dụng `@PreAuthorize("#owner == authentication.name")` trên một phương thức `Mono<String>` có tham số owner. Đặt username `alice` bằng `@WithMockUser`; xác nhận `owner="alice"` thành công và `owner="bob"` bị từ chối. Đảm bảo phương thức được gọi qua Spring bean proxy và Spring nhận diện được tên tham số.

### Bài 4: Chứng minh method security thật sự bật

Tạm bỏ `@EnableReactiveMethodSecurity` trong một nhánh thực hành cô lập và quan sát ca thiếu quyền có thể không còn bị từ chối. Khôi phục annotation và xác nhận ca âm hoạt động. Không để thay đổi này vào cấu hình ứng dụng sản xuất.

### Bài 5: Từ service test sang WebTestClient

Viết controller WebFlux gọi service có `@PreAuthorize`. Test bằng `WebTestClient` mock context với USER có scope, USER thiếu scope và guest. Xác nhận `200`/`403`/`401` theo demo dùng HTTP Basic; phân tích request nào bị từ chối ở web filter và request nào bị từ chối ở method interceptor.

### Bài 6: Phân biệt JWT giả và JWT thật

Dùng `@WithMockUser(authorities = "SCOPE_reports.read")` kiểm tra service. Sau đó viết integration test Resource Server gửi Bearer JWS còn hạn, hết hạn và ký sai khóa qua `ReactiveJwtDecoder` thật. Giải thích kết luận độc lập của mỗi nhóm test.

## 15. Tiêu chí hoàn thành bài học

Một bộ test Reactive method security có giá trị khi:

- Phương thức được gọi qua bean Spring đang có security proxy.
- `@EnableReactiveMethodSecurity` đã bật và kiểm thử âm chứng minh interceptor thật sự từ chối quyền không đủ.
- Mỗi test sử dụng `roles` hoặc `authorities` đúng với biểu thức `hasRole`/`hasAuthority`.
- `Mono`/`Flux` được subscribe bằng `StepVerifier`, với khẳng định rõ `onNext`, `onComplete` hoặc `onError`.
- Reactor Context được truyền đúng; không suy luận về Reactive identity từ ThreadLocal của test.
- Khi mục tiêu mở rộng sang HTTP, authentication provider, JWT/OIDC, đã có thêm integration tests chạy qua đúng thành phần thực.

`@WithMockUser` giúp kiểm chứng **phân quyền tại ranh giới phương thức** hiệu quả. Nó cung cấp một danh tính đã được xác thực giả định, nên luôn phải diễn giải kết quả đúng giới hạn: một test `@PreAuthorize` thành công không đồng nghĩa mật khẩu, chữ ký JWT hoặc OAuth2/OIDC flow đã được xác minh.

## 16. Tài liệu tham khảo

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize` và method authorization trong Reactive.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` và các test security context.
- [Spring Security — Reactive Method Security Testing](https://docs.spring.io/spring-security/reference/reactive/test/method.html): dùng `@WithMockUser` với publisher và `StepVerifier`.
- [Spring Security — Reactive Web Testing Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): tích hợp `WebTestClient` với `springSecurity()`.
- [Spring Security — Reactive Authentication Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): kiểm thử authentication giả trong WebFlux.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, các loại tín hiệu và test publisher.
