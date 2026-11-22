# Authorization failure

## 1. Authorization trong Kafka là gì?

Kafka bảo vệ tài nguyên bằng cơ chế xác thực danh tính và kiểm tra quyền truy cập. Sau khi client kết nối tới broker, Kafka cần xác định client là principal nào và principal đó được phép thực hiện thao tác gì trên tài nguyên nào.

**Authentication** xác định client là ai. **Authorization** quyết định client đã được xác thực có được phép thực hiện hành động đang yêu cầu hay không.

Ví dụ, một Spring Boot service có thể đăng nhập thành công vào Kafka bằng SASL/SCRAM nhưng vẫn bị từ chối khi ghi vào topic `orders.created`. Khi đó, thông tin đăng nhập đã được chấp nhận, nhưng principal của service không có quyền `WRITE` trên topic.

Authorization failure thường xuất hiện khi:

- Producer gửi record tới topic mà principal không có quyền ghi.
- Consumer đọc topic mà principal không có quyền đọc.
- Consumer tham gia group hoặc commit offset mà principal không có quyền trên group.
- Producer sử dụng Kafka transaction nhưng không có quyền trên transactional ID.
- Ứng dụng gọi AdminClient để tạo, mô tả hoặc thay đổi tài nguyên mà principal không được phép thao tác.
- Error handler gửi record sang dead-letter topic (DLT) nhưng producer dùng để publish DLT không có quyền ghi topic đích.

Trong Spring Kafka, các lỗi này có thể xuất hiện lúc khởi tạo producer/consumer, khi lấy metadata, trong poll, khi commit offset hoặc khi gửi record. Listener không nhất thiết được gọi trước khi lỗi xảy ra.

## 2. Phân biệt Authentication failure và Authorization failure

Hai loại lỗi có cách xử lý khác nhau:

| Loại lỗi | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication failure | Client có chứng minh được danh tính không? | Sai username/password SASL, cơ chế SASL không khớp, chứng chỉ TLS không hợp lệ |
| Authorization failure | Principal đã xác thực có quyền thao tác trên resource không? | Thiếu quyền READ trên topic hoặc READ trên consumer group |

Một số dấu hiệu trong log:

- `SaslAuthenticationException`: SASL authentication thất bại.
- `AuthenticationException`: lỗi xác thực ở tầng Kafka client.
- `TopicAuthorizationException`: principal không được phép thực hiện thao tác cần thiết trên topic.
- `GroupAuthorizationException`: principal không có quyền cần thiết trên consumer group.
- `ClusterAuthorizationException`: thao tác cần quyền ở phạm vi cluster bị từ chối.
- `TransactionalIdAuthorizationException`: producer không có quyền cần thiết trên transactional ID.
- `AuthorizationException`: lớp lỗi authorization tổng quát trong Kafka client.

Tên exception và thông tin chi tiết phụ thuộc phiên bản Kafka client, broker và API đang được gọi. Hãy xem exception gốc và log broker để xác định principal, resource và operation bị từ chối.

### 2.1. Ví dụ: xác thực thành công nhưng ghi topic thất bại

Giả sử service đăng nhập bằng principal `User:orders-service`. Broker chấp nhận SASL authentication. Sau đó producer gửi record tới `orders.created`, nhưng ACL không cấp `WRITE` cho principal này.

Luồng xử lý:

~~~text
Spring Boot application
       |
       | SASL authentication
       v
Kafka broker
       |
       | Principal = User:orders-service
       | Authentication: SUCCESS
       v
Producer sends to orders.created
       |
       | Authorization check: WRITE
       v
ACL evaluation
       |
       | No matching allow permission
       v
AuthorizationException
       |
       v
Send fails
~~~

Thay password trong trường hợp này không giải quyết được vấn đề. Cần cấp đúng quyền cho principal trên resource tương ứng, sau khi xác nhận service đang dùng principal nào.

## 3. Principal, resource, operation và ACL

Kafka ACL (Access Control List) mô tả principal nào được phép hoặc bị từ chối thực hiện operation trên resource.

