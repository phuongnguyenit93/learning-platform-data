# Retry, redelivery, dead-letter và kiểm tra lỗi không bị mất trong Messaging

## 1. Bài toán thực tế: một lỗi xử lý message có thể đi đâu?

Một consumer nhận message từ broker (RabbitMQ, Kafka hoặc hệ thống khác) có thể thất bại vì mạng chập chờn, database bị khóa, JSON không hợp lệ, schema không tương thích hoặc quy tắc nghiệp vụ bị vi phạm. Nếu chỉ viết `catch (Exception ex) { log.warn(...); }` rồi cho listener trả về bình thường, container có thể **ACK** message dù công việc không hoàn tất. Khi đó broker cho rằng message đã xử lý và không gửi lại nữa. Một lỗi đã bị che giấu sẽ không được retry, không vào dead-letter queue (DLQ) và rất khó truy vết.

Ở chiều ngược lại, nếu mặc định requeue mọi exception vô hạn, một **poison message** (message luôn lỗi do dữ liệu không hợp lệ) có thể được giao lại liên tục, gây log storm, chiếm tài nguyên consumer và chặn message hợp lệ.

Một thiết kế tốt không chỉ “bật retry”, mà cần **chứng minh trạng thái cuối**:

- Xử lý thành công → broker đã ACK, side effect nghiệp vụ đúng.
- Lỗi tạm thời → retry số lần có giới hạn rồi xử lý thành công.
- Lỗi bền vững → sau số lần cho phép, message đi đến **DLQ**, payload và thông tin nguồn có thể điều tra.
- NACK với `requeue=true` → broker **redeliver** message; consumer phải chấp nhận có xử lý lặp.
- Message trùng → **idempotency** ngăn lặp tác động nghiệp vụ.
- Khi gửi message ra broker → cần **publisher confirms/returns**, queue topology bền vững và reconciliation phù hợp để tránh “mất” ngay từ phía producer.
- DLQ được theo dõi, có cảnh báo, quyền truy cập và quy trình **replay có kiểm soát**. Không coi “message đã vào DLQ” là “nghiệp vụ đã hoàn tất”.

**Mục tiêu của bài học:**

1. Phân biệt **retry**, **broker redelivery**, **dead-letter**, **replay**, **ACK/NACK/REJECT** và **idempotency**.
2. Hiểu Spring AMQP `@RabbitListener`, `AcknowledgeMode.AUTO/MANUAL`, `RetryInterceptorBuilder` và `RejectAndDontRequeueRecoverer`.
3. Giải thích vì sao retry trong cùng delivery khác redelivery ở broker và tại sao `redelivered` không phải bộ đếm số lần xử lý.
4. Cấu hình RabbitMQ **main queue + dead-letter exchange (DLX) + DLQ**; quan sát `x-death` và payload gốc.
5. Dùng Java 17 + **Spring Boot 3.3.5** + Testcontainers RabbitMQ + JUnit Jupiter để thực thi **5 integration tests** trên broker thật.
6. Kiểm lỗi tạm thời được thử **tối đa 3 attempts** và thành công mà không vào DLQ.
7. Kiểm poison message thất bại ba lần và được broker chuyển sang DLQ thay vì biến mất.
8. Kiểm manual `basicNack(requeue=true)` tạo redelivery và ACK ở lần sau.
9. Kiểm gửi trùng một ID nhưng business effect chỉ được ghi nhận một lần trong ví dụ.
10. Biết giới hạn của test in-memory tracker và cách xây **outbox/inbox, durable idempotency, monitoring, publisher confirms, Kafka DLT** khi chuyển sang production.

**Bối cảnh:** Chủ đề cha là **Messaging**. Ví dụ runnable tập trung vào **RabbitMQ + Spring AMQP** để nhìn rõ ACK, NACK, redelivery và dead-letter. Phần Kafka giải thích tương ứng nhưng không giả vờ dùng chung API với RabbitMQ. Không cần HTTP server hay database production; test chỉ dùng container RabbitMQ disposable.

**Phiên bản cố định:** Java 17, Spring Boot **3.3.5**, Spring AMQP 3.1.x, Testcontainers và JUnit Jupiter. Các API mới hơn có thể khác; đặc biệt kiểm lại Spring Boot 4.x package/dependencies khi nâng cấp.

## 2. Từ producer tới consumer: các trạng thái khác nhau

~~~text
Producer
   |
   | publish (exchange + routing key)
   |  └─ nếu bật publisher confirm/return thì có phản hồi gửi
   v
RabbitMQ exchange
   |
   | route thành công
   v
Main queue --deliver--> Consumer @RabbitListener
   |                       |
   |                       +-- xử lý thành công --> ACK --> xóa khỏi main queue
   |                       |
   |                       +-- lỗi tạm thời
   |                       |       |
   |                       |       +-- in-process retry (attempt 1,2,3)
   |                       |                      |
   |                       |                      +-- thành công --> ACK
   |                       |
   |                       +-- lỗi bền vững / exhausted
   |                               |
   |                               +-- REJECT/NACK requeue=false
   |                                            |
   v                                            v
Dead-letter exchange  <---------------- broker dead-letter
   |
   | routing key "failed"
   v
Dead-letter queue (DLQ)
   |
   +-- lưu để quan sát/điều tra, sửa lỗi, replay có kiểm soát
~~~

**Retry** là **thử lại xử lý**. Nó có thể được thực hiện **bên trong listener container** ngay trên cùng một delivery (`RetryOperationsInterceptor`) hoặc theo lịch/broker. Tên “retry” tự nó không nói message đã đi qua broker bao nhiêu lần.

**Redelivery** là **broker gửi lại một delivery** khi message chưa ACK và được requeue (ví dụ consumer NACK requeue=true hoặc channel/connection bị đóng khi có unacked messages). RabbitMQ có redelivered flag, nhưng cờ này không phải bộ đếm attempts và không chứng minh side effect chưa từng xảy ra. Cùng một message có thể được xử lý nhiều lần trước khi một ACK thành công.

**Dead-letter** là cơ chế broker gửi message từ source queue qua **dead-letter exchange (DLX)** khi bị reject/nack `requeue=false`, hết TTL, vượt queue length limit hoặc quorum queue delivery limit (tùy loại queue/cấu hình). DLX là **exchange**, còn DLQ là **queue** được bind để nhận từ exchange đó. Không phải mọi message lỗi đều tự động có DLQ: **phải tạo đúng topology và routing**.

**Replay** là thao tác lấy message lỗi sau khi điều tra rồi đưa lại hệ thống (có thể giữ hoặc thay ID theo hợp đồng nghiệp vụ). Không nên tự chạy vòng vô hạn DLQ→main queue với poison message. Replay cần chính sách, khả năng audit, giới hạn và idempotency.

**“Lỗi không bị mất” có hai mặt:** payload chưa hoàn thành phải ở đâu đó có thể tìm được (main queue/retry queue/DLQ/ledger), và **nguyên nhân thất bại** phải truy vết được. RabbitMQ `x-death` có metadata dead-letter, nhưng **không tự chứa Java stack trace**. Muốn giữ thông tin exception, cần logs/metrics/tracing ổn định hoặc thiết kế recoverer/failed-message record có thông tin được phép lưu.

## 3. ACK, NACK và requeue: hiểu trước khi bật retry

| Tình huống RabbitMQ | Hành động | Điều broker hiểu |
|---|---|---|
| AUTO ACK mode, method trả bình thường | Container gửi `basicAck` | Message đã xử lý, xóa khỏi queue |
| AUTO mode, method ném exception | Container xử lý exception theo policy | Có thể reject/requeue hoặc dead-letter |
| `defaultRequeueRejected=true` (mặc định phổ biến) | Reject có requeue=true | Có thể bị giao lại liên tục |
| `defaultRequeueRejected=false` | Reject/NACK requeue=false | Bị loại khỏi main queue và đưa qua DLX **nếu đã cấu hình** |
| `AmqpRejectAndDontRequeueException` | Chỉ định không requeue | DLX tiếp nhận nếu routing tồn tại |
| `ImmediateRequeueAmqpException` | Yêu cầu requeue bất kể default | Có thể tạo broker redelivery |
| MANUAL mode: `basicAck(tag,false)` | Consumer tự xác nhận | Xóa message khỏi queue |
| MANUAL mode: `basicNack(tag,false,true)` | NACK, `requeue=true` | Đưa lại main queue, có thể redeliver |
| MANUAL mode: `basicReject(tag,false)` | Reject, `requeue=false` | Dead-letter nếu DLX hợp lệ |
| **Bắt exception rồi return bình thường** | AUTO container nghĩ thành công | **Có nguy cơ mất công việc** nếu chưa hoàn thành |

