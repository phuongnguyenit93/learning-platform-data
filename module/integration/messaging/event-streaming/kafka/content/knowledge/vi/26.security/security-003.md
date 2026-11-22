# Keystore, truststore, chứng chỉ và kiểm tra hostname

Kafka dùng TLS để mã hóa kết nối và xác thực danh tính của endpoint trong quá trình handshake. Để cấu hình TLS đúng, cần phân biệt ba việc: **keystore** giữ private key và certificate identity của bên trình chứng chỉ; **truststore** chứa CA hoặc certificate mà bên kết nối tin cậy; **hostname verification** xác nhận certificate thực sự được cấp cho hostname mà client đang kết nối.

Một kết nối có thể mã hóa thành công nhưng vẫn không an toàn nếu client bỏ qua hostname verification. Ngược lại, certificate có SAN đúng nhưng CA không nằm trong truststore thì handshake vẫn thất bại. Với Kafka cluster, còn phải kiểm tra các địa chỉ broker trong advertised.listeners vì client kết nối tới từng broker sau bước bootstrap ban đầu.

## 1. TLS bảo vệ kết nối Kafka như thế nào?

TLS tạo một kênh mã hóa giữa Kafka client và broker. Trong handshake, broker trình certificate chain để client xác minh. Nếu bật mutual TLS (mTLS), client cũng trình certificate để broker xác minh.

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant B as Kafka broker
    participant CA as Trusted CA

    C->>B: TLS ClientHello
    B-->>C: Server certificate chain
    C->>CA: Verify certificate chain
    C->>C: Verify SAN matches broker hostname
    alt mTLS enabled
        C->>B: Client certificate
        B->>B: Verify client certificate chain
    end
    B-->>C: TLS handshake complete
    C->>B: Kafka protocol requests over encrypted channel
~~~

TLS cung cấp:

- **Confidentiality:** mã hóa dữ liệu trên đường truyền.
- **Integrity:** phát hiện dữ liệu bị thay đổi trong quá trình truyền.
- **Server authentication:** client xác minh broker qua certificate.
- **Client authentication (tùy chọn):** broker xác minh client certificate khi dùng mTLS.

TLS không tự cấp quyền đọc topic, ghi topic hoặc quản trị cluster. Sau khi xác thực, Kafka vẫn cần authorization/ACL hoặc authorizer phù hợp để kiểm soát hành động.

## 2. Keystore và truststore khác nhau thế nào?

Hai store có vai trò ngược nhau trong xác thực certificate:

| Thành phần | Chứa gì? | Được dùng để làm gì? |
|---|---|---|
| Keystore | Private key và certificate chain của chính endpoint | Chứng minh endpoint sở hữu danh tính trong certificate |
| Truststore | CA certificate hoặc certificate được tin cậy | Xác minh certificate do peer trình ra |

Ví dụ khi Kafka client kết nối broker:

- Broker dùng keystore chứa private key và certificate server.
- Client dùng truststore chứa CA đã ký certificate server.
- Nếu bật mTLS, client có keystore riêng chứa private key và client certificate.
- Broker cần truststore tin cậy CA đã ký client certificate.

Không gửi private key cho peer. Truststore thường chỉ chứa public CA/certificate; keystore là nơi cần bảo vệ private key.

### Certificate chain

Một certificate server thường được CA trung gian ký; CA trung gian có thể được CA gốc ký. Server cần trình đủ certificate chain cần thiết để client xây dựng đường tin cậy đến CA mà truststore chấp nhận.

~~~text
Kafka client truststore
    └── Root CA (trusted)
          └── Intermediate CA
                └── Broker leaf certificate
                      └── Broker private key (keystore)
~~~

Certificate leaf không nhất thiết tự chứa root CA. Khi thiếu intermediate certificate, client có thể báo lỗi không xây dựng được certification path dù root CA đã nằm trong truststore.

## 3. JKS, PKCS12 và PEM

Kafka chạy trên JVM nên thường gặp các định dạng:

| Định dạng | Đặc điểm | Khi dùng |
|---|---|---|
| JKS | Java KeyStore truyền thống | Hệ thống Java cũ hoặc môi trường đã chuẩn hóa JKS |
| PKCS12 | Định dạng store tiêu chuẩn, hỗ trợ private key và certificate | Lựa chọn phổ biến cho triển khai Java hiện đại |
| PEM | Certificate và private key ở dạng văn bản Base64 | Hợp với hệ thống cấp phát certificate dùng OpenSSL/Kubernetes/secret manager |

