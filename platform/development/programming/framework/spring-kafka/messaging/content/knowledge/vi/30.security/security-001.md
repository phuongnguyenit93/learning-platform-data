# TLS giữa ứng dụng và Kafka

Ứng dụng Spring Kafka kết nối tới broker bằng Kafka Java client. Khi cần bảo vệ dữ liệu trên đường truyền, hãy cấu hình TLS (Transport Layer Security) cho các kết nối producer, consumer và các client Kafka liên quan. TLS mã hóa dữ liệu trên mạng, xác minh danh tính broker bằng certificate và, nếu bật mutual TLS (mTLS), xác minh thêm certificate của ứng dụng.

Spring Kafka không tự triển khai một giao thức TLS riêng. Nó chuyển cấu hình tới Kafka client thông qua `ProducerFactory`, `ConsumerFactory`, `KafkaAdmin` và các thành phần tương ứng. Vì vậy, cấu hình SSL của Kafka client là nền tảng cho kết nối an toàn trong ứng dụng Spring.

## 1. TLS bảo vệ điều gì?

Khi ứng dụng kết nối tới Kafka qua TLS, hai bên thực hiện handshake để thương lượng phiên mã hóa và xác minh certificate. Sau handshake, dữ liệu Kafka được truyền trong kênh TLS.

TLS mang lại ba thuộc tính chính:

- **Confidentiality:** người quan sát trên mạng không đọc được payload, key, header và protocol traffic đã được mã hóa.
- **Integrity:** thay đổi dữ liệu trên đường truyền sẽ bị phát hiện.
- **Authentication:** client xác minh broker dựa trên certificate chain; với mTLS, broker cũng xác minh certificate của client.

```text
Spring Kafka application                         Kafka broker
        |                                              |
        |---- ClientHello / TLS negotiation ---------->|
        |<--- Server certificate + handshake ----------|
        |                                              |
        | Verify CA chain, validity, hostname           |
        |                                              |
        |---- (mTLS) Client certificate --------------->|
        |<--- (mTLS) Server verifies client ------------|
        |                                              |
        |========== Encrypted TLS session ==============|
        |---- Kafka protocol: produce / fetch / commit ->|
        |<--- Kafka responses --------------------------|
```

TLS chỉ bảo vệ đường truyền giữa hai đầu TLS. Nó không mã hóa dữ liệu đang lưu trên Kafka broker, không thay thế ACL/authorization và không tự xác định user nào được phép đọc hoặc ghi topic.

## 2. Phân biệt TLS, mTLS và SASL

Ba khái niệm thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

| Cơ chế | Xác minh | Mục đích |
| --- | --- | --- |
| TLS một chiều (server-auth TLS) | Client xác minh certificate của broker | Mã hóa kết nối và xác thực broker |
| Mutual TLS (mTLS) | Client xác minh broker, broker xác minh certificate client | Xác thực cả hai đầu bằng certificate |
| SASL | Broker xác thực principal theo cơ chế SASL đã cấu hình | Xác thực ứng dụng bằng SCRAM, PLAIN, OAuth hoặc cơ chế hỗ trợ khác |

Trong Kafka, `security.protocol=SSL` dùng TLS. `security.protocol=SASL_SSL` kết hợp TLS với SASL authentication. Nếu chỉ dùng TLS một chiều, broker được xác thực với client nhưng client chưa được xác thực bằng certificate ở tầng TLS; broker vẫn có thể yêu cầu cơ chế xác thực khác.

Không nhầm TLS với authorization. Sau khi xác thực, Kafka ACL hoặc cơ chế authorizer của cluster mới quyết định principal được phép `READ`, `WRITE`, `CREATE`, `DESCRIBE` topic hay tham gia consumer group.

## 3. Certificate, CA và trust chain

Certificate X.509 chứa public key và thông tin danh tính của chủ thể, được CA (Certificate Authority) ký. Khi broker trình certificate, client kiểm tra chữ ký và xây dựng đường dẫn tin cậy tới một CA mà client tin cậy.

Một certificate server thường có:

- Subject/SAN xác định hostname hoặc DNS name của broker.
- Public key tương ứng với private key trên broker.
- Thời hạn `Not Before` và `Not After`.
- Extended Key Usage phù hợp với TLS server authentication.
- Chuỗi intermediate certificate nếu CA dùng nhiều cấp.

Client truststore chứa CA certificate hoặc certificate tin cậy dùng để xác minh broker. Thông thường client chỉ cần CA certificate, không cần private key của broker.

