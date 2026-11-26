# Bật method security bằng cơ chế của phiên bản mục tiêu

## 1. Mục tiêu và phạm vi

Trong một ứng dụng Spring, cấu hình bảo vệ URL chỉ quyết định ai được đi qua tầng HTTP. Một thao tác nghiệp vụ có thể còn được gọi từ controller khác, message consumer, scheduler hoặc một bean nội bộ. **Method security** đặt chính sách truy cập ngay tại phương thức của bean do Spring quản lý, để lời gọi được kiểm tra trước hoặc sau khi thực thi theo chính sách đã khai báo.

Bài học thuộc chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**. Trọng tâm là bật đúng cơ chế method security theo thế hệ Spring Security đang dùng, nhận biết cơ chế thực thi và kiểm chứng bằng `spring-security-test` trên ứng dụng Servlet hoặc Reactive. Sau bài này, bạn có thể:

- Chọn `@EnableMethodSecurity` hoặc `@EnableReactiveMethodSecurity` phù hợp với stack và phiên bản, thay vì sao chép cấu hình cũ theo thói quen.
- Phân biệt chính sách ở `SecurityFilterChain`/`SecurityWebFilterChain` với chính sách trên phương thức; hiểu vì sao cần kiểm thử cả hai.
- Viết và kiểm thử `@PreAuthorize`, hiểu ý nghĩa của `@PostAuthorize`, `@Secured`, `@RolesAllowed` và authority thực tế trong `SecurityContext`.
- Dùng `@WithMockUser`, MockMvc, WebTestClient và các đối tượng xác thực giả lập để chứng minh ca được phép, bị từ chối, chưa xác thực.
- Chẩn đoán các trường hợp annotation có mặt nhưng không có hiệu lực, đặc biệt là bean không qua Spring proxy và self-invocation.

> **Quy tắc chọn phiên bản:** Phiên bản *Spring Security* thực tế trong dependency graph quyết định annotation/cơ chế có sẵn. Spring Boot thường quản lý phiên bản thông qua BOM, nhưng bản Boot không phải là tên của annotation. Các ví dụ Java chính tập trung vào API hiện đại của Spring Security 6.x; nguyên tắc lựa chọn cũng áp dụng cho dòng 7.x. Khi dùng Boot 4.x/Security 7.x, cần đối chiếu import dành cho test auto-configuration với phiên bản Boot của dự án.

## 2. Method security giải quyết vấn đề gì?

Giả sử API `GET /invoices/42` được phép cho người dùng đã đăng nhập. Đây mới là điều kiện truy cập URL. Chính sách nghiệp vụ có thể yêu cầu quyền `invoice:read`, hoặc chỉ cho chủ sở hữu hóa đơn đọc nội dung.

```text
Client / test
     |
     v
Spring Security HTTP filter chain
     |  Kiểm tra authentication, URL, CSRF, ...
     v
Controller  ---> InvoiceService (Spring bean qua proxy)
                        |
                        v
                  Method interceptor
                  @PreAuthorize(...)
                        |
              +---------+---------+
              |                   |
          Cho phép             Từ chối
              |                   |
              v                   v
         Business method     AccessDeniedException
```

Chính sách HTTP và method security là **hai lớp kiểm soát khác nhau**. Một URL có thể qua kiểm tra HTTP rồi bị chặn ở service. Ngược lại, nếu chỉ bảo vệ URL mà service không có chính sách riêng, lời gọi ngoài luồng HTTP có thể không được kiểm tra theo yêu cầu nghiệp vụ.

`@PreAuthorize` kiểm tra **trước** khi thân phương thức chạy. `@PostAuthorize` kiểm tra **sau** khi có kết quả, thích hợp với một số chính sách phụ thuộc dữ liệu trả về; vì thân phương thức đã chạy nên không nên dùng riêng `@PostAuthorize` để bảo vệ thao tác có tác dụng phụ như chuyển tiền, xóa dữ liệu hay gửi thông báo.

## 3. Chọn annotation theo phiên bản và stack

