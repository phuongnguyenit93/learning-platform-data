# Tách quyền quản trị khỏi quyền chạy ứng dụng

Một ứng dụng Kafka thường chỉ cần gửi event vào một số topic, đọc một số topic và commit offset cho một consumer group xác định. Các thao tác như tạo/xóa topic, thay partition count, đổi cấu hình retention, điều chỉnh ACL hoặc reset offset lại thuộc trách nhiệm vận hành nền tảng. Nếu ứng dụng dùng cùng một tài khoản có quyền quản trị rộng, một lỗi cấu hình hoặc credential bị lộ có thể ảnh hưởng toàn bộ cluster.

Kafka hỗ trợ tách hai nhóm trách nhiệm bằng authentication và authorization. Authentication xác định client đang kết nối với principal nào; authorization kiểm tra principal đó có được phép thực hiện operation trên resource cụ thể hay không. Bài viết này tập trung vào cách dùng ACL để cấp quyền tối thiểu cho producer/consumer runtime và giữ quyền quản trị cho AdminClient hoặc công cụ vận hành riêng.

## 1. Authentication khác authorization

Hai lớp bảo mật giải quyết hai câu hỏi khác nhau:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Client là ai? | SASL/SCRAM xác thực `orders-writer`; mTLS xác thực certificate của service |
| Authorization | Principal đó được làm gì trên resource nào? | `User:orders-writer` được `WRITE` vào topic `orders.events` |

SASL, TLS và client certificate không tự quyết định quyền đọc/ghi topic. Chúng cung cấp danh tính và bảo vệ kết nối. Authorizer của broker dùng principal sau xác thực để kiểm tra ACL.

Ví dụ, hai client cùng kết nối bằng `SASL_SSL` nhưng đăng nhập bằng hai user khác nhau:

- `User:orders-writer` chỉ được ghi vào `orders.events`.
- `User:orders-admin` được tạo topic, thay cấu hình và quản lý ACL theo quyền đã cấp.

Nếu cả hai client dùng chung một credential quản trị, broker không thể phân biệt ứng dụng runtime với công cụ quản trị. Vì vậy, tách credential là bước đầu tiên để tách quyền.

## 2. Principal, resource và ACL

Một ACL Kafka mô tả principal nào được phép hoặc bị từ chối thực hiện operation trên resource, từ host nào và theo kiểu pattern nào.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Principal | Danh tính đã được xác thực | `User:orders-writer` |
| Resource type | Loại tài nguyên được bảo vệ | `TOPIC`, `GROUP`, `CLUSTER`, `TRANSACTIONAL_ID` |
| Resource name | Tên tài nguyên | `orders.events`, `payment-service` |
| Operation | Thao tác cần cấp quyền | `READ`, `WRITE`, `CREATE`, `ALTER`, `DESCRIBE` |
| Permission | Cho phép hoặc từ chối | `ALLOW`, `DENY` |
| Host | Địa chỉ nguồn được phép/không được phép | `*` hoặc địa chỉ host cụ thể |
| Pattern type | Cách resource name được so khớp | `LITERAL`, `PREFIXED` |

Ví dụ về một quy tắc: principal `User:orders-writer` được `WRITE` trên resource topic có tên chính xác `orders.events`, từ mọi host được phép theo cấu hình ACL. Quy tắc này không tự cấp quyền tạo topic, xóa topic hoặc ghi vào mọi topic khác.

### Resource thường gặp

| Resource | Bảo vệ đối tượng nào? | Ví dụ |
|---|---|---|
| `TOPIC` | Dữ liệu và metadata của topic | `orders.events` |
| `GROUP` | Consumer group và offset của group | `payment-service` |
| `CLUSTER` | Thao tác cấp cluster | `IdempotentWrite`, một số thao tác quản trị cluster |
| `TRANSACTIONAL_ID` | Transactional producer identity | `orders-tx-` |
| `DELEGATION_TOKEN` | Delegation token | Token được cấp cho client |

