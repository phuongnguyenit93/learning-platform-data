# Certificate chain trong JAR signing

Khi ký một JAR bằng `jarsigner`, công cụ không chỉ tạo chữ ký số cho nội dung archive. JAR còn mang certificate của signer và có thể mang các certificate trung gian để bên nhận kiểm tra đường dẫn tin cậy. Chuỗi certificate (certificate chain) kết nối certificate của người ký với một CA gốc mà bên xác minh đã tin cậy.

Cần phân biệt ba câu hỏi:

1. **Integrity:** nội dung JAR có còn khớp digest đã được ký không?
2. **Signature:** chữ ký có xác minh được bằng public key trong certificate của signer không?
3. **Trust:** certificate của signer có tạo được chain hợp lệ tới một trust anchor mà bên nhận tin cậy không?

Một JAR có thể có chữ ký mật mã hợp lệ nhưng signer certificate vẫn chưa được tin cậy. Bài này sử dụng JDK 17 trở lên, giải thích cấu trúc signature của JAR, cách chuẩn bị certificate chain, cách ký và xác minh bằng `jarsigner`, cũng như các lỗi thường gặp khi phát hành artifact.

## 1. Certificate chain là gì?

Certificate chain (chuỗi chứng chỉ) là đường dẫn xác minh từ certificate đầu cuối tới một CA gốc được tin cậy.

Với JAR ký bằng certificate do CA cấp, chain thường có cấu trúc:

~~~text
Signer certificate (leaf / end-entity)
        |
        | được ký bởi
        v
Intermediate CA certificate
        |
        | được ký bởi
        v
Root CA certificate (trust anchor)
~~~

Các vai trò:

- **Signer/leaf certificate:** certificate gắn với public key dùng để xác minh chữ ký JAR. Certificate này đại diện cho tổ chức hoặc nhà phát hành.
- **Intermediate CA:** CA trung gian ký certificate của signer hoặc CA cấp dưới khác. Nó cho phép CA gốc không phải trực tiếp ký mọi certificate cuối.
- **Root CA:** CA gốc được bên xác minh cấu hình làm trust anchor. Root thường tự ký và được phân phối trong truststore đáng tin cậy.
- **Private key của signer:** khóa bí mật tương ứng với public key trong leaf certificate. Khóa này được giữ trong keystore hoặc thiết bị ký được bảo vệ; không đưa vào JAR.

Một chain có thể có nhiều intermediate CA. Bên xác minh kiểm tra chữ ký của từng certificate, quan hệ issuer/subject, thời hạn, constraints và chính sách sử dụng khóa. Root CA phải được tin cậy độc lập; việc một certificate tự tuyên bố là root không khiến nó tự động đáng tin.

## 2. Certificate chain xuất hiện ở đâu trong JAR đã ký?

JAR signing dùng các thành phần trong thư mục `META-INF`:

| Thành phần | Vai trò |
|---|---|
| `META-INF/MANIFEST.MF` | Chứa digest của các entry được ký |
| `META-INF/ALIAS.SF` | Signature file, chứa digest của manifest hoặc các section tương ứng |
| `META-INF/ALIAS.RSA`, `.DSA` hoặc `.EC` | Signature block chứa chữ ký số và thông tin certificate của signer |

Tên file signature phụ thuộc alias và thuật toán chữ ký. Ví dụ signer alias `release-signer` có thể tạo các file như `RELEASE-S.SF` và `RELEASE-S.RSA`; tên cụ thể có thể bị rút gọn theo quy tắc của JAR signing.

Signature block dùng định dạng PKCS#7/CMS để mang chữ ký và certificate liên quan. Certificate chain của private-key entry trong keystore được dùng trong quá trình ký và có thể được đưa vào signature block để bên nhận xây dựng chain.

Thông thường, root CA không cần được gửi cùng JAR. Bên nhận nên có root CA trong truststore riêng hoặc trong kho CA được quản trị. Certificate trung gian cần thiết có thể được đưa cùng signature block để giúp xây dựng chain.

