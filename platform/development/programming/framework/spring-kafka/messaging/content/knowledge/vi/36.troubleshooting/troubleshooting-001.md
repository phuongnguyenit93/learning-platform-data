# Không kết nối được broker

Khi ứng dụng Spring Kafka không kết nối được Kafka broker, cần xác định lỗi xảy ra ở bước nào: phân giải địa chỉ, mở kết nối TCP, nhận metadata cluster, bắt tay TLS/SASL hay thực hiện thao tác Kafka. Một địa chỉ `bootstrap.servers` đúng cú pháp chưa đủ để bảo đảm ứng dụng truy cập được toàn bộ cluster. Sau khi kết nối bootstrap, Kafka client nhận metadata chứa địa chỉ broker được quảng bá và có thể mở kết nối tới các broker khác để gửi hoặc đọc partition leader.

Vì vậy, chẩn đoán nên đi theo thứ tự: **xác nhận endpoint từ đúng môi trường chạy ứng dụng → kiểm tra DNS/TCP → kiểm tra `advertised.listeners` → kiểm tra protocol và bảo mật → xác minh producer, consumer và AdminClient → kiểm tra quyền topic/group**. Cách làm theo lớp giúp tránh thay đổi cấu hình bảo mật hoặc timeout khi nguyên nhân thực tế chỉ là hostname hoặc port sai.

## 1. Hiểu đường đi của kết nối Kafka

Spring Kafka sử dụng Kafka Java client. Producer, consumer và AdminClient đều cần kết nối tới broker, nhưng mục đích và thời điểm tạo kết nối có thể khác nhau.

```text
Spring Boot application
    |
    +---- KafkaTemplate / ProducerFactory
    |
    +---- @KafkaListener / ConsumerFactory
    |
    +---- KafkaAdmin / AdminClient
              |
              v
       bootstrap.servers
              |
              v
        Bootstrap broker
              |
              | Metadata: broker IDs, endpoints,
              | topic partitions, leaders
              v
        Kafka cluster
          /    |    \
         v     v     v
      Broker Broker Broker
         \     |     /
          Partition leaders
```

`bootstrap.servers` là danh sách địa chỉ ban đầu để client khám phá cluster. Nó không phải danh sách duy nhất mà client sẽ kết nối trong suốt vòng đời. Sau khi nhận metadata, client dùng endpoint broker được quảng bá để kết nối tới coordinator hoặc partition leader phù hợp.

Một lỗi thường gặp là bootstrap broker có thể truy cập được, nhưng hostname trong `advertised.listeners` lại không thể phân giải hoặc không thể kết nối từ môi trường ứng dụng. Khi đó client khởi tạo được một phần nhưng produce/fetch vẫn thất bại.

## 2. Phân biệt các lớp lỗi

| Lớp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| Cấu hình endpoint | Có địa chỉ broker hợp lệ không? | `No resolvable bootstrap urls given` |
| DNS | Hostname có phân giải được từ runtime không? | `UnknownHostException` |
| TCP/network | Có mở được socket tới host và port không? | `Connection refused`, timeout, `DisconnectException` |
| Kafka metadata | Client có nhận được metadata và endpoint hợp lệ không? | Không tìm được node, metadata request timeout |
| Listener protocol | Port đó có đúng listener Kafka không? | Kết nối plaintext vào SSL port hoặc ngược lại |
| TLS | Certificate chain và hostname có hợp lệ không? | `SSLHandshakeException`, `PKIX path building failed` |
| SASL authentication | Credential và mechanism có đúng không? | `SaslAuthenticationException` |
| Authorization | Principal có quyền topic/group không? | `TopicAuthorizationException`, `GroupAuthorizationException` |
| Application behavior | Producer/consumer có thực sự thực hiện thao tác không? | Send future thất bại, listener không nhận record |

