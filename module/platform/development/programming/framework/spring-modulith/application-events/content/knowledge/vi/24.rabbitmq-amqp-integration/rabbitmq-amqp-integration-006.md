# Prefetch

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua sự kiện nghiệp vụ. Khi sự kiện được chuyển qua RabbitMQ bằng AMQP, consumer phải nhận message với tốc độ phù hợp với năng lực xử lý của nó. RabbitMQ cung cấp cơ chế **prefetch** thông qua Quality of Service (QoS) để giới hạn số message đã giao nhưng chưa được consumer xác nhận (unacknowledged messages).

Prefetch là cơ chế backpressure ở phía consumer. Nó điều tiết lượng công việc đang nằm trong tay consumer, tránh để một consumer nhận quá nhiều message khi chưa xử lý xong. Giá trị phù hợp phụ thuộc vào thời gian xử lý, kích thước message, số consumer đồng thời, mức độ song song và yêu cầu phân phối công bằng.

## 1. Prefetch giải quyết vấn đề gì?

Giả sử module Order phát event OrderConfirmed. Adapter gửi event tới RabbitMQ, còn một ứng dụng Inventory nhận message để giữ hàng. Nếu consumer nhận message nhanh hơn khả năng xử lý, nhiều message sẽ nằm trong bộ nhớ của consumer hoặc ở trạng thái đã giao nhưng chưa xác nhận. Điều này làm tăng áp lực bộ nhớ, kéo dài thời gian chờ và có thể khiến một consumer giữ quá nhiều công việc trong khi consumer khác đang rảnh.

Prefetch giới hạn số message chưa được acknowledge mà broker có thể giao cho một consumer tại một thời điểm. Khi consumer xử lý và acknowledge message, broker có thể giao thêm message để lấp đầy hạn mức.

~~~mermaid
flowchart LR
    A["RabbitMQ queue"] --> B["Consumer A"]
    A --> C["Consumer B"]
    B --> D["Process message"]
    C --> E["Process message"]
    D --> F["ACK"]
    E --> G["ACK"]
    F --> A
    G --> A
~~~

Ví dụ, nếu mỗi consumer có prefetch bằng 10, broker có thể giao tối đa 10 message chưa xác nhận cho từng consumer theo semantics per-consumer của RabbitMQ. Khi Consumer A acknowledge một message, một message khác có thể được giao cho A nếu queue còn dữ liệu. Consumer B có hạn mức riêng.

Prefetch điều tiết số lượng message đang được xử lý hoặc chờ xử lý ở phía consumer. Nó không giới hạn tốc độ publisher, không thay thế publisher confirms và không chứng minh consumer đã hoàn tất nghiệp vụ. Đây là ba cơ chế ở các vị trí khác nhau trong luồng messaging.

## 2. Unacknowledged message và consumer acknowledgement

RabbitMQ phân biệt message còn trong queue và message đã giao cho consumer nhưng chưa được xác nhận. Message chưa xác nhận được gọi là **unacknowledged**. Với acknowledgement thủ công, consumer phải gửi ACK sau khi xử lý thành công; khi channel hoặc connection đóng trước ACK, broker có thể đưa message chưa xác nhận trở lại trạng thái có thể giao cho consumer khác.

Các thao tác acknowledgement thường gặp trong AMQP 0-9-1:

| Thao tác | Ý nghĩa |
|---|---|
| ACK | Consumer xác nhận đã xử lý message |
| NACK | Consumer từ chối message; có thể yêu cầu requeue |
| Reject | Từ chối một message; có thể yêu cầu requeue |
| Requeue | Đưa message trở lại queue để giao lại |
| Dead-letter | Chuyển message sang dead-letter exchange nếu queue được cấu hình phù hợp |

Trong Spring AMQP, acknowledge mode quyết định container và listener phối hợp xác nhận message như thế nào:

- **AUTO:** container xác nhận sau khi listener xử lý thành công; khi listener ném exception, container áp dụng error handling và reject/requeue theo cấu hình.
- **MANUAL:** listener chủ động gửi ACK/NACK qua channel.
- **NONE:** message được giao theo chế độ auto-ack của broker; broker coi message đã được xác nhận ngay khi giao.

Prefetch có ý nghĩa khi broker theo dõi các message chưa xác nhận. Với chế độ auto-ack/NONE, broker không giữ message ở trạng thái unacknowledged để chờ listener xử lý xong, vì vậy prefetch không cung cấp cùng mức backpressure như chế độ có acknowledgement.

Với các luồng nghiệp vụ cần độ tin cậy, thường nên dùng acknowledgement sau khi listener hoàn thành công việc cần thiết. Nếu ACK trước khi dữ liệu nghiệp vụ được commit, ứng dụng có thể mất message khi process dừng sau ACK nhưng trước khi hoàn tất xử lý. Nếu ACK quá muộn hoặc listener bị treo, message tiếp tục chiếm một slot prefetch.

## 3. RabbitMQ QoS và phạm vi áp dụng

AMQP 0-9-1 có lệnh QoS để thiết lập giới hạn delivery. Trong RabbitMQ, cách áp dụng prefetch có một điểm cần hiểu rõ: mặc định, khi cờ global không được bật, prefetch được áp dụng riêng cho từng consumer. Đây là hành vi mở rộng của RabbitMQ so với cách diễn giải channel-wide thường gặp trong đặc tả AMQP.

Có hai phạm vi chính:

| Phạm vi | Hành vi trong RabbitMQ |
|---|---|
| Per-consumer (global=false) | Mỗi consumer trên channel có giới hạn unacknowledged riêng |
| Per-channel (global=true) | Các consumer trên cùng channel chia sẻ một giới hạn unacknowledged |

Nếu có hai consumer trên cùng channel và đặt prefetch 10 theo per-consumer, mỗi consumer có thể giữ tối đa 10 message chưa ACK, tức tổng cộng có thể là 20. Nếu đặt thêm giới hạn global 15, cả hai consumer cùng chịu giới hạn chung đó; giới hạn per-consumer và channel-wide có thể cùng có hiệu lực.

Trong RabbitMQ, giá trị prefetch bằng 0 có nghĩa là không đặt giới hạn số message chưa xác nhận. Điều này có thể khiến consumer nhận lượng message rất lớn trước khi xử lý xong. Với ứng dụng có payload lớn hoặc listener xử lý chậm, unlimited prefetch thường làm tăng rủi ro bộ nhớ và giảm khả năng phân phối công bằng.

Nếu dùng RabbitMQ Java client trực tiếp, lệnh QoS có thể được gọi trên channel:

~~~java
channel.basicQos(10);
~~~

Lệnh trên thiết lập prefetch count 10 theo hành vi mặc định per-consumer của RabbitMQ. API cũng có overload để chỉ định cờ global; hãy dùng đúng phạm vi mong muốn và kiểm tra semantics của phiên bản client/broker đang triển khai.

Không nên giả định mọi broker AMQP đều có semantics per-consumer giống RabbitMQ. Nếu adapter có thể chạy trên nhiều broker, hãy xác định hành vi QoS của từng transport và kiểm thử với broker thực tế.

## 4. Cấu hình prefetch trong Spring AMQP

Với Spring AMQP, prefetch được cấu hình trên message listener container. Khi dùng Spring Boot, có thể đặt cấu hình cho SimpleMessageListenerContainer qua application properties:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: auto
        prefetch: 20
        concurrency: 4
        max-concurrency: 8
~~~

Trong ví dụ, container bắt đầu với 4 consumer và có thể tăng tới 8 theo cấu hình. Mỗi consumer có prefetch 20, do đó với semantics per-consumer, tổng số message chưa ACK mà container có thể giữ có thể xấp xỉ 4 × 20 = 80 khi có 4 consumer hoạt động, và có thể tăng tới 8 × 20 = 160 khi đạt concurrency tối đa. Đây là ước lượng cho các consumer đang hoạt động; giới hạn channel-wide nếu được bật và cách container tạo channel có thể làm thay đổi tổng số thực tế.