ACL không phải role theo kiểu “Admin”, “Writer”, “Reader” được gán sẵn cho mọi trường hợp. Kafka kiểm tra các operation trên resource cụ thể. Một principal có thể có nhiều ACL nhỏ để tạo thành quyền runtime hoặc quyền quản trị cần thiết.

### Literal và prefixed resource

- `LITERAL` áp dụng cho tên resource chính xác. Ví dụ `orders.events` chỉ khớp topic đó.
- `PREFIXED` áp dụng cho mọi resource có tên bắt đầu bằng prefix. Ví dụ prefix `orders.` khớp `orders.events`, `orders.audit` và `orders.retry`.

Prefix giúp quản lý nhiều topic cùng một ứng dụng, nhưng prefix quá rộng có thể cấp quyền vượt nhu cầu. Dùng tên có namespace theo service/environment và chỉ cấp prefix khi ứng dụng thực sự cần nhiều topic cùng phạm vi.

## 3. Bật authorization bằng StandardAuthorizer trong KRaft

Với Kafka chạy KRaft, `org.apache.kafka.metadata.authorizer.StandardAuthorizer` là authorizer chuẩn để đánh giá ACL. Cấu hình cần được áp dụng nhất quán trên các broker/controller theo topology và phiên bản Kafka đang triển khai.

Ví dụ các thuộc tính bảo mật cốt lõi:

```properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false

# Principal quản trị khẩn cấp/được tin cậy tuyệt đối; phân tách bằng dấu chấm phẩy.
super.users=User:kafka-platform-admin
```

`allow.everyone.if.no.acl.found=false` khiến resource không có ACL phù hợp bị từ chối theo chính sách mặc định. Đây là cấu hình phù hợp với mô hình deny-by-default. Nếu bật `true`, resource chưa có ACL có thể được mở cho mọi principal; điều này dễ làm mất ý nghĩa của việc phân quyền tối thiểu.

`super.users` là danh sách principal bỏ qua kiểm tra ACL. Đây là quyền rất rộng, không nên đưa tài khoản ứng dụng runtime vào danh sách này. Chỉ dùng cho principal quản trị/break-glass hoặc principal hạ tầng thực sự cần quyền đặc biệt theo kiến trúc cluster. Với KRaft, cần đánh giá riêng danh tính inter-broker/controller và listener nội bộ để cluster vẫn hoạt động; không sao chép một danh sách super user mẫu mà chưa kiểm tra principal thực tế.

ACL trong KRaft được quản lý như metadata của cluster. Vì vậy, thay đổi ACL là thay đổi control plane và cần được kiểm soát, audit và sao lưu/quản lý như các thay đổi cấu hình nền tảng khác.

## 4. Thiết kế principal theo trách nhiệm

Không nên dùng một user chung cho mọi service. Tách principal theo ứng dụng, môi trường và vai trò giúp giới hạn blast radius khi credential bị lộ hoặc service bị xâm nhập.

Ví dụ một hệ thống đơn hàng:

| Principal | Vai trò | Quyền dự kiến |
|---|---|---|
| `User:orders-writer-prod` | Order Service runtime | Ghi `orders.events` và các topic được chỉ định |
| `User:payment-reader-prod` | Payment Service runtime | Đọc `orders.events`, dùng group `payment-service-prod` |
| `User:reporting-reader-prod` | Reporting runtime | Đọc các topic báo cáo và group riêng |
| `User:orders-transformer-prod` | Consume-transform-produce | Đọc input, ghi output, dùng transactional ID riêng |
| `User:kafka-provisioner` | CI/CD hoặc platform automation | Tạo topic và cấu hình theo phạm vi được giao |
| `User:kafka-platform-admin` | Quản trị nền tảng | Quản lý ACL, cấu hình và thao tác cluster theo quy trình vận hành |

Các nguyên tắc:

- Mỗi service có credential riêng; không chia sẻ credential runtime giữa các ứng dụng.
- Tách production, staging và development thành principal khác nhau.
- Tài khoản runtime chỉ có quyền trên topic/group/transactional ID mà nó sử dụng.
- Tài khoản provisioning có thể tạo topic nhưng không cần được dùng trong process phục vụ request nghiệp vụ.
- Tài khoản quản trị ACL và cluster không được nhúng vào image hoặc secret của ứng dụng.
- Khi service ngừng hoạt động, thu hồi ACL và credential tương ứng.

