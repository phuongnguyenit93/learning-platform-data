# AuthorizationException

Kafka dùng authentication để xác minh client là ai và authorization để quyết định principal đó được phép làm gì trên topic, consumer group, cluster hoặc transactional ID. Một consumer có thể xác thực SASL/TLS thành công nhưng vẫn không được đọc topic; một producer có thể kết nối broker nhưng bị từ chối quyền WRITE. Khi broker từ chối một thao tác do thiếu quyền, Kafka client có thể ném **AuthorizationException** hoặc một lớp con cụ thể.

Trong Spring Kafka, cần nhận biết loại lỗi này vì nó thường xảy ra ở **Kafka client/container layer**, trước khi listener method được gọi. Do đó, xử lý nó như exception nghiệp vụ của record và chỉ dựa vào DefaultErrorHandler thường không giải quyết được nguyên nhân. Spring Kafka có cơ chế riêng trên listener container qua thuộc tính **authExceptionRetryInterval** để thử lại sau authentication/authorization failures trong các phiên bản hỗ trợ.

Bài học thuộc chương **Bảo mật vận hành** của **Spring Kafka Reliability Operations**. Nội dung tập trung vào principal, ACL, phân biệt AuthenticationException với AuthorizationException, hành vi consumer container, producer failures, retry boundary, bảo vệ secrets và quy trình khôi phục production.

## 1. Authentication và authorization khác nhau

Hai câu hỏi bảo mật cần được tách riêng:

- **Authentication:** client là ai? Broker xác minh danh tính qua SASL, TLS client certificate hoặc cơ chế bảo mật được cấu hình.
- **Authorization:** principal đã xác thực có được phép thực hiện thao tác trên resource cụ thể không? Kafka kiểm tra ACL/policy tương ứng.

~~~text
orders-projection connects to Kafka
        |
        v
SASL authentication succeeds
        |
        v
Broker identifies principal: User:orders-projection
        |
        v
Consumer requests READ on topic orders.created
        |
        v
Broker checks ACL
       / \
  allowed denied
     |      |
  consume  AuthorizationException
~~~

Nếu SASL password sai, client có thể nhận authentication failure. Nếu password đúng nhưng principal không có quyền READ topic, đó là authorization failure.

| Tình huống | Loại vấn đề thường gặp |
|---|---|
| SASL username/password sai | AuthenticationException |
| SASL mechanism không được hỗ trợ | Authentication/configuration failure |
| TLS truststore không tin cậy broker certificate | TLS/SSL handshake failure |
| Client certificate không được chấp nhận | Authentication failure |
| Principal hợp lệ nhưng thiếu READ trên topic | AuthorizationException |
| Consumer có READ topic nhưng thiếu quyền READ group | Group authorization failure |
| Producer thiếu WRITE trên topic | Topic authorization failure |
| Transactional producer thiếu quyền trên transactional ID | Transactional ID authorization failure |

Lỗi TLS, SASL và authorization có thể xuất hiện ở những thời điểm khác nhau trong quá trình kết nối, metadata lookup, poll, send hoặc commit. Đọc exception subtype và broker logs để xác định đúng lớp lỗi.

## 2. AuthorizationException là gì?

Trong Kafka Java client, AuthorizationException đại diện cho thao tác bị broker từ chối do thiếu quyền. Các lớp con cụ thể có thể cho biết resource hoặc thao tác liên quan, tùy Kafka client version.

Các exception thường gặp:

- **TopicAuthorizationException:** principal không được phép thực hiện thao tác trên một hoặc nhiều topics.
- **GroupAuthorizationException:** principal không có quyền cần thiết trên consumer group.
- **ClusterAuthorizationException:** thao tác cần quyền trên cluster bị từ chối.
- **TransactionalIdAuthorizationException:** producer không có quyền trên transactional ID.
- **DelegationTokenAuthorizationException:** thao tác delegation token bị từ chối trong môi trường dùng delegation tokens.

Các lớp này thuộc Kafka client package, ví dụ org.apache.kafka.common.errors. Giữ nguyên cause chain để xác định subtype; tên class và metadata có thể khác giữa Kafka versions.

### 2.1 Một lỗi quyền không nhất thiết làm hỏng toàn cluster

Nếu consumer bị từ chối READ trên một topic, client khác với principal khác vẫn có thể hoạt động. Nếu service bị từ chối trên consumer group, producer của service đó vẫn có thể ghi topic nếu có ACL WRITE tương ứng.

Phạm vi sự cố phụ thuộc resource và principal. Không kết luận toàn cluster mất kết nối chỉ từ một authorization error.

### 2.2 Không nhầm với lỗi record

AuthorizationException thường phát sinh khi Kafka client gọi broker API như metadata, fetch, group coordination, offset commit hoặc produce. Nó không nhất thiết liên quan payload của một record cụ thể.

Poison message thường làm listener method ném exception khi xử lý record. AuthorizationException thường biểu thị client không được phép thực hiện thao tác ở tầng Kafka. Hai lỗi có recovery path khác nhau.

## 3. Consumer cần những quyền nào?

Một consumer group điển hình cần quyền trên topic và group:

- **READ trên topic** để consume records.
- **READ trên group** để join/manage consumer group và thực hiện các thao tác group cần thiết.
- Quyền metadata/describe tương ứng theo broker ACL model và thao tác ứng dụng. Trong Kafka ACL model, một số operations có thể bao hàm DESCRIBE; kiểm tra behavior của broker version.

