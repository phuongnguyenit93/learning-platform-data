# Kiểm tra SecurityContext và giới hạn phiên phản ứng theo phiên bản

## Mục tiêu bài học

Trong ứng dụng Spring WebFlux, bảo mật hoạt động trên chuỗi reactive và WebSession thay vì Servlet HttpSession. Spring Security đưa SecurityContext vào Reactor Context để các thành phần reactive đọc được danh tính hiện tại. Nếu ứng dụng cần duy trì đăng nhập giữa nhiều request, SecurityContext phải được lưu trong WebSession bằng một ServerSecurityContextRepository phù hợp. Spring Session có thể thay WebSession mặc định bằng phiên được lưu trong Redis để nhiều instance cùng khôi phục trạng thái xác thực.

Giới hạn số phiên đồng thời cũng phụ thuộc phiên bản. Spring Security bổ sung ReactiveSessionRegistry và reactive concurrent session control từ phiên bản 6.3. Spring Session bổ sung SpringSessionBackedReactiveSessionRegistry cùng cấu hình Redis WebSession có index từ phiên bản 3.3. Nếu dùng registry in-memory mặc định, giới hạn phiên chỉ được theo dõi trong một JVM; để giới hạn hoạt động trên nhiều node, registry cần đọc dữ liệu từ kho session dùng chung và tìm được phiên theo principal.

Sau bài học, bạn có thể:

- Phân biệt SecurityContext trong Reactor Context với SecurityContext được lưu trong WebSession.
- Kiểm tra WebSessionServerSecurityContextRepository và NoOpServerSecurityContextRepository.
- Cấu hình Spring Session Redis cho WebFlux bằng ReactiveSessionRepository.
- Kiểm thử SecurityContext qua nhiều request và nhiều instance bằng cookie session.
- Dùng StepVerifier để kiểm tra ReactiveSecurityContextHolder.
- Dùng WebTestClient để kiểm tra đăng nhập, endpoint được bảo vệ và trạng thái xác thực sau request.
- Cấu hình giới hạn phiên bằng SessionLimit và ReactiveSessionRegistry.
- Phân biệt InMemoryReactiveSessionRegistry với SpringSessionBackedReactiveSessionRegistry.
- Xác minh principal index cần thiết cho giới hạn phiên phân tán.
- Nhận biết khác biệt phiên bản Spring Security 6.2, 6.3+ và Spring Session 3.3+.
- Tránh nhầm Servlet HttpSession/JDBC session với WebFlux WebSession/reactive repository.

## 1. WebFlux sử dụng WebSession và Reactor Context

Spring MVC Servlet sử dụng HttpServletRequest, HttpSession, servlet filter và SecurityContextHolder dựa trên ThreadLocal. Spring WebFlux dùng ServerWebExchange, WebSession, WebFilter và Reactor Context.

Trong một request reactive, việc xử lý có thể chuyển qua nhiều thread hoặc scheduler. Vì vậy, không thể dựa vào ThreadLocal để truyền danh tính từ đầu pipeline đến cuối pipeline. Spring Security dùng Reactor Context và cung cấp ReactiveSecurityContextHolder để truy cập SecurityContext.

Hai nơi lưu trạng thái có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| Reactor Context | Mang SecurityContext trong quá trình thực thi một reactive chain |
| ReactiveSecurityContextHolder | API đọc/đặt SecurityContext trong Reactor Context |
| ServerSecurityContextRepository | Tải và lưu SecurityContext giữa các request |
| WebSession | Phiên của WebFlux, có thể chứa SecurityContext và thuộc tính ứng dụng |
| ReactiveSessionRepository | Tạo, tìm, lưu và xóa Session theo kiểu reactive |
| ReactiveSessionRegistry | Theo dõi các phiên của principal để giới hạn số phiên đồng thời |

Một request có thể tải SecurityContext từ WebSession rồi đưa nó vào Reactor Context. Khi request kết thúc, context trong Reactor Context không tự tồn tại cho request sau. Muốn giữ đăng nhập, ứng dụng cần lưu SecurityContext vào WebSession và khôi phục lại ở request kế tiếp.

### Luồng khôi phục xác thực

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux WebSessionManager
    participant R as Spring Session Reactive Repository
    participant S as Spring Security WebFilter
    participant A as Reactive Controller

    C->>W: Request + SESSION cookie
    W->>R: Tìm WebSession theo ID
    R-->>W: Session và attributes
    W->>S: ServerWebExchange có WebSession
    S->>W: Tải SecurityContext qua repository
    W-->>S: SecurityContext
    S->>S: Đưa context vào Reactor Context
    S->>A: Chạy reactive handler
    A->>S: ReactiveSecurityContextHolder
    S-->>C: Response
~~~

Nếu SecurityContext không được lưu hoặc không được tải lại, request đầu có thể xác thực thành công nhưng request kế tiếp trở thành anonymous. Test cần đi qua ít nhất hai request riêng biệt để phát hiện lỗi này.

## 2. ReactiveSecurityContextHolder không phải SecurityContextHolder

Trong WebFlux, dùng ReactiveSecurityContextHolder:

~~~java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

Không dùng đoạn imperative sau trong reactive pipeline để đọc danh tính hiện tại:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

SecurityContextHolder thường dựa trên ThreadLocal trong ứng dụng Servlet. Trong reactive flow, thread có thể thay đổi giữa các toán tử; giá trị ThreadLocal không bảo đảm đi theo subscription.

### Truyền context trong test

Có thể tạo Authentication giả và đặt nó vào Reactor Context:

~~~java
Authentication authentication =
        new TestingAuthenticationToken(
                "alice",
                "unused",
                "ROLE_USER"
        );

Mono<String> username =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());

StepVerifier.create(
        username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication)
        )
)
.expectNext("alice")
.verifyComplete();
~~~

Đây là unit test cho việc đọc context trong một reactive chain. Nó không chứng minh đăng nhập đã được lưu vào WebSession, cookie được phát hoặc request tiếp theo khôi phục được context. Những hành vi đó cần integration test qua WebTestClient và repository thật.

### Ranh giới của Reactor Context

- Context gắn với subscription, không phải một biến toàn cục.
- Toán tử reactive tiếp tục cùng subscription có thể truy cập context.
- Khi tạo một reactive chain độc lập, không giả định context tự xuất hiện.
- Các phương thức bảo mật reactive thường cần trả về Mono hoặc Flux để Spring Security tích hợp context.
- Không gọi block() trong request path chỉ để lấy Authentication; làm vậy có thể chặn event-loop và phá lợi ích non-blocking.

## 3. ServerSecurityContextRepository quyết định cách duy trì đăng nhập

ServerSecurityContextRepository định nghĩa cách Spring Security tải và lưu SecurityContext cho ServerWebExchange.

Hai lựa chọn thường gặp:

| Repository | Hành vi | Trường hợp sử dụng |
|---|---|---|
| WebSessionServerSecurityContextRepository | Lưu SecurityContext trong WebSession và tải lại ở request sau | Form login hoặc ứng dụng cookie-based cần duy trì đăng nhập |
| NoOpServerSecurityContextRepository | Không lưu SecurityContext giữa các request | API stateless dùng bearer token hoặc cơ chế xác thực độc lập mỗi request |

WebSessionServerSecurityContextRepository còn đổi Session ID khi lưu SecurityContext để giảm nguy cơ session fixation. Đây là hành vi quan trọng cần được kiểm thử sau authentication thành công.

### Cấu hình WebSession repository

~~~java
@Bean
ServerSecurityContextRepository securityContextRepository() {
    return new WebSessionServerSecurityContextRepository();
}
~~~

Với form login, có thể gắn repository rõ ràng vào cả cơ chế tải context và authentication filter:

~~~java
@Bean
SecurityWebFilterChain springSecurityFilterChain(
        ServerHttpSecurity http,
        ServerSecurityContextRepository securityContextRepository
) {
    return http
            .authorizeExchange(authorize -> authorize
                    .pathMatchers("/login", "/assets/**").permitAll()
                    .anyExchange().authenticated()
            )
            .securityContextRepository(securityContextRepository)
            .formLogin(form -> form
                    .securityContextRepository(securityContextRepository)
            )
            .build();
}
~~~

Cấu hình minh họa dùng form login. Trong ứng dụng thực tế, thêm authentication provider, success handler và các chính sách CSRF phù hợp. Spring Security reactive bật CSRF theo cấu hình mặc định; các request POST đăng nhập/đăng xuất trong test cần xử lý token đúng cách.

### Cấu hình stateless

Với API xác thực độc lập từng request bằng JWT, có thể dùng NoOpServerSecurityContextRepository:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance()
            )
            .authorizeExchange(authorize -> authorize
                    .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
}
~~~

Cấu hình stateless không có nghĩa toàn bộ ứng dụng không thể tạo WebSession. CSRF, request cache hoặc thành phần khác có thể cần WebSession tùy cấu hình. Test nên xác minh đúng điều cần kiểm tra: SecurityContext không được lưu giữa request bằng NoOp repository, thay vì giả định không có bất kỳ session nào trong hệ thống.

### HTTP Basic có thể khác form login

Trong các phiên bản Spring Security reactive hiện đại, HTTP Basic mặc định dùng NoOpServerSecurityContextRepository nếu không cấu hình khác, trong khi form login mặc định dùng WebSessionServerSecurityContextRepository. Vì vậy, nếu muốn HTTP Basic tạo phiên đăng nhập duy trì qua request, cần cấu hình repository cho HTTP Basic một cách rõ ràng:

~~~java
.httpBasic(basic -> basic
        .securityContextRepository(securityContextRepository)
)
~~~

Không chỉ kiểm tra form login rồi kết luận mọi authentication mechanism đều lưu context theo cùng cách.

## 4. Spring Session tích hợp WebFlux qua ReactiveSessionRepository

Spring Session WebFlux tích hợp với WebSession thông qua WebSessionManager và ReactiveSessionRepository. Ứng dụng tiếp tục dùng WebSession API; Spring Session cung cấp implementation lưu session trong kho dữ liệu bên ngoài.

Với Redis reactive, cấu hình cơ bản:

~~~java
@Configuration
@EnableRedisWebSession
class ReactiveSessionConfiguration {
}
~~~

Cấu hình này sử dụng Reactive Redis và tạo WebSessionManager backed by Spring Session. Cần có ReactiveRedisConnectionFactory trong application context. Redis repository cung cấp thao tác reactive để tạo, tải, lưu và xóa session.

Không dùng cấu hình Servlet sau cho WebFlux:

~~~java
@EnableRedisHttpSession
~~~

Annotation đó dành cho HttpSession và Servlet filter. WebFlux cần WebSession và WebSessionManager.

### ReactiveSessionRepository có API reactive

Các thao tác repository trả về Mono thay vì kết quả đồng bộ:

- createSession(): Mono của session mới.
- findById(id): Mono của session hoặc empty khi không tìm thấy.
- save(session): Mono<Void>.
- deleteById(id): Mono<Void>.

