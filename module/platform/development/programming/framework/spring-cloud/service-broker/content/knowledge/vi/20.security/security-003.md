# Cấu hình Spring Security cho Spring MVC hoặc Spring WebFlux

Service broker cung cấp các endpoint HTTP theo Open Service Broker API (OSB API), chẳng hạn `GET /v2/catalog`, provision service instance, update, bind, unbind và deprovision. Những endpoint này được platform gọi bằng cơ chế xác thực machine-to-machine đã cấu hình khi đăng ký broker. Spring Security cần xác thực platform, kiểm tra quyền gọi API và bảo vệ các endpoint quản trị, trong khi vẫn giữ đúng hợp đồng HTTP mà OSB API yêu cầu.

Với `SPRING_CLOUD_SERVICE_BROKER`, có hai cách triển khai web phổ biến: Spring MVC chạy trên Servlet stack và Spring WebFlux chạy trên reactive stack. Cả hai đều dùng Spring Security nhưng cấu hình filter chain và kiểu authentication khác nhau. Ứng dụng cần chọn cấu hình khớp với web stack đang chạy; không đăng ký đồng thời hai cấu hình như thể chúng thay thế được cho nhau. Bài này trình bày hai phương án riêng để bảo vệ OSB API, credential của broker, Actuator và các endpoint nội bộ.

## 1. Xác định ranh giới bảo mật của broker

Trước khi viết cấu hình, hãy xác định các nhóm endpoint và caller:

| Nhóm endpoint | Caller dự kiến | Chính sách |
|---|---|---|
| `/v2/**` | Cloud platform hoặc OSB client đã đăng ký | Xác thực broker client; chỉ cho phép các thao tác thuộc hợp đồng OSB API. |
| `/actuator/health` | Load balancer/orchestrator hoặc hệ thống giám sát | Chỉ công khai thông tin health tối thiểu nếu cần. |
| Actuator còn lại | Operator hoặc hệ thống monitoring được ủy quyền | Giới hạn theo role, mạng quản trị hoặc management port riêng. |
| `/admin/**` hoặc API nội bộ | Operator/service nội bộ | Xác thực riêng, phân quyền rõ ràng và audit. |
| Static/UI endpoint (nếu có) | Người vận hành qua browser | Có thể dùng session, form login và CSRF theo nhu cầu ứng dụng. |

Không mặc định toàn bộ ứng dụng chỉ có OSB API. Nếu có trang quản trị, actuator hoặc API nội bộ, cần tách quy tắc bảo mật để cấu hình cho OSB không vô tình mở các endpoint còn lại.

## 2. OSB API và cơ chế xác thực

OSB API định nghĩa giao thức và các thao tác broker, còn cách platform xác thực với broker phụ thuộc cấu hình tích hợp. Một mô hình phổ biến là HTTP Basic Authentication qua TLS; một số môi trường có thể đặt reverse proxy, mTLS hoặc cơ chế xác thực khác theo khả năng platform và broker.

Các nguyên tắc cần giữ:

- Chỉ nhận request từ platform/client được đăng ký và xác thực.
- Truyền credential qua HTTPS/TLS; không gửi Basic credentials qua HTTP thuần.
- Mỗi platform hoặc môi trường nên có credential riêng để có thể thu hồi/rotate độc lập.
- Lưu credential trong secret manager hoặc secret store của môi trường triển khai, không hardcode trong source code hay commit vào YAML.
- Không log `Authorization`, cookie, token hoặc request header nhạy cảm.
- Xác thực broker client không thay thế kiểm tra quyền ở cấp service instance, tenant hoặc binding.

Ví dụ request dùng Basic Authentication:

```http
GET /v2/catalog HTTP/1.1
Host: broker.example.internal
X-Broker-API-Version: 2.14
Authorization: Basic <base64-credentials>
Accept: application/json
```

Base64 chỉ là encoding, không phải mã hóa. TLS bảo vệ dữ liệu trên đường truyền; Spring Security xác minh thông tin xác thực ở phía server.

## 3. Chọn đúng web stack: MVC hay WebFlux

