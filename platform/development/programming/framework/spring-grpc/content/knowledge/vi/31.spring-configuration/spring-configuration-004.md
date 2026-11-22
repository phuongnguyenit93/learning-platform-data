# Cấu hình TLS cho server

gRPC chạy trên HTTP/2 và thường cần **TLS** để mã hóa dữ liệu trên đường truyền, xác thực danh tính server và bảo vệ metadata/request khỏi bị đọc hoặc sửa trên mạng. Trong **Spring gRPC**, cấu hình TLS cho server gồm chứng chỉ server, private key tương ứng, chính sách phiên bản TLS và cách tích hợp SslContext vào gRPC server đang được Spring quản lý.

TLS bảo vệ kênh truyền; nó không thay thế xác thực người dùng, authorization hoặc kiểm tra quyền ở tầng nghiệp vụ. Một server có chứng chỉ hợp lệ vẫn phải kiểm tra credential, tenant và quyền truy cập theo từng RPC.

## 1. TLS được thiết lập ở đâu trong gRPC?

Trước khi trao đổi message gRPC, client và server thực hiện TLS handshake. Server trình certificate chain để client xác minh danh tính; hai bên thương lượng phiên bản TLS, cipher suite và khóa phiên. Sau đó HTTP/2 được thương lượng qua **ALPN** với protocol h2, rồi gRPC mới truyền request/response.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant S as Spring gRPC server
    C->>S: TCP connection
    C->>S: TLS ClientHello
    S-->>C: Certificate chain + TLS parameters
    C->>C: Validate certificate and hostname
    C->>S: TLS handshake completed, ALPN h2
    C->>S: HTTP/2 + gRPC request
    S-->>C: HTTP/2 + gRPC response
~~~

Nếu certificate không được client tin cậy, hết hạn hoặc không khớp hostname, handshake thất bại trước khi service implementation nhận RPC. Nếu ALPN không chọn được h2, kết nối có thể thất bại dù certificate hợp lệ.

## 2. Chuẩn bị certificate và private key

Server cần ít nhất:

- **Certificate chain**: certificate của server và các intermediate certificate cần thiết để client xây dựng chuỗi tin cậy.
- **Private key**: khóa riêng tương ứng với public key trong server certificate.
- **CA trust**: client cần tin cậy CA đã ký certificate server. Với mutual TLS, server còn cần CA trust để xác minh certificate của client.

Certificate server phải có Subject Alternative Name (SAN) phù hợp với DNS name mà client dùng để kết nối, ví dụ grpc.internal.example.com. Client xác minh hostname theo SAN; không nên tắt hostname verification để né lỗi certificate.

Không commit private key vào Git, đóng gói vào source JAR hoặc ghi trực tiếp trong application.yml. Đưa key vào secret manager, Kubernetes Secret hoặc secret mount được bảo vệ; giới hạn quyền đọc file và tránh log nội dung key.

## 3. Khai báo đường dẫn TLS trong cấu hình Spring

Có thể quản lý đường dẫn certificate bằng configuration properties riêng của ứng dụng:

~~~yaml
app:
  grpc:
    tls:
      certificate-chain: /run/secrets/grpc/server-chain.pem
      private-key: /run/secrets/grpc/server-key.pem
      require-client-certificate: false
      client-ca: /run/secrets/grpc/client-ca.pem
~~~

Đây là namespace cấu hình do ứng dụng định nghĩa, không phải property mặc định của mọi Spring gRPC starter. Ví dụ record:

~~~java
@ConfigurationProperties(prefix = "app.grpc.tls")
public record GrpcServerTlsProperties(
    Path certificateChain,
    Path privateKey,
    boolean requireClientCertificate,
    Path clientCa
) {}
~~~

Đăng ký properties bằng ConfigurationPropertiesScan hoặc EnableConfigurationProperties(GrpcServerTlsProperties.class). Ở môi trường production, nên validate file tồn tại, có thể đọc được và có định dạng hợp lệ khi application khởi động để lỗi cấu hình xuất hiện sớm.

## 4. Tạo SslContext cho gRPC server

Với Netty transport, dùng GrpcSslContexts để tạo SslContext có cấu hình phù hợp cho gRPC/HTTP/2:

~~~java
import io.grpc.netty.GrpcSslContexts;
import io.netty.handler.ssl.ClientAuth;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;

