# DltStrategy

Trong hệ thống **Spring Kafka Reliability Operations**, non-blocking retry giúp chuyển record xử lý lỗi qua các retry topic thay vì giữ consumer ở topic chính trong suốt thời gian backoff. Khi đã thử hết số lần cho phép, record thường được đưa sang **Dead Letter Topic (DLT)** để điều tra hoặc xử lý theo một quy trình riêng. Nhưng bản thân consumer của DLT cũng có thể thất bại: không ghi được bản ghi lỗi vào database, API quản trị tạm ngừng hoạt động, hoặc payload không thể deserialize.

**DltStrategy** xác định Spring Kafka sẽ làm gì khi **DLT handler thất bại**, hoặc có tạo DLT cho luồng retry hay không. Nó là enum trong package **org.springframework.kafka.retrytopic**. Hiểu rõ ba giá trị **ALWAYS_RETRY_ON_ERROR**, **FAIL_ON_ERROR** và **NO_DLT** giúp tránh vòng lặp phát lại DLT vô hạn, xử lý nhầm record lỗi là đã hoàn tất hoặc vô tình bỏ qua một nguồn dữ liệu cần phục hồi.

Bài học sử dụng API phổ biến của Spring Kafka 3.x; tên thuộc tính và một số hành vi có thể khác giữa các phiên bản. Hãy đối chiếu Javadoc tương ứng với dependency thực tế trước khi áp dụng code vào ứng dụng.

## 1. DltStrategy nằm ở đâu trong non-blocking retry?

Một listener được cấu hình **@RetryableTopic** có thể tạo các retry topic với các khoảng chờ khác nhau. Khi listener của topic chính hoặc topic retry ném exception, cơ chế non-blocking retry publish record sang topic thích hợp để một consumer khác xử lý sau.

Luồng điển hình:

~~~text
orders                         Topic chính
  |
  | xử lý lỗi
  v
orders-retry-1000               Chờ tới lần thử tiếp theo
  |
  | vẫn lỗi
  v
orders-retry-2000               Tiếp tục thử với backoff
  |
  | hết lần thử được cấu hình
  v
orders-dlt                      Nhận record cần xử lý riêng
  |
  v
@DltHandler                     Ghi nhận/điều tra/phục hồi
  |
  +-- thành công                 Hoàn tất xử lý DLT
  |
  +-- exception                  Áp dụng DltStrategy
~~~

Tên retry topic, hậu tố, số lượng topic và khoảng chờ cụ thể phụ thuộc cấu hình và phiên bản Spring Kafka. Sơ đồ chỉ minh họa trình tự.

Có hai ranh giới lỗi cần tách bạch:

1. **Listener chính/retry thất bại:** bộ định tuyến retry topic quyết định chuyển sang retry topic tiếp theo hay DLT, dựa trên số lần thử, timeout, exception classification và destination.
2. **DLT handler thất bại:** DltStrategy quyết định có chuyển tiếp record trở lại DLT, báo lỗi mà không chuyển tiếp, hoặc ngay từ đầu không cấu hình DLT.

Vì vậy, DltStrategy không thay thế cấu hình attempts, backoff, include/exclude exception hay timeout của retry topic. Nó chủ yếu quyết định hành vi ở cuối luồng.

## 2. Ba giá trị của DltStrategy

| Giá trị | Khi nào dùng | Hành vi quan trọng |
|---|---|---|
| **ALWAYS_RETRY_ON_ERROR** | Muốn DLT tiếp tục nhận record khác, kể cả khi một record DLT xử lý lỗi | Khi DLT handler lỗi, thường publish record trở lại DLT để có một lần tiêu thụ mới; có ngoại lệ với fatal exception |
| **FAIL_ON_ERROR** | Muốn lỗi DLT handler được báo ra mà không tạo thêm bản sao DLT | Không tự forward record thất bại trở lại DLT; exception đi qua đường xử lý lỗi của DLT consumer/container |
| **NO_DLT** | Chấp nhận kết thúc luồng sau khi hết retry mà không tạo DLT | Không cấu hình DLT cho chuỗi retry đó |

**ALWAYS_RETRY_ON_ERROR là giá trị mặc định** trong cấu hình retry topic có DLT. Điều này không đồng nghĩa mọi exception đều được gửi trở lại DLT; framework có cơ chế loại trừ các lỗi được xem là fatal.

Ví dụ khai báo giá trị trong code Java:

~~~java
import org.springframework.kafka.retrytopic.DltStrategy;

DltStrategy defaultBehavior = DltStrategy.ALWAYS_RETRY_ON_ERROR;
DltStrategy failWithoutReforward = DltStrategy.FAIL_ON_ERROR;
DltStrategy omitDlt = DltStrategy.NO_DLT;
~~~

