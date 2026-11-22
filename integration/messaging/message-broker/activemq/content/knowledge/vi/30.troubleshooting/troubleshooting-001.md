# Không kết nối được do URI, cổng, DNS, tài khoản hoặc TLS

## 1. Chẩn đoán theo tầng, không đổi cấu hình ngẫu nhiên

Khi Java producer/consumer không kết nối được tới ActiveMQ, thông báo **connection refused**, **timeout**, **authentication failed**, **PKIX path building failed** hay **no subject alternative names matching** đều có thể xuất hiện dưới một triệu chứng chung: ứng dụng không gửi/nhận được message. Tuy nhiên, mỗi lỗi nằm ở một tầng khác nhau. Nếu đổi password khi DNS đang trỏ sai host, hoặc tắt TLS verification khi certificate thiếu SAN, sự cố sẽ không được xử lý đúng.

Thứ tự chẩn đoán hiệu quả:

1. **URI và protocol**: client đang dùng đúng scheme, hostname, port và query options của broker hay không?
2. **DNS và routing**: hostname có phân giải về địa chỉ mong muốn; máy client có route tới mạng đó không?
3. **TCP/listener**: broker có bind đúng interface/port; firewall, container port mapping và security group có cho phép không?
4. **TLS identity**: handshake có thành công; client có tin CA và kiểm tra đúng SAN/hostname; nếu mTLS thì broker có tin client certificate không?
5. **Authentication**: username/password hoặc certificate identity có được broker xác thực không?
6. **Authorization/destination**: principal có quyền connect, send/consume đúng queue/address không?
7. **JMS smoke test**: một chương trình tối giản có tạo connection/session, send và receive được không?

~~~mermaid
flowchart TD
    START["JMS client không kết nối"] --> URI{"URI/protocol/port đúng?"}
    URI -->|Không| FIXURI["Sửa scheme, host, port, options"]
    URI -->|Có| DNS{"DNS resolve đúng?"}
    DNS -->|Không| FIXDNS["Sửa DNS/search domain/hosts"]
    DNS -->|Có| TCP{"TCP tới listener thành công?"}
    TCP -->|Không| FIXTCP["Kiểm tra bind, firewall, route, Docker"]
    TCP -->|Có| TLS{"Endpoint có TLS?"}
    TLS -->|Có| HANDSHAKE{"TLS handshake + SAN pass?"}
    HANDSHAKE -->|Không| FIXTLS["Sửa CA, chain, SAN, key/trust store"]
    HANDSHAKE -->|Có| AUTH{"Authentication pass?"}
    TLS -->|Không| AUTH
    AUTH -->|Không| FIXAUTH["Kiểm tra user, password, auth provider"]
    AUTH -->|Có| ACL{"Có quyền destination?"}
    ACL -->|Không| FIXACL["Kiểm tra role và send/consume permission"]
    ACL -->|Có| JMS["JMS smoke test và broker metrics"]
~~~

**Nguyên tắc:** chỉ thay đổi một tầng sau khi đã có bằng chứng tầng trước hoạt động. Ghi lại URI đã che credential, hostname/IP, thời điểm, client/broker version, exception root cause và thao tác cuối cùng thành công. Đừng gửi password hoặc private key vào ticket/log.

Bài thuộc chương **Chẩn đoán sự cố** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Phạm vi là các lỗi không kết nối được do **URI, port, DNS, tài khoản hoặc TLS** trên ActiveMQ Classic và Artemis; tập trung vào quy trình phân loại, lệnh kiểm tra và ví dụ Java/JMS có thể chạy độc lập.

## 2. Xác định đúng broker, protocol và URI

Một cổng TCP mở không có nghĩa client đang nói đúng protocol. ActiveMQ Classic và Artemis có thể cùng dùng TCP nhưng native wire protocol, default ports và URL options khác nhau.

