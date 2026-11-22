# Thiết lập số consumer đồng thời và điều chỉnh tải

## 1. Bài toán và mục tiêu

Một JMS listener nhận message từ queue hoặc topic và gọi mã nghiệp vụ để xử lý. Khi chỉ có một consumer, ứng dụng xử lý tuần tự theo năng lực của consumer đó. Khi lượng message đến tăng, backlog có thể lớn dần và thời gian chờ tăng theo.

Spring JMS listener container quản lý việc nhận message, tạo Session và MessageConsumer, điều phối thread, giao message cho listener, xử lý acknowledgement, transaction và phục hồi kết nối. Ta có thể tăng số consumer để xử lý nhiều message đồng thời, hoặc cấu hình một khoảng concurrency để container tự tăng khi tải tăng và giảm khi tải hạ.

Bài học tập trung vào DefaultMessageListenerContainer (DMLC), container thường được dùng cho ứng dụng Spring JMS vì hỗ trợ concurrency động, transaction và khả năng phục hồi. Sau bài học, người đọc có thể:

- Phân biệt SimpleMessageListenerContainer và DefaultMessageListenerContainer.
- Cấu hình số consumer cố định hoặc một khoảng consumer tối thiểu/tối đa.
- Hiểu cách DMLC tăng và giảm consumer theo hoạt động nhận message.
- Điều chỉnh receive timeout, idle consumer, task executor và recovery.
- Ước lượng throughput và xác định giới hạn ở broker, CPU, database hoặc dịch vụ ngoài.
- Hiểu ảnh hưởng của concurrency đến thứ tự message, transaction và redelivery.
- Theo dõi số consumer đang chạy và chọn cấu hình dựa trên số liệu.
- Viết một ví dụ Java 17 chạy được với Spring JMS và ActiveMQ Classic.

## 2. Consumer đồng thời trong JMS

Một consumer là một MessageConsumer gắn với một JMS Session và một Destination. Khi Spring listener container tạo nhiều consumer cho cùng một queue, broker có thể giao các message khác nhau cho các consumer đó để xử lý song song.

~~~mermaid
flowchart TD
    P[Producer] --> Q[(JMS queue)]
    Q --> C1[Consumer 1]
    Q --> C2[Consumer 2]
    Q --> C3[Consumer 3]
    C1 --> L[Listener method]
    C2 --> L
    C3 --> L
    L --> DB[(Database or service)]
~~~

Với queue, các consumer cùng nhận việc từ một hàng đợi. Mỗi message được giao cho một consumer trong nhóm tại một lần giao nhận. Nếu listener của consumer 1 đang xử lý message A, consumer 2 có thể xử lý message B.

Một JMS Session không được chia sẻ để nhiều thread cùng thao tác đồng thời. Listener container tạo Session riêng cho từng consumer/invoker. Vì vậy, tăng concurrency thường kéo theo tăng số Session, MessageConsumer và thread xử lý.

Cần phân biệt concurrency với số instance ứng dụng. Nếu một ứng dụng chạy 3 replica và mỗi replica cấu hình 2 đến 6 consumer, tổng số consumer có thể dao động từ 6 đến 18. Khi tính tài nguyên, hãy dùng tổng trên toàn bộ replica.

## 3. Chọn listener container

Spring cung cấp hai container JMS chính: SimpleMessageListenerContainer (SMLC) và DefaultMessageListenerContainer (DMLC).

| Đặc điểm | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
|---|---|---|
| Cách nhận message | Đăng ký MessageListener trực tiếp với JMS provider | Poll bằng vòng lặp MessageConsumer.receive() |
| Concurrency | Số consumer cố định | Số consumer cố định hoặc tăng/giảm động |
| External transaction manager | Không hỗ trợ tham gia transaction được quản lý bên ngoài theo cách DMLC hỗ trợ | Có thể tham gia qua PlatformTransactionManager/JtaTransactionManager |
| Native JMS transaction | Có | Có |
| Phục hồi khi broker tạm mất kết nối | Phụ thuộc cơ chế provider và cấu hình recovery | Có cơ chế phục hồi và thử kết nối lại |
| Trường hợp phù hợp | Ứng dụng đơn giản, cần số consumer cố định và provider callback | Hầu hết ứng dụng Spring JMS cần transaction, recovery hoặc dynamic concurrency |

