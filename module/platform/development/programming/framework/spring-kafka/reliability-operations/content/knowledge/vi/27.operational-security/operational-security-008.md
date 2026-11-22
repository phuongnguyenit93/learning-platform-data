# Bảo vệ secret và certificate trong vận hành Spring Kafka

## 1. Vì sao secret và certificate cần được quản lý như một phần của độ tin cậy

Một ứng dụng Spring Kafka chỉ kết nối an toàn khi cả danh tính của broker, danh tính của client và quyền truy cập đều được kiểm soát. Trong môi trường thật, các thông tin này thường tồn tại dưới dạng mật khẩu SASL, token OAuth, private key, certificate, truststore và keystore. Nếu chúng bị lộ, bị thay sai hoặc hết hạn, ứng dụng có thể mất quyền truy cập Kafka; nếu cấu hình kiểm tra danh tính bị tắt để “chữa cháy”, ứng dụng còn có thể kết nối nhầm máy chủ.

Quản lý secret và certificate vì vậy là công việc vận hành liên tục. Nó bao gồm nơi lưu trữ, cách cấp quyền đọc, cách đưa thông tin vào tiến trình Spring Boot, cách xoay vòng trước khi hết hạn, cách thu hồi khi có sự cố và cách xác minh sau mỗi lần thay đổi.

Hai khái niệm cần phân biệt:

| Thành phần | Vai trò | Có cần giữ bí mật? |
|---|---|---|
| Username, password SASL, OAuth client secret hoặc access token | Xác thực client với Kafka hoặc hệ thống cấp token | Có |
| Private key của client hoặc broker | Chứng minh bên sở hữu certificate | Có, phải bảo vệ nghiêm ngặt |
| Certificate của broker hoặc client | Chứa danh tính và public key, được CA ký | Thường không cần giữ bí mật, nhưng phải bảo vệ tính toàn vẹn |
| CA certificate | Cho phép xác minh chuỗi tin cậy | Không phải secret, nhưng thay đổi trái phép có thể làm mất an toàn |
| Truststore | Chứa CA hoặc certificate mà client tin cậy | Nội dung thường không bí mật; quyền sửa phải được giới hạn |
| Keystore | Chứa private key và certificate chain của một danh tính | Phải bảo vệ như secret |
| Mật khẩu bảo vệ keystore | Mở khóa private key trong keystore | Có |

Không nên gọi mọi file TLS là secret. Certificate công khai thường không nhạy cảm như private key, nhưng một truststore bị thay thế vẫn có thể khiến client tin nhầm CA. Cần bảo vệ cả bí mật lẫn tính toàn vẹn của cấu hình tin cậy.

## 2. Các lớp bảo mật khi Spring Kafka kết nối đến broker

Kafka cung cấp nhiều security protocol:

| Protocol | Mã hóa TLS | Xác thực SASL |
|---|---:|---:|
| PLAINTEXT | Không | Không |
| SSL | Có | Không bắt buộc |
| SASL_PLAINTEXT | Không | Có |
| SASL_SSL | Có | Có |

Trong hệ thống production, SASL_SSL là lựa chọn phổ biến khi cần cả mã hóa đường truyền lẫn xác thực bằng SASL. SSL ở đây bảo vệ kênh truyền và xác minh certificate của broker; SASL xác thực principal của client. Hai cơ chế giải quyết hai việc khác nhau.

TLS một chiều cho phép client xác minh broker. Client cần truststore chứa CA phát hành certificate của broker, hoặc sử dụng truststore mặc định của JVM nếu certificate được ký bởi CA mà JVM đã tin cậy. TLS hai chiều (mTLS) bổ sung việc broker xác minh certificate của client. Khi dùng mTLS, client cần cả truststore để xác minh broker và keystore chứa private key cùng certificate chain của chính client.

SASL có thể dùng các cơ chế như SCRAM, PLAIN hoặc OAUTHBEARER tùy cấu hình Kafka và nền tảng định danh. SCRAM thường phù hợp với xác thực username/password có lưu credential ở phía Kafka. PLAIN chỉ nên chạy trên TLS vì bản thân cơ chế này không mã hóa thông tin xác thực. OAUTHBEARER dùng token; token và client secret phải được cấp, làm mới và thu hồi theo vòng đời của hệ thống định danh.

