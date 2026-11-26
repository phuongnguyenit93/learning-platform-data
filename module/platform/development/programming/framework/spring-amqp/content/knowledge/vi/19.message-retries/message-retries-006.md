# Số lần thử, khoảng chờ tăng dần và giới hạn tổng thời gian

## Mục tiêu bài học

Trong **Spring AMQP**, **RabbitTemplate** gửi message qua exchange, routing key và binding tới queue RabbitMQ; **@RabbitListener** xử lý message bất đồng bộ. Khi dịch vụ phụ thuộc như database, API vận chuyển hoặc cổng thanh toán tạm thời gặp lỗi, consumer thường **thử lại (retry)** để không bỏ cuộc trước một sự cố ngắn.

Nhưng retry không phải cứ lặp đến khi thành công. Một chính sách đúng cần trả lời **ba câu hỏi riêng biệt**:

1. **Thử bao nhiêu lần?** Ví dụ tổng cộng tối đa **5 attempts**, bao gồm lần đầu.
2. **Chờ bao lâu giữa hai lần?** Ví dụ **exponential backoff** bắt đầu 500 ms, nhân đôi và giới hạn 8 giây; có thể thêm **jitter**.
3. **Cho phép mất tổng cộng bao lâu?** Ví dụ công việc phải hoàn tất hoặc chuyển sang phục hồi trước **deadline 10 giây**; đây không phải điều tự suy ra từ số attempts.

Bài thuộc chương **Thử lại thông điệp**, dùng ví dụ **OrderCreated** và **OrderService → RabbitMQ → NotificationService** để minh họa **Spring Retry**, listener retry, ACK/NACK, dead-letter, giới hạn thời gian, idempotency và observability.

Sau bài học, bạn có thể:

- Phân biệt **attempt** với **retry**, hiểu chính xác **maxAttempts**.
- Tính lịch chờ của exponential backoff, max interval và tổng thời gian xấp xỉ.
- Thiết kế **retry budget** theo cả số lần thử và deadline, phân biệt **timeout chính sách retry** với **timeout của một lần gọi**.
- Cấu hình **RetryInterceptorBuilder** cho Spring AMQP, hoặc **RetryTemplate** với **CompositeRetryPolicy + TimeoutRetryPolicy**.
- Chọn **stateless/stateful retry**, retry trong container hay qua broker, tránh requeue hot loop.
- Chuyển message hết ngân sách sang **DLQ/parking queue** hoặc một quy trình phục hồi bền vững.
- Kiểm thử lỗi tạm thời, lỗi vĩnh viễn, sự cố broker và duplicate sau retry.

## 1. Retry giải quyết vấn đề gì, không giải quyết vấn đề gì?

Giả sử Order Service publish event **OrderCreated(eventId=e-101)** vào exchange **orders.events**, định tuyến tới queue **notification.orders**. Notification Service nhận event rồi cập nhật dữ liệu và gửi thông báo.

~~~mermaid
flowchart LR
    P["Order Service<br/>RabbitTemplate"] --> X{"orders.events<br/>exchange"}
    X -->|"binding order.created"| Q[("notification.orders")]
    Q --> C["@RabbitListener<br/>Notification Service"]
    C --> DB[("Database")]
    C --> API["Email/API provider"]
    C -.->|"thất bại tạm thời"| R["Retry có giới hạn"]
    R -.->|"thử lại"| C
    R -->|"cạn budget"| D[("DLQ / parking queue")]
~~~

Các lỗi phổ biến:

| Trường hợp | Bản chất | Có thể retry? |
| --- | --- | --- |
| Database trả timeout tạm thời | Transient, có thể phục hồi | Có, sau backoff và trong ngân sách |
| API ngoài trả HTTP 503 hoặc rate limit | Transient/overload | Có, tôn trọng Retry-After và giới hạn gọi |
| Kết nối RabbitMQ vừa mất | Infrastructure | Container tự recovery connection; retry nghiệp vụ cần phân biệt |
| JSON sai cú pháp | Permanent đối với message hiện tại | Không retry cùng payload vô hạn |
| schemaVersion chưa hỗ trợ | Contract chưa tương thích | Cách ly, sửa producer/consumer rồi replay |
| Tenant không có quyền thực hiện lệnh | Permanent hoặc cần điều tra | Không retry mù quáng |
| Email đã được gửi nhưng response timeout | **Kết quả bất định** | Chỉ retry an toàn nếu có idempotency/reconciliation |
| Message được publish trùng vì mất publisher confirm | Duplicate event | Consumer phải idempotent; retry không tự chống trùng |

**Retry không sửa payload sai, không tự thêm quyền truy cập, và không bảo đảm exactly-once.** Retry làm tăng xác suất xử lý thành công với lỗi có thể phục hồi, đồng thời làm tăng lưu lượng và khả năng trùng nếu không kiểm soát.

### Retry có thể xảy ra ở nhiều tầng

~~~text
Producer retry: RabbitTemplate publish lại khi lỗi gửi / confirm bất định
    ↓
Broker: queue giao message cho consumer
    ↓
Consumer local retry: Spring Retry gọi lại handler trong một delivery
    ↓
Broker redelivery: NACK/requeue hoặc channel mất khiến message giao lại
    ↓
Retry queue / scheduler: delay rồi chuyển message về work queue
~~~

Mỗi tầng có **đơn vị đếm và trạng thái riêng**. Không được cộng nhầm maxAttempts ở Spring Retry với delivery count của RabbitMQ hoặc số lượt retry của publisher.

## 2. Số lần thử: maxAttempts bao gồm lần đầu

Đây là lỗi cấu hình rất thường gặp:

**maxAttempts=4** nghĩa là **tổng cộng nhiều nhất bốn lời gọi xử lý**: lần đầu **#1** và tối đa ba lượt retry **#2–#4**.

| maxAttempts | Lần xử lý ban đầu | Số lượt retry tối đa sau lần đầu |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 5 | 1 | 4 |

Với một callback thất bại ở tất cả lượt:

~~~text
attempt #1: thất bại → chờ
attempt #2: thất bại → chờ
attempt #3: thất bại → chờ
attempt #4: thất bại → hết maxAttempts, chuyển recoverer
~~~

**Không chờ thêm backoff sau attempt cuối cùng** nếu retry policy đã hết lượt.

### Phân biệt maxAttempts với các cấu hình “maxRetries”

Một số tài liệu/API cũ dùng tên **maxRetries**. Cách diễn đạt của tên này có thể gây nhầm với **maxAttempts**. Khi triển khai, ưu tiên API **RetryInterceptorBuilder.maxAttempts(int)** và tài liệu đúng phiên bản; không tự suy từ tên property rằng “5 retries” luôn có nghĩa “5 attempts”.

