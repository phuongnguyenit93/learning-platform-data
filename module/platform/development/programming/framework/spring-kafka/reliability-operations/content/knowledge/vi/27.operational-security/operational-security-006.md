# ACL cho consumer trong Spring Kafka

Trong Kafka, một consumer phải chứng minh được **mình là principal nào** và phải được broker cho phép thực hiện **những operation nào**. Hai việc này khác nhau: SASL hoặc TLS xác thực danh tính; Kafka ACL quyết định principal đó có được đọc topic, tham gia consumer group và commit offsets hay không.

Với một Spring Kafka service thông thường dùng `@KafkaListener`, quyền tối thiểu cần xem xét thường nằm trên hai loại resource:

- **TOPIC**: principal cần quyền `READ` trên các topic mà consumer đọc.
- **GROUP**: principal cần quyền `READ` trên consumer group mà ứng dụng tham gia.

Nếu chỉ cấp quyền đọc topic nhưng quên quyền cho group, consumer có thể xác thực thành công và nhìn thấy topic metadata nhưng không thể tham gia group hoặc commit offsets như mong đợi. Nếu chỉ cấp quyền group mà thiếu quyền topic, consumer không thể đọc dữ liệu từ topic.

Bài học này trình bày cách thiết kế ACL theo least privilege, xác định đúng principal và group ID trong Spring Boot, cấu hình SASL/TLS, cấp và thu hồi ACL bằng `kafka-acls.sh`, xử lý topic subscriptions, kiểm tra lỗi authorization và xây integration tests.

## 1. Authentication và authorization là hai bước khác nhau

Một kết nối consumer đi qua hai câu hỏi:

1. **Authentication:** client kết nối với Kafka bằng danh tính nào?
2. **Authorization:** danh tính đó có quyền thực hiện request trên resource tương ứng không?

```text
Spring Kafka application
       |
       v
TLS / SASL authentication
       |
       v
Kafka xác định principal
       |
       v
Kafka authorizer kiểm tra ACL
       |
       +-- ALLOW --> request được thực hiện
       |
       +-- DENY  --> authorization exception
```

Ví dụ:

- Consumer dùng SASL/SCRAM với username `billing-consumer`.
- Broker xác định principal là `User:billing-consumer`.
- ACL cho phép principal đọc topic `orders.created`.
- ACL cho phép principal sử dụng group `billing-service`.
- Consumer có thể đọc và commit offsets theo quyền đã cấp.

Một SASL login thành công **không tự động cấp quyền đọc topic**. Ngược lại, một ACL cho `User:billing-consumer` không giúp ích nếu client không thể xác thực thành principal đó.

### 1.1. Các khái niệm cần phân biệt

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Username / certificate identity | `billing-consumer` | Thông tin dùng xác thực |
| Kafka principal | `User:billing-consumer` | Danh tính broker dùng trong ACL |
| Client ID | `billing-consumer-1` | Nhận diện client cho logs/metrics/quota |
| Consumer group ID | `billing-service` | Tên group dùng coordination và offset tracking |
| Topic | `orders.created` | Resource chứa record |
| ACL | Allow READ cho principal trên resource | Quyết định quyền truy cập |

**Client ID không phải consumer group ID và cũng không phải principal.** Đặt `client.id=billing-service` không tự cấp quyền group `billing-service`.

### 1.2. Principal có thể khác username

Với SASL/SCRAM, principal thường dựa trên username đã xác thực, ví dụ `User:billing-consumer`. Với TLS client authentication, principal có thể được tạo từ distinguished name của certificate, ví dụ `User:CN=billing-consumer,OU=Services,O=Example`.

Kerberos/GSSAPI có thể tạo principal theo dạng `User:service/host@REALM`, tùy principal builder và mapping rules.

Khi cấp ACL, phải dùng **principal mà broker thực sự nhìn thấy**, không suy đoán từ tên pod, Spring bean hoặc application name. Có thể xác minh qua broker authentication/authorizer logs và cấu hình principal mapping.

## 2. Vì sao consumer cần ACL trên cả topic và group?

Consumer group có hai phạm vi authorization riêng:

- Đọc record thuộc topic.
- Tham gia/hoạt động trong group, bao gồm coordination và quản lý committed offsets.

Ví dụ một listener:

```java
@KafkaListener(
    id = "billing-listener",
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(OrderCreated event) {
    billingService.process(event);
}
```

Kafka broker cần kiểm tra quyền tương ứng với:

```text
Principal: User:billing-consumer

TOPIC resource:
  orders.created
  operation: READ

GROUP resource:
  billing-service
  operation: READ
```

Trong Kafka ACL model, quyền `READ` trên topic là quyền chính để fetch records. Với StandardAuthorizer, `READ` cũng bao hàm khả năng `DESCRIBE` tương ứng theo quy tắc operation implication. Một số thao tác quản trị/metadata độc lập có thể cần quyền `DESCRIBE` được cấp tường minh.

Quyền `READ` trên group cho phép consumer sử dụng group resource cho các hoạt động coordination và offset liên quan. Không nhầm `READ` trên topic với `READ` trên group: đây là hai ACL trên hai resource khác nhau.

### 2.1. Ma trận quyền tối thiểu thông dụng

| Resource type | Resource name | Operation | Mục đích |
|---|---|---|---|
| TOPIC | `orders.created` | READ | Fetch records từ topic |
| GROUP | `billing-service` | READ | Join/coordinate consumer group và offset operations |
| TOPIC | `orders.updated` | READ | Chỉ khi listener thực sự đọc topic này |
| GROUP | `billing-replay` | READ | Chỉ khi ứng dụng sử dụng group ID này |

Với consumer subscribe theo group, đây là điểm xuất phát tốt cho least privilege. Quyền bổ sung chỉ nên được cấp khi một API hoặc workflow thực tế cần đến.

### 2.2. Thiếu topic ACL

Nếu principal có quyền group nhưng không có quyền đọc topic, consumer có thể gặp `TopicAuthorizationException` khi fetch/metadata access cần authorization. Log có thể nêu topic cụ thể bị từ chối.

Không cấp quyền `READ` trên mọi topic chỉ để xử lý một lỗi của `orders.created`.

### 2.3. Thiếu group ACL

Nếu principal đọc được topic nhưng không được phép sử dụng group, consumer có thể gặp `GroupAuthorizationException` trong quá trình join group, heartbeat/coordination hoặc offset operations tùy request.

Một số biểu hiện có thể là listener không nhận record, join group thất bại hoặc commit offset bị từ chối. Cần đọc exception và broker authorizer logs để biết resource bị từ chối là group nào.

### 2.4. Consumer không dùng group