| Môi trường | Cơ chế bật method security | Ghi chú |
|---|---|---|
| Servlet, Spring Security 6.x (thường cùng Boot 3.x) | `@EnableMethodSecurity` | Cơ chế hiện đại dựa trên `AuthorizationManager`; `@PreAuthorize`/`@PostAuthorize` được bật mặc định. |
| Servlet, Spring Security 7.x (thường cùng Boot 4.x) | `@EnableMethodSecurity` | Giữ mô hình method security hiện đại; kiểm tra sự tương thích của các thư viện và import khi nâng Boot. |
| Reactive WebFlux, Spring Security 6.x/7.x | `@EnableReactiveMethodSecurity` | Method security hoạt động cùng reactive security context trên Reactor; phương thức bảo vệ thường trả về `Mono`/`Flux`. |
| Dự án đời cũ dùng Spring Security 5.x | Có thể gặp `@EnableGlobalMethodSecurity(prePostEnabled = true)` | Đây là cấu hình cũ. `@EnableMethodSecurity` đã xuất hiện từ Spring Security 5.6 và là hướng chuyển đổi cho dự án đủ phiên bản. |

Ví dụ chuyển từ cấu hình cũ:

```java
// Cách cũ trong một số dự án Spring Security 5.x:
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacyMethodSecurityConfig { }

// Cách sử dụng với Spring Security hiện đại:
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig { }
```

Điểm khác biệt dễ bỏ sót: `@EnableMethodSecurity` đã bật các annotation pre/post theo mặc định, vì vậy không cần `prePostEnabled = true`. Tuy nhiên, **`@Secured` và JSR-250 `@RolesAllowed` không tự bật theo cấu hình mặc định**; nếu cần các annotation này, chủ động cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
public class MethodSecurityConfig {
}
```

Với Spring Security 6+/Spring Boot 3+, `@RolesAllowed` sử dụng package `jakarta.annotation.security.RolesAllowed`. Các ví dụ rất cũ dùng `javax.annotation.security` có thể phải đổi import khi nâng cấp lên thế hệ Jakarta.

**Không trộn hai cơ chế cấu hình cũ và mới trong cùng ứng dụng.** Hãy kiểm tra bản Spring Security đã được resolve, chọn cơ chế tương ứng và giữ đúng một nguồn cấu hình method security có chủ đích. Annotation trên service sẽ không có hiệu lực chỉ vì đã thêm `spring-boot-starter-security`: ứng dụng cần thực sự bật method security.

## 4. Chuẩn bị dependency và cấu hình Servlet

Trong một dự án Spring Boot dùng Maven, dependency chính và test thường là:

```xml
<dependencies>
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
```

Gradle Kotlin DSL tương đương:

```kotlin
implementation("org.springframework.boot:spring-boot-starter-security")
testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.security:spring-security-test")
```

Trong dự án Boot được quản lý dependency bằng BOM, thường **không khai báo phiên bản riêng** cho `spring-security-test`; để BOM chọn phiên bản phù hợp với các module Spring Security khác. Nếu không dùng BOM, phải đồng bộ phiên bản các module theo dependency management của dự án.

Bật method security bằng một class được component scan hoặc `@Import` vào application context:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Annotation này đăng ký các interceptor cho method authorization. Tại runtime, Spring AOP thường tạo proxy cho bean cần bảo vệ; lời gọi đi **qua proxy** mới được interceptor kiểm tra. Không cần viết một `MethodSecurityInterceptor` thủ công chỉ để dùng `@PreAuthorize` thông thường.

Ví dụ service kiểm soát cả authority cụ thể và vai trò quản trị:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    @PreAuthorize("hasAuthority('invoice:read')")
    public String read(String invoiceId) {
        // Minh họa; dự án thật sẽ đọc dữ liệu từ repository.
        return "INV-" + invoiceId;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String approve(String invoiceId) {
        // Minh họa; dự án thật sẽ thực hiện nghiệp vụ phê duyệt.
        return "APPROVED-" + invoiceId;
    }
}
```

