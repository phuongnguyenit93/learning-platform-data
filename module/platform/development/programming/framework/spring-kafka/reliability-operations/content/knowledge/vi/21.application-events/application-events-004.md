# ConsumerRetryAuthEvent

## 1. ConsumerRetryAuthEvent là gì?

**ConsumerRetryAuthEvent** là một **Spring Kafka application event** được phát khi Kafka consumer gặp lỗi authentication hoặc authorization và listener container đang **thử lại** theo cấu hình thay vì dừng ngay.

Event này thuộc tầng vận hành consumer, không phải event nghiệp vụ nằm trong Kafka topic. Nó không chứa một OrderCreated hay PaymentProcessed, cũng không trực tiếp thực hiện retry, cập nhật ACL hoặc đổi credential. Đây là tín hiệu giúp ứng dụng quan sát một đường retry đã được container quyết định.

Ví dụ: Order Fulfillment đọc topic orders.created. Một thay đổi ACL khiến principal của consumer tạm thời mất quyền đọc topic. Khi container được cấu hình retry auth, nó có thể phát ConsumerRetryAuthEvent, chờ khoảng thời gian đã cấu hình, rồi thử poll lại. Sau khi ACL được khôi phục và một lần retry thành công, container có thể phát **ConsumerRetryAuthSuccessfulEvent**.

~~~text
Spring Kafka listener container
          |
          v
     KafkaConsumer.poll()
          |
     +----+--------------------+
     |                         |
  Thành công            Auth/authz exception
     |                         |
     v                         v
  Listener              Retry enabled?
     |                    /          \
     v                   No          Yes
  Xử lý record           |            |
                         v            v
                      Container  ConsumerRetryAuthEvent
                      có thể     reason=AUTHENTICATION
                      dừng       hoặc AUTHORIZATION
                                      |
                                      v
                                Đợi retry interval
                                      |
                                      v
                                KafkaConsumer.poll()
                                      |
                               +------+------+
                               |             |
                             Vẫn lỗi     Thành công
                               |             |
                               v             v
                           Retry tiếp    ConsumerRetryAuth
                                        SuccessfulEvent
~~~

**Điểm then chốt:** event phản ánh **đang retry sau lỗi bảo mật**, không chứng minh lỗi đã được sửa hoặc record đã được xử lý.

## 2. Vị trí của event trong hệ thống Spring Kafka

Spring Kafka phát nhiều application events cho lifecycle của listener container:

| Event | Ý nghĩa chính |
|---|---|
| ConsumerStartingEvent | Consumer bắt đầu khởi động |
| ConsumerStartedEvent | Consumer đã start theo lifecycle tương ứng |
| ConsumerPartitionAssignedEvent | Consumer nhận partition |
| ConsumerPartitionRevokedEvent | Partition bị thu hồi |
| ConsumerPartitionLostEvent | Consumer mất ownership của partition |
| **ConsumerRetryAuthEvent** | Authentication/authorization thất bại và đang retry |
| **ConsumerRetryAuthSuccessfulEvent** | Retry auth đã thành công sau một retry auth trước đó |
| ConsumerStoppedEvent | Consumer đã stop; có thể kèm reason |
| ContainerStoppedEvent | Container đã dừng |
| NonResponsiveConsumerEvent | Container phát hiện consumer có dấu hiệu poll không phản hồi |

ConsumerRetryAuthEvent không thay thế ConsumerStoppedEvent. Một event biểu thị **đường retry đang hoạt động**, event kia biểu thị **consumer đã dừng**.

### 2.1. Không phải mọi auth error đều tạo retry event

Nếu authExceptionRetryInterval không được cấu hình, đường retry auth của container bị tắt. Khi KafkaConsumer ném AuthenticationException hoặc AuthorizationException, container có thể stop thay vì phát ConsumerRetryAuthEvent.

Do đó, thiếu ConsumerRetryAuthEvent không có nghĩa chắc chắn không xảy ra auth error. Phải kiểm tra cả cấu hình interval, logs và ConsumerStoppedEvent.

## 3. Authentication khác authorization thế nào?

**Authentication** xác minh danh tính:

- Sai username hoặc password SASL/SCRAM.
- SASL mechanism không phù hợp broker.
- Certificate TLS client không hợp lệ hoặc hết hạn.
- Cấu hình Kerberos/JAAS không phù hợp.
- Principal mapping hoặc identity configuration sai.

**Authorization** xác minh quyền của danh tính đã được broker nhận diện:

- Thiếu READ trên topic orders.created.
- Thiếu READ trên consumer group order-fulfillment.
- ACL DENY hoặc host restriction chặn request.
- Topic hoặc group ID khác với resource đã được cấp quyền.

| Nội dung | Authentication | Authorization |
|---|---|---|
| Câu hỏi | Client là ai? | Principal có quyền gì? |
| Lỗi Kafka điển hình | AuthenticationException, SaslAuthenticationException | AuthorizationException, TopicAuthorizationException, GroupAuthorizationException |
| Event reason | AUTHENTICATION | AUTHORIZATION |
| Cách khắc phục | Credential, TLS/SASL, principal mapping | ACL, resource name, operation, principal |
| Retry tự sửa được không? | Không nếu credential vẫn sai | Không nếu ACL vẫn thiếu |

