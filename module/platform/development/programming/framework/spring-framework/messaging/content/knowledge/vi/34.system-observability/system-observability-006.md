# Truyền ngữ cảnh truy vết qua header và ranh giới bất đồng bộ

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích trace, span, parent span và baggage trong distributed tracing.
- Nhận biết vai trò của các header chuẩn W3C như **traceparent**, **tracestate** và **baggage**.
- Truyền trace context qua Spring Message headers và header native của STOMP.
- Dùng Micrometer Tracing để inject context vào message đi ra và extract context khi nhận message.
- Giữ ngữ cảnh khi công việc đi qua executor, thread pool hoặc Reactor pipeline.
- Kiểm tra trace liên tục qua nhiều service mà không làm rò rỉ context giữa các request.

## 1. Vì sao cần truyền trace context?

Một request trong hệ thống messaging thường đi qua nhiều thành phần: API gateway, service nhận lệnh, message broker, consumer, executor và service phụ thuộc. Mỗi thành phần có thể chạy trên thread hoặc process khác nhau. Nếu chỉ ghi log cục bộ, khi một message bị chậm hoặc thất bại, rất khó nối các sự kiện lại thành một luồng xử lý.

Distributed tracing gán cho một luồng công việc một **trace ID** và chia luồng đó thành các **span**. Mỗi span biểu diễn một thao tác có thời gian bắt đầu/kết thúc, ví dụ nhận request, publish message, xử lý message hoặc gọi database.

- **Trace ID:** định danh toàn bộ hành trình phân tán.
- **Span ID:** định danh một thao tác cụ thể trong trace.
- **Parent span ID:** liên kết span hiện tại với thao tác đã tạo ra nó.
- **Baggage:** các giá trị ngữ cảnh nhỏ cần truyền giữa các service, ví dụ tenant tier hoặc locale. Baggage không thay thế trace ID và phải được kiểm soát chặt vì có thể đi qua nhiều ranh giới tin cậy.

Khi service A publish message cho service B, B cần biết message thuộc trace nào. Header truyền context giúp B tạo span con của thao tác publish, thay vì tạo một trace hoàn toàn mới. Khi B phát message tiếp cho C, C tiếp tục hành trình đó.

Không có trace context, mỗi service có thể vẫn ghi log và metric riêng, nhưng hệ thống khó trả lời câu hỏi: “Request ban đầu đã đi qua những service nào, và bị chậm ở đâu?”

## 2. W3C Trace Context: traceparent, tracestate và baggage

W3C Trace Context định nghĩa định dạng trao đổi trace context phổ biến giữa các thành phần.

Header **traceparent** phiên bản 00 có cấu trúc:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các phần theo thứ tự:

| Thành phần | Độ dài ở version 00 | Ý nghĩa |
| --- | ---: | --- |
| version | 2 ký tự hex | Phiên bản định dạng |
| trace-id | 32 ký tự hex | ID của trace |
| parent-id | 16 ký tự hex | Span ID ở đầu gửi |
| trace-flags | 2 ký tự hex | Cờ điều khiển, ví dụ sampled |

Các ID toàn số 0 không hợp lệ. Header phải được parser theo đặc tả; không tự tách chuỗi bằng vị trí cố định rồi tin mọi giá trị đầu vào.

**tracestate** mang trạng thái bổ sung theo vendor. Nó có thể được cập nhật khi context đi qua hệ thống tracing khác nhau. Ứng dụng thông thường nên để propagator của tracing library xử lý thay vì tự sửa chuỗi.

**baggage** truyền các cặp key/value ở cấp trace. Chỉ đưa vào các giá trị thực sự cần cho xử lý xuyên service. Không truyền access token, mật khẩu, dữ liệu cá nhân, payload nghiệp vụ lớn hoặc thông tin có thể làm tăng cardinality của metric. Nếu nhận baggage từ bên ngoài, cần allowlist key, kiểm tra độ dài và áp dụng chính sách tin cậy.

