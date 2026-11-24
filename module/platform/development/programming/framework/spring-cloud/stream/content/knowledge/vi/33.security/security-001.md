# Xác thực và mã hóa kết nối Kafka bằng SASL, SSL và TLS

## Mục tiêu

Ứng dụng Spring Cloud Stream kết nối tới Kafka qua các client do Kafka binder tạo ra: producer, consumer, AdminClient và, với mô hình xử lý tương ứng, Kafka Streams. Trong production, kết nối cần xác minh đúng broker, mã hóa dữ liệu trên đường truyền, xác thực danh tính ứng dụng và giới hạn quyền truy cập theo topic/group.

Kafka cung cấp hai nhóm cơ chế thường được cấu hình cùng nhau:

- **SSL/TLS** bảo vệ đường truyền bằng mã hóa và xác minh chứng thư của broker. Kafka vẫn dùng tiền tố cấu hình ssl.* dù giao thức bảo mật thực tế là TLS.
- **SASL** xác thực danh tính client bằng cơ chế như SCRAM, PLAIN, Kerberos hoặc OAuth.
- **mTLS** là TLS có xác thực chứng thư hai chiều: broker xác minh chứng thư client khi listener yêu cầu.
- **ACL** quyết định principal đã xác thực được phép đọc, ghi hoặc quản trị tài nguyên nào.

Bài học này tập trung vào cấu hình client của Spring Cloud Stream Kafka binder, phân biệt các giao thức SSL/SASL, thiết lập truststore/keystore, dùng JAAS cho SASL, cấu hình Kafka Streams binder, quản lý secret và kiểm thử kết nối bảo mật.

Sau bài học, bạn có thể:

- Phân biệt mã hóa TLS, xác thực SASL, xác thực chứng thư mTLS và phân quyền ACL.
- Chọn đúng security.protocol: SSL, SASL_SSL hoặc SASL_PLAINTEXT.
- Cấu hình truststore để xác minh chứng thư broker.
- Cấu hình keystore khi broker yêu cầu client certificate.
- Cấu hình SASL/PLAIN, SCRAM, GSSAPI hoặc OAUTHBEARER theo broker.
- Đặt security properties trong namespace của Kafka binder.
- Phân biệt cấu hình regular Kafka binder với Kafka Streams binder.
- Quản lý JAAS, credential và certificate bằng secret management.
- Cấp ACL tối thiểu cho producer, consumer, group và internal topics.
- Kiểm thử TLS handshake, SASL authentication, authorization và xử lý lỗi thường gặp.

## 1. Ba lớp bảo mật cần phân biệt

Một kết nối Kafka an toàn thường cần nhiều lớp. Chúng giải quyết các câu hỏi khác nhau:

| Lớp | Câu hỏi được giải quyết | Cơ chế |
|---|---|---|
| Mã hóa đường truyền | Người nghe lén trên mạng có đọc được dữ liệu không? | TLS |
| Xác thực | Client đang kết nối là ai? Broker có đúng danh tính không? | SASL, server certificate, mTLS |
| Phân quyền | Principal này được phép làm gì? | Kafka ACL hoặc authorizer |

TLS mã hóa dữ liệu giữa client và broker. Trong TLS thông thường, client xác minh chứng thư server; broker không nhất thiết xác minh danh tính client ở tầng chứng thư. Nếu broker bật client authentication, client phải trình chứng thư được CA mà broker tin cậy ký.

SASL xác thực principal của Kafka bằng cơ chế được broker bật. Khi dùng SASL_SSL, TLS bảo vệ handshake và dữ liệu, còn SASL xác thực danh tính Kafka. Sau khi xác thực, broker dùng principal để kiểm tra ACL.

Một client có thể kết nối TLS thành công nhưng vẫn bị từ chối do SASL credential sai. Client cũng có thể xác thực SASL thành công nhưng bị TopicAuthorizationException nếu principal không có quyền trên topic.

## 2. Các giá trị security.protocol

Kafka client dùng thuộc tính security.protocol để chọn loại kết nối:

| security.protocol | Mã hóa TLS | Xác thực SASL | Tình huống |
|---|---|---|---|
| PLAINTEXT | Không | Không | Chỉ môi trường test kín, không có dữ liệu/credential nhạy cảm |
| SSL | Có | Không | TLS server authentication; có thể thêm mTLS |
| SASL_PLAINTEXT | Không | Có | Chỉ dùng trong môi trường test được kiểm soát; credential không được mã hóa trên đường truyền |
| SASL_SSL | Có | Có | Lựa chọn phổ biến cho production khi dùng SASL |

