# Tăng consumer JMS và đánh đổi với thứ tự xử lý trong Spring

## Mục tiêu

Một queue JMS có thể nhận message nhanh hơn tốc độ một consumer xử lý. Khi backlog tăng, tăng số consumer là cách phổ biến để khai thác nhiều CPU, I/O và instance ứng dụng hơn. Tuy nhiên, nhiều consumer xử lý song song làm thay đổi thứ tự mà nghiệp vụ quan sát được.

Bài này giải thích cách tăng consumer cho Spring JMS, cách Spring quản lý concurrency, giới hạn của việc scale, và các lựa chọn khi cần vừa tăng throughput vừa giữ thứ tự. Trọng tâm là queue; topic có semantics khác và cần được xử lý riêng.

Luồng cơ bản:

`producer → broker queue → listener container → JMS Session/Consumer → @JmsListener → service/database`

Cần phân biệt ba loại thứ tự:

- **Thứ tự gửi/đến broker:** thứ tự producer gửi và broker chấp nhận message.
- **Thứ tự giao/nhận:** thứ tự broker dispatch message cho consumer.
- **Thứ tự hoàn tất nghiệp vụ:** thứ tự listener hoàn tất xử lý và commit side effect.

Ba thứ tự này có thể khác nhau. Tăng consumer chủ yếu làm tăng khả năng xử lý đồng thời; nó không bảo đảm thứ tự hoàn tất nghiệp vụ.

## 1. Consumer JMS và listener container trong Spring

Một JMS consumer nhận message từ một destination thông qua một JMS Session. Spring quản lý vòng đời consumer bằng listener container, thường là `DefaultMessageListenerContainer` (DMLC), rồi gọi phương thức được đánh dấu `@JmsListener`.

Với Spring Boot, starter JMS tự cấu hình `ConnectionFactory`, `JmsTemplate` và listener infrastructure. Ví dụ:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Phương thức listener được gọi bởi thread của listener container. Khi cấu hình nhiều consumer, container tạo nhiều phiên nhận độc lập; các lời gọi listener có thể chạy đồng thời trên những thread khác nhau.

Các điểm cần nhớ:

- Một consumer xử lý message trên một JMS Session của nó.
- JMS Session không phải đối tượng dùng đồng thời an toàn cho nhiều thread. Không chia sẻ session/consumer giữa các thread ứng dụng.
- Nhiều consumer trên cùng queue cạnh tranh nhận message; broker phân phối công việc giữa chúng.
- Concurrency của listener container là số consumer/phiên nhận hoạt động, không phải số worker thread tùy ý mà listener tự tạo.
- Nếu listener gửi tiếp công việc sang executor bất đồng bộ rồi trả về ngay, broker có thể coi lần nhận đã hoàn tất trước khi công việc thực sự kết thúc. Điều này ảnh hưởng acknowledgement, retry và ordering.

## 2. Cấu hình concurrency bằng Spring Boot

Với Spring Boot hiện đại, có thể cấu hình số consumer tối thiểu và tối đa trong `application.yml`:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 3
      max-concurrency: 10
~~~

Điều này cho phép listener container duy trì tối thiểu ba consumer và có thể tăng lên tối đa mười consumer khi tải tăng. Khi tải giảm, DMLC có thể giảm consumer về mức cơ bản.