Tên enum mô tả hành vi của **cơ chế retry-topic/DLT** trong Spring Kafka, không phải một Kafka broker configuration. Thay đổi DltStrategy không làm Kafka broker tự tạo thêm một loại acknowledgment hay bảo đảm exactly-once cho database.

## 3. ALWAYS_RETRY_ON_ERROR: gửi lại record về DLT

Đây là lựa chọn mặc định. Khi DLT handler ném một exception mà framework cho phép retry bằng DLT, record được publish **trở lại chính DLT**. Nhờ vậy, consumer có thể tiếp tục lấy và xử lý các record DLT khác, trong khi record vừa thất bại có thêm cơ hội được tiêu thụ lại.

Ví dụ DLT có các record:

~~~text
orders-dlt
offset 70: event A    -> xử lý DLT lỗi
offset 71: event B    -> xử lý DLT thành công
offset 72: event C    -> xử lý DLT thành công

Khi event A lỗi:
  A được publish trở lại orders-dlt ở một offset mới
  DLT consumer có thể tiếp tục đọc B và C
~~~

**Đây là một lần publish mới**, không phải “quay ngược offset” hoặc gọi lại cùng listener invocation. Offset mới của bản phát lại khác offset ban đầu. Nếu handler tiếp tục thất bại, luồng có thể tạo thêm nhiều bản record trên DLT.

### 3.1. Lợi ích

- Một record DLT lỗi không nhất thiết chặn tất cả record sau nó.
- Hệ thống có thể tự thử lại khi sự cố tạm thời của DLT processor kết thúc.
- Có thể cô lập phần lớn lỗi DLT khỏi hoạt động xử lý của topic chính và các retry topic.
- Thích hợp khi DLT handler chỉ gặp lỗi tạm thời, ví dụ hệ thống lưu sự cố bị timeout ngắn.

### 3.2. Rủi ro khi một record lỗi cố định

Giả sử DLT handler luôn ném exception vì payload có cấu trúc không hợp lệ. Nếu framework liên tục forward record về DLT, có thể xuất hiện:

~~~text
DLT event A #1
      |
      v
Handler lỗi
      |
      v
DLT event A #2
      |
      v
Handler lại lỗi
      |
      v
DLT event A #3
      |
      v
...
~~~

Hậu quả gồm tăng dung lượng topic, tăng lưu lượng producer/consumer, nhiều bản ghi cho cùng event, khó phân biệt số event gốc và số lần retry, và rủi ro DLT tăng nhanh hơn khả năng điều tra.

Do đó, cần quan sát **DLT reforward rate**, số lần xuất hiện theo eventId, tuổi record và kích thước DLT. Đặt retention, quota và cảnh báo phù hợp. Không mặc định để việc republish kéo dài vô hạn cho lỗi chắc chắn không thể phục hồi.

### 3.3. Ngoại lệ với fatal exception

Từ Spring Kafka **2.8.3**, chính sách ALWAYS_RETRY_ON_ERROR không tự forward về DLT với các exception được framework xem là fatal, bởi thử lại cùng payload có thể lặp lại cùng một lỗi mãi mãi.

Các nhóm điển hình trong danh sách fatal của tài liệu Spring Kafka gồm:

- DeserializationException
- MessageConversionException
- ConversionException
- MethodArgumentResolutionException
- NoSuchMethodException
- ClassCastException

Danh sách có thể được tùy chỉnh qua các API liên quan đến **DestinationTopicResolver** ở phiên bản Spring Kafka tương ứng. Không nên sửa danh sách chỉ để buộc những lỗi deserialize cố định liên tục quay về DLT. Khi thay đổi, cần hiểu rõ exception wrapper, cause chain và mục tiêu nghiệp vụ.

**ALWAYS** trong tên enum là chính sách mặc định cho lỗi DLT phù hợp để reforward; nó không phải cam kết rằng mọi loại exception đều được publish lại bất kể điều kiện.

## 4. FAIL_ON_ERROR: báo lỗi, không forward lại DLT

Với **FAIL_ON_ERROR**, khi DLT handler ném exception, Spring Kafka không tự đưa record đó trở lại DLT theo cơ chế reforward của non-blocking retry.

Ví dụ:

~~~text
orders-dlt, offset 70: event A
            |
            v
        @DltHandler
            |
            v
        Database lỗi
            |
            v
     FAIL_ON_ERROR
            |
            v
     Exception được báo ra
     Không tạo event A mới ở DLT
~~~

Điều này giúp tránh phát sinh nhiều bản sao DLT mới chỉ vì DLT processor bị lỗi. Nó phù hợp khi quy trình vận hành yêu cầu giữ một bản record để xử lý có kiểm soát, hoặc khi việc nhân bản dữ liệu lỗi có chi phí cao.

