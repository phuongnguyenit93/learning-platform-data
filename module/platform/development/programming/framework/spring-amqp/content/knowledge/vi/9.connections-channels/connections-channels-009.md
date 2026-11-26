# Executor, heartbeat, timeout và tên kết nối trong Spring AMQP

Ứng dụng có thể khai báo exchange, queue và binding chính xác nhưng `RabbitTemplate` vẫn gửi chậm, `@RabbitListener` ngừng nhận message, hoặc RabbitMQ Management UI xuất hiện hàng chục kết nối mang tên khó phân biệt. Nguyên nhân đôi khi không nằm ở routing hay payload mà ở **cách ứng dụng quản lý connection, channel, thread, heartbeat và timeout**. Đây là nhóm cấu hình phải hiểu trước khi xử lý lỗi mất kết nối hoặc mở rộng số consumer.

Bài học thuộc chương **Kết nối và channel** trong module **SPRING_AMQP**: học tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding; thực hành định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống để xây xử lý bất đồng bộ đáng tin cậy. Trọng tâm bài này là bốn yếu tố **executor**, **heartbeat**, **timeout** và **connection name** cùng những ảnh hưởng thực tế của chúng.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt TCP/AMQP **connection** với **channel** và giải thích vì sao Spring AMQP thường dùng `CachingConnectionFactory`.
2. Nhận diện các nhóm thread: RabbitMQ client dispatch executor, listener container task executor và thread I/O; phân biệt hành vi của `SimpleMessageListenerContainer` và `DirectMessageListenerContainer`.
3. Giải thích cách RabbitMQ và client thương lượng heartbeat, phát hiện mất kết nối và nguyên nhân gây false positive.
4. Chọn đúng loại timeout cho lỗi TCP connect, channel RPC, mượn channel từ cache hoặc đợi response ứng dụng.
5. Gắn tên kết nối dễ quan sát bằng `ConnectionNameStrategy`, đối chiếu tên đó trong RabbitMQ Management UI và log.
6. Thực hành kiểm chứng mất kết nối, chậm consumer, lỗi timeout và quá tải executor mà không nhầm với lỗi routing hoặc retry nghiệp vụ.

## 2. Connection và channel: hai tài nguyên có vòng đời khác nhau

AMQP 0-9-1 dùng một **connection** (thường là kết nối TCP lâu dài) để truyền nhiều **channel** logic. Channel cho phép các luồng publish/consume hoạt động độc lập trên cùng connection mà không phải mở socket mới cho từng message.

~~~mermaid
flowchart LR
    A["Spring application"] --> F["CachingConnectionFactory"]
    F --> C["AMQP connection<br/>TCP/TLS socket"]
    C --> CH1["Channel 1<br/>RabbitTemplate publish"]
    C --> CH2["Channel 2<br/>Listener A"]
    C --> CH3["Channel 3<br/>Listener B"]
    CH1 --> R["RabbitMQ broker"]
    CH2 --> R
    CH3 --> R
~~~

| Thành phần | Bản chất | Vòng đời điển hình | Khi xảy ra lỗi |
|---|---|---|---|
| **Connection** | Kết nối mạng và phiên AMQP tới broker | Lâu dài, thường dùng lại | Mất connection ảnh hưởng các channel đi qua nó |
| **Channel** | Phiên logic multiplex trên connection | Có thể được cache và tái sử dụng | Một lỗi AMQP cấp channel có thể đóng riêng channel |
| **RabbitTemplate** | API cấp cao để gửi/nhận message | Bean dùng chung | Lấy và trả channel qua connection factory theo thao tác |
| **@RabbitListener container** | Quản lý consumer, channel và xử lý delivery | Hoạt động trong thời gian ứng dụng chạy | Có cơ chế khôi phục consumer/channel tùy cấu hình |
| **CachingConnectionFactory** | Quản lý connection và cache channel của Spring AMQP | Thường là bean ứng dụng | Kết nối lại và cấp channel mới khi thích hợp |

Mặc định thường gặp của `CachingConnectionFactory` là **cache channel trên một connection được chia sẻ** (`CacheMode.CHANNEL`). `channelCacheSize` là **số channel nhàn rỗi có thể giữ lại trong cache**, không phải mặc nhiên là giới hạn số channel đang được sử dụng. Khi bật một `channelCheckoutTimeout` dương, cache size có thể trở thành giới hạn channel trên connection; người gọi phải chờ channel rảnh hoặc gặp timeout.

Một channel bị đóng vì `404 NOT_FOUND` khi khai báo/consume tài nguyên không tồn tại **không nhất thiết làm đóng cả TCP connection**. Ngược lại, mất socket/connection sẽ ảnh hưởng tất cả channel của connection đó. Cần đọc nguyên nhân trong log thay vì gọi mọi lỗi là “RabbitMQ disconnect”.

### Đừng mở connection mới cho mỗi message

Tạo connection tốn handshake, xác thực, tài nguyên socket và thread. Mở một connection cho mỗi `convertAndSend` là lựa chọn tốn kém và gây connection churn. Thông thường hãy dùng một `RabbitTemplate` bean và `ConnectionFactory` được quản lý, tránh tự mở/đóng kết nối trong mỗi request HTTP.

Nếu ứng dụng có lượng publish lớn, nhiều consumer, hoặc broker có cơ chế resource alarm/flow control, có thể cân nhắc **connection riêng cho publisher và consumer** để giảm ảnh hưởng lẫn nhau. Nhưng việc chia connection không tự giải quyết vấn đề thiếu channel hoặc thiếu năng lực consumer.

## 3. Executor: xác định thread nào thật sự xử lý công việc

Chữ “executor” trong Spring AMQP thường chỉ **hai lớp khác nhau**. Đặt nhầm executor hoặc cho quá ít thread có thể khiến listener chậm, callback bị nghẽn, thậm chí làm việc phát hiện lỗi kết nối trở nên khó chẩn đoán.

