# Lan truyền ngữ cảnh xác thực trong chuỗi reactive — Spring WebFlux và Spring Security

Trong Spring MVC truyền thống, thông tin người dùng đăng nhập thường được truy cập qua SecurityContextHolder, dựa trên một chiến lược gắn SecurityContext với thread đang chạy. Với Spring WebFlux, một request có thể tiếp tục trên nhiều thread khác nhau do publishOn, subscribeOn, I/O bất đồng bộ hoặc sự kiện mạng. Vì thế, việc gắn identity vào ThreadLocal không đủ để giữ đúng người dùng trong suốt một reactive pipeline.

Spring Security reactive dùng **Reactor Context**, được gắn với subscription, để lưu và chuyển tiếp SecurityContext. API trung tâm là ReactiveSecurityContextHolder. Khi WebFlux Security đã xác thực một HTTP request, security filters đưa context vào reactive chain; downstream service, reactive method security và các thao tác bất đồng bộ cùng thuộc chain có thể đọc đúng Authentication mà không phụ thuộc tên thread.

Bài học thuộc nhóm **Tích hợp bảo mật**, tập trung vào cách context được tạo, đọc, thay đổi và truyền qua các toán tử; vị trí của contextWrite; ranh giới subscription; tính an toàn khi gọi WebClient; và cách kiểm thử để tránh nhầm người dùng giữa các request đồng thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt SecurityContext, Authentication, principal và GrantedAuthority.
- Hiểu vì sao SecurityContextHolder kiểu ThreadLocal không phải cách tiếp cận chính cho WebFlux.
- Giải thích Reactor Context là dữ liệu bất biến theo subscription, không phải global map.
- Đọc context bằng ReactiveSecurityContextHolder.getContext().
- Cài context cho một subscriber bằng withAuthentication() và withSecurityContext().
- Xóa context có phạm vi bằng clearContext().
- Hiểu hướng truyền context từ downstream tới upstream qua contextWrite().
- Giải thích khả năng bảo toàn context qua map, flatMap, publishOn và subscribeOn.
- Nhận diện ranh giới subscribe thủ công, detached task và CompletableFuture.
- Hiểu cách Spring Security WebFilter chain cung cấp Authentication cho WebFlux.
- Dùng reactive method security với @EnableReactiveMethodSecurity và @PreAuthorize.
- Phân biệt truyền Authentication nội bộ với chuyển bearer token sang upstream bằng WebClient.
- Tránh lộ credential, rò rỉ ngữ cảnh hoặc hành vi giả mạo principal.
- Viết ứng dụng Spring Boot WebFlux Java 17+ và các kiểm thử xác thực/context.

## 2. Các khái niệm security cốt lõi

SecurityContext là đối tượng chứa Authentication đang hoạt động cho một phạm vi xử lý. Authentication thường có:

- Principal: danh tính đã được xác thực, ví dụ user ID hoặc UserDetails.
- Credentials: dữ liệu xác thực hoặc token, có thể đã được làm rỗng sau authentication.
- Authorities: các quyền như ROLE_USER hoặc SCOPE_orders.read.
- Authenticated flag: trạng thái token có được xác thực hay chưa.
- Details: thông tin phụ trợ được hệ thống cung cấp.

Ví dụ truy xuất tên và authority khi đã có Authentication:

~~~java
String username = authentication.getName();

List<String> permissions = authentication.getAuthorities()
    .stream()
    .map(GrantedAuthority::getAuthority)
    .toList();
~~~

getName() là tên danh tính từ Authentication. Không suy ra rằng một username trong request body có giá trị xác thực tương đương. Server phải dùng Authentication do security layer thiết lập sau khi kiểm tra credential.

### SecurityContextHolder và ReactiveSecurityContextHolder

| Mô hình | Cách truy cập | Phạm vi dữ liệu |
| --- | --- | --- |
| Servlet/MVC phổ biến | SecurityContextHolder.getContext() | Thường dựa vào ThreadLocal theo security strategy |
| WebFlux reactive | ReactiveSecurityContextHolder.getContext() | Reactor Context thuộc subscriber |
| Truyền thủ công | contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth)) | Chỉ các upstream operator trong phạm vi của contextWrite |

Không dùng SecurityContextHolder.getContext() như nguồn xác thực mặc định bên trong WebFlux reactive chain. Khi scheduler chuyển thread, ThreadLocal có thể rỗng hoặc chứa dữ liệu không còn phù hợp. Kể cả khi một ứng dụng bật cơ chế context-propagation bridge, code bảo mật vẫn nên dùng API reactive chính thức.

## 3. Reactor Context không phải ThreadLocal

Reactor Context là một context key-value bất biến về mặt cấu trúc, liên kết với Subscriber tại thời điểm subscribe. Nó phù hợp cho dữ liệu xuyên qua nhiều operator mà không cần thay chữ ký của mọi method.

~~~text
Incoming HTTP request
      |
      v
Spring Security filters: xác thực user alice
      |
      v
Subscriber Context chứa Mono<SecurityContext>
      |
      +--> Controller
      |       |
      |       +--> Service
      |               |
      |               +--> flatMap database
      |               +--> publishOn scheduler khác
      |
      +--> Reactive method authorization
      |
      v
HTTP response
~~~

Các tính chất cần nhớ:

1. Context gắn với một subscription, không gắn với toàn JVM.
2. Context không phải một biến static/global.
3. Hai request đồng thời có thể có SecurityContext khác nhau trên cùng thread.
4. Context được đặt tại subscription boundary hoặc qua contextWrite.
5. contextWrite ảnh hưởng đến các operator ở phía upstream của nó.
6. map, flatMap và các operator reactive thông thường có thể tiếp cận context khi nằm cùng chuỗi subscription.
7. Tạo một subscription mới độc lập bằng subscribe() có thể khiến bạn mất context ban đầu.

Reactor Context bất biến không có nghĩa SecurityContext hoặc Authentication được đặt bên trong là đối tượng bất biến. Tránh sửa Authentication dùng chung giữa nhiều subscriber; ưu tiên tạo context mới cho phạm vi xác thực mới.

## 4. API ReactiveSecurityContextHolder

Spring Security cung cấp class:

~~~java
org.springframework.security.core.context.ReactiveSecurityContextHolder
~~~

Các method quan trọng:

| API | Kiểu trả về | Công dụng |
| --- | --- | --- |
| getContext() | Mono<SecurityContext> | Đọc security context của subscriber |
| withAuthentication(Authentication) | Context | Tạo Reactor Context có SecurityContext từ Authentication |
| withSecurityContext(Mono<? extends SecurityContext>) | Context | Tạo Reactor Context lưu Mono SecurityContext |
| clearContext() | Function<Context, Context> | Loại security context khỏi Reactor Context trong phạm vi áp dụng |

### Đọc context

~~~java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Trong một subscription không có SecurityContext, getContext() có thể hoàn tất rỗng. Đừng mặc định rằng một object xác thực luôn tồn tại.

### Thiết lập context ở một pipeline test

~~~java
Authentication alice =
    new UsernamePasswordAuthenticationToken(
        "alice",
        "n/a",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Kết quả onNext: alice, sau đó onComplete.

withAuthentication() không ghi Authentication vào một static variable. Nó tạo một Context dùng bởi contextWrite của subscription cụ thể.

### Thiết lập bằng Mono<SecurityContext>

~~~java
SecurityContext securityContext =
    new SecurityContextImpl(alice);

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(
        ReactiveSecurityContextHolder.withSecurityContext(
            Mono.just(securityContext)));
~~~

Đây là cách tường minh khi có SecurityContext đã được tạo hoặc cần cung cấp nó theo một Mono.

### Xóa context trong phạm vi

~~~java
Mono<String> noSecurityContext =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous-for-demo")
        .contextWrite(ReactiveSecurityContextHolder.clearContext())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Kết quả: anonymous-for-demo. clearContext() loại security key khỏi context mà phần upstream đọc được. Ví dụ này chỉ minh họa scope; không dùng clearContext để lách authentication/authorization trong endpoint production.

## 5. Khi nào context thực sự được đọc?

Reactor publisher thường lazy. Code tạo Mono chưa chạy logic truy vấn ReactiveSecurityContextHolder.

~~~java
Mono<String> operation =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Lúc tạo operation, không cần có một thread mang user. Tại thời điểm subscription, operator mới truy vấn Reactor Context của subscriber đó.

~~~java
Mono<String> aliceOperation = operation.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice));

Mono<String> bobOperation = operation.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bob));
~~~

Hai publisher có thể dùng cùng định nghĩa operation nhưng đọc các context khác nhau khi được subscribe. Điều này quan trọng cho an toàn multi-user và multi-tenant.

### Không lấy current principal ở lúc tạo bean

Không viết:

~~~java
@Bean
MyService myService() {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    return new MyService(current);
}
~~~

Bean singleton thường được tạo ở startup, không ở một HTTP request cụ thể. Nếu lưu Authentication vào singleton field, bạn có thể dùng sai identity cho mọi request sau đó.

Hãy lấy context tại thời điểm thực thi request, bên trong Mono/Flux, hoặc truyền user ID sau khi đã được xác thực vào service method.

## 6. contextWrite truyền context theo hướng nào?

Reactor Context được truyền từ subscriber ở phía downstream về các operator upstream khi subscription được thiết lập.

~~~text
Source (upstream)
      |
      v
flatMap(...)
      |
      v
contextWrite(withAuthentication(alice))
      |
      v
Subscriber (downstream)

Context được cung cấp ngược chiều từ subscriber tới source.
Data và tín hiệu onNext chảy từ source về subscriber.
~~~

Một ví dụ đúng:

~~~java
Mono<String> username =
    Mono.just("start")
        .flatMap(ignored ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName))
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Kết quả: alice. contextWrite đứng sau flatMap theo code, nhưng nó cung cấp context cho toàn bộ phần upstream (gồm flatMap).

### Đặt contextWrite sai vị trí

~~~java
Mono<String> result =
    Mono.just("start")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice))
        .flatMap(ignored ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("no-context"));
~~~

Kết quả: no-context nếu không có context nào khác từ subscriber. contextWrite chỉ làm thay đổi context mà Mono.just ở phía upstream nhìn thấy; flatMap đứng downstream nên không được cung cấp SecurityContext này.

Không phải Reactor làm mất context; đó là phạm vi áp dụng của operator được đặt không đúng nơi mong muốn.

### Quy tắc thực hành

Khi chủ động thiết lập Authentication cho toàn pipeline (thường trong test hoặc một phạm vi nội bộ có chủ đích), đặt contextWrite ở phía downstream của toàn bộ source cần đọc nó. Trong request WebFlux bình thường, để Spring Security filters thiết lập context; đừng tự đặt Authentication của request bằng dữ liệu chưa được xác thực.

