# SimpleMessageListenerContainer và luồng xử lý riêng cho consumer

Khi một phương thức `@RabbitListener` nhận message từ RabbitMQ, ai thực sự gọi phương thức đó: **luồng I/O của RabbitMQ Java client**, hay **luồng của ứng dụng Spring**? Với **`SimpleMessageListenerContainer` (SMLC)**, câu trả lời quan trọng là: Spring AMQP đưa các lần giao message từ client qua một hàng đợi nội bộ, rồi sử dụng **task chạy trên `TaskExecutor`** để gọi listener. Mỗi consumer của SMLC có một tác vụ xử lý lâu dài; các tác vụ có thể chạy song song trên những luồng do executor cung cấp.

Thiết kế này giúp tách công việc ứng dụng khỏi luồng giao nhận của RabbitMQ client, nhưng cũng tạo các giới hạn cần hiểu: **số consumer**, **số luồng executor**, **prefetch**, **ACK/NACK**, bộ đệm message, shutdown và khả năng xử lý lỗi. Tăng concurrency sai cách có thể khiến broker đã giao nhiều message nhưng ứng dụng chưa xử lý kịp, hoặc khiến container không thể khởi động thêm consumer do executor cạn luồng.

Bài thuộc chương **Listener container** của module **SPRING_AMQP**. Chúng ta sẽ sử dụng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding để thực hành, sau đó liên hệ đến xác nhận giao nhận, retry, dead-letter, transaction và quan sát hệ thống nhằm xây dựng xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò của `SimpleMessageListenerContainer` và đường đi của một message từ RabbitMQ client tới `@RabbitListener`.
2. Phân biệt **luồng nhận delivery của RabbitMQ client** với **luồng xử lý listener do `TaskExecutor` cấp**.
3. Giải thích mối quan hệ giữa `concurrentConsumers`, `maxConcurrentConsumers`, executor threads và `prefetchCount`.
4. So sánh SMLC với `DirectMessageListenerContainer` (DMLC) ở cấp mô hình luồng và cấu hình concurrency.
5. Cấu hình SMLC trong Spring Boot bằng `spring.rabbitmq.listener.simple.*` và một `SimpleRabbitListenerContainerFactory` riêng.
6. Dùng log, RabbitMQ Management và `RabbitListenerEndpointRegistry` để xác định consumer đang chạy trên luồng nào.
7. Lựa chọn ACK, requeue, DLQ, retry và shutdown an toàn hơn cho listener xử lý nghiệp vụ.

## 2. Listener container là gì?

`@RabbitListener` là **khai báo endpoint**; một listener container mới là thành phần tạo consumer thật trên broker, nhận message và điều phối việc gọi handler. Trong Spring AMQP, hai loại container thường gặp là:

- **`SimpleMessageListenerContainer`**: tiếp nhận delivery từ RabbitMQ client vào hàng đợi nội bộ, rồi **consumer task** trong executor lấy message và gọi listener.
- **`DirectMessageListenerContainer`**: listener được gọi trực tiếp hơn trên luồng dispatch của RabbitMQ client; có mô hình concurrency và vận hành khác.

Tên “simple” **không có nghĩa container chỉ dùng một luồng**. SMLC có thể chạy nhiều consumer đồng thời, tự điều chỉnh số consumer trong khoảng cấu hình, hỗ trợ acknowledgment, error handling, converter và nhiều tính năng của Spring AMQP.

### Các thành phần tham gia

| Thành phần | Trách nhiệm | Điều cần nhớ |
|---|---|---|
| `RabbitTemplate` | Producer gửi publication tới exchange | Không phải consumer; gửi xong chưa đồng nghĩa listener đã xử lý |
| Exchange / binding / queue | RabbitMQ định tuyến và lưu message chờ tiêu thụ | SMLC không sửa routing key của message đã publish |
| RabbitMQ Java client | Quản lý AMQP connection/channel và callback khi broker giao message | Luồng client không nên bị công việc nghiệp vụ chậm chiếm giữ |
| `SimpleMessageListenerContainer` | Tạo/giám sát consumer, giao việc cho handler, xử lý ACK/reject và recovery | Là container thực hiện công việc |
| `TaskExecutor` | Cung cấp luồng thực thi **consumer task** | Phải có đủ năng lực cho số consumer được cấu hình |
| `MessageListener` / `@RabbitListener` | Chuyển body và gọi mã nghiệp vụ | Có thể chạy đồng thời trên nhiều consumer |
| `RabbitListenerEndpointRegistry` | Quản lý container được tạo từ annotation và lifecycle của chúng | Tra cứu theo `id` của `@RabbitListener` |

## 3. Vì sao SMLC có luồng xử lý riêng?

### 3.1. Luồng dữ liệu và luồng thực thi

RabbitMQ Java client nhận dữ liệu AMQP từ broker rồi gọi callback delivery. Với SMLC, callback đó **không trực tiếp chạy toàn bộ business handler**. Delivery được chuyển qua một **hàng đợi nội bộ** đến tác vụ consumer của Spring, đang chạy trên `TaskExecutor`. Tác vụ này lấy message, thực hiện chuyển đổi dữ liệu, gọi listener, rồi xử lý ACK/reject phù hợp với chế độ đã chọn.

~~~mermaid
flowchart LR
    subgraph B["RabbitMQ broker"]
        Q["Queue<br/>demo.container.orders"]
    end
    subgraph J["RabbitMQ Java client"]
        C["Client connection/channel<br/>delivery callback"]
    end
    subgraph S["SimpleMessageListenerContainer"]
        I["Hàng đợi nội bộ<br/>cho delivery"]
        E["TaskExecutor"]
        T1["Consumer task 1<br/>luồng ứng dụng"]
        T2["Consumer task 2<br/>luồng ứng dụng"]
        L["@RabbitListener<br/>mã nghiệp vụ"]
        E --> T1
        E --> T2
        T1 --> L
        T2 --> L
    end
    Q -->|"basic.deliver"| C
    C --> I
    I --> T1
    I --> T2
