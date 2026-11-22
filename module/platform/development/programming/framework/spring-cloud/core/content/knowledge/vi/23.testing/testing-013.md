# Kiểm thử endpoint quản trị có xác thực và phân quyền

## 1. Mục tiêu

Trong hệ thống Spring Cloud, một số endpoint quản trị có thể làm thay đổi trạng thái vận hành của ứng dụng hoặc cách hệ thống phân tán nhìn nhận một instance. Vì vậy, kiểm thử các endpoint này phải xác minh cả hành vi nghiệp vụ lẫn lớp bảo mật đứng trước endpoint.

Một ví dụ cụ thể là endpoint Service Registry Actuator do Spring Cloud Commons cung cấp:

- `GET /actuator/serviceregistry` đọc trạng thái registration hiện tại.
- `POST /actuator/serviceregistry` cập nhật trạng thái của registration qua JSON body có trường `status`.

Với Eureka, những giá trị status thường gặp là `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`. Provider khác có thể hỗ trợ tập giá trị hoặc cách diễn giải khác. Endpoint cần có bean `Registration` trong Spring ApplicationContext.

Một endpoint quản trị chỉ an toàn khi đáp ứng đồng thời các yêu cầu:

1. Endpoint được bật và expose có chủ đích.
2. Request đi qua security filter chain thực tế.
3. Người gọi đã xác thực.
4. Người gọi có quyền phù hợp với thao tác đọc hoặc thay đổi trạng thái.
5. Request thay đổi trạng thái đáp ứng CSRF policy khi CSRF được bật.
6. Kiểm thử chứng minh người không đủ quyền không thể gây side effect.

Bài thuộc chương **Kiểm thử** của mô-đun **SPRING_CLOUD_CORE**. Mô-đun tập trung vào các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình ngoài, discovery, service registry, giao tiếp dịch vụ và kiểm thử, vận hành các abstraction chung.

Sau bài học, người học có thể:

- Phân biệt authentication, authorization, endpoint exposure và endpoint access.
- Bảo vệ endpoint quản trị bằng Spring Security.
- Phân quyền riêng cho thao tác đọc và ghi trạng thái service registry.
- Viết kiểm thử tích hợp với `MockMvc` hoặc `WebTestClient`.
- Kiểm tra các trường hợp anonymous, authenticated nhưng thiếu role, thiếu CSRF token và admin hợp lệ.
- Xác minh side effect đã xảy ra hoặc bị chặn.
- Nhận diện các lỗi khiến test vượt qua security filter mà không kiểm tra được bảo mật thật.

## 2. Endpoint Service Registry của Spring Cloud Commons

Spring Cloud Commons cung cấp endpoint Actuator có ID `serviceregistry`. Với cấu hình Actuator mặc định, base path là `/actuator`, nên URL thường dùng là:

```text
GET  /actuator/serviceregistry
POST /actuator/serviceregistry
```

Endpoint dựa trên bean `Registration` trong application context. GET trả về trạng thái registration. POST nhận JSON có trường `status` và yêu cầu `ServiceRegistry` implementation cập nhật trạng thái tương ứng.

Endpoint thao tác trên registration hiện tại được gắn với ứng dụng. Nó không phải API để truyền tùy ý service ID hoặc instance ID rồi cập nhật một registration bất kỳ trong registry. GET trả về status do provider cung cấp, thường là một chuỗi như `UP`; không nên giả định mọi provider có cùng tập status hoặc cùng response semantics.

Ví dụ request:

```http
POST /actuator/serviceregistry
Content-Type: application/json

{
  "status": "OUT_OF_SERVICE"
}
```

Với Eureka, thao tác này có thể đưa instance ra khỏi trạng thái phục vụ traffic trong lúc bảo trì. Khi dùng Consul, Zookeeper hoặc provider khác, cần kiểm tra status mà implementation hỗ trợ. Không giả định mọi provider hiểu cùng một chuỗi status.

Endpoint quản trị này có phạm vi tác động lớn hơn một API đọc thông tin. Một người có quyền POST có thể làm thay đổi trạng thái mà discovery client và load balancer sử dụng. Vì vậy, quyền cập nhật status thường nên giới hạn cho nhóm vận hành hoặc một service quản trị chuyên biệt.