Đổi password không cấp quyền READ. Cấp quyền READ không làm sai password trở thành hợp lệ. Phân biệt reason giúp đội vận hành sửa đúng lớp lỗi.

## 4. API của ConsumerRetryAuthEvent

Class nằm trong package:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthEvent
~~~

Ở các phiên bản Spring Kafka 3.x và 4.x phù hợp, event kế thừa KafkaEvent và cung cấp:

| Thành phần | API | Ý nghĩa |
|---|---|---|
| Reason | event.getReason() | Lý do retry: AUTHENTICATION hoặc AUTHORIZATION |
| Source | event.getSource() | Listener container phát event |
| Container | event.getContainer() | Container liên quan; có thể là parent nếu source là child |
| Timestamp | event.getTimestamp() | Thời điểm event được tạo |

Nested enum:

~~~java
ConsumerRetryAuthEvent.Reason.AUTHENTICATION
ConsumerRetryAuthEvent.Reason.AUTHORIZATION
~~~

Một observer đơn giản:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerRetryAuthEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaAuthRetryObserver {

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        log.warn(
            "Consumer auth retry: reason={}, source={}, container={}",
            event.getReason(),
            event.getSource(),
            event.getContainer()
        );
    }
}
~~~

Event cung cấp reason, nhưng không phải một bản chụp đầy đủ về principal, resource, operation và stack trace. Khi muốn biết ACL nào thiếu, cần xem broker/client logs.

### 4.1. Không gọi consumer từ callback một cách tùy ý

KafkaConsumer không thread-safe. Spring event multicaster mặc định thường chạy listener trên thread phát event, nhưng ứng dụng có thể đổi sang async executor. Không giữ consumer reference hoặc gọi poll/commit/seek từ một event observer chạy trên thread khác.

Observer tốt nhất nên gọn: log, metric, cập nhật trạng thái monitoring thread-safe.

## 5. ConsumerRetryAuthSuccessfulEvent

Class liên quan:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthSuccessfulEvent
~~~

Event này được phát khi một lần thử lại authentication/authorization **thành công sau khi đã có ConsumerRetryAuthEvent trước đó**. Nó giúp đánh dấu một đoạn outage do auth/authz đã kết thúc ở tầng retry của consumer.

~~~text
10:00 ConsumerRetryAuthEvent(AUTHORIZATION)
10:30 ConsumerRetryAuthEvent(AUTHORIZATION)
11:00 ACL được cập nhật
11:01 Lần retry auth tiếp theo thành công
11:01 ConsumerRetryAuthSuccessfulEvent
11:02 Consumer tiếp tục poll/nhận assignment tùy trạng thái group
~~~

Timeline chỉ mang tính minh họa. Không giả định cứ mỗi đúng 30 giây đều có một event và không dùng số event làm số request auth chính xác.

### 5.1. Ví dụ bắt cả hai event

~~~java
@Component
public class KafkaAuthEvents {

    @EventListener
    public void retrying(ConsumerRetryAuthEvent event) {
        log.warn(
            "Kafka consumer retrying auth, reason={}",
            event.getReason()
        );
    }

    @EventListener
    public void recovered(ConsumerRetryAuthSuccessfulEvent event) {
        log.info(
            "Kafka consumer auth retry succeeded, source={}",
            event.getSource()
        );
    }
}
~~~

**ConsumerRetryAuthSuccessfulEvent không đảm bảo consumer lag đã giảm hoặc record đã được commit.** Nó chỉ báo lỗi auth/authz trong đường retry đã được vượt qua.

Nếu group còn rebalance, listener đang pause hoặc downstream DB gặp lỗi, dữ liệu vẫn có thể chưa được xử lý.

## 6. Cấu hình authExceptionRetryInterval

Spring Kafka hỗ trợ **authExceptionRetryInterval** trên container properties. Property này quy định khoảng chờ giữa các lần retry khi KafkaConsumer ném AuthenticationException hoặc AuthorizationException.

Ví dụ:

~~~java
factory.getContainerProperties()
    .setAuthExceptionRetryInterval(Duration.ofSeconds(30));
~~~

Đối với các phiên bản API hỗ trợ tính năng này, nếu property để null thì retry auth của container bị tắt và container có thể dừng khi nhận exception tương ứng.

### 6.1. Ràng buộc với max.poll.interval.ms

Khoảng auth retry **phải nhỏ hơn max.poll.interval.ms**.

~~~text
Kafka consumer:
  max.poll.interval.ms           = 300000 ms
  authExceptionRetryInterval     = 30000 ms
~~~

Giá trị 30 giây nhỏ hơn 5 phút. Tuy nhiên, ứng dụng còn phải xem thời gian xử lý record, batch, GC pause và downstream latency; không nên cấu hình interval sát giới hạn poll.