Ví dụ:

~~~text
Principal: User:orders-projection

Topic resource:
  orders.created
  required operation: READ

Group resource:
  orders-projection-prod
  required operation: READ
~~~

Topic READ và group READ là hai resource khác nhau. Nếu chỉ cấp topic READ mà thiếu group READ, client có thể lấy metadata nhưng không join group được như mong đợi. Nếu chỉ cấp group READ mà thiếu topic READ, consumer không fetch được records.

### 3.1 Ví dụ cấp ACL

Các lệnh sau minh họa cách dùng kafka-acls.sh; thay bootstrap server, principal, topic và group bằng giá trị của môi trường. Thực hiện theo quy trình quản trị quyền của tổ chức.

~~~bash
kafka-acls.sh --bootstrap-server kafka.example.internal:9092 --add --allow-principal 'User:orders-projection' --operation Read --topic orders.created

kafka-acls.sh --bootstrap-server kafka.example.internal:9092 --add --allow-principal 'User:orders-projection' --operation Read --group orders-projection-prod
~~~

Đây là quyền tối thiểu thường cần cho consumer group. Nếu ứng dụng dùng AdminClient, topic creation, transactions hoặc thao tác khác, cần ACL tương ứng. Không cấp Cluster ALL chỉ để làm một AuthorizationException biến mất.

### 3.2 Prefix ACL và wildcard

Kafka hỗ trợ resource patterns như literal, prefixed và wildcard tùy phiên bản. Prefix ACL tiện cho nhóm topics nhưng mở rộng phạm vi quyền.

Cho phép principal đọc mọi topic có prefix orders- có thể vô tình cấp quyền trên topic mới trong tương lai. Dùng literal ACL khi có thể; chỉ dùng prefix khi naming convention và ownership rõ ràng.

## 4. Producer cần những quyền nào?

Producer thông thường cần **WRITE trên destination topic**. Một số thao tác metadata cần DESCRIBE hoặc quyền được Kafka ACL model suy ra từ WRITE.

~~~text
Principal: User:orders-publisher
Topic: orders.created
Operation: WRITE
~~~

Ví dụ:

~~~bash
kafka-acls.sh --bootstrap-server kafka.example.internal:9092 --add --allow-principal 'User:orders-publisher' --operation Write --topic orders.created
~~~

Nếu producer dùng idempotence hoặc transactions, có thể cần thêm quyền liên quan transactional ID và cluster behavior theo Kafka version/security policy. Với transactional producer, quyền trên transactional ID phải được cấp đúng resource và operation; không chỉ cấp WRITE trên output topic rồi giả định transaction sẽ hoạt động.

### 4.1 Producer authorization không được xử lý bởi listener container

Nếu KafkaTemplate.send() bị broker từ chối, exception thường xuất hiện trong send result/future hoặc khi flush/transaction commit. Thuộc tính authExceptionRetryInterval của listener container không tự retry producer sends.

Producer application cần xử lý send failure theo business contract, retry budget, idempotency và transaction policy. Không cho rằng bật authExceptionRetryInterval trên consumer factory sẽ giải quyết lỗi WRITE ACL của KafkaTemplate.

## 5. Spring Kafka xử lý auth exceptions thế nào?

KafkaConsumer có thể ném AuthenticationException hoặc AuthorizationException khi thực hiện các thao tác với broker. Những exception này thường xuất hiện bên trong consumer loop, ví dụ poll hoặc group/metadata operations, thay vì được ném từ listener method.

Trong Spring Kafka:

- Theo default behavior, khi authentication/authorization exception xảy ra, listener container sẽ dừng.
- Trong các phiên bản hỗ trợ, có thể cấu hình **authExceptionRetryInterval** để container đợi một khoảng thời gian rồi thử lại.
- Cơ chế này dành cho lỗi authentication/authorization ở Kafka consumer/container path.
- Nó không thay thế DefaultErrorHandler cho record processing exceptions.
- Nó không tự khắc phục ACL hoặc credentials sai.

Nếu quyền vừa được cấp hoặc secret vừa được sửa, retry interval có thể giúp container tiếp tục thử lại mà không cần operator restart thủ công, với điều kiện version và container setup hỗ trợ.

## 6. Cấu hình authExceptionRetryInterval

Thuộc tính được cấu hình trên ContainerProperties:

~~~java
factory.getContainerProperties()
       .setAuthExceptionRetryInterval(Duration.ofSeconds(30));
~~~

Ví dụ factory:

~~~java
@Configuration
public class OrdersConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
               .setAuthExceptionRetryInterval(Duration.ofSeconds(30));

        return factory;
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-main",
    topics = "orders.created",
    groupId = "orders-projection-prod",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

Các bean và model trong ví dụ là minh họa. ConsumerFactory vẫn cần cấu hình SASL/TLS, deserializer, bootstrap servers, group properties và ACL phù hợp.

### 6.1 Version requirement

authExceptionRetryInterval được bổ sung trong Spring Kafka **2.8**. Với version cũ hơn, setter có thể không tồn tại và default behavior có thể là container stop khi gặp auth exception.

Trước khi copy code:

1. Xác nhận Spring Kafka dependency thực tế.
2. Kiểm tra ContainerProperties API của đúng version.
3. Xác nhận Duration type và setter signature.
4. Test auth failure trên staging.
5. Không giả định property YAML cùng tên được bind trong mọi Spring Boot release.

