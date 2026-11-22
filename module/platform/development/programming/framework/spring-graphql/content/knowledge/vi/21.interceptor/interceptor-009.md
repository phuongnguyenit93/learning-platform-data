# Authentication trong interceptor của Spring for GraphQL

Authentication xác định người gửi request là ai; authorization quyết định người đó được phép thực hiện thao tác nào và truy cập dữ liệu nào. Trong Spring for GraphQL, hai việc này cần được đặt đúng tầng vì HTTP GraphQL thường dùng một endpoint chung như `/graphql`, trong khi một operation có thể đọc nhiều field và gọi nhiều service.

`WebGraphQlInterceptor` cho phép can thiệp vào request và response ở tầng transport. Tuy nhiên, với HTTP, Spring Security filter chain thường là nơi xác thực credentials. Với GraphQL qua WebSocket, Spring for GraphQL cung cấp `AuthenticationWebSocketInterceptor` để lấy credentials từ payload `connection_init`, xác thực và truyền `SecurityContext` cho các request tiếp theo trên kết nối. Sau khi có danh tính, resolver và service thực hiện authorization ở mức field hoặc nghiệp vụ.

## 1. Phân biệt Authentication và Authorization

Hai khái niệm có liên quan nhưng trả lời hai câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Người gửi request là ai? | Token hợp lệ đại diện cho người dùng `alice`. |
| Authorization | Người dùng đó được làm gì? | `alice` được đọc dự án thuộc nhóm của mình nhưng không được xóa dự án của nhóm khác. |

Authentication thường tạo ra một đối tượng `Authentication` trong Spring Security, chứa principal và authorities. Đối tượng này được lưu trong `SecurityContext`.

Authorization sử dụng danh tính và quyền đã xác thực để quyết định cho phép hay từ chối một thao tác. Một người dùng đã đăng nhập vẫn có thể không đủ quyền gọi một mutation hoặc đọc một field nhạy cảm.

Không nên dùng interceptor chỉ để kiểm tra xem một header có tồn tại hay không rồi xem request là đã xác thực. Header có thể do client tự tạo; credentials phải được xác minh bằng authentication provider phù hợp.

## 2. Authentication nằm ở đâu trong kiến trúc GraphQL?

Vị trí xác thực phụ thuộc transport:

```text
HTTP GraphQL
Client Authorization header
        |
        v
Spring Security Filter Chain
        |
        | xác thực token/session
        v
SecurityContext
        |
        v
WebGraphQlInterceptor chain
        |
        v
GraphQL execution
        |
        v
@QueryMapping / @SchemaMapping
        |
        v
Service + method authorization

WebSocket GraphQL
Client connection_init payload
        |
        v
AuthenticationWebSocketInterceptor
        |
        | AuthenticationManager
        v
SecurityContext gắn với kết nối
        |
        v
Các subscribe request tiếp theo
        |
        v
GraphQL execution + authorization
```

Với HTTP, Spring Security bảo vệ URL GraphQL trước khi request tới GraphQL handler. `WebGraphQlInterceptor` có thể đọc metadata request, bổ sung `ExecutionInput` hoặc xử lý response, nhưng không thay thế authentication filter chain.

Với WebSocket, HTTP handshake chỉ tạo kết nối. Token dành cho GraphQL thường được gửi trong thông điệp `connection_init`; do đó cần interceptor hiểu vòng đời WebSocket và giữ `SecurityContext` cho những operation được gửi sau đó.

## 3. Bảo vệ HTTP GraphQL endpoint bằng Spring Security

Với Spring MVC, có thể yêu cầu mọi request đến `/graphql` phải được xác thực trong `SecurityFilterChain`. Ví dụ sau dùng OAuth2 Resource Server với JWT:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/graphql").authenticated()
                .anyRequest().permitAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Resource Server xác thực Bearer token theo cấu hình issuer/JWK hoặc public key của ứng dụng. Khi token hợp lệ, Spring Security tạo `Authentication` và đặt nó vào `SecurityContext`.

