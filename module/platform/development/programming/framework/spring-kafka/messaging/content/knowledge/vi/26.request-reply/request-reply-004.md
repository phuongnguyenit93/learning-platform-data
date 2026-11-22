# Reply topic và reply container

## 1. Request-reply trong Kafka hoạt động như thế nào?

Kafka chủ yếu hỗ trợ trao đổi bất đồng bộ: producer ghi record vào topic, consumer xử lý khi nhận được dữ liệu và không cần phản hồi ngay cho producer. Tuy nhiên, một số nghiệp vụ cần gửi yêu cầu rồi chờ kết quả, chẳng hạn tra cứu trạng thái đơn hàng, kiểm tra hạn mức hoặc yêu cầu một dịch vụ tính toán.

Request-reply trên Kafka mô phỏng mô hình hỏi-đáp bằng hai luồng record:

- Request được gửi vào request topic.
- Service xử lý request đọc record và phát response vào reply topic.
- Bên gửi lắng nghe reply topic, ghép response với request ban đầu rồi trả kết quả cho caller.

Kafka không tự tạo quan hệ giữa request và response. Ứng dụng cần một correlation ID cho mỗi request, truyền ID đó trong header của request và yêu cầu responder giữ nguyên ID trong response. Nếu thiếu correlation ID hoặc responder làm thay đổi giá trị này, bên gọi không thể ghép đúng response với lời gọi đang chờ.

Spring Kafka cung cấp `ReplyingKafkaTemplate` để gửi request và chờ response, cùng reply container để tiêu thụ các response. Ở phía responder, `@KafkaListener` kết hợp `@SendTo` có thể xử lý request và gửi kết quả về reply topic.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as ReplyingKafkaTemplate
    participant R as Request topic
    participant S as Responder
    participant P as Reply topic
    C->>T: sendAndReceive(request)
    T->>R: Request + correlation ID + reply destination
    S->>R: Poll request
    S->>S: Xử lý nghiệp vụ
    S->>P: Response + correlation ID
    T->>P: Reply container nhận response
    T->>T: Ghép correlation ID
    T-->>C: RequestReplyFuture hoàn tất
~~~

Request-reply vẫn là giao tiếp bất đồng bộ ở tầng Kafka. `ReplyingKafkaTemplate` cung cấp abstraction để caller chờ kết quả, nhưng request và response vẫn là hai Kafka record độc lập.

## 2. Phân biệt reply topic và reply container

**Reply topic** là topic Kafka chứa các response. Responder gửi response vào topic này sau khi xử lý request. Topic cần được tạo và cấu hình partition, replication, retention, ACL phù hợp.

**Reply container** là consumer container chuyên đọc reply topic. `ReplyingKafkaTemplate` nhận container này trong constructor, đăng ký listener nội bộ để nhận response và đối chiếu correlation ID với các request đang chờ.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Request topic | Nhận yêu cầu | `order-lookup.requests` |
| Reply topic | Chứa phản hồi | `order-lookup.replies` |
| Request listener | Xử lý yêu cầu | `@KafkaListener` trên request topic |
| Reply container | Đọc response | `ConcurrentMessageListenerContainer` |
| Correlation ID | Ghép response với request | `KafkaHeaders.CORRELATION_ID` |
| Reply destination | Cho responder biết nơi gửi response | `KafkaHeaders.REPLY_TOPIC` |

Reply container không phải listener nghiệp vụ thông thường. Nó được `ReplyingKafkaTemplate` dùng để hoàn tất các future đang chờ. Không gắn thêm listener nghiệp vụ có thể tiêu thụ mất response trên cùng container.

## 3. Các header dùng trong request-reply

Spring Kafka sử dụng header để truyền thông tin điều khiển request-reply:

| Header | Hướng | Ý nghĩa |
|---|---|---|
| `KafkaHeaders.CORRELATION_ID` | Request và reply | ID dùng để ghép response với request |
| `KafkaHeaders.REPLY_TOPIC` | Request | Topic mà responder gửi response đến |
| `KafkaHeaders.REPLY_PARTITION` | Request | Partition đích của response nếu được chỉ định |
| `KafkaHeaders.RECEIVED_KEY` | Nhận | Key của record được nhận |
| `KafkaHeaders.RECEIVED_TOPIC` | Nhận | Topic chứa record |
| `KafkaHeaders.RECEIVED_PARTITION` | Nhận | Partition chứa record |

