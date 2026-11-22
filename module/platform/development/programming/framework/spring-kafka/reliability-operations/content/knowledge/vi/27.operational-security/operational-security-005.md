# ACL cho producer

Trong Kafka, **producer ACL** xác định principal nào được phép ghi dữ liệu vào topic và sử dụng các tính năng producer cần thiết. Một ứng dụng Spring Kafka có thể kết nối broker và xác thực SASL/TLS thành công nhưng vẫn không được phép publish. Sau authentication, broker còn kiểm tra authorization dựa trên principal, resource, operation và các ACL đang có hiệu lực.

Thiết kế ACL đúng giới hạn một service chỉ được ghi vào những topic mà nó sở hữu. Với producer dùng idempotence hoặc Kafka transactions, quyền cần thiết còn liên quan đến **Cluster resource** và **TransactionalId resource**, ngoài quyền ghi topic. Bài học trình bày mô hình ACL, quyền tối thiểu, lệnh quản trị, cấu hình Spring Boot, transaction ID, retry/DLT, kiểm thử và runbook vận hành.

## 1. Authentication và authorization là hai bước khác nhau

- **Authentication:** broker xác định client là ai. Ví dụ principal `User:orders-producer` được xác thực qua SASL/SCRAM, SASL/OAUTHBEARER hoặc TLS client certificate.
- **Authorization:** broker kiểm tra principal có được phép thực hiện operation trên resource hay không. Ví dụ `User:orders-producer` có quyền `WRITE` trên topic `orders.events`.

~~~mermaid
sequenceDiagram
    participant P as Spring Kafka Producer
    participant B as Kafka Broker
    participant A as Kafka Authorizer
    P->>B: Kết nối + SASL/TLS authentication
    B-->>P: Principal được xác thực
    P->>B: Produce record vào orders.events
    B->>A: Kiểm tra WRITE ACL trên topic
    alt Có ACL phù hợp
        A-->>B: Allow
        B-->>P: Produce result
    else Không có quyền
        A-->>B: Deny
        B-->>P: TopicAuthorizationException
    end
~~~

Một client có thể kết nối broker thành công nhưng bị từ chối ghi topic; ghi được topic A nhưng không được ghi topic B; ghi topic thường được nhưng không được khởi tạo transaction; hoặc xác thực bằng principal khác dự kiến do cấu hình SASL/TLS không đúng.

**ACL không thay thế authentication.** Username/password đúng cũng không tự cấp quyền ghi topic.

## 2. Kafka ACL mô hình hóa resource và operation

| Resource | Ví dụ | Vai trò |
|---|---|---|
| `TOPIC` | `orders.events` | Quyền ghi/đọc dữ liệu topic. |
| `CLUSTER` | Kafka cluster | Quyền phạm vi cluster, ví dụ idempotent write. |
| `TRANSACTIONAL_ID` | `orders-tx-...` | Quyền dùng transactional producer identity. |
| `GROUP` | `orders-service` | Chủ yếu liên quan consumer group, không phải quyền ghi topic thông thường. |

Những operation thường liên quan:

| Operation | Ý nghĩa |
|---|---|
| `WRITE` | Ghi record vào topic hoặc sử dụng transactional ID theo resource type. |
| `DESCRIBE` | Xem metadata của resource. |
| `CREATE` | Tạo resource theo phạm vi được cấp. |
| `ALTER` | Thay đổi cấu hình/trạng thái resource theo API được hỗ trợ. |
| `DELETE` | Xóa resource. |
| `IDEMPOTENT_WRITE` | Cho phép producer dùng idempotent write trên cluster resource. |
| `ALL` | Tất cả operations; thường quá rộng cho runtime producer. |

Kafka có quy tắc implication giữa operations. Ví dụ `WRITE` trên topic thường bao hàm `DESCRIBE` tương ứng theo ACL semantics. Tuy nhiên, không suy ra mọi API khác đều được phép; hãy xác minh operation broker kiểm tra theo Kafka version.

Một ACL bao gồm principal, host, operation, permission type `ALLOW` hoặc `DENY`, resource type/name và pattern type như `LITERAL` hoặc `PREFIXED`.

## 3. Quyền tối thiểu cho producer ghi topic

Với producer không dùng Kafka transactions, quyền cốt lõi là:

- `WRITE` trên topic đích.
- Quyền metadata cần thiết theo ACL semantics/version; `WRITE` trên topic thường bao hàm `DESCRIBE`.
- Nếu producer dùng idempotence, cấp `IDEMPOTENT_WRITE` trên cluster resource theo authorization model của Kafka.
- Nếu ứng dụng tự tạo topic, quyền `CREATE` phải được cấp riêng theo phạm vi resource; thường nên provision topic bằng principal quản trị riêng.

Ví dụ service chỉ publish vào `orders.events`:

~~~text
Principal:
  User:orders-producer

Allowed:
  TOPIC orders.events -> WRITE
  CLUSTER kafka-cluster -> IDEMPOTENT_WRITE (nếu dùng idempotence)

