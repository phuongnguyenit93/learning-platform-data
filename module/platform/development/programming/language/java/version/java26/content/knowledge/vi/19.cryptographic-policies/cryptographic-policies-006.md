# Chuỗi chứng thư, dấu thời gian và độ tin cậy người ký

Khi nhận một JAR đã ký, việc kiểm tra chữ ký toán học chỉ trả lời rằng nội dung được ký chưa bị thay đổi và chữ ký khớp với public key đi kèm. Để quyết định có tin cậy mã đó hay không, ứng dụng còn phải xác minh chứng thư người ký, xây dựng chuỗi chứng thư tới một **trust anchor** được chấp nhận, kiểm tra mục đích sử dụng khóa, thời hạn, thu hồi và chính sách thuật toán. Nếu JAR có timestamp, cần xác minh thêm dấu thời gian cùng chuỗi chứng thư của Time Stamping Authority (TSA).

Java 26 cung cấp API PKIX, `JarFile`, `JarEntry`, `CodeSigner`, `Timestamp`, `CertPathValidator` và công cụ `jarsigner` để thực hiện các bước này. Đây là Java SE API ổn định, không phải preview hay incubator. Quy tắc quan trọng là **chữ ký hợp lệ không tự động làm cho người ký đáng tin cậy**: Javadoc của `JarFile` và `JarEntry` nói rõ quá trình xác minh JAR không bao gồm việc thiết lập trust cho certificate của signer. [Java 26 `JarFile`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html) · [Java 26 `JarEntry`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarEntry.html) · [Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html).

## 1. Phân biệt chữ ký hợp lệ và người ký đáng tin cậy

Một chữ ký số gắn dữ liệu với private key. Public key tương ứng có thể kiểm tra chữ ký, nhưng chỉ riêng phép kiểm tra đó chưa xác định ai đang sở hữu private key. Chứng thư X.509 do CA ký tạo liên kết giữa public key và danh tính/thuộc tính của chủ thể. Chuỗi chứng thư và trust anchor cho phép bên nhận quyết định có chấp nhận liên kết đó hay không.

| Câu hỏi | Cơ chế trả lời | Điều chưa được chứng minh |
|---|---|---|
| Nội dung JAR có bị sửa sau khi ký không? | Kiểm tra digest trong manifest và chữ ký của file `.SF`/signature block. | Chưa chứng minh signer là tổ chức mà ứng dụng muốn tin. |
| Chữ ký có khớp public key trong chứng thư không? | Kiểm tra chữ ký bằng public key của signer. | Chứng thư có thể tự ký hoặc được CA không đáng tin phát hành. |
| Chứng thư signer có nằm trong một đường dẫn hợp lệ không? | Xây dựng/kiểm tra PKIX certification path tới trust anchor. | Trust anchor có phù hợp chính sách ứng dụng hay không vẫn là quyết định của ứng dụng. |
| Chứng thư có được phép ký code không? | Kiểm tra KeyUsage, ExtendedKeyUsage và chính sách signer. | Một chứng thư hợp lệ cho TLS client/server không mặc nhiên là chứng thư code signing. |
| Chữ ký được tạo khi chứng thư signer còn hiệu lực không? | Timestamp token được TSA ký, sau đó đánh giá signer certificate tại thời điểm TSA xác nhận. | Timestamp không bỏ qua việc kiểm tra revocation, trust của TSA hoặc thuật toán yếu. |

Vì vậy, không dùng riêng thông báo `jar verified` làm kết luận rằng ứng dụng có thể chạy mã từ JAR đó. Hãy kiểm tra cả tính toàn vẹn, chuỗi chứng thư, mục đích sử dụng và danh tính signer theo allow-list hoặc trust policy của hệ thống.

## 2. Chuỗi chứng thư X.509 và trust anchor

Một certification path thông thường gồm:

1. **End-entity/leaf certificate:** chứng thư của người ký, chứa public key dùng để xác minh chữ ký JAR.
2. **Intermediate CA certificate(s):** chứng thư của CA trung gian, xác thực public key của CA cấp dưới.
3. **Trust anchor:** CA gốc hoặc chứng thư/key được bên nhận tin cậy trực tiếp và cấu hình trong truststore.

```text
JAR signature
     |
     v
Signer certificate (leaf)
     |
     | được Intermediate CA ký
     v
Intermediate CA certificate
     |
     | được Root CA ký
     v
Root CA / Trust Anchor
     |
     v
Truststore và chính sách của ứng dụng
```

Trust anchor là điểm tin cậy được cấu hình từ trước. Chỉ vì một root certificate được đính kèm trong file JAR hoặc do người gửi cung cấp cùng lúc không có nghĩa là phải tin nó. Nếu chấp nhận root không qua kênh xác minh độc lập, attacker có thể gửi một root giả và một chuỗi hoàn toàn tự nhất quán do chính họ tạo.

