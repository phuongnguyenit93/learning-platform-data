# Truyền ngữ cảnh và quan sát theo từng phần tử trong luồng

Trong ứng dụng Spring Cloud Stream dùng Reactor, một `Flux<T>` có thể xử lý nhiều message trên những thread khác nhau. Vì vậy, thông tin cần thiết cho một lần xử lý như `correlationId`, `eventId`, tenant, trace hoặc thông tin bảo mật không thể được quản lý tùy tiện bằng biến toàn cục hay `ThreadLocal` rồi giả định rằng nó luôn đi theo message.

Để truyền ngữ cảnh và quan sát đúng từng phần tử, cần phân biệt ba nơi lưu thông tin: **payload và headers của message** mang dữ liệu theo message qua broker; **Reactor Context** mang ngữ cảnh gắn với subscription trong pipeline reactive; **MDC/ThreadLocal** phục vụ log trên thread hiện tại và cần cơ chế context propagation khi pipeline đổi thread. Kết hợp đúng các cơ chế này giúp truy vết một sự kiện xuyên nhiều bước mà không làm lẫn ngữ cảnh giữa các message.

## 1. Ba loại ngữ cảnh trong một luồng reactive

Một message có thể cần nhiều loại thông tin, nhưng không phải thông tin nào cũng thuộc cùng một phạm vi:

| Nơi lưu | Phạm vi | Ví dụ | Có tự đi qua broker không? |
|---|---|---|---|
| Payload | Dữ liệu nghiệp vụ của message | `orderId`, `amount`, `status` | Có, nếu payload được serialize. |
| Message headers | Metadata gắn với một message | `eventId`, `correlationId`, `tenantId`, `contentType`, trace headers | Chỉ khi binder/broker mapping và cấu hình truyền header hỗ trợ. |
| Reactor Context | Ngữ cảnh của một subscription reactive | Trace/observation context, security context, dữ liệu phục vụ các toán tử trong pipeline | Không; cần chủ động chuyển metadata sang message khi qua broker. |
| MDC/ThreadLocal | Ngữ cảnh trên thread hiện tại | `traceId`, `correlationId` cho log | Không; chỉ tồn tại trong tiến trình và thread được gắn giá trị. |

Ví dụ, `eventId` định danh một sự kiện cụ thể nên thường nằm trong payload hoặc header của chính message. `correlationId` liên kết nhiều message cùng một quy trình nghiệp vụ nên thường được truyền qua header. Reactor Context có thể mang trace context hoặc security context trong lúc pipeline xử lý. MDC chỉ là cách đưa một số giá trị vào log của thread hiện tại.

Không nên dùng Reactor Context thay cho payload hoặc message header khi dữ liệu phải đi qua broker. Context của Reactor không được serialize tự động cùng message.

## 2. Reactor Context là gì?

Reactor Context là một cấu trúc key-value gắn với subscriber/subscription. Các toán tử có thể đọc context thông qua `deferContextual`, còn `contextWrite` tạo hoặc cập nhật context cho phần upstream của pipeline.

Một số đặc điểm quan trọng:

- Context gắn với subscription, không gắn cố định với thread.
- Context là bất biến về mặt API; thao tác ghi trả về một Context mới.
- Context được truyền qua các toán tử Reactor trong cùng pipeline/subscription.
- `contextWrite` ảnh hưởng tới các toán tử upstream theo hướng subscription, vì vậy vị trí đặt nó rất quan trọng.
- Context không phải một vùng lưu trữ tự động dành riêng cho từng phần tử của `Flux`.

Ví dụ tối giản:

```java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> greeting = Mono.deferContextual(context -> {
    String requestId = context.getOrDefault("requestId", "unknown");
    return Mono.just("request=" + requestId);
}).contextWrite(Context.of("requestId", "req-1001"));
```

`deferContextual` chỉ đọc context khi có subscription. `contextWrite` cung cấp giá trị `requestId` cho phần upstream của publisher. Kết quả là `request=req-1001`.

