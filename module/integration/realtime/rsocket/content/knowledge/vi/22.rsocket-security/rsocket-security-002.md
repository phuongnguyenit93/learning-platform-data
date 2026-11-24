# Bảo vệ truyền tải bằng TLS, WSS và kiểm tra chứng chỉ

## Mục tiêu bài học

RSocket truyền dữ liệu trên các byte-stream transport như TCP và WebSocket. Nếu kết nối đi qua mạng không tin cậy, cần mã hóa và xác thực peer ở tầng transport. Với TCP, có thể bọc kết nối bằng TLS. Với WebSocket, dùng WebSocket Secure (WSS), tức WebSocket chạy trên TLS.

Sau bài này, bạn có thể:

- Phân biệt RSocket TCP có TLS với RSocket chạy trên WSS.
- Giải thích TLS handshake diễn ra trước RSocket SETUP như thế nào.
- Cấu hình chứng chỉ và private key cho RSocket server bằng Spring Boot.
- Cấu hình WSS cho server WebFlux tích hợp và server WebSocket độc lập.
- Cấu hình client tin cậy CA và kiểm tra hostname/SAN.
- Giải thích SNI, certificate chain, trust store và mutual TLS (mTLS).
- Kiểm tra chứng chỉ bằng OpenSSL và xử lý lỗi handshake thường gặp.
- Lập kế hoạch gia hạn, xoay vòng chứng chỉ và bảo vệ private key.

## TLS bảo vệ lớp nào trong RSocket?

RSocket là giao thức ứng dụng. Nó định nghĩa SETUP, request-response, fire-and-forget, stream, channel, metadata, backpressure và các frame khác. TCP hoặc WebSocket là transport mang byte của RSocket.

TLS tạo một kênh được mã hóa giữa hai peer trước khi RSocket bắt đầu trao đổi frame. Vì vậy, khi TLS được cấu hình đúng:

- Data payload và metadata RSocket được bảo vệ khi truyền trên kết nối.
- Route, token, correlation ID và nội dung nghiệp vụ không bị đọc trực tiếp bởi bên nghe lén trên đường truyền.
- TLS kiểm tra chứng chỉ của server để client biết mình đang kết nối tới endpoint được tin cậy.
- Nếu bật mTLS, server cũng yêu cầu và kiểm tra chứng chỉ của client.

TLS không thay thế xác thực và phân quyền nghiệp vụ ở tầng RSocket. Chứng chỉ server xác nhận danh tính endpoint ở tầng truyền tải; JWT hoặc RSocket Authentication Metadata có thể xác định người dùng hay service được phép gọi route nào.

## Phân biệt TCP+TLS, WS và WSS

| Kiểu kết nối | Transport | Bảo vệ truyền tải | Cách định địa chỉ |
|---|---|---|---|
| RSocket TCP | TCP trực tiếp | Không có TLS nếu chưa cấu hình | Host và port |
| RSocket TCP+TLS | TCP được bọc TLS | TLS handshake trực tiếp trên socket | Host và port TLS |
| RSocket WebSocket | HTTP Upgrade rồi WebSocket | Không có TLS nếu dùng WS | URL WebSocket |
| RSocket WSS | WebSocket trên TLS | TLS bảo vệ handshake HTTP và các frame WebSocket | URL secure WebSocket |

WSS không phải một interaction type khác của RSocket. Sau khi WebSocket được nâng cấp thành công và RSocket SETUP hoàn tất, ứng dụng vẫn dùng cùng các kiểu request-response, fire-and-forget, request-stream và request-channel.

Với client trình duyệt, trang HTTPS nên kết nối tới endpoint WSS. Kết nối WS không mã hóa từ một trang HTTPS thường bị trình duyệt chặn như mixed content.

## Trình tự kết nối có TLS

TLS handshake hoàn tất trước khi hai phía trao đổi RSocket SETUP. Nếu chứng chỉ không hợp lệ, RSocket chưa có cơ hội xử lý route hoặc payload nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    C->>S: TCP connect
    Note over C,S: TLS ClientHello / ServerHello
    S-->>C: Server certificate chain
    C->>C: Kiểm tra CA, thời hạn và hostname/SAN
    opt mTLS
        C->>S: Client certificate
        S->>S: Kiểm tra CA và danh tính client
    end
    S-->>C: TLS handshake complete
    C->>S: RSocket SETUP (đã mã hóa)
    S-->>C: Session sẵn sàng
    C->>S: REQUEST_* và PAYLOAD (đã mã hóa)
