# DefaultMessageListenerContainer và vòng lặp nhận thông điệp

Trong Spring JMS, **DefaultMessageListenerContainer (DMLC)** là container quản lý việc nhận message từ Queue hoặc Topic và gọi listener trong các luồng làm việc riêng. Điểm đặc trưng của nó là dùng JMS API theo cơ chế polling: mỗi worker lặp lại lời gọi **MessageConsumer.receive()**, chờ message đến rồi chuyển message cho listener xử lý.

DMLC quản lý Connection, Session, MessageConsumer, thread, transaction, acknowledgement, cache và khả năng phục hồi khi broker tạm thời mất kết nối. Nhờ đó, ứng dụng không phải tự viết vòng lặp receive, tự tạo consumer cho từng worker hay tự xử lý toàn bộ vòng đời resource.

## 1. DMLC nằm ở đâu trong Spring JMS?

Spring JMS cung cấp các abstraction để ứng dụng làm việc với JMS provider:

- **ConnectionFactory:** tạo Connection đến broker hoặc JMS provider.
- **Connection:** đại diện kết nối tới provider.
- **Session:** ngữ cảnh single-threaded để tạo message, producer, consumer và quản lý transaction/acknowledgement.
- **MessageConsumer:** nhận message từ Queue hoặc Topic.
- **MessageListener:** callback xử lý một message.
- **MessageListenerContainer:** quản lý listener và các resource cần thiết để nhận message.

DMLC thuộc package **org.springframework.jms.listener** và kế thừa **AbstractPollingMessageListenerContainer**. Container dùng các lời gọi JMS client thông thường, cụ thể là vòng lặp các lần gọi **receive()** trên MessageConsumer. Cách này không yêu cầu JMS provider phải cung cấp ServerSessionPool.

DMLC phù hợp với môi trường JMS độc lập và môi trường Jakarta EE. Nó hỗ trợ concurrency, transaction do Spring quản lý, tự phục hồi khi broker tạm thời không sẵn sàng, đồng thời cho phép start, stop và thay đổi một số cấu hình trong lúc chạy.

### 1.1. DMLC khác SimpleMessageListenerContainer thế nào?

Spring có hai container JMS phổ biến:

| Tiêu chí | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
|---|---|---|
| Cách nhận | Polling bằng vòng lặp MessageConsumer.receive() | Đăng ký MessageListener trực tiếp với JMS provider |
| Thread thực thi | Các invoker task do Spring TaskExecutor quản lý | Provider điều phối callback theo cơ chế JMS |
| Concurrency | Có thể tăng/giảm động theo cấu hình | Chủ yếu tạo số consumer cố định lúc khởi động |
| Transaction | Hỗ trợ local JMS transaction và external transaction manager | Phạm vi hỗ trợ transaction hạn chế hơn |
| Phục hồi broker | Có cơ chế tự phục hồi và retry thiết lập consumer | Cơ chế phục hồi đơn giản hơn |
| Trường hợp sử dụng | Phần lớn ứng dụng cần khả năng điều chỉnh và phục hồi | Luồng đơn giản, số consumer cố định và provider phù hợp |

DMLC thường là lựa chọn mặc định khi cần kiểm soát concurrency, transaction hoặc khả năng phục hồi. SimpleMessageListenerContainer vẫn có thể phù hợp khi yêu cầu rất đơn giản và muốn dựa nhiều hơn vào callback do provider quản lý.

## 2. Vòng lặp receive hoạt động như thế nào?

Khi container khởi động, DMLC tạo số consumer ban đầu theo cấu hình. Mỗi consumer có một JMS Session và một MessageConsumer tương ứng. Container tạo invoker task và giao task cho Spring TaskExecutor.

Mỗi invoker thực hiện chu trình:

