# TLS, mTLS, chứng thư và truststore khi kết nối sổ đăng ký

Spring Cloud Service Discovery thường cần kết nối tới một hệ thống registry như Eureka, Consul hoặc ZooKeeper. Kết nối này mang thông tin đăng ký service, danh sách instance, metadata và đôi khi cả thông tin xác thực. Nếu truyền qua mạng không tin cậy, cần bảo vệ kênh giao tiếp bằng TLS để chống nghe lén, sửa đổi dữ liệu và giả mạo máy chủ.

TLS một chiều xác thực máy chủ với client. Mutual TLS (mTLS) xác thực cả máy chủ lẫn client bằng chứng thư số. Để thiết lập kết nối, ứng dụng phải tin cậy chứng thư của registry thông qua truststore; khi registry yêu cầu client certificate, ứng dụng còn cần keystore chứa private key và certificate chain của chính nó.

Bài viết giải thích cách các thành phần này phối hợp, cách cấu hình kết nối bảo mật với Eureka, Consul và ZooKeeper, cùng quy trình kiểm tra, luân chuyển chứng thư và xử lý lỗi handshake. Các ví dụ dùng Java JSSE và cấu hình Spring Cloud phổ biến; tên thuộc tính hoặc cách cài SSL context có thể khác theo phiên bản và HTTP transport của từng starter.

## 1. TLS bảo vệ kết nối tới registry

TLS (Transport Layer Security) tạo một kênh được mã hóa giữa hai đầu kết nối. Trong service discovery, một đầu thường là ứng dụng Spring Boot và đầu còn lại là Eureka Server, Consul agent hoặc ZooKeeper server.

TLS cung cấp ba thuộc tính quan trọng:

- **Bảo mật dữ liệu:** bên trung gian không thể đọc nội dung request/response nếu không có khóa phù hợp.
- **Toàn vẹn dữ liệu:** phát hiện dữ liệu bị thay đổi trong quá trình truyền.
- **Xác thực peer:** client xác minh danh tính server; với mTLS, server cũng xác minh danh tính client.

Khi client gọi registry bằng HTTP thường, dữ liệu đăng ký, service ID, địa chỉ instance và token ACL có thể bị quan sát hoặc sửa đổi bởi bên có khả năng nghe lén/chèn lưu lượng trên đường truyền. HTTPS bảo vệ kênh đó, nhưng không tự quyết định client được phép đăng ký hoặc đọc service nào. Quyền truy cập vẫn cần ACL, authentication và authorization ở tầng ứng dụng.

### TLS một chiều và mTLS

| Đặc điểm | TLS một chiều | Mutual TLS |
|---|---|---|
| Server gửi certificate | Có | Có |
| Client xác minh certificate của server | Có | Có |
| Client gửi certificate | Không bắt buộc | Có |
| Server xác minh certificate của client | Không | Có |
| Mục tiêu | Client biết mình đang kết nối đúng registry | Hai bên cùng xác thực danh tính ở tầng TLS |

Trong TLS một chiều, ứng dụng Spring Boot cần tin cậy CA đã ký certificate của registry. Trong mTLS, registry cũng cần tin cậy CA đã ký certificate của client và được cấu hình yêu cầu client certificate.

~~~mermaid
sequenceDiagram
    participant C as Spring Cloud client
    participant R as Registry
    C->>R: ClientHello
    R-->>C: Server certificate và handshake data
    C->>C: Xác minh chain, hạn dùng và hostname
    opt mTLS
        R-->>C: CertificateRequest
        C->>C: Chọn client certificate và private key
        C->>R: Client certificate và proof of private key
        R->>R: Xác minh client certificate
    end
    C->>R: Hoàn tất TLS handshake
    C->>R: HTTP request đăng ký hoặc tra cứu
    R-->>C: HTTP response
~~~

TLS chỉ thiết lập kênh và xác thực peer theo certificate. Registry vẫn cần kiểm tra quyền của client sau khi handshake hoàn tất.

## 2. Certificate, CA, chain và SAN

Certificate X.509 là tài liệu số liên kết danh tính với public key. Certificate thường chứa subject, issuer, thời hạn hiệu lực, public key, các extension và chữ ký của CA.

Các vai trò:

- **Root CA:** CA gốc được client tin cậy trực tiếp.
- **Intermediate CA:** CA trung gian dùng để ký certificate server hoặc client.
- **Server certificate:** certificate mà registry trình ra khi client kết nối.
- **Client certificate:** certificate ứng dụng trình ra khi registry yêu cầu mTLS.
- **Private key:** khóa bí mật tương ứng với public key trong certificate; phải được bảo vệ nghiêm ngặt.

Server thường gửi certificate cùng các intermediate certificate cần thiết để client xây dựng chain tới một CA được tin cậy. Root CA thường được cài sẵn trong truststore của client và không nhất thiết phải gửi trong handshake.

### SAN và hostname verification

Client phải xác minh tên máy trong URL khớp với Subject Alternative Name (SAN) của server certificate. Ví dụ, nếu cấu hình registry là https://eureka.internal:8761, certificate cần có DNS SAN phù hợp với eureka.internal.

Nếu client kết nối bằng IP, certificate cần có IP SAN tương ứng. Chỉ đặt hostname trong Common Name không còn là cách đáng tin cậy để thay thế SAN trong các client TLS hiện đại.

Không tắt hostname verification để chữa lỗi certificate mismatch. Hãy sửa DNS, URL hoặc phát hành certificate có SAN đúng. Việc bỏ xác minh hostname khiến client có thể chấp nhận một server giả dù chain certificate hợp lệ.

### EKU và mục đích sử dụng certificate

Certificate có thể giới hạn mục đích sử dụng qua Extended Key Usage (EKU):

- Server certificate cần mục đích **serverAuth**.
- Client certificate dùng cho mTLS cần mục đích **clientAuth**.

Certificate hết hạn, chưa đến thời điểm hiệu lực, thiếu intermediate CA hoặc có EKU không phù hợp đều có thể khiến handshake thất bại. Đồng hồ hệ thống của client và server cũng cần được đồng bộ để kiểm tra thời hạn chính xác.

## 3. Truststore và keystore khác nhau thế nào?

Đây là hai khái niệm thường bị nhầm lẫn:

| Thành phần | Nội dung chính | Dùng ở đâu |
|---|---|---|
| Truststore | Certificate CA hoặc certificate được tin cậy | Client xác minh server; server xác minh client khi mTLS |
| Keystore | Private key cùng certificate chain tương ứng | Client trình client certificate; server trình server certificate |

Truststore trả lời câu hỏi: “Tôi tin cậy certificate do CA nào ký?”. Keystore trả lời câu hỏi: “Tôi sở hữu private key nào và có thể chứng minh danh tính nào?”.

Ví dụ:

~~~text
Spring Boot client
  registry-truststore.p12
    - registry-root-ca
    - registry-intermediate-ca

  discovery-client-keystore.p12 (chỉ cần khi mTLS)
    - client private key
    - client certificate
    - intermediate certificate chain

Registry server
  registry-server-keystore.p12
    - server private key
    - server certificate
    - intermediate certificate chain

  client-ca-truststore.p12 (khi yêu cầu mTLS)
    - CA ký client certificate
~~~

Truststore có thể là JKS hoặc PKCS12. PKCS12 là định dạng phổ biến và có thể chứa cả certificate lẫn private key; tuy nhiên vai trò logic của file phụ thuộc nội dung và cách cấu hình, không chỉ phụ thuộc phần mở rộng.

Không đưa private key hoặc mật khẩu keystore vào Git, image Docker hay log. Dùng secret manager, Kubernetes Secret được bảo vệ, file mount có quyền truy cập giới hạn hoặc cơ chế quản lý khóa tương đương.

## 4. Chuẩn bị truststore cho ứng dụng Java

Nếu registry dùng certificate do CA nội bộ cấp, JVM cần tin cậy CA đó. Thông thường, đưa root CA và intermediate CA cần thiết vào truststore của client. Tránh chỉ import leaf certificate nếu tổ chức có quy trình cấp lại certificate thường xuyên; tin cậy CA giúp thay certificate server mà không phải cập nhật từng client, miễn là chain và chính sách CA vẫn hợp lệ.

Ví dụ tạo truststore PKCS12 từ file CA:

~~~bash
keytool -importcert -alias internal-registry-root -file registry-root-ca.crt -keystore registry-truststore.p12 -storetype PKCS12
~~~

Kiểm tra nội dung truststore:

~~~bash
keytool -list -v -keystore registry-truststore.p12 -storetype PKCS12
~~~

