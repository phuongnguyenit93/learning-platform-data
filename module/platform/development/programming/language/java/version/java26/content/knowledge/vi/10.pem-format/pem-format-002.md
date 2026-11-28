# Thực hành dùng API PEM preview Java 27 hiện hành

Java 27 cung cấp API chuẩn để đọc và ghi PEM cho các đối tượng mật mã như public key, private key, certificate và certificate revocation list (CRL). Thay vì tự tìm marker, cắt Base64 rồi gọi `KeyFactory` hoặc `CertificateFactory` cho từng trường hợp, ứng dụng có thể dùng `PEMDecoder` và `PEMEncoder` để chuyển đổi giữa PEM text và các kiểu JCA tương ứng.

API này được giới thiệu ở **JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)**. Các lớp `PEMEncoder`, `PEMDecoder`, `PEM`, interface `BinaryEncodable` và một số API liên quan vẫn là preview trong JDK 27. Bài thực hành dùng đúng tên và chữ ký API của JDK 27; không dùng tên `DEREncodable` hoặc `withFactory(...)` của vòng preview trước.

## 1. PEM chứa gì?

PEM là định dạng văn bản để mang dữ liệu mật mã nhị phân. Nội dung nhị phân thường được mã hóa Base64 và đặt giữa hai dòng marker có nhãn loại dữ liệu:

```text
-----BEGIN PUBLIC KEY-----
...Base64 content...
-----END PUBLIC KEY-----
```

Marker cho biết cấu trúc dự kiến của dữ liệu. Một số nhãn thường gặp:

| PEM label | Nội dung | Kiểu Java mà decoder có thể trả về |
| --- | --- | --- |
| `CERTIFICATE` | Chứng thư X.509 | `X509Certificate` |
| `X509 CRL` | Certificate Revocation List | `X509CRL` |
| `PUBLIC KEY` | Public key theo SubjectPublicKeyInfo | `PublicKey` |
| `PRIVATE KEY` | Private key không mã hóa theo PKCS #8 | `PrivateKey` hoặc `KeyPair` nếu chứa cả public key |
| `ENCRYPTED PRIVATE KEY` | Private key PKCS #8 được mã hóa | `EncryptedPrivateKeyInfo`, hoặc `PrivateKey`/`KeyPair` khi decoder đã cấu hình giải mã |

PEM là định dạng vận chuyển văn bản; Base64 không phải mã hóa bảo mật. Một khối `PRIVATE KEY` không có password chỉ là private key được biểu diễn dưới dạng text. Muốn bảo vệ private key bằng password, cần tạo khối `ENCRYPTED PRIVATE KEY` bằng API mã hóa.

## 2. Các lớp chính của API Java 27

| API | Vai trò |
| --- | --- |
| `PEMEncoder` | Mã hóa một đối tượng `BinaryEncodable` thành PEM text hoặc byte array |
| `PEMDecoder` | Đọc PEM text hoặc `InputStream` thành đối tượng mật mã Java |
| `BinaryEncodable` | Hợp đồng chung cho các đối tượng có thể biểu diễn thành dữ liệu nhị phân và chuyển sang PEM |
| `PEM` | Giữ nhãn PEM, Base64 content và dữ liệu đứng trước header khi chưa có kiểu Java tương ứng |
| `EncryptedPrivateKeyInfo` | Đại diện cấu trúc private key đã mã hóa theo PKCS #8; hỗ trợ mã hóa/giải mã bằng password hoặc key |

Các lớp encoder/decoder được tạo qua factory:

```java
PEMEncoder encoder = PEMEncoder.of();
PEMDecoder decoder = PEMDecoder.of();
```

`PEMEncoder` và `PEMDecoder` là immutable và thread-safe. Có thể tái sử dụng instance mặc định. Khi cấu hình password hoặc provider, các method trả về instance mới đã được cấu hình.

## 3. Bật preview khi biên dịch và chạy

PEM API là preview trong JDK 27. Cần bật preview ở cả compiler và runtime, đồng thời dùng JDK 27 cho cả hai bước:

```bash
javac --enable-preview --release 27 -d out src/PemPractice.java
java --enable-preview -cp out PemPractice
```

