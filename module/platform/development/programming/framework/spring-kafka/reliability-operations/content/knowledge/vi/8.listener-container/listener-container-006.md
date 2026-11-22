# Consumer thread naming

Trong Spring Kafka, consumer thread naming là cách đặt tên dễ nhận biết cho các thread đang chạy Kafka consumer và listener container. Tên thread xuất hiện trong thread dump, log, tracing và công cụ giám sát JVM. Khi một ứng dụng chạy nhiều listener, nhiều consumer concurrency hoặc nhiều replica, tên thread rõ ràng giúp xác định luồng nào đang poll Kafka, luồng nào đang xử lý record và luồng nào đang chờ tài nguyên.

Thread name là thông tin chẩn đoán của JVM. Nó không quyết định consumer thuộc group nào, không chọn partition và không thay thế Kafka client ID. Để đọc đúng thông tin trong production, cần phân biệt tên container, consumer group ID, client ID và tên thread.

## 1. Thread nào chạy consumer?

Kafka consumer không thread-safe. Một KafkaConsumer cần được sử dụng tuần tự bởi thread quản lý nó, đặc biệt với các thao tác như poll, subscribe, commit và close. Spring Kafka listener container quản lý vòng đời consumer và thread thực hiện vòng lặp poll.

Với listener container thông thường, luồng xử lý khái quát như sau:

~~~text
Spring application
       |
       v
KafkaListenerEndpointRegistry
       |
       v
Listener container
       |
       v
Consumer task / consumer thread
       |
       +---- KafkaConsumer.poll()
       |
       +---- nhận record từ broker
       |
       +---- gọi listener
       |
       +---- quản lý acknowledgement / commit
       |
       +---- tiếp tục poll
~~~

Trong cấu hình listener đồng bộ thông thường, listener được gọi trong luồng xử lý của consumer. Khi ứng dụng chuyển việc sang executor riêng, gọi API bất đồng bộ hoặc sử dụng một mô hình xử lý khác, có thể xuất hiện thêm thread do ứng dụng hoặc framework quản lý. Các thread đó có quy tắc đặt tên riêng và không nhất thiết là consumer thread.

Một số loại thread có thể xuất hiện trong ứng dụng Spring Kafka:

| Loại thread | Nhiệm vụ | Nguồn đặt tên thường gặp |
|---|---|---|
| Consumer thread | Poll Kafka, quản lý consumer và gọi listener theo mô hình đồng bộ | Executor của listener container hoặc cấu hình đổi tên consumer thread |
| Application worker thread | Xử lý công việc được chuyển sang executor riêng | ThreadFactory hoặc prefix của executor do ứng dụng cấu hình |
| Scheduler thread | Chạy tác vụ định kỳ, kiểm tra hoặc tác vụ nội bộ | Scheduler được cấu hình cho container hoặc ứng dụng |
| Web request thread | Xử lý HTTP request nếu ứng dụng có web layer | Web server và executor của web server |

Không nên suy luận rằng mọi thread có chữ kafka trong tên đều là consumer thread. Hãy đối chiếu tên với container, client ID, stack trace và log của ứng dụng.

## 2. Tên thread mặc định của listener container

Spring Kafka tạo consumer task cho từng consumer do listener container quản lý. Khi không cấu hình executor riêng, container sử dụng executor mặc định của nó. Tên thread mặc định thường được tạo từ tên bean/container và phần hậu tố để phân biệt consumer hoặc child container.

Với một listener đơn, tên có thể mang dạng gần như:

~~~text
ordersListener-C-1
~~~

Với container có concurrency lớn hơn một, các child container có thể có thêm chỉ số trong tên, ví dụ:

~~~text
ordersListener-0-C-1
ordersListener-1-C-1
ordersListener-2-C-1
~~~

Đây là ví dụ minh họa hình dạng tên thường gặp, không phải một định dạng ổn định được cam kết cho mọi phiên bản Spring Kafka. Hậu tố và cách đánh số phụ thuộc loại container, bean name, executor và phiên bản framework.

Phần tên gắn với container giúp nhận ra listener nào đang chạy. Phần hậu tố giúp phân biệt các consumer task. Khi thay executor hoặc bật cơ chế đổi tên thread, tên thực tế có thể khác ví dụ trên.