JAR signature không mã hóa nội dung. Người nhận vẫn có thể đọc class và resource; chữ ký dùng để phát hiện thay đổi và xác minh nguồn ký.

## 3. Keystore, certificate chain và truststore

Ba khái niệm này có liên quan nhưng không thay thế nhau.

| Thành phần | Nội dung | Ai sử dụng? |
|---|---|---|
| Signing keystore | Private key của signer và certificate chain tương ứng | Người/build system ký JAR |
| Certificate chain | Leaf certificate và các CA certificate trung gian | Signer cung cấp; verifier dùng để kiểm tra đường dẫn |
| Truststore | Root CA hoặc certificate được tin cậy | Người/máy xác minh JAR |

Trong Java `KeyStore`, entry giữ private key thường là `PrivateKeyEntry`. Entry đó chứa private key và certificate chain tương ứng. Entry chỉ chứa certificate được tin cậy thường là `trustedCertEntry`.

Không đưa signing keystore cho người nhận JAR. Người nhận chỉ cần JAR đã ký và truststore chứa CA được tin cậy. Private key phải được bảo vệ riêng.

## 4. Chuẩn bị key pair và signing keystore

Với JDK 17, `PKCS12` là định dạng keystore mặc định và phù hợp cho dự án mới. Ví dụ dưới đây tạo một key pair thử nghiệm bằng RSA 3072 bit.

~~~powershell
keytool -genkeypair -alias release-signer -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -storetype PKCS12 -keystore signing.p12 -validity 365 -dname "CN=Example Release, OU=Build, O=Example, C=VN"
~~~

`keytool` sẽ hỏi mật khẩu keystore và mật khẩu private key nếu cần. Không truyền mật khẩu thật bằng `-storepass` hoặc `-keypass` trên command line, vì chúng có thể xuất hiện trong shell history, process listing hoặc log.

Kiểm tra entry vừa tạo:

~~~powershell
keytool -list -v -alias release-signer -keystore signing.p12 -storetype PKCS12
~~~

Với ví dụ tự ký, entry có `PrivateKeyEntry` và certificate chain thường chỉ có một certificate. Đây là thiết lập phù hợp để học và kiểm thử nội bộ; certificate tự ký không được bên ngoài tin cậy mặc định.

Đối với phát hành thật, dùng certificate code-signing được cấp theo quy trình CA/tổ chức. Certificate nên có mục đích sử dụng phù hợp, bao gồm key usage và extended key usage theo chính sách của CA. Kiểm tra issuer, validity, subject và thuật toán trước khi ký.

## 5. Tạo CSR để CA cấp certificate signer

Trong môi trường phát hành, signer giữ private key trong keystore và gửi CSR cho CA. CSR chứa public key và thông tin subject; private key không rời khỏi signing keystore.

Tạo CSR từ đúng alias:

~~~powershell
keytool -certreq -alias release-signer -keystore signing.p12 -storetype PKCS12 -file release-signer.csr
~~~

Xem nội dung CSR:

~~~powershell
keytool -printcertreq -file release-signer.csr
~~~

Quy trình CA:

1. Tạo key pair trong signing keystore.
2. Tạo CSR từ alias chứa private key.
3. Gửi CSR cho CA theo quy trình xác minh danh tính của tổ chức.
4. CA trả về signer certificate và chain, thường ở dạng PEM hoặc PKCS#7.
5. Xác minh CA certificate và fingerprint qua kênh độc lập.
6. Import CA certificate cần thiết và certificate reply vào keystore.
7. Kiểm tra lại chain trên private-key entry trước khi ký JAR.

CA có thể áp dụng chính sách riêng cho subject, key usage, extended key usage và thời hạn. Không giả định mọi extension trong CSR đều được CA giữ nguyên; kiểm tra certificate được cấp thực tế.

## 6. Xác minh certificate CA trước khi import

Trước khi thêm certificate làm trust anchor, xem nội dung và fingerprint:

~~~powershell
keytool -printcert -file root-ca.pem
~~~

