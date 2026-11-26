# channelTransacted và giao dịch AMQP cục bộ

Khi tích hợp RabbitMQ với **Spring AMQP**, một ứng dụng có thể cần gửi nhiều message có liên quan hoặc chỉ xác nhận (ACK) message đầu vào sau khi xử lý hoàn tất. Thuộc tính `channelTransacted` của `RabbitTemplate` và listener container cho phép Spring sử dụng **AMQP transactional channel**, thực hiện `tx.commit` hoặc `tx.rollback` khi kết thúc công việc.

Tuy nhiên, **giao dịch AMQP cục bộ không tương đương transaction ACID của cơ sở dữ liệu**. Nó hoạt động trên một AMQP channel, không tự bao trùm bảng SQL, các channel khác, tác vụ chạy ở thread khác, và RabbitMQ không bảo đảm tính nguyên tử tuyệt đối ngay cả khi sự cố broker xảy ra giữa `tx.commit`. Hiểu đúng phạm vi này giúp tránh mất message, ACK nhầm và xử lý nghiệp vụ trùng khi xây hệ thống bất đồng bộ đáng tin cậy.

Bài thuộc chương **Giao dịch** của module **SPRING_AMQP**: kết hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, cơ chế ACK/NACK, retry, dead-letter và các cách quan sát hành vi trong lúc thành công hoặc lỗi.

## 1. Giao dịch AMQP cục bộ là gì?

### 1.1. Một transaction gắn với một channel

AMQP 0-9-1 có nhóm lệnh `tx`:

| Lệnh | Ý nghĩa |
|---|---|
| `tx.select` | Đưa **channel hiện tại** vào chế độ giao dịch. Broker phản hồi `tx.select-ok`. |
| `basic.publish` | Publish message trên channel đó; hiệu ứng thuộc transaction cho đến lúc commit. |
| `basic.ack`, `basic.reject` | Xác nhận hoặc từ chối delivery; RabbitMQ cho phép xử lý các thao tác này trong transaction. |
| `tx.commit` | Yêu cầu broker commit các thao tác của transaction hiện tại; broker trả `tx.commit-ok`. |
| `tx.rollback` | Hủy các thao tác chưa commit thuộc transaction hiện tại; broker trả `tx.rollback-ok`. |

Sơ đồ một lượt gửi:

```text
Ứng dụng                       RabbitMQ
    |                             |
    | ------- tx.select --------> |
    | <----- tx.select-ok ------- |
    |                             |
    | ------ basic.publish -----> |  chưa coi như đã commit
    | ------ basic.publish -----> |
    |                             |
    | ------- tx.commit --------> |
    | <------ tx.commit-ok ------ |
    |                             |
    |        transaction mới      |
```

Một channel đi vào tx mode vẫn giữ chế độ đó sau `tx.commit`; những thao tác tiếp theo thuộc transaction kế tiếp. Tương tự, `tx.rollback` kết thúc transaction đang có và channel tiếp tục ở chế độ giao dịch.

**Phạm vi quan trọng:** transaction được tạo theo **channel**, không theo connection, exchange, queue hay toàn bộ ứng dụng. Hai channel trên cùng connection không mặc nhiên chia sẻ một transaction.

### 1.2. Giao dịch bao gồm và không bao gồm điều gì?

| Hoạt động | Thuộc AMQP transaction? | Ghi chú |
|---|---|---|
| Publish message bằng `basic.publish` | Có | Commit/rollback áp dụng trong phạm vi channel. |
| ACK delivery bằng `basic.ack` | Có | Phần ACK được commit/rollback; việc broker đã gửi delivery là chuyện khác. |
| Reject delivery bằng `basic.reject` | Có trong RabbitMQ hiện đại | Requeue/DLX vẫn phụ thuộc cờ reject và cấu hình broker. |
| Nhận delivery hoặc `basic.get` | **Không** | Rollback không tự động “hoàn tác việc nhận”. |
| Tạo/xóa exchange, queue, binding | **Không** | Khai báo topology phải được quản lý độc lập. |
| Ghi SQL, gọi HTTP, ghi filesystem | **Không** | Đây là tài nguyên ngoài RabbitMQ channel. |
| Publish từ channel khác | **Không** | Mỗi channel có transaction riêng. |

