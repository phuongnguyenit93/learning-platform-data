# Kiểm tra chứng thư và dấu vân tay bằng keytool (Java 10+)

## 1. Vì sao cần kiểm tra chứng thư gốc thay vì chỉ “thấy kết nối HTTPS hoạt động”?

Khi ứng dụng Java mở kết nối TLS, nó cần quyết định **có tin chứng thư máy chủ hay không**. Việc này phụ thuộc vào nhiều yếu tố: chuỗi chứng thư X.509, tổ chức phát hành (CA), **trust anchor** do ứng dụng tin cậy, hạn sử dụng, chính sách thuật toán, danh tính máy chủ và trong một số cấu hình cả tình trạng thu hồi chứng thư.

Công cụ `keytool` đi kèm JDK giúp **đọc, liệt kê, xuất, nhập và kiểm tra các trường của chứng thư**. Trong bài này, nhiệm vụ chính là:

- Xem thông tin một file chứng thư dạng PEM hoặc DER.
- Tìm **SHA-256 certificate fingerprint** và đối chiếu với nguồn độc lập.
- Liệt kê một chứng thư trong Java truststore `cacerts` hoặc truststore riêng.
- Phân biệt **root CA, intermediate CA, leaf/server certificate**.
- Hiểu rằng đọc fingerprint **không đồng nghĩa đã kiểm chứng tính tin cậy**.
- Tạo và kiểm thử một root CA **chỉ dùng trong lab**, không sửa truststore hệ thống.
- Nhận diện các lỗi kiểm tra TLS/truststore thường gặp trên JDK hiện hành.

### Liên hệ Java 10: JEP 319

**JEP 319 — Root Certificates** được triển khai trong **JDK 10** nhằm cung cấp một tập **root CA certificates mặc định** trong các bản OpenJDK thích hợp. Trước đó, một số bản OpenJDK có `cacerts` trống, làm việc thiết lập các kết nối TLS phổ biến khó khăn nếu không cấu hình truststore riêng.

Kiến thức đó **vẫn áp dụng ngày nay**, nhưng không được hiểu nhầm thành “danh sách root CA luôn cố định từ Java 10 tới hiện tại”. Nhà cung cấp JDK có thể thêm, bỏ, hạn chế hoặc thay đổi chính sách đối với các trust anchors theo thời gian. **Kiểm tra chính runtime JDK đang chạy** chứ không dựa vào một danh sách certificate của bản JDK cũ.

**Special Note của module:** bài dùng `keytool`, X.509, SHA-256, PKCS#12 và các API Java 17+ còn phù hợp. Không khuyến nghị dùng hash MD5/SHA-1 làm cơ sở xác thực bảo mật mới, không hướng dẫn vô hiệu hóa TLS verification và không xem việc nhập bừa certificate vào `cacerts` là cách sửa lỗi kết nối.

## 2. Kiến thức nền: root, intermediate, leaf và trust anchor

Một chuỗi TLS đơn giản có thể được hình dung:

```text
Root CA (trust anchor đã được cấu hình tin cậy)
    |
    | ký phát hành
    v
Intermediate CA
    |
    | ký phát hành
    v
Leaf certificate / TLS server certificate
    |
    | chứng nhận public key cho một danh tính máy chủ
    v
HTTPS server: api.example.test
```

### 2.1. Root CA certificate

Một **root CA** thường có certificate **self-signed**, nghĩa là subject và issuer là cùng một thực thể và chữ ký có thể kiểm tra bằng chính public key của certificate ấy. Nó có thể mang:

- `Basic Constraints: CA:TRUE`;
- `Key Usage: keyCertSign`, có thể thêm `cRLSign`;
- public key của CA và các định danh X.509 khác.

**Quan trọng:** có thể tự tạo một root CA bất kỳ với tên `CN=Famous Root CA`. Việc nó **self-signed và tự xác minh chữ ký được** không làm nó tự động đáng tin. **Trust** đến từ quyết định đưa certificate/public key phù hợp thành **trust anchor** trong một truststore/chính sách đáng tin.

### 2.2. Intermediate CA certificate

Intermediate được CA khác ký, có thể dùng để ký leaf hoặc intermediate tiếp theo trong phạm vi `BasicConstraints`, `KeyUsage` và các ràng buộc khác. Nó **không mặc định là trust anchor**, dù có thể xuất hiện trong chuỗi mà máy chủ gửi.

### 2.3. Leaf/server certificate

Đây là chứng thư của máy chủ cụ thể, thường có:

- `Subject Alternative Name (SAN)` chứa DNS/IP được sử dụng;
- `Extended Key Usage (EKU): serverAuth` nếu chính sách yêu cầu;
- `Key Usage` phù hợp khóa và thuật toán;
- thời hạn `Not Before`/`Not After`;
- issuer trỏ tới CA phát hành.

**Không** dùng common name (`CN`) đơn thuần để bỏ qua kiểm tra SAN/hostname trên ứng dụng TLS hiện đại. Một certificate dù được CA tin cậy ký vẫn **có thể sai hostname**, hết hạn, bị thu hồi hoặc vi phạm chính sách thuật toán.

### 2.4. Truststore và keystore

Trong vận hành Java, hai thuật ngữ thường được dùng theo **vai trò**:

- **Truststore:** chứa các certificates/trust anchors mà ứng dụng tin cậy để kiểm tra phía đối tác.
- **Keystore:** có thể chứa private keys, certificate chains, trusted certificate entries và dữ liệu khóa tùy kiểu store/provider.

Cùng API `KeyStore` có thể dùng cho cả hai vai trò. **Đừng định nghĩa file `.jks` luôn là truststore và `.p12` luôn là keystore chứa khóa riêng.** Cả hai định dạng có thể dùng cho nhiều mục đích; nội dung **entry type** mới là điều cần kiểm tra.

Một entry quan trọng:

| Entry type | Ý nghĩa |
| --- | --- |
| `trustedCertEntry` | Chứa certificate tin cậy, **không** chứa private key gắn với entry |
| `PrivateKeyEntry` | Chứa private key và certificate chain tương ứng |
| `SecretKeyEntry` | Chứa secret key, không phải root CA X.509 thông thường |

**Không bao giờ tải lên/đưa công khai file chứa private key** chỉ vì nó có phần mở rộng `.p12` hoặc bạn cần cho người khác “xem fingerprint”.

## 3. Fingerprint SHA-256 là gì?

**Certificate fingerprint** là giá trị băm của **toàn bộ certificate được mã hóa theo DER**, thường hiển thị bằng các cặp byte hex ngăn bởi dấu hai chấm.

```text
SHA-256 certificate fingerprint = SHA-256(X.509 Certificate DER bytes)
```

SHA-256 tạo ra **32 byte = 256 bit**, hiển thị thành **64 chữ số hex**. Nếu tách thành từng cặp bởi `:`, chuỗi có **95 ký tự**: 64 ký tự hex + 31 dấu hai chấm.

