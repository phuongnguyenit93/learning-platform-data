# Tạo key pair bằng keytool

**Key pair** (cặp khóa) gồm một **private key** (khóa riêng) và một **public key** (khóa công khai) có quan hệ toán học với nhau. Java dùng cặp khóa trong các cơ chế mật mã khóa công khai như ký số, xác minh chữ ký và một số giao thức trao đổi/bảo vệ dữ liệu.

JDK cung cấp công cụ **`keytool`** để tạo và quản lý key pair, certificate và keystore. Lệnh thường dùng nhất để tạo cặp khóa là **`keytool -genkeypair`**. Lệnh này tạo private key, public key và một chứng thư số X.509 tự ký (self-signed certificate), sau đó lưu private key cùng certificate vào keystore.

## 1. Key pair hoạt động như thế nào?

Một cặp khóa có hai thành phần:

- **Private key:** phải được giữ bí mật. Chủ sở hữu dùng khóa này để ký dữ liệu hoặc thực hiện thao tác mật mã cần khóa riêng.
- **Public key:** có thể chia sẻ. Bên nhận dùng khóa công khai để xác minh chữ ký hoặc thực hiện thao tác phù hợp với thuật toán.

Với chữ ký số:

1. Người gửi tạo chữ ký từ dữ liệu bằng private key.
2. Người nhận dùng public key tương ứng để xác minh chữ ký.
3. Nếu xác minh thành công, chữ ký cho thấy dữ liệu phù hợp với private key đã ký và không bị thay đổi kể từ lúc ký, theo giả định thuật toán và khóa an toàn.

Public key thường được phân phối thông qua certificate X.509. Certificate liên kết public key với thông tin chủ thể (subject) và được ký bởi một CA hoặc tự ký trong môi trường thử nghiệm.

**Không chia sẻ private key.** Việc gửi certificate chứa public key cho người khác là bình thường; gửi keystore chứa private key hoặc mật khẩu keystore có thể làm lộ danh tính ký và cho phép người khác giả mạo chủ sở hữu khóa.

## 2. Keystore và truststore

`keytool` lưu khóa và certificate trong một **keystore**. Keystore là tệp chứa các entry, mỗi entry có alias để nhận diện.

Hai loại entry quan trọng:

| Loại entry | Nội dung | Mục đích |
| --- | --- | --- |
| `PrivateKeyEntry` | Private key cùng certificate và có thể cả certificate chain | Lưu khóa của ứng dụng để ký hoặc xác thực |
| `trustedCertEntry` | Một certificate được tin cậy, không có private key tương ứng | Lưu CA certificate hoặc certificate được tin cậy |

**Keystore** thường chứa private key của chính ứng dụng hoặc máy chủ. **Truststore** thường chứa certificate của CA hoặc đối tác mà ứng dụng tin cậy. Về mặt kỹ thuật, cả hai có thể dùng cùng định dạng tệp; tên gọi phản ánh mục đích sử dụng.

### Định dạng keystore

- **PKCS12:** định dạng tiêu chuẩn, có khả năng tương tác với nhiều công cụ và nền tảng. Đây là lựa chọn phù hợp cho keystore mới.
- **JKS:** định dạng keystore truyền thống của Java, vẫn có thể gặp trong hệ thống cũ.

Trong bài này, các lệnh dùng rõ `-storetype PKCS12` để tránh phụ thuộc vào giá trị mặc định của môi trường.

## 3. Kiểm tra keytool

`keytool` là công cụ đi kèm JDK. Kiểm tra môi trường:

```bash
java -version
keytool -help
keytool -genkeypair -help
```

Nếu terminal không nhận diện `keytool`:

- Kiểm tra máy đã cài JDK đầy đủ.
- Kiểm tra thư mục `bin` của JDK có trong `PATH`.
- Kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK.
- Mở terminal mới sau khi thay đổi biến môi trường.

Trợ giúp của `keytool -genkeypair` liệt kê các tùy chọn như `-alias`, `-keyalg`, `-keysize`, `-groupname`, `-sigalg`, `-dname`, `-validity`, `-ext`, `-keystore` và `-storetype`. Tùy chọn cụ thể có thể khác theo JDK; dùng trợ giúp trên đúng phiên bản đang triển khai.

## 4. Tạo key pair RSA và lưu vào PKCS12

Ví dụ tạo cặp khóa RSA dùng cho môi trường phát triển. Lệnh tạo keystore `app-signing.p12` và entry có alias `app-signing`:

```bash
keytool -genkeypair -alias app-signing -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore app-signing.p12 -dname "CN=Example Development Key, OU=Engineering, O=Example Org, L=Ho Chi Minh City, ST=Ho Chi Minh City, C=VN"
```

Giải thích:

- `-genkeypair`: tạo cặp khóa và certificate.
- `-alias app-signing`: tên entry trong keystore.
- `-keyalg RSA`: chọn thuật toán RSA.
- `-keysize 3072`: chọn kích thước khóa 3072 bit.
- `-sigalg SHA256withRSA`: dùng thuật toán chữ ký SHA-256 với RSA cho certificate tự ký.
- `-validity 365`: certificate có hiệu lực 365 ngày.
- `-storetype PKCS12`: dùng định dạng PKCS12.
- `-keystore app-signing.p12`: tên tệp keystore đầu ra.
- `-dname`: thông tin Distinguished Name của subject trong certificate.

Nếu không truyền mật khẩu trong dòng lệnh, `keytool` sẽ hỏi mật khẩu keystore trong terminal. Nhập mật khẩu đủ mạnh và xác nhận theo lời nhắc. Với PKCS12, mật khẩu bảo vệ private key thường phải giống mật khẩu keystore; khi công cụ hỏi mật khẩu riêng cho key, nhấn Enter để dùng cùng mật khẩu nếu được yêu cầu.

Không đưa mật khẩu thật vào lệnh shell, script được commit hoặc log CI. Cách nhập tương tác giúp tránh lưu mật khẩu trực tiếp trong lịch sử dòng lệnh.

Lệnh tạo certificate tự ký. Đây là lựa chọn tiện cho development, thử nghiệm và kiểm tra quy trình; certificate tự ký không tự động được hệ điều hành, trình duyệt hoặc khách hàng tin cậy.

## 5. Kiểm tra keystore và key pair vừa tạo

Dùng `-list` để xem các entry:

```bash
keytool -list -keystore app-signing.p12 -storetype PKCS12
```

Để xem chi tiết:

```bash
keytool -list -v -alias app-signing -keystore app-signing.p12 -storetype PKCS12
```

Sau khi nhập mật khẩu, kiểm tra các thông tin:

- Alias có đúng là `app-signing`.
- Entry type là `PrivateKeyEntry`.
- Certificate chain length thường là 1 với certificate tự ký mới tạo.
- Subject chứa Distinguished Name đã khai báo.
- Issuer trùng subject đối với certificate tự ký.
- Public key algorithm và key size đúng với lựa chọn.
- Signature algorithm và thời gian hiệu lực phù hợp.

Ví dụ, phần kết quả có thể cho biết:

```text
Alias name: app-signing
Entry type: PrivateKeyEntry
Certificate chain length: 1
Owner: CN=Example Development Key, ...
Issuer: CN=Example Development Key, ...
Subject Public Key Algorithm: 3072-bit RSA key
Signature algorithm name: SHA256withRSA
```

Đây là các trường minh họa; cách trình bày và giá trị chi tiết phụ thuộc JDK, certificate và thời điểm tạo.

## 6. Xuất public certificate

Public key thường được chia sẻ dưới dạng certificate X.509. Dùng `-exportcert` để xuất certificate của alias:

```bash
keytool -exportcert -rfc -alias app-signing -keystore app-signing.p12 -storetype PKCS12 -file app-signing.crt
```

- `-exportcert`: xuất certificate gắn với alias.
- `-rfc`: xuất theo dạng PEM, có dòng `BEGIN CERTIFICATE` và `END CERTIFICATE`.
- `-file app-signing.crt`: tệp certificate đầu ra.

Đọc certificate đã xuất:

```bash
keytool -printcert -file app-signing.crt -v
```

Có thể chia sẻ certificate công khai cho bên cần xác minh chữ ký hoặc kiểm tra danh tính. Tệp certificate chứa public key và thông tin X.509; nó **không chứa private key**.

`keytool -exportcert` không xuất private key. Giữ tệp `.p12` và mật khẩu của nó ở nơi bảo vệ an toàn.

## 7. Tạo key pair bằng thuật toán EC

Ngoài RSA, `keytool` hỗ trợ elliptic-curve cryptography (EC). Ví dụ tạo khóa EC trên nhóm `secp256r1`:

```bash
keytool -genkeypair -alias app-ec -keyalg EC -groupname secp256r1 -sigalg SHA256withECDSA -validity 365 -storetype PKCS12 -keystore app-ec.p12 -dname "CN=Example EC Key, OU=Engineering, O=Example Org, L=Ho Chi Minh City, ST=Ho Chi Minh City, C=VN"
```

Giải thích:

- `-keyalg EC`: tạo cặp khóa elliptic curve.
- `-groupname secp256r1`: chọn nhóm đường cong.
- `-sigalg SHA256withECDSA`: dùng ECDSA với SHA-256 để ký certificate tự ký.
- Các tùy chọn alias, validity, keystore và subject có ý nghĩa tương tự ví dụ RSA.

EC có thể cung cấp mức bảo mật tương đương với khóa RSA có kích thước lớn hơn, nhưng khả năng tương thích phụ thuộc hệ thống và giao thức. Chọn thuật toán, curve và kích thước theo chính sách bảo mật của tổ chức, nền tảng đích và yêu cầu của đối tác.

Không nên chọn thuật toán chỉ dựa trên việc lệnh tạo khóa chạy thành công; cần xác nhận hệ thống tiêu thụ hỗ trợ thuật toán và định dạng certificate đó.

## 8. Thêm Subject Alternative Name (SAN) cho certificate

Nếu certificate được dùng cho TLS, tên máy chủ nên được ghi trong **Subject Alternative Name (SAN)**. Chỉ ghi Common Name (CN) thường không đủ cho việc xác minh hostname hiện đại.

Ví dụ tạo certificate phát triển cho `localhost`:

```bash
keytool -genkeypair -alias localhost-tls -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore localhost-tls.p12 -dname "CN=localhost, OU=Development, O=Example Org, L=Ho Chi Minh City, ST=Ho Chi Minh City, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Tùy chọn `-ext` thêm X.509 extension. Trong ví dụ:

- `dns:localhost` khai báo DNS name.
- `ip:127.0.0.1` khai báo địa chỉ IP loopback.

Kiểm tra SAN:

```bash
keytool -list -v -alias localhost-tls -keystore localhost-tls.p12 -storetype PKCS12
```

Tìm phần SubjectAlternativeName trong certificate extensions.

Certificate tự ký cho localhost phù hợp để phát triển hoặc kiểm thử có kiểm soát. Nó không tự được client tin cậy trong production. Môi trường production cần certificate do CA phù hợp cấp, hostname SAN đúng với dịch vụ và chuỗi tin cậy được cấu hình đúng.

## 9. Tạo Certificate Signing Request (CSR)

Khi cần certificate do CA ký, không gửi private key cho CA. Thay vào đó, tạo **Certificate Signing Request (CSR)** từ entry chứa key pair.

Tạo CSR:

```bash
keytool -certreq -alias app-signing -keystore app-signing.p12 -storetype PKCS12 -file app-signing.csr -sigalg SHA256withRSA
```

CSR chứa public key và thông tin subject cần CA xác nhận; nó được ký bằng private key tương ứng để chứng minh người tạo sở hữu khóa riêng.

Quy trình tổng quát:

1. Tạo key pair trong keystore.
2. Tạo CSR bằng `keytool -certreq`.
3. Gửi CSR cho CA theo quy trình đăng ký.
4. CA xác minh yêu cầu và cấp certificate cùng chain cần thiết.
5. Kiểm tra certificate và chain nhận được.
6. Import certificate reply vào đúng alias đang chứa private key.
7. Kiểm tra lại entry và certificate chain bằng `keytool -list -v`.

Khi CA trả certificate, import certificate reply vào alias key pair:

```bash
keytool -importcert -alias app-signing -file app-signing-reply.pem -keystore app-signing.p12 -storetype PKCS12
```

Tệp reply cần chứa certificate được cấp cho public key trong CSR và chain cần thiết theo hướng dẫn của CA. CA root/intermediate cần được tin cậy và phân giải đúng để keytool xác minh chain. Không import một certificate không rõ nguồn gốc chỉ vì lệnh hiển thị lời nhắc xác nhận.

**Không tạo key pair mới sau khi gửi CSR** nếu muốn dùng certificate reply cho key hiện tại. Nếu thay private key, CSR cũ không còn khớp với key mới.

## 10. Tạo truststore và import certificate tin cậy

Truststore thường lưu certificate của CA hoặc đối tác mà ứng dụng tin cậy. Ví dụ import root CA certificate vào một truststore riêng:

```bash
keytool -importcert -alias example-root-ca -file root-ca.crt -keystore app-truststore.p12 -storetype PKCS12
```

Keytool yêu cầu xác nhận certificate. Trước khi trả lời đồng ý:

1. Lấy fingerprint certificate từ nguồn độc lập đáng tin cậy, chẳng hạn kênh phân phối chính thức của CA.
2. So sánh fingerprint với kết quả keytool hiển thị.
3. Xác nhận đúng certificate và đúng tổ chức.
4. Chỉ sau đó mới xác nhận import.

Liệt kê truststore:

```bash
keytool -list -v -keystore app-truststore.p12 -storetype PKCS12
```

Entry certificate tin cậy thường có loại `trustedCertEntry`. Nó chứa certificate được tin cậy, không phải private key của ứng dụng.

Không import certificate vào truststore chỉ vì nó được gửi kèm email hoặc tải từ một địa chỉ không xác thực. Việc thêm certificate vào truststore có thể làm ứng dụng tin cậy danh tính hoặc CA đó.

## 11. Dùng key pair để ký JAR

Một trường hợp sử dụng phổ biến của key pair là ký số JAR. Công cụ `jarsigner` dùng private key trong keystore để ký nội dung archive.

Ví dụ:

```bash
jarsigner -keystore app-signing.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar app-signing
```

Ý nghĩa:

- `-keystore app-signing.p12`: keystore chứa private key.
- `-storetype PKCS12`: định dạng keystore.
- `-signedjar app-signed.jar`: tên JAR sau khi ký.
- `app.jar`: JAR nguồn.
- `app-signing`: alias của entry chứa private key.

Keytool/jarsigner sẽ yêu cầu mật khẩu khi cần. Không truyền mật khẩu thật trực tiếp trong script hoặc lệnh được ghi vào lịch sử shell.

Xác minh chữ ký:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

Chữ ký cho phép kiểm tra nội dung JAR có bị thay đổi sau khi ký hay không và certificate nào đã được dùng. Tuy nhiên, JAR ký bằng certificate tự ký vẫn có thể không được người nhận tin cậy. Xác minh tính toàn vẹn và xác minh danh tính tin cậy là hai việc khác nhau.

## 12. Alias, mật khẩu và bảo vệ private key

**Alias** là tên dùng để truy xuất entry trong keystore. Một keystore có thể chứa nhiều alias, ví dụ:

- `app-signing`: khóa ký JAR.
- `localhost-tls`: khóa dùng cho môi trường TLS development.
- `service-client`: khóa xác thực client.
- `example-root-ca`: certificate CA tin cậy trong truststore.

Một số lệnh quản lý thường dùng:

| Lệnh | Công dụng |
| --- | --- |
| `keytool -list` | Liệt kê entry trong keystore |
| `keytool -list -v -alias <alias>` | Xem chi tiết entry |
| `keytool -exportcert` | Xuất public certificate |
| `keytool -importcert` | Import certificate hoặc chain |
| `keytool -certreq` | Tạo CSR từ key pair |
| `keytool -delete -alias <alias>` | Xóa entry |
| `keytool -changealias` | Đổi alias |
| `keytool -storepasswd` | Đổi mật khẩu keystore |
| `keytool -keypasswd` | Đổi mật khẩu private key entry khi định dạng hỗ trợ |

Thực hành bảo vệ:

- Dùng mật khẩu mạnh, riêng biệt và lưu trong secret manager phù hợp.
- Hạn chế quyền đọc tệp keystore theo tài khoản hệ điều hành.
- Không commit keystore, private key hoặc mật khẩu vào Git.
- Không gửi private key qua chat, email hoặc hệ thống ticket.
- Sao lưu keystore theo quy trình mã hóa và kiểm soát truy cập.
- Luân chuyển hoặc thu hồi certificate khi private key bị lộ.
- Tách khóa development, test và production.
- Không tái sử dụng một private key cho nhiều mục đích nếu chính sách bảo mật yêu cầu tách biệt.

Nếu private key bị lộ, chỉ đổi mật khẩu keystore là chưa đủ. Kẻ tấn công có thể đã sao chép private key; cần xử lý certificate, thu hồi hoặc thay khóa theo quy trình phù hợp.

## 13. Những lỗi thường gặp khi tạo key pair

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `keytool` không được nhận diện | Chưa cài JDK hoặc `PATH` chưa có thư mục `bin` | Kiểm tra `JAVA_HOME` và `PATH` |
| Alias đã tồn tại | Keystore đã có entry cùng alias | Chọn alias khác hoặc kiểm tra entry hiện tại trước khi thay đổi |
| Không mở được keystore | Sai mật khẩu hoặc sai định dạng keystore | Xác nhận mật khẩu và `-storetype` |
| Lỗi khi dùng key password khác store password với PKCS12 | PKCS12 thường yêu cầu mật khẩu private key trùng mật khẩu keystore | Dùng cùng mật khẩu cho store và key |
| Thuật toán hoặc key size không được hỗ trợ | Provider/JDK không hỗ trợ lựa chọn đó hoặc chính sách bảo mật chặn | Kiểm tra `keytool -genkeypair -help` và cấu hình provider |
| Certificate TLS không khớp hostname | SAN thiếu DNS/IP cần dùng | Tạo certificate có SAN chính xác hoặc xin certificate mới từ CA |
| Client không tin certificate | Certificate tự ký hoặc chain CA chưa được tin cậy | Dùng CA phù hợp và cấu hình truststore đúng |
| Import certificate reply thất bại | Certificate không khớp public key trong alias hoặc chain không đầy đủ | Kiểm tra CSR, alias, chain và certificate CA |
| Chia sẻ certificate nhưng bên nhận yêu cầu private key | Nhầm certificate công khai với key pair | Chia sẻ certificate/public key; chỉ chuyển private key qua quy trình bảo mật được phê duyệt |
| Chữ ký JAR hợp lệ nhưng vẫn có cảnh báo trust | Certificate tự ký hoặc CA chưa được bên nhận tin cậy | Phân phối certificate chain phù hợp và dùng CA được tin cậy |

## 14. Quy trình tạo key pair đề xuất

Một quy trình cơ bản, có thể lặp lại:

1. Xác định mục đích: ký JAR, TLS server, xác thực client hay thử nghiệm.
2. Chọn thuật toán và kích thước khóa phù hợp với chính sách bảo mật.
3. Chọn alias dễ nhận biết và tạo keystore PKCS12.
4. Dùng `keytool -genkeypair` để tạo key pair và certificate.
5. Kiểm tra entry bằng `keytool -list -v`.
6. Nếu cần chia sẻ public key, xuất certificate bằng `keytool -exportcert -rfc`.
7. Nếu cần CA ký, tạo CSR bằng `keytool -certreq` và nhập certificate reply vào đúng alias.
8. Nếu cần tin cậy CA, xác minh fingerprint rồi import certificate vào truststore.
9. Thử mục đích sử dụng thực tế, chẳng hạn ký JAR và xác minh chữ ký.
10. Bảo vệ keystore, mật khẩu và private key theo quy trình vận hành.

Lưu lại thuật toán, alias, loại keystore, thời hạn certificate và người/quy trình chịu trách nhiệm quản lý. Không ghi private key hoặc mật khẩu vào tài liệu vận hành.

## 15. Ghi nhớ

- Key pair gồm private key và public key; private key phải được bảo vệ.
- `keytool -genkeypair` tạo cặp khóa và certificate tự ký, lưu trong keystore.
- Dùng `-alias` để đặt tên entry, `-keyalg` để chọn thuật toán và `-keysize` hoặc `-groupname` để chọn tham số khóa.
- PKCS12 là định dạng keystore phù hợp cho hệ thống mới và khả năng tương tác.
- `keytool -list -v` kiểm tra entry, certificate, thuật toán và thời hạn.
- `keytool -exportcert -rfc` xuất certificate chứa public key, không xuất private key.
- `keytool -certreq` tạo CSR để CA cấp certificate.
- Truststore lưu certificate được tin cậy; cần xác minh fingerprint trước khi import.
- Certificate tự ký phù hợp cho development/test nhưng không tự được tin cậy trong production.
- Không commit hoặc chia sẻ keystore chứa private key; khi lộ private key, cần thay khóa và xử lý certificate liên quan.

Nắm được quy trình `keytool -genkeypair` → kiểm tra keystore → xuất certificate hoặc tạo CSR giúp bạn tạo và quản lý key pair Java đúng mục đích, đồng thời bảo vệ private key trong suốt vòng đời sử dụng.
