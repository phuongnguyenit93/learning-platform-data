# Import certificate bằng keytool trong Java

## Mục tiêu

Sau bài này, bạn có thể dùng lệnh keytool -importcert để thêm CA certificate vào truststore hoặc nhập certificate reply do Certificate Authority (CA) cấp vào private-key entry; phân biệt keystore và truststore; đọc và xác minh fingerprint; hiểu certificate chain; xử lý PEM, DER và PKCS#7; chọn đúng alias, keystore và store type; kiểm tra kết quả sau khi import; và chẩn đoán các lỗi thường gặp khi cấu hình TLS/SSL cho ứng dụng Java.

## 1. Import certificate là gì?

Certificate (chứng thư số) là một cấu trúc dữ liệu được ký số, thường theo chuẩn X.509, dùng để gắn một public key với thông tin nhận dạng của subject. Chữ ký của issuer giúp bên nhận kiểm tra certificate có bị thay đổi và có được cấp bởi một issuer mà họ tin cậy hay không.

Trong Java, công cụ keytool đi kèm JDK quản lý key pair, certificate và keystore. Lệnh:

~~~bash
keytool -importcert
~~~

đọc một certificate hoặc certificate chain từ file hoặc standard input rồi lưu vào keystore entry được chỉ định bởi alias.

Có hai tình huống import chính:

1. **Import trusted certificate:** thêm certificate của CA hoặc một bên mà ứng dụng quyết định tin cậy vào truststore. Entry mới có kiểu trustedCertEntry.
2. **Import certificate reply:** nhập certificate hoặc chain do CA trả về sau khi bạn gửi Certificate Signing Request (CSR). Certificate chain mới thay thế certificate tự ký ban đầu trong private-key entry có cùng public key.

Hai tình huống dùng cùng lệnh -importcert nhưng khác nhau ở trạng thái của alias. Vì vậy, cần xác định đúng mục tiêu trước khi chạy lệnh.

## 2. Phân biệt keystore, truststore và certificate entry

Keystore là nơi lưu trữ key và certificate. Các entry thường gặp:

| Loại entry | Nội dung | Mục đích |
|---|---|---|
| PrivateKeyEntry | Private key và certificate chain tương ứng | Chứng minh danh tính của server/client hoặc ký dữ liệu |
| SecretKeyEntry | Symmetric secret key | Mã hóa/giải mã dữ liệu |
| trustedCertEntry | Một public-key certificate | Lưu certificate mà chủ keystore quyết định tin cậy |

**Keystore** thường chứa private key của ứng dụng cùng certificate chain chứng minh public key tương ứng.

**Truststore** thường chứa trustedCertEntry của root CA hoặc CA mà ứng dụng tin cậy. Khi kết nối TLS, Java sử dụng trust material để kiểm tra certificate chain do peer gửi đến.

Keystore và truststore không phải hai định dạng file khác nhau. Chúng đều có thể dùng cùng loại keystore, chẳng hạn PKCS12; sự khác nhau nằm ở các entry được lưu và mục đích sử dụng.

Ví dụ:

- server-identity.p12: chứa private key của HTTPS server và certificate chain được CA ký.
- app-truststore.p12: chứa root CA mà client tin cậy để xác minh server.
- cacerts: truststore CA được JDK cung cấp và quản lý ở cấp cài đặt Java.

Không nên nhập private key bằng -importcert. Lệnh này nhập certificate hoặc certificate chain. Nếu cần chuyển private-key entry giữa hai keystore, dùng -importkeystore.

## 3. Cú pháp và các tùy chọn của -importcert

Cú pháp tổng quát:

~~~bash
keytool -importcert -alias <alias> -file <certificate-file> -keystore <keystore-file> -storetype <type>
~~~

Các tùy chọn thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| -importcert | Nhập certificate hoặc certificate chain |
| -alias | Tên entry đích |
| -file | File certificate đầu vào; nếu bỏ, dữ liệu được đọc từ stdin |
| -keystore | File keystore đích |
| -storetype | Loại keystore, ví dụ PKCS12 hoặc JKS |
| -storepass | Password của keystore |
| -keypass | Password bảo vệ private key khi nhập certificate reply |
| -trustcacerts | Cho phép dùng certificate trong cacerts để xây dựng trust chain |
| -cacerts | Chỉ định keystore cacerts của JDK làm keystore đích |
| -noprompt | Không hiển thị lời nhắc tương tác |
| -v | Hiển thị output chi tiết |

Trong JDK 9 trở lên, loại keystore mặc định là PKCS12. Để lệnh có kết quả rõ ràng giữa các máy và JDK, nên chỉ định -storetype tường minh khi biết định dạng file.

