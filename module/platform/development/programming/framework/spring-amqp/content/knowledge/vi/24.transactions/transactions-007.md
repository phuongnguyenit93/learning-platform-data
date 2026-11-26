# alwaysRequeueWithTxManagerRollback theo cấu hình và phiên bản

## 1. Đặt vấn đề: rollback giao dịch thì message đi đâu?

Trong ứng dụng **Spring AMQP** kết nối **RabbitMQ**, một listener thường nhận message từ queue, cập nhật dữ liệu trong database, rồi trả quyền xác nhận cho container. Khi xử lý thất bại, ứng dụng có thể muốn **gửi message trở lại queue** để thử lại hoặc **không requeue** để nó đi vào dead-letter queue (DLQ), nếu DLX đã được cấu hình.

Vấn đề phức tạp hơn khi listener container tham gia một giao dịch qua **PlatformTransactionManager** bên ngoài AMQP (chẳng hạn transaction manager cho JDBC/JPA). Sau khi giao dịch rollback, Spring AMQP phải xác định điều gì xảy ra với delivery vừa nhận.

Thuộc tính **alwaysRequeueWithTxManagerRollback** trên message listener container điều khiển một trường hợp đặc biệt: **khi rollback diễn ra với một transaction manager được cấu hình cho container, có buộc message luôn được requeue hay không?**

Đây là chủ đề dễ nhầm vì **giá trị mặc định đã thay đổi từ Spring AMQP 2.0**. Đồng thời, đặt `alwaysRequeueWithTxManagerRollback=false` **không tự động có nghĩa message sẽ vào DLQ**: kết quả còn phụ thuộc `defaultRequeueRejected`, loại exception và đường định tuyến dead-letter.

Sau bài học này, bạn có thể:

- Giải thích vì sao rollback của giao dịch ứng dụng và thao tác reject/requeue của RabbitMQ là hai khái niệm liên quan nhưng khác nhau.
- Phân biệt hành vi mặc định của `alwaysRequeueWithTxManagerRollback` giữa các phiên bản Spring AMQP.
- Cấu hình transaction manager, `channelTransacted`, `defaultRequeueRejected` và `alwaysRequeueWithTxManagerRollback` đúng vị trí.
- Xác định message được requeue hay reject trong các kịch bản lỗi, đồng thời tránh vòng lặp retry vô hạn.
- Kiểm chứng hành vi với exchange, queue, binding, DLX, `RabbitTemplate` và `@RabbitListener`.

## 2. Cơ sở: giao dịch không bao trùm việc RabbitMQ đã giao message

Ví dụ consumer nhận sự kiện `order.created`:

~~~text
RabbitMQ exchange -> binding -> orders.inbox.q
                                      |
                                      v
                              Listener container
                              (transaction manager)
                                      |
                                      v
                              @RabbitListener
                              cập nhật database
                                      |
                  +-------------------+-------------------+
                  |                                       |
                SUCCESS                                  ERROR
                  |                                       |
          Commit theo cấu hình                    Rollback transaction
          + xác nhận delivery                     + xử lý từ chối delivery
                                                          |
                                         +----------------+----------------+
                                         |                                 |
                                       requeue                     reject, no requeue
                                         |                                 |
                                    queue lại                         DLX -> DLQ
                                                            (nếu cấu hình tuyến DLX)
~~~

Giao dịch AMQP chủ yếu liên quan đến các thao tác publish và ACK với broker. **Việc broker đã gửi một delivery đến consumer không phải một phần có thể "hoàn tác" đơn giản bằng rollback transaction.** Khi listener thất bại, Spring AMQP phải phối hợp rollback với hành động từ chối message ở broker. Việc từ chối có thể kèm **requeue=true** hoặc **requeue=false**.

**Phân biệt ba tầng:**

| Tầng | Kiểm soát gì? | Điều không bảo đảm |
| --- | --- | --- |
| Database transaction manager | Commit/rollback các thay đổi trong database tương ứng. | Không tự tạo transaction XA với RabbitMQ. |
| AMQP channel transaction (`channelTransacted=true`) | Đồng bộ thao tác AMQP theo giao dịch của channel và transaction manager khi có. | Không làm việc nhận message ban đầu trở thành thao tác có thể rollback nguyên tử với database. |
| Listener container | ACK, reject hoặc requeue delivery khi xử lý thành công/lỗi. | Không bảo đảm retry đúng một lần, và không thay thế chính sách lỗi nghiệp vụ. |

