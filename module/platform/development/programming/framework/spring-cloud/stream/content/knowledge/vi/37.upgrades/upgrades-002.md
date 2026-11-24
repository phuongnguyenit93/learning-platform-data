# Nhận diện mã cũ dùng @EnableBinding, @StreamListener, Source, Processor và Sink

Trong những ứng dụng Spring Cloud Stream được viết theo thế hệ đầu, lập trình viên thường định nghĩa **message channel** bằng `Source`, `Sink`, `Processor` hoặc interface tự tạo, kích hoạt chúng bằng `@EnableBinding`, rồi xử lý sự kiện trong phương thức gắn `@StreamListener`. Khi đọc lại một dịch vụ như vậy để nâng cấp Spring Boot/Spring Cloud Stream, cần nhận diện đúng **mô hình lập trình cũ dựa trên annotation và channel** trước khi thay dependency hoặc sửa configuration. Nếu chỉ cập nhật phiên bản, các import có thể không còn tồn tại và các binding `input`/`output` cũ không tự động trở thành binding `functionName-in-0`/`functionName-out-0`.

Bài học thuộc chương **Nâng cấp** của module `SPRING_CLOUD_STREAM` — nền tảng viết ứng dụng sự kiện bằng `Supplier`, `Function`, `Consumer` với binder Kafka, RabbitMQ hoặc Pulsar. Mục tiêu trước hết là **phát hiện và hiểu dấu vết mã cũ**, lập bản đồ đường đi của message, nhận ra cấu hình và bài kiểm thử phụ thuộc mô hình cũ, sau đó biết hướng chuyển phù hợp sang mô hình hàm hiện đại mà không làm thay đổi âm thầm tên destination, consumer group, partition, retry/DLQ hoặc semantics giao nhận.

## 1. Hai thế hệ lập trình trong Spring Cloud Stream

| Tiêu chí | Mô hình channel/annotation cũ | Mô hình hàm được khuyến nghị |
|---|---|---|
| Định nghĩa điểm vào/ra | `@Input`, `@Output`, `Source`, `Sink`, `Processor` | Tham số và kiểu trả về của `Supplier`/`Function`/`Consumer` |
| Kích hoạt binding | `@EnableBinding(...)` | Auto-configuration phát hiện function bean; `spring.cloud.function.definition` khi cần |
| Xử lý message | `@StreamListener` | `@Bean` trả về `Consumer`, `Function` hoặc `Supplier` |
| Gửi output từ listener | `@SendTo` hoặc `MessageChannel.send(...)` | Giá trị trả về của `Function`/`Supplier`; hoặc `StreamBridge` khi gửi chủ động |
| Tên binding thông dụng | `input`, `output`, tên trong `@Input/@Output` | `beanName-in-0`, `beanName-out-0` |
| Gắn destination | `spring.cloud.stream.bindings.input.destination` | `spring.cloud.stream.bindings.processOrder-in-0.destination` |
| Test điển hình trong dự án cũ | `TestSupportBinder`, `MessageCollector` | `spring-cloud-stream-test-binder`, `InputDestination`, `OutputDestination` |

Mô hình channel/annotation từng là API chính ở các dòng Spring Cloud Stream cũ. Các API này bị deprecated trong giai đoạn chuyển sang functional model và không còn được hỗ trợ như mô hình ứng dụng trong các dòng Spring Cloud Stream hiện đại, đặc biệt từ dòng 4.x. Hãy xác nhận phiên bản bằng build/dependency management của **dự án khi thực hiện migration thực tế**; riêng bài học này không yêu cầu mở bất kỳ file build nào. Không kết luận chỉ dựa vào Spring Boot version rằng tất cả API cũ vẫn tồn tại.

## 2. Sơ đồ nhận diện luồng message cũ

```text
                  @EnableBinding(Processor.class)
                              |
                 Processor.INPUT / OUTPUT
                              |
Kafka / RabbitMQ / Pulsar --> input MessageChannel
                              |
                              v
                  @StreamListener(Processor.INPUT)
                    handle(...) + @SendTo(...)
                              |
                              v
                       output MessageChannel
                              |
                              v
                      Kafka / RabbitMQ / Pulsar
```

Trong kiến trúc mới, không cần interface channel được tạo riêng cho một luồng xử lý thông thường:

```text
Broker --> functionName-in-0 --> @Bean Function<T,R> --> functionName-out-0 --> Broker
Broker --> consumerName-in-0 --> @Bean Consumer<T>
            @Bean Supplier<T> --> supplierName-out-0 --> Broker
```

Khi rà soát repository cũ, hãy vẽ sơ đồ từng luồng: **ai phát message**, **đầu vào nào nhận nó**, **hàm nào xử lý**, **đầu ra nào được gửi**, **destination và group thực tế là gì**. Sơ đồ này quan trọng hơn việc đổi tên annotation vì cấu hình binder và yêu cầu giao nhận gắn với đường đi của message.

## 3. Tín hiệu nhận diện nhanh trong source code

Các dấu hiệu mạnh của mô hình cũ:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.annotation.Input;
import org.springframework.cloud.stream.annotation.Output;
import org.springframework.cloud.stream.messaging.Source;
import org.springframework.cloud.stream.messaging.Sink;
import org.springframework.cloud.stream.messaging.Processor;
```

Đây là **mẫu import để nhận diện trong mã lịch sử**, không phải hướng dẫn copy vào dự án mới. Có dự án dùng static import hoặc tên class đầy đủ, vì vậy tìm mỗi chuỗi `@EnableBinding` vẫn có thể bỏ sót một phần.

| Dấu vết | Khả năng cao đang làm gì? | Cần tìm kèm |
|---|---|---|
| `@EnableBinding(Source.class)` | Khai báo output channel mặc định | Ai gọi `source.output().send(...)`? |
| `@EnableBinding(Sink.class)` | Khai báo input channel mặc định | Phương thức `@StreamListener(Sink.INPUT)`? |
| `@EnableBinding(Processor.class)` | Khai báo cả input và output | `@StreamListener`, `@SendTo`, converter |
| `@EnableBinding(OrderChannels.class)` | Interface binding tự tạo | Tên trong `@Input/@Output` và config |
| `@StreamListener("input")` | Xử lý message từ channel tên `input` | Ack, error handling, @SendTo |
| `@SendTo("output")` | Định tuyến giá trị trả về vào output channel | Định dạng/kiểu trả về và nơi nhận |
| `Source.OUTPUT`, `Sink.INPUT` | Tham chiếu constant của channel cũ | Binding `output`/`input` trong YAML |
| `SubscribableChannel`, `MessageChannel` | Tầng Spring Messaging channel | Có liên kết `@Input/@Output` không? |

Không phải cứ có `MessageChannel` hoặc `@Bean Consumer<T>` là mã cũ: Spring Integration và Spring Messaging vẫn được sử dụng trong nhiều ngữ cảnh hiện đại. Cần nhìn **cách channel được đăng ký với Spring Cloud Stream** trước khi phân loại.

## 4. `@EnableBinding`: điểm khởi đầu quan trọng nhất

Đây là annotation cũ yêu cầu framework tạo binding và infrastructure dựa trên các interface channel được khai báo. Ví dụ:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Sink;

@EnableBinding(Sink.class)
public class LegacyOrderApplication {
}
```