Sơ đồ kết nối SASL_SSL:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot / Spring Kafka
    participant Broker as Kafka broker
    App->>Broker: Mở kết nối TLS
    Broker-->>App: Gửi certificate và certificate chain
    App->>App: Xác minh CA, thời hạn và hostname
    opt mTLS
        App->>Broker: Gửi certificate client
        Broker->>Broker: Xác minh certificate client
    end
    App->>Broker: SASL authentication
    Broker-->>App: Xác thực principal thành công
    App->>Broker: Produce / Fetch
    Broker->>Broker: Kiểm tra ACL
    Broker-->>App: Trả kết quả theo quyền được cấp
~~~

Sau xác thực vẫn còn bước authorization. Một client có certificate hợp lệ và SASL credential hợp lệ vẫn có thể bị từ chối nếu principal không có ACL phù hợp với topic hoặc consumer group. Khi xử lý sự cố, hãy tách biệt lỗi TLS, lỗi SASL và lỗi ACL thay vì thay credential một cách tùy tiện.

## 3. Lưu trữ và cấp phát secret

### 3.1. Không đưa secret vào mã nguồn hoặc cấu hình được commit

Không ghi password, token, private key hoặc mật khẩu keystore trực tiếp vào:

- Git repository, kể cả file cấu hình dành riêng cho production.
- Dockerfile, image layer, build argument hoặc log của pipeline.
- ConfigMap, file manifest triển khai hoặc tài liệu hướng dẫn dùng chung.
- URL kết nối, exception message, log ứng dụng hoặc thông tin telemetry.
- Test fixture có thể được đóng gói vào artifact production.

Việc xóa secret khỏi commit mới không làm secret đã lộ trong lịch sử Git trở nên an toàn. Nếu credential từng được commit hoặc gửi vào log, cần coi nó đã bị lộ: thu hồi hoặc xoay vòng credential, kiểm tra nơi đã truy cập và xử lý lịch sử lưu trữ theo quy trình của tổ chức.

File application.yml chỉ nên chứa tên biến hoặc tham chiếu đến nguồn cấp secret. Ví dụ, có thể dùng biến môi trường được nền tảng triển khai cấp từ secret store:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
    ssl:
      trust-store-location: file:/etc/kafka/tls/truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${KAFKA_TRUSTSTORE_PASSWORD}
      endpoint-identification-algorithm: https
~~~

Các giá trị trong dấu ngoặc nhọn ở ví dụ là placeholder được Spring Boot phân giải từ Environment. Chúng không phải giá trị credential thật. Cú pháp ngoặc vuông trong các key thuộc properties map giúp giữ nguyên key Kafka có dấu chấm. Nếu cấu hình SASL được truyền qua một nguồn khác, hãy bảo đảm nó vẫn được đưa vào Kafka client dưới đúng key và đúng định dạng JAAS.

Đối với mTLS, bổ sung cấu hình keystore cho client:

~~~yaml
spring:
  kafka:
    ssl:
      key-store-location: file:/etc/kafka/tls/client-keystore.p12
      key-store-type: PKCS12
      key-store-password: ${KAFKA_KEYSTORE_PASSWORD}
      key-password: ${KAFKA_KEY_PASSWORD}
~~~

Chỉ cấu hình keystore khi broker yêu cầu client certificate. Nếu chỉ cần TLS một chiều, client thường chỉ cần truststore. Không tạo keystore rỗng hoặc đưa private key vào ứng dụng khi kiến trúc không sử dụng mTLS.

### 3.2. Chọn nguồn cấp secret phù hợp

Nguồn cấp nên có quyền truy cập được kiểm soát, audit trail và cơ chế xoay vòng. Tùy nền tảng, có thể dùng secret manager của cloud, Vault, External Secrets Operator, Secrets Store CSI Driver hoặc Kubernetes Secret được cấu hình bảo vệ phù hợp.

