# Truyền mã theo dõi yêu cầu qua luồng con và ranh giới thực thi

Một yêu cầu trong ứng dụng reactive thường đi qua nhiều bước: nhận HTTP request, đọc dữ liệu, gọi dịch vụ phụ thuộc, chuyển sang scheduler khác, ghi audit và trả response. Khi có lỗi hoặc độ trễ, nhóm vận hành cần biết các log và thao tác đó thuộc cùng một yêu cầu nào.

Mã theo dõi (correlation ID hoặc trace ID) cung cấp mối liên hệ này. Trong Project Reactor, cách phù hợp để mang metadata theo một lần đăng ký là **Reactor Context**. Context gắn với subscriber và subscription, vì vậy có thể đi cùng tín hiệu qua các toán tử và ranh giới scheduler mà không phụ thuộc thread hiện tại.

Bài học này trình bày cách đưa mã theo dõi vào Context tại ranh giới request, đọc nó trong các Publisher con, giữ nó qua `publishOn` và `flatMap`, tích hợp với logging dựa trên ThreadLocal và kiểm thử việc truyền ngữ cảnh.

Các kiểu `Order`, `OrderView`, `Inventory`, `UserProfile` và những client trong ví dụ là kiểu miền minh họa do ứng dụng định nghĩa; các đoạn mã tập trung vào phần xử lý Context và có thể cần thêm import theo dự án.

## 1. Vì sao cần truyền mã theo dõi?

Giả sử một request tạo ra pipeline sau:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Load order"]
    B --> C["Load customer"]
    C --> D["Check inventory"]
    D --> E["Write audit"]
    E --> F["HTTP response"]
~~~

Mỗi bước có thể chạy trên thread khác nhau hoặc gọi một Publisher con. Nếu log chỉ ghi thread name, việc tìm các dòng thuộc cùng một request trở nên khó khăn. Nếu mỗi phương thức tự tạo một mã mới, các log không còn liên kết với nhau.

Một mã theo dõi được tạo hoặc tiếp nhận ở ranh giới vào ứng dụng và được truyền qua toàn bộ pipeline giúp:

- Ghép log từ nhiều bước xử lý thành một luồng yêu cầu.
- Tìm các thao tác chậm hoặc lỗi trong một request cụ thể.
- Truyền metadata tới client hoặc service được gọi nếu giao thức yêu cầu.
- Tránh truyền tham số kỹ thuật qua mọi chữ ký phương thức nghiệp vụ.
- Phân biệt các lần đăng ký đồng thời dù chúng chạy xen kẽ trên cùng scheduler.

Mã theo dõi là metadata của quá trình xử lý. Nó thường phù hợp với Context hơn là trở thành một trường trong mọi object nghiệp vụ.

## 2. Reactor Context gắn với subscription

Reactor Context là cấu trúc key-value bất biến gắn với subscriber. Nó được dùng để truyền metadata qua pipeline, chẳng hạn trace ID, tenant ID hoặc thông tin phục vụ quan sát.

Một vài đặc điểm cần nhớ:

- Context thuộc về một subscription, không phải một thread.
- Mỗi subscription có Context riêng; hai request đồng thời không ghi đè Context của nhau.
- Context bất biến. Các thao tác như `put` tạo Context mới thay vì sửa object hiện tại.
- Context có thể đi qua các toán tử Reactor và ranh giới scheduler.
- Context không tự động biến thành `ThreadLocal` hoặc MDC.
- Context nên chứa metadata nhỏ, ổn định; không nên dùng làm nơi lưu object nghiệp vụ lớn.

Có thể định nghĩa một key dùng chung:

~~~java
final class TraceContext {
    static final String TRACE_ID = "app.traceId";

    private TraceContext() {}
}
~~~

Nên đặt tên key có namespace để giảm nguy cơ trùng với key của thư viện hoặc module khác. Với hệ thống lớn, có thể gom key vào một lớp hằng số hoặc dùng kiểu key riêng theo quy ước của ứng dụng.

## 3. Đưa trace ID vào Context tại ranh giới request

Ở tầng HTTP, mã theo dõi có thể được đọc từ header do gateway gửi đến hoặc được tạo mới nếu request chưa có mã. Header đầu vào cần được kiểm tra độ dài và ký tự hợp lệ trước khi dùng trong log.

Ví dụ với Spring WebFlux `WebFilter`:

~~~java
import java.util.UUID;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