### 6.2 Consumer cần group.id

Cơ chế retry auth exception của listener container yêu cầu consumer được cấu hình với **group.id** theo contract của Spring Kafka. Cần đảm bảo group ID thực tế được đặt đúng, dù lấy từ ConsumerFactory hay @KafkaListener.

Nếu không có group ID phù hợp, đừng giả định container có thể tiếp tục theo retry interval. Xác minh API/version documentation và effective consumer configuration.

### 6.3 Retry interval là khoảng chờ, không phải số lần retry

Duration 30 giây có nghĩa container chờ giữa những lần thử lại theo cơ chế này. Nó không có nghĩa chỉ thử lại 30 lần, cũng không tự tạo exponential backoff hoặc jitter.

Nếu broker vẫn từ chối quyền, container có thể tiếp tục gặp auth exceptions theo chu kỳ. Cần alert để operator biết sự cố vẫn tồn tại.

## 7. Auth exception khác listener record exception

~~~text
KafkaConsumer.poll()
    |
    +-- AuthorizationException
    |       -> consumer/container error path
    |       -> stop by default, or retry interval if configured
    |
    +-- ConsumerRecord received
            |
            v
        @KafkaListener
            |
            +-- Database exception
            |       -> CommonErrorHandler / DefaultErrorHandler
            |
            +-- Business validation exception
                    -> retry/recovery policy
~~~

**DefaultErrorHandler không phải nơi sửa ACL.** Nếu Kafka broker từ chối READ topic hoặc READ group trong poll/join operation, listener method có thể chưa được gọi nên RetryListener của record error handler cũng không có delivery callback tương ứng.

Tương tự, @RetryableTopic không phải giải pháp cho consumer thiếu quyền đọc main topic hoặc retry topic. Retry-topic listeners cũng cần ACL riêng.

### 7.1 Tránh retry storm cho lỗi quyền vĩnh viễn

Nếu ACL thiếu trong nhiều giờ, retry interval ngắn có thể tạo request và logs lặp. Chọn interval có ý nghĩa vận hành, theo dõi số lần retry và alert. Nếu cần dừng nhanh khi credential/policy bị thu hồi, cân nhắc default stop behavior hoặc operational policy phù hợp.

### 7.2 Khi nào dùng DefaultErrorHandler?

Dùng DefaultErrorHandler cho exception phát sinh trong quá trình xử lý record ở listener path, ví dụ database timeout, business service exception hoặc validation/recovery failure. Không dùng nó để xử lý thiếu ACL của consumer poll hoặc group coordination.

## 8. Phân biệt TopicAuthorizationException và GroupAuthorizationException

| Exception | Resource thường liên quan | Kiểm tra |
|---|---|---|
| TopicAuthorizationException | Topic | Principal có READ/WRITE/Describe phù hợp không? |
| GroupAuthorizationException | Consumer group | Principal có READ trên group không? |
| ClusterAuthorizationException | Cluster-level operation | Có ACL cho thao tác cluster/Admin không? |
| TransactionalIdAuthorizationException | Transactional ID | Principal có quyền transaction tương ứng không? |

Tên exception chỉ là điểm khởi đầu. Broker logs hoặc exception metadata có thể cho biết resource cụ thể bị từ chối.

### 8.1 TopicAuthorizationException ở consumer

Nếu consumer subscribe nhiều topics và chỉ một topic bị từ chối, exception có thể chỉ ra một hoặc nhiều topics không được phép. Đừng cấp quyền wildcard cho mọi topics ngay lập tức.

Kiểm tra topic string sau khi resolve pattern, principal sau mapping, ACL resource pattern type, operation READ, cluster đang kết nối và các retry/DLT topics mà consumer cũng cần đọc.

### 8.2 GroupAuthorizationException

Nếu consumer có thể đọc metadata topic nhưng không join group, kiểm tra group.id thực tế, ACL resource type GROUP, principal broker nhận diện và khả năng group name bị override bởi @KafkaListener.id/idIsGroup.

Đổi group ID để né lỗi ACL có thể tạo một consumer group mới với offset namespace khác, dẫn tới replay hoặc bắt đầu từ offset khác. Không làm điều đó như workaround tùy tiện.

## 9. Principal mapping: broker nhìn thấy danh tính nào?

Tên người dùng cấu hình ở client không nhất thiết là chuỗi principal cuối cùng mà broker dùng so ACL.

~~~text
Client SASL username:
  orders-projection

Broker principal:
  User:orders-projection
~~~

Với TLS certificate, broker có thể tạo principal từ subject DN và áp dụng principal builder/mapping rules. Nếu ACL được cấp cho User:orders-projection nhưng broker xác định client là User:CN=orders-worker,OU=Services, ACL có thể không match.

Để điều tra:

1. Xác định broker listener endpoint và security protocol.
2. Kiểm tra broker authentication/audit logs.
3. Xem principal sau mapping.
4. Kiểm tra resource và operation bị từ chối.
5. So sánh với ACL thực tế.
6. Xác nhận đúng cluster/environment.

Không chỉ nhìn username trong application.yml rồi kết luận broker đang dùng cùng principal.

### 9.1 Không log credentials

Không log sasl.jaas.config, SASL password, OAuth access/refresh token, private key, keystore content, truststore passwords hoặc authorization headers.

