# AuthenticationException

## 1. AuthenticationException là gì?

**AuthenticationException** là exception của Kafka client biểu thị rằng client không xác thực được với Kafka broker. Nó thường xuất hiện khi consumer hoặc producer cố thực hiện thao tác cần một kết nối được xác thực, nhưng broker không chấp nhận danh tính hoặc cơ chế xác thực mà client cung cấp.

Class nằm trong package:

~~~java
org.apache.kafka.common.errors.AuthenticationException
~~~

Một subclass thường gặp trong kết nối SASL là:

~~~java
org.apache.kafka.common.errors.SaslAuthenticationException
~~~

Ví dụ, service Order Fulfillment kết nối Kafka bằng SASL/SCRAM. Sau khi password bị rotate ở broker, pod cũ vẫn dùng credential trước đó. Khi Kafka client thực hiện authentication handshake, broker từ chối credential và client có thể ném AuthenticationException hoặc subclass tương ứng.

~~~text
Spring Kafka application
          |
          v
      Kafka client
          |
          | SASL/TLS authentication
          v
      Kafka broker
          |
     +----+---------------------+
     |                          |
 Credential hợp lệ       Credential không hợp lệ
     |                          |
     v                          v
Authenticated client      AuthenticationException
     |                          |
     v                          v
Kafka operations          Retry hoặc fail theo policy
~~~

Đây là lỗi ở **lớp bảo mật kết nối Kafka**. Nó khác với exception do business method xử lý record ném ra. Trong nhiều tình huống, listener chưa nhận được record nên không có message cụ thể để retry hoặc chuyển sang DLT.

## 2. Authentication trả lời câu hỏi nào?

Kafka security có hai bước khái niệm:

1. **Authentication:** client là ai?
2. **Authorization:** principal đã xác thực được phép làm gì?

Authentication thiết lập danh tính cho kết nối. Authorization kiểm tra quyền đối với resource như topic, consumer group, transactional ID hoặc cluster.

| Nội dung | Authentication | Authorization |
|---|---|---|
| Câu hỏi | Client là ai? | Client được phép làm gì? |
| Ví dụ lỗi | Password SCRAM sai | Principal thiếu READ trên topic |
| Exception điển hình | AuthenticationException | AuthorizationException |
| Cách sửa | Credential, SASL, TLS, principal mapping | ACL, resource, operation |
| Có thể sửa bằng cách thêm ACL? | Không | Có thể |
| Có thể sửa bằng cách rotate password? | Có thể | Không nếu quyền vẫn thiếu |

Một password đúng không tự cấp READ trên topic. Một ACL READ đúng cũng không làm cho client với password sai trở thành authenticated.

**Đừng phân loại mọi lỗi security thành AuthenticationException.** Phải đọc exception class và nguyên nhân gốc trước khi chọn remediation.

## 3. Vị trí của exception trong Kafka client

Kafka client có thể phải xác thực khi thiết lập kết nối hoặc khi thực hiện request tới broker. Quá trình này có thể xảy ra khi consumer lấy metadata, tham gia group, fetch records hoặc khi producer gửi record.

Một luồng consumer điển hình:

~~~text
KafkaListenerContainer starts
          |
          v
ConsumerFactory creates KafkaConsumer
          |
          v
Consumer subscribes to topic
          |
          v
KafkaConsumer.poll()
          |
          v
Kafka client communicates with broker
          |
          v
Authentication handshake
          |
     +----+--------------------+
     |                         |
    OK                       Rejected
     |                         |
     v                         v
Metadata/group/fetch     AuthenticationException
     |                         |
     v                         v
Listener receives       Container retry/stop policy
ConsumerRecord
~~~

Không phải mọi authentication failure đều xảy ra đúng tại thời điểm khởi tạo KafkaConsumer. Một số lỗi chỉ xuất hiện khi client bắt đầu gửi request tới broker. Vì vậy, log startup thành công chưa đủ chứng minh consumer đã xác thực và đọc được dữ liệu.

Ngược lại, lỗi xảy ra trước khi listener container được tạo, ví dụ cấu hình bean hoặc property không hợp lệ, có thể không đi qua đường xử lý AuthenticationException của poll loop.

## 4. Những nguyên nhân phổ biến