### Nếu xử lý thành công sớm

Với **maxAttempts=5**, nếu attempt #2 thành công, hệ thống chỉ chạy **hai** attempt. Không phải lúc nào cũng phải thực hiện đủ năm lượt.

Nếu lỗi thuộc nhóm **không retry được**, policy có thể dừng ngay attempt đầu, dù maxAttempts còn dư.

## 3. Khoảng chờ tăng dần: fixed, exponential và jitter

Không đặt backoff nghĩa là nhiều lần thử có thể xảy ra liên tục, làm tăng tải đúng lúc hệ thống phụ thuộc đang lỗi.

### 3.1. Fixed backoff

Với initialInterval=1 giây và không tăng dần:

~~~text
attempt 1 ──1s──> attempt 2 ──1s──> attempt 3 ──1s──> attempt 4
~~~

Dễ dự đoán, phù hợp cho một số sự cố ngắn nhưng **nhiều instance có thể đồng bộ retry** cùng lúc.

### 3.2. Exponential backoff

Đặt:

- **initialInterval = 500 ms**
- **multiplier = 2.0**
- **maxInterval = 8.000 ms**
- **maxAttempts = 6**

Với lượt chờ thứ **k** (giữa attempt k và attempt k+1, tính k từ 1):

\[
d_k = \min(\text{maxInterval},\ \text{initialInterval}\times \text{multiplier}^{k-1})
\]

| Sau attempt thất bại | Chờ trước attempt tiếp | Vì sao? |
| --- | ---: | --- |
| #1 | 500 ms | Initial interval |
| #2 | 1.000 ms | 500 × 2 |
| #3 | 2.000 ms | 1.000 × 2 |
| #4 | 4.000 ms | 2.000 × 2 |
| #5 | 8.000 ms | Đạt maxInterval |
| #6 | Không chờ | Hết maxAttempts |

**Tổng thời gian chỉ để ngủ** nếu cả 6 attempt thất bại: **0,5 + 1 + 2 + 4 + 8 = 15,5 giây**. Đây **chưa phải tổng thời gian xử lý**, bởi mỗi attempt còn thực thi code, chờ database, network và overhead khác.

~~~mermaid
flowchart LR
    A1["Attempt 1"] -->|"0,5 s"| A2["Attempt 2"]
    A2 -->|"1 s"| A3["Attempt 3"]
    A3 -->|"2 s"| A4["Attempt 4"]
    A4 -->|"4 s"| A5["Attempt 5"]
    A5 -->|"8 s"| A6["Attempt 6"]
    A6 --> F["Success hoặc recover"]
~~~

### 3.3. Max interval khác max elapsed time

**maxInterval=8.000 ms** chỉ giới hạn **một khoảng chờ**; nó không giới hạn tổng thời gian hoặc số lượt thử.

Nếu còn thêm nhiều attempts, mỗi khoảng chờ tiếp theo có thể tiếp tục ở mức tối đa 8 giây, khiến tổng thời gian tăng lớn.

### 3.4. Jitter: tránh nhiều consumer thử lại cùng lúc

Khi RabbitMQ hoặc database phục hồi, hàng chục instance có thể cùng retry theo các mốc **0,5s → 1s → 2s → 4s**. Chúng vô tình tạo **thundering herd** lên dependency.

**Jitter** thêm tính ngẫu nhiên có kiểm soát vào thời gian chờ:

- **Full jitter:** lấy số ngẫu nhiên trong đoạn từ 0 đến delay đã tính.
- **Equal/proportional jitter:** giữ delay trong khoảng, chẳng hạn ±20% quanh giá trị lý thuyết.
- **Decorrelated jitter:** điều chỉnh delay dựa trên khoảng trước, có giới hạn.

Công thức ví dụ khi dùng proportional jitter:

\[
d'_k = d_k \times U(0{,}8,\ 1{,}2)
\]

Trong đó **U(a,b)** là lấy ngẫu nhiên trong khoảng **a đến b**. Chọn **maxInterval** sau jitter nếu yêu cầu trần tuyệt đối cho mỗi khoảng chờ.

**Jitter làm tổng thời gian không còn xác định trước chính xác.** Vì vậy budget tổng cần dựa trên **thời gian thực** (deadline), không dựa vào cộng một lịch sleep cố định.

## 4. Giới hạn tổng thời gian: tại sao maxAttempts không đủ?

Giả sử **maxAttempts=5**, backoff **0,5s, 1s, 2s, 4s**, và mỗi attempt chiếm **700 ms** nếu thất bại.

| Attempt | Bắt đầu xấp xỉ | Kết thúc xấp xỉ | Thời gian đợi tiếp |
| --- | ---: | ---: | ---: |
| #1 | 0,0s | 0,7s | 0,5s |
| #2 | 1,2s | 1,9s | 1,0s |
| #3 | 2,9s | 3,6s | 2,0s |
| #4 | 5,6s | 6,3s | 4,0s |
| #5 | 10,3s | 11,0s | Không |

**Tổng thời gian ~11 giây**, dù số attempts chỉ là 5. Nếu nghiệp vụ quy định **deadline 8 giây**, attempt #5 **không nên được khởi chạy** theo chính sách có kiểm soát.

### 4.1. Hai ràng buộc độc lập

Một retry policy có trách nhiệm thường dùng cả:

- **Attempt budget:** tối đa **N** lượt xử lý.
- **Elapsed-time budget:** từ lần thử đầu đến lúc dừng không vượt quá một mốc thời gian hoặc thời hạn nghiệp vụ cho phép.

Còn có ràng buộc thứ ba rất quan trọng:

- **Per-attempt timeout:** giới hạn riêng cho một lần gọi DB/HTTP; nếu một lần gọi treo 60 giây, maxAttempts=5 và backoff đẹp vẫn vô nghĩa đối với yêu cầu deadline 10 giây.

Tổng thời gian xấp xỉ:

\[
T_{\text{total}} \approx \sum_{i=1}^{A} T_{\text{attempt},i}
+ \sum_{i=1}^{A-1} d_i + T_{\text{overhead}}
\]

Trong đó **A** là số lần thử thực tế, không vượt quá maxAttempts; **d_i** là khoảng chờ trước lần thử tiếp; **overhead** gồm chuyển đổi, log, transaction, scheduling và network.

### 4.2. Deadline của một callback khác deadline của toàn event

