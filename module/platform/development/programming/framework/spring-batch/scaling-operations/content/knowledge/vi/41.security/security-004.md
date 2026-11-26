# Mutual TLS cho remote execution trong Spring Batch

## 1. Mục tiêu và bối cảnh

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, Spring Batch được mở rộng để xử lý workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và những mô hình phân tán như **remote partitioning** hoặc **remote chunking**. Khi manager và worker chạy trên các máy hoặc container khác nhau, đường điều phối job trở thành một phần của bề mặt tấn công: kẻ không được phép có thể giả danh worker, đọc dữ liệu trên đường truyền hoặc gửi thông điệp điều phối trái phép.

**Mutual TLS (mTLS)** là cơ chế bảo mật đường truyền trong đó **cả hai phía của một kết nối TLS đều xác thực chứng chỉ của phía kia**. Trong TLS một chiều thông thường, client xác minh danh tính server; với mTLS, server còn yêu cầu client trình chứng chỉ hợp lệ. Sau bắt tay TLS thành công, các dữ liệu gửi qua kết nối được bảo vệ bằng mã hóa và kiểm tra tính toàn vẹn.

Trong triển khai Spring Batch phân tán, mTLS thường được áp dụng cho **kết nối từ manager/worker đến message broker**, hoặc cho **kết nối HTTP/gRPC trực tiếp** nếu hệ thống tự xây dựng giao thức điều phối. Spring Batch không có một cờ cấu hình chung tên "bật mTLS cho mọi remote execution": cách cấu hình nằm tại **transport thực tế** như AMQP/RabbitMQ, Kafka, JMS, HTTP client/server hoặc service mesh.

Sau bài học, bạn có thể:

- Xác định các điểm kết nối cần mTLS trong remote partitioning và remote chunking.
- Giải thích vai trò của CA, server/client certificate, private key, truststore và keystore.
- Cấu hình mTLS cho một topology dùng Spring Batch, Spring Integration và RabbitMQ.
- Tách biệt xác thực kết nối với phân quyền message broker và quyền truy cập JobRepository.
- Kiểm thử kết nối hợp lệ, chứng chỉ sai/hết hạn/sai hostname, thiếu quyền và lỗi khôi phục.
- Lập kế hoạch cấp phát, giám sát, xoay vòng chứng chỉ và triển khai nhiều worker an toàn.

## 2. TLS một chiều và mTLS khác nhau ra sao?

| Tiêu chí | TLS một chiều | mTLS |
|---|---|---|
| Client kiểm tra server certificate | Có, nếu bật xác minh đúng | Có, bắt buộc kiểm tra đúng |
| Server kiểm tra client certificate | Không bắt buộc | Có, bắt buộc |
| Mã hóa và toàn vẹn đường truyền | Có | Có |
| Danh tính client ở tầng TLS | Chưa được xác thực bằng certificate | Được xác thực bằng certificate đã tin cậy |
| Phân quyền queue, job, dữ liệu | Vẫn cần cơ chế riêng | Vẫn cần cơ chế riêng |
| Ngăn xử lý trùng do redelivery/retry | Không | Không |

Một worker có chứng chỉ hợp lệ của tổ chức vẫn **không mặc nhiên được phép** tiêu thụ mọi queue. Sau TLS handshake, broker vẫn cần kiểm tra account hoặc identity được ánh xạ từ chứng chỉ và quyền **read/write/configure** đối với exchange, queue và virtual host.

mTLS giảm nguy cơ nghe lén, giả mạo endpoint và tấn công xen giữa ở đường truyền được bảo vệ. Nó **không thay thế** xác thực người khởi chạy job, phân quyền business operation, mã hóa dữ liệu khi lưu, idempotency, retry policy hay kiểm soát tài nguyên CPU/JDBC.

## 3. Đặt đúng ranh giới bảo vệ trong remote execution

### 3.1. Remote partitioning qua broker

Trong mô hình remote partitioning phổ biến với Spring Batch Integration, **manager** chia công việc thành các partition, gửi yêu cầu chạy StepExecution qua messaging; **worker** lấy thông tin partition, chạy worker step và gửi phản hồi. Tùy cấu hình, manager và worker truy cập cùng **JobRepository** để đọc và cập nhật metadata.

~~~mermaid
flowchart LR
    M[Spring Batch Manager] <-->|TLS + client cert M| B[(AMQP Broker)]
    B <-->|TLS + client cert W| W[Spring Batch Worker]
    M <-->|DB TLS độc lập| DB[(JobRepository)]
    W <-->|DB TLS độc lập| DB
~~~

**Điểm quan trọng:** Trong topology qua broker, mTLS xác thực từng kết nối **manager ↔ broker** và **worker ↔ broker**. Manager và worker **không trực tiếp xác thực certificate của nhau** chỉ nhờ bật mTLS trên hai kết nối này. Broker có thể giải mã thông điệp ở điểm kết thúc TLS rồi chuyển tiếp qua phiên kết nối TLS khác. Nếu cần bảo mật nội dung xuyên suốt từ manager đến worker ngay cả khi broker bị xâm nhập, phải đánh giá thêm mã hóa/chữ ký cấp message hoặc kiến trúc khác.

