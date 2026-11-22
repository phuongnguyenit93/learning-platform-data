# Authorization failure

Một ứng dụng Spring Kafka có thể kết nối thành công tới Kafka broker, hoàn tất TLS/SASL handshake và vẫn không được phép đọc topic, tham gia consumer group hoặc ghi record vào Dead Letter Topic (DLT). Đây là **authorization failure**: broker đã nhận diện principal của client nhưng chính sách ACL/authorizer không cho phép principal thực hiện operation trên resource tương ứng.

Trong vận hành, lỗi này thường xuất hiện sau khi triển khai một service mới, đổi `group.id`, thêm topic hoặc DLT, đổi principal giữa các môi trường, hay thay đổi quyền của service account. Một ứng dụng có thể vẫn khởi động và health endpoint vẫn trả `UP`, trong khi listener không thể consume. Vì vậy, cần phân biệt **authentication** (client là ai?) với **authorization** (client được phép làm gì?), xác định đúng resource/operation bị từ chối, rồi phản ánh trạng thái đó đúng vào readiness.

## 1. Authentication và authorization khác nhau thế nào?

Kafka bảo vệ kết nối qua nhiều lớp. TLS có thể mã hóa và xác thực certificate; SASL có thể xác thực principal; authorizer kiểm tra quyền trên cluster resources.

| Khái niệm | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| TLS / transport security | Có thiết lập được kênh bảo mật và tin cậy certificate không? | Certificate expired, truststore sai, hostname verification thất bại |
| Authentication | Client chứng minh danh tính principal như thế nào? | Sai SASL password, mechanism không khớp, certificate không hợp lệ |
| Authorization | Principal đã xác thực có quyền thực hiện operation trên resource không? | `TopicAuthorizationException`, `GroupAuthorizationException` |

Ví dụ:

```text
Spring Kafka application
       |
       | TLS + SASL handshake
       v
Kafka broker xác thực principal:
       User:orders-service
       |
       v
Authorizer kiểm tra ACL
       |
       +--> READ topic orders?  ALLOW
       +--> READ group orders-worker? DENY
       |
       v
GroupAuthorizationException
```

Trong ví dụ, mật khẩu và SASL mechanism có thể hoàn toàn đúng. Lỗi nằm ở quyền trên resource `Group`, không phải ở secret. Đổi password hoặc khởi động lại pod không tự cấp quyền `READ` cho consumer group.

## 2. Các authorization exceptions thường gặp

Kafka client cung cấp các exception riêng theo loại resource hoặc thao tác. Những exception thường gặp trong ứng dụng Spring Kafka gồm:

| Exception | Ý nghĩa thường gặp | Nơi cần kiểm tra |
|---|---|---|
| `TopicAuthorizationException` | Principal không được phép thực hiện operation trên một hoặc nhiều topic | ACL của topic nguồn, output topic, retry topic hoặc DLT |
| `GroupAuthorizationException` | Principal không được phép sử dụng consumer group | ACL `READ` trên group tương ứng |
| `ClusterAuthorizationException` | Principal không được phép thực hiện operation ở cấp cluster | ACL/permission cho cluster-level operation hoặc admin request |
| `TransactionalIdAuthorizationException` | Producer không được phép sử dụng transactional ID | ACL `WRITE` trên resource `TransactionalId` |
| `DelegationTokenAuthorizationException` | Không có quyền cho thao tác delegation token tương ứng | Chính sách delegation token và principal |

Tên exception và operation thực tế phụ thuộc request Kafka bị từ chối. Đôi khi framework bọc exception trong một exception khác; hãy tìm **root cause** thay vì chỉ đọc lớp exception ngoài cùng.

Không nhầm các exception này với lỗi kết nối như `TimeoutException`, lỗi DNS, `SaslAuthenticationException` hoặc lỗi SSL. Một timeout có thể che mất việc client đang retry request bị từ chối, nhưng không đủ để kết luận là ACL thiếu.

## 3. Kafka ACL gắn với resource và operation

Kafka authorizer quyết định quyền dựa trên principal, resource, operation, host và policy. Với luồng consume, những resource quan trọng thường là **Topic** và **Group**:

| Luồng | Resource | Operation thường cần |
|---|---|---|
| Đọc record từ topic nguồn | `Topic: orders` | `READ`; có thể cần `DESCRIBE` tùy thao tác/cấu hình |
| Tham gia group và commit offsets | `Group: orders-worker` | `READ` |
| Ghi kết quả sang topic khác | `Topic: order-results` | `WRITE`; có thể cần `DESCRIBE` |
| Ghi record sang DLT | `Topic: orders.DLT` | `WRITE`; có thể cần `DESCRIBE` |
| Ghi transaction Kafka | `TransactionalId: orders-tx-*` | `WRITE`; các thao tác/phiên bản có thể cần quyền bổ sung |
| Tạo topic hoặc thay đổi cấu hình | Topic/Cluster | `CREATE`, `ALTER`, `ALTER_CONFIGS` theo chính sách |

Các operation và quan hệ kế thừa giữa ACLs phụ thuộc Kafka authorizer/version. Ví dụ, một số operation ngầm bao hàm quyền `DESCRIBE`. Không nên cấp `ALL` chỉ để làm lỗi biến mất; hãy xác định request cụ thể bị từ chối và cấp quyền tối thiểu cần thiết.

Một principal consumer chỉ có `READ` trên topic nhưng thiếu `READ` trên group vẫn có thể không tham gia được consumer group. Ngược lại, có quyền group nhưng thiếu quyền topic vẫn không fetch được dữ liệu. Cần kiểm tra cả hai phía.

## 4. Lỗi authorization có thể xảy ra ở đâu trong vòng đời?

Không phải mọi lỗi authorization đều xuất hiện ngay lúc application context khởi động. Một số request chỉ được gửi khi listener subscribe, fetch metadata, join group, commit offset hoặc khi producer thực hiện send.

```text
Application start
       |
       v
ConsumerFactory tạo KafkaConsumer
       |
       v
subscribe / metadata / join group
       |
       +--> GroupAuthorizationException
       |
       v
poll / fetch records
       |
       +--> TopicAuthorizationException
       |
       v
Listener xử lý record
       |
       v
Producer send output hoặc DLT
       |
       +--> TopicAuthorizationException
       +--> TransactionalIdAuthorizationException
```

Vì vậy, một bean `KafkaTemplate` được tạo thành công không chứng minh principal có quyền ghi mọi topic. Một `KafkaConsumer` được khởi tạo cũng không chứng minh quyền đọc topic/group đã được kiểm tra đầy đủ. Chỉ một phép thử thực tế trên đúng principal, resource và operation mới xác nhận được quyền cần thiết.

## 5. Xác định đúng principal đang được Kafka nhìn thấy

Trước khi sửa ACL, cần biết broker đang nhận request từ principal nào. Trong môi trường có nhiều cluster hoặc nhiều listener factory, principal của consumer và producer thậm chí có thể khác nhau.

Kiểm tra:

1. `security.protocol` thực tế (`SASL_SSL`, `SSL`, hoặc cấu hình tương ứng).
2. `sasl.mechanism` và JAAS/client login config được consumer/producer sử dụng.
3. Certificate subject hoặc SASL principal mapping nếu dùng TLS/SASL.
4. `client.id`, consumer group và transactional ID để ghép log broker/client.
5. Secret version, workload identity hoặc service account gắn với đúng deployment.

Không in password, JAAS config có secret, private key, token hoặc toàn bộ environment vào log. Khi cần xác nhận principal, dùng broker audit logs hoặc cơ chế quan sát đã được bảo vệ; chỉ log tên principal đã được kiểm soát và không chứa credential.

Một lỗi thường gặp là consumer sử dụng principal `User:orders-service`, nhưng DLT producer lại dùng principal khác `User:orders-publisher`. Nếu chỉ cấp quyền cho consumer principal, đọc topic nguồn có thể thành công trong khi recovery publish vẫn thất bại.

## 6. Cấp quyền tối thiểu cho consumer

Một consumer group cần quyền đọc topic nguồn và quyền sử dụng group. Ví dụ dưới đây minh họa thao tác ACL bằng `kafka-acls.sh` với principal giả định `User:orders-service`:

```bash
# Quyền đọc topic nguồn
kafka-acls.sh --bootstrap-server kafka.example:9093 \
  --add --allow-principal User:orders-service \
  --operation Read --topic orders

# Quyền tham gia consumer group
kafka-acls.sh --bootstrap-server kafka.example:9093 \
  --add --allow-principal User:orders-service \
  --operation Read --group orders-worker
```

Đây là ví dụ lệnh quản trị; cần dùng bootstrap endpoint và cơ chế xác thực quản trị đúng môi trường, có thể cần `--command-config` trỏ tới file client config được bảo vệ. Không đưa password trực tiếp vào command line hoặc source control. Quyền `DESCRIBE` có thể cần tùy request, Kafka version và authorizer policy.

Nếu topic được quản lý bởi platform team, ứng dụng không nên tự có quyền `CREATE`/`ALTER` chỉ để consumer có thể chạy. Topic nên được provision trước qua quy trình hạ tầng, với retention, partition, replication và ACL được review.

## 7. Producer và DLT cần quyền riêng

Một consumer có thể đọc topic nguồn bình thường nhưng đến khi lỗi record, `DeadLetterPublishingRecoverer` gửi DLT thì gặp authorization failure. Lúc này lỗi không phải quyền `READ` của source consumer; đó là quyền publish của producer principal trên DLT.

| Luồng | Principal có thể dùng | Quyền cần kiểm tra |
|---|---|---|
| Consume `orders` | Consumer principal | `READ` topic `orders`, `READ` group `orders-worker` |
| Publish `order-results` | Producer principal | `WRITE` topic `order-results` |
| Publish `orders.DLT` | DLT producer principal | `WRITE` topic `orders.DLT` |
| Publish `orders-retry` | Retry publisher principal | `WRITE` topic `orders-retry` |
| Kafka transaction | Transactional producer principal | `WRITE` transactional ID và quyền trên topic liên quan |

Nếu `KafkaTemplate` và consumer dùng chung principal, quyền vẫn phải được cấp trên từng resource. Nếu dùng hai security configs khác nhau, hãy xác nhận principal cho **đúng producer factory** được DLT template sử dụng.

Khi DLT publish thất bại, recovery chưa chắc đã hoàn tất. Nếu recoverer được cấu hình để chờ send result và báo lỗi khi send thất bại, error handler có thể thử recovery lại theo policy; offset nguồn không nên được coi là đã recover thành công chỉ vì destination đã được chọn. Cần log source coordinates, DLT destination, principal và root exception, rồi xác minh committed offset cùng DLT record thực tế.

## 8. Authorization với Kafka transactions

Một producer transaction có thêm resource `TransactionalId`. Ứng dụng có thể có quyền `WRITE` trên output topic nhưng thiếu quyền sử dụng transactional ID, dẫn tới `TransactionalIdAuthorizationException` khi khởi tạo hoặc thực hiện transaction.

Ví dụ luồng consume-transform-produce:

```text
Consumer principal
  READ source topic
  READ consumer group
          |
          v
Listener + Kafka transaction manager
          |
          v
Transactional producer principal
  WRITE transactional ID
  WRITE output topic
          |
          v
Commit output + input offset trong Kafka transaction
```

Với Spring Kafka, `transactionIdPrefix` tạo transactional IDs cho producer instances. Prefix phải được thiết kế không xung đột giữa các instance đồng thời; tuy nhiên, **đặt prefix duy nhất không thay thế ACL**. Authorizer phải cho principal quyền sử dụng dải transactional IDs phù hợp. Nếu prefix thay đổi sau deploy, ACL resource pattern có thể không còn khớp.

Khi transaction commit/abort, quyền trên topic và transactional ID phải tương thích với thiết kế. Không cấp `ALL` trên toàn cluster chỉ để sửa một lỗi transactional ID; dùng resource pattern hẹp và kiểm tra quyền theo principal/ID thật.

## 9. Cấu hình bảo mật Spring Boot

