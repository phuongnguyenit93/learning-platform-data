# Kiểm thử TLS với certificate test

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích handshake TLS và vai trò của certificate trong gRPC qua HTTP/2.
- Tạo CA và server certificate dành riêng cho integration test.
- Cấu hình gRPC server Netty dùng certificate test và private key tương ứng.
- Cấu hình client trust CA, kết nối bằng hostname khớp Subject Alternative Name (SAN).
- Kiểm thử cả kết nối hợp lệ và các trường hợp certificate không đáng tin hoặc hostname không khớp.
- Quản lý certificate, channel và server theo vòng đời Spring test context.
- Phân biệt TLS xác thực server với mutual TLS (mTLS) xác thực cả client.

## 1. Vì sao phải kiểm thử TLS qua gRPC?

gRPC dùng HTTP/2 làm transport. Trong môi trường triển khai bảo mật, client và server thường thiết lập TLS trước khi trao đổi các frame HTTP/2 và message Protobuf. Một integration test dùng plaintext chỉ xác nhận RPC hoạt động qua transport không mã hóa; nó không kiểm tra certificate chain, hostname verification, trust store hoặc TLS handshake.

Với **SPRING_GRPC**, TLS có thể được cấu hình tại server do starter quản lý hoặc trên Netty server/channel. Test cần đi qua đúng đường kết nối TLS mà ứng dụng sử dụng, gọi RPC thật để kích hoạt handshake và xác nhận client chỉ tin server có certificate hợp lệ.

Một channel có thể được tạo trước khi handshake xảy ra. Vì vậy, việc gọi **build()** thành công không chứng minh TLS đã thiết lập. Hãy thực hiện ít nhất một RPC và kiểm tra kết quả.

## 2. Certificate test gồm những thành phần nào?

Một cấu hình server-auth TLS thường có:

- **CA certificate**: chứng thư CA mà client tin cậy.
- **Server certificate**: chứng thư định danh server, được CA ký.
- **Server private key**: khóa riêng tương ứng với server certificate.
- **Subject Alternative Name (SAN)**: tên DNS hoặc địa chỉ IP mà client dùng để kết nối.
- **Certificate chain**: server certificate cùng intermediate certificate cần thiết để client xây dựng chuỗi tin cậy.

Client giữ CA certificate trong trust store. Server giữ certificate chain và private key. Server không cần nhận private key của CA; CA private key chỉ dùng khi ký certificate và phải được bảo vệ riêng.

Hostname client dùng để kết nối phải khớp một SAN của server certificate. Nếu test kết nối tới **localhost**, certificate cần có **DNS:localhost**. Nếu kết nối tới **127.0.0.1**, certificate cần có SAN dạng IP tương ứng. Trường Common Name (CN) không thay thế SAN trong hostname verification hiện đại.

## 3. Tạo CA và server certificate dành cho test

Có thể tạo một CA test cục bộ, sau đó ký server certificate có SAN **localhost**. Ví dụ dưới đây cần OpenSSL hỗ trợ tùy chọn **-addext**:

~~~bash
mkdir -p src/test/resources/tls
cd src/test/resources/tls

# Tạo CA test. Không dùng CA private key này cho production.
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout test-ca.key \
  -out test-ca.crt \
  -days 30 \
  -subj "/CN=Spring gRPC Test CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"

# Tạo private key và CSR cho server.
openssl req -newkey rsa:2048 -nodes \
  -keyout server.key \
  -out server.csr \
  -subj "/CN=localhost"

# Các extension của server certificate.
cat > server.ext <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost
EOF

# Ký server certificate bằng CA test.
openssl x509 -req \
  -in server.csr \
  -CA test-ca.crt \
  -CAkey test-ca.key \
  -CAcreateserial \
  -out server.crt \
  -days 30 \
  -sha256 \
  -extfile server.ext
~~~

Đưa **server.crt**, **server.key** và **test-ca.crt** vào test resources theo chính sách repository. **test-ca.key**, CSR và file serial chỉ cần trong bước tạo certificate; không commit CA private key. Server private key trong test fixture không được tái sử dụng ở môi trường thật.

Certificate có thời hạn ngắn giúp tránh dùng test credential lâu dài. Khi certificate được tạo tự động trong test, hãy giữ SAN, key usage và extended key usage đúng mục đích; certificate server cần **serverAuth**.

Nếu CA ký qua intermediate CA, server nên gửi leaf certificate cùng intermediate certificate theo đúng thứ tự chain. Client thường chỉ cần trust root CA. Không khắc phục lỗi chain bằng cách tắt xác minh certificate.

## 4. Khởi động Netty gRPC server với certificate test

Với fixture tự quản lý server, Netty server nhận certificate chain và private key:

~~~java
import io.grpc.BindableService;
import io.grpc.Server;
import io.grpc.netty.GrpcSslContexts;
import io.grpc.netty.NettyServerBuilder;
import io.netty.handler.ssl.SslContext;
import java.io.File;
import java.util.concurrent.TimeUnit;
import org.springframework.context.SmartLifecycle;

final class TlsTestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private final File certificateChain;
    private final File privateKey;
    private volatile Server server;

    TlsTestGrpcServer(
            BindableService service,
            File certificateChain,
            File privateKey) {
        this.service = service;
        this.certificateChain = certificateChain;
        this.privateKey = privateKey;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        try {
            SslContext sslContext = GrpcSslContexts
                .forServer(certificateChain, privateKey)
                .build();

            server = NettyServerBuilder.forPort(0)
                .sslContext(sslContext)
                .addService(service)
                .build()
                .start();
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Cannot start TLS gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("TLS gRPC server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }
        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        Server current = server;
        return current != null && !current.isShutdown();
    }
}
~~~

**forServer(...)** tạo TLS context từ certificate chain và private key. **forPort(0)** để hệ điều hành cấp port động; test lấy port thực tế sau khi server đã start.

Đây là fixture dành cho trường hợp test tự sở hữu server. Nếu Spring gRPC starter đã khởi động server, hãy cấu hình TLS trên server do starter quản lý và dùng test support của starter để lấy port. Không tạo thêm một Netty server thứ hai cho cùng service chỉ để kiểm thử TLS.

## 5. Đăng ký fixture trong Spring test context

Test configuration có thể inject service bean và certificate từ test resources:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class TlsGrpcTestConfiguration {
    @Bean
    TlsTestGrpcServer tlsTestGrpcServer(
            GreeterServiceImpl greeter) throws IOException {
        File cert = new ClassPathResource("tls/server.crt").getFile();
        File key = new ClassPathResource("tls/server.key").getFile();
        return new TlsTestGrpcServer(greeter, cert, key);
    }
}
~~~

Ví dụ dùng **ClassPathResource.getFile()** phù hợp với test resources được bung thành file trong test classpath. Nếu test chạy từ một archive mà resource không có filesystem path, copy resource sang temporary file và xóa file tạm khi context đóng.

Với Spring Boot, **@SpringBootTest** tạo context, còn **SmartLifecycle** fixture khởi động server sau khi bean đã được tạo. Spring gọi **stop()** khi context đóng. Nếu starter đã tự đăng ký service và server, thay fixture bằng cấu hình TLS và accessor của starter; một context chỉ nên có một chủ sở hữu server lifecycle.

## 6. Cấu hình client tin cậy CA test

Client dùng CA certificate làm trust anchor và kết nối bằng hostname có trong SAN:

~~~java
File caCertificate =
    new ClassPathResource("tls/test-ca.crt").getFile();

SslContext clientSslContext = GrpcSslContexts.forClient()
    .trustManager(caCertificate)
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("localhost", tlsServer.port())
    .sslContext(clientSslContext)
    .build();

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);
~~~

Ở đây client chỉ tin certificate chain được ký bởi CA test. Hostname **localhost** phải khớp SAN của server certificate. Netty/gRPC thực hiện kiểm tra chain và hostname theo TLS configuration; không cần tắt xác minh để test kết nối được.

Không gọi **usePlaintext()** trong test TLS. Cũng không dùng **overrideAuthority()** để che hostname mismatch trong test thông thường. Nếu production có authority routing đặc biệt, hãy viết test riêng cho authority đó và bảo đảm certificate vẫn được xác minh theo đúng danh tính dự kiến.

## 7. Thực hiện RPC để kích hoạt handshake

TLS handshake thường được thực hiện khi channel bắt đầu kết nối, không nhất thiết ngay lúc tạo channel. Do đó, hãy gọi RPC để buộc client kết nối và xác minh certificate:

~~~java
@SpringBootTest
@Import(TlsGrpcTestConfiguration.class)
class GreeterTlsIntegrationTest {
    @Autowired
    TlsTestGrpcServer tlsServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() throws Exception {
        File ca = new ClassPathResource("tls/test-ca.crt").getFile();
        SslContext ssl = GrpcSslContexts.forClient()
            .trustManager(ca)
            .build();

        channel = NettyChannelBuilder
            .forAddress("localhost", tlsServer.port())
            .sslContext(ssl)
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(3, TimeUnit.SECONDS);
    }

