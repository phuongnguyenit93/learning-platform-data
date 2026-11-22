# Reactor Context thay đổi cách truyền danh tính giữa các bước xử lý

> **Chủ đề:** Spring Security - fundamentals → Kiến trúc reactive  
> **Trọng tâm:** Danh tính người dùng/`Authentication` đi qua chuỗi xử lý WebFlux theo *subscriber*, thay vì giả định luôn nằm trong `ThreadLocal` của một thread.

## 1. Học xong bài này cần hiểu gì?

- Vì sao cách đọc danh tính từ `SecurityContextHolder` theo `ThreadLocal` quen thuộc trong ứng dụng Servlet không còn là cơ chế đáng tin cậy cho toàn bộ luồng xử lý reactive.
- Reactor `Context` được gắn với *subscription/subscriber* như thế nào, được ghi bằng `contextWrite` và đọc bằng `deferContextual` ra sao.
- Spring Security WebFlux dùng `ReactiveSecurityContextHolder` để các tầng handler, service và kiểm tra quyền nhìn thấy `SecurityContext`/`Authentication` trong cùng một reactive chain.
- Nhận biết các điểm dễ làm mất ngữ cảnh: tự `subscribe()`, `block()`, dựng chuỗi độc lập hoặc chuyển sang API bất đồng bộ không thuộc Reactor.

## 2. Bài toán: danh tính không thể phụ thuộc vào thread

Trong Servlet truyền thống, một yêu cầu HTTP thường được xử lý theo mô hình thread gắn với request trong phần đáng kể của vòng đời. `SecurityContextHolder` mặc định dùng `ThreadLocal`, nên mã đang chạy trên thread đó có thể đọc `Authentication`:

~~~java
// Ví dụ cách truy cập phổ biến trong mã Servlet (minh họa, không phải chương trình độc lập).
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
~~~

Trong WebFlux, một request được biểu diễn bằng các `Mono`/`Flux`, được thực thi khi có subscription. Pipeline có thể chuyển thread tại ranh giới scheduler, chờ I/O mà không giữ thread, và kết hợp nhiều tác vụ bằng `flatMap`. Thread hiện tại vì vậy **không phải định danh ổn định của request**. Một `ThreadLocal` rỗng hoặc mang giá trị không như kỳ vọng không thể được dùng làm bằng chứng về user trong chuỗi reactive.

Ví dụ một request của Alice có thể đi qua:

~~~text
HTTP request (Alice)
    |
    v
WebFilter xác thực / nạp SecurityContext
    |
    v
Handler (event-loop thread A)
    |
    v
Service -- flatMap --> truy vấn bất đồng bộ (thread có thể đổi)
    |
    v
Service tiếp tục (thread B hoặc A)
    |
    v
HTTP response
~~~

Yêu cầu thực sự là: **mọi bước thuộc đúng chuỗi xử lý của Alice đọc được đúng `Authentication` của Alice, dù thread thay đổi; request của Bob không được nhìn thấy danh tính Alice.**

## 3. Reactor Context thực chất là gì?

`reactor.util.context.Context` là tập khóa–giá trị *bất biến* dùng để mang metadata theo subscription. Nó không đi trong phần dữ liệu `onNext` và không phải biến toàn cục. Một operator đọc được `ContextView` của subscriber phía downstream; `Context` thích hợp với correlation ID, tracing và ngữ cảnh bảo mật.

| Cơ chế | Gắn với | Ý nghĩa đối với danh tính |
| --- | --- | --- |
| `ThreadLocal` | Thread đang thực thi | Có thể không đi theo request khi lịch thực thi thay đổi |
| Tham số hàm, ví dụ `findByUser(userId)` | Lời gọi cụ thể | Rõ ràng và tốt cho dữ liệu nghiệp vụ cần truyền tường minh |
| Reactor `Context` | Subscriber/subscription trong reactive chain | Truyền metadata ngầm qua các operator Reactor cùng chain |
| `ReactiveSecurityContextHolder` | `SecurityContext` đặt trong Reactor `Context` | API Spring Security để lấy/xác lập ngữ cảnh xác thực reactive |

