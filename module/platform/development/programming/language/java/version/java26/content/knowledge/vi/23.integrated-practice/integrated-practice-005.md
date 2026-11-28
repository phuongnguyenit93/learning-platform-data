# Trao đổi đối tượng mật mã qua PEM preview Java 27

PEM là định dạng văn bản dùng để trao đổi dữ liệu mật mã như public key, private key, certificate và certificate revocation list (CRL). Nó đóng gói dữ liệu nhị phân theo chuẩn DER dưới dạng Base64, kèm nhãn ở phần đầu/cuối, ví dụ `BEGIN PUBLIC KEY` hoặc `BEGIN CERTIFICATE`. Java 27 tiếp tục preview API PEM qua JEP 538 (Third Preview), cung cấp `PEMEncoder`, `PEMDecoder`, `PEM` và `BinaryEncodable` để chuyển đổi giữa các đối tượng mật mã Java và văn bản PEM.

Bài thực hành tích hợp này xây dựng một luồng trao đổi khóa có thể kiểm chứng: tạo cặp khóa Ed25519, mã hóa public key thành PEM, mã hóa private key bằng mật khẩu, giải mã ở phía nhận rồi ký/xác minh một thông điệp. Bài cũng đọc một X.509 certificate và phân biệt việc parse PEM với việc xác minh certificate chain. Các API PEM trong Java 27 vẫn là preview; phải biên dịch và chạy bằng JDK 27 với `--enable-preview`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cấu trúc PEM và mối liên hệ giữa PEM, Base64, DER, PKCS #8 và X.509.
- Phân biệt `PEMEncoder`, `PEMDecoder`, `PEM`, `BinaryEncodable` và các kiểu mật mã được hỗ trợ.
- Tạo PEM cho public key, private key, key pair và certificate.
- Mã hóa private key trước khi trao đổi và giải mã bằng password ở phía nhận.
- Dùng typed `decode(..., Class)` để nhận đúng kiểu `PublicKey`, `PrivateKey`, `KeyPair` hoặc `X509Certificate`.
- Xử lý PEM label chưa có kiểu Java tương ứng bằng `PEM` tổng quát.
- Kiểm chứng round-trip bằng chữ ký số thay vì chỉ so sánh chuỗi PEM.
- Phân biệt parse certificate, kiểm tra thời hạn, xác minh chữ ký và xác minh trust chain.
- Bật preview đúng cách và nhận biết khác biệt API giữa JDK 26 và JDK 27.
- Bảo vệ private key, password, file PEM và dữ liệu trao đổi trong môi trường thật.

## 1. Bài toán: chuyển khóa và certificate giữa các hệ thống

Một dịch vụ Java có thể cần:

- Xuất public key để đối tác mã hóa dữ liệu hoặc xác minh chữ ký.
- Nhập public key từ một hệ thống khác để xác minh chữ ký đến.
- Chuyển private key giữa các môi trường được phép, ví dụ môi trường kiểm thử hoặc một quy trình khôi phục khóa.
- Nhận certificate từ CA hoặc đối tác để cấu hình TLS, xác minh chữ ký hay xây dựng trust chain.
- Nhận CRL để kiểm tra trạng thái thu hồi certificate.

Các API JCA/JCA providers đã có khả năng biểu diễn nhiều đối tượng này bằng Java object, nhưng trước API PEM mới, ứng dụng thường phải tự kết hợp `getEncoded()`, Base64, header/footer và các factory tương ứng. Tự ghép chuỗi PEM có thể tạo lỗi về label, line wrapping, charset, loại encoding hoặc xử lý password.

Java 27 bổ sung một API thống nhất để mã hóa và giải mã các kiểu đối tượng được hỗ trợ. API không thay thế toàn bộ PKI, không tự tạo trust policy và không biến một file PEM thành một giao thức trao đổi an toàn. Ứng dụng vẫn phải quản lý danh tính, quyền truy cập, password, certificate chain và định dạng giao tiếp.

## 2. PEM chứa gì?

PEM là textual encoding cho dữ liệu nhị phân. Một block thường có cấu trúc:

```text
-----BEGIN PUBLIC KEY-----
Base64-encoded DER data
-----END PUBLIC KEY-----
```

Phần `PUBLIC KEY` là type label. Nội dung Base64 thường là một cấu trúc DER theo chuẩn mật mã tương ứng. PEM không phải một thuật toán mã hóa; Base64 chỉ chuyển bytes thành văn bản có thể truyền qua hệ thống chỉ hỗ trợ text.

