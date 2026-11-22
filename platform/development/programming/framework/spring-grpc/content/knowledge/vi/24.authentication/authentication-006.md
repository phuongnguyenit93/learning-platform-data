# Rotation certificate trong Spring gRPC

Trong hệ thống **SPRING_GRPC**, certificate TLS xác thực danh tính server và, khi dùng mutual TLS (mTLS), cả client. Certificate có thời hạn, private key có thể bị lộ hoặc CA có thể được thay thế; vì vậy ứng dụng cần quy trình rotation để đổi certificate/key và trust material mà không làm gián đoạn RPC ngoài kế hoạch.

Rotation không chỉ là chép một file mới vào thư mục. Phải phối hợp thứ tự cập nhật trust, certificate phía server/client, kết nối HTTP/2 đang tồn tại và quá trình rollout. Với Spring Boot, SSL bundle giúp khai báo key/trust material tập trung; khả năng tự reload còn phụ thuộc consumer cụ thể. Bài này tập trung vào vòng đời certificate cho gRPC server/client, rotation an toàn, giới hạn hot reload và cách xác minh sau thay đổi.

## 1. Certificate, private key và trust chain

Một kết nối gRPC qua TLS thường liên quan đến các thành phần:

- **Leaf/server certificate:** xác nhận danh tính server. Subject Alternative Name (SAN) phải khớp hostname mà client kết nối.
- **Private key của server:** chứng minh server sở hữu certificate. Key phải khớp với public key trong certificate.
- **Intermediate CA:** nối certificate server tới CA gốc được client tin cậy.
- **Trust store của client:** chứa CA hoặc certificate được phép xác thực server.
- **Client certificate/private key:** chỉ cần khi server yêu cầu mTLS.
- **Trust store của server:** chứa CA được phép cấp certificate cho client mTLS.

TLS handshake kiểm tra chain, thời hạn, hostname và các thuộc tính certificate phù hợp với vai trò. Với gRPC qua HTTP/2, transport còn cần thương lượng HTTP/2 (ALPN `h2`) đúng cách.

Phân biệt hai loại thay đổi:

| Thay đổi | Thành phần phải cập nhật |
| --- | --- |
| Gia hạn leaf certificate, vẫn do cùng CA cấp | Certificate và private key mới trên endpoint; trust của client thường giữ nguyên |
| Thay private key, CA không đổi | Certificate/key mới phải khớp; client vẫn tin CA cũ |
| Chuyển sang CA mới | Trust store của peer và certificate chain của endpoint |
| Xoay client certificate trong mTLS | Client key/certificate; trust CA phía server nếu CA cấp phát thay đổi |
| Private key bị lộ | Thay key/certificate khẩn cấp, xử lý thu hồi theo chính sách PKI và loại bỏ trust/identity bị xâm phạm |

Không nhầm certificate rotation với token rotation. Certificate xác thực danh tính ở tầng TLS handshake; token hoặc credential trong metadata có thể được kiểm tra theo từng RPC.

## 2. Khai báo SSL bundle cho gRPC server

Spring Boot cung cấp SSL bundle để gom keystore, truststore và thông tin TLS dưới một tên. Spring gRPC cho phép server Netty sử dụng bundle thông qua `spring.grpc.server.ssl.bundle`.

Ví dụ PEM cho server TLS một chiều:

```yaml
spring:
  ssl:
    bundle:
      pem:
        grpc-server:
          keystore:
            certificate: "file:/run/secrets/grpc/server-chain.pem"
            private-key: "file:/run/secrets/grpc/server.key"

  grpc:
    server:
      ssl:
        bundle: grpc-server
```

`server-chain.pem` thường chứa leaf certificate và intermediate chain theo định dạng mà server cần. File private key phải khớp với certificate. Thư mục secret cần được mount với quyền đọc tối thiểu cho process.

Với mTLS, thêm trust material cho certificate client và yêu cầu client authentication:

```yaml
spring:
  ssl:
    bundle:
      pem:
        grpc-server:
          keystore:
            certificate: "file:/run/secrets/grpc/server-chain.pem"
            private-key: "file:/run/secrets/grpc/server.key"
          truststore:
            certificate: "file:/run/secrets/grpc/client-ca-bundle.pem"

  grpc:
    server:
      ssl:
        bundle: grpc-server
        client-auth: require
```

`client-auth: require` buộc client trình certificate được server xác minh theo trust material. Nếu chỉ dùng TLS một chiều, không cần cấu hình client-auth bắt buộc. Tên bundle trong `spring.grpc.server.ssl.bundle` phải trùng với tên dưới `spring.ssl.bundle`.

Ví dụ cấu hình và các property hỗ trợ phụ thuộc phiên bản Spring Boot, Spring gRPC và server transport. Kiểm tra reference của đúng phiên bản trước khi triển khai.

## 3. Rotation leaf certificate khi CA không đổi

Đây là trường hợp đơn giản nhất: CA cấp một leaf certificate mới cho cùng danh tính server, có thể đồng thời thay private key.

Quy trình:

1. Tạo key pair mới trong hệ thống quản lý key an toàn.
2. Yêu cầu CA cấp certificate mới với SAN, EKU và chain đúng.
3. Kiểm tra certificate mới, private key và chain trước khi đưa vào runtime.
4. Cập nhật secret hoặc file mount mà server sẽ đọc.
5. Thực hiện reload/recreate server hoặc rolling restart theo khả năng của transport.
6. Tạo kết nối TLS mới và xác minh client nhận certificate mới.
7. Theo dõi handshake, lỗi xác thực và trạng thái RPC trước khi xóa material cũ.

Nếu CA không đổi và client vẫn tin CA đó, thường không cần phát hành lại trust bundle cho client. Tuy vậy, client phải kiểm tra hostname và chain của certificate mới; certificate hết hạn, SAN sai hoặc thiếu intermediate vẫn làm handshake thất bại.

Không ghi đè đồng thời certificate và private key theo cách khiến process có thể đọc một nửa cặp cũ, một nửa cặp mới. Hãy tạo bộ file hoàn chỉnh trong thư mục staging rồi publish theo thao tác atomic phù hợp với hệ điều hành hoặc secret manager.

## 4. Rotation CA với giai đoạn trust overlap

Thay CA phức tạp hơn vì server và client phải chuyển trust mà không tạo khoảng thời gian hai phía không tin nhau. Cách an toàn là triển khai trust overlap: trong một khoảng chuyển tiếp, peer tin cả CA cũ và CA mới.

Ví dụ client trust bundle tạm thời chứa:

```text
-----BEGIN CERTIFICATE-----
... CA cũ ...
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
... CA mới ...
-----END CERTIFICATE-----
```

Thứ tự triển khai khuyến nghị:

1. **Mở rộng trust trước:** cập nhật client để tin cả CA cũ và CA mới. Với mTLS, cập nhật server trust bundle để chấp nhận certificate client do cả hai CA cấp.
2. **Xác nhận trust mới đã lan rộng:** kiểm tra tất cả replica, worker, batch job và client ngoài cụm đã nhận bundle mới.
3. **Chuyển server certificate:** cấp certificate server từ CA mới và rollout server.
4. **Chuyển client certificate nếu dùng mTLS:** cấp và triển khai certificate client mới trong khi server vẫn chấp nhận CA cũ và mới.
5. **Quan sát giai đoạn overlap:** xác nhận handshake thành công trên kết nối mới và không còn peer cần certificate cũ.
6. **Thu hẹp trust:** chỉ sau khi toàn bộ endpoint đã chuyển, gỡ CA cũ khỏi trust bundle và rollout lại các thành phần liên quan.