Các tính chất quan trọng:

1. **Ghi khi subscribe.** `contextWrite(...)` gắn/thay đổi context mà các operator *upstream* có thể nhìn thấy khi subscription đi từ cuối chuỗi ngược lên nguồn. Vị trí trong chuỗi quan trọng hơn thứ tự đọc từ trái sang phải của mã.
2. **Đọc tại thời điểm chạy.** `Mono.deferContextual(view -> ...)` chỉ lấy `ContextView` khi có subscription. Đọc context quá sớm, ngoài một subscriber, không tạo ra danh tính “mặc định” cho request.
3. **Bất biến và có phạm vi.** `put` trả về context mới; nó không sửa bản dùng chung. Hai subscription riêng có thể mang user khác nhau dù dùng cùng định nghĩa pipeline.
4. **Thường đi qua operator Reactor.** `map`, `flatMap`, `publishOn` vẫn có thể làm việc với context khi tạo thành một reactive chain đúng cách. Một `contextWrite` trong publisher con của `flatMap` chỉ ảnh hưởng phạm vi publisher con đó, không tự sửa mọi nhánh bên ngoài.
5. **Không tự động trở thành `ThreadLocal`.** Cơ chế *context-propagation* tùy chọn có thể làm cầu nối với `ThreadLocal` cho thư viện tương thích nếu cấu hình đúng. Bản thân Reactor `Context` và Spring Security reactive vẫn là các khái niệm riêng; không được mặc nhiên dựa vào cầu nối này.

### Đọc từ dưới lên khi thấy `contextWrite`

~~~java
Mono<String> name =
    Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("user", "guest")))
        .contextWrite(ctx -> ctx.put("user", "alice"));

// name.block() trả về "alice" trong ví dụ chạy ngoài event loop.
~~~

`contextWrite` xuất hiện cuối đoạn code nhưng ở phía *downstream* của `deferContextual`, nên giá trị `alice` được cấp cho đoạn đọc ở *upstream*.

Ngược lại:

~~~java
Mono<String> name =
    Mono.just("ignored")
        .contextWrite(ctx -> ctx.put("user", "alice"))
        .flatMap(ignored ->
            Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("user", "guest"))));

// name.block() trả về "guest": contextWrite nằm phía trên flatMap.
~~~

Hai đoạn trên chỉ minh họa semantics của Reactor, **chưa phải cơ chế xác thực người dùng**. `contextWrite` có thể đặt metadata tùy ý; Spring Security chỉ tin `Authentication` được tạo/xác minh bởi cơ chế bảo mật hợp lệ.

## 4. Thực hành chạy được: một pipeline, nhiều danh tính

Ví dụ này dùng Java 17+ và Reactor Core. Tạo một project Gradle nhỏ (hoặc đặt vào project Java/Gradle riêng đã có). File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.7.12'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ContextIdentityDemo'
}
~~~

File `src/main/java/demo/ContextIdentityDemo.java`:

~~~java
package demo;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public final class ContextIdentityDemo {
    private static final String USER_KEY = "user";

    private static Mono<String> readIdentity(String stage) {
        return Mono.deferContextual(view ->
            Mono.just(stage + "=" + view.getOrDefault(USER_KEY, "guest"))
        );
    }

    private static Mono<String> pipeline() {
        return readIdentity("handler")
            .publishOn(Schedulers.boundedElastic())
            .flatMap(first ->
                readIdentity("service")
                    .map(second -> first + " | " + second)
            );
    }

    public static void main(String[] args) {
        System.out.println(
            pipeline().contextWrite(Context.of(USER_KEY, "alice")).block()
        );
        System.out.println(
            pipeline().contextWrite(Context.of(USER_KEY, "bob")).block()
        );
        System.out.println(pipeline().block());
    }
}
~~~

Chạy bằng JDK 17+ và Gradle 8.x:

~~~bash
gradle run --quiet
~~~

