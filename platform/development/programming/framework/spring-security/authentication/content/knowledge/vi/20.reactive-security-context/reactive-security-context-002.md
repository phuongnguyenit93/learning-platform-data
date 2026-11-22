# Thời điểm đăng ký Publisher và vòng đời danh tính trong chuỗi

Trong Spring Security WebFlux, danh tính của một luồng xử lý không được gắn cố định vào lúc tạo đối tượng Mono/Flux. Danh tính được cung cấp và tra cứu qua **Reactor Context của từng subscription**. Hiểu đúng thời điểm này giúp tránh đọc nhầm người dùng, thất lạc SecurityContext hoặc rò dữ liệu giữa các request.

## 1. Phân biệt assembly và subscription

Một Publisher mô tả *cách xử lý*; việc tạo nó thường chưa thực thi tác vụ bất đồng bộ.

| Giai đoạn | Điều xảy ra | Ý nghĩa đối với danh tính |
| --- | --- | --- |
| Assembly (lắp chuỗi) | Controller/service trả về Mono hoặc Flux, khai báo các toán tử như map, flatMap, contextWrite. | Chưa thể mặc định biết Authentication nào sẽ đi cùng subscription tương lai. |
| Subscription (đăng ký) | Subscriber đăng ký; tín hiệu subscribe đi từ cuối chuỗi về nguồn, rồi dữ liệu/lỗi/hoàn thành đi theo hướng xử lý. | Reactor Context được truyền theo subscriber; phần đọc SecurityContext lười thực thi mới thấy danh tính của subscription đó. |
| OnNext / OnError / OnComplete | Publisher phát tín hiệu và kết thúc, hoặc bị hủy bởi cancel. | Context thuộc phạm vi subscription; không phải biến toàn cục hay danh tính tồn tại mãi sau request. |

Trong WebFlux, thông thường **framework thực hiện subscribe** cho Publisher trả về từ handler. Việc gọi phương thức controller để lấy Mono không đồng nghĩa mọi logic trong Mono đã chạy. Nếu một callback, phép tính hoặc lệnh gọi ngoài Publisher chạy ngay khi lắp chuỗi thì nó vẫn có thể chạy sớm; tính lazy phụ thuộc cách tạo Publisher.

Ví dụ Java có Reactor:

~~~java
Mono<String> eager = Mono.just(expensiveCall()); // expensiveCall() chạy ngay
Mono<String> lazy = Mono.fromCallable(() -> expensiveCall()); // chạy khi subscribe
Mono<String> deferred = Mono.defer(() -> buildPublisher()); // tạo Publisher bên trong khi subscribe
~~~

Đây là **mảnh mã minh họa**, không phải chương trình độc lập. Nếu công việc có side effect hoặc cần danh tính request, đặt nó trong nhánh reactive được thực thi lúc đăng ký. Không dùng Mono.just để trì hoãn một phép gọi đã chạy trước.

## 2. Danh tính nằm ở đâu trong WebFlux?

Trong Spring MVC đồng bộ, mã thường quen với SecurityContextHolder dựa trên ThreadLocal. Trong xử lý reactive, các đoạn của một request có thể chạy trên nhiều thread và một thread có thể phục vụ nhiều request. Vì vậy ThreadLocal không phải nguồn đáng tin để suy ra người dùng hiện tại ở mọi đoạn của pipeline.

Spring Security reactive dùng:

- **Authentication**: principal, quyền và trạng thái xác thực của người dùng/ứng dụng.
- **SecurityContext**: chứa Authentication.
- **ReactiveSecurityContextHolder**: API đọc/đưa Mono<SecurityContext> vào Reactor Context.
- **Reactor Context**: dữ liệu gắn với *subscriber*, bất biến theo cách sử dụng (contextWrite tạo context mới cho phần chuỗi chịu ảnh hưởng).

API trọng tâm:

~~~java
Mono<SecurityContext> context = ReactiveSecurityContextHolder.getContext();

Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> forOneSubscription = username.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication)
);
~~~