PKCS12 thường thuận tiện khi cần chuyển certificate từ công cụ OpenSSL sang JVM. Chọn type rõ ràng để tránh runtime đoán sai định dạng:

~~~properties
ssl.keystore.type=PKCS12
ssl.truststore.type=PKCS12
~~~

Kafka hỗ trợ PEM trong các phiên bản hiện đại, nhưng các property và cách cung cấp key/certificate khác với file JKS/PKCS12. Khả năng hỗ trợ phụ thuộc Kafka version, Java runtime và cấu hình cụ thể; kiểm tra tài liệu đúng phiên bản trước khi chuyển từ store file sang PEM. Không trộn cấu hình PEM inline với đường dẫn keystore/truststore của PKCS12.

### Hai loại password trong keystore

Với keystore file, thường có hai cấu hình:

- ssl.keystore.password: password mở keystore.
- ssl.key.password: password bảo vệ private key entry.

Hai password có thể giống hoặc khác nhau tùy cách tạo store. Truststore có ssl.truststore.password; truststore không cần private key password vì nó không giữ private key của endpoint.

Không commit password hoặc private key vào Git, Docker image hay file cấu hình công khai. Dùng secret manager, Kubernetes Secret hoặc cơ chế quản lý secret phù hợp; giới hạn quyền đọc file key ở user chạy Kafka/client.

## 4. Hostname verification và Subject Alternative Name (SAN)

Khi client kết nối tới kafka-1.example.com, client cần xác nhận certificate server có SAN khớp với hostname đó. SAN có thể chứa:

- DNS SAN: ví dụ DNS:kafka-1.example.com.
- IP SAN: ví dụ IP:10.20.1.15 nếu client kết nối trực tiếp bằng IP.

Certificate chỉ có Common Name (CN) mà không có SAN phù hợp không nên được coi là cấu hình hiện đại đáng tin cậy. Đưa mọi DNS name và IP endpoint cần sử dụng vào SAN khi cấp certificate.

Kafka Java client bật hostname verification theo mặc định thông qua:

~~~properties
ssl.endpoint.identification.algorithm=https
~~~

Giữ cấu hình này trong production. Đặt giá trị rỗng sẽ tắt hostname verification, làm client có thể chấp nhận certificate hợp lệ về CA nhưng được cấp cho hostname khác. Đây là cách né lỗi tạm thời, không phải cách sửa certificate.

### advertised.listeners ảnh hưởng trực tiếp đến SAN

Client dùng bootstrap server để lấy metadata cluster, sau đó kết nối tới địa chỉ broker được quảng bá trong advertised.listeners. Vì vậy, certificate phải khớp với hostname client thực sự sử dụng cho từng broker, không chỉ bootstrap hostname.

Ví dụ:

~~~properties
listeners=EXTERNAL://0.0.0.0:9094
advertised.listeners=EXTERNAL://kafka-1.example.com:9094
listener.security.protocol.map=EXTERNAL:SSL
~~~

Nếu bootstrap server là kafka.example.com nhưng metadata trả về broker-1.internal và certificate chỉ có SAN kafka.example.com, client có thể bootstrap thành công rồi thất bại khi kết nối broker. Hãy bảo đảm:

1. Hostname trong bootstrap server phân giải đúng.
2. Mỗi broker quảng bá hostname có thể truy cập từ network của client.
3. Certificate của từng broker có SAN chứa hostname advertised tương ứng.
4. Load balancer/DNS không làm client xác thực một hostname khác với hostname đã cấp certificate.

## 5. Cấu hình TLS trên Kafka broker

Broker cần certificate server trong keystore. Nếu broker yêu cầu client certificate hoặc dùng TLS cho inter-broker communication có mTLS, broker cũng cần truststore chứa CA cấp client/broker certificate.

Ví dụ một listener bên ngoài dùng TLS và listener nội bộ dùng TLS:

~~~properties
listeners=INTERNAL://0.0.0.0:9093,EXTERNAL://0.0.0.0:9094
advertised.listeners=INTERNAL://broker-1.kafka.local:9093,EXTERNAL://kafka-1.example.com:9094
listener.security.protocol.map=INTERNAL:SSL,EXTERNAL:SSL
inter.broker.listener.name=INTERNAL

