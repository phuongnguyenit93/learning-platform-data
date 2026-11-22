# ConsumerRetryAuthSuccessfulEvent

`ConsumerRetryAuthSuccessfulEvent` là **application event của Spring Kafka** được phát ra khi một Kafka consumer **đã gọi `poll()` thành công trở lại sau khi phải retry vì lỗi authentication hoặc authorization**. Đây là tín hiệu hữu ích để ghi nhận rằng quá trình thử lại thao tác đọc Kafka sau lỗi bảo mật đã vượt qua một bước phục hồi.

Sự kiện này đặc biệt quan trọng trong hệ thống chạy lâu dài: token có thể hết hạn rồi được làm mới, ACL có thể được sửa, broker hoặc dịch vụ xác thực có thể tạm thời không sẵn sàng. Nếu listener container được cấu hình retry các lỗi xác thực/phân quyền thay vì dừng ngay, ứng dụng cần biết **khi nào lần poll thử lại đã thành công** để đóng cảnh báo, đánh giá sức khỏe consumer và tiếp tục theo dõi backlog.

Tuy nhiên, `ConsumerRetryAuthSuccessfulEvent` **không phải tín hiệu một business record đã xử lý thành công**. Một lần `poll()` có thể trả về không có record; offset chưa chắc đã tiến; consumer group có thể vừa rebalance; và một sự cố authorization tại producer, DLT hoặc dịch vụ bên ngoài có thể vẫn tồn tại. Cần đặt event trong toàn bộ chu trình Kafka consumer, thay vì diễn giải nó như lời chứng nhận ứng dụng đã hoàn toàn khỏe mạnh.

## 1. Bối cảnh: consumer poll gặp lỗi authentication hoặc authorization

Kafka consumer phải kết nối broker, xác thực danh tính và được cấp quyền đối với các tài nguyên mà nó sử dụng. Khi một bước bảo mật liên quan đến hoạt động đọc thất bại, Kafka client có thể ném các exception như:

- `AuthenticationException`: lỗi xác thực, có thể liên quan SASL, token hoặc cơ chế bảo mật.
- `AuthorizationException`: lỗi phân quyền, chẳng hạn không có quyền đọc topic hoặc tham gia consumer group theo ACL.
- Các subtype cụ thể do Kafka client/broker phát ra tùy phiên bản và giao thức.

Nếu listener container không có cơ chế retry được cấu hình cho các exception này, consumer có thể dừng và phát lifecycle event tương ứng, như `ConsumerStoppedEvent` với reason liên quan `AUTH` trong những phiên bản hỗ trợ.

Spring Kafka cung cấp thuộc tính container `authExceptionRetryInterval`. Khi được cấu hình trong các phiên bản hỗ trợ, listener container có thể **chờ rồi thử `poll()` lại** sau khi gặp `AuthenticationException` hoặc `AuthorizationException`.

Trong quá trình đó, hai event rất dễ bị nhầm với nhau:

| Event | Thời điểm | Ý nghĩa |
|---|---|---|
| `ConsumerRetryAuthEvent` | Container đang chuẩn bị retry sau lỗi xác thực/phân quyền | Consumer vẫn trong giai đoạn lỗi/chờ thử lại. |
| **`ConsumerRetryAuthSuccessfulEvent`** | **Một lần `poll()` sau giai đoạn retry thành công** | **Consumer đã vượt qua lần thử poll từng bị cản bởi lỗi auth.** |
| `ConsumerStoppedEvent` | Consumer dừng, có thể do auth hoặc lỗi khác | Một vòng đời consumer đã kết thúc; không phải sự kiện hồi phục. |
| `ConsumerStartedEvent` | Consumer bắt đầu một vòng đời | Không bảo đảm lần poll sau đó sẽ thành công hoặc có dữ liệu. |

Không phải mọi lỗi auth đều dẫn đến `ConsumerRetryAuthSuccessfulEvent`. Nếu retry chưa được bật, consumer đã dừng, lỗi không thể khắc phục, hoặc ứng dụng bị shutdown trước khi poll thành công, sự kiện hồi phục sẽ không xuất hiện.

## 2. Luồng retry auth và thời điểm phát success event

Giả sử một service đọc topic `payments.events`. Consumer đang chạy ổn định thì broker từ chối một lần poll vì thông tin xác thực tạm thời không còn hợp lệ. Container được cấu hình retry auth với khoảng chờ nhất định.

~~~mermaid
sequenceDiagram
    participant L as Spring Kafka Listener Container
    participant C as Kafka Consumer
    participant B as Kafka Broker / Security
    participant E as Application Event Observer
    L->>C: poll()
    C->>B: Fetch / group operation
    B-->>C: Authentication/Authorization error
    C-->>L: AuthenticationException / AuthorizationException
    L->>E: ConsumerRetryAuthEvent
    Note over L: Chờ authExceptionRetryInterval
    L->>C: poll() thử lại
    C->>B: Fetch / group operation
    alt Quyền truy cập vẫn lỗi
        B-->>C: Authentication/Authorization error
        C-->>L: Exception
        L->>E: ConsumerRetryAuthEvent
        Note over L: Tiếp tục backoff/retry theo lifecycle
    else Poll thành công
        B-->>C: Poll thành công, có thể không có record
        C-->>L: ConsumerRecords
        L->>E: ConsumerRetryAuthSuccessfulEvent
        L->>L: Tiếp tục vòng xử lý listener
    end
~~~

Điểm cần nhớ:

1. `ConsumerRetryAuthEvent` thể hiện **thời điểm thử lại**, không phải đã phục hồi.
2. `ConsumerRetryAuthSuccessfulEvent` đánh dấu **một poll thành công sau retry auth**.
3. Event hồi phục không mang nghĩa record vừa được deserialize, xử lý hoặc commit thành công.
4. Sau thành công, Kafka consumer có thể phải xử lý assignment/rebalance hoặc bắt đầu từ committed offset phù hợp.
5. Nếu lỗi auth lại tái diễn sau đó, một chu kỳ retry mới có thể bắt đầu.

