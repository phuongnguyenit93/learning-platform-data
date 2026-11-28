# Kiểm thử mã hóa, giải mã và trao đổi với công cụ độc lập

PEM là định dạng văn bản để vận chuyển và lưu trữ các cấu trúc mật mã được mã hóa nhị phân, chẳng hạn khóa công khai, khóa riêng, chứng thư X.509 và danh sách thu hồi chứng thư. Để kiểm thử PEM đúng cách, cần kiểm tra cả hai chiều: Java đọc được dữ liệu do công cụ khác tạo, và công cụ khác đọc được dữ liệu do Java tạo.

Java 25 giới thiệu preview đầu tiên của PEM API; Java 26 tiếp tục ở **JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)** trong module `java.base`. Đây là preview API, vì vậy ví dụ Java 26 phải bật preview khi biên dịch và chạy. JDK 27 hiện vẫn đánh dấu tính năng này là preview lần thứ hai, nhưng đã đổi một số kiểu và tên phương thức. Bài này dùng API JDK 26 cho ví dụ chính, sau đó nêu rõ thay đổi cần áp dụng khi nâng JDK.

## 1. PEM chứa gì?

PEM không phải thuật toán mã hóa và cũng không tự bảo vệ bí mật. Nó là cách biểu diễn văn bản của dữ liệu nhị phân, thường là cấu trúc ASN.1 được mã hóa DER, sau đó chuyển thành Base64 và đặt giữa hai dòng nhãn.

Ví dụ cấu trúc:

    -----BEGIN PUBLIC KEY-----
    MIIB...Base64 content...
    -----END PUBLIC KEY-----

Phần nhãn cho biết loại cấu trúc bên trong. Phần Base64 chỉ chuyển dữ liệu nhị phân thành văn bản ASCII để trao đổi qua file, cấu hình hoặc giao thức văn bản. Nếu PEM chứa khóa riêng không mã hóa, bất kỳ ai đọc được file đều có thể lấy khóa riêng.

Một số nhãn thường gặp:

| Nhãn PEM | Cấu trúc thường chứa | API Java tương ứng |
|---|---|---|
| `CERTIFICATE` | Chứng thư X.509 | `X509Certificate` |
| `PUBLIC KEY` | SubjectPublicKeyInfo theo X.509 | `PublicKey` |
| `PRIVATE KEY` | PrivateKeyInfo/OneAsymmetricKey theo PKCS #8, không mã hóa | `PrivateKey` hoặc `KeyPair` nếu có public key |
| `ENCRYPTED PRIVATE KEY` | EncryptedPrivateKeyInfo theo PKCS #8 | `EncryptedPrivateKeyInfo`, hoặc khóa đã giải mã |
| `X509 CRL` | Certificate Revocation List | `X509CRL` |
| `CERTIFICATE REQUEST` | Yêu cầu cấp chứng thư PKCS #10 | `PEM` wrapper nếu không có kiểu Java tương ứng |

Đừng nhầm nhãn với thuật toán. `PRIVATE KEY` là cấu trúc PKCS #8 có thể chứa nhiều loại khóa như RSA hoặc EC; nó không có nghĩa khóa đó luôn là RSA. Tương tự, `PUBLIC KEY` là dạng bao khóa công khai chuẩn hóa, không phải một thuật toán cụ thể.

Theo RFC 7468, dòng mở đầu và kết thúc phải dùng cùng nhãn, mỗi dòng có đúng năm dấu gạch nối ở hai bên, và dữ liệu Base64 được ngắt dòng theo quy tắc của chuẩn. Các bộ sinh mới nên tạo định dạng chuẩn; tránh tự sửa nhãn hoặc cắt ghép phần Base64 bằng trình soạn thảo văn bản.

## 2. Trạng thái PEM API trong Java 26 và Java 27

| Phiên bản | JEP | Trạng thái |
|---|---|---|
| Java 25 | JEP 470 | Preview lần đầu |
| Java 26 | JEP 524 | Preview lần thứ hai; API có thay đổi so với Java 25 |
| Java 27 | JEP 524 | Vẫn là preview lần thứ hai; API tiếp tục được điều chỉnh |

Các API chính của Java 26:

- **`PEMEncoder`**: mã hóa các đối tượng mật mã thành PEM bằng `encode(...)` hoặc `encodeToString(...)`.
- **`PEMDecoder`**: giải mã PEM thành đối tượng Java bằng `decode(...)`.
- **`DEREncodable`**: giao diện preview đánh dấu các đối tượng có thể biểu diễn bằng DER.
- **`PEM`**: record preview dùng để giữ nhãn, nội dung Base64 và dữ liệu xuất hiện trước PEM block nếu kiểu dữ liệu không có lớp mật mã tương ứng trong Java.
- **`EncryptedPrivateKeyInfo`**: biểu diễn khóa riêng PKCS #8 đã mã hóa và hỗ trợ giải mã bằng mật khẩu.

Các lớp này nằm trong module `java.base`, không cần thêm module incubator. Tuy nhiên, chúng là preview API nên phải dùng đúng JDK release và bật preview ở cả compiler lẫn runtime.

## 3. Chuẩn bị công cụ độc lập OpenSSL

OpenSSL là công cụ độc lập phù hợp để kiểm tra việc trao đổi PEM giữa Java và một implementation mật mã khác. Trước tiên, xác nhận OpenSSL đã cài và có trong PATH:

    openssl version

Trong thư mục thử nghiệm riêng, tạo một khóa RSA và chứng thư tự ký. Đây chỉ là dữ liệu kiểm thử ngắn hạn:

    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out openssl-private-key.pem

    openssl pkey -in openssl-private-key.pem -pubout -out openssl-public-key.pem

    openssl req -new -x509 -key openssl-private-key.pem -sha256 -days 30 -out openssl-certificate.pem -subj "/CN=localhost" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,digitalSignature,keyCertSign,cRLSign" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

Lệnh `genpkey` tạo khóa riêng theo định dạng PKCS #8 không mã hóa; `pkey -pubout` trích xuất khóa công khai; `req -new -x509` tạo chứng thư tự ký chứa khóa công khai tương ứng. Phần mở rộng Subject Alternative Name cho phép kiểm tra hostname `localhost`.

Kiểm tra các file trước khi đưa vào Java:

    openssl pkey -in openssl-private-key.pem -check -noout

    openssl pkey -pubin -in openssl-public-key.pem -pubcheck -noout

    openssl x509 -in openssl-certificate.pem -noout -subject -issuer -dates -ext subjectAltName

    openssl verify -CAfile openssl-certificate.pem -verify_hostname localhost openssl-certificate.pem

Kết quả mong đợi là khóa riêng và khóa công khai được kiểm tra hợp lệ, chứng thư hiển thị đúng Subject/SAN và lệnh verify trả về `OK`. Chứng thư tự ký được tin cậy ở đây chỉ vì chính file đó được truyền làm CAfile cho bài lab; điều này không tạo ra trust anchor hợp lệ cho hệ thống thật.

## 4. Đọc PEM do OpenSSL tạo bằng Java 26

Java 26 cung cấp decoder có thể trả về đúng kiểu Java dựa trên nhãn PEM. Nên dùng overload có tham số `Class` khi biết trước loại dữ liệu, vì cách này tránh ép kiểu thủ công và phát hiện nhầm loại PEM sớm.