listener.name.internal.ssl.keystore.location=/etc/kafka/tls/broker-1.p12
listener.name.internal.ssl.keystore.type=PKCS12
listener.name.internal.ssl.keystore.password=__BROKER_KEYSTORE_PASSWORD__
listener.name.internal.ssl.key.password=__BROKER_KEY_PASSWORD__
listener.name.internal.ssl.truststore.location=/etc/kafka/tls/broker-truststore.p12
listener.name.internal.ssl.truststore.type=PKCS12
listener.name.internal.ssl.truststore.password=__INTERNAL_TRUSTSTORE_PASSWORD__
listener.name.internal.ssl.client.auth=required

listener.name.external.ssl.keystore.location=/etc/kafka/tls/broker-1.p12
listener.name.external.ssl.keystore.type=PKCS12
listener.name.external.ssl.keystore.password=__BROKER_KEYSTORE_PASSWORD__
listener.name.external.ssl.key.password=__BROKER_KEY_PASSWORD__
listener.name.external.ssl.truststore.location=/etc/kafka/tls/client-ca-truststore.p12
listener.name.external.ssl.truststore.type=PKCS12
listener.name.external.ssl.truststore.password=__CLIENT_CA_TRUSTSTORE_PASSWORD__
listener.name.external.ssl.client.auth=required
~~~

Đây là ví dụ minh họa listener-specific properties; thay hostname, file path và secret theo môi trường. Cấu hình ssl.client.auth=required yêu cầu client trình certificate được CA trong truststore tin cậy. Nếu client chỉ xác thực bằng SASL qua TLS, listener không nên bắt buộc client certificate; có thể dùng SASL_SSL và cấu hình SASL riêng.

Các giá trị listener-specific có dạng listener.name.<listener-name>.<ssl-property>. Tên listener trong prefix được viết thường. Nếu cấu hình một bộ SSL property chung cho mọi listener, cần chắc chắn các listener có cùng trust boundary và yêu cầu client authentication; tách riêng listener thường dễ kiểm soát hơn.

Với nhiều broker, mỗi broker thường có private key riêng và certificate SAN chứa tên broker đó. Không sao chép cùng một private key server ra toàn cluster nếu không có lý do kiến trúc và quy trình quản lý rủi ro rõ ràng.

## 6. Server TLS và mutual TLS (mTLS)

Có hai kiểu xác thực certificate thường gặp:

### TLS một chiều (server-auth TLS)

- Broker trình server certificate.
- Client xác minh certificate bằng truststore.
- Client không cần keystore hoặc client certificate.
- Dùng khi xác thực user bằng SASL/PLAIN, SCRAM, Kerberos hoặc cơ chế khác trên kênh TLS.

### Mutual TLS

- Broker trình server certificate và client xác minh.
- Client trình client certificate và broker xác minh qua truststore.
- Broker có thể lấy principal từ distinguished name (DN) của client certificate.
- Kafka ACL/authorizer vẫn quyết định principal được phép làm gì.

Broker có thể cấu hình:

~~~properties
listener.name.external.ssl.client.auth=required
~~~

Các giá trị thường dùng là none, requested và required:

| Giá trị | Hành vi |
|---|---|
| none | Broker không yêu cầu client certificate |
| requested | Broker yêu cầu certificate nhưng có thể tiếp tục nếu client không gửi |
| required | Client phải gửi certificate hợp lệ |

Khi dùng mTLS, cần bảo đảm truststore của broker tin CA cấp client certificate, và client keystore có certificate chain cùng private key tương ứng. Nếu bật required nhưng client chỉ có truststore, TLS handshake sẽ thất bại vì client không có identity certificate để trình.

## 7. Cấu hình Kafka client dùng TLS

Với server-auth TLS, client chỉ cần truststore để xác minh broker:

~~~properties
bootstrap.servers=kafka-1.example.com:9094,kafka-2.example.com:9094
security.protocol=SSL

ssl.truststore.location=/etc/app/tls/kafka-truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=__KAFKA_TRUSTSTORE_PASSWORD__

ssl.endpoint.identification.algorithm=https
~~~

Với mTLS, thêm client keystore:

~~~properties
ssl.keystore.location=/etc/app/tls/app-client.p12
ssl.keystore.type=PKCS12
ssl.keystore.password=__CLIENT_KEYSTORE_PASSWORD__
ssl.key.password=__CLIENT_KEY_PASSWORD__
~~~

