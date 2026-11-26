# Kiểm thử Servlet và Reactive dùng mô hình ngữ cảnh khác nhau

## Mục tiêu học tập

Spring Security bảo vệ cả ứng dụng Servlet/Spring MVC và Reactive/WebFlux, nhưng hai nền tảng không lưu và truyền thông tin xác thực theo cùng một cách. Nếu viết test theo thói quen của Servlet cho một luồng Reactive, bài kiểm thử có thể không nhìn thấy principal dù người dùng đã được thiết lập; ngược lại, dùng Reactor Context trong một ứng dụng MVC có thể làm ví dụ trở nên khó hiểu mà không mang lại lợi ích.

Sau bài học này, bạn có thể:

- Giải thích vai trò của `SecurityContextHolder` và `SecurityContext` trong Servlet.
- Giải thích vai trò của `ReactiveSecurityContextHolder` và Reactor Context trong WebFlux.
- Chọn đúng cách giả lập người dùng cho `MockMvc` và `WebTestClient`.
- Kiểm tra method security trong cả hai mô hình, kể cả khi service trả về `Mono` hoặc `Flux`.
- Nhận biết khác biệt về vòng đời, phạm vi request, thread và subscription để tránh rò rỉ ngữ cảnh giữa các test.
- Xử lý các tình huống `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC mock và các ca truy cập được phép hoặc bị từ chối.

Bài này thuộc module **SPRING_SECURITY_TESTING**, tập trung vào kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Điểm khác biệt quan trọng nhất: SecurityContext được truyền ở đâu?

Sau khi xác thực thành công, Spring Security tạo một đối tượng `Authentication` chứa principal, trạng thái xác thực và authorities. Đối tượng này được đặt trong `SecurityContext`. Code ứng dụng có thể đọc nó để biết người gọi là ai và có những quyền nào.

Khác biệt nằm ở cách framework đưa `SecurityContext` đến đoạn code đang xử lý:

- Với **Servlet**, cơ chế mặc định sử dụng `SecurityContextHolder` và chiến lược lưu trữ theo `ThreadLocal`. Filter chain thiết lập context khi xử lý request và dọn dẹp sau đó.
- Với **Reactive**, context được gắn vào **Reactor Context** của publisher/subscriber. Code truy cập qua `ReactiveSecurityContextHolder`; context đi theo chuỗi reactive ngay cả khi quá trình xử lý chuyển qua thread khác.

| Khía cạnh | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Cơ chế mang context | `SecurityContextHolder`, mặc định dựa trên `ThreadLocal`. | Reactor Context và `ReactiveSecurityContextHolder`. |
| Cách đọc authentication | Lấy trực tiếp từ holder trong luồng xử lý đồng bộ. | Lấy qua publisher, ví dụ `ReactiveSecurityContextHolder.getContext()`. |
| Đơn vị xử lý | Request và thread thực thi filter/controller; có thể có xử lý bất đồng bộ riêng. | Subscription và chuỗi `Mono`/`Flux`. |
| Test HTTP | `MockMvc`. | `WebTestClient`. |
| Giả lập user cho request | `user()`, `jwt()`, `httpBasic()`, `csrf()`. | `mockUser()`, `mockJwt()`, `mockOAuth2Login()`, `csrf()`. |
| Kiểm thử method security | Bean Spring + `@WithMockUser` hoặc thiết lập context. | Bean Spring trả reactive type + Reactor Context; có thể dùng listener để hỗ trợ `@WithMockUser`. |

Không nên đồng nhất hai holder. `SecurityContextHolder.getContext()` là cách truy cập quen thuộc của Servlet; trong code Reactive, việc đọc trực tiếp holder theo ThreadLocal không phải cách lấy context của subscription hiện tại.

### 1.1. Hai luồng xử lý

~~~mermaid
flowchart TD
    subgraph S["Servlet / Spring MVC"]
      S1["HTTP request"] --> S2["Security Filter Chain"]
      S2 --> S3["SecurityContextHolder"]
      S3 --> S4["Controller / Service"]
      S4 --> S5["Response"]
      S5 --> S6["Filter dọn context"]
    end
    subgraph R["Reactive / WebFlux"]
      R1["HTTP request"] --> R2["Security WebFilter Chain"]
      R2 --> R3["Reactor Context"]
      R3 --> R4["Mono / Flux handler"]
      R4 --> R5["Response publisher"]
    end
~~~

Sơ đồ mô tả cách truyền context ở mức khái niệm. Cách cấu hình cụ thể còn phụ thuộc filter chain, repository, loại authentication và phiên bản Spring Security.

## 2. Servlet: SecurityContextHolder gắn với luồng xử lý request

### 2.1. Cách ứng dụng đọc người dùng hiện tại

Trong ứng dụng Servlet, controller có thể nhận `Authentication` trực tiếp qua tham số, hoặc code imperative có thể đọc holder:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

String currentUsername() {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    return authentication.getName();
}
~~~

Cách nhận `Authentication` qua tham số controller thường dễ kiểm thử và làm rõ phụ thuộc hơn. Ví dụ:

~~~java
@GetMapping("/api/me")
String me(Authentication authentication) {
    return authentication.getName();
}
~~~

Spring Security thiết lập context trong quá trình xử lý request. Với cấu hình mặc định, context được giữ theo thread và filter security chịu trách nhiệm làm sạch sau request. Điều này ngăn danh tính của request trước vô tình được dùng cho request tiếp theo chạy trên cùng thread.

### 2.2. Giả lập người dùng trong MockMvc

Với Spring MVC, `MockMvc` cho phép gửi request qua cơ chế xử lý web của ứng dụng trong test context. Có hai cách phổ biến để đặt danh tính.

**Cách 1: gắn user vào từng request.**

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ServletRequestSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedUserCanReadProfile() throws Exception {
        mvc.perform(get("/api/me")
                .with(user("linh").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("linh"));
    }

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

`user("linh").roles("USER")` tạo một authentication giả lập cho request đang được kiểm tra. `roles("USER")` tạo authority `ROLE_USER`. Test này hữu ích để kiểm tra phân quyền và hành vi sau xác thực; nó không xác minh mật khẩu của `linh`.

**Cách 2: dùng @WithMockUser cho toàn bộ phương thức test.**

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
@AutoConfigureMockMvc
class ServletAnnotatedSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void adminCanReadAudit() throws Exception {
        mvc.perform(get("/api/admin/audit"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void regularUserCannotReadAudit() throws Exception {
        mvc.perform(get("/api/admin/audit"))
            .andExpect(status().isForbidden());
    }
}
~~~

`@WithMockUser` thiết lập `SecurityContext` cho thời gian chạy test thông qua test execution listener của Spring Security. Context được dọn dẹp sau test. Annotation thuận tiện khi nhiều request trong một phương thức dùng cùng danh tính; request post-processor `user()` linh hoạt hơn khi một test cần thử nhiều người dùng.

### 2.3. MockMvc phải được tích hợp với Spring Security

Khi dùng `@SpringBootTest` và `@AutoConfigureMockMvc` theo cấu hình thông thường, Spring Boot tích hợp filter của application context vào MockMvc.

Nếu tự tạo MockMvc, cần thêm configurer của Spring Security:

~~~java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

Nếu thiếu bước này, test có thể gọi controller mà không chạy chuỗi filter mà bạn muốn kiểm chứng. Một bài test nhận `200` trong tình huống đó không chứng minh URL authorization đã được áp dụng.

### 2.4. Kiểm thử method security trong Servlet

Method security bảo vệ bean ở thời điểm gọi phương thức, kể cả khi lời gọi không đến từ HTTP:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class AuditService {

    @PreAuthorize("hasRole('ADMIN')")
    String readAudit() {
        return "audit-data";
    }
}
~~~

Bật method security trong cấu hình:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Test phải gọi bean Spring được inject, để lời gọi đi qua proxy/interceptor:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest
class ServletMethodSecurityTest {

    @Autowired
    AuditService auditService;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAudit() {
        assertThat(auditService.readAudit()).isEqualTo("audit-data");
    }

    @Test
    @WithMockUser(roles = "USER")
    void regularUserIsDenied() {
        assertThatThrownBy(() -> auditService.readAudit())
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Đây là test phương thức, không phải test HTTP. Không có request matcher, CSRF hay status code. Nó tập trung chứng minh `@PreAuthorize` được áp dụng khi gọi service.

Nếu tự tạo `new AuditService()`, test có thể bỏ qua proxy và annotation không được thực thi. Ngoài ra, lời gọi nội bộ qua `this.readAudit()` trong cùng bean cũng có thể bỏ qua proxy theo cách gọi thông thường. Cần test đúng đường gọi mà ứng dụng thực sự sử dụng.

## 3. Reactive: SecurityContext đi theo Reactor Context

### 3.1. Vì sao ThreadLocal không phù hợp?

Trong WebFlux, một request có thể tiếp tục qua nhiều toán tử và chuyển thread do scheduler. Thread thực thi tại thời điểm đọc dữ liệu có thể khác thread đã nhận request ban đầu.

Nếu context chỉ nằm trong ThreadLocal, việc đổi thread có thể làm code không tìm thấy authentication hoặc đọc nhầm trạng thái. Spring Security Reactive sử dụng Reactor Context để context đi theo subscription thay vì phụ thuộc vào thread cụ thể.

Code Reactive truy cập người dùng hiện tại bằng publisher:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

Không gọi `SecurityContextHolder.getContext()` trong handler Reactive để lấy danh tính request. Cách đó đọc ThreadLocal, không phải Reactor Context của publisher hiện tại.

### 3.2. SecurityContext được đọc khi publisher được subscribe

Trong Reactive, một `Mono` thường mô tả công việc sẽ thực thi sau này. Tạo publisher không đồng nghĩa công việc đã chạy. Context cần có mặt trong subscription để các toán tử upstream truy cập được.

~~~java
Authentication authentication = UsernamePasswordAuthenticationToken
    .authenticated("linh", "n/a", List.of(
        new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> result = currentUsername()
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(authentication));
~~~

Ở đây `contextWrite(...)` thêm authentication vào Reactor Context của subscription. Khi subscriber kích hoạt `result`, `ReactiveSecurityContextHolder.getContext()` mới đọc được danh tính `linh`.

Không nên dùng `block()` chỉ để lấy authentication bên trong code WebFlux. Hãy giữ dữ liệu trong chuỗi `Mono`/`Flux` và kết hợp bằng các toán tử Reactive.

### 3.3. Giả lập user cho WebTestClient

Trong WebFlux, tiện ích `mockUser()` được dùng với `WebTestClient` thông qua `mutateWith(...)`. Ví dụ cấu hình web:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Handler đọc principal từ Reactor Context:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveProfileController {

    @GetMapping("/api/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.*;

@SpringBootTest
class ReactiveHttpSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void userCanReadOwnProfile() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("linh");
    }

    @Test
    void anonymousCannotReadOwnProfile() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Ví dụ giả định endpoint được bảo vệ bằng xác thực và ứng dụng dùng HTTP Basic làm entry point cho anonymous request. Với form login hoặc cấu hình entry point khác, mã phản hồi có thể là redirect hoặc một phản hồi khác theo hợp đồng ứng dụng.

`springSecurity()` gắn các thành phần bảo mật vào client mock server. Nếu tự dựng WebTestClient chỉ từ controller mà không đưa WebFilter chain vào, test không còn kiểm tra đầy đủ cấu hình bảo mật của ứng dụng.

### 3.4. JWT, OAuth2 và OIDC mock trong Reactive

Các tiện ích Reactive có cùng mục tiêu tạo authentication giả lập cho request:

~~~java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("scope", "orders.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Tùy loại ứng dụng, có thể dùng `mockOAuth2Login()`, `mockOidcLogin()` hoặc `mockOpaqueToken()`. Các tiện ích này thiết lập principal/authentication trong test context của WebFlux để kiểm tra xử lý phía sau.

Chúng không chứng minh chữ ký JWT được xác minh, introspection endpoint đã được gọi hay authorization code flow của OIDC chạy thành công. Muốn kiểm tra xác thực token thật, hãy gửi bearer token qua HTTP để `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector` thực sự xử lý.

## 4. Kiểm thử Reactive method security

### 4.1. Cấu hình method security

Trong WebFlux, bật `@EnableReactiveMethodSecurity`. Phương thức được bảo vệ nên trả về kiểu Reactive như `Mono` hoặc `Flux` để quyết định bảo mật được thực thi trong ngữ cảnh reactive:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveAuditService {

    @PreAuthorize("hasRole('ADMIN')")
    Mono<String> readAudit() {
        return Mono.just("audit-data");
    }
}
~~~

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

### 4.2. Thiết lập Reactor Context trực tiếp trong test

Đây là cách rõ ràng khi muốn kiểm thử một bean Reactive với authentication cụ thể:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

import java.util.List;

@SpringBootTest
class ReactiveMethodSecurityTest {

    @Autowired
    ReactiveAuditService auditService;

    @Test
    void adminCanReadAudit() {
        Authentication admin = UsernamePasswordAuthenticationToken
            .authenticated("mai", "n/a", List.of(
                new SimpleGrantedAuthority("ROLE_ADMIN")));

        StepVerifier.create(auditService.readAudit().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(admin)))
            .expectNext("audit-data")
            .verifyComplete();
    }

    @Test
    void regularUserIsDenied() {
        Authentication user = UsernamePasswordAuthenticationToken
            .authenticated("linh", "n/a", List.of(
                new SimpleGrantedAuthority("ROLE_USER")));

        StepVerifier.create(auditService.readAudit().contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(user)))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

`StepVerifier` subscribe vào publisher và xác minh kết quả. Nếu chỉ gọi `auditService.readAudit()` mà không subscribe, test chưa chắc đã kích hoạt việc thực thi và kiểm tra bảo mật.

### 4.3. Dùng @WithMockUser cho reactive method security

Có thể dùng `@WithMockUser` cho test method security Reactive nếu test context được nối với Reactor Context bằng `ReactorContextTestExecutionListener` của Spring Security Test.

Ví dụ cấu hình test listener:

~~~java
@TestExecutionListeners(
    listeners = ReactorContextTestExecutionListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
@SpringBootTest
class ReactiveAnnotatedMethodSecurityTest {

    @Autowired
    ReactiveAuditService auditService;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAudit() {
        StepVerifier.create(auditService.readAudit())
            .expectNext("audit-data")
            .verifyComplete();
    }
}
~~~

Cần import `ReactorContextTestExecutionListener` từ package `org.springframework.security.test.context.support`. Listener này giúp context do `@WithMockUser` thiết lập được cung cấp cho các publisher trong test. Nếu test không cấu hình listener, đừng mặc định rằng ThreadLocal context do annotation tạo ra tự động xuất hiện trong Reactor Context.

Với test HTTP Reactive, `mutateWith(mockUser(...))` thường dễ hiểu hơn vì nó gắn danh tính vào đúng request. Với test gọi trực tiếp service Reactive, `contextWrite(...)` hoặc listener là cách thiết lập ngữ cảnh cho subscription.

## 5. Vòng đời và phạm vi của SecurityContext trong test

Một trong những lỗi khó tìm là context của test trước ảnh hưởng test sau, hoặc context không còn khi code chạy bất đồng bộ. Cần hiểu rõ ai thiết lập, ai sử dụng và ai dọn dẹp.

| Vấn đề | Servlet | Reactive |
| --- | --- | --- |
| Nơi đặt context | Holder theo thread. | Reactor Context của subscription. |
| Phạm vi mock request | `.with(user(...))` gắn vào request cụ thể. | `.mutateWith(mockUser(...))` gắn vào request cụ thể. |
| Phạm vi annotation | `@WithMockUser` tạo context trong vòng đời phương thức test. | Có thể dùng `@WithMockUser` khi `ReactorContextTestExecutionListener` cung cấp context cho publisher. |
| Dọn dẹp | Security filter và test listener dọn context theo vòng đời tương ứng. | Context gắn với subscription; test listener xử lý context test theo cơ chế Reactive. |
| Chuyển thread | ThreadLocal không tự chia sẻ an toàn sang mọi thread khác. | Reactor Context đi theo chuỗi reactive qua scheduler khi publisher được compose đúng cách. |
| Truy cập | `SecurityContextHolder.getContext()`. | `ReactiveSecurityContextHolder.getContext()` trả về publisher. |

### 5.1. Không để danh tính rò rỉ giữa các request

Trong Servlet, nên ưu tiên post-processor theo request khi test nhiều danh tính trong cùng phương thức:

~~~java
mvc.perform(get("/api/me")
        .with(user("linh").roles("USER")))
    .andExpect(status().isOk());

mvc.perform(get("/api/me")
        .with(user("mai").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

Mỗi request có danh tính riêng. Không tự đặt context vào holder rồi quên xóa, vì các test có thể dùng chung thread hoặc cùng môi trường thực thi.

Trong Reactive, mỗi request có thể dùng một client đã mutate với configurer riêng. Context nằm trong subscription của request, không nên lưu một authentication dùng chung vào biến toàn cục hoặc singleton để tái sử dụng giữa người dùng.

### 5.2. Xử lý bất đồng bộ ở Servlet

Mặc định, `SecurityContextHolder` dùng ThreadLocal. Khi code tạo một task chạy ở executor hoặc thread khác, không nên giả định context của request tự được truyền sang đó.

Spring Security có các wrapper như `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextExecutor` để truyền context khi cần. Nếu ứng dụng dùng chúng, hãy kiểm thử rằng task nhận đúng danh tính và context được khôi phục/dọn dẹp sau khi chạy.

Một test chỉ gọi controller đồng bộ không chứng minh các background task, executor hoặc callback bất đồng bộ có context đúng. Hãy tạo test riêng cho đường thực thi đó nếu quyết định bảo mật phụ thuộc principal trong task.

### 5.3. Chuyển scheduler trong Reactive

Trong Reactor, context được gắn với subscription thay vì thread. Vì vậy, việc chuyển qua `publishOn(...)` hoặc `subscribeOn(...)` trong cùng chuỗi không tự làm mất Reactor Context như cách ThreadLocal có thể mất khi đổi thread.

Tuy nhiên, context chỉ có trong chuỗi được truyền context. Nếu tự tạo một subscription độc lập, gọi `subscribe()` bên trong service hoặc chuyển sang API imperative ngoài chuỗi, không thể mặc nhiên kỳ vọng context của request còn nguyên. Ưu tiên compose publisher và để framework quản lý subscription ở biên ứng dụng.

## 6. Kiểm thử token và principal theo đúng mô hình context

Các tiện ích trong `spring-security-test` khác nhau về cách dựng danh tính, nhưng đều cần đặt vào đúng mô hình của ứng dụng.

| Mục tiêu | Servlet / MockMvc | Reactive / WebTestClient |
| --- | --- | --- |
| User giả lập | `.with(user("linh"))` | `.mutateWith(mockUser("linh"))` |
| JWT giả lập | `.with(jwt())` | `.mutateWith(mockJwt())` |
| Opaque token giả lập | `.with(opaqueToken())` | `.mutateWith(mockOpaqueToken())` |
| OAuth2 login giả lập | `.with(oauth2Login())` | `.mutateWith(mockOAuth2Login())` |
| OIDC login giả lập | `.with(oidcLogin())` | `.mutateWith(mockOidcLogin())` |
| CSRF token | `.with(csrf())` | `.mutateWith(csrf())` |
| Đọc context imperative/reactive | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

Những helper này tạo trạng thái xác thực để kiểm tra logic downstream. Khi cần kiểm tra mật khẩu, chữ ký JWT, introspection, callback OAuth2/OIDC hoặc session thật, cần request đi qua cơ chế xác thực tương ứng. Không dùng mock principal làm bằng chứng cho toàn bộ giao thức.

## 7. Chẩn đoán lỗi: vì sao test không nhìn thấy user?

### 7.1. Servlet trả anonymous dù đã dùng @WithMockUser

Kiểm tra:

- Test có chạy với Spring Test context và Spring Security test listener hay không.
- Test có đang gọi bean trong cùng vòng đời context đã được annotation thiết lập không.
- MockMvc có thực sự tích hợp Spring Security filter chain không.
- Có test setup tùy chỉnh nào xóa hoặc thay context trước khi request được xử lý không.

Nếu chỉ muốn thiết lập user cho một request MockMvc, dùng `.with(user(...))` để làm rõ danh tính gắn với request.

### 7.2. Reactive code không đọc được user dù test có @WithMockUser

Nguyên nhân thường gặp là context được thiết lập trong holder imperative nhưng publisher không nhận Reactor Context. Kiểm tra `ReactorContextTestExecutionListener` hoặc chuyển sang thiết lập tường minh bằng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`.