Với Kubernetes:

- Dùng Secret hoặc cơ chế đồng bộ từ secret manager để cấp username, password và file certificate.
- Hạn chế quyền đọc Secret bằng RBAC; chỉ service account cần thiết mới được truy cập.
- Bật encryption at rest cho dữ liệu Secret trong etcd theo chính sách cluster.
- Mount file TLS ở chế độ read-only và giới hạn container được mount.
- Tránh đưa dữ liệu nhạy cảm vào ConfigMap hoặc manifest nằm trong Git.
- Không coi Base64 là mã hóa. Trường data của Kubernetes Secret chỉ được biểu diễn bằng Base64; nó không tự bảo vệ dữ liệu khỏi người có quyền đọc.

Ví dụ dưới đây chỉ minh họa cách tham chiếu một Kubernetes Secret đã được tạo bởi quy trình bảo mật:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: application
          env:
            - name: KAFKA_USERNAME
              valueFrom:
                secretKeyRef:
                  name: kafka-client-credentials
                  key: username
            - name: KAFKA_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: kafka-client-credentials
                  key: password
          volumeMounts:
            - name: kafka-tls
              mountPath: /etc/kafka/tls
              readOnly: true
      volumes:
        - name: kafka-tls
          secret:
            secretName: kafka-client-tls
~~~

Manifest trên không chứa giá trị secret, nhưng tên Secret và quyền truy cập vẫn là một phần của cấu hình bảo mật. Trong môi trường có secret manager, nên cân nhắc CSI hoặc cơ chế tương đương để lấy dữ liệu trực tiếp từ nguồn quản lý tập trung.

Biến môi trường tiện cho cấu hình ứng dụng, nhưng người có đủ quyền trên host hoặc container có thể đọc environment của tiến trình. Với hệ thống có yêu cầu bảo mật cao, ưu tiên cơ chế cấp file hoặc agent được kiểm soát, giới hạn quyền file và tránh sao chép secret vào nhiều lớp cấu hình. Spring Boot cũng hỗ trợ externalized configuration; có thể tổ chức cấu hình từ file được mount hoặc config tree tùy cách triển khai.

### 3.3. Quyền tối thiểu và phạm vi credential

Mỗi ứng dụng, môi trường và vai trò nên có principal riêng. Tránh dùng chung một tài khoản superuser cho producer, consumer, job quản trị và các môi trường dev/staging/production. Khi một credential bị lộ, phạm vi ảnh hưởng sẽ phụ thuộc vào quyền mà principal đó đang có.

Hãy cấp ACL theo đúng nhu cầu:

- Producer chỉ được ghi vào các topic cần thiết.
- Consumer chỉ được đọc các topic cần thiết và dùng đúng consumer group.
- Kafka Admin client chỉ được cấp quyền quản trị khi tác vụ thực sự cần.
- Quyền tạo topic, xóa topic hoặc thay đổi cấu hình broker không nên mặc định cấp cho ứng dụng nghiệp vụ.

Tách credential theo ứng dụng cũng giúp xoay vòng từng workload, điều tra log xác thực và thu hồi một client mà không làm gián đoạn các client khác.

## 4. Quản lý certificate, keystore và truststore

### 4.1. Hiểu đúng keystore và truststore

Keystore lưu danh tính mà client trình ra khi cần mTLS. Nó thường chứa private key và certificate chain tương ứng. Truststore lưu CA certificate hoặc certificate được client dùng để xác minh danh tính của broker.

| Thành phần | Nội dung điển hình | Ai sử dụng? |
|---|---|---|
| Broker certificate | Public key, SAN, issuer, thời hạn và chữ ký CA | Kafka broker trình cho client |
| Client certificate | Danh tính client và public key, do CA ký | Client trình cho broker khi dùng mTLS |
| Private key | Khóa bí mật tương ứng với certificate | Chủ thể được cấp certificate |
| Truststore của client | CA tin cậy để xác minh broker | Spring Kafka client |
| Keystore của client | Private key và certificate chain của client | Spring Kafka client khi dùng mTLS |
| Truststore của broker | CA được broker tin cậy để xác minh client | Kafka broker khi dùng mTLS |

