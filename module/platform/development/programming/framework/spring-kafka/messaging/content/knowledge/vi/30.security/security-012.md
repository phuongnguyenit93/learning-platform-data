# Luân chuyển chứng thư và credential

Ứng dụng Spring Kafka phải xác thực với Kafka broker trước khi producer gửi record hoặc consumer đọc dữ liệu. Tùy cơ chế bảo mật của cluster, client có thể dùng TLS một chiều, mutual TLS (mTLS), SASL/SCRAM, SASL/PLAIN hoặc SASL/OAUTHBEARER. Chứng thư và credential đều có thời hạn, có thể bị lộ hoặc cần thay theo chính sách bảo mật; vì vậy hệ thống phải có quy trình luân chuyển mà không làm gián đoạn luồng messaging ngoài mức chấp nhận.

Luân chuyển (rotation) là thay chứng thư, private key, password, token hoặc principal đang được client sử dụng bằng thông tin xác thực mới. Quy trình an toàn thường có giai đoạn chồng lấp: cấp và tin cậy thông tin mới, triển khai client dùng thông tin mới, xác nhận kết nối hoạt động rồi mới thu hồi thông tin cũ. Nếu thu hồi credential cũ trước khi toàn bộ client chuyển đổi, producer và consumer chưa được cập nhật có thể mất kết nối.

Bài học thuộc chương **Bảo mật** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Những gì cần luân chuyển trong kết nối Kafka

Một kết nối Kafka có thể sử dụng một hoặc nhiều lớp bảo mật:

| Thành phần | Dữ liệu cần quản lý | Mục đích |
| --- | --- | --- |
| Broker TLS certificate | Chứng thư và private key phía broker | Client xác minh broker là máy chủ đúng. |
| Client TLS certificate | Chứng thư và private key phía client | Broker xác minh danh tính client trong mTLS. |
| Truststore | CA certificate hoặc certificate chain được tin cậy | Xác minh chứng thư của peer. |
| Keystore | Private key và certificate chain của chính client/broker | Cung cấp danh tính TLS. |
| SASL credential | Username/password hoặc secret tương ứng | Xác thực client bằng SASL. |
| OAuth credential/token | Client secret, signing key hoặc access token | Cấp token cho SASL/OAUTHBEARER. |
| Kafka principal và ACL | Danh tính và quyền truy cập | Quyết định client được phép làm gì sau khi xác thực. |

Không phải cluster nào cũng sử dụng tất cả thành phần. Ví dụ cluster dùng SASL/SCRAM qua TLS cần truststore để xác minh broker và username/password để xác thực client; cluster dùng mTLS cần truststore cùng client keystore.

Cần phân biệt ba khái niệm:

- **Authentication:** client là ai?
- **Authorization:** client được phép đọc topic, ghi topic hoặc dùng consumer group nào?
- **Encryption:** dữ liệu trên đường truyền được bảo vệ như thế nào?

Luân chuyển credential thành công chưa chắc kết nối hoạt động nếu principal mới chưa được cấp ACL tương ứng.

## 2. TLS một chiều và mutual TLS

Trong TLS một chiều, client xác minh certificate của broker. Client cần truststore chứa CA hoặc certificate chain mà broker sử dụng.

Trong mutual TLS, broker cũng yêu cầu client cung cấp certificate. Hai phía xác minh danh tính của nhau:

~~~mermaid
flowchart TD
    A[Spring Kafka client] --> B[TLS handshake]
    B --> C[Client xác minh broker certificate]
    C --> D{Broker certificate hợp lệ?}
    D -->|Không| E[Handshake thất bại]
    D -->|Có| F[Client gửi certificate nếu broker yêu cầu mTLS]
    F --> G[Broker xác minh client certificate]
    G --> H{Client certificate hợp lệ?}
    H -->|Không| I[Authentication thất bại]
    H -->|Có| J[TLS channel được thiết lập]
    J --> K[Kafka authorization kiểm tra ACL]
~~~

Truststore thường chứa CA certificate dùng để xác minh peer. Keystore chứa private key và certificate chain của chính identity đang kết nối. Không nhầm truststore với keystore: truststore không cần giữ private key của client.

Nếu cluster dùng TLS một chiều, không cần cấu hình client keystore chỉ để xác minh broker. Nếu broker bật mTLS, client cần keystore phù hợp và broker cần trust CA cấp certificate client.

## 3. Cấu trúc certificate và trust chain

