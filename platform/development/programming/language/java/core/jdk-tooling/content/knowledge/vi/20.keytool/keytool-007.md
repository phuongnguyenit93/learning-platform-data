# Xem certificate bằng keytool

## 1. Mục tiêu

`keytool` là tiện ích quản lý keystore và certificate đi kèm JDK. Khi cần xem một certificate X.509, có thể dùng `keytool -printcert` để đọc thông tin từ file, certificate chain do máy chủ TLS gửi, hoặc signer certificate gắn với một JAR đã ký.

Việc xem certificate thường giúp trả lời các câu hỏi:

- Certificate được cấp cho chủ thể nào và do CA nào phát hành?
- Certificate còn hạn hay đã hết hạn?
- DNS name hoặc IP address của máy chủ có nằm trong Subject Alternative Name (SAN) không?
- Certificate dùng thuật toán chữ ký và public key nào?
- SHA-256 fingerprint có khớp giá trị được cung cấp qua kênh tin cậy không?
- Certificate là CA certificate hay certificate của server/client?
- Keystore có alias nào và alias đó chứa loại entry nào?
- Certificate chain gồm những certificate nào?

`keytool` hiển thị dữ liệu certificate để người quản trị kiểm tra. Việc nhìn thấy certificate không tự động chứng minh certificate đáng tin cậy, đúng hostname hoặc được phép dùng cho một mục đích cụ thể. Những bước xác minh đó cần được thực hiện riêng.

## 2. Certificate X.509 chứa những gì?

Certificate X.509 liên kết danh tính của một subject với public key. CA hoặc chủ thể tự ký tạo chữ ký trên nội dung certificate để bên nhận có thể kiểm tra tính toàn vẹn và nguồn phát hành.

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| Version | Phiên bản cấu trúc X.509; phần lớn certificate hiện đại là v3 |
| Subject / Owner | Danh tính được certificate đại diện |
| Issuer | CA hoặc chủ thể đã ký certificate |
| Serial number | Số định danh certificate do issuer cấp |
| Valid from / until | Thời điểm bắt đầu và kết thúc hiệu lực |
| Signature algorithm | Thuật toán dùng để ký certificate |
| Subject public key algorithm | Thuật toán và kích thước public key |
| SHA-256 fingerprint | Hash của toàn bộ certificate, dùng để nhận diện chính xác certificate |
| Subject Alternative Name | DNS name, IP address hoặc danh tính bổ sung |
| Basic Constraints | Cho biết certificate có được phép làm CA không |
| Key Usage | Các hoạt động mật mã được phép |
| Extended Key Usage | Mục đích sử dụng như serverAuth, clientAuth hoặc codeSigning |

Trong output `keytool`, trường `Owner` tương ứng với Subject. Đừng nhầm Subject với Issuer: Subject là đối tượng được chứng nhận, Issuer là bên ký certificate.

## 3. Cách đọc output của keytool

Một certificate X.509 v3 thường được `keytool -printcert -v` hiển thị theo dạng:

```text
Owner: CN=localhost, O=Example, C=VN
Issuer: CN=Example Test Root CA, O=Example, C=VN
Serial number: 825f5ab58daf3e50
Valid from: Tue Nov 10 23:40:12 GMT+07:00 2026 until: Wed Nov 10 23:40:12 GMT+07:00 2027
Certificate fingerprints:
         SHA1: ...
         SHA256: ...
Signature algorithm name: SHA384withRSA
Subject Public Key Algorithm: 2048-bit RSA key
Version: 3

Extensions:
  BasicConstraints:
    CA:false
  ExtendedKeyUsages:
    serverAuth
  KeyUsage:
    DigitalSignature
    Key_Encipherment
  SubjectAlternativeName:
    DNSName: localhost
    IPAddress: 127.0.0.1
```

Cách diễn giải:

- `Owner` là certificate của `localhost`.
- `Issuer` cho biết certificate được CA `Example Test Root CA` ký.
- `Valid from` là khoảng thời gian certificate có hiệu lực.
- `SHA256` là fingerprint nên dùng để đối chiếu certificate.
- `Signature algorithm name` mô tả thuật toán ký certificate.
- `Subject Public Key Algorithm` cho biết loại và kích thước public key.
- `CA:false` cho biết certificate này không được phát hành như CA certificate.
- `serverAuth` cho biết mục đích TLS server authentication.
- SAN chứa cả DNS name và IP address được certificate đại diện.