Một số label thường gặp:

| PEM label | Dữ liệu thường được chứa | Binary structure phổ biến |
|---|---|---|
| `PUBLIC KEY` | Public key | SubjectPublicKeyInfo theo X.509 |
| `PRIVATE KEY` | Private key không mã hóa | PKCS #8 PrivateKeyInfo hoặc OneAsymmetricKey |
| `ENCRYPTED PRIVATE KEY` | Private key được mã hóa bằng password | PKCS #8 EncryptedPrivateKeyInfo |
| `CERTIFICATE` | X.509 certificate | Certificate ASN.1/DER |
| `X509 CRL` | Certificate Revocation List | CRL ASN.1/DER |
| `CERTIFICATE REQUEST` | Certificate Signing Request | PKCS #10 |
| `PKCS7` hoặc `CMS` | Gói dữ liệu CMS/PKCS #7 | CMS ASN.1/DER |

API Java 27 có kiểu Java tương ứng cho một số loại phổ biến như public/private key, key pair, X.509 certificate và CRL. Với label không có kiểu Java tương ứng, decoder có thể trả về `PEM` tổng quát để ứng dụng tự chuyển tiếp hoặc xử lý bằng thư viện phù hợp.

**Không nhầm PEM với mã hóa bí mật:** một block `PRIVATE KEY` thường chứa private key ở dạng có thể đọc sau Base64 decode. Chỉ block `ENCRYPTED PRIVATE KEY` mới có lớp mã hóa password theo PKCS #8. Block `PUBLIC KEY` và `CERTIFICATE` vốn không phải dữ liệu bí mật.

## 3. Phiên bản API: Java 26 và Java 27 không dùng cùng kiểu dữ liệu

PEM API đã trải qua nhiều vòng preview. Điều này quan trọng vì một bài thực hành trong module Java 26 đang nhắm tới API preview Java 27.

| JDK | Preview | Mô hình API đáng chú ý |
|---|---|---|
| JDK 25 | JEP 470, First Preview | API PEM preview ban đầu |
| JDK 26 | JEP 524, Second Preview | Marker interface `DEREncodable`; `PEM` là record với Base64 content dạng `String` |
| JDK 27 | JEP 538, Third Preview | `DEREncodable` đổi tên thành `BinaryEncodable`; `PEM` là class, content Base64 ở dạng `byte[]`; có `CryptoException` cho lỗi xử lý mật mã |

Không copy source dùng `DEREncodable` hoặc giả định `PEM.content()` trả `String` từ JDK 26 vào project biên dịch với JDK 27. API JDK 27 dùng `BinaryEncodable`, `PEM.content()` trả `byte[]` và các method mới được đánh dấu preview theo release này.

Tại thời điểm bài học, JDK 27 đã phát hành GA; Oracle Consolidated Release Notes liệt kê update 27.0.1.1 ngày 17-11-2026. Dù dùng JDK 27 GA hay update mới hơn cùng major version, hãy kiểm tra vendor/build thực tế và dùng đúng preview API của JDK 27. Preview API có thể tiếp tục thay đổi hoặc không được giữ nguyên ở release sau.

## 4. Các thành phần Java 27

### `BinaryEncodable`

`java.security.BinaryEncodable` là preview interface đánh dấu các đối tượng mật mã có thể chuyển đổi sang biểu diễn nhị phân chuẩn và được PEM encoder/decoder xử lý thống nhất. Interface này là sealed; các kiểu liên quan gồm `AsymmetricKey`, `KeyPair`, `PKCS8EncodedKeySpec`, `X509EncodedKeySpec`, `EncryptedPrivateKeyInfo`, `X509Certificate`, `X509CRL` và `PEM`.

Danh sách subtype được tài liệu API ghi rõ là không exhaustive. Nếu dùng `switch` trên `BinaryEncodable`, luôn có `default` hoặc nhánh xử lý `BinaryEncodable` tổng quát; không giả định danh sách hiện tại sẽ không đổi trong các preview tiếp theo.

### `PEMEncoder`

`PEMEncoder.of()` tạo encoder. Hai phương thức chính:

- `encode(BinaryEncodable)` trả về PEM bytes.
- `encodeToString(BinaryEncodable)` trả về PEM text.