Một certificate X.509 thường được ký bởi CA. Client xác minh chuỗi từ certificate leaf của broker đến CA mà client tin cậy.

~~~text
Kafka broker certificate
        |
        v
Intermediate CA
        |
        v
Root CA
        |
        v
Client truststore
~~~

Khi kiểm tra certificate, cần quan tâm:

- Subject và Subject Alternative Name (SAN).
- Issuer và chuỗi CA.
- Not Before và Not After.
- Key usage và extended key usage.
- Thuật toán chữ ký và kích thước khóa.
- Hostname broker có khớp SAN hay không.

Kafka client kết nối tới hostname trong `bootstrap.servers` và các địa chỉ broker được quảng bá qua metadata. Certificate broker phải phù hợp với hostname mà client thực sự kết nối, không chỉ hostname bootstrap ban đầu.

Nếu broker certificate được cấp lại với SAN sai hoặc thiếu intermediate certificate, TLS handshake có thể thất bại dù certificate chưa hết hạn và CA đã được tin cậy.

Có thể kiểm tra certificate PEM:

~~~bash
openssl x509 -in broker.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

Với keystore PKCS12:

~~~bash
keytool -list -v -keystore client-keystore.p12 -storetype PKCS12
~~~

Các lệnh trên chỉ đọc thông tin certificate/keystore. Không đưa private key hoặc password vào command line hay log terminal.

## 4. Keystore, truststore và định dạng lưu trữ

Kafka client hỗ trợ cấu hình SSL bằng các định dạng lưu trữ phù hợp với Kafka client/JVM, phổ biến là JKS và PKCS12. PEM cũng có thể được dùng tùy cấu hình và phiên bản Kafka client.

| Thành phần | Nội dung | Ví dụ |
| --- | --- | --- |
| Client keystore | Private key và certificate chain của client | `client-keystore.p12` |
| Client truststore | CA dùng để xác minh broker | `kafka-truststore.p12` |
| Broker keystore | Private key và certificate chain của broker | `broker-keystore.p12` |
| Broker truststore | CA dùng để xác minh client certificate trong mTLS | `client-ca-truststore.p12` |

Password bảo vệ keystore/truststore cũng là credential cần luân chuyển. Thay password file nhưng quên cập nhật secret trong ứng dụng sẽ khiến client không mở được store.

Private key cần được bảo vệ chặt hơn public certificate. Không commit private key, keystore password hoặc SASL password vào Git, Docker image, log hay tài liệu hướng dẫn. Quyền đọc secret nên giới hạn theo service identity và môi trường.

## 5. Cấu hình TLS trong Spring Boot

Spring Boot cung cấp nhóm thuộc tính `spring.kafka.ssl.*` để cấu hình SSL cho Kafka client. Tên thuộc tính cụ thể có thể thay đổi theo phiên bản Spring Boot; hãy kiểm tra configuration metadata của phiên bản đang dùng.

Ví dụ client xác minh broker bằng truststore:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    properties:
      security.protocol: SSL
    ssl:
      trust-store-location: file:/etc/kafka/tls/client-truststore.p12
      trust-store-password: <injected-truststore-password>
      trust-store-type: PKCS12
~~~

Ví dụ mTLS bổ sung client keystore:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    properties:
      security.protocol: SSL
    ssl:
      trust-store-location: file:/etc/kafka/tls/client-truststore.p12
      trust-store-password: <injected-truststore-password>
      trust-store-type: PKCS12
      key-store-location: file:/etc/kafka/tls/client-keystore.p12
      key-store-password: <injected-keystore-password>
      key-password: <injected-private-key-password>
      key-store-type: PKCS12
~~~

Đường dẫn file ở đây là mount point trong runtime. Password là placeholder để minh họa secret được inject từ secret manager hoặc secret volume; không ghi giá trị thật vào file cấu hình được commit.

Nếu dự án cấu hình trực tiếp Kafka client properties, các thuộc tính tương ứng thường là `ssl.truststore.location`, `ssl.truststore.password`, `ssl.keystore.location`, `ssl.keystore.password`, `ssl.key.password` và `ssl.keystore.type`.

## 6. Cấu hình SASL/SCRAM

SASL/SCRAM xác thực client bằng username/password thông qua challenge-response. TLS vẫn nên được bật để mã hóa toàn bộ kết nối và bảo vệ dữ liệu, metadata cùng thông tin xác thực trên đường truyền.

