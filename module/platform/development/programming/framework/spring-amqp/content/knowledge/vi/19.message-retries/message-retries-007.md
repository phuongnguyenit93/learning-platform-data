# adviceChain và thứ tự retry so với giao dịch

Trong chương **Thử lại thông điệp** của **SPRING_AMQP**, khi **@RabbitListener** nhận message từ RabbitMQ và xử lý thất bại, việc dùng retry interceptor trong **adviceChain** có thể giúp thử lại trước khi đưa message vào DLQ. Nhưng khi listener thao tác với database, một vấn đề quan trọng hơn số lần retry là: **mỗi lần thử có transaction riêng hay tất cả attempts đều nằm trong một transaction?**

Câu trả lời phụ thuộc vào **thứ tự advice**, vị trí của **@Transactional**, việc listener container có cấu hình **setTransactionManager(...)** hay không, và lựa chọn **stateless/stateful retry**. Nếu chọn sai, attempt cuối có thể xử lý thành công nhưng transaction vẫn rollback, message có thể bị redeliver vô hạn hoặc dữ liệu bên ngoài DB bị thực hiện trùng.

Bài này đặt retry vào dòng xử lý **RabbitTemplate → exchange → queue → @RabbitListener**, mô tả hai mô hình transaction khác nhau, cách dùng RetryInterceptorBuilder, recoverer, ACK/requeue, dead-letter và kiểm thử phạm vi transaction. Mục tiêu không phải chỉ làm hết lỗi, mà là xử lý bất đồng bộ đáng tin cậy, có khả năng giải thích điều gì đã commit và điều gì còn có thể được giao lại.

> **Nguyên tắc:** Không thêm retry vào adviceChain rồi mặc định mỗi lần thử đã mở transaction mới. Trước hết phải xác định **interceptor bao ngoài**, **transaction owner** và **exception có thoát tới ranh giới rollback hay không**.

## 1. Những cơ chế được gọi là retry

| Cơ chế | Đơn vị được lặp lại | Có phải broker giao lại message? | Khi nào dùng |
|---|---|---|---|
| **Stateless retry** | Gọi lại listener trong một invocation | Thường **không** giữa các attempt | Retry ngắn, transaction nằm bên trong retry |
| **Stateful retry** | Retry state được nhận diện qua các lần giao cùng message | **Có thể có** sau rollback/requeue | Có outer transaction cần rollback trước retry |
| **Broker redelivery** | Broker giao lại message chưa ACK hoặc bị requeue | **Có** | Consumer disconnect, reject/requeue, rollback |
| **Retry queue / delay queue** | Đưa message sang queue chờ rồi quay lại | **Có**, theo topology | Delay dài, không giữ thread consumer |
| **Publisher retry** | RabbitTemplate thử gửi message tới broker | Không phải consumer retry | Lỗi kết nối/publish; cần chống gửi trùng |
| **Connection recovery** | Tái tạo connection/channel/consumer | Không tương đương business attempt | Broker hoặc network mất kết nối |

**adviceChain của listener không bật retry cho RabbitTemplate.** Nếu publisher gửi lại khi mất confirm, broker có thể nhận cùng sự kiện hai lần dù listener retry chỉ được cấu hình một lần. Vì thế, consumer vẫn phải **idempotent**.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] --> E["Exchange"]
    E --> Q[("Queue")]
    Q --> C["Listener container<br/>adviceChain"]
    C --> L["@RabbitListener"]
    L --> D["Business service<br/>DB transaction"]
    D -->|"Success"| A["ACK"]
    D -->|"Transient failure"| R{"Retry policy"}
    R -->|"Retry allowed"| L
    R -->|"Exhausted"| N["Reject requeue=false"]
    N --> X["Dead-letter exchange"]
    X --> DLQ[("DLQ")]
~~~

Sơ đồ là khái niệm tổng quát; đường quay lại listener có thể xảy ra **ngay trong một invocation** hoặc **sau broker redelivery**, tùy stateless/stateful.

## 2. adviceChain là chuỗi AOP advice lồng nhau

**adviceChain** của Spring AMQP listener container là mảng AOP **Advice** bao quanh phần thực thi listener. Mỗi advice có thể bổ sung retry, transaction, tracing, logging hoặc kiểm tra khác.

Trong một chuỗi AOP thông thường, **advice đầu tiên nằm ngoài cùng**, advice cuối nằm gần listener nhất.

~~~text
adviceChain = [A, B, C]

A.before
  B.before
    C.before
      @RabbitListener(...)
    C.after
  B.after
A.after
~~~

### 2.1. Retry ngoài transaction: transaction mới ở mỗi attempt

~~~text
adviceChain = [RETRY, TRANSACTION]

RETRY bắt đầu
  attempt 1
    BEGIN TX-1
    handler -> lỗi
    ROLLBACK TX-1
  backoff
  attempt 2
    BEGIN TX-2
    handler -> lỗi
    ROLLBACK TX-2
  backoff
  attempt 3
    BEGIN TX-3
    handler -> thành công
    COMMIT TX-3
