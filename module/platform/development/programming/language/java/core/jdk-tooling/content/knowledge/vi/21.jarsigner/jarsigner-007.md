# Artifact đã ký bằng jarsigner

**Artifact đã ký (signed artifact)** là tệp JAR đã được gắn chữ ký số để người nhận có thể kiểm tra nội dung có bị thay đổi sau khi ký hay không và xác định chứng chỉ chứa public key của người ký. Trong Java, công cụ **jarsigner** tạo và xác minh chữ ký cho JAR hoặc ZIP archive.

Một JAR đã ký vẫn chứa các class, resource và dữ liệu gốc. Chữ ký không mã hóa nội dung và không che giấu file. Nó bổ sung manifest digest, signature file và signature block để người nhận kiểm tra tính toàn vẹn của từng entry cùng chữ ký của người phát hành.

Cần phân biệt hai kết quả: **chữ ký hợp lệ về mặt mật mã** và **người ký được tin cậy theo chính sách của tổ chức hoặc môi trường triển khai**. Một JAR có thể vượt qua kiểm tra digest nhưng vẫn dùng chứng chỉ tự ký hoặc chuỗi chứng chỉ chưa được tin cậy.

## 1. Artifact đã ký là gì?

JAR là một archive dựa trên ZIP, thường chứa class file, resource, cấu hình và manifest. Khi ký bằng jarsigner, archive được cập nhật với các metadata chữ ký.

Ví dụ:

~~~text
hello-signed.jar
├── META-INF/
│   ├── MANIFEST.MF
│   ├── RELEASE.SF
│   └── RELEASE.RSA
└── com/
    └── example/
        └── Hello.class
~~~

Tên file chữ ký trong ví dụ được tạo từ alias **release**. Nếu không chỉ định **-sigfile**, jarsigner dùng tối đa tám ký tự đầu của alias, chuyển thành chữ hoa, để đặt tên cho **.SF** và signature block.

Một artifact đã ký có thể được phát hành qua Maven repository, package registry, server tải xuống hoặc hệ thống triển khai nội bộ. Bên nhận có thể chạy jarsigner để kiểm tra archive trước khi cài đặt hoặc đưa vào runtime.

### Chữ ký bảo vệ điều gì?

Chữ ký JAR cho phép kiểm tra:

- Nội dung của các entry đã ký có còn giống lúc ký hay không.
- Signature file có được ký bằng private key tương ứng với public key trong chứng chỉ hay không.
- Manifest digest có còn khớp với digest được ghi trong signature file hay không.
- Thuật toán dùng để ký có bị JDK hiện tại vô hiệu hóa hay không.

Chữ ký không:

- Mã hóa class hoặc resource.
- Bảo vệ private key của người phát hành sau khi private key đã bị lộ.
- Tự động chứng minh tổ chức phát hành là đáng tin.
- Đảm bảo chương trình an toàn hoặc không có mã độc.
- Bảo vệ các entry được thêm sau khi ký mà chưa được ký bổ sung.
- Thay thế kiểm thử, review mã nguồn hoặc kiểm tra nguồn gốc dependency.

JAR đã ký vẫn có thể được mở bằng công cụ ZIP để đọc nội dung. Bất kỳ ai có archive đều có thể xem các class và resource không được mã hóa.

## 2. Ba thành phần chữ ký trong META-INF

Khi jarsigner ký JAR, công cụ cập nhật manifest và thêm hai nhóm file chữ ký vào thư mục **META-INF**.

### MANIFEST.MF — digest của từng entry

Manifest lưu các thuộc tính chung của archive và các section riêng cho từng entry. Khi ký bằng jarsigner, mỗi file entry cần được bảo vệ có một section chứa digest của nội dung file.

Ví dụ minh họa:

~~~text
Manifest-Version: 1.0

Name: com/example/Hello.class
SHA-384-Digest: <base64-digest>
~~~

