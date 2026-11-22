# Signature algorithm trong jarsigner

## 1. Signature algorithm là gì?

Signature algorithm (thuật toán chữ ký số) là thuật toán dùng khóa riêng để tạo chữ ký và khóa công khai tương ứng để xác minh chữ ký. Trong Java, công cụ `jarsigner` dùng chữ ký số để xác nhận tính toàn vẹn của các entry trong JAR và nhận diện chứng thư của bên ký.

Một chữ ký JAR cung cấp hai thuộc tính chính:

- **Integrity:** nội dung entry được ký không bị thay đổi kể từ lúc ký. Nếu dữ liệu thay đổi, phép kiểm tra digest hoặc chữ ký sẽ thất bại.
- **Authenticity:** chữ ký được tạo bằng khóa riêng tương ứng với khóa công khai trong chứng thư của người ký. Người nhận có thể dùng chứng thư và chuỗi tin cậy để đánh giá danh tính bên ký.

Chữ ký số không mã hóa nội dung JAR. Người nhận vẫn có thể đọc class, resource và các file khác trong archive. Nó cũng không tự chứng minh phần mềm an toàn; nó cho biết nội dung có khớp với chữ ký và khóa ký hay không.

`jarsigner` dùng khóa riêng lấy từ keystore để ký, sau đó đưa chữ ký và chứng thư tương ứng vào JAR. Khi xác minh, công cụ dùng khóa công khai trong chứng thư để kiểm tra chữ ký.

## 2. Phân biệt digest algorithm và signature algorithm

Khi ký JAR, có hai loại thuật toán thường được cấu hình riêng:

| Thành phần | Tùy chọn | Nhiệm vụ |
|---|---|---|
| Message digest | `-digestalg` | Tính hash của nội dung từng entry trong JAR và ghi digest vào manifest. |
| Digital signature | `-sigalg` | Ký file chữ ký `.SF` bằng khóa riêng của người ký. |

Digest là giá trị hash có độ dài cố định được tính từ dữ liệu. Nó không sử dụng khóa riêng và không tự xác thực danh tính người ký.

Signature algorithm kết hợp cơ chế ký bất đối xứng với digest hoặc tham số chữ ký tương ứng. Khi xác minh, công cụ kiểm tra chữ ký bằng khóa công khai.

Ví dụ:

~~~bash
jarsigner -digestalg SHA-256 -sigalg SHA256withRSA ...
~~~

Trong lệnh này:

- `SHA-256` là thuật toán digest của các entry trong JAR.
- `SHA256withRSA` là thuật toán ký file `.SF` bằng khóa RSA.
- Phần SHA-256 nằm trong tên `SHA256withRSA` là digest được dùng bên trong thuật toán chữ ký RSA.

Hai tùy chọn liên quan nhưng không phải cùng một cấu hình. Có thể dùng `-digestalg SHA-256` với `-sigalg SHA384withRSA` nếu provider, chính sách bảo mật và môi trường đích hỗ trợ tổ hợp đó.

## 3. Cấu trúc chữ ký trong JAR

Khi ký một JAR, `jarsigner` cập nhật manifest và tạo các file chữ ký trong `META-INF`. Với một người ký, các thành phần quan trọng là:

~~~text
app-signed.jar
└── META-INF/
    ├── MANIFEST.MF
    ├── RELEASE.SF
    └── RELEASE.RSA
~~~

Tên file cụ thể được tạo từ alias hoặc tùy chọn `-sigfile`. Phần mở rộng của signature block phụ thuộc loại khóa ký, ví dụ `.RSA`, `.EC` hoặc `.DSA`.

Luồng ký được thực hiện theo các bước:

1. Tính digest của dữ liệu từng entry và ghi giá trị vào `META-INF/MANIFEST.MF`.
2. Tạo file `.SF` chứa digest của manifest hoặc các section tương ứng.
3. Dùng private key ký nội dung file `.SF`.
4. Ghi chữ ký số cùng chứng thư hoặc certificate chain vào signature block.
5. Đưa các file này vào thư mục `META-INF` của JAR.

Vai trò từng file:

- **MANIFEST.MF:** chứa metadata và digest của từng entry được ký.
- **.SF:** chứa digest của manifest và các section liên quan; đây là dữ liệu được ký số.
- **.RSA / .EC / .DSA:** chứa chữ ký của file `.SF` cùng chứng thư cần để xác minh public key.

