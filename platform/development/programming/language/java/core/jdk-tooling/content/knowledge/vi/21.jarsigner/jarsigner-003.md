# Kiểm tra chữ ký JAR bằng `jarsigner`

`jarsigner` là công cụ trong JDK dùng để ký và xác minh chữ ký số của file JAR. Khi kiểm tra một JAR đã ký, công cụ xác nhận chữ ký được tạo bởi khóa tương ứng với chứng thư của người ký, kiểm tra digest của các entry đã ký và đưa ra cảnh báo về chứng thư, chuỗi tin cậy, timestamp, thuật toán và các entry chưa được bảo vệ.

Lệnh kiểm tra cơ bản:

~~~text
jarsigner -verify application.jar
~~~

Trong quy trình phát hành, nên kiểm tra chi tiết hơn:

~~~text
jarsigner -verify -strict -verbose -certs application.jar
~~~

Đọc kết quả cần tách ba câu hỏi:

1. **Toàn vẹn:** các file được ký có còn khớp digest tại thời điểm ký không?
2. **Chứng thư:** chứng thư người ký còn hiệu lực, có mục đích code signing phù hợp và chuỗi chứng thư có được xác thực theo trust policy không?
3. **Danh tính:** chứng thư có thuộc đúng nhà phát hành mà tổ chức mong đợi không?

Một chữ ký toán học hợp lệ chưa tự chứng minh nhà phát hành là đáng tin. Phải xác minh fingerprint, danh tính chứng thư và chuỗi tin cậy bằng nguồn độc lập.

Toolchain được kiểm tra cho bài này là `jarsigner 24.0.2`. Cú pháp và chính sách thuật toán có thể thay đổi theo JDK; kiểm tra `jarsigner --help`, `keytool -printcert -help` và tài liệu của đúng toolchain đang triển khai.

## 1. Chữ ký số trong JAR hoạt động như thế nào?

Chữ ký số dùng private key để ký dữ liệu và public key tương ứng để xác minh. Private key phải được giữ bí mật; chứng thư số gắn public key với danh tính của chủ thể theo một hệ thống chứng thực.

Khi ký JAR, `jarsigner` thêm thông tin vào thư mục `META-INF`:

~~~text
application.jar
  META-INF/
    MANIFEST.MF
    RELEASE.SF
    RELEASE.RSA
  com/example/App.class
  config/application.properties
~~~

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `META-INF/MANIFEST.MF` | Chứa metadata và digest của các entry được ký |
| `RELEASE.SF` | Signature file chứa digest của manifest hoặc các section trong manifest |
| `RELEASE.RSA` | Signature block chứa chữ ký của file `.SF` và chứng thư/chứng thư chain của người ký |
| `.DSA`, `.EC` | Phần mở rộng signature block có thể dùng tùy loại khóa và thuật toán |

Tên `RELEASE` chỉ là ví dụ. Tên thực tế thường được tạo từ alias ký hoặc từ tùy chọn `-sigfile`.

Luồng ký và xác minh:

~~~text
JAR entries
    |
    v
Manifest: digest for each signed entry
    |
    v
Signature file (.SF): digest of manifest/sections
    |
    v
Private key signs the .SF file
    |
    v
Signature block (.RSA / .DSA / .EC)
    |
    v
Certificate and signature are stored in JAR
    |
    v
jarsigner -verify
    |
    +--> Verify signature block and .SF
    +--> Compare .SF digests with manifest
    +--> Recalculate entry digests
    +--> Check algorithm constraints
    +--> Report certificate and timestamp warnings
~~~

Nếu nội dung của một entry đã ký bị thay đổi, digest tính lại không còn khớp với manifest và xác minh thất bại. Nếu có entry được thêm sau khi ký, entry đó có thể không nằm trong chữ ký ban đầu và bị báo là unsigned.

## 2. Phân biệt toàn vẹn chữ ký và độ tin cậy của người ký

Khi chạy `jarsigner -verify`, công cụ có thể xác minh chữ ký bằng public key nằm trong chứng thư được đóng gói cùng JAR. Việc này trả lời liệu dữ liệu đã ký có khớp chữ ký hay không.

Việc tin người ký cần thêm kiểm tra:

- Chứng thư có đúng danh tính tổ chức hoặc nhà phát hành không?
- Fingerprint có khớp giá trị được công bố qua kênh độc lập không?
- Chuỗi chứng thư có dẫn đến CA/trust anchor được tổ chức chấp nhận không?
- Chứng thư còn hiệu lực tại thời điểm ký phù hợp với timestamp không?
- Key Usage hoặc Extended Key Usage có cho phép code signing không?
- Chứng thư hoặc khóa có bị thu hồi theo chính sách kiểm tra không?
- Thuật toán ký và độ dài khóa có đáp ứng chính sách bảo mật hiện tại không?

