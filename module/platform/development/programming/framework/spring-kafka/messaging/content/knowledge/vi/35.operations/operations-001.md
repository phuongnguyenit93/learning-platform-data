# Kiểm tra broker và bootstrap servers

Khi vận hành ứng dụng Spring Kafka, lỗi kết nối thường xuất hiện trước cả khi listener nhận được record. Ứng dụng có thể không phân giải được hostname, không mở được TCP connection, không xác thực được SASL/TLS hoặc kết nối được bootstrap broker nhưng không truy cập được các broker mà cluster quảng bá trong metadata.

Kiểm tra broker và `bootstrap.servers` cần đi theo toàn bộ luồng kết nối: từ địa chỉ bootstrap ban đầu, qua metadata Kafka trả về, đến endpoint của broker leader/controller mà client cần truy cập. Một địa chỉ bootstrap mở được cổng TCP chưa đủ để kết luận ứng dụng có thể đọc hoặc ghi dữ liệu.

## 1. Bootstrap servers dùng để làm gì?

`bootstrap.servers` là danh sách địa chỉ ban đầu để Kafka client tìm một broker và lấy metadata của cluster. Client không cần kết nối trực tiếp đến mọi broker ngay lúc khởi tạo; nó có thể bắt đầu với một hoặc vài địa chỉ trong danh sách, sau đó dùng metadata để biết broker nào đang quản lý partition và leader.

Ví dụ cấu hình nhiều endpoint:

```properties
spring.kafka.bootstrap-servers=broker-1.example.net:9092,broker-2.example.net:9092,broker-3.example.net:9092
```

Nên khai báo nhiều broker có thể truy cập để client còn endpoint khác khi một địa chỉ bootstrap tạm thời không sẵn sàng. Các địa chỉ phải thuộc cùng cluster và đúng listener/protocol mà ứng dụng sử dụng.

Bootstrap servers không phải danh sách duy nhất mà client sẽ kết nối trong suốt vòng đời. Sau khi nhận metadata, client kết nối đến endpoint broker được cluster quảng bá. Vì vậy, phải kiểm tra cả bootstrap address lẫn advertised broker address.

## 2. Hiểu advertised.listeners và lỗi kết nối sau bootstrap

Broker công bố endpoint cho client qua cấu hình `advertised.listeners`. Đây là hostname/IP và port mà broker gửi trong metadata. Cấu hình `listeners` quyết định broker bind và lắng nghe ở đâu; `advertised.listeners` quyết định client nhìn thấy địa chỉ nào để kết nối.

Một lỗi thường gặp khi chạy Kafka trong Docker là ứng dụng kết nối được `localhost:9092` hoặc một port được publish trên host, nhưng metadata lại trả về hostname chỉ phân giải được bên trong Docker network. Ứng dụng chạy ngoài container sẽ không kết nối được endpoint đó.

```text
Spring Boot app
      |
      | bootstrap: localhost:9092  (kết nối được)
      v
Kafka broker
      |
      | metadata trả về: kafka-1:29092
      v
App host không phân giải được kafka-1
```

Hãy cấu hình listener riêng cho các vùng mạng cần truy cập, ví dụ internal listener cho container và external listener cho ứng dụng chạy trên host. Mỗi client phải dùng đúng endpoint được quảng bá cho network của nó. Không đặt `advertised.listeners` thành `localhost` nếu client chạy trên máy hoặc container khác.

## 3. Kiểm tra DNS và TCP từ đúng môi trường chạy ứng dụng

Thực hiện kiểm tra từ chính máy, container hoặc Kubernetes pod chạy Spring Boot. Kiểm tra trên laptop của developer không chứng minh pod production có cùng DNS route, firewall hoặc network policy.

Trên Windows PowerShell:

```powershell
Resolve-DnsName broker-1.example.net
Test-NetConnection broker-1.example.net -Port 9092
```

Trên Linux hoặc container:

```bash
getent hosts broker-1.example.net
nc -vz broker-1.example.net 9092
```

`Resolve-DnsName` hoặc `getent hosts` kiểm tra phân giải tên. `Test-NetConnection` hoặc `nc` kiểm tra khả năng mở TCP đến port. TCP thành công chỉ chứng minh đường mạng và port có thể kết nối; nó chưa xác minh Kafka protocol, TLS handshake, SASL authentication, ACL hoặc quyền truy cập topic.

Lặp lại kiểm tra với các endpoint broker mà client nhận được trong metadata. Nếu bootstrap broker truy cập được nhưng một advertised endpoint không truy cập được, producer/consumer vẫn có thể timeout khi làm việc với partition do broker đó quản lý.

## 4. Kiểm tra TLS và SASL