| Broker / client | URI thường gặp | Protocol | Port mặc định thường gặp |
| --- | --- | --- | ---: |
| ActiveMQ Classic JMS client | tcp://host:61616 | OpenWire | 61616 |
| ActiveMQ Classic TLS transport | ssl://host:61617 hoặc port do cấu hình | OpenWire qua TLS | Không cố định |
| ActiveMQ Classic failover client | failover:(tcp://a:61616,tcp://b:61616) | OpenWire failover transport | Theo từng endpoint |
| Artemis Core/JMS client | tcp://host:61616 | Artemis Core protocol | 61616 |
| Artemis AMQP client | amqp://host:5672 | AMQP 1.0 | 5672 |
| Artemis MQTT client | mqtt://host:1883 | MQTT | 1883 |
| Artemis STOMP client | stomp://host:61613 | STOMP | 61613 |
| Artemis TLS Core/JMS | tcp://host:61617?sslEnabled=true | Core protocol qua TLS | Theo acceptor |

Port mặc định chỉ là điểm tham khảo. Broker có thể đổi port, tắt protocol hoặc bind trên interface khác. **Classic và Artemis đều có thể dùng 61616**, nhưng điều đó không làm OpenWire và Artemis Core tương thích wire-level. Phải dùng đúng client provider với đúng broker/protocol.

### 2.1. Kiểm tra scheme và endpoint

- Classic JMS native thường dùng **tcp://** hoặc **ssl://** với Classic client.
- Artemis Core/JMS thường dùng **tcp://**; bật TLS bằng option Netty phù hợp, thường là **sslEnabled=true**.
- AMQP producer không kết nối vào OpenWire/Core acceptor chỉ vì cùng là message broker.
- Không đưa **http://** hoặc **https://** vào JMS ConnectionFactory trừ khi dùng một gateway/protocol bridge thực sự hỗ trợ HTTP.
- URI **localhost** chỉ trỏ tới máy/container đang chạy client. Trong Docker, localhost của app container không phải localhost của broker container.
- URI failover phải có cú pháp đúng với provider; không dùng Classic Failover Transport URI như một cấu hình Artemis Core failover mà không xác minh client.

### 2.2. Kiểm tra query options và ký tự đặc biệt

Ví dụ URI có query:

~~~text
tcp://broker.internal:61616?wireFormat.maxInactivityDuration=30000
~~~

Classic transport options thường dùng cú pháp query của URI; Artemis Netty connector parameters thường dùng dấu chấm phẩy trong phần query. Không chép nguyên option của provider này sang provider kia.

Nếu password chứa ký tự như **@, :, /, ?, #, &, ;** thì không tự nối password vào URI bằng string concatenation. Dùng overload cấu hình credentials hoặc secret properties. Nếu bắt buộc credentials nằm trong URI theo một provider cụ thể, phải URL-encode đúng từng thành phần và tránh log URI đã chứa secret.

### 2.3. Xác minh URI thực tế ứng dụng sử dụng

Với Spring Boot, kiểm tra profile đang active và nguồn cấu hình cuối cùng: environment variable, command line, config map, secret, profile YAML hoặc external config. Giá trị trong file application.yml có thể bị ghi đè bởi:

- **SPRING_ARTEMIS_BROKER_URL** hoặc property tương ứng của starter.
- **SPRING_ACTIVEMQ_BROKER_URL** với cấu hình Classic starter tương thích.
- JVM system properties hoặc command-line arguments.
- Profile khác được kích hoạt trong container.
- Custom ConnectionFactory bean ghi đè auto-configuration.

Log URI đã che username/password và query secrets, đồng thời ghi **broker type, protocol, host và port**. Không bật logging toàn bộ properties nếu chúng chứa mật khẩu hoặc truststore password.

## 3. DNS: hostname có phân giải tới đúng địa chỉ?

DNS lỗi thường bị hiểu nhầm thành broker down. Kiểm tra từ **đúng máy hoặc container chạy JMS client**; kiểm tra trên laptop không đủ nếu app chạy trong Kubernetes, VM hay Docker network khác.

### 3.1. Windows PowerShell

~~~powershell
Resolve-DnsName broker.example.internal
nslookup broker.example.internal
Test-NetConnection broker.example.internal -Port 61616 -InformationLevel Detailed
~~~

- **Resolve-DnsName** cho biết DNS records mà Windows resolver trả về.
- **nslookup** giúp kiểm tra DNS server và câu trả lời.
- **Test-NetConnection** kiểm tra khả năng mở TCP tới endpoint; nó không xác minh TLS hay JMS authentication.

Nếu hostname có nhiều A/AAAA records, kiểm tra từng địa chỉ và IPv4/IPv6. Có trường hợp DNS trả IPv6 trước nhưng broker chỉ bind IPv4, tạo timeout hoặc connection refused tùy mạng.

### 3.2. Linux/container

~~~bash
getent ahosts broker.example.internal
nslookup broker.example.internal
nc -vz -w 3 broker.example.internal 61616
ip route get 10.20.30.40
~~~

Thay **10.20.30.40** bằng IP thực nhận từ DNS. **getent** sử dụng resolver/NSS của hệ điều hành; **nc -vz** chỉ kiểm tra TCP connect; **ip route get** cho biết kernel chọn đường đi nào tới địa chỉ đó.

Nếu image không có **nc** hoặc **nslookup**, có thể dùng **getent**, **busybox nc** hoặc công cụ debug container có sẵn theo policy. Không cài tiện ích vào production image chỉ để kiểm tra nếu quy trình triển khai không cho phép.

### 3.3. Docker và Kubernetes

Trong Docker Compose:

~~~yaml
services:
  broker:
    image: apache/activemq-artemis:latest
    ports:
      - "61616:61616"
  app:
    environment:
      BROKER_URL: tcp://broker:61616
~~~

Trong ví dụ này, app container kết nối bằng **service DNS broker:61616**, không phải localhost:61616. Tag **latest** chỉ minh họa cú pháp; production phải pin image version/digest và cấu hình volume/credentials rõ ràng.

Trong Kubernetes, kiểm tra Service và EndpointSlice từ namespace của app:

~~~bash
kubectl get svc -n messaging
kubectl get endpointslice -n messaging
kubectl get pods -n messaging -o wide
kubectl describe svc broker -n messaging
~~~

Xác nhận Service port và targetPort khớp acceptor port của broker; EndpointSlice có Pod IP sẵn sàng. NetworkPolicy, service mesh hoặc DNS policy có thể chặn traffic dù Service tồn tại.

**Không dùng IP Pod cố định trong cấu hình ứng dụng** nếu Service DNS đã được thiết kế làm endpoint ổn định. Khi Pod broker thay đổi, DNS Service cập nhật endpoint; client cần reconnect theo retry policy hợp lý.

## 4. TCP port và broker listener: cổng mở ở đúng interface chưa?

Sau khi DNS trả đúng IP, xác minh broker thực sự listen trên port đó và bind interface có thể tiếp cận từ client.

### 4.1. Kiểm tra listener trên broker

Windows:

~~~powershell
Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in 61616,61617,5672 } |
    Format-Table LocalAddress, LocalPort, State, OwningProcess