Ví dụ SCRAM-SHA-512 qua TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="order-service-v2"
        password="<injected-scram-password>";
    ssl:
      trust-store-location: file:/etc/kafka/tls/client-truststore.p12
      trust-store-password: <injected-truststore-password>
      trust-store-type: PKCS12
~~~

Client cần đồng thời:

- `security.protocol: SASL_SSL` để dùng SASL bên trong TLS.
- `sasl.mechanism: SCRAM-SHA-512` để chọn cơ chế xác thực.
- `sasl.jaas.config` để cung cấp login module và credential.
- Truststore để xác minh broker certificate.

Username là principal dùng cho authorization; password là secret xác thực. Khi đổi username sang principal mới, cần cấp ACL cho principal mới trước khi deploy client.

Không dùng SASL/PLAIN hoặc SCRAM qua kết nối `PLAINTEXT` trong môi trường không tin cậy. SCRAM không thay thế TLS vì TLS còn bảo vệ toàn bộ dữ liệu và chống giả mạo broker.

## 7. SASL/PLAIN và OAuth credential

SASL/PLAIN dùng username/password và thường được cấu hình qua `PlainLoginModule`:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: PLAIN
      sasl.jaas.config: >-
        org.apache.kafka.common.security.plain.PlainLoginModule required
        username="order-service"
        password="<injected-password>";
~~~

SASL/PLAIN chỉ nên dùng qua TLS vì cơ chế này không tự cung cấp bảo vệ mã hóa cho password trên đường truyền.

Với SASL/OAUTHBEARER, client dùng token thay vì password tĩnh. Cần quản lý:

- Client ID và client secret nếu identity provider yêu cầu.
- Thời hạn access token.
- Cơ chế lấy token mới trước khi token hết hạn.
- Signing key/JWKS và trust với identity provider.
- Clock synchronization và sai lệch thời gian.
- Phản hồi khi token bị thu hồi hoặc identity provider không khả dụng.

Token ngắn hạn giảm thời gian credential bị lạm dụng nếu bị lộ, nhưng ứng dụng phải có callback/login handler hoặc cơ chế OAuth tương ứng với Kafka client version. Không hard-code token dài hạn trong `sasl.jaas.config`.

## 8. Authentication thành công chưa đủ: principal và ACL

Sau khi xác thực, broker xác định principal rồi áp dụng authorization policy. Trong Kafka ACL, principal có thể đến từ SASL username hoặc TLS certificate identity, tùy cơ chế và cấu hình principal mapping của broker.

Một consumer service thường cần quyền:

| Hoạt động | Quyền thường cần |
| --- | --- |
| Producer ghi event vào topic | WRITE trên topic |
| Consumer đọc event | READ trên topic |
| Consumer tham gia group | READ trên consumer group |
| Transactional producer | Quyền phù hợp trên transactional ID và topic |
| Idempotent producer | Quyền IdempotentWrite trên cluster khi ACL authorizer yêu cầu |

Khi luân chuyển từ principal cũ sang principal mới, phải sao chép đúng quyền cần thiết cho workload. Không cấp wildcard hoặc quyền admin chỉ để làm kết nối mới hoạt động.

Với mTLS, certificate subject có thể được ánh xạ thành Kafka principal qua cấu hình broker. Nếu certificate mới có subject khác, principal có thể thay đổi và ACL cũ không còn khớp. Kiểm tra principal mapping trước khi triển khai certificate mới.

## 9. Luân chuyển client certificate trong mTLS

Giả sử client đang dùng certificate do CA cũ cấp và cần chuyển sang CA mới. Broker xác minh client certificate, vì vậy broker truststore phải tin cậy CA mới trước khi client đổi certificate.

Trình tự an toàn:

1. Cấp client certificate mới và private key mới.
2. Thêm CA mới vào truststore của broker trong khi vẫn giữ CA cũ.
3. Xác nhận broker đã nạp truststore mới theo cơ chế reload/rolling restart của môi trường.
4. Cấp certificate mới cho một client canary.
5. Khởi động lại hoặc tạo lại Kafka client dùng certificate mới.
6. Xác nhận TLS handshake, principal, ACL và produce/consume.
7. Rollout certificate mới tới toàn bộ instance.
8. Theo dõi kết nối và xác nhận không còn client dùng certificate cũ.
9. Thu hồi certificate cũ và bỏ CA cũ khỏi truststore broker sau thời gian overlap.

