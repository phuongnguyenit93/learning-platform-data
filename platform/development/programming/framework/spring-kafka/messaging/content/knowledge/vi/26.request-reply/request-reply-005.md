# Timeout khi chờ reply

Request-reply với Kafka cho phép một service gửi request lên topic và chờ service khác xử lý rồi gửi reply về. Trong Spring Kafka, ReplyingKafkaTemplate cung cấp API sendAndReceive() trả về một future đại diện cho reply tương ứng. Vì request và reply đi qua broker, thời gian hoàn tất phụ thuộc vào producer, Kafka, consumer xử lý request, producer gửi reply và consumer nhận reply.

Timeout là giới hạn thời gian phía requester sẵn sàng chờ kết quả. Khi hết thời gian, ứng dụng có thể ngừng chờ và trả trạng thái timeout cho caller. Điều đó không chứng minh request chưa được gửi hoặc service đích chưa xử lý. Request có thể đã được xử lý thành công nhưng reply đến chậm, bị mất hoặc chưa được requester nhận. Đây là điểm quan trọng nhất khi thiết kế request-reply: timeout tạo ra kết quả chưa xác định, vì vậy retry phải đi cùng idempotency.

Bài học tập trung vào timeout của ReplyingKafkaTemplate, cách cấu hình timeout mặc định và timeout theo từng request, phân biệt send failure với reply timeout, xử lý reply đến muộn, quản lý correlation ID và thiết kế retry an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả vòng đời request-reply trong Spring Kafka.
- Cấu hình ReplyingKafkaTemplate và reply listener container.
- Thiết lập thời gian chờ reply mặc định và theo từng request.
- Phân biệt timeout chờ reply với lỗi gửi request và timeout của Kafka producer.
- Giải thích vì sao timeout không hủy xử lý ở service đích.
- Nhận diện reply đến sau deadline và cách xử lý.
- Thiết kế correlation ID, request ID và idempotency key.
- Chọn timeout dựa trên latency budget của toàn luồng.
- Tránh retry storm và duplicate side effect sau timeout.
- Kiểm thử reply đúng hạn, timeout, late reply, send failure và cấu hình reply consumer group.

## 1. Request-reply hoạt động như thế nào?

Một requester gửi request record lên request topic. Record mang correlation ID để liên kết reply với lời gọi đang chờ. Requester cũng cần một reply topic mà reply listener container đang subscribe. Service xử lý request tạo reply và gửi về reply topic, kèm correlation ID tương ứng.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant K as Kafka
    participant B as Service xử lý
    A->>A: Tạo correlation ID
    A->>K: Gửi request + reply topic + correlation ID
    K->>B: Consumer nhận request
    B->>B: Xử lý nghiệp vụ
    B->>K: Gửi reply + correlation ID
    K->>A: Reply listener nhận reply
    A->>A: Tìm future theo correlation ID
    A-->>A: Hoàn tất future
~~~

ReplyingKafkaTemplate quản lý các request đang chờ trong bộ nhớ bằng correlation ID. Khi reply listener nhận một record, template tìm future tương ứng và hoàn tất future đó.

Các thành phần chính:

- Request topic: nơi service đích nhận request.
- Reply topic: nơi requester nhận reply.
- Reply listener container: consumer container lắng nghe reply topic.
- Correlation ID: khóa ghép reply với request đang chờ.
- RequestReplyFuture: future đại diện cho kết quả reply.
- Reply timeout: giới hạn thời gian chờ reply.

Request-reply qua Kafka là giao thức bất đồng bộ có thể được ứng dụng sử dụng theo kiểu chờ đồng bộ. Nó không có bảo đảm thời gian phản hồi như một lời gọi hàm nội bộ; broker, consumer lag, rebalance và downstream đều ảnh hưởng latency.

## 2. Cấu hình ReplyingKafkaTemplate

ReplyingKafkaTemplate cần một ProducerFactory để gửi request và một reply listener container để nhận reply.

Ví dụ cấu hình:

~~~java
@Configuration
public class KafkaRequestReplyConfiguration {