$brokerPid = 1234 # Thay bằng OwningProcess của listener cần kiểm tra.
Get-Process -Id $brokerPid
~~~

Linux:

~~~bash
ss -ltnp | grep -E ':(61616|61617|5672)\b'
lsof -nP -iTCP:61616 -sTCP:LISTEN
~~~

Nếu listener chỉ bind **127.0.0.1:61616**, client trên máy khác không thể kết nối trực tiếp. Nếu bind **0.0.0.0:61616** hoặc IP interface phù hợp, listener có thể nhận từ mạng; firewall và security group vẫn có thể chặn.

### 4.2. Phân biệt các lỗi TCP

| Lỗi | Ý nghĩa thường gặp | Kiểm tra tiếp |
| --- | --- | --- |
| **Connection refused** | Host tới được nhưng không có listener/port bị reject | Broker process, acceptor, bind address, port mapping |
| **Connect timed out** | Không nhận phản hồi TCP trong timeout | Firewall, route, security group, NetworkPolicy, IP sai |
| **No route to host / Network is unreachable** | Máy client không có đường tới mạng/host | Route table, VPN, subnet, gateway |
| **UnknownHostException** | Resolver không tìm được hostname | DNS, search domain, typo, container resolver |
| **Connection reset** | Peer/proxy đóng socket sau khi kết nối hoặc trong handshake | Protocol mismatch, broker restart, TLS, proxy timeout |
| **Connection closed** | Socket bị đóng; nguyên nhân có thể ở protocol/TLS/server policy | Broker log cùng timestamp và client root cause |

**Connection refused không phải lỗi password.** Authentication thường chỉ xảy ra sau khi TCP và protocol handshake đã tiến đủ xa. Đừng reset tài khoản chỉ để xử lý lỗi refused.

### 4.3. Firewall và network path

Kiểm tra cả chiều client → broker và các middleboxes:

- Windows Defender Firewall, Linux nftables/iptables/firewalld.
- Cloud security group, network ACL, load balancer listener/target.
- Kubernetes NetworkPolicy và service mesh egress/ingress.
- VPN, route table, NAT, port-forwarding và Docker published ports.
- Idle timeout của proxy/LB có thể đóng connection lâu không có traffic; khác với lỗi mở kết nối ban đầu.

Chỉ mở đúng port và source CIDR cần thiết. Không mở toàn bộ dải port broker ra Internet để “thử xem có kết nối được không”.


## 5. TLS: phân biệt lỗi handshake, trust chain và hostname

Khi TCP đã mở nhưng JMS client vẫn không kết nối, xác định port đó có yêu cầu TLS hay không. **Plain TCP tới TLS listener** và **TLS tới plaintext listener** đều có thể dẫn đến connection reset, unexpected packet hoặc handshake failure.

### 5.1. Kiểm tra TLS endpoint bằng OpenSSL

TLS listener một chiều:

~~~bash
openssl s_client -connect broker.example.internal:61617 \
  -servername broker.example.internal \
  -showcerts -verify_return_error
~~~

Kiểm tra CA và hostname rõ ràng:

~~~bash
openssl s_client -connect broker.example.internal:61617 \
  -servername broker.example.internal \
  -CAfile company-root-ca.pem \
  -verify_hostname broker.example.internal \
  -verify_return_error
~~~

Với listener mTLS, cung cấp client certificate và private key:

~~~bash
openssl s_client -connect broker.example.internal:61618 \
  -servername broker.example.internal \
  -CAfile company-root-ca.pem \
  -cert inventory-worker.crt \
  -key inventory-worker.key \
  -verify_hostname broker.example.internal \
  -verify_return_error
~~~

