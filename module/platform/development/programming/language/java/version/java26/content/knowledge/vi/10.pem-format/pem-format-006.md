# Tạo PEMDecoder và giải mã theo kiểu dữ liệu đích

## Mục tiêu

Sau bài học này, bạn có thể:

- Tạo decoder bằng `PEMDecoder.of()` và tái sử dụng instance phù hợp.
- Chọn kiểu Java đích ngay trong `decode(data, TargetType.class)`.
- Giải mã certificate, public key, private key, CRL và dữ liệu PEM chưa có kiểu Java tương ứng.
- Phân biệt giải mã từ `String` với giải mã từ `InputStream`.
- Xử lý private key được mã hóa bằng password và chọn JCA Provider khi cần.
- Nhận biết các lỗi về nhãn PEM, kiểu đích, dữ liệu đầu vào và provider.
- Bật đúng preview feature trên JDK 26 và tránh phụ thuộc vào API chưa ổn định trong production.

## 1. PEMDecoder dùng để làm gì?

PEM (Privacy-Enhanced Mail) là định dạng văn bản dùng để lưu và trao đổi dữ liệu mật mã. Một PEM block thường gồm:

1. Dòng mở đầu chứa nhãn loại dữ liệu, ví dụ `-----BEGIN CERTIFICATE-----`.
2. Nội dung nhị phân đã mã hóa Base64, thường là dữ liệu DER.
3. Dòng kết thúc có nhãn tương ứng, ví dụ `-----END CERTIFICATE-----`.

Ví dụ hình dạng của một public key:

~~~text
-----BEGIN PUBLIC KEY-----
BASE64_ENCODED_DER_DATA
-----END PUBLIC KEY-----
~~~

PEM chỉ là lớp biểu diễn văn bản. Nhãn trong header cho biết loại cấu trúc được chứa; nó không tự xác nhận thuật toán, tính hợp lệ của khóa, danh tính người sở hữu hoặc mức độ tin cậy của certificate.

JDK cung cấp các API JCA như `KeyFactory`, `CertificateFactory` và `X509Certificate` để làm việc với dữ liệu mật mã. `PEMDecoder` bổ sung bước đọc định dạng PEM và chuyển dữ liệu về kiểu Java tương ứng, giúp ứng dụng không phải tự tách header/footer, giải Base64 rồi tự dựng đối tượng.

Trong JDK 26, `PEMDecoder` nằm trong package `java.security`, module `java.base`, theo JEP 470. Đây là **preview API**, không phải API Java SE final.

## 2. Tạo PEMDecoder bằng of()

Tạo một decoder mặc định:

~~~java
import java.security.PEMDecoder;

PEMDecoder decoder = PEMDecoder.of();
~~~

Có thể tái sử dụng instance này để giải mã nhiều PEM. `PEMDecoder` là immutable và thread-safe. Khi cần cấu hình Provider hoặc giải mã private key được mã hóa, các phương thức cấu hình trả về một instance mới.

Không cần tạo một decoder mới cho mỗi lần giải mã thông thường. Hãy tạo instance ở phạm vi phù hợp với ứng dụng, nhưng tránh giữ một decoder được cấu hình bằng password lâu hơn thời gian cần thiết.

## 3. Chọn kiểu dữ liệu đích bằng decode(data, Class)

Hai overload quan trọng là:

~~~java
DEREncodable decode(String pemText)

<S extends DEREncodable> S decode(String pemText, Class<S> targetType)
~~~

Và các overload tương ứng nhận `InputStream`:

~~~java
DEREncodable decode(InputStream input)

<S extends DEREncodable> S decode(InputStream input, Class<S> targetType)
~~~

`targetType` cho biết ứng dụng muốn nhận kiểu dữ liệu Java nào. Đây là cách tránh ép kiểu sau khi giải mã và làm rõ hợp đồng của đoạn code.

Ví dụ, nếu biết nội dung là certificate:

~~~java
X509Certificate certificate =
    decoder.decode(pemText, X509Certificate.class);
~~~