Nếu cần log security config, chỉ log mechanism, protocol và secret reference/alias đã sanitize. Đừng stringify toàn bộ Kafka properties.

## 10. SASL/TLS có thể gây lỗi nào?

Ví dụ cấu hình client dùng SASL_SSL:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-projection" password="INJECTED_SECRET";
~~~

Đây là ví dụ cấu trúc, không phải cấu hình secret production hoàn chỉnh. Password nên đến từ secret manager hoặc environment injection an toàn; không commit credential vào source control.

Các nhóm lỗi:

- Security protocol không khớp broker listener.
- SASL mechanism không được hỗ trợ.
- Username/password sai hoặc hết hạn.
- JAAS syntax không hợp lệ.
- TLS truststore không tin cậy broker certificate.
- Client certificate không hợp lệ.
- Principal mapping khác với ACL.
- Authentication thành công nhưng ACL không đủ.

Không phải tất cả các lỗi này đều là AuthorizationException. Đọc root cause và broker logs trước khi chọn remediation.

## 11. Producer AuthorizationException qua KafkaTemplate

~~~java
kafkaTemplate.send("orders.created", orderId, event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            // Phân loại và xử lý send failure.
        }
    });
~~~

Nếu broker từ chối WRITE, future có thể hoàn tất exceptional với cause là TopicAuthorizationException hoặc exception wrapper tương ứng.

authExceptionRetryInterval là cơ chế của listener container/consumer path. KafkaTemplate send failure cần xử lý ở producer application hoặc transaction boundary.

Không retry producer send vô hạn vì lỗi ACL. Nếu principal không có WRITE, mỗi retry có thể tiếp tục bị từ chối và tạo duplicate attempts/logs.

Khi send failure không rõ outcome, cần xem producer delivery semantics, idempotence, transactions và business idempotency. AuthorizationException thường là denial rõ ràng; nhưng wrappers/async completion có thể khiến root cause khó thấy. Unwrap cause chain trước khi quyết định retry.

## 12. Transactional producer và quyền transactional ID

Transactional Kafka producer sử dụng transactional.id. Broker kiểm tra quyền trên transactional ID namespace và topic operations cần thiết.

Nếu thiếu quyền, transaction begin/commit hoặc producer initialization có thể thất bại với TransactionalIdAuthorizationException hoặc lớp lỗi liên quan.

Cần xác minh:

- Transactional ID prefix được cấu hình ở ProducerFactory.
- Principal thực tế của producer.
- ACL resource type TRANSACTIONAL_ID.
- Operation cần thiết theo Kafka version.
- Quyền WRITE trên output topics.
- Quyền consumer/group tương ứng nếu listener container consume trong transaction.
- ProducerFencedException có phải lỗi khác đang bị nhầm với authorization không.

### 12.1 Authorization và fencing khác nhau

- AuthorizationException: principal không có quyền.
- ProducerFencedException: producer instance bị fencing do transaction ownership conflict hoặc một producer khác dùng cùng transactional identity.

Cấp thêm ACL không giải quyết fencing. Tăng retry không giải quyết việc nhiều producer instances dùng transactional ID không phù hợp. Hãy xác định exception cụ thể.

Không catch transaction failure rồi return bình thường để giảm logs; transaction có thể rollback và offset không commit. Để exception đi qua Spring Kafka transaction handling và điều tra producer/consumer security policy.

## 13. Retry interval và vận hành container

Giả sử consumer gặp TopicAuthorizationException lúc 10:00 và authExceptionRetryInterval là 30 giây:

~~~text
10:00:00  poll/metadata operation bị từ chối
10:00:00  container nhận auth exception
10:00:00  container chờ retry interval
10:00:30  container thử lại
10:01:00  thử lại tiếp nếu ACL vẫn thiếu
...
10:02:10  operator cấp ACL đúng
10:02:30  lần thử tiếp theo có thể thành công
10:02:30  consumer tiếp tục lifecycle nếu điều kiện khác hợp lệ
~~~

Timeline chỉ minh họa; network, broker, metadata refresh và container scheduling có thể làm thay đổi timing.

### 13.1 Khoảng retry quá ngắn

Nếu interval 100 ms nhưng ACL sai kéo dài hàng giờ, consumer có thể lặp request và logs quá dày. Điều này không tạo thêm quyền.

### 13.2 Khoảng retry quá dài

Nếu ACL vừa được sửa, interval 10 phút khiến consumer phục hồi chậm dù broker đã cho phép. Chọn interval theo thời gian phản ứng mong muốn, broker capacity và operational alerting.

### 13.3 Interval không phải exponential backoff

authExceptionRetryInterval là khoảng retry theo API. Không mặc định có jitter hoặc exponential growth. Nếu cần policy khác, xem khả năng framework version và lifecycle management; không tự tạo thread sleep trong consumer callback.

## 14. Chọn stop hay retry theo policy

| Tình huống | Hướng xử lý thường cân nhắc |
|---|---|
| ACL bị thiếu do rollout, sẽ được sửa nhanh | Retry interval có giám sát |
| Secret rotation có khoảng lệch ngắn giữa pods | Retry interval và alert |
| Principal bị thu hồi có chủ đích | Stop/fail fast để tránh tiếp tục truy cập |
| ACL sai vĩnh viễn do deployment config | Dừng và alert; sửa config/policy |
| Broker security service tạm thời chưa đồng bộ | Retry interval có giám sát |
| Producer WRITE bị từ chối | Xử lý send failure riêng; consumer interval không áp dụng |