**Không hiểu FAIL_ON_ERROR là “bỏ qua record” hoặc “chắc chắn sẽ thử lại ngay”.** Lỗi tiếp tục tương tác với cấu hình của listener container, acknowledgment và error handler cho DLT. Tùy các thành phần đó, record có thể được giao lại, tiêu thụ chậm, làm partition bị giữ, hoặc được xử lý theo chính sách lỗi khác. FAIL_ON_ERROR chỉ khẳng định rằng chiến lược DLT này không tự forward lại record lên DLT như ALWAYS_RETRY_ON_ERROR.

Các trường hợp nên cân nhắc FAIL_ON_ERROR:

- DLT consumer ghi dữ liệu vào kho điều tra và không được âm thầm bỏ qua lỗi ghi.
- Cần hệ thống giám sát hoặc operator quyết định khi nào replay.
- Muốn hạn chế việc một lỗi cố định tạo nhiều bản sao trên DLT.
- DLT cần xử lý tuần tự theo key và không muốn record lỗi được đặt lại cuối log dưới offset mới.

Rủi ro là DLT consumer có thể lặp lại lỗi hoặc bị chậm nếu không có error handling phù hợp. Vì vậy, cần có cảnh báo và runbook xử lý record không thể hoàn tất.

## 5. NO_DLT: không cấu hình dead-letter topic

**NO_DLT** khác hẳn hai lựa chọn trên. Nó yêu cầu framework không cấu hình DLT cho retry-topic flow. Sau khi hết các lần thử, quá trình xử lý qua chuỗi retry kết thúc mà không có DLT được framework tạo ra để giữ record thất bại cuối cùng.

Ví dụ:

~~~text
orders -> orders-retry-1000 -> orders-retry-2000
                                  |
                                  v
                            Hết retry
                                  |
                                  v
                       Kết thúc luồng retry
                       (không tạo orders-dlt)
~~~

NO_DLT không có nghĩa Kafka tự xóa tất cả record gốc ngay lập tức. Record vẫn chịu retention của các topic đã được ghi. Nhưng hệ thống **không có điểm tập trung DLT** để điều tra, sửa dữ liệu và re-drive theo cơ chế retry-topic này.

NO_DLT chỉ phù hợp nếu nghiệp vụ có lý do rõ ràng để không lưu lỗi cuối cùng, chẳng hạn dữ liệu có thể tái tạo hoàn toàn từ một nguồn khác, kết quả xử lý không quan trọng, hoặc đã có luồng lưu lỗi độc lập được thiết kế có chủ đích.

Với đơn hàng, thanh toán, hóa đơn, tồn kho hoặc sự kiện có nghĩa vụ kiểm toán, bỏ DLT mà không có cơ chế phục hồi khác có thể khiến record quan trọng không được xử lý mà không dễ phát hiện. Trước khi chọn NO_DLT, hãy xác định ai chịu trách nhiệm theo dõi lỗi hết retry và cách khôi phục sự kiện.

## 6. Phân biệt NO_DLT với tắt tự khởi động DLT consumer

Một nhu cầu rất thường gặp là **vẫn lưu record vào DLT, nhưng không muốn ứng dụng tự động tiêu thụ DLT**. Ví dụ đội vận hành muốn xử lý DLT thủ công sau khi đã phân loại và sửa dữ liệu.

