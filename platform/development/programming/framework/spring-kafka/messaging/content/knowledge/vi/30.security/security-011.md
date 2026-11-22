# Kiểm tra kết nối bảo mật

## 1. Kiểm tra theo từng lớp

Một ứng dụng Spring Kafka kết nối được tới broker chưa có nghĩa toàn bộ cấu hình bảo mật đã đúng. Kết nối Kafka có nhiều lớp: DNS và mạng, TLS, xác thực SASL hoặc chứng thư client, phân quyền ACL, rồi mới đến thao tác producer/consumer thực tế.

Ví dụ, `order-service` có thể mở TCP tới `broker.example:9093` nhưng thất bại khi xác minh chứng thư TLS. Hoặc TLS và SASL đều thành công nhưng producer vẫn không ghi được topic `orders` vì principal thiếu quyền `WRITE`.

Hãy xác minh theo thứ tự:

1. Ứng dụng phân giải được hostname và mở kết nối tới broker.
2. TLS bắt tay thành công, chứng thư broker còn hạn và hostname khớp SAN.
3. SASL hoặc mutual TLS xác thực đúng danh tính client.
4. Broker cho phép principal thực hiện thao tác cần thiết.
5. Producer gửi được record và consumer đọc được record theo đúng consumer group.

~~~mermaid
flowchart TD
    A["Spring Kafka client"] --> B["DNS / TCP"]
    B --> C["TLS handshake"]
    C --> D["SASL authentication hoặc mTLS"]
    D --> E["Kafka ACL"]
    E --> F["Metadata / produce / fetch / commit"]
    B --> X1["Network / DNS error"]
    C --> X2["SSLHandshakeException"]
    D --> X3["SaslAuthenticationException"]
    E --> X4["Authorization error"]
~~~

Khi một bước thất bại, xử lý ở đúng lớp. Không đổi ACL để chữa lỗi certificate hoặc tắt TLS hostname verification để né DNS sai.

## 2. Phân biệt TLS, SASL và ACL

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| TLS | Kênh truyền có được mã hóa và broker có đúng danh tính không? | Certificate broker do CA tin cậy ký |
| SASL | Client kết nối với danh tính nào? | Username/password SCRAM |
| mTLS | Client chứng minh danh tính bằng certificate nào? | Client certificate và private key |
| ACL | Danh tính đã xác thực được phép làm gì? | Principal được WRITE topic orders |

Các giá trị `security.protocol` thường gặp:

| Giá trị | TLS | SASL | Trường hợp sử dụng |
|---|---:|---:|---|
| `PLAINTEXT` | Không | Không | Môi trường phát triển cô lập |
| `SSL` | Có | Không | TLS, có thể kết hợp client certificate |
| `SASL_PLAINTEXT` | Không | Có | Tránh dùng trên mạng không tin cậy |
| `SASL_SSL` | Có | Có | Phổ biến cho production dùng SASL |

`SASL_SSL` kết hợp TLS với SASL; client certificate không bắt buộc trừ khi broker yêu cầu mTLS. TLS bảo vệ kênh truyền và xác minh broker. SASL xác thực principal. ACL kiểm soát principal được đọc topic, ghi topic, tham gia group hoặc gọi thao tác quản trị nào.

## 3. TLS: truststore và certificate broker

Khi client kết nối qua TLS, client phải tin CA đã ký certificate của broker. Với Java Kafka client, CA thường được đưa vào truststore dạng JKS hoặc PKCS12.

| Thuộc tính | Mục đích |
|---|---|
| `ssl.truststore.location` | Đường dẫn truststore chứa CA tin cậy |
| `ssl.truststore.password` | Mật khẩu truststore nếu được đặt |
| `ssl.truststore.type` | Kiểu truststore, ví dụ PKCS12 hoặc JKS |
| `ssl.endpoint.identification.algorithm` | Thuật toán kiểm tra hostname của broker |

Certificate broker cần có SAN phù hợp với hostname mà client sử dụng. Nếu ứng dụng kết nối `broker.example.com` nhưng certificate chỉ có SAN `kafka.internal`, TLS hostname verification sẽ thất bại.