Client keystore phải chứa certificate client và private key. Truststore phải tin cậy CA đã ký certificate broker. Hai store phục vụ hai chiều xác thực khác nhau; không thay truststore bằng keystore hoặc ngược lại.

### Dùng SASL qua TLS

Nếu xác thực ứng dụng bằng SCRAM, dùng SASL_SSL: TLS mã hóa và xác thực broker, còn SASL xác thực user Kafka. Ví dụ phần cấu hình SASL (secret cần lấy từ secret manager):

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="__SCRAM_PASSWORD__";

ssl.truststore.location=/etc/app/tls/kafka-truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=__KAFKA_TRUSTSTORE_PASSWORD__
ssl.endpoint.identification.algorithm=https
~~~

Không đặt username/password thật trong file được commit. Nếu kết hợp SASL_SSL với mTLS, bổ sung client keystore theo cấu hình mTLS. Khi đó certificate dùng cho TLS client authentication và SASL identity là hai lớp danh tính; cách principal được dùng cho ACL phụ thuộc cơ chế authentication và cấu hình broker.

## 8. Cấu hình Spring Boot / Spring Kafka

Spring Kafka sử dụng Kafka client properties. Có thể cấu hình SSL trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.com:9094
      - kafka-2.example.com:9094
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": /etc/app/tls/kafka-truststore.p12
      "[ssl.truststore.type]": PKCS12
      "[ssl.truststore.password]": __KAFKA_TRUSTSTORE_PASSWORD__
      "[ssl.endpoint.identification.algorithm]": https
~~~

Với mTLS, bổ sung:

~~~yaml
spring:
  kafka:
    properties:
      "[ssl.keystore.location]": /etc/app/tls/app-client.p12
      "[ssl.keystore.type]": PKCS12
      "[ssl.keystore.password]": __CLIENT_KEYSTORE_PASSWORD__
      "[ssl.key.password]": __CLIENT_KEY_PASSWORD__
~~~

Ví dụ dùng property map của Spring Boot để chuyển tiếp nguyên tên property Kafka. Kiểm tra cách bind YAML và secret placeholder theo phiên bản Spring Boot của dự án; tránh khai báo hai lần cùng một key trong các file profile khác nhau.

Kafka Connect worker cũng là Kafka client khi truy cập broker. Worker cần TLS cấu hình cho bootstrap/internal topics; connector plugin có thể cần truststore hoặc TLS riêng để kết nối database/API bên ngoài. TLS của Connect-to-Kafka và TLS của connector-to-source/destination là hai kết nối độc lập.

## 9. Cấp certificate có SAN đúng

Trong production, dùng CA nội bộ hoặc CA doanh nghiệp được quản lý tập trung. Mỗi broker/client identity cần certificate riêng, thời hạn hợp lý và quy trình thu hồi/rotation. Không dùng certificate tự ký tùy tiện hoặc dùng một certificate wildcard rộng cho mọi thành phần nếu chính sách bảo mật yêu cầu identity riêng.

Ví dụ file cấu hình OpenSSL cho CSR broker:

~~~ini
[ req ]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[ req_distinguished_name ]
CN = kafka-1.example.com

[ v3_req ]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth

[ alt_names ]
DNS.1 = kafka-1.example.com
DNS.2 = broker-1.kafka.local
IP.1 = 10.20.1.15
~~~

Tạo private key và CSR:

~~~bash
openssl req -new -newkey rsa:3072 \
  -keyout broker-1.key \
  -out broker-1.csr \
  -config broker-1.cnf
~~~

Gửi CSR tới CA để ký. CA cần giữ lại SAN và extension phù hợp trong certificate được cấp. Ví dụ trên dùng cùng broker certificate cho vai trò TLS server và client trong inter-broker mTLS nên khai báo cả serverAuth và clientAuth. Nếu certificate chỉ dùng làm server identity, serverAuth thường là EKU cần thiết; client certificate dùng cho mTLS cần clientAuth. Chính sách CA có thể yêu cầu thêm key usage hoặc extension khác.

Sau khi CA cấp certificate, đóng gói thành PKCS12 (ví dụ dùng certificate chain đã được CA cung cấp):

~~~bash
openssl pkcs12 -export \
  -in broker-1.crt \
  -inkey broker-1.key \
  -certfile ca-chain.crt \
  -name broker-1 \
  -out broker-1.p12
