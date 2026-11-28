# PEM Encodings preview lần 2 ở Java 26, lần 3 ở Java 27

## 1. Mục tiêu và trạng thái hiện hành

PEM (Privacy-Enhanced Mail) là định dạng văn bản dùng để lưu trữ hoặc trao đổi dữ liệu mật mã như khóa công khai, khóa riêng, chứng chỉ X.509 và danh sách thu hồi chứng chỉ (CRL). Java bổ sung API chuẩn hóa thao tác mã hóa và giải mã PEM trong package `java.security`.

Bài học tập trung vào hai vòng preview trong phạm vi Java 26 và Java 27:

| Phiên bản | JEP | Trạng thái |
|---|---|---|
| JDK 25 | JEP 470 | Preview lần đầu |
| JDK 26 | JEP 524 | Preview lần thứ hai |
| JDK 27 | JEP 538 | Preview lần thứ ba |
| JDK 28 | JEP 542 | Được target để hoàn tất API |

Tính đến ngày 27/11/2026:

- JDK 27 là feature release mới nhất đã phát hành chính thức. PEM API vẫn là preview lần thứ ba và phải bật preview khi biên dịch, chạy.
- JDK 28 đang ở giai đoạn Early Access. JEP 542 đã được target cho JDK 28; tài liệu API của JDK 28 EA build 25 hiện không còn đánh dấu các lớp PEM là preview. Tuy nhiên, tài liệu EA vẫn là bản nháp và JDK 28 chưa phải bản GA. Không dùng JDK 28 EA làm runtime production.
- Theo lộ trình Oracle, JDK 26 đã kết thúc vòng đời hỗ trợ vào tháng 09/2026. Chính sách hỗ trợ thực tế còn phụ thuộc nhà cung cấp JDK.

Vì vậy, phần code chính của bài dùng API JDK 27 Preview 3 để có thể thử nghiệm trên JDK GA hiện hành. Phần cuối giải thích thay đổi API giữa JDK 26, JDK 27 và tiến trình hoàn tất trong JDK 28.

## 2. PEM là gì và chứa dữ liệu nào?

Một khối PEM có cấu trúc văn bản như sau:

~~~text
-----BEGIN CERTIFICATE-----
MIIB...Base64-encoded-content...
-----END CERTIFICATE-----
~~~

Cấu trúc gồm:

1. Dòng bắt đầu có nhãn loại dữ liệu, ví dụ `CERTIFICATE`.
2. Nội dung nhị phân đã được mã hóa Base64, thường là dữ liệu DER.
3. Dòng kết thúc có cùng nhãn.

PEM là cách biểu diễn và vận chuyển dữ liệu nhị phân dưới dạng văn bản. Base64 không phải thuật toán mã hóa bảo mật. Một private key được lưu ở dạng `PRIVATE KEY` vẫn là khóa riêng không được bảo vệ bằng mật khẩu; bất kỳ ai đọc được file đều có thể lấy nội dung khóa.

PEM thường được dùng cho:

- Chứng chỉ X.509 và chuỗi chứng chỉ.
- Khóa công khai theo cấu trúc X.509 SubjectPublicKeyInfo.
- Khóa riêng theo cấu trúc PKCS #8.
- Khóa riêng đã mã hóa theo PKCS #8 EncryptedPrivateKeyInfo.
- Certificate Revocation List (CRL).
- Các cấu trúc PKI/CMS khác như CSR, PKCS #7 hoặc CMS khi ứng dụng cần giữ nguyên dữ liệu PEM mà Java chưa có lớp biểu diễn chuyên biệt.

### 2.1. Phân biệt các nhãn thường gặp

| PEM label | Dữ liệu thường chứa | Java type có thể nhận |
|---|---|---|
| `CERTIFICATE` | Chứng chỉ X.509 | `X509Certificate` |
| `X509 CRL` | Danh sách thu hồi chứng chỉ | `X509CRL` |
| `PUBLIC KEY` | Khóa công khai dạng SubjectPublicKeyInfo | `PublicKey` hoặc `X509EncodedKeySpec` |
| `PRIVATE KEY` | Khóa riêng PKCS #8 / OneAsymmetricKey | `PrivateKey`, `KeyPair` nếu có cả public key, hoặc `PKCS8EncodedKeySpec` |
| `ENCRYPTED PRIVATE KEY` | Khóa riêng PKCS #8 đã mã hóa | `EncryptedPrivateKeyInfo`, hoặc `PrivateKey` khi decoder được cấu hình giải mã |
| `CERTIFICATE REQUEST` | Yêu cầu ký chứng chỉ PKCS #10 | `PEM` tổng quát nếu không có lớp Java tương ứng |