@Configuration
@EnableConfigurationProperties(GrpcServerTlsProperties.class)
public class GrpcTlsConfiguration {

    @Bean
    SslContext grpcServerSslContext(
            GrpcServerTlsProperties properties) throws SSLException {

        SslContextBuilder builder = GrpcSslContexts.forServer(
            properties.certificateChain().toFile(),
            properties.privateKey().toFile());

        builder.protocols("TLSv1.3", "TLSv1.2");

        if (properties.requireClientCertificate()) {
            if (properties.clientCa() == null) {
                throw new IllegalStateException(
                    "client-ca is required when mTLS is enabled");
            }
            builder.trustManager(properties.clientCa().toFile());
            builder.clientAuth(ClientAuth.REQUIRE);
        } else {
            builder.clientAuth(ClientAuth.NONE);
        }

        return builder.build();
    }
}
~~~

Ví dụ dùng package Netty không shaded (grpc-netty). Nếu dự án dùng grpc-netty-shaded, các import Netty phải lấy từ package shaded tương ứng; không trộn hai bộ class. Chọn phiên bản transport tương thích với gRPC Java đang dùng.

GrpcSslContexts.forServer(...) thiết lập cấu hình ALPN cần thiết cho gRPC trên Netty. Ví dụ chỉ cho phép TLS 1.3 và TLS 1.2; chính sách thực tế cần theo chuẩn bảo mật của môi trường. Không tự hạ xuống TLS cũ để khắc phục client không tương thích.

## 5. Gắn SslContext vào server

Với gRPC Java server tạo trực tiếp:

~~~java
Server server = NettyServerBuilder.forPort(9090)
    .sslContext(grpcServerSslContext)
    .addService(orderService)
    .build()
    .start();
~~~

NettyServerBuilder.sslContext(...) bật TLS trên transport. Khi dùng Spring starter tự tạo server, cần đưa bean SslContext vào điểm mở rộng cấu hình server builder mà đúng starter/version cung cấp. Không tạo một server thứ hai chỉ để bật TLS nếu starter đã quản lý server lifecycle.

Nếu tự quản lý server bằng Spring, bean có thể khai báo lifecycle start/shutdown theo cơ chế của ứng dụng. Khi shutdown, dừng nhận call mới và cho request đang chạy hoàn tất trong grace period trước khi đóng executor và tài nguyên liên quan.

## 6. TLS một chiều và mutual TLS

### TLS một chiều (server authentication)

Trong cấu hình cơ bản, server trình certificate; client xác minh certificate và hostname. Server không yêu cầu client trình certificate ở TLS handshake. Client vẫn có thể xác thực ở tầng gRPC bằng bearer token, OAuth2 hoặc credential phù hợp.

Đây là lựa chọn phổ biến khi danh tính client được quản lý bằng token/interceptor và server cần bảo vệ kênh truyền.

### Mutual TLS (mTLS)

Với mTLS, server yêu cầu client trình certificate. Server xác minh certificate đó bằng CA trust đã cấu hình. Phần code trên bật mTLS khi require-client-certificate là true:

~~~yaml
app:
  grpc:
    tls:
      certificate-chain: /run/secrets/grpc/server-chain.pem
      private-key: /run/secrets/grpc/server-key.pem
      require-client-certificate: true
      client-ca: /run/secrets/grpc/client-ca.pem
~~~

ClientAuth.REQUIRE buộc client cung cấp certificate được trust manager chấp nhận. Certificate hợp lệ xác định danh tính máy/client ở tầng transport; ứng dụng vẫn cần ánh xạ danh tính đó sang service account, workload identity hoặc policy authorization. Không mặc định cấp quyền nghiệp vụ chỉ vì TLS handshake thành công.

## 7. Cấu hình client phải tương thích với server

Client cần trust CA phát hành certificate server và kết nối bằng hostname có trong SAN. Trong môi trường nội bộ, có thể dùng CA doanh nghiệp hoặc CA riêng được phân phối an toàn tới client.

Với mTLS, client còn cần certificate chain và private key riêng để trình cho server. Không dùng chung private key của server cho client. Quản lý vòng đời certificate client theo workload identity và thu hồi khi credential không còn hợp lệ.

Nếu TLS được kết thúc tại gateway/proxy thay vì Spring gRPC server, chặng proxy-to-backend vẫn cần được bảo vệ theo trust boundary. Có thể dùng TLS hoặc mTLS nội bộ; tránh chuyển plaintext qua mạng không tin cậy chỉ vì client-facing hop đã được mã hóa.

