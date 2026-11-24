# Tùy biến nguồn pollable bằng MessageSourceCustomizer

Trong Spring Cloud Stream, phần lớn consumer nhận message theo kiểu **message-driven**: binder đăng ký listener, broker chuyển message đến và framework gọi function hoặc consumer tương ứng. **Pollable consumer** hoạt động khác: ứng dụng chủ động yêu cầu lấy một message bằng `PollableMessageSource.poll(...)`. Cách này hữu ích khi công việc cần chạy theo lịch, khi ứng dụng phải giới hạn số lần lấy message, hoặc khi muốn phối hợp việc lấy dữ liệu với năng lực thực tế của hệ thống phía sau.

Khi kết nối pollable source với Kafka, RabbitMQ hoặc một binder khác, cấu hình thông thường vẫn nằm trong YAML. Nhưng đôi khi cần điều chỉnh một thuộc tính nâng cao trên **đối tượng `MessageSource` cụ thể** mà binder đã tạo. Spring Cloud Stream cung cấp `MessageSourceCustomizer<T>` để làm việc đó.

Bài học này tập trung vào cơ chế tùy biến source cho pollable binding, điểm gọi của customizer, ví dụ `AmqpMessageSource` với RabbitMQ, mối liên hệ giữa tùy biến source và mở rộng số poller, cùng cách tránh lỗi acknowledgement hoặc xử lý trùng. Ví dụ dùng mô hình Supplier/Function/Consumer và binding của Spring Cloud Stream, nhưng **polling chủ động do ứng dụng điều khiển**.

## 1. Phân biệt source, binding, binder và poller

| Khái niệm | Nhiệm vụ | Có tự quyết định lịch poll không? |
|---|---|---|
| **Binder** | Kết nối binding với middleware như Kafka hoặc RabbitMQ | Không quyết định lịch gọi `poll()` của ứng dụng |
| **Binding** | Ánh xạ tên input/output logic với destination và consumer group | Không |
| **`PollableMessageSource`** | API Spring Cloud Stream mà ứng dụng gọi để lấy một message | Không; chỉ thực hiện khi được gọi |
| **`MessageSource`** | Adapter nguồn thực tế do binder tạo, ví dụ `AmqpMessageSource` | Thường chỉ cung cấp cách nhận từ broker |
| **`MessageSourceCustomizer<T>`** | Tùy biến adapter nguồn sau khi binder đặt các thuộc tính ban đầu | Không |
| **Scheduler / poller của ứng dụng** | Quyết định khi nào và bao nhiêu lần gọi `poll()` | Có |

Một lỗi thiết kế thường gặp là khai báo customizer rồi kỳ vọng hệ thống sẽ tự poll nhanh hơn. Customizer được gọi khi cấu hình source; nó không phải scheduler và không xử lý từng message. Nếu cần thay chu kỳ polling hoặc số luồng, điều chỉnh bộ lập lịch, số instance và khả năng xử lý của broker/consumer.

## 2. Khi nào cần MessageSourceCustomizer?

Ưu tiên thuộc tính Spring Cloud Stream và binder ở YAML nếu chúng đã giải quyết yêu cầu. Dùng customizer khi cần API nâng cao của adapter nguồn mà cấu hình thông thường chưa bao phủ, ví dụ:

- Thay `MessagePropertiesConverter` cho pollable RabbitMQ source để kiểm soát cách chuyển đổi message properties và header từ AMQP.
- Thay `AmqpHeaderMapper` khi cần quy tắc ánh xạ header khác mặc định.
- Cung cấp một `MessageConverter` phù hợp với giao thức/format cần nhận tại adapter.
- Bật tùy chọn lấy raw AMQP message vào header để phục vụ điều tra lỗi, khi thực sự cần và đã cân nhắc chi phí dữ liệu.
- Áp dụng tùy biến cho một destination và group cụ thể, tránh ảnh hưởng các nguồn pollable khác.

Customizer **không** thay thế cấu hình connection, destination, group, retry, DLQ hoặc binder selection. Những thuộc tính có sẵn vẫn nên khai báo ở nơi chuẩn vì dễ kiểm tra và triển khai hơn.