Digest được tính trên bytes của entry. Nếu nội dung **Hello.class** thay đổi, digest mới sẽ khác digest được lưu trong manifest.

Manifest cũng có thể chứa các thuộc tính ứng dụng như **Main-Class**, **Class-Path**, **Implementation-Version** và các thuộc tính khác. Các thuộc tính này có ý nghĩa riêng trong JAR; chúng không phải bản thân chữ ký số.

### RELEASE.SF — signature file

File **.SF** chứa digest của manifest hoặc từng section manifest tương ứng với entry. Nó liên kết dữ liệu manifest với chữ ký số.

Ví dụ minh họa:

~~~text
Signature-Version: 1.0
SHA-384-Digest-Manifest: <base64-manifest-digest>

Name: com/example/Hello.class
SHA-384-Digest: <base64-section-digest>
~~~

Mặc định, signature file có header chứa digest của toàn bộ manifest và manifest header để tối ưu quá trình xác minh. Nếu digest toàn manifest không khớp, quá trình xác minh có thể kiểm tra riêng các section tương ứng.

### RELEASE.RSA — signature block

File signature block chứa chữ ký số được tạo từ **.SF** bằng private key và chứa chứng chỉ hoặc certificate chain xác thực public key tương ứng.

Phần mở rộng phụ thuộc thuật toán khóa:

| Phần mở rộng | Thuật toán khóa thường gặp |
|---|---|
| .RSA | RSA hoặc RSASSA-PSS |
| .DSA | DSA |
| .EC | Elliptic Curve hoặc EdDSA |

Signature block dùng cấu trúc PKCS#7 để lưu chữ ký và chứng chỉ. Người nhận dùng public key trong chứng chỉ để xác minh chữ ký của **.SF**.

### Chuỗi liên kết

~~~text
Bytes của từng entry
        |
        v
Digest trong MANIFEST.MF
        |
        v
Digest của manifest section trong RELEASE.SF
        |
        v
Chữ ký số của RELEASE.SF trong RELEASE.RSA
        |
        v
Public key và certificate chain của signer
~~~

Mỗi lớp xác nhận lớp phía dưới. Nếu bytes của entry đã ký bị thay đổi, digest không khớp và quá trình xác minh thất bại.

## 3. jarsigner tạo signed artifact như thế nào?

jarsigner sử dụng private key được lưu trong keystore để ký JAR. Alias chỉ đến entry chứa private key; chứng chỉ đi kèm cung cấp public key và thông tin định danh người ký.

Quy trình tổng quát:

1. Tạo JAR hoàn chỉnh từ class và resource.
2. Chuẩn bị keystore chứa private key và certificate chain.
3. Chọn alias của key entry dùng ký.
4. Chạy jarsigner để cập nhật manifest và tạo signature file/signature block.
5. Xác minh artifact đầu ra.
6. Lưu artifact đã ký và kết quả xác minh trong release record.
7. Phát hành đúng bytes của artifact đã được xác minh.

Nên hoàn tất mọi thao tác thêm, xóa hoặc thay đổi entry trước bước ký. Sau khi ký, không chỉnh sửa nội dung archive rồi phát hành mà không ký và xác minh lại.

### Keystore và alias

Keystore chứa private key cùng certificate chain. Alias xác định entry chứa private key cần dùng.

Ví dụ tạo cặp RSA và chứng chỉ tự ký dùng trong môi trường học tập:

~~~bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -dname "CN=Example Release, O=Example, C=VN" \
  -keystore release.p12 \
  -storetype PKCS12
~~~

Keytool sẽ yêu cầu nhập password tương tác. Nếu không chỉ định password riêng cho private key, key password thường dùng cùng password của keystore.

Chứng chỉ tự ký phù hợp để thử nghiệm cơ chế chữ ký. Nó chưa tạo ra danh tính phát hành được một CA công khai xác nhận.

### Ký JAR và tạo output riêng

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar hello-signed.jar \
  hello.jar \
  release
~~~

Giải thích:

- **-keystore release.p12** chọn keystore.
- **-storetype PKCS12** chọn định dạng keystore.
- **-signedjar hello-signed.jar** tạo archive đã ký ở đường dẫn riêng.
- **hello.jar** là artifact đầu vào chưa ký.
- **release** là alias của private key entry.

Nếu bỏ **-signedjar**, jarsigner ghi kết quả ký đè lên JAR đầu vào. Trong quy trình release, nên tạo output riêng để giữ lại artifact đầu vào phục vụ so sánh và điều tra.

Không đặt password trực tiếp trong command line hoặc script phát hành. Để công cụ hỏi password tương tác hoặc dùng cơ chế cung cấp secret phù hợp với hệ thống build.

## 4. Ví dụ hoàn chỉnh: tạo và chạy một JAR đã ký

Ví dụ dùng Java 17 trở lên. Các lệnh **javac**, **jar**, **keytool** và **jarsigner** cần đến từ JDK tương ứng.

### Cấu trúc source

~~~text
signed-artifact-demo/
└── src/
    └── com/
        └── example/
            └── Hello.java
~~~

Tệp **src/com/example/Hello.java**:

~~~java
package com.example;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from signed artifact.");
    }
}
~~~

### Bước 1: Biên dịch

Từ thư mục gốc dự án:

~~~bash
javac --release 17 -d out src/com/example/Hello.java
~~~

Lệnh tạo class file tại **out/com/example/Hello.class**.

### Bước 2: Tạo JAR có Main-Class

~~~bash
jar --create \
  --file hello.jar \
  --main-class com.example.Hello \
  -C out .
~~~

Kiểm tra JAR đầu vào:

~~~bash
jar --list --file hello.jar
~~~

### Bước 3: Tạo keystore thử nghiệm

~~~bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -dname "CN=Example Release, O=Example, C=VN" \
  -keystore release.p12 \
  -storetype PKCS12
~~~

Trong ví dụ, chứng chỉ tự ký được tạo để minh họa. Khi phát hành production, dùng chứng chỉ code signing và chuỗi tin cậy theo chính sách tổ chức.

### Bước 4: Ký artifact

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar hello-signed.jar \
  hello.jar \
  release
~~~

### Bước 5: Xem các file chữ ký

~~~bash
jar --list --file hello-signed.jar
~~~

Các entry chữ ký chính dự kiến có dạng:

~~~text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
com/example/Hello.class
~~~

Thứ tự entry có thể khác. Các thư mục và entry khác phụ thuộc cách tạo JAR. Tên **.SF** và **.RSA** trong ví dụ xuất phát từ alias **release**.

### Bước 6: Xác minh artifact

~~~bash
jarsigner -verify -verbose -certs hello-signed.jar
~~~

Lệnh này kiểm tra chữ ký và hiển thị thông tin chứng chỉ khi có thể. Vì ví dụ dùng chứng chỉ tự ký, output có thể kèm cảnh báo signer self-signed hoặc certificate chain chưa được xác thực. Điều đó không có nghĩa digest và chữ ký toán học nhất thiết sai; nó có nghĩa danh tính người ký chưa được xác nhận bởi trust anchor phù hợp.

### Bước 7: Chạy JAR

~~~bash
java -jar hello-signed.jar
~~~

Output:

~~~text
Hello from signed artifact.
~~~

Chạy thành công chỉ chứng minh chương trình khởi chạy trong môi trường đó. Vẫn cần kiểm tra chữ ký, certificate chain, warning, nguồn artifact và chính sách phát hành.

### Khác biệt giữa demo và production

| Demo học tập | Phát hành production |
|---|---|
| Chứng chỉ tự ký | Chứng chỉ code signing theo chính sách tổ chức |
| Không cần TSA công khai | Thường dùng timestamp authority đáng tin |
| Có thể xuất hiện cảnh báo chain | Chain phải được xác thực theo trust policy |
| Keystore file thử nghiệm | Private key được bảo vệ, có thể dùng HSM/token |
| Xác minh thủ công | Xác minh tự động trong CI/CD với -strict |

