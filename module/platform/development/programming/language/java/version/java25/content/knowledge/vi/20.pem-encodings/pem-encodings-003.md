# Phân biệt lớp bao PEM với cấu trúc dữ liệu khóa hoặc chứng chỉ bên trong

## 1. Mục tiêu và bối cảnh

Trong các hệ thống Java tích hợp TLS, chữ ký số, xác thực client hoặc PKI doanh nghiệp, khóa và chứng chỉ thường được trao đổi dưới dạng tệp có phần mở rộng `.pem`, `.crt`, `.cer` hoặc `.key`. Một chuỗi bắt đầu bằng `-----BEGIN CERTIFICATE-----` trông giống một định dạng dữ liệu hoàn chỉnh, nhưng thực tế nó gồm nhiều lớp khác nhau.

**PEM (Privacy-Enhanced Mail)** là lớp biểu diễn văn bản để vận chuyển dữ liệu nhị phân. Phần thân PEM thường là Base64 của một cấu trúc nhị phân như ASN.1 DER. Cấu trúc bên trong mới mô tả đối tượng mật mã cụ thể: chứng chỉ X.509, SubjectPublicKeyInfo, khóa riêng PKCS #8, CRL hoặc một cấu trúc PKCS/CMS khác.

Nếu chỉ nhìn nhãn PEM, ta có thể nhầm một khóa riêng PKCS #8 với khóa riêng RSA PKCS #1, hoặc nhầm một chứng chỉ X.509 với một yêu cầu ký chứng chỉ PKCS #10. Những cấu trúc này có thể cùng được bọc trong PEM nhưng không thể thay thế cho nhau.

Bài **Phân biệt lớp bao PEM với cấu trúc dữ liệu khóa hoặc chứng chỉ bên trong**, thuộc chương **Mã hóa PEM** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào:

1. Cấu trúc văn bản PEM: BEGIN/END label và Base64.
2. Quan hệ giữa PEM, ASN.1, DER và các chuẩn PKCS/X.509.
3. Ý nghĩa của các nhãn `CERTIFICATE`, `PUBLIC KEY`, `PRIVATE KEY`, `ENCRYPTED PRIVATE KEY`.
4. Phân biệt PKCS #8, PKCS #1, SEC1, SubjectPublicKeyInfo và X.509 Certificate.
5. Dùng API PEMDecoder, PEMEncoder, DEREncodable và PEMRecord của Java 25.
6. Xác định điều gì được decoder phân tích và điều gì vẫn cần kiểm tra bảo mật ở tầng ứng dụng.
7. Nhận biết thay đổi API qua JDK 26, 27 và JDK 28.

**Phạm vi phiên bản:** ví dụ API trong bài dùng JDK 25 và **JEP 470 – PEM Encodings (Preview)**. API này cần bật preview trong Java 25. Tại ngày 27/11/2026, JDK 27 vẫn có preview lần thứ ba; JEP 542 đã hoàn thiện API trong nhánh JDK 28 Early Access. Phần lịch sử phiên bản sẽ phân biệt chính xác các tên API để không trộn source code giữa các release.

## 2. PEM là lớp bao văn bản, không phải cấu trúc khóa

Một khối PEM thường có dạng:

~~~text
-----BEGIN CERTIFICATE-----
MIIB...Base64-encoded-data...==
-----END CERTIFICATE-----
~~~

Khối này gồm ba phần:

| Phần | Vai trò |
| --- | --- |
| **BEGIN label** | Cho biết loại dữ liệu mà khối PEM tuyên bố chứa. |
| **Base64 body** | Chuyển byte nhị phân thành ký tự ASCII để dễ lưu trữ và trao đổi. |
| **END label** | Đóng khối; label phải tương ứng với label mở theo quy tắc định dạng. |

Có thể hình dung luồng dữ liệu như sau:

~~~mermaid
flowchart TD
    A["Java cryptographic object"] --> B["Binary encoding"]
    B --> C["ASN.1 structure encoded as DER"]
    C --> D["Base64 text"]
    D --> E["PEM BEGIN label + body + END label"]
    E --> F["File, email, config hoặc secret store"]
    F --> G["PEM decoder"]
    G --> H["Base64 decode"]
    H --> I["Binary ASN.1 payload"]
    I --> J["Parse thành key / certificate / CRL"]
~~~

**PEM không tự mô tả toàn bộ cấu trúc mật mã.** Label là gợi ý loại cấu trúc được mong đợi; Base64 chỉ mã hóa biểu diễn byte. Muốn biết bên trong có trường nào, thuật toán nào, public key thuộc loại gì hoặc certificate do ai ký, phải phân tích payload theo chuẩn tương ứng.

PEM cũng không tự mã hóa bí mật, không ký dữ liệu và không xác minh nguồn gốc. Bất kỳ ai cũng có thể Base64-encode một chuỗi byte rồi đặt nó giữa hai dòng BEGIN/END.

## 3. ASN.1 và DER nằm ở lớp bên trong

Nhiều cấu trúc khóa và chứng chỉ trong hệ sinh thái PKI được mô tả bằng **ASN.1 (Abstract Syntax Notation One)**. ASN.1 định nghĩa cấu trúc dữ liệu độc lập với ngôn ngữ lập trình, ví dụ một Certificate có trường issuer, subject, validity, subject public key và chữ ký.