Một lần hồi phục có thể xảy ra khi poll trả về **0 record**. Vì vậy, nếu dashboard muốn thể hiện luồng nghiệp vụ đã hoạt động trở lại, phải kết hợp với metrics về record consumption, listener success, commit và lag.

## 3. Phạm vi chính xác của ConsumerRetryAuthSuccessfulEvent

Sự kiện này liên quan đến **Kafka consumer poll bị lỗi vì authentication/authorization rồi retry thành công**. Nó không phải một callback chung cho tất cả loại retry trong Spring Kafka.

Những trường hợp **không nên suy diễn** từ event:

- Listener gặp exception nghiệp vụ rồi `DefaultErrorHandler` retry thành công.
- `@RetryableTopic` chuyển record giữa các retry topics.
- `DeadLetterPublishingRecoverer` gửi record lỗi vào DLT.
- Kafka producer retry một lần `send()` thất bại.
- KafkaTemplate hoàn tất Kafka transaction.
- Database reconnect thành công.
- HTTP client refresh token dùng cho dịch vụ bên ngoài.
- Một consumer khác trong cùng group đã phục hồi.

Các cơ chế trên có hệ thống logging/metrics hoặc event riêng. Không tăng bộ đếm “business retry recovered” chỉ vì một `ConsumerRetryAuthSuccessfulEvent` xuất hiện.

### Poll success khác processing success

Có thể diễn giải qua các trạng thái:

~~~text
Consumer có quyền kết nối/poll:
  poll() thành công
          |
          v
Consumer được assigned partition:
  có assignment, có thể đang rỗng
          |
          v
Consumer fetch được record:
  có ConsumerRecords
          |
          v
Listener xử lý nghiệp vụ:
  có thể thành công hoặc ném exception
          |
          v
Offset commit/recovery:
  phụ thuộc AckMode, transaction, error handler
~~~

`ConsumerRetryAuthSuccessfulEvent` chỉ cung cấp tín hiệu tại **bước poll phục hồi**. Những bước còn lại cần kiểm tra độc lập.

## 4. Điều kiện để Spring Kafka retry auth

Thuộc tính `authExceptionRetryInterval` nằm ở **listener container properties**, không phải là tham số Kafka broker và cũng không phải cùng nhóm với `retries` của Kafka producer.

Về nguyên tắc:

- Khi cấu hình khoảng retry phù hợp, Spring Kafka có thể retry những `AuthenticationException`/`AuthorizationException` phát sinh từ đường poll của consumer.
- Mỗi lần chuẩn bị retry có thể có `ConsumerRetryAuthEvent` để ứng dụng quan sát.
- Sau một lần poll thành công trong chuỗi này, container phát `ConsumerRetryAuthSuccessfulEvent`.
- Nếu ứng dụng yêu cầu dừng hoặc lỗi không thể tiếp tục, luồng lifecycle có thể kết thúc thay vì phát sự kiện thành công.

Không nên đặt khoảng retry quá nhỏ khiến consumer gửi hàng nghìn request vô ích trong lúc broker ACL/credential chưa được sửa. Ngược lại, retry quá lâu hoặc chặn vòng poll không phù hợp có thể gây vấn đề consumer group membership.

### Cấu hình qua ConcurrentKafkaListenerContainerFactory

Một ví dụ Spring Kafka dùng container factory riêng:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
    paymentKafkaListenerContainerFactory(
            ConsumerFactory<String, PaymentEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, PaymentEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAuthExceptionRetryInterval(
                Duration.ofSeconds(15));

        return factory;
    }
}
~~~

Ví dụ này thể hiện cách đặt khoảng retry 15 giây trên container properties. `PaymentEvent` là kiểu dữ liệu do ứng dụng định nghĩa. Các import như `Duration`, `ConcurrentKafkaListenerContainerFactory` và `ConsumerFactory` cần được bổ sung theo dự án.

Listener sử dụng factory:

~~~java
@KafkaListener(
        topics = "payments.events",
        groupId = "payment-service",
        containerFactory = "paymentKafkaListenerContainerFactory")
public void onPayment(PaymentEvent event) {
    paymentService.processIdempotently(event);
}
~~~

Giá trị 15 giây chỉ để minh họa. Trong production, cần chọn khoảng retry theo đặc tính dịch vụ xác thực, SLA và thời gian consumer group cho phép. API setter và hành vi có thể khác theo phiên bản Spring Kafka; xác nhận `authExceptionRetryInterval` tồn tại và nhận `Duration` trong version đang dùng.

### Đừng cấu hình nhầm ở Kafka client

Đoạn sau **không phải** một thuộc tính Kafka consumer chuẩn:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        authExceptionRetryInterval: 15000
~~~

Khai báo một tên property tùy ý vào map Kafka consumer properties không bảo đảm Spring Kafka container sẽ dùng nó. Cần cấu hình container properties bằng cơ chế mà Spring Kafka/Spring Boot của dự án hỗ trợ, chẳng hạn factory customization.

Các thuộc tính như `security.protocol`, `sasl.mechanism`, JAAS, TLS, OAuth, topic/group ACL vẫn phải được cấu hình đúng. `authExceptionRetryInterval` chỉ điều khiển **thử lại**, không thay thế chính sách bảo mật.

## 5. Đăng ký @EventListener cho event phục hồi

Vì `ConsumerRetryAuthSuccessfulEvent` là Spring application event, ứng dụng có thể lắng nghe bằng `@EventListener`:

~~~java
@Component
public class KafkaAuthRecoveryObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaAuthRecoveryObserver.class);

    @EventListener
    public void onAuthRetrySuccess(
            ConsumerRetryAuthSuccessfulEvent event) {

        log.info(
                "Kafka consumer auth retry recovered; sourceType={}",
                event.getSource().getClass().getSimpleName());
    }
}
~~~