Nếu cấu hình factory bằng Java, có thể đặt prefetch và concurrency như sau:

~~~java
@Bean
SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
        ConnectionFactory connectionFactory,
        SimpleRabbitListenerContainerFactoryConfigurer configurer) {

    var factory = new SimpleRabbitListenerContainerFactory();
    configurer.configure(factory, connectionFactory);

    factory.setPrefetchCount(20);
    factory.setConcurrentConsumers(4);
    factory.setMaxConcurrentConsumers(8);
    factory.setAcknowledgeMode(AcknowledgeMode.AUTO);

    return factory;
}
~~~

Listener sử dụng factory:

~~~java
@Component
class InventoryEventListener {

    private final InventoryService inventory;

    InventoryEventListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @RabbitListener(
        queues = "orders.confirmed",
        containerFactory = "rabbitListenerContainerFactory"
    )
    void onOrderConfirmed(OrderConfirmedMessage message) {
        inventory.reserve(
            message.orderId(),
            message.eventId()
        );
    }
}
~~~

Tên factory, container type và các property cần phù hợp với cấu hình Spring Boot của ứng dụng. Spring AMQP có cả SimpleMessageListenerContainer và DirectMessageListenerContainer; khả năng cấu hình concurrency và channel khác nhau giữa hai loại. Hãy xác định container đang được dùng trước khi tính giới hạn message.

Nếu cần giới hạn chung trên channel, Spring AMQP có tùy chọn global QoS ở các container/version hỗ trợ. Chỉ bật khi cần semantics channel-wide và đã hiểu cách container chia sẻ channel. Không bật global QoS chỉ vì muốn một con số tổng; nó có thể tạo thêm ràng buộc phối hợp giữa consumer trên cùng channel.

## 5. Prefetch, concurrency và throughput

Prefetch và concurrency là hai tham số khác nhau:

- **Concurrency** quyết định số consumer có thể nhận và xử lý message song song.
- **Prefetch** quyết định mỗi consumer có thể giữ bao nhiêu message chưa ACK cùng lúc.

Tăng concurrency có thể tăng số tác vụ chạy đồng thời và tận dụng CPU hoặc I/O tốt hơn. Tăng prefetch có thể giảm thời gian consumer chờ broker giao thêm message, nhất là khi thời gian round-trip giữa broker và consumer đáng kể. Tuy nhiên, cả hai đều làm tăng lượng công việc đang được giữ ở phía consumer.

Ví dụ với 4 consumer:

| Prefetch mỗi consumer | Số message chưa ACK tối đa ước lượng |
|---:|---:|
| 1 | 4 |
| 5 | 20 |
| 10 | 40 |
| 20 | 80 |
| 50 | 200 |

Bảng giả định 4 consumer hoạt động và giới hạn per-consumer. Nếu concurrency thay đổi động, tổng số message in-flight cũng thay đổi. Nếu dùng global QoS hoặc có nhiều queue/container, phải tính thêm phạm vi của từng giới hạn.

Không nên tăng concurrency và prefetch cùng lúc mà không đo lường. Nếu tăng cả hai, sẽ khó biết thay đổi nào cải thiện throughput hoặc gây ra áp lực bộ nhớ. Hãy điều chỉnh từng tham số, quan sát kết quả và ghi lại cấu hình đã thử.

## 6. Chọn giá trị prefetch

Không có một giá trị prefetch phù hợp cho mọi loại event. Hãy chọn theo thời gian xử lý, độ biến thiên của thời gian xử lý, kích thước message, tài nguyên consumer và yêu cầu phân phối công việc.

**Prefetch thấp** phù hợp khi mỗi message tốn nhiều tài nguyên, thời gian xử lý biến động mạnh hoặc cần phân phối công việc công bằng. Giá trị 1 giúp consumer chỉ giữ một message chưa ACK tại một thời điểm. Điều này giảm lượng công việc bị giữ bởi một consumer, nhưng có thể làm throughput thấp khi round-trip broker hoặc thời gian xử lý khiến consumer thường xuyên chờ message tiếp theo.