Các lệnh này kiểm tra **TLS handshake**, không kiểm tra JMS username/password, quyền send/consume hoặc protocol JMS. Sau handshake, OpenSSL có thể báo EOF/connection closed vì nó không gửi frame Core/OpenWire/AMQP tương ứng. Đánh giá **Verify return code**, certificate chain và broker log, không đòi s_client phải giữ một phiên JMS mở.

### 5.2. Kiểm tra SAN, chain và thời hạn

Certificate server phải có **Subject Alternative Name (SAN)** khớp hostname/IP mà client dùng:

| Client URI host | SAN cần có |
| --- | --- |
| broker.example.internal | DNS:broker.example.internal |
| localhost | DNS:localhost |
| 10.20.30.40 | IP:10.20.30.40 |
| mq.service.internal | DNS:mq.service.internal |

Nếu client dùng DNS alias của load balancer, certificate endpoint TLS thực sự trình bày phải chứa alias đó. Chỉ có Subject CN hoặc certificate do CA tin cậy ký **không đủ** nếu SAN không khớp.

Xem certificate:

~~~bash
openssl x509 -in broker.crt -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Kiểm tra chain:

~~~bash
openssl verify -CAfile company-root-ca.pem -untrusted intermediate-ca.pem broker.crt
~~~

Nếu server không gửi intermediate CA, client có thể báo **PKIX path building failed** hoặc **unable to find valid certification path** dù root CA đã được import. Cần sửa chain broker trình bày hoặc trust configuration theo PKI; không import certificate ngẫu nhiên và không bật trust-all.

### 5.3. Java truststore và keystore

- **Truststore client** chứa CA/trust anchor dùng xác minh certificate broker.
- **Keystore client** chứa client private key và certificate chain nếu broker yêu cầu mTLS.
- **Truststore broker** chứa CA tin cậy ký client certificate khi mTLS.
- **Keystore broker** chứa private key và certificate server.

Kiểm tra store:

~~~bash
keytool -list -v -keystore client-truststore.p12 -storetype PKCS12
keytool -list -v -keystore client-keystore.p12 -storetype PKCS12
~~~

Xác nhận truststore có **trustedCertEntry**, client keystore có **PrivateKeyEntry**, alias đúng và certificate chưa hết hạn. Lỗi **keystore password was incorrect** có thể do sai password, sai type hoặc file không phải keystore mà ứng dụng nghĩ nó là.

Để debug trong JVM, có thể bật JSSE:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
~~~

Chỉ bật trong lab hoặc khoảng thời gian sự cố được kiểm soát vì log rất lớn. Không đính kèm private key/password vào log.

Với ActiveMQ Classic, có thể kiểm tra cấu hình client SSL qua factory chuyên dụng:

~~~java
import org.apache.activemq.ActiveMQSslConnectionFactory;

ActiveMQSslConnectionFactory factory =
        new ActiveMQSslConnectionFactory(
                "ssl://broker.example.internal:61617");
factory.setTrustStore("C:/secrets/client-truststore.p12");
factory.setTrustStorePassword(System.getenv("TLS_TRUSTSTORE_PASSWORD"));
// Chỉ thêm client keystore nếu broker bắt buộc mTLS.
factory.setKeyStore("C:/secrets/client-keystore.p12");
factory.setKeyStorePassword(System.getenv("TLS_KEYSTORE_PASSWORD"));
~~~

Đây là ví dụ cấu hình vật liệu TLS; khi TLS một chiều, bỏ hai lệnh setKeyStore. Path và password phải lấy từ secret mount/environment. Kiểm tra hostname verification theo Classic client/JDK version đang dùng; truststore đúng CA không tự bảo đảm SAN đã được so khớp.

### 5.4. Hostname verification không được tắt để chữa lỗi

| Thông báo | Nguyên nhân có thể | Cách sửa đúng |
| --- | --- | --- |
| **PKIX path building failed** | Client không xây được chain tới trust anchor | Sửa CA/intermediate/truststore |
| **No subject alternative names matching** | Host trong URI không khớp SAN | Dùng hostname hợp lệ hoặc cấp lại cert SAN đúng |
| **CertificateExpiredException** | Certificate hết hạn | Rotation certificate và reload đúng SSLContext |
| **bad_certificate / certificate_required** | mTLS client cert thiếu, sai chain hoặc sai EKU | Client keystore, clientAuth EKU, broker truststore |
| **UnrecoverableKeyException** | Không mở được private key alias | Password/key alias/store type |
| **protocol_version / handshake_failure** | TLS protocol/cipher không giao nhau hoặc cấu hình sai | Kiểm tra JDK, broker, TLS versions/ciphers |

Không dùng **trustAll**, custom TrustManager chấp nhận mọi certificate hoặc **verifyHost=false** trong production. Nếu TLS thành công khi bỏ hostname verification, điều đó chứng minh cấu hình đang thiếu xác minh endpoint identity, không phải certificate đã đúng.

## 6. Authentication: TCP và TLS thành công nhưng tài khoản bị từ chối