File `.SF` và signature block không thay thế manifest. Chúng liên kết digest của entry với chữ ký số của người ký.

## 4. Cách xác minh chữ ký JAR

Khi chạy `jarsigner -verify`, công cụ kiểm tra chuỗi dữ liệu chữ ký theo thứ tự:

1. Xác minh chữ ký số của file `.SF` bằng public key trong chứng thư.
2. Kiểm tra digest của manifest hoặc từng section trong `.SF`.
3. Tính lại digest từ dữ liệu thực tế của từng entry và so sánh với giá trị trong manifest.
4. Kiểm tra việc sử dụng thuật toán bị vô hiệu hóa theo security properties của JDK.
5. Đánh giá chứng thư và chuỗi chứng thư; các cảnh báo được hiển thị để người vận hành xem xét.

Nếu nội dung một entry đã ký bị thay đổi, digest mới không khớp với manifest và quá trình xác minh thất bại.

Cần phân biệt hai câu hỏi:

- **Chữ ký có hợp lệ về mặt mật mã và nội dung có nguyên vẹn không?**
- **Chứng thư của người ký có được tin cậy trong môi trường nhận không?**

Một JAR có thể hiện dòng `jar verified.` nhưng vẫn đi kèm cảnh báo chứng thư tự ký hoặc certificate chain không được tin cậy. Chữ ký hợp lệ không tự động làm cho danh tính người ký trở thành trusted.

## 5. Các thuật toán chữ ký phổ biến

`jarsigner` hỗ trợ nhiều thuật toán tùy phiên bản JDK, provider, loại private key và chính sách bảo mật.

| Thuật toán | Loại khóa | Đặc điểm |
|---|---|---|
| `SHA256withRSA` | RSA | Kết hợp SHA-256 với chữ ký RSA PKCS#1 v1.5; tương thích rộng với các JDK hiện đại. |
| `SHA384withRSA` | RSA | Dùng SHA-384 với RSA; thường được chọn làm mặc định trên một số cấu hình JDK hiện đại. |
| `SHA256withECDSA` | EC | Dùng SHA-256 với Elliptic Curve Digital Signature Algorithm. |
| `SHA384withECDSA` | EC | Dùng SHA-384 với ECDSA. |
| `RSASSA-PSS` | RSA / RSASSA-PSS | Cơ chế RSA Probabilistic Signature Scheme; sử dụng các tham số hash, salt và mask generation function. |
| `Ed25519` / `Ed448` | EdDSA | Chữ ký Edwards-curve; tên thuật toán gắn với bộ tham số của khóa. |

Một số điểm cần nhớ:

- RSA, EC, RSASSA-PSS và EdDSA có cách chọn tham số khác nhau.
- Thuật toán ký phải tương thích với private key được chọn trong keystore.
- Với RSASSA-PSS, tham số hash, MGF và salt length là một phần của cấu hình chữ ký.
- Với Ed25519, tên thuật toán ký là `Ed25519`; `-digestalg` vẫn điều khiển digest entry của JAR.
- DSA và các thuật toán dựa trên SHA-1 hoặc MD5 là lựa chọn cũ; không dùng để ký artifact mới nếu không có yêu cầu tương thích được đánh giá và phê duyệt.

Tên thuật toán chuẩn không phân biệt chữ hoa/chữ thường. Tham khảo danh sách Java Security Standard Algorithm Names để chọn đúng tên và kiểm tra hỗ trợ của provider.

## 6. Mặc định thuật toán phụ thuộc JDK và loại khóa

Nếu không chỉ định `-sigalg`, `jarsigner` chọn thuật toán chữ ký mặc định tương thích với loại và kích thước private key. Nếu không chỉ định `-digestalg`, mặc định cũng phụ thuộc phiên bản JDK.

Không nên giả định một mặc định sẽ giữ nguyên qua mọi bản JDK. Oracle có thể cập nhật mặc định và security policy để tăng cường bảo mật.

Trong môi trường kiểm chứng JDK 24.0.2:

- JAR ký bằng RSA 3072-bit với cấu hình mặc định hiển thị digest `SHA-384` và signature algorithm `SHA384withRSA`.
- Khi chỉ định `-digestalg SHA-256 -sigalg SHA256withRSA`, phần xác minh hiển thị SHA-256 và SHA256withRSA.
- Khóa EC P-256 ký thành công với `SHA256withECDSA`.
- Khóa Ed25519 và khóa RSASSA-PSS cũng ký và xác minh thành công.