Một quyết định authorization thường phụ thuộc vào:

- **Principal:** danh tính client, thường có dạng `User:...`.
- **Resource type:** loại tài nguyên, ví dụ Topic, Group, Cluster hoặc TransactionalId.
- **Resource name:** tên topic, group ID, transactional ID hoặc tài nguyên tương ứng.
- **Operation:** hành động như READ, WRITE, CREATE, DESCRIBE hoặc ALTER.
- **Permission type:** ALLOW hoặc DENY.
- **Host:** phạm vi địa chỉ client nếu ACL có giới hạn host.
- **Resource pattern:** ACL áp dụng cho tên resource cụ thể, prefix hoặc pattern được hỗ trợ.

Ví dụ về một ACL:

~~~text
Principal: User:orders-service
Resource: Topic:orders.created
Operation: WRITE
Permission: ALLOW
Host: *
~~~

Quyền trên cho phép principal `User:orders-service` ghi topic `orders.created` từ host được ACL cho phép.

### 3.1. Các resource type thường gặp

| Resource | Dùng cho |
|---|---|
| Topic | Đọc, ghi, mô tả hoặc thay đổi topic |
| Group | Tham gia consumer group và quản lý offset |
| Cluster | Các thao tác cấp cluster, ví dụ quyền idempotent write hoặc thao tác quản trị |
| TransactionalId | Producer transaction và fencing theo transactional ID |
| DelegationToken | Các thao tác liên quan delegation token |

Tên principal không nhất thiết luôn là username SASL. Với TLS client authentication, principal có thể được tạo từ distinguished name (DN) của chứng chỉ. Broker có thể áp dụng principal mapping rules để chuẩn hóa tên. Vì vậy, ACL phải khớp với principal mà broker thực sự nhìn thấy.

### 3.2. Các operation thường gặp

| Operation | Ý nghĩa điển hình |
|---|---|
| READ | Đọc dữ liệu topic hoặc tham gia/đọc trạng thái group theo resource type |
| WRITE | Ghi dữ liệu vào topic hoặc sử dụng transactional ID theo ngữ cảnh |
| CREATE | Tạo tài nguyên |
| DELETE | Xóa tài nguyên |
| ALTER | Thay đổi tài nguyên |
| DESCRIBE | Đọc metadata của resource |
| DESCRIBE_CONFIGS | Đọc cấu hình resource |
| ALTER_CONFIGS | Thay đổi cấu hình resource |
| IDEMPOTENT_WRITE | Dùng cơ chế idempotent producer ở phạm vi cluster |
| CLUSTER_ACTION | Một số thao tác nội bộ hoặc quản trị cấp cluster |

Một số operation có quan hệ bao hàm trong mô hình ACL của Kafka. Ví dụ, quyền READ hoặc WRITE trên topic thường bao hàm quyền DESCRIBE cần thiết cho thao tác tương ứng. Không nên cấp tất cả operation chỉ để xử lý một lỗi; hãy cấp quyền tối thiểu theo resource và API thực tế.

## 4. Quyền cần thiết cho producer

Producer thông thường cần quyền ghi trên topic đích:

~~~text
Principal: User:orders-service
Resource: Topic:orders.created
Operation: WRITE
Permission: ALLOW
~~~

Nếu producer cần mô tả metadata topic, quyền tương ứng có thể được bao hàm bởi quyền WRITE trên topic trong mô hình ACL chuẩn của Kafka. Nếu ứng dụng thực hiện thêm thao tác AdminClient, hãy xem operation riêng cho các API đó.

### 4.1. Idempotent producer

Với producer bật `enable.idempotence=true`, một số phiên bản/cấu hình Kafka yêu cầu quyền `IDEMPOTENT_WRITE` trên resource Cluster. Đây là quyền khác với `WRITE` trên topic.

Điều này đặc biệt cần kiểm tra khi ứng dụng nâng cấp Kafka client hoặc bật idempotence tường minh. Kafka client hiện đại có thể bật idempotence mặc định, vì vậy một service trước đây chỉ cần quyền ghi topic có thể bắt đầu yêu cầu thêm quyền cluster-level trong môi trường ACL nghiêm ngặt. Hành vi cụ thể phụ thuộc phiên bản broker/client và cấu hình authorizer; hãy đối chiếu lỗi broker thực tế trước khi cấp.

