# Quản lý khóa ký trong Java

Quản lý khóa ký là quá trình tạo, bảo vệ, sử dụng, luân chuyển và thu hồi key pair dùng để xác thực nguồn gốc và tính toàn vẹn của artifact. Trong hệ sinh thái Java, công cụ chính là **keytool** để quản lý keystore/certificate và **jarsigner** để ký, xác minh chữ ký JAR.

Một quy trình cơ bản gồm:

1. Tạo key pair gồm private key và public key.
2. Tạo certificate request (CSR) từ public key.
3. Nhận certificate do CA cấp và nhập certificate chain vào keystore.
4. Dùng private key để ký JAR bằng jarsigner.
5. Xác minh chữ ký và certificate của signer.
6. Lưu trữ, backup, luân chuyển và ngừng sử dụng khóa theo chính sách.

Ví dụ lệnh tạo key pair trong keystore PKCS12:

~~~bash
keytool -genkeypair \
    -alias release-2026 \
    -keyalg RSA \
    -keysize 3072 \
    -sigalg SHA256withRSA \
    -dname "CN=Example Release Signing, OU=Release, O=Example, C=VN" \
    -validity 365 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Sau khi có certificate phù hợp, dùng jarsigner:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -signedjar app-signed.jar \
    app.jar \
    release-2026
~~~

Lệnh ký sử dụng private key được lưu trong alias release-2026. Trong môi trường thật, certificate ký phát hành thường do CA hoặc tổ chức có thẩm quyền cấp; certificate tự ký chỉ phù hợp cho lab hoặc môi trường kiểm soát riêng.

## 1. Key pair, certificate và chữ ký số

Một key pair gồm hai khóa toán học liên quan:

- **Private key:** bí mật, được dùng để tạo chữ ký số. Chỉ chủ sở hữu hoặc hệ thống ký được ủy quyền mới được phép sử dụng.
- **Public key:** có thể công khai, được dùng để xác minh chữ ký được tạo bởi private key tương ứng.

Certificate X.509 gắn public key với danh tính của một chủ thể và được ký bởi issuer. Certificate không chứa private key.

Trong quy trình ký JAR:

1. jarsigner dùng private key để tạo chữ ký cho nội dung JAR.
2. Chữ ký và certificate signer được lưu trong archive.
3. Người nhận dùng public key trong certificate để xác minh chữ ký.
4. Trust policy xác định certificate đó có đại diện cho signer đáng tin hay không.

Chữ ký số hỗ trợ hai thuộc tính:

- **Integrity:** phát hiện nội dung đã ký bị thay đổi.
- **Authenticity:** xác minh chữ ký được tạo bởi private key tương ứng với public key trong certificate.

Chữ ký JAR không mã hóa nội dung archive. Người nhận vẫn có thể đọc class, resource và manifest trong JAR.

Chữ ký hợp lệ về mặt mật mã cũng không tự chứng minh chương trình an toàn. Nó chứng minh nội dung khớp với chữ ký và cho biết signer key nào đã ký; việc tin cậy danh tính signer cần certificate chain và trust policy phù hợp.

## 2. Keystore, truststore và alias

**Keystore** là kho lưu trữ các entry bảo mật. Tùy loại entry, nó có thể chứa private key, certificate chain hoặc secret key.

**Truststore** thường chứa certificate được tin cậy, ví dụ certificate CA hoặc certificate peer được tổ chức chấp nhận. Về mặt kỹ thuật, keystore và truststore có thể dùng cùng định dạng; khác biệt chủ yếu là mục đích sử dụng và nội dung.

Các loại entry phổ biến:

| Entry type | Nội dung | Trường hợp sử dụng |
|---|---|---|
| PrivateKeyEntry | Private key và certificate chain | Ký JAR, định danh server hoặc client |
| trustedCertEntry | Một certificate công khai được tin cậy | Truststore, CA hoặc peer certificate |
| SecretKeyEntry | Khóa đối xứng | Mã hóa dữ liệu theo ứng dụng |

Một entry có **alias** để nhận diện trong keystore. Ví dụ release-2026 là alias của key entry dùng để ký bản phát hành. Alias chỉ là tên định danh, không phải cơ chế phân quyền hay mã hóa khóa.

Có thể xem các entry:

~~~bash
keytool -list -keystore release.p12 -storetype PKCS12
~~~

Xem chi tiết:

~~~bash
keytool -list -v -keystore release.p12 -storetype PKCS12
~~~