| Phạm vi | Ví dụ | Ai quản lý? |
| --- | --- | --- |
| **Một lần gọi API** | HTTP timeout 1 giây | HTTP client / DB driver |
| **Một phiên Spring Retry** | Nhiều attempt trong 6 giây | RetryTemplate/RetryPolicy |
| **Một lần giao message từ queue** | Handler được phép chạy 8 giây | Listener pipeline và workload |
| **Toàn vòng đời event** | Event phải xử lý trước giờ giao hàng | DB/job state, durable deadline |
| **Toàn bộ workflow** | Đặt hàng → thanh toán → thông báo trong 5 phút | Workflow/saga/orchestrator |

**TimeoutRetryPolicy** hoặc deadline trong một **RetryTemplate** thường **bắt đầu khi retry context được mở**, và có thể được tạo mới ở lần delivery khác. Nó **không tự giới hạn thời gian xuyên các lần broker redelivery hoặc qua restart**.

Nếu yêu cầu “event này sau 2 phút phải chuyển sang xử lý thủ công dù consumer đã restart nhiều lần”, hãy lưu **firstFailureAt/deadlineAt** bền vững (hoặc hợp đồng message được xác thực) và kiểm tra qua từng attempt.

### 4.3. Không phải một cơ chế ngắt cưỡng bức

**TimeoutRetryPolicy** kiểm tra thời gian khi quyết định **có cho phép attempt tiếp theo**; nó **không tự ngắt một HTTP request đang kẹt** và không bảo đảm một sleep đang chờ bị ngắt đúng mili-giây khi deadline hết.

Muốn thời hạn tổng nghiêm ngặt, cần thêm timeout ở **dependency client**, cơ chế hủy được hỗ trợ, kiểm tra **remaining budget trước mỗi lượt** và xử lý khi không còn đủ thời gian.

## 5. Quy tắc dừng theo cả số lần, lỗi và deadline

Một quyết định retry tốt cần có thứ tự rõ ràng:

~~~mermaid
flowchart TD
    S["Attempt thất bại"] --> E{"Lỗi permanent?"}
    E -->|"Có"| P["Không retry<br/>DLQ/parking/manual"]
    E -->|"Không"| N{"Đã chạm maxAttempts?"}
    N -->|"Có"| P
    N -->|"Không"| T{"Deadline đã qua?"}
    T -->|"Có"| P
    T -->|"Chưa"| B["Tính exponential backoff + jitter"]
    B --> W{"Còn đủ thời gian<br/>cho sleep + attempt?"}
    W -->|"Không"| P
    W -->|"Có"| SL["Chờ có giới hạn"]
    SL --> R["Attempt tiếp theo"]
    R --> S
~~~

Một thuật toán khái niệm:

~~~text
maxAttempts  = 5
initialDelay = 500ms
multiplier   = 2
maxDelay     = 8s
deadlineAt   = firstFailureAt + 10s

if error is permanent:
    STOP_AND_QUARANTINE
else if attempts >= maxAttempts:
    STOP_AND_QUARANTINE
else if now >= deadlineAt:
    STOP_AND_QUARANTINE
else:
    delay = min(maxDelay, initialDelay * 2^(attempts - 1))
    delay = applyJitter(delay)
    remaining = deadlineAt - now

    if remaining < delay + minimumTimeForNextAttempt:
        STOP_AND_QUARANTINE
    else:
        scheduleNextAttempt(now + delay)
~~~

**minimumTimeForNextAttempt** là ước lượng/giới hạn thiết kế để tránh lập lịch lượt không có cơ hội hoàn tất trước hạn. Đó không phải API tự có trong RabbitMQ. Nếu deadline cực kỳ nghiêm ngặt, hãy truyền **remaining** tới timeout của từng lệnh DB/HTTP và chấp nhận rằng một số thư viện không hỗ trợ hủy ngay.

### Permanent và transient phải được phân loại trước khi tính backoff

Không nên thử lại message sai schema 5 lần với tổng 15 giây chờ. Ngược lại, nếu DB mất kết nối 300 ms, có thể giải quyết sau một khoảng chờ ngắn. Nhóm lỗi thường được nhận biết qua **exception class**, **error code** và hợp đồng nghiệp vụ, không dựa duy nhất vào chuỗi exception message.

## 6. Spring AMQP: retry listener bằng RetryInterceptorBuilder

Với **@RabbitListener** đồng bộ, Spring AMQP tích hợp Spring Retry thông qua **RetryOperationsInterceptor** gắn vào **advice chain** của container.

Ví dụ **Spring Boot 3.x + Spring AMQP 3.x**, giả định có **spring-boot-starter-amqp** và thư viện **Spring Retry** trên classpath.

### 6.1. Spring Retry theo số lần và exponential backoff

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationRetryConfig {

    @Bean
    SimpleRabbitListenerContainerFactory notificationListenerFactory(
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(2);
        factory.setPrefetchCount(10);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(5)
                        .backOffOptions(500L, 2.0, 8_000L)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build());
        return factory;
    }
}
~~~

**Đọc đúng cấu hình:**

- **stateless()**: thử nhiều lần **trong cùng invocation của interceptor**, đơn giản khi không cần rollback một outer transaction đang có.
- **maxAttempts(5)**: tối đa **5 lượt xử lý**, bao gồm lần đầu.
- **backOffOptions(500L, 2.0, 8_000L)**: độ trễ **0,5 → 1 → 2 → 4 giây** giữa năm attempts; max 8 giây là trần mỗi khoảng chờ nếu cần thêm lượt.
- **RejectAndDontRequeueRecoverer**: khi cạn retry, ném chỉ thị **reject không requeue** để RabbitMQ có thể dead-letter message nếu queue đã cấu hình DLX.
- **AUTO**: container ACK khi xử lý/recovery được coi thành công; khi recoverer ném reject, đi theo nhánh reject thay vì ACK bình thường.

**Ví dụ này chưa đặt giới hạn tổng thời gian.** Dù chỉ có 5 attempts, nếu mỗi attempt timeout 20 giây thì tổng elapsed có thể rất lớn. Các phần kế tiếp bổ sung **elapsed-time policy** và timeout của từng dependency.

### 6.2. Listener thực thi nghiệp vụ

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class NotificationConsumer {
    private final NotificationService service;

    public NotificationConsumer(NotificationService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = "notification.orders",
            containerFactory = "notificationListenerFactory")
    public void onOrderCreated(OrderCreated event) {
        service.processIdempotently(event);
    }
}
~~~

