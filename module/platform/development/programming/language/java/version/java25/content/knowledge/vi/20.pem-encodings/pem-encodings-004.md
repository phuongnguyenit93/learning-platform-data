# Đọc, ghi và kiểm tra tính tương thích của vật liệu mật mã giữa hệ thống

## 1. PEM giải quyết vấn đề gì?

Khi một hệ thống cần trao đổi public key, private key, certificate hoặc certificate revocation list (CRL), dữ liệu mật mã thường được lưu dưới dạng nhị phân DER. File nhị phân phù hợp cho máy xử lý nhưng khó đưa vào cấu hình, email, secret store, ticket hỗ trợ hoặc trao đổi qua kênh văn bản.

**PEM (Privacy-Enhanced Mail)** là cách biểu diễn dữ liệu nhị phân đó dưới dạng văn bản Base64, có nhãn ở đầu và cuối:

```text
-----BEGIN CERTIFICATE-----
MIIC...
...Base64 data...
-----END CERTIFICATE-----
```

Một PEM block có ba phần:

1. **Label:** loại dữ liệu, ví dụ `CERTIFICATE`, `PUBLIC KEY`, `PRIVATE KEY`.
2. **Base64 body:** mã hóa văn bản của byte sequence nhị phân.
3. **Encapsulation boundary:** hai dòng `-----BEGIN ...-----` và `-----END ...-----`.

PEM không phải thuật toán mã hóa và Base64 không bảo vệ bí mật. Nếu PEM chứa private key không mã hóa, bất kỳ ai đọc được file đều có thể lấy vật liệu khóa. Muốn bảo vệ private key cần mã hóa theo định dạng khóa được mã hóa như PKCS #8 `ENCRYPTED PRIVATE KEY`, kiểm soát quyền truy cập file và quản lý mật khẩu/secret đúng cách.

Trong Java, các API `java.security.PEMEncoder` và `PEMDecoder` cung cấp cách chuyển giữa PEM text và các đối tượng mật mã như `PublicKey`, `PrivateKey`, `X509Certificate`, `X509CRL` và `EncryptedPrivateKeyInfo`. API này được giới thiệu ở JDK 25 dưới dạng preview qua JEP 470, tiếp tục preview ở JDK 26 và JDK 27; JEP 542 được nhắm tới JDK 28 để hoàn tất API sau ba vòng preview. Tại ngày 27/11/2026, JDK 27 là bản GA mới nhất và PEM API vẫn là preview; JDK 28 đang trong giai đoạn Early Access.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt PEM text, Base64 và DER binary.
- Nhận biết label PEM thường gặp và cấu trúc nhị phân bên dưới.
- Đọc/ghi certificate, public key, private key và encrypted private key bằng API Java.
- Chọn đúng `PEMDecoder` result type và xử lý PEM type chưa được hỗ trợ.
- So sánh định dạng giữa Java, OpenSSL, hệ thống TLS và secret store.
- Kiểm tra certificate chain, key pair, thuật toán và tham số trước khi tích hợp.
- Bảo vệ private key, password, file tạm và dữ liệu log.
- Nhận biết sự thay đổi API từ JDK 25 đến JDK 27/28 để không dùng nhầm tên lớp preview cũ.

## 2. Phân biệt PEM, Base64, DER và ASN.1

Các khái niệm này thường xuất hiện cùng nhau nhưng không đồng nghĩa:

| Thành phần | Vai trò | Dạng dữ liệu |
| --- | --- | --- |
| ASN.1 | Ngôn ngữ mô tả cấu trúc dữ liệu có kiểu | Mô hình dữ liệu |
| DER | Quy tắc mã hóa ASN.1 thành byte sequence xác định | Binary |
| Base64 | Biểu diễn byte sequence thành ký tự ASCII | Text encoding |
| PEM | Base64 body + label + header/footer | Text container |

Ví dụ với public key:

```text
-----BEGIN PUBLIC KEY-----
...Base64(SPKI DER bytes)...
-----END PUBLIC KEY-----
```

Phần Base64 khi decode sẽ cho ra cấu trúc SubjectPublicKeyInfo (SPKI) được mã hóa DER. Java thường biểu diễn cấu trúc này bằng `X509EncodedKeySpec`, rồi `KeyFactory` tạo ra `PublicKey` tương ứng.

Với certificate:

```text
-----BEGIN CERTIFICATE-----
...Base64(X.509 certificate DER bytes)...
-----END CERTIFICATE-----
```

DER bytes chứa cấu trúc X.509 certificate, gồm subject, issuer, validity, public key, extensions và chữ ký của issuer. PEM chỉ là lớp văn bản bao ngoài; nó không xác nhận certificate có đáng tin hay chữ ký có hợp lệ.

### 2.1. Vì sao không nên tự xử lý PEM bằng split chuỗi tùy tiện?

Cách cắt chuỗi theo `BEGIN`/`END`, rồi gọi Base64 decoder có thể hoạt động với một file đơn giản, nhưng dễ sai khi gặp:

- File có nhiều PEM blocks nối tiếp nhau.
- Dữ liệu metadata đứng trước block PEM.
- Line ending CRLF/LF khác nhau.
- Whitespace và line wrapping.
- PEM type chưa biết hoặc không được API hỗ trợ.
- Encrypted private key cần giải mã PKCS #8.
- Input malformed, thiếu footer hoặc Base64 không hợp lệ.

Dùng `PEMDecoder` khi cần chuyển trực tiếp thành cryptographic object; dùng `PEM` object khi cần giữ một PEM block chưa có Java object tương ứng. Nếu hệ thống cần parse format đặc thù, hãy dùng parser được kiểm chứng và xác thực cấu trúc/algorithm riêng.

## 3. Các label PEM và định dạng nhị phân thường gặp

Label là một phần của hợp đồng trao đổi. Hai file có cùng Base64 body nhưng label khác nhau có thể mang ngữ nghĩa và quy tắc parse khác nhau.