Đây là kết quả của JDK 24.0.2 và provider đang cài. Khi build cho nhiều runtime, hãy kiểm tra thuật toán được hỗ trợ trên tất cả phiên bản đích thay vì sao chép mặc định từ máy phát triển.

Có thể xem phiên bản công cụ:

~~~bash
jarsigner -version
java --version
~~~

Xem danh sách thuật toán chuẩn trong tài liệu JCA/JCE của đúng phiên bản Java đang sử dụng.

## 7. Chuẩn bị keystore và khóa ký

`jarsigner` cần một keystore có entry chứa private key và certificate chain. Alias truyền ở cuối lệnh phải trỏ tới `PrivateKeyEntry`, không phải chỉ là một trusted certificate entry.

Tạo một keystore PKCS12 cho ví dụ:

~~~bash
keytool -genkeypair \
  -alias releaseSigner \
  -keyalg RSA \
  -keysize 3072 \
  -dname "CN=Example Release Signer" \
  -validity 365 \
  -keystore release-signing.p12 \
  -storetype PKCS12
~~~

`keytool` sẽ hỏi mật khẩu keystore và thông tin xác nhận. Với PKCS12 mặc định, mật khẩu bảo vệ keystore cũng được dùng để bảo vệ private key entry trong ví dụ này.

Kiểm tra entry:

~~~bash
keytool -list -v \
  -keystore release-signing.p12 \
  -storetype PKCS12
~~~

Xác nhận alias có:

~~~text
Entry type: PrivateKeyEntry
~~~

Keystore dùng trong ví dụ tạo chứng thư tự ký để thử nghiệm. Trong môi trường phát hành thật, cần dùng chứng thư theo chính sách tổ chức, lưu private key trong vùng bảo vệ phù hợp và phân phối certificate chain theo quy trình tin cậy.

Không đưa keystore hoặc private key vào source repository, JAR phát hành hay artifact công khai. Không chia sẻ mật khẩu ký trong log build.

## 8. Tạo JAR mẫu

Tạo một resource đơn giản để có thể quan sát digest:

~~~bash
mkdir -p input
printf "Original signed content\n" > input/message.txt
jar --create --file app.jar -C input .
jar --list --file app.jar
~~~

Trên Windows PowerShell, có thể tạo file và JAR như sau:

~~~powershell
New-Item -ItemType Directory -Force input | Out-Null
Set-Content -Encoding ascii input/message.txt "Original signed content"
jar --create --file app.jar -C input .
jar --list --file app.jar
~~~

Output có entry:

~~~text
META-INF/
META-INF/MANIFEST.MF
message.txt
~~~

Đảm bảo mọi class và resource cuối cùng đã được đưa vào JAR trước khi ký. Nếu sửa hoặc thay nội dung entry sau khi ký, chữ ký của entry đó sẽ không còn hợp lệ.

## 9. Ký JAR bằng RSA và SHA-256

Sử dụng keystore đã tạo ở phần trước:

~~~bash
jarsigner \
  -keystore release-signing.p12 \
  -storetype PKCS12 \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -signedjar app-signed.jar \
  app.jar \
  releaseSigner
~~~

Nếu không truyền mật khẩu trong command line, `jarsigner` sẽ yêu cầu nhập khi cần. Cách này tránh đưa mật khẩu trực tiếp vào lịch sử lệnh.

Sau khi ký, kiểm tra cấu trúc:

~~~bash
jar --list --file app-signed.jar
~~~

Trong `META-INF` sẽ có các file tương tự:

~~~text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
~~~

Tên thực tế phụ thuộc alias và `-sigfile`. Phần mở rộng `.RSA` cho biết signature block được tạo với khóa RSA.

## 10. Xem digest và chữ ký trong archive

Có thể giải nén manifest và signature file để xem các trường digest:

~~~bash
jar --extract --file app-signed.jar META-INF/MANIFEST.MF
jar --extract --file app-signed.jar META-INF/RELEASE.SF
~~~

Một section trong manifest có thể có dạng:

~~~text
Name: message.txt
SHA-256-Digest: <base64 digest>
~~~

File `.SF` có thể chứa:

~~~text
Signature-Version: 1.0
SHA-256-Digest-Manifest: <base64 digest>
SHA-256-Digest-Manifest-Main-Attributes: <base64 digest>

Name: message.txt
SHA-256-Digest: <base64 digest>
~~~

Các giá trị Base64 ở đây chỉ minh họa cấu trúc. Giá trị thực được tạo từ nội dung JAR tại thời điểm ký.

`MANIFEST.MF` chứa digest của dữ liệu entry. `.SF` chứa digest của manifest và các section tương ứng. Signature block chứa chữ ký của `.SF` và chứng thư. Đây là lý do việc sửa nội dung file sau khi ký sẽ làm xác minh thất bại.

## 11. Xác minh chữ ký và chứng thư

Xác minh cơ bản:

~~~bash
jarsigner -verify app-signed.jar
~~~

Để xem entry, signer và certificate:

~~~bash
jarsigner -verify -verbose:summary -certs app-signed.jar
~~~

Output có thể có dạng:

~~~text
- Signed by "CN=Example Release Signer"
    Digest algorithm: SHA-256
    Signature algorithm: SHA256withRSA, 3072-bit RSA key

jar verified.
~~~

Nếu dùng chứng thư tự ký, output có thể kèm cảnh báo certificate chain không được tin cậy và chứng thư tự ký. Điều này không đồng nghĩa với digest hoặc chữ ký mật mã bị sai; nó cho biết bên xác minh chưa có trust path phù hợp.

Khi kiểm tra trong môi trường có truststore, truyền keystore chứa certificate được tin cậy:

~~~bash
jarsigner -verify -strict \
  -keystore trusted-signers.p12 \
  -storetype PKCS12 \
  -verbose:summary \
  -certs \
  app-signed.jar
~~~

`-strict` khiến các cảnh báo nghiêm trọng được xử lý như lỗi. Hãy đọc toàn bộ output, đặc biệt các thông báo về certificate chain, trạng thái chứng thư, timestamp và thuật toán.

`jar verified.` là kết quả kiểm tra chữ ký và tính toàn vẹn. Nó không thay thế việc xác định trust anchor, chính sách phát hành và danh tính signer trong môi trường triển khai.

## 12. Thử nghiệm khi nội dung JAR bị thay đổi

Sau khi ký, thay nội dung của một entry đã được ký:

~~~bash
mkdir -p altered
printf "Modified content after signing\n" > altered/message.txt
jar --update --file app-signed.jar -C altered message.txt
jarsigner -verify app-signed.jar
~~~

Kết quả sẽ báo lỗi digest hoặc security exception tương tự:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-256 digest error for message.txt
~~~

Điều này chứng minh chữ ký gắn với nội dung tại thời điểm ký. Trong quy trình build, chỉ ký sau khi đã hoàn tất biên dịch, đóng gói, nén và mọi bước chỉnh sửa JAR.

Nếu cần cập nhật artifact, tạo lại JAR từ nguồn build rồi ký lại. Không sửa trực tiếp resource hoặc class trong JAR đã phát hành.

## 13. Chọn thuật toán tương thích với private key

`-sigalg` phải tương thích với loại khóa trong alias. Một số tổ hợp thông dụng:

| Khóa tạo bằng keytool | Thuật toán ký tương ứng |
|---|---|
| `-keyalg RSA` | `SHA256withRSA`, `SHA384withRSA` hoặc `RSASSA-PSS` nếu provider và policy hỗ trợ. |
| `-keyalg EC` | `SHA256withECDSA` hoặc `SHA384withECDSA`. |
| `-keyalg RSASSA-PSS` | `RSASSA-PSS` với tham số phù hợp. |
| `-keyalg Ed25519` | `Ed25519`. |
| `-keyalg EdDSA` | Thuật toán EdDSA phù hợp với loại khóa và provider. |

Ví dụ tạo khóa EC P-256:

~~~bash
keytool -genkeypair \
  -alias ecSigner \
  -keyalg EC \
  -groupname secp256r1 \
  -dname "CN=EC Release Signer" \
  -keystore ec-signing.p12 \
  -storetype PKCS12
~~~

Ký bằng ECDSA:

~~~bash
jarsigner \
  -keystore ec-signing.p12 \
  -digestalg SHA-256 \
  -sigalg SHA256withECDSA \
  -signedjar app-ec-signed.jar \
  app.jar \
  ecSigner