RETRY kết thúc
~~~

**RETRY (outer) → TRANSACTION (inner)** cho phép mỗi attempt đi vào một transaction mới nếu transaction advice được gọi lại qua proxy/interceptor thích hợp.

Cấu trúc này phù hợp với **database deadlock**, lock timeout hoặc optimistic locking conflict: attempt thất bại **rollback trước**, rồi mới có attempt tiếp theo.

### 2.2. Transaction ngoài retry: nhiều attempts có thể dùng một transaction

~~~text
adviceChain = [TRANSACTION, RETRY]

BEGIN TX
  RETRY bắt đầu
    attempt 1 -> lỗi
    retry bắt exception
    attempt 2 -> lỗi
    retry bắt exception
    attempt 3 -> thành công
  RETRY trả về
COMMIT hoặc ROLLBACK toàn TX
~~~

**TRANSACTION (outer) → RETRY (inner)** không tạo một transaction mới cho mỗi lần thử. Nếu lỗi trước đó khiến transaction bị đánh dấu **rollback-only**, retry thành công sau đó cũng **không bảo đảm commit thành công**.

Ngoài ra, transaction ngoài có thể giữ database connection/lock trong suốt khoảng backoff. Không nên kết luận “lần cuối chạy thành công” chỉ từ việc method không ném exception.

### 2.3. Ngoại lệ đặc biệt của Spring AMQP: setTransactionManager

Theo Javadoc **AbstractMessageListenerContainer.setAdviceChain(...)** của **Spring AMQP 3.2**, khi container đã được cấu hình **setTransactionManager(PlatformTransactionManager)**, framework tạo **transaction advice riêng và áp dụng đầu tiên trong chain**.

Ví dụ:

~~~java
factory.setTransactionManager(jdbcTransactionManager);
factory.setAdviceChain(retryAdvice);
~~~

Về mặt thứ tự, cần hiểu gần với:

~~~text
TRANSACTION do listener container bổ sung (OUTER)
    -> RETRY do ứng dụng cung cấp
        -> @RabbitListener
~~~

**Không thêm một transaction interceptor nữa vào adviceChain nếu đã dùng setTransactionManager**: bạn có thể vô tình áp dụng hai lớp giao dịch.

Đây là điểm khiến công thức “cứ đưa retry lên đầu danh sách là retry ở ngoài transaction” **không đúng** đối với mọi cấu hình Spring AMQP. Muốn mỗi attempt có transaction mới, phải chọn transaction boundary cụ thể, không chỉ đổi thứ tự tham số khi gọi setAdviceChain.

## 3. Stateless và stateful retry trong quan hệ với giao dịch

### 3.1. Stateless retry

Stateless retry giữ số lần thử trong **một lần gọi**; interceptor bắt exception, đợi backoff và gọi lại handler nếu còn ngân sách retry.

Phù hợp khi:

- Listener không bị bao bởi một database transaction ngoài.
- Service **@Transactional** được gọi **bên trong mỗi attempt**, thông qua Spring proxy.
- Một attempt lỗi có thể rollback transaction trước khi attempt mới bắt đầu.
- Backoff ngắn, không cần nhả consumer thread quá lâu.

**Không nên** mặc định dùng stateless khi transaction đã bắt đầu **cao hơn** retry interceptor và bắt buộc rollback khi lỗi.

### 3.2. Stateful retry

Stateful retry lưu trạng thái theo **message identity**, thường từ **AMQP messageId** hoặc **MessageKeyGenerator** tùy chỉnh. Khi outer transaction thất bại, exception có thể đi ra ngoài để transaction **rollback**, rồi broker/container thực hiện redelivery. Interceptor nhận ra đây là cùng message ở lượt thử kế tiếp.

Vì vậy stateful retry thường thích hợp hơn khi **setTransactionManager(...)** đặt transaction ngoài listener invocation.

**Lưu ý:**

- messageId phải **ổn định và đủ duy nhất** cho mỗi message.
- Retry state của interceptor không phải bộ đếm bền vững vĩnh viễn trên broker; trạng thái in-memory có thể mất khi ứng dụng restart.
- Khi messageId thiếu, Spring AMQP có chính sách fatal đặc biệt; phải cấu hình/kiểm thử rõ.
- Khi exhausted, **recoverer** quyết định reject, republish hoặc xem như đã recovered.

### 3.3. Bảng lựa chọn

| Kiến trúc | Lựa chọn thường hợp lý | Vì sao |
|---|---|---|
| Không có transaction | Stateless | Đơn giản, retry ngay trong lời gọi |
| Listener gọi bean service @Transactional | Stateless | Transaction của service được mở lại mỗi attempt |
| Container mở external DB transaction bằng setTransactionManager | Stateful | Rollback trước redelivery/lượt thử sau |
| Chỉ bật channelTransacted=true | Cần phân tích riêng | AMQP transaction không tự là JDBC transaction |
| Retry sau vài phút/giờ | Retry queue / scheduler | Không giữ thread listener trong backoff dài |
| Lỗi JSON/schema cố định | Không retry nguyên message | Reject/DLQ/quarantine |
| Batch listener gom nhiều delivery | Thận trọng | Có thể không biết chính xác phần tử gây lỗi |