Không xóa CA cũ trước khi toàn bộ client đã chuyển. Nếu broker không hỗ trợ reload truststore theo cách triển khai hiện tại, cần rolling restart có kiểm soát.

## 10. Luân chuyển broker certificate

Khi broker certificate sắp hết hạn hoặc cần đổi CA, client là bên xác minh certificate broker. Do đó, client truststore cần tin cậy CA mới trước khi broker chuyển certificate.

Trình tự:

1. Phát hành broker certificate mới với SAN khớp hostname advertised listener.
2. Cập nhật client truststore để tin cả CA cũ và CA mới.
3. Phân phối truststore mới tới tất cả ứng dụng và xác nhận client đã dùng.
4. Thay broker certificate theo rolling procedure của Kafka cluster.
5. Kiểm tra kết nối tới từng broker, kể cả broker được quảng bá qua metadata.
6. Xác nhận producer/consumer hoạt động qua toàn bộ broker.
7. Sau thời gian overlap, loại CA cũ khỏi client truststore nếu không còn certificate nào phụ thuộc.
8. Thu hồi certificate cũ theo chính sách CA.

Nếu certificate mới vẫn do cùng CA cũ cấp, có thể không cần thay trust anchor; tuy nhiên vẫn cần kiểm tra SAN, chain, validity và reload broker certificate. Không giả định thay file keystore trên disk sẽ tự động khiến broker hoặc client đang chạy nạp certificate mới.

## 11. Luân chuyển SASL/SCRAM credential

Với SASL/SCRAM, username xác định principal và password chứng minh client sở hữu credential của principal đó. Một cách chuyển đổi có thời gian overlap là tạo principal mới, cấp đúng ACL rồi chuyển từng ứng dụng sang username/password mới.

Quy trình khuyến nghị:

1. Tạo principal mới, ví dụ `order-service-v2`.
2. Tạo SCRAM credential mới trong Kafka cluster hoặc hệ thống quản lý identity tương ứng.
3. Sao chép đúng ACL cần thiết từ principal cũ sang principal mới.
4. Lưu password mới trong secret manager.
5. Cập nhật một instance canary dùng principal mới.
6. Xác minh authentication, authorization, produce, consume và consumer group.
7. Rollout các instance còn lại.
8. Xác nhận không còn client sử dụng principal cũ.
9. Thu hồi credential và ACL cũ theo kế hoạch.

Tạo principal mới giúp hai credential cùng hợp lệ trong giai đoạn chuyển đổi. Nếu thay password trực tiếp trên cùng principal, client chưa cập nhật có thể thất bại khi reconnect hoặc reauthenticate; khả năng overlap phụ thuộc broker và cơ chế SASL được cấu hình.

Không xóa principal cũ ngay sau khi canary kết nối thành công. Hãy xác nhận tất cả replica, batch job, connector, scheduled task và ứng dụng phụ thuộc đã chuyển.

## 12. Cấp ACL cho principal mới

Authentication chỉ xác nhận danh tính; authorization vẫn phải được cấu hình riêng. Khi tạo principal mới, hãy xác định workload cần những quyền nào.

Ví dụ consumer đọc topic `order-events` trong group `order-service` thường cần READ trên topic và READ trên group. Producer gửi vào topic thường cần WRITE trên topic. Workload transactional hoặc idempotent có thể cần thêm quyền tương ứng với transactional ID hoặc cluster theo authorizer đang sử dụng.

Quy trình migration ACL:

- Export hoặc ghi nhận ACL của principal cũ.
- Xác định quyền tối thiểu thực sự được workload sử dụng.
- Cấp quyền tương đương cho principal mới.
- Test bằng đúng client config và topic/group production-like.
- Theo dõi lỗi authorization trong giai đoạn canary.
- Sau khi chuyển hết client, thu hồi ACL principal cũ.

Không copy wildcard hoặc quyền admin một cách máy móc. Luân chuyển credential là dịp kiểm tra least privilege, nhưng không nên đồng thời thay đổi quyền ngoài phạm vi cần thiết nếu chưa có kiểm thử.

Nếu dùng mTLS, ACL gắn với Kafka principal được tạo từ certificate identity. Certificate mới có thể làm principal thay đổi nếu subject hoặc principal mapping thay đổi. Hãy kiểm tra identity mà broker thực sự nhìn thấy trước khi rollout.

## 13. Luân chuyển SASL/PLAIN password