| Executor/thread | Ai quản lý? | Công việc chính | Điều cần quan sát |
|---|---|---|---|
| **RabbitMQ Java client executor** | Client hoặc `CachingConnectionFactory.setExecutor(...)` | Dispatch consumer deliveries/callbacks từ client đến container | Số thread, hàng đợi tác vụ, sự trì hoãn callback |
| **Listener container TaskExecutor** | `SimpleMessageListenerContainer`/`DirectMessageListenerContainer` | Với SMLC, chạy các listener invoker; với DMLC, phục vụ các tác vụ hỗ trợ/giám sát | Số consumer cần thiết, thời gian chạy logic nghiệp vụ |
| **Client socket/I/O threads** | RabbitMQ Java client và thread factory của nó | Đọc/ghi frame mạng, xử lý giao thức | Socket errors, CPU, network và lỗi I/O |
| **Application business executor** | Ứng dụng tùy thiết kế | Công việc bất đồng bộ do listener tự chuyển giao | Timeout/cancellation, idempotency và thời điểm ack |

### 3.1. SimpleMessageListenerContainer (SMLC)

Với `SimpleMessageListenerContainer`, thread từ **RabbitMQ client executor** nhận/dispatch delivery vào cơ chế container; `TaskExecutor` của **SMLC** được dùng để chạy listener invokers và gọi logic `@RabbitListener`. Nếu bạn cấu hình `concurrentConsumers = 4` và cho SMLC một thread pool chỉ có 2 thread không thể mở rộng, các invoker có thể bị đói thread.

~~~mermaid
flowchart LR
    NET["RabbitMQ client<br/>nhận delivery"] --> CLIENT["Client dispatch executor"]
    CLIENT --> BRIDGE["SimpleMessageListenerContainer"]
    BRIDGE --> APP["Container TaskExecutor"]
    APP --> L["@RabbitListener<br/>xử lý nghiệp vụ"]
~~~

Vì vậy, **tăng concurrency mà không tăng nguồn lực thực thi phù hợp** có thể làm giảm throughput hoặc tạo hàng đợi không mong muốn. Số consumer phải cân đối với CPU, database connection pool, downstream API và prefetch, không chỉ số thread.

### 3.2. DirectMessageListenerContainer (DMLC)

Với `DirectMessageListenerContainer`, callback của `@RabbitListener` chạy **trực tiếp trên thread dispatch của RabbitMQ client**. `TaskExecutor` của DMLC chủ yếu liên quan tác vụ giám sát container. Nếu listener blocking lâu hoặc client executor thiếu thread, các consumer khác có thể bị ảnh hưởng. Do đó, khi dùng DMLC, phải đặc biệt chú ý **client executor** đủ khả năng phục vụ tổng consumer trên connection factory.

~~~mermaid
flowchart LR
    NET["RabbitMQ client<br/>delivery"] --> EXEC["Client dispatch executor"]
    EXEC --> DMLC["DirectMessageListenerContainer"]
    DMLC --> L["@RabbitListener<br/>gọi trực tiếp"]
    MON["Container TaskExecutor"] -.->|"monitor tasks"| DMLC
~~~

Không thể chữa lỗi DMLC bị nghẽn callback chỉ bằng cách tăng `taskExecutor` của listener theo cùng suy luận như SMLC. Trước khi chỉnh thread pool, hãy xác nhận `spring.rabbitmq.listener.type` hoặc loại container thực tế.

### 3.3. Dấu hiệu thiếu thread và cách chọn pool

Các dấu hiệu thường gặp là queue depth tăng, số consumer đã đăng ký nhưng throughput thấp, thread dump có nhiều callback chờ, hoặc executor queue liên tục đầy. Cần phân biệt:

- Thiếu client dispatch threads: delivery/callback đến các container bị trì hoãn.
- Thiếu SMLC invoker threads: logic listener không có đủ worker để chạy.
- Nghiệp vụ blocking lâu: thread vẫn đang chạy nhưng chờ database/API hoặc lock.
- Broker flow control, network/connection issue: tăng executor không cải thiện nguyên nhân.

Nếu có nhiều connection, client mặc định có thể tạo executor riêng cho từng connection, làm số thread tăng mạnh. Dùng **shared executor** là lựa chọn khi hiểu tổng tải và đã cấp đủ thread. Đừng dùng một pool quá nhỏ để “tiết kiệm thread” rồi làm nghẽn mọi consumer.

Các giá trị pool size trong ví dụ bên dưới chỉ phục vụ thực hành; cần đo tải, số connection, tổng số consumer, tình trạng blocking và queueing để quyết định số thực tế.

## 4. Cấu hình executor trong Spring AMQP

### 4.1. Client executor trên CachingConnectionFactory

Với ứng dụng **tự sở hữu cấu hình connection factory**, có thể truyền một Spring `ThreadPoolTaskExecutor` tới `CachingConnectionFactory.setExecutor`. Ví dụ sau minh họa cách lắp ráp các bean; các cấu hình host, credential và TLS phải phù hợp môi trường thực tế.

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RabbitConnectionConfiguration {

    @Bean
    ThreadPoolTaskExecutor rabbitClientExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("rabbit-client-");
        return executor;
    }

    @Bean
    CachingConnectionFactory rabbitConnectionFactory(
            Environment environment,
            ThreadPoolTaskExecutor rabbitClientExecutor) {

        String host = environment.getRequiredProperty("spring.rabbitmq.host");
        String username =
                environment.getRequiredProperty("spring.rabbitmq.username");
        String password =
                environment.getRequiredProperty("spring.rabbitmq.password");

        CachingConnectionFactory factory =
                new CachingConnectionFactory(host);
        factory.setUsername(username);
        factory.setPassword(password);
        factory.setRequestedHeartBeat(20); // Giây, còn phải negotiate.
        factory.setConnectionTimeout(5_000); // Mili giây.
        factory.setExecutor(rabbitClientExecutor);
        factory.setChannelCacheSize(25);
        factory.setConnectionNameStrategy(
                connectionFactory -> "orders-service:consumer"
        );
        return factory;
    }
}
~~~