Nếu consumer dùng `assign()` để tự gán partition thay vì `subscribe()`, nó không tham gia group coordination theo cùng cách. Nhưng nếu vẫn commit offsets dưới một group ID, thao tác offset vẫn gắn với group resource và authorization cần được đánh giá tương ứng.

Trong ứng dụng Spring Kafka dùng `@KafkaListener` với `groupId` và subscription thông thường, hãy cấp quyền group như ma trận trên.

## 3. Kafka ACL model: resource, operation, principal và host

Một ACL entry được xác định bởi nhiều thành phần:

- **Principal:** danh tính được phép hoặc bị từ chối.
- **Host:** địa chỉ client mà ACL áp dụng, thường là `*` nếu không giới hạn host.
- **Operation:** READ, WRITE, DESCRIBE, CREATE, DELETE, ALTER...
- **Permission type:** ALLOW hoặc DENY.
- **Resource type/name:** TOPIC, GROUP, CLUSTER, TRANSACTIONAL_ID...
- **Pattern type:** literal, prefixed hoặc wildcard theo ACL model.

Ví dụ:

```text
ALLOW User:billing-consumer
  HOST *
  READ
  TOPIC orders.created
  LITERAL
```

Entry trên cho phép principal đọc topic cụ thể từ mọi host phù hợp với wildcard host.

### 3.1. Literal resource pattern

Literal là lựa chọn tốt khi ứng dụng chỉ cần một tập topic/group xác định.

Ví dụ:

```text
TOPIC orders.created (literal)
GROUP billing-service (literal)
```

Nếu service chỉ consume `orders.created` và dùng group `billing-service`, literal ACL giới hạn phạm vi rõ ràng.

### 3.2. Prefixed resource pattern

Một ACL có pattern `PREFIXED` áp dụng cho resource names bắt đầu bằng prefix đã chỉ định.

Ví dụ:

```text
TOPIC orders. (prefixed)
GROUP billing- (prefixed)
```

Điều này có thể hữu ích khi service consume nhiều topic theo quy ước tên. Nhưng prefix quá rộng như `orders` có thể cho phép đọc cả topic không thuộc workload.

Đối với group prefix, hãy cân nhắc liệu ứng dụng có thực sự cần nhiều group IDs hay chỉ có một group ID cố định. Nếu chỉ một group, literal dễ audit hơn.

### 3.3. Wildcard resource

Wildcard resource pattern có thể áp dụng trên phạm vi rất rộng. Dùng `--topic '*'` hoặc resource wildcard cho principal của ứng dụng có thể vô tình cấp quyền đọc dữ liệu ngoài phạm vi nghiệp vụ.

Không dùng wildcard làm giải pháp nhanh trong production nếu chưa có đánh giá phạm vi dữ liệu và phê duyệt bảo mật.

### 3.4. Host restriction

ACL có thể giới hạn host client. Trong môi trường Kubernetes, pod IP có thể thay đổi qua rollout/autoscaling; ràng buộc host theo IP tĩnh có thể làm consumer đột ngột mất quyền sau deployment.

Nếu dùng host `*`, hãy bù bằng principal riêng cho service, TLS/SASL, network controls và ACL resource hẹp. Host wildcard không có nghĩa mọi người dùng đều được phép; principal vẫn phải match.

## 4. Least privilege cho consumer

Một consumer chỉ nên được cấp quyền cần thiết cho chức năng cụ thể.

Ví dụ:

```text
billing-service:
  principal: User:billing-consumer
  topics:
    - orders.created
    - orders.updated
  groups:
    - billing-service
  operations:
    - READ on those topics
    - READ on that group
```

Consumer không cần những quyền sau chỉ để đọc topic theo group:

- `WRITE` trên topic nguồn.
- `CREATE` hoặc `DELETE` topic.
- `ALTER` topic configuration.
- `CLUSTER_ACTION`.
- `ALTER_CONFIGS` hoặc `DESCRIBE_CONFIGS` cho cluster/topic.
- `WRITE` trên group.
- `READ` trên mọi group hoặc mọi topic.

Một consumer có thể cần quyền khác nếu nó cũng publish output, tạo topics, gọi AdminClient hoặc sử dụng Kafka transactions. Khi đó hãy phân tách các vai trò hoặc cấp quyền bổ sung đúng resource.

### 4.1. Tách principal theo service

Không nên dùng một principal dùng chung cho tất cả applications:

```text
User:shared-application
  -> orders-service
  -> billing-service
  -> analytics-service
```

Nếu principal dùng chung có quyền đọc mọi topic, một service bị compromise có thể truy cập dữ liệu của các service khác. Principal riêng giúp thu hẹp blast radius và truy vết audit.

Ví dụ:

```text
User:orders-consumer
User:billing-consumer
User:analytics-consumer
```

Mỗi principal có topic/group ACL riêng.

### 4.2. Read-only consumer

Một consumer thuần đọc không cần quyền ghi topic. Nếu cùng service có cả consumer và producer, cân nhắc dùng principal riêng cho producer và consumer khi môi trường yêu cầu phân quyền rõ.

Nếu dùng chung principal, ACL phải bao gồm cả quyền producer cần thiết; điều đó làm tăng phạm vi quyền của consumer process.

### 4.3. Không cấp quyền quản trị cho runtime consumer

Runtime service không nên chạy bằng admin principal chỉ để tránh lỗi ACL. Admin credentials thường có quyền rộng, làm tăng tác động khi secret bị lộ hoặc ứng dụng bị khai thác.

Dùng một principal quản trị riêng cho provisioning/ACL changes và một principal runtime có quyền tối thiểu.

## 5. Cấp ACL bằng kafka-acls.sh

Công cụ `kafka-acls.sh` cho phép quản trị ACL qua Kafka Admin API. Ví dụ dưới đây giả định broker đã bật authorizer và người chạy lệnh có quyền quản trị ACL.

Tạo file cấu hình kết nối quản trị riêng, ví dụ `admin.properties`, với bootstrap servers và cơ chế xác thực phù hợp. Không đưa mật khẩu thật vào source control hoặc lệnh shell lưu trong lịch sử.

### 5.1. Cấp quyền READ trên topic

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.created
```

ACL này cấp quyền READ cho principal trên topic literal `orders.created`. Với StandardAuthorizer, READ bao hàm DESCRIBE theo operation implication.

Nếu policy nội bộ yêu cầu ACL DESCRIBE tường minh hoặc có client/admin operation riêng cần mô tả topic, có thể cấp riêng:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Describe \
  --topic orders.created
```

Không thêm quyền DESCRIBE_CONFIGS chỉ vì consumer cần đọc records; đây là quyền đọc cấu hình resource và có mục đích khác.

### 5.2. Cấp quyền READ trên consumer group

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --group billing-service
```

Resource `GROUP` ở đây phải khớp với group ID mà consumer thực sự dùng. Với ví dụ listener:

```java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(OrderCreated event) {
    // ...
}
```

group resource là `billing-service`.

### 5.3. Cấp quyền cho nhiều topic

Nếu service đọc thêm topic `orders.updated`, cấp ACL riêng:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.updated
```