ASN.1 là mô hình mô tả dữ liệu; nó không phải một chuỗi byte duy nhất. Muốn truyền cấu trúc ASN.1 thành byte cần một quy tắc mã hóa:

- **BER (Basic Encoding Rules):** họ quy tắc mã hóa ASN.1 linh hoạt.
- **DER (Distinguished Encoding Rules):** tập con có tính canonical hơn của BER, quy định một cách biểu diễn chuẩn cho cấu trúc hợp lệ.

Nhiều định dạng khóa/chứng chỉ PKIX và PKCS sử dụng DER trong payload PEM. RFC 7468 mô tả textual encoding cho các cấu trúc PKIX, PKCS và CMS; một số cấu trúc cho phép BER, nhưng DER thường được ưu tiên để có biểu diễn ổn định.

~~~text
PEM text
  └── Base64 decode
        └── DER bytes (thường gặp)
              └── ASN.1 value
                    └── Certificate / SubjectPublicKeyInfo /
                        PrivateKeyInfo / EncryptedPrivateKeyInfo ...
~~~

### DER không phải Base64

Base64 là lớp biểu diễn byte thành ký tự. DER là cách mã hóa một giá trị ASN.1 thành byte. Có thể Base64-encode bất kỳ byte nào, kể cả dữ liệu không phải DER. Vì vậy:

- Base64 decode thành công không chứng minh payload là DER hợp lệ.
- DER parse thành công không chứng minh certificate đáng tin cậy.
- Certificate parse thành công không chứng minh certificate hợp lệ cho hostname hoặc mục đích sử dụng.

Mỗi lớp cần được kiểm tra bằng parser và quy trình xác thực phù hợp.

## 4. Ý nghĩa của PEM label

Các label phổ biến theo RFC 7468:

| PEM label | Loại cấu trúc bên trong | Chuẩn thường liên quan |
| --- | --- | --- |
| `CERTIFICATE` | Chứng chỉ X.509 | X.509 / RFC 5280 |
| `PUBLIC KEY` | SubjectPublicKeyInfo (SPKI) | X.509 / RFC 5280 |
| `PRIVATE KEY` | PrivateKeyInfo hoặc OneAsymmetricKey không mã hóa | PKCS #8 / RFC 5208, RFC 5958 |
| `ENCRYPTED PRIVATE KEY` | EncryptedPrivateKeyInfo | PKCS #8 |
| `X509 CRL` | Certificate Revocation List | X.509 / RFC 5280 |
| `CERTIFICATE REQUEST` | CertificationRequest | PKCS #10 / RFC 2986 |
| `PKCS7` hoặc `CMS` | Cấu trúc SignedData/ContentInfo tương ứng | PKCS #7 / CMS |

Label là định danh textual theo quy ước của loại payload. Nó không phải thuật toán mã hóa, không phải tên Java class và không chứng minh payload thực sự phù hợp với label.

### Label chuẩn và label lịch sử

Đối với chứng chỉ, RFC 7468 yêu cầu generator dùng label **`CERTIFICATE`**. Các label cũ như `X509 CERTIFICATE` hoặc `X.509 CERTIFICATE` đã xuất hiện trong một số công cụ. Parser có thể hỗ trợ chúng để tương thích, nhưng ứng dụng mới nên tạo label chuẩn.

Đừng tự đổi label bằng cách sửa text. Ví dụ, đổi `BEGIN RSA PRIVATE KEY` thành `BEGIN PRIVATE KEY` không chuyển payload PKCS #1 thành PKCS #8; chỉ thay chữ trên lớp ngoài mà không thay cấu trúc ASN.1 bên trong.

## 5. Phân biệt các dạng khóa riêng thường gặp

Một nguyên nhân phổ biến gây lỗi tích hợp là coi mọi file có chữ `PRIVATE KEY` là cùng một cấu trúc.

| Label | Cấu trúc bên trong | Mô tả |
| --- | --- | --- |
| `PRIVATE KEY` | PKCS #8 `PrivateKeyInfo` hoặc RFC 5958 `OneAsymmetricKey` | Container tổng quát có algorithm identifier và private key bytes; có thể mang thêm public key trong dạng OneAsymmetricKey. |
| `ENCRYPTED PRIVATE KEY` | PKCS #8 `EncryptedPrivateKeyInfo` | Container PKCS #8 chứa thuật toán mã hóa, tham số và dữ liệu private key đã mã hóa. |
| `RSA PRIVATE KEY` | PKCS #1 `RSAPrivateKey` | Cấu trúc riêng cho khóa RSA, chứa các tham số RSA như modulus và private exponent. |
| `EC PRIVATE KEY` | SEC 1 `ECPrivateKey` | Cấu trúc khóa riêng elliptic-curve theo SEC 1, không phải PKCS #8. |

### PKCS #8: container tổng quát

PKCS #8 không định nghĩa một thuật toán khóa duy nhất. Nó cung cấp cấu trúc để chứa private key cùng định danh thuật toán và tham số liên quan. Do đó một khóa RSA, EC hoặc một thuật toán khác có thể được biểu diễn trong cùng loại container PKCS #8.

### PKCS #1: cấu trúc riêng cho RSA

`RSAPrivateKey` của PKCS #1 chứa trực tiếp các tham số toán học RSA. Nó không phải cấu trúc PKCS #8. Java API `PKCS8EncodedKeySpec` mong đợi dữ liệu PKCS #8, nên không thể chỉ lấy Base64 của `RSA PRIVATE KEY` rồi truyền nguyên vào `PKCS8EncodedKeySpec`.

