# Quản lý trust store

Trust store là kho chứng thư và trust anchor mà một ứng dụng dùng để quyết định certificate của peer có được tin cậy hay không. Trong gRPC qua TLS, client thường dùng trust store để xác minh certificate server; khi bật mutual TLS (mTLS), server cũng cần trust store để xác minh certificate client. Quản lý trust store đúng cách giúp giới hạn CA được tin cậy, triển khai thay đổi CA có kiểm soát và tránh lỗi kết nối khi certificate được rotate.

Trong Spring gRPC, trust store thuộc cấu hình TLS của channel hoặc server listener. Cần xác định TLS thực tế chạy bằng JSSE hay Netty/OpenSSL, cấu hình đúng trust manager cho từng chiều kết nối và kiểm tra hostname/SAN. Việc một file trust store tồn tại hoặc được mount vào container không chứng minh gRPC channel đang sử dụng file đó.

## 1. Trust store khác key store như thế nào?

Hai loại kho có mục đích khác nhau:

| Kho | Chứa gì? | Dùng để làm gì? |
| --- | --- | --- |
| Trust store | CA certificate hoặc certificate được cấu hình làm trust anchor | Xác minh certificate do peer gửi |
| Key store | Private key và certificate chain tương ứng với private key | Chứng minh danh tính của chính ứng dụng |

Trong TLS một chiều, client cần trust store để xác minh server certificate; server cần private key và server certificate chain trong key material để hoàn tất handshake.

Trong mTLS:

- Client cần trust store để xác minh server.
- Client còn cần key material chứa client private key và certificate chain.
- Server cần key material của server.
- Server cần trust store chứa CA được phép cấp client certificate.

Không đưa private key vào trust store chỉ vì tên file cấu hình có chữ trust. Trust store không thay thế key store, và key store không tự động định nghĩa CA mà ứng dụng tin cậy.

## 2. Trust anchor và certificate chain

Khi peer gửi leaf certificate, verifier xây dựng certificate path từ leaf qua intermediate CA tới một trust anchor đã được cấu hình. Trust anchor thường là root CA certificate, nhưng một số môi trường có thể pin intermediate hoặc leaf certificate theo policy.

```text
orders.internal server certificate (leaf)
             |
             v
       Workload Issuing CA
             |
             v
       Internal Root CA  <--- trust anchor in client trust store
```

Trust store chỉ nên chứa CA cần thiết cho kết nối. Nếu import một CA quá rộng, mọi certificate hợp lệ do CA đó cấp và phù hợp các điều kiện path/hostname/EKU có thể trở thành ứng viên được tin cậy. Giới hạn trust anchor theo môi trường và workload để giảm phạm vi ảnh hưởng khi CA key bị lộ.

Intermediate certificate thường được peer gửi trong handshake để client xây dựng chain. Không nhất thiết phải import mọi intermediate vào trust store nếu server cung cấp chain đầy đủ và root CA đã được tin cậy. Nếu thiếu intermediate, handshake có thể thất bại dù root CA đã có trong trust store.

## 3. Chọn định dạng và bảo vệ trust store

Java hỗ trợ nhiều keystore type. PKCS12 thường là lựa chọn phù hợp cho cấu hình mới vì là định dạng tiêu chuẩn và có thể chứa certificate/key entry:

```bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12
```

Lệnh trên nhập certificate vào trust store; xác nhận fingerprint trước khi chấp nhận certificate. Không dùng câu trả lời tự động xác nhận trust cho một certificate chưa được xác minh nguồn.

Kiểm tra nội dung:

```bash
keytool -list -v \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12
```

Kiểm tra alias, subject, issuer, serial number, validity period, SHA-256 fingerprint và entry type. Trust entry phải chứa certificate đúng CA/trust anchor dự kiến; không nhầm với private key entry.

Password bảo vệ cấu trúc kho và có thể bảo vệ dữ liệu nhạy cảm trong file, nhưng không thay thế file permission, secret management hoặc bảo vệ host. Không commit password vào source code, Docker image hoặc repository. Cấp password qua secret manager hoặc cơ chế secret injection của nền tảng; giới hạn quyền đọc file cho process cần dùng.

## 4. Xây dựng trust store từ nhiều CA