**Ví dụ cấu trúc, không phải fingerprint của CA thực:**

```text
SHA256: AA:BB:CC:...:11:22:33
```

Trong đầu ra `keytool`, dòng thường có dạng `SHA256:` theo sau là một chuỗi đầy đủ; ví dụ có dấu `...` ở trên **chỉ minh họa định dạng**, không dùng để đối chiếu.

### 3.1. Fingerprint giúp xác minh điều gì?

Nó giúp kiểm tra **hai nguồn đang mô tả cùng certificate bytes**:

- File CA mà bạn tải về và SHA-256 do tổ chức sở hữu CA công bố qua **kênh độc lập, đáng tin**.
- Certificate được export từ một truststore và certificate chuẩn cần kiểm tra.
- Bản PEM và bản DER của cùng một certificate; fingerprint phải trùng nếu DER của certificate không đổi.
- Certificate trong image/runtime JDK đang chạy và artifact mà nhóm bảo mật đã phê duyệt.

### 3.2. Fingerprint không tự chứng minh trust

Giả sử kẻ tấn công thay certificate tải xuống **và** thay luôn fingerprint hiển thị trên cùng trang bị kiểm soát. Hai giá trị sẽ khớp nhưng **không có nguồn tin cậy độc lập**.

Muốn tin root CA, bạn cần xác minh fingerprint từ một **kênh đã được xác thực độc lập** hoặc một truststore đã được quản trị. Đọc `Subject=Trusted CA` và thấy self-signed **không đủ**.

### 3.3. Không nhầm certificate fingerprint với public-key/SPKI fingerprint

Hai certificate có thể chứa **cùng public key** nhưng khác thời hạn, issuer, extension hoặc chữ ký. Khi đó:

- **Certificate SHA-256 fingerprints có thể khác**.
- SHA-256 băm **SubjectPublicKeyInfo (SPKI)** của cùng khóa có thể trùng.

`keytool -printcert` hiển thị fingerprint của **certificate**, không phải tự động hiển thị một SPKI pin. Đừng so một chuỗi SPKI pin của hệ thống với certificate fingerprint như hai giá trị cùng loại.

### 3.4. SHA-1 và thuật toán chữ ký

`keytool -v` có thể hiển thị cả `SHA1` và `SHA256` fingerprints. SHA-1 không phải lựa chọn mới được khuyến nghị cho kiểm tra bảo mật vì giới hạn chống va chạm. Dùng **SHA-256** hoặc chính sách hiện hành phù hợp.

Một trường riêng như `Signature algorithm name: SHA256withRSA` mô tả **thuật toán chữ ký của certificate**, **không phải** tên của certificate fingerprint. Có thể thấy `SHA256 fingerprint` của một certificate có thuật toán chữ ký khác: hai khái niệm không đồng nhất.

## 4. Những lệnh `keytool` cần nhớ

Theo tài liệu Oracle **Java SE 26 — The keytool Command**, các lệnh đọc hiện hành:

| Lệnh | Dùng khi |
| --- | --- |
| `keytool -printcert -file cert.pem` | Đọc chứng thư trực tiếp từ file PEM/DER |
| `keytool -printcert -v -file cert.pem` | Xem trường/extension chi tiết |
| `keytool -printcert -rfc -file cert.der` | Xuất biểu diễn PEM (RFC-style), không phải đầu ra thông tin verbose |
| `keytool -list -cacerts` | Liệt kê root/trusted entries của truststore `cacerts` thuộc JDK được gọi |
| `keytool -list -v -cacerts -alias alias` | Xem chi tiết một entry của `cacerts` |
| `keytool -list -v -keystore trust.p12 -alias name` | Xem entry trong một keystore/truststore riêng |
| `keytool -exportcert -rfc -alias name -file cert.pem ...` | Xuất **chứng thư công khai** ra PEM |
| `keytool -printcert -sslserver host:443` | Xem certificate server trình bày qua kết nối TLS (cần mạng) |

**Những quy tắc cú pháp thiết yếu:**

1. Mỗi lần gọi `keytool` dùng **một command**: ví dụ `-list` hoặc `-printcert`.
2. `-printcert -file` **không cần keystore hoặc mật khẩu**.
3. `-list -cacerts` chọn truststore JDK mặc định; **không kết hợp `-cacerts` với `-keystore` hay `-storetype`**.
4. Với `-list`, `-v` và `-rfc` **không dùng đồng thời**; một cách hiển thị chi tiết, một cách in PEM.
5. `-printcert -file` và `-printcert -sslserver` **không dùng cùng một lệnh**.
6. `-alias` là **tên entry** trong keystore, không phải CN, subject, serial number hoặc fingerprint của chứng thư.
7. Với file private key, nên tránh in `-storepass` dạng literal trên command line. JDK hỗ trợ `-storepass:env NAME` hoặc `-storepass:file PATH`; cách lựa chọn thực tế phải theo secret-management policy.
8. `-printcert -rfc` in PEM để sao lưu/chuyển định dạng; nếu muốn đọc thời hạn/fingerprint có thể bỏ `-rfc` hoặc dùng `-v`.

### 4.1. Xác định đúng JDK/keytool

```bash
java -version
keytool -help
```

Trên Windows PowerShell:

```powershell
Get-Command java
Get-Command keytool
```

Trên POSIX:

```bash
command -v java
command -v keytool
```

**Không mặc định** `keytool` trong PATH thuộc cùng JDK mà ứng dụng Java đang chạy. Container image/build agent có thể có nhiều runtime. Nếu cần chính xác, gọi `$JAVA_HOME/bin/keytool` trên POSIX hoặc đường dẫn tương ứng trong Windows của **JDK thực sự dùng để chạy service**.

Không dựa vào số lượng root certificates của một máy khác để kết luận máy của bạn cũng có từng đó entries.

## 5. Kiểm tra một file chứng thư PEM hoặc DER

### 5.1. PEM là gì?

PEM thường là văn bản Base64 có marker:

```text
-----BEGIN CERTIFICATE-----
...base64...
-----END CERTIFICATE-----
```

Marker và `...` ở trên **minh họa định dạng**, không phải chứng thư hợp lệ. Một file PEM có thể chứa **nhiều certificate blocks**; cần biết bạn đang kiểm tra **certificate nào trong chain**.

### 5.2. DER là gì?

DER là biểu diễn **nhị phân chuẩn hóa** của ASN.1 X.509 certificate. `keytool -printcert -file` nhận PEM hoặc DER theo tài liệu. Khi export cùng certificate sang PEM và DER, **bytes của file PEM khác file DER**, nhưng đối tượng certificate DER được mã hóa bên trong là cùng chứng thư, nên certificate fingerprint phải trùng.

### 5.3. Lệnh đọc certificate

```bash
keytool -printcert -file lab-root.pem
keytool -printcert -v -file lab-root.pem
keytool -printcert -file lab-root.der
```

