# Lệnh jarsigner trong Java

**`jarsigner`** là công cụ của JDK dùng để ký số và xác minh chữ ký số của tệp JAR. Khi ký, công cụ dùng private key trong keystore để tạo chữ ký cho nội dung archive và ghi metadata chữ ký vào thư mục `META-INF`. Khi xác minh, công cụ kiểm tra digest của các entry, chữ ký và certificate của người ký.

JAR signing giúp phát hiện nội dung đã bị thay đổi sau khi ký và gắn chữ ký với danh tính được thể hiện trong certificate. Chữ ký không mã hóa nội dung JAR, không tự động làm certificate được tin cậy và không thay thế kiểm tra bảo mật của ứng dụng.

## 1. JAR signing dùng để làm gì?

Khi phân phối thư viện hoặc ứng dụng Java, người nhận cần biết artifact có còn nguyên vẹn và được ký bởi danh tính mong đợi hay không.

JAR signing hỗ trợ:

- **Integrity:** phát hiện nội dung đã ký bị thay đổi sau thời điểm ký.
- **Signer identity:** xác định certificate và public key gắn với chữ ký.
- **Tamper detection:** phát hiện entry có digest không còn khớp.
- **Release verification:** kiểm tra artifact trước khi triển khai hoặc phân phối.
- **Multiple signers:** cho phép nhiều bên ký cùng một JAR theo quy trình phát hành.

Một JAR đã ký vẫn có thể chứa mã độc hoặc lỗi. Chữ ký cho biết nội dung phù hợp với chữ ký của private key tương ứng; việc tin cậy người ký còn phụ thuộc certificate chain, chính sách trust và quy trình cấp phát khóa.

## 2. Cơ chế chữ ký trong JAR

Khi ký JAR, `jarsigner` cập nhật hoặc tạo các tệp metadata trong `META-INF`. Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `META-INF/MANIFEST.MF` | Chứa digest của các entry trong JAR |
| `META-INF/<SIGNER>.SF` | Chứa digest của manifest hoặc các section manifest |
| `META-INF/<SIGNER>.RSA`, `.DSA` hoặc `.EC` | Signature block chứa chữ ký số và thông tin certificate tương ứng |

Tên file signature được tạo từ signer name hoặc tùy chọn `-sigfile`; phần mở rộng của signature block phụ thuộc thuật toán khóa.

Quy trình ở mức khái niệm:

1. Jarsigner tính digest cho nội dung từng entry cần ký.
2. Digest được ghi vào manifest.
3. Công cụ tạo signature file `.SF` chứa digest của manifest hoặc các section.
4. Private key ký signature file.
5. Chữ ký và certificate chain được lưu trong signature block.
6. Khi xác minh, công cụ tính lại digest và kiểm tra chữ ký bằng public key trong certificate.

Nếu nội dung entry đã ký bị thay đổi, digest không khớp và xác minh sẽ báo lỗi. Nếu thêm entry mới sau khi ký, entry đó không tự được bảo vệ bởi chữ ký cũ; người xác minh có thể thấy entry chưa được ký. Vì vậy, hãy ký sau khi đã hoàn tất mọi thay đổi đối với JAR.

## 3. Chuẩn bị keystore và key pair

Jarsigner cần private key để ký. Khóa thường được lưu trong keystore cùng certificate.

Với JDK hiện đại, PKCS12 là lựa chọn phù hợp cho keystore mới. Ví dụ tạo key pair RSA dành cho thử nghiệm:

```bash
keytool -genkeypair -alias release-key -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore release-signing.p12 -dname "CN=Example Test Signer, OU=Engineering, O=Example Org, C=VN"
```

Ý nghĩa:

- `-genkeypair`: tạo private key và public key.
- `-alias release-key`: tên entry trong keystore.
- `-keyalg RSA`: dùng thuật toán RSA.
- `-keysize 3072`: kích thước khóa RSA 3072 bit.
- `-sigalg SHA256withRSA`: thuật toán chữ ký certificate.
- `-validity 365`: thời hạn certificate tự ký là 365 ngày.
- `-storetype PKCS12`: định dạng keystore.
- `-keystore release-signing.p12`: tệp keystore đầu ra.
- `-dname`: Distinguished Name của subject trong certificate.