Encoder hỗ trợ các loại phổ biến gồm `X509Certificate`, `X509CRL`, `PublicKey`, `PrivateKey`, `EncryptedPrivateKeyInfo`, `KeyPair`, `X509EncodedKeySpec`, `PKCS8EncodedKeySpec` và `PEM`. Provider có thể hỗ trợ thêm loại khác.

Để mã hóa private key bằng password:

```java
PEMEncoder encryptedEncoder = PEMEncoder.of().withEncryption(password);
String pem = encryptedEncoder.encodeToString(keyPair);
```

Encoder được cấu hình bằng `withEncryption()` chỉ nhận `PrivateKey`, `KeyPair` và `PKCS8EncodedKeySpec`. Không dùng cùng encoder này để mã hóa public key hoặc certificate; các loại công khai phải được encode bằng encoder thông thường.

`PEMEncoder` immutable và thread-safe. Các phương thức `with...()` trả về instance mới.

### `PEMDecoder`

`PEMDecoder.of()` tạo decoder. Có thể giải mã từ `String` hoặc `InputStream`:

```java
PublicKey publicKey = PEMDecoder.of().decode(publicPem, PublicKey.class);
```

Các overload có `Class<S>` giúp yêu cầu kiểu đầu ra cụ thể, tránh cast không rõ ràng. Decoder có thể được cấu hình:

- `withDecryption(char[])`: giải mã private key được mã hóa bằng password; decoder này cũng giải mã PEM không mã hóa.
- `withFactoriesOf(Provider)`: dùng `KeyFactory` và `CertificateFactory` từ provider được chỉ định.

Decoder immutable và thread-safe. Nếu giải mã block `ENCRYPTED PRIVATE KEY` mà không cấu hình `withDecryption()`, kết quả là `EncryptedPrivateKeyInfo`, không phải `PrivateKey` đã giải mã.

### `PEM`

`PEM` là class preview dùng làm container tổng quát cho PEM type chưa có kiểu Java tương ứng hoặc khi ứng dụng muốn giữ dữ liệu PEM ở dạng thô. Các method quan trọng:

- `type()`: type label, ví dụ `CERTIFICATE REQUEST`.
- `content()`: Base64-encoded content dạng `byte[]`.
- `decode()`: Base64 decode content thành bytes.
- `leadingData()`: dữ liệu xuất hiện trước PEM header trong input, có thể không có.
- `toString()`: dựng PEM text từ type và content.

Constructor của `PEM` không xác minh type label có đúng RFC 7468 hay content có tương ứng với type hay không. Khi nhận PEM không hỗ trợ, ứng dụng phải tự allowlist type và xác minh dữ liệu trước khi sử dụng. Khi encoder ghi một `PEM` object, `leadingData()` không được thêm lại vào output; nếu cần giữ phần preamble, ứng dụng phải quản lý riêng.

## 5. Thiết lập project dùng preview Java 27

PEM API trong JDK 27 là preview API thuộc `java.base`. Không cần thêm module hoặc dependency bên ngoài, nhưng compiler và runtime phải bật preview.

Biên dịch:

```bash
javac --enable-preview --release 27 \
  -d out \
  src/main/java/example/PemExchange.java
```

Chạy:

```bash
java --enable-preview -cp out example.PemExchange
```

Compiler và runtime phải dùng cùng release preview. Không dùng `--enable-preview --release 26` để biên dịch source JDK 27; API JDK 26 dùng `DEREncodable` và có cấu trúc `PEM` khác.

Với Maven Compiler Plugin, đặt `release` là `27` và bật `enablePreview`; test/runtime fork cũng phải nhận `--enable-preview`. Với Gradle, thêm `--enable-preview` vào compiler args của `JavaCompile`, đồng thời thêm cùng flag vào JVM chạy test và application. Không bật preview chỉ ở compile rồi quên runtime.

## 6. Thực hành A — tạo cặp khóa và trao đổi PEM

Ta dùng Ed25519 để có một luồng ký/xác minh ngắn, không cần tự chọn tham số đường cong. Mục tiêu là kiểm tra key pair sau khi đi qua PEM vẫn dùng được trong JCA.

### Bước 1: sinh key pair

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair originalPair = generator.generateKeyPair();
```

Private key và public key là hai phần khác nhau. Public key có thể chia sẻ rộng hơn, nhưng phải bảo vệ tính toàn vẹn và xác thực nguồn. Private key phải được giữ bí mật.

### Bước 2: encode public key và private key

```java
import java.security.PEMEncoder;