~~~

Các bước quan trọng:

1. Client kết nối tới địa chỉ và port của server.
2. Hai phía thương lượng phiên bản TLS, cipher suite và các tham số liên quan.
3. Server gửi chứng chỉ và chuỗi chứng chỉ cần thiết.
4. Client kiểm tra chuỗi chứng chỉ có dẫn tới CA được tin cậy hay không.
5. Client kiểm tra chứng chỉ còn hiệu lực và tên endpoint khớp với hostname mà client gọi.
6. Nếu dùng mTLS, server yêu cầu client gửi chứng chỉ và kiểm tra nó.
7. Sau TLS handshake, RSocket mới gửi SETUP và bắt đầu trao đổi frame.

Nếu TLS handshake thất bại, hãy điều tra trust store, hostname, thời hạn, chuỗi chứng chỉ, TLS protocol và cấu hình mTLS trước khi kiểm tra handler RSocket.

## Các thành phần của một chứng chỉ X.509

Một chứng chỉ server thường gồm:

- **Subject:** thông tin chủ thể được chứng chỉ đại diện.
- **Issuer:** CA đã ký chứng chỉ.
- **Validity:** thời điểm bắt đầu và kết thúc hiệu lực.
- **Subject Alternative Name (SAN):** danh sách DNS name hoặc địa chỉ IP mà chứng chỉ đại diện.
- **Key Usage / Extended Key Usage:** mục đích được phép dùng khóa, ví dụ TLS server authentication.
- **Public key:** khóa công khai được peer dùng trong quá trình xác thực và thiết lập khóa phiên.
- **Signature:** chữ ký của issuer để xác nhận chứng chỉ không bị sửa đổi.

Client cần xác minh chuỗi từ chứng chỉ server qua các intermediate CA tới một trust anchor mà nó tin cậy. Server nên gửi đầy đủ intermediate certificate cần thiết. Thông thường không cần gửi root CA vì root đã nằm trong trust store của client.

### SAN và hostname verification

Chứng chỉ phải có SAN khớp với hostname mà client sử dụng:

- Client kết nối rsocket.example.com thì SAN cần có DNS:rsocket.example.com hoặc wildcard hợp lệ theo quy tắc hostname.
- Client kết nối bằng địa chỉ IP thì chứng chỉ cần có SAN dạng IP tương ứng.
- Không nên dựa vào Common Name (CN) như cách thay thế SAN.

Hai việc kiểm tra khác nhau:

1. **Chain validation:** chứng chỉ được ký bởi CA mà client tin cậy, còn hạn và đáp ứng các ràng buộc.
2. **Hostname verification:** chứng chỉ đó được cấp cho đúng máy chủ mà client đang gọi.

Chỉ kiểm tra CA mà bỏ qua hostname có thể khiến client chấp nhận một chứng chỉ hợp lệ nhưng thuộc về máy chủ khác.

### SNI không thay thế hostname verification

SNI (Server Name Indication) cho phép client gửi tên server mong muốn trong TLS ClientHello. Server có thể dùng tên này để chọn chứng chỉ phù hợp khi nhiều domain cùng dùng một địa chỉ IP.

SNI giúp server chọn đúng chứng chỉ; hostname verification giúp client xác nhận chứng chỉ được gửi có khớp tên server hay không. Cả hai có vai trò riêng.

## Cấu hình TLS cho RSocket TCP server bằng Spring Boot

Spring Boot hỗ trợ SSL cho RSocket server qua nhóm thuộc tính spring.rsocket.server.ssl.*. Có thể dùng SSL bundle để quản lý certificate và private key theo một tên cấu hình.

Ví dụ dùng PEM certificate chain và private key:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        rsocket-server:
          keystore:
            certificate: file:/etc/rsocket/server-chain.pem
            private-key: file:/etc/rsocket/server-key.pem

  rsocket:
    server:
      transport: tcp
      port: 7001
      ssl:
        bundle: rsocket-server
        enabled-protocols:
          - TLSv1.3
          - TLSv1.2
~~~

Trong ví dụ:

- server-chain.pem chứa chứng chỉ server và các intermediate certificate cần thiết.
- server-key.pem là private key tương ứng, cần được bảo vệ như một secret.
- spring.ssl.bundle.pem.rsocket-server định nghĩa bộ trust material có tên rsocket-server.
- spring.rsocket.server.ssl.bundle gắn bundle vào RSocket server.
- enabled-protocols giới hạn các phiên bản TLS được chấp nhận.

Spring Boot cũng hỗ trợ JKS hoặc PKCS12 keystore. Ví dụ PEM dễ dùng với certificate do CA hoặc hệ thống quản lý secret cấp; PKCS12 thuận tiện khi certificate và private key đã được đóng gói trong một keystore.

Ví dụ cấu hình PKCS12:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7001
      ssl:
        key-store: file:/etc/rsocket/server.p12
        key-store-password: <LOAD_FROM_SECRET>
        key-store-type: PKCS12
        key-alias: rsocket-server
        protocol: TLS
        enabled-protocols:
          - TLSv1.3
          - TLSv1.2
~~~

Không đưa password keystore hoặc private key vào Git. Dùng secret manager, secret mount hoặc cơ chế quản lý bí mật của nền tảng triển khai.

### Các thuộc tính SSL RSocket server thường dùng

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.rsocket.server.ssl.bundle | Tên SSL bundle đã khai báo |
| spring.rsocket.server.ssl.certificate | Đường dẫn PEM certificate |
| spring.rsocket.server.ssl.certificate-private-key | Đường dẫn PEM private key |
| spring.rsocket.server.ssl.key-store | Keystore chứa certificate và private key |
| spring.rsocket.server.ssl.key-store-password | Password của keystore |
| spring.rsocket.server.ssl.key-store-type | Loại keystore, ví dụ PKCS12 |
| spring.rsocket.server.ssl.trust-store | Trust store dùng để xác minh chứng chỉ client trong mTLS |
| spring.rsocket.server.ssl.client-auth | Chính sách yêu cầu chứng chỉ client |
| spring.rsocket.server.ssl.enabled-protocols | Các phiên bản TLS được cho phép |

Tên và khả năng của property phụ thuộc phiên bản Spring Boot. Kiểm tra bảng Common Application Properties của đúng phiên bản đang dùng trước khi triển khai.

## Cấu hình WSS cho server WebFlux tích hợp

Một ứng dụng Spring Boot WebFlux có thể gắn RSocket WebSocket vào HTTP server hiện có. Trong mô hình này, RSocket dùng chung listener HTTPS của WebFlux; TLS được cấu hình ở web server bằng server.ssl.* hoặc SSL bundle.

Ví dụ:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        web-server:
          keystore:
            certificate: file:/etc/rsocket/web-chain.pem
            private-key: file:/etc/rsocket/web-key.pem

  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket

server:
  port: 8443
  ssl:
    bundle: web-server
~~~

Client kết nối tới endpoint WebSocket bảo mật tại:

~~~text
https://rsocket.example.com:8443/rsocket
~~~

Trong API Spring RSocketRequester.Builder.websocket(URI), tài liệu Spring minh họa endpoint secure WebSocket bằng URI có scheme https. Client WebSocket thuần thường biểu diễn endpoint tương đương bằng scheme wss://.

Điều kiện quan trọng của chế độ tích hợp:

- Ứng dụng phải là WebFlux reactive application.
- RSocket được gắn vào web server tại mapping path.
- Spring Boot hỗ trợ kiểu tích hợp này với Reactor Netty.
- TLS thuộc về HTTP/WebFlux listener; không cần mở một RSocket TCP port độc lập.

## Cấu hình WSS cho server WebSocket độc lập

Nếu muốn RSocket WebSocket có port riêng, cấu hình server transport là websocket, khai báo port và SSL bundle ở nhóm RSocket server:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        rsocket-ws:
          keystore:
            certificate: file:/etc/rsocket/ws-chain.pem
            private-key: file:/etc/rsocket/ws-key.pem

  rsocket:
    server:
      transport: websocket
      port: 8443
      ssl:
        bundle: rsocket-ws
~~~

Đây là embedded WebSocket listener riêng. Nó không dùng chung port HTTPS của WebFlux. Khi triển khai, mở đúng port TCP ở firewall, load balancer hoặc container service.

Không nhầm hai mô hình:

| Mô hình | TLS được cấu hình tại | Port |
|---|---|---|
| WSS tích hợp WebFlux | server.ssl.* hoặc server.ssl.bundle | Port HTTPS của web server |
| WSS độc lập | spring.rsocket.server.ssl.* | Port riêng của RSocket server |
| RSocket TCP+TLS độc lập | spring.rsocket.server.ssl.* | Port TCP riêng của RSocket |

## Client RSocket TCP+TLS và trust store

Client cần tin cậy CA đã ký chứng chỉ server. Với chứng chỉ do CA công khai cấp, trust store mặc định của JVM thường đã có root CA tương ứng. Với CA nội bộ hoặc private PKI, cần thêm CA đó vào trust store hoặc cấu hình trust material riêng cho client.

Ví dụ dưới đây dùng Reactor Netty để tạo TCP transport có TLS và chỉ tin cậy CA nội bộ đã chỉ định:

~~~java
import java.io.File;

import io.rsocket.transport.netty.client.TcpClientTransport;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.netty.tcp.TcpClient;
import reactor.netty.tcp.TcpSslContextSpec;

class SecureRSocketClientFactory {

    RSocketRequester connect(RSocketRequester.Builder requesterBuilder) {
        TcpSslContextSpec sslContext = TcpSslContextSpec.forClient()
            .configure(builder -> builder
                .trustManager(new File("certs/internal-root-ca.pem"))
                .endpointIdentificationAlgorithm("HTTPS")
            );

        TcpClient tcpClient = TcpClient.create()
            .host("rsocket.example.com")
            .port(7001)
            .secure(ssl -> ssl.sslContext(sslContext));

        return requesterBuilder.transport(
            TcpClientTransport.create(tcpClient)
        );
    }
}
~~~

Các điểm cần hiểu:

- trustManager(...) chỉ định CA dùng để xác minh chuỗi chứng chỉ server.
- endpointIdentificationAlgorithm("HTTPS") bật kiểm tra hostname/SAN ở phía client.
- TcpClient.secure(...) bật TLS trên TCP transport.
- TcpClientTransport.create(tcpClient) chuyển cấu hình Reactor Netty thành transport mà RSocket sử dụng.
- RSocketRequester.Builder.transport(...) cho phép dùng transport đã được cấu hình thay vì helper TCP mặc định.

Nếu dùng Netty 4.1, không nên giả định hostname verification tự bật mặc định. Netty 4.2 đã thay đổi mặc định theo hướng bật endpoint verification, nhưng khai báo rõ ràng giúp cấu hình dễ đọc và tránh phụ thuộc khác biệt phiên bản.

Nếu server dùng CA công khai, có thể dùng trust store mặc định của JVM. Nếu dùng CA nội bộ, đừng thay thế toàn bộ trust store mặc định bằng một CA đơn lẻ nếu cùng JVM còn cần kết nối tới dịch vụ công khai khác; hãy quản lý trust anchors phù hợp với ứng dụng.

## Client WSS với RSocketRequester

Với endpoint WSS có chứng chỉ được JVM tin cậy, client Spring có thể tạo requester bằng URI secure WebSocket:

~~~java
import java.net.URI;

import org.springframework.messaging.rsocket.RSocketRequester;

class SecureWebSocketRequesterFactory {

    RSocketRequester connect(RSocketRequester.Builder requesterBuilder) {
        URI endpoint = URI.create(
            "https://rsocket.example.com/rsocket"
        );

        return requesterBuilder.websocket(endpoint);
    }
}
~~~

Spring Framework dùng URI secure để thiết lập WebSocket trên TLS. Nếu endpoint dùng CA công khai, trust store mặc định thường đủ. Nếu endpoint dùng private CA, hãy cấu hình trust material cho HTTP/WebSocket client tương ứng hoặc trust store của JVM.

Với Reactor Netty HTTP client tùy chỉnh, SSL được cấu hình qua HttpClient.secure(...); khi tự cung cấp một SslProvider, phải bảo đảm hostname verification được bật. Đừng thay bằng trust manager chấp nhận mọi chứng chỉ.

Trong môi trường trình duyệt, client kết nối bằng URL wss://. Trình duyệt dùng kho chứng chỉ của hệ điều hành hoặc nền tảng và tự thực hiện kiểm tra chứng chỉ/hostname trong quá trình TLS handshake.