**Prefetch trung bình** thường là điểm bắt đầu để cân bằng throughput và lượng công việc in-flight. Hãy bắt đầu với một giá trị hữu hạn, đo thời gian xử lý và độ trễ, sau đó tăng hoặc giảm theo kết quả.

**Prefetch cao** có thể hữu ích khi message nhỏ, xử lý nhanh, consumer có đủ bộ nhớ và chi phí giao message đáng kể. Nhưng nếu listener xử lý chậm, nhiều message sẽ nằm trong buffer của consumer và chưa được ACK. Consumer đó có thể giữ công việc trong khi consumer khác rảnh.

**Prefetch bằng 0** cho phép broker giao không giới hạn message chưa xác nhận theo QoS count. Chỉ dùng khi có lý do rõ ràng và đã kiểm soát dung lượng bộ nhớ cùng khả năng xử lý. Với phần lớn worker service, nên đặt giới hạn hữu hạn.

Một cách chọn giá trị ban đầu:

1. Đo thời gian xử lý trung bình và p95/p99 của listener.
2. Đo kích thước payload trung bình và trường hợp lớn nhất hợp lệ.
3. Xác định số consumer và giới hạn bộ nhớ dành cho xử lý message.
4. Bắt đầu với prefetch thấp hoặc trung bình.
5. Tăng dần từng bước trong môi trường tải đại diện.
6. So sánh throughput, consumer utilization, unacked count, queue depth, latency và memory.
7. Giữ giá trị đáp ứng SLO mà không tạo backlog quá lớn trong consumer.

Đừng chỉ tối ưu số message mỗi giây. Một cấu hình có throughput cao nhưng làm tăng p99 latency, memory pressure hoặc redelivery sau restart có thể làm trải nghiệm nghiệp vụ xấu hơn.

## 7. Prefetch và phân phối công bằng

RabbitMQ thường giao message tới consumer có slot prefetch còn trống. Khi một consumer nhận trước nhiều message và chưa ACK, các message đó đã được phân bổ cho consumer đó. Consumer khác có thể rảnh nhưng không được giao những message đang nằm trong buffer của consumer đầu tiên.

Điều này quan trọng khi thời gian xử lý biến động. Giả sử Consumer A nhận 20 message, trong đó nhiều message cần gọi API chậm; Consumer B xử lý xong nhanh và trở nên rảnh. Nếu A vẫn giữ các message chưa ACK, B không thể lấy lại những message đó. Prefetch cao có thể làm giảm fairness.

Prefetch thấp giúp broker phân phối công việc thường xuyên hơn khi slot được giải phóng. Prefetch bằng 1 thường tạo phân phối công bằng hơn giữa các consumer, đổi lại có thể giảm throughput. Nếu tác vụ có thời gian xử lý đồng đều và payload nhỏ, giá trị lớn hơn có thể tăng hiệu quả.

Prefetch không bảo đảm thứ tự hoàn tất. Với nhiều consumer, message được giao hoặc xử lý song song nên thứ tự ACK có thể khác thứ tự publish. Nếu nghiệp vụ yêu cầu ordering theo aggregate, hãy dùng partition/routing key hoặc thiết kế consumer kiểm tra sequence/version; không dựa vào prefetch để bảo đảm thứ tự.

## 8. Prefetch, memory và backpressure

Prefetch giới hạn số lượng message chưa ACK, không giới hạn tổng số byte. Hai consumer có cùng prefetch nhưng payload khác kích thước có thể tiêu thụ bộ nhớ rất khác nhau.

Ước lượng đơn giản:

**Dung lượng payload in-flight ≈ số consumer × prefetch × kích thước payload trung bình.**

