# TLS handshake thất bại

## 1. Xác định handshake dừng ở đâu

Trong **SPRING_GRPC**, client gọi service bằng gRPC trên HTTP/2 và trao đổi dữ liệu theo hợp đồng Protocol Buffers. Khi TLS handshake thất bại, TCP có thể đã kết nối thành công nhưng hai đầu chưa thống nhất được danh tính, chứng chỉ, phiên bản TLS hoặc tham số bảo mật để tạo kênh mã hóa.

Một kết nối gRPC bảo mật thường đi qua các bước:

1. Client phân giải target và mở TCP đến host/port.
2. Client và server thương lượng TLS version, cipher suite và các extension.
3. Client gửi SNI nếu có hostname.
4. Server gửi certificate chain.
5. Client xác minh chain, thời hạn và hostname/SAN của server.
6. Nếu bật mTLS, client gửi certificate; server xác minh certificate chain và policy của client.
7. TLS ALPN thương lượng `h2` cho HTTP/2.
8. gRPC bắt đầu trao đổi HTTP/2 frames và thực hiện RPC.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant S as TLS endpoint / server
    C->>S: TCP connect
    C->>S: ClientHello + SNI + ALPN(h2)
    S->>C: ServerHello + certificate chain
    C->>C: Verify CA, validity, SAN
    alt Mutual TLS enabled
        S->>C: CertificateRequest
        C->>S: Client certificate + proof of private key
        S->>S: Verify client certificate
    end
    S->>C: Finished
    C->>S: Finished
    Note over C,S: ALPN h2, then HTTP/2 and gRPC
~~~

Không phải mọi lỗi TLS đều do certificate. `protocol_version`, `no_application_protocol`, SNI mismatch hoặc cấu hình plaintext/TLS không đồng nhất cũng có thể làm handshake dừng trước khi gRPC method được gọi.

## 2. Phân biệt lỗi TCP, TLS và gRPC

Đọc exception gốc và log của cả client lẫn server. `UNAVAILABLE` từ gRPC chỉ là status ở tầng RPC; nguyên nhân có thể nằm sâu hơn trong transport.

| Dấu hiệu | Tầng có khả năng lỗi | Hướng kiểm tra |
|---|---|---|
| `Connection refused` | TCP | Listener, port, bind address và route |
| `Connection timed out` | TCP/network | Firewall, security group, NetworkPolicy |
| `SSLHandshakeException` | TLS | Certificate, trust, protocol, mTLS |
| `PKIX path building failed` | Xác minh certificate chain | CA trust store và intermediate certificates |
| `No subject alternative DNS name matching ...` | Hostname verification | SAN trong certificate và target hostname |
| `certificate has expired` / `not yet valid` | Certificate validity | Thời gian hệ thống và vòng đời certificate |
| `bad_certificate` / `unknown_ca` | Xác minh certificate ở một phía | Client/server certificate chain và CA trust |
| `handshake_failure` | TLS negotiation hoặc policy | TLS versions, cipher suites, client auth |
| `protocol_version` | TLS version không tương thích | Minimum/maximum TLS version ở hai đầu |
| `no_application_protocol` | ALPN | HTTP/2 `h2` và cấu hình proxy/TLS terminator |
| `UNAUTHENTICATED` sau handshake | gRPC authentication | Token, metadata và interceptor |
| `PERMISSION_DENIED` sau handshake | Authorization | Principal và policy quyền |

Nếu `grpcurl` hoặc client đã hoàn tất TLS nhưng method trả `UNAUTHENTICATED`, không tiếp tục thay CA hoặc certificate một cách ngẫu nhiên. Chuyển sang kiểm tra credential của ứng dụng.

## 3. Xác minh hai đầu có thống nhất plaintext hay TLS

Server và client phải dùng cùng chế độ transport:

- Server plaintext, client bật TLS: client gửi TLS ClientHello đến một endpoint không nói TLS; handshake thất bại.
- Server bật TLS, client plaintext: server nhận dữ liệu HTTP/2 plaintext ở nơi đang chờ TLS record; kết nối bị đóng hoặc báo lỗi protocol.
- Cả hai bật TLS nhưng dùng trust/certificate khác nhau: TCP thành công nhưng handshake có thể thất bại.

Probe theo đúng chế độ:

~~~bash
# Chỉ khi server được cấu hình plaintext.
grpcurl -plaintext orders-grpc.internal:9090 list

# TLS, xác minh server certificate bằng trust store mặc định.
grpcurl orders-grpc.internal:9090 list

# TLS với CA riêng.
grpcurl -cacert ./certs/internal-ca.pem orders-grpc.internal:9090 list
~~~

`-plaintext` không phải cách sửa TLS. `-insecure` cũng không phải cấu hình production; chỉ dùng trong môi trường kiểm soát để cô lập lỗi xác minh certificate, sau đó khôi phục kiểm tra trust và hostname.

## 4. Kiểm tra certificate server và trust chain

Client cần tin cậy CA đã ký certificate server. Certificate server thường chứa leaf certificate và intermediate certificates cần thiết để xây dựng chain đến root CA mà client tin cậy.

Kiểm tra:

- Certificate còn hiệu lực và chưa hết hạn.
- `Not Before` không nằm trong tương lai so với clock của client.
- Certificate có đủ intermediate certificates.
- Certificate được cấp bởi CA nằm trong trust store của client.
- Certificate/key pair thực sự thuộc cùng một cặp.
- Server gửi đúng certificate cho hostname/SNI đang được client dùng.

Có thể xem certificate PEM:

~~~bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
~~~

Xem fingerprint để đối chiếu certificate được deploy:

~~~bash
openssl x509 -in server-cert.pem -noout -fingerprint -sha256
~~~

Với PEM chain, thứ tự file thường là leaf certificate trước, sau đó là intermediate certificates. Root CA thường được cài trong trust store của client thay vì cần gửi lại như một phần của server chain. Xác nhận yêu cầu cụ thể của TLS library và cách đóng gói certificate.

Không nhầm certificate server với CA trust. Đưa leaf certificate vào trust store có thể là một lựa chọn pinning có chủ đích, nhưng không thay thế hiểu biết về chain và quy trình rotation.

## 5. SAN phải khớp hostname client xác minh

Client không chỉ xác minh certificate được CA tin cậy; nó còn xác minh danh tính server. Với hostname, certificate cần Subject Alternative Name (SAN) tương ứng.

Ví dụ client target:

~~~text
orders-grpc.backend.svc.cluster.local:9090
~~~

Certificate server phải có DNS SAN phù hợp, ví dụ:

~~~text
DNS:orders-grpc.backend.svc.cluster.local
~~~

Nếu client gọi bằng `orders.internal.example` nhưng certificate chỉ có SAN `orders-grpc.backend.svc.cluster.local`, TLS hostname verification sẽ thất bại dù CA chain hợp lệ.

Không sửa lỗi bằng cách tắt hostname verification. Cấp certificate có SAN đúng với service identity mà client sử dụng, hoặc thiết kế authority override rõ ràng nếu proxy/service mesh yêu cầu một authority khác. Cần bảo đảm tên được xác minh vẫn đại diện đúng server.

Với kết nối bằng IP literal, certificate cần IP SAN tương ứng. DNS SAN chứa chuỗi trông giống IP không thay thế IP SAN.

## 6. SNI và authority là hai khái niệm liên quan nhưng khác nhau

**SNI (Server Name Indication)** là extension trong TLS ClientHello cho biết hostname client muốn kết nối. TLS terminator có thể dùng SNI để chọn certificate phù hợp khi một địa chỉ IP phục vụ nhiều hostname.

HTTP/2 `:authority` là thông tin authority của request ở tầng HTTP/2. gRPC client thường suy ra authority từ target, nhưng có thể có cấu hình override trong một số topology.

Nếu SNI không đúng:

- Proxy có thể trả certificate mặc định của một virtual host khác.
- Client nhận certificate có SAN không khớp target.
- TLS terminator có thể từ chối handshake theo policy.

Kiểm tra bằng OpenSSL:

~~~bash
openssl s_client \
  -connect orders-grpc.internal:9090 \
  -servername orders-grpc.internal \
  -showcerts \
  -alpn h2
~~~

Thử có và không có `-servername` trong môi trường kiểm soát có thể cho thấy TLS terminator đang chọn certificate theo SNI. Không bỏ SNI trong cấu hình production chỉ để tránh lỗi; sửa hostname, certificate hoặc routing của TLS endpoint.