Nếu dùng retry interval vô thời hạn, cần alert khi container liên tục gặp auth exception hoặc không có record progress. Nếu muốn fail fast, default stop behavior có thể phù hợp hơn nhưng cần orchestrator/restart policy và incident response rõ ràng.

## 15. Observability cho AuthorizationException

Một log hữu ích cần phân biệt authentication failure và authorization failure, resource type/name, Kafka client role, principal đã xác thực nếu có, cluster/environment, listener ID hoặc producer component, retry/stop action, thời điểm bắt đầu và thời gian lỗi kéo dài.

Metrics gợi ý:

| Metric | Ý nghĩa |
|---|---|
| kafka_authentication_failures_total | Authentication failures |
| kafka_authorization_failures_total | Authorization denials |
| kafka_authorization_retry_total | Container auth retry attempts |
| kafka_container_stopped_total | Container stops do auth exception |
| kafka_consumer_last_successful_poll_timestamp | Thời điểm poll thành công gần nhất nếu custom instrument |
| kafka_consumer_records_processed_total | Records processed |
| kafka_consumer_lag | Group backlog |
| kafka_producer_send_failures_total | Producer send failures |
| kafka_transaction_failures_total | Transaction outcome failures |

Đây là metric names gợi ý cho custom instrumentation, không phải tất cả đều có sẵn trong Spring Kafka. Tags nên có cardinality thấp: service, listener, client role, exception category, environment. Không dùng raw principal nếu số principal lớn hoặc có dữ liệu nhạy cảm; cân nhắc mapping về service identity đã được duyệt.

### 15.1 Alert theo impact

Một authorization error có thể xuất hiện một lần trong lúc ACL rollout và tự phục hồi. Lỗi kéo dài cần alert theo duration/rate và impact:

~~~text
authorization failure rate > 0
AND consumer has no successful poll/progress
FOR 2 minutes
~~~

Điều kiện cụ thể phụ thuộc metric có sẵn và SLA. Cũng cần alert khi producer send failures tăng hoặc consumer lag vượt budget.

Không coi container RUNNING là healthy. Nếu auth retry interval được cấu hình, container có thể còn tồn tại nhưng chưa xử lý records thành công. Health check cần kết hợp successful poll/record progress, assignment và lag phù hợp.

## 16. Giảm log noise khi auth exception lặp lại

Nếu retry interval được bật và broker vẫn từ chối quyền, exception có thể xuất hiện lặp theo chu kỳ. Một policy thực dụng:

- Log ERROR một lần khi auth failure bắt đầu.
- Log WARN summary theo khoảng thời gian nếu vẫn kéo dài.
- Tăng metric cho từng retry attempt.
- Log INFO/WARN khi consumer phục hồi.
- Log ERROR khi container dừng hoặc producer send/recovery failure ảnh hưởng dữ liệu.

Ví dụ structured summary:

~~~text
event=kafka_authorization_retry
clientRole=consumer
listenerId=orders-main
exception=TopicAuthorizationException
resource=orders.created
retryIntervalSeconds=30
failureDurationSeconds=180
attempts=6
~~~

Đây là schema do ứng dụng định nghĩa. Resource và principal cần được sanitize. Nếu broker exception không cung cấp resource an toàn để log, ghi exception category và tham chiếu broker audit event.

Sampling không được che outage. Nếu chỉ log auth failure đầu tiên, hãy có counter và alert khi lỗi vẫn tồn tại. Khi phục hồi, log recovery event để operator biết consumer đã hoạt động lại.

## 17. ACL cho retry topics và DLT

Một listener dùng @RetryableTopic có thể subscribe main topic, retry topics và DLT. Consumer principal cần READ trên topics mà retry listener thực sự đọc và READ trên consumer groups tương ứng. Recoverer/producer principal cần WRITE trên destination retry/DLT topics.

Nếu chỉ cấp ACL cho main topic, main consumer có thể chạy nhưng retry listener lại bị TopicAuthorizationException. Nếu producer có thể ghi main topic nhưng không ghi DLT, recovery có thể thất bại đúng lúc poison record hết retries.

Ví dụ ma trận quyền:

| Component | Resource | Operation |
|---|---|---|
| Main consumer | orders.created | READ |
| Main consumer | orders-main group | READ |
| Retry consumer | orders.created-retry-* | READ |
| Retry consumer | retry group(s) | READ |
| DLT consumer | orders.created.DLT | READ |
| Recoverer producer | orders.created.DLT | WRITE |
| Retry publisher | retry topics | WRITE |

Tên group thực tế phụ thuộc retry-topic configuration. Không sao chép wildcard resource pattern mà chưa kiểm tra topic/group names được tạo ở runtime.

DLT recovery failure không phải consumer authorization retry. Nếu recoverer gửi DLT nhưng producer không có WRITE, đây là producer authorization failure. authExceptionRetryInterval của consumer không tự giải quyết quyền WRITE đó.

## 18. AdminClient và authorization errors

Ứng dụng có thể dùng KafkaAdmin/AdminClient để describe topics, create/delete topics, describe consumer groups, alter configs hoặc inspect cluster metadata. Các thao tác này có ACL riêng.