Stdout (ba dòng do chương trình in, có thể bỏ qua thông tin của Gradle):

~~~text
handler=alice | service=alice
handler=bob | service=bob
handler=guest | service=guest
~~~

**Giải thích:** `readIdentity` không đọc thread mà trì hoãn đọc `ContextView` đến subscription. `publishOn` đổi scheduler cho phần xử lý downstream mà không làm mất giá trị ở subscription tương ứng. Mỗi lần gọi `pipeline()`/`block()` trong ví dụ tạo một subscription; chỉ các subscription được gắn `Context.of(USER_KEY, ...)` mới đọc được `alice` hoặc `bob`. Dòng thứ ba không có metadata đó nên dùng giá trị dự phòng `guest`. `block()` chỉ có ở chương trình `main` thử nghiệm; **không gọi `block()` trong handler/service WebFlux đang xử lý request**.

> Đối chiếu: cùng một hàm `readIdentity` được tái sử dụng nhưng kết quả khác nhau theo subscriber. Đây là điểm cốt lõi để không trộn danh tính giữa các request đồng thời.

## 5. Spring Security WebFlux đưa `Authentication` vào đâu?

`Authentication` biểu diễn principal và các thông tin xác thực/quyền. `SecurityContext` chứa `Authentication`. Trong reactive stack, `ReactiveSecurityContextHolder` là API truy cập `SecurityContext` thông qua Reactor `Context`; nó không yêu cầu handler phải đọc `ThreadLocal`.

Luồng khái niệm:

~~~text
Request
  -> SecurityWebFilterChain
     -> xác thực token / HTTP Basic / session theo cấu hình
     -> SecurityContext cho request
     -> Reactor Context của chuỗi xử lý
  -> Controller
     -> Service
        -> ReactiveSecurityContextHolder.getContext()
        -> SecurityContext.getAuthentication()
        -> Authentication.getName(), getAuthorities()...
  -> Authorization / response
~~~

`ReactorContextWebFilter` có vai trò dùng `ServerSecurityContextRepository` để cung cấp `SecurityContext` cho `ReactiveSecurityContextHolder`. Các filter xác thực khác trong `SecurityWebFilterChain` cũng tham gia thiết lập ngữ cảnh cho request tùy cơ chế cấu hình. **Không suy ra rằng mọi hệ thống dùng session:** resource server JWT có thể xác thực token ở mỗi request, còn ứng dụng khác có thể lưu context qua repository.

Các API cần phân biệt:

- `ReactiveSecurityContextHolder.getContext()` → `Mono<SecurityContext>`; có thể empty nếu không có context.
- `ReactiveSecurityContextHolder.withAuthentication(authentication)` → một Reactor `Context` chứa `Mono<SecurityContext>` tương ứng, hữu ích cho test hoặc pipeline tạo có chủ đích.
- `ReactiveSecurityContextHolder.withSecurityContext(monoContext)` → đặt một `Mono<? extends SecurityContext>`.
- `ReactiveSecurityContextHolder.clearContext()` → hàm thay đổi Reactor context cho phạm vi áp dụng, không phải thao tác xóa trạng thái xác thực của mọi request.
- `SecurityContextHolder.getContext()` → API kiểu imperative/thread-local thường thấy ở Servlet; **không dùng làm nguồn principal mặc định trong business logic reactive**.

### Ví dụ controller trong ứng dụng WebFlux đã bật Spring Security

Đoạn dưới là thành phần để đặt vào ứng dụng Spring WebFlux có các dependency Spring Security phù hợp; đây **không** phải chương trình Java đứng độc lập:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class WhoAmIController {
    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication())
            )
            .map(Authentication::getName)
            .map(name -> "user=" + name);
    }
}
~~~

Khi request đã được xác thực và đúng filter chain, tên người dùng sẽ được đọc **bên trong publisher**. Nếu không có `SecurityContext`/`Authentication`, đoạn code trả về `Mono.empty()`; bản thân việc đọc principal không thay thế bước phân quyền.