Chỉ xem alias cụ thể:

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release-2026
~~~

## 3. Chọn định dạng keystore

Các định dạng thường gặp:

- **PKCS12:** định dạng chuẩn, được hỗ trợ rộng rãi và là lựa chọn mặc định của keytool trên các JDK hiện đại.
- **JKS:** định dạng Java KeyStore cũ, vẫn được hỗ trợ để tương thích hệ thống legacy.
- **PKCS11/HSM:** dùng provider và thiết bị bảo mật phần cứng hoặc token để giữ private key ngoài file keystore thông thường.

Tạo PKCS12:

~~~bash
keytool -genkeypair \
    -alias release-2026 \
    -keyalg RSA \
    -keysize 3072 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Tạo JKS khi hệ thống cũ yêu cầu:

~~~bash
keytool -genkeypair \
    -alias legacy-release \
    -keyalg RSA \
    -keysize 2048 \
    -keystore legacy.jks \
    -storetype JKS
~~~

Không đổi đuôi file để chuyển định dạng. Dùng keytool -importkeystore để chuyển entry và xác minh kết quả.

PKCS12 có thể có quy tắc về password và bảo vệ key khác JKS tùy provider. Một số provider yêu cầu password của private key giống password keystore. Hãy kiểm tra khả năng tương thích của provider và hệ thống đích trước khi chuẩn hóa cách cấp password.

## 4. Tạo key pair bằng keytool

Cú pháp cơ bản:

~~~bash
keytool -genkeypair [options]
~~~

Ví dụ tạo key pair RSA cho release signing:

~~~bash
keytool -genkeypair \
    -alias release-2026 \
    -keyalg RSA \
    -keysize 3072 \
    -sigalg SHA256withRSA \
    -dname "CN=Example Release Signing, OU=Release, O=Example, C=VN" \
    -validity 365 \
    -ext KU=digitalSignature \
    -ext EKU=codeSigning \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Các tham số:

| Tùy chọn | Ý nghĩa |
|---|---|
| -alias | Tên entry trong keystore |
| -keyalg | Thuật toán tạo key pair |
| -keysize | Kích thước khóa |
| -groupname | Tên nhóm khóa, thường dùng với một số thuật toán elliptic curve |
| -sigalg | Thuật toán chữ ký certificate |
| -dname | Distinguished Name của Subject |
| -validity | Số ngày hiệu lực của certificate tự ký ban đầu |
| -ext | Khai báo X.509 extension |
| -keystore | Đường dẫn keystore |
| -storetype | Định dạng keystore |

Tùy chọn KU=digitalSignature khai báo mục đích dùng khóa cho chữ ký số. EKU=codeSigning thể hiện mục đích ký mã khi certificate profile và CA hỗ trợ. Chính sách CA có thể yêu cầu extension hoặc thuật toán cụ thể.

Lệnh tạo key pair cũng tạo certificate tự ký ban đầu để gắn public key với entry. Certificate này chưa phải certificate do CA công cộng hoặc CA tổ chức cấp.

### Chọn thuật toán

Chọn thuật toán dựa trên chính sách bảo mật, khả năng tương thích runtime, CA và hệ thống ký:

- RSA với kích thước khóa phù hợp, ví dụ 3072 bit, thường tương thích rộng.
- ECDSA với curve được tổ chức và nền tảng hỗ trợ, ví dụ P-256 hoặc P-384.
- Dùng digest hiện đại như SHA-256 hoặc mạnh hơn theo chính sách.
- Không chọn MD5 hoặc SHA-1 cho quy trình ký mới.
- Tránh tự đặt thuật toán quá cũ chỉ để tương thích với hệ thống chưa được cập nhật.

Không có một cấu hình duy nhất phù hợp mọi môi trường. Hãy xác nhận thuật toán được chấp nhận bởi CA, JDK, hệ điều hành, công cụ kiểm tra và quy định phát hành.

### Password được hỏi khi tạo

Nếu không truyền -storepass hoặc -keypass, keytool có thể yêu cầu nhập password tương tác. Đây là cách phù hợp hơn cho thao tác thủ công vì password không nằm nguyên văn trong command line.

Không dùng password minh họa như changeit cho khóa production.

## 5. Tạo certificate signing request (CSR)

Khi dùng CA nội bộ hoặc CA bên ngoài, không gửi private key cho CA. Tạo CSR từ key pair hiện có:

~~~bash
keytool -certreq \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release-2026.csr
~~~