Khi đọc output, tìm các trường:

- `Owner` hoặc `Subject`: DN của thực thể được chứng nhận.
- `Issuer`: DN của thực thể phát hành.
- `Serial number`: serial number của certificate.
- `Valid from` / `until`: thời hạn `Not Before` và `Not After`.
- `Certificate fingerprints` → dòng `SHA256`.
- `Signature algorithm name`: thuật toán chữ ký.
- `Subject Public Key Algorithm`: thông tin public key.
- `Extensions`: `BasicConstraints`, `KeyUsage`, `SubjectAlternativeName`, `ExtendedKeyUsage` và các extension liên quan.

**Một số tên trường/cách biểu diễn thay đổi theo JDK/locale**. Đừng viết test dựa trên toàn bộ output từng ký tự; trích xuất các trường cần thiết.

### 5.4. Certificate chưa hết hạn vẫn có thể không hợp lệ

`Not Before <= now <= Not After` là **một điều kiện**, không phải toàn bộ kiểm tra PKIX/TLS. Một chứng thư còn hạn nhưng có thể bị từ chối do:

- không xây được đường dẫn đến trust anchor;
- sử dụng thuật toán/độ dài khóa không được policy chấp nhận;
- tên miền không khớp SAN;
- KeyUsage/EKU không phù hợp mục đích;
- certificate bị revoke theo chính sách kiểm tra thu hồi đang bật;
- basic constraints/path length hoặc name constraints không hợp lệ;
- chain thiếu intermediate hoặc sai thứ tự;
- trust anchor đã bị JDK security policy giới hạn.

`keytool -printcert` **hiển thị dữ liệu**, không tự thay toàn bộ bước kiểm tra PKIX và TLS hostname verification của ứng dụng.

## 6. Kiểm tra chứng thư gốc trong `cacerts`

### 6.1. Cách liệt kê an toàn, chỉ đọc

```bash
keytool -list -cacerts
```

Theo tài liệu JDK hiện hành, `cacerts` thường nằm dưới:

```text
$JAVA_HOME/lib/security/cacerts             (Linux/macOS)
%JAVA_HOME%\lib\security\cacerts          (Windows)
```

Tuy nhiên, một runtime build có thể có symlink, liên kết tới store do distro quản trị hoặc truststore riêng. **Ưu tiên `-cacerts`** để truy cập store của JDK mà `keytool` đang sử dụng; đừng đoán đường dẫn từ cấu trúc của bản JRE cũ.

`keytool` có thể hỏi **store password**. Nếu đọc mà không cung cấp password, có thể hiện cảnh báo tính toàn vẹn của dữ liệu chưa được xác minh. **Không nhầm “liệt kê được entries” với “đã xác minh tính toàn vẹn của store”.**

### 6.2. Xem một alias cụ thể

Sau khi đã biết alias từ danh sách:

```bash
keytool -list -v -cacerts -alias my-trusted-ca
```

`my-trusted-ca` ở đây là **tên alias minh họa**; thay bằng alias thực mà danh sách `-list -cacerts` hiển thị. Không chạy nguyên văn rồi kết luận CA đó bị thiếu.

Nếu alias có nhiều chứng thư hay là `PrivateKeyEntry`, đọc thông tin **chain length** và từng chứng thư tương ứng. Đối với các root CA trong `cacerts` thông thường, entry type thường là `trustedCertEntry`, nhưng không dùng giả định đó thay kết quả đọc thật.

### 6.3. Mật khẩu mặc định và bảo mật

Nhiều bản JDK có mật khẩu ban đầu `changeit` của `cacerts`. **Đây không phải secret bảo mật production đáng tin chỉ vì nó có sáu ký tự**. Nó cũng không bảo đảm mật khẩu của image/distro đang dùng chưa thay đổi.

- Tránh ghi mật khẩu thật trực tiếp vào shell history, CI logs, process arguments hoặc README.
- Sử dụng cơ chế nhập bí mật của môi trường, hoặc `-storepass:env`/`-storepass:file` theo chính sách.
- Hạn chế quyền sửa `cacerts` và audit thay đổi trust anchors.
- Không dùng `-noprompt` trên một thao tác **nhập certificate production** khi chưa xác minh nguồn certificate độc lập.
- Không chỉnh `cacerts` chỉ để “hết lỗi PKIX path building failed” khi chưa xác định đúng lý do.

### 6.4. Root có trong `cacerts` có chắc luôn được dùng không?

**Không.** Có những nguồn truststore khác:

- application đặt `-Djavax.net.ssl.trustStore=...`;
- framework tạo `SSLContext` hoặc `TrustManager` riêng;
- JDK distribution hoặc OS image dùng truststore đã tùy biến;
- container runtime có cacerts khác host;
- JDK security policy có thể distrust/restrict một số CA ở những bối cảnh nhất định.

Một alias nằm trong `cacerts` **không tự chứng minh kết nối TLS của ứng dụng đã chọn nó làm trust anchor**. Phải xem JVM thực tế và cấu hình JSSE/SSL context.

## 7. Bài thực hành an toàn: tạo root CA giả lập rồi kiểm tra bằng keytool

Bài lab này **không** cấp chứng thư cho website thật và **không** sửa `cacerts` của JDK. Mọi tệp được tạo trong **thư mục thử nghiệm riêng**, có thể xóa sau bài học.

**Mục tiêu của lab:** thực hành mọi bước đọc fingerprint và phân biệt `PrivateKeyEntry` với `trustedCertEntry`. Chứng thư tự ký trong lab sẽ chỉ được một truststore riêng tin cậy nếu ta **cố ý nhập nó vào truststore ấy**.

### 7.1. Chuẩn bị thư mục và mật khẩu lab

Tạo thư mục rỗng:

```bash
mkdir cert-lab
cd cert-lab
```

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Path cert-lab
Set-Location cert-lab
$env:LAB_CERT_PASS = 'Training-Only-385!'
```

Trên POSIX shell:

```bash
export LAB_CERT_PASS='Training-Only-385!'
```

**Mật khẩu `Training-Only-385!` là giá trị công khai chỉ để bài lab có thể chạy, không phải bí mật thật.** Không dùng nó trong production. Environment variable không phải nơi lưu secret hoàn hảo; secret managers, file descriptor hoặc protected prompt thích hợp hơn tùy chính sách. Sau bài lab, xóa biến môi trường và các tệp thử nghiệm trong thư mục riêng.

### 7.2. Tạo khóa và chứng thư root giả lập

Chạy **một dòng** (phù hợp PowerShell/POSIX):

```text
keytool -genkeypair -alias labroot -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Root CA, O=Training Only, C=VN" -validity 30 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore lab-root.p12 -storetype PKCS12 -storepass:env LAB_CERT_PASS -noprompt
```

Giải thích:

- `-genkeypair` tạo public/private key pair và certificate tự ký cho alias khi không chỉ định signer.
- `-keyalg RSA -keysize 3072` dùng RSA 3072-bit cho lab; không sử dụng key sizes yếu.
- `-sigalg SHA256withRSA` dùng thuật toán chữ ký hiện còn phù hợp trong demo.
- `-dname` đặt subject/issuer của certificate tự ký.
- `-validity 30` tạo thời hạn khoảng 30 ngày tính từ thời điểm chạy.
- `-ext bc=ca:true` đánh dấu certificate có khả năng là CA trong Basic Constraints.
- `-ext ku=keyCertSign,cRLSign` đặt key usages phục vụ ký certificate/CRL.
- `-keystore lab-root.p12 -storetype PKCS12` lưu **private key** vào PKCS#12 riêng.
- `-storepass:env LAB_CERT_PASS` lấy mật khẩu từ biến môi trường đã đặt.
- `-noprompt` ở đây chỉ bỏ prompt trong **lab tự tạo**, không phải hướng dẫn bỏ xác minh khi nhập chứng thư chưa được kiểm chứng.

Lệnh tạo file `lab-root.p12`. **Bảo vệ file này như chứa private key**, dù đây chỉ là khóa demo.

### 7.3. Xuất certificate công khai thành PEM và DER

```bash
keytool -exportcert -alias labroot -rfc -file lab-root.pem -keystore lab-root.p12 -storepass:env LAB_CERT_PASS
keytool -exportcert -alias labroot -file lab-root.der -keystore lab-root.p12 -storepass:env LAB_CERT_PASS
```

- `lab-root.pem` là certificate public ở định dạng PEM.
- `lab-root.der` là certificate public ở định dạng DER nhị phân.
- `lab-root.p12` chứa private key và certificate.

**`-exportcert` không xuất private key.** Đừng gửi toàn bộ `lab-root.p12` chỉ vì người khác cần chứng thư công khai; gửi `.pem` hoặc `.der` khi được phép, kèm fingerprint từ nguồn đáng tin.

### 7.4. Kiểm tra fingerprint trực tiếp từ hai file

```bash
keytool -printcert -file lab-root.pem
keytool -printcert -file lab-root.der
```

Hai lệnh phải hiển thị **cùng SHA-256 certificate fingerprint**. Chúng đọc cùng chứng thư được export ở hai cách mã hóa.

**Không chép một SHA-256 có giá trị cố định vào output bài lab**: mỗi lần `-genkeypair` tạo khóa mới thì certificate và fingerprint khác. Điều cần xác minh là **cùng giá trị giữa các biểu diễn**, không phải mọi học viên sinh cùng fingerprint.

Xem chi tiết extension:

```bash
keytool -printcert -v -file lab-root.pem
```

Tìm `BasicConstraints` có `CA:true` và `KeyUsage` chứa `Key_CertSign` theo cách biểu diễn của JDK. Mẫu certificate này còn có `Owner` và `Issuer` tương đương, vì nó tự ký.

### 7.5. Đọc certificate từ keystore chứa private key

```bash
keytool -list -v -alias labroot -keystore lab-root.p12 -storepass:env LAB_CERT_PASS
```

Tìm:

```text
Alias name: labroot
Entry type: PrivateKeyEntry
```

Ngoài ra, certificate bên trong entry phải có **cùng SHA-256 fingerprint** với `lab-root.pem`/`lab-root.der`.

**Cảnh báo:** `PrivateKeyEntry` nghĩa keystore chứa private key. Lệnh `-list` chỉ đọc thông tin; không cấp quyền công khai keystore hoặc đưa mật khẩu vào ticket/chat.

### 7.6. Nhập certificate công khai vào truststore test **riêng**

Sau khi biết chắc certificate này do **chính bạn tạo trong lab**, dùng:

```bash
keytool -importcert -alias labroot -file lab-root.pem -keystore lab-trust.p12 -storetype PKCS12 -storepass:env LAB_CERT_PASS -noprompt
```

Lệnh chỉ tạo/sửa `lab-trust.p12` trong thư mục lab. **Không** thêm `-cacerts` và không đụng hệ thống.

Kiểm tra:

```bash
keytool -list -v -alias labroot -keystore lab-trust.p12 -storepass:env LAB_CERT_PASS
```

Trong lab đã kiểm thử, kết quả hiển thị:

```text
Alias name: labroot
Entry type: trustedCertEntry
```

Dấu vân tay SHA-256 vẫn giống, nhưng **entry type đã đổi**. Truststore test chứa **certificate công khai**, không chứa private key của CA; về mặt tin cậy, nó tạo một điểm neo tin cậy **chỉ cho những ứng dụng thực sự dùng truststore test này**.

**Không bê `-noprompt` sang thao tác import chứng thư lấy từ internet vào production.** Khi quản trị root CA thật, phải kiểm tra fingerprint qua kênh độc lập **trước** khi quyết định thêm trust anchor.

### 7.7. Sơ đồ bốn cách đọc cùng certificate

```text
                       lab-root.p12
             PrivateKeyEntry + certificate
                          |
                       exportcert
                  /                    \
                 v                      v
          lab-root.pem             lab-root.der
              |                         |
              | printcert               | printcert
              v                         v
         SHA256 = F                 SHA256 = F
              |
              | importcert vào lab-trust.p12
              v
         trustedCertEntry
         SHA256 = F
         không có private key