| Nhóm nguyên nhân | Ví dụ | Hướng kiểm tra |
|---|---|---|
| Credential sai | Username/password SCRAM không khớp | Secret version và broker principal |
| Credential hết hiệu lực | Password bị rotate hoặc account bị vô hiệu hóa | Quy trình rotation, trạng thái account |
| SASL mechanism sai | Client dùng SCRAM-SHA-256 nhưng listener broker chỉ cho SCRAM-SHA-512 | Broker listener và client config |
| JAAS sai | Login module hoặc option không đúng | sasl.jaas.config |
| TLS client identity | Certificate client hết hạn hoặc không được tin cậy | Certificate chain, validity, principal mapping |
| OAuth token | Token hết hạn, audience/issuer sai hoặc không được chấp nhận | Token provider, issuer, audience, clock |
| Kerberos | Ticket hết hạn, service principal sai hoặc keytab lỗi | KDC, principal, keytab, clock skew |
| Principal mapping | Broker tạo principal khác với ACL mong đợi | Broker security configuration |
| Broker security change | Listener hoặc authentication provider thay đổi | Broker deployment và audit logs |
| Secret injection lỗi | Pod nhận giá trị rỗng hoặc secret cũ | Mounted secret, environment và rollout |

Một số lỗi TLS, DNS, network hoặc cấu hình client có thể được biểu diễn bằng exception khác như SSLException, ConfigException hoặc KafkaException. Không nên mặc định mọi lỗi kết nối có chữ security đều là AuthenticationException.

## 5. Phân biệt AuthenticationException với AuthorizationException

Các exception authorization thường gặp:

~~~java
org.apache.kafka.common.errors.AuthorizationException
org.apache.kafka.common.errors.TopicAuthorizationException
org.apache.kafka.common.errors.GroupAuthorizationException
~~~

Tên subclass cụ thể phụ thuộc Kafka client version và thao tác bị từ chối.

Ví dụ:

~~~text
SASL authentication succeeds
          |
          v
Broker identifies principal:
User:orders-reader
          |
          v
Consumer requests READ on orders.created
          |
          v
ACL check
          |
     +----+----------------------+
     |                           |
   ALLOW                       DENY
     |                           |
     v                           v
Fetch records              AuthorizationException
~~~

Khi thấy AuthenticationException, kiểm tra danh tính và credential trước. Khi thấy AuthorizationException, kiểm tra principal, resource và operation bị từ chối.

Không sửa AuthenticationException bằng cách cấp quyền superuser. Không sửa AuthorizationException bằng cách thay password liên tục.

## 6. SASL là gì trong ngữ cảnh exception?

SASL là framework xác thực mà Kafka có thể sử dụng để kiểm tra danh tính client. Các mechanism thường gặp:

| Mechanism | Mô tả ngắn |
|---|---|
| PLAIN | Truyền username/password qua SASL; nên dùng với TLS để bảo vệ trên đường truyền |
| SCRAM-SHA-256 | Challenge-response dùng salted password với SHA-256 |
| SCRAM-SHA-512 | Challenge-response dùng salted password với SHA-512 |
| GSSAPI | Thường tích hợp Kerberos |
| OAUTHBEARER | Dùng OAuth bearer token |
| Mechanism tùy chỉnh | Phụ thuộc plugin và cấu hình broker |

Client và broker phải thống nhất mechanism cho listener kết nối. Một client cấu hình sai mechanism có thể không hoàn thành authentication handshake.

### 6.1. SASL_SSL và SASL_PLAINTEXT

- **SASL_SSL** kết hợp SASL authentication và TLS encryption.
- **SASL_PLAINTEXT** dùng SASL nhưng không mã hóa transport bằng TLS.

Trong môi trường production, nên dùng TLS theo security policy của tổ chức. PLAIN không có TLS có nguy cơ lộ credential trên network.

### 6.2. TLS và mutual TLS

Với mutual TLS, client trình certificate để broker xác thực danh tính. Truststore và keystore có vai trò khác nhau:

- Truststore chứa CA/certificate mà client tin cậy khi xác minh broker.
- Keystore chứa private key và certificate của client khi cần client authentication.

Certificate hết hạn, chain không hợp lệ hoặc principal mapping không đúng có thể làm handshake thất bại. Tuy nhiên, lỗi TLS không phải lúc nào cũng được biểu diễn thành Kafka AuthenticationException; hãy xem root cause thực tế.

## 7. Cấu hình SASL/SCRAM trong Spring Boot

Ví dụ cấu hình consumer:

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
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="<secret-injected-at-runtime>";'
~~~

Chuỗi password chỉ là placeholder. Trong production, lấy secret từ secret manager, Kubernetes Secret hoặc cơ chế injection được nền tảng quản lý. Không commit password vào source control.

Cấu hình tương ứng phía producer phải sử dụng danh tính được phép publish tới topic. Không mặc định consumer và producer nên dùng chung principal; tách principal giúp áp dụng least privilege.