CSR chứa thông tin Subject và public key cùng chữ ký tạo bằng private key tương ứng. Private key vẫn nằm trong keystore.

Có thể chỉ định extension nếu CA yêu cầu và quy trình cấp certificate cho phép:

~~~bash
keytool -certreq \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release-2026.csr \
    -ext KU=digitalSignature \
    -ext EKU=codeSigning
~~~

Gửi CSR cho CA theo quy trình của tổ chức. CA xác minh danh tính và chính sách trước khi cấp certificate.

Xem CSR trước khi gửi:

~~~bash
keytool -printcertreq -file release-2026.csr
~~~

CSR không phải certificate đã được cấp. Không dùng output CSR để kết luận certificate chain hoặc trust đã hợp lệ.

## 6. Nhập certificate reply và chain từ CA

Sau khi CA cấp certificate, nhận certificate reply cùng các intermediate/root certificate cần thiết theo quy trình CA.

Có thể nhập CA certificate vào keystore bằng alias riêng nếu cần:

~~~bash
keytool -importcert \
    -alias example-intermediate-ca \
    -file intermediate-ca.cer \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Sau đó nhập certificate reply cho alias giữ private key:

~~~bash
keytool -importcert \
    -trustcacerts \
    -alias release-2026 \
    -file release-reply.pem \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Certificate reply phải tương ứng với public key trong entry release-2026. keytool kiểm tra mối liên hệ này trước khi thay certificate tự ký bằng certificate do CA cấp.

Nếu CA cung cấp chain dưới dạng PKCS#7 hoặc một file chứa nhiều certificate, dùng đúng file reply theo hướng dẫn CA. Nếu thiếu intermediate, cần nhập certificate CA thích hợp trước hoặc cung cấp chain đầy đủ.

Sau khi import, kiểm tra:

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release-2026
~~~

Xác nhận:

- Entry vẫn là PrivateKeyEntry.
- Certificate chain length hợp lý.
- Owner/Subject đúng danh tính release.
- Issuer đúng CA.
- Thời hạn và extension đúng yêu cầu.
- Certificate chain khớp hồ sơ CA.

Không import certificate lạ chỉ vì keytool hỏi có tin cậy hay không. Kiểm tra fingerprint qua kênh độc lập trước khi xác nhận.

## 7. Kiểm tra certificate và public key trước khi ký

Xem certificate của alias:

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release-2026
~~~

Export public certificate:

~~~bash
keytool -exportcert -rfc \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release-2026.cer
~~~

Xem fingerprint:

~~~bash
keytool -printcert -v -file release-2026.cer
~~~

Các trường cần xem:

- Subject/Owner: danh tính signer.
- Issuer: CA cấp certificate.
- Serial number: số định danh certificate trong phạm vi issuer.
- Validity: Not Before và Not After.
- SHA-256 fingerprint: giá trị nhận diện certificate.
- Public Key Algorithm: thuật toán và kích thước public key.
- Key Usage và Extended Key Usage: mục đích sử dụng.
- Certificate chain: đường dẫn CA.

Export certificate chỉ xuất dữ liệu public. Nó không xuất private key. Có thể chia sẻ certificate hoặc fingerprint để người nhận xác minh signer, nhưng không chia sẻ file keystore chứa private key.

## 8. Ký JAR bằng jarsigner

jarsigner ký JAR bằng private key trong keystore.

Cú pháp:

~~~bash
jarsigner [options] jar-file alias
~~~

Ví dụ tạo file đầu ra riêng để giữ lại JAR chưa ký:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -signedjar app-signed.jar \
    app.jar \
    release-2026
~~~

Ý nghĩa:

- -keystore chỉ định nơi lưu private key.
- -storetype xác định định dạng keystore.
- -digestalg chọn digest dùng để băm nội dung.
- -sigalg chọn thuật toán chữ ký.
- -signedjar chỉ định tên JAR đầu ra đã ký.
- app.jar là JAR đầu vào.
- release-2026 là alias chứa private key và certificate chain.

Nếu bỏ -signedjar, jarsigner có thể cập nhật archive đầu vào. Trong pipeline phát hành, dùng file đầu ra riêng giúp giữ lại artifact gốc để so sánh và phục hồi.

jarsigner sẽ yêu cầu password cần thiết nếu không được cung cấp qua tùy chọn. Tránh ghi password production trực tiếp vào command line hoặc log.

### Chữ ký được lưu ở đâu trong JAR?