**Quan trọng:** Bean `CachingConnectionFactory` tự tạo sẽ thay thế hoặc làm thay đổi cách Spring Boot auto-configure factory. Đoạn minh họa trên **không tự giữ lại** những cấu hình Boot khác như TLS, danh sách địa chỉ cluster, credentials provider hay publisher confirms. Không copy vào một ứng dụng đang chạy và mặc định mọi property Boot vẫn được truyền sang bean thủ công. Nếu chỉ cần heartbeat/timeout và connection name, nên ưu tiên **cấu hình Spring Boot có sẵn và bean `ConnectionNameStrategy`** ở các mục sau.

Spring AMQP hỗ trợ `setExecutor(Executor)` trên `AbstractConnectionFactory`; có thể truyền `ExecutorService` hoặc `ThreadPoolTaskExecutor` thích hợp. Với `ThreadPoolTaskExecutor` khai báo bằng `@Bean`, Spring gọi bước khởi tạo theo vòng đời bean, nên đoạn ví dụ không cần gọi thêm `initialize()` thủ công. Khi tự quản lý executor, ứng dụng cũng phải quản lý **vòng đời shutdown**. Với bean `ThreadPoolTaskExecutor` do Spring quản lý, cấu hình shutdown và theo dõi pool phù hợp với hành vi cần thiết khi dừng ứng dụng.

### 4.2. TaskExecutor cho SimpleRabbitListenerContainerFactory

Nếu mục tiêu là điều chỉnh thread **thực thi logic listener SMLC**, cấu hình một listener factory cụ thể:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class OrderListenerConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("orders-listener-");
        return executor;
    }

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            ThreadPoolTaskExecutor orderListenerExecutor) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setTaskExecutor(orderListenerExecutor);
        factory.setConcurrentConsumers(4);
        factory.setMaxConcurrentConsumers(8);
        return factory;
    }
}
~~~

Sử dụng factory đó tại listener:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @RabbitListener(
        queues = "orders.created.q",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(String payload) {
        // Xử lý nghiệp vụ; kiểm tra idempotency nếu có thể redeliver.
        System.out.println(payload);
    }
}
~~~

Để queue `orders.created.q` thật sự nhận message, vẫn phải có exchange/binding và producer gửi đúng route. Việc tăng executor không tạo queue/binding hoặc tự sửa lỗi message converter.

**Lưu ý:** Việc tự định nghĩa listener container factory có thể bỏ qua một số tùy biến auto-configuration của Spring Boot (ví dụ retry, converter, observation, ack mode) nếu không dùng configurer tương ứng. Trong ứng dụng dùng Boot, cân nhắc sử dụng `SimpleRabbitListenerContainerFactoryConfigurer` của **đúng phiên bản Boot** rồi chỉ thay task executor/concurrency cần thiết.

## 5. Heartbeat: phát hiện peer không còn phản hồi

Heartbeat trong AMQP 0-9-1 là **cơ chế phát hiện kết nối mạng không còn hoạt động** ở tầng giao thức, không phải phép đo sức khỏe nghiệp vụ của `@RabbitListener`.

Giả sử client và broker đã thiết lập connection với **heartbeat timeout = 20 giây**:

~~~mermaid
sequenceDiagram
    participant C as Spring / RabbitMQ client
    participant B as RabbitMQ broker
    Note over C,B: Heartbeat timeout thương lượng = 20 giây
    C->>B: AMQP frame / heartbeat khi kết nối nhàn rỗi
    B-->>C: AMQP frame / heartbeat
    Note over C,B: Khoảng gửi heartbeat thường ~10 giây
    B--xC: Mất gói tin / đứt mạng
    Note over C: Không có lưu lượng hợp lệ trong thời hạn
    C->>C: Đánh dấu connection không còn phản hồi
    C->>B: Thử thiết lập connection mới (theo cơ chế recovery)
~~~

Một số quy tắc quan trọng:

- **Giá trị cấu hình là heartbeat timeout**, thường tính theo **giây**, không phải “mỗi bao nhiêu giây gửi một frame”. Heartbeat frame có thể được gửi khoảng **một nửa** giá trị timeout khi thiếu traffic.
- **Traffic AMQP hợp lệ cũng được tính như heartbeat**; không nhất thiết nhìn thấy frame heartbeat riêng trên connection liên tục publish/consume.
- Timeout được **thương lượng giữa client và server** khi mở connection. Không nên diễn giải `requestedHeartbeat=20` là broker chắc chắn luôn chấp nhận 20 bất kể server cấu hình gì.
- Client và broker có thể đóng connection khi phát hiện peer không còn phản hồi; Spring AMQP sau đó thực hiện cơ chế kết nối/khởi tạo consumer lại nếu điều kiện cho phép.
- Heartbeat không bảo đảm message đã được broker ghi nhận hoặc consumer xử lý; việc đó cần publisher confirms, consumer acknowledgements và thiết kế xử lý trùng.

### 5.1. Cơ chế thương lượng

Với thuật toán của RabbitMQ Java client, nếu **cả hai giá trị đều khác 0**, timeout kết quả là giá trị **nhỏ hơn**. Nếu **một bên bằng 0**, kết quả là giá trị **lớn hơn**. Do đó, muốn **tắt heartbeat** bằng 0 thì **cả hai phía** phải đồng ý 0; không nên tắt trong các hệ thống thông thường.

| Broker đề xuất | Client yêu cầu | Timeout thương lượng |
|---|---|---|
| 60 giây | 20 giây | **20 giây** |
| 30 giây | 60 giây | **30 giây** |
| 60 giây | 0 giây | **60 giây** |
| 0 giây | 0 giây | **0 giây (tắt)** |