### 7.1. Xác nhận client thực sự nhận được secret

Một ứng dụng có thể khởi động dù secret được inject sai vào runtime configuration, tùy thời điểm client tạo connection. Cần xác nhận:

- Secret key tồn tại.
- Giá trị không rỗng.
- Pod dùng đúng secret version.
- Environment/property binding trỏ đúng key.
- JAAS config được tạo đúng.
- ConsumerFactory dùng đúng security properties.
- Broker logs nhận đúng principal mong đợi.

Không log password hoặc toàn bộ JAAS string để debug.

## 8. Cấu hình SCRAM phía broker

Broker cần hỗ trợ mechanism mà client sử dụng và có credential cho principal đó. Quy trình quản lý SCRAM user phụ thuộc cách triển khai Kafka, broker version và công cụ quản trị.

Về mặt vận hành, cần xác nhận:

1. Listener broker bật SASL.
2. Mechanism SCRAM-SHA-512 được cho phép trên listener.
3. User orders-reader đã được provision.
4. Password tại broker khớp với secret mà ứng dụng sử dụng.
5. Các broker trong cluster có security configuration nhất quán.
6. Rotation đã được áp dụng đúng cluster/environment.

Đừng giả định thay đổi một broker là đã thay đổi toàn cluster. Với deployment có nhiều broker hoặc external identity provider, cần xác nhận trạng thái trên toàn bộ đường kết nối.

## 9. Cấu hình TLS và certificate

Một ví dụ client dùng SASL_SSL với truststore:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[ssl.truststore.location]": /var/run/kafka-secrets/truststore.p12
      "[ssl.truststore.type]": PKCS12
      "[ssl.truststore.password]": "<truststore-password-from-secret>"
~~~

Nếu dùng mutual TLS, cấu hình thêm keystore theo yêu cầu broker và client certificate policy. Password truststore/keystore là secrets, không đưa vào logs hoặc repository.

Kiểm tra certificate:

- Not Before và Not After.
- Subject/SAN phù hợp.
- Certificate chain tới CA được tin cậy.
- Key usage và extended key usage.
- Truststore có CA đúng.
- Clock của pod/node và broker không bị lệch đáng kể.
- Broker listener yêu cầu client certificate hay không.

Một certificate hết hạn có thể gây handshake error nhưng exception cụ thể phụ thuộc vị trí lỗi trong TLS stack và Kafka client version.

## 10. AuthenticationException phía consumer

Khi consumer gặp AuthenticationException trong hoạt động Kafka, listener có thể chưa nhận record nào từ broker.

Điều đó có nghĩa:

- Không có ConsumerRecord cụ thể để đưa qua DefaultErrorHandler.
- Không có record để chuyển DLT chỉ vì credential sai.
- Retry record không thể sửa username/password.
- Cần xử lý security connection và consumer container lifecycle.

Luồng minh họa:

~~~text
KafkaConsumer.poll()
       |
       v
AuthenticationException
       |
       v
No record delivered to listener
       |
       v
Container authentication retry policy
       |
       +--> Wait and retry
       |
       +--> Stop container when retry is disabled
~~~

Đây là lỗi ở tầng kết nối/bảo mật. Hãy tìm root cause trong Kafka client logs và broker authentication logs.

## 11. AuthenticationException phía producer

AuthenticationException cũng có thể xảy ra ở producer side. Khi KafkaTemplate gửi message, lỗi có thể được báo qua callback hoặc CompletableFuture tùy API được sử dụng.

Ví dụ:

~~~java
kafkaTemplate.send("orders.created", orderId, event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Kafka send failed", error);
            return;
        }

        log.debug(
            "Kafka send succeeded: topic={}, partition={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition()
        );
    });
~~~

Trong production, cần phân loại exception chain để xác định AuthenticationException, AuthorizationException, timeout hay lỗi serialization.

**authExceptionRetryInterval trên listener container chỉ điều khiển đường xử lý consumer container.** Nó không cấu hình retry cho KafkaTemplate producer. Producer cần retry/error handling phù hợp với producer API, delivery timeout, idempotence và business outbox policy.

Không coi một future hoàn tất thành công là business transaction đã hoàn tất nếu còn bước lưu trạng thái database hoặc publish event khác.

## 12. Spring Kafka xử lý AuthenticationException như thế nào?

Đối với listener container, Spring Kafka có property:

**authExceptionRetryInterval**

Property này quy định thời gian chờ trước khi retry khi KafkaConsumer ném AuthenticationException hoặc AuthorizationException trong các đường xử lý được hỗ trợ.