String publicPem = PEMEncoder.of().encodeToString(originalPair.getPublic());

// password lấy từ console/secret manager; không hard-code trong source.
String encryptedPrivatePem = PEMEncoder.of()
        .withEncryption(password)
        .encodeToString(originalPair);
```

Public key được encode bằng encoder thông thường và tạo label `PUBLIC KEY`. Private key được encode cùng key pair qua PKCS #8 OneAsymmetricKey và có label `ENCRYPTED PRIVATE KEY` khi dùng encoder đã cấu hình password.

`KeyPair` có thể chứa cả private key và public key trong cấu trúc OneAsymmetricKey. Vì vậy, decoder có thể trả về `KeyPair` khi yêu cầu đúng kiểu và encoding có public key. Nếu chỉ có PKCS #8 PrivateKeyInfo không chứa public key, yêu cầu `KeyPair.class` không phù hợp; khi đó decode thành `PrivateKey` và lấy public key từ nguồn được xác thực riêng.

### Bước 3: trao đổi

Trong ví dụ, gửi `publicPem` cho bên cần xác minh chữ ký và gửi `encryptedPrivatePem` qua kênh bảo vệ phù hợp tới môi trường được phép giữ private key. Password phải được phân phối qua kênh độc lập hoặc secret manager. Không đặt password cạnh file private key, không ghi vào log và không đưa vào repository.

PEM không tự xác thực người gửi. Nếu attacker thay public key bằng key của họ, bên nhận có thể xác minh chữ ký của attacker mà không nhận ra việc đổi khóa. Hãy gắn public key/certificate với danh tính bằng certificate authority, pinning, fingerprint đã xác thực hoặc một trust mechanism của giao thức.

## 7. Thực hành B — decode và kiểm chứng bằng chữ ký

Ví dụ hoàn chỉnh sau encode public key, mã hóa private key, decode lại rồi ký/xác minh dữ liệu. Chữ ký thành công chứng minh private key giải mã được tương ứng với public key đã trao đổi.

```java
import java.io.Console;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Arrays;

public class PemExchange {
    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Chạy từ terminal có console hoặc lấy password từ secret manager");
        }

        char[] password = console.readPassword("PEM password: ");
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Password không được để trống");
        }

        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
            KeyPair originalPair = generator.generateKeyPair();

            String publicPem = PEMEncoder.of()
                    .encodeToString(originalPair.getPublic());

            String privatePem = PEMEncoder.of()
                    .withEncryption(password)
                    .encodeToString(originalPair);

            // Phía nhận: giải mã private key bằng password đã nhận an toàn.
            KeyPair importedPair = PEMDecoder.of()
                    .withDecryption(password)
                    .decode(privatePem, KeyPair.class);

            // Public key được giải mã độc lập từ block PUBLIC KEY.
            PublicKey importedPublic = PEMDecoder.of()
                    .decode(publicPem, PublicKey.class);

            byte[] message = "contract-id=INV-2026-001"
                    .getBytes(StandardCharsets.UTF_8);

            Signature signer = Signature.getInstance("Ed25519");
            signer.initSign(importedPair.getPrivate());
            signer.update(message);
            byte[] signatureBytes = signer.sign();

            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(importedPublic);
            verifier.update(message);

            if (!verifier.verify(signatureBytes)) {
                throw new SecurityException("PEM round-trip không khớp key pair");
            }

            System.out.println("PEM round-trip và chữ ký: PASS");
        } finally {
            // Xóa bản password do ứng dụng giữ; encoder/decoder đã clone mảng.
            Arrays.fill(password, '\0');
        }
    }
}
```

Ví dụ dùng `System.console()` để tránh password hiển thị khi nhập. Trong ứng dụng server, lấy password từ secret manager hoặc cơ chế cung cấp secret phù hợp. `withEncryption()` và `withDecryption()` clone mảng password và giữ bản sao trong instance cấu hình; vì vậy không giữ encoder/decoder chứa password lâu hơn cần thiết. Xóa mảng gốc không thể đảm bảo xóa ngay bản sao nội bộ khỏi heap.

Nếu muốn decode riêng private key mà không cần key pair:

```java
PrivateKey privateKey = PEMDecoder.of()
        .withDecryption(password)
        .decode(encryptedPrivatePem, PrivateKey.class);