### SEC 1: cấu trúc riêng cho EC

`ECPrivateKey` theo SEC 1 là cấu trúc khác với PKCS #8. Một số công cụ xuất file `EC PRIVATE KEY`; khả năng đọc trực tiếp phụ thuộc thư viện/provider. API PEM của JDK 25 liệt kê hỗ trợ chuẩn cho `PRIVATE KEY`, còn implementation note có thể hỗ trợ thêm `RSA PRIVATE KEY`; không nên giả định `EC PRIVATE KEY` được mọi JDK hỗ trợ.

Nếu hệ thống yêu cầu PKCS #8, hãy chuyển đổi bằng công cụ hoặc provider đáng tin cậy và xác minh lại key sau chuyển đổi. Không sửa label bằng tay để giả lập chuyển đổi định dạng.

## 6. Phân biệt PUBLIC KEY và RSA PUBLIC KEY

Hai dạng sau cũng không đồng nghĩa:

| Label | Cấu trúc | Nội dung |
| --- | --- | --- |
| `PUBLIC KEY` | X.509 SubjectPublicKeyInfo | AlgorithmIdentifier và BIT STRING chứa public-key data. |
| `RSA PUBLIC KEY` | PKCS #1 `RSAPublicKey` | Cấu trúc RSA trực tiếp gồm modulus và public exponent. |

SPKI có thể mô tả nhiều thuật toán public key, không chỉ RSA. AlgorithmIdentifier trong payload cho biết thuật toán và tham số liên quan.

Đây là lý do `X509EncodedKeySpec` thường được dùng cho dữ liệu `PUBLIC KEY`, còn dữ liệu PKCS #1 `RSA PUBLIC KEY` cần được chuyển đổi hoặc parse bằng API tương ứng. Không được mặc định mọi public-key PEM đều có cùng binary layout.

## 7. CERTIFICATE không đồng nghĩa với PUBLIC KEY

Một certificate X.509 không chỉ là public key. Cấu trúc Certificate chứa:

- Phiên bản và serial number.
- Signature algorithm identifier.
- Issuer và Subject.
- Validity period.
- SubjectPublicKeyInfo.
- Extensions, chẳng hạn Subject Alternative Name, Key Usage và Basic Constraints.
- Chữ ký của issuer trên phần dữ liệu certificate.

Public key nằm bên trong certificate tại trường SubjectPublicKeyInfo, nhưng certificate còn ràng buộc key đó với subject, issuer, thời hạn và các thuộc tính khác.

~~~text
-----BEGIN CERTIFICATE-----
Base64(DER(ASN.1 Certificate {
    tbsCertificate {
        issuer,
        subject,
        validity,
        subjectPublicKeyInfo,
        extensions,
        ...
    },
    signatureAlgorithm,
    signatureValue
}))
-----END CERTIFICATE-----
~~~

Khi Java `PEMDecoder` đọc `CERTIFICATE`, nó tạo `X509Certificate`. Việc parse thành công chỉ chứng minh dữ liệu có thể được biểu diễn thành object certificate; ứng dụng vẫn phải kiểm tra trust chain, validity, hostname, key usage, policy và revocation theo nhu cầu.

## 8. CRL, CSR và bundle cũng có payload riêng

### CRL

`X509 CRL` chứa danh sách chứng chỉ bị thu hồi do CA phát hành. Java có `X509CRL` và `CertificateFactory` để xử lý CRL. CRL không phải certificate và cũng không phải danh sách public key.

### CSR

`CERTIFICATE REQUEST` thường chứa cấu trúc PKCS #10 CertificationRequest, bao gồm subject, SubjectPublicKeyInfo, attributes và chữ ký của người yêu cầu. CSR chưa phải certificate đã được CA cấp.

Trong Java 25, `PEMRecord` có thể giữ loại PEM và Base64 payload cho một số loại mà JDK chưa có cryptographic class tương ứng, ví dụ PKCS #10. Việc có `PEMRecord` không đồng nghĩa JDK đã xác minh chữ ký CSR hoặc kiểm tra nội dung ASN.1.

### Certificate bundle/chain

Một file PEM có thể chứa nhiều khối liên tiếp:

~~~text
-----BEGIN CERTIFICATE-----
...leaf certificate...
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
...intermediate CA...
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
...root CA...
-----END CERTIFICATE-----
~~~

Đây là nhiều đối tượng PEM độc lập được đặt trong cùng một file, không phải một certificate ASN.1 duy nhất. Thứ tự thường được tổ chức theo leaf rồi intermediate, nhưng ứng dụng vẫn phải xác định và xác thực chuỗi chứng chỉ thay vì tin vào thứ tự file.

## 9. PEM có mã hóa dữ liệu không?

**Không. Base64 không phải encryption.** Bất kỳ ai có file PEM không mã hóa đều có thể Base64 decode để lấy payload nhị phân.

| Dạng | Có bí mật không? | Ý nghĩa |
| --- | --- | --- |
| `BEGIN CERTIFICATE` | Không | Certificate vốn được phân phối công khai. |
| `BEGIN PUBLIC KEY` | Không | Public key được thiết kế để chia sẻ. |
| `BEGIN PRIVATE KEY` | Không | Private key ở dạng PKCS #8 không mã hóa; cần bảo vệ file và quyền truy cập. |
| `BEGIN ENCRYPTED PRIVATE KEY` | Có lớp mã hóa khóa riêng | Payload là PKCS #8 EncryptedPrivateKeyInfo, dùng PBE và password/key để giải mã. |