Nếu không cấu hình interval, behavior mặc định của container là dừng khi exception auth/authz tương ứng xảy ra. Khi cấu hình interval, container có thể tiếp tục retry thay vì stop ngay.

Ví dụ:

~~~java
factory.getContainerProperties()
    .setAuthExceptionRetryInterval(Duration.ofSeconds(30));
~~~

Khoảng retry phải nhỏ hơn **max.poll.interval.ms** của consumer. Hãy xác nhận property và behavior theo Spring Kafka version đang triển khai.

### 12.1. Retry interval không tự sửa credential

Giả sử password ở broker đã đổi nhưng pod vẫn dùng password cũ. Consumer retry sau 30 giây vẫn có thể dùng cùng credential cũ và tiếp tục thất bại.

Retry interval chỉ tạo cơ hội để điều kiện bên ngoài được sửa: secret mới được nạp, broker identity provider phục hồi hoặc cấu hình security được khắc phục.

Nếu client không hỗ trợ reload credential trong lúc chạy, cần tái tạo KafkaConsumer hoặc restart process theo deployment policy.

### 12.2. Không đặt interval sát max.poll.interval.ms

Ví dụ:

~~~text
max.poll.interval.ms          = 300000 ms
authExceptionRetryInterval    = 30000 ms
~~~

30 giây nhỏ hơn 5 phút, nhưng tổng thời gian giữa các poll còn phụ thuộc thời gian xử lý record, GC, network và các callback khác. Đừng đặt retry interval sát giới hạn chỉ vì phép so sánh đơn giản có vẻ hợp lệ.

## 13. ConsumerRetryAuthEvent và phục hồi

Khi auth exception được retry theo cấu hình, Spring Kafka ở các phiên bản hỗ trợ có thể phát:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthEvent
~~~

Event có reason để phân biệt:

~~~java
ConsumerRetryAuthEvent.Reason.AUTHENTICATION
ConsumerRetryAuthEvent.Reason.AUTHORIZATION
~~~

Sau khi một lần retry thành công, framework có thể phát:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthSuccessfulEvent
~~~

Observer có thể ghi log:

~~~java
@Component
public class KafkaAuthenticationObserver {

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        log.warn(
            "Kafka authentication retry: reason={}, listener={}",
            event.getReason(),
            event.getContainer()
        );
    }

    @EventListener
    public void onRecovered(ConsumerRetryAuthSuccessfulEvent event) {
        log.info(
            "Kafka authentication retry succeeded: source={}",
            event.getSource()
        );
    }
}
~~~

Event retry cho biết container đang thử lại; successful event cho biết retry auth đã thành công sau một lỗi trước đó. Không coi successful event là bằng chứng listener đã xử lý record hoặc consumer lag đã về 0.

Nếu retry interval không được cấu hình, container có thể đi theo nhánh stop và phát ConsumerStoppedEvent với reason liên quan AUTH ở các phiên bản hỗ trợ.

## 14. Phân biệt authentication error với record processing error

Một listener có thể ném exception khi xử lý dữ liệu:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Nếu process ném IllegalStateException vì database timeout, đây là **record processing failure**. Có thể dùng DefaultErrorHandler để retry record hoặc recover.

Nếu KafkaConsumer.poll ném AuthenticationException trước khi giao record, DefaultErrorHandler không có record nghiệp vụ để xử lý.

| Lỗi | Cơ chế phù hợp |
|---|---|
| AuthenticationException | Sửa credential/TLS/SASL; auth retry hoặc container lifecycle |
| AuthorizationException | Sửa ACL/principal/resource |
| Database timeout trong listener | DefaultErrorHandler/backoff hoặc business retry |
| JSON deserialization error | ErrorHandlingDeserializer và recovery policy |
| Poison record | Non-retryable classification hoặc DLT |
| Producer send authentication failure | Producer future/callback, security fix và delivery policy |

Không gửi message vào DLT chỉ vì consumer không đăng nhập được Kafka. Listener chưa nhận được message để thực hiện recovery.

## 15. ConsumerStoppedEvent khi auth thất bại

Nếu container dừng vì AuthenticationException hoặc AuthorizationException và auth retry interval không được cấu hình, Spring Kafka có thể phát **ConsumerStoppedEvent** với reason **AUTH** ở các phiên bản hỗ trợ.

Điều này khác với ConsumerRetryAuthEvent:

| Event | Ý nghĩa |
|---|---|
| ConsumerRetryAuthEvent | Container đang retry sau auth/authz error |
| ConsumerRetryAuthSuccessfulEvent | Retry auth đã thành công |
| ConsumerStoppedEvent | Consumer đã dừng |
| ConsumerStartedEvent | Consumer bắt đầu lifecycle |
| ConsumerPartitionAssignedEvent | Consumer được giao partition |

Nếu observer nhận ConsumerStoppedEvent, cần phân biệt operator stop, application shutdown và auth failure. Không auto-restart vô hạn khi root cause vẫn tồn tại.

## 16. Secret rotation và consumer lifecycle

Một vấn đề thực tế là password được nạp vào environment khi JVM khởi động. Sau khi secret manager cập nhật giá trị mới, process đang chạy có thể vẫn giữ giá trị cũ.

~~~text
Secret manager
     |
     v
Pod starts with password v1
     |
     v
KafkaConsumer uses v1
     |
     v
Broker rotates to password v2
     |
     v
Existing consumer authentication fails
     |
     v
Retry may still use v1
~~~

Các câu hỏi phải xác minh:

1. Secret volume có được cập nhật không?
2. Ứng dụng đọc secret mỗi lần tạo KafkaConsumer hay chỉ lúc startup?
3. ConsumerFactory có giữ security properties đã bind từ trước không?
4. Tái tạo KafkaConsumer có nạp giá trị mới không?
5. Có cần restart pod/JVM để refresh environment?
6. Có rolling restart để giữ đủ consumer capacity không?

**Restart listener container không tự thay đổi environment variable.** Nếu configuration chỉ được nạp khi process start, cần restart process hoặc có một cơ chế reload đã được thiết kế và kiểm thử.

### 16.1. Rolling rotation

Với nhiều consumer replicas:

~~~text
1. Provision new credential
2. Configure broker to accept new credential
3. Roll out application using new credential
4. Confirm all consumers authenticate
5. Revoke old credential after migration
~~~

Trình tự cụ thể phụ thuộc cơ chế SCRAM, identity provider và khả năng hỗ trợ đồng thời credential cũ/mới. Đừng thu hồi credential cũ trước khi các replicas đã chuyển sang credential mới nếu deployment yêu cầu chuyển đổi không gián đoạn.

## 17. OAuth bearer token

Với SASL/OAUTHBEARER, client cần token hợp lệ theo issuer, audience, signature, expiration và broker validation policy.

AuthenticationException có thể xuất hiện nếu token không được chấp nhận. Điều tra:

- Token có hết hạn không?
- Clock của client và issuer có lệch không?
- Audience và issuer có đúng không?
- JWKS/key rotation có được cập nhật không?
- Token callback/refresh handler có hoạt động không?
- Broker có xác minh token theo đúng trust configuration không?

Không log token để debug. Chỉ log token acquisition outcome, issuer alias hoặc error category đã được phê duyệt.

Nếu token provider không thể refresh, tăng auth retry interval không tự tạo token hợp lệ. Phải khôi phục token provider hoặc cấu hình OAuth.

## 18. Kerberos/GSSAPI

Với GSSAPI, authentication phụ thuộc Kerberos ticket, service principal, keytab và KDC.

Các nguyên nhân thường gặp:

- Ticket hết hạn.
- Keytab không khớp principal.
- Service principal name sai.
- DNS canonicalization không đúng.
- Clock skew giữa client và KDC.
- KDC không truy cập được.
- JAAS login module cấu hình sai.

Kiểm tra Kerberos bằng tooling của nền tảng và broker/client logs theo quy trình bảo mật. Không copy keytab hoặc ticket cache vào issue tracker.

Nếu credential renewal có thể thực hiện trong process, xác nhận Kafka client/SASL callback dùng cơ chế renewal đó. Nếu không, cần restart/recreate consumer theo đúng lifecycle.

## 19. TLS trust và client certificate

Lỗi TLS có thể xảy ra ở nhiều bước:

- Client không tin CA ký certificate của broker.
- Broker không tin CA của client certificate.
- Certificate hết hạn.
- Subject/SAN không khớp.
- Keystore/truststore password sai.
- Private key không khớp certificate.
- Protocol/cipher policy không tương thích.

Không phải mọi lỗi TLS đều được đóng gói thành AuthenticationException. Ví dụ một truststore không đọc được có thể lỗi ngay khi client khởi tạo, trong khi handshake failure có thể xuất hiện dưới SSLException hoặc KafkaException tùy nguyên nhân và version.

Đọc nested cause, không chỉ tên exception ngoài cùng.

## 20. Chẩn đoán từ logs và broker

Một log AuthenticationException hữu ích cần có:

- Timestamp.
- Service/pod/instance.
- Client ID và group ID nếu có.
- Broker endpoint.
- Security protocol và mechanism, không kèm secret.
- Exception class và nested cause.
- Listener ID hoặc producer identity.
- Secret/config version alias đã được phê duyệt.

Broker authentication logs có thể cho biết principal, listener và nguyên nhân từ chối. Dùng chúng để xác nhận broker thực sự nhận danh tính nào.

Không log SASL JAAS config nguyên bản, password, token, private key hoặc serialized security material.

### 20.1. Kiểm tra config hiệu lực

Một deployment có thể có nhiều nguồn cấu hình:

- application.yml.
- Environment variables.
- Kubernetes ConfigMap/Secret.
- Secret manager provider.
- Custom ConsumerFactory.
- Kafka client properties map.

Hãy xác định giá trị **hiệu lực** của security.protocol, sasl.mechanism, JAAS config và truststore/keystore path. Đừng giả định file YAML là nguồn cuối cùng nếu environment override nó.

## 21. Phân biệt exception ở startup và runtime

Có thể có hai nhóm lỗi:

**Startup/configuration failure:** application hoặc bean không thể tạo KafkaConsumer vì property sai, keystore không đọc được hoặc cấu hình không hợp lệ. Container có thể không start được; ConsumerFailedToStartEvent hoặc application startup failure có thể xuất hiện tùy lifecycle.

**Runtime authentication failure:** consumer đã chạy và Kafka client gặp AuthenticationException trong quá trình giao tiếp với broker. Khi auth retry được cấu hình, container có thể phát ConsumerRetryAuthEvent.

Property authExceptionRetryInterval không phải một cơ chế tổng quát để sửa mọi lỗi khởi tạo bean hoặc lỗi parse configuration. Cần xem thời điểm exception và stack trace.

## 22. Producer và consumer dùng principal riêng

Một kiến trúc least-privilege có thể dùng:

| Principal | Quyền dự kiến |
|---|---|
| User:orders-api | WRITE trên orders.created |
| User:orders-reader | READ trên orders.created và READ trên group order-fulfillment |
| User:orders-dlt-reader | READ trên orders.created.DLT và group DLT riêng |
| User:kafka-admin | Quyền quản trị theo policy, không dùng runtime |

Nếu cùng một principal được chia sẻ giữa mọi services, một credential bị lộ có thể tạo phạm vi ảnh hưởng lớn hơn.

AuthenticationException cho biết client không xác thực được danh tính. Khi xác thực thành công, broker vẫn áp dụng ACL riêng cho từng principal/resource.

## 23. Backoff và retry policy

Nếu dùng authExceptionRetryInterval, chọn interval theo:

- Thời gian thường cần để sửa credential/ACL.
- max.poll.interval.ms.
- Consumer group SLO.
- Tốc độ tăng consumer lag.
- Số replicas cùng gặp lỗi.
- Broker authentication capacity.
- Quy trình alert/escalation.

Không đặt interval quá ngắn khiến tất cả consumer retry cùng lúc, gây connection/authentication storm. Có thể cân nhắc jitter ở lớp automation bên ngoài nếu policy cho phép; không tự giả định framework interval có jitter.

Nếu credential sai cố định, retry vô hạn chỉ tạo log noise và giữ hệ thống ở trạng thái degraded. Cần alert theo thời gian outage và restart budget.

## 24. Vì sao restart không tự sửa AuthenticationException?

Restart container có thể tạo KafkaConsumer mới, nhưng nếu ConsumerFactory vẫn dùng cùng password sai thì consumer mới cũng sẽ thất bại.

~~~text
Container A
  credential v1
  authentication fails
       |
       v
stop/start
       |
       v
Container B
  credential v1
  authentication fails again
~~~

Restart chỉ hữu ích nếu nó thực sự nạp cấu hình mới hoặc khởi tạo lại client sau khi root cause đã được sửa.

Trước khi restart:

1. Xác định principal và nguyên nhân.
2. Sửa credential, certificate hoặc broker configuration.
3. Xác nhận consumer factory sẽ sử dụng giá trị mới.
4. Chọn restart container hay pod dựa trên cách nạp config.
5. Dừng hoàn tất trước khi start lại.
6. Xác nhận consumer join group và nhận partition.

Không reset offsets chỉ để xử lý authentication failure. Offset là vị trí dữ liệu, không phải credential.

## 25. AuthenticationException và transactions

Với producer transaction hoặc consume-transform-produce, authentication failure có thể ngăn producer init transaction hoặc consumer fetch dữ liệu.