Ví dụ nhập CA certificate vào truststore riêng:

~~~bash
keytool -importcert -alias company-root -file company-root.pem -keystore app-truststore.p12 -storetype PKCS12
~~~

keytool sẽ yêu cầu password nếu cần và có thể hiển thị thông tin certificate để người dùng xác nhận. Hãy xác minh fingerprint trước khi đồng ý.

Không đặt password thật trực tiếp trong command line hoặc script được lưu vào source control. Nếu không truyền password, keytool có thể yêu cầu nhập tương tác. Với automation, hãy dùng cơ chế quản lý secret và password-protection phù hợp với môi trường triển khai.

## 4. Xác định đúng loại import qua alias

Đây là quy tắc quan trọng nhất của -importcert.

### Trường hợp A: alias chưa tồn tại — import trusted certificate

Nếu alias không trỏ đến một key entry hiện có, keytool hiểu rằng bạn muốn thêm một trusted certificate entry.

~~~bash
keytool -importcert -alias company-root -file company-root.pem -keystore app-truststore.p12 -storetype PKCS12
~~~

Kết quả mong đợi là một entry mới có kiểu trustedCertEntry.

Alias phải chưa tồn tại. Nếu alias đã là một trusted certificate entry, keytool báo lỗi và không nhập certificate dưới alias đó.

### Trường hợp B: alias đã trỏ đến private-key entry — import certificate reply

Nếu alias đang trỏ đến một key entry, keytool hiểu dữ liệu đầu vào là certificate reply của CA.

~~~bash
keytool -importcert -trustcacerts -alias app-server -file app-server-reply.p7b -keystore server-identity.p12 -storetype PKCS12
~~~

Trong trường hợp này:

- Private key hiện có được giữ lại.
- Certificate chain cũ, thường bắt đầu bằng self-signed certificate, được thay bằng chain do CA cấp.
- Public key trong certificate reply phải khớp với public key của private key entry.
- Certificate reply phải xây dựng được trust chain tới trusted certificate.
- Nếu key password khác store password, keytool có thể yêu cầu key password.

Nếu certificate reply không chứa public key tương ứng với key entry, keytool không thể cài certificate đó vào alias này.

### Bảng phân biệt

| Trạng thái alias | Ý định import | Entry sau import |
|---|---|---|
| Chưa tồn tại | Thêm CA/peer certificate để tin cậy | trustedCertEntry |
| Đã tồn tại dưới dạng trustedCertEntry | Alias bị trùng | Báo lỗi |
| Đã tồn tại dưới dạng private-key entry | Cài certificate reply cho key pair hiện tại | PrivateKeyEntry với certificate chain mới |

Không chọn alias chỉ dựa trên tên file certificate. Hãy kiểm tra entry hiện có và xác định certificate cần được tin cậy hay là certificate cấp cho private key của chính ứng dụng.

## 5. Xác minh certificate trước khi import

Import certificate là hành động thay đổi trust configuration. Nếu nhập nhầm certificate của kẻ tấn công vào truststore, ứng dụng có thể tin cậy certificate hoặc dữ liệu do bên đó ký.

### Xem certificate từ file

Dùng -printcert:

~~~bash
keytool -printcert -file company-root.pem
~~~

Muốn xem chi tiết:

~~~bash
keytool -printcert -v -file company-root.pem
~~~

Thông tin quan trọng gồm:

- Owner/Subject: danh tính được certificate mô tả.
- Issuer: CA hoặc thực thể đã ký certificate.
- Serial Number: số định danh certificate do issuer cấp.
- Valid from / until: khoảng thời gian hiệu lực.
- SHA-256 fingerprint: dấu vân tay của certificate.
- Subject Alternative Name (SAN): hostname, IP hoặc identity được certificate đại diện.
- Key Usage và Extended Key Usage: mục đích sử dụng được cho phép.
- Signature algorithm và public-key algorithm.

### So sánh SHA-256 fingerprint qua kênh độc lập

Lấy SHA-256 fingerprint do keytool hiển thị và so sánh với fingerprint được cung cấp qua một kênh xác thực độc lập, chẳng hạn:

- Tài liệu bảo mật chính thức của CA.
- Người quản trị PKI hoặc nhóm bảo mật của tổ chức.
- Kho certificate nội bộ có cơ chế xác thực.
- Kênh liên hệ đã xác minh với chủ sở hữu certificate.

Không chỉ tải certificate và fingerprint từ cùng một nguồn không xác thực rồi so sánh chúng với nhau. Nếu kẻ tấn công thay certificate trên đường truyền và cũng thay fingerprint đi kèm, phép so sánh đó không chứng minh được danh tính.

