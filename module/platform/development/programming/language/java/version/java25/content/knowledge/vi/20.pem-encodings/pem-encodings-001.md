# Mục tiêu và trạng thái preview của PEM Encodings of Cryptographic Objects trong JDK 25

## Mục tiêu bài học

**PEM (Privacy-Enhanced Mail)** là định dạng văn bản dùng để trao đổi dữ liệu mật mã nhị phân như khóa công khai, khóa riêng, chứng chỉ X.509 và danh sách thu hồi chứng chỉ (CRL). PEM bao bọc dữ liệu nhị phân đã mã hóa Base64 bằng nhãn ở phần đầu và cuối, ví dụ `-----BEGIN CERTIFICATE-----` và `-----END CERTIFICATE-----`.

Trước JDK 25, ứng dụng Java thường phải kết hợp nhiều API để chuyển đổi giữa PEM text, DER bytes, `KeySpec`, `KeyFactory`, `CertificateFactory` và các đối tượng khóa/chứng chỉ. **JEP 470 — PEM Encodings of Cryptographic Objects** giới thiệu một API thống nhất trong package `java.security` để mã hóa và giải mã các đối tượng mật mã phổ biến.

Tính năng xuất hiện lần đầu dưới dạng **preview trong JDK 25**. Đến JDK 27, API vẫn đang preview ở lần thứ ba theo JEP 538. Trong các lần preview, tên và kiểu dữ liệu của API đã thay đổi; ví dụ hiện hành trong bài dùng API JDK 27, còn phần lịch sử JDK 25 chỉ giúp nhận diện khác biệt khi nâng cấp.

Sau bài này, bạn có thể:

1. Giải thích PEM là định dạng vận chuyển văn bản cho dữ liệu mật mã nhị phân, không phải thuật toán mã hóa.
2. Nêu mục tiêu của JEP 470 và trạng thái preview của API trong JDK 25.
3. Nhận diện các kiểu PEM phổ biến như `CERTIFICATE`, `PUBLIC KEY`, `PRIVATE KEY` và `ENCRYPTED PRIVATE KEY`.
4. Dùng `PEMEncoder` và `PEMDecoder` trong API preview hiện hành của JDK 27.
5. Mã hóa và giải mã `PrivateKey`, `PublicKey`, `KeyPair`, `X509Certificate` và `X509CRL`.
6. Xử lý PEM type chưa có lớp mật mã tương ứng thông qua `PEM`.
7. Mã hóa/giải mã private key PKCS #8 có bảo vệ bằng mật khẩu.
8. Phân biệt giải mã PEM với xác thực chứng chỉ, xác minh chữ ký và kiểm tra chuỗi tin cậy.
9. Biên dịch và chạy đúng phiên bản preview tương ứng với JDK đang sử dụng.
10. Nhận biết các thay đổi API giữa JDK 25, JDK 26 và JDK 27 để tránh sao chép mã preview cũ vào runtime mới.

> **Trạng thái hiện hành tại JDK 27:** PEM Encodings of Cryptographic Objects vẫn là preview API, lần thứ ba theo JEP 538. JDK 25 dùng JEP 470 (preview đầu tiên), JDK 26 dùng JEP 524 (preview thứ hai). Không xem API này là Java SE permanent API và không giả định mã nguồn preview của JDK 25 sẽ biên dịch nguyên trạng trên JDK 27.

## 1. PEM giải quyết vấn đề gì?

Nhiều hệ thống chỉ thuận tiện khi trao đổi dữ liệu dạng văn bản ASCII. Trong khi đó, khóa và chứng chỉ thường được lưu dưới dạng cấu trúc nhị phân ASN.1/DER. PEM kết hợp hai phần:

1. **Nhãn (type label):** cho biết loại dữ liệu nằm trong khối.
2. **Nội dung Base64:** biểu diễn dữ liệu nhị phân dưới dạng văn bản.

Ví dụ cấu trúc:

~~~text
-----BEGIN CERTIFICATE-----
MIIC...Base64 data...
...more Base64 data...
-----END CERTIFICATE-----
~~~

PEM thường xuất hiện trong:

- Certificate Authority (CA) phát hành certificate chain.
- TLS server/client cấu hình chứng chỉ và private key.
- Hệ thống quản lý khóa và secret.
- Công cụ như OpenSSL và hạ tầng certificate management.
- Thiết bị bảo mật, HSM hoặc token cần trao đổi certificate/key material.

PEM không định nghĩa một thuật toán mật mã mới. Nó là định dạng văn bản để đóng gói và trao đổi dữ liệu nhị phân theo các cấu trúc chuẩn như X.509 và PKCS #8.