Spring MVC chạy trên Servlet API và dùng `SecurityFilterChain` cùng `HttpSecurity`. Spring WebFlux dùng reactive runtime và cấu hình bằng `SecurityWebFilterChain` cùng `ServerHttpSecurity`.

| Thành phần | Spring MVC | Spring WebFlux |
|---|---|---|
| Runtime | Servlet container | Reactive server (ví dụ Reactor Netty) |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Configurer | `HttpSecurity` | `ServerHttpSecurity` |
| Authorization DSL | `authorizeHttpRequests` | `authorizeExchange` |
| User details | `UserDetailsService` | `ReactiveUserDetailsService` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Kiểm thử HTTP | MockMvc | WebTestClient |

Kiểu dependency và auto-configuration quyết định web application thực tế chạy theo stack nào. Không trộn `HttpSecurity` với `ServerHttpSecurity`, không dùng Servlet filter cho WebFlux và không dùng reactive security chain cho ứng dụng MVC thuần. Nếu dự án có cả hai starter do dependency kéo theo, cần kiểm tra loại application context mà Spring Boot khởi tạo.

## 4. Cấu hình Spring Security cho Spring MVC

Với Spring MVC, tạo một `SecurityFilterChain` bảo vệ toàn bộ OSB API. Ví dụ sau dùng HTTP Basic để minh họa; credential thực tế cần lấy từ nguồn cấu hình bảo mật và user store phù hợp.