Không cần cho runtime producer thông thường:
  TOPIC payments.events -> WRITE
  TOPIC orders.events -> DELETE
  CLUSTER kafka-cluster -> ALTER
  CLUSTER kafka-cluster -> CREATE
~~~

Một producer không cần quyền đọc topic chỉ vì nó ghi dữ liệu vào topic đó. Nếu ứng dụng có thêm consumer, AdminClient, Schema Registry hoặc DLT publishing, hãy phân tích từng chức năng và cấp quyền riêng.

### WRITE không phải CREATE

`WRITE` cho phép publish vào topic đã tồn tại. `CREATE` liên quan tạo topic mới. Không cấp `CREATE` cho runtime producer nếu topic được provision qua quy trình hạ tầng riêng.

Nếu broker bật `auto.create.topics.enable`, producer gửi đến topic chưa tồn tại có thể kích hoạt topic creation theo cấu hình cluster và ACL policy. Hành vi cụ thể phụ thuộc Kafka version và authorizer. Production nên quản lý topic trước, tránh typo trong topic name tự tạo topic ngoài ý muốn.

## 4. Idempotent producer cần quyền cluster nào?

Kafka producer idempotence giúp tránh duplicate do producer retry trong phạm vi protocol hỗ trợ. Với Kafka ACL authorization, idempotent producer cần operation `IDEMPOTENT_WRITE` trên resource `CLUSTER`.

Phân biệt:

- `TOPIC / WRITE`: được ghi vào topic đích.
- `CLUSTER / IDEMPOTENT_WRITE`: được dùng cơ chế idempotent write.
- `TRANSACTIONAL_ID / WRITE`: được sử dụng transactional identity nếu producer dùng transaction.

Nếu producer ghi topic thành công khi idempotence tắt nhưng sau khi bật idempotence lại gặp `ClusterAuthorizationException`, có thể principal thiếu `IDEMPOTENT_WRITE` trên cluster.

Ở Kafka client hiện đại, idempotence thường được bật mặc định khi cấu hình tương thích. Đừng giả định producer không bật idempotence chỉ vì ứng dụng không khai báo property; hãy xem effective producer config và Kafka client version.

**Idempotence không đồng nghĩa transaction.** Idempotence bảo vệ retry send theo producer protocol; nó không tự tạo transaction consume-transform-produce và không bao trùm database/HTTP.

## 5. Transactional producer cần quyền gì?

Kafka transactions cho phép producer ghi nhiều records và, trong consume-transform-produce, phối hợp output records với input offsets trong cùng transaction nếu container/transaction manager được cấu hình đúng.

Một transactional producer thường cần:

1. `WRITE` trên từng topic mà producer ghi.
2. `WRITE` trên resource `TRANSACTIONAL_ID` tương ứng với transactional ID thực tế.
3. `IDEMPOTENT_WRITE` trên cluster resource theo authorization requirements của Kafka.
4. Quyền bổ sung nếu ứng dụng đồng thời thực hiện admin/consumer operations; không suy ra chúng từ quyền transaction.

Ví dụ:

~~~text
Principal:
  User:orders-transactional-producer

Resources:
  TOPIC orders.events.out -> WRITE
  TRANSACTIONAL_ID orders-tx-orders-service-* -> WRITE
  CLUSTER kafka-cluster -> IDEMPOTENT_WRITE
~~~

`TRANSACTIONAL_ID` là resource riêng. ACL `WRITE` trên topic không tự cấp quyền sử dụng transactional ID; quyền transactional ID cũng không cho phép ghi vào mọi topic.

Nếu producer dùng transactional ID cụ thể `orders-tx-pod-a-0`, ACL phải match ID đó. Nếu Spring Kafka sinh ID bằng prefix và suffix, pattern cần match toàn bộ IDs được tạo. Không cấp prefix quá rộng như `*` trên transactional IDs của mọi ứng dụng: producer có thể can thiệp vào vòng đời producer khác thông qua fencing.

## 6. Cấp ACL bằng kafka-acls.sh

Kafka cung cấp CLI `kafka-acls.sh` để quản lý ACL. Ví dụ dùng `--bootstrap-server` và file client config có quyền quản trị ACL. Bảo vệ file config, không commit secret vào source control.

### Cho phép producer ghi một topic

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --topic orders.events
~~~

Lệnh này cấp `WRITE` trên topic `orders.events`. Không dùng shortcut `--producer` khi cần policy tối thiểu và audit rõ operation; shortcut có thể cấp thêm operation tiện ích tùy CLI version.

### Cho phép idempotent write

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation IdempotentWrite \
  --cluster
~~~

Tên operation CLI thường là `IdempotentWrite`; xác nhận help output của Kafka version đang triển khai. Quyền này áp dụng cluster resource, không phải topic resource.

### Cho phép transactional producer

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --transactional-id orders-tx-orders-service- \
  --resource-pattern-type prefixed