~~~

Ví dụ tạo khóa Ed25519:

~~~bash
keytool -genkeypair \
  -alias edSigner \
  -keyalg Ed25519 \
  -dname "CN=Ed Release Signer" \
  -keystore ed-signing.p12 \
  -storetype PKCS12
~~~

Ký bằng Ed25519:

~~~bash
jarsigner \
  -keystore ed-signing.p12 \
  -signedjar app-ed-signed.jar \
  app.jar \
  edSigner
~~~

Với Ed25519, JDK có thể chọn digest entry độc lập, ví dụ SHA-384, trong khi signature algorithm hiển thị là Ed25519. Không thêm `withRSA` hoặc `withECDSA` vào tên thuật toán cho một khóa Ed25519.

Nếu chọn thuật toán không tương thích, `jarsigner` sẽ báo lỗi dạng:

~~~text
key algorithm not compatible with signature algorithm
~~~

Không cố ép thuật toán chỉ để làm cho lệnh chạy. Hãy chọn key pair và signature algorithm như một cặp phù hợp.

## 14. RSASSA-PSS và tham số chữ ký

`RSASSA-PSS` là một scheme chữ ký RSA có tính ngẫu nhiên. Khác với tên dạng `SHA256withRSA`, PSS có các tham số như:

- Digest algorithm.
- Mask Generation Function, thường là MGF1.
- Digest của MGF1.
- Salt length.
- Trailer field.

Nếu khóa RSASSA-PSS được tạo với tham số đã mã hóa, `jarsigner` dùng các tham số tương ứng. Nếu không, công cụ chọn tham số theo quy tắc của JDK và kích thước khóa.

Ví dụ tạo khóa và ký:

~~~bash
keytool -genkeypair \
  -alias pssSigner \
  -keyalg RSASSA-PSS \
  -keysize 3072 \
  -dname "CN=PSS Release Signer" \
  -keystore pss-signing.p12 \
  -storetype PKCS12

jarsigner \
  -keystore pss-signing.p12 \
  -sigalg RSASSA-PSS \
  -signedjar app-pss-signed.jar \
  app.jar \
  pssSigner
~~~

PSS ký và xác minh thành công trên JDK 24.0.2 trong phép thử của bài này. Trước khi dùng trong sản phẩm, kiểm tra provider, tham số và mọi JDK runtime cần xác minh artifact.

## 15. Timestamp cho chữ ký

Timestamp cho biết chữ ký đã tồn tại tại một thời điểm được Time-Stamping Authority (TSA) xác nhận. Nó hữu ích khi chứng thư ký có thời hạn: hệ thống có thể kiểm tra rằng JAR đã được ký khi chứng thư còn hiệu lực.

Dùng `-tsa` để chỉ định URL của TSA:

~~~bash
jarsigner \
  -keystore release-signing.p12 \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -tsa "$TSA_URL" \
  -signedjar app-timestamped.jar \
  app.jar \
  releaseSigner
~~~

Thiết lập biến môi trường `TSA_URL` thành endpoint TSA được tổ chức chấp thuận trước khi chạy. Khi TSA trả timestamp token thành công, token được lưu cùng signature block trong JAR.

Các tùy chọn liên quan:

- `-tsa URL` chỉ định TSA endpoint.
- `-tsacert alias` lấy TSA certificate từ keystore; chứng thư cần có thông tin Subject Information Access xác định URL TSA.
- `-tsapolicyid OID` gửi policy identifier cho TSA.
- `-tsadigestalg algorithm` chọn digest dùng cho message imprint của timestamp request.

Trong JDK 24, digest mặc định cho timestamp request là SHA-384. Digest này độc lập với `-digestalg` dùng cho entry của JAR.

Timestamp không làm cho chữ ký sai trở thành hợp lệ, không thay thế việc xác minh certificate chain và không chứng minh nội dung an toàn. Nó bổ sung bằng chứng về thời điểm chữ ký được tạo.

## 16. Thuật toán bị vô hiệu hóa và thuật toán legacy

JDK sử dụng security properties để kiểm soát thuật toán bị xem là không an toàn:

- `jdk.jar.disabledAlgorithms` liệt kê thuật toán không được chấp nhận khi xác minh JAR.
- `jdk.security.legacyAlgorithms` xác định thuật toán cũ có thể vẫn được chấp nhận kèm cảnh báo.