RabbitMQ thường đề xuất giá trị mặc định 60 giây, nhưng **phải kiểm tra giá trị thực tế của từng connection** trên broker của bạn. Một giá trị quá thấp (đặc biệt dưới vài giây) dễ gây false positive khi CPU quá tải, mạng nghẽn hoặc flow control tạm thời. Tài liệu RabbitMQ khuyến nghị tránh cấu hình rất thấp và thường xem khoảng 5–20 giây là phù hợp với nhiều môi trường; chọn giá trị dựa trên đo đạc thực tế.

### 5.2. Heartbeat không thay TCP keepalive và health check

| Cơ chế | Phát hiện điều gì? | Không giải quyết điều gì? |
|---|---|---|
| AMQP heartbeat | Peer kết nối không còn trao đổi frame trong thời hạn | Listener deadlock nghiệp vụ, payload sai, backlog |
| TCP keepalive | Socket lâu nhàn rỗi/peer mạng không phản hồi theo cấu hình hệ điều hành | Thành công publish hoặc consumer ack |
| Application health/metrics | Khả năng hoạt động theo định nghĩa của service | Mặc định không thay giao thức phát hiện mất connection |
| Publisher confirms | Broker xác nhận xử lý publish theo cơ chế confirm | Consumer đã hoàn thành giao dịch nghiệp vụ |

Heartbeat tạo lưu lượng nhỏ định kỳ, nên cũng có thể giúp ngăn proxy/load balancer đóng kết nối nhàn rỗi quá sớm. Tuy vậy, cần đối chiếu timeout của **load balancer, firewall, NAT và cả RabbitMQ**. Nếu một tầng mạng ngắt socket sớm hơn heartbeat, connection vẫn có thể bị mất.

Một listener bị kẹt truy vấn database **không nhất thiết** làm heartbeat lập tức thất bại: network/client heartbeat xử lý khác với thread nghiệp vụ. Cần quan sát riêng `messages_unacknowledged`, thời gian listener, thread dump và network status.

## 6. Timeout: cùng tên nhưng là những đồng hồ khác nhau

Khi gặp `TimeoutException` hoặc `AmqpTimeoutException`, đừng tăng mọi timeout cùng lúc. Hãy xác định **thao tác nào đang đợi**, **đợi điều kiện nào**, và **nguồn cấu hình** nằm ở tầng nào.

| Loại timeout | Phạm vi | Property/API điển hình | Biểu hiện khi hết |
|---|---|---|---|
| **TCP connect timeout** | Thiết lập socket đến RabbitMQ | `spring.rabbitmq.connection-timeout` / `setConnectionTimeout(...)` | Không mở được connection đến host/port |
| **AMQP handshake timeout** | Hoàn tất bắt tay giao thức sau khi có socket | RabbitMQ Java client `setHandshakeTimeout(...)`; broker `handshake_timeout` | TCP đã nối nhưng phiên AMQP không hình thành |
| **Channel RPC continuation timeout** | Chờ phản hồi của lệnh AMQP đồng bộ trên channel | `spring.rabbitmq.channel-rpc-timeout` nếu phiên bản Boot hỗ trợ | Lệnh declare/operation cần phản hồi không hoàn tất đúng hạn |
| **Channel checkout timeout** | Chờ channel khả dụng từ `CachingConnectionFactory` | `spring.rabbitmq.cache.channel.checkout-timeout` / `setChannelCheckoutTimeout(...)` | Chờ hết hạn khi giới hạn channel đang dùng đã đạt |
| **RabbitTemplate reply timeout** | Chờ response trong request/reply pattern | `spring.rabbitmq.template.reply-timeout` | Request đã gửi nhưng không có response ứng dụng đúng hạn |
| **RabbitTemplate receive timeout** | Chờ khi chủ động lấy message bằng `receive(...)` | `spring.rabbitmq.template.receive-timeout` | Polling không lấy được message trước thời hạn |
| **Listener receive timeout** | Chờ nhận delivery/batch trong listener container | `spring.rabbitmq.listener.simple.receive-timeout` theo version | Không có message trong khoảng đợi; không chứng minh mất connection |
| **Heartbeat timeout** | Chờ lưu lượng AMQP từ peer | `spring.rabbitmq.requested-heartbeat` + giá trị broker | Kết nối có thể được coi là không còn phản hồi |

**Không nhầm socket connect timeout với toàn bộ thời gian retry kết nối.** Một operation có thể thử nhiều địa chỉ, có retry/backoff hoặc mất thêm thời gian DNS/TLS/handshake tùy cấu hình. Timeout của một bước không bảo đảm toàn workflow kết thúc đúng một mốc duy nhất.

**Không nhầm reply timeout với publisher confirm.** Request/reply timeout nói về ứng dụng khác không trả lời đúng hạn; publisher confirm nói về broker xử lý publish. Một publish được confirm thành công vẫn có thể không có business reply.

### 6.1. Ví dụ Spring Boot AMQP 0-9-1

Với những phiên bản Spring Boot **3.x** có bộ `spring.rabbitmq.*` tương ứng:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: CHANGE_ME
    virtual-host: /
    connection-timeout: 5s
    requested-heartbeat: 20s
    channel-rpc-timeout: 10s
    cache:
      channel:
        size: 25
        checkout-timeout: 2s
    template:
      reply-timeout: 3s
~~~

Ví dụ dùng thông tin đăng nhập **giả định**; trong ứng dụng thật lấy secret từ cơ chế quản lý bí mật và không commit mật khẩu vào repository. Các giá trị 5s/20s/10s/2s/3s là để **minh họa cách cấu hình và phạm vi khác nhau**, không phải thiết lập tối ưu hay khuyến nghị áp dụng nguyên xi cho production.

Đặt `checkout-timeout = 2s` khác 0 có thể khiến `cache.channel.size` trở thành **giới hạn channel được sử dụng đồng thời** trong cache mode thích hợp. Với nhiều listener giữ channel lâu dài, đặt size quá thấp có thể làm publisher đợi channel và hết timeout. Nếu bạn không cần giới hạn cứng, hãy hiểu mặc định của cache và broker channel max trước khi bật checkout timeout.