Trong ứng dụng thực, lỗi có thể xảy ra sau khi database commit nhưng trước khi ACK được broker ghi nhận. Vì vậy, kể cả khi đã cấu hình transaction, hệ thống vẫn cần **idempotent consumer** để xử lý trùng một cách an toàn.

## 3. Lịch sử phiên bản: tại sao hành vi lại khác nhau?

Theo tài liệu tham chiếu và Javadoc của Spring AMQP:

| Phiên bản Spring AMQP | Hành vi với external transaction manager khi rollback | Ghi chú |
| --- | --- | --- |
| **Trước 1.7.1** | Rollback với transaction manager dẫn đến requeue theo hành vi cũ. | Chưa có setter cấu hình `alwaysRequeueWithTxManagerRollback`. |
| **1.7.1 đến 1.7.x** | Thuộc tính được đưa vào, **mặc định true** để giữ tương thích. | Có thể đặt **false** để dùng logic requeue thông thường. |
| **Từ 2.0** (bao gồm các dòng 2.x, 3.x và API 4.x được ghi nhận trong tài liệu) | **Mặc định false**. | Hành vi khi rollback thống nhất hơn giữa giao dịch local và trường hợp có transaction manager; đặt true để khôi phục cách cũ. |

Đặt `true` là một lựa chọn tương thích với hành vi cũ khi migration. Nó **không phải** tùy chọn nên bật mặc định cho mọi ứng dụng.

Nguồn chính thức:

- [Spring AMQP Reference – Transactions, mục "A note on Rollback of Received Messages"](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html).
- [Javadoc AbstractMessageListenerContainer – setAlwaysRequeueWithTxManagerRollback (Spring AMQP 3.2.5)](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/listener/AbstractMessageListenerContainer.html).
- [Spring AMQP Reference 1.7.8 – hành vi trước Spring AMQP 2.0](https://docs.spring.io/spring-amqp/docs/1.7.8.RELEASE/reference/html/_reference.html).

**Cần xác nhận phiên bản thư viện thực tế do Spring Boot quản lý**, vì việc nâng Spring Boot có thể đồng thời nâng Spring AMQP và thay đổi default. Không suy ra default chỉ từ phiên bản RabbitMQ: thuộc tính này nằm ở **Spring listener container**, không phải một RabbitMQ server setting.

## 4. Hai thuộc tính quan trọng nhất và bảng quyết định

### 4.1. alwaysRequeueWithTxManagerRollback

- **true:** trong tình huống container dùng external transaction manager và giao dịch rollback, Spring AMQP **luôn yêu cầu requeue**, ngay cả khi thiết lập từ chối thông thường muốn không requeue.
- **false:** khi rollback, Spring AMQP áp dụng cơ chế quyết định requeue **thông thường** dựa trên `defaultRequeueRejected` và một số exception đặc biệt.
- **Không có transaction manager gắn vào container:** nhánh logic "with TxManager rollback" không phải tình huống đang xét; bật cờ này không tạo ra giao dịch.

### 4.2. defaultRequeueRejected

`defaultRequeueRejected` mặc định **true** trong cấu hình listener container thường dùng. Khi listener gặp exception và container từ chối message:

- **true:** lỗi thông thường dẫn tới **requeue**.
- **false:** lỗi thông thường dẫn tới **không requeue**; nếu queue có dead-letter exchange phù hợp, RabbitMQ có thể chuyển message đến DLQ.
- **AmqpRejectAndDontRequeueException:** trong logic requeue thông thường, đây là tín hiệu **không requeue**, kể cả khi default là true.
- **ImmediateRequeueAmqpException** (có từ Spring AMQP 2.1): trong logic thông thường, đây là tín hiệu **requeue**, kể cả khi default là false.

### 4.3. Bảng quyết định dành cho rollback có transaction manager

Giả sử listener ném exception khiến **giao dịch thật sự rollback**, exception không bị một bộ xử lý lỗi tùy chỉnh nuốt mất:

| alwaysRequeueWithTxManagerRollback | defaultRequeueRejected | Exception minh họa | Kết quả trong trường hợp rollback đang xét |
| --- | --- | --- | --- |
| **true** | false | `IllegalStateException` | **Requeue**, vì bật hành vi luôn requeue. |
| **true** | true | `IllegalStateException` | **Requeue**. |
| **true** | false | `AmqpRejectAndDontRequeueException` | **Requeue** theo hành vi override tương thích cũ; không dùng cơ chế này để bảo đảm tới DLQ. |
| **false** | true | `IllegalStateException` | **Requeue** do defaultRequeueRejected=true. |
| **false** | false | `IllegalStateException` | **Reject, không requeue**; vào DLQ nếu có binding DLX đúng. |
| **false** | true | `AmqpRejectAndDontRequeueException` | **Reject, không requeue** theo exception đặc biệt. |
| **false** | false | `ImmediateRequeueAmqpException` (2.1+) | **Requeue** theo exception đặc biệt. |

Bảng trên mô tả nhánh lỗi/rollback tiêu chuẩn của listener container. Nếu có **retry interceptor**, error handler, rollback rule riêng, thao tác ACK thủ công hoặc sự cố kết nối, điểm ra quyết định thực tế có thể khác; hãy kiểm chứng theo cấu hình cụ thể.

Một sai lầm phổ biến là nhìn thấy `alwaysRequeueWithTxManagerRollback=false` rồi kết luận "rollback luôn đẩy sang DLQ". **Sai:** với `defaultRequeueRejected=true`, exception thông thường vẫn requeue.

## 5. Ví dụ thực hành: có database transaction và DLQ

Ta xây một luồng giả lập xử lý đơn hàng:

~~~text
RabbitTemplate
    |
    v
exchange orders.events.x
    | routing key: order.created
    v
queue orders.process.q
    |    DLX: orders.dead.x
    |    DL routing key: order.failed
    v
@RabbitListener trong transaction
    |
    +--> commit thành công -> ACK
    |
    +--> rollback + requeue=true -> trở lại orders.process.q
    |
    +--> rollback + requeue=false -> exchange orders.dead.x
                                              |
                                              v
                                         orders.dead.q
~~~

### 5.1. Dependency

Ví dụ dùng Spring Boot với **Spring AMQP** và transaction manager cho JDBC:

~~~xml
<!-- Maven: đặt trong mục dependencies của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
~~~

Để chạy phần JDBC, ứng dụng phải có **DataSource và driver database** (H2, PostgreSQL, MySQL...), cùng schema tương ứng. Đoạn mã dưới minh họa cách nối listener vào transaction manager; các câu truy vấn/DAO nghiệp vụ cần được xây dựng phù hợp với database đã chọn.

### 5.2. Khai báo exchange, queue, binding và DLX

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderMessagingTopology {
    public static final String EVENTS_EXCHANGE = "orders.events.x";
    public static final String WORK_QUEUE = "orders.process.q";
    public static final String ROUTING_KEY = "order.created";
    public static final String DEAD_EXCHANGE = "orders.dead.x";
    public static final String DEAD_QUEUE = "orders.dead.q";
    public static final String DEAD_ROUTING_KEY = "order.failed";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    Queue ordersWorkQueue() {
        return QueueBuilder.durable(WORK_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING_KEY)
                .build();
    }

    @Bean
    Queue ordersDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    Binding ordersWorkBinding(Queue ordersWorkQueue,
                              DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersWorkQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    Binding ordersDeadBinding(Queue ordersDeadQueue,
                              DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersDeadQueue)
                .to(ordersDeadExchange)
                .with(DEAD_ROUTING_KEY);
    }
}
~~~

Đặt DLX trên queue để RabbitMQ có đường đi khi một delivery được reject mà **không requeue**. Trong hệ thống thật có thể dùng **RabbitMQ policy** để quản lý DLX thay cho hard-code queue arguments; việc thay đổi queue arguments đã tồn tại có thể cần migration, không tự sửa topology production.

### 5.3. Gắn transaction manager và thuộc tính rollback vào listener

Phương thức `setAlwaysRequeueWithTxManagerRollback(boolean)` thuộc **AbstractMessageListenerContainer**. Khi tạo container bằng **SimpleRabbitListenerContainerFactory**, cấu hình thuộc tính này lên container bằng **setContainerCustomizer(...)** (API có từ Spring AMQP 2.2.2). Trên các dòng cũ không hỗ trợ customizer, cấu hình trực tiếp trên container được khởi tạo thủ công.

~~~java
import javax.sql.DataSource;

import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class TransactionalListenerConfig {

    @Bean("ordersDbTransactionManager")
    PlatformTransactionManager ordersDbTransactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("ordersTransactionalListenerFactory")
    SimpleRabbitListenerContainerFactory ordersTransactionalListenerFactory(
            ConnectionFactory connectionFactory,
            @Qualifier("ordersDbTransactionManager")
            PlatformTransactionManager dbTransactionManager) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);

        // Dùng AMQP channel transaction cho các thao tác AMQP.
        factory.setChannelTransacted(true);

        // Transaction manager bên ngoài dành cho dữ liệu JDBC.
        factory.setTransactionManager(dbTransactionManager);

        // Lỗi thông thường sau rollback: không requeue -> DLX.
        factory.setDefaultRequeueRejected(false);

        // Từ Spring AMQP 2.0, giá trị mặc định đã là false.
        // Đặt tường minh để giữ ý định rõ ràng khi cấu hình.
        factory.setContainerCustomizer(container ->
                container.setAlwaysRequeueWithTxManagerRollback(false));

        return factory;
    }
}
~~~