DMLC thường là lựa chọn mặc định cho hệ thống xử lý queue. SMLC có ít logic runtime hơn, nhưng không tự tăng/giảm consumer theo tải. Với SMLC, dùng setConcurrentConsumers() để đặt số consumer cố định.

Không tăng concurrency cho topic theo cách của queue nếu chưa cấu hình shared subscription hoặc cơ chế riêng của provider. Với topic subscription thông thường, mỗi consumer/subscription có thể nhận bản sao của cùng một publication; nhiều consumer có thể khiến một ứng dụng xử lý lặp cùng sự kiện.

## 4. Cấu hình số consumer cố định

DMLC có thuộc tính concurrentConsumers để xác định số consumer tối thiểu được duy trì. Mặc định là 1.

Cấu hình bằng Java:

~~~java
DefaultJmsListenerContainerFactory factory =
    new DefaultJmsListenerContainerFactory();

factory.setConnectionFactory(connectionFactory);
factory.setConcurrentConsumers(4);
~~~

Cấu hình này tạo bốn consumer cho listener container. Khi một consumer hoàn tất message, nó tiếp tục nhận message tiếp theo. Số consumer không tự tăng vượt quá bốn.

Có thể cấu hình số consumer ngay trên endpoint:

~~~java
@JmsListener(
    id = "ordersListener",
    destination = "orders.queue",
    concurrency = "4-4"
)
public void processOrder(String payload) {
    // Xử lý đơn hàng
}
~~~

Thuộc tính concurrency của annotation ghi đè giá trị concurrency được đặt trên factory cho endpoint đó. Dùng cấu hình riêng khi một queue cần nhiều tài nguyên hơn queue khác. Với `DefaultMessageListenerContainer`, giá trị đơn `4` là khoảng từ 1 đến tối đa 4 consumer; dùng `4-4` khi thực sự muốn cố định bốn consumer.

Tăng consumer thường hữu ích với queue có lượng message lớn và listener có thời gian xử lý đáng kể. Với queue ít message, một consumer thường đủ và giảm số Session/thread không cần thiết.

## 5. Cấu hình khoảng concurrency và scale động

DMLC hỗ trợ concurrency dạng khoảng lower-upper. Ví dụ 2-8 có nghĩa container giữ tối thiểu hai consumer và có thể tăng dần đến tối đa tám consumer khi có tải.

~~~java
factory.setConcurrency("2-8");
~~~

Có thể đặt bằng hai thuộc tính riêng:

~~~java
factory.setConcurrentConsumers(2);
factory.setMaxConcurrentConsumers(8);
~~~

Nếu chỉ truyền một số như 8, lower bound là 1 và upper bound là 8. Với queue quan trọng, đặt rõ cả hai đầu để biết chính xác mức tải nền và giới hạn scale.

DMLC khởi động số consumer cơ sở. Khi một consumer nhận được message và container thấy còn tải cùng số consumer đang rảnh chưa đủ, nó có thể lập lịch thêm invoker. Việc tăng diễn ra từ từ, không lập tức tạo toàn bộ consumer tối đa. Khi tải giảm, consumer dư được đánh dấu idle và dừng theo các ngưỡng idle đã cấu hình.

Không nên hiểu scale động là container đọc một con số queue depth rồi tính ra đúng số consumer cần thiết. DMLC quan sát việc nhận message và trạng thái idle của các invoker để quyết định tăng/giảm.

### 5.1. Điều khiển việc scale lên

Các thuộc tính liên quan:

- concurrentConsumers: số consumer cơ sở luôn được giữ.
- maxConcurrentConsumers: giới hạn trên của số consumer.
- idleConsumerLimit: số consumer idle được phép tồn tại trước khi container lập lịch thêm invoker. Giá trị mặc định là 1.
- setConcurrency("2-8"): cách viết gọn để đặt min/max.

Tăng maxConcurrentConsumers cho phép hệ thống xử lý burst lớn hơn, nhưng mỗi consumer bổ sung dùng thêm Session, thread và tài nguyên downstream. Đặt upper bound theo ngân sách tài nguyên thực tế.