SSL là tên giao thức trong cấu hình Kafka và tên các thuộc tính client; các kết nối hiện đại dùng TLS. Không cần một giao thức Kafka riêng tên TLS để bật mã hóa.

**SASL_SSL** thường là lựa chọn phù hợp khi ứng dụng cần cả xác thực principal bằng SASL và mã hóa đường truyền bằng TLS. **SSL** phù hợp khi hệ thống dùng client certificate để xác thực hoặc chỉ cần TLS server authentication theo chính sách. Tránh dùng SASL_PLAINTEXT trên mạng không tin cậy vì username/password hoặc dữ liệu xác thực có thể bị lộ.

## 3. TLS bảo vệ kết nối như thế nào?

Trong TLS handshake, client và broker thương lượng phiên mã hóa, xác minh chứng thư và thiết lập khóa phiên. Sau handshake, dữ liệu Kafka protocol được truyền trong kênh TLS.

Để xác minh broker, client cần tin cậy CA đã ký chứng thư server. Chứng thư broker phải có Subject Alternative Name (SAN) khớp hostname hoặc IP mà client dùng để kết nối.

Luồng kết nối:

    Spring Cloud Stream application
        -> Kafka binder / Kafka client
        -> TLS handshake
        -> Kiểm tra chain chứng thư và hostname broker
        -> (Nếu dùng SASL_SSL) SASL authentication
        -> Kafka authorization bằng ACL
        -> Produce / consume / metadata request

Nếu hostname trong bootstrap.servers là kafka-1.example.internal nhưng SAN của chứng thư chỉ chứa kafka-old.example.internal, hostname verification sẽ thất bại dù truststore có CA đúng.

Kafka client bật hostname verification theo mặc định trong các phiên bản hiện đại. Thuộc tính ssl.endpoint.identification.algorithm thường là https. Không tắt hostname verification bằng chuỗi rỗng chỉ để bỏ qua lỗi chứng thư; hãy sửa SAN, DNS hoặc địa chỉ advertised.listeners.

## 4. Truststore và keystore khác nhau thế nào?

Hai loại store thường bị nhầm:

| Store | Chứa gì? | Ai sử dụng? | Mục đích |
|---|---|---|---|
| Truststore | CA hoặc certificate mà bên kết nối tin cậy | Client trust broker; broker trust client CA khi mTLS | Xác minh chứng thư của peer |
| Keystore | Private key và certificate chain của chính identity | Broker giữ server identity; client giữ client identity nếu mTLS | Trình bày danh tính bằng chứng thư |

Với TLS một chiều phổ biến:

- Broker có keystore chứa private key và server certificate.
- Client có truststore chứa CA đã ký server certificate.
- Client không cần keystore nếu broker không yêu cầu client certificate.

Với mutual TLS:

- Client vẫn có truststore để xác minh broker.
- Client có thêm keystore chứa client private key và certificate.
- Broker cấu hình client authentication và truststore chứa CA ký client certificate.

Private key trong keystore là dữ liệu nhạy cảm. Truststore chứa CA công khai thường không bí mật, nhưng vẫn cần kiểm soát nguồn phát hành để tránh tin nhầm CA.

## 5. Cấu hình TLS-only trong Kafka binder

Nếu broker listener dùng TLS và không yêu cầu SASL, regular Kafka binder có thể cấu hình SSL như sau:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: kafka-1.example.internal:9093,kafka-2.example.internal:9093
              configuration:
                security.protocol: SSL
                ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                ssl.truststore.type: PKCS12
                ssl.endpoint.identification.algorithm: https
                ssl.enabled.protocols: TLSv1.2,TLSv1.3

Các thuộc tính quan trọng:

- brokers phải trỏ tới listener TLS, không phải listener PLAINTEXT.
- security.protocol: SSL bật TLS cho Kafka client.
- ssl.truststore.location là đường dẫn truststore trong container/host chạy ứng dụng.
- ssl.truststore.password mở truststore nếu store có password.
- ssl.truststore.type phải khớp định dạng thực tế, ví dụ PKCS12 hoặc JKS.
- ssl.endpoint.identification.algorithm bật xác minh hostname.
- ssl.enabled.protocols giới hạn phiên bản TLS được phép thương lượng.

TLS 1.2 là mức tương thích phổ biến; có thể bật TLS 1.3 khi JDK, Kafka client và broker đều hỗ trợ. Không bật TLS cũ chỉ để tương thích với một broker đã hết hỗ trợ; hãy nâng cấp endpoint hoặc lập kế hoạch tương thích có thời hạn.