### 2.1. Phân biệt endpoint ID và URL

`serviceregistry` là endpoint ID. URL HTTP được tạo từ management base path và ID:

```text
<management-base-path>/serviceregistry
```

Nếu thay `management.endpoints.web.base-path`, URL cũng thay đổi. Khi viết security rule, nên dùng `EndpointRequest.to("serviceregistry")` thay vì hard-code `/actuator/serviceregistry`. Matcher này gắn với endpoint ID và management base path của ứng dụng.

Một số tài liệu Spring Cloud cũ dùng `/service-registry` hoặc path con `instance-status`. Đối với Spring Cloud Commons hiện hành, endpoint ID được tài liệu hóa là `serviceregistry`; luôn đối chiếu release train đang chạy trước khi viết test path.

## 3. Bốn lớp cần kiểm tra

Không nên gộp mọi lỗi endpoint thành lỗi authentication. Một endpoint Actuator chịu ảnh hưởng của nhiều lớp độc lập:

| Lớp | Câu hỏi | Ví dụ cấu hình hoặc kiểm tra |
| --- | --- | --- |
| Endpoint availability | Endpoint có được tạo trong application context không? | Có `Registration` bean và `ServiceRegistry` implementation phù hợp. |
| Exposure | Endpoint có được công bố qua HTTP không? | `management.endpoints.web.exposure.include`. |
| Endpoint access | Endpoint có cho phép read/write operation không? | `management.endpoint.<id>.access` và `management.endpoints.access.default` ở các phiên bản hỗ trợ. |
| Authentication và authorization | Ai được gọi endpoint và họ được phép làm gì? | Spring Security, `SecurityFilterChain`, role hoặc authority. |

Các lớp này có ý nghĩa khác nhau:

- Endpoint không được expose thường không có HTTP mapping.
- Endpoint được expose nhưng không có `Registration` bean có thể không hoạt động hoặc trả 404 tùy cấu hình.
- Endpoint bị giới hạn access có thể không còn operation tương ứng.
- Request chưa xác thực thường nhận 401 với HTTP Basic.
- Request đã xác thực nhưng thiếu role thường nhận 403.
- POST thiếu CSRF token cũng có thể nhận 403 dù người gọi đã có role quản trị.

Khi test thất bại, hãy xác định lớp nào từ chối request trước khi kết luận security rule sai.

## 4. Expose endpoint có chủ đích

Spring Boot mặc định chỉ expose endpoint `health` qua HTTP. Quy tắc exposure qua JMX được cấu hình riêng và có thể rộng hơn. Muốn dùng Service Registry Actuator qua HTTP, cần thêm endpoint ID vào danh sách expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,serviceregistry
```

Không dùng `include: "*"` chỉ để bật một endpoint quản trị. Danh sách tường minh giúp tránh vô tình công bố `env`, `configprops`, `beans`, `heapdump`, `loggers` hoặc các endpoint khác chứa thông tin nhạy cảm hay có khả năng thay đổi hệ thống.

### 4.1. Endpoint access trong các phiên bản Spring Boot hỗ trợ access levels

Spring Boot có thể giới hạn access ở cấp endpoint. Ví dụ:

```yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,serviceregistry
  endpoint:
    health:
      access: read-only
    serviceregistry:
      access: unrestricted