Certificate root thường tự ký, nghĩa là Subject và Issuer có thể giống nhau. Điều đó không tự chứng minh root certificate thuộc về CA mà bạn mong muốn. Niềm tin vào public key của root phải đến từ một nguồn xác thực độc lập.

### Kiểm tra certificate của HTTPS server

Có thể đọc certificate mà một máy chủ TLS trình bày:

~~~bash
keytool -printcert -sslserver api.example.com:443
~~~

Nếu bỏ port, keytool dùng cổng HTTPS mặc định 443.

Lệnh này giúp xem certificate do server gửi. Nó là bước kiểm tra thông tin certificate, không thay thế một TLS handshake đầy đủ và không tự chứng minh ứng dụng sẽ chấp nhận hostname, trust chain, protocol hay cipher suite đó.

### Không dùng -noprompt trước khi xác minh

-noprompt tắt tương tác. Khi import certificate, keytool sẽ không hỏi người dùng xác nhận certificate như trong luồng thông thường.

Chỉ dùng tùy chọn này trong automation khi fingerprint, nguồn gốc certificate và chính sách trust đã được xác minh độc lập. Không dùng -noprompt đơn thuần để làm cho pipeline chạy qua mà không kiểm tra certificate.

## 6. Import CA certificate vào truststore

Giả sử tổ chức cung cấp root CA certificate dưới tên company-root.pem. Bạn muốn ứng dụng Java tin cậy các server có certificate chain kết thúc tại CA này.

### Bước 1: kiểm tra certificate

~~~bash
keytool -printcert -v -file company-root.pem
~~~

Xác nhận subject, issuer, validity, fingerprint và CA extensions theo thông tin đã được nhóm PKI xác thực.

### Bước 2: tạo hoặc cập nhật truststore

~~~bash
keytool -importcert -alias company-root -file company-root.pem -keystore app-truststore.p12 -storetype PKCS12
~~~

Nếu truststore chưa tồn tại, keytool có thể tạo file mới và yêu cầu password. Nếu alias chưa tồn tại, certificate được thêm thành trustedCertEntry.

Khi keytool hiển thị certificate để xác nhận, chỉ nhập yes sau khi fingerprint khớp với nguồn đáng tin cậy.

### Bước 3: kiểm tra entry

~~~bash
keytool -list -v -alias company-root -keystore app-truststore.p12 -storetype PKCS12
~~~

Xác nhận:

- Alias là company-root.
- Entry type là trustedCertEntry.
- Owner/Subject và Issuer đúng.
- SHA-256 fingerprint khớp với fingerprint đã xác minh.
- Certificate có validity và CA usage phù hợp.

### Bước 4: cấu hình ứng dụng sử dụng truststore

Với ứng dụng Java dùng JSSE, có thể cấu hình truststore khi chạy:

~~~bash
java -Djavax.net.ssl.trustStore=app-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar client-app.jar
~~~

Nếu môi trường yêu cầu password, cấu hình qua cơ chế secret phù hợp. Không đưa password thật vào command line có thể bị ghi trong process list, shell history hoặc log.

Việc import certificate vào file app-truststore.p12 không tự làm mọi ứng dụng Java sử dụng file đó. Ứng dụng phải được cấu hình dùng đúng truststore, hoặc truststore phải được đặt tại vị trí mặc định mà runtime thực sự sử dụng.

## 7. Import certificate reply từ CA vào private-key entry

Đây là quy trình phổ biến khi tạo HTTPS server hoặc client certificate.

Ban đầu, keytool tạo một key pair và lưu private key cùng self-signed certificate trong private-key entry. Sau khi CA ký CSR, certificate reply được import để thay self-signed certificate bằng certificate chain được CA cấp.

### Bước 1: tạo key pair

~~~bash
keytool -genkeypair -alias app-server -keyalg RSA -keysize 3072 -dname "CN=api.example.com, O=Example, C=VN" -keystore server-identity.p12 -storetype PKCS12 -validity 365
~~~

Keytool tạo private/public key pair và certificate ban đầu trong alias app-server.

Certificate self-signed ở bước này chỉ phục vụ việc khởi tạo entry và chưa tự động được một CA công khai tin cậy.

### Bước 2: tạo CSR

~~~bash
keytool -certreq -alias app-server -file app-server.csr -keystore server-identity.p12 -storetype PKCS12
~~~

CSR dùng định dạng PKCS #10 và được ký bằng private key tương ứng. Gửi file CSR cho CA theo quy trình xác thực danh tính của tổ chức.

### Bước 3: nhận certificate reply