1. Lấy hoặc thiết lập Connection, Session và MessageConsumer theo cache level.
2. Gọi MessageConsumer.receive() với receive timeout đã cấu hình.
3. Nếu nhận được message, chuyển message đến listener.
4. Thực hiện commit, rollback hoặc acknowledgement theo transaction/acknowledgement mode.
5. Tiếp tục vòng lặp để nhận message tiếp theo.
6. Nếu không nhận được message trong khoảng timeout, đánh dấu lần nhận đó là idle và áp dụng chính sách điều phối consumer.
7. Khi container dừng hoặc resource gặp lỗi, đóng hoặc thiết lập lại các resource theo lifecycle.

~~~mermaid
flowchart TD
    A["Container start"] --> B["Create consumer invoker"]
    B --> C["Obtain Connection / Session / Consumer"]
    C --> D["MessageConsumer.receive(timeout)"]
    D --> E{"Received message?"}
    E -->|Yes| F["Invoke MessageListener"]
    F --> G["Commit / acknowledge or rollback"]
    G --> D
    E -->|No, timeout| H["Mark receive as idle"]
    H --> I{"Scale or reschedule?"}
    I -->|Continue| D
    I -->|Release surplus worker| J["Close worker resources"]
    J --> K["Wait for new scheduling"]
    C -. "Connection failure" .-> R["Recovery / reconnect"]
    R --> C
~~~

Vòng lặp nhận thuộc về container. Listener chỉ xử lý message được chuyển tới; không cần tự gọi receive() hoặc tự tạo vòng while để polling destination.

### 2.1. Vai trò của receive timeout

DMLC dùng receive timeout để giới hạn thời gian một lần gọi receive() chờ message. Với cấu hình mặc định thông dụng, timeout là khoảng 1.000 ms. Có thể thay đổi bằng:

~~~java
container.setReceiveTimeout(1_000);
~~~

Giá trị tính bằng milliseconds. Khi hết thời gian mà chưa có message, receive() trả về null; invoker có cơ hội đánh giá trạng thái idle và điều chỉnh lịch chạy.

Receive timeout không phải thời gian tối đa cho listener xử lý một message. Nếu listener mất 20 giây để xử lý, receive timeout không tự ngắt listener sau 1 giây. Timeout này điều khiển thời gian chờ nhận message.

Timeout quá dài có thể làm việc nhận biết trạng thái idle và giải phóng consumer dư diễn ra chậm. Timeout quá ngắn có thể làm vòng lặp kiểm tra thường xuyên hơn và tăng số lần receive trả về null. Hãy chọn theo workload, yêu cầu phản hồi và chính sách scaling.

## 3. Mỗi invoker quản lý resource JMS riêng

JMS Session là ngữ cảnh single-threaded. DMLC tổ chức các consumer worker để mỗi luồng xử lý có Session và MessageConsumer tương ứng theo cache policy.

Ví dụ khi có ba consumer:

~~~text
Invoker 1 -> Session 1 -> Consumer 1 -> Listener
Invoker 2 -> Session 2 -> Consumer 2 -> Listener
Invoker 3 -> Session 3 -> Consumer 3 -> Listener
~~~

Mỗi invoker có thể nhận và xử lý message độc lập. DMLC quản lý việc tạo, cache, đóng và tái thiết lập resource khi cần. Không nên tự lấy Session của container rồi lưu vào field singleton để chia sẻ cho các thread khác.

Listener bean thường là singleton. Khi container có nhiều consumer, phương thức listener có thể được gọi đồng thời trên cùng instance. Vì vậy:

- Dùng biến local để giữ dữ liệu của từng lần xử lý.
- Dùng object bất biến cho dữ liệu chia sẻ.
- Nếu cần state dùng chung, chọn cấu trúc thread-safe và xác định rõ tính nguyên tử.
- Không lưu Message, Session hoặc trạng thái giao dịch của một lần xử lý vào field rồi dùng ở invocation khác.

## 4. Cấu hình DMLC cơ bản

DMLC có thể được khai báo trực tiếp như một Spring bean. Ví dụ sau minh họa một Queue listener với hai consumer ban đầu và khả năng tăng lên tối đa tám consumer:

~~~java
@Configuration
public class JmsListenerConfiguration {

    @Bean
    public DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListener orderMessageListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderMessageListener);

        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(8);

        container.setReceiveTimeout(1_000);
        container.setSessionTransacted(true);
        container.setRecoveryInterval(5_000);

        return container;
    }
}
~~~

Bean MessageListener có thể được triển khai riêng:

~~~java
@Component
public class OrderMessageListener implements MessageListener {

    private final OrderService orderService;

    public OrderMessageListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void onMessage(Message message) {
        orderService.process(message);
    }
}
~~~

Ví dụ dùng kiểu JMS của phiên bản Spring tương ứng. Spring Framework 6 trở lên sử dụng Jakarta Messaging API với package jakarta.jms; các ứng dụng Spring cũ có thể dùng javax.jms. Cần thống nhất package với phiên bản Spring và JMS provider.

Một số cấu hình quan trọng:

- **setConnectionFactory:** cung cấp ConnectionFactory do provider cấu hình.
- **setDestinationName:** đặt tên Queue hoặc Topic; việc phân giải destination dựa trên DestinationResolver.
- **setMessageListener:** đăng ký listener nhận message.
- **setConcurrentConsumers:** số consumer cơ bản được duy trì.
- **setMaxConcurrentConsumers:** giới hạn trên khi container cần scale up.
- **setReceiveTimeout:** thời gian chờ tối đa cho một lần receive.
- **setSessionTransacted:** bật transaction JMS cục bộ cho Session.
- **setRecoveryInterval:** khoảng nghỉ giữa các lần thử phục hồi theo cấu hình cố định.

Khi cần dùng transaction manager bên ngoài, có thể cấu hình thuộc tính transactionManager thay cho việc chỉ dựa vào local transacted Session. Cách cấu hình phụ thuộc transaction manager và JMS provider.

## 5. Concurrency và dynamic scaling

DMLC có hai thuộc tính chính để điều khiển số consumer:

- **concurrentConsumers:** số consumer cơ bản. Giá trị mặc định là 1.
- **maxConcurrentConsumers:** số consumer tối đa. Giá trị mặc định là 1.

Nếu maxConcurrentConsumers lớn hơn concurrentConsumers, DMLC có thể tạo thêm invoker khi nhận thấy tải message tăng. Khi tải giảm, consumer dư có thể được thu hẹp về mức cơ bản.

Ví dụ:

~~~java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(8);
~~~

Container luôn duy trì mức consumer cơ bản theo cấu hình và có thể tăng đến tám consumer khi điều kiện điều phối phù hợp. Việc scale dựa trên hoạt động nhận message và trạng thái idle, không phải một autoscaler tức thời dựa trên CPU.

### 5.1. Những thuộc tính liên quan đến scaling

DMLC có một số thuộc tính nâng cao:

| Thuộc tính | Vai trò |
|---|---|
| idleConsumerLimit | Giới hạn số consumer đang idle mà container chấp nhận khi quyết định tạo thêm invoker |
| idleTaskExecutionLimit | Số lần một task được đánh dấu idle trước khi task dư bị dừng |
| idleReceivesPerTaskLimit | Số lần receive liên tiếp trả về null để đánh dấu task idle |
| maxMessagesPerTask | Số lần thử nhận message tối đa trong một task trước khi task được reschedule |
| taskExecutor | Executor chạy các listener invoker |

Các thuộc tính này giúp cân bằng khả năng tăng tải với chi phí tạo thread và JMS resource. Nếu scaling lên/xuống quá thường xuyên, có thể điều chỉnh idle limits hoặc receive timeout để consumer dư được giữ lâu hơn. Nếu cần giải phóng tài nguyên nhanh khi queue trống, có thể giảm ngưỡng idle phù hợp.

### 5.2. TaskExecutor và vòng đời thread