Nếu ứng dụng dùng Spring WebFlux, cấu hình tương ứng là `SecurityWebFilterChain`:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/graphql").authenticated()
                .anyExchange().permitAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Hai cấu hình trên là các lựa chọn theo stack; ứng dụng MVC dùng `HttpSecurity`, còn WebFlux dùng `ServerHttpSecurity`. Cần có dependency và cấu hình issuer/JWT phù hợp với hệ thống xác thực đang sử dụng.

Khi request thiếu hoặc có token không hợp lệ, Spring Security từ chối ở tầng HTTP trước khi GraphQL thực thi. Nếu endpoint cho phép anonymous, request vẫn có thể đến GraphQL với trạng thái chưa xác thực; các resolver/service cần xử lý trường hợp đó theo chính sách API.

## 4. Lấy principal trong annotated controller

Spring for GraphQL hỗ trợ `java.security.Principal` và `@AuthenticationPrincipal` làm method argument trong annotated controller. `@AuthenticationPrincipal` lấy `Authentication.getPrincipal()` từ Spring Security context.

Ví dụ với JWT principal:

```java
@Controller
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @QueryMapping
    Account myAccount(@AuthenticationPrincipal Jwt jwt) {
        return accountService.findBySubject(jwt.getSubject());
    }
}
```

Ở đây `Jwt` là principal do OAuth2 Resource Server cung cấp sau khi xác thực token. Không lấy `sub` trực tiếp từ một JWT chưa được xác minh.

Cũng có thể nhận `Principal` nếu chỉ cần danh tính tổng quát:

```java
@QueryMapping
List<Project> myProjects(Principal principal) {
    return projectService.findVisibleTo(principal.getName());
}
```

Spring for GraphQL có `AuthenticationPrincipalArgumentResolver` để hỗ trợ cả Spring MVC và WebFlux. Resolver sử dụng `SecurityContextHolder` cho MVC và `ReactiveSecurityContextHolder` cho WebFlux. Vì vậy, trong reactive application không nên tự đọc `SecurityContextHolder.getContext()` trong resolver rồi giả định ThreadLocal luôn có dữ liệu.

Nếu endpoint cho phép anonymous, principal có thể không có. Hãy khai báo và xử lý kiểu nullable phù hợp hoặc yêu cầu xác thực ở endpoint trước khi gọi resolver.

## 5. Authorization theo operation và field

Bảo vệ URL `/graphql` chỉ trả lời câu hỏi người dùng có được gọi endpoint hay không. Nó không phân biệt người dùng được gọi `myProjects` nhưng không được gọi `allAccounts`, vì cả hai field cùng đi qua một URL.

Để kiểm soát chi tiết hơn, Spring for GraphQL khuyến nghị đặt method security trên các service method được gọi khi phân giải field. Ví dụ:

```java
@Service
class ProjectService {

    @PreAuthorize("hasAuthority('project:read')")
    List<Project> findAll() {
        return projectRepository.findAll();
    }

    @PreAuthorize("@projectAuthorization.canRead(authentication, #projectId)")
    Project findById(UUID projectId) {
        return projectRepository.findById(projectId).orElseThrow();
    }
}
```

`@EnableMethodSecurity` bật method authorization trong ứng dụng servlet. Với WebFlux, dùng `@EnableReactiveMethodSecurity`. Khi Spring Security method security được kích hoạt, `@PreAuthorize` kiểm tra quyền trước khi gọi method; `@PostAuthorize` có thể kiểm tra kết quả trả về, nhưng cần cân nhắc kỹ với method ghi dữ liệu vì thao tác có thể đã xảy ra trước khi hậu kiểm.

Ví dụ controller có thể gọi service mà không tự triển khai toàn bộ quy tắc quyền:

```java
@Controller
class ProjectController {

    private final ProjectService projectService;

    ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @QueryMapping
    Project project(@Argument UUID id) {
        return projectService.findById(id);
    }
}
```