Các thuộc tính hiện hành:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.jms.listener.min-concurrency` | Số consumer tối thiểu |
| `spring.jms.listener.max-concurrency` | Số consumer tối đa |
| `spring.jms.listener.auto-startup` | Có tự khởi động listener container hay không |
| `spring.jms.listener.receive-timeout` | Thời gian chờ nhận message giữa các lần poll |
| `spring.jms.listener.session.transacted` | Có dùng JMS Session transaction hay không |

Trong Spring Boot 3.x và 4.x, dùng `min-concurrency` và `max-concurrency`. Một số phiên bản Boot cũ dùng tên `spring.jms.listener.concurrency` cho mức tối thiểu; hãy kiểm tra Common Application Properties của đúng phiên bản đang chạy.

Có thể đặt riêng concurrency cho một endpoint bằng thuộc tính của `@JmsListener`:

~~~java
@JmsListener(
        destination = "orders.queue",
        concurrency = "3-10")
public void receive(OrderEvent event) {
    orderService.process(event);
}
~~~

Chuỗi `3-10` có nghĩa là mức cơ bản ba consumer và mức tối đa mười consumer. Giá trị đơn như `"5"` đặt giới hạn tối đa năm consumer, với mức cơ bản là một trong DMLC.

Cấu hình tại endpoint có thể ghi đè concurrency mặc định của factory. Dùng nó khi các queue có tải hoặc yêu cầu ordering khác nhau.

## 3. Cấu hình bằng DefaultJmsListenerContainerFactory

Nếu cần nhiều listener factory với chính sách khác nhau, tạo factory riêng:

~~~java
@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory scalableQueueFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("3-10");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory orderedQueueFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Chỉ định factory trên endpoint:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "scalableQueueFactory")
public void processInParallel(OrderEvent event) {
    orderService.process(event);
}

@JmsListener(
        destination = "account.events",
        containerFactory = "orderedQueueFactory")
public void processSequentially(AccountEvent event) {
    accountService.apply(event);
}
~~~

Đây là các cấu hình minh họa. Nếu Spring Boot đã tạo factory mặc định, có thể dùng `DefaultJmsListenerContainerFactoryConfigurer` để khởi tạo factory tùy chỉnh với cùng các thiết lập Boot rồi chỉ thay đổi concurrency. Tránh vô tình bỏ qua converter, transaction manager, destination resolver hoặc error handler đang được ứng dụng sử dụng.

DMLC giữ số consumer cơ bản và có thể schedule consumer bổ sung khi có đủ message. Việc tăng/giảm diễn ra theo cơ chế của container, không phải một lần tăng tức thời theo từng message. Theo dõi số consumer đang hoạt động thực tế; giá trị cấu hình tối đa không đồng nghĩa tất cả consumer luôn được tạo.

## 4. Concurrency làm tăng throughput như thế nào?

Giả sử một consumer xử lý trung bình `μ` message mỗi giây và có `n` consumer hoạt động. Mức năng lực lý thuyết gần đúng là:

[
Throughput_{max} approx n 	imes mu
]

Nếu mỗi message mất trung bình 100 ms và một consumer xử lý tuần tự, năng lực lý thuyết của consumer đó khoảng 10 message/giây. Mười consumer có thể đạt gần 100 message/giây nếu công việc độc lập và broker, CPU, database cùng các dependency đủ khả năng đáp ứng.

Đây chỉ là mô hình ước lượng. Throughput thực tế còn phụ thuộc:

- Thời gian xử lý và tỷ lệ thời gian chờ I/O.
- CPU, heap, garbage collection và số thread.
- Connection pool, database pool, giới hạn transaction và lock contention.
- Broker dispatch, persistence, disk I/O, network và số message đang in-flight.
- Kích thước message, converter và chi phí serialize/deserialize.
- Prefetch hoặc consumer window do JMS provider cấu hình.
- Retry, redelivery, transaction commit và acknowledgement.
- Số instance ứng dụng chạy cùng queue.

Nếu consumer bị giới hạn bởi CPU, tăng concurrency quá số core hữu dụng có thể chỉ làm tăng context switching. Nếu consumer chủ yếu chờ database hoặc HTTP, một số concurrency bổ sung có thể che thời gian chờ, nhưng cuối cùng sẽ đẩy tải sang dependency.

Với nhiều instance, tổng consumer là tổng concurrency của tất cả instance. Ví dụ ba pod, mỗi pod có tối đa tám consumer, có thể tạo tới 24 consumer cho queue. Cần tính tổng này khi đặt giới hạn database pool, broker session, connection và downstream rate limit.

## 5. Đo trước khi tăng consumer

Không tăng concurrency chỉ vì thấy queue có backlog. Hãy đo:

- **Queue depth:** số message đang chờ.
- **Oldest message age:** tuổi của message cũ nhất; thường phản ánh độ trễ người dùng cảm nhận tốt hơn chỉ số depth.
- **Enqueue/dequeue rate:** tốc độ message vào và ra queue.
- **Processing duration:** thời gian listener xử lý một message, nên theo dõi p50/p95/p99.
- **In-flight/unacknowledged:** số message đã giao cho consumer nhưng chưa hoàn tất.
- **Active consumer count:** số consumer đang hoạt động thực tế.
- **Redelivery/DLQ:** số lần giao lại và số message chuyển dead-letter queue.
- **CPU, heap, thread, DB pool và downstream latency:** giúp xác định nút thắt nằm ở đâu.

Nếu tốc độ vào `λ` lớn hơn tốc độ xử lý tổng `n × μ` trong thời gian dài, backlog sẽ tăng. Nếu backlog tăng nhưng consumer đã dùng hết CPU hoặc database pool, tăng thêm consumer có thể làm hệ thống chậm hơn.

Little's Law cung cấp một quan hệ hữu ích cho hệ thống ổn định:

[
L = lambda 	imes W
]

Trong đó `L` là số công việc trung bình trong hệ thống, `λ` là throughput trung bình và `W` là thời gian trung bình một công việc nằm trong hệ thống. Công thức giúp liên hệ queue depth, throughput và latency; nó không thay thế việc đo các tầng riêng.

## 6. Vì sao nhiều consumer làm mất thứ tự?

Giả sử broker có các message theo thứ tự:

`A1 → A2 → A3 → A4`

Với một consumer, listener có thể xử lý tuần tự A1, A2, A3, A4. Khi có hai consumer, broker có thể giao:

- Consumer 1: A1, A3
- Consumer 2: A2, A4

Consumer 2 có thể hoàn tất A2 trước khi consumer 1 hoàn tất A1. Hoặc A3 có thể hoàn tất trước A2 nếu thời gian xử lý khác nhau. Vì vậy, thứ tự hoàn tất có thể thành A2, A1, A4, A3 dù broker đã dispatch message theo một trình tự.

Spring Framework ghi rõ rằng khi đăng ký nhiều concurrent consumers trên queue, các bảo đảm ordering bị mất. Với queue có yêu cầu thứ tự, giữ một consumer hoặc dùng cơ chế grouping/partition phù hợp.

Có nhiều nguồn gây đảo thứ tự:

1. Nhiều consumer nhận message đồng thời.
2. Listener gọi executor bất đồng bộ và không chờ công việc hoàn tất.
3. Message có thời gian xử lý khác nhau.
4. Retry/redelivery khiến message lỗi quay lại sau các message khác.
5. Priority, scheduled delivery, expiration hoặc selector ảnh hưởng thứ tự dispatch.
6. Nhiều producer gửi đồng thời; thứ tự nghiệp vụ toàn cục không tự xuất hiện chỉ vì dùng một queue.
7. Consumer commit side effect theo thứ tự khác với thứ tự nhận.

Do đó, "broker giao theo thứ tự" không đồng nghĩa "nghiệp vụ hoàn tất theo thứ tự".

## 7. Khi nào nên giữ một consumer?

Dùng concurrency bằng một khi queue cần thứ tự xử lý tuần tự nghiêm ngặt:

~~~java
@JmsListener(
        destination = "payments.ordered",
        concurrency = "1")
public void process(PaymentCommand command) {
    paymentService.apply(command);
}
~~~

Cách này phù hợp khi:

- Tất cả message trong queue phải được xử lý tuần tự.
- Lưu lượng thấp và backlog không đáng kể.
- Các thao tác có phụ thuộc trạng thái chặt chẽ.
- Nghiệp vụ chưa có partition key rõ ràng.
- Đơn giản và khả năng dự đoán quan trọng hơn throughput tối đa.

Giới hạn là chỉ một message được xử lý tại một thời điểm trên listener đó. Khi một message mất nhiều thời gian hoặc bị retry, message phía sau phải chờ. Một poison message có thể làm queue bị nghẽn nếu policy cứ redeliver nó ở đầu luồng.

Một consumer cũng chỉ giữ thứ tự trong phạm vi mà broker và producer bảo đảm. Nếu nhiều producer cùng gửi message liên quan, hãy thêm sequence/version nghiệp vụ thay vì giả định có một thứ tự toàn cục.

## 8. Tăng concurrency nhưng giữ thứ tự theo nghiệp vụ với JMSXGroupID

Nhiều hệ thống không cần thứ tự toàn cục. Chúng chỉ cần message của cùng một thực thể được xử lý tuần tự, ví dụ:

- Các thay đổi của cùng một order.
- Các giao dịch của cùng một account.
- Các sự kiện của cùng một customer.
- Các lệnh của cùng một device hoặc aggregate.

Apache ActiveMQ Artemis hỗ trợ message grouping qua thuộc tính JMS `JMSXGroupID`. Broker ghim các message cùng group ID vào cùng một consumer. Các group khác nhau có thể được phân phối cho các consumer khác nhau.

Ví dụ producer gắn group ID bằng order ID:

~~~java
public record OrderEvent(
        String orderId,
        long version,
        String status) {}

@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderEvent event) {
        jmsTemplate.convertAndSend(
                "orders.events",
                event,
                message -> {
                    message.setStringProperty(
                            "JMSXGroupID",
                            event.orderId());

                    message.setLongProperty(
                            "aggregateVersion",
                            event.version());

                    return message;
                });
    }
}
~~~

Listener có thể dùng nhiều consumer:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(
            destination = "orders.events",
            concurrency = "4-16")
    public void receive(OrderEvent event) {
        orderService.applyInOrder(event);
    }
}
~~~

Với Artemis, các message có cùng `JMSXGroupID` được chuyển tới cùng consumer, kể cả khi queue có nhiều consumer. Điều đó cho phép xử lý tuần tự trong từng group và song song giữa các group.

Điều kiện để cách này giữ được thứ tự nghiệp vụ:

- Producer phải gắn cùng group ID cho mọi message thuộc cùng aggregate.
- Producer phải gửi các message của một group theo sequence nghiệp vụ đúng.
- Listener xử lý đồng bộ tới khi hoàn tất; không trả về rồi đưa message sang executor khác để chạy song song.
- Transaction/acknowledgement phải phản ánh thời điểm nghiệp vụ hoàn tất.
- Nếu có nhiều producer cùng phát message cho một group, cần cơ chế cấp sequence và điều phối thứ tự ở producer hoặc domain layer.

`JMSXGroupID` là khả năng phụ thuộc broker. Kiểm tra tài liệu provider đang dùng trước khi dựa vào nó trong production. ActiveMQ Artemis và ActiveMQ Classic đều có tài liệu message grouping, nhưng chi tiết cấu hình và hành vi khi failover có thể khác nhau.

## 9. Đánh đổi của message grouping

Message grouping giúp mở rộng theo key, nhưng không biến một group thành công việc song song:

- Mọi message cùng group được xử lý tuần tự bởi một consumer tại một thời điểm.
- Một group nóng có thể trở thành nút thắt, dù các consumer khác còn rảnh.
- Số group khác nhau và mức phân bố giữa các group quyết định mức song song thực tế.
- Nếu chỉ có một group, tăng consumer không giúp tăng throughput cho group đó.
- Khi consumer sở hữu group đóng hoặc chết, broker có thể gán group cho consumer khác. Cần kiểm tra transaction và redelivery để tránh side effect lặp.
- Nếu listener offload xử lý sang executor, broker grouping chỉ bảo đảm consumer nhận message; nó không tự bảo đảm các task bất đồng bộ của group hoàn tất theo thứ tự.

Artemis cũng lưu ý rằng một khối message grouped ở đầu queue có thể tạm thời làm giảm concurrent processing của các message không thuộc group do FIFO semantics. Nếu lưu lượng grouped và non-grouped có đặc tính khác nhau, cân nhắc tách chúng sang các queue riêng.

Không tạo group ID quá thô. Ví dụ, nếu dùng `"orders"` làm group ID cho mọi message, toàn bộ queue trở thành một luồng tuần tự. Hãy chọn key theo aggregate cần bảo vệ, chẳng hạn order ID hoặc account ID.

## 10. Partition queue theo key

Nếu broker không hỗ trợ message grouping phù hợp, có thể partition bằng nhiều queue:

1. Tạo N queue, ví dụ `orders.0` đến `orders.7`.
2. Tính partition từ khóa nghiệp vụ, chẳng hạn `hash(orderId) % N`.
3. Producer gửi mọi message của cùng order vào cùng queue.
4. Mỗi queue có một consumer tuần tự hoặc một consumer group được kiểm soát.
5. Các queue khác nhau được xử lý song song.

Ví dụ:

~~~java
int partitionFor(String orderId, int partitionCount) {
    return Math.floorMod(orderId.hashCode(), partitionCount);
}

void publish(OrderEvent event) {
    int partition = partitionFor(event.orderId(), 8);
    String destination = "orders." + partition;

    jmsTemplate.convertAndSend(destination, event);
}
~~~

Partitioning tạo ra một số luồng tuần tự độc lập. Nếu có tám queue và mỗi queue một consumer, tối đa tám partition có thể chạy đồng thời; mỗi order vẫn ở một partition.

Cần lưu ý:

- Cùng key luôn phải dùng cùng partition function và cùng số partition.
- Thay đổi số partition có thể làm key chuyển sang queue khác trong khi message cũ còn tồn đọng. Phải có kế hoạch drain, migration hoặc versioned partition mapping.
- Một partition có thể nóng hơn các partition khác.
- Cần quản lý retry/DLQ và replay theo từng partition.
- Không gửi message cùng aggregate sang hai queue khác nhau trong cùng thời gian nếu yêu cầu ordering nghiêm ngặt.

## 11. Sequence number và kiểm tra thứ tự ở domain layer

Ngay cả khi dùng một consumer hoặc message group, nên có sequence/version nghiệp vụ để phát hiện message trùng hoặc đến sai thứ tự.

Ví dụ một aggregate có các version 41, 42, 43. Consumer lưu version cuối đã xử lý:

- Nhận version 42 khi đang ở 41: xử lý và cập nhật lên 42.
- Nhận version 42 lần nữa khi đang ở 42: nhận diện duplicate và bỏ qua theo idempotency policy.
- Nhận version 44 khi đang ở 42: thiếu version 43; giữ lại, retry hoặc yêu cầu replay theo chính sách.
- Nhận version 41 khi đang ở 42: message cũ; không áp dụng lại side effect.

Pseudocode:

~~~java
@Transactional
public void applyInOrder(OrderEvent event) {
    long currentVersion =
            orderRepository.currentVersion(event.orderId());

    if (event.version() <= currentVersion) {
        return; // duplicate hoặc event cũ đã được xử lý
    }

    if (event.version() != currentVersion + 1) {
        throw new OutOfOrderEventException(
                event.orderId(),
                currentVersion,
                event.version());
    }

    orderRepository.apply(event);
    orderRepository.updateVersion(
            event.orderId(),
            event.version());
}
~~~

Đây là logic minh họa; cách retry và transaction cần khớp với broker. Nếu ném exception để rollback message, broker có thể redeliver liên tục một message có version bị thiếu. Có thể cần retry có backoff, parking queue hoặc một cơ chế giữ message chờ version trước.

Sequence number bảo vệ tính đúng đắn khi có reordering; nó không tự sắp xếp lại message. Nếu cần buffer/resequence, phải thiết kế nơi lưu các message đến sớm, timeout chờ gap và cách xử lý khi message thiếu không bao giờ tới.

## 12. Retry, redelivery và poison message

Tăng concurrency làm việc điều tra thứ tự khi lỗi phức tạp hơn. Một message có thể thất bại trong consumer A rồi được redeliver sau khi consumer B đã xử lý message tiếp theo.

Cần quyết định:

- Retry ngay trong listener hay trả lỗi để broker redeliver?
- Có giới hạn số lần thử và backoff hay không?
- Khi hết số lần thử, message đi đâu?
- DLQ replay có phải giữ nguyên sequence/version không?
- Message sau có được phép tiếp tục nếu message trước chưa xử lý thành công không?

Với strict order, nếu message version 10 lỗi và version 11 được xử lý trước, state có thể sai. Có thể cần dừng group/partition, chuyển message lỗi sang parking queue và chỉ mở lại sau khi sửa hoặc replay. Với Artemis message groups, kiểm tra broker behavior khi message rollback, redelivery và consumer failover.

Không dùng retry vô hạn không backoff. Một poison message có thể tạo vòng lặp, tăng tải broker và giữ group không tiến triển. Thiết kế idempotent handler, giới hạn delivery attempts, DLQ và công cụ replay có kiểm soát.

Nếu listener ghi database và acknowledge JMS, hãy chọn transaction semantics rõ ràng. JMS local transaction không tự động atomic với database transaction độc lập. Dùng JTA/XA khi thật sự cần distributed atomic commit; trong nhiều hệ thống, inbox/outbox và idempotency là lựa chọn thực tế hơn.

## 13. Queue và topic không scale giống nhau

Queue có competing consumers: nhiều consumer cùng nhận message từ một queue, mỗi message được một consumer xử lý theo semantics của broker.

Topic có publish/subscribe: mỗi subscription nhận bản sao của message. Nếu tạo nhiều subscriber độc lập, mỗi subscriber đều nhận message; đó không phải là cách chia tải như queue.

Vì vậy:

- Với queue, tăng concurrent consumers là cách phổ biến để chia tải.
- Với topic, nhiều subscription thường có nghĩa là nhiều bản sao cho nhiều subscriber.
- Nếu cần chia tải trong một topic subscription, chỉ dùng shared subscription khi JMS provider hỗ trợ và cấu hình đúng. Kiểm tra ordering và failover semantics của provider.
- Spring Framework khuyến cáo không tăng concurrency cho topic listener theo cấu hình thông thường nếu không có setup vendor-specific phù hợp.

Không dùng `spring.jms.pub-sub-domain=true` rồi tăng concurrency như thể đó là queue. Hãy xác định rõ queue, topic, durable subscription và shared subscription theo nhu cầu.

## 14. Prefetch, in-flight messages và fairness

Broker có thể đẩy trước một số message cho mỗi consumer để giảm round trip. Tên và cách cấu hình phụ thuộc provider, ví dụ prefetch size ở ActiveMQ Classic hoặc consumer window size ở Artemis.

Prefetch lớn có thể:

- Tăng throughput khi consumer xử lý nhanh và ổn định.
- Làm một consumer giữ nhiều message chưa xử lý trong khi consumer khác rảnh.
- Tạo mất cân bằng khi message có thời gian xử lý rất khác nhau.
- Làm shutdown/rebalance chậm hơn vì message đã được dispatch nhưng chưa hoàn tất.
- Tác động tới thứ tự và latency khi có retry hoặc consumer fail.

Prefetch nhỏ hơn có thể cải thiện fairness và giảm số message in-flight nhưng tăng overhead network/dispatch. Không có một giá trị đúng cho mọi queue; đo trên workload thật và đọc tài liệu broker.

Cũng cần theo dõi số session/consumer và connection. Tăng consumer không đồng nghĩa chỉ tăng thread; nó làm tăng tài nguyên phía broker và phía client.

## 15. Quy trình tăng consumer an toàn

Một quy trình thực tế:

1. Đo queue depth, oldest age, enqueue/dequeue rate, processing latency và resource usage.
2. Xác định queue có yêu cầu global order, per-key order hay không cần order.
3. Bắt đầu từ concurrency hiện tại và tăng theo bước nhỏ, ví dụ 1 → 2 → 4 → 8.
4. Sau mỗi bước, đo throughput, p95/p99 latency, CPU, DB pool, broker resource và redelivery.
5. Kiểm tra các invariant nghiệp vụ: version không nhảy, không có duplicate side effect, group/partition giữ đúng key.
6. Đặt max concurrency dựa trên giới hạn dependency, không chỉ dựa trên số CPU.
7. Có khả năng rollback cấu hình nhanh khi latency hoặc error rate tăng.
8. Kiểm thử cả scale-out nhiều instance, restart consumer, broker failover và DLQ replay.

Nếu queue có message group, theo dõi throughput theo group hoặc partition để phát hiện hot key. Throughput tổng có thể tốt nhưng một account/order cụ thể vẫn bị chậm.

## 16. Kiểm thử concurrency và ordering với broker thật

Unit test cho service không chứng minh broker grouping hoạt động. Dùng integration test với broker thật mà production sử dụng để kiểm tra:

- Gửi nhiều message với cùng group ID và sequence 1..N; xác nhận listener áp dụng theo thứ tự.
- Gửi message thuộc nhiều group; xác nhận các group khác nhau có thể xử lý đồng thời.
- Tăng concurrency và số instance; xác nhận cùng group vẫn được broker pin theo provider semantics.
- Tạo xử lý chậm có chủ đích cho một message; kiểm tra các message cùng group không vượt qua nó.
- Ném exception; kiểm tra redelivery, transaction rollback và ảnh hưởng đến message tiếp theo.
- Dừng consumer đang sở hữu group; kiểm tra consumer khác tiếp nhận group và không tạo side effect trùng.
- Gửi message có version trùng, thiếu hoặc cũ; xác nhận idempotency và gap handling.
- Replay message từ DLQ; xác nhận thứ tự và sequence policy.

Một test đơn giản có thể dùng `CountDownLatch` để chờ N message, một collection thread-safe để ghi thứ tự nhận và assertion sau khi listener hoàn tất. Không dùng `Thread.sleep` cố định; dùng timeout hữu hạn và condition-based waiting. Dùng queue riêng cho test để không nhận message tồn đọng từ lần chạy khác.

## 17. Lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Tăng concurrency từ 1 lên 10 mà không kiểm tra nghiệp vụ | Message cùng entity hoàn tất sai thứ tự | Phân loại yêu cầu global/per-key/no order trước khi scale |
| Dùng cùng một group ID cho mọi message | Tất cả message bị tuần tự hóa vào một consumer | Chọn group key theo aggregate |
| Dùng group ID khác nhau cho các message cùng order | Một order có thể chạy đồng thời trên nhiều consumer | Gắn ổn định theo order/account/device ID |
| Listener trả về trước khi task async hoàn tất | Broker có thể acknowledge trước khi nghiệp vụ xong; task có thể chạy sai thứ tự | Chờ xử lý hoàn tất trong listener hoặc dùng cơ chế durable work khác |
| Dùng nhiều topic subscriber để chia tải | Mỗi subscriber nhận một bản sao | Dùng queue hoặc shared subscription đúng semantics |
| Chỉ nhìn queue depth | Không biết consumer có bị nghẽn ở DB hay không | Theo dõi latency, in-flight, CPU và downstream pool |
| Prefetch quá lớn | Một consumer giữ nhiều message trong khi consumer khác rảnh | Điều chỉnh theo broker và phân bố thời gian xử lý |
| Retry message lỗi ngay lập tức | Poison message lặp vô hạn và group không tiến triển | Backoff, giới hạn retry, DLQ và replay |
| Thay đổi số partition khi queue còn message | Cùng key có thể đi vào hai partition | Drain/migrate có kế hoạch và giữ mapping version |
| Dùng một consumer nhưng nhiều producer không có sequence | Không có thứ tự nghiệp vụ toàn cục rõ ràng | Cấp sequence theo aggregate và kiểm tra version |

## 18. Checklist triển khai

- [ ] Đã xác định queue cần global order, per-key order hay không cần order.
- [ ] Đã đo throughput, latency, queue age và resource trước khi tăng consumer.
- [ ] Đã chọn min/max concurrency theo giới hạn của broker, database và downstream.
- [ ] Đã tính tổng consumer trên tất cả application instances.
- [ ] Đã giữ concurrency bằng 1 cho luồng cần tuần tự toàn cục.
- [ ] Đã dùng JMSXGroupID hoặc partition key ổn định cho per-key ordering nếu broker hỗ trợ.
- [ ] Listener không offload công việc rồi acknowledge trước khi xử lý hoàn tất.
- [ ] Có sequence/version và idempotency để phát hiện duplicate hoặc out-of-order event.
- [ ] Retry, redelivery, DLQ và replay không phá invariant nghiệp vụ.
- [ ] Prefetch/consumer window được đo và điều chỉnh theo provider.
- [ ] Topic/shared subscription được cấu hình theo đúng semantics.
- [ ] Có integration test với broker thật cho concurrency, grouping, failover và redelivery.
- [ ] Dashboard theo dõi active consumers, queue age, throughput, processing latency và DLQ.

## Tài liệu tham khảo

- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, listener container factory và cấu hình concurrency.
- [Spring Framework — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): concurrent consumers, dynamic scaling và cảnh báo về ordering.
- [Spring Boot — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): JMS auto-configuration, listener factory và transaction behavior.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.jms.listener.min-concurrency`, `max-concurrency` và các thuộc tính listener.
- [Apache ActiveMQ Artemis — Message Grouping](https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html): `JMSXGroupID`, consumer pinning, group lifecycle và trade-offs.
- [Apache ActiveMQ Classic — Message Groups](https://activemq.apache.org/components/classic/documentation/message-groups): sticky load balancing và per-group ordering.
- [Spring Framework — Receiving JMS Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener transactions, rollback và message acknowledgement.