Không phải mọi lỗi xuất hiện trong log Kafka đều là lỗi mạng. Ví dụ `TopicAuthorizationException` cho biết client đã đi đủ xa để broker từ chối quyền truy cập; tăng timeout hoặc đổi port không giải quyết được lỗi ACL.

## 3. Bước đầu tiên: xác nhận bootstrap.servers

Kiểm tra cấu hình thực tế được nạp khi ứng dụng chạy, không chỉ file `application.yml` trong source. Profile, environment variable, command-line argument hoặc secret/config map có thể ghi đè giá trị mặc định.

Spring Boot cấu hình bootstrap servers bằng:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9092,broker-2.example.net:9092
```

Các điểm cần kiểm tra:

- Hostname đúng với môi trường mà ứng dụng đang chạy.
- Port đúng listener Kafka, không nhầm với JMX, controller, HTTP proxy hoặc port của một service khác.
- Danh sách có dấu phẩy phân tách đúng, không chứa URL scheme như `http://`.
- Không dùng `localhost` nếu broker không chạy trong cùng network namespace với ứng dụng.
- Không trộn endpoint plaintext, SSL và SASL_SSL trong cùng danh sách nếu client chỉ được cấu hình cho một protocol.
- Profile đang hoạt động thực sự nạp đúng giá trị.

Nếu dùng environment variable:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Hãy xác minh biến này tồn tại trong process/container/pod. Một biến có trên máy developer không tự động xuất hiện trong Docker container hoặc Kubernetes pod.

## 4. Kiểm tra DNS từ đúng môi trường chạy ứng dụng

Một hostname có thể phân giải trên máy host nhưng không phân giải trong container hoặc pod. Chạy lệnh kiểm tra từ cùng môi trường network với ứng dụng.

Trên Windows PowerShell:

```powershell
Resolve-DnsName broker-1.example.net
```

Trên Linux hoặc trong container:

```bash
getent hosts broker-1.example.net
```

Nếu DNS thất bại:

- Kiểm tra hostname có đúng chính tả và domain suffix không.
- Kiểm tra DNS server mà container/pod đang sử dụng.
- Kiểm tra service discovery, namespace và DNS search path.
- Với Kubernetes, kiểm tra service name và namespace, ví dụ `kafka-bootstrap.messaging.svc.cluster.local`.
- Không thay hostname bằng IP một cách tùy tiện nếu certificate TLS hoặc broker metadata yêu cầu hostname cụ thể.

Nếu DNS trả về nhiều địa chỉ, kiểm tra từng endpoint và bảo đảm tất cả broker được quảng bá đều có thể truy cập.

## 5. Kiểm tra TCP và port

DNS thành công chỉ chứng minh hostname được phân giải. Tiếp theo cần kiểm tra kết nối TCP.

Trên Windows PowerShell:

```powershell
Test-NetConnection broker-1.example.net -Port 9092
```

Đọc trường `TcpTestSucceeded`. Nếu là `False`, kiểm tra route, firewall, security group, network policy, port mapping và listener phía broker.

Trên Linux:

```bash
nc -vz broker-1.example.net 9092
```

Các kết quả thường gặp:

| Kết quả | Ý nghĩa có thể | Hướng xử lý |
| --- | --- | --- |
| Connection refused | Host reachable nhưng port không có service lắng nghe hoặc bị reject | Kiểm tra broker listener, port mapping và service target |
| Connection timed out | Packet bị drop, route/firewall sai hoặc endpoint không phản hồi | Kiểm tra network route, firewall, security group và NetworkPolicy |
| No route to host | Không có đường mạng hoặc thiết bị trung gian từ chối | Kiểm tra subnet, gateway, route và policy |
| TCP thành công | Socket có thể mở | Tiếp tục kiểm tra Kafka protocol, TLS/SASL và metadata |

TCP test thành công chưa chứng minh Kafka protocol đúng. Ví dụ port mở nhưng đó là listener SSL trong khi client đang dùng PLAINTEXT; bước handshake Kafka sẽ thất bại.