    @Bean
    public ConcurrentMessageListenerContainer<String, OrderReply>
            repliesContainer(
                    ConcurrentKafkaListenerContainerFactory<String, OrderReply>
                            replyListenerFactory) {

        ConcurrentMessageListenerContainer<String, OrderReply> container =
                replyListenerFactory.createContainer("orders.replies");

        container.getContainerProperties().setGroupId(
                "orders-requester-replies"
        );

        return container;
    }

    @Bean
    public ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
            replyingKafkaTemplate(
                    ProducerFactory<String, OrderRequest> producerFactory,
                    ConcurrentMessageListenerContainer<String, OrderReply>
                            repliesContainer) {

        ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template =
                new ReplyingKafkaTemplate<>(
                        producerFactory,
                        repliesContainer
                );

        template.setDefaultReplyTimeout(Duration.ofSeconds(10));

        return template;
    }
}
~~~

Ví dụ giả định đã có ProducerFactory và reply listener factory với key/value deserializer phù hợp. Reply container phải subscribe đúng reply topic và được khởi động cùng application context.

Service xử lý request có thể trả về một object; Spring Kafka gửi object đó đến reply topic được chỉ ra trong header của request:

~~~java
@KafkaListener(
    topics = "orders.requests",
    groupId = "orders-processor"
)
@SendTo
public OrderReply process(OrderRequest request) {
    return orderService.handle(request);
}
~~~

Requester tạo record và gọi template:

~~~java
ProducerRecord<String, OrderRequest> requestRecord =
        new ProducerRecord<>(
                "orders.requests",
                request.orderId(),
                request
        );

RequestReplyFuture<String, OrderRequest, OrderReply> future =
        replyingKafkaTemplate.sendAndReceive(
                requestRecord,
                Duration.ofSeconds(5)
        );
~~~

ReplyingKafkaTemplate thêm correlation metadata và thông tin reply destination dựa trên reply listener container. Từ Spring Kafka 2.2, template có thể suy ra reply topic/partition khi container nghe đúng một topic hoặc một TopicPartitionOffset; nếu container nghe nhiều destination, ứng dụng phải cung cấp reply headers tường minh. @SendTo không có destination tường minh cho phép listener dùng reply destination trong request header. Hai phía phải thống nhất serializer/deserializer và kiểu reply.

Có thể dùng một reply topic cố định cho requester hoặc một reply topic/partition riêng theo instance. Khi dùng reply topic chung cho nhiều requester instance, cần thiết kế consumer group để reply được giao đến đúng requester; phần này được giải thích ở mục về shared reply topic.

### Chờ reply container được assign trước khi gửi

Từ Spring Kafka 2.8.8, ReplyingKafkaTemplate có waitForAssignment(). Cách này hữu ích khi reply container dùng auto.offset.reset=latest, để requester không gửi request trước khi reply consumer khởi tạo và bỏ lỡ reply đến sớm:

~~~java
if (!replyingKafkaTemplate.waitForAssignment(Duration.ofSeconds(10))) {
    throw new IllegalStateException(
            "Reply container chưa được assign partition"
    );
}
~~~

Thời gian chờ assignment là một bước khởi động riêng, không phải reply timeout của từng request. Với manual partition assignment không dùng group management, thời gian chờ cần lớn hơn pollTimeout của container vì thông báo assignment chỉ được phát sau poll đầu tiên. Nếu gửi request trước khi reply container sẵn sàng, reply có thể được ghi vào Kafka nhưng requester chưa nhận được trong khoảng thời gian mong muốn.

## 3. Cấu hình timeout mặc định

ReplyingKafkaTemplate cho phép đặt thời gian chờ mặc định bằng setDefaultReplyTimeout().

~~~java
template.setDefaultReplyTimeout(Duration.ofSeconds(10));
~~~

Mọi request gửi bằng sendAndReceive() mà không truyền timeout riêng (hoặc truyền null) sẽ dùng giá trị mặc định này. Spring Kafka hiện mặc định reply timeout là 5 giây; ứng dụng nên đặt giá trị tường minh theo SLA thay vì phụ thuộc mặc định.

Nên cấu hình timeout tường minh thay vì phụ thuộc vào giá trị mặc định của phiên bản thư viện. Timeout phù hợp tùy thuộc loại request, SLA của service đích, tải Kafka và thời gian xử lý downstream.

Ví dụ:

| Loại request | Timeout minh họa |
|---|---:|
| Tra cứu trạng thái nhẹ | 2 giây |
| Tính toán nghiệp vụ thông thường | 5 giây |
| Xử lý phụ thuộc nhiều service | 10–15 giây |
| Tác vụ dài hoặc báo cáo | Nên chuyển sang job bất đồng bộ thay vì giữ request-reply lâu |

Các con số chỉ là ví dụ để bắt đầu thiết kế. Hãy lấy latency percentile thực tế, SLA và timeout của các dependency làm căn cứ.

Timeout quá ngắn làm tăng timeout giả khi hệ thống chỉ chậm tạm thời. Timeout quá dài giữ request context và tài nguyên của caller lâu hơn, đồng thời làm người dùng chờ lâu khi service đích đã gặp sự cố.

## 4. Timeout riêng cho từng request

Một số request có SLA khác nhau. Có thể truyền Duration cho từng lần sendAndReceive() thay vì dùng timeout mặc định.

~~~java
RequestReplyFuture<String, OrderRequest, OrderReply> future =
        replyingKafkaTemplate.sendAndReceive(
                requestRecord,
                Duration.ofSeconds(3)
        );
~~~

Ví dụ service có hai loại request:

~~~java
public OrderReply getOrderStatus(OrderRequest request) throws Exception {
    ProducerRecord<String, OrderRequest> record =
            new ProducerRecord<>("orders.requests", request.orderId(), request);

    RequestReplyFuture<String, OrderRequest, OrderReply> future =
            replyingKafkaTemplate.sendAndReceive(
                    record,
                    Duration.ofSeconds(2)
            );

    return future.get();
}

public OrderReply calculateOrder(OrderRequest request) throws Exception {
    ProducerRecord<String, OrderRequest> record =
            new ProducerRecord<>("orders.requests", request.orderId(), request);

    RequestReplyFuture<String, OrderRequest, OrderReply> future =
            replyingKafkaTemplate.sendAndReceive(
                    record,
                    Duration.ofSeconds(12)
            );

    return future.get();
}
~~~

Timeout theo từng request giúp không phải dùng một giá trị chung cho mọi nghiệp vụ. Tuy nhiên, không nên đặt timeout tùy tiện ở từng nơi; hãy định nghĩa latency budget theo use case để tránh các service gọi nhau với timeout mâu thuẫn.

Nếu phiên bản Spring Kafka đang dùng chưa có overload sendAndReceive(record, Duration), dùng API tương ứng của phiên bản hoặc cấu hình default reply timeout. Hãy kiểm tra Javadoc theo dependency thực tế.

## 5. RequestReplyFuture và kết quả gửi request

RequestReplyFuture đại diện cho kết quả reply. Nó cũng cung cấp send future để theo dõi việc gửi request.

Có hai giai đoạn cần phân biệt:

1. Producer gửi request lên Kafka.
2. Requester nhận reply khớp correlation ID.

Ví dụ:

~~~java
RequestReplyFuture<String, OrderRequest, OrderReply> future =
        replyingKafkaTemplate.sendAndReceive(requestRecord);

future.getSendFuture().whenComplete((sendResult, sendError) -> {
    if (sendError != null) {
        log.error("Không gửi được request lên Kafka", sendError);
        return;
    }

    log.debug(
            "Request đã gửi: topic={}, partition={}, offset={}",
            sendResult.getRecordMetadata().topic(),
            sendResult.getRecordMetadata().partition(),
            sendResult.getRecordMetadata().offset()
    );
});
~~~

Nếu send future thất bại, request chưa được xác nhận gửi thành công theo kết quả producer. Nếu send future thành công nhưng reply future timeout, request đã được broker xác nhận nhưng requester chưa nhận được reply đúng hạn.

Không gộp hai trường hợp này thành cùng một thông báo lỗi. Chúng dẫn đến quyết định retry và điều tra khác nhau.

Trong Spring Kafka 3.0 trở lên, future của request-reply và send future là CompletableFuture. Ở các phiên bản 2.x, API future có thể là ListenableFuture; cách đăng ký callback cần điều chỉnh theo phiên bản đang dùng.

## 6. Phân biệt reply timeout với các timeout khác

Một request-reply có nhiều đồng hồ thời gian. Chúng cần được cấu hình và giám sát riêng.