Những import chính gồm:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerRetryAuthSuccessfulEvent;
import org.springframework.stereotype.Component;
~~~

Cách xử lý này đơn giản: nhận event, ghi log để chứng minh một lần poll phục hồi đã xảy ra. Khi nhiều instance/child consumer cùng chạy, log cần thêm thông tin application instance, listener ID, client ID hoặc container ID nếu API và ngữ cảnh hiện tại cung cấp.

### Kết hợp event retry và recovery

Một observer có thể đăng ký hai phương thức:

~~~java
@Component
public class KafkaAuthEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaAuthEventObserver.class);

    @EventListener
    public void onAuthRetry(ConsumerRetryAuthEvent event) {
        log.warn("Kafka consumer is retrying after auth-related failure");
    }

    @EventListener
    public void onAuthRecovered(
            ConsumerRetryAuthSuccessfulEvent event) {
        log.info("Kafka consumer poll succeeded after auth retry");
    }
}
~~~

Đoạn code tránh dựa vào các field không phải phiên bản nào cũng hỗ trợ. Ở những phiên bản cung cấp reason cho `ConsumerRetryAuthEvent`, có thể dùng phân loại authentication/authorization để enrich log và metrics. Không mặc định `ConsumerRetryAuthSuccessfulEvent` có đầy đủ exception gốc hoặc một `getReason()` giống retry event.

### Ý nghĩa của event source

`getSource()` là source theo cơ chế Spring `ApplicationEvent`. Nó hữu ích cho liên kết observer với container đã phát event, nhưng không nên lưu toàn bộ object source vào một hàng đợi giám sát lưu lâu. Điều đó có thể giữ reference tới container/consumer lifecycle, tăng bộ nhớ và làm khó serialization.

Nên **trích xuất metadata cần thiết** thành một record đơn giản nếu cần gửi sang logging, metrics hoặc notification service.

## 6. Event được phát đồng bộ hay bất đồng bộ?

Spring application event mặc định thường được phát đồng bộ qua `ApplicationEventMulticaster`. Với lifecycle của Spring Kafka, observer có thể chạy trên thread liên quan consumer/container.

Điều này dẫn đến một yêu cầu vận hành: **handler phải nhẹ và không được làm nghẽn vòng poll**.

Không nên:

- `Thread.sleep` nhiều giây để chờ các component khác.
- Gọi database/network I/O không timeout.
- Đồng bộ tải lại toàn bộ secrets/certificates trong callback.
- Thực hiện một HTTP notification chậm ở ngay consumer thread.
- Gọi `KafkaConsumer.poll()` hoặc `commitSync()` từ event listener.
- Tự ý `start()`, `stop()` hoặc `seek()` container khi chưa kiểm tra lifecycle.

Nếu cần gửi thông báo đến hệ thống ngoài, hãy chuyển một DTO nhỏ sang executor/queue phù hợp; không truyền reference consumer cho background thread. `KafkaConsumer` nói chung không thread-safe.

Nếu ứng dụng tự cấu hình multicaster bất đồng bộ, event observer có thể chạy trên một thread khác. Khi đó không được giả định thứ tự callback hoặc thread-local context giống như luồng phát đồng bộ. Nên dùng thời gian và correlation metadata riêng khi dựng incident timeline.

## 7. Một event hồi phục không có nghĩa authentication đã “khỏi vĩnh viễn”

Một lần poll thành công chỉ chứng minh trạng thái ở **thời điểm đó**. Những tình huống sau vẫn có thể xảy ra:

- OAuth token được làm mới nhưng lại hết hạn ở chu kỳ tiếp theo.
- ACL vừa được cấp nhưng bị thu hồi sau đó.
- Broker khác trong cluster vẫn có cấu hình lệch hoặc dịch vụ xác thực không ổn định.
- Consumer đã poll thành công nhưng producer gửi DLT thiếu quyền.
- Topic gốc có quyền đọc nhưng topic khác cùng ứng dụng không có quyền.
- Consumer có thể poll nhưng listener xử lý record thất bại vì lỗi schema hoặc database.
- Consumer group đang rebalance khiến record processing chưa quay lại ngay.

Do đó, không dùng `ConsumerRetryAuthSuccessfulEvent` làm chứng cứ rằng toàn bộ service đã “healthy” một cách tuyệt đối. Có thể xem nó là **recovery signal theo consumer**, kết hợp với điều kiện ready/healthy khác.

### Readiness và liveness

- **Liveness:** process còn hoạt động và có khả năng tiếp tục phục vụ/khôi phục theo thiết kế hay không.
- **Readiness:** instance hiện có sẵn sàng nhận và xử lý workload như kỳ vọng hay không.
- **Auth retry success:** consumer từng gặp auth error nay đã poll thành công một lần.

Ba điều không hoàn toàn tương đương. Nếu đang điều chỉnh Kubernetes probes, tránh cấu hình liveness giết pod liên tục chỉ vì một outage authentication tạm thời mà container vốn được thiết kế để retry. Đồng thời, readiness không nên được đánh dấu tốt chỉ dựa trên một event nếu listener vẫn pause, không có assignment hoặc backlog tiếp tục tăng.

## 8. ConsumerRetryAuthEvent và phân biệt authentication/authorization

`ConsumerRetryAuthEvent` là tín hiệu phát khi consumer đang retry vì một trong hai nhóm lỗi bảo mật. Authentication và authorization có nguyên nhân khác nhau.

