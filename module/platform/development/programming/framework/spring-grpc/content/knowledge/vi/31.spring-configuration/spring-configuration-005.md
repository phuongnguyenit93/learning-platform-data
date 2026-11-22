# Cấu hình TLS cho client trong Spring gRPC

Trong hệ sinh thái **SPRING_GRPC**, client thường gọi service qua mạng nội bộ, service mesh hoặc load balancer. TLS bảo vệ dữ liệu trên đường truyền và xác minh danh tính server trước khi client gửi request. Khi cần xác thực cả hai đầu, client còn trình certificate của chính workload bằng mutual TLS (mTLS).

Spring Boot tích hợp cấu hình TLS của gRPC client với **SSL bundle** và các properties theo từng channel. Nhờ đó, ứng dụng có thể chọn TLS một chiều hoặc mTLS, quản lý truststore/keystore theo môi trường và tạo stub từ channel đã cấu hình. Bài này tập trung vào cấu hình TLS phía client, cách kiểm tra certificate/hostname và kiểm thử kết nối thực tế.

## 1. Client cần xác minh điều gì?

Trong TLS một chiều, server trình certificate; client phải xác minh:

- Certificate còn hiệu lực tại thời điểm kết nối.
- Certificate chain dẫn tới CA mà client tin cậy.
- Hostname trong địa chỉ client dùng để kết nối khớp với Subject Alternative Name (SAN) của certificate.
- Certificate có mục đích sử dụng phù hợp cho server authentication.
- TLS handshake thương lượng được HTTP/2 (ALPN `h2`) để gRPC hoạt động.

Trong mTLS, server cũng yêu cầu client trình certificate. Khi đó client cần thêm private key và certificate của workload; server xác minh chain của client theo truststore phía server.

| Cơ chế | Certificate được trình | Bên xác minh |
| --- | --- | --- |
| TLS một chiều | Server certificate | Client xác minh server |
| mTLS | Server và client certificate | Cả client và server xác minh peer |

TLS xác minh danh tính ở tầng kết nối. Nó không tự quyết định service account có quyền gọi RPC nào; authorization theo method vẫn có thể cần token, scope hoặc policy ở tầng ứng dụng.

## 2. Cấu hình TLS một chiều bằng channel properties

Với server dùng certificate do CA công cộng hoặc CA đã có trong JVM truststore cấp, có thể bật TLS trực tiếp trên channel:

```yaml
spring:
  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            enabled: true
```

Trong đó:

- `inventory` là tên logical channel mà ứng dụng dùng khi tạo stub.
- `target` xác định endpoint gRPC. Scheme `static://` chỉ định target tĩnh.
- `ssl.enabled: true` bật TLS cho channel.

Ví dụ tương đương trong `application.properties`:

```properties
spring.grpc.client.channel.inventory.target=static://inventory.internal.example:9090
spring.grpc.client.channel.inventory.ssl.enabled=true
```

Nếu certificate server được ký bởi CA mà JVM tin cậy, client có thể dùng trust mặc định. Nếu server dùng CA nội bộ hoặc private PKI, cấu hình trust material riêng bằng SSL bundle như phần tiếp theo.

Tên DNS trong `target` phải khớp SAN của server certificate. Nếu client kết nối bằng IP, certificate cần có SAN kiểu IP tương ứng; không nên bỏ xác minh hostname để né lỗi cấu hình certificate.

## 3. Dùng SSL bundle với CA riêng

Spring Boot SSL bundle gom truststore và/hoặc keystore dưới một tên. Với TLS một chiều dùng CA nội bộ, client chỉ cần truststore chứa CA phát hành certificate server.

Ví dụ PEM:

```yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-trust:
          truststore:
            certificate: "file:/etc/pki/inventory/server-ca-chain.pem"

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-trust
```

File truststore chứa CA root và, khi cần, intermediate CA mà client dùng để xây dựng certificate chain. Không cần đưa private key của server vào client truststore.

Có thể dùng JKS/PKCS12 thay cho PEM:

```yaml
spring:
  ssl:
    bundle:
      jks:
        inventory-trust:
          truststore:
            location: "file:/etc/pki/inventory/truststore.p12"
            password: ${INVENTORY_TRUSTSTORE_PASSWORD}
            type: PKCS12

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-trust
```

Khi channel tham chiếu `ssl.bundle`, TLS được bật tự động trừ khi cấu hình bị override. Nên chọn một nguồn trust rõ ràng cho mỗi channel để tránh nhầm CA mặc định với CA nội bộ.

## 4. Cấu hình mTLS bằng SSL bundle

Với mTLS, client cần cả:

- Truststore chứa CA dùng để xác minh server.
- Keystore chứa client certificate chain và private key tương ứng.

Ví dụ bundle PEM:

```yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-mtls:
          keystore:
            certificate: "file:/run/secrets/grpc/client-chain.pem"
            private-key: "file:/run/secrets/grpc/client.key"
          truststore:
            certificate: "file:/etc/pki/inventory/server-ca.pem"

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-mtls
```

Server phải được cấu hình yêu cầu client authentication và trust CA đã cấp client certificate. Nếu server không yêu cầu client certificate, client certificate có thể không được sử dụng trong handshake theo chính sách server.

Tương đương với PKCS12:

```yaml
spring:
  ssl:
    bundle:
      jks:
        inventory-mtls:
          keystore:
            location: "file:/run/secrets/grpc/client.p12"
            password: ${CLIENT_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: "file:/etc/pki/inventory/server-trust.p12"
            password: ${SERVER_TRUSTSTORE_PASSWORD}
            type: PKCS12

  grpc:
    client:
      channel:
        inventory:
          target: static://inventory.internal.example:9090
          ssl:
            bundle: inventory-mtls
```

Không đóng gói private key hoặc mật khẩu keystore vào JAR, Docker image hay Git. Mount key từ secret manager với quyền đọc tối thiểu; certificate công khai và private key phải được quản lý như hai loại dữ liệu có độ nhạy khác nhau.

## 5. Tạo stub từ channel đã cấu hình

Sau khi khai báo channel properties, inject `GrpcChannelFactory` để tạo channel và bind generated stub:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.grpc.client.GrpcChannelFactory;

@Configuration
class InventoryClientConfiguration {

    @Bean
    StockServiceGrpc.StockServiceBlockingStub stockStub(
            GrpcChannelFactory channels) {

        return StockServiceGrpc.newBlockingStub(
                channels.createChannel("inventory"));
    }
}
```

Channel tên `inventory` được resolve từ `spring.grpc.client.channel.inventory`. TLS được áp dụng khi channel được tạo; generated stub không cần tự xây dựng SSL context.

Nếu dự án dùng `@ImportGrpcClients` để Spring tự tạo stub bean, có thể cấu hình channel target tương ứng trong properties và để cơ chế import bind stub vào channel. Chọn cách tạo thủ công hoặc tự động theo cấu trúc ứng dụng, nhưng bảo đảm stub đang dùng đúng channel có TLS.

Không tạo một `ManagedChannel` mới cho từng RPC. Channel nên được quản lý theo vòng đời ứng dụng và được shutdown đúng lúc khi ứng dụng dừng.

## 6. Tên channel, hostname và certificate SAN

TLS không chỉ kiểm tra CA. Client còn phải xác minh danh tính server theo hostname mà nó gọi.

Ví dụ target:

```yaml
target: static://inventory.internal.example:9090
```

Certificate server cần có SAN phù hợp, chẳng hạn:

```text
DNS:inventory.internal.example
```

Nếu client gọi một alias DNS khác, alias đó cũng cần được certificate bao phủ. Kết nối tới IP đòi hỏi SAN dạng IP; chỉ có DNS SAN không đủ để xác minh địa chỉ IP.

Khi có load balancer hoặc service discovery, certificate phải phù hợp với tên mà client thực sự dùng làm authority. Không giải quyết hostname mismatch bằng cách tắt certificate validation; sửa DNS, target hoặc certificate SAN cho khớp.

## 7. Phân biệt TLS với authentication metadata

Một channel có thể vừa dùng TLS vừa gửi Bearer token hoặc metadata xác thực:

- TLS mã hóa request/response và xác minh server certificate.
- mTLS bổ sung danh tính workload ở tầng kết nối.
- Bearer token xác định principal/claims ở tầng RPC.
- Authorization quyết định principal có quyền gọi method hay không.

Nếu service yêu cầu OAuth2, cấu hình TLS không tự thêm token. Dùng client interceptor hoặc cơ chế credential riêng để gửi metadata trên từng RPC. Ngược lại, Bearer token không thay thế TLS vì token có thể bị lộ nếu gửi qua kết nối plaintext không tin cậy.

## 8. Không tắt xác minh certificate trong production

Spring Boot có property `bypass-certificate-validation` cho channel, chủ yếu để hỗ trợ một số tình huống kiểm thử. Khi bật, client bỏ qua kiểm tra certificate server; kết nối có thể chấp nhận server giả mạo và làm mất bảo đảm danh tính TLS.

Không dùng cấu hình sau trong production:

```yaml
spring:
  grpc:
    client:
      channel:
        inventory:
          bypass-certificate-validation: true