~~~

Lệnh sẽ yêu cầu password để bảo vệ PKCS12 và có thể yêu cầu password private key. Bảo vệ file tạm, CSR và private key trong toàn bộ quá trình. Không gửi private key lên CA; chỉ gửi CSR.

### Tạo truststore từ CA

~~~bash
keytool -importcert \
  -alias kafka-root-ca \
  -file root-ca.crt \
  -keystore kafka-truststore.p12 \
  -storetype PKCS12
~~~

Nếu chain có intermediate CA, thêm các CA cần thiết vào truststore hoặc bảo đảm peer trình đủ chain để JVM xây dựng trust path. Khi import, xác minh fingerprint certificate từ nguồn tin cậy; không xác nhận certificate chỉ vì lệnh keytool hiển thị prompt.

## 10. Kiểm tra keystore, truststore và SAN

### Xem nội dung PKCS12

~~~bash
keytool -list -v \
  -keystore broker-1.p12 \
  -storetype PKCS12
~~~

Kiểm tra alias, loại entry, certificate chain, issuer, thời hạn và Subject Alternative Name. Keystore server cần có PrivateKeyEntry; truststore CA thường có trusted certificate entries.

### Kiểm tra certificate file

~~~bash
openssl x509 -in broker-1.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

Kiểm tra:

- Certificate chưa hết hạn và chưa tới thời điểm hiệu lực.
- SAN có DNS/IP mà client thực sự kết nối.
- Issuer/chain được CA dự kiến ký.
- EKU phù hợp vai trò serverAuth hoặc clientAuth.
- Private key khớp certificate.

### Kiểm tra TLS handshake và hostname

~~~bash
openssl s_client \
  -connect kafka-1.example.com:9094 \
  -servername kafka-1.example.com \
  -verify_hostname kafka-1.example.com \
  -CAfile ca-chain.crt
~~~

servername gửi SNI; verify_hostname kiểm tra hostname trên certificate; CAfile cung cấp CA chain được tin cậy cho phép thử. Kết quả Verify return code: 0 (ok) là tín hiệu tốt cho lần kiểm tra TLS này, nhưng vẫn cần kiểm tra Kafka protocol, authentication và ACL.

### Kiểm tra bằng Kafka CLI

Tạo client.properties với truststore và protocol phù hợp, rồi chạy:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server kafka-1.example.com:9094 \
  --command-config client.properties
~~~

Nếu lệnh truy cập broker thành công, TLS handshake và Kafka protocol đã hoạt động cho endpoint được kiểm tra. Với cluster nhiều broker, tiếp tục xác minh client có thể kết nối các hostname trong metadata của tất cả broker.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| PKIX path building failed | Client không tin CA hoặc thiếu intermediate certificate | Kiểm tra truststore, issuer và certificate chain |
| No subject alternative DNS name matching | Hostname kết nối không nằm trong SAN | So sánh bootstrap/advertised hostname với SAN |
| No name matching ... found | SAN không khớp DNS name | Cấp lại certificate với SAN đúng |
| Untrusted certificate | CA không được trust hoặc certificate chain không hợp lệ | Xác minh fingerprint, CA và chain |
| Keystore was tampered with, or password was incorrect | Sai password hoặc file store hỏng/sai type | Kiểm tra password, file path và PKCS12/JKS type |
| UnrecoverableKeyException | Sai key password hoặc private key entry không đọc được | Kiểm tra ssl.key.password và alias |
| bad_certificate / handshake failure với mTLS | Client thiếu certificate, certificate không được tin hoặc EKU sai | Kiểm tra client keystore, broker truststore và clientAuth |
| Bootstrap thành công nhưng produce/fetch thất bại | Broker advertised hostname khác SAN hoặc network không tới broker đó | Kiểm tra metadata, advertised.listeners, DNS và firewall |
| Certificate expired / not yet valid | Certificate hết hạn hoặc clock lệch | Kiểm tra thời gian hệ thống và lịch rotation |
| TLS protocol/cipher mismatch | Client và broker không có protocol/cipher chung | Kiểm tra JVM, ssl.protocol và ssl.enabled.protocols |

Không tắt hostname verification để chữa lỗi SAN. Không import certificate lạ vào truststore chỉ để handshake thành công; trước tiên phải xác minh fingerprint và nguồn cấp certificate.

