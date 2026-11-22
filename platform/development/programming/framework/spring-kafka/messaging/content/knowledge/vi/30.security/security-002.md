# SASL và cơ chế xác thực

Kafka cần biết client nào đang kết nối trước khi cho phép client sử dụng cluster. **SASL (Simple Authentication and Security Layer)** là cơ chế để client chứng minh danh tính với broker thông qua một authentication mechanism như PLAIN, SCRAM, GSSAPI hoặc OAUTHBEARER. Trong Spring Kafka, các thiết lập SASL được truyền tới Kafka client thông qua cấu hình Spring Boot hoặc các factory tự cấu hình.

SASL giải quyết câu hỏi **“client là ai?”**. Sau khi xác thực, broker còn phải kiểm tra **“client được phép làm gì?”** bằng authorization, thường thông qua ACL. Hai bước này độc lập: đăng nhập thành công không đồng nghĩa client được phép đọc mọi topic, ghi mọi topic hoặc tham gia mọi consumer group.

Bài học thuộc chương **Bảo mật** của module **SPRING_KAFKA_MESSAGING**, tập trung vào các cơ chế SASL, cách kết hợp SASL với TLS và cách cấu hình xác thực cho producer, consumer cùng Kafka Admin client trong Spring Kafka.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vai trò của SASL trong quá trình kết nối Kafka.
- Phân biệt authentication và authorization.
- Nhận biết các cơ chế PLAIN, SCRAM, GSSAPI và OAUTHBEARER.
- Phân biệt SASL_SSL với SASL_PLAINTEXT.
- Cấu hình SASL mechanism và JAAS login config trong Spring Boot.
- Cấu hình TLS truststore để xác minh broker.
- Áp dụng cấu hình chung hoặc credential riêng cho producer, consumer và AdminClient.
- Quản lý credential bằng secret store và lên kế hoạch rotation.
- Phân biệt lỗi xác thực, lỗi TLS và lỗi ACL.
- Kiểm thử kết nối và quyền truy cập với tài khoản có phạm vi tối thiểu.

## 1. SASL nằm ở đâu trong kết nối Kafka?

Khi một producer hoặc consumer kết nối broker, Kafka client thiết lập kết nối mạng, thương lượng giao thức bảo mật và xác thực danh tính trước khi thực hiện các thao tác Kafka cần quyền truy cập.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant Client as Spring Kafka client
    participant Broker as Kafka broker
    Client->>Broker: Open network connection
    opt SASL_SSL
        Client->>Broker: TLS handshake and verify broker certificate
        Broker-->>Client: TLS session established
    end
    Client->>Broker: SASL handshake (mechanism)
    Client->>Broker: SASL authentication exchange
    Broker-->>Client: Authentication result
    Client->>Broker: Kafka API request
    Broker->>Broker: Authorize principal against ACL
    Broker-->>Client: API response or authorization error
~~~

SASL không thay thế Kafka protocol. Nó là lớp xác thực được dùng trong quá trình thiết lập kết nối. Sau khi xác thực, client tiếp tục gửi các request như Metadata, Produce, Fetch, OffsetCommit hoặc các API quản trị.

Với `SASL_SSL`, TLS bảo vệ kênh truyền trước khi SASL trao đổi thông tin xác thực. Với `SASL_PLAINTEXT`, SASL được dùng trên kết nối không mã hóa; thông tin trao đổi có thể bị nghe lén trên mạng không đáng tin.

## 2. Authentication khác authorization

Hai khái niệm này thường bị nhầm lẫn:

| Khái niệm | Câu hỏi | Kafka xử lý bằng |
|---|---|---|
| Authentication | Client là ai? | SASL mechanism hoặc xác thực TLS client certificate. |
| Authorization | Client được phép làm gì? | ACL hoặc authorizer được broker cấu hình. |

Ví dụ:

- Producer đăng nhập thành công bằng user `orders-publisher`.
- Broker xác định principal tương ứng.
- ACL cho phép principal ghi vào topic `orders.created`.
- Nếu producer gửi tới `payments.private` mà không có quyền, broker từ chối dù authentication đã thành công.

Consumer thường cần quyền đọc topic và quyền sử dụng consumer group. Quyền cụ thể phụ thuộc API và cấu hình cluster, nhưng xác thực thành công không tự cấp quyền đọc/ghi.

Không dùng username/password của SASL như một cơ chế phân quyền trong code ứng dụng. Quyền truy cập phải được cấu hình và kiểm tra ở broker.