**AUTO ACK mode của Spring listener container không giống `autoAck=true` của RabbitMQ protocol.** Với `AcknowledgeMode.AUTO`, Spring tự ACK **sau khi listener chạy thành công**, và quyết định reject nếu listener thất bại. Với `AcknowledgeMode.NONE`, broker coi message đã ACK ngay khi deliver (“autoack” theo RabbitMQ). Không nhầm hai khái niệm.

Ví dụ **phản mẫu**:

~~~java
@RabbitListener(queues = "orders.work")
void consume(String body) {
    try {
        process(body);
    } catch (Exception ex) {
        log.error("Failed: {}", body, ex);
        // Không throw nữa: container có thể ACK.
    }
}
~~~

Đây là snippet minh họa, không phải file chạy độc lập. Logging tốt nhưng **chỉ log không phải chính sách retry/retain failure**. Nếu `process` thất bại, caller cần throw (để container xử lý) hoặc chủ động ghi failed record rồi ACK theo một **quy trình bù trừ có transaction bảo đảm**, không nuốt lỗi vô điều kiện.

### 3.1. Khi nào không nên requeue?

Lỗi do thiếu config tạm thời, broker dependency không đáp ứng hoặc service trả 503 có thể retry. Trái lại, JSON không thể parse, dữ liệu vi phạm schema hoặc trạng thái nghiệp vụ không thể hợp lệ thường không hết lỗi bằng cách gọi lại ngay. Với poison message, bounded retry rồi DLQ và alert là cách an toàn hơn việc `requeue=true` vô hạn.

Đừng dùng `defaultRequeueRejected=false` **nếu chưa cấu hình DLX/failed record** rồi tuyên bố lỗi được lưu lại: khi broker không thể dead-letter, message có thể bị drop. Đây là lý do test phải **nhận được message thật ở DLQ**, không chỉ kiểm listener đã ném exception.

### 3.2. Retry nội bộ không đồng nghĩa broker redelivery

~~~text
One RabbitMQ delivery (redelivered=false)
   -> Spring listener attempt 1: IllegalStateException
   -> Spring listener attempt 2: IllegalStateException
   -> Spring listener attempt 3: SUCCESS
   -> basicAck (one broker delivery)

NACK requeue=true của một delivery:
   -> broker delivers message (delivery #1, redelivered=false)
   -> consumer basicNack(requeue=true)
   -> broker delivers message again (delivery #2, redelivered=true)
   -> consumer basicAck
~~~

Ở sơ đồ đầu, số attempts là **3** nhưng `x-death` không tăng vì message không dead-letter, và broker không nhất thiết đã gửi message ba lần. Ở sơ đồ sau, broker có **2 deliveries**, nhưng không hề cần Spring RetryOperationsInterceptor.

### 3.3. Stateless và stateful retry

**Stateless retry** chạy nhiều attempts trong **cùng listener invocation/delivery**, thuận tiện khi không có transaction bên ngoài bắt buộc rollback giữa attempts. Ví dụ demo dùng 3 attempts và backoff nhỏ để test nhanh.

**Stateful retry** giữ retry state gắn với message identity giữa những deliveries; phù hợp hơn khi một transaction đang mở bên ngoài retry và bắt buộc rollback đúng mỗi delivery. Stateful retry cần **message ID đáng tin** hoặc `MessageKeyGenerator`; thiếu ID có thể gây policy fatal/consumer stop tùy cấu hình. Không chuyển từ stateless sang stateful chỉ bằng việc thay một chữ mà không test message identity, transaction, requeue và recovery.

**Spring Retry maxAttempts(3)** bao gồm **lần xử lý đầu tiên và hai lần thử lại**. Đừng diễn giải là 3 retries cộng thêm lần đầu, rồi viết assertions sai thành 4.

## 4. Dead-letter exchange, DLQ và x-death

Một topology RabbitMQ tối thiểu:

~~~text
main queue = learning.work.q
  x-dead-letter-exchange    = learning.dead.x
  x-dead-letter-routing-key = failed

direct exchange = learning.dead.x
  binding failed -> learning.dead.q

dead-letter queue = learning.dead.q
  Không có @RabbitListener mặc định: người vận hành/test đọc có chủ đích
~~~

Khi một message bị reject `requeue=false`, RabbitMQ lấy exchange/routing key đã cấu hình trên **source queue**, chuyển message sang DLX và route tới DLQ. Nếu sai tên exchange, thiếu binding hoặc chính DLQ không khả dụng, bạn không thể giả định message luôn còn. Production nên kiểm topology bằng declaration, broker metrics và test end-to-end.

**`x-death` do broker gắn khi dead-letter** thường gồm `queue`, `reason`, `count`, `time` và exchange/routing metadata. `reason` có thể là `rejected` cho basicReject/basicNack không requeue. `count` phản ánh số lần broker dead-letter theo nhóm thông tin, **không phải số lần Java method bị retry bên trong container**.

**Không làm giả `x-death` để đánh lừa logic.** Nó là metadata broker; test nên kiểm message thật đi qua broker. Với RabbitMQ 4.x, cách broker xử lý một số headers do client tự gửi đã thay đổi; đừng lấy header từ app client làm nguồn sự thật tương đương broker-generated x-death.

### 4.1. DLQ không giữ stack trace mặc định

Trong mẫu này dùng `RejectAndDontRequeueRecoverer`: sau khi retry hết, recoverer ném `AmqpRejectAndDontRequeueException`; container reject và **RabbitMQ DLX** chuyển message vào DLQ. Message giữ payload gốc cùng metadata về dead-letter, nhưng **không tự nhúng nguyên nhân `IllegalStateException` của Java**.

Muốn giữ nguyên nhân, bạn có các lựa chọn:
- Structured log/error event với `messageId`, correlation ID, exception type và trace ID, không in secrets.
- Persistent failed-message table hoặc event có key/id, error code, attempt count và thời gian; transaction consistency rõ.
- Spring AMQP `RepublishMessageRecoverer` republish message tới error exchange, có thể gắn exception-related headers. **Khác broker DLX**: nếu recoverer xử lý thành công và trả về, message gốc có thể được **ACK**; nếu republish thất bại hoặc thiếu publisher confirms, không được mặc định coi failed payload đã an toàn.
- Dùng metric/alert và dashboard DLQ queue depth, oldest message age, DLX routing failures.

**Không replay tự động mọi lỗi.** Với poison data, hãy điều tra nguyên nhân trước; nếu chưa sửa schema/consumer, replay chỉ tái tạo vòng lỗi.

## 5. Chiến lược kiểm thử: xác minh state, không chỉ verify(exception)

| Trường hợp | Điều phải kiểm |
|---|---|
| Healthy | 1 attempt, business effect 1, không DLQ |
| Transient lỗi 2 lần | 3 attempts, xử lý cuối thành công, không DLQ |
| Poison luôn lỗi | 3 attempts, business effect 0, **DLQ có payload gốc + x-death** |
| Broker redelivery | 2 broker deliveries, redelivered flag ở lần 2, consumer ACK |
| Duplicate publish | 2 delivery/attempt observations, **business effect chỉ 1** |
| Producer unroutable | Publisher return/confirm có cảnh báo, không coi `convertAndSend` thành đã đến queue |
| Consumer bị kill trước ACK | Broker có thể redeliver, phải idempotent |
| DLQ unreachable | Test/monitor phải phát hiện; không tuyên bố no-loss |
| Retry bị vượt quá budget | Có dead-letter/failed record/alert, không requeue vô hạn |
| Replay message đã xử lý | Không lặp side effect, có audit |

Chỉ mock một method `process()` của listener với Mockito không chứng minh RabbitMQ ACK/NACK/DLX hoạt động. Vì vậy ví dụ runnable dùng **RabbitMQContainer thật** qua Testcontainers. Tests còn dùng một `DeliveryTracker` lưu đếm attempts và effects **trong bộ nhớ** để dễ quan sát; tracker chỉ là phép đo của bài học, **không phải durable ledger**. Production phải dùng DB unique constraint/inbox/outbox và chính sách commit/ack phù hợp.

### 5.1. Tránh test bất đồng bộ bằng Thread.sleep cố định

`@RabbitListener` chạy ở thread riêng. Gửi message rồi ngay lập tức assert số attempts có thể flaky vì consumer chưa nhận. Ví dụ dùng **Awaitility** (`await().atMost(Duration.ofSeconds(15)).untilAsserted(...)`) để chờ một trạng thái observable với deadline. `Thread.sleep(1000)` không biết đã đủ hay dư; trên CI chậm có thể fail ngẫu nhiên.

Riêng DLQ, `RabbitTemplate.receive(queue, timeoutMillis)` polling broker tới khi có message hoặc hết hạn; đó là cách chủ động kiểm message thật đã tới DLQ. Lệnh receive **lấy message ra khỏi DLQ và ACK trong test**. Trong production, không sử dụng một monitoring job tiêu thụ DLQ chỉ để “đếm lỗi”; dùng RabbitMQ management/metrics cho quan sát không phá dữ liệu.

## 6. Project chạy được: Java 17 + Spring Boot 3.3.5 + RabbitMQ Testcontainers

Ví dụ có **hai queues inbound** để tách hai cơ chế:
- `learning.work.q`: Spring **AUTO ack + stateless retry 3 attempts + DLX**.
- `learning.redelivery.q`: Spring **MANUAL ack**, NACK requeue ở delivery đầu, ACK khi broker giao lần hai.
- `learning.dead.q`: DLQ nhận các message rejected từ work queue; **không có listener auto consume**.
- `learning.dead.x`: direct DLX bind routing key `failed` tới DLQ.

Publisher gửi hai chuỗi dạng `jobId|kind` vào work queue. `kind` nhận:
- `ok`: xử lý ngay.
- `transient`: fail hai lần đầu rồi thành công ở lần thứ ba.
- `poison`: fail mọi lần và đi DLQ.

Trong ví dụ, “business effect” chỉ là một counter thread-safe. Đó là dụng cụ học tập để assert idempotency; muốn chịu crash/restart phải thay bằng DB transaction/unique key.

### 6.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/java/demo/messaging/MessagingDemoApplication.java
src/main/java/demo/messaging/MessagingTopology.java
src/main/java/demo/messaging/RabbitListenerConfiguration.java
src/main/java/demo/messaging/DeliveryTracker.java
src/main/java/demo/messaging/WorkListener.java
src/main/java/demo/messaging/RedeliveryListener.java
src/main/java/demo/messaging/WorkPublisher.java
src/test/java/demo/messaging/MessagingReliabilityTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'rabbit-retry-dlq-test'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

- **starter-amqp**: Spring AMQP, RabbitTemplate, `@RabbitListener`, listener container factories và Spring Retry integrations.
- **starter-test**: JUnit Jupiter, Spring Test và Awaitility dùng chờ async assertions.
- **spring-boot-testcontainers**: `@ServiceConnection` cho typed RabbitMQContainer trong Boot 3.3.x.
- **Testcontainers JUnit + RabbitMQ module**: chạy RabbitMQ Docker thật và quản lý container lifecycle.
- Dependency versions do Spring Boot BOM quản lý. Bài không yêu cầu web starter hoặc database client.

**Điều kiện chạy:** Java 17, Gradle phù hợp, Docker daemon/container runtime Testcontainers hỗ trợ, quyền pull image `rabbitmq:3.13-management-alpine`, mạng/port mapping. Không dùng RabbitMQ production và không hard-code `localhost:5672` vì Testcontainers map host port động.

### 6.2. Main application

**src/main/java/demo/messaging/MessagingDemoApplication.java**

~~~java
package demo.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingDemoApplication.class, args);
    }
}
~~~