Một cấu hình consumer SASL/SSL có thể được truyền qua Spring Boot properties. Ví dụ minh họa dùng environment variable cho secret:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka.example:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
```

Ví dụ này chỉ minh họa cơ chế cấu hình; cơ chế SCRAM, JAAS module, truststore và property binding cần khớp với cluster. Trong production, inject secret từ secret manager/Kubernetes Secret hoặc workload identity theo chuẩn tổ chức. Không ghi giá trị thật vào YAML trong Git.

Nếu producer dùng cấu hình bảo mật riêng, cần cấu hình `spring.kafka.producer.properties` hoặc producer factory tương ứng. Một custom `KafkaTemplate`/`ProducerFactory` có thể không kế thừa cấu hình mà consumer đang sử dụng. Kiểm tra bean wiring thay vì giả định một security block áp dụng cho mọi client.

## 10. `authExceptionRetryInterval` trong Spring Kafka

Khi container gặp authorization exception, hành vi mặc định trong các phiên bản Spring Kafka hỗ trợ là dừng consumer/container nếu không cấu hình cơ chế retry phù hợp. Từ Spring Kafka 2.8, `ContainerProperties` có thuộc tính **`authExceptionRetryInterval`** để container có thể thử lại sau một khoảng thời gian khi gặp lỗi authorization thuộc phạm vi được hỗ trợ.

Ví dụ:

```java
ContainerProperties properties = factory.getContainerProperties();
properties.setAuthExceptionRetryInterval(Duration.ofSeconds(30));
```

Khoảng retry phải được chọn có chủ đích và theo tài liệu của đúng version. Đặc biệt, không giả định thuộc tính này sửa mọi lỗi authentication như SASL password sai hoặc TLS handshake thất bại. **Authorization failure** có thể được khắc phục bằng thay đổi ACL khi runtime; **authentication failure** thường đòi hỏi sửa credentials/certificate/config và có thể có semantics dừng khác.

Retry interval không cấp quyền, không làm broker bỏ qua ACL và không đảm bảo listener đã sẵn sàng. Nó chỉ cho phép container thử lại trong các trường hợp được framework hỗ trợ. Nếu ACL không được sửa, ứng dụng có thể lặp log lỗi theo chu kỳ; cần alert, backoff hợp lý và tránh log storm.

## 11. Retry authorization có phù hợp với mọi loại listener không?

Hãy chọn hành vi dựa trên cách tổ chức cấp quyền và SLO:

| Tình huống | Cách tiếp cận |
|---|---|
| ACL có thể được cấp trong vài phút sau deploy | Có thể dùng `authExceptionRetryInterval` để container thử lại, đồng thời readiness phản ánh chưa sẵn sàng |
| Principal/secret sai vĩnh viễn | Sửa identity/secret; không dựa vào retry liên tục |
| Topic/group bị xóa hoặc sai tên | Sửa cấu hình/resource; retry auth không giải quyết resource mismatch |
| DLT producer thiếu quyền | Sửa quyền publish của producer principal; xác nhận recovery không commit nhầm offset |
| ACL bị thu hồi khi app đang chạy | Theo dõi exception, trạng thái container và readiness; chuẩn bị khôi phục quyền |
| Authorization failure kéo dài | Alert và giữ instance out of readiness nếu consumer là chức năng bắt buộc |

Retry nên có nhịp phù hợp với thời gian phản hồi của platform team. Một vòng lặp mỗi vài mili giây chỉ làm tăng log và request broker. Mặt khác, khoảng retry quá dài làm chậm khôi phục sau khi ACL đã được sửa. Chọn giá trị theo SLO, số consumer và cách ACL propagation của cluster.

## 12. Readiness và liveness phải phản ánh đúng failure

Đối với một consumer service, process có thể vẫn sống nhưng listener không thể đọc topic do authorization failure. Đây là khác biệt quan trọng giữa **liveness** và **readiness**:

| Probe | Câu hỏi | Khi Kafka authorization thất bại |
|---|---|---|
| Liveness | JVM/process còn hoạt động và có thể tự phục hồi không? | Thường vẫn `UP`; không restart chỉ vì ACL thiếu |
| Readiness | Instance có thể thực hiện chức năng cần thiết ngay lúc này không? | Có thể `DOWN` nếu listener là dependency bắt buộc |
| Startup | Ứng dụng đã hoàn tất khởi tạo ban đầu chưa? | Phụ thuộc startup policy; không nên biến ACL tạm thời thành restart loop vô hạn |

Nếu liveness probe thất bại vì authorization, Kubernetes có thể restart pod liên tục dù nguyên nhân nằm ở broker ACL. Restart không cấp quyền mới và có thể tạo thêm group churn. Readiness phù hợp hơn để loại instance khỏi luồng phục vụ khi consumer thiết yếu không thể hoạt động.

Tuy nhiên, một HTTP API và một Kafka consumer trong cùng process có thể có yêu cầu readiness khác nhau. Nếu instance còn phục vụ một API độc lập nhưng consumer chỉ là một workload phụ, không nhất thiết phải đánh dấu toàn application `DOWN`. Xác định readiness theo **vai trò của listener đối với chức năng instance**.

## 13. Broker connectivity không chứng minh consumer authorization

Một health check chỉ mở socket hoặc gọi `describeCluster` không nhất thiết kiểm tra được quyền đọc topic và group của consumer principal. Health check có thể dùng `KafkaAdmin` với cấu hình client khác, hoặc chỉ kiểm tra cluster metadata.

Ví dụ:

```text
Health check principal: User:platform-monitor
  DESCRIBE cluster -> ALLOW