PKCS12 là định dạng keystore phổ biến và được Java hỗ trợ. JKS vẫn có thể xuất hiện ở hệ thống cũ. Khi chuyển định dạng, cần xác minh lại alias, private key, certificate chain và mật khẩu; đổi phần mở rộng file không phải là chuyển đổi định dạng.

### 4.2. Xác minh certificate trước khi triển khai

Trước khi đưa certificate vào production, cần kiểm tra:

1. Certificate còn hiệu lực và thời gian hệ thống được đồng bộ.
2. SAN (Subject Alternative Name) có chứa hostname mà client thực sự kết nối.
3. Certificate được ký bởi CA nằm trong truststore dự kiến.
4. Certificate chain đầy đủ và đúng thứ tự theo yêu cầu của nền tảng.
5. Key Usage và Extended Key Usage phù hợp với vai trò server hoặc client.
6. Private key khớp với public key trong certificate và không bị lộ.
7. Thuật toán, protocol và cipher suite được hai phía hỗ trợ theo chính sách bảo mật.

Điểm đặc biệt quan trọng với Kafka là client không chỉ kết nối tới bootstrap server. Sau lần kết nối đầu tiên, broker trả về metadata chứa địa chỉ các broker mà client cần liên hệ tiếp. Certificate phải hợp lệ với hostname của từng broker được quảng bá trong metadata, không chỉ hostname bootstrap. Nếu bootstrap hostname đúng nhưng advertised listener dùng hostname khác không có trong SAN, client vẫn có thể lỗi xác minh hostname ở bước sau.

Không tắt hostname verification để khắc phục lỗi SAN. Hãy sửa certificate hoặc advertised listener cho khớp với tên máy chủ thực tế. Kafka client thường bật endpoint identification theo HTTPS; nếu cấu hình tường minh trong Spring Boot, giữ giá trị https như ví dụ ở trên.

Có thể kiểm tra nội dung truststore bằng keytool:

~~~bash
keytool -list -v -keystore /etc/kafka/tls/truststore.p12 -storetype PKCS12
~~~

Lệnh sẽ yêu cầu mật khẩu tương tác nếu cần. Tránh thêm mật khẩu trực tiếp vào tham số dòng lệnh vì command history, process list hoặc log của công cụ có thể làm lộ giá trị đó.

Có thể kiểm tra certificate server và quá trình bắt tay TLS bằng OpenSSL:

~~~bash
openssl s_client -connect broker.example.com:9093 -servername broker.example.com -showcerts -verify_return_error
~~~

Khi dùng CA nội bộ, có thể chỉ định file CA phù hợp bằng tùy chọn CA file. Kết quả giúp kiểm tra certificate chain và handshake từ máy chạy lệnh; nó không thay thế việc kiểm thử bằng đúng cấu hình, truststore và runtime Java mà ứng dụng Spring Kafka sử dụng.

## 5. Xoay vòng secret và certificate an toàn

Xoay vòng (rotation) là thay credential hoặc certificate theo lịch, trước thời điểm hết hạn, hoặc ngay khi có dấu hiệu bị lộ. Một quy trình rotation tốt có giai đoạn chồng lấn giữa thông tin cũ và mới để tránh một thời điểm mà client và broker không còn tin cậy lẫn nhau.

### 5.1. Xoay vòng certificate

Với thay đổi CA hoặc certificate, nguyên tắc chung là cập nhật phía xác minh tin cậy trước, sau đó mới đổi certificate được trình ra:

1. Kiểm kê broker, client, CA, certificate chain, vị trí lưu file, ngày hết hạn và service owner.
2. Phát hành CA hoặc certificate mới theo quy trình PKI. Bảo vệ private key trong quá trình tạo, lưu trữ và phân phối.
3. Nếu CA thay đổi, đưa CA mới vào truststore của bên xác minh trước khi chuyển certificate sang CA mới. Trong thời gian chuyển tiếp, truststore có thể cần chứa cả CA cũ và CA mới.
4. Cập nhật certificate server hoặc client theo từng nhóm có kiểm soát. Với broker, kiểm tra listener và certificate được broker trình ra; với mTLS, kiểm tra broker đã tin CA cấp certificate client mới.
5. Triển khai lại hoặc tái tạo Kafka client theo cơ chế của ứng dụng, sau đó xác minh handshake và thao tác produce/consume.
6. Theo dõi lỗi TLS, số kết nối, authentication failure và trạng thái từng workload.
7. Chỉ gỡ CA hoặc certificate cũ sau khi xác nhận không còn workload nào cần nó.

Không giả định Kafka client tự nạp lại keystore hoặc truststore ngay khi file trên đĩa thay đổi. Việc file mount được cập nhật không đồng nghĩa producer, consumer và connection hiện hữu đã dùng nội dung mới. Cần xác định hành vi của phiên bản Kafka client và cách tạo client trong ứng dụng; nếu không có cơ chế reload đã được kiểm chứng, hãy dùng rolling restart hoặc tái tạo client factory/client theo kế hoạch.

Trong Kubernetes, Secret volume có thể được cập nhật theo cơ chế của kubelet, nhưng tiến trình đang chạy vẫn có thể giữ cấu hình TLS đã nạp từ trước. Mount bằng subPath cũng có hành vi cập nhật khác với mount cả thư mục. Vì vậy phải kiểm thử quy trình cập nhật thực tế và có bước restart/reload rõ ràng trong runbook.

### 5.2. Xoay vòng SASL credential

Với SCRAM hoặc password-based SASL, đổi password trực tiếp có thể tạo khoảng thời gian mà một số instance vẫn dùng credential cũ. Nếu nền tảng hỗ trợ nhiều principal, phương án ít gián đoạn thường là:

1. Tạo principal mới cho ứng dụng.
2. Cấp đúng ACL mà principal cũ đang cần, sau khi rà soát quyền.
3. Cập nhật secret store và triển khai client dùng principal mới.
4. Xác minh tất cả instance đã kết nối và thao tác thành công.
5. Thu hồi principal cũ và kiểm tra không còn client nào sử dụng.

Nếu buộc phải đổi password trên cùng principal, cần xác nhận cách Kafka và cơ chế SASL của nền tảng áp dụng thay đổi, thời gian credential được cập nhật và khả năng kết nối lại của client. Lập lịch triển khai có thể rollback và theo dõi authentication failure. Với OAuth, cần quản lý thời hạn token, refresh và khả năng cấp token mới mà không ghi token vào log.

### 5.3. Tự động hóa và theo dõi hạn dùng

Nên lưu metadata về owner, mục đích, hệ thống phát hành, ngày bắt đầu hiệu lực, ngày hết hạn và quy trình thu hồi của từng certificate/credential. Không lưu giá trị bí mật trong inventory hoặc dashboard.

Thiết lập cảnh báo theo ngưỡng phù hợp với thời gian cần thiết để xin cấp mới và triển khai, ví dụ nhiều mốc trước ngày hết hạn thay vì chỉ cảnh báo vào ngày cuối. Cảnh báo cần chỉ rõ workload, certificate alias hoặc serial number, hostname và owner để người trực có thể hành động. Không đưa private key, password hoặc token vào nội dung cảnh báo.

Rotation nên có thể lặp lại và kiểm chứng được: cùng một quy trình cấp phát, phân phối, triển khai, xác minh và thu hồi; có log audit về ai thực hiện và thời điểm nào; có rollback trong giai đoạn chuyển tiếp; và có kiểm tra sau triển khai để phát hiện instance còn giữ cấu hình cũ.

## 6. Đưa cấu hình bảo mật vào Spring Kafka

Spring Boot cung cấp các thuộc tính dưới spring.kafka để cấu hình bootstrap server, SSL và các Kafka client properties dùng chung. Các thuộc tính spring.kafka.properties được chuyển tới Kafka client; producer, consumer và admin client có thể nhận cấu hình chung, đồng thời có thể có cấu hình riêng theo từng loại client. Khi dùng cấu hình riêng, cần bảo đảm không vô tình bỏ sót security protocol, SASL hoặc SSL.