## 5. jarsigner xác minh signed artifact ra sao?

Khi chạy:

~~~bash
jarsigner -verify hello-signed.jar
~~~

jarsigner thực hiện các bước xác minh chính:

1. Xác minh chữ ký trong signature block đối với file **.SF**.
2. Kiểm tra digest trong **.SF** có khớp các section tương ứng của manifest hay không.
3. Đọc từng entry có section tương ứng trong **.SF**, tính lại digest của bytes và so sánh với digest trong manifest.
4. Kiểm tra việc sử dụng các thuật toán đã bị vô hiệu hóa theo security properties của JDK.

Nếu một bước xác minh nghiêm trọng thất bại, công cụ báo lỗi thay vì coi artifact là hợp lệ.

### Xác minh chữ ký khác xác minh danh tính

Chữ ký toán học có thể hợp lệ vì **.SF** được ký bằng private key tương ứng với public key trong chứng chỉ. Tuy nhiên, chứng chỉ đó có thể:

- Là chứng chỉ tự ký.
- Không có chuỗi chứng chỉ dẫn đến CA được tin cậy.
- Đã hết hạn hoặc chưa đến thời điểm hiệu lực.
- Có KeyUsage hoặc ExtendedKeyUsage không cho phép code signing.
- Đã bị thu hồi hoặc không thể kiểm tra trạng thái thu hồi.
- Sử dụng thuật toán đã bị JDK vô hiệu hóa.

Vì vậy, đọc cả thông tin chứng chỉ và warning của jarsigner. Không chỉ dựa vào dòng **jar verified** để quyết định phát hành.

### Xác minh với thông tin chi tiết

~~~bash
jarsigner -verify -verbose -certs hello-signed.jar
~~~

Các ký hiệu thường gặp trong output verbose:

| Ký hiệu | Ý nghĩa |
|---|---|
| s | Chữ ký của entry đã được xác minh |
| m | Entry được liệt kê trong manifest |
| k | Có ít nhất một chứng chỉ được tìm thấy trong keystore |

Ký hiệu **k** chỉ cho biết có chứng chỉ phù hợp được tìm thấy trong keystore đang kiểm tra. Nó không tự chứng minh certificate chain được tin cậy hoặc tổ chức phát hành đã được xác minh.

### Kiểm tra nghiêm ngặt

~~~bash
jarsigner -verify -strict hello-signed.jar
~~~

**-strict** khiến exit code phản ánh các severe warning. Nếu không dùng **-strict**, một số severe warning có thể được hiển thị nhưng tiến trình vẫn trả exit code 0. Vì vậy, release pipeline cần dùng **-strict** và xử lý warning theo chính sách.

Một số severe warning quan trọng:

- Chứng chỉ signer hết hạn hoặc chưa có hiệu lực.
- Certificate chain không được xác thực.
- Chứng chỉ signer tự ký.
- Thuật toán bị vô hiệu hóa.
- Chứng chỉ không có KeyUsage phù hợp để ký code.
- JAR có entry chưa được ký.
- Entry được ký bởi alias khác với alias được yêu cầu.

Ví dụ self-signed ở trên có thể không vượt qua **-strict** do cảnh báo trust. Đây là kết quả dự kiến của môi trường thử nghiệm, không phải cấu hình phát hành production.

## 6. Entry đã ký, entry chưa ký và thay đổi sau khi ký

jarsigner ký các file entry của JAR bằng cách ghi digest vào manifest và signature file. Tuy nhiên, tình trạng chữ ký phụ thuộc thời điểm entry được thêm vào archive.

### Sửa nội dung entry đã ký

Nếu một class hoặc resource đã được ký bị thay đổi sau đó, digest mới không còn khớp digest trong manifest. Khi xác minh, jarsigner báo lỗi toàn vẹn.