Cần đặc biệt chú ý nhận message: một `tx.rollback` thuần AMQP **không tự requeue delivery vừa nhận**. Khi listener của Spring AMQP lỗi, framework kết hợp rollback với thao tác **reject/requeue** riêng dựa trên cấu hình container. Vì vậy không thể giải thích redelivery chỉ bằng câu “rollback thì message tự quay lại queue”.

### 1.3. Mức bảo đảm thực tế của RabbitMQ

RabbitMQ xem các AMQP transaction gần với cơ chế gom nhóm publish/ack hơn là một transaction ACID của database. Theo broker semantics:

- `tx.commit-ok` đối với publish cho biết broker đã nhận trách nhiệm và hiệu ứng transaction đã có thể quan sát được.
- Trong lúc broker gặp lỗi khi commit, RabbitMQ **không bảo đảm atomicity** theo nghĩa “tất cả hoặc không có gì”, kể cả khi publish tới một queue; khi ảnh hưởng nhiều queue, nguy cơ một phần hiệu ứng được ghi nhận càng đáng chú ý.
- ACK đã nằm trong một transaction được commit vẫn không chứng minh nghiệp vụ ở consumer đích đã chạy, và sự cố broker về sau vẫn có thể dẫn tới redelivery.
- Lỗi routing, exchange không tồn tại và thay đổi topology có những quy tắc độc lập; transaction không bảo đảm một message luôn đến queue mong muốn.

Vì thế, có thể diễn giải **rollback khi ứng dụng ném exception** là kết quả *mong đợi trong điều kiện broker hoạt động bình thường*, không suy rộng thành cam kết tuyệt đối khi mất kết nối, broker crash hoặc nhiều tài nguyên cùng tham gia.

## 2. channelTransacted trong Spring AMQP

Spring hỗ trợ AMQP transaction trên hai thành phần thường dùng:

- **`RabbitTemplate`:** `setChannelTransacted(true)` yêu cầu các thao tác gửi/nhận qua template dùng transactional channel. Nếu không có transaction Spring đang hoạt động, từng thao tác template thường tự hoàn tất bằng commit hoặc rollback.
- **Listener container:** `setChannelTransacted(true)` khiến container dùng transactional channel trong quá trình tiêu thụ, ACK/reject và kết thúc xử lý listener.

Mặc định `channelTransacted` là **`false`**. Đặt thuộc tính này là quyết định cấu hình lúc khởi tạo component; việc một service method có `@Transactional` **không tự bật** AMQP transaction nếu `channelTransacted=false`.

### 2.1. Bảng so sánh

| Thành phần | `channelTransacted=false` | `channelTransacted=true` |
|---|---|---|
| `RabbitTemplate` publish | Publish không dùng AMQP tx | Publish nằm trong AMQP tx; commit/rollback khi kết thúc giao dịch |
| `RabbitTemplate` có nhiều lệnh liên tiếp | Các lệnh không nhóm trong một AMQP tx | **Chỉ nhóm được** khi cùng transactional context/channel; không mặc nhiên gộp mọi lời gọi |
| Listener xử lý thành công | Container ACK theo ack mode, không có `tx.commit` | Container thực hiện ACK và commit theo vòng đời transaction |
| Listener ném exception | Container reject/requeue theo chính sách lỗi | Container rollback và xử lý reject/requeue theo chính sách lỗi |
| Spring DB transaction | Độc lập với thao tác AMQP | Có thể đồng bộ commit/rollback AMQP với transaction ngoài, nhưng **không phải XA** |

**Một chi tiết dễ bỏ qua:** `channelTransacted=true` trên `RabbitTemplate` là điều kiện cần để có AMQP transaction, nhưng **chưa đủ** để hai lời gọi `convertAndSend(...)` ở hai dòng tự động có cùng transaction. Muốn nhóm nhiều thao tác một cách rõ ràng, cần đặt chúng trong transaction phù hợp, ví dụ `RabbitTransactionManager`.

## 3. Thực hành với RabbitTemplate: giao dịch publish cục bộ

