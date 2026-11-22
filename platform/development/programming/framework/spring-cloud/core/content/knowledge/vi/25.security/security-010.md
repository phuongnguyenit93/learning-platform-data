# Kiểm thử quyền tối thiểu đối với thao tác quản trị

## 1. Mục tiêu của bài kiểm thử

Các thao tác quản trị trong hệ thống Spring Cloud thường có tác động lớn hơn thao tác đọc thông thường. Ví dụ, một operator có thể xem danh sách service, drain một instance khỏi traffic, đăng ký service mới, refresh cấu hình hoặc thay đổi trạng thái của registry. Nếu mọi người dùng đã đăng nhập đều được thực hiện các thao tác này, ứng dụng đang cấp quyền rộng hơn nhu cầu công việc.

Nguyên tắc least privilege yêu cầu mỗi principal chỉ có đúng quyền cần cho nhiệm vụ của họ. Việc kiểm thử phải chứng minh cả hai phía:

- Người có quyền phù hợp thực hiện được thao tác được giao.
- Người không có quyền, kể cả người đã đăng nhập, không thể thực hiện thao tác đó và không gây ra side effect.

Một bài test chỉ xác nhận administrator gọi thành công là chưa đủ. Cần kiểm tra anonymous, người dùng đã xác thực nhưng thiếu quyền, người chỉ có quyền đọc và người có đúng authority cho một thao tác cụ thể.

Sau bài học, người đọc có thể:

- Thiết kế ma trận quyền cho các thao tác quản trị.
- Phân biệt role với authority chi tiết.
- Bảo vệ cả HTTP endpoint và service method.
- Viết test cho anonymous, authenticated, forbidden và allowed.
- Kiểm thử CSRF, JWT authority mapping và quyền theo tenant/resource.
- Xác nhận request bị từ chối không làm thay đổi dữ liệu hoặc phát sinh side effect.

## 2. Least privilege bắt đầu từ ma trận quyền

Trước khi viết annotation hoặc security matcher, hãy liệt kê các thao tác và quyền cần thiết. Không nên suy ra quyền chỉ từ tên nhóm người dùng như operator hoặc administrator.

Ví dụ một service quản lý đăng ký service:

| Thao tác | Authority đề xuất | Người dùng điển hình |
| --- | --- | --- |
| Xem registry | `registry:read` | Monitoring, operator |
| Drain một instance | `registry:drain` | Operator trực ca |
| Đăng ký instance | `registry:register` | Deployment agent |
| Gỡ registration | `registry:deregister` | Registry administrator |
| Refresh cấu hình | `config:refresh` | Configuration operator |
| Tắt ứng dụng | `application:shutdown` | Administrator có quy trình phê duyệt |

Ma trận cần trả lời ba câu hỏi:

1. Hành động nào là read-only, hành động nào làm thay đổi trạng thái?
2. Một người dùng cần quyền nào để thực hiện từng hành động?
3. Có cần giới hạn thêm theo tenant, service, environment hoặc resource owner không?

Không nên tạo một authority chung như `admin:all` rồi gán cho mọi tài khoản vận hành. Quyền càng cụ thể thì việc cấp, thu hồi và kiểm thử càng rõ ràng.

### 2.1. Role và authority khác nhau thế nào?

Role thường mô tả nhóm trách nhiệm ở mức rộng, còn authority mô tả một quyền cụ thể mà code có thể kiểm tra.

| Cách kiểm tra | Giá trị được so khớp |
| --- | --- |
| `hasRole("OPS")` | Authority `ROLE_OPS` theo prefix mặc định |
| `hasAuthority("registry:drain")` | Authority chính xác `registry:drain` |
| `hasAnyAuthority("registry:read", "registry:drain")` | Một trong các authority được liệt kê |

`@WithMockUser(roles = "OPS")` tự thêm tiền tố `ROLE_`. `@WithMockUser(authorities = "registry:drain")` giữ nguyên tên authority. Khi ứng dụng dùng permission dạng domain:action, hãy test bằng authorities để tránh nhầm role prefix.

