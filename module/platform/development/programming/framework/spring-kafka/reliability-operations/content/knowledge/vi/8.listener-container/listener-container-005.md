# Listener task executor trong Spring Kafka

Trong Spring Kafka, **listener task executor** là `TaskExecutor` mà listener container dùng để chạy các consumer threads. Mỗi consumer thread thực hiện vòng lặp poll, chuyển record tới listener, xử lý acknowledgement và tiếp tục poll. Executor quyết định thread nào chạy vòng lặp đó, cách đặt tên thread và cách cấp phát thread khi có nhiều listener container.

Tên `listenerTaskExecutor` có thể khiến người đọc nghĩ rằng executor này tạo một thread mới cho từng lần gọi `@KafkaListener`. Đó không phải vai trò của nó. Trong Spring Kafka hiện đại, executor được dùng để chạy consumer thread lâu dài của container. Listener thường được gọi tuần tự trên consumer thread tương ứng.

Cấu hình executor đúng giúp ứng dụng khởi động đủ consumer, tránh thiếu thread khi tăng concurrency và làm log dễ truy vết. Cấu hình sai có thể khiến một số container không khởi động, consumer bị chờ trong hàng đợi của thread pool hoặc việc shutdown kéo dài.

## 1. Task executor nằm ở đâu trong kiến trúc?

Spring Kafka cung cấp listener container để quản lý vòng đời của Kafka consumer. Với `@KafkaListener`, endpoint được đăng ký với `KafkaListenerEndpointRegistry`; container được tạo từ `ConcurrentKafkaListenerContainerFactory` hoặc factory tương ứng.

~~~text
Spring Application
       |
       v
KafkaListenerEndpointRegistry
       |
       v
ConcurrentMessageListenerContainer
       |
       +--> child container 1
       |       |
       |       +--> Kafka consumer 1
       |       +--> consumer thread 1
       |                 |
       |                 +--> poll()
       |                 +--> gọi @KafkaListener
       |                 +--> acknowledgement / commit
       |
       +--> child container 2
       |       |
       |       +--> Kafka consumer 2
       |       +--> consumer thread 2
       |                 |
       |                 +--> poll()
       |                 +--> gọi @KafkaListener
       |                 +--> acknowledgement / commit
       |
       +--> child container 3
               |
               +--> Kafka consumer 3
               +--> consumer thread 3
                         |
                         +--> poll()
                         +--> gọi @KafkaListener
                         +--> acknowledgement / commit

             Listener task executor
             cấp thread cho các consumer
~~~

Với `KafkaMessageListenerContainer`, thường có một consumer và một consumer thread. Với `ConcurrentMessageListenerContainer`, container cha quản lý nhiều child container; mỗi child có consumer riêng và cần một thread để chạy.

`ContainerProperties` giữ cấu hình executor thông qua `listenerTaskExecutor`. Executor mặc định là `SimpleAsyncTaskExecutor`. Nếu không cần kiểm soát pool hoặc tên thread riêng, ứng dụng thường có thể dùng mặc định.

## 2. Executor này thực sự chạy việc gì?

Một consumer thread thực hiện một vòng lặp dài trong suốt thời gian container chạy:

1. Gọi `KafkaConsumer.poll()` để lấy record.
2. Chuyển record tới listener adapter.
3. Gọi method `@KafkaListener`.
4. Xử lý acknowledgement, commit offset hoặc transaction theo cấu hình container.
5. Tiếp tục poll cho tới khi container được dừng.

Vì vậy, một thread của executor thường bị chiếm bởi một consumer trong toàn bộ vòng đời chạy của consumer đó. Đây là khác biệt quan trọng so với executor xử lý các tác vụ ngắn, nơi thread lấy một task, chạy xong rồi quay lại pool.

### Executor không tạo một thread cho mỗi record

Giả sử listener có concurrency bằng ba và đang xử lý hàng nghìn record. Container không cần tạo hàng nghìn thread. Nó sử dụng ba consumer thread; mỗi thread xử lý tuần tự record được giao cho consumer tương ứng.