### 4.2. Producer gửi DLT

Nếu Spring Kafka dùng `DeadLetterPublishingRecoverer` để gửi record lỗi sang topic như `orders.created.DLT`, producer của recoverer cần quyền WRITE trên topic DLT. Quyền WRITE trên topic gốc không tự động cấp quyền ghi cho DLT.

Ví dụ luồng:

~~~text
Consumer reads orders.created
       |
       v
Listener processing fails
       |
       v
Error handler retries
       |
       v
Recovery publishes to orders.created.DLT
       |
       v
Kafka checks WRITE on orders.created.DLT
~~~

Nếu DLT publish thất bại do authorization, lỗi gốc và lỗi gửi DLT cần được phân biệt trong log. Cần kiểm tra principal mà KafkaTemplate/recoverer đang dùng, topic DLT thực tế và ACL của topic đó.

## 5. Quyền cần thiết cho consumer

Consumer cần quyền READ trên topic và quyền READ trên consumer group để tham gia group và quản lý offset.

Ví dụ:

~~~text
Principal: User:orders-fulfillment
Resource: Topic:orders.created
Operation: READ
Permission: ALLOW

Principal: User:orders-fulfillment
Resource: Group:order-fulfillment
Operation: READ
Permission: ALLOW
~~~

Hai quyền này bảo vệ hai loại tài nguyên khác nhau:

- READ trên topic cho phép consumer đọc record.
- READ trên group cho phép consumer thực hiện các thao tác cần thiết với consumer group, bao gồm tham gia group và commit offset theo flow tương ứng.

Có quyền đọc topic nhưng thiếu quyền group có thể khiến consumer không khởi động được group membership hoặc không commit offset như mong muốn. Ngược lại, có quyền group nhưng thiếu READ trên topic vẫn không cho phép đọc dữ liệu.

### 5.1. Consumer đọc nhiều topic

Nếu listener subscribe nhiều topic, principal cần quyền phù hợp trên từng topic mà listener đọc. Với pattern subscription, có thể dùng ACL resource pattern phù hợp, nhưng phải bảo đảm prefix không bao phủ ngoài phạm vi cần thiết.

Ví dụ service đọc:

- `orders.created`
- `orders.updated`
- `orders.cancelled`

thì quyền READ cần áp dụng cho cả ba topic hoặc cho một prefix đã được thiết kế riêng, chẳng hạn `orders.`, nếu chính sách bảo mật cho phép.

### 5.2. Retry topic và DLT consumer

Nếu ứng dụng dùng retry topic hoặc DLT topic, consumer đọc các topic này cũng cần READ trên resource tương ứng. Không nên chỉ cấp quyền cho topic gốc rồi bỏ qua các topic được tạo bởi retry/DLT mechanism.

## 6. Quyền cho transactional producer

Kafka transaction dùng transactional ID để xác định producer transaction. Producer cần quyền phù hợp trên transactional ID, ngoài quyền ghi trên các topic đầu ra.

Ví dụ quyền:

~~~text
Principal: User:orders-transactional-producer
Resource: TransactionalId:orders-tx-
Operation: WRITE
Permission: ALLOW
Pattern: PREFIXED
~~~

Tên prefix phải khớp với transactional ID prefix mà Spring Kafka sử dụng. Spring Kafka có thể tạo transactional ID riêng cho các producer instance dựa trên prefix và suffix nội bộ. Nếu ACL chỉ cấp cho một tên chính xác trong khi producer dùng các tên con khác, transaction có thể bị từ chối.

Với Spring Boot, transaction ID prefix có thể cấu hình như sau:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
~~~

Producer transaction cũng cần quyền ghi trên các topic đầu ra. Nếu dùng consume-transform-produce, consumer còn cần quyền READ trên topic đầu vào và READ trên group để xử lý offset. Khi có lỗi `TransactionalIdAuthorizationException`, kiểm tra transactional ID thực tế trong broker log thay vì đoán từ tên bean hoặc listener ID.

