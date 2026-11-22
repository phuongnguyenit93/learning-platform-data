# Thay SecurityContextHolder và ThreadLocal bằng ReactiveSecurityContextHolder trong Spring Security WebFlux

## 1. Mục tiêu và bối cảnh chuyển đổi

Khi chuyển một ứng dụng Spring Security từ Servlet/Spring MVC sang WebFlux (Reactive), việc đọc người dùng đăng nhập bằng SecurityContextHolder.getContext().getAuthentication() trong service thường không còn đáng tin. Lý do: mô hình reactive không gắn toàn bộ xử lý một request với một thread cố định. Các bước của một chuỗi Mono/Flux có thể chạy trên các thread khác nhau; cùng một event-loop thread cũng có thể phục vụ nhiều request.

Bài này hướng dẫn cách chuyển sang **ReactiveSecurityContextHolder**, hiểu cách Authentication nằm trong **Reactor Context theo từng subscriber**, sửa API/service để trả Mono/Flux, giữ context qua các toán tử reactive, kiểm tra bằng StepVerifier và xử lý các ranh giới nơi context có thể mất.

Sau khi học, có thể:
- Phân biệt SecurityContextHolder (thường dựa ThreadLocal trong luồng imperative) và ReactiveSecurityContextHolder (dựa Reactor Context).
- Đọc SecurityContext/Authentication đúng lúc subscription, không đọc sớm ở lúc lắp chuỗi.
- Dùng getContext(), withAuthentication(), withSecurityContext() và clearContext() đúng chức năng.
- Chuyển service, WebFlux handler và phương thức có security annotation mà không dùng block()/subscribe() tùy tiện.
- Phân tích hiện tượng principal=null, 401/403 bất thường, context rò giữa request hoặc bị mất khi gọi thư viện bất đồng bộ ngoài Reactor.

**Phạm vi:** Spring Security cho WebFlux/reactive, Java 17+, Project Reactor. Các đoạn mã thuộc ứng dụng Maven/Gradle có spring-boot-starter-webflux và spring-boot-starter-security (và reactor-test, JUnit Jupiter khi kiểm thử). Mã minh họa là các lớp hoặc đoạn dùng bên trong project Spring phù hợp, không phải chương trình chỉ cần JDK mà biên dịch bằng javac đơn thuần.

## 2. Khác biệt cốt lõi: dữ liệu gắn với thread hay subscriber?

### Kiểu imperative trước đây

Trong ứng dụng Servlet, Spring Security thường chuẩn bị SecurityContextHolder cho thread xử lý request. Code quen thuộc:

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
String username = auth.getName();
~~~

Trong một đoạn thực thi đồng bộ thuộc chuỗi Servlet Security chuẩn, cách đọc này thường hợp lệ. Nhưng khi di chuyển nguyên đoạn đó sang WebFlux, các tình huống lỗi thường xuất hiện:
- Lúc lắp Mono, security context của request chưa tồn tại hoặc chưa được khôi phục cho thread hiện tại.
- Một bước xử lý chạy trên thread khác sau subscribeOn/publishOn hoặc một sự kiện I/O.
- Event-loop thread được tái sử dụng liên tục cho các request độc lập.
- Một lời gọi callback/CompletableFuture/@Async tự tạo luồng thực thi ngoài subscription hiện tại.

ThreadLocal lưu theo thread, không tự di chuyển theo một subscription reactive. Tự đặt SecurityContextHolder.setContext(...) ở đầu request cũng có thể gây rò thông tin giữa người dùng nếu lifecycle và clear không đúng hoặc bị tái sử dụng thread.

### Kiểu reactive đúng

ReactiveSecurityContextHolder cất một Mono<SecurityContext> trong Reactor Context, tức cấu trúc ngữ cảnh gắn với một **Subscriber**. Spring Security WebFlux đưa security context vào subscriber khi xử lý qua filter chain thích hợp. Code đọc:

~~~java
Mono<Authentication> currentAuthentication =
        ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()));
~~~

Giá trị Authentication chỉ được đọc khi Mono được subscribe theo context của request hiện tại. Nếu không có context/authentication, publisher có thể hoàn tất rỗng. Không giả định mỗi request đều có người dùng đăng nhập.

| Tiêu chí | Servlet/imperative | WebFlux/reactive |
| --- | --- | --- |
| Nguồn security context | SecurityContextHolder, chiến lược thường là ThreadLocal | ReactiveSecurityContextHolder qua Reactor Context |
| Phạm vi chính | Thread đang thực thi | Subscriber và chuỗi operators |
| Đọc thông tin | Đồng bộ: Authentication hoặc null | Bất đồng bộ: Mono<SecurityContext>, Mono<Authentication> |
| Đổi scheduler | ThreadLocal không tự bảo đảm có giá trị | Context được truyền qua các toán tử Reactor chuẩn trong cùng subscription |
| Bước tích hợp | FilterChain Servlet | SecurityWebFilterChain và cơ chế context của Spring Security WebFlux |
| Sai lầm hay gặp | Quên clear ThreadLocal khi tự quản lý | block()/subscribe() giữa chừng, cache principal, mất context ở API bên ngoài Reactor |

**Điểm then chốt:** Reactor Context là cơ chế dữ liệu theo chuỗi đăng ký, không phải bản sao của ThreadLocal và không phải một biến toàn cục. Sự tồn tại của authentication trong context cũng chưa có nghĩa là một thao tác đã được **ủy quyền**; phân quyền vẫn phải do SecurityWebFilterChain, method security hoặc logic được thiết kế rõ ràng bảo vệ.