Ví dụ sau đọc khóa riêng, khóa công khai và chứng thư do OpenSSL tạo. Sau đó, chương trình xác minh chứng thư, kiểm tra khóa công khai trong chứng thư khớp với file public key, ký một thông điệp bằng private key và kiểm tra chữ ký bằng public key. Cuối cùng, Java mã hóa lại ba đối tượng thành PEM để OpenSSL đọc ở bước tiếp theo.

    import java.nio.charset.StandardCharsets;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import java.security.MessageDigest;
    import java.security.PrivateKey;
    import java.security.PublicKey;
    import java.security.Signature;
    import java.security.PEMDecoder;
    import java.security.PEMEncoder;
    import java.security.cert.X509Certificate;

    public class PemInterop26 {

        public static void main(String[] args) throws Exception {
            PEMDecoder decoder = PEMDecoder.of();
            PEMEncoder encoder = PEMEncoder.of();

            String privateText = Files.readString(
                    Path.of("openssl-private-key.pem"),
                    StandardCharsets.US_ASCII
            );
            String publicText = Files.readString(
                    Path.of("openssl-public-key.pem"),
                    StandardCharsets.US_ASCII
            );
            String certificateText = Files.readString(
                    Path.of("openssl-certificate.pem"),
                    StandardCharsets.US_ASCII
            );

            PrivateKey privateKey =
                    decoder.decode(privateText, PrivateKey.class);
            PublicKey publicKey =
                    decoder.decode(publicText, PublicKey.class);
            X509Certificate certificate =
                    decoder.decode(certificateText, X509Certificate.class);

            certificate.checkValidity();

            if (!MessageDigest.isEqual(
                    certificate.getPublicKey().getEncoded(),
                    publicKey.getEncoded())) {
                throw new IllegalStateException(
                        "Public key trong certificate không khớp"
                );
            }

            certificate.verify(publicKey);

            byte[] message =
                    "PEM interoperability test".getBytes(StandardCharsets.UTF_8);

            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(privateKey);
            signer.update(message);
            byte[] signed = signer.sign();

            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(certificate.getPublicKey());
            verifier.update(message);

            if (!verifier.verify(signed)) {
                throw new IllegalStateException("Chữ ký không hợp lệ");
            }

            Files.writeString(
                    Path.of("java-private-key.pem"),
                    encoder.encodeToString(privateKey),
                    StandardCharsets.US_ASCII
            );
            Files.writeString(
                    Path.of("java-public-key.pem"),
                    encoder.encodeToString(publicKey),
                    StandardCharsets.US_ASCII
            );
            Files.writeString(
                    Path.of("java-certificate.pem"),
                    encoder.encodeToString(certificate),
                    StandardCharsets.US_ASCII
            );

            System.out.println("Đã giải mã PEM và kiểm tra chữ ký thành công.");
            System.out.println("Đã ghi lại ba PEM file do Java tạo.");
        }
    }

Biên dịch và chạy bằng JDK 26:

    javac --enable-preview --release 26 -encoding UTF-8 -d out src/PemInterop26.java

    java --enable-preview -cp out PemInterop26

Chương trình cần đọc được ba file PEM do OpenSSL tạo. Việc ký rồi xác minh chữ ký chứng minh private key và public key tương ứng về mặt mật mã. Việc so sánh public key trong certificate với file public key kiểm tra thêm rằng chứng thư đang dùng đúng cặp khóa thử nghiệm.

`certificate.verify(publicKey)` chỉ xác minh chữ ký của chứng thư bằng public key được cung cấp. `checkValidity()` kiểm tra thời hạn chứng thư. Hai lệnh này không tự xây dựng chuỗi tin cậy, kiểm tra trạng thái thu hồi hoặc thay thế việc xác minh hostname trong TLS.

## 5. Kiểm tra PEM do Java tạo bằng OpenSSL

Sau khi chạy chương trình Java, dùng OpenSSL đọc lại các file Java vừa tạo:

    openssl pkey -in java-private-key.pem -check -noout

    openssl pkey -pubin -in java-public-key.pem -pubcheck -noout

    openssl x509 -in java-certificate.pem -noout -subject -issuer -dates -ext subjectAltName

    openssl verify -CAfile java-certificate.pem -verify_hostname localhost java-certificate.pem

Nếu OpenSSL đọc được file, nhận dạng đúng loại cấu trúc, kiểm tra được khóa và xác minh chứng thư trong môi trường lab, Java và OpenSSL đã trao đổi được các dạng PEM tương ứng.

Có thể so sánh public key lấy từ ba nguồn: private key, file public key và certificate. Xuất từng public key về DER trước:

    openssl pkey -in java-private-key.pem -pubout -outform DER -out public-from-private.der

    openssl pkey -pubin -in java-public-key.pem -pubout -outform DER -out public-from-pem.der

    openssl x509 -in java-certificate.pem -pubkey -noout -out certificate-public.pem

    openssl pkey -pubin -in certificate-public.pem -pubout -outform DER -out public-from-certificate.der

Sau đó tính SHA-256:

    openssl dgst -sha256 public-from-private.der public-from-pem.der public-from-certificate.der

Ba digest phải giống nhau. Đây là cách đối chiếu độc lập rằng private key, public key và certificate chứa cùng một public key.