## 7. Context qua map, flatMap và các nhánh bất đồng bộ

Một service có thể xây dựng pipeline nhiều bước:

~~~java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}

public Mono<String> loadGreeting() {
    return Mono.just("load")
        .flatMap(ignored -> currentUsername())
        .map(name -> "Hello " + name);
}
~~~

Nếu loadGreeting() được gọi trong subscription chứa SecurityContext của alice, kết quả là Hello alice. flatMap subscribe publisher con theo cơ chế của Reactor và chuyển context phù hợp trong chuỗi.

### publishOn và subscribeOn

~~~java
Mono<String> result =
    Mono.just("work")
        .publishOn(Schedulers.parallel())
        .flatMap(ignored -> currentUsername())
        .map(name -> "user:" + name)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Kết quả: user:alice. Việc chuyển execution thread bằng publishOn không làm mất subscriber Context.

Tương tự, khi dùng subscribeOn để chuyển thread đăng ký source, Context vẫn thuộc subscription:

~~~java
Mono<String> result = currentUsername()
    .subscribeOn(Schedulers.boundedElastic())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Không cần copy Authentication vào ThreadLocal chỉ vì operator chạy trên scheduler khác. Một giới hạn thực sự là khi code tạo một subscription hoàn toàn độc lập hoặc đi ra ngoài Reactive Streams.

## 8. Ranh giới subscription và detached task

Một lỗi phổ biến:

~~~java
public Mono<Void> triggerAction() {
    backgroundService.doWork().subscribe();
    return Mono.empty();
}
~~~

Đây là một subscription bị tách khỏi chain của HTTP request:

- Caller không còn chờ completion/error của doWork().
- Cancellation và timeout không được phối hợp đúng.
- SecurityContext của request không nhất thiết được truyền sang subscription mới.
- Exception có thể chỉ đi tới global error hook/log và khó quan sát.
- Khi request kết thúc, công việc còn chạy có thể bị bỏ quên.

Nếu công việc phải hoàn tất trong cùng request, hãy trả publisher và compose:

~~~java
public Mono<Void> triggerAction() {
    return backgroundService.doWork();
}
~~~

Nếu cần đưa công việc vào queue thực sự, hãy tạo một command chứa định danh đã xác thực (hoặc identity/provenance cần thiết), ghi command vào hệ thống queue theo một hợp đồng được xác minh, rồi xử lý dưới security boundary riêng của consumer. Đừng giả định Reactor Context của HTTP request tự vượt qua Kafka, RabbitMQ, scheduler job hoặc process khác.

## 9. CompletableFuture, callback và thư viện blocking

Reactor Context không tự trở thành ThreadLocal cho mọi callback Java bên ngoài Reactor.

Ví dụ nguy hiểm:

~~~java
CompletableFuture.supplyAsync(() ->
    SecurityContextHolder.getContext()
        .getAuthentication()
        .getName());
~~~

Một thread của common pool không nhất thiết có SecurityContext của request WebFlux; đoạn code này có thể NullPointerException hoặc trả identity sai nếu có chiến lược ThreadLocal tùy chỉnh không được quản lý.

Cách an toàn là đọc principal trong reactive pipeline rồi truyền giá trị tối thiểu cần thiết:

~~~java
public Mono<Profile> findProfile() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(username ->
            Mono.fromCallable(() -> legacyDao.findByUser(username))
                .subscribeOn(Schedulers.boundedElastic()));
}
~~~

Đây là fragment minh họa: legacyDao.findByUser là một API blocking trong ứng dụng. BoundedElastic thích hợp hơn event loop cho thao tác blocking có giới hạn; cần kiểm soát queue/thread và timeout. Không copy toàn bộ credentials sang thread blocking khi chỉ cần username.

Nếu library hỗ trợ Context Propagation hoặc Micrometer ContextSnapshot, có thể cấu hình bridge theo nhu cầu để hỗ trợ MDC, tracing hoặc một số ThreadLocal. Cơ chế này không thay đổi API chuẩn để truy vấn Spring Security trong reactive code và không bảo đảm mọi detached task đều tự có Authentication.

## 10. Spring Security tạo context trong WebFlux như thế nào?

Khi ứng dụng dùng spring-boot-starter-security và cấu hình reactive SecurityWebFilterChain, Spring Security xử lý HTTP request theo WebFilter chain:

~~~text
HTTP request
      |
      v
SecurityWebFilterChain
      |
      +-- Authentication filter:
      |     Đọc Basic/Bearer/session credential
      |     Xác thực bằng manager/provider
      |
      +-- SecurityContext persistence/loading:
      |     ServerSecurityContextRepository (theo cấu hình)
      |
      +-- ReactorContextWebFilter:
      |     Tích hợp SecurityContext vào Reactor Context
      |
      +-- Authorization:
      |     Quyết định request có được đi tiếp không
      |
      v
Annotated controller / functional route
      |
      v
Service có ReactiveSecurityContextHolder
      |
      v
Reactive repository / downstream operations
~~~

Đây là sơ đồ khái niệm, không biểu diễn thứ tự chính xác của mọi security filter. Chi tiết phụ thuộc cơ chế HTTP Basic, OAuth2 Resource Server, session, form login hoặc các filter tùy chỉnh.

Trong WebFlux Security, ReactorContextWebFilter tích hợp SecurityContext từ repository vào Reactor Context. Các authentication filter cũng có thể cung cấp context phù hợp sau khi xác thực. Application code không phải tự tạo contextWrite(withAuthentication()) cho mọi incoming HTTP request khi Security được cấu hình đúng.