~~~

Sơ đồ trên mang tính khái niệm: **mỗi consumer có đường nhận delivery riêng, kênh AMQP riêng và tác vụ xử lý tương ứng**; không nên hiểu mọi consumer dùng chung đúng một hàng đợi nội bộ duy nhất. SMLC duy trì cơ chế đệm và chuyển giao từ callback client tới consumer task của từng consumer.

### 3.2. Một consumer có một tác vụ xử lý lâu dài

Thông thường SMLC tạo **một consumer task cho mỗi consumer được khởi chạy**. Tác vụ chạy liên tục, nhận lần giao kế tiếp, gọi listener và xử lý acknowledgment. `TaskExecutor` cung cấp thread để thực thi tác vụ đó.

Ví dụ:

~~~text
SMLC: concurrentConsumers=2, maxConcurrentConsumers=4

Ban đầu:
  Consumer A -> Task A -> thread "smlc-orders-1" -> listener
  Consumer B -> Task B -> thread "smlc-orders-2" -> listener

Khi SMLC tăng lên 4 consumer:
  Consumer C -> Task C -> thread "smlc-orders-3" -> listener
  Consumer D -> Task D -> thread "smlc-orders-4" -> listener
~~~

Đó là hình dung **một tác vụ lâu dài cho mỗi consumer đang chạy**, không phải cam kết tên luồng hoặc mapping được giữ mãi qua reconnect/restart. Khi một consumer lỗi và được tạo lại, thread hoặc consumer tag có thể thay đổi. Nếu executor dùng chung cho nhiều container, tất cả các consumer task có thể cạnh tranh năng lực luồng của cùng executor.

**Không được hiểu “một thread cho một consumer” là “một thread mới cho mỗi message”.** Một consumer task thường xử lý **nhiều message liên tiếp**; số thread cần cấp phụ thuộc số consumer đồng thời, không trực tiếp bằng số message trong queue.

### 3.3. Tách luồng đem lại gì và phải trả giá gì?

**Lợi ích:**

- Luồng dispatch của RabbitMQ client không phải trực tiếp chạy mọi thao tác database, HTTP hoặc xử lý nghiệp vụ chậm.
- Ứng dụng kiểm soát tài nguyên listener thông qua `TaskExecutor` riêng.
- Một nhóm consumer có thể tăng/giảm song song theo chiến lược SMLC mà không tạo luồng mới cho từng message.
- Có thể đặt tên executor thread để theo dõi log và phân biệt các nhóm xử lý.

**Đánh đổi:**

- Có bước chuyển giao qua hàng đợi nội bộ, cần bộ nhớ và hoạt động điều phối.
- Có thể có delivery đang nằm ở vùng đệm hoặc đang được xử lý nhưng **chưa ACK**.
- Executor thiếu luồng có thể gây nghẽn khởi động/mở rộng consumer.
- Khi xử lý bất đồng bộ bên ngoài listener, thời điểm phương thức trả về và ACK phải được thiết kế rõ; **không được mặc nhiên cho rằng `AUTO` sẽ đợi một công việc nền do bạn tự tạo**.

## 4. Phân biệt SMLC với DirectMessageListenerContainer

`DirectMessageListenerContainer` (DMLC) là một lựa chọn khác. Khác biệt kiến trúc chính nằm ở **đường từ client callback đến listener**.

| Khía cạnh | `SimpleMessageListenerContainer` | `DirectMessageListenerContainer` |
|---|---|---|
| Luồng gọi listener | Tác vụ consumer trên `TaskExecutor` của Spring | Listener được gọi trên luồng dispatch của RabbitMQ Java client |
| Chuyển giao message | Qua hàng đợi nội bộ trước khi handler chạy | Không có bước chuyển giao kiểu SMLC cho handler |
| Đơn vị concurrency điển hình | `concurrentConsumers` và `maxConcurrentConsumers` | `consumersPerQueue` (số consumer cho mỗi queue) |
| Tăng/giảm consumer tự động theo tải | Có cơ chế điều chỉnh trong phạm vi cấu hình | Không sử dụng cùng thuật toán tăng/giảm `concurrentConsumers` của SMLC |
| Executor thread | Cần đủ thread cho các consumer task đang chạy | Cần hiểu và cấu hình năng lực thread của RabbitMQ client |
| Khi nào cân nhắc | Cần cách biệt client dispatch và mã nghiệp vụ; muốn scaling consumer động theo SMLC | Muốn mô hình gọi trực tiếp, giảm bước chuyển giao; đã đo lường và hiểu concurrency của client |

**DMLC không đương nhiên nhanh hơn trong mọi ứng dụng** và SMLC cũng không mặc định tốt hơn. Nếu xử lý nghiệp vụ chủ yếu chờ database hoặc HTTP, cần xét cả số kết nối DB, độ trễ, `prefetch`, chiến lược backpressure và giới hạn broker. Không quyết định dựa trên tên loại container hoặc một benchmark không phản ánh tải thực.

Trong Spring Boot, thuộc tính `spring.rabbitmq.listener.type=simple` hoặc `direct` xác định loại container factory mặc định. Hai loại có **nhóm thuộc tính khác nhau**; ví dụ `spring.rabbitmq.listener.simple.concurrency` không phải cách cấu hình `consumersPerQueue` của direct container.

## 5. Ba giới hạn quyết định throughput: consumer, thread, prefetch

### 5.1. Số consumer đang chạy

SMLC hỗ trợ:

- `concurrentConsumers`: số consumer cơ sở cần chạy.
- `maxConcurrentConsumers`: giới hạn mở rộng tối đa khi bật cơ chế tăng concurrency.

Trong Java:

~~~java
factory.setConcurrentConsumers(2);
factory.setMaxConcurrentConsumers(4);
~~~

Nếu số consumer có thể tăng động, SMLC dựa trên **mức độ hoạt động của consumer theo các chu kỳ nhận message**, có điều kiện về số lần liên tiếp và khoảng thời gian tối thiểu giữa những lần thay đổi. Đây **không phải autoscaling tức thì theo độ dài queue**. Khi listener chỉ chạy vài giây hoặc traffic tăng/giảm đột ngột, số consumer thực tế có thể vẫn ở mức cơ sở.

Các tham số chuyên sâu trên container như chu kỳ active/idle, `startConsumerMinInterval`, `stopConsumerMinInterval` và `receiveTimeout` ảnh hưởng quá trình này. Chỉ tinh chỉnh chúng sau khi quan sát tải và hiểu lifecycle; đừng rút ngắn mọi khoảng thời gian chỉ để thấy consumer tăng nhanh trong demo.

### 5.2. Năng lực của TaskExecutor

Nếu SMLC có thể chạy **4 consumer** nhưng executor chỉ có **2 thread có thể duy trì cho các task**, container có thể không chạy đủ consumer như dự định; việc mượn thread bị chậm hoặc từ chối gây triệu chứng khó hiểu.

Một nguyên tắc thực hành: **đảm bảo executor có đủ capacity cho số consumer tối đa trên các container dùng chung**, và chừa khoảng cho tác vụ phụ nếu executor còn dùng mục đích khác. Nếu chỉ định executor riêng cho một listener factory, hãy tính tổng concurrency của **mọi container dùng factory đó**, không chỉ một listener.

`ThreadPoolTaskExecutor` có `corePoolSize`, `maxPoolSize` và `queueCapacity`. Đặc biệt, một executor có **queue task lớn** có thể làm các consumer task chờ trong queue thay vì được tạo thread ngay, khiến cấu hình `maxConcurrentConsumers` không phản ánh concurrency thực tế. Với consumer task **chạy lâu dài**, không nên dùng cấu hình executor dành cho các tác vụ rất ngắn mà không đánh giá.

### 5.3. Prefetch và số message chưa ACK

`prefetchCount` giới hạn số lượng delivery broker có thể giao cho consumer trước khi nhận ACK, theo QoS áp dụng. Ví dụ:

~~~text
4 consumer hoạt động × prefetch=5
  → có thể có tới khoảng 20 message đang được giao/chưa ACK
    ở nhóm consumer đó (nếu không có giới hạn khác).
~~~

Đây là **giới hạn in-flight khả dĩ**, không có nghĩa chính xác 20 message đang xử lý CPU đồng thời. Các delivery chưa ACK có thể đang được đệm hoặc chờ tác vụ consumer xử lý. `prefetch=5` **không tạo thêm 5 thread cho mỗi consumer**.

| Điều chỉnh | Tác động phổ biến | Rủi ro khi quá cao |
|---|---|---|
| Tăng `concurrentConsumers` | Thêm consumer task/luồng và AMQP channel | Cạnh tranh CPU, DB connections, lock, channel |
| Tăng `maxConcurrentConsumers` | Cho SMLC mở rộng số consumer khi đủ điều kiện | Executor hết luồng; tăng tải nền đột ngột |
| Tăng `prefetchCount` | Mỗi consumer có thể nhận trước nhiều delivery | Nhiều Unacked, phân phối thiếu công bằng, bộ nhớ tăng |
| Tăng executor threads | Cung cấp năng lực chạy nhiều consumer task | Quá nhiều thread, context switch, bộ nhớ |

**Không dùng công thức `concurrency × prefetch` làm số đơn hàng đang commit trong database.** Một listener thường xử lý từng callback tuần tự trên consumer task của nó; doanh số/transaction concurrency thực tế còn tùy mã nghiệp vụ.

## 6. Spring Boot: cấu hình SMLC đơn giản

### 6.1. Chuẩn bị RabbitMQ

Trong môi trường local có thể khởi chạy broker kèm giao diện quản trị:

~~~bash
docker run -d --name rabbitmq-smlc-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

RabbitMQ Management thường ở `http://localhost:15672`. Tài khoản `lab/lab123456` chỉ dùng thử trên máy cá nhân; không hard-code credentials thật vào source production, không công khai cổng quản trị, và dùng TLS/quyền vhost tối thiểu khi triển khai.

### 6.2. Dependency

Trong dự án Spring Boot có parent hoặc BOM phù hợp, thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ dưới dùng Java 17+ và API thông dụng của Spring Boot 3.x / Spring AMQP 3.x. Không ghi cố định phiên bản starter vào một dự án đã được dependency management kiểm soát; chọn các phiên bản tương thích với nhau.

### 6.3. `application.yml` cho listener simple

~~~yaml
server:
  port: 8080

spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      type: simple
      simple:
        concurrency: 2
        max-concurrency: 4
        prefetch: 5
        acknowledge-mode: auto
        default-requeue-rejected: false
~~~

Ý nghĩa chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `listener.type: simple` | Chọn `SimpleRabbitListenerContainerFactory` cho listener mặc định |
| `listener.simple.concurrency: 2` | Khởi tạo số consumer cơ sở cho container |
| `listener.simple.max-concurrency: 4` | Cho phép mở rộng đến tối đa 4 consumer khi đủ điều kiện |
| `listener.simple.prefetch: 5` | Giới hạn delivery chưa ACK theo QoS tương ứng, không phải số thread |
| `listener.simple.acknowledge-mode: auto` | Spring container ACK khi handler thành công |
| `listener.simple.default-requeue-rejected: false` | Với lỗi xử lý dẫn đến reject theo cách thông thường, không requeue mặc định |