Keytool sẽ yêu cầu nhập và xác nhận mật khẩu. Hãy nhập tương tác thay vì ghi mật khẩu trực tiếp vào dòng lệnh, script hoặc lịch sử shell. Với PKCS12, mật khẩu bảo vệ private key thường dùng cùng mật khẩu keystore.

Certificate tự ký trong ví dụ phù hợp cho học tập và thử nghiệm. Đối với phát hành thật, dùng certificate ký mã phù hợp với quy trình tổ chức hoặc CA được bên nhận tin cậy. Không dùng certificate thử nghiệm làm danh tính phát hành production.

Kiểm tra entry:

```bash
keytool -list -v -alias release-key -keystore release-signing.p12 -storetype PKCS12
```

Xác nhận entry type là `PrivateKeyEntry`, thuật toán khóa đúng và certificate là certificate gắn với alias dự kiến.

## 4. Cú pháp cơ bản của jarsigner

Cú pháp ký:

```text
jarsigner [options] jar-file alias
```

Cú pháp xác minh:

```text
jarsigner -verify [options] jar-file [alias...]
```

Các tham số:

- `jar-file`: JAR cần ký hoặc xác minh.
- `alias`: alias của entry chứa private key và certificate trong keystore.
- `options`: keystore, thuật toán digest/chữ ký, timestamp và tùy chọn đầu ra.

Xem trợ giúp trên JDK đang sử dụng:

```bash
jarsigner -help
jarsigner -version
```

Một số tùy chọn thường dùng:

| Tùy chọn | Công dụng |
| --- | --- |
| `-keystore <url>` | Vị trí keystore |
| `-storetype <type>` | Loại keystore, ví dụ PKCS12 |
| `-storepass <password>` | Mật khẩu keystore |
| `-keypass <password>` | Mật khẩu private key nếu khác |
| `-signedjar <file>` | Tên JAR đầu ra sau khi ký |
| `-digestalg <algorithm>` | Thuật toán digest |
| `-sigalg <algorithm>` | Thuật toán chữ ký |
| `-tsa <url>` | Địa chỉ Timestamping Authority |
| `-tsacert <alias>` | Certificate TSA trong keystore |
| `-tsadigestalg <algorithm>` | Thuật toán digest cho yêu cầu timestamp |
| `-verify` | Xác minh JAR đã ký |
| `-verbose` | Hiển thị thông tin chi tiết |
| `-certs` | Hiển thị certificate khi xác minh ở chế độ verbose |
| `-strict` | Xem warning là lỗi |
| `-sigfile <file>` | Tên cơ sở cho signature file |

Một số tùy chọn phụ thuộc phiên bản JDK hoặc provider. Hãy dùng `jarsigner -help` trên môi trường build/phát hành để xác nhận.

## 5. Ký JAR bằng private key

Giả sử đã có JAR `app.jar` và keystore `release-signing.p12` chứa alias `release-key`.

Ký và ghi kết quả ra tệp mới:

```bash
jarsigner -keystore release-signing.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -signedjar app-signed.jar app.jar release-key
```

Giải thích:

- `-keystore release-signing.p12`: keystore chứa private key.
- `-storetype PKCS12`: định dạng keystore.
- `-digestalg SHA-256`: dùng SHA-256 để tạo digest cho nội dung.
- `-sigalg SHA256withRSA`: dùng RSA với SHA-256 để ký signature file.
- `-signedjar app-signed.jar`: ghi JAR đã ký vào tệp mới.
- `app.jar`: JAR nguồn.
- `release-key`: alias của private key dùng ký.

Jarsigner sẽ yêu cầu mật khẩu keystore và, nếu cần, mật khẩu private key. Không truyền mật khẩu thật trong lệnh hoặc file cấu hình có thể bị lưu vào log.

Dùng `-signedjar` giúp giữ lại JAR nguồn để so sánh hoặc ký lại. Nếu bỏ tùy chọn này, jarsigner có thể cập nhật chính JAR đầu vào; trong quy trình phát hành nên dùng artifact đầu ra riêng để dễ kiểm soát.