Trong trường hợp này, **không dùng NO_DLT**. Hãy vẫn cấu hình DLT và tắt việc tự khởi động listener của DLT bằng thuộc tính **autoStartDltHandler**.

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "4",
    autoStartDltHandler = "false"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void process(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong API @RetryableTopic, **autoStartDltHandler là String**, nên ví dụ dùng giá trị chuỗi `"false"`. Với configuration builder, dùng phương thức nhận Boolean là **autoStartDltHandler(false)**.

Kết quả mong muốn: khi record hết retry, record vẫn có thể được gửi vào DLT; container xử lý DLT không tự start. Sau đó có thể khởi động DLT container qua **KafkaListenerEndpointRegistry** theo cơ chế lifecycle của ứng dụng. DLT giữ record theo retention trong thời gian chờ.

| Cấu hình | Có DLT? | DLT consumer tự chạy? | Sau khi hết retry |
|---|---|---|---|
| NO_DLT | Không | Không có DLT consumer từ flow này | Luồng kết thúc, không forward vào DLT |
| DLT mặc định | Có | Thông thường có | Record được chuyển sang DLT và xử lý bởi DLT listener |
| DLT + autoStartDltHandler="false" | Có | Không tự chạy | Record được lưu trong DLT để xử lý sau |

Tắt auto-start không đồng nghĩa record được giữ mãi. Hãy đặt DLT retention đủ dài để tránh mất khả năng điều tra trước khi operator khởi động handler.

## 7. Cấu hình DltStrategy bằng @RetryableTopic

Với Spring Kafka 3.x, thuộc tính annotation dùng để chọn enum là **dltStrategy**.

Ví dụ dùng FAIL_ON_ERROR và một DLT handler rõ ràng:

~~~java
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.kafka.retrytopic.DltStrategy;
import org.springframework.retry.annotation.Backoff;

@Component
public class OrderConsumer {

    private final OrderService orderService;
    private final IncidentStore incidentStore;

    public OrderConsumer(
            OrderService orderService,
            IncidentStore incidentStore) {
        this.orderService = orderService;
        this.incidentStore = incidentStore;
    }

    @RetryableTopic(
        kafkaTemplate = "kafkaTemplate",
        attempts = "4",
        backoff = @Backoff(
            delay = 1_000,
            multiplier = 2.0,
            maxDelay = 8_000
        ),
        dltStrategy = DltStrategy.FAIL_ON_ERROR
    )
    @KafkaListener(
        topics = "orders",
        groupId = "order-service"
    )
    public void process(OrderEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void processDlt(OrderEvent event) {
        // Tác vụ lưu lỗi phải có tính idempotent.
        // Khi persist thất bại, ném exception để
        // framework áp dụng FAIL_ON_ERROR.
        incidentStore.saveOnce(event.eventId(), event);
    }
}
~~~

Đây là ví dụ thiết kế: **OrderEvent**, **OrderService** và **IncidentStore** là các kiểu nghiệp vụ do ứng dụng triển khai. Cần cấu hình producer template, serializer, deserializer và topic đúng với kiểu payload thực tế.

Trong cấu hình trên:

1. Listener chính thử xử lý event.
2. Khi có lỗi thuộc loại được retry, framework chuyển qua retry topic tương ứng.
3. Sau khi hết attempts, record chuyển vào DLT.
4. processDlt() cố lưu event vào hệ thống điều tra.
5. Nếu processDlt() ném exception, FAIL_ON_ERROR ngăn cơ chế tự reforward record vào DLT.

Cách đếm **attempts** của @RetryableTopic bao gồm lần xử lý ban đầu theo API hiện hành; khác với tham số số retry của nhiều BackOff implementation. Không trộn lẫn hai cách đếm khi dự báo tổng số lần gọi dịch vụ.

**Lưu ý:** Một method @DltHandler trong cùng class có thể được dùng cho các method @RetryableTopic khác trong class. Nếu nhiều listener xử lý payload hoặc nghiệp vụ khác nhau, hãy tách class hoặc thiết kế DLT handler xử lý rõ từng loại event.

## 8. Cấu hình ALWAYS_RETRY_ON_ERROR bằng annotation

Muốn sử dụng mặc định, có thể bỏ thuộc tính dltStrategy:

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "5"
)
@KafkaListener(topics = "notifications", groupId = "notification-worker")
public void process(NotificationEvent event) {
    notificationService.dispatch(event);
}

@DltHandler
public void processDlt(NotificationEvent event) {
    incidentStore.saveOnce(event.eventId(), event);
}
~~~

Tương đương với việc chỉ định rõ:

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "5",
    dltStrategy = DltStrategy.ALWAYS_RETRY_ON_ERROR
)
~~~

Chỉ nên dùng chính sách này khi DLT handler có khả năng phục hồi sau lỗi tạm thời và đội vận hành đã theo dõi được số lần reforward. Nếu incidentStore luôn lỗi vì validation cố định, việc republish liên tục có thể làm DLT tăng nhanh.

Trong tài liệu Spring Kafka có thể gặp các ví dụ hoặc cách đặt tên cũ như **dltProcessingFailureStrategy**. Cần dùng tên thuộc tính mà Javadoc của phiên bản dependency đang chạy cung cấp; trong API Spring Kafka 3.x hiện hành là **dltStrategy**.

## 9. Cấu hình NO_DLT bằng annotation

Khi nghiệp vụ thật sự không yêu cầu DLT:

~~~java
@RetryableTopic(
    kafkaTemplate = "kafkaTemplate",
    attempts = "3",
    dltStrategy = DltStrategy.NO_DLT
)
@KafkaListener(topics = "ephemeral-events", groupId = "ephemeral-worker")
public void process(EphemeralEvent event) {
    ephemeralService.process(event);
}
~~~

Không cần @DltHandler cho flow này, vì Spring Kafka không cấu hình DLT. Hãy bổ sung metric cho số record hết retry để operator biết có bao nhiêu event không được xử lý hoàn tất. Nếu cần lưu lỗi, hãy dùng một cơ chế lưu trữ khác có độ bền thích hợp.

NO_DLT có thể có giá trị với event tạm thời hoặc dữ liệu có thể tái dựng, nhưng không nên dùng chỉ để tránh vận hành DLT. Việc không nhìn thấy backlog lỗi không phải dấu hiệu hệ thống đang khỏe.

## 10. Cấu hình qua RetryTopicConfigurationBuilder