**Vì sao phải set trên container?** `SimpleRabbitListenerContainerFactory` trực tiếp cung cấp các setter như `setTransactionManager`, `setChannelTransacted`, `setDefaultRequeueRejected`. Riêng `setAlwaysRequeueWithTxManagerRollback` là setter của container, nên có thể dùng customizer để thay đổi nó sau khi factory tạo container. Không gọi một setter không tồn tại trên factory.

**Giới hạn:** phối hợp một JDBC transaction manager với channel transaction **không phải distributed XA/2PC**. Nếu ứng dụng bắt buộc không mất/chưa phát trùng sự kiện qua DB và broker khi một thành phần chết, hãy cân nhắc transactional outbox, idempotency và cơ chế phục hồi rõ ràng.

### 5.4. Listener và producer minh họa

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @RabbitListener(
        queues = OrderMessagingTopology.WORK_QUEUE,
        containerFactory = "ordersTransactionalListenerFactory"
    )
    public void onOrderCreated(String orderId) {
        // Thay bằng thao tác JDBC/Repository thật khi thực hành.
        // Trường hợp này mô phỏng lỗi khiến transaction rollback.
        if (orderId.startsWith("BROKEN-")) {
            throw new IllegalStateException("Simulated processing failure");
        }

        // Ví dụ thực tế: ghi DB trong transaction container đã mở,
        // dùng orderId/eventId làm khóa idempotency.
        System.out.println("Processed order: " + orderId);
    }
}
~~~

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderCreatedPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderCreatedPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String orderId) {
        rabbitTemplate.convertAndSend(
                OrderMessagingTopology.EVENTS_EXCHANGE,
                OrderMessagingTopology.ROUTING_KEY,
                orderId);
    }
}
~~~

Chạy ví dụ với `publish("ORDER-100")`: listener kết thúc bình thường, container xử lý commit và xác nhận delivery theo cấu hình. Gửi `publish("BROKEN-100")`: listener ném exception, giao dịch rollback. Vì ví dụ đặt **alwaysRequeueWithTxManagerRollback=false** và **defaultRequeueRejected=false**, delivery bị reject không requeue và có thể được đưa qua DLX tới `orders.dead.q`.

Đoạn listener trên chủ động chỉ mô phỏng lỗi, **chưa thực hiện SQL**; muốn kiểm tra rollback database, cần thêm DAO thao tác DB trong transaction và quan sát dữ liệu sau khi exception. Không suy luận DB đã rollback chỉ bằng việc message xuất hiện ở DLQ.

## 6. Thử nghiệm thay đổi cờ với cùng một message lỗi

Để thấy tác dụng của `alwaysRequeueWithTxManagerRollback`, giữ nguyên:

- External transaction manager đã gắn vào container.
- `channelTransacted=true`.
- Queue có DLX và binding đúng.
- `defaultRequeueRejected=false`.
- Listener luôn ném `IllegalStateException` cho message `BROKEN-100`.

Sau đó **thay đổi chỉ một dòng** tại customizer:

~~~java
// Cấu hình A: hành vi hiện đại, tôn trọng defaultRequeueRejected.
container.setAlwaysRequeueWithTxManagerRollback(false);

// Cấu hình B: tương thích hành vi cũ, luôn requeue khi rollback
// với external transaction manager.
container.setAlwaysRequeueWithTxManagerRollback(true);
~~~