## Mutual TLS: xác thực cả client và server

TLS thông thường xác thực server với client. Mutual TLS (mTLS) yêu cầu client cũng trình chứng chỉ để server xác minh danh tính ở tầng transport.

mTLS phù hợp khi các service trong mạng nội bộ cần xác thực lẫn nhau bằng chứng chỉ do private CA quản lý. Nó thường được dùng cùng authorization ở tầng ứng dụng.

Server cần:

1. Chứng chỉ và private key của chính server.
2. Trust store chứa CA được phép cấp chứng chỉ client.
3. Cấu hình yêu cầu client certificate.

Ví dụ dùng SSL bundle PEM:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        rsocket-mtls:
          keystore:
            certificate: file:/etc/rsocket/server-chain.pem
            private-key: file:/etc/rsocket/server-key.pem
          truststore:
            certificate: file:/etc/rsocket/client-ca.pem

  rsocket:
    server:
      transport: tcp
      port: 7001
      ssl:
        bundle: rsocket-mtls
        client-auth: need
~~~

Các chế độ client authentication thường gặp:

| Giá trị | Hành vi |
|---|---|
| none | Server không yêu cầu client certificate |
| want | Server yêu cầu certificate nhưng có thể chấp nhận client không gửi |
| need | Client phải gửi certificate hợp lệ; nếu không, handshake thất bại |

Client mTLS phải gửi certificate chain và private key của chính nó. Với Reactor Netty TCP:

~~~java
TcpSslContextSpec sslContext = TcpSslContextSpec.forClient()
    .configure(builder -> builder
        .trustManager(new File("certs/server-ca.pem"))
        .keyManager(
            new File("certs/client-chain.pem"),
            new File("certs/client-key-pkcs8.pem")
        )
        .endpointIdentificationAlgorithm("HTTPS")
    );
~~~

Private key client phải khớp với certificate client và ở định dạng mà Netty hỗ trợ, thường là PEM PKCS#8 trong ví dụ này.

mTLS xác thực danh tính của peer ở cấp kết nối. Nếu một kết nối được chia sẻ cho nhiều người dùng, chứng chỉ client không tự xác định người dùng cuối của từng request. Vẫn cần JWT, RSocket Authentication hoặc cơ chế định danh nghiệp vụ nếu ứng dụng cần authorization theo người dùng.

## TLS, mTLS và RSocket Security giải quyết các vấn đề khác nhau

| Cơ chế | Xác minh điều gì? | Bảo vệ chính |
|---|---|---|
| TLS một chiều | Client xác minh server | Mã hóa, toàn vẹn dữ liệu và xác thực server |
| mTLS | Hai phía xác minh chứng chỉ của nhau | Mã hóa và xác thực danh tính service/client ở tầng transport |
| RSocket Authentication | Danh tính hoặc credential của requester | Xác thực ở tầng RSocket |
| RSocket Authorization | Quyền thực hiện thao tác hoặc truy cập route | Kiểm soát truy cập nghiệp vụ |

TLS bảo vệ toàn bộ byte trên transport, gồm cả RSocket metadata và data. RSocket Security có thể xác thực tại SETUP hoặc từng request tùy mô hình kết nối. Nếu một connection dùng chung cho nhiều người dùng, xác thực tại request time thường phù hợp hơn việc gắn một user token duy nhất cho cả connection.

## Kiểm tra chứng chỉ trước khi triển khai

Có thể dùng OpenSSL để xem thông tin certificate:

~~~bash
openssl x509 -in server-chain.pem -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Kiểm tra:

- Subject và Issuer có đúng không.
- Certificate đã hết hạn hoặc chưa đến thời điểm hiệu lực chưa.
- SAN có chứa DNS name hoặc địa chỉ IP mà client sử dụng không.
- Extended Key Usage có cho phép TLS server authentication không.

Kiểm tra TLS handshake tới RSocket TCP server:

~~~bash
openssl s_client \
  -connect rsocket.example.com:7001 \
  -servername rsocket.example.com \
  -CAfile internal-root-ca.pem \
  -verify_hostname rsocket.example.com \
  -verify_return_error
~~~

Các tham số:

- -connect chọn host và port.
- -servername gửi SNI để server chọn certificate.
- -CAfile chỉ định CA dùng để xác minh chuỗi.
- -verify_hostname kiểm tra tên endpoint.
- -verify_return_error khiến lỗi xác minh được trả về rõ ràng.