Không tắt hostname verification bằng cách đặt `ssl.endpoint.identification.algorithm` thành chuỗi rỗng để làm kết nối chạy được. Hãy sửa DNS, `advertised.listeners` hoặc SAN của certificate cho khớp.

Ví dụ truststore PKCS12 được mount trong container:

~~~text
/run/secrets/kafka/truststore.p12
~~~

Truststore thường chứa CA root và intermediate cần thiết để xác minh certificate chain. Không đưa private key của broker vào truststore client.

## 4. Spring Boot với SASL_SSL và SCRAM

Ví dụ sau dùng TLS để mã hóa kết nối và SASL/SCRAM-SHA-512 để xác thực username/password:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: "${KAFKA_SASL_JAAS_CONFIG}"
      ssl.truststore.location: "${KAFKA_TRUSTSTORE_LOCATION}"
      ssl.truststore.password: "${KAFKA_TRUSTSTORE_PASSWORD}"
      ssl.truststore.type: PKCS12
      ssl.endpoint.identification.algorithm: https
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Các placeholder biểu thị biến môi trường hoặc giá trị được cấp từ secret manager. Ví dụ giá trị của `KAFKA_SASL_JAAS_CONFIG`:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required username="order-service" password="secret-from-secret-manager";
~~~

Trong môi trường thật, không ghi username/password vào YAML, Git, Docker image hoặc log. Inject secret qua Kubernetes Secret, Vault hoặc secret manager; hạn chế quyền đọc secret và xoay vòng credential theo quy trình vận hành.

`spring.kafka.properties` là nơi cấu hình thuộc tính Kafka dùng chung. Nếu producer, consumer hoặc admin client cần thiết lập khác nhau, dùng nhóm `spring.kafka.producer.properties`, `spring.kafka.consumer.properties` hoặc `spring.kafka.admin.properties` tương ứng. Tránh cấu hình cùng một thuộc tính ở nhiều nơi với giá trị mâu thuẫn.

`SCRAM-SHA-512` chỉ là ví dụ. Cơ chế SASL phải khớp với listener của broker và credential đã được provision. Một số cluster dùng SCRAM-SHA-256, PLAIN hoặc OAuth Bearer; hãy lấy đúng cơ chế từ cấu hình nền tảng.

## 5. SASL mechanism và JAAS

SASL cung cấp cơ chế xác thực. Kafka Java client cần `sasl.mechanism` và `sasl.jaas.config` khớp với cơ chế broker cho phép.

Ví dụ SCRAM:

~~~properties
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="order-service" password="replace-with-secret";
~~~

Ví dụ PLAIN:

~~~properties
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="order-service" password="replace-with-secret";
~~~

`PLAIN` chỉ nên sử dụng qua `SASL_SSL` để bảo vệ credential trên đường truyền. Không dùng `SASL_PLAINTEXT` trên mạng không tin cậy.

Lỗi cấu hình thường gặp:

- Chọn SCRAM-SHA-512 trong client nhưng broker chỉ bật SCRAM-SHA-256.
- JAAS module không khớp với mechanism.
- Username/password đã xoay vòng nhưng ứng dụng vẫn dùng secret cũ.
- Chuỗi JAAS thiếu dấu nháy hoặc dấu chấm phẩy kết thúc.
- Secret chứa ký tự đặc biệt nhưng được escape sai trong YAML hoặc biến môi trường.

Không đưa JAAS string vào log. Chỉ log mechanism và tên secret reference không nhạy cảm; không log password hoặc token.

Với OAuth Bearer, callback handler và token endpoint phụ thuộc thư viện/provider. Không sao chép JAAS snippet SCRAM/PLAIN sang OAuth; dùng cấu hình chính thức của identity provider và Kafka client version tương ứng.

## 6. Mutual TLS: xác thực client bằng certificate

Một số cluster yêu cầu client trình certificate riêng ngoài việc xác minh certificate broker. Đây là mutual TLS (mTLS).

Client cần truststore chứa CA tin cậy để xác minh broker, keystore chứa client certificate và private key, cùng mật khẩu keystore/key nếu được bảo vệ. Broker cần principal mapping phù hợp để nhận diện và phân quyền certificate.