Chứng thư tự ký có thể tạo chữ ký toán học hợp lệ cho một JAR thử nghiệm, nhưng không tự tạo ra danh tính nhà phát hành đã được CA tin cậy xác nhận. Vì vậy, kết quả `jar verified` cần được đọc cùng các warning và thông tin certificate.

Không dùng riêng tên alias để nhận diện publisher. Alias chỉ là tên mục trong keystore của người kiểm tra; nó không phải danh tính được ký bên trong JAR.

## 3. Cú pháp và các tùy chọn kiểm tra

Cú pháp xác minh:

~~~text
jarsigner -verify [options] jar-file [alias...]
~~~

Các tùy chọn thường dùng:

| Tùy chọn | Công dụng |
|---|---|
| `-verify` | Xác minh chữ ký và tính toàn vẹn của JAR |
| `-strict` | Chuyển severe warnings thành lỗi qua exit code |
| `-verbose` | Hiển thị thông tin chi tiết theo từng entry |
| `-verbose:all` | Hiển thị chi tiết từng entry và thông tin signer |
| `-verbose:grouped` | Nhóm các entry theo signer |
| `-verbose:summary` | Tóm tắt entry theo signer |
| `-certs` | Hiển thị certificate information khi kết hợp `-verify` và `-verbose` |
| `-keystore file` | Chỉ định keystore để đối chiếu certificate với alias |
| `-revCheck` | Bật kiểm tra thu hồi certificate qua OCSP/CRL |
| `-version` | Hiển thị phiên bản công cụ |
| `-help` | Hiển thị trợ giúp |

Ví dụ kiểm tra nhanh:

~~~text
jarsigner -verify application.jar
~~~

Kiểm tra từng entry và signer:

~~~text
jarsigner -verify -verbose -certs application.jar
~~~

Kiểm tra nghiêm ngặt:

~~~text
jarsigner -verify -strict -verbose -certs application.jar
~~~

Nếu cần xác nhận JAR được ký bởi alias mong đợi trong keystore:

~~~text
jarsigner -verify -strict -verbose -certs -keystore release-signers.p12 application.jar release-signer
~~~

Khi truyền alias sau tên JAR, `jarsigner` kiểm tra certificate dùng để xác minh các entry có khớp một trong các alias được chỉ định trong keystore hay không. Nếu cần đối chiếu nhiều signer được phép, truyền danh sách alias theo cú pháp của công cụ.

`-keystore` trong verify mode có thể giúp hiển thị alias tương ứng với certificate. Đừng coi việc certificate xuất hiện trong một keystore bất kỳ là bằng chứng đủ để chấp nhận nhà phát hành; vẫn phải áp dụng trust policy và xác nhận fingerprint.

## 4. Đọc kết quả `-verbose`

Khi dùng `-verbose`, output có thể hiển thị các ký hiệu bên cạnh entry:

| Ký hiệu | Ý nghĩa |
|---|---|
| `s` | Chữ ký của entry đã được xác minh |
| `m` | Entry có trong manifest |
| `k` | Có ít nhất một certificate khớp với entry trong keystore |

Ví dụ minh họa:

~~~text
s k     1200 Mon Jan 12 10:00:00 UTC 2026 META-INF/MANIFEST.MF
smk     2450 Mon Jan 12 10:00:00 UTC 2026 com/example/App.class
smk      620 Mon Jan 12 10:00:00 UTC 2026 config/application.properties

- Signed by "CN=Example Release Signer, O=Example"
    Digest algorithm: SHA-384
    Signature algorithm: SHA384withRSA, 3072-bit key

jar verified.
~~~

Đây là output minh họa; ngày, kích thước, tên certificate, thuật toán và cách nhóm dòng phụ thuộc artifact, JDK và signer thực tế.

Cần hiểu:

- `s` cho biết chữ ký entry được xác minh.
- `m` cho biết entry có section trong manifest.
- `k` cho biết certificate khớp một entry trong keystore được kiểm tra.
- `k` không tự chứng minh certificate đó là CA tin cậy hoặc đúng nhà phát hành mong đợi.
- Dòng `jar verified` không thay thế việc đọc warning ở cuối output.

Khi JAR có nhiều signer, `-certs` giúp xem certificate của từng signer. Dùng `-verbose:summary` khi cần báo cáo gọn, hoặc `-verbose:all` khi cần truy vết từng entry.

