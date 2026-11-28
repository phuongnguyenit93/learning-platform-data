# Chữ ký JAR với ML-DSA được hỗ trợ từ Java 26

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ML-DSA và vai trò của nó trong việc ký số JAR.
- Phân biệt hỗ trợ thuật toán ML-DSA trong JCA từ JDK 24 với tích hợp ký và xác minh JAR từ JDK 26.
- Tạo cặp khóa ML-DSA và certificate bằng keytool.
- Ký JAR bằng jarsigner với đúng signature algorithm và digest algorithm.
- Hiểu cấu trúc manifest, signature file và signature block của một JAR đã ký.
- Xác minh chữ ký, tính toàn vẹn nội dung và mức độ tin cậy của certificate.
- Kiểm tra khả năng tương thích giữa JDK, Provider, hệ thống build và nền tảng phân phối.
- Triển khai quản lý khóa, timestamp và chính sách mật mã phù hợp.

## 1. ML-DSA là gì?

ML-DSA (Module-Lattice-Based Digital Signature Algorithm) là thuật toán chữ ký số hậu lượng tử được chuẩn hóa trong NIST FIPS 204. Thuật toán được thiết kế để bảo vệ chữ ký trước các tấn công cổ điển và các máy tính lượng tử có khả năng phá vỡ những giả định mật mã khóa công khai truyền thống.

ML-DSA dùng để **ký và xác minh chữ ký**, không phải thuật toán mã hóa dữ liệu. Trong quy trình ký JAR:

- Người phát hành dùng private key ML-DSA để tạo chữ ký.
- JAR chứa chữ ký cùng certificate hoặc certificate chain tương ứng.
- Người nhận dùng public key trong certificate để xác minh chữ ký.
- Các digest trong manifest được kiểm tra để phát hiện nội dung JAR đã bị sửa sau khi ký.

ML-DSA có ba parameter set:

| Parameter set | Tiêu chuẩn | Ý nghĩa |
|---|---|---|
| ML-DSA-44 | FIPS 204 | Mức bảo mật thấp hơn trong ba lựa chọn, chữ ký và khóa gọn hơn |
| ML-DSA-65 | FIPS 204 | Lựa chọn trung gian, được SUN Provider dùng làm mặc định khi không chỉ định parameter set |
| ML-DSA-87 | FIPS 204 | Mức bảo mật cao nhất trong ba lựa chọn, dữ liệu khóa/chữ ký lớn hơn |

Không nên chọn parameter set chỉ theo tên hoặc giả định mức cao nhất luôn phù hợp. Cần tuân theo chính sách mật mã, yêu cầu chứng nhận, hiệu năng, kích thước artifact và khả năng tương thích của hệ sinh thái phát hành.

ML-DSA trước khi được chuẩn hóa từng được gọi là Dilithium. Các bản triển khai dựa trên draft Dilithium cũ không mặc nhiên tương thích với ML-DSA theo FIPS 204. Khi tích hợp thư viện hoặc HSM, phải xác nhận implementation hỗ trợ đúng chuẩn ML-DSA hiện hành.

## 2. Phân biệt JDK 24 và JDK 26

Cần phân biệt hỗ trợ primitive mật mã với hỗ trợ định dạng chữ ký JAR:

| Phiên bản | Hỗ trợ |
|---|---|
| JDK 24 | JEP 497 bổ sung triển khai ML-DSA trong Java Cryptography Architecture: tạo khóa, ký và xác minh dữ liệu bằng các API bảo mật |
| JDK 26 | Bổ sung khả năng tạo và xác minh JAR được ký bằng ML-DSA thông qua jarsigner và JarSigner API, dùng PKCS #7/CMS theo RFC 9882 |

Vì vậy, việc JDK 24 đã có Signature algorithm ML-DSA không có nghĩa jarsigner của JDK 24 đã hỗ trợ cấu trúc CMS cần thiết để ký JAR bằng ML-DSA.

Tính năng ký JAR ML-DSA được đưa vào JDK 26 theo thay đổi JDK-8349732. Oracle JDK 26 hỗ trợ cả hai chiều: ký JAR và xác minh JAR đã ký ML-DSA.