### 5.2. Điều khiển việc scale xuống

DMLC dùng các ngưỡng idle để thu hẹp số consumer dư. Những thuộc tính quan trọng gồm:

- receiveTimeout: thời gian một lần receive chờ message trước khi trả về null.
- idleReceivesPerTaskLimit: số lần receive liên tiếp không có message trước khi task được xem là idle.
- idleTaskExecutionLimit: số lần thực thi task được xem là idle trước khi task dư kết thúc.
- maxMessagesPerTask: số lần nhận message tối đa trong một task; ảnh hưởng cách task được tái lập lịch.

Giá trị idleTaskExecutionLimit mặc định là 1. Nếu consumer tăng/giảm liên tục khi tải dao động quanh ngưỡng, có thể tăng giới hạn idle để giữ consumer dư lâu hơn. Tăng receiveTimeout hoặc số idle receive cũng làm consumer tồn tại lâu hơn, nhưng có thể kéo dài thời gian thu hẹp và làm tăng thời gian chờ khi kiểm tra idle.

Không nên đặt mọi ngưỡng thật cao để tránh scale down. Điều đó có thể giữ nhiều thread và Session rảnh trong thời gian dài. Hãy điều chỉnh theo chu kỳ burst và thời gian cần phản ứng khi tải giảm.

## 6. Cấu hình annotation-driven listener

@EnableJms bật hạ tầng @JmsListener. Spring tạo một listener container cho từng endpoint được khai báo trên bean.

Ví dụ:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        factory.setReceiveTimeout(1_000L);
        // Idle task limits belong to DefaultMessageListenerContainer, not this factory.

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(
        id = "ordersListener",
        destination = "orders.queue"
    )
    public void processOrder(String payload) {
        // Xử lý message
    }
}
~~~

Nếu không chỉ định containerFactory, hạ tầng annotation tìm bean tên jmsListenerContainerFactory. Trong ví dụ, factory mặc định là DMLC và áp dụng concurrency từ 2 đến 8.

Có thể đặt concurrency riêng trên annotation:

~~~java
@JmsListener(
    id = "billingListener",
    destination = "billing.queue",
    concurrency = "1-3"
)
public void processBilling(String payload) {
    // Công việc cần ít tài nguyên hơn
}
~~~

Đặt mức concurrency riêng theo đặc tính công việc. Một listener gửi email có thể cần concurrency cao hơn một listener xử lý giao dịch ghi nhiều bảng hoặc gọi API có quota thấp.

## 7. Ước lượng năng lực xử lý

Giả sử một message mất trung bình S giây để xử lý. Một consumer xử lý tuần tự có năng lực lý thuyết xấp xỉ:

\[
\text{throughput per consumer} \approx \frac{1}{S}
\]

Với C consumer đồng thời:

\[
\text{throughput ideal} \approx \frac{C}{S}
\]

Ví dụ, thời gian xử lý trung bình là 250 ms, tương đương 0,25 giây:

- Một consumer: khoảng 4 message/giây.
- Bốn consumer: khoảng 16 message/giây trong điều kiện lý tưởng.
- Tám consumer: khoảng 32 message/giây trong điều kiện lý tưởng.

Đây là giới hạn ước lượng, không phải cam kết throughput. Năng lực thực tế còn phụ thuộc vào broker, thời gian mạng, CPU, database, lock, connection pool, API bên ngoài và tỷ lệ lỗi/retry.

Gọi tốc độ message đến là λ và năng lực xử lý tổng là μ. Nếu λ lớn hơn μ trong thời gian dài, backlog sẽ tăng. Tăng consumer chỉ giúp khi bottleneck nằm ở số listener đang xử lý. Nếu database đã hết connection hoặc API ngoài đang giới hạn tốc độ, tăng consumer có thể làm lỗi nhiều hơn.

### 7.1. Ví dụ xác định điểm nghẽn

Một hệ thống có bốn consumer, mỗi message xử lý trung bình 200 ms. CPU còn dư nhưng database pool chỉ có bốn connection và mỗi listener giữ một connection trong suốt quá trình xử lý.

Nếu tăng lên 12 consumer, tối đa bốn listener có thể truy cập database cùng lúc; tám listener còn lại chờ connection. Độ trễ tăng, thread bị giữ lâu và backlog có thể không giảm đáng kể.

