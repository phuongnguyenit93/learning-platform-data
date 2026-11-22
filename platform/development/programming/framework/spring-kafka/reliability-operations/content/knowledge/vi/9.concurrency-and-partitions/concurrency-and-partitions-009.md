# Executor thiếu thread làm consumer không start

Trong Spring Kafka, mỗi Kafka consumer cần một thread để chạy vòng lặp `poll()`, nhận record, gọi listener và phối hợp commit offset. Listener container tạo và chạy các consumer task thông qua một `AsyncTaskExecutor`. Nếu ứng dụng gắn một executor có giới hạn thread quá thấp, dùng chung executor đã bận hoặc cấu hình hàng đợi khiến task consumer bị kẹt, một phần consumer có thể không bắt đầu chạy.

Vấn đề thường xuất hiện sau khi tăng `concurrency`, thêm listener mới hoặc dùng chung một `ThreadPoolTaskExecutor` cho nhiều công việc nền. Container có thể đã được yêu cầu start, nhưng consumer task vẫn nằm trong queue hoặc bị executor từ chối. Khi đó ứng dụng không nhận record như dự kiến dù topic có dữ liệu.

## 1. Vì sao consumer cần thread riêng?

Kafka consumer không phải đối tượng có thể được gọi đồng thời tùy ý từ nhiều thread. Spring Kafka quản lý consumer bên trong listener container và thực hiện các thao tác consumer trên thread do container điều phối. Thread này chạy vòng lặp poll, xử lý record hoặc batch, phối hợp rebalance và commit offset.

Với `ConcurrentMessageListenerContainer`, thuộc tính `concurrency` tạo nhiều child container/consumer để xử lý song song. Mỗi consumer task cần một thread chạy liên tục trong thời gian container hoạt động.

Ví dụ:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-projection",
        concurrency = "4")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

Listener này yêu cầu bốn consumer trong cùng listener container. Nếu listener executor chỉ có thể chạy đồng thời hai consumer task, tối đa hai consumer có thể vào vòng poll; hai task còn lại phải chờ hoặc bị từ chối tùy chính sách executor. Consumer đang chạy thường giữ thread để tiếp tục poll, vì vậy task đang chờ không tự có cơ hội chạy chỉ vì một record đã xử lý xong.

Kafka có thể gán partition cho consumer đang hoạt động. Nếu số consumer lớn hơn số partition, một số consumer sẽ không nhận partition và ở trạng thái idle, nhưng các consumer task vẫn cần thread để tham gia group và duy trì vòng đời. Vì vậy, số thread cần thiết không chỉ phụ thuộc số partition đang có việc.

## 2. Listener task executor hoạt động ở đâu?

Spring Kafka cho phép cấu hình executor chạy listener container thông qua `ContainerProperties.setListenerTaskExecutor(...)`. Executor này chạy consumer task của container. Nó khác với executor mà code nghiệp vụ sử dụng để xử lý tác vụ bất đồng bộ bên trong listener.

```text
ApplicationContext
       |
       v
KafkaListenerEndpointRegistry
       |
       v
Listener container (concurrency = N)
       |
       +---- consumer task 1 ----> listener thread 1 ----> poll()
       +---- consumer task 2 ----> listener thread 2 ----> poll()
       +---- consumer task 3 ----> listener thread 3 ----> poll()
       |
       v
Listener code có thể gọi executor nghiệp vụ riêng nếu cần
```

`listenerTaskExecutor` phải có đủ khả năng chạy các consumer task cần thiết. Nếu listener gọi `@Async` hoặc submit công việc vào một executor khác, đó là một lớp xử lý bổ sung với nhu cầu thread riêng. Không nên nhầm việc listener task đã được khởi chạy với việc tác vụ nghiệp vụ bất đồng bộ đã hoàn tất.

Khi không cấu hình executor riêng, Spring Kafka sử dụng executor mặc định của container theo phiên bản framework. Khi ứng dụng thay bằng một thread pool dùng chung, chính sách `corePoolSize`, `maxPoolSize`, queue capacity và rejection policy của pool bắt đầu ảnh hưởng trực tiếp đến khả năng start consumer.