Ví dụ về thao tác có thể làm hỏng chữ ký:

- Thay nội dung class file.
- Thay resource hoặc cấu hình đã ký.
- Sửa manifest theo cách làm thay đổi section đã được ký.
- Repackage archive sau khi sửa nội dung entry.

Không sửa artifact đã ký rồi phát hành lại mà không ký lại toàn bộ artifact theo quy trình.

### Thêm entry mới sau khi ký

Nếu một file mới được thêm vào JAR sau khi ký, entry mới có thể không có digest trong signature file hiện tại. Các entry cũ vẫn có thể xác minh thành công, nhưng JAR chứa entry chưa được kiểm tra toàn vẹn.

jarsigner có severe warning **hasUnsignedEntry** cho trường hợp này. Warning có mã 16 và được **-strict** coi là lỗi.

Do đó, một lần verify không có failure về chữ ký cũ chưa đủ để kết luận mọi entry trong archive đều được bảo vệ. Hãy kiểm tra unsigned entries và dùng **-strict** trong CI.

### Thứ tự xử lý đúng

1. Compile và đóng gói tất cả class/resource.
2. Thêm manifest attributes cần thiết.
3. Kiểm tra nội dung và dependency của JAR.
4. Ký artifact sau cùng.
5. Xác minh bằng jarsigner.
6. Lưu checksum, chữ ký và kết quả kiểm tra trong release record.
7. Phát hành đúng file đã được xác minh; không sửa archive sau bước ký.

## 7. Timestamp và vòng đời chứng chỉ

Khi ký JAR, có thể yêu cầu Time-Stamp Authority (TSA) tạo timestamp cho chữ ký.

Timestamp token được lưu cùng signature block. Nó cung cấp bằng chứng về thời điểm ký, giúp hệ thống đánh giá liệu chứng chỉ signer còn hiệu lực tại thời điểm ký hay không.

Ví dụ cú pháp:

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -tsa https://tsa.example.org \
  -signedjar hello-signed.jar \
  hello.jar \
  release
~~~

**https://tsa.example.org** chỉ là URL minh họa; thay bằng endpoint TSA thực tế được tổ chức tin cậy và cho phép sử dụng.

Các tùy chọn liên quan:

| Tùy chọn | Ý nghĩa |
|---|---|
| -tsa URL | Gửi yêu cầu timestamp đến TSA tại URL |
| -tsacert alias | Chọn chứng chỉ TSA trong keystore; URL có thể được lấy từ SIA extension của chứng chỉ |
| -tsapolicyid OID | Chỉ định TSA policy identifier |
| -tsadigestalg algorithm | Chọn digest algorithm cho timestamp request |

Timestamp không làm cho chứng chỉ signer có hiệu lực vô thời hạn. TSA certificate, timestamp token, certificate chain và thuật toán liên quan vẫn cần được xác minh theo chính sách. Nếu không có timestamp, JAR có thể không còn xác minh được sau ngày hết hạn chứng chỉ signer hoặc sau một thời điểm thu hồi trong tương lai.

### Kiểm tra trạng thái thu hồi

Tùy chọn **-revCheck** bật kiểm tra thu hồi chứng chỉ khi ký hoặc xác minh:

~~~bash
jarsigner -verify -revCheck hello-signed.jar
~~~

Khi bật, jarsigner có thể cần kết nối mạng để lấy OCSP response hoặc CRL. Revocation checking không được bật mặc định. Pipeline cần tính đến network access, timeout và chính sách xử lý khi dịch vụ kiểm tra trạng thái chứng chỉ không khả dụng.

## 8. Thuật toán digest và signature

Digest algorithm và signature algorithm là hai phần khác nhau:

- **Digest algorithm** tạo hash của bytes trong entry hoặc manifest.
- **Signature algorithm** dùng private key để ký dữ liệu digest hoặc signature file.

Một số tùy chọn:

- **-digestalg**: chỉ định thuật toán digest của các entry.
- **-sigalg**: chỉ định thuật toán chữ ký, phải tương thích với private key.