Ta xây ví dụ publish hai sự kiện về một đơn hàng. Cả hai cùng định tuyến tới một queue để quan sát dễ dàng. Những phần này sử dụng Spring Boot, Spring AMQP và Java; ví dụ giả định RabbitMQ đang chạy và ứng dụng có quyền khai báo topology.

### 3.1. Khai báo exchange, queue, binding và template

```java
@Configuration
public class OrderPublishTxConfiguration {

    @Bean
    Declarables orderEventTopology() {
        DirectExchange exchange = new DirectExchange("orders.events");
        Queue queue = QueueBuilder.durable("orders.events.queue").build();

        return new Declarables(
                exchange,
                queue,
                BindingBuilder.bind(queue)
                        .to(exchange).with("orders.created"),
                BindingBuilder.bind(queue)
                        .to(exchange).with("orders.audited")
        );
    }

    @Bean("txRabbitTemplate")
    RabbitTemplate txRabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setChannelTransacted(true);
        return template;
    }

    @Bean("rabbitTransactionManager")
    RabbitTransactionManager rabbitTransactionManager(
            ConnectionFactory connectionFactory) {
        return new RabbitTransactionManager(connectionFactory);
    }
}
```

Các import tiêu biểu:

```java
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.transaction.RabbitTransactionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
```

Ở đây `orders.events` là direct exchange, còn `orders.events.queue` là durable queue có hai binding. Khi triển khai, các bean khai báo topology và transaction nên được đặt trong cấu hình quản lý rõ ràng. **Khai báo exchange/queue/binding không thuộc AMQP transaction** và không tự bị rollback cùng một lệnh publish.

`RabbitTransactionManager` sử dụng một `ConnectionFactory` RabbitMQ; template và manager phải tham chiếu cùng factory để template nhận đúng Rabbit channel gắn với transaction.

### 3.2. Nhóm hai lần publish vào cùng một transaction

```java
@Service
public class OrderEventPublisher {

    private final RabbitTemplate txRabbitTemplate;

    public OrderEventPublisher(
            @Qualifier("txRabbitTemplate") RabbitTemplate txRabbitTemplate) {
        this.txRabbitTemplate = txRabbitTemplate;
    }

    @Transactional(transactionManager = "rabbitTransactionManager")
    public void publishPair(String orderId, boolean failAfterFirstPublish) {
        txRabbitTemplate.convertAndSend(
                "orders.events",
                "orders.created",
                "CREATED:" + orderId);

        if (failAfterFirstPublish) {
            throw new IllegalStateException("Lỗi trước sự kiện thứ hai");
        }

        txRabbitTemplate.convertAndSend(
                "orders.events",
                "orders.audited",
                "AUDITED:" + orderId);
    }
}
```

Các import chính:

```java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
```

`@Transactional(transactionManager = "rabbitTransactionManager")` yêu cầu Spring mở transaction bằng **RabbitTransactionManager**, để hai lệnh gửi qua `txRabbitTemplate` cùng tham gia một AMQP channel/transaction gắn với thread hiện tại.

Trong điều kiện hoạt động bình thường:

- `publishPair("A001", false)`: hai lần publish được commit khi phương thức hoàn tất; queue đích nhận hai sự kiện.
- `publishPair("A002", true)`: lệnh đầu đã gửi vào transaction nhưng phương thức ném exception; transaction được rollback; không kỳ vọng có `CREATED:A002` ở queue.
- Một exception xảy ra **sau khi commit đã hoàn thành** không thể quay lại hủy transaction đó.

**Lưu ý khi gọi:** `@Transactional` dựa trên cơ chế proxy của Spring. Gọi `publishPair` từ bean khác qua Spring bean proxy; gọi `this.publishPair(...)` từ chính class thường bỏ qua transaction advice, khiến các lệnh template có thể trở thành các local transaction riêng.

### 3.3. Hai lần convertAndSend độc lập có cùng transaction không?

Xét code **không** nằm trong `@Transactional`:

```java
public void publishWithoutOuterTransaction(String orderId) {
    txRabbitTemplate.convertAndSend(
            "orders.events", "orders.created", "CREATED:" + orderId);

    // Nếu ném lỗi ở đây, publish trên có thể đã commit.
    validate(orderId);

    txRabbitTemplate.convertAndSend(
            "orders.events", "orders.audited", "AUDITED:" + orderId);
}
```