~~~text
Consumer thread 1: poll -> record A -> listener -> poll -> record D -> listener
Consumer thread 2: poll -> record B -> listener -> poll -> record E -> listener
Consumer thread 3: poll -> record C -> listener -> poll -> record F -> listener
~~~

Nếu cần tăng số consumer xử lý song song, hãy điều chỉnh concurrency và số partition. Đổi task executor sang pool lớn hơn tự nó không làm tăng số consumer hay số partition được xử lý.

### Không phải executor để offload business logic

`listenerTaskExecutor` không phải một worker pool riêng để listener gửi từng record sang thread khác rồi trả về ngay. Việc tự offload xử lý sang một executor khác có thể làm thay đổi thứ tự hoàn tất, thời điểm acknowledgement và commit offset.

Nếu cần xử lý bất đồng bộ, hãy sử dụng cơ chế async listener được Spring Kafka hỗ trợ ở phiên bản đang chạy hoặc thiết kế rõ ràng việc manual acknowledgement, thứ tự xử lý và xử lý lỗi. Không chia sẻ Kafka `Consumer` sang thread khác để gọi `poll`, `seek`, `commit` hoặc các API consumer tùy ý; Kafka consumer không thread-safe và được container quản lý trên consumer thread.

## 3. Khai báo listener task executor trong ContainerProperties

Thuộc tính executor được cấu hình trên `ContainerProperties`:

~~~java
factory.getContainerProperties()
        .setListenerTaskExecutor(listenerTaskExecutor);
~~~

API `setListenerTaskExecutor(AsyncTaskExecutor)` được cung cấp từ Spring Kafka 2.8.9. API cũ `setConsumerTaskExecutor(AsyncListenableTaskExecutor)` đã deprecated để chuyển sang `setListenerTaskExecutor`.

Khi đọc tài liệu hoặc mã nguồn theo phiên bản, có thể gặp các tên cũ như `consumerTaskExecutor` hoặc `consumerExecutor`. Hãy dùng API được hỗ trợ bởi dependency thực tế của dự án; với Spring Kafka hiện đại, ưu tiên `setListenerTaskExecutor`.

Executor là cấu hình Spring Framework, không phải thuộc tính Kafka consumer như `max.poll.records` hay `max.poll.interval.ms`. Vì vậy, không đặt nó trong `spring.kafka.consumer.properties`. Hãy inject executor vào container factory và gắn vào `ContainerProperties`.

## 4. Executor mặc định: SimpleAsyncTaskExecutor

Nếu ứng dụng không cung cấp executor riêng, Spring Kafka sử dụng `SimpleAsyncTaskExecutor` cho consumer threads.

Đặc điểm vận hành cần hiểu:

- Executor tạo thread để chạy task khi container cần khởi động consumer.
- Tên thread mặc định có dạng gắn với bean name và số thứ tự consumer, ví dụ `ordersListener-0-C-1`.
- Với concurrent container, mỗi child container có phần định danh riêng trong tên thread.
- `SimpleAsyncTaskExecutor` không phải một pool tái sử dụng thread giống `ThreadPoolTaskExecutor`.
- Có thể dùng mặc định khi số listener và concurrency ở mức phù hợp, nhưng ứng dụng lớn thường muốn kiểm soát số thread và tên thread rõ ràng hơn.

Không nên giả định rằng `SimpleAsyncTaskExecutor` tự giới hạn số thread theo số CPU. Số consumer đang chạy chủ yếu đến từ số container và concurrency được cấu hình. Nếu cần giới hạn tài nguyên, hãy thiết lập executor có giới hạn và bảo đảm đủ thread cho tất cả consumer cần chạy.

## 5. Dùng ThreadPoolTaskExecutor cho consumer threads

`ThreadPoolTaskExecutor` là lựa chọn khi muốn quản lý số thread, thread name prefix và chính sách cấp phát tập trung.

Ví dụ dưới đây tạo pool cố định ba thread cho một listener container có concurrency bằng ba:

~~~java
@Configuration
public class KafkaListenerExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor kafkaListenerTaskExecutor() {
        var executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(3);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("orders-consumer-");

        return executor;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            ThreadPoolTaskExecutor kafkaListenerTaskExecutor) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setListenerTaskExecutor(kafkaListenerTaskExecutor);

        return factory;
    }
}
~~~

Ở đây:

- `corePoolSize=3` giữ ba thread cơ bản.
- `maxPoolSize=3` giới hạn tổng thread của pool ở ba.
- `queueCapacity=0` dùng cơ chế bàn giao trực tiếp thay vì xếp các consumer task vào một hàng đợi dài.
- `threadNamePrefix` giúp nhận diện consumer threads trong log và thread dump.
- `setConcurrency(3)` tạo ba child container cần ba consumer threads.
- `setListenerTaskExecutor` gắn pool vào các consumer do factory tạo.

Bean `ThreadPoolTaskExecutor` được Spring quản lý lifecycle và khởi tạo. Trong ứng dụng thật, cần đặt tên bean rõ ràng và dùng `@Qualifier` nếu có nhiều executor cùng kiểu.

Nếu số child container được cấu hình lớn hơn số thread có thể cấp phát, một số consumer task có thể bị từ chối hoặc chờ trong queue. Container có thuộc tính `consumerStartTimeout` để chờ consumer thread khởi động trước khi ghi nhận cảnh báo; mặc định hiện đại thường là 30 giây. Hãy xem log khởi động và event nếu consumer không bắt đầu đúng hạn.

## 6. Tính số thread cần cấp phát

Với consumer task, hãy tính theo tổng số consumer đang chạy, không chỉ theo số listener method.

Công thức lập kế hoạch đơn giản:

~~~text
Số consumer threads cần có
    = tổng concurrency của các listener container đang chạy
      dùng chung executor
~~~

Ví dụ:

| Listener container | Concurrency | Consumer threads cần |
|---|---:|---:|
| ordersListener | 3 | 3 |
| paymentsListener | 2 | 2 |
| inventoryListener | 1 | 1 |
| **Tổng** | **6** | **6** |

Nếu cả ba container cùng dùng một executor, pool cần đủ sáu thread để cả sáu consumer có thể chạy đồng thời.

Đừng chỉ tính một factory nếu ứng dụng có nhiều `@KafkaListener` hoặc nhiều factory dùng chung executor. Cũng cần tính các container được tạo động nếu chúng dùng cùng pool.

### Concurrency lớn hơn số partition

Nếu topic có hai partition nhưng listener concurrency được đặt bằng năm, Spring có thể tạo năm child consumer; chỉ hai consumer có thể được gán partition trong group ở trạng thái ổn định, các consumer còn lại không có partition để xử lý.

Tuy vậy, mỗi child container vẫn là một consumer task và cần thread để chạy. Do đó, khi sizing executor, dùng concurrency được cấu hình và số container thực tế, không chỉ số partition hiện đang được gán.

Tăng concurrency vượt số partition có thể không tăng throughput nhưng vẫn tiêu thụ thread và consumer connection. Hãy chọn concurrency dựa trên số partition, khả năng xử lý của dependency và mục tiêu throughput.

## 7. Vì sao queue của thread pool cần được cân nhắc?

`ThreadPoolTaskExecutor` thường hoạt động theo thứ tự: sử dụng core threads trước, sau đó đưa task vào queue; chỉ khi queue đầy mới mở rộng tới max pool size.

Đối với consumer task, đây là điều cần chú ý vì task thường sống lâu bằng container. Nếu queue lớn, task consumer mới có thể nằm chờ trong queue trong khi các thread đang chạy bị chiếm lâu dài bởi những consumer khác.

Ví dụ pool có core size hai, max size sáu và queue capacity một trăm. Khi hai consumer task đã chiếm hai core threads, các consumer task tiếp theo có thể được xếp hàng. Pool không nhất thiết mở rộng lên sáu ngay, vì queue chưa đầy.