Lệnh này kiểm tra TLS handshake. Nó không gửi RSocket SETUP hoặc gọi route nghiệp vụ. Sau khi TLS thành công, cần dùng một RSocket client để kiểm tra SETUP và request end-to-end.

Với WSS, có thể kiểm tra TLS ở port HTTPS bằng cùng cách gọi OpenSSL tới port đó. Sau đó dùng WebSocket/RSocket client để kiểm tra HTTP Upgrade, WebSocket subprotocol và RSocket SETUP.

## Kiểm tra trust store Java

Có thể xem nội dung trust store:

~~~bash
keytool -list -v -keystore client-truststore.p12 -storetype PKCS12
~~~

Thêm một CA nội bộ vào trust store:

~~~bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore client-truststore.p12 \
  -storetype PKCS12
~~~

Nếu ứng dụng dùng trust store này qua JVM system properties, có thể cấu hình lúc khởi động:

~~~bash
-Djavax.net.ssl.trustStore=/etc/rsocket/client-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<LOAD_FROM_SECRET>
~~~

Các thuộc tính JVM ảnh hưởng đến những client sử dụng default JSSE trust manager trong process. Với ứng dụng có nhiều kết nối tới các hệ thống khác nhau, SSL bundle hoặc trust store riêng cho từng client giúp cô lập trust policy tốt hơn.

## Lỗi TLS thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| PKIX path building failed | Client không tin CA, thiếu intermediate hoặc chain không hợp lệ | Kiểm tra trust store và full chain server gửi |
| No subject alternative DNS name | SAN không khớp hostname client gọi | Cấp lại certificate có DNS SAN đúng |
| CertificateExpiredException | Certificate hết hạn | Gia hạn và triển khai certificate mới |
| NotBefore chưa có hiệu lực | Thời gian hệ thống sai hoặc certificate chưa tới ngày hiệu lực | Đồng bộ clock và kiểm tra validity |
| unknown_ca khi mTLS | Server không tin CA cấp certificate client | Kiểm tra trust store phía server |
| bad_certificate | Certificate client không hợp lệ, không khớp private key hoặc thiếu chain | Kiểm tra key pair, EKU, chain và thời hạn |
| handshake_failure | TLS version, cipher, SNI hoặc mTLS không tương thích | Bật log TLS phù hợp và kiểm tra cấu hình hai phía |
| TCP connect được nhưng RSocket SETUP lỗi | TLS đã qua nhưng RSocket MIME type, protocol hoặc setup không tương thích | Kiểm tra RSocket client/server sau TLS |
| WSS TLS thành công nhưng WebSocket Upgrade thất bại | Sai path, proxy không hỗ trợ Upgrade hoặc subprotocol không khớp | Kiểm tra mapping path, reverse proxy và handshake |

Không nên khắc phục lỗi chứng chỉ bằng cách tắt kiểm tra certificate, bỏ hostname verification hoặc dùng trust manager chấp nhận tất cả. Hãy sửa trust chain, SAN, key pair hoặc cấu hình TLS thực tế.

## TLS termination tại reverse proxy

Trong môi trường triển khai, TLS có thể kết thúc ở load balancer hoặc reverse proxy:

~~~mermaid
flowchart LR
    C[Client] -->|WSS / TLS| P[Load balancer / Proxy]
    P -->|RSocket over WS or TCP| A[Spring Boot application]
~~~

Khi proxy kết thúc TLS:

- Client xác minh certificate của proxy, không phải certificate backend.
- Đoạn proxy tới ứng dụng có thể là plaintext nếu không cấu hình TLS tiếp.
- Nếu yêu cầu mã hóa end-to-end giữa proxy và backend, cấu hình TLS hoặc mTLS cho hop nội bộ.
- Proxy phải hỗ trợ WebSocket Upgrade và giữ kết nối lâu dài.
- Nếu dùng raw RSocket TCP, proxy phải hỗ trợ TCP pass-through hoặc TCP proxy; HTTP reverse proxy thông thường không tự hiểu RSocket TCP.

Ghi rõ ranh giới tin cậy trong kiến trúc. WSS từ client đến proxy không tự động mã hóa đoạn proxy đến backend.

