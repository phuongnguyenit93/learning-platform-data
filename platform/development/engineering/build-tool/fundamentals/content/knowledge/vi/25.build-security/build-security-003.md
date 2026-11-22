# Checksum và chữ ký: kiểm tra toàn vẹn và xác minh nguồn

Khi tải dependency, nhận một JAR từ nhà cung cấp hoặc tạo artifact để phát hành, cần xác định hai điều: nội dung có bị thay đổi so với bản đã được chấp nhận hay không, và artifact có thực sự đến từ nguồn hoặc người phát hành mà ta tin cậy hay không. **Checksum** và **chữ ký số** hỗ trợ hai mục tiêu liên quan nhưng khác nhau.

Checksum là giá trị băm được tính từ byte của file. Nếu chỉ một bit thay đổi, giá trị băm có xác suất rất cao thay đổi theo. Chữ ký số dùng khóa riêng để ký dữ liệu và khóa công khai để xác minh chữ ký, qua đó liên kết artifact với danh tính hoặc khóa của bên ký. Một checksum đúng có thể chứng minh file giống với một digest đã tin cậy; chữ ký hợp lệ có thể chứng minh dữ liệu được ký bởi người giữ khóa riêng tương ứng. Cả hai chỉ có ý nghĩa khi nguồn của checksum hoặc khóa công khai được xác minh đáng tin cậy.

Trong Gradle, có thể kiểm soát dependency bằng **dependency verification** với checksum và chữ ký PGP, kiểm tra Gradle Wrapper distribution bằng checksum riêng, và kiểm tra JAR đã ký bằng công cụ JDK. Ở bước phát hành, có thể ký artifact hoặc publication để consumer xác minh nguồn. Những cơ chế này bổ sung cho TLS, dependency locking, SBOM và quy trình review.

## 1. Toàn vẹn và xác minh nguồn là hai mục tiêu khác nhau

**Toàn vẹn (integrity)** trả lời câu hỏi: file hiện tại có đúng từng byte so với một bản tham chiếu đã được chấp nhận không?

**Xác minh nguồn (authenticity/provenance)** trả lời câu hỏi: ai hoặc hệ thống nào đã phát hành file này, và ta có tin cậy danh tính đó không?

Ví dụ, nhà phát hành công bố một file JAR cùng SHA-256:

~~~text
order-client-1.0.0.jar
SHA256: 8f... (digest minh họa)
~~~

Nếu ta tải JAR và tính ra đúng digest đã lấy từ kênh đáng tin cậy, ta có bằng chứng file không bị thay đổi so với bản tham chiếu đó.

Nhưng nếu kẻ tấn công thay cả JAR lẫn file checksum trên cùng một máy chủ bị chiếm quyền, hai file vẫn có thể khớp nhau. Checksum tự nó không xác định ai đã tạo ra file.

Chữ ký số bổ sung mối liên hệ với khóa ký. Nếu chữ ký hợp lệ và khóa công khai được xác nhận thuộc về nhà phát hành mà ta tin cậy, ta có bằng chứng mạnh hơn về nguồn phát hành.

| Cơ chế | Xác nhận điều gì? | Cần tin cậy điều gì? |
|---|---|---|
| Checksum | Byte của file khớp với digest tham chiếu | Nguồn cung cấp digest |
| Chữ ký số | Dữ liệu được ký bằng khóa riêng tương ứng | Danh tính và khóa công khai của người ký |
| TLS/HTTPS | Kênh truyền tới máy chủ được xác thực và mã hóa | Certificate chain và tên máy chủ |
| SBOM | Thành phần được khai báo trong artifact/build | Quy trình tạo và tính chính xác của SBOM |
| Provenance/attestation | Thông tin về quy trình tạo artifact | Hệ thống phát hành và danh tính ký attestation |

Không cơ chế đơn lẻ nào chứng minh phần mềm an toàn tuyệt đối. Một artifact có checksum và chữ ký hợp lệ vẫn có thể chứa lỗ hổng hoặc mã độc nếu chính nguồn phát hành bị xâm phạm.

## 2. Checksum hoạt động như thế nào?

Checksum thường được tạo bằng một hàm băm mật mã như SHA-256 hoặc SHA-512. Hàm băm nhận nội dung file với độ dài bất kỳ và tạo ra digest có độ dài cố định.

Ví dụ quy trình:

~~~text
artifact.jar
    |
    v
SHA-256
    |
    v
digest 256 bit
    |
    v
so sánh với digest đã tin cậy
~~~

Nếu file bị thay đổi, digest thường sẽ khác. Với SHA-256, xác suất hai file khác nhau tình cờ tạo cùng digest là cực kỳ nhỏ trong thực tế.

Một số thuật toán thường gặp:

| Thuật toán | Đánh giá sử dụng |
|---|---|
| MD5 | Không nên dùng để xác minh an toàn trước đối thủ vì đã có tấn công va chạm |
| SHA-1 | Không nên dùng cho mục tiêu bảo mật mới vì đã có tấn công va chạm thực tế |
| SHA-256 | Lựa chọn phổ biến, phù hợp cho kiểm tra toàn vẹn hiện nay |
| SHA-512 | Lựa chọn mạnh, hữu ích khi hệ thống hoặc chính sách yêu cầu |