Hãy kiểm tra đồng thời:

- CPU và thời gian chạy listener.
- Số connection database đang dùng và thời gian chờ connection.
- Số request đang chờ ở dịch vụ ngoài.
- Số Session/consumer của JMS provider.
- Thời gian message nằm trong queue và thời gian xử lý thực tế.

## 8. Tác động đến thứ tự message

Một queue có thể giao message theo thứ tự nhận, nhưng nhiều consumer xử lý song song làm thứ tự hoàn tất thay đổi.

Ví dụ:

~~~text
Broker giao:    message-1 -> consumer A
                message-2 -> consumer B

Xử lý:          consumer A mất 2 giây
                consumer B mất 200 ms

Hoàn tất:       message-2 trước message-1
~~~

Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt, giữ một consumer hoặc phân vùng công việc theo khóa nghiệp vụ. Một lựa chọn khác là dùng tính năng message group/partition do provider hỗ trợ, để các message cùng khóa được xử lý theo một luồng có thứ tự.

Không tăng concurrency chỉ dựa trên throughput nếu các thao tác cập nhật cùng một tài khoản, đơn hàng hoặc trạng thái nghiệp vụ phụ thuộc thứ tự. Cần xác định rõ phạm vi thứ tự cần bảo vệ.

## 9. Queue và topic có semantics khác nhau

Với queue, nhiều consumer thường chia nhau các message. Đây là mô hình phù hợp cho work queue và competing consumers.

Với topic, publication được gửi đến các subscription. Trong cấu hình subscription thông thường, mỗi subscription nhận bản sao của publication. Tăng số consumer có thể làm một ứng dụng nhận cùng sự kiện nhiều lần nếu chúng tạo các subscription độc lập.

Nếu muốn nhiều worker chia nhau message từ một topic, phải cấu hình shared subscription theo JMS/provider và xác minh semantics của broker. Không giả định rằng tăng concurrency trên topic luôn có nghĩa chia tải giống queue.

Trong hầu hết trường hợp xử lý công việc nền, dùng queue với DMLC và concurrency động là cách dễ kiểm soát hơn.

## 10. Transaction và redelivery khi listener lỗi

DMLC mặc định dùng AUTO_ACKNOWLEDGE nếu không cấu hình transaction. Với DMLC, acknowledgement mặc định được thực hiện trước khi listener chạy; nếu listener ném exception, message có thể không được redeliver.

Nếu cần xử lý tin cậy, cấu hình local JMS transaction:

~~~java
factory.setSessionTransacted(true);
~~~

Hoặc cung cấp external transaction manager phù hợp, ví dụ JtaTransactionManager với ConnectionFactory hỗ trợ XA.

Khi Session transacted, listener xử lý thành công thì transaction commit; nếu listener ném exception, transaction rollback và broker có thể giao lại message theo semantics của provider. Hãy cấu hình redelivery limit, backoff và dead-letter policy ở broker/provider để message lỗi không lặp vô hạn.

Nếu listener cập nhật database và xử lý JMS trong cùng một local JMS transaction, transaction database không tự động tham gia. Cần transaction manager phối hợp, XA nếu thực sự cần, hoặc thiết kế idempotency/outbox/inbox để xử lý khả năng redelivery và trạng thái không đồng bộ.

## 11. TaskExecutor và thread

DMLC thực thi listener bằng các task thông qua Spring TaskExecutor. Mặc định, container dùng SimpleAsyncTaskExecutor và tạo thread theo số consumer được cấu hình.

Một listener consumer thường chiếm thread trong phần lớn vòng đời vì nó liên tục chờ nhận message. Do đó, một thread pool thông thường không nhất thiết làm giảm số thread cần thiết; pool phải có đủ thread để chạy các consumer sống lâu.

Chỉ truyền TaskExecutor bên ngoài khi có lý do rõ ràng, chẳng hạn cần tích hợp thread được quản lý bởi application server hoặc dùng SchedulingTaskExecutor với task ngắn hạn. Cần bảo đảm executor không thiếu thread khiến consumer không thể chạy.