`hasAuthority('invoice:read')` so khớp **chính xác** authority được cấp. `hasRole('ADMIN')` mặc định kiểm tra authority `ROLE_ADMIN`. Vì thế `@WithMockUser(roles = "ADMIN")` phù hợp với `hasRole('ADMIN')`, còn `@WithMockUser(authorities = "invoice:read")` phù hợp với `hasAuthority('invoice:read')`. Không tự thêm tiền tố `ROLE_` vào đối số `roles` của `@WithMockUser`.

Nếu hệ thống cấp quyền qua OAuth2 access token, converter mặc định của JWT resource server thường chuyển scope như `invoices.read` thành authority `SCOPE_invoices.read`. Khi đó biểu thức cần khớp convention thực tế, chẳng hạn `hasAuthority('SCOPE_invoices.read')`; đừng mặc định rằng `invoice:read`, `ROLE_ADMIN` và `SCOPE_invoices.read` là các quyền tương đương.

## 5. Vì sao cần kiểm tra cả HTTP lẫn phương thức?

Thêm controller để có đường đi HTTP tới service:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/invoices")
public class InvoiceController {
    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public String read(@PathVariable String id) {
        return service.read(id);
    }
}
```

Để cô lập hiệu ứng của method security trong ví dụ, cấu hình HTTP cho phép request đi đến controller và bật HTTP Basic để phản hồi rõ ràng khi chưa xác thực:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`permitAll()` ở đây là thiết kế **chỉ dành cho minh họa kiểm thử**: request được chuyển tiếp đến service, nhưng `@PreAuthorize` vẫn buộc principal có `invoice:read`. Trong sản phẩm thật, hãy định nghĩa chính sách HTTP phù hợp thay vì mở rộng `permitAll()` toàn ứng dụng. Với ví dụ GET, CSRF không phải là điều kiện gây nhiễu; khi thêm POST/PUT/DELETE, test phải xử lý CSRF và các chính sách HTTP tương ứng.

Với stack Servlet, kết quả kỳ vọng khi gọi `GET /invoices/42` qua filter chain như sau:

| Người gọi | Authority | Kết quả dự kiến | Nguồn quyết định |
|---|---|---|---|
| Chưa đăng nhập | Không có | **401 Unauthorized** với cấu hình HTTP Basic ở trên | Không có authentication được phương thức chấp nhận; entry point HTTP Basic trả 401. |
| Đã đăng nhập | `invoice:write` | **403 Forbidden** | Authentication hợp lệ nhưng `@PreAuthorize` từ chối. |
| Đã đăng nhập | `invoice:read` | **200 OK**, nội dung `INV-42` | Method interceptor cho phép gọi service. |

**Lưu ý:** 401 và 403 là mã phản hồi ở **tầng HTTP**, không phải kết quả trực tiếp của lời gọi Java tới service. Với test service thuần, hãy kỳ vọng exception tương ứng (chẳng hạn `AccessDeniedException`), không kỳ vọng một mã HTTP.

## 6. Kiểm thử trực tiếp method security bằng `@WithMockUser`

Đây là cách ngắn để chứng minh rằng interceptor đã được đăng ký và hoạt động. Test cần khởi tạo Spring context để lấy bean đã được proxy; tự `new InvoiceService()` sẽ bỏ qua method security.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class InvoiceServiceSecurityTest {

    @Autowired
    InvoiceService service;

    @Test
    @WithMockUser(authorities = "invoice:read")
    void userWithReadAuthorityCanRead() {
        assertEquals("INV-42", service.read("42"));
    }

    @Test
    @WithMockUser(authorities = "invoice:write")
    void userWithoutReadAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.read("42"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanApprove() {
        assertEquals("APPROVED-42", service.approve("42"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotApprove() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve("42"));
    }
}
```

`@WithMockUser` tạo một `Authentication` thử nghiệm trong `SecurityContext`, không cần truy vấn database người dùng và không chứng minh password, OAuth2 token hay chữ ký JWT thật đã được xác minh. Test service này trả lời câu hỏi: **với authentication có tập quyền cho trước, annotation method security cho phép hay chặn lời gọi?**

Có thể thêm ca `@WithAnonymousUser` hoặc không gắn annotation để kiểm tra trường hợp chưa xác thực. Exception cụ thể ở lớp method có thể khác theo trạng thái security context, nhưng nguyên tắc cần chứng minh là người gọi không được thực thi nghiệp vụ khi chính sách yêu cầu quyền mà họ không có.

