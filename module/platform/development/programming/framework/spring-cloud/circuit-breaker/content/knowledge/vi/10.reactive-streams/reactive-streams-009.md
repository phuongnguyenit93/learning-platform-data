# Reactor Context khác ThreadLocal khi chuyển luồng

Trong ứng dụng Spring WebFlux, một request có thể đi qua nhiều toán tử Reactor và được xử lý trên nhiều thread khác nhau. Khi cần giữ thông tin như correlation ID, mã tenant hoặc dữ liệu phục vụ tracing, việc lưu thông tin vào ThreadLocal có thể gây lỗi vì ThreadLocal gắn dữ liệu với một thread cụ thể. Reactor Context được thiết kế cho mô hình reactive: dữ liệu gắn với subscription và có thể được đọc trong chuỗi xử lý dù các toán tử chuyển sang scheduler khác.

Sự khác biệt này đặc biệt quan trọng khi tích hợp Spring Cloud CircuitBreaker với Reactor. Lời gọi WebClient, thao tác qua ReactiveCircuitBreaker và fallback có thể chạy ở những thời điểm hoặc thread khác nhau. Nếu code dựa vào ThreadLocal để lấy request metadata, thông tin có thể không còn hiện diện tại nơi cần dùng. Reactor Context cung cấp cách truyền metadata theo luồng reactive mà không phụ thuộc thread đang thực thi.

## 1. ThreadLocal lưu dữ liệu theo thread

ThreadLocal là cơ chế của Java cho phép mỗi thread có một giá trị riêng gắn với cùng một biến ThreadLocal. Hai thread cùng truy cập một biến sẽ nhìn thấy hai giá trị độc lập. Cơ chế này thường được dùng trong ứng dụng đồng bộ để lưu thông tin gắn với quá trình xử lý trên một thread, ví dụ thông tin người dùng hiện tại hoặc dữ liệu phục vụ logging.

Ví dụ:

~~~java
public final class RequestContextHolder {

    private static final ThreadLocal<String> CORRELATION_ID =
            new ThreadLocal<>();

    private RequestContextHolder() {
    }

    public static void setCorrelationId(String id) {
        CORRELATION_ID.set(id);
    }

    public static String getCorrelationId() {
        return CORRELATION_ID.get();
    }

    public static void clear() {
        CORRELATION_ID.remove();
    }
}
~~~

Trong mô hình xử lý đồng bộ, một request thường được xử lý từ đầu đến cuối trên cùng một thread. Code có thể đặt correlation ID khi bắt đầu request, đọc nó trong các lớp sâu hơn và xóa nó khi request kết thúc.

Nhưng ThreadLocal không tự truyền giá trị từ thread này sang thread khác. Trong hệ thống dùng thread pool, các thread được tái sử dụng cho nhiều công việc khác nhau. Nếu code không xóa giá trị đúng lúc, dữ liệu cũ còn sót lại có thể bị đọc nhầm trong một công việc sau đó.

## 2. Vì sao ThreadLocal không phù hợp để làm nguồn ngữ cảnh chính trong Reactor?

Reactor không bảo đảm một chuỗi xử lý luôn chạy trên một thread. Các toán tử như publishOn và subscribeOn có thể thay đổi scheduler thực thi. Một request có thể bắt đầu trên thread xử lý WebFlux, chuyển sang scheduler khác để thực hiện công việc, rồi tiếp tục trên một thread khác khi nhận tín hiệu.

Ví dụ:

~~~java
Mono<String> pipeline = Mono.just("work")
    .publishOn(Schedulers.boundedElastic())
    .map(ignored -> "correlationId="
            + RequestContextHolder.getCorrelationId());
~~~

Nếu ThreadLocal được đặt trên thread ban đầu trước khi subscription, toán tử map sau publishOn có thể chạy trên một thread thuộc boundedElastic. Thread đó không nhất thiết có giá trị ThreadLocal của thread ban đầu. Kết quả có thể là null hoặc một giá trị khác còn sót trên thread được tái sử dụng.

Hai toán tử thường gặp có vai trò khác nhau:

- **publishOn** chuyển việc xử lý các tín hiệu downstream sau vị trí đặt toán tử sang scheduler được chỉ định.
- **subscribeOn** ảnh hưởng đến scheduler dùng để thực hiện quá trình subscription ở phía upstream.

Cả hai đều có thể làm thay đổi thread thực thi. Do đó, không nên giả định một request reactive sẽ luôn ở trên thread ban đầu hoặc ThreadLocal sẽ tự đi theo request.

## 3. Reactor Context gắn với subscription

Reactor Context là một cấu trúc key-value bất biến, gắn với subscriber và được truyền qua chuỗi reactive. Nó được thiết kế để lưu metadata cần truy cập trong quá trình thực thi publisher, ví dụ:

- Correlation ID hoặc trace ID.
- Mã tenant dùng để chọn phạm vi dữ liệu.
- Metadata về quyền truy cập đã được chuẩn hóa, nếu pipeline cần sử dụng.
- Metadata phục vụ logging, tracing hoặc chính sách nghiệp vụ.

Context không gắn với một thread. Khi Reactor chuyển việc xử lý sang scheduler khác, Context vẫn được truyền theo subscription để các toán tử có thể truy cập.

Có thể hình dung:

~~~mermaid
flowchart TD
    A[Subscriber tạo subscription] --> B[Reactor Context đi theo subscription]
    B --> C[Publisher và các toán tử upstream]
    C --> D[publishOn chuyển scheduler]
    D --> E[Toán tử chạy trên thread khác]
    E --> F[Đọc cùng metadata từ Reactor Context]
~~~

Điều này khác với ThreadLocal: ThreadLocal được tra cứu từ thread hiện tại, còn Reactor Context được truy cập từ subscriber context của chuỗi reactive.

Context là bất biến. Khi thêm hoặc thay đổi giá trị, Reactor tạo một Context mới cho phần upstream tương ứng. Nhờ đó, nhiều request chạy đồng thời có thể mang Context riêng mà không ghi đè dữ liệu của nhau.

## 4. Đưa dữ liệu vào Context bằng contextWrite

Có thể thêm một giá trị vào Context bằng contextWrite:

~~~java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just(context.get("correlationId")))
    .contextWrite(context ->
        context.put("correlationId", "req-2026-001"));
~~~

Trong ví dụ này:

1. contextWrite thêm correlationId vào Context của subscription.
2. deferContextual đọc giá trị từ Context khi publisher được subscribe.
3. Mono phát ra chuỗi req-2026-001.

Có thể dùng Context.of khi muốn tạo Context từ đầu:

~~~java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("correlationId", "unknown")))
    .contextWrite(Context.of("correlationId", "req-2026-001"));
~~~

Các API thường dùng:

| API | Mục đích |
|---|---|
| contextWrite(context -> context.put(key, value)) | Thêm hoặc thay một giá trị trong Context cho upstream |
| Context.of(key, value) | Tạo Context với một hoặc nhiều cặp key-value |
| deferContextual(contextView -> ...) | Đọc Context tại thời điểm subscription |
| contextView.get(key) | Đọc giá trị theo key; phát sinh lỗi nếu key không tồn tại |
| contextView.getOrDefault(key, defaultValue) | Đọc giá trị hoặc dùng mặc định |
| contextView.hasKey(key) | Kiểm tra key có tồn tại hay không |

Nên dùng key có tên rõ ràng và tránh trùng lặp giữa các thành phần. Với ứng dụng lớn, có thể định nghĩa hằng số hoặc key theo namespace để tránh một thư viện ghi đè metadata của thành phần khác.

## 5. Chiều truyền Context và vị trí đặt contextWrite

Một điểm dễ nhầm là Context được truyền từ subscriber về phía upstream, ngược chiều phát dữ liệu. Toán tử contextWrite làm thay đổi Context mà các toán tử nằm phía upstream nhìn thấy.

Ví dụ:

~~~java
Mono<String> pipeline =
        Mono.deferContextual(context ->
                Mono.just("trace=" + context.get("traceId")))
            .map(value -> value + ", processed")
            .contextWrite(context -> context.put("traceId", "trace-001"));
~~~

contextWrite nằm phía dưới trong chuỗi khai báo, nhưng Context được cung cấp cho các toán tử phía trên nó khi subscription diễn ra. Vì vậy, deferContextual có thể đọc traceId.