Nếu cluster yêu cầu TLS hoặc SASL, protocol và credential của client phải khớp listener broker. Với Spring Boot, cấu hình ví dụ cho SASL/SCRAM qua TLS:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": ${KAFKA_SASL_JAAS_CONFIG}
```

Biến `KAFKA_BOOTSTRAP_SERVERS` chứa danh sách host:port phân tách bằng dấu phẩy. `KAFKA_SASL_JAAS_CONFIG` chứa cấu hình JAAS được cấp từ secret manager hoặc môi trường triển khai. Không ghi username/password thật vào source code, file cấu hình được commit hoặc log.

Nếu dùng CA riêng, cấu hình truststore hoặc trust material phù hợp để JVM xác minh chứng thư broker. Kiểm tra hostname trong certificate có khớp hostname client truy cập không. Không tắt hostname verification để né lỗi certificate trong production.

Phân biệt lỗi thường gặp:

- `SSLHandshakeException`: kiểm tra trust chain, certificate expiry, hostname và TLS protocol/cipher.
- `SaslAuthenticationException`: kiểm tra username, password, mechanism và JAAS config.
- `TopicAuthorizationException` hoặc `GroupAuthorizationException`: client đã đi xa hơn bước kết nối nhưng principal thiếu ACL trên topic hoặc consumer group.

## 5. Kiểm tra broker bằng Kafka CLI

Dùng các script đi kèm Kafka distribution để xác minh từ cùng network và với cùng security configuration mà ứng dụng dùng. Khi cluster yêu cầu SASL/TLS, tạo file client properties riêng, ví dụ `client.properties`, rồi truyền bằng `--command-config`.

Kiểm tra broker hỗ trợ Kafka API và có phản hồi:

```bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties
```

Liệt kê topic:

```bash
kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties \
  --list
```

Xem partition, leader, replica và ISR của một topic:

```bash
kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties \
  --describe \
  --topic orders
```

Kiểm tra consumer group và committed offset:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties \
  --describe \
  --group order-service
```

Trên Windows, dùng các file `.bat` tương ứng trong thư mục `bin\windows` của Kafka distribution. Tên script và một số option có thể khác theo phiên bản Kafka; hãy dùng script từ phiên bản tương thích với cluster.

Các lệnh `--list` và `--describe` cần quyền ACL tương ứng. Nếu lệnh bị authorization denied, điều đó không nhất thiết có nghĩa broker không hoạt động; hãy phân biệt lỗi kết nối/xác thực với lỗi quyền trên resource.

## 6. Kiểm tra cluster bằng AdminClient

Ứng dụng Java có thể dùng Kafka `AdminClient` để kiểm tra cluster ID, broker node và controller. Đây là kiểm tra ở tầng Kafka protocol, hữu ích hơn một phép thử TCP đơn thuần:

```java
Map<String, Object> config = new HashMap<>();
config.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "broker-1.example.net:9092,broker-2.example.net:9092");

// Bổ sung security.protocol, sasl.mechanism và sasl.jaas.config
// nếu cluster yêu cầu SASL/TLS.
try (AdminClient admin = AdminClient.create(config)) {
    DescribeClusterResult result = admin.describeCluster();

    String clusterId = result.clusterId().get(5, TimeUnit.SECONDS);
    Collection<Node> nodes = result.nodes().get(5, TimeUnit.SECONDS);
    Node controller = result.controller().get(5, TimeUnit.SECONDS);

    log.info("Kafka cluster={}, brokers={}, controller={}",
        clusterId, nodes.size(), controller);
}
```

Đặt timeout hữu hạn cho thao tác quản trị để health check không treo vô thời hạn. Đóng `AdminClient` sau khi dùng. Nếu dùng AdminClient trong một health indicator chạy định kỳ, có thể tái sử dụng một client được quản lý theo lifecycle thay vì tạo client mới ở mỗi lần probe.

Có thể mở rộng kiểm tra bằng `describeTopics(...)` để xác minh topic tồn tại và xem partition metadata. Tuy nhiên, quyền `DESCRIBE` và quyền đọc dữ liệu là hai vấn đề khác nhau; thành công khi mô tả topic chưa chứng minh consumer có ACL `READ` hoặc producer có ACL `WRITE`.

## 7. Cấu hình bootstrap servers trong Spring Boot

Trong ứng dụng Spring Boot, đặt bootstrap list ở một nơi nhất quán và đưa giá trị theo môi trường triển khai:

```properties
spring.kafka.bootstrap-servers=${KAFKA_BOOTSTRAP_SERVERS}
spring.kafka.consumer.group-id=order-service
spring.kafka.consumer.properties[request.timeout.ms]=30000
spring.kafka.admin.properties[request.timeout.ms]=10000
```

Không hard-code địa chỉ dev vào artifact production. Dùng DNS/service endpoint phù hợp với môi trường và bảo đảm mọi broker endpoint trong metadata đều có thể truy cập từ workload.

Nếu ứng dụng có cấu hình riêng cho `ProducerFactory`, `ConsumerFactory`, `KafkaAdmin` hoặc `AdminClient`, kiểm tra từng client có nhận đúng bootstrap list và security properties. Một số cấu hình custom có thể ghi đè auto-configuration của Spring Boot.

## 8. Readiness check và kiểm tra lúc khởi động