```

Không decode private key bằng overload không cấu hình password rồi giả định decoder tự hỏi password. Với encrypted PEM, decoder chưa cấu hình decryption trả `EncryptedPrivateKeyInfo`.

## 8. Thực hành C — đọc X.509 certificate

Có thể tạo certificate tự ký cho môi trường thử nghiệm bằng `keytool` có sẵn trong JDK:

```bash
keytool -genkeypair \
  -alias pem-demo \
  -keyalg EC \
  -groupname secp256r1 \
  -dname "CN=PEM Demo" \
  -validity 30 \
  -storetype PKCS12 \
  -keystore demo.p12

keytool -exportcert \
  -alias pem-demo \
  -storetype PKCS12 \
  -keystore demo.p12 \
  -rfc \
  -file demo-cert.pem
```

`keytool` sẽ hỏi password nếu không truyền trên command line. Không đưa password thật vào shell history hoặc process arguments.

Đọc certificate bằng Java 27:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.cert.X509Certificate;

String certificatePem = Files.readString(
        Path.of("demo-cert.pem"), StandardCharsets.UTF_8);

X509Certificate certificate = PEMDecoder.of()
        .decode(certificatePem, X509Certificate.class);

certificate.checkValidity();
System.out.println(certificate.getSubjectX500Principal());
```

Có thể encode lại certificate:

```java
String encodedAgain = PEMEncoder.of().encodeToString(certificate);
```

### Parse không đồng nghĩa xác minh trust

`PEMDecoder` tạo `X509Certificate` từ cấu trúc certificate. Điều đó chỉ chứng minh dữ liệu có thể parse theo kiểu được hỗ trợ. Nó không tự xác nhận certificate đáng tin cậy.

Các bước bảo mật phải được phân biệt:

1. **Parse:** PEM syntax và DER structure hợp lệ, tạo được `X509Certificate`.
2. **Validity:** `checkValidity()` xác nhận thời gian hiện tại nằm trong khoảng `notBefore`/`notAfter`.
3. **Signature:** `certificate.verify(issuerPublicKey)` xác minh chữ ký certificate bằng public key issuer được cung cấp.
4. **Path validation:** xác minh chain tới một trust anchor bằng PKIX `CertPathValidator`/`TrustManagerFactory`, kiểm tra constraints, key usage, extended key usage, policy và revocation theo yêu cầu.
5. **Endpoint identity:** nếu dùng cho TLS client/server, xác minh hostname hoặc service identity theo giao thức.

Certificate tự ký có thể qua `checkValidity()` và `verify(certificate.getPublicKey())` nhưng vẫn không tự trở thành trust anchor. Chỉ tin certificate khi trust policy của ứng dụng xác nhận nó.

## 9. Thực hành D — xử lý PEM label chưa có kiểu Java tương ứng

Một số PEM type như `CERTIFICATE REQUEST`, `CMS` hoặc `PKCS7` có thể chưa có kiểu Java SE tương ứng trong API này. Decoder có thể trả về `PEM` tổng quát:

```java
import java.security.PEM;
import java.security.PEMDecoder;

PEM rawPem = PEMDecoder.of().decode(csrText, PEM.class);

String type = rawPem.type();
byte[] base64Content = rawPem.content();
byte[] derContent = rawPem.decode();
byte[] leadingData = rawPem.leadingData();
```

`content()` trả về Base64 bytes; `decode()` trả về bytes đã Base64 decode. `leadingData()` giữ dữ liệu trước header nếu decoder được yêu cầu trả `PEM.class`. Với các kiểu Java cụ thể như `PublicKey` hoặc `X509Certificate`, phần leading data được bỏ qua.

Không xử lý mọi generic PEM như nhau. Kiểm tra `type()` theo allowlist của ứng dụng trước khi chuyển bytes tới parser phù hợp. Không tin label do input tự khai báo; constructor `PEM` không xác minh rằng content thực sự tương ứng với type.

Nếu muốn giữ một block chưa được hỗ trợ dưới dạng văn bản PEM, có thể gọi `rawPem.toString()` hoặc encode `PEM` object. Lưu ý `PEMEncoder` không đưa `leadingData()` trở lại output. Nếu preamble chứa metadata có ý nghĩa, lưu riêng và xác minh theo giao thức của ứng dụng.

## 10. Trao đổi nhiều block PEM trong một file

Một file PEM có thể chứa nhiều block liên tiếp, ví dụ certificate leaf và intermediate certificates. Có thể dùng `InputStream` để đọc từng block theo thứ tự:

```java
try (InputStream input = Files.newInputStream(Path.of("chain.pem"))) {
    PEMDecoder decoder = PEMDecoder.of();

    X509Certificate leaf = decoder.decode(input, X509Certificate.class);
    X509Certificate intermediate = decoder.decode(input, X509Certificate.class);
}
```

Mỗi lần decode đọc tới footer của block PEM. Nếu có lỗi I/O, vị trí stream có thể không còn nhất quán; không nên tiếp tục decode trên cùng stream sau lỗi đó. Khi không còn block, overload `InputStream` có thể ném `EOFException`.

Nếu cần xử lý file có thể chứa nhiều loại block, đọc tuần tự về `BinaryEncodable` rồi phân nhánh bằng `instanceof`. Vì `BinaryEncodable` có thể mở rộng trong preview sau, giữ nhánh mặc định:

```java
BinaryEncodable item = decoder.decode(input);

if (item instanceof X509Certificate cert) {
    // Xác minh certificate theo trust policy.
} else if (item instanceof X509CRL crl) {
    // Kiểm tra CRL theo issuer và policy.
} else if (item instanceof PublicKey publicKey) {
    // Liên kết public key với identity đã xác thực.
} else if (item instanceof PEM raw) {
    // Kiểm tra allowlist type rồi chuyển tới parser phù hợp.
} else {
    throw new IllegalArgumentException(
            "Không hỗ trợ PEM object type: " + item.getClass().getName());
}
```

Đây là xử lý theo kiểu minh họa; ứng dụng cần định nghĩa rõ thứ tự, loại block, số lượng tối đa và cách liên kết certificate/key. Không giả định mọi file PEM đều chỉ có một block.

## 11. Bảo vệ private key và password

Private key là tài sản nhạy cảm. Một file PEM không mã hóa có thể bị đọc bởi bất kỳ ai có quyền truy cập file. Thực hành cần áp dụng:

- Ưu tiên không export private key khỏi HSM/KMS nếu provider hoặc thiết bị được thiết kế để giữ key không thể xuất.
- Nếu bắt buộc trao đổi, mã hóa private key bằng password mạnh và chuyển password qua kênh riêng.
- Không lưu password trong source code, repository, command line, log, ticket hoặc cùng thư mục chia sẻ với PEM.
- Giới hạn quyền file và quyền đọc secret; dùng thư mục tạm có ACL phù hợp và xóa bản tạm sau khi sử dụng.
- Không ghi nội dung `ENCRYPTED PRIVATE KEY`, private key object hoặc password vào log/telemetry.
- Xác minh fingerprint của public key/certificate qua một kênh tin cậy trước khi tin khóa nhận được.
- Có quy trình rotate, revoke, backup và khôi phục khóa.

`PEMEncoder.withEncryption(password)` sử dụng thuật toán PBE mặc định. Security property `jdk.epkcs8.defaultAlgorithm` xác định thuật toán mặc định; tham số cụ thể phụ thuộc provider. Thông tin thuật toán và tham số được lưu trong encrypted PKCS #8 nên decoder có thể dùng thông tin trong dữ liệu để giải mã. Nếu cần thuật toán, tham số hoặc provider khác, dùng các phương thức mã hóa của `EncryptedPrivateKeyInfo`, rồi truyền object đó cho encoder.

Không tự giả định password encryption làm cho việc chia sẻ private key an toàn trong mọi tình huống. Password yếu có thể bị dò offline nếu attacker lấy được file. Dùng secret có entropy phù hợp và bảo vệ cả file lẫn password.

### Khóa không exportable

Một private key được giữ trong HSM hoặc hardware-backed provider có thể không cung cấp encoding (`getEncoded()` trả `null`). Khi đó không thể export nó thành PEM chỉ bằng cách gọi encoder. Đây là giới hạn bảo mật có chủ đích; không tìm cách trích xuất private key bằng reflection hoặc truy cập nội bộ provider. Nếu đối tác cần xác minh, thường chỉ cần export certificate/public key; private key tiếp tục ở lại HSM.