Một điểm quan trọng: khi B nhận traceparent từ A, B tạo span mới với **cùng trace ID nhưng span ID mới**. Khi B gửi tiếp sang C, parent ID trong header đi ra phải tham chiếu span của B. Không sao chép nguyên header đầu vào cho mọi message đi tiếp, vì như vậy quan hệ cha-con sẽ sai.

## 3. Spring Message headers và header trên transport

Trong Spring Messaging, một message có hai phần chính:

- **Payload:** dữ liệu nghiệp vụ.
- **MessageHeaders:** metadata đi cùng message trong nội bộ Spring, chẳng hạn ID, timestamp, content type, correlation ID hoặc các custom header.

Có thể tạo message với header bằng MessageBuilder:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("order-created")
        .setHeader("traceparent", traceparent)
        .setHeader("tracestate", tracestate)
        .build();
~~~

MessageHeaders là metadata của abstraction Spring. Việc một custom header có được gửi qua mạng hay không phụ thuộc adapter và transport. Không nên giả định rằng mọi header nội bộ đều tự động trở thành header HTTP, STOMP native header hoặc RSocket metadata.

Cần phân biệt:

- **Spring Message header:** metadata bên trong pipeline Spring Messaging.
- **Transport header/metadata:** trường thực sự được mã hóa và gửi qua network.
- **Tracing context:** nội dung chuẩn mà propagator inject/extract vào carrier.

Khi đi qua broker hoặc protocol adapter, phải xác định rõ mapping hai chiều giữa MessageHeaders và header/metadata trên wire. Nếu adapter loại bỏ custom header, trace sẽ bị đứt dù message vẫn đến được consumer.

Không nên tự tạo các tên header gần giống chuẩn như **x-trace-id** nếu hệ thống đã dùng W3C Trace Context. Hãy thống nhất tên chuẩn và để Micrometer Tracing chọn định dạng propagation tương ứng với bridge/configuration.

## 4. Inject và extract bằng Micrometer Tracing

Spring Boot 3 thường tích hợp Micrometer Observation và Micrometer Tracing. Tracing bridge (ví dụ Brave hoặc OpenTelemetry) cung cấp implementation để tạo span và propagator. Với transport đã có instrumentation tự động, hãy ưu tiên instrumentation đó. Chỉ tự inject/extract ở ranh giới messaging chưa được instrument để tránh tạo span trùng hoặc liên kết parent sai.

Micrometer Tracing cung cấp:

- **Tracer:** tạo span, truy cập span hiện tại và mở scope.
- **Span:** đại diện cho một thao tác trong trace.
- **Propagator:** inject context vào carrier và extract context từ carrier.
- **TraceContext:** thông tin context của span, gồm trace ID và span ID.

### Gửi message: tạo producer span và inject context

Ví dụ sau tạo span cho thao tác publish, inject các trường propagation vào một Map, sau đó sao chép chúng vào Spring Message headers:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

class TracedMessagePublisher {

    private final Tracer tracer;
    private final Propagator propagator;
    private final MessageChannel output;

    TracedMessagePublisher(
            Tracer tracer,
            Propagator propagator,
            MessageChannel output) {
        this.tracer = tracer;
        this.propagator = propagator;
        this.output = output;
    }

    void publish(String payload) {
        Span span = tracer.nextSpan()
                .name("orders.publish")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            Map<String, String> carrier = new LinkedHashMap<>();

            propagator.inject(
                    span.context(),
                    carrier,
                    (headers, key, value) -> headers.put(key, value));

            Message<String> message = MessageBuilder
                    .withPayload(payload)
                    .copyHeaders(carrier)
                    .build();

            output.send(message);
        } finally {
            span.end();
        }
    }
}
~~~

Các điểm cần chú ý:

1. **nextSpan()** tạo span mới; nếu có span hiện tại, span mới được liên kết làm con của span đó.
2. **withSpan(span)** đặt span vào scope hiện tại trong lúc publish để log và instrumentation đồng bộ có thể nhìn thấy nó.
3. **Propagator.inject(...)** ghi các header propagation phù hợp với tracing bridge. Không hardcode trace ID hoặc span ID.
4. **copyHeaders(...)** đưa các trường đã inject vào Spring Message. Adapter vẫn phải chuyển các trường này ra transport header/metadata.
5. **finally** kết thúc span kể cả khi gửi message thất bại.

Đoạn code là mẫu tích hợp ở ranh giới ứng dụng; MessageChannel, bean Tracer và Propagator phải được cấu hình trong Spring context. Nếu transport adapter đã tạo producer span và inject context tự động, không bọc thêm một producer span thủ công cho cùng thao tác.

Với send bất đồng bộ, thời điểm kết thúc producer span cần phản ánh hợp đồng của thao tác. Nếu send trả về ngay sau khi enqueue, span chỉ đo thời gian enqueue. Nếu cần đo thời gian broker xác nhận, hãy kết thúc span trong callback/acknowledgement tương ứng.

### Nhận message: extract context và tạo consumer span

Ở phía consumer, lấy carrier từ MessageHeaders và yêu cầu propagator extract parent context. Sau đó tạo span mới cho thao tác xử lý:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import org.springframework.messaging.Message;

class TracedMessageHandler {

    private final Tracer tracer;
    private final Propagator propagator;
    private final OrderService orderService;

    TracedMessageHandler(
            Tracer tracer,
            Propagator propagator,
            OrderService orderService) {
        this.tracer = tracer;
        this.propagator = propagator;
        this.orderService = orderService;
    }

    void handle(Message<String> message) {
        Span.Builder parent = propagator.extract(
                message.getHeaders(),
                (headers, key) -> {
                    Object value = headers.get(key);
                    return value == null ? null : value.toString();
                });

        Span span = tracer.nextSpan(parent)
                .name("orders.process")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            orderService.process(message.getPayload());
        } finally {
            span.end();
        }
    }
}
~~~

Nếu header hợp lệ, span consumer là con của context được truyền đến. Nếu không có context, propagator có thể trả về builder không có parent và tracing library tạo một trace mới. Không để header lỗi làm hỏng nghiệp vụ chỉ vì tracing; cần có chính sách xử lý malformed context và log có kiểm soát.

Không đọc trace ID từ payload nghiệp vụ nếu header propagation đã là nguồn context chuẩn. Payload nên giữ ý nghĩa domain; metadata truy vết thuộc header hoặc carrier riêng.

## 5. Truyền trace header qua STOMP/WebSocket

STOMP có native headers được truyền trong frame. Với Spring, có thể dùng StompHeaderAccessor để đặt và đọc các header này.

Ví dụ tạo một message STOMP SEND có trace context:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;

StompHeaderAccessor accessor =
        StompHeaderAccessor.create(StompCommand.SEND);

accessor.setDestination("/app/orders");
accessor.setNativeHeader("traceparent", traceparent);
accessor.setNativeHeader("tracestate", tracestate);
accessor.setLeaveMutable(true);

Message<byte[]> outbound =
        MessageBuilder.createMessage(payloadBytes, accessor.getMessageHeaders());
~~~

Ở phía nhận, có thể đọc native header từ message STOMP:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

String traceparent = accessor.getFirstNativeHeader("traceparent");
String tracestate = accessor.getFirstNativeHeader("tracestate");
~~~

Nếu dùng SimpMessagingTemplate, có thể tạo SimpMessageHeaderAccessor, gọi setNativeHeader và truyền MessageHeaders vào convertAndSend. Hãy xác nhận header thực sự xuất hiện trong frame trên wire bằng integration test; header nội bộ được copy không có nghĩa mọi adapter đều gửi nó.

Không đưa trace header vào destination hoặc sửa payload chỉ để mang context. Header native được thiết kế cho metadata giao thức và giúp giữ payload domain độc lập.

## 6. Giữ context qua ranh giới bất đồng bộ