Bên cạnh annotation, Spring Kafka hỗ trợ **RetryTopicConfigurationBuilder**. Cách này phù hợp khi cần gom cấu hình retry topic vào một @Configuration class hoặc áp dụng chính sách theo topic.

Ví dụ với FAIL_ON_ERROR:

~~~java
@Bean
RetryTopicConfiguration retryTopicConfiguration(
        KafkaTemplate<String, OrderEvent> template) {

    return RetryTopicConfigurationBuilder
            .newInstance()
            .maxAttempts(4)
            .fixedBackOff(1_000L)
            .doNotRetryOnDltFailure()
            .create(template);
}
~~~

Phương thức **doNotRetryOnDltFailure()** đặt DltStrategy thành FAIL_ON_ERROR.

Có thể dùng phương thức tổng quát:

~~~java
RetryTopicConfigurationBuilder.newInstance()
    .dltProcessingFailureStrategy(DltStrategy.FAIL_ON_ERROR);
~~~

Hoặc nếu muốn **không có DLT**:

~~~java
RetryTopicConfigurationBuilder.newInstance()
    .maxAttempts(4)
    .fixedBackOff(1_000L)
    .doNotConfigureDlt();
~~~

Phương thức **doNotConfigureDlt()** chọn NO_DLT. Nếu chỉ muốn giữ DLT nhưng tạm dừng consumer của nó:

~~~java
RetryTopicConfigurationBuilder.newInstance()
    .maxAttempts(4)
    .autoStartDltHandler(false);
~~~

Những đoạn builder phía sau minh họa từng lựa chọn và cần gọi **create(kafkaTemplate)** khi đưa vào một bean RetryTopicConfiguration thực tế.

Với cấu hình builder toàn cục, hãy giới hạn phạm vi topic theo nhu cầu thực tế; đừng vô tình áp dụng chính sách NO_DLT cho một listener nghiệp vụ quan trọng. Không chồng cấu hình annotation và bean cho cùng listener khi chưa xác định cách framework chọn RetryTopicConfiguration.

## 11. @DltHandler: thành công, thất bại và xử lý nghiệp vụ

DLT handler không chỉ để log. Nó có thể lưu record vào hệ thống điều tra, gửi cảnh báo, đánh dấu ticket hoặc chuẩn bị thông tin cho quy trình re-drive.

Ví dụ một handler ghi vào database:

~~~java
@DltHandler
public void processDlt(OrderEvent event) {
    incidentService.recordFailure(event);
}
~~~

Điều quan trọng là **không bắt exception rồi chỉ log và trả về bình thường** khi thực tế chưa lưu được record:

~~~java
@DltHandler
public void unsafeDltHandler(OrderEvent event) {
    try {
        incidentService.recordFailure(event);
    }
    catch (RuntimeException exception) {
        log.error("Failed to persist DLT event", exception);
        // Listener trả về bình thường dù record chưa được lưu.
    }
}
~~~

Trong ví dụ sai này, Spring Kafka có thể xem DLT handler hoàn tất thành công. Khi đó DltStrategy không có exception để áp dụng. Record DLT vẫn còn trong Kafka theo retention, nhưng committed offset có thể tiến qua nó và hệ thống vận hành tưởng việc xử lý đã hoàn tất.

Cách an toàn hơn là ghi log và **ném lại exception**:

~~~java
@DltHandler
public void processDlt(OrderEvent event) {
    try {
        incidentService.recordFailure(event);
    }
    catch (RuntimeException exception) {
        log.error(
            "Cannot persist failed eventId={}",
            event.eventId(),
            exception
        );
        throw exception;
    }
}
~~~

Khi @DltHandler trả về bình thường, container áp dụng cơ chế acknowledgment/commit phù hợp. Khi handler ném exception, DltStrategy có thể xử lý lỗi theo chính sách đã chọn. Hãy bảo đảm phương thức ghi dữ liệu có ranh giới transaction rõ ràng và có thể chạy lặp.

## 12. Nếu không viết @DltHandler thì sao?

Khi không có method @DltHandler hoặc handler do builder chỉ định, framework có thể tạo **logging DLT handler** mặc định. Handler này ghi log thông tin nhận record DLT theo cơ chế mặc định.

Điều này hữu ích trong ví dụ đơn giản, nhưng có một hệ quả vận hành: **log thành công không có nghĩa record lỗi đã được lưu vào hệ thống điều tra hoặc được sửa**. Nếu consumer DLT mặc định đang chạy, committed offset có thể tiến lên khiến consumer lag của DLT thấp dù còn nhiều event nghiệp vụ chưa được giải quyết.

Nếu DLT là phần quan trọng của quy trình reliability, nên chủ động chọn một trong các cách:

- Có @DltHandler thực hiện một tác vụ idempotent và lưu trạng thái xử lý.
- Dùng builder dltHandlerMethod() để chỉ định bean/method chuyên trách.
- Tắt autoStartDltHandler và giao việc xử lý DLT cho một dịch vụ/đội vận hành riêng.