| Cấu hình | Điều mong đợi |
| --- | --- |
| A: `false`, `defaultRequeueRejected=false` | Message lỗi không requeue; nếu DLX hoạt động, đi tới DLQ. |
| B: `true`, `defaultRequeueRejected=false` | Message lỗi requeue, có thể bị giao lại liên tục; không đến DLQ chỉ vì lỗi đó. |
| C: `false`, đổi `defaultRequeueRejected=true` | Message lỗi requeue do chính defaultRequeueRejected. |

**Cách kiểm tra:** gửi đúng một message lỗi, quan sát số lần listener nhận, số lần rollback và số message tại DLQ. Có thể đọc cờ `redelivered` của AMQP message khi được giao lại; cờ này hỗ trợ chẩn đoán nhưng không thay thế event ID hoặc bộ đếm retry nghiệp vụ.

Nếu thử B trong môi trường phát triển, phải có cách **dừng listener** hoặc giới hạn thử nghiệm để tránh hot loop. Không để một message luôn lỗi tiêu thụ CPU vô hạn trên môi trường dùng chung.

## 7. Exception đặc biệt và chỗ dễ nhầm

Giả sử business logic xác định payload không hợp lệ, và muốn **loại bỏ khỏi luồng retry tức thời**:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ValidatingOrderListener {

    @RabbitListener(
        queues = OrderMessagingTopology.WORK_QUEUE,
        containerFactory = "ordersTransactionalListenerFactory"
    )
    public void validate(String orderId) {
        if (orderId.isBlank()) {
            throw new AmqpRejectAndDontRequeueException(
                    "Order ID cannot be blank");
        }
        // Xử lý nghiệp vụ với idempotency.
    }
}
~~~

**Không bật đồng thời hai listener minh họa cho cùng một queue khi thử nghiệm**, vì chúng sẽ tranh nhận message. Dừng `OrderCreatedListener` nếu chạy `ValidatingOrderListener`.

Trong hành vi từ **Spring AMQP 2.0** với `alwaysRequeueWithTxManagerRollback=false`, loại exception này cho phép từ chối message mà không requeue, kể cả khi cấu hình mặc định muốn requeue. Ngược lại, nếu bật `alwaysRequeueWithTxManagerRollback=true` trong kịch bản rollback với transaction manager, hành vi "luôn requeue" được ưu tiên. Do đó, **không dùng cờ true nếu yêu cầu poison message phải tới DLQ theo quyết định của listener**.

Ngược lại, `ImmediateRequeueAmqpException` (Spring AMQP 2.1+) biểu thị muốn requeue kể cả khi `defaultRequeueRejected=false` trong đường xử lý từ chối thông thường. Tuy nhiên, nếu đang dùng retry interceptor, error handler, custom recoverer, hoặc rollback rules, cần xem điều gì thực sự được container ném/nhận ở cuối chuỗi xử lý.

**Đừng nhầm exception lỗi nghiệp vụ với lỗi hạ tầng:** mạng đứt, mất kết nối database, broker không sẵn sàng, JSON không giải mã được, hoặc mất queue là các nhóm lỗi cần được xử lý khác nhau. Một thông điệp hỏng định dạng có thể thất bại ở tầng converter/error handler trước khi code trong `@RabbitListener` được chạy.

## 8. Phân biệt local transaction và external transaction manager

Cùng đặt `channelTransacted=true`, nhưng hai chế độ không giống nhau:

| Chế độ | Cấu hình điển hình | Vai trò của alwaysRequeueWithTxManagerRollback |
| --- | --- | --- |
| **Local AMQP transaction** | Channel có transaction, **không gắn external PlatformTransactionManager** cho listener container. | Cờ này không phải cơ chế điều khiển chính; logic reject/requeue thông thường áp dụng. |
| **External transaction manager** | Listener container gắn `PlatformTransactionManager` (ví dụ `DataSourceTransactionManager`) cùng `channelTransacted=true`. | Cờ **true** có thể ép requeue trên rollback; **false** để logic thông thường quyết định. |
| **Không bật channelTransacted** | AMQP channel không ở chế độ giao dịch. | Không thể giả định các thao tác ACK/publish tham gia rollback giống nhánh transaction channel; phải xem cấu hình ACK và manager riêng. |