Một lỗi phổ biến là context có ở thread nhận message nhưng biến mất khi xử lý chuyển sang thread khác. Nhiều tracing implementation lưu span hiện tại trong ThreadLocal. ThreadLocal chỉ gắn với thread đang chạy; khi task chuyển sang executor hoặc scheduler khác, thread mới không tự nhận context cũ.

Các ranh giới thường làm mất context:

- @Async hoặc ThreadPoolTaskExecutor.
- ExecutorService tự tạo.
- Reactor publishOn/subscribeOn hoặc callback chạy trên scheduler khác.
- Callback của client HTTP/database.
- Message được đưa vào queue nội bộ rồi xử lý ở worker khác.

Không truyền một đối tượng Span bằng biến static hoặc giữ span cũ trong singleton để khắc phục. Cách đó có thể khiến context của request này rò sang request khác.

### Dùng ContextPropagatingTaskDecorator cho executor

Spring Framework 6.1 cung cấp ContextPropagatingTaskDecorator để capture và restore context được đăng ký qua Micrometer Context Propagation.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class MessagingExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor messagingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);

        TaskDecorator decorator =
                new ContextPropagatingTaskDecorator();
        executor.setTaskDecorator(decorator);

        return executor;
    }
}
~~~

TaskDecorator capture context ở thời điểm task được submit và khôi phục các context accessor đã đăng ký khi task chạy. Nó giúp truyền tracing/logging context qua executor, nhưng không tự truyền mọi biến tùy ý. Đảm bảo Micrometer Context Propagation và tracing bridge được cấu hình đúng trong ứng dụng.

Không nên dùng một executor queue không giới hạn chỉ để tránh mất context. Queue capacity, rejection policy và shutdown behavior vẫn phải được thiết kế theo tải thực tế.

### Reactor Context

Reactor chạy pipeline trên nhiều thread nhưng cung cấp Reactor Context để giữ dữ liệu gắn với subscription. Context này không phải ThreadLocal. Khi dùng Micrometer Context Propagation, tracing context có thể được bridge giữa Reactor Context và ThreadLocal theo cấu hình của ứng dụng.

Ví dụ minh họa dữ liệu tương quan riêng của ứng dụng trong Reactor Context:

~~~java
import reactor.core.publisher.Mono;

Mono<String> process(String payload, String correlationId) {
    return Mono.deferContextual(context -> {
        String id = context.get("correlationId");
        return Mono.just("processed:" + id + ":" + payload);
    }).contextWrite(context ->
            context.put("correlationId", correlationId));
}
~~~

Đoạn code trên minh họa Reactor Context cho correlation ID, không tự triển khai distributed tracing. Với trace/span context, dùng Micrometer Tracing và cơ chế context propagation được hỗ trợ; không tự lưu mỗi trace ID trong Reactor Context rồi giả định đã bảo toàn đầy đủ parent span, sampling và baggage.

Nếu bật automatic context propagation của Reactor, hãy bật ở cấu hình khởi động và kiểm tra đúng phiên bản Reactor/Spring đang dùng. Tránh bật/tắt hook tùy tiện giữa các test vì hook có phạm vi toàn cục và có thể ảnh hưởng các test chạy chung JVM.

## 7. Dùng Observation để quan sát xử lý message

Micrometer Observation cung cấp API chung để đo thời gian và gắn ngữ cảnh cho một thao tác. Khi ứng dụng có tracing handler/bridge, observation có thể được xuất thành span; khi có meter handler, nó cũng có thể tạo metric.

Ví dụ instrument một handler:

~~~java
import org.springframework.messaging.Message;
import org.springframework.observation.Observation;
import org.springframework.observation.ObservationRegistry;

class ObservedOrderHandler {

    private final ObservationRegistry observationRegistry;
    private final OrderService orderService;

    ObservedOrderHandler(
            ObservationRegistry observationRegistry,
            OrderService orderService) {
        this.observationRegistry = observationRegistry;
        this.orderService = orderService;
    }

