# maxMessagesPerTask và vòng đời tác vụ nhận trong DefaultMessageListenerContainer

**Chủ đề:** Spring Framework - jms → Default container.

## 1. maxMessagesPerTask giải quyết vấn đề gì?

Khi ứng dụng sử dụng `@JmsListener` với `DefaultMessageListenerContainer` của Spring JMS, việc nhận message không phải do Spring tạo một lời gọi `receive()` duy nhất rồi kết thúc. Container chạy các **tác vụ nhận (consumer/invoker tasks)**: mỗi tác vụ lặp lại thao tác chờ/nhận JMS message, gọi listener khi có message, rồi tiếp tục.

Cấu hình:

~~~java
container.setMaxMessagesPerTask(10);
~~~

đặt một giới hạn cho **số lần thử nhận message trong một lần thực thi tác vụ**. Theo Javadoc Spring Framework 6.2, bộ đếm này gồm cả:

- Lần `MessageConsumer.receive(...)` trả về một JMS message và listener xử lý nó.
- Lần `receive(...)` hết `receiveTimeout`, trả `null` vì chưa có message.

Đó là điểm dễ nhầm nhất của tên thuộc tính **maxMessagesPerTask**: xét sát triển khai, nó là giới hạn *receive attempts per task*, **không** bảo đảm xử lý chính xác N message nghiệp vụ trong một batch.

Ví dụ giả định `maxMessagesPerTask = 4`:

| Lần thử nhận | Kết quả nhận | Số message thực xử lý | Số receive attempts đã dùng |
| --- | --- | ---: | ---: |
| 1 | Message A | 1 | 1 |
| 2 | Hết timeout, `null` | 1 | 2 |
| 3 | Message B | 2 | 3 |
| 4 | Hết timeout, `null` | 2 | 4 |
| Kết thúc lượt task | Có thể nhường chỗ/reschedule tùy container | **2**, không phải 4 | **4** |

**Giới hạn chỉ áp dụng cho một task execution.** Nó không giới hạn tổng số message consumer xử lý trong suốt vòng đời ứng dụng, không xóa message còn trong queue và không ra lệnh dừng toàn bộ listener container.

Một container vẫn có thể xử lý hàng triệu message thông qua **nhiều lần thực thi task**; các core consumers được duy trì theo cấu hình và những tác vụ cần thiết có thể tiếp tục được lên lịch.

Bài sử dụng **Spring Framework 6.2.x, Spring JMS và Jakarta Messaging 3.1** với Java **17+**. Dự án Spring Boot 3.x có cùng cách cấu hình qua `DefaultJmsListenerContainerFactory`. Lưu ý các version cũ có thể khác chi tiết mặc định; phần mô tả giới hạn và idle behavior dựa trên Javadoc Spring Framework 6.2.

## 2. Phân biệt message, receive attempt, task, consumer, thread và container

Sáu khái niệm sau **không đồng nghĩa**:

| Khái niệm | Mô tả | Thời gian tồn tại |
| --- | --- | --- |
| **JMS message** | Đơn vị dữ liệu được broker giao | Từ lúc gửi tới khi được xử lý/ack/expire theo chính sách |
| **Receive attempt** | Một vòng gọi nhận message có thể thành công hoặc timeout | Tính theo từng lần gọi `receive(...)` |
| **Consumer task/invoker** | Công việc do Spring `TaskExecutor` thực thi; chứa vòng lặp nhiều lần receive | Hữu hạn theo `maxMessagesPerTask` hoặc có thể lâu dài |
| **JMS MessageConsumer** | Đối tượng client nhận message từ destination | Có thể được giữ/cached hoặc tạo lại tùy cache level/transaction/recovery |
| **Thread** | Luồng của executor chạy tác vụ | Có thể riêng cho task hoặc tái sử dụng qua thread pool |
| **Listener container** | `DefaultMessageListenerContainer` quản lý consumers, lifecycle, connection và dispatch | Thường tồn tại theo vòng đời ứng dụng/context |

Một **task** không phải một **message**. Một **task** cũng không nhất thiết bằng một **thread** mãi mãi: thread pool có thể chạy nhiều task liên tiếp trên cùng một thread; executor không pooling có thể tạo thread mới cho task kế tiếp.

Sơ đồ khái niệm:

~~~text
                    Spring ApplicationContext
                            |
               DefaultMessageListenerContainer
                            |
             core consumers / surplus consumers
                            |
                        TaskExecutor
                            |
                   Async invoker task
                            |
                +-----------+-----------+
                |                       |
           receive() #1              ...
                |
          Message hoặc null
                |
          Message -> listener
          null    -> idle signal
                |
           receive() #2
                |
               ...
                |
      đạt maxMessagesPerTask hoặc
      idle/recovery/shutdown condition
                |
             task kết thúc
                |
    container xem xét reschedule/scale-down
    (core consumers vẫn được duy trì)
~~~

Cấu hình `maxMessagesPerTask=3` có thể khiến một core consumer được **reschedule sang task khác** sau ba lần thử nhận. Nó **không** đồng nghĩa đóng application context, hủy destination hay ngừng khả năng tiếp tục nhận message.

## 3. Tại sao DefaultMessageListenerContainer có receive loop?

`org.springframework.jms.listener.DefaultMessageListenerContainer` là listener container sử dụng **JMS client API theo kiểu polling**, cụ thể là lặp lời gọi `jakarta.jms.MessageConsumer.receive(...)`. Đây khác với `SimpleMessageListenerContainer`, vốn dựa trên việc đăng ký callback `MessageConsumer.setMessageListener(...)` của provider.

Luồng xử lý thông dụng:

1. Container khởi tạo các JMS connections/sessions/consumers theo `ConnectionFactory` và cấu hình.
2. Container gửi một hoặc nhiều **invoker tasks** tới `TaskExecutor`.
3. Mỗi task chạy vòng lặp nhận message.
4. Khi nhận được message, Spring dispatch vào `@JmsListener`/message listener adapter, xử lý ack/transaction theo cấu hình.
5. Khi nhận `null` sau timeout, container ghi nhận một lần nhận trống (idle receive).
6. Sau giới hạn receive attempts hoặc điều kiện idle/lifecycle, task kết thúc hoặc được reschedule.
7. Container duy trì core consumers, đồng thời có thể co giãn surplus consumers.

`DefaultMessageListenerContainer` phù hợp cho môi trường JMS native và môi trường cần transaction/recovery/caching. Cần phân biệt nó với **JmsTemplate.receive(...)**: JmsTemplate là lời gọi nhận đồng bộ do ứng dụng chủ động; Default container là hạ tầng **listener chạy nền** cho annotated endpoints.

### 3.1. Vì sao có thể giới hạn vòng đời task?

Trong executor **non-pooling**, việc giữ các consumer tasks trên cùng thread dài hạn thường hiệu quả do ít rescheduling. Trong executor **thread pool**, một task chiếm thread mãi mãi sẽ làm khó việc chia sẻ pool cho những công việc khác. Task hữu hạn cho phép executor điều phối lại các công việc định kỳ.