Đây là tính năng Java SE/JDK ổn định, không phải preview hoặc incubator. Không cần bật --enable-preview hay thêm module incubator.

## 3. JAR dùng cấu trúc chữ ký nào?

JAR là định dạng ZIP có thể chứa thư mục META-INF. Khi jarsigner ký toàn bộ JAR, công cụ cập nhật manifest và thêm các tệp chữ ký vào META-INF.

Một JAR đã ký thường có các thành phần:

~~~text
application-signed.jar
|
+-- META-INF/
|   +-- MANIFEST.MF
|   +-- SIGNER.SF
|   +-- SIGNER.DSA
|
+-- com/example/Main.class
+-- application.properties
+-- ...
~~~

Vai trò của từng tệp:

- **MANIFEST.MF:** chứa digest của các entry được ký trong JAR.
- **SIGNER.SF:** chứa digest của manifest hoặc các section tương ứng, qua đó ràng buộc nội dung JAR với chữ ký.
- **SIGNER.DSA:** signature block chứa chữ ký CMS/PKCS #7 của tệp .SF và certificate hoặc certificate chain của signer.

Với khóa ML-DSA, JDK 26 mặc định dùng đuôi .DSA cho signature block. Đây là quy ước tên file của định dạng JAR; nó không có nghĩa chữ ký bên trong sử dụng thuật toán DSA cổ điển. Thuật toán thật được nhận diện từ AlgorithmIdentifier/OID trong CMS SignedData.

JAR specification đã dành các phần mở rộng .DSA, .RSA và .EC cho signature block. Vì vậy, không đổi tên .DSA thành một đuôi tự đặt như .MLDSA; công cụ xác minh JAR cần nhận diện các tệp chữ ký theo quy ước chuẩn.

## 4. Chữ ký JAR được tạo và xác minh ra sao?

Quy trình ký gồm các bước chính:

1. jarsigner đọc từng entry của JAR và tính digest.
2. Digest được ghi vào các section trong MANIFEST.MF.
3. Công cụ tạo signature file .SF, chứa digest của manifest và các section liên quan.
4. ML-DSA ký nội dung signature file theo cấu trúc CMS.
5. Signature block được ghi vào META-INF cùng certificate hoặc certificate chain.

Quy trình xác minh thực hiện ngược lại:

1. Xác minh chữ ký ML-DSA trong signature block đối với tệp .SF.
2. Kiểm tra digest trong .SF với manifest.
3. Tính lại digest của từng entry và so sánh với giá trị trong manifest.
4. Kiểm tra certificate chain và các điều kiện bảo mật nếu được cấu hình.

Nếu một entry đã ký bị thay đổi, digest không còn khớp và xác minh thất bại. Nếu một entry được thêm sau khi ký, entry đó có thể không được chữ ký ban đầu bảo vệ; jarsigner có thể cảnh báo JAR chứa unsigned entry.

Chữ ký JAR không mã hóa nội dung. Người nhận vẫn có thể đọc các file trong JAR; chữ ký cung cấp bằng chứng về tính toàn vẹn và nguồn ký theo certificate được tin cậy.

## 5. Tạo khóa ML-DSA bằng keytool

JDK 26 cung cấp ML-DSA qua SUN Provider. Có thể tạo key pair và lưu private key cùng certificate trong keystore PKCS12.

Ví dụ tạo khóa ML-DSA-65:

~~~bash
keytool -genkeypair -alias signer -keyalg ML-DSA -groupname ML-DSA-65 -sigalg ML-DSA -dname "CN=Example Code Signing" -validity 365 -keystore signer.p12 -storetype PKCS12
~~~

Ý nghĩa:

- -genkeypair: tạo public key và private key.
- -alias signer: tên entry trong keystore.
- -keyalg ML-DSA: chọn họ thuật toán ML-DSA.
- -groupname ML-DSA-65: chọn parameter set cụ thể.
- -sigalg ML-DSA: dùng ML-DSA để ký certificate tự ký được tạo bởi keytool.
- -dname: thông tin subject của certificate.
- -validity 365: thời hạn certificate tính theo ngày.
- -keystore signer.p12: file keystore.
- -storetype PKCS12: dùng định dạng keystore PKCS12.