## 4. Transaction DB, AMQP transaction và ACK khác nhau

| Cơ chế | Phạm vi | Không tự bảo đảm |
|---|---|---|
| **@Transactional trên service JDBC** | Giao dịch database của method | Broker ACK sẽ commit atomically |
| **setTransactionManager(...)** trên container | External transaction bao quanh listener | Mỗi attempt bên trong sẽ có TX mới |
| **channelTransacted=true** | AMQP channel commit/rollback | Là XA giữa RabbitMQ và database |
| **AcknowledgeMode.AUTO** | Container ACK khi xử lý thành công | Transaction DB tự được tạo |
| **AcknowledgeMode.MANUAL** | Ứng dụng ACK/NACK với deliveryTag | Retry có thể thu hồi ACK đã gửi |
| **RabbitTransactionManager** | Rabbit channel transaction | Quản lý JDBC/XA |

Khi **channelTransacted=true** và có external transaction manager, Spring AMQP hỗ trợ phối hợp theo kiểu **Best Efforts One Phase Commit**. Đây **không phải XA/distributed transaction**. Nếu database đã commit nhưng ACK của broker bị mất, message vẫn có thể được giao lại. Consumer phải dùng **eventId, idempotency key, unique constraint và transaction** để bảo vệ side effect.

## 5. Ví dụ thực hành: stateless adviceChain, @Transactional trong service

Ví dụ nhắm tới **Spring Boot 3.x, Spring AMQP 3.x, Spring Retry 2.x**, kết hợp RabbitMQ AMQP 0-9-1, JDBC và H2 trên môi trường test.

### 5.1. Dependencies

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Tên starter và API của Spring Boot/Spring AMQP 4.x có thể thay đổi; cần đối chiếu phiên bản đang dùng. Trong ví dụ này, Spring Boot quản lý versions tương thích.

### 5.2. application.yml và bảng demo

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: local-demo-only
  datasource:
    url: jdbc:h2:mem:retrydemo;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
~~~

Đây là thông tin demo; production phải dùng biến môi trường hoặc secret manager. Trên vhost test, cần có user/permission tương ứng.

Định nghĩa bảng dùng trong schema migration test (có thể đưa vào **schema.sql** của ứng dụng demo, được khởi tạo trước listener):

~~~sql
CREATE TABLE handled_events (
    event_id VARCHAR(120) PRIMARY KEY
);
~~~

### 5.3. Khai báo exchange, queue, binding, DLQ

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryTopology {
    public static final String EXCHANGE = "orders.retry.exchange";
    public static final String KEY = "orders.process";
    public static final String QUEUE = "orders.retry.q";
    public static final String DLX = "orders.retry.dlx";
    public static final String DLQ = "orders.retry.dlq";
    public static final String DEAD_KEY = "orders.failed";

    @Bean
    public Declarables resources() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);
        DirectExchange dlx =
                new DirectExchange(DLX, true, false);

        Queue work = QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
        Queue failed = QueueBuilder.durable(DLQ).build();

        return new Declarables(
                exchange, dlx, work, failed,
                BindingBuilder.bind(work).to(exchange).with(KEY),
                BindingBuilder.bind(failed).to(dlx).with(DEAD_KEY)
        );
    }
}
~~~

Khi exhausted và container **reject với requeue=false**, RabbitMQ có thể gửi message vào DLQ nếu topology đúng. **DLX không tự kích hoạt retry** nếu chưa có retry interceptor hoặc topology retry riêng.

### 5.4. Stateless retry interceptor trong listener factory

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StatelessRetryConfig {

    @Bean("statelessRetryFactory")
    public SimpleRabbitListenerContainerFactory statelessRetryFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(1);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(200, 2.0, 1000)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build()
        );
        return factory;
    }
}
~~~

**maxAttempts(3)** = **3 lần gọi tổng cộng** (1 lần đầu và tối đa 2 lần thử lại), không phải 3 retries sau lần đầu. Các khoảng backoff trong builder tính bằng **milli giây**.

**RejectAndDontRequeueRecoverer** ném AmqpRejectAndDontRequeueException khi exhausted, khiến container reject không requeue để broker có thể dead-letter. Không dùng recoverer chỉ log rồi trả bình thường nếu nghiệp vụ yêu cầu bảo toàn message chưa xử lý.

Bài này **không đặt setTransactionManager(...) trên listener factory**. Transaction được mở bên trong mỗi lần listener gọi service.

### 5.5. Service @Transactional, ghi DB rồi giả lập lỗi

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RecordingService {
    private final JdbcTemplate jdbc;
    private final AtomicInteger attemptCounter = new AtomicInteger();

    public RecordingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void record(String eventId) {
        jdbc.update(
                "INSERT INTO handled_events(event_id) VALUES (?)",
                eventId
        );

        int attempt = attemptCounter.incrementAndGet();
        System.out.println("DB attempt = " + attempt);

        if (attempt <= 2) {
            throw new IllegalStateException(
                    "Simulated temporary failure"
            );
        }
    }
}
~~~