Role hierarchy có thể cấp các quyền kế thừa, ví dụ `ROLE_PLATFORM_ADMIN` bao gồm `registry:read` và `registry:drain`. Khi dùng hierarchy, test cần xác nhận cả quyền được kế thừa lẫn quyền không được kế thừa; nếu không, một thay đổi hierarchy có thể vô tình mở rộng quyền.

## 3. Bảo vệ ở request layer và service layer

Request-level authorization bảo vệ đường vào HTTP. Method security bảo vệ thao tác tại service, kể cả khi service được gọi từ một controller khác, message listener hoặc một thành phần Spring khác.

Hai lớp này có trách nhiệm bổ sung cho nhau:

- HTTP security xác định request nào được đi vào route quản trị.
- Method security xác định principal có được thực hiện hành động cụ thể hay không.
- Kiểm tra quyền theo resource xác định principal có quyền trên đúng service, tenant hoặc instance đang được yêu cầu hay không.

Không nên chỉ bảo vệ URL rồi giả định mọi đường gọi service đều đi qua controller đó. Cũng không nên bỏ catch-all rule ở HTTP layer vì method security chỉ bảo vệ những method đã được đánh dấu.

## 4. Ví dụ thiết kế quyền cho Registry Admin

### 4.1. Bật method security

Spring Security không tự bật method authorization chỉ vì ứng dụng có Spring Boot Security starter. Cần khai báo:

```java
@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Khi bật, Spring Security có thể áp dụng @PreAuthorize, @PostAuthorize, @PreFilter và @PostFilter cho Spring-managed bean. Cấu hình này dựa trên Spring AOP; hãy gọi service qua bean proxy do Spring quản lý.

### 4.2. Khai báo quyền ở service method

Service chỉ cho phép principal có authority registry:drain gọi thao tác drain:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class RegistryAdminService {

    private final RegistryRepository repository;

    public RegistryAdminService(RegistryRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('registry:drain')")
    public void drain(String instanceId) {
        repository.markDraining(instanceId);
    }

    @PreAuthorize("hasAuthority('registry:register')")
    public void register(RegistrationRequest request) {
        repository.register(request);
    }

    @PreAuthorize("hasAuthority('registry:deregister')")
    public void deregister(String instanceId) {
        repository.remove(instanceId);
    }
}
```

Mỗi method yêu cầu đúng authority cho hành động của nó. Người có registry:read không tự động có quyền drain hoặc deregister.

### 4.3. Bảo vệ route HTTP

Request layer có thể áp dụng cùng ma trận:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class AdminHttpSecurityConfiguration {

    @Bean
    SecurityFilterChain adminSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/admin/registry/**")
                .hasAuthority("registry:read")
            .requestMatchers(HttpMethod.POST, "/admin/registry/*/drain")
                .hasAuthority("registry:drain")
            .requestMatchers(HttpMethod.POST, "/admin/registry")
                .hasAuthority("registry:register")
            .requestMatchers(HttpMethod.DELETE, "/admin/registry/**")
                .hasAuthority("registry:deregister")
            .anyRequest().denyAll()
        );
        // HTTP Basic minh họa authentication entry point cho API.
        // Ứng dụng dùng JWT có thể cấu hình oauth2ResourceServer thay thế.
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

anyRequest().denyAll() tạo quy tắc mặc định từ chối cho những route chưa được liệt kê. Nếu ứng dụng còn route nghiệp vụ khác, có thể tách security chain hoặc thêm các matcher cần thiết trước catch-all; không để một route mới vô tình rơi vào trạng thái chỉ cần authenticated.

HTTP Basic ở đây chỉ minh họa entry point trả 401 cho request chưa xác thực. Ứng dụng thật vẫn cần AuthenticationProvider, UserDetailsService hoặc OAuth2 Resource Server phù hợp để xác thực credential; chỉ bật httpBasic không tự tạo danh tính và quyền cho người dùng.