Các lớp PEM nằm trong module `java.base` thuộc `java.security` và `javax.crypto`; không cần `--add-modules`. Nếu bỏ `--enable-preview`, compiler hoặc JVM sẽ từ chối chương trình sử dụng API preview.

## 4. Tạo và ghi public key dưới dạng PEM

Ví dụ tạo cặp khóa RSA để thực hành. Trong ứng dụng thật, thuật toán, kích thước khóa và chính sách lưu trữ phải tuân theo yêu cầu bảo mật của hệ thống.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMEncoder;

public class ExportPublicKey {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair keyPair = generator.generateKeyPair();

        String publicPem = PEMEncoder.of().encodeToString(keyPair.getPublic());

        Files.writeString(
                Path.of("public-key.pem"),
                publicPem,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
        );
    }
}
```

`encodeToString()` trả về PEM text; `encode()` trả về byte array nếu cần ghi trực tiếp bằng `Files.write`. Public key thường có nhãn `PUBLIC KEY`. `PEMEncoder` cũng có thể mã hóa `X509Certificate`, `X509CRL`, `PrivateKey`, `KeyPair`, `X509EncodedKeySpec` và `PKCS8EncodedKeySpec`.

`KeyPair` được mã hóa theo cấu trúc PKCS #8 v2.0 `OneAsymmetricKey` với nhãn `PRIVATE KEY`; cấu trúc có thể mang cả private key và public key. Nếu muốn trao đổi riêng public key, hãy mã hóa `keyPair.getPublic()` như ví dụ trên.

## 5. Đọc public key từ PEM

Nếu biết loại dữ liệu mong đợi, dùng overload `decode(String, Class)` để nhận đúng kiểu và tránh ép kiểu thủ công:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PublicKey;

public class ImportPublicKey {
    public static void main(String[] args) throws Exception {
        String pem = Files.readString(
                Path.of("public-key.pem"),
                StandardCharsets.UTF_8
        );

        PublicKey publicKey = PEMDecoder.of().decode(pem, PublicKey.class);

        System.out.println("Algorithm: " + publicKey.getAlgorithm());
        System.out.println("Format: " + publicKey.getFormat());
    }
}
```

Decoder phân tích PEM và dùng các factory mật mã của JCA để tạo đối tượng. Với dữ liệu không đúng loại `PublicKey`, overload có `Class` có thể ném `ClassCastException`; dữ liệu PEM sai cú pháp hoặc không giải mã được có thể ném `IllegalArgumentException`.

## 6. Mã hóa private key thành ENCRYPTED PRIVATE KEY

Không ghi private key không mã hóa vào repository, log, ticket hoặc thư mục chia sẻ. Có thể cấu hình `PEMEncoder` bằng `withEncryption(char[])` để mã hóa và xuất PEM trong một bước.

Ví dụ dùng `Console.readPassword()` để không đặt password trong source code hoặc đối số dòng lệnh:

```java
import java.io.Console;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.KeyPair;
import java.security.PEMEncoder;
import java.util.Arrays;

static void writeEncryptedPrivateKey(KeyPair keyPair) throws Exception {
    Console console = System.console();
    if (console == null) {
        throw new IllegalStateException("Run this example from a terminal");
    }

    char[] password = console.readPassword("Private key password: ");
    if (password == null || password.length == 0) {
        throw new IllegalArgumentException("A password is required");
    }

    try {
        String encryptedPem = PEMEncoder.of()
                .withEncryption(password)
                .encodeToString(keyPair.getPrivate());

        Files.writeString(
                Path.of("private-key.pem"),
                encryptedPem,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
        );
    } finally {
        Arrays.fill(password, '\0');
    }
}
```

Instance `PEMEncoder` được cấu hình bằng `withEncryption` chỉ dùng để mã hóa `PrivateKey`, `KeyPair` hoặc `PKCS8EncodedKeySpec`. Truyền certificate hoặc public key vào instance đó sẽ gây `IllegalArgumentException`.

`withEncryption` dùng thuật toán PBE mặc định của JDK/provider. Security property `jdk.epkcs8.defaultAlgorithm` xác định thuật toán mặc định; các tham số thuật toán mặc định do provider quyết định. Không nên giả định mọi provider hoặc mọi phiên bản JDK đều dùng cùng một thuật toán mặc định. PEM đã tạo lưu thuật toán và tham số cần thiết để giải mã; hãy kiểm tra chính sách mật mã và thử nghiệm khả năng tương thích với hệ thống nhận trước khi triển khai.

