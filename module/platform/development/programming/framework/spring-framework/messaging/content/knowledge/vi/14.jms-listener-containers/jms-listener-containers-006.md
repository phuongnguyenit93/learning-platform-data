# TaskExecutor, receiveTimeout và thời gian consumer rảnh trong Spring JMS

## 1. Ba yếu tố phối hợp trong listener container

DefaultMessageListenerContainer (DMLC) nhận message bằng vòng lặp gọi MessageConsumer.receive(timeout). Mỗi consumer có một JMS Session, một MessageConsumer và một tác vụ listener chạy bất đồng bộ. Ba cấu hình quyết định cách container dùng thread và giữ consumer khi destination không có message:

- **TaskExecutor** quyết định tác vụ listener chạy trên thread nào và được lập lịch ra sao.
- **receiveTimeout** quyết định mỗi lần gọi receive chờ message tối đa bao lâu.
- **Các giới hạn idle** quyết định khi nào một consumer dư thừa được giữ lại hoặc dừng sau nhiều lần không nhận được message.

Các thuộc tính này liên quan chặt chẽ đến concurrency. Chúng ảnh hưởng đến tốc độ tăng consumer khi queue có tải, thời gian giải phóng consumer khi queue vắng và số thread/tài nguyên JMS được giữ trong suốt vòng đời container.

Cần phân biệt thời gian consumer rảnh với thời gian xử lý message. receiveTimeout chỉ áp dụng khi consumer đang chờ message. Nếu listener đã nhận message và đang xử lý một công việc mất 30 giây, receiveTimeout 1 giây không hủy hoặc giới hạn công việc đó.

## 2. TaskExecutor chạy các consumer như thế nào?

DMLC sử dụng Spring TaskExecutor để thực thi các invoker. Khi container khởi động, nó tạo số tác vụ ban đầu theo concurrentConsumers. Mỗi tác vụ quản lý vòng nhận message và gọi listener khi có message.

### 2.1. Executor mặc định

Nếu không truyền executor, DMLC tạo SimpleAsyncTaskExecutor:

~~~java
DefaultMessageListenerContainer container =
    new DefaultMessageListenerContainer();

container.setConcurrentConsumers(3);
~~~

Với cấu hình trên, container khởi tạo ba consumer và các tác vụ listener tương ứng. SimpleAsyncTaskExecutor tạo thread theo nhu cầu; mặc định dùng platform thread và không phải pool tái sử dụng truyền thống.

Một thread listener thường bị chiếm trong suốt thời gian tác vụ nhận message. Đây là cách đơn giản và phù hợp với nhiều ứng dụng JMS độc lập. Số thread listener có thể tăng theo maxConcurrentConsumers nếu bật dynamic scaling.

### 2.2. Truyền executor riêng

Có thể cung cấp executor do ứng dụng quản lý:

~~~java
container.setTaskExecutor(jmsListenerExecutor);
~~~

Việc này hữu ích khi cần tích hợp với môi trường quản lý thread đặc biệt hoặc muốn kiểm soát pool, tên thread và giới hạn tài nguyên. Tuy nhiên, một thread pool thông thường không tự động làm cho consumer nhẹ hơn: nếu tác vụ listener chạy lâu dài, mỗi consumer vẫn giữ một thread trong thời gian đó.

DMLC nhận biết SchedulingTaskExecutor có khai báo ưu tiên tác vụ ngắn. Với loại executor này, container mặc định dùng maxMessagesPerTask bằng 10 để kết thúc và lập lịch lại tác vụ sau một số lần nhận. Điều đó cho thread pool cơ hội phân phối thread cho các công việc khác.

Nếu dùng executor có pool nhỏ hơn số consumer tối đa, các tác vụ có thể phải xếp hàng hoặc bị từ chối khi pool không còn khả năng tiếp nhận. Hãy phối hợp kích thước pool, queue capacity và maxConcurrentConsumers; theo dõi cả số consumer được lập lịch lẫn số consumer đang hoạt động.

### 2.3. Virtual thread trên Java 21+