CA có thể trả về:

- Một certificate X.509 của server.
- Một chuỗi certificate X.509.
- Một certificate chain ở định dạng PKCS#7.

Một file reply có thể được đặt tên app-server-reply.pem, app-server-reply.cer hoặc app-server-reply.p7b tùy định dạng CA cung cấp. Phần mở rộng file không tự xác định nội dung; hãy xác nhận định dạng thực tế.

Nếu CA trả về một certificate đơn, keytool cần các trusted certificate phù hợp trong keystore hoặc cacerts để xây dựng chain tới root. Nếu CA trả về chain, chain thường bắt đầu bằng certificate của server rồi đến các certificate CA cấp cao hơn.

### Bước 4: cài certificate reply

~~~bash
keytool -importcert -trustcacerts -alias app-server -file app-server-reply.p7b -keystore server-identity.p12 -storetype PKCS12
~~~

Ở đây app-server đã là alias của private-key entry. Keytool nhận biết đây là certificate reply, kiểm tra public key có khớp với key entry hay không và thay certificate chain cũ bằng chain mới nếu việc xác minh thành công.

-trustcacerts cho phép keytool sử dụng các trusted certificate trong cacerts khi xây dựng certificate chain. Tùy chọn này không có nghĩa là mọi certificate đầu vào tự động được tin cậy.

Nếu CA sử dụng intermediate CA, cần có đủ certificate để xây dựng chain từ server certificate qua intermediate CA đến trusted root. Có thể nhập root/intermediate certificate cần thiết vào keystore hoặc quản lý chúng trong truststore/cacerts theo chính sách PKI.

### Bước 5: kiểm tra private-key entry và chain

~~~bash
keytool -list -v -alias app-server -keystore server-identity.p12 -storetype PKCS12
~~~

Xác nhận:

- Entry type vẫn là PrivateKeyEntry.
- Subject là identity được CA cấp.
- Issuer là CA phù hợp.
- Certificate chain length phù hợp với chain được cấp và trust path đã xây dựng.
- Certificate đầu tiên chứa public key khớp với private key của alias.
- SAN, validity, key usage và extended key usage đúng với mục đích sử dụng.

Việc nhập thành công không có nghĩa server đã được cấu hình TLS hoàn chỉnh. Cần kiểm tra server thực sự trình bày certificate chain mới và client xác minh được hostname cũng như trust path.

## 8. Hiểu certificate chain và trust anchor

Certificate chain là chuỗi certificate liên kết chữ ký giữa subject và issuer.

Một chain điển hình:

~~~text
Server certificate
       |
       v
Intermediate CA certificate
       |
       v
Root CA certificate (trust anchor)
~~~

Certificate đầu tiên là certificate của server hoặc client. Certificate tiếp theo xác thực public key của CA đã ký certificate trước đó. Chuỗi tiếp tục cho tới root CA được tin cậy.

Một số điểm cần nhớ:

- Certificate reply có thể chỉ chứa leaf certificate.
- Certificate chain có thể được trả về dưới dạng PKCS#7 hoặc một chuỗi X.509.
- Khi import một certificate đơn, keytool cố gắng xây dựng chain tới self-signed root bằng các trusted certificate có sẵn.
- -trustcacerts cho phép dùng thêm certificate trong cacerts.
- Nếu không xây dựng được trust path cho một certificate mới, keytool có thể hiển thị fingerprint để người dùng xác minh.
- Root certificate tự ký không tự tạo ra niềm tin; cần xác minh public key của root qua nguồn đáng tin cậy.

Không phải lúc nào cũng cần nhập mọi intermediate certificate như một trust anchor. Thông thường, client tin cậy root CA và server gửi đủ intermediate certificate để hoàn thành chain. Tuy nhiên, quy trình PKI của tổ chức có thể yêu cầu quản lý intermediate riêng.

## 9. Phân biệt -trustcacerts và -cacerts

Hai tùy chọn có tên gần giống nhau nhưng mục đích khác nhau.

| Tùy chọn | Ý nghĩa |
|---|---|
| -trustcacerts | Cho phép dùng certificate từ cacerts để xác minh/xây dựng chain khi import |
| -cacerts | Chọn chính keystore cacerts của JDK làm keystore đích hoặc nguồn cho lệnh phù hợp |

Ví dụ import CA vào truststore riêng và dùng cacerts để hỗ trợ xác minh:

~~~bash
keytool -importcert -trustcacerts -alias company-root -file company-root.pem -keystore app-truststore.p12 -storetype PKCS12
~~~

Ví dụ nhập certificate trực tiếp vào cacerts của JDK:

~~~bash
keytool -importcert -cacerts -alias company-root -file company-root.pem
~~~

Lệnh thứ hai thay đổi truststore cấp JDK. Thường cần quyền quản trị hoặc quyền ghi vào thư mục cài đặt Java. Nó ảnh hưởng đến các ứng dụng sử dụng cacerts của chính JDK đó.

Trong môi trường doanh nghiệp, ưu tiên truststore riêng của ứng dụng nếu chính sách yêu cầu trust scope hẹp. Nếu quản trị cacerts toàn cục, cần có quy trình phê duyệt, backup, kiểm soát alias và kế hoạch gỡ certificate khi CA bị thu hồi hoặc không còn được tin cậy.

## 10. Định dạng certificate mà keytool hỗ trợ

keytool có thể nhập:

- X.509 v1 certificate.
- X.509 v2 certificate.
- X.509 v3 certificate.
- PKCS#7 certificate chain.
- Một chuỗi các X.509 certificate.

Dữ liệu có thể ở dạng:

| Định dạng | Đặc điểm |
|---|---|
| DER | Dữ liệu certificate ở dạng nhị phân |
| PEM | Dạng Base64 có dòng BEGIN CERTIFICATE và END CERTIFICATE |
| PKCS#7 | Định dạng có thể chứa certificate chain |

Ví dụ PEM:

~~~text
-----BEGIN CERTIFICATE-----
Base64-encoded certificate data
-----END CERTIFICATE-----
~~~

Ví dụ xem certificate PEM:

~~~bash
keytool -printcert -file company-root.pem
~~~

Nếu file certificate là DER, keytool vẫn có thể đọc trực tiếp:

~~~bash
keytool -printcert -file company-root.cer
~~~

Đuôi .cer, .crt, .pem hoặc .p7b không bảo đảm định dạng thực tế. Khi lệnh báo không đọc được certificate, hãy xác minh nội dung file và định dạng mà CA cung cấp.

Nếu certificate chain ở dạng PKCS#7, dùng trực tiếp file chain theo quy trình import. Không cần chuyển sang PEM chỉ vì tên file khác nhau nếu keytool đã hỗ trợ định dạng đầu vào đó.

## 11. Import certificate vào cacerts của JDK

cacerts là truststore được JDK cung cấp với tập root CA mặc định. Vị trí thường nằm dưới:

~~~text
$JAVA_HOME/lib/security/cacerts
~~~

Có thể liệt kê certificate hiện có:

~~~bash
keytool -list -cacerts
~~~

Muốn xem một alias cụ thể:

~~~bash
keytool -list -v -cacerts -alias company-root
~~~

Nếu tổ chức yêu cầu thêm root CA vào truststore toàn cục của JDK:

~~~bash
keytool -importcert -cacerts -alias company-root -file company-root.pem
~~~

Trước khi chạy:

1. Xác định chính xác JAVA_HOME mà ứng dụng sử dụng.
2. Xác minh fingerprint của root certificate qua kênh độc lập.
3. Kiểm tra alias có phù hợp với quy ước quản trị.
4. Đảm bảo có quyền ghi và quy trình backup/rollback.
5. Kiểm tra các ứng dụng bị ảnh hưởng sau khi cập nhật.

Mỗi JDK installation có thể có cacerts riêng. Import certificate vào cacerts của một JDK không tự cập nhật cacerts của các JDK khác, container khác hoặc truststore riêng của ứng dụng.

Không thay thế cacerts bằng một file chỉ chứa CA nội bộ nếu ứng dụng vẫn cần các root CA công khai khác. Hãy quản lý tập trusted certificate theo đúng chính sách của môi trường.

## 12. Kiểm tra kết quả sau khi import

Không kết luận thành công chỉ vì keytool hiển thị thông báo đã import. Cần xác nhận entry và certificate chain.

### Kiểm tra một trusted certificate entry

~~~bash
keytool -list -v -alias company-root -keystore app-truststore.p12 -storetype PKCS12
~~~

Kết quả cần có entry type:

~~~text
Entry type: trustedCertEntry
~~~

Đồng thời kiểm tra SHA-256 fingerprint, Subject, Issuer, serial number và validity.

### Kiểm tra certificate reply của server

~~~bash
keytool -list -v -alias app-server -keystore server-identity.p12 -storetype PKCS12
~~~

Kết quả cần có:

~~~text
Entry type: PrivateKeyEntry
Certificate chain length: 2
~~~

Chain length trong ví dụ chỉ minh họa trường hợp leaf certificate và root CA. Nếu có intermediate CA hoặc chain khác, số lượng certificate sẽ khác.

### Kiểm tra certificate bằng lệnh printcert