## 5. Ma trận quyền cho producer runtime

Một producer thông thường cần ghi record vào topic. Quyền cơ bản là `WRITE` trên topic đích. Kafka có quan hệ operation implication; chẳng hạn một số quyền `WRITE` bao hàm khả năng `DESCRIBE` tương ứng. Không cần cấp `ALL` chỉ để producer gửi message.

Ví dụ principal `User:orders-writer-prod` chỉ ghi topic `orders.events`:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-writer-prod \
  --operation Write \
  --topic orders.events
```

Nếu producer cần ghi một nhóm topic có prefix, có thể dùng resource pattern `PREFIXED`:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-writer-prod \
  --operation Write \
  --topic orders. \
  --resource-pattern-type prefixed
```

Chỉ cấp prefix nếu producer thực sự gửi vào nhiều topic có tên bắt đầu bằng `orders.`. Với một topic cố định, ACL literal chính xác dễ audit hơn.

### Producer idempotent và transactional producer

Producer idempotent có thể cần quyền `IDEMPOTENT_WRITE` trên resource `CLUSTER` khi ACL authorizer được bật, tùy phiên bản và loại producer. Producer dùng transaction cần quyền `WRITE` trên resource `TRANSACTIONAL_ID` tương ứng, ngoài quyền ghi topic. Với transactional producer, transactional ID nên có prefix riêng cho service/instance và ACL phải giới hạn đúng prefix đó.

Ví dụ cấp quyền cho transactional ID có prefix `orders-tx-`:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-transformer-prod \
  --operation Write \
  --transactional-id orders-tx- \
  --resource-pattern-type prefixed
```

Nếu client yêu cầu quyền `IdempotentWrite` cấp cluster, cấp riêng operation đó cho principal cần dùng producer idempotent:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-writer-prod \
  --operation IdempotentWrite \
  --cluster
```

Yêu cầu ACL chính xác có thể phụ thuộc phiên bản Kafka, transactional mode và API được gọi. Hãy kiểm tra authorization exception và tài liệu của phiên bản đang triển khai trước khi cấp quyền rộng hơn.

## 6. Ma trận quyền cho consumer runtime

Consumer group cần quyền đọc topic và quyền tham gia group/commit offset. Thông thường:

- `READ` trên topic để fetch record.
- `READ` trên group để join group và commit offset.
- `DESCRIBE` có thể được cấp riêng nếu công cụ hoặc API cần mô tả group/topic mà không có operation khác bao hàm quyền này.

Ví dụ `User:payment-reader-prod` đọc `orders.events` và dùng đúng group `payment-service-prod`:

```bash
# Quyền đọc topic
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:payment-reader-prod \
  --operation Read \
  --topic orders.events

# Quyền dùng consumer group
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:payment-reader-prod \
  --operation Read \
  --group payment-service-prod
```

Nếu group có suffix theo instance hoặc môi trường, có thể dùng prefix như `payment-service-prod-` thay vì cấp `Read` trên mọi group. Không cấp `GROUP *` chỉ để một consumer có thể commit offset.

Một ứng dụng đọc nhiều topic nhưng chỉ sử dụng một group vẫn cần ACL topic cho từng topic được subscribe. Quyền `READ` trên group không tự cấp quyền đọc topic; quyền đọc topic cũng không tự cấp quyền sử dụng mọi group.

## 7. Ma trận quyền cho AdminClient và công cụ quản trị

`AdminClient` là API quản trị Kafka, nhưng bản thân class này không tự bypass ACL. Mọi request vẫn được xác thực bằng principal của client và authorizer kiểm tra operation trên resource tương ứng.

Một số thao tác và quyền thường liên quan:

| Admin API/hoạt động | Resource | Operation ACL thường cần |
|---|---|---|
| `createTopics` | Topic hoặc Cluster | `CREATE` trên topic đích hoặc cluster theo cách tạo |
| `deleteTopics` | Topic | `DELETE` |
| `createPartitions` | Topic | `ALTER` |
| Thay topic config | Topic | `ALTER_CONFIGS` |
| `describeConfigs` | Topic/Broker/Cluster | `DESCRIBE_CONFIGS` |
| `describeCluster` | Cluster | `DESCRIBE` |
| `describeConsumerGroups` | Group | `DESCRIBE` |
| `deleteConsumerGroups` | Group | `DELETE` |
| Điều chỉnh committed offsets | Group | `ALTER` |
| Quản lý ACL | Cluster | `ALTER` trên Cluster (và quyền tương ứng theo API/version) |

Bảng trên là hướng dẫn thiết kế quyền, không thay thế kiểm tra authorization cho từng API/version. Một Admin API có thể chạm nhiều resource; ví dụ thao tác topic có thể cần thêm quyền trên cluster hoặc resource liên quan tùy request. Khi nhận `AuthorizationException`, hãy xem resource và operation trong broker log để cấp đúng ACL còn thiếu.

### Tạo topic bằng principal provisioning

Tạo topic là thao tác control plane. Nếu topic đã được provisioning trước qua CI/CD, producer runtime không cần quyền `CREATE`.

Ví dụ principal `User:kafka-provisioner` được tạo topic có prefix `orders.`:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:kafka-provisioner \
  --operation Create \
  --topic orders. \
  --resource-pattern-type prefixed
```

Sau khi provisioning hoàn tất, service runtime chỉ nhận quyền `WRITE` hoặc `READ` trên topic được giao. Không cần cấp `CREATE`, `DELETE`, `ALTER` hay `ALTER_CONFIGS` cho runtime nếu ứng dụng không thực hiện các tác vụ đó.

### Điều chỉnh consumer group offset

Admin API như `alterConsumerGroupOffsets` là thao tác có ảnh hưởng đến tiến độ xử lý. Principal quản trị offset cần quyền phù hợp trên group (thường là `ALTER`) và quyền đọc/kiểm tra metadata liên quan theo API. Không cấp quyền này cho consumer runtime chỉ vì consumer có commit offset thông thường; `READ` trên group phục vụ luồng tiêu thụ khác với quyền `ALTER` để thay đổi offset từ bên ngoài.

### Gọi AdminClient bằng principal provisioning

Đoạn Java sau minh họa một công cụ provisioning độc lập tạo topic bằng credential quản trị được cấp riêng:

```java
Properties adminProps = new Properties();
adminProps.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
               "broker-1:9093,broker-2:9093");
adminProps.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SASL_SSL");
adminProps.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");
adminProps.put(SaslConfigs.SASL_JAAS_CONFIG,
               secretProvider.kafkaAdminJaasConfig());

try (Admin admin = Admin.create(adminProps)) {
    NewTopic topic = new NewTopic("orders.events", 6, (short) 3);
    admin.createTopics(List.of(topic)).all().get();
}
```

`secretProvider` là thành phần do công cụ provisioning cung cấp để lấy JAAS config từ secret manager; không hardcode credential trong source. Công cụ này chạy trong pipeline hoặc job vận hành với principal `kafka-provisioner`, còn Order Service runtime chỉ dùng `orders-writer-prod` và ACL `WRITE` trên topic. Không đưa `adminProps` hoặc secret provisioning vào cấu hình producer/consumer của service.

Trong thực tế, nên xử lý riêng các trường hợp topic đã tồn tại, timeout và `ExecutionException` chứa `TopicExistsException` hoặc authorization failure. Không bắt mọi exception rồi bỏ qua, vì điều đó có thể khiến pipeline báo thành công dù topic chưa được tạo đúng cấu hình.

## 8. Cấu hình client dùng principal runtime

Ví dụ Java client dùng SASL/SCRAM qua TLS:

```properties
bootstrap.servers=broker-1:9093,broker-2:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-writer-prod" password="${KAFKA_PASSWORD}";
ssl.truststore.location=/etc/kafka/secrets/client.truststore.p12
ssl.truststore.password=${TRUSTSTORE_PASSWORD}
```

Đây là ví dụ minh họa thuộc tính client; cách thay biến môi trường phụ thuộc launcher/secret manager. Kafka client không tự nội suy `${KAFKA_PASSWORD}` trong mọi cách chạy. Trong production, render JAAS config từ secret manager hoặc truyền qua cơ chế secret an toàn; không commit password/truststore password vào repository, Docker image hoặc log.

Producer và consumer nên nhận principal riêng. Ví dụ producer dùng `orders-writer-prod`; consumer dùng `payment-reader-prod`. Nếu một process vừa produce vừa consume, có thể cấp hai nhóm quyền cần thiết cho một principal service chuyên biệt, nhưng vẫn không cấp quyền quản trị cluster.

### Tách cấu hình runtime và admin

Ví dụ hai cấu hình tách biệt:

```text
application-kafka.properties
  username = orders-writer-prod
  password = secret của orders-writer-prod
  quyền = WRITE trên orders.events