    void handle(Message<String> message) {
        Observation.createNotStarted(
                        "messaging.process",
                        observationRegistry)
                .lowCardinalityKeyValue("messaging.system", "spring-messaging")
                .lowCardinalityKeyValue("messaging.operation", "process")
                .observe(() -> orderService.process(message.getPayload()));
    }
}
~~~

Tên observation nên ổn định. Low-cardinality key/value phù hợp cho metric dimension như messaging system, operation hoặc destination template. Không đưa order ID, user ID, raw message ID hoặc trace ID vào low-cardinality metric tag vì sẽ tạo cardinality rất lớn.

Nếu Spring adapter hoặc broker instrumentation đã tạo observation/span cho thao tác này, hãy bổ sung convention/tag vào instrumentation hiện có thay vì tạo observation thứ hai bao quanh cùng một công việc.

## 8. Correlation ID, trace ID và message ID

Ba loại ID này có mục đích khác nhau:

| ID | Mục đích | Có thay đổi giữa các message trong cùng trace? |
| --- | --- | --- |
| Trace ID | Nối các span thuộc một hành trình phân tán | Thường giữ nguyên trong trace |
| Span ID | Định danh một thao tác cụ thể | Mỗi span có ID riêng |
| Correlation ID | Nối các message thuộc cùng một workflow nghiệp vụ | Theo hợp đồng ứng dụng |
| Message ID | Định danh một message cụ thể để dedup/audit | Mỗi message có ID riêng |

Một workflow có thể kéo dài nhiều phút hoặc nhiều giờ, vượt quá vòng đời của một trace. Correlation ID có thể giữ ổn định qua workflow đó, trong khi trace mới được tạo cho mỗi lần xử lý hoặc mỗi lần resume. Không dùng trace ID thay thế message ID hoặc idempotency key.

Khi ghi log, có thể đưa trace ID và span ID vào MDC để log backend hiển thị chúng. Context phải được khôi phục/xóa đúng lúc để log của task tiếp theo trên cùng thread không mang nhầm ID. Hãy dùng cơ chế MDC integration của tracing library thay vì tự set ThreadLocal mà không cleanup.

## 9. Bảo mật và giới hạn dữ liệu trong header

Trace context đến từ request hoặc message bên ngoài có thể bị giả mạo. Nó hữu ích cho liên kết quan sát, nhưng không phải bằng chứng xác thực.

- Không dùng trace ID, span ID hoặc baggage để quyết định quyền truy cập.
- Không đưa token, session cookie, mật khẩu hoặc payload nhạy cảm vào baggage.
- Chỉ forward các header được allowlist qua ranh giới tin cậy.
- Giới hạn tổng kích thước header và số lượng baggage item.
- Không tin tenant ID trong baggage nếu tenant đã có nguồn xác thực riêng.
- Tránh ghi nguyên payload hoặc toàn bộ baggage vào log.
- Với message đi qua broker dùng chung, xác định rõ header nào được giữ, loại bỏ hoặc ghi đè.

Nếu traceparent không hợp lệ, tracing library nên xử lý theo chuẩn parser của nó. Ứng dụng không nên tự tin dùng các giá trị không hợp lệ làm parent. Tùy chính sách, có thể bắt đầu trace mới và ghi metric về header lỗi mà không log toàn bộ giá trị đầu vào.

## 10. Kiểm thử propagation qua các ranh giới

