# 13.9 Lập bộ CA thử nghiệm và giữ ranh giới giữa chứng thư thử nghiệm với môi trường thật

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Certificate Authority (CA)**, **root CA**, **chứng thư đầu cuối (leaf/end-entity certificate)**, **Certificate Signing Request (CSR)**, **trust anchor**, **certificate chain** và cơ chế kiểm tra X.509.
2. Dùng **keytool trong JDK 17+** để lập một root CA phục vụ thực hành, sinh khóa server, tạo CSR, cấp chứng thư server có **Subject Alternative Name (SAN)** và **Extended Key Usage (EKU)**, lưu chứng thư vào **PKCS12** và tạo **truststore thử nghiệm riêng biệt**.
3. Phân biệt **chứng thư được CA ký** với **chứng thư đã được một client tin cậy**. Chữ ký hợp lệ chưa đủ: còn phải có trust anchor được cấp quyền tin cậy, chuỗi hợp lệ, thời hạn đúng, hostname đúng và chính sách sử dụng phù hợp.
4. Đọc, kiểm tra chứng thư bằng keytool và dùng **Java CertPathValidator/PKIX** để thử đường dẫn chứng thực tới **duy nhất root CA lab**.
5. Giữ ranh giới không thể nhầm giữa **lab/test** với **production**: không đưa CA thử nghiệm vào cacerts, hệ điều hành, thiết bị người dùng, container production hoặc shared truststore; không dùng private key thử nghiệm trong môi trường thật; không tắt xác thực TLS để vượt lỗi.
6. Thiết kế test âm (untrusted CA, sai hostname, sai EKU, chứng thư hết hạn hoặc bị thay), quy trình hủy/rotation và checklist trước khi triển khai.

**Thông điệp quan trọng:** Tự tạo một CA thử nghiệm là cách tốt để học cơ chế **PKI/X.509/TLS**, nhưng đồng thời tạo ra quyền lực rất lớn: bất kỳ client nào tin CA đó có thể tin những chứng thư mà CA cấp **theo chính sách kiểm tra của client**. Vì vậy CA lab phải có **phạm vi tin cậy riêng, thời hạn ngắn, định danh chỉ dành cho lab và không bao giờ được đẩy sang production**.

## 1. CA làm gì, và điều gì khiến một chứng thư được tin?

Trong PKI, **CA** sở hữu một cặp khóa. Private key của CA dùng để **ký** chứng thư X.509 cho các subject/khóa công khai khác; certificate của CA chứa public key và thông tin nhận dạng. Khi một TLS client nhận chứng thư server, client có thể kiểm tra chữ ký và đường dẫn chứng thực đến một **trust anchor** mà nó đã chủ động cấu hình tin.

~~~text
                       TRUST ANCHOR (được client chọn)
                           Lab Root CA certificate
                           Public key của Lab Root CA
                                      |
                               ký leaf certificate
                                      v
Server key pair ---> CSR ----> Lab Server certificate
(private key chỉ ở server)     SAN=DNS:localhost,IP:127.0.0.1
                               EKU=serverAuth
                                      |
                                  TLS handshake
                                      |
Client kiểm tra:
   chứng thư server phù hợp public/private key đang sử dụng?
   đường dẫn chữ ký có đến CA mà client TIN không?
   còn hạn? extensions và key usage đúng?
   hostname/IP có khớp SAN?
   có vi phạm chính sách trust hoặc revocation không?
~~~

**Tự ký (self-signed)** chỉ nói rằng chứng thư được ký bằng private key tương ứng public key trong chính chứng thư ấy. Nó **không tự được mọi máy tin cậy**. Chỉ khi một client chủ động tin chứng thư CA đó (hoặc cơ chế trust tương đương), nó mới trở thành **trust anchor** cho quá trình xác minh.

### 1.1 “Được ký” khác “được tin”

Giả sử root của lab cấp chứng thư server.example.com. Bằng cách nào đó attacker đưa root lab vào truststore production của một ứng dụng. Khi ấy attacker giữ private key CA lab có thể phát hành chứng thư cho tên miền mà ứng dụng truy cập. Nếu ứng dụng không có kiểm soát khác, **chuỗi cert có thể được xem là tin cậy**, tạo rủi ro giả mạo endpoint/MITM.

Vì thế, **ranh giới truststore** là ranh giới an ninh quan trọng: thêm một root CA không đơn giản là “thêm một file cert cho hết lỗi”, mà là **trao quyền phát hành chứng thư được tin** trong phạm vi sử dụng của truststore đó.

### 1.2 Những thành phần cần phân biệt

| Thành phần | Chức năng | Có private key không? | Có nên đưa vào production? |
| --- | --- | --- | --- |
| **Root CA private key của lab** | Ký các leaf certificate trong bài thực hành | **Có, cực kỳ nhạy cảm** | **Không bao giờ** |
| **Root CA certificate của lab** | Cung cấp public key để kiểm tra chữ ký và có thể làm trust anchor | Không | **Không được cài làm trusted root production** |
| **CSR** | Đề nghị cấp chứng thư, chứa public key và chủ thể đề nghị | Không chứa private key | Chỉ dùng theo luồng cấp chứng thư đã kiểm soát |
| **Leaf private key của lab server** | Server chứng minh quyền giữ khóa trong TLS | Có | Không dùng cho production identity |
| **Leaf certificate của lab** | Gắn public key server với tên/thuộc tính do lab CA chứng nhận | Không | Không phải chứng thư production đáng tin |
| **Server keystore** | Lưu keypair và certificate chain cho server | Thường có private key | Chỉ dùng trong lab |
| **Client truststore riêng** | Chứa root certificate lab được client thực hành chủ động tin | Thường chỉ có public cert | Không được dùng làm truststore chung/prod |

**Keystore và truststore đều có thể dùng PKCS12**. Khác biệt là **vai trò**: server cần khóa định danh, client cần những trust anchor nó có chủ đích tin tưởng.

## 2. Ngôn ngữ X.509 quan trọng trước khi phát hành

### 2.1 BasicConstraints: CA hay end entity?

X.509 extension **BasicConstraints** xác định subject có thể đóng vai CA hay không, kèm tùy chọn path length.

- **Root CA thử nghiệm:** BasicConstraints **CA=true**, đánh dấu **critical** theo chính sách phù hợp. Một CA có thể ký leaf; trong lab này dùng **pathLen=0** để không tạo chuỗi CA trung gian không cần thiết.
- **Server leaf:** BasicConstraints **CA=false**. Nó là end entity, **không được cấp quyền phát hành chứng thư CA**.
- **pathLen=0** là giới hạn số intermediate CA tiếp theo trong đường chứng thực, **không có nghĩa CA không được ký leaf certificate**.