## 3. Các security protocol của Kafka

Kafka client có thuộc tính `security.protocol` để chọn lớp bảo vệ kết nối:

| Protocol | TLS mã hóa kết nối | SASL authentication | Mục đích |
|---|---:|---:|---|
| `PLAINTEXT` | Không | Không | Kết nối không bảo vệ, thường chỉ dùng trong môi trường local cô lập. |
| `SSL` | Có | Không | TLS, có thể kết hợp xác thực client bằng certificate. |
| `SASL_PLAINTEXT` | Không | Có | SASL trên kết nối không mã hóa. |
| `SASL_SSL` | Có | Có | SASL authentication bên trong kết nối TLS. |

Với cluster production đi qua mạng không hoàn toàn tin cậy, thông thường nên chọn `SASL_SSL`. `SASL_PLAINTEXT` không mã hóa traffic Kafka và không bảo vệ confidentiality của thông tin xác thực trên đường truyền.

TLS cũng giúp client xác minh certificate của broker để tránh kết nối nhầm endpoint. Không tắt hostname verification hoặc certificate validation chỉ để làm cho kết nối thử nghiệm chạy được.

## 4. SASL/PLAIN

PLAIN là cơ chế SASL đơn giản, dùng username và password để xác thực. Cấu hình client thường khai báo login module:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="orders-app" password="secret";
~~~

PLAIN không tự mã hóa username/password. Khi dùng qua `SASL_SSL`, TLS bảo vệ thông tin trên đường truyền. Nếu dùng `SASL_PLAINTEXT`, thông tin xác thực có nguy cơ bị lộ trên mạng.

PLAIN thường phù hợp khi nền tảng Kafka cung cấp user/password và đã cấu hình cơ chế SASL/PLAIN ở broker. Cách lưu trữ và kiểm tra credential phía broker phụ thuộc nền tảng triển khai.

Không ghi password thật vào source code, Git, Docker image hoặc log. Ví dụ trên chỉ minh họa cấu trúc JAAS; giá trị thực cần được cấp qua secret management.

## 5. SASL/SCRAM

SCRAM (Salted Challenge Response Authentication Mechanism) dùng quy trình challenge-response để xác thực mà không gửi password trực tiếp như PLAIN. Kafka hỗ trợ phổ biến:

- `SCRAM-SHA-256`
- `SCRAM-SHA-512`

Ví dụ:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="secret";
~~~

Broker cần được cấu hình hỗ trợ mechanism tương ứng và credential SCRAM của user phải được provision trước. Client và broker phải thống nhất mechanism; nếu client chọn SHA-512 nhưng listener chỉ hỗ trợ SHA-256, authentication sẽ thất bại.

SCRAM không thay thế TLS. Dùng `SASL_SSL` để mã hóa toàn bộ traffic, bảo vệ metadata và payload, đồng thời xác minh broker certificate.

## 6. SASL/GSSAPI với Kerberos

GSSAPI thường được dùng trong môi trường doanh nghiệp tích hợp Kerberos. Client xác thực bằng principal và Kerberos ticket, thường lấy ticket thông qua keytab hoặc cơ chế đăng nhập của môi trường.

Một JAAS login module có thể có dạng:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=kafka
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true keyTab="/run/secrets/orders.keytab" principal="orders-app@EXAMPLE.COM";
~~~

Cấu hình Kerberos còn phụ thuộc realm, KDC, DNS, clock synchronization, service principal của broker và file `krb5.conf`. Keytab là credential nhạy cảm, cần bảo vệ quyền đọc và rotation theo chính sách tổ chức.

GSSAPI thường phù hợp với hạ tầng đã có Kerberos. Không chọn cơ chế này chỉ vì nó có sẵn trong Kafka nếu hệ thống không vận hành KDC và principal tương ứng.

## 7. SASL/OAUTHBEARER

OAUTHBEARER cho phép client xác thực bằng OAuth bearer token. Client cần có cách lấy token, làm mới token và cung cấp token cho Kafka SASL callback handler.

Khác với PLAIN hoặc SCRAM dùng username/password tĩnh trong JAAS, OAuth thường phụ thuộc identity provider, issuer, audience, scope, expiry và callback handler tương thích với nền tảng Kafka.

Cấu hình có thể cần các thuộc tính như:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=OAUTHBEARER
sasl.login.callback.handler.class=com.example.kafka.OAuthLoginCallbackHandler
~~~