## 3. Contract của MessageSourceCustomizer

Trong Spring Cloud Stream, interface nằm ở:

~~~java
org.springframework.cloud.stream.config.MessageSourceCustomizer<T>
~~~

Chữ ký cốt lõi:

~~~java
@FunctionalInterface
public interface MessageSourceCustomizer<T> {
    void configure(
        T source,
        String destinationName,
        String group
    );
}
~~~

Ý nghĩa ba tham số:

| Tham số | Ý nghĩa | Ứng dụng thường làm gì? |
|---|---|---|
| `source` | Đối tượng `MessageSource` do binder tạo | Gọi setter nâng cao được source hỗ trợ |
| `destinationName` | Tên destination gắn với source | Chọn cấu hình theo topic/exchange/queue logic |
| `group` | Consumer group được binding sử dụng | Giới hạn tùy biến cho nhóm xử lý mong muốn |

Theo JavaDoc, nếu có **một bean** `MessageSourceCustomizer` phù hợp trong application context, binder có thể gọi bean đó sau khi thiết lập các thuộc tính chuẩn cho pollable source. Callback là bước **cấu hình**, không phải callback mỗi lần nhận message. Nếu cấu hình mới ghi đè một setter mà binder vừa đặt, giá trị của customizer có thể trở thành giá trị hiệu lực: phải kiểm tra để tránh xung đột.

Trong ứng dụng có nhiều binder/source type, không giả định mọi binder đều tạo cùng một lớp adapter. Kiểu generic `T` phải phù hợp với implementation thực tế; ví dụ `AmqpMessageSource` dành cho Spring Integration AMQP, không thể ép Kafka source thành lớp đó. Chỉ định một customizer có phạm vi rõ và xác nhận hành vi trên phiên bản binder đang chạy.

## 4. Khai báo một pollable binding

Giả sử dịch vụ lập hóa đơn chỉ được lấy đơn hàng từ RabbitMQ khi đã sẵn sàng xử lý. Khai báo:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: ordersPoll
      bindings:
        ordersPoll-in-0:
          destination: orders.pending
          group: billing-worker
          binder: rabbit
app:
  polling:
    delay-ms: 250
~~~

Các thành phần có vai trò khác nhau:

- `spring.cloud.stream.pollable-source=ordersPoll` yêu cầu tạo nguồn pollable có tên logic `ordersPoll`.
- Binding được đặt tên `ordersPoll-in-0` theo quy ước input binding của mô hình hàm.
- `destination` là địa chỉ logic phía broker; với RabbitMQ binder, binder quản lý việc ánh xạ exchange/queue theo group và các thuộc tính Rabbit cụ thể.
- `group=billing-worker` giúp các instance thuộc cùng một nhóm tiêu thụ từ queue tương ứng, tùy semantics của binder.
- `binder=rabbit` chọn RabbitMQ binder. Có thể bỏ khi RabbitMQ là binder mặc định được chọn rõ ràng.
- `app.polling.delay-ms` là thuộc tính riêng của ứng dụng cho scheduler; nó không phải thuộc tính của `MessageSourceCustomizer`.

Ứng dụng cần dependency RabbitMQ binder tương thích Spring Cloud Stream. Cấu hình `pollable-source` chỉ tạo nguồn; **không tạo vòng lặp poll tự động**.

## 5. Poll chủ động bằng scheduler

Ví dụ class poller đọc từng message, thực hiện một bước nghiệp vụ rồi mới trả về. Giả định `InvoiceService` là service nghiệp vụ của dự án:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
class SchedulingConfiguration { }

@Component
class InvoicePollingTask {
    private final PollableMessageSource source;
    private final InvoiceService invoiceService;

    InvoicePollingTask(
        @Qualifier("ordersPoll-in-0") PollableMessageSource source,
        InvoiceService invoiceService
    ) {
        this.source = source;
        this.invoiceService = invoiceService;
    }

    @Scheduled(fixedDelayString = "${app.polling.delay-ms:250}")
    void pollOnce() {
        source.poll(message -> {
            invoiceService.createInvoice(message);
        });
    }
}
~~~