keytool sẽ yêu cầu password nếu chưa được cung cấp. Trong môi trường thật, không ghi password trực tiếp trên command line hoặc trong script; dùng prompt, cơ chế secret được bảo vệ hoặc token/HSM theo chính sách vận hành.

Certificate tự ký trong ví dụ chỉ phù hợp cho thử nghiệm. Production cần certificate do CA hoặc hệ thống PKI của tổ chức cấp, với subject, key usage, extended key usage và chain đáp ứng chính sách code signing của nền tảng phát hành.

### Chọn parameter set khác

Có thể thay giá trị groupname bằng một trong các tên:

~~~text
ML-DSA-44
ML-DSA-65
ML-DSA-87
~~~

Không dùng -keysize để thay thế parameter set nếu thuật toán yêu cầu named parameters. keytool dùng -groupname để truyền NamedParameterSpec tương ứng.

Có thể xem entry sau khi tạo:

~~~bash
keytool -list -v -keystore signer.p12 -storetype PKCS12 -alias signer
~~~

Kiểm tra thuật toán khóa, certificate, thời hạn và fingerprint. Bảo vệ file keystore và giới hạn quyền truy cập private key.

## 6. Ký JAR bằng jarsigner

Giả sử có file application.jar và keystore signer.p12 chứa private key ML-DSA-65 ở alias signer.

~~~bash
jarsigner -keystore signer.p12 -storetype PKCS12 -sigalg ML-DSA -digestalg SHA-384 -signedjar application-signed.jar application.jar signer
~~~

jarsigner sẽ yêu cầu password keystore/private key nếu cần. Không đặt password thật trong script build hoặc lịch sử command.

Các tùy chọn quan trọng:

| Tùy chọn | Vai trò |
|---|---|
| -keystore | Keystore chứa private key và certificate chain |
| -storetype | Loại keystore, ví dụ PKCS12 |
| -sigalg ML-DSA | Chọn thuật toán chữ ký ML-DSA |
| -digestalg SHA-384 | Chọn digest dùng cho các entry JAR |
| -signedjar | Đặt tên JAR đầu ra đã ký |
| -tsa | URL của dịch vụ timestamp RFC 3161 |
| -sigfile | Chọn tên gốc cho .SF và signature block |

Với khóa ML-DSA, jarsigner mặc định chọn signature algorithm ML-DSA. Có thể chỉ định -sigalg ML-DSA tường minh để cấu hình build dễ đọc và dễ kiểm tra.

ML-DSA-44, ML-DSA-65 và ML-DSA-87 là parameter set của khóa; signature algorithm name được dùng trong jarsigner là ML-DSA. Parameter set thực tế được xác định bởi khóa được chọn.

### Phân biệt -sigalg và -digestalg

Hai tùy chọn có vai trò khác nhau:

- -sigalg chọn thuật toán tạo chữ ký cho signature file.
- -digestalg chọn thuật toán digest để tính hash các entry của JAR.

Với ML-DSA-65, SHA-384 là lựa chọn được RFC 9882 cho phép trong CMS khi sử dụng signed attributes. JDK 26 cũng dùng SHA-384 làm digest algorithm mặc định cho jarsigner nếu không chỉ định.

Nếu dùng ML-DSA-87, cần chú ý yêu cầu digestAlgorithm trong CMS theo RFC 9882: với signed attributes, digest phù hợp gồm SHA-512, SHA3-512 hoặc SHAKE256. Hãy chọn cấu hình tương thích, ví dụ SHA-512 nếu digest option của công cụ được dùng cho trường CMS tương ứng, và xác minh artifact bằng implementation độc lập. Không suy ra rằng mọi digest mặc định đều phù hợp với mọi parameter set chỉ vì lệnh ký thành công.

## 7. Xác minh JAR đã ký ML-DSA

Dùng jarsigner với -verify:

~~~bash
jarsigner -verify -verbose -certs application-signed.jar
~~~

Các tùy chọn:

- -verify: xác minh chữ ký và digest của các entry.
- -verbose: hiển thị tiến trình kiểm tra.
- -certs: hiển thị thông tin certificate của signer.

Khi chữ ký hợp lệ, jarsigner hiển thị thông báo xác minh thành công. Tuy nhiên, kết quả này cần được đọc cùng các cảnh báo về certificate, unsigned entry, thuật toán bị vô hiệu hóa hoặc certificate chain không được tin cậy.