Không cấp quyền topic `orders.*` bằng wildcard nếu ứng dụng chỉ cần hai topics cố định.

### 5.4. Xem ACL hiện có

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.created
```

Xem ACL của group:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --group billing-service
```

Có thể xem toàn bộ ACL bằng `--list`, nhưng trong cluster lớn nên lọc theo resource để kết quả dễ kiểm tra.

### 5.5. Thu hồi ACL

Khi service ngừng sử dụng topic:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.created
```

Thu hồi group ACL riêng nếu group không còn được dùng:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --group billing-service
```

Thao tác remove cần khớp chính xác principal, operation, resource pattern và host của ACL cần xóa. Kiểm tra kết quả `--list` sau khi thay đổi.

## 6. Prefixed ACL cho topic subscriptions

Một listener có thể subscribe nhiều topic bằng pattern hoặc regex. Khi đó cần hiểu **những topic nào thực sự được subscribe** và ACL có bao phủ tất cả không.

Ví dụ listener:

```java
@KafkaListener(
    id = "orders-listener",
    topicPattern = "orders\\.events\\..*",
    groupId = "billing-service"
)
public void consume(String payload) {
    // ...
}
```

Nếu topic names tuân theo prefix `orders.events.`, có thể cân nhắc prefixed ACL:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.events. \
  --resource-pattern-type prefixed
```

Group vẫn cần ACL riêng:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --group billing-service
```

### 6.1. Prefix quá rộng có thể mở rộng quyền ngoài dự kiến

Ví dụ prefix `orders.` có thể bao gồm:

```text
orders.events.created
orders.events.updated
orders.internal.audit
orders.admin.commands
orders.private.customer-data
```

Nếu service chỉ cần `orders.events.*`, prefix hẹp `orders.events.` an toàn hơn. Với topic có naming convention không ổn định, dùng ACL literal cho danh sách topic được phê duyệt.

### 6.2. Regex subscription không tự cấp quyền

`topicPattern` chỉ quyết định client subscribe theo pattern. Nó không tự tạo ACL và không làm broker bỏ qua authorization.

Khi một topic mới match pattern được tạo, consumer principal vẫn cần quyền đọc resource đó. Prefixed ACL có thể giúp topic mới trong prefix được đọc mà không phải cấp từng ACL, nhưng phải được thiết kế có chủ đích.

### 6.3. Group ID động

Nếu group ID thay đổi theo môi trường hoặc instance, literal group ACL có thể không match. Đừng dùng group prefix rộng để chữa lỗi ngay. Trước hết xác định group ID thực tế qua config/logs; sau đó quyết định literal hay prefix.

Thông thường các replicas của cùng một logical service nên dùng **cùng group ID**, không phải group ID chứa pod name, để chia partition và cân bằng tải. Nếu mỗi pod dùng group ID riêng, mỗi pod có thể nhận toàn bộ stream độc lập và cần ACL riêng cho từng group.

## 7. DENY ACL và thứ tự quyền

Kafka ACL có permission type ALLOW và DENY. Khi một request khớp với một DENY ACL, quyền bị từ chối theo quy tắc authorizer; không nên giả định một ALLOW rộng hơn sẽ ghi đè DENY.

Ví dụ:

```text
ALLOW User:billing-consumer READ TOPIC orders.
DENY  User:billing-consumer READ TOPIC orders.created
```

Nếu cả hai ACL cùng match theo resource pattern/host/operation, DENY có thể khiến consumer không đọc được `orders.created`.

### 7.1. Kiểm tra ACL hiệu lực, không chỉ ACL mong muốn

Khi consumer nhận authorization error:

1. Liệt kê ACL trên topic cụ thể.
2. Liệt kê ACL trên group cụ thể.
3. Kiểm tra resource pattern literal/prefixed/wildcard.
4. Kiểm tra principal thực tế sau authentication/mapping.
5. Kiểm tra host condition.
6. Kiểm tra DENY entries có match không.
7. Kiểm tra `super.users` và policy của authorizer nếu có.
8. Xem broker logs để biết resource/operation bị từ chối.

Một ACL ALLOW tồn tại không chứng minh request sẽ được phép nếu có DENY phù hợp hoặc principal/host không match.

### 7.2. Tránh wildcard principal

ACL cho `User:*` hoặc principal rộng làm suy yếu khả năng cô lập service. Dùng principal riêng và resource hẹp. Với DENY, đặc biệt cẩn thận vì một entry rộng có thể làm gián đoạn nhiều workloads.

## 8. Bật authorizer trên Kafka broker

ACL chỉ có tác dụng khi broker dùng authorizer tương ứng. Cấu hình phụ thuộc Kafka deployment mode và version.

Với Kafka chạy KRaft ở các phiên bản hiện đại, authorizer phổ biến là:

```properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
```

Với một số deployment ZooKeeper/phiên bản cũ, authorizer có thể là:

```properties
authorizer.class.name=kafka.security.authorizer.AclAuthorizer
```

Đây là cấu hình phía broker, không phải cấu hình trong Spring Boot consumer. Không copy authorizer class của một mode/version sang deployment khác mà chưa đối chiếu tài liệu Kafka đang chạy.

### 8.1. Default deny và ACL bootstrap

Khi authorizer bật, các request cần authorization sẽ được kiểm tra. Nếu không có ACL ALLOW phù hợp và không có ngoại lệ theo cấu hình, request bị từ chối.

Cần chuẩn bị:

- Principal quản trị có quyền tạo/list/remove ACL.
- `super.users` nếu policy triển khai cần superuser identities.
- ACL cho runtime services.
- Quy trình bootstrap để admin không tự khóa quyền quản trị.
- Audit trail cho thay đổi ACL.

Không bật authorizer trên production trước khi có đường truy cập quản trị và ACL bootstrap đã được kiểm chứng. Cấu hình sai có thể làm broker từ chối cả thao tác quản trị cần thiết.

### 8.2. allow.everyone.if.no.acl.found

Một số authorizer/configuration có tùy chọn `allow.everyone.if.no.acl.found`. Nếu bật, resource không có ACL có thể được xử lý theo policy cho phép rộng hơn.

Đây không phải giải pháp thay thế cho việc cấp ACL đúng. Cần hiểu chính xác default behavior của authorizer/version và policy bảo mật của cluster. Trong môi trường yêu cầu least privilege, tránh cấu hình “không có ACL thì cho tất cả” nếu không có quyết định bảo mật rõ ràng.

### 8.3. KRaft và ZooKeeper khác nhau