Sau khi transport/protocol/TLS handshake thành công, broker mới có thể từ chối **authentication**. Phân biệt:

- **Authentication failed**: broker không xác thực được danh tính (username/password, certificate principal, JAAS/LDAP/OAuth provider tùy cấu hình).
- **Authorization failed**: đã có principal nhưng không có quyền thực hiện operation.
- **Destination not found**: queue/address chưa tồn tại hoặc broker không cho auto-create; có thể bị che bởi security policy.
- **Connection limit exceeded**: user/client vượt giới hạn connection hoặc resource quota, không nhất thiết password sai.

### 6.1. Kiểm tra credentials theo nguồn cấu hình

Với Spring Boot, đối chiếu chính xác profile và environment mà process đang chạy. Ví dụ property Artemis:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://broker.internal:61616
~~~

Credential có thể được bind qua environment **SPRING_ARTEMIS_USER** và **SPRING_ARTEMIS_PASSWORD**. Kiểm tra biến môi trường đã được inject vào đúng container/pod, tên có đúng chính tả và secret version đã được rollout chưa. Không in giá trị secret ra log.

PowerShell kiểm tra sự hiện diện, không in password:

~~~powershell
if ([string]::IsNullOrWhiteSpace($env:SPRING_ARTEMIS_USER)) {
    Write-Error "SPRING_ARTEMIS_USER is missing"
}
if ([string]::IsNullOrWhiteSpace($env:SPRING_ARTEMIS_PASSWORD)) {
    Write-Error "SPRING_ARTEMIS_PASSWORD is missing"
}
~~~

Linux:

~~~bash
test -n "$SPRING_ARTEMIS_USER" && echo "ARTEMIS_USER is set"
test -n "$SPRING_ARTEMIS_PASSWORD" && echo "ARTEMIS_PASSWORD is set"
~~~

Nếu credentials vừa rotate, kiểm tra app có thực sự restart/reload secret. Một pod cũ có thể vẫn giữ password cũ trong memory; thay Kubernetes Secret không đảm bảo process đang chạy tự đọc lại.

### 6.2. Kiểm tra authentication provider ở broker

Xem broker log cùng timestamp với client exception:

- User có tồn tại trong đúng realm/security domain không?
- Broker đang dùng JAAS properties, LDAP, custom login module hoặc certificate authentication nào?
- Có nhiều broker với user database/realm khác nhau không?
- Có cấu hình anonymous access hoặc default user gây hiểu nhầm không?
- Nếu mTLS, broker có xác thực certificate chain nhưng sau đó vẫn yêu cầu JMS username/password không?

Không mặc định **mTLS thành công** nghĩa JMS user đã được xác thực. TLS client certificate và JMS principal có thể là hai lớp identity riêng biệt.

## 7. Authorization và destination: đã đăng nhập nhưng không được send/consume

Một kết nối có thể mở thành công, Connection.start() thành công nhưng send hoặc createConsumer bị từ chối do quyền. Hãy thử **operation nhỏ nhất** trên một queue test và xem broker security log.

### 7.1. Các quyền thường bị nhầm

| Operation | Quyền cần xem xét |
| --- | --- |
| Mở connection/session | Connect/authentication policy |
| Send tới queue/address | Send permission |
| Consume queue | Consume permission |
| Tạo queue/address động | Create address/queue permission theo broker policy |
| Xóa queue/address | Delete permission |
| Durable subscription/topic | Quyền tạo/consume subscription và policy tương ứng |
| Management/JMX/console | Quyền quản trị riêng, không nên cấp cho app worker |

Trong Artemis, authorization thường được cấu hình theo **address match và role permissions**. Classic dùng security plugin/security settings theo destination. Không áp dụng XML của một broker sang broker kia.

### 7.2. Cách khoanh vùng

1. Ghi principal thực tế đã được broker xác thực (không ghi secret).
2. Ghi destination đầy đủ, bao gồm address/queue và routing type nếu Artemis.
3. Xác định operation bị từ chối: send, consume, create hay management.
4. Kiểm tra role mapping và wildcard match của destination.
5. Cấp đúng quyền tối thiểu cho queue/address cần thiết.
6. Kết nối lại bằng cùng user và thử lại một message có eventId riêng.

Nếu producer gửi được nhưng consumer không nhận, không vội kết luận network hỏng. Có thể consumer không có quyền consume, queue không có message, selector không match hoặc message đang ở queue khác.

### 7.3. Không dùng tài khoản admin để “xác nhận tạm”

Dùng admin có thể làm test pass dù app role thiếu quyền. Sau khi xác minh kết nối bằng admin, phải lặp lại bằng **service account thực tế** và quyền tối thiểu. Không để password admin mặc định trong image, compose file hoặc repository.

## 8. Java/JMS smoke test: kiểm tra end-to-end bằng provider đúng