Nếu biết nội dung là public key:

~~~java
PublicKey publicKey =
    decoder.decode(pemText, PublicKey.class);
~~~

Nếu biết nội dung là private key không mã hóa theo nhãn PKCS#8:

~~~java
PrivateKey privateKey =
    decoder.decode(privateKeyPem, PrivateKey.class);
~~~

Kiểu đích phải phù hợp với nhãn PEM và nội dung bên trong. Nếu yêu cầu một class không tương thích với dữ liệu, decoder ném `ClassCastException`. Nếu PEM sai định dạng hoặc không thể giải mã, thao tác có thể ném `IllegalArgumentException`.

Không nên dùng `Object.class` để né việc lựa chọn kiểu. Hãy chọn class cụ thể nếu định dạng đầu vào đã được quy định trong cấu hình hoặc hợp đồng giao tiếp.

## 4. Các nhãn PEM phổ biến và kiểu Java được trả về

JDK 26 hỗ trợ các loại PEM phổ biến sau:

| Nhãn PEM | Kiểu mặc định | Kiểu có thể yêu cầu tường minh |
|---|---|---|
| `CERTIFICATE` | `X509Certificate` | `X509Certificate.class` |
| `X509 CRL` | `X509CRL` | `X509CRL.class` |
| `PUBLIC KEY` | `PublicKey` | `X509EncodedKeySpec.class` |
| `PRIVATE KEY` | `PrivateKey`; có thể là `KeyPair` nếu encoding chứa cả public key | `PKCS8EncodedKeySpec.class`; có thể yêu cầu public key hoặc `X509EncodedKeySpec.class` nếu encoding có public key |
| `ENCRYPTED PRIVATE KEY` | `EncryptedPrivateKeyInfo` nếu decoder chưa cấu hình giải mã | `PrivateKey.class` khi decoder được cấu hình password; các kiểu key spec tương ứng cũng có thể được yêu cầu |
| Nhãn khác | `PEM` | `PEM.class` |

Với `PublicKey` và `PrivateKey`, decoder trả về lớp cụ thể theo thuật toán nếu provider hỗ trợ, ví dụ `RSAPublicKey`, `ECPublicKey`, `RSAPrivateKey` hoặc `ECPrivateKey`.

### Giải mã certificate

~~~java
X509Certificate certificate =
    PEMDecoder.of().decode(certificatePem, X509Certificate.class);

System.out.println(certificate.getSubjectX500Principal());
System.out.println(certificate.getIssuerX500Principal());
System.out.println(certificate.getNotAfter());
~~~

### Giải mã public key

~~~java
PublicKey publicKey =
    PEMDecoder.of().decode(publicKeyPem, PublicKey.class);

System.out.println(publicKey.getAlgorithm());
System.out.println(publicKey.getFormat());
~~~

### Giải mã private key

~~~java
PrivateKey privateKey =
    PEMDecoder.of().decode(privateKeyPem, PrivateKey.class);

System.out.println(privateKey.getAlgorithm());
~~~

Không log hoặc in nội dung private key. Ví dụ chỉ hiển thị thuật toán và định dạng.

## 5. Khi nào nên yêu cầu KeySpec thay vì Key?

`PublicKey` và `PrivateKey` là đối tượng key có thể được dùng trực tiếp trong các API như `Signature`, `Cipher` hoặc `KeyAgreement`, tùy thuật toán và mục đích.

`X509EncodedKeySpec` và `PKCS8EncodedKeySpec` biểu diễn dữ liệu key ở dạng encoded để ứng dụng có thể đưa vào một `KeyFactory` cụ thể hoặc xử lý theo quy trình riêng.

Ví dụ, lấy public key dưới dạng `X509EncodedKeySpec`:

~~~java
X509EncodedKeySpec keySpec =
    decoder.decode(publicKeyPem, X509EncodedKeySpec.class);

System.out.println(keySpec.getFormat()); // X.509
~~~

Ví dụ lấy private key dưới dạng `PKCS8EncodedKeySpec`:

~~~java
PKCS8EncodedKeySpec keySpec =
    decoder.decode(privateKeyPem, PKCS8EncodedKeySpec.class);

System.out.println(keySpec.getFormat()); // PKCS#8
~~~

Chọn `PublicKey` hoặc `PrivateKey` khi muốn dùng đối tượng mật mã đã được tạo. Chọn KeySpec khi ứng dụng cần giữ representation chuẩn hóa hoặc muốn tự gọi `KeyFactory` với Provider/thuật toán đã chọn.

Đừng nhầm nhãn PEM với class Java. Ví dụ, `PUBLIC KEY` là nhãn của cấu trúc public key trong PEM; `X509EncodedKeySpec` là một kiểu Java có thể được yêu cầu để nhận phần encoding tương ứng.

## 6. Giải mã dữ liệu chưa có kiểu Java tương ứng bằng PEM.class

Nếu nhãn PEM không ánh xạ tới một đối tượng mật mã mà JDK nhận diện, decoder trả về `PEM`. Có thể yêu cầu kiểu này tường minh:

~~~java
PEM pem = decoder.decode(pemText, PEM.class);

System.out.println(pem.type());

byte[] derBytes = pem.decode();
byte[] leadingData = pem.leadingData();
~~~

`PEM` là preview record trong JDK 26, chứa:

- `type()`: nhãn PEM, ví dụ `CERTIFICATE REQUEST` hoặc `CMS`.
- `content()`: nội dung Base64, không bao gồm header và footer.
- `leadingData()`: dữ liệu văn bản xuất hiện trước PEM header; có thể là `null`.
- `decode()`: giải Base64 của `content()` thành byte array.

Dùng `PEM.class` khi ứng dụng cần tự xử lý nội dung hoặc cần biết nhãn và dữ liệu đi kèm. Không coi việc decoder trả về `PEM` là xác nhận rằng nội dung bên trong hợp lệ về mặt mật mã.

Lưu ý: `PEM` không kiểm tra rằng `type` tuân theo RFC, `content` là Base64 hợp lệ hoặc dữ liệu đã giải Base64 thực sự tương ứng với nhãn. Khi tạo `PEM` thủ công, constructor cũng không thực hiện các kiểm tra đó. Mảng `leadingData` không được defensive-copy; nếu cần giữ bản sao riêng, hãy clone:

~~~java
byte[] leading = pem.leadingData();
byte[] safeCopy = leading == null ? null : leading.clone();
~~~

## 7. Giải mã từ String

Khi PEM đã có sẵn trong cấu hình hoặc được đọc thành chuỗi, dùng overload nhận `String`:

~~~java
String pemText = Files.readString(
    Path.of("server-cert.pem"),
    StandardCharsets.UTF_8
);

X509Certificate certificate =
    PEMDecoder.of().decode(pemText, X509Certificate.class);
~~~

API đọc nội dung chuỗi theo UTF-8. Nếu không tìm thấy PEM data, `decode(String)` ném `IllegalArgumentException`. Lỗi cú pháp hoặc class đích không phù hợp cũng cần được xử lý tại ranh giới đọc dữ liệu.

Với các kiểu mật mã được nhận diện, dữ liệu không phải PEM xuất hiện trước header có thể bị bỏ qua. Nếu cần giữ phần dữ liệu đứng trước PEM header, yêu cầu `PEM.class` và đọc `leadingData()`.

Không nên đọc file private key thành chuỗi rồi log, đưa vào exception message hoặc lưu trong hệ thống quan sát. Nếu có thể, đọc từ file bằng `InputStream` và kiểm soát quyền truy cập file.

## 8. Giải mã từ InputStream và quản lý tài nguyên

Dùng `InputStream` khi muốn đọc trực tiếp từ file hoặc nguồn dữ liệu dạng luồng:

~~~java
static X509Certificate readCertificate(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return PEMDecoder.of().decode(input, X509Certificate.class);
    }
}
~~~