## 3. Nhận diện chính xác lỗi trong code cũ

### Lỗi 1: Trả String đồng bộ từ service

~~~java
// Mẫu imperative không phù hợp khi gọi từ WebFlux:
public String currentUsername() {
    return SecurityContextHolder.getContext()
            .getAuthentication().getName();
}
~~~

Trong WebFlux, getAuthentication() có thể null, hoặc code tình cờ nhìn thấy context không thuộc subscription hiện tại. Cách sửa không phải chỉ thêm null-check; cần đổi contract thành Mono<String>.

### Lỗi 2: Đọc SecurityContextHolder trước khi tạo Mono

~~~java
// Code sai phạm vi: gọi ngay khi hàm được thực thi.
public Mono<String> username() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    return Mono.just(auth.getName());
}
~~~

Mono.just(...) đánh giá tham số ngay tại thời điểm lắp publisher, khác với việc đọc Reactive Context lúc subscription. Thay Mono.just(...) bằng Mono.defer(...) mà **vẫn đọc ThreadLocal** cũng không sửa nguyên nhân: code có thể chạy trên một thread không có SecurityContextHolder phù hợp.

### Lỗi 3: Lưu Authentication vào biến instance/singleton

~~~java
// Không lưu principal của request trên field của @Service singleton.
private Authentication currentAuthentication;
~~~

Các request có thể chạy đồng thời; field dùng chung dễ khiến request A đọc thông tin request B. Cũng không được dùng static field hoặc Map toàn cục như phương tiện giữ "người dùng hiện tại".

### Lỗi 4: Tự subscribe rồi trả kết quả khác

~~~java
// Detached subscription: không dùng trong handler để lấy principal.
ReactiveSecurityContextHolder.getContext()
        .subscribe(context -> doSomething(context.getAuthentication()));
return Mono.empty();
~~~

subscribe() tạo subscription riêng, thường tách khỏi security context và lifecycle của request; lỗi không còn được propagate qua handler. Thay bằng flatMap/map trong chuỗi được return cho WebFlux.

## 4. Bốn API quan trọng của ReactiveSecurityContextHolder

Lớp org.springframework.security.core.context.ReactiveSecurityContextHolder cung cấp:

| API | Kiểu trả về | Chức năng |
| --- | --- | --- |
| getContext() | Mono<SecurityContext> | Lấy context từ Reactor Context ở thời điểm subscription; có thể không phát ra phần tử. |
| withAuthentication(authentication) | reactor.util.context.Context | Tạo entry Reactor Context từ Authentication đã được xác thực/thiết lập đúng. |
| withSecurityContext(monoSecurityContext) | reactor.util.context.Context | Đặt publisher Mono<? extends SecurityContext> vào Reactor Context. |
| clearContext() | Function<Context,Context> | Bỏ entry reactive security context trong **phạm vi chuỗi** dùng contextWrite. |

Ví dụ đặt authentication cho **một subscription được kiểm soát**, thường dùng trong test:

~~~java
Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
        "alice", null, AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");

Mono<String> testFlow = username.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Khi subscribe testFlow, kết quả là "alice". Khi subscribe trực tiếp username từ môi trường không có security context, kết quả là "anonymous". Ví dụ trên giả định các class Spring Security/Reactor đã được import vào dự án. **Không** sử dụng withAuthentication() để đánh dấu một username do client gửi là "đã đăng nhập"; Authentication phải đến từ bước xác thực hợp lệ.

Đối với publisher đã có SecurityContext đã thiết lập từ cơ chế xác thực:

~~~java
Mono<SecurityContext> verifiedContext = obtainVerifiedSecurityContext();

return securedWork().contextWrite(
        ReactiveSecurityContextHolder.withSecurityContext(verifiedContext));
~~~

Đây là mã cấu trúc minh họa, không phải đoạn độc lập: obtainVerifiedSecurityContext() phải là bước xác thực có thật, securedWork() phải trả Publisher và mọi xử lý lỗi/cancel phải được thiết kế. Trong ứng dụng thông thường, **Spring Security tự đưa context vào pipeline**; không tự chèn context vào mỗi service.

Khi cần chủ ý xóa quyền truy cập trong một đoạn:

~~~java
Mono<String> withoutSecurityContext = currentUserService.currentUsername()
        .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

Đoạn đó không nhìn thấy security context upstream. clearContext() chỉ tác động ở phạm vi chuỗi reactive đó; **không tương đương với logout**, không thu hồi JWT, không xóa session hoặc hủy SecurityContextRepository. Logout phải dùng cơ chế logout, vô hiệu hóa session/token và chính sách lưu trữ phù hợp.

## 5. Ví dụ service hoàn chỉnh: lấy tên người dùng theo subscriber

Đây là lớp Java 17+ đặt trong src/main/java/example/security/CurrentUserService.java của ứng dụng Spring Boot WebFlux:

~~~java
package example.security;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentUserService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx ->
                        Mono.justOrEmpty(ctx.getAuthentication()))
                .filter(this::isRealAuthenticatedUser)
                .map(Authentication::getName)
                .switchIfEmpty(Mono.error(
                        new AuthenticationCredentialsNotFoundException(
                                "Authentication required")));
    }

    private boolean isRealAuthenticatedUser(Authentication authentication) {
        return authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

Các điểm cần hiểu:
1. **Kiểu trả Mono<String>**: controller/service gọi từ reactive pipeline sẽ nhận kết quả lúc subscribe, không đòi đọc String ngay.
2. **Mono.justOrEmpty(ctx.getAuthentication())**: SecurityContext có thể tồn tại nhưng getAuthentication() trả null; dùng map(SecurityContext::getAuthentication) trực tiếp với giá trị null sẽ gây lỗi theo hợp đồng Reactive Streams. justOrEmpty xử lý null như empty đúng ngữ nghĩa.
3. **Đừng chỉ kiểm tra isAuthenticated()**: Một AnonymousAuthenticationToken của Spring Security có thể trả true, nên phải phân biệt anonymous theo chính sách. Tùy cấu hình custom, cần đánh giá thêm các kiểu Authentication khác.
4. **switchIfEmpty**: không biến người dùng chưa đăng nhập thành chuỗi rỗng/guest trong service vốn yêu cầu xác thực. Exception có thể được tầng security/web xử lý thành HTTP phù hợp; cách chuyển exception sang response cần được xác nhận bằng integration test của ứng dụng.
5. **getName() là nhận diện, chưa phải phân quyền**: Một endpoint xem hoặc sửa dữ liệu phải dùng security rules/ownership checks phù hợp, không cấp quyền chỉ vì có tên người dùng.

Nếu nghiệp vụ chỉ cần một account ID ổn định, nên định nghĩa typed principal/application identity sau quá trình xác thực, thay vì mãi phụ thuộc vào chuỗi Authentication.getName(). Tránh ép kiểu principal sang custom user/Jwt nếu ứng dụng có nhiều cơ chế xác thực; kiểm tra loại hoặc dùng adapter phù hợp.

## 6. Gọi service từ controller WebFlux

Ví dụ lớp src/main/java/example/security/MeController.java:

~~~java
package example.security;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class MeController {
    private final CurrentUserService currentUserService;

    public MeController(CurrentUserService currentUserService) {
        this.currentUserService = currentUserService;
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me() {
        return currentUserService.currentUsername()
                .map(name -> Map.of("username", name));
    }
}
~~~

Khi request đi qua SecurityWebFilterChain và xác thực thành công, Spring WebFlux subscribe vào publisher trả về; currentUsername() đọc context của request tương ứng.

Ví dụ cấu hình bảo vệ tuyến đường dưới đây là **đoạn class có thể đặt trong ứng dụng đã cấu hình cơ chế authentication thích hợp**:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

httpBasic() chỉ là cơ chế xác thực minh họa; production phải dùng cơ chế phù hợp (OAuth2 Resource Server/JWT, OAuth2 login, session, mTLS...) với HTTPS, credential storage và CSRF policy phù hợp. Không tắt CSRF một cách máy móc nếu hệ thống phục vụ trình duyệt và dùng cookie/session hoặc HTTP Basic. Đừng tự triển khai custom WebFilter để chèn Authentication trong mọi request khi Spring Security đã có AuthenticationWebFilter, ReactiveAuthenticationManager và ServerSecurityContextRepository.

Kết quả logic với account đã xác thực tên alice là JSON có username "alice". Request không xác thực phải bị từ chối theo cấu hình (thường 401 khi dùng HTTP Basic); request có authentication nhưng thiếu quyền cho endpoint khác có thể nhận 403. Mã response thực tế phụ thuộc entry point và SecurityWebFilterChain của ứng dụng.

## 7. Vì sao contextWrite đặt ở dưới lại ảnh hưởng toán tử phía trên?

Trong Reactor, Context đi **từ Subscriber (cuối pipeline) ngược lên các operator upstream** tại thời điểm subscription. contextWrite tạo ngữ cảnh cho các operator nằm **phía trên** nó, không tự sửa một thread local toàn cục.

Ví dụ:

~~~java
Mono<String> who = ReactiveSecurityContextHolder.getContext()
        .flatMap(c -> Mono.justOrEmpty(c.getAuthentication()))
        .map(Authentication::getName)
        .defaultIfEmpty("guest");

Mono<String> scoped = who.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Nếu alice là Authentication đã xác thực, scoped phát "alice". Nhưng đoạn đọc context nằm **sau** một contextWrite trong pipeline bên ngoài chưa chắc nhận entry này:

~~~java
Mono<String> onlyUpstream = who
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))
        .then(who);
~~~

Ở ví dụ này, who đầu tiên được subscribe với context alice, còn who dùng làm đối số của then được subscribe trong ngữ cảnh downstream của then, nơi chưa được withAuthentication đặt. Nếu không có context khác, kết quả cuối sẽ là "guest". Điều cần ghi nhớ không phải "dòng code trên dưới" theo trình tự viết Java, mà là vị trí operator trong **đồ thị subscription**.

Cách sửa khi cần cùng ngữ cảnh cho toàn bộ pipeline:

~~~java
Mono<String> entireFlow = firstStep()
        .then(who)
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

firstStep() là publisher của ứng dụng (đoạn giả định); chỉ có authentication từ kết quả xác thực hợp lệ mới được truyền. Trong request bình thường, SecurityWebFilterChain thực hiện công việc thiết lập ngữ cảnh; code nghiệp vụ chỉ cần đọc.

Một chi tiết quan trọng nữa: contextWrite ở nhánh một Mono không mặc định lan sang một nhánh độc lập được subscribe riêng. Việc tái sử dụng cùng biến Mono là an toàn nếu nó vẫn **cold** và không cache kết quả cá nhân; mỗi subscriber nhìn thấy context của chính mình.

## 8. Scheduler đổi thread mà vẫn giữ Reactor Context