Không so sánh nguyên văn hai file PEM để kết luận chúng chứa cùng khóa. Cùng một đối tượng DER có thể được trình bày với khác biệt về xuống dòng, khoảng trắng hoặc cách tạo PEM. So sánh biểu diễn DER hoặc thực hiện thao tác ký/xác minh mới kiểm tra đúng nội dung mật mã.

## 6. Kiểm thử khóa riêng được mã hóa bằng mật khẩu

PEM không tự mã hóa khóa riêng. Nếu file có nhãn `PRIVATE KEY`, nội dung PKCS #8 không được bảo vệ bằng mật khẩu. Khi cần lưu hoặc trao đổi private key qua file, hãy dùng nhãn `ENCRYPTED PRIVATE KEY` với cấu trúc PKCS #8 EncryptedPrivateKeyInfo và thuật toán password-based encryption phù hợp.

Java 26 có thể mã hóa private key bằng `PEMEncoder.withEncryption(char[])` và giải mã bằng `PEMDecoder.withDecryption(char[])`. Ví dụ dưới đây lấy mật khẩu từ console thay vì ghi trực tiếp vào mã nguồn:

    import java.io.Console;
    import java.nio.charset.StandardCharsets;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import java.security.PrivateKey;
    import java.security.PEMDecoder;
    import java.security.PEMEncoder;
    import java.util.Arrays;

    Console console = System.console();
    if (console == null) {
        throw new IllegalStateException(
                "Hãy chạy từ terminal có hỗ trợ Console"
        );
    }

    char[] password = console.readPassword("Mật khẩu PEM: ");

    try {
        String encryptedPem = PEMEncoder.of()
                .withEncryption(password)
                .encodeToString(privateKey);

        Files.writeString(
                Path.of("java-encrypted-private-key.pem"),
                encryptedPem,
                StandardCharsets.US_ASCII
        );

        PrivateKey recovered = PEMDecoder.of()
                .withDecryption(password)
                .decode(encryptedPem, PrivateKey.class);

        if (!Arrays.equals(
                privateKey.getEncoded(),
                recovered.getEncoded())) {
            throw new IllegalStateException(
                    "Private key sau giải mã không khớp"
            );
        }
    } finally {
        Arrays.fill(password, '\0');
    }

`withEncryption` chỉ hỗ trợ các đối tượng private key, key pair và PKCS8EncodedKeySpec. Mật khẩu được API sao chép vào encoder/decoder đã cấu hình; việc xóa mảng mật khẩu của ứng dụng không xóa được bản sao nội bộ. Hãy giữ các instance đã cấu hình trong phạm vi ngắn, tránh ghi mật khẩu vào log và không giữ chúng lâu hơn cần thiết.

OpenSSL có thể đọc file khóa riêng đã mã hóa và hỏi mật khẩu tương tác:

    openssl pkey -in java-encrypted-private-key.pem -check -noout

Không truyền mật khẩu thật bằng tham số dòng lệnh như `-passin pass:...`, vì giá trị có thể xuất hiện trong lịch sử shell hoặc danh sách tiến trình.

Để kiểm tra chiều ngược lại, tạo khóa PKCS #8 mã hóa bằng OpenSSL:

    openssl pkcs8 -topk8 -in openssl-private-key.pem -out openssl-encrypted-private-key.pem -v2 aes-256-cbc -v2prf hmacWithSHA256 -iter 600000

OpenSSL hỏi mật khẩu khi tạo file. Dùng Java 26 với `PEMDecoder.of().withDecryption(password)` để giải mã file này. Nếu giải mã không thành công, kiểm tra thuật toán PBE, tham số KDF, provider và khả năng hỗ trợ của JDK; không kết luận rằng mọi file ENCRYPTED PRIVATE KEY đều dùng cùng một thuật toán.

Mặc định PBE của Java được điều khiển bởi security property `jdk.epkcs8.defaultAlgorithm`; tham số cụ thể còn phụ thuộc provider. Giá trị mặc định có thể thay đổi theo JDK hoặc provider, nhưng file đã tạo mang theo AlgorithmIdentifier và tham số cần cho giải mã. Khi cần khả năng tương thích ổn định giữa nhiều hệ thống, hãy chốt thuật toán/parameter được hai phía hỗ trợ và kiểm thử với đúng phiên bản OpenSSL/JDK triển khai.