Đây là **mảnh mã minh họa**; biến authentication phải có giá trị phù hợp trong scope. getContext() trả về Publisher, không trả về SecurityContext đồng bộ. Nếu không có context, Mono có thể hoàn thành rỗng. Tùy cấu hình anonymous authentication, một request chưa đăng nhập có thể thấy principal ẩn danh thay vì Mono rỗng; không được đồng nhất hai trường hợp.

Lưu ý: withAuthentication(...) thêm Authentication vào **Reactor Context của subscription chịu ảnh hưởng**. Nó **không tự lưu trạng thái đăng nhập qua request khác** và không thay thế chính sách xác thực, repository hoặc token của ứng dụng.

## 3. Dòng thời gian của một request WebFlux

Một đường đi điển hình (chi tiết tùy cấu hình filter):

1. HTTP request vào chuỗi WebFilter/Spring Security.
2. Spring Security lấy thông tin xác thực từ cơ chế thích hợp. ReactorContextWebFilter có thể dùng ServerSecurityContextRepository để khởi tạo ReactiveSecurityContextHolder; AuthenticationWebFilter có thể thiết lập context khi xác thực thành công.
3. Handler tạo và trả Mono/Flux. Khi WebFlux subscribe vào Publisher, Reactor Context của subscriber được đưa đến các toán tử thuộc scope.
4. Khi một toán tử đọc ReactiveSecurityContextHolder.getContext() trong chuỗi, nó nhận context có hiệu lực đối với **subscription hiện tại**.
5. Khi response hoàn thành, lỗi hoặc bị hủy, subscription kết thúc. Context của subscription không phải kho dữ liệu lâu dài. Nếu muốn duy trì xác thực giữa các request, phải có chiến lược lưu/khôi phục thích hợp (ví dụ session) hoặc xác thực lại từ token ở request mới.

Sơ đồ thời gian:

~~~text
HTTP request
  -> Spring Security WebFilter / xác thực
  -> tạo chuỗi Mono/Flux (assembly)
  -> WebFlux subscribe
       -> subscriber mang Reactor Context
       -> contextWrite bổ sung context cho upstream
       -> getContext() đọc Authentication của subscription đó
       -> xử lý dữ liệu -> complete / error / cancel
  -> kết thúc phạm vi subscription
~~~

Context không được gắn với "lúc khai báo biến Mono". Hai request có thể dùng cùng một mô tả pipeline nhưng đăng ký với hai context khác nhau. Sự cô lập chỉ còn đúng nếu ứng dụng không chia sẻ trạng thái mutable hoặc cache dữ liệu phụ thuộc danh tính sai phạm vi.

## 4. Ví dụ Java 17+: một Publisher, ba subscription

Ví dụ dưới đây chạy trong project có **reactor-core** và **spring-security-core** (thường đã có trong ứng dụng Spring Boot WebFlux dùng Spring Security). Tệp: **IdentityContextDemo.java**.

~~~java
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public class IdentityContextDemo {

    public static void main(String[] args) {
        Mono<String> identity = Mono.defer(() -> {
            System.out.println("read during subscribe");
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
        });

        System.out.println("ASSEMBLED");

        System.out.println("S1=" + identity
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")))
            .block());

        System.out.println("S2=" + identity
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("bob")))
            .block());

        System.out.println("S3=" + identity.block());
    }

    private static Authentication user(String name) {
        return new UsernamePasswordAuthenticationToken(
            name,
            "demo",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }
}
~~~

Kết quả stdout chính xác:

~~~text
ASSEMBLED
read during subscribe
S1=alice
read during subscribe
S2=bob
read during subscribe
S3=anonymous
~~~

Giải thích:

- Chỉ tạo Mono tại dòng khai báo identity thì chưa in "read during subscribe".
- Mỗi block() trong chương trình demo tạo **một subscription riêng**, nên Mono.defer chạy ba lần.
- S1 và S2 áp dụng contextWrite khác nhau cho cùng một Publisher được xây dựng trước đó, lần lượt đọc alice và bob.
- S3 không gắn SecurityContext, vì vậy defaultIfEmpty phát "anonymous".
- Giá trị Authentication trong ví dụ chỉ là dữ liệu kiểm thử; ứng dụng thật phải xác thực credential/token bằng cơ chế tin cậy trước khi cấp quyền.

**Không sao chép cách dùng block() vào WebFlux controller hoặc xử lý trên event-loop.** block() ở đây chỉ làm cho chương trình main đồng bộ dễ quan sát và chủ động tạo subscription. Trong ứng dụng, trả Mono/Flux cho framework để framework quản lý việc đăng ký.

## 5. contextWrite được áp dụng cho phần nào của chuỗi?

Reactor Context đi theo **hướng từ subscriber (downstream) lên nguồn (upstream) trong giai đoạn subscribe**. Vì vậy toán tử contextWrite ở phía dưới một đoạn xử lý có thể bổ sung context mà đoạn phía trên nhìn thấy. Không hiểu contextWrite như thao tác sửa biến toàn cục cho toàn bộ chuỗi.

Ví dụ độc lập về Reactor Context (mảnh mã; giả sử đã import Mono):

~~~java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just("user=" + ctx.getOrDefault("user", "guest"))
);

String a = message.contextWrite(ctx -> ctx.put("user", "alice")).block();
String b = message.block();

// a = "user=alice"
// b = "user=guest"
~~~

Các chú thích a/b là kết quả mong đợi khi chạy trong môi trường demo đồng bộ. contextWrite chỉ tác động đến subscription a; không sửa Publisher message để b tự động thành alice.

**Vị trí của contextWrite quan trọng.** Xét mảnh mã:

~~~java
Mono<String> identity = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .defaultIfEmpty("anonymous");

Mono<String> correct = Mono.just("go")
    .flatMap(value -> identity)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")));

Mono<String> wrongScope = Mono.just("go")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")))
    .flatMap(value -> identity);
~~~

Khi subscribe độc lập trong môi trường không có context bên ngoài, correct phát "alice", còn wrongScope phát "anonymous": contextWrite của wrongScope nằm ở upstream của flatMap, trong khi Publisher identity được đăng ký bởi flatMap ở phía downstream. Quy tắc thực hành: đặt scope context ở đoạn bao trùm **toàn bộ phần xử lý cần đọc nó**, và kiểm tra vị trí của toán tử đọc context khi tách chuỗi.

Nếu cần dữ liệu tùy ý từ Reactor Context, dùng Mono.deferContextual(...) (hoặc API contextual tương ứng). Với danh tính Spring Security, ưu tiên ReactiveSecurityContextHolder.getContext(), tránh tự đoán key nội bộ trong Reactor Context.

## 6. Giữ danh tính xuyên suốt flatMap và thao tác bất đồng bộ

Trong chuỗi thuần Reactor, flatMap, concatMap, publishOn và subscribeOn làm việc với subscription/context của Reactor. Việc chuyển scheduler bằng publishOn/subscribeOn **không có nghĩa tự động mất Reactor Context**. Tuy nhiên ThreadLocal tùy ý, MDC, tác vụ gửi thủ công sang executor hoặc callback của thư viện ngoài Reactor không tự nhiên có cùng ngữ nghĩa.

Mẫu phục vụ nghiệp vụ theo người dùng:

~~~java
public Mono<Order> currentUserOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .switchIfEmpty(Mono.error(new IllegalStateException("Missing authentication")))
        .flatMap(auth -> orderService.findForOwner(orderId, auth.getName()));
}
~~~

Đây là **mảnh mã service**, phụ thuộc kiểu Order và orderService của ứng dụng. Repository phải kiểm tra ownership/quyền tại nơi truy vấn phù hợp; chỉ truyền auth.getName() không tự bảo đảm authorization. Với hệ thống dùng định danh bất biến, nên lấy id ổn định từ principal/token thay vì giả định username luôn là khóa dữ liệu.