~~~

Ví dụ dùng prefix pattern để match transactional IDs bắt đầu bằng `orders-tx-orders-service-`. Prefix phải đủ riêng biệt giữa các service/environment/instance. Nếu producer dùng một ID cố định, có thể cấp ACL literal cho ID đó.

### Host restriction

Có thể giới hạn ACL theo host nếu hạ tầng có địa chỉ nguồn ổn định và authorizer hỗ trợ. Với Kubernetes, pod IP thường thay đổi; giới hạn theo IP pod tĩnh có thể khiến rollout làm producer mất quyền. Cân nhắc network policy và service identity trước khi đặt host restriction.

## 7. Kiểm tra ACL đã cấp

Liệt kê policy cho topic:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --topic orders.events
~~~

Liệt kê ACL theo principal:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --principal User:orders-producer
~~~

Kiểm tra transactional ID:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --transactional-id orders-tx-orders-service-
~~~

CLI options và resource pattern filters có thể khác nhẹ giữa Kafka versions. Dùng `kafka-acls.sh --help` của đúng distribution và xác nhận kết quả trên cluster mục tiêu.

Khi kiểm tra, đối chiếu principal thực tế, resource name, resource pattern type, operation, host restriction, ACL DENY đang match, authorizer configuration và cluster đang kiểm tra. Một ACL ALLOW đúng tên topic nhưng sai principal hoặc sai pattern type vẫn không cho phép producer.

## 8. Literal và prefixed resource patterns

Kafka ACL có thể áp dụng cho resource literal hoặc prefix.

| Pattern | Resource | Principal | Phạm vi |
|---|---|---|---|
| Literal | `orders.events` | `User:orders-producer` | Chỉ topic này. |
| Prefixed | `orders.` | `User:orders-producer` | Topic bắt đầu bằng `orders.`. |
| Literal | `orders-tx-a-0` | `User:orders-producer` | Một transactional ID. |
| Prefixed | `orders-tx-prod-` | `User:orders-producer` | Transactional IDs có prefix đó. |

Literal là lựa chọn an toàn mặc định khi service chỉ cần ghi một topic. Prefix tiện khi service có tập topic/transaction IDs được quản lý chung, nhưng phải chọn prefix hẹp và có quy ước naming.

Không cấp prefix `orders` nếu các topic `orders-admin`, `orders-audit` hoặc `orders-sensitive` có owner/quyền khác nhau. Prefix rộng có thể vô tình mở quyền cho tài nguyên được tạo trong tương lai.

## 9. DENY ACL và quyền rộng hơn

Kafka ACL có allow và deny. Khi một deny ACL khớp principal/host/resource/operation, nó có thể ngăn allow ACL khác khớp cùng request theo authorizer semantics. Vì vậy, thêm ALLOW mới không phải lúc nào cũng khắc phục được lỗi authorization.

~~~text
ALLOW User:orders-producer WRITE TOPIC orders.events
DENY  User:*               WRITE TOPIC orders.events
~~~

Đây là ví dụ minh họa xung đột policy. Đọc ACL match và broker logs trước khi thay đổi; không xóa deny ACL diện rộng nếu đó là policy bảo mật có chủ đích.

Principal superuser có thể được bypass authorization theo cấu hình authorizer. Không dùng superuser credential cho ứng dụng producer thường ngày.

## 10. Xóa ACL khi thu hồi quyền

Khi service ngừng sử dụng topic hoặc principal bị thu hồi, xóa đúng ACL đã cấp:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --remove \
  --allow-principal User:orders-producer \
  --operation Write \
  --topic orders.events \
  --force
~~~

Cú pháp `--force`/confirmation tùy Kafka CLI version. Trước khi remove, xác minh principal và resource, kiểm tra ACL có được dùng bởi instance khác không, lưu audit/change ticket và xác định rollback plan nếu xóa nhầm.

Không xóa tất cả ACL của principal nếu mục tiêu chỉ là thu hồi một topic.

## 11. Principal riêng cho từng producer service

Một nguyên tắc quan trọng là **mỗi workload có danh tính riêng**:

~~~text
User:orders-producer-prod
  WRITE -> orders.events
  IDEMPOTENT_WRITE -> cluster (nếu cần)

User:payments-producer-prod
  WRITE -> payments.events
  IDEMPOTENT_WRITE -> cluster (nếu cần)

User:shipping-producer-prod
  WRITE -> shipping.events
  IDEMPOTENT_WRITE -> cluster (nếu cần)
~~~

Nếu tất cả service dùng chung `User:application`, ACL không thể giới hạn blast radius theo service. Khi một credential bị lộ, attacker có thể sử dụng mọi quyền của principal chung.

Tách principal theo service/application, environment, producer role/consumer role, runtime identity/admin identity và tenant khi yêu cầu cách ly cao. Không dùng credential quản trị Kafka trong Spring Boot runtime chỉ để producer tự tạo topic.