Nếu transaction chưa bắt đầu/commit, lỗi authentication không tạo ra một transaction outcome thành công. Khi kết nối được phục hồi, cần xác nhận transaction manager và producer factory hoạt động lại.

Đối với transactional producer, kiểm tra thêm:

- Transactional ID prefix.
- Principal có quyền cần thiết trên transactional ID.
- Broker transaction coordinator.
- Producer fencing có xảy ra độc lập với authentication hay không.

**ProducerFencedException không phải AuthenticationException.** Hai lỗi cần root-cause analysis riêng.

Nếu consumer đã thực hiện side effect ngoài Kafka trước khi lỗi kết nối hoặc process dừng, side effect đó không tự rollback theo Kafka transaction. Dùng idempotency hoặc outbox/inbox phù hợp.

## 26. Integration test AuthenticationException

Một test hữu ích nên dùng Kafka broker test có SASL authentication thực, chẳng hạn Testcontainers image/cấu hình được dự án hỗ trợ.

Kịch bản tổng quát:

1. Khởi tạo broker với SASL mechanism đã chọn.
2. Provision principal consumer và credential test.
3. Khởi động Spring Kafka listener với security properties hợp lệ.
4. Xác nhận listener nhận được record mẫu.
5. Thay đổi credential hoặc tạo một client với credential sai trong môi trường test.
6. Xác nhận client gặp AuthenticationException hoặc subclass thực tế.
7. Nếu kiểm tra Spring auth retry, cấu hình authExceptionRetryInterval ngắn hơn max.poll.interval.ms.
8. Thu thập ConsumerRetryAuthEvent khi version hỗ trợ.
9. Khôi phục điều kiện authentication.
10. Đợi ConsumerRetryAuthSuccessfulEvent nếu đường retry được hỗ trợ và client có thể phục hồi.
11. Xác nhận consumer tiếp tục poll và xử lý record.
12. Dọn credentials và resources của test.

Không dùng broker giả chỉ ném một exception tùy ý rồi kết luận SASL/TLS authentication hoạt động end-to-end. Unit test exception classification hữu ích nhưng không thay thế integration test với broker security.

### 26.1. Test fail-fast

Một test khác không cấu hình authExceptionRetryInterval:

- Gây authentication failure.
- Quan sát container stop theo behavior của Spring Kafka version.
- Kiểm tra ConsumerStoppedEvent reason AUTH nếu API/version hỗ trợ.
- Sửa credential.
- Restart container có kiểm soát.
- Xác nhận listener xử lý record tiếp theo.

## 27. Monitoring và alert

| Tín hiệu | Ý nghĩa |
|---|---|
| AuthenticationException count | Tần suất lỗi xác thực |
| SaslAuthenticationException count | Lỗi liên quan SASL |
| ConsumerRetryAuthEvent reason AUTHENTICATION | Container đang retry authentication |
| ConsumerRetryAuthSuccessfulEvent | Retry auth đã phục hồi |
| ConsumerStoppedEvent reason AUTH | Consumer dừng do auth/authz theo version |
| ConsumerFailedToStartEvent | Consumer không start được |
| Broker auth failure logs | Principal/listener bị từ chối |
| Secret rotation version | Credential nào đang được dùng |
| Consumer lag | Ảnh hưởng tới tiến độ dữ liệu |
| Connection/reconnect metrics | Khả năng giao tiếp với broker |

Alert nên gom nhiều retry events thành một incident kéo dài, không tạo một page cho mỗi event.

Ví dụ điều kiện alert:

- Authentication failure kéo dài quá ngưỡng SLO.
- Nhiều replicas cùng gặp lỗi ngay sau secret rotation.
- Consumer lag tăng trong lúc retry.
- ConsumerStoppedEvent reason AUTH xuất hiện ở listener quan trọng.
- Không có successful retry sau khi secret đã được rollout.

## 28. Runbook production

Khi gặp AuthenticationException:

1. Ghi nhận timestamp, service, pod, client ID và listener/group nếu có.
2. Đọc exception class và toàn bộ nested cause.
3. Xác định thao tác thất bại ở consumer hay producer.
4. Kiểm tra security.protocol và sasl.mechanism hiệu lực.
5. Với SCRAM/PLAIN, xác nhận username, password và broker credential.
6. Với OAuth, kiểm tra token issuer, audience, expiration và refresh.
7. Với Kerberos, kiểm tra ticket, principal, keytab, KDC và clock.
8. Với TLS, kiểm tra truststore, certificate chain, expiry và client identity.
9. Đối chiếu broker authentication logs.
10. Phân biệt AuthenticationException với AuthorizationException.
11. Kiểm tra secret/config version thực sự được process sử dụng.
12. Nếu consumer container retry, theo dõi ConsumerRetryAuthEvent và lag.
13. Nếu container đã stop, sửa root cause trước khi restart.
14. Nếu secret chỉ được nạp lúc JVM start, thực hiện rolling pod restart phù hợp.
15. Xác nhận consumer join group và nhận partition.
16. Xác nhận listener xử lý record và offset tiến.
17. Kiểm tra duplicate side effects nếu record chưa commit được giao lại.
18. Ghi root cause và cập nhật quy trình credential rotation.