| Timeout | Áp dụng ở đâu | Ý nghĩa |
|---|---|---|
| Reply timeout | ReplyingKafkaTemplate | Thời gian requester chờ reply tương ứng |
| Producer delivery timeout | Kafka producer | Giới hạn thời gian gửi record thành công hoặc báo lỗi |
| Request processing timeout | Service xử lý request | Giới hạn thời gian nghiệp vụ xử lý |
| Downstream timeout | HTTP/database/client khác | Giới hạn thời gian chờ dependency |
| Caller timeout | HTTP/gRPC/API bên ngoài | Thời gian caller chờ service hiện tại |
| Startup assignment timeout | Reply listener container | Thời gian chờ reply consumer nhận assignment |

Ví dụ producer delivery timeout:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

delivery.timeout.ms không phải reply timeout. Producer có thể gửi request thành công trong vài mili giây nhưng service xử lý mất 20 giây; khi đó reply timeout 5 giây vẫn có thể xảy ra.

Ngược lại, producer có thể không gửi được request vì broker unavailable trước khi reply timeout có ý nghĩa. Hãy kiểm tra send future để phân biệt.

## 7. Timeout không hủy request ở service đích

Khi ReplyingKafkaTemplate hết thời gian chờ, requester nhận TimeoutException hoặc future hoàn tất exceptionally theo cơ chế timeout của template. Điều đó chỉ kết thúc việc chờ kết quả tại requester.

Nó không:

- Xóa request record khỏi Kafka.
- Hủy consumer đang xử lý request.
- Rollback database transaction của service đích.
- Thu hồi HTTP/API call mà service đích đã gửi.
- Ngăn service đích publish reply sau đó.

Ví dụ:

~~~text
t=0s   Requester gửi request R-100
t=1s   Service B nhận request
t=2s   Service B bắt đầu cập nhật database
t=5s   Requester hết reply timeout
t=7s   Service B commit database
t=8s   Service B gửi reply
~~~

Ở thời điểm 5 giây, requester báo timeout nhưng nghiệp vụ vẫn có thể hoàn tất ở giây thứ 7. Nếu requester lập tức gửi request mới và service B xử lý lần nữa, side effect có thể bị lặp.

Vì vậy, timeout nên được biểu diễn là kết quả chưa xác định hoặc trạng thái cần tra cứu, tùy nghiệp vụ. Không được mặc định timeout nghĩa là thao tác thất bại.

## 8. Reply đến muộn (late reply)

Reply có thể đến sau khi requester đã timeout vì:

- Consumer xử lý request bị lag.
- Service đích đang chờ database hoặc HTTP dependency.
- Reply producer gửi chậm hoặc retry.
- Reply topic có nhiều traffic.
- Requester reply container rebalance hoặc mất kết nối.
- Timeout được cấu hình thấp hơn latency thực tế.

Khi timeout nội bộ của ReplyingKafkaTemplate đã loại request khỏi danh sách đang chờ, reply đến sau đó không còn future tương ứng để hoàn tất. Template không thể trả kết quả đó về lời gọi đã timeout; reply thường bị xem là không có request đang chờ và được ghi log.

Ứng dụng cần quyết định có cần lưu late reply để tra cứu hay không. Với nghiệp vụ có side effect quan trọng, một kết quả đến muộn có thể vẫn có giá trị để cập nhật trạng thái request trong database hoặc gửi notification.

Không nên tăng timeout vô hạn chỉ để tránh late reply. Hãy chọn timeout theo SLA, đồng thời thiết kế trạng thái nghiệp vụ cho request đang xử lý, đã hoàn tất, timeout chờ và kết quả đến muộn.

## 9. Correlation ID và request ID là hai định danh khác nhau

Correlation ID liên kết reply với một future đang chờ trong requester. Request ID định danh một yêu cầu nghiệp vụ qua nhiều lần gửi hoặc retry.

Nên tách hai mục đích:

| Định danh | Phạm vi | Khi retry |
|---|---|---|
| Correlation ID | Một lần trao đổi request-reply đang chờ | Có thể tạo ID mới cho lần gửi mới |
| Request ID | Một yêu cầu nghiệp vụ logic | Giữ nguyên để deduplicate |
| Event ID | Một sự kiện cụ thể | Giữ nguyên khi phát lại cùng event |
| Redrive ID | Một lần vận hành gửi lại record | Tạo mới cho mỗi lần redrive |