`decode(InputStream, Class)` đọc tới cuối PEM footer hoặc cuối stream. Ứng dụng chịu trách nhiệm đóng stream; đặt stream trong try-with-resources để bảo đảm tài nguyên được đóng kể cả khi giải mã lỗi.

Nếu có lỗi I/O trong khi đọc, vị trí đọc của stream có thể không còn nhất quán. Javadoc khuyến nghị không tiếp tục dùng stream đó để giải mã thêm dữ liệu. Nếu không tìm thấy PEM data hoặc stream kết thúc bất ngờ, API có thể ném `EOFException`; lỗi I/O hoặc cú pháp cũng có thể ném `IOException` hay `IllegalArgumentException`.

Một lời gọi decode xử lý một PEM object theo footer của nó. Nếu ứng dụng xử lý một file bundle có nhiều PEM block, hãy xác định rõ cấu trúc bundle và quy tắc tách từng block; không giả định một lần gọi tự động trả về danh sách tất cả certificate hoặc key.

## 9. Giải mã private key được mã hóa

Private key có thể được lưu dưới nhãn `ENCRYPTED PRIVATE KEY`. Nếu decoder chưa cấu hình password, kết quả mặc định là `EncryptedPrivateKeyInfo`:

~~~java
EncryptedPrivateKeyInfo encrypted =
    PEMDecoder.of().decode(
        encryptedPrivateKeyPem,
        EncryptedPrivateKeyInfo.class
    );
~~~

Nếu muốn decoder giải mã và trả về `PrivateKey`, cấu hình bằng `withDecryption(char[])`:

~~~java
char[] password = obtainPassword();

try {
    PEMDecoder decoder =
        PEMDecoder.of().withDecryption(password);

    PrivateKey privateKey =
        decoder.decode(encryptedPrivateKeyPem, PrivateKey.class);

    usePrivateKey(privateKey);
} finally {
    Arrays.fill(password, '\0');
}
~~~

`obtainPassword()` và `usePrivateKey()` là các hàm do ứng dụng cung cấp. Không hard-code password trong source code, không lưu password trong log hoặc exception message và không commit file chứa secret vào repository.

JDK 26 clone mảng password và lưu bản sao trong decoder đã cấu hình. Vì vậy, xóa mảng password ban đầu bằng `Arrays.fill` không xóa bản sao nội bộ mà decoder đang giữ. Hãy giới hạn vòng đời của decoder được cấu hình decryption, không giữ nó như một singleton lâu dài nếu không cần thiết.

Decoder được cấu hình decryption vẫn giải mã được PEM không mã hóa. Nếu decryption thất bại, API ném lỗi; không được tự động coi lỗi password là lý do để thử diễn giải private key theo một định dạng khác.

## 10. Chọn JCA Provider bằng withFactory

JCA sử dụng Provider để cung cấp implementation cho các dịch vụ mật mã. Nếu ứng dụng cần dùng một Provider cụ thể để tạo key hoặc certificate, cấu hình decoder:

~~~java
PEMDecoder decoder =
    PEMDecoder.of().withFactory(provider);

PublicKey publicKey =
    decoder.decode(publicKeyPem, PublicKey.class);
~~~

`provider` là một instance `java.security.Provider` được ứng dụng lựa chọn. Trong JDK 26, `withFactory(Provider)` cấu hình decoder dùng `KeyFactory` và `CertificateFactory` từ Provider đó.

Phương thức trả về một decoder mới; instance ban đầu không bị thay đổi. Lỗi khi Provider không có implementation phù hợp sẽ xuất hiện trong lúc giải mã. Vì vậy, hãy kiểm tra provider và thuật toán cần dùng trên đúng JDK/runtime triển khai.

Không mặc định mọi Provider đều hỗ trợ mọi thuật toán hoặc mọi kiểu key. Nếu ứng dụng phụ thuộc Provider ngoài JDK, cần kiểm thử riêng trên môi trường triển khai và quản lý phiên bản Provider như một dependency bảo mật.

## 11. Phân biệt giải mã PEM với xác thực và kiểm tra độ tin cậy