```

**F là fingerprint mới được tạo ngẫu nhiên mỗi lần**, không phải hằng số trong tài liệu. Bốn chỗ phải **cùng F** nếu không có file bị sửa.

## 8. Chương trình Java 17+ để kiểm tra độc lập SHA-256 và entry type

`keytool` là công cụ chính của bài; chương trình bổ sung này dùng **Java SE API chuẩn**, giúp chứng minh fingerprint tính từ X.509 DER certificate, không phải lấy thông tin tùy ý từ tên file.

Nó thực hiện:

1. Đọc certificate từ PEM và DER qua `CertificateFactory`.
2. So sánh bytes DER đã giải mã.
3. Tính `SHA-256(cert.getEncoded())` và kiểm tra độ dài.
4. Kiểm tra self-issued, tự xác minh chữ ký bằng public key, BasicConstraints/KeyUsage.
5. Kiểm tra thời hạn tại thời điểm chạy.
6. Đọc `lab-trust.p12` bằng `KeyStore` và kiểm tra alias là trusted certificate entry, không phải key entry.
7. So fingerprint của truststore certificate với file PEM.

**Lưu file `CertAudit385.java`:**

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HexFormat;

public final class CertAudit385 {
    private static X509Certificate readCertificate(String file) throws Exception {
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }
    }

    private static byte[] sha256(X509Certificate cert) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(cert.getEncoded());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: java CertAudit385 lab-root.pem lab-root.der lab-trust.p12");
        }
        String password = System.getenv("LAB_CERT_PASS");
        if (password == null) {
            throw new IllegalStateException("LAB_CERT_PASS not set");
        }

        X509Certificate pem = readCertificate(args[0]);
        X509Certificate der = readCertificate(args[1]);
        byte[] fingerprint = sha256(pem);
        String formatted = HexFormat.ofDelimiter(":")
                .withUpperCase().formatHex(fingerprint);

        System.out.println("pemAndDerSameBytes=" +
                MessageDigest.isEqual(pem.getEncoded(), der.getEncoded()));
        System.out.println("sha256Bytes=" + fingerprint.length);
        System.out.println("sha256FingerprintCharacters=" + formatted.length());
        System.out.println("sameFingerprintFromBothFiles=" +
                MessageDigest.isEqual(fingerprint, sha256(der)));
        System.out.println("subjectEqualsIssuer=" +
                pem.getSubjectX500Principal().equals(pem.getIssuerX500Principal()));

        pem.verify(pem.getPublicKey());
        System.out.println("selfSignatureVerifies=true");
        System.out.println("caConstraintPresent=" + (pem.getBasicConstraints() >= 0));
        boolean[] usage = pem.getKeyUsage();
        System.out.println("keyCertSignPermitted=" +
                (usage != null && usage.length > 5 && usage[5]));

        pem.checkValidity();
        System.out.println("validNow=true");

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(args[2]))) {
            store.load(in, password.toCharArray());
        }
        X509Certificate trusted = (X509Certificate) store.getCertificate("labroot");
        System.out.println("trustedCertificateEntry=" +
                store.isCertificateEntry("labroot"));
        System.out.println("truststoreCertMatchesFile=" +
                (trusted != null && MessageDigest.isEqual(
                        fingerprint, sha256(trusted))));
        System.out.println("keyEntryInTruststore=" + store.isKeyEntry("labroot"));
    }
}
```

### 8.1. Biên dịch và chạy

Vẫn ở thư mục `cert-lab`, sau khi thực hiện các lệnh `keytool` ở phần 7:

```bash
javac --release 17 -encoding UTF-8 CertAudit385.java
java CertAudit385 lab-root.pem lab-root.der lab-trust.p12
```

Với PowerShell, hai lệnh tương tự. Biến `LAB_CERT_PASS` phải còn tồn tại trong môi trường của tiến trình.

### 8.2. Stdout **đã kiểm thử chính xác** trên OpenJDK 24.0.2

```text
pemAndDerSameBytes=true
sha256Bytes=32
sha256FingerprintCharacters=95
sameFingerprintFromBothFiles=true
subjectEqualsIssuer=true
selfSignatureVerifies=true
caConstraintPresent=true
keyCertSignPermitted=true
validNow=true
trustedCertificateEntry=true
truststoreCertMatchesFile=true
keyEntryInTruststore=false
```

**Vì sao không in SHA-256 cụ thể?** Chứng thư được sinh mới với khóa ngẫu nhiên, nên fingerprint thay đổi ở mỗi lần lab. Chương trình in độ dài fingerprint và quan hệ bằng nhau, để stdout đáng tin, không ép mọi người phải sinh ra cùng khóa.

### 8.3. Diễn giải kết quả chính xác

- `pemAndDerSameBytes=true`: certificate được giải mã từ PEM/DER thành cùng DER bytes.
- `sha256Bytes=32`: SHA-256 digest có 32 byte.
- `sha256FingerprintCharacters=95`: cách viết 32 cặp hex và 31 dấu `:` có 95 ký tự.
- `sameFingerprintFromBothFiles=true`: fingerprint từ hai file giống nhau.
- `subjectEqualsIssuer=true`: đây là certificate **self-issued** theo tên DN.
- `selfSignatureVerifies=true`: kiểm tra chữ ký bằng public key của chính certificate thành công; **không** chứng minh CA này được một tổ chức độc lập tin tưởng.
- `caConstraintPresent=true` và `keyCertSignPermitted=true`: certificate lab có Basic Constraints CA và KeyUsage ký certificate.
- `validNow=true`: certificate lab chưa vượt thời hạn theo đồng hồ runtime; **không** chứng minh chứng thư chưa bị thu hồi hay phù hợp mọi PKIX policy.
- `trustedCertificateEntry=true`: truststore lab chứa entry certificate tin cậy.
- `truststoreCertMatchesFile=true`: đó đúng là certificate đã export.
- `keyEntryInTruststore=false`: alias trong truststore riêng không có private key.

### 8.4. Giới hạn rất quan trọng của demo

Chương trình **không thực hiện** xác minh chuỗi TLS đến một CA công khai, kiểm tra DNS hostname, CRL/OCSP hoặc kiểm tra đầy đủ `PKIXCertPathValidator`. Nó chỉ xác minh vài thuộc tính cụ thể của **chứng thư tự ký trong lab** và độ nhất quán của các bản copy.

Một certificate có thể qua tất cả assertions trong demo mà **không hề là CA public đáng tin**. Đó chính là lý do cần kênh xác minh fingerprint độc lập và trust policy.

Chương trình dùng `java.security.cert.X509Certificate`, `CertificateFactory`, `MessageDigest`, `KeyStore` và `HexFormat` — các API công khai vẫn được hỗ trợ trong Java 17+.

## 9. Kiểm tra certificate của một TLS server bằng `-sslserver`

`keytool` có lệnh:

```bash
keytool -printcert -sslserver example.com:443
```

Lệnh trên **cần kết nối mạng** và có thể thất bại do proxy, DNS, firewall, TLS negotiation hoặc cấu hình server. Nó đọc thông tin certificate/chain mà server trình bày. **Không sử dụng lệnh này như phép kiểm tra TLS trust hoàn chỉnh cho ứng dụng**.

### 9.1. Vì sao không thể lấy fingerprint server bất kỳ làm bằng chứng trust?

Nếu bạn truy cập server qua kết nối bị can thiệp (ví dụ một proxy TLS mà tổ chức không biết), bạn có thể quan sát certificate do proxy đưa ra. Fingerprint lúc đó là hash của certificate **được nhìn thấy**, chưa chắc là certificate mong đợi.

Hãy xác minh độc lập:

1. Chính xác hostname và port bạn cần kiểm tra.
2. Có proxy/SSL inspection hợp lệ trong hạ tầng không.
3. Server trình bày những certificates nào, có thiếu intermediate không.
4. Fingerprint kỳ vọng do chủ sở hữu công bố qua kênh đáng tin là gì.
5. Truststore/SSLContext **của chính ứng dụng** là gì.
6. Kết nối TLS **thực** có xác minh hostname, chain và policy không.

`keytool -printcert -sslserver` giúp chẩn đoán, nhưng **không** thay `HttpsURLConnection`/HTTP client sử dụng JSSE đúng cấu hình.

### 9.2. Không chỉ dựa vào leaf fingerprint khi server rotate

Leaf certificate có thể được gia hạn và thay đổi định kỳ trong khi root/intermediate CA vẫn giữ nguyên. Nếu một quy trình giám sát yêu cầu **leaf fingerprint cố định** mà không có kế hoạch rotation, nó có thể làm hệ thống gián đoạn khi certificate thay mới hợp lệ.

