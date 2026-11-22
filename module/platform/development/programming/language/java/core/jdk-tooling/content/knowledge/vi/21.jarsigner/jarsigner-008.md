# JAR unsigned: cách nhận biết, ký và xác minh bằng jarsigner

## 1. JAR unsigned là gì?

JAR (Java ARchive) là một tệp ZIP dùng để đóng gói class, resource và metadata của ứng dụng hoặc thư viện Java. Một JAR **unsigned** là JAR chưa có chữ ký số hợp lệ của người phát hành.

JAR unsigned không nhất thiết bị hỏng hoặc không chạy được. Ứng dụng Java vẫn có thể sử dụng một JAR unsigned trên classpath hoặc module path theo cách triển khai thông thường. Vấn đề là người nhận không có chữ ký số để kiểm tra rằng nội dung JAR được ký bởi một danh tính cụ thể và các entry được ký chưa bị thay đổi kể từ lúc ký.

Cần phân biệt:

- **JAR unsigned**: chưa có chữ ký số.
- **JAR signed**: có metadata chữ ký để xác minh nội dung và chứng thư của signer.
- **JAR bị sửa sau khi ký**: digest của entry không còn khớp với chữ ký; việc xác minh sẽ báo lỗi.
- **JAR ký một phần**: có chữ ký nhưng vẫn còn entry không được ký, ví dụ file được thêm vào sau khi ký.

JAR unsigned không đồng nghĩa với mã độc. JAR signed cũng không chứng minh chương trình an toàn. Chữ ký giúp xác minh tính toàn vẹn và danh tính signer theo chứng thư; quyết định có tin signer hay không vẫn cần dựa trên chính sách tin cậy của tổ chức.

## 2. Manifest không phải là chữ ký số

Một JAR thông thường có thể chứa:

~~~text
application.jar
  META-INF/
    MANIFEST.MF
  com/example/Main.class
  config/app.properties
~~~

`META-INF/MANIFEST.MF` chứa metadata như phiên bản manifest, main class và thuộc tính của từng entry. Chỉ có manifest không có nghĩa JAR đã được ký.

Sau khi ký, cấu trúc thường có thêm các tệp trong `META-INF`:

~~~text
application-signed.jar
  META-INF/
    MANIFEST.MF
    RELEASE.SF
    RELEASE.RSA
  com/example/Main.class
  config/app.properties
~~~

Tên và phần mở rộng phụ thuộc tên signer và thuật toán chữ ký. Có thể gặp `.SF` cùng signature block `.RSA`, `.DSA` hoặc `.EC`.

Vai trò chính:

- `MANIFEST.MF`: liệt kê các entry và metadata của chúng.
- `RELEASE.SF`: chứa digest của manifest hoặc các section manifest.
- `RELEASE.RSA` (hoặc `.DSA` / `.EC`): chứa chữ ký số của tệp `.SF` và chứng thư signer.

Khi ký, `jarsigner` tạo hoặc cập nhật manifest digest cho các entry được ký, tạo signature file và signature block. Khi xác minh, công cụ kiểm tra chuỗi digest và chữ ký để phát hiện nội dung không khớp.

Không nên tự sửa các tệp chữ ký trong `META-INF`. Nếu nội dung JAR thay đổi, hãy tạo lại artifact rồi ký lại bằng quy trình phát hành.

## 3. Chữ ký JAR bảo vệ điều gì?

Chữ ký số JAR hỗ trợ hai mục tiêu:

**Tính toàn vẹn (integrity)**

Digest của entry được kiểm tra. Nếu một class hoặc resource đã ký bị sửa, digest không khớp và việc xác minh báo lỗi.

**Danh tính signer (signer identity)**

Signature block chứa chữ ký và chứng thư số. Người nhận có thể kiểm tra chứng thư, chuỗi CA, thời hạn và danh tính được chứng thư xác nhận.

Chữ ký không mã hóa JAR. Người nhận vẫn có thể liệt kê và đọc bytecode, manifest và resource.