Từ Spring Framework 6.2, DMLC có setVirtualThreads(true) để yêu cầu SimpleAsyncTaskExecutor mặc định dùng virtual thread thay cho platform thread:

~~~java
container.setVirtualThreads(true);
~~~

Tùy chọn này chỉ áp dụng khi DMLC tự tạo executor mặc định. Nếu đã truyền TaskExecutor bên ngoài, hãy cấu hình virtual thread ngay trên executor đó. Virtual thread phù hợp với tác vụ chờ I/O, nhưng không thay thế việc giới hạn concurrency, quản lý tài nguyên JMS hoặc xử lý listener chậm.

## 3. receiveTimeout điều khiển một lần polling

DMLC kế thừa receiveTimeout từ AbstractPollingMessageListenerContainer. Giá trị mặc định là 1000 mili giây, tức một giây.

~~~java
container.setReceiveTimeout(1_000L);
~~~

Mỗi lần polling gọi MessageConsumer.receive(timeout). Kết quả có thể là:

| Giá trị timeout | Hành vi |
| --- | --- |
| Số dương, ví dụ 1000 | Chờ tối đa 1000 ms; nếu chưa có message, receive trả về null |
| 0 | Chờ vô thời hạn; thường không phù hợp vì có thể khiến container khó shutdown sạch |
| Số âm, ví dụ -1 | Không chờ; tương ứng receiveNoWait() |

Timeout được tính bằng mili giây. Với timeout hữu hạn, container có cơ hội quay lại vòng lặp để kiểm tra trạng thái, điều phối tác vụ và thực hiện logic quản lý consumer.

Nếu container tham gia transaction, receiveTimeout cần nhỏ hơn transaction timeout của transaction manager. Nếu receive chờ lâu hơn transaction timeout, transaction có thể hết hạn trong khi consumer vẫn đang đợi message.

### 3.1. receiveTimeout không phải message processing timeout

Giả sử listener nhận một message lúc 10:00:00 và xử lý đến 10:00:20. Trong 20 giây đó, listener đang làm việc với message; receiveTimeout không giới hạn thời gian này. Sau khi xử lý xong, consumer mới quay lại gọi receive để đợi message tiếp theo.

Nếu cần giới hạn thời gian xử lý nghiệp vụ, hãy đặt timeout ở HTTP client, database call, service call hoặc cơ chế xử lý tương ứng. Không dùng receiveTimeout để kiểm soát một listener đang chạy lâu.

### 3.2. Chọn timeout theo mục tiêu

- Timeout ngắn giúp consumer nhận biết queue rỗng nhanh và phản ứng với trạng thái dừng sớm hơn, nhưng làm tăng số lần polling.
- Timeout dài giảm tần suất polling khi queue thường rỗng, nhưng có thể làm thời gian nhận biết idle và thời gian shutdown kéo dài hơn.
- Timeout bằng 0 giữ consumer trong một lần receive vô hạn và thường không được khuyến nghị cho DMLC.
- Timeout âm có thể tạo vòng polling không chờ; chỉ dùng khi đã thiết kế rõ nhịp chạy và giới hạn tải.

Không có một giá trị phù hợp cho mọi hệ thống. Hãy chọn timeout dựa trên độ trễ mong muốn, transaction timeout, nhịp message và chi phí polling của JMS provider.

## 4. Consumer rảnh là gì?

Một lần receive được xem là idle receive khi đã hết receiveTimeout mà không có message, nghĩa là consumer nhận được kết quả null.

DMLC dùng kết quả này để đánh giá consumer dư thừa có nên tiếp tục tồn tại hay không. Một consumer vừa được tạo để xử lý tải tăng có thể tiếp tục nhận message trong một thời gian. Nếu queue lại vắng, container có thể giải phóng consumer đó và quay về số consumer cơ bản.

Cần phân biệt:

- **Core consumer:** nằm trong concurrentConsumers; container giữ chúng cho đến khi shutdown.
- **Surplus consumer:** consumer được tạo thêm khi dynamic scaling; có thể bị dừng khi tải giảm.
- **Idle receive:** một lần receive hết timeout mà không nhận message.
- **Idle task execution:** một lượt chạy tác vụ không nhận được message theo các giới hạn của task.

Các giới hạn idle phối hợp với receiveTimeout và maxMessagesPerTask để điều chỉnh tốc độ scale up/scale down.

## 5. Bật dynamic scaling bằng concurrency

DMLC chỉ tự tăng/giảm số consumer khi maxConcurrentConsumers lớn hơn concurrentConsumers.

~~~java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(8);
~~~

Trong ví dụ này:

- Hai consumer là mức tối thiểu được duy trì.
- Khi tải queue tăng, DMLC có thể tạo thêm consumer cho đến tối đa tám.
- Khi tải giảm, các consumer dư thừa có thể được dừng để quay về hai consumer cơ bản.

Mặc định concurrentConsumers và maxConcurrentConsumers đều là 1, vì vậy dynamic scaling chưa được bật nếu không thay đổi maxConcurrentConsumers.

### 5.1. Tăng consumer khi message đến

Khi một invoker nhận được message, DMLC có thể lên lịch thêm invoker nếu chưa đạt maxConcurrentConsumers và giới hạn idleConsumerLimit cho phép. idleConsumerLimit mặc định là 1: container chỉ lên lịch thêm một invoker nếu hiện không có invoker nào đang idle.

Tăng idleConsumerLimit có thể làm container mở rộng mạnh hơn, vì nó cho phép tạo thêm invoker ngay cả khi vẫn còn một số consumer rảnh. Điều này có thể tăng tốc ramp-up nhưng cũng có thể tạo nhiều consumer hơn cần thiết.

### 5.2. Giảm consumer khi queue vắng

Khi các lần receive liên tiếp trả về null, DMLC đánh dấu tác vụ là idle. Nếu tác vụ đạt idleTaskExecutionLimit, consumer dư thừa sẽ kết thúc và nhường tài nguyên cho các consumer còn lại.

idleTaskExecutionLimit mặc định là 1. Tăng giá trị này giúp giữ consumer lâu hơn, tránh việc scale lên rồi scale xuống liên tục khi tải dao động.

## 6. Các giới hạn idle và mặc định trong Spring Framework 7.0.9

DMLC có nhiều thuộc tính điều khiển vòng đời tác vụ. Không nên nhầm chúng với nhau:

| Thuộc tính | Mặc định | Tác dụng |
| --- | --- | --- |
| concurrentConsumers | 1 | Số consumer cơ bản luôn được giữ |
| maxConcurrentConsumers | 1 | Số consumer tối đa; bằng 1 thì chưa có dynamic scaling |
| receiveTimeout | 1000 ms | Thời gian chờ tối đa của một lần receive |
| idleConsumerLimit | 1 | Số consumer idle cho phép khi quyết định tạo thêm invoker |
| idleTaskExecutionLimit | 1 | Số lần thực thi tác vụ idle trước khi tác vụ kết thúc |
| idleReceivesPerTaskLimit | 10 với executor mặc định/simple | Số lần receive liên tiếp trả về null trước khi đánh dấu surplus consumer là idle |
| maxMessagesPerTask | -1 với TaskExecutor thông thường; 10 với SchedulingTaskExecutor ưu tiên tác vụ ngắn | Số lần thử nhận tối đa trong một task; lần hết timeout cũng được tính |

### 6.1. idleReceivesPerTaskLimit và thời gian consumer rảnh

Với executor mặc định SimpleAsyncTaskExecutor, DMLC đặt idleReceivesPerTaskLimit hiệu lực là 10 cho consumer dư thừa. Nếu receiveTimeout mặc định là 1000 ms, một surplus consumer có thể được scale down sau khoảng mười lần receive liên tiếp không có message, tức khoảng 10 giây idle.

Ví dụ:

| receiveTimeout | idleReceivesPerTaskLimit | Thời gian idle ước tính |
| --- | --- | --- |
| 500 ms | 10 | Khoảng 5 giây |
| 1000 ms | 10 | Khoảng 10 giây |
| 2000 ms | 10 | Khoảng 20 giây |

Đây là ước lượng dựa trên các lần receive hết timeout liên tiếp; thời gian thực tế còn phụ thuộc lịch chạy task và độ trễ provider.

Giới hạn này chủ yếu áp dụng cho surplus consumer, không làm giảm số core consumer trong concurrentConsumers. Từ Spring 6.2, khi dùng executor ưu tiên tác vụ ngắn, idleReceivesPerTaskLimit chỉ ảnh hưởng core consumer khi kết hợp với maxMessagesPerTask để DMLC lập lịch lại các tác vụ đó.

### 6.2. idleTaskExecutionLimit

idleTaskExecutionLimit quyết định cần bao nhiêu lượt thực thi idle trước khi task kết thúc. Mặc định là 1, vì vậy một tác vụ đã được đánh dấu idle có thể kết thúc ngay trong cơ chế dynamic scaling.

Tăng giá trị này khi consumer bị tạo và dừng quá thường xuyên. Consumer sẽ tồn tại lâu hơn sau khi queue vắng, đổi lại sẽ giữ thread và tài nguyên JMS lâu hơn.

### 6.3. maxMessagesPerTask

Tên thuộc tính nói đến số message, nhưng thực tế nó giới hạn số lần thử nhận trong một task. Những lần receive hết timeout và trả về null cũng được tính.

Với TaskExecutor thông thường, mặc định là -1, nghĩa là task có thể chạy liên tục cho đến khi container dừng. Với SchedulingTaskExecutor khai báo ưu tiên task ngắn, mặc định là 10 để task kết thúc và được lập lịch lại sau tối đa mười lần thử nhận.

Có thể đặt rõ giá trị:

~~~java
container.setMaxMessagesPerTask(10);
~~~

Giá trị khoảng 10 đến 100 thường là điểm bắt đầu để cân bằng giữa chi phí lập lịch lại và khả năng thread pool phân phối công việc. Giá trị nhỏ giúp task trả thread thường xuyên hơn; giá trị lớn giảm context switch nhưng giữ thread lâu hơn.

## 7. Ví dụ cấu hình DMLC với TaskExecutor và thời gian idle

Ví dụ sau cấu hình một queue listener với hai consumer cơ bản và tối đa tám consumer. ThreadPoolTaskExecutor là executor dành riêng cho listener; mỗi task xử lý tối đa mười lần thử nhận rồi được lập lịch lại.

~~~java
@Configuration
public class OrdersListenerConfiguration {

    @Bean
    public ThreadPoolTaskExecutor jmsListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("jms-orders-");
        return executor;
    }

    @Bean
    public DefaultMessageListenerContainer ordersContainer(
            ConnectionFactory connectionFactory,
            ThreadPoolTaskExecutor jmsListenerExecutor,
            MessageListener orderMessageListener) {

        DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderMessageListener);

        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(8);

        container.setTaskExecutor(jmsListenerExecutor);
        container.setMaxMessagesPerTask(10);
        container.setReceiveTimeout(1_000L);
        container.setIdleTaskExecutionLimit(1);

        container.setSessionTransacted(true);
        return container;
    }
}
~~~

Các thành phần ConnectionFactory và MessageListener được cung cấp bởi ứng dụng. ConnectionFactory phải kết nối được tới JMS provider và queue orders.queue phải tồn tại hoặc được provider cho phép tạo động.

ThreadPoolTaskExecutor có tám worker, tương ứng với maxConcurrentConsumers bằng tám. Queue capacity 32 cho phép các task được lập lịch lại chờ worker sẵn sàng. maxMessagesPerTask bằng 10 giúp các task kết thúc định kỳ để pool phân phối thread.

Vì ví dụ dùng executor kiểu SchedulingTaskExecutor, DMLC mặc định có thể dùng maxMessagesPerTask bằng 10; code đặt tường minh để chính sách dễ đọc và không phụ thuộc vào mặc định ngầm. Với kiểu executor này, mỗi task có thể thực hiện tối đa mười lần thử nhận, kể cả lần chờ hết receiveTimeout.