Ứng dụng không cần server HTTP. Spring Boot Rabbit auto-configuration tìm connection factory, RabbitTemplate, RabbitAdmin và listener infrastructure theo starter. Test sẽ đưa RabbitMQ endpoint từ container vào auto-configuration nhờ `@ServiceConnection`.

### 6.3. Queue, DLX, DLQ: declaration thật lên broker

**src/main/java/demo/messaging/MessagingTopology.java**

~~~java
package demo.messaging;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MessagingTopology {

    public static final String WORK_QUEUE =
            "learning.work.q";
    public static final String REDELIVERY_QUEUE =
            "learning.redelivery.q";
    public static final String DEAD_EXCHANGE =
            "learning.dead.x";
    public static final String DEAD_QUEUE =
            "learning.dead.q";
    public static final String DEAD_ROUTING_KEY = "failed";

    @Bean
    Declarables messagingDeclarables() {
        DirectExchange dlx =
                new DirectExchange(DEAD_EXCHANGE, true, false);

        Queue dlq = QueueBuilder.durable(DEAD_QUEUE).build();

        Binding deadBinding =
                BindingBuilder.bind(dlq)
                        .to(dlx)
                        .with(DEAD_ROUTING_KEY);

        Queue workQueue = QueueBuilder.durable(WORK_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING_KEY)
                .build();

        Queue redeliveryQueue =
                QueueBuilder.durable(REDELIVERY_QUEUE).build();

        return new Declarables(
                dlx, dlq, deadBinding,
                workQueue, redeliveryQueue);
    }
}
~~~

**Cách hoạt động:**

1. `DirectExchange` tên `learning.dead.x` nhận dead-letter từ work queue.
2. DLQ `learning.dead.q` được bind với routing key `failed`.
3. Work queue có arguments `x-dead-letter-exchange` và `x-dead-letter-routing-key`. Khi consumer reject không requeue, broker route message đến DLQ.
4. Redelivery queue là một queue riêng, không dùng retry advice và không cần DLX cho test NACK→ACK.
5. `Declarables` được RabbitAdmin của Spring khai báo trên broker. Khi publish trực tiếp với `RabbitTemplate.convertAndSend(queueName, payload)`, RabbitTemplate dùng **default exchange** và routing key là queue name; RabbitMQ tự bind default exchange với các queue theo tên. Không cần exchange riêng cho publishers trong ví dụ.

**Trong production:** durable queue cùng persistent messages là điều kiện quan trọng nhưng không phải bảo đảm “không bao giờ mất message”. Có thể cần quorum queues, replication, publisher confirms, returns, đúng broker policies, theo dõi routing và recovery. RabbitMQ khuyến khích cấu hình DLX bằng **broker policy** thay vì hard-code x-arguments khi cần đổi topology linh hoạt; code dùng x-arguments để dễ tái lập bằng Testcontainers.

### 6.4. Container factories: một cái retry, một cái manual ack

**src/main/java/demo/messaging/RabbitListenerConfiguration.java**

~~~java
package demo.messaging;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitListenerConfiguration {

    @Bean("workFactory")
    SimpleRabbitListenerContainerFactory workFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        var factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(25L, 1.0, 25L)
                        .recoverer(
                                new RejectAndDontRequeueRecoverer())
                        .build());

        return factory;
    }

    @Bean("manualAckFactory")
    SimpleRabbitListenerContainerFactory manualAckFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        var factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setPrefetchCount(1);

        return factory;
    }
}
~~~

**Các quyết định không được bỏ qua:**

- `workFactory` có **AUTO ack**: nếu listener thành công sau retry thì ACK; nếu hết retries, `RejectAndDontRequeueRecoverer` yêu cầu không requeue.
- `.maxAttempts(3)` = **lần đầu + 2 retries**. `.backOffOptions(25,1.0,25)` chỉ để test gọn; production thường cần backoff dài hơn, jitter và phân loại lỗi retryable/fatal.
- `.setDefaultRequeueRejected(false)` làm policy an toàn hơn nếu exception không được advice xử lý như mong đợi. Nó không tạo DLQ; việc broker dead-letter phụ thuộc topology ở trên.
- `manualAckFactory` không có retry advice; listener có trách nhiệm **ack/nack đúng mọi path**. `prefetch=1` giúp kịch bản giáo dục dễ đoán, không phải cấu hình hiệu năng tối ưu.
- Hai factories dùng `SimpleRabbitListenerContainerFactoryConfigurer` do Boot cung cấp để giữ các thiết lập connection/observability liên quan. Không tạo một `new ConnectionFactory` trỏ `localhost` làm mất service connection.

**Quan trọng về retry strategy:** Stateless retry không nên áp dụng bừa khi có transaction bao ngoài callback cần rollback giữa deliveries. Khi nghiệp vụ dùng DB transaction với broker ack, phải thiết kế transaction boundary, outbox/inbox và retry strategy thống nhất; tham khảo stateful retry khi phù hợp.

### 6.5. Thread-safe tracker dùng cho assertions (không phải durable store)