`withEncryption` và `withDecryption` đều clone password array và lưu bản sao trong instance đã cấu hình. Xóa mảng password phía ứng dụng bằng `Arrays.fill` vẫn là thực hành tốt, nhưng không xóa được bản sao nội bộ của encoder/decoder. Vì vậy, giữ các instance có password trong phạm vi ngắn và tránh lưu chúng như singleton hoặc field toàn cục.

## 7. Đọc và giải mã private key

Đọc private key đã mã hóa bằng `PEMDecoder.withDecryption(char[])`:

```java
import java.io.Console;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.util.Arrays;

static PrivateKey readEncryptedPrivateKey() throws Exception {
    Console console = System.console();
    if (console == null) {
        throw new IllegalStateException("Run this example from a terminal");
    }

    String encryptedPem = Files.readString(
            Path.of("private-key.pem"),
            StandardCharsets.UTF_8
    );
    char[] password = console.readPassword("Private key password: ");
    if (password == null) {
        throw new IllegalArgumentException("A password is required");
    }

    try {
        return PEMDecoder.of()
                .withDecryption(password)
                .decode(encryptedPem, PrivateKey.class);
    } finally {
        Arrays.fill(password, '\0');
    }
}
```

Nếu PEM chứa cả public và private key, có thể yêu cầu `KeyPair.class` thay cho `PrivateKey.class`. Dùng kiểu đích rõ ràng giúp code thể hiện chính xác loại dữ liệu cần dùng.

Nếu gọi `PEMDecoder.of().decode(encryptedPem)` mà không cấu hình decryption, decoder trả về `EncryptedPrivateKeyInfo`; nó không tự giải mã private key. Có thể giải mã theo hai bước:

```java
import javax.crypto.EncryptedPrivateKeyInfo;
import java.security.PrivateKey;

EncryptedPrivateKeyInfo encrypted = PEMDecoder.of().decode(
        encryptedPem,
        EncryptedPrivateKeyInfo.class
);

PrivateKey privateKey = encrypted.getKey(password);
```

`withDecryption` là cách ngắn gọn khi ứng dụng muốn decoder trả thẳng `PrivateKey` hoặc `KeyPair`. Dùng `EncryptedPrivateKeyInfo` trực tiếp khi cần kiểm soát riêng bước giải mã hoặc muốn thao tác với metadata của cấu trúc PKCS #8 đã mã hóa.

## 8. Đọc certificate và CRL

Đọc certificate:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

String certificatePem = Files.readString(
        Path.of("server-certificate.pem"),
        StandardCharsets.UTF_8
);

X509Certificate certificate = PEMDecoder.of().decode(
        certificatePem,
        X509Certificate.class
);

certificate.checkValidity();
```

`checkValidity()` chỉ kiểm tra thời hạn chứng thư. Việc decode thành công cũng không chứng minh chứng thư được tin cậy. Trước khi dùng certificate để xác thực peer, ứng dụng còn phải kiểm tra chuỗi chứng thư theo trust anchor, chữ ký, thời hạn, chính sách thuật toán, hostname khi dùng TLS và chính sách revocation phù hợp. Có thể dùng PKIX `CertPathValidator` và trust store đã cấu hình để kiểm tra đường dẫn chứng thư.

Tương tự, CRL có thể được đọc thành `X509CRL`:

```java
X509CRL crl = PEMDecoder.of().decode(crlPem, X509CRL.class);
```

Việc parse CRL không tự động xác nhận chữ ký CRL hoặc việc CRL được phát hành bởi CA tin cậy. Ứng dụng cần xác minh chữ ký, issuer, thời hạn hiệu lực và áp dụng đúng chính sách kiểm tra thu hồi.

## 9. Đọc PEM type chưa có kiểu Java tương ứng

Không phải mọi nhãn PEM đều có lớp mật mã tương ứng trong Java Platform. Ví dụ, một PEM chứa `CERTIFICATE REQUEST` có thể được trả về dưới dạng `PEM` thay vì một đối tượng CSR chuyên biệt.

```java
import java.security.PEM;
import java.security.PEMDecoder;