`PEMDecoder` chuyển dữ liệu PEM thành đối tượng Java. Việc giải mã thành công không đồng nghĩa dữ liệu đã đáng tin cậy.

Ví dụ, sau khi có `X509Certificate`, ứng dụng vẫn cần kiểm tra các yêu cầu nghiệp vụ và bảo mật:

- Certificate còn trong thời hạn hiệu lực hay không.
- Chuỗi certificate có nối tới trust anchor được tin cậy hay không.
- Certificate có phù hợp mục đích sử dụng, key usage và extended key usage hay không.
- Hostname hoặc danh tính peer có khớp với certificate hay không khi dùng TLS.
- Certificate có bị thu hồi theo chính sách kiểm tra của hệ thống hay không.

`certificate.checkValidity()` chỉ kiểm tra khoảng thời gian hiệu lực. Nó không thay thế xác thực chuỗi certificate hoặc kiểm tra hostname.

Tương tự, giải mã `PublicKey` không xác nhận key thuộc về người gửi. Giải mã `PrivateKey` không chứng minh key khớp với certificate hoặc public key mà ứng dụng dự định sử dụng. Các bước xác minh phải được thực hiện theo giao thức và chính sách tin cậy của ứng dụng.

## 12. Các lỗi thường gặp

| Tình huống | Kết quả có thể gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy PEM header/footer hợp lệ | `IllegalArgumentException` hoặc `EOFException` tùy overload | Kiểm tra file, encoding, header/footer và dữ liệu đầu vào |
| Chọn sai class đích | `ClassCastException` | Dùng class phù hợp với PEM label và loại dữ liệu |
| Dữ liệu Base64/DER hỏng | Lỗi giải mã hoặc `IllegalArgumentException` | Kiểm tra nguồn và tính toàn vẹn của PEM |
| Provider không hỗ trợ thuật toán | Lỗi trong quá trình tạo key/certificate | Chọn Provider có implementation phù hợp |
| Private key được mã hóa nhưng không cấu hình password | Trả về `EncryptedPrivateKeyInfo` | Dùng `withDecryption(char[])` nếu có quyền giải mã |
| Password sai hoặc dữ liệu mã hóa hỏng | Lỗi giải mã | Xử lý như lỗi bảo mật, không fallback mù quáng |
| Dùng stream sau lỗi đọc | Vị trí đọc có thể không nhất quán | Đóng stream và mở lại từ nguồn đáng tin cậy |

Không bắt mọi exception rồi trả về `null`. Điều đó khiến lỗi sai định dạng, sai password hoặc thiếu Provider bị nhầm thành “không có key”. Hãy chuyển lỗi thành thông báo nghiệp vụ phù hợp, đồng thời tránh đưa nội dung PEM hoặc secret vào log.

## 13. An toàn khi xử lý key và certificate

PEM thường chứa dữ liệu công khai như certificate hoặc dữ liệu bí mật như private key. Hãy áp dụng chính sách bảo vệ theo loại dữ liệu:

- Giới hạn quyền đọc file private key; chỉ tài khoản và tiến trình cần thiết được truy cập.
- Không ghi PEM chứa private key vào log, telemetry, exception hoặc báo cáo lỗi.
- Không đưa password, private key hoặc dữ liệu nhạy cảm vào source code, test fixture công khai hay repository.
- Giới hạn kích thước file và nguồn đầu vào trước khi giải mã để tránh tiêu thụ bộ nhớ không kiểm soát.
- Dùng password từ secret manager hoặc cơ chế cấp phát secret an toàn; không lưu password trong `String` nếu có thể tránh.
- Không giữ `PrivateKey` hoặc decoder được cấu hình decryption lâu hơn vòng đời cần thiết.
- Không coi dữ liệu do bên ngoài cung cấp là đáng tin cậy chỉ vì PEM parse thành công.
- Kiểm tra algorithm, key size và chính sách mật mã của hệ thống trước khi chấp nhận key.

PEM decoder không thay thế việc quản lý vòng đời khóa, lưu trữ khóa an toàn, xác thực certificate, kiểm tra chữ ký hoặc chính sách xoay vòng khóa.