| Nhóm | Triệu chứng có thể gặp | Điều tra |
|---|---|---|
| Authentication | Broker từ chối danh tính; SASL/OAuth/TLS handshake hoặc token không hợp lệ | Secret, certificate, token refresh, clock skew, JAAS, SASL mechanism. |
| Authorization | Client xác thực được nhưng không có quyền sử dụng topic/group | Kafka ACL, principal mapping, quyền READ/DESCRIBE và group access. |
| Broker/security service tạm thời | Một lần auth thất bại rồi thành công sau khi hệ thống ngoài phục hồi | Broker logs, identity provider availability, retry timing. |
| Thay đổi cấu hình client | Sau deployment mọi poll tiếp tục thất bại | Effective config, môi trường và secret mount. |

Tùy version, `ConsumerRetryAuthEvent` có thể cung cấp phân loại reason giúp tách hai nhóm trên. Đối với `ConsumerRetryAuthSuccessfulEvent`, cần liên hệ sự kiện thành công với những sự kiện lỗi trước đó cùng consumer/container để biết **nó phục hồi sau nhóm lỗi nào**.

### Khi nào retry hữu ích?

Retry thường hữu ích khi:

- Một token có thể được refresh tự động.
- ACL đang được cập nhật theo một thay đổi đã được phê duyệt.
- Kafka broker hoặc hệ thống xác thực đang gặp lỗi thoáng qua.
- Quá trình rotation secret có cơ chế reload/reconnect đúng.
- Quyền truy cập được cấp sau khi service khởi động.

Retry có thể **không** đủ khi:

- Password sai cố định trong config.
- Client thiếu role/ACL và không có tiến trình cấp lại quyền.
- Certificate hết hạn mà client không reload được.
- Topic/group bị cấm theo chính sách dài hạn.
- Quyền producer hoặc DLT khác quyền consumer, trong khi event chỉ phản ánh một lần consumer poll.

Không nên tăng retry frequency để “sửa” nguyên nhân cấu hình không thay đổi.

## 9. authExceptionRetryInterval và max.poll.interval.ms

Kafka consumer cần gọi `poll()` đủ thường xuyên để duy trì tiến độ của group. `max.poll.interval.ms` đặt giới hạn thời gian tối đa giữa những lần poll theo cơ chế consumer group; `session.timeout.ms` và heartbeat liên quan việc phát hiện member không còn hoạt động.

Khi thiết kế retry auth, cần kiểm soát:

- Khoảng chờ `authExceptionRetryInterval` giữa các lần retry.
- Thời gian một lần `poll()`/network request thất bại.
- Thời gian listener/callback xử lý trước khi vòng poll quay lại.
- Các giới hạn consumer group như `max.poll.interval.ms`.
- Session timeout, membership tĩnh và rebalance nếu thời gian outage kéo dài.
- Shutdown responsiveness: consumer phải có khả năng ngừng khi ứng dụng được yêu cầu stop.

Một khoảng retry ngắn hơn `max.poll.interval.ms` thường là điều kiện cần để tránh tự giữ consumer thread quá lâu; **không đủ** nếu mỗi lần poll hoặc các công việc khác đã mất gần hết ngân sách thời gian.

### Ví dụ thời gian

~~~text
max.poll.interval.ms = 300000  (5 phút)
authExceptionRetryInterval = 15000  (15 giây)

T0: poll -> AuthorizationException
T1: phát ConsumerRetryAuthEvent
T2: chờ khoảng retry
T3: poll tiếp -> AuthorizationException
T4: retry tiếp
T5: ACL được sửa
T6: poll thành công -> ConsumerRetryAuthSuccessfulEvent
~~~

Nếu outage kéo dài 20 phút, consumer có thể đã bị coordinator xem là mất membership hoặc trải qua rebalance tùy group protocol và lifecycle client. Event thành công sau đó không bảo đảm consumer vẫn giữ assignment cũ hoặc không có record bị giao lại.

### Retry interval không phải SLA phục hồi

Nếu config retry mỗi 15 giây, thời gian hồi phục thực tế không được bảo đảm chính xác là 15 giây. Các yếu tố khác gồm network, DNS, broker availability, authentication mechanism, metadata refresh, scheduling, group join và thời gian ứng dụng sẵn sàng xử lý record.

Đặt SLA theo đo lường thực tế, không chỉ theo giá trị interval.

## 10. Quan hệ với consumer group, rebalance và offset

Lỗi authentication/authorization có thể ảnh hưởng việc join group, fetch record và các thao tác client liên quan. Khi consumer retry thành công, partition ownership có thể đã thay đổi.

Ví dụ:

~~~text
Trước sự cố:
  Consumer A -> Partition 0, 1
  Consumer B -> Partition 2, 3

Trong outage auth:
  A không poll thành công một thời gian dài
  Group có thể rebalance

Sau khi poll thành công:
  A có thể nhận assignment khác
  Committed offset quyết định điểm đọc tương ứng
~~~

Không dùng `ConsumerRetryAuthSuccessfulEvent` để tự commit một offset mới hoặc seek tới cuối topic. Event không chứa bằng chứng nghiệp vụ rằng mọi record phía trước đã được xử lý.

### Khi record bị giao lại

Giả sử consumer đã cập nhật database nhưng chưa commit offset thì gặp auth outage:

1. Database update đã thành công.
2. Consumer không commit offset nguồn.
3. Group membership thay đổi hoặc consumer restart.
4. Một member hợp lệ đọc lại record từ committed offset trước đó.
5. Cùng business event có thể chạy lần thứ hai.

Cần idempotency như event ID ổn định và unique constraint/inbox trong transaction database. Auth recovery event không thể loại bỏ cửa sổ duplicate này.

### Offset commit sau phục hồi

Sau khi poll thành công, listener container tiếp tục xử lý theo `AckMode` hoặc Kafka transaction. Chỉ khi record được xử lý/recovered theo policy thì offset mới được phép tiến.

Không gọi `Acknowledgment.acknowledge()` hoặc `commitSync()` từ auth recovery observer. Observer không sở hữu vòng đời xử lý record và có thể chạy khác thread với consumer.