Nếu đọc context bên ngoài publisher, trước khi subscription diễn ra, sẽ không có context của subscription để truy cập. Vì vậy, không nên gọi `ContextView` như thể nó là một biến toàn cục.

## 3. Phân biệt context theo subscription và dữ liệu theo từng message

Một điểm dễ nhầm là cho rằng mọi phần tử trong `Flux` có một Reactor Context riêng. Thực tế, Reactor Context gắn với subscription. Nếu một subscription phát ra hàng nghìn phần tử, context của subscription thường được chia sẻ cho các toán tử xử lý những phần tử đó.

Nếu mỗi message có `correlationId` khác nhau, hãy lấy ID từ header/payload của chính message. Có thể tạo một inner publisher cho từng message rồi đặt giá trị vào context của inner subscription:

```java
import org.springframework.messaging.Message;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// messages là Flux<Message<String>> nhận từ binding đầu vào.
Flux<String> descriptions = messages.flatMap(message ->
    {
        String messageCorrelationId = message.getHeaders()
            .get("correlationId", String.class);
        return Mono.deferContextual(context -> {
            String correlationId = context.get("correlationId");
            return Mono.just(correlationId + ": " + message.getPayload());
        }).contextWrite(context -> context.put(
            "correlationId",
            messageCorrelationId == null ? "unassigned" : messageCorrelationId
        ));
    }
);
```

Mỗi message tạo một inner publisher. `contextWrite` ở inner publisher cung cấp correlation ID của message đó cho `deferContextual` tương ứng. Context của inner subscription này không ghi đè context của các message khác trong cùng `flatMap`.

Tuy vậy, context không thay thế header. Khi kết quả cần được gửi sang broker hoặc dịch vụ khác, hãy sao chép hoặc tạo lại metadata cần thiết trong `Message<?>` đầu ra.

## 4. Đưa message metadata vào reactive pipeline

Với Spring Cloud Stream, một function có thể nhận `Flux<Message<T>>` để truy cập payload và headers của từng message. Cách này hữu ích khi xử lý cần `eventId`, `correlationId`, tenant hoặc trace metadata riêng theo message.

Ví dụ function xử lý các sự kiện đơn hàng:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
class OrderContextFunctions {

    @Bean
    Function<Flux<Message<OrderCreated>>, Flux<Message<OrderProcessed>>> processOrders(
            OrderService orderService) {
        return messages -> messages.flatMap(message -> {
            String correlationId = message.getHeaders()
                .get("correlationId", String.class);

            return Mono.deferContextual(context ->
                orderService.process(
                    message.getPayload(), context.get("correlationId"))
                    .map(result -> MessageBuilder.withPayload(result)
                        .copyHeaders(message.getHeaders())
                        .build())
            ).contextWrite(context -> context.put(
                "correlationId",
                correlationId == null ? "unassigned" : correlationId
            ));
        });
    }
}