admin-kafka.properties
  username = kafka-platform-admin
  password = secret quản trị riêng
  quyền = thao tác quản trị theo quy trình vận hành
```

Ứng dụng không nên đọc `admin-kafka.properties` trong process runtime. Công cụ CI/CD hoặc operator dùng credential quản trị qua pipeline/secret store được kiểm soát. Không đưa credential admin vào biến môi trường chung được inject cho mọi deployment.

## 9. Cấu hình Spring Boot và Spring Kafka

Với Spring Boot, cấu hình SASL/TLS runtime có thể đặt trong consumer/producer properties. Ví dụ producer:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9093,broker-2:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
      ssl.truststore.location: /etc/kafka/secrets/client.truststore.p12
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
    producer:
      acks: all
      properties:
        enable.idempotence: true
```

Consumer có thể dùng principal riêng bằng cách override security properties ở consumer factory nếu producer và consumer cần credential khác nhau. Không nên giả định một cấu hình `spring.kafka.properties` dùng chung sẽ tự tạo hai principal khác nhau; hãy cấu hình rõ `ProducerFactory` và `ConsumerFactory` hoặc dùng các property namespace riêng theo phiên bản Spring Boot.

Nếu Spring application có `KafkaAdmin` để tự tạo topic lúc khởi động, cần hiểu rằng thao tác tạo topic chạy bằng principal của Admin client được cấu hình cho `KafkaAdmin`. Nếu ứng dụng runtime chỉ có quyền `WRITE` mà `KafkaAdmin` vẫn cố tạo topic, startup có thể nhận authorization error. Trong production, thường provisioning topic bằng pipeline riêng và tắt hoặc giới hạn auto topic creation của ứng dụng.

## 10. Cấp, xem và thu hồi ACL bằng CLI

`kafka-acls.sh` là công cụ phổ biến để quản lý ACL. Các lệnh cần kết nối bằng principal có quyền quản trị ACL. File `admin.properties` trong ví dụ là client config chứa credential quản trị và TLS/SASL, không phải file cấu hình broker.

Xem ACL của một topic:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.events
```

Xem ACL theo principal:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --list \
  --principal User:orders-writer-prod
```

Thu hồi quyền ghi:

```bash
kafka-acls.sh \
  --bootstrap-server broker-1:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal User:orders-writer-prod \
  --operation Write \
  --topic orders.events
```

Khi thu hồi, phải chỉ rõ principal, resource pattern và operation giống ACL đã cấp. Nếu ACL được tạo với `PREFIXED`, cần chỉ rõ cùng pattern type khi remove. Trước khi xóa ACL rộng, hãy liệt kê và lưu lại trạng thái hiện tại để tránh thu hồi nhầm quyền của service khác.

## 11. DENY, wildcard và super user: các điểm cần thận trọng

### DENY có thể làm quyền ALLOW không còn hiệu lực