Kafka KRaft và ZooKeeper-based clusters có lịch sử authorizer/configuration khác nhau. KRaft sử dụng metadata quorum cho metadata/ACL storage; ZooKeeper deployments cũ có cơ chế tương ứng của version đó.

Lệnh `kafka-acls.sh --bootstrap-server` là đường quản trị hiện đại thường được ưu tiên, nhưng flags, authorizer behavior và bootstrap requirements vẫn phải kiểm tra theo version/distribution.

## 9. Cấu hình Spring Boot consumer với SASL/SCRAM và TLS

ACL xác định quyền, nhưng client vẫn cần xác thực. Ví dụ một consumer dùng SASL_SSL và SCRAM-SHA-512:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9093,kafka-2.internal:9093
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.billing.events
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="billing-consumer" password="${KAFKA_CONSUMER_PASSWORD}";
      ssl.endpoint.identification.algorithm: https
~~~

Đây là ví dụ minh họa. `KAFKA_CONSUMER_PASSWORD` phải được inject từ secret manager/environment theo deployment policy. Không commit password thật vào `application.yml`, Helm values công khai, Docker image hoặc repository.

### 9.1. TLS trust

Với SASL_SSL, client xác thực SASL và bảo vệ kết nối bằng TLS. Truststore/CA cần cho phép client xác minh broker certificate.

Nếu cluster yêu cầu mutual TLS, client còn cần keystore/certificate/key phù hợp. Principal Kafka có thể được hình thành từ SASL identity hoặc TLS certificate identity tùy listener/auth configuration và principal builder.

### 9.2. Phân biệt lỗi SASL và lỗi ACL

| Exception / symptom | Lớp lỗi thường gặp | Hướng kiểm tra |
|---|---|---|
| SaslAuthenticationException | Authentication | Username, password, mechanism, JAAS config |
| SSLHandshakeException | TLS handshake/trust | CA, hostname, certificate, protocol |
| TopicAuthorizationException | Authorization | TOPIC ACL, principal, operation |
| GroupAuthorizationException | Authorization | GROUP ACL, group ID |
| ClusterAuthorizationException | Authorization | CLUSTER operation được yêu cầu |
| Timeout / disconnect | Kết nối hoặc broker | Network, listener, TLS, broker health |

SASL login thành công nhưng topic ACL thiếu sẽ cho một nhóm lỗi khác với sai password. Đừng sửa credential khi broker logs đã xác nhận principal hợp lệ và operation bị từ chối.

### 9.3. Tách credentials admin và runtime

`admin.properties` dùng cho `kafka-acls.sh` nên thuộc principal quản trị. Spring Boot consumer dùng runtime principal riêng.

Không cấu hình consumer runtime bằng credential admin chỉ để test xem listener có chạy được không. Một phép thử bằng superuser có thể che giấu ACL thiếu.

## 10. Ví dụ cấu hình SASL_SSL trong properties

Nếu dùng Java properties thay YAML:

~~~properties
spring.kafka.bootstrap-servers=kafka-1.internal:9093,kafka-2.internal:9093
spring.kafka.consumer.group-id=billing-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.properties.security.protocol=SASL_SSL
spring.kafka.properties.sasl.mechanism=SCRAM-SHA-512
spring.kafka.properties.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="billing-consumer" password="${KAFKA_CONSUMER_PASSWORD}";
spring.kafka.properties.ssl.endpoint.identification.algorithm=https
~~~

Spring Boot bind các thuộc tính Kafka vào consumer/producer/admin clients theo cấu hình. Nếu ứng dụng tạo custom `ConsumerFactory`, hãy xác nhận nó nhận đúng properties từ Boot hoặc map các Kafka client properties tương ứng.

### 10.1. Không đặt mật khẩu trên command line

Một số shell/process inspection tools có thể hiển thị command-line arguments. Tránh đưa secret trực tiếp vào tham số `--command-config` hoặc inline JAAS trong command history. Dùng file quyền truy cập hạn chế hoặc secret injection theo nền tảng.

### 10.2. Rotation credentials

Khi rotate SCRAM password hoặc TLS certificate:

1. Chuẩn bị identity/credential mới.
2. Cập nhật broker-side credential/certificate theo quy trình.
3. Cập nhật secret ở runtime deployment.
4. Roll/restart consumers có kiểm soát.
5. Xác nhận authentication và authorization vẫn thành công.
6. Thu hồi credential cũ sau khi tất cả clients đã chuyển.
7. Theo dõi reconnect/rebalance và authorization errors.

Credential rotation không tự thay đổi ACL nếu principal name vẫn giữ nguyên; nhưng nếu principal thay đổi, ACL phải được cấp cho identity mới.

## 11. Consumer group ID phải khớp ACL

Một lỗi phổ biến là ACL được cấp cho group `billing-service`, nhưng runtime lại dùng group ID khác.

Các nguồn cấu hình group ID có thể gồm:

- `spring.kafka.consumer.group-id`.
- `groupId` trên `@KafkaListener`.
- `idIsGroup` behavior của annotation/container trong phiên bản tương ứng.
- Custom container properties hoặc factory.
- Environment-specific overrides.

Ví dụ:

~~~java
@KafkaListener(
    id = "billing-listener",
    groupId = "${app.kafka.billing-group}"
)
public void consume(OrderCreated event) {
    billingService.process(event);
}
~~~

Nếu `app.kafka.billing-group=billing-prod-v2`, ACL phải cấp quyền cho resource GROUP `billing-prod-v2`, không phải `billing-service`.

### 11.1. Listener ID không phải group ID

Trong ví dụ:

~~~java
@KafkaListener(
    id = "billing-listener",
    groupId = "billing-service",
    topics = "orders.created"
)
~~~

- Listener ID: `billing-listener` — nhận diện container trong Spring Kafka registry.
- Group ID: `billing-service` — Kafka consumer group resource.
- Principal: `User:billing-consumer` — identity được broker authorization.

ACL group dùng **group ID**, không dùng listener ID.

### 11.2. Nhiều listeners, nhiều groups

Một service có thể có hai listeners:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "billing-orders"
)
public void onOrder(OrderCreated event) { }

@KafkaListener(
    id = "refund-listener",
    topics = "refunds.created",
    groupId = "billing-refunds"
)
public void onRefund(RefundCreated event) { }
~~~

Nếu cùng một principal phục vụ cả hai listeners, cần quyền READ trên hai topics và READ trên hai groups. Nếu muốn tách blast radius, có thể sử dụng principals riêng hoặc deployment identities riêng.

## 12. Consumer pattern subscription và ACL cho topic mới

Với topic pattern, quyền đọc phải bao phủ từng topic mà pattern match. Có hai cách thường dùng:

1. Cấp ACL literal cho từng topic hiện hữu và cập nhật khi topic mới được thêm.
2. Cấp ACL prefixed cho một naming namespace được quản lý.