### 4.4. Controller chuyển tiếp đến service

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/registry")
public class RegistryAdminController {

    private final RegistryAdminService adminService;

    public RegistryAdminController(RegistryAdminService adminService) {
        this.adminService = adminService;
    }

    @PostMapping("/{instanceId}/drain")
    ResponseEntity<Void> drain(@PathVariable String instanceId) {
        adminService.drain(instanceId);
        return ResponseEntity.noContent().build();
    }
}
```

HTTP matcher và @PreAuthorize cùng yêu cầu registry:drain. Việc lặp lại chính sách ở hai lớp có chủ đích: route bị giới hạn tại biên HTTP và service vẫn được bảo vệ khi được gọi từ đường khác.

## 5. Thiết kế kiểm thử theo ma trận quyền

Với một thao tác drain, ma trận cơ bản có thể như sau:

| Principal | Authority | Kết quả HTTP mong đợi | Service được gọi? |
| --- | --- | --- | --- |
| Anonymous | Không có | `401 Unauthorized` | Không |
| Viewer | `registry:read` | `403 Forbidden` | Không |
| Deployer | `registry:register` | `403 Forbidden` | Không |
| Operator | `registry:drain` | `204 No Content` | Có |
| Admin | `registry:read`, `registry:drain`, `registry:deregister` | `204 No Content` | Có |

Với thao tác ghi, cần xác nhận request bị từ chối không làm thay đổi registry. Chỉ assert 403 là chưa đủ nếu code có thể ghi dữ liệu trước khi kiểm tra quyền.

Nên có cả test dương và test âm cho từng hành động. Nếu một route chỉ có test administrator thành công, test đó không phát hiện được việc route đang cho phép mọi authenticated user.

## 6. Kiểm thử trực tiếp service method

Method-security test giúp kiểm tra quyền ngay tại service, không cần đi qua HTTP controller.

### 6.1. Test authority được phép

Các import và test này dùng JUnit 5, AssertJ, Spring Test và Spring Security Test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;
```

```java
@SpringBootTest
class RegistryAdminServiceSecurityTests {

    @Autowired
    RegistryAdminService adminService;

    @Test
    @WithMockUser(authorities = "registry:drain")
    void operatorWithDrainAuthorityCanDrain() {
        assertThatCode(() -> adminService.drain("instance-17"))
            .doesNotThrowAnyException();
    }
}
```

### 6.2. Test principal thiếu authority

```java
@Test
@WithMockUser(authorities = "registry:read")
void readOnlyUserCannotDrain() {
    assertThatExceptionOfType(AccessDeniedException.class)
        .isThrownBy(() -> adminService.drain("instance-17"));
}
```

### 6.3. Test authority gần giống nhưng không đúng

```java
@Test
@WithMockUser(authorities = "registry:register")
void registerAuthorityDoesNotGrantDrain() {
    assertThatExceptionOfType(AccessDeniedException.class)
        .isThrownBy(() -> adminService.drain("instance-17"));
}
```

Các test này phải inject bean RegistryAdminService từ ApplicationContext. Nếu tạo object bằng new RegistryAdminService(...), Spring AOP proxy không được áp dụng và @PreAuthorize sẽ không chạy.

@WithMockUser đưa một Authentication giả vào SecurityContext cho test. roles tự thêm ROLE_; authorities dùng chính xác chuỗi đã khai báo. Người dùng giả không cần tồn tại trong database, vì vậy cách này tập trung kiểm tra authorization rule chứ không kiểm tra quy trình đăng nhập.

@WithMockUser phù hợp với test gọi trực tiếp Spring bean trên test thread. Với MockMvc, có thể dùng request post processor user() để gắn Authentication vào HTTP request. Với test end-to-end gửi request tới server đang chạy ở thread khác, hãy xác thực request bằng HTTP Basic hoặc bearer token thật.

## 7. Kiểm thử HTTP bằng MockMvc