Tên callback handler và các thuộc tính bổ sung phụ thuộc thư viện hoặc nhà cung cấp Kafka. Không có một cấu hình callback handler chung phù hợp với mọi identity provider.

Không hardcode bearer token dài hạn trong file cấu hình. Token nên được cấp ngắn hạn và refresh qua callback handler hoặc integration được nhà cung cấp hỗ trợ. Khi triển khai OAuth, cần kiểm tra cả quá trình lấy token, refresh và xử lý khi token hết hạn.

## 8. Chọn mechanism nào?

| Cơ chế | Credential | Điểm cần lưu ý |
|---|---|---|
| PLAIN | Username/password | Dễ cấu hình; phải dùng TLS để bảo vệ trên đường truyền. |
| SCRAM-SHA-256/512 | Username/password + challenge-response | Broker phải provision SCRAM credential và hỗ trợ đúng hash mechanism. |
| GSSAPI | Kerberos principal/ticket | Cần KDC, service principal, keytab hoặc ticket cache. |
| OAUTHBEARER | OAuth access token | Cần identity provider và callback handler quản lý token. |

Lựa chọn phụ thuộc nền tảng Kafka, hệ thống định danh hiện có, quy trình cấp/thu hồi credential và yêu cầu bảo mật. Producer và consumer không bắt buộc phải dùng cùng một principal; có thể cấp danh tính riêng theo vai trò để giới hạn quyền.

Dù chọn mechanism nào, hãy xác minh broker listener đã bật cơ chế đó và client dùng đúng tên mechanism. Cấu hình ở Spring Boot không tự bật SASL trên broker.

## 9. Cấu hình SASL/SCRAM trong Spring Boot

Spring Boot chuyển các thuộc tính Kafka client qua `spring.kafka.properties`. Ví dụ dùng SCRAM-SHA-512 và TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093,kafka-2.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.truststore.type: PKCS12
~~~

Trong ví dụ:

- `security.protocol` chọn SASL kết hợp TLS.
- `sasl.mechanism` chọn SCRAM-SHA-512.
- `sasl.jaas.config` chỉ định login module và credential.
- `ssl.truststore.*` giúp JVM trust certificate chain của broker.

Các placeholder phải được cung cấp từ environment hoặc secret integration khi ứng dụng chạy. Không đưa giá trị thật vào file YAML được commit.

Nếu certificate broker được ký bởi CA đã có trong truststore mặc định của JVM, cấu hình truststore riêng có thể không cần thiết. Hãy dùng trust chain được tổ chức phê duyệt và không tắt kiểm tra certificate để né lỗi.

## 10. Cấu hình credential riêng cho producer và consumer

Nếu producer và consumer dùng hai principal khác nhau, có thể đặt thuộc tính riêng ở từng client thay vì dùng chung credential:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      security.protocol: SASL_SSL
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.truststore.type: PKCS12

    producer:
      properties:
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: >-
          org.apache.kafka.common.security.scram.ScramLoginModule required
          username="${KAFKA_PRODUCER_USERNAME}"
          password="${KAFKA_PRODUCER_PASSWORD}";

    consumer:
      properties:
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: >-
          org.apache.kafka.common.security.scram.ScramLoginModule required
          username="${KAFKA_CONSUMER_USERNAME}"
          password="${KAFKA_CONSUMER_PASSWORD}";
~~~

Cách tách principal giúp giới hạn quyền:

- Producer chỉ cần quyền ghi vào các topic được phép.
- Consumer chỉ cần quyền đọc các topic và group được phép.
- Tài khoản vận hành hoặc AdminClient có thể dùng principal khác với quyền quản trị riêng.

Nếu producer và consumer dùng chung cấu hình `spring.kafka.properties`, cả hai thường nhận cùng các thuộc tính client chung. Thuộc tính ở `spring.kafka.producer.properties` hoặc `spring.kafka.consumer.properties` cho phép override theo client. Cần kiểm tra cấu hình hiệu lực khi ứng dụng có nhiều ConsumerFactory, ProducerFactory hoặc template tự tạo.

## 11. Cấu hình SASL cho Kafka Admin client

Spring Boot có thể tạo KafkaAdmin để provision hoặc kiểm tra topic. Admin client cũng cần xác thực và authorization phù hợp.

Có thể đặt thuộc tính riêng:

~~~yaml
spring:
  kafka:
    admin:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: >-
          org.apache.kafka.common.security.scram.ScramLoginModule required
          username="${KAFKA_ADMIN_USERNAME}"
          password="${KAFKA_ADMIN_PASSWORD}";
        ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
        ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Không nên dùng principal quản trị cho producer/consumer chỉ để tránh lỗi ACL. Hãy cấp quyền AdminClient riêng cho thao tác cần thiết, ví dụ mô tả hoặc tạo topic theo quy trình đã phê duyệt.

Nếu ứng dụng tự tạo AdminClient bằng `AdminClient.create(props)`, phải truyền đúng cấu hình bảo mật vào map properties. Cấu hình `spring.kafka.admin.properties` chỉ áp dụng cho KafkaAdmin được Boot auto-configure, không tự động thay đổi mọi AdminClient do code tự tạo.

## 12. TLS truststore và SASL là hai phần khác nhau

Trong `SASL_SSL`, hai cơ chế có trách nhiệm khác nhau:

- TLS mã hóa kết nối và xác minh certificate của broker.
- SASL xác thực principal của client.

Truststore chứa CA hoặc certificate mà client tin cậy để xác minh broker. Nó không phải nơi lưu username/password SCRAM. Nếu dùng mutual TLS, keystore của client chứa private key và certificate client; đó là một lớp xác thực TLS riêng.

| Thành phần | Chức năng |
|---|---|
| Truststore | Tin cậy certificate chain của broker. |
| Keystore | Chứa certificate/private key của client khi cần mutual TLS. |
| JAAS config | Cung cấp login module và credential cho SASL. |
| SASL mechanism | Xác định giao thức xác thực. |
| ACL | Xác định principal được phép thao tác gì. |

Nếu gặp `SSLHandshakeException`, kiểm tra certificate chain, hostname, truststore và thời hạn certificate. Nếu gặp `SaslAuthenticationException`, kiểm tra mechanism, username/password, token hoặc principal.

## 13. Broker phải được cấu hình tương ứng

Client chỉ khai báo cách kết nối; broker phải có listener phù hợp. Ví dụ client dùng `SASL_SSL` với `SCRAM-SHA-512`, broker listener tương ứng cần bật SASL trên TLS và hỗ trợ mechanism đó.

Các điều kiện phía broker/nền tảng thường gồm:

- Listener bind đúng port và protocol.
- Bật SASL mechanism mà client chọn.
- Cấu hình TLS certificate cho listener.
- Provision user hoặc credential SCRAM/OAuth/Kerberos tương ứng.
- Cấu hình authorizer và ACL nếu cần giới hạn quyền.
- Cho phép network route từ application tới broker.

Tên listener, cơ chế provision user và cấu hình authorizer phụ thuộc Kafka distribution hoặc managed Kafka service. Không sao chép một cấu hình broker từ môi trường khác nếu chưa xác minh phiên bản và nền tảng.

## 14. ACL sau khi SASL authentication thành công

Sau authentication, broker tạo principal cho client. Authorizer dùng principal và ACL để quyết định request có được phép hay không.

Ví dụ quyền thường cần:

| Vai trò | Quyền thường cần |
|---|---|
| Producer | WRITE và thường DESCRIBE trên topic đích. |
| Consumer | READ và thường DESCRIBE trên topic nguồn; READ trên consumer group. |
| Admin topic | Quyền quản trị topic/cluster tương ứng thao tác. |
| Transactional producer | Quyền cần thiết trên transactional ID cùng topic/cluster theo ACL model đang dùng. |

Quyền chính xác phụ thuộc Kafka version, authorizer, operation và resource pattern. Khi bật transactions, producer có thể cần quyền với transactional ID ngoài quyền ghi topic.

Không cấp `ALL` cho mọi principal chỉ để làm ứng dụng chạy. Hãy bắt đầu từ thao tác thực tế, cấp quyền tối thiểu và kiểm tra lỗi authorization sau khi xác thực.

## 15. Quản lý username, password, keytab và token

Credential là dữ liệu nhạy cảm. Các nguyên tắc cần tuân thủ:

- Không commit password, token, private key hoặc keytab vào Git.
- Không ghi JAAS config đầy đủ vào log.
- Không đưa secret vào exception message hoặc diagnostic endpoint.
- Dùng Kubernetes Secret, Vault, cloud secret manager hoặc cơ chế secret store của tổ chức.
- Giới hạn quyền đọc secret theo service account và application identity.
- Mã hóa dữ liệu secret khi lưu trữ và bảo vệ kênh phân phối.
- Dùng credential riêng cho producer, consumer và AdminClient khi phù hợp.
- Thu hồi credential khi service không còn cần truy cập.
- Không dùng tài khoản cá nhân của developer làm credential production.