## 6. Kiểm tra advertised.listeners

`listeners` xác định địa chỉ/port broker bind để nhận kết nối. `advertised.listeners` xác định endpoint broker công bố trong metadata cho client sử dụng. Hai cấu hình có vai trò khác nhau.

Ví dụ broker trong Docker:

```properties
listeners=INTERNAL://0.0.0.0:29092,EXTERNAL://0.0.0.0:9092
advertised.listeners=INTERNAL://kafka:29092,EXTERNAL://localhost:9092
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT
inter.broker.listener.name=INTERNAL
```

Trong ví dụ này:

- Container khác cùng Docker network kết nối tới `kafka:29092`.
- Ứng dụng chạy trên máy host kết nối tới `localhost:9092`.
- Broker quảng bá endpoint tương ứng với listener mà client sử dụng.

Không cấu hình broker quảng bá `localhost:9092` cho một ứng dụng chạy trong container khác. `localhost` trong container là chính container ứng dụng, không phải broker container.

Một triệu chứng điển hình: `Test-NetConnection` tới bootstrap port thành công, log cho thấy client đã nhận metadata, sau đó xuất hiện lỗi kết nối tới hostname khác. Hãy đọc hostname/port trong log `Connection to node ... could not be established` và so sánh với `advertised.listeners`.

## 7. Bootstrap broker và broker endpoint sau metadata

Giả sử cấu hình:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-bootstrap:9092
```

Bootstrap broker trả metadata chứa ba broker:

```text
broker 1 -> kafka-1.internal:9092
broker 2 -> kafka-2.internal:9092
broker 3 -> kafka-3.internal:9092
```

Ứng dụng vẫn cần phân giải và kết nối được các endpoint cần thiết đó. Nếu chỉ `kafka-bootstrap` truy cập được nhưng `kafka-1.internal` không truy cập được từ application subnet, client có thể không produce/fetch ổn định.

Vì vậy, hãy kiểm tra toàn bộ địa chỉ broker được quảng bá, không chỉ một bootstrap endpoint. Trong môi trường cloud hoặc Kubernetes, đảm bảo DNS/service routing và firewall cho phép client truy cập các broker endpoint cần thiết.

## 8. Docker Compose: lỗi localhost và network alias

Trong Docker Compose, service name thường được dùng làm hostname giữa các container trên cùng network:

```yaml
services:
  kafka:
    image: apache/kafka:latest
    ports:
      - "9092:9092"
    # Broker phải quảng bá listener phù hợp cho cả
    # container trong network và client trên host.

  order-service:
    build: .
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
    depends_on:
      - kafka
```

Đoạn Compose trên chỉ minh họa service discovery; cấu hình listener thực tế phụ thuộc image Kafka và cách broker được khởi tạo. `depends_on` không bảo đảm Kafka đã sẵn sàng nhận request, nó chủ yếu điều phối thứ tự khởi chạy container trừ khi có healthcheck/condition phù hợp.

Các lỗi phổ biến:

- Ứng dụng trong container dùng `localhost:9092` thay vì service name `kafka:29092`.
- Broker chỉ quảng bá endpoint host `localhost`, khiến container không truy cập được.
- Port publish ra host đúng nhưng port nội bộ container khác.
- Ứng dụng khởi động trước khi broker hoàn tất startup.
- Broker và application nằm ở hai Docker network khác nhau.

Hãy dùng endpoint nội bộ cho container-to-container và endpoint external cho client chạy ngoài Docker. Không giả định một địa chỉ duy nhất phù hợp cho mọi network.

## 9. Kubernetes: service DNS, pod endpoint và NetworkPolicy

Trong Kubernetes, ứng dụng thường bootstrap qua Service DNS. Tuy nhiên, Kafka broker có thể trả metadata chứa endpoint riêng cho từng broker. Các endpoint này cũng phải truy cập được từ pod ứng dụng.

Kiểm tra từ pod:

```bash
kubectl exec -n app deploy/order-service -- \
  getent hosts kafka-bootstrap.messaging.svc.cluster.local