Với `fixedDelay`, lần chạy tiếp theo được lên lịch sau khi lần chạy hiện tại kết thúc. Hàm xử lý cần **hoàn tất công việc quan trọng trước khi callback kết thúc** nếu đang dựa vào cơ chế tự acknowledgement mặc định. Không chạy asynchronous fire-and-forget rồi lập tức trả về nếu downstream chưa hoàn tất và chưa có chiến lược acknowledgement riêng.

Scheduler này chủ động gọi một lần `poll()` cho mỗi lần kích hoạt. Nếu queue trống, poll trả về `false`, cho biết không có message nào được xử lý. Cần điều chỉnh lịch polling khi liên tục không có dữ liệu để tránh quá nhiều request rỗng.

## 6. Tùy biến AmqpMessageSource đúng điểm mở rộng

RabbitMQ binder hỗ trợ tùy biến pollable source thông qua `MessageSourceCustomizer<AmqpMessageSource>`. Trường hợp mẫu từ tài liệu Spring là thay `MessagePropertiesConverter`.

Đây là class cấu hình độc lập, có thể đặt trong package được Spring Boot component-scan:

~~~java
import org.springframework.amqp.rabbit.support.DefaultMessagePropertiesConverter;
import org.springframework.amqp.rabbit.support.MessagePropertiesConverter;
import org.springframework.cloud.stream.config.MessageSourceCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.inbound.AmqpMessageSource;

@Configuration(proxyBeanMethods = false)
class RabbitPollableSourceConfiguration {

    @Bean
    MessagePropertiesConverter pollingPropertiesConverter() {
        // LongString header <= 4096 bytes is converted to String.
        return new DefaultMessagePropertiesConverter(4096);
    }

    @Bean
    MessageSourceCustomizer<AmqpMessageSource> rabbitSourceCustomizer(
        MessagePropertiesConverter pollingPropertiesConverter
    ) {
        return (source, destinationName, group) -> {
            if ("orders.pending".equals(destinationName)
                    && "billing-worker".equals(group)) {
                source.setPropertiesConverter(pollingPropertiesConverter);
            }
        };
    }
}
~~~

Hành vi mong đợi:

1. Spring Cloud Stream cấu hình pollable binding `ordersPoll-in-0`.
2. Rabbit binder tạo adapter nguồn AMQP và áp dụng các thuộc tính chuẩn.
3. Framework gọi `configure(source, destinationName, group)` cho bean customizer.
4. Nếu destination và group khớp, adapter dùng converter do ứng dụng cung cấp.
5. Khi ứng dụng gọi `poll()`, message được lấy từ source đã cấu hình.

`DefaultMessagePropertiesConverter(4096)` chỉ minh họa một chính sách chuyển đổi header AMQP `LongString`. Giá trị mặc định thường chuyển các `LongString` không quá 1.024 byte thành `String`; giới hạn mới là 4.096 byte. Header lớn hơn ngưỡng có thể vẫn được giữ ở dạng `LongString`. Việc tăng ngưỡng có thể làm tăng memory allocation, nên phải có nhu cầu contract rõ ràng và kiểm thử trên payload/header thực tế.

Không nhầm `MessagePropertiesConverter` với content-type conversion của Spring Cloud Stream. Converter này thuộc Spring AMQP, xử lý properties ở ranh giới giao thức AMQP; việc biến payload JSON thành Java object còn phụ thuộc các message converter và cấu hình content type khác.

## 7. Tùy biến theo destination và group

Một ứng dụng có thể có nhiều pollable sources: queue xử lý đơn, queue đối soát và queue retry. Không nên áp dụng tùy biến chuyên biệt cho tất cả chỉ vì cùng dùng RabbitMQ.

~~~java
@Bean
MessageSourceCustomizer<AmqpMessageSource> scopedCustomizer(
    MessagePropertiesConverter converter
) {
    return (source, destinationName, group) -> {
        if (!"reconciliation.events".equals(destinationName)) {
            return;
        }
        if (!"reconciliation-worker".equals(group)) {
            return;
        }
        source.setPropertiesConverter(converter);
        source.setRawMessageHeader(true);
    };
}
~~~