**AtomicInteger chỉ phục vụ thử một message**, không phải retry counter production. Khi thực tế có nhiều event và consumer, phải dùng exception có ý nghĩa nghiệp vụ và retry policy theo từng message.

### 5.6. Listener gọi bean qua Spring proxy

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class RecordingListener {
    private final RecordingService service;

    public RecordingListener(RecordingService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = RetryTopology.QUEUE,
            containerFactory = "statelessRetryFactory"
    )
    public void receive(String eventId) {
        service.record(eventId);
    }
}
~~~

**@Transactional ở bean RecordingService khác** nên lời gọi đi qua Spring proxy. Nếu listener dùng **this.record(...)** trong cùng bean và trông chờ proxy tạo transaction, bạn có thể vô tình bỏ qua @Transactional do **self-invocation**.

Luồng retry:

~~~text
Stateless retry advice
  attempt 1 -> RecordingService proxy -> TX-1 INSERT -> THROW -> ROLLBACK
  backoff
  attempt 2 -> RecordingService proxy -> TX-2 INSERT -> THROW -> ROLLBACK
  backoff
  attempt 3 -> RecordingService proxy -> TX-3 INSERT -> RETURN -> COMMIT
Listener return -> container ACK.
~~~

### 5.7. Producer gửi eventId

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class RetryDemoPublisher {
    private final RabbitTemplate template;

    public RetryDemoPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String eventId) {
        template.convertAndSend(
                RetryTopology.EXCHANGE,
                RetryTopology.KEY,
                eventId
        );
    }
}
~~~

Trong test, gọi **publish("evt-1")** đúng một lần. Khi broker, queue và H2 đã sẵn sàng, log dự kiến có ba lần gọi service; bảng **handled_events** cuối cùng có **một hàng evt-1**, vì hai INSERT đầu rollback.

**Đây là kết quả dự kiến, không phải test đã chạy.** Muốn chứng minh transaction boundary, bật transaction logs hoặc thêm TransactionSynchronization ghi nhận commit/rollback, thay vì chỉ đếm method calls. Khi xử lý thật, cần xử lý duplicate eventId có chủ đích: primary key đơn thuần có thể ném lỗi khi redelivery sau commit.

## 6. Thực hành với stateful retry khi container mở transaction

Bây giờ thay đổi kiến trúc. Listener container được gắn **PlatformTransactionManager** để transaction bắt đầu **bên ngoài** adviceChain do ứng dụng cung cấp. Theo quy tắc Spring AMQP đã nêu, một stateless interceptor ở trong transaction có thể bắt lỗi và gọi lại trước khi transaction ngoài thực sự rollback.

Với kiểu xử lý yêu cầu rollback sau mỗi lần thất bại, nên cân nhắc **stateful retry**.

### 6.1. Factory stateful + external transaction manager

Đây là **cấu hình thay thế** cho statelessRetryFactory, không chạy cả hai listener trên cùng queue trong lúc so sánh.

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class StatefulTxConfiguration {

    @Bean("statefulTxFactory")
    public SimpleRabbitListenerContainerFactory statefulTxFactory(
            ConnectionFactory connectionFactory,
            PlatformTransactionManager jdbcTransactionManager) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(1);

        // Container tạo transaction advice bên ngoài adviceChain.
        factory.setTransactionManager(jdbcTransactionManager);
        factory.setChannelTransacted(true);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateful()
                        .maxAttempts(3)
                        .backOffOptions(500, 2.0, 5000)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build()
        );

        return factory;
    }
}
~~~

Trong ví dụ, **jdbcTransactionManager** là PlatformTransactionManager cho datasource đang được sử dụng. Nếu có nhiều transaction manager, dùng **@Qualifier** để chọn rõ bean. **setChannelTransacted(true)** yêu cầu Rabbit channel sử dụng AMQP transaction; đây là sự phối hợp best-efforts với external transaction chứ không phải XA giữa JDBC và RabbitMQ.

**Không thêm transaction interceptor thủ công vào setAdviceChain** của factory này. Container đã có transaction manager và sẽ bổ sung transaction advice của nó ở ngoài.

### 6.2. Stateful retry cần messageId ổn định

Ở đây chỉ dùng **messageId** để nhận diện các broker redelivery của cùng một message. Producer có thể gắn nó khi gửi:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public void publishWithMessageId(
        RabbitTemplate template,
        String eventId) {
    Message message = MessageBuilder
            .withBody(eventId.getBytes(StandardCharsets.UTF_8))
            .setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN)
            .setContentEncoding("UTF-8")
            .setMessageId(eventId)
            .build();

    template.send(RetryTopology.EXCHANGE, RetryTopology.KEY, message);
}
~~~