final class TraceIdWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String supplied = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Request-Id");

        String traceId = isValid(supplied)
            ? supplied
            : UUID.randomUUID().toString();

        exchange.getResponse()
            .getHeaders()
            .set("X-Request-Id", traceId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put(TraceContext.TRACE_ID, traceId)
            );
    }

    private boolean isValid(String value) {
        return value != null
            && value.length() <= 128
            && value.matches("[A-Za-z0-9._-]+");
    }
}
~~~

`contextWrite` đặt trace ID vào Context của subscription xử lý request. Các toán tử nằm phía upstream của ranh giới này có thể đọc giá trị đó. Việc trả header response giúp client và log phía server cùng tham chiếu một mã.

Trong môi trường có gateway tin cậy, cần quy định rõ thành phần nào được phép cung cấp trace ID. Không nên tin một header tùy ý từ Internet nếu giá trị đó có thể chứa ký tự điều khiển, dữ liệu nhạy cảm hoặc gây nhầm lẫn khi truy vấn log. Có thể thay thế bằng trace ID do server sinh hoặc dùng chuẩn tracing do hạ tầng đã quản lý.

## 4. Đọc Context bằng deferContextual

Để đọc Context, dùng `deferContextual`. Hàm nhận `ContextView`, chỉ đọc được các key đang có trong subscription:

~~~java
import reactor.core.publisher.Mono;

Mono<String> currentTraceId = Mono.deferContextual(contextView ->
    Mono.just(contextView.get(TraceContext.TRACE_ID))
);
~~~

`deferContextual` trì hoãn việc đọc cho đến lúc có subscription. Vì vậy, mỗi subscription có thể nhận trace ID riêng.

Có thể dùng `getOrDefault` khi metadata là tùy chọn:

~~~java
Mono<String> currentTraceId = Mono.deferContextual(contextView ->
    Mono.just(
        contextView.getOrDefault(TraceContext.TRACE_ID, "trace-missing")
    )
);
~~~

Nếu trace ID bắt buộc phải có, dùng `get` để phát hiện cấu hình thiếu sớm. Nếu có thể thiếu trong một số đường gọi nội bộ, dùng `getOrEmpty` hoặc `getOrDefault` và định nghĩa rõ hành vi dự phòng.

Không nên đọc Context lúc xây dựng pipeline bằng một biến toàn cục hoặc lưu giá trị vào static field. Pipeline có thể được tái sử dụng cho nhiều subscription; giá trị cần được đọc trong subscription tương ứng.

## 5. Context đi cùng các Publisher con

Khi một bước tạo Publisher con bằng `flatMap`, Context của subscriber được truyền cho quá trình xử lý bên trong. Vì vậy, Publisher con có thể dùng `deferContextual` để lấy cùng trace ID mà không cần thêm tham số vào mapper.

~~~java
Mono<OrderView> loadOrderView(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            Mono.deferContextual(contextView -> {
                String traceId =
                    contextView.get(TraceContext.TRACE_ID);

                return inventoryClient.check(order.productId())
                    .flatMap(stock ->
                        auditClient.record(
                            traceId,
                            order.id(),
                            stock.available()
                        ).thenReturn(new OrderView(order, stock))
                    );
            })
        );
}
~~~

Mapper của `flatMap` tạo Publisher con theo đơn hàng. `deferContextual` đọc Context tại thời điểm Publisher con được subscribe. Các bước kiểm tra tồn kho và ghi audit có thể sử dụng cùng trace ID.

Có thể đọc Context ở nhiều tầng nếu cần:

~~~java
Mono<Order> findOrder(String orderId) {
    return Mono.deferContextual(contextView -> {
        String traceId = contextView.get(TraceContext.TRACE_ID);
        log.debug("trace={} load order={}", traceId, orderId);
        return orderRepository.findById(orderId);
    });
}
~~~

Tuy nhiên, không nên lặp lại việc đọc và ghi log ở mọi phương thức. Hãy đặt instrumentation tại các ranh giới có giá trị: nhận request, gọi dịch vụ ngoài, thao tác dữ liệu quan trọng và xử lý lỗi. Context giúp truyền metadata; nó không bắt buộc mọi hàm nghiệp vụ phải biết về tracing.

## 6. Context vẫn tồn tại qua publishOn và subscribeOn