Lệnh import sẽ yêu cầu mật khẩu và xác nhận tin cậy. Trước khi chấp nhận certificate, phải xác minh fingerprint của CA qua một kênh độc lập đáng tin cậy. Không chấp nhận certificate chỉ vì nó xuất hiện trong một kết nối đang gặp lỗi.

### Chỉ định truststore cho JVM

Với HTTP client sử dụng JSSE default SSLContext, có thể cấu hình JVM:

~~~bash
java -Djavax.net.ssl.trustStore=/run/secrets/registry-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=REPLACE_WITH_SECRET -jar application.jar
~~~

Các system property này phải được đặt khi khởi động JVM, trước khi TLS context được tạo. Mật khẩu trong ví dụ chỉ là placeholder; trong triển khai thực tế nên lấy từ secret store hoặc cơ chế cấp secret của nền tảng, tránh để lộ trong process listing hoặc log.

Khi đặt javax.net.ssl.trustStore, JVM có thể chỉ dùng các trust anchor trong file được chỉ định thay cho truststore mặc định. Nếu ứng dụng còn gọi các HTTPS endpoint công cộng, cần bảo đảm truststore chứa cả CA công cộng cần thiết hoặc dùng SSL context riêng cho kết nối registry.

Một số HTTP client hoặc starter tạo SSLContext riêng. Khi đó system property toàn JVM có thể không được áp dụng như mong đợi. Cần kiểm tra HTTP transport đang dùng và cấu hình trust material theo extension point mà phiên bản đó hỗ trợ.

## 5. Cấu hình keystore cho mTLS phía client

Khi registry yêu cầu client certificate, ứng dụng cần có private key và certificate chain của chính nó. Ví dụ cấu hình JVM cho JSSE:

~~~bash
java -Djavax.net.ssl.trustStore=/run/secrets/registry-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=TRUSTSTORE_SECRET -Djavax.net.ssl.keyStore=/run/secrets/discovery-client-keystore.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -Djavax.net.ssl.keyStorePassword=KEYSTORE_SECRET -jar application.jar
~~~

Trong cấu hình này:

- Truststore xác minh certificate của registry.
- Keystore cung cấp client certificate và private key khi server yêu cầu.
- Registry cần tin cậy CA phát hành client certificate.
- Client certificate phải còn hiệu lực, có EKU phù hợp và được gắn với danh tính được phép truy cập.

Các thuộc tính JSSE trên áp dụng ở cấp JVM khi HTTP transport dùng SSLContext mặc định. Chúng có thể ảnh hưởng mọi kết nối TLS outbound của ứng dụng. Nếu các registry hoặc dịch vụ khác nhau yêu cầu identity khác nhau, nên dùng SSL context/HTTP client riêng cho từng đích khi thư viện tích hợp hỗ trợ, thay vì gửi cùng một client certificate tới tất cả endpoint.

## 6. TLS outbound khác với HTTPS inbound của Spring Boot

Ứng dụng Spring Boot có thể đồng thời:

- Mở HTTPS để consumer gọi API của service.
- Kết nối HTTPS tới Eureka Server hoặc Consul agent.

Đây là hai chiều kết nối độc lập.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: /run/secrets/inventory-server-keystore.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_SECRET
~~~

Cấu hình server.ssl ở trên điều khiển HTTPS inbound của embedded web server. Nó không tự cấu hình truststore hoặc client certificate cho kết nối outbound từ Eureka/Consul client.

Tương tự, cấu hình JVM truststore để gọi registry không tự bật HTTPS cho API của inventory-service. Nếu cần cả hai, phải cấu hình riêng server SSL và outbound registry client.

## 7. Kết nối Eureka Client qua HTTPS

Eureka Client sử dụng URL registry được khai báo trong cấu hình. Ví dụ:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal:8761/eureka/
~~~

URL phải khớp hostname, port và context path của Eureka Server. Certificate server phải có SAN phù hợp với eureka.internal, chain phải được JVM hoặc HTTP client tin cậy.

Nếu Eureka Server được bảo vệ bằng TLS một chiều, client cần truststore tin cậy CA của server. Nếu server yêu cầu mTLS, client còn cần keystore chứa client certificate. Cách truyền SSL context vào Eureka HTTP transport phụ thuộc phiên bản Spring Cloud Netflix và transport được cấu hình (ví dụ Jersey hoặc HTTP client khác). Không giả định server.ssl của ứng dụng tự áp dụng cho kết nối Eureka outbound.