Đây là **phương thức ví dụ phải nằm trong một class/bean**. Mỗi sự kiện phải có messageId ổn định; không tạo một ID mới mỗi lần broker redelivery, không dùng **deliveryTag** làm khóa retry và không dùng cùng ID cho nhiều sự kiện khác nhau.

Nếu producer không cấp messageId, có thể cấu hình **MessageKeyGenerator** dựa trên một khóa nghiệp vụ duy nhất, ví dụ eventId trong payload hoặc header. Phải đảm bảo cách sinh key nhất quán và không lộ thông tin nhạy cảm.

### 6.3. Listener sử dụng factory stateful

~~~java
@RabbitListener(
        queues = RetryTopology.QUEUE,
        containerFactory = "statefulTxFactory"
)
public void receiveWithOuterTransaction(String eventId) {
    billingService.process(eventId);
}
~~~

Đây là **phương thức minh họa đặt trong một Spring bean** có dependency billingService. Chỉ bật listener này khi đã dừng/loại listener stateless cùng queue để không tạo competing consumers trong bài thử.

Mô hình xử lý:

~~~text
Broker delivery 1 (messageId=evt-101)
  BEGIN external TX-1 (container)
    stateful retry thấy attempt đầu
      gọi listener -> lỗi
  ROLLBACK TX-1
  message được requeue/redeliver theo chính sách

Broker delivery tiếp theo (cùng messageId)
  BEGIN external TX-2
    stateful retry nhận diện cùng message
      gọi listener -> thành công
  COMMIT TX-2
  container ACK theo cấu hình
~~~

Với stateful retry, **mỗi exception có thể đi ra khỏi lời gọi listener**, giúp transaction ngoài rollback trước khi có delivery kế tiếp. Bộ đếm attempt được interceptor giữ theo message identity để không lặp vô hạn một cách vô thức.

**Đừng coi số lần broker redelivery là bằng đúng maxAttempts trong mọi sự cố.** Restart ứng dụng, timeout kết nối, requeue và queue type có thể thay đổi hành vi quan sát. Cần kiểm thử trên đúng phiên bản của Spring AMQP/RabbitMQ và cấu hình transaction.

### 6.4. Thiếu messageId và retry state

Theo Spring AMQP, khi **stateful retry** không có messageId, hành vi mặc định có thể coi lỗi là **fatal đối với consumer** sau một lần xử lý, do interceptor không thể nhận diện trạng thái message. Thuộc tính **statefulRetryFatalWithNullMessageId=false** có thể cho phép consumer tiếp tục và reject message theo policy thay vì dừng.

Nhưng tắt fatal **không phải giải pháp thay cho identity**. Cách tốt nhất là producer đặt ID ổn định, hoặc dùng MessageKeyGenerator có contract rõ.

Stateful retry context thường được lưu trong bộ nhớ của consumer. Nếu tiến trình restart, bộ nhớ retry không còn. Khi yêu cầu giới hạn attempts **bền vững xuyên restart**, phải bổ sung một cơ chế lưu attempt hoặc retry queue có chiến lược rõ ràng.

## 7. Recoverer quyết định số phận message sau khi exhausted

Khi **maxAttempts** đã hết, **MessageRecoverer** quyết định bước tiếp theo. Không được mặc định mọi recoverer đều đưa message vào DLQ.

| Recoverer | Hành vi điển hình | Kết quả với original message |
|---|---|---|
| **RejectAndDontRequeueRecoverer** | Ném AmqpRejectAndDontRequeueException | Broker reject không requeue; có thể dead-letter |
| **RepublishMessageRecoverer** | Publish failed message sang error exchange | Nếu recovery thành công, original có thể được ACK |
| **RepublishMessageRecovererWithConfirms** | Republish và xác minh publisher confirm | Giảm một số rủi ro mất message khi republish; vẫn cần chính sách lỗi |
| **Recoverer chỉ log rồi return** | Lỗi được coi là recovered | Original có thể ACK, **không tự DLQ** |
| **Custom recoverer ném exception** | Exception đi lên container | Requeue/reject tùy loại exception và container |

### 7.1. Khác biệt giữa reject và republish

~~~mermaid
flowchart TD
    E["Retry exhausted"] --> R{"Recoverer"}
    R -->|"RejectAndDontRequeue"| N["Container reject<br/>requeue=false"]
    N --> DX["Broker DLX"]
    DX --> DQ[("DLQ")]
    R -->|"Republish"| P["RabbitTemplate publish<br/>error exchange"]
    P --> A["Recoverer thành công<br/>ACK original"]
    R -->|"Log and return"| B["ACK original<br/>có thể mất cơ hội điều tra"]
~~~

Nếu muốn RabbitMQ tạo header dead-letter như **x-death**, dùng đường broker reject → DLX và xác minh cấu hình. **Republish** tạo một publish mới theo cơ chế ứng dụng, không phải broker dead-letter của original.

**Một recoverer chỉ log rồi return có thể khiến message được ACK mà không còn ở queue chính hoặc DLQ.** Hãy chọn hành vi có chủ đích và kiểm tra bằng thực nghiệm.

### 7.2. Khi nào broker có thể dead-letter?

