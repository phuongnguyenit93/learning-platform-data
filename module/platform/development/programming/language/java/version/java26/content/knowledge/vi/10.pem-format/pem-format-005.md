# Tạo PEMEncoder và mã hóa đối tượng được hỗ trợ

PEM là định dạng văn bản thường dùng để trao đổi khóa công khai, khóa riêng, chứng chỉ và danh sách thu hồi chứng chỉ. Nội dung nhị phân của đối tượng mật mã được mã hóa Base64, đặt giữa hai dòng nhãn `BEGIN` và `END`. Trước JDK 25, JDK chưa có API chuyên biệt để chuyển các đối tượng mật mã sang PEM; ứng dụng thường dùng thư viện ngoài hoặc tự kết hợp DER, Base64 và nhãn PEM. Java 26 bổ sung `java.security.PEMEncoder` dưới dạng preview API để thực hiện việc này.

`PEMEncoder` nhận các đối tượng triển khai `DEREncodable` của JDK 26, chọn nhãn PEM tương ứng và trả về `String` hoặc `byte[]`. API còn hỗ trợ mã hóa khóa riêng bằng mật khẩu thông qua `withEncryption(char[])`. Đây là **preview API**, không phải API Java SE final.

## 1. PEMEncoder trong Java 26 là gì?

PEM (*Privacy-Enhanced Mail*) là định dạng văn bản dùng để lưu trữ hoặc chuyển giao dữ liệu mật mã. Theo RFC 7468, một khối PEM thường có dạng:

```text
-----BEGIN PUBLIC KEY-----
Base64-encoded-data
-----END PUBLIC KEY-----
```

Phần Base64 biểu diễn dữ liệu nhị phân đã được mã hóa theo định dạng mật mã tương ứng, thường là DER/ASN.1. Nhãn cho biết loại cấu trúc bên trong, ví dụ `PUBLIC KEY`, `PRIVATE KEY`, `CERTIFICATE` hoặc `ENCRYPTED PRIVATE KEY`.

`PEMEncoder` không tạo khóa, không cấp chứng chỉ và không xác minh chuỗi tin cậy. Nó chuyển một đối tượng mật mã đã tồn tại thành dạng PEM. Việc tạo khóa vẫn thuộc `KeyPairGenerator`; việc đọc chứng chỉ vẫn thuộc `CertificateFactory` hoặc quy trình PKI; việc ký và xác minh vẫn thuộc `Signature`.

Trong JDK 26, API thuộc JEP 524 (*PEM Encodings of Cryptographic Objects, Second Preview*). `PEMEncoder`, `PEMDecoder`, `DEREncodable` và `PEM` đều là preview API. Do đó, mã dùng chúng cần bật preview ở cả bước biên dịch và bước chạy.

## 2. Tạo PEMEncoder và sử dụng lại

Tạo một encoder bằng factory `PEMEncoder.of()`:

```java
import java.security.PEMEncoder;

PEMEncoder encoder = PEMEncoder.of();
```

`PEMEncoder` là immutable và thread-safe. Có thể sử dụng lại cùng một instance để mã hóa nhiều đối tượng mà không phải tạo encoder mới cho mỗi lần gọi:

```java
String publicKeyPem = encoder.encodeToString(publicKey);
byte[] certificatePem = encoder.encode(certificate);
```

Hai phương thức chính:

| Phương thức | Kết quả | Khi phù hợp |
|---|---|---|
| `encode(DEREncodable)` | `byte[]` chứa PEM | Ghi ra file, stream hoặc gửi qua API dạng byte |
| `encodeToString(DEREncodable)` | `String` chứa PEM | Cấu hình, log metadata không nhạy cảm hoặc giao tiếp API dạng văn bản |

Hai phương thức nhận cùng một loại đầu vào. Nếu đối tượng không thể mã hóa hoặc không được hỗ trợ, API ném `IllegalArgumentException`; nếu đầu vào là `null`, API ném `NullPointerException`.

Không ghi nội dung PEM của khóa riêng vào log hoặc thông báo lỗi. `String` là bất biến và không thể xóa nội dung khỏi bộ nhớ theo cách có thể kiểm soát; với dữ liệu nhạy cảm, hạn chế tạo thêm bản sao và ưu tiên ghi vào vị trí lưu trữ có quyền truy cập được kiểm soát.

## 3. Các đối tượng được hỗ trợ trên JDK 26

`PEMEncoder.encode()` và `encodeToString()` nhận `DEREncodable`. Đây là preview interface mà JDK gắn vào các kiểu mật mã có thể biểu diễn bằng dữ liệu nhị phân chuẩn. Các kiểu được API Java SE 26 liệt kê như sau:

| Đối tượng Java | Nhãn PEM | Ý nghĩa |
|---|---|---|
| `X509Certificate` | `CERTIFICATE` | Chứng chỉ X.509 |
| `X509CRL` | `X509 CRL` | Danh sách thu hồi chứng chỉ X.509 |
| `PublicKey` | `PUBLIC KEY` | Khóa công khai, dùng cấu trúc SubjectPublicKeyInfo |
| `PrivateKey` | `PRIVATE KEY` | Khóa riêng, dùng cấu trúc PKCS #8 |
| `EncryptedPrivateKeyInfo` | `ENCRYPTED PRIVATE KEY` | Khóa riêng PKCS #8 đã mã hóa |
| `KeyPair` | `PRIVATE KEY` | Gói OneAsymmetricKey theo PKCS #8 v2.0, có thể chứa cả khóa công khai và khóa riêng |
| `X509EncodedKeySpec` | `PUBLIC KEY` | Biểu diễn nhị phân của khóa công khai |
| `PKCS8EncodedKeySpec` | `PRIVATE KEY` | Biểu diễn nhị phân của khóa riêng |
| `PEM` | Theo `PEM.type()` | Khối PEM tổng quát đã có type và Base64 content |

Một implementation có thể hỗ trợ thêm loại PEM hoặc đối tượng `DEREncodable`. Khi cần tính tương thích giữa các JDK/vendor, hãy dựa trên danh sách chuẩn của API và kiểm tra khả năng hỗ trợ của môi trường triển khai, không giả định mọi provider đều hỗ trợ mọi thuật toán khóa.

### 3.1. Mã hóa khóa công khai và khóa riêng

Ví dụ tạo một cặp khóa Ed25519 rồi mã hóa riêng từng thành phần:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMEncoder;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair keyPair = generator.generateKeyPair();

PEMEncoder encoder = PEMEncoder.of();

String publicKeyPem = encoder.encodeToString(keyPair.getPublic());
String privateKeyPem = encoder.encodeToString(keyPair.getPrivate());

System.out.println(publicKeyPem);
```

Khối khóa công khai có nhãn `PUBLIC KEY`; khối khóa riêng có nhãn `PRIVATE KEY`. `PRIVATE KEY` trong trường hợp này là khóa PKCS #8 chưa mã hóa. Base64 chỉ là cách biểu diễn dữ liệu nhị phân thành văn bản, **không phải mã hóa bảo mật**. Bất kỳ ai có file `PRIVATE KEY` chưa mã hóa đều có thể lấy dữ liệu khóa từ nó.

### 3.2. Mã hóa cả KeyPair

JDK 26 hỗ trợ truyền trực tiếp `KeyPair`:

```java
String keyPairPem = encoder.encodeToString(keyPair);
```

`KeyPair` được mã hóa thành cấu trúc OneAsymmetricKey của PKCS #8 v2.0, dùng nhãn `PRIVATE KEY`. Cấu trúc này có thể mang cả khóa riêng và khóa công khai. Nó không tương đương với hai khối PEM tách biệt `PUBLIC KEY` và `PRIVATE KEY`.

Nếu hệ thống nhận chỉ mong đợi khóa công khai, hãy truyền `keyPair.getPublic()` để tạo `PUBLIC KEY`. Nếu hệ thống mong đợi khóa riêng PKCS #8, truyền `keyPair.getPrivate()` hoặc `keyPair` tùy yêu cầu định dạng của bên nhận. Kiểm tra tài liệu giao thức trước khi chọn một trong hai dạng.

### 3.3. Mã hóa chứng chỉ và CRL

Khi đã có đối tượng `X509Certificate` hoặc `X509CRL`, có thể mã hóa trực tiếp:

```java
import java.security.PEMEncoder;
import java.security.cert.X509CRL;
import java.security.cert.X509Certificate;

PEMEncoder encoder = PEMEncoder.of();

String certificatePem = encoder.encodeToString(certificate);
String crlPem = encoder.encodeToString(crl);
```

`certificate` và `crl` ở đây là các đối tượng đã được ứng dụng nạp hoặc nhận từ quy trình PKI. Encoder không kiểm tra chứng chỉ còn hạn, chữ ký CA có hợp lệ, hostname có khớp hay CRL có mới nhất không. Những bước xác minh đó vẫn phải được thực hiện bằng API chứng chỉ/PKIX phù hợp.

### 3.4. Mã hóa từ KeySpec

Nếu ứng dụng đang làm việc với key specification, JDK 26 cũng hỗ trợ:

```java
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