Không xóa CA cũ ngay sau khi thay certificate server. Client cũ có thể vẫn cần CA cũ, hoặc một service mTLS khác chưa được cập nhật. Lưu lại thời điểm hết hạn certificate cũ và thời gian overlap đã thống nhất.

## 5. Rotation certificate client trong mTLS

Với mTLS, server xác minh client certificate trong TLS handshake. Khi xoay certificate client:

- Phát hành client certificate mới với EKU `clientAuth`, SAN/identity theo quy tắc của tổ chức và thời hạn phù hợp.
- Nếu CA không đổi, server trust có thể giữ nguyên.
- Nếu CA đổi, server phải tin CA mới trước khi client chuyển sang certificate mới.
- Cập nhật secret phía client và tạo lại kết nối/channel theo cơ chế của ứng dụng.
- Kiểm tra server nhận đúng identity mới và authorization vẫn ánh xạ identity đó vào principal/role mong muốn.

Certificate xác thực client ở tầng transport. Authorization theo user, tenant hoặc quyền gọi method vẫn có thể cần metadata/token và Spring Security. Một certificate hợp lệ không tự động cấp mọi quyền nghiệp vụ.

## 6. Spring Boot reload SSL bundle và giới hạn với gRPC

Spring Boot hỗ trợ PEM SSL bundle với `reload-on-update`. Khi file key material được theo dõi thay đổi, bundle có thể được nạp lại và phát sự kiện cập nhật. Ví dụ:

```yaml
spring:
  ssl:
    bundle:
      pem:
        web-tls:
          reload-on-update: true
          keystore:
            certificate: "file:/run/secrets/web/fullchain.pem"
            private-key: "file:/run/secrets/web/privkey.pem"
```

File watcher có thể dùng quiet period để đợi các file được cập nhật hoàn tất trước khi reload. Tính năng này không tự cấp hoặc gia hạn certificate; công cụ bên ngoài như Certbot, cert-manager hoặc hệ thống PKI phải thực hiện việc đó.

**Điểm quan trọng với Spring gRPC:** tài liệu Spring Boot hiện mô tả reloadable SSL bundle cho các consumer tương thích như Tomcat và Netty web server. Tài liệu gRPC xác nhận native `grpc-netty` và `grpc-netty-shaded` có thể dùng SSL bundle, nhưng không khẳng định native gRPC server tự thay certificate đang phục vụ ngay khi bundle reload. Không suy ra khả năng hot reload của web server Netty đồng nghĩa với gRPC Netty server cũng hot reload.

Vì vậy, với native gRPC server:

- Kiểm tra đúng phiên bản starter/transport và xác minh có cơ chế cập nhật server TLS context được hỗ trợ hay không.
- Nếu không có bảo đảm rõ ràng, dùng rolling restart hoặc tạo server mới với bundle mới rồi chuyển traffic.
- Không chỉ thay file và coi rotation đã hoàn tất; phải kiểm tra certificate trên một kết nối TLS mới.
- Nếu cần hot reload không restart, cân nhắc terminate TLS tại proxy/load balancer có cơ chế reload đã được xác nhận, hoặc triển khai custom server lifecycle có kiểm thử đầy đủ.

Nếu gRPC chạy qua servlet container, TLS thường do web server quản lý. Khi đó khả năng reload phụ thuộc container và cách Spring Boot tích hợp SSL bundle; vẫn cần kiểm chứng thực tế.

## 7. Kết nối HTTP/2 đang tồn tại và thời điểm certificate mới có hiệu lực

gRPC thường duy trì channel HTTP/2 lâu dài và multiplex nhiều RPC trên một kết nối TCP/TLS. Certificate được xác minh trong TLS handshake khi kết nối được thiết lập. Thay certificate trên server không làm handshake lại cho mọi RPC đang chạy trên kết nối cũ.

Điều này dẫn tới ba hệ quả:

- RPC trên kết nối hiện tại có thể tiếp tục chạy dù server đã nạp certificate mới.
- Client chỉ nhìn thấy certificate mới khi thiết lập kết nối TLS mới.
- Client channel được tạo từ SSL context cũ có thể vẫn dùng trust/key material cũ cho những kết nối mới mà channel đó tạo ra, tùy cách channel và transport được xây dựng.

Để xác minh rotation, tạo channel mới hoặc buộc một kết nối mới tới endpoint. Với rollout server, drain kết nối cũ theo chính sách graceful shutdown và deadline của RPC. Không kết luận rotation thành công chỉ vì một RPC trên channel cũ vẫn trả kết quả.

## 8. Rolling rotation không gián đoạn

Với nhiều replica sau load balancer, có thể thay certificate theo từng đợt:

1. Mở rộng trust ở client và server mTLS để chấp nhận CA cũ/mới.
2. Cập nhật secret cho một replica.
3. Khởi động/recreate replica bằng certificate mới.
4. Chờ readiness và thực hiện một TLS handshake mới tới replica đó.
5. Đưa replica vào phục vụ; tiếp tục với replica kế tiếp.
6. Sau khi mọi replica đã đổi, drain và loại bỏ kết nối cũ.
7. Gỡ CA/certificate cũ sau thời gian overlap và xác minh không còn consumer.

Đặt readiness chỉ thành công khi server đã bind, service cần thiết đã đăng ký và các dependency thiết yếu sẵn sàng. Graceful shutdown phải đủ thời gian cho RPC đang chạy hoàn tất; client vẫn phải đặt deadline hữu hạn.

Nếu chỉ có một replica, cần dùng một server song song hoặc chấp nhận một khoảng gián đoạn có kế hoạch. Rotation key bị lộ là tình huống khẩn cấp: ưu tiên vô hiệu hóa identity bị xâm phạm theo quy trình PKI và chấp nhận rollout khẩn cấp thay vì kéo dài overlap thiếu an toàn.

## 9. Kiểm tra certificate trước và sau rotation

Trước khi publish, kiểm tra subject, issuer, thời hạn và SAN:

```bash
openssl x509 -in server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
```

Xác minh chain với CA dự kiến:

```bash
openssl verify -CAfile ca-bundle.pem server.crt
```

Xác nhận certificate và private key khớp nhau bằng cách so sánh public key được trích xuất từ mỗi file. Dùng công cụ phù hợp với loại key; không in private key ra log hoặc terminal chia sẻ.

Sau rollout, mở kết nối mới và kiểm tra TLS/HTTP2:

```bash
openssl s_client \
  -connect grpc.example.com:9090 \
  -servername grpc.example.com \
  -alpn h2 \
  -CAfile ca-bundle.pem \
  -verify_return_error \
  -showcerts
```

Nếu server bật reflection, có thể kiểm tra bằng grpcurl:

```bash
grpcurl -cacert ca-bundle.pem grpc.example.com:9090 list
```

Với mTLS:

```bash
grpcurl -cacert server-ca.pem \
  -cert client.crt \
  -key client.key \
  grpc.example.com:9090 list
```

Nếu reflection bị tắt, gọi method bằng proto file/import path phù hợp thay vì `list`. Không dùng tùy chọn bỏ qua certificate validation trong kiểm tra production; nó che khuất lỗi trust và hostname.

## 10. Kiểm thử rotation trong môi trường test

Một integration test nên chứng minh cả đường thành công và thất bại:

- Server certificate hợp lệ và hostname khớp: TLS handshake thành công.
- Client trust CA sai: handshake thất bại.
- Certificate hết hạn hoặc chưa tới thời điểm `notBefore`: xác minh thất bại theo chính sách.
- mTLS không có client certificate khi server yêu cầu: kết nối bị từ chối.
- Client certificate do CA không tin cậy cấp: handshake thất bại.
- Sau khi thay server certificate và tạo channel mới: client xác minh certificate mới.
- Trong CA overlap: client trust cả CA cũ và mới; sau khi gỡ CA cũ, certificate cũ phải không còn được chấp nhận.