### 1.1. Những phần ứng dụng thường phải tự làm

Nếu tự xử lý PEM bằng API cấp thấp, code thường phải:

- Tìm header/footer và tách type label.
- Lấy phần Base64 bên trong.
- Giải mã Base64 thành DER bytes.
- Chọn đúng `KeyFactory`, `CertificateFactory` hoặc `KeySpec`.
- Tạo `PublicKey`, `PrivateKey`, `X509Certificate` hoặc `X509CRL`.
- Xử lý riêng private key được mã hóa bằng mật khẩu.
- Xử lý các PEM type không có lớp Java tương ứng.

PEM API gom các thao tác phổ biến này vào `PEMEncoder` và `PEMDecoder`. Ứng dụng vẫn phải quyết định chính sách bảo mật, provider, thuật toán và cách xác thực dữ liệu sau khi giải mã.

## 2. Các kiểu PEM phổ biến

| PEM label | Nội dung thường gặp | Kiểu Java có thể nhận |
|---|---|---|
| `CERTIFICATE` | Chứng chỉ X.509 dạng DER | `X509Certificate` |
| `X509 CRL` | Certificate Revocation List | `X509CRL` |
| `PUBLIC KEY` | Khóa công khai theo X.509 SubjectPublicKeyInfo | `PublicKey` hoặc `X509EncodedKeySpec` |
| `PRIVATE KEY` | Private key theo PKCS #8, không mã hóa bằng mật khẩu | `PrivateKey`, `KeyPair` nếu có cả public key, hoặc `PKCS8EncodedKeySpec` |
| `ENCRYPTED PRIVATE KEY` | Private key PKCS #8 được bảo vệ bằng mật khẩu | `EncryptedPrivateKeyInfo`, hoặc `PrivateKey`/`KeyPair` khi decoder được cấu hình giải mã |
| Label khác | PEM type không có lớp Java tương ứng | `PEM` tổng quát |

Không suy luận thuật toán chỉ từ PEM label. Ví dụ `PUBLIC KEY` có thể đại diện cho RSA, EC, EdDSA hoặc thuật toán khác mà provider hỗ trợ. Sau khi decode, kiểm tra loại key và thuật toán bằng API của đối tượng:

~~~java
System.out.println(publicKey.getAlgorithm());
System.out.println(publicKey.getFormat());
~~~

### 2.1. Phân biệt PRIVATE KEY và ENCRYPTED PRIVATE KEY

- `PRIVATE KEY` thường là PKCS #8 PrivateKeyInfo không mã hóa bằng mật khẩu.
- `ENCRYPTED PRIVATE KEY` là cấu trúc EncryptedPrivateKeyInfo theo PKCS #8, có thông tin thuật toán và tham số cần thiết để giải mã.

**Base64 không phải mã hóa bảo mật.** Ai có nội dung PEM `PRIVATE KEY` đều có thể khôi phục bytes khóa nếu không có lớp bảo vệ khác. Chỉ riêng việc đặt private key trong PEM không bảo vệ nó bằng mật khẩu.

### 2.2. PEM và DER khác nhau thế nào?

| Tiêu chí | DER | PEM |
|---|---|---|
| Dạng dữ liệu | Nhị phân ASN.1 encoding | Văn bản Base64 bao quanh bởi header/footer |
| Dùng để | Biểu diễn cấu trúc mật mã | Trao đổi/lưu trữ ở môi trường hỗ trợ văn bản |
| Nội dung lõi | DER bytes | Base64 của dữ liệu nhị phân |
| Bảo mật | Không tự mã hóa | Không tự mã hóa |
| Tương quan | Có thể là dữ liệu bên trong PEM | Đóng gói dữ liệu nhị phân như DER |

PEM không đồng nghĩa với DER; PEM là lớp văn bản bên ngoài, còn DER thường là cấu trúc nhị phân bên trong.

## 3. Mục tiêu của JEP 470 trong JDK 25

JEP 470 giới thiệu các API:

- `PEMEncoder`: mã hóa đối tượng mật mã sang PEM text hoặc byte array.
- `PEMDecoder`: giải mã PEM thành đối tượng mật mã.
- `DEREncodable`: interface preview biểu diễn đối tượng có thể chuyển đổi sang/từ dạng nhị phân DER.
- `PEMRecord`: biểu diễn PEM type và Base64 content khi không muốn hoặc không thể chuyển thành một cryptographic object có kiểu Java cụ thể.

API thuộc module `java.base`, package `java.security`; không cần thêm dependency bên ngoài để truy cập các lớp này trong JDK tương ứng.

