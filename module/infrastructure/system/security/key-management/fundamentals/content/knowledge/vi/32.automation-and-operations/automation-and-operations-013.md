# Runbook certificate expiry: Phát hiện, gia hạn và xử lý chứng thư hết hạn

**Runbook certificate expiry** là quy trình vận hành để phát hiện chứng thư số sắp hết hạn, xác định phạm vi ảnh hưởng, gia hạn hoặc cấp lại chứng thư, triển khai bản mới và xác minh các hệ thống đã sử dụng chứng thư hợp lệ. Mục tiêu là tránh gián đoạn TLS, mTLS, ký số hoặc xác thực danh tính dịch vụ khi chứng thư hết hiệu lực.

Chứng thư X.509 chứa public key, danh tính, thông tin tổ chức phát hành và khoảng thời gian hiệu lực. Private key tương ứng là tài sản mật mã riêng biệt và phải được quản lý theo key policy. Gia hạn chứng thư không đồng nghĩa với gia hạn private key: quy trình có thể giữ cặp khóa hiện tại hoặc tạo cặp khóa mới tùy chính sách, mục đích, mức độ rủi ro và yêu cầu của CA.

Trong module quản lý khóa mật mã, runbook này kết nối vòng đời chứng thư với quản lý private key, keystore/truststore, PKI, KMS/HSM, automation và audit. Nó áp dụng cho chứng thư server TLS, client mTLS, chứng thư ứng dụng và các chứng thư dịch vụ có thời hạn. Quy trình cụ thể phải được điều chỉnh theo CA, nền tảng triển khai và mức độ quan trọng của dịch vụ.

## 1. Khi nào cần chạy runbook?

Kích hoạt runbook khi có một trong các điều kiện:

- Monitoring cảnh báo chứng thư sắp hết hạn trong cửa sổ đã cấu hình.
- Certificate inventory phát hiện chứng thư sắp tới ngày notAfter.
- ACME client, CA integration hoặc job gia hạn báo lỗi liên tiếp.
- Người dùng hoặc hệ thống đối tác báo lỗi TLS, mTLS hoặc xác thực chứng thư.
- Một chứng thư đã hết hạn và handshake bắt đầu thất bại.
- Thay đổi CA, intermediate certificate, thuật toán hoặc chính sách PKI yêu cầu cấp lại.
- Phát hiện private key có thể đã bị lộ; trường hợp này cần quy trình xử lý compromise song song với cấp chứng thư mới.

Runbook áp dụng cho chứng thư đang được dùng trong production và môi trường khác. Chứng thư test vẫn cần inventory và cảnh báo để tránh ảnh hưởng pipeline hoặc tạo thói quen bỏ qua cảnh báo.

## 2. Phân biệt chứng thư, public key và private key

Trước khi xử lý, cần xác định chính xác tài sản sắp hết hạn:

| Thành phần | Vai trò | Có ngày hết hạn không? |
|---|---|---|
| X.509 certificate | Gắn public key với danh tính và khoảng thời gian hiệu lực do CA ký. | Có notBefore và notAfter. |
| Public key | Dùng xác minh chữ ký hoặc tham gia trao đổi khóa theo thuật toán. | Bản thân public key không có trường hết hạn X.509. |
| Private key | Thực hiện ký hoặc thao tác riêng tư tương ứng. | Key material không tự có notAfter; thời hạn sử dụng được quản lý bởi key policy và chứng thư liên quan. |
| CA/intermediate certificate | Xác lập chuỗi tin cậy cho chứng thư được phát hành. | Có thời hạn riêng; hết hạn có thể ảnh hưởng nhiều dịch vụ. |
| Truststore | Chứa trust anchor hoặc chứng thư được tin cậy. | Không tự có hạn dùng chung; từng chứng thư trong đó có thời hạn riêng. |

Hết hạn chứng thư không tự động có nghĩa private key bị hỏng hoặc đã bị lộ. Tuy vậy, nếu private key bị compromise thì chỉ cấp chứng thư mới bằng cùng private key không giải quyết được sự cố. Khi đó cần tạo key pair mới, thu hồi chứng thư cũ theo khả năng PKI và điều tra phạm vi ảnh hưởng.

## 3. Phân loại chứng thư và mức độ ảnh hưởng

