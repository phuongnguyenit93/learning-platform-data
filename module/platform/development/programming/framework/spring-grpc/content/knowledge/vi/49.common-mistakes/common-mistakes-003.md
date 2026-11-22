# Dùng plaintext trong production

## 1. Vì sao plaintext là một rủi ro?

Trong **SPRING_GRPC**, client và server trao đổi request/response Protobuf qua HTTP/2. Khi client cấu hình channel bằng plaintext, transport không mã hóa dữ liệu. Bất kỳ thành phần nào có thể quan sát đường truyền đều có thể đọc payload, metadata và response; thành phần có thể can thiệp traffic còn có khả năng sửa hoặc giả mạo dữ liệu trên đường truyền.

Một số request có thể chứa access token, customer data, thông tin thanh toán, dữ liệu nội bộ hoặc command thay đổi trạng thái. Dùng plaintext trong production khiến các dữ liệu này phụ thuộc hoàn toàn vào mức độ tin cậy của network path.

Các rủi ro chính:

- **Confidentiality:** người có khả năng nghe lén có thể đọc request, response và metadata.
- **Integrity:** traffic có thể bị sửa nếu không có cơ chế bảo vệ kênh.
- **Server identity:** client không có bằng chứng mật mã rằng nó đang kết nối đúng server.
- **Credential exposure:** bearer token trong metadata có thể bị thu thập và tái sử dụng.
- **Lateral movement:** một workload bị xâm nhập có thể quan sát hoặc giả mạo traffic nội bộ nếu mạng không cô lập đủ chặt.

Plaintext có thể phù hợp cho local development hoặc một đoạn kết nối nội bộ có kiểm soát theo threat model cụ thể. Nó không nên là mặc định production chỉ vì các service đang chạy cùng VPC, cluster hoặc subnet.

## 2. Plaintext và TLS khác nhau ở tầng transport

gRPC sử dụng HTTP/2 để truyền message. TLS bảo vệ kênh transport trước khi gRPC gửi dữ liệu ứng dụng:

| Thuộc tính | Plaintext | TLS |
| --- | --- | --- |
| Mã hóa dữ liệu trên đường truyền | Không | Có |
| Kiểm tra tính toàn vẹn của record | Không có bảo vệ TLS | Có |
| Xác minh danh tính server | Không | Client kiểm tra certificate chain và hostname |
| Xác minh danh tính client | Không ở tầng TLS | Có thể dùng mTLS |
| HTTP/2 negotiation | h2c/cleartext theo cấu hình | ALPN thương lượng h2 trong TLS |
| Bảo vệ metadata/token | Không | Được mã hóa trong kênh TLS |

TLS không thay thế authorization nghiệp vụ. Một client có certificate hợp lệ vẫn cần được kiểm tra xem có quyền gọi RPC method và truy cập resource cụ thể hay không.

## 3. Dùng TLS trên client gRPC

Với gRPC Java, ManagedChannel có thể bật transport security bằng useTransportSecurity():

```java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("orders.internal.example", 8443)
    .useTransportSecurity()
    .build();
```

Cấu hình này dùng trust roots mặc định của runtime. Nó phù hợp khi certificate server được cấp bởi CA mà môi trường client tin cậy.

Nếu service dùng private CA, client cần trust đúng CA/certificate chain:

```java
SslContext sslContext = GrpcSslContexts.forClient()
    .trustManager(new File("/etc/grpc/pki/internal-ca.pem"))
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal.example", 8443)
    .sslContext(sslContext)
    .build();
```

Các class Netty TLS phụ thuộc việc dự án dùng grpc-netty hay grpc-netty-shaded; package import cần khớp dependency đang dùng. Nếu dùng Spring gRPC starter, ưu tiên cấu hình TLS qua cơ chế channel/client configuration của starter để Spring quản lý channel lifecycle. Không tạo một channel phụ ngoài lifecycle chỉ để bật TLS.

Client phải xác minh certificate chain và hostname/SAN khớp với authority đang kết nối. Không tắt hostname verification, không dùng trust-all manager và không chấp nhận certificate bất kỳ để “sửa nhanh” lỗi handshake.

## 4. Cấu hình TLS cho server gRPC

Server cần certificate chain và private key tương ứng. Với Netty gRPC server, có thể cấu hình SSL context:

```java
SslContext sslContext = GrpcSslContexts
    .forServer(
        new File("/etc/grpc/pki/server-chain.pem"),
        new File("/etc/grpc/pki/server-key.pem")
    )
    .build();

NettyServerBuilder serverBuilder = NettyServerBuilder
    .forPort(8443)
    .sslContext(sslContext)
    .addService(orderService);
```

Ví dụ minh họa API gRPC Java Netty; tên package phụ thuộc grpc-netty hoặc grpc-netty-shaded. Trong ứng dụng Spring, starter thường sở hữu server builder và lifecycle. Cấu hình certificate/key thông qua server TLS properties hoặc customizer được hỗ trợ bởi starter đang dùng; tránh tự dựng một server thứ hai song song với server Spring.

Certificate phải chứa SAN phù hợp với DNS name client sử dụng. Common Name đơn lẻ không nên được xem là thay thế cho Subject Alternative Name trong thiết kế hiện đại.

## 5. TLS handshake, certificate chain và hostname verification

Khi client kết nối TLS, hai phía thương lượng protocol/cipher và xác minh certificate. Với gRPC qua HTTP/2, ALPN cần thương lượng protocol h2.

Client kiểm tra:

1. Certificate còn hiệu lực trong khoảng thời gian hiện tại.
2. Certificate chain dẫn tới trust anchor được client tin cậy.
3. Certificate có mục đích sử dụng phù hợp.
4. SAN khớp hostname/authority mà client gọi.
5. Certificate chưa bị thu hồi nếu môi trường có kiểm tra revocation tương ứng.

Server certificate hợp lệ nhưng SAN không khớp target vẫn phải bị từ chối. Ví dụ client gọi orders.internal.example thì certificate phải có DNS SAN tương ứng hoặc wildcard hợp lệ theo quy tắc hostname matching.

Không dùng IP address để gọi endpoint nếu certificate chỉ có DNS SAN, trừ khi certificate cũng có IP SAN tương ứng. Không dùng authority override như cách che giấu mismatch trong production; sửa DNS/target/certificate để identity khớp.

## 6. Mutual TLS để xác minh cả client và server

TLS một chiều xác minh server với client. **Mutual TLS (mTLS)** yêu cầu client cũng trình certificate để server xác minh danh tính workload gọi tới.

mTLS hữu ích khi:

- Các service nội bộ cần xác minh workload identity.
- Chỉ workload được cấp certificate bởi CA tin cậy mới được thiết lập kênh.
- Network có nhiều service/tenant và cần giảm nguy cơ giả mạo client.
- Hạ tầng dùng service mesh hoặc PKI nội bộ cấp certificate ngắn hạn.

Ví dụ server yêu cầu client certificate:

```java
SslContext serverContext = GrpcSslContexts
    .forServer(serverChainFile, serverKeyFile)
    .trustManager(clientCaFile)
    .clientAuth(ClientAuth.REQUIRE)
    .build();

NettyServerBuilder server = NettyServerBuilder
    .forPort(8443)
    .sslContext(serverContext)
    .addService(orderService);
```

Client gửi certificate của chính nó và đồng thời xác minh server:

```java
SslContext clientContext = GrpcSslContexts.forClient()
    .trustManager(serverCaFile)
    .keyManager(clientCertificateFile, clientPrivateKeyFile)
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal.example", 8443)
    .sslContext(clientContext)
    .build();
```

Server cần ánh xạ certificate identity (ví dụ SAN URI/DNS hoặc subject theo PKI policy) thành principal/workload identity. Việc TLS handshake thành công chỉ xác nhận certificate được chấp nhận; authorization vẫn phải kiểm tra principal có được gọi method đó hay không.

Nếu dùng service mesh, mesh có thể thực hiện mTLS ở sidecar/proxy. Hãy hiểu rõ identity được xác minh ở proxy nào và cách identity được chuyển tới application. Không tin một header identity do client tùy ý gửi; chỉ tin metadata được proxy đáng tin cậy xóa/ghi lại và bảo vệ theo kiến trúc.

## 7. TLS termination ở load balancer hoặc proxy

Một số deployment kết thúc TLS tại ingress/load balancer rồi chuyển traffic tới gRPC server nội bộ. Khi đó có hai đoạn kết nối:

- Client → load balancer: TLS.
- Load balancer → backend: có thể TLS hoặc plaintext tùy cấu hình.

TLS ở hop đầu không tự động mã hóa hop sau. Nếu backend network có thể bị quan sát hoặc truy cập bởi workload không tin cậy, plaintext nội bộ vẫn có rủi ro.

Các lựa chọn:

- **End-to-end TLS:** client TLS trực tiếp tới gRPC server.
- **TLS re-encryption:** load balancer giải mã rồi thiết lập TLS mới tới backend.
- **mTLS giữa proxy và backend:** xác minh cả hai workload ở hop nội bộ.
- **Plaintext nội bộ có kiểm soát:** chỉ khi threat model, network isolation, workload identity và policy chấp nhận rõ ràng.

Với HTTP/2 gRPC, proxy/load balancer phải hỗ trợ HTTP/2 ở hop tương ứng và giữ đúng semantics streaming, trailers, deadline cùng status. Cấu hình TLS đúng nhưng proxy chuyển sang HTTP/1.1 không tương thích có thể làm RPC lỗi hoặc mất streaming behavior.

## 8. Quản lý certificate và private key

Certificate có hạn sử dụng; private key là bí mật cần bảo vệ. Không commit private key vào Git, không đóng gói key production trong JAR/container image và không ghi key ra log.

Thực hành phù hợp:

- Lưu private key trong secret manager, Kubernetes Secret có encryption at rest hoặc PKI agent được quản lý.
- Giới hạn quyền đọc key theo service identity.
- Ưu tiên certificate ngắn hạn và tự động cấp/renew.
- Theo dõi ngày hết hạn và cảnh báo trước khi certificate hết hạn.
- Dùng certificate chain đầy đủ để client có thể xác minh.
- Có quy trình thu hồi và thay thế certificate bị lộ.
- Phân tách certificate theo môi trường và workload identity.

Không dùng cùng một private key cho mọi service nếu không có lý do kiến trúc rõ ràng. Một key dùng chung làm tăng phạm vi ảnh hưởng khi một workload bị xâm nhập.

## 9. Xoay certificate mà không làm gián đoạn RPC

Certificate rotation cần phối hợp server, client, CA trust và channel lifecycle.

Một quy trình an toàn thường là:

1. Phát hành certificate mới trong khi certificate cũ vẫn còn hiệu lực.
2. Cập nhật trust bundle để client chấp nhận CA/certificate mới trước khi server chuyển đổi, nếu trust anchor thay đổi.
3. Cập nhật server certificate/key và reload hoặc khởi tạo server instance mới theo cơ chế được hỗ trợ.
4. Kiểm tra handshake bằng client production-like.
5. Cập nhật client certificate nếu dùng mTLS.
6. Drain kết nối cũ và quan sát lỗi handshake/RPC.
7. Chỉ loại bỏ trust cũ sau khi mọi client đã chuyển đổi và không còn certificate cũ hợp lệ cần hỗ trợ.

Không phải mọi Netty/gRPC server đều tự reload file certificate khi file thay đổi. Cần dùng cơ chế reload được framework hỗ trợ hoặc triển khai rolling replacement có health check và drain. Client channel đang hoạt động cũng có thể giữ SSL context cũ; rotation phải tính tới việc tạo channel mới có kiểm soát và drain channel cũ.

## 10. TLS không thay thế authentication và authorization

TLS bảo vệ kênh và xác minh transport identity. Application vẫn cần quyết định caller được phép làm gì:

- Authentication có thể dựa vào mTLS principal, OAuth/JWT bearer token hoặc cơ chế identity được tin cậy.
- Authorization kiểm tra principal có quyền gọi RPC method và truy cập resource.
- Tenant isolation phải được áp dụng trong application/database query.
- Metadata không được tin chỉ vì nó đi qua TLS; client đã xác thực vẫn có thể gửi metadata sai hoặc vượt quyền.
- Audit cần ghi identity đã xác minh và action, không ghi secret/token.

Nếu dùng bearer token, gửi qua gRPC metadata trên TLS. Không gửi token qua plaintext, không log metadata nhạy cảm và không đưa token vào metric labels.

## 11. Phân biệt lỗi TLS với lỗi RPC/application

Lỗi TLS thường xảy ra trước khi RPC method được thực thi:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Certificate unknown/untrusted | CA chain không nằm trong trust store | Cập nhật trust bundle đúng |
| Hostname/SAN mismatch | Target không khớp certificate | Sửa DNS/authority hoặc cấp certificate đúng SAN |
| Certificate expired | Certificate hết hạn | Renew/rotate theo quy trình |
| Client certificate required | Server bật mTLS nhưng client không gửi cert | Cấp và cấu hình client certificate |
| Client certificate rejected | CA hoặc identity không được server chấp nhận | Kiểm tra client CA và identity policy |
| ALPN/protocol negotiation failure | Proxy/transport không thương lượng HTTP/2 đúng | Kiểm tra TLS/ALPN và cấu hình proxy |
| UNAVAILABLE sau handshake | Server/network không sẵn sàng | Điều tra transport/server health |
| INVALID_ARGUMENT/NOT_FOUND | RPC đã tới application và lỗi nghiệp vụ | Sửa request hoặc xử lý resource theo contract |