jarsigner tạo hoặc cập nhật metadata trong META-INF, thường gồm:

- MANIFEST.MF: chứa digest của các entry.
- File .SF: chứa digest của manifest hoặc các section.
- File signature block như .RSA, .DSA hoặc .EC: chứa chữ ký và thông tin certificate signer.

Tên file phụ thuộc signature file name và thuật toán ký. Có thể xem nội dung archive:

~~~bash
jar --list --file app-signed.jar
~~~

Chữ ký bảo vệ các entry được ký. Nếu sửa nội dung entry sau khi ký, xác minh sẽ thất bại. Nếu thêm file sau khi ký, file mới có thể không được ký. Vì vậy hãy hoàn tất đóng gói, resource và metadata trước khi ký; ký là bước cuối của pipeline artifact.

## 9. Xác minh chữ ký JAR

Lệnh cơ bản:

~~~bash
jarsigner -verify app-signed.jar
~~~

Xem chi tiết và certificate signer:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Tùy chọn:

- -verify: xác minh chữ ký.
- -verbose: hiển thị chi tiết quá trình.
- -certs: hiển thị certificate khi verbose và verify.
- -keystore: chỉ định keystore được dùng khi xác minh.
- -strict: xem warning như lỗi và trả trạng thái lỗi phù hợp.

Trong CI có thể dùng:

~~~bash
jarsigner -verify -verbose -certs -strict app-signed.jar
~~~

Chỉ bật -strict sau khi truststore, certificate chain và timestamp đã được cấu hình đúng cho môi trường build/verify. Nếu dùng certificate tự ký trong lab, việc xác minh có thể phát cảnh báo rằng certificate chưa được tin cậy dù chữ ký nội dung đúng.

### Hai khái niệm cần phân biệt

**Signature integrity** trả lời: nội dung JAR có khớp với chữ ký không?

**Signer trust** trả lời: certificate có xây dựng được đường dẫn tin cậy tới trust anchor mà người xác minh chấp nhận không?

Một JAR có thể có chữ ký khớp về mặt mật mã nhưng signer certificate không được truststore tin cậy. Ngược lại, certificate được tin cậy không cứu được một JAR đã bị sửa sau khi ký.

Đọc toàn bộ warning/error của jarsigner. Không chỉ nhìn một dòng "jar verified" rồi bỏ qua cảnh báo về chain, timestamp, certificate hết hạn hoặc entry chưa ký.

## 10. Timestamp khi ký JAR

Timestamp chứng minh chữ ký đã tồn tại tại một thời điểm do Timestamping Authority (TSA) xác nhận.

Ví dụ:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -tsa https://tsa.example.com \
    -signedjar app-signed.jar \
    app.jar \
    release-2026
~~~

TSA URL trong ví dụ là địa chỉ minh họa; thay bằng TSA được tổ chức hoặc nhà phát hành chấp nhận.

Một số tùy chọn timestamp:

| Tùy chọn | Ý nghĩa |
|---|---|
| -tsa | URL của Timestamping Authority |
| -tsacert | Alias certificate TSA trong keystore |
| -tsapolicyid | Policy OID yêu cầu từ TSA |
| -tsadigestalg | Digest algorithm cho timestamp request |

Timestamp hữu ích khi certificate signer có thời hạn. Nếu chữ ký được timestamp hợp lệ trong lúc certificate còn hiệu lực, verifier có thể đánh giá thời điểm ký theo timestamp và chính sách certificate tương ứng.

Timestamp không kéo dài thời hạn certificate, không thay thế trust chain và không làm một chữ ký sai trở thành đúng. Certificate TSA cũng cần được xác minh và tin cậy theo chính sách.

Nếu không có timestamp, việc xác minh chữ ký sau khi certificate signer hết hạn có thể gặp cảnh báo hoặc không đáp ứng chính sách của hệ thống.

## 11. Chọn digest và signature algorithm

jarsigner cho phép chọn thuật toán:

~~~bash
-digestalg SHA-256
-sigalg SHA256withRSA
~~~

Digest algorithm tạo hash của nội dung. Signature algorithm dùng private key để ký dữ liệu digest hoặc cấu trúc tương ứng.

Một số lựa chọn thường gặp tùy chính sách:

- SHA-256 hoặc mạnh hơn cho digest.
- SHA256withRSA cho RSA key.
- SHA256withECDSA cho EC key phù hợp.
- Thuật toán và kích thước khóa phải tương thích với JDK, CA, verifier và security policy.