| PEM label | Nội dung thường chứa | Cấu trúc nhị phân |
| --- | --- | --- |
| `CERTIFICATE` | X.509 certificate | X.509 Certificate DER |
| `X509 CRL` | Certificate Revocation List | X.509 CRL DER |
| `PUBLIC KEY` | Public key tổng quát | SubjectPublicKeyInfo (SPKI) |
| `PRIVATE KEY` | Private key không mã hóa | PKCS #8 PrivateKeyInfo / OneAsymmetricKey |
| `ENCRYPTED PRIVATE KEY` | Private key mã hóa bằng password | PKCS #8 EncryptedPrivateKeyInfo |
| `RSA PRIVATE KEY` | RSA private key dạng truyền thống | PKCS #1 RSAPrivateKey |
| `EC PRIVATE KEY` | EC private key dạng truyền thống | SEC 1 ECPrivateKey |
| `CERTIFICATE REQUEST` | Certificate Signing Request (CSR) | PKCS #10 |
| `PKCS7` / `CMS` | Gói dữ liệu ký/mã hóa | CMS / PKCS #7 |

Các label `RSA PRIVATE KEY` và `EC PRIVATE KEY` thường gặp trong file cũ hoặc công cụ cụ thể. Đối với trao đổi private key mới, ưu tiên PKCS #8 `PRIVATE KEY` hoặc `ENCRYPTED PRIVATE KEY` khi phù hợp. Không giả định mọi implementation PEMDecoder đều hỗ trợ mọi label trong bảng; API có danh sách kiểu được hỗ trợ và có thể trả về `PEM` cho loại chưa có Java cryptographic object tương ứng.

### 3.1. Những nhầm lẫn dễ gây lỗi tích hợp

- `PUBLIC KEY` thường là SPKI; `RSA PUBLIC KEY` thường là cấu trúc PKCS #1 riêng. Không đổi label mà không chuyển đổi DER.
- `PRIVATE KEY` là PKCS #8; `RSA PRIVATE KEY` thường là PKCS #1. Đổi tên file không biến PKCS #1 thành PKCS #8.
- `ENCRYPTED PRIVATE KEY` là PKCS #8 đã mã hóa; không phải PEM body Base64 được mã hóa tùy ý.
- `CERTIFICATE` là certificate; `CERTIFICATE REQUEST` là CSR chờ CA ký. CSR không phải certificate đã được cấp.
- Certificate chain có thể gồm nhiều `CERTIFICATE` blocks; thứ tự, trust anchor và policy xác thực vẫn phải được kiểm tra.

### 3.2. Chuẩn hiện hành cần biết

- **RFC 7468** mô tả textual encoding của các cấu trúc PKIX, PKCS và CMS, gồm nhãn và cách đóng gói PEM.
- **RFC 5280** định nghĩa hồ sơ X.509 PKI certificate và CRL.
- **RFC 5958** định nghĩa Asymmetric Key Packages (OneAsymmetricKey), được PKCS #8 v2.0 sử dụng.
- **RFC 5208** mô tả PKCS #8 Private-Key Information Syntax phiên bản cũ; khi trao đổi mới cần hiểu cấu trúc PKCS #8 hiện hành và hỗ trợ của hệ thống nhận.

Không dùng các quy ước mã hóa private key kiểu PEM truyền thống với header `Proc-Type`/`DEK-Info` làm định dạng mới mặc định. Ưu tiên encrypted PKCS #8 và kiểm tra rõ thuật toán mã hóa/password-based encryption được hai bên hỗ trợ.

## 4. Trạng thái API PEM trong các phiên bản Java

API Java PEM đã thay đổi tên và mô hình dữ liệu qua các vòng preview:

| JDK | JEP | Thay đổi chính |
| --- | --- | --- |
| JDK 25 | JEP 470 — Preview đầu tiên | `DEREncodable`, `PEMRecord`, `PEMEncoder`, `PEMDecoder` |
| JDK 26 | JEP 524 — Preview thứ hai | Điều chỉnh API; `PEM` được phát triển theo hướng biểu diễn PEM chưa có Java object tương ứng |
| JDK 27 | JEP 538 — Preview thứ ba | `DEREncodable` đổi thành `BinaryEncodable`; `PEMRecord` đổi thành `PEM`; bổ sung/chuẩn hóa xử lý `CryptoException` và provider factory |
| JDK 28 | JEP 542 — Finalization được nhắm tới | Hoàn tất API sau ba vòng preview; JDK 28 Early Access đã có bản thử nghiệm dùng PEM API không cần preview flag |

**Mốc thực hành cho bản GA mới nhất hiện nay là JDK 27.** Các ví dụ API trong bài dùng tên `BinaryEncodable`, `PEM`, `withFactoriesOf` và `CryptoException` của JDK 27. Khi dùng JDK 27, phải bật preview ở compile và run. JDK 28 chưa GA tại ngày 27/11/2026; JEP 542 đã được nhắm tới JDK 28 để hoàn tất tính năng. Hãy xác nhận API trên JDK 28 GA khi nâng cấp production, không lấy một bản EA làm runtime triển khai chính thức.

### 4.1. Vì sao tên DEREncodable được thay bằng BinaryEncodable?

PEM không chỉ chứa những đối tượng có một API DER cụ thể. Nó có thể mang các cấu trúc nhị phân chuẩn khác và những loại dữ liệu chưa có Java class tương ứng. `BinaryEncodable` mô tả tổng quát hơn khả năng biểu diễn đối tượng thành binary form để đưa vào PEM.

### 4.2. Vì sao PEMRecord được thay bằng PEM?

Ở JDK 25, `PEMRecord` là record chứa `type`, Base64 `content` dạng String và `leadingData`. Từ JDK 26/27, `PEM` trở thành class đại diện một PEM structure, lưu content ở dạng byte array và hỗ trợ truy cập decoded bytes. Mô hình mới có thể bảo vệ dữ liệu tốt hơn qua việc sao chép mảng byte ở biên API.

Không viết code mới trên JDK 27 bằng `PEMRecord` hoặc `DEREncodable`; đó là tên từ preview đầu tiên của JDK 25. Nếu duy trì code đã thử nghiệm bằng JDK 25, hãy xem đây là điểm migration cần thay đổi khi chuyển lên JDK 27.

## 5. Đọc certificate và public key bằng PEMDecoder

`PEMDecoder` nằm trong package `java.security`. Dùng overload có `Class` để yêu cầu kiểu Java cụ thể, tránh cast thủ công và phát hiện sớm khi label/body không tương ứng với kiểu mong muốn.

### 5.1. Đọc X.509 certificate

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

String pemText = Files.readString(Path.of("server-cert.pem"));
X509Certificate certificate =
        PEMDecoder.of().decode(pemText, X509Certificate.class);