## 3. Cách thread pool làm consumer task bị kẹt

### Pool nhỏ hơn tổng concurrency

Giả sử ứng dụng có ba listener:

| Listener | Concurrency |
|---|---:|
| `orders-listener` | 4 |
| `payments-listener` | 3 |
| `inventory-listener` | 2 |
| **Tổng** | **9** |

Nếu cả ba listener dùng chung executor chỉ có bốn thread chạy đồng thời, năm consumer task còn lại không thể vào vòng poll. Bốn task đã chạy có vòng đời dài nên tiếp tục giữ thread. Queue có thể tăng mãi hoặc executor từ chối task khi queue đầy.

### Queue lớn che giấu thiếu thread

`ThreadPoolExecutor` thường ưu tiên dùng thread lõi, sau đó xếp task vào queue; chỉ khi queue đầy mới mở rộng tới `maxPoolSize`. Nếu queue không giới hạn, `maxPoolSize` lớn hơn `corePoolSize` có thể không giúp tăng số thread trong tình huống thông thường.

Ví dụ một pool có `corePoolSize=2`, `maxPoolSize=12` và queue không giới hạn. Khi hai consumer task đầu tiên chạy, các task tiếp theo có thể được đưa vào queue. Vì hai consumer đầu tiên tiếp tục giữ thread trong vòng poll, queue không đầy và pool không mở rộng tới 12 thread. Các consumer còn lại chờ lâu dài.

### Executor dùng chung đã bị chiếm hết

Một executor có thể đang chạy các tác vụ khác như gửi email, gọi API, xử lý file hoặc tác vụ `@Async`. Nếu các tác vụ này giữ thread lâu, consumer task mới không còn thread để bắt đầu. Dùng chung pool khiến độ sẵn sàng của Kafka phụ thuộc vào tải của các công việc không liên quan.

### Rejection policy từ chối task

Khi pool đạt giới hạn thread và queue cũng đầy, executor có thể ném `TaskRejectedException` hoặc `RejectedExecutionException`. Tùy điểm gọi và phiên bản Spring Kafka, lỗi có thể xuất hiện trong quá trình khởi động container hoặc được ghi nhận trong log khi consumer task được submit. Cần tìm exception gốc trong log, không chỉ dựa vào trạng thái `isRunning()`.

## 4. Tính số thread cần thiết

Với một executor dùng chung cho nhiều listener container, hãy tính tổng concurrency của tất cả container cùng dùng executor đó.

```text
requiredConsumerThreads = sum(concurrency của từng listener container)
```

Ví dụ:

```text
orders-listener       concurrency = 4
payments-listener     concurrency = 3
inventory-listener    concurrency = 2
--------------------------------------
Tổng consumer task cần chạy đồng thời = 9
```

Pool cần ít nhất chín thread có thể chạy đồng thời để mọi consumer task của ba listener đều hoạt động. Nếu executor còn chạy công việc khác, hãy cộng thêm nhu cầu đó hoặc tách riêng pool để consumer không bị tranh chấp.

| Thành phần | Cần tính thế nào? |
|---|---|
| Một listener với `concurrency=N` | Dự trù N consumer task |
| Nhiều listener dùng chung executor | Cộng concurrency của tất cả listener đó |
| Container tự tạo nhiều consumer | Tính từng child consumer, kể cả consumer có thể idle vì thiếu partition |
| Tác vụ nghiệp vụ chạy qua executor khác | Tính riêng pool nghiệp vụ; không cộng nhầm vào listener task executor nếu hai pool tách biệt |
| Tác vụ nền dùng chung executor | Dự trù thêm thread hoặc tách khỏi pool Kafka |

Đây là mức tối thiểu về khả năng chạy đồng thời, chưa phải sizing cuối cùng cho toàn ứng dụng. Cần dành tài nguyên cho JVM, HTTP server, scheduler, database pool và các thread quản trị. Không nên đặt toàn bộ thread của process cho Kafka consumer.

## 5. Cấu hình ThreadPoolTaskExecutor dành riêng cho Kafka