Reactor cho phép switch thread bằng publishOn và subscribeOn. Context đi theo subscription, nên các operator Reactor chuẩn nhìn được context sau đổi thread:

~~~java
Mono<String> result = Mono.delay(Duration.ofMillis(10))
        .publishOn(Schedulers.boundedElastic())
        .then(currentUserService.currentUsername());
~~~

Với request đã được Spring Security xác thực và subscription giữ nguyên, currentUsername() vẫn lấy đúng Authentication. Các package liên quan là java.time.Duration, reactor.core.publisher.Mono và reactor.core.scheduler.Schedulers.

Điều quan trọng: Context là dữ liệu theo subscriber; **không phải mọi ThreadLocal đều được tự động truyền qua scheduler**. Ví dụ sau không đáng tin trong WebFlux:

~~~java
Mono<String> unsafe = Mono.fromCallable(() ->
        SecurityContextHolder.getContext().getAuthentication().getName())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Callable chạy ở worker thread; SecurityContextHolder có thể trống hoặc phản ánh dữ liệu không mong muốn. Thêm publishOn, subscribeOn hay defer không biến SecurityContextHolder thành API reactive.

Khi phải gọi thư viện blocking, đặt blocking I/O trên boundedElastic (hoặc giải pháp đã thiết kế) và **truyền rõ dữ liệu nghiệp vụ đã được phép sử dụng**:

~~~java
public Mono<String> auditCurrentUser() {
    return currentUserService.currentUsername()
            .flatMap(username ->
                    Mono.fromCallable(() ->
                            blockingAuditClient.recordUserAction(username))
                        .subscribeOn(Schedulers.boundedElastic()));
}
~~~

Đây là đoạn phương thức phụ thuộc blockingAuditClient của ứng dụng; kiểu trả ở ví dụ giả định recordUserAction trả String. Dòng code không truyền SecurityContextHolder qua thread; username được lấy từ context trong pipeline trước khi gọi hệ thống blocking. Tránh truyền credentials, JWT hoặc SecurityContext đầy đủ cho nơi chỉ cần một mã actor. Quyền ghi audit phải được kiểm tra ở tầng appropriate.

## 9. Ranh giới làm mất context: subscribe, Future, @Async và message queue

### Tự subscribe bên trong service

~~~java
// Tránh tách công việc khỏi request:
someMono.subscribe();
return Mono.just("accepted");
~~~

Subscription mới có thể thiếu Context và không được WebFlux chờ/ủy quyền, lỗi bị xử lý tách biệt. Thay:

~~~java
return someMono.thenReturn("accepted");
~~~

Trong chuỗi kết quả trả về, việc subscribe do WebFlux thực hiện một lần đúng lifecycle.

### CompletableFuture và thread thủ công

Reactor Context không tự vượt qua Thread mới, CompletableFuture.supplyAsync, callback của SDK không tích hợp Reactor hoặc @Async method. Khi chuyển sang API ngoài Reactor, chọn một trong hai cách có chủ đích:
- **Ưu tiên** lấy ít dữ liệu đã được phép dùng rồi truyền tường minh vào lời gọi bên ngoài (ví dụ actorId, tenantId sau validation). Kiểm tra quyền ở nơi cần thiết.
- Nếu cần propagation cho framework observability/legacy thông qua Micrometer Context Propagation, dùng adapter và cấu hình được thư viện hỗ trợ; không trông chờ ThreadLocal hay SecurityContextHolder tự chứa principal.

Đừng lén đặt SecurityContextHolder.setContext(...) vào một shared executor rồi quên clear. Nếu một thư viện bắt buộc sử dụng ThreadLocal, việc bridge sang nó cần scope try/finally, isolation, kiểm thử request đồng thời và sự hỗ trợ chính thức của framework. Đó là giải pháp tương thích có kiểm soát, không phải cách viết mới mặc định.

### Message queue và background job

Một message được xử lý sau khi HTTP request đã kết thúc là một luồng công việc độc lập, không tự có Authentication của request cũ. Khi cần audit actor, đưa một định danh actor đã xác minh, quyền tối thiểu hoặc mệnh lệnh nghiệp vụ vào message theo contract được phê duyệt. Worker phải xác thực/ủy quyền lại theo chính sách của nó, tuyệt đối không gửi nguyên SecurityContext hoặc bearer token vào queue chỉ để "khôi phục" thread context.

### Các nguồn publisher đặc biệt

Hot publisher, share/cache, sink toàn cục hoặc callback phát tín hiệu từ ngoài Reactor có thể làm thay đổi nơi subscription và cách chia sẻ giá trị. Đừng lưu/cached publisher đã resolve Authentication cho nhiều request. **Mỗi caller cần identity trong context của chính subscriber**, và authorization phải kiểm tra theo request cụ thể.

## 10. Nguy hiểm khi cache hoặc share dữ liệu người dùng

Mono.cache() biến một publisher thành nguồn replay kết quả cho subscriber sau. Nếu cache dùng cho username hoặc quyền theo người dùng tại singleton service, subscriber B có thể nhận kết quả của subscriber A:

~~~java
// Sai: field singleton lưu giá trị của người đầu tiên subscribe.
private final Mono<String> cachedUser =
        currentUserService.currentUsername().cache();
~~~

Dù currentUsername() bản gốc đọc đúng context lúc subscription, sau khi cache hoàn tất nó trả lại kết quả đã lưu. Không có context propagation nào sửa được **dữ liệu đã được cache sai phạm vi**.

Thay bằng:

~~~java
// Mỗi request gọi publisher cold theo context riêng.
public Mono<String> handle() {
    return currentUserService.currentUsername()
            .flatMap(this::processForCurrentUser);
}
~~~

processForCurrentUser(String) là hàm nghiệp vụ trả Mono<String> của ứng dụng. Nếu cần cache dữ liệu nghiệp vụ, phân vùng key theo tenant/user được xác thực, ràng buộc authorization, vòng đời cache và invalidation; không dùng cache principal hiện tại như một singleton.

Tránh sửa SecurityContext hoặc Authentication mutable rồi dùng lại cùng object cho nhiều subscription song song. withAuthentication() không làm object trở nên immutable hoặc tự bảo đảm isolation nếu cùng instance bị chia sẻ/đột biến.

## 11. Vai trò của SecurityWebFilterChain và ReactiveSecurityContextHolder

Trong WebFlux, Spring Security dùng SecurityWebFilterChain và các WebFilter để xử lý xác thực, phân quyền, context. Khi SecurityContextRepository hoặc cơ chế bearer authentication xác định thông tin hợp lệ, framework cung cấp context cho xử lý downstream qua Reactor.

Các trường hợp điển hình:
- **HTTP Basic:** thông tin đăng nhập được xác thực bởi authentication manager/provider phù hợp; controller/service đọc bằng ReactiveSecurityContextHolder.
- **OAuth2 Resource Server với JWT:** filter bearer kiểm tra chữ ký, exp/nbf, issuer/audience (theo cấu hình), rồi đặt Authentication đã xác thực. Service chỉ đọc context, không tự giải mã token lần thứ hai để đoán ai đang gọi.
- **Session/form login:** repository lưu hoặc tải context theo session; trong request reactive, vẫn truy xuất qua ReactiveSecurityContextHolder.
- **Request permitAll:** authorization không yêu cầu danh tính; getContext() có thể không có Authentication hoặc có anonymous token. Không mặc định permitAll đồng nghĩa "đã đăng nhập".

Đừng tự gọi ReactiveSecurityContextHolder.withAuthentication(new UsernamePasswordAuthenticationToken(...)) dựa vào header không xác minh hoặc id query string. Điều đó bỏ qua bước authentication và có thể leo thang quyền. Nếu đang chuyển một bộ lọc xác thực tự viết từ Servlet:
1. Tách bước **đọc credential** và **xác thực credential** (ReactiveAuthenticationManager hoặc cơ chế hỗ trợ).
2. Sử dụng lớp AuthenticationWebFilter và ServerSecurityContextRepository khi phù hợp, thay vì tự quản lý context ở mọi callback.
3. Đặt filter đúng thứ tự trong SecurityWebFilterChain, xác định entry point và response lỗi.
4. Test các trường hợp credential hợp lệ, sai, thiếu, hết hạn; không chỉ test đọc ReactiveSecurityContextHolder.
5. Không log credential/raw Authorization khi gỡ lỗi propagation.

## 12. Chuyển SecurityContextHolder trong từng tầng ứng dụng

### Controller/handler

**Trước:** Gọi một service trả String username đồng bộ.

**Sau:** Trả Mono/Flux hoặc dùng các tham số WebFlux có hỗ trợ principal. Ví dụ đã đưa ở phần 6 dùng Mono<Map<String,String>>. Trong WebFlux handler, ServerWebExchange.getPrincipal() cũng trả Mono<Principal>; có thể dùng cho trường hợp chỉ cần principal tại HTTP layer. Khi code dùng chung ở nhiều tầng, ReactiveSecurityContextHolder và mô hình nhận diện nghiệp vụ phù hợp hơn.

### Service dùng Authentication

**Trước:**

~~~java
String owner = SecurityContextHolder.getContext()
        .getAuthentication().getName();
return repository.findByOwner(owner);
~~~

**Sau:** Giả sử repository.findByOwner(String) trả Mono<Order>:

~~~java
return currentUserService.currentUsername()
        .flatMap(repository::findByOwner);
~~~

Đây là đoạn minh họa trong một phương thức trả Mono<Order>. Tránh lấy owner từ request body để thay thế auth context nếu dữ liệu phải được giới hạn bởi người dùng đăng nhập. Vẫn cần kiểm tra ownership/authorization khi tra cứu ID theo request.

### Service cần chạy nhiều bước

~~~java
return currentUserService.currentUsername()
        .flatMap(user -> accountRepository.findByOwner(user))
        .flatMap(account -> paymentService.readStatus(account.id()));
~~~

accountRepository.findByOwner(...) và paymentService.readStatus(...) là reactive API nghiệp vụ giả định; kiểu trả và xử lý error phải thống nhất trong implementation. Việc truyền actor/ID tường minh giữa các tầng thường giúp code dễ test và đánh giá quyền hơn việc mỗi helper ngầm đọc security context.

### Code thư viện không biết Spring Security

Không ép thư viện domain/DAO phụ thuộc trực tiếp vào ReactiveSecurityContextHolder chỉ để tìm current user. Ở boundary application/service, lấy identity đã kiểm tra, sau đó truyền một kiểu Actor/TenantId hoặc tham số cụ thể vào domain logic. Điều này giảm coupling với framework và làm test đơn giản.

## 13. Phân quyền reactive bằng method security

Nếu dùng annotation phân quyền ở tầng service, cần bật **reactive method security**, không sao chép nguyên cấu hình Servlet @EnableMethodSecurity mà bỏ qua mô hình Publisher.