**RabbitTransactionManager** là một `PlatformTransactionManager` cho các tài nguyên RabbitMQ, không phải công cụ tự động tạo một giao dịch phân tán nguyên tử với database. Với nhiều tài nguyên, hãy hiểu cơ chế đồng bộ và thứ tự commit, kiểm thử tình huống commit một phía thành công và phía kia thất bại.

Tài liệu tham khảo: [Spring AMQP – Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html).

## 9. Retry, dead-letter và idempotency

Để xử lý bất đồng bộ đáng tin cậy, không nên dựa hoàn toàn vào requeue của broker khi rollback.

### 9.1. Vấn đề requeue vô hạn

Với message luôn lỗi:

~~~text
consumer nhận -> exception -> rollback -> requeue=true
       ^                                  |
       |__________________________________|
~~~

Vòng lặp này có thể xảy ra rất nhanh, tạo nhiều log, tăng CPU và làm chậm các message hợp lệ. `alwaysRequeueWithTxManagerRollback=true` đặc biệt nguy hiểm khi lỗi không thể tự phục hồi (payload sai schema, thiếu trường bắt buộc, không có tài nguyên tương ứng).

### 9.2. Chính sách nên cân nhắc

1. **Lỗi tạm thời:** retry có giới hạn, backoff và jitter phù hợp, có thể dùng retry interceptor hoặc queue chờ + DLX để tránh tái xử lý tức thời.
2. **Lỗi vĩnh viễn:** không requeue; dead-letter vào queue riêng để kiểm tra/sửa dữ liệu.
3. **Đủ số lần retry:** chuyển sang DLQ hoặc trạng thái thất bại lưu bền vững. Chọn recoverer phù hợp; không coi mọi lỗi đều là lỗi có thể retry.
4. **Không làm trùng hiệu ứng:** consumer dùng business ID/event ID ổn định và cơ chế idempotency, đặc biệt khi thao tác email, đơn hàng, thanh toán.
5. **Theo dõi:** đếm số lần nhận, số rollback, số redelivery, số vào DLQ, độ trễ retry và số message lỗi đang quay vòng.

**Lưu ý với retry interceptor:** lỗi đã được recoverer "nuốt" và phương thức listener trả thành công có thể dẫn đến ACK; lỗi vẫn được ném ra thì container mới đi vào đường rollback/reject tùy cấu hình. Nếu cần route sang DLQ, hãy kiểm chứng recoverer, ACK mode và cấu hình DLX cùng nhau.

## 10. Các trường hợp biên cần kiểm tra

| Hiện tượng | Điều có thể gây ra | Hướng điều tra |
| --- | --- | --- |
| Đặt `alwaysRequeueWithTxManagerRollback=false` nhưng message cứ quay lại | `defaultRequeueRejected=true`, exception yêu cầu requeue, retry advice hoặc ACK/recoverer tùy chỉnh. | Kiểm tra toàn bộ factory/container thực tế và exception cuối cùng. |
| Đặt `defaultRequeueRejected=false` nhưng message vẫn quay lại | `alwaysRequeueWithTxManagerRollback=true` khi rollback với external transaction manager. | Đọc cấu hình container, đối chiếu phiên bản; chuyển false khi muốn tôn trọng reject. |
| Message biến mất khỏi queue xử lý, không thấy trong DLQ | Chưa khai báo DLX/binding, DLX không tồn tại, hoặc consumer đã ACK/loại bỏ theo error handler. | Kiểm tra topology, broker logs, AMQP properties và policy của queue. |
| Update DB thành công nhưng message bị xử lý lại | Lỗi ở ranh giới commit/ACK, redelivery sau mất kết nối hoặc retry. | Dùng idempotency key và giao dịch DB có unique constraint khi ghi dấu. |
| Chỉ vài message bị requeue sai sau khi nâng version | Default đổi hoặc có khác biệt cấu hình giữa các listener factory. | Ghi nhận phiên bản Spring AMQP và kiểm tra mọi container bean. |
| Listener có `@Transactional` nhưng kết quả khác kỳ vọng | Annotation quản lý transaction ở mức method, container có thể đang dùng manager/ACK khác. | Xác nhận transaction manager được gắn vào container và `channelTransacted`. |

**Quan sát chi tiết:** nếu queue có dead-letter, RabbitMQ có thể thêm header `x-death` trên message được dead-letter (tùy phiên bản/protocol). Header này giúp điều tra số lần dead-letter, nhưng không thay thế một retry counter do ứng dụng kiểm soát khi message chỉ requeue qua NACK.