Sau khi DNS, TCP, TLS và credentials đã được kiểm tra, chạy một chương trình tối giản để xác nhận đúng protocol và quyền destination. Chương trình dưới đây gửi một message tới queue test và nhận lại bằng selector theo **probeId**. Dùng queue riêng, không chạy vào queue nghiệp vụ production.

### 8.1. ActiveMQ Classic với javax.jms

Maven dependency cho client Classic:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>5.18.3</version>
</dependency>
~~~

Java smoke test:

~~~java
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

import java.util.UUID;

public class ClassicJmsProbe {
    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        String queueName = System.getenv().getOrDefault(
                "PROBE_QUEUE", "diagnostics.connection.probe");

        if (user == null || password == null) {
            throw new IllegalStateException("Missing broker credentials");
        }

        ConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);
        Connection connection = factory.createConnection(user, password);
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue(queueName);
                MessageConsumer consumer = session.createConsumer(
                        queue, "probeId IS NOT NULL");
                MessageProducer producer = session.createProducer(queue);
                try {
                    connection.start();

                    String probeId = UUID.randomUUID().toString();
                    TextMessage sent = session.createTextMessage(
                            "connection-probe");
                    sent.setStringProperty("probeId", probeId);

                    producer.send(sent);
                    session.commit();

                    Message received = consumer.receive(10_000L);
                    if (received == null
                            || !probeId.equals(
                                    received.getStringProperty("probeId"))) {
                        session.rollback();
                        throw new IllegalStateException(
                                "Probe message was not received");
                    }

                    session.commit();
                    System.out.println(
                            "PASS Classic JMS probeId=" + probeId);
                } finally {
                    producer.close();
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

### 8.2. ActiveMQ Artemis với jakarta.jms

Maven dependency:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.42.0</version>
</dependency>
~~~

Java smoke test:

~~~java
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public class ArtemisJmsProbe {
    public static void main(String[] args) {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        String queueName = System.getenv().getOrDefault(
                "PROBE_QUEUE", "diagnostics.connection.probe");

        if (user == null || password == null) {
            throw new IllegalStateException("Missing broker credentials");
        }

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue(queueName);
            JMSConsumer consumer = context.createConsumer(
                    queue, "probeId IS NOT NULL");

            try {
                String probeId = UUID.randomUUID().toString();
                TextMessage sent =
                        context.createTextMessage("connection-probe");
                sent.setStringProperty("probeId", probeId);

                context.createProducer().send(queue, sent);
                context.commit();

                var received = consumer.receive(10_000L);
                if (received == null
                        || !probeId.equals(
                                received.getStringProperty("probeId"))) {
                    context.rollback();
                    throw new IllegalStateException(
                            "Probe message was not received");
                }

                context.commit();
                System.out.println(
                        "PASS Artemis JMS probeId=" + probeId);
            } finally {
                consumer.close();
            }
        } finally {
            factory.close();
        }
    }
}
~~~

**Điều kiện của smoke test:** queue phải tồn tại hoặc broker phải cho phép auto-create; service account có cả send và consume; selector property được gắn đúng. Test transacted gửi rồi commit, sau đó nhận message theo probeId và commit ACK. Nếu queue không hỗ trợ auto-create, tạo queue test bằng công cụ quản trị có phân quyền trước khi chạy.


## 9. Kiểm tra TLS theo từng provider

TLS URL khác nhau giữa Classic và Artemis. Cần xác định **broker acceptor thực tế**, không chỉ sửa client URI.

### 9.1. Artemis Core acceptor

Ví dụ trong phần acceptors của broker.xml:

~~~xml
<acceptor name="core-plain">tcp://0.0.0.0:61616?protocols=CORE</acceptor>
<acceptor name="core-tls">tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/run/secrets/broker-keystore.p12;keyStorePassword=REPLACE_FROM_SECRET;keyStoreType=PKCS12</acceptor>
~~~

Đây là ví dụ minh họa cấu trúc acceptor. Trong production, không ghi password trực tiếp vào broker.xml; dùng secret/credential mechanism được release hỗ trợ. Client Artemis Core/JMS cần URI tương ứng:

~~~text
tcp://broker.example.internal:61617?sslEnabled=true;verifyHost=true
~~~

Client phải trust CA của broker. Với mTLS, acceptor cần truststore và yêu cầu client certificate theo cấu hình phù hợp, còn client cần keystore chứa private key/certificate. TLS handshake có thể thành công nhưng user vẫn bị từ chối bởi JMS authentication/authorization.

### 9.2. ActiveMQ Classic OpenWire SSL transport

Classic broker có thể khai báo transport connector trong activemq.xml:

~~~xml
<transportConnector
    name="openwire"
    uri="tcp://0.0.0.0:61616"/>
<transportConnector
    name="openwire-ssl"
    uri="ssl://0.0.0.0:61617"/>
~~~

SSL connector cần SSL context/keystore được cấu hình đúng cho broker theo release Classic đang chạy. Client Classic dùng **ssl://broker.example.internal:61617** và truststore phù hợp; khi mTLS, cấu hình thêm client key material theo ActiveMQSslConnectionFactory/JSSE.