~~~bash
keytool -printcert -file app-server-reply.p7b
~~~

Dùng để xem nội dung certificate/chain được CA gửi về. So sánh Subject, Issuer, SAN, validity và fingerprint với hồ sơ cấp phát.

### Kiểm tra HTTPS thực tế

Sau khi cấu hình ứng dụng sử dụng truststore, hãy thực hiện kết nối HTTPS tới endpoint thử nghiệm. Kiểm tra:

- TLS handshake hoàn tất.
- Hostname khớp với SAN của server certificate.
- Certificate còn trong thời hạn hiệu lực.
- Chain kết thúc ở trust anchor được chấp nhận.
- Key Usage và Extended Key Usage phù hợp.
- TLS protocol và cipher suite đáp ứng chính sách bảo mật.
- Ứng dụng thực sự sử dụng đúng truststore và đúng JDK runtime.

Có thể dùng thêm công cụ kiểm tra TLS của môi trường để quan sát chain mà server trình bày. Kết quả keytool -list chỉ xác nhận nội dung keystore; nó không thay thế kiểm tra kết nối thật.

## 13. Ví dụ thực hành hoàn chỉnh: tạo lab CA và import certificate reply

Ví dụ này tạo một root CA thử nghiệm, một private-key entry cho server, một CSR và certificate reply do root CA ký. Các file chỉ phục vụ môi trường lab.

### Bước 1: tạo root CA thử nghiệm

~~~bash
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 3072 -dname "CN=Lab Root CA, O=Example, C=VN" -ext bc=ca:true -ext ku=keyCertSign,cRLSign -validity 3650 -keystore lab-root.p12 -storetype PKCS12
~~~

Khi được hỏi password, nhập password lab và lưu lại an toàn để dùng cho các bước tiếp theo.

### Bước 2: xuất root CA certificate

~~~bash
keytool -exportcert -rfc -alias lab-root -keystore lab-root.p12 -storetype PKCS12 -file lab-root.pem
~~~

Kiểm tra fingerprint:

~~~bash
keytool -printcert -v -file lab-root.pem
~~~

Đây là CA tự tạo trong lab. Không sử dụng certificate này để bảo vệ hệ thống production.

### Bước 3: tạo key pair cho server

~~~bash
keytool -genkeypair -alias app-server -keyalg RSA -keysize 2048 -dname "CN=localhost, O=Example, C=VN" -ext san=dns:localhost -ext eku=serverAuth -validity 365 -keystore app-server.p12 -storetype PKCS12
~~~

Certificate ban đầu là self-signed và private key được lưu trong app-server.p12.

### Bước 4: tạo CSR

~~~bash
keytool -certreq -alias app-server -file app-server.csr -keystore app-server.p12 -storetype PKCS12
~~~

CSR chứa public key và thông tin subject được ký bằng private key của alias app-server.

### Bước 5: dùng lab root CA ký CSR

~~~bash
keytool -gencert -alias lab-root -keystore lab-root.p12 -storetype PKCS12 -infile app-server.csr -outfile app-server-reply.pem -rfc -validity 365 -ext san=dns:localhost -ext eku=serverAuth
~~~

Lệnh tạo certificate reply cho public key trong CSR. Root CA dùng private key của alias lab-root để ký.

### Bước 6: thêm root CA vào keystore chứa key server

~~~bash
keytool -importcert -alias lab-root -file lab-root.pem -keystore app-server.p12 -storetype PKCS12
~~~

Xác nhận fingerprint root CA trước khi chấp nhận. Sau bước này, app-server.p12 có root CA dưới dạng trustedCertEntry và app-server dưới dạng PrivateKeyEntry.

### Bước 7: nhập certificate reply vào alias server

~~~bash
keytool -importcert -trustcacerts -alias app-server -file app-server-reply.pem -keystore app-server.p12 -storetype PKCS12
~~~

Keytool kiểm tra public key trong reply có khớp private-key entry app-server hay không, sau đó xây dựng chain từ certificate server tới root CA đã được tin cậy.

### Bước 8: xác minh kết quả

~~~bash
keytool -list -v -alias app-server -keystore app-server.p12 -storetype PKCS12
~~~

Kiểm tra:

- Entry type là PrivateKeyEntry.
- Certificate đầu tiên có Subject CN=localhost và SAN DNS:localhost.
- Issuer là Lab Root CA.
- Chain chứa certificate server và root CA trong ví dụ này.
- Certificate chain length là 2 nếu chain được xây dựng đúng như ví dụ.

### Bước 9: tạo truststore cho client lab

~~~bash
keytool -importcert -alias lab-root -file lab-root.pem -keystore client-trust.p12 -storetype PKCS12
~~~

