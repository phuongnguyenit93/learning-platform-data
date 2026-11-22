# Phân quyền ACL cho consumer

Kafka ACL (Access Control List) giới hạn principal nào được phép thực hiện thao tác nào trên tài nguyên Kafka. Với một consumer Spring Kafka, quyền cần thiết thường gồm `READ` trên topic được subscribe và `READ` trên consumer group mà consumer tham gia. Cấp quyền đúng hai phạm vi này giúp consumer đọc dữ liệu và commit offset mà không cần quyền quản trị cluster.

ACL chỉ có ý nghĩa khi broker đã bật authorizer và client được xác thực thành một principal. Spring Kafka cấu hình kết nối và listener; việc kiểm tra quyền được Kafka broker thực hiện.

## 1. Phân biệt authentication và authorization

Hai bước này giải quyết hai câu hỏi khác nhau:

- **Authentication:** client là ai? Ví dụ SASL/SCRAM xác thực username và password, còn TLS client authentication có thể xác định principal từ chứng thư.
- **Authorization:** principal đó được làm gì? Kafka authorizer kiểm tra ACL trên topic, group hoặc tài nguyên khác trước khi cho phép request.

Ví dụ, Spring Boot consumer đăng nhập bằng SASL/SCRAM với username `orders-consumer`. Broker xác thực client và ánh xạ danh tính đó thành principal `User:orders-consumer`. ACL được tạo cho principal này. `group.id=orders-service` là tên consumer group, không phải username hoặc principal.

Nếu client dùng TLS certificate hoặc custom principal builder, tên principal mà broker nhìn thấy có thể khác username trong cấu hình ứng dụng. Hãy kiểm tra principal thực tế trong log broker trước khi tạo ACL.

## 2. Những thành phần trong một ACL

Một ACL xác định principal, permission, operation, resource và có thể cả host:

| Thành phần | Ý nghĩa | Ví dụ consumer |
| --- | --- | --- |
| Principal | Danh tính đã được broker xác thực | `User:orders-consumer` |
| Resource type | Loại tài nguyên được bảo vệ | `Topic`, `Group` |
| Resource name | Tên tài nguyên | `orders`, `orders-service` |
| Operation | Hành động được phép | `READ` |
| Permission | Cho phép hoặc từ chối | `ALLOW` |
| Host | Máy khách được phép kết nối | `*` hoặc địa chỉ được giới hạn |

Với consumer thông thường, cần cấp `READ` trên từng topic mà listener đọc và `READ` trên group ID thực tế. `READ` trên topic cũng bao hàm quyền `DESCRIBE` theo quan hệ quyền của Kafka ACL. Nếu một công cụ vận hành cần mô tả consumer group, có thể cấp `DESCRIBE` trên group cho principal vận hành riêng.

## 3. Cấp quyền tối thiểu cho consumer

Giả sử ứng dụng dùng principal `User:orders-consumer`, subscribe topic `orders` và cấu hình `group.id=orders-service`. Dùng một principal quản trị riêng để tạo ACL:

```bash
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --topic orders

kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service
```

Lệnh thứ nhất cho phép đọc topic; lệnh thứ hai cho phép consumer tham gia group và quản lý offset của group đó. Nếu consumer subscribe nhiều topic, cấp `READ` cho từng topic hoặc dùng resource pattern có phạm vi được kiểm soát.

Không cấp `ALL` trên cluster hoặc `CREATE` trên topic cho một consumer chỉ có nhiệm vụ đọc. Nếu ứng dụng cần tạo topic, hãy dùng principal provisioning/admin riêng hoặc quy trình triển khai tạo topic trước khi consumer chạy.

## 4. Resource pattern cho nhiều topic hoặc group

Kafka ACL hỗ trợ resource pattern `LITERAL` và `PREFIXED`. Dùng prefix khi các resource được đặt tên theo một quy ước ổn định, ví dụ các topic `orders.created`, `orders.updated` và các group `orders-service-blue`, `orders-service-green`.

```bash
# Cho phép đọc mọi topic bắt đầu bằng orders.
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --topic orders. \
  --resource-pattern-type prefixed

# Cho phép tham gia các group bắt đầu bằng orders-service-.
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service- \
  --resource-pattern-type prefixed
```

Prefix ACL mở quyền cho mọi resource có tiền tố tương ứng, kể cả resource được tạo trong tương lai. Chỉ dùng khi mọi topic/group trong prefix thuộc cùng ranh giới tin cậy. Nếu mỗi tenant có dữ liệu hoặc quyền truy cập khác nhau, ưu tiên ACL literal hoặc prefix hẹp theo tenant.

## 5. Cấu hình xác thực trong Spring Boot

ACL không được khai báo trong `@KafkaListener`; listener chỉ chọn topic và group. Client phải kết nối bằng credential tương ứng với principal đã được cấp ACL. Ví dụ dưới đây dùng SASL/SCRAM qua TLS:

```properties
spring.kafka.bootstrap-servers=kafka.example.com:9093
spring.kafka.consumer.group-id=orders-service
spring.kafka.consumer.properties[security.protocol]=SASL_SSL
spring.kafka.consumer.properties[sasl.mechanism]=SCRAM-SHA-512
spring.kafka.consumer.properties[sasl.jaas.config]=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
```

Đặt `KAFKA_USERNAME=orders-consumer` và cung cấp password qua secret manager hoặc biến môi trường của môi trường chạy. Không commit password, JAAS secret hoặc private key vào Git. Với CA riêng, cấu hình truststore/SSL theo hạ tầng của cluster.