**Lưu ý phiên bản:** Spring Boot có thể đổi starter, namespace hoặc cơ chế auto-configuration ở các thế hệ mới. Khi sử dụng Spring AMQP dựa trên RabbitMQ AMQP 0-9-1, hãy xác minh **đúng Spring Boot/Spring AMQP version đang dùng**, chọn tài liệu tương ứng thay vì copy property từ trang “latest”. Một số tên ở bảng trên có thể không có trên nhánh cũ.

### 6.2. Ví dụ bằng Java client khi tự quản lý factory

~~~java
import com.rabbitmq.client.ConnectionFactory;

public class RabbitClientOptions {

    public static ConnectionFactory create() {
        ConnectionFactory clientFactory = new ConnectionFactory();
        clientFactory.setHost("localhost");
        clientFactory.setPort(5672);
        clientFactory.setRequestedHeartbeat(20); // Giây.
        clientFactory.setConnectionTimeout(5_000); // Mili giây.
        clientFactory.setHandshakeTimeout(10_000); // Mili giây.
        return clientFactory;
    }
}
~~~

Đây là **underlying RabbitMQ Java client factory**, khác interface `org.springframework.amqp.rabbit.connection.ConnectionFactory`. Trong ứng dụng Spring Boot, thường không cần tự tạo nó; chỉ làm khi cần tinh chỉnh những API mà Boot/Spring AMQP chưa ánh xạ. Nếu dùng factory này để xây `CachingConnectionFactory`, phải quản lý đủ credential, TLS, recovery, connection name và các thông số khác.

## 7. Tên kết nối: biến một connection khó hiểu thành thông tin vận hành

Trong RabbitMQ Management UI, một connection có thể hiển thị dưới dạng địa chỉ IP/cổng, user, virtual host, protocol, số channel và **client-provided name**. Tên kết nối giúp phân biệt instance, role hoặc môi trường khi nhiều ứng dụng cùng kết nối broker.

Ví dụ đặt quy ước:

~~~text
orders-service/staging/instance-2/consumer
orders-service/staging/instance-2/publisher
billing-service/production/instance-7/consumer
~~~

Tên giúp người vận hành trả lời “connection này của service nào?” mà không phải suy từ IP container. Tuy nhiên, **connection name là nhãn dễ đọc, không phải ID duy nhất bắt buộc**. Hai connection có thể dùng cùng tên; đừng dùng tên đó làm khóa duy nhất để gọi RabbitMQ HTTP API hoặc xác định chính xác TCP socket.

### 7.1. ConnectionNameStrategy với Spring Boot auto-configuration

Trong các thế hệ Spring Boot RabbitMQ AMQP 0-9-1 hỗ trợ tích hợp này, một bean `ConnectionNameStrategy` có thể được Spring Boot tự phát hiện và gắn vào `CachingConnectionFactory` được auto-configure:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionNameStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class RabbitConnectionNameConfiguration {

    @Bean
    ConnectionNameStrategy connectionNameStrategy(Environment environment) {
        String application = environment.getProperty(
                "spring.application.name", "spring-amqp-service"
        );
        String profile = environment.getProperty(
                "app.environment", "local"
        );
        String instance = environment.getProperty(
                "app.instance-id", "instance-unknown"
        );

        return connectionFactory ->
                application + "/" + profile + "/" + instance;
    }
}
~~~

Khi dùng đoạn code, hãy thiết lập `app.environment` và `app.instance-id` từ deployment metadata của bạn nếu cần phân biệt instance. Ví dụ, trên Kubernetes, có thể đưa pod name vào property qua biến môi trường và cơ chế bind configuration phù hợp; tránh gắn password, token, toàn bộ URI kết nối hoặc dữ liệu cá nhân vào tên kết nối.

Trong Spring AMQP, `setConnectionNameStrategy(...)` cũng dùng được nếu bạn trực tiếp tạo `CachingConnectionFactory`. Nếu sử dụng connection riêng cho publisher theo cơ chế Spring AMQP, phần publisher có thể được gắn hậu tố như `.publisher` theo cách framework cấu hình. Cần quan sát tên connection **thực tế** trong broker, vì cấu hình và phiên bản có thể khác nhau.

### 7.2. Không trộn connection name với consumer tag

| Giá trị | Gắn với | Mục đích |
|---|---|---|
| **connection name** | AMQP connection | Nhận diện ứng dụng/instance/role trong quản trị |
| **connection identity trên broker** | Connection cụ thể | Phân biệt và thao tác với một connection thực |
| **channel number** | Channel trong một connection | Định danh logic channel, chỉ có ý nghĩa trong connection đó |
| **consumer tag** | Consumer subscription trên channel | Phân biệt consumer registration |
| **messageId/correlationId** | Message/workflow | Theo dõi publish/consume và nghiệp vụ |

Tên connection **không thay thế** message ID để chống xử lý trùng, consumer tag để quản lý subscription hoặc channel number để ack delivery.

## 8. Kết hợp executor, heartbeat, timeout và naming trong một hệ thống

Giả sử service xử lý đơn hàng có **4 consumer**, một `RabbitTemplate` publish sự kiện khác, và RabbitMQ broker chạy sau load balancer:

~~~mermaid
flowchart TD
    APP["orders-service<br/>instance-2"]
    APP --> CF["CachingConnectionFactory<br/>name: orders-service/staging/instance-2"]
    CF --> CLIENT["Client executor<br/>dispatch callbacks"]
    CF --> CON["AMQP connection<br/>heartbeat negotiated"]
    CON --> CH["Channels<br/>publish / consumers"]
    CLIENT --> SMLC["SimpleMessageListenerContainer"]
    SMLC --> TASK["Listener TaskExecutor<br/>4–8 workers"]
    TASK --> WORK["@RabbitListener<br/>business handler"]
    CH --> BROKER["RabbitMQ cluster"]
    BROKER --> METRICS["Connections / Channels / Queue metrics"]