Khi worker cần truy cập metadata database, TLS/mTLS của broker **không bảo vệ** đường nối tới JobRepository. Hãy thiết kế TLS, identity, quyền database, network policy và cách quản lý bí mật cho đường DB riêng.

### 3.2. Remote chunking

Trong remote chunking, manager thường đọc và gửi **items/chunk request** qua broker, worker xử lý và ghi dữ liệu rồi trả chunk response. Vì payload có thể chứa dữ liệu nghiệp vụ, yêu cầu bảo vệ broker, queue, storage, log và đường mạng càng đáng chú ý.

Nếu broker lưu message ra đĩa hoặc người vận hành có quyền truy cập queue, mTLS chỉ mã hóa **dữ liệu đang truyền trên từng kết nối**, không mã hóa mặc định dữ liệu **đang lưu** trong broker. Cần cân nhắc data-at-rest encryption, giới hạn retention, DLQ, log masking và ACL.

### 3.3. Điều phối trực tiếp qua HTTP hoặc service mesh

Một ứng dụng có thể tự thiết kế remote worker API qua HTTP/gRPC. Khi đó manager là TLS client, worker là TLS server; worker phải yêu cầu client certificate và manager phải xác minh server certificate. Trong service mesh, sidecar/proxy có thể thực hiện mTLS thay cho ứng dụng. Cần xác định **TLS kết thúc tại proxy hay tại ứng dụng**, chính sách giữa sidecar và process và identity mà policy engine thật sự kiểm tra.

Không suy luận rằng dùng Kubernetes, private VPC hay service mesh thì mọi kết nối broker, database, actuator và callback đều đã có mTLS. Mỗi luồng phải được xác minh bằng cấu hình và phép thử thực tế.

## 4. Những thành phần tạo nên một phiên mTLS

| Thành phần | Chức năng | Vị trí/đối tượng điển hình |
|---|---|---|
| **Certificate Authority (CA)** | Ký và tạo chuỗi tin cậy cho certificate | PKI nội bộ, doanh nghiệp hoặc CA được quản lý |
| **Server certificate** | Chứng minh endpoint broker/worker API là đúng server | Broker TLS listener hoặc HTTP server |
| **Client certificate** | Chứng minh identity của manager hoặc worker | Manager/worker TLS client |
| **Private key** | Chứng minh quyền sở hữu public key khi bắt tay TLS; phải giữ bí mật | Secret manager, volume có quyền truy cập hạn chế |
| **Truststore** | Chứa CA/certificate được phép dùng để xác minh peer | Client tin broker; broker tin CA cấp client cert |
| **Keystore** | Chứa certificate chain và private key của chính endpoint | Client manager/worker; server broker |
| **SAN (Subject Alternative Name)** | Gắn danh tính DNS/IP được phép cho server certificate | DNS broker trong cấu hình kết nối |
| **Certificate policy** | Thời hạn, EKU, key usage, thuật toán và vòng đời chứng chỉ | PKI + quy trình vận hành |

Thông thường client sẽ dùng **truststore** để kiểm tra certificate chain của broker và **keystore** để trình danh tính của chính nó. Phía broker dùng server certificate/private key của broker và CA được tin cậy để xác minh client certificate.

Đối với server certificate, **SAN phải khớp hostname được client dùng để kết nối**, nếu client dùng DNS; chỉ đặt một Common Name gần giống DNS không đủ cho kiểm tra hostname hiện đại. Certificate cũng phải còn hạn, có chuỗi CA hợp lệ và extension phù hợp, ví dụ **serverAuth** cho server hoặc **clientAuth** cho client khi PKI/transport yêu cầu.

Chỉ nên tin các CA cần thiết cho mục đích cụ thể. Nếu dùng cùng một CA phát hành mọi certificate nhưng không có cơ chế authorization sau TLS, một client hợp lệ của dịch vụ khác có thể vượt qua kiểm tra *certificate trusted* dù không được phép chạy batch. Vì thế nên thiết kế **identity riêng cho manager, worker** và chính sách broker giới hạn quyền theo identity.

## 5. Mô hình đe dọa và quyền hạn

| Nguy cơ | mTLS giúp gì? | Biện pháp còn cần thiết |
|---|---|---|
| Nghe lén request/reply giữa client và broker | Mã hóa dữ liệu trên kết nối TLS | Bảo vệ broker storage, DLQ và log chứa payload |
| Giả mạo broker hoặc tấn công trung gian | Xác minh CA chain và hostname của server | Không tắt xác minh hostname/certificate |
| Client ngoài tổ chức kết nối broker | Broker chỉ nhận client cert thuộc nhóm tin cậy | Xác thực account/cert mapping và ACL từng queue |
| Worker hợp lệ tiêu thụ sai workload | Chứng minh danh tính ở mức kết nối | Tách virtual host, destination và phân quyền theo role |
| Gửi lại message đã xử lý | Không giải quyết | Idempotent writer, deduplication, transaction/restart |
| Lộ private key từ pod/secret | Certificate có thể bị giả mạo tới lúc thu hồi/hết hạn | Secret access control, rotation, revocation, audit |
| JobRepository bị truy cập trái phép | Không bảo vệ DB chỉ bằng broker mTLS | DB TLS, quyền DB tối thiểu, network policy, secrets |
| Quá tải worker hoặc retry storm | Không giải quyết | Concurrency limit, queue capacity, backoff và quan sát tài nguyên |