Framework đời cũ hiểu rằng ứng dụng cần input channel do `Sink` mô tả. `@EnableBinding` không phải một phép kết nối trực tiếp với mọi topic; destination cụ thể do thuộc tính binder và binding định nghĩa. Trong một số mã, annotation nằm trên `@SpringBootApplication` hoặc class `@Configuration`, không nằm cùng class với listener.

Các biến thể cần nhận diện:

```java
@EnableBinding(Source.class)
// Hoặc:
@EnableBinding(Processor.class)
// Hoặc interface tùy chỉnh:
@EnableBinding({OrderChannels.class, AuditChannels.class})
```

`@EnableBinding` **không tương đương** với `@EnableTestBinder`. `@EnableTestBinder` thuộc hạ tầng **kiểm thử hiện đại** của `spring-cloud-stream-test-binder`; không phải cách khôi phục API channel cũ cho ứng dụng production.

## 5. `Source`: dấu hiệu producer kiểu cũ

`Source` là interface có **một output channel** mặc định tên `output`. Trong các phiên bản cũ, một service phát message bằng cách inject `Source`, gọi phương thức `output()` rồi `send()`:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Source;
import org.springframework.messaging.support.MessageBuilder;

@EnableBinding(Source.class)
class LegacyOrderPublisher {

    private final Source source;

    LegacyOrderPublisher(Source source) {
        this.source = source;
    }

    boolean publishOrder(String orderId) {
        return source.output().send(
            MessageBuilder.withPayload(orderId).build()
        );
    }
}
```

Các điểm cần ghi lại khi kiểm kê:

1. `Source.OUTPUT`/`output()` ánh xạ đến **binding `output`**, không phải tên topic bắt buộc là `output`.
2. Message được gửi **chủ động khi method được gọi** (ví dụ từ REST handler), không nhất thiết theo lịch.
3. `send` trả về trạng thái gửi đến message channel trong mô hình đó; không tự đồng nghĩa broker đã lưu bền vững hoặc consumer đã xử lý.
4. Một service có thể gọi `source.output().send()` tại nhiều điểm khác nhau; cần tìm **mọi call site** trước khi thay bằng `Supplier` hoặc `StreamBridge`.

Ví dụ cấu hình cũ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        output:
          destination: orders.created
```

Nếu viết lại dưới mô hình hàm mà không giữ destination này, message có thể bị gửi đến topic khác mang tên binding mới. Với publisher phát theo request/command, hướng tiếp cận thường là **`StreamBridge`**; một `Supplier` kiểu polling chỉ phù hợp khi bản chất luồng là chủ động cung cấp giá trị theo chu kỳ.

## 6. `Sink`: dấu hiệu consumer kiểu cũ

`Sink` định nghĩa **một input channel** mặc định tên `input`. Dấu hiệu phổ biến là `@EnableBinding(Sink.class)` cùng `@StreamListener(Sink.INPUT)`:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Sink;

@EnableBinding(Sink.class)
class LegacyOrderConsumer {

    @StreamListener(Sink.INPUT)
    public void consume(String payload) {
        System.out.println("Received: " + payload);
    }
}
```

`Sink.INPUT` có giá trị logic `input`. Nếu `consume` không trả về dữ liệu, đây thường là vai trò tương đương một `Consumer<T>` trong functional model. Nhưng cần xem method có cập nhật database, gọi HTTP, publish thêm event, xử lý exception hay tự ack không: các tác động này quyết định cách viết lại, không chỉ kiểu trả về `void`.

Ví dụ YAML cũ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.created
          group: order-projection
          content-type: application/json
```

`input` là **tên binding**; `orders.created` là **destination**; `order-projection` là **consumer group**. Không đổi group trong migration nếu muốn consumer mới tiếp tục xử lý theo cùng định danh logic và chính sách offset/subscription đã dự kiến. Các binder xử lý group và offset khác nhau, nên việc giữ group vẫn cần thử nghiệm với middleware thực tế.

## 7. `Processor`: có một input và một output

`Processor` kết hợp vai trò của `Sink` và `Source`, cung cấp `Processor.INPUT` (giá trị `input`) và `Processor.OUTPUT` (giá trị `output`). Đây là mẫu phổ biến nhất khi ứng dụng **nhận, biến đổi và phát tiếp** sự kiện:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Processor;
import org.springframework.messaging.handler.annotation.SendTo;

@EnableBinding(Processor.class)
class LegacyOrderProcessor {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String normalize(String orderId) {
        return orderId.trim().toUpperCase();
    }
}
```

Ở code cũ, `@StreamListener(Processor.INPUT)` chỉ ra input channel, còn `@SendTo(Processor.OUTPUT)` đưa **giá trị trả về** vào output channel. Nếu bỏ `@SendTo` khi refactor nhưng không có đường publish khác, output có thể biến mất. Nếu sử dụng `Message<T>`, cần giữ những header nghiệp vụ quan trọng khi biến đổi.

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
        output:
          destination: orders.normalized
```

Sau khi chuyển sang một function bean tên `normalize`, binding mặc định sẽ là `normalize-in-0` và `normalize-out-0`. **Tên broker destination vẫn có thể giữ nguyên**, nhưng phải cập nhật hoặc alias các thuộc tính binding.

## 8. `@StreamListener`: phương thức nhận sự kiện do framework gọi

`@StreamListener` trong mã lịch sử đánh dấu phương thức xử lý record từ một input channel. Dạng thông dụng:

```java
@StreamListener("input")
public void onMessage(String body) {
    // Xử lý sự kiện cũ
}
```

Hoặc với tên constant:

```java
@StreamListener(Sink.INPUT)
public void onMessage(Message<String> message) {
    // Đọc payload và header
}
```

Các biến thể cần ghi lại:

- Tham số là POJO, `String`, `byte[]` hoặc `Message<T>`.
- Phương thức `void` (thường chỉ tiêu thụ) hoặc có kiểu trả về (có thể phát output).
- Có/không `@SendTo`.
- Có điều kiện `@StreamListener(value = ..., condition = ...)`.
- Dùng nhiều `@StreamListener` trên cùng một input hoặc nhiều channel khác nhau.
- Có tham số header, ví dụ `@Header(...)`.
- Có xử lý exception, retry hoặc acknowledgment đặc thù binder.

`@StreamListener` không phải tên bean function được Spring Cloud Function tìm qua `definition`. Đổi `spring.cloud.function.definition` thành tên method cũ mà vẫn giữ `@StreamListener` **không** tự tạo functional binding mới; cần chuyển method thành bean function đúng kiểu.

## 9. `@SendTo`: đường output của listener

Trong mã cũ, `@SendTo` từ Spring Messaging là một dấu hiệu quan trọng của việc route giá trị trả về. Ví dụ:

```java
@StreamListener(Processor.INPUT)
@SendTo(Processor.OUTPUT)
public String trim(String body) {
    return body.trim();
}
```

Nếu phương thức trả về `void`, thông thường không có output từ giá trị trả về; nếu nó gọi `MessageChannel.send()` bên trong thì vẫn có side effect phát message. Khi lập bản đồ luồng, cần kiểm tra **cả `@SendTo` và các lệnh send thủ công**.

Đừng gộp tất cả phương thức `@StreamListener` có `@SendTo` thành một `Function<T,R>` nếu có routing nhiều nhánh, nhiều output, delay, ack hoặc condition. Một `Function` có đầu vào/đầu ra phù hợp với xử lý một-một đơn giản, nhưng luồng phức tạp cần thiết kế rõ các output binding và điều kiện route.

## 10. Interface custom với `@Input` và `@Output`

Không phải code cũ nào cũng import `Source`, `Sink` hoặc `Processor`. Một số ứng dụng tạo interface tùy chỉnh:

```java
import org.springframework.cloud.stream.annotation.Input;
import org.springframework.cloud.stream.annotation.Output;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;

interface OrderChannels {
    String ORDERS_IN = "ordersIn";
    String ORDERS_OUT = "ordersOut";

    @Input(ORDERS_IN)
    SubscribableChannel ordersIn();

    @Output(ORDERS_OUT)
    MessageChannel ordersOut();
}
```

Class sử dụng:

```java
@EnableBinding(OrderChannels.class)
class LegacyCustomChannels {

    @StreamListener(OrderChannels.ORDERS_IN)
    @SendTo(OrderChannels.ORDERS_OUT)
    public String process(String body) {
        return body.toUpperCase();
    }
}
```

Tên binding là **`ordersIn` và `ordersOut`**, không phải `input`/`output`. Lần theo constant, literal string, `@Input`, `@Output` và configuration; đừng chỉ tìm `Processor.INPUT`.

```yaml
spring:
  cloud:
    stream:
      bindings:
        ordersIn:
          destination: orders.raw
          group: order-projection
        ordersOut:
          destination: orders.normalized
```

Một interface có thể chứa nhiều `@Input`/`@Output`. Mỗi channel tạo đường message cần kiểm kê độc lập. Trong mô hình hàm mới, những đường này có thể thành nhiều function, một function nhiều output, hoặc `StreamBridge`, tùy semantics chứ không phải số lượng annotation.

## 11. Nhận diện lệnh gửi trực tiếp qua `MessageChannel`

Không phải ứng dụng cũ nào cũng có method `@StreamListener`; có ứng dụng chỉ có REST endpoint, scheduler hoặc domain service sử dụng `MessageChannel` để gửi message. Ví dụ:

```java
@EnableBinding(Source.class)
class LegacyEventGateway {

    private final MessageChannel output;

    LegacyEventGateway(Source source) {
        this.output = source.output();
    }

    void fire(String event) {
        output.send(MessageBuilder.withPayload(event).build());
    }
}
```

Để phát hiện mẫu này, tìm `MessageChannel.send(`, `.output().send(`, `@Autowired Source` và injection các interface `@Output`. Cần xem call site được kích hoạt bởi request, domain transaction, scheduler hay message handler. Một publisher phát theo **sự kiện nghiệp vụ** không thể mặc nhiên thay bằng `Supplier` chạy polling mỗi giây mà không thay đổi hành vi.

`MessageChannel` còn dùng rộng rãi trong Spring Integration; chỉ phân loại là **Spring Cloud Stream legacy channel** nếu nó gắn với `@EnableBinding`/`@Output`/binding configuration tương ứng.

## 12. Tên binding cũ không đồng nhất với tên topic/queue

Cấu hình cũ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
        output:
          destination: orders.validated
```

Ở đây `input` và `output` là **tên logic trong ứng dụng**; binder sẽ biến chúng thành consumer/producer tới broker destination tương ứng. Kafka Binder thường trỏ đến topic, RabbitMQ Binder có thể tạo exchange/queue với tên phụ thuộc destination/group, còn Pulsar Binder trỏ đến topic và subscription theo cấu hình binder.

Sau khi chuyển sang functional model, mặc định một bean tên `validateOrder` sinh:

```text
validateOrder-in-0  -> orders.events
validateOrder-out-0 -> orders.validated
```

Phải chuyển cả cấu hình destination, consumer group và các **extended binder properties** đang gắn với `input`/`output`; nếu chỉ đổi Java code, các thuộc tính cũ có thể không còn tác dụng trên binding mới.

## 13. Xem cấu hình binder-specific gắn với tên cũ

Ngoài `spring.cloud.stream.bindings.*`, ứng dụng thường có thuộc tính nằm dưới binder Kafka, RabbitMQ hoặc Pulsar. Ví dụ dấu vết Kafka Binder cũ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
          consumer:
            concurrency: 3
            maxAttempts: 3
      kafka:
        bindings:
          input:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlq
```

Đây là cú pháp minh họa cho **mô hình cấu hình Kafka Binder cũ**; khả năng có mặt, tên property và tác động khi bật retry/DLQ phụ thuộc phiên bản. Khi chuyển `input` thành `processOrder-in-0`, cả `kafka.bindings.input.consumer...` cũng phải được kiểm tra/đổi tên nếu không dùng alias tương thích.

Những nhóm thuộc tính phải kiểm kê:

| Nhóm | Ví dụ | Rủi ro nếu bỏ sót |
|---|---|---|
| Destination | `bindings.input.destination` | Đọc nhầm topic/queue mới |
| Group/subscription | `bindings.input.group` | Thay đổi offset/subscription, có thể replay/duplicate |
| Concurrency | `bindings.input.consumer.concurrency` | Thay đổi throughput/ordering |
| Retry | `maxAttempts`, backoff | Xử lý lỗi và thời gian chặn khác trước |
| Kafka DLQ | `kafka.bindings.input.consumer.enableDlq` | Message lỗi không đi đúng DLQ |
| RabbitMQ topology | exchange, queue, routing, DLX | Tạo queue/exchange khác hoặc đổi routing |
| Pulsar subscription | subscription type/name và producer/consumer properties | Có thể đọc lại, chia tải sai hoặc mất key ordering |
| Serialization | `content-type`, native encoding/Serde | Thay đổi payload/schema thực tế |
| Partitioning | key expression, partition count | Thay đổi key-to-partition mapping và thứ tự |
| Error/ack | error channel, ack mode/handler | Commit sớm, retry lặp hoặc mất thông điệp |

Tên property hiện đại có thể đổi, không chỉ đổi prefix binding. Khi migration thực tế phải đối chiếu chính xác tài liệu Spring Cloud Stream/binder của **release train đích** và kiểm thử với broker, thay vì copy YAML cũ rồi coi đã đủ.

## 14. Các method `@StreamListener` có điều kiện

Một số code cũ cho phép xử lý nhiều loại message trên cùng channel qua `condition`, ví dụ:

```java
@StreamListener(value = Sink.INPUT,
                condition = "headers['eventType']=='ORDER_CREATED'")
public void onCreated(String payload) {
    // Xử lý sự kiện tạo đơn hàng
}

@StreamListener(value = Sink.INPUT,
                condition = "headers['eventType']=='ORDER_PAID'")
public void onPaid(String payload) {
    // Xử lý sự kiện thanh toán
}
```

Đây là một ví dụ **nhận diện cú pháp cũ**, không nên đem nguyên đoạn sang model mới. Trong functional model, hai `Consumer` độc lập cùng subscribe một destination không tự động tương đương cơ chế định tuyến điều kiện cũ; broker có thể chia message thay vì broadcast tùy group/binder.

Các lựa chọn chuyển đổi cần thiết kế rõ: một `Consumer<Message<T>>` đọc header và điều phối theo `eventType`, một function router được cấu hình đúng, hoặc các destination/consumer group riêng với quy tắc publish phù hợp. Nếu đổi từ điều kiện trong cùng một input sang hai group độc lập, hành vi delivery, throughput và duplication có thể thay đổi đáng kể.

## 15. Method có nhiều tham số, header và error handling

Không chỉ xem tên annotation; hãy đọc **chữ ký method và logic quanh nó**:

```java
@StreamListener(Sink.INPUT)
public void handle(
        String body,
        @Header("correlationId") String correlationId) {
    // Sử dụng payload cùng header
}
```

Các thành phần cần ghi vào inventory:

- Chữ ký có `Message<T>`, `@Payload`, `@Header` hay raw `byte[]` không?
- Có dùng header gắn key, partition, routing hoặc correlation ID không?
- Có `try/catch`, tự retry, error channel hoặc chuyển DLQ bằng code không?
- Có lệnh trả về sớm nhưng công việc vẫn chạy bất đồng bộ không?
- Có transaction/ack/commit phụ thuộc thời điểm method trả về không?
- Có ghi database, gọi service khác, phát message mới hoặc tham gia saga không?

Trong functional model, thường dùng `Consumer<Message<T>>` hoặc `Function<Message<T>, Message<R>>` để xử lý header. `Function<T,R>` có payload đơn giản nhưng không phải mọi header nghiệp vụ đều được giữ theo cách cũ khi thay đổi kiểu message. Phải kiểm thử message converter, header mapping và binder-specific delivery semantics.

## 16. Dấu hiệu mã cũ trong bài kiểm thử

Kiểm thử lịch sử có thể dùng dependency `spring-cloud-stream-test-support`, `TestSupportBinder` hoặc `MessageCollector`. Mẫu thường gặp là gửi một message vào input channel hoặc lấy queue message đã phát qua collector:

```java
// Dấu hiệu nhận diện test API của thế hệ cũ:
@Autowired
private MessageCollector messageCollector;

@Autowired
private Processor processor;

// Trong test method của dự án cũ:
processor.input().send(MessageBuilder.withPayload("abc").build());
Message<?> out = messageCollector
    .forChannel(processor.output())
    .poll();
```

Đoạn trích trên thiếu imports và assertion có chủ đích: đây là **mẫu nhận diện**, không phải test hoàn chỉnh để chạy trên phiên bản hiện đại. Hãy tìm thêm `org.springframework.cloud.stream.test.binder` và các import test support cũ. Đừng nghĩ code production đã nâng cấp thành công chỉ vì bài test cũ không còn compile: test infrastructure cũng cần thay đổi theo.

Đối với Spring Cloud Stream hiện đại, Test Binder có dependency `spring-cloud-stream-test-binder` và API `InputDestination`, `OutputDestination`, `@EnableTestBinder`. **Không** thay `@EnableBinding` bằng `@EnableTestBinder` trong production: annotation mới chỉ phục vụ test context.

## 17. Nhận diện dependency và version gây ra API cũ

Khi được phép thực hiện migration một repository thực tế, cần kiểm tra BOM, Spring Boot/Spring Cloud release train và các artifact binder. Những dependency thường xuất hiện ở dự án cũ:

```text
org.springframework.cloud:spring-cloud-stream
org.springframework.cloud:spring-cloud-stream-binder-kafka
org.springframework.cloud:spring-cloud-stream-binder-rabbit
org.springframework.cloud:spring-cloud-stream-test-support
```

Sự xuất hiện của Kafka/Rabbit binder **không chứng minh** ứng dụng còn dùng annotation model: các binder tương tự cũng có thể phục vụ functional model. Dấu hiệu mạnh hơn là import `org.springframework.cloud.stream.annotation.EnableBinding` hoặc `org.springframework.cloud.stream.messaging.Source` trong Java code cùng cấu hình `input`/`output`.

Một số module sử dụng Spring Kafka (`@KafkaListener`), Spring AMQP (`@RabbitListener`) hoặc Pulsar listener native thay vì Spring Cloud Stream. Các annotation đó là API **khác**; không phân loại chúng thành `@StreamListener` cũ và không tự đổi thành `Consumer<T>` nếu không có yêu cầu thay đổi công nghệ.

## 18. Tìm kiếm mã cũ một cách có hệ thống

Trong dự án mà bạn có quyền kiểm tra toàn bộ repository, có thể dùng các lệnh tìm kiếm **tham khảo** sau. Bài học này không yêu cầu chạy chúng trong workspace hiện tại.