## 8. Certificate rotation và cấu hình khi triển khai

Certificate có thời hạn. Quy trình vận hành cần:

1. Cấp certificate mới với SAN đúng và chain đầy đủ.
2. Phân phối certificate/private key qua secret management.
3. Kiểm tra quyền file, định dạng PEM và cặp certificate/key khớp nhau.
4. Cập nhật SslContext hoặc restart/reload server theo khả năng của integration đang dùng.
5. Xác minh client handshake thành công với certificate mới.
6. Thu hồi certificate cũ theo quy trình CA khi hết giai đoạn chuyển tiếp.

Thay file trên disk không có nghĩa SslContext đã tạo trước đó tự nạp certificate mới. Nếu ứng dụng không hỗ trợ reload TLS context động, cần rolling restart có kiểm soát. Trong giai đoạn chuyển đổi CA, có thể cần trust đồng thời CA cũ và mới để tránh làm gián đoạn client.

## 9. Kiểm thử cấu hình TLS

Không thể xác minh TLS handshake chỉ bằng in-process transport vì transport này không thiết lập TLS socket thực. Cần integration test bằng Netty server và client qua loopback hoặc môi trường test tương đương.

Các trường hợp cần kiểm tra:

- Client trust đúng CA và hostname khớp SAN: handshake thành công, RPC hoạt động.
- Client không trust CA: handshake thất bại.
- Hostname không khớp SAN hoặc certificate hết hạn: client từ chối kết nối.
- Server yêu cầu mTLS nhưng client không trình certificate: handshake thất bại.
- Client trình certificate do CA không tin cậy ký: server từ chối.
- Certificate/key không khớp hoặc file không đọc được: server không khởi động thành công.
- HTTP/2 ALPN chọn h2 và gRPC trailers/status vẫn hoạt động.

Kiểm thử cả trường hợp plaintext tới cổng TLS để chắc server không vô tình chấp nhận kết nối không mã hóa. Không dùng chế độ trust-all trong test vì nó che giấu lỗi xác minh certificate.

## 10. Chẩn đoán lỗi handshake

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| UNAVAILABLE kèm lỗi handshake | TLS negotiation thất bại | Xem cause chain, protocol và cipher tương thích |
| Certificate unknown/untrusted | Client thiếu CA hoặc chain server không đầy đủ | Kiểm tra trust store và intermediate certificates |
| Hostname verification failed | SAN không khớp target | Kết nối bằng DNS name đúng hoặc cấp lại certificate |
| Bad certificate ở server | Client certificate không được trust hoặc thiếu EKU phù hợp | Kiểm tra client CA, certificate usage và mTLS policy |
| ALPN không chọn được h2 | Proxy/transport không thương lượng HTTP/2 | Kiểm tra ALPN và cấu hình HTTP/2 trên từng hop |
| Server không khởi động | Sai đường dẫn, quyền file, PEM lỗi hoặc key không khớp | Validate secret mount và certificate/key pair |

Không log private key, token hoặc toàn bộ certificate material vào log ứng dụng. Có thể log fingerprint, subject, issuer, expiry và handshake failure category để hỗ trợ vận hành.

## 11. Ghi nhớ và tự kiểm tra

**Cấu hình TLS cho server** cần certificate chain, private key tương ứng và SslContext được gắn vào gRPC server transport. Với Netty, GrpcSslContexts hỗ trợ cấu hình ALPN cho HTTP/2; mTLS bổ sung client CA trust và ClientAuth.REQUIRE. Trong Spring, quản lý đường dẫn qua configuration properties/secret mount và tích hợp SslContext vào server mà starter đang sở hữu.

Tự kiểm tra:

1. Vì sao certificate server cần SAN khớp hostname client sử dụng?
2. grpc-timeout và TLS giải quyết hai vấn đề khác nhau như thế nào?
3. mTLS khác TLS một chiều ở yêu cầu certificate phía client ra sao?
4. Vì sao thay file certificate không bảo đảm SslContext đang chạy đã được cập nhật?
5. Cần kiểm thử những gì ngoài việc xác nhận server khởi động thành công?

TLS được cấu hình và vận hành đúng giúp Spring gRPC mã hóa kênh truyền, xác thực danh tính server/client theo chính sách và duy trì kết nối HTTP/2 an toàn qua các môi trường triển khai.