## 6. Cấu hình mTLS khi broker yêu cầu client certificate

Nếu listener yêu cầu client certificate, broker cần xác minh certificate chain của client. Client bổ sung keystore:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: kafka-1.example.internal:9093
              configuration:
                security.protocol: SSL
                ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                ssl.truststore.type: PKCS12
                ssl.keystore.location: ${KAFKA_KEYSTORE_LOCATION}
                ssl.keystore.password: ${KAFKA_KEYSTORE_PASSWORD}
                ssl.key.password: ${KAFKA_PRIVATE_KEY_PASSWORD}
                ssl.keystore.type: PKCS12
                ssl.endpoint.identification.algorithm: https

Trong ví dụ:

- Truststore giúp client xác minh broker.
- Keystore chứa client certificate và private key.
- ssl.keystore.password mở keystore.
- ssl.key.password mở private key nếu private key có password riêng.

Phía broker phải bật client authentication, ví dụ ssl.client.auth=required, và có truststore chứa CA ký client certificate. Nếu broker chỉ yêu cầu TLS server authentication, không cần cung cấp client keystore.

Khi dùng mTLS với SASL, client có thể vừa trình client certificate ở TLS handshake vừa xác thực SASL. Hai lớp có thể cùng tồn tại nếu listener và policy của cluster được cấu hình tương ứng.

## 7. Kết hợp SASL_SSL và SCRAM

SCRAM-SHA-256 và SCRAM-SHA-512 xác thực username/password theo challenge-response. Kafka hỗ trợ SCRAM ở broker và client; cơ chế phải được bật ở broker và client phải chọn đúng tên mechanism.

Ví dụ regular Kafka binder dùng SASL_SSL với SCRAM-SHA-512:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: kafka-1.example.internal:9093,kafka-2.example.internal:9093
              configuration:
                security.protocol: SASL_SSL
                sasl.mechanism: SCRAM-SHA-512
                sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'
                ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                ssl.truststore.type: PKCS12
                ssl.endpoint.identification.algorithm: https
                ssl.enabled.protocols: TLSv1.2,TLSv1.3

JAAS config chỉ định login module và credential. Placeholder ở ví dụ được resolve từ external configuration; không ghi username/password thật vào source control.

Broker phải bật SCRAM-SHA-512 trên listener và đã tạo credential cho principal. Chỉ cấu hình client không tự tạo user hoặc credential trên broker. Việc provision user nên được quản trị bằng công cụ và quyền admin của cluster.

SCRAM nên chạy qua TLS. TLS ngăn kẻ nghe lén quan sát trao đổi xác thực và bảo vệ dữ liệu Kafka sau khi xác thực.

## 8. Các SASL mechanism thường gặp

| Mechanism | Cách xác thực | Khi nào dùng | Lưu ý |
|---|---|---|---|
| PLAIN | Username/password | Hệ thống có user store hoặc authentication callback | Chỉ dùng cùng TLS trong production |
| SCRAM-SHA-256 | Challenge-response với credential SCRAM | Username/password, không muốn gửi password trực tiếp trong SASL exchange | Dùng TLS và password mạnh |
| SCRAM-SHA-512 | Challenge-response với SHA-512 | Lựa chọn phổ biến cho cluster hỗ trợ SCRAM | Broker phải provision credential và bật mechanism |
| GSSAPI | Kerberos ticket/principal | Hệ thống đã có Kerberos hoặc Active Directory | Cần service principal, keytab và krb5 config |
| OAUTHBEARER | OAuth bearer token | Tích hợp identity provider/token service | Cần callback/token handler production phù hợp |

Tên mechanism trong cấu hình phải khớp broker listener. Nếu broker chỉ bật SCRAM-SHA-256 mà client chọn SCRAM-SHA-512, handshake sẽ thất bại.

### PLAIN

Client dùng login module:

    sasl.mechanism: PLAIN
    sasl.jaas.config: 'org.apache.kafka.common.security.plain.PlainLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'

PLAIN không tự mã hóa password. Dùng SASL_SSL để TLS bảo vệ credential và dữ liệu trên mạng. Không sử dụng SASL_PLAINTEXT cho credential PLAIN trong môi trường production.

### Kerberos/GSSAPI

Một cấu hình client có thể dùng keytab:

    sasl.mechanism: GSSAPI
    sasl.kerberos.service.name: kafka
    sasl.jaas.config: 'com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true keyTab="${KAFKA_KEYTAB}" principal="${KAFKA_PRINCIPAL}";'