```bash
# Tìm annotation hoặc interface channel cũ trong Java:
rg -n '@EnableBinding|@StreamListener|@Input\(|@Output\(|@SendTo' src
rg -n 'cloud\.stream\.messaging\.(Source|Sink|Processor)' src
rg -n 'Source\.OUTPUT|Sink\.INPUT|Processor\.(INPUT|OUTPUT)' src

# Tìm cách gửi và nhận qua channel:
rg -n 'MessageChannel|SubscribableChannel|\.output\(\)\.send|\.send\(' src

# Tìm binding config và test API cũ:
rg -n 'spring-cloud-stream-test-support|MessageCollector|TestSupportBinder' .
rg -n 'spring\.cloud\.stream|bindings:|destination:|group:' src/main/resources
```

`rg` là công cụ ripgrep; có thể thay bằng IDE Find in Files. Dòng tìm `send(` rất rộng nên kết quả là **ứng viên cần đọc**, không phải chứng cứ cuối cùng. Nếu dự án dùng static import, search `@EnableBinding` và `@StreamListener` sẽ bắt annotation ngay cả khi đường import bị lược. Nếu có code được sinh từ annotation processing hoặc class từ thư viện, cần xác minh call path thực tế.

Không thay hàng loạt bằng text replacement vì nhiều `Processor.INPUT` có thể ánh xạ về các destination khác nhau tùy profile và binder environment.

## 19. Mẫu bảng inventory dành cho quá trình nâng cấp

Trước khi sửa code, nên lập một hàng cho mỗi **đường message**, không chỉ một hàng cho mỗi Java class:

| Trường inventory | Ví dụ | Vì sao cần |
|---|---|---|
| Java owner | `LegacyOrderProcessor.normalize` | Định vị handler |
| Legacy API | `@EnableBinding(Processor.class)`, `@StreamListener` | Biết cơ chế khai báo |
| Input binding | `input` | Khớp key config cũ |
| Output binding | `output` | Khớp đường publish |
| Input destination | `orders.raw` | Giữ nguồn dữ liệu |
| Output destination | `orders.normalized` | Giữ topic/queue đích |
| Consumer group | `order-normalizer` | Bảo vệ offset/subscription |
| Payload và schema | `OrderEvent` + JSON/Avro | Tránh lỗi converter/Serde |
| Headers | `correlationId`, Kafka key | Bảo toàn tracking/routing |
| Retry/DLQ | `maxAttempts=3`, Kafka DLQ | Giữ chính sách lỗi |
| Partition/concurrency | 12 partitions, 3 threads | Tránh thay ordering/throughput |
| Side effect | DB update + outbound message | Đánh giá transaction/idempotency |
| Test hiện có | `MessageCollector` hoặc integration test | Biết phần cần viết lại |

Nếu hệ thống có nhiều profile (`local`, `staging`, `prod`) hoặc binder instance khác nhau, giá trị destination/group thực tế có thể khác. Inventory phải ghi các cấu hình quan trọng theo môi trường, không chỉ lấy giá trị mặc định trong một YAML.

## 20. Phân biệt `Source` với một functional `Supplier`

Tên `Source` khiến nhiều người nghĩ có thể đổi máy móc sang `Supplier<T>`, nhưng cần xem **điều kiện kích hoạt publish**:

| Mã cũ | Ngữ nghĩa | Hướng mới thường hợp lý |
|---|---|---|
| REST controller gọi `source.output().send(event)` | Phát khi nhận request | `StreamBridge.send(bindingName, event)` |
| Domain transaction gọi `output.send(...)` | Phát sau thay đổi nghiệp vụ | `StreamBridge` kết hợp outbox/transaction boundary phù hợp |
| Scheduler mỗi phút gọi `send` | Phát theo lịch | `Supplier` có poller phù hợp hoặc scheduler + `StreamBridge` |
| Generator vô hạn/sự kiện streaming | Phát liên tục | Reactive `Supplier<Flux<T>>` nếu semantics và lifecycle phù hợp |

`Supplier` của Spring Cloud Function có thể được polling theo lịch bởi framework. Nếu một publisher trước đây chỉ phát khi có lệnh thanh toán mà đổi thành `Supplier` trả lại cùng dữ liệu mỗi lần poll, hệ thống có thể phát **sự kiện trùng**. Chọn hướng chuyển dựa trên hành vi thực tế chứ không dựa vào tên interface cũ.

## 21. `Sink` thường chuyển thành `Consumer<T>`

Với listener chỉ xử lý một input và không phát output, mô hình hàm phù hợp là:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderConsumerConfiguration {

    @Bean
    Consumer<String> consumeOrder() {
        return payload -> System.out.println("Received: " + payload);
    }
}
```

Binding mới mặc định là `consumeOrder-in-0`. Để giữ destination/group từ ví dụ `Sink` cũ:

```yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.created
          group: order-projection
          content-type: application/json
```

Đây là **ví dụ đối chiếu mô hình**, không phải kết luận test nghiệp vụ đã pass. Nếu listener cũ nhận `Message<String>` hoặc đọc header partition/key, phải chuyển signature và assertions tương ứng. Nếu listener cũ dùng transaction/ack tùy chỉnh, cần kiểm thử container và binder thực, không chỉ unit test `Consumer.accept`.

## 22. `Processor` thường chuyển thành `Function<T,R>`

Ví dụ chuyển một handler cũ có `@SendTo`:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderTransformConfiguration {

    @Bean
    Function<String, String> normalizeOrder() {
        return orderId -> orderId.trim().toUpperCase();
    }
}
```

Cấu hình mapping:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
        normalizeOrder-out-0:
          destination: orders.normalized
```

`Function<T,R>` phù hợp khi giá trị đầu vào tạo ra một giá trị đầu ra theo cùng luồng. Nếu handler cũ có nhiều side effect hoặc output route khác nhau, cần phân tích riêng. Đừng mặc định mọi `@StreamListener` returning POJO đều có một `@SendTo` và một output tường minh.

## 23. Publisher kiểu cũ phát theo yêu cầu: `StreamBridge`

Để thay đường gửi chủ động qua `Source.output().send(...)`, API hiện đại thường là `StreamBridge`:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(String orderId) {
        return streamBridge.send(
            "orders-out-0",
            MessageBuilder.withPayload(orderId).build()
        );
    }
}
```

Gắn tên output binding `orders-out-0` vào destination cũ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
```

`StreamBridge.send(...)` tạo/sử dụng output binding dựa trên tên được cung cấp và cấu hình; đây không phải chính xác cùng API với `MessageChannel.send(...)`. Kiểm thử kiểu payload, header, binder routing, failure handling và semantics xác nhận gửi của binder. Không hiểu boolean của `send` là bảo đảm end-to-end delivery hoặc consumer đã xử lý.

## 24. Đổi tên binding tường minh hoặc dùng alias

Mô hình functional tạo tên binding ngầm định bằng tên function bean. Có hai chiến lược để giữ cấu hình cũ:

**Cách A — Đổi khóa cấu hình sang tên mới**, dễ đọc về lâu dài:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
        normalizeOrder-out-0:
          destination: orders.normalized
```