| Loại chứng thư | Vị trí thường gặp | Tác động khi hết hạn |
|---|---|---|
| Server TLS certificate | Load balancer, ingress, reverse proxy, web server, API gateway. | Client có thể từ chối kết nối HTTPS/TLS. |
| Client mTLS certificate | Workload, service mesh, API client, thiết bị. | Server có thể từ chối danh tính client. |
| Service-to-service certificate | Sidecar, mesh control plane, internal service. | Giao tiếp nội bộ có thể gián đoạn trên diện rộng. |
| Code signing certificate | CI/CD, ký artifact, ứng dụng. | Artifact mới có thể không được ký hoặc xác minh theo policy; chữ ký cũ có quy tắc đánh giá riêng. |
| Document/email signing certificate | Hệ thống ký tài liệu hoặc email. | Không thể tạo chữ ký mới hợp lệ theo chính sách hiện hành. |
| Intermediate CA certificate | PKI chain, CA service, thiết bị hoặc trust bundle. | Nhiều chứng thư leaf có thể không xây dựng được chain tin cậy. |
| Root CA certificate | Trust store của hệ điều hành, JVM, thiết bị và đối tác. | Tác động rộng, cần kế hoạch chuyển trust anchor và phân phối trust bundle. |

Ưu tiên xử lý theo phạm vi và mức độ quan trọng. Chứng thư intermediate hoặc root có thể tác động nhiều dịch vụ hơn một leaf certificate đơn lẻ. Chứng thư mTLS của nền tảng điều phối hoặc service mesh cũng có thể gây gián đoạn diện rộng nếu nhiều workload cùng phụ thuộc.

## 4. Trách nhiệm và thông tin cần chuẩn bị

Trước khi thay chứng thư, xác định người chịu trách nhiệm cho từng phần:

| Vai trò | Trách nhiệm |
|---|---|
| Service owner | Xác nhận endpoint, mức độ ảnh hưởng, cửa sổ triển khai và kiểm thử nghiệp vụ. |
| PKI/Certificate operator | Làm việc với CA, tạo CSR, kiểm tra chain và quản lý trạng thái chứng thư. |
| Key custodian/KMS-HSM operator | Bảo vệ private key, tạo key pair mới hoặc cấp quyền dùng key handle. |
| Platform/Operations | Triển khai certificate/secret, reload service, kiểm tra endpoint và rollback. |
| Security/Incident responder | Đánh giá compromise, phê duyệt ngoại lệ và quyết định revoke khi cần. |

Thu thập các thông tin sau từ inventory và hệ thống quản lý cấu hình:

- Certificate ID, serial number, SHA-256 fingerprint và đường dẫn/alias.
- Subject, Subject Alternative Name (SAN), issuer, chain và loại chứng thư.
- notBefore, notAfter, ngày cảnh báo và CA profile.
- Service owner, môi trường, endpoint, port, SNI và vùng triển khai.
- Nơi lưu private key: HSM/KMS handle, PKCS#12, JKS hoặc keystore khác.
- Nơi lưu certificate và trust chain: secret manager, file mount, ingress, truststore hoặc service mesh.
- Cách reload/restart và quy trình rollback đã kiểm thử.
- Dependency: client, upstream, partner, truststore JVM, agent hoặc thiết bị cần tin CA.

Không yêu cầu người vận hành gửi private key qua ticket hoặc chat. Runbook chỉ cần key ID/alias, fingerprint và vị trí được kiểm soát.

## 5. Cửa sổ cảnh báo và mức độ ưu tiên

Nên thiết lập nhiều mốc cảnh báo để có thời gian xử lý và xử lý lỗi cấp phát. Các con số sau là ví dụ khởi điểm, cần điều chỉnh theo loại chứng thư, SLA của CA, quy trình phê duyệt và tần suất triển khai:

| Thời điểm còn lại | Mức cảnh báo gợi ý | Hành động |
|---|---|---|
| 60 ngày | Informational | Xác nhận owner, CA, dependency và phương án gia hạn. |
| 30 ngày | Warning | Tạo yêu cầu renew/reissue, kiểm tra challenge và quyền cấp phát. |
| 14 ngày | High | Hoàn tất cấp chứng thư mới và chuẩn bị triển khai. |
| 7 ngày | Urgent | Ưu tiên triển khai, kiểm thử endpoint và theo dõi chặt. |
| 72 giờ | Critical | Escalate owner/PKI/operations, chuẩn bị cửa sổ xử lý khẩn cấp. |
| Đã hết hạn | Incident | Xử lý gián đoạn, cấp lại và khôi phục dịch vụ. |