Ví dụ requester gửi requestId ORD-100-UPDATE lần đầu với correlationId C-1. Request timeout. Khi retry, requester có thể tạo correlationId C-2 nhưng vẫn giữ requestId ORD-100-UPDATE.

Service đích dùng requestId để kiểm tra request đã được xử lý chưa. Nếu đã hoàn tất, nó có thể trả lại kết quả đã lưu thay vì thực hiện side effect lần nữa.

Không dùng correlation ID làm idempotency key nếu mỗi lần retry tạo correlation ID mới.

## 10. Thiết kế idempotency ở service xử lý request

Nếu request có thể được gửi lại sau timeout, service đích cần bảo vệ side effect bằng request ID ổn định.

Ví dụ:

~~~java
@Transactional
public OrderReply handle(OrderRequest request) {
    Optional<StoredReply> previous =
            requestRepository.findReplyByRequestId(request.requestId());

    if (previous.isPresent()) {
        return previous.get().toOrderReply();
    }

    OrderReply reply = orderService.apply(request);

    requestRepository.save(
            new StoredReply(
                    request.requestId(),
                    reply.status(),
                    reply.orderId()
            )
    );

    return reply;
}
~~~

Trong production, việc kiểm tra request ID, thực hiện nghiệp vụ và lưu reply phải được bảo vệ bằng cùng transaction database hoặc một cơ chế đồng bộ tương đương. Unique constraint trên requestId là lớp bảo vệ trước các request trùng đến đồng thời.

Nếu chỉ kiểm tra exists rồi mới ghi mà không có unique constraint, hai consumer thread có thể cùng thấy request chưa tồn tại và cùng thực hiện side effect.

Với request có thể chạy lâu, có thể lưu trạng thái ACCEPTED/PROCESSING/COMPLETED/FAILED. Khi requester timeout, nó tra cứu theo requestId để biết công việc đã hoàn tất hay vẫn đang chạy.

## 11. Cấu hình reply topic và consumer group

Reply listener container phải nhận được reply dành cho đúng requester. Khi mỗi requester instance có reply topic riêng, việc định tuyến tương đối đơn giản. Khi nhiều requester instance dùng chung một reply topic, cần chú ý consumer group.

Nếu các requester instance dùng chung một group ID trên reply topic, Kafka phân phối mỗi reply cho một member trong group. Reply có thể đến instance không có future với correlation ID đó. Instance sở hữu request không nhận được reply và sẽ timeout.

Ví dụ tình huống sai:

~~~text
Requester pod A ----\
                     +---- replies topic, group=reply-consumers
Requester pod B ----/             |
                                   v
                           Kafka phân phối reply
                           đến một member bất kỳ
~~~

Một cách triển khai là dùng group ID riêng cho từng requester instance khi dùng reply topic chung. Khi đó, mỗi group nhận bản sao của reply topic và instance có thể tìm correlation ID của chính nó. Các reply không thuộc instance sẽ không khớp future và bị bỏ qua theo cơ chế của template.

Khi nhiều ReplyingKafkaTemplate cùng dùng một reply topic, bật sharedReplyTopic để hạ log của reply không khớp từ ERROR xuống DEBUG:

~~~java
replyingKafkaTemplate.setSharedReplyTopic(true);
~~~

Thiết lập này chỉ điều chỉnh cách template xử lý/log reply không thuộc instance; nó không thay thế yêu cầu group ID riêng hoặc partition riêng cho từng requester.

Đánh đổi là mỗi requester instance đọc toàn bộ reply topic, làm tăng lưu lượng consumer. Với tải lớn, cân nhắc reply topic hoặc partition riêng theo instance và định tuyến reply đúng nơi.

Không đặt group ID cố định chung cho mọi requester instance nếu mỗi instance chỉ giữ pending correlation trong bộ nhớ riêng.

## 12. Timeout và retry an toàn

Khi reply timeout, requester có thể retry nhưng cần tránh retry storm và duplicate.

Một chính sách retry thường có:

- Số lần thử hữu hạn.
- Exponential backoff.
- Jitter để các requester không retry đồng loạt.
- Request ID ổn định qua các lần thử.
- Correlation ID riêng cho từng lần trao đổi.
- Idempotency ở service đích.
- Tổng deadline cho toàn bộ thao tác.