Ví dụ naming convention:

~~~text
billing.input.orders.created
billing.input.orders.updated
billing.input.refunds.created
~~~

Prefix `billing.input.` có thể phù hợp hơn `billing.` nếu consumer chỉ đọc các topic đầu vào.

### 12.1. Topic được tạo sau khi ACL đã cấp

Nếu ACL literal chỉ áp dụng `orders.created`, một topic mới `orders.updated` sẽ không tự được phép chỉ vì code regex match topic đó.

Nếu dùng prefixed ACL, topic mới có tên bắt đầu bằng prefix có thể match ACL ngay, tùy authorizer/resource pattern semantics. Đây là tiện ích vận hành nhưng cũng làm phạm vi quyền mở rộng khi topic mới được tạo.

### 12.2. Metadata discovery và AdminClient

Consumer subscription thông thường cần metadata và quyền đọc topics mà nó consume. Nếu ứng dụng còn dùng `AdminClient` để liệt kê topics, describe cluster, inspect configs hoặc provision resources, đó là một tập operations khác.

Không cấp CLUSTER DESCRIBE, DESCRIBE_CONFIGS hoặc CREATE chỉ vì `@KafkaListener` cần đọc records. Nếu service thật sự cần AdminClient operations, xác định API và resource tương ứng rồi cấp ACL riêng.

### 12.3. Regex subscription không phải cơ chế quản lý ACL

Đừng dùng một regex quá rộng như `.*` rồi cấp wildcard topic READ. Subscription và authorization là hai cơ chế độc lập. Giữ naming convention và ACL pattern được review cùng nhau.

## 13. ACL cho consumer dùng retry topics và DLT

Một listener có thể dùng retry topics hoặc dead-letter topic. Khi đó service có thể vừa consume topic gốc, vừa consume retry topics, và có thể publish record sang retry/DLT destinations.

Một consumer thuần đọc topic gốc có thể chỉ cần READ trên nguồn và READ trên group. Nhưng một service dùng `@RetryableTopic` thường có thêm quyền theo các đường xử lý retry/DLT.

Ví dụ:

~~~text
Input topics:
  orders.created

Retry topics:
  orders.created-retry-1000
  orders.created-retry-5000

DLT:
  orders.created.DLT
~~~

Các quyền phụ thuộc vào cách retry được triển khai:

| Hoạt động | Resource | Operation thường cần |
|---|---|---|
| Consume original topic | TOPIC source | READ |
| Join original group | GROUP source group | READ |
| Consume retry topic | TOPIC retry | READ |
| Join retry consumer group | GROUP retry group | READ |
| Publish retry record | TOPIC retry | WRITE |
| Publish DLT record | TOPIC DLT | WRITE |
| Consume DLT trong listener riêng | TOPIC DLT | READ |
| Join DLT consumer group | GROUP DLT group | READ |

**Không cấp WRITE trên DLT cho một consumer chỉ đọc DLT.** Nếu `DeadLetterPublishingRecoverer` publish record, producer role cần WRITE trên topic đích; consumer role cần READ nếu có DLT listener riêng.

### 13.1. Retry topics tự động tạo

Nếu framework/deployment tự tạo retry topics, cần xác định ai tạo chúng:

- Provisioning/admin pipeline có thể tạo topics trước.
- Runtime application có thể dùng AdminClient tạo topic nếu được cấp quyền.
- Infrastructure operator có thể quản lý topic lifecycle.

Không cấp CREATE/ALTER/DELETE cho runtime consumer mặc định. Pre-provision topics và cấp ACL runtime thường dễ audit hơn.

### 13.2. DLT producer failure là recovery failure

Nếu service không có WRITE ACL trên DLT, recoverer không thể hoàn tất việc lưu record lỗi. Cần quan sát `TopicAuthorizationException`, đảm bảo recovery không bị coi thành công và giữ offset nguồn an toàn theo error handler/transaction policy.

Consumer có quyền READ trên source/group nhưng thiếu WRITE trên DLT vẫn có thể xử lý record bình thường cho tới khi cần recovery. Đây là lý do phải test cả đường lỗi, không chỉ happy path.

## 14. Consumer dùng transactional listener có cần thêm ACL không?

Với Kafka transactions, quyền cần thêm phụ thuộc consumer có publish records trong transaction và producer transaction ID như thế nào.

Một transactional listener có thể:

- Consume input topic: READ trên TOPIC.
- Tham gia group: READ trên GROUP.
- Produce output: WRITE trên TOPIC output.
- Dùng transactional producer ID: quyền phù hợp trên resource TRANSACTIONAL_ID theo transaction setup/version.
- Dùng transaction coordinator operations: Kafka authorization có thể kiểm tra các resource liên quan.

Không mặc định consumer-only cần TRANSACTIONAL_ID ACL. Chỉ cấp quyền này khi ứng dụng thực sự sử dụng transactional producer/transaction manager và authorizer yêu cầu cho resource đó.

### 14.1. Transactional ID resource

Nếu ứng dụng dùng transactional producer, xem `transactional.id` hoặc prefix được Spring Kafka tạo từ `transactionIdPrefix`. ACL pattern cho `TRANSACTIONAL_ID` cần phù hợp với ID thực tế, nhất là khi có nhiều instances và suffix động.

Producer fencing/transaction authorization là vấn đề khác với quyền READ trên group. Hãy kiểm tra broker exception và transaction configuration trước khi thêm ACL.

### 14.2. Tách quyền theo role

Một kiến trúc có thể dùng:

~~~text
billing-consumer principal:
  READ source topics
  READ consumer group

billing-publisher principal:
  WRITE output topics
  TRANSACTIONAL_ID operations nếu cần

billing-dlt-publisher principal:
  WRITE DLT/retry topics
~~~

Việc tách principal có thêm chi phí quản lý secrets/configuration nhưng thu hẹp quyền của từng runtime component. Chọn theo threat model và vận hành của hệ thống.

## 15. Kiểm tra ACL hiệu lực bằng kafka-acls.sh

Để xem ACL cho topic:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.created
~~~

Để xem ACL group:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --group billing-service
~~~

Để xem ACL cho principal cụ thể, tùy Kafka CLI version có thể lọc bằng `--principal` khi list. Nếu không, list theo resource rồi đối chiếu principal/pattern/host/operation trong output.

Khi kiểm tra, xác nhận đủ tất cả các chiều:

- Principal đúng chính tả/case.
- Resource type đúng TOPIC hoặc GROUP.
- Resource name đúng.
- Pattern type đúng literal/prefixed.
- Operation có READ.
- Permission type là ALLOW.
- Host condition match.
- Không có DENY ACL khác match.

### 15.1. ACL list không chứng minh client authentication