Không dùng “DLT lag bằng 0” làm bằng chứng tất cả lỗi nghiệp vụ đã được giải quyết.

## 13. Fatal exception và giới hạn của ALWAYS_RETRY_ON_ERROR

Một số lỗi có bản chất cố định: payload không đúng định dạng, method listener không nhận được tham số cần thiết hoặc chuyển đổi kiểu thất bại. Nếu DLT handler liên tục gặp cùng một lỗi như vậy, forward về DLT chỉ làm log tăng thêm.

Vì thế framework giữ một danh sách exception không được reforward theo chính sách ALWAYS_RETRY_ON_ERROR. Phân loại fatal exception có thể khác theo phiên bản và cấu hình bổ sung.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Không deserialize được | Dữ liệu JSON lỗi hoặc serializer mismatch | Sửa schema/deserialize configuration; xử lý bản gốc có kiểm soát |
| Không chuyển đổi message | Payload không khớp kiểu listener yêu cầu | Kiểm tra message converter và kiểu Java |
| Không resolve được tham số | Method signature hoặc header không tương thích | Sửa method listener/configuration |
| Class cast không hợp lệ | Sai type mapping | Sửa type information/consumer |
| Lỗi I/O tạm thời | Database hoặc network timeout | Có thể retry có giới hạn |
| Lỗi validation cố định | Thiếu trường bắt buộc | Cần sửa dữ liệu hoặc đưa vào quy trình điều tra |

Cần phân biệt **exception classification cho listener chính** (quyết định khi nào đưa record sang retry topic/DLT) với **fatal exception khi DLT handler lỗi** (quyết định có cho reforward DLT hay không). Đây là hai giai đoạn khác nhau.

Không coi việc DLT không bị reforward là sự bảo đảm record đã được xử lý. Cần xem exception, offset và trạng thái lưu trữ để biết record đang ở đâu.

## 14. Hành vi đối với offset, duplicate và idempotency

DltStrategy không tạo một transaction nguyên tử giữa Kafka và database bên ngoài. Có hai tình huống quan trọng:

**DLT handler ghi database thành công rồi ứng dụng dừng trước khi offset được commit.** Record DLT có thể được giao lại khi consumer restart. Nếu handler tạo ticket hoặc record incident mới mỗi lần, một event có thể tạo nhiều ticket.

**DLT handler thất bại sau khi side effect đã xảy ra, rồi ALWAYS_RETRY_ON_ERROR forward lại record.** Một bản DLT mới có thể được tạo dù side effect đã hoàn tất. Khi bản mới được xử lý, side effect có nguy cơ chạy lặp.

Cách thiết kế an toàn:

1. Gắn **eventId ổn định** cho sự kiện ngay từ đầu; giữ nguyên qua topic chính, retry topic và DLT.
2. Lưu eventId làm unique key khi tạo incident, ticket hoặc bản ghi inbox.
3. Đặt thao tác đánh dấu đã xử lý và cập nhật nghiệp vụ trong cùng database transaction khi có thể.
4. Với API bên ngoài, truyền idempotency key nếu dịch vụ đích hỗ trợ.
5. Ghi nhận topic, partition, offset DLT và số lần reforward để hỗ trợ điều tra.
6. Không dùng offset mới của bản DLT làm định danh duy nhất cho sự kiện nghiệp vụ.

Ví dụ về lưu incident idempotent:

~~~sql
BEGIN;