```

Trong ví dụ, `serviceregistry` được phép cung cấp cả read operation và write operation ở lớp Actuator. Quyền gọi vẫn phải được kiểm soát bằng Spring Security.

Hai cơ chế không thay thế nhau:

- `access: unrestricted` không có nghĩa là anonymous user được phép gọi endpoint.
- Spring Security cho role `OPS_ADMIN` không làm write operation xuất hiện nếu Actuator đã giới hạn endpoint ở chế độ read-only.
- `management.endpoints.web.exposure.include` quyết định endpoint có được expose qua HTTP hay không; nó không cấp quyền cho người gọi.

Nếu ứng dụng dùng phiên bản Boot cũ không có access-level properties tương ứng, hãy dùng cơ chế enabled/exposure và security phù hợp với phiên bản đó. Không copy nguyên cấu hình của Boot 4 sang mọi phiên bản Boot 3.

## 5. Authentication và authorization

**Authentication** xác minh danh tính của người gọi. Ví dụ, request cung cấp HTTP Basic credentials hoặc bearer token hợp lệ.

**Authorization** quyết định danh tính đó có được phép thực hiện thao tác cụ thể hay không. Ví dụ, user đã đăng nhập nhưng chỉ có role `VIEWER` không được phép đổi trạng thái service registry.

Một policy có thể được mô tả như sau:

| Người gọi | GET status | POST đổi status |
| --- | --- | --- |
| Anonymous | Từ chối | Từ chối |
| User đã xác thực, role `VIEWER` | Từ chối | Từ chối |
| User đã xác thực, role `OPS_ADMIN` | Cho phép | Cho phép khi CSRF hợp lệ nếu CSRF đang bật |
| Service account có authority ghi riêng | Theo policy | Chỉ cho phép nếu có authority vận hành tương ứng |

Không nên mặc định rằng mọi user đã đăng nhập đều là quản trị viên. Việc kiểm tra authentication thành công không thay thế kiểm tra role/authority.

### 5.1. Role và authority

Với `hasRole("OPS_ADMIN")`, Spring Security kiểm tra authority `ROLE_OPS_ADMIN`. Khi dùng `User.withUsername(...).roles("OPS_ADMIN")`, Spring tự thêm tiền tố `ROLE_`.

Với OAuth2 Resource Server, policy có thể dựa trên scope hoặc authority, ví dụ:

```java
requestMatchers(EndpointRequest.to("serviceregistry"))
        .hasAuthority("SCOPE_registry.write")
```

Không viết `hasRole("ROLE_OPS_ADMIN")`: `hasRole` tự thêm tiền tố `ROLE_`. Nếu muốn kiểm tra chuỗi authority chính xác, dùng `hasAuthority`.

## 6. Bảo vệ endpoint bằng SecurityFilterChain

Ví dụ servlet-based với Spring Boot 4:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("serviceregistry"))
                    .hasRole("OPS_ADMIN")
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .anyRequest()
                    .authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Trong ví dụ:

- Chỉ user có role `OPS_ADMIN` mới truy cập endpoint `serviceregistry`.
- Health endpoint được phép truy cập công khai theo policy đã chọn.
- Các request còn lại cần xác thực.
- CSRF vẫn giữ mặc định của Spring Security vì không có cấu hình tắt CSRF.

Spring Boot 4 dùng package `org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest`. Với Spring Boot 3.x, package thường dùng là `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest`. Chọn import theo phiên bản thực tế của ứng dụng.

### 6.1. Vì sao cần chú ý khi khai báo nhiều SecurityFilterChain?

Khi ứng dụng tự khai báo một bean `SecurityFilterChain`, Spring Boot security auto-configuration lùi lại và để ứng dụng tự quản lý các access rule. Nếu tạo một chain chỉ match Actuator:

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
```

thì chain đó chỉ xử lý Actuator. Cần có một chain khác cho API và các URL còn lại, nếu không những request không match chain có thể không được bảo vệ như mong đợi.

Có thể dùng một chain bao phủ toàn ứng dụng như ví dụ ở trên, hoặc dùng nhiều chain với `@Order` và một fallback chain. Dù chọn cách nào, hãy kiểm thử cả endpoint quản trị và endpoint nghiệp vụ để phát hiện đường request bị bỏ lọt.

### 6.2. Dùng matcher theo endpoint ID

`EndpointRequest.to("serviceregistry")` phù hợp hơn kiểm tra chuỗi path thủ công:

- Tôn trọng `management.endpoints.web.base-path`.
- Match endpoint root và các subpath liên quan.
- Không bị buộc vào `/actuator` nếu ứng dụng đổi base path.
- Giữ security rule gắn với endpoint ID thay vì một URL có thể thay đổi.

Nếu dùng một management server port riêng, vẫn cần kiểm thử đường đi thực tế và network policy của management port. Security matcher không thay thế firewall hoặc network segmentation.