Đối chiếu SHA-256 fingerprint với giá trị nhận được qua một kênh độc lập, đáng tin cậy, ví dụ portal CA đã xác thực, tài liệu PKI nội bộ đã được ký hoặc quản trị viên PKI. Không xác minh certificate chỉ bằng cách so với fingerprint được gửi cùng chính file đó.

Kiểm tra:

- Subject và issuer có đúng CA mong đợi không.
- Fingerprint SHA-256 có khớp nguồn độc lập không.
- Certificate còn hiệu lực không.
- Basic Constraints có xác định CA certificate đúng vai trò không.
- Key Usage có cho phép ký certificate không.
- Chain có intermediate cần thiết không.

Không import một certificate không rõ nguồn gốc vào truststore chỉ để làm cho lệnh xác minh thành công. Khi trust một root CA, bạn đang cho phép các certificate hợp lệ theo chính sách của root đó được xem xét là đáng tin.

## 7. Xây dựng chain trong signing keystore

Nếu CA trả về signer certificate và intermediate chain trong file PKCS#7, có thể nhập certificate reply vào đúng alias chứa private key.

Khi cần thiết, import root/intermediate CA đã xác minh làm trusted certificate trước. Ví dụ:

~~~powershell
keytool -importcert -alias organization-root -file root-ca.pem -keystore signing.p12 -storetype PKCS12
~~~

Nếu có intermediate CA:

~~~powershell
keytool -importcert -alias organization-intermediate -file intermediate-ca.pem -keystore signing.p12 -storetype PKCS12
~~~

Sau khi đã chuẩn bị trust anchor/chain, nhập certificate reply vào alias đã tạo CSR:

~~~powershell
keytool -importcert -alias release-signer -file signer-reply.p7b -keystore signing.p12 -storetype PKCS12 -trustcacerts
~~~

Alias `release-signer` phải là private-key entry đã tạo CSR. Public key trong certificate reply phải khớp public key của private key đó. Nếu dùng alias mới, `keytool` có thể tạo một trusted certificate entry riêng thay vì cập nhật chain của private key.

Xem chain sau khi nhập:

~~~powershell
keytool -list -v -alias release-signer -keystore signing.p12 -storetype PKCS12
~~~

Kiểm tra `Certificate chain length` và từng certificate trong chain. Với CA chain, signer certificate thường đứng đầu, tiếp theo là intermediate CA; root trust anchor được xác định từ truststore. Nếu chain thiếu hoặc không khớp, dừng trước khi ký và yêu cầu CA cung cấp lại chain phù hợp.

## 8. Tạo JAR mẫu để ký

Ví dụ dùng một ứng dụng Java nhỏ để tạo executable JAR.

Cấu trúc dự án:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Main.java
├── classes/
└── app.jar
~~~