`ReplyingKafkaTemplate` tạo correlation ID và thêm thông tin reply destination vào request. Responder Spring Kafka có thể đọc các header này và gửi response với correlation ID tương ứng.

Khi dùng `@SendTo` cố định, topic đích được xác định bởi annotation. Khi cần reply topic khác nhau theo từng request, responder có thể dùng `KafkaHeaders.REPLY_TOPIC` được gửi trong request. Không lấy reply topic từ payload hoặc header tùy ý mà chưa xác thực; responder chỉ nên gửi đến topic nằm trong allowlist mà dịch vụ được phép ghi.

Header Kafka có giá trị byte. Với Spring Message hoặc converter, cách ánh xạ header phụ thuộc cấu hình header mapper. Khi dùng request-reply của Spring Kafka, để template và listener adapter xử lý các header framework. Nếu tự tạo `ProducerRecord`, cần dùng đúng tên header và kiểu byte mà API yêu cầu.

## 4. Cấu hình reply container

Reply container cần consumer factory có key/value deserializer tương thích với kiểu response. Ví dụ dưới đây dùng key và response đều là `String`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;

@Configuration
public class RequestReplyConfiguration {

    @Bean
    ConcurrentMessageListenerContainer<String, String> repliesContainer(
            ConcurrentKafkaListenerContainerFactory<String, String>
                    kafkaListenerContainerFactory) {

        var container =
            kafkaListenerContainerFactory.createContainer(
                "order-lookup.replies"
            );

        container.getContainerProperties().setGroupId(
            "order-lookup-reply-client"
        );

        return container;
    }
}
~~~

`createContainer()` tạo container chuyên dùng cho reply topic. `setGroupId()` đặt consumer group cho reply container; group này cần được chọn theo topology triển khai, đặc biệt khi có nhiều instance requester.

Trong ví dụ một instance, group ID có thể là `order-lookup-reply-client`. Khi triển khai nhiều instance, không nên để mọi instance chia sẻ một reply consumer group nếu mỗi instance phải nhận response dành cho request đang chờ ở chính instance đó. Phần nhiều instance được giải thích ở mục 11.

Reply container phải chạy trước khi request được gửi để tránh response đến trước khi consumer bắt đầu lắng nghe. Spring quản lý vòng đời container thông qua bean lifecycle; ứng dụng nên chỉ nhận request sau khi reply container đã sẵn sàng. Không tắt auto startup trừ khi ứng dụng chủ động khởi động container đúng thời điểm.

## 5. Khai báo ReplyingKafkaTemplate

Sau khi có reply container, tạo `ReplyingKafkaTemplate` bằng producer factory và container đó:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.requestreply.ReplyingKafkaTemplate;

@Configuration
public class RequestReplyTemplateConfiguration {

    @Bean
    ReplyingKafkaTemplate<String, String, String> replyingKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            ConcurrentMessageListenerContainer<String, String>
                    repliesContainer) {

        var template = new ReplyingKafkaTemplate<>(
            producerFactory,
            repliesContainer
        );

        template.setDefaultReplyTimeout(Duration.ofSeconds(8));
        return template;
    }
}
~~~

Generic của template có dạng `ReplyingKafkaTemplate<K, V, R>`:

- `K`: kiểu key của request.
- `V`: kiểu value của request.
- `R`: kiểu value của response.

Ví dụ trên dùng `String` cho cả ba kiểu. Producer factory phải serialize được request; reply container phải deserialize được response. Nếu request và response dùng định dạng khác nhau, cấu hình producer factory và consumer factory tương ứng thay vì ép mọi payload về cùng một kiểu.

`setDefaultReplyTimeout(Duration)` đặt thời gian chờ mặc định cho response. Timeout chỉ giới hạn thời gian caller chờ; nó không hủy request đã được gửi vào Kafka và không dừng responder đang xử lý.

## 6. Gửi request và nhận response