Nếu chữ ký dùng thuật toán đã bị vô hiệu hóa, JDK có thể coi JAR như chưa được ký. Nếu dùng thuật toán legacy, công cụ có thể đưa ra cảnh báo rằng thuật toán sẽ bị vô hiệu hóa trong bản cập nhật tương lai.

Các thuộc tính này nằm trong file `java.security` ở thư mục cấu hình bảo mật của JDK, thường là `$JAVA_HOME/conf/security/java.security`.

Không sửa security properties trên máy người dùng chỉ để cho một JAR cũ được xác minh. Hãy tạo lại chữ ký bằng thuật toán được chấp nhận và kiểm tra tương thích trên runtime mục tiêu.

Có thể bật chẩn đoán chi tiết:

~~~bash
jarsigner -J-Djava.security.debug=jar -verify app-signed.jar
~~~

Đọc cảnh báo và lỗi cùng phiên bản JDK đang dùng. Chính sách thuật toán có thể thay đổi theo JDK update và cấu hình của tổ chức.

## 17. Bảo vệ mật khẩu và private key

Mật khẩu keystore và private key không nên xuất hiện trong script công khai hoặc log CI.

`jarsigner` có thể yêu cầu nhập mật khẩu tương tác. Trong môi trường tự động, công cụ hỗ trợ lấy mật khẩu từ environment variable hoặc file bằng các dạng `-storepass:env`, `-storepass:file`, `-keypass:env` và `-keypass:file`.

Ví dụ:

~~~bash
jarsigner \
  -keystore release-signing.p12 \
  -storepass:env JAR_STORE_PASSWORD \
  -keypass:env JAR_KEY_PASSWORD \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  app.jar \
  releaseSigner
~~~

Đặt các biến trong secret manager của hệ thống CI và chỉ cấp cho job ký. Environment variable vẫn có thể bị lộ qua cấu hình hoặc process inspection; dùng HSM, smart card hoặc PKCS#11 token khi chính sách bảo mật yêu cầu.

Với provider PKCS#11 đã cấu hình, `jarsigner` có thể truy cập token bằng `-keystore NONE -storetype PKCS11`. Khi dùng hardware token, tuân thủ quy trình PIN và protected authentication path của thiết bị.

## 18. Ký JAR bằng nhiều signer

Một JAR có thể được ký nhiều lần bởi các signer khác nhau:

~~~bash
jarsigner app.jar releaseSignerA
jarsigner app.jar releaseSignerB
~~~

Mỗi signer tạo một cặp signature file và signature block riêng trong `META-INF`. Ví dụ:

~~~text
META-INF/
├── RELEASEA.SF
├── RELEASEA.RSA
├── RELEASEB.SF
└── RELEASEB.RSA
~~~

Điều này có thể dùng khi nhiều tổ chức hoặc người phát hành cần cùng ký một artifact. Mỗi chữ ký có thể được xác minh độc lập; cần kiểm tra signer nào được yêu cầu theo chính sách phân phối.

Nếu nội dung entry đã ký thay đổi, chữ ký tương ứng sẽ không còn xác minh được. Thực hiện mọi thay đổi trước khi tạo chữ ký cuối cùng.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `key algorithm not compatible with signature algorithm` | `-sigalg` không tương thích với private key của alias. | Chọn thuật toán phù hợp loại khóa hoặc tạo key pair đúng loại. |
| `keystore was tampered with, or password was incorrect` | Mật khẩu hoặc loại keystore không đúng. | Kiểm tra `-storepass`, `-storetype` và file keystore. |
| `key associated with alias not a private key` | Alias trỏ tới trusted certificate entry thay vì private key entry. | Dùng alias có `Entry type: PrivateKeyEntry`. |
| `digest error for ...` | Entry đã thay đổi sau khi ký hoặc file bị hỏng. | Tạo lại JAR từ artifact gốc và ký lại. |
| `jar is unsigned` | JAR chưa có signature block hợp lệ hoặc thuật toán bị vô hiệu hóa. | Kiểm tra `META-INF`, thuật toán và security properties của JDK. |
| `jar verified` nhưng có cảnh báo self-signed | Chữ ký và digest hợp lệ, nhưng certificate chain chưa được tin cậy. | Dùng chứng thư phát hành phù hợp hoặc truststore có trust anchor được quản lý. |
| Cảnh báo chữ ký không có timestamp | JAR chưa có timestamp token. | Dùng TSA qua `-tsa` hoặc `-tsacert` theo chính sách phát hành. |
| Thuật toán hoạt động trên JDK này nhưng lỗi trên JDK khác | Provider hoặc security policy giữa các phiên bản khác nhau. | Kiểm tra standard algorithm names, provider và `jdk.jar.disabledAlgorithms` trên từng runtime. |
| Không tìm thấy provider cho thuật toán | Provider không hỗ trợ hoặc chưa được cấu hình. | Kiểm tra provider, JDK distribution và tùy chọn `-addprovider`/`-providerClass` nếu cần. |
| JAR có entry mới nhưng entry đó chưa được ký | Entry được thêm sau khi ký. | Hoàn tất nội dung archive trước khi ký và kiểm tra unsigned entries khi verify. |