Kafka ACL hỗ trợ `ALLOW` và `DENY`. Một ACL DENY khớp principal/resource/operation/host có thể khiến request bị từ chối dù có ACL ALLOW khác. Vì vậy, cần xem toàn bộ ACL khớp với resource, không chỉ tìm một dòng ALLOW.

### Wildcard và prefix rộng

Principal `User:*`, resource pattern rộng hoặc prefix chung như `*` có thể mở quyền cho nhiều service ngoài dự kiến. Không dùng wildcard để chữa nhanh lỗi authorization trong production. Hãy xác định chính xác principal, resource và operation từ log.

### Super user không phải role runtime

Principal trong `super.users` bỏ qua kiểm tra ACL. Nếu đưa principal ứng dụng vào đây, mọi ACL giới hạn topic/group cho principal đó gần như mất tác dụng. Không dùng `super.users` để xử lý lỗi quyền thiếu; hãy bổ sung ACL nhỏ nhất cần thiết.

## 12. Kiểm chứng quyền tối thiểu bằng negative test

Không chỉ kiểm tra thao tác được phép thành công; cần xác nhận thao tác không được phép thực sự thất bại. Ví dụ với `orders-writer-prod`:

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Produce vào `orders.events` | Thành công |
| Produce vào `payments.events` | Bị từ chối |
| Consume topic `orders.events` | Bị từ chối nếu không cấp READ |
| Tạo topic mới | Bị từ chối |
| Xóa topic `orders.events` | Bị từ chối |
| Thay retention config | Bị từ chối |
| Alter offset group `payment-service-prod` | Bị từ chối |

Với `payment-reader-prod`:

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Consume `orders.events` với group `payment-service-prod` | Thành công |
| Consume `payments.events` | Bị từ chối nếu không cấp READ |
| Dùng group không nằm trong ACL | Bị từ chối |
| Produce vào `orders.events` | Bị từ chối |
| Tạo/xóa topic hoặc sửa ACL | Bị từ chối |

Negative test là một phần của kiểm thử bảo mật. Nếu thao tác ngoài phạm vi vẫn thành công, kiểm tra wildcard ACL, prefix pattern, `super.users`, `allow.everyone.if.no.acl.found`, principal mapping và các ACL được kế thừa/áp dụng cho resource.

## 13. Phân biệt lỗi authentication và authorization

| Triệu chứng | Lớp lỗi | Hướng điều tra |
|---|---|---|
| SASL authentication failed | Authentication | Username/password, SCRAM mechanism, JAAS config, credential provisioning |
| TLS handshake/certificate error | TLS/authentication | Truststore, certificate chain, hostname verification, client certificate nếu dùng mTLS |
| `TopicAuthorizationException` | Authorization | ACL trên topic và operation READ/WRITE/CREATE tương ứng |
| `GroupAuthorizationException` | Authorization | ACL trên resource GROUP và group ID thực tế |
| `ClusterAuthorizationException` | Authorization | ACL trên CLUSTER hoặc operation cluster-level như IdempotentWrite |
| `TransactionalIdAuthorizationException` | Authorization | ACL trên TRANSACTIONAL_ID và transactional ID thực tế |

Đừng xử lý authorization error bằng cách đổi sang principal admin trong ứng dụng. Điều đó che giấu cấu hình thiếu quyền và mở rộng blast radius. Hãy ghi nhận principal, resource, operation bị từ chối rồi bổ sung đúng ACL.

## 14. Audit và vận hành vòng đời quyền

Quyền Kafka cần được quản lý như code/cấu hình hạ tầng:

- Lưu ACL mong muốn trong repository hoặc hệ thống provisioning có review.
- Mọi thay đổi ACL production cần có người phê duyệt và audit trail.
- Theo dõi principal, operation, resource, host, người thay đổi và thời điểm.
- Dùng credential riêng theo môi trường và xoay vòng định kỳ.
- Thu hồi credential/ACL khi service nghỉ hưu hoặc có sự cố bảo mật.
- Kiểm tra quyền thực tế định kỳ để loại ACL thừa và wildcard không còn cần thiết.
- Giữ một quy trình break-glass cho sự cố cluster, có thời hạn và audit.
- Không ghi password, token hoặc secret JAAS vào log.