```

Kiểm tra TCP từ pod bằng một công cụ có sẵn trong image hoặc ephemeral debug container:

```bash
kubectl exec -n app deploy/order-service -- \
  nc -vz kafka-0.kafka-brokers.messaging.svc.cluster.local 9092
```

Kiểm tra:

- Service selector có trỏ đúng broker pods không.
- Headless Service và per-broker DNS có hoạt động nếu cluster cần.
- Kafka `advertised.listeners` trả hostname/port mà pod ứng dụng phân giải được.
- NetworkPolicy cho phép egress từ namespace ứng dụng tới broker port.
- Firewall/security group của node hoặc managed Kafka cho phép traffic.
- TLS certificate SAN khớp DNS name mà Kafka metadata quảng bá.
- Service port và targetPort không bị nhầm.

Không dùng pod IP cố định làm bootstrap endpoint nếu nền tảng cung cấp service discovery ổn định. Pod IP có thể thay đổi khi broker restart hoặc reschedule.

## 10. Kiểm tra broker có chạy và listener có bind đúng

Ở phía broker, kiểm tra:

- Broker process/container/pod đang healthy.
- Kafka startup log không có lỗi bind port, cấu hình listener hoặc storage.
- `listeners` bind vào interface có thể nhận kết nối từ network cần thiết; bind `127.0.0.1` chỉ nhận kết nối loopback.
- Port thực tế trùng với endpoint client dùng.
- Listener security protocol map đúng với listener name.
- `advertised.listeners` không dùng hostname nội bộ mà client không thể truy cập.
- Nếu cluster có nhiều broker, tất cả broker có endpoint và certificate hợp lệ.

Lệnh kiểm tra phụ thuộc cách triển khai Kafka. Với Docker:

```bash
docker ps
docker logs kafka
```

Với Kubernetes:

```bash
kubectl get pods -n messaging
kubectl get svc -n messaging
kubectl logs -n messaging kafka-0
```

Container đang ở trạng thái `Running` không đồng nghĩa Kafka đã sẵn sàng. Đọc startup log và dùng health/readiness check phù hợp với Kafka listener.

## 11. Kiểm tra listener protocol: PLAINTEXT, SSL hay SASL_SSL

Port phải khớp protocol client cấu hình. Ví dụ:

| Broker listener | Client `security.protocol` |
| --- | --- |
| PLAINTEXT | `PLAINTEXT` |
| SSL | `SSL` |
| SASL_PLAINTEXT | `SASL_PLAINTEXT` |
| SASL_SSL | `SASL_SSL` |

Spring Boot cấu hình protocol qua Kafka properties:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
```

Nếu client dùng `PLAINTEXT` để kết nối SSL port, hoặc dùng `SSL` tới plaintext port, handshake sẽ thất bại. Hãy xác nhận listener/port do đội vận hành Kafka cung cấp thay vì thử ngẫu nhiên các protocol.

Với nhiều listener trên broker, `listener.security.protocol.map` phải ánh xạ đúng listener name tới protocol tương ứng. Với inter-broker communication, cấu hình `inter.broker.listener.name` cũng cần trỏ tới listener phù hợp.

## 12. Chẩn đoán TLS certificate

Nếu TCP mở nhưng TLS handshake thất bại, kiểm tra trust chain, thời hạn certificate và hostname verification.

Các cấu hình client TLS thường gặp:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

Các lỗi phổ biến:

- `PKIX path building failed`: truststore thiếu CA hoặc intermediate certificate.
- `No subject alternative DNS name matching`: hostname kết nối không có trong SAN certificate.
- `Keystore was tampered with, or password was incorrect`: sai password hoặc sai loại keystore.
- `UnrecoverableKeyException`: private key password hoặc key entry không hợp lệ.
- Certificate expired/not yet valid: certificate hết hạn hoặc thời gian hệ thống sai.