Remote execution của Spring Batch thường là việc **worker chạy step đã được ứng dụng đăng ký**, không phải trao quyền chạy lệnh tùy ý trên hệ điều hành. Dù vậy, một message điều phối bị chấp nhận sai vẫn có thể kích hoạt xử lý dữ liệu không được phép hoặc gây quá tải.

## 6. Trình tự TLS handshake và xác thực quyền

Trong ví dụ dùng AMQP TLS, luồng xử lý ở mức khái niệm như sau:

~~~mermaid
sequenceDiagram
    participant M as Manager client
    participant B as Broker server
    M->>B: ClientHello / TLS negotiation
    B-->>M: Server certificate và yêu cầu client certificate
    Note over M: Kiểm tra CA, hostname/SAN, thời hạn, policy
    M->>B: Client certificate và chứng minh có private key
    Note over B: Kiểm tra chain, thời hạn, EKU và danh tính client
    B-->>M: TLS handshake thành công
    M->>B: AMQP authentication và publish request
    Note over B: Kiểm tra quyền vhost, exchange và queue
    B-->>M: Chấp nhận hoặc từ chối operation
~~~

TLS và AMQP authentication có thể dùng cơ chế ánh xạ client certificate (ví dụ SASL EXTERNAL khi được bật/cấu hình) hoặc một account riêng sau TLS. **Có mTLS không tự động có SASL EXTERNAL**, và không tự động cấp quyền đọc/ghi queue. Đây là hai quyết định cấu hình độc lập.

Nếu worker kết nối broker bằng một identity riêng, quy trình handshake diễn ra tương tự. Việc manager và worker dùng cùng trust root không làm hai identity trở nên tương đương về quyền.

## 7. Thiết kế identity, chứng chỉ và trust

Một thiết kế cụ thể cho ứng dụng nhập dữ liệu:

| Endpoint | Danh tính certificate | Trust cần có | Quyền nghiệp vụ tối thiểu |
|---|---|---|---|
| Broker AMQP | DNS **batch-broker.internal.example** trong SAN, serverAuth | CA đã cấp client cert hợp lệ | Chỉ mở TLS listener cần thiết |
| Manager replica | Identity **batch-import-manager**, clientAuth | CA chứng nhận broker | Publish request, consume reply tương ứng |
| Worker replica | Identity **batch-import-worker**, clientAuth | CA chứng nhận broker | Consume request, publish reply tương ứng |
| JobRepository DB | Server identity của DB; client identity nếu DB bật mTLS | Theo chính sách PKI của DB | Chỉ những quyền DB mà tiến trình thực sự cần |

Nếu nhiều worker sử dụng chung identity certificate, broker khó phân biệt hoặc thu hồi **từng replica**. Có thể phát hành identity riêng theo workload/service account và thậm chí theo instance nếu chính sách yêu cầu; cần cân bằng khả năng quan sát, quản lý key và tốc độ rotation.

Các điểm cần thống nhất từ trước:

1. **Trust boundary:** CA cấp cho server, CA cấp client, có cần tách root/intermediate theo môi trường dev/staging/production hay không.
2. **Subject/SAN:** DNS server, URI/SPIFFE ID hoặc thuộc tính danh tính client mà broker/policy engine thực sự dùng; đừng dựa vào tên certificate tùy ý.
3. **Key material:** định dạng PKCS#12/PEM, thuật toán/độ dài khóa được chính sách hỗ trợ, lưu ở đâu và ai được đọc.
4. **Thu hồi:** cách xử lý khi key lộ; cơ chế CRL/OCSP hoặc thu hồi cấp quyền/broker identity phù hợp hệ thống. TLS không mặc định kiểm tra thu hồi trong mọi runtime.
5. **Vòng đời:** ai cấp, ngày hết hạn, cảnh báo, rotation và thủ tục khôi phục khi CA/certificate gặp sự cố.

## 8. Ví dụ cấu hình mTLS với RabbitMQ

Ví dụ dùng Spring Batch + Spring Integration AMQP, manager và worker giao tiếp qua RabbitMQ. Đây là cấu hình **minh họa** cho topology được mô tả, cần điều chỉnh đường dẫn, credential, phiên bản Spring Boot/Spring AMQP và cách triển khai thực tế.

### 8.1. Phía RabbitMQ: bật TLS listener và yêu cầu client certificate

Trong cấu hình **rabbitmq.conf** của broker:

~~~properties
listeners.ssl.default = 5671

ssl_options.cacertfile = /etc/rabbitmq/tls/client-ca-chain.pem
ssl_options.certfile = /etc/rabbitmq/tls/broker.crt
ssl_options.keyfile = /etc/rabbitmq/tls/broker.key
ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = true
~~~