### Đặt tên listener rõ ràng

Với listener khai báo bằng annotation, đặt id có ý nghĩa giúp định danh endpoint/container trong Spring:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service",
        clientIdPrefix = "orders-consumer")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong ví dụ:

- id định danh listener endpoint/container trong Spring Kafka.
- groupId xác định consumer group mà listener tham gia.
- clientIdPrefix tạo tiền tố Kafka client ID cho consumer; Kafka client ID được dùng trong metric và log phía Kafka.
- Tên thread do container/executor quản lý, có thể dùng tên container làm một phần tiền tố.

Ba thuộc tính id, groupId và clientIdPrefix có mục đích khác nhau. Đặt id = ordersListener không có nghĩa group ID hoặc client ID tự động có cùng giá trị trong mọi cấu hình. Nên khai báo group ID và client ID tường minh khi cần khả năng quan sát rõ ràng.

## 3. Concurrency ảnh hưởng đến số thread như thế nào?

ConcurrentMessageListenerContainer có thể tạo nhiều child KafkaMessageListenerContainer. Mỗi child quản lý một KafkaConsumer và một consumer task. Vì vậy, tăng concurrency thường làm tăng số consumer thread của listener.

Ví dụ cấu hình factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Listener dùng factory:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Với concurrency bằng 3, container quản lý ba consumer task cho listener này. Nếu ứng dụng chạy hai replica và mỗi replica có concurrency bằng 3, group có thể có tổng cộng sáu consumer member cho listener đó.

Số thread không đồng nghĩa số partition. Nếu topic có hai partition, chỉ tối đa hai consumer trong cùng group có thể sở hữu partition của topic đó trong assignment ổn định; các consumer còn lại không có partition để đọc. Nếu topic có mười partition và sáu consumer, một số consumer có thể nhận nhiều partition.

Trong Spring Boot, có thể cấu hình concurrency mặc định cho listener container:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Giá trị này áp dụng cho listener container được cấu hình qua auto-configuration, trừ khi listener hoặc factory có cấu hình concurrency riêng. Hãy kiểm tra cấu hình thực tế của từng listener khi ứng dụng có nhiều factory.

Khi điều tra thread dump, hãy kết hợp tên thread với số partition được giao và client ID. Không nên chỉ đếm thread rồi kết luận hệ thống có cùng số consumer đang thực sự xử lý record.

## 4. Phân biệt thread name, listener ID, group ID và client ID

Các định danh này thường xuất hiện cùng nhau trong log nhưng không thể thay thế cho nhau:

| Định danh | Ví dụ | Mục đích |
|---|---|---|
| Listener ID | ordersListener | Nhận diện endpoint/container trong Spring Kafka |
| Consumer group ID | orders-service | Xác định nhóm consumer chia assignment và offset |
| Kafka client ID | orders-consumer-0 | Nhận diện client trong metric và log Kafka |
| Thread name | ordersListener-0-C-1 | Nhận diện luồng thực thi trong JVM và thread dump |
| Application instance ID | orders-pod-2 | Nhận diện replica hoặc instance của ứng dụng |

Một group có thể có nhiều client ID. Một client có thể được chạy trên một consumer thread tại một thời điểm. Khi listener dùng concurrency, mỗi child consumer có thể có client ID riêng được tạo từ prefix và suffix.

Ví dụ đặt clientIdPrefix:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service",
        clientIdPrefix = "orders-consumer")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Kafka client có thể thêm hậu tố để phân biệt các consumer được tạo từ cùng prefix trong container concurrency. Tên client ID thực tế phụ thuộc cách Spring Kafka tạo consumer và cấu hình client.id.

client.id hữu ích khi xem JMX metric hoặc log broker, còn thread name hữu ích khi xem JVM thread dump. Khi hai thông tin có thể liên hệ với nhau, việc tìm consumer gây lag hoặc bị block sẽ nhanh hơn.

## 5. Tùy chỉnh tên thread bằng consumer task executor

Container properties cho phép cấu hình executor chạy consumer task. Một cách đơn giản là dùng SimpleAsyncTaskExecutor với thread name prefix riêng:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    var consumerExecutor =
            new SimpleAsyncTaskExecutor("orders-consumer-");
    factory.getContainerProperties()
            .setConsumerTaskExecutor(consumerExecutor);

    return factory;
}
~~~