| Task dài | Task ngắn |
| --- | --- |
| Ít overhead lập lịch/chuyển task | Linh hoạt hơn khi chia sẻ thread pool |
| Có thể giữ thread lâu | Có thể giải phóng thread giữa các lượt |
| Phù hợp executor đơn giản, dedicated consumer threads | Thường hữu ích với pooled/SchedulingTaskExecutor |
| Nếu cấu hình sai có thể chiếm thread pool | Nếu quá ngắn có thể tăng overhead và churn |

**Không có lựa chọn tuyệt đối tốt nhất.** Tùy thread model, receive timeout, throughput, idle pattern, Session/consumer cache, provider và giới hạn tài nguyên.

## 4. Giá trị mặc định: -1 hay 10?

Javadoc Spring 6.2 giải thích: `maxMessagesPerTask` **không có một con số mặc định duy nhất cho mọi TaskExecutor**.

| Task executor container dùng | maxMessagesPerTask mặc định | Lý do |
| --- | ---: | --- |
| `SimpleAsyncTaskExecutor` mặc định hoặc executor thường, không ưu tiên task ngắn | **-1** (không giới hạn receive attempts mỗi task) | Giữ invoker/thread lâu dài tới shutdown hoặc lifecycle khác |
| `SchedulingTaskExecutor` báo `prefersShortLivedTasks() == true` | **10** | Cho executor cơ hội scheduling task ngắn hơn |
| Ứng dụng gọi `setMaxMessagesPerTask(20)` tường minh | **20** | Override giá trị tự chọn |
| Ứng dụng gọi `setMaxMessagesPerTask(3)` tường minh | **3** | Ví dụ minh họa task turnover thường xuyên |

Với pool thích task ngắn, tài liệu Spring gợi ý cân nhắc khoảng **10–100 lần thử nhận mỗi task** để cân bằng giữa overhead và fairness. Đây là hướng dẫn tuning, **không phải giới hạn API cứng**; giá trị `3` trong demo chỉ giúp quan sát dễ hơn.

### 4.1. Vì sao -1 không đồng nghĩa listener chỉ có một task vĩnh viễn?

`-1` có nghĩa **không áp trần số lần receive cho một task theo thuộc tính này**. Task vẫn có thể kết thúc vì stop/shutdown, lỗi kết nối/recovery, điều kiện idle với surplus consumers hoặc các sự kiện lifecycle khác.

Đừng ghi “-1 làm container không bao giờ restart” hoặc “-1 không thể scale-down”. `maxMessagesPerTask` chỉ là **một** điều kiện của vòng đời task.

### 4.2. Thread pool báo short-lived preference thế nào?

Spring interface `org.springframework.scheduling.SchedulingTaskExecutor` có method `prefersShortLivedTasks()`. Nếu executor hiện hành triển khai interface và trả `true`, DefaultMessageListenerContainer sẽ tính đến preference ấy khi chọn giới hạn mặc định phù hợp.

Không phải cứ class có tên “pool” là Spring tự chọn 10 trong mọi phiên bản/cấu hình. Nên quan sát giá trị thực thông qua `getMaxMessagesPerTask()` trên container đã tạo; khi muốn chắc chắn, **đặt giá trị tường minh**.

## 5. API cấu hình và các lớp liên quan

Trên container thực:

~~~java
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setMaxMessagesPerTask(30);
int configured = container.getMaxMessagesPerTask();
~~~

Đây là trích đoạn **chưa tạo được listener hoạt động**, vì còn thiếu `ConnectionFactory`, destination và message listener. Nó chỉ minh họa API setter/getter.

Với `@JmsListener`, cách thông dụng là cấu hình **factory** để mọi endpoint do factory ấy tạo nhận cùng tham số:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class ListenerConfig {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1-3");
        factory.setMaxMessagesPerTask(30);
        factory.setReceiveTimeout(1_000L);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Đây là cấu hình Spring Framework 6.x hợp lệ khi tồn tại `ConnectionFactory` bean, nhưng chưa có broker/consumer runnable riêng. Method tên `jmsListenerContainerFactory` tạo **default factory bean** được `@JmsListener` sử dụng khi annotation không chỉ định `containerFactory`.

Đặc biệt:

- `DefaultMessageListenerContainer.setMaxMessagesPerTask(int)` áp vào **container instance**.
- `DefaultJmsListenerContainerFactory.setMaxMessagesPerTask(Integer)` áp vào **những container do factory tạo**.
- `@JmsListener` **không** có thuộc tính `maxMessagesPerTask` trực tiếp để viết `@JmsListener(maxMessagesPerTask=...)`.
- Có thể tạo **nhiều listener factories** cho những nhóm endpoints cần thread/idle/timeout riêng.

### 5.1. Chọn factory riêng tại @JmsListener

~~~java
@Bean("shortTaskJmsFactory")
DefaultJmsListenerContainerFactory shortTaskJmsFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setMaxMessagesPerTask(20);
    factory.setReceiveTimeout(500L);
    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
    destination = "demo.task.events",
    containerFactory = "shortTaskJmsFactory")
public void onEvent(String body) {
    System.out.println(body);
}
~~~

Đây là **hai trích đoạn**, cần đặt trong Spring-managed configuration/component với imports đúng. Tên `shortTaskJmsFactory` là **bean name**, không phải destination. Một listener không đặt `containerFactory` sẽ dùng factory mặc định thay vì tự chọn custom factory này.

### 5.2. Đừng nhầm với cấu hình của JmsTemplate

`JmsTemplate.setReceiveTimeout(...)` cấu hình timeout cho **lời gọi synchronous receive của JmsTemplate**. Nó **không** tự thiết lập `maxMessagesPerTask` hoặc receive timeout của listener container.

Với `DefaultMessageListenerContainer`, timeout được đặt trên container/factory:

~~~java
factory.setReceiveTimeout(1_000L);
~~~

Trong Spring Framework 6.2, Default container mặc định **1000 ms** cho mỗi vòng receive, khác với mặc định chờ vô hạn của lời gọi synchronous JmsTemplate receive (nếu không cấu hình). Đừng dùng chung một giá trị config theo giả định hai API là một.

## 6. Quan hệ với receiveTimeout: thời gian một lần thử nhận

`receiveTimeout` quy định **thời gian tối đa mỗi lần chờ message** của một receive attempt.

| Cấu hình | Hành vi ở Default container |
| --- | --- |
| `setReceiveTimeout(1_000L)` | Mỗi lần receive có thể chờ khoảng 1 giây trước khi trả null |
| `setReceiveTimeout(250L)` | Có thể kiểm tra idle/stop nhanh hơn nhưng tăng tần suất polling |
| `setReceiveTimeout(5_000L)` | Mỗi lần receive chờ lâu hơn nếu không có message |
| `setReceiveTimeout(0L)` | Nhận có thể chờ vô hạn; với listener container/transactions điều này có thể gây khó shutdown, không nên dùng tùy tiện |
| Giá trị âm như `-1L` | No-wait receive; có thể làm vòng lặp nhận trống chạy rất nhanh |