Chữ ký cũng không đảm bảo code không có lỗ hổng hoặc hành vi độc hại. Một JAR độc hại vẫn có thể được ký bởi một signer mà người nhận đã tin cậy. Vì vậy, hãy kết hợp xác minh chữ ký với kiểm tra nguồn phát hành, review, quét bảo mật và kiểm thử.

## 4. Kiểm tra JAR unsigned bằng jar và jarsigner

Trước tiên, liệt kê nội dung:

~~~bash
jar --list --file application.jar
~~~

Xác minh JAR:

~~~bash
jarsigner --verify --verbose --certs application.jar
~~~

Với JAR unsigned, JDK 24.0.2 hiển thị dạng:

~~~text
?     425 ... demo/Hello.class

  s = signature was verified
  m = entry is listed in manifest
  k = at least one certificate was found in keystore
  ? = unsigned entry

jar is unsigned.
~~~

Dấu `?` chỉ entry không có chữ ký. Cụm `jar is unsigned.` là chẩn đoán trực tiếp rằng archive chưa được ký.

Một chi tiết quan trọng cho script CI: trên JDK 24.0.2, `jarsigner --verify` với JAR unsigned vẫn trả exit code 0 dù in `jar is unsigned.`. Vì vậy, chỉ kiểm tra exit code 0 là chưa đủ để khẳng định artifact đã được ký. Hãy kiểm tra nội dung kết quả hoặc dùng chính sách xác minh nghiêm ngặt đã được thử nghiệm với phiên bản JDK trong pipeline.

## 5. Tạo key pair để ký JAR

`jarsigner` sử dụng private key và certificate lấy từ keystore. Nó không tự tạo danh tính signer.

Để tạo key pair RSA trong keystore PKCS12 dùng cho bài thực hành:

~~~bash
keytool -genkeypair \
  -alias demo-signer \
  -keyalg RSA \
  -keysize 3072 \
  -validity 30 \
  -dname "CN=JAR Signing Demo, OU=Test, O=Example, C=VN" \
  -keystore signer.p12 \
  -storetype PKCS12
~~~

`keytool` sẽ yêu cầu mật khẩu keystore và có thể hỏi mật khẩu riêng cho private key. Ví dụ này tạo chứng thư self-signed để học quy trình; nó không tạo chứng thư được CA công cộng tin cậy.

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `-genkeypair` | Tạo public/private key pair và chứng thư |
| `-alias demo-signer` | Tên định danh entry trong keystore |
| `-keyalg RSA` | Thuật toán tạo khóa |
| `-keysize 3072` | Kích thước khóa RSA |
| `-validity 30` | Thời hạn chứng thư tính theo ngày |
| `-dname` | Distinguished Name trong chứng thư |
| `-keystore signer.p12` | File keystore |
| `-storetype PKCS12` | Định dạng keystore |

Đối với phát hành thật, hãy dùng chứng thư code signing phù hợp do CA hoặc hệ thống PKI của tổ chức cấp. Bảo vệ private key bằng quyền truy cập tối thiểu, thiết bị bảo mật hoặc secret manager phù hợp. Không đưa mật khẩu thật vào script, command history hoặc log CI.

Kiểm tra entry:

~~~bash
keytool -list -v -keystore signer.p12 -storetype PKCS12
~~~

Signer cần có private key entry (thường hiển thị `PrivateKeyEntry`) cùng certificate chain. Một trusted certificate entry chỉ có chứng thư công khai, không có private key để ký.

## 6. Ký JAR unsigned bằng jarsigner

Giả sử bạn có `application-unsigned.jar` và keystore `signer.p12` chứa private key entry alias `demo-signer`.

Lệnh ký:

~~~bash
jarsigner \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -signedjar application-signed.jar \
  application-unsigned.jar \
  demo-signer
~~~

Công cụ yêu cầu mật khẩu keystore/private key khi cần. Dùng `-signedjar` để ghi kết quả vào file mới và giữ lại artifact unsigned ban đầu để đối chiếu.

Có thể chỉ định thuật toán digest và signature tường minh khi chính sách tương thích của dự án yêu cầu:

~~~bash
jarsigner \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -signedjar application-signed.jar \
  application-unsigned.jar \
  demo-signer