Trong controller, ưu tiên dùng WebSession thông qua ServerWebExchange hoặc API WebFlux. Không truy cập trực tiếp repository để thay thế WebSession lifecycle trừ khi có lý do thiết kế rõ ràng.

### Cookie định danh WebSession

Spring Session WebFlux mặc định dùng CookieWebSessionIdResolver. Cookie thường có tên SESSION; ứng dụng có thể thay tên, Path hoặc SameSite bằng WebSessionIdResolver bean.

Ví dụ:

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
    resolver.setCookieName("SESSION");
    resolver.addCookieInitializer(builder -> builder.path("/"));
    resolver.addCookieInitializer(builder -> builder.sameSite("Lax"));
    return resolver;
}
~~~

Khi kiểm thử đăng nhập, lấy cookie từ response và gửi lại trong request kế tiếp. Không giả định WebTestClient tự giữ cookie giống trình duyệt nếu test client chưa được cấu hình cookie store.

## 5. SecurityContext được lưu trong WebSession như thế nào?

WebSessionServerSecurityContextRepository lưu SecurityContext vào thuộc tính của WebSession. Khi request mới đến với cookie hợp lệ, Spring Security tải context từ session và đưa vào Reactor Context.

Luồng lưu:

1. Authentication filter xác thực credential.
2. Authentication thành công.
3. ServerSecurityContextRepository lưu SecurityContext vào WebSession.
4. WebSession được đánh dấu cần lưu.
5. Spring Session ghi thay đổi vào ReactiveSessionRepository.
6. Resolver gửi Session ID về client.
7. Request sau gửi cookie và khôi phục SecurityContext.

### Kiểm tra session fixation

Khi WebSessionServerSecurityContextRepository lưu SecurityContext, nó đổi Session ID để giảm nguy cơ session fixation. Vì vậy, test nên giữ cookie trước xác thực nếu session ẩn danh đã được tạo, sau đó so sánh với cookie sau login.

Không phải mọi cấu hình đều tạo session trước login. Nếu không có ID trước login, test không thể khẳng định ID đã thay đổi; khi đó hãy xác minh phiên sau login được tạo, cookie được phát và SecurityContext được khôi phục ở request sau.

### Đổi ID và thuộc tính session

Đổi Session ID không đồng nghĩa xóa toàn bộ WebSession. Thuộc tính cần giữ có thể tiếp tục tồn tại. Test cần xác minh cả định danh mới và thuộc tính mong muốn còn đọc được.

Không chỉ kiểm tra Set-Cookie. Gửi request tiếp theo với cookie mới và đọc một endpoint yêu cầu authentication để chứng minh context thực sự được tải.

## 6. Giới hạn phiên phản ứng: mốc phiên bản Spring Security 6.3

Reactive concurrent session control không có trong các phiên bản Spring Security reactive cũ theo cùng DSL hiện đại. ReactiveSessionRegistry và sessionManagement().concurrentSessions() được bổ sung từ Spring Security 6.3.

| Thành phần | Mốc phiên bản | Ý nghĩa |
|---|---|---|
| ReactiveSecurityContextHolder | Spring Security 5.0 | Truy cập SecurityContext trong Reactor Context |
| WebSessionServerSecurityContextRepository | Spring Security 5.0 | Lưu context trong WebSession và đổi ID khi lưu |
| ReactiveSessionRegistry | Spring Security 6.3 | Registry theo dõi phiên reactive theo principal |
| Reactive concurrent session control DSL | Spring Security 6.3 | Cấu hình maximumSessions trong ServerHttpSecurity |
| SpringSessionBackedReactiveSessionRegistry | Spring Session 3.3 | Dùng repository Spring Session làm registry để hoạt động trên nhiều node |
| EnableRedisIndexedWebSession | Spring Session 3.3 | Reactive Redis repository có index để tìm phiên theo principal |

Khi dự án dùng Spring Security 6.2 hoặc thấp hơn, không sao chép cấu hình concurrent session control của 6.3+. Cần nâng cấp theo Spring Boot/Spring Framework dependency management tương thích hoặc tự triển khai chính sách giới hạn phiên phù hợp.

Spring Session 3.3+ cung cấp SpringSessionBackedReactiveSessionRegistry. Chỉ nâng Spring Security lên 6.3 mà vẫn dùng registry in-memory không tạo ra khả năng giới hạn phiên phân tán.

### Kiểm tra dependency thực tế

Trước khi viết test, kiểm tra dependency tree hoặc dependency management của dự án để biết chính xác:

- Spring Boot version.
- Spring Security version.
- Spring Session version.
- Spring Data Redis version.
- Reactor version.

Không nâng riêng một thư viện Spring lên version mới ngoài BOM nếu chưa xác minh compatibility. Một số method DSL, handler hoặc annotation có thể khác giữa major/minor version.

## 7. Giới hạn số phiên với ReactiveSessionRegistry

Spring Security reactive cho phép giới hạn số phiên đồng thời theo principal. Mặc định, số phiên được phép không bị giới hạn.

Ví dụ giới hạn một phiên trên mỗi người dùng:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        ReactiveSessionRegistry sessionRegistry
) {
    return http
            .authorizeExchange(authorize -> authorize
                    .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .concurrentSessions(concurrent -> concurrent
                            .maximumSessions(SessionLimit.of(1))
                            .sessionRegistry(sessionRegistry)
                    )
            )
            .build();
}
~~~

Đoạn DSL này yêu cầu Spring Security 6.3 trở lên. Nếu muốn cho phép không giới hạn, dùng SessionLimit.UNLIMITED.

### Giới hạn theo quyền của người dùng

