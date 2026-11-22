# Ký JAR bằng jarsigner

**jarsigner** là công cụ dòng lệnh đi kèm JDK để ký số và xác minh chữ ký của Java Archive (JAR). Khi ký, công cụ dùng private key của người phát hành để tạo chữ ký số cho các entry trong JAR. Certificate tương ứng với public key và certificate chain của signer được lưu cùng chữ ký trong file JAR.

Ký JAR giúp người nhận kiểm tra hai thuộc tính quan trọng:

- **Integrity**: các entry đã được ký không bị thay đổi kể từ khi ký.
- **Authenticity**: chữ ký được tạo bằng private key tương ứng với public key trong certificate của signer.

Chữ ký JAR không mã hóa nội dung, không che giấu class hoặc resource, không chứng minh chương trình an toàn và cũng không tự động cấp quyền chạy cho ứng dụng. Người nhận vẫn cần đánh giá certificate, danh tính signer, nguồn tải và chính sách bảo mật của mình.

## 1. Quy trình ký JAR tổng quát

Một quy trình phát hành thường gồm các bước:

1. Biên dịch và đóng gói ứng dụng thành JAR.
2. Chuẩn bị key pair và certificate của người ký trong keystore.
3. Dùng jarsigner ký JAR bằng alias chứa private key.
4. Tạo timestamp qua Time Stamping Authority (TSA) khi quy trình phát hành yêu cầu.
5. Xác minh chữ ký và các entry bằng jarsigner -verify.
6. Kiểm tra certificate chain, signer identity, timestamp và warning.
7. Phát hành đúng artifact đã được ký và kiểm tra.

Sơ đồ khái quát:

~~~text
Java source
    |
    v
javac / jar
    |
    v
app.jar (unsigned)
    |
    +---- keystore: private key + signer certificate chain
    |
    v
jarsigner
    |
    +---- META-INF/MANIFEST.MF
    +---- META-INF/ACME.SF
    +---- META-INF/ACME.RSA
    |
    v
app-signed.jar
    |
    v
jarsigner -verify
    |
    +---- signature integrity
    +---- certificate / timestamp diagnostics
    |
    v
release artifact
~~~

jarsigner có thể ký JAR được tạo bởi công cụ jar và các ZIP archive. Khi ký một ZIP chưa có manifest, công cụ tạo META-INF/MANIFEST.MF để lưu digest của các entry.

## 2. Chuẩn bị keystore và signing key

Để ký JAR, cần một cặp public/private key cùng certificate xác thực public key. Private key được dùng để tạo chữ ký; certificate và chain được đưa vào signature block để bên nhận có thể xác minh.

Trong Java, keytool quản lý keystore. Từ JDK 9, loại keystore mặc định thường là PKCS12. Nên chỉ rõ loại store trong script để tránh phụ thuộc cấu hình máy.

### Tạo keystore thử nghiệm

Ví dụ tạo một RSA key pair để học và kiểm thử nội bộ:

~~~bash
keytool -genkeypair \
  -alias acme \
  -keyalg RSA \
  -keysize 3072 \
  -validity 3650 \
  -dname "CN=Acme Demo, O=Acme, C=VN" \
  -keystore signing.p12 \
  -storetype PKCS12
~~~

keytool sẽ yêu cầu nhập password cho keystore và có thể hỏi password riêng cho private key. Không ghi password thật trực tiếp trong source code hoặc repository.

Giải thích:

- -genkeypair tạo public/private key pair và certificate.
- -alias acme đặt tên entry để jarsigner tìm đúng private key.
- -keyalg RSA chọn thuật toán khóa RSA.
- -keysize 3072 chọn kích thước khóa.
- -validity 3650 đặt thời hạn certificate tự ký được tạo, tính theo ngày.
- -dname đặt Distinguished Name cho certificate.
- -keystore signing.p12 đặt file keystore.
- -storetype PKCS12 chọn định dạng lưu trữ.

Certificate tự ký trong ví dụ chỉ phù hợp lab, thử nghiệm và xác minh quy trình. Nó không tự trở thành certificate của nhà phát hành được hệ thống hoặc người dùng tin cậy.

### Kiểm tra alias

~~~bash
keytool -list -v \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -alias acme
~~~

Kiểm tra các thông tin:

- Alias name là acme.
- Entry type là PrivateKeyEntry.
- Certificate có Subject và Issuer như dự kiến.
- Public key algorithm và key size đúng.
- Validity dates còn phù hợp.
- Certificate chain có đầy đủ thành phần cần thiết.

PrivateKeyEntry là entry cần thiết để ký. Một trustedCertEntry chỉ chứa certificate công khai, không có private key để tạo chữ ký.

## 3. Dùng certificate ký mã do CA cấp

Trong môi trường phát hành thật, tổ chức thường dùng certificate code-signing được CA cấp theo chính sách phù hợp. Quy trình điển hình:

1. Tạo private key trong keystore hoặc HSM.
2. Tạo certificate signing request (CSR).
3. Gửi CSR cho CA code-signing.
4. Nhận certificate được CA ký và certificate chain.
5. Import certificate reply vào đúng alias đã tạo private key.
6. Kiểm tra chain và mục đích sử dụng certificate trước khi ký.

Tạo CSR:

~~~bash
keytool -certreq \
  -alias acme \
  -file acme-signing.csr \
  -keystore signing.p12 \
  -storetype PKCS12
~~~

Sau khi CA cấp certificate reply, import vào alias đã chứa private key:

~~~bash
keytool -importcert \
  -alias acme \
  -file acme-code-signing-chain.p7b \
  -keystore signing.p12 \
  -storetype PKCS12
~~~

Tên file và định dạng certificate reply phụ thuộc CA. Khi import certificate reply cho alias có private key, keytool liên kết certificate chain mới với private key hiện có.

Không tạo một alias trusted certificate mới rồi nhầm nó với signing key. Alias dùng để ký phải chứa private key cùng certificate chain tương ứng.

Certificate code-signing cần có KeyUsage và ExtendedKeyUsage phù hợp. Nếu certificate không được phép ký code, jarsigner có thể phát warning về badKeyUsage hoặc badExtendedKeyUsage.

## 4. Đóng gói ứng dụng thành JAR trước khi ký

Nên ký artifact cuối cùng sau khi đã biên dịch, đóng gói resource và hoàn tất manifest. Mọi thay đổi nội dung sau khi ký đều có thể làm mất hiệu lực digest của entry.

Ví dụ ứng dụng Java 17:

~~~text
project/
  src/
    com/acme/Main.java
  out/
  app.jar
~~~

Tệp src/com/acme/Main.java:

~~~java
package com.acme;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from signed JAR");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/com/acme/Main.java
~~~

Đóng gói executable JAR:

~~~bash
jar --create \
  --file app.jar \
  --main-class com.acme.Main \
  -C out .
~~~

Kiểm tra nội dung archive:

~~~bash
jar --list --file app.jar
~~~

Có thể chạy bản unsigned để kiểm tra ứng dụng trước khi ký:

~~~bash
java -jar app.jar
~~~

Stdout:

~~~text
Hello from signed JAR
~~~

Đây là bước kiểm tra chương trình. Chữ ký được tạo sau đó để bảo vệ tính toàn vẹn và xác thực nguồn phát hành của artifact.

## 5. Ký JAR bằng jarsigner

Cú pháp cơ bản:

~~~bash
jarsigner [options] jar-file alias
~~~

Ví dụ ký app.jar bằng alias acme trong signing.p12 và ghi kết quả sang file riêng:

~~~bash
jarsigner \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

jarsigner yêu cầu password keystore và password private key nếu cần. Nếu không cung cấp password trên dòng lệnh, công cụ sẽ hỏi tương tác.

Ý nghĩa các đối số:

- -keystore chỉ định nơi lưu private key và certificate.
- -storetype chỉ định loại keystore.
- -signedjar đặt tên JAR đã ký được tạo ra.
- app.jar là JAR đầu vào.
- acme là alias chứa private key dùng để ký.

Nếu bỏ -signedjar, jarsigner ghi đè JAR đầu vào bằng bản đã ký. Trong pipeline phát hành, nên ghi sang file output riêng để có thể đối chiếu unsigned artifact với signed artifact và tránh ghi đè nhầm.

Nếu keystore là file mặc định .keystore trong user home, jarsigner có thể tìm thấy nó mà không cần -keystore. Tuy nhiên, script build/release nên chỉ rõ keystore để kết quả dễ tái tạo và kiểm soát.

## 6. JAR được ký như thế nào?

Khi ký, jarsigner bổ sung các file trong thư mục META-INF. Với RSA signer có alias acme, các file thường có dạng:

~~~text
META-INF/
  MANIFEST.MF
  ACME.SF
  ACME.RSA
~~~

Tên signature file mặc định lấy tối đa tám ký tự đầu của alias, chuyển thành chữ hoa. Signature block có phần mở rộng phụ thuộc thuật toán khóa, ví dụ .RSA, .DSA hoặc .EC.

Ba thành phần có vai trò khác nhau:

### MANIFEST.MF

Manifest chứa thông tin metadata và digest của các entry trong JAR. Digest được tính trên nội dung nhị phân của từng entry được ký.

### Signature file (.SF)

File .SF chứa digest của các phần tương ứng trong manifest. Theo mặc định, nó cũng có header chứa digest của toàn bộ manifest để tối ưu quá trình xác minh.

### Signature block (.RSA, .DSA hoặc .EC)

Signature block chứa chữ ký số của file .SF và certificate hoặc certificate chain xác thực public key tương ứng với private key đã ký.

Quan hệ khái quát:

~~~text
Entry bytes
    |
    v
Entry digest
    |
    v
MANIFEST.MF
    |
    v
Digest of manifest sections
    |
    v
ACME.SF
    |
    v
Private-key signature
    |
    v
ACME.RSA + signer certificate chain
~~~

Khi xác minh, jarsigner kiểm tra chữ ký của .SF, đối chiếu digest giữa .SF và manifest, sau đó tính lại digest của các entry để so sánh. Nếu nội dung entry đã ký bị thay đổi, kiểm tra sẽ thất bại.

Chữ ký không mã hóa entry. Người nhận vẫn có thể mở JAR và đọc class/resource như một ZIP archive bình thường.

## 7. Xác minh JAR đã ký

Dùng tùy chọn -verify:

~~~bash
jarsigner -verify app-signed.jar
~~~

Khi chữ ký và nội dung các entry được kiểm tra thành công, jarsigner có thể hiển thị:

~~~text
jar verified.
~~~

Để xem chi tiết từng entry:

~~~bash
jarsigner -verify -verbose app-signed.jar
~~~

Để xem thông tin certificate của signer:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Các cờ thường gặp trong output verbose:

| Cờ | Ý nghĩa |
|---|---|
| s | Chữ ký của entry đã được xác minh |
| m | Entry được liệt kê trong manifest |
| k | Tìm thấy ít nhất một certificate tương ứng trong keystore được kiểm tra |

Output chi tiết có thể hiển thị signer DN, certificate chain, digest algorithm, signature algorithm và timestamp.

### Kiểm tra signer cụ thể

Khi cần xác nhận JAR được ký bởi alias dự kiến, có thể chỉ định keystore và alias ở cuối lệnh verify:

~~~bash
jarsigner -verify -verbose -certs \
  -keystore trusted-signers.p12 \
  -storetype PKCS12 \
  app-signed.jar \
  acme
~~~

Alias sau tên JAR yêu cầu certificate dùng để xác minh entry phải khớp với alias tương ứng trong keystore. Đây là bước hữu ích khi pipeline chỉ chấp nhận artifact do một signer cụ thể phát hành.

Không nhầm việc chữ ký khớp về mặt mật mã với việc danh tính signer đã được tổ chức tin cậy. Cần kiểm tra certificate chain và fingerprint qua nguồn đáng tin cậy.

## 8. Chữ ký hợp lệ khác với signer đáng tin cậy

Một JAR có thể có chữ ký mật mã hợp lệ nhưng certificate của signer là self-signed hoặc chain không dẫn tới CA được tin cậy.

Phân biệt ba câu hỏi:

1. **Integrity**: entry có bị sửa sau khi ký không?
2. **Signature authenticity**: chữ ký có khớp public key trong certificate không?
3. **Signer trust**: certificate có xác thực đúng danh tính nhà phát hành và được chính sách tin cậy chấp nhận không?

Ví dụ lab dùng certificate tự ký có thể vượt qua kiểm tra chữ ký và digest nhưng vẫn tạo warning signerSelfSigned hoặc chainNotValidated. Điều đó không biến certificate thử nghiệm thành danh tính nhà phát hành được CA xác thực.

Khi đánh giá JAR phát hành:

- Xác minh certificate chain.
- Kiểm tra Subject, Issuer, validity và KeyUsage/ExtendedKeyUsage.
- Kiểm tra certificate fingerprint với thông tin do nhà phát hành công bố qua kênh độc lập.
- Kiểm tra timestamp và warning.
- So sánh signer với danh sách signer được tổ chức chấp nhận.
- Kiểm tra artifact được tải từ nguồn phát hành chính thức.