## 12. Spring Boot cấu hình SASL/SCRAM và producer

Ví dụ cấu hình producer dùng SASL_SSL/SCRAM-SHA-512:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer" password="injected-secret";
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[enable.idempotence]": true
~~~

Ví dụ minh họa, cần điều chỉnh serializer, broker endpoints và cơ chế authentication theo môi trường. Secret nên được inject từ secret manager/environment, không commit vào YAML hoặc in ra log. Kiểm tra effective configuration trong ứng dụng, nhất là JAAS string có dấu chấm phẩy.

`acks=all` là lựa chọn durability/producer acknowledgment, không phải ACL. `enable.idempotence=true` là producer behavior, không tự cấp `IDEMPOTENT_WRITE` cho principal. Hai lớp cấu hình phải khớp.

### SASL authentication không tự cấp WRITE

Khi Spring Boot tạo producer, broker xác thực principal từ SASL. Sau đó ACL kiểm tra `WRITE`. Nếu SASL thành công nhưng ACL thiếu, ứng dụng vẫn nhận authorization exception.

Không giải quyết `TopicAuthorizationException` bằng cách thay password nếu authentication đã thành công và principal đúng. Kiểm tra broker logs và ACL trước khi xoay credential.

## 13. Spring Kafka transactional producer và transaction ID prefix

Spring Kafka có thể cấu hình Kafka transactions thông qua transaction ID prefix. Với Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-prod-
~~~

Spring Kafka dùng prefix để tạo transactional IDs cho producer instances. Các ID cuối cùng được sinh từ prefix và suffix theo cơ chế producer factory. Bảo đảm prefix **không xung đột giữa những ứng dụng/instance độc lập có thể chạy đồng thời**.

Cấp prefix ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --transactional-id orders-tx-prod- \
  --resource-pattern-type prefixed
~~~

Nếu nhiều environments dùng chung cluster, prefix nên chứa environment và service identity, chẳng hạn `orders-tx-prod-` và `orders-tx-staging-`. Không cấp một prefix chung như `orders-tx-` nếu principal không cần dùng transaction IDs của mọi môi trường.

### Producer fencing là vấn đề khác ACL

Nếu hai producer cùng dùng transactional ID, Kafka có thể fence producer cũ khi producer mới khởi tạo. Phân biệt:

- `TransactionalIdAuthorizationException`: principal không được phép dùng transactional ID.
- `ProducerFencedException`: producer đã mất quyền sử dụng transactional ID/epoch.
- `TopicAuthorizationException`: principal không được phép ghi topic.
- `ClusterAuthorizationException`: thiếu quyền cluster operation như idempotent write hoặc operation khác.

Sửa ACL không giải quyết transactional ID collision; tăng retry cũng không sửa identity design.

## 14. Producer có cần quyền CREATE topic không?

Thông thường **không** nếu topic được provision trước. Producer runtime chỉ cần ghi vào các topic đã được tạo và cấp ACL phù hợp.

Nếu ứng dụng dùng `KafkaAdmin` hoặc `NewTopic` beans để tự tạo topic lúc startup, AdminClient có thể cần quyền tạo/describe/configure topic theo API và cluster policy. Đây là quyền quản trị, nên cân nhắc tách:

~~~text
Provisioning identity:
  CREATE/ALTER/DESCRIBE_CONFIGS theo quy trình quản trị

Runtime producer identity:
  WRITE trên topic được chỉ định
  IDEMPOTENT_WRITE trên cluster nếu cần
  WRITE trên transactional ID nếu transactional
~~~

Tách provisioning identity khỏi runtime identity giúp giảm quyền của ứng dụng. Nếu phải tự động tạo topic, dùng principal quản trị có phạm vi hẹp và audit riêng; không cấp quyền CREATE/ALTER/DELETE cho mọi producer.

## 15. Schema Registry là lớp authorization riêng

Nhiều hệ thống dùng Avro, Protobuf hoặc JSON Schema. Producer có thể cần đăng ký/lấy schema từ Schema Registry trước khi serialize. **Kafka broker ACL không cấp quyền Schema Registry**.

Kafka ACL có thể cho phép `WRITE` topic `orders.events` nhưng Schema Registry vẫn từ chối đăng ký schema vào subject tương ứng. Producer sẽ lỗi serialization/registry trước khi gửi record thành công đến broker.

Khi producer không publish được, xác định lỗi nằm ở Kafka broker authentication, Kafka ACL, Schema Registry authorization, serialization/compatibility hay broker/network/producer send. Không cấp thêm `WRITE` Kafka topic để sửa lỗi Schema Registry.

## 16. Producer ghi nhiều topics cần ACL riêng

Một service có thể publish vào nhiều destinations:

~~~text
orders-service
  orders.events
  orders.audit
  orders.events.DLT
  orders.events-retry-2000
~~~