Nếu cluster dùng nhiều broker, client có thể kết nối tới broker khác sau bootstrap, ví dụ khi nhận metadata hoặc fetch partition leader. Certificate của từng broker cần có SAN phù hợp với hostname được quảng bá trong `advertised.listeners` và hostname mà client thực sự kết nối.

## 4. Truststore và keystore khác nhau thế nào?

| Thành phần | Chứa gì? | Dùng ở đâu? |
| --- | --- | --- |
| Truststore | CA certificate hoặc certificate tin cậy | Client xác minh certificate broker |
| Keystore | Certificate của chính client và private key tương ứng | Client cung cấp danh tính khi broker yêu cầu mTLS |

Với TLS một chiều, ứng dụng thường chỉ cần truststore. Với mTLS, ứng dụng cần cả truststore và keystore:

```text
Client application
  truststore: CA ký certificate của broker
  keystore:   client certificate + client private key

Kafka broker
  keystore:   broker certificate + broker private key
  truststore: CA ký certificate client
```

Truststore không cần chứa private key. Private key trong keystore phải được bảo vệ như secret; không commit vào Git, không nhúng trong JAR hoặc image container và không đưa vào log.

## 5. Bật TLS trong Spring Boot

Kafka client nhận các SSL properties thông qua `spring.kafka.properties`. Ví dụ TLS một chiều dùng truststore PKCS12:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9093,broker-2.example.net:9093
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

Trong ví dụ, `KAFKA_TRUSTSTORE_LOCATION` trỏ tới truststore được mount vào runtime và password được lấy từ secret store hoặc environment injection. Không ghi password thật vào file cấu hình được commit.

Các property trong `spring.kafka.properties` là cấu hình Kafka client dùng chung. Vì vậy producer, consumer và các client được cấu hình từ nhóm property này có thể sử dụng cùng TLS settings. Nếu producer hoặc consumer cần cấu hình riêng, có thể đặt override trong `spring.kafka.producer.properties` hoặc `spring.kafka.consumer.properties` theo nhu cầu và phiên bản Spring Boot.

`security.protocol=SSL` yêu cầu broker listener tương ứng phải bật SSL. Đổi port từ 9092 sang 9093 trong ví dụ chỉ là quy ước minh họa; hãy dùng đúng địa chỉ và port mà cluster cung cấp.

## 6. Cấu hình mTLS cho client

Nếu broker yêu cầu client certificate, bổ sung keystore của ứng dụng:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9093
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.keystore.location]": ${KAFKA_KEYSTORE_LOCATION}
      "[ssl.keystore.password]": ${KAFKA_KEYSTORE_PASSWORD}
      "[ssl.key.password]": ${KAFKA_PRIVATE_KEY_PASSWORD}
      "[ssl.keystore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

Trong mTLS:

- Truststore của client tin cậy CA đã ký certificate broker.
- Keystore của client chứa certificate và private key mà broker có thể xác minh.
- Broker cần cấu hình truststore tin cậy CA đã ký certificate client.
- Broker phải bật yêu cầu client authentication, ví dụ `ssl.client.auth=required`, nếu muốn bắt buộc mọi client trình certificate.

`ssl.keystore.password` bảo vệ keystore container; `ssl.key.password` có thể bảo vệ private key bên trong. Với một số keystore, hai password có thể giống nhau; không nên giả định điều đó nếu hệ thống PKI cấp riêng.

## 7. Cấu hình SSL bằng PEM

Kafka client hỗ trợ PEM ở các phiên bản Kafka tương ứng. Khi dùng PEM, có thể cung cấp certificate chain, private key và CA certificates trực tiếp thay vì một file JKS/PKCS12:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.type]": PEM
      "[ssl.truststore.certificates]": ${KAFKA_CA_CERTIFICATE}
      "[ssl.keystore.type]": PEM
      "[ssl.keystore.certificate.chain]": ${KAFKA_CLIENT_CERTIFICATE_CHAIN}
      "[ssl.keystore.key]": ${KAFKA_CLIENT_PRIVATE_KEY}
      "[ssl.endpoint.identification.algorithm]": https