Giá trị cụ thể sẽ khác theo certificate. Luôn đọc output thực tế thay vì giả định mọi certificate có cùng extension hoặc cùng thuật toán.

## 4. Xem certificate từ file PEM hoặc DER

Đây là cách trực tiếp nhất khi bạn nhận certificate từ CA, hệ thống quản trị hoặc người vận hành server.

Xem certificate từ file PEM:

```bash
keytool -printcert -file server.pem
```

Xem đầy đủ extension và fingerprint:

```bash
keytool -printcert -file server.pem -v
```

Có thể yêu cầu output theo định dạng RFC/PEM:

```bash
keytool -printcert -file server.pem -rfc
```

`-file` chỉ định certificate đầu vào. `-v` hiển thị chi tiết hơn. `-rfc` xuất biểu diễn certificate theo định dạng Base64 PEM.

PEM thường có phần bao:

```text
-----BEGIN CERTIFICATE-----
MIID...
-----END CERTIFICATE-----
```

DER là định dạng nhị phân. Cùng một certificate có thể được lưu dưới dạng DER hoặc PEM. `keytool -printcert -file` có thể đọc cả hai định dạng.

## 5. Phân biệt PEM và DER

| Định dạng | Đặc điểm | Dấu hiệu thường gặp |
|---|---|---|
| DER | Dữ liệu nhị phân ASN.1 | File .der hoặc .cer |
| PEM | DER được Base64 và bọc bởi header/footer | -----BEGIN CERTIFICATE----- |
| PKCS#12 | Container có thể chứa private key, certificate và chain | .p12, .pfx |
| JKS | Java KeyStore format | .jks |

Xuất certificate ở dạng DER:

```bash
keytool -exportcert -alias server -keystore server.p12 -storetype PKCS12 -file server.der
```

Xuất ở dạng PEM:

```bash
keytool -exportcert -alias server -keystore server.p12 -storetype PKCS12 -rfc -file server.pem
```

Sau đó xem certificate:

```bash
keytool -printcert -file server.der -v
keytool -printcert -file server.pem -v
```

`-exportcert` chỉ xuất certificate công khai, không xuất private key. File `.p12` hoặc `.jks` có thể chứa private key nên phải bảo vệ như bí mật. Không gửi keystore chứa private key chỉ để chia sẻ certificate.

## 6. Xem certificate trong keystore

Một keystore có thể chứa nhiều entry. Trước tiên liệt kê alias:

```bash
keytool -list -keystore server.p12 -storetype PKCS12
```

Xem toàn bộ thông tin entry:

```bash
keytool -list -v -keystore server.p12 -storetype PKCS12
```

Chỉ xem một alias cụ thể:

```bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
```

`keytool` sẽ yêu cầu mật khẩu keystore nếu cần. Với keystore JKS, chỉ định:

```bash
keytool -list -v -keystore server.jks -storetype JKS
```

Các entry thường gặp:

| Entry type | Nội dung |
|---|---|
| PrivateKeyEntry | Private key và certificate chain tương ứng |
| trustedCertEntry | Certificate công khai được lưu làm trusted certificate |
| SecretKeyEntry | Secret key đối xứng; không phải certificate entry |

Khi output có `Certificate chain length: 2`, entry đang giữ hai certificate trong chain, thường là certificate của server và CA ký nó. Không có nghĩa keystore chứa hai private key.

## 7. Xem certificate chain

Certificate chain mô tả đường từ certificate đầu cuối tới CA trung gian và root CA.

```text
Server certificate
    Issuer: Intermediate CA
        Issuer: Root CA
```

Trong một `PrivateKeyEntry`, certificate đầu tiên thường là leaf certificate gắn với private key; các certificate tiếp theo là CA certificate trong chain.

Xem chain của alias:

```bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
```

Xem certificate được máy chủ TLS gửi:

```bash
keytool -printcert -sslserver example.com:443 -v
```

`-printcert -sslserver` kết nối tới endpoint TLS và hiển thị các certificate mà server trình bày. Nếu server gửi intermediate certificate, output có thể có nhiều mục `Certificate #0`, `Certificate #1`, v.v.