Không thể kết luận private key được bảo vệ tốt chỉ bằng cách nhìn thấy label `ENCRYPTED PRIVATE KEY`. Cần xem thuật toán mã hóa, tham số, chất lượng password và chính sách lưu trữ.

### Không dùng nhầm định dạng mã hóa private key lịch sử

Một số công cụ cũ xuất private key PEM với header phụ như:

~~~text
Proc-Type: 4,ENCRYPTED
DEK-Info: ...
~~~

Đây là dạng mã hóa PEM lịch sử, không phải cấu trúc PKCS #8 `EncryptedPrivateKeyInfo` hiện đại. Không nên chọn dạng này cho thiết kế mới. Ưu tiên encrypted PKCS #8 theo thuật toán PBE được hỗ trợ và chính sách mật mã hiện hành; khi cần đọc file cũ, kiểm tra khả năng tương thích của provider/công cụ thay vì giả định API PEM mới xử lý mọi biến thể lịch sử.

## 10. Java 25 bổ sung API PEM nào?

**JEP 470 – PEM Encodings (Preview)** giới thiệu API trong module `java.base`, package `java.security`:

| API | Vai trò |
| --- | --- |
| `PEMDecoder` | Đọc PEM text hoặc InputStream và chuyển payload thành Java cryptographic object khi loại dữ liệu được hỗ trợ. |
| `PEMEncoder` | Chuyển cryptographic object sang PEM text hoặc byte array. |
| `DEREncodable` | Marker interface preview cho các Java security object có thể biểu diễn bằng DER. |
| `PEMRecord` | Giữ type label, Base64 content và dữ liệu đứng trước khối PEM nếu có. |
| `EncryptedPrivateKeyInfo` | Biểu diễn encrypted private key theo PKCS #8; JDK 25 bổ sung các API preview để mã hóa/giải mã bằng password hoặc key. |

Các API này là preview trong Java 25. Cần bật preview khi biên dịch và chạy; không đưa source code Java 25 preview vào thư viện công khai mà không tính đến thay đổi chữ ký ở release sau.

Vì các lớp nằm trong module `java.base`, không cần thêm module ngoài JDK. Ví dụ biên dịch và chạy một chương trình dùng PEM API:

~~~bash
javac --enable-preview --release 25 -d out src/PemDemo.java
java --enable-preview -cp out PemDemo
~~~

Compiler và runtime phải cùng dùng JDK 25. Chỉ bật `--enable-preview` ở bước biên dịch là chưa đủ. Với JDK 27, phải biên dịch theo release 27 và dùng API `BinaryEncodable`/`PEM`; với JDK 28 EA theo JEP 542, API đã final và không cần `--enable-preview`.

## 11. Đọc PEM thành Java object bằng PEMDecoder

Ví dụ đọc certificate, public key và private key:

~~~java
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

public final class ReadPemObjects {

    static X509Certificate readCertificate(String pem) {
        return PEMDecoder.of().decode(pem, X509Certificate.class);
    }

    static PublicKey readPublicKey(String pem) {
        return PEMDecoder.of().decode(pem, PublicKey.class);
    }

    static PrivateKey readPrivateKey(String pem) {
        return PEMDecoder.of().decode(pem, PrivateKey.class);
    }
}
~~~

Overload `decode(String, Class)` yêu cầu kiểu kết quả phù hợp với PEM label và payload. Ví dụ:

- `CERTIFICATE` có thể decode thành `X509Certificate`.
- `PUBLIC KEY` có thể decode thành `PublicKey`.
- `PRIVATE KEY` có thể decode thành `PrivateKey`.
- `ENCRYPTED PRIVATE KEY` khi chưa cấu hình giải mã sẽ trả `EncryptedPrivateKeyInfo`.

Nếu kiểu được yêu cầu không phù hợp với PEM content, decoder có thể ném `ClassCastException` hoặc lỗi decode. Không bắt exception rồi tiếp tục sử dụng object rỗng như thể dữ liệu đã hợp lệ.

### Dùng decode không chỉ định class

Khi chưa biết chính xác loại object, có thể nhận `DEREncodable` rồi phân nhánh:

~~~java
import java.security.DEREncodable;
import java.security.PEMDecoder;
import java.security.PublicKey;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;

DEREncodable decoded = PEMDecoder.of().decode(pemText);

if (decoded instanceof X509Certificate certificate) {
    System.out.println(certificate.getSubjectX500Principal());
} else if (decoded instanceof PublicKey publicKey) {
    System.out.println(publicKey.getAlgorithm());
} else if (decoded instanceof PrivateKey privateKey) {
    System.out.println(privateKey.getAlgorithm());
} else {
    throw new IllegalArgumentException(
            "PEM type chưa được ứng dụng xử lý: " + decoded.getClass());
}
~~~

Trong code thực tế nên xử lý thêm `X509CRL`, `EncryptedPrivateKeyInfo` và `PEMRecord`. Không coi nhánh default là dữ liệu an toàn; nó có thể là một loại PEM hợp lệ nhưng ứng dụng chưa hỗ trợ.

## 12. PEMRecord giúp giữ payload chưa có Java class