Nếu một leaf có CA=false nhưng lại có KeyUsage keyCertSign, cấu hình là sai về mục đích và không được xem là CA hợp lệ theo profile. Đừng vô tình tạo CA certificate làm certificate server.

### 2.2 KeyUsage và ExtendedKeyUsage

**KeyUsage (KU)** giới hạn các hành vi dùng public key trong chứng thư:

- CA: **keyCertSign**; có thể thêm **cRLSign** nếu thiết kế xử lý danh sách thu hồi.
- TLS server với RSA: thường cần **digitalSignature** (đặc biệt TLS hiện đại); tùy giao thức/cấu hình có thể có **keyEncipherment** cho các trường hợp tương thích legacy.
- Không đặt **keyCertSign** trên leaf.

**ExtendedKeyUsage (EKU)** diễn đạt mục đích ứng dụng ở mức cao hơn. Với leaf của HTTPS server, bài lab dùng:

~~~text
EKU = serverAuth
OID = 1.3.6.1.5.5.7.3.1
~~~

Nếu muốn cấp chứng thư cho client mTLS, EKU **clientAuth** là mục đích khác; không cho rằng mọi leaf đều tự động dùng được để xác thực cả server lẫn client.

### 2.3 Subject Alternative Name và hostname verification

Ngày nay HTTPS client dùng **Subject Alternative Name (SAN)** để kiểm tra danh tính máy chủ theo quy tắc phù hợp. CN của subject **không thay thế** SAN cho một cấu hình TLS hiện đại.

Trong bài lab sẽ cấp leaf với:

~~~text
Subject: CN=localhost, O=Local Training, C=VN
SAN: DNS:localhost, IP:127.0.0.1
EKU: serverAuth
BasicConstraints: CA=false
~~~

Điều này phục vụ truy cập **https://localhost** hoặc **https://127.0.0.1** trong lab tùy server/client cấu hình. **Không thêm SAN của domain công ty thật hoặc domain production**. Nếu hostname bạn truy cập là service.prod.example.com, chứng thư lab cho localhost phải **không** khớp; đừng tắt hostname verification để che lỗi.

### 2.4 Thời hạn, serial number, issuer và trust

Mỗi X.509 certificate có:

- **Subject:** danh tính được chứng nhận, ví dụ CN=localhost; không phải toàn bộ quy tắc kiểm tra hostname.
- **Issuer:** tên CA ký.
- **Validity:** Not Before và Not After, phụ thuộc đồng hồ và chính sách.
- **Serial number:** định danh trong phạm vi issuer.
- **Signature algorithm và chữ ký CA:** dùng để xác nhận certificate bytes được CA ký.
- **Public key:** khóa công khai của subject.
- **Extensions:** SAN, KU, EKU, BasicConstraints, SKI/AKI, policy, CRL/OCSP tùy thiết kế.

**Có chữ ký hợp lệ không đồng nghĩa thuộc một chuỗi chứng thực được tin cậy**. Client cần trust anchor, kiểm tra đường dẫn, thời gian, mục đích, hostname, trạng thái thu hồi theo chính sách và ứng dụng.

## 3. Phạm vi lab và luật cách ly ngay từ đầu

**Mô hình lab dùng trong bài:**