Theo quy ước `CertPath` của Java, chuỗi X.509 được sắp từ target/leaf tới chứng thư do trust anchor cấp; chứng thư đại diện cho trust anchor không nằm trong `CertPath`. `PKIXParameters` nhận một hoặc nhiều `TrustAnchor` hoặc một `KeyStore` chứa trusted certificate entries. `CertPathValidator` kiểm tra path theo thuật toán PKIX; `CertPathBuilder` có thể tìm path khi ứng dụng mới có target certificate và các nguồn chứng thư hỗ trợ. [Java 26 `CertPath`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPath.html) · [Java 26 `PKIXParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html) · [Java 26 `CertPathBuilder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathBuilder.html).

### Những gì PKIX kiểm tra

PKIX path validation không chỉ kiểm tra rằng mỗi certificate được ký bởi issuer trước đó. Tùy extension, tham số và chính sách, quá trình còn kiểm tra:

- Chữ ký của từng chứng thư trong path.
- Thời hạn `notBefore`/`notAfter` tại thời điểm đánh giá.
- `BasicConstraints`, quyền CA và path length của intermediate CA.
- Name constraints, certificate policies và các extension critical.
- KeyUsage và các giới hạn thuật toán/key size áp dụng cho path.
- Trạng thái thu hồi qua OCSP hoặc CRL nếu revocation checking được bật và có dữ liệu phù hợp.

Một chứng thư hết hạn, bị thu hồi, có chữ ký dùng thuật toán bị cấm hoặc được cấp sai mục đích đều có thể làm path không hợp lệ. Việc một certificate có `Subject` chứa tên công ty quen thuộc không thay thế bất kỳ kiểm tra nào trong số này.

## 3. Tạo truststore và xác minh CA trước khi tin cậy

Java dùng `KeyStore` để lưu private key, certificate chain và trusted certificate entries. Với ứng dụng cần một chính sách code-signing riêng, nên dùng truststore riêng ở định dạng hiện hành **PKCS12** thay vì nhập tùy tiện CA vào truststore toàn JVM. Điều này giúp ứng dụng chỉ tin các CA được phê duyệt cho mục đích ký phần mềm.

Trước khi nhập root certificate, xem nội dung và fingerprint:

```bash
keytool -printcert -file company-code-root.cer -v
```

So sánh fingerprint SHA-256 với giá trị nhận qua một kênh độc lập, ví dụ trang quản trị PKI nội bộ đã xác thực, tài liệu phát hành được ký hoặc xác nhận trực tiếp từ đội quản trị CA. Không chỉ so sánh fingerprint trên cùng email hoặc cùng file đính kèm chứa certificate.

Sau khi xác minh, tạo truststore riêng:

```bash
keytool -importcert \
        -alias company-code-root \
        -file company-code-root.cer \
        -keystore code-signing-trust.p12 \
        -storetype PKCS12
```

`keytool` yêu cầu xác nhận tin cậy và mật khẩu. Kiểm tra lại entry:

```bash
keytool -list -v \
        -keystore code-signing-trust.p12 \
        -storetype PKCS12
```

Một CA root được nhập dưới dạng trusted certificate entry sẽ có vai trò trust anchor trong `PKIXParameters(KeyStore)`. Không nhập leaf certificate từ JAR thành trusted certificate chỉ để xóa cảnh báo `chainNotValidated`; làm như vậy là chuyển từ mô hình tin cậy CA sang tin cậy trực tiếp một signer cụ thể. Chỉ pin leaf/public key nếu đây là chính sách có chủ đích, có quy trình rotation và xác minh fingerprint rõ ràng.

Truststore mặc định của JDK (`cacerts`) phục vụ các CA mà bản phân phối JDK tin cậy cho những mục đích của nó. Danh sách đó có thể không phải chính sách phù hợp cho code signer nội bộ. Hãy quản lý trust anchor theo mục đích, môi trường và yêu cầu của ứng dụng.

## 4. JAR signature block, manifest và certificate chain

Khi ký JAR bằng `jarsigner`, cấu trúc chữ ký thường thêm hai loại file trong `META-INF`:

- File `.SF`: chứa digest của manifest hoặc các section tương ứng với từng entry.
- File signature block `.RSA`, `.DSA` hoặc `.EC`: chứa chữ ký của `.SF` và certificate hoặc certificate chain xác thực public key signer.

Khi xác minh, `jarsigner` kiểm tra chữ ký của `.SF`, digest giữa `.SF` và manifest, rồi đọc từng entry được liệt kê để so sánh digest nội dung. Nếu entry đã bị thay đổi sau khi ký, kiểm tra sẽ thất bại. Nếu JAR có nhiều signer, mỗi signer có cặp signature file/block riêng.