Trong ứng dụng thực, **chỉ khai báo một bean** `MessageSourceCustomizer` cho phạm vi binder đang dùng. Đây là ví dụ thay thế cho bean ở mục trước, không phải bean cần thêm bên cạnh bean đó. Nếu muốn xử lý nhiều destination, dùng một callback rồi phân nhánh trong callback.

`setRawMessageHeader(true)` có thể đưa raw AMQP message vào header để phục vụ xử lý lỗi. Điều này hữu ích khi cần kiểm tra nguyên bản dữ liệu, nhưng làm tăng lượng dữ liệu giữ trong memory và nguy cơ ghi lộ payload/header nhạy cảm qua log/tracing. Chỉ bật cho trường hợp thực sự cần.

Không ghép `destinationName` và `group` thành một bean name hoặc giả định chúng luôn khác `null`. Với consumer group ẩn danh, group có thể không được khai báo. Dùng so sánh null-safe như `"billing-worker".equals(group)`.

## 8. Các setter nâng cao có thể cân nhắc trên AmqpMessageSource

`AmqpMessageSource` của Spring Integration có nhiều điểm mở rộng, nhưng mỗi điểm thay đổi một phần hành vi:

| API trên source | Mục đích | Lưu ý |
|---|---|---|
| `setPropertiesConverter(...)` | Chuyển `BasicProperties` của Rabbit client sang `MessageProperties` của Spring AMQP | Kiểm tra header đặc thù và chi phí chuyển đổi |
| `setHeaderMapper(...)` | Ánh xạ message properties sang Spring Integration headers | Không làm rơi correlation/tracing headers cần thiết |
| `setMessageConverter(...)` | Chuyển payload ở tầng Spring AMQP source | Tránh xung đột với content-type conversion của Spring Cloud Stream |
| `setRawMessageHeader(true)` | Đính kèm raw AMQP message | Tốn memory và cần bảo vệ dữ liệu |
| `setTransacted(true)` | Dùng AMQP channel transaction cho acknowledgement theo khả năng adapter | Không tạo transaction phân tán với database/Kafka |
| `setBatchingStrategy(...)` | Tùy biến de-batching khi dùng message đã batch | Cần đồng bộ với producer batching và error semantics |

Các API này thuộc lớp adapter của binder cụ thể. Không copy cấu hình RabbitMQ sang Kafka hoặc Pulsar. Khi API phiên bản thay đổi, đọc JavaDoc đúng phiên bản đang chạy và thử nghiệm trong integration test.

## 9. MessageSourceCustomizer khác gì ListenerContainerCustomizer?

Spring Cloud Stream còn có những hook khác, nhưng mỗi hook dùng cho một mục tiêu:

| Hook | Được gọi cho | Ví dụ |
|---|---|---|
| `MessageSourceCustomizer<T>` | Source được binder tạo cho **pollable consumer** | `AmqpMessageSource.setPropertiesConverter(...)` |
| `ListenerContainerCustomizer<T>` | Listener container cho **message-driven consumer** | Đặt advice chain hoặc thuộc tính listener container |
| `ConsumerEndpointCustomizer<E>` | Consumer endpoint do binder tạo | Điều chỉnh adapter endpoint theo API của implementation |
| `ProducerMessageHandlerCustomizer<H>` | Producer message handler | Tùy biến handler đẩy message ra broker |

Nếu consumer của bạn dùng `Function<String, String>` thông thường và framework gọi function mỗi khi broker giao message, hãy xem `ListenerContainerCustomizer` hoặc binding properties phù hợp. `MessageSourceCustomizer` chỉ có tác dụng ở đường xử lý pollable. Nếu pollable binding chưa được tạo, customizer dù được Spring khởi tạo cũng không giúp tạo ra nguồn polling.

## 10. Không nhầm lúc cấu hình với lúc chạy

Timeline điển hình:

~~~text
Application context start
  -> Binder resolves pollable binding and destination/group
  -> Binder creates underlying MessageSource
  -> Binder applies standard properties
  -> MessageSourceCustomizer.configure(source, destination, group)
  -> Application scheduler starts invoking PollableMessageSource.poll(...)
  -> Source receives one message per successful poll
  -> Handler completes; acknowledgment/error policy is applied