Không nên đợi tới sát notAfter mới yêu cầu cấp chứng thư. CA có thể chậm, DNS challenge có thể lỗi, approval có thể chờ hoặc hệ thống triển khai có thể cần thời gian lan truyền. Với chứng thư tự động hóa thời hạn ngắn, hãy dùng cơ chế renew liên tục theo tỷ lệ vòng đời thay vì chỉ một cảnh báo cố định.

## 6. Bước 1: Xác minh cảnh báo và chứng thư đang được phục vụ

Khi nhận cảnh báo:

1. Lấy certificate ID/serial/fingerprint từ alert.
2. Đối chiếu inventory để xác nhận owner, môi trường, endpoint và notAfter.
3. Kiểm tra endpoint thực tế đang phục vụ chứng thư nào; không chỉ dựa vào file trên đĩa.
4. Kiểm tra SAN có chứa hostname cần phục vụ không.
5. Xác định loại chứng thư: leaf, intermediate, root, serverAuth, clientAuth hoặc signing.
6. Kiểm tra chain và truststore của client quan trọng.
7. Xác định các replica, node, region, ingress hoặc instance cần cập nhật.
8. Kiểm tra liệu cảnh báo có nhầm chứng thư cũ không còn được tham chiếu hay không.

Chứng thư trên filesystem có thể đã được thay nhưng tiến trình vẫn dùng SSLContext hoặc certificate được nạp lúc khởi động. Vì vậy, kiểm tra endpoint từ bên ngoài và từ các mạng/client quan trọng là bước bắt buộc.

### Lệnh kiểm tra chứng thư đang phục vụ

Có thể dùng OpenSSL từ máy vận hành có quyền truy cập endpoint:

~~~bash
openssl s_client -connect api.example.internal:443 \
  -servername api.example.internal -showcerts </dev/null
~~~

Lệnh hiển thị chain mà server gửi trong handshake. Để kiểm tra thông tin một certificate PEM đã lưu:

~~~bash
openssl x509 -in server.crt -noout \
  -subject -issuer -serial -dates -fingerprint -sha256 \
  -ext subjectAltName -ext extendedKeyUsage
~~~

Có thể kiểm tra certificate còn hiệu lực ít nhất 30 ngày bằng lệnh sau; giá trị 2592000 là số giây trong 30 ngày:

~~~bash
openssl x509 -in server.crt -checkend 2592000 -noout
~~~

Thay hostname và đường dẫn bằng giá trị thực. Không đưa private key vào lệnh kiểm tra hoặc lưu output chứa bí mật vào ticket. Nếu OpenSSL không có sẵn, dùng công cụ PKI/TLS được tổ chức phê duyệt.

## 7. Bước 2: Đánh giá nguyên nhân và chọn renew hay reissue

Xác định lý do phải cấp chứng thư mới:

- **Sắp hết hạn bình thường:** thực hiện renew/reissue theo CA và chính sách hiện hành.
- **Đã hết hạn:** cấp chứng thư mới; việc cấp lại có thể cần xác minh danh tính hoặc challenge lại.
- **SAN/Subject sai hoặc thay đổi hostname:** tạo CSR hoặc yêu cầu mới với SAN chính xác.
- **Thay đổi thuật toán/key size:** tạo key pair mới theo cryptographic policy.
- **Private key bị nghi ngờ lộ:** xử lý như sự cố compromise, tạo key pair mới và revoke chứng thư cũ theo quy trình.
- **CA/intermediate thay đổi hoặc sắp hết hạn:** đánh giá chain, truststore và tất cả leaf certificate phụ thuộc.
- **Certificate chain không hợp lệ:** kiểm tra intermediate, cross-sign, thứ tự chain và trust anchor trước khi kết luận leaf đã hết hạn.

Renewal có thể giữ lại key pair hiện tại hoặc tạo key pair mới tùy CA và công cụ. Reissue có thể phát hành lại chứng thư với cùng hoặc khóa mới. Hãy xác định rõ hành vi của công cụ và không mặc định rằng lệnh renew luôn tạo private key mới.

Theo key policy, ưu tiên tạo key pair mới khi có yêu cầu thay đổi khóa, khi khóa cũ bị compromise hoặc khi chính sách quy định rekey. Nếu chỉ gia hạn định kỳ, quyết định tái sử dụng hay thay khóa cần dựa trên loại khóa, cryptoperiod, khả năng triển khai và quy định của tổ chức. Private key không nên được xuất khỏi HSM/KMS chỉ để phục vụ việc gia hạn chứng thư.

## 8. Bước 3: Tạo hoặc chọn private key và CSR

Nếu cần key pair mới:

1. Chọn thuật toán và tham số theo cryptographic policy.
2. Sinh private key trong HSM/KMS hoặc nơi bảo vệ được phê duyệt.
3. Giữ private key trong ranh giới bảo vệ; chỉ xuất public key hoặc CSR cần thiết.
4. Tạo CSR với Subject và SAN phù hợp.
5. Đặt KeyUsage/EKU đúng mục đích, ví dụ serverAuth hoặc clientAuth.
6. Xác minh owner và domain/service identity trước khi gửi CA.
7. Ghi lại key ID, public key fingerprint và CSR/request ID.

CSR chứa public key và thông tin yêu cầu cấp chứng thư, không chứa private key. CA phải xác minh quyền sở hữu domain hoặc danh tính theo chính sách trước khi phát hành.

Nếu tái sử dụng private key hiện tại, kiểm tra key ID/alias và quyền sử dụng; không copy key material sang máy khác nếu không có quy trình được phê duyệt. Nếu private key nằm trong HSM, có thể cần tạo CSR bằng provider hoặc công cụ hỗ trợ thao tác với key handle.

## 9. Bước 4: Yêu cầu CA cấp chứng thư mới

Tùy môi trường, có thể dùng CA nội bộ, public CA, ACME hoặc hệ thống PKI doanh nghiệp. Trước khi gửi yêu cầu:

- Kiểm tra CA profile, thời hạn được cấp và thuật toán chấp nhận.
- Kiểm tra SAN đầy đủ, không dựa vào Common Name để thay thế SAN.
- Kiểm tra KeyUsage/EKU đúng vai trò server/client/code signing.
- Xác nhận CAA record nếu public CA và domain có áp dụng.
- Với ACME, xác nhận HTTP-01, DNS-01 hoặc TLS-ALPN-01 challenge hoạt động.
- Đảm bảo DNS, ingress, firewall hoặc quyền cập nhật DNS không bị thay đổi ngoài dự kiến.
- Lưu request ID, CA order ID và trạng thái challenge trong ticket/automation log.

Không dùng cùng một chứng thư cho nhiều dịch vụ hoặc hostname không liên quan chỉ để giảm số lượng certificate nếu điều đó làm tăng phạm vi ảnh hưởng. Wildcard certificate cũng cần được đánh giá về blast radius và quyền sử dụng private key.

Khi CA phát hành, tải certificate và intermediate chain từ kênh tin cậy. Xác minh fingerprint, serial, issuer và public key trong certificate khớp với key pair/CSR đã yêu cầu.

## 10. Bước 5: Kiểm tra chứng thư mới trước khi triển khai

Trước khi đưa certificate vào production, kiểm tra các trường:

| Thuộc tính | Điều cần xác minh |
|---|---|
| Subject / SAN | Đúng hostname, service identity hoặc danh tính client. |
| Issuer | Được cấp bởi CA dự kiến và đúng profile. |
| Serial / fingerprint | Khớp hồ sơ cấp phát và không nhầm bản cũ. |
| notBefore / notAfter | Đã bắt đầu hiệu lực và có thời gian còn lại đủ dài. |
| Public key | Khớp với private key/handle được dự định sử dụng. |
| KeyUsage / EKU | Đúng mục đích serverAuth, clientAuth, digitalSignature hoặc yêu cầu khác. |
| Basic Constraints | Leaf không bị cấp nhầm thành CA; CA certificate có thuộc tính CA phù hợp. |
| Chain | Có intermediate cần thiết và xây dựng được tới trust anchor. |
| Signature algorithm | Phù hợp chính sách và client tương thích. |
| Revocation status | Không bị revoke theo cơ chế kiểm tra mà hệ thống sử dụng. |

Kiểm tra thời gian hệ thống và đồng bộ NTP. Đồng hồ lệch có thể khiến chứng thư bị xem là chưa có hiệu lực hoặc đã hết hạn dù thời gian trên certificate đúng.

### Kiểm tra cặp khóa

Đảm bảo public key trong certificate khớp với private key được giữ trong keystore/HSM. Có thể so sánh public key fingerprint hoặc dùng một challenge ký bằng private key rồi xác minh bằng public key trong certificate. Không cần export private key để thực hiện phép kiểm tra này.

### Kiểm tra chain

Server thường gửi leaf certificate và các intermediate cần thiết; root trust anchor thường đã có trong truststore của client và không nhất thiết phải gửi từ server. Không thay đổi chain chỉ dựa vào tên file. Hãy kiểm tra CA path, cross-sign và khả năng tương thích của client/JVM/thiết bị cũ.

## 11. Bước 6: Triển khai certificate và private key an toàn