Với Java 21 trở lên, Spring Framework 6.2 hỗ trợ bật virtual threads cho default executor của DMLC bằng setVirtualThreads(true). Tính năng này không áp dụng cho Java 17 và không tự làm tăng năng lực database hoặc broker. Dù dùng platform thread hay virtual thread, vẫn phải giới hạn concurrency và tài nguyên downstream.

## 12. Prefetch và phân phối message của provider

JMS specification không định nghĩa một thuộc tính prefetch chung cho mọi provider. Broker/provider có thể gửi trước một số message đến consumer trước khi listener xử lý xong message hiện tại.

Prefetch cao có thể giảm round trip và tăng throughput với message ngắn. Tuy nhiên, consumer nhanh có thể giữ nhiều message đã được broker phân phối trong khi consumer khác ít việc. Điều này có thể làm phân phối mất cân bằng và tăng số message đang nằm trong bộ đệm phía client.

Prefetch thấp thường giúp phân phối công việc đều hơn và giới hạn lượng message đang được giao cho từng consumer, nhưng có thể tăng chi phí trao đổi với broker.

Khi điều chỉnh prefetch:

- Dùng thuộc tính riêng của JMS provider, không giả định một cấu hình áp dụng cho mọi broker.
- Đo số message đang được dispatch nhưng chưa xử lý xong.
- Kiểm tra redelivery và phân phối lại khi consumer dừng.
- Kết hợp với thời gian xử lý và concurrency của listener.
- Thử tải với message ngắn, dài và thời gian xử lý không đồng đều.

Đừng chỉ tăng prefetch và concurrency cùng lúc. Thay đổi từng yếu tố sẽ giúp xác định nguyên nhân khi latency hoặc throughput thay đổi.

## 13. Cache Session và tài nguyên listener

DMLC tự quản lý vòng đời Connection, Session và MessageConsumer theo cache level. Với local JMS resources, mặc định container dùng CACHE_CONSUMER, tức giữ Connection, Session và Consumer theo listener thread.

Khi có external transaction manager, mặc định DMLC dùng CACHE_NONE để lấy tài nguyên mới trong phạm vi transaction, vì một số Jakarta EE server chỉ enlist Connection/Session mới lấy vào XA transaction. Chỉ đổi cache level sau khi xác minh yêu cầu của provider và transaction manager.

Không tự động bọc CachingConnectionFactory bên ngoài DMLC. Spring khuyến nghị để listener container tự quản lý cache trong lifecycle của nó. CachingConnectionFactory bên ngoài có thể gây vấn đề khi stop/start container, scale consumer hoặc dùng provider-specific task hints.

Nếu cần cache riêng, hãy kiểm thử các trường hợp stop/start, broker reconnect, transaction rollback, dynamic scaling và durable subscription.

## 14. Theo dõi consumer và backlog

DMLC cung cấp các thông tin hữu ích:

- getConcurrentConsumers(): số consumer cơ sở được cấu hình.
- getMaxConcurrentConsumers(): giới hạn consumer tối đa.
- getScheduledConsumerCount(): số consumer đã được lập lịch.
- getActiveConsumerCount(): số consumer hiện đang hoạt động.
- isRunning(): trạng thái listener container.

Scheduled count có thể cao hơn active count khi một số consumer đã được lập lịch nhưng đang chờ hoặc chưa thực thi. Đừng coi hai số này là tương đương.

Có thể lấy container từ JmsListenerEndpointRegistry:

~~~java
DefaultMessageListenerContainer container =
    (DefaultMessageListenerContainer)
        registry.getListenerContainer("ordersListener");

int active = container.getActiveConsumerCount();
int scheduled = container.getScheduledConsumerCount();

System.out.println("activeConsumers=" + active);
System.out.println("scheduledConsumers=" + scheduled);
~~~

Ngoài consumer count, cần theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Queue depth | Số message đang chờ |
| Oldest message age | Tuổi message cũ nhất trong queue |
| Enqueue/dequeue rate | Tốc độ message đến và rời queue |
| Processing latency | Thời gian listener xử lý một message |
| Active/scheduled consumers | Số consumer thực sự đang hoạt động và đã lập lịch |
| Redelivery count | Số lần message được giao lại |
| Failure/dead-letter count | Tỷ lệ lỗi và message bị chuyển sang DLQ |
| DB/API wait time | Thời gian chờ tài nguyên phụ trợ |