## Gia hạn và xoay vòng chứng chỉ

Certificate có thời hạn. Quy trình vận hành cần tránh để chứng chỉ hết hạn làm gián đoạn mọi client cùng lúc.

Một quy trình xoay vòng an toàn thường gồm:

1. Theo dõi ngày hết hạn của certificate server và client.
2. Tạo key pair mới và cấp certificate mới với SAN/EKU phù hợp.
3. Nếu đổi CA, triển khai trust anchor mới cho client trước khi server đổi certificate.
4. Duy trì giai đoạn chấp nhận cả CA cũ và mới khi cần chuyển đổi.
5. Triển khai certificate chain mới lên server.
6. Khởi động lại hoặc reload SSL context theo khả năng của phiên bản và cách cấu hình.
7. Kiểm thử handshake, hostname verification, mTLS và RSocket SETUP.
8. Thu hồi hoặc loại bỏ trust anchor cũ sau khi toàn bộ peer đã chuyển đổi.

Private key cần được quản lý như secret: giới hạn quyền đọc, không commit vào repository, không ghi ra log và không đưa vào image container công khai. Với mTLS, cần có quy trình cấp, thu hồi và thay certificate cho cả client lẫn server.

## Kiểm thử bảo mật truyền tải

Một bộ kiểm thử tích hợp nên bao gồm:

1. Client kết nối thành công với certificate hợp lệ và hostname khớp SAN.
2. Client từ chối certificate do CA không tin cậy cấp.
3. Client từ chối certificate hết hạn hoặc chưa có hiệu lực.
4. Client từ chối certificate có SAN không khớp hostname.
5. Server từ chối client không có certificate khi mTLS dùng need.
6. Server từ chối client certificate do CA không tin cậy cấp.
7. Client mTLS hợp lệ có thể hoàn tất handshake.
8. WSS thực hiện HTTP Upgrade đúng path và sau đó RSocket SETUP thành công.
9. Certificate rotation không làm client mất khả năng xác minh.
10. TLS lỗi được phân biệt với lỗi RSocket route hoặc lỗi nghiệp vụ.

Trong test local, có thể dùng CA và certificate tự ký dành riêng cho môi trường kiểm thử. Không đưa CA test hoặc trust-all cấu hình vào production.

## Checklist triển khai

Trước khi đưa RSocket TCP+TLS hoặc WSS vào môi trường thật, hãy trả lời:

1. Transport là TCP+TLS, WSS độc lập hay WSS tích hợp WebFlux?
2. TLS được kết thúc ở Spring Boot hay reverse proxy?
3. Server certificate có đầy đủ intermediate chain không?
4. SAN có khớp chính xác hostname hoặc IP client sử dụng không?
5. Client có trust store chứa CA hợp lệ không?
6. Hostname verification có được bật không?
7. SNI có gửi đúng tên domain khi cần chọn certificate không?
8. Có yêu cầu mTLS không và server dùng trust store nào để xác minh client?
9. RSocket Authentication và Authorization có được cấu hình riêng khi cần không?
10. Có giám sát thời hạn certificate, quy trình rotation và test handshake không?

TLS bảo vệ kết nối RSocket TCP; WSS bảo vệ RSocket chạy trên WebSocket. Client phải xác minh cả chuỗi CA lẫn hostname/SAN, còn mTLS bổ sung xác thực chứng chỉ client ở tầng transport. Khi tách rõ TLS, RSocket Security và authorization nghiệp vụ, đồng thời quản lý certificate lifecycle có kiểm soát, hệ thống realtime có thể bảo vệ dữ liệu và danh tính peer trong suốt vòng đời kết nối.

## Tài liệu tham khảo

- [Spring Boot Reference: RSocket server auto-configuration](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot Reference: SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot 3.5: Common Application Properties — RSocket SSL](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework Reference: RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Reactor Netty Reference: TCP Client SSL/TLS](https://projectreactor.io/docs/netty/release/reference/tcp-client.html)
- [Reactor Netty Reference: TCP Server SSL/TLS](https://projectreactor.io/docs/netty/release/reference/tcp-server.html)
- [Netty API: SslContextBuilder and endpoint identification](https://netty.io/4.1/api/io/netty/handler/ssl/SslContextBuilder.html)
- [Spring Security Reference: RSocket Authentication](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)