Chọn cách triển khai phù hợp kiến trúc:

- **Kubernetes:** cập nhật Secret hoặc certificate controller; xác minh pod/ingress đã nhận phiên bản mới.
- **Load balancer/ingress:** cập nhật certificate bundle qua control plane; kiểm tra mọi listener và region.
- **Java application:** cập nhật keystore/truststore hoặc key handle, sau đó reload SSLContext hoặc restart theo quy trình.
- **Service mesh:** cập nhật workload certificate và kiểm tra sidecar/control plane đã đồng bộ.
- **VM/bare metal:** triển khai file theo quyền truy cập chặt, cập nhật symlink/version và reload service.
- **HSM/KMS:** giữ private key trong thiết bị; cập nhật certificate tham chiếu tới key ID/handle.

### Nguyên tắc triển khai

1. Lưu bản mới vào vị trí/version riêng, không ghi đè bản đang hoạt động trước khi kiểm tra.
2. Giới hạn quyền đọc private key/keystore cho đúng service identity.
3. Cập nhật certificate và chain theo một thao tác nguyên tử hoặc một phiên bản bundle nhất quán.
4. Xác minh file/secret mới đã đến tất cả node, pod, region và replica.
5. Reload hoặc restart theo cơ chế hỗ trợ của ứng dụng.
6. Kiểm tra endpoint từ bên ngoài và từ các client nội bộ quan trọng.
7. Chỉ sau khi xác minh thành công mới đánh dấu triển khai hoàn tất và lưu fingerprint mới.

Không gửi keystore password, private key hoặc nội dung Secret vào log CI/CD. Secret store và deployment agent cần quyền tối thiểu; artifact chỉ nên chứa certificate công khai hoặc tham chiếu tới secret được bảo vệ.

## 12. Bước 7: Xác minh sau triển khai

Sau khi deploy:

- Kiểm tra endpoint bằng SNI đúng hostname.
- Xác nhận server trả certificate có serial/fingerprint mới.
- Kiểm tra notAfter và SAN.
- Xác minh chain tới trust anchor trên các loại client quan trọng.
- Kiểm tra TLS handshake và protocol/cipher suite theo policy.
- Kiểm tra mTLS theo cả hai chiều nếu dịch vụ dùng client certificate.
- Kiểm tra ứng dụng Java đã nạp SSLContext mới; filesystem đổi file không đồng nghĩa JVM tự reload.
- Kiểm tra mọi replica, node, ingress, region và failover endpoint.
- Chạy smoke test nghiệp vụ qua kết nối TLS.
- Theo dõi handshake error, certificate validation error, connection failure và latency.

Ví dụ xác minh endpoint:

~~~bash
openssl s_client -connect api.example.internal:443 \
  -servername api.example.internal \
  -verify_return_error -showcerts </dev/null
~~~

Lệnh này hỗ trợ quan sát chain và lỗi xác minh theo trust store của OpenSSL trên máy chạy lệnh. Nó không chứng minh tất cả client/JVM đều tin chain đó; cần kiểm tra trên truststore và runtime thực tế của các client quan trọng.

### Kiểm tra chứng thư trong Java

Đoạn mã sau kiểm tra thời hạn của một X.509 certificate đã được nạp từ KeyStore:

~~~java
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;

public static void checkCertificateValidity(
        KeyStore keyStore,
        String alias) throws Exception {

    Certificate certificate = keyStore.getCertificate(alias);
    if (!(certificate instanceof X509Certificate x509)) {
        throw new IllegalStateException(
                "Alias không chứa X.509 certificate");
    }

    x509.checkValidity(Date.from(Instant.now()));
    System.out.println("Certificate is currently valid");
    System.out.println("Not after: " + x509.getNotAfter().toInstant());
    System.out.println("Subject: " + x509.getSubjectX500Principal());
}
~~~

Ví dụ dùng pattern matching cho instanceof, yêu cầu Java 16 trở lên. Trong ứng dụng thật, không chỉ kiểm tra thời hạn: cần kiểm tra SAN, EKU, chain, fingerprint, hostname verification và trạng thái revocation theo policy. Không in private key hoặc mật khẩu KeyStore ra console.

## 13. Rollback khi triển khai chứng thư mới thất bại

Nếu certificate mới gây lỗi:

1. Xác định lỗi nằm ở certificate, chain, private key, truststore, hostname, provider hay reload.
2. Kiểm tra bản certificate/keystore trước đó còn hiệu lực và private key tương ứng vẫn được phép dùng không.
3. Nếu bản cũ còn hợp lệ và không bị compromise, rollback tới bundle/version trước theo quy trình.
4. Reload/restart và xác minh endpoint bằng serial/fingerprint của bản cũ.
5. Ghi nhận nguyên nhân, thời điểm và các node đã rollback.
6. Sửa lỗi và thử lại trên staging hoặc canary trước khi triển khai toàn bộ.

Không rollback về chứng thư đã hết hạn, đã bị revoke hoặc dùng private key nghi ngờ bị lộ. Nếu private key cũ bị compromise, giữ chứng thư cũ hoạt động có thể kéo dài rủi ro; cần chuyển sang quy trình incident response và cấp cặp khóa mới.

Với triển khai nhiều node, dùng rollout theo đợt hoặc canary để phát hiện vấn đề trước khi thay toàn bộ. Đảm bảo mọi node cuối cùng cùng phục vụ đúng certificate version.

## 14. Xử lý khi certificate đã hết hạn và dịch vụ bị gián đoạn

Nếu handshake đang thất bại do chứng thư hết hạn:

1. Xác nhận serial/fingerprint của chứng thư endpoint đang phục vụ và thời điểm notAfter.
2. Xác định phạm vi: một hostname, một region, toàn bộ ingress hay giao tiếp mTLS nội bộ.
3. Kiểm tra thời gian hệ thống, SAN, chain và truststore để loại trừ nguyên nhân khác.
4. Cấp lại chứng thư qua CA đã phê duyệt; ưu tiên automation nếu challenge và quyền hoạt động.
5. Nếu CA hoặc ACME gặp lỗi, escalate tới PKI operator và xử lý challenge/DNS/approval; không tự tạo chứng thư tự ký cho production trừ khi quy trình khẩn cấp và client trust đã cho phép rõ ràng.
6. Triển khai certificate mới, reload service và kiểm tra handshake từ nhiều điểm.
7. Kiểm tra client cache, connection pool, session và các kết nối dài hạn nếu giao thức/ứng dụng cần tái kết nối.
8. Theo dõi error rate và thông báo cho service owner/incident channel theo quy trình.
9. Ghi timeline, nguyên nhân gốc, thời gian khôi phục và hành động phòng ngừa.

Không tắt certificate validation hoặc hostname verification để khôi phục dịch vụ. Biện pháp đó khiến client chấp nhận danh tính không được xác minh và có thể tạo lỗ hổng lớn hơn sự cố hết hạn.

## 15. Trường hợp private key bị compromise

Nếu có bằng chứng hoặc nghi ngờ hợp lý rằng private key bị lộ, đây là sự cố key compromise, không chỉ là certificate expiry:

- Ngừng dùng private key cũ cho thao tác mới nếu có thể.
- Tạo key pair mới trong KMS/HSM hoặc vùng bảo vệ được phê duyệt.
- Gửi CSR mới và yêu cầu CA cấp certificate mới.
- Revoke certificate cũ theo quy trình CA; kiểm tra CRL/OCSP hoặc cơ chế trạng thái mà client thực sự dùng.
- Cập nhật endpoint, trust relationship và mọi nơi tham chiếu tới key ID cũ.
- Điều tra log truy cập keystore/HSM/KMS, export event, heap dump, backup và artifact.
- Đánh giá chữ ký hoặc dữ liệu có thể bị giả mạo/giải mã trong thời gian private key bị lộ.
- Xử lý bản sao, backup và quyền của principal liên quan theo key policy.

Việc revoke certificate không bảo đảm mọi client ngừng tin ngay lập tức. Một số client không kiểm tra OCSP/CRL theo thời gian thực hoặc có cache trạng thái. Cần hiểu hành vi của hệ thống tiêu thụ chứng thư và có biện pháp thu hồi/deny bổ sung khi cần.

## 16. Certificate automation và ACME

Với hệ thống có nhiều endpoint, tự động hóa renew giúp giảm lỗi do con người. ACME client hoặc certificate controller có thể:

1. Theo dõi thời hạn certificate.
2. Tạo order và thực hiện challenge.
3. Tạo hoặc sử dụng key pair theo policy.
4. Nhận certificate và chain.
5. Kiểm tra SAN, thời hạn và chain.
6. Cập nhật secret/keystore.
7. Trigger reload hoặc rollout.
8. Kiểm tra endpoint sau triển khai.
9. Gửi audit event và metric.