Không reset offsets, cấp superuser hoặc restart vô hạn chỉ để làm biến mất exception.

## 29. Những sai lầm thường gặp

**AuthenticationException có nghĩa principal thiếu READ trên topic.** Không đúng; đó là authorization.

**Thêm ACL sẽ sửa password sai.** Không đúng; phải sửa credential hoặc authentication configuration.

**DefaultErrorHandler retry được AuthenticationException từ poll.** Không đúng; error handler xử lý record listener failures, còn auth exception có thể xảy ra trước khi record được giao.

**DLT là nơi gửi message khi consumer không đăng nhập được.** Không đúng; consumer chưa nhận record để recover.

**authExceptionRetryInterval tự refresh password.** Không đúng; nó chỉ điều khiển thời gian retry.

**Restart listener container luôn nạp secret mới.** Không đúng nếu secret được bind vào environment lúc JVM startup.

**Mọi TLS error đều là AuthenticationException.** Không đúng; xem exception và nested cause thực tế.

**Producer cũng được điều khiển bởi authExceptionRetryInterval.** Không đúng; property thuộc listener container.

**Authentication thành công nghĩa là có quyền đọc topic.** Không đúng; broker còn kiểm tra ACL.

**Consumer retry thành công nghĩa là lag bằng zero.** Không đúng; cần xác nhận assignment, processing và commit.

**Log full JAAS string để tìm password sai.** Không an toàn; JAAS có thể chứa secret.

**Tăng retry vô hạn sẽ giải quyết credential hết hạn.** Không đúng; credential phải được khôi phục.

## 30. Checklist triển khai

- [ ] Xác định đúng Kafka AuthenticationException và nested cause.
- [ ] Phân biệt authentication với authorization.
- [ ] Xác định lỗi ở consumer, producer hay startup.
- [ ] Kiểm tra security.protocol và SASL mechanism.
- [ ] Quản lý username/password qua secret provider.
- [ ] Kiểm tra OAuth/Kerberos/TLS nếu được sử dụng.
- [ ] Không log JAAS, password, token hoặc private key.
- [ ] Cấu hình authExceptionRetryInterval có chủ đích cho listener container.
- [ ] Retry interval nhỏ hơn max.poll.interval.ms.
- [ ] Quan sát ConsumerRetryAuthEvent và successful event khi version hỗ trợ.
- [ ] Có policy cho container stop với reason AUTH.
- [ ] Không dùng DefaultErrorHandler/DLT cho lỗi kết nối auth trước khi nhận record.
- [ ] Có quy trình secret rotation và xác minh reload.
- [ ] Dùng principal riêng và least-privilege ACL.
- [ ] Test authentication failure với broker bảo mật thật.
- [ ] Xác minh group assignment, processing và offset sau phục hồi.

## 31. Ghi nhớ

**AuthenticationException** là exception của Kafka client cho biết client không xác thực được với broker. Nguyên nhân thường nằm ở credential, SASL mechanism, JAAS, OAuth token, Kerberos hoặc TLS client identity. Nó khác với **AuthorizationException**, vốn xảy ra khi principal đã được xác thực nhưng thiếu quyền trên resource.

Ở Spring Kafka consumer, **authExceptionRetryInterval** có thể cho container chờ và retry khi KafkaConsumer ném AuthenticationException hoặc AuthorizationException trong các đường xử lý được hỗ trợ. Nếu không cấu hình, container có thể stop. Retry interval không tự sửa credential và không thay thế việc quản lý secret. Producer-side AuthenticationException cần xử lý qua producer future/callback và delivery policy riêng.

Khi khắc phục, hãy đọc nested cause và broker logs, xác minh security configuration hiệu lực, sửa credential/certificate hoặc identity provider, rồi chọn restart container hay pod theo cách ứng dụng nạp secret. Sau khi authentication phục hồi, xác nhận consumer join group, nhận partition, xử lý record và commit offset; bảo vệ side effects trước khả năng redelivery bằng idempotency.