X509EncodedKeySpec publicSpec =
        new X509EncodedKeySpec(keyPair.getPublic().getEncoded());
PKCS8EncodedKeySpec privateSpec =
        new PKCS8EncodedKeySpec(keyPair.getPrivate().getEncoded());

String publicPem = encoder.encodeToString(publicSpec);
String privatePem = encoder.encodeToString(privateSpec);
```

`X509EncodedKeySpec` dùng cấu trúc SubjectPublicKeyInfo cho khóa công khai; `PKCS8EncodedKeySpec` dùng cấu trúc OneAsymmetricKey cho khóa riêng. Nếu đã có `PublicKey` hoặc `PrivateKey`, mã hóa trực tiếp đối tượng key thường ngắn gọn hơn. KeySpec hữu ích khi ứng dụng đang xử lý sẵn byte encoding hoặc cần giữ ranh giới giữa dữ liệu mã hóa và đối tượng key.

## 4. Mã hóa khóa riêng bằng mật khẩu

Để tạo PEM `ENCRYPTED PRIVATE KEY`, cấu hình encoder bằng `withEncryption(char[])`. Phương thức này trả về một instance mới đã được cấu hình với mật khẩu và thuật toán mã hóa mặc định:

```java
import java.security.PEMEncoder;
import java.util.Arrays;

char[] password = obtainPasswordFromSecureInput();
PEMEncoder encryptedEncoder;

try {
    encryptedEncoder = PEMEncoder.of().withEncryption(password);
} finally {
    Arrays.fill(password, '\0');
}

String encryptedPrivateKeyPem =
        encryptedEncoder.encodeToString(keyPair.getPrivate());
```

`obtainPasswordFromSecureInput()` đại diện cho cơ chế nhận mật khẩu của ứng dụng, không phải hàm JDK. Không đặt mật khẩu thật trong source code, command line, file cấu hình công khai hoặc log.

Trên JDK 26, encoder đã cấu hình encryption chỉ nhận `PrivateKey`, `KeyPair` hoặc `PKCS8EncodedKeySpec`. Truyền `PublicKey`, `X509Certificate`, `X509CRL` hoặc `PEM` vào instance này sẽ gây `IllegalArgumentException`.

`withEncryption()` sao chép mảng mật khẩu và lưu bản sao trong instance mới. Xóa mảng do ứng dụng sở hữu sau khi cấu hình encoder giúp giảm thời gian tồn tại của bản gốc; bản sao bên trong encoder vẫn còn trong vòng đời của instance và không có API `close()` để xóa trực tiếp. Vì vậy, hãy giới hạn vòng đời của encoder đã cấu hình mật khẩu, tránh lưu nó trong singleton hoặc cache toàn ứng dụng.

### 4.1. Thuật toán mã hóa mặc định

Thuộc tính security `jdk.epkcs8.defaultAlgorithm` xác định thuật toán PBE mặc định được dùng khi mã hóa khóa riêng. Tham số thuật toán mặc định phụ thuộc provider đang được chọn. Giá trị mặc định có thể thay đổi trong các bản JDK sau; PEM đã tạo vẫn mang tên thuật toán và các tham số cần thiết trong cấu trúc mã hóa, nên thay đổi mặc định sau này không tự làm mất khả năng giải mã dữ liệu cũ.

Nếu cần kiểm soát thuật toán, tham số hoặc provider cụ thể, dùng các overload preview của `EncryptedPrivateKeyInfo.encrypt(...)` để tạo đối tượng `EncryptedPrivateKeyInfo`, rồi truyền đối tượng đó vào encoder thông thường:

```java
import javax.crypto.EncryptedPrivateKeyInfo;
import java.util.Arrays;

char[] pbePassword = obtainPasswordFromSecureInput();
EncryptedPrivateKeyInfo encryptedInfo;
try {
    encryptedInfo = EncryptedPrivateKeyInfo.encrypt(
            keyPair.getPrivate(),
            pbePassword,
            pbeAlgorithm,
            algorithmParameters,
            provider);
} finally {
    Arrays.fill(pbePassword, '\0');
}