Automation phải giám sát được cả lỗi renew và lỗi deploy. Một job có thể cấp chứng thư thành công nhưng cập nhật ingress thất bại; dashboard chỉ báo “renew success” sẽ che giấu việc endpoint vẫn dùng chứng thư cũ.

Theo dõi:

- Thời gian tới expiry của chứng thư đang được phục vụ.
- Lần renew gần nhất và lần deploy thành công gần nhất.
- Tỷ lệ ACME challenge thành công.
- CA order pending/failed và rate limit.
- Secret/certificate version đang dùng trên mỗi node.
- Reload failure và thời gian lan truyền.
- Sai lệch giữa inventory và certificate quan sát từ endpoint.

Không để account key ACME hoặc credential DNS có quyền rộng không cần thiết. Tách quyền cập nhật DNS theo zone/record nếu nền tảng hỗ trợ và bảo vệ account key như một secret quan trọng.

## 17. Monitoring và alerting

Một hệ thống giám sát certificate nên kết hợp inventory với kiểm tra endpoint thực tế:

| Tín hiệu | Ý nghĩa | Hành động |
|---|---|---|
| Certificate còn dưới ngưỡng cảnh báo | Sắp hết hạn. | Tạo ticket/renew workflow và xác nhận owner. |
| Renew job thất bại | Có thể không kịp cấp chứng thư mới. | Kiểm tra CA, challenge, DNS, quyền và quota. |
| Certificate mới được cấp nhưng endpoint vẫn trả bản cũ | Deploy/reload chưa hoàn tất. | Kiểm tra secret version, node, ingress và SSLContext. |
| Endpoint trả certificate khác inventory | Drift hoặc cấu hình sai. | Xác minh nguồn phát và cập nhật đúng bundle. |
| Chain validation thất bại | Thiếu intermediate, trust anchor hoặc thuật toán không được chấp nhận. | Kiểm tra chain và truststore trên client thực tế. |
| Certificate sắp hết hạn ở nhiều dịch vụ | Có thể là vấn đề CA/intermediate hoặc automation chung. | Đánh giá blast radius và xử lý theo thứ tự ưu tiên. |
| SAN/EKU không đúng | Certificate không phù hợp mục đích hoặc hostname. | Ngừng triển khai và yêu cầu cấp lại. |
| Private key export hoặc truy cập bất thường | Có nguy cơ compromise. | Kích hoạt incident response và xem xét rekey/revoke. |

Probe nên kiểm tra từ nhiều vùng mạng và loại client quan trọng, có SNI chính xác. Một certificate hợp lệ khi kiểm tra từ máy vận hành chưa chắc đã hợp lệ với JVM truststore, thiết bị cũ hoặc đối tác có trust bundle riêng.

## 18. Audit trail và bằng chứng hoàn tất

Mỗi lần renew/reissue/deploy cần ghi nhận:

- Certificate ID, serial, fingerprint cũ và mới.
- Key ID/alias hoặc handle của private key liên quan; không ghi key material.
- Owner, service, hostname/SAN, environment và CA.
- Request/CSR/CA order ID và approval/change reference.
- Người hoặc workload thực hiện, thời điểm và kết quả từng bước.
- Thời gian cấp, thời gian deploy, thời gian reload và thời gian xác minh.
- Các endpoint/node đã kiểm tra và certificate fingerprint quan sát được.
- Rollback hoặc ngoại lệ nếu có.
- Trạng thái revoke của certificate cũ nếu cần.

Audit log không được chứa private key, keystore password, ACME account key, DNS token hoặc credential CA. Bằng chứng hoàn tất nên chứng minh certificate mới đang được phục vụ từ endpoint và được client mục tiêu chấp nhận, không chỉ chứng minh file mới đã được ghi vào filesystem.

## 19. Checklist vận hành nhanh

**Trước khi renew**

- [ ] Xác nhận certificate ID, serial, fingerprint và notAfter.
- [ ] Xác định endpoint, owner, môi trường, dependency và mức độ ưu tiên.
- [ ] Kiểm tra certificate đang phục vụ thực tế, không chỉ file trên đĩa.
- [ ] Xác định nguyên nhân: expiry, SAN, chain, CA change hay private key compromise.
- [ ] Chọn renew/reissue và quyết định giữ hay tạo key pair mới theo key policy.

**Khi cấp chứng thư**

- [ ] Dùng CA/profile đã phê duyệt và xác minh danh tính/domain.
- [ ] CSR có SAN chính xác, KeyUsage/EKU phù hợp.
- [ ] Private key được bảo vệ trong KMS/HSM/keystore được kiểm soát.
- [ ] Certificate khớp public key, serial, issuer và chain.
- [ ] notBefore/notAfter hợp lệ và thời gian hệ thống chính xác.