**Cách B — Alias binding ngầm định sang tên cũ**, hữu ích khi có nhiều thuộc tính đang tham chiếu `input`/`output`:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      function:
        bindings:
          normalizeOrder-in-0: input
          normalizeOrder-out-0: output
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
        output:
          destination: orders.normalized
```

Property `spring.cloud.stream.function.bindings` ánh xạ **implicit function binding name** sang tên binding tường minh. Khi dùng alias, bạn phải nhất quán: destination và extended binder properties cần gắn đúng tên binding đã được ánh xạ. Alias không khôi phục `@StreamListener` hay `@EnableBinding` đã bị loại khỏi API; nó chỉ giúp đặt tên cho binding của **function bean hiện đại**.

Chỉ dùng alias nếu có lợi ích thực tế về migration; không tạo nhiều tầng tên gây khó hiểu khi dự án không có ràng buộc tương thích.

## 25. Xem `spring.cloud.function.definition` khi ứng dụng có nhiều hàm

Ở mô hình cũ, `@EnableBinding` liệt kê interface channel, còn các method `@StreamListener` tự chỉ ra input cần nhận. Ở mô hình hàm, một ứng dụng có nhiều bean `Consumer`, `Function`, `Supplier` cần chọn các function liên kết với broker theo cấu hình.

```java
@Bean
Consumer<String> auditOrder() {
    return value -> System.out.println("Audit: " + value);
}

@Bean
Function<String, String> normalizeOrder() {
    return value -> value.trim().toUpperCase();
}
```

Ví dụ chọn hai function độc lập:

```yaml
spring:
  cloud:
    function:
      definition: auditOrder;normalizeOrder
```

Trong functional model, dấu `;` thường tách nhiều định nghĩa function độc lập, trong khi dấu `|` là cú pháp composition của Spring Cloud Function. Hai kiểu này không thể thay cho nhau tùy ý: composition làm thay đổi đường đi output/input, kiểu dữ liệu và tên binding. Nếu ứng dụng có nhiều function bean nhưng `definition` chưa được đặt tường minh, việc auto-detect có thể không khởi tạo binding như người nâng cấp mong đợi.

Khi nhận diện app cũ có nhiều listener, cần ghi rõ những listener nào là các luồng độc lập, những listener nào nằm trên cùng một channel và những listener nào là các bước liên tiếp. Sau đó mới quyết định `definition`, composition hoặc một function điều phối.

## 26. Cẩn trọng với `@StreamListener` kiểu reactive

Mã cũ đôi khi nhận/trả về `Flux` hoặc dùng `@StreamListener` với Kafka Streams `KStream`/`KTable`, thay vì nhận từng POJO. Ví dụ nhận diện chữ ký (mang tính minh họa):

```java
@StreamListener("input")
@SendTo("output")
public Flux<String> transform(Flux<String> input) {
    return input.map(String::toUpperCase);
}
```

Không đổi trực tiếp thành `Function<String,String>` nếu hành vi trước đây là một luồng reactive liên tục với backpressure, batching, window hoặc concurrency khác. Cần hiểu ranh giới subscription, completion, error và framework version đang sử dụng. Mô hình hàm có các kiểu reactive như `Function<Flux<T>, Flux<R>>` trong ngữ cảnh phù hợp, nhưng semantics khác function nhận từng message và cần kiểm tra binder hỗ trợ.

Đặc biệt, Kafka Streams Binder hỗ trợ kiểu xử lý gắn với `KStream`/`KTable`; khi nâng cấp, mục tiêu có thể là `Function<KStream<K,V>, KStream<K2,V2>>` hoặc `Consumer<KStream<K,V>>`, không phải `Function<OrderEvent,OrderEvent>` thông thường. Phải giữ application ID, Serde, task topology, repartition, changelog/state store và compatibility với dữ liệu Kafka hiện có. Việc chỉ nhìn `@StreamListener` mà không kiểm tra **kiểu tham số** sẽ phân loại sai loại ứng dụng.

## 27. Những mẫu Java không đồng nghĩa API Spring Cloud Stream cũ

Khi tìm kiếm toàn repository, nhiều kết quả tên gần giống nhau nhưng mang semantics khác:

| Dấu hiệu | Thuộc hệ thống nào? | Có phải dấu hiệu legacy Stream không? |
|---|---|---|
| `@EnableBinding` từ `org.springframework.cloud.stream.annotation` | Spring Cloud Stream annotation model | Có |
| `@StreamListener` từ `org.springframework.cloud.stream.annotation` | Spring Cloud Stream annotation model | Có |
| `@EnableTestBinder` | Spring Cloud Stream Test Binder | Không; đây là test API |
| `@KafkaListener` | Spring Kafka | Không trực tiếp |
| `@RabbitListener` | Spring AMQP | Không trực tiếp |
| `@Bean Consumer<OrderEvent>` | Spring Cloud Function/Java functional bean | Thường là model mới |
| `MessageChannel` không kèm `@Output` | Spring Messaging/Integration hoặc custom code | Chưa đủ bằng chứng |
| `Function<T,R>` chỉ dùng trong thuật toán Java | Java standard library | Chưa chắc đã được bind với broker |

Khi báo cáo "bao nhiêu chỗ phải chuyển", chỉ tính những entry point và output path **thực sự thuộc annotation-based Spring Cloud Stream model**. Nếu có một lớp vừa dùng `@KafkaListener` vừa dùng `@StreamListener`, hãy lập riêng hai đường dữ liệu và không thay thế nhầm phương thức listener của Spring Kafka.

## 28. Các rủi ro khi đổi API nhưng không giữ semantics

| Thao tác nâng cấp vội | Hậu quả có thể xảy ra | Kiểm tra trước khi deploy |
|---|---|---|
| Xóa `@EnableBinding`, giữ `@StreamListener` | Function binding mới không được tạo | Có bean `Consumer/Function/Supplier` thật không? |
| Đổi `Processor` thành `Function` nhưng giữ YAML `input`/`output` | Binding mới dùng destination mặc định ngoài dự kiến | Kiểm tra tên binding/runtime destination |
| Đổi tên consumer group theo Pod/release | Offset/subscription tách riêng, replay hoặc nhân bản message | Giữ group cũ hoặc lên kế hoạch migration offset |
| Đổi publisher chủ động thành polling Supplier | Phát message trùng hoặc phát sai thời điểm | Ghi nhận nguồn kích hoạt thực của publisher |
| Bỏ `@SendTo` mà không có output mới | Event không được phát tiếp | Test output payload và destination |
| Bỏ `@Header` vì chỉ giữ POJO | Mất correlation/routing/partition key | Assertion headers ở integration test |
| Thay condition bằng hai Consumer cùng destination không điều phối | Mỗi consumer có thể thấy/chia message khác trước | Xác minh semantics group/binder |
| Thay `Message<T>` thành `T` mà không kiểm converter | Payload/schema hoặc headers thay đổi | Test content type, schema và Serde |
| Thay binder mà không kiểm retry/DLQ | Lỗi được retry hoặc dead-letter khác trước | Integration test lỗi tạm thời/poison message |
| Tăng concurrency sau migration | Thứ tự per key/partition bị ảnh hưởng bởi app logic | Test ordering, ack và database version |
| Nâng Kafka Streams topology mà không kiểm state | Restore/repartition/changelog ngoài dự kiến | Test state compatibility và recovery |

Điểm cốt lõi là **legacy annotation không chứa toàn bộ hợp đồng vận hành**. Hợp đồng nằm ở sự kết hợp của Java method, binding names, binder properties, broker topology, schema, producer/consumer group và error handling.

## 29. Mô hình khử trùng lặp và giao nhận khi chuyển đổi

Một consumer cũ có thể nhận message theo at-least-once: nếu database đã ghi thành công nhưng ứng dụng chết trước ack/offset commit, message có thể được gửi lại. Sau migration vẫn phải bảo vệ:

```text
Broker -> Consumer -> kiểm tra eventId/version
                     -> transaction cập nhật dữ liệu
                     -> ack/commit khi đã an toàn