Lệnh `kafka-acls.sh --list` chạy bằng admin principal và cho biết cấu hình ACL. Nó không chứng minh runtime consumer đã đăng nhập thành công với principal dự kiến.

Để xác nhận identity, dùng broker logs/authentication metrics hoặc test bằng runtime credentials. Đừng kết luận “ACL đúng” chỉ vì list output có một ALLOW entry nếu client thực tế authenticate thành principal khác.

### 15.2. Kiểm tra principal mapping

Nếu TLS DN hoặc Kerberos principal được map, xem `principal.builder.class` và mapping rules liên quan. Một certificate renewal có DN khác có thể làm principal thay đổi và khiến ACL cũ không còn match.

Khi identity mapping thay đổi, kiểm thử trên một broker/listener staging trước khi triển khai toàn cluster.

## 16. Kiểm tra consumer thực tế bằng đúng runtime identity

Một phép thử tốt cần dùng **cùng credentials, security protocol, group ID và topic scope** như ứng dụng.

Ví dụ dùng Kafka console consumer:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --consumer.config billing-consumer.properties \
  --topic orders.created \
  --group billing-service \
  --from-beginning \
  --max-messages 1
~~~

File `billing-consumer.properties` chứa security properties runtime được bảo vệ. Lệnh trên đọc tối đa một message và có thể ảnh hưởng group offsets nếu dùng cùng group ID thật.

**Trong production, không dùng một lệnh test với group ID đang chạy** nếu không muốn thay đổi group membership/offset behavior. Dùng một test group riêng và cấp ACL cho test group đó, hoặc thực hiện một smoke test theo runbook có kiểm soát.

### 16.1. Test group riêng

Ví dụ:

~~~text
group.id = billing-acl-smoke-test
principal = User:billing-consumer
topic = orders.created
~~~

Cấp READ trên topic và group test; chạy console consumer với đúng properties; sau đó thu hồi group ACL test. Điều này xác nhận principal có thể fetch topic và sử dụng group mà không can thiệp offset của production group.

### 16.2. Test đúng ứng dụng Spring Kafka

Console consumer hữu ích nhưng không kiểm tra hết serializer, listener factory, group ID overrides và Spring error handling. Cuối cùng cần chạy smoke test bằng chính Spring Boot application với runtime profile/secret phù hợp.

Quan sát startup logs, assignment, poll, listener invocation và offset progress.

## 17. Troubleshooting theo exception

### 17.1. TopicAuthorizationException

Dấu hiệu: consumer không được phép thực hiện operation trên topic.

Kiểm tra:

1. Topic name chính xác trong exception.
2. Principal broker đã xác thực.
3. ACL TOPIC cho principal có ALLOW READ không.
4. Resource pattern có match topic không.
5. Có DENY ACL nào match không.
6. Broker authorizer logs cho biết operation bị từ chối không.
7. Listener có subscribe thêm topics do regex/pattern không.

Không thêm wildcard topic READ nếu chỉ thiếu ACL trên một topic.

### 17.2. GroupAuthorizationException

Dấu hiệu: consumer không được phép sử dụng group resource.

Kiểm tra:

1. Runtime group ID từ effective configuration.
2. ACL GROUP có ALLOW READ cho principal không.
3. Group prefix/literal có match không.
4. Principal có bị mapping sang tên khác không.
5. Có group ID override ở `@KafkaListener` hoặc environment không.
6. Có DENY ACL match không.

Một group ACL cấp cho `billing-service` không áp dụng cho `billing-service-v2` nếu dùng literal pattern.

### 17.3. ClusterAuthorizationException

Một số client/API có thể yêu cầu CLUSTER-level operation, ví dụ thao tác quản trị hoặc cluster description. Đừng cấp CLUSTER quyền rộng cho consumer chỉ để giải quyết exception mà chưa biết API nào gây ra request.

Nếu application dùng AdminClient, xác định operation thực tế và xem có thể tách phần quản trị khỏi runtime listener hay không.

### 17.4. SaslAuthenticationException

Đây là lỗi xác thực, không phải thiếu topic/group ACL. Kiểm tra username/password, mechanism, JAAS module, credential rotation và broker SASL listener.

### 17.5. SSLHandshakeException

Kiểm tra CA trust, broker hostname/SAN, client certificate nếu mutual TLS, TLS protocol/cipher và certificate expiration. Không thay đổi ACL để chữa một lỗi TLS handshake.

### 17.6. Không có exception rõ ràng nhưng listener không nhận record

Kiểm tra:

- Consumer đã authenticate chưa?
- Group đã join/assign partitions chưa?
- Topic có record và retention phù hợp không?
- Consumer có bị pause không?
- ACL có cho READ topic và READ group không?
- Application có dùng đúng cluster/bootstrap servers không?
- Consumer lag/offset đang ở đâu?
- Logs có bị thiếu do logging level hoặc async delivery không?

Authorization errors thường xuất hiện trong client logs và broker authorizer logs; metrics có thể giúp nhận diện nhưng không thay exception/resource details.

## 18. ACL và consumer group offsets

Kafka lưu committed offsets theo group và topic-partition. Consumer group cần authorization phù hợp để sử dụng group và commit offsets.

Nếu consumer đọc được record nhưng commit offset bị từ chối hoặc không thể hoạt động với group, hệ thống có thể:

- Đọc lại record sau restart/rebalance.
- Không tiến committed offset.
- Tạo lag tăng dù listener đã chạy một số record.
- Gây duplicate business processing nếu side effects không idempotent.

### 18.1. Không cấp quyền topic WRITE để commit offsets

Offset commit không phải business produce vào topic nguồn. Kafka quản lý group offsets qua group coordinator và group resource. Cấp WRITE trên topic không thay thế quyền READ trên GROUP.

### 18.2. Manual commit và Spring Kafka AckMode

Các chế độ `AckMode` như RECORD, BATCH, MANUAL và MANUAL_IMMEDIATE điều khiển thời điểm container xác nhận/commit offset theo cấu hình. Chúng không thay đổi nguyên tắc ACL resource: consumer group vẫn cần quyền phù hợp để thực hiện group/offset operations.

Nếu logs có lỗi commit, hãy phân biệt:

- Authorization bị từ chối.
- Coordinator/network timeout.
- Generation/member ID không hợp lệ do rebalance.
- Transaction commit/abort.
- Application acknowledgement chưa được gửi.

Không thêm ACL khi nguyên nhân thực tế là rebalance hoặc timeout.

## 19. ACL cho nhiều môi trường

Production, staging và development nên dùng identities riêng nếu policy yêu cầu cô lập.

Ví dụ:

| Environment | Principal | Group | Topics |
|---|---|---|---|
| Dev | `User:billing-dev` | `billing-dev` | `dev.orders.created` |
| Staging | `User:billing-staging` | `billing-staging` | `staging.orders.created` |
| Production | `User:billing-consumer` | `billing-service` | `orders.created` |