## 7. CSRF và thao tác POST

CSRF bảo vệ ứng dụng khỏi request thay đổi trạng thái được trình duyệt tự động gửi kèm cookie hoặc thông tin xác thực. Spring Security bật CSRF mặc định cho các ứng dụng servlet.

Do đó, request POST tới `serviceregistry` có thể bị từ chối với 403 khi thiếu CSRF token, kể cả khi user đã xác thực và có role `OPS_ADMIN`.

Trong kiểm thử, phải tách hai trường hợp:

1. User thiếu role: bị authorization từ chối.
2. User có role nhưng thiếu CSRF token: bị CSRF filter từ chối.

Không tắt CSRF toàn cục chỉ để test POST qua được. Nếu endpoint chỉ phục vụ machine-to-machine bằng bearer token stateless và không dùng cookie/session authentication, có thể thiết kế CSRF policy riêng sau khi đánh giá mô hình xác thực. Nếu dùng HTTP Basic hoặc session cookie, hãy xem xét nguy cơ CSRF và giữ bảo vệ phù hợp.

Spring Security Test cung cấp request post-processor `csrf()`:

```java
mockMvc.perform(post("/actuator/serviceregistry")
        .with(user("ops-admin").roles("OPS_ADMIN"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"OUT_OF_SERVICE\"}"));
```

Có thể dùng `csrf().asHeader()` nếu muốn mô phỏng token qua header. Cũng có thể kiểm thử token không hợp lệ bằng `csrf().useInvalidToken()`.

## 8. Chiến lược kiểm thử

Để kiểm tra endpoint quản trị đúng cách, nên có các lớp test:

| Loại test | Mục tiêu |
| --- | --- |
| Unit test policy | Xác minh mapping role/authority sang quyền đọc và ghi. |
| MVC security test | Xác minh filter chain trả đúng 401/403 và chặn side effect. |
| Actuator integration test | Xác minh endpoint thực sự được tạo, expose và gọi được. |
| Provider integration test | Xác minh status được chuyển tới Eureka/Consul/Zookeeper theo contract provider. |
| Network test | Xác minh management port, firewall, proxy và TLS ở môi trường triển khai. |

`@SpringBootTest` kết hợp `@AutoConfigureMockMvc` phù hợp khi muốn kiểm tra cả Actuator endpoint và Spring Security trong một application context. `MockMvc` chạy request qua MVC và security filters mà không cần mở socket thật.

Với kiểm thử WebFlux, dùng `WebTestClient` cùng `SecurityWebFilterChain`. Nếu cần kiểm tra hành vi của servlet container, proxy, TLS termination hoặc management port tách biệt, bổ sung test chạy server thật bằng `RANDOM_PORT`.

### 8.1. Dependency kiểm thử

Với Gradle, các dependency thường cần gồm:

```groovy
testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.security:spring-security-test")
```

Dùng Spring Boot BOM/plugin để quản lý version. Với Spring Boot 4, package của một số test auto-configuration đã được tách theo module; ví dụ `@AutoConfigureMockMvc` thuộc `org.springframework.boot.webmvc.test.autoconfigure`. Với Boot 3.x, import thường là `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`.

Không dùng `@AutoConfigureMockMvc(addFilters = false)` trong test bảo mật. Thuộc tính này loại security filters khỏi MockMvc và làm test không còn kiểm tra đường bảo vệ thật.

## 9. Kiểm thử bằng MockMvc

Ví dụ sau giả định:

- Ứng dụng có `ServiceRegistry` và `Registration` bean trong context.
- Endpoint được expose qua HTTP.
- Security configuration đã giới hạn `serviceregistry` cho role `OPS_ADMIN`.
- HTTP Basic được cấu hình để xác thực user vận hành.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,serviceregistry",
        "spring.security.user.name=ops-admin",
        "spring.security.user.password=test-secret",
        "spring.security.user.roles=OPS_ADMIN"
})
@AutoConfigureMockMvc
@Import(RegistryEndpointTestConfiguration.class)
class ServiceRegistryEndpointSecurityTests {

    private static final String ENDPOINT = "/actuator/serviceregistry";