Tình huống sai thường thấy:

~~~java
public Mono<Void> triggerAudit() {
    auditPublisher.subscribe(); // tự tạo subscription tách khỏi request
    return Mono.empty();
}
~~~

Lời gọi subscribe() này tạo nhánh độc lập, không đương nhiên được quản lý cancellation/error/context của request. Mẫu đúng là **nối việc audit vào pipeline trả về**:

~~~java
public Mono<Void> triggerAudit() {
    return auditPublisher.then();
}
~~~

Hai mảnh mã trên giả sử auditPublisher là Mono<Void> hoặc Publisher tương thích. Nếu auditPublisher đã sinh dữ liệu ở assembly hoặc cần chạy nền thực sự, thiết kế lifecycle riêng và truyền identity tối thiểu, rõ ràng; không dựa vào việc subscriber mới tự thừa hưởng Reactor Context.

## 7. Các điểm gãy vòng đời và rủi ro rò danh tính

| Tình huống | Điều cần hiểu | Cách xử lý |
| --- | --- | --- |
| Đọc SecurityContextHolder.getContext() trong reactive handler | ThreadLocal phụ thuộc thread; nhiều request có thể xen kẽ trên cùng pool. | Dùng ReactiveSecurityContextHolder.getContext() trong Mono/Flux, hoặc principal được WebFlux cung cấp. |
| Gọi block() để lấy Authentication trong controller/service | Tạo subscription riêng, có thể mất context request và chặn event-loop. | Giữ xử lý ở map/flatMap, trả Publisher. |
| Gọi subscribe() bên trong doOnNext/subscribe(...) | Nhánh con có subscription/lifecycle riêng; lỗi và cancel khó quản lý, context có thể thiếu. | Kết hợp nhánh con bằng flatMap/then/when và trả Publisher cho WebFlux. |
| Mono.cache(), share(), hot Publisher chứa kết quả theo người dùng | Kết quả có thể được tái sử dụng giữa subscriber; context khác không tính lại giá trị đã cache. | Không cache kết quả nhạy cảm theo danh tính ở scope dùng chung; nếu cần cache, phân vùng theo key người dùng và quyền, kèm chính sách hết hạn/vô hiệu hóa. |
| Lưu Authentication vào static field, singleton mutable field | Danh tính của request này có thể đè request khác. | Giữ dữ liệu theo subscription hoặc truyền principal cụ thể qua đối số. |
| Chuyển sang CompletionStage, executor, API callback ngoài Reactor | Cơ chế truyền Reactor Context không nhất thiết vượt ranh giới tích hợp. | Truyền thông tin tối thiểu tường minh hoặc dùng cơ chế context propagation đã cấu hình, có test xác nhận. |
| retry()/repeat() | Có thể tái đăng ký nguồn và chạy lại side effect. | Thiết kế tác vụ idempotent, đọc context trong subscription, xác định rõ quyền và trạng thái được dùng mỗi lần thử. |
| cancel/error | Pipeline kết thúc sớm; doOnComplete không chạy cho mọi kiểu kết thúc. | Dùng doFinally khi cần cleanup cho complete, error hoặc cancel; không giữ principal ngoài vòng đời. |

Một minh họa nguy hiểm của cache (mảnh mã; identity và user(...) như mục 4):

~~~java
Mono<String> shared = identity.cache();

String first = shared
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")))
    .block();

String second = shared
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("bob")))
    .block();
~~~

Sau lần đầu hoàn tất thành công, first và second có thể cùng là "alice", vì Mono.cache() phát lại tín hiệu đã lưu mà không chạy lại nguồn cho subscriber sau. **Đây là lỗi thiết kế cache thông tin theo người dùng**, không phải bằng chứng Reactor Context bị lẫn. Không dùng cache chia sẻ toàn ứng dụng cho kết quả phụ thuộc SecurityContext.