Tránh dùng cùng principal có quyền đọc tất cả environments, nhất là khi dữ liệu production nhạy cảm.

### 19.1. ACL-as-code

Nên quản lý ACL changes như cấu hình hạ tầng có version:

- Principal và owner.
- Resource type/name/pattern.
- Operation và permission type.
- Environment/cluster.
- Ticket/change reason.
- Người phê duyệt.
- Ngày cấp và điều kiện thu hồi.

Một pipeline có thể áp dụng ACL qua Admin API/CLI, sau đó list và so sánh với desired state. Không lưu credentials admin trong repository.

### 19.2. Drift detection

Theo thời gian, ACL có thể bị cấp thủ công, không được thu hồi hoặc bị thay đổi ngoài pipeline. Định kỳ so sánh ACL thực tế với policy đã phê duyệt.

Tập trung vào:

- Wildcard principal.
- Wildcard topic/group.
- ALLOW READ trên topic nhạy cảm.
- DENY entries rộng.
- Principal không còn service owner.
- Prefix pattern mở rộng quá mức.
- Runtime identities có quyền admin.

## 20. Quy trình cấp quyền consumer an toàn

Một workflow thực tế:

1. Xác định service và owner nghiệp vụ.
2. Xác định Kafka cluster/environment.
3. Xác định authentication mechanism.
4. Xác minh principal broker thực tế.
5. Liệt kê topics mà listener thực sự subscribe.
6. Xác định group ID hiệu lực.
7. Liệt kê retry/DLT topics nếu service sử dụng.
8. Xác định service có chỉ consume hay còn publish/AdminClient/transaction.
9. Tạo ACL literal tối thiểu cho TOPIC READ.
10. Tạo ACL literal tối thiểu cho GROUP READ.
11. Áp dụng ACL bằng admin identity.
12. List ACL để xác minh resource/pattern/operation.
13. Smoke test bằng runtime credentials và group phù hợp.
14. Xác nhận listener assignment, processing và offset progress.
15. Lưu audit record và owner của ACL.
16. Đặt thời hạn review/thu hồi nếu quyền tạm thời.

Không cấp ACL rộng trước rồi hy vọng thu hẹp sau. Việc cấp tạm quyền rộng dễ bị quên và trở thành quyền tồn tại lâu dài.

## 21. Thu hồi và rotation ACL

Khi service ngừng consume topic, cần thu hồi quyền không còn sử dụng. Trước khi remove:

1. Xác nhận không còn deployment/consumer nào dùng principal.
2. Kiểm tra listener groups và topic subscriptions.
3. Kiểm tra retry/DLT/replay jobs.
4. Xác định có consumer migration đang diễn ra không.
5. Thu hồi ACL cụ thể.
6. List lại ACL để xác nhận.
7. Theo dõi authorization errors và consumer group activity.

Nếu đổi principal, quy trình an toàn thường là cấp ACL cho principal mới, deploy/verify client mới, rồi thu hồi ACL principal cũ sau khi migration hoàn tất.

Đừng thu hồi ACL group khi consumer cũ vẫn cần commit offsets hoặc đang drain trong rollout.

## 22. Quan sát ACL và authorization trong production

Các tín hiệu hữu ích:

| Tín hiệu | Mục đích |
|---|---|
| Authentication failure count | Phát hiện credentials/mechanism lỗi |
| Authorization failure count | Phát hiện ACL thiếu hoặc DENY |
| TopicAuthorizationException count | Phân biệt topic resource |
| GroupAuthorizationException count | Phân biệt group resource |
| Principal / client ID | Tìm runtime identity |
| Topic/group resource | Xác định phạm vi bị từ chối |
| Consumer group state | Xác nhận join/assignment |
| Commit failure count | Theo dõi offset progress |
| Rebalance rate | Phân biệt authorization với lifecycle/group issues |
| Secret/certificate expiry | Phòng ngừa lỗi authentication |

Tên metric cụ thể phụ thuộc Kafka version, broker authorizer, logging/metrics exporter và instrumentation của ứng dụng. Các exception counters có thể cần được tạo ở application layer hoặc log pipeline.

### 22.1. Log authorization failures

Broker authorizer logs thường hữu ích để biết principal, host, operation và resource bị từ chối. Bảo vệ các logs này vì chúng chứa thông tin về identity, topic naming và security policy.

Không log password, SASL token hoặc private key. Chỉ log principal và resource metadata cần thiết cho audit/troubleshooting.

### 22.2. Alert theo thay đổi, không chỉ số lượng

Một service mới deploy có thể tạo nhiều authorization failures trong vài giây nếu ACL chưa được provision. Alert nên có service/cluster/principal/resource context để operator sửa đúng entry.

Nếu có một principal liên tục thử đọc nhiều topics không được cấp, đây có thể là dấu hiệu cấu hình sai hoặc hoạt động bất thường cần điều tra.

## 23. Kiểm thử ACL trong integration environment

Một unit test Spring Kafka không chứng minh broker authorizer đã enforce ACL. Cần một Kafka environment có authentication và authorizer được bật để test end-to-end.

### 23.1. Happy path với least privilege

1. Tạo principal `billing-consumer`.
2. Tạo topic `orders.created`.
3. Cấp TOPIC READ cho principal.
4. Cấp GROUP READ cho `billing-service`.
5. Chạy consumer với đúng SASL/TLS credentials.
6. Gửi test record bằng producer test identity.
7. Xác nhận listener nhận record và offset tiến.
8. Kiểm tra broker logs không có authorization deny.

### 23.2. Thiếu topic ACL

1. Thu hồi TOPIC READ.
2. Giữ GROUP READ.
3. Restart hoặc tạo consumer test với principal đó.
4. Xác nhận topic authorization failure được quan sát.
5. Cấp lại READ và xác nhận consumer phục hồi.

Kịch bản này chứng minh group permission không thay thế topic permission.

### 23.3. Thiếu group ACL

1. Giữ TOPIC READ.
2. Thu hồi GROUP READ.
3. Dùng group ID test.
4. Xác nhận group authorization failure.
5. Cấp lại GROUP READ và xác nhận consumer có thể join/commit.

Không chạy test này trên production group đang xử lý dữ liệu thật.

### 23.4. Prefixed ACL

1. Cấp READ với prefix `orders.events.`.
2. Tạo hai topic nằm trong prefix.
3. Xác nhận principal đọc được cả hai.
4. Tạo topic ngoài prefix.
5. Xác nhận principal không đọc được topic ngoài phạm vi.
6. Kiểm tra group ACL vẫn độc lập.

### 23.5. DENY ACL