Một ứng dụng có thể kết nối nhiều hệ thống nội bộ được cấp certificate bởi các CA khác nhau. Có thể nhập nhiều CA vào cùng một trust store với alias riêng:

```bash
keytool -importcert \
  -alias orders-root-ca \
  -file orders-root-ca.pem \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12

keytool -importcert \
  -alias payments-root-ca \
  -file payments-root-ca.pem \
  -keystore grpc-truststore.p12 \
  -storetype PKCS12
```

Mỗi alias phải mô tả rõ CA và môi trường. Không tái sử dụng alias chung như ca1 hoặc cert nếu nó khiến việc audit và rotation khó khăn. Nếu hai hệ thống không nên tin cùng CA, cân nhắc trust store riêng hoặc trust manager riêng theo channel thay vì gom tất cả CA vào một kho toàn cục.

Trước khi import, xác minh fingerprint của CA qua kênh tin cậy độc lập. Một file PEM có tên internal-root-ca.pem không chứng minh nội dung của nó thực sự thuộc CA nội bộ.

## 5. Dùng trust store với JSSE TrustManagerFactory

Với TLS dựa trên JSSE, TrustManagerFactory tạo trust manager từ trust store:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

Path trustStorePath = Path.of("/run/secrets/grpc-truststore.p12");
char[] password = loadTrustStorePassword();

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustStorePath)) {
    trustStore.load(input, password);
}

TrustManagerFactory trustManagers =
    TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, trustManagers.getTrustManagers(), null);
```

Ví dụ tạo SSLContext tin cậy peer theo trust store. Nó chưa cấu hình client certificate/private key; mTLS cần KeyManagerFactory riêng và truyền key managers vào sslContext.init. Xóa hoặc làm sạch password char array sau khi sử dụng theo cách phù hợp với lifecycle của ứng dụng.

Đối với client, trust manager này xác minh certificate server. Đối với server mTLS, trust manager được cấu hình tương tự để xác minh certificate client. Cần đặt hostname verification ở client; trust chain hợp lệ nhưng SAN không khớp hostname vẫn phải bị từ chối.

## 6. Trust store trong grpc-java Netty

Nếu gRPC dùng Netty transport, TLS context thường được tạo bằng Netty SslContext. Ví dụ client trust CA từ PEM:

```java
import io.grpc.netty.GrpcSslContexts;
import io.grpc.netty.NettyChannelBuilder;
import io.netty.handler.ssl.SslContext;

SslContext clientTls = GrpcSslContexts.forClient()
    .trustManager(new File("/run/secrets/internal-root-ca.pem"))
    .build();

ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal", 8443)
    .sslContext(clientTls)
    .build();
```

Package/import có thể khác nếu dự án dùng grpc-netty-shaded; khi đó dùng namespace shaded tương ứng và không trộn class Netty thường với shaded. API cụ thể cần khớp phiên bản grpc-java trong dependency graph.

Ví dụ server mTLS cần cả server key material và CA tin cậy cho client:

```java
SslContext serverTls = GrpcSslContexts.forServer(
        new File("/run/secrets/server-chain.pem"),
        new File("/run/secrets/server-key.pem"))
    .trustManager(new File("/run/secrets/client-root-ca.pem"))
    .clientAuth(ClientAuth.REQUIRE)
    .build();