Không dùng MD5 hoặc SHA-1 cho chữ ký phát hành mới. Nếu JAR cũ dùng thuật toán yếu, hãy kiểm tra khả năng tương thích và lập kế hoạch ký lại bằng thuật toán hiện đại.

Không chọn signature algorithm chỉ theo thói quen. Cần xem certificate public key, provider hỗ trợ, quy định mật mã và hệ thống người nhận.

## 12. Đổi alias, password và chuyển keystore

Quản lý alias và password là các thao tác khác nhau.

### Đổi alias

~~~bash
keytool -changealias \
    -alias release-old \
    -destalias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Đổi alias chỉ đổi tên entry. Nó không tạo key pair mới và không thay đổi certificate hoặc private key.

Sau khi đổi alias, cập nhật pipeline và script ký dùng tên alias mới. JAR đã ký trước đó vẫn chứa chữ ký cũ; đổi alias không làm thay đổi chữ ký trong archive.

### Đổi password của private key entry

~~~bash
keytool -keypasswd \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Tùy provider, thao tác này có thể không được hỗ trợ hoặc có ràng buộc riêng đối với PKCS12. Hãy kiểm tra loại keystore và nhập password cũ/mới theo prompt.

### Đổi password keystore

~~~bash
keytool -storepasswd \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Lệnh này thay password bảo vệ keystore. Nó không thay key pair hoặc certificate.

### Chuyển JKS sang PKCS12

~~~bash
keytool -importkeystore \
    -srckeystore legacy.jks \
    -srcstoretype JKS \
    -destkeystore release.p12 \
    -deststoretype PKCS12
~~~

Sau khi chuyển:

1. Liệt kê entry trong keystore đích.
2. Kiểm tra alias và entry type.
3. Kiểm tra certificate chain.
4. Thử truy cập private key bằng quy trình ký kiểm thử.
5. Xác nhận ứng dụng và pipeline có thể đọc định dạng mới.
6. Giữ backup keystore nguồn cho tới khi hoàn tất xác minh và chính sách lưu trữ cho phép loại bỏ.

Không xóa keystore nguồn ngay sau khi import nếu chưa xác minh đầy đủ entry và khả năng phục hồi.

## 13. Luân chuyển khóa ký (key rotation)

Khóa ký không nên được dùng vô thời hạn. Rotation có thể cần thiết khi:

- Certificate gần hết hạn.
- Thuật toán hoặc kích thước khóa không còn đáp ứng chính sách.
- Nhân sự hoặc nhà cung cấp quản lý khóa thay đổi.
- Private key có nguy cơ bị lộ.
- Tổ chức đổi CA hoặc quy trình phát hành.
- Cần tách môi trường hoặc sản phẩm.

Quy trình rotation:

1. Tạo key pair mới với alias và định danh riêng.
2. Tạo CSR và xin certificate mới.
3. Xác minh Subject, Issuer, validity, fingerprint và extension.
4. Cập nhật pipeline ký sang alias mới.
5. Ký artifact phát hành mới bằng khóa mới.
6. Kiểm tra người dùng và hệ thống đích chấp nhận certificate mới.
7. Giữ certificate cũ để xác minh artifact đã phát hành trước đó theo chính sách.
8. Thu hồi certificate cũ nếu có sự cố hoặc chính sách yêu cầu.
9. Ngừng sử dụng private key cũ sau khi hoàn tất giai đoạn chuyển tiếp.
10. Ghi lại thời điểm, người phê duyệt và artifact liên quan.

Không xóa certificate cũ chỉ vì đã đổi alias hoặc tạo key pair mới. Người dùng có thể cần xác minh artifact đã ký bằng certificate cũ trong tương lai.

Nếu private key bị lộ, rotation đơn thuần chưa đủ. Cần đánh giá phạm vi artifact bị ảnh hưởng, thu hồi certificate theo quy trình CA, phát hành thông báo và ký lại artifact cần thiết.

## 14. Backup và khôi phục keystore

Private key thường không thể tái tạo từ public certificate. Nếu mất private key, không thể tiếp tục ký với danh tính cũ.

Backup cần có:

- Keystore được mã hóa và bảo vệ quyền truy cập.
- Password hoặc cơ chế mở khóa được lưu trong secret manager riêng.
- Bản sao dự phòng ở vị trí kiểm soát.
- Quy trình khôi phục đã được thử nghiệm.
- Metadata về alias, certificate chain, thuật toán và ngày hết hạn.
- Quy trình xác định ai có quyền phục hồi hoặc sử dụng khóa.