Một cách dễ kiểm soát là tạo một `ThreadPoolTaskExecutor` chuyên chạy listener container. Ví dụ dưới đây dự trù tối đa sáu consumer task đồng thời:

```java
@Configuration
public class KafkaListenerExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor kafkaListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(6);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("kafka-listener-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Với `queueCapacity=0`, task không bị xếp vào một queue lớn để chờ vô thời hạn; pool phải có thread sẵn sàng để chạy task. Vì `corePoolSize` và `maxPoolSize` cùng bằng sáu, cấu hình này cung cấp tối đa sáu consumer thread. Tổng concurrency của các listener dùng pool này không được vượt quá sáu nếu muốn mọi consumer task chạy đồng thời.

Gắn executor vào container factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            ThreadPoolTaskExecutor kafkaListenerExecutor) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(4);
        factory.getContainerProperties()
                .setListenerTaskExecutor(kafkaListenerExecutor);
        return factory;
    }
}
```

Trong ví dụ, factory của listener orders tạo bốn consumer task và dùng pool có sáu thread. Nếu factory này được dùng bởi các listener khác hoặc có thêm factory cùng tham chiếu executor, hãy tính tổng concurrency của tất cả listener đó trước khi chọn kích thước pool.

`ThreadPoolTaskExecutor` được Spring quản lý vòng đời khi khai báo bằng `@Bean`; không cần tự gọi `initialize()` trong ví dụ thông thường. Nếu dùng `queueCapacity=0`, khi số task được submit vượt `maxPoolSize`, executor có thể từ chối task. Vì vậy, cấu hình phải được đồng bộ với concurrency thực tế và kế hoạch scale.

## 6. Hiểu đúng corePoolSize, maxPoolSize và queueCapacity

Ba thuộc tính này quyết định pool phản ứng ra sao khi có task mới:

| Thuộc tính | Ý nghĩa | Rủi ro khi cấu hình sai |
|---|---|---|
| `corePoolSize` | Số thread lõi được duy trì theo chính sách pool | Quá nhỏ có thể khiến consumer task chờ nếu queue nhận task trước khi pool mở rộng |
| `maxPoolSize` | Số thread tối đa pool có thể tạo | Tăng max không có ích nếu queue không giới hạn luôn nhận task |
| `queueCapacity` | Số task có thể chờ trong queue | Queue quá lớn có thể che giấu thiếu thread; queue đầy dẫn tới rejection |

Với `ThreadPoolTaskExecutor`, queue capacity dương tạo queue có giới hạn; queue capacity âm hoặc rất lớn tùy cách cấu hình có thể dẫn tới queue gần như không giới hạn. Queue capacity bằng không dùng kiểu handoff trực tiếp, khiến pool có thể tăng thread tới `maxPoolSize` trước khi từ chối task.

Đối với consumer task, queue không giải quyết được tình trạng thiếu thread kéo dài. Consumer task thường là tác vụ sống lâu, không phải công việc ngắn kết thúc sau vài mili giây. Nếu pool chỉ chạy được bốn consumer task, bốn task đó có thể giữ thread trong suốt thời gian listener hoạt động; task thứ năm không thể chờ một thread “rảnh” từ bốn task đầu như một tác vụ ngắn thông thường.

Một cấu hình thường dễ dự đoán là đặt `corePoolSize` bằng số consumer task cần chạy đồng thời, `maxPoolSize` bằng hoặc cao hơn theo kế hoạch scale, và queue capacity nhỏ hoặc bằng không. Nếu dùng queue, phải hiểu rõ cách queue ảnh hưởng tới việc pool mở rộng và chấp nhận task chờ.

## 7. Không dùng chung pool một cách thiếu kiểm soát

Executor chung có thể giảm số lượng pool trong ứng dụng, nhưng làm các workload cạnh tranh thread. Một tác vụ HTTP bị treo hoặc một batch xử lý file dài có thể chiếm thread cần thiết để Kafka consumer tiếp tục poll.