Hãy bảo vệ endpoint bằng chính cấu hình security, chẳng hạn đoạn cấu hình thuộc ứng dụng WebFlux:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/me").authenticated()
            .anyExchange().permitAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Các import tương ứng gồm `@Bean` từ Spring Context, `SecurityWebFilterChain`, `ServerHttpSecurity` và `org.springframework.security.config.Customizer`. Cấu hình này chỉ minh họa quy tắc endpoint; ứng dụng thực cần một cơ chế tạo/xác minh credentials thích hợp. Nếu dùng `@EnableReactiveMethodSecurity`, kiểm tra quyền ở phương thức reactive cũng dựa trên ngữ cảnh bảo mật trong chuỗi Reactor.

### Ví dụ gắn danh tính trong một test reactive

Trong test với dependency `reactor-test` và `spring-security-core`, có thể dùng `StepVerifier` và một `Authentication` đã biết:

~~~java
Authentication alice = new UsernamePasswordAuthenticationToken(
    "alice",
    "unused",
    List.of(new SimpleGrantedAuthority("ROLE_USER"))
);

Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(username)
    .expectNext("alice")
    .verifyComplete();
~~~

Cần import `java.util.List`, `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `SecurityContext`, `ReactiveSecurityContextHolder`, `Mono` và `StepVerifier`. Constructor ba tham số của `UsernamePasswordAuthenticationToken` tạo authentication được đánh dấu authenticated cho mục đích test. Test này chứng minh **truyền context trong pipeline**, không thử tính đúng đắn của xác thực password/token.

## 6. Danh tính đi qua các bước xử lý như thế nào?

Giả sử request đã được security filter xác thực. Controller có thể trả thẳng một `Mono` do service tạo; service tiếp tục gọi repository reactive:

~~~java
// Các method dưới là ví dụ ghép nối, không phải một class độc lập.
Mono<String> loadMyProfile() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(profileRepository::findDisplayNameByUsername);
}
~~~

Ở đây `flatMap` kết hợp publisher của repository vào cùng luồng. Danh tính được lấy đúng lúc thực thi, không bị chụp sớm vào một biến thread-local. Với nghiệp vụ cần audit hoặc truy vấn theo chủ tài nguyên, truyền `username`/`userId` tường minh vào repository còn giúp ranh giới phân quyền rõ ràng. **Reactor Context là hạ tầng truyền metadata; nó không tự động thêm điều kiện `WHERE owner_id = ...` vào câu truy vấn.**

Hai request đồng thời có thể sử dụng cùng mã controller/service nhưng mỗi subscription mang context khác nhau. Ngược lại, nếu một tác vụ độc lập được sinh ra bằng `subscribe()` ở trong service, nó trở thành subscription mới và không được bảo đảm kế thừa security context từ request ban đầu.

Một điều dễ nhầm khác: `contextWrite` trong publisher con chỉ thay đổi phạm vi con. Ví dụ:

~~~java
Mono<String> inner = readCurrentUser()
    .contextWrite(ctx -> ctx.put("user", "inner"));

Mono<String> outer = Mono.just("start")
    .flatMap(ignored -> inner)
    .flatMap(ignored -> readCurrentUser())
    .contextWrite(ctx -> ctx.put("user", "outer"));
~~~

Trong ví dụ này, giả định `readCurrentUser()` đọc khóa Reactor `user` như ở ví dụ Reactor thuần: lượt đọc trong `inner` thấy `inner`, lượt đọc cuối của `outer` thấy `outer`. Không được suy diễn rằng ghi context trong một nhánh sẽ cập nhật tất cả subscriber hoặc một “session” dùng chung.

## 7. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `SecurityContextHolder.getContext()` rỗng giữa WebFlux service | Code phụ thuộc `ThreadLocal` | Đọc reactive bằng `ReactiveSecurityContextHolder.getContext()` bên trong publisher |
| `deferContextual` không thấy khóa đã ghi | `contextWrite` đặt sai phía hoặc chỉ áp dụng cho nhánh khác | Kiểm tra luồng subscription từ dưới lên và vị trí ranh giới `flatMap` |
| Sau `subscribe()` thủ công không còn principal | Tạo subscription độc lập, ngữ cảnh request không được truyền như kỳ vọng | Trả lại `Mono`/`Flux` để framework quản lý subscription; nối bằng `flatMap`, `then`... |
| `block()` làm chậm, lỗi hoặc mất context trong handler | Chặn event loop và thường phát sinh subscription phụ | Giữ pipeline bất đồng bộ; dùng operator reactive, không `block()` trong WebFlux request path |
| Chuyển sang `CompletableFuture`/callback thư viện khác rồi mất metadata | Rời mô hình context của Reactor | Chuyển dữ liệu cần thiết thành tham số; nếu cần, dùng cơ chế context propagation tương thích và được cấu hình rõ |
| Hai request dường như chia sẻ user | Dùng biến static, mutable singleton hoặc ThreadLocal không dọn đúng cách | Không lưu `Authentication` vào state toàn cục; giữ phạm vi theo subscriber và kiểm tra isolation |
| Có `SecurityContext` nhưng vẫn truy cập sai quyền | Nhầm sự hiện diện của context với authorization | Áp dụng `SecurityWebFilterChain`/method security và kiểm tra quyền đối với tài nguyên nghiệp vụ |

**Lưu ý bảo mật:** `Authentication` có thể chứa credentials, claims hoặc token nhạy cảm. Không log toàn bộ `SecurityContext` hoặc serialise nó để truyền sang hệ thống khác. Chỉ dùng dữ liệu tối thiểu cần cho mục đích được phép, và để framework kiểm tra xác thực/phân quyền.

## 8. Cách kiểm tra và gỡ lỗi

1. Xác minh request đã đi qua đúng `SecurityWebFilterChain` và endpoint có yêu cầu xác thực phù hợp.
2. Đặt một điểm quan sát *trong publisher*, chẳng hạn `ReactiveSecurityContextHolder.getContext().map(SecurityContext::getAuthentication)`; kiểm tra trạng thái empty khác với context chứa principal.
3. Kiểm tra có `subscribe()`, `block()`, `toFuture()` hoặc callback bên ngoài Reactor tạo ra ranh giới mới hay không; quan sát vị trí `contextWrite`.
4. Viết test bằng `StepVerifier`: cùng định nghĩa pipeline chạy với `alice`, `bob` và không có authentication; xác nhận kết quả tách biệt và không lẫn user.
5. Kiểm tra quy tắc truy cập endpoint và tài nguyên. Đúng principal chưa bảo đảm đúng permission.

Ba câu hỏi tự kiểm tra:

- Vì sao `publishOn` có thể đổi thread mà một operator `deferContextual` ở cùng chain vẫn đọc được metadata từ subscriber?
- Trong chuỗi `source.contextWrite(...).flatMap(...)`, `flatMap` có chắc đọc được khóa vừa ghi không? Giải thích theo chiều truyền context lúc subscribe.
- Vì sao lấy `username` từ `ReactiveSecurityContextHolder` rồi truyền vào repository là hợp lý, nhưng chỉ đọc username mà bỏ qua kiểm tra owner/role thì chưa đủ an toàn?

**Kết luận:** WebFlux thay đổi đơn vị truyền danh tính thực tế từ giả định “một thread giữ request” sang **một reactive subscription mang ngữ cảnh**. Spring Security dùng `ReactiveSecurityContextHolder` trên Reactor `Context` để principal theo đúng pipeline; code nghiệp vụ vẫn phải ghép publisher đúng cách, xử lý trường hợp context vắng mặt và thực thi phân quyền ở những ranh giới cần bảo vệ.

## Tài liệu tham khảo

- [Project Reactor — Adding a Context to a Reactive Sequence](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/advancedFeatures/context.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — ReactorContextWebFilter API](https://docs.spring.io/spring-security/site/docs/6.2.x/api/org/springframework/security/web/server/context/ReactorContextWebFilter.html)