Với prefix orders-consumer-, các thread được tạo bởi executor có tên dạng orders-consumer-1, orders-consumer-2 và tiếp tục tăng theo bộ đếm của executor. Tên chính xác còn phụ thuộc executor và vòng đời tạo task.

Một executor riêng hữu ích khi:

- Ứng dụng có nhiều listener và cần phân biệt thread theo luồng nghiệp vụ.
- Thread dump cần cho biết ngay listener nào đang chạy.
- Muốn quản lý executor và prefix nhất quán thay vì dựa vào tên mặc định.
- Cần áp dụng giới hạn hoặc quan sát executor theo từng nhóm listener.

### Dùng ThreadPoolTaskExecutor

Có thể dùng ThreadPoolTaskExecutor nếu muốn kiểm soát pool và lifecycle:

~~~java
@Bean
ThreadPoolTaskExecutor ordersConsumerExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("orders-consumer-");
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(3);
    executor.setQueueCapacity(0);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    executor.initialize();
    return executor;
}
~~~

Gắn executor vào factory:

~~~java
factory.getContainerProperties()
        .setConsumerTaskExecutor(ordersConsumerExecutor);
~~~

Consumer task là tác vụ chạy lâu dài vì nó thực hiện vòng poll cho đến khi container dừng. Vì vậy, pool cần đủ thread cho toàn bộ consumer task được khởi chạy trên executor đó. Nếu pool chỉ có hai thread nhưng factory tạo concurrency bằng bốn, một số container có thể không có thread để chạy hoặc phải chờ tài nguyên tùy chính sách executor.

Không nên dùng queue lớn để che việc pool thiếu thread cho consumer task. Queue chỉ trì hoãn việc khởi động consumer; nó không tăng số consumer có thể poll đồng thời. Hãy tính số consumer task của tất cả container dùng chung executor, không chỉ một listener.

SimpleAsyncTaskExecutor tạo thread mới cho task và không tái sử dụng thread như một pool truyền thống. ThreadPoolTaskExecutor quản lý pool và cần được cấu hình kích thước, queue, shutdown phù hợp. Chọn executor theo số consumer, tài nguyên JVM và cách ứng dụng triển khai.

## 6. Đổi tên consumer thread bằng threadNameSupplier

Một số phiên bản Spring Kafka cung cấp ContainerProperties với các tùy chọn changeConsumerThreadName và threadNameSupplier. Cơ chế này cho phép ứng dụng đặt tên consumer thread dựa trên Kafka Consumer thay vì chỉ dùng prefix do executor tạo.

Ví dụ minh họa:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    var properties = factory.getContainerProperties();
    var sequence = new AtomicInteger();
    properties.setChangeConsumerThreadName(true);
    properties.setThreadNameSupplier(
            consumer -> "orders-consumer-" + sequence.incrementAndGet());

    return factory;
}
~~~

Khi bật changeConsumerThreadName, container sử dụng kết quả từ threadNameSupplier để đổi tên consumer thread theo hỗ trợ của phiên bản Spring Kafka. Ví dụ dùng bộ đếm để tạo tên duy nhất trong vòng đời factory.

Các API này phụ thuộc phiên bản Spring Kafka. Nếu dự án không có các method trên, hãy dùng consumerTaskExecutor với thread name prefix hoặc kiểm tra tài liệu đúng phiên bản trước khi nâng cấp. Không nên thêm code dựa trên API của phiên bản mới vào dự án cũ mà chưa kiểm tra dependency thực tế.

Tên thread nên ngắn, dễ tìm và duy nhất trong phạm vi process. Không đưa token, password, payload hoặc dữ liệu cá nhân vào tên thread. Cũng không nên đặt tên phụ thuộc vào partition assignment hiện tại nếu thread có thể tiếp tục sống qua nhiều lần rebalance và sở hữu partition khác nhau.

## 7. Tên thread và cấu hình @KafkaListener

Annotation @KafkaListener có một số thuộc tính có ảnh hưởng đến định danh container hoặc Kafka client:

~~~java
@KafkaListener(
        id = "paymentEventsListener",
        topics = "payment-events",
        groupId = "payment-projection",
        clientIdPrefix = "payment-projection-client",
        concurrency = "2")
public void handle(PaymentEvent event) {
    projectionService.apply(event);
}
~~~

Trong ví dụ:

- id giúp định danh listener endpoint trong Spring.
- topics xác định topic subscription.
- groupId đặt group ID cho listener.
- clientIdPrefix đặt tiền tố Kafka client ID.
- concurrency đặt số consumer do listener container quản lý.

concurrency có thể được cấu hình tại annotation hoặc listener container factory. Nếu cấu hình ở nhiều nơi, cần biết giá trị nào được áp dụng cho endpoint cụ thể theo phiên bản Spring Kafka và cách tạo container. Tránh khai báo nhiều giá trị khác nhau mà không có chủ đích.

Nếu có nhiều listener, đặt ID theo nghiệp vụ và đặt factory riêng khi chúng cần executor hoặc concurrency khác nhau:

~~~java
@KafkaListener(
        id = "ordersCreatedListener",
        topics = "orders-created",
        groupId = "order-projection",
        containerFactory = "ordersListenerContainerFactory")
public void onOrderCreated(OrderCreated event) {
    orderProjection.update(event);
}

@KafkaListener(
        id = "paymentsCapturedListener",
        topics = "payments-captured",
        groupId = "payment-projection",
        containerFactory = "paymentsListenerContainerFactory")
public void onPaymentCaptured(PaymentCaptured event) {
    paymentProjection.update(event);
}
~~~

Tên listener và thread prefix nên phản ánh cùng một ngữ cảnh nghiệp vụ để dễ liên hệ trong log. Không cần nhồi toàn bộ group ID, topic, partition và pod ID vào thread name nếu những thông tin đó đã được ghi ở log context.

## 8. Tên thread trong log và thread dump

Thread name chỉ hữu ích khi log và công cụ quan sát thực sự hiển thị nó. Với Logback, pattern %thread hiển thị tên thread:

~~~xml
<encoder>
    <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
</encoder>
~~~

Một log có thể trông như:

~~~text
2026-11-15 10:30:12.145 [orders-consumer-2] INFO  OrderListener - Received order event
~~~

Trong production, nên bổ sung các trường có ý nghĩa như application instance, listener ID, group ID, topic, partition và offset vào log message hoặc MDC. Thread name không thay thế các trường này vì thread có thể xử lý nhiều partition và partition ownership có thể thay đổi sau rebalance.

Ví dụ log trong listener:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service")
public void handle(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
            "Processing event key={} topic={} partition={} offset={}",
            record.key(),
            record.topic(),
            record.partition(),
            record.offset());

    orderService.process(record.value());
}
~~~

Khi đọc thread dump bằng jstack, Java Flight Recorder hoặc công cụ APM, hãy kiểm tra:

- Thread name để nhận diện listener/executor.
- Stack trace để biết thread đang ở KafkaConsumer.poll(), listener code, serialization, database call hay chờ lock.
- Trạng thái thread như RUNNABLE, WAITING hoặc BLOCKED.
- Thời gian thread ở trạng thái đó và tần suất lặp lại qua nhiều dump.
- Số thread so với concurrency và số replica mong đợi.

Một thread đang nằm trong KafkaConsumer.poll() không nhất thiết bị treo; đó có thể là trạng thái chờ record bình thường. Một consumer thread thường xuyên nằm trong database call hoặc lock contention có thể làm poll chậm và dẫn đến rebalance nếu vượt giới hạn cấu hình.

## 9. MDC và context khi chuyển công việc sang thread khác

MDC thường được dùng để gắn correlation ID, request ID hoặc thông tin nghiệp vụ vào log. MDC thường dựa trên ThreadLocal, vì vậy giá trị MDC của consumer thread không tự động xuất hiện trong worker thread khác.

Nếu listener xử lý đồng bộ, MDC được thiết lập trên consumer thread có thể tồn tại trong phạm vi xử lý nếu được xóa đúng cách. Nếu listener chuyển việc sang executor, cần truyền context rõ ràng:

~~~java
Map<String, String> context = MDC.getCopyOfContextMap();