**OrderCreated** và **NotificationService** là phần nghiệp vụ do ứng dụng định nghĩa. Listener muốn nhận DTO JSON cần **JSON MessageConverter phù hợp** trong factory (hoặc annotation converter) và cùng contract với publisher. Nếu chưa có converter, đoạn ví dụ có thể không giải mã được body như mong muốn.

**Không nuốt lỗi rồi return:** nếu service bắt exception, chỉ log mà không ném tiếp hoặc không lưu job phục hồi bền vững, interceptor sẽ nghĩ lần xử lý đó đã thành công, và container có thể ACK.

### 6.3. Retry tại listener không phải broker redelivery

Với **stateless interceptor**, một message có thể được xử lý 5 lần **trước khi container quyết định ACK/NACK cho một lần delivery**. RabbitMQ không nhất thiết gửi lại message năm lần. Vì vậy:

- **retry attempt count của interceptor** khác số broker deliveries.
- **redelivered flag** có thể vẫn false trong tất cả local retries.
- **x-death** không tăng theo những lần retry nội bộ đó.
- Trong thời gian sleep/backoff, consumer thread có thể bị giữ; cần tính vào throughput/concurrency.

## 7. Spring Boot YAML: retry đơn giản

Spring Boot hỗ trợ cấu hình retry cho listener container do Boot tự quản lý.

~~~yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 4
        prefetch: 10
        default-requeue-rejected: false
        retry:
          enabled: true
          max-attempts: 5
          initial-interval: 500ms
          multiplier: 2.0
          max-interval: 8s
~~~

Với các version Spring Boot 3.x hỗ trợ những property này, cấu hình mô tả **maxAttempts + exponential backoff** ở listener. Đây **không phải** cấu hình retry phía publisher; producer dùng nhóm **spring.rabbitmq.template.retry**.

**Cần kiểm tra việc recover sau cạn lượt:** một số cơ chế mặc định có thể **log và consume/discard** message sau khi recovery xử lý exception, chứ không tự đưa vào DLQ. Nếu muốn broker dead-letter, chọn **recoverer từ chối requeue** hoặc cấu hình error handling cụ thể. Đừng suy luận rằng cứ bật retry và có DLX thì mọi message cạn retry chắc chắn nằm trong DLQ.

**Giới hạn của YAML trên:** không có một thuộc tính chung mặc định trong nhóm này bảo đảm **deadline tổng theo event** hay **per-attempt HTTP/DB timeout**. Nếu cần giới hạn tổng, hãy bổ sung chính sách code và/hoặc bền vững.

**Lưu ý:** Nếu tự tạo factory **notificationListenerFactory** và advice chain như mục 6, những property Boot ở trên không tự nhất thiết áp dụng vào custom factory. Không vô tình bật cả **Boot retry** và **custom interceptor** nếu cả hai có thể chạy trong cùng pipeline, gây nhân bội số lần thử.

## 8. Giới hạn elapsed time trong Spring Retry

Spring Retry có **TimeoutRetryPolicy** để giới hạn thời gian một **retry context** được phép tiếp tục retry, và **CompositeRetryPolicy** để kết hợp nó với **SimpleRetryPolicy** (số attempts).