**src/main/java/demo/messaging/DeliveryTracker.java**

~~~java
package demo.messaging;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class DeliveryTracker {

    private final ConcurrentMap<String, AtomicInteger> attempts =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> effects =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, AtomicInteger> brokerDeliveries =
            new ConcurrentHashMap<>();

    private final Set<String> completed =
            ConcurrentHashMap.newKeySet();

    private final Set<String> seenRedelivery =
            ConcurrentHashMap.newKeySet();

    public int recordAttempt(String id) {
        return attempts
                .computeIfAbsent(id, key -> new AtomicInteger())
                .incrementAndGet();
    }

    public int attempts(String id) {
        AtomicInteger counter = attempts.get(id);
        return counter == null ? 0 : counter.get();
    }

    public boolean isCompleted(String id) {
        return completed.contains(id);
    }

    public void completeOnce(String id) {
        effects.computeIfAbsent(id, key -> new AtomicInteger())
                .compareAndSet(0, 1);
        completed.add(id);
    }

    public int effects(String id) {
        AtomicInteger counter = effects.get(id);
        return counter == null ? 0 : counter.get();
    }

    public int recordBrokerDelivery(String id) {
        return brokerDeliveries
                .computeIfAbsent(id, key -> new AtomicInteger())
                .incrementAndGet();
    }

    public int brokerDeliveries(String id) {
        AtomicInteger counter = brokerDeliveries.get(id);
        return counter == null ? 0 : counter.get();
    }

    public void markRedelivered(String id) {
        seenRedelivery.add(id);
    }

    public boolean sawRedelivered(String id) {
        return seenRedelivery.contains(id);
    }
}
~~~

`ConcurrentHashMap` và `AtomicInteger` tránh data races khi listener chạy background threads còn test thread đọc trạng thái. `recordAttempt` ghi số lần Java listener được gọi; `recordBrokerDelivery` ghi số lần RabbitMQ giao message đến manual-ack consumer.

**Không đưa tracker này vào production và gọi đó là idempotency vĩnh viễn.** Nó mất state khi process restart, không phối hợp được nhiều consumer instances và `completed`/`effects` không được commit transactionally cùng business write. Trong production cần một **persistent inbox/idempotency table** với unique constraint trên message ID, hoặc business operation vốn idempotent, xử lý trong một transaction phù hợp.

### 6.6. Work listener: transient thành công, poison đi DLQ

**src/main/java/demo/messaging/WorkListener.java**

~~~java
package demo.messaging;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WorkListener {

    private final DeliveryTracker tracker;

    public WorkListener(DeliveryTracker tracker) {
        this.tracker = tracker;
    }

    @RabbitListener(
            queues = MessagingTopology.WORK_QUEUE,
            containerFactory = "workFactory")
    public void consume(String payload) {
        String[] fields = payload.split("\\|", 2);
        if (fields.length != 2
                || fields[0].isBlank()
                || fields[1].isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid message format");
        }

        String id = fields[0];
        String kind = fields[1];
        int attempt = tracker.recordAttempt(id);

        // Đã xử lý ID trước đó: không lặp business effect.
        if (tracker.isCompleted(id)) {
            return;
        }

        if ("poison".equals(kind)) {
            throw new IllegalArgumentException(
                    "Permanent poison payload id=" + id);
        }

        if ("transient".equals(kind) && attempt < 3) {
            throw new IllegalStateException(
                    "Simulated temporary dependency failure");
        }

        if (!"ok".equals(kind)
                && !"transient".equals(kind)) {
            throw new IllegalArgumentException(
                    "Unsupported kind=" + kind);
        }

        tracker.completeOnce(id);
    }
}
~~~

**Lưu ý:** Đoạn `completeOnce` chỉ là một counter test. Khi consumer thấy duplicate `id`, method trả bình thường và AUTO container ACK duplicate; đây là behavior idempotent trong phạm vi một JVM instance. Hai payload khác nhau dùng cùng id không được tự động coi là cùng nghiệp vụ nếu contract không cho phép — phải xác định message ID và versioning. Với hệ thật, dedup key cần đủ mạnh và được bảo vệ bằng unique constraint/transaction.

**Vì sao exception được ném thay vì bị catch rồi bỏ qua?** Để retry advice nhìn thấy lỗi. Với "transient", calls 1 và 2 ném lỗi, call 3 thành công. Với "poison", cả ba attempts đều ném, recoverer yêu cầu REJECT không requeue, broker route sang DLQ. Như vậy test có thể xác minh hai outcome khác nhau.

**Không dùng `attempt` trong tracker làm retry counter sản xuất.** Ở test nó chạy trong một process, không bị reset khi restart. Một production retry policy có thể dựa vào Spring RetryContext, message headers, persisted attempts hoặc broker delivery limits, tùy cơ chế.

### 6.7. Manual-ack listener: chủ động NACK để broker redeliver

**src/main/java/demo/messaging/RedeliveryListener.java**

~~~java
package demo.messaging;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class RedeliveryListener {

    private final DeliveryTracker tracker;

    public RedeliveryListener(DeliveryTracker tracker) {
        this.tracker = tracker;
    }

    @RabbitListener(
            queues = MessagingTopology.REDELIVERY_QUEUE,
            containerFactory = "manualAckFactory")
    public void consume(Message message, Channel channel)
            throws IOException {

        String id = new String(
                message.getBody(), StandardCharsets.UTF_8);

        long deliveryTag = message.getMessageProperties()
                .getDeliveryTag();

        int count = tracker.recordBrokerDelivery(id);

        if (count == 1) {
            // Trả về broker để giao lại; không phải Spring Retry.
            channel.basicNack(deliveryTag, false, true);
            return;
        }

        // Lần thứ hai: ACK xong mới ghi dấu cho test.
        channel.basicAck(deliveryTag, false);

        if (Boolean.TRUE.equals(
                message.getMessageProperties().isRedelivered())) {
            tracker.markRedelivered(id);
        }
    }
}
~~~

`basicNack(deliveryTag, false, true)` nghĩa:
- `deliveryTag`: tag của **delivery trên channel hiện tại**, không phải business ID.
- `multiple=false`: chỉ áp dụng một delivery, không ack/nack hàng loạt những tags trước.
- `requeue=true`: trả message cho RabbitMQ để có thể được giao lại.

`basicAck(deliveryTag, false)` xác nhận thành công. Với một queue, một consumer, prefetch 1 và container disposable, bài test kỳ vọng delivery thứ hai có `redelivered=true`. Cờ này **không phải retry count**, có thể còn chịu ảnh hưởng của connection/channel recovery trong hệ thực. Không dùng `redelivered` làm unique identifier hoặc cơ chế đảm bảo exactly-once.

**Rủi ro của MANUAL ack:** Nếu code quên ACK/NACK, message có thể nằm trạng thái unacked cho tới khi channel đóng; nếu NACK true mọi lần, message loop. Trong production cần `try/catch` cho mọi lỗi, deadline/backoff, metrics và policy xử lý những đường không thể ACK. Ví dụ giới hạn một lần requeue bằng tracker chỉ nhằm minh họa; không phải bounded retry production vì tracker biến mất khi process restart.

### 6.8. Publisher dùng default exchange và routing key queue name

**src/main/java/demo/messaging/WorkPublisher.java**

~~~java
package demo.messaging;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class WorkPublisher {

    private final RabbitTemplate template;

    public WorkPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void sendWork(String id, String kind) {
        template.convertAndSend(
                MessagingTopology.WORK_QUEUE,
                id + "|" + kind);
    }

    public void sendForRedelivery(String id) {
        template.convertAndSend(
                MessagingTopology.REDELIVERY_QUEUE, id);
    }
}
~~~

Publisher gửi String dạng plain text thông qua RabbitTemplate default converter. Trong ví dụ, `id|kind` không dùng dấu `|` trong id. Payload và queue names là fixtures học tập; trong hệ thật dùng JSON/Avro/Protobuf có schema version, validation và correlation ID rõ.

**Quan trọng:** `convertAndSend` trả về bình thường **không tự chứng minh message đã được durable-routed tới đúng queue**, nhất là khi cần kiểm mất message phía producer. Muốn nâng lên bài toán no-loss phải bật publisher confirms, mandatory returns hoặc cơ chế outbox, kiểm broker topology và error paths. Tests runnable dưới đây tập trung ở **consumer outcome** và broker DLQ, không tự nhận là đã kiểm đủ mọi failure trong network/cluster.

## 7. Năm integration tests chạy RabbitMQ thật