**Cảnh báo:** `default-requeue-rejected: false` trong lab giúp tránh vòng lặp lỗi dữ liệu, nhưng với lỗi database/network tạm thời, cần retry/backoff có giới hạn hoặc một chiến lược chuyển DLQ phù hợp trước khi dùng cấu hình này ở production.

Nếu không khai báo factory tùy chỉnh, Spring Boot thường tự tạo `rabbitListenerContainerFactory` cho `@RabbitListener` cùng các thuộc tính `listener.simple.*`. Phần tiếp theo xây **factory riêng** để người học quan sát executor thread. Trong một ứng dụng có nhiều listener, không nên mặc định toàn bộ listener sẽ dùng factory riêng này: phải chỉ định `containerFactory` đúng bean.

## 7. Topology lab: exchange, queue, binding và DLQ

Ta dùng direct exchange `demo.container.events`, routing key `order.created` và queue `demo.container.orders`. Với message bị reject không requeue, queue được cấu hình dead-letter sang `demo.container.dlx` rồi đến `demo.container.dlq`.

~~~mermaid
flowchart LR
    P["RabbitTemplate"] --> X["demo.container.events<br/>direct exchange"]
    X -->|"order.created"| Q["demo.container.orders"]
    Q --> S["SimpleMessageListenerContainer<br/>@RabbitListener"]
    Q -.->|"reject / nack, requeue=false"| DX["demo.container.dlx"]
    DX -.->|"order.dead"| D["demo.container.dlq"]
~~~

Java configuration:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ContainerLabTopology {

    @Bean
    DirectExchange containerEvents() {
        return new DirectExchange("demo.container.events", true, false);
    }

    @Bean
    DirectExchange containerDlx() {
        return new DirectExchange("demo.container.dlx", true, false);
    }

    @Bean
    Queue containerOrders() {
        return QueueBuilder.durable("demo.container.orders")
                .deadLetterExchange("demo.container.dlx")
                .deadLetterRoutingKey("order.dead")
                .build();
    }

    @Bean
    Queue containerDlq() {
        return QueueBuilder.durable("demo.container.dlq").build();
    }

    @Bean
    Binding ordersBinding(Queue containerOrders,
                          DirectExchange containerEvents) {
        return BindingBuilder.bind(containerOrders)
                .to(containerEvents)
                .with("order.created");
    }

    @Bean
    Binding dlqBinding(Queue containerDlq,
                       DirectExchange containerDlx) {
        return BindingBuilder.bind(containerDlq)
                .to(containerDlx)
                .with("order.dead");
    }
}
~~~

Khi Spring Boot có `RabbitAdmin` được auto-configure phù hợp, các bean `Queue`, `DirectExchange` và `Binding` thường được khai báo trên broker lúc kết nối. Nếu queue đã có từ trước với arguments khác, broker có thể trả `PRECONDITION_FAILED - inequivalent arg`; không xóa queue có dữ liệu để “sửa” mà chưa có kế hoạch migration.

## 8. Factory riêng: chủ động cấp luồng cho consumer task

Để log phản ánh rõ mô hình luồng, tạo một `ThreadPoolTaskExecutor` có tiền tố tên `smlc-orders-`, sau đó gắn vào `SimpleRabbitListenerContainerFactory`.

Trong Spring Boot 3.x, `SimpleRabbitListenerContainerFactoryConfigurer` giúp **kế thừa cấu hình Boot** trước khi override một số thuộc tính dành riêng cho lab:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ContainerLabListenerConfig {

    @Bean("ordersListenerExecutor")
    ThreadPoolTaskExecutor ordersListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("smlc-orders-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(0);
        return executor;
    }

    @Bean("ordersListenerFactory")
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory,
            @Qualifier("ordersListenerExecutor") TaskExecutor executor) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        // Áp các cài đặt Boot trước khi ghi đè có chủ đích.
        configurer.configure(factory, connectionFactory);
        factory.setTaskExecutor(executor);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(5);
        return factory;
    }
}
~~~

**Giải thích:**

1. `ordersListenerExecutor` cấp các thread xử lý consumer task, được đặt tên dễ nhận trong log.
2. `setCorePoolSize(4)` và `setMaxPoolSize(8)` dành dư năng lực cho **một listener container** có tối đa 4 consumer trong lab; không có nghĩa 8 consumer tự xuất hiện.
3. `queueCapacity=0` tránh việc một số consumer task sống lâu bị giữ mãi trong hàng chờ executor thay vì nhận thread; nếu vượt số thread tối đa, executor vẫn có thể từ chối task. Cần kiểm tra sizing khi có thêm listener khác dùng chung executor.
4. `configurer.configure(...)` giúp factory được áp các cài đặt Spring Boot phù hợp. Không nên chỉ `new` factory và đặt `ConnectionFactory` nếu bạn còn phụ thuộc converter, retry, timeout và các property khác của Boot.
5. `ordersListenerFactory` **không thay** factory mặc định `rabbitListenerContainerFactory`. Listener muốn dùng nó phải nêu rõ `containerFactory = "ordersListenerFactory"`.

**Nếu nhiều listener container cùng dùng factory/executor**, số consumer task tối đa có thể vượt 4. Lúc đó cần tính **tổng concurrency** và kiểm tra giới hạn threads, RabbitMQ channels, DB connections; các con số demo không còn đủ.

### Nếu muốn tạo SMLC trực tiếp, không dùng annotation

Spring AMQP cũng cho phép lập trình viên tạo `SimpleMessageListenerContainer` như một bean, rồi tự gắn một `MessageListener`:

~~~java
// Ví dụ rút gọn: dùng trong một cấu hình THAY THẾ, không chạy song song
// với @RabbitListener cùng queue khi muốn kiểm tra từng cách riêng biệt.
SimpleMessageListenerContainer container =
        new SimpleMessageListenerContainer(connectionFactory);