```

Ở phía server, trustManager chỉ định CA dùng để xác minh client certificate; clientAuth(REQUIRE) yêu cầu client trình certificate. Nếu chỉ cấu hình server certificate mà không bật clientAuth, server không thực hiện mTLS client authentication.

Không phải mọi Spring gRPC starter đều expose trực tiếp SslContext hoặc cùng một builder API. Một số cấu hình dùng SSL bundle, customizer hoặc extension point riêng. Chọn đúng hook mà phiên bản starter cung cấp; không tự tạo property giả định rồi cho rằng nó được áp dụng.

## 7. Trust store cho client và server trong mTLS

Mỗi phía có trust decision độc lập:

| Thành phần | Key material | Trust store |
| --- | --- | --- |
| gRPC client | Client certificate/private key nếu mTLS | CA cấp server certificate |
| gRPC server | Server certificate/private key | CA cấp client certificate |

Nếu client và server dùng cùng một internal CA, có thể cùng trust root đó. Nếu các workload được chia miền tin cậy, dùng CA riêng hoặc trust store riêng để một service không tự động tin certificate của mọi workload.

Server certificate cần SAN khớp DNS name mà client kết nối. Client certificate cần EKU/key usage phù hợp vai trò client và subject/SAN/URI SAN theo identity policy của hệ thống. Trust store xác minh chain; authorization vẫn phải kiểm tra identity và quyền sau TLS handshake.

Không tắt hostname verification để xử lý lỗi SAN. Sửa certificate hoặc target hostname theo contract. Tương tự, không chuyển sang trust-all TrustManager để bỏ qua lỗi trust chain trong production.

## 8. Kiểm tra hostname, chain và certificate bằng công cụ

Có thể dùng OpenSSL để quan sát server certificate chain và kiểm tra trust:

```bash
openssl s_client \
  -connect orders.internal:8443 \
  -servername orders.internal \
  -showcerts \
  -verify_return_error \
  -CAfile internal-root-ca.pem
```

Với môi trường mTLS, thêm client certificate và private key:

```bash
openssl s_client \
  -connect orders.internal:8443 \
  -servername orders.internal \
  -cert client-chain.pem \
  -key client-key.pem \
  -CAfile server-root-ca.pem \
  -verify_return_error