Ứng dụng cần có krb5.conf phù hợp và quyền đọc keytab. Service name phải khớp principal service của broker. Trong môi trường Kerberos, dùng FQDN nhất quán cho bootstrap.servers và advertised.listeners để tránh lỗi DNS/SPN.

### OAuth/OAUTHBEARER

OAuth bearer cho phép client dùng token do identity provider cấp. Cấu hình thường cần sasl.mechanism=OAUTHBEARER và callback handler tương thích với hệ thống phát hành/refresh token. Kafka có implementation mặc định phục vụ mục đích phát triển, không nên dùng token unsecured đó cho production.

Với OAuth production, dùng callback handler hoặc integration do nền tảng cung cấp để lấy, refresh và xác minh token. Không hardcode access token dài hạn vào YAML; xử lý hết hạn, clock skew và thu hồi credential.

## 9. Cấu hình bảo mật trong Spring Cloud Stream regular Kafka binder

Spring Cloud Stream cung cấp property:

    spring.cloud.stream.kafka.binder.configuration

Map này chuyển Kafka client properties tới các client do binder tạo. Vì vậy, có thể đặt security.protocol, sasl.mechanism, sasl.jaas.config và các ssl.* properties tại đây.

Ví dụ dạng property phẳng:

    spring.cloud.stream.kafka.binder.configuration.security.protocol=SASL_SSL
    spring.cloud.stream.kafka.binder.configuration.sasl.mechanism=SCRAM-SHA-512
    spring.cloud.stream.kafka.binder.configuration.ssl.endpoint.identification.algorithm=https

Có thể dùng YAML nested map như các ví dụ ở trên. Các thuộc tính bảo mật được áp dụng cho các client mà binder tạo, bao gồm producer, consumer và AdminClient theo cấu hình binder.

Điều này quan trọng vì ứng dụng có thể gửi message thành công nhưng AdminClient không tạo được topic do thiếu cấu hình hoặc ACL. Khi bảo mật được bật, cần kiểm tra mọi client path, không chỉ producer hoặc consumer.

Trong môi trường production, thường tắt auto topic creation/partition management ở ứng dụng và provision topic/ACL bằng quy trình quản trị. Tài khoản runtime không nhất thiết có quyền admin để tạo hoặc thay đổi topic.

## 10. Cấu hình bảo mật cho Kafka Streams binder

Kafka Streams binder có namespace cấu hình riêng. Nếu ứng dụng dùng function nhận KStream/KTable, security properties phải được đặt dưới Kafka Streams binder configuration:

    spring:
      cloud:
        stream:
          kafka:
            streams:
              binder:
                brokers: kafka-1.example.internal:9093
                configuration:
                  security.protocol: SASL_SSL
                  sasl.mechanism: SCRAM-SHA-512
                  sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'
                  ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                  ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                  ssl.truststore.type: PKCS12
                  ssl.endpoint.identification.algorithm: https

Đây là namespace của Kafka Streams binder, không phải regular Kafka binder. Không copy cấu hình vào spring.cloud.stream.kafka.binder rồi giả định Kafka Streams topology tự nhận được nó.

Kafka Streams cũng cần quyền với applicationId consumer group và internal topics như changelog/repartition. ACL của principal phải cho phép đọc input topics, ghi output topics và thực hiện các thao tác cần thiết trên internal topics. Khi bật transactions hoặc idempotent producer, cần thêm quyền phù hợp với transactional ID theo cấu hình ứng dụng.

Nếu ứng dụng dùng nhiều binder, mỗi binder có thể cần broker, credential, truststore và ACL riêng.

## 11. Nhiều Kafka cluster với credential riêng

Spring Cloud Stream hỗ trợ nhiều binder instance. Mỗi binder có thể có environment riêng để cấu hình cluster và SASL JAAS riêng.