`publishOn` chuyển việc xử lý các toán tử phía sau sang scheduler được chỉ định. `subscribeOn` ảnh hưởng nơi quá trình subscribe và yêu cầu nguồn bắt đầu thực thi. Hai toán tử này có thể làm tín hiệu được xử lý trên thread khác, nhưng Reactor Context vẫn gắn với subscriber.

~~~java
Mono<String> result = Mono.deferContextual(contextView -> {
        String traceId = contextView.get(TraceContext.TRACE_ID);
        return Mono.fromCallable(() -> blockingLookup(traceId));
    })
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(value -> "result=" + value);
~~~

Trong ví dụ, `deferContextual` đọc Context khi subscription chạy. Công việc chặn được chuyển sang `boundedElastic`; bước xử lý phía sau `publishOn` chuyển sang `parallel`. Việc đổi thread không làm mất key trong Reactor Context.

Cần phân biệt hai khái niệm:

- **Reactor Context:** metadata gắn với subscription, có thể được đọc bằng `deferContextual`.
- **ThreadLocal:** dữ liệu gắn với thread hiện tại, chỉ có giá trị trên thread đã đặt nó trừ khi có cơ chế truyền riêng.

Nếu code gọi `MDC.get("traceId")` sau một lần `publishOn`, giá trị có thể không tồn tại hoặc có thể là giá trị cũ do thread được tái sử dụng. Context còn nguyên không có nghĩa ThreadLocal cũng tự động được khôi phục.

## 7. Vị trí của contextWrite rất quan trọng

Context được truyền từ subscriber downstream ngược về phía upstream. `contextWrite` tạo Context mà các toán tử phía upstream nhìn thấy. Vì thế, vị trí của nó trong chuỗi operator ảnh hưởng đến nơi có thể đọc key.

Cách thường dùng là đặt `contextWrite` ở cuối pipeline được trả về:

~~~java
Mono<String> pipeline = Mono.deferContextual(contextView ->
        Mono.just(contextView.get(TraceContext.TRACE_ID))
    )
    .map(traceId -> "trace=" + traceId)
    .contextWrite(context ->
        context.put(TraceContext.TRACE_ID, "req-42")
    );
~~~

Ở đây, `deferContextual` nằm upstream của `contextWrite`, nên nhìn thấy `req-42`.

Ngược lại, `contextWrite` đặt trước một toán tử downstream không tự động làm Context xuất hiện trong callback của toán tử đó. Hãy đọc chuỗi operator theo hướng subscription: Context được truyền từ cuối chuỗi về đầu chuỗi, không chảy như một phần tử dữ liệu từ trên xuống.

Có thể hình dung:

~~~text
Subscriber
   |
   v
contextWrite(put traceId)   -- tạo Context cho phía upstream
   |
   v
map(...)
   |
   v
deferContextual(...)        -- đọc traceId
   |
   v
Source
~~~

Khi có nhiều `contextWrite`, thao tác ở gần subscriber hơn có thể bổ sung hoặc ghi đè key mà upstream nhìn thấy. Nếu hai tầng cùng dùng một key, cần thống nhất quy tắc sở hữu để tránh một tầng vô tình thay trace ID của tầng khác.

## 8. Context và ThreadLocal/MDC trong logging

Nhiều thư viện logging lấy metadata từ MDC, vốn dựa trên ThreadLocal. Reactor Context không tự động cập nhật MDC trong mọi cấu hình. Có hai cách tiếp cận thường gặp.

### Cách rõ ràng: đọc Context tại điểm ghi log

Với một callback logging cụ thể, có thể đọc Context từ `Signal` rồi đặt MDC trong phạm vi callback. Phải khôi phục hoặc xóa giá trị sau khi ghi log vì thread có thể được tái sử dụng:

~~~java
import org.slf4j.MDC;
import reactor.core.publisher.Signal;

static void logWithTrace(Signal<?> signal) {
    if (!signal.isOnNext()) {
        return;
    }

    String traceId = signal.getContextView()
        .getOrDefault(TraceContext.TRACE_ID, "trace-missing");

    String previous = MDC.get("traceId");
    MDC.put("traceId", traceId);
    try {
        log.info("Đã nhận kết quả {}", signal.get());
    } finally {
        if (previous == null) {
            MDC.remove("traceId");
        } else {
            MDC.put("traceId", previous);
        }
    }
}
~~~

Có thể gắn helper vào pipeline:

~~~java
Mono<Order> order = orderRepository.findById(orderId)
    .doOnEach(MyLogging::logWithTrace);