### Phân biệt authentication và authorization

- **Authentication:** xác minh identity là ai.
- **Authorization:** xác minh identity có quyền làm hành động nào.

Có Authentication trong context không có nghĩa tự động có quyền thực hiện mọi thao tác. Method security hoặc authorization check vẫn phải xét GrantedAuthority, tenant, ownership và resource cần truy cập.

## 11. Đọc principal ở controller và service

Trong WebFlux controller, có một số lựa chọn:

~~~java
@GetMapping("/identity")
public Mono<String> identity(
        @AuthenticationPrincipal Mono<UserDetails> principal) {
    return principal.map(UserDetails::getUsername);
}
~~~

Đây là ví dụ injection khi principal thực tế là UserDetails; với JWT, principal thường là Jwt hoặc kiểu tùy provider, nên signature phải phù hợp. Không giả định mọi Authentication đều có principal kiểu UserDetails.

Một cách ít ràng buộc hơn là lấy Principal:

~~~java
@GetMapping("/identity-name")
public Mono<String> identityName(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
~~~

Khi logic nằm sâu trong service và không muốn phải truyền Principal xuyên mọi method, ReactiveSecurityContextHolder.getContext() là cách reactive phù hợp:

~~~java
public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

Với nghiệp vụ nhạy cảm, ưu tiên truyền user ID đã xác thực vào service/repository boundary nếu điều đó giúp làm rõ authorization và giảm phụ thuộc ambient context. Dù dùng cách nào, không lấy user ID từ query param làm quyền truy cập mặc định.

## 12. Reactive method security

Spring Security hỗ trợ @PreAuthorize trên method reactive khi bật method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfiguration {
}
~~~

Ví dụ service:

~~~java
@Service
public class ReportsService {

    @PreAuthorize("hasRole('USER')")
    public Mono<String> report() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "report-for:" + auth.getName());
    }
}
~~~

Khi caller có ROLE_USER, publisher có thể phát report-for:alice. Khi caller chỉ có ROLE_GUEST, reactive method security có thể phát AccessDeniedException; HTTP security exception handling thường ánh xạ thành 403 Forbidden.

### Điều kiện quan trọng

- Method cần được gọi thông qua Spring AOP proxy để interceptor bảo vệ.
- Với Spring Security reactive method security, method bảo vệ nên trả Mono/Flux hoặc Publisher có hỗ trợ; không trông đợi cùng semantics cho method trả String đồng bộ.
- Không tự gọi một method @PreAuthorize từ một method khác trong cùng class rồi giả định proxy luôn được áp dụng; self-invocation có thể bỏ qua advice.
- hasRole('USER') kiểm tra authority ROLE_USER theo tiền tố mặc định.
- Nếu cần kiểm tra quyền theo resource ID, bổ sung authorization theo owner/tenant hoặc permission thay vì chỉ kiểm tra role.

Method security dùng cùng Reactor Context, vì vậy một lời gọi service được compose trong HTTP request có thể đọc đúng Authentication đã được WebFlux Security thiết lập.

## 13. Khi nào dùng withAuthentication hoặc withSecurityContext?

Trong request HTTP đã qua Spring Security, thông thường bạn **không cần** tự gọi withAuthentication. Các tình huống có thể có chủ đích:

- Unit test một publisher cần Authentication.
- Reactive job có security boundary đã xác thực độc lập và cần tạo scope cục bộ.
- Đoạn code tích hợp đã xác thực credential bằng một cơ chế được tin cậy rồi muốn chuyển sang reactive API.
- Kiểm thử phương pháp context isolation và operator placement.

Ví dụ test:

~~~java
Authentication testAuth =
    new UsernamePasswordAuthenticationToken(
        "test-user",
        "unused",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

StepVerifier.create(
        service.currentName()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(testAuth)))
    .expectNext("test-user")
    .verifyComplete();
~~~

Không gọi:

~~~java
Authentication forged =
    new UsernamePasswordAuthenticationToken(
        request.getQueryParams().getFirst("username"),
        "n/a",
        AuthorityUtils.createAuthorityList("ROLE_ADMIN"));
~~~

để làm context xác thực. Bất kỳ caller nào cũng có thể gửi username=admin; đây là lỗi bảo mật nghiêm trọng. Hãy để authentication manager kiểm tra credential/identity và tạo Authentication được tin cậy.

## 14. WebClient outbound: context nội bộ không phải HTTP Authorization

Reactor Context chỉ tồn tại bên trong reactive execution của tiến trình, không tự đi qua TCP sang service khác.

Nếu controller của service A đang xử lý user alice rồi gọi service B bằng WebClient, việc service A có ReactiveSecurityContextHolder không có nghĩa service B tự nhận cùng SecurityContext. Muốn service B biết identity, phải dùng giao thức xác thực phù hợp:

- Chuyển OAuth2 access token khi hợp đồng bảo mật cho phép.
- Sử dụng token exchange hoặc on-behalf-of flow khi architecture yêu cầu.
- Dùng service identity cho machine-to-machine.
- Truyền một signed claim được tin cậy, không phải header username tùy ý.

### Bearer token propagation của Spring Security

Với reactive OAuth2 Resource Server, có thể dùng ServerBearerExchangeFilterFunction:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder
        .filter(new ServerBearerExchangeFilterFunction())
        .baseUrl("https://downstream.example.com")
        .build();
}
~~~