Nếu đặt contextWrite ở một nhánh không nằm trong cùng subscription, nhánh khác sẽ không tự động nhận được giá trị đó. Khi compose nhiều publisher, cần hiểu ranh giới subscription và vị trí đặt contextWrite.

Ví dụ với hai nhánh:

~~~java
Mono<String> source = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("tenantId", "public")));

Mono<String> result = source
        .flatMap(value -> source.map(other -> value + ":" + other))
        .contextWrite(context -> context.put("tenantId", "tenant-a"));
~~~

Các publisher được compose trong cùng chuỗi subscription có thể nhìn thấy Context tương ứng. Tuy nhiên, nếu tạo một subscription độc lập bằng subscribe() hoặc khởi chạy một tác vụ bên ngoài chuỗi, Context không tự động được chia sẻ sang tác vụ đó. Hãy ưu tiên compose publisher thay vì tự tạo subscription mới.

## 6. Context vẫn tồn tại khi chuyển scheduler

Ví dụ sau minh họa việc đọc cùng một correlation ID trước và sau publishOn:

~~~java
Mono<String> pipeline = Mono.deferContextual(context -> {
        String beforeSwitch = context.get("correlationId");

        return Mono.just(beforeSwitch)
                .publishOn(Schedulers.boundedElastic())
                .map(value -> {
                    String afterSwitch = context.get("correlationId");
                    return value + " -> " + afterSwitch;
                });
    })
    .contextWrite(context ->
            context.put("correlationId", "req-42"));
~~~

Mục đích của ví dụ là cho thấy Context được gắn với subscription, không phụ thuộc thread. Dù map được thực thi trên scheduler khác, nó vẫn có thể đọc metadata trong Context của subscriber.

Trong code thực tế, nếu cần đọc Context ở nhiều điểm, nên dùng deferContextual tại vị trí cần truy cập. Không nên đọc Context lúc tạo publisher rồi lưu giá trị vào biến toàn cục hoặc biến dùng chung cho nhiều request.

## 7. Áp dụng Reactor Context cho lời gọi Circuit Breaker reactive

Trong Spring Cloud CircuitBreaker, ReactiveCircuitBreaker bảo vệ các publisher Mono hoặc Flux. Metadata như correlation ID có thể được đặt vào Context trước khi publisher được subscribe. Khi lời gọi đi qua WebClient, Circuit Breaker và fallback, các toán tử reactive trong cùng chuỗi có thể đọc metadata đó.

Ví dụ:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class PartnerClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker circuitBreaker;

    public PartnerClient(
            WebClient webClient,
            ReactiveCircuitBreaker circuitBreaker) {
        this.webClient = webClient;
        this.circuitBreaker = circuitBreaker;
    }

    public Mono<PartnerResponse> findPartner(String partnerId) {
        Mono<PartnerResponse> remoteCall = webClient.get()
                .uri("/partners/{id}", partnerId)
                .retrieve()
                .bodyToMono(PartnerResponse.class);

        return circuitBreaker.run(
                remoteCall,
                error -> Mono.deferContextual(context -> {
                    String correlationId =
                            context.getOrDefault("correlationId", "unknown");

                    logFallback(correlationId, error);
                    return Mono.just(PartnerResponse.unavailable(partnerId));
                })
        );
    }

    private void logFallback(String correlationId, Throwable error) {
        // Ghi log có correlation ID và nguyên nhân fallback.
    }
}
~~~

Tầng gọi có thể bổ sung Context:

~~~java
return partnerClient.findPartner(partnerId)
        .contextWrite(context ->
                context.put("correlationId", correlationId));
~~~

Trong thiết kế này, fallback dùng deferContextual để đọc correlation ID tại thời điểm subscription. Không nên gọi context.get trong lúc tạo publisher vì khi đó chưa có subscriber context để đọc.

Việc Context có được bảo toàn qua fallback hay không cần được xác nhận bằng kiểm thử tích hợp với phiên bản Spring Cloud CircuitBreaker, Resilience4j và Reactor của ứng dụng. Khi fallback được compose trong cùng chuỗi reactive, Reactor Context là cơ chế phù hợp để truyền metadata. Nếu adapter hoặc code tùy chỉnh tạo subscription độc lập, Context có thể không còn nằm trong cùng phạm vi.