SessionLimit có thể quyết định số phiên tối đa dựa trên Authentication:

~~~java
private SessionLimit sessionLimit() {
    return authentication -> {
        boolean unlimited = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        authority.getAuthority().equals("ROLE_UNLIMITED_SESSIONS"));

        if (unlimited) {
            return Mono.empty();
        }

        boolean admin = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        authority.getAuthority().equals("ROLE_ADMIN"));

        return Mono.just(admin ? 3 : 1);
    };
}
~~~

Trong ví dụ, user có ROLE_UNLIMITED_SESSIONS không bị giới hạn, admin có tối đa ba phiên và user thường có một phiên. Chính sách thật cần dựa trên quyền được cấp từ nguồn tin cậy, không lấy role từ request client.

### Khi vượt quá giới hạn

Hành vi mặc định là hết hạn các phiên ít được sử dụng gần đây nhất cho đến khi đáp ứng giới hạn. Có thể thay đổi thành từ chối login mới bằng PreventLoginServerMaximumSessionsExceededHandler.

~~~java
.sessionManagement(session -> session
        .concurrentSessions(concurrent -> concurrent
                .maximumSessions(SessionLimit.of(1))
                .maximumSessionsExceededHandler(
                        new PreventLoginServerMaximumSessionsExceededHandler()
                )
        )
)
~~~

Tên handler và API cần đối chiếu với version Spring Security đang dùng. Nếu có custom maximum sessions exceeded handler, hãy test cả kết quả login mới và trạng thái phiên cũ.

### Session limit không tự logout ở Identity Provider

Nếu ứng dụng dùng OAuth2 Login, Spring Security có thể hết hạn WebSession cục bộ nhưng không tự động vô hiệu hóa phiên tại Identity Provider. Nếu cần đăng xuất khỏi IdP, phải có cơ chế riêng với provider và giao thức logout tương ứng.

## 8. InMemoryReactiveSessionRegistry chỉ theo dõi trong một JVM

Spring Security cung cấp InMemoryReactiveSessionRegistry. Nó phù hợp cho test hoặc ứng dụng chỉ có một instance, nhưng registry lưu dữ liệu trong bộ nhớ của process.

Trong deployment nhiều node:

- Node A có registry A.
- Node B có registry B.
- Login tại A được ghi vào registry A.
- B không tự thấy bản ghi ở A.
- Cả hai node có thể đánh giá giới hạn phiên dựa trên tập dữ liệu riêng.

Do đó, dùng InMemoryReactiveSessionRegistry không đủ để bảo đảm giới hạn phiên trên toàn cụm.

Không nhầm việc session được lưu trong Redis với việc registry cũng được chia sẻ. Hai thành phần có thể độc lập: WebSession repository có thể là Redis, trong khi ReactiveSessionRegistry vẫn là in-memory.

## 9. SpringSessionBackedReactiveSessionRegistry cho nhiều node

Spring Session cung cấp SpringSessionBackedReactiveSessionRegistry để lấy thông tin phiên từ Spring Session repository thay vì giữ registry riêng trong JVM. Lớp này có từ Spring Session 3.3 và cần repository hỗ trợ tìm session theo index principal.

Với Redis reactive, dùng cấu hình indexed WebSession:

~~~java
@Configuration
@EnableRedisIndexedWebSession
class IndexedReactiveSessionConfiguration {
}
~~~

Annotation này tạo ReactiveRedisIndexedSessionRepository. Repository vừa quản lý session, vừa triển khai ReactiveFindByIndexNameSessionRepository để tìm các phiên theo principal name.

Đăng ký registry:

~~~java
@Bean
ReactiveSessionRegistry reactiveSessionRegistry(
        ReactiveRedisIndexedSessionRepository repository
) {
    return new SpringSessionBackedReactiveSessionRegistry<>(
            repository,
            repository
    );
}
~~~

ReactiveRedisIndexedSessionRepository triển khai cả ReactiveSessionRepository và ReactiveFindByIndexNameSessionRepository, nên có thể truyền cùng một bean cho hai tham số constructor.

Khi kết hợp với DSL concurrent session control, các node cùng truy vấn kho session/index dùng chung. Một phiên được tạo ở A có thể được tính khi login tiếp theo đến B.

### Vì sao cần indexed repository?

Giới hạn phiên được tính theo người dùng, không chỉ theo Session ID. Registry cần tìm mọi session của principal để đếm và áp dụng handler khi vượt giới hạn.

ReactiveRedisSessionRepository cơ bản có thể tìm session theo ID nhưng không cung cấp principal index tương đương. ReactiveRedisIndexedSessionRepository cung cấp khả năng tìm theo index và là lựa chọn phù hợp cho SpringSessionBackedReactiveSessionRegistry.

Không cấu hình registry backed by Spring Session với một repository chỉ hỗ trợ tìm theo ID. Nếu thiếu ReactiveFindByIndexNameSessionRepository, ứng dụng không có dữ liệu cần thiết để tìm các phiên của một principal.

## 10. Principal index phải khớp với Authentication

ReactiveFindByIndexNameSessionRepository dùng index PRINCIPAL_NAME_INDEX_NAME để tìm các session của người dùng. Giá trị index phải khớp với cách registry biểu diễn principal.

Spring Session Redis Indexed có PrincipalNameIndexResolver để nhận diện principal từ SecurityContext được lưu trong session. Tuy nhiên, ứng dụng dùng custom authentication flow hoặc custom principal cần xác minh index thực tế được tạo.

Các điểm cần kiểm tra:

- SecurityContext đã được lưu vào WebSession trước khi repository tạo/cập nhật index.
- Principal có tên ổn định, nhất quán giữa các request.
- Chuỗi principal mà registry truy vấn trùng với giá trị index.
- Custom Authentication không đổi tên principal giữa lần login và lần tra cứu.
- Các phiên được tạo bằng flow riêng cũng được đăng ký.
- Nếu cần, custom IndexResolver xử lý principal theo mô hình của ứng dụng.

Không giả định Spring Session tự biết mọi cách ứng dụng xác thực người dùng. Repository chỉ có thể index dữ liệu mà resolver nhận diện được.

### Kiểm thử principal index

Sau khi login bằng user alice:

1. Lấy cookie session.
2. Xác minh session có SecurityContext.
3. Truy vấn repository theo PRINCIPAL_NAME_INDEX_NAME với giá trị alice trong test integration.
4. Xác minh session ID xuất hiện trong kết quả.
5. Đăng nhập phiên thứ hai bằng cùng principal ở node khác.
6. Xác minh registry thấy cả hai session trước khi áp dụng giới hạn.

Không dùng Redis key nội bộ làm hợp đồng API lâu dài. Ưu tiên kiểm tra qua ReactiveFindByIndexNameSessionRepository; nếu kiểm tra key để debug, khóa test vào phiên bản repository cụ thể.

## 11. Kiểm thử SecurityContext bằng StepVerifier

StepVerifier phù hợp để kiểm tra reactive pipeline nhận đúng SecurityContext từ Reactor Context.

~~~java
@Test
void readsAuthenticationFromReactorContext() {
    Authentication authentication =
            new TestingAuthenticationToken(
                    "alice",
                    "unused",
                    "ROLE_USER"
            );

    Mono<String> username = ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);

    StepVerifier.create(
            username.contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(authentication)
            )
    )
    .expectNext("alice")
    .verifyComplete();
}
~~~

Test này xác minh API context. Nó không xác minh SecurityContextRepository, WebSession hoặc Redis.

### Kiểm tra context không được đặt

Nếu không có SecurityContext trong Reactor Context, ReactiveSecurityContextHolder.getContext() thường hoàn tất empty. Test nên xác minh service xử lý trường hợp này an toàn, thay vì dereference context như thể luôn có authentication.

### Kiểm tra method security

Nếu dùng @EnableReactiveMethodSecurity, method được bảo vệ nên trả về Mono hoặc Flux để SecurityContext đi theo Reactor Context.

Ví dụ:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOperation() {
    return Mono.just("allowed");
}
~~~

Test nên chạy cả user có quyền và user không có quyền, xác minh kết quả được phát ra qua reactive signal. Không gọi method imperative rồi đọc SecurityContext từ ThreadLocal.

## 12. Kiểm thử WebSession persistence bằng WebTestClient

StepVerifier không thay thế test HTTP. Để xác minh context được lưu giữa các request, dùng WebTestClient với application context thật, WebFlux security chain và Spring Session repository.

Một kịch bản:

1. Gửi POST login bằng credential hợp lệ.
2. Xử lý CSRF token nếu CSRF đang bật.
3. Lấy cookie SESSION từ response.
4. Gửi GET endpoint được bảo vệ với cookie đó.
5. Xác minh endpoint nhận đúng username.
6. Gửi request tiếp theo với cùng cookie và xác minh context vẫn được khôi phục.
7. Logout hoặc invalidate session.
8. Gửi lại cookie cũ và xác minh request trở thành unauthenticated.

Ví dụ lấy cookie:

~~~java
EntityExchangeResult<byte[]> loginResult =
        webTestClient.post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "alice")
                        .with("password", "test-password"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

ResponseCookie sessionCookie =
        loginResult.getResponseCookies().getFirst("SESSION");

assertThat(sessionCookie).isNotNull();
~~~

Đây là khung minh họa. Form login có thể yêu cầu CSRF token; test cần lấy token hoặc dùng SecurityMockServerConfigurers.csrf() theo cấu hình test. Success handler cũng có thể trả 200 thay vì redirect, nên assertion status phải khớp hợp đồng ứng dụng.

Dùng cookie nhận được để gửi request tiếp theo:

~~~java
webTestClient.get()
        .uri("/api/me")
        .cookie("SESSION", sessionCookie.getValue())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.username").isEqualTo("alice");
~~~

Nếu cookie name được cấu hình khác, dùng tên thực tế. Không hard-code SESSION ở nhiều test helper.

### Mock user không chứng minh persistence

WebTestClient có thể dùng mock user để kiểm tra authorization:

~~~java
webTestClient.mutateWith(mockUser("alice"))
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk();
~~~

Cách này hữu ích cho test phân quyền, nhưng không chứng minh login tạo WebSession, SecurityContext được serialize hoặc cookie có thể dùng ở request sau. Cần có test đăng nhập thực sự với repository thật.

## 13. Kiểm thử giới hạn phiên tuần tự

Với maximumSessions bằng 1 và handler mặc định:

1. Login user alice ở node A, nhận cookie A.
2. Login cùng user alice ở node B, nhận cookie B.
3. Kiểm tra registry chỉ giữ phiên theo chính sách giới hạn.
4. Gửi request được bảo vệ với cookie A.
5. Xác minh phiên A đã hết hạn hoặc không còn xác thực.
6. Gửi request với cookie B và xác minh phiên mới hoạt động.

Nếu dùng PreventLoginServerMaximumSessionsExceededHandler:

1. Login ở A.
2. Login lần hai ở B.
3. Xác minh login thứ hai bị từ chối theo handler.
4. Xác minh cookie A vẫn truy cập được endpoint bảo vệ.
5. Xác minh registry không để lại session mới không mong muốn.

Không chỉ kiểm tra response login lần hai. Cần xác minh trạng thái cả phiên cũ và phiên mới.

### Kiểm tra giới hạn theo role

Nếu admin có tối đa ba phiên và user thường có một phiên, test các trường hợp:

- User thường: login lần hai làm phiên cũ hết hạn hoặc bị từ chối.
- Admin: ba phiên được chấp nhận, phiên thứ tư áp dụng exceeded handler.
- User có quyền unlimited: không bị giới hạn theo SessionLimit.
- User đổi role sau khi đã đăng nhập: xác định policy có được tính lại ở lần authentication tiếp theo hay cần invalidate session hiện tại.

## 14. Kiểm thử nhiều node và registry dùng chung

Đây là test quan trọng nhất khi triển khai WebFlux nhiều instance.

Mô hình:

~~~text
                 Client
                   |
              Load balancer
               /         \
              v           v
         WebFlux A     WebFlux B
              |           |
              +-----+-----+
                    |
             Redis Indexed WebSession
                    |
        SpringSessionBackedReactiveSessionRegistry
~~~

Kịch bản:

1. Login alice ở A.
2. A lưu WebSession và SecurityContext vào Redis.
3. Login alice lần hai ở B.
4. B tra registry backed by Redis và nhìn thấy phiên từ A.
5. Handler áp dụng chính sách maximumSessions.
6. Request tiếp theo dùng cookie A/B đến node bất kỳ.
7. Chỉ phiên còn hiệu lực được xác thực.

Để test có giá trị:

- A và B phải là hai application instance độc lập.
- Cùng Redis endpoint và namespace.
- Cùng serializer và repository type.
- Cùng cấu hình Spring Security.
- Cùng principal mapping.
- Cùng reactive registry implementation.
- Không dùng InMemoryReactiveSessionRegistry riêng trên mỗi node.
- Không để sticky session giữ toàn bộ request ở một node.

Nếu test chỉ chạy hai WebTestClient trên cùng một application context, nó chưa chứng minh registry hoạt động xuyên JVM.

## 15. Kiểm thử authentication flow tùy chỉnh

Spring Security tự tích hợp concurrent session control vào các authentication mechanism được hỗ trợ như Form Login, OAuth2 Login và HTTP Basic. Cơ chế này móc vào authentication success handlers.

Nếu ứng dụng cấu hình custom ServerAuthenticationSuccessHandler thay thế danh sách handler mặc định, concurrent session control có thể không còn được gọi như mong đợi.

Khi thêm handler tùy chỉnh, hãy thêm vào danh sách handler được cấu hình thay vì vô tình thay thế các handler do session concurrency DSL đăng ký. Trong các version có API consumer cho authenticationSuccessHandler, có thể thêm handler vào danh sách hiện có.

Với custom WebFilter tự xác thực:

- Xác định filter có gọi đúng authentication success handlers không.
- Đăng ký session information sau authentication thành công.
- Lưu SecurityContext vào repository.
- Xác minh principal index được tạo.
- Kiểm thử maximum sessions khi login qua flow tùy chỉnh.
- Không chỉ test form login nếu production dùng custom OAuth callback hoặc token exchange.

Một flow xác thực tự viết có thể lưu SecurityContext nhưng bỏ qua ReactiveSessionRegistry. Khi đó người dùng vẫn đăng nhập được nhưng giới hạn phiên không hoạt động.

## 16. Kiểm thử giới hạn phiên đồng thời thật sự

Hai login xảy ra gần như đồng thời khác với hai login tuần tự. Nếu cả hai request cùng kiểm tra registry trước khi một request kịp đăng ký session, có thể xuất hiện race tùy implementation, repository và version.

Một test đồng thời nên:

1. Khởi chạy hai instance.
2. Chuẩn bị cùng một principal.
3. Gửi hai login request gần như đồng thời đến hai node.
4. Dùng barrier ở test để hai request bắt đầu gần nhau.
5. Chờ cả hai authentication flow hoàn tất.
6. Truy vấn registry theo principal.
7. Xác minh số phiên theo chính sách đã chọn.
8. Thử từng cookie trên endpoint bảo vệ.
9. Lặp lại test nhiều lần với cùng dependency versions.

Không dùng Thread.sleep cố định làm bằng chứng rằng login thực sự chồng lấn. Dùng barrier/latch hoặc công cụ load test để điều khiển và quan sát timing.

Nếu quy tắc kinh doanh yêu cầu giới hạn tuyệt đối ngay cả trong race login đồng thời, hãy xác minh implementation và repository đang dùng có bảo đảm admission atomic theo yêu cầu hay không. Khi cần, bổ sung cơ chế admission control dùng chung có transaction/atomic update. Không suy ra bảo đảm tuyệt đối chỉ từ một test login tuần tự.

## 17. Kiểm tra invalidate session và logout

Khi logout hoặc hết hạn session:

- WebSession phải được invalidate.
- Reactive repository phải xóa hoặc làm cho ID không còn tải được như session hợp lệ.
- Registry phải cập nhật thông tin phiên tương ứng.
- Request tiếp theo dùng cookie cũ không được khôi phục SecurityContext.
- Cookie resolver gửi cookie hết hạn hoặc xóa cookie theo cấu hình.

Một số thao tác quản trị cần thu hồi tất cả phiên của user, ví dụ đổi password hoặc phát hiện tài khoản bị xâm nhập. Có thể dùng ReactiveSessionRegistry để lấy phiên theo principal, invalidate từng WebSession và xóa khỏi WebSessionStore.

Ví dụ ý tưởng:

~~~java
Mono<Void> invalidateAllSessions(
        String username,
        ReactiveSessionRegistry registry,
        WebSessionStore webSessionStore
) {
    return registry.getAllSessions(username)
            .flatMap(information ->
                    webSessionStore.retrieveSession(information.getSessionId())
                            .flatMap(WebSession::invalidate)
                            .then(webSessionStore.removeSession(information.getSessionId()))
            )
            .then();
}
~~~

Đây là khung minh họa cần điều chỉnh theo API WebSessionStore và phiên bản cụ thể. Nếu session không còn tồn tại, xử lý empty một cách an toàn. Thao tác phải có authorization và audit; không cung cấp endpoint thu hồi session cho user tùy ý.

## 18. Khác biệt với Servlet và giới hạn JDBC

Một số cấu hình Servlet không thể sao chép sang WebFlux:

| Servlet | WebFlux |
|---|---|
| HttpSession | WebSession |
| SessionRepositoryFilter | WebSessionManager/WebSessionStore |
| SessionRepository | ReactiveSessionRepository |
| SecurityContextHolder theo ThreadLocal | ReactiveSecurityContextHolder trong Reactor Context |
| SessionRegistry | ReactiveSessionRegistry |
| @EnableRedisHttpSession | @EnableRedisWebSession hoặc @EnableRedisIndexedWebSession |
| @EnableJdbcHttpSession | Không có cấu hình JDBC WebSession reactive tương đương trong các repository built-in phổ biến |
| MockMvc | WebTestClient |

Spring Session JDBC repository tiêu chuẩn dùng JDBC đồng bộ và Servlet HttpSession. Không gắn @EnableJdbcHttpSession vào WebFlux rồi kỳ vọng WebSession hoạt động reactive.

Các implementation ReactiveSessionRepository được cung cấp phổ biến gồm reactive map và reactive Redis. Nếu ứng dụng cần WebFlux với session lưu relational database, phải đánh giá custom ReactiveSessionRepository dùng driver reactive (ví dụ R2DBC) hoặc thiết kế phù hợp khác; không gọi JDBC blocking trên event-loop.

ReactiveMapSessionRepository phù hợp test hoặc tiện ích trong một process, không phải kho session cluster bền vững nếu dùng ConcurrentHashMap cục bộ.

## 19. Kiểm thử expiration và principal index

Concurrent session control phụ thuộc dữ liệu registry và trạng thái WebSession. Hãy kiểm tra:

- Session hết hạn có bị loại khỏi kết quả tìm principal.
- Session bị invalidate có biến mất khỏi registry.
- Index principal được cập nhật khi SecurityContext được lưu.
- Index không giữ session ID đã xóa.
- Cleanup task hoạt động theo cấu hình Redis indexed repository.
- TTL và maxInactiveInterval phù hợp.
- Một request không hoạt động đủ lâu không tiếp tục được xác thực.

Redis indexed reactive repository có cơ chế index và cleanup riêng. Keyspace notifications hoặc cleanup task có thể tác động thời điểm metadata được dọn. Test không nên giả định cleanup vật lý diễn ra đúng tức thì; quan trọng là request mới không được khôi phục một session đã hết hạn.

Để test expiration ổn định, dùng timeout ngắn trong profile test và xác minh qua repository/API. Không phụ thuộc một key nội bộ hoặc thời gian sleep dài không ổn định.

## 20. Những lỗi thường gặp

**Dùng SecurityContextHolder trong WebFlux.**  
ThreadLocal không bảo đảm truyền qua reactive chain. Dùng ReactiveSecurityContextHolder.

**Test StepVerifier pass rồi kết luận SecurityContext đã được lưu.**  
StepVerifier chỉ chứng minh context trong subscription. Cần WebTestClient và cookie để kiểm tra persistence qua request.

**Dùng NoOpServerSecurityContextRepository nhưng mong đăng nhập duy trì.**  
NoOp không lưu context giữa request. Dùng WebSessionServerSecurityContextRepository nếu cần cookie session.

**Chỉ cấu hình WebSession repository mà quên HTTP Basic.**  
HTTP Basic có thể dùng NoOp mặc định. Cấu hình repository cho authentication filter tương ứng.

**Dùng InMemoryReactiveSessionRegistry trong cluster.**  
Registry là local process. Dùng SpringSessionBackedReactiveSessionRegistry với repository có principal index.

**Dùng @EnableRedisWebSession rồi mong tìm tất cả session theo user.**  
Repository cơ bản không có principal index như indexed repository. Dùng @EnableRedisIndexedWebSession khi cần registry theo principal.

**Chỉ nâng Spring Security mà không nâng Spring Session phù hợp.**  
Reactive concurrent control có từ Security 6.3; Spring Session-backed registry có từ Spring Session 3.3. Kiểm tra dependency alignment.

**Principal index không khớp username.**  
Registry tìm theo giá trị index. Xác minh custom principal và cách biểu diễn principal name.

**Custom success handler làm mất concurrency control.**  
Giữ lại handler mặc định hoặc thêm handler theo API consumer được version hỗ trợ.

**Dùng Servlet SessionCreationPolicy hoặc HttpSession trong WebFlux.**  
Chọn WebSession và ServerSecurityContextRepository phù hợp.

**Dùng JDBC blocking trong reactive request.**  
Nó có thể chặn event-loop. Chọn reactive store hoặc cô lập blocking work theo thiết kế có kiểm soát.

**Chỉ test login tuần tự.**  
Không phát hiện race giữa hai authentication flow đồng thời trên nhiều node.

## 21. Checklist trước khi phát hành

### SecurityContext

- SecurityContext được lưu bằng WebSession repository nếu cần đăng nhập duy trì.
- ReactiveSecurityContextHolder đọc đúng Authentication trong Mono/Flux.
- Request tiếp theo với cookie hợp lệ khôi phục đúng principal.
- Session ID được đổi theo session fixation protection khi lưu context.
- NoOp repository chỉ dùng cho flow stateless.
- HTTP Basic, Form Login và OAuth2 Login có repository phù hợp.
- Custom authentication flow được kiểm thử riêng.

### Concurrent sessions

- Spring Security version hỗ trợ reactive concurrent session control.
- ReactiveSessionRegistry được cấu hình đúng.
- InMemory registry chỉ dùng khi chấp nhận phạm vi một JVM.
- Multi-node dùng SpringSessionBackedReactiveSessionRegistry.
- Spring Session version hỗ trợ registry-backed reactive từ 3.3.
- Repository hỗ trợ ReactiveFindByIndexNameSessionRepository.
- Principal index được tạo và truy vấn đúng.
- Maximum sessions và exceeded handler phù hợp policy.
- Test phiên cũ và phiên mới sau login vượt giới hạn.
- Test login đồng thời trên hai node.

### WebFlux và repository

- Dùng WebSession, không dùng HttpSession.
- Dùng @EnableRedisWebSession hoặc @EnableRedisIndexedWebSession đúng nhu cầu.
- Cookie resolver thống nhất giữa các node.
- Redis namespace, serializer và TTL tương thích.
- Không dùng JDBC blocking như reactive session repository.
- WebTestClient test chạy với filter chain và repository thật.
- Không log cookie hoặc Session ID.
- Có test logout, invalidate và expiration.

## 22. Tự kiểm tra

1. SecurityContext trong WebFlux được truyền qua cơ chế nào?
2. ReactiveSecurityContextHolder khác SecurityContextHolder ra sao?
3. ServerSecurityContextRepository có trách nhiệm gì?
4. Khi nào nên dùng WebSessionServerSecurityContextRepository?
5. Khi nào nên dùng NoOpServerSecurityContextRepository?
6. Vì sao StepVerifier không đủ để chứng minh SecurityContext được lưu giữa request?
7. Reactive concurrent session control có từ Spring Security version nào?
8. SpringSessionBackedReactiveSessionRegistry có từ Spring Session version nào?
9. Vì sao InMemoryReactiveSessionRegistry không đủ cho cluster?
10. Vì sao cần ReactiveRedisIndexedSessionRepository?
11. Principal index có vai trò gì trong giới hạn phiên?
12. Handler mặc định xử lý thế nào khi số phiên vượt giới hạn?
13. Custom authentication success handler có thể ảnh hưởng concurrent session control ra sao?
14. Vì sao @EnableJdbcHttpSession không phải cấu hình WebFlux?
15. Cần kiểm tra gì khi hai login diễn ra đồng thời trên hai node?

### Gợi ý trả lời

1. Reactor Context, thông qua ReactiveSecurityContextHolder.
2. ReactiveSecurityContextHolder đọc context theo subscription; SecurityContextHolder thường dựa trên ThreadLocal của imperative/Servlet flow.
3. Tải và lưu SecurityContext cho ServerWebExchange giữa các request.
4. Khi ứng dụng cookie-based cần lưu context trong WebSession và khôi phục ở request sau.
5. Khi mỗi request tự xác thực, ví dụ API stateless dùng bearer token.
6. Vì StepVerifier chỉ kiểm tra Reactor Context trong một pipeline, không kiểm tra WebSession repository hoặc cookie.
7. Spring Security 6.3.
8. Spring Session 3.3.
9. Vì registry giữ dữ liệu trong bộ nhớ một JVM, node khác không nhìn thấy.
10. Vì nó cung cấp principal index để tìm các phiên của cùng người dùng.
11. Registry dùng index để liệt kê và đếm phiên theo principal.
12. Mặc định hết hạn các phiên ít được dùng gần đây nhất; có thể cấu hình handler từ chối login mới.
13. Nếu thay thế success handlers mặc định, handler đăng ký phiên có thể không được gọi.
14. Nó tích hợp Servlet HttpSession/JDBC đồng bộ; WebFlux dùng WebSession và ReactiveSessionRepository.
15. Registry dùng chung, principal index, trạng thái cả hai cookie, race giữa authentication flows và exceeded handler.

## Kết luận

Trong WebFlux, SecurityContext được đưa vào Reactor Context để các thành phần reactive đọc được; muốn duy trì đăng nhập giữa các request, Spring Security phải lưu context vào WebSession thông qua WebSessionServerSecurityContextRepository. Spring Session thay WebSession mặc định bằng repository reactive như Redis, giúp nhiều node khôi phục cùng trạng thái phiên.

Reactive concurrent session control có từ Spring Security 6.3. Registry mặc định InMemoryReactiveSessionRegistry chỉ theo dõi trong một JVM. Để giới hạn phiên trên nhiều node, dùng Spring Session 3.3+ với SpringSessionBackedReactiveSessionRegistry và repository có principal index, thường là @EnableRedisIndexedWebSession. Kiểm thử cần bao gồm Reactor Context, login và protected request qua cookie, session limit, logout, principal index và hai node dùng chung Redis. Không nhầm API Servlet/JDBC với WebFlux; hãy căn chỉnh đúng version và xác minh cả login tuần tự lẫn login đồng thời trước khi phát hành.