Tên nhãn không tự chứng minh nội dung bên trong hợp lệ. Ví dụ, việc đổi nhãn một blob bất kỳ thành `CERTIFICATE` không biến blob đó thành chứng chỉ X.509.

### 2.2. Phân biệt PEM, DER, PKCS #8 và X.509

- **DER** là cách mã hóa nhị phân xác định của cấu trúc ASN.1.
- **PEM** bọc nội dung nhị phân bằng Base64 và header/footer để dễ lưu trữ, truyền qua hệ thống văn bản.
- **PKCS #8** định nghĩa cấu trúc lưu khóa riêng, độc lập với thuật toán khóa.
- **X.509 SubjectPublicKeyInfo** định nghĩa cấu trúc phổ biến để lưu khóa công khai.
- **X.509 Certificate** chứa thông tin định danh, khóa công khai, thời hạn và chữ ký của tổ chức phát hành.

PEM không thay thế PKCS #8, X.509 hoặc DER. Nó chỉ là lớp biểu diễn văn bản bên ngoài.

## 3. API PEM trong Java

Hai lớp chính của API:

- `java.security.PEMEncoder`: mã hóa đối tượng mật mã thành chuỗi hoặc mảng byte PEM.
- `java.security.PEMDecoder`: giải mã nội dung PEM thành đối tượng Java.

Các API liên quan:

| API | Vai trò |
|---|---|
| `BinaryEncodable` | Giao diện preview chung cho đối tượng có biểu diễn nhị phân có thể chuyển đổi |
| `PEM` | Đại diện PEM tổng quát khi không có lớp Java chuyên biệt |
| `EncryptedPrivateKeyInfo` | Đại diện khóa riêng PKCS #8 đã mã hóa |
| `PKCS8EncodedKeySpec` | Biểu diễn nhị phân khóa riêng PKCS #8 |
| `X509EncodedKeySpec` | Biểu diễn nhị phân khóa công khai X.509 |

### 3.1. Mã hóa bằng PEMEncoder

Tạo encoder mặc định:

~~~java
PEMEncoder encoder = PEMEncoder.of();
~~~

Mã hóa một đối tượng thành chuỗi:

~~~java
String pem = encoder.encodeToString(publicKey);
~~~

Mã hóa thành byte array:

~~~java
byte[] pemBytes = encoder.encode(privateKey);
~~~

Encoder mặc định hỗ trợ các loại đối tượng như `X509Certificate`, `X509CRL`, `PublicKey`, `PrivateKey`, `KeyPair`, `EncryptedPrivateKeyInfo`, `X509EncodedKeySpec`, `PKCS8EncodedKeySpec` và `PEM`.

Một `KeyPair` được mã hóa theo cấu trúc PKCS #8 v2.0 OneAsymmetricKey với nhãn `PRIVATE KEY`. Cấu trúc này có thể chứa cả khóa riêng và khóa công khai.

### 3.2. Giải mã bằng PEMDecoder

Tạo decoder mặc định:

~~~java
PEMDecoder decoder = PEMDecoder.of();
~~~

Nếu biết trước kiểu dữ liệu, nên dùng overload nhận `Class` để có kiểu trả về cụ thể:

~~~java
PublicKey publicKey =
        decoder.decode(publicKeyPem, PublicKey.class);

PrivateKey privateKey =
        decoder.decode(privateKeyPem, PrivateKey.class);

X509Certificate certificate =
        decoder.decode(certificatePem, X509Certificate.class);
~~~

Cách này tránh ép kiểu thủ công và giúp phát hiện sớm trường hợp nhãn PEM không khớp kiểu dữ liệu yêu cầu.

Nếu dùng `decode(String)` không truyền `Class`, decoder trả về kiểu `BinaryEncodable` phù hợp nhất với nhãn PEM. Ví dụ:

- `CERTIFICATE` trả `X509Certificate`.
- `PUBLIC KEY` trả `PublicKey`.
- `PRIVATE KEY` trả `PrivateKey` hoặc `KeyPair` nếu nội dung chứa cả khóa công khai.
- `ENCRYPTED PRIVATE KEY` trả `EncryptedPrivateKeyInfo` nếu decoder chưa được cấu hình giải mã.
- Nhãn không có lớp Java tương ứng trả về `PEM`.

Nếu `Class` được yêu cầu không khớp với nội dung, decoder ném `ClassCastException`. Nếu cú pháp PEM không hợp lệ hoặc không tìm thấy khối PEM, phương thức có thể ném `IllegalArgumentException`; giải mã từ `InputStream` còn có thể ném `IOException` hoặc `EOFException`.