~~~

Chọn thuật toán theo chính sách bảo mật hiện hành và khả năng hỗ trợ của môi trường chạy. Không dùng thuật toán yếu hoặc đã bị vô hiệu hóa chỉ để làm cho lệnh cũ chạy được.

Nếu bỏ `-signedjar`, `jarsigner` ký trực tiếp vào JAR đầu vào. Với quy trình build/release, tạo artifact mới thường dễ kiểm tra và truy vết hơn.

Khi thành công, công cụ báo:

~~~text
jar signed.
~~~

Nếu signer dùng chứng thư self-signed, công cụ sẽ cảnh báo rằng chứng thư tự ký. Đây là điều bình thường trong lab, nhưng không chứng minh người nhận có thể xác minh danh tính signer một cách độc lập.

## 7. Xác minh JAR đã ký

Chạy:

~~~bash
jarsigner --verify --verbose --certs application-signed.jar
~~~

Các tùy chọn:

- `--verify`: kiểm tra chữ ký và digest của JAR.
- `--verbose`: liệt kê trạng thái từng entry.
- `--certs`: hiển thị chứng thư signer.
- `-strict`: coi các cảnh báo xác minh là lỗi và trả exit code khác 0 khi có signer warning/error theo quy tắc của công cụ.

Khi một entry được ký hợp lệ, output verbose có thể có ký hiệu `s` và `m` trước entry:

~~~text
sm       425 ... demo/Hello.class

  s = signature was verified
  m = entry is listed in manifest
~~~

Nếu có chứng thư signer, output còn hiển thị thông tin chứng thư và thuật toán chữ ký. Ví dụ lab self-signed có thể kết thúc bằng:

~~~text
jar verified.

Warning:
This jar contains entries whose certificate chain is invalid.
This jar contains entries whose signer certificate is self-signed.
This jar contains signatures that do not include a timestamp.
~~~

`jar verified.` xác nhận các phép kiểm tra chữ ký/digest của entry đã ký thành công. Các warning ở trên vẫn có ý nghĩa: chuỗi chứng thư không được tin cậy, chứng thư self-signed và chữ ký không có timestamp. Không nên hiểu dòng `jar verified.` là tổ chức đã tin signer.

Trong pipeline phát hành, có thể dùng:

~~~bash
jarsigner --verify --strict --verbose --certs application-signed.jar
~~~

Chính sách CI cần xác định rõ truststore, certificate chain, timestamp và cảnh báo nào được phép. Không tắt `-strict` chỉ để che warning mà chưa hiểu nguyên nhân.

## 8. Phân biệt JAR unsigned, JAR bị sửa và JAR ký một phần

Ba tình huống có output khác nhau:

| Tình huống | Kết quả xác minh |
|---|---|
| JAR chưa ký | Báo `jar is unsigned.` và đánh dấu entry unsigned |
| Entry đã ký bị sửa | Digest không khớp; xác minh thất bại |
| Thêm entry mới sau khi ký | Entry mới có thể mang dấu `?`; các entry cũ vẫn có chữ ký |

Ví dụ, sau khi ký, nếu thay nội dung `demo/Hello.class`, JDK 24.0.2 báo lỗi tương tự:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-256 digest error for demo/Hello.class
~~~

Nếu chỉ thêm `readme.txt` sau khi ký, file mới không tự động được ký. `jarsigner --verify --verbose` sẽ đánh dấu file mới bằng `?` và cảnh báo:

~~~text
This jar contains unsigned entries which have not been integrity-checked.
~~~

Vì vậy, không cập nhật resource hoặc class vào JAR sau bước ký. Hãy hoàn tất build, đóng gói và kiểm tra artifact trước; ký ở bước cuối; sau đó xác minh chính file sẽ được phân phối.

## 9. Chứng thư self-signed và chứng thư được tin cậy

Chữ ký mật mã hợp lệ và chứng thư được tin cậy là hai câu hỏi khác nhau.

**Chứng thư self-signed**