## 14. Bật preview và chạy trên JDK 26

Trong JDK 26, `PEMDecoder`, `DEREncodable`, `PEM` và `PEMEncoder` thuộc preview feature theo JEP 470. Đây là preview API đầu tiên của tính năng PEM; nó đã xuất hiện từ JDK 25 và vẫn chưa là API Java SE final trong JDK 26.

Để biên dịch ví dụ bằng JDK 26:

~~~bash
javac --release 26 --enable-preview -d out PemExample.java
~~~

Chạy bằng đúng JDK 26 và bật preview:

~~~bash
java --enable-preview -cp out PemExample
~~~

Cần bật preview ở cả compile và runtime. Không cần `--add-modules` vì API thuộc module `java.base`. Nếu dùng IDE hoặc build tool, cấu hình compiler release 26 và JVM chạy ứng dụng/test với `--enable-preview`.

JDK 27 tiếp tục PEM Encodings of Cryptographic Objects theo JEP 524 (Second Preview). Preview API có thể thay đổi giữa các release; hãy biên dịch lại và kiểm tra Javadoc đúng phiên bản JDK đích. Không giả định code compile với JDK 26 sẽ tương thích nguyên trạng với JDK 27 hoặc release sau.

## 15. Khi nào nên dùng PEMDecoder?

| Nhu cầu | Cách dùng |
|---|---|
| Đọc certificate PEM | `decode(text, X509Certificate.class)` |
| Đọc public key PEM | `decode(text, PublicKey.class)` |
| Đọc private key PKCS#8 không mã hóa | `decode(text, PrivateKey.class)` |
| Đọc private key mã hóa | `withDecryption(password).decode(text, PrivateKey.class)` |
| Nhận KeySpec thay vì Key | Yêu cầu `X509EncodedKeySpec.class` hoặc `PKCS8EncodedKeySpec.class` |
| Đọc PEM type chưa có class Java tương ứng | `decode(text, PEM.class)` |
| Đọc từ file/stream | Dùng overload `InputStream` và try-with-resources |
| Cần Provider cụ thể | `withFactory(provider)` trước khi decode |

Nếu ứng dụng cần API ổn định cho nhiều JDK, các API JCA như `CertificateFactory`, `KeyFactory`, `PKCS8EncodedKeySpec`, `X509EncodedKeySpec` và `Base64` vẫn là những lựa chọn ổn định để xây dựng quy trình đọc PEM theo định dạng đã xác định. Không cần đưa preview `PEMDecoder` vào public API chỉ để giảm một vài dòng chuyển đổi.

## Kết luận

`PEMDecoder.of()` tạo decoder và `decode(data, TargetType.class)` cho phép chọn kiểu Java đích ngay khi giải mã. JDK 26 hỗ trợ các kiểu phổ biến như `X509Certificate`, `X509CRL`, `PublicKey`, `PrivateKey`, `KeyPair`, KeySpec và `EncryptedPrivateKeyInfo`; với loại chưa được ánh xạ, có thể yêu cầu `PEM.class` để lấy nhãn, Base64 content và leading data. Dùng `InputStream` với try-with-resources, cấu hình `withDecryption(char[])` cho private key được mã hóa và `withFactory(Provider)` khi cần Provider cụ thể. Trong JDK 26, API vẫn là preview theo JEP 470, vì vậy phải bật `--enable-preview` ở cả compile và runtime, đồng thời đánh giá khả năng tương thích trước khi dùng trong production.

## Tài liệu tham khảo

- [JEP 470: PEM Encodings of Cryptographic Objects (Preview)](https://openjdk.org/jeps/470)
- [JDK 26 API – PEMDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html)
- [JDK 26 API – PEM](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEM.html)
- [JDK 26 API – DEREncodable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/DEREncodable.html)
- [JDK 26 API – EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html)
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [JEP 524: PEM Encodings of Cryptographic Objects (Second Preview), JDK 27](https://openjdk.org/jeps/524)
- [RFC 7468: Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468)