Ý nghĩa:

- **listeners.ssl.default** mở cổng AMQP qua TLS; trong ví dụ là 5671.
- **cacertfile** chứa CA chain dùng để xác minh certificate của client.
- **certfile/keyfile** là danh tính TLS của broker.
- **verify_peer** bật kiểm tra chứng chỉ phía đối tác; **fail_if_no_peer_cert = true** buộc client có certificate. Nếu bỏ yêu cầu certificate, hệ thống có thể chỉ đạt TLS một chiều.

Đồng thời cần kiểm tra broker có còn mở AMQP plaintext listener ở cổng 5672 không. Đối với môi trường yêu cầu tất cả traffic được mã hóa, hãy **vô hiệu hóa hoặc chặn cổng plaintext** theo cấu hình/network policy thực tế. Phân biệt chứng chỉ cho node-to-node clustering, management UI và AMQP listener: bảo vệ một listener không tự động bảo vệ các listener còn lại.

### 8.2. Phía manager: Spring Boot RabbitMQ client

Trong **application.yml** của manager, có thể dùng khóa TLS của Spring Boot để cấu hình RabbitMQ client. Keystore chứa client certificate/private key của manager; truststore chứa CA tin cậy cho broker.

~~~yaml
spring:
  rabbitmq:
    host: batch-broker.internal.example
    port: 5671
    username: ${BATCH_RABBIT_USERNAME}
    password: ${BATCH_RABBIT_PASSWORD}
    ssl:
      enabled: true
      key-store: file:/etc/batch/tls/manager-identity.p12
      key-store-type: PKCS12
      key-store-password: ${BATCH_KEYSTORE_PASSWORD}
      trust-store: file:/etc/batch/tls/broker-trust.p12
      trust-store-type: PKCS12
      trust-store-password: ${BATCH_TRUSTSTORE_PASSWORD}
~~~

Phải xác minh **server certificate chain và hostname** bằng các thuộc tính/API được hỗ trợ ở phiên bản Spring Boot/Spring AMQP/RabbitMQ client đang dùng. Không bật chế độ trust-all, không tắt hostname verification để chữa lỗi certificate. Nếu hostname không khớp SAN, hãy sửa DNS/certificate hoặc endpoint cấu hình cho chính xác.

### 8.3. Phía worker: dùng identity khác với manager

Worker dùng cấu hình transport tương tự nhưng có client certificate và account riêng:

~~~yaml
spring:
  rabbitmq:
    host: batch-broker.internal.example
    port: 5671
    username: ${WORKER_RABBIT_USERNAME}
    password: ${WORKER_RABBIT_PASSWORD}
    ssl:
      enabled: true
      key-store: file:/etc/batch/tls/worker-identity.p12
      key-store-type: PKCS12
      key-store-password: ${WORKER_KEYSTORE_PASSWORD}
      trust-store: file:/etc/batch/tls/broker-trust.p12
      trust-store-type: PKCS12
      trust-store-password: ${WORKER_TRUSTSTORE_PASSWORD}
~~~

Hai service có thể cùng tin CA cấp broker nhưng **không nên mặc định dùng chung private key**. Trên Kubernetes, mount secret dưới dạng volume chỉ đọc vào container liên quan; cấu hình quyền tệp và service account để giới hạn ai có thể đọc private key. Secret password nên được cấp qua secret manager/Kubernetes Secret hoặc cơ chế quản lý bí mật được phê duyệt, tránh commit vào Git hoặc in ra log.

**Lưu ý phiên bản:** tên thuộc tính, API cấu hình SSL bundle, cách kiểm tra hostname và hỗ trợ certificate format có thể khác nhau giữa các thế hệ Spring Boot/Spring AMQP. Ví dụ trên thể hiện cấu hình thường gặp cho RabbitMQ client dựa trên keystore/truststore; khi dùng SSL bundle hoặc custom ConnectionFactory, phải kiểm tra cấu hình hiệu lực trên instance thực sự tạo kết nối.

### 8.4. Chứng chỉ: tạo PKCS#12 từ certificate và private key đã được cấp

Sau khi CA đã cấp **client certificate hợp lệ** cho manager, có thể đóng gói certificate chain và private key thành keystore PKCS#12. Ví dụ trên môi trường quản trị an toàn:

~~~bash
openssl pkcs12 -export \
  -in manager.crt \
  -inkey manager.key \
  -certfile client-ca-chain.pem \
  -out manager-identity.p12 \
  -name batch-manager
~~~

Công cụ yêu cầu passphrase khi tạo tệp; trong quy trình thực tế, **tránh nhập passphrase dưới dạng literal trong shell history hoặc CI logs**. Có thể dùng secret manager hoặc công cụ cấp phát certificate để hạn chế lộ thông tin. File manager.key và manager-identity.p12 đều chứa vật liệu nhạy cảm: giới hạn quyền đọc và xử lý bản tạm theo chính sách của tổ chức.