Trong gRPC Java, `overrideAuthority(...)` tác động đến authority được dùng cho call. Nó không sửa DNS, không tự cấp certificate và không nên dùng để bỏ qua xác minh danh tính. Xác minh hành vi cụ thể của transport/version trước khi dùng.

## 7. Kiểm tra mTLS: server có yêu cầu client certificate không?

TLS một chiều xác minh server certificate ở phía client. **Mutual TLS (mTLS)** bổ sung việc server yêu cầu và xác minh client certificate.

Với mTLS, phải có đủ hai trust direction:

- Client tin CA ký server certificate.
- Server tin CA ký client certificate.
- Client gửi certificate phù hợp khi server yêu cầu.
- Client có private key khớp certificate và chứng minh được quyền sở hữu key.
- Certificate client còn hiệu lực và thỏa policy (EKU, subject/SAN hoặc identity mapping).

Dấu hiệu thường gặp:

- Server yêu cầu client certificate nhưng client không gửi: handshake bị từ chối.
- Client gửi certificate nhưng server không tin CA: lỗi `unknown_ca` hoặc `bad_certificate`.
- Client certificate thiếu `clientAuth` EKU theo policy: server có thể từ chối.
- Private key không khớp certificate hoặc không đọc được: client không thể hoàn tất xác thực.

Không nhầm lỗi mTLS với bearer token. TLS client certificate xác thực peer ở transport; JWT/API token thường xác thực principal hoặc quyền ở tầng ứng dụng. Một hệ thống có thể yêu cầu cả hai.

## 8. Probe mTLS bằng OpenSSL và grpcurl

OpenSSL có thể kiểm tra handshake với client certificate:

~~~bash
openssl s_client \
  -connect orders-grpc.internal:9090 \
  -servername orders-grpc.internal \
  -alpn h2 \
  -CAfile ./certs/server-ca.pem \
  -cert ./certs/client-cert.pem \
  -key ./certs/client-key.pem \
  -verify_return_error
~~~

Với `grpcurl`, có thể truyền CA và client certificate/key:

~~~bash
grpcurl \
  -cacert ./certs/server-ca.pem \
  -cert ./certs/client-cert.pem \
  -key ./certs/client-key.pem \
  orders-grpc.internal:9090 list
~~~

Lệnh `list` cần reflection được bật. Nếu reflection tắt, dùng `.proto`/protoset để mô tả và gọi method; lỗi reflection không chứng minh TLS thất bại.

Không đưa private key vào command line trong môi trường có process listing/audit không phù hợp. Với môi trường production, dùng secret manager, file permission phù hợp hoặc cơ chế credential provider được hỗ trợ.

## 9. Kiểm tra ALPN và HTTP/2

gRPC dựa trên HTTP/2. Khi TLS được dùng, hai đầu thường thương lượng application protocol `h2` qua ALPN. TLS handshake có thể thất bại nếu endpoint chỉ hỗ trợ protocol không tương thích hoặc proxy không quảng bá `h2`.

Kiểm tra ALPN:

~~~bash
openssl s_client \
  -connect orders-grpc.internal:9090 \
  -servername orders-grpc.internal \
  -alpn h2
~~~

Trong kết quả, tìm `ALPN protocol: h2`. Nếu không có protocol được chọn, kiểm tra:

- TLS terminator có bật ALPN `h2` không?
- Load balancer listener có hỗ trợ HTTP/2 không?
- Proxy có chuyển upstream bằng HTTP/2 theo yêu cầu của backend không?
- Có cấu hình chỉ cho HTTP/1.1 ở một chặng không?
- TLS version/cipher policy có tương thích với HTTP/2 implementation không?

Nếu proxy terminate TLS ở edge rồi chuyển đến backend, cần xác định rõ từng chặng: client→proxy dùng TLS/HTTP2 hay plaintext/HTTP2; proxy→gRPC server dùng TLS hay plaintext; backend có yêu cầu mTLS riêng không. Không giả định TLS ở edge đồng nghĩa backend cũng đang được mã hóa.

## 10. Phiên bản TLS và cipher suite

Client và server phải có ít nhất một TLS version và cipher suite tương thích. Các hệ thống hiện đại thường ưu tiên TLS 1.2 hoặc TLS 1.3 theo policy bảo mật.