## 7. Cấu hình bảo mật trong Spring Boot

Spring Boot chuyển các property bảo mật chung tới Kafka clients được auto-configure. Ví dụ dưới đây minh họa SASL/SCRAM qua TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093,kafka-2.example.net:9093
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-service" password="<inject-from-secret>";'
~~~

Trong môi trường thật, password phải được lấy từ secret manager hoặc secret injection của nền tảng triển khai. Không commit password, token hoặc private key vào source control, file cấu hình chia sẻ hay log.

Nếu dùng TLS truststore riêng, có thể cấu hình thêm:

~~~yaml
spring:
  kafka:
    properties:
      "[ssl.truststore.location]": /run/secrets/kafka/truststore.p12
      "[ssl.truststore.type]": PKCS12
      "[ssl.truststore.password]": "<inject-from-secret>"
~~~

Với mutual TLS, client còn cần keystore và private key phù hợp. Khi dùng SASL_SSL, TLS bảo vệ kết nối còn SASL xác thực principal; hai lớp có vai trò khác nhau.

### 7.1. Cấu hình riêng producer và consumer

Nếu producer và consumer dùng cùng principal, có thể dùng security properties chung. Nếu mỗi thành phần cần principal riêng, có thể cấu hình producer/consumer properties hoặc tạo các factory riêng với cấu hình xác thực tương ứng.

Ví dụ cấu hình consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="<inject-from-secret>";'
~~~

Producer có thể dùng principal khác với quyền WRITE, trong khi consumer dùng principal chỉ có READ. Cách tách này hỗ trợ least privilege, nhưng cần kiểm tra AdminClient, KafkaTemplate, retry publisher và DLT recoverer đang dùng factory/principal nào.

### 7.2. Security properties không cấp ACL

Khai báo `security.protocol`, `sasl.mechanism`, username và password chỉ cấu hình cách client kết nối và xác thực. Các property này không tự tạo ACL trên broker.

Quyền truy cập được quản lý ở broker authorizer. Khi cần cấp quyền, phải thay đổi ACL qua quy trình quản trị Kafka phù hợp; sửa application.yml không thể tự cấp quyền trên cluster.

## 8. Bật và quản lý ACL ở broker

Kafka cần authorizer phù hợp để thực thi ACL. Với Kafka chạy KRaft, cấu hình thường dùng StandardAuthorizer:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
super.users=User:admin
allow.everyone.if.no.acl.found=false
~~~

Với cluster dùng ZooKeeper hoặc phiên bản cũ, authorizer class và cách quản lý ACL có thể khác. Hãy dùng tài liệu phù hợp với phiên bản Kafka và mode triển khai hiện tại.

`super.users` là danh sách principal có quyền quản trị đặc biệt. Chỉ đưa principal quản trị được kiểm soát vào danh sách này. Không thêm service application vào super.users để né lỗi authorization.

`allow.everyone.if.no.acl.found` có thể thay đổi hành vi khi resource chưa có ACL. Trong môi trường cần kiểm soát truy cập, không bật chế độ cho phép mọi người chỉ để làm biến mất lỗi. Hãy cấp ACL cụ thể cho principal và resource cần thiết.

## 9. Kiểm tra và cấp ACL bằng kafka-acls

Kafka cung cấp công cụ `kafka-acls.sh` để liệt kê, thêm và xóa ACL. Cần dùng tài khoản quản trị có quyền phù hợp và file command config an toàn.

Ví dụ file `admin.properties` chứa cấu hình kết nối bảo mật của principal quản trị. Không đưa secret vào command line hoặc chia sẻ file này.

### 9.1. Xem ACL hiện tại

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.created
~~~

Nếu cần kiểm tra group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --list \
  --group order-fulfillment
~~~

Đọc kết quả để xác nhận principal, operation, resource pattern và host có khớp với request bị từ chối hay không.

### 9.2. Cấp quyền ghi topic cho producer

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.created
~~~