container.setQueueNames("demo.container.orders");
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(4);
container.setPrefetchCount(5);
container.setTaskExecutor(ordersExecutor);
container.setMessageListener(message -> {
    // Đây là listener dùng raw AMQP Message.
    System.out.println("Nhận message, thread="
            + Thread.currentThread().getName());
});
~~~

Đây là đoạn cấu hình **minh họa**, trong đó `connectionFactory` và `ordersExecutor` là các đối tượng được cung cấp từ bean/DI. Nếu đưa container vào Spring context như bean có lifecycle, Spring sẽ khởi động/dừng nó theo lifecycle phù hợp. Đừng tạo một SMLC ẩn danh rồi quên đăng ký/quản lý lifecycle, cũng không chạy SMLC trực tiếp và `@RabbitListener` cùng queue nếu muốn tất cả message đi qua đúng một handler.

## 9. Listener log thread, consumer tag và delivery tag

Khi annotation chỉ định `ordersListenerFactory`, Spring AMQP dùng factory đó để tạo SMLC cho endpoint:

~~~java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersContainerListener {
    private static final Logger log =
            LoggerFactory.getLogger(OrdersContainerListener.class);

    @RabbitListener(
            id = "ordersContainerListener",
            queues = "demo.container.orders",
            containerFactory = "ordersListenerFactory")
    public void receive(Message message) throws InterruptedException {
        MessageProperties p = message.getMessageProperties();
        String orderId = new String(
                message.getBody(), StandardCharsets.UTF_8);

        log.info(
                "START orderId={} msgId={} thread={} consumerTag={} "
                        + "deliveryTag={} redelivered={}",
                orderId,
                p.getMessageId(),
                Thread.currentThread().getName(),
                p.getConsumerTag(),
                p.getDeliveryTag(),
                p.isRedelivered());

        // Chỉ để quan sát concurrency trong lab.
        Thread.sleep(350);

        if (orderId.startsWith("BAD-")) {
            throw new AmqpRejectAndDontRequeueException(
                    "Dữ liệu đơn hàng không hợp lệ: " + orderId);
        }

        // Production: commit công việc nghiệp vụ idempotent trước khi ACK.
        log.info("DONE orderId={} thread={}",
                orderId, Thread.currentThread().getName());
    }
}
~~~

Với `AcknowledgeMode.AUTO` của listener container, khi phương thức kết thúc thành công container sẽ ACK delivery tương ứng. Nếu ném `AmqpRejectAndDontRequeueException`, container xử lý theo đường **reject/nack không requeue** và với topology lab đã khai báo, message có thể được chuyển sang DLQ.

`Thread.sleep(350)` **chỉ mô phỏng công việc chậm** cho mục đích quan sát, không phải kỹ thuật tối ưu hiệu năng hoặc triển khai production. Nếu thread bị interrupt khi shutdown, listener có thể thất bại; cần xử lý shutdown/retry theo thiết kế. Trong hệ thống thật, thay bằng nghiệp vụ có validation, giới hạn thời gian, transaction và idempotency.

Khi có nhiều consumer, log sẽ cho thấy các message xen kẽ trên những thread tên `smlc-orders-...`. **Không có cam kết một đơn hàng sẽ luôn vào cùng một consumer/thread**; đặc biệt nếu có reconnect hoặc scale. `consumerTag` mô tả subscription, `deliveryTag` chỉ nhận diện delivery trên AMQP channel tương ứng; **không dùng hai trường này làm event ID**.

## 10. Producer tạo tải từ RabbitTemplate

Để kiểm tra nhiều consumer cùng xử lý, tạo một HTTP endpoint publish các sự kiện đơn hàng. Ví dụ có giới hạn số lượng gửi nhằm tránh làm đầy queue ngoài ý muốn:

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/orders")
public class ContainerLabPublisher {
    private final RabbitTemplate rabbitTemplate;

    public ContainerLabPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostMapping("/batch")
    public ResponseEntity<Map<String, Object>> batch(
            @RequestParam(defaultValue = "12") int count,
            @RequestParam(defaultValue = "false") boolean includeBad) {

        if (count < 1 || count > 50) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "count must be between 1 and 50"));
        }

        for (int i = 0; i < count; i++) {
            String orderId = (includeBad && i == 0 ? "BAD-" : "ORD-")
                    + UUID.randomUUID();
            String eventId = UUID.randomUUID().toString();

            rabbitTemplate.convertAndSend(
                    "demo.container.events",
                    "order.created",
                    orderId,
                    message -> {
                        message.getMessageProperties().setMessageId(eventId);
                        message.getMessageProperties()
                                .setHeader("eventId", eventId);
                        message.getMessageProperties()
                                .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                        return message;
                    });
        }

        return ResponseEntity.accepted().body(
                Map.of("submitted", count, "includeBad", includeBad));
    }
}
~~~

`202 Accepted` trong demo chỉ thể hiện HTTP handler đã gọi các lệnh publish mà không phát hiện lỗi đồng bộ. Nó **không xác nhận** broker đã ACK tất cả publication hoặc các listener đã xử lý xong. Khi nghiệp vụ cần biết broker nhận message nào, dùng **publisher confirms tương quan** và **publisher returns** nếu cần phát hiện unroutable publication.

Nếu exchange `demo.container.events` không tồn tại, hoặc binding sai, kết quả publish có thể thất bại hoặc message không đến queue như mong muốn. Cần kiểm tra topology trong RabbitMQ Management thay vì chỉ nhìn HTTP response.

## 11. Chạy thử và quan sát luồng riêng cho consumer

### 11.1. Gửi tải hợp lệ

Khởi động RabbitMQ và Spring Boot với các bean đã khai báo, rồi gửi:

~~~bash
curl -X POST "http://localhost:8080/demo/orders/batch?count=20"
~~~

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là alias không nhận cú pháp trên.

Log có thể tương tự:

~~~text
smlc-orders-1 START orderId=ORD-... consumerTag=amq.ctag-... deliveryTag=1
smlc-orders-2 START orderId=ORD-... consumerTag=amq.ctag-... deliveryTag=1
smlc-orders-1 DONE  orderId=ORD-...
smlc-orders-2 DONE  orderId=ORD-...
smlc-orders-1 START orderId=ORD-... consumerTag=amq.ctag-... deliveryTag=2
~~~

Các giá trị `deliveryTag` và tên consumer ở đây chỉ là **ví dụ**. Cùng số `deliveryTag=1` ở hai channel là hợp lệ vì mỗi channel có chuỗi tag riêng. Số consumer có thể tăng/giảm theo điều kiện runtime; không kết luận cấu hình hỏng chỉ vì một batch ngắn không tăng ngay từ 2 lên 4.

### 11.2. Tạo một message lỗi và quan sát DLQ

~~~bash
curl -X POST "http://localhost:8080/demo/orders/batch?count=3&includeBad=true"
~~~

Message có body bắt đầu bằng `BAD-` sẽ khiến listener ném `AmqpRejectAndDontRequeueException`. Với DLX và binding đang hoạt động, message lỗi có thể chuyển từ `demo.container.orders` sang `demo.container.dlq`. Hai message hợp lệ còn lại có thể được xử lý và ACK.

**Lưu ý:** một listener ném lỗi **không** trực tiếp thực hiện publisher return. Publisher returns thuộc phía **producer không định tuyến được tới queue**; DLQ thuộc đường message **đã vào queue rồi bị dead-letter** vì reject, TTL, giới hạn queue hoặc chính sách tương ứng.

### 11.3. Dùng Management để phân biệt các trạng thái

Trong RabbitMQ Management, mở **Queues and Streams** (hoặc **Queues** tùy giao diện), chọn `demo.container.orders`:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `Consumers` | Số consumer đang đăng ký lên queue | Quan sát số lượng tăng/giảm thực tế |
| `Ready` | Message đang nằm chờ được giao | Tăng khi producer nhanh hơn tốc độ giao/tiêu thụ |
| `Unacked` | Message broker đã giao nhưng chưa được xác nhận | Có thể tăng theo concurrency × prefetch |
| Deliver / Ack rate | Tốc độ giao và xác nhận | Dùng so sánh trước/sau khi đổi concurrency |
| Connections / Channels | AMQP connections/channels | Kiểm tra có bao nhiêu consumer/channel đang mở |
| `demo.container.dlq` | Message bị dead-letter | Kiểm tra reject không requeue và lý do xử lý lỗi |

**Management không cho biết chính xác pool thread của ứng dụng.** Muốn xem thread nhận listener đang chạy, dùng tên thread trong log, thread dump/metrics executor và `RabbitListenerEndpointRegistry`. Một channel tồn tại trên broker không đồng nghĩa có đúng một thread Java dành riêng vĩnh viễn cho nó ở mọi lúc.

### 11.4. Xem trạng thái container bằng registry

Với listener có `id="ordersContainerListener"`, có thể kiểm tra từ một Spring bean:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class OrdersContainerInspector {
    private final RabbitListenerEndpointRegistry registry;

    public OrdersContainerInspector(RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersContainerListener");
        return container != null && container.isRunning();
    }
}
~~~

`RabbitListenerEndpointRegistry` quản lý những container được tạo qua annotation. Khi container được khai báo trực tiếp dưới dạng `@Bean` thay vì tạo từ `@RabbitListener`, lifecycle/tra cứu có khác biệt; không giả định mọi bean container nằm trong cùng registry.

## 12. ACK, NACK và đường xử lý lỗi không phụ thuộc tên thread

Một consumer task trên executor riêng vẫn phải làm đúng hợp đồng acknowledgement. **Luồng riêng không thay thế ACK** và cũng không tự làm cho xử lý thành exactly-once.

### Các chế độ ACK

| Chế độ | Hành vi | Rủi ro/cách dùng |
|---|---|---|
| Spring `AUTO` | Container ACK sau khi listener xử lý thành công; lỗi đi theo error handler/reject/requeue | Thường phù hợp với xử lý đồng bộ trong phương thức |
| Spring `MANUAL` | Code ứng dụng ACK/NACK delivery trên đúng `Channel` | Dùng khi phải kiểm soát thời điểm xác nhận |
| Spring `NONE` | RabbitMQ auto-ack khi giao, broker không chờ kết quả listener | Có thể mất message khi consumer chết trong lúc xử lý |

`AcknowledgeMode.AUTO` của Spring **khác** với RabbitMQ client `autoAck=true`; nó gần với cơ chế consumer ack do container quản lý.

### Ví dụ thay thế: manual ACK trên SMLC

Nếu muốn manual ack, **thay listener trong mục 9** bằng một listener tương đương dưới đây thay vì chạy cả hai trên cùng queue:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualOrdersListener {

    @RabbitListener(
            queues = "demo.container.orders",
            containerFactory = "ordersListenerFactory",
            ackMode = "MANUAL")
    public void receive(Message message, Channel channel)
            throws IOException {

        long tag = message.getMessageProperties().getDeliveryTag();
        String orderId = new String(
                message.getBody(), StandardCharsets.UTF_8);

        if (orderId.isBlank()) {
            channel.basicReject(tag, false); // Không requeue.
            return;
        }

        // Production: xử lý idempotent và commit phù hợp trước khi ACK.
        channel.basicAck(tag, false);
    }
}
~~~

**Chỉ ACK/NACK trên channel của chính delivery đó.** `deliveryTag` là số trong phạm vi channel; không chuyển tag sang một channel khác để xác nhận. ACK hai lần hoặc ACK sai channel có thể làm RabbitMQ đóng channel với lỗi `unknown delivery tag`. Đặc biệt, đừng dùng `multiple=true` thiếu kiểm soát khi nhiều delivery chưa ACK đang tồn tại.