Sau khi xác minh fingerprint và xác nhận import, kiểm tra:

~~~bash
keytool -list -v -alias lab-root -keystore client-trust.p12 -storetype PKCS12
~~~

Entry phải có kiểu trustedCertEntry.

Ví dụ này minh họa đầy đủ sự khác biệt giữa private-key entry và trusted certificate entry. Trong production, certificate và private key phải được cấp phát, lưu giữ, backup và bảo vệ theo quy trình PKI của tổ chức.

## 14. Lỗi thường gặp và cách xử lý

### Alias đã tồn tại

**Dấu hiệu:** keytool báo đã có trusted certificate cho alias.

**Nguyên nhân:** alias đang trỏ đến trustedCertEntry và bạn cố nhập certificate khác vào cùng alias.

**Cách xử lý:** kiểm tra entry bằng -list -v; chọn alias mới hoặc thực hiện quy trình thay certificate có kiểm soát. Không xóa entry cũ trước khi xác minh certificate thay thế và kế hoạch rollback.

### Certificate reply không khớp private key

**Dấu hiệu:** keytool không thể cài certificate reply vào alias hiện tại.

**Nguyên nhân:** certificate được CA cấp từ CSR của key pair khác hoặc nhầm file reply.

**Cách xử lý:** kiểm tra lại alias đã tạo CSR, file CSR đã gửi cho CA và certificate reply nhận về. Không cố import certificate không tương ứng vào private-key entry.

### Không xây dựng được certificate chain

**Dấu hiệu:** keytool không thể xác minh certificate reply hoặc không tìm thấy trusted certificate phù hợp.

**Nguyên nhân:** thiếu root CA, intermediate CA hoặc CA certificate chưa được tin cậy trong keystore/cacerts.

**Cách xử lý:** lấy đúng CA certificate từ nguồn đã xác minh, import trusted certificate theo chính sách và chạy lại import reply. Kiểm tra chain order nếu CA cung cấp PKCS#7 hoặc chuỗi X.509.

### Fingerprint không khớp

**Dấu hiệu:** SHA-256 fingerprint hiển thị khác với fingerprint được công bố.

**Nguyên nhân:** file certificate sai, bị thay thế, đã đổi certificate hoặc lấy từ một endpoint khác.

**Cách xử lý:** dừng import, xác minh lại nguồn và yêu cầu CA/PKI cung cấp fingerprint chính xác qua kênh độc lập. Không chấp nhận certificate chỉ vì Subject hoặc Issuer có tên quen thuộc.

### Certificate hết hạn hoặc chưa có hiệu lực

**Dấu hiệu:** certificate có Valid from/Valid until không phù hợp thời điểm hiện tại.

**Nguyên nhân:** certificate hết hạn, start date nằm trong tương lai hoặc đồng hồ hệ thống sai.

**Cách xử lý:** kiểm tra thời gian hệ thống, timezone và certificate mới nhất do CA cấp. Không thay đổi thời gian máy để bỏ qua certificate hết hạn.

### Certificate không có SAN phù hợp

**Dấu hiệu:** import thành công nhưng HTTPS client vẫn báo hostname mismatch.

**Nguyên nhân:** certificate không có Subject Alternative Name tương ứng hostname/IP mà client truy cập.

**Cách xử lý:** yêu cầu CA cấp certificate có SAN chính xác. Việc import certificate không sửa được hostname mismatch.

### Import vào nhầm keystore hoặc JDK

**Dấu hiệu:** keytool list cho thấy certificate đã tồn tại nhưng ứng dụng vẫn báo PKIX path building failed.

**Nguyên nhân:** ứng dụng chạy bằng JDK khác, dùng truststore khác hoặc cấu hình javax.net.ssl.trustStore chưa đúng.

**Cách xử lý:** kiểm tra java.home, cấu hình truststore thực tế và đường dẫn file. Xác minh alias bằng chính JDK mà ứng dụng dùng.

### Sai định dạng certificate

**Dấu hiệu:** keytool báo không thể phân tích dữ liệu certificate.

**Nguyên nhân:** file không phải X.509/PKCS#7 hợp lệ, file bị cắt hoặc extension không phản ánh định dạng thật.

**Cách xử lý:** kiểm tra file bằng -printcert; yêu cầu CA xuất lại PEM/DER/PKCS#7 phù hợp và không chỉnh sửa nội dung certificate.

### Không có quyền ghi cacerts

**Dấu hiệu:** keytool báo Access denied hoặc không thể cập nhật keystore.

**Nguyên nhân:** user hiện tại không có quyền ghi thư mục cài đặt JDK.