## 5. Kiểm tra chữ ký của từng entry

Xác minh JAR gồm các bước chính:

1. Xác minh chữ ký trong signature block đối với file `.SF`.
2. So sánh digest trong `.SF` với section tương ứng trong manifest.
3. Đọc từng entry có thông tin ký, tính lại digest và so sánh với giá trị trong manifest.
4. Kiểm tra thuật toán có bị vô hiệu hóa theo security policy của JDK hay không.

Nếu một class hoặc resource đã ký bị thay đổi sau khi ký, bước so sánh digest sẽ thất bại.

### 5.1. JAR bị sửa sau khi ký

Giả sử `application.jar` đã được ký. Nếu ai đó thay đổi nội dung `com/example/App.class`, digest không khớp với giá trị đã ký và `jarsigner -verify` sẽ báo lỗi xác minh.

Nếu một file mới được thêm sau khi ký, file mới có thể không được bảo vệ bởi chữ ký ban đầu. Khi đó, JAR có thể vẫn chứa các entry đã ký hợp lệ nhưng đồng thời có entry unsigned.

Đối với artifact phát hành, cần kiểm tra cả hai tình huống:

- Không có entry đã ký nào bị thay đổi.
- Không có entry ngoài dự kiến chưa được ký.

Không nên chỉ tìm dòng `jar verified` rồi bỏ qua warning về unsigned entries.

### 5.2. Kiểm tra nội dung `META-INF`

Dùng `jar` để xem danh sách entry:

~~~text
jar --list --file application.jar
~~~

Tập trung vào:

- `META-INF/MANIFEST.MF`
- File `.SF`
- File signature block `.RSA`, `.DSA` hoặc `.EC`
- Các class/resource cần được ký
- Entry lạ hoặc file được thêm sau quá trình ký

`jar --list` chỉ hiển thị nội dung archive; nó không xác minh chữ ký. Dùng `jarsigner -verify` để kiểm tra tính toàn vẹn.

## 6. Kiểm tra certificate bằng `keytool`

`jarsigner -certs` hiển thị certificate trong quá trình verify. `keytool` cung cấp các lệnh chuyên để xem chi tiết certificate và keystore.

### 6.1. Đọc certificate được nhúng trong JAR

~~~text
keytool -printcert -jarfile application.jar -v
~~~

Lệnh này in certificate được tìm thấy trong signed JAR, gồm subject, issuer, thời hạn hiệu lực, thuật toán và fingerprint.

Dùng fingerprint để đối chiếu với giá trị được nhà phát hành công bố qua một kênh độc lập, ví dụ release portal hoặc tài liệu ký đã được xác thực.

Không tải một JAR rồi chỉ tin fingerprint được in từ chính JAR đó. Kẻ tấn công có thể thay cả artifact lẫn certificate nếu người kiểm tra không có giá trị tham chiếu độc lập.

### 6.2. Xem certificate trong keystore

~~~text
keytool -list -v -keystore release-signers.p12 -storetype PKCS12
~~~

Lệnh liệt kê alias, loại entry và certificate chain trong keystore. Nếu không truyền password, công cụ có thể yêu cầu nhập tại prompt.

Để xem certificate riêng:

~~~text
keytool -printcert -file signer.cer -v
~~~

`keytool -printcert` chỉ hiển thị thông tin certificate. Nó không thay thế `jarsigner -verify` và không chứng minh mọi entry trong JAR còn nguyên vẹn.

### 6.3. Kiểm tra những thuộc tính quan trọng

Khi review certificate, chú ý:

- Subject: danh tính được chứng thư cấp cho.
- Issuer: CA hoặc chủ thể đã phát hành certificate.
- Serial number: số serial của certificate.
- Validity: thời gian bắt đầu và kết thúc hiệu lực.
- SHA-256 fingerprint: dấu vân tay để đối chiếu ngoài băng.
- Key Usage: quyền sử dụng public key.
- Extended Key Usage: mục đích sử dụng, ví dụ code signing.
- Certificate chain: các intermediate certificate và root CA liên quan.

Nếu chain không được xác thực, điều đó có thể xuất phát từ thiếu intermediate certificate, CA chưa được tin cậy hoặc môi trường build không có trust anchor phù hợp. Hãy xác định nguyên nhân theo PKI policy của tổ chức.

## 7. Hiểu certificate chain và trust

Certificate trong signature block xác nhận public key của signer. CA certificate phía trên có thể xác nhận certificate của signer; chuỗi này cần dẫn đến trust anchor mà môi trường kiểm tra chấp nhận.

Một chain thường có dạng:

~~~text
JAR signer certificate
        |
        v
Intermediate code-signing CA
        |
        v
Organization / Public root CA
        |
        v
Trusted by verification policy
~~~

Nếu certificate là self-signed, không có CA bên ngoài xác nhận danh tính. Đây là lý do JDK có thể báo severe warning dù digest và chữ ký toán học vẫn khớp.

Khi kiểm tra JAR của nhà cung cấp:

1. Lấy fingerprint mong đợi từ kênh phát hành đáng tin.
2. In certificate từ JAR bằng `keytool -printcert -jarfile`.
3. So sánh fingerprint và subject với thông tin phát hành.
4. Xác nhận issuer/chain theo trust policy.
5. Kiểm tra certificate còn hiệu lực và mục đích code signing phù hợp.
6. Kiểm tra revocation theo chính sách tổ chức.

Không import certificate không rõ nguồn gốc vào truststore chỉ để làm cho `jarsigner -strict` chạy qua. Thao tác thêm trust anchor làm thay đổi quyết định tin cậy của môi trường và cần được phê duyệt theo chính sách PKI.

## 8. Timestamp và thời điểm ký

Certificate code signing có thời hạn. Nếu JAR được ký khi certificate còn hiệu lực và chữ ký có timestamp hợp lệ, người kiểm tra có thể xác nhận thời điểm ký ngay cả khi certificate signer hết hạn sau đó.

Khi ký, có thể yêu cầu TSA cấp timestamp:

~~~text
jarsigner -keystore release-signers.p12 -tsa https://tsa.example.org -signedjar application-signed.jar application.jar release-signer
~~~

`https://tsa.example.org` chỉ là URL minh họa; phải thay bằng TSA endpoint được tổ chức hoặc nhà cung cấp chứng thực phê duyệt.

Jarsigner sử dụng Time-Stamp Protocol (TSP) theo RFC 3161. Timestamp token được lưu cùng signature block khi TSA xử lý thành công.

Có thể dùng `-tsacert alias` nếu certificate TSA trong keystore có thông tin Subject Information Access chỉ đến TSA. Certificate TSA phải có trong keystore khi dùng tùy chọn này.

Khi xác minh, kiểm tra:

- Có timestamp hay không.
- Thời điểm ký có nằm trong thời gian hiệu lực của signer certificate không.
- TSA certificate có hợp lệ và chain có được xác thực không.
- Timestamp có hết hạn hoặc bị đánh giá là không hợp lệ không.
- Digest và signature algorithm của timestamp có được chính sách hiện tại chấp nhận không.

Nếu không có timestamp, JDK có thể đưa ra cảnh báo `noTimestamp`. Đây là informational warning; về lâu dài, JAR có thể khó được xác thực sau khi certificate signer hết hạn hoặc sau một mốc thu hồi trong tương lai.

## 9. Kiểm tra thu hồi certificate

Certificate có thể bị thu hồi trước ngày hết hạn, ví dụ khi private key bị lộ hoặc certificate được cấp sai.

Tùy chọn `-revCheck` bật kiểm tra thu hồi:

~~~text
jarsigner -verify -revCheck -verbose -certs application.jar
~~~

Khi bật, `jarsigner` có thể kết nối mạng để lấy OCSP response hoặc CRL. Nếu môi trường build offline hoặc firewall chặn endpoint, bước này có thể thất bại hoặc không hoàn tất như mong đợi.

Cần xác định rõ chính sách:

- Có bắt buộc kiểm tra thu hồi ở mọi lần verify không?
- Môi trường CI có quyền truy cập OCSP/CRL endpoint không?
- Nếu dịch vụ thu hồi tạm thời không truy cập được, pipeline xử lý thế nào?
- Kết quả được lưu lại để audit ra sao?

Không suy luận certificate chưa bị thu hồi chỉ vì lệnh verify không bật `-revCheck`. Theo help của JDK 24.0.2, revocation checking không được bật mặc định.

## 10. Hiểu `-strict` và exit code

Đây là phần quan trọng khi đưa xác minh chữ ký vào CI.

Nếu chỉ chạy `jarsigner -verify`, tool có thể trả exit code `0` dù có severe warning. Dùng `-strict` để đưa severe warning vào exit code:

~~~text
jarsigner -verify -strict -verbose -certs application.jar
~~~

Theo tài liệu JDK 24:

- Exit code `1`: thao tác ký hoặc xác minh thất bại.
- Không có failure nhưng có severe warning: mặc định exit code `0`; với `-strict`, exit code là phép OR các warning code.
- Chỉ có informational warning hoặc không có warning: exit code `0`.