Một bộ test cần kiểm tra cả nội dung header và quan hệ span, không chỉ kiểm tra rằng log có chứa một chuỗi ID.

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Header hợp lệ | Gửi traceparent hợp lệ vào consumer | Span xử lý có cùng trace ID và parent đúng |
| Publish tiếp | Consumer phát message mới | Header đi ra tham chiếu span producer mới |
| Thiếu header | Gửi message không có trace context | Tạo trace mới hoặc hành vi theo policy |
| Header sai | Gửi traceparent sai định dạng | Không dùng context lỗi làm parent |
| Async executor | Submit task trong scope có span | Task nhìn thấy đúng context, task kế tiếp không bị rò |
| Reactor scheduler | Chuyển scheduler trong pipeline | Context vẫn được bridge theo cấu hình |
| Hai message đồng thời | Xử lý hai trace trên cùng thread pool | Không trộn trace ID/span ID giữa hai message |
| STOMP | Gửi/nhận native header | Header được giữ đúng qua frame trên wire |
| Broker/adapter | Publish và consume qua transport thật | Context không bị adapter loại bỏ |
| Baggage | Gửi key nằm trong allowlist và key không cho phép | Chỉ key được phép được forward |

Khi kiểm tra tracing bridge, dùng in-memory span exporter hoặc test tracer phù hợp với bridge đang dùng. Assert:

- Trace ID của span downstream khớp trace đầu vào.
- Span ID downstream khác span ID upstream.
- Parent span ID trỏ về span upstream tương ứng.
- Span có thời lượng và trạng thái error đúng khi handler thất bại.
- Context được đóng sau xử lý; message kế tiếp không kế thừa span cũ.

Với async executor, tạo ít nhất hai task có trace context khác nhau và cố tình cho chúng chạy trên cùng worker thread theo thứ tự. Xác nhận task thứ hai không thấy trace của task thứ nhất. Đây là cách phát hiện context leak mà test chỉ chạy một task thường bỏ sót.

Với transport thật, kiểm tra header ở cả hai đầu. Unit test chỉ xác nhận MessageBuilder giữ header trong bộ nhớ; nó không chứng minh STOMP, RSocket hoặc broker adapter đã serialize và truyền header đó.

## 11. Lỗi thường gặp

- **Chỉ truyền trace ID:** downstream không biết parent span nên cây trace bị đứt hoặc liên kết không chính xác.
- **Copy nguyên traceparent đầu vào cho message tiếp theo:** parent ID không phản ánh span hiện tại.
- **Cho rằng MessageHeaders luôn đi qua mạng:** adapter có thể chỉ chuyển một tập header được hỗ trợ.
- **Dùng ThreadLocal qua @Async mà không decorator:** worker thread không có context hoặc giữ nhầm context cũ.
- **Tự tạo span khi instrumentation đã tự tạo:** trace xuất hiện hai span cho cùng thao tác.
- **Đưa ID có cardinality cao vào metric tag:** metric backend tăng số time series nhanh.
- **Đưa thông tin nhạy cảm vào baggage:** dữ liệu có thể bị chuyển qua nhiều service và xuất hiện trong telemetry.
- **Dùng trace ID làm idempotency key:** trace có thể đổi khi retry và không đảm bảo duy nhất cho một thao tác nghiệp vụ.
- **Chỉ kiểm tra log:** log có ID không chứng minh quan hệ parent-child và thời gian span chính xác.

## 12. Checklist triển khai

- [ ] Chọn W3C Trace Context hoặc propagation format thống nhất cho toàn hệ thống.
- [ ] Có producer span và consumer span tại đúng ranh giới messaging.
- [ ] Dùng Micrometer Propagator để inject/extract, không tự ghép traceparent.
- [ ] Xác nhận custom MessageHeaders được map sang transport header/metadata.
- [ ] Context được giữ qua executor và Reactor bằng cơ chế được hỗ trợ.
- [ ] Scope và span được đóng ngay cả khi xử lý lỗi hoặc bị cancel.
- [ ] Không tạo span trùng với instrumentation tự động.
- [ ] Correlation ID, message ID và idempotency key được dùng đúng mục đích.
- [ ] Baggage có allowlist, giới hạn kích thước và không chứa secret.
- [ ] Có test header hợp lệ, thiếu/sai header, async, concurrency và transport thật.
- [ ] Log và metric không chứa raw payload hoặc high-cardinality tags không cần thiết.

## Tài liệu tham khảo

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)
- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework Reference — WebSocket STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework API — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