- Một thư mục riêng **ca-lab/**, **không đồng bộ vào repo/CI artifacts**.
- Một root CA tự ký, chỉ phát hành leaf cho **localhost**.
- Root validity **30 ngày**, leaf validity **7 ngày**.
- Khóa RSA **3072 bit**, chữ ký **SHA256withRSA** cho demo, không phụ thuộc công cụ bên ngoài JDK.
- Mọi keystore/truststore do lab tạo dùng **PKCS12**.
- Mật khẩu được nhập tương tác; **không nhúng vào shell history, script, README, Dockerfile, command line**.
- Không gửi bất cứ chứng thư lab nào tới production truststore, **$JAVA_HOME/lib/security/cacerts**, OS/system trust, browser profile chung hoặc service account không thuộc lab.
- Root private key không nằm trong máy/container đang chạy server thật. Bài lab dùng chung thư mục để dễ học; thiết kế thực tế phải tách máy CA và runtime service.
- Không cấp phép public DNS domain, IP công ty hoặc SAN tùy ý từ CSR lạ.

**Giới hạn của lab:** Đây là môi trường học certificate issuance, không phải vận hành một Public CA hay Internal PKI đúng quy mô. Nó **không thiết lập** CRL/OCSP responder, CA audit, certificate transparency, HSM, approval workflow hay high availability. Không xem root của lab là CA production đủ chuẩn chỉ vì keytool đã tạo nó.

## 4. Thực hành bằng keytool JDK 17+: root → CSR → leaf → truststore

Các lệnh **keytool** dưới đây là lệnh đầy đủ, mỗi lệnh nằm trên **một dòng**, nên có thể gõ trong Bash, PowerShell hoặc terminal có keytool trên PATH. Nếu chưa có JDK 17+, cần cài JDK thích hợp; **java -version** và **keytool -help** có thể dùng để kiểm tra công cụ đang chạy.

**Không chạy các lệnh trong thư mục đang chứa keystore production**. Tên file cố ý chứa chữ lab. Không dùng giá trị mật khẩu mẫu cố định trong tài liệu; khi keytool hỏi, hãy nhập mật khẩu đủ mạnh chỉ sử dụng cho lab này. Không cần dùng chung một mật khẩu cho root, server và truststore.

### 4.1 Tạo không gian riêng

~~~bash
mkdir ca-lab
cd ca-lab
~~~

Đảm bảo thư mục nằm ngoài repo/shared drive và có quyền truy cập hạn chế. Các file sắp tạo gồm **lab-root.p12**, **lab-root.pem**, **lab-server.p12**, **lab-server.csr**, **lab-server.pem**, **lab-client-trust.p12**. Khi chạy lại từ đầu nên tạo thư mục lab khác; không overwrite những file đang chứa khóa hoặc chứng thư có giá trị.

### 4.2 Tạo root CA thử nghiệm, không phải server certificate

~~~bash
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Root CA, O=Local Training, C=VN" -validity 30 -ext BC:critical=ca:true,pathlen:0 -ext KU:critical=keyCertSign,cRLSign -keystore lab-root.p12 -storetype PKCS12
~~~

Lệnh sinh một **PrivateKeyEntry** có private key RSA 3072 bit và một **self-signed X.509 root CA certificate** trong lab-root.p12.

Giải thích quan trọng:

- **BC:critical=ca:true,pathlen:0:** thể hiện certificate được dùng làm CA, không cho intermediate CA tiếp theo theo đường chứng thực thông thường.
- **KU:critical=keyCertSign,cRLSign:** root có quyền ký certificate và CRL theo bit KU, nhưng lab **chưa vận hành CRL**, không được coi là có kiểm soát revocation.
- **-validity 30:** tuổi chứng thư root 30 ngày; không có ý nghĩa thời hạn mặc định hợp lệ cho CA production.
- **-sigalg SHA256withRSA:** chỉ định thuật toán ký trong ví dụ.
- **lab-root.p12:** chứa **private key CA**; bảo vệ cẩn thận, không gửi cho client/server và không commit vào Git.

Quan sát root certificate trong keystore:

~~~bash
keytool -list -v -alias lab-root -keystore lab-root.p12 -storetype PKCS12
~~~

Kỳ vọng thấy **Entry type: PrivateKeyEntry**, issuer/subject là root lab, BasicConstraints CA:true và KeyUsage có keyCertSign. Keytool sẽ hiển thị fingerprint, serial và validity cụ thể phụ thuộc vào lần sinh.

### 4.3 Xuất **chỉ chứng thư công khai** của root

~~~bash
keytool -exportcert -rfc -alias lab-root -file lab-root.pem -keystore lab-root.p12 -storetype PKCS12
~~~

**lab-root.pem** là certificate PEM công khai, **không chứa private key**. Nó có thể được phân phối cho **client lab được cấp phép**, sau khi client xác minh fingerprint từ kênh tin cậy. Không nhầm một bản copy PEM bất kỳ với một trust anchor đã xác minh nguồn.

Kiểm tra:

~~~bash
keytool -printcert -file lab-root.pem
~~~

Nhìn vào subject, issuer, validity, BasicConstraints, KU và **SHA-256 fingerprint**. Khi nhập root này vào một truststore, người quản trị cần so sánh fingerprint với giá trị được chuyển qua **kênh xác thực độc lập**, không chỉ tin file vừa được gửi qua một kênh không đáng tin.

### 4.4 Sinh khóa server và chứng thư self-signed tạm thời

~~~bash
keytool -genkeypair -alias lab-server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=localhost, O=Local Training, C=VN" -validity 7 -keystore lab-server.p12 -storetype PKCS12
~~~

Keytool tạo private key và một self-signed certificate tạm thời trong **lab-server.p12**. **Đây chưa phải chứng thư do lab-root ký.** Khi import certificate reply từ lab-root, entry dưới alias lab-server sẽ được cập nhật để mang certificate chain tương ứng.

**Private key server** ở lab-server.p12 phải được giữ trong phạm vi server lab. Bên CA cần biết **CSR**, không cần và không được lấy raw private key server.

### 4.5 Tạo Certificate Signing Request (CSR)

~~~bash
keytool -certreq -alias lab-server -file lab-server.csr -keystore lab-server.p12 -storetype PKCS12
~~~

CSR được ký bằng **private key của lab-server** và mang public key cùng thông tin subject yêu cầu. CSR **không chứa private key server**. Một CA chân chính còn phải kiểm tra requestor có quyền xin những danh tính/SAN nào.

Để xem nội dung CSR:

~~~bash
keytool -printcertreq -file lab-server.csr -v
~~~

**Cảnh báo bảo mật:** Không tự động cấp cho mọi tên miền mà CSR khai báo. Trong bài lab, **CA ký với SAN do chính quy trình cấp chứng thư quy định**, không dùng **-ext honored=all** để chấp nhận toàn bộ extension do một CSR không tin cậy yêu cầu.

### 4.6 CA ký CSR thành leaf cho localhost, có SAN và serverAuth

~~~bash
keytool -gencert -alias lab-root -keystore lab-root.p12 -storetype PKCS12 -infile lab-server.csr -outfile lab-server.pem -rfc -validity 7 -ext BC:critical=ca:false -ext KU:critical=digitalSignature,keyEncipherment -ext EKU=serverAuth -ext SAN=dns:localhost,ip:127.0.0.1
~~~

Điểm quan trọng:

- **-alias lab-root:** dùng private key của CA để ký certificate reply cho subject trong CSR.
- **-rfc:** đầu ra PEM Base64 thay vì DER.
- **-validity 7:** leaf có thời hạn ngắn; root validity nên bao phủ thời hạn leaf trong lab.
- **BC:critical=ca:false:** leaf là end entity, không thể trở thành CA.
- **KU:critical=digitalSignature,keyEncipherment:** ràng buộc mục đích sử dụng public key RSA theo các khả năng được khai báo; TLS hiện đại phụ thuộc digitalSignature.
- **EKU=serverAuth:** đánh dấu mục đích xác thực TLS server.
- **SAN=dns:localhost,ip:127.0.0.1:** danh tính chỉ thuộc local lab, không cấp chứng thư cho domain thật.

**Trong thực tế**, CA cần quy trình xác minh danh tính, giới hạn SAN, quản lý serial, kiểm soát private key, CRL/OCSP và audit. Một keytool gencert local không tạo ra các chức năng vận hành đó.

Kiểm tra leaf đã ký:

~~~bash
keytool -printcert -file lab-server.pem
~~~

Quan sát và so sánh: **Issuer = Lab Root CA**, **Subject = localhost**, SAN có localhost/127.0.0.1, BasicConstraints CA:false, KU và EKU tương ứng.

### 4.7 Thêm root công khai vào server keystore để xây certificate chain

Trước khi nhập reply của leaf, nhập **bản root certificate đã xác minh** vào keystore server, dưới alias khác alias private key:

~~~bash
keytool -importcert -alias lab-root-trust -file lab-root.pem -keystore lab-server.p12 -storetype PKCS12
~~~

Keytool có thể hỏi có tin root certificate này không. **Chỉ trả lời đồng ý sau khi kiểm tra đúng fingerprint lab root**. Trong keystore server dùng để thực hành, bản public certificate này hỗ trợ keytool dựng chain cho leaf. Nó **không** có nghĩa server nên đồng thời dùng keystore identity làm truststore chung.

Sau đó nhập certificate reply vào **đúng alias lab-server**, để thay chứng thư self-signed tạm thời:

~~~bash
keytool -importcert -alias lab-server -file lab-server.pem -keystore lab-server.p12 -storetype PKCS12
~~~

**Thứ tự import quan trọng**: phải có issuer root mà keytool có thể dùng để dựng chain trước khi nhập leaf reply đơn lẻ. Kiểm tra kết quả:

~~~bash
keytool -list -v -alias lab-server -keystore lab-server.p12 -storetype PKCS12
~~~

Kỳ vọng là **PrivateKeyEntry** với **certificate chain length = 2** trong bài lab một root + một leaf: chứng thư đầu là lab-server do root ký; chứng thư tiếp theo là root CA. Kết quả số lượng/format có thể phụ thuộc vào cách import hoặc provider; nếu không thấy chain đúng, phải chẩn đoán thay vì bỏ qua kiểm tra.

**Không copy lab-root.p12 sang máy server**. Server chỉ cần **private key của chính server** và public cert chain; CA signing key phải tách biệt.

### 4.8 Lập truststore riêng cho client thử nghiệm

~~~bash
keytool -importcert -alias lab-root-trust -file lab-root.pem -keystore lab-client-trust.p12 -storetype PKCS12
~~~

Nếu truststore chưa tồn tại, keytool có thể tạo file mới và hỏi mật khẩu. Khi hỏi có tin cert không, chỉ xác nhận sau khi xem và đối chiếu SHA-256 fingerprint của lab-root.pem qua kênh độc lập.

Kiểm tra:

~~~bash
keytool -list -v -keystore lab-client-trust.p12 -storetype PKCS12
~~~

**Kỳ vọng:** truststore có **TrustedCertificateEntry** cho alias lab-root-trust, chứa đúng root CA public certificate, **không chứa private key** và **không chứa certificate root bất kỳ khác**. Giữ truststore này độc lập với production và với truststore chung của doanh nghiệp.

### 4.9 Danh sách file cuối cùng

| File | Có gì? | Ai có thể dùng? | Quy tắc bảo vệ |
| --- | --- | --- | --- |
| **lab-root.p12** | Root CA private key + root certificate | Chỉ người vận hành CA lab | Giữ bí mật, không ship sang client/server/production |
| **lab-root.pem** | Root CA public certificate | Client lab sau xác minh fingerprint | Không được cài làm root trusted toàn máy |
| **lab-server.p12** | Server private key + leaf cert chain (và root trusted entry phục vụ dựng chain) | Chỉ server lab | Hạn chế quyền file/password |
| **lab-server.csr** | CSR với public key/subject | CA lab | Không chứa private key, vẫn phải xác minh requestor/SAN |
| **lab-server.pem** | Leaf public certificate do root lab ký | Client/server lab | Không bí mật nhưng không chứng minh tự tin cậy |
| **lab-client-trust.p12** | TrustedCertificateEntry của root lab | Chỉ client tiến trình lab | Không thay cacerts/OS trust store |

**Tuyệt đối không** đưa lab-root.p12 vào nơi có ứng dụng production. Root private key là tài sản nhạy cảm nhất trong mô hình này vì nó có khả năng cấp chứng thư mới được client tin.

## 5. Java 17+: đọc và xác minh đường dẫn tới đúng CA của lab

Lệnh keytool cho thấy nội dung store và certificate, nhưng để hiểu JCA, hãy xây một chương trình đọc hai file đã tạo và chạy **PKIX certificate path validation**.

Chương trình **LabCaCheck.java** này:

- Nhập mật khẩu keystore và truststore qua **Console.readPassword()** (không để mật khẩu trong command line).
- Load **lab-server.p12** và **lab-client-trust.p12** theo PKCS12.
- Lấy leaf từ alias lab-server và root certificate từ alias lab-root-trust.
- Kiểm tra root có BasicConstraints CA=true, leaf có CA=false, leaf có EKU serverAuth và có SAN DNS localhost.
- Gọi **CertPathValidator.getInstance("PKIX")** với **duy nhất root certificate lab** làm TrustAnchor.
- **Không** tắt hoặc thay thế PKIX signature/path validation; chỉ đặt **revocationEnabled(false)** trong lab vì ví dụ chưa triển khai CRL/OCSP.
- Không dùng truststore mặc định/cacerts và không cấp trust rộng cho toàn bộ JVM.

**Đây là ví dụ thực hành certificate path; không phải một TLS client hoàn chỉnh.** Kiểm tra SAN bằng tay ở đây chỉ chứng minh dữ liệu SAN tồn tại, không thay thế bộ quy tắc hostname verification của HTTPS; server certificate sẽ còn phải được TLS stack kiểm tra theo endpoint thật.

Tệp **LabCaCheck.java**:

~~~java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public class LabCaCheck {
    private static KeyStore openPkcs12(
            String filename, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(Path.of(filename))) {
            store.load(input, password);
        }
        return store;
    }

    private static boolean hasLocalhostSan(X509Certificate certificate)
            throws Exception {
        Collection<List<?>> san = certificate.getSubjectAlternativeNames();
        if (san == null) {
            return false;
        }
        for (List<?> item : san) {
            // SAN type 2 = dNSName
            if (Integer.valueOf(2).equals(item.get(0))
                    && "localhost".equalsIgnoreCase(
                            String.valueOf(item.get(1)))) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                "Run from an interactive terminal (Console required)");
        }

        char[] serverPassword =
                console.readPassword("Lab server keystore password: ");
        char[] trustPassword =
                console.readPassword("Lab client truststore password: ");
        if (serverPassword == null || trustPassword == null) {
            throw new IllegalStateException("Password input aborted");
        }

        try {
            KeyStore server = openPkcs12(
                    "lab-server.p12", serverPassword);
            KeyStore trust = openPkcs12(
                    "lab-client-trust.p12", trustPassword);

            X509Certificate leaf = (X509Certificate)
                    server.getCertificate("lab-server");
            X509Certificate root = (X509Certificate)
                    trust.getCertificate("lab-root-trust");

            if (leaf == null || root == null) {
                throw new IllegalStateException(
                    "Required lab certificate alias missing");
            }

            leaf.checkValidity();
            root.checkValidity();

            boolean rootIsCa = root.getBasicConstraints() >= 0;
            boolean leafIsEndEntity = leaf.getBasicConstraints() == -1;
            List<String> eku = leaf.getExtendedKeyUsage();
            boolean serverAuth = eku != null &&
                    eku.contains("1.3.6.1.5.5.7.3.1");
            boolean localhostSan = hasLocalhostSan(leaf);

            System.out.println("Root is CA: " + rootIsCa);
            System.out.println(
                    "Leaf is end entity: " + leafIsEndEntity);
            System.out.println(
                    "Leaf allows serverAuth: " + serverAuth);
            System.out.println(
                    "Leaf SAN includes localhost: " + localhostSan);

            if (!rootIsCa || !leafIsEndEntity
                    || !serverAuth || !localhostSan) {
                throw new SecurityException(
                    "Lab certificate extensions do not match policy");
            }

            CertificateFactory factory =
                    CertificateFactory.getInstance("X.509");
            CertPath path = factory.generateCertPath(List.of(leaf));

            PKIXParameters parameters = new PKIXParameters(
                    Set.of(new TrustAnchor(root, null)));

            // Lab chỉ kiểm tra chain; CHƯA vận hành CRL/OCSP.
            // Production phải cấu hình revocation theo PKI policy.
            parameters.setRevocationEnabled(false);

            CertPathValidator.getInstance("PKIX")
                    .validate(path, parameters);
            System.out.println("PKIX chain to lab root: VALID");
        } finally {
            Arrays.fill(serverPassword, '\0');
            Arrays.fill(trustPassword, '\0');
        }
    }
}
~~~

Biên dịch và chạy **từ thư mục ca-lab** sau khi tạo các file ở mục 4:

~~~bash
javac -encoding UTF-8 LabCaCheck.java
java LabCaCheck
~~~

Chương trình hỏi hai mật khẩu tương tác. Nếu các file/alias/extension/chain đã đúng và chứng thư chưa hết hạn, phần **stdout sau hai lời nhắc** sẽ là:

~~~text
Root is CA: true
Leaf is end entity: true
Leaf allows serverAuth: true
Leaf SAN includes localhost: true
PKIX chain to lab root: VALID
~~~

Chương trình chủ động **ném exception** khi password sai, không thấy alias, certificate hết hạn, profile không phù hợp hoặc đường dẫn PKIX không xác minh được. Đây là hành vi **fail closed**, tốt hơn trả true trong mọi trường hợp.

### 5.1 Tại sao CertPath chỉ chứa leaf?

Certificate path **không cần nhét root trust anchor vào danh sách certificate cần chứng minh**; root đã được khai báo riêng qua **PKIXParameters(Set<TrustAnchor>)**. Lab này không có intermediate CA, nên đường dẫn chỉ có **leaf**. Với PKI nhiều cấp, path phải có các intermediate đúng thứ tự hoặc dùng CertPathBuilder phù hợp để tìm chain.

**TrustAnchor là đầu vào được ứng dụng tin từ trước**. Đưa bất kỳ root certificate do mạng gửi vào Set.of(new TrustAnchor(...)) mà không xác minh nguồn **sẽ phá ranh giới trust**. Trong ví dụ, root được load từ truststore riêng đã được cấp quyền và kiểm tra fingerprint.

### 5.2 Vì sao revocationEnabled(false) chỉ chấp nhận trong lab?

Chứng thư có thể cần bị thu hồi trước NotAfter do private key bị lộ, server đã nghỉ hoạt động hoặc CA phát hiện cấp sai. Trong PKI production, kiểm tra thu hồi theo chính sách có thể dùng **CRL, OCSP, cơ chế TLS được triển khai phù hợp và kiểm soát vòng đời**.

Ví dụ lab **không cung cấp CRL/OCSP**, nên nó cố ý tắt revocation trong chương trình chỉ để tập trung vào chain/signature/path validation. **Không sao chép dòng này làm mặc định bảo mật production**, và cũng không cho rằng bật một boolean là đủ nếu PKI không có cơ chế trạng thái thu hồi đúng.

### 5.3 Code có xác minh hostname đầy đủ chưa?

**Chưa.** Hàm hasLocalhostSan chỉ kiểm tra **một SAN DNS** đúng với mục tiêu lab. Nó **không** thực hiện đầy đủ các quy tắc HTTPS hostname verification (wildcards, IP SAN, IDN, normalization, policy). Khi dùng HTTPS, cần để **HTTPS/TLS library chính thống** xác minh hostname. Nếu tự dùng SSLSocket, phải cấu hình endpoint identification phù hợp.

## 6. Dùng truststore lab trong JSSE mà không mở rộng trust cho production

### 6.1 Không đưa root lab vào cacerts

**Không chạy** các biến thể nhập root lab với mục tiêu:

~~~text
$JAVA_HOME/lib/security/cacerts
keytool -importcert -cacerts ...
Windows Trusted Root Certification Authorities
macOS System Keychain trust
Browser/OS trust profile dùng chung
Container image hoặc trust bundle production
~~~

Các dòng trên là **danh sách nơi cấm đưa CA lab vào**, không phải lệnh chạy. Việc nhập root vào truststore chung sẽ khiến nhiều ứng dụng ngoài lab **có thể** tin các leaf do CA lab phát hành. Đây là loại thay đổi có thể vượt quá phạm vi thử nghiệm và tạo rủi ro MITM.

**Điểm phân biệt:** Root certificate công khai không nhất thiết bí mật, nhưng **đặt nó vào danh sách trusted roots** là một hành động cấp quyền tin cậy có tác động bảo mật lớn.

### 6.2 Cách dùng per-process: chỉ đưa truststore cho ứng dụng lab

Đối với một tiến trình Java chuyên để học TLS, có thể đặt **javax.net.ssl.trustStore** trỏ đến **lab-client-trust.p12**, kèm **javax.net.ssl.trustStoreType=PKCS12**, theo cấu hình test chuyên biệt. Nhưng **không đưa password plaintext vào command line hoặc log** trong hệ thống thật. Cách có kiểm soát hơn là **nạp truststore bằng Java và tạo SSLContext riêng** cho HTTP/TLS client lab.

Mẫu Java sau **không phải chương trình độc lập**: giả định biến **labTrust** đã load PKCS12 bằng mật khẩu đúng, và URL lab endpoint có TLS server đang chạy.

~~~java
TrustManagerFactory factory = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
factory.init(labTrust);

SSLContext labTls = SSLContext.getInstance("TLS");
labTls.init(null, factory.getTrustManagers(), null);

HttpsURLConnection conn = (HttpsURLConnection)
        new URL("https://localhost:8443/").openConnection();
conn.setSSLSocketFactory(labTls.getSocketFactory());
conn.connect();
// Không thay HostnameVerifier; HTTPS tiếp tục kiểm tra hostname.
~~~

Để biên dịch đoạn trên thành chương trình, cần các import **javax.net.ssl.TrustManagerFactory**, **javax.net.ssl.SSLContext**, **javax.net.ssl.HttpsURLConnection**, **java.net.URL** và phần nạp labTrust. Mẫu này minh họa **SSLContext cho riêng một connection lab**; không tạo kết nối nếu chưa có server TLS lab nghe ở cổng 8443.

**Không làm điều sau:**

~~~java
// ANTI-PATTERN: Không dùng trong lab hoặc production.
HttpsURLConnection.setDefaultHostnameVerifier(
        (hostname, session) -> true);
~~~

Thao tác đó tắt kiểm tra danh tính host cho nhiều kết nối của lớp API, làm mất một lớp bảo vệ quan trọng. Một “trust-all X509TrustManager” cũng nguy hiểm tương tự. **Sửa lỗi certificate bằng cách thêm đúng root CA vào truststore lab được cấp phép**, không bằng cách bỏ xác thực.

### 6.3 Cần nhớ: truststore và hostname validation là hai bước khác nhau

Ngay cả khi **PKIX path** đúng:

- Nếu client truy cập **https://service.company.example** nhưng cert chỉ có SAN=localhost, **hostname phải bị từ chối**.
- Nếu cert có SAN đúng nhưng không chain tới root mà client tin, **path validation phải thất bại**.
- Nếu cert hết hạn hoặc chưa có hiệu lực, **time validation phải thất bại**.
- Nếu EKU/KU không phù hợp hoặc TLS stack không chấp nhận thuật toán/chữ ký, **handshake có thể thất bại**.
- Nếu kiểm tra thu hồi được yêu cầu nhưng không thể thực hiện đúng theo policy, xử lý phải theo chính sách; không âm thầm bỏ qua.

Không nhầm “tôi có thể in ra certificate” với “TLS đã xác thực đúng đối tác”.

### 6.4 Keystore server và truststore client không nên tráo vai trò

Một server cần **KeyManagerFactory** truy cập private key và chain để chứng minh danh tính với TLS peer. Client cần **TrustManagerFactory** với CA roots/anchors để kiểm tra chứng chỉ server. Trong **mutual TLS (mTLS)**, cả hai phía có thể vừa có identity keystore vừa có truststore, nhưng trách nhiệm và quyền khác nhau.

Không nên dùng **lab-root.p12** làm server keystore: như vậy server nắm **CA signing private key**, tạo rủi ro rất lớn. Server chỉ dùng lab-server.p12 chứa private key của **leaf server**. Client chỉ nhận lab-root.pem/lab-client-trust.p12, **không nhận private key server/CA**.

## 7. Bộ kiểm thử âm để chứng minh ranh giới thực sự tồn tại

Một CA lab hoàn thành bài không phải vì “có file và chain”, mà vì **chỉ client lab được phép tin nó; các đối tượng không được phép vẫn phải từ chối**.

| Tình huống | Kết quả kỳ vọng | Điểm được kiểm chứng |
| --- | --- | --- |
| Client lab dùng đúng truststore lab và kết nối tới localhost của server lab | Handshake thành công nếu server/protocol cấu hình đúng | CA trust + SAN + key usage + thời gian |
| Client khác dùng truststore mặc định không chứa lab root | **Không tin được lab server certificate** | Không rò trust sang phạm vi ngoài lab |
| Client lab truy cập server bằng hostname không có trong SAN | **Từ chối hostname** | Không tắt hostname verification |
| Client lab tin một root test khác nhưng không tin root bài này | **Từ chối chain** | Trust anchor không phải bất kỳ self-signed cert nào |
| Thay leaf bằng cert ký bởi key không thuộc root lab | **Từ chối path** | Chữ ký và đường dẫn phải xác minh |
| Đổi byte trong nội dung chứng thư đã ký | **Từ chối** | Không thể sửa cert mà không phá chữ ký |
| Leaf hết hạn, chưa tới NotBefore hoặc đồng hồ sai đáng kể | **Từ chối theo chính sách** | Kiểm tra validity |
| Leaf thiếu EKU serverAuth khi policy yêu cầu | **Từ chối** | Kiểm tra mục đích |
| Leaf CA=true dùng làm server identity | **Không dùng cho lab server** | Phân biệt CA và end entity |
| Root CA private key xuất hiện trong container/app runtime | **Lỗi kiến trúc phải sửa** | CA signing key không phân phối |
| Có người đề nghị nhập root lab vào production cacerts | **Từ chối thay đổi** | Chặn mở rộng trust ngoài phạm vi |
| Certificate bị thu hồi nhưng vẫn còn hạn | Phải xử lý qua revocation policy khi production | Validity date không thay thế revocation |
| Gỡ truststore lab khỏi tiến trình lab | Lab certificate không còn được tin nếu không có trust từ nơi khác | Trust có thể được thu hồi theo phạm vi |

**Quan trọng:** Để làm test “truststore mặc định không tin CA lab”, phải xác định môi trường thật chưa cài CA lab trước đó. Không thể khẳng định mọi máy đều từ chối nếu CA lab đã bị import vào truststore chung từ một lần thử trước.

### 7.1 Kiểm thử danh tính sai không phải lý do để bỏ HTTPS

Một lỗi quen thuộc:

~~~text
SSLHandshakeException: PKIX path building failed
                   |
Developer: "Chắc chứng thư tự ký, bật trust-all thôi"
                   |
           Tất cả endpoint giả cũng có thể được chấp nhận
~~~

Cách sửa đúng:

1. Phân loại lỗi: **untrusted issuer**, **hostname mismatch**, **expired cert**, **EKU/KU mismatch**, **chain thiếu**, **sai key**, **revocation**.
2. Với **CA lab**, kiểm tra file truststore của **duy nhất client test**, xác minh fingerprint.
3. Với domain production, dùng chứng thư/chains được CA tin cậy theo chính sách production; **không đưa CA lab vào production để chữa lỗi**.
4. Giữ hostname verification, PKIX path validation và TLS phiên bản/cipher suites phù hợp.
5. Tạo test âm để bảo đảm sửa lỗi không làm mở rộng trust ngoài ý muốn.

### 7.2 Không cấp SAN tùy ý theo CSR

CSR chứng minh quyền kiểm soát **private key của keypair đang yêu cầu** thông qua chữ ký CSR, **không tự chứng minh quyền sở hữu DNS name/IP**. Nếu CA cứ chấp nhận -ext honored=all và bất kỳ SAN client đòi hỏi, nó có thể ký cho tên miền không thuộc phạm vi lab.

Trong bài, CA ký với SAN **localhost/127.0.0.1** bằng lệnh -gencert được quản trị rõ. Một CA nội bộ thật phải có quy trình kiểm tra danh tính, phê duyệt domain/namespace và giới hạn cấu hình issuer.

## 8. Những ranh giới buộc phải giữ giữa test và production

### 8.1 Tách biệt key material

**Không dùng cùng khóa CA hoặc leaf** giữa lab và production.

- **Lab root private key** chỉ tồn tại trong kho/tài khoản lab được phép.
- **Production CA/private key** phải được cấp phát qua CA/KMS/HSM/quy trình được phê duyệt, không lấy từ bài tập.
- Không đặt lab root key trong source, environment variable chia sẻ, artifact CI, Docker image hoặc backup production.
- Nếu cần demo mTLS qua nhiều nhóm, dùng **CA riêng theo môi trường/team hoặc namespace được phê duyệt**, không dựng một lab root toàn doanh nghiệp.

### 8.2 Tách biệt trust anchor và truststore

**Truststore production không chứa lab root**. Client test chỉ tin lab root trong phạm vi runtime test; tiến trình production chỉ dùng roots theo chính sách production.

Một truststore tách file nhưng được mount vào mọi service vẫn là **truststore chung về mặt tác động**. Cần tách cả **đường triển khai, quyền, tài khoản, CI/CD variables, container mounts và môi trường runtime**.

### 8.3 Tách biệt tên định danh và hạ tầng

Chỉ dùng **localhost, loopback hoặc DNS namespace được tổ chức dành riêng cho test**. Không đặt SAN là public company domain, không tạo root với tên giống CA thật, không cấp subject có vẻ như production để dễ copy nhầm.

Đặt tên file có prefix rõ:

~~~text
lab-root.p12
lab-root.pem
lab-server.p12
lab-server.csr
lab-server.pem
lab-client-trust.p12
~~~

Tên file chỉ là **tín hiệu vận hành**, không phải hàng rào bảo mật. Chặn rò rỉ thực tế bằng IAM, policy, review và kiểm thử truststore.

### 8.4 Thời hạn ngắn không thay thế giới hạn quyền

Certificate leaf sống 7 ngày vẫn có thể được lạm dụng nếu client production đã tin lab root. Thời hạn ngắn làm giảm thời gian rủi ro nhưng **không triệt tiêu khả năng giả mạo** trước khi hết hạn.

Root hết hạn 30 ngày cũng không bảo vệ trước mọi lỗ hổng vận hành, đặc biệt khi process không kiểm tra đúng policy hoặc vẫn giữ trust anchor cũ. Cần quản lý hiệu lực, thu hồi trust, xóa deployment sai và giám sát.

### 8.5 Không biến chứng thư lab thành production bằng cách import

**Quy trình hợp lệ để đi production không phải:**

~~~text
lab-root.pem
       |
import vào $JAVA_HOME/lib/security/cacerts
       |
"Prod dùng được"  <- LỖI PHÂN TÁCH TRUST
~~~

**Quy trình đúng:**

~~~text
Tài liệu/prototype lab
       |
Rà soát yêu cầu PKI production
       |
Xin/cấp key và certificate qua CA được phép
       |
Xác minh danh tính, SAN, EKU, chain, validity
       |
Cấp trust theo production policy
       |
Kiểm thử, audit, rotation và giám sát
~~~

Đảm bảo production không thừa hưởng lab root dưới dạng image layer, mounted volume, keystore, secret, env var hoặc config bundle.

## 9. Thu hồi, rotation và kết thúc lab

### 9.1 Khác nhau giữa xóa leaf và thu hồi trust root

Nếu chỉ xóa lab-server.p12, client lab vẫn tin root và root private key còn có thể cấp một leaf mới. **Muốn ngừng tin toàn bộ CA lab**, phải **gỡ root khỏi truststore của tất cả client lab đã cấp quyền** và thu hồi quyền phân phối truststore.

Nếu root key bị lộ, không thể “đổi password PKCS12” rồi xem mọi chứng thư CA đã cấp vẫn an toàn. Phải **ngừng tin root đó**, xây root mới nếu còn cần lab, cấp lại leaf, cập nhật truststore và đánh giá phạm vi ảnh hưởng.

### 9.2 Thu hồi chứng thư và kiểm tra trạng thái

**CRL và OCSP** là các cơ chế thường gặp để công bố/kiểm tra trạng thái certificate. Một CA lab keytool tạo bằng lệnh trên **không tự vận hành** cơ chế revocation. KeyUsage cRLSign chỉ mô tả **khả năng/quyền dùng khóa để ký CRL**, không tự tạo CRL.

Đối với production, cần chính sách rõ: có kiểm tra trạng thái hay không, responder/CRL ở đâu, hành vi khi offline, log và SLA thu hồi. Đừng dùng **PKIXParameters.setRevocationEnabled(false)** từ ví dụ lab để mặc định bỏ qua revocation trong hệ thống thật.

### 9.3 Checklist dọn dẹp sau bài học

1. Dừng tiến trình TLS server/client của lab.
2. Xác minh **không có CA lab** trong cacerts, OS trust, browser profile chung, image hoặc deployment production.
3. Thu hồi/cắt quyền truy cập tới truststore lab khi không còn dùng.
4. Xóa hoặc lưu trữ có kiểm soát **lab-root.p12/lab-server.p12**, password/backup liên quan theo chính sách tổ chức. Không upload file khóa vào ticket/chat.
5. Gỡ config per-process/truststore mount đã dùng để chạy bài.
6. Kiểm tra không còn môi trường test đang dùng certificate hết hạn/hỏng như một lý do để tắt TLS verification.
7. Nếu đã vô tình đưa root lab vào production trust, coi đây là **sự cố bảo mật cần xử lý**, lập danh sách hệ thống bị ảnh hưởng, loại root, luân chuyển thông tin cần thiết và đánh giá rủi ro giả mạo.

**Lưu ý:** Không xóa bừa cacerts hoặc truststore chung để “dọn lab”; chỉ gỡ đúng root lab **nếu đã được cài và theo quy trình thay đổi được cho phép**.

## 10. Những lỗi thường gặp cần tránh

1. **“CA do keytool tạo nên mặc nhiên được tất cả Java client tin.”** Sai: self-signed root chưa có trust anchor trong client.
2. **“Chỉ cần chữ ký leaf đúng là TLS an toàn.”** Sai: còn trust anchor, hostname, EKU/KU, thời gian, thuật toán, trạng thái thu hồi và policy.
3. **“Leaf CN=localhost là đủ, không cần SAN.”** Không phù hợp với HTTPS hostname verification hiện đại; cung cấp SAN đúng kiểu DNS/IP.
4. **“Root CA có thể dùng làm server identity.”** Không: server cần leaf private key/cert đúng mục đích; không đưa CA signing key vào server.
5. **“Root CA cho lab đã nằm trong truststore thì cho production dùng chung để tiện test.”** Sai nghiêm trọng: mở rộng quyền cấp chứng thư được tin.
6. **“Mật khẩu CA ngắn vì chỉ dùng 7 ngày không sao.”** Sai: CA signing key vẫn có thể bị lạm dụng và bị dò offline nếu file bị sao chép.
7. **“CSR đã yêu cầu SAN nào thì CA bắt buộc ký SAN đó.”** Sai: CA phải kiểm tra và quyết định cấp danh tính.
8. **“Đặt CA=true trên leaf để tiện dùng nhiều chỗ.”** Sai: làm sai ranh giới CA/end entity.
9. **“Có cRLSign nghĩa là đã tự động kiểm tra CRL.”** Sai: cần cơ chế phát hành và kiểm tra trạng thái.
10. **“PKIX demo không bật revocation, vậy production cũng tắt.”** Sai: demo không triển khai CRL/OCSP; production phải theo policy.
11. **“Dùng trust-all giải quyết lỗi SSLHandshakeException nhanh mà không ảnh hưởng bảo mật.”** Sai: bỏ xác minh identity/trust.
12. **“HostnameVerifier trả true mọi nơi là hợp lý trên localhost.”** Sai: dễ rò vào runtime khác và làm mất bảo vệ.
13. **“Nhập lab-root.pem vào cacerts chỉ ảnh hưởng app của tôi.”** Sai: có thể ảnh hưởng mọi app dùng kho trust đó.
14. **“Private key CA có thể copy vào server vì nó cùng một nhóm test.”** Sai: server bị chiếm sẽ trao cho attacker quyền phát hành certificate.
15. **“Dùng root validity 30 ngày bảo đảm root an toàn.”** Sai: expiry không giải quyết việc root key bị lộ trước khi hết hạn.
16. **“Tên file demo.p12 nói lên đây là test, không thể dùng nhầm.”** Sai: phải dùng kiểm soát IAM/deployment/trust policy.
17. **“Đã import leaf reply nên không cần kiểm tra chain.”** Sai: xác minh alias, chain, issuer, SAN, EKU và signature.
18. **“Một máy tin CA lab nghĩa là một máy khác cũng tin.”** Sai: trust configuration nằm tại từng runtime/system/profile.
19. **“Có thể dùng cùng root lab để ký cert cho domain production nhằm test staging.”** Sai: cấp theo namespace test và quy trình được phê duyệt.
20. **“Certificate hết hạn thì không cần gỡ trust root.”** Sai: root được tin vẫn có thể có tác dụng đối với certificate khác nếu còn hợp lệ hoặc các client có chính sách xử lý khác.

## 11. Bài tập tự kiểm tra

**Câu 1.** Một root CA self-signed có tự trở thành trusted root trên mọi Java runtime không?

**Trả lời:** Không. Client phải được cấp quyền tin một trust anchor xác thực nguồn gốc; tự ký không tự tạo trust.

**Câu 2.** Tại sao truststore lab phải tách khỏi cacerts hoặc truststore production?

**Trả lời:** Vì thêm root lab vào truststore sản xuất cho phép client production tin các cert do CA lab phát hành trong phạm vi quy tắc xác minh, tạo bề mặt giả mạo endpoint.

**Câu 3.** CA lab khác leaf server ở BasicConstraints và KeyUsage thế nào?

**Trả lời:** CA cần CA=true và keyCertSign phù hợp; leaf cần CA=false và key usage/EKU phù hợp với TLS server, không có quyền ký chứng thư CA.

**Câu 4.** Trong bài, tại sao root có pathLen=0 mà vẫn ký được leaf?

**Trả lời:** pathLen giới hạn số intermediate CA không self-issued theo sau CA trong một certification path; nó không chặn cấp end-entity certificate.

**Câu 5.** Chứng thư server có CN=localhost nhưng SAN chỉ chứa địa chỉ khác; HTTPS đến localhost có nên được chấp nhận không?

**Trả lời:** Không theo chính sách hostname validation hiện đại. Phải có SAN DNS:localhost phù hợp và trust/path vẫn phải đúng.

**Câu 6.** CSR chứa SAN của domain thật có tự chứng minh quyền sở hữu domain đó không?

**Trả lời:** Không. Chữ ký CSR chỉ thể hiện quyền giữ private key CSR; CA phải xác minh quyền sở hữu/tên trước khi phát hành.

**Câu 7.** Keytool tạo server keystore với self-signed certificate. Khi nào nó có chain root→leaf?

**Trả lời:** Khi CA ký CSR, root public certificate được import để dựng chain và certificate reply được import vào đúng alias private key, rồi kiểm tra chain.

**Câu 8.** Trong Java code, việc đưa lab root vào TrustAnchor mang ý nghĩa gì?

**Trả lời:** Ứng dụng chủ động tin CA đó; PKIX validator kiểm tra đường dẫn tới anchor. Không thể dùng root tùy ý lấy từ mạng mà không xác minh danh tính/fingerprint.

**Câu 9.** Lab chưa có CRL/OCSP nên setRevocationEnabled(false). Điều này có chứng minh revocation an toàn không?

**Trả lời:** Không. Đó là giới hạn cố ý của lab; production cần vận hành revocation theo policy và đánh giá hành vi khi dịch vụ trạng thái lỗi.

**Câu 10.** Nếu CA private key bị lộ, chỉ thay store password là đủ chưa?

**Trả lời:** Chưa. Kẻ tấn công có thể có private key và phát hành certificate. Cần ngừng tin CA bị lộ, cấp CA/leaf mới và đánh giá sự cố.

**Câu 11.** Đã có lab-root.pem là client có thể dùng nó như identity keystore không?

**Trả lời:** Không. PEM public root certificate không có private key; client identity (nếu mTLS) cần private key và cert chain riêng.

**Câu 12.** Một HTTPS client truy cập localhost nhưng truststore sai, có nên tắt certificate verification không?

**Trả lời:** Không. Phải tải đúng truststore lab, xác minh root fingerprint, chain, SAN và chính sách TLS; fail closed nếu không xác thực được.

## 12. Tài liệu chính thức và tiêu chuẩn

- [Oracle Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): các lệnh genkeypair, certreq, gencert, importcert, exportcert, extension BC/KU/EKU/SAN và thứ tự import chain.
- [Oracle Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): API file keystore/truststore, PKCS12, alias, certificate chain.
- [Oracle Java SE 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): TrustAnchor và tham số kiểm tra certification path.
- [Oracle Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): xây và kiểm tra đường dẫn chứng thực theo PKIX.
- [Oracle Java SE 17 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): cơ chế trust anchors, PKIX và extension/checker.
- [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): KeyManager/TrustManager, TLS và truststore.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): BasicConstraints, KeyUsage, EKU, SAN, path validation, revocation và trust model.

## Kết luận

**Lập một CA thử nghiệm không khó về mặt lệnh keytool, nhưng quyết định CA đó được tin ở đâu mới là nội dung bảo mật cốt lõi.** Một bộ lab đúng gồm: root CA có CA=true và khóa riêng được giữ kín; leaf có CA=false, SAN=localhost, EKU=serverAuth và được ký từ CSR; server keystore chứa **private key leaf + certificate chain**; client có **truststore PKCS12 độc lập** chỉ chứa public root certificate đã xác minh fingerprint. Java có thể kiểm tra path bằng PKIX; HTTPS còn phải kiểm tra hostname, mục đích và các điều kiện TLS.

**Tuyệt đối giữ CA/truststore/key thử nghiệm ra khỏi production, không sửa cacerts hệ thống để tránh lỗi, không tắt xác thực TLS và không lấy lab root làm trust anchor chung.** Khi lên production phải dùng quy trình PKI được phê duyệt, danh tính được xác minh, chứng thư/khóa riêng và quản lý vòng đời, audit, revocation phù hợp.