Nếu queue depth tăng nhưng consumer đã đạt max concurrency, hãy kiểm tra thời gian xử lý và bottleneck downstream trước khi tăng giới hạn. Nếu active consumer thấp hơn scheduled consumer trong thời gian dài, kiểm tra thread executor, trạng thái broker và lỗi khởi tạo consumer.

## 15. Phục hồi khi broker gián đoạn

DMLC có cơ chế phục hồi khi broker tạm thời không sẵn sàng. Recovery interval mặc định là 5 giây. Có thể dùng setRecoveryInterval() hoặc setBackOff() để điều chỉnh khoảng thời gian giữa các lần thử kết nối.

~~~java
factory.setBackOff(new FixedBackOff(5_000L, FixedBackOff.UNLIMITED_ATTEMPTS));
~~~

Với factory, cấu hình `setBackOff(...)`; `setRecoveryInterval(...)` là setter trên `DefaultMessageListenerContainer`, không phải `DefaultJmsListenerContainerFactory`. Tương tự, `setIdleTaskExecutionLimit(...)` là cấu hình của DMLC. Khi cần điều khiển trực tiếp hai giá trị này, tạo container thủ công:

~~~java
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container = new DefaultMessageListenerContainer();
container.setIdleTaskExecutionLimit(2);
container.setRecoveryInterval(5_000L);
~~~

Nếu broker có thời gian bảo trì hoặc khởi động lại dài, backoff tăng dần có thể giảm số lần thử kết nối liên tục. Khi broker trở lại, container tạo lại tài nguyên JMS cần thiết và tiếp tục nhận message.

Recovery không thay thế transaction và idempotency. Nếu kết nối bị mất đúng lúc message đang được xử lý hoặc commit, ứng dụng cần chấp nhận kết quả không chắc chắn và xử lý redelivery an toàn.

## 16. Ví dụ chạy được với Java 17, Spring JMS và ActiveMQ Classic

Ví dụ dùng Spring Framework 6.2.19, Java 17 và Apache ActiveMQ Classic 6.1.5. ActiveMQ VM transport tạo broker nhúng trong JVM, phù hợp để thực hành local. Chương trình gửi 24 message đến một queue; DMLC khởi động với hai consumer và có thể tăng đến sáu consumer khi có tải.

### 16.1. Cấu trúc dự án

~~~text
jms-concurrency-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/
                ├── JmsConfig.java
                ├── WorkListener.java
                └── ConcurrencyJmsDemo.java
~~~

### 16.2. Maven dependencies

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jms-concurrency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-all</artifactId>
            <version>6.1.5</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

ActiveMQ Classic 6.x sử dụng namespace jakarta.jms, tương thích với Spring Framework 6.2. Dependency activemq-all gom các thành phần cần thiết cho ví dụ nhúng broker.

### 16.3. Cấu hình JMS listener container

Tạo src/main/java/com/example/JmsConfig.java:

~~~java
package com.example;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean
    ConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
            "vm://concurrency-demo?broker.persistent=false&broker.useJmx=false"
        );
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        factory.setReceiveTimeout(1_000L);
        factory.setBackOff(new FixedBackOff(5_000L, FixedBackOff.UNLIMITED_ATTEMPTS));

        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    WorkListener workListener() {
        return new WorkListener(24);
    }
}
~~~

Bean jmsListenerContainerFactory được hạ tầng @EnableJms sử dụng làm factory mặc định. Cấu hình 2-6 giữ ít nhất hai consumer và cho phép scale lên tối đa sáu. Session transaction được bật để listener exception có thể rollback JMS transaction và kích hoạt redelivery theo policy của provider.

### 16.4. Listener xử lý message

Tạo src/main/java/com/example/WorkListener.java:

~~~java
package com.example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;

public class WorkListener {

    private final CountDownLatch completedLatch;
    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger peakInFlight = new AtomicInteger();
    private final AtomicInteger completed = new AtomicInteger();

    public WorkListener(int expectedMessages) {
        this.completedLatch = new CountDownLatch(expectedMessages);
    }