Root CA thường được client tin cậy qua truststore và không nhất thiết phải được server gửi trong TLS handshake. Vì vậy, chain nhìn thấy trên mạng có thể không chứa root certificate.

Nếu chỉ thấy leaf certificate, hãy kiểm tra cấu hình server có gửi đầy đủ intermediate certificate không. Thiếu intermediate có thể khiến một số client không xây dựng được chain tới trusted root.

## 8. Xem certificate đang được server HTTPS sử dụng

Khi cần điều tra certificate của website hoặc API:

```bash
keytool -printcert -sslserver api.example.com:443
```

Xem chi tiết:

```bash
keytool -printcert -sslserver api.example.com:443 -v
```

Có thể thay host và port theo endpoint thực tế:

```bash
keytool -printcert -sslserver localhost:8443 -v
```

Nếu lệnh không kết nối được, kiểm tra DNS, firewall, port, proxy và trạng thái TLS listener. Với server yêu cầu SNI hoặc có nhiều virtual host, hãy kiểm tra đúng hostname mà client thực tế truy cập.

Lệnh này giúp xem certificate server trình bày. Nó không thay thế việc kiểm tra hostname trong client application, chính sách truststore, revocation hoặc TLS configuration của ứng dụng.

## 9. Xem certificate ký JAR

Một JAR đã ký có thể chứa signer certificate và certificate chain trong thư mục `META-INF`.

Xem signer certificate:

```bash
keytool -printcert -jarfile app.jar
```

Xem đầy đủ thông tin:

```bash
keytool -printcert -jarfile app.jar -v
```

Lệnh này giúp biết JAR được ký bởi danh tính nào, certificate có thời hạn ra sao và chain gồm những certificate nào.

Để kiểm tra chữ ký của nội dung JAR, dùng `jarsigner`:

```bash
jarsigner -verify -verbose -certs app.jar
```

Nếu cần xác minh chain theo truststore cụ thể:

```bash
jarsigner -verify -verbose -certs -keystore truststore.p12 -storetype PKCS12 app.jar
```

`keytool -printcert -jarfile` là bước xem thông tin signer. `jarsigner -verify` mới kiểm tra chữ ký trên các entry của JAR. Kết quả còn phụ thuộc certificate chain có được tin cậy, certificate có phù hợp mục đích code signing và timestamp có hợp lệ hay không.

## 10. Xem certificate trong cacerts

JDK có truststore mặc định thường được gọi là `cacerts`. Nó chứa các CA certificate mà môi trường Java tin cậy theo bản phân phối JDK.

Liệt kê các alias:

```bash
keytool -list -cacerts
```

Xem chi tiết các trusted certificate:

```bash
keytool -list -v -cacerts
```

Xem một alias cụ thể:

```bash
keytool -list -v -cacerts -alias example-root
```

`cacerts` thường nằm dưới thư mục security của Java runtime. Dùng `-cacerts` giúp keytool truy cập truststore mặc định mà không cần tự đoán đường dẫn.

Không thêm hoặc xóa CA khỏi `cacerts` chỉ để làm cho một kết nối chạy được. Thay đổi truststore mặc định ảnh hưởng tới nhiều ứng dụng sử dụng cùng runtime. Với ứng dụng riêng, cân nhắc dùng truststore riêng.

## 11. Những trường cần kiểm tra khi xem certificate

Không phải certificate nào cũng có cùng mục đích. Khi đọc output, hãy kiểm tra các nhóm sau.

### Subject, Issuer và danh tính

`Subject` mô tả danh tính được chứng nhận. `Issuer` cho biết CA nào ký certificate. So sánh chúng để hiểu certificate là leaf, intermediate hay root.

Đối với TLS hostname, xem `SubjectAlternativeName` (SAN). DNS name hoặc IP address mà client truy cập cần khớp SAN tương ứng. Không nên dựa riêng vào Common Name (CN) để xác định hostname.

### Thời hạn

Kiểm tra `Valid from` và `Valid until`. Certificate chưa tới `notBefore` hoặc đã qua `notAfter` có thể bị client từ chối. Đồng hồ hệ thống sai cũng có thể làm certificate trông như chưa hợp lệ hoặc đã hết hạn.