Listener principal: User:orders-service
  READ orders -> ALLOW
  READ orders-worker group -> DENY

Generic broker health = UP
Actual consumer readiness = DOWN
```

Vì vậy, đừng lấy một health indicator kết nối broker chung làm bằng chứng rằng mọi listener đã được authorization đầy đủ. Readiness nên xét trạng thái container/listener cần thiết và các lỗi authorization gần nhất trên đúng principal.

Không nên phát một record giả vào topic production chỉ để probe quyền mỗi vài giây; điều đó tạo side effects và tải không cần thiết. Có thể dùng một probe topic/group riêng được cấp quyền, nhưng nó chỉ chứng minh principal của probe có quyền trên probe resource, không chứng minh quyền trên `orders` hoặc `orders-worker`. Tốt nhất là kiểm tra ACL qua platform control plane và xác nhận listener thật đã join/fetch thành công.

## 14. Thiết kế readiness state cho listener quan trọng

Với listener thiết yếu, có thể duy trì trạng thái readiness ở application layer dựa trên lifecycle events, assignment/health state và authorization errors. Ví dụ dưới đây minh họa ý tưởng thay vì phụ thuộc vào một API lifecycle cụ thể của mọi phiên bản Spring Kafka:

```java
public enum ConsumerReadiness {
    STARTING,
    READY,
    AUTHORIZATION_FAILED,
    STOPPED
}

@Component
public class ConsumerReadinessState {

    private final AtomicReference<ConsumerReadiness> state =
            new AtomicReference<>(ConsumerReadiness.STARTING);

    public void markReady() {
        state.set(ConsumerReadiness.READY);
    }

    public void markAuthorizationFailed() {
        state.set(ConsumerReadiness.AUTHORIZATION_FAILED);
    }

    public void markStopped() {
        state.set(ConsumerReadiness.STOPPED);
    }

    public ConsumerReadiness current() {
        return state.get();
    }
}
```

Một `HealthIndicator` có thể phản ánh state:

```java
@Component
public class OrdersConsumerHealthIndicator implements HealthIndicator {

    private final ConsumerReadinessState readiness;

    public OrdersConsumerHealthIndicator(ConsumerReadinessState readiness) {
        this.readiness = readiness;
    }