jarsigner có thể dùng keystore mặc định hoặc keystore được chỉ định để cung cấp thêm thông tin certificate. Với verification chi tiết, -certs giúp hiển thị certificate của signer. Không coi một dòng jar verified là bằng chứng duy nhất rằng publisher đã được xác thực theo chính sách của tổ chức.

## 9. Timestamp cho chữ ký JAR

Timestamp ghi nhận thời điểm chữ ký được tạo thông qua Time Stamping Authority (TSA). Timestamp token được lưu cùng signature block.

Tạo timestamp bằng URL TSA:

~~~bash
jarsigner \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -tsa https://tsa.example.com \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

URL trong ví dụ là địa chỉ minh họa. Khi phát hành, sử dụng endpoint TSA do CA hoặc nhà cung cấp dịch vụ ký cung cấp.

Có thể dùng -tsacert alias nếu certificate TSA được lưu trong keystore và có Subject Information Access extension chứa URL TSA:

~~~bash
jarsigner -tsacert tsa-certificate ...
~~~

Tùy chọn liên quan:

| Tùy chọn | Công dụng |
|---|---|
| -tsa URL | Chỉ định URL của TSA |
| -tsacert alias | Lấy thông tin TSA từ certificate trong keystore |
| -tsapolicyid OID | Gửi policy identifier tới TSA |
| -tsadigestalg algorithm | Chọn digest algorithm cho timestamp request |

Trên JDK 26, digest mặc định cho timestamp request là SHA-384 nếu không chỉ định -tsadigestalg.

### Vì sao timestamp hữu ích?

Nếu certificate ký JAR hết hạn sau ngày phát hành, timestamp hợp lệ có thể giúp xác định JAR đã được ký khi certificate còn hiệu lực. Việc chấp nhận chữ ký sau thời điểm certificate hết hạn vẫn phụ thuộc quy tắc xác minh, trạng thái certificate, timestamp chain và chính sách thuật toán của runtime.

Timestamp không làm certificate bị thu hồi trở lại thành đáng tin cậy và không cứu được chữ ký dùng thuật toán đã bị vô hiệu hóa.

Không có timestamp, jarsigner có thể phát informational warning noTimestamp. Với phần mềm phân phối lâu dài, nên dùng TSA đáng tin cậy theo chính sách release.

## 10. Thuật toán digest và signature

Ký JAR sử dụng hai loại thuật toán:

- **Digest algorithm** tính hash của entry và các phần manifest.
- **Signature algorithm** dùng private key để ký dữ liệu digest hoặc cấu trúc chữ ký tương ứng.

Trong JDK 26, digest algorithm mặc định của jarsigner là SHA-384 nếu không chỉ định -digestalg. Signature algorithm mặc định phụ thuộc loại và kích thước private key.

Có thể chỉ định rõ thuật toán khi cần:

~~~bash
jarsigner \
  -digestalg SHA-384 \
  -sigalg SHA384withRSA \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

Thuật toán signature phải tương thích với private key và provider đang cài đặt.

JDK có các security properties như jdk.jar.disabledAlgorithms và jdk.security.legacyAlgorithms để kiểm soát thuật toán bị vô hiệu hóa hoặc bị xem là legacy. JAR dùng thuật toán bị disable có thể bị xem như chưa ký; thuật toán legacy có thể tạo warning.

Không dùng SHA-1 hoặc thuật toán yếu cho artifact mới. Cũng không nên cố định một thuật toán mà không kiểm tra khả năng tương thích với các JDK runtime mục tiêu. Giá trị mặc định có thể thay đổi theo release để tăng mức bảo mật.

## 11. Ký nhiều lần và nhiều signer

Một JAR có thể được ký bởi nhiều signer. Chạy jarsigner nhiều lần với alias khác nhau sẽ thêm một cặp signature file và signature block cho mỗi signer.

Ví dụ:

~~~bash
jarsigner -keystore release-a.p12 -signedjar stage-a.jar app.jar releaseA
jarsigner -keystore release-b.p12 -signedjar app-final.jar stage-a.jar releaseB
~~~

JAR cuối cùng có thể chứa nhiều cặp chữ ký trong META-INF. Khi xác minh, jarsigner kiểm tra các chữ ký tương ứng.