### Fingerprint

Ưu tiên SHA-256 fingerprint. So sánh toàn bộ fingerprint với giá trị được tổ chức, CA hoặc quản trị viên cung cấp qua kênh độc lập đáng tin cậy. Không lấy fingerprint từ chính kết nối đang nghi ngờ rồi coi đó là xác nhận danh tính.

SHA-1 vẫn có thể xuất hiện trong output để tương thích hoặc nhận diện cũ, nhưng không nên dùng nó làm lựa chọn xác minh mới.

### Public key và chữ ký

Kiểm tra thuật toán public key, kích thước key và signature algorithm. Cảnh giác với thuật toán yếu, key quá ngắn hoặc chữ ký không còn được chính sách bảo mật cho phép.

### Extensions

- `BasicConstraints: CA:true` cho biết certificate có thể đóng vai trò CA theo extension.
- `KeyUsage` giới hạn hoạt động mật mã như ký số hoặc mã hóa key.
- `ExtendedKeyUsage` giới hạn mục đích như `serverAuth`, `clientAuth` hoặc `codeSigning`.
- `SubjectAlternativeName` chứa DNS/IP hoặc danh tính khác.
- `SubjectKeyIdentifier` và `AuthorityKeyIdentifier` hỗ trợ liên kết chain.

Không kết luận certificate hợp lệ chỉ từ một trường riêng lẻ. Cần xét cả chain, thời hạn, hostname, mục đích sử dụng và chính sách trust.

## 12. Fingerprint: cách đối chiếu certificate

Fingerprint là hash của toàn bộ certificate, không phải hash riêng public key. Nếu certificate được phát hành lại với serial, thời hạn hoặc extension khác, fingerprint sẽ thay đổi dù Subject giống nhau.

Xem SHA-256:

```bash
keytool -printcert -file server.pem -v
```

Trong output, tìm mục:

```text
Certificate fingerprints:
    SHA256: ...
```

Đối chiếu fingerprint với nguồn tin cậy độc lập, ví dụ:

- Thông báo chính thức từ quản trị viên PKI.
- Kênh quản trị bảo mật của tổ chức.
- Tài liệu triển khai đã được xác thực.
- Giá trị pinning được phát hành qua quy trình kiểm soát.

Không chấp nhận certificate chỉ vì Subject có tên giống tổ chức mong đợi. Một kẻ khác có thể tạo certificate tự ký với cùng Subject.

## 13. Xem certificate khác với xác minh trust

Đây là điểm rất quan trọng:

- `keytool -printcert` đọc và hiển thị nội dung certificate.
- `keytool -list` cho biết entry và certificate đang lưu trong keystore.
- `keytool -printcert -sslserver` hiển thị certificate server trình bày.
- `jarsigner -verify` kiểm tra chữ ký của JAR.
- Trust validation xác định chain có kết thúc tại CA được tin cậy và đáp ứng chính sách hay không.

Một certificate có thể:

- Có chữ ký đúng nhưng issuer không được tin cậy.
- Còn hạn nhưng SAN không khớp hostname.
- Có chain nhưng thiếu intermediate certificate.
- Là certificate CA nhưng không phù hợp mục đích server authentication.
- Có fingerprint đúng nhưng đã bị thu hồi.
- Có thể đọc được bằng keytool nhưng không được ứng dụng chấp nhận.

Với TLS, cần kiểm tra chain tới trust anchor, hostname, thời hạn, key usage/EKU, revocation policy và cấu hình TLS của client. Với JAR signing, cần kiểm tra signature, signer chain, code-signing purpose và timestamp theo chính sách phát hành.

Không dùng `keytool -printcert` như bằng chứng duy nhất rằng một kết nối hoặc artifact an toàn.

## 14. Import trusted certificate sau khi đã kiểm tra

Khi tổ chức cung cấp root CA hoặc certificate cần trust, trước hết xem file và xác nhận SHA-256 fingerprint qua kênh độc lập:

```bash
keytool -printcert -file organization-root.pem -v
```

Sau khi đã xác nhận đúng certificate, import vào truststore riêng:

```bash
keytool -importcert -alias organization-root -file organization-root.pem -keystore app-truststore.p12 -storetype PKCS12
```