## 12. Rotation và thu hồi certificate

Certificate có thời hạn. Rotation cần phối hợp CA, broker, client và thời gian triển khai để tránh gián đoạn.

Một quy trình thường dùng:

1. Cấp CA/certificate mới trước khi certificate cũ hết hạn.
2. Nếu đổi CA, triển khai truststore chứa cả CA cũ và CA mới lên các bên cần xác minh peer.
3. Cập nhật broker certificate/keystore theo rolling procedure phù hợp.
4. Cập nhật client certificate nếu dùng mTLS.
5. Kiểm tra handshake, hostname, ACL principal và log lỗi trên mọi listener.
6. Sau khi tất cả peer đã chuyển, loại CA cũ khỏi truststore.
7. Thu hồi certificate cũ theo chính sách CA và lưu audit.

Không xóa CA cũ khỏi truststore trước khi toàn bộ broker/client đã dùng certificate mới. Nếu certificate client xác định principal theo DN, thay certificate hoặc subject DN có thể ảnh hưởng mapping và ACL; cần kiểm tra ssl.principal.mapping.rules và authorization trước khi rotate.

Khả năng reload SSL material động phụ thuộc Kafka version, loại cấu hình và cách triển khai. Nếu chưa xác nhận dynamic reload được hỗ trợ và hoạt động đúng, dùng rolling restart có kiểm soát; không giả định sửa file keystore trên disk làm broker tự nạp certificate mới.

## 13. TLS, SASL và ACL là các lớp khác nhau

| Cơ chế | Câu hỏi nó trả lời |
|---|---|
| TLS | Kết nối có được mã hóa và peer có certificate hợp lệ không? |
| mTLS | Client có trình certificate identity mà broker tin cậy không? |
| SASL | Client xác thực bằng username/password, SCRAM, Kerberos hoặc cơ chế SASL nào? |
| ACL/Authorizer | Principal đã xác thực được phép đọc/ghi topic, group hoặc cluster resource nào? |

Ví dụ:

- SSL: mã hóa và broker authentication bằng certificate.
- SASL_SSL: TLS bảo vệ đường truyền, SASL xác thực user.
- SSL với mTLS: TLS bảo vệ đường truyền và broker xác thực client certificate.
- SASL_SSL + mTLS: dùng cả client certificate và SASL identity; phải xác định rõ principal được authorizer sử dụng.

Không coi việc TLS handshake thành công là bằng chứng client có quyền đọc topic. Sau khi xác thực, kiểm tra ACL cho topic, consumer group, transactional ID và cluster operation mà ứng dụng cần.

## 14. Production checklist

- [ ] Mỗi broker có certificate và private key được quản lý riêng.
- [ ] Keystore chứa đúng private key và certificate chain; truststore chứa CA được xác minh.
- [ ] Store type JKS/PKCS12/PEM khớp với cấu hình và Kafka version.
- [ ] Password được quản lý qua secret manager, không commit vào Git.
- [ ] SAN chứa mọi DNS/IP mà client thực sự dùng để kết nối broker.
- [ ] advertised.listeners công bố hostname có thể truy cập và khớp SAN.
- [ ] Client giữ ssl.endpoint.identification.algorithm=https.
- [ ] Listener phân biệt rõ server-auth TLS, mTLS và SASL_SSL.
- [ ] Nếu mTLS, broker trust client CA và client trình certificate hợp lệ.
- [ ] Inter-broker listener có certificate/trust chain và network phù hợp.
- [ ] ACL/authorizer giới hạn quyền sau khi client đã xác thực.
- [ ] Certificate chain, EKU, validity, clock và protocol/cipher được kiểm tra.
- [ ] Đã kiểm thử bằng keytool/openssl và Kafka CLI trên mọi broker endpoint.
- [ ] Có lịch rotation, overlap CA, rollback và thu hồi certificate.
- [ ] Theo dõi handshake failure, certificate expiry và lỗi hostname verification.

Keystore chứng minh danh tính của endpoint bằng private key và certificate; truststore xác định CA/certificate mà endpoint tin cậy; hostname verification ràng buộc certificate với địa chỉ broker mà client kết nối. Cấu hình ba phần này đúng, kết hợp TLS/mTLS hoặc SASL_SSL và ACL phù hợp, giúp bảo vệ Kafka traffic mà vẫn duy trì xác thực và phân quyền rõ ràng.