Trong Java 25, `PEMRecord` biểu diễn một PEM block theo ba thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `type()` | Label, ví dụ `CERTIFICATE REQUEST`. |
| `content()` | Base64 text, không gồm BEGIN/END. |
| `leadingData()` | Byte dữ liệu văn bản xuất hiện trước PEM header trong input. |

Ví dụ đọc CSR thành record:

~~~java
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.PEMRecord;

PEMRecord request = PEMDecoder.of().decode(
        csrPemText, PEMRecord.class);

System.out.println(request.type());
String base64Payload = request.content();

String samePayloadTypePem =
        PEMEncoder.of().encodeToString(request);
~~~

`PEMRecord` là lớp giữ cấu trúc PEM tổng quát; nó không tự parse hoặc xác minh ASN.1 payload. API `PEMEncoder` khi mã hóa record sẽ dùng `type()` và `content()` để tạo header/body/footer; `leadingData()` không được đưa trở lại output.

Một lưu ý an toàn: constructor `PEMRecord` không xác minh content có phải Base64 hợp lệ hay có khớp với type label không. Trường `leadingData` là `byte[]` và không được defensive-copy đầy đủ theo hợp đồng Java 25. Không dùng record này làm ranh giới xác thực cho dữ liệu không tin cậy.

## 13. Tạo PEM từ Java object bằng PEMEncoder

Ví dụ chuyển certificate và key thành text:

~~~java
import java.security.KeyPair;
import java.security.PEMEncoder;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.cert.X509Certificate;

public final class WritePemObjects {

    static String encodeCertificate(X509Certificate certificate) {
        return PEMEncoder.of().encodeToString(certificate);
    }

    static String encodePublicKey(PublicKey publicKey) {
        return PEMEncoder.of().encodeToString(publicKey);
    }

    static String encodePrivateKey(PrivateKey privateKey) {
        return PEMEncoder.of().encodeToString(privateKey);
    }

    static String encodeKeyPair(KeyPair keyPair) {
        return PEMEncoder.of().encodeToString(keyPair);
    }
}
~~~

Theo API Java 25:

- `X509Certificate` được encode với label `CERTIFICATE`.
- `PublicKey` được encode với label `PUBLIC KEY` và payload SubjectPublicKeyInfo.
- `PrivateKey` được encode với label `PRIVATE KEY` và payload PKCS #8.
- `KeyPair` được encode thành OneAsymmetricKey theo PKCS #8 v2.0 với label `PRIVATE KEY`.

Không phải mọi `PrivateKey` đều exportable. Một khóa nằm trong HSM hoặc provider chỉ cho phép thao tác ký có thể trả `null` từ `getEncoded()` hoặc không hỗ trợ xuất dữ liệu. PEMEncoder không thể biến một key không exportable thành PEM; giữ key trong provider/HSM và dùng API ký phù hợp.

## 14. Mã hóa private key thành ENCRYPTED PRIVATE KEY

JDK 25 cho phép cấu hình encoder để mã hóa private key bằng password:

~~~java
import java.security.PrivateKey;
import java.security.PEMEncoder;
import java.util.Arrays;

static String encodeEncryptedPrivateKey(
        PrivateKey privateKey, char[] password) {
    try {
        return PEMEncoder.of()
                .withEncryption(password)
                .encodeToString(privateKey);
    } finally {
        Arrays.fill(password, '\0');
    }
}
~~~

Kết quả là PEM có label `ENCRYPTED PRIVATE KEY`, chứa ASN.1 `EncryptedPrivateKeyInfo` theo PKCS #8. Trong JDK 25, `withEncryption(char[])` dùng thuật toán mã hóa mặc định của runtime. Thuộc tính bảo mật `jdk.epkcs8.defaultAlgorithm` xác định thuật toán mặc định; tham số mặc định phụ thuộc provider.

Nếu cần chỉ định thuật toán PBE hoặc tham số rõ ràng, dùng API preview `EncryptedPrivateKeyInfo.encryptKey(...)` với `AlgorithmParameterSpec` và provider phù hợp, sau đó đưa object trả về cho PEMEncoder. Cần chọn thuật toán, iteration/cost và tham số dựa trên chính sách bảo mật hiện hành; không tự đặt một con số hoặc thuật toán cũ chỉ để làm ví dụ.

`char[]` cho phép xóa bản sao do ứng dụng sở hữu sau khi dùng, nhưng không thể bảo đảm mọi bản sao nội bộ của provider/JVM bị xóa tức thì. Không ghi password vào log, command line, source control hoặc cấu hình công khai.

## 15. Giải mã ENCRYPTED PRIVATE KEY

Có thể cấu hình decoder bằng password:

~~~java
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.util.Arrays;

static PrivateKey decodeEncryptedPrivateKey(
        String encryptedPem, char[] password) {
    try {
        return PEMDecoder.of()
                .withDecryption(password)
                .decode(encryptedPem, PrivateKey.class);
    } finally {
        Arrays.fill(password, '\0');
    }
}
~~~

`withDecryption` trả một decoder mới được cấu hình để giải mã private key. Decoder cũng có thể đọc PEM không mã hóa. Nếu không cấu hình decryption, `ENCRYPTED PRIVATE KEY` được trả về dưới dạng `EncryptedPrivateKeyInfo`; ứng dụng có thể giải mã object đó bằng password/key và API tương ứng.

Không nhầm ba bước:

1. PEM decoder loại bỏ lớp text/Base64 và parse cấu trúc PKCS #8.
2. PBE decrypt giải mã nội dung private key bằng password hoặc encryption key.
3. KeyFactory/provider chuyển encoded key material thành `PrivateKey` dùng được.