Một số severe warning code thường gặp:

| Warning | Code | Ý nghĩa |
|---|---:|---|
| `hasExpiredCert` | 4 | Signer certificate đã hết hạn |
| `notYetValidCert` | 4 | Signer certificate chưa bắt đầu hiệu lực |
| `chainNotValidated` | 4 | Certificate chain chưa được xác thực |
| `signerSelfSigned` | 4 | Signer certificate tự ký |
| `disabledAlg` | 4 | Thuật toán bị xem là không an toàn và đã bị vô hiệu hóa |
| `badKeyUsage` | 8 | Key Usage không cho phép ký code |
| `badExtendedKeyUsage` | 8 | Extended Key Usage không cho phép ký code |
| `hasUnsignedEntry` | 16 | JAR có entry chưa được kiểm tra toàn vẹn bằng chữ ký |
| `notSignedByAlias` | 32 | Entry không được ký bởi alias được yêu cầu |
| `tsaChainNotValidated` | 64 | TSA certificate chain không hợp lệ |

Các mã có thể được kết hợp bằng phép OR. Ví dụ certificate hết hạn và Key Usage không phù hợp có thể tạo code `12` (`4 + 8`).

Một số informational warning không có exit code riêng, ví dụ:

- `noTimestamp`: chữ ký không có timestamp.
- `legacyAlg`: thuật toán được xem là rủi ro nhưng chưa bị vô hiệu hóa.
- `hasExpiringCert`: signer certificate sắp hết hạn.
- `hasExpiringTsaCert`: TSA certificate sắp hết hạn.

Vì vậy, `-strict` không tự biến mọi informational warning thành lỗi. CI nên lưu output và có policy riêng nếu tổ chức muốn chặn cả những cảnh báo này.

## 11. Thuật toán ký và chính sách bảo mật

Jarsigner kiểm tra thuật toán theo các security properties của JDK, trong đó có:

- `jdk.jar.disabledAlgorithms`
- `jdk.security.legacyAlgorithms`

Nếu JAR dùng thuật toán đã bị vô hiệu hóa, chữ ký có thể bị coi như unsigned. Thuật toán cũ nhưng chưa bị vô hiệu hóa có thể tạo informational warning.

Khi ký mới:

- Dùng digest và signature algorithm còn được JDK hỗ trợ và chính sách tổ chức chấp nhận.
- Chọn key size phù hợp với yêu cầu bảo mật hiện tại.
- Không dùng MD5 hoặc SHA-1 cho chữ ký mới.
- Không hạ thuật toán chỉ để tương thích với runtime quá cũ mà chưa đánh giá rủi ro.
- Kiểm tra thuật toán mặc định của JDK đang dùng vì mặc định có thể thay đổi theo release.
- Đảm bảo certificate có Key Usage và Extended Key Usage phù hợp.

Có thể chỉ định thuật toán khi ký:

~~~text
jarsigner -digestalg SHA-256 -sigalg SHA256withRSA -keystore release-signers.p12 -signedjar application-signed.jar application.jar release-signer
~~~

Đây là cấu hình ví dụ RSA; thuật toán thực tế phải tương thích với private key, JDK mục tiêu và policy hiện hành. Với JDK mới, default digest/signature algorithm có thể mạnh hơn cấu hình ví dụ này. Không cố định thuật toán cũ trong build script nếu không có lý do tương thích được ghi nhận.

## 12. Kiểm tra JAR có nhiều signer

Một JAR có thể được ký nhiều lần bởi nhiều signer. Mỗi lần ký bằng alias khác có thể thêm một cặp `.SF` và signature block riêng trong `META-INF`.

Ví dụ:

~~~text
META-INF/
  RELEASE.SF
  RELEASE.RSA
  AUDIT.SF
  AUDIT.EC
~~~

Khi verify, `jarsigner` kiểm tra các signature có trong JAR. Nếu cần giới hạn signer được chấp nhận, truyền alias mong đợi cùng `-keystore`:

~~~text
jarsigner -verify -strict -verbose -certs -keystore release-signers.p12 application.jar release-signer audit-signer
~~~

Xác nhận:

- Có đủ signer theo chính sách phát hành.
- Không có signer ngoài danh sách được phép.
- Mỗi signer có certificate chain và mục đích sử dụng phù hợp.
- Các entry quan trọng được ký theo yêu cầu.
- Không có entry unsigned hoặc entry được ký bởi alias ngoài dự kiến.

Khi JAR được ký lần lượt bởi nhiều signer, manifest có thể được cập nhật để thêm section cho entry mới. Chữ ký cũ vẫn có thể hợp lệ nếu những entry đã ký trước đó không bị thay đổi.