~~~

Hệ quả:

- Không đặt business processing hoặc gọi broker để lấy message bên trong `configure`.
- Không tăng một counter tên `messages.processed` từ callback này, vì một lần customizer được gọi không tương đương một message.
- Không dựa vào customizer để cập nhật delay của `@Scheduled`; scheduler là thành phần độc lập.
- Một binding có thể được tạo lại khi lifecycle thay đổi; không viết logic dựa trên giả định callback chỉ chạy đúng một lần trong cả đời JVM.
- Tùy biến nên là cấu hình ngắn, deterministic, không gây side effect khó hoàn tác và không giữ reference đến source sau khi nó không còn được quản lý.

## 11. Ack, reject và requeue khi polling

`PollableMessageSource.poll(handler)` xử lý từng message thông qua callback. Theo mặc định, khi handler kết thúc bình thường, message thường được acknowledge. Nếu handler ném lỗi, luồng error handling của Spring Cloud Stream có thể được kích hoạt.

Đặc biệt cần hiểu:

- Mỗi poll cố lấy **một message**; giá trị trả về cho biết có xử lý message hay không.
- Nếu handler ném exception, framework có thể gửi `ErrorMessage` đến channel `<destination>.<group>.errors` và global `errorChannel`.
- Nếu không có subscriber xử lý error channel, lỗi có thể chỉ được log và message vẫn được acknowledge như thành công. Không suy luận rằng một exception bất kỳ luôn gây requeue.
- `RequeueCurrentMessageException` là cách yêu cầu requeue current message theo cơ chế hỗ trợ của binder.
- `AcknowledgmentCallback.noAutoAck()` chuyển trách nhiệm ack/nack sang ứng dụng. Nếu đã dùng, phải hoàn tất ack hoặc nack; không để callback treo làm rò rỉ tài nguyên.

Ví dụ chủ động requeue lỗi tạm thời:

~~~java
@Scheduled(fixedDelayString = "${app.polling.delay-ms:250}")
void pollOnce() {
    source.poll(message -> {
        try {
            invoiceService.createInvoice(message);
        }
        catch (TemporaryDependencyException ex) {
            throw new RequeueCurrentMessageException(
                "Billing dependency is temporarily unavailable", ex);
        }
    });
}
~~~

Trong ví dụ trên, `TemporaryDependencyException` là exception nghiệp vụ do ứng dụng định nghĩa. Lỗi dữ liệu vĩnh viễn không nên requeue vô hạn; cần quy trình reject, DLQ, cảnh báo và điều tra riêng.

Với Kafka, cơ chế requeue liên quan offset và có thể khiến record đã xử lý sau đó bị giao lại. Với RabbitMQ, việc requeue có thể ảnh hưởng thứ tự và tạo vòng lặp redelivery. Tính idempotent, consumer group, partition và DLQ phải được kiểm thử bằng broker thật.

## 12. Khi nào cần manual acknowledgment?

Chỉ dùng manual ack khi có lý do cụ thể, chẳng hạn công việc được giao sang worker khác và chỉ có thể xác nhận sau khi worker hoàn tất.

~~~java
source.poll(message -> {
    AcknowledgmentCallback ack =
        StaticMessageHeaderAccessor.getAcknowledgmentCallback(message);
    ack.noAutoAck();

    // The application must later call acknowledge(ACCEPT,
    // REJECT or REQUEUE) on every path including failures.
    asyncWorker.submit(message, ack);
});
~~~

Đây là mẫu minh họa trách nhiệm, **không phải ví dụ production đầy đủ**: một worker thực phải xác định timeout, cách đóng ứng dụng, việc callback có an toàn khi ack ở thread khác và cách xử lý exception. Đừng thiết kế fire-and-forget nếu broker có thể xem message hoàn tất trước khi công việc thực sự được lưu.

Nếu một handler có thể hoàn tất đồng bộ, cách an toàn và đơn giản hơn thường là xử lý thành công rồi để framework tự ack.

## 13. Mở rộng poller: customizer không quyết định concurrency