record OrderCreated(String eventId, String orderId) {}
record OrderProcessed(String eventId, String orderId, String status) {}
```

Ví dụ này minh họa ba việc:

1. Đọc `correlationId` từ header của từng message.
2. Đưa giá trị đó vào Reactor Context của inner publisher để các thành phần reactive downstream có thể đọc.
3. Tạo message đầu ra và sao chép headers để giữ metadata cần thiết.

Trong ứng dụng thực tế, cần xác định rõ header nào được phép truyền tiếp. Không nên sao chép mù quáng mọi header, đặc biệt là credential, header nội bộ của broker hoặc dữ liệu nhạy cảm. Có thể dùng `MessageBuilder` để chỉ chọn các header cần thiết và cập nhật những giá trị đã thay đổi.

## 5. contextWrite và vị trí đặt toán tử

`contextWrite` cung cấp context cho các toán tử upstream. Điều này có nghĩa là vị trí của nó trong chuỗi toán tử ảnh hưởng tới nơi có thể đọc giá trị.

```java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("tenantId"))
).contextWrite(ctx -> ctx.put("tenantId", "tenant-42"));
```

Ở ví dụ này, `deferContextual` nằm upstream so với `contextWrite` nên đọc được `tenantId`. Nếu đặt một toán tử đọc context ở phía downstream của `contextWrite`, toán tử đó không tự động nhìn thấy giá trị được ghi cho upstream.

Trong các pipeline phức tạp, hãy đặt `deferContextual` ở nơi thực sự cần đọc context và đặt `contextWrite` ở đúng subscription scope. Khi dùng `flatMap`, nếu cần context khác nhau cho từng message, đặt `contextWrite` bên trong publisher được tạo cho từng phần tử thay vì ghi một giá trị biến thiên lên context chung của toàn bộ `Flux`.

## 6. Context propagation khi đổi thread

Reactor có thể chuyển xử lý giữa các thread do `publishOn`, `subscribeOn`, scheduler hoặc các thư viện bất đồng bộ. Reactor Context đi theo subscription, nhưng `ThreadLocal` và MDC lại gắn với thread. Vì vậy, giá trị được đặt trong MDC trên thread A không tự xuất hiện trên thread B.

Ví dụ, đoạn code sau không bảo đảm MDC luôn có `correlationId` ở callback sau khi đổi scheduler:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

MDC.put("correlationId", "corr-1001");

return service.loadOrder()
    .publishOn(Schedulers.parallel())
    .doOnNext(order -> log.info("Loaded {}", order.id()));
```

Callback `doOnNext` có thể chạy trên thread khác, nơi MDC không có giá trị đã đặt ở thread ban đầu. Hơn nữa, nếu không xóa MDC đúng cách, thread được tái sử dụng có thể mang dữ liệu của message trước sang message sau.

Để giải quyết, có thể dùng Micrometer Context Propagation và cơ chế tích hợp Reactor. Các `ThreadLocalAccessor` đã đăng ký cho phép chụp/khôi phục giá trị từ context phù hợp. Reactor hỗ trợ chế độ propagation giới hạn và chế độ automatic; chế độ automatic có thể được bật bằng `Hooks.enableAutomaticContextPropagation()` trước khi tạo các subscription cần áp dụng. Với ứng dụng Spring Boot, hãy kiểm tra cấu hình context propagation và phiên bản Reactor/Micrometer đang dùng vì mức tự động tích hợp phụ thuộc phiên bản và dependency.

Không nên bật hook nhiều lần trong từng message hoặc từng function. Đây là cấu hình ở cấp ứng dụng, cần được khởi tạo một lần theo hướng dẫn của phiên bản framework.

## 7. Dùng MDC an toàn khi ghi log

MDC thường được dùng để thêm `correlationId`, `eventId` hoặc `traceId` vào mọi dòng log trên thread hiện tại. Nếu cần ghi log trực tiếp từ callback, hãy bảo đảm giá trị được khôi phục/xóa ngay sau callback.

Ví dụ scope MDC cục bộ:

```java
import org.slf4j.MDC;

void logOrder(OrderCreated event, String correlationId) {
    String previous = MDC.get("correlationId");
    try {
        if (correlationId == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", correlationId);
        }
        log.info("Processing order {}", event.orderId());
    } finally {
        if (previous == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", previous);
        }
    }
}
```

Đoạn code này giới hạn MDC trong một callback đồng bộ. Nếu log được ghi ở nhiều callback trên các scheduler khác nhau, cần context propagation tương ứng hoặc tạo scope MDC cục bộ trong từng callback. Không nên giữ MDC mở xuyên qua một publisher bất đồng bộ rồi đóng trên một thread khác.

Với ứng dụng có Micrometer Tracing, ưu tiên dùng tích hợp tracing/context propagation của Spring Boot và Micrometer để trace ID/span ID được đưa vào log nhất quán. Không tự tạo trace ID mới cho từng toán tử nếu muốn giữ một trace xuyên suốt một lần xử lý.