Certificate chain được đóng gói trong signature block giúp người nhận xây dựng path, nhưng **không tự tạo trust anchor**. Root CA thường cần có sẵn trong truststore của bên nhận. Intermediate certificate có thể được gửi cùng chữ ký hoặc được tìm qua nguồn chứng thư được cấu hình.

Một JAR cũng có thể chứa entry không được ký. `jarsigner` có cảnh báo `hasUnsignedEntry`; ứng dụng cần quyết định có chấp nhận JAR hỗn hợp hay không. Với artifact thực thi, thường nên yêu cầu tất cả entry chứa code/configuration quan trọng được ký bởi signer được phê duyệt.

## 5. Timestamp RFC 3161 chứng minh điều gì?

Timestamp chữ ký được tạo bởi **Time Stamping Authority (TSA)**. Khi ký JAR, `jarsigner` có thể gửi dấu vết băm của chữ ký tới TSA. TSA trả về một `TimeStampToken` có chữ ký riêng, chứa `messageImprint`, hash algorithm, policy và `genTime` theo UTC. Token gắn bằng mật mã với chữ ký được gửi tới TSA.

Timestamp là bằng chứng rằng dữ liệu được đóng dấu đã tồn tại **không muộn hơn thời điểm `genTime` do TSA xác nhận**. Nó mạnh hơn việc ghi `System.currentTimeMillis()` vào manifest hoặc tên file, vì thời gian đó do máy của người ký tự khai báo và không có xác nhận độc lập.

```text
JAR entries + manifest
          |
          v
      jarsigner
          |
          +--> .SF + signature block
                    |
                    v
              chữ ký của signer
                    |
                    v
           hash của chữ ký gửi tới TSA
                    |
                    v
           TSA tạo TimeStampToken
           - messageImprint
           - genTime (UTC)
           - TSA signature
           - TSA certificate/policy
                    |
                    v
          token được lưu trong signature block
```

### Timestamp và chứng thư signer hết hạn

Giả sử chứng thư code-signing của signer có hiệu lực từ ngày A đến ngày B. JAR được ký và TSA đóng dấu ở thời điểm T, trong đó A ≤ T ≤ B. Nếu certificate hết hạn sau B, timestamp hợp lệ có thể cho phép bên kiểm tra đánh giá chữ ký tại T thay vì yêu cầu signer certificate còn hiệu lực ở thời điểm hiện tại. Đây là lý do timestamp rất quan trọng với phần mềm được phân phối và lưu trữ lâu dài.

Timestamp **không kéo dài thời hạn certificate** và không biến một chữ ký vốn đã sai thành đúng. Để dựa vào timestamp, cần ít nhất:

1. Token có chữ ký TSA hợp lệ và `messageImprint` khớp đúng chữ ký của signer.
2. `genTime` được xác minh và nằm trong thời hạn hiệu lực của signer certificate.
3. Chứng thư signer không bị thu hồi tại thời điểm ký theo bằng chứng revocation phù hợp; nếu certificate đã bị thu hồi trước T, timestamp không cứu được chữ ký.
4. TSA certificate/path được tin cậy, đáp ứng mục đích timestamping và không bị chính sách revocation/algorithm loại bỏ.
5. Các thuật toán ký, hash, khóa và certificate path vẫn được chính sách bảo mật hiện hành chấp nhận.