JDK 25 giới thiệu API dưới dạng preview. Các preview API có thể thay đổi hoặc bị loại bỏ trước khi trở thành permanent. Vì vậy, JEP 470 là cột mốc giới thiệu API, không phải bằng chứng rằng chữ ký method của JDK 25 đã ổn định cho mọi bản JDK sau này.

### 3.1. Lịch sử preview và thay đổi API

| JDK | JEP | Trạng thái | Điểm cần nhớ |
|---|---|---|---|
| **JDK 25** | JEP 470 | Preview lần đầu | Dùng `DEREncodable`, `PEMRecord`, `withFactory(Provider)` |
| **JDK 26** | JEP 524 | Preview lần hai | `PEMRecord` được đổi thành `PEM`; hỗ trợ mã hóa/giải mã KeyPair và PKCS8EncodedKeySpec được mở rộng |
| **JDK 27** | JEP 538 | Preview lần ba | `DEREncodable` đổi tên thành `BinaryEncodable`; `PEM` là class; provider method là `withFactoriesOf`; có `CryptoException` preview |

Trong JDK 27, API vẫn mang dấu preview trong JavaDoc. Do đó, code mẫu ở các phần sau dùng JDK 27 hiện hành và không dùng tên preview cũ của JDK 25.

### 3.2. Vì sao tên API thay đổi?

`DEREncodable` được đổi thành `BinaryEncodable` vì API biểu diễn dữ liệu nhị phân có thể không chỉ giới hạn ở DER. Tên mới mô tả vai trò rộng hơn của interface.

`PEMRecord` trong JDK 25 là record chứa type, Base64 content và leading data. Qua các preview tiếp theo, API chuyển sang lớp `PEM` để quản lý nội dung nhị phân và defensive copying rõ ràng hơn.

`withFactory(Provider)` được đổi thành `withFactoriesOf(Provider)` trong JDK 27 để diễn đạt việc provider được dùng cho cả `KeyFactory` và `CertificateFactory`.

Đây là các thay đổi có ý nghĩa khi nâng cấp từ JDK 25. Không dùng một snippet có `DEREncodable` hoặc `PEMRecord` rồi kỳ vọng nó biên dịch trực tiếp với JDK 27.

## 4. Cấu hình preview đúng phiên bản JDK

Preview API phải được bật khi biên dịch và khi chạy. Dùng đúng JDK release cho cả hai bước.

### 4.1. Thử API JDK 25

Với JDK 25, dùng compiler và runtime JDK 25:

~~~bash
javac --enable-preview --release 25 -d out src/PemExample.java
java --enable-preview -cp out PemExample
~~~

API JDK 25 có các tên `DEREncodable`, `PEMRecord` và `withFactory(Provider)`. Những tên này chỉ dùng trong source nhắm tới preview JDK 25.

### 4.2. Dùng API hiện hành JDK 27

Các ví dụ thực hành trong bài dùng API JDK 27:

~~~bash
javac --enable-preview --release 27 -d out src/PemExample.java
java --enable-preview -cp out PemExample
~~~

JDK 27 dùng `BinaryEncodable`, `PEM` và `withFactoriesOf(Provider)`. Các lớp/method preview vẫn cần `--enable-preview`.

### 4.3. Không trộn class file preview giữa các release

Preview feature gắn với release cụ thể. Không biên dịch code preview bằng JDK 25 rồi chạy nó bằng JDK 27 như thể preview API không thay đổi. Khi nâng JDK:

1. Chọn đúng JDK compiler/runtime đích.
2. Đọc JavaDoc preview của release đó.
3. Cập nhật các tên interface/class/method đã thay đổi.
4. Biên dịch lại bằng `--enable-preview`.
5. Chạy test bằng đúng release và preview flag.
6. Kiểm tra provider, key format và khả năng tương tác với hệ thống ngoài.

Nếu ứng dụng không thể chấp nhận preview API trong production, tiếp tục dùng API Java ổn định phù hợp hoặc một thư viện PEM được duy trì và tương thích với chính sách bảo mật của dự án cho tới khi API được final.

## 5. Dùng PEMEncoder và PEMDecoder trong JDK 27

Hai lớp chính có factory method:

- `PEMEncoder.of()`
- `PEMDecoder.of()`

Cả hai lớp là immutable và thread-safe theo JavaDoc. Có thể tái sử dụng instance không chứa cấu hình bí mật cho nhiều thao tác. Các method cấu hình như `withEncryption`, `withDecryption` và `withFactoriesOf` trả về instance đã cấu hình.

Ví dụ encode và decode private key:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.PrivateKey;

public final class PemKeyExample {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair original = generator.generateKeyPair();

        PEMEncoder encoder = PEMEncoder.of();
        String privatePem = encoder.encodeToString(original);