Environment variable trong ví dụ chỉ là cách minh họa inject cấu hình. Trong production, cần bảo vệ cả nguồn cấp biến môi trường và khả năng đọc environment của process/container.

## 16. Rotation credential

Credential có thể cần rotation định kỳ hoặc ngay khi nghi ngờ bị lộ. Một quy trình an toàn thường gồm:

1. Tạo credential mới hoặc cập nhật secret theo khả năng của broker.
2. Nếu nền tảng hỗ trợ, duy trì khoảng thời gian overlap để cả credential cũ và mới cùng hợp lệ.
3. Cập nhật secret của ứng dụng.
4. Tạo mới hoặc restart client/container theo quy trình triển khai.
5. Xác minh producer, consumer và AdminClient đã xác thực bằng credential mới.
6. Thu hồi credential cũ sau khi toàn bộ instance đã chuyển đổi.
7. Theo dõi lỗi authentication và connection trong giai đoạn chuyển tiếp.

Không giả định thay environment variable sẽ tự cập nhật JAAS config của các Kafka client đang chạy. Các producer/consumer hiện hữu thường giữ cấu hình và kết nối đã tạo; việc refresh phụ thuộc mechanism, callback handler và lifecycle client.

Với OAuth, callback handler có thể làm mới token theo integration được hỗ trợ. Với username/password JAAS tĩnh, thường cần tạo lại client hoặc restart ứng dụng để áp dụng credential mới một cách rõ ràng.

## 17. Phân biệt lỗi xác thực, TLS và ACL

| Dấu hiệu | Nhóm nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `SaslAuthenticationException` | Username/password, token, principal hoặc JAAS sai | Kiểm tra secret, login module và broker mechanism. |
| Unsupported SASL mechanism | Client mechanism không được listener hỗ trợ | Đối chiếu `sasl.mechanism` với broker listener. |
| `SSLHandshakeException` | Truststore, certificate, hostname hoặc TLS protocol | Kiểm tra CA, hostname và hạn certificate. |
| `TopicAuthorizationException` | Principal không có quyền topic | Kiểm tra ACL cho topic và operation. |
| `GroupAuthorizationException` | Principal không có quyền consumer group | Kiểm tra ACL resource group. |
| `ClusterAuthorizationException` | Thiếu quyền thao tác cluster/admin | Kiểm tra quyền quản trị tương ứng. |
| Timeout hoặc disconnect | Network, DNS, listener, firewall hoặc broker unavailable | Kiểm tra route, bootstrap server và broker logs. |

Không xử lý mọi lỗi kết nối bằng cách retry vô hạn. Sai password hoặc ACL không tự được sửa bằng chờ; retry liên tục chỉ tạo log noise và tải lên broker. Phân loại lỗi để cảnh báo và sửa cấu hình.

## 18. Kiểm thử SASL và authorization

Một bài kiểm thử bảo mật nên xác minh cả kết nối hợp lệ lẫn hành vi bị từ chối.

| Kịch bản | Điều cần xác minh |
|---|---|
| Credential hợp lệ | Producer/consumer kết nối và thực hiện đúng thao tác được cấp quyền. |
| Password sai | Authentication thất bại và không có record được ghi/đọc. |
| Username không tồn tại | Broker từ chối authentication. |
| Mechanism sai | Client không thể hoàn tất SASL handshake. |
| Certificate không tin cậy | TLS handshake thất bại trước khi dùng Kafka API. |
| Hostname không khớp | Client từ chối certificate theo hostname verification. |
| Principal không có quyền WRITE | Produce bị từ chối dù authentication thành công. |
| Consumer thiếu READ trên group | Join/commit group bị từ chối theo ACL. |
| Admin thiếu quyền | Thao tác quản trị thất bại đúng như dự kiến. |
| Credential rotation | Instance mới kết nối bằng secret mới và credential cũ được thu hồi đúng lúc. |

Có thể dùng Testcontainers hoặc môi trường Kafka test đã cấu hình SASL/TLS. Cần tạo broker listener, user, mechanism và ACL tương ứng; chỉ cấu hình client trong Spring Boot không đủ để tạo môi trường SASL test.

Integration test nên xác minh cả producer, consumer và AdminClient nếu ứng dụng dùng cả ba. Không chỉ kiểm tra ứng dụng khởi động thành công: connection tới broker có thể được tạo lười và lỗi chỉ xuất hiện khi client gửi request đầu tiên.

## 19. Checklist vận hành