Sai password, sai thuật toán, payload hỏng hoặc provider không hỗ trợ có thể gây lỗi giải mã. Không thử lần lượt nhiều password trong một vòng lặp không giới hạn; hãy áp dụng chính sách xác thực và audit phù hợp.

## 16. Provider và loại PEM được hỗ trợ

PEMDecoder dùng `KeyFactory` và `CertificateFactory` để tạo Java cryptographic object. Trong Java 25, có thể chỉ định provider:

~~~java
import java.security.PEMDecoder;
import java.security.Provider;
import java.security.Security;
import java.security.cert.X509Certificate;

Provider provider = Security.getProvider("SUN");
if (provider == null) {
    throw new IllegalStateException("Provider không khả dụng");
}

PEMDecoder decoder = PEMDecoder.of().withFactory(provider);
X509Certificate certificate =
        decoder.decode(certificatePem, X509Certificate.class);
~~~

Chỉ định provider hữu ích khi môi trường yêu cầu provider cụ thể, nhưng làm giảm tính linh hoạt nếu tên provider không có ở runtime khác. Chỉ yêu cầu provider riêng khi biết chắc provider đó được cài đặt và cấu hình.

### Các loại PEM được JDK 25 hỗ trợ

Theo Java SE 25 API, decoder ánh xạ các loại phổ biến:

| PEM type | Java object |
| --- | --- |
| `CERTIFICATE` | `X509Certificate` |
| `X509 CRL` | `X509CRL` |
| `PUBLIC KEY` | `PublicKey` |
| `PRIVATE KEY` | `PrivateKey` |
| `ENCRYPTED PRIVATE KEY` | `EncryptedPrivateKeyInfo`, hoặc `PrivateKey` khi cấu hình decryption |
| Loại khác không có Java class tương ứng | `PEMRecord` |

Implementation của JDK 25 còn ghi nhận hỗ trợ thêm `X509 CERTIFICATE`, `X.509 CERTIFICATE`, `CRL` và `RSA PRIVATE KEY`. Đây là implementation note; không nên xem mọi alias đó là bảo đảm liên thông cho tất cả JDK/provider.

Nếu decoder trả `PEMRecord`, điều đó chỉ cho biết API chưa ánh xạ payload sang Java cryptographic type. Ứng dụng cần parser phù hợp hoặc thư viện có hỗ trợ chuẩn tương ứng.

## 17. PEM không thay thế xác thực certificate hoặc key

Đọc PEM thành công không đồng nghĩa dữ liệu đáng tin cậy. Các bước kiểm tra phụ thuộc loại object:

### Với X.509 certificate

- Xác thực certificate path tới trust anchor được cấu hình.
- Kiểm tra thời hạn `notBefore`/`notAfter`.
- Kiểm tra hostname/SAN khi dùng TLS.
- Kiểm tra Key Usage, Extended Key Usage và Basic Constraints.
- Kiểm tra trạng thái thu hồi bằng CRL/OCSP nếu chính sách yêu cầu.
- Kiểm tra thuật toán chữ ký và kích thước khóa theo policy.

### Với public/private key

- Kiểm tra thuật toán và key size có được phép.
- Nếu có key pair, xác nhận public key tương ứng private key bằng thao tác kiểm chứng phù hợp.
- Bảo vệ private key bằng quyền file, secret manager hoặc HSM.
- Không ghi private key, password hoặc encoded payload nhạy cảm vào log.
- Không coi label là bằng chứng key thuộc người hoặc dịch vụ nào.

### Với CSR

Kiểm tra chữ ký proof-of-possession của CSR và xác minh các subject/extension request theo chính sách CA. PEMRecord chỉ giữ dữ liệu; nó không thực hiện kiểm tra này.

## 18. Lỗi thường gặp khi phân tích PEM

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `InvalidKeySpecException` khi tạo private key | Payload là PKCS #1/SEC1 nhưng code mong PKCS #8. | Xác định cấu trúc thực, chuyển đổi bằng công cụ/provider đáng tin cậy hoặc dùng parser tương ứng. |
| `ClassCastException` từ PEMDecoder | Class yêu cầu không khớp label/payload. | Dùng đúng kiểu đích hoặc decode tổng quát rồi kiểm tra type. |
| Decoder trả `PEMRecord` | Loại PEM chưa có Java class tương ứng. | Kiểm tra `type()` và dùng parser phù hợp; không giả định đã parse ASN.1. |
| Decode certificate thành công nhưng TLS thất bại | Certificate không đúng hostname, chain thiếu hoặc trust anchor không phù hợp. | Xác thực path, SAN, validity và trust store. |
| Sai password hoặc giải mã thất bại | Password sai, thuật toán/provider không hỗ trợ hoặc payload hỏng. | Kiểm tra nguồn password, PBE parameters và provider; không log secret. |
| `PUBLIC KEY` không đọc được | Payload không phải SubjectPublicKeyInfo hoặc key algorithm chưa hỗ trợ. | Xác định cấu trúc inner payload và provider hỗ trợ. |
| File có nhiều certificate nhưng chỉ lấy một | Một lần decode chỉ trả một đối tượng PEM. | Xử lý từng block riêng, giữ đúng thứ tự chain và xác thực đầy đủ. |
| Đổi label nhưng vẫn parse lỗi | Label đã đổi nhưng cấu trúc ASN.1 không đổi. | Chuyển đổi payload thực sự, không sửa text label. |
| File `.crt` bị hiểu sai là PEM | Phần mở rộng không xác định nội dung; file có thể là DER nhị phân. | Kiểm tra byte/file format trước khi chọn decoder. |
| PEM parse được nhưng nội dung không đáng tin | Parse chỉ kiểm tra cú pháp/kiểu, không xác minh trust. | Thực hiện kiểm tra mật mã và chính sách ở tầng ứng dụng. |