Ví dụ:

~~~java
Duration[] retryDelays = {
        Duration.ofMillis(200),
        Duration.ofMillis(500),
        Duration.ofSeconds(1)
};
~~~

Đây chỉ là ví dụ lịch backoff. Không nên retry nếu lỗi là validation hoặc request không hợp lệ. Timeout có kết quả chưa xác định nên cần tra cứu trạng thái hoặc retry bằng request ID idempotent.

Nếu mỗi lần retry đều dùng timeout 10 giây và có ba lần thử tuần tự, caller có thể phải chờ hơn 30 giây cộng backoff. Hãy đặt một deadline tổng và tính thời gian còn lại trước mỗi lần gửi.

## 13. Dùng deadline tổng thay vì cộng dồn timeout

Giả sử API bên ngoài có SLA 8 giây. Nếu mỗi tầng trong chuỗi request-reply tự đặt timeout 8 giây, tổng thời gian có thể vượt SLA.

Ví dụ:

~~~text
HTTP caller deadline: 8s
    |
    +-- requester chờ Kafka reply: 7s
            |
            +-- service B gọi database: 6s
                    |
                    +-- retry dependency: 4s
~~~

Các timeout lồng nhau có thể làm tổng thời gian lớn hơn deadline bên ngoài. Nên truyền hoặc tính deadline còn lại, không reset timeout đầy đủ ở mỗi tầng.

Một nguyên tắc:

~~~text
remaining = overallDeadline - currentTime

replyTimeout = min(configuredReplyTimeout, remaining)
dependencyTimeout <= remaining - safetyMargin
~~~

Nếu remaining <= 0, không gửi request mới. Trả trạng thái timeout hoặc pending theo hợp đồng API.

Kafka request-reply không có deadline propagation tự động cho mọi tầng. Nếu cần deadline nghiệp vụ, truyền deadline hoặc expiry timestamp trong payload/header và service đích tự kiểm tra trước khi bắt đầu công việc.

## 14. Đặt timeout ở service đích

Reply timeout của requester không ngăn service đích xử lý một request đã quá hạn. Nếu request không còn hữu ích sau deadline, service đích cần biết deadline và quyết định có tiếp tục hay không.

Ví dụ payload:

~~~java
public record OrderRequest(
        String requestId,
        String orderId,
        Instant deadline,
        String operation
) {}
~~~

Service xử lý:

~~~java
public OrderReply handle(OrderRequest request) {
    if (Instant.now().isAfter(request.deadline())) {
        return OrderReply.expired(request.requestId());
    }

    return orderService.apply(request);
}
~~~

Kiểm tra deadline trước khi bắt đầu side effect. Với công việc đã bắt đầu, việc dừng an toàn phụ thuộc nghiệp vụ và transaction boundary. Không hủy ngang một thao tác database giữa chừng nếu điều đó có thể để lại trạng thái không nhất quán.

Nếu request đã được xử lý xong nhưng reply đến muộn, hãy giữ kết quả theo requestId để requester có thể truy vấn sau.

## 15. Xử lý reply error thay vì timeout

Không phải mọi reply không thành công đều là timeout. Service đích có thể trả một reply biểu diễn lỗi nghiệp vụ, ví dụ OrderNotFound hoặc ValidationFailed.

Ví dụ:

~~~java
public record OrderReply(
        String requestId,
        boolean success,
        String errorCode,
        String message,
        String orderId
) {}
~~~

Requester nhận reply và kiểm tra:

~~~java
OrderReply reply = future.get();

if (!reply.success()) {
    throw new OrderRequestRejectedException(
            reply.errorCode(),
            reply.message()
    );
}
~~~

Đây là reply thành công ở tầng transport nhưng biểu diễn lỗi ở tầng nghiệp vụ. Không retry một reply từ chối do validation như thể đó là timeout tạm thời.

Spring Kafka cũng hỗ trợ reply error checker trên ReplyingKafkaTemplate để chuyển một số reply có exception header thành exception phía requester. Nếu dùng cơ chế này, hãy xác định rõ header nào được xem là lỗi và phân biệt với reply nghiệp vụ bình thường.

## 16. Kiểm soát kích thước pending requests