~~~

Callback trên chỉ minh họa cách đặt MDC cho chính lần ghi log đó. Không nên đặt MDC rồi để nó tồn tại sau khi callback kết thúc, vì một tác vụ khác có thể dùng lại cùng thread và nhận nhầm trace ID.

### Cách tích hợp: Micrometer Context Propagation

Trong ứng dụng dùng Micrometer Context Propagation, có thể đăng ký accessor để ánh xạ một ThreadLocal như MDC vào cơ chế Context Propagation. Reactor hỗ trợ tích hợp này ở các phiên bản tương thích; ứng dụng có thể bật automatic context propagation bằng `Hooks.enableAutomaticContextPropagation()` khi khởi động.

Cách tích hợp cụ thể phụ thuộc phiên bản Reactor, Micrometer và accessor được đăng ký. Chỉ bật hook sau khi đã cấu hình accessor và kiểm tra phạm vi khôi phục ThreadLocal. Đây là cấu hình cấp ứng dụng, không nên bật hoặc tắt tùy tiện trong từng request.

Dù dùng bridge tự động, Reactor Context vẫn nên là nguồn metadata chính của pipeline. MDC chỉ là bản chiếu tạm thời để thư viện logging đọc được metadata trên thread đang thực thi.

## 9. Truyền metadata tới dịch vụ ngoài

Context không tự động trở thành HTTP header của request gửi đi. Nếu dịch vụ đích cần correlation ID, hãy đọc Context và đưa giá trị vào request tại ranh giới client:

~~~java
Mono<Inventory> checkInventory(String productId) {
    return Mono.deferContextual(contextView -> {
        String traceId =
            contextView.get(TraceContext.TRACE_ID);

        return webClient.get()
            .uri("/inventory/{id}", productId)
            .header("X-Request-Id", traceId)
            .retrieve()
            .bodyToMono(Inventory.class);
    });
}
~~~

Ở đây, `deferContextual` đọc mã theo dõi của subscription hiện tại. WebClient nhận header rõ ràng. Nếu hệ thống sử dụng chuẩn distributed tracing như W3C Trace Context, nên dùng instrumentation tracing tương ứng để truyền `traceparent` và span context thay vì tự tạo một giao thức header riêng.

Không gửi metadata nội bộ tùy tiện ra ngoài. Chỉ truyền các trường đã được thống nhất trong hợp đồng giữa các service, tránh đưa token, thông tin xác thực hoặc dữ liệu nhạy cảm vào header theo dõi.

## 10. Context trong xử lý lỗi và cancellation

Context vẫn hữu ích khi pipeline đi vào nhánh xử lý lỗi. Có thể đọc trace ID trong `onErrorResume` để bổ sung thông tin cho log hoặc tạo lỗi miền có correlation ID:

~~~java
Mono<Order> result = orderRepository.findById(orderId)
    .onErrorResume(error ->
        Mono.deferContextual(contextView -> {
            String traceId =
                contextView.getOrDefault(TraceContext.TRACE_ID, "unknown");

            log.error("trace={} không tải được order={}",
                traceId, orderId, error);

            return Mono.error(
                new OrderLoadException(traceId, orderId, error)
            );
        })
    );
~~~

Context không biến lỗi thành dữ liệu và cũng không thay đổi quy tắc terminal. Nó chỉ cung cấp metadata để ghi nhận hoặc quyết định cách xử lý.

Khi downstream hủy subscription, các nguồn upstream nhận cancellation theo giao thức. Không nên dựa vào một callback `onComplete` để ghi nhận mọi trường hợp kết thúc; cancellation không phải tín hiệu hoàn tất bình thường. Nếu cần quan sát cả complete, error và cancel, có thể dùng `doFinally` để nhận `SignalType`, kết hợp với Context ở một hook thích hợp hoặc ghi nhận trace ID trước khi bắt đầu công việc.

## 11. Kiểm thử Context bằng StepVerifier

`StepVerifier` hỗ trợ xác minh Context của subscription. Có thể kiểm tra key được đặt và đọc trong pipeline:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void contextWriteTruyenTraceIdDenUpstream() {
    Mono<String> traceId = Mono.deferContextual(contextView ->
        Mono.just(contextView.get(TraceContext.TRACE_ID))
    ).contextWrite(context ->
        context.put(TraceContext.TRACE_ID, "req-42")
    );

    StepVerifier.create(traceId)
        .expectAccessibleContext()
        .contains(TraceContext.TRACE_ID, "req-42")
        .then()
        .expectNext("req-42")
        .verifyComplete();
}
~~~