Không tắt hostname verification để bỏ qua lỗi SAN. Sửa certificate hoặc endpoint được quảng bá để chúng khớp nhau. Nếu dùng mTLS, kiểm tra cả keystore client, private key và broker truststore tin cậy CA của client.

Có thể kiểm tra TLS độc lập bằng:

```bash
openssl s_client -connect broker-1.example.net:9093 \
  -servername broker-1.example.net -showcerts
```

Lệnh này giúp quan sát certificate chain và handshake; nó không xác minh đầy đủ Kafka protocol hay SASL authentication.

## 13. Chẩn đoán SASL authentication

Nếu cluster dùng SASL, kiểm tra mechanism, username/password hoặc token và JAAS/callback configuration.

Ví dụ SASL SCRAM qua TLS:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
```

Kiểm tra:

- `sasl.mechanism` có đúng cơ chế broker bật không.
- Credential thuộc đúng cluster/environment và chưa hết hạn.
- JAAS config có đúng cú pháp, dấu nháy và dấu chấm phẩy.
- Với OAuth, callback handler và token provider có thể truy cập endpoint cấp token.
- Với `SASL_SSL`, truststore và hostname verification vẫn phải đúng.

`SaslAuthenticationException` thường là lỗi xác thực, không phải lỗi TCP. Không đưa password/token vào log để debug; log tên mechanism và loại exception là đủ để khoanh vùng ban đầu.

## 14. Phân biệt authentication và authorization

Khi TLS/SASL thành công, broker vẫn có thể từ chối thao tác vì ACL.

| Exception | Ý nghĩa thường gặp | Cần kiểm tra |
| --- | --- | --- |
| `SaslAuthenticationException` | Xác thực SASL thất bại | Credential, mechanism, JAAS/token |
| `TopicAuthorizationException` | Principal không có quyền topic | ACL `READ`/`WRITE`/`DESCRIBE` trên topic |
| `GroupAuthorizationException` | Principal không có quyền consumer group | ACL group tương ứng |
| `TransactionalIdAuthorizationException` | Không có quyền transactional ID | ACL transactional ID cho producer transaction |

Không cấp quyền `superuser` hoặc quyền rộng cho mọi topic chỉ để làm lỗi biến mất. Hãy cấp quyền tối thiểu cho service theo vai trò producer, consumer hoặc transactional producer.

## 15. Xác minh bằng Kafka command-line tools

Nếu có Kafka CLI trong môi trường có thể truy cập cluster, dùng `kafka-broker-api-versions` để kiểm tra bootstrap và metadata:

```bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker-1.example.net:9092
```

Với cluster SSL/SASL, truyền file cấu hình client:

```bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker-1.example.net:9093 \
  --command-config client.properties
```

Kiểm tra topic metadata:

```bash
kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe --topic orders.created
```

Nếu CLI chạy được từ cùng môi trường nhưng Spring app không chạy, so sánh chính xác bootstrap servers, protocol, truststore, SASL mechanism, principal và các override trong Spring profile. Nếu CLI cũng thất bại, tập trung vào endpoint, network hoặc broker.

## 16. Kiểm tra từng Kafka client trong Spring Boot

Một ứng dụng có thể dùng các cấu hình khác nhau cho producer, consumer và admin client. Ví dụ cấu hình chung:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9092,broker-2.example.net:9092
    properties:
      "[security.protocol]": PLAINTEXT
    producer:
      properties:
        "[client.id]": order-service-producer
    consumer:
      group-id: order-service-consumer
      properties:
        "[client.id]": order-service-consumer
    admin:
      fail-fast: true
```