**Cách xử lý:** dùng truststore riêng của ứng dụng nếu phù hợp hoặc nhờ administrator quản lý cacerts theo quy trình được phê duyệt. Không thay đổi quyền toàn bộ thư mục JDK chỉ để chạy một lệnh import.

### Dùng -noprompt không kiểm tra certificate

**Dấu hiệu:** pipeline import thành công nhưng certificate không đúng.

**Nguyên nhân:** -noprompt bỏ qua xác nhận tương tác và pipeline không kiểm tra fingerprint trước đó.

**Cách xử lý:** xác minh fingerprint độc lập trước khi tự động import; chỉ dùng -noprompt sau khi có trust decision rõ ràng và có log/audit.

## 15. Các nguyên tắc bảo mật khi import certificate

- Xác minh SHA-256 fingerprint qua một kênh độc lập trước khi tin cậy root hoặc peer certificate.
- Chỉ nhập certificate từ CA hoặc chủ sở hữu đã được xác thực.
- Không coi self-signed certificate là đáng tin chỉ vì chữ ký tự kiểm tra được.
- Phân biệt truststore chứa trustedCertEntry với keystore chứa private-key entry.
- Giữ private key trong vùng bảo vệ; không gửi private key cùng CSR hoặc certificate reply.
- Không đặt store password hoặc key password thật trong shell history, source code hay log.
- Không dùng -noprompt nếu chưa có quy trình xác minh fingerprint.
- Chỉ cập nhật cacerts khi có phê duyệt và kế hoạch rollback.
- Theo dõi ngày hết hạn, việc thu hồi certificate và lịch thay CA.
- Kiểm tra hostname/SAN, validity, key usage, extended key usage và thuật toán được chính sách JDK cho phép.
- Kiểm tra ứng dụng bằng TLS handshake thật sau khi cập nhật truststore.
- Giữ lại bản sao truststore trước khi thay đổi nếu quy trình vận hành yêu cầu rollback.

Import certificate chỉ là một bước trong quản lý PKI. Việc một certificate xuất hiện trong truststore không chứng minh nó phù hợp với mọi mục đích hoặc mọi ứng dụng.

## 16. Checklist trước và sau khi import

### Trước khi import

- [ ] Xác định mục tiêu là thêm trusted certificate hay cài certificate reply.
- [ ] Xác nhận đúng alias và loại entry hiện tại.
- [ ] Xác định chính xác keystore/truststore đích.
- [ ] Xác nhận store type, ví dụ PKCS12 hoặc JKS.
- [ ] Xác nhận certificate file là X.509 hoặc PKCS#7 hợp lệ.
- [ ] Xem certificate bằng keytool -printcert.
- [ ] So sánh SHA-256 fingerprint qua kênh độc lập.
- [ ] Kiểm tra Subject, Issuer, validity, SAN và Key Usage.
- [ ] Xác nhận có root/intermediate CA cần thiết để xây dựng chain.
- [ ] Xác định JDK/runtime mà ứng dụng thực sự sử dụng.

### Sau khi import

- [ ] Chạy keytool -list -v với đúng alias.
- [ ] Xác nhận trustedCertEntry hoặc PrivateKeyEntry theo mục đích.
- [ ] Xác minh fingerprint và certificate chain.
- [ ] Kiểm tra SAN, issuer và thời hạn hiệu lực.
- [ ] Xác nhận ứng dụng đang sử dụng đúng truststore.
- [ ] Thực hiện TLS handshake/integration test.
- [ ] Ghi lại alias, fingerprint, ngày import và owner chịu trách nhiệm.
- [ ] Có kế hoạch thay thế/gỡ certificate khi hết hạn hoặc không còn tin cậy.

## 17. Tài liệu tham khảo chính thức

- [The keytool Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html) — tùy chọn -importcert, trusted certificate, certificate reply, certificate chain, cacerts, định dạng X.509/PKCS#7 và kiểm tra fingerprint.
- [Java Security Standard Algorithm Names — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — tên chuẩn của security algorithms, certificate types và keystore types.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html) — cách Java sử dụng key manager, trust manager và truststore khi thiết lập TLS.
- [Java KeyStore API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html) — mô hình keystore, entry type và cách truy cập key/certificate.
- [RFC 5280: Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280) — cấu trúc X.509 certificate, certificate path validation và các extension.

Lệnh keytool -importcert có thể thêm một trusted certificate hoặc cài certificate reply vào private-key entry. Hãy xác định đúng loại entry, xác minh fingerprint và trust chain, sau đó kiểm tra lại keystore và TLS thực tế trước khi đưa cấu hình vào production.