## 7. Xử lý PEM type chưa có lớp Java tương ứng

Không phải mọi nhãn PEM đều có lớp đối tượng mật mã trong Java. Ví dụ, PKCS #10 CSR dùng nhãn `CERTIFICATE REQUEST`. Trong trường hợp này, JDK 26 có thể trả về đối tượng `PEM` để ứng dụng đọc nhãn và nội dung Base64:

    import java.nio.charset.StandardCharsets;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import java.security.PEM;
    import java.security.PEMDecoder;

    String csrText = Files.readString(
            Path.of("request.csr"),
            StandardCharsets.US_ASCII
    );

    PEM csr = PEMDecoder.of().decode(csrText, PEM.class);

    System.out.println("PEM type: " + csr.type());
    byte[] csrDer = csr.decode();

`PEM.decode()` chỉ giải mã Base64 thành byte array. Nó không xác minh chữ ký CSR, không xác minh nội dung ASN.1 phù hợp với nhãn và không chứng minh yêu cầu được tạo bởi người sở hữu private key. JDK 26 cũng không cung cấp lớp CSR chuẩn tương ứng trong danh sách đối tượng được PEMDecoder giải mã.

Dùng OpenSSL để kiểm tra cấu trúc và chữ ký CSR:

    openssl req -new -key openssl-private-key.pem -out request.csr -subj "/CN=localhost"

    openssl req -in request.csr -noout -verify -text

Nếu cần tái xuất một PEM type không có lớp Java tương ứng, có thể dùng `PEMEncoder` với đối tượng `PEM`. Tuy nhiên, constructor `PEM` không xác minh nội dung Base64 có thật sự tương ứng với nhãn đã khai báo. Không dùng thao tác re-encode như một phép kiểm tra tính hợp lệ của CSR, CMS, PKCS7 hoặc cấu trúc ASN.1 khác.

## 8. Đọc lỗi và phân loại kết quả kiểm thử

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `IllegalArgumentException` khi decode | PEM không có block, Base64 sai, nhãn không hỗ trợ hoặc nội dung không giải mã được | Kiểm tra BEGIN/END label, Base64 và cấu trúc DER |
| `ClassCastException` hoặc lỗi kiểu khi decode | Class yêu cầu không tương ứng với nhãn PEM | Dùng đúng class như `PrivateKey.class`, `PublicKey.class`, `X509Certificate.class` hoặc `PEM.class` |
| `NoSuchAlgorithmException` hoặc lỗi KeyFactory | Thuật toán trong khóa không được provider hỗ trợ | Kiểm tra `key.getAlgorithm()`, provider và thuật toán JDK hỗ trợ |
| Lỗi giải mã khóa mã hóa | Mật khẩu sai, thuật toán PBE hoặc tham số không tương thích | Kiểm tra password, AlgorithmIdentifier và provider |
| OpenSSL đọc private key nhưng Java không đọc được | Loại cấu trúc, thuật toán hoặc provider khác với phần Java hỗ trợ | Kiểm tra nhãn, PKCS #8, thuật toán và API decoder |
| Java đọc certificate nhưng verify thất bại | Chữ ký certificate không khớp public key, certificate hỏng hoặc dùng sai issuer key | So sánh public key, issuer và chữ ký |
| Parse certificate thành công nhưng TLS không tin cậy | Parse PEM không xác minh trust chain, hostname hoặc trạng thái thu hồi | Kiểm tra truststore, CertPath/TrustManager, SAN và chính sách PKI |

Với `decode(InputStream)`, nếu gặp lỗi I/O trong lúc đọc, vị trí stream có thể không còn nhất quán; API khuyến nghị không tiếp tục giải mã trên stream đó. Nếu file chỉ có một PEM block, đọc bằng `Files.readString` rồi dùng overload String cũng dễ kiểm tra hơn.

Khi decoder gặp loại PEM chưa có class tương ứng, nó trả về `PEM` thay vì tự tạo một đối tượng mật mã không phù hợp. Ứng dụng nên xử lý trường hợp này tường minh và chuyển cho parser chuyên biệt nếu nghiệp vụ cần xác minh cấu trúc.

## 9. Phân biệt kiểm tra PEM với kiểm tra tin cậy chứng thư