    @Test
    void acceptsCertificateSignedByTrustedTestCa() {
        HelloReply reply = stub.sayHello(
            HelloRequest.newBuilder().setName("Linh").build());

        assertEquals("Hello, Linh", reply.getMessage());
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Tên generated service, request và response trong ví dụ cần thay bằng kiểu được sinh từ Protobuf của dự án. Đặt deadline hữu hạn để test không treo nếu handshake hoặc RPC không hoàn tất. Channel do test tạo phải được shutdown; server do Spring context quản lý sẽ dừng khi context đóng.

## 8. Kiểm thử certificate không đáng tin

Một test âm nên dùng CA khác không ký server certificate. Khi client gọi RPC, TLS handshake phải thất bại trước khi method nghiệp vụ được thực thi.

~~~java
File unrelatedCa =
    new ClassPathResource("tls/unrelated-ca.crt").getFile();

SslContext untrustedSsl = GrpcSslContexts.forClient()
    .trustManager(unrelatedCa)
    .build();

ManagedChannel untrustedChannel = NettyChannelBuilder
    .forAddress("localhost", tlsServer.port())
    .sslContext(untrustedSsl)
    .build();

try {
    GreeterGrpc.GreeterBlockingStub untrustedStub =
        GreeterGrpc.newBlockingStub(untrustedChannel)
            .withDeadlineAfter(3, TimeUnit.SECONDS);

    assertThrows(StatusRuntimeException.class, () ->
        untrustedStub.sayHello(
            HelloRequest.newBuilder().setName("Linh").build()));
} finally {
    untrustedChannel.shutdownNow();
}
~~~

Lỗi handshake thường được client quan sát dưới dạng RPC status như **UNAVAILABLE** kèm nguyên nhân TLS trong cause chain; chi tiết status/message có thể phụ thuộc transport và phiên bản. Assertion chính là RPC không tới service method khi trust chain không hợp lệ.

Để xác minh hostname verification, dùng một client target khác với SAN, ví dụ kết nối **127.0.0.1** trong khi certificate chỉ có **DNS:localhost**. Test phải thất bại. Không sửa test bằng cách tắt hostname verification.

## 9. Các thuộc tính certificate cần kiểm tra

| Thuộc tính | Điều cần xác nhận |
| --- | --- |
| Trust chain | Client trust CA ký server certificate; intermediate cần thiết được server gửi. |
| SAN | Có DNS/IP mà client thực sự dùng để kết nối. |
| Validity | Thời điểm hiện tại nằm trong khoảng Not Before/Not After. |
| Key pair | Private key tương ứng với public key trong server certificate. |
| Extended Key Usage | Server certificate có **serverAuth**. |
| Key Usage | Phù hợp thuật toán/key exchange và chữ ký đang sử dụng. |
| Chain order | Leaf certificate đứng trước intermediate certificate trong chain được gửi. |

Certificate hết hạn hoặc chưa có hiệu lực phải bị từ chối. Không tăng độ tin cậy bằng cách thêm leaf certificate tùy tiện vào trust store khi mục tiêu là kiểm tra CA chain.

## 10. Mutual TLS khi server yêu cầu client certificate

TLS server-auth chỉ xác thực server với client. Nếu hệ thống yêu cầu mTLS, server còn yêu cầu client trình certificate được CA mà server tin cậy ký.

Ví dụ cấu hình server yêu cầu client certificate:

~~~java
SslContext serverSsl = GrpcSslContexts
    .forServer(serverCertificate, serverPrivateKey)
    .trustManager(clientCaCertificate)
    .clientAuth(ClientAuth.REQUIRE)
    .build();
~~~

Client cung cấp certificate và private key của chính nó:

~~~java
SslContext clientSsl = GrpcSslContexts.forClient()
    .trustManager(serverCaCertificate)
    .keyManager(clientCertificate, clientPrivateKey)
    .build();
~~~

Client certificate cần có Extended Key Usage phù hợp, thường là **clientAuth**. Server trust CA ký client certificate. Viết test riêng cho:

- Client certificate hợp lệ được chấp nhận.
- Không gửi client certificate bị từ chối.
- Client certificate được CA không tin cậy ký bị từ chối.
- Server certificate vẫn được client xác minh độc lập.

Không bật **ClientAuth.REQUIRE** cho test server-auth thông thường nếu client không được cấu hình identity certificate.

## 11. Lưu trữ certificate và private key trong test

Certificate test không phải secret production, nhưng private key vẫn cần được quản lý có chủ đích:

- Chỉ đặt fixture trong **src/test/resources** hoặc tạo trong thư mục tạm của test.
- Không dùng private key production hoặc CA production trong test.
- Không commit CA private key có thể ký certificate khác; chỉ cần CA certificate để client trust.
- Giới hạn quyền đọc file private key nếu test chạy trên máy dùng chung.
- Không ghi nội dung private key hoặc toàn bộ TLS handshake secret vào log.
- Có thể tái tạo certificate test khi hết hạn thay vì kéo dài thời hạn vô hạn.

Nếu certificate được tạo lúc test chạy, lưu đường dẫn file tạm trong fixture và xóa file khi context đóng. Đảm bảo server đã shutdown trước khi xóa certificate/key mà transport có thể còn cần.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng **usePlaintext()** trong TLS test | Không có TLS handshake được kiểm tra | Dùng Netty TLS channel và trust CA. |
| Certificate chỉ có CN, thiếu SAN | Hostname verification thất bại | Tạo SAN khớp hostname/IP client dùng. |
| Client trust nhầm certificate/CA | Handshake thất bại hoặc trust quá rộng | Trust đúng test CA, kiểm tra chain. |
| Dùng **localhost** nhưng certificate chỉ có IP SAN | Hostname mismatch | Đồng bộ target host và SAN. |
| Chỉ tạo channel mà không gọi RPC | Chưa chứng minh handshake thành công | Gọi RPC có deadline để kích hoạt kết nối. |
| Tắt hostname verification để test pass | Bỏ qua kiểm tra danh tính server | Sửa SAN hoặc target host cho đúng. |
| Server gửi thiếu intermediate certificate | Client không xây dựng được chain | Cấu hình certificate chain đầy đủ. |
| Dùng private key production trong test | Rủi ro lộ credential | Tạo key riêng, chỉ dùng trong test. |
| Nhầm server-auth TLS với mTLS | Test không xác minh client identity | Thêm test riêng với client certificate và ClientAuth.REQUIRE. |
| Đóng server trước channel hoặc call đang chạy | Test teardown không ổn định | Đóng channel/call, rồi để Spring dừng server. |

## 13. Ma trận kiểm thử TLS

Một bộ integration test cơ bản nên bao gồm:

1. CA test tin cậy, SAN khớp: RPC thành công.
2. CA không tin cậy: handshake thất bại.
3. Hostname không khớp SAN: handshake thất bại.
4. Certificate hết hạn/chưa có hiệu lực: handshake thất bại.
5. Chain thiếu intermediate: handshake thất bại khi chain cần intermediate đó.
6. Nếu bật mTLS: client certificate hợp lệ được chấp nhận.
7. Nếu bật mTLS: thiếu hoặc sai client certificate bị từ chối.
8. Channel/server được đóng đúng lifecycle, không giữ thread hoặc file tạm sau test.

Test âm cần kiểm tra rằng service method không được gọi khi TLS handshake thất bại. Có thể dùng spy/counter trên service bean để xác nhận request chưa tới tầng ứng dụng.

## 14. Bài tập thực hành

Tạo integration test TLS cho một service Spring gRPC:

1. Tạo CA test và server certificate có SAN **DNS:localhost**, EKU **serverAuth**.
2. Đăng ký service implementation vào TLS server do starter quản lý hoặc test fixture Netty có Spring lifecycle.
3. Bind port động và lấy port thực tế sau khi server start.
4. Tạo client channel trust CA test, kết nối bằng **localhost** và gọi unary RPC có deadline.
5. Xác nhận RPC thành công với certificate hợp lệ.
6. Tạo client trust một CA khác và xác nhận handshake thất bại.
7. Kết nối bằng hostname không nằm trong SAN và xác nhận bị từ chối.
8. Nếu ứng dụng dùng mTLS, thêm test client certificate hợp lệ và không hợp lệ.
9. Shutdown channel và xác nhận Spring dừng server khi context đóng.

**Tiêu chí hoàn thành:** test chứng minh được handshake TLS thật, trust chain và hostname được xác minh, test âm thất bại đúng lý do và mọi certificate/channel/server fixture được quản lý theo vòng đời.

## 15. Ghi nhớ

- TLS test phải gọi RPC qua Netty TLS transport; channel build thành công chưa chứng minh handshake thành công.
- Server cung cấp certificate chain và private key; client trust CA ký certificate.
- SAN phải khớp hostname/IP client dùng để kết nối; CN không thay thế SAN.
- Kiểm tra validity, key pair, EKU, key usage và intermediate chain.
- Không dùng plaintext, tắt hostname verification hoặc trust mọi certificate để làm test pass.
- Server-auth TLS và mTLS là hai mục tiêu khác nhau; mTLS cần client certificate và server trust client CA.
- Certificate/private key test phải tách biệt credential production.
- Đóng channel của test và để Spring/starter quản lý shutdown server.

Kiểm thử TLS bằng certificate test giúp xác nhận gRPC server chỉ nhận kết nối có danh tính được xác minh, client tin đúng CA và Spring quản lý an toàn vòng đời của server cùng tài nguyên TLS.