Ví dụ cấu hình:

~~~java
factory.setMaxMessagesPerTask(3);
factory.setReceiveTimeout(1_000L);
~~~

Nếu queue rỗng suốt ba receive attempts, một task có thể chờ xấp xỉ **3 giây** cộng overhead để hoàn thành ba lần thử. Nếu nhận được message, vòng xử lý còn bao gồm thời gian handler, ack/transaction và provider operations.

**Không được coi** `maxMessagesPerTask * receiveTimeout` là **hard deadline** cho task: có message có thể đến ngay, handler có thể chạy lâu, retry/recovery có thể thêm thời gian. Giới hạn là **số lần thử receive**, không phải đồng hồ đo task lifetime.

### 6.1. Với timeout vô hạn thì sao?

Nếu một lần `receive()` chờ vô hạn vì không có message, bộ đếm maxMessagesPerTask **không tăng cho đến khi lời gọi receive ấy kết thúc**. Do đó ngay cả `maxMessagesPerTask=1` cũng không tự làm một blocking `receive(0)` thoát sau 1 giây. Lựa chọn timeout cần xét shutdown responsiveness và transaction timeout riêng.

### 6.2. Ví dụ đếm attempt mà không nhầm với message

Giả định `maxMessagesPerTask=5`, `receiveTimeout=1000` và một task gặp chuỗi:

~~~text
receive #1 -> Message A
receive #2 -> null (timeout)
receive #3 -> Message B
receive #4 -> null (timeout)
receive #5 -> null (timeout)
--------------------------
5 attempts, 2 messages xử lý
task đã đạt trần số attempts
~~~

Khi task đạt ngưỡng, container có thể reschedule công việc hoặc cho surplus consumer kết thúc nếu đủ điều kiện idle/scale-down. Đó không phải một “batch 5 message”.

## 7. Idle behavior: ba cấu hình dễ nhầm

Cùng với `maxMessagesPerTask`, Spring DefaultMessageListenerContainer 6.2 còn có các thuộc tính **idle-related** rất quan trọng.

| Thuộc tính | API trên DefaultMessageListenerContainer | Đơn vị tính | Ý nghĩa |
| --- | --- | --- | --- |
| `maxMessagesPerTask` | `setMaxMessagesPerTask(int)` | **Số receive attempts/task** | Cho task nhường/chuyển lượt sau một số lần nhận thử |
| `idleReceivesPerTaskLimit` | `setIdleReceivesPerTaskLimit(int)` | **Số lần receive liên tiếp trả null** | Xác định task đã idle sau một chuỗi nhận trống |
| `idleTaskExecutionLimit` | `setIdleTaskExecutionLimit(int)` | **Số task executions được đánh dấu idle** | Quyết định surplus consumer có nên dừng sau nhiều lượt idle |
| `idleConsumerLimit` | `setIdleConsumerLimit(int)` | **Số consumer idle cho phép** | Điều chỉnh điều kiện scheduling invokers mới |
| `receiveTimeout` | `setReceiveTimeout(long)` | Milliseconds mỗi receive | Ảnh hưởng tốc độ phát sinh null/idle |
| `concurrentConsumers` | `setConcurrentConsumers(int)` | Core consumer count | Số consumer tối thiểu duy trì |
| `maxConcurrentConsumers` | `setMaxConcurrentConsumers(int)` | Max consumer count | Trần tăng thêm surplus consumers |

Ba thuộc tính đầu không cùng một loại giới hạn: **attempts**, **consecutive idle receives**, và **idle task executions**. Không đổi chúng cho nhau.

### 7.1. idleReceivesPerTaskLimit

Theo Javadoc Spring 6.2, `idleReceivesPerTaskLimit` đánh dấu task là idle khi có đủ số receive liên tiếp trả `null` sau timeout. Nó hữu ích nếu muốn task được xem là idle **trước khi đạt maxMessagesPerTask lớn**.

Ví dụ về ý tưởng:

~~~java
container.setMaxMessagesPerTask(500);
container.setIdleReceivesPerTaskLimit(60);
container.setReceiveTimeout(1_000L);
container.setIdleTaskExecutionLimit(1);
~~~

Nếu không còn message, task có thể bị xem là idle sau 60 lần nhận trống liên tiếp (xấp xỉ một phút với receiveTimeout=1 giây), **không phải cần đợi đủ 500 lần receive attempts**. Sau đó hành vi release/scale-down còn phụ thuộc task là core hay surplus, executor và các giới hạn khác.

**Lưu ý Spring 6.2:** idle-receives limit riêng lẻ về cơ bản tác động lên **surplus consumers** vượt core; với core consumer, hành vi rescheduling cần xét thêm `maxMessagesPerTask` và executor. Nó không phải một lệnh cho phép giảm số consumers xuống dưới `concurrentConsumers`.

### 7.2. idleTaskExecutionLimit

`idleTaskExecutionLimit` mặc định **1**. Nó giới hạn số lần thực thi task được coi là idle trước khi một **surplus consumer** nên rời khỏi nhóm nhận, tránh giữ tài nguyên khi tải đã giảm.

Giả sử cấu hình động:

~~~java
container.setConcurrentConsumers(1);
container.setMaxConcurrentConsumers(4);
container.setIdleTaskExecutionLimit(3);
~~~

Khi queue bận, có thể tăng tới tối đa 4 consumers nếu điều kiện scheduling cho phép. Khi yên ắng đủ lâu, các surplus consumers có thể lần lượt kết thúc; **core consumer tối thiểu 1 vẫn được duy trì** cho tới khi container stop/shutdown.

Giới hạn 3 không có nghĩa consumer kết thúc sau ba message. Đây là giới hạn **idle task executions**, không đếm số message thành công.

### 7.3. idleConsumerLimit

`idleConsumerLimit` mặc định **1**. Nó giới hạn số idle consumers mà container chấp nhận khi xem xét scheduling thêm invokers. Tăng giá trị này có thể làm container tăng số invokers mạnh hơn để sẵn sàng nhận, nhưng đổi lại có thể tăng tài nguyên JMS.

Không nên tăng `idleConsumerLimit` chỉ để “xử lý 10 message mỗi task”. Hai mục tiêu khác nhau: **aggressiveness khi scale-up** và **task receive-attempt lifespan**.

### 7.4. Mặc định 10 idle receives dành cho trường hợp nào?

Với executor mặc định/simple non-pooling trong Spring 6.2, `idleReceivesPerTaskLimit` có giá trị hiệu dụng mặc định **10 cho surplus consumers**. Nếu receive timeout ở mặc định 1000 ms và liên tục không có message, một surplus task có thể scale-down sau khoảng **10 giây** nhận trống, tùy các yếu tố khác.

Đừng nhầm con số 10 đó với mặc định `maxMessagesPerTask=10` của executor thích task ngắn. Hai “10” xuất hiện trong **hai bối cảnh và hai bộ đếm** khác nhau.