Một kiểm thử PEM tốt cần tách ba mức xác nhận:

1. **Định dạng:** parser nhận đúng header/footer, Base64 và dữ liệu DER.
2. **Đối tượng mật mã:** khóa có thể được sử dụng, chữ ký có thể được tạo và xác minh, chứng thư có chữ ký hợp lệ và còn hạn.
3. **Tin cậy trong ngữ cảnh sử dụng:** chứng thư có chuỗi tin cậy đến CA được cấu hình, hostname khớp SAN, key usage/EKU phù hợp, chính sách thu hồi và thời hạn được đáp ứng.

PEMDecoder chủ yếu giải quyết mức thứ nhất và tạo đối tượng cho mức thứ hai. Nó không thay thế PKIX path validation hoặc kiểm tra TLS hostname. Một certificate đọc được bằng Java không đồng nghĩa server được tin cậy.

Trong Java, có thể dùng `CertPathValidator` với `PKIX` hoặc cấu hình `TrustManagerFactory` để kiểm tra chuỗi tin cậy theo truststore. Trong OpenSSL, dùng `openssl verify -CAfile ... -verify_hostname ...` với CA và certificate phù hợp. Không dùng certificate tự ký của bài lab làm trust anchor production.

## 10. Khác biệt API khi chuyển từ JDK 26 sang JDK 27

JDK 27 tiếp tục PEM Encodings of Cryptographic Objects ở **JEP 524, Second Preview**. Các ý tưởng mã hóa/giải mã vẫn tương tự, nhưng API thay đổi đủ lớn để mã nguồn Java 26 cần được điều chỉnh.

| Thành phần | Java 26 | Java 27 |
|---|---|---|
| Giao diện biểu diễn dữ liệu nhị phân | `DEREncodable` | `BinaryEncodable` |
| `PEM` | Record; content là Base64 String và có `leadingData` | Class; content được biểu diễn bằng byte array và dữ liệu được defensive-copy |
| Decoder chỉ định Provider | `withFactory(Provider)` | `withFactoriesOf(Provider)` |
| Lỗi giải mã khóa mã hóa | `IllegalArgumentException` | `CryptoException` preview |
| Kiểu tham số của `PEMEncoder.encode(...)` | `DEREncodable` | `BinaryEncodable` |

Vì vậy, không chỉ đổi cờ `--release 26` thành `--release 27` rồi kỳ vọng code giữ nguyên. Khi nâng JDK, hãy sửa import/type, kiểm tra lại cách đọc nội dung `PEM`, đổi tên phương thức Provider và cập nhật catch block cho `CryptoException`.

Ví dụ dùng JDK 27 sẽ khai báo kiểu tổng quát là `BinaryEncodable`:

    import java.security.BinaryEncodable;
    import java.security.PEMDecoder;

    BinaryEncodable decoded =
            PEMDecoder.of().decode(pemText);

Nếu cần giải mã thành kiểu cụ thể, overload có tham số Class vẫn là lựa chọn rõ ràng:

    PrivateKey privateKey =
            PEMDecoder.of().decode(pemText, PrivateKey.class);

PEM API vẫn là preview trong JDK 27. Hãy kiểm tra Preview API List và Java API Specification của release đích trước khi nâng cấp; không đưa API này vào public contract cần tương thích lâu dài khi chưa chấp nhận rủi ro thay đổi.

## 11. Quy trình kiểm thử hai chiều trước khi tích hợp

1. Ghi nhận phiên bản JDK và OpenSSL bằng `java --version`, `javac --version` và `openssl version`.
2. Tạo khóa, public key và certificate thử nghiệm bằng OpenSSL; dùng PKCS #8 và X.509 hiện hành.
3. Kiểm tra file nguồn bằng `openssl pkey`, `openssl x509` và `openssl verify`.
4. Dùng PEMDecoder của Java đọc từng file với đúng class đích.
5. Xác minh khóa công khai trong certificate khớp public key, certificate còn hạn và chữ ký thử nghiệm hợp lệ.
6. Dùng PEMEncoder tạo lại private key, public key và certificate thành file PEM mới.
7. Dùng OpenSSL đọc lại và kiểm tra các file do Java tạo.
8. So sánh digest của public key ở private key, public key PEM và certificate.
9. Nếu dùng encrypted private key, kiểm thử cả chiều Java mã hóa/OpenSSL giải mã và OpenSSL mã hóa/Java giải mã.
10. Lặp lại trên JDK release sẽ triển khai, cập nhật API preview và ghi nhận provider/thuật toán PBE thực tế.