Nội dung `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "Java" : String.join(" ", args);
        System.out.println("Hello, " + target + "!");
    }
}
~~~

Từ thư mục gốc `project`, biên dịch và đóng gói:

~~~powershell
New-Item -ItemType Directory -Force -Path classes | Out-Null
javac -d classes src/com/example/Main.java
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Chạy JAR chưa ký để kiểm tra chương trình:

~~~powershell
java -jar app.jar "before signing"
~~~

Stdout:

~~~text
Hello, before signing!
~~~

Khi đã xác nhận artifact cuối cùng, mới ký. Không sửa hoặc cập nhật nội dung JAR sau khi ký; thay đổi entry đã ký sẽ làm digest không còn khớp.

## 9. Ký JAR bằng jarsigner

Dùng signing keystore và alias chứa private key:

~~~powershell
jarsigner -keystore signing.p12 -storetype PKCS12 -sigalg SHA256withRSA -digestalg SHA-256 -signedjar app-signed.jar app.jar release-signer
~~~

Các thành phần:

- `-keystore signing.p12`: signing keystore.
- `-storetype PKCS12`: định dạng keystore.
- `-sigalg SHA256withRSA`: thuật toán ký dữ liệu signature file.
- `-digestalg SHA-256`: thuật toán digest cho nội dung JAR.
- `-signedjar app-signed.jar`: ghi JAR đã ký ra file mới, giữ nguyên `app.jar`.
- `app.jar`: JAR nguồn cần ký.
- `release-signer`: alias private-key entry.

`jarsigner` hỏi mật khẩu keystore/private key nếu không truyền qua command line. Với release, dùng thuật toán hiện đại được JDK và chính sách bảo mật cho phép; tránh MD5, SHA-1 và thuật toán yếu.

Sau khi ký, JAR có signature metadata dưới `META-INF`. Xem danh sách file:

~~~powershell
jar --list --file app-signed.jar
~~~

Bạn sẽ thấy `META-INF/MANIFEST.MF` và các file signature có phần mở rộng như `.SF`, `.RSA`, `.DSA` hoặc `.EC`. Signature block chứa chữ ký và certificate signer; chain giúp bên nhận xây dựng đường dẫn tin cậy.

Chạy chính JAR đã ký:

~~~powershell
java -jar app-signed.jar "signed artifact"
~~~

Stdout:

~~~text
Hello, signed artifact!
~~~

Việc chạy thành công cho thấy launcher có thể thực thi ứng dụng từ archive. Nó không thay thế bước xác minh chữ ký hoặc trust chain.

## 10. Xác minh chữ ký và certificate chain

Xác minh chữ ký JAR:

~~~powershell
jarsigner -verify -verbose -certs app-signed.jar
~~~

Các tùy chọn:

- `-verify`: xác minh digest và chữ ký của các entry đã ký.
- `-verbose`: hiển thị các entry và trạng thái kiểm tra.
- `-certs`: hiển thị thông tin certificate của signer/chain.

Có thể dùng `keytool` để đọc certificate được nhúng trong JAR:

~~~powershell
keytool -printcert -jarfile app-signed.jar
~~~

Kiểm tra certificate signer, issuer, fingerprint, validity và chain. Output chính xác phụ thuộc certificate, JDK và trạng thái trust của máy.

### 10.1. Xác minh với truststore cụ thể

Để xác minh chain theo CA mà tổ chức tin cậy, cung cấp truststore chứa root CA đã xác minh:

~~~powershell
jarsigner -verify -strict -verbose -certs -keystore verify-truststore.p12 -storetype PKCS12 app-signed.jar
~~~

`verify-truststore.p12` là truststore của bên xác minh, không phải signing keystore chứa private key. Có thể tạo truststore bằng cách import root CA đã xác minh:

~~~powershell
keytool -importcert -alias organization-root -file root-ca.pem -keystore verify-truststore.p12 -storetype PKCS12
~~~

Nếu tổ chức dùng CA public, cấu hình truststore phù hợp với môi trường xác minh. Không mặc định rằng truststore của một máy có cùng CA roots với máy khác.

### 10.2. Ý nghĩa của -strict

`-strict` yêu cầu `jarsigner` xem các warning nghiêm trọng trong quá trình xác minh là lỗi và trả exit code khác 0 khi gặp các trường hợp tương ứng. Đây là lựa chọn phù hợp cho bước kiểm tra release/CI.

Không chỉ kiểm tra dòng tổng kết. Hãy xem diagnostic, certificate chain, timestamp và trạng thái từng entry. Một JAR có thể có chữ ký mật mã hợp lệ nhưng signer certificate chưa được truststore tin cậy.

## 11. Phân biệt integrity, signature và trust

| Kiểm tra | Câu hỏi | Bằng chứng |
|---|---|---|
| Digest/integrity | Entry có bị thay đổi kể từ khi ký không? | Digest của entry khớp manifest/signature file |
| Chữ ký số | Signature file có được ký bởi private key tương ứng không? | Chữ ký xác minh bằng public key trong signer certificate |
| Certificate chain | Certificate signer có đường dẫn hợp lệ tới CA không? | Chain, chữ ký CA, thời hạn và constraints hợp lệ |
| Trust | Root CA có được bên nhận chấp nhận không? | Trust anchor hiện diện trong truststore được cấu hình |
| Timestamp | Chữ ký đã tồn tại vào thời điểm nào? | Timestamp token hợp lệ từ TSA được tin cậy |

Một certificate chain hợp lệ về mặt cấu trúc chưa đủ để tạo trust nếu root CA không nằm trong truststore. Ngược lại, thêm một certificate vào truststore là quyết định trust của người xác minh; điều đó không sửa một chữ ký JAR đã bị thay đổi.

JAR signature cũng không chứng minh mã an toàn hoặc không có lỗ hổng. Nó giúp xác minh nội dung có khớp với artifact được ký và danh tính signer theo trust policy.

## 12. Timestamp cho chữ ký JAR

Certificate signer có thời hạn. Nếu JAR được ký khi certificate còn hiệu lực nhưng được kiểm tra sau ngày certificate hết hạn, bên xác minh có thể cần bằng chứng thời điểm ký.

`jarsigner` hỗ trợ lấy timestamp từ Time-Stamp Authority (TSA) qua `-tsa`:

~~~powershell
jarsigner -keystore signing.p12 -storetype PKCS12 -sigalg SHA256withRSA -digestalg SHA-256 -tsa https://tsa.example.org -signedjar app-timestamped.jar app.jar release-signer
~~~

Thay URL ví dụ bằng endpoint TSA thực tế do CA hoặc nhà cung cấp tin cậy chỉ định. TSA tạo timestamp token gắn với signature; token có certificate chain riêng cần được xác minh.

Timestamp giúp chứng minh chữ ký đã tồn tại tại một thời điểm được TSA xác nhận. Nó không làm cho chữ ký sai trở nên hợp lệ, không khôi phục private key bị lộ và không thay thế việc kiểm tra chain của signer hoặc TSA.

Với artifact phát hành dài hạn, timestamp thường là một phần quan trọng của quy trình code signing. Kiểm tra timestamp trong output `jarsigner -verify -verbose -certs` và bảo đảm TSA được truststore của môi trường xác minh chấp nhận.

## 13. Entry không được ký và thay đổi JAR sau khi ký

Một JAR có thể chứa entry chưa được ký, ví dụ file được thêm vào sau khi ký hoặc một phần nội dung không được signature bao phủ. Vì vậy:

- Dùng `-verbose` để xem trạng thái từng entry.
- Xác nhận tất cả class/resource quan trọng đều được ký.
- Không chỉ dựa vào dòng `jar verified` mà bỏ qua warning về unsigned entries.
- Ký sau bước đóng gói cuối cùng.
- Nếu thay đổi entry đã ký, build lại JAR và ký lại toàn bộ artifact.

Nếu một entry đã ký bị sửa, digest không còn khớp và xác minh phải phát hiện thay đổi. Nếu entry không được ký, chữ ký không cung cấp bảo đảm integrity cho entry đó.

Không cập nhật manifest hoặc thêm resource vào JAR sau khi ký. Hãy hoàn tất việc tạo archive, kiểm tra nội dung, rồi ký và xác minh chính file sẽ phát hành.

## 14. Các lỗi certificate chain thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `certificate chain not validated` | Không xây dựng được chain hoặc thiếu trust anchor | Cung cấp intermediate và root CA đã xác minh trong truststore |
| `signer certificate is self-signed` | Dùng certificate tự ký chưa được bên xác minh tin cậy | Chỉ trust trong môi trường test; dùng CA code-signing cho phát hành |
| `unable to find valid certification path` | Root/intermediate không có trong truststore hoặc chain bị đứt | Kiểm tra issuer/subject, import đúng CA chain và xác minh root |
| `Certificate reply does not contain public key for ...` | CA reply không khớp private key đã tạo CSR | Dùng đúng alias/CSR hoặc yêu cầu CA cấp lại certificate |
| `Certificate expired` | Leaf hoặc intermediate đã hết hạn | Gia hạn/cấp lại certificate và kiểm tra timestamp nếu có |
| Host/usage không phù hợp | Certificate được cấp cho mục đích khác | Dùng certificate có key usage/EKU phù hợp với code signing |
| `digest error` hoặc `signature invalid` | JAR entry bị sửa hoặc file hỏng sau khi ký | Build lại artifact từ nguồn tin cậy và ký lại |
| `jar verified` nhưng có unsigned entries | Một số entry không nằm trong phạm vi chữ ký | Xem output verbose và ký lại JAR hoàn chỉnh |
| Timestamp không hợp lệ | TSA chain, timestamp token hoặc digest không hợp lệ | Kiểm tra TSA URL, certificate TSA, thời gian và thuật toán |
| `-strict` trả exit code khác 0 | Có warning nghiêm trọng về trust, chain, thời hạn hoặc thuật toán | Đọc toàn bộ diagnostic và xử lý nguyên nhân trước release |

Đừng giải quyết lỗi trust bằng cách import certificate signer bất kỳ vào truststore mà không xác minh. Truststore quyết định CA nào được chấp nhận; nhập nhầm certificate có thể làm suy yếu toàn bộ chính sách xác minh.

## 15. Quy trình release JAR có certificate chain

Một quy trình phát hành an toàn có thể gồm:

1. Build JAR hoàn chỉnh từ source đã được review.
2. Tạo/đọc signing key trong keystore hoặc thiết bị ký được bảo vệ.
3. Kiểm tra signer certificate và chain.
4. Xác minh root CA fingerprint qua kênh độc lập.
5. Nhập CA reply vào đúng private-key alias.
6. Ký JAR bằng `jarsigner`, dùng digest/signature algorithm được chấp nhận.
7. Lấy timestamp từ TSA tin cậy khi yêu cầu phát hành dài hạn.
8. Xác minh JAR bằng `jarsigner -verify -verbose -certs`.
9. Xác minh trust chain với truststore được quản trị và dùng `-strict` trong CI.
10. Kiểm tra mọi entry quan trọng đã được ký, không có nội dung bị thêm sau ký.
11. Chạy thử JAR đã ký và lưu lại fingerprint, signer identity, build ID cùng kết quả xác minh.
12. Phân phối JAR; không phân phối signing keystore hoặc private key.

Đối với hệ thống phát hành quan trọng, cân nhắc HSM hoặc signing service để private key không phải nằm dưới dạng file thông thường trên build agent. Giới hạn quyền truy cập khóa, audit lần ký và có kế hoạch xoay vòng certificate.

## 16. Checklist trước khi phát hành

- [ ] JAR đã hoàn tất trước khi ký.
- [ ] Signing alias là `PrivateKeyEntry` và giữ đúng private key.
- [ ] Signer certificate phù hợp cho code signing.
- [ ] Certificate chain có signer và intermediate cần thiết.
- [ ] Root CA đã được xác minh fingerprint qua kênh độc lập.
- [ ] Truststore của bên xác minh chứa đúng trust anchor.
- [ ] Dùng digest/signature algorithm mạnh, được JDK chấp nhận.
- [ ] Đã ký bằng `jarsigner` và giữ bản JAR nguồn.
- [ ] `jarsigner -verify -verbose -certs` xác minh chữ ký.
- [ ] `-strict` không báo warning nghiêm trọng trong CI.
- [ ] Đã kiểm tra unsigned entries và từng entry quan trọng.
- [ ] Timestamp hợp lệ nếu quy trình phát hành yêu cầu.
- [ ] Không thay đổi JAR sau khi ký.
- [ ] Private key và signing keystore được bảo vệ, không phân phối cùng JAR.
- [ ] Đã lưu kết quả xác minh và thông tin signer cho audit.

Certificate chain cho JAR signing nối certificate của signer với CA gốc mà bên nhận tin cậy. `jarsigner` dùng private key để ký, đưa chữ ký và certificate vào JAR, rồi xác minh digest/chữ ký khi kiểm tra. Để xác minh nguồn phát hành, bên nhận còn cần xây dựng chain tới trust anchor đáng tin cậy, kiểm tra certificate và xem xét timestamp. Hãy kiểm tra cả integrity, chain, trust và trạng thái từng entry trước khi phát hành.

## Tài liệu tham khảo

- Oracle, The jarsigner Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Oracle, The keytool Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle, JAR File Specification, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