HTTP test cần đi qua Spring Security filter chain để xác minh request matcher, authentication và method security phối hợp đúng.

### 7.1. Chuẩn bị test

Thêm dependency spring-security-test ở test scope. Để tránh lệch phiên bản với Spring Security runtime, để Spring Boot BOM hoặc Spring Security BOM quản lý version thay vì tự chọn một version riêng. Với Spring Boot 4, package của @AutoConfigureMockMvc thuộc module webmvc test:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

### 7.2. Test anonymous và authenticated thiếu quyền

```java
@SpringBootTest
@AutoConfigureMockMvc
class RegistryAdminHttpSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotDrain() throws Exception {
        mockMvc.perform(post("/admin/registry/instance-17/drain")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readOnlyUserCannotDrain() throws Exception {
        mockMvc.perform(post("/admin/registry/instance-17/drain")
                .with(user("viewer").authorities(
                    new SimpleGrantedAuthority("registry:read")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

Test anonymous vẫn gửi CSRF token hợp lệ để kết quả phản ánh authentication. Nếu bỏ token, CSRF filter có thể trả 403 trước khi request tới bước xác thực; khi đó test không còn chứng minh được anonymous bị từ chối vì thiếu đăng nhập.

Trong ví dụ HTTP Basic ở mục 4.3, anonymous bị trả 401 vì chưa có Authentication. Người đã đăng nhập nhưng thiếu authority nhận 403. Nếu ứng dụng dùng form login, OAuth2 Resource Server hoặc entry point tùy chỉnh, response cho anonymous có thể là redirect hoặc status khác; hãy assert theo entry point thật của API.

### 7.3. Test đúng authority được phép

```java
@Test
void operatorWithDrainAuthorityCanDrain() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain")
            .with(user("operator").authorities(
                new SimpleGrantedAuthority("registry:drain")
            ))
            .with(csrf()))
        .andExpect(status().isNoContent());
}
```

### 7.4. Test role không được tự động trở thành permission

```java
@Test
void genericOpsRoleDoesNotGrantDrainPermission() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain")
            .with(user("ops").roles("OPS"))
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

Test này chỉ đúng khi ứng dụng không cấu hình RoleHierarchy biến ROLE_OPS thành registry:drain. Nếu có hierarchy, hãy kiểm thử chính sách kế thừa theo cấu hình thực tế.

Các đoạn test trên minh họa từng method trong cùng lớp test; khi ghép lại, đặt chúng bên trong RegistryAdminHttpSecurityTests.

## 8. CSRF là một chiều kiểm thử riêng

Spring Security mặc định bảo vệ các HTTP method không an toàn như POST, PUT, PATCH và DELETE bằng CSRF token trong cấu hình session-based thông thường.

Vì vậy, test một thao tác quản trị ghi cần phân biệt:

- Không có CSRF token: request có thể bị từ chối ở CSRF filter.
- Có CSRF token nhưng không đăng nhập: authentication layer từ chối.
- Đã đăng nhập nhưng thiếu authority: authorization layer từ chối.
- Có đủ authority và CSRF hợp lệ: request được xử lý.

Ví dụ xác nhận CSRF protection vẫn hoạt động:

```java
@Test
@WithMockUser(authorities = "registry:drain")
void postWithoutCsrfTokenIsRejected() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain"))
        .andExpect(status().isForbidden());
}
```

Test này cần được giữ riêng với test thiếu authority. Không tắt CSRF toàn cục chỉ để làm cho test POST dễ chạy. Với API stateless dùng bearer token, quyết định CSRF phụ thuộc cách credential được gửi và khả năng trình duyệt tự động đính kèm credential; hãy cấu hình theo threat model rồi test đúng cấu hình đó.

## 9. Kiểm thử JWT và authority mapping

Nếu API dùng OAuth2 Resource Server với JWT, quyền trong token thường được chuyển thành GrantedAuthority bởi JwtAuthenticationConverter. Cần kiểm thử cả ánh xạ claim sang authority.