## 6. Kiểm tra JAR đã ký

Liệt kê nội dung archive:

```bash
jar --list --file app-signed.jar
```

Trong JAR đã ký, thường sẽ có các tệp signature trong `META-INF`, bên cạnh manifest và các class/resource ban đầu.

Xác minh chữ ký:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

Các tùy chọn:

- `-verify`: yêu cầu xác minh chữ ký.
- `-verbose`: hiển thị trạng thái entry và thông tin xác minh.
- `-certs`: hiển thị certificate chain liên quan đến chữ ký.

Có thể dùng chế độ summary:

```bash
jarsigner -verify -verbose:summary -certs app-signed.jar
```

Kết quả có thể cho biết JAR đã được xác minh về mặt chữ ký, đồng thời hiển thị warning nếu certificate tự ký, certificate chain không được tin cậy hoặc có vấn đề về thời hạn/chính sách.

Đừng chỉ nhìn dòng `jar verified`. Hãy đọc toàn bộ warning và kiểm tra từng entry cần được ký. JAR có thể chứa entry chưa được ký hoặc certificate chưa được tin cậy dù phép kiểm tra chữ ký của một số entry thành công.

## 7. Phân biệt integrity và certificate trust

Đây là điểm quan trọng nhất khi đọc kết quả xác minh.

**Integrity/signature verification** trả lời: nội dung được ký có còn khớp với digest và chữ ký hay không?

**Certificate trust** trả lời: có nên tin cậy danh tính người ký dựa trên certificate chain, CA, thời hạn, chính sách và trạng thái thu hồi hay không?

Ví dụ, JAR ký bằng certificate tự ký có thể vượt qua phép kiểm tra toán học của chữ ký nhưng vẫn tạo warning rằng certificate chưa được tin cậy. Người nhận cần xác minh fingerprint certificate qua kênh độc lập và quyết định có tin cậy signer hay không.

Các yếu tố ảnh hưởng trust:

- Certificate có được cấp bởi CA hoặc trust anchor được tin cậy không?
- Certificate còn hiệu lực tại thời điểm ký/xác minh phù hợp không?
- Certificate có mục đích sử dụng phù hợp cho code signing không?
- Certificate chain có đầy đủ và hợp lệ không?
- Có thông tin timestamp đáng tin cậy không?
- Chính sách có yêu cầu kiểm tra revocation không?
- Thuật toán và độ dài khóa có bị security policy của JDK vô hiệu hóa không?

Không import certificate vào truststore chỉ để loại bỏ warning nếu chưa xác minh nguồn gốc và fingerprint.

## 8. Dùng -strict trong quy trình xác minh

Tùy chọn `-strict` yêu cầu jarsigner xem warning là lỗi:

```bash
jarsigner -verify -strict -verbose -certs app-signed.jar
```

Điều này hữu ích trong CI hoặc quy trình release khi mọi warning về chữ ký/certificate đều cần được xử lý.

Với certificate tự ký trong ví dụ học tập, chế độ strict có thể trả trạng thái thất bại do certificate chưa được tin cậy. Đây là kết quả phù hợp với môi trường thử nghiệm, không có nghĩa chữ ký toán học nhất thiết bị hỏng.

Trong release pipeline, hãy cấu hình truststore và certificate chain phù hợp trước khi bật strict. Không hạ mức kiểm tra chỉ để làm pipeline xanh nếu chưa hiểu warning.

Phân biệt:

- `-verify` bật kiểm tra chữ ký.
- `-strict` biến warning thành lỗi.
- `-certs` hiển thị certificate để hỗ trợ đánh giá signer.
- `-verbose` cung cấp chi tiết về các entry và kết quả.

## 9. Timestamp chữ ký với TSA

Khi ký một JAR phát hành lâu dài, có thể thêm timestamp từ một **Timestamping Authority (TSA)**.

Ví dụ cú pháp:

```bash
jarsigner -keystore release-signing.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -tsa <TSA_URL> -signedjar app-timestamped.jar app.jar release-key
```

Thay `<TSA_URL>` bằng URL TSA thực tế do tổ chức hoặc nhà cung cấp tin cậy chỉ định.