        PrivateKey decoded = PEMDecoder.of()
                .decode(privatePem, PrivateKey.class);

        System.out.println(decoded.getAlgorithm());
        System.out.println(decoded.getFormat());
    }
}
~~~

JDK 27 hỗ trợ `KeyPair` dưới PEM label `PRIVATE KEY`, theo cấu trúc OneAsymmetricKey của PKCS #8 v2.0. Khi decode, có thể yêu cầu `KeyPair.class` nếu nội dung có cả private key và public key.

### 5.1. Encode và decode public key

~~~java
String publicPem = PEMEncoder.of().encodeToString(original.getPublic());

PublicKey decodedPublic = PEMDecoder.of()
        .decode(publicPem, PublicKey.class);
~~~

PEM label thường là `PUBLIC KEY`, biểu diễn X.509 SubjectPublicKeyInfo. Không nhầm với các định dạng khóa công khai đặc thù khác.

### 5.2. Decode certificate và CRL

~~~java
X509Certificate certificate = PEMDecoder.of()
        .decode(certificatePem, X509Certificate.class);

X509CRL crl = PEMDecoder.of()
        .decode(crlPem, X509CRL.class);
~~~

Decoder tạo đối tượng Java tương ứng nếu PEM type và provider hỗ trợ. Đây là bước parsing/decoding. Nó chưa chứng minh chứng chỉ được CA tin cậy, còn hiệu lực, phù hợp hostname hoặc được phép dùng cho mục đích cụ thể.

### 5.3. Chỉ định kiểu trả về khi decode

Dùng overload `decode(String, Class)` hoặc `decode(InputStream, Class)` để yêu cầu kiểu cụ thể:

~~~java
PrivateKey privateKey = PEMDecoder.of()
        .decode(privateKeyPem, PrivateKey.class);

X509Certificate certificate = PEMDecoder.of()
        .decode(certificatePem, X509Certificate.class);
~~~

Nếu lớp được yêu cầu không tương thích với PEM type hoặc nội dung, decoder có thể ném `ClassCastException`. Nếu không có PEM data hoặc dữ liệu không hợp lệ, decoder có thể ném `IllegalArgumentException`; khi dùng InputStream còn có thể có `IOException` hoặc `EOFException`.

## 6. Mã hóa private key bằng mật khẩu

JDK 27 cho phép tạo encoder được cấu hình để mã hóa private key:

~~~java
char[] password = obtainPasswordFromSecretStore();

try {
    PEMEncoder encryptedEncoder =
            PEMEncoder.of().withEncryption(password);

    String encryptedPem =
            encryptedEncoder.encodeToString(privateKey);
} finally {
    Arrays.fill(password, '\0');
}
~~~

Encoder được cấu hình trả về dữ liệu PEM có label `ENCRYPTED PRIVATE KEY`. Đây là dạng private key PKCS #8 được bảo vệ bằng mật khẩu.

JDK 27 hỗ trợ encryption cho:

- `PrivateKey`
- `KeyPair`
- `PKCS8EncodedKeySpec`

Các loại object khác không được mã hóa bằng instance encoder đã cấu hình `withEncryption`; thao tác không phù hợp có thể ném `IllegalArgumentException`.

### 6.1. Giải mã private key đã mã hóa

~~~java
char[] password = obtainPasswordFromSecretStore();

try {
    PEMDecoder decryptingDecoder =
            PEMDecoder.of().withDecryption(password);

    PrivateKey privateKey = decryptingDecoder.decode(
            encryptedPrivatePem,
            PrivateKey.class
    );
} finally {
    Arrays.fill(password, '\0');
}
~~~

Nếu PEM chứa cả public key trong cấu trúc OneAsymmetricKey, có thể yêu cầu `KeyPair.class`.

Nếu decoder chưa được cấu hình `withDecryption`, PEM type `ENCRYPTED PRIVATE KEY` được trả về dưới dạng `EncryptedPrivateKeyInfo`. Khi decoder đã cấu hình giải mã, nó có thể giải mã cả PEM không mã hóa và PEM được mã hóa.

### 6.2. Không giả định thuật toán mặc định

`PEMEncoder.withEncryption(char[])` sử dụng thuật toán mặc định theo security property `jdk.epkcs8.defaultAlgorithm` và tham số mặc định của provider được chọn.

Nếu cần interoperability với hệ thống khác, hãy:

- Kiểm tra security property và provider đang sử dụng.
- Thử decode file được tạo bởi công cụ ngoài.
- Xác minh thuật toán, KDF và tham số mã hóa tương thích.
- Dùng overload kiểm soát thuật toán/tham số của `EncryptedPrivateKeyInfo` nếu use case cần cấu hình cụ thể.
- Không tự giả định mọi provider dùng cùng default algorithm hoặc cùng parameter set.