```

Nếu handler mới trả về ngay sau khi đẩy việc vào thread pool, binder có thể nhận tín hiệu thành công trước khi cập nhật database; đó không phải hành vi tương đương với handler cũ xử lý đồng bộ. Kafka transaction/exactly-once semantics không tự tạo giao dịch phân tán với database ngoài Kafka; cần idempotency, transactional outbox hoặc thiết kế phối hợp thích hợp.

Khi lập inventory, ghi rõ *thời điểm method trả về*, *thời điểm side effect bền vững*, *lúc ack/commit*, *cách retry* và *cách replay DLQ*. Đây là những tiêu chí migration test quan trọng hơn việc Java class biên dịch thành công.

## 30. Tách phép nhận diện khỏi quyết định nâng cấp

Quy trình triển khai có thể chia thành hai phần rõ ràng:

**Phần A — Nhận diện không sửa behavior**

1. Liệt kê annotation/interface channel cũ.
2. Nối chúng với các cấu hình `bindings`, `kafka.bindings`, `rabbit.bindings` hoặc Pulsar binder tùy phiên bản.
3. Vẽ mỗi đường input → handler → output, including side effects.
4. Ghi lại destination, group/subscription, partitioning, serializer, retry/DLQ.
5. Đọc test hiện có để xác định contract thực tế và khoảng trống.
6. Phân loại handler: consume-only, transform, publish-on-demand, multi-input, multi-output, reactive/stateful.

**Phần B — Chuyển đổi có kiểm soát**

1. Chọn đúng kiểu functional bean hoặc `StreamBridge`.
2. Đặt `spring.cloud.function.definition` và binding names rõ ràng.
3. Mapping destination/group và các binder-specific properties.
4. Viết unit test cho logic, Test Binder test cho functional wiring.
5. Viết integration test với đúng Kafka/RabbitMQ/Pulsar và broker policy.
6. Deploy canary/rolling update có kiểm soát, đối chiếu message flow/metrics.
7. Chỉ loại bỏ mã cũ khi đường message mới và rollback strategy đã được xác minh.

**Không chạy song song hai consumer path của hai phiên bản** trên cùng một topic một cách vô tình. Nếu chúng dùng khác group, mỗi nhóm có thể xử lý cùng event; nếu cùng group nhưng xử lý khác schema/protocol, kết quả có thể không nhất quán. Với upgrade cần zero downtime, phải thiết kế version compatibility, ownership và rollback minh bạch.

## 31. Ví dụ thực hành: kiểm kê một service legacy

Giả sử tài liệu nội bộ của một service cũ cho biết:

```java
@EnableBinding(Processor.class)
class PaymentNormalizer {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String normalize(String reference) {
        return reference.trim().toUpperCase();
    }
}
```

Và configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: payments.raw
          group: payment-normalizer
          content-type: text/plain
        output:
          destination: payments.normalized
          content-type: text/plain
```

Bản inventory cần ghi:

| Nội dung | Kết quả kiểm kê |
|---|---|
| API legacy | `@EnableBinding`, `Processor`, `@StreamListener`, `@SendTo` |
| Kiểu xử lý | Một input → một output, synchronous transform |
| Input binding logic | `input` |
| Input destination | `payments.raw` |
| Consumer group | `payment-normalizer` |
| Output binding logic | `output` |
| Output destination | `payments.normalized` |
| Payload | `String`, trim + uppercase, `text/plain` |
| Chưa rõ | Retry/DLQ, binder type, serializer, ack, idempotency, deployment replicas |

Sau khi nhận diện, có thể viết `Function<String,String> normalizePayment` và chuyển binding names sang `normalizePayment-in-0`/`normalizePayment-out-0`, nhưng **chưa được** tuyên bố migration thành công cho đến khi các mục "chưa rõ" được giải đáp và kiểm thử. Bài thực hành tốt phải lưu lại cả các thông tin thiếu; không điền giả định như thể chúng đã được xác minh.

## 32. Kiểm thử regression cho việc nâng cấp API

Một bộ test hữu ích nên chứa:

| Kịch bản | Mục tiêu | Công cụ phù hợp |
|---|---|---|
| Input string/JSON hợp lệ | Logic transform đúng như trước | Unit test + Test Binder |
| Input thiếu field/sai schema | Converter và xử lý lỗi đúng | Test Binder + broker integration |
| Output destination đúng | Không phát sang topic/queue mới ngoài dự kiến | Configuration integration test |
| Consumer group giữ nguyên | Không đổi offset/subscription ngoài ý muốn | Broker integration |
| Retry và DLQ | Message lỗi được xử lý theo policy kỳ vọng | Kafka/RabbitMQ/Pulsar thật hoặc test environment |
| Kafka partition key | Cùng key vẫn tới partition theo thiết kế | Kafka integration |
| Rabbit exchange/queue/routing | Provision/routing không bị đổi | RabbitMQ integration |
| Pulsar subscription/schema | Consumer đọc đúng backlog/encoding | Pulsar integration |
| Crash sau side effect | Redelivery không nhân đôi tác động | Fault-injection integration |
| Multi-function routing | Message đến đúng handler điều kiện | Functional integration test |
| Kafka Streams state restore | State tương thích sau deployment | Topology/stateful integration |