Đây là fragment cần các dependency OAuth2 Resource Server và import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction. Nó không nằm trong project HTTP Basic hoàn chỉnh bên dưới.

Filter tìm Authentication hiện tại từ reactive security context, rồi trích credential kiểu OAuth2 AbstractOAuth2Token để thêm Authorization: Bearer ... vào outbound request. Với HTTP Basic Authentication, không có bearer token để tự relay. Filter không tự làm mới token hết hạn.

### Cảnh báo bảo mật khi relay token

- Chỉ relay tới destination được phép; tránh chuyển user token sang host không tin cậy.
- Xác định token audience và scope có phù hợp downstream hay không.
- Không ghi access token vào log hoặc Reactor Context tùy ý.
- Không sao chép Authorization request header bừa bãi để gọi mọi URL.
- Token relay không thay thế authorization của service B.
- Đối với OAuth2 client authorization code flow, có thể cần cấu hình OAuth2AuthorizedClientManager thay vì chỉ bearer relay.

Context propagation trong ứng dụng và token propagation giữa các ứng dụng là hai vấn đề khác nhau.

## 15. Context qua parallel processing và nhiều request đồng thời

Hãy hình dung hai HTTP request chạy gần như đồng thời:

~~~text
Request A: alice -------------------+
                                    |-- Reactor event-loop X
Request B: bob ---------------------+       |
                                    |    publishOn
                                    v       |
                                Scheduler Y
                                    |
                 Alice Context --> A operators
                 Bob Context   --> B operators
~~~

Cả hai có thể chạy trên cùng thread tại các thời điểm khác nhau. Nếu code dùng ThreadLocal không được quản lý, có thể đọc sai identity hoặc null. Nếu dùng Reactor Context qua cùng subscription, mỗi request nhận context của riêng nó.

### Context độc lập theo subscription

~~~java
Mono<String> who = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> aliceFlow = who.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice));

Mono<String> bobFlow = who.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bob));
~~~

Hai publisher chia sẻ định nghĩa who nhưng có context khác nhau. Mỗi lần subscribe lấy context tương ứng.

### Parallelism không phải bằng chứng mất context

publishOn và subscribeOn thông thường bảo toàn Reactor subscriber Context trong reactive chain. Điều làm mất context thường là tạo subscription độc lập, rời khỏi Reactor API mà không chuyển dữ liệu cần thiết, hoặc đặt contextWrite sai phạm vi.

Với parallel() và runOn(), vẫn cần kiểm tra thiết kế operator và concurrency; đừng cố sửa bằng static map user ID theo thread.

## 16. Kiểm soát thay đổi Authentication và xóa context

Reactor Context là bất biến về mặt map, nhưng giá trị trong context có thể là mutable SecurityContext. Khi muốn chạy một nhánh theo identity được tin cậy khác, phải có chính sách rõ ràng.

Một số ví dụ:

~~~java
Mono<String> scoped = service.currentName()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(systemAuthentication));
~~~

Nó chỉ hợp lệ nếu systemAuthentication được tạo bởi một thành phần có quyền tương ứng, không lấy từ input không tin cậy.

Nếu cần một nhánh không có context:

~~~java
Mono<String> noContext = service.currentName()
    .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

Khi currentName() coi thiếu context là lỗi, publisher này phát lỗi. clearContext() không xóa global authentication, không đăng xuất một browser session và không thay thế logout handler. Nó chỉ sửa Context của phạm vi operator upstream.

### Không dùng context để bypass quyền

Không sửa Authentication hoặc GrantedAuthority của user để vượt qua một @PreAuthorize trong business logic. SecurityContext cần phản ánh danh tính đã được xác minh bởi security boundary; mọi quyền đặc biệt phải có chính sách, audit và kiểm tra riêng.

## 17. Ví dụ hoàn chỉnh Java 17+ Spring Boot WebFlux

Ví dụ xây dựng API có HTTP Basic authentication:

- GET /api/me: trả tên caller hiện tại qua ReactiveSecurityContextHolder.
- GET /api/async: chuyển scheduler bằng publishOn rồi đọc context trong flatMap.
- GET /api/report: được bảo vệ bằng reactive method security, cần ROLE_USER.
- Một user alice có ROLE_USER.
- Một user eve có ROLE_GUEST.

Ví dụ sử dụng Basic authentication đơn giản để tránh cấu hình OAuth2/JWT phức tạp che mất trọng tâm context propagation. Password có prefix {noop} **chỉ phục vụ môi trường học cục bộ**; không dùng cách lưu password này trong production.

### Cấu trúc project

~~~text
reactive-security-context-demo/
├── pom.xml
└── src
    ├── main/java/com/example/securitycontext
    │   ├── ReactiveContextApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── IdentityService.java
    │   └── IdentityController.java
    └── test/java/com/example/securitycontext
        └── ReactiveContextIntegrationTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>reactive-security-context-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
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
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot 3.3.5 quản lý phiên bản Spring Framework, Spring Security và Reactor tương thích với Java 17.

### ReactiveContextApplication.java

~~~java
package com.example.securitycontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
~~~

### SecurityConfiguration.java

~~~java
package com.example.securitycontext;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}password")
            .roles("USER")
            .build();

        UserDetails eve = User.withUsername("eve")
            .password("{noop}password")
            .roles("GUEST")
            .build();

        return new MapReactiveUserDetailsService(alice, eve);
    }
}
~~~