SASL/PLAIN dùng password tĩnh nên cần quy trình đổi secret có overlap. Nếu broker hỗ trợ nhiều identity, cách an toàn thường là tạo username mới thay vì đổi password của username đang được tất cả client dùng.

Nếu buộc phải đổi password trên cùng principal:

1. Xác định hành vi cập nhật credential của broker và thời điểm credential mới có hiệu lực.
2. Chuẩn bị rollout client config mới trước khi thu hồi password cũ nếu nền tảng hỗ trợ overlap.
3. Xác định các kết nối hiện tại có thể bị ảnh hưởng khi reconnect/reauthentication.
4. Thực hiện canary và theo dõi authentication failure.
5. Rollout toàn bộ client và xác nhận không còn kết nối dùng password cũ.
6. Thu hồi password cũ theo cơ chế của identity provider/broker.

Không giả định connection đang mở sẽ giữ quyền truy cập mãi sau khi password bị đổi. Broker có thể yêu cầu reauthentication hoặc kết nối có thể bị đóng vì nhiều nguyên nhân khác nhau. Thiết kế phải chịu được việc client tạo connection mới bằng credential hiện hành.

SASL/PLAIN phải chạy qua TLS. Nếu password bị lộ, ưu tiên thu hồi khẩn cấp theo incident procedure thay vì kéo dài overlap không an toàn.

## 14. Luân chuyển OAuth client secret và token

Với OAuth, cần phân biệt client secret và access token:

- Client secret dùng để client xác thực với identity provider.
- Access token là credential ngắn hạn được gửi trong quá trình SASL/OAUTHBEARER.
- Signing key/JWKS xác minh chữ ký token.
- Token expiry xác định thời điểm client phải lấy token mới.

Quy trình đổi client secret tùy identity provider. Nếu provider hỗ trợ hai secret hoạt động đồng thời, tạo secret mới, cập nhật một client canary, xác minh token mới rồi rollout toàn bộ client trước khi revoke secret cũ. Nếu provider không hỗ trợ overlap, cần lên lịch đổi đồng bộ hoặc tạo client registration mới.

Ứng dụng phải lấy token mới trước khi token hiện tại hết hạn và xử lý lỗi cấp token, clock skew, identity provider timeout và token bị thu hồi. Không lưu access token lâu dài trong YAML hoặc log.

Nếu signing key của identity provider thay đổi, các bên xác minh token cần nhận được JWKS/key mới trước khi token mới được phát hành rộng rãi. Giữ overlap key cũ và mới trong khoảng thời gian phù hợp với lifetime token đang lưu hành.

## 15. Phân phối secret trong Spring Boot và môi trường triển khai

Ứng dụng không nên chứa credential thật trong `application.yml` được commit. Thay vào đó, inject secret lúc runtime từ một nguồn được quản lý:

- Kubernetes Secret được mount thành file hoặc cung cấp qua environment.
- HashiCorp Vault hoặc secret manager của cloud provider.
- Secret store tích hợp trong nền tảng triển khai.
- PKI nội bộ cấp và gia hạn certificate tự động.

Ví dụ YAML chỉ giữ đường dẫn và tên biến:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="order-service"
        password="<runtime-injected-secret>";
~~~

Placeholder phải được thay bằng secret do môi trường cung cấp. Không ghi password thật vào source, Docker build argument, image layer, shell history hoặc log cấu hình.

Environment variable tiện cho cấu hình lúc process khởi động nhưng có thể khó xoay vòng trong process đang chạy. Secret volume có thể được nền tảng cập nhật file, nhưng Kafka client không mặc nhiên tự đọc lại keystore hoặc JAAS config khi file thay đổi.

## 16. Khi nào Kafka client phải được tạo lại?

Kafka client đọc cấu hình khi client/producer/consumer được tạo. Việc thay file secret trên disk không đảm bảo các connection hiện tại dùng certificate hoặc credential mới.

Với Spring Kafka:

- `ProducerFactory` có thể quản lý và cache producer instance.
- Listener container quản lý consumer instance trong suốt lifecycle.
- `KafkaTemplate` sử dụng producer do ProducerFactory cung cấp.
- Cập nhật property source không tự động bảo đảm producer/consumer hiện tại reload credential.