Có thể dùng -strict để biến các severe warnings thành trạng thái lỗi của command:

~~~bash
jarsigner -verify -strict -verbose -certs application-signed.jar
~~~

Trong CI/CD, -strict giúp phát hiện các vấn đề certificate hoặc JAR mà một lần verify thông thường có thể chỉ hiển thị dưới dạng warning. Chữ ký và digest được kiểm tra bằng dữ liệu trong JAR; jarsigner cũng cố gắng xác thực certificate của signer và báo warning nếu chain có vấn đề.

**Lưu ý về -keystore khi xác minh:** tùy chọn này không phải một tham số chọn trust store tùy ý. Khi verify, jarsigner có thể kiểm tra keystore được chỉ định để xem certificate signer có khớp alias nào không và hiển thị alias đó. Việc đối chiếu alias không tự biến một certificate thành trust anchor. Trust anchor và chính sách PKIX phải được cấu hình trong môi trường xác minh mà hệ thống sử dụng, chẳng hạn kho CA được tin cậy của JDK; nếu ứng dụng cần trust policy riêng, hãy thực hiện kiểm tra certificate path bằng CertPathValidator với TrustAnchor được quản lý riêng.

Nếu cần kiểm tra trạng thái thu hồi, tùy chọn -revCheck yêu cầu jarsigner truy cập OCSP/CRL theo certificate chain. Kiểm tra thu hồi không được bật mặc định; cần cân nhắc network access, độ sẵn sàng của dịch vụ và chính sách fail-open/fail-closed.

### Xác minh certificate và danh tính signer

Chữ ký ML-DSA hợp lệ không tự chứng minh signer là tổ chức mà người nhận mong đợi. Cần kiểm tra:

- Certificate có được cấp bởi CA hoặc trust anchor được chấp nhận không.
- Certificate chain có hợp lệ và còn hiệu lực không.
- KeyUsage và ExtendedKeyUsage có cho phép mục đích code signing không.
- Certificate có bị thu hồi hay không theo chính sách kiểm tra.
- Fingerprint, subject, issuer và key ID có khớp danh tính signer đã đăng ký không.

Một certificate tự ký có thể xác minh chữ ký về mặt toán học nhưng không tự tạo ra niềm tin. Với PKI thông thường, hãy cài đặt root CA certificate đã xác minh fingerprint vào trust store được runtime xác minh sử dụng. Chỉ pin trực tiếp certificate signer như trust anchor khi hệ thống chủ đích dùng mô hình certificate pinning và có quy trình thay khóa/thu hồi rõ ràng.

Trong môi trường lab, certificate tự ký thường tạo severe warning signerSelfSigned; vì vậy lệnh verify với -strict có thể trả mã lỗi dù phép kiểm tra chữ ký toán học thành công. Đây là kết quả mong đợi khi certificate chưa được tin cậy, không phải lý do để tắt -strict trong pipeline production.

## 8. Timestamp cho chữ ký JAR

Certificate ký code có thể hết hạn. Nếu JAR được ký mà không có timestamp, người dùng có thể gặp khó khăn khi xác minh sau khi certificate hết hạn hoặc sau khi chính sách thu hồi thay đổi.

jarsigner hỗ trợ timestamp bằng dịch vụ TSA theo RFC 3161:

~~~bash
jarsigner -keystore signer.p12 -storetype PKCS12 -sigalg ML-DSA -digestalg SHA-384 -tsa https://tsa.example.org -signedjar application-signed.jar application.jar signer
~~~

URL chỉ là ví dụ; phải thay bằng TSA được tổ chức tin cậy và hỗ trợ. Timestamp token được lưu trong signature block.

Thuật toán và certificate của TSA là một phần riêng của quy trình timestamp. Không giả định TSA phải dùng ML-DSA chỉ vì JAR signer sử dụng ML-DSA. Cần kiểm tra thuật toán, certificate chain và khả năng tương thích của TSA với client xác minh.

Timestamp không thay thế việc kiểm tra certificate chain hoặc chính sách thu hồi. Nó cung cấp bằng chứng thời điểm chữ ký được đóng dấu theo trust model của TSA.