SecurityWebFilterChain yêu cầu authentication cho /api/**. HTTP Basic xác thực credential trên request và tạo Authentication của user. Method security được bật với AuthorizationManager. Code cố ý không tắt CSRF mặc định; các API minh họa đều là GET, vì vậy không có request thay đổi trạng thái cần xử lý CSRF token.

Không hardcode password và dùng {noop} trong production. Dùng password encoder phù hợp và secret/user store được quản lý an toàn.

### IdentityService.java

~~~java
package com.example.securitycontext;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class IdentityService {

    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .filter(auth ->
                auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authenticated principal is required")));
    }

    public Mono<String> nestedOnAnotherScheduler() {
        return Mono.just("work")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentUser())
            .map(username -> "async-user:" + username);
    }

    @PreAuthorize("hasRole('USER')")
    public Mono<String> userReport() {
        return currentUser()
            .map(username -> "report-for:" + username);
    }
}
~~~

Giải thích:

1. currentUser() đọc Authentication từ reactive subscriber Context, không từ ThreadLocal.
2. Mono.justOrEmpty() xử lý trường hợp SecurityContext không chứa Authentication.
3. AnonymousAuthenticationToken bị loại bỏ; service không coi anonymous principal là user đã đăng nhập.
4. switchIfEmpty() biến thiếu authentication thành exception rõ ràng, không tạo identity giả.
5. nestedOnAnotherScheduler() chuyển execution thread rồi mới gọi currentUser() trong flatMap.
6. userReport() dùng @PreAuthorize để kiểm tra quyền trước khi thực hiện logic publisher.

### IdentityController.java

~~~java
package com.example.securitycontext;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class IdentityController {

    private final IdentityService identityService;

    public IdentityController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me() {
        return identityService.currentUser()
            .map(username -> Map.of("user", username));
    }

    @GetMapping("/async")
    public Mono<Map<String, String>> async() {
        return identityService.nestedOnAnotherScheduler()
            .map(value -> Map.of("result", value));
    }

    @GetMapping("/report")
    public Mono<Map<String, String>> report() {
        return identityService.userReport()
            .map(value -> Map.of("result", value));
    }
}
~~~

Controller không đọc Username từ query param để quyết định quyền. Tất cả các response đều lấy identity từ security context do Spring Security quản lý.

## 18. Integration test: xác thực, đổi scheduler và method security

Kiểm thử sử dụng WebTestClient của Spring Boot. Các request HTTP thực tới embedded server kiểm tra security filter chain, controller và service. Các StepVerifier tests tạo scoped Authentication để xác minh ReactiveSecurityContextHolder khi không có HTTP request.

### ReactiveContextIntegrationTests.java

~~~java
package com.example.securitycontext;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveContextIntegrationTests {

    @Autowired
    private WebTestClient client;

    @Autowired
    private IdentityService identityService;

    private Authentication authentication(
            String username,
            String role) {

        return new UsernamePasswordAuthenticationToken(
            username,
            "unused",
            AuthorityUtils.createAuthorityList(role));
    }

    @Test
    void httpBasicAuthenticationIsAvailableToController() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"user\":\"alice\"}");
    }

    @Test
    void contextSurvivesSchedulerChangeAndNestedFlatMap() {
        client.get()
            .uri("/api/async")
            .headers(headers ->
                headers.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"result\":\"async-user:alice\"}");
    }

    @Test
    void reactiveMethodSecurityAllowsRoleUser() {
        client.get()
            .uri("/api/report")
            .headers(headers ->
                headers.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"result\":\"report-for:alice\"}");
    }

    @Test
    void reactiveMethodSecurityRejectsGuestRole() {
        client.get()
            .uri("/api/report")
            .headers(headers ->
                headers.setBasicAuth("eve", "password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unauthenticatedHttpRequestIsRejected() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void contextWriteProvidesAuthenticationToPublisher() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> user = identityService.currentUser()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(user)
            .expectNext("unit-alice")
            .verifyComplete();
    }

    @Test
    void identityRemainsIsolatedAcrossSubscriptions() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");
        Authentication bob =
            authentication("unit-bob", "ROLE_USER");

        Mono<String> source = identityService.currentUser();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("unit-alice")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
            .expectNext("unit-bob")
            .verifyComplete();
    }

    @Test
    void publisherKeepsContextAcrossSubscribeOn() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> user = identityService.currentUser()
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(user)
            .expectNext("unit-alice")
            .verifyComplete();
    }

    @Test
    void clearContextRemovesUpstreamAuthentication() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> user = identityService.currentUser()
            .contextWrite(ReactiveSecurityContextHolder.clearContext())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(user)
            .expectError(AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void contextWriteDoesNotAffectDownstreamFlatMap() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> result = Mono.just("work")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice))
            .flatMap(ignored ->
                ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .defaultIfEmpty("no-context"));

        StepVerifier.create(result)
            .expectNext("no-context")
            .verifyComplete();
    }
}
~~~

Các test không dùng sleep hoặc assert Thread.currentThread().getName(). Điều cần chứng minh là identity đọc qua context sau khi đổi scheduler, không phải thread có tên nào.

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q test
~~~

Khi cả 10 bài test pass, Maven kết thúc với exit code 0. Nếu không có Maven hoặc JDK 17+, cài công cụ phù hợp trước. Đây là mô tả kết quả mong đợi; không thay cho việc thực thi test trong môi trường của bạn.

## 19. Chạy ứng dụng và kiểm tra HTTP

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Mặc định embedded server nghe tại localhost:8080 nếu không cấu hình server.port khác.

### Caller alice xem danh tính

~~~bash
curl -i -u alice:password http://localhost:8080/api/me
~~~

Response status mong đợi: HTTP 200 OK.

~~~json
{"user":"alice"}
~~~

### Context qua scheduler

~~~bash
curl -i -u alice:password http://localhost:8080/api/async
~~~

Response status mong đợi: HTTP 200 OK.

~~~json
{"result":"async-user:alice"}
~~~

### Method security cho ROLE_USER

~~~bash
curl -i -u alice:password http://localhost:8080/api/report
~~~

Response status mong đợi: HTTP 200 OK.

~~~json
{"result":"report-for:alice"}
~~~

### Caller eve không có ROLE_USER

~~~bash
curl -i -u eve:password http://localhost:8080/api/report
~~~

Response status mong đợi: HTTP 403 Forbidden. Nội dung error body do Spring Boot xử lý, không giả định một JSON cố định.

### Không có credential

~~~bash
curl -i http://localhost:8080/api/me
~~~

Response status mong đợi: HTTP 401 Unauthorized; không được trả {"user":"anonymousUser"} như dữ liệu đã xác thực.

## 20. Những lỗi phổ biến khi lan truyền context

1. **Dùng SecurityContextHolder.getContext() trong service reactive.** ThreadLocal không bảo đảm đúng identity khi pipeline đổi thread; dùng ReactiveSecurityContextHolder.
2. **Lấy Authentication tại lúc tạo bean singleton.** Startup không thuộc request cụ thể; đọc ở subscription hoặc nhận user ID tin cậy qua method parameter.
3. **Gọi subscribe() thủ công trong controller/service.** Tạo subscription tách rời và phá error/cancellation/context scope; compose bằng return Mono/Flux.
4. **Đặt contextWrite trước vị trí cần đọc theo chiều code.** Operator downstream có thể không nhìn thấy context; kiểm tra hướng subscription.
5. **Cho rằng publishOn luôn làm mất context.** Trong Reactor chain thông thường subscriber Context được giữ; đừng sửa bằng static ThreadLocal.
6. **Cho rằng CompletableFuture tự nhận SecurityContext.** Code bên ngoài Reactor không mặc nhiên nhận subscriber Context; truyền thông tin tối thiểu cần thiết.
7. **Không kiểm tra Mono.empty() khi getContext() vắng mặt.** Có thể biến thiếu identity thành null hoặc hành vi ngầm; xác định rõ kết quả/error.
8. **Coi anonymous principal là user đã xác thực.** AnonymousAuthenticationToken có semantics riêng; kiểm tra policy phù hợp.
9. **Cho rằng authentication cũng là authorization.** Có user không đồng nghĩa có ROLE_USER hoặc quyền sở hữu tài nguyên.
10. **Đặt withAuthentication từ user input.** Dễ giả mạo principal và leo thang quyền; chỉ thiết lập từ authentication đáng tin cậy.
11. **Dùng @PreAuthorize nhưng method không đi qua proxy.** Self-invocation có thể bỏ qua advice; gọi qua Spring bean hoặc thiết kế lại.
12. **Dùng method security cho method đồng bộ rồi kỳ vọng Reactor Context.** Reactive method security cần publisher-compatible method; kiểm tra version và signature.
13. **Tự forward Authorization tới mọi upstream.** Có nguy cơ lộ bearer token; giới hạn destination và audience.
14. **Cho rằng ServerBearerExchangeFilterFunction hoạt động với HTTP Basic.** Filter relay OAuth2 bearer token phù hợp, không tạo bearer token từ Basic credentials.
15. **Không kiểm tra token audience/scope ở service B.** Token được relay vẫn cần authorization độc lập tại downstream.
16. **Log Authentication.toString() hoặc credentials.** Có thể lộ thông tin nhạy cảm; chỉ log user ID và event ID tối thiểu.
17. **Cache Mono<Authentication> hoặc SecurityContext toàn ứng dụng.** Có thể chia sẻ context sai user; scoped publisher chỉ nên dùng trong request/subscription.
18. **Tạo background job bằng detached subscribe và trông đợi request context.** Hãy dùng queue và security boundary riêng.
19. **Không test nhiều identity khác nhau.** Dễ bỏ sót context leakage; test alice/bob với hai subscription.
20. **Không test vị trí contextWrite.** Unit test positive và negative giúp thấy rõ upstream/downstream semantics.
21. **Dùng {noop} password trong production.** Đây chỉ là shortcut trong demo; dùng password hashing và credential store đúng chuẩn.
22. **Bỏ qua CSRF khi triển khai cookie-based browser authentication.** CORS và Reactor Context không thay thế CSRF protection; đánh giá theo cơ chế đăng nhập.

## 21. Checklist thiết kế ứng dụng bảo mật reactive

Trước khi phát hành một WebFlux API, kiểm tra:

- SecurityWebFilterChain có xác thực request trước khi controller không?
- ReactiveSecurityContextHolder được dùng thay SecurityContextHolder trong reactive logic?
- Authentication đến từ một cơ chế đáng tin cậy, không phải query param?
- Service xử lý trường hợp getContext() rỗng thế nào?
- Có phân biệt anonymous, authenticated và authorized?
- contextWrite nằm ở phía downstream của các operator cần đọc context?
- Có tạo subscribe() tách rời ngoài lifecycle HTTP request không?
- publishOn/subscribeOn và flatMap đã được test với context?
- CompletableFuture hoặc blocking library nhận user ID theo tham số rõ ràng?
- Method @PreAuthorize có được áp dụng qua Spring proxy?
- Các method được bảo vệ trả Mono/Flux phù hợp?
- WebClient outbound có relay token có chọn lọc, không gửi token tới host bất kỳ?
- Token relay có audience/scope thích hợp không?
- Có log credential hoặc raw token trong MDC/exception không?
- Khi tạo system identity, có chính sách cấp quyền và audit không?
- Unit tests có kiểm tra cùng publisher với hai Authentication khác nhau?
- HTTP integration tests có kiểm tra 200, 401 và 403?
- User identity và resource ownership được đánh giá riêng khi cần?
- Có cleanup và cancellation cho background work không?
- Production có password encoder/secret management và TLS đúng chuẩn không?

## 22. Bài tập tự kiểm tra

**Câu 1.** Vì sao ThreadLocal không đủ cho Spring WebFlux?  
**Đáp án:** Một request reactive có thể chạy qua nhiều thread; ThreadLocal không tự theo subscription.

**Câu 2.** API nào đọc SecurityContext của reactive subscriber?  
**Đáp án:** ReactiveSecurityContextHolder.getContext() trả Mono<SecurityContext>.

**Câu 3.** withAuthentication() trả về gì?  
**Đáp án:** Một Reactor Context chứa Mono<SecurityContext> mới tương ứng với Authentication được cung cấp.

**Câu 4.** contextWrite ảnh hưởng operator upstream hay downstream?  
**Đáp án:** Upstream, theo hướng truyền context của subscription.

**Câu 5.** publishOn có tự xóa Reactor Context không?  
**Đáp án:** Không trong một chuỗi Reactor thông thường; subscriber Context vẫn có thể đọc được.

**Câu 6.** Gọi subscribe() thủ công tạo vấn đề gì?  
**Đáp án:** Tạo subscription độc lập, mất phối hợp error/cancellation và có thể không còn security context của request.

**Câu 7.** Reactive method security sử dụng context nào?  
**Đáp án:** Reactor Context được ReactiveSecurityContextHolder cung cấp.

**Câu 8.** @PreAuthorize("hasRole('USER')") kiểm tra authority gì theo mặc định?  
**Đáp án:** ROLE_USER.

**Câu 9.** Nếu context không tồn tại thì getContext() sẽ ra sao?  
**Đáp án:** Mono có thể complete rỗng; service nên định nghĩa hành vi thiếu authentication phù hợp.

**Câu 10.** Reactive Context có tự đi qua WebClient sang microservice khác không?  
**Đáp án:** Không; cần cơ chế token hoặc service identity qua giao thức mạng.

**Câu 11.** ServerBearerExchangeFilterFunction dùng làm gì?  
**Đáp án:** Trong reactive OAuth2 resource server, nó lấy bearer token phù hợp từ current Authentication và gắn vào outbound HTTP request.

**Câu 12.** Có nên dùng withAuthentication để nâng quyền từ username trong request không?  
**Đáp án:** Không; đó là giả mạo authentication và tạo lỗ hổng leo thang quyền.

**Câu 13.** clearContext() có đăng xuất HTTP session không?  
**Đáp án:** Không; nó chỉ xóa security key trong phạm vi Reactor Context nơi được áp dụng.

**Câu 14.** Có thể test context bằng StepVerifier không?  
**Đáp án:** Có; dùng contextWrite(withAuthentication(testAuth)) và xác nhận kết quả khi subscribe.

**Câu 15.** Vì sao một user đã authenticated vẫn có thể bị 403?  
**Đáp án:** Vì user chưa có authority, role hoặc quyền resource mà endpoint/method yêu cầu.

## 23. Ghi nhớ

Spring Security reactive đặt SecurityContext trong Reactor Context của subscriber. ReactiveSecurityContextHolder.getContext() là API truy vấn chính; withAuthentication() và withSecurityContext() đặt context trong phạm vi được chỉ định; clearContext() xóa key trong phạm vi đó. Không lấy SecurityContextHolder ThreadLocal làm nguồn identity cho WebFlux reactive pipeline.

contextWrite tác động tới upstream; map, flatMap, publishOn và subscribeOn thông thường có thể bảo toàn subscriber Context khi toàn bộ công việc nằm trong cùng reactive chain. Ngược lại, subscribe() thủ công, background job và callback ngoài Reactor tạo ranh giới mới cần xử lý identity một cách tường minh.

Trong WebFlux HTTP, SecurityWebFilterChain xác thực và đưa context vào chain. Reactive method security kiểm tra quyền trên cùng context; authentication không thay thế authorization. Khi gọi service khác qua WebClient, Reactor Context không tự đi qua network: chỉ relay OAuth2 token tới destination được phép hoặc dùng một service identity đúng hợp đồng.

Cách kiểm tra tốt nhất là viết unit test cho contextWrite, clearContext và hai subscriber khác identity, đồng thời dùng HTTP integration test để xác nhận các kết quả 200, 401, 403 và việc bảo toàn context sau scheduler switch.

### Tài liệu tham khảo

- Spring Security, [Reactive method security](https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html).
- Spring Security, [Reactive WebFlux security](https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html).
- Spring Security Javadoc, [ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).
- Spring Security, [OAuth2 Resource Server – Bearer Token Propagation](https://docs.spring.io/spring-security/reference/6.3/reactive/oauth2/resource-server/bearer-tokens.html).
- Project Reactor, [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- Project Reactor, [Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
- Spring Framework, [Annotated Controllers and Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html).
- Spring Boot, [Testing Web Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