Nếu producer cần idempotent write và broker/client version yêu cầu quyền cluster-level:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service \
  --operation IdempotentWrite \
  --cluster
~~~

Chỉ cấp quyền cluster-level khi xác nhận lỗi và phiên bản triển khai yêu cầu. Quyền này rộng hơn một quyền ghi trên một topic, vì vậy cần được phê duyệt theo chính sách least privilege.

### 9.3. Cấp quyền đọc topic và group

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-fulfillment \
  --operation Read \
  --topic orders.created
~~~

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-fulfillment \
  --operation Read \
  --group order-fulfillment
~~~

### 9.4. Cấp quyền cho DLT

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.created.DLT
~~~

Nếu consumer cần đọc DLT để điều tra hoặc replay, cấp READ trên DLT và READ trên group tương ứng cho principal consumer đó.

### 9.5. Cấp quyền transactional ID theo prefix

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-transactional-producer \
  --operation Write \
  --transactional-id orders-tx- \
  --resource-pattern-type prefixed
~~~

Cú pháp option có thể khác nhẹ giữa phiên bản Kafka CLI. Luôn kiểm tra `kafka-acls.sh --help` và phiên bản công cụ đi kèm cluster trước khi chạy lệnh quản trị.

### 9.6. Xác nhận sau khi cấp

Sau khi thay đổi ACL:

1. Liệt kê lại ACL của resource.
2. Xác nhận principal đúng như broker nhận diện.
3. Kiểm tra resource name và pattern type.
4. Kiểm tra operation được cấp.
5. Thử lại thao tác nhỏ bằng đúng credential của service.
6. Xác nhận producer gửi thành công hoặc consumer tham gia group, đọc và commit được offset.
7. Theo dõi broker log để bảo đảm không còn authorization denial cho resource đó.

Không dùng principal quản trị để thử thay cho principal ứng dụng. Kiểm tra bằng credential thật của service mới xác nhận được quyền của service.

## 10. Các loại authorization failure thường gặp trong Spring Kafka

| Exception hoặc log | Resource/operation thường liên quan | Cách kiểm tra |
|---|---|---|
| `TopicAuthorizationException` | Topic READ, WRITE, DESCRIBE hoặc operation topic khác | Xác nhận topic và principal, kiểm tra ACL đúng operation |
| `GroupAuthorizationException` | Group READ hoặc thao tác group | Kiểm tra group ID thực tế và ACL trên Group |
| `ClusterAuthorizationException` | Operation cấp cluster như idempotent write hoặc Admin API | Xem operation bị từ chối và quyền Cluster |
| `TransactionalIdAuthorizationException` | TransactionalId WRITE | Xem transactional ID thực tế và ACL literal/prefixed |
| `AuthorizationException` | Operation không được phép, có thể không được mô tả bằng subclass cụ thể | Đọc broker log để tìm principal, resource và operation |
| `SaslAuthenticationException` | Authentication, không phải ACL authorization | Kiểm tra SASL mechanism, credential và JAAS config |

Một lỗi có thể xuất hiện trong producer future, consumer poll, offset commit hoặc AdminClient. Vì thế, cần tìm đúng thành phần phát request. Một ứng dụng có thể dùng nhiều principal hoặc nhiều factory khác nhau.

## 11. Chẩn đoán theo từng luồng Spring Kafka

### 11.1. Producer không gửi được record

Triệu chứng:

- `KafkaTemplate.send()` hoàn tất future với exception.
- Log có `TopicAuthorizationException`.
- Broker báo principal không có quyền WRITE trên topic.

Cách điều tra:

1. Xác định topic thực tế trong lời gọi `send()`, kể cả topic được chọn động.
2. Xác định producer factory/KafkaTemplate đang được dùng.
3. Kiểm tra principal sau authentication và mapping.
4. Xem ACL WRITE trên topic.
5. Nếu idempotence được bật, kiểm tra thêm khả năng thiếu IDEMPOTENT_WRITE trên Cluster theo phiên bản Kafka.
6. Thử gửi lại bằng đúng credential sau khi ACL được cập nhật.