Truststore của client phải chứa CA phù hợp để xác minh broker. Nếu có intermediate CA, cần chuỗi chứng chỉ nhất quán và đúng chính sách xác minh của runtime. **Không đưa private key của CA vào container**.

## 9. Cấp quyền broker sau khi đã xác thực mTLS

Một kết nối mTLS hợp lệ chưa chứng minh manager được publish vào mọi exchange hoặc worker được đọc mọi queue. Nên áp dụng **least privilege** theo chiều dữ liệu:

| Role | Hoạt động thường cần | Hoạt động nên bị giới hạn |
|---|---|---|
| Manager | Publish request đến exchange/routing key được phép, consume reply | Consume queue của workload khác, quản trị user/vhost |
| Worker | Consume request, publish reply | Đọc reply của manager khác, publish job trái phép |
| Provisioning/operations | Khai báo exchange/queue/binding theo pipeline được kiểm soát | Không dùng credential quản trị cho tất cả worker |

RabbitMQ có các quyền **configure, write, read** theo vhost và tên resource, cùng cơ chế xác thực người dùng/certificate tùy cấu hình. Hãy thử quyền bằng kết nối của đúng role, vì một số ứng dụng tự declare exchange/queue khi khởi động và có thể cần quyền configure; nếu muốn giảm quyền runtime, nên provision topology trước bằng identity chuyên trách.

Nếu dùng SASL EXTERNAL để ánh xạ client cert thành user, phải cấu hình plugin/cơ chế auth phù hợp tại broker và chính sách mapping certificate. Nếu dùng username/password cùng mTLS như ví dụ, TLS xác thực kết nối bằng client cert còn account kiểm soát quyền AMQP. Không nên hiểu hai cơ chế này là thay thế hoàn toàn cho nhau.

Ngoài ACL, có thể tách vhost và bộ destination theo môi trường, tenant hoặc nhóm workload. Đảm bảo worker không vô tình subscribe queue của deployment/version khác.

## 10. Kiểm thử handshake và quyền truy cập

### 10.1. Kiểm tra kết nối TLS bằng công cụ độc lập

Trong môi trường test, dùng bộ certificate của một client test được phép truy cập broker:

~~~bash
openssl s_client \
  -connect batch-broker.internal.example:5671 \
  -servername batch-broker.internal.example \
  -verify_hostname batch-broker.internal.example \
  -CAfile broker-ca-chain.pem \
  -cert client-test.crt \
  -key client-test.key \
  -verify_return_error
~~~

Kết quả cần kiểm tra: TLS handshake thành công, certificate chain được xác minh, hostname trong SAN khớp, TLS version/cipher thuộc danh sách cho phép và broker thực sự yêu cầu client certificate. **Handshake thành công chưa chứng minh AMQP authorization hoặc xử lý StepExecution thành công**, vì lệnh trên không gửi đủ thao tác AMQP application-level.

Khi kiểm thử lỗi, tránh cách chỉ xem exit code của pipeline shell; cần đọc trạng thái verify và thông báo lỗi từ chính công cụ. Không đưa private key hoặc toàn bộ nội dung secret vào ticket/log.

### 10.2. Ma trận kiểm thử dương và âm

| Kịch bản | Tác động kiểm thử | Kỳ vọng |
|---|---|---|
| Manager certificate hợp lệ | Kết nối đến đúng broker, publish request | TLS thành công và AMQP publish được cấp quyền |
| Worker certificate hợp lệ | Connect, consume request và publish reply | Handshake, auth và xử lý đúng một công việc test |
| Không trình client certificate | Broker được cấu hình bắt buộc mTLS | Kết nối bị từ chối ở handshake/auth phù hợp |
| Client cert do CA lạ cấp | Trust root broker không có CA đó | Kết nối bị từ chối |
| Client cert hết hạn/chưa có hiệu lực | Dùng cert test sai thời hạn | Handshake hoặc bước kiểm tra policy từ chối |
| Broker certificate sai SAN | Hostname kết nối khác SAN của cert | Client không kết nối thành công khi hostname verification được bật |
| Broker CA không được tin | Truststore client không có CA phù hợp | Client từ chối kết nối |
| Client cert hợp lệ nhưng thiếu ACL | Kết nối bằng identity role khác | TLS có thể thành công nhưng AMQP operation bị từ chối |
| CA/client cert rotation | Thay certificate trong cửa sổ có bản cũ và bản mới | Kết nối mới dùng cert mới, job không mất/trùng khi reconnect |
| Worker restart giữa chunk/partition | Ngắt worker test khi đang chạy | Message/state được recovery theo policy; đầu ra không trùng/thiếu |

Kiểm tra thêm worker đang dùng **đúng key/cert** khi có nhiều instance; một pod dùng secret cũ có thể vẫn kết nối, trong khi pod mới hết hạn certificate và liên tục crash/reconnect.

## 11. TLS cho JobRepository và hệ thống phụ thuộc

Trong remote partitioning, manager và worker thường chia sẻ kho metadata Spring Batch. Vì vậy ngoài broker TLS cần xác định:

- DB driver kết nối qua TLS, xác minh CA/hostname của database, và có client certificate nếu DB yêu cầu mTLS.
- Mỗi workload dùng DB credential và quyền tối thiểu; việc dùng chung schema metadata được kiểm soát theo thiết kế JobRepository.
- Password, certificate, JDBC URL và cấu hình TLS được cấp an toàn cho worker replica.
- Endpoint API mà processor/writer gọi cũng có chính sách TLS/mTLS phù hợp nếu dữ liệu nhạy cảm.
- Không ghi tràn ExecutionContext/JobParameters, payload message hoặc private key vào logs/traces.

**Không nhầm mTLS với retry/restart.** Sau mất kết nối broker, một request/reply có thể được giao lại hoặc thất lạc tùy transport và ack/transaction policy. Dữ liệu đã commit có thể không trùng khớp với trạng thái message. Cần thiết kế **idempotency**, checkpoint, transaction boundary và giám sát JobRepository độc lập với kết quả TLS handshake.

## 12. Hiệu năng: chi phí bảo mật và cách đo

mTLS bổ sung bước xác minh certificate và mật mã trong quá trình bắt tay kết nối. Chi phí này thường đáng chú ý nhất khi ứng dụng **liên tục tạo và hủy kết nối**, không phải cứ mỗi chunk lại có một TLS handshake nếu transport tái sử dụng kết nối.

Với hệ thống batch throughput lớn, đo:

| Nhóm metric | Ý nghĩa |
|---|---|
| Handshake duration/failure | Có chi phí thiết lập mới hoặc lỗi CA/certificate/hostname không |
| Kết nối mở/reconnect rate | Worker có liên tục mở kết nối và làm quá tải broker không |
| CPU client và broker | Chi phí mã hóa, xử lý TLS và message |
| AMQP request/reply latency | Có tăng thời gian phân phối hoặc nhận phản hồi không |
| Queue depth và redelivery | Có backlog, retry storm hoặc message không được ack không |
| Throughput item/s, p95 chunk, commit/rollback | Độ trễ TLS ảnh hưởng vận hành job thế nào |
| JDBC pool/DB latency, heap/GC | Có nút thắt từ phía xử lý khác đang che khuất tác động TLS không |

Giữ nguyên **dataset, chunk size, worker concurrency, broker placement, network và JVM resources** khi so sánh các cấu hình TLS. Không giảm xác minh certificate hoặc hostname để tăng thông lượng. Ưu tiên **tái sử dụng kết nối/channel hợp lý**, tránh tạo connection trên từng item/chunk, giảm kích thước payload không cần thiết và điều chỉnh parallelism theo giới hạn CPU/JDBC thực tế.

Khi nâng số worker, broker phải xử lý nhiều TLS client connection, heartbeat và message. Kiểm tra connection limit, CPU, memory broker, file descriptors và network policy. Certificate mới được dùng tại thời điểm tạo/kết nối lại TLS session; chỉ thay file secret chưa chắc làm **kết nối đang mở** dùng certificate mới.

## 13. Rotation và quản lý vòng đời certificate

Certificate có thời hạn và có thể bị thu hồi. Trong workload batch, một job có thể chạy hàng giờ; triển khai lại tất cả worker không có kế hoạch có thể ngắt nhiều partition/chunk đang xử lý.

### 13.1. Quy trình xoay vòng an toàn

1. **Kiểm kê:** thống kê identity, CA, SAN, ngày hết hạn, service/namespace, secret mount, replica và destination mà certificate đang phục vụ.
2. **Cập nhật trust trước:** khi đổi CA, đưa root/intermediate CA mới vào truststore của các đối tác cần thiết và duy trì CA cũ trong cửa sổ chuyển tiếp được chấp nhận.
3. **Cấp cert mới:** tạo private key mới, certificate chain hợp lệ, EKU/SAN đúng, bảo đảm broker chấp nhận identity và ACL.
4. **Canary:** thử một manager/worker replica với certificate mới qua kết nối thực, xác minh publish/consume/reply và trạng thái JobRepository.
5. **Roll theo nhóm:** giảm hoặc drain công việc của replica sắp đổi certificate, thay secret/restart/reconnect theo khả năng reload được hỗ trợ; giám sát in-flight/ack/retry.
6. **Kiểm tra toàn bộ:** bảo đảm mọi kết nối mới dùng certificate mới; không còn replica phụ thuộc CA cũ và không có message/StepExecution bị bỏ quên.
7. **Thu hẹp trust:** gỡ CA cũ khỏi truststore khi đã an toàn, thu hồi/khóa credential cũ và lưu audit của lần rotation.

Việc CA cũ và mới cùng được tin trong một thời gian không đồng nghĩa bỏ qua xác minh chain hoặc hostname. Nếu có sự cố lộ private key, quy trình ứng cứu có thể yêu cầu thu hồi/khóa ngay thay vì một giai đoạn chuyển tiếp dài.

### 13.2. Kubernetes và long-lived connection

Khi dùng Kubernetes Secret/CSI/secret manager:

- Mount certificate dưới quyền đọc tối thiểu, tách secret cho manager và worker.
- Xác định bản ứng dụng/broker có **reload TLS material tự động** hay chỉ nạp keystore tại startup. Secret thay đổi trên volume không bảo đảm ConnectionFactory cập nhật key và trust ngay.
- Sau rotation, cần tạo kết nối mới có kiểm soát để kiểm tra certificate đang dùng; cân nhắc drain, rolling restart và cách khôi phục những partition/chunk chưa ack.
- Liveness/readiness chỉ cho thấy process có đáp ứng một số kiểm tra; thiết kế health check hoặc canary **thực hiện kết nối broker với identity đúng** để phát hiện lỗi certificate và ACL.
- Đồng bộ thời gian máy/nút: sai lệch clock có thể làm certificate bị xem là chưa có hiệu lực hoặc đã hết hạn.

### 13.3. Cảnh báo trước khi hết hạn

Nên đặt cảnh báo nhiều ngưỡng (ví dụ 30 ngày, 14 ngày, 7 ngày tùy thời gian cấp phát), giám sát certificate trên **từng endpoint**, bao gồm broker và client replicas. Với kết nối sống lâu, không nên chỉ nhìn metric số kết nối hiện đang thành công: khi certificate hết hạn, lỗi có thể xuất hiện lúc broker restart hoặc worker reconnect sau đó.

## 14. Chẩn đoán lỗi mTLS thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **PKIX path building failed / unknown CA** | Truststore thiếu CA hoặc chain không đủ | Chain thực tế của broker, CA trust của client, intermediate |
| **Hostname verification failed** | Kết nối bằng IP/alias không có trong SAN | DNS, endpoint, SAN và cấu hình hostname verification |
| **Bad certificate / certificate required** | Client thiếu cert, cert không được broker tin hoặc sai key usage | Broker yêu cầu client cert, cert chain, EKU/clientAuth, key |
| **Certificate expired/not yet valid** | Cert hết hạn hoặc clock sai | NotBefore/NotAfter, NTP, replica đang dùng cert nào |
| **UnrecoverableKeyException / keystore error** | Keystore sai mật khẩu, định dạng, alias hoặc key không khớp | Mount, password secret, PKCS12, certificate/private key |
| **TLS handshake OK nhưng ACCESS_REFUSED** | User/cert mapping hoặc ACL sai | Vhost, read/write/configure và broker authentication |
| **Connection reset / reconnect loop** | Network, broker limit, TLS policy mismatch, cert rotation lỗi | Broker/client log, network policy, TLS version và cipher |
| **Worker nhận request nhưng job FAILED** | Logic step, JobRepository, idempotency hoặc downstream | StepExecution, ExecutionContext, JDBC, business output |
| **Một số pod chạy được, pod khác lỗi** | Khác secret/CA/config version hoặc thời gian triển khai | Pod image, secret mount, certificate fingerprint và expiry |

Các error class/chuỗi log thay đổi theo Java provider, RabbitMQ client và phiên bản thư viện; hãy dùng **bằng chứng từ cả client lẫn broker**. Khi phát hiện lỗi handshake, đừng sửa nhanh bằng cách tắt certificate validation, cho phép mọi client certificate hoặc quay về AMQP plaintext.

## 15. Runbook khi mTLS làm gián đoạn remote execution

1. **Giới hạn tác động:** tạm dừng khởi chạy job mới nếu manager không thể publish; xem worker nào đang chạy và request/reply còn tồn tại trên broker.
2. **Xác định điểm lỗi:** manager → broker, worker → broker, HTTP trực tiếp hay đường DB. Thu thập timestamp, deployment version, certificate expiry, correlation/StepExecution ID và số reconnect.
3. **So sánh với cấu hình hợp lệ:** CA chain, DNS/SAN, key/trust store, identity client, ACL và TLS policy giữa bản cũ/bản mới.
4. **Khôi phục đường kết nối an toàn:** sửa certificate, trust hoặc ACL, triển khai/reconnect có kiểm soát. Không xóa bừa queue/DLQ hoặc sửa thủ công trạng thái JobRepository.
5. **Đối soát tiến độ:** xác định StepExecution đang chạy/dừng/lỗi, commit/rollback, in-flight message, ack và replay. Restart đúng JobInstance theo cơ chế Spring Batch khi cần.
6. **Kiểm chứng:** chạy canary, kiểm tra cả TLS handshake và quyền publish/consume/reply; đối soát số item, khóa nghiệp vụ và side effect tránh mất/trùng.
7. **Mở tải dần:** quan sát TLS failures, broker lag, retry, CPU, JDBC và throughput; hoàn tất bản ghi sự cố, cải thiện cảnh báo rotation.

Trong remote partitioning, worker có thể đã ghi dữ liệu nhưng manager chưa kịp nhận reply do lỗi kết nối. Trong remote chunking, chunk response có thể mất hoặc message bị redeliver. **mTLS chỉ bảo vệ truyền thông**, còn kết quả phục hồi chính xác phụ thuộc trạng thái commit/checkpoint, ack policy và idempotency của writer.

## 16. Bài thực hành: bảo vệ một hệ thống remote partitioning