Timestamp là bằng chứng do TSA ký, ghi nhận chữ ký tồn tại tại một thời điểm. Nó hữu ích khi certificate ký mã hết hạn sau ngày ký: nếu timestamp và certificate chain hợp lệ, bên xác minh có thể xác định chữ ký được tạo khi certificate còn hiệu lực.

Một số điểm cần nhớ:

- TSA phải được bên xác minh tin cậy.
- Máy build cần kết nối được đến TSA khi ký.
- Timestamp không biến certificate tự ký thành certificate được tin cậy.
- Timestamp không sửa được chữ ký sai hoặc nội dung đã bị thay đổi.
- Timestamp không loại bỏ mọi vấn đề thu hồi certificate hoặc thuật toán yếu.
- Nếu TSA không truy cập được hoặc trả timestamp không hợp lệ, quá trình ký có thể thất bại hoặc không tạo được timestamp mong muốn.

Có thể chọn digest cho timestamp bằng `-tsadigestalg SHA-256` nếu cần cấu hình rõ ràng và JDK/provider hỗ trợ.

## 10. Ký JAR bằng certificate do CA cấp

Trong môi trường phát hành, quy trình thường không dừng ở certificate tự ký.

Quy trình tổng quát:

1. Tạo key pair trong keystore.
2. Tạo CSR bằng `keytool -certreq`.
3. Gửi CSR cho CA hoặc dịch vụ cấp certificate theo quy trình code signing.
4. CA xác minh tổ chức/người yêu cầu và cấp certificate cùng chain.
5. Import certificate reply vào đúng alias chứa private key.
6. Kiểm tra certificate chain bằng `keytool -list -v`.
7. Dùng jarsigner ký JAR bằng alias đó.
8. Thêm timestamp từ TSA phù hợp.
9. Xác minh JAR trên môi trường có trust store tương ứng.

Tạo CSR:

```bash
keytool -certreq -alias release-key -keystore release-signing.p12 -storetype PKCS12 -file release-signing.csr
```

Import certificate reply:

```bash
keytool -importcert -alias release-key -file signing-certificate-chain.pem -keystore release-signing.p12 -storetype PKCS12
```

Tệp certificate reply cần khớp với public key trong CSR và có chain hợp lệ theo yêu cầu CA. Không tạo key pair mới giữa lúc gửi CSR và import certificate reply; nếu đổi key, CSR cũ sẽ không khớp.

## 11. Ký JAR có nhiều signer

Một JAR có thể có chữ ký từ nhiều signer. Ví dụ, một tổ chức có thể yêu cầu cả nhóm build và một đơn vị phát hành cùng ký artifact theo quy trình riêng.

Về nguyên tắc:

- Mỗi signer dùng private key riêng.
- Mỗi signer tạo signature metadata riêng trong `META-INF`.
- Các chữ ký có thể được xác minh độc lập.
- Thêm signer không thay thế hoặc chứng minh thay cho signer trước.
- Mọi signer cần ký cùng nội dung artifact theo quy trình đã thống nhất.

Ví dụ khái niệm: ký JAR bằng signer thứ nhất, sau đó ký JAR đã ký bằng signer thứ hai với keystore/alias khác. Hãy xác minh tất cả chữ ký sau bước cuối cùng:

```bash
jarsigner -verify -verbose -certs app-multisigned.jar
```

Trong thực tế, cần quản lý thứ tự ký, timestamp, certificate chain và chính sách trust của từng signer. Không chỉnh sửa nội dung JAR sau khi các bên đã ký.

## 12. Điều gì làm chữ ký JAR mất hiệu lực?

Chữ ký dựa trên digest của nội dung. Những thao tác sau có thể làm xác minh thất bại hoặc khiến entry không được bảo vệ:

- Sửa bytecode hoặc resource của entry đã ký.
- Thay thế class file trong archive.
- Thay đổi nội dung manifest hoặc signature metadata theo cách làm digest/chữ ký không còn khớp.
- Xóa hoặc thay đổi các tệp chữ ký.
- Thêm entry mới sau khi ký mà không ký lại: entry mới không được chữ ký cũ bảo vệ.