Cần queue gốc có **x-dead-letter-exchange** hoặc policy tương đương, DLX tồn tại, binding tới DLQ hợp lệ, và message bị reject/nack **requeue=false** (hoặc sự kiện dead-letter khác). Nếu thiếu topology, message có thể bị loại bỏ.

Không xóa queue đang có dữ liệu để sửa một sai lệch DLX/argument trong môi trường production. Dùng migration/policy phù hợp.

## 8. Rollback, ACK/NACK và defaultRequeueRejected

| Tình huống | Database | Broker/Container |
|---|---|---|
| Listener thành công | Commit nếu transaction hợp lệ | ACK theo AUTO |
| Stateless attempt lỗi, TX ở service | TX của attempt rollback | Retry advice có thể gọi lại listener nội bộ |
| Stateful attempt lỗi, TX ở container | Outer TX rollback | Message có thể được broker redeliver |
| Retry exhausted, recoverer reject | Các attempts thất bại rollback theo boundary | Reject không requeue; DLQ nếu có |
| Retry exhausted, recoverer return bình thường | Tùy transaction và recovery logic | Original có thể ACK |
| DB commit nhưng ACK bị mất | DB đã thay đổi | Broker có thể redeliver, cần idempotency |

**defaultRequeueRejected** thường có mặc định là **true**. Nếu exception đến container và không được phân loại theo cách khác, broker có thể requeue message, thậm chí tạo vòng lặp vô hạn. **AmqpRejectAndDontRequeueException** yêu cầu reject không requeue bất kể default này.

**ImmediateRequeueAmqpException** có thể yêu cầu requeue dù default đang false, nhưng requeue tức thì không tạo delay/backoff.

**AcknowledgeMode.AUTO** nghĩa container ACK khi việc xử lý được coi là thành công; khác RabbitMQ auto-ack khi nhận. Với **MANUAL**, listener phải tự ACK/NACK đúng channel và delivery tag. Đừng tự ACK sớm rồi mong retry interceptor có thể thu hồi ACK đã gửi.

### 8.1. Database transaction không phải Rabbit transaction

- **@Transactional trên JDBC service**: rollback database khi method ném exception phù hợp.
- **channelTransacted=true**: RabbitMQ AMQP channel dùng transaction ở phía messaging.
- **setTransactionManager(...)**: container có external transaction quanh listener.
- **Publisher confirms**: producer nhận thông tin broker đã xử lý publish, không liên quan trực tiếp DB commit của consumer.

Ngay cả khi container dùng external transaction và channelTransacted, Spring AMQP chủ yếu cung cấp **best-efforts** chứ không phải XA. Khi DB commit thành công nhưng broker không nhận ACK, cùng event có thể được xử lý lại.

### 8.2. Rollback-only và UnexpectedRollbackException

Với **transaction ngoài + stateless retry trong**, exception ở attempt đầu có thể làm transaction bị đánh dấu **rollback-only**. Retry interceptor bắt lỗi và gọi lại listener, nhưng attempt sau vẫn nằm trong transaction đó.

Kết quả: method cuối trả về thành công, nhưng **commit ném UnexpectedRollbackException** hoặc transaction rollback. Một số database còn khiến transaction không thể tiếp tục sau SQL error.

**Tăng maxAttempts không giải quyết transaction boundary sai.** Cần bảo đảm rollback xong rồi mới retry hoặc chọn mô hình stateful với outer transaction.

## 9. Phân loại exception trước khi retry

| Lỗi | Ví dụ | Chính sách phù hợp |
|---|---|---|
| **Transient database** | Lock timeout, deadlock, lỗi kết nối ngắn | Retry giới hạn, TX mới mỗi attempt |
| **Transient dependency** | HTTP 503, timeout có thể hồi phục | Backoff, giới hạn tổng thời gian |
| **Malformed payload** | JSON sai, sai contentType | Không retry nguyên payload, DLQ |
| **Permanent business** | Đơn hàng không hợp lệ | Business error hoặc DLQ tùy contract |
| **Code bug** | NPE không dự kiến | Alert, không retry vô hạn |
| **Broker/channel failure** | Mất kết nối RabbitMQ | Connection/container recovery riêng |
| **Duplicate event** | Cùng eventId đã commit | Bỏ tác dụng phụ lần hai, ACK an toàn |

Spring Retry policy có thể lọc exception, nhưng **ListenerExecutionFailedException** thường bọc lỗi thật. Với classifier tùy chỉnh, cần xem **cause chain** thay vì chỉ so sánh class của wrapper.

Đừng đánh đồng “handler không ném nữa” với “business transaction đã thực sự commit”. Khi recoverer return bình thường, container có thể ACK mà nghiệp vụ chưa hoàn thành, nếu không có hợp đồng recovery rõ.

## 10. Backoff dài có thể làm chậm toàn bộ consumer

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ
    participant L as Listener container
    participant DB as Database
    Q->>L: Delivery event-1
    L->>DB: Attempt 1
    DB-->>L: Transient error
    Note over L: Backoff 200 ms
    L->>DB: Attempt 2
    DB-->>L: Transient error
    Note over L: Backoff 400 ms
    L->>DB: Attempt 3
    DB-->>L: Success
    L->>Q: ACK