String encryptedPem = PEMEncoder.of().encodeToString(encryptedInfo);
```

`pbeAlgorithm`, `algorithmParameters` và `provider` phải được chọn theo chính sách mật mã và khả năng hỗ trợ của provider trong môi trường đích. Ví dụ chỉ minh họa luồng API; không sao chép tên thuật toán hoặc tham số từ một môi trường khác mà chưa kiểm tra. Các overload này cũng là preview API trên JDK 26.

### 4.2. Mã hóa không đồng nghĩa với quản lý khóa

`PEMEncoder` chỉ tạo định dạng PEM. Nó không thay thế kho khóa, hệ thống quản lý bí mật, KMS hoặc HSM. Trong hệ thống production:

- Giới hạn quyền đọc file chứa private key; dùng ACL hoặc permission phù hợp với hệ điều hành và tài khoản dịch vụ.
- Không commit private key vào Git, artifact build, image container hoặc thư mục log.
- Dùng encrypted private key nếu cần trao đổi file khóa qua môi trường không tin cậy; bảo vệ mật khẩu bằng kênh riêng.
- Cân nhắc KMS/HSM hoặc keystore khi ứng dụng cần kiểm soát quyền truy cập, xoay vòng và kiểm toán khóa.
- Không xem việc mã hóa PEM bằng mật khẩu là thay thế cho TLS, chữ ký số, xác minh chứng chỉ hoặc chính sách phân quyền.

## 5. Dùng PEM tổng quát khi không có kiểu Java tương ứng

JDK 26 có record preview `java.security.PEM` triển khai `DEREncodable`. Nó biểu diễn một khối PEM bằng `type`, `content` Base64 và `leadingData` tùy chọn:

```java
import java.security.PEM;
import java.security.PEMEncoder;