~~~java
package example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Ví dụ trong một Spring-managed service trả Mono<String>:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<String> readOrderStatus(String orderId) {
    return orderRepository.findStatus(orderId);
}
~~~

Dòng trên là đoạn phương thức minh họa, orderRepository cần được khai báo và trả Mono<String>; để compile cần import org.springframework.security.access.prepost.PreAuthorize. Method security với Reactor Context được áp dụng thông qua proxy/interceptor cho lời gọi Spring-managed bean; self-invocation bên trong cùng instance thường không qua proxy. Quy tắc hasAuthority phải khớp đúng authority được tạo từ JWT/role thật, chẳng hạn SCOPE_orders.read trong Resource Server với converter mặc định phù hợp. Với cơ chế khác, chính sách quyền và prefix có thể khác.

Spring Security khuyến nghị các publisher reactive để framework có thể gắn kiểm tra authorization với Reactor Context. Không đổi kiểu trả về thành String bằng cách block() chỉ để sử dụng annotation imperative. Cũng không coi kiểm tra Authentication.isAuthenticated() trong service là đủ cho quyền đọc/sửa tài nguyên.

## 14. Kiểm thử đơn vị bằng Reactor Test: không có, có và tách biệt context

Đặt src/test/java/example/security/CurrentUserServiceTest.java; cần JUnit Jupiter và reactor-test cùng phiên bản tương thích với dự án. Các test sau chỉ dùng logic của CurrentUserService, không cần khởi động web server:

~~~java
package example.security;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class CurrentUserServiceTest {
    private final CurrentUserService service = new CurrentUserService();

    private static Authentication auth(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, null, AuthorityUtils.createAuthorityList("ROLE_USER"));
    }

    @Test
    void missingContextIsRejected() {
        StepVerifier.create(service.currentUsername())
                .expectError(AuthenticationCredentialsNotFoundException.class)
                .verify();
    }

    @Test
    void readsAuthenticationFromSubscriber() {
        StepVerifier.create(service.currentUsername()
                        .contextWrite(ReactiveSecurityContextHolder
                                .withAuthentication(auth("alice"))))
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void keepsContextAcrossSchedulerChange() {
        Mono<String> flow = Mono.delay(Duration.ofMillis(10))
                .publishOn(Schedulers.boundedElastic())
                .then(service.currentUsername())
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(auth("alice")));

        StepVerifier.create(flow)
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void concurrentSubscribersDoNotShareAuthentication() {
        Mono<String> sharedColdSource = service.currentUsername();

        Mono<String> alice = Mono.delay(Duration.ofMillis(20))
                .then(sharedColdSource)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(auth("alice")));

        Mono<String> bob = Mono.delay(Duration.ofMillis(5))
                .then(sharedColdSource)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(auth("bob")));

        StepVerifier.create(Flux.merge(alice, bob).collectSortedList())
                .expectNext(List.of("alice", "bob"))
                .verifyComplete();
    }
}
~~~

**Kỳ vọng test:**
- Không có context: publisher kết thúc bằng AuthenticationCredentialsNotFoundException.
- Context alice: phát đúng chuỗi "alice".
- Sau đổi scheduler: vẫn là "alice", không phải null.
- Hai subscription chồng nhau: trả danh sách đã sắp xếp ["alice", "bob"], không rò context.

Lệnh chạy trong dự án có wrapper và dependencies tương ứng:

~~~bash
./mvnw -Dtest=CurrentUserServiceTest test
~~~

Hoặc với Gradle (có thể cần tên fully qualified nếu nhiều class trùng tên):

~~~bash
./gradlew test --tests example.security.CurrentUserServiceTest
~~~

Trên Windows dùng mvnw.cmd hoặc gradlew.bat. Test không cố định chuỗi stdout của Maven/Gradle vì kết quả console phụ thuộc runner, version, plugin và các test khác; tiêu chí đúng là cả bốn test thành công. Đây là test hồi quy logic, **chưa chứng minh** SecurityWebFilterChain ngoài HTTP hoạt động đúng.

### Kiểm thử tích hợp WebFlux

Với spring-security-test và WebTestClient, có thể giả lập một người dùng tại filter chain mà không tự đặt ThreadLocal. Ví dụ đoạn test nằm trong class đã có WebTestClient được cấu hình để tích hợp Spring Security:

~~~java
webTestClient
        .mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.username").isEqualTo("alice");
~~~

Cần import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser. Khi triển khai test thực, cấu hình context, client và controller phù hợp; thêm test request không xác thực nhận 401, request có role sai nhận 403 tại endpoint bảo vệ, và hai request song song với identity khác nhau không bao giờ trả lẫn principal. Không dùng @WithMockUser hoặc mockUser làm cơ chế xác thực ở production.

## 15. Quy trình debug khi getContext() rỗng

Khi code mới vẫn không thấy Authentication, kiểm tra theo chuỗi sau:

1. **Request đi qua đúng SecurityWebFilterChain?** Xác minh URL, matcher, thứ tự chain và web application type thực chạy. Không suy diễn từ việc dependency spring-security-web có mặt.
2. **Request đã xác thực thật chưa?** Kiểm tra kết quả 401/403 ở endpoint bảo vệ, cấu hình AuthenticationWebFilter/Resource Server, issuer, audience, session và entry point. Với permitAll, không có user là điều bình thường.
3. **Đọc context lúc subscription hay lúc lắp Mono?** Không đọc ở static initializer, constructor singleton, @PostConstruct hay trước khi WebFlux subscribe.
4. **Có subscribe()/block() hoặc Future riêng trong helper?** Truy vết chain tại nơi tách subscription, không chỉ tại điểm đọc getContext().
5. **Có cache/share/hot publisher chứa principal?** Kiểm tra field singleton, .cache(), share(), Sinks/Subjects được dùng chung và memoization theo user.
6. **Có operator contextWrite(clearContext()) hoặc thay Context sai?** Xem phạm vi upstream/downstream và xem liệu code dùng contextWrite(ctx -> Context.empty()) làm mất toàn bộ entries hay không.
7. **Có gateway/SDK/service ngoài Reactor?** Kiểm tra reactive adapter, callback, @Async và message handler. Với luồng độc lập, cần explicit actor contract hoặc cơ chế xác thực mới.
8. **Có kiểm tra anonymous đúng không?** isAuthenticated() không tự động loại AnonymousAuthenticationToken.
9. **Có nhầm SecurityContextHolder với ReactiveSecurityContextHolder ở helper cũ?** Search các đoạn getContext(), setContext(), clearContext(), ThreadLocal và MDC trong phạm vi mã cần migrate.
10. **Có quyền nhưng vẫn 403?** Kiểm tra authorities, prefix ROLE_ / SCOPE_, method security, mapping claim, tenancy/ownership; context tồn tại không chứng minh người dùng có quyền đó.

Khi log để debug, chỉ ghi event, correlation ID an toàn, route template, trạng thái xác thực/anonymous và loại exception đã chuẩn hóa. **Không in Authentication.toString(), principal object, credentials, Authorization header, cookie, JWT hoặc SecurityContext**; log full object có thể làm lộ dữ liệu cá nhân và token.

## 16. Vì sao Micrometer Context Propagation không thay thế API reactive?

Reactor hỗ trợ tích hợp io.micrometer:context-propagation để chụp/khôi phục một số trạng thái ThreadLocal qua Context. Có chế độ mặc định và chế độ automatic với Hooks.enableAutomaticContextPropagation() (phụ thuộc phiên bản Reactor/cấu hình). Điều này hữu ích cho trace ID/MDC hoặc thư viện legacy cần ThreadLocal.

Tuy nhiên:
- **Nguồn chuẩn của security context trong WebFlux vẫn là Reactor Context** qua ReactiveSecurityContextHolder. Không thiết kế code mới dựa vào việc SecurityContextHolder có vô tình được đồng bộ sang ThreadLocal hay không.
- Cơ chế automatic có phạm vi, điều kiện đăng ký ThreadLocalAccessor và tác động hiệu năng. Việc enable sau khi subscription đã tạo không bảo đảm sửa tất cả luồng cũ.
- Một callback ngoài reactive chain không đương nhiên mang ngữ cảnh chỉ vì đã bật Micrometer; cần adapter/capture theo tài liệu.
- Không đưa Authentication/JWT nguyên vẹn vào MDC, tracing baggage hoặc log. Trường hợp cần identity cho audit, ưu tiên dữ liệu đã xác minh và tối thiểu.
- Tránh sửa ThreadLocal của framework trong try/catch rời rạc; nếu bắt buộc bridge một library, phải kiểm tra việc reset/clear để không làm lộ thông tin trên thread dùng chung.

Reactor Context là cơ chế cho dữ liệu theo subscription; Micrometer có thể bridge một phần sang ThreadLocal khi có nhu cầu rõ ràng. Hai công cụ phục vụ mục đích khác nhau.

## 17. Chiến lược migration cho codebase có nhiều service

**Bước 1 — Xác định chỗ phụ thuộc ThreadLocal.** Tìm các call SecurityContextHolder.getContext(), setContext(), clearContext(), MODE_INHERITABLETHREADLOCAL, custom ThreadLocal, MDC chứa userId, RestTemplate interceptor, @Async và CompletableFuture. Đặc biệt kiểm tra service dùng trong reactive controllers nhưng vẫn trả dữ liệu đồng bộ từ current user.

**Bước 2 — Phân loại thay đổi.** Logic ở boundary HTTP có thể dùng principal do WebFlux cung cấp; service reactive cần current-user abstraction trả Mono<Actor>; domain/repository tốt hơn nhận Actor hoặc ownerId rõ ràng. Các task chạy nền cần identity/authorization contract riêng, không cố kế thừa user thread context.

**Bước 3 — Đổi contract từ đồng bộ sang Publisher.** Ví dụ String currentUsername() → Mono<String> currentUsername(). Refactor callers bằng map/flatMap; không gọi block() ở event loop để "giữ nguyên signature". Nếu đang dùng API blocking, chuyển qua adapter boundedElastic hoặc API reactive phù hợp.

**Bước 4 — Đặt auth ở đúng framework layer.** Dùng SecurityWebFilterChain, WebFlux Security, AuthenticationWebFilter/ReactiveAuthenticationManager hoặc OAuth2 Resource Server hiện có. Không tạo filter tùy ý đặt Auth dựa trên input chưa xác minh.

**Bước 5 — Định nghĩa chính sách khi không có context.** Endpoint public có thể không có user. Endpoint private nên yêu cầu xác thực và có error semantics nhất quán; lựa chọn fallback "guest" chỉ dùng cho logic cho phép anonymous. Không nuốt exception rồi tự gán tài khoản đặc quyền mặc định.

**Bước 6 — Bảo vệ đường phân quyền.** Thêm reactive method security ở nơi cần, kiểm tra hasRole/hasAuthority, ownership và dữ liệu cùng tenant. Đảm bảo mọi đường truy cập nguồn dữ liệu quan trọng đều qua authorization.