## 8. Quan sát theo từng phần tử: log, metric và trace

Ba tín hiệu observability có mục đích khác nhau:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Log có cấu trúc | Điều gì đã xảy ra với message cụ thể? | `eventId`, `orderId`, `correlationId`, trạng thái xử lý. |
| Metric | Hệ thống đang hoạt động ra sao theo thời gian? | Số message/giây, tỷ lệ lỗi, thời gian xử lý, backlog. |
| Trace/span | Message đi qua những dịch vụ và bước nào? | Span nhận message, gọi service, ghi database, phát event kế tiếp. |

Mỗi message có thể có `eventId` riêng để tra cứu log. `correlationId` liên kết nhiều message thuộc cùng một quy trình. Trace context như W3C `traceparent` và `tracestate` hoặc định dạng tương ứng giúp liên kết span qua ranh giới dịch vụ, nếu producer, binder và consumer truyền các header đó đúng cách.

Không đưa `eventId`, `orderId`, `correlationId` hoặc tenant ID có số lượng giá trị rất lớn vào metric tag thông thường. Những giá trị có cardinality cao có thể làm tăng số time series và chi phí lưu trữ. Dùng chúng trong log hoặc trace; metric tag nên dùng các giá trị có tập hợp hữu hạn như `operation`, `result`, `message_type` hoặc `error_category`.

## 9. Tạo Observation cho một message

Micrometer Observation cung cấp API thống nhất để đo thời gian và tạo ngữ cảnh cho metric/trace handler đã đăng ký. Với một publisher reactive, vòng đời Observation nên theo vòng đời subscription và kết thúc khi publisher hoàn tất, lỗi hoặc bị hủy.

Ví dụ minh họa tạo Observation cho mỗi message:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import reactor.core.publisher.Mono;

Mono<OrderProcessed> observeOne(
        OrderCreated event,
        OrderService service,
        ObservationRegistry registry) {

    return Mono.defer(() -> {
        Observation observation = Observation
            .createNotStarted("orders.process", registry)
            .lowCardinalityKeyValue("operation", "process-order");

        observation.start();
        return Mono.defer(() -> service.process(event))
            .doOnSuccess(result -> observation.lowCardinalityKeyValue(
                "result", result == null ? "empty" : "success"))
            .doOnError(observation::error)
            .doFinally(signal -> observation.stop());
    });
}
```

`Mono.defer` tạo Observation mới cho mỗi subscription của message. `doOnError` ghi nhận exception và `doFinally` dừng Observation khi hoàn tất, lỗi hoặc cancellation. Trong mã production, cần bảo đảm Observation được mở/đóng đúng một lần và context của nó được tích hợp với Micrometer Context Propagation nếu cần liên kết log/trace qua các scheduler.

Chỉ dùng low-cardinality key cho giá trị có số lượng hữu hạn. Không gắn `eventId` hoặc `orderId` vào low-cardinality metric tag. Nếu cần đưa định danh cụ thể vào trace, dùng cơ chế high-cardinality attribute phù hợp với chính sách telemetry của hệ thống.

## 10. Truyền trace context qua broker

Reactor Context chỉ tồn tại trong subscription hiện tại. Khi function phát một message mới qua output binding, nếu cần giữ liên kết trace giữa dịch vụ phát và dịch vụ nhận, context phải được inject vào headers theo chuẩn propagation mà hệ thống sử dụng.

Với W3C Trace Context, các header thường gặp là:

- `traceparent`: chứa trace ID, parent span ID và flags.
- `tracestate`: mang thông tin vendor-specific tùy chọn.

Các thư viện tracing của Spring/Micrometer có thể inject/extract các header này khi được cấu hình và tích hợp với messaging instrumentation. Tuy nhiên, việc truyền header qua broker còn phụ thuộc binder header mapping, cấu hình native headers và giới hạn header của broker. Cần kiểm thử trên binder thực tế để xác nhận consumer nhận được trace context.

Nếu tự truyền `correlationId` nghiệp vụ, hãy đặt header rõ ràng trong message đầu ra:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderProcessed> output = MessageBuilder
    .withPayload(result)
    .setHeader("correlationId", correlationId)
    .setHeader("eventId", result.eventId())
    .build();
```