Để tăng throughput pollable consumer, cần xem các giới hạn sau:

1. **Tốc độ polling.** Scheduler gọi source quá chậm thì broker còn message dù worker rảnh.
2. **Thời gian xử lý.** Nếu mỗi poll xử lý đồng bộ 500 ms, một poller đơn chỉ có thể hoàn tất khoảng hai message/giây, chưa tính thời gian broker.
3. **Số poller/instance.** Có thể tăng instance, nhưng phải hiểu cách binder và broker phân phối công việc.
4. **Broker capacity.** Rabbit queue, Kafka partition hoặc network có thể trở thành nút thắt.
5. **Downstream limits.** Database, API, thread pool và memory có thể không chịu được concurrency quá cao.

Ví dụ một poller mất trung bình 40 ms để xử lý một message và không có delay đáng kể. Capacity đơn luồng lý thuyết khoảng 25 message/giây. Nếu thêm 200 ms delay sau mỗi lần xử lý, throughput thấp hơn rõ rệt. Không thể tăng tốc bằng cách đổi `setPropertiesConverter(...)`; phải thay lịch, tăng song song hợp lệ hoặc tối ưu công việc.

Với RabbitMQ queue, nhiều instance trong cùng nhóm có thể cạnh tranh nhận message từ queue; cần kiểm tra thực tế, nhất là khi tạo nhiều request rỗng. Với Kafka, partition và consumer group/offset giới hạn song song. Không tự gọi đồng thời `poll()` trên cùng một source từ nhiều thread nếu binder không bảo đảm thread safety và acknowledgement semantics. Khi cần mở rộng, ưu tiên scale instance có ranh giới consumer rõ ràng và benchmark.

## 14. Lịch polling và chiến lược giảm poll rỗng

Khi queue hầu như trống, một vòng lặp `while(true)` không nghỉ có thể gây tải không cần thiết lên broker và CPU. Một lựa chọn là fixed delay có giới hạn; nếu lịch cần nhanh khi có message và chậm khi không có message, dùng scheduler động hoặc backoff có kiểm soát.

~~~java
boolean received = source.poll(message -> handle(message));
if (received) {
    // Record one successfully handled poll; next run can be sooner.
}
else {
    // No message available; wait according to an idle backoff policy.
}
~~~

Đừng `Thread.sleep` lâu trong callback nếu đang chiếm thread dùng chung cho nhiều poller. Với `@Scheduled`, ưu tiên thay đổi interval bằng cấu hình và quan sát số lần poll rỗng. Nếu dùng nhiều poller trên cùng node, thiết lập scheduler thread pool một cách có kiểm soát và bảo đảm từng nguồn có ranh giới concurrency rõ ràng.

## 15. Quan sát và đặt SLO cho pollable pipeline

Cần đo ít nhất:

| Chỉ số | Mục đích | Vị trí đo |
|---|---|---|
| `poll.attempts` | Số lần ứng dụng gọi poll | Scheduler quanh `poll()` |
| `poll.empty` | Tỷ lệ poll rỗng | Khi `poll()` trả `false` |
| `poll.handled` | Message xử lý hoàn tất | Sau callback xử lý thành công |
| `poll.duration` | Thời gian poll + xử lý | Timer quanh lời gọi `poll()` |
| `poll.errors` | Lỗi khi nhận/xử lý | Error handler và log có correlation |
| Queue depth / consumer lag | Backlog broker còn lại | RabbitMQ/Kafka monitoring |
| Oldest-message age | Thời gian message bị chờ | Broker/metadata và timestamp |
| Redelivery / DLQ count | Khả năng phục hồi, lỗi lặp | Broker và error pipeline |

Đừng cộng số lần customizer được gọi vào `poll.handled`. Customizer chỉ chạy ở vòng đời cấu hình. Tránh gắn message ID, customer ID hoặc raw payload thành metric label vì cardinality lớn và nguy cơ lộ dữ liệu. Dùng tên destination/group đã chuẩn hóa, có giới hạn số giá trị, nếu phù hợp chính sách observability.