Nên ưu tiên SHA-256 hoặc SHA-512. Nếu repository cũ chỉ công bố SHA-1, không nên xem đó là bằng chứng bảo mật đủ mạnh trước một đối thủ chủ động.

### Digest không mã hóa nội dung

Checksum không phải encryption. Người có file có thể tính digest mà không cần khóa bí mật. Digest cũng không thể khôi phục nội dung file.

Checksum chỉ có ích khi giá trị tham chiếu được lấy từ một nguồn tin cậy và được gắn với đúng artifact, version và nền tảng.

## 3. Tính checksum của artifact

Có thể tính SHA-256 bằng nhiều công cụ.

### Linux hoặc macOS

~~~bash
sha256sum order-client-1.0.0.jar
~~~

Trên một số hệ thống macOS, có thể dùng:

~~~bash
shasum -a 256 order-client-1.0.0.jar
~~~

### Windows PowerShell

~~~powershell
Get-FileHash .\order-client-1.0.0.jar -Algorithm SHA256
~~~

### Windows Command Prompt

~~~bat
certutil -hashfile order-client-1.0.0.jar SHA256
~~~

Các lệnh trên chỉ tính digest của file cục bộ. Để xác minh, cần so sánh kết quả với digest được công bố qua một kênh đáng tin cậy.

Ví dụ:

~~~text
Expected SHA-256: 5b7c...9a20
Actual SHA-256:   5b7c...9a20
Result: MATCH
~~~

Giá trị trong ví dụ chỉ minh họa. Không sao chép digest minh họa để xác minh artifact thật.

### Tính checksum của nhiều file

Có thể tính checksum cho tất cả artifact trong một thư mục:

~~~bash
sha256sum build/libs/*.jar
~~~

Trên PowerShell:

~~~powershell
Get-ChildItem .\build\libs\*.jar | Get-FileHash -Algorithm SHA256
~~~

Khi lưu digest, cần gắn rõ tên file, version và loại artifact. Hai file có tên gần giống nhau nhưng khác classifier hoặc nền tảng phải có digest riêng.

## 4. Lấy checksum từ nguồn đáng tin cậy

Không nên lấy file và checksum từ cùng một vị trí không được bảo vệ rồi coi chúng là hai bằng chứng độc lập.

Nguồn tham chiếu tốt có thể là:

- Trang phát hành chính thức qua HTTPS với certificate hợp lệ.
- Repository chính thức của nhà phát hành.
- Kênh thông báo phát hành đã được xác thực độc lập.
- Metadata được lưu trong repository nội bộ đã qua review.
- Checksum được ký bằng khóa phát hành đã được xác minh.

Nếu nhà phát hành cung cấp file checksum riêng, hãy kiểm tra file đó đến từ đúng nguồn và đúng release. Nếu có chữ ký cho file checksum, xác minh chữ ký trước khi dùng digest trong file.

Một tình huống không an toàn là tải JAR và checksum từ cùng một mirror bị xâm phạm. Kẻ tấn công có thể thay cả hai để digest vẫn khớp. Khi đó, cần checksum hoặc chữ ký từ nguồn độc lập đáng tin cậy.

## 5. Chữ ký số và cặp khóa công khai/riêng

Chữ ký số sử dụng một cặp khóa:

- **Private key**: giữ bí mật, dùng để tạo chữ ký.
- **Public key**: có thể phân phối công khai, dùng để xác minh chữ ký.

Quy trình khái quát:

~~~text
Người phát hành
    |
    | artifact
    v
Tính digest và ký bằng private key
    |
    v
Artifact + chữ ký
    |
    | phân phối
    v
Consumer
    |
    | dùng public key đã tin cậy
    v
Xác minh chữ ký
~~~

Nếu nội dung đã ký bị thay đổi, xác minh chữ ký sẽ thất bại. Nếu chữ ký được tạo bằng private key không tương ứng với public key đang dùng, xác minh cũng thất bại.

### Chữ ký hợp lệ chưa tự chứng minh danh tính

Một public key có thể xác minh chữ ký về mặt toán học, nhưng ta vẫn cần biết khóa đó thuộc về ai. Nếu nhận public key từ cùng nguồn không đáng tin cậy với artifact, kẻ tấn công có thể thay cả artifact lẫn key.

Hãy xác minh fingerprint của public key qua một kênh độc lập, chẳng hạn tài liệu phát hành chính thức, danh bạ khóa của tổ chức hoặc xác nhận trực tiếp theo quy trình nội bộ.

Cần quản lý vòng đời khóa: thời hạn, thu hồi, thay khóa, quyền truy cập và quy trình xử lý khi khóa bị lộ.

## 6. Chữ ký JAR trong hệ sinh thái Java

Java hỗ trợ ký JAR bằng công cụ **jarsigner** của JDK. Khi ký, công cụ tạo các metadata trong META-INF, bao gồm manifest và các file chữ ký.

Một JAR đã ký thường có các file dạng:

~~~text
META-INF/
├── MANIFEST.MF
├── RELEASE.SF
└── RELEASE.RSA
~~~

Tên và loại file chữ ký có thể khác tùy thuật toán và cấu hình. Manifest chứa digest của các entry; file chữ ký chứa thông tin ký trên manifest hoặc phần tương ứng.

Chữ ký JAR bảo vệ các entry được ký trong archive. Nếu một entry đã ký bị sửa, thêm hoặc thay thế theo cách không được chữ ký bao phủ, xác minh sẽ phát hiện bất thường.

### Khi nào nên ký JAR?

- Phát hành thư viện hoặc ứng dụng Java cho bên ngoài.
- Cung cấp artifact cần xác minh danh tính nhà phát hành.
- Phân phối ứng dụng trong môi trường yêu cầu kiểm soát nguồn.
- Đáp ứng quy trình phát hành nội bộ hoặc chính sách bảo mật.

Chữ ký JAR không thay thế checksum ở mọi trường hợp. Chúng giải quyết các câu hỏi khác nhau và có thể được dùng cùng nhau.

## 7. Ký JAR bằng jarsigner

JAR có thể được ký bằng keystore chứa private key và certificate tương ứng.

Ví dụ minh họa:

~~~bash
jarsigner \
  -keystore /secure/path/release.p12 \
  -storetype PKCS12 \
  -signedjar order-client-1.0.0-signed.jar \
  order-client-1.0.0.jar \
  release-key
~~~

Công cụ có thể yêu cầu password tương tác nếu không được cung cấp qua tham số. Không ghi password hoặc private key trực tiếp vào lệnh, build script, file cấu hình được commit hay log CI.

Trong CI, private key nên được lưu trong secret manager hoặc signing service được kiểm soát. Chỉ job phát hành được cấp quyền ký artifact; build pull request từ mã không tin cậy không nên nhận quyền truy cập khóa phát hành.

Có thể dùng keystore PKCS12 hoặc định dạng được môi trường phát hành hỗ trợ. Alias là tên entry chứa khóa ký trong keystore.

### Ký sau khi đóng gói cuối cùng

Nếu artifact là Fat JAR hoặc đã qua shading, relocation, resource merge hay chỉnh sửa manifest, hãy ký sau khi tất cả biến đổi hoàn tất.

Mọi thay đổi nội dung sau khi ký có thể làm chữ ký không còn hợp lệ. Nếu cần chỉnh sửa artifact, hãy tạo lại và ký lại bản cuối cùng.

## 8. Xác minh chữ ký JAR

Dùng jarsigner:

~~~bash
jarsigner -verify -verbose -certs order-client-1.0.0-signed.jar
~~~

Có thể dùng chế độ strict để coi các cảnh báo nghiêm trọng về chữ ký/chứng thư là lỗi:

~~~bash
jarsigner -verify -strict -verbose -certs order-client-1.0.0-signed.jar
~~~

Kiểm tra certificate trong JAR:

~~~bash
keytool -printcert -jarfile order-client-1.0.0-signed.jar
~~~

Khi đọc kết quả, chú ý:

- Chữ ký có xác minh được về mặt mật mã không?
- Các entry cần thiết có được ký không?
- Có entry chưa ký không?
- Certificate của người ký là ai?
- Certificate có hết hạn hoặc có vấn đề về chain/trust không?
- Fingerprint có khớp với fingerprint đã được xác minh độc lập không?

Thông báo chữ ký hợp lệ không tự động có nghĩa certificate được hệ điều hành hoặc tổ chức tin cậy. Một certificate tự ký vẫn có thể dùng để kiểm tra chữ ký toán học, nhưng consumer phải có quy trình tin cậy riêng cho certificate đó.

Nếu dùng strict mode và lệnh trả mã khác 0, hãy đọc cảnh báo cụ thể. Có thể chữ ký không hợp lệ, certificate chain không được tin cậy hoặc JAR có entry chưa ký.

## 9. Xác minh certificate và fingerprint

Một certificate liên kết public key với thông tin danh tính. Khi nhận certificate của nhà phát hành, cần xác minh fingerprint qua kênh độc lập.

Không nên chỉ dựa vào tên hiển thị trong certificate. Tên có thể giống nhau hoặc không đủ để xác nhận người sở hữu khóa.

Quy trình:

1. Lấy certificate hoặc public key từ nguồn phát hành.
2. Tính hoặc hiển thị fingerprint.
3. So sánh với fingerprint công bố qua kênh tin cậy độc lập.
4. Kiểm tra thời hạn và chain theo chính sách PKI.
5. Kiểm tra trạng thái thu hồi nếu hệ thống có quy trình hỗ trợ.
6. Ghi nhận key ID/fingerprint và thời điểm xác minh.
7. Dùng đúng public key để xác minh artifact.

Với JAR, có thể xem certificate được gắn vào archive bằng keytool:

~~~bash
keytool -printcert -jarfile order-client-1.0.0-signed.jar
~~~

Nếu tổ chức dùng certificate nội bộ, consumer cần trust store và chính sách trust được cấu hình rõ ràng. Không tắt kiểm tra certificate chỉ để làm cho bước verify chạy qua.

## 10. Chữ ký PGP tách rời artifact

Nhiều repository phát hành file chữ ký tách rời, thường có phần mở rộng .asc:

~~~text
order-client-1.0.0.jar
order-client-1.0.0.jar.asc
~~~

File .asc chứa chữ ký PGP của artifact. Consumer dùng GnuPG và public key của nhà phát hành để xác minh.

Ví dụ:

~~~bash
gpg --verify order-client-1.0.0.jar.asc order-client-1.0.0.jar
~~~

Kết quả cho biết chữ ký có hợp lệ với key được dùng hay không. Cần tiếp tục xác minh fingerprint của key theo kênh đáng tin cậy.

Nếu GPG báo chữ ký hợp lệ nhưng key chưa được tin cậy, điều đó chỉ xác nhận dữ liệu khớp với key đã có; nó không chứng minh key thuộc đúng nhà phát hành.

Chữ ký tách rời hữu ích khi artifact không phải JAR hoặc khi repository yêu cầu ký nhiều loại file như POM, module metadata, source archive và binary archive.

## 11. JAR signing khác PGP detached signature như thế nào?

| Tiêu chí | JAR signing | PGP detached signature |
|---|---|---|
| Công cụ thường dùng | jarsigner, keytool | gpg |
| Chữ ký lưu ở đâu? | Metadata trong JAR | File chữ ký riêng, ví dụ .asc |
| Phạm vi | Các entry được ký trong JAR | Nội dung file được ký |
| Kiểu artifact | JAR | JAR, ZIP, POM, checksum hoặc file khác |
| Xác minh | jarsigner -verify | gpg --verify |
| Thông tin certificate/key | Certificate trong JAR | Public key được quản lý ngoài artifact |

Hai hình thức không loại trừ nhau. Một dự án có thể ký JAR bằng jarsigner và đồng thời ký publication artifact bằng PGP để phục vụ repository hoặc quy trình phân phối.

Cần hiểu định dạng mà consumer hoặc repository yêu cầu. Một file .asc không phải chữ ký JAR; ngược lại, file signature metadata bên trong JAR không tự động thay thế detached signature mà repository yêu cầu.

## 12. Gradle dependency verification

Gradle cung cấp **dependency verification** để kiểm tra các dependency được resolve trong build trước khi đưa chúng vào classpath hoặc sử dụng.

Cấu hình xác minh được lưu trong:

~~~text
gradle/verification-metadata.xml
~~~

File này có thể chứa checksum mong đợi và thông tin khóa PGP được tin cậy. Khi build resolve dependency, Gradle so sánh artifact và metadata với thông tin xác minh đã được cấu hình.

Dependency verification giúp phát hiện:

- Artifact bị thay đổi sau khi nhóm đã chấp nhận.
- Một version có nội dung khác với checksum đã ghi nhận.
- Artifact không có trong verification metadata.
- Chữ ký không hợp lệ hoặc được tạo bởi khóa không được tin cậy, nếu signature verification được bật.
- Metadata module thay đổi ngoài dự kiến, nếu metadata verification được bật.

File verification metadata nên được quản lý trong version control và review cùng thay đổi dependency.

### Checksum và chữ ký trong dependency verification

Checksum giúp xác minh byte của artifact so với digest đã chấp nhận. PGP verification giúp kiểm tra chữ ký và khóa ký.

Một build có thể dùng checksum mà không bật signature verification. Nếu muốn xác minh chữ ký PGP, cần cấu hình và tin cậy đúng public key. Không phải repository nào cũng cung cấp chữ ký cho mọi artifact.

## 13. Tạo verification metadata ban đầu

Gradle có thể tạo file verification metadata bằng tùy chọn:

~~~bash
./gradlew --write-verification-metadata sha256 build
~~~

Để thu thập cả checksum SHA-256 và thông tin chữ ký PGP nếu repository cung cấp:

~~~bash
./gradlew --write-verification-metadata sha256,pgp build
~~~

Lệnh cần thực hiện những task/configuration có resolve dependency mà nhóm muốn đưa vào phạm vi xác minh. Một lệnh build không nhất thiết resolve mọi configuration trong toàn bộ repository; các dependency chỉ dùng trong task hoặc source set chưa được chạy có thể chưa xuất hiện trong file metadata.

Sau khi sinh file:

1. Mở gradle/verification-metadata.xml.
2. Xem các module và artifact được thêm.
3. Kiểm tra checksum và key ID.
4. Xác minh nguồn artifact và fingerprint của key bằng kênh độc lập.
5. Loại bỏ hoặc điều chỉnh entry không mong muốn theo chính sách.
6. Commit file sau khi review.

**Không tự động tin mọi giá trị vừa sinh ra.** Nếu máy hoặc repository đang bị xâm phạm khi chạy lệnh tạo metadata, Gradle có thể ghi nhận checksum của artifact không đáng tin cậy. Việc tạo metadata chỉ thu thập giá trị; bước xác minh nguồn và review vẫn cần thiết.

## 14. Cấu trúc verification-metadata.xml

Một file rút gọn có thể trông như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<verification-metadata>
    <configuration>
        <verify-metadata>true</verify-metadata>
        <verify-signatures>false</verify-signatures>
    </configuration>
    <components>
        <component group="com.example" name="json-core">
            <artifact name="json-core-2.4.0.jar">
                <sha256 value="DIGEST_DA_XAC_MINH"/>
            </artifact>
        </component>
    </components>
</verification-metadata>
~~~

Digest ở ví dụ là placeholder, không phải checksum dùng được. File thật được Gradle tạo và cần được review.

Các phần quan trọng:

- **configuration**: điều khiển xác minh metadata và chữ ký.
- **components**: khai báo module và artifact cần xác minh.
- **artifact**: chỉ rõ tên file artifact.
- **sha256** hoặc thuật toán khác: digest mong đợi.
- **trusted-keys**: danh sách key PGP được tin cậy.
- **trusted-artifacts**: ngoại lệ cho artifact được miễn xác minh theo pattern, cần dùng rất hạn chế.

### Bật xác minh metadata

Property:

~~~xml
<verify-metadata>true</verify-metadata>
~~~

yêu cầu Gradle xác minh metadata module như POM hoặc Gradle Module Metadata theo thông tin verification đã khai báo.

Metadata quan trọng vì nó điều khiển dependency graph. Một POM hoặc .module bị thay đổi có thể làm consumer nhận dependency khác dù JAR chính không đổi.

### Bật xác minh chữ ký

Property:

~~~xml
<verify-signatures>true</verify-signatures>
~~~

bật kiểm tra chữ ký PGP theo cấu hình verification. Khi dùng, cần có chữ ký được repository cung cấp và key được tin cậy phù hợp. Nếu artifact không có chữ ký hoặc key không được tin cậy, build có thể thất bại.

Không bật signature verification một cách máy móc nếu repository không cung cấp chữ ký. Hãy xác định chính sách của dependency và dùng checksum verification khi đó là bằng chứng được chấp nhận.

## 15. Trusted keys và quản lý khóa PGP

Gradle dependency verification có thể ghi nhận key PGP được tin cậy trong phần trusted-keys của verification metadata.

Ví dụ minh họa:

~~~xml
<trusted-keys>
    <trusted-key id="0123456789ABCDEF"/>
</trusted-keys>
~~~

Key ID ở đây chỉ là giá trị minh họa. Trong file thật, cần dùng key được xác minh.

Một số lưu ý:

- Key ID ngắn có thể không đủ để phân biệt khóa; xác minh fingerprint đầy đủ.
- Key có thể hết hạn, bị thu hồi hoặc thay thế.
- Nhà phát hành có thể dùng nhiều khóa cho các release khác nhau.
- Khi key rotation, cần cập nhật metadata sau khi xác minh khóa mới.
- Không thêm key chỉ vì Gradle gợi ý trong log mà chưa kiểm tra nguồn.
- Không dùng trusted-artifacts rộng để bỏ qua kiểm tra toàn bộ nhóm dependency.

Nếu chữ ký của artifact thay đổi key, hãy xác minh thông báo key rotation từ nhà phát hành qua kênh độc lập trước khi cập nhật trusted-keys.

## 16. Dependency verification và metadata verification

Artifact JAR chứa bytecode/resource. POM và Gradle Module Metadata mô tả dependency graph, version, variant và constraints.

Nếu chỉ xác minh JAR mà không xác minh metadata, một kẻ tấn công có thể thay POM hoặc .module để kéo thêm dependency độc hại hoặc thay đổi graph.

Vì vậy, với build có yêu cầu an toàn cao, cân nhắc xác minh cả metadata:

~~~xml
<configuration>
    <verify-metadata>true</verify-metadata>
</configuration>
~~~

Gradle cần có verification metadata tương ứng để so sánh. Khi metadata được cập nhật có chủ đích, thay đổi phải được review như thay đổi dependency code.

Metadata verification có thể làm build thất bại khi repository cập nhật metadata hợp lệ nhưng checksum cũ chưa được cập nhật. Điều này là tín hiệu cần review, không phải lý do để tắt verification ngay lập tức.

## 17. Cập nhật verification metadata khi nâng dependency

Khi chủ động nâng version dependency, checksum và metadata có thể thay đổi. Quy trình an toàn:

1. Tạo branch thay đổi dependency.
2. Kiểm tra release notes và nguồn phát hành.
3. Chạy build với tùy chọn ghi verification metadata cho version mới.
4. Xem diff của gradle/verification-metadata.xml.
5. Xác minh checksum hoặc PGP key theo nguồn đáng tin cậy.
6. Xem dependency graph trước và sau.
7. Chạy test và build consumer liên quan.
8. Review thay đổi metadata cùng với version update.
9. Commit file metadata sau khi đã chấp nhận artifact.

Không nên xóa toàn bộ verification-metadata.xml để làm build qua. Hành động đó loại bỏ chính sách xác minh cho mọi dependency.

Nếu một dependency đã publish lại cùng tọa độ/version với nội dung khác, cần điều tra lý do. Không tự động cập nhật checksum để chấp nhận artifact mới; việc thay nội dung dưới cùng version có thể là dấu hiệu repository bị ghi đè hoặc supply chain bị xâm phạm.

## 18. Kiểm tra Gradle Wrapper distribution bằng SHA-256

Gradle Wrapper tải một bản Gradle distribution theo URL trong:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

Có thể khai báo checksum SHA-256 của distribution ZIP:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=SHA256_DA_XAC_MINH
~~~

Khi Wrapper tải distribution, nó kiểm tra file tải về với checksum đã khai báo. Nếu không khớp, Wrapper dừng thay vì tiếp tục dùng distribution không đúng.

Giá trị SHA256_DA_XAC_MINH chỉ là placeholder. Lấy checksum chính thức tương ứng với đúng file distribution và version từ nguồn Gradle đáng tin cậy, rồi xác minh theo chính sách của tổ chức.

### Phân biệt Wrapper checksum với dependency verification

| Cơ chế | Đối tượng được kiểm tra |
|---|---|
| distributionSha256Sum | ZIP Gradle distribution mà Wrapper tải |
| dependency verification | Dependency và metadata được Gradle resolve |
| jarsigner | Entry được ký trong JAR |
| gpg --verify | File được ký bằng detached PGP signature |
| sha256sum/Get-FileHash | Digest của một file cụ thể |

Wrapper checksum không xác minh JAR dependency của project. Dependency verification cũng không thay thế checksum của Gradle distribution.

### gradle-wrapper.jar cũng cần được bảo vệ

Wrapper JAR là bootstrap code được commit trong repository. distributionSha256Sum chỉ áp dụng cho distribution ZIP, không xác minh file gradle-wrapper.jar.

Hãy lấy Wrapper JAR từ quy trình tạo Wrapper đáng tin cậy, review thay đổi của file này và sử dụng kiểm tra integrity phù hợp với chính sách tổ chức. Không nhận một Wrapper JAR lạ chỉ vì distribution checksum vẫn đúng.

## 19. Kiểm tra checksum và chữ ký trong quy trình phát hành Gradle

Nếu thư viện được publish lên Maven repository, có thể dùng Gradle Signing plugin để tạo chữ ký cho publication.

Ví dụ Kotlin DSL:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
    id("signing")
}

group = "com.example"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            artifactId = "order-client"
        }
    }
}

signing {
    useGpgCmd()
    sign(publishing.publications["mavenJava"])
}
~~~

Signing plugin tích hợp với publication để tạo các chữ ký tương ứng cho artifact và metadata được ký. Cấu hình thực tế phụ thuộc công cụ GPG, khóa và yêu cầu repository.

Với GPG command mode, môi trường phát hành cần có GPG và private key đã được cấu hình an toàn. Không commit private key hoặc passphrase vào repository.

Có thể kiểm tra các task được tạo:

~~~bash
./gradlew tasks --all
~~~

Sau khi publish vào repository thử nghiệm, xác nhận các file signature được tạo và xác minh bằng public key tin cậy. Đừng chỉ kiểm tra task sign có chạy thành công; cần thử verify artifact đã publish.

## 20. Lưu trữ khóa ký an toàn trong CI

Private key là tài sản nhạy cảm. Nếu bị lộ, kẻ tấn công có thể tạo artifact hoặc metadata có chữ ký trông như phát hành hợp lệ.

Các nguyên tắc:

- Lưu private key trong secret manager hoặc hệ thống ký chuyên dụng.
- Chỉ cấp quyền cho job phát hành đã được bảo vệ.
- Không đưa private key vào Git, build log, artifact trung gian hoặc image dùng chung.
- Giới hạn người có quyền trigger release workflow.
- Tách job kiểm thử pull request khỏi job ký release.
- Dùng quyền ngắn hạn hoặc signing service nếu hệ thống hỗ trợ.
- Có kế hoạch thu hồi và thay khóa khi nghi bị lộ.
- Giữ audit log cho thao tác ký.
- Xác minh fingerprint của public key công bố cho consumer.

Không nên truyền password keystore qua command line vì có thể xuất hiện trong process list hoặc log. Ưu tiên secret handling của CI và cơ chế nhập khóa mà plugin/công cụ hỗ trợ.

## 21. Kiểm tra artifact sau khi đóng gói

Artifact cần được xác minh ở đúng thời điểm phát hành. Nếu build tạo JAR, sau đó một bước khác sửa manifest, nén lại hoặc gộp resource, chữ ký cũ không còn phù hợp.

Một luồng an toàn:

~~~text
Compile + Test
     |
     v
Package final JAR
     |
     v
Compute checksum
     |
     v
Sign final artifact
     |
     v
Verify signature and checksum
     |
     v
Publish immutable artifact
~~~

Thứ tự có thể khác nếu quy trình ký metadata của repository, nhưng chữ ký phải bao phủ đúng nội dung cuối cùng mà consumer tải về.

Sau khi ký:

- Không sửa JAR.
- Không thêm resource.
- Không thay manifest.
- Không repack archive.
- Nếu phải thay đổi nội dung, tạo artifact mới và ký lại.
- Tính lại checksum của file cuối cùng.
- Lưu chữ ký và checksum gắn với đúng version.

Đối với Fat JAR, hãy ký sau khi Shadow hoặc công cụ đóng gói hoàn tất việc merge và relocation.

## 22. TLS không thay thế checksum hoặc chữ ký

HTTPS bảo vệ kết nối đến repository và giúp xác thực máy chủ qua certificate chain. Điều đó rất quan trọng, nhưng không tự chứng minh artifact là đúng release mà nhà phát hành dự định.

Một repository hợp lệ có thể bị xâm phạm; một tài khoản publish có thể bị chiếm; một artifact có thể được phát hành nhầm. TLS sẽ bảo vệ kết nối đến máy chủ đó nhưng không phát hiện nội dung độc hại đã được publish từ trước.

Kết hợp nhiều lớp:

- HTTPS để bảo vệ đường truyền.
- Dependency verification để xác minh artifact và metadata.
- Chữ ký để liên kết artifact với khóa phát hành.
- Version locking/constraints để kiểm soát lựa chọn dependency.
- Review và provenance để hiểu nguồn gốc build.
- SBOM để mô tả thành phần trong artifact.
- CI policy để đảm bảo kiểm tra được thực hiện trước phát hành.

## 23. Dependency locking bổ sung cho checksum

Dependency locking ghi lại phiên bản thực tế được phân giải cho configuration. Nó giúp các lần build sau dùng cùng version đã được chốt, trong phạm vi lock state được quản lý.

Ví dụ bật dependency locking cho configuration:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.activateDependencyLocking()
}
~~~

Ghi lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Dependency locking kiểm soát **version được chọn**. Checksum verification kiểm soát **nội dung artifact tại version đó**.

Hai cơ chế bổ sung cho nhau:

| Kiểm soát | Bảo vệ điều gì? |
|---|---|
| Version lock | Tránh version graph thay đổi ngoài dự kiến |
| Checksum verification | Phát hiện artifact bytes khác với digest được chấp nhận |
| PGP signature | Xác minh chữ ký và khóa ký |
| Metadata verification | Phát hiện metadata dependency thay đổi |
| Wrapper checksum | Xác minh Gradle distribution ZIP |

Lockfile không chứng minh JAR không bị thay nội dung dưới cùng tọa độ/version. Checksum không quyết định version nào nên được chọn. Nên dùng cả hai nếu chính sách build yêu cầu.

## 24. SBOM và provenance bổ sung cho xác minh

**SBOM** (Software Bill of Materials) liệt kê các thành phần phần mềm được đưa vào một sản phẩm. Nó giúp trả lời artifact chứa thư viện nào và version nào.

**Provenance** mô tả nguồn và quy trình tạo artifact, chẳng hạn repository, commit, workflow, builder và thông tin môi trường.

Checksum và chữ ký không thay thế SBOM hoặc provenance:

- Checksum xác minh byte.
- Chữ ký xác minh chữ ký của khóa.
- SBOM mô tả thành phần.
- Provenance mô tả quá trình tạo và nguồn.
- Reproducible build giúp so sánh output giữa các lần build có điều kiện tương đương.

Một artifact có chữ ký hợp lệ vẫn có thể được tạo từ source không đáng tin cậy. Do đó, xác minh nguồn cần xem cả người ký, repository source, commit, workflow và quyền phát hành.

## 25. Các lỗi thường gặp khi xác minh

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| SHA-256 không khớp | File tải sai, artifact bị thay đổi hoặc digest lấy sai version | Kiểm tra tên/version, tải lại từ nguồn chính thức và xác minh digest qua kênh độc lập |
| PGP signature invalid | File bị thay đổi hoặc chữ ký không tương ứng artifact | Kiểm tra đúng file .asc và artifact, xác minh nguồn tải |
| Signature valid nhưng key không được tin cậy | Public key chưa được xác minh hoặc trust chưa được cấu hình | Xác minh fingerprint độc lập rồi cập nhật trust policy |
| JAR có unsigned entries | Có entry chưa được ký hoặc archive bị bổ sung sau khi ký | Kiểm tra nội dung và ký lại artifact cuối cùng |
| jarsigner báo certificate chain warning | Certificate tự ký, thiếu intermediate hoặc trust store chưa có CA | Xác minh chain và cấu hình trust đúng chính sách |
| Gradle báo verification metadata missing | Dependency mới chưa có entry trong verification file | Xác minh nguồn, sinh metadata và review diff |
| Gradle báo checksum mismatch | Artifact khác digest đã được chấp nhận | Dừng phát hành, xác minh artifact/repository; không cập nhật checksum mù quáng |
| Gradle không tìm thấy PGP signature | Repository không cung cấp signature hoặc artifact không được ký | Xác nhận chính sách; dùng checksum được xác minh hoặc yêu cầu nhà phát hành cung cấp chữ ký |
| Wrapper báo distribution checksum mismatch | ZIP tải về không khớp digest đã cấu hình | Kiểm tra URL, proxy/cache và checksum chính thức |
| Build fail sau khi bật metadata verification | POM hoặc .module thay đổi so với metadata đã ghi | Review thay đổi metadata và xác minh dependency graph trước khi cập nhật |
| Build fail khi đổi khóa phát hành | Trusted key cũ không còn phù hợp | Xác minh key rotation qua kênh độc lập rồi cập nhật trusted-keys |
| Chữ ký mất hiệu lực sau khi đóng gói | JAR bị chỉnh sửa sau khi ký | Ký lại artifact sau bước đóng gói cuối |

Không nên xử lý checksum mismatch bằng cách ghi đè digest mới ngay lập tức. Đó là một tín hiệu an toàn cần điều tra.

## 26. Quy trình xác minh dependency trong dự án Gradle

Một quy trình có thể áp dụng:

1. Xác định dependency trực tiếp và version mà build cần.
2. Dùng repository chính thức qua HTTPS.
3. Bật dependency verification trong Gradle.
4. Tạo verification metadata bằng SHA-256; thu thập PGP khi repository cung cấp.
5. Xác minh fingerprint của khóa phát hành độc lập.
6. Review và commit gradle/verification-metadata.xml.
7. Bật metadata verification nếu cần bảo vệ POM và Gradle Module Metadata.
8. Bật dependency locking để cố định version được chọn.
9. Xác minh Gradle Wrapper distribution bằng distributionSha256Sum.
10. Chạy build trong CI với cùng chính sách verification.
11. Khi dependency được nâng version, review thay đổi checksum, signature key và dependency graph.
12. Không tắt verification để bỏ qua lỗi không rõ nguyên nhân.

Lệnh tạo metadata ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256,pgp build
~~~

Sau khi file được review và commit, build bình thường sẽ dùng metadata đó để xác minh dependency. Hãy chạy thêm các task cần thiết để resolve các configuration khác ngoài những gì lệnh ban đầu đã chạm tới.

## 27. Quy trình xác minh artifact trước khi phát hành

Đối với artifact do chính dự án tạo:

1. Chạy test và build từ source/commit đã được review.
2. Tạo artifact cuối cùng trong môi trường phát hành được kiểm soát.
3. Tính SHA-256 hoặc SHA-512 cho artifact.
4. Ký artifact bằng khóa phát hành được quản lý an toàn.
5. Xác minh chữ ký bằng public key tin cậy.
6. Kiểm tra certificate, fingerprint và trạng thái trust.
7. Lưu checksum, chữ ký và metadata cùng release.
8. Publish artifact vào repository theo quy trình immutable release.
9. Tải artifact từ repository như một consumer và xác minh lại.
10. Lưu log phát hành, commit, builder identity và provenance theo chính sách.

Kiểm tra lại file sau khi tải từ repository giúp xác nhận artifact được lưu trữ và phân phối đúng với bản đã ký.

## 28. Những nguyên tắc cần nhớ

- Checksum xác minh byte của file so với digest đã tin cậy; nó không tự xác minh danh tính người phát hành.
- Chữ ký số liên kết nội dung với private key; cần xác minh public key/fingerprint qua kênh độc lập.
- Ưu tiên SHA-256 hoặc SHA-512; tránh dùng MD5 hoặc SHA-1 cho mục tiêu bảo mật mới.
- Tính checksum bằng sha256sum, shasum, Get-FileHash hoặc certutil và so sánh với digest đúng version.
- JAR signing dùng jarsigner; PGP detached signature dùng gpg --verify.
- Xác minh chữ ký phải kiểm tra cả nội dung ký lẫn trust của certificate/key.
- Ký JAR sau khi hoàn tất mọi bước đóng gói, merge resource và relocation.
- Gradle dependency verification lưu chính sách trong gradle/verification-metadata.xml.
- Sinh metadata bằng --write-verification-metadata chỉ là bước thu thập; cần xác minh nguồn và review trước khi tin.
- Bật verify-metadata khi cần bảo vệ cả POM và Gradle Module Metadata.
- distributionSha256Sum bảo vệ Gradle Wrapper distribution ZIP, không bảo vệ dependency JAR hoặc wrapper JAR.
- Dependency locking cố định version; checksum verification cố định nội dung; chữ ký xác minh khóa phát hành.
- TLS, SBOM, provenance và reproducible build bổ sung cho checksum/chữ ký.
- Không bỏ qua checksum mismatch hoặc cập nhật digest mới khi chưa điều tra.
- Giữ private key trong secret manager hoặc signing service; không commit hoặc ghi secret vào log.
- Xác minh artifact sau khi tải từ repository để bảo đảm bản consumer nhận được đúng bản đã phát hành.

Checksum và chữ ký là hai lớp quan trọng trong an toàn build. Checksum giúp phát hiện nội dung thay đổi so với bản tham chiếu; chữ ký giúp xác minh artifact được ký bởi khóa mà tổ chức tin cậy. Khi kết hợp Gradle dependency verification, Wrapper checksum, JAR/PGP signature, dependency locking và quy trình CI có kiểm soát, nhóm có thể phát hiện thay đổi bất thường trong dependency cũng như bảo vệ artifact do mình phát hành.