Một test tốt nên bao gồm cả **ca được phép lẫn ca bị từ chối**. Chỉ kiểm tra `200 OK` hoặc chỉ gọi service thành công chưa đủ để phát hiện trường hợp `@EnableMethodSecurity` bị quên: khi không bật interceptor, một số lời gọi trái quyền cũng có thể thành công.

## 7. Kiểm chứng end-to-end ở HTTP Servlet với MockMvc

Để kiểm chứng thêm chuỗi HTTP, dùng `@SpringBootTest`, `@AutoConfigureMockMvc` và `spring-security-test`. Với Spring Boot 3.x, import của `@AutoConfigureMockMvc` là `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`; các package test auto-configuration của Boot 4.x được tổ chức lại, nên sử dụng import tương ứng phiên bản đang chạy.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class InvoiceHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCallerGets401() throws Exception {
        mvc.perform(get("/invoices/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "invoice:write")
    void wrongAuthorityGets403() throws Exception {
        mvc.perform(get("/invoices/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void correctAuthorityGets200() throws Exception {
        mvc.perform(get("/invoices/42"))
            .andExpect(status().isOk())
            .andExpect(content().string("INV-42"));
    }
}
```

Các kỳ vọng 401/403/200 ở trên dựa vào **đúng cấu hình HTTP Basic minh họa ở mục 5** và service có `@PreAuthorize` ở mục 4. Nếu thay bằng form login, exception handler riêng, resource server hoặc chính sách URL khác, kết quả HTTP có thể khác. Luôn xác minh theo cấu hình thực tế thay vì giả định mọi ứng dụng đều phải trả cùng một status.

Với `MockMvcBuilders.webAppContextSetup(context)` tự tạo, cần tích hợp Spring Security test, chẳng hạn `.apply(springSecurity())`, để filter chain và request post-processors hoạt động như mong muốn. `@AutoConfigureMockMvc` trong ứng dụng Boot có Spring Security thường xử lý việc tích hợp này.

Khi kiểm thử resource server dùng JWT, có thể tạo authentication giả lập từ request:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Trong một test MockMvc, khi service yêu cầu SCOPE_invoices.read:
mvc.perform(get("/invoices/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoices.read"))))
    .andExpect(status().isOk());
```

Đoạn JWT trên **chỉ hợp lệ nếu chính sách của service cũng dùng** `hasAuthority('SCOPE_invoices.read')`; service minh họa ở mục 4 đang đòi `invoice:read`, nên cần sửa biểu thức hoặc cấp đúng authority trước khi chạy test. `jwt()` giả lập kết quả xác thực để kiểm tra authorization; nó không kiểm tra chữ ký token, issuer, audience hoặc network call đến identity provider. Với OAuth2 Login/OIDC trên Servlet, `oauth2Login()` và `oidcLogin()` cũng cung cấp trạng thái xác thực giả lập phù hợp cho các bài test theo flow đó.

## 8. Bật method security trên WebFlux/Reactive

Reactive WebFlux dùng cơ chế bật riêng, **không dùng `@EnableMethodSecurity` của Servlet** để kỳ vọng bảo vệ các luồng reactive. Cấu hình tối thiểu:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
```

Service trả về kiểu reactive và khai báo chính sách:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInvoiceService {

    @PreAuthorize("hasAuthority('invoice:read')")
    public Mono<String> read(String invoiceId) {
        return Mono.just("INV-" + invoiceId);
    }
}
```

Trong reactive stack, security context được truyền theo **Reactor Context** thay vì chỉ dựa vào `ThreadLocal` của servlet. Không tự `block()` bên trong phương thức reactive để cố lấy authentication. Chính sách được đánh giá khi publisher được subscribe trong ngữ cảnh tương ứng; một test chỉ tạo `Mono` mà không subscribe sẽ không kiểm chứng được kết quả.

Nếu endpoint WebFlux đã gọi `ReactiveInvoiceService.read()`, có thể kiểm chứng với WebTestClient và security mock configurer:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

// webTestClient được tạo từ Spring WebFlux application context:
WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();

webTestClient.mutateWith(mockUser("lan").authorities(
        new SimpleGrantedAuthority("invoice:read")))
    .get().uri("/invoices/42")
    .exchange()
    .expectStatus().isOk();

webTestClient.mutateWith(mockUser("lan").authorities(
        new SimpleGrantedAuthority("invoice:write")))
    .get().uri("/invoices/42")
    .exchange()
    .expectStatus().isForbidden();
```

Đây là **mẫu đoạn test**: `applicationContext` cần được inject trong test, ứng dụng cần controller/route reactive `/invoices/{id}` gọi đúng service và HTTP security phải cho request tới service để kiểm tra method policy. WebTestClient đã tự thực hiện request và subscribe; với test trực tiếp `Mono`/`Flux`, dùng `StepVerifier` để xác minh tín hiệu hoàn thành hoặc lỗi. Khi dùng JWT/OIDC giả lập với WebTestClient, `mockJwt()`/`mockOidcLogin()` thuộc nhóm *reactive server test configurer*, khác API `jwt()`/`oidcLogin()` dùng cho MockMvc Servlet.

## 9. Các bẫy thường gặp khi bật annotation

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| Có `@PreAuthorize` nhưng user sai quyền vẫn chạy được | Chưa có `@EnableMethodSecurity` hoặc `@EnableReactiveMethodSecurity` phù hợp | Kiểm tra annotation nằm trong Spring context và viết test **denied** gọi bean thật. |
| Test tạo `new InvoiceService()` rồi annotation không chặn | Instance không do Spring quản lý | Inject bean từ Spring test context. |
| Gọi trực tiếp từ phương thức khác cùng bean mà không bị kiểm tra | **Self-invocation** bỏ qua AOP proxy theo cấu hình proxy thông dụng | Chuyển phương thức được bảo vệ sang bean riêng, gọi qua bean được inject. |
| Một số phương thức không bị chặn | Method là `private`/`final` hoặc đối tượng/proxy không thể advise phù hợp | Đặt ranh giới bảo mật ở public method của Spring bean và kiểm tra cơ chế proxy. |
| `@Secured`/`@RolesAllowed` không có tác dụng | Chưa bật `securedEnabled`/`jsr250Enabled` | Khai báo cờ rõ ràng trên `@EnableMethodSecurity`. |
| `@WithMockUser(roles = "ADMIN")` không qua `hasAuthority('ADMIN')` | Role có tiền tố mặc định `ROLE_` nhưng authority được kiểm tra nguyên văn | Đồng bộ biểu thức với quyền thật; phân biệt `hasRole` và `hasAuthority`. |
| Test MockMvc nhận 302 thay vì 401 | Ứng dụng sử dụng form login hoặc entry point khác HTTP Basic | Kiểm tra `SecurityFilterChain` và exception handling thay vì sửa assert tùy tiện. |
| Test `@WebMvcTest` báo service không áp chính sách | Service thật bị thay bằng mock hoặc không được nạp vào slice test | Dùng test context nạp bean service thật cho bài toán method security. |
| Reactive test không thể hiện lỗi quyền | Không subscribe publisher hoặc security context không vào Reactor Context | Dùng WebTestClient tích hợp `springSecurity()`/`mockUser()` hoặc StepVerifier với reactive context. |

Ví dụ self-invocation cần nhận diện:

```java
@Service
class InvoiceBatchService {

    public void runBatch() {
        approveInternal();  // Lời gọi "this" trong cùng bean: dễ bỏ qua proxy.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void approveInternal() {
        // Tác vụ cần bảo vệ.
    }
}
```

Trong proxy mode mặc định, gọi `runBatch()` từ bên ngoài đi qua proxy không đồng nghĩa lời gọi nội bộ `approveInternal()` cũng đi qua proxy. Cách rõ ràng là đặt `approveInternal()` trên bean nghiệp vụ riêng và inject bean đó vào batch service, rồi viết test trái quyền đi qua đúng đường gọi thực tế.

Nếu chính sách phụ thuộc quyền sở hữu bản ghi, chỉ kiểm tra `hasRole('USER')` là chưa đủ. Có thể đặt chính sách lên một bean chuyên kiểm tra tài nguyên, ví dụ `@PreAuthorize("@invoicePolicy.canRead(authentication, #invoiceId)")`, sau đó kiểm thử đủ trường hợp **đúng người/đúng hóa đơn**, **đúng role nhưng hóa đơn người khác** và **không có quyền**. Với SpEL tham chiếu tên tham số `#invoiceId`, bảo đảm tên tham số được giữ lại trong bytecode (`-parameters`) hoặc dùng cơ chế đặt tên tham số được Spring Security hỗ trợ.

## 10. Ma trận kiểm thử tối thiểu

Khi hoàn tất cấu hình cho một phương thức nhạy cảm, đối chiếu các tầng sau:

| Ca thử | Test service với `@WithMockUser` | Test HTTP MockMvc/WebTestClient | Bảo đảm điều gì? |
|---|---|---|---|
| Principal có đúng authority | Lời gọi thành công | 200 khi HTTP cho phép | Cấu hình và biểu thức chấp nhận đúng quyền. |
| Principal thiếu authority | `AccessDeniedException` hoặc lỗi authorization tương ứng | 403 khi đã xác thực | Interceptor thực sự hoạt động. |
| Chưa xác thực | Không được gọi nghiệp vụ | Thường 401 với HTTP Basic/Bearer, hoặc hành vi entry point đã cấu hình | Không có đường bỏ qua yêu cầu xác thực. |
| Có role nhưng không có quyền sở hữu tài nguyên | Từ chối theo policy đối tượng | 403 theo handler thực tế | Tránh lộ dữ liệu giữa người dùng. |
| Đường gọi nội bộ/không qua controller | Từ chối trên bean thật | Không nhất thiết có HTTP test | Chính sách không chỉ dựa vào URL. |

Đối với request thay đổi trạng thái, bổ sung kiểm tra CSRF trên Servlet khi có áp dụng, kiểm tra nội dung phản hồi và xác minh nghiệp vụ **không bị thực thi** khi bị từ chối (ví dụ repository không thay đổi dữ liệu). Với JWT/OAuth2/OIDC, phân biệt rõ test mock authentication phục vụ authorization với integration test xác thực token thật.

## 11. Thực hành tự kiểm tra

1. Trong một ứng dụng Servlet dùng Spring Security 6.x, tạo `@EnableMethodSecurity` và service có `@PreAuthorize("hasAuthority('invoice:read')")`. Dùng `@WithMockUser` chứng minh một test được phép và một test bị từ chối. Tạm thời bỏ annotation enable để quan sát vì sao test bị từ chối phải thất bại; sau đó khôi phục cấu hình.
2. Bổ sung controller gọi service, kiểm thử MockMvc theo ba trường hợp `401`, `403`, `200` với cấu hình HTTP Basic đã nêu. Đổi sang cấu hình form login hoặc JWT của dự án và giải thích vì sao status/entry point có thể khác.
3. Thử `@Secured("ROLE_ADMIN")`: xác minh annotation chỉ hoạt động sau khi bật `securedEnabled = true`. So sánh với `@PreAuthorize("hasRole('ADMIN')")`.
4. Thử gọi phương thức được bảo vệ từ một phương thức khác trong cùng bean, sau đó tách sang bean riêng. Viết một test gọi theo đường nghiệp vụ thật để chứng minh sự khác biệt.
5. Với WebFlux, dùng `@EnableReactiveMethodSecurity`, `Mono<String>` và WebTestClient có `springSecurity()`. Chứng minh `mockUser` với `invoice:read` được phép, còn `invoice:write` bị từ chối; giải thích vai trò Reactor Context.

**Tiêu chí hoàn thành:** Một phương thức nhạy cảm phải chặn được người gọi sai quyền khi được truy cập qua Spring bean thật, và test HTTP phải phản ánh đúng filter chain/entry point đang cấu hình. Nếu test trái quyền vẫn thành công, trước hết hãy kiểm tra annotation enable, bean/proxy và đường gọi; đó thường là lỗi cấu hình method security, không phải lỗi của dữ liệu mock.