Ví dụ SASL_SSL với SCRAM và TLS một chiều:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
    ssl:
      trust-store-location: file:/etc/kafka/tls/truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${KAFKA_TRUSTSTORE_PASSWORD}
      endpoint-identification-algorithm: https
~~~

Ví dụ mTLS bổ sung key store:

~~~yaml
spring:
  kafka:
    ssl:
      key-store-location: file:/etc/kafka/tls/client-keystore.p12
      key-store-type: PKCS12
      key-store-password: ${KAFKA_KEYSTORE_PASSWORD}
      key-password: ${KAFKA_KEY_PASSWORD}
~~~

Các ví dụ giả định phiên bản Spring Boot đang dùng hỗ trợ các thuộc tính trên. Khi nâng cấp Spring Boot hoặc Kafka client, hãy đối chiếu metadata cấu hình của đúng phiên bản và kiểm thử với broker thật hoặc môi trường tích hợp tương đương. Không sao chép nguyên cấu hình của một phiên bản sang phiên bản khác mà không xác minh.

Một số nguyên tắc khi đưa cấu hình vào ứng dụng:

- Chỉ khai báo một nguồn có thẩm quyền cho mỗi secret để tránh giá trị bị ghi đè khó truy vết giữa file, environment và command-line arguments.
- Không log toàn bộ Environment, Kafka properties hoặc JAAS config khi khởi động.
- Không đưa password vào exception message hoặc custom health indicator.
- Không tạo bean Kafka client riêng mà bỏ qua cấu hình bảo mật dùng chung.
- Giới hạn quyền đọc file keystore và secret; chỉ user chạy ứng dụng cần quyền đó.
- Giữ hostname verification bật và dùng certificate có SAN đúng.
- Không cấu hình trust-all, TrustManager bỏ qua xác minh hoặc endpoint identification rỗng trong production.

Nếu dùng Java code để tạo ProducerFactory, ConsumerFactory hoặc KafkaAdmin thủ công, cần kiểm tra các properties bảo mật có được chuyển tới từng client hay không. Cấu hình Boot chỉ có tác dụng với bean được Boot quản lý hoặc bean được xây dựng dựa trên cấu hình đó; một client tự khởi tạo với map rỗng có thể vô tình dùng thiết lập mặc định không phù hợp.

## 7. Chẩn đoán lỗi mà không làm lộ secret

Khi kết nối Kafka thất bại, hãy xác định lỗi xảy ra ở giai đoạn nào:

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| PKIX path building failed | Client không tìm được chuỗi CA tin cậy hoặc thiếu intermediate CA | Kiểm tra truststore, issuer và certificate chain |
| No subject alternative DNS name matching | Hostname client dùng không có trong SAN | Kiểm tra bootstrap server, advertised listener và SAN |
| Certificate expired hoặc not yet valid | Certificate hết hạn, chưa có hiệu lực hoặc clock lệch | Kiểm tra thời hạn và đồng bộ thời gian |
| Keystore password was incorrect hoặc UnrecoverableKeyException | Sai mật khẩu, alias hoặc private key entry | Kiểm tra keystore type, alias và nguồn cấp mật khẩu |
| SSLHandshakeException / handshake_failure | TLS protocol, cipher, certificate hoặc yêu cầu mTLS không khớp | Kiểm tra cấu hình hai phía và handshake |
| SaslAuthenticationException | Username/password, token, JAAS hoặc SASL mechanism không khớp | Kiểm tra secret version, cơ chế SASL và principal |
| TopicAuthorizationException | Principal đã xác thực nhưng thiếu ACL | Kiểm tra quyền topic và consumer group |

Trình tự điều tra nên đi từ ít rủi ro đến sâu hơn:

1. Ghi nhận timestamp, hostname broker, client ID, pod/instance và loại thao tác thất bại.
2. Kiểm tra secret version hoặc certificate serial đang được workload sử dụng; không in giá trị secret.
3. Kiểm tra DNS, bootstrap address và advertised listener.
4. Kiểm tra certificate chain, SAN, thời hạn và truststore bằng công cụ phù hợp.
5. Kiểm tra security protocol, SASL mechanism và principal ở cả client lẫn broker.
6. Kiểm tra ACL sau khi xác thực đã thành công.
7. Chỉ bật log TLS hoặc Kafka security chi tiết trong thời gian ngắn, ở phạm vi instance cần điều tra; giới hạn người xem và rà soát log trước khi chia sẻ.

Không xử lý lỗi bằng cách in password ra log, đưa password vào câu lệnh có thể lưu trong shell history, tắt xác minh hostname hoặc dùng trust-all. Những cách này có thể che triệu chứng nhưng làm tăng nguy cơ lộ credential hoặc chấp nhận broker giả mạo.

Sau khi khắc phục, kiểm tra lại bằng đúng runtime của ứng dụng. Một lệnh OpenSSL thành công chỉ chứng minh một đường kết nối TLS cụ thể; nó không chứng minh JAAS, SASL, ACL, truststore của JVM hoặc cấu hình Kafka client đã đúng. Cần xác nhận ứng dụng có thể tạo kết nối, xác thực và thực hiện đúng thao tác được cấp quyền.

## 8. Checklist vận hành

Trước khi triển khai:

- [ ] Mỗi ứng dụng và môi trường có principal riêng, quyền tối thiểu.
- [ ] Secret được lưu trong secret manager hoặc cơ chế được tổ chức phê duyệt.
- [ ] Repository, image, pipeline và log không chứa password, token hoặc private key.
- [ ] File keystore/truststore được phân phối có kiểm soát và giới hạn quyền đọc/ghi.
- [ ] Certificate còn hạn, SAN đúng với mọi broker hostname client sử dụng.
- [ ] Truststore chứa CA phù hợp; keystore chỉ được cấu hình khi cần mTLS.
- [ ] TLS hostname verification được bật.
- [ ] SASL mechanism và security protocol khớp với cấu hình broker.

Trong vận hành:

- [ ] Có owner, inventory và lịch cảnh báo hết hạn cho certificate.
- [ ] Có quy trình rotation cho password, token, client certificate và CA.
- [ ] Có kế hoạch rollout/restart hoặc reload Kafka client sau khi thay file TLS.
- [ ] Có thể xác định workload đang dùng phiên bản secret/certificate nào mà không đọc giá trị bí mật.
- [ ] Có audit trail cho việc đọc, thay đổi, cấp mới và thu hồi secret.
- [ ] Theo dõi lỗi TLS, SASL authentication và ACL authorization riêng biệt.

Khi có sự cố lộ secret:

1. Thu hồi hoặc vô hiệu hóa credential bị lộ theo mức độ khẩn cấp.
2. Cấp credential mới và triển khai tới workload hợp lệ.
3. Kiểm tra audit log để xác định phạm vi truy cập và dấu hiệu sử dụng bất thường.
4. Xác minh client cũ không còn kết nối bằng credential đã thu hồi.
5. Xử lý bản sao secret trong repository, artifact, log hoặc hệ thống lưu trữ liên quan theo quy trình ứng phó sự cố.
6. Ghi lại nguyên nhân và cập nhật quy trình cấp phát để tránh lặp lại.

## 9. Kết luận vận hành

Bảo vệ secret và certificate trong Spring Kafka cần được xem là một vòng đời: cấp phát đúng danh tính, lưu trữ có kiểm soát, đưa cấu hình vào Kafka client an toàn, theo dõi hạn dùng, xoay vòng có giai đoạn chuyển tiếp và thu hồi khi không còn cần thiết hoặc khi có sự cố. TLS bảo vệ kênh truyền và danh tính broker; mTLS có thể xác minh thêm client; SASL xác thực principal; ACL giới hạn hành động principal được phép thực hiện. Khi các lớp này được cấu hình và vận hành riêng rẽ, đội ngũ có thể xử lý lỗi chính xác mà không phải nới lỏng bảo mật để khôi phục kết nối.