### 6.2. Khoảng chờ không sửa quyền

Retry interval giúp consumer **có cơ hội** phục hồi khi ACL, credential hoặc broker condition được sửa từ bên ngoài. Nó không tự tạo ACL hoặc tự cập nhật password đã bị hardcode.

Nếu một ứng dụng dùng secret chỉ được nạp lúc JVM start, retry trong cùng process có thể tiếp tục sử dụng secret cũ. Khi đó cần thiết kế refresh configuration hoặc restart process có kiểm soát.

## 7. Cấu hình ConcurrentKafkaListenerContainerFactory

Ví dụ tạo factory riêng để áp dụng auth retry:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            authRetryKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
            .setAuthExceptionRetryInterval(Duration.ofSeconds(30));

        return factory;
    }
}
~~~

Gắn factory vào endpoint:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "authRetryKafkaListenerContainerFactory"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Ví dụ giả định ConsumerFactory, deserializer và security đã được cấu hình tương thích.

**Lưu ý nhiều factory:** cấu hình interval trên một factory không tự động áp dụng cho các listener dùng factory khác. Khi debug, phải xác nhận @KafkaListener đang dùng factory nào.

### 7.1. Spring Boot auto-configuration

Tên property YAML ánh xạ trực tiếp tới authExceptionRetryInterval có thể khác hoặc chưa có ở một dòng Spring Boot cụ thể. Dùng setter Java như ví dụ giúp tránh phỏng đoán property name.

Nếu muốn đặt qua configuration properties, cần kiểm tra metadata/version Spring Boot đang triển khai hoặc dùng factory customizer chính thức mà version đó hỗ trợ.

## 8. Ví dụ SASL/SCRAM consumer

Một cấu hình kết nối an toàn:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-a.example.net:9093
      - kafka-b.example.net:9093

    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="<injected-secret>";'

    listener:
      ack-mode: batch
~~~

Chuỗi password chỉ là placeholder. Trong production, nhận secret từ secret manager hoặc cơ chế injection do nền tảng triển khai quản lý. Không commit password, private key hoặc token vào source control.

Đặt SASL_SSL giúp tạo kết nối có TLS và SASL, nhưng không tự cấp ACL.

### 8.1. Quyền tối thiểu cho consumer

Ví dụ principal:

~~~text
Principal: User:orders-reader

Topic orders.created:
    operation READ

Group order-fulfillment:
    operation READ
~~~

Cần xác nhận resource/principal thực tế từ broker logs. Nếu listener subscribe thêm topic hoặc dùng group ID khác do annotation override, ACL phải khớp chính xác.

## 9. AUTHENTICATION event: ví dụ password rotation

Giả sử Kafka cluster đổi password SCRAM cho principal orders-reader nhưng pod cũ vẫn dùng password trước đó.

~~~text
Consumer starts
      |
      v
SASL handshake rejected
      |
      v
AuthenticationException
      |
      v
ConsumerRetryAuthEvent(AUTHENTICATION)
      |
      v
Wait retry interval
      |
      v
Retry with current client credentials
~~~

Cần kiểm tra:

1. Secret mới đã được phát hành đúng chưa?
2. Pod/app đã nhận secret mới chưa?
3. JAAS config của ConsumerFactory đang dùng credential nào?
4. Kafka client có khả năng reload credentials mà không restart không?
5. Có cần recreate KafkaConsumer hoặc restart pod không?
6. Broker log có xác nhận principal và lỗi thực tế không?

Nếu password vẫn sai, retry có thể tiếp tục thất bại. Chỉ tăng retry count hoặc giảm interval không giải quyết root cause.

### 9.1. Phân biệt với lỗi network

Lỗi kết nối TLS, DNS hoặc broker disconnect có thể đi qua exception path khác tùy Kafka client version. Không có ConsumerRetryAuthEvent không đồng nghĩa kết nối/bảo mật đang khỏe.

Phải đọc exception gốc và đối chiếu broker logs.

## 10. AUTHORIZATION event: ví dụ thiếu group ACL

Consumer đăng nhập SASL thành công với principal User:orders-reader, nhưng broker từ chối tham gia group order-fulfillment.

~~~text
SASL auth: SUCCESS
       |
       v
Group operation
       |
       v
Broker ACL check: DENIED
       |
       v
GroupAuthorizationException
       |
       v
ConsumerRetryAuthEvent(AUTHORIZATION)
       |
       v
Admin fixes READ permission on group
       |
       v
Consumer retry succeeds
       |
       v
ConsumerRetryAuthSuccessfulEvent
~~~

Các bước vận hành:

- Xác định principal mà broker nhìn thấy.
- Xác nhận group ID thực tế của listener.
- Kiểm tra READ trên group.
- Kiểm tra READ trên tất cả topic mà consumer đọc.
- Kiểm tra DENY rule, host restriction và ACL resource pattern.
- Cấp đúng quyền tối thiểu theo quy trình quản trị.
- Quan sát retry successful event và consumer group assignment.