## 11. Quan hệ với Listener error handler, retry topic và DLT

Một lỗi authentication khi poll và một lỗi nghiệp vụ khi xử lý record nằm ở **hai tầng khác nhau**:

~~~mermaid
flowchart TD
    A[Listener container] --> B[Consumer poll]
    B --> C{Poll gặp auth exception?}
    C -->|Có| D[authExceptionRetryInterval]
    D --> E[ConsumerRetryAuthEvent]
    E --> B
    C -->|Không| F[ConsumerRetryAuthSuccessfulEvent nếu vừa retry auth]
    F --> G[Records / listener]
    G --> H{Business processing thành công?}
    H -->|Có| I[Commit theo policy]
    H -->|Không| J[DefaultErrorHandler hoặc rollback/retry]
    J --> K[Retry record / recovery / DLT]
~~~

Trong sơ đồ, nếu chưa từng có retry auth thì poll thành công bình thường **không nhất thiết phát** `ConsumerRetryAuthSuccessfulEvent`.

- `DefaultErrorHandler` giải quyết lỗi listener/record trong container không transactional theo policy phù hợp.
- `@RetryableTopic` định tuyến record sang retry topics để thử xử lý nghiệp vụ sau.
- `DeadLetterPublishingRecoverer` gửi record không thể xử lý sang DLT.
- `authExceptionRetryInterval` xử lý tình huống **poll auth failure**.

Vì vậy không dùng `ConsumerRetryAuthSuccessfulEvent` làm điều kiện xóa DLT hoặc đóng mọi ticket listener processing failure. Có thể auth đã phục hồi nhưng DLT producer vẫn thiếu quyền `WRITE`.

## 12. Quan hệ với ContainerStoppedEvent và ConsumerStoppedEvent

Khi không retry hoặc không thể tiếp tục sau auth exception, consumer có thể dừng. Ở những phiên bản hỗ trợ phân loại này, `ConsumerStoppedEvent` với reason `AUTH` thể hiện một đường lifecycle khác với việc poll retry thành công.

| Diễn biến | Event quan trọng | Hàm ý |
|---|---|---|
| Consumer bắt đầu chạy bình thường | `ConsumerStartedEvent` | Consumer đã bắt đầu vòng đời, chưa chứng minh auth recovery. |
| Poll gặp lỗi auth, container sẽ retry | `ConsumerRetryAuthEvent` | Lỗi đang được retry; consumer chưa hồi phục. |
| Poll thành công sau auth retry | **`ConsumerRetryAuthSuccessfulEvent`** | Consumer vừa vượt qua một lần poll sau auth failure. |
| Consumer dừng vì auth issue | `ConsumerStoppedEvent` / reason liên quan `AUTH` | Consumer stop, cần điều tra hoặc khởi động lại theo policy. |
| Cả listener container dừng | `ContainerStoppedEvent` | Trạng thái container-level, không phải riêng một lần poll. |

Nếu ứng dụng restart container sau khi auth failure mà không sử dụng cơ chế retry in-place, lần khởi động mới có thể phát `ConsumerStartedEvent` mà không phát `ConsumerRetryAuthSuccessfulEvent`. Không định nghĩa “đã phục hồi” chỉ bằng một loại event duy nhất trong mọi đường lỗi.

## 13. Concurrency: nhiều consumer có thể hồi phục riêng

Với `ConcurrentMessageListenerContainer` và `concurrency=4`, Spring Kafka thường quản lý bốn consumer con. Mỗi consumer có vòng poll và có thể phát những event auth retry/success của riêng mình.

Ví dụ:

~~~text
Parent listener: paymentsListener
  Child 0: auth retry -> recovered
  Child 1: auth retry -> vẫn thất bại
  Child 2: không gặp lỗi auth
  Child 3: auth retry -> recovered

Có 2 ConsumerRetryAuthSuccessfulEvent
Không có nghĩa tất cả 4 child đều khỏe.
~~~

Nếu authentication outage ảnh hưởng toàn Kafka cluster, nhiều consumer có thể phát event gần cùng lúc khi quyền truy cập được sửa. Đừng dùng một lần success event để đánh dấu **toàn consumer group** đã phục hồi.

Nên theo dõi:

- Số consumer thực đang chạy so với cấu hình concurrency và replica count.
- Mỗi child listener/container có retry/auth issue đang mở hay không.
- Consumer group membership và assignment thực tế.
- Lag, record processing và committed offsets sau recovery.
- Mức độ bão hòa downstream khi nhiều consumer cùng trở lại.

### Chống cảnh báo trùng

Nếu nhiều child consumer hồi phục đồng thời, gửi một thông báo tổng hợp cho incident thay vì hàng chục thông báo “Kafka đã ổn”. Dùng grouping key có ý nghĩa: environment, Kafka cluster, service, consumer group và giai đoạn outage.

## 14. Ghi nhận recovery với Micrometer

Một bộ đếm đơn giản:

~~~java
@Component
public class KafkaAuthRecoveryMetrics {

    private final MeterRegistry meterRegistry;

    public KafkaAuthRecoveryMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        meterRegistry.counter(
                "kafka.consumer.auth.retry.events").increment();
    }

    @EventListener
    public void onRecovered(ConsumerRetryAuthSuccessfulEvent event) {
        meterRegistry.counter(
                "kafka.consumer.auth.retry.success.events").increment();
    }
}
~~~

Hai counter này đếm **sự kiện**, không phải số record retry hoặc xác suất xử lý nghiệp vụ thành công. Một consumer có thể phát nhiều retry events trước một recovery event; nhiều consumer khác nhau có số chu kỳ retry khác nhau.

Nếu cần tính thời gian outage, hãy dùng một state tracker theo consumer/container được nhận diện ổn định, lưu timestamp khi lần đầu gặp auth retry và đóng trạng thái đó khi recovery event tương ứng xuất hiện. Trong trường hợp container stop mà không recovery, trạng thái phải được đóng theo **failed/stopped**, không tính là recovered.