Một tình huống nguy hiểm khác là listener task executor và executor xử lý nghiệp vụ dùng chung một pool nhỏ. Consumer thread nhận record rồi submit công việc sang cùng pool và chờ `Future.get()`. Nếu tất cả thread đều đang chạy consumer task và chờ công việc được xếp vào queue của chính pool đó, công việc nghiệp vụ không bao giờ có thread để chạy. Đây là thread starvation hoặc deadlock do thiết kế executor.

Ví dụ mô hình không nên dùng:

```text
Pool có 4 thread
  thread 1: consumer task -> chờ Future từ pool
  thread 2: consumer task -> chờ Future từ pool
  thread 3: consumer task -> chờ Future từ pool
  thread 4: consumer task -> chờ Future từ pool

Queue:
  business task A
  business task B
  business task C
  business task D

Không còn thread để chạy business task trong queue.
```

Tách executor theo vai trò:

```text
kafkaListenerExecutor
  -> chạy vòng poll và listener container

businessExecutor
  -> chạy công việc bất đồng bộ do listener submit

httpExecutor / scheduler
  -> xử lý HTTP client hoặc tác vụ định kỳ
```

Nếu listener thực hiện xử lý đồng bộ, consumer thread có thể chạy trực tiếp phần nghiệp vụ. Nếu listener chuyển công việc sang executor khác, cần quản lý acknowledgment, exception và giới hạn in-flight task. Tách pool không tự giải quyết việc commit offset sớm; listener vẫn phải xác nhận sau khi tác động nghiệp vụ hoàn tất.

## 8. Concurrency phải phù hợp với partition và tài nguyên

`concurrency` quyết định số consumer mà container tạo. Số consumer lớn hơn số partition trong một consumer group không làm tăng số partition được xử lý song song; các consumer thừa sẽ không được gán partition. Dù vậy, các consumer đó vẫn cần thread và tài nguyên để chạy.

Ví dụ topic có ba partition:

| Concurrency | Consumer có thể nhận partition | Hệ quả |
|---:|---:|---|
| 1 | 1 consumer nhận cả ba partition | Ít thread, ít song song |
| 3 | 3 consumer có thể nhận mỗi người một partition | Có thể khai thác song song theo partition |
| 6 | Tối đa 3 consumer nhận partition; phần còn lại idle | Dùng thêm thread mà không tăng song song của topic này |

Khi có nhiều listener topic khác nhau, tổng số consumer task có thể lớn hơn số partition của từng topic. Hãy tính theo từng listener container rồi cộng lại nếu dùng chung executor.

Không nên tăng concurrency chỉ để chữa consumer lag khi executor chưa đủ thread. Tăng concurrency làm tăng nhu cầu thread, socket, memory, connection tới broker và có thể làm tăng áp lực lên database hoặc dịch vụ phụ trợ. Nếu số partition không tăng, thêm consumer có thể không cải thiện throughput.

## 9. Phân biệt thiếu thread với lỗi Kafka khác

Consumer không xử lý record có thể do nhiều nguyên nhân. Hãy xác định consumer task đã chạy hay chưa trước khi thay đổi cấu hình broker hoặc offset.

| Dấu hiệu | Khả năng nguyên nhân | Kiểm tra tiếp theo |
|---|---|---|
| Không có thread `kafka-listener-*` và task bị queue | Executor không cấp thread hoặc chưa được gắn đúng | Pool active count, queue size, cấu hình factory |
| Có `TaskRejectedException` hoặc `RejectedExecutionException` lúc start | Pool đã đạt giới hạn và từ chối task | `maxPoolSize`, queue capacity, concurrency tổng |
| Chỉ một số consumer được start khi concurrency lớn | Pool không đủ thread cho mọi consumer task | Đếm concurrency trên tất cả container dùng pool |
| Consumer đã start nhưng chưa có partition | Rebalance, group membership hoặc partition assignment chưa hoàn tất | Consumer events, group state, topic partition count |
| Consumer đã poll nhưng listener xử lý chậm | Nghiệp vụ chậm, I/O hoặc thread bị block | Listener duration, thread dump, dependency latency |
| Consumer rời group khi xử lý lâu | Vượt `max.poll.interval.ms` hoặc mất heartbeat | Poll interval, xử lý record, rebalance logs |
| Pool có thread nhưng không có record | Topic rỗng, offset ở cuối, group sai hoặc partition khác | Topic data, group ID, committed offset, assignment |