### Checklist chẩn đoán

1. Đọc chính xác BEGIN/END label.
2. Xác định cấu trúc được label đại diện: SPKI, PKCS #8, PKCS #1, SEC1, X.509 hay CSR.
3. Base64 decode và kiểm tra payload nhị phân bằng parser đúng chuẩn.
4. Xác định JDK release, provider và API preview/final đang dùng.
5. Kiểm tra decoder trả Java cryptographic object hay record tổng quát.
6. Nếu private key được mã hóa, xác minh PBE algorithm/parameters và password.
7. Sau khi parse, xác thực certificate/key theo mục đích sử dụng.

## 19. Khác biệt API PEM giữa Java 25, 26, 27 và 28

API PEM được preview nhiều lần; một số tên đã thay đổi. Đây là bảng quan trọng khi đọc ví dụ từ tài liệu hoặc thư viện ở các release khác nhau:

| JDK | JEP | Trạng thái | Tên API quan trọng |
| --- | --- | --- | --- |
| **JDK 25** | **JEP 470** | Preview lần đầu | `DEREncodable`, `PEMRecord` (record), `PEMDecoder.withFactory(...)`. |
| **JDK 26** | **JEP 524** | Preview lần hai | Tiếp tục preview; API vẫn dùng tên `DEREncodable`/`PEMRecord`. |
| **JDK 27** | **JEP 538** | Preview lần ba | `DEREncodable` đổi thành `BinaryEncodable`; `PEMRecord` đổi thành class `PEM`; `withFactory(...)` đổi thành `withFactoriesOf(...)`; có `CryptoException`. |
| **JDK 28** | **JEP 542** | API final đã tích hợp vào Early Access | Dùng `BinaryEncodable`, class `PEM`, `withFactoriesOf(...)`; không cần preview flag trong JDK 28 EA. |

### Những đổi tên cần chú ý

| Java 25/26 | Java 27/28 |
| --- | --- |
| `DEREncodable` | `BinaryEncodable` |
| `PEMRecord` | `PEM` |
| `PEMDecoder.withFactory(provider)` | `PEMDecoder.withFactoriesOf(provider)` |
| `PEMRecord` chứa Base64 `String` | `PEM` hỗ trợ content ở dạng byte và defensive copying |
| Một số lỗi runtime trả `RuntimeException` | `CryptoException` cho lỗi xử lý mật mã |

`DEREncodable` được đổi thành `BinaryEncodable` vì interface đại diện cho đối tượng có biểu diễn nhị phân chuẩn, không nên hiểu là mọi payload đều chỉ có một encoding DER. Trong JDK 28 EA, API không còn được đánh dấu preview và có thể biên dịch/chạy mà không bật `--enable-preview`.

Tại ngày 27/11/2026, JDK 28 vẫn là Early Access, chưa phải bản GA. Vì vậy:

- Khi học đúng Java 25, dùng API `DEREncodable`/`PEMRecord` và preview flags.
- Khi triển khai trên JDK 27, dùng API preview lần thứ ba và tên `BinaryEncodable`/`PEM`.
- Khi thử JDK 28 EA, dùng API final theo JEP 542; không mang `PEMRecord` hoặc `withFactory` từ Java 25 sang.
- Khi ứng dụng cần chạy trên JDK GA hiện có mà không chấp nhận preview, cân nhắc API ổn định khác hoặc thư viện PKI đang được duy trì cho đến khi PEM API final có mặt trong bản GA.

## 20. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài A — Phân tích một khối CERTIFICATE

1. Lấy một certificate thử nghiệm không chứa thông tin nhạy cảm.
2. Xác định PEM label và phần Base64.
3. Decode thành `X509Certificate` bằng PEMDecoder trên JDK 25.
4. Đọc issuer, subject, validity và public-key algorithm.
5. Giải thích vì sao parse thành công chưa có nghĩa certificate được trust.

**Đạt:** phân biệt được PEM wrapper, DER/ASN.1 Certificate và quy trình xác thực trust chain.

### Bài B — So sánh PUBLIC KEY và PRIVATE KEY

Tạo một KeyPair thử nghiệm. Encode public key và private key thành PEM. Đọc lại từng block bằng PEMDecoder; xác định cấu trúc SPKI và PKCS #8.

**Đạt:** giải thích vì sao hai block có cùng Base64 body format nhưng mang cấu trúc ASN.1 khác nhau và vì sao private key phải được bảo vệ.

### Bài C — So sánh PKCS #8 và PKCS #1

Dùng công cụ tin cậy tạo hai file RSA private key ở dạng PKCS #8 và PKCS #1. Quan sát label và cấu trúc; thử decode theo API Java 25. Ghi lại loại được hỗ trợ trực tiếp và loại cần chuyển đổi.

**Đạt:** không dùng cách đổi label bằng tay để chuyển định dạng.

### Bài D — Mã hóa private key