System.out.println(certificate.getSubjectX500Principal());
System.out.println(certificate.getIssuerX500Principal());
System.out.println(certificate.getNotBefore());
System.out.println(certificate.getNotAfter());
```

Khi cần nhiều certificate blocks, đọc từng block theo contract của file hoặc dùng API stream/parser thích hợp. Không giả định một lần `decode(String)` sẽ trả về toàn bộ chain như một collection.

### 5.2. Đọc public key

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PublicKey;

String pemText = Files.readString(Path.of("server-public-key.pem"));
PublicKey publicKey =
        PEMDecoder.of().decode(pemText, PublicKey.class);

System.out.println(publicKey.getAlgorithm());
System.out.println(publicKey.getFormat());
```

Với PEM `PUBLIC KEY`, decoder trả về `PublicKey` nếu thuật toán được provider/runtime hỗ trợ. Nếu cần dữ liệu SPKI để tự tạo key qua `KeyFactory`, có thể yêu cầu `X509EncodedKeySpec.class`.

### 5.3. Đọc private key không mã hóa

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;

String pemText = Files.readString(Path.of("service-private-key.pem"));
PrivateKey privateKey =
        PEMDecoder.of().decode(pemText, PrivateKey.class);

System.out.println(privateKey.getAlgorithm());
System.out.println(privateKey.getFormat());
```

Đọc private key là thao tác nhạy cảm. Không in object key, `getEncoded()` hoặc PEM text ra log; không ghi dữ liệu vào exception message, tracing attribute hoặc telemetry. Đọc từ secret store hoặc file với quyền truy cập tối thiểu, giới hạn thời gian giữ bản sao trong bộ nhớ và không tạo bản copy không cần thiết.

### 5.4. Đọc PEM chưa có kiểu Java tương ứng

Nếu label không được API ánh xạ thành cryptographic class, decoder trả về `PEM`. Có thể yêu cầu rõ `PEM.class`:

```java
import java.security.PEM;
import java.security.PEMDecoder;

PEM pem = PEMDecoder.of().decode(pemText, PEM.class);

System.out.println(pem.type());
byte[] binaryContent = pem.decode();
byte[] leadingData = pem.leadingData();
```

`PEM` giữ type identifier và Base64 content; `decode()` trả byte sequence sau Base64 decoding. `leadingData()` chứa dữ liệu văn bản đứng trước PEM header nếu có. Đây là cách giữ một block chưa được Java API hỗ trợ để chuyển tiếp hoặc xử lý bằng parser chuyên biệt.

**Quan trọng:** `PEM` là container, không phải validator. Không có bảo đảm rằng `type` khớp với ASN.1 structure trong content, rằng dữ liệu là một key hợp lệ hay rằng certificate đáng tin. Cần parser/validation ở lớp tiếp theo.

### 5.5. Chọn provider cho KeyFactory và CertificateFactory

Nếu môi trường triển khai yêu cầu provider cụ thể, có thể tạo decoder mới với `withFactoriesOf(Provider)`. Provider được chọn phải cung cấp các factory cần thiết cho loại key/certificate mà ứng dụng đọc:

```java
import java.security.PEMDecoder;
import java.security.Provider;
import java.security.cert.X509Certificate;

Provider cryptoProvider = resolveApprovedProvider();
PEMDecoder decoder = PEMDecoder.of().withFactoriesOf(cryptoProvider);
X509Certificate certificate =
        decoder.decode(pemText, X509Certificate.class);
```

`withFactoriesOf` áp dụng cho `KeyFactory` và `CertificateFactory` khi decoder tạo cryptographic objects. Chỉ chỉ định provider khi deployment policy yêu cầu; kiểm tra provider có hỗ trợ cả factory và algorithm cụ thể. Đây không phải tùy chọn thay thế việc chọn provider cho mọi API mật mã khác trong ứng dụng.

## 6. Ghi certificate, public key và private key bằng PEMEncoder

`PEMEncoder` chuyển cryptographic object thành PEM text hoặc byte array. Ví dụ ghi public key:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMEncoder;

KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(3072);
KeyPair pair = generator.generateKeyPair();

String publicPem = PEMEncoder.of().encodeToString(pair.getPublic());
Files.writeString(
        Path.of("service-public-key.pem"),
        publicPem,
        StandardCharsets.US_ASCII);
```

Với certificate hoặc CRL đã có:

```java
String certificatePem = PEMEncoder.of().encodeToString(certificate);
Files.writeString(
        Path.of("service-certificate.pem"),
        certificatePem,
        StandardCharsets.US_ASCII);

byte[] crlPem = PEMEncoder.of().encode(crl);
Files.write(Path.of("revocation-list.pem"), crlPem);
```

PEM là định dạng văn bản ASCII. Khi ghi file, chọn charset ASCII/US-ASCII để biểu đạt rõ đây là dữ liệu văn bản chuẩn; không chuyển PEM thành UTF-16 hoặc một encoding tùy ý. Khi trao đổi qua API HTTP, xác định charset và content type trong hợp đồng giao tiếp.

### 6.1. Ghi private key không mã hóa

Có thể encode `PrivateKey` trực tiếp:

```java
byte[] privatePem = PEMEncoder.of().encode(privateKey);
Files.write(Path.of("service-private-key.pem"), privatePem);
```

Kết quả có label `PRIVATE KEY`, thường là PKCS #8. Đây là private key plaintext trong file PEM. Chỉ làm vậy khi storage đã được bảo vệ bằng cơ chế phù hợp, quyền file tối thiểu và quy trình secret management đã được xác định.

Không đưa file private key plaintext vào source repository, Docker image layer, artifact public, issue tracker hoặc log CI. Xóa file tạm không bảo đảm mọi bản sao trên filesystem, snapshot hoặc backup đã biến mất.

### 6.2. Ghi KeyPair

JDK PEM API có thể encode `KeyPair` thành cấu trúc OneAsymmetricKey theo PKCS #8 v2.0, dùng label `PRIVATE KEY`. Cấu trúc này có thể mang cả private key và public key tương ứng.

```java
String keyPairPem = PEMEncoder.of().encodeToString(pair);
```

Không phải hệ thống nhận nào cũng sử dụng public key component đi kèm. Nếu đối tác yêu cầu một loại private key cụ thể, hãy thống nhất label và binary structure trong hợp đồng thay vì chỉ dựa vào việc cả hai phía đều đọc được PEM.