    @Autowired
    MockMvc mockMvc;

    @Autowired
    InMemoryServiceRegistry registry;

    @BeforeEach
    void resetRegistryStatus() {
        registry.reset();
    }

    @Test
    void anonymousUserCannotReadRegistryStatus() throws Exception {
        mockMvc.perform(get(ENDPOINT)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousUserCannotPostEvenWithValidCsrfToken() throws Exception {
        String before = registry.currentStatus();

        mockMvc.perform(post(ENDPOINT)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isUnauthorized());

        assertThat(registry.currentStatus()).isEqualTo(before);
    }

    @Test
    void authenticatedUserWithoutOperationsRoleCannotReadStatus() throws Exception {
        mockMvc.perform(get(ENDPOINT)
                        .with(user("viewer").roles("VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void operationsAdminCanReadStatusUsingHttpBasic() throws Exception {
        mockMvc.perform(get(ENDPOINT)
                        .with(httpBasic("ops-admin", "test-secret"))
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("UP")));
    }

    @Test
    void operationsAdminCannotPostWithoutCsrfToken() throws Exception {
        String before = registry.currentStatus();

        mockMvc.perform(post(ENDPOINT)
                        .with(user("ops-admin").roles("OPS_ADMIN"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isForbidden());

        assertThat(registry.currentStatus()).isEqualTo(before);
    }

    @Test
    void operationsAdminCanPostWithValidCsrfToken() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                        .with(user("ops-admin").roles("OPS_ADMIN"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().is2xxSuccessful());

        assertThat(registry.currentStatus()).isEqualTo("OUT_OF_SERVICE");
    }

    @Test
    void viewerCannotPostEvenWithValidCsrfToken() throws Exception {
        String before = registry.currentStatus();

        mockMvc.perform(post(ENDPOINT)
                        .with(user("viewer").roles("VIEWER"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isForbidden());

        assertThat(registry.currentStatus()).isEqualTo(before);
    }
}
```

Trong test này:

- `httpBasic(...)` kiểm tra authentication bằng HTTP Basic credentials.
- `user(...)` tạo một principal đã xác thực để kiểm tra authorization mà không cần kiểm tra password.
- `csrf()` thêm CSRF token hợp lệ cho request POST.
- Test admin POST thành công cần xác minh thêm trạng thái registry đã đổi; chỉ assert 2xx chưa đủ để chứng minh side effect đúng.

Ví dụ test fixture có thể inject `ServiceRegistry` giả lập để kiểm tra trạng thái sau POST. Khi dùng registry thật, hãy kiểm tra status bằng API/provider test tương ứng và khôi phục status sau mỗi test.

### 9.1. Fake registry cho test cô lập

Khi muốn test endpoint và security mà không phụ thuộc Eureka hoặc Consul đang chạy, có thể dùng test-only Registration và ServiceRegistry. Các import sau đặt ở đầu file test:

```java
import java.net.URI;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;
import org.springframework.context.annotation.Bean;
```

Test configuration đăng ký một registration và registry giả:

```java
@TestConfiguration(proxyBeanMethods = false)
class RegistryEndpointTestConfiguration {

    @Bean
    TestRegistration registration() {
        return new TestRegistration();
    }

    @Bean
    InMemoryServiceRegistry serviceRegistry() {
        return new InMemoryServiceRegistry();
    }
}
```

Khai báo registration giả làm lớp package-private ở cùng test source file:

```java
final class TestRegistration implements Registration {

    @Override
    public String getInstanceId() {
        return "catalog-test-1";
    }

    @Override
    public String getServiceId() {
        return "catalog-service";
    }

    @Override
    public String getHost() {
        return "127.0.0.1";
    }

    @Override
    public int getPort() {
        return 8080;
    }

    @Override
    public boolean isSecure() {
        return false;
    }

    @Override
    public URI getUri() {
        return URI.create("http://127.0.0.1:8080");
    }

    @Override
    public Map<String, String> getMetadata() {
        return Map.of();
    }
}
```

Registry giả có thể lưu status trong `AtomicReference<String>`:

```java
final class InMemoryServiceRegistry
        implements ServiceRegistry<TestRegistration> {

    private final AtomicReference<String> status =
            new AtomicReference<>("UP");

    @Override
    public void register(TestRegistration registration) {
    }

    @Override
    public void deregister(TestRegistration registration) {
    }

    @Override
    public void close() {
    }

    @Override
    public void setStatus(TestRegistration registration, String newStatus) {
        status.set(newStatus);
    }

    @SuppressWarnings("unchecked")
    @Override
    public <T> T getStatus(TestRegistration registration) {
        return (T) status.get();
    }

    String currentStatus() {
        return status.get();
    }

    void reset() {
        status.set("UP");
    }
}
```

Đăng ký hai bean này trong `@TestConfiguration` được import vào test context như ví dụ ở trên. Khi test POST thành công, có thể inject `InMemoryServiceRegistry` và assert `currentStatus()` bằng giá trị mong đợi.

Ví dụ assertion:

```java
assertThat(registry.currentStatus()).isEqualTo("OUT_OF_SERVICE");
```

Đây là test cô lập endpoint adapter và security. Nó không xác minh Eureka/Consul thật lưu status như thế nào. Không đưa fake registry vào component scan production; giữ fixture trong test source set.

Nếu ứng dụng đang có discovery provider trên classpath, tránh để test fixture và provider cùng tạo nhiều `ServiceRegistry` bean không rõ ràng. Dùng test application context riêng hoặc cấu hình test loại provider integration khỏi context.

## 10. Kiểm thử theo ma trận quyền

Một ma trận rõ ràng giúp tránh chỉ test trường hợp admin thành công:

| Request | Principal | CSRF | Kết quả mong đợi |
| --- | --- | --- | --- |
| GET status | Anonymous | Không áp dụng | 401 |
| GET status | `VIEWER` | Không áp dụng | 403 |
| GET status | `OPS_ADMIN` | Không áp dụng | 200 |
| POST status | Anonymous | Thiếu/không hợp lệ | 403 do CSRF filter |
| POST status | Anonymous | Hợp lệ | 401 do chưa xác thực |
| POST status | `VIEWER` | Hợp lệ | 403 |
| POST status | `OPS_ADMIN` | Thiếu | 403 |
| POST status | `OPS_ADMIN` | Không hợp lệ | 403 |
| POST status | `OPS_ADMIN` | Hợp lệ | 2xx và status được cập nhật |

Các status code có thể khác nếu ứng dụng dùng OAuth2 entry point, gateway hoặc custom exception handler. Điều cần giữ là request không có quyền không được thực hiện side effect.

### 10.1. Kiểm thử cả trạng thái trước và sau POST

Một test thay đổi status nên xác minh:

1. Trạng thái ban đầu của registration.
2. Request POST có đúng JSON field `status`.
3. HTTP response thành công.
4. `ServiceRegistry` nhận status mới.
5. GET tiếp theo trả status mới hoặc provider API xác nhận status mới.
6. Test dọn trạng thái sau khi chạy để không ảnh hưởng test khác.

Với Eureka, có thể dùng `OUT_OF_SERVICE` làm giá trị ví dụ. Với provider khác, dùng trạng thái được implementation đó hỗ trợ.

### 10.2. Kiểm thử rằng request bị từ chối không làm thay đổi registry

Đối với anonymous, viewer hoặc request thiếu CSRF, không chỉ assert 401/403. Hãy assert status registry vẫn giữ nguyên:

```java
String before = registry.currentStatus();

mockMvc.perform(post(ENDPOINT)
        .with(user("viewer").roles("VIEWER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
    .andExpect(status().isForbidden());

assertThat(registry.currentStatus()).isEqualTo(before);
```

Assertion này phát hiện lỗi nghiêm trọng: security trả response lỗi nhưng logic cập nhật status vẫn chạy do một đường xử lý khác hoặc side effect được kích hoạt trước khi authorization hoàn tất.

## 11. Kiểm thử OAuth2 Resource Server

Nếu endpoint dùng bearer token thay vì HTTP Basic, authorization có thể dựa trên scope hoặc authority:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(EndpointRequest.to("serviceregistry"))
            .hasAuthority("SCOPE_registry.write")
        .anyRequest()
            .authenticated());
```

Với MockMvc, Spring Security Test có request post-processor `jwt()` để tạo một JWT authentication giả lập:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(post(ENDPOINT)
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_registry.write")))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
    .andExpect(status().is2xxSuccessful());
```

`jwt()` hữu ích để kiểm thử authorization sau khi token đã được xác thực. Nó không chứng minh JWT thật có chữ ký hợp lệ, issuer đúng, audience đúng hoặc decoder được cấu hình đúng. Các kiểm tra token thực tế cần test riêng cho `JwtDecoder`, issuer/JWK hoặc môi trường identity provider.

Nếu resource server là stateless và chỉ nhận bearer token trong Authorization header, CSRF policy có thể khác so với ứng dụng dùng session cookie. Hãy cấu hình và kiểm thử theo cơ chế xác thực thực tế; không dùng test `jwt()` làm lý do tắt CSRF cho toàn bộ ứng dụng.

## 12. Kiểm thử WebFlux với WebTestClient

Ứng dụng reactive dùng `SecurityWebFilterChain` và `ServerHttpSecurity` thay cho servlet `SecurityFilterChain` và `HttpSecurity`. Có thể dùng `WebTestClient` để gửi request qua reactive security chain.

Ví dụ security rule tương ứng với Spring Boot 4:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.reactive.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
class ReactiveManagementSecurityConfiguration {

    @Bean
    SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
        return http.authorizeExchange(exchange -> exchange
                        .matchers(EndpointRequest.to("serviceregistry"))
                            .hasRole("OPS_ADMIN")
                        .anyExchange()
                            .authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Với Spring Boot 3.x, class reactive matcher là `org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest`. Kiểm tra import theo phiên bản đang dùng.

Ví dụ kiểm tra một request GET:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveManagementSecurityTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void anonymousUserCannotReadRegistryStatus() {
        webTestClient.get()
                .uri("/actuator/serviceregistry")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Ví dụ dùng package `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient` của Boot 4. Với Boot 3.x, annotation thường thuộc package `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`.

Với test authorization, dùng Spring Security reactive test support để cung cấp principal/authority. Với POST khi CSRF đang bật, dùng `SecurityMockServerConfigurers.csrf()` để gửi token hợp lệ và có test riêng cho token thiếu hoặc không hợp lệ.

Đừng thay `WebTestClient` bằng test gọi trực tiếp `ServiceRegistryEndpoint` nếu mục tiêu là xác minh security web filter. Gọi method trực tiếp sẽ bỏ qua đường HTTP và lớp bảo mật.

## 13. Mock test và test server thật

`MockMvc` và `WebTestClient` trong mock environment phù hợp để kiểm tra:

- Request matcher.
- Authentication và authorization.
- CSRF.
- JSON body và response status.
- Side effect trong bean `ServiceRegistry`.

Chúng không chứng minh:

- Management port có mở đúng network interface hay không.
- Firewall hoặc ingress có chặn truy cập không mong muốn hay không.
- TLS certificate, hostname verification và reverse proxy hoạt động đúng.
- Management server port riêng có được bảo vệ giống application port hay không.
- Registry bên ngoài thực sự chấp nhận trạng thái mới.

Với các yêu cầu trên, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc test environment chạy server thật, sau đó gửi HTTP request qua đúng management address. Nếu `management.server.port` khác `server.port`, phải gửi request tới management port.

## 14. Các lỗi kiểm thử thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| GET trả 404 | Endpoint chưa expose, chưa có Registration bean hoặc sai base path/endpoint ID | Kiểm tra endpoint availability, `management.endpoints.web.exposure.include` và `/serviceregistry`. |
| GET trả 401 | Request chưa xác thực hoặc credentials sai | Kiểm tra AuthenticationEntryPoint và HTTP Basic/bearer token. |
| GET trả 403 | User đã xác thực nhưng thiếu role/authority | Kiểm tra role prefix, scope mapping và request matcher. |
| POST trả 403 dù user là admin | CSRF token thiếu/sai hoặc authorization không khớp | Phân biệt CSRF rejection với access-denied; dùng `csrf()` trong test hợp lệ. |
| POST trả 404/405 | Endpoint access bị giới hạn read-only hoặc write operation không khả dụng | Kiểm tra endpoint access level và phiên bản Boot. |
| Test security pass nhưng production không an toàn | MockMvc không chạy security filter hoặc cấu hình production khác test | Giữ filters, dùng context production-like và test server thật khi cần. |
| Test chỉ kiểm tra 2xx | Không xác minh trạng thái registry đã đổi | Assert side effect trong fake registry hoặc đọc lại provider. |
| Custom SecurityFilterChain làm API khác mất bảo vệ | Boot default security đã back off và chain không có rule fallback | Bao phủ toàn ứng dụng hoặc thêm chain fallback có `@Order`. |
| Test `user()` pass nhưng Basic login lỗi | Request post-processor giả lập principal, không kiểm tra credential store | Bổ sung test với `httpBasic()` và user thật trong test configuration. |
| Endpoint admin truy cập được qua public ingress | Chỉ kiểm tra role trong app, chưa giới hạn network exposure | Tách management port, firewall, ingress rule và xác minh từ network ngoài. |

## 15. Quy trình kiểm thử đề xuất

1. Xác nhận endpoint ID, URL và provider đang sử dụng.
2. Xác nhận application context có `Registration` và `ServiceRegistry` bean.
3. Chỉ expose `health` và endpoint quản trị thực sự cần thiết.
4. Xác định endpoint access có cho phép write operation không.
5. Viết policy phân biệt role đọc và role thay đổi trạng thái.
6. Xác minh `SecurityFilterChain` bảo vệ cả endpoint quản trị lẫn các URL ứng dụng khác.
7. Test anonymous, authenticated-without-role và admin.
8. Test POST với CSRF thiếu, sai và hợp lệ.
9. Assert request bị từ chối không làm thay đổi status.
10. Assert admin POST cập nhật đúng status theo provider.
11. Test bearer token hoặc Basic credentials thật theo cơ chế authentication đang dùng.
12. Bổ sung test server thật cho management port, TLS, proxy và network policy.

## 16. Câu hỏi tự kiểm tra

1. Endpoint `serviceregistry` của Spring Cloud Commons thực hiện thao tác gì qua GET và POST?
2. Vì sao endpoint phải có `Registration` bean trong application context?
3. Endpoint exposure khác endpoint access ở điểm nào?
4. Authentication khác authorization như thế nào?
5. Vì sao user đã xác thực nhưng thiếu role vẫn phải nhận 403?
6. Tại sao POST có thể bị CSRF filter từ chối dù user có role quản trị?
7. Vì sao nên dùng `EndpointRequest.to("serviceregistry")` thay vì hard-code `/actuator/serviceregistry`?
8. Khi khai báo custom `SecurityFilterChain`, điều gì xảy ra với security auto-configuration của Spring Boot?
9. Vì sao test dùng `user()` không thay thế test xác thực HTTP Basic hoặc JWT thật?
10. Làm thế nào chứng minh request bị từ chối không làm thay đổi trạng thái trong service registry?

## 17. Tài liệu tham khảo chính thức

- [Spring Cloud Commons 5.0.4 — Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons 5.0.2 — ServiceRegistryEndpoint API](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/endpoint/ServiceRegistryEndpoint.html)
- [Spring Boot — Actuator Endpoints and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Spring Security and EndpointRequest](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot 4 — Servlet EndpointRequest API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/servlet/EndpointRequest.html)
- [Spring Boot 4 — Reactive EndpointRequest API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/reactive/EndpointRequest.html)
- [Spring Boot 4 — AutoConfigureWebTestClient API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/webtestclient/autoconfigure/AutoConfigureWebTestClient.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Security — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)

Đường dẫn, package import và endpoint access properties thay đổi theo phiên bản Spring Boot/Spring Cloud. Hãy kiểm tra tài liệu đúng release train; giữ kiểm thử gắn với `EndpointRequest` và contract của provider thay vì phụ thuộc vào URL hoặc status riêng của một phiên bản cũ.