### Theo dõi thời gian từ retry đến poll thành công

~~~text
auth_retry_started_at = thời điểm retry auth đầu tiên cho consumer
auth_poll_recovered_at = thời điểm ConsumerRetryAuthSuccessfulEvent
duration = recovered_at - started_at
~~~

Đây là chỉ số **thời gian poll bị gián đoạn do auth**, không nhất thiết là thời gian nghiệp vụ mất khả năng xử lý. Đối chiếu với consumer lag, processing rate và consumer group status để biết ảnh hưởng thực tế.

Nếu app restart giữa hai thời điểm, state tracker trong bộ nhớ sẽ mất lịch sử. Một hệ thống giám sát tập trung có thể dùng structured logs/trace để dựng lại sự cố.

## 15. Tránh nhầm recovery signal với health signal

Một incident có thể chia thành nhiều giai đoạn:

| Giai đoạn | Tín hiệu | Cách xác nhận |
|---|---|---|
| Auth issue bắt đầu | `ConsumerRetryAuthEvent` hoặc Kafka authentication error | Log exception và retry state. |
| Auth issue kéo dài | Nhiều retry events, không có successful poll | Backoff attempts, broker logs và group membership. |
| Poll đã phục hồi | `ConsumerRetryAuthSuccessfulEvent` | Application event và timestamp. |
| Consumer nhận assignment hợp lệ | Group assignment/consumer metrics | Consumer đã join group hoặc giữ assignment phù hợp. |
| Listener xử lý tiếp | Record consumption, listener success | Processing metrics và logs. |
| Backlog được xử lý | Partition lag giảm, offsets tiến | End offset, committed offset và throughput. |
| Incident đóng | Kiểm tra nhiều tín hiệu ổn định qua một khoảng thời gian | SLO phục hồi và không còn auth failures. |

Nếu chỉ dựa vào event thành công để đóng incident ngay lập tức, có thể bỏ sót việc consumer đang liên tục nhận thành công một poll rồi thất bại ở poll tiếp theo. Nên dùng **stability window**: yêu cầu các lần poll/processing/assignment ổn định trong một khoảng đủ dài theo SLA trước khi đánh dấu hoàn toàn recovered.

## 16. Retry auth có thể không khắc phục credential sai cố định

Giả sử ứng dụng khởi động với password sai lưu trong config và không có cơ chế reload. Consumer sẽ tiếp tục thất bại dù `authExceptionRetryInterval` được đặt 15 giây. Kafka broker không tự thay password trong process client.

Cần phân biệt:

- **Credential được rotate và client có thể làm mới:** retry có thể thành công sau refresh.
- **ACL chưa được cấp nhưng operator sẽ cấp:** retry có thể thành công sau thay đổi broker.
- **Credential sai cố định, không có reload:** cần sửa cấu hình/secret và có thể restart theo quy trình.
- **Certificate hết hạn:** có thể cần thay file/cấu hình TLS và khởi tạo lại client.
- **Broker hoặc identity provider tạm thời gián đoạn:** retry có backoff có thể giúp vượt qua.

Điều chỉnh retry interval không thay thế công việc sửa nguyên nhân. Nếu có nguy cơ credential bị lộ, thực hiện rotation theo quy trình bảo mật; không log secret để “debug” auth.

## 17. Lỗi producer và DLT không tự hồi phục theo consumer event

Một service có thể vừa consume vừa produce:

~~~text
payments.events  --consumer-->  PaymentService
                                    |
                                    +--> payments.results
                                    |
                                    +--> payments.events.DLT
~~~

Nếu consumer được sửa quyền `READ` và poll thành công, `ConsumerRetryAuthSuccessfulEvent` có thể xuất hiện. Nhưng producer gửi `payments.results` hoặc DLT vẫn có thể bị từ chối vì thiếu `WRITE` trên topic đích.

Để xác nhận end-to-end:

1. Kiểm tra consumer poll/assignment.
2. Kiểm tra listener xử lý business event.
3. Kiểm tra producer send result/transaction commit.
4. Kiểm tra DLT recovery nếu có record lỗi.
5. Kiểm tra input committed offset và output visibility.
6. Kiểm tra external database/API nếu nằm trong quy trình.

Một auth recovery event của consumer không có thẩm quyền xác nhận mọi bước này.

## 18. Khi Kafka transaction và fencing cùng xuất hiện

Trong transactional consume–transform–produce, consumer được phép đọc input, còn producer transactional phải có quyền khởi tạo và hoàn tất transaction với Kafka coordinator. Lỗi authentication/authorization có thể xuất hiện ở nhiều bước: group join, fetch, producer init, publish hoặc transaction commit.

`ConsumerRetryAuthSuccessfulEvent` chỉ thể hiện **poll auth retry thành công**, không giải quyết producer fencing hoặc transactional ID collision.

Nếu có đồng thời:

- `ConsumerRetryAuthSuccessfulEvent` từ consumer,
- `ProducerFencedException` ở producer,
- transaction abort và consumer lag tăng,

thì cần điều tra riêng producer identity (`transactionIdPrefix`, `transactional.id`, epoch) và consumer group membership. Đừng đánh dấu transaction đã ổn chỉ vì consumer poll lại được.

Trong Kafka transactional listener, offset đầu vào và Kafka output có thể được commit cùng transaction nếu wiring đúng. Nhưng database/HTTP vẫn cần idempotency. Khi auth outage hoặc rebalance khiến record được giao lại, một external side effect có thể bị thực hiện lần hai.

## 19. Bảo mật dữ liệu khi log auth retry

Auth errors có thể đi kèm thông tin nhạy cảm trong client config hoặc exception messages. Một event handler không nên đưa nguyên văn credential, token, JAAS config hoặc certificate private key vào logs.