`SASL_SSL` vừa mã hóa đường truyền vừa xác thực client bằng SASL. `SASL_PLAINTEXT` không mã hóa dữ liệu trên mạng; không dùng nó trên mạng không tin cậy. Cơ chế SASL phải khớp với broker, ví dụ `SCRAM-SHA-512`, `PLAIN` hoặc `OAUTHBEARER`.

Nếu dùng nhiều Kafka client trong cùng ứng dụng, hãy nhớ cấu hình producer, consumer và `KafkaAdmin` theo đúng principal và nhu cầu riêng. Các thuộc tính dưới `spring.kafka.consumer.properties` chỉ áp dụng cho consumer. Không mặc định rằng credential consumer có thể tạo topic hoặc gửi message.

## 6. Quyền cho các tác vụ liên quan

Consumer chỉ đọc topic và tham gia group thường không cần quyền quản trị cluster. Một số tác vụ khác cần ACL riêng:

| Tác vụ | Resource/operation thường cần |
| --- | --- |
| Consume topic | `READ` trên `Topic` và `READ` trên `Group` |
| Xem thông tin consumer group bằng công cụ vận hành | `DESCRIBE` trên `Group` cho principal vận hành |
| Publish record | `WRITE` trên `Topic` |
| Tạo topic | `CREATE` trên `Topic` hoặc quyền cluster phù hợp với cách provisioning |
| Xóa topic | `DELETE` trên `Topic` |
| Quản lý ACL | Quyền quản trị ACL theo authorizer và phiên bản Kafka |

Nếu ứng dụng dùng `KafkaAdmin` với `NewTopic` bean để tự tạo topic lúc khởi động, client admin cần quyền tạo topic. Tách việc provisioning khỏi principal runtime của consumer sẽ giúp giảm quyền và tránh ứng dụng đọc dữ liệu có thể tự thay đổi cấu trúc cluster.

## 7. Kiểm tra ACL đã cấp

Dùng principal quản trị để liệt kê ACL của consumer:

```bash
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --list \
  --principal User:orders-consumer
```

Kiểm tra có ACL `ALLOW READ` cho topic `orders` và group `orders-service`, đồng thời xác minh resource pattern và host đúng như dự kiến. Đừng chỉ kiểm tra ACL tồn tại; hãy chạy consumer bằng đúng credential runtime để xác nhận broker nhận diện đúng principal.

Có thể kiểm thử bằng một listener nhỏ đọc một record từ topic. Nếu listener subscribe được topic và join group, rồi đọc record thành công, quyền runtime cơ bản đã hoạt động. Dùng một topic/group thử nghiệm để kiểm tra trường hợp bị từ chối mà không ảnh hưởng luồng production.

## 8. Nhận biết lỗi authorization

Khi ACL thiếu hoặc principal không khớp, broker từ chối request. Một số lỗi thường gặp:

- `TopicAuthorizationException`: principal không có quyền cần thiết trên topic được truy cập.
- `GroupAuthorizationException`: principal không có quyền trên consumer group, thường liên quan đến join group hoặc commit offset.
- `ClusterAuthorizationException`: client gọi thao tác cấp cluster nhưng không có quyền tương ứng.
- `SaslAuthenticationException`: xác thực thất bại; đây là lỗi authentication, cần kiểm tra username, password, SASL mechanism và cấu hình TLS trước khi xem ACL.

Khi chẩn đoán, kiểm tra theo thứ tự principal broker nhận được, tên topic chính xác, `group.id` runtime, operation bị từ chối và ACL áp dụng cho resource. Tên group có thể bị ghi đè bởi cấu hình container hoặc `@KafkaListener(groupId=...)`, vì vậy đừng chỉ nhìn `spring.kafka.consumer.group-id`.

Không bắt rồi bỏ qua lỗi authorization như thể đó là record lỗi nghiệp vụ. Việc retry vô hạn không sửa được ACL thiếu; cần sửa quyền hoặc cấu hình principal, sau đó khởi động lại/tiếp tục consumer theo chính sách vận hành.

## 9. Thu hồi quyền khi không còn sử dụng

Khi ứng dụng hoặc tenant ngừng hoạt động, thu hồi đúng ACL đã cấp. Ví dụ:

```bash
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal User:orders-consumer \
  --operation Read \
  --topic orders

kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service
```

Thu hồi ACL không xóa topic, record hoặc committed offset. Nếu principal dùng chung cho nhiều ứng dụng, thu hồi quyền có thể làm gián đoạn tất cả client đó. Vì vậy, nên cấp principal riêng cho từng service hoặc workload, có quy trình xoay vòng credential và thu hồi khi ngừng triển khai.

## 10. Checklist bảo mật cho consumer

- Xác nhận broker bật authorizer và không có cấu hình mở quyền ngoài dự kiến.
- Xác định principal thực tế từ SASL hoặc TLS certificate.
- Cấp `READ` đúng topic và `READ` đúng group ID mà listener sử dụng.
- Dùng ACL literal hoặc prefix hẹp theo ranh giới dữ liệu.
- Dùng `SASL_SSL` hoặc TLS phù hợp và lưu credential trong secret manager.
- Tách principal runtime consumer khỏi principal quản trị/provisioning.
- Kiểm thử cả trường hợp được phép và bị từ chối bằng credential thật.
- Theo dõi authorization failure và rà soát ACL định kỳ.

Phân quyền ACL cho consumer là việc giới hạn quyền đọc theo topic và consumer group gắn với principal đã xác thực. Kết hợp ACL least privilege với SASL/TLS, credential riêng cho từng service và kiểm thử bằng đúng cấu hình runtime giúp bảo vệ dữ liệu Kafka mà vẫn giữ luồng Spring Kafka hoạt động ổn định.