## 9. Định dạng CMS và RFC 9882

JDK 26 dùng Cryptographic Message Syntax (CMS), còn được gọi là PKCS #7 trong ngữ cảnh JAR signature block, để lưu chữ ký ML-DSA. RFC 9882 quy định cách dùng ML-DSA trong CMS SignedData.

RFC 9882 định nghĩa các AlgorithmIdentifier cho ba parameter set:

| Parameter set | OID |
|---|---|
| ML-DSA-44 | 2.16.840.1.101.3.4.3.17 |
| ML-DSA-65 | 2.16.840.1.101.3.4.3.18 |
| ML-DSA-87 | 2.16.840.1.101.3.4.3.19 |

Các OID này giúp verifier nhận biết chính xác parameter set được dùng để tạo chữ ký. Không dùng phần mở rộng .DSA của file để suy ra OID hoặc parameter set.

RFC 9882 quy định ML-DSA trong CMS sử dụng pure mode, không phải HashML-DSA pre-hash mode. Khi signed attributes hiện diện, chữ ký được tính trên DER encoding của SignedAttrs; message-digest attribute chứa digest của nội dung SignedData.

Digest algorithm trong CMS phải phù hợp với parameter set nếu signed attributes được dùng:

| Parameter set | Digest phù hợp theo RFC 9882 |
|---|---|
| ML-DSA-44 | SHA-256, SHA-384, SHA-512, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 |
| ML-DSA-65 | SHA-384, SHA-512, SHA3-384, SHA3-512, SHAKE256 |
| ML-DSA-87 | SHA-512, SHA3-512, SHAKE256 |

SHA-512 là lựa chọn có khả năng tương thích rộng theo RFC 9882. Khi xây dựng quy trình ký cho nhiều hệ thống, cần kiểm tra CMS SignedData thực tế và chạy xác minh bằng các implementation mà người nhận sử dụng.

## 10. Khả năng tương thích giữa JDK và hệ sinh thái

JDK 26 bổ sung hỗ trợ ký và xác minh JAR bằng ML-DSA. Điều này không có nghĩa mọi runtime Java, công cụ build hoặc nền tảng triển khai đều hỗ trợ ngay lập tức.

Cần kiểm tra:

- Runtime Java dùng để xác minh JAR có hỗ trợ ML-DSA trong CMS/RFC 9882 không.
- Công cụ build có gọi jarsigner của JDK 26 hoặc mới hơn không.
- Hệ thống triển khai có đọc signature block .DSA và nhận diện OID ML-DSA không.
- Certificate chain có dùng thuật toán và profile được verifier chấp nhận không.
- HSM/PKCS#11 token có hỗ trợ tạo chữ ký ML-DSA và Provider có tích hợp được với jarsigner không.
- Công cụ kiểm tra supply chain, antivirus, repository scanner và package manager có hỗ trợ chữ ký mới không.

Các JDK trước 26 có thể đã hỗ trợ primitive ML-DSA nhưng không thể mặc định rằng jarsigner của chúng xác minh được JAR ký ML-DSA. Cần kiểm tra chính xác phiên bản verifier.

Nếu thư viện hoặc pipeline đang dùng implementation Dilithium draft, không giả định chữ ký tương thích với ML-DSA theo FIPS 204/RFC 9882. Cần nâng cấp và kiểm thử bằng test vector chuẩn.

### Khác biệt định dạng private key giữa JDK 26 và JDK 27

JDK 27 thay đổi mặc định encoding PKCS#8 của private key ML-DSA sang dạng seed. JDK cũ có thể không đọc được key mới tạo theo mặc định. Nếu keystore ML-DSA cần dùng chung giữa JDK 26 và JDK 27, phải xác nhận encoding private key và cấu hình tương thích theo tài liệu của JDK mục tiêu.

Không nên chuyển file keystore qua các JDK khác nhau mà không thử load, ký và xác minh trên từng môi trường. Có thể cần xuất/nhập lại hoặc chuyển đổi key bằng KeyFactory theo chính sách bảo mật của tổ chức.

## 11. Khả năng hỗ trợ Provider và HSM