Không lưu password cùng thư mục với keystore theo cách không được bảo vệ. Không commit keystore hoặc file secret vào Git.

Backup không thay thế kiểm soát truy cập. Một bản sao private key không được bảo vệ cũng là một bản sao có thể bị đánh cắp.

Với khóa quan trọng, cân nhắc HSM hoặc dịch vụ quản lý khóa để private key không cần xuất thành file thông thường.

## 15. Quản lý khóa trong HSM hoặc PKCS11

Trong môi trường có yêu cầu bảo mật cao, private key có thể nằm trong HSM hoặc hardware token. Ứng dụng gọi provider để sử dụng khóa; private key không cần rời khỏi thiết bị.

keytool và jarsigner hỗ trợ provider, ví dụ SunPKCS11, thông qua cấu hình provider:

~~~bash
keytool -list \
    -keystore NONE \
    -storetype PKCS11 \
    -addprovider SunPKCS11 \
    -providerarg pkcs11.cfg
~~~

Cú pháp và cấu hình chính xác phụ thuộc JDK, provider, driver và thiết bị. Một số hệ thống yêu cầu token PIN hoặc protected authentication path.

jarsigner cũng có các tùy chọn provider như -addprovider, -providerArg, -providerClass và -providerPath. Kiểm tra help của đúng JDK và tài liệu nhà cung cấp HSM.

Lợi ích của HSM:

- Giảm nhu cầu xuất private key ra file.
- Có thể áp dụng chính sách sử dụng khóa trong thiết bị.
- Hỗ trợ audit và kiểm soát truy cập.
- Có thể yêu cầu nhiều yếu tố hoặc phê duyệt cho thao tác ký.

HSM không tự động bảo đảm toàn bộ quy trình phát hành an toàn. Pipeline, quyền truy cập token, firmware, backup và quy trình phê duyệt vẫn cần được quản lý.

## 16. Bảo vệ khóa trong CI/CD

Signing key là tài sản nhạy cảm của quy trình phát hành. Nếu private key bị lộ, kẻ tấn công có thể tạo artifact mang chữ ký của tổ chức.

Thực hành:

- Dùng secret manager hoặc hệ thống quản lý khóa của tổ chức.
- Không lưu password trong source, build file hoặc log.
- Hạn chế job có quyền ký chỉ cho release pipeline được phê duyệt.
- Dùng runner ephemeral hoặc môi trường ký được kiểm soát.
- Tách khóa development, staging và production.
- Hạn chế người có quyền đọc hoặc sử dụng keystore.
- Ghi audit log cho mỗi lần ký.
- Kiểm tra artifact và dependency trước khi ký.
- Ký sau cùng, sau khi mọi nội dung đã hoàn tất.
- Lưu checksum, version và provenance của artifact cùng kết quả ký.
- Luân chuyển khóa theo lịch và khi có sự cố.

Nếu cần truyền password cho process trong CI, dùng cơ chế secret injection được nền tảng bảo vệ và tránh in giá trị ra log. Cần đánh giá cả process arguments, environment variables, temporary files và quyền truy cập runner; không có một cách truyền password phù hợp cho mọi hệ thống.

Không để pull request từ nguồn không tin cậy chạy job có quyền sử dụng signing key production.

## 17. Ví dụ Java 17+: build JAR và chuẩn bị ký

Ví dụ này tạo một ứng dụng nhỏ có thể đóng gói thành JAR. Phần Java được biên dịch và chạy độc lập; các lệnh keytool/jarsigner phía sau minh họa quy trình ký artifact.

Cấu trúc:

~~~text
jar-signing-demo/
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── build/
    ├── classes/
    ├── app.jar
    ├── release.p12
    └── app-signed.jar
~~~

### Main.java

~~~java
package com.example;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String version = args.length == 0 ? "development" : args[0];
        System.out.println("Release " + version + " ready.");
    }
}
~~~

### Biên dịch

Từ thư mục gốc jar-signing-demo:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/Main.java
~~~

### Chạy class

~~~bash
java -cp build/classes com.example.Main 1.0.0
~~~

Output:

~~~text
Release 1.0.0 ready.
~~~

### Tạo JAR có Main-Class

~~~bash
jar --create \
    --file build/app.jar \
    --main-class com.example.Main \
    -C build/classes .
~~~