```

Nếu handshake thất bại, tìm nguyên nhân thực:

- CA chưa có trong truststore.
- Thiếu intermediate certificate.
- Certificate hết hạn hoặc chưa đến thời điểm hiệu lực.
- Hostname không khớp SAN.
- Server không gửi đúng certificate chain.
- Client và server không thống nhất TLS/HTTP2 hoặc cipher/protocol được phép.

Chỉ dùng chế độ bỏ qua xác minh trong test cô lập, không kết nối dữ liệu thật và không để cấu hình đó lọt vào profile production.

## 9. Kiểm tra TLS handshake

Có thể kiểm tra certificate chain và ALPN trước khi gọi RPC bằng OpenSSL:

```bash
openssl s_client \
  -connect inventory.internal.example:9090 \
  -servername inventory.internal.example \
  -alpn h2 \
  -CAfile server-ca.pem \
  -verify_return_error \
  -showcerts
```

Kết quả cần thể hiện xác minh certificate thành công và ALPN chọn `h2`. Lệnh này kiểm tra TLS handshake, không kiểm tra logic RPC hoặc authorization.

Nếu server bật reflection, kiểm tra gRPC bằng grpcurl:

```bash
grpcurl \
  -cacert server-ca.pem \
  inventory.internal.example:9090 \
  list
```

Với mTLS:

```bash
grpcurl \
  -cacert server-ca.pem \
  -cert client.crt \
  -key client.key \
  inventory.internal.example:9090 \
  list
```

Nếu reflection bị tắt, cung cấp proto file/import path và gọi method cụ thể thay cho `list`. Không đưa private key, password hoặc token thật vào command history hay log CI.

## 10. Kiểm thử tích hợp cho client TLS

Một bộ kiểm thử qua transport mạng thật nên bao gồm:

1. Server certificate do CA tin cậy cấp và SAN khớp: channel kết nối thành công.
2. Server certificate do CA không tin cậy cấp: handshake thất bại.
3. Hostname target không khớp SAN: client từ chối server.
4. Certificate hết hạn hoặc chưa có hiệu lực: xác minh thất bại.
5. Với mTLS, client certificate hợp lệ: server chấp nhận.
6. Với mTLS, không có client certificate hoặc certificate sai CA: server từ chối handshake.
7. Sau khi thay truststore/certificate, tạo kết nối mới để xác minh material mới thực sự được dùng.

In-process transport không tạo TLS handshake mạng, vì vậy test in-process chỉ phù hợp kiểm tra logic stub/service/interceptor. Muốn kiểm chứng TLS phải chạy Netty hoặc transport mạng thật với certificate test.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `UNAVAILABLE` kèm lỗi handshake | CA, chain, hostname, protocol hoặc listener TLS |
| `PKIX path building failed` | Client không xây dựng được chain tới CA tin cậy |
| `No subject alternative DNS name` | Target hostname không có trong SAN |
| Server yêu cầu client certificate | Channel chưa có keystore/client identity hoặc certificate không được trust |
| `handshake_failure` | Trust/key material, TLS protocol/cipher hoặc chính sách mTLS không khớp |
| TLS thành công nhưng RPC bị từ chối | Kiểm tra authentication metadata và authorization ở tầng RPC |
| Channel mới vẫn dùng certificate cũ | Channel/SSL context chưa được tạo lại hoặc bundle chưa được cập nhật |

Khi chẩn đoán, xem exception cause và log TLS ở môi trường kiểm thử. Không bật log chứa secret hoặc private key. Phân biệt lỗi handshake với gRPC status được trả về sau khi RPC đã tới server.

## 12. Checklist cấu hình client TLS

- [ ] Channel target dùng hostname có trong SAN của server certificate.
- [ ] `ssl.enabled` bật TLS một chiều hoặc `ssl.bundle` tham chiếu đúng bundle.
- [ ] Truststore chứa CA cần thiết và chain có đủ intermediate.
- [ ] Với mTLS, keystore chứa client certificate/private key hợp lệ.
- [ ] Server yêu cầu mTLS và trust CA cấp client certificate.
- [ ] Private key/password lấy từ secret manager hoặc secret mount.
- [ ] Không bật `bypass-certificate-validation` trong production.
- [ ] Kiểm tra TLS handshake và ALPN `h2`.
- [ ] Integration test chạy trên transport mạng thật.
- [ ] Channel được tái sử dụng và đóng theo lifecycle ứng dụng.

### Ghi nhớ

**Cấu hình TLS cho client là cấu hình trust và, khi cần, danh tính certificate của workload.** Dùng `ssl.enabled` cho TLS một chiều với trust mặc định; dùng `ssl.bundle` khi cần CA riêng hoặc mTLS với cả truststore và keystore. Đảm bảo target hostname khớp SAN, không tắt xác minh certificate trong production và kiểm tra handshake trên transport mạng thật trước khi phát hành.

## Tài liệu tham khảo

- [Spring Boot — gRPC: Client SSL Support](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring gRPC — Client and Channel Configuration](https://docs.spring.io/spring-grpc/reference/client.html)
- [gRPC — Authentication](https://grpc.io/docs/guides/auth/)