Ví dụ quy trình sai:

1. Build JAR.
2. Ký JAR.
3. Cập nhật một file cấu hình bên trong JAR.
4. Phân phối JAR mà không ký lại.

Quy trình đúng:

1. Build hoàn tất mọi class/resource/configuration.
2. Kiểm tra nội dung JAR.
3. Ký artifact cuối cùng.
4. Xác minh chữ ký.
5. Lưu checksum và phát hành chính artifact đã xác minh.

Nếu cần sửa JAR sau khi ký, hãy tạo artifact mới và ký lại toàn bộ nội dung cuối cùng.

## 13. Thuật toán digest và chữ ký

Hai tùy chọn có vai trò khác nhau:

- `-digestalg`: thuật toán băm nội dung entry.
- `-sigalg`: thuật toán dùng private key để ký signature file.

Ví dụ với RSA:

```bash
jarsigner -digestalg SHA-256 -sigalg SHA256withRSA ...
```

Ví dụ với EC:

```bash
jarsigner -digestalg SHA-256 -sigalg SHA256withECDSA ...
```

Lựa chọn thuật toán cần xét:

- Chính sách bảo mật hiện hành.
- Khả năng tương thích với JDK và nền tảng đích.
- Loại private key trong keystore.
- Quy định của tổ chức hoặc CA.
- Security property của JDK, có thể từ chối thuật toán yếu hoặc bị vô hiệu hóa.

Tránh dùng MD5 hoặc SHA-1 cho chữ ký phát hành mới. Không tự chọn thuật toán cũ chỉ vì cần tương thích với một runtime cũ; hãy đánh giá rủi ro và chính sách hỗ trợ rõ ràng.

## 14. Kiểm tra nội dung signature metadata

Sau khi ký, có thể liệt kê nội dung JAR:

```bash
jar --list --file app-signed.jar
```

Tìm các mục trong `META-INF`, ví dụ:

```text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
com/example/Main.class
config/application.properties
```

Tên `RELEASE` chỉ là minh họa; jarsigner tạo tên signature file dựa trên signer hoặc cấu hình `-sigfile`.

Có thể xem manifest đã ký:

```bash
unzip -p app-signed.jar META-INF/MANIFEST.MF
```

Lệnh `unzip` là tiện ích hệ điều hành, không phải lệnh của JDK. Nếu không có, dùng `jar --extract` để giải nén manifest vào thư mục tạm rồi đọc tệp.

Không chỉnh sửa trực tiếp các tệp `.SF`, `.RSA`, `.DSA` hoặc `.EC`. Chúng là một phần của cấu trúc chữ ký; thay đổi chúng sẽ làm quá trình xác minh không còn hợp lệ.

## 15. Tự động hóa trong CI/CD

Một pipeline ký JAR an toàn thường gồm:

1. Build JAR từ source đã review.
2. Chạy unit test và kiểm tra dependency.
3. Lấy signing key từ kho khóa hoặc dịch vụ ký được kiểm soát.
4. Ký artifact với digest/signature algorithm được phê duyệt.
5. Yêu cầu TSA timestamp nếu chính sách phát hành cần.
6. Xác minh chữ ký bằng `jarsigner -verify`.
7. Chạy `-strict` khi trust store và certificate chain đã được cấu hình đúng.
8. Kiểm tra unsigned entry và warning.
9. Lưu artifact, checksum, signer identity và kết quả xác minh.
10. Phát hành đúng artifact đã được ký và xác minh.

Bảo vệ pipeline:

- Không lưu private key trong repository.
- Không in mật khẩu keystore ra log.
- Ưu tiên secret manager, HSM hoặc dịch vụ ký tập trung nếu phù hợp.
- Hạn chế quyền truy cập signing key cho tài khoản build.
- Tách khóa test và production.
- Theo dõi ngày hết hạn và quy trình luân chuyển certificate.
- Lưu lại bằng chứng ký và timestamp theo yêu cầu kiểm toán.

Nếu dùng secret injection, hãy đảm bảo secret không xuất hiện trong process log, build scan, command history hoặc artifact.