Liệt kê destinations thật sự: topic business output, retry topics, DLT, audit/outbox topics. Spring Kafka retry infrastructure có thể tạo hoặc sử dụng retry/DLT topics. Principal publish của retry infrastructure cần quyền phù hợp trên các destinations thực tế. Không chỉ cấp `WRITE` topic gốc rồi giả định retry/DLT cũng được phép.

Nếu dùng retry-topic auto creation, topic creation là trách nhiệm provisioning riêng. Kiểm tra Spring Kafka Admin setup và ACL cần thiết; đừng cấp `CREATE`/`ALTER` rộng cho runtime producer để làm startup “hết lỗi”.

DLT có thể dùng cùng principal nếu một workload sở hữu cả business output và DLT; hoặc dùng principal riêng nếu tổ chức muốn tách quyền vận hành/audit. Dù chọn cách nào, DLT permission cần có owner rõ ràng.

## 17. Các authorization exceptions thường gặp

| Exception | Nguyên nhân có thể | ACL cần kiểm tra |
|---|---|---|
| `TopicAuthorizationException` | Không có quyền ghi topic hoặc một trong các topics gửi tới | `TOPIC / WRITE` cho principal/topic. |
| `ClusterAuthorizationException` | Thiếu quyền cluster-level operation | `CLUSTER / IDEMPOTENT_WRITE` nếu producer idempotent; xem operation trong broker log. |
| `TransactionalIdAuthorizationException` | Không có quyền sử dụng transactional ID | `TRANSACTIONAL_ID / WRITE` cho ID thực tế/prefix. |
| `AuthenticationException` | Principal chưa được xác thực | SASL/TLS credential/mechanism, certificate, token. |
| `SerializationException` | Payload/schema/serializer lỗi | Serializer/schema contract; không phải Kafka topic ACL mặc định. |

Kafka client và Spring Kafka version có thể bọc exception khác nhau. Đọc **root cause** và broker authorization logs, không chỉ exception wrapper từ listener container.

Nhiều authorization exceptions là lỗi policy và không tự hết nếu ACL không thay đổi. Retry liên tục có thể tạo log storm. Khi quyền được cấp sau đó, producer có thể cần thử lại theo cách phù hợp với client lifecycle; nếu authz state không tự phục hồi, điều phối producer/container restart theo quy trình đã xác minh.

## 18. Quy trình cấp ACL least privilege

1. **Xác định workload:** service, environment, principal, owner.
2. **Liệt kê operations:** topic WRITE, idempotent write, transactional ID write và quyền phụ trợ thực sự cần.
3. **Liệt kê resources:** topic literal/prefix, cluster, transactional ID.
4. **Kiểm tra effective principal:** xác minh SASL/TLS tạo đúng principal.
5. **Kiểm tra ACL hiện tại:** list theo principal và resource.
6. **Tạo change:** cấp ACL nhỏ nhất cần thiết, có ticket/audit.
7. **Kiểm tra policy:** xác nhận không có DENY, host restriction hoặc pattern mismatch.
8. **Test producer:** gửi record kiểm thử có kiểm soát vào topic đúng.
9. **Kiểm tra kết quả:** producer ack, broker logs và consumer/offset nếu cần.
10. **Lưu bằng chứng:** principal, resource, operation, pattern và thời điểm.
11. **Theo dõi:** authorization errors và producer send rate sau thay đổi.
12. **Thu hồi:** xóa quyền khi workload/topic không còn sử dụng.

Không dùng principal quản trị để test ứng dụng runtime; làm vậy sẽ che giấu thiếu ACL của service principal.

## 19. Ví dụ ACL cho producer thường

Yêu cầu: service `orders-producer-prod` chỉ publish vào `orders.events`, dùng idempotence, không dùng transaction.

~~~bash
# Topic write
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --topic orders.events

# Idempotent write permission
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation IdempotentWrite \
  --cluster
~~~

Producer config:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer-prod" password="injected-secret";
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

Xác minh broker nhận đúng principal `User:orders-producer-prod`, topic ACL match `orders.events`, cluster ACL match cluster, producer send có ack theo policy và producer không được WRITE vào topic ngoài phạm vi. Không cần `ALL` trên cluster hoặc `CREATE` nếu topic đã được provision.

## 20. Ví dụ transactional producer end-to-end

Yêu cầu: service publish `orders.events.out` bằng Spring Kafka transaction với prefix `orders-tx-prod-`.

Topic ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --topic orders.events.out
~~~

Transactional ID ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --transactional-id orders-tx-prod- \
  --resource-pattern-type prefixed
~~~

Cluster idempotent ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation IdempotentWrite \
  --cluster
~~~

Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-prod-
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

Trong production, prefix cần unique giữa producer applications/instances theo cách Spring Kafka sinh transactional IDs. ACL prefixed pattern phải match ID thực tế. Prefix sai hoặc ACL prefix quá rộng có thể tạo lỗi authorization hoặc producer fencing.

## 21. Phân biệt quyền runtime và quyền AdminClient