Nếu một phía chỉ cho phép TLS 1.3 còn phía kia hoặc TLS terminator cũ chỉ hỗ trợ TLS 1.2, handshake có thể thất bại. Cipher suite bị giới hạn quá chặt hoặc cấu hình security provider không tương thích cũng có thể tạo `handshake_failure`.

Không hạ xuống TLS 1.0/1.1 để “thử cho chạy”. Kiểm tra policy và nâng cấp runtime/proxy/certificate configuration để có giao thức chung an toàn.

OpenSSL có thể ép phiên bản để chẩn đoán:

~~~bash
openssl s_client -connect orders-grpc.internal:9090 -servername orders-grpc.internal -tls1_2 -alpn h2
openssl s_client -connect orders-grpc.internal:9090 -servername orders-grpc.internal -tls1_3 -alpn h2
~~~

Chỉ dùng các tùy chọn này để xác định khác biệt giữa phiên bản. Sau đó sửa cấu hình theo policy thống nhất, không duy trì nhiều cấu hình yếu chỉ để hỗ trợ một client cũ chưa được nâng cấp.

## 11. Cấu hình TLS cho gRPC Java client

Với gRPC Java API dùng channel credentials, client có thể cung cấp CA trust và tùy chọn client certificate:

~~~java
import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.TlsChannelCredentials;

import java.io.File;

TlsChannelCredentials.Builder tls =
        TlsChannelCredentials.newBuilder()
                .trustManager(new File("certs/server-ca.pem"));

// Chỉ cấu hình keyManager khi server yêu cầu mTLS.
tls.keyManager(
        new File("certs/client-cert-chain.pem"),
        new File("certs/client-key.pem"));

ManagedChannel channel = Grpc.newChannelBuilder(
        "dns:///orders-grpc.backend.svc.cluster.local:9090",
        tls.build()).build();
~~~

Đây là ví dụ client mTLS; nếu chỉ xác minh server, bỏ `keyManager(...)`. Các file và API cụ thể phụ thuộc phiên bản gRPC Java, transport provider và định dạng private key được hỗ trợ.

Nếu ứng dụng dùng `NettyChannelBuilder` và `GrpcSslContexts`, cấu hình tương đương có thể được tạo bằng Netty `SslContext`. Không trộn lẫn hai cơ chế credentials/SSL context trong cùng channel nếu không có lý do rõ ràng.

Không dùng `InsecureTrustManagerFactory` hoặc trust-all manager trong production. Nó vô hiệu hóa xác minh certificate và cho phép kết nối đến peer giả mạo.

## 12. Cấu hình TLS cho gRPC Java server

Với API gRPC Java dùng server credentials, server cung cấp certificate/private key; nếu yêu cầu mTLS thì thêm trust manager và đặt client auth policy:

~~~java
import io.grpc.Grpc;
import io.grpc.Server;
import io.grpc.TlsServerCredentials;

import java.io.File;

TlsServerCredentials credentials =
        TlsServerCredentials.newBuilder()
                .keyManager(
                        new File("certs/server-cert-chain.pem"),
                        new File("certs/server-key.pem"))
                .trustManager(new File("certs/client-ca.pem"))
                .clientAuth(TlsServerCredentials.ClientAuth.REQUIRE)
                .build();

Server server = Grpc.newServerBuilderForPort(9090, credentials)
        .addService(ordersService)
        .build()
        .start();
~~~

Đoạn code yêu cầu client certificate. Nếu chỉ dùng TLS một chiều, không cấu hình client auth `REQUIRE` và không yêu cầu client CA theo cách này. Server cần gửi chain phù hợp; client cần trust CA ký server certificate.

Trong ứng dụng Spring gRPC, starter có thể tự tạo và quản lý server. Khi đó, cấu hình TLS qua property/API của đúng starter và phiên bản đang dùng; không tạo một gRPC server thứ hai bằng code chỉ để bật TLS. Xác minh log startup cho biết server đang bind đúng port và đã nạp certificate thành công.

## 13. Keystore, truststore và private key

Trong Java, có thể dùng JKS hoặc PKCS12 keystore/truststore tùy API và starter:

- **Keystore:** giữ private key và certificate chain của chính endpoint.
- **Truststore:** giữ CA/certificate mà endpoint tin cậy.
- **Server keystore:** thường chứa server private key và server certificate chain.
- **Client truststore:** chứa CA tin server certificate.
- **Client keystore trong mTLS:** chứa client private key và client certificate chain.
- **Server truststore trong mTLS:** chứa CA tin client certificate.

Không nhầm keystore với truststore. Đưa server certificate vào truststore của client có thể tạo pinning, nhưng không có nghĩa client đã có private key server. Ngược lại, truststore không cung cấp identity private key cho server.

Nếu chuyển PEM sang PKCS12/JKS, kiểm tra alias, chain, key password, store password và loại key. Không ghi password vào source code hoặc commit vào repository; lấy từ secret manager hoặc secret injection có kiểm soát.

## 14. Spring gRPC: xác minh đúng cấu hình của starter

Spring gRPC starter và các thư viện gRPC Spring khác nhau có thể dùng namespace property và cơ chế nạp TLS khác nhau. Trước khi chỉnh cấu hình:

1. Xác định starter thực tế đang chạy và phiên bản tương thích.
2. Xác định gRPC server được starter quản lý hay do ứng dụng tự tạo.
3. Xác minh property TLS, đường dẫn certificate/key, password và client-auth mode theo tài liệu đúng phiên bản.
4. Kiểm tra file/secret được mount vào đúng container và user process có quyền đọc.
5. Kiểm tra log startup có lỗi load key, parse certificate hoặc bind port không.
6. Xác minh server thực sự trình bày certificate mới sau deploy.

Không sao chép property TLS từ starter khác chỉ vì tên cấu hình trông giống nhau. Không đặt cả `spring.grpc.*` và `grpc.server.*` với kỳ vọng cả hai đều có tác dụng; có thể chỉ một namespace được bind.

## 15. TLS termination tại proxy hoặc service mesh

Trong production, TLS có thể kết thúc ở load balancer, ingress gateway hoặc service mesh sidecar. Cần vẽ rõ các hop:

~~~text
gRPC client
   | TLS + HTTP/2 (h2)
   v
Load balancer / gateway
   | TLS + HTTP/2, hoặc plaintext + HTTP/2 theo policy
   v
Service mesh sidecar
   | mTLS hoặc transport được cấu hình
   v
Spring gRPC server
~~~

Các lỗi thường gặp:

- Edge certificate hợp lệ nhưng gateway chọn nhầm certificate vì SNI.
- Client→gateway dùng HTTP/2 nhưng gateway→backend dùng HTTP/1.1.
- Gateway yêu cầu mTLS nhưng client không gửi certificate.
- Gateway terminate TLS nhưng backend cũng bật TLS, trong khi gateway lại gửi plaintext.
- Sidecar yêu cầu workload identity/certificate khác với cấu hình ứng dụng.

Kiểm tra log và metric ở từng hop. Nếu OpenSSL kết nối được gateway nhưng gRPC server không nhận request, điều tra upstream protocol và backend TLS riêng. TLS thành công ở edge không chứng minh TLS/mTLS giữa gateway và backend thành công.

## 16. Bật chẩn đoán TLS trong Java

Với JSSE/JDK SSL provider, có thể bật debug trong môi trường test hoặc staging:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

Log có thể cho biết ClientHello, ServerHello, certificate chain, trust decision và alert. Tuy nhiên, gRPC Java có thể dùng Netty/OpenSSL native provider; khi đó `javax.net.debug` không nhất thiết hiển thị toàn bộ handshake. Kiểm tra provider đang dùng và bật logging phù hợp của Netty/TLS terminator.

Không để debug TLS chi tiết bật lâu dài trong production nếu log có thể chứa thông tin nhạy cảm hoặc tạo lượng log lớn. Thu thập trong khoảng thời gian có kiểm soát, giới hạn quyền truy cập và tắt sau khi chẩn đoán.

## 17. Quy trình khoanh vùng TLS handshake

Thực hiện từ transport đến ứng dụng:

1. **Xác nhận TCP:** host/port có mở được từ đúng môi trường client không?
2. **Xác nhận mode:** server và client đều dùng TLS hay plaintext theo đúng thiết kế?
3. **Lấy certificate thực tế:** dùng `openssl s_client -showcerts` với SNI đúng.
4. **Kiểm tra chain và thời hạn:** CA trust, intermediate, `Not Before`/`Not After`.
5. **Kiểm tra SAN/SNI:** hostname client xác minh phải khớp certificate server được chọn.
6. **Kiểm tra mTLS:** server có yêu cầu client certificate không; client có gửi key/cert và server có trust CA không?
7. **Kiểm tra TLS version/cipher:** tìm giao thức chung được policy cho phép.
8. **Kiểm tra ALPN:** phải thương lượng `h2` cho gRPC qua TLS.
9. **Kiểm tra proxy từng hop:** TLS termination, upstream protocol và mTLS giữa các workload.
10. **Probe gRPC:** dùng `grpcurl` với CA/client cert phù hợp; sau đó mới điều tra authentication và method.

Mỗi bước ghi lại bằng chứng. Không thay đồng thời CA, hostname, TLS version và proxy config vì sẽ khó xác định nguyên nhân thực.

## 18. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `PKIX path building failed` | Client không xây dựng được chain đến CA tin cậy | Cài đúng root CA và gửi đủ intermediate |
| Hostname/SAN mismatch | Certificate không đại diện target client dùng | Cấp SAN đúng hoặc thiết kế authority rõ ràng |
| `certificate expired` | Certificate hết hạn | Rotate certificate và kiểm tra automation |
| `certificate not yet valid` | Clock lệch hoặc certificate chưa có hiệu lực | Đồng bộ thời gian và kiểm tra validity |
| `unknown_ca` | Một phía không tin CA của certificate bên kia | Cài đúng trust anchor ở đúng phía |
| `bad_certificate` | Certificate không hợp lệ, chain/key/EKU sai | Kiểm tra chain, key pair và certificate usage |
| Server yêu cầu client cert nhưng client không gửi | mTLS chưa cấu hình ở client | Nạp client certificate/private key |
| `protocol_version` | TLS version không giao nhau | Đồng bộ minimum/maximum TLS an toàn |
| `handshake_failure` | Cipher/policy/client-auth không tương thích | Đọc alert và log hai đầu, đối chiếu policy |
| `no_application_protocol` | ALPN không thương lượng được `h2` | Sửa HTTP/2/ALPN tại endpoint và proxy |
| TLS thành công nhưng RPC `UNAUTHENTICATED` | Credential tầng ứng dụng thiếu/sai | Kiểm tra token và interceptor |

## 19. Những lỗi cấu hình thường gặp

| Cách làm sai | Hậu quả | Cách làm đúng |
|---|---|---|
| Dùng plaintext ở một đầu, TLS ở đầu kia | Handshake/protocol thất bại | Đồng bộ transport mode |
| Tin CA nhưng không kiểm tra SAN | Có thể kết nối nhầm server | Xác minh hostname identity |
| Dùng certificate leaf thiếu intermediate | Client không xây dựng được chain | Gửi chain đầy đủ theo yêu cầu |
| Nhầm truststore với keystore | Thiếu trust hoặc thiếu private key | Tách server/client identity và trust |
| Bật mTLS ở server nhưng không cấp client cert | Handshake bị từ chối | Cấu hình client key/cert và server trust CA |
| Tắt hostname verification hoặc trust-all | Mất xác minh danh tính peer | Sửa CA, SAN, SNI và trust |
| Dùng TLS version quá cũ để tương thích | Hạ mức bảo mật | Nâng cấp runtime/proxy và thống nhất TLS 1.2/1.3 |
| TLS edge thành công nên bỏ qua backend | Lỗi upstream mTLS/HTTP2 không được phát hiện | Kiểm tra từng hop |
| Chỉ kiểm tra TCP | Không phát hiện lỗi certificate/ALPN | Dùng OpenSSL và grpcurl |

**Ghi nhớ:** TLS handshake của gRPC cần đồng thời đúng transport mode, certificate chain, trust, SAN/SNI, mTLS policy và ALPN `h2`. Xác minh từng phía: client tin server certificate; nếu bật mTLS, server cũng phải tin client certificate. Dùng OpenSSL để xem certificate/ALPN, grpcurl để probe gRPC, và log TLS có kiểm soát để xác định alert. Với Spring gRPC, cấu hình theo đúng starter/version và kiểm tra riêng từng hop nếu có proxy hoặc service mesh.