Đối với các consumer cần khởi động đồng thời, thường nên chọn một trong hai cách:

- Pool cố định có số thread bằng tổng consumer cần chạy, với queue nhỏ hoặc bằng không.
- Pool có giới hạn rõ ràng và cơ chế queue/rejection được thiết kế có chủ đích, đồng thời bảo đảm mọi consumer cần thiết đều có thể bắt đầu.

Không nên đặt queue không giới hạn rồi cho rằng `maxPoolSize` sẽ tự mở rộng pool. Cũng không nên chọn `CallerRunsPolicy` một cách tùy tiện: task consumer có thể chạy trên thread gọi lệnh start, làm việc khởi động container bị chặn hoặc thay đổi thread thực thi ngoài dự kiến.

## 8. Chia sẻ executor giữa nhiều listener container

Có thể chia sẻ một executor giữa nhiều factory hoặc container để quản lý thread tập trung. Khi làm vậy, phải sizing theo tổng concurrency của mọi container cùng dùng pool.

Ví dụ hai factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        @Qualifier("kafkaListenerTaskExecutor")
        ThreadPoolTaskExecutor executor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setListenerTaskExecutor(executor);

    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentsFactory(
        ConsumerFactory<String, PaymentEvent> consumerFactory,
        @Qualifier("kafkaListenerTaskExecutor")
        ThreadPoolTaskExecutor executor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, PaymentEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(2);
    factory.getContainerProperties().setListenerTaskExecutor(executor);

    return factory;
}
~~~

Pool dùng chung cần ít nhất năm consumer threads nếu cả hai listener chạy đồng thời và không có container khác dùng pool.

Nếu pool chỉ có ba thread, orders có thể chiếm hết thread trước khi payments khởi động. Điều đó có thể khiến payments không nhận được consumer thread trong thời gian `consumerStartTimeout`.

### Khi nào nên dùng executor riêng?

Executor riêng cho từng nhóm listener giúp:

- Giới hạn tài nguyên của từng nhóm.
- Tránh listener có concurrency cao chiếm toàn bộ thread của nhóm khác.
- Đặt thread name prefix riêng để theo dõi.
- Điều chỉnh capacity độc lập theo tải và mức độ quan trọng.

Đổi lại, nhiều pool làm tăng số thread tổng cộng và cần quản lý lifecycle nhiều hơn. Hãy chia pool khi có lý do về cô lập tài nguyên hoặc vận hành, không chỉ vì mỗi listener có một tên khác nhau.

## 9. Listener task executor và concurrency có quan hệ thế nào?

`concurrency` quyết định số child consumer container mà một `ConcurrentMessageListenerContainer` quản lý. Executor cấp thread để các child consumer chạy.

Hai cấu hình phối hợp với nhau:

~~~text
factory.setConcurrency(4)
             |
             v
Tạo 4 child consumer containers
             |
             v
Mỗi child cần 1 consumer thread
             |
             v
listenerTaskExecutor phải cấp được 4 threads
~~~

Ví dụ:

~~~java
factory.setConcurrency(4);
factory.getContainerProperties()
        .setListenerTaskExecutor(kafkaListenerTaskExecutor);
~~~

Nếu executor có đủ bốn thread, bốn consumer có thể chạy. Nếu chỉ có hai thread và không có chỗ phù hợp để các task còn lại được chạy, hai consumer còn lại không thể bắt đầu đúng hạn.

Tăng pool size mà không tăng concurrency không làm listener có thêm consumer. Ngược lại, tăng concurrency mà không tăng khả năng cấp thread có thể làm một số child container không khởi động.

Concurrency cũng bị giới hạn hiệu quả bởi số partition được gán. Nếu có bốn consumer nhưng topic chỉ có hai partition, không thể đạt bốn consumer xử lý partition độc lập trong cùng group.

## 10. Phân biệt listener task executor với các executor khác