Readiness nên phản ánh khả năng ứng dụng thực sự phục vụ workload. Với service phụ thuộc Kafka để nhận hoặc gửi event, có thể kiểm tra `describeCluster()` hoặc một thao tác metadata có timeout trước khi đánh dấu dependency sẵn sàng.

Không nên dùng một phép probe quá nặng ở mỗi lần health request. Health indicator nên có timeout ngắn, tránh tạo nhiều AdminClient liên tục và tránh làm Kafka outage khiến endpoint health bị treo. Có thể cache trạng thái kiểm tra trong một khoảng ngắn và ghi rõ trạng thái `UP`, `DOWN` cùng nguyên nhân đã rút gọn.

Phân biệt readiness và liveness:

- **Readiness:** ứng dụng có thể nhận traffic hoặc xử lý event hay chưa; phụ thuộc Kafka có thể khiến instance chưa sẵn sàng.
- **Liveness:** tiến trình có còn sống và có khả năng tự phục hồi hay không. Không nên restart liên tục chỉ vì Kafka tạm thời mất kết nối nếu ứng dụng được thiết kế để retry và phục hồi.

Nếu dùng Spring Boot Actuator, kiểm tra health endpoint và các contributor thực tế được cấu hình trong ứng dụng. Một health indicator Kafka thành công không thay thế smoke test gửi/nhận qua đúng topic, group và principal runtime.

## 9. Smoke test producer và consumer

Sau khi broker và metadata truy cập được, thực hiện một smoke test bằng topic thử nghiệm:

1. Dùng đúng credential runtime để publish một record có correlation ID duy nhất.
2. Chờ future của `KafkaTemplate.send()` hoàn tất trong timeout.
3. Dùng consumer group thử nghiệm đọc record và xác minh key, payload, partition.
4. Xác nhận consumer group có thể commit offset nếu ứng dụng cần commit.
5. Ghi lại cluster, topic, partition, timestamp và kết quả; tránh log payload nhạy cảm.

Smoke test này xác minh được cả broker protocol, serialization, ACL, producer và consumer. Dùng topic/group riêng để không làm thay đổi dữ liệu hoặc offset của luồng production.

## 10. Các lỗi thường gặp và hướng điều tra

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| `UnknownHostException` | DNS, hostname trong bootstrap list và advertised.listeners. |
| `Connection refused` | Broker listener, port, service endpoint và firewall. |
| `TimeoutException` sau khi lấy metadata | Advertised broker endpoints, route từ pod/host đến mọi broker và broker load. |
| `DisconnectException` liên tục | TCP/TLS, proxy/load balancer, idle timeout và broker logs. |
| `SSLHandshakeException` | CA, truststore, hostname certificate và thời hạn chứng thư. |
| `SaslAuthenticationException` | Credential, JAAS config, SASL mechanism và listener broker. |
| `TopicAuthorizationException` | ACL của principal trên topic. |
| `GroupAuthorizationException` | ACL `READ` trên consumer group. |
| Topic không tồn tại hoặc partition thiếu leader | Topic provisioning, metadata, controller và trạng thái broker. |

Khi điều tra, ghi nhận bootstrap address đã dùng, broker endpoint nhận từ metadata, exception gốc, thời điểm và client ID. Không ghi password, JAAS string, token hoặc private key vào log.

## 11. Checklist vận hành

- Có ít nhất hai bootstrap endpoint phù hợp với topology và chính sách HA của cluster.
- Kiểm tra DNS và TCP từ đúng host/container/pod chạy ứng dụng.
- Xác minh `advertised.listeners` trả về hostname và port truy cập được từ workload.
- Kiểm tra TLS certificate, truststore, SASL mechanism và credential.
- Dùng Kafka CLI với cùng security properties để xác minh broker, topic và group.
- Kiểm tra cluster ID, broker nodes và controller bằng AdminClient khi cần chẩn đoán sâu.
- Xác minh topic, partition leader, replica/ISR và consumer group offset.
- Đưa bootstrap servers và secret vào cấu hình môi trường/secret manager.
- Có readiness timeout và smoke test phù hợp; không nhầm TCP check với Kafka health.
- Ghi log chẩn đoán có kiểm soát, không để lộ credential.

Kiểm tra broker và bootstrap servers cần xác minh cả endpoint ban đầu lẫn các broker mà cluster công bố qua metadata. Kết hợp DNS/TCP, TLS/SASL, Kafka CLI, AdminClient và smoke test bằng đúng principal runtime giúp khoanh vùng sự cố từ network đến ACL, đồng thời tránh kết luận sai rằng Kafka đã sẵn sàng chỉ vì một port đang mở.

## Tài liệu tham khảo

- [Kafka Producer Configs - bootstrap.servers](https://kafka.apache.org/documentation/#producerconfigs_bootstrap.servers)
- [Kafka Broker Configs - listeners and advertised.listeners](https://kafka.apache.org/documentation/#brokerconfigs_advertised.listeners)
- [Kafka AdminClient API](https://kafka.apache.org/documentation/#adminapi)
- [Spring Boot Kafka support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