Keytool sẽ yêu cầu xác nhận trust và mật khẩu truststore. Chỉ đồng ý sau khi fingerprint khớp giá trị đã xác thực.

Kiểm tra entry sau import:

```bash
keytool -list -v -alias organization-root -keystore app-truststore.p12 -storetype PKCS12
```

Certificate được import dưới dạng `trustedCertEntry`. Nó không chứa private key. Truststore riêng giúp giới hạn phạm vi tin cậy cho ứng dụng thay vì thay đổi `cacerts` của toàn bộ JDK.

Không import leaf certificate hoặc root certificate lạ chỉ để bỏ qua lỗi TLS. Hãy xác định vì sao chain không được tin cậy trước khi thay đổi trust configuration.

## 15. Ví dụ thực hành: tạo CA thử nghiệm và xem chain

Ví dụ này tạo một root CA dùng riêng cho lab, một server key pair, CSR và certificate do CA thử nghiệm ký. Chỉ dùng dữ liệu giả trong môi trường local; không dùng root CA này cho production.

Tạo root CA:

```bash
keytool -genkeypair -alias root-ca -keyalg RSA -keysize 3072 -validity 3650 -dname "CN=Example Test Root CA, O=Example, C=VN" -ext bc=ca:true -ext ku=keyCertSign,cRLSign -keystore root-ca.p12 -storetype PKCS12
```

Xuất root certificate ở định dạng PEM:

```bash
keytool -exportcert -alias root-ca -keystore root-ca.p12 -storetype PKCS12 -rfc -file root-ca.pem
```

Tạo key pair cho server. SAN khai báo hostname và IP mà server sẽ sử dụng:

```bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -validity 365 -dname "CN=localhost, O=Example, C=VN" -ext bc=ca:false -ext ku=digitalSignature,keyEncipherment -ext eku=serverAuth -ext san=dns:localhost,ip:127.0.0.1 -keystore server.p12 -storetype PKCS12
```

Tạo certificate signing request (CSR):

```bash
keytool -certreq -alias server -keystore server.p12 -storetype PKCS12 -file server.csr -ext san=dns:localhost,ip:127.0.0.1
```

CA ký CSR và tạo server certificate:

```bash
keytool -gencert -alias root-ca -keystore root-ca.p12 -storetype PKCS12 -infile server.csr -outfile server-signed.pem -rfc -validity 365 -ext bc=ca:false -ext ku=digitalSignature,keyEncipherment -ext eku=serverAuth -ext san=dns:localhost,ip:127.0.0.1
```

Import root CA vào keystore server trước, sau đó cài certificate reply vào đúng alias:

```bash
keytool -importcert -alias root-ca -file root-ca.pem -keystore server.p12 -storetype PKCS12
keytool -importcert -alias server -file server-signed.pem -keystore server.p12 -storetype PKCS12
```

Xem certificate leaf:

```bash
keytool -printcert -file server-signed.pem -v
```

Xem alias và chain:

```bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
```

Kết quả quan trọng cần nhận ra:

- Subject là `localhost`.
- Issuer là `Example Test Root CA`.
- SAN chứa `DNSName: localhost` và `IPAddress: 127.0.0.1`.
- Leaf certificate có `CA:false`.
- Extended Key Usage có `serverAuth`.
- Keystore có `PrivateKeyEntry`.
- Certificate chain length là `2`: server certificate và root CA.

Xuất certificate ở DER rồi xem lại:

```bash
keytool -exportcert -alias server -keystore server.p12 -storetype PKCS12 -file server-signed.der
keytool -printcert -file server-signed.der -v
```

SHA-256 fingerprint của certificate PEM và DER phải giống nhau vì chúng là hai cách mã hóa cùng certificate.

## 16. Ví dụ xem certificate từ TLS server

Khi có TLS listener chạy trên `localhost:8443`, dùng:

```bash
keytool -printcert -sslserver localhost:8443 -v
```

Output có thể hiển thị:

```text
Certificate #0
Owner: CN=localhost, O=Example, C=VN
Issuer: CN=Example Test Root CA, O=Example, C=VN
Certificate fingerprints:
    SHA256: ...

Certificate #1
Owner: CN=Example Test Root CA, O=Example, C=VN
Issuer: CN=Example Test Root CA, O=Example, C=VN
```