RFC 3161 yêu cầu TSA sử dụng nguồn thời gian đáng tin cậy và khóa dành riêng cho timestamping. Certificate của TSA phải có ExtendedKeyUsage `id-kp-timeStamping` (`1.3.6.1.5.5.7.3.8`) được đánh dấu critical. Bên xác minh cần kiểm tra chữ ký token, imprint, nonce/tính kịp thời khi có, TSA certificate status và policy của TSA. [RFC 3161](https://www.rfc-editor.org/rfc/rfc3161.html).

### Timestamp không thay thế revocation checking

Nếu signer certificate bị thu hồi vì private key bị lộ, cần biết thời điểm thu hồi và nguyên nhân. Timestamp có thể cung cấp bằng chứng chữ ký tồn tại trước thời điểm thu hồi, nhưng chỉ khi timestamp đáng tin và chính sách cho phép chấp nhận chữ ký trước thời điểm đó. Nếu key compromise được xác định đã xảy ra trước `genTime`, không được coi timestamp là giấy phép tự động chấp nhận.

Timestamp TSA cũng có vòng đời riêng. TSA certificate có thể hết hạn, bị thu hồi hoặc dùng thuật toán không còn được chấp nhận. `jarsigner` có cảnh báo nghiêm trọng `hasExpiredTsaCert` và `tsaChainNotValidated` khi timestamp không còn hợp lệ theo kiểm tra của công cụ. Không coi timestamp là bằng chứng tồn tại vĩnh viễn nếu không có kế hoạch bảo toàn token, chain, revocation evidence và thuật toán phù hợp cho việc xác minh lâu dài.

## 6. Ký JAR có timestamp bằng `jarsigner`

Giả sử đã có PKCS12 keystore `release-signing.p12` với alias `releaseSigner`, chứa private key và certificate chain dùng để ký. Dùng TSA được tổ chức tin cậy:

```bash
jarsigner -keystore release-signing.p12 \
          -signedjar app-signed.jar \
          -tsa https://tsa.example.com \
          app.jar releaseSigner
```

Nếu không cung cấp `-storepass` hoặc `-keypass`, công cụ sẽ hỏi tương tác. Tránh đặt password trực tiếp trong command line hoặc script có thể bị ghi lại trong process list/log. `-tsa` chỉ định URL TSA; `jarsigner` dùng Time-Stamp Protocol theo RFC 3161 và lưu token trong signature block. Có thể cấu hình TSA certificate qua `-tsacert` nếu alias trong keystore chứa certificate TSA cùng Subject Information Access URL.

Không tự chọn SHA-1/MD5 hoặc khóa yếu để tương thích với một hệ thống cũ. Để JDK chọn thuật toán mặc định hiện hành trừ khi có yêu cầu interoperability cụ thể; nếu phải override `-sigalg`, `-digestalg` hoặc `-tsadigestalg`, hãy kiểm tra danh sách thuật toán được hỗ trợ và disabled-algorithm policy của tất cả runtime cần xác minh.

Xác minh JAR:

```bash
jarsigner -verify -strict -revCheck -verbose -certs app-signed.jar
```

- `-verify` kiểm tra chữ ký và digest của các entry.
- `-verbose -certs` hiển thị thông tin entry và certificate của signer.
- `-strict` khiến severe warnings được phản ánh thành exit code khác 0.
- `-revCheck` yêu cầu `jarsigner` kiểm tra trạng thái thu hồi qua OCSP/CRL; thao tác này cần network hoặc nguồn revocation phù hợp.

Không có `-revCheck`, `jarsigner` không bật revocation checking trong quá trình validate chain. Trong CI, không chỉ kiểm tra chuỗi `jar verified`: đọc toàn bộ warning, đặc biệt `chainNotValidated`, `tsaChainNotValidated`, `disabledAlg`, `badKeyUsage`, `badExtendedKeyUsage`, `hasUnsignedEntry` và `noTimestamp`. `-strict` chuyển severe warnings thành lỗi, nhưng informational warnings như `legacyAlg` hoặc `noTimestamp` vẫn cần được CI/policy xử lý riêng.

## 7. Kiểm tra chain bằng Java PKIX API

Khi ứng dụng cần tự quyết định trust policy, dùng `CertPathValidator` với thuật toán `PKIX` và truststore đã được quản lý. Ví dụ dưới đây minh họa validate một `CertPath` đã có sẵn; `KeyStore` chỉ nên chứa trusted certificate entries đại diện cho trust anchor được phê duyệt.

```java
import java.security.KeyStore;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXParameters;
import java.util.Date;

static void validatePath(
        CertPath path,
        KeyStore trustStore,
        Date validationTime) throws Exception {

    PKIXParameters parameters = new PKIXParameters(trustStore);
    parameters.setDate(validationTime);

    // Bật kiểm tra thu hồi; provider có thể cần truy cập OCSP/CRL.
    parameters.setRevocationEnabled(true);

    CertPathValidator validator = CertPathValidator.getInstance("PKIX");
    validator.validate(path, parameters);
}
```

`PKIXParameters(KeyStore)` lấy trust anchors từ các trusted certificate entries. Private-key entries trong keystore không tự trở thành trust anchor. `setDate` đặt thời điểm đánh giá hiệu lực path; nếu không đặt, PKIX mặc định đánh giá theo thời điểm hiện tại. Revocation checking có thể cần truy vấn OCSP hoặc CRL và có thể thất bại khi không lấy được dữ liệu. Trong môi trường production, cấu hình nguồn revocation, timeout, cache, fallback và hành vi khi offline theo chính sách bảo mật; không bật `SOFT_FAIL` chỉ để che lỗi mạng nếu hệ thống yêu cầu fail-closed.

Nếu đã có đủ signer leaf và intermediate certificates, tạo `CertPath` bằng `CertificateFactory` rồi gọi validator. Nếu thiếu intermediate, dùng `CertPathBuilder` cùng `PKIXBuilderParameters` và `CertStore` để tìm path. Không tự nối certificate theo thứ tự tên issuer rồi coi như đã xác thực.

## 8. Lấy signer và timestamp từ một JAR bằng `JarFile`

`JarFile` có thể xác minh nội dung entry và cung cấp `CodeSigner`. Phải mở JAR với verification bật và đọc entry tới EOF; `JarEntry.getCodeSigners()` chỉ có dữ liệu sau khi entry đã được đọc và xác minh hoàn chỉnh.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.security.CodeSigner;
import java.security.Timestamp;
import java.util.Date;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

static void inspectEntry(Path jarPath, String entryName) throws Exception {
    try (JarFile jar = new JarFile(jarPath.toFile(), true)) {
        JarEntry entry = jar.getJarEntry(entryName);
        if (entry == null) {
            throw new IllegalArgumentException("Entry not found: " + entryName);
        }

        // Đọc hết entry để JarFile thực hiện kiểm tra digest/chữ ký.
        try (InputStream input = jar.getInputStream(entry)) {
            input.transferTo(OutputStream.nullOutputStream());
        }

        CodeSigner[] signers = entry.getCodeSigners();
        if (signers == null || signers.length == 0) {
            throw new SecurityException("Entry is unsigned: " + entryName);
        }

        for (CodeSigner signer : signers) {
            Timestamp timestamp = signer.getTimestamp();
            Date signingTime = timestamp == null
                    ? new Date()
                    : timestamp.getTimestamp();

            System.out.println("Signer path: " + signer.getSignerCertPath());
            System.out.println("Timestamp: " + signingTime);

            // Ở đây gọi validatePath(signer.getSignerCertPath(),
            // signerTrustStore, signingTime) theo trust policy của ứng dụng.
            // Nếu timestamp != null, cần validate riêng TSA path/token và policy.
        }
    }
}
```

Ví dụ chỉ kiểm tra một entry cụ thể. Với JAR thực tế, lặp qua tất cả payload entries mà ứng dụng sẽ sử dụng, đọc từng entry tới EOF, từ chối entry unsigned nếu policy yêu cầu toàn bộ artifact phải được ký, rồi kiểm tra signer của từng entry. Một JAR có thể có nhiều signer; ứng dụng cần quyết định có yêu cầu một signer cụ thể, một tập signer, hay chỉ cần một signer nằm trong allow-list.

`CodeSigner.getTimestamp()` trả về `null` nếu chữ ký không có timestamp. Nếu có, `Timestamp.getTimestamp()` trả về thời gian và `Timestamp.getSignerCertPath()` trả về path của TSA. Các dữ liệu này cho phép ứng dụng áp dụng validation time và trust policy riêng. Tuy nhiên, việc đọc được `CodeSigner` không thay thế việc validate trust anchor, TSA certificate, revocation và mục đích sử dụng certificate.

### Kiểm tra mục đích sử dụng certificate

Với signer leaf, kiểm tra KeyUsage `digitalSignature` nếu extension được đặt và ExtendedKeyUsage `codeSigning` (`1.3.6.1.5.5.7.3.3`) nếu certificate giới hạn mục đích sử dụng. Với TSA leaf, RFC 3161 yêu cầu EKU `id-kp-timeStamping` (`1.3.6.1.5.5.7.3.8`) và extension EKU phải critical. JDK `jarsigner` có severe warnings `badKeyUsage` và `badExtendedKeyUsage` khi certificate signer không cho phép code signing.

Không dùng một certificate chỉ có EKU `serverAuth` hoặc `clientAuth` như code-signing certificate chỉ vì nó được CA tin cậy. Trust path chứng minh chuỗi phát hành; KeyUsage/EKU chứng minh mục đích khóa được phép dùng.

## 9. Đánh giá timestamp đúng thời điểm

Khi JAR có timestamp, thời điểm đánh giá signer certificate thường là `Timestamp.getTimestamp()`, sau khi token và TSA đã được xác minh. Khi không có timestamp, không có bằng chứng độc lập cho biết chữ ký được tạo khi nào; việc kiểm tra certificate thường phải dựa vào thời điểm hiện tại và policy chấp nhận artifact không timestamp.

| Trạng thái | Cách đánh giá signer certificate | Kết quả cần xem xét |
|---|---|---|
| Chưa hết hạn, không có timestamp | Tại thời điểm hiện tại. | Path phải còn hiệu lực; cần revocation và trust check. |
| Đã hết hạn, có timestamp hợp lệ trong thời hạn certificate | Tại `genTime` của TSA. | Có thể tiếp tục xác minh chữ ký cũ nếu signer path hợp lệ tại thời điểm đó, TSA được tin và thuật toán còn được chấp nhận. |
| Đã hết hạn, không có timestamp | Không có bằng chứng tin cậy về thời điểm ký. | Không tự suy ra chữ ký được tạo trước ngày hết hạn; JAR có thể không còn được xác minh sau expiry. |
| Bị thu hồi trước hoặc tại `genTime` | Kiểm tra revocation evidence và thời điểm thu hồi. | Không chấp nhận chỉ vì có timestamp. |
| Bị thu hồi sau `genTime` | Cần bằng chứng lịch sử và lý do thu hồi. | Timestamp có thể hỗ trợ chứng minh chữ ký tồn tại trước thời điểm thu hồi, nhưng quyết định cuối cùng phụ thuộc policy và loại compromise. |
| TSA chain hết hạn/không tin cậy hoặc token sai | Timestamp không được chấp nhận. | Không dùng timestamp để thay đổi validation date của signer. |

`PKIXParameters.setDate` chỉ đặt thời điểm mà PKIX dùng để đánh giá path. Nó không tự xác minh RFC 3161 token, không chứng minh `messageImprint` khớp chữ ký, không kiểm tra TSA policy và không tạo ra dữ liệu lịch sử revocation còn thiếu. Các bước này phải được thực hiện bởi cơ chế xác minh timestamp và chính sách PKI có thẩm quyền.

## 10. Thu hồi chứng thư: OCSP, CRL và chính sách fail-closed

Certificate có thể bị thu hồi trước khi hết hạn, ví dụ private key bị lộ, thông tin subject sai hoặc CA ngừng tin cậy. Hai cơ chế phổ biến:

- **CRL (Certificate Revocation List):** CA ký một danh sách certificate serial number đã bị thu hồi, có thời điểm phát hành và thời điểm cập nhật tiếp theo.
- **OCSP (Online Certificate Status Protocol):** client hỏi responder về trạng thái của một certificate cụ thể.

`PKIXRevocationChecker` hỗ trợ OCSP và CRL. Theo Javadoc Java 26, OCSP được ưu tiên mặc định và CRL là fallback; có thể dùng `PREFER_CRLS` hoặc `NO_FALLBACK` để điều chỉnh. `SOFT_FAIL` cho phép bỏ qua một số lỗi kết nối khi lấy trạng thái revocation. Đây là quyết định rủi ro: hệ thống fail-open có thể chấp nhận certificate khi không thể kiểm tra nó đã bị thu hồi hay chưa.

Trong quy trình release và xác minh artifact quan trọng:

- Lưu lại kết quả kiểm tra và nguồn revocation evidence theo thời điểm.
- Có network route, proxy, timeout và cache phù hợp tới OCSP/CRL endpoints.
- Quy định rõ hành vi khi responder không truy cập được.
- Phân biệt trạng thái `revoked`, `good` và `unknown`; không coi `unknown` là `good`.
- Với timestamp lâu dài, lưu bằng chứng cần thiết để có thể đánh giá trạng thái tại thời điểm ký, không chỉ trạng thái hiện tại.

Trong `jarsigner`, revocation checking không được bật mặc định; thêm `-revCheck` khi chính sách yêu cầu. Tùy chọn này yêu cầu kiểm tra trạng thái thu hồi của các certificate trong signer chain. Không giả định nó thay thế toàn bộ việc xác minh TSA token, TSA certificate path, EKU và policy timestamp; các bước đó cần được kiểm tra riêng theo trust policy. Với code tự dùng PKIX API, kiểm tra `PKIXParameters.isRevocationEnabled()` và cấu hình `PKIXRevocationChecker` theo đúng policy.

## 11. Chính sách thuật toán trong JDK

Một certificate chain có thể đúng về mặt cấu trúc nhưng vẫn bị từ chối vì thuật toán hoặc kích thước khóa không còn được chấp nhận. JDK có các security properties liên quan:

| Security property | Phạm vi chính |
|---|---|
| `jdk.certpath.disabledAlgorithms` | Thuật toán/key size bị cấm trong certification path validation. |
| `jdk.jar.disabledAlgorithms` | Thuật toán bị cấm trong JAR signature verification. Nếu chữ ký dùng thuật toán bị disable, JAR được coi như unsigned đối với xác minh. |
| `jdk.security.legacyAlgorithms` | Thuật toán bị xem là legacy; công cụ có thể phát informational warning để báo trước khả năng bị disable trong tương lai. |

Các property được cấu hình trong `<java-home>/conf/security/java.security` ở JDK hiện đại. Giá trị cụ thể thay đổi theo bản phát hành và nhà cung cấp JDK; không sao chép một danh sách hard-coded từ bài viết cũ. `jarsigner` dùng `jdk.jar.disabledAlgorithms` và `jdk.security.legacyAlgorithms`; PKIX implementation của Oracle dùng `jdk.certpath.disabledAlgorithms` khi xây dựng/kiểm tra path.

Không xóa một algorithm restriction toàn cục chỉ để làm một JAR cũ vượt qua kiểm tra. Hướng xử lý là phát hành lại artifact bằng digest/signature algorithm và key size hiện hành, cập nhật certificate chain, timestamp lại bằng TSA phù hợp, hoặc thay dependency không còn được duy trì. Nếu cần ngoại lệ tương thích trong thời gian chuyển đổi, phải có scope, thời hạn và người phê duyệt rõ ràng.

## 12. Định danh signer và allow-list

Certificate subject/CN là thông tin hiển thị, không phải khóa định danh duy nhất. Nhiều certificate có thể dùng cùng Common Name; một tổ chức có thể đổi tên, tái cấp certificate hoặc dùng CA khác. Ứng dụng nên định nghĩa signer policy theo một hoặc nhiều yếu tố:

- Trust anchor/CA được phê duyệt cho code signing.
- Certificate policy OID hoặc EKU/KeyUsage theo quy định.
- Fingerprint certificate hoặc public key/SPKI đã được pin nếu cần trust trực tiếp.
- Danh tính signer và quy tắc rotation được quản lý trong allow-list.
- Tên artifact, version, repository hoặc release metadata được gắn với quy trình phát hành đã xác thực.

Không chỉ so sánh `X509Certificate.getSubjectX500Principal()` với một chuỗi tên công ty. Nếu pin certificate fingerprint, phải có kế hoạch thay fingerprint khi certificate được cấp mới. Nếu pin public key, cần đánh giá rủi ro khi khóa bị compromise và cách chuyển sang key mới.

Một JAR có nhiều signer không tự động đáng tin hơn một JAR có một signer. Cần xác định chính xác điều kiện chấp nhận: phải có signer A, phải có cả A và B, hoặc phải có ít nhất một signer thuộc một nhóm được phép. Không dùng phép kiểm tra “có bất kỳ certificate nào” thay cho policy signer.

## 13. Những cảnh báo quan trọng khi xác minh JAR

| Cảnh báo của `jarsigner` | Ý nghĩa | Cách xử lý |
|---|---|---|
| `chainNotValidated` | Signer certificate chain không được xác minh tới trust anchor. | Kiểm tra intermediate/root và truststore; không import leaf tùy tiện để xóa cảnh báo. |
| `tsaChainNotValidated` | TSA chain hoặc timestamp không hợp lệ. | Xác minh TSA certificate, EKU, chain, revocation và timestamp token. |
| `hasExpiredCert` | Signer certificate hết hạn theo thời điểm đánh giá. | Kiểm tra timestamp có hợp lệ trước ngày hết hạn hay không; nếu không, cấp certificate mới và ký lại. |
| `hasExpiredTsaCert` | Timestamp đã hết hạn theo validation của công cụ. | Kiểm tra TSA chain/token và kế hoạch bảo toàn timestamp dài hạn. |
| `disabledAlg` | Thuật toán hoặc key size bị policy hiện hành cấm. | Ký lại bằng thuật toán hiện hành; không gỡ restriction toàn cục. |
| `legacyAlg` | Thuật toán bị xem là yếu/legacy nhưng chưa bị disable. | Lập kế hoạch tái ký trước khi JDK tương lai disable. |
| `badKeyUsage` / `badExtendedKeyUsage` | Certificate không cho phép mục đích code signing. | Dùng certificate được cấp đúng purpose. |
| `hasUnsignedEntry` | Có entry chưa được integrity-check bởi chữ ký. | Xác định entry có thể chạy/ảnh hưởng ứng dụng không; ký lại artifact đầy đủ nếu policy yêu cầu. |
| `noTimestamp` | Chữ ký không có timestamp. | Cân nhắc ký lại có TSA timestamp trước khi phân phối lâu dài. |

`jarsigner -strict` biến severe warnings thành lỗi với exit code khác 0. Nếu chỉ có informational warnings, công cụ vẫn có thể trả exit code 0; CI cần đọc cảnh báo và áp dụng policy riêng, không dựa vào exit code duy nhất.

## 14. Quy trình kiểm tra một JAR trước khi chạy

Một quy trình release/deploy có thể đi theo thứ tự:

1. **Xác minh nguồn artifact:** lấy JAR từ repository/release channel đã xác thực; kiểm tra hash ngoài băng nếu quy trình yêu cầu.
2. **Kiểm tra chữ ký và entry digest:** chạy `jarsigner -verify -strict -verbose -certs`; từ chối JAR có entry bị sửa hoặc không đáp ứng policy unsigned-entry.
3. **Xác minh chain signer:** kiểm tra leaf/intermediate tới trust anchor đã được quản lý; xác nhận KeyUsage/EKU và danh tính signer nằm trong allow-list.
4. **Xác minh timestamp:** kiểm tra token, TSA chain, TSA EKU, `genTime`, message imprint, policy và revocation evidence.
5. **Kiểm tra thuật toán:** đối chiếu `jdk.jar.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms` và `jdk.security.legacyAlgorithms` của runtime triển khai.
6. **Đánh giá revocation:** thực hiện OCSP/CRL theo policy; quy định rõ khi nguồn revocation không truy cập được.
7. **Ghi lại quyết định:** lưu signer fingerprint, chain/trust anchor, timestamp, kết quả revocation, thuật toán và JDK build dùng để xác minh.
8. **Chỉ thực thi sau khi policy pass:** chữ ký đúng nhưng signer không được tin cậy vẫn phải bị từ chối.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| JAR có chữ ký hợp lệ thì chắc chắn an toàn. | Chữ ký chỉ chứng minh nội dung khớp private key; còn cần trust signer và policy ứng dụng. |
| Certificate chain đi kèm JAR tự tạo trust. | Chain chỉ cung cấp dữ liệu để xây path; trust anchor phải được bên nhận cấu hình độc lập. |
| Root certificate phải nằm trong `CertPath`. | Theo quy ước Java PKIX, trust anchor không nằm trong `CertPath`; nó được cung cấp qua `PKIXParameters`. |
| `jar verified` có nghĩa signer đã được tin cậy. | `JarFile` verification không thiết lập signer trust; cần PKIX validation và allow-list riêng. |
| Timestamp là thời gian file hoặc thời gian máy ký. | RFC 3161 token do TSA ký xác nhận dữ liệu đã tồn tại không muộn hơn `genTime`. |
| Timestamp kéo dài thời hạn của signer certificate. | Timestamp cung cấp bằng chứng để đánh giá chữ ký tại thời điểm ký; certificate vẫn hết hạn và revocation vẫn phải kiểm tra. |
| Có timestamp thì không cần kiểm tra TSA. | TSA signature, certificate path, EKU, revocation và policy phải được xác minh. |
| OCSP/CRL luôn được kiểm tra mặc định bởi `jarsigner`. | `jarsigner` cần `-revCheck`; không bật tùy chọn này thì revocation checking không được thực hiện. |
| `-strict` biến mọi cảnh báo thành lỗi. | Nó biến severe warnings thành lỗi; informational warnings vẫn có thể trả exit code 0. |
| Chỉ cần so sánh CN trong certificate. | CN không phải định danh duy nhất; cần CA/trust policy, EKU và signer pin/allow-list. |

## 16. Checklist triển khai

- [ ] Đã phân biệt kiểm tra chữ ký JAR với xác minh trust của signer.
- [ ] Đã hiểu leaf, intermediate CA và trust anchor; root tin cậy được cấu hình ngoài artifact.
- [ ] Đã xác minh fingerprint CA qua một kênh độc lập trước khi import vào truststore.
- [ ] Đã dùng truststore PKCS12 riêng theo chính sách ứng dụng khi cần signer trust nội bộ.
- [ ] Đã kiểm tra PKIX path, thời hạn, BasicConstraints, KeyUsage, EKU và algorithm constraints.
- [ ] Đã xác định signer được phép bằng CA/policy/fingerprint hoặc allow-list; không chỉ dựa vào CN.
- [ ] Đã đọc toàn bộ JAR entry trước khi lấy `JarEntry.getCodeSigners()`.
- [ ] Đã quyết định cách xử lý entry unsigned và JAR có nhiều signer.
- [ ] Đã tạo timestamp RFC 3161 từ TSA được tin cậy khi cần lưu trữ/xác minh dài hạn.
- [ ] Đã xác minh `messageImprint`, `genTime`, TSA chain, TSA EKU `id-kp-timeStamping` và TSA revocation.
- [ ] Đã đánh giá signer certificate tại timestamp hợp lệ khi có token; không dùng timestamp không hợp lệ để bỏ qua expiry.
- [ ] Đã bật revocation checking theo policy và hiểu hành vi khi OCSP/CRL không truy cập được.
- [ ] Đã kiểm tra `jdk.certpath.disabledAlgorithms`, `jdk.jar.disabledAlgorithms` và cảnh báo legacy của JDK đích.
- [ ] Đã dùng `jarsigner -verify -strict` và xử lý cả informational warnings trong CI.
- [ ] Đã có quy trình certificate/key rotation, timestamp preservation và tái ký artifact.
- [ ] Đã xác minh lại trên JDK build sẽ chạy production; không phụ thuộc API preview/incubator hoặc cơ chế legacy.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `JarFile`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html)
- [Java SE 26 — `JarEntry`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarEntry.html)
- [Java SE 26 — `CodeSigner`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/CodeSigner.html)
- [Java SE 26 — `Timestamp`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Timestamp.html)
- [Java SE 26 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [Java SE 26 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html)
- [Java SE 26 — `PKIXRevocationChecker`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html)
- [Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html)
- [The `jarsigner` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [The `keytool` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161.html)
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [JDK 26 — Disabling and Restricting Cryptographic Algorithms](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)

*Cập nhật nội dung: 27-11-2026. Các API PKIX/JAR dùng trong bài là Java SE ổn định. Timestamp chỉ có giá trị khi token và TSA được xác minh; trust anchor, revocation và thuật toán phải phù hợp chính sách của runtime đang triển khai.*