Nếu Eureka Server nằm sau reverse proxy hoặc ingress, proxy có thể kết thúc TLS. Khi đó cần bảo đảm:

- Client kết nối tới hostname và certificate của proxy.
- Proxy xác thực hoặc chuyển tiếp client certificate nếu dùng mTLS.
- Đường từ proxy tới Eureka Server được bảo vệ theo yêu cầu nội bộ.
- Basic authentication hoặc cơ chế authorization của Eureka vẫn được cấu hình riêng nếu cần.

TLS/mTLS xác minh kênh và peer; nó không tự cấp quyền đăng ký hoặc đọc mọi service.

## 8. Kết nối Spring Cloud Consul Discovery qua HTTPS

Spring Cloud Consul Discovery thường giao tiếp với Consul agent qua HTTP API. Khi agent bật HTTPS, cấu hình scheme phù hợp:

~~~yaml
spring:
  cloud:
    consul:
      host: consul-agent.internal
      port: 8501
      scheme: https
      discovery:
        enabled: true
        register: true
        service-name: inventory-service
~~~

Port 8501 thường là HTTPS API port mặc định của Consul, nhưng có thể được thay đổi trong cấu hình agent. Hãy xác minh listener thực tế thay vì chỉ dựa vào số cổng mặc định.

Client cần tin cậy CA cấp certificate cho agent. Với HTTP transport dùng JSSE mặc định, JVM truststore có thể cung cấp CA. Nếu agent yêu cầu mTLS, cần cấu hình client identity cho HTTP client mà Spring Cloud Consul sử dụng. Cách cấu hình chi tiết phụ thuộc phiên bản Spring Cloud Consul và Consul client transport; kiểm tra property reference hoặc extension point tương ứng.

Nếu Consul dùng ACL, token là lớp xác thực/ủy quyền ở cấp API, độc lập với TLS. Cấp token quyền tối thiểu cho thao tác discovery và registration. Không nhúng token vào URL, log hoặc metadata service.

## 9. Kết nối ZooKeeper bằng TLS

Spring Cloud Zookeeper sử dụng Apache Curator và ZooKeeper client để giao tiếp với ensemble. ZooKeeper có thể cấu hình secure client port để client kết nối TLS. Đây là cấu hình ở phía ZooKeeper server và client transport; nó không được bật chỉ bằng server.ssl của ứng dụng Spring Boot.

Ở phía server, cần:

- Cấu hình secure client port và server certificate/private key.
- Cấu hình truststore hoặc trust material để xác minh client certificate nếu dùng mTLS.
- Giữ riêng các cổng quorum/election nội bộ và client secure port.

Ở phía Spring Cloud client, cần:

- Kết nối tới secure client port của ensemble.
- Bật chế độ secure của ZooKeeper client theo phiên bản đang dùng.
- Cung cấp truststore để xác minh server certificate.
- Cung cấp client keystore nếu server yêu cầu mTLS.

ZooKeeper/Curator có các thuộc tính SSL và cách tạo SSL context riêng theo phiên bản. Tên property, định dạng truststore và cách Spring Cloud chuyển cấu hình xuống Curator có thể khác nhau. Hãy đối chiếu tài liệu của ZooKeeper, Curator và Spring Cloud Zookeeper đúng phiên bản; không sao chép thuộc tính của Eureka hoặc Consul sang ZooKeeper.

Session ZooKeeper, ephemeral znode và watch vẫn hoạt động trên kết nối bảo mật. TLS bảo vệ đường truyền, còn session timeout quyết định vòng đời session và ephemeral node.

## 10. Cấu hình mTLS ở phía registry server

Client có keystore chỉ là một nửa cấu hình mTLS. Registry server phải được cấu hình yêu cầu và xác minh client certificate.

Về mặt khái niệm, server cần:

1. Server keystore chứa private key và certificate chain của registry.
2. Truststore chứa CA được phép phát hành client certificate.
3. Chế độ client authentication yêu cầu certificate nếu chính sách là bắt buộc.
4. Authorization ánh xạ danh tính certificate tới quyền API phù hợp.

Với một Spring Boot server dùng embedded server, cấu hình server-side mTLS có thể có dạng:

~~~yaml
server:
  port: 8761
  ssl:
    enabled: true
    key-store: /run/secrets/registry-server-keystore.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_SECRET
    trust-store: /run/secrets/registry-client-ca-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: CLIENT_CA_SECRET
    client-auth: need
~~~

Ví dụ này minh họa Spring Boot server yêu cầu client certificate. Eureka Server có thể chạy trên embedded server hoặc nằm sau proxy; nếu TLS kết thúc ở proxy, cấu hình mTLS phải đặt tại proxy và danh tính client phải được chuyển tiếp an toàn theo kiến trúc. Consul và ZooKeeper có cấu hình server riêng, không dùng trực tiếp YAML server.ssl của ứng dụng Spring Boot.

Khi mTLS được kết thúc ở proxy, không tin cậy một header client-certificate do client tự gửi. Proxy phải xóa header do bên ngoài cung cấp, tự xác minh certificate và chèn thông tin danh tính qua một kênh nội bộ được bảo vệ.

## 11. Quản lý certificate và luân chuyển khóa

Certificate có thời hạn. Nếu không theo dõi, registry hoặc client có thể đột ngột mất khả năng kết nối khi certificate hết hạn.

Một quy trình quản lý tốt gồm:

- Theo dõi ngày hết hạn của server và client certificate.
- Gia hạn trước thời điểm hết hạn đủ lâu để kiểm thử và triển khai.
- Dùng CA và chain nhất quán giữa các môi trường.
- Luân chuyển certificate theo giai đoạn: thêm CA mới vào truststore trước, triển khai certificate mới, xác minh toàn bộ client, rồi mới loại CA cũ khi không còn certificate phụ thuộc.
- Bảo vệ private key và giới hạn quyền đọc file.
- Có quy trình thu hồi certificate khi private key bị lộ.
- Đồng bộ thời gian hệ thống để tránh lỗi not-yet-valid hoặc expired.

Nếu truststore hoặc keystore được mount từ secret volume, việc file trên đĩa thay đổi không đảm bảo JVM hoặc HTTP client đang chạy tự nạp lại SSL context. Nhiều client chỉ đọc key material lúc khởi tạo. Cần xác minh khả năng reload động của transport; nếu không có, lên kế hoạch restart/rollout an toàn sau khi cập nhật secret.

Không xoay đồng thời CA, server certificate và client certificate trên toàn hệ thống mà không có giai đoạn tương thích. Một quy trình overlap giúp client cũ và mới đều xác minh được chain trong thời gian chuyển đổi.

## 12. Kiểm tra certificate và kết nối TLS

### Kiểm tra certificate server bằng OpenSSL

~~~bash
openssl s_client -connect eureka.internal:8761 -servername eureka.internal -showcerts -verify_return_error
~~~

Lệnh này giúp xem certificate chain và lỗi xác minh từ môi trường có OpenSSL. Để kiểm tra với CA nội bộ, có thể thêm CA file:

~~~bash
openssl s_client -connect eureka.internal:8761 -servername eureka.internal -CAfile registry-root-ca.crt -verify_return_error
~~~

Khi kiểm tra mTLS, client có thể cần cung cấp certificate và private key:

~~~bash
openssl s_client -connect consul-agent.internal:8501 -servername consul-agent.internal -CAfile registry-root-ca.crt -cert discovery-client.crt -key discovery-client.key -verify_return_error
~~~

Không dùng private key production trên máy kiểm thử không được bảo vệ. Các lệnh trên chỉ nên chạy từ môi trường được phép và với certificate thử nghiệm khi có thể.

### Kiểm tra truststore và keystore

~~~bash
keytool -list -v -keystore /run/secrets/registry-truststore.p12 -storetype PKCS12
keytool -list -v -keystore /run/secrets/discovery-client-keystore.p12 -storetype PKCS12
~~~

Kiểm tra:

- Alias cần dùng có tồn tại không.
- Truststore có CA đúng không.
- Keystore có PrivateKeyEntry và certificate chain đầy đủ không.
- Certificate còn hiệu lực và SAN/EKU đúng không.
- Mật khẩu và quyền đọc file có đúng không.

### Bật log TLS khi chẩn đoán

Trong môi trường kiểm thử, có thể bật debug JSSE:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar application.jar
~~~