Trong Oracle JDK 24, digest mặc định của jarsigner là SHA-384. Signature algorithm mặc định được chọn dựa trên loại và kích thước private key. Ví dụ, RSA 3072-bit sử dụng SHA384withRSA theo bảng mặc định JDK 24.

Không nên cố định một thuật toán cũ chỉ để tương thích nếu nó đã bị đánh dấu yếu hoặc vô hiệu hóa. JDK sử dụng các security properties như **jdk.jar.disabledAlgorithms** và **jdk.security.legacyAlgorithms** để đánh giá thuật toán. Một JAR sử dụng thuật toán bị vô hiệu hóa có thể bị xử lý như JAR unsigned.

Nếu phải hỗ trợ JDK cũ, kiểm tra khả năng tương thích giữa các phiên bản và chọn thuật toán phù hợp với chính sách bảo mật thay vì hạ mức an toàn tùy tiện.

## 9. Nhiều người ký một artifact

Một JAR có thể được ký nhiều lần bằng nhiều private key khác nhau. Mỗi lần ký bằng alias khác sẽ tạo một cặp signature file và signature block tương ứng.

Ví dụ:

~~~bash
jarsigner app.jar release-team-a
jarsigner app.jar release-team-b
~~~

Archive có thể chứa nhiều cặp file chữ ký, mỗi cặp đại diện cho một signer. Tên file thực tế được suy ra từ alias hoặc **-sigfile**; các alias khác nhau cần tạo tên signature file không xung đột.

Nhiều chữ ký có thể hữu ích khi yêu cầu phê duyệt từ nhiều đơn vị. Khi xác minh, cần kiểm tra mọi signer, certificate chain, timestamp và policy. Không nên chỉ xác minh một alias nếu quy trình yêu cầu tất cả signer cụ thể.

## 10. Tùy chọn jarsigner hữu ích khi làm việc với artifact

| Tùy chọn | Mục đích |
|---|---|
| -keystore | Chọn keystore dùng ký hoặc hỗ trợ kiểm tra chứng chỉ |
| -storetype | Chọn định dạng keystore |
| -signedjar | Ghi artifact đã ký ra file riêng |
| -sigfile | Đặt base name cho .SF và signature block |
| -digestalg | Chọn digest algorithm |
| -sigalg | Chọn signature algorithm |
| -verify | Xác minh chữ ký JAR |
| -verbose | Hiển thị chi tiết quá trình ký/xác minh |
| -certs | Hiển thị thông tin chứng chỉ khi verify verbose |
| -strict | Chuyển severe warning thành exit code lỗi |
| -tsa | Yêu cầu TSA tạo timestamp |
| -tsacert | Chọn TSA certificate trong keystore |
| -revCheck | Bật kiểm tra trạng thái thu hồi chứng chỉ |
| -sectionsonly | Chỉ đưa digest các section vào .SF; chủ yếu dùng cho kiểm thử |

Kiểm tra tùy chọn theo JDK đang cài:

~~~bash
jarsigner -version
jarsigner -help
jarsigner -verify -help
~~~

Không phải mọi JDK hoặc provider đều có cùng default algorithm và security policy. Hãy kiểm tra toolchain thực tế trong pipeline release.

## 11. Tích hợp kiểm tra signed artifact vào CI/CD

Một pipeline phát hành nên tạo artifact và xác minh artifact đúng file sẽ được phân phối.

Quy trình tham khảo:

1. Build ứng dụng và tạo JAR.
2. Chạy unit test, integration test và kiểm tra dependency.
3. Xác định signer alias và keystore từ secret management hoặc signing service.
4. Ký JAR bằng jarsigner.
5. Nếu cần, yêu cầu TSA timestamp.
6. Chạy **jarsigner -verify -verbose -certs**.
7. Chạy **jarsigner -verify -strict** và xử lý mọi severe warning.
8. Kiểm tra signer certificate, chain, expiry, usage và timestamp.
9. Tính checksum của signed artifact và lưu cùng release metadata.
10. Đưa đúng artifact đã xác minh vào repository hoặc deployment.