Một ứng dụng Spring có thể có nhiều loại executor. Không nên dùng chúng thay thế cho nhau mà không xem xét vòng đời và mục đích.

| Thành phần | Mục đích | Vòng đời task |
|---|---|---|
| `listenerTaskExecutor` | Chạy consumer thread của listener container | Task dài hạn, thường tồn tại trong thời gian container chạy |
| Executor của `@Async` | Chạy phương thức bất đồng bộ của ứng dụng | Task nghiệp vụ ngắn hoặc dài tùy ứng dụng |
| `TaskScheduler` | Chạy công việc theo lịch và monitor task | Task định kỳ hoặc có thời điểm chạy |
| Executor của `CompletableFuture` | Chạy callback hoặc tác vụ bất đồng bộ | Task theo từng lần hoàn tất |
| Producer callback executor do ứng dụng tạo | Chạy logic sau khi producer send hoàn tất | Task theo từng lần gửi |

Không nên dùng chung một pool nhỏ cho consumer threads và các tác vụ HTTP hoặc công việc nền ngắn. Consumer task giữ thread lâu dài; nếu tác vụ nghiệp vụ chiếm hết pool, consumer có thể không khởi động hoặc không có thread để tiếp tục poll.

Tương tự, không nên cấu hình một pool có hàng chục consumer threads chỉ để giải quyết nhu cầu `@Async`. Hãy tách tài nguyên theo loại công việc.

## 11. Không offload KafkaConsumer sang nhiều thread

Kafka `Consumer` không thread-safe. Spring Kafka container đảm bảo consumer được sử dụng trong thread quản lý của nó. `listenerTaskExecutor` chỉ cung cấp thread cho container chạy vòng lặp consumer.

Không làm kiểu sau:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(
        ConsumerRecord<String, OrderCreated> record,
        Consumer<?, ?> consumer) {

    businessExecutor.execute(() -> {
        // Không gọi consumer.seek(), poll(), commitSync() hoặc
        // các API Consumer khác từ thread này.
        process(record.value());
    });
}
~~~

Đoạn trên chỉ minh họa ranh giới nguy hiểm. Việc offload như vậy còn tạo thêm vấn đề: listener trả về trước khi xử lý nghiệp vụ hoàn tất, nên container có thể commit offset trong khi side effect chưa thành công. Nếu process lỗi, record có thể đã được xem là xử lý xong.

Nếu cần asynchronous processing, hãy dùng API async listener được hỗ trợ bởi phiên bản Spring Kafka hoặc thiết kế manual acknowledgement và `asyncAcks` với hiểu biết rõ về thứ tự offset, pause và recovery. Không truyền đối tượng Kafka Consumer sang thread nghiệp vụ.

## 12. Thread naming và chẩn đoán

Tên thread giúp phân biệt consumer trong log và thread dump. Mặc định Spring Kafka tạo tên có liên hệ với bean name và child container. Khi dùng executor riêng, có thể đặt prefix:

~~~java
executor.setThreadNamePrefix("orders-consumer-");
~~~

Log có thể hiển thị:

~~~text
orders-consumer-1
orders-consumer-2
orders-consumer-3
~~~

Nếu nhiều listener dùng cùng pool, thread name prefix chung không cho biết thread đang chạy container nào tại mọi thời điểm. Hãy kết hợp thread name với log listener ID, group ID, client ID, topic, partition và offset.

Từ Spring Kafka 3.0.1, container có hỗ trợ tùy chỉnh tên consumer thread thông qua `changeConsumerThreadName` và `threadNameSupplier`. Đây là chức năng đặt tên thread của container; nó không thay đổi số thread hay cơ chế cấp phát của executor.

Một số tín hiệu vận hành cần theo dõi:

- `ConsumerFailedToStartEvent`: consumer không khởi động trong khoảng `consumerStartTimeout`; một nguyên nhân có thể là executor thiếu thread.
- Log cảnh báo consumer start timeout.
- Pool size, active thread count và task rejection của `ThreadPoolTaskExecutor`.
- Số consumer thực sự đã start và partition được assign.
- Consumer lag, poll latency và thời gian listener xử lý.
- Thread dump khi consumer không poll hoặc container không dừng.