Kiểm tra manifest và nội dung:

~~~bash
jar --list --file build/app.jar
jar --describe-module --file build/app.jar
~~~

JAR này là automatic module nếu đặt trên module path mà không có module descriptor. Ví dụ chỉ cần executable JAR trên classpath nên không cần module-info.java.

### Tạo key pair cho lab

~~~bash
keytool -genkeypair \
    -alias demo-release \
    -keyalg RSA \
    -keysize 2048 \
    -sigalg SHA256withRSA \
    -dname "CN=Demo Release Signer, OU=Training, O=Example, C=VN" \
    -validity 30 \
    -keystore build/demo-release.p12 \
    -storetype PKCS12
~~~

Trong lab, keytool sẽ yêu cầu password. Certificate tự ký chỉ dùng để minh họa; người nhận có thể xác minh chữ ký nhưng chưa tự động tin cậy danh tính signer.

### Ký JAR

~~~bash
jarsigner \
    -keystore build/demo-release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -signedjar build/app-signed.jar \
    build/app.jar \
    demo-release
~~~

### Xác minh chữ ký

~~~bash
jarsigner -verify -verbose -certs build/app-signed.jar
~~~

Trong lab, có thể xuất hiện warning về certificate tự ký hoặc chain chưa được trust. Đó là tình huống khác với lỗi nội dung chữ ký. Đọc toàn bộ output để phân biệt.

### Xem certificate signer

~~~bash
keytool -printcert -jarfile build/app-signed.jar
~~~

### Chạy JAR đã ký

~~~bash
java -jar build/app-signed.jar 1.0.0
~~~

Output của ứng dụng:

~~~text
Release 1.0.0 ready.
~~~

Việc chạy được JAR không thay thế xác minh chữ ký. Thực hiện verify riêng trong pipeline hoặc trước khi triển khai.

## 18. Các lỗi thường gặp khi quản lý khóa ký

### Alias không tồn tại

jarsigner không tìm thấy alias trong keystore. Kiểm tra:

~~~bash
keytool -list -keystore release.p12 -storetype PKCS12
~~~

Dùng đúng alias và đúng file keystore.

### Không mở được keystore

Kiểm tra password, storetype, provider và đường dẫn. JKS và PKCS12 không thể được hoán đổi chỉ bằng cách đổi phần mở rộng file.

### Certificate reply không khớp private key

Certificate do CA cấp phải chứa public key tương ứng với private key trong alias. Tạo CSR từ đúng alias và không tạo key pair mới giữa lúc gửi CSR và nhập reply.

### Thiếu certificate chain

Nhập intermediate/root certificate theo quy trình CA hoặc cung cấp chain đầy đủ. Kiểm tra Certificate chain length và Issuer sau khi import.

### jarsigner báo không có private key

Alias có thể chỉ là trustedCertEntry, hoặc keystore không chứa private key tương ứng. Ký JAR cần PrivateKeyEntry có private key sử dụng được.

### Chữ ký không hợp lệ sau khi đóng gói

Có thể artifact đã bị sửa sau khi ký. Hoàn tất build, nén, thêm resource và manifest trước khi ký. Nếu nội dung thay đổi, tạo artifact mới và ký lại.

### Certificate chưa được tin cậy

Chữ ký có thể khớp nhưng certificate chain không kết thúc ở trust anchor được chấp nhận. Kiểm tra CA, truststore và chính sách của môi trường verify. Không import certificate lạ chỉ để bỏ cảnh báo.

### Certificate hết hạn hoặc thiếu timestamp

Kiểm tra validity và timestamp token. Dùng TSA đáng tin khi chính sách phát hành yêu cầu. Timestamp phải được xác minh; chỉ có trường timestamp không đủ chứng minh chữ ký hợp lệ.

### Thuật toán bị từ chối

JDK có thể từ chối thuật toán yếu theo security policy. Chọn digest/signature algorithm được hỗ trợ và được chính sách cho phép; không hạ thấp chính sách bảo mật chỉ để làm cho artifact cũ verify thành công.

### -strict làm build thất bại

-strict xem warning như lỗi. Đọc warning cụ thể, sửa trust chain, timestamp, unsigned entries hoặc vấn đề certificate. Không bỏ -strict mà không hiểu nguyên nhân nếu CI yêu cầu xác minh nghiêm ngặt.

## 19. Quy trình phát hành có chữ ký

Một pipeline ký JAR có thể theo thứ tự:

~~~text
Source
  |
  v