Một test suite cần kiểm **trạng thái broker** lẫn **trạng thái xử lý**. Không nên chỉ `verify(listener, times(3))` bằng Mockito: điều đó không thấy message có vào DLQ hay không. Ở đây có RabbitMQContainer thật, RabbitTemplate gửi message và đọc DLQ, Awaitility chờ listener hoàn tất.

**src/test/java/demo/messaging/MessagingReliabilityTest.java**

~~~java
package demo.messaging;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class MessagingReliabilityTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    "rabbitmq:3.13-management-alpine");

    @Autowired
    WorkPublisher publisher;

    @Autowired
    DeliveryTracker tracker;

    @Autowired
    RabbitTemplate template;

    @Autowired
    AmqpAdmin admin;

    private int queuedCount(String queue) {
        Properties properties = admin.getQueueProperties(queue);
        assertNotNull(properties, "Missing queue: " + queue);

        return ((Number) properties.get(
                RabbitAdmin.QUEUE_MESSAGE_COUNT)).intValue();
    }

    @Test
    void healthyMessageIsProcessedOnceWithoutDeadLetter() {
        String id = "healthy-326";

        publisher.sendWork(id, "ok");

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertTrue(tracker.isCompleted(id));
                    assertEquals(1, tracker.attempts(id));
                    assertEquals(1, tracker.effects(id));
                });

        assertEquals(0, queuedCount(MessagingTopology.DEAD_QUEUE));
    }

    @Test
    void transientFailureRetriesThreeAttemptsThenSucceeds() {
        String id = "transient-326";

        publisher.sendWork(id, "transient");

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertTrue(tracker.isCompleted(id));
                    assertEquals(3, tracker.attempts(id));
                    assertEquals(1, tracker.effects(id));
                });

        assertEquals(0, queuedCount(MessagingTopology.DEAD_QUEUE));
    }

    @Test
    void poisonFailureIsDeadLetteredWithOriginalPayload() {
        String id = "poison-326";
        String original = id + "|poison";

        publisher.sendWork(id, "poison");

        Message dead = template.receive(
                MessagingTopology.DEAD_QUEUE, 15_000);

        assertNotNull(
                dead,
                "Failed payload must reach DLQ, not disappear");

        assertEquals(
                original,
                new String(dead.getBody(), StandardCharsets.UTF_8));

        List<Map<String, ?>> deaths =
                dead.getMessageProperties().getXDeathHeader();

        assertNotNull(deaths);
        assertFalse(deaths.isEmpty());
        assertEquals("rejected", deaths.get(0).get("reason"));
        assertEquals(
                MessagingTopology.WORK_QUEUE,
                deaths.get(0).get("queue"));

        assertEquals(3, tracker.attempts(id));
        assertFalse(tracker.isCompleted(id));
        assertEquals(0, tracker.effects(id));
    }

    @Test
    void brokerNackRequeuesAndSetsRedeliveredFlag() {
        String id = "redelivery-326";

        publisher.sendForRedelivery(id);

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertEquals(2, tracker.brokerDeliveries(id));
                    assertTrue(tracker.sawRedelivered(id));
                });

        assertEquals(
                0, queuedCount(MessagingTopology.REDELIVERY_QUEUE));
    }

    @Test
    void duplicateMessageDoesNotRepeatBusinessEffect() {
        String id = "duplicate-326";

        publisher.sendWork(id, "ok");
        publisher.sendWork(id, "ok");

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    assertEquals(2, tracker.attempts(id));
                    assertTrue(tracker.isCompleted(id));
                    assertEquals(1, tracker.effects(id));
                });

        assertEquals(0, queuedCount(MessagingTopology.DEAD_QUEUE));
    }
}
~~~

**Đúng 5 phương thức JUnit Jupiter `@Test`.** `queuedCount` là helper, không phải test. Không có `@TestMethodOrder`, `Thread.sleep` hoặc dữ liệu test phụ thuộc thứ tự. Mỗi test dùng message ID khác nhau, test container RabbitMQ chỉ dành cho class này, và test poison **đọc/xóa message khỏi DLQ có chủ đích** để assert nội dung. Nếu thay bằng production DLQ, không nên để test consume message lỗi của hệ thống đang chạy.

### 7.1. Test healthy: ACK và không vào DLQ

Message `healthy-326|ok` được publish vào work queue. Listener `recordAttempt` tăng lên 1, business counter tăng lên 1 và trả về bình thường; container AUTO ACK. Test chờ `isCompleted=true`, `attempts=1`, `effects=1`, rồi kiểm queue depth DLQ bằng 0.

**Đừng chỉ assert `isCompleted=true`**: điều đó không bắt được một listener cố tình chạy hai lần hoặc business effect bị lặp. Trong ví dụ, cả attempt count và effect count đều được kiểm để thấy behavior cụ thể.

### 7.2. Test transient: ba attempts, chỉ một broker delivery

Message `transient-326|transient`: attempt 1/2 ném `IllegalStateException` giả lập dependency tạm thời; retry advice thử lại; attempt 3 thành công. **Max attempts 3** bao gồm lần đầu. Test đợi completed, assert attempts=3, effects=1 và DLQ không có message.

**Không kết luận rằng RabbitMQ đã giao message ba lần chỉ vì method chạy ba lần.** Trong cấu hình **stateless retry** này, cùng delivery được xử lý lại bên trong advice, nên redelivered flag ở broker không cần true và `x-death` không tăng.

### 7.3. Test poison: bằng chứng lỗi không bị âm thầm mất

Message `poison-326|poison` ném exception trên cả ba attempts. Khi retries cạn, `RejectAndDontRequeueRecoverer` yêu cầu không requeue; RabbitMQ dead-letters qua DLX sang DLQ. Test dùng `RabbitTemplate.receive(DLQ, timeout)` lấy **message thật đã được broker route**, rồi assert:

1. **Payload bytes** giải mã UTF-8 bằng original string.
2. **x-death** được broker gắn và không rỗng.
3. `x-death.reason` là `rejected`.
4. `x-death.queue` đúng source work queue.
5. Counter thể hiện **3 listener attempts**.
6. Business effect **0**, message chưa được đánh dấu completed.

**Đây là bằng chứng mạnh hơn “listener đã throw exception”** vì nó kiểm trạng thái trên broker. Nhưng nó **không phải chứng minh toàn hệ thống không bao giờ mất message**. Nếu exchange/binding không tồn tại, broker tắt hoặc DLQ không durable, một thiết kế thiếu xác nhận/giám sát vẫn có thể mất message trong tình huống khác. Test cần được mở rộng cho outage/routing/callback failures theo SLO thực.

### 7.4. Test manual redelivery: NACK rồi ACK

Redelivery listener nhận `redelivery-326` lần đầu, gọi `basicNack(tag,false,true)`. Broker requeue và gửi lại lần hai; listener ACK. Tracker ghi **2 broker deliveries** và cờ redelivered=true ở lần thứ hai. Test không dùng Spring retry advice cho queue này, nên nó thực sự kiểm **broker redelivery**.

**Lưu ý:** RabbitMQ redelivered flag có ý nghĩa best-effort theo protocol: nó báo delivery có thể đã từng được giao, không phải cam kết side effect đã hay chưa chạy, và không cho biết attempt count. Idempotency vẫn là bắt buộc trong xử lý thực.

### 7.5. Test duplicate publish: idempotency là yếu tố riêng

Publisher gửi cùng `duplicate-326|ok` hai lần. Listener ghi cả hai attempts, nhưng `tracker.isCompleted` làm lần thứ hai không tăng business effect. Test assert attempts=2, effects=1.

**Không gọi đây là exactly-once delivery.** RabbitMQ đã nhận **hai messages**; code chỉ đảm bảo một **business effect** trong môi trường test. Production có thể chạy nhiều consumer replicas, crash giữa DB commit và ACK, hoặc tái giao cùng message sau network failure. Muốn kiểm tra end-to-end, dùng persistent dedup/inbox id với unique constraint và transaction phù hợp; test crash/restart và concurrent deliveries.

## 8. Chạy tests và điều kiện môi trường

Nếu project đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu mới tạo `settings.gradle`, `build.gradle` và các files nguồn mà **chưa có Gradle Wrapper**, `./gradlew` chưa tồn tại; dùng Gradle tương thích để tạo wrapper hoặc chạy `gradle test`.

Chạy riêng lớp:

~~~bash
./gradlew test --tests demo.messaging.MessagingReliabilityTest
~~~