Không kết nối **tcp://** plaintext vào SSL connector hoặc **ssl://** vào connector plaintext. Cả hai tình huống đều có thể hiện thành reset/handshake error chứ không phải lỗi password.

### 9.3. Spring Boot: xác nhận property đúng starter

Với Artemis starter:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://broker.example.internal:61616
~~~

Credential được bind qua environment **SPRING_ARTEMIS_USER** và **SPRING_ARTEMIS_PASSWORD**.

Với Classic starter tương thích:

~~~yaml
spring:
  activemq:
    broker-url: tcp://broker.example.internal:61616
~~~

Credential được bind qua environment **SPRING_ACTIVEMQ_USER** và **SPRING_ACTIVEMQ_PASSWORD**. Hai cấu hình trên thuộc **hai starter khác nhau**. Không giữ đồng thời cả hai rồi suy rằng Spring tự chọn đúng broker. Kiểm tra dependency, auto-configuration report và bean ConnectionFactory thực tế được inject vào JmsTemplate/listener.

Nếu dùng TLS qua JSSE, truststore phải được thiết lập trước khi SSLContext mặc định khởi tạo, ví dụ JVM options:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/client-truststore.p12
-Djavax.net.ssl.trustStorePassword=FROM_SECRET
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đối với Artemis, URI có thể bật **sslEnabled=true** và **verifyHost=true** theo provider option. Với Classic, dùng SSL transport và xác minh hostname verification theo client/JDK version; không giả định chỉ có ssl:// là đủ. Nếu application có nhiều TLS destinations, cân nhắc SSLContext riêng thay vì thay default truststore toàn JVM.

## 10. Log và bằng chứng cần thu thập

Chẩn đoán nhanh hơn khi client và broker logs được đối chiếu theo **cùng timestamp, hostname, connection ID và source IP**.

### 10.1. Broker-side

Thu thập:

- Log lúc broker startup: acceptor/transport nào bind thành công, port nào.
- Log authentication/authorization cùng user/principal (không có password).
- TLS handshake/certificate error, truststore load và certificate expiry.
- Connection count, remote address, consumer count.
- Broker restart, failover, address/queue creation và resource limit.
- Disk full, journal/storage errors, thread starvation và paging.