Compile and test
  |
  v
Package unsigned JAR
  |
  v
Inspect artifact and dependencies
  |
  v
Authorize signing job
  |
  v
Use protected private key
  |
  v
Sign JAR and request timestamp
  |
  v
Verify signature, certificate and timestamp
  |
  v
Publish immutable signed artifact
~~~

Các điểm kiểm soát:

1. Chỉ build từ commit hoặc release được phê duyệt.
2. Kiểm tra dependency và nội dung trước khi ký.
3. Chỉ signing job có quyền truy cập private key.
4. Không xuất private key khỏi HSM nếu chính sách cấm.
5. Ký artifact cuối cùng và không sửa sau khi ký.
6. Verify chữ ký ngay sau signing.
7. Kiểm tra certificate chain và timestamp theo trust policy.
8. Lưu audit log, checksum, version và signer identity.
9. Publish đúng artifact đã được verify.
10. Giữ quy trình rotation và incident response sẵn sàng.

## 20. Checklist quản lý khóa ký

- [ ] Mỗi môi trường hoặc sản phẩm có khóa riêng theo chính sách.
- [ ] Private key được tạo trong môi trường được kiểm soát.
- [ ] Thuật toán và kích thước khóa đáp ứng chính sách hiện hành.
- [ ] Alias và Subject được đặt tên rõ ràng.
- [ ] CSR được tạo từ đúng key pair.
- [ ] Certificate reply và chain đã được xác minh.
- [ ] Keystore dùng định dạng được hỗ trợ, ưu tiên PKCS12 khi phù hợp.
- [ ] Password và private key không nằm trong repository hoặc log.
- [ ] Backup được bảo vệ và đã thử khôi phục.
- [ ] Signing job có quyền tối thiểu cần thiết.
- [ ] Artifact được đóng gói hoàn chỉnh trước khi ký.
- [ ] Timestamp được thêm khi chính sách yêu cầu.
- [ ] jarsigner verify thành công theo trust policy.
- [ ] Warning về self-signed, chain, expiry và unsigned entries được xử lý.
- [ ] Certificate và key có lịch rotation.
- [ ] Có quy trình thu hồi khi private key bị lộ.
- [ ] Artifact đã ký được lưu bất biến cùng checksum và provenance.

## 21. Lệnh keytool và jarsigner cần nhớ

~~~bash
# Generate a key pair
keytool -genkeypair -alias release-2026 \
    -keyalg RSA -keysize 3072 \
    -keystore release.p12 -storetype PKCS12

# Create a certificate request
keytool -certreq -alias release-2026 \
    -keystore release.p12 -storetype PKCS12 \
    -file release-2026.csr

# Import a CA-issued certificate reply
keytool -importcert -alias release-2026 \
    -file release-reply.pem \
    -keystore release.p12 -storetype PKCS12

# Inspect key and certificate chain
keytool -list -v -alias release-2026 \
    -keystore release.p12 -storetype PKCS12

# Export the public certificate
keytool -exportcert -rfc -alias release-2026 \
    -keystore release.p12 -storetype PKCS12 \
    -file release-2026.pem

# Sign the final JAR
jarsigner -keystore release.p12 -storetype PKCS12 \
    -digestalg SHA-256 -sigalg SHA256withRSA \
    -signedjar app-signed.jar app.jar release-2026

# Verify signature and show signer certificate
jarsigner -verify -verbose -certs app-signed.jar

# Apply strict verification policy
jarsigner -verify -verbose -certs -strict app-signed.jar

# Rename an alias
keytool -changealias -alias old-name -destalias new-name \
    -keystore release.p12 -storetype PKCS12

# Convert a JKS keystore to PKCS12
keytool -importkeystore \
    -srckeystore legacy.jks -srcstoretype JKS \
    -destkeystore release.p12 -deststoretype PKCS12
~~~

Quản lý khóa ký là quản lý vòng đời của một danh tính phát hành, không chỉ là chạy một lệnh ký JAR. Khi private key được bảo vệ, certificate chain được kiểm tra, artifact được ký ở bước cuối và chữ ký được xác minh theo trust policy, nhóm có thể phát hành JAR có thể kiểm tra nguồn gốc và tính toàn vẹn qua nhiều phiên bản.

## Tài liệu tham khảo

- [The keytool Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- [The jarsigner Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Java Security Developer's Guide — PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/24/security/java-pki-programmers-guide.html)
- [JAR File Specification — Signing and Verification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