Ví dụ khung cấu hình:

    spring:
      cloud:
        stream:
          binders:
            secureKafkaA:
              type: kafka
              environment:
                spring:
                  cloud:
                    stream:
                      kafka:
                        binder:
                          brokers: kafka-a.example.internal:9093
                          configuration:
                            security.protocol: SASL_SSL
                            sasl.mechanism: SCRAM-SHA-512
                            sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_A_USERNAME}" password="${KAFKA_A_PASSWORD}";'
                            ssl.truststore.location: ${KAFKA_A_TRUSTSTORE}
                            ssl.truststore.password: ${KAFKA_A_TRUSTSTORE_PASSWORD}
            secureKafkaB:
              type: kafka
              environment:
                spring:
                  cloud:
                    stream:
                      kafka:
                        binder:
                          brokers: kafka-b.example.internal:9093
                          configuration:
                            security.protocol: SASL_SSL
                            sasl.mechanism: SCRAM-SHA-512
                            sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_B_USERNAME}" password="${KAFKA_B_PASSWORD}";'
                            ssl.truststore.location: ${KAFKA_B_TRUSTSTORE}
                            ssl.truststore.password: ${KAFKA_B_TRUSTSTORE_PASSWORD}
          bindings:
            orders-out-0:
              destination: orders.secure
              binder: secureKafkaA
            audit-out-0:
              destination: audit.secure
              binder: secureKafkaB

Mỗi binder có môi trường và credential riêng. Không dùng chung JAAS string cho hai cluster nếu principal hoặc password khác nhau. Đảm bảo binding được gán đúng binder và truststore chứa CA của đúng cluster.

Nếu cấu hình JAAS bằng property sasl.jaas.config, property này có ưu tiên cao trong việc chọn login configuration. Spring Cloud Stream cũng hỗ trợ JAAS file và một số Spring Boot JAAS properties. Không trộn JAAS file với Spring Boot JAAS properties trong cùng application khi tài liệu binder nêu rằng system property java.security.auth.login.config có thể khiến Spring Cloud Stream bỏ qua cấu hình Boot.

## 12. Cấu hình broker listener tương ứng

Client và broker phải thống nhất giao thức. Nếu client dùng SASL_SSL, broker phải có listener SASL_SSL, certificate hợp lệ và bật SASL mechanism tương ứng.

Ví dụ cấu hình broker tối giản cho listener SCRAM qua TLS:

    listeners=SASL_SSL://0.0.0.0:9093
    advertised.listeners=SASL_SSL://kafka-1.example.internal:9093
    sasl.enabled.mechanisms=SCRAM-SHA-512
    ssl.keystore.type=PKCS12
    ssl.keystore.location=/etc/kafka/secrets/broker.keystore.p12
    ssl.keystore.password=<broker-keystore-password>
    ssl.key.password=<broker-private-key-password>
    ssl.client.auth=none

Broker giữ private key và server certificate trong keystore. Client cần trust CA ký certificate đó. Với mTLS, đặt ssl.client.auth=required và cấu hình broker truststore chứa CA ký client certificate.

Cấu hình listener thực tế còn cần các listener nội bộ, controller/inter-broker listener, advertised listener, ACL authorizer và credential provisioning. Không sao chép nguyên ví dụ tối giản vào cluster production mà chưa xác định topology broker.

### Broker bật SASL mechanism

Ví dụ broker chỉ bật SCRAM-SHA-512:

    sasl.enabled.mechanisms=SCRAM-SHA-512

Tạo credential cho client principal bằng công cụ quản trị Kafka theo phiên bản cluster. Với KRaft, SCRAM credential được lưu trong metadata log. Không tạo user chỉ ở client; broker phải có credential tương ứng hoặc được tích hợp authentication backend.

## 13. JAAS file và Spring Boot properties

Có hai cách phổ biến để cung cấp JAAS:

1. Client property sasl.jaas.config, thường đặt trong Kafka binder configuration.
2. JAAS file được JVM nạp qua system property java.security.auth.login.config.

Ví dụ JAAS file cho client Kerberos:

    KafkaClient {
        com.sun.security.auth.module.Krb5LoginModule required
        useKeyTab=true
        storeKey=true
        keyTab="/etc/security/keytabs/kafka-client.keytab"
        principal="stream-service@EXAMPLE.COM";
    };

Khởi chạy JVM với:

    -Djava.security.auth.login.config=/etc/kafka/kafka-client-jaas.conf
    -Djava.security.krb5.conf=/etc/krb5.conf

Nếu dùng JAAS file, bảo đảm file chỉ đọc được bởi user chạy ứng dụng. Với password-based mechanism, không commit file chứa credential vào repository.

Spring Cloud Stream còn có các property jaas.loginModule, jaas.controlFlag và jaas.options cho login context mà binder hỗ trợ, đặc biệt hữu ích với Kerberos. Với SCRAM/PLAIN, client property sasl.jaas.config là cách trực tiếp để cung cấp login module và options.

Không trộn các chiến lược JAAS trong cùng ứng dụng nếu chưa hiểu precedence. Kiểm tra log startup và effective client configuration để biết cấu hình nào được dùng.

## 14. TLS certificate, hostname và trust chain