PEM request = new PEM("CERTIFICATE REQUEST", base64Content);
String pemText = PEMEncoder.of().encodeToString(request);
```

Ví dụ này chỉ phù hợp khi ứng dụng đã có nội dung Base64 đúng cấu trúc của một certificate request. Constructor `PEM` không xác minh rằng Base64 hợp lệ hoặc nội dung thực sự tương ứng với nhãn `CERTIFICATE REQUEST`. Encoder sẽ đặt phần `content` giữa header/footer theo `type`; `leadingData` không được đưa vào output.

Khi có kiểu mật mã Java chuyên biệt như `X509Certificate`, `PublicKey` hoặc `PrivateKey`, hãy ưu tiên truyền trực tiếp kiểu đó. Dùng `PEM` tổng quát khi cần bảo toàn loại PEM mà JDK không có lớp mật mã tương ứng và ứng dụng tự chịu trách nhiệm xác minh nội dung.

## 6. Lưu PEM ra file hoặc truyền qua API

`encodeToString()` trả văn bản PEM; `encode()` trả byte array. Ví dụ lưu một chứng chỉ công khai:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

String pem = encoder.encodeToString(certificate);
Files.writeString(
        Path.of("server-certificate.pem"),
        pem,
        StandardCharsets.US_ASCII,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

PEM là văn bản ASCII nên `US_ASCII` phù hợp với nội dung do encoder tạo. Với private key, cần tạo file ở thư mục có quyền truy cập hạn chế và áp dụng ACL/permission an toàn trước khi đưa file vào sử dụng. Nếu file đích đã tồn tại, ví dụ trên ghi đè nội dung; đối với khóa nhạy cảm, hãy thiết kế quy trình thay thế file an toàn và tránh để lại bản cũ ngoài ý muốn.

Khi gửi qua HTTP, có thể truyền chuỗi PEM trong body dạng text hoặc byte array theo hợp đồng API của bên nhận. Không đưa PEM private key vào URL, query string, header dễ bị ghi log hoặc thông tin telemetry.

## 7. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `IllegalArgumentException` khi encode | Đối tượng không được hỗ trợ hoặc encoder cấu hình encryption không chấp nhận kiểu đó | Kiểm tra kiểu `DEREncodable` và bảng hỗ trợ; với encryption chỉ dùng ba loại được phép |
| `NullPointerException` | Đối tượng truyền vào hoặc password là `null` | Kiểm tra đầu vào trước khi gọi API |
| Không có nhãn PEM như mong đợi | Chọn nhầm object hoặc định dạng bên nhận yêu cầu khác | Kiểm tra PEM type và cấu trúc PKCS #8/X.509 theo giao thức |
| Bên nhận không đọc được private key | Bên nhận không hỗ trợ thuật toán, định dạng hoặc encryption scheme đã dùng | Xác minh thuật toán key, PKCS #8 và PBE với hệ thống đích |
| Khóa riêng bị lộ trong log hoặc file | Dùng `PRIVATE KEY` chưa mã hóa hoặc lưu sai vị trí | Dùng encrypted PEM hoặc KMS/keystore; giới hạn quyền và loại bỏ log nhạy cảm |
| Tưởng encoder xác minh chứng chỉ | Nhầm chuyển đổi định dạng với kiểm tra PKI | Thực hiện kiểm tra chữ ký, validity, hostname, path và revocation riêng |

PEM chỉ là lớp biểu diễn văn bản của dữ liệu mật mã. Một khối `CERTIFICATE` hợp cú pháp chưa chắc là chứng chỉ đáng tin cậy; một khối `PUBLIC KEY` hợp cú pháp chưa chắc thuộc đúng danh tính; một khối `PRIVATE KEY` hợp cú pháp chưa chắc được bảo vệ bằng mật khẩu.

## 8. Preview trên JDK 26 và thay đổi ở JDK 27

Trạng thái theo release:

| JDK | JEP | Trạng thái | Tên interface và biểu diễn PEM |
|---|---|---|---|
| JDK 25 | JEP 470 | Preview lần đầu | `DEREncodable`, `PEMRecord` |
| JDK 26 | JEP 524 | Preview lần thứ hai | `DEREncodable`, `PEM` là record |
| JDK 27 | JEP 538 | Preview lần thứ ba | `BinaryEncodable`, `PEM` là class |

JDK 27 đổi tên `DEREncodable` thành `BinaryEncodable` và đổi `PEM` từ record sang class, đồng thời chuyển content sang biểu diễn nhị phân và bổ sung bảo vệ sao chép dữ liệu. Vì vậy, ví dụ JDK 26 trong bài dùng `DEREncodable` và API `PEM` record; khi chuyển sang JDK 27 phải biên dịch lại và cập nhật theo tài liệu JDK 27. Không dùng tên `PEMRecord` của preview đầu tiên trong code JDK 26/27.

Với JDK 26, biên dịch và chạy bằng đúng JDK 26, bật preview ở cả hai bước:

```bash
javac --release 26 --enable-preview PemEncodeDemo.java
java --enable-preview PemEncodeDemo
```

Chỉ bật `--enable-preview` khi biên dịch là chưa đủ; JVM chạy ứng dụng cũng phải bật. Bytecode dùng preview của JDK 26 không phải cam kết chạy trên JDK 27. Khi nâng JDK, đọc JEP/API Specification của release đích và biên dịch lại mã nguồn.

Nếu sản phẩm không chấp nhận phụ thuộc preview, chưa nên đưa `PEMEncoder` của JDK 26 vào hợp đồng API ổn định. Có thể tiếp tục dùng API chuẩn ổn định đang có trong JCA để lấy DER (`getEncoded()`), kết hợp thư viện PEM được duy trì và đã được kiểm tra tương thích, hoặc đợi PEM API được chuẩn hóa trong một JDK GA tương lai. Không tự viết parser/encoder mật mã bằng cách nối chuỗi Base64 nếu không có yêu cầu và kiểm thử bảo mật chuyên biệt.

## 9. Checklist trước khi đưa vào ứng dụng

- [ ] Đối tượng đầu vào thuộc danh sách `DEREncodable` được hỗ trợ trên đúng JDK.
- [ ] Chọn đúng nhãn PEM và cấu trúc DER/PKCS #8/X.509 mà hệ thống nhận yêu cầu.
- [ ] Phân biệt khóa riêng chưa mã hóa (`PRIVATE KEY`) với khóa riêng được mã hóa (`ENCRYPTED PRIVATE KEY`).
- [ ] Không coi Base64 là mã hóa; không để private key xuất hiện trong log hoặc source control.
- [ ] Nếu dùng `withEncryption`, hiểu rằng encoder giữ bản sao password và chỉ nhận `PrivateKey`, `KeyPair`, `PKCS8EncodedKeySpec`.
- [ ] Kiểm tra thuật toán PBE mặc định hoặc cấu hình tham số/provider rõ ràng theo chính sách mật mã.
- [ ] Xác minh chứng chỉ, CRL, chữ ký và quyền sử dụng khóa bằng API/chính sách riêng; encoder không làm việc đó.
- [ ] Bật preview ở cả compile và runtime trên JDK 26.
- [ ] Khi nâng lên JDK 27, cập nhật `DEREncodable` thành `BinaryEncodable` và rà soát thay đổi `PEM`.

## Tài liệu tham khảo

- [JEP 524: PEM Encodings of Cryptographic Objects (Second Preview, JDK 26)](https://openjdk.org/jeps/524)
- [Java SE 26 API: PEMEncoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html)
- [Java SE 26 API: DEREncodable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/DEREncodable.html)
- [Java SE 26 API: PEM](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEM.html)
- [Java SE 26 API: EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html)
- [Java SE 26 Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [JEP 538: PEM Encodings of Cryptographic Objects (Third Preview, JDK 27)](https://openjdk.org/jeps/538)
- [Java SE 27 API: BinaryEncodable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html)