**Khi triển khai**

- [ ] Lưu bundle mới theo version và có thể rollback.
- [ ] Phân phối đủ leaf và intermediate cần thiết.
- [ ] Cập nhật mọi node/region/ingress/pod/sidecar.
- [ ] Reload SSLContext hoặc restart theo cơ chế ứng dụng.
- [ ] Kiểm tra endpoint bằng SNI và xác minh hostname/chain.
- [ ] Chạy smoke test TLS/mTLS và nghiệp vụ.

**Sau khi hoàn tất**

- [ ] Inventory ghi fingerprint, serial và expiry mới.
- [ ] Monitoring quan sát đúng certificate version trên endpoint.
- [ ] Audit lưu request, approval, triển khai và kết quả.
- [ ] Certificate cũ được giữ, revoke hoặc loại bỏ theo policy.
- [ ] Có cảnh báo renew/deploy thất bại và owner nhận được thông báo.

## 20. Bảng xử lý nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| certificate has expired | Endpoint đang phục vụ leaf/intermediate hết hạn hoặc đồng hồ sai. | Kiểm tra serial, notAfter, chain và NTP. |
| hostname mismatch | SAN không chứa hostname/SNI. | Kiểm tra SAN và endpoint được client gọi. |
| unable to find valid certification path | Thiếu intermediate hoặc client truststore không tin CA. | Kiểm tra chain server gửi và truststore JVM/client. |
| bad_certificate trong mTLS | Client certificate hết hạn, sai EKU, sai chain hoặc bị từ chối theo policy. | Kiểm tra certificate client và log phía server. |
| Certificate mới đã có nhưng endpoint vẫn trả certificate cũ | Secret chưa đồng bộ hoặc tiến trình chưa reload. | Kiểm tra version trên từng node và SSLContext. |
| ACME challenge thất bại | DNS/HTTP challenge, firewall, routing hoặc quyền DNS sai. | Kiểm tra challenge record/path và CA order. |
| Certificate được cấp nhưng key mismatch | CSR dùng key pair khác với keystore đang triển khai. | So sánh public key fingerprint và key ID. |
| Một số client lỗi, số khác hoạt động | Truststore, chain hoặc thuật toán khác nhau giữa client. | Kiểm tra runtime/JVM/OS và chain từ từng nhóm client. |

## 21. Những sai lầm cần tránh

**Chỉ theo dõi file certificate.** Endpoint có thể đang phục vụ bản khác hoặc tiến trình chưa reload. Giám sát cả inventory và handshake thực tế.

**Chờ tới ngày hết hạn mới renew.** CA, DNS challenge và triển khai đều có thể thất bại. Cấp chứng thư mới đủ sớm và theo dõi nhiều mốc.

**Coi renew luôn tạo key pair mới.** Hành vi phụ thuộc công cụ và CA. Xác minh private key được giữ hay thay theo key policy.

**Tái sử dụng private key đã compromise.** Cấp certificate mới bằng cùng key không khắc phục lộ khóa. Tạo key pair mới và xử lý revoke.

**Quên intermediate certificate.** Leaf mới có thể hợp lệ nhưng client không xây dựng được chain nếu server thiếu intermediate.

**Coi root certificate như leaf.** Thay root CA cần kế hoạch phân phối trust anchor và chuyển đổi rộng hơn nhiều.

**Tắt hostname verification hoặc trust validation để chữa cháy.** Điều này làm suy yếu xác thực danh tính và mở ra nguy cơ MITM.

**Cho rằng JVM tự nạp certificate mới khi file thay đổi.** Nhiều ứng dụng chỉ nạp KeyStore/SSLContext lúc khởi động. Cần reload hoặc restart có kiểm soát.

**Không kiểm tra mọi replica.** Một node cũ có thể tiếp tục phục vụ chứng thư hết hạn sau khi rollout một phần.

**Không lưu bằng chứng endpoint.** File mới có mặt chưa chứng minh client đang nhận và tin certificate mới.

Runbook certificate expiry giúp đội vận hành xử lý chứng thư trước khi gián đoạn, bảo vệ private key trong suốt quá trình renew/reissue và chứng minh kết quả sau triển khai. Khi inventory, cảnh báo, CA automation, KMS/HSM, reload và kiểm tra endpoint được nối thành một quy trình, tổ chức có thể giảm lỗi hết hạn và phát hiện sớm những vấn đề về chain, truststore hoặc key compromise.