~~~

Khi dùng **stateless retry với backoff**, thread listener có thể chờ trong cùng invocation. Nếu nhiều message lỗi và backoff tính bằng hàng chục giây/phút, consumer có thể không nhận được công việc mới.

Với các nghiệp vụ cần delay dài, cân nhắc **retry queue, DLX/TTL hoặc scheduler** thay vì để một nhóm worker ngủ. Khi thiết kế retry queue, giới hạn số vòng và xem xét DLQ/parking queue để không tạo message loop.

**Prefetch** cũng rất quan trọng: message đã chuyển sang **Unacked** ở consumer không thể được broker tự lấy lại ngay để ưu tiên job khác. Kiểm tra **Ready, Unacked, consumer count và processing latency** trong suốt bài thử.

## 11. Quan sát thứ tự advice và commit/rollback thật

Chỉ đếm “method được gọi 3 lần” là chưa đủ. Cần chứng minh transaction nào commit hoặc rollback.

| Tín hiệu | Ý nghĩa |
|---|---|
| **eventId / messageId** | Các attempts có thuộc cùng message không? |
| **retryCount** | Spring Retry đang ở lần thử nào? |
| **DB begin/commit/rollback** | Có transaction mới giữa các attempts không? |
| **TransactionSynchronizationManager** | Vị trí code đang có active transaction không? |
| **redelivered** | Broker có giao lại message không? |
| **Ready / Unacked** | Broker đang giữ hay đã giao message? |
| **DLQ depth** | Exhausted có đi đúng đường DLX không? |
| **duplicate_skipped** | Idempotent consumer đã xử lý duplicate an toàn chưa? |

Trong môi trường phát triển có thể tăng log:

~~~yaml
logging:
  level:
    org.springframework.transaction.interceptor: TRACE
    org.springframework.retry: DEBUG
    org.springframework.jdbc.support.JdbcTransactionManager: DEBUG
~~~

Tùy phiên bản và bean thực tế, transaction manager có thể là **DataSourceTransactionManager** hoặc **JdbcTransactionManager**; điều chỉnh logger tương ứng. Tránh bật TRACE nhạy cảm trong production.

### 11.1. Ma trận kiểm thử

| Cấu hình | Transactions | Deliveries | Điều kỳ vọng |
|---|---|---|---|
| Stateless retry + @Transactional service bên trong | TX riêng cho từng attempt | Thường 1 khi không disconnect | Hai rollback, một commit |
| Stateless retry nằm trong outer container transaction | Có thể cùng một TX cho nhiều attempts | Thường 1 trước khi lỗi thoát | Rủi ro rollback-only |
| Stateful retry + outer transaction | TX rollback theo delivery | Có thể nhiều delivery | Redelivery và retry state theo messageId |
| Không giới hạn retry, requeue=true | Tùy | Có thể vô hạn | Poison loop |
| Retry exhausted + RejectAndDontRequeueRecoverer | Theo boundary | Tùy retry type | Reject, DLX nếu có |
| Retry exhausted + recoverer chỉ log | Theo boundary | Tùy | Original có thể ACK, không ở DLQ |

Những giá trị trên là **mô hình dự kiến**, không phải kiểm chứng đã chạy. Với hệ thống thực, test trên cùng phiên bản Spring AMQP/RabbitMQ, queue type và transaction manager mà production dùng.

## 12. Bài tập thực hành

### Bài A — Mỗi attempt một transaction

1. Tạo RabbitMQ/vhost test, exchange/queue/DLQ ở mục 5.
2. Chuẩn bị H2 và bảng **handled_events**.
3. Chạy statelessRetryFactory với RecordingListener.
4. Gửi **evt-1** đúng một lần.
5. Quan sát ba lần gọi RecordingService, transaction rollback hai lần đầu, commit lần cuối.
6. Truy vấn bảng: chỉ có một eventId.
7. Giải thích vì sao gọi qua Spring proxy quan trọng.

### Bài B — Outer transaction và stateless retry

1. Tạo một factory riêng với setTransactionManager.
2. Thử stateless advice trong factory này trên dữ liệu test.
3. Bật log transaction, đo số lần begin/rollback và kiểm tra rollback-only.
4. Giải thích vì sao listener thành công ở attempt cuối nhưng transaction vẫn có thể rollback.
5. Đối chiếu với statefulRetryFactory.

### Bài C — Stateful và messageId

1. Publish message gắn messageId ổn định.
2. Cho handler thất bại một số lượt, sau đó thành công.
3. Quan sát broker redelivery, transaction rollback và retry state.
4. Publish một message không có messageId trên vhost test riêng.
5. Nghiên cứu statefulRetryFatalWithNullMessageId và cách thay bằng MessageKeyGenerator.

### Bài D — So sánh recoverer