~~~

Một cấu hình có thể có:

- **Connection name** để đọc đúng instance trong Management UI.
- **Heartbeat** phù hợp đặc tính mạng nhằm phát hiện socket chết.
- **Connection timeout** để tránh đợi rất lâu khi broker không thể kết nối.
- **Channel RPC timeout** để tránh chờ vô hạn trên những operation cần phản hồi.
- **Client executor** đủ sức dispatch callbacks cho tổng connection/consumer.
- **SMLC task executor** đủ sức xử lý số listener invokers, nhưng vẫn giới hạn concurrency theo năng lực database/downstream.
- **Publisher confirms và consumer acknowledgements** cho yêu cầu độ tin cậy; chúng không được tự tạo bởi việc đổi timeout.

Các thông số trên tương tác với nhau nhưng **không thể suy một giá trị từ giá trị khác**. Ví dụ, 20 giây heartbeat không nói rằng `RabbitTemplate.convertAndSend` phải luôn hoàn thành trong 20 giây hoặc consumer xử lý xong trong 20 giây.

## 9. Mất kết nối và recovery: điều gì được khôi phục?

Khi broker restart, mạng đứt hoặc proxy đóng socket, ứng dụng có thể phải:

1. Phát hiện connection đã lỗi thông qua network/heartbeat/exception.
2. Đóng hoặc loại bỏ tài nguyên channel/connection không còn hợp lệ.
3. Tạo connection mới và khôi phục channels, consumer registrations.
4. Tái khai báo topology do ứng dụng sở hữu nếu cơ chế `RabbitAdmin` được cấu hình.
5. Tiếp tục nhận message, xử lý redelivery và xác định lại trạng thái publish còn chưa confirm.

Spring AMQP có cơ chế connection/channel recovery riêng, và mặc định thường **vô hiệu hóa automatic recovery của RabbitMQ Java client** để tránh hai tầng recovery can thiệp lẫn nhau. Không tự bật cả hai với giả định “hai lớp phục hồi thì chắc chắn hơn”. Nếu cần đổi cơ chế, phải đọc tài liệu đúng phiên bản và kiểm thử broker restart/network partition.

### Recovery không có nghĩa exactly-once

Trong khoảng mất kết nối, producer có thể đã gửi bytes nhưng **chưa nhận confirm**. Sau reconnect, producer không thể suy chắc message cũ đã được broker chấp nhận hay chưa. Gửi lại có thể làm phát sinh trùng; không gửi lại có thể làm mất sự kiện.

Với consumer, message đã giao nhưng chưa ack khi connection đứt có thể được giao lại. **Delivery tag thuộc channel** và không được sử dụng làm business event ID ổn định qua reconnect. Một thiết kế đáng tin cậy cần:

- Publisher confirms và cơ chế lưu trạng thái/outbox khi cần.
- Idempotency key ổn định trên event và xử lý trùng ở consumer.
- Retry/backoff có giới hạn; dead-letter cho message xử lý lỗi theo thiết kế.
- Quan sát trạng thái kết nối, số message unacked, DLQ và outcome nghiệp vụ.

### Connection blocked khác connection disconnected

RabbitMQ có thể báo **connection.blocked** khi broker chịu áp lực tài nguyên, ví dụ memory/disk alarm. Lúc đó TCP connection có thể vẫn tồn tại và heartbeat vẫn là một khía cạnh riêng, nhưng hoạt động publish có thể bị ngăn/chậm. Spring AMQP cung cấp các sự kiện như `ConnectionBlockedEvent` và `ConnectionUnblockedEvent` ở những phiên bản hỗ trợ.

Nếu publisher và consumer dùng cùng connection bị blocked, ứng dụng có thể gặp ảnh hưởng dây chuyền; cân nhắc tách connection publish/consume theo hướng dẫn framework và mức đảm bảo giao dịch. Đừng coi mọi publish delay là “heartbeat quá cao” rồi hạ timeout để chữa một broker memory alarm.

## 10. Bảng chẩn đoán các lỗi thường gặp

| Dấu hiệu | Giả thuyết chính | Cách kiểm chứng |
|---|---|---|
| `Connection refused` hoặc connect timeout | Host/port sai, broker down, network/firewall không thông | Kiểm tra endpoint, DNS, cổng, broker logs và connection timeout |
| Socket nối nhưng handshake thất bại | TLS/AMQP handshake, xác thực, virtual host, timeout | So log broker/client, TLS config, quyền/vhost và handshake |
| Connection thường xuyên đóng vì missed heartbeat | Mạng bất ổn, timeout quá thấp, CPU/I/O stall, proxy | Đọc log hai phía, negotiated heartbeat, network metrics |
| Consumer còn đăng ký nhưng xử lý chậm | Executor thiếu thread, listener blocking, prefetch, downstream chậm | Thread dump, executor metrics, queue ready/unacked |
| `AmqpTimeoutException` lúc lấy channel | Bật checkout timeout nhưng channel cache/limit không đủ | Kiểm tra in-use/idle channel, checkout timeout, concurrency |
| Channel RPC timeout | Broker không phản hồi một operation cần response kịp thời | Đọc operation đang chờ, broker load và client timeout |
| Request/reply timeout | Consumer/RPC responder không trả kết quả đúng hạn | Đối chiếu replyTo/correlationId, consumer log và reply timeout |
| `404 NOT_FOUND`, channel bị đóng | Exchange/queue không tồn tại cho operation | Xem tên resource, vhost, topology declaration; không tăng heartbeat |
| `406 PRECONDITION_FAILED` | Khai báo queue/exchange không tương thích | So durable/type/arguments thực tế; chuẩn bị migration |
| Management UI khó biết connection thuộc service nào | Thiếu connection name strategy hoặc naming kém | Đặt connection name dễ đọc; đối chiếu tên sau reconnect |
| Tăng thread pool nhưng queue không giảm | Bottleneck là database, downstream, broker flow control hoặc logic | Đo end-to-end throughput, ack latency và tài nguyên |