### 6.3. Dùng PEM cho type chưa được hỗ trợ

Khi cần ghi một PEM type mà Java API chưa có cryptographic class tương ứng, có thể dùng `PEM`:

```java
import java.security.PEM;
import java.security.PEMEncoder;

PEM custom = new PEM(
        "CERTIFICATE REQUEST",
        base64EncodedDerBytes);

String pemText = PEMEncoder.of().encodeToString(custom);
```

Đầu vào `base64EncodedDerBytes` ở ví dụ là **Base64 bytes**, không phải DER bytes thô. `PEM` là container cho type và content; API không xác minh nội dung có thật sự là CSR hợp lệ hay không. Hãy để parser PKCS #10 hoặc CA client kiểm tra cấu trúc và chữ ký của CSR.

## 7. Đọc và ghi private key được mã hóa

Private key cần được bảo vệ khi lưu trữ hoặc chuyển qua kênh không đáng tin cậy. PKCS #8 encrypted private key dùng PEM label `ENCRYPTED PRIVATE KEY`.

### 7.1. Mã hóa khi ghi bằng password

`PEMEncoder.withEncryption(char[])` tạo một encoder được cấu hình mã hóa private key:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMEncoder;
import java.util.Arrays;

char[] password = obtainPasswordFromSecretStore();

try {
    PEMEncoder encryptedEncoder =
            PEMEncoder.of().withEncryption(password);

    byte[] encryptedPem = encryptedEncoder.encode(privateKey);
    Files.write(Path.of("service-private-key-encrypted.pem"), encryptedPem);
} finally {
    Arrays.fill(password, '\0');
}
```

Trong JDK 27, `withEncryption` hỗ trợ `PrivateKey`, `KeyPair` và `PKCS8EncodedKeySpec`. Nếu truyền object khác, API có thể ném `IllegalArgumentException`. Password được clone khi cấu hình encoder; xóa mảng password phía caller sau khi dùng vẫn là thực hành tốt, dù không thể bảo đảm mọi bản sao trong runtime/provider đã bị xóa.

`withEncryption` dùng thuật toán mã hóa mặc định. Security property `jdk.epkcs8.defaultAlgorithm` và mặc định `AlgorithmParameterSpec` của provider ảnh hưởng thuật toán/parameters. Vì vậy, không giả định hai JDK vendor hoặc provider khác nhau luôn sinh cùng cấu hình encrypted PKCS #8. Nếu yêu cầu thuật toán và parameters cố định theo policy, hãy cấu hình rõ qua các overload `EncryptedPrivateKeyInfo.encrypt(...)` và kiểm tra provider hỗ trợ.

### 7.2. Giải mã private key

`PEMDecoder.withDecryption(char[])` tạo decoder có thể giải mã encrypted private key:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.util.Arrays;

char[] password = obtainPasswordFromSecretStore();

try {
    String encryptedPem = Files.readString(
            Path.of("service-private-key-encrypted.pem"));

    PEMDecoder decoder = PEMDecoder.of().withDecryption(password);
    PrivateKey privateKey =
            decoder.decode(encryptedPem, PrivateKey.class);

    // Dùng privateKey trực tiếp với Signature, Cipher hoặc KeyAgreement.
} finally {
    Arrays.fill(password, '\0');
}
```

Nếu encrypted PEM được đọc bằng decoder không cấu hình decryption, kết quả là `EncryptedPrivateKeyInfo`, cho phép ứng dụng kiểm tra metadata thuật toán và quyết định bước giải mã tiếp theo. Khi decoder đã cấu hình decryption, nó có thể đọc cả encrypted lẫn unencrypted PEM.

### 7.3. Phân biệt lỗi định dạng và lỗi mật mã

Một số lỗi có thể xảy ra:

- Không tìm thấy PEM header hoặc body bị hỏng: lỗi parse/argument.
- Label không tương thích với class yêu cầu: `ClassCastException`.
- Password sai hoặc cryptographic processing thất bại: `CryptoException` trong preview API.
- Provider không hỗ trợ thuật toán/parameters: lỗi cryptographic processing hoặc lỗi provider tương ứng.
- File bị cắt hoặc I/O thất bại: `IOException`/`EOFException` với overload stream.

Không bắt mọi exception rồi báo “invalid PEM”. Ghi nhận loại lỗi kỹ thuật ở mức an toàn, nhưng không ghi password, private key, PEM body hay plaintext DER vào log.

### 7.4. Không xem password encryption là thay thế key management

Mã hóa PKCS #8 bằng password bảo vệ file khi lưu/chuyển, nhưng không thay thế:

- Secret manager hoặc HSM để cấp phát và kiểm soát key.
- Quy trình rotation, revocation và phân quyền.
- Bảo vệ password khỏi source code và environment dump.
- Kiểm soát quyền truy cập file, backup và snapshot.
- TLS hoặc secure channel khi truyền dữ liệu.

Password yếu có thể bị đoán ngoại tuyến nếu kẻ tấn công lấy được encrypted private key. Chọn password đủ mạnh và encryption parameters theo chính sách bảo mật hiện hành; không dùng mật khẩu mặc định hoặc hard-code password.

### 7.5. Khi cần encryption parameters tường minh

`EncryptedPrivateKeyInfo.encrypt` có overload nhận `BinaryEncodable`, password, thuật toán, `AlgorithmParameterSpec` và provider. Dùng cách này khi policy yêu cầu kiểm soát thuật toán/parameters thay vì dùng mặc định của `PEMEncoder`:

```java
EncryptedPrivateKeyInfo encrypted = EncryptedPrivateKeyInfo.encrypt(
        privateKey,
        password,
        approvedPbeAlgorithm,
        approvedParameters,
        approvedProvider);

String encryptedPem = PEMEncoder.of().encodeToString(encrypted);
```

`approvedPbeAlgorithm`, `approvedParameters` và `approvedProvider` phải được chọn theo security policy và khả năng tương thích của peer. Test giải mã file bằng đúng JDK/provider dự kiến của bên nhận; đừng tự đặt thuật toán yếu hoặc tự chế scheme mã hóa.

## 8. Kiểm tra tính tương thích giữa các hệ thống

Một PEM file đọc được không có nghĩa hai hệ thống đã tương thích về mặt mật mã. Cần kiểm tra nhiều lớp.