Tạo ALLOW rộng có kiểm soát rồi thêm DENY cho một topic cụ thể. Xác nhận topic bị DENY không đọc được trong khi topic khác vẫn đọc được theo policy.

Dọn test ACL sau khi hoàn tất và list lại resource để không để lại quyền tạm thời.

### 23.6. Authentication failure

Dùng credential sai hoặc mechanism không khớp trong test environment. Xác nhận lỗi là authentication, phân biệt với authorization. Không dùng credential thật để cố tình tạo login failures trên production.

### 23.7. Retry/DLT permissions

Nếu service có retry/DLT:

- Xác nhận source READ và group READ.
- Xác nhận retry topic READ/WRITE đúng vai trò.
- Xác nhận DLT producer có WRITE.
- Xác nhận DLT listener có READ và group READ.
- Thu hồi WRITE DLT để test recovery failure có kiểm soát.
- Xác nhận record nguồn không bị ack/commit sai khi DLT publish bị từ chối.

## 24. Các sai lầm thường gặp

**Chỉ cấp READ trên topic mà quên group.** Consumer không thể hoạt động đầy đủ với group hoặc commit offsets theo policy.

**Chỉ cấp READ trên group mà quên topic.** Consumer không được fetch dữ liệu từ topic.

**Dùng listener ID thay group ID trong ACL.** ACL GROUP phải khớp resource group thực tế.

**Dùng client ID làm principal.** Client ID là metadata của client, không phải identity được xác thực.

**Dùng admin credentials cho runtime consumer.** Che giấu ACL thiếu và mở rộng blast radius.

**Cấp wildcard TOPIC READ cho service.** Cho phép đọc dữ liệu ngoài phạm vi nghiệp vụ.

**Dùng prefix quá rộng.** Topic mới có thể tự động nằm trong vùng được cấp quyền.

**Nhầm authentication với authorization.** Sai SASL password không được chữa bằng thêm ACL.

**Nhầm topic ACL với group ACL.** Đây là hai resource độc lập.

**Quên retry/DLT topics.** Happy path chạy nhưng error path bị authorization failure.

**Cho consumer quyền CREATE/DELETE/ALTER topic mặc định.** Runtime consumer không cần quyền quản trị chỉ để đọc.

**Cho rằng DESCRIBE_CONFIGS cần cho mọi consumer.** Đây là operation quản trị cấu hình, không phải quyền fetch record.

**Không kiểm tra principal mapping.** Certificate/Kerberos mapping có thể làm principal khác username dự kiến.

**Cấp group prefix cho pod-specific group IDs mà không đánh giá.** Có thể biến mỗi pod thành một group độc lập và làm thay đổi semantics consumption.

**Dùng test bằng admin principal.** Test thành công không chứng minh runtime identity có quyền đúng.

**Không kiểm tra DENY và host constraints.** Một ALLOW entry có thể không đủ để authorize request.

**Cấp ACL production thủ công mà không audit.** Quyền tạm thời dễ tồn tại lâu dài.

**Thu hồi ACL trước khi consumer drain xong.** Có thể gây commit/rebalance failures trong rollout.

**Cho rằng Kafka ACL bảo vệ database hoặc HTTP side effects.** ACL chỉ bảo vệ Kafka resources/operations; dependency ngoài Kafka cần authorization riêng.

## 25. Runbook khi consumer gặp authorization failure

### Giai đoạn A — Xác định lớp lỗi

1. Thu exception class và broker logs.
2. Phân biệt SASL/TLS authentication với Kafka authorization.
3. Ghi principal thực tế, host và client ID.
4. Xác định TOPIC, GROUP hay CLUSTER resource.
5. Ghi topic/group ID và operation bị từ chối.

### Giai đoạn B — Đối chiếu policy

1. List ACL trên topic/group liên quan.
2. Kiểm tra ALLOW/DENY.
3. Kiểm tra literal/prefixed/wildcard.
4. Kiểm tra principal mapping.
5. Kiểm tra host restrictions.
6. So sánh với effective Spring Boot group ID và listener topic subscription.
7. Xác định consumer có retry/DLT/AdminClient/transactional behavior không.

### Giai đoạn C — Khắc phục

1. Cấp quyền tối thiểu cho đúng principal/resource/operation.
2. Không cấp wildcard hoặc admin rights để bypass.
3. Dùng runtime credentials smoke test.
4. Restart/reconnect consumer có kiểm soát nếu cần.
5. Xác nhận group join, partition assignment, record processing và offset progress.
6. Theo dõi authorization failures sau deploy.
7. Audit và lưu thay đổi ACL.

Nếu authentication thành công và broker chỉ rõ `READ` bị từ chối trên `orders.created`, hãy sửa TOPIC ACL tương ứng. Nếu resource là `billing-service` dạng GROUP, sửa GROUP ACL. Không thay đổi cả hai một cách mù quáng.

## 26. Tài liệu tham chiếu theo phiên bản

Khi triển khai ACL, đối chiếu tài liệu chính thức của Kafka distribution/version đang chạy:

- **Apache Kafka Security — Authorization and ACLs**: principals, resources, operations, ALLOW/DENY và resource patterns.
- **Apache Kafka Security — SASL Authentication**: SCRAM, PLAIN, GSSAPI và listener configuration.
- **Apache Kafka Security — SSL**: truststore, keystore, client authentication và principal mapping.
- **Kafka `kafka-acls.sh` documentation**: `--add`, `--remove`, `--list`, `--topic`, `--group`, `--principal`, resource pattern types.
- **Apache Kafka Authorizer documentation**: StandardAuthorizer cho KRaft và authorizer của các deployment/version cũ.
- **Spring for Apache Kafka Reference — Connecting to Kafka / Boot Integration**: consumer factory, container và security properties.
- **Spring Boot Reference — Kafka Properties**: `spring.kafka.consumer.group-id`, `spring.kafka.properties.*` và client configuration.
- **Kafka Consumer API**: subscribe/assign, group membership, offset commit và consumer behavior.
- **Kafka Admin API**: quản lý ACL và resource operations.

Các class authorizer, default behavior, CLI flags và operation implications có thể thay đổi giữa Kafka versions/distributions. Hãy xác minh Javadoc/help của đúng `kafka-acls.sh` và broker configuration trước khi thay đổi production ACL.

**Kết luận kỹ thuật:** một Spring Kafka consumer dùng consumer group thông thường cần được xác thực thành đúng principal, được phép **READ trên từng topic nguồn** và **READ trên group ID thực tế**. Cấp quyền theo literal/prefix có kiểm soát, giữ runtime principal tách khỏi admin, và kiểm thử bằng đúng credentials của ứng dụng. Khi lỗi xuất hiện, phân biệt authentication, topic authorization và group authorization trước khi sửa ACL; least privilege phải bao phủ cả retry/DLT paths nếu service sử dụng chúng.