Có thể lắng nghe event để phát hiện consumer không khởi động:

~~~java
@Component
public class KafkaConsumerLifecycleMonitor {

    @EventListener
    public void onConsumerFailedToStart(
            ConsumerFailedToStartEvent event) {
        log.error(
                "Kafka consumer failed to start; check task executor capacity: {}",
                event.getSource()
        );
    }
}
~~~

Kiểu event và API getter có thể thay đổi theo phiên bản. Hãy dùng class event của Spring Kafka đang được ứng dụng sử dụng.

## 13. Shutdown và lifecycle của executor

Consumer thread thường chạy cho tới khi listener container dừng. Vì vậy, executor phải còn hoạt động trong khi container cần khởi động, poll và shutdown.

Một trình tự shutdown hợp lý:

~~~text
Ứng dụng bắt đầu shutdown
          |
          v
Ngừng nhận công việc mới
          |
          v
Dừng listener containers
          |
          v
Container đóng Kafka consumers
          |
          v
Các consumer tasks kết thúc
          |
          v
Executor được shutdown theo Spring lifecycle
~~~

Nếu executor bị shutdown trước khi container được dừng, container có thể không start lại được hoặc không cấp được thread cần thiết. Hãy để Spring quản lý bean lifecycle và bảo đảm thứ tự dừng giữa listener container và executor phù hợp với ứng dụng.

Không nên tự gọi `shutdown()` trên executor dùng chung khi một listener vẫn đang chạy. Nếu dùng executor cho nhiều container, chỉ đóng nó sau khi tất cả container phụ thuộc đã dừng.

Khi ứng dụng triển khai lại hoặc dừng trong lúc listener xử lý record, offset chưa commit có thể khiến record được giao lại sau đó. Executor không quyết định semantics commit; acknowledgement mode, transaction và error handler mới kiểm soát việc đó. Listener vẫn cần idempotent nếu nghiệp vụ có thể bị redelivery.

## 14. Cấu hình Spring Boot và custom factory

Spring Boot có các property cho listener như concurrency, ack mode và thời gian poll. Tuy nhiên, một `TaskExecutor` tùy chỉnh là bean của Spring, không phải Kafka client property đơn giản để đặt trong YAML.

Ví dụ YAML cấu hình concurrency:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: record
~~~

Sau đó, cấu hình executor trên factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
kafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        @Qualifier("kafkaListenerTaskExecutor")
        ThreadPoolTaskExecutor executor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setListenerTaskExecutor(executor);

    return factory;
}
~~~

Nếu muốn dùng factory tự động cấu hình của Spring Boot, có thể tùy biến factory bean theo cơ chế cấu hình của phiên bản Boot đang dùng. Khi ứng dụng có nhiều listener, hãy xác định rõ listener nào dùng factory nào để tránh cấu hình executor trên factory không được endpoint sử dụng.

## 15. Những lỗi thường gặp

**Pool có ít thread hơn tổng concurrency**

Một số consumer task bị xếp hàng hoặc bị từ chối. Container có thể phát cảnh báo consumer start timeout. Hãy tính tổng concurrency của tất cả container dùng chung executor.

**Queue quá lớn**

Task consumer mới nằm chờ trong queue vì thread đang chạy các consumer lâu dài. Pool không mở rộng như dự kiến vì queue chưa đầy. Với consumer tasks, nên thiết kế pool theo số thread cần chạy đồng thời.

**Dùng chung pool với @Async hoặc HTTP tasks**

Tác vụ ngắn có thể chiếm thread mà consumer cần. Tách pool hoặc sizing theo tổng công việc và mức độ ưu tiên.

**Tăng executor size nhưng không tăng concurrency**

Số consumer không thay đổi. Pool có thể có nhiều thread nhàn rỗi.

**Tăng concurrency vượt số partition**