Oracle JDK 26 cung cấp ML-DSA trong SUN Provider, bao gồm KeyPairGenerator, KeyFactory và Signature với ML-DSA-44, ML-DSA-65, ML-DSA-87. PKCS12 KeyStore được hỗ trợ để lưu trữ key entry.

Với HSM hoặc token PKCS#11:

- Xác nhận thiết bị và firmware hỗ trợ ML-DSA parameter set cần dùng.
- Xác nhận PKCS#11 mechanism tương ứng được Provider công bố.
- Xác nhận certificate chain và private key entry được keytool/jarsigner truy cập đúng.
- Kiểm thử ký JAR và xác minh JAR trên đúng môi trường HSM.
- Không giả định mọi Provider có hỗ trợ ML-DSA đều hỗ trợ ký CMS/JAR qua jarsigner.

Ứng dụng phổ thông nên để JCA chọn Provider phù hợp theo thứ tự ưu tiên. Chỉ chỉ định Provider cụ thể khi có yêu cầu vận hành, chứng nhận hoặc tích hợp HSM rõ ràng.

Nếu dùng PKCS#11 token, jarsigner có thể truy cập keystore qua cấu hình SunPKCS11, ví dụ dùng -keystore NONE -storetype PKCS11 cùng Provider đã cấu hình. Cấu hình cụ thể phụ thuộc token và thư viện PKCS#11.

## 12. Quản lý khóa ký và certificate

Private key ML-DSA là tài sản bảo mật của tổ chức. Nếu private key bị lộ, kẻ tấn công có thể tạo JAR giả mạo hợp lệ về mặt chữ ký.

Các nguyên tắc vận hành:

- Giữ private key trong HSM, token hoặc kho khóa được bảo vệ nếu môi trường yêu cầu.
- Hạn chế quyền truy cập alias và thao tác ký.
- Tách khóa ký production khỏi khóa demo, test và developer workstation.
- Không commit keystore, private key hoặc password vào source repository.
- Ghi audit log cho hoạt động ký, người thực hiện, artifact digest và certificate serial.
- Có quy trình xoay vòng, thu hồi và thay thế certificate.
- Giữ lại artifact đã ký, certificate chain và timestamp để phục vụ kiểm tra về sau.
- Bảo vệ quy trình build và signing pipeline khỏi việc thay artifact sau khi đã được duyệt.

ML-DSA không loại bỏ nhu cầu quản lý certificate, trust anchor, timestamp, code signing policy hoặc bảo vệ private key. Thuật toán mạnh không bù đắp được private key bị đánh cắp hoặc pipeline phát hành bị xâm nhập.

## 13. Chính sách thuật toán khi xác minh

jarsigner sử dụng các security properties để đánh giá thuật toán ký:

- jdk.jar.disabledAlgorithms: thuật toán bị vô hiệu hóa; JAR sử dụng thuật toán bị disable được xử lý như JAR chưa ký.
- jdk.security.legacyAlgorithms: thuật toán bị coi là legacy; jarsigner có thể hiển thị informational warning.

Các property nằm trong file java.security của JDK. Không xóa thuật toán khỏi danh sách disabled chỉ để làm một JAR cũ được chấp nhận. Hãy đánh giá lại chữ ký, nâng cấp signer và tạo artifact mới bằng thuật toán còn được chính sách hiện hành cho phép.

ML-DSA là lựa chọn chữ ký hậu lượng tử được chuẩn hóa, nhưng chính sách cuối cùng vẫn phụ thuộc tiêu chuẩn tổ chức, cơ quan quản lý và hệ sinh thái verifier.

## 14. Phân biệt ký JAR với các cơ chế bảo mật khác

| Cơ chế | Mục tiêu |
|---|---|
| ML-DSA JAR signing | Xác minh tính toàn vẹn và nguồn ký của artifact theo certificate |
| TLS | Bảo vệ kênh truyền giữa các endpoint |
| HPKE | Mã hóa và xác thực thông điệp theo mode HPKE |
| Hash/checksum không có chữ ký | Phát hiện thay đổi nếu giá trị tham chiếu đến từ nguồn đáng tin cậy |
| JAR signing với RSA/ECDSA | Chữ ký JAR dựa trên thuật toán cổ điển |