Nếu không cấu hình executor riêng, DMLC dùng SimpleAsyncTaskExecutor để tạo các thread cho invoker. Những thread này thường sống trong thời gian dài vì mỗi invoker lặp receive liên tục.

Một thread pool thông thường không nhất thiết đem lại lợi ích nếu mỗi task chiếm thread trong gần như toàn bộ vòng đời container. Executor riêng hữu ích khi cần tích hợp với cơ chế quản lý thread của Jakarta EE hoặc một môi trường thực thi có chính sách riêng.

Với Spring Framework 6.2 và Java 21 trở lên, DMLC còn hỗ trợ tùy chọn virtual threads cho executor mặc định thông qua setVirtualThreads(true). Tùy chọn này chỉ áp dụng khi container dùng executor mặc định; nếu truyền executor riêng, ứng dụng phải cấu hình virtual thread ở executor đó.

## 6. Queue và Topic có hành vi concurrency khác nhau

Với Queue, nhiều consumer thường cạnh tranh nhận message. Một message được giao cho một consumer tại một thời điểm theo semantics của queue. Tăng số consumer có thể tăng throughput nếu listener và hệ thống downstream đủ khả năng xử lý song song.

Tuy nhiên, khi nhiều consumer cùng hoạt động, thứ tự hoàn tất xử lý có thể khác thứ tự message được gửi hoặc nhận. Ví dụ, consumer 1 nhận message A trước consumer 2 nhận B, nhưng B xử lý nhanh hơn và hoàn tất trước A.

Với Topic, mỗi subscription độc lập thường nhận bản sao của message được publish. Nếu tăng số consumer theo cách thông thường trên cùng một Topic, nhiều consumer có thể cùng nhận một publication, dẫn đến xử lý lặp. Chỉ tăng concurrency cho Topic khi provider và cấu hình shared subscription hoặc cơ chế tương đương hỗ trợ đúng semantics mong muốn.

Nếu nghiệp vụ yêu cầu ordering:

- Giữ một consumer cho destination khi cần thứ tự xử lý đơn giản và throughput cho phép.
- Nhóm message theo khóa nghiệp vụ nếu provider hỗ trợ message grouping.
- Dùng sequence number hoặc version để phát hiện event đến trễ hoặc sai thứ tự.
- Thiết kế handler idempotent và có thể xử lý duplicate.
- Kiểm thử thứ tự nhận và thứ tự hoàn tất trên provider thực tế.

## 7. Transaction và acknowledgement trong vòng lặp nhận

DMLC không chỉ nhận message mà còn điều phối thời điểm commit hoặc acknowledge sau khi listener xử lý.

### 7.1. AUTO_ACKNOWLEDGE mặc định

Với AUTO_ACKNOWLEDGE, DMLC thực hiện acknowledgement trước khi gọi listener theo semantics của container. Nếu listener ném exception, message đã được acknowledge và không được redelivery chỉ vì exception đó.

Điều này có nghĩa một listener có thể thất bại sau khi broker/provider đã xem message là được xác nhận. Nếu ứng dụng cần redelivery khi xử lý lỗi, không nên dựa vào AUTO_ACKNOWLEDGE mặc định.

### 7.2. Local transacted Session

Có thể bật transaction JMS cục bộ:

~~~java
container.setSessionTransacted(true);
~~~

Khi đó, việc nhận message và xử lý listener nằm trong transaction của Session. Nếu listener hoàn tất bình thường, container commit transaction. Nếu listener ném exception, container rollback theo transaction policy và provider có thể giao lại message.

Redelivery behavior cụ thể phụ thuộc JMS provider, delivery count, redelivery delay và dead-letter policy. Nếu một message luôn gây lỗi, nó có thể được giao lại nhiều lần; cần giới hạn retry và cấu hình poison-message/DLQ phù hợp.

### 7.3. External transaction manager