Log nên có:

- Service, environment, Kafka cluster/alias.
- Listener/container ID và group ID nếu có.
- Thời điểm retry bắt đầu và recovery.
- Nhóm lỗi authentication/authorization.
- Số lần retry hoặc elapsed duration theo policy.
- Trạng thái consumer group sau recovery.
- Correlation/incident ID được tạo bởi hệ thống vận hành.

Không log payload Kafka chỉ để chứng minh consumer đã poll thành công. Consumer có thể poll thành công với không record, và event recovery không cần payload.

## 20. Kiểm thử ConsumerRetryAuthSuccessfulEvent

Có thể kiểm thử observer ở mức Spring application event và kiểm thử retry integration với một Kafka broker test có cấu hình bảo mật.

### Unit/application test cho observer

Một event recorder có thể thu event để test việc lắng nghe:

~~~java
@Component
public class AuthEventRecorder {

    private final BlockingQueue<String> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        events.offer("RETRY");
    }

    @EventListener
    public void onRecovered(
            ConsumerRetryAuthSuccessfulEvent event) {
        events.offer("RECOVERED");
    }

    public String await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
~~~

Ví dụ tập trung vào kỹ thuật observer; các import như `BlockingQueue`, `LinkedBlockingQueue`, `TimeUnit` cần được bổ sung. Trong production không lưu vô hạn event object trong queue. Nếu tự xây dựng event trong unit test, dùng constructor phù hợp với phiên bản Spring Kafka thực tế thay vì đoán chữ ký.

### Integration test auth recovery

1. Khởi chạy một Kafka broker test có SASL/ACL hoặc cơ chế xác thực tương ứng.
2. Tạo topic, group và một principal có thể điều chỉnh quyền trong test.
3. Cấu hình consumer container với `authExceptionRetryInterval` hữu hạn.
4. Cố ý khiến consumer poll gặp `AuthenticationException`/`AuthorizationException`.
5. Xác minh `ConsumerRetryAuthEvent` xuất hiện.
6. Khôi phục quyền/credential theo cách Kafka client có thể nhận được.
7. Đợi lần poll thành công và xác minh `ConsumerRetryAuthSuccessfulEvent`.
8. Sau đó publish một record test và kiểm tra listener xử lý, offset/lag theo policy.
9. Thử một kịch bản không phục hồi để xác nhận stop/alert policy phù hợp.
10. Dừng test containers và xác minh observer không kéo dài shutdown.

Kafka test broker không bật security/ACL thường **không đủ** để chứng minh luồng auth retry. Cần mô phỏng lỗi thực tế hoặc dùng integration environment phù hợp. Không cố tình thu hồi ACL/rotate credential trên cluster production đang phục vụ nghiệp vụ.

### Kịch bản test concurrency

Với `concurrency=3`, cho nhiều consumer con gặp auth failure. Kiểm tra rằng recorder và metrics không nhầm success của một child thành recovery của cả ba. Đồng thời test shutdown giữa lúc retry để chắc chắn controller không khởi động lại một container đang được dừng có chủ đích.

## 21. Monitoring dashboard và alerting

| Tín hiệu | Phạm vi | Ý nghĩa |
|---|---|---|
| Auth retry event count | Consumer/container | Tần suất lỗi poll cần retry. |
| Auth retry success event count | Consumer/container | Số chu kỳ poll phục hồi được quan sát. |
| Duration từ retry đầu đến success | Consumer/container | Thời gian consumer không poll thành công vì auth. |
| Last successful poll time | Consumer/client | Consumer có tiếp tục poll sau recovery không. |
| Group member count và assignment | Consumer group | Có member nhận partition hợp lệ không. |
| Lag theo partition | Topic/group | Backlog có tăng trong outage và giảm sau recovery không. |
| Listener record processing rate | Listener | Nghiệp vụ có tiếp tục xử lý không. |
| Commit latency / committed offsets | Consumer group | Offset có tiến theo policy không. |
| Authentication/authorization failures | Kafka client/broker | Nguyên nhân có lặp lại hoặc ảnh hưởng rộng không. |
| Producer/DLT errors | Producer/recoverer | Không bỏ sót lỗi ở nhánh ngoài consumer poll. |

Đặt cảnh báo theo diễn biến thay vì một con số đơn lẻ:

- Có retry auth liên tục nhưng không có successful poll trong thời gian vượt SLA.
- Retry success xuất hiện nhưng sau đó poll errors lại tái diễn.
- Consumer đã poll trở lại nhưng member assignment vẫn thiếu.
- Lag tiếp tục tăng dù có success event.
- Nhiều service đồng loạt gặp auth failures sau rotation/ACL deployment.
- Recovery event count tăng đột biến, gợi ý broker/security subsystem không ổn định.

Với high availability, có thể dùng alert theo tỷ lệ consumer đang affected thay vì một lỗi đơn lẻ. Khi một broker/security provider outage diện rộng, gom alert theo cluster/incident để không bão hòa kênh on-call.

## 22. Runbook: Retry auth kéo dài không có success event

1. Xác định application, listener ID, group ID, instance và thời gian retry đầu tiên.
2. Tìm exception gốc: authentication, authorization hay loại lỗi khác.
3. Kiểm tra `authExceptionRetryInterval` đã cấu hình đúng trên container factory được listener dùng hay chưa.
4. Kiểm tra credential/token/certificate được client sử dụng thực tế.
5. Xem Kafka ACL cho topic và group; đối chiếu principal mapping.
6. Kiểm tra broker logs, identity provider và network connectivity.
7. Xác định secret hoặc ACL đã được sửa nhưng client có reload/reconnect đúng không.
8. Theo dõi retry events, stop events và trạng thái container.
9. Sau khi phục hồi, xác nhận poll success, assignment, record consumption và lag.
10. Nếu lỗi không thay đổi, stop/restart có kiểm soát sau khi sửa config; không retry nóng vô hạn.