### 8.1. Ma trận tương thích

| Lớp | Cần thống nhất | Ví dụ lỗi |
| --- | --- | --- |
| Text container | PEM label, line ending, charset, số block | Java nhận `PUBLIC KEY` nhưng hệ thống kia gửi `RSA PUBLIC KEY` |
| Binary structure | SPKI, PKCS #8, PKCS #1, SEC 1, X.509, CRL | Đổi label mà không chuyển DER |
| Algorithm | RSA, EC, Ed25519, X25519 và OID tương ứng | Runtime không có provider hỗ trợ thuật toán |
| Parameters | RSA key size, EC named curve, algorithm parameters | EC key dùng curve mà peer không hỗ trợ |
| Key usage | Signing, key agreement, encryption | Dùng keyAgreement key cho chữ ký |
| Certificate | Issuer, subject, validity, SAN, KU, EKU, extensions | Certificate hết hạn hoặc hostname không khớp |
| Trust | Trust anchor, chain, revocation policy | Parse thành công nhưng chain không được tin cậy |
| Encryption | PKCS #8 encryption scheme, KDF, cipher, parameters | Peer không hỗ trợ thuật toán encrypted private key |

Trước khi tích hợp, lập một contract cho từng file: PEM label, binary structure, thuật toán, parameters, encoding và mục đích sử dụng. Không chỉ ghi “file PEM” vì thông tin đó chưa đủ.

### 8.2. Kiểm tra key algorithm và encoding

Sau khi decode, xem metadata không nhạy cảm:

```java
System.out.println(publicKey.getAlgorithm());
System.out.println(publicKey.getFormat());  // thường là X.509
System.out.println(privateKey.getAlgorithm());
System.out.println(privateKey.getFormat()); // thường là PKCS#8
```

`getAlgorithm()` và `getFormat()` hữu ích cho kiểm tra tương thích, nhưng không thay thế xác minh cryptographic operation. Một key có thể được parse thành công nhưng provider không hỗ trợ thuật toán cần dùng trong protocol.

### 8.3. Xác nhận public key khớp private key

Không thể kết luận một cặp key khớp nhau chỉ vì chúng cùng thuật toán hoặc cùng tên file. Một cách tổng quát là ký một challenge ngẫu nhiên bằng private key và xác minh bằng public key tương ứng. Chọn signature algorithm tương thích với loại key và policy của hệ thống:

```java
byte[] challenge = new byte[32];
new java.security.SecureRandom().nextBytes(challenge);

java.security.Signature signature =
        java.security.Signature.getInstance("SHA256withRSA");

signature.initSign(privateKey);
signature.update(challenge);
byte[] signed = signature.sign();

signature.initVerify(publicKey);
signature.update(challenge);

if (!signature.verify(signed)) {
    throw new java.security.GeneralSecurityException(
            "Public key does not match private key");
}
```

Ví dụ dùng RSA và `SHA256withRSA`. Với EC hoặc EdDSA, chọn signature algorithm tương ứng; không hard-code RSA algorithm cho mọi key. Challenge chỉ dùng trong bộ nhớ, không log private key hoặc signature material nhạy cảm.

### 8.4. Certificate parse thành công không có nghĩa certificate đáng tin

`PEMDecoder` tạo `X509Certificate`, nhưng không tự xác nhận certificate chain được trust store tin cậy hoặc certificate phù hợp hostname/use case. Ứng dụng phải kiểm tra:

- Thời gian hiệu lực (`notBefore`, `notAfter`).
- Subject Alternative Name (SAN) với hostname cần xác thực.
- Key Usage và Extended Key Usage (EKU).
- Chain từ leaf certificate đến trust anchor.
- Chữ ký certificate, algorithm constraints và policy.
- Revocation theo OCSP/CRL nếu policy yêu cầu.

Trong TLS, để SSL/TLS trust manager và PKIX validation thực hiện xác thực theo trust store/policy; không dùng riêng `certificate.getSubjectX500Principal()` làm căn cứ tin cậy.

## 9. Certificate chain, CRL và PKIX validation

Một PEM bundle có thể chứa nhiều certificate blocks nối tiếp nhau. Java `CertificateFactory` là API ổn định để đọc certificate/CRL và tạo `CertPath`; việc đọc PEM thành `X509Certificate` vẫn khác với việc xác thực trust chain.

### 9.1. Đọc nhiều certificate trong một bundle

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.util.Collection;

CertificateFactory factory = CertificateFactory.getInstance("X.509");

try (InputStream input = Files.newInputStream(Path.of("chain.pem"))) {
    Collection<? extends Certificate> certificates =
            factory.generateCertificates(input);

    System.out.println("Certificates: " + certificates.size());
}
```

`generateCertificates` đọc collection certificate được hỗ trợ bởi provider, phù hợp với file bundle có nhiều certificate. Kiểm tra thứ tự và vai trò từng certificate sau khi parse; không lấy certificate đầu tiên làm trust anchor chỉ vì nó xuất hiện đầu file.

### 9.2. Xác thực chain với PKIX

Một certificate có thể parse thành công nhưng vẫn hết hạn, bị thu hồi, sai hostname, sai EKU hoặc không nối được tới trust anchor. Khi cần xác thực path, dùng PKIX với trust anchors được quản lý độc lập:

```java
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

CertificateFactory factory = CertificateFactory.getInstance("X.509");

// chain theo thứ tự target/leaf -> intermediate CA.
CertPath path = factory.generateCertPath(List.of(leaf, intermediate));

Set<TrustAnchor> trustAnchors = Set.of(
        new TrustAnchor(trustedRoot, null));

PKIXParameters parameters = new PKIXParameters(trustAnchors);
parameters.setRevocationEnabled(true);