Đây là cấu hình tích hợp Spring JMS, không phải chương trình độc lập. Để chạy cần một JMS provider, ConnectionFactory, queue và bean MessageListener đã cấu hình. Không có stdout cố định vì kết quả phụ thuộc message thực tế trong broker.

## 8. Khi nào giữ consumer lâu hơn hoặc scale down nhanh hơn?

| Tình huống | Điều chỉnh gợi ý | Tác động |
| --- | --- | --- |
| Queue có tải đều | Giữ concurrentConsumers phù hợp và maxConcurrentConsumers gần tải dự kiến | Tránh tạo/dừng consumer thường xuyên |
| Tải tăng theo burst | Cho maxConcurrentConsumers cao hơn và xem xét idleConsumerLimit | Tăng tốc tạo consumer khi message đến |
| Tải giảm nhanh sau burst | Giảm receiveTimeout hoặc idleReceivesPerTaskLimit | Consumer dư thừa được đánh dấu idle sớm hơn |
| Tải dao động liên tục | Tăng idleTaskExecutionLimit hoặc idleReceivesPerTaskLimit | Giữ consumer lâu hơn, giảm churn |
| Thread pool cần chia sẻ worker | Dùng SchedulingTaskExecutor và đặt maxMessagesPerTask hợp lý | Task kết thúc định kỳ để pool phân phối lại |
| Queue ít message | Giữ concurrency thấp | Giảm thread và session nhàn rỗi |
| Listener xử lý lâu | Điều chỉnh concurrency theo thời gian xử lý và khả năng broker | Tránh để message backlog tăng quá nhanh |

Không tăng concurrency chỉ để giảm queue depth. Nếu listener xử lý chậm do database hoặc dịch vụ bên ngoài, thêm consumer có thể làm hệ thống phụ thuộc bị quá tải.

## 9. Queue, topic và thứ tự xử lý

Dynamic scaling chủ yếu phù hợp với queue. Nhiều consumer cùng đọc queue sẽ chia tải; một message được giao cho một consumer phù hợp.

Với topic, nhiều consumer trên cùng một node trong cấu hình thông thường có thể nhận cùng một bản sao message. Vì vậy, thường giữ một consumer cho topic, trừ khi broker hỗ trợ shared subscription và ứng dụng đã cấu hình đúng theo provider.

Khi tăng số consumer trên queue, thứ tự xử lý toàn cục không còn được đảm bảo. Hai message được giao cho hai consumer có thể hoàn tất theo thứ tự khác nhau. Nếu nghiệp vụ yêu cầu thứ tự theo đơn hàng, tài khoản hoặc partition, hãy thiết kế khóa phân vùng hoặc cơ chế tuần tự hóa riêng.

## 10. receiveTimeout, transaction và shutdown

receiveTimeout phải nhỏ hơn transaction timeout nếu container đang tham gia transaction. Nếu transaction timeout là 30 giây, không nên để một lần receive chờ lâu hơn mức đó.

Timeout bằng 0 có nghĩa chờ vô hạn. Cách này có thể khiến container khó shutdown sạch vì thread đang bị chặn trong receive. Giá trị âm thực hiện receive không chờ và có thể làm vòng polling chạy quá thường xuyên nếu không có cơ chế điều tiết.

Với listener cần độ tin cậy, cấu hình sessionTransacted hoặc transaction manager phù hợp. Khi listener ném exception trong JMS transaction cục bộ, transaction có thể rollback và broker có thể redeliver message theo chính sách của provider. Consumer vẫn nên idempotent vì duplicate có thể xảy ra trong một số tình huống biên.

## 11. Theo dõi consumer và điều tra vấn đề

DMLC cung cấp các phương thức quan sát hữu ích:

- getConcurrentConsumers(): số consumer cơ bản được cấu hình.
- getMaxConcurrentConsumers(): giới hạn consumer tối đa.
- getScheduledConsumerCount(): số consumer task đã được lập lịch.
- getActiveConsumerCount(): số consumer đang hoạt động.
- isRecovering(): container có đang trong quá trình phục hồi kết nối hay không.

Số scheduled consumer có thể cao hơn active consumer vì một task đã được lên lịch nhưng hiện chưa chạy. Hãy đọc các chỉ số cùng queue depth, tốc độ message đến, thời gian listener xử lý và số lần broker reconnect.

Nếu active consumer thường xuyên chạm maxConcurrentConsumers trong khi backlog vẫn tăng, kiểm tra thời gian xử lý listener, throughput của database và giới hạn broker. Nếu consumer liên tục tăng rồi giảm, xem receiveTimeout, idleReceivesPerTaskLimit, idleTaskExecutionLimit và nhịp message.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ có một consumer dù muốn scale | maxConcurrentConsumers vẫn bằng concurrentConsumers | Đặt maxConcurrentConsumers cao hơn mức tối thiểu |
| Consumer dư thừa biến mất quá nhanh | idleReceivesPerTaskLimit hoặc idleTaskExecutionLimit thấp | Tăng giới hạn idle nếu tải thường xuyên quay lại |
| Consumer giữ thread lâu khi queue rỗng | receiveTimeout dài hoặc maxMessagesPerTask lớn | Giảm timeout hoặc số lần thử trong một task |
| Thread pool không chạy hết consumer | Pool nhỏ hơn concurrency hoặc task chiếm thread lâu dài | Tăng pool phù hợp hoặc dùng SchedulingTaskExecutor với task ngắn |
| Task bị từ chối khi scale | Pool hết worker và queue đầy | Kiểm tra queue capacity, max pool size và concurrency |
| Consumer topic nhận message lặp | Nhiều consumer cùng subscription không dùng shared subscription phù hợp | Giữ một consumer hoặc cấu hình shared subscription theo provider |
| Message hoàn tất sai thứ tự | Nhiều consumer xử lý đồng thời | Giữ concurrency 1 hoặc thiết kế partition/sequence |
| Shutdown bị chậm | receiveTimeout bằng 0 hoặc listener xử lý quá lâu | Dùng timeout hữu hạn và kiểm soát thời gian xử lý |
| CPU tăng khi queue rỗng | receiveTimeout âm tạo polling không chờ quá thường xuyên | Dùng timeout hữu hạn và đo chi phí polling |

## 13. Checklist cấu hình

- [ ] Xác định queue hay topic trước khi tăng concurrency.
- [ ] Chọn concurrentConsumers là mức consumer tối thiểu cần duy trì.
- [ ] Chỉ bật dynamic scaling khi maxConcurrentConsumers lớn hơn concurrentConsumers.
- [ ] Chọn TaskExecutor theo mô hình task dài hạn hay task ngắn hạn.
- [ ] Nếu dùng pool, bảo đảm pool và queue đủ sức tiếp nhận số consumer tối đa.
- [ ] Đặt receiveTimeout nhỏ hơn transaction timeout và phù hợp với độ trễ mong muốn.
- [ ] Hiểu rõ timeout 0 là chờ vô hạn và giá trị âm là no-wait.
- [ ] Phân biệt idleReceivesPerTaskLimit, idleTaskExecutionLimit và maxMessagesPerTask.
- [ ] Theo dõi số consumer active/scheduled và queue backlog.
- [ ] Kiểm thử tải tăng, tải giảm, broker restart, listener chậm và shutdown.
- [ ] Cấu hình transaction/acknowledgement và thiết kế consumer idempotent khi cần độ tin cậy.

## 14. Tài liệu tham khảo

- [Spring Framework API — DefaultMessageListenerContainer 7.0.9](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework API — AbstractPollingMessageListenerContainer 7.0.9](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Framework API — TaskExecutor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework API — SchedulingTaskExecutor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/scheduling/SchedulingTaskExecutor.html)
- [Spring Framework API — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