Spring Boot có thể tự cấu hình KafkaAdmin/AdminClient cho thao tác quản trị, ví dụ tạo topic từ `NewTopic` bean. Nếu producer và AdminClient dùng cùng cấu hình common, chúng có thể cùng xác thực bằng một principal. Điều đó dễ dẫn đến cấp quyền quá rộng cho runtime service.

~~~text
Deployment / provisioning pipeline
  -> Admin principal
  -> Create/alter topics, partitions, configs

Application runtime
  -> Producer principal
  -> Write only to approved topics
  -> IdempotentWrite if required
  -> TransactionalId Write if required
~~~

Nếu bắt buộc app tạo topic lúc startup, hãy xác định có thật sự cần runtime auto-create không, topic provision ngoài app có tốt hơn không, Admin credentials có thể tách riêng không và quyền CREATE/ALTER có thể giới hạn theo prefix cụ thể không.

Không cấp `CLUSTER / ALL` để làm KafkaAdmin hoạt động nếu chỉ cần tạo một số topic. Tìm operation/resource mà Admin API thực sự yêu cầu theo Kafka version.

## 22. Secret rotation và principal lifecycle

Khi credential bị rotate:

1. Cấp/đổi credential ở identity provider/broker theo quy trình.
2. Xác minh principal mapping vẫn đúng.
3. Cập nhật secret store và ứng dụng theo chiến lược rolling.
4. Xác nhận producer mới authenticate đúng.
5. Xác nhận ACL của principal mới tương đương phạm vi được phê duyệt.
6. Quan sát producer send và authorization failures.
7. Thu hồi credential cũ sau khi các instances cũ đã ngừng.

Nếu rotation đồng thời đổi username/principal, ACL của principal cũ không tự chuyển sang principal mới. Producer có thể authenticate thành công với principal mới nhưng bị `TopicAuthorizationException` vì chưa có ACL.

Không log JAAS config, password, OAuth bearer token hoặc private key khi điều tra. Dùng principal name và exception category làm metadata an toàn hơn.

## 23. ACL drift giữa môi trường

Một service chạy ở dev có thể publish bình thường nhưng production bị deny do ACL khác nhau. Đừng suy luận từ config code rằng quyền trên cluster đã giống nhau.

Quản lý policy dưới dạng infrastructure-as-code hoặc quy trình change có audit:
- Principal mapping theo environment.
- Topic/transactional ID resource patterns.
- Allowed operations và deny rules.
- Authorizer/superuser config.
- ACL verification output.
- Change owner và rollback plan.

Không nhất thiết dùng cùng principal ở dev và production. Tách danh tính giúp giảm nguy cơ credential môi trường thấp được dùng truy cập dữ liệu production.

## 24. Kiểm thử producer ACL trong môi trường tích hợp

Một test thực tế nên chạy với broker bật authentication và ACL, không chỉ broker test mặc định mở quyền.

1. Tạo principal test `User:orders-producer-test`.
2. Cấp `WRITE` trên `orders.events.test`.
3. Cấp `IDEMPOTENT_WRITE` nếu producer bật idempotence.
4. Khởi chạy Spring Boot producer với đúng SASL principal.
5. Gửi record đến topic được phép và xác nhận send result.
6. Gửi thử đến `payments.events.test` không được cấp quyền; xác nhận authorization failure.
7. Nếu test transaction, cấp transactional ID prefix và xác nhận `initTransactions`/send/commit thành công.
8. Thu hồi transactional ID ACL rồi xác minh producer nhận đúng authorization error.
9. Thu hồi topic WRITE và xác minh producer không còn publish được.
10. Dọn topic/principal/ACL test theo quy trình.

Không dùng credential hoặc topic production để cố ý tạo deny trong test. Test cần xác nhận **least privilege**: producer được ghi đúng nơi cần và bị từ chối ở nơi không được phép. Một test chỉ xác nhận send vào topic được phép chưa đủ phát hiện overpermission.

## 25. Observability cho producer authorization

Metric/log cần phân biệt authentication, authorization, serialization, network và broker availability.

| Tín hiệu | Ý nghĩa |
|---|---|
| `TopicAuthorizationException` count | Principal bị từ chối ghi topic. |
| `ClusterAuthorizationException` count | Cluster-level operation bị từ chối. |
| `TransactionalIdAuthorizationException` count | Transactional ID ACL không phù hợp. |
| `AuthenticationException` count | SASL/TLS/OAuth authentication thất bại. |
| Producer send error rate | Tất cả lỗi gửi, cần phân loại nguyên nhân. |
| Producer request latency | Broker/network/send path chậm. |
| Record send success rate | Số send operations thành công theo instrumentation. |
| Transaction abort/fencing | Transaction lifecycle có vấn đề. |
| DLT/retry send failures | Quyền publish ở destinations phụ có thiếu không. |

Không đưa exception message đầy đủ hoặc principal/tenant tùy ý vào metric label nếu làm cardinality cao. Ghi principal/resource trong structured logs với quyền truy cập phù hợp.