Ví dụ callback để ghi nhận lỗi:

~~~java
kafkaTemplate.send("orders.created", orderId, event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            log.error(
                "Kafka publish failed, topic={}, orderId={}",
                "orders.created",
                orderId,
                exception
            );
            return;
        }

        log.info(
            "Kafka publish acknowledged, topic={}, partition={}, offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset()
        );
    });
~~~

Callback giúp quan sát lỗi bất đồng bộ. Không log password, JAAS string hoặc secret khi ghi nhận lỗi.

### 11.2. Consumer không đọc được topic

Triệu chứng:

- Consumer không lấy được record.
- Log có `TopicAuthorizationException`.
- Consumer có thể thất bại ngay khi lấy metadata hoặc gọi poll.

Kiểm tra:

1. Topic subscription có đúng tên không?
2. Principal consumer có READ trên từng topic không?
3. Nếu subscribe pattern, ACL có bao phủ topic được match không?
4. Consumer có dùng đúng credential và ConsumerFactory không?
5. Broker log có ghi operation/topic cụ thể bị từ chối không?

Nếu consumer đọc nhiều topic, chỉ cấp quyền trên một topic có thể khiến listener vẫn lỗi khi chạm topic còn lại.

### 11.3. Consumer không tham gia group hoặc commit offset

Triệu chứng:

- Log có `GroupAuthorizationException`.
- Consumer không ổn định trong group hoặc commit offset thất bại.
- Consumer đọc được metadata topic nhưng group operation bị từ chối.

Kiểm tra READ trên group ID thực tế. Group ID có thể được cấu hình ở `spring.kafka.consumer.group-id`, trên `@KafkaListener(groupId=...)` hoặc trong custom container properties. ACL phải khớp với giá trị hiệu lực của listener.

### 11.4. Transaction hoặc DLT publish thất bại

Với transactional producer, kiểm tra:

- Transactional ID prefix cấu hình trong Spring Boot.
- Transactional ID thực tế do producer instance sử dụng.
- WRITE trên transactional ID.
- WRITE trên topic đầu ra.
- IDEMPOTENT_WRITE trên Cluster nếu phiên bản/config yêu cầu.

Với DLT, kiểm tra producer được recoverer sử dụng, topic đích và quyền WRITE. Nếu error handler dùng KafkaTemplate riêng, principal có thể khác với producer nghiệp vụ.

## 12. Authorization failure trong error handler

Authorization failure thường là lỗi cấu hình quyền hoặc danh tính, không phải lỗi xử lý record nghiệp vụ có thể giải quyết bằng retry thông thường.

Ví dụ, listener lỗi và error handler muốn gửi record sang DLT. Nếu DLT producer bị từ chối, việc retry DLT publish liên tục không tạo ra quyền WRITE. Tương tự, consumer thiếu quyền READ trên group không thể tự khắc phục bằng cách gọi poll nhiều lần.

Cách xử lý phù hợp:

- Ghi nhận exception gốc và resource bị từ chối.
- Không che lỗi bằng cách bắt exception rồi coi record đã xử lý thành công.
- Sửa ACL hoặc principal mapping theo quy trình bảo mật.
- Khôi phục listener/producer theo lifecycle và retry policy của phiên bản Spring Kafka đang chạy.
- Xác nhận record chưa bị mất hoặc commit nhầm trong quá trình phục hồi.

Không cấu hình retry dài hạn cho lỗi authorization nếu quyền chưa được sửa. Với lỗi không thể retry, cần để lỗi được phát hiện và chuyển tới quy trình vận hành phù hợp.

## 13. Principal mapping và môi trường triển khai

Một nguyên nhân phổ biến là ACL được cấp cho principal mà đội phát triển nghĩ ứng dụng đang dùng, nhưng broker nhận một principal khác.

Ví dụ SASL username `orders-service` có thể được ánh xạ thành principal `User:orders-service`. Với TLS client authentication, principal có thể được tạo từ subject DN của certificate, ví dụ `User:CN=orders-service,OU=Apps,O=Example`.