Certificate #0 là leaf certificate server trình bày. Certificate tiếp theo có thể là intermediate hoặc root nếu server gửi nó.

Trong một lần kiểm thử local trên JDK 24.0.2, `keytool -printcert -sslserver localhost:18443 -v` đọc được leaf certificate và root CA từ TLS server thử nghiệm; TLS handshake hoàn tất. Fingerprint của leaf khớp fingerprint khi đọc file PEM và DER.

Nếu server không gửi chain đầy đủ, hãy kiểm tra cấu hình TLS server và certificate bundle. Đừng tự suy ra chain đầy đủ chỉ từ certificate leaf.

## 17. Ví dụ xem signer certificate trong JAR

Tạo hoặc nhận một JAR đã ký, sau đó xem signer:

```bash
keytool -printcert -jarfile app.jar -v
```

Xem chữ ký và chain:

```bash
jarsigner -verify -verbose -certs -keystore truststore.p12 -storetype PKCS12 app.jar
```

Trong thử nghiệm trên JDK 24.0.2, JAR ký bằng certificate có EKU `codeSigning` và chain kết thúc tại root đã import vào truststore. `keytool -printcert -jarfile` hiển thị signer certificate và root; `jarsigner -verify` xác nhận chữ ký.

Một JAR không có timestamp có thể vẫn được xác minh ở hiện tại nhưng có thể không còn xác minh được sau khi signer certificate hết hạn. Release pipeline nên cân nhắc timestamp authority theo chính sách ký của tổ chức.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Input not an X.509 certificate` | File không phải certificate X.509 hoặc sai định dạng | Kiểm tra PEM/DER và nội dung file |
| `Keystore was tampered with, or password was incorrect` | Sai mật khẩu hoặc store type | Xác nhận mật khẩu và `-storetype` |
| `Alias does not exist` | Sai alias hoặc entry chưa được import | Dùng `keytool -list` để liệt kê alias |
| Không thấy certificate chain đầy đủ | Thiếu intermediate hoặc reply import sai | Kiểm tra `Certificate chain length` và thứ tự import |
| `Certificate expired` | Thời hạn đã kết thúc | Xác minh ngày hệ thống và yêu cầu certificate mới |
| `Not yet valid` | Thời điểm hiện tại trước `Valid from` | Kiểm tra đồng hồ và thời gian phát hành |
| Hostname mismatch | SAN không chứa hostname/IP được truy cập | Cấp certificate có SAN đúng |
| `PKIX path building failed` | Chain không kết thúc tại trust anchor được tin cậy | Kiểm tra root/intermediate và truststore |
| `unable to find valid certification path` | Thiếu CA hoặc chain không hợp lệ | Lấy CA từ nguồn tin cậy và xác minh fingerprint |
| `Certificate reply does not contain public key` | Import certificate reply không khớp private key alias | Tạo CSR từ đúng alias và import đúng reply |
| EKU không phù hợp | Certificate không dành cho serverAuth/clientAuth/codeSigning cần dùng | Cấp certificate với mục đích phù hợp |
| TLS handshake failure | Certificate, protocol, cipher, trust hoặc hostname có vấn đề | Kiểm tra chain và cấu hình TLS client/server |
| JAR signature invalid | Nội dung JAR thay đổi sau khi ký hoặc chữ ký hỏng | Build lại rồi ký artifact cuối cùng |
| JAR báo thiếu timestamp | Không dùng timestamp authority | Áp dụng timestamp theo chính sách release |

Khi gặp lỗi, phân biệt lỗi đọc file, lỗi keystore, lỗi chain và lỗi ứng dụng TLS. Không import một certificate lạ vào truststore chỉ để làm biến mất lỗi.

## 19. Quy trình kiểm tra certificate có hệ thống

Một quy trình kiểm tra thực tế:

1. Xác định nguồn certificate: file, keystore, TLS server hay signed JAR.
2. Chạy đúng lệnh `keytool -printcert` hoặc `keytool -list -v`.
3. Ghi lại Subject, Issuer, serial và thời hạn.
4. Kiểm tra SAN khớp hostname/IP thực tế.
5. Kiểm tra Basic Constraints, Key Usage và Extended Key Usage.
6. Kiểm tra public key và signature algorithm theo chính sách bảo mật.
7. So sánh SHA-256 fingerprint với giá trị được xác thực độc lập.
8. Xem chain và xác định trusted root.
9. Kiểm tra truststore ứng dụng thực sự đang sử dụng.
10. Thực hiện TLS handshake hoặc JAR signature verification trong đúng môi trường chạy.
11. Kiểm tra revocation và timestamp nếu chính sách yêu cầu.
12. Ghi nhận alias, store type, certificate fingerprint và thời hạn để phục vụ vận hành.

Với certificate production, lưu lại fingerprint và ngày hết hạn để chủ động gia hạn. Không chia sẻ private key hoặc keystore có private key trong báo cáo điều tra.

## 20. Bảo mật khi sử dụng keytool

- Không gửi file `.p12`, `.pfx` hoặc `.jks` có private key cho người không có quyền.
- Không đưa mật khẩu keystore vào source code, ticket, log hoặc lệnh dùng chung.
- Ưu tiên để keytool hỏi mật khẩu tương tác trong phiên quản trị an toàn.
- Chỉ import CA sau khi kiểm tra fingerprint từ nguồn độc lập.
- Không dùng self-signed certificate trong production chỉ vì keytool đọc được nó.
- Không tắt hostname verification hoặc trust validation để né lỗi.
- Bảo vệ file truststore và giới hạn quyền sửa CA.
- Dùng thuật toán và kích thước key theo chính sách PKI hiện hành.
- Theo dõi hạn certificate, quy trình gia hạn và thu hồi.
- Tách certificate public khỏi private key trong quy trình trao đổi file.

Certificate là dữ liệu công khai trong nhiều tình huống, nhưng quyết định trust một certificate có ảnh hưởng trực tiếp tới bảo mật kết nối và artifact. Hãy xác minh danh tính và chain trước khi thay đổi trust configuration.

## 21. Checklist nhanh khi xem certificate

- [ ] Đã xác định đúng file, alias, TLS endpoint hoặc JAR chưa?
- [ ] Subject/Owner có đúng danh tính dự kiến không?
- [ ] Issuer có đúng CA không?
- [ ] Serial number đã được ghi nhận chưa?
- [ ] Certificate còn trong thời hạn hiệu lực không?
- [ ] SAN có hostname/IP mà client truy cập không?
- [ ] SHA-256 fingerprint khớp nguồn tin cậy độc lập không?
- [ ] Public key và signature algorithm có đáp ứng chính sách không?
- [ ] Basic Constraints, Key Usage và EKU có phù hợp mục đích không?
- [ ] Certificate chain có intermediate và trusted root cần thiết không?
- [ ] Truststore của ứng dụng có chứa đúng trust anchor không?
- [ ] Đã thực hiện xác minh TLS/JAR thực tế nếu mục đích yêu cầu chưa?

## 22. Tổng kết

`keytool -printcert` là lệnh chính để xem nội dung certificate X.509. Dùng `-file` cho certificate PEM/DER, `-sslserver` cho certificate server trình bày và `-jarfile` cho signer certificate trong JAR. Dùng `keytool -list -v` để xem alias, entry type và certificate chain trong keystore.

Khi đọc output, tập trung vào Subject, Issuer, serial number, thời hạn, SHA-256 fingerprint, public key, signature algorithm, SAN, Basic Constraints, Key Usage và Extended Key Usage. Xem cả chain thay vì chỉ leaf certificate.

Hãy phân biệt việc hiển thị certificate với xác minh trust. Certificate phải có chain được tin cậy, còn hạn, khớp hostname và phù hợp mục đích sử dụng. Với JAR, kiểm tra chữ ký bằng `jarsigner -verify`; với TLS, kiểm tra bằng client thực tế và truststore được cấu hình.

**Tài liệu tham khảo chính thức:**

- [Oracle JDK 24 — keytool command reference](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- [Oracle JDK 24 — jarsigner command reference](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Java SE 24 API — X509Certificate](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/X509Certificate.html)
- [Java SE 24 API — Certificate](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/cert/Certificate.html)
- [Java SE 24 API — KeyStore](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/KeyStore.html)