Trước khi đưa ứng dụng Spring Kafka dùng SASL vào production, kiểm tra:

- [ ] Broker listener bật đúng security protocol và SASL mechanism.
- [ ] Client dùng đúng bootstrap server và listener port.
- [ ] TLS certificate được xác minh bằng truststore hợp lệ.
- [ ] Username/password, keytab hoặc token được cấp từ secret store.
- [ ] Producer và consumer có principal riêng khi phù hợp.
- [ ] ACL chỉ cấp quyền cần thiết cho topic, group, transactional ID và thao tác quản trị.
- [ ] Secret không xuất hiện trong Git, image, log hoặc endpoint chẩn đoán.
- [ ] Có quy trình rotation và thu hồi credential.
- [ ] Authentication error được phân biệt với TLS, network và authorization error.
- [ ] Alert được cấu hình cho authentication failure và authorization denial tăng bất thường.
- [ ] Integration test xác minh cả kết nối thành công và quyền bị từ chối.
- [ ] Runbook nêu owner, nơi lấy secret và cách khôi phục kết nối.

## 20. Bài tập tổng hợp: bảo vệ Order Service bằng SASL/SCRAM

Hãy cấu hình Spring Kafka để Order Service kết nối cluster qua `SASL_SSL` và `SCRAM-SHA-512`.

Yêu cầu:

1. Xác minh broker listener hỗ trợ SASL_SSL và SCRAM-SHA-512.
2. Tạo principal riêng cho producer và consumer.
3. Provision SCRAM credential ở broker hoặc managed Kafka platform.
4. Cấu hình `security.protocol`, `sasl.mechanism` và `sasl.jaas.config`.
5. Cấu hình TLS truststore và xác minh broker certificate.
6. Inject username/password từ secret store.
7. Cấu hình producer chỉ có quyền WRITE topic `orders.created`.
8. Cấu hình consumer có quyền READ topic và READ group `orders-fulfillment`.
9. Dùng AdminClient với principal quản trị riêng nếu cần tạo hoặc mô tả topic.
10. Thử password sai và ghi nhận authentication failure.
11. Thử mechanism không được broker hỗ trợ.
12. Thử produce vào topic không được cấp quyền và xác minh authorization failure.
13. Rotation credential trong môi trường test, xác minh client mới kết nối bằng secret mới.
14. Kiểm tra log không chứa password, token hoặc JAAS secret.
15. Viết integration test và runbook xử lý lỗi authentication/authorization.

Bài tập hoàn thành khi producer, consumer và AdminClient xác thực đúng principal, mỗi principal chỉ thực hiện được thao tác được cấp quyền, TLS xác minh broker và credential có thể rotation mà không bị lộ.

## 21. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Security model | Authentication và authorization | Phân biệt client identity với quyền thao tác. |
| 2. Protocol | PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL | Chọn đúng protocol theo yêu cầu bảo mật. |
| 3. Mechanisms | PLAIN, SCRAM, GSSAPI, OAUTHBEARER | Giải thích credential và điều kiện broker hỗ trợ. |
| 4. Spring Boot | Kafka client properties và JAAS | Cấu hình producer/consumer đúng mechanism. |
| 5. TLS | Truststore và certificate verification | Xác minh được broker certificate. |
| 6. Client identities | Producer, consumer và AdminClient | Dùng principal theo vai trò. |
| 7. ACL | Topic, group, transactional ID | Cấp quyền tối thiểu cho thao tác cần thiết. |
| 8. Secrets | Secret store và credential rotation | Không commit/log secret và đổi credential có kiểm soát. |
| 9. Troubleshooting | SASL, TLS, ACL và network errors | Xác định đúng lớp gây lỗi. |
| 10. Testing/operations | Negative tests, metrics, runbook | Chứng minh kết nối hợp lệ và từ chối đúng quyền. |

Bài học hoàn thành khi bạn có thể chọn SASL mechanism phù hợp, cấu hình Spring Kafka client với TLS, xác thực producer/consumer/AdminClient bằng principal riêng và phân biệt lỗi authentication với authorization. Bạn cũng cần có quy trình quản lý secret, rotation và kiểm thử quyền truy cập.

SASL xác minh danh tính client; ACL quyết định client được làm gì; TLS bảo vệ kết nối và xác minh broker. Khi ba phần này được cấu hình đúng, ứng dụng Spring Kafka có thể kết nối an toàn với Kafka và chỉ truy cập đúng topic, group hoặc tài nguyên được cấp quyền.