Một consumer có thể đọc topic bình thường nhưng health check dùng AdminClient lại bị ClusterAuthorizationException vì principal không có quyền DescribeCluster hoặc DescribeConfigs.

Không cấp quyền Admin rộng cho consumer chỉ để health check xanh.

### 18.1 Tách principal theo role

Một kiến trúc bảo mật thường tách:

- Consumer principal: chỉ READ topics và READ group.
- Producer principal: chỉ WRITE topics cần thiết.
- Admin principal: quyền quản trị có kiểm soát, dùng bởi deployment/operations tooling.
- DLT/recovery principal: chỉ destination và operations cần thiết.

Nếu một service dùng chung principal cho consume, publish, admin và DLT, blast radius khi credential bị lộ sẽ lớn hơn.

## 19. Least privilege và quyền prefix

ACL nên cấp theo resource và operation tối thiểu. Tránh cấp Cluster ALL, Topic wildcard và Group wildcard chỉ để làm listener chạy.

Một policy hợp lý hơn:

- READ trên topics cụ thể cần consume.
- READ trên consumer group cụ thể.
- WRITE chỉ trên output/retry/DLT topics mà service thật sự publish.
- Transactional ID permissions chỉ cho namespace của service nếu dùng transactions.
- Admin permissions được tách khỏi runtime principal.

Prefix orders- có thể tiện cho retry topics được sinh tự động, nhưng phải có ownership và naming rules. Nếu service có quyền trên prefix quá rộng, topic mới trong tương lai có thể tự động nằm trong phạm vi quyền mà không có review.

### 19.1 ACL rollout và secret rotation

1. Tạo/kiểm tra principal mới.
2. Cấp ACL tối thiểu.
3. Test authentication và authorization từ môi trường tương ứng.
4. Rollout credentials theo chiến lược overlap nếu platform hỗ trợ.
5. Theo dõi auth errors và consumer progress.
6. Thu hồi credential cũ sau khi xác nhận mọi instances đã chuyển.
7. Giữ audit trail cho thay đổi ACL.

Không thu hồi credential cũ trước khi mọi replicas dùng credential mới nếu hệ thống không có cơ chế coordinated rotation.

## 20. Chẩn đoán AuthorizationException theo thứ tự

Khi consumer dừng với AuthorizationException:

1. Lấy exception subtype và full cause chain.
2. Xác định thao tác thất bại: metadata, fetch, group join, commit, transaction hay produce.
3. Xác định resource: topic, group, cluster hoặc transactional ID.
4. Xác định principal broker thực sự nhận diện.
5. Xác nhận cluster/environment mà client kết nối.
6. Đọc broker authorization/audit logs.
7. Liệt kê ACL hiện có cho principal và resource.
8. So sánh operation cần thiết với operation được cấp.
9. Kiểm tra resource pattern literal/prefix/wildcard.
10. Kiểm tra listener group ID có bị override bởi annotation hoặc idIsGroup không.
11. Kiểm tra retry/DLT topics và groups nếu có.
12. Sửa ACL hoặc principal mapping theo least privilege.
13. Xác nhận container retry/restart theo policy.
14. Kiểm tra consumer assignment, successful poll, lag và record progress.
15. Ghi lại thay đổi quyền và kết quả phục hồi.

Không bắt đầu bằng cách cấp Cluster ALL hoặc reset offsets. Đó là các hành động rộng và có thể tạo vấn đề mới.

## 21. Khi container stop vì AuthorizationException

Nếu default stop behavior đang có hiệu lực:

- Container có thể không tự khởi động lại chỉ vì ACL được cấp sau đó.
- Cần xác định lifecycle policy: operator restart, application restart hoặc container registry start.
- Xác nhận lỗi quyền đã được sửa trước khi restart.
- Theo dõi group rebalance và partition reassignment.
- Kiểm tra committed offsets và lag sau khi consumer quay lại.

Nếu authExceptionRetryInterval được cấu hình và version hỗ trợ:

- Container có thể thử lại sau interval.
- Không cần restart chỉ vì ACL được cấp muộn nếu retry thành công.
- Nếu ACL vẫn sai, lỗi tiếp tục xuất hiện theo chu kỳ.
- Cần alert và summary để tránh noise.
- Cần xác nhận successful poll/record progress sau recovery.

Không restart liên tục khi ACL chưa sửa. Restart loop có thể tạo log noise, consumer group churn và broker authentication load. Nếu lỗi là authorization denial ổn định, restart không thêm quyền.

## 22. Chẩn đoán producer authorization failure

Khi KafkaTemplate.send() thất bại:

1. Xác định future/transaction exception và unwrap cause.
2. Xác nhận destination topic đúng cluster.
3. Xác định principal producer thực tế.
4. Kiểm tra WRITE/Describe ACL trên topic.
5. Nếu dùng transaction, kiểm tra transactional ID permissions.
6. Kiểm tra idempotence/transaction setup và producer fencing riêng.
7. Xác định send outcome có chắc chắn failed hay unknown.
8. Áp dụng retry budget phù hợp và idempotency.
9. Log final failure có topic và operation, không payload.
10. Alert nếu producer không thể publish sự kiện quan trọng.

Không dựa vào listener container auth retry interval để retry KafkaTemplate sends.

## 23. Những lỗi dễ bị nhầm