DMLC có thể tham gia transaction bên ngoài thông qua thuộc tính transactionManager, thường là JtaTransactionManager trong môi trường Jakarta EE với ConnectionFactory có hỗ trợ XA/JTA.

Khi dùng external transaction manager, DMLC mặc định không cache resource ở mức Connection/Session/Consumer để bảo đảm resource mới được lấy trong phạm vi transaction theo yêu cầu của một số application server. Có thể điều chỉnh cacheLevel nếu provider/server cho phép và đã kiểm thử.

Không giả định local JMS transaction và transaction database tự động là một transaction nguyên tử. Nếu cần commit đồng thời database và JMS, cần cấu hình XA/JTA phù hợp hoặc dùng Transactional Outbox theo kiến trúc ứng dụng.

## 8. Cache level của DMLC

DMLC có cơ chế cache resource riêng. Các mức cache chính:

| Cache level | Resource được giữ |
|---|---|
| CACHE_NONE | Không cache JMS resource |
| CACHE_CONNECTION | Cache Connection |
| CACHE_SESSION | Cache Connection và Session |
| CACHE_CONSUMER | Cache Connection, Session và MessageConsumer |
| CACHE_AUTO | Để container tự chọn theo transaction strategy |

Với local JMS resource, mặc định thường là CACHE_CONSUMER. Khi có external transaction manager, mặc định là CACHE_NONE để lấy resource mới trong phạm vi transaction.

Ví dụ đặt mức cache rõ ràng:

~~~java
container.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_CONSUMER
);
~~~

Chỉ chọn mức cache sau khi hiểu transaction manager và quy tắc của provider. Một số Jakarta EE server yêu cầu Connection và Session mới để đăng ký resource vào XA transaction. Ép cache trong trường hợp đó có thể khiến transaction không được enlist đúng.

### 8.1. Kết hợp với CachingConnectionFactory

DMLC đã quản lý cache theo lifecycle của listener worker. Spring khuyến nghị để listener container tự quản lý mức cache phù hợp trong nhiều trường hợp.

Nếu dùng thêm CachingConnectionFactory, cần chú ý:

- Có thể xuất hiện hai tầng cache cùng giữ Connection, Session hoặc Consumer.
- Dừng rồi khởi động lại container cần Connection được cache độc lập ở phạm vi container; một Connection cache bên ngoài có thể làm lifecycle restart không hoạt động như mong muốn.
- Dynamic scaling với provider-specific hints và cached consumer có thể làm message được giao cho consumer đã không còn gắn với listener container.
- Cần kiểm thử reconnect, shutdown, durable subscription và redelivery với đúng JMS provider.

Không bật cache ở mọi tầng chỉ vì muốn tăng hiệu năng. Hãy đo chi phí tạo resource và chọn một chiến lược cache dễ quản lý.

## 9. Phục hồi khi broker tạm thời không hoạt động

DMLC có khả năng tự phục hồi khi broker ngừng hoạt động tạm thời. Khi thiết lập Connection hoặc Consumer thất bại, container lên lịch thử khôi phục lại thay vì dừng vĩnh viễn.

Khoảng phục hồi mặc định là 5 giây. Có thể cấu hình:

~~~java
container.setRecoveryInterval(5_000);
~~~

Hoặc cung cấp một BackOff để điều chỉnh thời gian chờ giữa các lần thử:

~~~java
container.setBackOff(new ExponentialBackOff(1_000, 2.0));
~~~

Ví dụ BackOff minh họa cần import và cấu hình giới hạn phù hợp với phiên bản Spring đang dùng. Nếu BackOff kết thúc bằng trạng thái STOP, container sẽ ngừng các lần thử tiếp theo theo contract của BackOff.

Recovery của container giúp tái lập kết nối và consumer. Nó không thay thế retry cho lỗi nghiệp vụ bên trong listener. Cần phân biệt:

- **Connection/setup failure:** broker không sẵn sàng, lỗi xác thực hoặc không tạo được consumer. DMLC thực hiện recovery.
- **Listener processing failure:** listener ném exception khi xử lý message. Transaction, error handler, redelivery và DLQ quyết định cách xử lý.
- **Application shutdown:** container được stop/destroy và đóng resource theo lifecycle; đây không phải lỗi broker cần recovery.

## 10. Lifecycle: start, stop và shutdown

DMLC triển khai các interface lifecycle của Spring, gồm SmartLifecycle. Trong ApplicationContext, container có thể tự khởi động theo cấu hình autoStartup và dừng khi context đóng.

Một số thao tác thường gặp:

~~~java
container.start();
container.stop();
container.destroy();
~~~

Trong ứng dụng Spring, thường để ApplicationContext quản lý lifecycle thay vì gọi thủ công trong business service.

Khi stop, container ngừng các listener invoker và đóng Session/Consumer được quản lý. Với stop callback, ứng dụng có thể biết khi nào quá trình xử lý listener thực sự đã dừng. Cần thiết kế graceful shutdown để các transaction đang xử lý có cơ hội hoàn tất hoặc rollback đúng cách trước khi ứng dụng kết thúc.

Không đóng ConnectionFactory dùng chung từ một listener worker. Resource do container hoặc factory sở hữu cần được đóng theo lifecycle tương ứng.

## 11. Error handling và giám sát

Listener có thể ném exception do dữ liệu sai, lỗi nghiệp vụ, database tạm thời không truy cập được hoặc lỗi lập trình. DMLC có thể được cấu hình ErrorHandler để xử lý lỗi listener theo chính sách ứng dụng.

Ví dụ:

~~~java
container.setErrorHandler(error ->
        logger.error("JMS listener failed", error)
);
~~~

ErrorHandler giúp ghi log hoặc phát cảnh báo, nhưng không tự quyết định message có được redelivery hay không. Redelivery phụ thuộc transaction/acknowledgement và provider. Không nuốt exception trong listener nếu cần rollback transacted Session.

Các chỉ số nên theo dõi:

- Số consumer đang active và số consumer đã được schedule.
- Số message đang chờ trong queue hoặc subscription backlog.
- Tốc độ nhận và xử lý message.
- Thời gian xử lý trung bình và percentile cao.
- Số lần lỗi listener, rollback và redelivery.
- Số lần recovery/reconnect.
- Số message bị chuyển DLQ.
- Thread đang chạy và thời gian listener bị block.

DMLC cung cấp các thông tin như activeConsumerCount và scheduledConsumerCount để quan sát trạng thái concurrency. Kết hợp với metric của broker sẽ giúp phân biệt queue backlog do thiếu consumer với listener xử lý chậm hoặc downstream service đang nghẽn.

## 12. Các lỗi thường gặp

### 12.1. Tự viết vòng while và receive song song với DMLC

DMLC đã quản lý vòng lặp nhận. Tự tạo thêm vòng receive trên cùng Session/Consumer có thể gây cạnh tranh và phá vỡ lifecycle.

Cách xử lý: giao việc nhận message cho container; listener chỉ xử lý message được truyền vào.

### 12.2. Nghĩ rằng listener exception luôn làm message được gửi lại

Với AUTO_ACKNOWLEDGE mặc định của DMLC, acknowledgement diễn ra trước listener execution nên exception không tự tạo redelivery.

Cách xử lý: dùng sessionTransacted hoặc external transaction manager khi cần rollback/redelivery; kiểm tra policy của broker.

### 12.3. Tăng concurrency nhưng bỏ qua ordering

Nhiều consumer xử lý song song có thể hoàn tất message theo thứ tự khác nhau.

Cách xử lý: xác định ordering cần bảo toàn, cân nhắc một consumer hoặc grouping/sequence theo nghiệp vụ.

### 12.4. Tăng consumer trên Topic như trên Queue

Nhiều consumer subscription độc lập có thể nhận cùng một publication.