PEM rawPem = PEMDecoder.of().decode(pemText, PEM.class);

String label = rawPem.type();
byte[] base64Content = rawPem.content();
byte[] decodedContent = rawPem.decode();
byte[] leadingData = rawPem.leadingData();
```

Các method có ý nghĩa khác nhau:

- `type()` trả về nhãn trong marker, ví dụ `CERTIFICATE REQUEST`.
- `content()` trả về phần Base64 content dưới dạng byte array.
- `decode()` trả về dữ liệu nhị phân sau khi giải mã Base64 MIME.
- `leadingData()` trả về dữ liệu đứng trước PEM header trong input.

Với loại PEM đã có kiểu Java tương ứng, decoder bỏ qua leading data. Với loại không được hỗ trợ, `PEM` giữ lại leading data để ứng dụng có thể xử lý. Khi `PEMEncoder` mã hóa một `PEM` object, nó tạo header/footer từ `type()` và body từ `content()`; `leadingData()` không được đưa vào output.

Constructor của `PEM` không kiểm tra nhãn có tuân theo RFC hay Base64 content có thực sự tương ứng với nhãn đó. Vì vậy, không dùng `new PEM(...)` như một bước xác thực dữ liệu. Hãy kiểm tra nhãn mong đợi và xác minh nội dung ở tầng nghiệp vụ/mật mã trước khi sử dụng.

## 10. Đọc từ InputStream

Khi PEM nằm trong file hoặc stream, có thể truyền `InputStream` trực tiếp:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

try (InputStream input = Files.newInputStream(Path.of("certificate.pem"))) {
    X509Certificate certificate = PEMDecoder.of().decode(
            input,
            X509Certificate.class
    );
}
```

Decoder đọc đến PEM footer hoặc hết stream. Nếu xảy ra lỗi I/O trong khi decode, vị trí stream có thể không còn nhất quán; không nên tiếp tục decode trên cùng stream sau lỗi đó. Nếu không tìm thấy PEM hoặc stream kết thúc bất thường, API có thể ném `EOFException`.

## 11. Dùng provider cụ thể

Thông thường, `PEMDecoder.of()` dùng các provider mặc định của JCA. Nếu ứng dụng cần một provider cụ thể để tạo key hoặc certificate object, dùng `withFactoriesOf(Provider)`:

```java
import java.security.PEMDecoder;
import java.security.Provider;
import java.security.Security;
import java.security.cert.X509Certificate;

Provider provider = Security.getProvider("MyCryptoProvider");
if (provider == null) {
    throw new IllegalStateException("Required provider is not installed");
}

PEMDecoder decoder = PEMDecoder.of().withFactoriesOf(provider);
X509Certificate certificate = decoder.decode(
        certificatePem,
        X509Certificate.class
);
```

`withFactoriesOf` sử dụng `KeyFactory` và `CertificateFactory` của provider được chỉ định để tạo đối tượng. Provider phải được cài đặt và cung cấp service phù hợp với loại dữ liệu. Tùy chọn này không có nghĩa mọi thao tác PBE/Cipher cũng tự động chuyển sang provider đó; nếu cần kiểm soát provider hoặc tham số mã hóa private key, hãy dùng các overload tương ứng của `EncryptedPrivateKeyInfo.encrypt(...)`.

Nếu dùng `decode(pemText)` không có tham số `Class`, kết quả có kiểu `BinaryEncodable`. Có thể dùng pattern matching để xử lý từng loại:

```java
import java.security.BinaryEncodable;
import java.security.KeyPair;
import java.security.PEM;
import java.security.PublicKey;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.security.cert.X509CRL;
import javax.crypto.EncryptedPrivateKeyInfo;

BinaryEncodable decoded = PEMDecoder.of().decode(pemText);

switch (decoded) {
    case X509Certificate certificate -> handleCertificate(certificate);
    case X509CRL crl -> handleCrl(crl);
    case PublicKey publicKey -> handlePublicKey(publicKey);
    case PrivateKey privateKey -> handlePrivateKey(privateKey);
    case KeyPair keyPair -> handleKeyPair(keyPair);
    case EncryptedPrivateKeyInfo encrypted -> handleEncryptedKey(encrypted);
    case PEM raw -> handleUnsupportedPem(raw);
    default -> throw new IllegalArgumentException(
            "Unsupported cryptographic object: " + decoded.getClass().getName()
    );
}
```