**Bước 7 — Kiểm thử đồng thời và lỗi.** Chạy requests đồng thời ở nhiều scheduler, token hợp lệ/hết hạn, missing context, canceled subscription, retry, timeout và thư viện gọi ngoài Reactor. Xác nhận identity không chuyển từ request A sang B.

**Bước 8 — Xóa đường code cũ và quan sát hồi quy.** Khi đã migrate tất cả callers, loại các helper SecurityContextHolder/ThreadLocal dùng để truy cập principal trong WebFlux. Theo dõi tăng đột ngột của 401/403, sự cố principal missing, 5xx và thay đổi latency.

Đừng vội đổi toàn bộ ứng dụng trong một commit lớn nếu chưa có test authentication/authorization; có thể làm từng controller/service, giữ đầu ra HTTP ổn định và thực hiện regression tests ở mỗi bước.

## 18. Những bẫy khó phát hiện

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| getAuthentication() null trong reactive handler | Đọc SecurityContextHolder ở thread không gắn request | Dùng ReactiveSecurityContextHolder.getContext() trong Mono/Flux; xác minh chain |
| App chạy tốt ở máy dev, lỗi khi tải cao | Thread reused, race condition, singleton field lưu principal | Bỏ ThreadLocal/global state và test concurrent subscribers |
| Chạy publishOn rồi “mất user” | Helper vẫn đọc ThreadLocal hoặc đã tách subscription | Đọc Reactor Context; giữ publisher trong cùng chain |
| Test có auth nhưng HTTP trả 401 | Test chỉ dùng withAuthentication cho Mono, chưa đi qua WebFlux filter chain | Thêm WebTestClient integration test với spring-security-test |
| @PreAuthorize không hoạt động như mong đợi | Chưa bật reactive method security, self-invocation hoặc return type không phù hợp | Bật @EnableReactiveMethodSecurity và test lời gọi qua bean proxy |
| Service thấy "anonymous" nhưng isAuthenticated()=true | AnonymousAuthenticationToken được đánh dấu authenticated | Kiểm tra loại token và rules phù hợp |
| Dữ liệu người A xuất hiện ở người B | Mono.cache/share hoặc field singleton lưu identity | Bỏ cache context-dependent, tách theo subscriber |
| Tạo Context mới làm mất trace/security | contextWrite(ctx -> Context.empty()) hoặc clearContext sai phạm vi | Giữ nguyên entries, chỉ sửa key cần thiết |
| Logout xong vẫn dùng token | Nhầm clearContext với logout/session invalidation | Thực hiện session/token invalidation theo mô hình xác thực |
| WebClient callback không có context | Lời gọi external library / Future / detached subscribe | Dùng operator Reactor hoặc truyền actor rõ ràng, xác thực lại khi cần |

## 19. Checklist kiểm tra trước khi đưa lên production

- [ ] Trong luồng WebFlux, không còn phụ thuộc SecurityContextHolder/ThreadLocal để đọc người dùng hiện tại.
- [ ] SecurityContext/Authentication được lấy lazily qua ReactiveSecurityContextHolder, với xử lý trường hợp không có auth.
- [ ] Không có singleton/static field hoặc Mono.cache()/share() lưu Authentication của request.
- [ ] Không dùng block()/subscribe() ở controller/service để ép giá trị principal thành đồng bộ.
- [ ] SecurityWebFilterChain và các cơ chế authentication của framework được dùng đúng; không chèn Authentication từ dữ liệu client chưa xác minh.
- [ ] Method security dùng @EnableReactiveMethodSecurity và các Publisher cần thiết.
- [ ] Publisher vẫn giữ context sau publishOn/subscribeOn; các ranh giới ngoài Reactor được xử lý tường minh.
- [ ] Test StepVerifier bao phủ absent, authenticated, scheduler switch, concurrent subscribers.
- [ ] Test WebTestClient xác minh 401, 403 và dữ liệu đúng theo quyền/người dùng cho request thật.
- [ ] Log/tracing/MDC không chứa credentials, token, full SecurityContext hoặc dữ liệu cá nhân ngoài chính sách.
- [ ] Tác vụ background/queue có auth model riêng; clearContext không được hiểu là logout.
- [ ] Bộ test bảo mật chạy trong CI sau các đợt nâng cấp Spring Security, Reactor và context propagation.

## 20. Tài liệu chính thức để đối chiếu API

1. [ReactiveSecurityContextHolder Java API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html) — getContext, withAuthentication, withSecurityContext và clearContext.
2. [Spring Security Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — reactive method authorization dựa vào Reactor Context; ví dụ StepVerifier.
3. [Spring Security Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — SecurityWebFilterChain và cấu hình WebFlux.
4. [Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) — contextWrite, ContextView, hướng lan truyền theo subscriber.
5. [Reactor Reference — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html) — cầu nối Micrometer với ThreadLocal, chế độ mặc định/automatic.
6. [Spring Security Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html) — Spring Security Test và WebTestClient.

**Ghi nhớ:** Trong WebFlux, current user thuộc **subscription**, không thuộc thread. Đọc bằng ReactiveSecurityContextHolder.getContext(), tiếp tục xử lý qua Mono/Flux, để SecurityWebFilterChain thiết lập context, và dùng authorization phù hợp. Hãy giữ danh tính tách biệt giữa các subscriber, không cache principal dùng chung và không giả định một ThreadLocal sẽ đi theo các bước reactive.