Cách xử lý: kiểm tra shared subscription và semantics của provider; không tăng concurrency nếu cấu hình topic không hỗ trợ mô hình đó.

### 12.5. Dùng external transaction manager nhưng ép cache không phù hợp

Một số application server cần resource mới trong transaction để enlist XA.

Cách xử lý: hiểu default CACHE_NONE, kiểm tra quy tắc provider và chỉ thay đổi cacheLevel sau khi thử nghiệm XA thực tế.

### 12.6. Scale up/down quá thường xuyên

Receive timeout và idle limits có thể khiến consumer dư được tạo rồi dừng liên tục khi tải dao động.

Cách xử lý: điều chỉnh idleTaskExecutionLimit, idleReceivesPerTaskLimit, maxMessagesPerTask và receiveTimeout theo workload.

### 12.7. Listener singleton giữ state mutable không an toàn

Nhiều consumer có thể gọi listener trên cùng bean instance.

Cách xử lý: dùng biến local, immutable object hoặc cấu trúc thread-safe; tránh giữ Session/Message của invocation trong field.

### 12.8. Nhầm recovery với retry nghiệp vụ

DMLC recovery khôi phục Connection/Consumer khi broker gặp sự cố. Nó không thay thế retry policy cho lỗi xử lý payload.

Cách xử lý: cấu hình recovery cho hạ tầng và transaction/retry/DLQ cho message processing riêng biệt.

## 13. Ví dụ Java 17: mô phỏng vòng lặp polling với hai consumer

Ví dụ sau dùng BlockingQueue và ExecutorService của JDK để mô phỏng ý tưởng cốt lõi của DMLC: nhiều worker chạy vòng lặp poll, mỗi worker có một Session riêng và xử lý message nhận được. Đây là chương trình minh họa bằng JDK thuần, không phải implementation Spring JMS và không kết nối broker.

Tạo file **PollingListenerLoopDemo.java**:

~~~java
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PollingListenerLoopDemo {

    record DemoMessage(String id) {}

    record ProcessedMessage(String messageId, String sessionId) {}

    record DemoSession(String id) {}

    public static void main(String[] args) throws Exception {
        BlockingQueue<DemoMessage> queue =
                new ArrayBlockingQueue<>(10);

        queue.add(new DemoMessage("M-1"));
        queue.add(new DemoMessage("M-2"));

        Set<String> sessionIds = ConcurrentHashMap.newKeySet();
        ConcurrentLinkedQueue<ProcessedMessage> processed =
                new ConcurrentLinkedQueue<>();

        CountDownLatch workersStarted = new CountDownLatch(2);
        CountDownLatch firstMessagesReceived = new CountDownLatch(2);
        CountDownLatch continuePolling = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> first = executor.submit(() ->
                    runConsumer(
                            "consumer-1",
                            queue,
                            sessionIds,
                            processed,
                            workersStarted,
                            firstMessagesReceived,
                            continuePolling
                    )
            );

            Future<?> second = executor.submit(() ->
                    runConsumer(
                            "consumer-2",
                            queue,
                            sessionIds,
                            processed,
                            workersStarted,
                            firstMessagesReceived,
                            continuePolling
                    )
            );

            if (!workersStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Consumers did not start");
            }

            if (!firstMessagesReceived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Both consumers did not receive a first message");
            }

            queue.add(new DemoMessage("M-3"));
            queue.add(new DemoMessage("M-4"));
            continuePolling.countDown();

            first.get();
            second.get();

            System.out.println("Consumers started: " + sessionIds.size());
            System.out.println("Messages processed: " + processed.size());
            System.out.println(
                    "Distinct worker sessions: " + sessionIds.size());
        }
        finally {
            continuePolling.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }

    private static void runConsumer(
            String consumerId,
            BlockingQueue<DemoMessage> queue,
            Set<String> sessionIds,
            ConcurrentLinkedQueue<ProcessedMessage> processed,
            CountDownLatch workersStarted,
            CountDownLatch firstMessagesReceived,
            CountDownLatch continuePolling) {

        DemoSession session = new DemoSession("session-" + consumerId);
        sessionIds.add(session.id());
        workersStarted.countDown();

        try {
            DemoMessage first = queue.poll(5, TimeUnit.SECONDS);

            if (first != null) {
                processed.add(new ProcessedMessage(first.id(), session.id()));
                firstMessagesReceived.countDown();
                continuePolling.await();
            }

            DemoMessage next;
            while ((next = queue.poll(200, TimeUnit.MILLISECONDS)) != null) {
                processed.add(new ProcessedMessage(next.id(), session.id()));
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac PollingListenerLoopDemo.java
java PollingListenerLoopDemo
~~~

Kết quả:

~~~text
Consumers started: 2
Messages processed: 4
Distinct worker sessions: 2
~~~

Hai consumer nhận hai message đầu tiên trong lúc mỗi worker sở hữu Session riêng. Sau khi cả hai đã nhận message, chương trình thêm hai message nữa và cho phép vòng polling tiếp tục. Kết quả chỉ in số lượng để tránh phụ thuộc vào việc worker nào nhận M-3 hoặc M-4.

Ví dụ minh họa cách tổ chức worker và vòng lặp polling. DMLC thật còn quản lý Connection, MessageConsumer, transaction, acknowledgement, timeout, scaling, recovery và lifecycle.

## 14. Quy trình triển khai và kiểm thử

Khi triển khai DMLC, nên thực hiện theo thứ tự:

1. Chọn Queue hay Topic và xác định semantics nhận message.
2. Cấu hình ConnectionFactory, destination và listener.
3. Bắt đầu với một consumer, sau đó tăng concurrency khi đã đo được throughput và ordering cần thiết.
4. Cấu hình receiveTimeout để cân bằng polling và nhận biết trạng thái idle.
5. Chọn sessionTransacted hoặc external transaction manager theo yêu cầu xử lý.
6. Chọn cacheLevel tương thích với transaction manager và provider.
7. Cấu hình recovery interval hoặc BackOff cho lỗi kết nối.
8. Định nghĩa ErrorHandler, retry, redelivery và DLQ cho lỗi listener.
9. Kiểm tra listener bean an toàn khi được gọi đồng thời.
10. Kiểm thử start/stop, broker restart, transaction rollback, queue backlog, ordering và graceful shutdown.

Các tình huống kiểm thử cần có:

- Gửi message khi container đang chạy và xác nhận listener nhận đúng payload.
- Tăng concurrency để xác nhận nhiều consumer thực sự xử lý song song.
- Cho listener ném exception trong transacted Session và xác nhận rollback/redelivery.
- Kiểm tra AUTO_ACKNOWLEDGE để hiểu hành vi khi listener lỗi.
- Dừng broker tạm thời rồi khởi động lại, xác nhận DMLC tự phục hồi.
- Tạo tải tăng/giảm để quan sát dynamic scaling và idle consumer cleanup.
- Dừng ApplicationContext khi listener đang xử lý để kiểm tra resource và transaction được kết thúc đúng.
- Với Topic, xác nhận subscription và concurrency không làm phát sinh nhiều lần xử lý ngoài ý muốn.

DefaultMessageListenerContainer quản lý vòng lặp receive, worker, Session, Consumer và transaction để ứng dụng tập trung vào logic listener. Hiểu cách polling, receive timeout, concurrency, cache level và acknowledgement phối hợp giúp cấu hình đúng theo Queue/Topic và JMS provider. Khi kết hợp transaction phù hợp, recovery có backoff, giám sát backlog và listener thread-safe, DMLC có thể nhận message ổn định ngay cả khi tải thay đổi hoặc broker tạm thời gián đoạn.

## Tài liệu tham khảo

- [Spring Framework 6.2: DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework: JMS integration reference](https://docs.spring.io/spring-framework/reference/integration/jms.html)