Nhiều chữ ký hữu ích khi:

- Hai tổ chức cùng phê duyệt artifact.
- Một nhà phát hành và một đơn vị phân phối cần ký độc lập.
- Quy trình release yêu cầu chữ ký của nhiều vai trò.

Chữ ký của signer mới không xóa chữ ký trước đó. Tuy nhiên, tất cả signer và certificate chain đều cần được đánh giá theo chính sách phát hành.

## 12. Những tùy chọn jarsigner thường dùng

| Tùy chọn | Ý nghĩa |
|---|---|
| -keystore | Chọn keystore chứa signing key hoặc certificate dùng khi verify |
| -storetype | Chọn loại keystore như PKCS12 hoặc JKS |
| -signedjar | Đặt tên file JAR đã ký |
| -verify | Xác minh chữ ký JAR |
| -verbose | Hiển thị chi tiết quá trình ký/xác minh |
| -certs | Hiển thị thông tin certificate khi verify verbose |
| -sigfile | Đặt tên cơ sở cho file .SF và signature block |
| -digestalg | Chọn digest algorithm cho entry |
| -sigalg | Chọn signature algorithm tương thích private key |
| -tsa | Tạo timestamp bằng TSA URL |
| -tsacert | Dùng certificate TSA trong keystore |
| -revCheck | Bật kiểm tra thu hồi certificate qua OCSP/CRL |
| -strict | Làm cho severe warnings ảnh hưởng exit code |
| -certchain | Cung cấp certificate chain khi private-key entry không có chain đầy đủ |
| -storepass | Cung cấp password keystore |
| -keypass | Cung cấp password private key |

Một số tùy chọn như -storepass và -keypass chỉ cần khi ký; verification không cần password keystore để kiểm tra chữ ký cơ bản.

### Password và CI/CD

Không ghi password thật trong command line hoặc file script được commit. JDK 26 hỗ trợ password modifier dạng environment variable và file:

~~~bash
jarsigner \
  -storepass:env SIGNING_STORE_PASSWORD \
  -keypass:env SIGNING_KEY_PASSWORD \
  -keystore signing.p12 \
  -storetype PKCS12 \
  app.jar \
  acme
~~~

Chỉ dùng biến môi trường được secret manager của CI cấp và bảo vệ. Với thao tác thủ công, để jarsigner hỏi password tương tác thường an toàn hơn việc lưu password trong lịch sử shell.

### Ký bằng HSM hoặc PKCS#11

Nếu private key được giữ trong hardware token hoặc HSM, không cần xuất private key ra file. Khi provider PKCS#11 đã được cấu hình, jarsigner có thể truy cập token bằng:

~~~bash
jarsigner \
  -keystore NONE \
  -storetype PKCS11 \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

Token có thể yêu cầu PIN hoặc protected authentication path. Cấu hình provider, token và quyền truy cập theo tài liệu của thiết bị.

## 13. -strict và xử lý warning trong pipeline

Theo mặc định, jarsigner có thể trả exit code 0 khi ký hoặc verify không thất bại nhưng có severe warning. Khi thêm -strict, severe warnings được phản ánh trong exit code.

Ví dụ:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Các severe warnings thường gặp:

| Warning | Ý nghĩa |
|---|---|
| hasExpiredCert | Certificate signer đã hết hạn |
| notYetValidCert | Certificate signer chưa có hiệu lực |
| chainNotValidated | Không xác minh được certificate chain |
| signerSelfSigned | Certificate signer tự ký |
| disabledAlg | Thuật toán bị chính sách bảo mật vô hiệu hóa |
| badKeyUsage | KeyUsage không cho phép ký code |
| badExtendedKeyUsage | ExtendedKeyUsage không cho phép ký code |
| hasUnsignedEntry | JAR có entry chưa được integrity-check |
| notSignedByAlias | Entry được ký bởi alias khác alias được yêu cầu |
| aliasNotInStore | Signer không có alias tương ứng trong keystore được chỉ định |

Các informational warnings có thể gồm:

- noTimestamp: chữ ký không có timestamp.
- legacyAlg: sử dụng thuật toán được xem là legacy.
- hasExpiringCert: certificate sắp hết hạn.
- extraAttributesDetected: có POSIX permission hoặc symlink attributes không được chữ ký bảo vệ.