Các bước chuẩn bị certificate:

1. Dùng CA nội bộ hoặc CA được tổ chức tin cậy phát hành certificate cho từng broker.
2. Mỗi broker giữ private key và certificate chain trong keystore.
3. SAN của certificate phải bao gồm hostname/IP trong advertised.listeners mà client sẽ kết nối.
4. Client truststore chứa CA root và intermediate CA cần thiết.
5. Nếu dùng mTLS, client có certificate/private key riêng và broker trust CA ký certificate đó.
6. Thiết lập thời hạn certificate, lịch rotation và cảnh báo expiry.

Không dùng certificate self-signed tùy tiện trong production. Nếu dùng CA nội bộ, quản lý CA private key như tài sản đặc biệt nhạy cảm. Không phân phối CA signing key tới ứng dụng client; client chỉ cần CA certificate công khai trong truststore.

Khi broker trả metadata, client có thể kết nối tới các broker khác trong advertised.listeners. Mọi hostname được quảng bá đều phải resolve được và certificate của broker tương ứng phải có SAN khớp hostname đó. Một bootstrap server đúng nhưng advertised listener sai vẫn có thể gây lỗi sau lần metadata request đầu tiên.

### Kiểm tra certificate

Có thể dùng openssl để xem certificate và SAN:

    openssl s_client -connect kafka-1.example.internal:9093 -servername kafka-1.example.internal -showcerts

Lệnh này giúp kiểm tra TLS handshake và chain ở mức TLS. Nó không xác minh SASL authentication hoặc Kafka ACL. Khi kiểm tra bằng openssl, dùng hostname thực tế để SNI và hostname verification có ý nghĩa.

## 15. Quản lý credential và secret

Không ghi password, token, private key password hoặc JAAS string có credential thật vào Git. Cấu hình nên tham chiếu secret từ môi trường triển khai:

    sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'

Các nguồn secret có thể là Kubernetes Secret, Vault, cloud secret manager hoặc Spring Boot config tree. Bảo đảm secret được inject vào đúng process và không xuất hiện trong log, actuator endpoint, diagnostic dump hoặc error message.

Một số nguyên tắc:

- Dùng principal riêng cho từng service/environment.
- Không dùng tài khoản superuser cho runtime application.
- Hạn chế quyền đọc secret và private key.
- Rotate password/token/certificate theo lịch.
- Có quy trình cập nhật credential không làm gián đoạn mọi replica cùng lúc.
- Che giá trị nhạy cảm trong log và cấu hình hiển thị.
- Không truyền password qua command line nếu có thể bị liệt kê trong process list hoặc shell history.
- Kiểm tra YAML/JAAS escaping khi password chứa dấu nháy, dấu gạch chéo hoặc ký tự đặc biệt.

Khi rotate certificate, có thể cần giai đoạn overlap: broker/client trust cả CA hoặc certificate cũ và mới trong thời gian chuyển đổi. Thứ tự triển khai phải bảo đảm client mới tin broker mới trước khi broker chuyển certificate, và client certificate mới được broker trust trước khi client dùng nó.

## 16. SASL authentication không thay thế ACL

Sau khi client xác thực, Kafka tạo principal. Authorizer kiểm tra principal đó có quyền trên tài nguyên hay không.

Ví dụ quyền thường cần:

| Client role | Resource | Quyền cần xem xét |
|---|---|---|
| Producer | Output topic | Write, Describe |
| Consumer | Input topic | Read, Describe |
| Consumer | Consumer group | Read |
| Kafka Streams | Input/output topics | Read/Write |
| Kafka Streams | Application group | Read và các quyền group cần thiết |
| Kafka Streams | Changelog/repartition topics | Read/Write/Describe, đôi khi Create |
| AdminClient | Topic/cluster | Describe hoặc Create/Alter nếu ứng dụng được phép quản trị |
| Transactional producer | Transactional ID | Quyền transaction phù hợp |

Kafka CLI có convenience ACL cho producer và consumer, nhưng Kafka Streams topology có thêm internal topics, group và đôi khi transactional IDs. Cần kiểm tra quyền thực tế theo topology và tính năng bật.

Trong môi trường bảo mật, thường provision topic, partition, ACL và internal topic policy bằng quy trình quản trị. Nếu tắt autoCreateTopics/autoAddPartitions, đội vận hành cần tạo trước các destination cần thiết. Tài khoản runtime có thể chỉ có quyền produce/consume chứ không có quyền tạo topic.