CertPathValidator.getInstance("PKIX").validate(path, parameters);
```

Đây là khung minh họa; trong ứng dụng thật cần cấu hình revocation checker/OCSP/CRL, algorithm constraints, policy và hostname verification theo giao thức. Root CA/trust anchor phải đến từ trust store được quản trị; không tin root certificate chỉ vì nó nằm cạnh leaf certificate trong PEM bundle.

### 9.3. Đọc CRL không đồng nghĩa đã kiểm tra revocation

Có thể đọc CRL bằng `CertificateFactory` hoặc `PEMDecoder` nếu implementation hỗ trợ `X509 CRL`. Sau đó vẫn cần kiểm tra issuer, chữ ký CRL, thời gian hiệu lực, CRL number/delta CRL và trạng thái certificate theo policy. Một file CRL parse được chưa chứng minh nó được phát hành bởi CA đáng tin.

## 10. Xử lý stream, nhiều block và dữ liệu đứng trước PEM

### 10.1. Chọn String hay InputStream

Dùng `decode(String)` khi PEM text đã nằm trong bộ nhớ; dùng `decode(InputStream)` khi đọc file hoặc stream. Input của String được diễn giải UTF-8. API stream đọc đến PEM footer hoặc hết stream; nếu có I/O error, vị trí stream có thể không còn nhất quán, vì vậy không nên tiếp tục decode trên stream đó.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PublicKey;

try (InputStream input = Files.newInputStream(Path.of("public-key.pem"))) {
    PublicKey key = PEMDecoder.of().decode(input, PublicKey.class);
}
```

Đừng dùng lại một stream đã gặp lỗi decode/I/O. Nếu cần xử lý nhiều block, hãy xác định rõ cách phân tách và thứ tự trong hợp đồng bundle; với certificate bundle, cân nhắc `CertificateFactory.generateCertificates`.

### 10.2. Dữ liệu đứng trước PEM header

Theo API decoder, non-PEM text trước PEM header có thể bị bỏ qua khi decode thành cryptographic object. Nếu cần giữ phần đó, yêu cầu `PEM.class`:

```java
PEM pem = PEMDecoder.of().decode(bundleText, PEM.class);
byte[] leadingData = pem.leadingData();
```

`leadingData` có thể chứa metadata/ghi chú kèm theo bundle. Không coi nội dung này là dữ liệu đã xác thực; chỉ xử lý theo một format metadata được định nghĩa riêng. Khi decode thành `PublicKey`, `PrivateKey` hoặc certificate, leading data không được trả kèm với cryptographic object.

### 10.3. Không giả định decoder xử lý toàn bộ file như một collection

Các overload `decode` trả về một `BinaryEncodable` cho một PEM item. Nếu file chứa public key, private key, certificate chain và CRL, cần xử lý từng item theo cấu trúc bundle hoặc dùng API phù hợp với collection certificate. Không cast kết quả đơn lẻ thành `List` hoặc giả định mọi block được tự động ghép thành chain.

## 11. Tương thích với OpenSSL và các hệ thống khác

Java PEM API được thiết kế để làm việc với các định dạng phổ biến như PKCS #8, X.509 và CRL. Tuy nhiên, hai hệ thống phải thống nhất cả PEM label lẫn binary structure và algorithm parameters.

### 11.1. Một số lệnh OpenSSL hữu ích

Xem thông tin certificate:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates
```

Kiểm tra private key:

```bash
openssl pkey -in service-private-key.pem -check -noout
```

Xuất public key từ private key:

```bash
openssl pkey -in service-private-key.pem -pubout -out service-public-key.pem
```

Xác minh certificate với CA bundle:

```bash
openssl verify -CAfile trusted-ca.pem server-cert.pem
```

Nếu private key được mã hóa, OpenSSL có thể yêu cầu passphrase qua terminal. Tránh đưa password trực tiếp vào command line vì process listing, shell history và CI logs có thể làm lộ secret.

### 11.2. Kiểm tra format trước khi chuyển giao

Khi hệ thống đối tác báo “unsupported key”, hãy hỏi cụ thể:

- PEM label là `PUBLIC KEY`, `RSA PUBLIC KEY`, `PRIVATE KEY`, `RSA PRIVATE KEY`, `EC PRIVATE KEY` hay `ENCRYPTED PRIVATE KEY`?
- Body là SPKI, PKCS #8, PKCS #1 hay SEC 1?
- Thuật toán là RSA, EC, Ed25519, X25519 hay loại khác?
- Nếu EC, curve/OID nào?
- Nếu encrypted PKCS #8, encryption algorithm, KDF, salt/iteration/parameters nào?
- Certificate có chain, SAN, KU/EKU và issuer như mong đợi không?

Không giải quyết lỗi bằng cách đổi tên label trong file. Nếu cấu trúc DER không khớp label, phải chuyển đổi bằng công cụ hiểu cấu trúc ASN.1/PKCS tương ứng.

### 11.3. Dùng JCA ổn định khi PEM API chưa sẵn sàng

PEM API trong JDK 27 vẫn là preview. Nếu dự án không thể bật preview, vẫn có thể dùng các API JCA ổn định sau khi có DER bytes được trích xuất bằng parser PEM đáng tin cậy:

```java
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

// derSpki và derPkcs8 phải là DER bytes đã được parser PEM chuẩn
// trích xuất và kiểm tra label tương ứng.
PublicKey publicKey = KeyFactory.getInstance("RSA")
        .generatePublic(new X509EncodedKeySpec(derSpki));

PrivateKey privateKey = KeyFactory.getInstance("RSA")
        .generatePrivate(new PKCS8EncodedKeySpec(derPkcs8));