Cách vận hành đơn giản và dễ kiểm chứng nhất là rollout/restart ứng dụng theo từng batch sau khi secret mới đã được mount. Với yêu cầu reload không restart, cần thiết kế rõ việc đóng/recreate producer, consumer và listener container theo API của phiên bản Spring Kafka; kiểm thử transaction, in-flight send, consumer assignment và offset trước khi dùng production.

Không chỉ thay keystore file rồi giả định TLS session đã dùng certificate mới. Theo dõi certificate fingerprint hoặc serial number từ client/broker telemetry nếu môi trường có hỗ trợ.

## 17. Rolling rotation không gián đoạn

Để tránh gián đoạn, cần có giai đoạn mà cả credential cũ và mới đều được chấp nhận. Một rollout có thể chia thành các bước:

~~~mermaid
flowchart TD
    A[Kiểm kê client và credential cũ] --> B[Cấp certificate/credential mới]
    B --> C[Thêm trust hoặc ACL mới]
    C --> D[Deploy canary dùng credential mới]
    D --> E{Kết nối và quyền hoạt động?}
    E -->|Không| F[Rollback canary, giữ credential cũ]
    E -->|Có| G[Rolling deploy các client còn lại]
    G --> H[Xác nhận không còn client cũ]
    H --> I[Revoke credential cũ]
    I --> J[Loại trust anchor cũ sau overlap]
~~~

Một số lưu ý:

- Cấp quyền và trust mới trước khi chuyển client.
- Chỉ thu hồi credential cũ sau khi kiểm kê toàn bộ client.
- Roll từng nhóm nhỏ và chờ health check.
- Theo dõi cả producer và consumer, không chỉ một loại client.
- Giữ khả năng rollback trong giai đoạn overlap.
- Broker-side change cần rolling procedure riêng để không làm mất quorum hoặc availability.

Không thể cam kết zero downtime chỉ bằng cách dùng rolling deployment. Kết quả còn phụ thuộc số replica, partition assignment, broker availability, consumer lag, thời gian reconnect và cách hệ thống xử lý in-flight request.

## 18. Certificate renewal cùng CA và đổi CA khác nhau thế nào?

Hai tình huống có quy trình khác nhau:

| Tình huống | Thay đổi | Việc cần làm |
| --- | --- | --- |
| Renew certificate do cùng CA cấp | Leaf certificate/private key hoặc validity thay đổi | Xác minh subject/SAN, chain, key usage và cập nhật keystore; truststore thường vẫn tin CA hiện tại. |
| Chuyển sang CA mới | Trust anchor thay đổi | Thêm CA mới vào truststore trước, chuyển certificate, sau đó mới loại CA cũ. |
| Đổi subject/principal | Identity Kafka có thể thay đổi | Cập nhật principal mapping/ACL trước khi client dùng certificate mới. |
| Đổi hostname broker | Endpoint thay đổi | SAN phải khớp hostname mới và client phải kết nối được endpoint được quảng bá. |

Ngay cả khi cùng CA, private key mới vẫn cần được bảo vệ và cấp phát đúng. Không tái sử dụng private key cũ chỉ để tránh cập nhật cấu hình nếu chính sách PKI yêu cầu key mới.

Nếu đổi CA, truststore có thể tạm thời chứa cả CA cũ và mới. Chỉ loại CA cũ sau khi xác nhận không còn broker/client certificate hợp lệ nào dựa vào CA đó.

## 19. Kiểm tra certificate và credential trước rollout

Trước khi triển khai, kiểm tra metadata và tính hợp lệ:

~~~bash
openssl x509 -in client.crt -noout -subject -issuer -dates -ext subjectAltName
openssl verify -CAfile ca-chain.pem client.crt
keytool -list -v -keystore client-keystore.p12 -storetype PKCS12
~~~

Đối với mTLS, kiểm tra thêm certificate có mục đích client authentication trong extended key usage và private key có khớp certificate. Với broker certificate, xác nhận SAN chứa hostname broker mà Kafka client sẽ kết nối.

Kiểm thử kết nối bằng một client cấu hình giống Spring Kafka:

- Đúng `security.protocol`.
- Đúng SASL mechanism hoặc TLS keystore/truststore.
- Đúng principal và ACL.
- Đúng broker endpoint và DNS.
- Đúng topic, group và transactional ID nếu dùng transaction.

Một lệnh kiểm tra TLS thành công không chứng minh ACL Kafka đúng. Cần test produce/consume với principal mới để xác nhận cả authentication lẫn authorization.

## 20. Theo dõi thời hạn và lỗi xác thực