Không tự tạo hoặc sửa `traceparent` theo cách tùy ý. Hãy dùng propagator của thư viện tracing để bảo đảm cấu trúc và quan hệ parent/child hợp lệ. Correlation ID nghiệp vụ và trace ID là hai khái niệm khác nhau; một quy trình có thể chứa nhiều trace qua các lần gọi hoặc xử lý bất đồng bộ.

## 11. Context trong các toán tử bất đồng bộ

Các toán tử như `flatMap`, `publishOn` và `subscribeOn` có thể làm luồng xử lý phức tạp hơn. Reactor Context được truyền theo subscription, nhưng dữ liệu riêng của từng phần tử vẫn nên nằm trong message hoặc được đóng trong inner publisher tương ứng.

Ví dụ, với hai message có correlation ID khác nhau:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// service là OrderService đã được inject vào thành phần xử lý.
Message<String> first = MessageBuilder.withPayload("order-1")
    .setHeader("eventId", "evt-1")
    .setHeader("correlationId", "corr-A")
    .build();
Message<String> second = MessageBuilder.withPayload("order-2")
    .setHeader("eventId", "evt-2")
    .setHeader("correlationId", "corr-B")
    .build();

Flux<String> outputs = Flux.just(first, second)
    .flatMap(msg -> Mono.deferContextual(ctx ->
        service.describe(msg.getPayload())
            .map(description -> ctx.get("correlationId") + ":" + description)
    ).contextWrite(ctx -> ctx.put(
        "correlationId",
        msg.getHeaders().get("correlationId", String.class)
    )));
```

Mỗi inner publisher nhận giá trị context từ header của message tương ứng. Kết quả không bị lẫn giữa `corr-A` và `corr-B` dù hai message có thể được xử lý đồng thời.

Khi dùng `flatMap`, cần giới hạn concurrency nếu service phụ thuộc có giới hạn tải. Nếu yêu cầu thứ tự đầu ra, cân nhắc `concatMap` hoặc `flatMapSequential`. Context đúng không tự bảo đảm thứ tự hoàn tất của nghiệp vụ.

## 12. Security context và tenant context

Một pipeline có thể cần thông tin người dùng hoặc tenant. Với Spring Security reactive, `SecurityContext` được lưu trong Reactor Context và truy cập qua các API reactive của Spring Security. Không nên đọc `SecurityContextHolder` theo kiểu imperative trong một callback reactive rồi giả định nó luôn có mặt trên thread hiện tại.

Tenant ID có thể là metadata nghiệp vụ hoặc định tuyến. Nếu tenant được nhận từ message header, phải xác thực tenant đó thuộc phạm vi mà producer được phép gửi. Không tin tưởng header `tenantId` chỉ vì nó đến từ broker; broker có thể nhận message từ nhiều producer hoặc một nguồn không đáng tin cậy.

Không truyền access token, password hoặc credential qua headers của event nếu không thực sự cần thiết. Nếu consumer cần xác định quyền, dùng cơ chế service identity và xác thực giữa dịch vụ; context nghiệp vụ không thay thế kiểm tra quyền truy cập.

## 13. Lỗi thường gặp khi truyền context

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| MDC trống sau `publishOn` | MDC là ThreadLocal và callback chạy trên thread khác. | Dùng Micrometer Context Propagation hoặc scope MDC tại callback. |
| Message sau mang correlation ID của message trước | Không xóa/khôi phục ThreadLocal khi thread được tái sử dụng. | Dùng scope `try/finally`; không lưu trạng thái message trong field singleton. |
| `deferContextual` không tìm thấy key | `contextWrite` đặt sai vị trí hoặc key không được ghi cho subscription đó. | Kiểm tra hướng upstream và đặt contextWrite ở inner publisher phù hợp. |
| Hai phần tử dùng chung một correlation ID | Ghi context chung cho toàn subscription thay vì lấy ID từ từng message. | Đọc metadata từ từng message và tạo inner publisher riêng khi cần. |
| Trace bị đứt qua broker | Header trace không được inject, mapping hoặc extract đúng. | Kiểm tra tracing instrumentation và header mapping của binder. |
| Reactor Context biến mất sau khi gửi message | Context không tự serialize qua broker. | Chuyển metadata cần thiết sang message header/payload. |
| Metric có quá nhiều time series | Đưa event ID/order ID vào metric tag. | Chuyển định danh sang log/trace; giữ metric tag có cardinality thấp. |

## 14. Kiểm thử context và observability

Nên kiểm thử riêng logic context, message header và đường truyền qua binder.

### Kiểm thử Reactor Context

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {

    @Test
    void readsContextFromSubscription() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("correlationId"))
        );

        StepVerifier.create(source.contextWrite(
                Context.of("correlationId", "corr-1001")))
            .expectNext("corr-1001")
            .verifyComplete();
    }
}
```