Quyền đọc dự án được kiểm tra tại service, nên các entry point khác gọi cùng nghiệp vụ cũng tuân theo chính sách đó. Điều này giúp tránh chỉ bảo vệ một resolver trong khi một đường gọi khác lại bỏ qua kiểm tra.

## 6. `WebGraphQlInterceptor` và Authentication cho HTTP

`WebGraphQlInterceptor` có thể đọc HTTP header và chuyển metadata cần thiết vào `GraphQLContext`. Tuy nhiên, nếu Spring Security đã xác thực HTTP request thì không cần tự phân tích Bearer token lần nữa trong interceptor.

Ví dụ interceptor chỉ bổ sung mã tenant sau khi đã có một nguồn đáng tin cậy xác định tenant:

```java
@Component
class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(WebGraphQlRequest request, Chain chain) {
        String tenantId = resolveTrustedTenant(request);

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context -> context.put("tenantId", tenantId)).build()
        );

        return chain.next(request);
    }

    private String resolveTrustedTenant(WebGraphQlRequest request) {
        // Lấy tenant từ thông tin đã được xác minh bởi security layer.
        // Không tin cậy một header tenant tùy ý do client tự gửi.
        return "resolved-tenant";
    }
}
```

Đây là ví dụ về việc truyền context, không phải một triển khai xác thực hoàn chỉnh. Trong ứng dụng thực tế, `resolveTrustedTenant` cần dựa vào principal/claims đã được xác minh hoặc một tenant resolver đáng tin cậy; không dùng giá trị cố định như ví dụ.

Nếu chỉ muốn sao chép một số HTTP header vào GraphQL context, Spring for GraphQL có `HttpRequestHeaderInterceptor`. Chỉ map các header không nhạy cảm và thực sự cần thiết. Tránh đưa access token vào context hoặc log nếu resolver có thể lấy principal trực tiếp từ Spring Security.

## 7. Authentication cho GraphQL qua WebSocket

WebSocket là kết nối dài hạn. Sau khi handshake hoàn tất, client gửi thông điệp `connection_init` theo GraphQL over WebSocket protocol. Payload của thông điệp này có thể mang thông tin xác thực:

```json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer <access-token>"
  }
}
```

Spring for GraphQL cung cấp `AuthenticationWebSocketInterceptor` cho hai transport:

| Transport | Interceptor | Bộ xác thực |
|---|---|---|
| Spring MVC | `org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor` | `AuthenticationManager` |
| Spring WebFlux | `org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor` | `ReactiveAuthenticationManager` |

Hai interceptor này dùng `AuthenticationExtractor` để lấy authentication từ payload `connection_init`, xác thực bằng manager tương ứng và truyền `SecurityContext` sang các request GraphQL tiếp theo trên cùng kết nối.

### Cấu hình cho Spring MVC

```java
@Configuration
class GraphQlWebSocketSecurityConfiguration {

    @Bean
    WebSocketGraphQlInterceptor authenticationWebSocketInterceptor(
            AuthenticationManager authenticationManager) {

        return new org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            authenticationManager
        );
    }
}
```

### Cấu hình cho Spring WebFlux

```java
@Configuration
class GraphQlWebSocketSecurityConfiguration {

    @Bean
    WebSocketGraphQlInterceptor authenticationWebSocketInterceptor(
            ReactiveAuthenticationManager authenticationManager) {

        return new org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            authenticationManager
        );
    }
}
```

Hai ví dụ là lựa chọn thay thế theo ứng dụng, không đăng ký đồng thời cả hai. `BearerTokenAuthenticationExtractor` mặc định đọc khóa `Authorization` trong payload `connection_init`. Có thể truyền tên khóa khác vào constructor nếu client dùng payload key riêng.

`AuthenticationManager` hoặc `ReactiveAuthenticationManager` phải được cấu hình để xác thực loại token được extractor tạo ra. Chỉ trích xuất token không có nghĩa token đã hợp lệ.