Với test HTTP, dùng `mutateWith(mockUser(...))` trên `WebTestClient` đã áp dụng `springSecurity()`.

### 7.3. Method security không chạy

- Xác nhận đã bật `@EnableMethodSecurity` cho Servlet hoặc `@EnableReactiveMethodSecurity` cho Reactive.
- Gọi bean do Spring quản lý, không tự tạo object.
- Với Reactive, method cần trả về kiểu publisher được hỗ trợ và test phải subscribe.
- Kiểm tra đường gọi nội bộ qua `this.method()` có bỏ qua proxy hay không.

### 7.4. Reactive test chỉ tạo Mono rồi kết thúc

Một publisher có thể lazy. Nếu test không subscribe, code bảo mật và handler có thể chưa chạy. Dùng `StepVerifier` hoặc `WebTestClient.exchange()` để kích hoạt và xác minh publisher.

### 7.5. Test nhận 403 nhưng không phải do role

Nếu request là POST/PUT/PATCH/DELETE và CSRF đang bật, thiếu token có thể làm filter chặn trước khi authorization được kiểm tra. Thêm `csrf()` vào test phân quyền; bỏ token trong test chuyên kiểm tra CSRF.

### 7.6. Test mock JWT xanh nhưng bearer token thật thất bại

Mock JWT bỏ qua decoder. Kiểm tra riêng chữ ký, thời hạn, issuer, audience, JWK/JWKS và converter bằng test gửi bearer token qua resource server thật trong test context.