Ví dụ bước verify trong CI:

~~~bash
jarsigner -verify -strict -verbose -certs build/app-signed.jar
~~~

Nếu lệnh trả exit code khác 0, pipeline cần dừng phát hành và lưu diagnostic để điều tra.

### Lưu release evidence

Nên lưu cùng mỗi bản phát hành:

- Tên và version artifact.
- SHA-256 checksum của file JAR cuối cùng.
- Signer certificate fingerprint.
- Subject và issuer của certificate.
- Signature algorithm và digest algorithm.
- Timestamp và TSA identity nếu có.
- Kết quả **jarsigner -verify -strict**.
- JDK vendor/version và build identifier.
- Danh sách entry chưa ký nếu có; release production thường phải từ chối trường hợp này.

Checksum giúp nhận diện chính xác artifact đã phát hành. Nó không thay thế chữ ký số; checksum cần được phân phối qua kênh tin cậy hoặc được bảo vệ trong release metadata.

## 12. Signed JAR và các loại artifact khác

jarsigner được thiết kế cho JAR và ZIP archive. Nó không thay thế công cụ ký code signing của hệ điều hành cho các định dạng khác.

| Artifact | Cơ chế ký thường dùng |
|---|---|
| JAR | jarsigner |
| ZIP có cấu trúc JAR | jarsigner |
| Windows EXE/MSI | Authenticode và công cụ ký Windows |
| macOS app/PKG/DMG | Apple code signing và notarization |
| Container image | Image signature theo hệ sinh thái container |
| Maven/Gradle metadata | Repository checksum và cơ chế chữ ký artifact tương ứng |

Một release có thể gồm JAR, native launcher, installer và container image. Mỗi loại artifact cần quy trình ký và xác minh phù hợp. Chữ ký JAR không tự động bảo vệ installer hoặc container bên ngoài chứa nó.

## 13. Lỗi thường gặp khi xác minh artifact đã ký

### JAR unsigned hoặc thiếu signature files

Nguyên nhân có thể là artifact chưa được ký, signature files bị xóa hoặc không thể phân tích. Kiểm tra:

~~~bash
jar --list --file app.jar
~~~

Tìm **META-INF/MANIFEST.MF**, file **.SF** và signature block tương ứng. Nếu thiếu, xác nhận đúng artifact và build stage.

### Digest không khớp

Một entry hoặc manifest section đã thay đổi sau khi ký. Dùng output verbose để tìm entry gây lỗi, build lại JAR từ source và ký lại sau khi hoàn tất mọi thay đổi.

### Entry chưa ký

Có file được thêm sau lần ký cuối hoặc chỉ một tập entry được bảo vệ. **-strict** có thể phát hiện severe warning **hasUnsignedEntry**. Kiểm tra toàn bộ archive và ký lại artifact hoàn chỉnh.

### Chứng chỉ tự ký hoặc chain chưa được xác thực

Chữ ký có thể hợp lệ về mặt toán học nhưng certificate chain không dẫn đến trust anchor được chấp nhận. Dùng chứng chỉ phù hợp với chính sách phát hành, cài đặt trust anchor đúng cách và kiểm tra certificate chain.

### Chứng chỉ hết hạn hoặc chưa có hiệu lực

Kiểm tra thời gian hệ thống, certificate validity period và timestamp token. Nếu artifact được ký khi chứng chỉ còn hiệu lực, timestamp hợp lệ có thể giúp đánh giá chữ ký theo thời điểm ký; vẫn phải xác minh TSA chain và policy.

### Thuật toán bị vô hiệu hóa

JDK có thể từ chối hoặc xử lý JAR như unsigned nếu signature/digest algorithm nằm trong **jdk.jar.disabledAlgorithms**. Dùng thuật toán hiện hành được hỗ trợ và ký lại bằng toolchain phù hợp.