### Kiểm thử context riêng cho từng phần tử

Tạo hai message có hai correlation ID khác nhau, xử lý đồng thời qua `flatMap`, rồi xác minh kết quả vẫn gắn với đúng ID. Bài test này phát hiện lỗi dùng chung một biến mutable hoặc ghi context ở sai scope.

### Kiểm thử MDC và thread switch

Nếu ứng dụng dùng MDC, hãy kiểm thử callback trước và sau `publishOn`/`subscribeOn`, xác minh trace/correlation metadata được phục hồi và không rò rỉ sang tác vụ tiếp theo trên cùng thread. Với Micrometer Context Propagation, kiểm tra accessor và chế độ propagation đã cấu hình.

### Kiểm thử binder

Dùng Spring Cloud Stream Test Binder để gửi message có headers qua binding và xác minh headers đầu ra. Test Binder không mô phỏng đầy đủ header mapping của broker thật; cần integration test với Kafka, RabbitMQ hoặc Pulsar khi phụ thuộc vào native header, trace propagation hoặc giới hạn metadata của broker.

## 15. Checklist vận hành

Trước khi đưa reactive function vào production, hãy xác minh:

1. `eventId` và `correlationId` có được đặt ở payload/header đúng phạm vi không?
2. Metadata cần qua broker có được serialize/mapping và kiểm thử ở consumer không?
3. Reactor Context có được đặt trong đúng subscription và đúng vị trí của pipeline không?
4. Context theo từng message có được lấy từ message thay vì dùng chung một biến mutable không?
5. MDC có được khôi phục hoặc xóa trong mọi đường kết thúc callback không?
6. Context propagation qua scheduler đã được cấu hình đúng theo phiên bản Reactor/Micrometer/Spring Boot chưa?
7. Trace headers có được inject/extract bằng propagator, thay vì tự chế tạo không?
8. Metric tag có cardinality thấp; định danh message được ghi trong log/trace không?
9. Tenant/security metadata có được xác thực và không mang credential nhạy cảm không?
10. Có test cho context, thread switch, header mapping và binder thật ở các ranh giới quan trọng không?

Truyền context đúng cách giúp mỗi phần tử trong luồng giữ được định danh và dấu vết xử lý của chính nó. Dùng message headers cho metadata cần đi qua broker, Reactor Context cho ngữ cảnh của subscription, và context propagation cho MDC/ThreadLocal khi đổi thread sẽ giúp Spring Cloud Stream có log, metric và trace đáng tin cậy mà không làm lẫn dữ liệu giữa các message.