## 12. Xử lý lỗi và đầu vào không tin cậy

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `IllegalArgumentException` khi decode String | PEM malformed, không có PEM block hoặc type/encoding không phù hợp | Kiểm tra format, giới hạn kích thước input và type allowlist |
| `IOException` khi decode InputStream | Lỗi đọc hoặc PEM syntax không hợp lệ | Đóng stream; sau lỗi không tiếp tục dùng lại stream đó |
| `EOFException` | Stream kết thúc trước khi tìm thấy block/PEM footer | Kiểm tra file rỗng, cắt cụt hoặc sai framing |
| `ClassCastException` | Yêu cầu `decode(..., Class)` với class không khớp type PEM | Kiểm tra label và yêu cầu đúng kiểu, hoặc decode generic rồi phân loại |
| `CryptoException` | Lỗi xử lý mã hóa/giải mã hoặc password sai | Kiểm tra password, provider và thuật toán; không log secret |
| `IllegalArgumentException` khi encode | Đối tượng không có encoding hoặc kiểu không được hỗ trợ | Kiểm tra loại `BinaryEncodable` và khả năng export của key |
| `IllegalArgumentException` khi dùng encrypted encoder cho public key/certificate | `withEncryption()` chỉ hỗ trợ PrivateKey, KeyPair, PKCS8EncodedKeySpec | Dùng `PEMEncoder.of()` thông thường cho dữ liệu công khai |
| Decode thành `EncryptedPrivateKeyInfo` thay vì PrivateKey | Decoder chưa cấu hình `withDecryption()` | Dùng decoder đã cấu hình password hoặc xử lý EncryptedPrivateKeyInfo theo quy trình riêng |
| Certificate parse thành công nhưng TLS handshake thất bại | Chưa xác minh chain, hostname, EKU, thời hạn hoặc trust anchor | Chạy PKIX validation và endpoint identity checks |

Đầu vào PEM có thể rất lớn hoặc chứa nhiều block. Giới hạn kích thước file, số block, số byte Base64 và thời gian xử lý trước khi decode. Không nhận PEM từ request không tin cậy rồi đưa thẳng vào hệ thống truststore hoặc thay khóa production.

## 13. Kiểm thử round-trip và interoperability

Một bài kiểm thử tích hợp nên xác nhận nhiều lớp:

| Kiểm thử | Cách xác nhận |
|---|---|
| Public key round-trip | Encode rồi decode thành `PublicKey`; so sánh thuật toán và encoded bytes |
| Private key encrypted round-trip | Encode `KeyPair` với password, decode lại thành `KeyPair` bằng password đúng |
| Wrong password | Dùng password sai và xác nhận quá trình giải mã thất bại |
| Tampered PEM | Sửa Base64 hoặc tag/encrypted bytes và xác nhận parser/decrypt từ chối |
| Signature | Ký bằng private key đã decode và xác minh bằng public key đã decode |
| Certificate | Decode thành `X509Certificate`, kiểm tra thời hạn và validate trust chain |
| Unsupported label | Decode thành `PEM`, kiểm tra type và chỉ chuyển tới parser được allowlist |
| Multi-block | Đọc đúng số block và đúng thứ tự; xử lý EOF rõ ràng |
| Interoperability | Trao đổi PEM với OpenSSL hoặc hệ thống đối tác dùng PKCS #8/X.509 tương ứng |

Ví dụ assertion cho public key round-trip:

```java
byte[] originalEncoded = originalPair.getPublic().getEncoded();
byte[] importedEncoded = importedPublic.getEncoded();

if (!Arrays.equals(originalEncoded, importedEncoded)) {
    throw new AssertionError("Public key bytes không khớp");
}
```

Byte equality phù hợp với cùng loại key encoding chuẩn hóa. Với các format hoặc provider có representation khác nhau nhưng tương đương về mặt mật mã, hãy xác minh bằng thao tác mật mã thực tế như chữ ký hoặc trao đổi khóa, không dựa duy nhất vào byte equality.