Đặc biệt, thiếu thread trước khi consumer chạy khác với consumer đã chạy nhưng xử lý chậm. `max.poll.interval.ms` thường liên quan đến thời gian giữa các lần poll khi consumer đang hoạt động; nó không tạo thêm thread cho một consumer task còn nằm trong executor queue.

## 10. Quy trình chẩn đoán

### Bước 1: Tính số consumer task cần chạy

Liệt kê tất cả `@KafkaListener`, `concurrency` của từng listener và những factory/container cùng dùng executor. Cộng concurrency để có nhu cầu thread tối thiểu.

```text
orders-listener       4
payments-listener     3
inventory-listener    2
--------------------------------
Tổng                    9 consumer task
```

Kiểm tra cấu hình concurrency từ annotation, factory và cấu hình runtime. Nếu một listener dùng concurrency mặc định, ghi nhận giá trị thực tế mà factory cung cấp.

### Bước 2: Kiểm tra executor được gắn vào container

Tìm nơi tạo `ConcurrentKafkaListenerContainerFactory` hoặc cấu hình `ContainerProperties`. Xác nhận đúng executor được truyền vào `setListenerTaskExecutor(...)`. Kiểm tra xem nhiều factory có đang dùng cùng bean hay không.

Đừng giả định rằng `spring.task.execution.pool.*` tự động cấu hình listener executor. Những thuộc tính đó chỉ ảnh hưởng executor do Spring Boot auto-configure theo cơ chế tương ứng; listener container chỉ dùng pool đó nếu ứng dụng hoặc auto-configuration cụ thể đã gắn nó vào factory.

### Bước 3: Quan sát số thread và queue

Với `ThreadPoolTaskExecutor`, có thể quan sát các chỉ số như pool size, active count, queue size và completed task count. Các chỉ số này giúp phân biệt pool không có thread, pool bận hết thread và task bị queue.

Ví dụ lấy số liệu từ bean:

```java
@Component
public class KafkaExecutorMetrics {

    private final ThreadPoolTaskExecutor kafkaListenerExecutor;

    public KafkaExecutorMetrics(ThreadPoolTaskExecutor kafkaListenerExecutor) {
        this.kafkaListenerExecutor = kafkaListenerExecutor;
    }

    public void logState() {
        ThreadPoolExecutor executor =
                kafkaListenerExecutor.getThreadPoolExecutor();

        log.info("Kafka executor: poolSize={}, active={}, queued={}, completed={}",
                executor.getPoolSize(),
                executor.getActiveCount(),
                executor.getQueue().size(),
                executor.getCompletedTaskCount());
    }
}
```

Trong ứng dụng thực tế, có thể đưa các giá trị này vào Micrometer hoặc hệ thống metrics thay vì chỉ log. Không nên gọi `getThreadPoolExecutor()` trước khi executor đã được khởi tạo; xử lý trường hợp bean chưa sẵn sàng nếu metrics được thu thập rất sớm.

### Bước 4: Kiểm tra thread dump

Thread dump cho biết thread đang chạy consumer loop, đang chờ queue hoặc đang bị block trong một dependency. Tìm prefix thread đã cấu hình, ví dụ `kafka-listener-`. Nếu số thread active luôn bằng giới hạn pool và queue tăng, executor có thể đang bão hòa.

Nếu consumer thread đang chờ `Future.get()` trong khi business task nằm trong queue cùng pool, hãy xem xét starvation do pool dùng chung. Nếu thread đang block ở JDBC hoặc HTTP, đó là vấn đề thời gian xử lý/dependency; cần kiểm tra timeout và khả năng pool nghiệp vụ thay vì chỉ tăng số thread Kafka.

### Bước 5: Xác nhận consumer group

Sau khi chắc chắn consumer task đã chạy, kiểm tra trạng thái group và partition assignment. Có thể dùng lệnh Kafka:

```bash
kafka-consumer-groups.sh \\
  --bootstrap-server kafka.example:9092 \\
  --describe \\
  --group order-projection
```

Nếu group không có member, consumer có thể chưa tham gia group hoặc kết nối/authentication thất bại. Nếu group có member nhưng không có assignment như mong đợi, kiểm tra topic partition, subscription, rebalance và cấu hình group. Lệnh này là một phần chẩn đoán Kafka; nó không thay thế việc kiểm tra executor bên trong JVM.

## 11. Các cách khắc phục

### Tăng pool theo tổng concurrency

Đảm bảo pool có đủ thread chạy tất cả consumer task cần hoạt động đồng thời. Nếu concurrency được tăng từ bốn lên tám, cập nhật sizing executor cùng lúc.

### Tách pool Kafka khỏi tác vụ nền

Tạo executor riêng cho listener container để email, HTTP hoặc scheduler không thể chiếm hết thread cần cho consumer. Tách pool cũng giúp metrics và cảnh báo rõ ràng hơn.

### Điều chỉnh queue capacity

Không dùng queue lớn để che giấu việc thiếu thread. Consumer task là tác vụ dài hạn, vì vậy queue chỉ làm trì hoãn thời điểm consumer tham gia group. Cân nhắc queue nhỏ hoặc zero và cấu hình `maxPoolSize` phù hợp; đồng thời bảo đảm tổng concurrency không vượt năng lực chạy đồng thời của pool.

### Giảm concurrency khi tài nguyên có hạn

Nếu instance chỉ được cấp ít CPU hoặc thread, giảm `concurrency` tới mức executor và các dependency có thể hỗ trợ. Có thể tăng partition hoặc replica sau khi đo throughput, nhưng không nên thêm consumer mà không tính chi phí thread.

### Tránh pool starvation do chờ tác vụ trong cùng pool

Không để consumer task chiếm hết thread rồi chờ các business task được submit vào cùng pool. Tách executor hoặc thiết kế xử lý bất đồng bộ không block; nếu dùng async acknowledgment, cần kiểm soát số tác vụ in-flight và xử lý lỗi rõ ràng.

### Xử lý rejection rõ ràng

Nếu executor từ chối task, log exception với tên listener/container và trạng thái pool. Không dùng `CallerRunsPolicy` một cách tùy tiện cho consumer task: chính thread gọi submit có thể bị buộc chạy một vòng consumer task dài hạn, làm thay đổi luồng lifecycle hoặc block thread quản lý. Chọn rejection policy sau khi hiểu chính xác thread nào gọi submit và cách container xử lý lỗi.

## 12. Tích hợp với Spring Boot

Spring Boot có thể tự cấu hình executor cho một số tác vụ nền của ứng dụng. Tuy nhiên, không nên suy luận rằng cấu hình `spring.task.execution` luôn điều khiển consumer thread của Spring Kafka. Listener container dùng executor được cấu hình trên `ContainerProperties`; muốn sử dụng một bean executor cụ thể, hãy gắn bean đó vào listener container factory.

Ví dụ đặt tên bean tường minh và gắn trực tiếp:

```java
@Bean("kafkaListenerExecutor")
ThreadPoolTaskExecutor kafkaListenerExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("kafka-consumer-");
    return executor;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentListenerFactory(
        ConsumerFactory<String, PaymentEvent> consumerFactory,
        @Qualifier("kafkaListenerExecutor") ThreadPoolTaskExecutor executor) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(5);
    factory.getContainerProperties().setListenerTaskExecutor(executor);
    return factory;
}
```

Trong ví dụ, pool có tám thread và factory tạo năm consumer task. Nếu một factory khác cũng dùng bean này, phải cộng concurrency của factory kia vào tổng nhu cầu. Dùng `@Qualifier` giúp tránh inject nhầm executor khi ứng dụng có nhiều bean `TaskExecutor`.

API và cách tùy biến auto-configured factory có thể khác theo phiên bản Spring Boot/Spring Kafka. Nếu cần giữ nguyên factory do Boot tạo, có thể tùy biến factory qua cơ chế customizer/configurer tương ứng của phiên bản đang dùng; quan trọng là listener container cuối cùng phải nhận đúng executor dự kiến.