Mỗi request đang chờ cần một entry correlation/future trong bộ nhớ của requester. Nếu service đích chậm hoặc reply timeout quá dài, số pending request có thể tăng.

Một số biện pháp:

- Giới hạn số request đồng thời bằng semaphore hoặc bulkhead.
- Đặt timeout hữu hạn cho mọi request.
- Giới hạn queue của HTTP executor hoặc thread pool.
- Theo dõi số pending requests và thời gian chờ.
- Dùng circuit breaker khi dependency liên tục timeout.
- Chuyển tác vụ dài sang asynchronous job thay vì giữ request-reply mở lâu.

Không mở hàng nghìn request đồng thời chỉ vì API trả về future. Bất đồng bộ không có nghĩa tài nguyên là vô hạn.

Khi timeout, template hoàn tất future và dọn entry chờ theo cơ chế của nó. Nếu caller chỉ dùng future.get(timeout, unit) với timeout của Java Future, đó chỉ là giới hạn chờ của caller; nó không thay thế timeout nội bộ của ReplyingKafkaTemplate và không nhất thiết dọn pending correlation ngay tại thời điểm get() ném TimeoutException.

Vì vậy, hãy cấu hình timeout ở ReplyingKafkaTemplate hoặc overload sendAndReceive có timeout. Có thể dùng get(timeout) như một lớp deadline bổ sung, nhưng không dựa vào nó làm cơ chế quản lý pending request.

## 17. Quan sát timeout trong production

Cần theo dõi riêng send failure, reply timeout và late/unmatched reply.

Các metric nên có:

| Metric | Ý nghĩa |
|---|---|
| request_send_success_total | Số request producer gửi thành công |
| request_send_failure_total | Số request không gửi thành công |
| request_reply_success_total | Số request nhận reply đúng hạn |
| request_reply_timeout_total | Số request hết thời gian chờ |
| request_reply_latency | Thời gian từ gửi request đến nhận reply |
| pending_request_count | Số request đang chờ reply |
| unmatched_reply_total | Reply không khớp correlation đang chờ |
| late_reply_total | Reply đến sau deadline, nếu ứng dụng nhận diện được |
| reply_consumer_lag | Lag của reply listener container |

Gắn các thuộc tính vào log:

- requestId.
- correlationId.
- request topic/partition/offset.
- reply topic/partition/offset.
- service đích.
- timeout được chọn.
- thời gian gửi, thời gian nhận và tổng latency.
- attempt number.
- trạng thái idempotency.

Không log toàn bộ payload hoặc dữ liệu nhạy cảm. Dùng requestId và correlationId để nối trace giữa requester, service đích và reply consumer.

Nếu timeout tăng, kiểm tra theo thứ tự: send failure, request topic lag, service processing latency, reply publish latency, reply topic lag và requester assignment/rebalance.

## 18. Kiểm thử timeout với EmbeddedKafka hoặc Testcontainers

Một test tốt phải mô phỏng thời điểm request được gửi, reply được phát và deadline hết hạn.

Các kịch bản nên có:

1. Reply đến trước timeout: future hoàn tất bình thường.
2. Không có reply: future hoàn tất exceptionally do reply timeout.
3. Service xử lý lâu hơn timeout: requester timeout nhưng side effect phía service vẫn có thể hoàn tất.
4. Reply đến sau timeout: không có future ban đầu để hoàn tất; xác nhận log/metric và chính sách late reply.
5. Producer gửi request thất bại: send future báo lỗi riêng với reply timeout.
6. Correlation ID sai hoặc thiếu: reply không ghép được với future.
7. Hai request đồng thời: mỗi reply phải hoàn tất đúng future.
8. Reply topic chung với hai requester instance: kiểm tra group ID không làm reply đi nhầm instance.
9. Reply container chưa được assign: xác nhận ứng dụng chờ assignment hoặc báo lỗi khởi động.
10. Request retry sau timeout: cùng requestId nhưng correlation ID mới; side effect chỉ thực hiện một lần.
11. Service đích trả business error: requester nhận reply lỗi, không phân loại thành timeout.
12. Reply consumer rebalance: xác nhận request đang chờ có thể timeout và hệ thống ghi nhận nguyên nhân.