## 8. Vòng đời task khi container co giãn (dynamic scaling)

Dynamic scaling không tự bật chỉ bằng `maxMessagesPerTask`. Nó cần:

~~~java
container.setConcurrentConsumers(1);
container.setMaxConcurrentConsumers(5);
~~~

Container có quyền chạy **tối thiểu 1 và tối đa 5 consumers**. Khi có message, nó có thể lên lịch thêm invokers trong phạm vi này nếu điều kiện cho phép. Khi không còn message và vượt idle limits, surplus consumers được scale-down.

~~~text
Lúc nhàn rỗi:
    core = 1 consumer

Tải tăng:
    core 1 -> 2 -> 3 ... tối đa 5
    (không phải mỗi message lại tạo một consumer)

Tải giảm:
    surplus consumers trở nên idle
         |
         v
    idleReceive / idleTaskExecution logic
         |
         v
    surplus consumers rời đi
    core 1 vẫn được duy trì

Container stop:
    các task/consumers được dừng theo lifecycle
~~~

Một vài nguyên tắc cần nhớ:

- `maxMessagesPerTask` quyết định **độ dài mỗi task execution theo receive attempts**.
- `maxConcurrentConsumers` quyết định **tối đa bao nhiêu consumers có thể tồn tại**.
- `idleTaskExecutionLimit` và `idleReceivesPerTaskLimit` ảnh hưởng thời điểm **surplus consumers** giảm xuống.
- `idleConsumerLimit` ảnh hưởng việc **scheduling thêm** consumer.
- `receiveTimeout` ảnh hưởng thời gian một receive attempt chờ message.
- Một task kết thúc **không** làm mức core consumer giảm dưới `concurrentConsumers`.
- Không có lời hứa rằng container sẽ đạt max consumers ngay khi queue depth lớn; scaling do thuật toán/demand/provider và executor quyết định.

### 8.1. Thận trọng khi dùng Topic

Với Topic truyền thống, tạo nhiều consumers/subscriptions có thể làm **cùng một sự kiện được nhận nhiều lần** trong cùng instance, tùy subscription configuration. Dynamic scaling của Default container phù hợp hơn với **Queue**; Spring Javadoc khuyến nghị thường giữ **một consumer** cho Topic, trừ khi provider-specific setup bảo đảm điều bạn cần.

Nếu nghiệp vụ yêu cầu từng message xử lý theo đúng thứ tự, tăng concurrent consumers trên Queue cũng có thể phá kỳ vọng ordering, vì nhiều listener methods chạy song song. Khi đó chọn `concurrentConsumers=1` hoặc dùng JMS message groups/partitioning theo provider và kiểm thử thực tế.

## 9. Cấu hình Java 17+ trong Spring Boot 3.x với Artemis

Ví dụ đầy đủ minh họa:

- Cấu hình một `DefaultJmsListenerContainerFactory` có `maxMessagesPerTask=3`.
- Đặt `receiveTimeout=500 ms` để nhận trống không block quá lâu.
- Chỉ dùng **1 consumer** trong demo, tránh concurrency và độ bất định thứ tự.
- Đăng ký `@JmsListener` với ID và kiểm tra container thực sử dụng cấu hình.
- Gửi **6 messages** rồi kiểm tra rằng listener vẫn xử lý tất cả, dù mỗi task execution có giới hạn 3 receive attempts.

### 9.1. Chuẩn bị