```java
@Configuration
@EnableWebSecurity
public class OsbMvcSecurityConfiguration {

    @Bean
    SecurityFilterChain osbApiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/v2/**")
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

Đoạn cấu hình trên có ý nghĩa:

- `securityMatcher("/v2/**")` giới hạn chain vào các endpoint OSB API.
- `anyRequest().authenticated()` yêu cầu mọi request trong chain đã xác thực.
- `httpBasic(...)` bật Basic Authentication cho platform nếu đó là cơ chế đã cấu hình.
- `STATELESS` không tạo session HTTP để lưu trạng thái đăng nhập.
- CSRF được tắt trong chain API machine-to-machine này; chỉ làm vậy khi endpoint không dựa vào cookie/session hoặc browser ambient credentials. Nếu API có thể được gọi bằng credential tự động gửi từ browser, phải đánh giá lại CSRF hoặc dùng cơ chế bảo vệ phù hợp.

Nếu ứng dụng có UI quản trị, tạo chain riêng cho UI và giữ CSRF theo yêu cầu của session-based browser flow. Không tắt CSRF toàn cục cho toàn ứng dụng chỉ vì OSB API là machine-to-machine.

### Cấu hình user và password encoder

Không lưu password dạng rõ hoặc dùng password hardcode. Spring Security nên so sánh password đã được mã hóa bằng `PasswordEncoder` với giá trị lấy từ secret store hoặc kho credential đã bảo vệ.

Ví dụ cấu trúc cho một broker client:

```java
@Configuration
public class BrokerClientAuthenticationConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService brokerUsers(BrokerCredentialRepository repository) {
        return username -> repository.findActiveByUsername(username)
                .map(credential -> User.withUsername(credential.username())
                        .password(credential.passwordHash())
                        .roles("BROKER_PLATFORM")
                        .disabled(!credential.active())
                        .build())
                .orElseThrow(() -> new UsernameNotFoundException("Invalid broker credentials"));
    }
}
```

`BrokerCredentialRepository` là thành phần domain do ứng dụng định nghĩa. Bản ghi chỉ nên lưu password hash hoặc reference tới secret store, trạng thái active, thời điểm hết hạn và metadata rotation. Không lưu password thô để tiện so sánh.

Nếu cần nhiều platform credentials, mỗi credential nên có username/client ID riêng và quyền được cấp phù hợp. Khi rotate, có thể cho phép giai đoạn chuyển tiếp ngắn với hai credential hợp lệ, sau đó revoke credential cũ.

## 5. Cấu hình chain riêng cho UI và actuator trong MVC

Nếu cùng ứng dụng có endpoint quản trị, không để fallback chain vô tình cho phép anonymous truy cập. Có thể tạo chain ưu tiên cho OSB, chain cho actuator và chain cuối cho các endpoint còn lại.

```java
@Configuration
@EnableWebSecurity
public class ApplicationSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain osbChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/v2/**")
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/actuator/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
                .build();
    }
}
```

Đây là ví dụ minh họa. Các chain dùng chung authentication provider/user store phù hợp với cấu hình ứng dụng. Nếu actuator chạy trên management port hoặc management context riêng, cấu hình thực tế có thể cần được đặt trong context tương ứng. Không công khai toàn bộ actuator chỉ vì `/actuator/health` cần được load balancer truy cập.

## 6. Cấu hình Spring Security cho Spring WebFlux

Với WebFlux, dùng `SecurityWebFilterChain` và `ServerHttpSecurity`. Không khai báo `SecurityFilterChain` Servlet cho reactive endpoint.

```java
@Configuration
@EnableWebFluxSecurity
public class OsbWebFluxSecurityConfiguration {

    @Bean
    SecurityWebFilterChain osbApiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/v2/**").authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance()
                )
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
```

Trong ví dụ này:

- `authorizeExchange` áp dụng authorization theo reactive exchange.
- `pathMatchers("/v2/**").authenticated()` bảo vệ endpoint OSB.
- `anyExchange().denyAll()` từ chối các route chưa được khai báo trong chain này.
- `NoOpServerSecurityContextRepository` tránh lưu security context trong session server-side.
- CSRF chỉ được tắt khi chain dành cho API machine-to-machine không dùng cookie/session authentication; nếu có browser flow, cần cấu hình CSRF riêng.

Nếu ứng dụng WebFlux có nhiều nhóm endpoint, nên tạo security chain có matcher/ordering rõ ràng hoặc khai báo path authorization cụ thể. Không dùng một rule `permitAll()` rộng cho `/v2/**` để sửa lỗi tích hợp.

### Reactive user details

WebFlux dùng `ReactiveUserDetailsService` và reactive authentication provider. Ví dụ:

```java
@Configuration
public class ReactiveBrokerAuthenticationConfiguration {

    @Bean
    MapReactiveUserDetailsService brokerUsers(PasswordEncoder passwordEncoder) {
        UserDetails platform = User.withUsername("platform-client")
                .password(passwordEncoder.encode("<load-from-secret-store>"))
                .roles("BROKER_PLATFORM")
                .build();

        return new MapReactiveUserDetailsService(platform);
    }
}
```

Đây chỉ là ví dụ cấu trúc cho môi trường phát triển. Không để placeholder hoặc password literal trong source khi triển khai. Với production, dùng reactive repository/identity store hoặc authentication manager phù hợp; không dùng in-memory user store làm kho credential production.

Nếu repository dùng JDBC blocking, không gọi trực tiếp trên event loop. Chọn R2DBC hoặc cô lập thao tác blocking trên scheduler phù hợp. Reactive API không tự làm cho password lookup hoặc provider call trở thành non-blocking.

## 7. Phân quyền: authentication không đủ

Authentication trả lời câu hỏi “caller là ai?”. Authorization trả lời “caller được phép làm gì?”. Sau khi platform xác thực thành công, broker vẫn cần kiểm tra quyền trên từng service instance và binding.

Ví dụ các lớp kiểm tra:

- Broker client có quyền gọi OSB API.
- Request tham chiếu đúng service ID và plan ID đã provision.
- Instance thuộc đúng organization/space hoặc tenant context đã xác thực.
- Binding ID thuộc đúng instance và consumer.
- Instance đang ở trạng thái cho phép update, bind hoặc deprovision.
- Operation quản trị chỉ dành cho role phù hợp.

Không dùng `hasRole("BROKER_PLATFORM")` như bằng chứng caller được truy cập mọi instance. Nếu có nhiều platform hoặc tenant, lưu principal/client ID và scope trong security context, sau đó kiểm tra ownership của resource trong service layer.

Có thể bật method security cho các service nghiệp vụ:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Ví dụ method authorization cho API quản trị nội bộ:

```java
@PreAuthorize("hasRole('OPS')")
public Mono<BrokerOperation> retryFailedOperation(String operationId) {
    return operationService.retry(operationId);
}
```

Method security là lớp bảo vệ bổ sung. Service vẫn cần kiểm tra operation thuộc phạm vi operator được phép quản lý và ghi audit khi thực hiện retry.

## 8. CSRF và CORS cho OSB API

CSRF và CORS giải quyết hai vấn đề khác nhau:

- **CSRF** bảo vệ ứng dụng khỏi request giả mạo được browser gửi kèm credential tự động, thường liên quan cookie/session hoặc cơ chế xác thực ambient.
- **CORS** là chính sách browser kiểm soát JavaScript từ origin khác có được đọc response hay gửi một số loại request hay không. CORS không phải cơ chế xác thực caller.

OSB API thường được platform gọi server-to-server, không phải JavaScript chạy trong browser. Vì vậy, một chain riêng cho OSB có thể không cần CSRF token nếu dùng credential machine-to-machine, không dựa vào cookie/session và không mở flow đăng nhập browser. Nếu cùng host có UI quản trị hoặc Basic credentials có thể được browser tự động gửi, phải xem xét CSRF theo mô hình thực tế; không tắt CSRF toàn ứng dụng theo thói quen.

CORS thường có thể giữ tắt cho OSB API nếu không có browser client hợp lệ cần gọi trực tiếp. Nếu cần bật, chỉ allowlist origin, method và header thực sự cần thiết. Không dùng wildcard origin cùng credentials. Không cho phép mọi origin chỉ để khắc phục lỗi từ browser console.

## 9. Bảo vệ endpoint OSB và xử lý HTTP error

Security filter chạy trước controller/service. Nếu caller chưa xác thực, Spring Security thường trả `401 Unauthorized`; nếu caller đã xác thực nhưng không có quyền, trả `403 Forbidden`. Các status/body cần tương thích với contract và cách platform tích hợp broker.

Các nguyên tắc:

- Không chuyển lỗi xác thực thành `200 OK` với body báo lỗi.
- Không trả stack trace, password hash, username enumeration hoặc chi tiết identity store trong response.
- Không để exception handler toàn cục ghi đè response `401/403` của Spring Security hoặc error mapping OSB.
- Nếu platform cần JSON error body theo quy ước riêng, cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` có kiểm soát, rồi kiểm thử qua endpoint thật.
- Không giả định mọi OSB client xử lý challenge Basic hoặc error body giống nhau; kiểm tra behavior platform mục tiêu.

Ví dụ handler MVC trả body tối thiểu:

```java
@Component
public class OsbAuthenticationEntryPoint implements AuthenticationEntryPoint {
    @Override
    public void commence(HttpServletRequest request,
                         HttpServletResponse response,
                         AuthenticationException exception) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(
                "{\"description\":\"Broker authentication is required.\"}"
        );
    }
}
```

Đây là ví dụ cho Servlet stack; cần đăng ký entry point trong đúng chain và bảo đảm JSON literal được escape/serialize an toàn. Nếu dùng Spring Cloud Open Service Broker error model, hãy kiểm tra response thực tế để không phá hợp đồng lỗi của framework. Với WebFlux, dùng `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`, không dùng Servlet interfaces.

## 10. Bảo vệ credential và cấu hình môi trường

Credential broker và credential dùng để gọi provider là hai loại secret khác nhau:

| Secret | Dùng cho | Vị trí quản lý |
|---|---|---|
| Broker client credential | Platform xác thực với broker | Secret store/configuration được bảo vệ của broker. |
| Provider API credential | Broker gọi cloud/database provider | Secret manager hoặc workload identity; scope quyền tối thiểu. |
| Binding credential | Ứng dụng consumer kết nối service | Secret store hoặc kho credential có encryption và lifecycle riêng. |
| Signing/encryption key | Ký token hoặc mã hóa dữ liệu | Key management service/HSM hoặc secret store chuyên dụng. |

Không dùng chung một password cho broker API và provider admin. Không đặt secret trong `application.yml` được commit, Docker image, command line argument hoặc log startup. Nếu dùng environment variable, bảo vệ quyền đọc process/environment và ưu tiên tích hợp secret manager theo nền tảng.

Credential cần có quy trình rotation:

1. Tạo credential mới và cập nhật platform/secret store theo kế hoạch.
2. Có giai đoạn chuyển tiếp nếu platform hỗ trợ hai credential.
3. Theo dõi xác thực thành công bằng credential mới.
4. Thu hồi credential cũ.
5. Ghi audit event không chứa giá trị secret.

## 11. TLS, reverse proxy và mạng quản trị

Spring Security xác thực request ở ứng dụng, nhưng TLS có thể được kết thúc tại ingress, load balancer hoặc reverse proxy. Cần bảo đảm:

- Kết nối từ platform tới edge dùng TLS với chứng chỉ hợp lệ.
- Nếu TLS terminate tại proxy, kết nối proxy tới broker cũng được bảo vệ theo threat model.
- Broker chỉ tin forwarded headers từ proxy đáng tin cậy; không chấp nhận `X-Forwarded-Proto` hoặc client IP do Internet client tự gửi.
- Không expose management port hoặc actuator ra mạng public nếu không cần.
- Network policy/firewall chỉ cho phép platform và thành phần vận hành cần thiết truy cập broker.
- Không để endpoint provider nội bộ hoặc database admin được truy cập qua OSB API ngoài ý muốn.

Nếu ứng dụng cần biết request gốc là HTTPS sau proxy, cấu hình forwarded-header strategy đúng với kiến trúc. Không dùng header do client tùy ý gửi để quyết định bỏ qua TLS hoặc authorization.

## 12. Actuator và endpoint quản trị

Actuator có thể cung cấp health, metrics, env, beans, mappings, loggers và các thông tin nhạy cảm khác tùy endpoint được expose. Chỉ expose những endpoint thật sự cần.

Ví dụ cấu hình giới hạn exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Các property và endpoint có sẵn tùy Spring Boot version/dependency. Dù đã giới hạn exposure, vẫn cần security chain hoặc management network/port phù hợp. Không expose `env`, `configprops`, `heapdump`, `loggers` hoặc endpoint thay đổi runtime cho mạng public nếu không có nhu cầu và kiểm soát chặt.

`/actuator/health` có thể được phép truy cập bởi load balancer nếu response chỉ chứa trạng thái tối thiểu. Health detail và thông tin provider/database nên yêu cầu role quản trị hoặc chỉ có trên management network.

## 13. Kiểm thử Spring MVC bằng MockMvc

Với MVC, dùng `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` hoặc test slice phù hợp để kiểm tra security filter thực tế.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OsbMvcSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void catalogRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/v2/catalog"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedPlatformCanReadCatalog() throws Exception {
        mockMvc.perform(get("/v2/catalog")
                        .with(httpBasic("platform-client", "test-password")))
                .andExpect(status().isOk());
    }
}
```

Đây là ví dụ test; user/password phải đến từ test configuration riêng và endpoint catalog phải có test fixture hợp lệ. Không dùng credential production trong test. Nếu cấu hình không dùng Basic, thay request post-processor bằng cơ chế auth thực tế.

## 14. Kiểm thử Spring WebFlux bằng WebTestClient

Với WebFlux, dùng `WebTestClient` và security test support tương ứng:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OsbWebFluxSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void catalogRequiresAuthentication() {
        webTestClient.get()
                .uri("/v2/catalog")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedPlatformCanReadCatalog() {
        webTestClient.get()
                .uri("/v2/catalog")
                .headers(headers -> headers.setBasicAuth(
                        "platform-client", "test-password"))
                .exchange()
                .expectStatus().isOk();
    }
}
```

Ví dụ này minh họa kiểm thử reactive server. Nếu dùng `@WebFluxTest`, cần import security configuration và mock các service/controller dependency. Không chạy MockMvc test như bằng chứng cho WebFlux chain hoặc ngược lại.

## 15. Ma trận kiểm thử bảo mật

Ngoài happy path, nên kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không gửi credential tới `/v2/catalog` | `401` hoặc challenge theo auth scheme đã cấu hình. |
| Credential sai | Bị từ chối, không gọi service nghiệp vụ. |
| Credential hợp lệ | Request đi qua authorization và handler OSB. |
| Caller thiếu role quản trị gọi `/admin/**` | `403` hoặc từ chối theo policy. |
| Request tham chiếu instance của tenant khác | Service-level authorization từ chối. |
| Gọi actuator nhạy cảm từ mạng public | Không truy cập được. |
| CSRF request tới UI/session endpoint | CSRF được kiểm tra theo policy UI. |
| OSB machine-to-machine request không dùng cookie | Không bị yêu cầu CSRF token nếu chain được thiết kế stateless đúng cách. |
| CORS từ origin không được allowlist | Browser policy không cho phép origin đó. |
| Authorization header xuất hiện trong log | Test phải phát hiện và thất bại. |
| Credential đã rotate/revoke | Credential cũ không còn xác thực được sau thời gian chuyển tiếp. |

Kiểm thử nên xác minh cả status HTTP lẫn side effect: request chưa xác thực không được gọi provider, không tạo operation và không làm thay đổi database.

## 16. Lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `SecurityFilterChain` cho WebFlux | Security không bảo vệ reactive route như mong đợi | Dùng `SecurityWebFilterChain`. |
| Dùng `SecurityWebFilterChain` cho MVC | Servlet endpoints không được cấu hình đúng | Dùng `SecurityFilterChain`. |
| `permitAll()` cho `/v2/**` để platform gọi được | OSB API bị mở cho caller không xác thực | Cấu hình auth đúng và kiểm tra credential phía platform. |
| Chỉ kiểm tra role platform | Tenant/instance khác có thể bị truy cập | Kiểm tra ownership ở service layer. |
| Tắt CSRF toàn ứng dụng | UI/session endpoint có thể bị CSRF | Tách API chain và UI chain. |
| Cho phép CORS `*` | Mở rộng bề mặt truy cập browser | Tắt nếu không cần hoặc allowlist origin cụ thể. |
| Expose toàn bộ Actuator | Lộ cấu hình, environment và dữ liệu vận hành | Giới hạn exposure, auth và management network. |
| Hardcode password trong YAML/source | Secret bị lộ qua repo/image | Dùng secret manager và rotation. |
| Reverse proxy headers không được kiểm soát | Có thể giả mạo scheme/IP hoặc bypass policy | Chỉ tin proxy được chỉ định và cấu hình forwarded headers đúng. |
| Exception handler ghi đè 401/403 | Platform nhận response không đúng contract | Kiểm thử security entry point và OSB error mapping. |

## 17. Checklist triển khai

- Xác định ứng dụng chạy Spring MVC hay Spring WebFlux.
- Dùng đúng security chain cho web stack đang chạy.
- Bảo vệ toàn bộ `/v2/**` bằng cơ chế platform/broker đã thống nhất.
- Dùng TLS và quản lý broker credentials ngoài source code.
- Cấu hình stateless cho OSB machine-to-machine API khi phù hợp.
- Chỉ tắt CSRF trong chain không dùng cookie/session; giữ CSRF cho UI cần bảo vệ.
- CORS tắt nếu không cần browser cross-origin; nếu bật thì allowlist cụ thể.
- Authentication và authorization được tách rõ; có kiểm tra tenant/instance ownership.
- Endpoint quản trị và Actuator có role/network policy riêng.
- Reverse proxy chỉ được tin khi nằm trong trust boundary.
- 401/403 và error response tương thích platform/OSB contract.
- Có integration test cho MVC hoặc WebFlux đúng với runtime.
- Kiểm tra request không xác thực không gây side effect và secret không xuất hiện trong log.

Spring Security bảo vệ service broker ở lớp HTTP, nhưng tính an toàn hoàn chỉnh còn phụ thuộc authorization trong service layer, quản lý secret, TLS, mạng triển khai và quy trình vận hành. Khi tách cấu hình MVC và WebFlux rõ ràng, bảo vệ toàn bộ OSB endpoints, giới hạn Actuator và kiểm tra quyền trên từng instance/binding, broker có thể tiếp nhận request từ platform mà vẫn giữ được ranh giới giữa API công khai và các chức năng quản trị nội bộ.