1. Cố tình cho listener luôn ném transient exception.
2. Đặt maxAttempts(3).
3. Với RejectAndDontRequeueRecoverer, kiểm tra message vào DLQ.
4. Trong một thử nghiệm riêng, dùng RepublishMessageRecoverer và quan sát original có thể được ACK.
5. Giải thích vì sao recoverer chỉ log và return có thể khiến message không còn ở queue nào để điều tra.

### Bài E — Duplicate và ACK bị mất

1. Cho database commit thành công nhưng giả lập mất ACK trước khi broker ghi nhận.
2. Để message cùng eventId được redeliver.
3. Thiết kế idempotency key và unique constraint để side effect chỉ xảy ra một lần.
4. Phân biệt số lần gọi handler và số lần thay đổi dữ liệu thực tế.

### Bài F — Backoff và throughput

1. Tạo nhiều message gây lỗi tạm thời.
2. So sánh stateless retry backoff dài với retry queue.
3. Đo số consumer bị giữ, Unacked, Ready và thời gian xử lý.
4. Đề xuất cách giới hạn concurrency và tránh tất cả worker chờ cùng một downstream.

## 13. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Thêm retry vào adviceChain và nghĩ TX tự mới mỗi lần | Các attempts có thể nằm trong một outer TX | Xác định transaction owner và thứ tự advice |
| Đặt stateless trong container outer DB TX | Rollback-only, commit thất bại | Chọn stateful hoặc đổi boundary |
| setTransactionManager rồi thêm transaction advice lần nữa | Hai tầng transaction không mong muốn | Chỉ dùng một nơi khai báo external transaction |
| Self-invocation của @Transactional method | Proxy có thể không chạy | Tách bean hoặc dùng transaction boundary tường minh |
| Không phân loại permanent vs transient | Retry vô ích hoặc mất cơ hội phục hồi | Exception classifier và bounded retry |
| Recoverer chỉ log rồi return | Message có thể được ACK khi chưa xử lý | Chọn recoverer theo yêu cầu DLQ |
| Không có DLX nhưng giả định reject sẽ lưu message | Message có thể bị discard | Kiểm tra DLX/queue/binding |
| Stateful thiếu messageId | Retry state sai hoặc container dừng | Stable ID/MessageKeyGenerator |
| Giữ transaction mở suốt backoff dài | Giữ connection và lock | TX riêng mỗi attempt hoặc retry queue |
| Đếm calls mà không xem commit | Kết luận sai về tính nhất quán | Transaction logs và DB assertion |
| MANUAL ACK sớm rồi kỳ vọng retry sửa được | Delivery đã ACK | ACK sau khi xử lý phù hợp |
| Không idempotent sau DB commit | Redelivery tạo tác dụng phụ trùng | eventId + unique constraint/transaction |

## 14. Tổng kết

- **adviceChain** là tập hợp AOP advice bao quanh listener; theo quy tắc thông thường, **advice đầu tiên nằm ngoài cùng**.
- **Retry ngoài transaction** có thể tạo **transaction mới cho mỗi attempt**; **transaction ngoài retry** có thể khiến nhiều attempts cùng dùng một transaction.
- **Ngoại lệ quan trọng của Spring AMQP:** cấu hình **setTransactionManager(...)** trên container khiến framework **thêm transaction advice ở đầu**, bên ngoài adviceChain do ứng dụng cấp. Đừng thêm một transaction interceptor trùng lặp.
- **Stateless retry** thường phù hợp khi transaction được mở **bên trong từng attempt**. **Stateful retry** thường phù hợp hơn nếu outer transaction phải rollback trước khi broker redeliver.
- **Stateful retry cần message identity**, và state in-memory không phải giới hạn retries bền vững xuyên restart.
- **Recoverer quyết định số phận message sau exhausted**: reject để broker DLX khác với republish hoặc log/ACK.
- **ACK, DB commit, AMQP transaction, publisher confirm** là các tín hiệu khác nhau, không tự bảo đảm exactly-once.
- Một hệ thống đáng tin cậy kết hợp **RabbitTemplate**, **@RabbitListener**, exchange/queue/binding, retry hữu hạn, transaction boundary đúng, DLQ, idempotency và giám sát.

### Tài liệu tham khảo chính thức

- [Spring AMQP — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): stateless/stateful retry, RetryInterceptorBuilder, recoverers, messageId và DLQ.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): channelTransacted, external transaction manager, rollback và Best Efforts One Phase Commit.
- [Spring AMQP 3.2.5 — AbstractMessageListenerContainer.setAdviceChain](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/listener/AbstractMessageListenerContainer.html): transaction advice của container và thứ tự áp dụng.
- [Spring AMQP 3.2 — RetryInterceptorBuilder API](https://docs.spring.io/spring-amqp/docs/3.2.12-SNAPSHOT/api/org/springframework/amqp/rabbit/config/RetryInterceptorBuilder.html): maxAttempts, backOffOptions, stateful/stateless.
- [Spring Integration — Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): quy tắc lồng advice và transaction scope.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK và publisher confirm.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject không requeue và DLQ.