Artemis thường ghi log dưới thư mục instance **log/**; Classic thường có log file do log4j configuration quản lý. Vị trí chính xác tùy instance, container image và deployment. Trong Kubernetes:

~~~bash
kubectl logs -n messaging deploy/broker --since=15m
kubectl describe pod -n messaging -l app=broker
~~~

Nếu nhiều replica, chọn đúng pod xử lý endpoint mà client resolve tới. Đừng chỉ xem log của pod đang healthy rồi kết luận broker đã nhận kết nối.

### 10.2. Client-side

Ghi lại:

- Root cause exception và toàn bộ cause chain.
- URI đã che credentials/query secrets.
- Broker type, JMS client artifact/version, Java version.
- DNS answer và IP thực tế được kết nối.
- Thời điểm bắt đầu, timeout, retry count và thời điểm lỗi cuối.
- TLS peer subject/issuer/SAN (không ghi private key).
- Principal và destination operation bị từ chối.

Đừng chỉ ghi **JMSException: Could not connect**. Hãy lấy **linkedException**, **getCause()** và nested SSL/socket exception; lỗi gốc thường nằm sâu hơn wrapper JMS.

### 10.3. Cây quyết định theo lỗi thường gặp

| Exception / symptom | Tầng đầu tiên cần kiểm tra | Bằng chứng xác nhận |
| --- | --- | --- |
| UnknownHostException | DNS | Resolver không trả địa chỉ |
| ConnectException: refused | TCP/listener | Host reachable nhưng port không listen/reject |
| SocketTimeoutException khi connect | Network path | SYN không được phản hồi trong timeout |
| No route to host | Routing/firewall | Route/interface/network policy |
| SSLHandshakeException | TLS | Cause chain, OpenSSL handshake, broker TLS log |
| PKIX path building failed | Trust chain | CA/intermediate và truststore |
| No subject alternative names | Hostname identity | URL hostname so với certificate SAN |
| AuthenticationException / invalid credentials | Authentication | Broker security log, realm/user/secret |
| Not authorized / security exception | Authorization | Role và destination permission |
| InvalidClientIDException | JMS client identity | ClientID trùng hoặc không được policy cho phép |
| Destination does not exist | Destination policy | Queue/address provisioning và auto-create |
| Connection limit/resource exhausted | Capacity/quota | Connection count, max connections, broker logs |

Tên exception cụ thể có thể khác theo provider/version. Luôn đọc **root cause**, không chỉ map bằng một chuỗi message chung.

## 11. Quy trình khôi phục sự cố có kiểm soát

Khi hệ thống production mất kết nối, thứ tự thao tác cần giảm rủi ro và giữ lại bằng chứng.

### Bước 1 — Xác định phạm vi

- Một instance hay tất cả app clients?
- Một broker hay nhiều broker?
- Chỉ một subnet/zone hay toàn hệ thống?
- Lỗi chỉ xảy ra khi deploy/rotate secret/restart broker?
- Chỉ TLS port hay cả plaintext test port trong mạng quản trị?

Nếu chỉ một pod lỗi, kiểm tra environment, DNS, secret mount, image và node networking của pod đó trước khi thay cấu hình toàn broker.

### Bước 2 — Kiểm tra endpoint mà không tạo thay đổi

1. Lấy URI đã che secret từ runtime config.
2. Resolve DNS từ đúng runtime.
3. Kiểm tra TCP tới port.
4. Xem broker listener/acceptor và log.
5. Nếu TLS, xác minh chain và SAN.
6. Thử auth bằng service account đã cấp phép.
7. Chạy JMS probe trên queue diagnostics.

Không restart broker chỉ để “thử lại” khi chưa xác định lỗi nằm ở client hay server. Restart có thể làm mất log, tạo reconnect storm và ảnh hưởng các producer/consumer đang hoạt động.

### Bước 3 — Sửa đúng một nguyên nhân đã chứng minh

| Bằng chứng | Thao tác |
| --- | --- |
| URI sai protocol/port | Sửa config client hoặc broker listener theo protocol đã chọn |
| DNS sai record | Sửa DNS/service/hosts trong đúng môi trường |
| Broker bind localhost | Bind interface đúng và giới hạn firewall |
| Container port chưa publish | Sửa mapping/Service targetPort, không đổi port ngẫu nhiên |
| CA/intermediate thiếu | Cập nhật truststore/chain |
| SAN không khớp | Dùng endpoint đúng hoặc cấp certificate mới đúng SAN |
| Client cert không được trust | Kiểm tra clientAuth, CA và broker truststore |
| Secret cũ | Rollout/reload credential đúng cách |
| Role thiếu permission | Cấp quyền send/consume tối thiểu |
| Connection quota đầy | Tìm connection leak/consumer leak và điều chỉnh quota theo capacity |

### Bước 4 — Xác minh sau khắc phục

- Kết nối bằng đúng client/provider và service account production.
- Xác nhận broker nhận connection từ đúng IP/principal.
- Gửi và nhận một message có **probeId duy nhất** trên destination test.
- Kiểm tra message được ACK, không còn in-flight hoặc DLQ bất thường.
- Với TLS, chạy lại cả positive test và negative test hostname sai.
- Kiểm tra reconnect sau khi broker/client restart nếu sự cố liên quan recovery.
- Theo dõi connection count, reconnect rate và broker logs trong một cửa sổ đủ dài.

### Bước 5 — Ghi lại nguyên nhân gốc

Incident record nên ghi:

~~~text
Incident ID:
Start/end time:
Affected applications/pods:
Broker type/version:
JMS client artifact/version:
Protocol and sanitized URI:
DNS result:
TCP test:
TLS result (chain/SAN/client cert):
Authentication result:
Authorization/destination:
Root cause:
Corrective change:
JMS probeId:
Recovery time:
Messages pending/redelivered/DLQ:
Follow-up action:
~~~

Không lưu credential, private key, truststore password hoặc nội dung message nhạy cảm trong incident record.

## 12. Checklist ngăn lỗi kết nối tái diễn

| Hạng mục | Kiểm tra định kỳ |
| --- | --- |
| URI | Scheme, host, port, protocol và query options khớp provider |
| DNS | A/AAAA record, TTL, search domain và failover endpoints |
| TCP | Listener bind đúng interface, firewall/source CIDR |
| Docker/Kubernetes | Service/targetPort, endpoints, NetworkPolicy và DNS trong namespace |
| TLS | Certificate expiry, SAN, chain, TLS protocol và hostname verification |
| mTLS | Client cert expiry, clientAuth EKU, broker truststore và rotation |
| Authentication | Secret rollout, realm/JAAS/LDAP health, account lockout |
| Authorization | Send/consume permission đúng destination, least privilege |
| Capacity | Connection/consumer count, max connections, thread/disk/resource limit |
| Recovery | Reconnect policy, broker restart và TLS context refresh đã thử |
| Observability | Client root cause, broker security logs, connection metrics và alerts |
| Smoke test | Probe queue có owner, cleanup policy và service account riêng |

**Kết luận:** Khi ActiveMQ Classic hoặc Artemis không kết nối được, hãy lần lượt chứng minh **URI/protocol đúng → DNS đúng → TCP listener reachable → TLS identity hợp lệ → authentication thành công → authorization cho phép destination → JMS send/receive thành công**. Connection refused, timeout, PKIX, SAN mismatch và invalid credentials là các loại lỗi khác nhau; sửa đúng tầng giúp phục hồi nhanh mà không hạ bảo mật hoặc mở rộng quyền không cần thiết.