Ví dụ 8 consumer, prefetch 25 và payload trung bình 40 KB có khoảng 8 MB payload thô có thể đang in-flight. Bộ nhớ thực tế cao hơn vì còn object sau deserialize, header, buffer, wrapper, dữ liệu tạm và chi phí runtime. Một payload lớn bất thường có thể làm mức sử dụng bộ nhớ tăng đáng kể.

Backpressure hiệu quả cần kết hợp:

- Prefetch hữu hạn để giới hạn số message chưa ACK.
- Concurrency phù hợp với CPU, connection pool và downstream capacity.
- Giới hạn kích thước message.
- Timeout cho lời gọi phụ thuộc.
- Giới hạn số tác vụ đồng thời khi listener gọi API hoặc cơ sở dữ liệu.
- Retry có backoff và dead-letter cho message không thể xử lý.
- Autoscaling dựa trên backlog và khả năng xử lý, không chỉ CPU.

Nếu consumer gọi một database có connection pool 10 nhưng concurrency tăng lên 50, nhiều listener có thể cùng chờ connection. Tăng prefetch không giải quyết nút thắt này; nó chỉ có thể giữ thêm message trong ứng dụng. Cần cân đối concurrency với giới hạn tài nguyên của các dependency.

## 9. Acknowledgement, lỗi và redelivery

Một message chỉ giải phóng slot prefetch khi broker nhận được acknowledgement phù hợp. Nếu listener xử lý lâu, message tiếp tục nằm trong trạng thái unacknowledged. Nếu listener thất bại và message được requeue, message có thể được giao lại và chiếm slot ở lần xử lý tiếp theo.

Với Spring AMQP AUTO, container thường ACK khi listener hoàn tất thành công. Khi listener ném exception, error handler và cấu hình requeue/reject quyết định message có được giao lại hay chuyển sang dead-letter. Cần kiểm tra cấu hình thực tế của container, chính sách requeue mặc định, retry interceptor và dead-letter topology.

Với MANUAL, listener chịu trách nhiệm ACK/NACK. Ví dụ minh họa:

~~~java
@RabbitListener(
    queues = "orders.confirmed",
    containerFactory = "manualAckListenerContainerFactory"
)
void handle(
        OrderConfirmedMessage event,
        Channel channel,
        Message message) throws IOException {

    long deliveryTag =
        message.getMessageProperties().getDeliveryTag();

    try {
        inventoryService.reserve(event.orderId(), event.eventId());
        channel.basicAck(deliveryTag, false);
    } catch (RecoverableInventoryException exception) {
        channel.basicNack(deliveryTag, false, true);
    } catch (InvalidOrderEventException exception) {
        channel.basicNack(deliveryTag, false, false);
    }
}
~~~

Factory của ví dụ cần được cấu hình với acknowledge mode MANUAL. basicNack với requeue=true yêu cầu broker giao lại message; nếu nguyên nhân lỗi không được khắc phục, message có thể lặp vô hạn. requeue=false từ chối message và có thể chuyển message tới dead-letter exchange nếu queue được cấu hình dead-letter; nếu không có cấu hình phù hợp, message có thể bị loại bỏ.

Không ACK message trước khi nghiệp vụ quan trọng đã commit. Với thao tác có tác dụng phụ bên ngoài, cần idempotency key hoặc cơ chế đối soát vì process có thể dừng sau khi dịch vụ ngoài thực hiện xong nhưng trước khi consumer ACK.

## 10. Poison message và retry loop

Poison message là message luôn thất bại khi xử lý, ví dụ JSON sai schema, thiếu field bắt buộc hoặc dữ liệu vi phạm invariant. Nếu requeue ngay lập tức và prefetch được giải phóng nhanh, broker có thể giao lại cùng message liên tục. Điều này tạo retry loop, tăng CPU/network và cản trở message hợp lệ.

Nên phân loại lỗi:

| Nhóm lỗi | Hướng xử lý |
|---|---|
| Lỗi mạng hoặc dependency tạm thời | Retry có backoff và giới hạn |
| Rate limit | Chờ theo chính sách dịch vụ, sau đó retry |
| JSON malformed hoặc schema không hỗ trợ | Reject và dead-letter để điều tra |
| Dữ liệu nghiệp vụ không hợp lệ | Dead-letter hoặc quy trình xử lý thủ công |
| Lỗi code có thể khắc phục bằng deploy | Giữ message theo chính sách retry có kiểm soát |
| Message đã xử lý trước đó | ACK sau khi xác định duplicate an toàn |

Một retry topology có thể dùng retry queue với TTL và dead-letter exchange để trì hoãn lần giao tiếp theo. Khi số lần thử vượt giới hạn, message được đưa vào dead-letter queue. Cách thiết kế cụ thể phụ thuộc loại queue, broker version và cấu hình Spring AMQP.

Prefetch cao có thể khiến một consumer giữ nhiều poison message hoặc message đang chờ xử lý. Khi channel đóng, nhiều message unacknowledged có thể được requeue cùng lúc, tạo một đợt redelivery lớn. Hãy quan sát redelivery count, unacked count và DLQ để phát hiện tình huống này.

## 11. Tương tác với Spring Modulith application events

Trong một ứng dụng Spring Modulith, có thể có hai đoạn giao tiếp:

1. Module nội bộ phát application event và listener trong cùng ứng dụng xử lý.
2. Adapter externalize một integration event sang RabbitMQ; một ứng dụng hoặc service khác nhận qua AMQP.

Prefetch thuộc phía consumer AMQP. Nó giới hạn message broker giao cho consumer mà chưa được xác nhận. Prefetch không điều chỉnh số application event đang nằm trong Event Publication Registry và không thay thế trạng thái publication của Spring Modulith.

Nếu một Rabbit listener nhận integration event rồi gọi use case hoặc phát application event nội bộ, cần quan sát cả hai ranh giới. ACK AMQP nên phản ánh việc xử lý message theo hợp đồng consumer; publication nội bộ có vòng đời riêng theo listener và registry. Đừng coi ACK từ RabbitMQ là bằng chứng mọi listener nội bộ đã hoàn tất nếu use case chỉ phát event rồi trả về.

Với luồng externalization, adapter gửi event ra RabbitMQ thường quan tâm tới publisher confirms và trạng thái publication. Prefetch không kiểm soát publisher. Publisher confirms giúp producer biết broker đã xác nhận việc publish theo semantics của broker/client; consumer ACK xác nhận việc consumer đã nhận và xử lý message theo hợp đồng của consumer. Hai hướng xác nhận này cần được quan sát riêng.

## 12. Metrics cần theo dõi khi tuning prefetch

Khi thay đổi prefetch, theo dõi đồng thời phía broker và ứng dụng:

| Tín hiệu | Điều cần quan sát |
|---|---|
| messages_ready | Message đang chờ trong queue |
| messages_unacknowledged | Message đã giao nhưng chưa ACK |
| consumer count | Số consumer đang hoạt động |
| consumer utilization/capacity | Mức độ consumer có thể nhận thêm công việc, nếu broker version cung cấp |
| delivery rate | Tốc độ broker giao message |
| ACK rate | Tốc độ consumer xác nhận message |
| redelivery rate | Số message được giao lại |
| listener duration | Thời gian xử lý message |
| queue depth / backlog age | Lượng message chờ và tuổi message cũ nhất |
| JVM memory / GC | Áp lực bộ nhớ do payload và xử lý đồng thời |

Diễn giải các tín hiệu cùng nhau:

- **messages_ready cao, unacknowledged thấp:** consumer có thể thiếu concurrency, bị nghẽn hoặc không nhận message.
- **unacknowledged cao, listener duration cao:** consumer đang giữ nhiều message và xử lý chậm; cân nhắc giảm prefetch hoặc xử lý nút thắt downstream.
- **unacknowledged cao, memory tăng:** payload hoặc buffer có thể vượt khả năng bộ nhớ; giảm prefetch, giới hạn payload hoặc concurrency.
- **ready giảm, throughput tăng, latency ổn định:** thay đổi prefetch có thể cải thiện sử dụng consumer.
- **redelivery tăng:** kiểm tra ACK timing, listener exception, connection churn và retry policy.