Không ánh xạ mọi handshake failure thành INVALID_ARGUMENT. Nhiều lỗi TLS xảy ra trước khi server có thể trả gRPC status bình thường; client có thể thấy UNAVAILABLE hoặc lỗi transport cụ thể.

## 12. Kiểm thử TLS trong môi trường gần production

Cần có test chứng minh server từ chối kết nối không tin cậy và chấp nhận certificate đúng:

| Test | Điều cần xác nhận |
| --- | --- |
| Client trust CA đúng | TLS handshake thành công và RPC chạy |
| CA không tin cậy | Handshake thất bại |
| SAN không khớp hostname | Client từ chối server certificate |
| Certificate hết hạn | Handshake thất bại |
| mTLS thiếu client cert | Server từ chối |
| mTLS cert từ CA sai | Server từ chối |
| mTLS cert hợp lệ | Handshake thành công; authorization vẫn được kiểm tra |
| Certificate rotation | Client mới kết nối được trong lúc channel cũ drain |
| Proxy termination | TLS trên từng hop đúng với threat model |
| Plaintext vào TLS listener | Kết nối thất bại |
| TLS client vào plaintext listener | Kết nối thất bại hoặc negotiation không thành công theo cấu hình |

Dùng certificate test CA riêng, SAN rõ ràng và thời hạn kiểm thử phù hợp. Không tắt certificate verification trong test để làm test “xanh”; điều đó chỉ che giấu lỗi cấu hình.

Test TLS nên chạy cùng loại transport/proxy topology production nếu hệ thống phụ thuộc ingress hoặc service mesh.

## 13. Local development và môi trường production

Local development có thể dùng plaintext để giảm bước thiết lập certificate khi chỉ giao tiếp trên loopback hoặc môi trường cô lập:

```java
ManagedChannel localChannel = ManagedChannelBuilder
    .forAddress("localhost", 9090)
    .usePlaintext()
    .build();
```

Cần tách cấu hình theo profile/môi trường. Không để production profile kế thừa plaintext vì một property mặc định hoặc conditional config sai.

Có thể dùng local CA và certificate test để developer kiểm tra TLS sớm. CI cũng nên có ít nhất một integration suite chạy TLS để phát hiện SAN, trust chain, ALPN và mTLS regression trước deploy.

Production nên fail startup hoặc fail health/readiness nếu TLS material bắt buộc không có/không hợp lệ, thay vì âm thầm fallback sang plaintext.

## 14. Checklist review

- Production channel dùng TLS; plaintext chỉ được bật có chủ đích cho local/test.
- Server certificate chain và private key được cấp/quản lý từ nguồn tin cậy.
- Client trust đúng CA và xác minh hostname/SAN.
- TLS negotiation hỗ trợ HTTP/2 qua ALPN.
- Không có trust-all manager, bỏ hostname verification hoặc authority override để né lỗi.
- mTLS được dùng khi cần xác minh workload client.
- Certificate identity được ánh xạ thành principal; authorization vẫn chạy ở application.
- TLS termination/proxy hop được đánh giá riêng, không mặc định hop nội bộ an toàn.
- Private key không nằm trong source control/image/log và quyền truy cập được giới hạn.
- Certificate expiry, renewal, revocation và rotation có quy trình.
- Channel/server rotation có drain và health check.
- Có integration tests cho CA sai, SAN sai, expiry, mTLS và proxy topology.
- Authentication, authorization, tenant isolation và audit không bị thay thế bởi TLS.

Trong **SPRING_GRPC**, dùng plaintext trong production khiến dữ liệu và metadata gRPC không được bảo vệ trên đường truyền, đồng thời client không xác minh được server identity. Cấu hình TLS với trust chain và hostname đúng; dùng mTLS khi cần xác minh workload hai chiều; quản lý private key và certificate rotation có kiểm soát. Nếu TLS kết thúc ở proxy, đánh giá riêng từng hop tới backend. TLS bảo vệ transport, còn authentication và authorization vẫn phải được thực hiện ở tầng ứng dụng.