Không dùng allow.everyone.if.no.acl.found=true trong production như cách sửa nhanh authorization error. Cấu hình đó có thể mở tài nguyên chưa có ACL cho mọi principal.

## 17. Kiểm thử kết nối bảo mật

Kiểm thử cần tách các lớp để biết lỗi nằm ở đâu.

| Test | Điều cần chứng minh | Cách thực hiện |
|---|---|---|
| TLS handshake | Client tin certificate chain và hostname broker | openssl hoặc Kafka client với truststore |
| SASL authentication | Credential/mechanism đúng | Kafka CLI hoặc application client |
| Authorization | Principal có đúng ACL | Thử read/write đúng topic/group |
| Binder startup | Tất cả client của binder dùng security config | Khởi động Spring context và kiểm tra binder logs |
| Produce/consume | Luồng message thực sự hoạt động | Gửi và đọc message qua binding |
| Kafka Streams | Input/output/internal topics được phép | Khởi động topology, tạo state và kiểm tra changelog |
| Negative test | Sai credential/CA/ACL bị từ chối | Dùng credential hoặc truststore sai trong môi trường test |

### Kiểm tra bằng Kafka CLI

Tạo file client.properties chứa cấu hình client bảo mật:

    security.protocol=SASL_SSL
    sasl.mechanism=SCRAM-SHA-512
    sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="stream-service" password="secret-from-test-secret";
    ssl.truststore.location=/etc/kafka/client.truststore.p12
    ssl.truststore.password=<test-truststore-password>
    ssl.truststore.type=PKCS12
    ssl.endpoint.identification.algorithm=https

Dùng file này với công cụ Kafka:

    bin/kafka-broker-api-versions.sh --bootstrap-server kafka-1.example.internal:9093 --command-config client.properties
    bin/kafka-topics.sh --bootstrap-server kafka-1.example.internal:9093 --command-config client.properties --list

Các lệnh xác minh kết nối Kafka và quyền tương ứng với request. Quyền list/describe cluster hoặc topic có thể cần ACL riêng. Không đặt password thật trong lệnh shell; chỉ dùng file bảo mật có quyền đọc giới hạn và xóa file test khi không còn cần thiết.

### Integration test với Spring Cloud Stream

Dùng broker test được cấu hình TLS/SASL tương đương production. Test binder trong bộ nhớ không thực hiện TLS handshake và không xác minh SASL/ACL, vì vậy không thể thay thế broker integration test.

Test nên xác minh:

1. Spring context khởi động với đúng security properties.
2. AdminClient lấy metadata hoặc kiểm tra topic thành công.
3. Producer gửi message qua output binding.
4. Consumer nhận message qua input binding.
5. Principal bị từ chối khi dùng sai password.
6. Client bị từ chối khi truststore không tin CA.
7. Hostname mismatch bị phát hiện.
8. Principal hợp lệ nhưng thiếu ACL bị authorization error.
9. Kafka Streams binder tạo/đọc/ghi internal topics đúng quyền.
10. Certificate/password rotation không làm gián đoạn ngoài kế hoạch.

Kiểm thử negative cases trong cluster riêng; không thử sai credential liên tục trên production vì có thể kích hoạt rate limit, alert hoặc lockout ở authentication backend.

## 18. Chẩn đoán lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SSLHandshakeException: PKIX path building failed | Truststore thiếu CA/intermediate hoặc certificate chain không đầy đủ | Cập nhật truststore và kiểm tra chain |
| No subject alternative names matching | Hostname client dùng không có trong SAN certificate | Sửa SAN, DNS hoặc advertised.listeners |
| Received fatal alert: bad_certificate | Client certificate không được broker trust hoặc key/chain sai | Kiểm tra keystore và broker truststore |
| SaslAuthenticationException | Username/password sai, JAAS sai hoặc principal chưa được provision | Kiểm tra mechanism, JAAS và credential broker |
| UnsupportedSaslMechanismException | Client chọn mechanism broker chưa bật | Đồng bộ sasl.mechanism và sasl.enabled.mechanisms |
| TopicAuthorizationException | Principal thiếu quyền trên topic | Cấp ACL đúng resource/operation |
| GroupAuthorizationException | Consumer thiếu quyền trên group | Cấp ACL Read cho consumer group |
| ClusterAuthorizationException | AdminClient thiếu quyền cluster-level | Xác định binder có đang tạo/describe topic không; cấp quyền tối thiểu |
| Timeout sau khi bootstrap thành công | advertised.listeners, DNS hoặc firewall sai | Kiểm tra mọi broker endpoint trong metadata |
| SSL keystore password incorrect | Store password hoặc key password sai | Phân biệt ssl.keystore.password và ssl.key.password |
| Client không tìm thấy truststore | Đường dẫn trong container không tồn tại hoặc mount sai | Kiểm tra secret volume và file permission |
| SASL config không có hiệu lực | Property đặt sai namespace hoặc JAAS file ghi đè | Kiểm tra binder config và JAAS precedence |
| Kafka Streams không khởi động | Thiếu ACL cho group/internal topics hoặc config ở sai binder | Kiểm tra applicationId, Streams binder namespace và ACL |
| Topic không được tạo | Runtime principal không có quyền Create | Provision topic bằng admin hoặc cấp quyền có kiểm soát |