## 8. Ma trận chọn công cụ theo loại test

| Câu hỏi cần trả lời | Servlet | Reactive |
| --- | --- | --- |
| Request HTTP có qua filter chain và URL authorization không? | `MockMvc` + `springSecurity()`/`@AutoConfigureMockMvc`. | `WebTestClient` gắn context + `springSecurity()`. |
| Một user cụ thể có được gọi endpoint không? | `.with(user(...))` hoặc `.with(jwt())`. | `.mutateWith(mockUser(...))` hoặc `.mutateWith(mockJwt())`. |
| Method security chặn service không? | Gọi bean Spring với `@WithMockUser`. | Gọi bean Reactive với Reactor Context và `StepVerifier`. |
| Principal hiện tại được đọc thế nào? | `SecurityContextHolder`. | `ReactiveSecurityContextHolder` trong publisher. |
| Cần test token thật? | Gửi bearer header qua `JwtDecoder`/`OpaqueTokenIntrospector`. | Gửi bearer header qua `ReactiveJwtDecoder`/`ReactiveOpaqueTokenIntrospector`. |
| Cần test tác vụ bất đồng bộ? | Kiểm tra cơ chế truyền SecurityContext qua executor/task. | Kiểm tra context qua subscription và các nhánh publisher. |

Một test tốt nên được chọn dựa trên **cơ chế chịu trách nhiệm**. Dùng MockMvc cho Servlet, WebTestClient cho WebFlux, và test method security ở đúng loại bean/context của ứng dụng.