| Exception/triệu chứng | Khả năng | Hướng kiểm tra |
|---|---|---|
| SaslAuthenticationException | Credential/mechanism/principal auth | SASL config và broker auth logs |
| SSLHandshakeException | TLS trust/certificate/protocol | Truststore, certificate chain, listener |
| TopicAuthorizationException | Thiếu quyền topic | Topic ACL và principal |
| GroupAuthorizationException | Thiếu quyền group | Group ACL và group.id thực tế |
| ClusterAuthorizationException | Thiếu cluster operation | Admin/cluster ACL |
| TransactionalIdAuthorizationException | Thiếu quyền transactional ID | Transactional ID ACL |
| ProducerFencedException | Producer bị fencing | Transactional ID uniqueness/lifecycle |
| TimeoutException | Network, broker, queue hoặc operation timeout | Client metrics và broker health |
| UnknownTopicOrPartitionException | Topic/partition không tồn tại hoặc metadata stale | Topic provisioning/metadata |
| RecordDeserializationException | Dữ liệu không decode được | Deserializer/schema; không phải ACL |

Exception wrapping có thể làm log hiển thị ExecutionException hoặc ListenerExecutionFailedException bên ngoài. Luôn kiểm tra root cause.

## 24. Integration tests cho auth behavior

Unit test gọi trực tiếp listener method không kiểm chứng auth behavior, vì AuthorizationException thường xảy ra trước khi listener được gọi. Dùng broker test environment có ACL/security thật hoặc môi trường integration tương đương.

### 24.1 Consumer thiếu topic READ

1. Tạo test principal có authentication hợp lệ.
2. Chỉ cấp group READ, cố ý không cấp topic READ.
3. Khởi động listener container.
4. Xác nhận exception subtype/behavior theo Kafka/Spring Kafka version.
5. Xác nhận listener không được gọi cho record chưa đọc.
6. Cấp topic READ.
7. Nếu authExceptionRetryInterval bật, đợi container thử lại.
8. Xác nhận consumer join/consume được và records tiến triển.

### 24.2 Consumer thiếu group READ

1. Cấp topic READ.
2. Không cấp group READ.
3. Khởi động consumer với group.id cụ thể.
4. Xác nhận group authorization failure.
5. Cấp quyền group phù hợp.
6. Xác nhận retry/restart behavior đúng.
7. Kiểm tra offsets/assignment sau recovery.

### 24.3 Producer thiếu topic WRITE

1. Tạo producer principal có auth hợp lệ.
2. Không cấp WRITE trên destination topic.
3. Gọi KafkaTemplate.send().
4. Xác nhận future/transaction failure có cause phù hợp.
5. Cấp WRITE.
6. Gửi lại theo test policy.
7. Xác nhận record xuất hiện theo semantics/idempotency mong đợi.

Test này không sử dụng authExceptionRetryInterval của consumer container.

### 24.4 Test transactional ID ACL

- Cấu hình transactional producer với transactional.id/prefix cụ thể.
- Cấp topic permissions nhưng cố ý thiếu transactional ID permission.
- Xác nhận transaction operation bị từ chối.
- Cấp đúng quyền.
- Kiểm tra transaction commit/abort và downstream read_committed behavior.

### 24.5 Test retry interval

- Chạy Spring Kafka version hỗ trợ authExceptionRetryInterval.
- Đặt interval đủ dài để quan sát.
- Cố ý tạo auth failure.
- Xác nhận container không xử lý nó như listener record exception.
- Cấp ACL trong lúc container chờ.
- Xác nhận lần retry sau có thể thành công.
- Đo successful poll/record progress.
- Không assert timing chính xác đến millisecond; dùng timeout hợp lý.

### 24.6 Test không lộ secrets

- Dùng credentials giả trong test.
- Capture application/client logs.
- Xác nhận password, token và JAAS secret không xuất hiện.
- Xác nhận principal/resource/error category đủ cho chẩn đoán.
- Kiểm tra log masking sau khi exception bị wrap.

## 25. Runbook bảo mật vận hành

**Khoanh vùng**

1. Xác định service, pod, listener/client role và Kafka cluster.
2. Xác định consumer hay producer/admin client.
3. Thu exception subtype và resource bị từ chối.
4. Kiểm tra thời điểm bắt đầu và scope replicas bị ảnh hưởng.
5. Xem broker audit/security logs để xác nhận principal.

**Khắc phục**

6. Xác minh group ID/topic/transactional ID thực tế.
7. Kiểm tra ACL theo resource và operation.
8. Kiểm tra principal mapping, SASL/TLS và secret rotation.
9. Cấp quyền tối thiểu hoặc sửa identity mapping.
10. Nếu container đã stop, restart theo lifecycle policy; nếu retry interval đang hoạt động, chờ lần thử kế tiếp có kiểm soát.
11. Với producer failure, xử lý send/transaction outcome riêng.

**Xác nhận**

12. Xác nhận authentication/authorization failures ngừng tăng.
13. Xác nhận consumer assignment và successful poll.
14. Xác nhận committed offsets/lag tiến triển.
15. Xác nhận producer sends và transaction commits thành công.
16. Kiểm tra retry/DLT consumers cũng có quyền cần thiết.
17. Ghi lại ACL change, principal, resource và người phê duyệt.
18. Thu hẹp hoặc thu hồi quyền tạm thời sau incident nếu policy yêu cầu.

## 26. Những hiểu nhầm thường gặp