## 13. Shutdown và vòng đời executor

Listener consumer task thường chạy lâu dài cho tới khi container dừng. Vì vậy, thứ tự shutdown cần bảo đảm container có cơ hội dừng và kết thúc consumer task trước khi executor bị đóng. Nếu executor shutdown quá sớm, container có thể không submit được task hoặc consumer task đang chạy không được quản lý như dự kiến.

Khi dùng executor bean riêng, để Spring quản lý vòng đời và phối hợp thứ tự dừng với listener container. Cấu hình `setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(...)` có thể hữu ích cho executor, nhưng không thay thế việc gọi lifecycle stop của container đúng cách. Thời gian chờ phải nằm trong ngân sách graceful shutdown của ứng dụng và nền tảng triển khai.

Nếu process bị kill trước khi consumer dừng và commit offset, record chưa commit có thể được giao lại. Đây là lý do listener cần idempotent đối với side effect bên ngoài Kafka. Không nên cố giữ consumer thread vô hạn trong executor shutdown; cần timeout và quy trình dừng rõ ràng.

## 14. Runbook khi consumer không start sau khi tăng concurrency

Giả sử trước đây `orders-listener` chạy với concurrency 2 và executor có hai thread. Sau khi tăng concurrency lên 6, chỉ hai consumer hoạt động. Có thể xử lý theo trình tự:

1. Xác nhận cấu hình concurrency thực tế đã thành sáu và xác định listener factory đang dùng.
2. Kiểm tra `ContainerProperties.listenerTaskExecutor` có trỏ tới pool hai thread hay không.
3. Kiểm tra pool size, active count, queue size và exception rejection.
4. Kiểm tra có listener container khác hoặc tác vụ nền cùng dùng pool hay không.
5. Tăng hoặc tách executor để cung cấp ít nhất sáu thread cho listener này, cộng nhu cầu của container khác nếu dùng chung.
6. Khởi động lại container theo quy trình lifecycle phù hợp; không chỉ tăng queue capacity.
7. Xác nhận đủ consumer task đã chạy, consumer group có member và partition assignment phù hợp.
8. Theo dõi consumer lag, listener duration, thread utilization và tải database sau thay đổi.

Nếu đủ thread nhưng consumer vẫn không tham gia group, chuyển sang kiểm tra broker connectivity, authentication, topic subscription, group ID và rebalance. Không tiếp tục tăng pool khi dấu hiệu cho thấy lỗi nằm ở kết nối hoặc cấu hình Kafka.

## 15. Nguyên tắc thiết kế

| Nguyên tắc | Lý do |
|---|---|
| Tính tổng concurrency của mọi container dùng chung executor | Mỗi consumer task cần thread để chạy poll loop |
| Dành executor riêng cho listener khi tải ứng dụng phức tạp | Tránh tác vụ nền chiếm thread của Kafka |
| Không để queue lớn che giấu thiếu thread | Consumer task là tác vụ dài hạn và có thể nằm chờ vô thời hạn |
| Căn chỉnh pool size với concurrency và giới hạn tài nguyên | Tránh rejection hoặc tiêu thụ quá nhiều thread |
| Quan sát active thread, queue và rejection | Phát hiện sớm starvation trước khi consumer lag tăng cao |
| Phân biệt listener executor với business executor | Tránh deadlock khi consumer task chờ công việc trong cùng pool |
| Dừng container trước khi đóng executor | Đảm bảo consumer task kết thúc theo lifecycle có kiểm soát |

Khi executor thiếu thread, consumer task không thể chạy vòng `poll()` và không tham gia xử lý partition như mong đợi. Hãy tính số consumer task từ concurrency thực tế, bảo đảm listener executor có đủ thread chạy đồng thời, tách pool khỏi các workload cạnh tranh và theo dõi queue/rejection. Khi đủ năng lực chạy task mà consumer vẫn không start, tiếp tục kiểm tra trạng thái container, kết nối Kafka và consumer group để xác định đúng tầng gây lỗi.