## 9. Bài thực hành tổng hợp

Tạo hai ứng dụng mẫu nhỏ: một Spring MVC và một WebFlux. Mỗi ứng dụng có endpoint hồ sơ cá nhân và endpoint quản trị.

1. **Servlet HTTP:** dùng MockMvc kiểm tra anonymous, user thường và admin. Thử cả `.with(user(...))` và `@WithMockUser`, so sánh phạm vi của chúng.
2. **Servlet method security:** bảo vệ service bằng `@PreAuthorize`. Gọi bean Spring với hai role và xác minh kết quả/ngoại lệ.
3. **Reactive HTTP:** dùng WebTestClient gắn application context, áp dụng `springSecurity()` và dùng `mutateWith(mockUser(...))`.
4. **Reactive context:** viết một handler đọc tên từ `ReactiveSecurityContextHolder`; xác minh publisher nhận đúng principal.
5. **Reactive method security:** bật `@EnableReactiveMethodSecurity`, dùng `StepVerifier` và `contextWrite(...)` để thử user được phép/bị từ chối.
6. **Annotation trong Reactive:** thêm `ReactorContextTestExecutionListener` rồi thử `@WithMockUser`; so sánh với cách truyền context trực tiếp.
7. **Context isolation:** gửi hai request với hai người dùng khác nhau; xác minh request thứ hai không nhận danh tính của request thứ nhất.
8. **Async boundary:** nếu Servlet dùng executor, kiểm tra việc truyền context bằng wrapper phù hợp. Nếu Reactive chuyển scheduler, kiểm tra context vẫn được đọc trong cùng publisher chain.
9. **Token mock:** thử JWT hoặc OIDC mock trong từng stack; ghi rõ phần xác minh token thật chưa được kiểm tra.

**Tiêu chí hoàn thành:** bạn giải thích được context nằm ở đâu, ai thiết lập, code đọc nó bằng API nào, phạm vi tồn tại đến đâu và test nào chứng minh đường xử lý thật.

## 10. Ghi nhớ

Servlet và Reactive cùng dùng `SecurityContext` để biểu diễn danh tính và quyền, nhưng khác nhau ở cách mang context. Servlet mặc định dùng `SecurityContextHolder` theo ThreadLocal trong vòng đời request. Reactive dùng Reactor Context và `ReactiveSecurityContextHolder` trong chuỗi publisher/subscriber.

Vì thế, hãy dùng `MockMvc` và request post-processor/annotation cho ứng dụng Servlet; dùng `WebTestClient` cùng `mockUser()`, `mockJwt()` và các configurer Reactive cho WebFlux. Khi kiểm tra method security Reactive, bảo đảm context có mặt lúc publisher được subscribe và dùng `StepVerifier` để quan sát kết quả.

Một bài test đúng mô hình sẽ chứng minh được **đúng danh tính được truyền đến đúng luồng xử lý**, không phụ thuộc vào việc tình cờ chạy trên cùng một thread.