## 8. SecurityContext trong subscription khác với phiên đăng nhập

Cần tách ba câu hỏi:

1. **Ai xác thực request này?** Bộ lọc xác thực, token, session/repository hoặc cấu hình an ninh xác định Authentication hợp lệ.
2. **Đoạn reactive hiện tại thấy ai?** SecurityContext trong Reactor Context của subscription hiện tại, miễn là toán tử đọc nằm đúng scope.
3. **Request kế tiếp thấy ai?** Phụ thuộc cơ chế duy trì/khôi phục xác thực giữa request; contextWrite của một Publisher không có nhiệm vụ đó.

Ví dụ, ứng dụng stateless có thể xác minh bearer token ở mỗi request; ứng dụng dùng session có thể lưu/khôi phục SecurityContext qua ServerSecurityContextRepository. Cả hai đều có thể sử dụng Reactor Context **trong** một request. Không dùng withAuthentication của đoạn demo để giả làm đăng nhập thành công trong production.

Reactive method security cũng dựa vào Reactor Context. Để kiểm tra quyền trong đường đi reactive, giữ chuỗi trả về Mono/Flux dưới sự quản lý của Spring Security; tránh tự tách subscribe làm mất phạm vi áp dụng chính sách.

## 9. Kiểm thử bằng StepVerifier

Ví dụ kiểm thử chủ đích (mảnh mã JUnit 5; project cần reactor-test và spring-security-core, cùng phương thức user(...) từ ví dụ chính):

~~~java
@Test
void eachSubscriptionReadsItsOwnIdentity() {
    Mono<String> identity = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");

    StepVerifier.create(identity.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(user("alice"))))
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(identity.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(user("bob"))))
        .expectNext("bob")
        .verifyComplete();

    StepVerifier.create(identity)
        .expectNext("anonymous")
        .verifyComplete();
}
~~~

Cần import org.junit.jupiter.api.Test và reactor.test.StepVerifier, cùng các import IdentityContextDemo ở mục 4. Kiểm thử không cần gọi block(); StepVerifier chủ động đăng ký và xác minh tín hiệu. Để test lỗi scope, đặt contextWrite trước/sau flatMap như mục 5 và so sánh kết quả. Để test rò dữ liệu, dùng hai principal khác nhau cùng một Publisher cache/share và xác minh thiết kế không trả dữ liệu của principal thứ nhất cho principal thứ hai.

## 10. Cách áp dụng khi thiết kế và debug

Khi một request báo "không tìm thấy người dùng", "đôi lúc sai danh tính" hoặc "mất Authentication sau bất đồng bộ", kiểm tra lần lượt:

1. **Điểm tạo Publisher:** có chạy side effect/đọc ThreadLocal ngay lúc assembly hay không?
2. **Điểm subscribe:** WebFlux là subscriber hay có subscribe()/block() thủ công tạo đường đi mới?
3. **Nguồn Authentication:** bộ lọc xác thực đã tạo/khôi phục SecurityContext chưa, request có thật sự được xác thực không?
4. **Ranh giới contextWrite:** toán tử đọc ReactiveSecurityContextHolder có nằm upstream trong scope phù hợp không?
5. **Ranh giới thư viện:** scheduler thuần Reactor hay callback/executor ngoài Reactor?
6. **Chia sẻ kết quả:** có cache, singleton state, hot Publisher hoặc retry làm sai phạm vi dữ liệu không?
7. **Kết thúc:** complete/error/cancel có cleanup phù hợp và không lưu tham chiếu danh tính vượt vòng đời request không?

Tư duy cốt lõi: **Publisher là bản mô tả; subscription là một lần thực thi với Reactor Context của riêng nó.** Đọc danh tính ở vị trí reactive thích hợp tại thời điểm đăng ký; giữ phạm vi của SecurityContext cùng pipeline, không biến nó thành state toàn cục.

### Tài liệu kỹ thuật

- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — ReactiveSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — ReactorContextWebFilter API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html
- Project Reactor — Context reference: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