**“Authentication thành công nghĩa là consumer có thể đọc topic.”** Sai. Broker còn kiểm tra ACL trên topic và group.

**“AuthorizationException là lỗi của listener record.”** Thường không. Nó có thể xảy ra trong Kafka client/container operations trước listener invocation.

**“DefaultErrorHandler sẽ retry AuthorizationException.”** Không nên giả định. Container có xử lý riêng cho authentication/authorization failures.

**“authExceptionRetryInterval áp dụng cho mọi producer send.”** Sai. Đây là cơ chế listener container/consumer path; KafkaTemplate send failures cần xử lý riêng.

**“Bật retry interval là ACL sẽ tự đúng.”** Sai. Nó chỉ thử lại sau khoảng chờ; quyền vẫn phải được sửa.

**“Group ID và listener ID luôn giống nhau.”** Không. @KafkaListener.id có thể được dùng làm group khi idIsGroup=true và không có groupId explicit, nhưng đây là hai khái niệm khác nhau.

**“Cấp Cluster ALL là cách sửa nhanh an toàn.”** Sai. Nó mở rộng blast radius và vi phạm least privilege.

**“Producer có WRITE topic thì transaction chắc chắn hoạt động.”** Không. Transactional ID và các quyền liên quan cũng cần phù hợp.

**“Dùng consumer auth retry interval để sửa DLT producer ACL.”** Sai. DLT publisher là producer path.

**“Restart consumer sẽ sửa ACL.”** Sai. Restart không tạo quyền mới.

**“Không thấy exception nghĩa là dữ liệu đã xử lý.”** Không. Cần kiểm tra successful poll, assignment, offset progress và business completion.

**“Có thể log JAAS config để biết username/password.”** Không. Không log secrets; xác minh principal bằng broker logs và secret reference đã sanitize.

## 27. Checklist triển khai

**Identity và ACL**

- [ ] Biết principal broker thực tế nhận diện.
- [ ] Phân biệt authentication và authorization.
- [ ] Consumer có READ topic và READ group cần thiết.
- [ ] Producer có WRITE trên destination topics.
- [ ] Retry/DLT consumers và publishers có ACL tương ứng.
- [ ] Transactional producer có quyền trên transactional ID phù hợp.
- [ ] Prefix/wildcard ACL được governance và giới hạn.
- [ ] Runtime principals dùng least privilege.

**Spring Kafka behavior**

- [ ] Xác nhận Spring Kafka version.
- [ ] Hiểu default container stop behavior khi auth exception.
- [ ] authExceptionRetryInterval được cấu hình khi policy cần retry.
- [ ] Consumer group ID thực tế được xác định.
- [ ] Không nhầm auth exception với listener record exception.
- [ ] Producer send failure được xử lý riêng.
- [ ] Recovery/DLT producer errors có monitoring riêng.

**Observability và security**

- [ ] Log exception subtype, resource và operation khi có.
- [ ] Không log password, token, JAAS hoặc private key.
- [ ] Có metrics cho auth failures/retries và consumer progress.
- [ ] Alert khi auth failures kéo dài.
- [ ] Log retry được rate-limit/summary nếu cần.
- [ ] Audit trail lưu ACL changes.
- [ ] Không cấp quyền rộng để dập alert.

**Verification**

- [ ] Test consumer thiếu topic READ.
- [ ] Test consumer thiếu group READ.
- [ ] Test producer thiếu topic WRITE.
- [ ] Test transactional ID ACL nếu dùng transactions.
- [ ] Test authExceptionRetryInterval với broker security thật.
- [ ] Test ACL recovery không cần reset offsets.
- [ ] Test logs không lộ secrets.
- [ ] Test retry/DLT topics và consumer groups.

## 28. Tài liệu tham khảo

- Spring for Apache Kafka — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Spring for Apache Kafka — Message Listener Containers: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka API — ContainerProperties: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/ContainerProperties.html
- Apache Kafka — Authorization and ACLs: https://kafka.apache.org/documentation/#security_authz
- Apache Kafka — Consumer configuration: https://kafka.apache.org/documentation/#consumerconfigs
- Apache Kafka — Producer configuration: https://kafka.apache.org/documentation/#producerconfigs

API details and ACL implications should be checked against the Kafka broker/client and Spring Kafka versions deployed in the environment.

## 29. Kết luận

**AuthorizationException** cho biết Kafka broker đã từ chối một thao tác vì principal không có quyền phù hợp trên resource. Với consumer, lỗi có thể xảy ra trong poll, metadata hoặc group coordination trước khi listener nhận record; vì vậy không xử lý nó như exception nghiệp vụ thông thường trong DefaultErrorHandler. Spring Kafka từ version 2.8 hỗ trợ cấu hình **authExceptionRetryInterval** trên ContainerProperties để container thử lại sau một khoảng chờ, nếu consumer được cấu hình group ID và các điều kiện version/API tương ứng được đáp ứng.

Cách khôi phục đúng là xác định exception subtype, principal thực tế, resource và operation bị từ chối; sửa ACL hoặc identity mapping theo least privilege; rồi xác nhận container/producer thực sự hoạt động lại. Retry interval chỉ giúp thử lại sau khi quyền được sửa, không thay thế security policy. Một vận hành an toàn cần phân biệt consumer với producer/DLT paths, theo dõi auth failures cùng offset/lag progress và tuyệt đối không để credentials xuất hiện trong logs.