Không cấp superuser cho runtime service để tránh authz error.

## 11. Event reason và exception gốc

ConsumerRetryAuthEvent.getReason() chỉ phân loại **AUTHENTICATION** hoặc **AUTHORIZATION**. Nó không phải API trả về nguyên Kafka exception với mọi nested cause.

Để debug cần kết hợp:

| Nguồn thông tin | Thông tin có ích |
|---|---|
| ConsumerRetryAuthEvent | Loại auth/authz error và container source |
| Kafka consumer logs | AuthenticationException, AuthorizationException và các cause |
| Broker security logs | Principal, operation, resource, host |
| Spring Kafka container logs | Poll retry, container lifecycle, stop |
| Deployment/config history | Secret rotation, ACL change, rollout |
| Consumer group metrics | Lag, assignment, rebalance, commit |

Không suy ra topic thiếu ACL chỉ từ reason AUTHORIZATION, vì lỗi có thể ở **Group**, **Topic** hoặc resource khác liên quan request.

### 11.1. Quan sát principal thật

Với SASL/SCRAM, broker thường nhận principal dựa trên username. Với mTLS, principal có thể dựa trên certificate subject và mapping rules.

ACL phải khớp **principal ở broker**, không nhất thiết là tên bean, Spring application name hay service account theo cách gọi nội bộ.

## 12. Khi không cấu hình retry interval

Nếu authExceptionRetryInterval để null, Spring Kafka container có thể dừng khi gặp lỗi auth/authz:

~~~text
KafkaConsumer.poll()
        |
        v
AuthenticationException / AuthorizationException
        |
        v
authExceptionRetryInterval = null
        |
        v
Container stops
        |
        v
ConsumerStoppedEvent(reason=AUTH)
~~~

Ở các phiên bản Spring Kafka hỗ trợ, **ConsumerStoppedEvent** có reason **AUTH** khi consumer stop do authentication/authorization exception và không cấu hình retry interval.

Một chính sách fail-fast có thể hữu ích nếu security team muốn lỗi quyền được phát hiện ngay và yêu cầu operator xử lý.

### 12.1. Auth retry và restart là hai lựa chọn khác nhau

| Tình huống | Hướng hợp lý |
|---|---|
| ACL dự kiến được khôi phục nhanh | Có thể retry với authExceptionRetryInterval |
| Credential sai cố định | Sửa secret; retry không đủ |
| Consumer đã stop do AUTH | Sửa nguyên nhân rồi restart có kiểm soát |
| Secret nằm trong env và chỉ nạp lúc JVM start | Có thể cần restart process/pod |
| Broker tạm mất kết nối nhưng client đang reconnect | Không nhất thiết restart container |
| Runtime policy yêu cầu fail-fast | Không bật retry kéo dài ngoài ý muốn |

Không tự restart vô hạn vì cùng một lỗi có thể tiếp tục xảy ra và tạo consumer group rebalance liên tục.

## 13. ConsumerRetryAuthEvent khác ConsumerStoppedEvent

| Thuộc tính | ConsumerRetryAuthEvent | ConsumerStoppedEvent |
|---|---|---|
| Khi phát | Lỗi auth/authz và retry được thực hiện | Consumer đã dừng |
| Trạng thái | Container đang cố phục hồi | Consumer không còn chạy |
| Reason | AUTHENTICATION, AUTHORIZATION | NORMAL, AUTH, FENCED, ERROR và các giá trị theo version |
| Mục đích | Log, metric, cảnh báo, quan sát hồi phục | Phân loại stop và quản lý lifecycle |
| Có chứng minh record đang được xử lý? | Không | Không |
| Có nên gọi start ngay trong handler? | Không | Không nếu chưa đảm bảo stop-complete và chính sách restart |

Nếu không thấy retry event nhưng có ConsumerStoppedEvent với reason AUTH, kiểm tra cấu hình retry interval trước.

## 14. Concurrency và các child containers

Với @KafkaListener concurrency=3:

~~~text
Parent ConcurrentMessageListenerContainer
      |
      +-- child #0 -> KafkaConsumer #0
      +-- child #1 -> KafkaConsumer #1
      +-- child #2 -> KafkaConsumer #2
~~~

Một child có thể phát ConsumerRetryAuthEvent, trong khi child khác chưa gặp cùng lỗi hoặc vẫn đang poll.

Spring Kafka event có:

- **getSource()**: container phát event.
- **getContainer()**: container liên quan, có thể là parent trong mô hình child.

Không dùng một boolean toàn ứng dụng như authFailed=true để diễn tả mọi consumer nếu ứng dụng có nhiều listeners hoặc concurrency lớn.

Một state map theo consumer/container identity tốt hơn, có kết hợp listener ID và group ID khi có thông tin phù hợp.

### 14.1. Event không phải một record Kafka

ConsumerRetryAuthEvent được phát qua Spring application event infrastructure. Nó không xuất hiện trong một Kafka topic trừ khi ứng dụng chủ động xây một pipeline audit riêng để publish telemetry.