Ngược lại, **CA root fingerprint** cũng có thể thay do chương trình cập nhật root/trust anchor. Chọn thứ cần pin/đối chiếu theo threat model và chính sách quản trị, không mặc nhiên pin mọi certificate vĩnh viễn.

## 10. Đọc certificate chain và phân biệt “issuer” với “được tin”

Giả sử lệnh `-printcert` hiển thị:

```text
Owner: CN=api.example.test
Issuer: CN=Example Intermediate CA
```

Điều này chỉ cho biết leaf tự khai báo **issuer DN**. Để xác định chain hợp lệ, cần:

- có certificate public key của issuer phù hợp;
- xác minh chữ ký leaf bằng issuer public key;
- kiểm tra BasicConstraints/KeyUsage/pathLen của các CA trung gian;
- xác minh từng liên kết lên một **trust anchor** mà ứng dụng chấp nhận;
- kiểm tra thời hạn và chính sách thuật toán;
- kiểm tra hostname/SAN khi dùng cho TLS server;
- kiểm tra revocation theo chính sách được cấu hình.

**Đừng hiểu** “`Issuer` trông giống một CA lớn” thành “certificate được CA tin cậy ký và đã kiểm chứng”.

### 10.1. Root self-signed vs trust anchor

Root CA công khai thường tự ký. Nhưng một trust anchor còn được **xác định bằng chính sách cấu hình tin cậy**, không chỉ bởi certificate có `Subject=Issuer`.

Một certificate self-signed do lab sinh có thể qua `pem.verify(pem.getPublicKey())` mà không được JDK mặc định tin. Khi ta nhập nó vào `lab-trust.p12`, ta đã đưa ra **quyết định tin cậy cục bộ cho truststore riêng**, không làm certificate biến thành một public root được mọi trình duyệt/JDK chấp nhận.

### 10.2. `trustedCertEntry` có nghĩa gì?

Đó là một **entry được truststore sở hữu**. Nếu chương trình dùng truststore ấy theo policy, certificate có thể là trust anchor. Nó **không** có nghĩa certificate đó tồn tại trong mọi truststore Java, cũng không chứng minh private key được giữ an toàn ở CA phát hành.

### 10.3. Trường hợp cross-signing

Một CA intermediate/root có thể có nhiều bản certificate dùng cùng public key nhưng ký bởi các issuer khác nhau hoặc có extensions/thời hạn khác. **Certificate fingerprints khác nhau** không nhất thiết public keys khác nhau.

Khi đối chiếu cần biết bạn đang kiểm tra:

- đúng **certificate DER**;
- public key SPKI;
- subject/issuer;
- trust anchor được chấp nhận;
- chain mà server/app đang sử dụng.

Đừng vội xem fingerprint không khớp là chắc chắn bị tấn công: trước hết xác định có phải cùng loại certificate/chain và cùng bản phát hành hay không; nhưng **không bỏ qua mismatch** nếu đã có expected fingerprint độc lập.

## 11. Lý do Java có thể báo lỗi `PKIX path building failed`

Ví dụ thường gặp:

```text
sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
```

Đây là **ví dụ loại thông báo**, không phải output cố định của lab. Nó có thể liên quan:

- server không gửi đủ intermediate certificates;
- root/intermediate CA cần thiết không có trong **truststore mà ứng dụng dùng**;
- ứng dụng đang dùng một JDK image khác với JDK mà bạn vừa `keytool -list -cacerts`;
- cấu hình `javax.net.ssl.trustStore` trỏ tới file sai hoặc đã thay đổi;
- algorithm constraints/CA distrust policy khiến chain không được chấp nhận;
- certificate không hợp lệ theo thời hạn/chain/path constraints.

**Không giải quyết bằng cách import mọi leaf certificate vào global `cacerts`**. Làm vậy có thể mở rộng trust ngoài ý muốn và che khuất lỗi cấu hình server.

### 11.1. Một quy trình chẩn đoán có trách nhiệm

1. Xác định đúng process/JDK và `java.home` của ứng dụng.
2. Xác định truststore **thực sự** được JSSE/SSLContext sử dụng.
3. Xem chuỗi server với `keytool -printcert -sslserver` (và công cụ TLS khác khi cần).
4. Xem một CA certificate từ file bằng `-printcert -file`.
5. So **SHA-256 fingerprint** với nguồn độc lập đã xác thực.
6. Kiểm tra `-list -v -cacerts -alias ...` hoặc truststore riêng để thấy đúng trust anchor.
7. Kiểm tra thời hạn, SAN, chain, KeyUsage/EKU, algorithm constraints và revocation policy.
8. Khắc phục đúng điểm thiếu: server bổ sung intermediate, sửa cấu hình truststore, hoặc quản trị CA theo quy trình được duyệt.
9. Chạy lại **kết nối TLS có xác minh thật** từ chính ứng dụng.
10. Ghi nhận thay đổi để đánh giá khi CA root hoặc server certificate rotate.

### 11.2. Đừng tắt xác minh TLS

Không sử dụng một `TrustManager` “tin tất cả certificates” hoặc `HostnameVerifier` trả `true` vô điều kiện như “giải pháp” cho lỗi PKIX. Điều đó loại bỏ mục đích bảo vệ của TLS và dễ mở đường cho man-in-the-middle.

`keytool` là công cụ để **xác định đúng chứng thư/cấu hình**, không phải lý do vô hiệu hóa kiểm tra.

## 12. SHA-256 fingerprint và những trường cần lưu trong biên bản kiểm tra

Khi nhóm vận hành cần xác nhận một root CA trước khi thêm vào truststore, một biên bản tối thiểu có thể bao gồm:

| Trường | Ví dụ loại giá trị | Mục đích |
| --- | --- | --- |
| Nguồn file | `partner-root.pem` | Certificate nhận từ đâu? |
| Kênh fingerprint độc lập | Website/tài liệu CA có xác thực | Ai công bố giá trị kỳ vọng? |
| Certificate SHA-256 | 32-byte digest dạng colon-separated hex | So đúng certificate DER |
| Subject DN | `CN=...` | Danh tính được trình bày |
| Issuer DN | `CN=...` | Nơi phát hành được khai báo |
| Serial number | Số hex | Phân biệt bản phát hành |
| Not Before / Not After | Thời hạn | Xác định có còn hiệu lực về thời gian |
| BasicConstraints | `CA:true/false` | Có thể là CA theo extension? |
| KeyUsage | `keyCertSign` hoặc `digitalSignature` | Phù hợp vai trò ký chứng thư/TLS? |
| Signature algorithm/public key | Ví dụ `SHA256withRSA` / RSA 3072 | Có vi phạm policy không? |
| Alias và entry type | `labroot`/`trustedCertEntry` | Đang lưu ở dạng entry nào? |
| Truststore runtime | JDK cacerts hoặc `app-trust.p12` | App thực sự dựa vào store nào? |
| JDK vendor/build | JDK đang chạy | CA defaults/policies theo phiên bản |
| Approval/review | Người phê duyệt + thời điểm | Quản trị trust anchor |