    @Override
    public Health health() {
        return switch (readiness.current()) {
            case READY -> Health.up().build();
            case AUTHORIZATION_FAILED -> Health.down()
                    .withDetail("reason", "Kafka authorization failed")
                    .build();
            case STARTING -> Health.outOfService()
                    .withDetail("reason", "Kafka listener is starting")
                    .build();
            case STOPPED -> Health.down()
                    .withDetail("reason", "Kafka listener is stopped")
                    .build();
        };
    }
}
```

`HealthIndicator`, `Health` và `Status` thuộc Spring Boot Actuator. Đoạn code là một mô hình state đơn giản; production implementation cần cập nhật state từ đúng lifecycle/error observation, xử lý nhiều child consumers và tránh `markReady()` quá sớm. Một container `isRunning()` không luôn chứng minh nó đã được assign partition hoặc fetch được record. Readiness tốt hơn nên được đánh dấu sau khi listener đạt điều kiện hoạt động mà service yêu cầu, đồng thời reset khi authorization failure xuất hiện.

Không để một child consumer khỏe ghi đè state `READY` trong khi child khác của listener quan trọng vẫn bị authorization failure. Với concurrency nhiều, aggregate readiness phải phản ánh **tất cả consumer bắt buộc** hoặc quy tắc quorum/partition ownership đã được định nghĩa.

## 15. Quan sát authorization failures

Các tín hiệu hữu ích cho dashboard và alert:

| Tín hiệu | Dùng để làm gì |
|---|---|
| Count theo exception class | Phân biệt `TopicAuthorizationException`, `GroupAuthorizationException`, transactional ID failure |
| Principal và client ID trong audit logs | Xác định danh tính bị từ chối, khi được phép ghi |
| Resource và operation | Biết ACL cần sửa ở topic, group, cluster hay transactional ID |
| Listener/container state | Xác định listener vẫn chạy, đã dừng hay đang retry authorization |
| Readiness state | Cho biết instance có thể nhận workload cần thiết hay không |
| DLT send failure count | Phát hiện producer principal không được phép publish DLT |
| Transaction failures | Phát hiện transactional ID ACL hoặc producer authorization issue |
| Consumer lag/oldest record age | Đánh giá tác động nghiệp vụ khi listener không thể consume |

Log nên chứa service, environment, `client.id`, group, topic, operation, exception class và timestamp nếu biết. Không log SASL password, token, JAAS raw string, private key hoặc full config object.

Metric labels cần cardinality thấp. Dùng exception class hoặc error category đã chuẩn hóa; không dùng raw exception message, offset, event ID hay credential làm label. Principal có thể là tag nếu số lượng principal hữu hạn và đã được review, nhưng thường log/audit chi tiết an toàn hơn.

## 16. Troubleshooting theo exception

Khi nhận authorization failure, hãy đi theo resource thay vì thử cấp quyền rộng:

| Exception / triệu chứng | Kiểm tra trước tiên | Hành động |
|---|---|---|
| `GroupAuthorizationException` | Principal thực tế, `group.id`, ACL Group | Cấp `READ` đúng group cho principal consumer |
| `TopicAuthorizationException` khi consume | Topic subscription, metadata/fetch, ACL Topic | Xác minh `READ` và quyền mô tả cần thiết trên topic nguồn |
| `TopicAuthorizationException` khi publish | Producer principal, output/DLT/retry topic | Cấp `WRITE` đúng topic cho producer principal |
| `TransactionalIdAuthorizationException` | `transactional.id` thực tế và prefix | Cấp quyền trên resource TransactionalId theo pattern phù hợp |
| `ClusterAuthorizationException` | Request cluster-level nào bị từ chối | Xác định có thực sự cần quyền cluster hay không; tránh cấp ALL |
| `SaslAuthenticationException` | Credential, mechanism, principal mapping | Sửa secret/identity; ACL không sửa được lỗi xác thực |
| SSL handshake failure | Certificate, truststore, hostname, TLS version | Sửa transport trust/identity; không thay ACL để chữa TLS |

Nếu exception không nêu rõ resource, bật log Kafka client/broker có chọn lọc trong khoảng điều tra và tra audit logs. Không bật TRACE toàn bộ Kafka client lâu dài trên production vì log có thể rất lớn và có thể lộ thông tin cấu hình nhạy cảm.

## 17. Cách kiểm tra ACL hiện tại

Với Kafka cluster dùng ACL authorizer và công cụ quản trị tương ứng, có thể liệt kê quyền của một principal:

```bash
kafka-acls.sh --bootstrap-server kafka.example:9093 \
  --command-config admin-client.properties \
  --list --principal User:orders-service