Không phải mọi warning đều có cùng mức nghiêm trọng. Đọc nội dung warning và áp dụng chính sách release. Trong CI, thường nên dùng -strict và yêu cầu certificate chain, signer, thuật toán, timestamp và entry coverage đáp ứng chính sách.

Lưu ý: -strict làm severe warnings ảnh hưởng exit status; informational warnings vẫn có thể không làm lệnh thất bại.

## 14. Điều gì xảy ra nếu sửa JAR sau khi ký?

Chữ ký bảo vệ digest của các entry được ký. Nếu thay đổi nội dung một entry sau khi ký, digest tính lại sẽ không khớp và verification thất bại.

Ví dụ:

1. Ký app.jar thành app-signed.jar.
2. Mở archive và sửa com/acme/Main.class.
3. Chạy jarsigner -verify.
4. Verification phát hiện entry đã thay đổi.

Nếu thêm entry mới sau khi ký, entry mới có thể không có digest tương ứng trong signature của signer. JAR có thể xuất hiện warning hasUnsignedEntry vì entry mới chưa được integrity-check.

Vì vậy, quy trình release phải:

- Hoàn tất compile và packaging trước khi ký.
- Không sửa manifest hoặc resource sau khi ký.
- Không chèn dependency hoặc class mới vào JAR đã ký.
- Chạy verification sau khi ký.
- Phát hành đúng file output đã verify.
- Nếu cần thay đổi nội dung, tạo lại JAR và ký lại từ đầu.

Chữ ký không bảo vệ các thuộc tính filesystem như POSIX permission hoặc symlink metadata trong mọi trường hợp. jarsigner có thể cảnh báo khi phát hiện những thuộc tính này.

## 15. Ví dụ thực hành hoàn chỉnh Java 17+

Ví dụ sau tạo một executable JAR, ký bằng certificate thử nghiệm, xác minh và chạy chương trình. Certificate tự ký chỉ dùng để học quy trình, không dùng để phát hành sản phẩm cho người dùng.

Cấu trúc thư mục:

~~~text
jar-signing-demo/
  src/
    com/acme/Main.java
  out/
  signing.p12
  app.jar
  app-signed.jar
~~~

### Bước 1: Tạo source

Tệp src/com/acme/Main.java:

~~~java
package com.acme;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from signed JAR");
    }
}
~~~

### Bước 2: Biên dịch

~~~bash
javac --release 17 -d out src/com/acme/Main.java
~~~

### Bước 3: Tạo JAR

~~~bash
jar --create --file app.jar --main-class com.acme.Main -C out .
~~~

### Bước 4: Tạo signing key

~~~bash
keytool -genkeypair -alias acme -keyalg RSA -keysize 3072 -validity 3650 -dname "CN=Acme Demo, O=Acme, C=VN" -keystore signing.p12 -storetype PKCS12
~~~

Nhập password theo prompt và kiểm tra alias:

~~~bash
keytool -list -v -keystore signing.p12 -storetype PKCS12 -alias acme
~~~

### Bước 5: Ký sang file mới

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar acme
~~~

### Bước 6: Xác minh chữ ký

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Với certificate tự ký, output có thể chứa warning về signer self-signed, chain hoặc timestamp. Đây là kết quả dự kiến của ví dụ lab. Không dùng certificate tự ký làm bằng chứng về danh tính nhà phát hành.

### Bước 7: Chạy JAR đã ký

~~~bash
java -jar app-signed.jar
~~~

Stdout:

~~~text
Hello from signed JAR
~~~

Chương trình vẫn chạy như một executable JAR thông thường. Việc ký bổ sung cơ chế kiểm tra integrity/authenticity; nó không thay đổi logic của chương trình.