```

Đây là phần chuyển đổi DER thành key object; nó **không phải parser PEM hoàn chỉnh**. Không tự cắt header/footer bằng một regex đơn giản cho production nếu cần xử lý bundles, metadata, line ending hoặc legacy formats. Có thể dùng thư viện PEM/ASN.1 đã được đánh giá theo dependency policy của tổ chức, hoặc nâng lên JDK có PEM API đã hoàn tất.

## 12. Build, preview flags và tương thích JDK

### 12.1. Dùng API PEM trên JDK 27 GA

Trong JDK 27, JEP 538 đưa PEM API vào preview lần thứ ba. Cần bật preview ở cả compile và runtime:

```bash
javac --enable-preview --release 27 -d out src/PemExample.java
java --enable-preview -cp out PemExample
```

`--release 27` chọn ngôn ngữ/API target JDK 27; `--enable-preview` bật preview feature của chính release đó. Class file được biên dịch với preview phải chạy bằng JVM của cùng release và bật preview. Không xem preview bytecode JDK 27 là artifact tương thích với JDK 25 hoặc JDK 28.

### 12.2. Khác biệt từ JDK 25 đến JDK 27

| Nội dung | JDK 25 preview | JDK 27 preview |
| --- | --- | --- |
| Interface | `DEREncodable` | `BinaryEncodable` |
| Raw PEM container | `PEMRecord` | `PEM` |
| Content | Base64 `String` trong record | Base64 bytes trong class |
| Provider factory | API preview ban đầu | `withFactoriesOf(Provider)` |
| Cryptographic processing failure | Lỗi theo API/provider | Có `CryptoException` preview |
| Compile/run | `--enable-preview --release 25` | `--enable-preview --release 27` |

Nếu nâng code từ JDK 25 lên JDK 27, cập nhật imports, interface type, raw PEM representation và method provider. Không chỉ đổi `--release`; API đã thay đổi.

### 12.3. JDK 28 và JEP 542

JEP 542 được nhắm tới JDK 28 để hoàn tất PEM API sau ba preview. JDK 28 Early Access hiện đã có build thể hiện API không cần `--enable-preview`; tuy nhiên JDK 28 chưa GA tại ngày 27/11/2026. Trước khi phát hành production, dùng JDK 28 GA và tài liệu Java SE 28 cuối cùng để xác nhận API, behavior và compatibility. Không triển khai production bằng Early Access chỉ vì API đã được finalization target.

### 12.4. Tránh trộn class file preview giữa các release

Preview feature gắn với release cụ thể. Ví dụ, code PEM compile bằng JDK 27 với `--enable-preview` không nên đóng gói như thư viện dùng chung cho ứng dụng chạy JDK 25 hoặc JDK 28. Khi thư viện cần hỗ trợ nhiều JDK, cân nhắc:

- Dùng API JCA ổn định và một parser PEM tương thích trên toàn bộ dải JDK.
- Tách implementation theo JDK release bằng multi-release JAR nếu thực sự cần.
- Nâng baseline JDK tới release có API PEM final khi JDK 28 GA.
- Không yêu cầu toàn bộ ứng dụng bật preview chỉ để một module nhỏ đọc PEM.

## 13. Chẩn đoán lỗi khi trao đổi PEM

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` khi decode | Không có PEM block, header/footer sai hoặc Base64 body hỏng | Kiểm tra label, encapsulation boundary, body và line ending |
| `ClassCastException` | Yêu cầu class không khớp PEM type | Dùng đúng `Class` parameter hoặc decode thành `PEM.class` để kiểm tra type |
| Decoder trả về `PEM` thay vì `PrivateKey` | PEM label/format chưa được API hỗ trợ hoặc không có cryptographic class tương ứng | Kiểm tra binary format; chuyển sang PKCS #8 nếu phù hợp hoặc dùng parser được đánh giá |
| `Unrecognized algorithm`/provider error | JDK/provider không hỗ trợ algorithm OID hoặc curve | Kiểm tra `getAlgorithm()`, provider và algorithm constraints |
| Private key không giải mã được | Password sai, encryption scheme không hỗ trợ hoặc parameters không tương thích | Kiểm tra password source, `EncryptedPrivateKeyInfo` algorithm/parameters và provider |
| `PEM` content decode được nhưng key parse thất bại | Container Base64 hợp lệ nhưng DER/ASN.1 hoặc label không hợp lệ | Validate DER và type bằng parser phù hợp; Base64 decode không xác thực cấu trúc |
| Java đọc được, đối tác không đọc được | Label, PKCS format, algorithm hoặc key parameters không tương thích | So sánh contract PEM/DER và test round-trip với tool của đối tác |
| Chỉ đọc được một phần bundle | API decode một PEM item, không tự động tạo collection mọi loại | Dùng parser/bundle contract; certificate collection có thể dùng `CertificateFactory` |
| Certificate hợp lệ về cú pháp nhưng bị từ chối | Hết hạn, revoked, sai hostname, thiếu intermediate hoặc không trusted | Thực hiện PKIX validation, revocation check và hostname verification |

### 13.1. Phân biệt các tầng xác thực

Một pipeline an toàn có nhiều bước độc lập:

1. **Text syntax:** PEM boundary và Base64 có hợp lệ không?
2. **Binary syntax:** DER/ASN.1 có đúng cấu trúc theo label không?
3. **Cryptographic object:** key/certificate có parse được bởi provider không?
4. **Key compatibility:** algorithm/parameters có tương thích với hệ thống và protocol không?
5. **Trust and policy:** certificate chain, hostname, EKU, revocation và policy có hợp lệ không?
6. **Protocol behavior:** TLS/signature/key agreement có hoạt động với peer thật không?

Thành công ở một tầng không chứng minh các tầng sau cũng thành công. Ví dụ, PEM parse được không chứng minh certificate trusted; `X509Certificate.verify()` kiểm tra chữ ký certificate với public key issuer nhưng không thay thế PKIX path validation.

### 13.2. Các API PEM có thể dùng chung giữa threads

Trong JDK 27, `PEMEncoder` và `PEMDecoder` là immutable và thread-safe. Các phương thức cấu hình như `withEncryption`, `withDecryption` và `withFactoriesOf` trả về instance mới được cấu hình. Có thể tái sử dụng instance mặc định cho thao tác không cấu hình; không chia sẻ password hoặc key material mutable giữa request nếu không có lý do rõ ràng.

## 14. Tình huống thực hành: tích hợp certificate và private key cho service HTTPS

### 14.1. Bối cảnh

Một service Java cần cấu hình HTTPS từ ba file:

- `server-cert.pem`: leaf X.509 certificate.
- `intermediate-ca.pem`: intermediate CA certificate.
- `server-key-encrypted.pem`: encrypted PKCS #8 private key.

Mục tiêu là đọc vật liệu, kiểm tra private key khớp public key của certificate, xác thực certificate path với trust anchors, sau đó dùng key/certificate trong `KeyManager` để tạo TLS context.

### 14.2. Các bước thực hiện

1. Đọc certificate bằng `PEMDecoder` hoặc `CertificateFactory`.
2. Đọc encrypted private key với `PEMDecoder.of().withDecryption(password)`.
3. Kiểm tra thời gian hiệu lực và SAN theo hostname service.
4. Kiểm tra public key trong certificate khớp private key bằng sign/verify challenge.
5. Tạo `CertPath` từ leaf và intermediate theo thứ tự.
6. Xác thực path bằng `CertPathValidator` với trust anchor lấy từ trust store.
7. Tạo keystore tạm trong bộ nhớ hoặc dùng keystore được quản lý; không ghi private key plaintext ra file trung gian nếu không cần.
8. Khởi tạo `KeyManagerFactory`/`SSLContext` theo TLS policy của ứng dụng.
9. Chạy integration test từ client độc lập, kiểm tra hostname, chain và protocol.
10. Ghi nhận version, key algorithm, certificate fingerprint, expiry và trust result; không ghi PEM/private key.