Chứng thư tự ký giúp thử nghiệm kỹ thuật. Người nhận không có CA độc lập xác nhận danh tính chủ thể. Nếu chỉ nhận JAR và file certificate từ cùng một nguồn không xác thực, kẻ tấn công có thể thay cả hai.

**Chứng thư do CA hoặc PKI tổ chức cấp**

Chuỗi chứng thư có thể được xác minh đến trust anchor mà máy nhận đã tin cậy. Người phát hành cần cung cấp đúng chain và người nhận cần có truststore phù hợp.

Nếu tổ chức dùng self-signed certificate nội bộ, người nhận chỉ nên import certificate sau khi đã xác minh fingerprint qua một kênh độc lập được xác thực. Không import certificate chỉ vì file được gửi cùng JAR.

Có thể xuất certificate công khai từ keystore:

~~~bash
keytool -exportcert \
  -alias demo-signer \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -file signer.cer
~~~

Xem fingerprint:

~~~bash
keytool -printcert -file signer.cer
~~~

Nếu chính sách tổ chức yêu cầu truststore riêng, import certificate sau khi đã xác minh fingerprint:

~~~bash
keytool -importcert \
  -alias trusted-demo-signer \
  -file signer.cer \
  -keystore trusted-signers.p12 \
  -storetype PKCS12
~~~

Truststore chứa certificate được tin cậy; nó không cần private key để xác minh chữ ký. Không chia sẻ file keystore có private key cho người nhận chỉ để họ xác minh JAR.

## 10. Timestamp và thời hạn chứng thư

Chữ ký JAR có thể được gửi đến một Timestamping Authority (TSA) để tạo timestamp có xác thực. Trong môi trường build, cấu hình biến môi trường `TSA_URL` với endpoint TSA thực tế do tổ chức hoặc nhà cung cấp chứng thực chỉ định:

~~~bash
jarsigner \
  -tsa "$TSA_URL" \
  -keystore signer.p12 \
  -storetype PKCS12 \
  application-unsigned.jar \
  demo-signer
~~~

Timestamp giúp chứng minh chữ ký đã được tạo trong một thời điểm khi chứng thư signer còn hiệu lực. Không có timestamp, người dùng có thể không xác minh được chữ ký sau khi certificate hết hạn, tùy chính sách xác minh và trạng thái chứng thư.

Timestamp không làm cho một certificate không đáng tin trở nên đáng tin, cũng không thay thế kiểm tra revocation hoặc trust chain. Hãy cấu hình TSA, certificate chain và chính sách kiểm tra thu hồi theo yêu cầu phát hành.

## 11. Ví dụ Java 17 hoàn chỉnh: tạo, ký và xác minh một JAR

Tạo source `src/demo/Hello.java`:

~~~java
package demo;