**Đừng lưu private key hoặc keystore password vào biên bản chỉ đọc certificate.** Certificate là thông tin công khai, private key là thông tin bí mật và cần bảo vệ bằng cơ chế riêng.

### 12.1. Không so fingerprint bằng cách bỏ qua phần khác

Hai certificates có SHA-256 khác nhau là **hai DER certificates khác nhau** với xác suất cực cao. Nhưng chứng thư có đúng fingerprint kỳ vọng vẫn cần được dùng **trong đúng mục đích**. Ví dụ root CA phục vụ test không nên tự nhiên trở thành trust anchor cho mọi kết nối production.

### 12.2. Hết hạn, thuật toán yếu, bị distrust

JDK có chính sách security properties như `jdk.certpath.disabledAlgorithms` và cơ chế hạn chế trust đối với một số CA theo release/policy. Certificate **có mặt** trong `cacerts` không có nghĩa ứng dụng sẽ chấp nhận mọi chain chứa nó trong mọi thời điểm.

Đừng dùng `-printcert` như bằng chứng đầy đủ về **trạng thái thu hồi OCSP/CRL**. Revocation checking trong Java phụ thuộc API/cấu hình và policy; phải kiểm tra riêng nếu đây là yêu cầu.

## 13. Những lỗi phổ biến

**Lỗi 1 — “Certificate có `Owner=Trusted Root` nên đáng tin.”**  
Sai. Subject/Owner là metadata; trust cần quyết định độc lập và xác minh fingerprint.

**Lỗi 2 — “`Subject=Issuer` nghĩa đây là root CA đã được công khai tin cậy.”**  
Sai. Bất kỳ ai cũng có thể tạo certificate tự ký.

**Lỗi 3 — “Fingerprint trùng với fingerprint trên cùng trang tải xuống là an toàn.”**  
Không đủ. Trang có thể bị thay thế cả hai; cần kênh xác thực độc lập.

**Lỗi 4 — “SHA1 và SHA256 cùng là độ mạnh bảo mật cho quyết định mới.”**  
Sai. Dùng SHA-256 để so certificate identity theo chính sách hiện hành.

**Lỗi 5 — “Signature algorithm SHA256withRSA chính là SHA256 certificate fingerprint.”**  
Sai. Một cái mô tả chữ ký X.509, cái còn lại là hash của toàn certificate DER.

**Lỗi 6 — “Alias trong keystore chính là DNS hostname của certificate.”**  
Sai. Alias là tên entry, tách biệt subject/SAN/fingerprint.

**Lỗi 7 — “Đọc `-list -cacerts` ở laptop thì server đang dùng cùng cacerts.”**  
Không chắc. JDK vendor/build, container image và truststore override có thể khác.

**Lỗi 8 — “`cacerts` có root nghĩa server TLS luôn hợp lệ.”**  
Sai. Còn chain, SAN, EKU, thời hạn, revocation/policies và lựa chọn truststore của app.

**Lỗi 9 — “`keytool -printcert -file` tự xác nhận CA chain an toàn.”**  
Sai. Đây chủ yếu là lệnh hiển thị nội dung, không thay PKIX validation.

**Lỗi 10 — “PEM và DER của cùng certificate phải là những file byte-identical.”**  
Sai. File encodings khác nhau; certificate DER bytes sau parse có thể giống.

**Lỗi 11 — “Một file `.p12` chỉ chứa certificate công khai.”**  
Sai. Nó có thể chứa private key, secret key hoặc trusted certificate entries.

**Lỗi 12 — “`-exportcert` và xuất keystore là cùng một thao tác.”**  
Sai. `-exportcert` xuất public certificate; sao chép/đưa file keystore có thể làm lộ private keys.

**Lỗi 13 — “Chỉ có leaf certificate là đủ để biết toàn chain.”**  
Không. Cần issuer/intermediate/trust anchor phù hợp và chính sách kiểm tra.

**Lỗi 14 — “Thêm certificate vào global `cacerts` là cách chữa mọi lỗi TLS.”**  
Sai. Việc mở rộng trust phải qua xác minh và phê duyệt; tốt hơn là khắc phục đúng nguyên nhân.

**Lỗi 15 — “`-noprompt` an toàn để tự động import mọi CA.”**  
Sai. Tùy chọn này bỏ tương tác và có thể bỏ qua cơ hội phát hiện certificate đáng ngờ.

**Lỗi 16 — “Kiểm tra SHA-256 là đã kiểm tra hostname của server.”**  
Sai. Fingerprint identity không phải hostname verification.

**Lỗi 17 — “CA root được JEP 319 thêm vào rồi sẽ tồn tại mãi ở mọi JDK.”**  
Sai. Truststore và security policies tiếp tục cập nhật sau Java 10.

**Lỗi 18 — “Certificate lab có chữ ký hợp lệ nghĩa internet cũng tin.”**  
Sai. Nó chỉ tự ký/tự kiểm tra được, còn trust anchor do ứng dụng quyết định.

**Lỗi 19 — “Mật khẩu `changeit` là secret production nên có thể hard-code.”**  
Sai. Nó là giá trị mặc định lịch sử, không thay thế quản lý secret/truststore.

**Lỗi 20 — “Một leaf fingerprint không đổi mãi sẽ an toàn hơn.”**  
Không hẳn. Leaf certificate rotation là bình thường; pinning cần chiến lược phù hợp và khả năng rollout.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `keytool -printcert -file root.pem` có cần keystore password không?  
**Đáp án:** Không, vì đọc trực tiếp public certificate file.

**Câu 2.** Tên command nào liệt kê root CA entries của JDK?  
**Đáp án:** `keytool -list -cacerts`, dùng `-v` và `-alias` để xem chi tiết nếu cần.

**Câu 3.** Có dùng đồng thời `-cacerts` và `-keystore custom.p12` không?  
**Đáp án:** Không. Chọn một nguồn keystore rõ ràng.

**Câu 4.** Đọc SHA-256 fingerprint bằng lệnh nào?  
**Đáp án:** `keytool -printcert -file cert.pem` hoặc `keytool -list -v -keystore store.p12 -alias name`.

**Câu 5.** Vì sao certificate fingerprint của PEM và DER lại trùng?  
**Đáp án:** Khi hai file biểu diễn cùng certificate, DER bytes được giải mã là như nhau.

**Câu 6.** SHA-256 certificate fingerprint có bao nhiêu byte?  
**Đáp án:** 32 byte, tương đương 64 ký tự hex hoặc 95 ký tự nếu có dấu `:` phân cách.

**Câu 7.** Fingerprint certificate có phải hash của public key SPKI không?  
**Đáp án:** Không; hai phép hash lấy dữ liệu đầu vào khác nhau.