Bổ sung các thuộc tính sau khi broker yêu cầu mTLS:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SSL
      ssl.truststore.location: "${KAFKA_TRUSTSTORE_LOCATION}"
      ssl.truststore.password: "${KAFKA_TRUSTSTORE_PASSWORD}"
      ssl.truststore.type: PKCS12
      ssl.keystore.location: "${KAFKA_KEYSTORE_LOCATION}"
      ssl.keystore.password: "${KAFKA_KEYSTORE_PASSWORD}"
      ssl.key.password: "${KAFKA_PRIVATE_KEY_PASSWORD}"
      ssl.keystore.type: PKCS12
      ssl.endpoint.identification.algorithm: https
~~~

Nếu cluster yêu cầu cả SASL và mTLS, dùng `SASL_SSL` đồng thời cấu hình truststore, keystore và SASL mechanism. Certificate client xác thực ở lớp TLS; SASL là lớp xác thực bổ sung nếu listener yêu cầu cả hai.

Không nhầm truststore với keystore:

- Truststore chứa certificate CA mà client tin cậy.
- Keystore chứa danh tính client và private key của client.

Private key phải được bảo vệ như credential. Không commit keystore vào repository và không chia sẻ một client certificate giữa các dịch vụ nếu cần truy vết principal và thu hồi quyền riêng biệt.

## 7. Kiểm tra bằng Kafka command-line tools

Trước khi debug Spring application, có thể dùng Kafka CLI với cùng bootstrap server và cấu hình bảo mật để tách lỗi môi trường khỏi lỗi code.

Tạo file `client.properties` bên ngoài repository, với quyền đọc giới hạn:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="order-service" password="replace-with-secret";
ssl.truststore.location=/run/secrets/kafka/truststore.p12
ssl.truststore.password=replace-with-secret
ssl.truststore.type=PKCS12
ssl.endpoint.identification.algorithm=https
~~~

Chạy kiểm tra API versions:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker.example.com:9093 \
  --command-config client.properties
~~~

Lệnh này kiểm tra khả năng kết nối và trao đổi protocol với broker. Nó chưa chứng minh principal có quyền ghi hoặc đọc một topic cụ thể.

Kiểm tra metadata của topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker.example.com:9093 \
  --command-config client.properties \
  --describe \
  --topic orders
~~~

Lệnh `--describe` cần quyền phù hợp để xem metadata topic. Nếu kết nối và xác thực thành công nhưng lệnh bị từ chối, hãy kiểm tra ACL cho principal.

Không đưa `client.properties` chứa secret vào Git, artifact build hoặc log CI. Dùng file tạm được cấp từ secret manager và xóa theo chính sách sau khi kiểm tra.

## 8. Kiểm tra bằng AdminClient

Có thể dùng Kafka `AdminClient` để kiểm tra broker metadata từ cùng môi trường chạy Spring application. Ví dụ dưới đây tạo client với cấu hình SASL_SSL và yêu cầu metadata cluster:

~~~java
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.common.config.SslConfigs;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class KafkaConnectionProbe {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaConnectionProbe.class);

    public void verify(
            String bootstrapServers,
            String jaasConfig,
            String truststorePath,
            String truststorePassword) throws Exception {

        var properties = new Properties();
        properties.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );
        properties.put(
            CommonClientConfigs.SECURITY_PROTOCOL_CONFIG,
            "SASL_SSL"
        );
        properties.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");
        properties.put(SaslConfigs.SASL_JAAS_CONFIG, jaasConfig);
        properties.put(
            SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
            truststorePath
        );
        properties.put(
            SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
            truststorePassword
        );
        properties.put(
            SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG,
            "PKCS12"
        );
        properties.put(
            SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
            "https"
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            var nodes = admin.describeCluster()
                .nodes()
                .get(10, TimeUnit.SECONDS);

            log.info(
                "Kafka metadata probe thành công, brokerCount={}",
                nodes.size()
            );
        }
    }
}
~~~

Ví dụ kiểm tra kết nối, TLS, SASL và truy vấn metadata cluster. `describeCluster()` có thể yêu cầu quyền `DESCRIBE` ở cấp cluster tùy cấu hình broker. Nếu principal chỉ có quyền produce/consume topic mà không có quyền xem cluster, probe có thể thất bại vì authorization dù kết nối bảo mật đã thành công.