Với listener dùng `AUTO`, **không tự gọi `basicAck`** cho cùng delivery; nếu không, container có thể ACK lại và gây lỗi. Nếu listener khởi chạy tác vụ nền rồi trả về ngay, `AUTO` có thể ACK **trước khi tác vụ nền hoàn tất**. Muốn xử lý bất đồng bộ đúng, cần dùng cơ chế async listener được Spring AMQP hỗ trợ phù hợp phiên bản hoặc kiểm soát thủ công lifecycle ACK, timeout và lỗi; không chỉ `CompletableFuture.runAsync(...)` rồi trả về.

### Retry và dead-letter

- **Lỗi dữ liệu cố định:** thường reject không requeue và đưa vào DLQ để điều tra; tránh hot loop.
- **Lỗi tạm thời:** retry có backoff, giới hạn số lần, log/metrics và phương án DLQ khi vượt giới hạn.
- **Mất kết nối khi chưa ACK:** broker có thể giao lại delivery; code nghiệp vụ cần **idempotency**.
- **Publisher đã nhận confirm ACK:** không có nghĩa consumer vừa xử lý xong; publisher confirms và consumer acknowledgments thuộc các bước khác nhau.

SMLC vận hành kênh và thread cho listener nhưng **không** tự tạo một transaction nguyên tử giữa RabbitMQ với database. Nếu nghiệp vụ vừa ghi DB vừa phát event, cân nhắc transactional outbox ở producer, consumer idempotent và cơ chế phục hồi hợp lý.

## 13. Shutdown, recovery và những message chưa xử lý

### 13.1. Dừng container không chỉ là ngừng một thread

SMLC quản lý các consumer đang chạy, channel, executor tasks và delivery chưa ACK. Khi dừng, container cố gắng đóng consumer hợp lệ và cho các xử lý đang thực hiện hoàn tất theo cấu hình shutdown. Nếu **hết thời hạn chờ**, channel/connection có thể bị đóng và các delivery chưa ACK được broker giao lại.

Trong Spring AMQP có các cấu hình liên quan tới graceful shutdown (ví dụ `shutdownTimeout` và cách xử lý force close). Ý nghĩa cụ thể phụ thuộc phiên bản/cấu hình. Không nên suy rằng mọi `stop()` sẽ chờ vô hạn đến khi tất cả giao dịch DB hoàn tất.

**Quy tắc vận hành:** xử lý ngắt an toàn, giữ ID nghiệp vụ để chống trùng, kiểm soát tác vụ đang chạy và theo dõi lại `Ready/Unacked` sau khi restart. Đừng tự kill thread hoặc đóng channel tùy tiện khi còn business transaction chưa xác định trạng thái.

### 13.2. Recovery khi RabbitMQ hoặc consumer gặp lỗi

Khi broker tạm ngắt hoặc consumer bị hủy, listener container thường cố gắng **khôi phục consumer** theo cơ chế quản lý của Spring AMQP. Consumer tag, channel và thread có thể thay đổi sau khi phục hồi. Các message đã giao nhưng chưa ACK có thể được giao lại.

`redelivered=true` là một tín hiệu chẩn đoán, **không phải bộ đếm retry** và không chứng minh side effect nghiệp vụ đã thực hiện hay chưa. Ngược lại, `redelivered=false` cũng không bảo đảm event chưa từng được producer gửi trùng. Dùng `eventId` ổn định và kiểm tra idempotency bền vững.

### 13.3. Backpressure không chỉ nằm ở queue

SMLC có thể chịu áp lực ở nhiều tầng:

~~~text
Producer publish nhanh
    ↓
RabbitMQ queue Ready tăng
    ↓
Broker deliver tới consumer (prefetch)
    ↓
Unacked / nội bộ consumer SMLC tăng
    ↓
TaskExecutor xử lý nghiệp vụ
    ↓
Database, HTTP hoặc external service chậm
~~~

Tăng consumer có thể **chuyển bottleneck** sang database hoặc downstream service thay vì loại bỏ bottleneck. Nếu DB chỉ có 5 connection hữu dụng, tăng 20 consumer xử lý cùng lúc chưa chắc giúp cải thiện. Cần đo latency, error rate và capacity của toàn luồng, không chỉ số lượng thread.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `@RabbitListener` không nhận message | Sai queue/exchange/binding/vhost; consumer chưa được đăng ký | Xem topology, Consumers, logs và listener registry |
| Cấu hình `max-concurrency=4` nhưng chỉ thấy 2 consumer | SMLC chưa đủ điều kiện tăng động; tải quá ngắn | Quan sát dưới tải kéo dài; kiểm tra active/idle trigger và executor |
| Thread mang tên mặc định, không có `smlc-orders-` | Listener đang dùng factory khác hoặc custom executor không được gắn | Kiểm tra `containerFactory="ordersListenerFactory"` và bean thực tế |
| Executor báo reject task / container không mở đủ consumer | Pool thread quá nhỏ, executor bị dùng chung hoặc bị shutdown | Tính tổng consumer tasks, chỉnh capacity và tách workload |
| `Unacked` cao nhưng CPU thấp | Prefetch lớn; listener đang chờ DB/I/O hoặc delivery được đệm | Kiểm tra thread dump, downstream latency, prefetch |
| `Ready` tăng liên tục | Producer nhanh hơn consumer hoặc consumer không chạy | Xem tốc độ ACK/deliver, DB và concurrency |
| Message xử lý lặp sau restart | Delivery chưa ACK được giao lại hoặc producer gửi trùng | Idempotency bằng `eventId` và transaction nghiệp vụ |
| Channel bị đóng với `unknown delivery tag` | ACK hai lần, ACK sai channel, trộn `AUTO` với `MANUAL` | Sửa ACK semantics, dùng tag/channel đúng |
| Message lỗi bị giao lại liên tục | Requeue mặc định hoặc retry không giới hạn | Dùng backoff, giới hạn retry, DLQ, phân loại lỗi |
| Message bị DLQ ngay vì lỗi mạng tạm thời | Reject không requeue áp cho mọi exception | Thiết kế retry tạm thời riêng, kiểm tra error handler |
| Listener thread chậm hoặc đứng | Blocking I/O không timeout, lock, deadlock | Đặt timeout, điều tra thread dump, tránh giữ lock lâu |
| Cấu hình `listener.simple.*` không có tác dụng | Listener dùng custom factory không gọi configurer, hoặc dùng direct container | Xác định loại container/factory đang chạy, áp đúng property |