Một lỗi log như “Consumer raised exception” còn cần kiểm tra **body, converter, business exception và chính sách ack/requeue**; không phải lỗi executor hoặc heartbeat chỉ vì listener dừng xử lý được message.

### Một thứ tự chẩn đoán có thể lặp lại

1. Đọc log ứng dụng và RabbitMQ theo **cùng khoảng thời gian**, tìm lỗi connection/channel, blocked/unblocked và listener.
2. Trong Management UI đúng virtual host, kiểm tra connection name, negotiated heartbeat, số channel và consumer.
3. Xác nhận chính xác **container type** (simple/direct), concurrency, executor đang chạy và tình trạng thread.
4. Chỉ ra **timeout nào đã hết**: connect, handshake, channel RPC, checkout hay reply; xác định điểm thao tác đã chờ.
5. Đối chiếu queue ready/unacked, publisher confirms, retry/DLQ, broker alarms và network proxy.
6. Thay một cấu hình ở môi trường test, đo hành vi trước/sau; tránh chỉnh đồng thời heartbeat, executor và tất cả timeout vì sẽ không biết tác nhân chính.

## 11. Bài thực hành A — Đọc connection và channel trong RabbitMQ

**Mục tiêu:** chứng minh nhiều channel có thể nằm trên cùng connection và tên connection dùng để nhận diện service.

1. Tạo ứng dụng Spring AMQP có một `RabbitTemplate` và ít nhất một `@RabbitListener` trên queue test đã được khai báo.
2. Thiết lập `ConnectionNameStrategy` để connection mang nhãn như `orders-service/lab/instance-1`.
3. Publish một vài message rồi mở RabbitMQ Management UI tại đúng vhost.
4. Quan sát số **Connections** và **Channels**. Xác định channel của publisher/consumer nếu broker/UI hiển thị đủ thông tin.
5. So sánh kết quả với giả thuyết sai: “mỗi lần gửi message thì tạo một connection mới”.

**Kết quả mong đợi:** ứng dụng dùng connection được cache theo thiết kế, các thao tác có thể tạo/tái dùng channel. Connection name giúp nhận diện service, nhưng không phải ID socket duy nhất.

## 12. Bài thực hành B — Quan sát heartbeat và reconnect

**Mục tiêu:** hiểu thời điểm mất connection được phát hiện và phân biệt nó với xử lý message lỗi.

1. Dùng RabbitMQ và ứng dụng trong môi trường test; bật log connection/recovery ở mức thích hợp.
2. Đặt requested heartbeat phù hợp, ví dụ `20s`, rồi kiểm tra **giá trị negotiated thực tế** tại broker.
3. Đảm bảo listener đang consume từ queue bền vững, gửi message có messageId rõ ràng.
4. Mô phỏng **gián đoạn mạng hoặc broker restart** trong môi trường có thể khôi phục; ghi thời điểm log connection lost, reconnect và listener active trở lại.
5. Gửi message khi connection mất và kiểm tra trạng thái confirm/publish, không suy `convertAndSend` “thành công” từ việc chưa thấy exception ngay.
6. Quan sát message chưa ack có redeliver không; xác minh xử lý idempotent.

**Lưu ý:** không thực hiện gián đoạn trên production hoặc broker dùng chung không được phép thử. Heartbeat giúp phát hiện lỗi connection, nhưng không bảo đảm ứng dụng tự xử lý lại mọi business operation.

## 13. Bài thực hành C — Nhận diện executor và các loại timeout

### 13.1. Executor

Tạo một `SimpleRabbitListenerContainerFactory` có concurrency 4 và executor `orders-listener-`. Log `Thread.currentThread().getName()` trong listener để xác nhận thread thật sự chạy logic. Chuyển sang DMLC trong môi trường test và quan sát thread name khác đi; khi ấy cần xem **client dispatch executor**, không suy pool SMLC còn điều khiển callback theo cùng cách.

Đừng chỉ quan sát tên thread mà kết luận throughput: cần đo task queue, active threads, message latency và downstream wait.

### 13.2. Timeout

| Phép thử | Tác động dự kiến | Điều cần quan sát |
|---|---|---|
| Chỉ sai host/port | Không lập được kết nối; connect timeout/refused | Lỗi kết nối, **không** phải reply timeout |
| Channel checkout timeout nhỏ, giới hạn channel quá thấp | Người gọi có thể chờ channel và hết hạn | `AmqpTimeoutException`/metric cache và concurrency |
| RPC responder cố ý chậm hơn `reply-timeout` | Người gọi request/reply có thể timeout | Business reply chưa đến, dù publish có thể được confirm |
| Consumer xử lý rất chậm | Queue/unacked tăng, listener vẫn đang chạy | Thread dump, business latency, không tự coi connection đã chết |
| Chặn đường mạng test | Heartbeat/network phát hiện peer chết | Log reconnect và negotiated heartbeat |

Thực hiện các phép thử độc lập, mỗi lần chỉ đổi điều kiện cần quan sát. Với timeout ứng dụng, đưa giá trị về cấu hình phù hợp ngay sau thử nghiệm.

## 14. Bài tập tự kiểm tra

### Bài 1 — Cache và channel

`channelCacheSize=10` nhưng `channelCheckoutTimeout=0`. Có phải hệ thống **không bao giờ** tạo hơn 10 channel đồng thời?

**Đáp án:** không. Trong chế độ cache channel thường gặp, size là số channel **có thể giữ để tái sử dụng**, không tự là giới hạn cứng khi checkout timeout bằng 0. Cần quan sát broker channel max và cấu hình factory.

### Bài 2 — SMLC và DMLC

Bạn chuyển listener từ SMLC sang DMLC. Listener xử lý chậm dù tăng `taskExecutor` của container. Cần kiểm tra executor nào trước?