**Câu 8.** Một root self-signed đã đủ để mọi Java runtime tin không?  
**Đáp án:** Không. Root cần được cấu hình là trust anchor theo chính sách, và chain phải hợp lệ.

**Câu 9.** `trustedCertEntry` chứa private key không?  
**Đáp án:** Không; đó là certificate entry, khác `PrivateKeyEntry`.

**Câu 10.** `-exportcert -rfc` xuất gì?  
**Đáp án:** Public certificate dạng PEM, không phải private key.

**Câu 11.** Nếu `keytool -printcert -sslserver` hiển thị certificate, app TLS đã xác thực hostname chưa?  
**Đáp án:** Chưa; lệnh này chủ yếu thu/hiển thị dữ liệu để kiểm tra.

**Câu 12.** Vì sao `Not After` chưa qua không đủ chứng minh certificate hợp lệ?  
**Đáp án:** Còn chain/trust, algorithm policy, SAN/hostname, usage và revocation policy.

**Câu 13.** Nếu ứng dụng dùng `javax.net.ssl.trustStore` riêng, có thể chỉ xem `-cacerts` không?  
**Đáp án:** Không. Phải kiểm tra truststore mà ứng dụng thực sự chọn.

**Câu 14.** `keytool -list -v` và `-list -rfc` có dùng đồng thời không?  
**Đáp án:** Không; tài liệu keytool nêu `-v` và `-rfc` loại trừ nhau với `-list`.

**Câu 15.** Cách an toàn để nhập một CA thật là gì?  
**Đáp án:** Xác minh fingerprint qua nguồn độc lập, đánh giá trust scope/policy, được phê duyệt rồi mới import vào truststore thích hợp; kiểm thử TLS thực.

**Câu 16.** Lý do gì khiến hai certificates có cùng public key nhưng fingerprint khác?  
**Đáp án:** Chúng có thể khác serial, issuer, thời hạn, extensions hoặc chữ ký DER.

**Câu 17.** Vì sao trong lab không có SHA-256 cố định để chép?  
**Đáp án:** Mỗi lần tạo keypair/certificate mới, DER certificate thay đổi ngẫu nhiên; chỉ các bản PEM/DER/truststore cùng lượt phải khớp.

**Câu 18.** JEP nào liên quan bộ root CA certificates được tích hợp vào JDK 10?  
**Đáp án:** **JEP 319 — Root Certificates**.

**Câu 19.** Làm sao chứng minh test truststore không mang private key của CA?  
**Đáp án:** `keytool -list -v` cho entry type `trustedCertEntry`; chương trình còn kiểm tra `isKeyEntry("labroot") == false`.

**Câu 20.** Có nên tắt hostname verification để vượt qua lỗi PKIX không?  
**Đáp án:** Không. Phải xác định và khắc phục đúng lỗi chain/trust/hostname.

## 15. Checklist vận hành nhanh

- Xác định **đúng JDK/keytool của ứng dụng**, không dùng nhầm JDK trên host.
- Xác định đúng **certificate file/alias/truststore**, phân biệt root, intermediate, leaf.
- Đọc `keytool -printcert -v -file` hoặc `keytool -list -v ...`.
- Ghi lại **SHA-256 certificate fingerprint** và so với nguồn **độc lập, đã xác thực**.
- Xác nhận entry type `trustedCertEntry`/`PrivateKeyEntry`; không làm lộ private key.
- Kiểm tra `Subject`, `Issuer`, serial, thời hạn, BasicConstraints, KeyUsage/EKU.
- Với TLS server, kiểm tra SAN/hostname, chain, trust anchor và revocation/algorithm policy.
- Kiểm tra cấu hình `cacerts` hoặc truststore riêng **đang được runtime sử dụng**.
- Tránh thêm root vào global `cacerts` nếu không có phê duyệt và nhu cầu rõ ràng.
- Chỉ dùng `-noprompt` trong automation đã xác thực certificate/trust decision.
- Không đặt password thật trong shell history/CI logs; dùng cơ chế quản lý secrets.
- Sau thay đổi root/truststore, chạy lại **kết nối TLS có xác minh thật** của ứng dụng.
- Lập kế hoạch cập nhật root CA, certificate rotation và JDK security updates.

## 16. Ghi nhớ

1. **Java 10/JEP 319** đưa một tập root CA mặc định vào những bản OpenJDK thích hợp; truststore và chính sách tiếp tục thay đổi trên JDK mới.
2. **`keytool -printcert -file`** đọc PEM/DER và hiển thị **SHA-256 certificate fingerprint** mà không cần private key.
3. **`keytool -list -cacerts`** truy cập JDK root truststore; với truststore riêng dùng `-keystore`/`-alias`.
4. **SHA-256 fingerprint = SHA-256 của DER certificate**, không phải SPKI pin, serial number hoặc signature algorithm name.
5. So fingerprint chỉ đáng tin khi có **expected fingerprint từ nguồn độc lập**.
6. **Self-signed ≠ trusted**. Phải quản trị trust anchors, kiểm tra CA extensions và PKIX chain theo chính sách.
7. **`trustedCertEntry` khác `PrivateKeyEntry`**; certificate file PEM/DER không chứa private key, còn keystore PKCS#12 có thể có.
8. `keytool` giúp quan sát certificate, nhưng **không thay toàn bộ TLS chain, hostname, EKU và revocation validation**.
9. **Không sửa `cacerts` bằng cách nhập bừa leaf/root**, không bỏ TLS verification để vượt lỗi.
10. Lab tạo root giả lập và Java 17+ cho kết quả kiểm tra nhất quán mà **không đụng các root certificates trong hệ thống**.

## Tài liệu tham khảo chính thức còn áp dụng

- OpenJDK **JEP 319 — Root Certificates**, triển khai trong Java 10: https://openjdk.org/jeps/319
- Oracle **Java SE 26 — The keytool Command** (các lệnh `-list`, `-printcert`, `-exportcert`, `-importcert`, `-cacerts`, `-storepass:env`): https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html
- Oracle **Java SE 24 — The keytool Command**, tương thích các cú pháp kiểm tra hiện hành: https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html
- Oracle **Java SE 10 — keytool**, bối cảnh cú pháp Java 10 và root certificates: https://docs.oracle.com/javase/10/tools/keytool.htm
- OpenJDK **JDK 10 Release Notes — JEP 319**: https://www.oracle.com/java/technologies/javase/10all-relnotes.html
- Java SE **`X509Certificate`** API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/X509Certificate.html
- Java SE **`KeyStore`** API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html
- Java SE **`CertificateFactory`** API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertificateFactory.html
- Java SE **`MessageDigest`** API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/MessageDigest.html
- Java SE **`HexFormat`** API (Java 17+): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HexFormat.html
- Oracle **Java PKI/CertPath APIs**, `CertPathValidator`/`PKIXParameters`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathValidator.html