Một số consumer không nhận partition, nên throughput không tăng tương ứng nhưng vẫn cần thread và tài nguyên consumer.

**Nhầm executor là cơ chế parallelize listener**

Một consumer thread thường gọi listener tuần tự. Muốn xử lý bất đồng bộ cần API và acknowledgement semantics phù hợp, không chỉ thay executor.

**Tự dùng Kafka Consumer từ thread khác**

Có thể gây lỗi thread-safety và vi phạm quyền sở hữu consumer của container. Để container quản lý consumer API.

**Shutdown executor khi container còn chạy**

Container không còn thread để poll hoặc restart. Hãy dừng container trước khi đóng executor.

**Dùng API cũ**

`setConsumerTaskExecutor` đã deprecated để chuyển sang `setListenerTaskExecutor`. Kiểm tra Spring Kafka version và dùng API phù hợp.

## 16. Quy trình sizing executor cho production

1. Liệt kê tất cả listener container đang chạy và factory mà mỗi listener sử dụng.
2. Ghi lại concurrency của từng container.
3. Nhóm các container theo executor dùng chung.
4. Tính tổng concurrency trong từng nhóm.
5. Cấu hình core/max pool size đủ cho số consumer cần chạy đồng thời.
6. Chọn queue capacity có chủ đích; tránh queue không giới hạn cho các task dài hạn.
7. Đặt thread name prefix riêng để quan sát.
8. Khởi động ứng dụng và xác nhận mọi consumer đã start.
9. Kiểm tra partition assignment để biết concurrency có tạo thêm throughput thực tế hay không.
10. Kiểm tra pool metrics, consumer lag và thời gian xử lý khi tải tăng.
11. Thử shutdown/restart để xác nhận container dừng trước executor.
12. Kiểm tra log consumer start timeout và task rejection khi cấu hình thiếu capacity.

Ví dụ nếu có hai listener với concurrency lần lượt là bốn và hai, cùng dùng một pool, hãy bắt đầu với sáu consumer threads. Sau đó kiểm tra tải và số partition để xác nhận mức concurrency có hiệu quả. Không tăng pool chỉ dựa vào số CPU; consumer threads thường chờ I/O và chạy vòng lặp poll, còn throughput phụ thuộc partition, broker, listener latency và dependency.

## 17. Checklist cấu hình

- Đã xác định `listenerTaskExecutor` đang chạy consumer threads của container.
- Đã phân biệt executor này với pool xử lý từng business task.
- Đã dùng `setListenerTaskExecutor(AsyncTaskExecutor)` trên phiên bản hỗ trợ.
- Đã tính tổng concurrency của tất cả container dùng chung pool.
- Pool có đủ thread cho consumer tasks cần chạy đồng thời.
- Queue capacity và rejection policy được lựa chọn có chủ đích.
- Không dùng chung pool nhỏ với tác vụ HTTP, `@Async` hoặc callback không liên quan.
- Không truy cập Kafka Consumer từ thread khác.
- Đã kiểm tra số partition và concurrency thực tế.
- Thread name giúp nhận diện consumer trong log.
- Có theo dõi consumer start timeout, task rejection, active threads và consumer lag.
- Executor vẫn sống trong thời gian container hoạt động.
- Container được dừng trước khi executor bị shutdown.
- Đã thử khởi động, dừng và khởi động lại ứng dụng.

Listener task executor là cơ chế cấp thread cho các consumer loop do Spring Kafka container quản lý. Hãy sizing nó theo số consumer chạy đồng thời, giữ executor đủ tài nguyên trong toàn bộ lifecycle và tách nó khỏi worker pool xử lý nghiệp vụ. Khi hiểu đúng ranh giới này, việc điều chỉnh concurrency, theo dõi consumer và vận hành shutdown sẽ dễ dự đoán hơn.

## Tài liệu tham khảo

- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka 3.2 — ContainerProperties API](https://docs.spring.io/spring-kafka/docs/3.2.10/api/org/springframework/kafka/listener/ContainerProperties.html)
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