workerExecutor.execute(() -> {
    try {
        if (context != null) {
            MDC.setContextMap(context);
        }
        processAsync(event);
    }
    finally {
        MDC.clear();
    }
});
~~~

Đây là ví dụ truyền MDC thủ công. Có thể dùng TaskDecorator hoặc cơ chế context propagation của framework để chuẩn hóa việc sao chép và khôi phục context. Luôn xóa context sau khi task kết thúc vì thread pool tái sử dụng thread; nếu không, log của event sau có thể mang correlation ID của event trước.

Đừng nhầm việc đổi tên thread với việc truyền context. Thread name là nhãn của luồng thực thi; MDC là dữ liệu log gắn với luồng tại một thời điểm. Đổi tên thread không tự đưa group ID, event ID hoặc trace ID vào MDC.

## 10. Thread naming khi có nhiều ứng dụng và replica

Một cluster Kafka có thể được đọc bởi nhiều ứng dụng, mỗi ứng dụng có nhiều replica và mỗi replica có nhiều consumer. Nếu tất cả dùng tên thread chung như kafka-consumer-1, log tập trung sẽ khó xác định thread thuộc ứng dụng nào.

Nên dùng một quy ước có các thành phần vừa đủ:

~~~text
<service>-<listener>-consumer-<index>
~~~

Ví dụ:

~~~text
orders-created-consumer-1
orders-created-consumer-2
payments-captured-consumer-1
payments-captured-consumer-2
~~~

Nếu log và APM đã có service.name, instance.id, client.id và group.id, thread name không nhất thiết phải chứa tất cả các trường đó. Giữ tên ngắn giúp đọc thread dump dễ hơn và tránh tạo tên quá dài.

Khi ứng dụng chạy nhiều replica:

- Dùng application instance ID để nhận diện pod hoặc process trong log và metric.
- Dùng group ID ổn định cho các replica cần chia tải.
- Dùng client ID prefix khác nhau theo listener hoặc nhóm consumer khi cần theo dõi metric.
- Dùng thread name prefix khác nhau cho executor của từng listener.
- Không dùng một group ID khác nhau cho từng replica nếu mục tiêu là các replica chia cùng assignment.

Tên thread không cần duy nhất trên toàn cluster vì thread chỉ tồn tại trong một JVM. Tuy nhiên, tên kết hợp với service và instance ID trong log phải đủ để xác định nguồn phát sinh sự kiện.

## 11. Những lưu ý về executor và vòng đời thread

Consumer thread chạy vòng lặp dài hạn. Do đó, cấu hình executor cho listener container khác với executor xử lý các tác vụ ngắn:

- Pool cần đủ thread cho số consumer task đang chạy.
- Queue lớn không làm tăng số consumer có thể poll đồng thời.
- Nếu pool bị shutdown trước container, consumer task có thể không khởi động hoặc không tiếp tục được.
- Khi shutdown ứng dụng, container nên dừng trước hoặc theo lifecycle được Spring quản lý để consumer có thể đóng đúng cách.
- Không tự ý đổi thread name từ bên trong listener nếu không có lý do rõ ràng; việc này có thể làm tên thread không còn phản ánh container.

Với SimpleAsyncTaskExecutor, mỗi task có thể tạo một thread mới thay vì lấy thread từ pool tái sử dụng. Điều này thuận tiện cho consumer task chạy lâu nhưng vẫn cần giới hạn số task và tài nguyên JVM.

Với ThreadPoolTaskExecutor, đặt core/max pool size phù hợp với tổng consumer task dùng chung executor. Nếu có nhiều listener factory cùng dùng một pool, hãy cộng concurrency của các listener đang hoạt động để tính số thread cần thiết.

Không nên gắn cùng một executor có pool quá nhỏ cho nhiều listener có concurrency cao. Một listener có thể chiếm hết worker thread và khiến listener khác không khởi động. Nếu cần cách ly tài nguyên, tạo executor riêng theo nhóm listener.

## 12. Theo dõi consumer thread trong production

Thread name là một phần của khả năng quan sát. Kết hợp nó với các metric consumer và container để tìm nguyên nhân chậm hoặc rebalance:

| Dấu hiệu | Điều cần kiểm tra |
|---|---|
| Thread không xuất hiện sau khi container start | Executor có được cấp thread không, factory có khởi tạo container không, có lỗi startup không |
| Số thread thấp hơn concurrency | Pool có thiếu worker, queue có bị nghẽn hoặc container có bị pause không |
| Consumer thread thường xuyên bị BLOCKED | Lock contention trong listener hoặc thư viện được gọi |
| Consumer thread ở lâu trong database/network call | Listener đang blocking; đo latency dependency và thời gian xử lý mỗi poll |
| Thread dump có nhiều thread cùng prefix nhưng không có partition | Concurrency có thể lớn hơn số partition hoặc listener subscription không khớp |
| Tên thread không thể liên hệ với listener | Đặt ID container và prefix executor rõ ràng; bổ sung client ID và instance ID vào log |
| Log có thread name thay đổi bất ngờ | Kiểm tra threadNameSupplier, executor, hoặc code tự đổi tên thread |

Nên ghi nhận số consumer đang hoạt động, partition assignment, consumer lag, thời gian xử lý listener, thời gian giữa các lần poll và số lần rebalance. Thread name giúp định vị thread trong JVM, nhưng không thay thế metric group và partition.

## 13. Những hiểu nhầm thường gặp

**Thread name chính là Kafka client ID.** Không đúng. Thread name thuộc JVM; client ID là thuộc tính của Kafka client dùng cho metric và log Kafka.

**Group ID quyết định tên thread.** Không đúng. Group ID xác định consumer group. Thread name thường đến từ container bean name hoặc executor; có thể dùng group ID như một phần prefix nếu ứng dụng chủ động cấu hình.

**Tăng concurrency chỉ làm thay đổi tên thread.** Không đúng. Nó tạo thêm consumer task/member, có thể thay đổi partition assignment, mức song song, số kết nối và tải broker.

**Một thread có tên consumer luôn sở hữu đúng một partition.** Không đúng. Một consumer có thể sở hữu nhiều partition. Assignment thay đổi sau rebalance.

**Đổi tên thread làm consumer có client ID mới.** Không đúng. Thread name và Kafka client ID là hai cấu hình độc lập.

**Tất cả công việc do listener khởi chạy chạy trên consumer thread.** Không đúng. Nếu ứng dụng chuyển việc sang executor hoặc API bất đồng bộ, công việc có thể chạy trên thread khác. Cần quan sát thread thực tế trong log và thread dump.

**Có thể dùng thread pool nhỏ hơn concurrency mà không ảnh hưởng.** Không đúng. Consumer task là tác vụ chạy lâu dài; pool thiếu worker có thể khiến một số container không được chạy.

## 14. Quy trình đặt tên thread cho listener

Khi tạo listener mới, có thể thực hiện theo trình tự sau:

1. Đặt listener ID rõ ràng theo luồng nghiệp vụ.
2. Đặt group ID ổn định cho các replica cần chia tải.
3. Đặt client ID prefix nếu cần theo dõi metric riêng cho listener.
4. Xác định concurrency theo số partition và năng lực xử lý.
5. Dùng tên thread mặc định nếu đã đủ rõ; nếu không, cấu hình consumer task executor với prefix riêng.
6. Nếu phiên bản Spring Kafka hỗ trợ, cân nhắc threadNameSupplier để đổi tên consumer thread có kiểm soát.
7. Cấu hình log pattern có %thread và ghi thêm topic, partition, offset, group ID khi xử lý record.
8. Truyền MDC rõ ràng khi chuyển công việc sang executor khác.
9. Kiểm tra thread dump sau khi ứng dụng khởi động để xác nhận số thread và tên thực tế.
10. Kiểm thử graceful shutdown và restart để bảo đảm executor và container được dừng đúng lifecycle.

Consumer thread naming giúp nhận diện luồng thực thi trong JVM và điều tra vấn đề vận hành. Một quy ước tốt kết hợp tên container dễ hiểu, executor prefix rõ ràng, client ID riêng và log có partition metadata. Khi tách bạch các định danh này, đội vận hành có thể nhanh chóng liên hệ thread đang bị chậm với listener, consumer group và partition mà nó đang xử lý.