Dùng latch, Awaitility hoặc future completion để đồng bộ test. Không dùng Thread.sleep cố định rồi suy luận request đã được xử lý. Với test late reply, chủ động trì hoãn reply bằng latch hoặc test service có điều khiển.

## 19. Các lỗi thường gặp

**Coi timeout là request thất bại chắc chắn.** Request có thể đã được xử lý nhưng reply chưa đến. Dùng trạng thái chưa xác định và requestId để tra cứu.

**Chỉ dùng future.get(timeout).** Đây là timeout chờ của caller, không thay thế timeout nội bộ của ReplyingKafkaTemplate. Cấu hình default reply timeout hoặc timeout riêng.

**Dùng cùng reply consumer group cho nhiều requester instance.** Kafka có thể giao reply cho instance không có correlation tương ứng. Dùng group riêng hoặc định tuyến reply theo instance.

**Retry ngay sau timeout mà không có idempotency.** Request đầu có thể đã tạo side effect. Giữ requestId và deduplicate ở service đích.

**Dùng một timeout cho mọi loại request.** Request nhẹ và request dài có latency khác nhau. Dùng timeout theo use case nhưng giữ deadline tổng.

**Không kiểm tra send future.** Producer gửi thất bại bị hiểu nhầm là reply timeout. Theo dõi giai đoạn gửi riêng.

**Không chờ reply container assignment.** Reply container chưa subscribe khi request được gửi. Chờ assignment trước khi nhận traffic.

**Tăng timeout để che consumer lag.** Caller chờ lâu hơn nhưng nguyên nhân vẫn còn. Theo dõi lag và latency từng chặng.

**Không xử lý late reply.** Kết quả nghiệp vụ có thể hoàn tất sau khi caller đã timeout. Lưu trạng thái theo requestId nếu cần truy vấn hoặc thông báo sau.

**Dùng correlation ID làm request ID.** Retry tạo correlation mới làm mất khả năng deduplicate. Tách correlation ID khỏi request ID.

**Để pending request không giới hạn.** Service đích chậm có thể làm requester giữ nhiều future. Giới hạn concurrency và đặt timeout hữu hạn.

## 20. Checklist thiết kế timeout

- [ ] ReplyingKafkaTemplate dùng reply listener container đã subscribe đúng topic.
- [ ] Reply container được assign trước khi requester nhận traffic.
- [ ] Có timeout mặc định hữu hạn.
- [ ] Request quan trọng có thể đặt timeout riêng.
- [ ] Send failure và reply timeout được ghi nhận riêng.
- [ ] Timeout được chọn theo latency budget và SLA.
- [ ] Caller timeout không bị nhầm với timeout nội bộ của template.
- [ ] Late reply có chính sách quan sát hoặc lưu trạng thái.
- [ ] Request ID ổn định qua retry.
- [ ] Correlation ID xác định từng lần request-reply.
- [ ] Service đích có idempotency hoặc inbox theo requestId.
- [ ] Retry có giới hạn, backoff và jitter.
- [ ] Reply consumer group được thiết kế đúng khi dùng shared reply topic.
- [ ] Pending requests và reply consumer lag được giám sát.
- [ ] Test bao gồm reply đúng hạn, timeout, late reply và send failure.

## Kết luận

Timeout của ReplyingKafkaTemplate xác định thời gian requester chờ reply, không hủy request đã được gửi và không rollback nghiệp vụ ở service đích. Hãy cấu hình default reply timeout hoặc timeout riêng cho từng request, theo dõi send future để phân biệt lỗi gửi với lỗi chờ reply, và chờ reply container được assign trước khi nhận traffic. Khi timeout, kết quả có thể chưa xác định; giữ requestId ổn định qua retry, dùng correlation ID riêng cho từng lần trao đổi và bảo vệ side effect bằng idempotency. Kết hợp deadline tổng, retry có giới hạn, reply group đúng và metrics theo từng chặng sẽ giúp request-reply vận hành có kiểm soát.

## Tài liệu tham khảo

- [Spring Kafka – Request/Reply Messaging](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html#replying-template)
- [Spring Kafka – ReplyingKafkaTemplate API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/ReplyingKafkaTemplate.html)
- [Spring Kafka – RequestReplyFuture API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/RequestReplyFuture.html)
- [Apache Kafka – Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)