Không tạo KafkaTemplate.send từ observer cho mỗi retry event mà không cân nhắc chính lỗi auth/broker hiện tại có thể khiến việc publish telemetry thất bại và gây nhiễu.

## 15. Thread safety và ApplicationEventMulticaster

Spring application event listener thường chạy đồng bộ trên thread phát event nếu không cấu hình async multicaster. Khi đổi sang async executor, event callbacks có thể chạy trên thread khác.

**KafkaConsumer không thread-safe.** Vì vậy không nên:

- Gọi poll, seek, commit hoặc subscribe từ @EventListener chạy async.
- Giữ reference KafkaConsumer để dùng sau.
- Thực hiện I/O blocking lâu trong observer.
- Gọi restart listener container ngay khi nhận retry event.
- Thay đổi ACL hoặc credential từ consumer event thread.
- Cho exception của metrics/backend làm poll thread dừng.

Observer nên ghi log ngắn hoặc cập nhật metric/cấu trúc dữ liệu thread-safe.

### 15.1. Ví dụ metric qua Micrometer

~~~java
@Component
public class AuthRetryMetrics {

    private final MeterRegistry meterRegistry;

    public AuthRetryMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        meterRegistry.counter(
            "kafka.consumer.auth.retry.events",
            "reason",
            event.getReason().name()
        ).increment();
    }

    @EventListener
    public void onSuccess(ConsumerRetryAuthSuccessfulEvent event) {
        meterRegistry.counter(
            "kafka.consumer.auth.retry.success.events"
        ).increment();
    }
}
~~~

Đoạn code giả định Micrometer dependency đã tồn tại. Metric này đếm **sự kiện** framework phát, không bảo đảm bằng đúng số lần broker thực hiện authentication handshake.

Không đưa password, token, principal nhạy cảm hoặc ID động vào metric labels.

## 16. Trạng thái theo vòng đời auth retry

Có thể xây một monitoring state machine, không phải state machine chính thức của Spring Kafka:

~~~text
HEALTHY
   |
   | ConsumerRetryAuthEvent
   v
AUTH_RETRYING
   |
   +-- Retry event tiếp -> AUTH_RETRYING
   |
   +-- ConsumerRetryAuthSuccessfulEvent
   |            |
   |            v
   |       AUTH_RECOVERED
   |            |
   |            v
   |       Poll/assignment/
   |       processing OK
   |            |
   |            v
   |         HEALTHY
   |
   +-- ConsumerStoppedEvent
                |
                v
              STOPPED
~~~

Nên lưu theo mỗi consumer hoặc listener container:

- First auth retry timestamp.
- Last auth retry timestamp.
- Last reason.
- Successful retry timestamp.
- Container stopped state.
- Last assignment và poll/processing progress.
- Consumer lag.

Nếu event multicaster chạy async, callback có thể được xử lý khác thứ tự phát. Không dùng thứ tự sự kiện telemetry như một cơ chế correctness nghiệp vụ.

## 17. Alert theo thời gian lỗi tồn tại

Không nên mở một incident mới mỗi khi có ConsumerRetryAuthEvent; một outage kéo dài có thể sinh nhiều events.

Cảnh báo có thể dựa trên:

- Auth retry kéo dài hơn ngưỡng SLO.
- Consumer lag tăng khi retry.
- Nhiều consumer trong cùng group gặp AUTHENTICATION sau secret rotation.
- AUTHORIZATION xảy ra ngay sau ACL deployment.
- Container stop với reason AUTH.
- Không có ConsumerRetryAuthSuccessfulEvent trong thời hạn mong đợi.
- Không có record processing dù topic có backlog.

Ví dụ structured logs:

~~~text
event=consumer_retry_auth
service=order-fulfillment
listener=orders-consumer
groupId=order-fulfillment
reason=AUTHORIZATION
action=retrying
~~~

Sau khi phục hồi:

~~~text
event=consumer_retry_auth_successful
service=order-fulfillment
listener=orders-consumer
groupId=order-fulfillment
action=auth_recovered
~~~

Cần nhớ success event chưa chứng minh data pipeline khỏe hoàn toàn. Chỉ đóng incident khi processing, assignment và lag đã trở lại tiêu chí mong muốn.

## 18. Tác động tới consumer lag và offset

Trong thời gian authentication/authorization thất bại, consumer có thể không lấy được record mới. Producer tiếp tục ghi topic, nên backlog có thể tăng.

~~~text
P0 committed offset: 150
P0 log end offset:   250

Consumer encounters auth error
      |
      v
ConsumerRetryAuthEvent
      |
      v
Cannot make progress
      |
      v
More records arrive
      |
      v
Lag increases
      |
      v
Auth retry succeeds
      |
      v
Consumer resumes from appropriate offset
~~~

**Event không commit offset.** Commit vẫn do consumer/container và AckMode hoặc Kafka transaction quản lý.

Nếu một record đã tạo DB side effect nhưng offset chưa commit trước khi consumer mất group membership hoặc dừng, record đó có thể được giao lại khi phục hồi. Do vậy, business side effect cần idempotency.