## 16. Lỗi thường gặp khi ký và xác minh JAR

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không mở được keystore | Sai đường dẫn, mật khẩu hoặc store type | Kiểm tra `-keystore`, `-storetype` và mật khẩu |
| Không tìm thấy alias | Alias không tồn tại hoặc gõ sai | Dùng `keytool -list` để kiểm tra |
| Không có private key để ký | Entry là `trustedCertEntry`, không phải `PrivateKeyEntry` | Dùng alias có private key |
| Lỗi thuật toán chữ ký | Thuật toán không tương thích với key hoặc bị security policy chặn | Chọn thuật toán được hỗ trợ và được phê duyệt |
| JAR báo digest error | Entry đã bị thay đổi sau khi ký hoặc archive bị hỏng | Build lại JAR cuối cùng và ký lại |
| JAR verified nhưng có warning trust | Certificate tự ký hoặc chain chưa được tin cậy | Xác minh signer/fingerprint và cấu hình trust phù hợp |
| Strict verification thất bại | Có warning bị `-strict` nâng thành lỗi | Đọc warning, xử lý trust/timestamp/entry rồi chạy lại |
| TSA không phản hồi | URL TSA sai, mạng bị chặn hoặc dịch vụ lỗi | Kiểm tra endpoint, proxy và dịch vụ timestamp |
| Certificate hết hạn | Certificate không còn hiệu lực theo chính sách xác minh | Dùng timestamp hợp lệ nếu có và thực hiện quy trình cấp/luân chuyển certificate |
| Có entry chưa ký | JAR bị thêm file sau khi ký hoặc chỉ ký một phần | Hoàn thiện archive rồi ký lại |
| JAR chạy được nhưng signer không được tin cậy | Integrity không đồng nghĩa với certificate trust | Kiểm tra chain, CA và chính sách trust của môi trường chạy |

## 17. Quy trình ký JAR đề xuất

Một quy trình phát hành có thể lặp lại:

1. Build artifact hoàn chỉnh và xác định đúng JAR đầu ra.
2. Kiểm tra manifest và danh sách entry.
3. Xác nhận keystore có alias `PrivateKeyEntry` đúng.
4. Chọn digest SHA-256 trở lên và signature algorithm tương thích với key.
5. Ký ra tệp mới bằng `-signedjar`.
6. Thêm TSA timestamp nếu chính sách phát hành yêu cầu.
7. Xác minh bằng `jarsigner -verify -verbose -certs`.
8. Kiểm tra warning và certificate trust; dùng `-strict` trong CI khi đã thiết lập trust phù hợp.
9. Kiểm tra JAR không có entry ngoài dự kiến hoặc entry chưa ký.
10. Lưu artifact và bằng chứng xác minh.
11. Phân phối certificate/public key qua kênh tin cậy để người nhận có thể xác minh signer.

Không chỉnh sửa artifact sau khi hoàn tất bước ký. Nếu nội dung thay đổi, hãy tạo lại và ký lại.

## 18. Ghi nhớ

- `jarsigner` dùng private key trong keystore để ký JAR và dùng public key/certificate để xác minh.
- `jarsigner -keystore ... -signedjar ... jar alias` ký JAR ra tệp mới.
- `-digestalg` chọn digest; `-sigalg` chọn thuật toán chữ ký.
- `jarsigner -verify -verbose -certs` kiểm tra chữ ký và hiển thị certificate.
- `-strict` biến warning thành lỗi, phù hợp với release pipeline có trust configuration rõ ràng.
- `-tsa` yêu cầu timestamp từ TSA.
- Integrity của chữ ký khác với trust của certificate.
- Certificate tự ký có thể dùng để thử nghiệm nhưng không tự được tin cậy trong production.
- Sửa JAR sau khi ký làm entry đã ký mất tính toàn vẹn; entry mới thêm vào không được chữ ký cũ bảo vệ.
- Private key và mật khẩu keystore phải được bảo vệ, không commit hoặc đưa vào log.

Khi nắm được quy trình tạo key pair → ký JAR → timestamp → xác minh chữ ký và certificate, bạn có thể phát hành artifact Java có thể kiểm tra tính toàn vẹn và nguồn ký một cách có kiểm soát.