```

`admin-client.properties` phải nằm trong vùng bảo vệ và chứa cấu hình kết nối/quản trị phù hợp; không đưa nội dung file vào log hoặc Git. Kết quả list cần được đọc cùng resource pattern, host, operation và permission type (ALLOW/DENY). ACL có wildcard/prefix có thể ảnh hưởng nhiều resource hơn một entry cụ thể.

Nếu cluster dùng authorizer hoặc policy engine khác Kafka ACL truyền thống, dùng công cụ control plane chính thức của platform. Một số managed Kafka services quản lý quyền qua role/permission sets thay vì cho phép chạy `kafka-acls.sh` trực tiếp.

Khi xác minh, kiểm tra **principal đang chạy**, không phải principal quản trị. Admin có thể nhìn thấy toàn bộ ACL nhưng ứng dụng vẫn thiếu quyền do dùng principal khác, resource pattern không khớp hoặc host restriction.

## 18. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
|---|---|---|
| App kết nối broker nhưng listener không join group | Thiếu `READ` trên Group | Xác nhận `group.id` thực tế và ACL Group |
| Consumer join group nhưng không fetch topic | Thiếu quyền trên Topic hoặc subscribe nhầm tên | Kiểm tra topic ACL và subscription pattern |
| Publish chính thành công nhưng DLT send thất bại | Producer principal thiếu `WRITE` trên DLT | Cấp quyền riêng cho DLT topic |
| Gửi output thường được nhưng transaction thất bại | Thiếu ACL trên transactional ID | Kiểm tra prefix/ID thực tế và quyền TransactionalId |
| Local chạy được, production lỗi | Principal, cluster ACL hoặc topic naming khác nhau | So sánh identity/resource theo environment, không copy ACL rộng |
| Health endpoint `UP` nhưng consumer không xử lý | Health check chỉ kiểm tra broker connectivity | Bổ sung readiness theo listener state/authorization |
| Pod restart liên tục | Liveness bị gắn với ACL failure | Giữ liveness cho process; phản ánh chức năng qua readiness |
| Retry authorization tạo log storm | Retry interval quá ngắn hoặc ACL chưa được sửa | Chọn interval, alert và phối hợp platform team |
| Thêm quyền `ALL` mới chạy | Quyền thiếu chưa được xác định | Thu hẹp ACL về principal/resource/operation tối thiểu |

## 19. Kịch bản kiểm thử authorization và readiness

Kiểm thử cần xác nhận cả **lỗi bị phát hiện** lẫn **ứng dụng phản ứng đúng**. Có thể dùng Kafka test cluster hỗ trợ ACL hoặc môi trường integration riêng có authorizer bật.

Các trường hợp nên có:

1. **Consumer đủ quyền:** principal đọc được topic và group, listener nhận record.
2. **Thiếu Topic READ:** xác nhận root cause là topic authorization và readiness phản ánh listener không thể xử lý.
3. **Thiếu Group READ:** consumer không tham gia group; phân biệt với thiếu topic permission.
4. **Producer thiếu DLT WRITE:** xử lý record lỗi, DLT publish thất bại, recovery không bị coi là hoàn tất.
5. **Thiếu transactional ID WRITE:** producer transaction thất bại với lỗi resource phù hợp.
6. **ACL được cấp khi app đang chạy:** nếu dùng `authExceptionRetryInterval`, xác nhận container thử lại theo interval và trở lại trạng thái sẵn sàng khi quyền có hiệu lực.
7. **Authentication sai:** xác nhận không nhầm `SaslAuthenticationException` với authorization và không retry vô hạn theo chính sách không phù hợp.
8. **Readiness và liveness:** ACL failure làm readiness xuống khi listener thiết yếu bị lỗi, nhưng không tạo liveness restart loop.
9. **Nhiều child consumers:** một child bị lỗi không bị child khác ghi đè trạng thái aggregate sai.
10. **Secret rotation:** client mới sử dụng credential mới mà không log lộ secret; kiểm tra behavior khi consumer được restart.
11. **Least privilege:** quyền được cấp đủ cho thao tác cần thiết nhưng không vô tình cho phép CREATE/ALTER/DELETE trên tài nguyên ngoài phạm vi.
12. **Recovery sau outage:** sau khi ACL được sửa, lag giảm, record được xử lý đúng và không có duplicate/mất offset.

Không chỉ mock một `AuthorizationException` trong unit test rồi kết luận ACL production đúng. Cần ít nhất một integration test với principal và authorizer tương ứng để xác nhận resource/operation thực sự.

## 20. Runbook khi consumer gặp authorization failure

1. **Xác định workload:** service, instance, listener ID, consumer group, topic và client ID.
2. **Lấy root exception:** phân biệt authorization, authentication, TLS và timeout.
3. **Xác định principal:** xác nhận broker nhìn thấy principal nào từ đúng consumer hoặc producer client.
4. **Xác định resource/operation:** Topic READ/WRITE, Group READ, TransactionalId WRITE hoặc cluster-level operation.
5. **Kiểm tra ACL/policy hiện tại:** resource pattern, host, ALLOW/DENY và environment.
6. **Kiểm tra readiness:** listener thiết yếu có thực sự hoạt động không; giữ process liveness độc lập với quyền Kafka.
7. **Cấp quyền tối thiểu qua platform control plane:** không cấp `ALL` để chữa cháy nếu chưa có phê duyệt/phân tích.
8. **Để container retry hoặc restart có kiểm soát:** dùng `authExceptionRetryInterval` nếu phù hợp với version và loại exception; không tạo restart storm.
9. **Xác nhận khôi phục:** listener đã join/fetch, DLT/producer send thành công nếu có, committed offset tiến và lag giảm.
10. **Ghi nhận nguyên nhân gốc:** ACL/resource bị thiếu, principal/config sai, thời gian phát hiện, ảnh hưởng dữ liệu và biện pháp ngăn tái diễn.

Nếu record đã được xử lý vào DB nhưng offset chưa commit trong lúc consumer dừng vì authorization failure, redelivery có thể xảy ra sau khi quyền được khôi phục. Đảm bảo side effect idempotent hoặc có inbox để tránh xử lý trùng. Nếu DLT publish thất bại, kiểm tra source offset và recovery state trước khi replay hoặc reset offsets.

## 21. Nguyên tắc production

1. Phân biệt **authentication** với **authorization** trước khi thay đổi secret hoặc ACL.
2. Xác định principal thực tế của từng consumer, producer, DLT publisher và transactional producer.
3. Cấp quyền theo resource/operation tối thiểu: Topic, Group, TransactionalId hoặc Cluster khi thật sự cần.
4. Kiểm tra cả topic nguồn lẫn consumer group; consumer có thể thiếu quyền ở một trong hai nơi.
5. DLT/retry/output topics cần quyền WRITE của đúng producer principal.
6. Kafka transaction cần ACL cho transactional ID; prefix duy nhất không thay thế quyền authorizer.
7. Dùng `authExceptionRetryInterval` khi loại exception/version hỗ trợ và khi quyền có thể được sửa lúc runtime; không coi nó là cách cấp quyền.
8. Giữ liveness phản ánh sức sống process; dùng readiness để thể hiện listener thiết yếu chưa thể xử lý workload.
9. Không xem broker connectivity hoặc generic admin health là bằng chứng consumer authorization thành công.
10. Không log credential; metrics tags phải cardinality thấp và không chứa raw exception message/secret.
11. Kiểm thử thiếu Topic/Group/DLT/TransactionalId ACL, readiness, retry và khôi phục trước khi triển khai.
12. Sau khi cấp quyền, xác minh listener assignment, record processing, DLT send, committed offsets và consumer lag.

**Kết luận:** authorization failure là lỗi quyền trên một resource cụ thể, không phải một trạng thái “Kafka down” chung chung. Trong Spring Kafka, xác định đúng principal, operation và resource giúp sửa ACL tối thiểu; `authExceptionRetryInterval` có thể hỗ trợ khôi phục trong những trường hợp được framework hỗ trợ. Readiness cần phản ánh khả năng xử lý thực tế của listener, trong khi liveness vẫn tập trung vào sức khỏe process. Khi log, metrics, ACL và recovery được liên kết đúng, đội vận hành có thể xử lý lỗi quyền mà không tạo restart storm, bỏ qua record hoặc che giấu thất bại publish DLT.