### 18.1. Rebalance có thể xảy ra

Nếu consumer không poll hoặc không duy trì membership đúng yêu cầu Kafka, group có thể rebalance và partition assignment thay đổi. Tuy nhiên, không phải mọi ConsumerRetryAuthEvent đều chắc chắn dẫn đến rebalance.

Theo dõi song song:

- ConsumerPartitionAssignedEvent.
- ConsumerPartitionRevokedEvent.
- ConsumerPartitionLostEvent.
- Group rebalance count.
- max.poll.interval.ms.
- Poll latency, commit failures và lag.

## 19. Phân biệt auth retry với retry record

Có hai lớp retry rất khác nhau.

**Auth retry:** KafkaConsumer gặp AuthenticationException/AuthorizationException. Listener có thể chưa nhận record; container thử poll sau khoảng chờ.

**Record retry:** KafkaConsumer đã nhận record và @KafkaListener gặp business exception. DefaultErrorHandler có thể retry hoặc recover sang DLT.

~~~text
KafkaConsumer.poll()
         |
      AUTH error
         |
         v
ConsumerRetryAuthEvent
         |
         v
Auth retry at container

KafkaConsumer.poll() succeeds
         |
         v
@KafkaListener
         |
     Business exception
         |
         v
DefaultErrorHandler
         |
    +----+------+
    |           |
  Retry        DLT
~~~

Không dùng authExceptionRetryInterval để giải quyết malformed JSON hoặc DB timeout trong listener. Cũng không chuyển một record sang DLT chỉ vì consumer thiếu quyền READ, bởi chưa chắc listener đã nhận được record đó.

## 20. Restart container hay đợi retry?

Khi container **đang retry**, stop/start nó mỗi lần nhận event thường gây hại:

- Thêm SASL/TLS handshakes.
- Gây thêm rebalance.
- Có thể làm child containers khỏe mạnh bị gián đoạn.
- Không thay đổi ACL hoặc password vẫn sai.
- Khó đối chiếu timestamp của outage.

Restart có thể cần khi:

1. Container đã dừng hẳn.
2. Credential mới chỉ được nạp khi tạo KafkaConsumer hoặc khởi động JVM.
3. ConsumerFactory/configuration đã được sửa nhưng consumer hiện tại chưa nhận.
4. Operator xác nhận root cause được khắc phục và muốn tái khởi tạo lifecycle.

Khi restart, dùng KafkaListenerEndpointRegistry hoặc managed container reference, đợi stop hoàn tất trước start và tránh thực hiện thao tác trực tiếp trong ConsumerRetryAuthEvent observer.

### 20.1. Restart riêng listener không luôn reload secret

Nếu secret được nạp qua environment variable tại JVM startup, việc stop/start Kafka listener container trong cùng JVM không tự cập nhật biến môi trường. Có thể phải restart pod hoặc dùng cơ chế dynamic refresh đã được thiết kế.

Trái lại, khi ACL broker được sửa cho đúng principal hiện tại, consumer có thể tự phục hồi ở lần retry sau mà không cần restart process.

## 21. Security và least privilege

Một event AUTHORIZATION không nên kích hoạt logic tự cấp ACL bằng tài khoản superuser. Việc cấp quyền runtime dựa trên một event tùy ý tạo nguy cơ privilege escalation.

Quy trình an toàn:

- Xác định principal đã được xác thực.
- Xác định resource type, resource name và operation bị từ chối.
- Đối chiếu ACL ALLOW/DENY, host và pattern.
- Chỉ cấp quyền cần thiết cho service.
- Ghi nhận người phê duyệt và thay đổi security.
- Quan sát retry successful event.
- Xác nhận topic/group hoạt động lại.

Không log toàn bộ JAAS config, password, token hoặc TLS private key. Log lỗi bảo mật cũng phải tuân thủ phân quyền và retention phù hợp.

## 22. Integration test cho Authorization retry

Một integration test hữu ích nên dùng Kafka broker có authorizer và ACL thật, không chỉ mock listener method.

Kịch bản:

1. Tạo topic orders.created và group order-fulfillment.
2. Tạo principal consumer có credential hợp lệ.
3. Tạm không cấp READ trên topic hoặc group.
4. Cấu hình authExceptionRetryInterval phù hợp.
5. Khởi động @KafkaListener và thu thập ConsumerRetryAuthEvent.
6. Xác nhận reason AUTHORIZATION.
7. Cấp ACL READ tối thiểu.
8. Đợi ConsumerRetryAuthSuccessfulEvent.
9. Xác nhận consumer join group và nhận partition.
10. Publish event hợp lệ, xác nhận listener xử lý.
11. Xác nhận offset tiến và lag phục hồi.
12. Dọn test ACL và topic theo quy trình test.

Dùng await với timeout thay vì sleep cố định, vì thời gian broker ACL propagation và rebalance có thể khác nhau.

### 22.1. Test collector cho application events