### Phân biệt lỗi TLS, SASL và ACL

- Nếu TLS handshake thất bại, client chưa tới bước xác thực SASL.
- Nếu TLS thành công nhưng SASL thất bại, kiểm tra mechanism, credential và JAAS.
- Nếu SASL thành công nhưng request bị từ chối, kiểm tra ACL và principal.
- Nếu bootstrap thành công nhưng request tới broker khác timeout, kiểm tra advertised.listeners, DNS và certificate SAN của từng broker.

Đừng tắt hostname verification hoặc chuyển sang PLAINTEXT để che lỗi. Hãy sửa nguyên nhân ở certificate, DNS, credential hoặc ACL.

## 19. Checklist triển khai production

Trước khi phát hành một Spring Cloud Stream application kết nối Kafka bảo mật:

1. Chọn listener và security.protocol đúng: SSL hoặc SASL_SSL.
2. Xác nhận broker bật đúng SASL mechanism.
3. Cấp principal riêng cho service và environment.
4. Cấu hình truststore chứa CA tin cậy.
5. Xác minh certificate SAN khớp tất cả advertised broker hostnames.
6. Nếu dùng mTLS, cấp client certificate và cấu hình keystore/truststore hai phía.
7. Đặt security properties trong regular Kafka binder hoặc Kafka Streams binder đúng mô hình.
8. Đưa password, token và store password vào secret management.
9. Kiểm tra ACL cho topic, group, internal topics, cluster và transactional ID nếu cần.
10. Provision topic/partition/ACL bằng quy trình quản trị phù hợp.
11. Kiểm thử handshake, SASL, authorization, produce/consume và Streams topology.
12. Kiểm tra log không in secret hoặc JAAS string.
13. Có kế hoạch rotate certificate, password và token.
14. Theo dõi authentication failure, authorization failure, TLS handshake error và connection retry.
15. Ghi lại broker, Kafka client, Spring Boot và Spring Cloud Stream versions trong runbook.

## 20. Kết luận

TLS mã hóa dữ liệu trên đường truyền và giúp client xác minh broker qua certificate. SASL xác thực principal bằng PLAIN, SCRAM, Kerberos hoặc OAuth. mTLS bổ sung xác thực client bằng certificate. Kafka ACL quyết định principal đã xác thực được phép đọc, ghi hoặc quản trị tài nguyên nào.

Với regular Spring Cloud Stream Kafka binder, đặt Kafka client security properties dưới spring.cloud.stream.kafka.binder.configuration. Với Kafka Streams binder, dùng spring.cloud.stream.kafka.streams.binder.configuration. Cấu hình security.protocol, SASL mechanism/JAAS và ssl.* properties phải khớp listener và certificate của broker.

Trong production, ưu tiên SASL_SSL hoặc SSL theo mô hình identity; dùng TLS 1.2 trở lên, giữ hostname verification, quản lý CA/keystore/truststore và secret có kiểm soát. Không coi authentication là authorization: cấp ACL tối thiểu cho topic, consumer group, internal topics và transactional ID. Chỉ xem kết nối là hoàn tất khi integration test chứng minh TLS handshake, SASL authentication, ACL và luồng produce/consume thực tế.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream 5.0.4 — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html)
- [Apache Kafka 4.4 — Authentication using SASL](https://kafka.apache.org/44/security/authentication-using-sasl/)
- [Apache Kafka 4.4 — Encryption and Authentication using SSL](https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/)
- [Apache Kafka 4.4 — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)
- [Apache Kafka 4.4 — Security Model](https://kafka.apache.org/44/security/security-model/)

Khi triển khai, chọn reference guide đúng release của Spring Cloud Stream, Kafka client và broker đang dùng. Một property có trong Kafka client mới không bảo đảm binder hoặc broker cũ hỗ trợ cùng behavior.