Mật khẩu được truyền bằng `char[]` và API clone/lưu một bản trong instance đã cấu hình. Xóa mảng do ứng dụng sở hữu bằng `Arrays.fill` không đồng nghĩa xóa bản sao bên trong encoder/decoder. Hãy giữ vòng đời các instance chứa mật khẩu ngắn, không đăng ký chúng thành singleton lâu dài và không ghi mật khẩu ra log.

## 7. Dùng provider cụ thể khi giải mã

JCA dùng provider để cung cấp các dịch vụ mật mã. Nếu môi trường có provider riêng hoặc cần ép dùng provider đã kiểm thử, JDK 27 có:

~~~java
Provider provider = Security.getProvider("MyCryptoProvider");

PEMDecoder decoder = PEMDecoder.of()
        .withFactoriesOf(provider);

PrivateKey privateKey = decoder.decode(
        privateKeyPem,
        PrivateKey.class
);
~~~

`withFactoriesOf(Provider)` cấu hình provider được dùng cho `KeyFactory` và `CertificateFactory` khi tạo đối tượng tương ứng. Nó không có nghĩa toàn bộ hoạt động mật mã trong ứng dụng đều tự động chuyển sang provider đó.

Trước khi sử dụng provider:

- Xác nhận provider đã được cài đặt/đăng ký và có thuật toán cần thiết.
- Kiểm tra chính sách FIPS hoặc compliance nếu hệ thống yêu cầu.
- Kiểm thử key algorithm, certificate format và encrypted private key.
- Xử lý trường hợp provider không hỗ trợ thuật toán hoặc tham số cụ thể.

## 8. Xử lý PEM type chưa có lớp Java tương ứng

Không phải mọi PEM label đều có một lớp cryptographic object tương ứng trong Java. Ví dụ, một số loại certificate request hoặc cấu trúc CMS có thể không được ánh xạ trực tiếp thành lớp Java.

Trong JDK 27, decoder trả về `PEM` cho PEM type không thể biểu diễn thành một đối tượng mật mã cụ thể.

~~~java
BinaryEncodable decoded = PEMDecoder.of().decode(pemText);

if (decoded instanceof PEM rawPem) {
    System.out.println(rawPem.type());

    byte[] base64Content = rawPem.content();
    byte[] binaryContent = rawPem.decode();
    byte[] leadingData = rawPem.leadingData();
}
~~~

Các phương thức có ý nghĩa:

- `type()`: nhãn PEM, không gồm cú pháp BEGIN/END.
- `content()`: nội dung Base64.
- `decode()`: giải mã Base64 thành byte array.
- `leadingData()`: dữ liệu đứng trước PEM header trong input, nếu có.

Đối với loại PEM chưa có API Java, ứng dụng có thể giữ dữ liệu ở dạng tổng quát hoặc chuyển bytes sang parser chuyên biệt đã được kiểm thử.

### 8.1. Không coi PEM tổng quát là dữ liệu mật mã đã được xác thực

Lớp `PEM` có thể giữ type và Base64 content, nhưng điều đó không chứng minh content đúng với type. JavaDoc ghi rõ việc tạo PEM tổng quát không xác thực type có tuân theo RFC 7468 hay content có thực sự tương ứng với nhãn hay không.

Khi xử lý PEM không rõ nguồn gốc:

1. Giới hạn kích thước input.
2. Kiểm tra PEM type theo allowlist của use case.
3. Decode Base64 và parse bằng API phù hợp với cấu trúc mong đợi.
4. Xác minh chữ ký, thuật toán và các ràng buộc cần thiết.
5. Không chấp nhận một PEM label tùy ý chỉ vì parser trả về một object.

### 8.2. Lưu ý về leading data

Decoder có thể giữ dữ liệu không phải PEM đứng trước header trong `leadingData()` khi trả về `PEM` tổng quát. Tuy nhiên, khi `PEMEncoder` encode object `PEM`, phần leading data không được đưa vào output.

Nếu ứng dụng cần giữ nguyên metadata hoặc phần văn bản đứng trước PEM block, hãy lưu và xử lý phần đó riêng. Không giả định encode/decode round trip sẽ bảo toàn toàn bộ nội dung ngoài PEM block.

## 9. API preview không thay thế quy trình xác thực PKI

PEMDecoder có thể tạo `X509Certificate`, nhưng parsing thành công không có nghĩa certificate đáng tin cậy.

Sau khi decode certificate, quy trình PKI vẫn cần xem xét:

- Chữ ký certificate có hợp lệ không?
- Certificate chain có dẫn tới trust anchor được cấu hình không?
- Certificate còn trong thời hạn `notBefore`/`notAfter` không?
- Key Usage và Extended Key Usage có phù hợp không?
- Subject Alternative Name có khớp hostname cần xác thực không?
- Certificate có bị thu hồi theo chính sách CRL/OCSP không?
- Thuật toán và key size có đáp ứng policy hiện hành không?

Ví dụ, `certificate.checkValidity()` chỉ kiểm tra thời hạn:

~~~java
certificate.checkValidity();
~~~

Nó không thay thế PKIX path validation, kiểm tra hostname hoặc chính sách trust. Dùng `CertPathValidator`, `TrustManager`, `KeyStore` và các API phù hợp với mục đích của ứng dụng.

**PEM là lớp định dạng vận chuyển.** Nó không xác thực danh tính, không xác minh chữ ký và không quyết định certificate có được tin cậy hay không.

## 10. Các API được hỗ trợ và giới hạn

Theo API JDK 27, các kiểu chính được hỗ trợ gồm:

| Đối tượng | PEM output | Ghi chú |
|---|---|---|
| `X509Certificate` | `CERTIFICATE` | Certificate X.509 |
| `X509CRL` | `X509 CRL` | Danh sách thu hồi |
| `PublicKey` | `PUBLIC KEY` | X.509 SubjectPublicKeyInfo |
| `PrivateKey` | `PRIVATE KEY` | PKCS #8 |
| `PrivateKey` đã mã hóa | `ENCRYPTED PRIVATE KEY` | Khi encoder có encryption |
| `KeyPair` | `PRIVATE KEY` | OneAsymmetricKey PKCS #8 v2 |
| `X509EncodedKeySpec` | `PUBLIC KEY` | Key specification |
| `PKCS8EncodedKeySpec` | `PRIVATE KEY` | Key specification |
| `EncryptedPrivateKeyInfo` | `ENCRYPTED PRIVATE KEY` | PKCS #8 encrypted |
| `PEM` | Theo `PEM.type()` | Nội dung tổng quát |

Các implementation có thể hỗ trợ thêm PEM type hoặc BinaryEncodable khác. Không giả định mọi provider/runtime hỗ trợ chính xác cùng tập định dạng mở rộng.

### 10.1. InputStream và xử lý lỗi

Khi dùng `decode(InputStream)`:

- Decoder đọc đến hết PEM footer hoặc hết stream.
- Nếu I/O error xảy ra, vị trí đọc của stream có thể không nhất quán.
- JavaDoc khuyến nghị không tiếp tục decode trên cùng stream sau lỗi I/O.
- Nếu không tìm thấy PEM data hoặc stream kết thúc bất thường, có thể nhận `EOFException`.
- Lỗi cú pháp hoặc dữ liệu có thể gây `IOException` hoặc `IllegalArgumentException`.

Với input dạng String, dữ liệu được đọc theo UTF-8. Nếu nguồn dữ liệu là file, nên mở stream với lifecycle rõ ràng và giới hạn kích thước file trước khi parse.

## 11. Ví dụ thực hành: round trip KeyPair

Ví dụ sau dùng API JDK 27 hiện hành. Nó tạo một Ed25519 key pair, encode thành PEM, rồi decode lại.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.PublicKey;
import java.util.Arrays;

public final class PemRoundTrip {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");

        KeyPair original = generator.generateKeyPair();

        PEMEncoder encoder = PEMEncoder.of();
        String privatePem = encoder.encodeToString(original);
        String publicPem = encoder.encodeToString(original.getPublic());

        PEMDecoder decoder = PEMDecoder.of();

        KeyPair decodedPair =
                decoder.decode(privatePem, KeyPair.class);

        PublicKey decodedPublic =
                decoder.decode(publicPem, PublicKey.class);

        if (!Arrays.equals(
                original.getPublic().getEncoded(),
                decodedPair.getPublic().getEncoded())) {
            throw new IllegalStateException("KeyPair không khớp");
        }

        if (!Arrays.equals(
                original.getPublic().getEncoded(),
                decodedPublic.getEncoded())) {
            throw new IllegalStateException("Public key không khớp");
        }

        System.out.println("PEM encode/decode thành công");
    }
}
~~~

Đây là bài thực hành kiểm tra encode/decode và so sánh public key bytes. Không in private key PEM ra console hoặc CI log.

## 12. Ví dụ thực hành: mã hóa private key bằng mật khẩu

~~~java
import java.security.KeyPair;
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.util.Arrays;

public final class EncryptedPemRoundTrip {