/** A small JAR signing demonstration. */
public final class Hello {
    /** Runs the example. */
    public static void main(String[] args) {
        System.out.println("JAR signing demo");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d build/classes src/demo/Hello.java
~~~

Đóng gói JAR unsigned:

~~~bash
jar --create \
  --file build/hello-unsigned.jar \
  --main-class demo.Hello \
  -C build/classes .
~~~

Xác minh trạng thái ban đầu:

~~~bash
jarsigner --verify --verbose build/hello-unsigned.jar
~~~

Kết quả phải có `jar is unsigned.`. Đừng kết luận unsigned chỉ từ exit code vì bản JDK 24.0.2 trả 0 cho tình huống này.

Tạo keystore PKCS12 dùng cho lab:

~~~bash
keytool -genkeypair \
  -alias demo-signer \
  -keyalg RSA \
  -keysize 3072 \
  -validity 30 \
  -dname "CN=JAR Signing Demo, OU=Test, O=Example, C=VN" \
  -keystore build/signer.p12 \
  -storetype PKCS12
~~~

Ký vào file mới:

~~~bash
jarsigner \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -keystore build/signer.p12 \
  -storetype PKCS12 \
  -signedjar build/hello-signed.jar \
  build/hello-unsigned.jar \
  demo-signer
~~~

Xác minh:

~~~bash
jarsigner --verify --verbose --certs build/hello-signed.jar
~~~

Liệt kê signature metadata:

~~~bash
jar --list --file build/hello-signed.jar
~~~

Danh sách thường có:

~~~text
META-INF/MANIFEST.MF
META-INF/DEMO-SIG.SF
META-INF/DEMO-SIG.RSA
demo/Hello.class
~~~

Tên signature file có thể khác theo alias hoặc cấu hình `-sigfile`. Với self-signed certificate, kết quả xác minh sẽ có warning về trust chain và timestamp; đó là giới hạn có chủ đích của lab.

Chạy JAR:

~~~bash
java -jar build/hello-signed.jar
~~~

Stdout chính xác:

~~~text
JAR signing demo
~~~

Chữ ký không thay đổi logic chương trình. Lệnh `java -jar` chạy main class như bình thường; chữ ký là metadata để kiểm tra tính toàn vẹn và signer.

## 12. Lỗi thường gặp khi ký và xác minh

### jar is unsigned.

JAR chưa có signature metadata. Kiểm tra alias, keystore và lệnh ký; xác minh lại file output mà bạn định phân phối.

### keystore was tampered with, or password was incorrect

Mật khẩu keystore không đúng, file keystore hỏng hoặc định dạng keystore không khớp. Kiểm tra `-storetype`, đường dẫn file và thông tin xác thực.

### Alias ... does not exist

Alias không có trong keystore đang chỉ định. Dùng `keytool -list -keystore ...` để xem alias. Đảm bảo alias trỏ đến `PrivateKeyEntry` khi ký.

### This jar contains unsigned entries

Một hoặc nhiều entry chưa được ký. Có thể file được thêm sau bước ký hoặc quá trình ký không bao phủ tất cả entry. Build lại artifact rồi ký lại.

### digest error

Nội dung entry đã thay đổi sau khi ký hoặc metadata digest không khớp. Không sửa trực tiếp file trong JAR đã ký; tạo lại JAR từ source/build output và ký lại.

### Certificate chain invalid hoặc self-signed

Chữ ký có thể đúng về mặt mật mã nhưng certificate không được truststore tin cậy. Kiểm tra chain, root CA, alias, truststore và fingerprint signer. Không import certificate chưa xác minh.

### Certificate hết hạn hoặc thiếu timestamp

Kiểm tra thời hạn certificate và cấu hình TSA. Timestamp phải đến từ dịch vụ đáng tin cậy và được kiểm tra theo chính sách của tổ chức.

### JAR đã ký nhưng file mới thêm vào lại unsigned

Mọi cập nhật sau bước ký có thể tạo entry không được ký. Ký sau cùng, rồi xác minh lại đúng artifact cuối cùng.

## 13. Checklist trước khi phân phối JAR

- [ ] Xác định artifact cuối cùng và kiểm tra danh sách entry.
- [ ] Dùng keystore đúng loại và alias có `PrivateKeyEntry`.
- [ ] Bảo vệ private key và mật khẩu khỏi source code, log và repository.
- [ ] Dùng certificate chain phù hợp với người nhận và chính sách phát hành.
- [ ] Ký sau khi hoàn tất mọi thay đổi nội dung JAR.
- [ ] Cân nhắc digest/signature algorithm theo chính sách bảo mật.
- [ ] Cấu hình TSA và timestamp nếu quy trình phát hành yêu cầu.
- [ ] Chạy `jarsigner --verify --verbose --certs`.
- [ ] Dùng `-strict` khi CI phải chặn signer warning/error.
- [ ] Xác minh không có entry `?` ngoài dự kiến.
- [ ] Kiểm tra trust chain, thời hạn và trạng thái certificate.
- [ ] Chạy thử artifact đã ký và lưu kết quả xác minh cùng build.

JAR unsigned chỉ cho biết archive chưa có chữ ký số. `jarsigner` có thể ký artifact bằng private key trong keystore và xác minh digest/chữ ký sau đó. Để phân phối an toàn, cần kiểm tra cả tính toàn vẹn của entry, danh tính signer, trust chain, timestamp và việc không có nội dung được thêm sau khi ký.