`BinaryEncodable` là sealed interface nhưng danh sách subtype trong `permits` không được công bố đầy đủ. Vì vậy, switch không thể chỉ liệt kê các subtype đang thấy trong API rồi giả định đã exhaustive; cần `default` hoặc nhánh `case BinaryEncodable` để xử lý subtype bổ sung trong JDK tương lai. Nếu ứng dụng biết rõ kiểu cần nhận, overload `decode(..., Class)` vẫn ngắn và dễ kiểm tra hơn.

## 12. Tùy chỉnh thuật toán mã hóa private key

`PEMEncoder.withEncryption(password)` thuận tiện vì dùng thuật toán PBE mặc định. Khi chính sách yêu cầu thuật toán, tham số hoặc provider cụ thể, có thể tạo `EncryptedPrivateKeyInfo` trực tiếp rồi mã hóa object đó thành PEM:

```java
import javax.crypto.EncryptedPrivateKeyInfo;
import java.security.PrivateKey;
import java.security.PEMEncoder;

EncryptedPrivateKeyInfo encrypted = EncryptedPrivateKeyInfo.encrypt(
        privateKey,
        password,
        algorithmName,
        parameterSpec,
        provider
);

String encryptedPem = PEMEncoder.of().encodeToString(encrypted);
```

`algorithmName`, `parameterSpec` và `provider` phải tương thích với provider đang dùng. Không sao chép một tên thuật toán từ ví dụ mà không kiểm tra hỗ trợ và tham số thực tế. Với overload `encrypt(BinaryEncodable, char[])`, JDK chọn thuật toán PBE mặc định theo security property `jdk.epkcs8.defaultAlgorithm` và tham số mặc định của provider.

## 13. Những thay đổi từ JDK 26 sang JDK 27

PEM API thay đổi qua các vòng preview. JDK 27 dùng JEP 538, Third Preview; một số tên của JDK 26/JEP 524 không còn là tên API hiện hành.

| JDK 26 — JEP 524, Second Preview | JDK 27 — JEP 538, Third Preview |
| --- | --- |
| `DEREncodable` | `BinaryEncodable` |
| `PEM` là record | `PEM` là class với constructor và accessor |
| `withFactory(Provider)` | `withFactoriesOf(Provider)` |
| Lỗi xử lý mật mã được báo qua các exception hiện có | Bổ sung preview `CryptoException` cho lỗi mật mã |
| `PEMEncoder`/`PEMDecoder` đã là preview | Vẫn preview; cần bật preview ở compile và runtime |

Khi nâng từ JDK 26 lên JDK 27, đổi import và kiểu `DEREncodable` thành `BinaryEncodable`, đổi `withFactory` thành `withFactoriesOf`, rồi biên dịch lại. Không dùng class file preview đã biên dịch bằng JDK 26 để chạy trên JDK 27.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Compiler báo preview API không được bật | Thiếu `--enable-preview` hoặc dùng JDK không khớp `--release` | Biên dịch bằng JDK 27 với `--enable-preview --release 27` |
| Runtime từ chối preview class file | Chạy mà không có `--enable-preview` hoặc dùng JDK khác phiên bản compile | Chạy bằng JDK 27 và thêm `--enable-preview`; biên dịch lại nếu đổi JDK |
| `IllegalArgumentException` khi decode | PEM sai cú pháp, Base64 lỗi, label không hỗ trợ hoặc kiểu nội dung không hợp lệ | Kiểm tra toàn bộ marker, body, định dạng PKCS/X.509 và kiểu mong đợi |
| `ClassCastException` | Dùng overload `decode(..., Class)` với kiểu không khớp nội dung PEM | Xác định đúng label/kiểu dữ liệu trước khi yêu cầu class |
| `CryptoException` khi giải mã | Password sai, PBE algorithm/provider không hỗ trợ hoặc dữ liệu mã hóa hỏng | Kiểm tra password, provider, thuật toán và tham số; không log password/private key |
| `EncryptedPrivateKeyInfo` được trả về thay vì `PrivateKey` | Decoder chưa được cấu hình `withDecryption(...)` | Dùng `withDecryption(password)` hoặc gọi `getKey(password)` trên `EncryptedPrivateKeyInfo` |
| `EOFException` khi đọc stream | Không tìm thấy PEM block hoặc stream kết thúc trước footer | Kiểm tra file rỗng, marker và việc ghi file chưa hoàn tất |
| Provider không tạo được key/certificate | Provider thiếu `KeyFactory`/`CertificateFactory` cho loại dữ liệu | Cài đúng provider và kiểm tra service mà provider công bố |