Một lần decode thành công chưa đủ chứng minh tương thích. Bằng chứng tốt hơn là cả hai công cụ đều đọc được file do công cụ còn lại tạo, cùng xác minh được public key và thực hiện được thao tác mật mã phù hợp.

## 12. Lưu ý bảo mật khi chia sẻ file PEM

- Không commit private key, password, file khóa thử nghiệm hoặc log có nội dung khóa vào Git.
- Không ghi nội dung PEM private key ra log; log chỉ nên ghi loại đối tượng, thuật toán, fingerprint hoặc kết quả kiểm tra phù hợp.
- Giới hạn quyền đọc file private key và xóa file tạm sau khi hoàn thành bài lab.
- Dùng `ENCRYPTED PRIVATE KEY` khi cần lưu private key bằng mật khẩu; không xem Base64 là biện pháp mã hóa.
- Không đặt mật khẩu thật trong command line hoặc mã nguồn. Dùng prompt bảo mật hoặc secret manager.
- Không tự bỏ xác minh certificate chỉ vì PEM đã parse thành công.
- Không dùng một self-signed certificate trong bài lab làm chứng thư production.
- Khi triển khai thật, ưu tiên quản lý khóa trong HSM, KMS hoặc keystore phù hợp nếu yêu cầu bảo mật và vòng đời khóa đòi hỏi.

PEM chỉ là lớp biểu diễn và trao đổi. Việc chọn thuật toán, độ mạnh khóa, bảo vệ private key, kiểm tra chứng thư và quản lý trust vẫn phải tuân theo chính sách bảo mật của ứng dụng.

## Tài liệu chính thức

- [JEP 524 — PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524): phạm vi API preview trong Java 26.
- [Java SE 26 API — PEMEncoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html): loại đối tượng hỗ trợ, PEM type và mã hóa khóa riêng bằng mật khẩu.
- [Java SE 26 API — PEMDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html): giải mã theo kiểu, Provider và xử lý khóa riêng đã mã hóa.
- [Java SE 26 API — PEM](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEM.html): xử lý PEM type không có class mật mã Java tương ứng.
- [Oracle — Java Cryptography Architecture Reference Guide, PEM Transport Format](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html): ví dụ encode/decode, password encryption và xử lý PEM type tổng quát.
- [Java SE 27 API — PEMEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html): API preview hiện hành với BinaryEncodable.
- [Java SE 27 API — PEMDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html): API hiện hành, Provider factory và CryptoException.
- [Java SE 27 API — BinaryEncodable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html): giao diện thay thế DEREncodable trong JDK 27.
- [Java SE 27 API — EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): PKCS #8 EncryptedPrivateKeyInfo và API encrypt/decrypt.
- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468): quy tắc nhãn, Base64, dòng và các loại PEM chuẩn.
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958): cấu trúc OneAsymmetricKey dùng cho gói khóa.
- [OpenSSL 3.5 — pkey](https://docs.openssl.org/3.5/man1/openssl-pkey/): kiểm tra, đọc và xuất khóa công khai/riêng.
- [OpenSSL 3.5 — x509](https://docs.openssl.org/3.5/man1/openssl-x509/): đọc, kiểm tra và hiển thị chứng thư X.509.
- [OpenSSL 3.5 — pkcs8](https://docs.openssl.org/3.5/man1/openssl-pkcs8/): chuyển đổi và mã hóa khóa riêng PKCS #8.
- [OpenSSL 3.5 — verify](https://docs.openssl.org/3.5/man1/openssl-verify/): xác minh chuỗi chứng thư và hostname.

Tại ngày 27-11-2026, PEMEncoder/PEMDecoder vẫn là preview API trong JDK 26 và JDK 27. Bài thực hành dùng chuẩn PEM/PKCS #8/X.509 hiện hành, không dựa vào định dạng khóa riêng legacy; hãy xác nhận API và provider trên đúng JDK trước khi triển khai.