ML-DSA không tự mã hóa JAR, không thay TLS và không tự xác thực người tải file. Chữ ký chỉ có ý nghĩa xác thực danh tính nếu certificate chain và trust policy được người nhận kiểm tra.

Có thể triển khai song song nhiều signer trong một JAR để chuyển đổi hệ sinh thái, nhưng cần đánh giá quy tắc verifier: hệ thống có chấp nhận một trong nhiều chữ ký hay yêu cầu mọi chữ ký đều hợp lệ? Không giả định việc thêm chữ ký thứ hai tự động làm mọi nền tảng cũ và mới tương thích.

## 15. Kiểm thử và tích hợp CI/CD

Pipeline ký JAR nên có các bước:

1. Build artifact từ source và dependency đã khóa phiên bản.
2. Tính digest của artifact trước khi ký để lưu audit.
3. Lấy private key ML-DSA từ keystore/HSM theo quyền đã cấp.
4. Ký JAR bằng JDK 26 trở lên.
5. Xác minh chữ ký ngay sau khi ký.
6. Kiểm tra certificate chain, key usage, timestamp và cảnh báo.
7. Kiểm tra artifact đã ký không bị thay đổi trong bước upload/repository publish.
8. Xác minh lại sau khi tải artifact từ repository hoặc mirror.
9. Chạy compatibility test với runtime và công cụ của người nhận.

Ví dụ các lệnh kiểm tra:

~~~bash
jarsigner -verify -verbose -certs application-signed.jar
jarsigner -verify -strict -verbose -certs application-signed.jar
keytool -list -v -keystore signer.p12 -storetype PKCS12 -alias signer
~~~

Nếu muốn kiểm tra signer có khớp một alias đã biết trong keystore hay không, có thể chỉ định keystore và alias:

~~~bash
jarsigner -verify -verbose -certs -keystore signer-registry.p12 application-signed.jar signer
~~~

Keystore trong lệnh này phục vụ đối chiếu alias của signer; không coi nó là tùy chọn trust store tổng quát để thay thế cấu hình trust anchor của runtime.

Test nên bao gồm:

- JAR chưa bị thay đổi.
- Một entry bị sửa sau khi ký.
- Một entry được thêm sau khi ký.
- Certificate hết hạn hoặc không được trust.
- Signature block bị xóa hoặc thay đổi.
- JAR được xác minh bằng JDK 26 và các runtime mục tiêu.
- Certificate chain có thuật toán được hệ thống PKI hỗ trợ.
- Digest và signature algorithm tuân thủ profile đã phê duyệt.

Không chỉ kiểm tra command trả về mã 0. Đọc warning và dùng -strict trong release gate để phát hiện các vấn đề nghiêm trọng.

## 16. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| NoSuchAlgorithmException khi ký ML-DSA | Runtime hoặc Provider không hỗ trợ ML-DSA | Dùng JDK/Provider có hỗ trợ và kiểm tra tên thuật toán |
| InvalidKeyException | Private key không phải ML-DSA hoặc Provider không chấp nhận key | Kiểm tra alias, thuật toán key và parameter set |
| Lỗi đọc keystore | Keystore type/password/PKCS#8 encoding không tương thích | Kiểm tra PKCS12, JDK tạo key và định dạng private key |
| jarsigner không xác minh được signature block | Runtime cũ hoặc CMS implementation không hỗ trợ RFC 9882 | Dùng JDK 26+ và kiểm tra interoperability |
| JAR verified nhưng certificate warning | Chữ ký hợp lệ nhưng chain không được trust hoặc certificate có vấn đề | Kiểm tra trust store, chain, thời hạn và key usage |
| Unsigned entry warning | Entry được thêm sau khi ký hoặc không nằm trong vùng được ký | Ký lại artifact hoàn chỉnh |
| Disabled algorithm warning/error | Chính sách JDK từ chối thuật toán | Dùng thuật toán hiện hành và không bypass security property |
| TSA failure | TSA không truy cập được hoặc certificate/algorithm không tương thích | Kiểm tra URL, trust chain, digest và timestamp response |

## 17. Trạng thái tính năng trong Java 26