Test yêu cầu Docker daemon hoạt động, có quyền tạo containers, tải được image RabbitMQ 3.13 management-alpine. Không nên đặt một timeout cố định rất nhỏ cho container startup trên máy CI tải image lần đầu. `Awaitility` timeout trong tests **15 giây là giới hạn cho việc xử lý message sau khi container/context đã sẵn sàng**, không phải giới hạn Docker pull/startup.

**Dự kiến từ source:** JUnit Jupiter phát hiện 5 test methods; healthy/transient/poison/redelivery/duplicate đều được thiết kế PASS khi RabbitMQ và network runtime hoạt động như đã nêu. Đây là kết quả **dự kiến từ mã nguồn**, không phải tuyên bố các test đã được chạy trên môi trường người đọc.

Báo cáo Gradle thường có tại:

~~~text
build/reports/tests/test/index.html
~~~

**Về noise trong log:** Test poison cố ý ném exception ba lần, do đó Spring AMQP có thể ghi WARN/ERROR với thông tin retry exhausted. Log này không đồng nghĩa toàn test thất bại; kiểm assertion DLQ và Gradle results. Ngược lại, nếu test chỉ có log ERROR nhưng không có assertion về broker state thì vẫn có thể “xanh giả”.

### 8.1. Vì sao @ServiceConnection quan trọng?

Spring Boot 3.3 nhận diện **typed `RabbitMQContainer`** nhờ `@ServiceConnection` trong module `spring-boot-testcontainers`, tạo **RabbitConnectionDetails** chứa host/port/credentials thực của container. Rabbit auto-configuration dùng những details đó để tạo connection factory.

Không hard-code host port 5672 trong test; Testcontainers chọn mapped port động. Nếu test tạo một custom `ConnectionFactory` bằng tay trỏ tới máy local, client có thể không sử dụng service connection. Một test xanh do vô tình kết nối RabbitMQ đang chạy ngoài Docker **không chứng minh** Testcontainers topology hoạt động.

### 8.2. Vì sao không dùng Mockito cho broker-level assertions?

Mockito có thể kiểm `verify(service, times(3)).process(id)` hoặc giả lập exception, nhưng không chạy RabbitMQ routing, ACK, DLQ hoặc x-death. Unit test nên dùng cho việc **phân loại lỗi/retry policy business**, còn integration test với RabbitMQContainer nên xác minh những chức năng thực của broker.

`@RabbitListenerTest` cùng `RabbitListenerTestHarness` có thể giúp spy/capture các listener invocations khi muốn test-level introspection, nhưng nó cũng **không thay thế kiểm chứng broker topology** nếu mục tiêu là dead-letter. Tránh đánh đồng “spy được gọi 3 lần” với “message đã được bảo toàn khi xử lý thất bại”.

## 9. “Lỗi không bị mất”: checklist theo từng ranh giới

### 9.1. Producer → broker

- **Publisher confirms:** Bật cơ chế broker xác nhận publisher message (ví dụ Spring Boot Rabbit `spring.rabbitmq.publisher-confirm-type=correlated`). Xử lý ACK/NACK từ broker và timeout callback theo policy. `convertAndSend` trả về không phải điều kiện đủ.
- **Publisher returns / mandatory:** Bật `spring.rabbitmq.publisher-returns=true` và `spring.rabbitmq.template.mandatory=true` khi muốn phát hiện message gửi tới exchange nhưng **không được route đến queue**. Confirm và return giải quyết các câu hỏi khác nhau.
- **Durability:** Exchange/queue durable, message persistent, broker HA/quorum policy theo SLO. Không dùng non-durable queue rồi khẳng định đã giữ message khi broker restart.
- **Outbox:** Nếu nghiệp vụ vừa commit DB vừa publish, dùng transactional outbox/CDC hoặc giải pháp đồng bộ tương đương để tránh DB commit xong nhưng message chưa gửi, hoặc message gửi rồi DB rollback.
- **Message ID:** Unique, stable, traceable qua mỗi retry/replay; tránh reuse ID cho hai công việc khác nhau. Correlation ID không nhất thiết là idempotency key.
- **Monitoring:** Ghi counters của publish failures, returned messages và confirm timeouts; có cảnh báo. Retry không thể sửa một lỗi unrouteable mãi mãi nếu topology sai.

Ví dụ cấu hình **minh họa** khi mở rộng RabbitMQ producer:

~~~properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
~~~

Chỉ thêm các dòng trên **chưa đủ**: application còn phải có confirm/return callbacks hoặc logic chờ confirm, xử lý failures và quyết định retry/outbox. Không sử dụng `RabbitTemplate` publisher confirms như một “fire-and-forget success detector” nếu chưa quan sát kết quả.

### 9.2. Broker → consumer

- **ACK sau khi nghiệp vụ hoàn tất**, không ACK ngay khi mới parse message hoặc mới gọi một async task chưa xong.
- Với `AcknowledgeMode.AUTO`, nếu xử lý lỗi thì ném exception hoặc dùng error/recoverer policy rõ; không catch-and-return.
- Retry chỉ lỗi **transient**; lỗi **fatal/permanent** nên dead-letter sớm theo classifier. Trong ví dụ, mọi exception đều được thử 3 lần để dễ học, nhưng production nên phân loại.
- **Bounded attempts** và backoff/jitter để tránh retry storm; tránh requeue vô hạn không có pause.
- DLX/DLQ declared, routing key đúng, có retention và alarms. `defaultRequeueRejected=false` mà thiếu DLX có thể drop message.
- Nếu manual ack, mọi đường đi phải được ACK/NACK hoặc có policy xử lý lỗi, không để unacked hang.
- **Poison test:** Assert message thật có mặt trong DLQ, nội dung và metadata đúng, không chỉ exception/log.
- **Duplicate test:** Tối thiểu kiểm lần giao lặp không làm tăng business effect. Muốn chắc hơn, test nhiều replicas và crash points.

### 9.3. Consumer → database / external side effect

**At-least-once delivery + idempotent processing** thường là lựa chọn thực tế. Không có atomic transaction mặc định giữa RabbitMQ ACK và một database hoàn toàn độc lập. Ví dụ:

~~~text
1. Consumer nhận message X.
2. Database COMMIT nghiệp vụ X thành công.
3. Consumer chết TRƯỚC khi broker nhận ACK.
4. RabbitMQ redeliver message X.
5. Nếu không có persistent idempotency, business effect bị thực hiện lần hai.
~~~

Giải pháp thường có **inbox table**:

~~~sql
CREATE TABLE processed_message (
    message_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Đây là schema gợi ý, không phải một phần project RabbitMQ runnable. Trong một DB transaction, consumer cố `INSERT processed_message(message_id,processed_at)`, xử lý business write, rồi commit. Nếu duplicate key nghĩa ID đã xử lý, bỏ qua business effect theo contract. Sau khi transaction commit, consumer ACK. Cần thiết kế đồng bộ/inbox locking cho concurrent deliveries và tránh ghi “đã xử lý” trước khi business transaction thành công.

**Với external API side effect** (chuyển tiền, gửi email, gọi remote service) mà database không thể rollback tác động, cần idempotency key ở downstream hoặc cơ chế compensation/reconciliation. Đừng nghĩ một transaction JDBC có thể rollback một HTTP call đã thành công.

### 9.4. DLQ → vận hành / replay

Một DLQ không có người theo dõi có thể giữ lỗi đến lúc TTL expire hoặc queue đầy. Cần:
- Alert theo **DLQ depth**, oldest message age, tốc độ tăng và loại lỗi.
- Dashboard/structured logging với messageId, traceId, error type, attempt count. Không lưu nguyên PII/secret trong error header.
- Chế độ cách ly message chứa dữ liệu nhạy cảm, retention và access control.
- Replay tool có review/approval, dry run, rate limiting, dedup và audit.
- Nếu lỗi là schema deployment mismatch, khắc phục consumer version trước replay; đừng replay lỗi bền vững vào main queue vô hạn.
- Chọn chính sách TTL; một số topology retry-delay qua DLQ TTL có thể gây **death loop** nếu không có max attempts/cutoff.

**Chú ý:** DLQ message được lấy bằng `RabbitTemplate.receive` sẽ bị ACK và rời DLQ. Trong ví dụ đó là hành động test có chủ đích. Một công cụ quan sát production không nên ăn mất messages của DLQ chỉ để thống kê.

## 10. Retry có backoff và retry queue khác instant redelivery

Một lỗi tạm thời có thể cần 2–30 giây hoặc vài phút để phục hồi. Nếu ngay lập tức `basicNack(requeue=true)` liên tục, broker/consumer có thể lặp hàng nghìn lần mỗi giây. Có ba kiến trúc cơ bản:

| Cách | Ưu điểm | Rủi ro |
|---|---|---|
| **In-process bounded retry** | Cấu hình gọn, tốt cho transient lỗi ngắn | Giữ consumer thread; với giao dịch phải thiết kế rollback |
| **Broker redelivery (nack requeue=true)** | Broker giao lại message, thuận tiện khi worker chết | Không có delay/budget tự động; có thể hot loop |
| **Delayed retry queue / TTL + DLX** | Giãn thời gian, giải phóng consumer thread | Phức tạp routing, x-death counting, poison loop |
| **Republish to retry exchange** | Chủ động headers, scheduling, routing | Phải bảo đảm publish/ack atomicity hoặc có reconciliation |
| **Kafka retry topics / DLT** | Phù hợp mô hình Kafka records | Khác AMQP ACK, offset, partition/ordering |

Chọn backoff phù hợp với loại lỗi; với service downstream đang lỗi toàn diện, circuit breaker/rate limit/bulkhead có thể cần thiết. Retry không nên làm tăng tải đáng kể đúng lúc hệ thống phụ thuộc đang suy yếu.

Trong Spring AMQP, `RetryInterceptorBuilder.stateless()` ở ví dụ dùng `.backOffOptions(25,1.0,25)` để test nhanh; đừng copy 25 ms vào production theo thói quen. Nếu quá trình xử lý có transaction database cần rollback giữa attempts, xem **stateful retry** cùng message ID và container transaction semantics, thay vì lấy stateless retry làm lời giải chung.

## 11. RabbitMQ so với Kafka: cùng mục tiêu, API khác

Không thể dùng `@RabbitListener`/`basicNack` trực tiếp cho Kafka. Trong Spring Kafka:
- Listener thường dùng `@KafkaListener` và consumer group/offset management.
- Failure handling có **`DefaultErrorHandler`**, có thể retry/seek theo chính sách backoff.
- **`DeadLetterPublishingRecoverer`** có thể publish failed record tới **DLT topic** sau khi retries exhausted.
- **`@RetryableTopic`** hỗ trợ non-blocking retry topics và DLT theo cấu hình Spring Kafka tương thích.
- Việc commit offset, retry sequencing, partition ordering và transactional producer/consumer khác RabbitMQ queue ACK.
- Broker Kafka có log retention; “DLT” là topic chứa failed records, không phải RabbitMQ DLQ/DLX.
- Test nên assert **record trên DLT topic**, key/value/headers/correlation/partition/offset policy, không chỉ mock handler exception.

Sơ đồ tương ứng:

~~~text
RabbitMQ:
main queue -> listener retry -> reject requeue=false
          -> DLX -> DLQ -> review/replay

Kafka:
main topic -> @KafkaListener / DefaultErrorHandler
           -> retry/seek or retry topic(s)
           -> DeadLetterPublishingRecoverer -> DLT topic
           -> review/replay
~~~

**Kafka-specific caveats:** Bảo đảm thứ tự trên một partition có thể bị ảnh hưởng bởi non-blocking retry topics; commit offset không tương đương RabbitMQ basicAck. Nếu một topic có nhiều partitions, không assert global ordering bừa. Với Kafka, dùng `EmbeddedKafka` hoặc Kafka Testcontainers tùy mục tiêu; để kiểm broker DLT behavior thật và persistence, broker integration thường phù hợp.

Tài liệu Spring Kafka có các APIs riêng cho exception classification, backoff, delivery attempts và DLT routing. Không “đổi tên dead queue thành dead topic” rồi tái sử dụng nguyên test RabbitMQ.

## 12. Negative tests và failure injection: bằng chứng chống mất lỗi

Các mutation nhỏ sau giúp kiểm suite có phát hiện nguy cơ hay không:

| Mutation/thay đổi | Test kỳ vọng thất bại hoặc cần thêm |
|---|---|
| Bỏ `RejectAndDontRequeueRecoverer` và để exception bị nuốt | Poison test không thấy message DLQ |
| Đổi `defaultRequeueRejected` thành true khi bỏ recoverer | Poison có thể requeue vô hạn, test timeout |
| Xóa `deadLetterExchange` khỏi work queue | Poison không đến DLQ |
| Đổi binding routing key từ failed thành unknown | DLQ không nhận message |
| Bắt `IllegalArgumentException` rồi return | Poison bị ACK và mất khỏi main queue |
| Đổi `maxAttempts(3)` thành 2 | Test transient 3 attempts fail hoặc vào DLQ |
| Bỏ `basicNack(...,true)` và ACK lần đầu | Redelivery test fail |
| Đổi `basicNack(...,true)` thành false | Message bị loại/dlq nếu có config, không redeliver |
| Bỏ dedup logic `isCompleted` | Duplicate effect có thể tăng >1 |
| Dùng một `AtomicInteger` static không tách ID | Tests phụ thuộc thứ tự hoặc gây nhiễu |
| Assert DLQ chỉ bằng log “error” | Có thể xanh giả dù payload đã biến mất |
| Kiểm DLQ bằng `receive` ở monitor production | Chính monitor tiêu thụ và xóa message lỗi |
| Gọi external HTTP trước DB commit rồi ACK | Crash/retry có thể lặp remote effect |
| Không xử lý publisher returns | Unroutable publish có thể bị hiểu nhầm là thành công |

**Bổ sung test có điều kiện cho production:**

1. **Producer confirmation:** Thử exchange có routing key không có queue, kiểm mandatory return và confirm; không chờ một “green” từ `convertAndSend`.
2. **Broker restart:** Gửi persistent message tới durable/quorum queue, restart broker đúng quy trình, kiểm message vẫn đọc được. Test này cần quy tắc durable storage thực và CI có khả năng điều khiển container.
3. **Consumer crash sau DB commit trước ACK:** Kill consumer process, cho broker redeliver và assert business effect vẫn đúng một lần. In-memory tracker của ví dụ sẽ reset, nên test phải dùng persistent DB.
4. **DLX binding lỗi:** Tháo binding trong môi trường disposable để kiểm monitoring/protection báo lỗi dead-letter delivery.
5. **Poison payload:** Dùng payload malformed, unknown schema version, headers sai và content type conversion lỗi trước khi listener chạy; xác minh error handler policy.
6. **Retry backoff:** Dùng test clock/scheduler hoặc broker timed retries, đừng dựa `Thread.sleep` không chắc chắn.
7. **Concurrent duplicate:** Hai consumers nhận cùng id ở hai messages, database unique constraint/inbox phải đảm bảo một side effect.
8. **Replay:** Gửi một message hợp lệ đã review trở lại main queue; kiểm audit, idempotency và DLQ depth giảm/không tăng.
9. **Publisher→DB atomicity:** Outbox record commit trước publish; failure injection giữa hai bước; relay publish lại không lặp effect.
10. **DLQ retention:** TTL, size limit, quorum delivery-limit và policy khi queue đầy; cần xử lý vận hành khi retention hết hạn.

**Tuyên bố no-loss phải có phạm vi.** Bộ 5 tests runnable chứng minh behavior trên RabbitMQ container với topology, listener và fault scenarios đã mô tả. Nó không chứng minh mọi race/failover/network partition/storage corruption đều được bảo toàn.

## 13. Bảng troubleshooting

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý/kiểm thử |
|---|---|---|
| Message lỗi biến mất, DLQ rỗng | Listener catch-and-return → ACK | Không nuốt exception; test payload DLQ |
| Message lỗi biến mất khi reject | Thiếu DLX, binding hoặc sai routing key | Declare topology, assert queue metadata |
| Poison gây log storm | Requeue=true vô hạn | Bounded retry, backoff, reject→DLQ |
| Retry luôn chỉ 1 lần | Chưa gắn advice vào đúng factory | Kiểm containerFactory name, interceptor |
| Expected 3 attempts nhưng thấy 4 | Nhầm maxAttempts với số retries | maxAttempts=3 gồm lần đầu |
| Broker deliveries=1 nhưng attempts=3 | Stateless retry cùng delivery | Phân biệt attempts và redelivery |
| `redelivered=false` ở lần retry nội bộ | Không có broker requeue | Đúng semantics; đừng assert cờ sai |
| Manual listener không nhận lần hai | Quên `basicNack(..., true)` hoặc ACK sớm | Kiểm deliveryTag/requeue flag |
| Message kẹt trạng thái unacked | Manual mode quên ACK/NACK | Kiểm mọi nhánh và consumer channel |
| DLQ có message nhưng không có stack trace | x-death chỉ metadata broker | Structured logs/error records/recoverer |
| x-death count không bằng Java attempts | Retry advice không dead-letter mỗi lần | Đừng dùng x-death làm in-process retry counter |
| Test fail ngẫu nhiên trên CI | Assert trước khi listener async xử lý | Awaitility, unique message IDs, isolated broker |
| @RabbitListener không subscribe | Factory bean sai tên, thiếu queue/declaration | Kiểm @RabbitListener, RabbitAdmin, startup logs |
| `Could not connect to localhost:5672` | ConnectionFactory không dùng container endpoint | @ServiceConnection + Boot auto-config |
| `Queue declaration failed` | Queue đã có với arguments khác | Docker/container disposable hoặc broker policy migrations |
| Payload không convert thành String | Content type/converter khác | Gửi String qua RabbitTemplate, kiểm converter |
| Dead-letter bị route sang queue khác | DLX/binding key không khớp | Kiểm x-death.queue và DLQ binding |
| Retry lặp effect nghiệp vụ | Crash sau DB commit trước ACK, không dedup | Persistent inbox/idempotency table |
| RabbitMQ restart mất dữ liệu | Non-durable queue/transient messages hoặc cluster config | Durable/persistent/quorum + restart tests |
| Publish bị unroutable mà app coi là OK | Không xử lý mandatory returns | Publisher returns + confirm + alert |
| DLQ tăng không được phát hiện | Không có queue depth/oldest age metric | Alert/dashboard/replay procedure |
| Chỉ nhìn logged exception | Log có thể bị rotate/mất context | Broker state assertion và trace ID |
| Kafka DLT test dùng RabbitMQ matcher | Hai broker semantics khác nhau | Kafka error handler/DLT topic integration |

### 13.1. Checklist trước khi merge thay đổi messaging

1. **Topologies:** Queue/exchange/DLX/DLQ declarable đúng, routing key không bị sai chính tả.
2. **Ack mode:** Biết mình đang ở AUTO, MANUAL hay NONE; không nhầm AUTO với broker autoack.
3. **Failure policy:** Phân loại transient/fatal; max attempts và backoff hữu hạn.
4. **Exhaustion:** Sau retry, recoverer đúng; message đi DLQ hoặc persistent failure ledger, không bị ACK nhầm.
5. **Evidence:** Tests assert broker DLQ payload, x-death, processing count và no business effect.
6. **Redelivery:** Test một NACK/requeue hoặc crash scenario; không coi retry attempts là broker delivery count.
7. **Idempotency:** Duplicate messages không lặp business effect; production dùng persistent dedup.
8. **Publisher:** Confirms, returns, mandatory, outbox được thiết kế theo yêu cầu reliability.
9. **Operations:** Metrics, alarms, retention, replay tool, quyền truy cập và audit.
10. **Isolation:** Docker broker test riêng, message IDs riêng, Awaitility thay fixed sleep.
11. **Security:** Không đưa PII/token/secret vào exception/x-death/log công khai.
12. **Compatibility:** Spring Boot 3.3.5/Spring AMQP 3.1.x API, broker RabbitMQ version và factory configs được kiểm.
13. **Rollback:** DB transaction và Rabbit ACK không được xem là một atomic transaction trừ khi thiết kế cụ thể.
14. **Timeout:** Poison test có deadline và báo lỗi rõ, không chờ vô hạn.
15. **Evidence over optimism:** “Test pass” phải gắn với assertion về state broker/business, không chỉ method invocation.

## 14. Bài tập tự luyện

**Bài 1 — Retry count:** Đổi `.maxAttempts(3)` thành `.maxAttempts(2)`. Message transient còn đến được trạng thái thành công không? Test nào phát hiện?

**Bài 2 — DLQ bị hỏng:** Bỏ DLX trên work queue trong H2/RabbitMQ **disposable**, gửi poison. Vì sao `RejectedAndDontRequeue` không bảo đảm vẫn còn message? Đề xuất test startup topology.

**Bài 3 — Return bình thường:** Bắt và nuốt `IllegalArgumentException` trong WorkListener, thử lại poison test. Điều gì xảy ra với broker ACK và DLQ?

**Bài 4 — Redelivery:** Đổi `basicNack(tag,false,true)` thành `basicAck(tag,false)` tại lần đầu. So sánh attempts và redelivered flag.

**Bài 5 — Idempotency:** Thay in-memory completed set bằng một bảng `processed_message` có PRIMARY KEY và business effect trong cùng DB transaction. Viết test concurrent duplicates.

**Bài 6 — Crash window:** Thiết kế failure injection giữa DB commit và Rabbit ACK. Vì sao at-least-once delivery cần dedup ngay cả khi listener không tự retry?

**Bài 7 — Headers:** Thêm `messageId`, correlation ID và schemaVersion cho mỗi Rabbit message; kiểm chúng được giữ trong DLQ. Không log secret.

**Bài 8 — Error taxonomy:** Phân biệt IllegalArgumentException (fatal) và IOException (transient); gắn retry classifier, kiểm fatal dead-letter không tốn 3 attempts nếu policy yêu cầu.

**Bài 9 — Publisher loss:** Bật correlated publisher confirm và mandatory returns. Gửi tới exchange/routing không có binding trong một broker disposable và kiểm return callback.

**Bài 10 — Replay:** Lấy một failed payload từ DLQ, sửa điều kiện lỗi, publish lại với ID/correlation policy được xác định, ghi audit và kiểm business effect không lặp.

**Bài 11 — Delay:** Thiết kế retry queue TTL + DLX có giới hạn attempts; trình bày cách tránh poison loop khi x-death tăng.

**Bài 12 — Kafka:** Chuyển model sang Spring Kafka `DefaultErrorHandler` + `DeadLetterPublishingRecoverer`; test DLT topic bằng Kafka Testcontainers, không dùng RabbitMQ x-death semantics.

**Bài 13 — Observability:** Thiết kế dashboard cho messages processed, retries, DLQ depth, oldest message age, returned publications và consumer lag. Alert dựa trên xu hướng nào?

**Bài 14 — Migration:** Khi nâng Boot 3.3 lên một major mới, kiểm lại các interfaces của retry advice, container factory, Testcontainers @ServiceConnection và RabbitMQ broker DLX handling.

## 15. Tài liệu chính thức

- [Spring AMQP 3.1 — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/3.1/amqp/resilience-recovering-from-errors-and-broker-failures.html): stateless/stateful retry, recoverer và xử lý lỗi consumer.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `defaultRequeueRejected`, fatal conversion errors, AMQP listener exception semantics.
- [Spring AMQP 3.1 API — MessageProperties](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/core/MessageProperties.html): `getDeliveryTag`, `isRedelivered`, `getXDeathHeader`.
- [Spring AMQP 3.1 API — RetryInterceptorBuilder](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/rabbit/config/RetryInterceptorBuilder.html): `stateless`, `stateful`, `maxAttempts`, `backOffOptions`.
- [Spring AMQP — Rabbit Listener Container Acknowledgments](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): AUTO/MANUAL/NONE acknowledge modes.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter reasons, queue policies và routing tới DLQ.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): basicAck/basicNack/basicReject, publisher confirms.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`, RabbitConnectionDetails và typed RabbitMQContainer.
- [Testcontainers for Java — RabbitMQ](https://java.testcontainers.org/modules/rabbitmq/): RabbitMQContainer và Docker runtime.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, DLT.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): `@RetryableTopic`, retry topics và DLT.

**Ghi nhớ:** **Retry** là thử lại xử lý, **redelivery** là broker giao lại message, **dead-letter** là đưa message không xử lý được qua DLX tới DLQ; ba cơ chế không đồng nghĩa. Với RabbitMQ và Spring Boot, hãy giới hạn retry, tránh requeue vô hạn, ACK sau thành công, reject không requeue để dead-letter khi đã hết attempts. Một bài test tốt phải kiểm **payload thật trong DLQ + x-death + attempts + business effect**, không chỉ log exception. Để đạt reliability trong production cần thêm **publisher confirms/returns, durable topology, persistent idempotency/outbox, metrics và replay có kiểm soát**. Không có một annotation retry đơn lẻ bảo đảm “không mất lỗi” trên mọi failure boundary.