Mỗi thao tác của `RabbitTemplate` có thể mở/commit một AMQP transaction cục bộ riêng. Nếu `validate` ném exception, sự kiện thứ nhất **có thể đã được gửi thành công**. Vì vậy, `setChannelTransacted(true)` không thay thế transaction boundary có chủ đích ở phương thức dịch vụ.

Một cách khác để kiểm soát phạm vi là `TransactionTemplate` với `RabbitTransactionManager`, phù hợp khi cần quyết định chương trình thay vì annotation. Nhưng ở cả hai phương án, transaction cục bộ vẫn chỉ bao trùm RabbitMQ resources, không có DB.

## 4. channelTransacted trong @RabbitListener

### 4.1. Vòng đời một delivery

Listener container thường đặt acknowledgment mode là `AUTO`: framework ACK nếu listener thành công, hoặc reject/NACK nếu listener lỗi. Với `channelTransacted=true`, ACK/reject được xử lý cùng vòng đời AMQP transaction theo cơ chế của container.

```text
RabbitMQ                       Spring listener container
    |                                      |
    | -------- delivery M --------------> |
    |                                      v
    |                                gọi @RabbitListener
    |                                    /       \
    |                              thành công    exception
    |                                  |             |
    |                              ACK + commit   rollback
    |                                                |
    |                                           reject/requeue
    |                                                |
    |                                     theo defaultRequeueRejected
    |                                         và loại exception
```

Sơ đồ là mô tả logic: thứ tự lệnh ACK, rollback và reject do Spring container xử lý. **AMQP rollback một mình không tự đưa delivery đã nhận quay lại queue**; Spring phải chủ động giải quyết delivery lỗi bằng thao tác reject/requeue hoặc khi channel đóng.

### 4.2. Ví dụ queue nguồn và dead-letter

```java
@Configuration
@EnableRabbit
public class OrderConsumeTxConfiguration {

    @Bean
    Declarables orderWorkTopology() {
        DirectExchange input = new DirectExchange("orders.input");
        DirectExchange dlx = new DirectExchange("orders.dlx");

        Queue work = QueueBuilder.durable("orders.work")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("orders.failed")
                .build();
        Queue dead = QueueBuilder.durable("orders.dead").build();

        return new Declarables(
                input, dlx, work, dead,
                BindingBuilder.bind(work)
                        .to(input).with("orders.process"),
                BindingBuilder.bind(dead)
                        .to(dlx).with("orders.failed")
        );
    }

    @Bean("txListenerFactory")
    SimpleRabbitListenerContainerFactory txListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setChannelTransacted(true);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        return factory;
    }
}
```

Các import tiêu biểu:

```java
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
```

Chỉ thị `setDefaultRequeueRejected(false)` là lựa chọn **cố ý cho bài thực hành**, khiến message không xử lý được đi tới DLX nếu topology hợp lệ. Giá trị mặc định thường là `true`; để nguyên có thể dẫn tới vòng lặp giao lại nếu không có retry/backoff. Hệ thống thực cần phân loại lỗi nghiệp vụ và lỗi hạ tầng, thiết kế retry có giới hạn.

### 4.3. Listener có giao dịch AMQP cục bộ

```java
@Component
public class OrderWorkListener {

    @RabbitListener(
            queues = "orders.work",
            containerFactory = "txListenerFactory")
    public void process(String orderId) {
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("Mã đơn hàng rỗng");
        }

        if ("FAIL".equals(orderId)) {
            throw new IllegalStateException("Mô phỏng lỗi xử lý");
        }

        // Thay bằng logic xử lý đơn hàng thật.
        System.out.println("Processed order " + orderId);
    }
}
```