INSERT INTO failed_event(event_id, payload, received_at)
VALUES (:event_id, :payload, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

Ví dụ dùng cú pháp PostgreSQL. Với nghiệp vụ cần cập nhật trạng thái hoặc số lần xử lý, hãy thực hiện các thay đổi liên quan trong cùng transaction, và kiểm tra kết quả insert/upsert thay vì chỉ xem câu lệnh không ném lỗi.

## 15. Chọn chiến lược theo yêu cầu nghiệp vụ

| Nhu cầu | Lựa chọn cần cân nhắc | Điều kiện đi kèm |
|---|---|---|
| DLT handler chỉ gặp lỗi I/O ngắn hạn, muốn DLT tiếp tục tiêu thụ | ALWAYS_RETRY_ON_ERROR | Giám sát reforward, idempotent handler, kiểm soát retention |
| DLT handler cần báo lỗi cho operator, không muốn nhân bản record | FAIL_ON_ERROR | Error handling của DLT container, cảnh báo và re-drive |
| Tạm dừng xử lý DLT để điều tra thủ công | Có DLT + autoStartDltHandler="false" | Theo dõi tuổi/retention và có quy trình khởi động |
| Event có thể bỏ qua sau retry, có nguồn tái tạo | NO_DLT | Chấp nhận không có DLT và có metric cho lỗi cuối cùng |
| Thanh toán, đơn hàng hoặc nghiệp vụ cần kiểm toán | Có DLT, thường quản trị xử lý riêng | Lưu bền vững, idempotency, quyền truy cập và runbook |
| Một record DLT bị lỗi deserialize cố định | Xem fatal exception, sửa schema trước | Không tạo vòng lặp reforward |
| DLT xử lý được nhưng kho lưu sự cố lỗi kéo dài | FAIL_ON_ERROR hoặc tạm dừng DLT consumer | Khôi phục dependency trước khi xử lý tiếp |

Không cần chọn một DltStrategy duy nhất cho mọi nghiệp vụ. Một hệ thống có thể dùng chính sách khác nhau cho các listener hoặc nhóm topic, miễn là scope cấu hình rõ ràng.

## 16. Quan sát DLT trong production

Để vận hành DltStrategy an toàn, cần đo cả **số record vào DLT** và **số record được xử lý thành công**, không chỉ consumer lag.

Các metric nên có:

- Số record được gửi vào DLT từ retry topic mỗi phút.
- Số record được **forward lại từ DLT sang DLT** mỗi phút.
- Số eventId duy nhất trong DLT so với tổng số record.
- Số lần DLT handler thành công, thất bại, timeout.
- Số fatal exception không được reforward.
- Consumer lag và tuổi record cũ nhất của DLT group.
- Dung lượng, retention và tốc độ tăng của DLT.
- Số record được operator re-drive và kết quả sau re-drive.

Log nên bao gồm **eventId**, nguồn topic, nguồn partition/offset, topic DLT, DLT partition/offset, exception class, attempt, correlation ID và trạng thái lưu trữ. Có thể sử dụng headers do Spring Kafka bổ sung để truy tìm nguồn gốc record và lỗi cuối cùng; không giả định mọi version có cùng bộ headers.

Không đưa payload nhạy cảm vào log. Nếu cần lưu payload để điều tra, hãy áp dụng phân quyền và retention theo yêu cầu bảo mật dữ liệu.

### Cảnh báo cần ưu tiên

- DLT ingress tăng đột biến khi retry topic lỗi hàng loạt.
- DLT reforward rate không giảm sau khi dependency phục hồi.
- Cùng eventId xuất hiện nhiều lần liên tiếp.
- DLT handler thất bại liên tục theo một loại exception.
- DLT retention gần hết trước khi backlog được xử lý.
- DLT consumer không chạy theo kế hoạch hoặc có lag tăng nhanh.

## 17. Quy trình vận hành khi DLT gặp lỗi

Khi có cảnh báo lỗi xử lý DLT:

1. **Xác nhận chiến lược:** ALWAYS_RETRY_ON_ERROR, FAIL_ON_ERROR hay NO_DLT được gán cho listener đó.
2. **Xác định lỗi:** do payload, schema, database, quyền truy cập, serializer hay timeout.
3. **Xem eventId và headers:** phân biệt event mới với cùng event được forward nhiều lần.
4. **Kiểm tra lượng dữ liệu:** DLT ingress, reforward rate, oldest age và thời gian retention còn lại.
5. **Khoanh vùng tác động:** chỉ một event/partition hay toàn bộ DLT handler bị lỗi.
6. **Chặn vòng lặp có hại:** điều chỉnh lỗi gốc, giảm tải hoặc dừng có kiểm soát DLT container nếu cần.
7. **Khôi phục dependency hoặc sửa code:** xác nhận handler có thể xử lý một record mẫu.
8. **Re-drive có giới hạn:** giữ eventId cũ và bảo đảm idempotency.
9. **Theo dõi sau phục hồi:** tỷ lệ lỗi, reforward và backlog phải trở lại mức bình thường.
10. **Ghi nhận nguyên nhân gốc:** cải thiện classification, timeout, cấu hình DLT và cảnh báo.

Nếu đang dùng ALWAYS_RETRY_ON_ERROR và DLT có vòng lặp nhân bản vô hạn, chỉ tăng partition hoặc số consumer có thể làm hệ thống xử lý vòng lặp nhanh hơn. Hãy giải quyết lỗi handler và chính sách reforward trước.

## 18. Các kịch bản kiểm thử cần có

Những tình huống dưới đây giúp xác nhận hành vi ở ranh giới lỗi thực tế. Chạy trong môi trường tích hợp với Kafka và Spring Kafka đúng phiên bản triển khai:

1. **Đã hết retry của listener chính:** record đi vào DLT khi DLT được cấu hình.
2. **ALWAYS_RETRY_ON_ERROR + lỗi tạm thời:** DLT handler ném exception, record được publish lại vào DLT ở offset mới theo chính sách.
3. **ALWAYS_RETRY_ON_ERROR + fatal exception:** record không bị reforward thành vòng lặp theo danh sách fatal của phiên bản đang dùng.
4. **FAIL_ON_ERROR:** DLT handler lỗi; không có bản mới được forward theo DltStrategy; quan sát error handler và committed offset.
5. **NO_DLT:** retry hết lần mà không có DLT đích; xác nhận metric và cơ chế phục hồi thay thế.
6. **autoStartDltHandler="false":** record vẫn tới DLT nhưng listener DLT không chạy trước khi được start.
7. **DLT handler lỗi sau database commit:** record được giao lại hoặc reforward mà không tạo side effect trùng.
8. **DLT publisher lỗi:** không coi reforward đã thành công khi publish thất bại.
9. **Ứng dụng restart/rebalance:** xác nhận offset và idempotency khi DLT handler đang xử lý.
10. **DLT retention ngắn:** kiểm tra cảnh báo và quy trình lưu trữ dữ liệu lỗi trước khi hết retention.

Chỉ kiểm tra exception được ném chưa đủ; cần xác nhận topic đích, số bản record, offset, trạng thái nghiệp vụ và khả năng re-drive.

## 19. Các nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu phù hợp |
|---|---|---|
| DltStrategy quyết định retry của listener chính | Retry và DLT là hai giai đoạn khác nhau | Attempts/backoff điều khiển retry; DltStrategy điều khiển DLT |
| ALWAYS_RETRY_ON_ERROR luôn retry mọi lỗi | Fatal exception có thể không được reforward | Kiểm tra fatal classification theo phiên bản |
| FAIL_ON_ERROR có nghĩa record bị xóa | Không forward lại không đồng nghĩa xóa log Kafka | Xem container error handling và committed offset |
| NO_DLT tương đương tắt DLT consumer | NO_DLT không tạo DLT | Dùng autoStartDltHandler="false" nếu vẫn cần lưu lỗi |
| DLT lag thấp nghĩa lỗi đã xử lý xong | Default logging handler có thể chỉ ghi log rồi commit | Theo dõi trạng thái xử lý nghiệp vụ và unique event |
| @DltHandler bắt exception rồi log là an toàn | Framework có thể coi listener đã thành công | Ném lỗi lại nếu nghiệp vụ chưa bền vững |
| DLT record mới là một event nghiệp vụ mới | Reforward tạo offset khác cho cùng event | Giữ eventId ổn định, xử lý idempotent |
| Càng nhiều consumer DLT càng tốt | Có thể tăng tốc vòng lặp retry gây quá tải | Giới hạn tốc độ và sửa nguyên nhân lỗi |
| DLT thay thế backup | Retention có thể xóa record trước khi điều tra | Thiết kế lưu trữ và phục hồi theo SLA |

## 20. Kết nối DltStrategy với chiến lược reliability

Một hệ thống tin cậy cần trả lời được ba câu hỏi:

**Record lỗi đang ở đâu?** Trong topic chính, retry topic, DLT hay kho lưu sự cố riêng? Cần truy vết eventId và offset để định vị.

**Ai chịu trách nhiệm xử lý tiếp?** Framework tự retry, DLT handler tự ghi nhận, hay operator có trách nhiệm điều tra và re-drive? DltStrategy nên phản ánh đúng mô hình trách nhiệm đó.

**Khi xử lý lặp có an toàn không?** DLT reforward, restart, rebalance và timeout đều có thể tạo duplicate. Handler và các side effect cần idempotent trước khi chọn chính sách tự động reforward.

Với hệ thống nghiệp vụ quan trọng, thường nên có DLT, metric, cảnh báo, cơ chế lưu lỗi bền vững và quy trình xử lý thủ công khi không thể tự phục hồi. Với event tạm thời có thể tái tạo, NO_DLT đôi khi hợp lý. DltStrategy là một quyết định vận hành về cách record lỗi cuối cùng được lưu và xử lý, nên chọn dựa trên hậu quả mất dữ liệu, thứ tự xử lý, tải và khả năng phục hồi.

## 21. Tài liệu tham khảo

- Spring for Apache Kafka — DLT Strategies: https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html
- Spring for Apache Kafka — Retry Topic Configuration: https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html
- API DltStrategy: https://docs.spring.io/spring-kafka/docs/3.3.8/api/org/springframework/kafka/retrytopic/DltStrategy.html
- API RetryableTopic: https://docs.spring.io/spring-kafka/docs/3.3.8/api/org/springframework/kafka/annotation/RetryableTopic.html

**Ghi nhớ:** ALWAYS_RETRY_ON_ERROR giữ DLT tiến lên bằng cách có thể forward lại record lỗi vào DLT; FAIL_ON_ERROR không thực hiện reforward đó; NO_DLT không tạo DLT cho flow. Nếu muốn giữ DLT nhưng tạm dừng tự động xử lý, sử dụng autoStartDltHandler thay vì NO_DLT. Kết hợp mọi lựa chọn với idempotency, monitoring, retention phù hợp và quy trình phục hồi rõ ràng.