**Bối cảnh:** Một hệ thống chạy manager và 8 worker trên Kubernetes, sử dụng Spring Batch Integration với RabbitMQ và PostgreSQL JobRepository. Mỗi job import 3 triệu bản ghi và được chia thành 32 partition. Nhóm đang dùng AMQP plaintext trên cổng 5672 và muốn chuyển sang mTLS mà vẫn bảo đảm khả năng restart.

Hãy thực hiện trong **staging**, với chứng chỉ thử nghiệm do CA hợp lệ của môi trường phát hành:

1. Vẽ sơ đồ tất cả các kết nối manager/worker ↔ broker, manager/worker ↔ PostgreSQL và dịch vụ API được processor gọi. Chọn kết nối phải có TLS hoặc mTLS và nêu ranh giới tin cậy ở từng nơi.
2. Tạo server certificate có SAN đúng DNS RabbitMQ và client identity riêng cho manager/worker. Cấu hình RabbitMQ listener 5671 bắt buộc client certificate, đồng thời khóa đường truy cập plaintext không còn được phép.
3. Mount keystore/truststore vào từng ứng dụng, inject password qua secret, kiểm tra chain/hostname thực sự được xác minh và thiết lập ACL theo role.
4. Chạy test TLS hợp lệ, thiếu client cert, sai CA, sai SAN, certificate expired, client hợp lệ nhưng không có quyền consume/publish.
5. Khởi chạy job và kiểm tra request/reply cùng trạng thái StepExecution. Ngắt kết nối của một worker trong lúc chạy rồi khôi phục; đối soát số record, duplicate business key và khả năng restart.
6. Giả lập việc rotation certificate của một worker replica; xác nhận replica mới hoạt động, các task đang xử lý được drain hoặc phục hồi đúng và không còn kết nối dùng cert bị thu hồi.
7. So sánh CPU broker, reconnect rate, throughput, p95 chunk và JDBC pending trước/sau chuyển đổi dưới cùng workload. Đề xuất ngưỡng cảnh báo cert expiry và TLS handshake failure.

### Câu hỏi tự kiểm tra

- Nếu manager và worker đều dùng mTLS tới RabbitMQ, chúng đã xác thực certificate của nhau trực tiếp chưa? Vì sao?
- Vì sao một worker có certificate hợp lệ vẫn phải bị từ chối khi cố consume queue của tenant khác?
- Chỉ thay Secret của worker trên Kubernetes có đủ để mọi kết nối TLS hiện hữu lập tức dùng certificate mới không?
- Nếu worker đã commit dữ liệu nhưng reply bị mất do mạng, điều gì giúp tránh ghi trùng sau redelivery?
- Khi client báo hostname mismatch, vì sao không nên tắt hostname verification để job tiếp tục chạy?
- Cần thêm cấu hình nào để dữ liệu trên đường tới JobRepository được bảo vệ?

## 17. Checklist trước khi triển khai production

- [ ] Lập bản đồ mọi kết nối giữa manager, worker, broker, JobRepository và dịch vụ ngoài.
- [ ] Xác định chính xác vị trí TLS termination, có hay không TLS hop-to-hop hoặc mTLS trực tiếp.
- [ ] Broker yêu cầu client certificate, client xác minh CA chain và **hostname/SAN** của broker.
- [ ] Manager và worker có identity/secret riêng; các key có quyền đọc tối thiểu.
- [ ] Có broker ACL phù hợp với request/reply exchange, queue, vhost và role của từng workload.
- [ ] Chứng chỉ hợp lệ về thời gian, key usage, EKU và chính sách PKI; thời gian nút được đồng bộ.
- [ ] Không mở plaintext listener trái chính sách; không dùng trust-all hoặc bỏ qua hostname validation.
- [ ] Có chính sách bảo vệ data-at-rest, DLQ, broker logs, JobParameters và ExecutionContext.
- [ ] Đã chạy ma trận test TLS âm/dương, quyền AMQP, lỗi network và restart/redelivery.
- [ ] Có cơ chế cảnh báo trước khi hết hạn, rotation, reconnect và thu hồi certificate bị lộ.
- [ ] Đã đo CPU, số TLS connection, broker backlog, throughput, queue và JDBC pool ở concurrency thực tế.
- [ ] Có runbook an toàn cho sự cố mTLS, drain, rollback và đối soát dữ liệu sau phục hồi.

## 18. Ghi nhớ

**Mutual TLS bảo vệ và xác thực từng kết nối trong remote execution**, nhưng nó không tự quyết định worker nào được chạy job, không thay thế ACL của broker và không giải quyết retry/restart hay dữ liệu xử lý trùng. Với Spring Batch qua broker, manager và worker thường có **hai phiên TLS độc lập tới broker**, còn JobRepository và API bên ngoài cần chính sách bảo vệ riêng. Một triển khai tốt kết hợp certificate/CA/trust đúng, kiểm tra hostname, identity và phân quyền tối thiểu, quản lý secret/rotation, kiểm thử lỗi handshake và đặc biệt là **đối soát dữ liệu sau reconnect** khi job đang chạy ở tải thực tế.