## 13. Quy trình Java 17: tạo JAR, ký và xác minh

Ví dụ sau tạo một ứng dụng nhỏ, đóng gói thành JAR, tạo certificate tự ký cho môi trường học tập, ký artifact và kiểm tra chữ ký.

Cấu trúc:

~~~text
project/
  src/
    com/
      example/
        Hello.java
  build/
    classes/
    hello.jar
    hello-signed.jar
    training.p12
~~~

### 13.1. Source code

Tệp `src/com/example/Hello.java`:

~~~java
package com.example;

public final class Hello {
    private Hello() {
    }

    public static void main(String[] args) {
        System.out.println("Hello, signed JAR!");
    }
}
~~~

### 13.2. Biên dịch và tạo JAR

Chạy từ thư mục gốc `project`.

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\classes | Out-Null

javac --release 17 -encoding UTF-8 `
    -d build\classes `
    src\com\example\Hello.java

jar --create `
    --file build\hello.jar `
    --main-class com.example.Hello `
    -C build\classes .
~~~

macOS/Linux:

~~~sh
mkdir -p build/classes

javac --release 17 -encoding UTF-8 \
    -d build/classes \
    src/com/example/Hello.java

jar --create \
    --file build/hello.jar \
    --main-class com.example.Hello \
    -C build/classes .
~~~

Chạy JAR chưa ký:

~~~text
java -jar build/hello.jar
~~~

Stdout:

~~~text
Hello, signed JAR!
~~~

### 13.3. Tạo keystore thử nghiệm

Dùng `keytool` để tạo RSA key pair và certificate tự ký:

~~~text
keytool -genkeypair -alias training-signer -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore build/training.p12 -dname "CN=Training Signer, OU=Java Core, O=Example, C=VN"
~~~

`keytool` sẽ yêu cầu nhập password keystore. Trong môi trường học tập, có thể dùng keystore riêng. Không dùng certificate tự ký của ví dụ này để phát hành sản phẩm thật.

### 13.4. Ký JAR

~~~text
jarsigner -keystore build/training.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -signedjar build/hello-signed.jar build/hello.jar training-signer
~~~

Nếu không truyền password trên command line, `jarsigner` sẽ yêu cầu nhập. Đây là cách phù hợp hơn cho ví dụ tương tác; trong CI, lấy secret từ secret manager hoặc cơ chế protected authentication path.

Sau khi ký, xem các entry chữ ký:

~~~text
jar --list --file build/hello-signed.jar
~~~

Trong `META-INF` sẽ có manifest, file `.SF` và signature block tương ứng với alias `training-signer`.

### 13.5. Xác minh chữ ký

Kiểm tra chữ ký và xem certificate:

~~~text
jarsigner -verify -verbose -certs build/hello-signed.jar
~~~

In certificate được nhúng:

~~~text
keytool -printcert -jarfile build/hello-signed.jar -v
~~~

Chạy ứng dụng sau khi ký:

~~~text
java -jar build/hello-signed.jar
~~~

Stdout:

~~~text
Hello, signed JAR!
~~~

Certificate của bài lab là self-signed nên output verify có thể cảnh báo về signer certificate không được tin cậy. Đây là kết quả dự kiến của môi trường học tập; nó minh họa sự khác nhau giữa chữ ký/toàn vẹn và danh tính signer được CA xác nhận.

Khi thêm `-strict`:

~~~text
jarsigner -verify -strict -verbose -certs build/hello-signed.jar
~~~

JDK có thể trả exit code khác `0` do severe warning về self-signed certificate hoặc chain chưa được xác thực. Điều này không có nghĩa source code Java không biên dịch hoặc digest của mọi entry chắc chắn bị thay đổi; cần đọc chính xác warning để xác định vấn đề.

Trong môi trường release thật, thay certificate tự ký bằng code-signing certificate do CA được chấp nhận cấp, dùng TSA được phê duyệt và xác minh bằng trust policy của tổ chức.

## 14. Tự động kiểm tra nhiều JAR trong PowerShell

`jarsigner -verify` nhận một JAR mỗi lần gọi. Các đối số alias phía sau tên JAR là signer alias, không phải danh sách JAR. Vì vậy, để kiểm tra nhiều artifact, dùng vòng lặp.

Ví dụ:

~~~powershell
$targets = @(
    Get-ChildItem .\build\libs -Filter *.jar -File -Recurse |
        Where-Object {
            $_.Name -notlike '*-sources.jar' -and
            $_.Name -notlike '*-javadoc.jar'
        }
)

if ($targets.Count -eq 0) {
    throw "No release JAR files were found."
}

New-Item -ItemType Directory -Force .\build\signature-reports | Out-Null

$failed = @()

foreach ($item in $targets) {
    Write-Host "Verifying $($item.FullName)..."

    $report = & jarsigner -verify -strict -verbose:summary -certs $item.FullName 2>&1
    $exitCode = $LASTEXITCODE

    $reportPath = Join-Path .\build\signature-reports ($item.BaseName + ".txt")
    $report | Set-Content -Encoding UTF8 $reportPath

    if ($exitCode -ne 0) {
        $failed += "$($item.FullName) (exit code $exitCode)"
    }
}

if ($failed.Count -gt 0) {
    $failed | ForEach-Object { Write-Error $_ }
    throw "One or more JAR signature checks failed."
}
~~~

Script này:

- Tìm JAR trong thư mục build.
- Bỏ qua source JAR và Javadoc JAR.
- Xác minh từng JAR với `-strict`.
- Lưu report riêng cho từng artifact.
- Thu thập các artifact có exit code khác `0`.
- Làm build thất bại nếu có JAR không đạt strict verification.

Nếu hai thư mục có JAR cùng `BaseName`, hãy điều chỉnh cách đặt tên report để tránh ghi đè report của nhau. Nếu cần kiểm tra alias signer cụ thể, thêm `-keystore` và alias được phê duyệt vào lệnh verify.

## 15. Tích hợp xác minh chữ ký trong CI/CD

Một pipeline phát hành nên xác minh artifact ngay sau khi ký và trước khi publish:

1. Build JAR từ commit đã được duyệt.
2. Tạo artifact inventory và checksum.
3. Ký JAR bằng key/certificate của release.
4. Lấy timestamp từ TSA được phê duyệt.
5. Chạy `jarsigner -verify -strict -verbose:summary -certs`.
6. Kiểm tra signer certificate, fingerprint và chain.
7. Kiểm tra warning informational theo release policy.
8. Kiểm tra mọi entry cần bảo vệ đã được ký.
9. Lưu raw verification report cùng artifact.
10. Publish đúng file đã được xác minh; không sửa JAR sau bước verify.

Ví dụ command cho một artifact:

~~~text
jarsigner -verify -strict -verbose:summary -certs build/application-signed.jar
~~~

Nếu có nhiều signer được phép:

~~~text
jarsigner -verify -strict -verbose:summary -certs -keystore release-signers.p12 build/application-signed.jar release-signer
~~~

Không đặt password thật trực tiếp trong script hoặc command line của pipeline. Dùng secret manager, biến môi trường hoặc file secret có quyền truy cập hạn chế theo cơ chế được JDK hỗ trợ.

Giữ lại:

- JAR đã ký và checksum.
- JDK/jarsigner version.
- Certificate fingerprint và signer alias.
- Timestamp và TSA certificate details.
- Lệnh verify đã chạy.
- Exit code và raw output.
- Kết quả policy review cho informational warnings.

Nếu artifact được ký lại, nén lại hoặc cập nhật sau khi verify, phải chạy xác minh lại trên đúng file cuối cùng sẽ publish.

## 16. Troubleshooting khi xác minh chữ ký

### `jar is unsigned`

**Nguyên nhân:** JAR không có chữ ký hợp lệ hoặc các thuật toán chữ ký đã bị vô hiệu hóa.

**Cách xử lý:** kiểm tra `META-INF`, file `.SF`, signature block và thuật toán. Xác nhận đúng artifact đã được ký trước khi phát hành.

### `invalid SHA-256 signature file digest`

**Nguyên nhân:** digest trong signature file không khớp manifest hiện tại.

**Cách xử lý:** kiểm tra JAR có bị sửa sau khi ký, manifest có bị cập nhật ngoài quy trình hoặc file ký có bị thay thế không. Tạo lại artifact từ nguồn tin cậy và ký lại.

### `digest error` hoặc entry digest mismatch

**Nguyên nhân:** nội dung entry khác với nội dung tại thời điểm ký.

**Cách xử lý:** xác định entry bị thay đổi, truy nguyên artifact và build lại. Không bỏ qua mismatch để tiếp tục publish.

### `This jar contains unsigned entries`

**Nguyên nhân:** có file trong JAR không được bao phủ bởi chữ ký hiện tại, ví dụ file được thêm sau khi ký.

**Cách xử lý:** xác định entry có được phép unsigned không. Nếu release policy yêu cầu toàn bộ payload được ký, tạo lại JAR rồi ký lại sau khi hoàn tất mọi thay đổi.

### `signer certificate is self-signed`

**Nguyên nhân:** certificate không có CA chain được xác thực theo trust policy.

**Cách xử lý:** dùng certificate do CA được tổ chức chấp nhận cấp hoặc thực hiện quy trình trust nội bộ đã phê duyệt. Kiểm tra fingerprint qua kênh độc lập.

### `certificate chain not validated`

**Nguyên nhân:** thiếu intermediate certificate, root CA không được tin cậy hoặc môi trường kiểm tra thiếu dữ liệu chain.

**Cách xử lý:** xem certificate bằng `-certs`/`keytool`, xác nhận chain và trust anchor theo policy; kiểm tra môi trường build có đúng cấu hình PKI.

### `signer certificate has expired`

**Nguyên nhân:** certificate hết hạn tại thời điểm kiểm tra hoặc không có timestamp hợp lệ chứng minh thời điểm ký phù hợp.

**Cách xử lý:** kiểm tra timestamp token, thời hạn signer certificate và TSA chain. Ký release mới bằng certificate còn hiệu lực khi cần.

### `timestamp is invalid`

**Nguyên nhân:** TSA certificate chain không hợp lệ, timestamp token không được xác minh hoặc TSA certificate hết hạn.

**Cách xử lý:** kiểm tra TSA chain, thời gian ký và endpoint TSA; dùng TSA được phê duyệt và xác minh lại.

### `disabled algorithm`

**Nguyên nhân:** JAR sử dụng digest hoặc signature algorithm bị security property của JDK vô hiệu hóa.

**Cách xử lý:** ký lại bằng thuật toán và key size phù hợp. Không chỉnh `jdk.jar.disabledAlgorithms` để bỏ qua lỗi chỉ nhằm làm release pass.

### `badKeyUsage` hoặc `badExtendedKeyUsage`

**Nguyên nhân:** certificate không được cấp cho mục đích ký code.

**Cách xử lý:** yêu cầu certificate có extension phù hợp với chính sách code signing; không dùng certificate TLS hoặc certificate sai mục đích.

### Exit code `0` nhưng vẫn có warning

**Nguyên nhân:** lệnh chưa dùng `-strict`, hoặc warning thuộc nhóm informational.

**Cách xử lý:** dùng `-strict` để chặn severe warning và áp dụng policy riêng cho `noTimestamp`, `legacyAlg` hoặc warning informational khác.

### `aliasNotInStore` hoặc `notSignedByAlias`

**Nguyên nhân:** signer trong JAR không khớp alias được yêu cầu hoặc certificate không có trong keystore được chỉ định.

**Cách xử lý:** kiểm tra đúng keystore, alias và signer certificate. Đối chiếu fingerprint trước khi chấp nhận alias thay thế.

## 17. Checklist trước khi chấp nhận JAR đã ký

- [ ] Đã xác nhận JDK và `jarsigner` version.
- [ ] Đã chạy `jarsigner -verify`.
- [ ] Đã chạy strict verification theo policy release.
- [ ] Không có entry đã ký bị thay đổi hoặc digest mismatch.
- [ ] Không có unsigned entry ngoài danh sách được phép.
- [ ] Đã kiểm tra tất cả signer và alias cần thiết.
- [ ] Đã xem certificate chain bằng `-certs`.
- [ ] Đã đối chiếu fingerprint với nguồn độc lập.
- [ ] Subject, issuer, validity và mục đích code signing phù hợp.
- [ ] Timestamp hợp lệ và TSA chain được xác thực nếu policy yêu cầu.
- [ ] Revocation checking được thực hiện theo policy.
- [ ] Không có thuật toán bị vô hiệu hóa hoặc yếu ngoài chính sách.
- [ ] Informational warnings đã được review và chấp nhận có lý do.
- [ ] JAR không bị thay đổi sau bước verify.
- [ ] Raw report, exit code, checksum và toolchain version được lưu cùng release.

## 18. Tài liệu tham khảo

- Oracle JDK 24 — The `jarsigner` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Oracle JDK 24 — `keytool` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html
- Java SE Security Developer Guide — Certificate and keystore concepts: https://docs.oracle.com/en/java/javase/24/security/

`jarsigner -verify` xác nhận chữ ký và tính toàn vẹn của các entry đã ký; `-certs`, `keytool` và quy trình xác nhận fingerprint giúp review danh tính signer; `-strict` đưa severe warnings vào kết quả kiểm tra của CI. Chỉ phát hành artifact cuối cùng khi cả nội dung, certificate, timestamp, thuật toán và trust policy đều đạt yêu cầu.