    public static KeyPair roundTrip(
            KeyPair keyPair,
            char[] password) {

        try {
            PEMEncoder encoder =
                    PEMEncoder.of().withEncryption(password);

            String encryptedPem =
                    encoder.encodeToString(keyPair);

            PEMDecoder decoder =
                    PEMDecoder.of().withDecryption(password);

            return decoder.decode(encryptedPem, KeyPair.class);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Trong production, `password` phải lấy từ secret manager hoặc cơ chế cấp phát bí mật phù hợp. Ví dụ trên chỉ minh họa luồng API. Do encoder/decoder clone và giữ bản sao password trong instance đã cấu hình, việc xóa mảng đầu vào không xóa ngay các bản sao nội bộ. Giữ các instance này trong scope ngắn và tránh log hoặc cache chúng.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo preview API disabled | Chưa bật preview | Dùng `--enable-preview` với đúng JDK |
| JDK 25 không nhận `BinaryEncodable` | JDK 25 dùng tên `DEREncodable` | Dùng API đúng release hoặc nâng JDK và migrate |
| JDK 27 không nhận `PEMRecord` | Tên hiện hành là `PEM` | Đổi sang `PEM` và `BinaryEncodable` |
| JDK 27 không có `withFactory` | Method hiện hành là `withFactoriesOf` | Cập nhật source theo JDK 27 |
| Decode trả về `PEM` thay vì `PrivateKey` | PEM type không được ánh xạ hoặc không phù hợp | Kiểm tra label, encoding và parser tương ứng |
| `ClassCastException` | Requested class không phù hợp với PEM type | Dùng đúng class hoặc decode tổng quát |
| Không tìm thấy PEM header | Input không chứa PEM block hợp lệ | Kiểm tra file, encoding và delimiter |
| Decode encrypted key thất bại | Password sai, thuật toán/provider không tương thích hoặc dữ liệu hỏng | Kiểm tra password và security provider |
| Certificate decode thành công nhưng TLS vẫn fail | Parsing không xác minh trust/hostname | Thực hiện PKIX validation và hostname verification |
| Unknown PEM content được chấp nhận | Generic `PEM` chỉ giữ label/content | Kiểm tra allowlist và parse payload theo chuẩn |
| PEM encode không giữ phần leading text | `PEMEncoder` không xuất `leadingData` | Lưu metadata ngoài PEM riêng |
| Chạy được trên JDK 25 nhưng không compile JDK 27 | API đã đổi tên giữa các preview | Migrate sang BinaryEncodable/PEM/withFactoriesOf |

## 14. Ma trận kiểm thử nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| P1 | Encode `PublicKey` | Sinh PEM label `PUBLIC KEY` |
| P2 | Decode `PUBLIC KEY` thành `PublicKey` | Thu được public key tương ứng |
| P3 | Encode `PrivateKey` | Sinh PEM label `PRIVATE KEY` |
| P4 | Decode `PRIVATE KEY` thành `PrivateKey` | Thu được private key tương ứng |
| P5 | Encode `KeyPair` | Sinh PKCS #8 OneAsymmetricKey |
| P6 | Decode KeyPair có public component | Có thể lấy lại `KeyPair` |
| P7 | Encode `X509Certificate` | Sinh PEM label `CERTIFICATE` |
| P8 | Decode certificate | Thu được `X509Certificate` |
| P9 | Decode `X509 CRL` | Thu được `X509CRL` |
| P10 | Encode private key với password | Sinh `ENCRYPTED PRIVATE KEY` |
| P11 | Decode encrypted key với đúng password | Thu được key |
| P12 | Decode encrypted key với password sai | Nhận lỗi giải mã phù hợp |
| P13 | Decode encrypted key không cấu hình password | Nhận `EncryptedPrivateKeyInfo` |
| P14 | Decode PEM type chưa hỗ trợ | Nhận `PEM` tổng quát |
| P15 | Yêu cầu sai target class | Nhận lỗi kiểu phù hợp |
| P16 | PEM input không có header/footer | Decode thất bại rõ ràng |
| P17 | PEM có leading data | Kiểm tra `leadingData()` khi decode thành `PEM` |
| P18 | Encode lại `PEM` có leading data | Xác nhận leading data không tự được đưa vào output |
| P19 | Dùng provider được chỉ định | KeyFactory/CertificateFactory được chọn theo provider |
| P20 | Compile/run với preview JDK 27 | Thành công khi bật preview đúng release |
| P21 | Thử code preview JDK 25 trên JDK 27 | Nhận diện và sửa khác biệt API |
| P22 | Certificate parse thành công nhưng chain không tin cậy | PKIX validation vẫn từ chối theo trust policy |

## 15. Checklist bảo mật khi xử lý PEM

- Chỉ chấp nhận PEM type phù hợp với use case.
- Giới hạn kích thước file/string trước khi decode.
- Không coi Base64 là mã hóa hoặc biện pháp bảo vệ private key.
- Dùng `ENCRYPTED PRIVATE KEY` khi cần password-based protection cho file private key.
- Lấy password từ secret manager, không hardcode trong source hoặc CI.
- Không ghi PEM private key, password hoặc raw key bytes vào log.
- Giới hạn quyền đọc file private key và file recording/debug chứa dữ liệu nhạy cảm.
- Xác minh thuật toán/provider khi cần interoperability.
- Xác thực certificate chain, validity, hostname, key usage và revocation theo policy.
- Không coi PEM label là bằng chứng nội dung tương ứng với label.
- Xử lý PEM type không hỗ trợ theo allowlist và parser chuyên biệt.
- Giữ preview API sau khi đánh giá rủi ro tương thích; kiểm thử lại khi nâng JDK.
- Không chia sẻ preview class file giữa các release.
- Giữ các instance encoder/decoder có password trong scope ngắn.

## 16. Bài thực hành tổng hợp

Xây dựng một tiện ích Java có nhiệm vụ đọc certificate, public key và private key PEM cho một ứng dụng TLS nội bộ.

Thực hiện:

1. Dùng JDK 27 và bật preview khi compile/run.
2. Tạo Ed25519 key pair trong môi trường test.
3. Encode key pair và public key thành PEM.
4. Decode lại bằng `PEMDecoder` với target class cụ thể.
5. Encode/decode một certificate X.509 test.
6. Tạo private key PEM được mã hóa bằng password lấy từ secret test.
7. Decode bằng `withDecryption` và xử lý lỗi password sai.
8. Thử một PEM type chưa được ánh xạ để kiểm tra `PEM` fallback.
9. Dùng `withFactoriesOf` với provider phù hợp nếu dự án có provider riêng.
10. Tách bước decode certificate khỏi bước PKIX validation.
11. Viết test cho P1–P22.
12. Viết tài liệu nâng cấp nêu khác biệt API JDK 25, 26 và 27.

**Sản phẩm nghiệm thu:** mã nguồn encode/decode, test suite, PEM fixture không chứa secret thật, kết quả kiểm tra certificate validation, hướng dẫn preview flags và bảng migration API giữa các JDK.

## 17. Checklist nâng cấp từ JDK 25 lên JDK 27

Khi nâng từ JDK 25 lên JDK 27, kiểm tra:

- `DEREncodable` đổi thành `BinaryEncodable`.
- `PEMRecord` đổi thành `PEM`.
- `withFactory(Provider)` đổi thành `withFactoriesOf(Provider)`.
- `PEM` ở JDK 27 là class với nội dung và leading data được defensive copy.
- `CryptoException` preview được dùng cho lỗi xử lý mật mã.
- Compile và runtime đều dùng `--enable-preview` của JDK 27.
- Các test encryption/decryption chạy với provider và security properties thực tế.
- Không dùng code preview JDK 25 như API ổn định.
- Xác nhận thư viện ngoài và build pipeline dùng đúng JDK.

## Tài liệu tham khảo chính thức

- [JEP 470 — PEM Encodings of Cryptographic Objects (JDK 25 Preview)](https://openjdk.org/jeps/470): mục tiêu ban đầu và preview đầu tiên của API.
- [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): xác nhận PEM Encodings of Cryptographic Objects là preview API trong JDK 25.
- [Oracle Java SE 25 — PEMEncoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMEncoder.html): API encoder trong preview đầu tiên.
- [Oracle Java SE 25 — PEMDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/PEMDecoder.html): decode, các PEM type và provider trong JDK 25.
- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): các thay đổi preview trong JDK 26.
- [Oracle JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận preview lần thứ hai trong JDK 26.
- [JEP 538 — PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538): preview lần thứ ba trong JDK 27.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận JEP 538 vẫn là preview API trong JDK 27.
- [Oracle Java SE 27 — BinaryEncodable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html): interface preview hiện hành.
- [Oracle Java SE 27 — PEM](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html): xử lý PEM type tổng quát, content và leading data.
- [Oracle Java SE 27 — PEMEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html): mã hóa key, certificate, CRL và encrypted private key.
- [Oracle Java SE 27 — PEMDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html): decode object, provider selection và decryption.
- [Oracle Java SE 27 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): ví dụ PEM, JCA provider và cách tích hợp.
- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468): đặc tả PEM text cho các cấu trúc PKIX, PKCS và CMS.
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958): cấu trúc OneAsymmetricKey dùng trong PKCS #8 v2.0.