## 15. Checklist bảo mật trước khi dùng trong ứng dụng

- [ ] Bật preview cho cả compile và runtime; khóa đúng JDK 27 trong môi trường thử nghiệm.
- [ ] Xác nhận label và kiểu dữ liệu mong đợi trước khi sử dụng đối tượng đã decode.
- [ ] Không xem Base64/PEM là mã hóa; private key phải dùng `ENCRYPTED PRIVATE KEY` nếu cần bảo vệ bằng password.
- [ ] Không ghi private key hoặc password vào log, source control, command line hay artifact công khai.
- [ ] Giới hạn quyền đọc file private key bằng ACL/permission của hệ điều hành và dùng secret manager phù hợp khi triển khai.
- [ ] Xóa password array phía ứng dụng trong `finally`; giới hạn thời gian sống của encoder/decoder đã cấu hình password.
- [ ] Xác minh certificate chain, trust anchor, hostname, validity và revocation theo chính sách ứng dụng; parse thành công không đồng nghĩa certificate đáng tin cậy.
- [ ] Kiểm tra thuật toán PBE, tham số và provider được hỗ trợ ở cả phía mã hóa và giải mã.
- [ ] Kiểm thử tương thích với công cụ hoặc hệ thống nhận PEM thực tế.
- [ ] Không để preview API trở thành public contract của thư viện production nếu chưa chấp nhận rủi ro thay đổi.

PEM phù hợp để trao đổi key/certificate với công cụ và hệ thống khác. Nếu ứng dụng cần kho lưu trữ key lâu dài với alias, metadata và quyền truy cập, hãy cân nhắc `KeyStore` cùng chính sách bảo vệ phù hợp thay vì dùng file PEM như một keystore.

## Ghi nhớ

- Java 27 cung cấp `PEMEncoder` và `PEMDecoder` qua JEP 538 — Third Preview.
- `BinaryEncodable` là kiểu chung của các đối tượng có thể chuyển đổi sang PEM; `PEM` giữ nội dung thô khi chưa có kiểu Java tương ứng.
- Dùng `encodeToString()`/`encode()` để ghi và `decode(..., Class)` để đọc đúng kiểu.
- `withEncryption(char[])` tạo PEM `ENCRYPTED PRIVATE KEY`; `withDecryption(char[])` giải mã private key khi đọc.
- `PEMDecoder` chưa cấu hình decryption sẽ trả `EncryptedPrivateKeyInfo` cho khối private key đã mã hóa.
- `withFactoriesOf(Provider)` chọn provider cho `KeyFactory` và `CertificateFactory`.
- PEM/Base64 không thay thế encryption, certificate path validation hoặc quản lý key an toàn.
- JDK 27 cần `--enable-preview` ở cả compile và run; API có thể thay đổi hoặc bị loại bỏ trong release sau.

## Tài liệu tham khảo

- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538) — mục tiêu và vòng preview trong JDK 27.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — xác nhận PEM API là Third Preview.
- [PEMEncoder, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html) — encode, encodeToString và mã hóa private key.
- [PEMDecoder, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html) — decode, typed decode, decryption và provider factories.
- [BinaryEncodable, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html) — hợp đồng chuyển đổi binary và PEM.
- [PEM, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html) — xử lý PEM chưa có kiểu Java tương ứng.
- [EncryptedPrivateKeyInfo, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html) — mã hóa/giải mã PKCS #8 private key.
- [Java Cryptography Architecture Reference Guide, Java SE 27](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html) — hướng dẫn PEM, provider và bảo vệ private key.
- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468) — quy tắc biểu diễn văn bản PEM cho các cấu trúc PKI/PKCS/CMS.