Có thể dùng CLI để xuất danh sách ACL và so sánh với manifest quyền mong muốn. Với cluster lớn, nên tự động hóa provisioning theo service identity và môi trường để tránh tạo ACL thủ công không nhất quán.

## 15. Bài thực hành: tách runtime principal và admin principal

Thực hiện trên Kafka KRaft lab có SASL/SCRAM và StandardAuthorizer:

1. Bật `StandardAuthorizer` và cấu hình deny-by-default.
2. Tạo principal `orders-writer-lab`, `payment-reader-lab` và `kafka-admin-lab` bằng cơ chế authentication của môi trường.
3. Dùng admin principal tạo topic `orders.events` và group ACL cho `payment-service-lab`.
4. Cấp `WRITE` cho `orders-writer-lab` trên `orders.events`.
5. Cấp `READ` cho `payment-reader-lab` trên `orders.events` và `payment-service-lab`.
6. Dùng producer runtime gửi event thành công.
7. Thử producer runtime ghi topic `payments.events`, tạo topic hoặc xóa topic; xác minh authorization bị từ chối.
8. Dùng consumer runtime đọc đúng topic/group rồi thử group khác và topic khác; xác minh bị từ chối.
9. Dùng admin principal gọi AdminClient tạo topic hoặc xem config theo ACL được cấp.
10. Thu hồi `WRITE` của writer, thử gửi lại và xác minh quyền đã bị thu hồi.
11. Xem broker logs và ACL list để đối chiếu principal/resource/operation.

Chỉ chạy bài thực hành trên cluster lab. Không bật authorizer hoặc thay đổi ACL trên cluster production khi chưa có kế hoạch bootstrap principal quản trị, kiểm thử quyền broker/controller và phương án khôi phục.

## 16. Những nhầm lẫn thường gặp

- **Cho rằng SASL_SSL tự cấp quyền đọc/ghi:** SASL xác thực, TLS bảo vệ kết nối; ACL mới quyết định quyền resource.
- **Cho rằng AdminClient luôn có quyền admin:** AdminClient dùng principal của credential được cấu hình và vẫn chịu authorizer kiểm tra.
- **Dùng credential quản trị cho producer/consumer:** làm ứng dụng có thể thay đổi hoặc xóa tài nguyên ngoài phạm vi nghiệp vụ.
- **Cấp `ALL` trên cluster để sửa một lỗi topic:** cấp quá rộng và che mất operation/resource thực sự cần thiết.
- **Cấp READ topic nhưng quên GROUP:** consumer có thể đọc metadata nhưng không join/commit group được.
- **Cấp quyền group nhưng quên topic:** consumer có thể tham gia group nhưng không đọc được dữ liệu.
- **Cho rằng producer chỉ cần WRITE cho mọi mode:** idempotent/transactional producer có thể cần thêm ACL cluster hoặc transactional ID tùy mode/version.
- **Đưa runtime principal vào `super.users`:** làm mất hiệu lực của mô hình least privilege đối với principal đó.
- **Bật `allow.everyone.if.no.acl.found=true` để tránh lỗi:** resource chưa có ACL có thể được mở cho mọi user.
- **Chỉ kiểm tra positive test:** thao tác được phép thành công chưa chứng minh thao tác ngoài phạm vi đã bị chặn.
- **Thu hồi ACL nhưng không kiểm tra prefix/wildcard:** một ACL rộng khác vẫn có thể cấp quyền.

Tách quyền quản trị khỏi quyền chạy ứng dụng bằng principal riêng và ACL theo resource/operation giúp giới hạn tác động khi service lỗi hoặc credential bị lộ. Runtime chỉ nên có quyền đọc/ghi topic và group cần thiết; provisioning và quản trị dùng principal riêng, được kiểm soát qua AdminClient/CLI và quy trình audit. Kiểm thử cả thao tác được phép lẫn thao tác bị từ chối để chứng minh mô hình least privilege thực sự có hiệu lực.