### 8.1. Ví dụ kết hợp số attempts và elapsed-time policy

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.RetryPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.CompositeRetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.policy.TimeoutRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class OrderRetryBudgetConfiguration {

    @Bean
    RetryTemplate orderRetryTemplate() {
        SimpleRetryPolicy attemptPolicy = new SimpleRetryPolicy();
        attemptPolicy.setMaxAttempts(5);

        TimeoutRetryPolicy timePolicy = new TimeoutRetryPolicy();
        timePolicy.setTimeout(7_000L); // 7 giây tính từ lúc mở retry context.

        CompositeRetryPolicy combined = new CompositeRetryPolicy();
        combined.setOptimistic(false); // AND: mọi policy phải cho retry.
        combined.setPolicies(new RetryPolicy[] {
                attemptPolicy, timePolicy
        });

        ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(8_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(combined);
        template.setBackOffPolicy(backOff);
        return template;
    }
}
~~~

**Giải thích quan trọng:**

1. **SimpleRetryPolicy** giới hạn **tổng số lần retry callback có thể được gọi**.
2. **TimeoutRetryPolicy** chỉ cho phép thêm attempt khi **retry context chưa hết thời gian**.
3. **CompositeRetryPolicy.setOptimistic(false)** là kết hợp kiểu **AND**: nếu một policy không cho tiếp tục, retry dừng.
4. **ExponentialBackOffPolicy** điều khiển sleep, không quyết định còn attempt hay deadline.
5. **7 giây là thời hạn của một retry context**, không tự tồn tại xuyên restart hoặc lần broker redelivery mới.

**TimeoutRetryPolicy không phải watchdog:** nó không tự hủy một DB query hay HTTP request đã chạy quá lâu. Cũng không bảo đảm dừng đúng mốc 7 giây nếu đang ở một lần attempt/sleep không được ngắt. Muốn strict deadline, phải phối hợp timeout từng dependency và kiểm tra remaining time trước sleep/attempt.

### 8.2. Sử dụng RetryTemplate trong handler có recovery rõ ràng

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class RetryingOrderProcessor {
    private final RetryTemplate retryTemplate;
    private final OrderService orderService;

    public RetryingOrderProcessor(
            RetryTemplate orderRetryTemplate,
            OrderService orderService) {
        this.retryTemplate = orderRetryTemplate;
        this.orderService = orderService;
    }

    public void process(OrderCreated event) {
        retryTemplate.execute(
                context -> {
                    orderService.processIdempotently(event);
                    return null;
                },
                context -> {
                    // Hết budget -> container AUTO sẽ reject không requeue.
                    throw new AmqpRejectAndDontRequeueException(
                            "Order processing retry budget exhausted",
                            context.getLastThrowable());
                });
    }
}
~~~

Listener gọi **retryingOrderProcessor.process(event)** và **không bật thêm một listener retry interceptor khác cho cùng xử lý**, nếu không muốn xếp nhiều tầng retry gây số lượt thử khó kiểm soát.

**OrderService** là interface/lớp nghiệp vụ do ứng dụng định nghĩa. Ví dụ minh họa outcome khi hết ngân sách; chưa bao gồm **chính sách lọc exception transient/permanent** và **per-call timeout**, cần triển khai thêm trong hệ thống thật.

### 8.3. Chỉ retry lỗi có thể phục hồi

Một SimpleRetryPolicy mặc định có thể retry nhiều loại exception. Trong ứng dụng thật cần phân loại **theo exception type** (và cause chain), không để **InvalidOrderSchemaException** hoặc **AuthorizationException** mất 7 giây rồi vẫn thất bại.

Spring Retry có **ExceptionClassifierRetryPolicy** hoặc **SimpleRetryPolicy** với cấu hình retryable exceptions và khả năng traverse causes. Spring AMQP thường gói lỗi từ method listener trong **ListenerExecutionFailedException**, nên khi đặt retry interceptor ngoài method cần xem nguyên nhân sâu hơn exception wrapper; không chỉ so class top-level.

Một policy hợp lý:

| Lỗi | Retryable? | Lý do |
| --- | --- | --- |
| **TransientDataAccessException** | Có | DB có thể phục hồi |
| **SocketTimeoutException** từ dependency | Tùy | Có thể là kết quả bất định; cần idempotency |
| **HTTP 429** | Có điều kiện | Tôn trọng Retry-After và rate limit |
| **HTTP 503** | Có | Lỗi tạm thời |
| **IllegalArgumentException** do schema sai | Không | Retry cùng message không làm dữ liệu đúng |
| **MessageConversionException** | Không | Body/type header cần sửa |
| **AccessDeniedException** do policy cố định | Không | Cần sửa quyền hoặc dữ liệu |
| **BusinessRuleRejectedException** | Thường không | Quyết định nghiệp vụ đã rõ |

Đừng phân loại một lỗi “timeout” là hoàn toàn an toàn để gọi lại **payment/charge** nếu provider có thể đã thực hiện lệnh. Với API có side effect, luôn dùng **idempotency key**, trạng thái bền vững và reconciliation khi kết quả bất định.

## 9. Tổng thời gian của event qua nhiều delivery: cần storage bền vững

Giới hạn **maxAttempts=5** trong Spring Retry áp dụng **một retry context/invocation**, không tự đếm mọi lần broker redelivery hoặc restart process.

Xem tình huống:

~~~text
T0  Broker giao eventId=e-101 → consumer A
T1  Spring Retry chạy 5 attempts, hết budget, message requeue
T2  Broker giao lại e-101 → consumer B, context retry mới
T3  Consumer B lại được 5 attempts
T4  Broker connection reset → consumer C nhận lại
...
~~~

Nếu thiếu hạn mức bền vững, **maxAttempts=5 vẫn có thể tạo rất nhiều lần xử lý toàn cục**.

### 9.1. Thiết kế durable retry state

Một bảng minh họa:

~~~sql
CREATE TABLE consumer_retry_state (
    consumer_name       VARCHAR(100) NOT NULL,
    event_id            VARCHAR(100) NOT NULL,
    first_failure_at    TIMESTAMPTZ NOT NULL,
    deadline_at         TIMESTAMPTZ NOT NULL,
    total_attempts      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ,
    status              VARCHAR(32) NOT NULL,
    last_error          TEXT,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

**consumer_name + event_id** phân biệt những consumer group độc lập. Nếu Notification và Analytics đều cần xử lý event, chúng không nên dùng chung một bản ghi trạng thái khiến service này chặn service kia.

Quy trình dispatcher/worker:

1. Lưu **firstFailureAt, deadlineAt** khi lỗi xuất hiện lần đầu, không reset mỗi lần restart.
2. Khi nhận lại event, lock/claim trạng thái để tránh hai instance tự tăng số attempts đồng thời.
3. Nếu **now >= deadlineAt** hoặc **totalAttempts >= maxTotalAttempts**, chuyển **NEEDS_ATTENTION/QUARANTINED**.
4. Tính next delay có cap + jitter, **không đặt nextAttemptAt sau deadline**.
5. Chỉ đánh dấu **COMPLETED** sau khi tác động nghiệp vụ đã commit hoặc nhiệm vụ tiếp theo được lưu bền vững.
6. Dùng **idempotency key** để xử lý khi broker hoặc publisher giao lại.

Đây là thiết kế **cross-delivery**. Không nên chỉ dùng một biến **static AtomicInteger** trong JVM để giới hạn tổng attempts: nó mất sau restart và không phối hợp giữa nhiều instance.

### 9.2. Message TTL không phải deadline xử lý nghiệp vụ

RabbitMQ **message TTL** có thể khiến message **chờ trong queue** hết hạn và dead-letter. Nhưng:

- TTL không có nghĩa broker ngắt một handler đã nhận delivery khi thời hạn nghiệp vụ hết.
- TTL của retry queue điều khiển **thời gian chờ trong queue**, không tự hiểu deadlineAt của event.
- Event có thể rời retry queue sau TTL nhưng vẫn phải chờ backlog work queue.
- Tổng thời gian phải gồm **queue wait, processing, backoff, redelivery và outbound calls**.

Nếu business SLA tính từ lúc **order được tạo**, hãy lưu **occurredAt/deadlineAt** trong bản ghi đáng tin cậy và kiểm tra trước khi thực hiện tác động ngoài, không chỉ trước khi schedule.

## 10. Local retry, broker retry và delayed retry khác nhau

| Phương án | Thời gian đợi diễn ra ở đâu? | Có giữ consumer thread? | Budget qua restart | Lưu ý |
| --- | --- | --- | --- | --- |
| **RetryTemplate trong listener** | Trong JVM, sleep/backoff | Thường **có** | Không, nếu không tự lưu state | Dễ dùng cho lỗi ngắn, vài lượt |
| **NACK/requeue ngay** | Broker giao lại sớm | Không sleep trong handler | Không tự có maxAttempts | Dễ tạo hot loop |
| **TTL retry queue + DLX** | Message chờ trên broker | Không giữ thread local | Queue bền vững tùy cấu hình | Cần nhiều delay tier hoặc scheduler, tránh cycle |
| **Durable DB scheduler** | DB lưu nextAttemptAt | Không giữ thread local | Có, nếu thiết kế đúng | Phức tạp hơn, dễ thực thi deadline toàn event |
| **Native delayed retry của quorum queue phiên bản hỗ trợ** | Broker giữ trạng thái delay | Không giữ thread local | Theo tính năng broker | Có thể là **linear backoff**, không đồng nhất exponential |

### 10.1. Local retry: cho sự cố ngắn

Ví dụ: transaction bị deadlock một lần, database kẹt 200 ms. Retry ngắn trong listener với vài attempts có thể thành công nhanh, không phải đưa message qua nhiều queue.

Nhược điểm: thời gian sleep **giữ chỗ consumer**, khiến throughput giảm và tăng unacked khi broker vẫn chưa nhận ACK.

### 10.2. Retry queue: cho thời gian đợi dài

Ví dụ dependency email provider bị 503 và cần chờ 30 giây, vài phút. Thường không nên giữ một consumer thread ngủ dài trong listener. Có thể:
- reject/dead-letter sang retry queue có TTL;
- khi TTL hết, DLX đưa lại work queue;
- hoặc dùng ứng dụng re-publish với **publisher confirms** và lịch bền vững.

~~~mermaid
flowchart LR
    W[("work queue")] --> C["Consumer"]
    C -->|"lỗi tạm, chuyển retry"| R[("retry queue<br/>TTL / delayed delivery")]
    R -->|"hết thời gian, DLX"| X{"return exchange"}
    X --> W
    C -->|"vượt maxAttempts / deadline"| D[("parking DLQ")]
~~~

Sơ đồ là mô hình, **không tự hoạt động chỉ nhờ vẽ**. Phải khai báo exchange, binding, queue, TTL và dead-letter rules chính xác; tránh một DLX cycle không giới hạn và thiết kế đường quarantine.

### 10.3. Native quorum delayed retry: chú ý phiên bản

Các phiên bản **RabbitMQ 4.3 trở lên** có hỗ trợ **delayed retry cho quorum queue** với các tùy chọn cấu hình broker; backoff native trong tính năng này là **linear theo delivery count**, **không phải exponential 2^n** của Spring Retry. Khi dùng, phải kiểm tra loại queue, broker version, **x-delayed-retry-type**, delay min/max và semantics của return/failure.

Không áp các tham số quorum này sang **classic queue hoặc stream queue** rồi kỳ vọng cùng cơ chế.

### 10.4. Cẩn thận với x-death và retry_count

**x-death** do broker cập nhật khi message đi qua dead-lettering; nó **không đếm mọi local retry** và không thay thế số attempts trong DB.

Từ **Spring AMQP 3.2**, có **retry_count** trong MessageProperties để hỗ trợ các luồng ứng dụng tự republish, vì **RabbitMQ 4.0** không coi giá trị **x-death do client tự gửi** là lịch sử broker đáng tin. Nếu dùng retry across deliveries, hãy thống nhất ai sở hữu counter, khi nào increment, tránh spoofing và reset sau requeue/restart.

## 11. Sau khi hết budget: làm gì với message?

**Hết attempts hoặc deadline không có nghĩa nên xóa dữ liệu nghiệp vụ.** Hãy xác định trạng thái cuối an toàn cho từng loại sự kiện.

### 11.1. Recoverer và đường tới DLQ

Trong Spring AMQP, một **MessageRecoverer** có thể xử lý message sau khi Spring Retry cạn lượt:

| Recoverer / hành vi | Kết quả |
| --- | --- |
| **RejectAndDontRequeueRecoverer** | Ném chỉ thị reject không requeue; broker dead-letter **nếu queue có DLX phù hợp** |
| **RepublishMessageRecoverer** | Ứng dụng publish một message mới tới error exchange/queue | Không phải broker DLX tự động; cần theo dõi publish |
| **RepublishMessageRecovererWithConfirms** | Republish với publisher confirms ở các version hỗ trợ | Giảm rủi ro mất message khi republish |
| Recoverer chỉ **log rồi return** | Container có thể coi lỗi đã được xử lý và ACK | Không mặc nhiên có message trong DLQ |
| Không có recoverer phù hợp | Phụ thuộc mặc định, container error handler và reject/requeue | Không nên dựa vào ngầm định cho dữ liệu quan trọng |

**ACK do recoverer đã “xử lý” lỗi không đồng nghĩa email/DB nghiệp vụ đã thành công**. Nếu recoverer ghi lỗi bền vững vào parking queue/DB rồi return, hành vi ACK có thể hợp lý. Nếu nó chỉ ghi log, bạn có thể làm mất trách nhiệm xử lý.

### 11.2. Phân tầng trạng thái

Một thiết kế thường có:
- **PENDING**: cần xử lý.
- **RETRY_SCHEDULED**: transient error và còn budget.
- **IN_PROGRESS**: worker đã claim.
- **COMPLETED**: tác động đã commit.
- **QUARANTINED/NEEDS_ATTENTION**: hết budget, lỗi permanent hoặc cần operator.
- **EXPIRED**: quá hạn nghiệp vụ theo policy rõ ràng.

Dữ liệu lỗi cần gồm **eventId, consumerName, error category, totalAttempts, firstFailureAt, deadlineAt, lastAttemptAt** và chỉ những metadata không nhạy cảm cần thiết.

**DLQ cần quy trình vận hành**: cảnh báo, điều tra root cause, cho phép replay sau khi sửa code/schema, giữ eventId ổn định và bảo vệ idempotency.

## 12. Retry, ACK và idempotency phối hợp thế nào?

Trong **AcknowledgeMode.AUTO**:

1. Listener nhận message nhưng broker vẫn coi delivery **unacked**.
2. Retry interceptor có thể gọi lại handler nhiều lần trong một delivery.
3. Handler thành công: container ACK theo policy.
4. Retry cạn: recoverer/container quyết định ACK, reject không requeue hoặc requeue.
5. Nếu connection chết khi ACK chưa tới broker, message có thể được giao lại.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Spring Listener
    participant D as Database
    B->>C: deliver OrderCreated(e-101)
    C->>D: attempt 1 (timeout)
    D--xC: timeout
    Note over C: backoff 500ms
    C->>D: attempt 2
    D-->>C: COMMIT success
    C--xB: ACK mất do connection drop
    B->>C: redeliver e-101
    C->>D: attempt mới trên delivery mới
    D-->>C: duplicate eventId, no-op
    C-->>B: ACK
~~~

**Ngay cả local retry đã thành công, message vẫn có thể redeliver** vì ACK bị mất. Nếu mỗi retry tạo một payment mới, tác động có thể bị nhân đôi.

### 12.1. Transactional idempotency

Một bảng PostgreSQL tối giản:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderProcessor {
    private final JdbcTemplate jdbc;
    private final OrderProjectionRepository repository;

    public IdempotentOrderProcessor(
            JdbcTemplate jdbc,
            OrderProjectionRepository repository) {
        this.jdbc = jdbc;
        this.repository = repository;
    }

    @Transactional
    public void process(OrderCreated event) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "notification-projection", event.eventId());

        if (inserted == 0) {
            return; // Không lặp lại tác động DB.
        }

        repository.apply(event);
    }
}
~~~