### 9.1. Dùng jwt() để kiểm tra authorization

jwt() của Spring Security Test tạo một JwtAuthenticationToken giả cho MockMvc. Có thể gán authority trực tiếp:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void jwtWithDrainAuthorityCanDrain() throws Exception {
    mockMvc.perform(post("/admin/registry/instance-17/drain")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("registry:drain")
            ))
            .with(csrf()))
        .andExpect(status().isNoContent());
}
```

Đây là test authorization sau khi đã có Authentication. Nó không xác minh chữ ký JWT, issuer, audience, expiry hoặc cấu hình decoder.

### 9.2. Kiểm thử converter riêng

Nếu token chứa claim permissions với danh sách registry:read và registry:drain, hãy kiểm tra converter tạo ra đúng authorities. Cần có test cho:

- Claim có đủ quyền.
- Claim chỉ có quyền đọc.
- Claim không tồn tại.
- Claim sai kiểu hoặc chứa giá trị không hợp lệ.
- Scope mặc định không vô tình trở thành quyền quản trị.

### 9.3. Integration test cho bearer token thật

Để xác minh toàn bộ authentication pipeline, cần integration test dùng JWT được ký bằng khóa test hoặc test issuer. Kiểm tra decoder, issuer/audience validator, converter và filter chain trong cùng luồng request. jwt() là công cụ tốt để cô lập authorization, nhưng không thay thế test token verification.

## 10. Kiểm thử quyền theo resource và chống IDOR

Có authority registry:drain không nhất thiết đồng nghĩa người dùng được drain mọi instance. Trong hệ thống multi-tenant, quyền cần được giới hạn thêm theo tenant, service hoặc resource owner.

Ví dụ:

```java
// Bổ sung điều kiện resource-level vào method drain đã khai báo ở mục 4.2.
@PreAuthorize("hasAuthority('registry:drain') and " +
        "@registryAuthorization.canManage(authentication, #p0)")
public void drain(String instanceId) {
    repository.markDraining(instanceId);
}
```

RegistryAuthorization là một Spring bean có method canManage(Authentication, String). Biểu thức #p0 tham chiếu tham số đầu tiên, tránh phụ thuộc vào việc compiler có giữ tên tham số hay không. Bean này kiểm tra principal có quyền quản lý đúng instance hay không. Khi viết test, cần tạo ít nhất hai resource thuộc hai tenant khác nhau:

1. User của tenant A drain instance thuộc tenant A: được phép.
2. User của tenant A drain instance thuộc tenant B: bị từ chối.
3. User không có registry:drain nhưng thuộc tenant A: vẫn bị từ chối.

Không nên chỉ kiểm tra quyền trên URL hoặc chỉ kiểm tra role. Nếu API nhận instanceId từ client mà không kiểm tra quyền trên resource, người dùng có thể thay ID trong request để truy cập tài nguyên của tenant khác.

@PostAuthorize có thể bảo vệ dữ liệu trả về theo owner, nhưng không phù hợp để bảo vệ một method ghi dữ liệu: method đã thực thi side effect trước khi điều kiện sau method được đánh giá. Với thao tác quản trị làm thay đổi trạng thái, hãy xác minh quyền trước khi ghi.

## 11. Kiểm thử side effect khi bị từ chối

Một test authorization tốt phải xác nhận thao tác bị từ chối không gọi repository, không phát event và không gửi lệnh tới provider.

Ví dụ với Mockito:

Trong integration test, thay RegistryRepository bằng mock bean để xác nhận thao tác ghi không được gọi:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@MockitoBean
RegistryRepository registryRepository;
```

```java
@Test
@WithMockUser(authorities = "registry:read")
void deniedDrainDoesNotChangeRegistry() {
    assertThatExceptionOfType(AccessDeniedException.class)
        .isThrownBy(() -> adminService.drain("instance-17"));

    verify(registryRepository, never()).markDraining("instance-17");
}
```