    @JmsListener(
        id = "workListener",
        destination = "work.queue"
    )
    public void process(String payload) {
        int current = inFlight.incrementAndGet();
        peakInFlight.accumulateAndGet(current, Math::max);

        boolean success = false;
        try {
            Thread.sleep(150);
            completed.incrementAndGet();
            success = true;
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Listener interrupted", ex);
        }
        finally {
            inFlight.decrementAndGet();
            if (success) {
                completedLatch.countDown();
            }
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return completedLatch.await(timeout, unit);
    }

    public int getCompleted() {
        return completed.get();
    }

    public int getPeakInFlight() {
        return peakInFlight.get();
    }
}
~~~

Listener bean được dùng chung giữa các consumer thread, vì vậy các bộ đếm dùng AtomicInteger và CountDownLatch. Mỗi lần gọi xử lý một message trong 150 ms để mô phỏng công việc có thời gian thực thi.

### 16.5. Chương trình gửi message

Tạo src/main/java/com/example/ConcurrencyJmsDemo.java:

~~~java
package com.example;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jms.core.JmsTemplate;

public class ConcurrencyJmsDemo {

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(JmsConfig.class)) {

            JmsTemplate jmsTemplate =
                context.getBean(JmsTemplate.class);

            WorkListener listener =
                context.getBean(WorkListener.class);

            for (int i = 1; i <= 24; i++) {
                jmsTemplate.convertAndSend(
                    "work.queue",
                    "job-" + i
                );
            }

            if (!listener.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timed out waiting for all messages"
                );
            }

            System.out.println(
                "completed=" + listener.getCompleted()
            );
            System.out.println(
                "peakInFlight=" + listener.getPeakInFlight()
            );
        }
    }
}
~~~

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.ConcurrencyJmsDemo
~~~

Kết quả:

~~~text
completed=24
peakInFlight=N
~~~

completed luôn bằng 24 nếu mọi message được xử lý thành công. N là số listener invocation đồng thời lớn nhất quan sát được trong lần chạy đó; giá trị phụ thuộc lịch thread và môi trường, không nhất thiết bằng sáu. Cấu hình 2-6 là giới hạn của container, không phải yêu cầu luôn phải có sáu consumer.

Ví dụ dùng broker nhúng không lưu message bền vững và chỉ dành cho học tập. Khi kết nối broker thật, hãy thay ConnectionFactory, cấu hình credential/TLS và queue theo môi trường.

## 17. Điều chỉnh tải theo từng loại công việc

Không nên dùng một concurrency chung cho mọi listener. Hãy phân loại theo đặc tính xử lý:

| Loại công việc | Đặc điểm | Hướng cấu hình |
|---|---|---|
| Gửi email hoặc gọi HTTP | Chủ yếu chờ I/O | Có thể tăng concurrency đến giới hạn quota và connection |
| Resize ảnh hoặc nén tệp | Tốn CPU và bộ nhớ | Giới hạn concurrency theo CPU/RAM |
| Ghi dữ liệu database | Phụ thuộc connection pool và lock | Cân đối consumer với DB pool và contention |
| Xử lý hóa đơn theo tài khoản | Có yêu cầu thứ tự theo khóa | Phân vùng theo accountId hoặc giữ xử lý tuần tự theo khóa |
| Queue ít message, không có SLA ngắn | Tải thấp | Giữ một consumer hoặc concurrency thấp |
| Burst theo đợt | Tải biến động | Dùng DMLC min/max và ngưỡng idle phù hợp |

Nếu listener thực hiện một thao tác rất ngắn, chi phí tạo Session, transaction và chuyển message có thể chiếm tỷ lệ lớn. Khi đó batching hoặc gom công việc có thể hiệu quả hơn việc tăng vô hạn số consumer.

Nếu listener gọi dịch vụ ngoài có quota, đặt max concurrency theo quota đó. Ví dụ dịch vụ cho phép 20 request đồng thời thì không nên tạo 100 consumer cùng gọi dịch vụ mà không có rate limiter hoặc bulkhead.

## 18. Các lỗi thường gặp