Ví dụ quan sát KafkaTemplate send:

~~~java
kafkaTemplate.send("orders.events", orderId, event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Kafka publish failed: topic={}, errorType={}",
                        "orders.events",
                        exception.getClass().getSimpleName());
            }
            else {
                log.debug(
                        "Kafka publish acknowledged: topic={}, partition={}, offset={}",
                        result.getRecordMetadata().topic(),
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset());
            }
        });
~~~

Ví dụ dùng API `CompletableFuture` trong các phiên bản Spring Kafka hiện đại; một số version cũ trả `ListenableFuture`. Không log payload hoặc key nếu key chứa PII. Callback này đo send operation; với transactional producer, send future hoàn tất chưa chắc transaction đã commit.

## 26. Lỗi producer ACL và retry policy

Authorization failure thường là lỗi policy, không phải lỗi mạng thoáng qua. Nếu producer retry liên tục, log volume tăng, buffer có thể giữ records, listener source có thể chờ send khi transaction và retry/DLT forwarding có thể tiếp tục thất bại.

Không đặt retry vô hạn để chờ ACL. Khi phát hiện authorization exception:
1. Ghi nhận principal, resource và operation bị từ chối.
2. Dừng retry vô ích hoặc áp dụng backoff phù hợp.
3. Gửi cảnh báo tới owner Kafka ACL.
4. Cấp quyền đúng qua quy trình.
5. Kiểm tra producer/client có tiếp tục hoạt động hay cần recreate.
6. Xác minh send result và transaction outcome sau khi ACL cập nhật.

Đối với DLT, nếu producer không có quyền ghi DLT, record lỗi gốc có thể không được recover an toàn. Không cho offset nguồn tiến như thể recovery thành công nếu DLT send chưa được xác nhận theo policy.

## 27. Runbook: TopicAuthorizationException khi publish

1. Ghi exception class, topic đích, application instance và thời điểm.
2. Xác minh principal thực tế broker nhận được từ SASL/TLS.
3. Liệt kê ACL cho đúng principal và topic bằng `kafka-acls.sh --list`.
4. Kiểm tra operation `WRITE`, resource pattern type, host và DENY ACL.
5. Kiểm tra producer có gửi vào topic khác do typo hoặc routing không.
6. Nếu retry/DLT, kiểm tra cả các destination topics đó.
7. Cấp đúng `WRITE` ACL qua change process.
8. Gửi record test và xác minh broker ack.
9. Theo dõi error rate và backlog sau khi khôi phục.

Không cấp `ALL` cho principal chỉ để hết lỗi. Không đổi SASL password nếu authentication đã thành công và exception là authorization.

## 28. Runbook: ClusterAuthorizationException với idempotent producer

1. Xác minh producer effective config có bật idempotence không.
2. Kiểm tra Kafka client version và broker authorization requirements.
3. Đọc broker log để xác định cluster operation bị từ chối.
4. Liệt kê ACL trên cluster resource cho principal.
5. Xác minh `IDEMPOTENT_WRITE` được cấp đúng principal và cluster.
6. Không thay `acks`/idempotence một cách ngẫu nhiên để né lỗi.
7. Cấp ACL tối thiểu theo policy.
8. Restart/recreate producer chỉ khi client state yêu cầu.
9. Xác minh send result và retry/transaction behavior.

Tắt idempotence có thể thay đổi delivery behavior và duplicate risk; không coi đó là biện pháp sửa ACL mặc định.

## 29. Runbook: TransactionalIdAuthorizationException

1. Lấy transactional ID thực tế từ producer/broker logs.
2. Xác định prefix Spring Kafka đang cấu hình và suffix được sinh ra.
3. Liệt kê ACL cho resource `TRANSACTIONAL_ID` với pattern phù hợp.
4. Xác minh principal có `WRITE` trên đúng ID/prefix.
5. Kiểm tra ACL có bị giới hạn host hoặc có DENY match không.
6. Phân biệt authorization failure với producer fencing.
7. Cấp `WRITE` transactional ID ACL theo prefix hẹp.
8. Xác minh producer `initTransactions`, send và commit transaction.
9. Theo dõi transaction abort và consumer offset.

Không cấp quyền `WRITE` trên toàn bộ transactional IDs nếu service chỉ cần một prefix.

## 30. Runbook: Authentication thành công nhưng ACL không khớp

1. Kiểm tra broker logs để lấy principal đã xác thực.
2. So sánh principal đó với `--allow-principal` trong ACL.
3. Kiểm tra mapping của SASL user, TLS DN hoặc OAuth principal.
4. Xác minh môi trường/cluster endpoint có đúng không.
5. Kiểm tra ACL resource name và pattern.
6. Kiểm tra host restriction và DENY.
7. Cấp hoặc sửa ACL cho principal đúng, không dùng admin principal làm workaround.
8. Gửi thử một record và lưu bằng chứng.