`ReplyingKafkaTemplate.sendAndReceive()` nhận một `ProducerRecord` và trả về `RequestReplyFuture`. Future này cung cấp cả kết quả gửi request và kết quả reply.

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.requestreply.ReplyingKafkaTemplate;
import org.springframework.kafka.requestreply.RequestReplyFuture;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {

    private final ReplyingKafkaTemplate<String, String, String> template;

    public OrderLookupClient(
            ReplyingKafkaTemplate<String, String, String> template) {
        this.template = template;
    }

    public String lookup(String orderId) throws Exception {
        var request = new ProducerRecord<>(
            "order-lookup.requests",
            orderId,
            orderId
        );

        RequestReplyFuture<String, String, String> future =
            template.sendAndReceive(request);

        SendResult<String, String> sendResult =
            future.getSendFuture().get(5, TimeUnit.SECONDS);

        var replyRecord = future.get(8, TimeUnit.SECONDS);

        log.info(
            "Request đã được xác nhận topic={} partition={} offset={}",
            sendResult.getRecordMetadata().topic(),
            sendResult.getRecordMetadata().partition(),
            sendResult.getRecordMetadata().offset()
        );

        return replyRecord.value();
    }
}
~~~

Có hai kết quả cần phân biệt:

- `future.getSendFuture()` hoàn tất khi producer nhận kết quả gửi request theo cấu hình `acks`.
- `future.get()` hoàn tất khi reply container nhận được response có correlation ID khớp với request đang chờ.

Request gửi thành công không đồng nghĩa responder đã xử lý xong. Reply timeout cũng không đồng nghĩa request chưa được gửi. Trong ví dụ, thời gian chờ send là 5 giây và thời gian chờ reply là 8 giây; chọn giới hạn phù hợp với SLA thực tế.

Không dùng offset request như offset response vì hai record nằm ở hai topic khác nhau. Nếu cần log response, đọc metadata từ `replyRecord` hoặc các header nhận được.

## 7. Responder với @KafkaListener và @SendTo