Log TLS có thể chứa hostname, certificate metadata và thông tin kết nối nhạy cảm. Chỉ bật trong thời gian ngắn, lưu trữ có kiểm soát và tắt sau khi chẩn đoán.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| PKIX path building failed | Client không tìm được chain tới CA tin cậy | Kiểm tra truststore và intermediate certificate |
| No subject alternative DNS name matching | Hostname URL không khớp SAN | Sửa DNS/URL hoặc cấp lại certificate có SAN đúng |
| certificate_expired | Certificate hết hạn | Gia hạn và triển khai certificate mới |
| bad_certificate | Client certificate không hợp lệ hoặc server không tin CA client | Kiểm tra client keystore, chain, EKU và truststore phía server |
| handshake_failure | TLS version, cipher suite, certificate hoặc client-auth không tương thích | Xem log hai phía và đối chiếu chính sách TLS |
| UnrecoverableKeyException | Không đọc được private key hoặc sai key password | Kiểm tra keystore type, alias và mật khẩu |
| Kết nối HTTPS thành công nhưng API trả 403 | TLS đã thiết lập nhưng ACL/authorization từ chối | Kiểm tra Consul token, Eureka security hoặc quyền registry |
| JVM tin cậy certificate nhưng HTTP client vẫn lỗi | Transport dùng SSLContext riêng hoặc truststore khác | Kiểm tra client implementation và cấu hình SSL riêng |
| Sau khi cập nhật secret vẫn dùng certificate cũ | SSLContext đã cache key material | Xác minh reload support hoặc rollout/restart an toàn |

Không khắc phục lỗi bằng cách tắt xác minh certificate, bỏ hostname verification hoặc chấp nhận mọi certificate. Những cách này loại bỏ chính cơ chế bảo vệ mà TLS được cấu hình để cung cấp.

## 14. Phân biệt các lớp bảo mật

Một hệ thống service discovery có thể có nhiều kênh TLS khác nhau:

| Kênh | Mục đích | Cấu hình nằm ở đâu |
|---|---|---|
| Service client → Registry | Bảo vệ đăng ký và truy vấn | Registry client HTTP/TLS transport |
| Consumer → Provider | Bảo vệ request nghiệp vụ | HTTPS/mTLS của service provider và consumer |
| Registry node → Registry node | Bảo vệ giao tiếp nội bộ của cụm | Cấu hình cluster/server tương ứng |
| Client identity → API authorization | Quyết định client được phép thao tác gì | ACL, authentication và authorization |

Ví dụ, bật HTTPS cho inventory-service không có nghĩa kết nối từ inventory-service tới Eureka đã được mã hóa. Bật HTTPS cho Eureka cũng không tự mã hóa giao tiếp giữa các Eureka peer hoặc giữa consumer và provider. Mỗi kênh cần được cấu hình và kiểm tra riêng.

## 15. Nguyên tắc triển khai an toàn

- Dùng TLS cho mọi kết nối registry đi qua mạng không tin cậy.
- Dùng mTLS khi cần xác thực client ở tầng TLS và registry/transport hỗ trợ đầy đủ.
- Cài CA cần thiết vào truststore; giữ private key trong keystore được bảo vệ.
- Kiểm tra certificate chain, SAN, EKU, thời hạn và hostname verification.
- Không nhầm server.ssl của HTTPS inbound với SSL context outbound của registry client.
- Cấu hình riêng theo Eureka, Consul hoặc ZooKeeper; không giả định mọi starter dùng cùng HTTP transport hay thuộc tính SSL.
- Giữ ACL/token và authorization ngay cả khi đã bật TLS/mTLS.
- Không đặt secret trong repository, image, URL hoặc log.
- Theo dõi hạn certificate và luân chuyển CA/certificate theo giai đoạn có thời gian overlap.
- Xác minh kết nối từ đúng runtime/container/Pod của ứng dụng và bằng đúng HTTP client mà starter đang sử dụng.

TLS bảo vệ kênh kết nối tới registry; mTLS bổ sung xác thực certificate của client. Truststore xác định CA mà ứng dụng tin cậy, còn keystore giữ private key và certificate identity của ứng dụng. Khi cấu hình đúng cả certificate chain, hostname, quyền API và vòng đời luân chuyển khóa, Spring Cloud Service Discovery có thể đăng ký và tra cứu service an toàn mà vẫn duy trì khả năng vận hành khi certificate được thay mới.