**OrderProjectionRepository** là thành phần ứng dụng phải triển khai. Bản ghi processed_events và thay đổi projection **phải ở cùng database transaction**; nếu repository thất bại, transaction rollback cả dấu processed.

### 12.2. External side effects

Gửi email, thanh toán hoặc webhook ra ngoài DB không thể được rollback chỉ bằng transaction địa phương. Một timeout không nói chắc API đã hoàn tất hay chưa. Vì vậy:
- tạo **notification/payment job** có eventId/idempotency key ổn định;
- dùng idempotency key provider khi có;
- lưu trạng thái job để reconcile kết quả bất định;
- không retry một payment charge như hàm thuần vô hại.

**Retry có backoff không phải giải pháp thay thế cho idempotency.**

## 13. Sizing: tính tổng thời gian và sức tải

Giả sử một consumer có:
- **maxAttempts=5**
- **initialInterval=500 ms**
- **multiplier=2**, **maxInterval=8 s**
- **per-attempt timeout=1 s**
- **deadline của phiên retry=10 s**

Nếu mọi attempt dùng hết 1 giây, lịch lý thuyết khi chưa giới hạn elapsed:

| Attempt | Bắt đầu | Kết thúc | Delay trước lượt sau |
| --- | ---: | ---: | ---: |
| #1 | 0s | 1s | 0,5s |
| #2 | 1,5s | 2,5s | 1s |
| #3 | 3,5s | 4,5s | 2s |
| #4 | 6,5s | 7,5s | 4s |
| #5 | 11,5s | 12,5s | — |