Dùng `PEMEncoder.withEncryption(password)` để tạo `ENCRYPTED PRIVATE KEY`. Decode với password đúng và sai trong môi trường thử nghiệm; kiểm tra lỗi được xử lý mà không log password.

**Đạt:** phân biệt Base64 với PBE encryption và hiểu `EncryptedPrivateKeyInfo`.

### Bài E — PEMRecord với CSR

Đọc một CSR bằng `PEMDecoder` và yêu cầu `PEMRecord.class`. Xem type/content/leadingData. Giải thích phần nào JDK đã xử lý và phần nào cần parser/validation PKCS #10.

**Đạt:** không coi PEMRecord là bằng chứng CSR hợp lệ.

### Bài F — Kiểm tra certificate chain

Đặt leaf và intermediate certificate trong cùng một file PEM. Xử lý từng block, xây dựng chuỗi và xác thực bằng trust anchor trong môi trường test.

**Đạt:** phân biệt nhiều PEM blocks với một ASN.1 object và không tin thứ tự file như một cơ chế xác thực.

### Câu hỏi tự kiểm tra

1. PEM wrapper gồm những thành phần nào?
2. Base64 khác DER ở vai trò nào?
3. ASN.1 mô tả dữ liệu gì và DER làm nhiệm vụ gì?
4. `PUBLIC KEY` thường chứa cấu trúc X.509 nào?
5. `PRIVATE KEY` khác `RSA PRIVATE KEY` ở cấu trúc nào?
6. Vì sao không thể đổi label PEM để chuyển PKCS #1 thành PKCS #8?
7. `CERTIFICATE` chứa thêm thông tin gì ngoài public key?
8. `ENCRYPTED PRIVATE KEY` dùng cấu trúc PKCS #8 nào?
9. PEM có tự mã hóa hoặc xác minh tính toàn vẹn dữ liệu không?
10. `PEMRecord` trong Java 25 dùng để làm gì và giới hạn gì?
11. Vì sao parse certificate thành công không đồng nghĩa certificate được trust?
12. JEP 470, 524, 538 và 542 tương ứng với các JDK nào?
13. Vì sao `DEREncodable` được đổi thành `BinaryEncodable`?
14. API PEM nào của Java 25 cần bật preview và API nào ở JDK 28 EA không cần preview?

## 21. Tài liệu tham khảo chính thức

- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468): cú pháp BEGIN/END, Base64 body, label và các cấu trúc textual encoding.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc X.509 Certificate, SubjectPublicKeyInfo và CRL.
- [RFC 5208 — PKCS #8: Private-Key Information Syntax](https://www.rfc-editor.org/rfc/rfc5208): cấu trúc PrivateKeyInfo và EncryptedPrivateKeyInfo.
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958): OneAsymmetricKey, bao gồm khả năng chứa public key cùng private key.
- [RFC 8017 — PKCS #1: RSA Cryptography Specifications](https://www.rfc-editor.org/rfc/rfc8017): cấu trúc RSA public/private key.
- [RFC 2986 — PKCS #10: Certification Request Syntax](https://www.rfc-editor.org/rfc/rfc2986): cấu trúc CSR.
- [JEP 470 — PEM Encodings (Preview)](https://openjdk.org/jeps/470): API PEM preview đầu tiên trong JDK 25.
- [PEMDecoder — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMDecoder.html): các loại PEM và cách decode.
- [PEMEncoder — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMEncoder.html): cách encode key/certificate và mã hóa private key.
- [PEMRecord — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMRecord.html): type, Base64 content và leading data.
- [DEREncodable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/DEREncodable.html): các Java cryptographic object có thể encode thành DER.
- [EncryptedPrivateKeyInfo — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): encrypted private key theo PKCS #8.
- [JCA Reference Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): hướng dẫn PEMDecoder, PEMEncoder, PEMRecord và EncryptedPrivateKeyInfo.
- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): vòng preview thứ hai trong JDK 26.
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): thay đổi API trong JDK 27.
- [JEP 542 — PEM Encodings of Cryptographic Objects](https://openjdk.org/jeps/542): hoàn thiện API trong JDK 28.
- [PEMDecoder — Java SE 28 Early Access API](https://download.java.net/java/early_access/jdk28/docs/api/java.base/java/security/PEMDecoder.html): API BinaryEncodable, PEM, withFactoriesOf và giải mã không preview.

**Ghi chú tính hiện hành:** PEM là định dạng textual wrapper vẫn được sử dụng rộng rãi. Payload bên trong phải được hiểu theo chuẩn PKIX/PKCS/CMS tương ứng. API PEM của JDK 25 (JEP 470) là preview; API đã thay đổi ở JDK 27 và được hoàn thiện trong JDK 28 theo JEP 542. Không dùng label lịch sử hoặc biến thể mã hóa private key cũ làm lựa chọn mặc định cho hệ thống mới.

**Kết quả cần nộp:** một sơ đồ ba lớp PEM/Base64/ASN.1-DER; bảng đối chiếu ít nhất `CERTIFICATE`, `PUBLIC KEY`, `PRIVATE KEY`, `ENCRYPTED PRIVATE KEY`, `RSA PRIVATE KEY`; chương trình Java 25 encode/decode một certificate và key; ví dụ xử lý `PEMRecord`; cùng phần giải thích vì sao parse PEM không thay thế xác thực certificate hoặc kiểm tra chính sách bảo vệ private key.