Spring Boot Starter phát hiện interceptor bean và đưa vào `WebGraphQlHandler` chain. Lưu ý trong một chain chỉ được có tối đa một interceptor thuộc loại `WebSocketGraphQlInterceptor`; có thể kết hợp nó với các `WebGraphQlInterceptor` thông thường khác.

## 8. Tùy chỉnh cách lấy credentials từ `connection_init`

Nếu payload không dùng khóa `Authorization` hoặc cần định dạng credentials riêng, có thể cung cấp `AuthenticationExtractor` tùy chỉnh. Interface này nhận payload `Map<String, Object>` và trả về `Mono<Authentication>`.

Ví dụ payload có khóa `accessToken`:

```json
{
  "type": "connection_init",
  "payload": {
    "accessToken": "<access-token>"
  }
}
```

Extractor có trách nhiệm chuyển token thành một đối tượng authentication chưa được xác thực phù hợp với authentication provider của ứng dụng. Authentication manager mới là nơi kiểm tra chữ ký, issuer, audience, thời hạn hoặc thông tin xác thực khác.

Khi cần tùy biến cả quy trình xác thực và cách ghi `SecurityContext` vào Reactor context, có thể kế thừa `AbstractAuthenticationWebSocketInterceptor`. Lớp cơ sở cung cấp điểm mở rộng `authenticate(...)` và `getContextToWrite(...)`. Thông thường nên ưu tiên interceptor có sẵn và `BearerTokenAuthenticationExtractor`; chỉ tùy biến khi giao thức credentials thực sự khác.

## 9. Dùng principal trong subscription và các request tiếp theo

Sau khi `AuthenticationWebSocketInterceptor` xác thực thành công `connection_init`, Spring for GraphQL lưu authentication trong WebSocket session attributes và truyền `SecurityContext` tới các subscribe request tiếp theo.

Resolver có thể tiếp tục nhận principal như với HTTP:

```java
@Controller
class NotificationController {

    @SubscriptionMapping
    Flux<Notification> notifications(@AuthenticationPrincipal Jwt jwt) {
        return notificationService.streamFor(jwt.getSubject());
    }
}
```

Với subscription, cần bảo đảm luồng dữ liệu được giới hạn theo principal đã xác thực. Không để client tự gửi `userId` trong argument rồi dùng nó làm căn cứ duy nhất để chọn luồng thông báo của người khác.

Kết nối WebSocket có thể tồn tại lâu hơn thời hạn access token. Cần quyết định chính sách khi token hết hạn hoặc bị thu hồi: đóng kết nối, yêu cầu client kết nối lại với token mới, hoặc kiểm tra hiệu lực quyền ở mỗi sự kiện tùy yêu cầu bảo mật. Không nên giả định token được xác thực một lần sẽ luôn hợp lệ trong suốt kết nối vô hạn.

## 10. Kiểm thử Authentication và Authorization

Nên kiểm tra riêng các tầng để xác định lỗi nằm ở xác thực, phân quyền hay GraphQL execution.

| Tình huống | Điều cần xác minh |
|---|---|
| HTTP không có credentials | Security filter chain từ chối hoặc endpoint xử lý anonymous theo cấu hình. |
| HTTP có token không hợp lệ | Authentication thất bại; resolver không được thực thi nếu endpoint yêu cầu xác thực. |
| Token hợp lệ | Principal được cung cấp cho annotated controller. |
| Người dùng thiếu authority | Method security từ chối service method tương ứng. |
| Người dùng truy cập tài nguyên của người khác | Quy tắc ownership/tenant từ chối dù người dùng đã đăng nhập. |
| WebSocket thiếu hoặc sai token trong `connection_init` | Không cho phép các operation được xác thực chạy dưới danh tính không hợp lệ. |
| WebSocket token hợp lệ | Principal được truyền tới query/subscription tiếp theo. |
| Token hết hạn trong kết nối dài hạn | Hành vi đóng kết nối hoặc yêu cầu xác thực lại đúng chính sách. |