## 16. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jarsigner không tìm thấy alias | Alias sai hoặc keystore không chứa private key | Dùng keytool -list -v kiểm tra alias và entry type |
| Cannot recover key | Sai key password hoặc private key không thể truy cập | Kiểm tra key password, provider và token |
| Keystore password was incorrect | Sai password hoặc sai store type | Kiểm tra password và PKCS12/JKS |
| JAR verification failed | Entry đã bị thay đổi hoặc signature metadata không hợp lệ | Build lại JAR và ký lại |
| hasUnsignedEntry | Có entry không được ký hoặc được thêm sau khi ký | Đóng gói hoàn chỉnh trước khi ký và kiểm tra toàn bộ entry |
| signerSelfSigned | Certificate signer tự ký | Dùng certificate CA cấp cho phát hành thật |
| chainNotValidated | Thiếu intermediate/root CA hoặc chain không được tin cậy | Kiểm tra chain và trust anchors của môi trường verify |
| noTimestamp | Không có timestamp token | Dùng TSA được tổ chức hoặc CA chấp nhận |
| disabledAlg | Thuật toán ký hoặc digest bị JDK policy vô hiệu hóa | Dùng thuật toán và key strength còn được hỗ trợ |
| badKeyUsage | Certificate không cho phép code signing | Yêu cầu certificate có KeyUsage phù hợp |
| badExtendedKeyUsage | EKU không phù hợp mục đích ký code | Kiểm tra certificate profile với CA |
| Timestamp failure | TSA không truy cập được hoặc timestamp response không hợp lệ | Kiểm tra endpoint, mạng, certificate và policy TSA |
| Verification khác giữa các JDK | Security properties hoặc thuật toán được hỗ trợ khác nhau | Kiểm tra jdk.jar.disabledAlgorithms và test trên JDK mục tiêu |
| JAR báo verified nhưng publisher không được xác nhận | Chữ ký hợp lệ nhưng signer certificate chưa được tin cậy | Xác minh fingerprint, certificate chain và danh tính signer |

## 17. Quy trình ký JAR trong CI/CD

Một pipeline phát hành nên tách bước build, sign và verify:

1. Build source với JDK release đã pin.
2. Chạy unit test và integration test.
3. Đóng gói JAR cuối cùng và kiểm tra manifest.
4. Lấy signing key từ keystore bảo vệ hoặc HSM.
5. Ký JAR bằng alias được phê duyệt.
6. Dùng TSA đáng tin cậy để tạo timestamp theo chính sách.
7. Chạy jarsigner -verify -strict -verbose -certs.
8. Xác nhận signer certificate, chain, timestamp và thuật toán.
9. Lưu hash của artifact đã ký và provenance của build.
10. Phát hành đúng artifact đã verify; không chỉnh sửa sau khi ký.

Nên giới hạn quyền sử dụng private key cho release job cần thiết. Không đưa signing key hoặc password vào source repository, image build không tin cậy hoặc log CI.

Nếu dùng HSM, ưu tiên ký trực tiếp trong thiết bị để private key không rời khỏi phần cứng. Quản lý quyền ký, audit log, backup và rotation theo chính sách của tổ chức.

## 18. Ghi nhớ

- jarsigner ký và xác minh JAR bằng private key và certificate trong keystore.
- Alias phải trỏ tới entry có private key để ký.
- JAR đã ký chứa manifest, signature file .SF và signature block như .RSA, .DSA hoặc .EC.
- Digest trong manifest bảo vệ nội dung entry; signature block chứa chữ ký và certificate chain.
- -signedjar tạo file output riêng, tránh ghi đè JAR đầu vào.
- -verify kiểm tra chữ ký và integrity; -verbose -certs hiển thị chi tiết signer certificate.
- Chữ ký hợp lệ về mật mã không đồng nghĩa publisher đã được tin cậy.
- Timestamp qua -tsa giúp xác định thời điểm ký và hỗ trợ xác minh sau khi certificate signer hết hạn.
- JDK 26 mặc định dùng SHA-384 cho entry digest; signature algorithm mặc định phụ thuộc loại và kích thước key.
- jdk.jar.disabledAlgorithms và jdk.security.legacyAlgorithms quyết định thuật toán bị vô hiệu hóa hoặc cảnh báo legacy.
- -strict làm severe warnings ảnh hưởng exit code; nên cân nhắc dùng trong CI.
- -revCheck bật kiểm tra thu hồi certificate qua OCSP/CRL; kiểm tra này không bật mặc định.
- Thay đổi entry sau khi ký làm hỏng integrity; thêm entry mới có thể tạo unsigned-entry warning.
- Ký JAR không mã hóa nội dung và không chứng minh chương trình an toàn.
- Chỉ phát hành artifact sau khi xác minh chữ ký, certificate chain, signer identity, timestamp và warning theo chính sách.

## Tài liệu tham khảo chính thức

- [The jarsigner Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [The keytool Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [Java Security Standard Algorithm Names — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html)
- [JAR File Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [Signing JAR Files — Oracle Java Tutorials](https://docs.oracle.com/javase/tutorial/deployment/jar/signing.html)