### Alias không khớp signer

Khi truyền alias sau tên JAR trong lệnh verify, jarsigner có thể báo entry không được ký bởi alias được chỉ định. Kiểm tra signer thực tế trong signature block và alias trong keystore.

### Timestamp hoặc TSA chain không hợp lệ

Kiểm tra TSA certificate, timestamp token, policy, thời hạn và khả năng truy cập dịch vụ. Không bỏ qua lỗi TSA chỉ để làm pipeline thành công.

### Revocation check thất bại

Nếu dùng **-revCheck**, OCSP/CRL endpoint có thể không truy cập được hoặc certificate bị thu hồi. Kiểm tra network, proxy, firewall và trạng thái chứng chỉ; tuân thủ chính sách fail-open/fail-closed đã được tổ chức phê duyệt.

## 14. Checklist trước khi phát hành artifact đã ký

- Build xong tất cả class, resource và metadata trước khi ký.
- Chọn đúng JAR đầu vào và đúng output artifact.
- Dùng private key entry được phép ký release.
- Bảo vệ keystore/private key và password bằng secret management.
- Kiểm tra signer certificate, Subject, issuer, validity và key usage.
- Chọn digest/signature algorithm phù hợp với JDK mục tiêu.
- Dùng timestamp authority đáng tin nếu quy trình phát hành yêu cầu.
- Xác minh bằng **jarsigner -verify -verbose -certs**.
- Dùng **-strict** trong CI để bắt severe warning.
- Xác nhận mọi entry cần bảo vệ đã được ký.
- Không sửa JAR sau khi ký.
- Kiểm tra certificate chain và trust policy độc lập với kiểm tra digest.
- Lưu checksum và thông tin signer cùng release evidence.
- Kiểm thử đúng artifact đã ký trên runtime/deployment environment.
- Nếu release có EXE, MSI, PKG, DMG hoặc container image, thực hiện quy trình ký riêng cho từng loại.

## 15. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Signed artifact | Artifact có chữ ký số để xác minh tính toàn vẹn và nguồn ký |
| JAR | Archive ZIP chứa class, resource và metadata Java |
| Manifest | File META-INF/MANIFEST.MF chứa thuộc tính chung và section theo entry |
| Digest | Giá trị băm của bytes hoặc manifest section |
| Signature file | File .SF chứa digest của manifest/section |
| Signature block | File .RSA, .DSA hoặc .EC chứa chữ ký và chứng chỉ |
| Signer | Chủ thể sở hữu private key dùng ký artifact |
| Certificate chain | Chuỗi chứng chỉ liên kết signer đến CA/trust anchor |
| TSA | Time-Stamp Authority cung cấp timestamp token |
| Timestamp | Bằng chứng thời điểm ký được TSA xác nhận |
| Unsigned entry | Entry chưa có digest được bảo vệ bởi chữ ký tương ứng |
| -strict | Chuyển severe warning thành exit code lỗi |
| -revCheck | Bật kiểm tra thu hồi chứng chỉ qua OCSP/CRL |
| Trust anchor | Chứng chỉ gốc được cấu hình là điểm tin cậy |
| Code signing | Cơ chế ký số phần mềm để xác minh nguồn phát hành và tính toàn vẹn |

Artifact JAR đã ký là một phần của chuỗi cung ứng phần mềm. Hãy ký sau khi build hoàn tất, xác minh toàn bộ entry và signer certificate, xử lý warning nghiêm ngặt trong CI, dùng timestamp phù hợp và phát hành đúng bytes đã được kiểm tra.

## Tài liệu tham khảo

- Oracle JDK 24 — The jarsigner Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Oracle JDK 24 — JAR File Specification: https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html
- Oracle JDK 24 — The keytool Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html
- Oracle JDK 24 — Java Security Developer's Guide: https://docs.oracle.com/en/java/javase/24/security/security-developer-guide.pdf