Tên metric của broker phụ thuộc phiên bản và loại queue. Dashboard cần ghi rõ đơn vị, phạm vi queue/consumer và khoảng thời gian lấy mẫu. Không so sánh số liệu từ các broker hoặc container khác nhau nếu semantics chưa được chuẩn hóa.

## 13. Kiểm thử prefetch và hành vi consumer

Unit test của listener không đủ để chứng minh broker áp dụng QoS như mong muốn. Cần có kiểm thử tích hợp với RabbitMQ hoặc môi trường tương đương để xác minh message delivery, acknowledgement và redelivery.

Các kịch bản hữu ích:

1. **Prefetch limit:** giữ listener chưa ACK và xác nhận số message giao cho consumer không vượt hạn mức đã cấu hình.
2. **ACK frees a slot:** xác nhận broker giao thêm message sau khi listener ACK một message.
3. **Multiple consumers:** xác nhận phạm vi per-consumer và tổng unacknowledged phù hợp với concurrency.
4. **Manual acknowledgement:** xác nhận ACK/NACK chỉ xảy ra theo nhánh xử lý dự kiến.
5. **Consumer crash:** đóng channel khi còn message unacknowledged và xác nhận broker redelivery theo cấu hình.
6. **Slow dependency:** làm listener chậm để quan sát queue depth, unacked count, latency và memory.
7. **Poison message:** xác nhận retry có giới hạn và dead-letter hoạt động.
8. **Duplicate delivery:** gửi lại cùng eventId và xác nhận consumer idempotent.
9. **Load test:** so sánh nhiều mức prefetch với cùng concurrency và workload đại diện.
10. **Ordering:** xác nhận giới hạn ordering của ứng dụng khi nhiều consumer xử lý song song.

Trong test prefetch, cần cố ý giữ listener ở trạng thái đang xử lý hoặc chặn ACK để quan sát giới hạn. Nếu listener ACK ngay lập tức, số unacknowledged có thể không tăng đủ để chứng minh QoS. Hãy đo tại broker và consumer, không chỉ dựa vào số lần method được gọi.

## 14. Quy trình tuning trong môi trường thực tế

Có thể áp dụng quy trình sau khi triển khai RabbitMQ consumer:

1. Xác định container type, acknowledge mode, số consumer và cách tạo channel.
2. Đo kích thước message, listener duration và giới hạn tài nguyên downstream.
3. Chọn prefetch hữu hạn ban đầu, chẳng hạn 1 hoặc 10 tùy workload.
4. Giữ nguyên concurrency và workload trong lần đo đầu.
5. Đo throughput, p95/p99 latency, messages_ready, messages_unacknowledged, redelivery và memory.
6. Tăng hoặc giảm prefetch từng bước để tìm điểm cân bằng.
7. Sau khi ổn định prefetch, mới thử điều chỉnh concurrency.
8. Kiểm tra lại khi payload size, listener logic hoặc dependency thay đổi.
9. Ghi lại giá trị cấu hình, lý do lựa chọn và kết quả đo để có thể so sánh sau này.

Không có một giá trị prefetch tối ưu cố định cho mọi queue. Queue chứa event nhỏ và xử lý nhanh có thể cần cấu hình khác queue chứa message lớn hoặc tác vụ gọi nhiều dịch vụ ngoài. Giá trị cuối cùng phải dựa trên tải thực tế và SLO của nghiệp vụ.

Prefetch là công cụ điều tiết delivery ở phía RabbitMQ consumer. Khi hiểu rõ unacknowledged message, acknowledgement mode, phạm vi QoS, concurrency và chi phí bộ nhớ, đội phát triển có thể chọn giới hạn phù hợp để cân bằng throughput, fairness và độ trễ. Kết hợp prefetch với idempotency, retry có giới hạn, dead-letter và observability giúp luồng application events qua AMQP ổn định hơn khi tải tăng hoặc consumer gặp sự cố.