- **Tăng concurrentConsumers mà không kiểm tra database**: listener có thể chờ connection và làm backlog tăng nhanh hơn.
- **Nhầm concurrency là số thread của toàn bộ ứng dụng**: mỗi endpoint có container riêng; mỗi replica lại có số consumer riêng.
- **Đặt maxConcurrentConsumers quá cao**: có thể làm broker, CPU hoặc dịch vụ ngoài quá tải.
- **Dùng dynamic scaling cho topic subscription thông thường**: ứng dụng có thể nhận nhiều bản sao của cùng publication.
- **Cho rằng thứ tự hoàn tất được giữ nguyên**: nhiều consumer xử lý song song có thể hoàn tất message sau trước message trước.
- **Dùng SimpleMessageListenerContainer khi cần scale động**: SMLC giữ số consumer cố định.
- **Dùng AUTO_ACKNOWLEDGE khi cần redelivery đáng tin cậy**: DMLC ack trước listener invocation; listener exception có thể làm message không được giao lại.
- **Dùng TaskExecutor quá nhỏ**: không đủ thread để chạy các listener consumer.
- **Tăng receiveTimeout quá lớn**: thời gian nhận biết consumer idle và scale xuống có thể kéo dài.
- **Giảm receiveTimeout quá thấp**: tăng số lần polling khi queue rỗng và có thể làm tăng overhead.
- **Bỏ qua prefetch của provider**: một consumer có thể giữ nhiều message đang chờ xử lý, làm phân phối mất cân bằng.
- **Không quan sát active và scheduled consumer count**: khó biết container đã scale đến đâu hoặc thread nào chưa chạy.
- **Không kiểm thử broker restart và listener shutdown**: lỗi thường chỉ xuất hiện khi tài nguyên JMS bị tái tạo.

## 19. Checklist tuning trước production

- [ ] Chọn DMLC nếu cần dynamic concurrency, transaction hoặc recovery.
- [ ] Đặt concurrentConsumers theo tải nền và maxConcurrentConsumers theo giới hạn tài nguyên.
- [ ] Tính tổng consumer trên tất cả application replica.
- [ ] Xác định yêu cầu thứ tự và chọn queue/topic/shared subscription phù hợp.
- [ ] Bật sessionTransacted hoặc external transaction manager nếu cần redelivery khi listener lỗi.
- [ ] Cấu hình retry, redelivery limit và dead-letter policy ở broker/provider.
- [ ] Đo thời gian xử lý trung bình và p95/p99.
- [ ] Đo queue depth, tuổi message cũ nhất, enqueue/dequeue rate và active consumers.
- [ ] Kiểm tra CPU, database pool, HTTP quota và lock contention.
- [ ] Chọn receiveTimeout và idle thresholds theo chu kỳ tải.
- [ ] Kiểm tra prefetch theo provider và kiểu workload.
- [ ] Đảm bảo TaskExecutor có đủ thread cho consumer được cấu hình.
- [ ] Kiểm thử scale lên, scale xuống, broker restart, transaction rollback và shutdown.
- [ ] Giữ concurrency tối đa trong ngân sách tài nguyên đã đo được.

## 20. Tổng kết

Spring JMS listener container quản lý consumer, Session, thread, transaction và việc phục hồi khi broker gián đoạn. Với DMLC, concurrentConsumers đặt mức nền và maxConcurrentConsumers đặt giới hạn scale. Cấu hình dạng 2-8 giữ hai consumer khi tải thấp và có thể tăng dần lên tám khi queue có nhiều message.

Hiệu quả của concurrency phụ thuộc vào toàn bộ đường xử lý. Tăng consumer chỉ có lợi khi broker, CPU, database, thread executor và dịch vụ phụ trợ còn khả năng đáp ứng. Khi có nhiều consumer, thứ tự hoàn tất message có thể thay đổi; topic subscription có semantics khác queue; và transaction phải được cấu hình rõ nếu cần redelivery khi listener thất bại.

Hãy bắt đầu từ số liệu tải thật, điều chỉnh một yếu tố mỗi lần và theo dõi cả backlog lẫn tài nguyên downstream. Cách này giúp chọn concurrency ổn định, tránh scale quá mức và giữ hành vi xử lý đúng với yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2.19 — DefaultMessageListenerContainer Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2.x — SimpleMessageListenerContainer Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html
- Jakarta Messaging Specification: https://jakarta.ee/specifications/messaging/3.1/