Các yếu tố cần kiểm tra:

- SASL mechanism và username thực tế.
- TLS client certificate subject nếu dùng mTLS.
- Principal builder hoặc mapping rules trên broker.
- Secret version đang được pod mount.
- Custom producer/consumer factory có override security properties không.
- Các pod cũ và mới có đang dùng credential khác nhau không.

Khi rotate secret, cần bảo đảm credential mới được cấp ACL tương ứng trước khi rollout service. Nếu đổi username, principal cũng có thể đổi và các ACL cũ không còn khớp.

## 14. Authorization và AdminClient

Spring Kafka hoặc ứng dụng có thể dùng AdminClient để kiểm tra topic, tạo topic, mô tả metadata hoặc quản trị cấu hình. Những API này cần quyền khác với quyền đọc/ghi record.

Ví dụ:

| Tác vụ | Resource/operation cần xem |
|---|---|
| Mô tả topic | DESCRIBE trên Topic |
| Tạo topic | CREATE ở phạm vi phù hợp với policy |
| Xóa topic | DELETE trên Topic |
| Thay đổi partition/config | ALTER hoặc ALTER_CONFIGS tương ứng |
| Đọc cấu hình topic | DESCRIBE_CONFIGS |
| Liệt kê/kiểm tra group | Operation group/cluster phù hợp với API và phiên bản |

Không cấp quyền quản trị rộng cho runtime service chỉ vì startup code có một lệnh kiểm tra topic. Có thể tách trách nhiệm tạo topic sang provisioning job hoặc principal quản trị, trong khi service runtime chỉ có quyền READ/WRITE cần thiết.

Nếu startup fail khi AdminClient kiểm tra hoặc tạo topic, cần xem API cụ thể trong broker log. Lỗi này có thể xảy ra trước khi listener bắt đầu xử lý record.

## 15. Least privilege và quản lý ACL an toàn

Một chính sách ACL tốt nên cấp đúng principal, resource và operation cần thiết:

- Tách principal producer và consumer nếu workload cần quyền khác nhau.
- Chỉ cấp WRITE trên topic producer thực sự phát.
- Chỉ cấp READ trên topic consumer thực sự đọc.
- Chỉ cấp READ trên group ID mà consumer dùng.
- Cấp quyền DLT/retry topic riêng cho principal thực sự publish hoặc consume chúng.
- Giới hạn transactional ID theo prefix dành riêng cho service.
- Tránh dùng super user cho application runtime.
- Tránh wildcard resource rộng nếu chỉ cần một tập topic nhỏ.
- Ghi lại owner, lý do, thời hạn và quy trình thu hồi ACL.

ACL DENY có thể ảnh hưởng kết quả dù có ACL ALLOW khác tùy cơ chế authorizer và cấu hình. Khi một quyền đã được cấp mà request vẫn bị từ chối, hãy kiểm tra cả deny rule, host constraint, resource pattern và principal mapping.

Không giải quyết lỗi bằng cách bật quyền truy cập cho mọi principal, tắt authorizer hoặc cấp toàn bộ quyền cluster. Cách làm đó che mất nguyên nhân và mở rộng phạm vi truy cập ngoài nhu cầu của service.

## 16. Quy trình xử lý Authorization failure

Khi nhận lỗi authorization trong production, có thể xử lý theo trình tự:

1. **Xác định thành phần phát request:** producer, consumer, listener container, DLT recoverer hay AdminClient.
2. **Đọc exception gốc:** lấy exception class, operation và resource nếu có.
3. **Đối chiếu broker log:** xác nhận principal, resource type/name, operation và host mà broker nhìn thấy.
4. **Kiểm tra authentication:** bảo đảm client đang đăng nhập bằng credential dự kiến.
5. **Kiểm tra ACL:** liệt kê ACL cho principal và resource; kiểm tra allow, deny, pattern và host.
6. **Xác định quyền tối thiểu:** topic READ/WRITE, group READ, transactional ID WRITE, cluster IDEMPOTENT_WRITE hoặc quyền Admin API tùy thao tác.
7. **Cập nhật ACL qua quy trình quản trị:** dùng principal quản trị và ghi nhận thay đổi.
8. **Thử lại bằng credential của service:** xác nhận thao tác cụ thể đã thành công.
9. **Khôi phục container/producer:** nếu client đã dừng hoặc ở trạng thái lỗi, thực hiện restart/recovery theo lifecycle của ứng dụng và phiên bản thư viện.
10. **Theo dõi sau khôi phục:** kiểm tra consumer lag, publish errors, DLT backlog, commit failures và record bị replay.
11. **Ghi lại nguyên nhân:** cập nhật runbook và ma trận quyền cho service.