Tạo Maven project ở [Spring Initializr](https://start.spring.io/) với Java 17+, Spring Boot **3.x**, group `com.example`, artifact `jms-task-lifecycle-demo` và dependency **Spring for Apache ActiveMQ Artemis**, tương ứng Maven starter:

~~~text
org.springframework.boot:spring-boot-starter-artemis
~~~

Cần một **Artemis broker đang chạy bên ngoài process** ở `tcp://localhost:61616`. Broker phải cho phép user/password của ứng dụng kết nối, gửi và consume queue `demo.task.lifecycle`. Queue được tạo trước hoặc broker cho phép auto-create theo chính sách. Nên dùng queue sạch, không có consumer khác để có output dễ kiểm tra.

Thiết lập biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` phù hợp với broker. Không ghi mật khẩu thật vào Git.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`spring.artemis.mode=native` **không tự chạy Artemis broker**. Boot chỉ cấu hình JMS client theo properties và dependency; việc tạo queue/quyền bảo mật nằm ở broker.

### 9.2. Mã Java hoàn chỉnh

Tệp `src/main/java/com/example/JmsTaskLifecycleApplication.java`:

~~~java
package com.example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsTaskLifecycleApplication {

    private static final String QUEUE = "demo.task.lifecycle";

    public static void main(String[] args) {
        SpringApplication.run(JmsTaskLifecycleApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setMaxMessagesPerTask(3);
        factory.setReceiveTimeout(500L);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner demo(
            JmsTemplate template,
            TaskLifecycleListener listener,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            var endpoint =
                    registry.getListenerContainer("taskLifecycleEndpoint");

            if (!(endpoint instanceof DefaultMessageListenerContainer dmlc)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            System.out.println("MAX_ATTEMPTS="
                    + dmlc.getMaxMessagesPerTask());

            for (int i = 1; i <= 6; i++) {
                template.convertAndSend(QUEUE, "event-" + i);
            }
            System.out.println("SENT=6");

            boolean allReceived = listener.awaitAll();
            System.out.println("ALL_RECEIVED=" + allReceived);
            System.out.println("HANDLED_COUNT=" + listener.handledCount());
        };
    }
}

@Component
class TaskLifecycleListener {

    private final AtomicInteger handled = new AtomicInteger();
    private final CountDownLatch latch = new CountDownLatch(6);

    @JmsListener(
            id = "taskLifecycleEndpoint",
            destination = "demo.task.lifecycle")
    public void receive(String body) {
        handled.incrementAndGet();
        System.out.println("HANDLED=" + body);
        latch.countDown();
    }

    boolean awaitAll() throws InterruptedException {
        return latch.await(20, TimeUnit.SECONDS);
    }

    int handledCount() {
        return handled.get();
    }
}
~~~

**Kiểm tra khả năng biên dịch:** Code có một public class trùng tên file và một package-private `@Component` ở cùng package được Spring Boot scan. `@EnableJms` bật annotation-driven endpoint registration; trong Spring Boot thông thường hạ tầng này còn có thể được auto-configured, nhưng đặt annotation để mục tiêu học rõ ràng.

**Kiểm tra cấu hình:** `jmsListenerContainerFactory` là tên default factory bean, dùng `jakarta.jms.ConnectionFactory` do Boot cấu hình. `factory.setMaxMessagesPerTask(3)` là API có thật của Spring JMS 6.x; nó áp dụng cho `DefaultMessageListenerContainer` được factory tạo.

**Kiểm tra listener:** `@JmsListener(id=...)` tạo endpoint `taskLifecycleEndpoint` tra được từ `JmsListenerEndpointRegistry`. Code kiểm tra `instanceof DefaultMessageListenerContainer` trước khi gọi `getMaxMessagesPerTask()`, không cast mù quáng.

**Kiểm tra kết quả:** `CountDownLatch(6)` đợi sáu lần listener xử lý; `AtomicInteger` ghi số lần method được gọi, thread-safe ngay cả khi sau này điều chỉnh concurrency. Latch chỉ là công cụ test/demonstration, không thay broker acknowledgment hoặc business transaction.

### 9.3. Chạy

Tại thư mục dự án Maven:

~~~bash
mvn spring-boot:run
~~~

Nếu project có Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với broker/queue/credentials đúng, queue sạch và không có consumer khác, những dòng do chương trình in ra gồm:

~~~text
MAX_ATTEMPTS=3
HANDLED=event-1
HANDLED=event-2
HANDLED=event-3
HANDLED=event-4
HANDLED=event-5
HANDLED=event-6
SENT=6
ALL_RECEIVED=true
HANDLED_COUNT=6
~~~

Đây là **tập dòng kỳ vọng**, **không phải thứ tự stdout bắt buộc**. `MAX_ATTEMPTS=3` luôn được in trước vòng gửi của AppRunner. `SENT=6` có thể xuất hiện trước hoặc sau một số dòng `HANDLED` vì listener chạy bất đồng bộ. Hai dòng cuối được in sau khi `awaitAll()` trả về; nếu timeout hoặc lỗi/queue có dữ liệu cũ, `ALL_RECEIVED` có thể là false và count khác 6. Spring Boot startup logs cũng xuất hiện.

**Điểm kiểm chứng chính:** Dù `MAX_ATTEMPTS=3`, cả **sáu** message vẫn có thể được xử lý trong suốt hoạt động của listener. Task được thay lượt/reschedule, **không** có luật tổng số message của toàn application bằng 3.

### 9.4. Vì sao không thể nhìn log để suy ra “mỗi task xử lý đúng 3 message”?

Ngay cả với sáu message gửi liên tiếp, task có thể gặp receive attempts trả null do timing, broker delivery, transaction/connection setup hoặc sự thay đổi tải. Thời điểm task kết thúc còn liên quan rescheduling và idle logic.

Chỉ đọc dòng `HANDLED=...` không đủ xác định **task boundary**. Muốn quan sát task lifecycle, cần kết hợp Spring JMS debug logs, thread/task executor metrics và nếu cần profiling/JFR. Trong một thread pool, thread name có thể được tái sử dụng qua nhiều task, nên log thread name cũng không phải ID duy nhất của task.

### 9.5. Vì sao demo chọn concurrency = 1?

`maxMessagesPerTask` và `concurrency` là hai tham số khác nhau. Với một core consumer, mã dễ quan sát mà không phải giải thích interleaving giữa nhiều consumers.

Nếu chuyển sang:

~~~java
factory.setConcurrency("2-5");
~~~

container có thể chạy 2 core và tối đa 5 concurrent consumers, mỗi task của từng consumer có giới hạn receive attempts riêng. Không có “giới hạn 3 messages chia cho cả 5 consumers”. Cần test lại ordering, throughput, database connection pool và idempotency trong workload đồng thời.

## 10. Lựa chọn TaskExecutor: dedicated threads hay thread pool?

Mặc định DefaultMessageListenerContainer dùng `SimpleAsyncTaskExecutor`, tạo worker threads cho listener invokers. Với cấu hình mặc định và `maxMessagesPerTask=-1`, invoker tasks có thể sống rất lâu để hạn chế scheduling overhead.

Nếu tích hợp với `ThreadPoolTaskExecutor`/managed thread pool, việc một JMS consumer chiếm thread suốt vòng đời pool có thể khiến pool thiếu thread cho công việc khác. Task hữu hạn cho phép engine lên lịch theo từng đợt.

### 10.1. Cấu hình executor riêng (biến thể, không ghép trùng với demo)

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor jmsConsumerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("jms-consumer-");
    return executor;
}
~~~

Trong **factory khác**, inject executor và chọn:

~~~java
factory.setTaskExecutor(jmsConsumerExecutor);
factory.setMaxMessagesPerTask(20);
factory.setConcurrency("1-4");
~~~

Đây là **trích đoạn cấu hình thay thế**, yêu cầu bean `jmsConsumerExecutor` được inject đúng kiểu; nó **không** nằm sẵn trong demo phần 9. Với Spring quản lý bean executor, Spring thực hiện initialization/shutdown theo lifecycle tương ứng.

Khi dùng thread pool, cần kiểm tra:

1. Pool đủ thread cho **maxConcurrentConsumers** mà bạn muốn, cộng workload khác nếu pool không dedicated.
2. Queue capacity/ rejection policy không làm các JMS invokers bị từ chối hoặc starve.
3. `maxMessagesPerTask` không quá lớn đến mức task giữ thread hầu như mãi, nhưng cũng không quá nhỏ gây reschedule quá dày.
4. Config session caching phù hợp với provider; không chỉ tối ưu thread rồi bỏ qua JMS resources.
5. Shutdown và recovery không giữ các tasks bị block trong `receiveTimeout=0`.

**Lời khuyên:** nếu chỉ có một vài JMS listeners và không có yêu cầu managed pool, ưu tiên cấu hình đơn giản với executor mặc định. Chỉ tích hợp pool riêng khi có lý do đo được và có observability.

### 10.2. Lợi ích và chi phí khi giới hạn task

| Giá trị thấp, ví dụ 3 | Giá trị vừa, ví dụ 20–100 | Không giới hạn, -1 |
| --- | --- | --- |
| Task chuyển lượt thường xuyên | Cân bằng giữa scheduling và giữ task | Invoker có thể chạy dài |
| Dễ quan sát vòng đời trong demo | Có thể phù hợp pooled executor | Phù hợp dedicated threads |
| Có thể tạo overhead context-switch/reinit | Thường dùng làm điểm bắt đầu tuning | Có thể chiếm thread của pool dài hạn |
| Không đồng nghĩa xử lý chính xác 3 messages | Không đồng nghĩa batch transaction 20–100 messages | Không đồng nghĩa container không bao giờ stop |

Không có lời hứa rằng đổi `3 → 20` sẽ tăng throughput theo tỷ lệ. Chi phí nhận/gửi JMS, transactions, message size, session cache và business I/O thường quyết định nhiều hơn.

## 11. Resource caching và vòng đời JMS Session/MessageConsumer

Khi một invoker task kết thúc, **không được mặc định** rằng mọi JMS `Connection`, `Session` và `MessageConsumer` được đóng ngay rồi tạo mới từ đầu. Tài nguyên thực chịu ảnh hưởng của:

- `cacheLevel`/`CACHE_AUTO`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`.
- Transaction management (local transaction hay external `PlatformTransactionManager`/JTA).
- JMS provider/client và khả năng recovery.
- Task rescheduling, consumer scale-up/scale-down, container stop/shutdown.

Trong môi trường native JMS, DMLC thường cache Session/MessageConsumer theo listener threads để hạn chế overhead. Với external transaction manager, mức caching mặc định có thể thay đổi nhằm bảo đảm tương thích Jakarta EE servers.

### 11.1. CachingConnectionFactory có thể gây rủi ro

Spring Javadoc cảnh báo rằng dùng `CachingConnectionFactory` bên ngoài một `DefaultMessageListenerContainer` có thể có hạn chế, đặc biệt khi dynamic scaling và custom `maxMessagesPerTask`: một message có thể được chuyển tới **cached consumer đã không còn gắn với listener container** theo cách người vận hành mong muốn.

Vì vậy:

- Tránh tự động “cache hai lớp” cho listener container khi chưa kiểm tra provider behavior.
- Thường nên để chính `DefaultMessageListenerContainer` quản lý caching của JMS resources cho listener.
- Nếu phải dùng `CachingConnectionFactory`, kiểm thử stop/restart, scaling, provider prefetch và resource cleanup thực tế.

`maxMessagesPerTask` không phải một phương thức “đóng socket sau N message”. Không dùng nó thay cơ chế connection recovery, keep-alive hay pool sizing.

### 11.2. Kiểm tra session/transaction trước khi tune

Nếu dùng `factory.setSessionTransacted(true)`, từng message nhận và listener processing được gắn với JMS session transaction theo semantics container. Một task xử lý nhiều message **không** mặc nhiên là một transaction gộp mọi message trong task.

Cũng không phải task kết thúc thì message chưa acknowledge sẽ bị bỏ qua hoặc commit theo “batch size”. Ack/commit/rollback phụ thuộc chính sách session, listener success/failure, external transaction và provider.

## 12. Tác động đến reliability: không nhầm task turnover với redelivery

Giả sử handler ném exception ở một message. Kết quả có thể gồm:

- Container xử lý lỗi và rollback JMS session (nếu configured transacted).
- Broker redeliver message sau đó, tùy retry/DLQ policy.
- Container tiếp tục nhận hoặc recovery connection/session nếu lỗi hạ tầng.
- Task hiện tại có thể hết attempt limit hoặc đi vào recovery, nhưng đó **không** tự quyết định business transaction.

**Không đúng** khi nói “`maxMessagesPerTask=5` nghĩa là cứ năm message mới commit một lần.” Không có quy tắc như vậy trong Spring Default container.

Ví dụ:

~~~java
factory.setSessionTransacted(true);
factory.setMaxMessagesPerTask(5);
~~~

Hai dòng phục vụ hai trách nhiệm khác:

1. `sessionTransacted=true`: lựa chọn JMS local transaction.
2. `maxMessagesPerTask=5`: giới hạn receive attempts mỗi task execution.

Nếu cần mỗi message có thao tác DB và JMS atomic, local JMS transaction không tự mở transaction đồng nhất với database. Cần cân nhắc outbox/inbox, idempotency hoặc transaction coordination/JTA/XA đúng yêu cầu.

### 12.1. Vì sao vẫn cần idempotency?

Task turnover không gây duplicate theo mục tiêu thiết kế, nhưng bất kỳ hệ thống messaging nào cũng có thể redeliver sau lỗi, rollback hoặc reconnect. Listener phải có logic nhận diện message đã xử lý khi điều đó quan trọng.

Thay vì tin “task không restart nên sẽ không trùng”, hãy thiết kế:

- Business/event ID ổn định.
- Ghi nhận xử lý idempotent bằng unique constraint/inbox.
- Retry với backoff, DLQ cho poison messages.
- Logging và metrics tách task lifecycle khỏi delivery count.

### 12.2. AUTO_ACKNOWLEDGE và transaction

Spring DMLC Javadoc khuyến nghị dùng `sessionTransacted=true` hoặc external transaction manager cho các xử lý quan trọng. Với mặc định `AUTO_ACKNOWLEDGE` của DMLC, acknowledgment có thể xảy ra **trước listener execution**, khiến exception trong business method không tự bảo đảm message được redeliver.

Không suy ra từ `maxMessagesPerTask` rằng listener đã đảm bảo at-least-once/exactly-once. Cần cấu hình ack/transaction phù hợp và kiểm thử với broker thật.

## 13. Quan sát trạng thái container và task

`JmsListenerEndpointRegistry` cho phép tra endpoint theo `id`:

~~~java
@JmsListener(
        id = "billingEndpoint",
        destination = "billing.incoming")
public void consume(String body) {
    // ...
}
~~~

Một service quản trị có thể lấy:

~~~java
var endpoint = registry.getListenerContainer("billingEndpoint");
if (endpoint instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println("CONFIGURED_MAX_ATTEMPTS="
            + dmlc.getMaxMessagesPerTask());
    System.out.println("CORE_CONSUMERS="
            + dmlc.getConcurrentConsumers());
    System.out.println("MAX_CONSUMERS="
            + dmlc.getMaxConcurrentConsumers());
    System.out.println("SCHEDULED_CONSUMERS="
            + dmlc.getScheduledConsumerCount());
    System.out.println("ACTIVE_CONSUMERS="
            + dmlc.getActiveConsumerCount());
    System.out.println("RUNNING=" + dmlc.isRunning());
}
~~~

Đây là **đoạn trích**, `registry` phải được inject từ Spring context và endpoint ID phải có thật. Các getter là API thực tế của `DefaultMessageListenerContainer` Spring 6.2.

### 13.1. Đọc các con số cho đúng

| Metric/getter | Giải thích | Không nên suy ra |
| --- | --- | --- |
| `getMaxMessagesPerTask()` | Giới hạn receive attempts mỗi task | Tổng messages tối đa trong app |
| `getConcurrentConsumers()` | Cấu hình core consumers | Đúng bằng active consumers tại mọi thời điểm |
| `getMaxConcurrentConsumers()` | Trần cấu hình consumers | Container luôn tạo đủ consumer đến trần |
| `getScheduledConsumerCount()` | Số invokers đang scheduled | Số message đã xử lý |
| `getActiveConsumerCount()` | Số consumers hiện active | Queue depth/throughput/số transaction commit |
| `isRunning()` | Container được start theo lifecycle | Broker có message hoặc nghiệp vụ thành công |

Dùng thêm metrics của JMS broker như **queue depth**, **consumer count**, **message age**, **redelivery/DLQ**, cùng ứng dụng metrics **processed/sec**, **handler latency**, **error rate**, **CPU/thread use**.

### 13.2. Vì sao thread name không đủ?

Trong `ThreadPoolTaskExecutor`, một thread có thể chạy task A, sau đó task B. Ngược lại, với non-pooling executor, task reschedule có thể chạy trên một thread khác. Vì vậy log như `Thread.currentThread().getName()` chỉ cho bạn biết **thread xử lý**, không phải ID bền vững của “receive task”.

Nếu muốn nghiên cứu task-level execution, xem log `org.springframework.jms.listener` ở mức DEBUG trong môi trường test (không bật quá verbose trong production), JFR/profiler hoặc executor instrumentation. Không dùng thread count để suy luận “mỗi message một thread” khi container đang dùng receive loop.

## 14. Tuning trong các tình huống thực tế

### 14.1. Dịch vụ ổn định, traffic đều, queue ít

Gợi ý xuất phát:

~~~java
factory.setConcurrency("1");
factory.setReceiveTimeout(1_000L);
// Có thể giữ maxMessagesPerTask mặc định tùy executor.
~~~

Nếu dùng executor mặc định, việc giữ invoker task dài hạn thường hợp lý. Không buộc phải đặt maxMessagesPerTask thấp chỉ vì thuộc tính tồn tại.

### 14.2. Nhiều listener dùng shared thread pool

Nếu có một pool được dùng cho nhiều workloads, cần tránh một vài long-lived JMS receive tasks chiếm mọi threads.

~~~java
factory.setMaxMessagesPerTask(20);
factory.setReceiveTimeout(1_000L);
~~~

Đây có thể là điểm khởi đầu, không phải thông số “tối ưu” cho mọi ứng dụng. Theo dõi scheduling fairness, task rejection, pool active count và queue backlog. Nếu thread pool quá nhỏ hoặc có queue capacity không phù hợp, có thể xảy ra starvation hoặc task submissions không được xử lý.

### 14.3. Traffic burst, cần scale-up/scale-down

Ví dụ container trực tiếp:

~~~java
container.setConcurrentConsumers(1);
container.setMaxConcurrentConsumers(6);
container.setIdleTaskExecutionLimit(2);
container.setIdleConsumerLimit(1);
container.setMaxMessagesPerTask(30);
container.setReceiveTimeout(1_000L);
~~~

Đây là **cấu hình minh họa**, không phải thông số production đã benchmark. Lưu ý mỗi biến ảnh hưởng khía cạnh riêng: core/max consumers, idle task count, aggressiveness of scheduling, attempts/task và timeout. Tăng đồng thời mọi tham số không có nghĩa throughput sẽ tăng.

### 14.4. Traffic thưa, muốn giải phóng surplus nhanh

Cân nhắc các giá trị nhận trống, chẳng hạn đặt `receiveTimeout` khoảng 250–1000 ms trong một môi trường thử nghiệm, `idleReceivesPerTaskLimit` phù hợp và `idleTaskExecutionLimit` nhỏ. Nhưng nếu cấu hình quá nhạy, số consumer có thể **scale up/down liên tục** khi message đến theo cụm, làm tăng connection/session churn.

Đừng giảm core consumers xuống 0 bằng cách ép các idle limit; core min của DMLC cần được duy trì theo cấu hình. Nếu muốn tạm ngừng toàn bộ consume, sử dụng lifecycle `stop()` hoặc tắt auto-startup với quy trình vận hành rõ.

### 14.5. Long-running handler

Nếu listener xử lý một message trong 20 giây, `maxMessagesPerTask=3` không tự ngắt việc xử lý sau 3 giây. Task thường tính lần receive và chạy listener theo đường synchronous; thời gian handler làm task dài hơn.

Để giới hạn thời gian xử lý nghiệp vụ, dùng timeout ở DB/HTTP client, cancellation semantics phù hợp, bounded queues/concurrency và observability. Đừng dùng `maxMessagesPerTask` như business processing timeout.

## 15. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `maxMessagesPerTask=5` là tối đa 5 messages của cả listener | Chỉ áp dụng cho một invoker task execution | Container có thể reschedule để tiếp tục consume |
| Giá trị 5 luôn có 5 message thành công | Receive attempt timeout trả null cũng được tính | Có thể xử lý ít hơn 5 messages trong task |
| Đặt giới hạn này sẽ giảm số consumers xuống 5 | Đây không phải concurrency setting | Dùng `concurrentConsumers`/`maxConcurrentConsumers` |
| Đặt giới hạn này sẽ commit mỗi 5 messages | Không phải transaction batch size | Ack/commit tùy session/transaction |
| `maxMessagesPerTask=-1` nghĩa không bao giờ dừng thread | Stop/recovery/idle có thể tác động | -1 chỉ bỏ trần attempts theo thuộc tính này |
| Container có maxMessagesPerTask mặc định luôn 10 | Executor thường mặc định -1 | Xem `TaskExecutor` và `prefersShortLivedTasks()` |
| `receiveTimeout=1000` là toàn bộ task chỉ sống 1 giây | Timeout tính **mỗi lần receive** | Một task gồm nhiều attempts + handler time |
| `idleTaskExecutionLimit=3` là 3 idle receives | Nó đếm idle task executions | Phân biệt `idleReceivesPerTaskLimit` |
| Core consumer bị đóng sau một chuỗi null | Core min được container duy trì | Chủ yếu surplus consumers được scale-down |
| Mỗi task tương ứng một JMS session mới | Cache level/provider/transaction ảnh hưởng | Đừng suy luận resource lifecycle từ task count |
| `maxMessagesPerTask` tự bật dynamic scaling | Scaling cần maxConcurrentConsumers > concurrentConsumers | Phối hợp concurrency và idle limits |
| Tăng consumers trên Topic giống Queue | Topic/subscription semantics khác | Tránh duplicate subscription/delivery |
| Chỉ nhìn log thread name là biết số task | Thread pool tái sử dụng thread | Đo task/executor riêng |
| Cấu hình JmsTemplate receive timeout cũng đổi listener | Hai thành phần có config riêng | Đặt trên DefaultJmsListenerContainerFactory |
| Tăng maxMessagesPerTask luôn tăng throughput | Có thể tăng pool starvation | Benchmark handler/broker/pool |
| Giảm maxMessagesPerTask luôn giảm memory | Có thể tăng task churn/overhead | Theo dõi resources thực tế |
| Dùng CachingConnectionFactory càng nhiều càng tốt | Có thể xung đột với DMLC caching/scaling | Ưu tiên để listener container cache đúng |
| DMLC và SimpleMessageListenerContainer có task loop như nhau | Simple dựa vào provider callback | Áp dụng thuộc tính đúng container type |

## 16. Checklist kiểm thử và vận hành

Dùng checklist sau khi thử chỉnh `maxMessagesPerTask`:

1. Xác minh listener thật sự dùng **DefaultMessageListenerContainer**, không phải `SimpleMessageListenerContainer`.
2. Kiểm tra `getMaxMessagesPerTask()` trên container được registry đăng ký.
3. Kiểm tra số core consumers, max consumers và active/scheduled counts.
4. Xác định task executor là `SimpleAsyncTaskExecutor` hay pooled/SchedulingTaskExecutor.
5. Kiểm tra `prefersShortLivedTasks()` hoặc đặt explicit limit khi muốn chắc chắn.
6. Xác định `receiveTimeout` thực và timeout của transaction manager nếu có.
7. Gửi số message **lớn hơn** `maxMessagesPerTask`; xác minh listener vẫn xử lý qua các task.
8. Gửi message thưa, có các lần nhận `null`; đo task turnover và idle behavior.
9. Tải tăng theo burst, xác nhận scale-up không vượt max và scale-down không giảm dưới core.
10. Kiểm tra concurrency không phá ordering/idempotency của nghiệp vụ.
11. Test broker restart, connection recovery, stop/start container và graceful shutdown.
12. Đo queue depth, latency, throughput, CPU/thread count, session/consumer count, task rejection, GC.
13. Nếu dùng CachingConnectionFactory, kiểm chứng đặc biệt provider prefetch và stop/restart.
14. Kiểm chứng rollback/redelivery/DLQ khi listener method ném exception.
15. Lưu kết quả benchmark trước–sau; chỉ đổi một vài biến mỗi lượt test để hiểu nguyên nhân.
16. Không áp thông số demo `maxMessagesPerTask=3` thẳng vào production nếu chưa benchmark.

### 16.1. Bộ kịch bản test ngắn

| Kịch bản | Điều muốn chứng minh |
| --- | --- |
| Gửi 10 messages, maxMessagesPerTask=3 | Tổng số message xử lý có thể lớn hơn 3 |
| Queue rỗng, maxMessagesPerTask=3, timeout 500ms | Task có thể hết 3 receive attempts mà không xử lý message nào |
| Core 1, max 4, traffic tăng rồi giảm | Số consumers tăng/giảm trong khoảng 1–4 |
| Có thread pool nhỏ, maxMessagesPerTask=-1 | Cần quan sát thread starvation và pool occupancy |
| Có lỗi handler sau receive | Kiểm tra transaction/redelivery, **không** suy luận theo task boundary |
| Stop container khi receiveTimeout rất lớn | Đánh giá shutdown responsiveness |
| Bật external CachingConnectionFactory | Kiểm tra caching và consumer lifecycle thực |
| Message có JMSXGroupID/ordering constraints | Kiểm tra nhóm/ordering khi concurrency thay đổi |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `maxMessagesPerTask=3` có khiến listener ngừng sau ba message của cả ứng dụng không?

**Đáp án:** Không. Nó giới hạn ba **receive attempts cho mỗi task execution**, và container có thể reschedule task để tiếp tục nhận.

**Câu 2.** Trong ba lần receive, hai lần trả `null` và một lần nhận message. Có vượt maxMessagesPerTask=3 chưa?

**Đáp án:** Đã dùng đủ ba attempts. Trong task đó chỉ có một message được xử lý thành công.

**Câu 3.** Default maxMessagesPerTask của Spring DMLC luôn là 10?

**Đáp án:** Không. Với executor thường/non-pooling mặc định là **-1**; với `SchedulingTaskExecutor.prefersShortLivedTasks()==true` mặc định thường là **10** theo Spring 6.2 Javadoc.

**Câu 4.** Vì sao `receiveTimeout=0` có thể làm task bị block lâu dù maxMessagesPerTask thấp?

**Đáp án:** Bộ đếm attempts chỉ tiến khi lời gọi receive quay về; `receive(0)` có thể chờ vô hạn trước khi lượt ấy kết thúc.

**Câu 5.** `setMaxMessagesPerTask(10)` và `setMaxConcurrentConsumers(10)` khác gì nhau?

**Đáp án:** Một cái giới hạn receive attempts/task, cái kia giới hạn số consumers có thể hoạt động đồng thời.

**Câu 6.** `idleReceivesPerTaskLimit` và `idleTaskExecutionLimit` khác gì?

**Đáp án:** Cái đầu đếm số lần receive liên tiếp trả null trong một task; cái sau đếm số task executions bị coi là idle trước khi surplus consumer có thể kết thúc.

**Câu 7.** Sau khi một task đạt max attempts, JMS MessageConsumer bắt buộc phải đóng ngay?

**Đáp án:** Không thể khẳng định. Resource caching, transaction manager, provider và lifecycle container quyết định cách tài nguyên được giữ/tạo lại.

**Câu 8.** `factory.setMaxMessagesPerTask(5)` có tự động tạo 5 threads không?

**Đáp án:** Không. Concurrency do `concurrentConsumers`, `maxConcurrentConsumers` và executor quyết định.

**Câu 9.** Vì sao `maxMessagesPerTask=5` không phải “batch commit 5 message”?

**Đáp án:** Nó chỉ điều khiển vòng lặp nhận task; JMS ack/transaction boundaries được cấu hình riêng.

**Câu 10.** Muốn dùng pooled TaskExecutor, nên quan tâm thông số nào ngoài maxMessagesPerTask?

**Đáp án:** Pool size, queue capacity/rejection, `prefersShortLivedTasks`, receive timeout, concurrency/idle limits, session caching, transaction và measured throughput.

**Câu 11.** Khi queue yên ắng, core consumer có bị giảm xuống 0 bởi idleTaskExecutionLimit không?

**Đáp án:** Không. Container duy trì tối thiểu số core consumers đã cấu hình cho tới khi shutdown/stop; các surplus consumers có thể được scale-down.

**Câu 12.** Có thể áp dụng cách tune concurrency của queue cho topic không?

**Đáp án:** Không nên áp dụng máy móc. Topic/subscription có semantics khác và có nguy cơ nhận trùng khi tạo nhiều consumers/subscriptions.

**Câu 13.** Làm sao xác minh container dùng maxMessagesPerTask nào trong runtime?

**Đáp án:** Lấy container theo endpoint ID qua `JmsListenerEndpointRegistry`, kiểm tra `instanceof DefaultMessageListenerContainer` rồi gọi `getMaxMessagesPerTask()`.

**Câu 14.** Vì sao listener nhận đủ 6 messages trong demo dù maxMessagesPerTask=3?

**Đáp án:** Một tác vụ nhận hữu hạn có thể nhường chỗ/reschedule; container tiếp tục nhận message qua nhiều lượt task, không có giới hạn toàn cục bằng 3.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 Javadoc — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): cách hoạt động, `setMaxMessagesPerTask`, default -1/10, dynamic scaling, idle limits và caching cảnh báo.
- [Spring Framework 6.2 Javadoc — AbstractPollingMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html): `receiveTimeout` mặc định 1000 ms và transaction/receive loop.
- [Spring Framework 6.2 Javadoc — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): `setMaxMessagesPerTask(Integer)`, `setReceiveTimeout(Long)`, `setTaskExecutor(Executor)`, concurrency và factory API.
- [Spring Framework 6.2 Javadoc — SchedulingTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/SchedulingTaskExecutor.html): `prefersShortLivedTasks()` gợi ý executor scheduling.
- [Spring Framework Reference — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, factory mặc định và endpoint registration.
- [Spring Framework Reference — JMS Namespace Support](https://docs.spring.io/spring-framework/reference/integration/jms/namespace.html): các loại listener containers và cấu hình.
- [Spring Boot 3.5 Reference — JMS/ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): starter, connection và broker native.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS MessageConsumer.receive, queue/topic semantics, acknowledgment và transactions.