Trong Spring Boot, có thể tái sử dụng cấu hình Kafka đã externalize thay vì tạo bộ cấu hình thứ hai. Probe cần dùng cùng bootstrap server, truststore, SASL mechanism và secret như producer/consumer thực tế.

Không gọi probe cho từng message. Có thể chạy lúc startup, trong readiness check với timeout hữu hạn hoặc trong công cụ vận hành theo lịch. Tránh tạo quá nhiều AdminClient liên tục.

## 9. Kiểm tra quyền produce và consume thực tế

Metadata probe không chứng minh producer có quyền ghi hoặc consumer có quyền đọc. Hãy kiểm tra từng thao tác bằng principal và topic mà ứng dụng thực sự sử dụng.

### Kiểm tra producer

Dùng topic kiểm tra được provision riêng và `KafkaTemplate` có kiểu/serializer khớp payload probe. Ví dụ dưới đây giả định template `KafkaTemplate<String, String>` dùng `StringSerializer`; nếu dùng template JSON của service, hãy gửi một event probe đúng kiểu thay vì ép generic sang `String`:

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.core.KafkaTemplate;

public class KafkaProducerProbe {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaProducerProbe(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void verifyWrite() throws Exception {
        String probeId = "probe-" + UUID.randomUUID();

        var result = kafkaTemplate.send(
            "connection-check",
            probeId,
            "secure-connection-check"
        ).get(10, TimeUnit.SECONDS);

        var metadata = result.getRecordMetadata();

        System.out.printf(
            "Produce OK: topic=%s partition=%d offset=%d%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
}
~~~

Future hoàn tất thành công cho biết broker đã xác nhận lần gửi theo cấu hình `acks`. Kiểm tra này cũng xác minh serializer, kết nối và quyền cần thiết cho thao tác ghi topic. Nó không chứng minh consumer đọc được record.

Dùng topic probe có retention ngắn và quyền ghi hạn chế. Không ghi record kiểm tra tùy tiện vào topic nghiệp vụ vì consumer production có thể xử lý chúng như dữ liệu thật.

### Kiểm tra consumer

Dùng consumer group kiểm tra riêng để xác minh principal có thể subscribe và đọc topic. Ví dụ CLI:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server broker.example.com:9093 \
  --consumer.config client.properties \
  --topic connection-check \
  --group connection-check-probe \
  --from-beginning \
  --timeout-ms 10000
~~~

Consumer cần quyền `READ` topic và quyền `READ` trên group theo ACL broker. Group ID mới có thể bắt đầu theo `auto.offset.reset`; chỉ dùng `--from-beginning` trên topic probe đã kiểm soát.

Để xác minh toàn luồng, gửi probe record rồi đọc nó bằng consumer test. Nếu producer thành công nhưng consumer không đọc được, kiểm tra topic ACL, group ACL, subscription, offset và deserializer.

## 10. Phân biệt authentication và authorization

Hai loại lỗi này có ý nghĩa khác nhau:

- **Authentication failure:** broker không xác minh được danh tính client. Ví dụ username/password sai, SASL mechanism không được hỗ trợ, certificate client không hợp lệ.
- **Authorization failure:** broker đã xác định principal nhưng principal không có quyền thực hiện thao tác. Ví dụ không có `WRITE` topic hoặc `READ` group.

Một số quyền Kafka thường gặp:

| Thao tác | Quyền thường cần |
|---|---|
| Gửi record | `WRITE` trên topic; một số client flow có thể cần `DESCRIBE` |
| Đọc record | `READ` trên topic |
| Tham gia consumer group và commit offset | `READ` trên group |
| Xem metadata topic | `DESCRIBE` trên topic |
| Xem metadata cluster | `DESCRIBE` trên cluster |
| Tạo topic | `CREATE` ở phạm vi được cấp hoặc quyền tương đương theo broker policy |

Resource, operation và cách kế thừa quyền phụ thuộc Kafka ACL authorizer và cấu hình broker. Hãy cấp quyền tối thiểu theo principal của từng service; không cấp superuser để chữa lỗi authorization.

Nếu producer ghi được nhưng consumer không đọc được, kiểm tra quyền topic và group riêng biệt. Nếu AdminClient probe thất bại vì thiếu `DESCRIBE` cluster, đừng kết luận SASL/TLS sai khi các thao tác nghiệp vụ được cấp quyền vẫn hoạt động.

## 11. Chẩn đoán lỗi kết nối thường gặp

| Lỗi hoặc biểu hiện | Lớp có khả năng lỗi | Kiểm tra và hướng xử lý |
|---|---|---|
| `UnknownHostException` | DNS | Kiểm tra hostname, DNS trong container/pod và địa chỉ broker |
| `Connection refused` | TCP/listener | Kiểm tra port, firewall, broker listener và service endpoint |
| Timeout khi lấy metadata | Network hoặc advertised listener | Kiểm tra route tới tất cả broker được quảng bá trong metadata |
| `SSLHandshakeException` | TLS | Kiểm tra protocol, certificate chain, truststore, expiry và TLS version |
| `PKIX path building failed` | Trust chain | Import đúng CA/intermediate vào truststore và kiểm tra certificate chain |
| Hostname/SAN mismatch | TLS identity | Kết nối bằng hostname có trong SAN hoặc cấp certificate đúng SAN |
| `SaslAuthenticationException` | SASL authentication | Kiểm tra mechanism, JAAS module, username/password và trạng thái credential |
| `UnsupportedSaslMechanismException` | SASL negotiation | Chọn mechanism broker đang bật |
| `TopicAuthorizationException` | ACL topic | Cấp quyền đúng thao tác trên topic |
| `GroupAuthorizationException` | ACL consumer group | Cấp READ cho group cần dùng |
| `ClusterAuthorizationException` | ACL cluster | Xác minh thao tác admin có được phép hay không |
| CLI thành công nhưng Spring thất bại | Khác cấu hình hoặc runtime | So sánh bootstrap server, secret, truststore mount, serializer và client properties |

### Lưu ý về advertised.listeners

Client chỉ dùng `bootstrap.servers` để tìm broker ban đầu. Sau khi lấy metadata, Kafka client kết nối đến các địa chỉ được broker quảng bá qua `advertised.listeners`.

Vì vậy, có thể kết nối được bootstrap broker nhưng vẫn timeout khi produce/consume nếu hostname trong metadata không phân giải được hoặc không thể truy cập từ mạng của ứng dụng. Certificate TLS cũng phải hợp lệ với hostname mà client thực sự kết nối sau khi nhận metadata.

Khi chạy trong Kubernetes, kiểm tra DNS và network policy từ bên trong đúng pod/namespace. Kiểm tra trên laptop không chứng minh container production có cùng đường mạng.

## 12. Kiểm tra cấu hình hiệu lực của Spring

Khi CLI thành công nhưng ứng dụng Spring Kafka thất bại, so sánh cấu hình hiệu lực của hai client:

- `bootstrap.servers` và toàn bộ broker hostname trong `advertised.listeners`.
- `security.protocol` có phải SASL_SSL hoặc SSL như listener broker yêu cầu.
- `sasl.mechanism` và JAAS module có khớp nhau.
- Secret được mount đúng path và process có quyền đọc.
- Truststore/keystore đúng định dạng và certificate chưa hết hạn.
- `ssl.endpoint.identification.algorithm` không bị tắt ngoài ý muốn.
- Producer, consumer và AdminClient có nhận common properties hay không.
- Producer/consumer override có ghi đè security protocol hoặc SASL settings không.

Spring Boot có thể áp dụng common properties và thuộc tính riêng cho từng client. Nếu một client hoạt động còn client khác không, hãy kiểm tra cấu hình riêng của client đó thay vì chỉ nhìn `spring.kafka.properties`.

Không dump toàn bộ Environment, Properties hoặc JAAS string ra log. Nếu cần debug, chỉ in tên property không nhạy cảm và trạng thái đã cấu hình/thiếu; che password, token, private key và truststore password.

## 13. Kiểm thử bảo mật đúng môi trường

Kiểm thử Kafka bằng broker local `PLAINTEXT` hữu ích cho logic messaging nhưng không xác minh TLS, SASL, certificate rotation hoặc ACL production.

Một chiến lược kiểm thử nên có:

1. **Unit test:** kiểm tra property binding và việc secret được truyền qua cấu hình mà không ghi giá trị secret vào log.
2. **Integration test TLS:** chạy broker test với CA riêng và client truststore đúng.
3. **Integration test SASL:** bật mechanism tương ứng, xác minh credential đúng kết nối và credential sai bị từ chối.
4. **Integration test ACL:** principal được phép produce/consume thành công; principal thiếu quyền nhận authorization error.
5. **Staging smoke test:** dùng certificate, secret manager, DNS, network policy và broker listener như production.
6. **Rotation test:** thay credential hoặc certificate theo quy trình và xác minh client được restart/recreate an toàn.

Testcontainers chỉ xác minh bảo mật nếu broker container được cấu hình TLS/SASL/ACL tương ứng. Broker test mặc định không bật các cơ chế này không thể chứng minh kết nối production an toàn.

Không dùng certificate hoặc credential production trong test. Tạo CA, principal và secret riêng cho môi trường test.

## 14. Readiness, health check và vận hành

Có thể dùng probe kết nối Kafka để xác định ứng dụng có khả năng giao tiếp với broker trước khi nhận traffic. Tuy nhiên, cần phân biệt:

- **Liveness:** tiến trình ứng dụng còn sống và không bị treo.
- **Readiness:** ứng dụng đã sẵn sàng thực hiện công việc cần Kafka.
- **Operation probe:** thao tác cụ thể như describe cluster, produce hoặc consume có thành công không.

Không nên để liveness phụ thuộc trực tiếp vào Kafka trong mọi trường hợp. Nếu broker tạm thời mất kết nối, Kubernetes restart tất cả pod liên tục có thể làm sự cố nặng hơn. Readiness có thể phản ánh Kafka unavailable nếu ứng dụng không thể phục vụ nghiệp vụ khi thiếu broker; lựa chọn này phụ thuộc kiến trúc.

Probe phải có timeout hữu hạn, giới hạn tần suất và không tạo record vào topic nghiệp vụ. Nếu cần kiểm tra produce/consume, dùng topic probe và group chuyên biệt, có ACL riêng.

Khi certificate hoặc password được xoay vòng, Kafka client đã tạo có thể vẫn giữ cấu hình cũ. Quy trình rotation cần cập nhật secret, tạo lại producer/consumer hoặc restart ứng dụng theo chiến lược triển khai. Không giả định chỉ thay file secret trên disk sẽ tự làm Kafka client reload truststore, keystore hoặc SASL credential.

## 15. Checklist kiểm tra kết nối bảo mật

- [ ] Xác minh DNS, TCP và route tới bootstrap server.
- [ ] Kiểm tra các địa chỉ broker trong `advertised.listeners` đều truy cập được từ runtime.
- [ ] Chọn đúng `security.protocol` theo listener broker.
- [ ] Kiểm tra certificate chain, thời hạn và SAN hostname.
- [ ] Dùng truststore chứa CA đúng; không tắt hostname verification để né lỗi.
- [ ] Nếu dùng mTLS, kiểm tra client certificate, private key và keystore.
- [ ] Nếu dùng SASL, xác minh mechanism, JAAS module và secret.
- [ ] Chỉ dùng SASL PLAIN qua TLS.
- [ ] Tách biệt authentication failure với authorization failure.
- [ ] Cấp ACL tối thiểu cho topic, group và thao tác admin cần thiết.
- [ ] Kiểm tra bằng Kafka CLI với cùng cấu hình bảo mật.
- [ ] Kiểm tra metadata bằng AdminClient nếu principal có quyền phù hợp.
- [ ] Thử produce và consume trên topic probe riêng.
- [ ] Không ghi secret, token, password hoặc private key vào log/repository.
- [ ] Kiểm thử certificate/credential rotation và readiness trong staging.

Kiểm tra kết nối bảo mật cần chứng minh cả kênh truyền, danh tính và quyền thao tác. TLS bảo vệ đường truyền và xác minh broker; SASL hoặc mTLS xác thực client; ACL giới hạn thao tác trên topic, group và cluster. Khi xác minh từng lớp bằng CLI, AdminClient và một lần produce/consume thực tế, nhóm phát triển có thể xác định chính xác cấu hình nào đang lỗi và vận hành Spring Kafka an toàn hơn.