Ở **deadline 10 giây**, attempt #5 sẽ bắt đầu quá muộn. Policy có thể dừng sau attempt #4 hoặc sau một lần kiểm tra timeout tùy cách triển khai. **Không được viết SLA rằng tổng runtime chắc chắn không vượt 10 giây** chỉ nhờ TimeoutRetryPolicy.

### Tác động tới throughput

Với **concurrency=4** và mọi consumer đều sleep backoff 4 giây, cả bốn slot có thể tạm thời không nhận công việc mới. Trong khi đó queue ready tăng, unacked có thể giữ nhiều message đã giao.

| Dấu hiệu | Khả năng |
| --- | --- |
| queue ready tăng, thread phần lớn đang sleep | Local backoff giữ consumer quá lâu |
| unacked tăng và ACK rate giảm | Listener chậm, prefetch lớn hoặc retry lâu |
| DB CPU tăng khi dependency vừa phục hồi | Retry storm thiếu jitter |
| Nhiều message vào DLQ đúng lúc outage dài | Budget quá ngắn so với recovery window |
| Latency P99 lớn dù số attempts ít | Per-attempt timeout quá cao |
| Cùng eventId có nhiều tác động | Thiếu idempotency |
| Attempt budget thường chạm nhưng deadline còn rộng | Cần điều tra loại lỗi/chính sách retry |

### Khi nào chuyển từ local retry sang delayed retry?

Không có ngưỡng tuyệt đối cho mọi hệ thống. Một hướng thực hành:
- Sự cố **vài trăm mili-giây đến vài giây**, xử lý nhanh, số lượt nhỏ: local retry hợp lý.
- Sự cố **hàng chục giây đến phút**, có nhiều message cạnh tranh: dùng broker delay hoặc durable scheduler để nhả consumer thread.
- Sự cố **dài/không rõ khi nào hồi phục**: quarantine hoặc durable work queue với lịch retry, cảnh báo và operator policy.

## 14. Quan sát retry budget và xác minh SLA

Nên có các metric tách biệt:

| Metric | Định nghĩa | Dùng để làm gì? |
| --- | --- | --- |
| **retry_attempt_total** | Tổng số lần thực thi handler do retry | Tính retry amplification |
| **retry_exhausted_total** | Hết attempts hoặc elapsed budget | Tìm lỗi kéo dài |
| **retry_delay_seconds** | Khoảng chờ giữa attempts | Kiểm tra backoff/jitter |
| **event_age_seconds** | Thời gian từ event phát sinh đến hiện tại | Quan sát deadline nghiệp vụ |
| **event_deadline_missed_total** | Event quá thời hạn xử lý | Cảnh báo SLA |
| **dependency_timeout_total** | Timeout của DB/HTTP theo dependency | Xác định bottleneck |
| **listener_processing_seconds** | Thời gian xử lý/attempt | Tuning timeout và concurrency |
| **queue_ready / queue_unacked** | Backlog và delivery chưa ACK | Đánh giá ảnh hưởng ngủ/backoff |
| **DLQ depth** | Event hết budget/permanent | Cần operator xử lý |
| **duplicate_event_total** | EventId đã xử lý xuất hiện lại | Đo redelivery/publisher retry |
| **publisher_confirm_nack / return** | Lỗi phía publish | Không nhầm với consumer retries |

Một log retry có cấu trúc nên gồm **eventId, consumerName, deliveryId nếu cần chẩn đoán, attemptNumber, maxAttempts, elapsedMs, deadlineAt, nextDelayMs, errorCategory, decision**. Không log raw payload chứa dữ liệu cá nhân.

**Phân biệt thời gian wall-clock và monotonic:** trong một JVM, đo elapsed bằng nguồn monotonic phù hợp sẽ ổn định hơn thay đổi đồng hồ hệ thống; với durable deadlineAt qua nhiều process, lưu timestamp UTC và xử lý khả năng clock skew giữa các node.

### Cảnh báo định lượng

Ví dụ một service cần xử lý event trong 30 giây:
- cảnh báo khi **oldest pending event > 20 giây**;
- cảnh báo khi **deadline missed > 0 trong cửa sổ theo dõi**;
- cảnh báo khi **retry_attempt_total tăng nhanh nhưng success không tăng**;
- cảnh báo khi **DLQ depth** tăng hoặc job không được claim.

Đây là **ngưỡng minh họa**, phải điều chỉnh theo SLA thực tế, tải và loại tác vụ.

## 15. Kiểm thử chính sách bằng sự cố có kiểm soát

### Bài 1 — Đếm đúng maxAttempts

Cấu hình **maxAttempts=4**, handler luôn ném một exception retryable. Ghi số lần method được gọi và khẳng định **chỉ có tối đa bốn attempts**, không phải năm. Sau đó cho thành công ở attempt #2 và kiểm tra không chạy thêm.

### Bài 2 — Tính lịch exponential

Chọn **initialInterval=200 ms**, **multiplier=3**, **maxInterval=1.000 ms**, **maxAttempts=6**. Tính các khoảng chờ: **200, 600, 1.000, 1.000, 1.000 ms**; tổng **3,8 giây** nếu cả sáu attempts đều thất bại. Đo thời gian thực và giải thích sai lệch do overhead/scheduling.

### Bài 3 — Deadline độc lập số lần