Test Binder hiện đại giúp xác minh phần wiring và message transformation, nhưng không thay thế broker-level tests cho partition, ACL, DLQ, consumer group rebalancing và delivery guarantees. Nếu nâng cấp app vốn dùng `MessageCollector`, cần chuyển test hạ tầng song song với code để vẫn có kiểm thử regression đáng tin cậy.

## 33. Chẩn đoán lỗi thường gặp khi đọc hoặc nâng cấp mã cũ

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
|---|---|---|
| IDE không tìm thấy `@EnableBinding` | Phiên bản Spring Cloud Stream mới không còn cung cấp API cũ | Xác định release train và chuyển functional model |
| `@StreamListener` không còn hoạt động | Mô hình annotation không được hỗ trợ/không được đăng ký | Tạo bean function và binding mới |
| App chạy nhưng không nhận event | Binding mới trỏ đến destination mặc định khác | Kiểm tra `function.definition`, binding/destination |
| Nhận lại message cũ hoặc có duplicate | Group/subscription bị đổi | So sánh consumer group cũ và mới, offset/subscription |
| Output không xuất hiện | Method cũ có `@SendTo`, function mới không trả output | Kiểm tra kiểu `Function`, output binding và destination |
| Có function nhưng không được bind | Có nhiều bean và thiếu/chưa đúng `definition` | Chọn đúng function bean hoặc composition |
| Kafka DLQ không còn hoạt động | Binder-specific config vẫn gắn key `input` cũ | Chuyển/alias extended binding properties |
| Schema mapping lỗi | Message converter/content type/native serde khác trước | So sánh payload và headers ở broker |
| Test `MessageCollector` không compile | Test-support cũ không tương thích | Dùng `spring-cloud-stream-test-binder` đúng version |
| Đổi publisher sang Supplier gây trùng | Poller tự kích hoạt nhiều lần | Dùng StreamBridge cho event-triggered send |
| Kafka Streams không phục hồi state | Topology/Serde/application ID thay đổi | Kiểm tra compatibility và state recovery |

## 34. Checklist nhận diện trước khi sửa một dòng code

- [ ] Đã tìm `@EnableBinding`, `@StreamListener`, `@Input`, `@Output` và `@SendTo`.
- [ ] Đã tìm import `Source`, `Sink`, `Processor` và custom channel interfaces.
- [ ] Đã xác định nơi gọi `MessageChannel.send()` và `source.output().send()`.
- [ ] Đã phân biệt channel binding name và broker destination.
- [ ] Đã vẽ input → handler → output cho từng luồng sự kiện.
- [ ] Đã ghi đúng consumer group/subscription, không suy từ tên service.
- [ ] Đã kiểm tra Kafka/RabbitMQ/Pulsar binder-specific properties có dùng tên binding cũ không.
- [ ] Đã nhận diện listener điều kiện, multi-input/multi-output, reactive và Kafka Streams.
- [ ] Đã ghi lại payload types, content type, schema và headers nghiệp vụ.
- [ ] Đã xác định retry, DLQ, ack/offset, transaction và side effect.
- [ ] Đã kiểm tra nơi sử dụng test-support cũ và lập kế hoạch đổi test infrastructure.
- [ ] Đã chọn giữa `Consumer`, `Function`, `Supplier` và `StreamBridge` dựa vào behavior.
- [ ] Đã quyết định đổi binding key hay dùng `spring.cloud.stream.function.bindings` alias.
- [ ] Đã lập bộ regression tests dùng broker thật cho điều kiện giao nhận quan trọng.

## 35. Câu hỏi tự kiểm tra

1. `Source`, `Sink`, `Processor` cung cấp những channel nào và tên mặc định của chúng là gì?
2. `@EnableBinding(Processor.class)` và `@StreamListener(Processor.INPUT)` đảm nhận vai trò khác nhau thế nào?
3. Tại sao `@SendTo(Processor.OUTPUT)` là dấu vết phải kiểm tra riêng khi nâng cấp?
4. Làm sao tìm đúng tên binding khi ứng dụng dùng interface có `@Input("ordersIn")`?
5. `bindings.input.destination=orders.raw` có nghĩa topic phải đặt tên `input` không?
6. Vì sao đổi `input` thành `normalize-in-0` nhưng giữ nguyên Kafka DLQ properties có thể gây lỗi?
7. Khi publisher cũ gửi trong REST handler, `Supplier` polling có luôn tương đương `Source.output().send()` không?
8. Có nên thay `@EnableBinding` bằng `@EnableTestBinder` trong ứng dụng production không? Vì sao?
9. Mẫu `@StreamListener` nhận `Flux` hoặc `KStream` cần phân tích thêm điều gì?
10. Vì sao giữ consumer group, ack/commit và idempotency quan trọng khi đổi API dù logic transform không đổi?

## Kết luận

Nhận diện mã cũ Spring Cloud Stream là quá trình tìm **dấu vết của mô hình channel/annotation**, không chỉ rà soát vài tên class. `@EnableBinding` tạo binding cho `Source`/`Sink`/`Processor` hoặc interface `@Input`/`@Output`; `@StreamListener` xử lý input; `@SendTo` và `MessageChannel.send` là những đường phát output cần theo dõi. Cấu hình `bindings.input`/`bindings.output`, consumer group, destination, binder extensions, retry/DLQ, serialization và test-support cũ là một phần của cùng hợp đồng xử lý sự kiện. Sau khi lập inventory đầy đủ, mới chọn `Supplier`, `Function`, `Consumer` hay `StreamBridge` và chuyển tên binding có chủ đích, rồi xác minh bằng regression/integration tests trước khi nâng cấp production.

## Tài liệu tham khảo

- Spring Cloud Stream Reference — Functional Binding Names: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html
- Spring Cloud Stream Reference — Producing and Consuming Messages: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html
- Spring Cloud Stream Reference — Binding Properties: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html
- Spring Cloud Stream Reference — StreamBridge: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html#streambridge-and-dynamic-destinations
- Spring Cloud Stream Reference — Test Binder: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html
- Spring Cloud Function Reference — Function Definition and Composition: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
- Spring Cloud Stream 3.x Documentation — Historical annotation programming model (tra cứu bản đúng với dự án cũ): https://docs.spring.io/spring-cloud-stream/docs/3.2.x/reference/html/