### 14.3. Kiểm thử tương thích với đối tác

Chuẩn bị bộ fixture test không chứa private key production:

- RSA PKCS #8 private key + SPKI public key.
- EC PKCS #8 private key + SPKI public key với curve được thống nhất.
- X.509 leaf + intermediate chain.
- Encrypted PKCS #8 với password test.
- PEM type chưa hỗ trợ để kiểm tra fallback `PEM`.
- Input malformed: thiếu footer, Base64 sai, label không khớp binary structure.

Chạy cùng fixture qua JDK đang dùng, OpenSSL và parser của đối tác. So sánh algorithm, key parameters, certificate fingerprint và kết quả sign/verify; đừng so sánh byte-for-byte giữa hai PEM encoder nếu khác line wrapping hoặc newline convention nhưng binary DER tương đương.

## 15. Checklist và nguồn tham khảo

### 15.1. Checklist trước khi đọc PEM

- [ ] Biết file có một block hay nhiều blocks.
- [ ] Xác định PEM label và binary format tương ứng.
- [ ] Xác nhận JDK/vendor/provider có hỗ trợ loại key/certificate cần đọc.
- [ ] Dùng `PEMDecoder` với `Class` đích cụ thể khi cần cryptographic object.
- [ ] Dùng `PEM.class` khi cần giữ type chưa được hỗ trợ hoặc leading data.
- [ ] Không coi Base64 decode hoặc PEM parse là validation/trust.
- [ ] Kiểm tra algorithm, parameters, certificate validity, SAN, KU/EKU và trust chain.

### 15.2. Checklist trước khi ghi PEM

- [ ] Chọn label và binary format đúng contract đối tác.
- [ ] Ưu tiên SPKI `PUBLIC KEY`, PKCS #8 `PRIVATE KEY` hoặc `ENCRYPTED PRIVATE KEY` khi phù hợp.
- [ ] Không đổi label để giả lập một binary format khác.
- [ ] Dùng US-ASCII cho PEM text và thống nhất line ending theo hệ thống nhận.
- [ ] Mã hóa private key theo policy khi lưu/truyền qua nơi không đáng tin cậy.
- [ ] Không hard-code password hoặc ghi password/private key vào log.
- [ ] Kiểm tra round-trip trên cả Java và công cụ của hệ thống nhận.

### 15.3. Checklist nâng cấp Java 25 → 27/28

- [ ] Xác định code đang dùng preview JDK 25 (`DEREncodable`, `PEMRecord`) hay JDK 27 (`BinaryEncodable`, `PEM`).
- [ ] Cập nhật import, generic bounds và kiểu dữ liệu Base64 content.
- [ ] Cập nhật provider method theo API hiện hành (`withFactoriesOf`).
- [ ] Xử lý `CryptoException` khi encryption/decryption.
- [ ] Nếu ở JDK 27 GA, bật `--enable-preview` nhất quán ở compile/run.
- [ ] Khi JDK 28 GA, xác minh JEP 542 và bỏ preview flags nếu API đã được final như mục tiêu.
- [ ] Không phát hành preview class files như binary dùng chung xuyên các JDK release.

### 15.4. Nguồn tham khảo

- [JEP 470 — PEM Encodings of Cryptographic Objects (Preview)](https://openjdk.org/jeps/470): preview đầu tiên trong JDK 25.
- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): vòng preview thứ hai trong JDK 26.
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): vòng preview thứ ba trong JDK 27; đổi `DEREncodable` thành `BinaryEncodable`.
- [JEP 542 — PEM Encodings of Cryptographic Objects](https://openjdk.org/jeps/542): nhắm tới hoàn tất API trong JDK 28.
- [Oracle Java SE 27 API — PEMEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html): encode key, certificate, CRL, `withEncryption` và danh sách loại hỗ trợ.
- [Oracle Java SE 27 API — PEMDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html): decode String/InputStream, target class, `withDecryption` và `withFactoriesOf`.
- [Oracle Java SE 27 API — BinaryEncodable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html): mô hình binary object dùng chung cho PEM.
- [Oracle Java SE 27 API — PEM](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html): giữ PEM type, Base64 content và leading data.
- [Oracle Java SE 27 API — EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): PKCS #8 encrypted private key, encrypt/decrypt.
- [RFC 7468](https://www.rfc-editor.org/rfc/rfc7468): Textual Encodings of PKIX, PKCS, and CMS Structures.
- [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280): Internet X.509 Public Key Infrastructure Certificate and CRL Profile.
- [RFC 5958](https://www.rfc-editor.org/rfc/rfc5958): Asymmetric Key Packages.
- [Inside Java — JEP targeted to JDK 28: 542](https://inside.java/2026/10/06/jep542-target-jdk28/): thông tin JEP 542 được nhắm tới JDK 28.
- [OpenSSL `pkey`](https://docs.openssl.org/3.0/man1/openssl-pkey/), [OpenSSL `x509`](https://docs.openssl.org/3.0/man1/openssl-x509/) và [OpenSSL `verify`](https://docs.openssl.org/3.0/man1/openssl-verify/): công cụ kiểm tra và chuyển đổi key/certificate.

**Kết luận:** PEM là lớp văn bản Base64 có label bao ngoài cấu trúc DER; tính tương thích phụ thuộc vào label, PKCS/X.509 structure, thuật toán, parameters và trust policy. Java 25 giới thiệu `PEMEncoder`/`PEMDecoder` dưới dạng preview, API được điều chỉnh qua JDK 26 và JDK 27, rồi JEP 542 nhắm tới hoàn tất trong JDK 28. Khi làm việc với bản GA mới nhất JDK 27, dùng `BinaryEncodable` và `PEM`, bật preview flags nhất quán; khi nâng cấp JDK 28 GA, xác minh API final và bỏ preview dependency. Luôn kiểm tra certificate chain, key pair, encryption policy và interoperability với hệ thống nhận; parse thành công chỉ là bước đầu của quá trình xác thực.