Khi kiểm tra interoperability, xác nhận rõ đối tác dùng `PUBLIC KEY` (SubjectPublicKeyInfo), `PRIVATE KEY`/`ENCRYPTED PRIVATE KEY` (PKCS #8) hay một legacy label như `RSA PRIVATE KEY` (PKCS #1). Đừng giả định mọi PEM parser hỗ trợ cùng tập label. Ưu tiên PKCS #8 cho private key và X.509 SubjectPublicKeyInfo cho public key khi giao thức cho phép.

## 14. Trạng thái preview và tương thích

| Thành phần | JDK 27 |
|---|---|
| JEP 538 — PEM Encodings of Cryptographic Objects | Third Preview |
| `BinaryEncodable` | Preview API, `Since: 27` |
| `PEMEncoder`, `PEMDecoder` | Preview API |
| `PEM` | Preview class; không còn là record như API JDK 26 |
| `CryptoException` | Preview exception cho lỗi xử lý mật mã |
| Module | `java.base`, không cần thêm module |
| Compile/run | Cần `--enable-preview` trên JDK 27 |

Preview API có thể thay đổi hoặc bị loại bỏ trong release sau. Không nên xuất `BinaryEncodable`, `PEM`, `PEMEncoder` hoặc `PEMDecoder` trong public API của thư viện production dùng chung nếu chưa chấp nhận chi phí migrate. Có thể đóng gói chúng sau một interface nội bộ ổn định của ứng dụng để giảm phạm vi phụ thuộc preview.

Nếu hệ thống production không chấp nhận preview, tiếp tục dùng API JCA ổn định (`KeyFactory`, `KeyPairGenerator`, `CertificateFactory`, `EncryptedPrivateKeyInfo`, `Base64`) hoặc thư viện PEM đã được tổ chức phê duyệt. Đừng bật preview toàn bộ runtime chỉ để dùng một API thử nghiệm mà không đánh giá các preview khác trong ứng dụng.

## 15. Bài tập thực hành tích hợp

Xây dựng một tiện ích `KeyExchangeTool` để một dịch vụ gửi public key và certificate cho đối tác, đồng thời lưu private key đã mã hóa trong kho bí mật.

**Yêu cầu:**

1. Dùng JDK 27 và bật preview cho cả compile lẫn runtime.
2. Sinh cặp khóa Ed25519 bằng `KeyPairGenerator`.
3. Encode public key thành PEM label `PUBLIC KEY`.
4. Encode `KeyPair` thành PEM mã hóa password, tạo label `ENCRYPTED PRIVATE KEY`.
5. Decode public key bằng `decode(publicPem, PublicKey.class)`.
6. Decode private key bằng `withDecryption(password).decode(privatePem, KeyPair.class)`.
7. Ký một thông điệp đại diện cho giao dịch và xác minh chữ ký bằng public key đã decode.
8. Tạo certificate thử nghiệm bằng `keytool`, decode thành `X509Certificate` và kiểm tra thời hạn.
9. Mô tả cách xác minh certificate chain bằng PKIX; phân biệt việc parse certificate với việc tin certificate.
10. Thử decode PEM type không được hỗ trợ bằng `PEM.class`, kiểm tra `type()`, `content()`, `decode()` và `leadingData()`.
11. Thử password sai, PEM malformed, key không exportable và block bị cắt cụt.
12. Ghi nhận khác biệt API giữa JDK 26 second preview và JDK 27 third preview; không trộn source của hai release.

**Kết quả mong đợi:**

- Public key và encrypted private key round-trip thành công.
- Chữ ký tạo bằng private key đã decode được xác minh bởi public key tương ứng.
- Password không nằm trong source, log hoặc cùng gói trao đổi với private key.
- Certificate parse và validity check thành công; trust validation được thực hiện riêng theo PKIX policy.
- PEM type chưa hỗ trợ được giữ dưới dạng container tổng quát và chỉ xử lý sau khi kiểm tra allowlist.
- Ứng dụng compile/run với JDK 27 preview flags; không giả định API là final.
- Người học giải thích được khác biệt `DEREncodable`/`BinaryEncodable` và `PEM` record/class giữa JDK 26 và JDK 27.

## Tài liệu tham khảo

- [JEP 538: PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): phạm vi và trạng thái preview trong JDK 27.
- [PEMEncoder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html): các loại đối tượng hỗ trợ, encode và password encryption.
- [PEMDecoder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html): typed decode, InputStream, decryption và provider selection.
- [PEM — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html): generic PEM container, type, Base64 content và leading data.
- [BinaryEncodable — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html): marker interface và các loại cryptographic object được hỗ trợ.
- [JCA Reference Guide — The BinaryEncodable Interface](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): cách PEM API hoạt động với đối tượng mật mã và PKCS #8/X.509.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): JEP 538 Third Preview và các thay đổi JDK 27.
- [JDK 27 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html): các bản GA/update của JDK 27; Oracle ghi nhận 27.0.1.1 phát hành ngày 17-11-2026.
- [RFC 7468: Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html): quy tắc textual encoding cho các cấu trúc PKIX, PKCS và CMS.
- [RFC 5958: Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958.html): cấu trúc OneAsymmetricKey dùng trong PKCS #8 v2.0.