Có thể kiểm tra Context được giữ trong Publisher con và qua scheduler:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@Test
void contextGiuTrongPublisherConQuaScheduler() {
    Mono<String> nested = Mono.just("order-1")
        .publishOn(Schedulers.parallel())
        .flatMap(orderId ->
            Mono.deferContextual(contextView ->
                Mono.just(
                    orderId + ":" +
                    contextView.get(TraceContext.TRACE_ID)
                )
            )
        )
        .contextWrite(context ->
            context.put(TraceContext.TRACE_ID, "req-99")
        );

    StepVerifier.create(nested)
        .expectNext("order-1:req-99")
        .verifyComplete();
}
~~~

Phép thử xác nhận Publisher con đọc được Context sau khi `publishOn` chuyển việc xử lý sang scheduler khác.

Các trường hợp nên kiểm thử thêm:

- Mỗi subscription đồng thời nhận đúng trace ID riêng.
- Thiếu key bắt buộc được phát hiện theo chính sách đã chọn.
- `contextWrite` ghi đè key theo đúng quy tắc sở hữu.
- Publisher con tạo bởi `flatMap` đọc được Context của subscription cha.
- `publishOn` và `subscribeOn` không làm mất Reactor Context.
- Header gửi tới service ngoài chứa đúng mã theo dõi.
- MDC được khôi phục hoặc xóa sau callback để không rò giá trị giữa các tác vụ.
- Nhánh lỗi ghi nhận đúng trace ID và cancellation được quan sát riêng với completion.

## 12. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng ThreadLocal làm nơi lưu duy nhất trace ID | Giá trị có thể mất hoặc lẫn khi đổi thread. | Lưu metadata trong Reactor Context; dùng bridge khi cần MDC. |
| Đặt `contextWrite` sai phía của operator | `deferContextual` không nhìn thấy key mong muốn. | Nhớ Context đi từ downstream ngược lên upstream. |
| Đọc Context khi xây pipeline thay vì khi subscribe | Nhiều subscription có thể dùng chung giá trị cũ. | Dùng `deferContextual` tại thời điểm cần đọc. |
| Lưu toàn bộ request hoặc session vào Context | Giữ object graph lớn và kéo dài vòng đời dữ liệu. | Chỉ lưu ID hoặc metadata nhỏ, bất biến. |
| Nghĩ Context tự tạo HTTP header | Service đích không nhận được correlation ID. | Ánh xạ Context thành header tại ranh giới client. |
| Để MDC tồn tại sau callback | Thread tái sử dụng có thể mang trace ID cũ. | Khôi phục hoặc xóa MDC trong `finally`. |
| Dùng một static trace ID cho mọi request | Các request đồng thời bị gộp log. | Đặt Context riêng cho từng subscription. |

## 13. Quy trình thiết kế propagation

Khi thêm correlation ID vào một ứng dụng Reactor, có thể triển khai theo trình tự:

1. Xác định ranh giới tạo hoặc tiếp nhận trace ID, thường là WebFilter hoặc message consumer.
2. Kiểm tra định dạng và độ dài nếu ID đến từ bên ngoài.
3. Đưa ID vào Reactor Context bằng `contextWrite`.
4. Đọc ID bằng `deferContextual` tại nơi cần gọi service, ghi audit hoặc tạo log.
5. Giữ Context qua các toán tử và scheduler; không dựa vào tên thread.
6. Chỉ chuyển sang MDC hoặc HTTP header tại ranh giới tích hợp cần metadata đó.
7. Kiểm thử subscription đồng thời, Publisher con, lỗi và cancellation.
8. Theo dõi để bảo đảm callback, subscription và cache không giữ request context quá vòng đời cần thiết.

Trong hệ sinh thái Java reactive, Reactor Context cung cấp cách truyền metadata theo subscription qua các luồng con và ranh giới thực thi. Correlation ID được đặt một lần ở ranh giới request, đọc ở các bước cần thiết và giữ độc lập giữa những request chạy đồng thời. Khi phân biệt rõ Context với ThreadLocal, đặt `contextWrite` đúng vị trí và kiểm thử propagation, việc truy vết pipeline Mono và Flux trở nên nhất quán mà không phải truyền tham số kỹ thuật qua mọi tầng nghiệp vụ.