Với controller/service, có thể dùng `@WithMockUser` hoặc test security context phù hợp để kiểm tra method authorization. Với HTTP endpoint, dùng MockMvc hoặc WebTestClient để kiểm tra filter chain và GraphQL response. Với WebSocket, kiểm thử handshake, payload `connection_init`, phản hồi xác nhận kết nối và một operation tiếp theo.

Đừng chỉ kiểm tra HTTP status. Một operation GraphQL có thể thực thi một phần và trả `data` cùng `errors`; method security từ chối một field có thể biểu hiện thành GraphQL error trong response. Hãy kiểm tra cả `data`, `errors`, `path` và mã lỗi theo hợp đồng ứng dụng.

## 11. Những lỗi thường gặp

**Tự coi việc có Authorization header là đã xác thực.** Header chỉ chứa credentials; phải xác minh bằng Spring Security authentication provider.

**Dùng `WebGraphQlInterceptor` thay thế HTTP security filter chain.** Với HTTP, hãy bảo vệ `/graphql` ở `SecurityFilterChain` hoặc `SecurityWebFilterChain`; interceptor chủ yếu xử lý concern ở ranh giới GraphQL request.

**Chỉ bảo vệ URL `/graphql`.** Tất cả query và mutation đều đi qua cùng endpoint. Dùng method security hoặc kiểm tra quyền trong service để phân quyền theo nghiệp vụ và tài nguyên.

**Nhầm Authentication với Authorization.** Token hợp lệ không đồng nghĩa người dùng được đọc mọi object hoặc gọi mọi mutation.

**Dùng `SecurityContextHolder` trực tiếp trong reactive flow.** Với WebFlux, security context nằm trong Reactor context. Dùng `@AuthenticationPrincipal`, `Principal`, reactive method security hoặc `ReactiveSecurityContextHolder` phù hợp.

**Quên xác thực payload `connection_init`.** WebSocket handshake thành công không có nghĩa người dùng đã được xác thực cho GraphQL operation. Cần cấu hình `AuthenticationWebSocketInterceptor` nếu token được gửi trong connection payload.

**Đăng ký hai `WebSocketGraphQlInterceptor`.** Một chain chỉ hỗ trợ tối đa một interceptor thuộc loại này. Kết hợp logic cần thiết hoặc dùng interceptor thông thường cho concern khác.

**Đưa token vào GraphQL variables hoặc query arguments.** Token có thể xuất hiện trong log, tracing hoặc cache. Dùng HTTP Authorization header hoặc payload `connection_init` theo transport.

**Không xét thời hạn token của WebSocket.** Kết nối lâu dài có thể tiếp tục sau khi token hết hạn. Cần có chính sách hết hạn, thu hồi và reconnect.

## Kết luận

Với Spring for GraphQL, HTTP authentication nên được thực hiện trong Spring Security filter chain; `WebGraphQlInterceptor` chỉ bổ sung metadata và xử lý request/response khi cần. Đối với WebSocket, dùng `AuthenticationWebSocketInterceptor` cùng `BearerTokenAuthenticationExtractor` và `AuthenticationManager` hoặc `ReactiveAuthenticationManager` để xác thực payload `connection_init` và truyền `SecurityContext` cho các operation tiếp theo. Sau authentication, dùng `@AuthenticationPrincipal`, `Principal` và method security để bảo vệ dữ liệu ở cấp field/nghiệp vụ. Hãy kiểm thử riêng HTTP, WebSocket, quyền theo tài nguyên và vòng đời token.

## Tài liệu tham khảo

- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL API — `AuthenticationWebSocketInterceptor` for WebMVC](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/webmvc/AuthenticationWebSocketInterceptor.html)
- [Spring for GraphQL API — `AuthenticationWebSocketInterceptor` for WebFlux](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/webflux/AuthenticationWebSocketInterceptor.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