```

Đây là ví dụ mTLS; nếu chỉ dùng TLS một chiều, client chỉ cần CA certificate trong truststore và không cần keystore client. PEM private key phải ở định dạng mà Kafka client hỗ trợ; nếu key được mã hóa, cấu hình password tương ứng theo tài liệu Kafka client của phiên bản đang dùng.

Không đặt nội dung private key trực tiếp trong YAML được lưu vào repository. Các biến ví dụ cần được cấp qua secret manager hoặc mount file an toàn; nếu dùng file path, kiểm tra quyền đọc của process và quyền truy cập của người dùng trên host.

## 8. Cấu hình ProducerFactory và ConsumerFactory bằng Java

Khi tự tạo Kafka factories, đặt SSL properties vào map cấu hình Kafka client. Ví dụ dùng truststore cho producer:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.config.SslConfigs;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "broker-1.example.net:9093");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put("security.protocol", "SSL");
        properties.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
                System.getenv("KAFKA_TRUSTSTORE_LOCATION"));
        properties.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
                System.getenv("KAFKA_TRUSTSTORE_PASSWORD"));
        properties.put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12");
        properties.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
                "https");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Consumer factory cần các SSL properties tương tự:

```java
properties.put("security.protocol", "SSL");
properties.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG, truststoreLocation);
properties.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG, truststorePassword);
properties.put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12");
properties.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG, "https");
```

Đặt các property vào cả producer và consumer factory nếu cả hai kết nối cần TLS. Nếu dùng Spring Boot auto-configuration, không cần tự tạo lại factories chỉ để bật SSL; cấu hình YAML ở phần trước thường đủ.

Ví dụ Java dùng `System.getenv()` để minh họa nguồn cấu hình runtime. Trong ứng dụng thực tế, nên validate biến môi trường khi khởi động và báo lỗi rõ ràng nếu thiếu path/password. Tránh đưa password vào log hoặc exception message.

## 9. Hostname verification rất quan trọng

TLS không chỉ kiểm tra certificate có được CA tin cậy ký hay không. Client còn phải xác minh certificate thuộc về đúng broker mà nó đang kết nối. Kafka Java client mặc định dùng `ssl.endpoint.identification.algorithm=https` để thực hiện hostname verification.

Ví dụ client kết nối `broker-1.example.net:9093`, certificate server cần có DNS SAN `broker-1.example.net`. Nếu broker quảng bá địa chỉ `kafka-1.internal` nhưng certificate chỉ có SAN `broker-1.example.net`, handshake có thể thất bại khi client kết nối tới hostname được quảng bá.

Không tắt hostname verification bằng cách đặt `ssl.endpoint.identification.algorithm` thành chuỗi rỗng để “sửa nhanh” lỗi certificate. Cách đó làm client không còn xác minh broker có đúng hostname mong đợi hay không, tạo điều kiện cho kết nối tới server giả mạo nếu CA hoặc mạng bị xâm phạm.

Nếu gặp lỗi hostname mismatch, hãy sửa SAN của certificate hoặc `advertised.listeners`/DNS để hostname kết nối khớp certificate.

## 10. Cấu hình phía Kafka broker

Ứng dụng chỉ kết nối TLS thành công khi broker cũng có listener SSL và certificate hợp lệ. Ví dụ cấu hình minh họa cho broker:

```properties
listeners=SSL://0.0.0.0:9093
advertised.listeners=SSL://broker-1.example.net:9093
listener.security.protocol.map=SSL:SSL

ssl.keystore.location=/etc/kafka/secrets/broker.keystore.p12
ssl.keystore.password=${BROKER_KEYSTORE_PASSWORD}
ssl.key.password=${BROKER_PRIVATE_KEY_PASSWORD}
ssl.keystore.type=PKCS12