Đây là ví dụ cấu hình chung cho môi trường plaintext. Production thường cần SSL/SASL và secret tương ứng. `KafkaAdmin` có thể kết nối khi ứng dụng khởi động để kiểm tra/tạo topic tùy cấu hình; nếu `fail-fast` được bật, lỗi admin có thể làm startup thất bại sớm.

Nếu producer gửi được nhưng listener không nhận, kiểm tra riêng:

- Consumer bootstrap servers và security properties.
- Consumer group ID và ACL group.
- Topic subscription và topic tồn tại.
- Deserializer có khởi tạo được không.
- Partition assignment và consumer lag.

Nếu consumer chạy nhưng producer lỗi, kiểm tra producer factory, serializer, topic write ACL và callback/future của `KafkaTemplate`.

## 17. Ứng dụng khởi động được nhưng Kafka chưa sẵn sàng

Không phải mọi Kafka client đều mở kết nối ngay khi Spring context được tạo. Producer có thể tạo lazy và chỉ kết nối khi gửi; listener container có thể retry kết nối trong quá trình chạy; KafkaAdmin có thể thực hiện thao tác khi startup tùy cấu hình.

Vì vậy, ứng dụng báo `Started` không đồng nghĩa broker đã kết nối thành công. Ngược lại, một lần log connection error lúc broker đang khởi động chưa chắc là lỗi kéo dài nếu client reconnect thành công sau đó.

Hãy phân biệt:

- **Startup failure:** context không khởi động do KafkaAdmin hoặc listener fail-fast.
- **Transient connection failure:** broker chưa sẵn sàng hoặc network chập chờn, client sẽ reconnect.
- **Persistent connection failure:** endpoint, DNS, protocol hoặc security cấu hình sai.
- **Operation failure:** client kết nối được nhưng send/fetch/metadata/authorization thất bại.

Readiness của ứng dụng nên phản ánh yêu cầu nghiệp vụ. Nếu service không thể phục vụ khi Kafka unavailable, health/readiness cần thể hiện điều đó. Nếu ứng dụng có thể khởi động và retry trong khi broker phục hồi, không nên biến một lỗi transient thành crash loop chỉ vì một lần kết nối đầu tiên thất bại.

## 18. Timeout và reconnect: điều chỉnh sau khi đã xác định nguyên nhân

Kafka client có cơ chế reconnect và retry. Một số cấu hình liên quan:

| Thuộc tính | Vai trò |
| --- | --- |
| `reconnect.backoff.ms` | Khoảng chờ cơ bản giữa các lần reconnect |
| `reconnect.backoff.max.ms` | Giới hạn backoff reconnect |
| `socket.connection.setup.timeout.ms` | Giới hạn thời gian thiết lập kết nối socket |
| `socket.connection.setup.timeout.max.ms` | Giới hạn trên của thời gian setup connection với backoff |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request |
| `default.api.timeout.ms` | Timeout mặc định cho các API có timeout |

Không tăng tất cả timeout lên vài phút để che giấu DNS/advertised listener sai. Timeout lớn có thể khiến ứng dụng phát hiện sự cố chậm hơn. Trước tiên sửa endpoint và network; sau đó mới điều chỉnh reconnect/backoff theo yêu cầu chịu lỗi.

Với producer, phân biệt timeout lúc `send()` đang chờ metadata/buffer (`max.block.ms`) với lỗi của future sau khi record đã được nhận vào luồng gửi (`delivery.timeout.ms`). Với consumer, kiểm tra poll loop và rebalance riêng, không suy ra từ producer timeout.

## 19. Quy trình chẩn đoán theo thứ tự

Thực hiện lần lượt để thu hẹp phạm vi:

1. **Xác nhận cấu hình runtime:** lấy `bootstrap.servers`, profile, environment variable và security protocol thực tế; che password/secret khi ghi log.
2. **Kiểm tra DNS:** phân giải từng bootstrap hostname từ container/pod/process chạy ứng dụng.
3. **Kiểm tra TCP:** test từng hostname/port; ghi nhận refused, timeout hoặc success.
4. **Kiểm tra broker listener:** xác nhận broker đang bind port và listener dùng đúng protocol.
5. **Kiểm tra metadata:** dùng Kafka CLI hoặc log client để xem broker endpoints được quảng bá.
6. **Kiểm tra advertised listeners:** test DNS/TCP tới mọi broker endpoint cần truy cập.
7. **Kiểm tra TLS/SASL:** xác minh CA, SAN, keystore, mechanism và credential.
8. **Kiểm tra authorization:** xác minh topic/group/transactional ID ACL.
9. **Kiểm tra từng client:** producer, consumer và AdminClient có cấu hình tương ứng.
10. **Kiểm tra thao tác end-to-end:** publish record test, consume bằng group test và quan sát send result/lag.

Ghi lại thời điểm, hostname, port, broker node ID, exception class và client ID. Những thông tin này đủ giúp đội vận hành tìm đúng broker/log mà không phải chia sẻ credential.

## 20. Bảng lỗi thường gặp và cách xử lý

| Log/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `No resolvable bootstrap urls given` | Bootstrap list rỗng hoặc sai định dạng | Kiểm tra property runtime, dấu phân tách và hostname |
| `UnknownHostException` | DNS không phân giải được | Kiểm tra DNS từ đúng container/pod và service name |
| `Connection refused` | Broker không listen trên port hoặc sai port mapping | Kiểm tra broker process, listener và port |
| `Connection timed out` | Firewall, route, security group hoặc network policy drop packet | Kiểm tra network path hai chiều và policy |
| `Connection to node -1 could not be established` | Bootstrap endpoint không kết nối được | Kiểm tra bootstrap hostname/port, broker startup và protocol |
| Bootstrap thành công nhưng node khác lỗi | `advertised.listeners` trả endpoint client không truy cập được | Kiểm tra metadata và advertised host/port của từng broker |
| `SSLHandshakeException` | TLS protocol, trust chain, SAN hoặc certificate lỗi | Kiểm tra truststore, certificate chain và hostname verification |
| `PKIX path building failed` | Client không tin cậy CA ký broker certificate | Thêm đúng CA/intermediate vào truststore |
| `SaslAuthenticationException` | Credential hoặc SASL mechanism sai | Kiểm tra username/password/token và mechanism |
| `UnsupportedSaslMechanismException` | Client dùng mechanism broker không bật | Đồng bộ `sasl.mechanism` với broker |
| `TopicAuthorizationException` | Principal thiếu quyền topic | Kiểm tra ACL `READ`/`WRITE`/`DESCRIBE` |
| `GroupAuthorizationException` | Principal thiếu quyền consumer group | Kiểm tra ACL group |
| Producer gửi được, listener không nhận | Consumer config, group, subscription hoặc deserialize lỗi | Kiểm tra consumer log, assignment, lag và deserializer |
| App báo started nhưng chưa gửi được | Producer chưa thực hiện kết nối thực tế hoặc send async thất bại | Quan sát future/callback và thực hiện smoke test |

## 21. Smoke test kết nối sau khi sửa lỗi

Sau khi endpoint và security đã đúng, xác minh luồng thực tế bằng một topic test:

1. Dùng Kafka CLI kiểm tra broker metadata từ môi trường ứng dụng.
2. Tạo hoặc xác nhận topic test có partition phù hợp.
3. Gửi một record với key/event ID duy nhất bằng producer test.
4. Chờ `KafkaTemplate.send()` future hoàn tất và kiểm tra `RecordMetadata`.
5. Consume record bằng consumer group test với deserializer đúng.
6. Xác minh key, payload, headers và partition.
7. Kiểm tra consumer lag/offset để xác nhận record đã được đọc.
8. Lặp lại với producer, consumer và AdminClient của ứng dụng nếu chúng dùng factory/config riêng.