Không lấy số lần retry thành công của consumer khác trong group làm bằng chứng instance đang lỗi đã khỏi.

## 23. Runbook: Success event xuất hiện nhưng consumer không xử lý record

1. Xác nhận event thuộc consumer/container nào, tránh nhầm instance khác.
2. Kiểm tra topic subscription, group ID, assignment và số partition.
3. Xem `poll()` có trả về record hay chỉ là lần poll rỗng.
4. Kiểm tra container có pause, đang rebalance hoặc đợi state restore không.
5. So sánh committed offset với end offset để xác định có backlog không.
6. Kiểm tra listener exceptions, retry/DLT và downstream latency.
7. Kiểm tra producer/DLT quyền truy cập nếu pipeline cần publish đầu ra.
8. Không reset offset hoặc seek tới đầu/cuối chỉ vì success event không dẫn đến processing ngay.

Một consumer poll thành công khi topic không có dữ liệu có thể là trạng thái bình thường.

## 24. Runbook: Auth phục hồi nhưng lỗi lại xuất hiện nhiều lần

1. Dựng timeline `ConsumerRetryAuthEvent` và `ConsumerRetryAuthSuccessfulEvent` theo instance.
2. Xác định recovery duration và khoảng thời gian ổn định giữa hai outage.
3. Kiểm tra token refresh/expiry và credential rotation schedule.
4. Kiểm tra broker hoặc security provider có intermittent outage không.
5. Kiểm tra ACL/config drift giữa brokers hoặc clusters nếu có dấu hiệu phân bố lỗi.
6. Xem DNS/TLS/SASL client logs theo đúng mức logging an toàn.
7. Điều chỉnh retry interval/backoff theo SLA, tránh tạo auth request storm.
8. Thiết lập stability window trước khi đóng incident.
9. Sau sửa, kiểm tra group stability, lag và processing throughput.

Đừng tăng `authExceptionRetryInterval` vô hạn; nó chỉ kéo dài khoảng chờ mà không xử lý nguyên nhân.

## 25. Runbook: Event hồi phục xuất hiện trong lúc rolling deployment

1. Xác định pod đang khởi động hay pod sắp bị shutdown.
2. Kiểm tra consumer retry xảy ra trước hay sau thay đổi credentials/ACL.
3. Xem instance có còn `isRunning()` và đang giữ assignment hay không.
4. Xác nhận success event có liên quan một container sắp dừng để tránh đánh dấu pod ready sai.
5. Kiểm tra không có restart controller kích hoạt ngược trong shutdown.
6. So sánh member count và lag trước/sau rollout.
7. Nếu có transaction, kiểm tra producer identity và commit/abort độc lập.
8. Đóng incident khi workload processing thực sự ổn định, không chỉ khi có một success event.

## 26. Runbook: Có auth retry success nhưng DLT publish vẫn thất bại

1. Xác định consumer poll đã hồi phục; lấy source topic/partition/offset của record lỗi.
2. Kiểm tra exception khi `DeadLetterPublishingRecoverer` publish DLT.
3. Xác nhận producer có quyền `WRITE` trên DLT và các ACL transaction cần thiết nếu dùng transaction.
4. Kiểm tra serializer, partition count/topic đích và broker availability.
5. Bảo đảm recoverer không coi việc publish DLT thất bại là success rồi commit offset nguồn.
6. Khôi phục quyền producer, sau đó retry/recovery theo policy.
7. Đối chiếu DLT message, offset nguồn và audit/replay log.

Consumer authentication success không tương đương producer authorization success.

## 27. Bảng kiểm soát ConsumerRetryAuthSuccessfulEvent

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Retry enabled | Listener container có `authExceptionRetryInterval` hợp lệ không? | Container factory config và runtime logs. |
| Event semantics | Success event có đến sau một lần poll retry auth thành công không? | Retry/recovered timeline. |
| Observer wiring | `@EventListener` có nhận đúng event không? | Spring context và structured logs. |
| Consumer identity | Có xác định được child consumer/instance phục hồi không? | Listener/container ID, group và instance. |
| Root cause | Trước đó lỗi authentication hay authorization? | `ConsumerRetryAuthEvent` và exception/broker logs. |
| Poll budget | Retry interval có phù hợp `max.poll.interval.ms` và group lifecycle? | Effective properties, poll/rebalance metrics. |
| Group health | Consumer đã có assignment và đủ member không? | Group membership và assignment. |
| Business progress | Record đã được xử lý và offset tiến chưa? | Listener metrics, committed offset, lag. |
| Producer/DLT | Quyền producer, DLT, transaction có độc lập được kiểm tra không? | Send result, recovery và transaction metrics. |
| Restart policy | Retry auth có dẫn đến restart loop hoặc double-controller không? | Stop/start events và orchestration state. |
| Security | Log có tránh lộ credential/token/payload không? | Logging policy và access review. |
| Incident closure | Có stability window thay vì đóng ngay khi thấy event không? | Alert lifecycle, processing rate và recovery duration. |

**Kết luận:** `ConsumerRetryAuthSuccessfulEvent` đánh dấu một lần **Kafka consumer poll thành công sau giai đoạn retry authentication hoặc authorization** do Spring Kafka container quản lý. Đây là tín hiệu quan sát quan trọng để biết một lỗi bảo mật tạm thời đã được vượt qua ở tầng đọc Kafka. Để vận hành đáng tin cậy, cần cấu hình `authExceptionRetryInterval` đúng, lắng nghe cả retry và success events, phân biệt consumer-level recovery với business-level success, đo tình trạng group/lag/offset sau phục hồi và kiểm soát restart/credential policy. Không coi event là bằng chứng mọi record, transaction hoặc tác động bên ngoài Kafka đã hoàn tất.