Ở phía xử lý, listener đọc request, thực hiện nghiệp vụ và trả về payload response. `@SendTo` xác định reply topic cố định:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class OrderLookupResponder {

    private final OrderQueryService orderQueryService;

    public OrderLookupResponder(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @KafkaListener(
        topics = "order-lookup.requests",
        groupId = "order-lookup-responder",
        containerFactory = "requestListenerContainerFactory"
    )
    @SendTo("order-lookup.replies")
    public String handle(String orderId) {
        return orderQueryService.findStatus(orderId);
    }
}
~~~

Khi listener trả về payload, Spring Kafka gửi payload đó đến topic trong `@SendTo`. Correlation ID của request được giữ trong reply để `ReplyingKafkaTemplate` ghép đúng response.

Listener factory cần có reply template để gửi response. Có thể gắn template vào `ConcurrentKafkaListenerContainerFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
        requestListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                KafkaTemplate<String, String> replyTemplate) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setReplyTemplate(replyTemplate);
    return factory;
}
~~~

`replyTemplate` là template phía responder dùng để phát response. Nó cần serializer phù hợp với kiểu response và được cấu hình trong container factory. `ReplyingKafkaTemplate` ở requester và `replyTemplate` ở responder có vai trò khác nhau: một bên gửi request/chờ reply, bên kia gửi response.

### Thiết kế response lỗi

Nếu listener ném exception trước khi trả về payload, `@SendTo` không tự tạo một error response theo hợp đồng nghiệp vụ. Caller thường tiếp tục chờ cho đến khi reply timeout, trong khi listener container xử lý exception theo error handler của nó.

Nếu caller cần nhận cả kết quả thành công và thất bại nghiệp vụ, hãy định nghĩa response envelope có trường trạng thái rõ ràng, ví dụ `status`, `result` và `errorCode`. Responder có thể bắt các lỗi nghiệp vụ đã dự kiến và trả envelope thất bại; lỗi hạ tầng hoặc lỗi lập trình vẫn nên đi qua retry/error handler theo chính sách. Không gửi stack trace, secret hoặc exception message nội bộ nguyên vẹn cho caller.

## 8. Dùng reply topic được chỉ định trong request

Một hệ thống có thể có nhiều requester hoặc nhiều loại request. Thay vì cố định reply topic trong `@SendTo`, responder có thể gửi reply về topic trong header `KafkaHeaders.REPLY_TOPIC`.

Ví dụ listener trả về response mà không chỉ định topic trong annotation:

~~~java
@KafkaListener(
    topics = "order-lookup.requests",
    groupId = "order-lookup-responder",
    containerFactory = "requestListenerContainerFactory"
)
@SendTo
public OrderStatusReply handle(OrderLookupRequest request) {
    return orderQueryService.lookup(request.orderId());
}
~~~

Với request được tạo bởi `ReplyingKafkaTemplate`, header reply topic được gửi kèm request. Listener adapter dùng reply template và thông tin header này để gửi response đến đúng topic.

Nếu ứng dụng muốn dùng một topic cố định cho mọi requester, `@SendTo("order-lookup.replies")` dễ đọc và dễ cấu hình hơn. Nếu dùng reply topic động, hãy giới hạn topic đích theo allowlist, cấp ACL tối thiểu và không tin giá trị do client bất kỳ tự gửi.

Khi annotation chỉ rõ topic, đó là destination được khai báo cho listener. Chọn một chiến lược rõ ràng cho từng listener, tránh vừa cấu hình topic cố định vừa giả định header reply topic động sẽ luôn được ưu tiên.

## 9. Correlation ID và cách ghép response

`ReplyingKafkaTemplate` theo dõi các request đang chờ bằng correlation ID. Khi gửi request, template thêm correlation header; response phải mang lại cùng giá trị đó.

Nếu tự tạo response bằng `KafkaTemplate` thay vì dùng cơ chế reply của listener adapter, cần sao chép correlation header từ request sang response:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.support.KafkaHeaders;

public ProducerRecord<String, OrderStatusReply> createReply(
        ConsumerRecord<String, OrderLookupRequest> request,
        OrderStatusReply reply) {

    var response = new ProducerRecord<>(
        "order-lookup.replies",
        request.key(),
        reply
    );

    Header correlationId =
        request.headers().lastHeader(KafkaHeaders.CORRELATION_ID);

    if (correlationId != null) {
        response.headers().add(
            KafkaHeaders.CORRELATION_ID,
            correlationId.value()
        );
    }

    return response;
}
~~~

Nếu correlation ID không được trả lại hoặc bị thay đổi, template không thể hoàn tất đúng future. Request sẽ hết thời gian chờ dù responder có thể đã xử lý xong và gửi response.

Correlation ID không phải event ID hay business ID. Một order ID có thể xuất hiện trong nhiều request khác nhau; mỗi lần request cần correlation ID riêng để phân biệt các lần gọi đồng thời.

## 10. Timeout, lỗi và response đến muộn

Request-reply phải có timeout hữu hạn. Nếu không có timeout, caller có thể chờ vô thời hạn khi responder dừng, reply bị mất hoặc correlation header sai.

| Tình huống | Kết quả phía requester | Hành động |
|---|---|---|
| Request không gửi được | Send future thất bại | Xử lý lỗi producer và quyết định retry gửi |
| Request gửi thành công nhưng responder không xử lý | Reply future timeout | Kiểm tra consumer lag, responder và request topic |
| Responder xử lý nhưng không gửi reply | Reply future timeout | Kiểm tra reply template, ACL và exception |
| Reply được gửi nhưng correlation ID sai | Future tương ứng không hoàn tất | Kiểm tra header correlation ở hai phía |
| Reply đến sau timeout | Caller đã ngừng chờ | Template không còn request đang chờ để ghép; response không được sử dụng bởi lời gọi đã timeout |
| Caller timeout rồi gửi request mới | Có thể có hai request cùng thực hiện nghiệp vụ | Dùng request ID ổn định/idempotency key cho side effect |

Timeout ở requester không hủy record trong Kafka. Responder vẫn có thể xử lý và phát reply sau đó. Nếu nghiệp vụ có side effect, retry request có thể thực hiện cùng thao tác nhiều lần; cần idempotency key hoặc deduplication ở responder.

Các request đang chờ được `ReplyingKafkaTemplate` theo dõi trong bộ nhớ của instance. Nếu requester restart, mapping correlation ID và future đang chờ không được khôi phục chỉ từ reply topic. Response cũ vẫn có thể được lưu trong Kafka nhưng không còn future cũ để hoàn tất; nếu nghiệp vụ cần phục hồi sau restart, hãy lưu request ID và trạng thái chờ ở kho bền vững rồi thiết kế cơ chế đối soát riêng.

`setDefaultReplyTimeout()` đặt thời gian chờ mặc định cho template. Nếu cần timeout khác nhau theo từng request, kiểm tra overload `sendAndReceive(record, Duration)` trong phiên bản Spring Kafka đang dùng; API overload có thể khác theo phiên bản. Dù chọn cách nào, vẫn cần timeout hữu hạn ở caller.

## 11. Nhiều instance requester và shared reply topic

Khi chạy nhiều instance của cùng requester service, cách dùng reply topic ảnh hưởng trực tiếp đến việc response có đến đúng instance đang chờ hay không.

### Mỗi instance có reply topic riêng

Ví dụ:

- Instance A lắng nghe `order-lookup.replies.A`.
- Instance B lắng nghe `order-lookup.replies.B`.

Mỗi requester chỉ tiêu thụ reply của mình. Cách này dễ hiểu và tránh việc instance khác lấy mất response, nhưng cần quản lý topic, ACL và partition theo instance hoặc theo nhóm triển khai có vòng đời rõ ràng. Không tạo topic mới theo từng request.

### Dùng một shared reply topic

Nhiều instance có thể dùng chung một reply topic nếu mỗi instance có reply consumer group riêng để từng instance nhận được bản sao của mọi reply. Mỗi `ReplyingKafkaTemplate` chỉ hoàn tất future có correlation ID mà nó đang theo dõi; reply dành cho instance khác được bỏ qua.

Bật chế độ shared reply topic trên template:

~~~java
template.setSharedReplyTopic(true);
~~~

Nếu nhiều instance dùng cùng một consumer group trên reply topic, Kafka phân phối mỗi record cho một instance trong group. Response có thể đến instance không sở hữu request đang chờ; requester đúng sẽ không nhận được response và cuối cùng timeout.

Với shared topic, cần đánh giá lượng traffic nhân bản cho từng instance: mỗi instance nhận tất cả reply, dù chỉ một phần thuộc về nó. Nếu số instance hoặc throughput lớn, reply topic riêng hoặc chiến lược partition routing có thể phù hợp hơn.

## 12. Reply partition và định tuyến response

`KafkaHeaders.REPLY_PARTITION` cho phép requester chỉ định partition mà responder cần dùng khi gửi response. Cách này hữu ích khi reply topic có nhiều partition và requester muốn điều phối response về partition mà reply container của nó đang đọc.

Nếu chỉ định reply partition:

- Reply topic phải có partition tương ứng.
- Requester phải có consumer assignment có thể đọc partition đó.
- Responder phải giữ nguyên header và dùng reply template hỗ trợ destination partition.
- Cần kiểm thử partition routing khi tăng/giảm partition hoặc thay đổi concurrency.

Không chỉ định partition tùy tiện nếu chưa xác định topology của reply container. Nếu không có yêu cầu định tuyến cụ thể, để Kafka partitioner chọn partition hoặc dùng reply topic riêng cho từng requester thường đơn giản hơn.

## 13. Bảo mật và vận hành reply topic

Reply topic là một phần của API nội bộ giữa requester và responder. Cần quản lý quyền và vòng đời như các topic ứng dụng khác:

- Requester có quyền ghi request topic và đọc reply topic.
- Responder có quyền đọc request topic và ghi reply topic.
- Reply topic chỉ nên được đọc bởi requester được phép.
- Không cho phép client tự do chỉ định mọi topic làm reply destination.
- Dùng TLS, ACL và xác thực client theo tiêu chuẩn cluster.
- Chọn retention phù hợp để response đến muộn không tồn tại quá lâu.
- Theo dõi consumer lag, số request timeout, reply không ghép được correlation ID và lỗi publish response.

Không đưa secret hoặc dữ liệu nhạy cảm vào correlation ID. Correlation ID thường xuất hiện trong log và tracing; nên dùng giá trị ngẫu nhiên không chứa thông tin cá nhân.

Reply topic cần đủ partition và replication factor theo yêu cầu tải. Nếu reply topic dùng partition routing, cấu hình partition phải phù hợp với giá trị `KafkaHeaders.REPLY_PARTITION`. Nếu dùng shared topic, cần đánh giá chi phí mỗi requester instance đọc toàn bộ reply.

## 14. Kiểm thử request-reply

Nên kiểm thử cả đường request, responder, reply container và correlation mapping. Mock riêng `ReplyingKafkaTemplate` không chứng minh broker, header và consumer container phối hợp đúng.

Các trường hợp nên kiểm thử:

- Request được gửi đến đúng topic, key và có correlation ID.
- Responder nhận request, thực hiện nghiệp vụ và phát response.
- Reply topic và correlation header được giữ nguyên.
- Future hoàn tất với đúng response khi có nhiều request đồng thời.
- Nhiều request được trả lời theo thứ tự khác nhau nhưng vẫn ghép đúng theo correlation ID.
- Reply timeout xảy ra khi responder không phản hồi.
- Response đến sau timeout không làm hoàn tất nhầm request khác.
- Correlation ID sai hoặc thiếu không làm future khác hoàn tất.
- Shared reply topic hoạt động khi mỗi instance có group riêng.
- Reply partition được định tuyến đúng khi sử dụng.
- Lỗi serializer, deserializer, ACL và publish response được quan sát rõ ràng.

Ví dụ integration test minh họa cách chờ response:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;

class OrderLookupRequestReplyTest {

    @Test
    void receivesCorrelatedReply() throws Exception {
        var request = new ProducerRecord<>(
            "order-lookup.requests",
            "ORD-1",
            "ORD-1"
        );

        var future = replyingKafkaTemplate.sendAndReceive(request);

        var reply = future.get(10, TimeUnit.SECONDS);

        assertThat(reply.value()).isEqualTo("SHIPPED");
    }
}
~~~

Test cần khởi tạo broker, reply container, responder listener và template trước khi gửi request. Dùng topic và group riêng cho test cùng timeout hữu hạn. Nếu test nhiều request đồng thời, xác minh từng future nhận đúng response theo correlation ID thay vì chỉ kiểm tra số lượng response.

## 15. Khi nào nên dùng request-reply trên Kafka?

Request-reply phù hợp khi:

- Hai service giao tiếp qua Kafka nhưng caller thực sự cần một kết quả trả về.
- Công việc hoàn thành trong thời gian chờ có giới hạn và có thể đặt timeout hợp lý.
- Cả requester và responder có thể quản lý correlation ID, reply topic và vòng đời response.
- Hệ thống đã có Kafka và muốn dùng cùng hạ tầng bảo mật, routing và quan sát.

Không nên dùng request-reply cho mọi tương tác:

- Nếu caller không cần kết quả ngay, phát event và xử lý bất đồng bộ thường đơn giản hơn.
- Nếu caller cần latency rất thấp hoặc giao tiếp tương tác trực tiếp, HTTP/gRPC có thể phù hợp hơn.
- Nếu công việc kéo dài nhiều phút, dùng command/event và trạng thái tiến trình thay vì giữ request future mở.
- Nếu response lớn hoặc cần truyền tệp, gửi metadata/tham chiếu qua Kafka thay vì giữ payload lớn trong reply.
- Nếu nhiều requester có vòng đời khác nhau, cần thiết kế reply topic và consumer group trước khi triển khai.

Request-reply trên Kafka không biến Kafka thành RPC đồng bộ có bảo đảm exactly-once. Nó là mô hình bất đồng bộ có correlation và timeout. Side effect của responder vẫn cần idempotency; response có thể đến muộn, request có thể được xử lý lại và caller có thể hết thời gian chờ trước khi công việc kết thúc.

## 16. Checklist triển khai

- [ ] Tạo request topic và reply topic với partition, replication và retention phù hợp.
- [ ] Cấu hình `ReplyingKafkaTemplate` với producer factory và reply container đúng kiểu.
- [ ] Dùng consumer factory/deserializer tương thích với response.
- [ ] Đặt group ID riêng cho reply container theo topology requester.
- [ ] Đảm bảo reply container chạy trước khi gửi request.
- [ ] Cấu hình timeout hữu hạn cho từng request hoặc default timeout.
- [ ] Dùng `@KafkaListener` và `@SendTo` hoặc reply template để phát response.
- [ ] Giữ nguyên correlation ID từ request sang response.
- [ ] Cấu hình shared reply topic đúng cách nếu nhiều requester instance dùng chung.
- [ ] Không để nhiều instance chia sẻ cùng reply consumer group nếu cần nhận response riêng của từng instance.
- [ ] Chỉ cho phép reply destination trong allowlist và cấp ACL tối thiểu.
- [ ] Thiết kế idempotency cho responder khi requester retry sau timeout.
- [ ] Theo dõi request timeout, reply lag, correlation mismatch và lỗi publish response.
- [ ] Kiểm thử request-reply qua broker thật, gồm nhiều request đồng thời và response đến muộn.

`ReplyingKafkaTemplate` kết hợp reply container giúp Spring Kafka thực hiện request-reply bằng request topic, reply topic và correlation ID. Responder có thể dùng `@KafkaListener` cùng `@SendTo` để trả kết quả. Để mô hình vận hành ổn định, cần cấu hình consumer group và reply routing đúng topology, đặt timeout hữu hạn, bảo toàn correlation ID và xử lý idempotent khi request được gửi lại.