Ví dụ yêu cầu: xử lý tối thiểu 100 message/giây, p95 từ lúc broker nhận đến lúc hoàn tất dưới 2 giây, tỷ lệ poll rỗng không vượt ngưỡng chi phí hạ tầng, và không mất dữ liệu được acknowledge. Tất cả mục tiêu này phải được đo ở môi trường có broker thật, dưới tải thực tế.

## 16. Kiểm thử customizer bằng các lớp test phù hợp

Có thể chia kiểm thử thành ba tầng:

**Tầng 1 — Kiểm thử logic cấu hình**

- Tạo `AmqpMessageSource` thích hợp hoặc dùng mock rồi gọi callback `configure(source,destination,group)`.
- Xác nhận setter `setPropertiesConverter` chỉ được gọi khi destination và group trùng khớp.
- Xác nhận destination/group khác không bị tác động.
- Xác nhận customizer không phụ thuộc vào dữ liệu runtime hoặc side effect.

**Tầng 2 — Kiểm thử xử lý message**

- Dùng Spring Cloud Stream Test Binder để kiểm tra mã gọi `PollableMessageSource.poll()`, mapping payload và cách xử lý thành công/lỗi.
- Test Binder dùng nguồn mô phỏng trong JVM; nó **không xác minh** rằng RabbitMQ binder thật đã tạo `AmqpMessageSource` và áp dụng customizer.

**Tầng 3 — Integration test với RabbitMQ thật**

- Khởi động RabbitMQ trong Testcontainers hoặc broker test riêng và chạy ứng dụng với Rabbit binder.
- Xác minh callback được gọi cho đúng destination/group khi binding được tạo.
- Publish message có header `LongString` ở các kích thước hai bên ngưỡng đã chọn.
- Poll message và kiểm tra header/payload thực nhận; đo memory và latency khi header lớn.
- Thử xử lý thành công, lỗi tạm thời gây requeue, lỗi vĩnh viễn, restart và duplicate.
- Chạy nhiều instance/poller hợp lệ và xác nhận throughput, phân phối message và queue depth.

Không kết luận customizer hoạt động trên broker chỉ từ test unit với mock hoặc Test Binder. Phần triển khai thật cần ít nhất một integration test qua binder đích.

## 17. Lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `rabbitSourceCustomizer` không được gọi | Không khai báo pollable binding hoặc binder không tạo loại source mong đợi | Kiểm tra `pollable-source`, binder type và lifecycle |
| App khởi động nhưng không nhận message | Không có scheduler nào gọi `poll()` | Bật scheduling và gọi poll chủ động |
| Setter không có hiệu lực | Destination/group filter không khớp hoặc implementation khác | Kiểm tra callback arguments và JavaDoc source thực tế |
| Chỉnh delay trong customizer nhưng poll vẫn như cũ | Lịch poll nằm ở scheduler, không ở source customizer | Cấu hình scheduler riêng |
| Mất header sau chuyển đổi | `MessagePropertiesConverter` hoặc header mapper không phù hợp | Test header mapping của RabbitMQ |
| Raw message xuất hiện trong log/trace | Bật `setRawMessageHeader(true)` rồi log toàn bộ headers | Tắt raw header hoặc lọc log/tracing |
| Lỗi bị log nhưng message không redeliver | Luồng error channel đã xử lý như thành công | Dùng requeue/ack strategy rõ ràng, test với broker |
| Queue đầy dù CPU rảnh | Poll quá thưa hoặc scheduler thiếu thread | Đo empty rate, interval và throughput thực |
| CPU/network tăng khi traffic thấp | Poll vòng lặp quá nhanh, nhiều request rỗng | Thêm idle backoff và giám sát |
| Duplicate khi scale/restart | Ack không gắn với hoàn tất công việc hoặc requeue | Áp dụng idempotency và kiểm tra offset/ack policy |
| Customizer bean xung đột | Nhiều bean cùng loại trong context hoặc generic type không phù hợp | Gom logic vào một bean và kiểm tra binder hỗ trợ |

## 18. Bài thực hành có thể tự làm

Xây dựng một dịch vụ lấy lệnh thanh toán từ RabbitMQ theo chu kỳ:

1. Tạo project Spring Boot có Spring Cloud Stream RabbitMQ binder và Scheduling.
2. Khai báo `pollable-source=paymentsPoll`, binding `paymentsPoll-in-0`, destination `payments.pending`, group `payment-worker`.
3. Viết scheduler gọi `PollableMessageSource.poll()` sau mỗi 250 ms.
4. Thêm `MessageSourceCustomizer<AmqpMessageSource>` với một `DefaultMessagePropertiesConverter(4096)` chỉ cho destination/group đó.
5. Gửi 100 message có header thường và một số message chứa header `LongString` lớn.
6. Xác nhận mỗi message được xử lý và acknowledgement theo policy dự kiến.
7. Tăng nhịp poll, đo throughput, CPU, poll rỗng và p95 latency.
8. Chạy thêm một instance; quan sát queue depth và kiểm tra không có nghiệp vụ được thực thi hai lần khi cùng event bị redeliver.
9. Giả lập một lỗi tạm thời với `RequeueCurrentMessageException`, rồi xác minh message xử lý lại đúng.
10. Thêm một pollable destination khác và xác nhận customizer không sửa source ngoài phạm vi.

Tiêu chí hoàn thành: callback customizer chỉ nhận đúng source đích, polling được điều khiển bởi scheduler, header chuyển đổi đúng, ứng dụng xử lý được lỗi và replay không làm sai kết quả nghiệp vụ.

## 19. Checklist trước khi triển khai

- [ ] Đã chọn pollable consumer vì có yêu cầu polling chủ động, thay vì dùng nó để thay thế message-driven consumer theo thói quen.
- [ ] Binding `<name>-in-0`, destination, group và binder được khai báo chính xác.
- [ ] Có scheduler/poller thực sự gọi `poll()` và có giới hạn tần suất.
- [ ] `MessageSourceCustomizer` được dùng cho thuộc tính nâng cao chưa được cấu hình bằng YAML.
- [ ] Generic `T` đúng với source implementation của binder.
- [ ] Chỉ có một customizer phù hợp trong context hoặc đã xác minh cơ chế chọn bean.
- [ ] Có lọc destination/group null-safe, tránh tác động nguồn khác.
- [ ] Callback không xử lý business message, không tạo thread hoặc giữ reference source không cần thiết.
- [ ] Đã phân biệt AMQP properties converter với content-type converter của Spring Cloud Stream.
- [ ] Đã đánh giá ảnh hưởng memory, raw header và dữ liệu nhạy cảm.
- [ ] Ack/requeue, error channel và DLQ đã được kiểm thử với broker thật.
- [ ] Đã đo poll rỗng, throughput, p95 latency, backlog và redelivery khi mở rộng.
- [ ] Có integration test đúng binder thay vì chỉ dựa trên Test Binder.
- [ ] Đã xác nhận phiên bản Spring Cloud Stream, Spring Integration và binder hỗ trợ API đang sử dụng.

`MessageSourceCustomizer` là điểm mở rộng để tùy biến adapter nguồn **sau khi** binder áp dụng các thuộc tính chuẩn. Với pollable RabbitMQ consumer, có thể gắn một `MessagePropertiesConverter` vào `AmqpMessageSource` cho đúng destination và group. Tuy nhiên, **chu kỳ poll, mức song song và tính đúng đắn của acknowledgement vẫn do ứng dụng cùng binder/broker quyết định**. Muốn scale an toàn, phải kết hợp customizer có phạm vi rõ, scheduler có giới hạn, idempotency và quan sát backlog/latency trên broker thật.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Properties, Advanced Consumer Configuration](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Using Polled Consumers](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream 5.0.2 API — MessageSourceCustomizer](https://javadoc.io/static/org.springframework.cloud/spring-cloud-stream/5.0.2/spring.cloud.stream/org/springframework/cloud/stream/config/MessageSourceCustomizer.html)
- [Spring Integration 6.5.2 API — AmqpMessageSource](https://docs.spring.io/spring-integration/docs/6.5.2/api/org/springframework/integration/amqp/inbound/AmqpMessageSource.html)
- [Spring AMQP — Message Properties Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html)