Các assertion này kiểm tra invariant quan trọng hơn status code: không có hành động quản trị nào được thực hiện trước khi quyền được xác nhận.

Với hệ thống dùng message broker, cũng cần xác nhận không publish command khi principal bị từ chối. Nếu method có retry, transaction hoặc audit event, hãy xác định side effect nào được phép ghi nhận cho một lần từ chối và test riêng.

## 12. Những lỗi thường gặp khi kiểm thử quyền tối thiểu

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @PreAuthorize không có tác dụng | Chưa bật @EnableMethodSecurity | Kiểm tra cấu hình method security |
| Test method security luôn thành công | Tạo service bằng new nên không đi qua Spring proxy | Inject bean từ ApplicationContext |
| User có ROLE_OPS nhưng test authority không khớp | roles tự thêm tiền tố ROLE_ | Dùng authorities cho permission cụ thể |
| User thiếu quyền nhưng POST trả 403 do CSRF | CSRF filter từ chối trước authorization | Gửi CSRF hợp lệ trong test phân quyền; giữ test CSRF riêng |
| Test controller pass nhưng gọi service từ nơi khác vẫn được | Chỉ bảo vệ HTTP route | Thêm method security tại service boundary |
| Route mới mặc định cho mọi user đã đăng nhập | Thiếu catch-all deny rule | Dùng anyRequest().denyAll() hoặc quy tắc fallback tương đương |
| Admin test pass nhưng viewer cũng làm được | Chỉ có positive test | Thêm test negative cho từng authority |
| Người dùng tenant A truy cập dữ liệu tenant B | Chỉ kiểm tra role, thiếu object-level authorization | Kiểm tra tenant/owner trước side effect |
| jwt() test pass nhưng token thật bị từ chối | Chưa kiểm tra decoder, validator hoặc authority converter | Thêm integration test với token ký bằng khóa test |
| Test POST thất bại dù có authority | CSRF token thiếu hoặc sai | Dùng csrf() trong test authorization |
| Quyền tăng sau khi thêm role hierarchy | Role kế thừa authority ngoài dự kiến | Test cả quyền kế thừa và quyền không được cấp |
| Method không có annotation vẫn được gọi | Method security không tự bảo vệ method không được đánh dấu | Bổ sung request catch-all và rà soát service boundary |

## 13. Checklist kiểm thử quyền tối thiểu

1. Liệt kê thao tác quản trị và authority riêng cho từng hành động.
2. Mặc định từ chối route chưa có quy tắc.
3. Bật @EnableMethodSecurity nếu dùng method authorization.
4. Bảo vệ service method làm thay đổi trạng thái, không chỉ controller.
5. Kiểm thử anonymous, authenticated thiếu quyền và principal có đúng authority.
6. Phân biệt roles với authorities trong test.
7. Kiểm thử CSRF riêng với authorization cho các request ghi.
8. Nếu dùng JWT, test cả authority mapping và token validation.
9. Kiểm tra tenant/resource ownership để ngăn IDOR.
10. Xác nhận denied request không ghi dữ liệu, không publish event và không gọi provider.
11. Kiểm thử role hierarchy để phát hiện quyền kế thừa ngoài ý muốn.
12. Gọi service thông qua Spring proxy trong method-security test.
13. Dùng integration test cho các luồng authentication thực tế và kiểm thử đơn vị cho từng authorization rule.

## 14. Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity, @PreAuthorize, authority, request-level và method-level authorization.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): @WithMockUser, @WithAnonymousUser, @WithUserDetails và test method authorization.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token và cách kiểm thử request không an toàn.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/): MockMvc integration và request post processors.

Least privilege được chứng minh bằng ma trận kiểm thử đầy đủ: mỗi principal chỉ thực hiện được hành động được cấp, các hành động còn lại bị từ chối, và request bị từ chối không tạo side effect. Hãy kiểm tra cả request boundary, service boundary và quyền trên resource cụ thể để chính sách quản trị giữ nguyên khi ứng dụng có thêm controller hoặc đường gọi mới.