ssl.truststore.location=/etc/kafka/secrets/broker.truststore.p12
ssl.truststore.password=${BROKER_TRUSTSTORE_PASSWORD}
ssl.truststore.type=PKCS12
```

Đây là cấu hình minh họa cho listener SSL; cú pháp nạp secret phụ thuộc cách triển khai Kafka. Với TLS một chiều, broker không nhất thiết phải yêu cầu client certificate. Với mTLS bắt buộc:

```properties
ssl.client.auth=required
```

Broker truststore phải tin cậy CA đã ký certificate client. Nếu cluster có nhiều broker, mỗi broker cần certificate SAN phù hợp hostname được quảng bá. Trong cluster KRaft hoặc ZooKeeper cũ, các listener nội bộ và controller cần được cấu hình theo topology riêng; không sao chép nguyên cấu hình client-facing listener cho mọi listener.

## 11. TLS cho producer, consumer và Kafka Admin

Một ứng dụng Spring Kafka có thể tạo nhiều Kafka client:

- `KafkaProducer` do `ProducerFactory` quản lý.
- `KafkaConsumer` do `ConsumerFactory` quản lý.
- `AdminClient` được dùng bởi `KafkaAdmin` để kiểm tra hoặc tạo topic.

Nếu chỉ cấu hình SSL trên producer nhưng consumer vẫn kết nối tới listener plaintext, một nửa ứng dụng vẫn không được bảo vệ. Hãy xác định tất cả client và bootstrap endpoint mà ứng dụng sử dụng.

Với cấu hình chung qua `spring.kafka.properties`, Spring Boot có thể truyền SSL settings tới các client được cấu hình từ property map chung. Khi tạo factory/admin client tùy chỉnh hoặc dùng cluster/endpoint khác nhau, cần gắn SSL properties đúng vào từng client tương ứng.

## 12. TLS và SASL_SSL

Nếu cluster yêu cầu username/password hoặc token authentication, dùng `SASL_SSL` để vừa mã hóa kết nối vừa xác thực bằng SASL. Ví dụ với SCRAM:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

Ví dụ chỉ minh họa việc ghép TLS với SASL SCRAM. Password phải được inject từ secret store; không commit vào YAML. Nếu dùng OAuth hoặc cơ chế SASL khác, cấu hình callback handler, login module và token provider theo cơ chế đó.

TLS chịu trách nhiệm bảo vệ kênh truyền và xác minh certificate. SASL xác thực principal ứng dụng. ACL của Kafka quyết định principal được phép thao tác trên topic và group.

## 13. Quản lý certificate và rotation

Certificate có thời hạn. Nếu không theo dõi ngày hết hạn, producer/consumer có thể mất kết nối khi certificate hết hạn hoặc CA bị thay thế.

Quy trình rotation an toàn thường gồm:

1. Cấp CA/certificate mới và xác minh SAN, thời hạn, key usage.
2. Cập nhật truststore client để tin cậy CA mới trước khi broker chuyển certificate, nếu cần thay CA.
3. Triển khai certificate mới lên broker theo chiến lược rolling phù hợp.
4. Cập nhật keystore client nếu mTLS và certificate client được rotate.
5. Khởi tạo lại hoặc refresh Kafka clients theo cơ chế hỗ trợ của ứng dụng.
6. Xác minh handshake, hostname, producer send và consumer fetch trên từng broker.
7. Gỡ CA/certificate cũ sau khi toàn bộ kết nối đã chuyển đổi.

Spring Kafka `DefaultKafkaProducerFactory` và `DefaultKafkaConsumerFactory` quản lý lifecycle client. Việc thay file truststore/keystore trên đĩa không đồng nghĩa mọi Kafka client đang chạy tự động nạp lại nội dung mới. Cần có chiến lược refresh/restart factory hoặc ứng dụng phù hợp với phiên bản và cách triển khai.

Không rotate CA bằng cách gỡ CA cũ trước khi toàn bộ broker/client chuyển xong. Dùng giai đoạn overlap để tránh gián đoạn kết nối.

## 14. Bảo vệ secret và file certificate

Các file truststore/keystore và password cần được quản lý như cấu hình bảo mật:

- Lưu password trong secret manager hoặc nền tảng quản lý secret của môi trường.
- Mount certificate/key thành file read-only với quyền truy cập tối thiểu.
- Không commit keystore, private key hoặc password vào Git.
- Không đưa secret vào command line, log, exception hoặc diagnostic dump.
- Tách certificate theo môi trường dev/test/staging/production.
- Cấp certificate client riêng theo service hoặc workload để có thể thu hồi độc lập.
- Có quy trình thu hồi khi private key bị lộ.

Truststore chứa public CA certificate, nhưng vẫn nên quản lý thay đổi và nguồn gốc tin cậy. Thêm CA không đáng tin cậy vào truststore có thể khiến client chấp nhận broker giả mạo.

## 15. Kiểm thử TLS connection

Kiểm thử cần xác minh cả handshake và hoạt động Kafka sau handshake.

### Kiểm tra TLS handshake

- Client kết nối đúng hostname trong certificate SAN.
- Certificate còn hạn và chuỗi CA đầy đủ.
- Truststore chứa CA phù hợp.
- Với mTLS, broker chấp nhận certificate client và client có private key tương ứng.
- TLS protocol/cipher được hai bên hỗ trợ.

### Kiểm thử tích hợp Spring Kafka

1. Khởi chạy broker test có listener SSL.
2. Cấu hình Spring Boot producer/consumer dùng truststore test.
3. Gửi một record bằng `KafkaTemplate`.
4. Nhận record bằng `@KafkaListener`.
5. Xác minh metadata và payload đúng.
6. Nếu dùng mTLS, lặp lại với certificate client hợp lệ và kiểm tra client thiếu/không tin cậy certificate bị từ chối.
7. Kiểm tra producer, consumer và Kafka Admin đều dùng endpoint TLS theo thiết kế.

Không nên chỉ dùng Embedded Kafka plaintext rồi kết luận TLS hoạt động. Hãy dùng broker kiểm thử được cấu hình SSL hoặc mTLS tương tự môi trường thật. Có thể kiểm tra handshake độc lập bằng công cụ TLS phù hợp, nhưng integration test vẫn cần xác minh Kafka protocol sau handshake.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `SSLHandshakeException: PKIX path building failed` | Truststore thiếu CA/intermediate hoặc chain không hợp lệ | Cập nhật đúng CA chain vào truststore |
| `No subject alternative DNS name matching` | Hostname kết nối không có trong SAN certificate | Sửa SAN hoặc hostname/advertised listener |
| `Keystore was tampered with, or password was incorrect` | Sai password hoặc sai loại file | Kiểm tra password, file path và `ssl.keystore.type` |
| `UnrecoverableKeyException` | Sai password private key hoặc key entry không hợp lệ | Kiểm tra `ssl.key.password` và private key |
| Broker yêu cầu client certificate nhưng client không gửi | Chưa cấu hình keystore hoặc broker truststore không tin cậy CA client | Cấu hình mTLS hai phía và kiểm tra certificate chain |
| Producer dùng TLS nhưng consumer lỗi plaintext | SSL properties chỉ được đặt trên producer factory | Cấu hình consumer/admin client tương ứng |
| Một số broker kết nối được, broker khác lỗi | SAN/chain/advertised listener không đồng nhất | Kiểm tra certificate và DNS của từng broker |
| Kết nối thất bại sau rotation | Client cũ chưa nạp truststore mới hoặc CA cũ bị gỡ quá sớm | Dùng overlap CA và refresh/restart client có kiểm soát |
| Handshake thành công nhưng thao tác topic bị từ chối | TLS đã xác minh kênh nhưng principal thiếu quyền Kafka ACL | Cấp quyền topic/group/transactional ID phù hợp |

## 17. Checklist triển khai

- [ ] Broker cung cấp SSL listener và endpoint/port chính xác.
- [ ] Truststore chứa CA tin cậy và đầy đủ chain cần thiết.
- [ ] Certificate broker có SAN khớp hostname được quảng bá.
- [ ] Hostname verification vẫn được bật.
- [ ] Chọn TLS một chiều hay mTLS đúng yêu cầu.
- [ ] Nếu mTLS, broker truststore tin cậy CA client và client có keystore hợp lệ.
- [ ] Producer, consumer và Kafka Admin đều dùng TLS theo thiết kế.
- [ ] Secret được inject từ môi trường an toàn, không commit vào repository.
- [ ] Certificate expiry và rotation có quy trình theo dõi.
- [ ] ACL/authorization được cấu hình riêng ngoài TLS.
- [ ] Integration test dùng broker SSL/mTLS thực tế.
- [ ] Log không chứa password hoặc private key.

## 18. Kết luận

TLS giữa ứng dụng và Kafka mã hóa dữ liệu trên đường truyền và giúp client xác minh broker bằng certificate. Với TLS một chiều, client cần truststore để tin cậy CA ký certificate broker. Với mTLS, client bổ sung keystore chứa certificate và private key; broker cũng cần truststore tin cậy CA của client.

Trong Spring Kafka, cấu hình SSL được truyền tới Kafka client qua `spring.kafka.properties` hoặc map của `ProducerFactory`/`ConsumerFactory`. Hãy giữ hostname verification, đồng bộ certificate SAN với `advertised.listeners`, quản lý secret và rotation có kiểm soát. Nếu cần xác thực principal bằng username/password hoặc token, kết hợp `SASL_SSL`; sau đó dùng Kafka ACL để giới hạn quyền. TLS là lớp bảo vệ đường truyền, không thay thế authorization và không tự mã hóa dữ liệu lưu trên broker.

## Tài liệu tham khảo

- [Apache Kafka — Encryption and Authentication using SSL](https://kafka.apache.org/documentation/#security_ssl)
- [Apache Kafka — SSL Configurations](https://kafka.apache.org/documentation/#brokerconfigs_ssl)
- [Spring for Apache Kafka — Connecting to Kafka](https://docs.spring.io/spring-kafka/reference/kafka/connecting.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