Tên username trong JAAS không nhất thiết được map theo cách bạn giả định; broker principal builder/mapping có thể thay đổi principal string.

## 31. Runbook: Producer ghi topic chính được nhưng DLT/retry publish thất bại

1. Xác định destination retry/DLT topic thực tế.
2. Lấy principal của producer template/recoverer đang publish.
3. Kiểm tra `WRITE` ACL cho từng destination.
4. Nếu dùng idempotence, kiểm tra cluster `IDEMPOTENT_WRITE`.
5. Nếu transactional, kiểm tra `TRANSACTIONAL_ID / WRITE`.
6. Xác minh template serializer hỗ trợ record lỗi (có thể là raw bytes).
7. Xác nhận send result/ack và recovery callback.
8. Không để source offset commit nếu DLT handoff chưa thành công theo policy.
9. Sau khi sửa, replay/test một record đại diện và xác minh không mất/nhân đôi.

## 32. Runbook: Producer mới bị deny sau secret rotation

1. Xác định username/principal trước và sau rotation.
2. Kiểm tra client hiện tại đã reload secret hay còn dùng credential cũ.
3. Xác minh principal mới đã được tạo và được map đúng.
4. Kiểm tra ACL của principal mới trên topic/cluster/transactional ID.
5. Cấp quyền tối thiểu tương đương theo change approval.
6. Rolling restart/recreate producer theo cơ chế an toàn nếu client không reload.
7. Xác minh broker auth logs, send ack và transaction commit.
8. Chỉ thu hồi principal cũ sau khi tất cả instances đã chuyển.

Không copy toàn bộ quyền `ALL` từ principal cũ sang principal mới; tái xác nhận scope cần thiết.

## 33. Runbook: Producer bị fencing sau khi cấp ACL

1. Đọc exception gốc: `ProducerFencedException` khác `TransactionalIdAuthorizationException`.
2. Kiểm tra transactional ID thực tế của các instances.
3. Tìm prefix trùng giữa pods, services hoặc environments.
4. Kiểm tra rollout overlap và process cũ chưa dừng.
5. Xác nhận mỗi producer instance có identity theo thiết kế.
6. Sửa prefix/instance ID và ACL pattern tương ứng.
7. Khởi tạo producer mới sau khi identity được sửa.
8. Kiểm tra transaction abort/commit và input offsets.
9. Theo dõi fencing sau deployment.

ACL đúng không loại bỏ nguy cơ hai producer tranh cùng transactional ID.

## 34. Bảng kiểm soát ACL cho producer

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Identity | Broker xác thực producer thành principal nào? | Broker auth logs, SASL/TLS/OAuth mapping. |
| Topic scope | Producer chỉ được WRITE đúng topics? | ACL list theo principal/resource. |
| Idempotence | Producer có bật idempotence không và cần cluster ACL nào? | Effective producer config, `IDEMPOTENT_WRITE`. |
| Transactions | Transactional ID thực tế/prefix có match ACL? | Producer logs và `TRANSACTIONAL_ID / WRITE`. |
| Topic provisioning | Runtime producer có thực sự cần CREATE? | `NewTopic`/KafkaAdmin config và provisioning workflow. |
| Retry/DLT | Tất cả destination topics có WRITE phù hợp? | Retry/DLT topology và ACL list. |
| Pattern | Literal/prefixed pattern có quá rộng không? | ACL resource pattern và topic inventory. |
| Deny/host | Có DENY hoặc host restriction đang chặn? | Effective ACL evaluation và broker logs. |
| Secret | Credential được quản lý/rotate an toàn? | Secret manager, deployment history. |
| Schema Registry | Producer có quyền registry riêng nếu cần? | Registry ACL/auth logs. |
| Observability | Authorization failures có được phân loại? | Exception metrics, structured logs. |
| Testing | Positive và negative ACL tests đều pass? | Integration tests với broker bật ACL. |
| Recovery | Retry/DLT send failure có giữ offset an toàn? | Producer ack, recovery result, committed offset. |
| Audit | Thay đổi ACL có owner, approval và rollback? | Change ticket, ACL snapshot. |

**Kết luận:** ACL cho producer cần được cấp theo **principal, resource và operation** cụ thể. Producer ghi topic thông thường cần `WRITE` trên topic; producer idempotent cần thêm `IDEMPOTENT_WRITE` trên cluster resource; producer transactional cần `WRITE` trên transactional ID và các topic đích. Dùng principal riêng theo service/environment, literal hoặc prefix pattern hẹp, tách runtime producer khỏi admin provisioning, và xác minh cả positive lẫn negative permissions. Khi gặp authorization exception, kiểm tra principal broker thực tế, topic/transactional ID, ACL pattern, DENY và operation bị từ chối trước khi thay credential hoặc restart. Least-privilege ACL giới hạn blast radius và giữ cho producer, retry/DLT cùng Kafka transactions hoạt động đúng phạm vi được phê duyệt.