```

Lệnh này hữu ích để kiểm tra handshake độc lập với ứng dụng, nhưng không chứng minh Spring gRPC đang nạp đúng trust store hoặc dùng đúng TLS provider. Cần kiểm tra cấu hình runtime và gọi RPC bằng channel thực tế.

Khi chẩn đoán, phân biệt:

- Unknown CA: trust anchor thiếu hoặc chain không xây dựng được.
- Expired/not yet valid: thời gian certificate không hợp lệ.
- SAN/hostname mismatch: danh tính server không khớp target.
- Missing intermediate: peer không gửi chain cần thiết.
- Wrong EKU/key usage: certificate không hợp vai trò client/server.
- Client certificate required: server bật mTLS nhưng client không trình certificate.

Không gửi private key hoặc password lên log/ticket. Có thể chia sẻ subject, issuer, serial và fingerprint sau khi đánh giá mức độ nhạy cảm.

## 9. Cập nhật trust store và rotation CA

Thay đổi trust anchor cần được triển khai theo thứ tự để tránh outage:

1. Phân phối CA mới vào trust store của client/server cần tin certificate mới.
2. Xác minh file, alias, fingerprint và trust manager đã nạp CA mới.
3. Triển khai leaf certificate mới được CA mới ký.
4. Mở kết nối mới và kiểm tra TLS/mTLS cùng RPC nghiệp vụ.
5. Theo dõi handshake error trên toàn bộ replica.
6. Sau khi không còn peer hợp lệ dùng CA cũ, loại CA cũ khỏi trust store.

Giai đoạn overlap cho phép trust cả CA cũ và mới trong thời gian chuyển đổi. Không xóa CA cũ trước khi mọi peer cần thiết đã chuyển certificate, trừ khi CA cũ bị compromise và cần thu hồi khẩn cấp.

Một trust store file được cập nhật trên disk không nhất thiết được process đang chạy nạp lại. TrustManagerFactory/SSLContext/Netty SslContext thường được tạo từ dữ liệu tại thời điểm khởi tạo. Cần reload TLS context, tạo channel/server mới hoặc restart instance theo cơ chế được ứng dụng hỗ trợ.

Với gRPC HTTP/2, channel có thể giữ connection lâu dài. Để dùng trust store mới, drain và tạo channel mới để handshake mới sử dụng cấu hình mới. Xác minh mọi replica, sidecar và gateway có cùng trust policy trước khi kết thúc rotation.

## 10. Quản lý trust store trong Spring deployment

Trong Spring gRPC, trust store thường được cung cấp dưới dạng mounted secret hoặc file được quản lý bởi platform. Các nguyên tắc:

- Đặt trust store ngoài application artifact và container image.
- Dùng quyền file tối thiểu; process chỉ cần đọc file.
- Truyền password qua secret manager/environment injection có kiểm soát, không commit vào YAML công khai.
- Tách trust store theo môi trường và workload boundary.
- Ghi nhận version, fingerprint, issuer và thời điểm cập nhật.
- Có cơ chế reload/recreate channel hoặc rolling restart khi trust store đổi.
- Theo dõi lỗi handshake và certificate chain sau rollout.

Nếu dùng Spring Boot SSL bundle hoặc starter-specific TLS configuration, kiểm tra bundle đó được áp dụng vào đúng gRPC channel/server. Cấu hình Actuator HTTPS hoặc HTTP server không tự động chứng minh gRPC Netty listener dùng cùng trust store.

## 11. Kiểm thử trust store

Tạo CA/certificate riêng cho test. Không dùng production private key. Ma trận test cơ bản:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Server certificate do CA trong trust store ký | Client handshake thành công |
| Server certificate do CA không tin cậy ký | Client từ chối handshake |
| Thiếu intermediate trong chain | Handshake thất bại trừ khi chain có thể được xây dựng hợp lệ |
| SAN không khớp target hostname | Client từ chối server |
| Server certificate hết hạn | Handshake thất bại |
| mTLS client certificate do CA được server tin cậy ký | Server chấp nhận handshake |
| Client certificate do CA không tin cậy ký | Server từ chối handshake |
| Client không gửi certificate khi server REQUIRE | Handshake thất bại |
| Trust store mới được nạp vào channel mới | Kết nối theo CA mới thành công |
| Channel cũ giữ TLS context cũ | Hành vi được xác minh trước khi drain |
| Alias/fingerprint sai | Deployment validation phát hiện |
| Password hoặc file permission sai | Ứng dụng báo lỗi cấu hình rõ ràng |

Test integration cần chạy qua gRPC channel thực tế, không chỉ gọi TrustManager trực tiếp. Xác minh client hostname verification, server mTLS client validation, status/transport error mà ứng dụng quan sát và hành vi khi channel được recreate.

## 12. Bài tập vận dụng

Một nền tảng có OrderClient gọi OrderService qua mTLS. Hai service hiện dùng Internal Root CA v1; tổ chức chuẩn bị chuyển sang Root CA v2. OrderClient chạy nhiều replica với channel HTTP/2 dài hạn.

**Yêu cầu:**

1. Xác định key material và trust store cần có ở client và server.
2. Tạo trust store PKCS12 chứa CA v1 và CA v2 trong giai đoạn overlap.
3. Xác minh alias, issuer, serial và SHA-256 fingerprint trước khi triển khai.
4. Cấu hình client trust server CA và server trust client CA theo đúng TLS provider.
5. Kiểm tra hostname/SAN và EKU của cả hai certificate.
6. Triển khai leaf certificate mới, tạo channel mới và xác minh mTLS.
7. Drain channel cũ trước khi loại CA v1 khỏi trust store.
8. Viết test chứng minh CA không tin cậy và hostname sai bị từ chối.
9. Kiểm tra Spring gRPC starter đang dùng đúng trust manager/TLS context, không chỉ kiểm tra file được mount.

**Câu hỏi tự kiểm tra:**

- Trust store khác key store ở dữ liệu và mục đích nào?
- Trust anchor và intermediate certificate có vai trò gì?
- Vì sao import CA quá rộng làm tăng trust boundary?
- Trong mTLS, client và server cần trust store của ai?
- Vì sao chain hợp lệ nhưng hostname sai vẫn phải thất bại?
- TrustManagerFactory tạo thành phần nào trong JSSE?
- Netty SslContext và JSSE SSLContext có thể khác nhau thế nào?
- Vì sao cập nhật file trust store không tự thay đổi SSLContext đang chạy?
- Tại sao phải drain channel HTTP/2 khi rotation trust anchor?
- Những test nào chứng minh gRPC listener thực sự dùng trust store mới?

**Ghi nhớ:** Trust store xác định CA/certificate mà peer được tin cậy; key store cung cấp private key và certificate của chính ứng dụng. Trong mTLS, mỗi phía vừa trình key material vừa xác minh trust chain của peer. Quản lý alias/fingerprint, hostname và EKU; triển khai CA mới theo giai đoạn overlap; reload TLS context và tạo channel mới; kiểm thử qua đúng Spring gRPC TLS provider đang chạy.