## 4. Ví dụ: mã hóa và giải mã KeyPair

Tạo cặp khóa EC bằng JCA, mã hóa thành PEM và giải mã trở lại:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

public class PemKeyPairDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));

        KeyPair original = generator.generateKeyPair();

        // Mã hóa KeyPair thành một khối PRIVATE KEY.
        String keyPairPem = PEMEncoder.of().encodeToString(original);

        // Khôi phục cả public key và private key.
        KeyPair restored = PEMDecoder.of()
                .decode(keyPairPem, KeyPair.class);

        if (!Arrays.equals(
                original.getPublic().getEncoded(),
                restored.getPublic().getEncoded())) {
            throw new AssertionError("Public key không khớp");
        }

        if (!Arrays.equals(
                original.getPrivate().getEncoded(),
                restored.getPrivate().getEncoded())) {
            throw new AssertionError("Private key không khớp");
        }

        System.out.println("PEM KeyPair round-trip thành công.");
    }
}
~~~

Nếu chỉ muốn lưu khóa công khai:

~~~java
String publicPem =
        PEMEncoder.of().encodeToString(original.getPublic());

PublicKey publicKey = PEMDecoder.of()
        .decode(publicPem, PublicKey.class);
~~~

Nếu chỉ muốn lưu khóa riêng PKCS #8:

~~~java
String privatePem =
        PEMEncoder.of().encodeToString(original.getPrivate());

PrivateKey privateKey = PEMDecoder.of()
        .decode(privatePem, PrivateKey.class);
~~~

Không in private key PEM vào log hoặc terminal dùng chung. Ví dụ chỉ xác nhận việc khôi phục bằng cách so sánh encoding, không hiển thị dữ liệu khóa.

## 5. Đọc chứng chỉ X.509 và CRL

### 5.1. Đọc chứng chỉ từ file PEM

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.cert.X509Certificate;

public class PemCertificateDemo {
    public static void main(String[] args) throws Exception {
        String pemText = Files.readString(
                Path.of("server-certificate.pem")
        );

        X509Certificate certificate = PEMDecoder.of()
                .decode(pemText, X509Certificate.class);

        System.out.println("Subject: "
                + certificate.getSubjectX500Principal());
        System.out.println("Issuer: "
                + certificate.getIssuerX500Principal());
        System.out.println("Valid from: " + certificate.getNotBefore());
        System.out.println("Valid until: " + certificate.getNotAfter());

        String exportedPem =
                PEMEncoder.of().encodeToString(certificate);

        Files.writeString(
                Path.of("server-certificate-copy.pem"),
                exportedPem
        );
    }
}
~~~

Việc decode thành công chỉ chứng minh dữ liệu PEM có thể được chuyển thành một đối tượng chứng chỉ X.509. Nó chưa chứng minh chứng chỉ đáng tin cậy hoặc phù hợp với máy chủ đang kết nối.

Trước khi tin chứng chỉ, ứng dụng vẫn phải kiểm tra các điều kiện phù hợp:

- Thời hạn chứng chỉ còn hiệu lực.
- Chuỗi chứng chỉ dẫn tới trust anchor đáng tin cậy.
- Chữ ký chứng chỉ và các ràng buộc PKI hợp lệ.
- Tên máy chủ khớp với Subject Alternative Name khi dùng TLS.
- Key Usage và Extended Key Usage phù hợp với mục đích sử dụng.
- Trạng thái thu hồi nếu chính sách yêu cầu kiểm tra CRL hoặc OCSP.

PEM chỉ là định dạng trao đổi; nó không thực hiện các bước xác minh PKI này.

### 5.2. Đọc CRL

CRL cũng có thể được decode thành `X509CRL`:

~~~java
X509CRL crl = PEMDecoder.of()
        .decode(crlPem, X509CRL.class);
~~~

Có thể dùng `X509CRL` để kiểm tra thông tin phát hành, thời điểm cập nhật và trạng thái thu hồi của serial number. Việc xác minh chữ ký CRL và issuer vẫn cần được thực hiện theo chính sách PKI.

## 6. Mã hóa private key bằng mật khẩu

### 6.1. Dùng withEncryption và withDecryption

`PEMEncoder.withEncryption(char[])` trả về một encoder mới được cấu hình mã hóa khóa riêng bằng mật khẩu:

~~~java
PEMEncoder encryptedEncoder =
        PEMEncoder.of().withEncryption(password);
~~~

Encoder đã cấu hình mã hóa chỉ hỗ trợ các đối tượng:

- `PrivateKey`
- `KeyPair`
- `PKCS8EncodedKeySpec`