Import chính:

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
```

Gửi một message đến `orders.input` với routing key `orders.process`:

| Message | Listener | Transaction của container | Kết quả mong đợi |
|---|---|---|---|
| `"A001"` | Kết thúc bình thường | ACK và commit | Delivery rời `orders.work` |
| `"FAIL"` | Ném exception | Rollback, xử lý reject với `requeue=false` | Broker dead-letter sang `orders.dead` nếu DLX hoạt động |
| `""` | Ném lỗi kiểm tra đầu vào | Rollback, reject | Message lỗi có thể xuất hiện ở DLQ |
| Message hợp lệ nhưng broker mất kết nối lúc commit | Đã chạy logic ứng dụng | Commit outcome có thể không chắc chắn | Có thể redelivery; cần idempotency |

Cần phân biệt rằng `println`, ghi database hoặc gọi HTTP **không được rollback** chỉ vì Rabbit transaction rollback. Ví dụ chỉ minh họa vòng đời message, chưa hiện thực chính sách retry cho tác vụ thực tế.

### 4.4. Requeue và exception điều khiển

Spring AMQP dựa trên chính sách container và loại exception để quyết định reject/requeue sau lỗi:

- `defaultRequeueRejected=true`: thông thường request requeue khi listener lỗi; với lỗi lặp liên tục có thể làm hệ thống nghẽn.
- `defaultRequeueRejected=false`: thông thường reject không requeue; message có thể vào DLQ khi queue nguồn có DLX phù hợp.
- `AmqpRejectAndDontRequeueException`: yêu cầu không requeue trong các trường hợp được container xử lý, hữu ích cho lỗi payload không hợp lệ.
- `ImmediateRequeueAmqpException`: yêu cầu requeue ngay bất kể cấu hình mặc định trong đường xử lý thông thường.

Giao dịch không thay thế retry. Khi cần delay/backoff, sử dụng retry interceptor, retry queue TTL/DLX hoặc cơ chế retry do ứng dụng điều phối, kèm giới hạn số lần và observability.

Không nên gọi `channel.basicAck(...)` bằng tay trong listener đang dùng `AUTO` mà không thay đổi thiết kế acknowledgment, bởi container cũng sẽ ACK/commit delivery. ACK trùng có thể làm channel đóng với lỗi giao thức.

## 5. RabbitTransactionManager khác gì với @Transactional của database?

Spring quản lý transaction thông qua `PlatformTransactionManager`, nhưng **manager nào được sử dụng** quyết định tài nguyên nào thực sự tham gia.

| Cấu hình | Tài nguyên được quản lý | Điều không được bảo đảm |
|---|---|---|
| `RabbitTransactionManager` + `@Transactional("rabbitTransactionManager")` | RabbitMQ channel dùng bởi Spring AMQP trên cùng factory/thread | Không tự quản lý JDBC hoặc HTTP |
| `DataSourceTransactionManager` + `@Transactional("dataSourceTransactionManager")` | JDBC connection | Không tự tạo một AMQP transaction nếu `channelTransacted=false` |
| DB transaction manager + `channelTransacted=true` | Có thể đồng bộ AMQP commit/rollback với transaction ngoài | **Không phải atomic commit/XA** giữa DB và RabbitMQ |
| Không có manager ngoài, `RabbitTemplate.channelTransacted=true` | Local AMQP transaction cho thao tác template | Không tự nhóm nhiều phương thức hoặc nhiều thread |
| Listener container `channelTransacted=true` | Transaction của channel tiêu thụ | Không bao trùm tác dụng phụ của mã nghiệp vụ ngoài broker |

### 5.1. Vì sao không được mặc định gọi đây là “transaction chung”?

Ví dụ một phương thức có cả cập nhật DB và publish:

```java
@Transactional(transactionManager = "dataSourceTransactionManager")
public void approveOrder(String orderId) {
    orderRepository.markApproved(orderId);
    txRabbitTemplate.convertAndSend(
            "orders.events", "orders.created", "CREATED:" + orderId);
}
```

Giả sử `txRabbitTemplate` đã bật `channelTransacted=true`, Spring có thể đồng bộ AMQP transaction với DB transaction của **thread hiện tại**. Một lỗi nghiệp vụ trước commit có thể khiến cả hai nhánh rollback. Song vẫn có **khoảng hở giữa các bước commit**:

1. DB commit thành công.
2. Spring tiến hành hoàn tất AMQP transaction.
3. Broker hoặc kết nối lỗi trước khi AMQP commit được xác nhận.
4. DB đã thay đổi, nhưng sự kiện có thể chưa xuất hiện hoặc trạng thái publish không chắc chắn.

Mô hình này được mô tả là **Best Efforts One Phase Commit**: cố gắng đồng bộ giao dịch, nhưng không có coordinator XA bảo đảm cả hai commit hoặc cùng rollback trong mọi tình huống. Nếu cần mức an toàn nghiệp vụ cao, hãy cân nhắc **transactional outbox**: ghi bản ghi nghiệp vụ và outbox trong **một DB transaction**, rồi worker riêng publish với confirm/returns và retry; consumer vẫn phải idempotent.

Một ví dụ phối hợp listener với DB còn cần chú ý riêng: khi đặt `PlatformTransactionManager` vào listener container, framework mở transaction ngoài cho việc xử lý delivery. Nếu DB rollback, AMQP transaction cũng được xử lý rollback; nhưng rủi ro sự cố ở giai đoạn commit cuối vẫn tồn tại.

### 5.2. Phân biệt sync transaction với việc tạo thread mới

Spring transaction thường được liên kết với thread hiện tại. Đoạn code sau **không** tự chuyển Rabbit transaction sang thread mới:

```java
@Transactional(transactionManager = "rabbitTransactionManager")
public void publishAsync(String orderId) {
    CompletableFuture.runAsync(() ->
        txRabbitTemplate.convertAndSend(
            "orders.events", "orders.created", orderId));
}
```

`CompletableFuture.runAsync` có thể thực thi sau khi transaction của thread gọi đã commit; thao tác gửi từ thread khác sẽ không đương nhiên nằm trong cùng transaction. Nếu cần atomic intent giữa tác vụ nền và nghiệp vụ, cần thiết kế boundary riêng hoặc outbox; tránh giả định transaction context tự được mang sang executor.

## 6. Những lựa chọn dễ bị nhầm

### 6.1. AMQP transaction so với publisher confirms

| Tiêu chí | `channelTransacted=true` | Publisher confirms |
|---|---|---|
| Mục đích | Phối hợp commit/rollback thao tác AMQP trên channel | Nhận xác nhận broker đã xử lý publish |
| Cơ chế | `tx.select`, `tx.commit`, `tx.rollback` | `confirm.select` và các publish ACK/NACK |
| Throughput | Thường thấp hơn; commit phải chờ round-trip | Thường phù hợp cho luồng publish thông lượng cao |
| Điều khiển nhiều thao tác | Có thể nhóm trong một transaction context | Mỗi publish có kết quả xác nhận, ứng dụng quản lý trạng thái |
| Có dùng đồng thời trên cùng channel? | **Không** | **Không** |

RabbitMQ không cho một channel vừa ở chế độ giao dịch vừa ở chế độ confirms. Đừng bật mọi cơ chế xác nhận rồi giả định chúng cùng hoạt động trên một channel. Nếu dùng publisher confirms, ứng dụng thường phối hợp persistent messages, durable queues, mandatory + returns cho trường hợp unroutable, retry và idempotency.

**Transaction không xác nhận rằng business consumer đã xử lý message**. Cả `tx.commit-ok` và publisher confirm đều phản ánh mức xử lý phía broker, không phải kết quả của nghiệp vụ ở bên nhận.

### 6.2. Giao dịch so với durable message/queue

`channelTransacted` xử lý ranh giới commit/rollback, còn **durable queue**, **persistent message** và cơ chế lưu trữ của loại queue quyết định các khía cạnh độ bền khi broker restart. Tạo queue durable không làm mọi message trở thành persistent. Transaction cũng không thay thế cấu hình durability.

Nếu publish vào exchange mà không có binding đến queue nào, transaction có thể commit nhưng message vẫn **không vào queue đích**; cần kết hợp kiểm tra routing, `mandatory` và publisher returns ở các nhánh publish thích hợp.

### 6.3. Rollback có luôn khiến message vào DLQ?

Không. Có ba quyết định riêng:

1. Transaction của channel có commit hay rollback?
2. Sau lỗi listener, Spring container reject với `requeue=true` hay `false`?
3. Nếu reject không requeue, queue nguồn có DLX và binding đích đúng không?

Nếu queue nguồn không cấu hình DLX, message bị reject không requeue có thể **bị loại bỏ**. Nếu requeue, message có thể bị xử lý lặp đi lặp lại. Nếu broker gặp sự cố ở commit, có thể xảy ra redelivery hoặc kết quả không chắc chắn ngay cả khi phần code Java đã hoàn thành.

### 6.4. Bắt exception rồi không ném tiếp

```java
@RabbitListener(queues = "orders.work", containerFactory = "txListenerFactory")
public void unsafeListener(String orderId) {
    try {
        processBusiness(orderId);
    } catch (Exception ex) {
        log.error("Cannot process {}", orderId, ex);
        // Không ném tiếp!
    }
}
```

Nếu method trở về bình thường, container có thể coi delivery là thành công và ACK/commit. Transaction **không tự biết** rằng nghiệp vụ thất bại nếu exception bị nuốt. Để message retry/DLQ, hãy ném exception theo thiết kế hoặc thực hiện xử lý lỗi có chủ đích rồi đảm bảo đã hoàn tất.

### 6.5. Tốn chi phí hiệu năng

Transactions yêu cầu trao đổi với broker để hoàn tất commit/rollback; throughput thấp hơn so với publisher confirms khi cần gửi nhiều message. Đặt transaction rất lớn hoặc có I/O chậm sẽ giữ channel/tài nguyên lâu hơn. Nên đo latency publish, tốc độ commit, `messages_unacknowledged`, CPU/memory broker và redelivery trước khi áp dụng rộng.

## 7. Chọn giải pháp theo nhu cầu

| Nhu cầu | Giải pháp nên xem xét | Lý do |
|---|---|---|
| Gửi một số thao tác AMQP đồng bộ cần cùng ranh giới commit logic | `RabbitTransactionManager` và `RabbitTemplate.channelTransacted=true` | Dễ biểu đạt transaction boundary, trong giới hạn broker semantics |
| ACK message sau khi listener chạy thành công | Listener với `AcknowledgeMode.AUTO`, cân nhắc `channelTransacted=true` | Container điều khiển acknowledgment và kết thúc giao dịch |
| Publisher thông lượng cao cần biết broker đã nhận message | Publisher confirms + returns | Hiệu quả hơn AMQP transaction thường xuyên |
| Chuyển message lỗi qua DLQ | NACK/reject phù hợp + DLX | Transaction không quyết định routing lỗi |
| Cập nhật DB và bảo đảm sự kiện sẽ được phát sau commit | Transactional outbox + publisher confirms, retry | Xử lý khoảng hở giữa DB và RabbitMQ |
| Gọi HTTP đồng thời với gửi RabbitMQ | Idempotency, compensation hoặc workflow/saga | AMQP transaction không rollback cuộc gọi HTTP |
| Xử lý message trùng do redelivery | Business ID + deduplication/idempotency | Kết quả commit/ACK có thể không chắc chắn sau lỗi kết nối |

Không cần bật transactions cho mọi nơi. Hãy chỉ rõ yêu cầu thật sự là **rollback ở cấp channel**, **xác nhận publish**, hay **tính nhất quán nghiệp vụ xuyên tài nguyên**.

## 8. Bài thực hành: quan sát commit, rollback và requeue

Chuẩn bị RabbitMQ với các exchange/queue/binding như mục 3–4. Trên RabbitMQ Management UI, theo dõi số lượng `Ready`, `Unacked`, số message trong DLQ. Dùng message ID hoặc order ID riêng cho từng lần chạy.

### 8.1. Thí nghiệm 1: nhóm hai publish

1. Gọi `publishPair("TX-OK", false)` qua một Spring bean khác. Xác nhận queue `orders.events.queue` nhận hai sự kiện.
2. Gọi `publishPair("TX-FAIL", true)`. Kết quả mong đợi là method ném `IllegalStateException`; khi broker hoạt động bình thường, không có sự kiện `CREATED:TX-FAIL` được commit.
3. Bỏ `@Transactional(transactionManager = "rabbitTransactionManager")` hoặc gọi phương thức nội bộ bỏ qua proxy; lặp lại `TX-FAIL` và đối chiếu. Trong trường hợp các lệnh template độc lập, sự kiện đầu có thể đã commit trước khi lỗi xảy ra.
4. Ghi lại số message ở queue và stack trace của caller. Không tự suy rằng rollback đã xảy ra chỉ vì method Java ném exception.

### 8.2. Thí nghiệm 2: listener lỗi và dead-letter

1. Publish `"A001"` vào `orders.input` bằng routing key `orders.process`. Quan sát message được xử lý và ACK/commit.
2. Publish `"FAIL"`; listener ném exception. Với `defaultRequeueRejected=false`, broker có thể chuyển message sang `orders.dead` vì queue nguồn có DLX.
3. Thử đặt `defaultRequeueRejected=true` trong môi trường test và phát lại `"FAIL"`. Quan sát message có thể được giao lại nhiều lần; dừng thử nghiệm sớm để tránh vòng lặp nóng.
4. Dùng một message có `messageId` cố định để thử giả lập xử lý trùng: handler idempotent phải bỏ qua ID đã hoàn thành.

### 8.3. Thí nghiệm 3: sự khác nhau với DB

Trong môi trường test, thực hiện một phương thức lưu đơn hàng vào DB rồi gửi RabbitMQ trong transaction đồng bộ. Kiểm tra hai nhánh thông thường: throw trước commit và không throw. Sau đó mô phỏng broker unavailable ở giai đoạn hoàn tất để hiểu khoảng hở nhất quán. Đây là lý do cần triển khai outbox cho nghiệp vụ không được mất sự kiện.

**Các dấu hiệu cần ghi lại:** transaction manager được chọn, listener/container factory đang sử dụng, có gọi bean qua proxy không, ACK/NACK, số message redelivered, đường DLX, publish confirm/return nếu có, và business ID.

## 9. Câu hỏi tự kiểm tra

1. Khi bật `channelTransacted=true` trên `RabbitTemplate`, hai lần `convertAndSend` liên tiếp có tự thuộc cùng transaction không?
2. `tx.rollback` thuần AMQP có tự requeue message đã được broker giao cho consumer không?
3. Transaction AMQP bao gồm thao tác tạo exchange/queue hay cập nhật bảng SQL không?
4. Vì sao `@Transactional(transactionManager = "rabbitTransactionManager")` không bảo đảm rollback thay đổi JDBC?
5. Nếu DB đã commit nhưng RabbitMQ commit thất bại, mô hình đồng bộ transaction của Spring có bảo đảm all-or-nothing không?
6. Có thể bật publisher confirms và `tx.select` trên cùng AMQP channel không?
7. Vì sao message vẫn có thể được giao lại dù code listener từng chạy thành công?

**Đáp án gợi ý:** (1) không; cần chung transaction context, (2) không, Spring xử lý reject/requeue riêng, (3) không, (4) manager chỉ quản lý RabbitMQ resource, (5) không, đó là Best Efforts One Phase Commit, (6) không, (7) ACK/commit chưa chắc được broker ghi nhận hoặc broker gặp sự cố khiến message được giao lại.

## 10. Tổng kết

`channelTransacted=true` làm cho `RabbitTemplate` và listener container dùng transactional AMQP channel. Nó cho phép **commit/rollback thao tác publish và ACK/reject trên channel**, đặc biệt khi kết hợp `RabbitTransactionManager` để xác định transaction boundary của một nhóm thao tác. Trong listener, Spring phải kết hợp rollback với cơ chế reject/requeue; **rollback AMQP không tự đưa delivery đã nhận về queue**.

Giới hạn quan trọng nhất là phạm vi: **một channel RabbitMQ khác với một transaction nghiệp vụ toàn hệ thống**. AMQP transaction không bao trùm DB hay HTTP, không dùng chung channel confirm, và RabbitMQ không cung cấp atomicity ACID tuyệt đối khi có sự cố commit. Hãy dùng publisher confirms cho thông lượng cao, outbox cho tính nhất quán với database, DLX/retry để xử lý lỗi, cùng business ID/idempotency để chịu được redelivery.

### Tài liệu tham khảo

- [Spring AMQP Reference — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): `channelTransacted`, Spring transaction synchronization, `RabbitTransactionManager` và rollback của received messages.
- [RabbitMQ — Broker Semantics](https://www.rabbitmq.com/docs/semantics): phạm vi `tx`, atomicity và giới hạn trong lúc broker commit.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): tính khác biệt giữa consumer acknowledgments, publisher confirms và transactional channel.