Cho mỗi attempt giả lập mất 700 ms, dùng lịch **0,5, 1, 2, 4 giây** và **maxAttempts=5**. Với deadline **8 giây**, xác định attempts nào có thể bắt đầu và kết thúc trong hạn. Tại sao maxAttempts=5 chưa đủ giới hạn tổng elapsed?

### Bài 4 — TimeoutRetryPolicy không ngắt HTTP call

Tạo một callback gọi HTTP client giả lập treo 20 giây, **RetryTemplate timeout policy=5 giây**. Quan sát behavior và bổ sung timeout 1 giây cho client. Giải thích sự khác nhau giữa **retry context timeout** với **per-attempt timeout**.

### Bài 5 — Poison message

Publish JSON sai cú pháp, dùng JSON converter và listener retry policy. Chứng minh lỗi permanent không nên ngủ qua nhiều backoff. Cấu hình error handler/recoverer để reject không requeue và kiểm tra DLQ trên queue test.

### Bài 6 — Retry nội bộ so với redelivery

Dùng Spring Retry stateless **maxAttempts=3**. Trong một lần delivery, cho handler lỗi hai lần rồi thành công lần ba. Ghi **retry attempt count**, **RabbitMQ redelivery flag** và **x-death**. Tại sao ba attempts không có nghĩa ba broker deliveries?

### Bài 7 — Backoff với jitter

Chạy 20 consumer mock cùng nhận HTTP 503. So sánh retry schedule cố định và schedule có jitter. Đếm số request đồng thời ở các mốc khôi phục, giải thích tác dụng giảm thundering herd.

### Bài 8 — Cross-delivery budget

Lưu **firstFailureAt, deadlineAt, totalAttempts** ở DB. Cố tình restart worker sau một local retry session rồi tiếp tục. Kiểm tra tổng attempts không bị reset theo restart, và event quá hạn chuyển QUARANTINED.

### Bài 9 — Idempotency sau ACK thất lạc

Để handler ghi DB thành công rồi mất connection trước ACK. Khi broker redeliver, consumer phát hiện eventId đã xử lý qua unique constraint, bỏ qua tác động và ACK an toàn. Đối chiếu việc chỉ giới hạn retry bằng maxAttempts có ngăn tác động trùng hay không.

### Bài 10 — Chọn kiến trúc cho sự cố dài

Giả sử email provider outage **10 phút**, Notification Service có **50 consumers**, hàng trăm nghìn message. Đề xuất local retries rất ngắn, broker delayed retry/durable scheduler, budget theo SLA, DLQ, idempotency và dashboard. Giải thích vì sao giữ 50 thread sleep nhiều phút là một lựa chọn tồi.

## 16. Câu hỏi tự đánh giá

1. Với maxAttempts=5, số lượt retry thêm sau lần đầu tối đa là bao nhiêu?
2. Exponential backoff **initial=500ms, multiplier=2, maxInterval=4s** tạo chuỗi chờ thế nào?
3. **maxInterval** có giống **maxElapsedTime** không?
4. Vì sao tổng thời gian xử lý phải cộng cả **attempt duration** và **sleep/backoff**?
5. TimeoutRetryPolicy có ngắt được một JDBC query đã kẹt 60 giây hay không?
6. Vì sao CompositeRetryPolicy theo logic **AND** phù hợp khi cần cả giới hạn số lần và elapsed?
7. Tại sao maxAttempts của một stateless retry context không tự giới hạn toàn bộ số broker redelivery?
8. Retry nội bộ có làm **x-death** tăng không? Khi nào x-death thay đổi?
9. Khi nào dùng **RejectAndDontRequeueRecoverer**? Nó có tự tạo DLQ không?
10. Vì sao recoverer chỉ log rồi return có thể làm message bị ACK thay vì dead-letter?
11. Tại sao lỗi HTTP timeout của payment API có thể yêu cầu idempotency key?
12. Khi nào nên chuyển từ local backoff sang retry queue hoặc durable scheduler?
13. **RabbitMQ 4.3 quorum delayed retry** có mặc nhiên exponential 2^n như Spring Retry không?
14. Vì sao cần lưu deadlineAt bên ngoài JVM nếu SLA phải tồn tại qua restart?
15. Cần những metric nào để biết một outage đã tạo retry storm?
16. Nếu một event đã được DB commit nhưng ACK mất, giới hạn maxAttempts có giúp chống ghi trùng không?
17. Nên làm gì khi event đã hết cả attempts và deadline nhưng vẫn cần điều tra?
18. Có nên bật cả Boot listener retry và custom listener retry interceptor cho cùng endpoint không? Vì sao?

## 17. Tài liệu tham khảo chính thức

- [Spring AMQP — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retry, stateless/stateful, recoverer, dead-letter và exception classification.
- [Spring AMQP 3.2 API — RetryInterceptorBuilder](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/config/RetryInterceptorBuilder.html): maxAttempts, backOffOptions, retryOperations và recoverer.
- [Spring Retry 2.0 — TimeoutRetryPolicy API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/policy/TimeoutRetryPolicy.html): thời hạn trong một retry context, không cưỡng bức dừng callback.
- [Spring Retry — CompositeRetryPolicy API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/policy/CompositeRetryPolicy.html): kết hợp nhiều điều kiện RetryPolicy.
- [Spring Retry — ExponentialBackOffPolicy API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/backoff/ExponentialBackOffPolicy.html): initialInterval, multiplier và maxInterval.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): fatal conversion và reject semantics.
- [Spring Boot — AMQP Support](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): listener/template retry properties và cấu hình factory.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK, redelivery và publisher confirms.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject, TTL, DLX, x-death và giới hạn dead-letter.
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): delivery-limit, delayed retry theo version và các semantics của quorum.

---

**Ghi nhớ:** Một chính sách retry đáng tin cậy phải kiểm soát **ba thứ khác nhau**: **maxAttempts** (tổng số lần xử lý, gồm lần đầu), **backoff** (khoảng chờ tăng dần có cap/jitter) và **deadline tổng** (giới hạn elapsed time/SLA). **MaxAttempts không giới hạn thời gian**, **maxInterval không phải maxElapsedTime**, và **TimeoutRetryPolicy không tự ngắt một attempt đang treo**. Với Spring AMQP, chọn đúng **stateless/stateful retry, recoverer, ACK/NACK, DLQ**, đồng thời ghi **deadline bền vững qua redelivery/restart** khi nghiệp vụ yêu cầu. **Retry không thay thế idempotency**: message có thể được giao hoặc xử lý lại kể cả sau khi một attempt đã thành công.