Nếu truyền chứng chỉ hoặc public key vào encoder đã cấu hình mã hóa, API ném `IllegalArgumentException`.

Ví dụ mã hóa và giải mã private key:

~~~java
String encryptedPrivatePem = PEMEncoder.of()
        .withEncryption(password)
        .encodeToString(privateKey);

PrivateKey restoredPrivateKey = PEMDecoder.of()
        .withDecryption(password)
        .decode(encryptedPrivatePem, PrivateKey.class);
~~~

Khi decoder chưa được cấu hình `withDecryption`, khối `ENCRYPTED PRIVATE KEY` được trả về dưới dạng `EncryptedPrivateKeyInfo`. Khi decoder được cấu hình giải mã, nó có thể trả trực tiếp `PrivateKey` hoặc `KeyPair` nếu dữ liệu có cả public key.

### 6.2. Ví dụ hoàn chỉnh với mật khẩu nhập từ Console

~~~java
import java.io.Console;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

public class PemEncryptedKeyDemo {
    static String encryptPrivateKey(
            PrivateKey privateKey,
            char[] password
    ) {
        return PEMEncoder.of()
                .withEncryption(password)
                .encodeToString(privateKey);
    }

    static PrivateKey decryptPrivateKey(
            String encryptedPem,
            char[] password
    ) {
        return PEMDecoder.of()
                .withDecryption(password)
                .decode(encryptedPem, PrivateKey.class);
    }

    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Hãy chạy chương trình từ terminal có Console."
            );
        }

        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair keyPair = generator.generateKeyPair();

        char[] password = console.readPassword(
                "Nhập mật khẩu bảo vệ private key: "
        );

        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Mật khẩu không hợp lệ");
        }

        try {
            String encryptedPem = encryptPrivateKey(
                    keyPair.getPrivate(),
                    password
            );

            PrivateKey restored = decryptPrivateKey(
                    encryptedPem,
                    password
            );

            if (!Arrays.equals(
                    keyPair.getPrivate().getEncoded(),
                    restored.getEncoded())) {
                throw new AssertionError("Private key không khớp");
            }

            System.out.println("Encrypted PEM round-trip thành công.");
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Trong ví dụ, khóa được tạo bằng JCA để minh họa vòng đời encode/decode. Ở ứng dụng thật, khóa nên được nạp từ kho khóa hoặc nguồn được quản lý và xác minh nguồn gốc trước khi sử dụng.

API clone mảng mật khẩu khi tạo encoder/decoder cấu hình. Xóa mảng mật khẩu phía ứng dụng sau khi dùng giúp giảm thời gian giữ bản sao do ứng dụng quản lý, nhưng không phải cam kết xóa sạch mọi bản sao trong bộ nhớ JVM hoặc provider.

### 6.3. Thuật toán mã hóa mặc định

Khi dùng `withEncryption(char[])`, JDK chọn thuật toán PBE mặc định. Security property:

~~~text
jdk.epkcs8.defaultAlgorithm
~~~

quy định thuật toán mặc định. Các tham số mặc định còn phụ thuộc provider. Giá trị mặc định có thể thay đổi trong bản JDK tương lai.

Dữ liệu `ENCRYPTED PRIVATE KEY` lưu kèm thuật toán và tham số cần thiết để giải mã, vì vậy thay đổi giá trị mặc định không làm mất thông tin thuật toán của các PEM đã tạo trước đó.

Trong môi trường có chính sách mật mã bắt buộc, không nên dựa vào mặc định không được kiểm soát. Hãy kiểm tra security property và provider đang dùng; nếu cần chỉ định rõ thuật toán hoặc tham số, dùng `EncryptedPrivateKeyInfo.encrypt(...)`.

## 7. Tùy chỉnh thuật toán và provider với EncryptedPrivateKeyInfo

`EncryptedPrivateKeyInfo` biểu diễn cấu trúc khóa riêng đã mã hóa theo PKCS #8. JDK 27 bổ sung các phương thức preview để mã hóa trực tiếp một `BinaryEncodable`.

Ví dụ dùng thuật toán PBE cụ thể:

~~~java
import java.security.PrivateKey;
import java.security.PEMEncoder;
import javax.crypto.EncryptedPrivateKeyInfo;

static String encryptWithExplicitAlgorithm(
        PrivateKey privateKey,
        char[] password
) {
    EncryptedPrivateKeyInfo encrypted =
            EncryptedPrivateKeyInfo.encrypt(
                    privateKey,
                    password,
                    "PBEWithHmacSHA256AndAES_256",
                    null,
                    null
            );

    return PEMEncoder.of().encodeToString(encrypted);
}
~~~

Trong ví dụ:

- Tham số thứ nhất là đối tượng cần mã hóa; hỗ trợ `PrivateKey`, `KeyPair` hoặc `PKCS8EncodedKeySpec`.
- Tham số thứ hai là mật khẩu.
- Tham số thứ ba là tên thuật toán PBE.
- Tham số `AlgorithmParameterSpec` là `null` để provider chọn tham số mặc định.
- Tham số `Provider` là `null` để JCA chọn provider theo thứ tự cấu hình.

Chỉ dùng tên thuật toán khi provider triển khai có hỗ trợ. Nếu yêu cầu kiểm soát tham số KDF, số vòng lặp, salt hoặc provider, hãy truyền cấu hình tường minh và kiểm tra tương thích với hệ thống cần giải mã.

Có thể giải mã theo hai bước:

~~~java
EncryptedPrivateKeyInfo encrypted = PEMDecoder.of()
        .decode(encryptedPem, EncryptedPrivateKeyInfo.class);

PrivateKey privateKey = encrypted.getKey(password);
~~~

Hoặc cấu hình decoder để giải mã trực tiếp:

~~~java
PrivateKey privateKey = PEMDecoder.of()
        .withDecryption(password)
        .decode(encryptedPem, PrivateKey.class);
~~~

### 7.1. Khi nào cần chỉ định provider?

`PEMDecoder.withFactoriesOf(Provider)` tạo decoder sử dụng `KeyFactory` và `CertificateFactory` từ provider được chỉ định khi tạo đối tượng mật mã.

Ví dụ:

~~~java
Provider provider = Security.getProvider("MyCryptoProvider");

if (provider == null) {
    throw new IllegalStateException("Provider chưa được cài đặt");
}

PEMDecoder decoder = PEMDecoder.of()
        .withFactoriesOf(provider);

PrivateKey key = decoder.decode(
        privateKeyPem,
        PrivateKey.class
);
~~~

Chỉ chỉ định provider khi ứng dụng có yêu cầu rõ ràng, chẳng hạn provider HSM hoặc provider đáp ứng chính sách FIPS. Đừng hard-code tên provider nếu runtime triển khai không bảo đảm có provider đó.

## 8. PEM tổng quát cho loại dữ liệu chưa có lớp Java

Không phải mọi nhãn PEM đều có lớp biểu diễn chuyên biệt trong Java. Ví dụ, Java SE không cung cấp lớp PKCS #10 CSR trong `java.security` tương ứng với `X509Certificate`.

Khi gặp nhãn không có lớp tương ứng, decoder trả về đối tượng `PEM` tổng quát:

~~~java
PEM request = PEMDecoder.of().decode(
        csrPem,
        PEM.class
);

System.out.println("PEM type: " + request.type());

byte[] base64Content = request.content();
byte[] decodedContent = request.decode();
byte[] leadingData = request.leadingData();
~~~

Trong JDK 27:

- `type()` trả về nhãn PEM, ví dụ `CERTIFICATE REQUEST`.
- `content()` trả về nội dung Base64 dưới dạng byte array.
- `decode()` trả về nội dung nhị phân sau khi giải mã Base64.
- `leadingData()` trả về dữ liệu xuất hiện trước header PEM, hoặc `null` nếu không có.

Có thể mã hóa đối tượng `PEM` trở lại văn bản:

~~~java
String pemText = PEMEncoder.of().encodeToString(request);
~~~

Dữ liệu `leadingData` không được đưa vào chuỗi PEM khi encode lại. Nếu metadata ở phần đầu file có ý nghĩa, ứng dụng phải lưu và xử lý riêng.

Đối tượng `PEM` không xác minh nội dung Base64 có đúng cấu trúc của nhãn hay không. Ví dụ, constructor có thể tạo một đối tượng mang nhãn `CERTIFICATE REQUEST` nhưng nội dung không phải CSR hợp lệ. Việc parse và xác minh cấu trúc PKCS #10 phải do API hoặc thư viện chuyên biệt thực hiện.

Không dùng `PEM` tổng quát như bằng chứng rằng khóa, chứng chỉ hoặc CSR đã được kiểm tra mật mã.

## 9. Định dạng được hỗ trợ và giới hạn tương thích

### 9.1. Ưu tiên định dạng chuẩn hóa

Để tăng khả năng tương thích giữa JDK, OpenSSL và các hệ thống PKI, nên trao đổi theo các định dạng chuẩn:

| Mục đích | Định dạng nên dùng |
|---|---|
| Khóa công khai | X.509 SubjectPublicKeyInfo, nhãn `PUBLIC KEY` |
| Khóa riêng | PKCS #8, nhãn `PRIVATE KEY` |
| Khóa riêng có mật khẩu | PKCS #8 EncryptedPrivateKeyInfo, nhãn `ENCRYPTED PRIVATE KEY` |
| Chứng chỉ | X.509 Certificate, nhãn `CERTIFICATE` |
| Danh sách thu hồi | X.509 CRL, nhãn `X509 CRL` |

Một số công cụ có thể tạo định dạng khóa riêng gắn với thuật toán hoặc công cụ cụ thể, ví dụ `RSA PRIVATE KEY`, `EC PRIVATE KEY` hoặc `OPENSSH PRIVATE KEY`. Chúng không phải cùng một cấu trúc PKCS #8 chuẩn hóa mà API portable tập trung hỗ trợ.

Implementation Oracle JDK có ghi chú nhận dạng một số trường hợp RSA private key không mã hóa với nhãn `RSA PRIVATE KEY`; đây là ghi chú implementation, không nên xem là cam kết tương thích của mọi JDK hoặc mọi provider. Khi kiểm soát được định dạng đầu ra, hãy chuyển sang PKCS #8 `PRIVATE KEY` hoặc `ENCRYPTED PRIVATE KEY`.

### 9.2. PEM bundle và nhiều khối liên tiếp

Một file PEM có thể chứa nhiều khối nối tiếp, ví dụ:

~~~text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
~~~

Mỗi khối có nhãn riêng. Không giả định một lần gọi `decode(String)` trả về tất cả các khối trong bundle; overload này trả về một đối tượng tương ứng với PEM được giải mã. Nếu cần đọc tuần tự, dùng `InputStream` và quản lý từng lần decode theo đúng ranh giới footer.

Khi đọc từ `InputStream`, nếu có lỗi I/O, vị trí stream có thể không còn nhất quán. Tài liệu API khuyến cáo không tiếp tục giải mã từ cùng stream sau lỗi I/O đó.

### 9.3. Provider có thể hỗ trợ thêm loại PEM

Danh sách loại dữ liệu được hỗ trợ bởi implementation mặc định không phải danh sách tối đa cho mọi provider. Một provider khác có thể nhận dạng thêm loại PEM. Vì vậy, ứng dụng cần xử lý trường hợp decoder trả `PEM` tổng quát thay vì giả định mọi nhãn đều có Java class.

## 10. Khác biệt API giữa JDK 26 và JDK 27

JDK 26 dùng JEP 524 (preview lần thứ hai). JDK 27 dùng JEP 538 (preview lần thứ ba). Một số thay đổi quan trọng:

| Nội dung | JDK 26 — JEP 524 | JDK 27 — JEP 538 |
|---|---|---|
| Giao diện dữ liệu nhị phân | `DEREncodable` | Đổi tên thành `BinaryEncodable` |
| Lớp `PEM` | Record | Class final |
| Nội dung Base64 trong `PEM` | `String` | `byte[]` |
| Dữ liệu leading | Mảng byte có thể được chia sẻ trực tiếp theo semantics record | Mảng byte được defensive copy |
| Giải mã nội dung PEM tổng quát | `PEM` record | `PEM` class với `content()`, `decode()`, `type()`, `leadingData()` |
| Lỗi mật mã | Dùng các exception hiện có của preview trước | Bổ sung `CryptoException` cho lỗi xử lý mật mã |
| Mã hóa khóa riêng | Có `withEncryption` | Tiếp tục hỗ trợ, đồng thời mở rộng xử lý `EncryptedPrivateKeyInfo` |
| Chỉ định provider khi decode | Chưa có `withFactoriesOf` trong API JDK 26 | Có `withFactoriesOf(Provider)` |
| Các kiểu mã hóa | Hỗ trợ các đối tượng DER preview | Dùng `BinaryEncodable` cho đối tượng có biểu diễn nhị phân, không giới hạn tên gọi ở DER |

Điểm cần chú ý khi chuyển code JDK 26 sang JDK 27:

- Thay `DEREncodable` bằng `BinaryEncodable`.
- Không dùng `PEM.content()` như một `String` trong JDK 27; nó trả về byte array chứa nội dung Base64.
- `PEM.decode()` trả byte array đã giải mã Base64.
- `PEM` không còn là record; không dựa vào record accessor semantics hoặc việc chia sẻ mảng `leadingData`.
- Xử lý `CryptoException` khi encode/decode có mã hóa.
- Dùng `withFactoriesOf(Provider)` nếu cần điều khiển provider tạo KeyFactory/CertificateFactory.

Không sao chép code JDK 26 preview vào JDK 27 mà không kiểm tra kiểu dữ liệu và chữ ký API. Preview có thể thay đổi giữa các feature release.

## 11. Tiến trình JDK 28 và cách chọn runtime

JEP 542 đã được target cho JDK 28 để hoàn tất PEM API sau ba vòng preview ở JDK 25, 26 và 27.

Tài liệu Java SE 28 Early Access build 25 hiện thể hiện:

- `PEMEncoder`, `PEMDecoder`, `PEM` và `BinaryEncodable` không còn dấu preview.
- Các phương thức `encode`, `encodeToString`, `decode`, `withEncryption`, `withDecryption` và `withFactoriesOf` vẫn hiện diện.
- Chữ ký API hiện gần với JDK 27, nhưng đây là tài liệu draft của JDK 28 EA và có thể tiếp tục thay đổi.

Cách chọn runtime:

| Mục đích | Runtime và cờ |
|---|---|
| Ứng dụng production cần JDK đã phát hành | Dùng JDK GA còn được nhà cung cấp hỗ trợ; nếu dùng PEM API trên JDK 27 thì chấp nhận preview |
| Thử nghiệm PEM API JDK 27 | JDK 27 với `--enable-preview` ở cả compile và run |
| Kiểm thử tương thích với API hoàn tất dự kiến | JDK 28 Early Access; tài liệu EA hiện không đánh dấu PEM API preview |
| Production trong tương lai | Chờ JDK 28 GA và xác nhận API cuối cùng trong tài liệu release chính thức |

JDK 26 đã hết vòng đời hỗ trợ theo lộ trình Oracle từ tháng 09/2026. Không chọn JDK 26 làm runtime triển khai mới chỉ vì bài học mang tên Java 26.

## 12. Biên dịch và chạy với JDK 27 Preview

PEM API trong JDK 27 là preview feature. Cần bật preview ở cả compiler và runtime:

~~~bash
javac --release 27 --enable-preview -d out PemKeyPairDemo.java
java --enable-preview -cp out PemKeyPairDemo
~~~

Nếu thử trên JDK 26 còn được nhà cung cấp hỗ trợ, thay `27` bằng `26`:

~~~bash
javac --release 26 --enable-preview -d out PemKeyPairDemo.java
java --enable-preview -cp out PemKeyPairDemo
~~~

PEM API nằm trong module `java.base`; không cần thêm module incubator.

Khi thử bằng JDK 28 Early Access build có API PEM không còn đánh dấu preview trong tài liệu tương ứng, không dùng `--enable-preview` cho PEM API. Tuy nhiên, chỉ dùng EA để kiểm thử tương thích, không triển khai production.

Nếu compiler không nhận ra `PEMEncoder`, `PEMDecoder` hoặc `BinaryEncodable`, hãy kiểm tra:

1. Compiler có đúng JDK 27 trở lên không.
2. `--release` có đang đặt thấp hơn 27 không.
3. `--enable-preview` đã được bật khi biên dịch chưa.
4. Runtime có cùng feature release với compiler không.
5. IDE, CI và terminal có thực sự dùng cùng JDK không.

## 13. Nguyên tắc bảo mật khi vận hành PEM

PEM chỉ định dạng dữ liệu. An toàn phụ thuộc cách quản lý khóa, chứng chỉ, mật khẩu, provider và chuỗi tin cậy.

- Không commit private key hoặc PEM chứa private key vào Git, artifact công khai, ticket hoặc log.
- Không in nội dung `PRIVATE KEY` hay `ENCRYPTED PRIVATE KEY` ra console/log.
- Dùng secret manager hoặc cơ chế cấp phát mật khẩu an toàn; không hard-code password.
- Giữ private key ở trạng thái không mã hóa chỉ khi có lý do rõ ràng và storage được bảo vệ phù hợp.
- Nếu khóa không cần export, cân nhắc HSM, smart card hoặc dịch vụ quản lý khóa thay vì xuất ra PEM.
- Dùng PKCS #8 `ENCRYPTED PRIVATE KEY` khi cần lưu trữ private key có mật khẩu.
- Chọn thuật toán PBE và tham số theo chính sách mật mã hiện hành; kiểm tra provider hỗ trợ trước khi triển khai.
- Xác minh chứng chỉ và chuỗi tin cậy độc lập sau khi decode.
- Kiểm tra public key trong chứng chỉ khớp với private key dự định sử dụng.
- Không xem việc Base64 decode thành công là xác minh chữ ký, nguồn gốc hoặc tính hợp lệ của dữ liệu.
- Khi nhận PEM từ nguồn không tin cậy, giới hạn kích thước input, số khối, số lần parse và xử lý lỗi có kiểm soát.

Nếu ứng dụng sử dụng nhiều provider, hãy kiểm thử trên đúng provider và runtime triển khai. API PEM tạo đối tượng qua JCA; việc một provider hỗ trợ thuật toán hoặc định dạng cụ thể vẫn là điều kiện cần được xác minh.

## 14. Checklist tích hợp

Trước khi đưa PEM vào ứng dụng:

1. Xác nhận JDK GA và trạng thái preview của đúng phiên bản.
2. Xác định rõ PEM label và cấu trúc bên trong: X.509, PKCS #8, CRL hay dữ liệu khác.
3. Dùng `decode(String, Class)` hoặc `decode(InputStream, Class)` khi biết kiểu dữ liệu mong đợi.
4. Dùng `PEM` tổng quát khi cần giữ dữ liệu không có lớp Java tương ứng; không coi đó là parse/validate hoàn chỉnh.
5. Nếu private key cần mã hóa, chọn chính sách PBE và kiểm tra provider.
6. Quản lý mật khẩu bằng secret manager hoặc nguồn nhập an toàn.
7. Kiểm tra chuỗi chứng chỉ, thời hạn, hostname, mục đích sử dụng và thu hồi theo chính sách PKI.
8. Kiểm thử round-trip encode/decode bằng so sánh encoding hoặc kiểm tra chữ ký.
9. Kiểm thử lỗi với PEM sai cú pháp, sai nhãn, sai mật khẩu, sai provider và dữ liệu bị cắt.
10. Đánh giá khả năng tương thích với OpenSSL hoặc hệ thống bên ngoài bằng fixture thực tế.
11. Cô lập preview API trong adapter/module nội bộ để dễ nâng cấp khi JDK 28 GA hoặc khi preview tiếp tục thay đổi.

## 15. Kết luận

PEM API cung cấp cách thống nhất để chuyển đổi khóa, chứng chỉ và CRL giữa đối tượng Java và định dạng PEM:

- `PEMEncoder` tạo PEM từ `BinaryEncodable`.
- `PEMDecoder` chuyển PEM thành đối tượng Java có kiểu cụ thể.
- `withEncryption` và `withDecryption` hỗ trợ mã hóa/giải mã private key PKCS #8 bằng mật khẩu.
- `EncryptedPrivateKeyInfo` cho phép kiểm soát thuật toán PBE và tham số.
- `PEM` giữ dữ liệu PEM chưa có lớp Java tương ứng, nhưng không tự xác minh nội dung.
- JDK 26 dùng JEP 524 Preview 2; JDK 27 dùng JEP 538 Preview 3 với các thay đổi quan trọng về `BinaryEncodable` và lớp `PEM`.
- JEP 542 được target cho JDK 28; tài liệu JDK 28 EA hiện không còn đánh dấu PEM API preview, nhưng chỉ nên dùng EA để kiểm thử cho đến khi bản GA phát hành.

Hãy xem PEM như một lớp định dạng trao đổi. Việc mã hóa Base64 không bảo vệ bí mật, và việc decode thành công không xác minh độ tin cậy của khóa hoặc chứng chỉ. Quản lý khóa, mật khẩu, provider và kiểm tra PKI vẫn là trách nhiệm riêng của ứng dụng.

## Tài liệu tham khảo chính thức

- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview, JDK 26)](https://openjdk.org/jeps/524)
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview, JDK 27)](https://openjdk.org/jeps/538)
- [JEP 542 — PEM Encodings of Cryptographic Objects (targeted JDK 28)](https://openjdk.org/jeps/542)
- [PEMEncoder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html)
- [PEMDecoder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html)
- [PEM — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEM.html)
- [PEMEncoder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html)
- [PEMDecoder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html)
- [PEM — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html)
- [BinaryEncodable — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html)
- [EncryptedPrivateKeyInfo — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html)
- [JCA Reference Guide — Java SE 27, PEM Encoding and Decoding](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html)
- [JDK 27 Security Enhancements — Inside Java](https://inside.java/2026/09/16/jdk27-security-enhancements/)
- [JEP 542 targeted to JDK 28 — Inside Java](https://inside.java/2026/10/06/jep542-target-jdk28/)
- [PEMEncoder — Java SE 28 Early Access API](https://download.java.net/java/early_access/jdk28/docs/api/java.base/java/security/PEMEncoder.html)
- [PEMDecoder — Java SE 28 Early Access API](https://download.java.net/java/early_access/jdk28/docs/api/java.base/java/security/PEMDecoder.html)
- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html)
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958.html)