## 8. ThreadLocal, MDC và logging

Nhiều thư viện logging dùng MDC (Mapped Diagnostic Context) để gắn correlation ID vào log. MDC truyền thống dựa trên ThreadLocal. Vì vậy, nếu ứng dụng reactive chuyển scheduler, MDC có thể không chứa giá trị mong đợi ở thread hiện tại.

Có thể xử lý theo một số cách:

- Dùng Micrometer Context Propagation để đăng ký cách đọc, ghi và xóa giá trị ThreadLocal, sau đó kết nối với Reactor Context theo cơ chế mà phiên bản thư viện hỗ trợ.
- Dùng Micrometer Tracing hoặc tích hợp tracing của Spring Boot để quản lý trace context xuyên suốt các thành phần được hỗ trợ.
- Ghi log từ các toán tử reactive bằng metadata đọc trực tiếp từ Reactor Context, nếu không cần MDC.
- Nếu cần bridge sang MDC, bảo đảm giá trị được khôi phục và xóa đúng lúc để thread pool không giữ dữ liệu của request trước.

Reactor và hệ sinh thái Micrometer có cơ chế context propagation để kết nối Context với các thư viện imperative dựa trên ThreadLocal. Tuy nhiên, khả năng tự động propagation phụ thuộc phiên bản Reactor, Micrometer Context Propagation và cách ứng dụng bật chế độ tương ứng. Không nên giả định ThreadLocal tự động được đồng bộ chỉ vì ứng dụng đã dùng Reactor.

Một cách tiếp cận là đăng ký ThreadLocalAccessor cho MDC hoặc một ThreadLocal cụ thể trong ContextRegistry, sau đó sử dụng cơ chế capture/restore phù hợp với phiên bản. Với một số cấu hình Reactor, có thể bật automatic context propagation bằng hook tương ứng. Cần kiểm tra tài liệu của dependency thực tế và tránh bật nhiều cơ chế bridge chồng chéo.

## 9. contextCapture và automatic context propagation

Micrometer Context Propagation cung cấp công cụ để capture giá trị từ các context kiểu ThreadLocal đã đăng ký và chuyển chúng vào cơ chế context phù hợp. Trong môi trường Reactor, các API tích hợp có thể hỗ trợ việc capture tại thời điểm subscription và khôi phục ThreadLocal khi callback được thực thi.

Hai khái niệm cần phân biệt:

- **Context capture** lấy giá trị từ ThreadLocal đã đăng ký tại một thời điểm và đưa vào Reactor Context. Việc này hữu ích khi bắt đầu một chuỗi reactive từ code imperative có sẵn ThreadLocal.
- **Automatic context propagation** cho phép Reactor tự động khôi phục các ThreadLocal đã đăng ký trong phạm vi thực thi các callback được hỗ trợ. Cơ chế này cần phiên bản tương thích và cấu hình rõ ràng.

Không phải mọi ThreadLocal đều tự động được capture. Chỉ những accessor đã đăng ký và được cơ chế propagation hỗ trợ mới có thể được đọc/ghi theo quy tắc tương ứng. Việc capture cũng không có nghĩa toàn bộ trạng thái thread được sao chép.

Trong ứng dụng Spring Boot, hãy xem phiên bản Reactor và Micrometer Context Propagation do dependency management của dự án cung cấp. Kiểm tra hướng dẫn cấu hình của phiên bản đó trước khi bật hook hoặc sử dụng contextCapture. Nếu không cần tương thích với thư viện imperative, ưu tiên dùng Reactor Context trực tiếp để giảm phụ thuộc vào trạng thái thread.

## 10. Những điều không nên lưu trong Reactor Context

Reactor Context phù hợp với metadata cần truy cập trong chuỗi xử lý, nhưng không phải nơi lưu mọi dữ liệu của ứng dụng.

Nên lưu các giá trị nhỏ và ổn định như correlation ID, trace metadata hoặc tenant identifier. Không nên lưu:

- Request body lớn hoặc đối tượng dữ liệu có vòng đời dài.
- Buffer, stream hoặc tài nguyên cần đóng.
- Mutable object được nhiều nhánh publisher cùng sửa.
- Secret, access token hoặc thông tin xác thực nếu không thực sự cần thiết.
- Dữ liệu cần được truyền qua mạng mà chưa có cơ chế mã hóa và kiểm soát riêng.

Context là cấu trúc bất biến, nhưng object được lưu bên trong không tự động bất biến. Nếu đặt một mutable object vào Context rồi nhiều nhánh cùng thay đổi object đó, vẫn có thể xảy ra race condition. Hãy lưu giá trị bất biến hoặc dữ liệu metadata nhỏ.

Context cũng không tự truyền sang một dịch vụ khác qua HTTP. Nếu cần truyền correlation ID sang dependency, phải đưa nó vào header bằng WebClient filter hoặc sử dụng tracing instrumentation phù hợp. Reactor Context chỉ quản lý dữ liệu trong phạm vi reactive pipeline hiện tại.

## 11. Các lỗi thường gặp khi chuyển luồng

- **Đọc ThreadLocal sau publishOn và mong đợi giá trị cũ**: callback có thể chạy trên thread khác; dùng Reactor Context hoặc bridge đã cấu hình.
- **Đọc Context khi assembly thay vì subscription**: dùng deferContextual để truy cập Context tại thời điểm thực thi.
- **Đặt contextWrite sai vị trí**: Context được cung cấp cho upstream; cần kiểm tra toán tử nào nằm trong phạm vi đó.
- **Gọi subscribe() trong service**: subscription độc lập có thể tách khỏi Context của request ban đầu.
- **Dùng chung mutable object trong Context**: Context bất biến không làm object bên trong trở thành bất biến.
- **Dùng MDC mà không propagation**: log trên thread khác có thể thiếu correlation ID hoặc đọc nhầm giá trị.
- **Không xóa ThreadLocal khi bridge thủ công**: thread pool tái sử dụng có thể làm rò rỉ dữ liệu giữa các request.
- **Cho rằng Context tự đi qua HTTP**: cần WebClient filter hoặc tracing để truyền metadata qua ranh giới dịch vụ.
- **Không kiểm thử fallback**: fallback là một nhánh khác của pipeline; cần xác nhận nó đọc được metadata mong muốn trong phiên bản đang chạy.

## 12. Quy trình áp dụng trong dịch vụ Spring Cloud CircuitBreaker

Khi một reactive service cần giữ request metadata qua lời gọi dependency và fallback, có thể thực hiện theo trình tự:

1. Xác định metadata cần truyền, chẳng hạn correlation ID hoặc tenant ID.
2. Định nghĩa key thống nhất và chỉ lưu giá trị nhỏ, bất biến trong Reactor Context.
3. Đưa metadata vào pipeline bằng contextWrite tại tầng bắt đầu xử lý.
4. Dùng deferContextual ở các toán tử cần đọc metadata, kể cả trong fallback.
5. Compose WebClient và ReactiveCircuitBreaker trong cùng chuỗi reactive; tránh tự subscribe hoặc tạo tác vụ độc lập.
6. Nếu cần MDC hoặc thư viện imperative, cấu hình Micrometer Context Propagation với accessor phù hợp và kiểm tra tương thích phiên bản.
7. Nếu cần truyền metadata qua HTTP, cấu hình WebClient filter hoặc tracing instrumentation để đưa metadata vào header.
8. Kiểm thử qua publishOn, subscribeOn, nhánh fallback và nhiều request đồng thời để xác nhận không mất hoặc trộn lẫn Context.

Reactor Context gắn metadata với subscription nên phù hợp với mô hình reactive và vẫn có thể truy cập khi luồng chuyển scheduler. ThreadLocal gắn dữ liệu với thread nên chỉ an toàn khi vòng đời xử lý được giữ trên thread đó hoặc có cơ chế propagation rõ ràng. Khi kết hợp Spring Cloud CircuitBreaker với WebFlux, dùng Reactor Context cho metadata trong pipeline, thiết kế fallback để đọc Context đúng thời điểm và chỉ bridge sang ThreadLocal khi cần tích hợp thư viện imperative.