**Đáp án:** executor của RabbitMQ client phục vụ callback delivery, vì DMLC gọi listener trực tiếp trên client thread. Đồng thời kiểm tra business blocking và concurrency.

### Bài 3 — Heartbeat negotiation

Broker đề xuất 60 giây, client yêu cầu 20 giây. Giá trị nào được sử dụng? Nếu client yêu cầu 0, có tắt heartbeat được không?

**Đáp án:** thường thương lượng 20 giây khi cả hai khác 0; yêu cầu 0 trong khi broker đề xuất 60 **không** tắt heartbeat. Muốn tắt, cả hai phía phải cùng 0; điều này không được khuyến khích trong vận hành thông thường.

### Bài 4 — Phân biệt timeout

`RabbitTemplate.convertSendAndReceive(...)` publish được request, nhưng đối tác không trả reply trong 3 giây. Bạn phải xem `connection-timeout` hay `reply-timeout`?

**Đáp án:** `reply-timeout` phản ánh chờ response nghiệp vụ. Connection timeout chỉ liên quan giai đoạn tạo socket; publish thành công không có nghĩa sẽ có reply.

### Bài 5 — Connection name có duy nhất không?

Hai replica cùng đặt `connection_name=orders-service`. Có thể dùng chuỗi này làm khóa để đóng chính xác một connection qua RabbitMQ HTTP API không?

**Đáp án:** không. Đây là nhãn hiển thị, không phải định danh connection duy nhất; cần dùng định danh broker/API phù hợp, và nên bổ sung instance/role để quan sát rõ hơn.

### Bài 6 — Mất kết nối lúc chờ confirm

Producer gửi message, connection mất ngay trước khi nhận publisher confirm. Sau reconnect có thể gửi lại ngay mà chắc chắn không gây trùng không?

**Đáp án:** không thể khẳng định. Broker có thể đã chấp nhận message nhưng confirm chưa tới producer. Cần outbox/publish state và consumer idempotency để xử lý trạng thái không chắc chắn.

### Bài 7 — Thread pool thiếu hay broker chậm?

Queue backlog tăng nhưng RabbitMQ Management UI thấy connection vẫn hoạt động, heartbeat bình thường. Hãy nêu ít nhất ba khả năng.

**Gợi ý:** listener blocking database/API; executor thiếu thread; prefetch/concurrency không phù hợp; broker flow control; message xử lý lỗi và requeue. Heartbeat tốt không chứng minh nghiệp vụ khỏe.

## 15. Checklist trước khi triển khai

- [ ] Xác định đúng Spring Boot/Spring AMQP/RabbitMQ Java client version và loại listener container.
- [ ] Dùng connection lâu dài thông qua connection factory, tránh mở connection cho mỗi publish.
- [ ] Theo dõi số connection/channel, cache channel và giới hạn channel của broker.
- [ ] Phân biệt RabbitMQ **client executor** với **listener task executor**; cấp đủ thread phù hợp concurrency và mô hình SMLC/DMLC.
- [ ] Đặt tên thread dễ đọc để đối chiếu log và thread dump.
- [ ] Chọn heartbeat theo điều kiện mạng và negotiated value thực tế; tránh giá trị quá thấp/tắt tùy tiện.
- [ ] Kiểm tra load balancer, proxy, NAT và TCP keepalive khi connection nhàn rỗi bị đóng.
- [ ] Phân biệt connect timeout, handshake timeout, channel RPC timeout, channel checkout timeout và reply timeout.
- [ ] Nếu bật channel checkout timeout, hiểu tác động biến cache size thành giới hạn sử dụng.
- [ ] Cấp `ConnectionNameStrategy` mang application/environment/instance/role, không chứa secrets và không dùng làm ID duy nhất.
- [ ] Quan sát broker blocked/unblocked, listener latency, queue ready/unacked và connection recovery.
- [ ] Test broker restart/mất mạng, publish chưa confirm, consumer redelivery; đảm bảo cơ chế retry và idempotency phù hợp.
- [ ] Nếu tự tạo `CachingConnectionFactory`, xác minh đầy đủ TLS, credentials, cluster addresses, confirms/returns và shutdown executor.

## 16. Nguồn tra cứu chính thức

Các nguồn sau hữu ích khi cấu hình; hãy chọn đúng nhánh/version mà ứng dụng đang sử dụng:

- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): connection factory, channel cache, connection naming và recovery.
- [Spring AMQP — Threading and Asynchronous Consumers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/threading.html): phân vai client executor và listener task executor.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): concurrency, task executor, timeout và các thuộc tính container.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/3.4/reference/messaging/amqp.html): auto-configuration và `spring.rabbitmq.*` trên nhánh Boot 3.4.
- [Spring Boot 3.4 — Application Properties](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html): tên và ý nghĩa các property tương ứng.
- [RabbitMQ — Heartbeats](https://www.rabbitmq.com/docs/heartbeats): negotiated timeout, frame interval và network failure.
- [RabbitMQ — Java Client API Guide](https://www.rabbitmq.com/client-libraries/java-api-guide): connection/channel lifecycle, threading và recovery.
- [RabbitMQ — Limits and Timeouts](https://www.rabbitmq.com/docs/limits): timeout/giới hạn phía broker.

**Ghi nhớ:** **Executor** quyết định các tác vụ callback và listener được chạy trên thread nào; **heartbeat** giúp phát hiện peer kết nối không phản hồi; **timeout** giới hạn thời gian đợi ở từng thao tác cụ thể; **connection name** giúp vận hành nhận diện connection. Bốn yếu tố này bổ sung cho nhau nhưng không thay thế routing, publisher confirm, consumer acknowledgement hay xử lý idempotent. Hiểu đúng ranh giới giúp bạn chẩn đoán sự cố Spring AMQP nhanh hơn và vận hành hệ thống RabbitMQ an toàn, có thể quan sát.