## 20. Quy trình ký và xác minh trong CI

Một pipeline phát hành có thể thực hiện:

~~~bash
# 1. Tạo artifact cuối cùng
jar --create --file build/app.jar -C build/classes .

# 2. Ký bằng key và thuật toán được phê duyệt
jarsigner \
  -keystore "$SIGNING_KEYSTORE" \
  -storepass:env JAR_STORE_PASSWORD \
  -keypass:env JAR_KEY_PASSWORD \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -tsa "$TSA_URL" \
  -signedjar build/app-signed.jar \
  build/app.jar \
  releaseSigner

# 3. Xác minh chữ ký và certificate chain
jarsigner -verify -strict -verbose:summary \
  -keystore "$TRUSTSTORE" \
  -storetype PKCS12 \
  -certs \
  build/app-signed.jar
~~~

Pipeline nên:

- Chỉ ký artifact sau khi mọi bước build và chỉnh sửa JAR hoàn tất.
- Lưu khóa riêng trong secret manager hoặc thiết bị ký được quản lý.
- Dùng thuật toán và key size được chính sách tổ chức chấp thuận.
- Cấu hình TSA nếu artifact cần bằng chứng thời điểm ký.
- Xác minh bằng JDK/runtime đại diện cho môi trường triển khai.
- Xử lý cảnh báo certificate chain, timestamp và legacy algorithm như một phần của review.
- Kiểm tra output để bảo đảm các entry mong đợi đều được ký.
- Lưu artifact đã ký và báo cáo xác minh cùng build revision.

Không nên chỉ kiểm tra exit code hoặc tìm chuỗi `jar verified`. Hãy đọc warning và xác nhận truststore, certificate chain, timestamp cùng các thuật toán thực tế.

## 21. Checklist trước khi phát hành

- Alias trong keystore trỏ tới `PrivateKeyEntry`.
- Keystore và private key được bảo vệ, không commit vào repository.
- Loại khóa tương thích với `-sigalg`.
- `-digestalg` được chọn theo chính sách bảo mật.
- Signature algorithm được provider và mọi runtime đích hỗ trợ.
- Đã hiểu mặc định của JDK và không phụ thuộc vào mặc định chưa kiểm chứng.
- Tất cả file/resource đã được đưa vào JAR trước khi ký.
- Manifest và signature files nằm trong `META-INF`.
- `jarsigner -verify` xác minh thành công.
- Đã kiểm tra certificate chain và trust anchor.
- Timestamp được tạo nếu quy trình phát hành yêu cầu.
- Không có thuật toán bị disabled hoặc legacy warning chưa được xử lý.
- Đã thử nghiệm rằng sửa một entry đã ký khiến xác minh thất bại.
- Artifact và báo cáo verify gắn với đúng source/build revision.

## 22. Tài liệu tham khảo

- [The jarsigner Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [JAR File Specification — Signed JAR File](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
- [Java Security Standard Algorithm Names — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/security/standard-names.html)
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161)

`-digestalg` kiểm soát digest của các entry JAR, còn `-sigalg` kiểm soát thuật toán ký file `.SF` bằng private key. Hãy chọn thuật toán tương thích với khóa và runtime đích, hiểu sự khác biệt giữa xác minh chữ ký và tin cậy chứng thư, rồi kiểm tra timestamp, security policy và tính toàn vẹn của artifact trước khi phát hành.