## 15. Bài tập tự thực hành

**Bài A — Nhận diện thread riêng.** Chạy lab và publish 20 order hợp lệ. Nhóm log theo `consumerTag` và `thread`. Giải thích vì sao những thread `smlc-orders-*` thuộc executor của ứng dụng, còn message thực tế đến từ broker qua RabbitMQ client.

**Bài B — So sánh số consumer.** Cấu hình `concurrency=1` rồi `concurrency=2`, giữ `prefetch=5` và tải giống nhau. Đo thời gian xử lý, số Consumers và mức Unacked. Đừng suy throughput sẽ tăng đúng 2 lần nếu phần xử lý bị giới hạn ở DB/I/O.

**Bài C — Thay prefetch.** Chạy cùng một workload với `prefetch=1` và `prefetch=20`. So sánh độ sâu Ready/Unacked, sự phân phối message giữa các consumer và bộ nhớ; giải thích vì sao prefetch không tạo thêm threads.

**Bài D — Executor quá nhỏ.** Trong môi trường lab riêng, giới hạn executor còn ít hơn số consumer tối đa và mô phỏng tải kéo dài. Ghi nhận trạng thái container/consumer, log task rejection hoặc thread contention (nếu phát sinh), rồi khôi phục cấu hình an toàn. Không thử trên RabbitMQ dùng cho production.

**Bài E — Message lỗi và DLQ.** Gọi endpoint với `includeBad=true`; quan sát `demo.container.dlq`. Trình bày sự khác biệt giữa **consumer reject** và **publisher return** khi routing key sai.

**Bài F — Đổi sang DMLC về mặt thiết kế.** Không cần viết lại toàn bộ lab: liệt kê những tham số cần xem lại nếu đổi `spring.rabbitmq.listener.type=direct`, đặc biệt `consumersPerQueue` và mô hình client dispatch thread, rồi đề xuất benchmark có cùng tải và mức bảo đảm ACK.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `SimpleMessageListenerContainer` có gọi `@RabbitListener` ngay trên RabbitMQ client delivery thread không?

**Đáp án:** Trong mô hình SMLC, delivery được chuyển qua hàng đợi nội bộ và listener được gọi từ **consumer task chạy trên `TaskExecutor`**. Đây là điểm khác với DMLC.

**Câu 2.** `concurrentConsumers=4` có nghĩa SMLC tạo thread mới cho mỗi message không?

**Đáp án:** Không. Thông thường có **một consumer task lâu dài cho mỗi consumer**; task xử lý liên tiếp nhiều delivery trên thread do executor cung cấp.

**Câu 3.** Nếu đặt `prefetch=20`, có 20 thread xử lý song song cho một consumer không?

**Đáp án:** Không. Prefetch kiểm soát số delivery có thể chưa được ACK theo consumer/QoS, không phải số thread listener.

**Câu 4.** Vì sao executor có thể làm SMLC không đạt concurrency đã đặt?

**Đáp án:** Consumer task cần luồng để hoạt động; nếu executor thiếu thread hoặc giữ task trong hàng chờ, số consumer thực sự chạy có thể không đạt số mong muốn.

**Câu 5.** Spring `AUTO` có đợi `CompletableFuture.runAsync(...)` được một listener tự tạo hoàn tất không?

**Đáp án:** Không nên mặc định như vậy. Nếu listener trả về bình thường trước khi công việc nền hoàn tất, container có thể ACK quá sớm; cần cơ chế async acknowledgment được framework hỗ trợ hoặc thiết kế manual ACK an toàn.

**Câu 6.** SMLC có làm message được xử lý exactly-once khi consumer mất connection không?

**Đáp án:** Không. Delivery chưa ACK có thể được giao lại; idempotency và transaction nghiệp vụ vẫn cần thiết.

**Câu 7.** Nếu consumer nhận được message rồi reject không requeue, có phải producer vừa nhận `basic.return` không?

**Đáp án:** Không. Reject/NACK là hành vi **consumer đối với delivery đã vào queue**. Publisher return xảy ra **trong quá trình publish** khi message không định tuyến đến queue nào và có `mandatory` phù hợp.

## 17. Ghi nhớ

- **SMLC tách luồng RabbitMQ client và luồng chạy listener** bằng cách chuyển delivery qua hàng đợi nội bộ, rồi xử lý bằng **consumer task trên `TaskExecutor`**.
- **Một consumer thường có một tác vụ lâu dài**, không phải mỗi message một thread mới. Số consumer hoạt động phụ thuộc concurrency động và executor capacity.
- **`prefetch` giới hạn in-flight deliveries, không giới hạn số thread**; cần quan sát cả Ready, Unacked, số consumer, latency và downstream resources.
- **SMLC khác DMLC về mô hình luồng**. Chọn loại container và thông số theo workload thực tế, không theo giả định “direct luôn nhanh hơn”.
- **Luồng xử lý riêng không thay cho độ tin cậy**: vẫn cần đúng exchange/queue/binding, consumer ACK, publisher confirms/returns, retry có giới hạn, DLQ, idempotency, transaction/outbox và giám sát hệ thống.