~~~java
@Component
public class TestAuthEventCollector {

    private final BlockingQueue<ConsumerRetryAuthEvent> retryEvents =
        new LinkedBlockingQueue<>();

    private final BlockingQueue<ConsumerRetryAuthSuccessfulEvent> successEvents =
        new LinkedBlockingQueue<>();

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        retryEvents.offer(event);
    }

    @EventListener
    public void onSuccess(ConsumerRetryAuthSuccessfulEvent event) {
        successEvents.offer(event);
    }

    public ConsumerRetryAuthEvent awaitRetry(Duration timeout)
            throws InterruptedException {

        return retryEvents.poll(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }

    public ConsumerRetryAuthSuccessfulEvent awaitSuccess(Duration timeout)
            throws InterruptedException {

        return successEvents.poll(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }
}
~~~

Ví dụ giả định có imports cho BlockingQueue, LinkedBlockingQueue, Duration và TimeUnit. Với nhiều listener factories, nên lọc theo source/container để test không nhầm event của endpoint khác.

## 23. Integration test cho Authentication retry

Authentication retry cần môi trường SASL hoặc TLS thực tế.

Kịch bản:

1. Tạo Kafka test cluster yêu cầu SASL/SCRAM hoặc client certificate.
2. Khởi động consumer với authExceptionRetryInterval.
3. Cố tình tạo lỗi xác thực.
4. Quan sát ConsumerRetryAuthEvent reason AUTHENTICATION.
5. Cập nhật credential hoặc broker setting theo cơ chế test.
6. Nếu client hỗ trợ reload/re-authentication, quan sát successful event.
7. Nếu credential chỉ được nạp lúc process start, kiểm tra hướng restart phù hợp.
8. Xác nhận consumer sau phục hồi đọc được record và offset tiến.
9. Đảm bảo test logs không chứa secrets.

Không mặc định mọi hình thức secret rotation sẽ tự phục hồi trong cùng JVM. Cách nạp credential và Kafka client version quyết định điều đó.

### 23.1. Test fail-fast không có interval

Một test bổ sung:

- Không đặt authExceptionRetryInterval.
- Gây AuthenticationException hoặc AuthorizationException.
- Quan sát container stop theo behavior version cụ thể.
- Xác nhận ConsumerStoppedEvent reason AUTH khi version hỗ trợ.
- Sửa nguyên nhân, restart có kiểm soát và xác nhận xử lý tiếp.

Test này chứng minh đường **retry** khác với đường **container stopped**.

## 24. Runbook production

Khi nhận ConsumerRetryAuthEvent:

1. Ghi nhận thời điểm, service, listener/container source và reason.
2. Phân biệt AUTHENTICATION hay AUTHORIZATION.
3. Đọc client và broker logs để xác định root exception.
4. Với AUTHENTICATION: kiểm tra SASL mechanism, TLS certificate, password/secret version, principal.
5. Với AUTHORIZATION: kiểm tra topic/group READ, principal, resource pattern, host và deny rules.
6. Xác nhận authExceptionRetryInterval và max.poll.interval.ms.
7. Kiểm tra container còn retry hay đã dừng.
8. Không restart hàng loạt consumer chỉ vì một retry event.
9. Sửa credential hoặc ACL theo quy trình quản trị.
10. Khi cần, thực hiện reload/restart container hoặc pod có kiểm soát.
11. Quan sát ConsumerRetryAuthSuccessfulEvent sau lần retry thành công.
12. Kiểm tra consumer group assignment và rebalance.
13. Xác nhận listener xử lý record hợp lệ và commit offset.
14. Quan sát consumer lag có giảm về mức phù hợp SLO không.
15. Kiểm tra side effect idempotency nếu record chưa commit được giao lại.
16. Cập nhật incident report và alert/runbook cho đợt sau.

Nếu successful event không xuất hiện dù đã sửa ACL, xem principal thực tế, group ID, topic, trạng thái container và security configuration của client. Không chỉ tăng retry interval rồi kết luận đã sửa.

## 25. Ví dụ tổng hợp: Order Fulfillment bị thu hồi ACL

Giả sử Order Fulfillment chạy ba consumer con cùng group order-fulfillment. Topic orders.created vẫn nhận event đều đặn.

Một thay đổi security vô tình thu hồi quyền READ trên consumer group. Consumer nhận GroupAuthorizationException. Container đã cấu hình retry 30 giây nên phát ConsumerRetryAuthEvent reason AUTHORIZATION.

~~~text
09:00  Group xử lý bình thường
09:05  ACL group READ bị thu hồi
09:05  AuthorizationException
09:05  ConsumerRetryAuthEvent(AUTHORIZATION)
09:06  Monitoring phát hiện lag tăng
09:07  Admin khôi phục READ cho group
09:07+ ConsumerRetryAuthSuccessfulEvent
09:08  Group assignment và processing được xác minh
~~~

Đây là mốc minh họa; thời gian thực tế phụ thuộc interval và group lifecycle.

Đội vận hành không restart các pod ngay khi có event. Họ kiểm tra principal/resource bị deny, sửa ACL, quan sát retry thành công và đợi consumer catch up.

Nếu một record đã tạo side effect DB nhưng chưa commit offset trước khi consumer dừng hoặc rebalance, record đó có thể được giao lại. Inbox/idempotent consumer giúp tránh tạo fulfillment trùng.

Kết luận tình huống: **ACL sửa đúng mới là nguyên nhân phục hồi**, còn ConsumerRetryAuthEvent cung cấp tín hiệu giám sát quá trình lỗi và retry.

## 26. Những sai lầm thường gặp

**ConsumerRetryAuthEvent báo auth thành công.** Sai; nó báo một lỗi đang được retry. Thành công có event riêng.

**Reason AUTHORIZATION nghĩa là password sai.** Sai; authorization là quyền truy cập tài nguyên.

**Không thấy retry event nghĩa là không có auth error.** Sai; container có thể dừng khi chưa cấu hình retry interval.

**Successful event chứng minh listener đã commit record.** Sai; cần kiểm tra processing và offset riêng.

**Mỗi retry event là một incident mới.** Không nên; nhiều events có thể thuộc một outage kéo dài.

**Retry interval tự tạo ACL.** Không đúng; quyền phải được cập nhật tại broker.

**Retry interval luôn tự reload secret.** Không đúng; phụ thuộc cách client nạp credential.

**Nhận retry event là restart container ngay.** Không nên; có thể tạo rebalance storm.

**Event listener được phép gọi KafkaConsumer ở thread bất kỳ.** Sai; KafkaConsumer không thread-safe.

**Một child auth retry chứng minh cả parent stopped.** Sai; cần kiểm tra từng child/container.

**Auth retry xử lý được JSON lỗi.** Sai; lỗi deserialization cần ErrorHandlingDeserializer/error handler.

**Có success event là consumer lag bằng 0.** Sai; backlog có thể vẫn lớn.

**Log nguyên JAAS config giúp debug an toàn.** Sai; JAAS có thể chứa secret.

## 27. Checklist triển khai

- [ ] Đặt authExceptionRetryInterval khi muốn container retry AuthenticationException/AuthorizationException.
- [ ] Interval nhỏ hơn max.poll.interval.ms.
- [ ] Xác nhận @KafkaListener dùng đúng container factory.
- [ ] Lắng nghe ConsumerRetryAuthEvent.
- [ ] Lắng nghe ConsumerRetryAuthSuccessfulEvent.
- [ ] Phân biệt AUTHENTICATION và AUTHORIZATION.
- [ ] Có fallback giám sát ConsumerStoppedEvent reason AUTH.
- [ ] Observer nhẹ và an toàn thread.
- [ ] Không log password, token, JAAS secret hoặc private key.
- [ ] Có runbook khôi phục ACL và credential.
- [ ] Có cơ chế reload/restart khi secret không tự refresh.
- [ ] Theo dõi group assignment, consumer lag và offset commit.
- [ ] Tránh incident/restart storm khi retry kéo dài.
- [ ] Business side effects idempotent nếu record redeliver.
- [ ] Test auth failure, authz failure, retry success và fail-fast path.

## 28. Tài liệu tham khảo

- Spring Kafka Reference — Application Events: https://docs.spring.io/spring-kafka/reference/kafka/events.html
- Spring Kafka JavaDoc — ConsumerRetryAuthEvent: https://docs.spring.io/spring-kafka/docs/3.3.2/api/org/springframework/kafka/event/ConsumerRetryAuthEvent.html
- Spring Kafka JavaDoc — ConsumerProperties: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/ConsumerProperties.html

Tham khảo JavaDoc theo phiên bản Spring Kafka đang triển khai vì API container, lifecycle reason và tích hợp Spring Boot có thể thay đổi qua các dòng phát hành.

## 29. Ghi nhớ

**ConsumerRetryAuthEvent** là tín hiệu Spring Kafka cho biết consumer gặp lỗi **authentication** hoặc **authorization** và container **đang thử lại** theo cấu hình authExceptionRetryInterval. Reason **AUTHENTICATION** hướng tới credential/TLS/SASL; reason **AUTHORIZATION** hướng tới ACL, principal, resource và operation.

**ConsumerRetryAuthSuccessfulEvent** báo đường retry auth đã hồi phục sau lỗi trước đó. Nó không thay thế bằng chứng consumer đã có partition assignment, listener đã xử lý record hoặc offsets đã commit. Khi không cấu hình retry interval, consumer có thể stop và phát ConsumerStoppedEvent với reason AUTH.

Vận hành tin cậy cần kết hợp retry interval nhỏ hơn max.poll.interval.ms, observer nhẹ và thread-safe, least-privilege ACL, secret management, cảnh báo có ngưỡng và giám sát lag/processing. Sau khi quyền hoặc credential được khôi phục, vẫn cần xác nhận consumer group xử lý dữ liệu bình thường và bảo vệ side effects trước khả năng redelivery.