| Thành phần | Trạng thái |
|---|---|
| ML-DSA JCA primitive | Có từ JDK 24 theo JEP 497 |
| ML-DSA-44, ML-DSA-65, ML-DSA-87 | Được SUN Provider hỗ trợ trong JDK 26 |
| ML-DSA key generation qua keytool | Được hỗ trợ |
| Ký JAR ML-DSA qua jarsigner | Được hỗ trợ từ JDK 26 |
| Xác minh JAR ML-DSA | Được hỗ trợ từ JDK 26 |
| JarSigner API | Hỗ trợ ML-DSA từ JDK 26 |
| CMS/PKCS #7 encoding | Theo RFC 9882 |
| Preview/incubator | Không phải preview hoặc incubator |

JarSigner API nằm trong module jdk.jartool, package jdk.security.jarsigner. Ứng dụng module hóa tham chiếu API này cần khai báo:

~~~java
module com.example.signing {
    requires jdk.jartool;
}
~~~

Nếu chỉ gọi command-line jarsigner trong pipeline, không cần thêm module vào source ứng dụng.

## 18. Checklist triển khai

- [ ] Build và ký bằng JDK 26 trở lên có hỗ trợ ML-DSA JAR.
- [ ] Xác định parameter set ML-DSA-44/65/87 theo chính sách.
- [ ] Private key được tạo và lưu trong keystore hoặc HSM an toàn.
- [ ] Certificate chain được cấp và tin cậy bởi hệ thống nhận artifact.
- [ ] jarsigner dùng signature algorithm ML-DSA tương thích với key.
- [ ] Digest algorithm tuân theo profile CMS/RFC 9882 và parameter set.
- [ ] Signature block được tạo trong META-INF và không đổi tên phần mở rộng .DSA.
- [ ] JAR được verify bằng JDK 26 và runtime mục tiêu.
- [ ] Kiểm tra trust chain, key usage, expiry, revocation và timestamp.
- [ ] Không để password hoặc private key trong source/build log.
- [ ] HSM/Provider đã được kiểm tra thực tế nếu dùng khóa phần cứng.
- [ ] Có kiểm thử phát hiện unsigned entry và nội dung bị sửa.
- [ ] Pipeline giữ nguyên artifact sau khi ký và xác minh lại sau publish.
- [ ] Có kế hoạch tương thích key encoding khi trao đổi keystore giữa JDK 26 và JDK 27.

## Kết luận

Java 26 bổ sung khả năng ký và xác minh JAR bằng ML-DSA theo CMS/PKCS #7 RFC 9882 thông qua jarsigner và JarSigner API. JDK 24 đã cung cấp primitive ML-DSA trong JCA, nhưng JDK 26 mới tích hợp thuật toán hậu lượng tử này vào quy trình ký JAR. Có thể tạo khóa bằng keytool với ML-DSA-44, ML-DSA-65 hoặc ML-DSA-87, sau đó dùng jarsigner với signature algorithm ML-DSA. Signature block mặc định có đuôi .DSA theo quy ước JAR, dù chữ ký bên trong là ML-DSA. Để triển khai an toàn, phải xác minh digest/CMS profile, certificate chain, trust, timestamp, Provider, runtime nhận JAR và bảo vệ private key; chữ ký hợp lệ không tự chứng minh danh tính nếu certificate chưa được tin cậy.

## Tài liệu tham khảo

- [JDK 26 Release Notes – Signed JAR Support for ML-DSA (JDK-8349732)](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 26 jarsigner Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [JDK 26 keytool Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [Java Security Standard Algorithm Names – ML-DSA](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html)
- [JDK 26 Providers Documentation – SUN Provider](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html)
- [Java SE 26 API – JarSigner](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jartool/jdk/security/jarsigner/JarSigner.html)
- [Java SE 26 API – JarSigner.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jartool/jdk/security/jarsigner/JarSigner.Builder.html)
- [JEP 497 – Quantum-Resistant Module-Lattice-Based Digital Signature Algorithm](https://openjdk.org/jeps/497)
- [RFC 9882 – Use of the ML-DSA Signature Algorithm in the Cryptographic Message Syntax (CMS)](https://www.rfc-editor.org/rfc/rfc9882.html)
- [NIST FIPS 204 – Module-Lattice-Based Digital Signature Standard](https://csrc.nist.gov/pubs/fips/204/final)