## 11. Bài thực hành

**Bối cảnh:** Service Xử lý Đơn hàng ghi trạng thái đơn vào database sau khi nhận sự kiện. Một số message sai định dạng hoặc luôn lỗi. Yêu cầu: message không hợp lệ đến DLQ, message hợp lệ được xử lý đúng một lần theo event ID ở mức nghiệp vụ.

**Các bước:**

1. Cấu hình Spring Boot với RabbitMQ, DataSource và schema lưu sự kiện đã xử lý; khai báo topology như mục 5.
2. Gắn `DataSourceTransactionManager` vào listener container, bật `channelTransacted=true`, đặt `defaultRequeueRejected=false` và `alwaysRequeueWithTxManagerRollback=false`.
3. Gửi `ORDER-100`; kiểm tra database ghi nhận thành công và queue xử lý được ACK.
4. Gửi `BROKEN-100`; quan sát rollback và message tới DLQ. Xác minh trong database không có thay đổi đã rollback.
5. Chỉ đổi `alwaysRequeueWithTxManagerRollback=true`, khởi động lại listener và gửi một message lỗi. Quan sát redelivery; **dừng listener sớm** để tránh vòng lặp vô hạn.
6. Giữ `alwaysRequeueWithTxManagerRollback=false`, đổi `defaultRequeueRejected=true`, lặp lại lỗi thường. Giải thích vì sao vẫn requeue.
7. Khôi phục cấu hình an toàn, ném `AmqpRejectAndDontRequeueException` cho message sai nghiệp vụ và kiểm tra DLQ.
8. Mô phỏng consumer bị dừng giữa ghi DB và ACK; kiểm tra idempotency bằng event ID và unique constraint.

### Câu hỏi tự kiểm tra

**Câu 1.** Trong Spring AMQP 3.x, `alwaysRequeueWithTxManagerRollback` mặc định là gì?

**Đáp án:** `false`. Từ phiên bản 2.0, mặc định đã chuyển sang hành vi thống nhất với logic reject/requeue thông thường.

**Câu 2.** Có external transaction manager và rollback. `alwaysRequeueWithTxManagerRollback=false` nhưng `defaultRequeueRejected=true`. Listener ném `IllegalStateException`. Message đi đâu?

**Đáp án:** Thông thường **requeue**, bởi `defaultRequeueRejected=true`; riêng cờ always=false chỉ bỏ hành vi cưỡng ép requeue.

**Câu 3.** Nếu `alwaysRequeueWithTxManagerRollback=true`, `defaultRequeueRejected=false` và listener lỗi, có thể dựa vào DLX để nhận message lỗi không?

**Đáp án:** Không nên. Trong tình huống rollback có external transaction manager đang xét, cờ true ép requeue nên message có thể quay lại queue xử lý thay vì bị reject không requeue để tới DLQ.

**Câu 4.** Khi một message xuất hiện trong DLQ, có thể kết luận database transaction đã rollback chính xác mọi thay đổi bên ngoài không?

**Đáp án:** Không. DLQ chỉ thể hiện kết quả xử lý message ở RabbitMQ. Các hệ thống lưu trữ hoặc side effect bên ngoài phải được kiểm tra theo transaction boundary và có cơ chế chống trùng/khôi phục riêng.

## 12. Ghi nhớ

**alwaysRequeueWithTxManagerRollback** là thuộc tính của **Spring AMQP listener container**, có ý nghĩa khi xử lý rollback cùng một **external transaction manager**. Trong **Spring AMQP 1.7.1–1.7.x**, giá trị mặc định là `true`; **từ 2.0 trở lên** mặc định là `false`. Để message lỗi được đưa sang DLQ, cần phối hợp `defaultRequeueRejected=false` (hoặc exception không requeue phù hợp), **DLX/queue/binding**, retry giới hạn và idempotency. Bật `true` chỉ khi thật sự cần duy trì hành vi tương thích cũ và đã kiểm soát được vòng lặp requeue.

### Tài liệu chính thức để đối chiếu khi nâng phiên bản

- [Spring AMQP Reference: Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html).
- [Spring AMQP: Resilience, Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html).
- [Javadoc: AbstractMessageListenerContainer 3.2.5](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/listener/AbstractMessageListenerContainer.html).
- [Javadoc: AbstractRabbitListenerContainerFactory 3.2.5](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/config/AbstractRabbitListenerContainerFactory.html).