Không nên chỉ dựa vào thông báo chung “Not authorized”. Broker log thường là nguồn quan trọng nhất để xác định principal và operation chính xác.

## 17. Ví dụ tổng hợp: Order Service

Giả sử có hai thành phần:

- Order API producer dùng principal `User:orders-api`.
- Fulfillment consumer dùng principal `User:orders-fulfillment`.

Producer ghi vào topic `orders.created`; consumer đọc topic đó bằng group `order-fulfillment`. Khi xử lý lỗi, producer DLT của service gửi sang `orders.created.DLT`.

Ma trận quyền có thể như sau:

| Principal | Resource | Operation |
|---|---|---|
| `User:orders-api` | Topic `orders.created` | WRITE |
| `User:orders-api` | Cluster | IDEMPOTENT_WRITE nếu cần theo phiên bản/config |
| `User:orders-fulfillment` | Topic `orders.created` | READ |
| `User:orders-fulfillment` | Group `order-fulfillment` | READ |
| `User:orders-fulfillment` | Topic `orders.created.DLT` | WRITE nếu principal này gửi DLT |
| `User:orders-fulfillment` | Topic retry tương ứng | READ/WRITE theo vai trò retry topic |

Nếu Order API gửi record và nhận `TopicAuthorizationException`, hãy kiểm tra quyền WRITE của `User:orders-api` trên `orders.created`. Nếu consumer không tham gia group và nhận `GroupAuthorizationException`, hãy kiểm tra READ trên group `order-fulfillment`. Nếu DLT publish thất bại, hãy kiểm tra quyền WRITE trên `orders.created.DLT` của principal thực sự được KafkaTemplate/recoverer sử dụng.

Việc tách principal giúp xác định rõ service nào cần quyền nào. Khi một service bị xâm nhập hoặc credential bị lộ, phạm vi quyền của principal đó cũng được giới hạn theo đúng vai trò.

## 18. Checklist vận hành

- [ ] Phân biệt được authentication failure với authorization failure.
- [ ] Xác định principal mà broker thực sự nhìn thấy.
- [ ] Ghi lại resource type, resource name và operation bị từ chối.
- [ ] Producer có WRITE trên topic đích.
- [ ] Consumer có READ trên từng topic cần đọc.
- [ ] Consumer có READ trên group ID hiệu lực.
- [ ] Idempotent producer có quyền IDEMPOTENT_WRITE nếu phiên bản/config yêu cầu.
- [ ] Transactional producer có WRITE trên transactional ID và topic đầu ra.
- [ ] Retry/DLT producer có WRITE trên topic đích; consumer có READ trên topic cần đọc.
- [ ] AdminClient chỉ có quyền quản trị cần thiết.
- [ ] ACL không bị deny rule, host constraint hoặc resource pattern cản trở.
- [ ] Secret và principal mapping khớp với cấu hình deployment.
- [ ] Đã thử lại bằng credential thực tế của service.
- [ ] Consumer lag, commit, publish và DLT backlog ổn định sau khi khôi phục.

Authorization failure trong Kafka được xử lý đúng khi xác định chính xác principal, resource và operation bị từ chối, sau đó cấp quyền tối thiểu phù hợp. Trong Spring Kafka, cần kiểm tra riêng producer, consumer group, listener, transactional producer, AdminClient và DLT publisher vì mỗi thành phần có thể thực hiện những thao tác khác nhau và dùng principal khác nhau.