Rotation phải bắt đầu trước ngày hết hạn, không đợi đến khi client bị từ chối kết nối. Theo dõi:

- Certificate Not After và số ngày còn lại.
- Certificate serial number/fingerprint đang được dùng.
- Truststore/keystore version được deploy.
- SASL authentication failure theo principal.
- TLS handshake failure, hostname verification failure và certificate expired.
- Authorization failure theo topic/group/transactional ID.
- OAuth token refresh failure và token expiry.
- Producer reconnect, consumer disconnect và rebalance.
- Consumer lag và tỷ lệ send failure trong thời gian rollout.

Có thể đặt ngưỡng cảnh báo theo chính sách tổ chức, ví dụ 30 ngày, 14 ngày và 7 ngày trước khi hết hạn. Cần tính thời gian cấp certificate, phê duyệt, rollout và khả năng rollback vào ngưỡng cảnh báo.

Không log password, token, private key hoặc toàn bộ JAAS config. Log principal, error class, endpoint, certificate fingerprint đã được phép công khai và correlation ID là đủ cho nhiều tình huống điều tra.

## 21. Rollback và xử lý credential bị lộ

Trong rotation định kỳ, giữ credential cũ còn hiệu lực trong thời gian rollback đã xác định. Nếu canary dùng credential mới thất bại, có thể quay lại config cũ trong khi điều tra trust, ACL, certificate chain hoặc secret injection.

Khi credential bị lộ, ưu tiên containment:

1. Xác định principal, certificate hoặc secret bị ảnh hưởng.
2. Kiểm tra log truy cập và phạm vi quyền của identity.
3. Tạo identity/credential thay thế và cấp quyền tối thiểu cần thiết.
4. Chuyển workload hợp lệ sang credential mới.
5. Thu hồi credential bị lộ theo mức độ khẩn cấp.
6. Xác nhận kết nối trái phép không còn hoạt động.
7. Kiểm tra các secret khác có thể bị lộ cùng nguồn.
8. Ghi nhận nguyên nhân và cập nhật quy trình rotation.

Trong sự cố rò rỉ, không kéo dài overlap chỉ để tiện rollback nếu điều đó giữ credential bị lộ còn hoạt động. Cần phối hợp giữa security incident response và vận hành Kafka.

Certificate revocation qua CRL/OCSP phụ thuộc CA, broker, JVM và cấu hình TLS của môi trường. Không giả định mọi Kafka deployment tự động kiểm tra revocation; phải xác nhận cơ chế thực tế và có quy trình thu hồi phù hợp.

## 22. Checklist luân chuyển chứng thư và credential

Trước khi hoàn tất một đợt rotation, xác nhận:

1. Đã kiểm kê mọi producer, consumer, Kafka Streams app, connector và job dùng identity cũ.
2. Đã xác định loại bảo mật: TLS, mTLS, SASL/SCRAM, PLAIN hay OAUTHBEARER.
3. Certificate mới có chain, SAN, validity và key usage hợp lệ.
4. Truststore tin CA mới trước khi peer chuyển certificate.
5. Keystore chứa đúng private key và certificate chain.
6. Password keystore/truststore được inject từ secret manager.
7. Principal mới đã được cấp ACL tối thiểu cần thiết.
8. Certificate subject/principal mapping không làm mất quyền ngoài dự kiến.
9. Canary produce/consume thành công bằng credential mới.
10. Mọi instance đã được rollout và dùng secret version mới.
11. Kafka clients đã được recreate/restart khi cần để nạp cấu hình mới.
12. Không còn kết nối hoặc workload phụ thuộc credential cũ.
13. Metrics authentication, authorization, TLS và consumer lag ổn định.
14. Credential cũ được revoke và CA cũ được loại bỏ đúng thời điểm.
15. Có bằng chứng audit, owner, thời điểm rotation và kế hoạch lần tiếp theo.

Luân chuyển chứng thư và credential cần có giai đoạn overlap, xác minh principal/ACL và rollout client có kiểm soát. Với mTLS, phải phân biệt truststore xác minh peer với keystore giữ private key của chính client; với SASL, phải thay credential và bảo toàn quyền truy cập của principal. Spring Kafka không tự động reload mọi secret hoặc certificate khi file thay đổi, vì vậy cần chủ động recreate client hoặc rolling restart, theo dõi handshake/authentication và chỉ thu hồi thông tin cũ sau khi toàn bộ workload đã chuyển đổi.