Dùng certificate test riêng, có thời hạn ngắn và private key không tái sử dụng trong production. Đồng bộ clock của môi trường test để tránh lỗi giả do sai lệch thời gian.

Một test chạy trên in-process transport không kiểm tra TLS vì không có TLS handshake mạng. Phải dùng Netty/transport thật hoặc môi trường integration có listener TLS.

## 11. Theo dõi rotation và xử lý sự cố

Theo dõi các tín hiệu sau trong suốt đợt rotation:

| Tín hiệu | Điều cần phát hiện |
| --- | --- |
| Ngày hết hạn certificate | Certificate sắp hết hạn hoặc job renew không chạy |
| TLS handshake failure | Chain sai, hostname sai, CA chưa được phân phối hoặc key/cert không khớp |
| Lỗi xác thực mTLS | Client certificate thiếu, hết hạn hoặc CA chưa được trust |
| gRPC `UNAVAILABLE` | Kết nối bị đóng, server chưa sẵn sàng hoặc proxy/network có vấn đề |
| gRPC `UNAUTHENTICATED` | Danh tính/credential bị từ chối; cần xem cả TLS và authentication layer |
| Replica readiness | Replica mới chưa bind listener hoặc service chưa sẵn sàng |
| Tỷ lệ kết nối mới thành công | Xác nhận client thực sự bắt tay với certificate mới |

Log issuer, serial number, fingerprint và thời hạn certificate ở mức vận hành nếu chính sách cho phép; tuyệt đối không log private key, keystore password hoặc nội dung secret. Lưu audit trail cho người phát hành, thời điểm deploy và lần loại bỏ CA cũ.

## 12. Checklist rotation thực tế

- [ ] Xác định certificate nào đang được xoay: server, client hay CA.
- [ ] Kiểm tra SAN, EKU, chain, thời hạn và cặp private key.
- [ ] Xác nhận nơi lưu key và quyền đọc của process.
- [ ] Phân phối trust mới trước khi chuyển certificate nếu CA thay đổi.
- [ ] Kiểm tra khả năng reload thực tế của đúng gRPC transport.
- [ ] Nếu không có hot reload được hỗ trợ, chuẩn bị rolling restart/server replacement.
- [ ] Tạo kết nối TLS mới để xác minh certificate mới.
- [ ] Drain kết nối HTTP/2 cũ và theo dõi RPC đang chạy.
- [ ] Giữ overlap đủ lâu cho mọi client/replica cập nhật.
- [ ] Chỉ gỡ CA cũ sau khi xác nhận không còn consumer.
- [ ] Theo dõi handshake failures và cảnh báo expiry sau rollout.

### Ghi nhớ

**Rotation certificate là một quy trình chuyển đổi danh tính và trust có kiểm soát.** Gia hạn leaf certificate cùng CA thường chỉ cần cập nhật endpoint; thay CA cần trust overlap trước khi đổi certificate. Spring SSL bundle giúp quản lý key/trust material, nhưng không có nghĩa mọi gRPC server tự hot reload. Với native gRPC Netty, hãy xác minh khả năng của đúng phiên bản hoặc dùng rolling restart/server replacement; sau đó tạo kết nối mới, kiểm tra chain/hostname/mTLS và chỉ loại bỏ trust cũ khi toàn bộ peer đã chuyển.

## Tài liệu tham khảo

- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot — gRPC and SSL support](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring gRPC — Server](https://docs.spring.io/spring-grpc/reference/server.html)
- [OpenSSL — x509](https://docs.openssl.org/3.5/man1/openssl-x509/)
- [OpenSSL — s_client](https://docs.openssl.org/3.5/man1/openssl-s_client/)