Không chỉ dùng `nc` hoặc `Test-NetConnection` làm bằng chứng ứng dụng đã kết nối Kafka. Những lệnh đó chỉ kiểm tra TCP; smoke test Kafka mới kiểm tra metadata, protocol, authentication và thao tác produce/consume.

## 22. Logging và observability

Khi điều tra, thu thập thông tin có ích nhưng không làm lộ secret:

- Kafka bootstrap hostname/port và profile đang dùng.
- Kafka client ID, group ID và broker node ID.
- Exception class, root cause và thời điểm xảy ra.
- Producer send rate/error rate và request latency.
- Consumer connection status, assignment, lag và rebalance count.
- TLS certificate subject/SAN/expiry nếu lỗi liên quan certificate; không log private key.
- Broker listener và network policy thay đổi gần thời điểm lỗi.

Có thể bật log Kafka client ở mức DEBUG tạm thời trong môi trường test hoặc trong khoảng điều tra được kiểm soát. DEBUG có thể tạo lượng log lớn và chứa metadata nhạy cảm; không nên bật lâu dài ở production nếu chưa đánh giá.

## 23. Checklist phòng ngừa

- [ ] `bootstrap.servers` lấy từ cấu hình runtime đúng môi trường.
- [ ] Hostname và port có thể truy cập từ nơi ứng dụng chạy.
- [ ] Tất cả broker endpoint trong metadata đều phân giải và kết nối được.
- [ ] `listeners` bind vào interface phù hợp.
- [ ] `advertised.listeners` quảng bá endpoint đúng network của client.
- [ ] Docker/Kubernetes service, port mapping và NetworkPolicy được kiểm tra.
- [ ] `security.protocol` khớp listener.
- [ ] TLS truststore, SAN, hostname verification và mTLS được cấu hình đúng nếu cần.
- [ ] SASL mechanism và credential hợp lệ nếu dùng SASL.
- [ ] ACL topic, group và transactional ID được cấp theo least privilege.
- [ ] Producer, consumer và AdminClient đều dùng đúng cấu hình.
- [ ] Có smoke test produce/consume và monitoring connection/lag.
- [ ] Có readiness/reconnect policy phù hợp khi broker tạm thời unavailable.

## 24. Kết luận

Lỗi không kết nối được broker cần được chẩn đoán theo từng lớp: endpoint, DNS, TCP, metadata, advertised listener, protocol, TLS/SASL và authorization. Điểm quan trọng nhất là kiểm tra từ đúng môi trường chạy ứng dụng và kiểm tra toàn bộ broker endpoint mà metadata trả về. Một bootstrap hostname truy cập được không bảo đảm các broker được quảng bá cũng truy cập được.

Trong Spring Kafka, xác minh cấu hình `spring.kafka.bootstrap-servers` và property runtime, kiểm tra producer/consumer/AdminClient riêng, rồi dùng smoke test Kafka để chứng minh publish và consume thực sự hoạt động. Giữ hostname verification, không tắt bảo mật để né lỗi, không cấp ACL quá rộng và chỉ điều chỉnh timeout sau khi đã sửa nguyên nhân mạng hoặc listener. Khi có quy trình kiểm tra DNS/TCP/metadata/security rõ ràng, phần lớn sự cố kết nối có thể được khoanh vùng nhanh và xử lý có căn cứ.

## Tài liệu tham khảo

- [Apache Kafka — Broker Configurations: Listeners](https://kafka.apache.org/documentation/#brokerconfigs_listeners)
- [Apache Kafka — Security](https://kafka.apache.org/documentation/#security)
- [Apache Kafka — Admin Client](https://kafka.apache.org/documentation/#adminapi)
- [Spring for Apache Kafka — Connecting to Kafka](https://docs.spring.io/spring-kafka/reference/kafka/connecting.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
