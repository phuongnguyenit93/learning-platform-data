# KeyFactory trong Java Cryptography Architecture

**KeyFactory** là lớp engine của Java Cryptography Architecture (JCA) dùng để chuyển đổi giữa biểu diễn khóa (KeySpec) và đối tượng khóa Java (Key). Ứng dụng có thể tạo đối tượng PublicKey hoặc PrivateKey từ dữ liệu khóa đã mã hóa, trích xuất một dạng KeySpec từ đối tượng khóa có thể xuất, hoặc chuyển khóa sang cách biểu diễn do provider hiện tại hỗ trợ.

KeyFactory thường xuất hiện khi ứng dụng nhận khóa công khai từ chứng thư, nạp khóa riêng từ tệp PKCS#8, hoặc cần trao đổi khóa giữa các thư viện mật mã. Nó không tự sinh một cặp khóa mới, không lưu trữ khóa như KeyStore và cũng không thực hiện mã hóa dữ liệu như Cipher. Hiểu đúng vai trò này giúp ứng dụng chuyển đổi khóa mà vẫn giữ được ranh giới bảo vệ key material trong vòng đời quản lý khóa.

## 1. KeyFactory nằm ở đâu trong JCA?

JCA cung cấp các lớp engine có giao diện thống nhất để ứng dụng sử dụng thuật toán mật mã thông qua provider. **KeyFactory** chịu trách nhiệm chuyển đổi biểu diễn của khóa bất đối xứng thành đối tượng khóa mà các API khác có thể sử dụng.

Ví dụ, một ứng dụng nhận khóa công khai RSA ở dạng DER được mã hóa Base64 trong PEM. Ứng dụng giải mã Base64 để lấy byte DER, bọc byte đó bằng **X509EncodedKeySpec**, rồi dùng KeyFactory RSA để tạo **PublicKey**. Sau đó PublicKey có thể được truyền cho Cipher, Signature hoặc một API phù hợp khác.

| Thành phần | Vai trò |
|---|---|
| KeyFactory | Chuyển đổi giữa KeySpec và đối tượng Key. |
| KeySpec | Mô tả khóa bằng cấu trúc cụ thể hoặc dữ liệu mã hóa. |
| PublicKey / PrivateKey | Giao diện đối tượng khóa công khai và khóa riêng. |
| Provider | Cung cấp triển khai KeyFactory và kiểu khóa tương ứng. |
| KeyPairGenerator | Sinh cặp khóa công khai/riêng mới. |
| SecretKeyFactory | Chuyển đổi hoặc tạo khóa bí mật đối xứng từ KeySpec phù hợp. |
| KeyStore | Lưu và quản lý các mục khóa/chứng thư theo alias. |

KeyFactory được lấy theo tên thuật toán, chẳng hạn RSA hoặc EC:

~~~java
KeyFactory rsaFactory = KeyFactory.getInstance("RSA");
KeyFactory ecFactory = KeyFactory.getInstance("EC");
~~~

Provider được chọn phải hỗ trợ thuật toán và loại KeySpec được yêu cầu. Khi làm việc với HSM hoặc provider chuyên dụng, cần kiểm tra tài liệu provider vì khả năng xuất/nhập khóa, định dạng mã hóa và loại KeySpec được hỗ trợ có thể khác nhau.

## 2. KeySpec và các định dạng khóa phổ biến

**KeySpec** là mô tả dữ liệu của khóa. Một số KeySpec mô tả các thành phần toán học của khóa; một số khác chứa toàn bộ biểu diễn khóa đã mã hóa.

| KeySpec | Dữ liệu mô tả | Trường hợp sử dụng |
|---|---|---|
| X509EncodedKeySpec | Khóa công khai được mã hóa theo cấu trúc SubjectPublicKeyInfo của X.509. | Nạp khóa công khai từ PEM có nhãn PUBLIC KEY hoặc dữ liệu DER tương ứng. |
| PKCS8EncodedKeySpec | Khóa riêng được mã hóa theo cấu trúc PrivateKeyInfo của PKCS#8. | Nạp khóa riêng từ PEM có nhãn PRIVATE KEY hoặc dữ liệu DER tương ứng. |
| RSAPublicKeySpec | Modulus và public exponent của RSA. | Tạo PublicKey RSA từ các thành phần toán học. |
| RSAPrivateKeySpec | Modulus và private exponent của RSA. | Tạo PrivateKey RSA từ thành phần khóa phù hợp. |
| RSAPrivateCrtKeySpec | Các thành phần RSA CRT như p, q, dP, dQ và qInv. | Tạo khóa riêng RSA có thông tin CRT khi nguồn dữ liệu cung cấp đầy đủ. |
| ECPublicKeySpec | Điểm công khai và tham số đường cong elliptic. | Tạo khóa công khai EC từ các thành phần EC. |
| ECPrivateKeySpec | Giá trị bí mật và tham số đường cong elliptic. | Tạo khóa riêng EC từ các thành phần EC. |

Hai định dạng mã hóa thường gặp cần phân biệt:

- **X.509 SubjectPublicKeyInfo** (thường được gọi ngắn là X.509 encoded public key) chứa thuật toán và khóa công khai. Java biểu diễn dạng này bằng X509EncodedKeySpec.
- **PKCS#8 PrivateKeyInfo** chứa thuật toán và dữ liệu khóa riêng. Java biểu diễn dạng này bằng PKCS8EncodedKeySpec.

Tên PEM là một chỉ dấu hữu ích nhưng phải đọc đúng loại cấu trúc:

| Nhãn PEM | Nội dung |
|---|---|
| BEGIN PUBLIC KEY | SubjectPublicKeyInfo, thường dùng với X509EncodedKeySpec. |
| BEGIN PRIVATE KEY | PKCS#8 không mã hóa, thường dùng với PKCS8EncodedKeySpec. |
| BEGIN ENCRYPTED PRIVATE KEY | PKCS#8 được mã hóa; cần giải mã bằng mật khẩu và thuật toán bảo vệ trước khi tạo PKCS8EncodedKeySpec. |
| BEGIN RSA PUBLIC KEY | Khóa công khai RSA dạng PKCS#1, không phải SubjectPublicKeyInfo. |
| BEGIN RSA PRIVATE KEY | Khóa riêng RSA dạng PKCS#1, không phải PKCS#8. |
| BEGIN CERTIFICATE | Chứng thư X.509; dùng CertificateFactory để phân tích chứng thư rồi lấy khóa công khai. |

Không được đưa trực tiếp mọi nội dung PEM vào X509EncodedKeySpec hoặc PKCS8EncodedKeySpec. Cần xác định đúng cấu trúc DER bên trong. Với khóa RSA dạng PKCS#1, ứng dụng cần chuyển đổi sang cấu trúc phù hợp hoặc dùng thư viện hỗ trợ định dạng đó. Với khóa riêng được mã hóa, phải giải mã theo định dạng và thuật toán đã sử dụng trước khi đưa dữ liệu PKCS#8 đã giải mã vào KeyFactory.

## 3. Tạo PublicKey từ dữ liệu X.509

Ví dụ sau đọc một tệp PEM có nhãn PUBLIC KEY, loại bỏ phần nhãn, giải mã Base64 và tạo PublicKey RSA:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

public class PublicKeyLoader {
    public static PublicKey loadRsaPublicKey(Path pemPath)
            throws Exception {
        String pem = Files.readString(
                pemPath, StandardCharsets.US_ASCII);

        String base64 = pem
                .replace("-----BEGIN PUBLIC KEY-----", "")
                .replace("-----END PUBLIC KEY-----", "")
                .replaceAll("\\s", "");

        byte[] der = Base64.getDecoder().decode(base64);
        X509EncodedKeySpec keySpec = new X509EncodedKeySpec(der);
        KeyFactory keyFactory = KeyFactory.getInstance("RSA");
        return keyFactory.generatePublic(keySpec);
    }
}
~~~

Ví dụ yêu cầu tệp có đúng nhãn PUBLIC KEY và chứa SubjectPublicKeyInfo của RSA. Trong mã sản xuất, cần kiểm tra nhãn PEM, giới hạn kích thước đầu vào, xử lý lỗi Base64/DER và xác minh thuật toán mong đợi. Đọc được khóa công khai không đồng nghĩa đã xác minh danh tính của chủ sở hữu khóa; ứng dụng cần kiểm tra chứng thư, chữ ký hoặc kênh phân phối đáng tin cậy theo giao thức.

Nếu đầu vào là chứng thư X.509, nên dùng **CertificateFactory**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.PublicKey;

public class CertificatePublicKeyReader {
    public static PublicKey readPublicKey(Path certificatePath)
            throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");

        try (InputStream input = Files.newInputStream(certificatePath)) {
            Certificate certificate = factory.generateCertificate(input);
            return certificate.getPublicKey();
        }
    }
}
~~~

CertificateFactory phân tích cấu trúc chứng thư. Việc kiểm tra chuỗi chứng thư, thời hạn, mục đích sử dụng và trust anchor là công việc xác minh chứng thư riêng; chỉ gọi getPublicKey không xác nhận chứng thư đáng tin cậy.

## 4. Tạo PrivateKey từ PKCS#8

Với tệp PEM có nhãn **BEGIN PRIVATE KEY**, phần Base64 thường biểu diễn PKCS#8 PrivateKeyInfo không mã hóa. Có thể chuyển nó thành PrivateKey như sau:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Base64;

public class PrivateKeyLoader {
    public static PrivateKey loadRsaPrivateKey(Path pemPath)
            throws Exception {
        String pem = Files.readString(
                pemPath, StandardCharsets.US_ASCII);

        String base64 = pem.lines()
                .filter(line -> !line.startsWith("-----BEGIN ")
                        && !line.startsWith("-----END "))
                .collect(java.util.stream.Collectors.joining());

        byte[] der = Base64.getDecoder().decode(base64);
        PKCS8EncodedKeySpec keySpec = new PKCS8EncodedKeySpec(der);
        KeyFactory keyFactory = KeyFactory.getInstance("RSA");
        return keyFactory.generatePrivate(keySpec);
    }
}
~~~

Đây là ví dụ minh họa thao tác đọc khóa riêng chưa mã hóa. Các ví dụ dùng Files.readString và String.lines nên yêu cầu JDK 11 trở lên; với JDK cũ hơn, có thể đọc bằng Files.readAllBytes hoặc BufferedReader và xử lý từng dòng tương ứng. Tệp khóa riêng cần được bảo vệ bằng quyền hệ thống tệp, mã hóa khi lưu và kênh cấp phát bí mật phù hợp. Không đưa nội dung PEM, byte DER, số mũ bí mật hoặc đối tượng khóa vào log. Nếu không cần xuất khóa khỏi HSM/KMS, nên dùng handle khóa do provider cung cấp thay vì nạp key material vào heap của ứng dụng.

### Khóa riêng PKCS#8 được mã hóa

PEM có nhãn **BEGIN ENCRYPTED PRIVATE KEY** chứa cấu trúc EncryptedPrivateKeyInfo. KeyFactory không tự hỏi mật khẩu và không giải mã cấu trúc này. Ứng dụng phải thực hiện bước giải mã theo thuật toán bảo vệ PKCS#8 trước, sau đó mới đưa PrivateKeyInfo đã giải mã vào PKCS8EncodedKeySpec.

Quá trình giải mã cần xác định chính xác thuật toán mã hóa, salt, iteration count, IV và các tham số KDF. Dùng thư viện hoặc công cụ được duy trì và hỗ trợ định dạng cụ thể; không tự triển khai thuật toán giải mã PEM. Mật khẩu phải được lấy từ nguồn bí mật được kiểm soát và không ghi ra log. Tránh ghi khóa riêng đã giải mã ra tệp tạm không được bảo vệ.

## 5. Tạo khóa từ các thành phần toán học

KeyFactory cũng có thể tạo khóa từ KeySpec chứa các thành phần toán học. Ví dụ với RSA, khóa công khai được mô tả bằng modulus (n) và public exponent (e):

~~~java
import java.math.BigInteger;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.RSAPublicKeySpec;

BigInteger modulus = new BigInteger(modulusHex, 16);
BigInteger publicExponent = new BigInteger(exponentHex, 16);

KeyFactory factory = KeyFactory.getInstance("RSA");
RSAPublicKeySpec spec =
        new RSAPublicKeySpec(modulus, publicExponent);
PublicKey publicKey = factory.generatePublic(spec);
~~~

Ví dụ chỉ minh họa việc tạo đối tượng từ các thành phần đã có. Dữ liệu khóa phải đến từ nguồn đáng tin cậy và được kiểm tra theo chính sách thuật toán của ứng dụng. Không tự ghép modulus và exponent tùy ý hoặc chấp nhận khóa RSA có kích thước quá nhỏ.

Với EC, KeySpec cần có tham số đường cong phù hợp cùng điểm công khai hoặc giá trị riêng. Việc chọn đường cong, kiểm tra điểm và tham số phải tuân theo chuẩn và chính sách của provider. Không nên tự xây dựng các tham số đường cong tùy ý trong ứng dụng nếu không có yêu cầu và đánh giá chuyên môn.

## 6. Lấy KeySpec từ đối tượng Key

Chiều chuyển đổi ngược dùng **getKeySpec**. Nếu đối tượng khóa có thể xuất và provider hỗ trợ loại KeySpec yêu cầu, ứng dụng có thể lấy biểu diễn tương ứng:

~~~java
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.RSAPublicKeySpec;

KeyFactory factory = KeyFactory.getInstance("RSA");
RSAPublicKeySpec spec =
        factory.getKeySpec(publicKey, RSAPublicKeySpec.class);

System.out.println("Modulus bits: "
        + spec.getModulus().bitLength());
System.out.println("Public exponent: "
        + spec.getPublicExponent());
~~~

Ví dụ chỉ in thông tin công khai để minh họa việc kiểm tra cấu trúc. Với khóa riêng, không in các thành phần bí mật như private exponent hoặc CRT values.

Các phương thức phổ biến của KeyFactory:

| Phương thức | Chức năng |
|---|---|
| generatePublic(KeySpec) | Tạo PublicKey từ KeySpec công khai. |
| generatePrivate(KeySpec) | Tạo PrivateKey từ KeySpec khóa riêng. |
| getKeySpec(Key, Class) | Lấy KeySpec có kiểu được yêu cầu từ đối tượng Key. |
| translateKey(Key) | Chuyển một đối tượng Key sang dạng khóa mà provider của KeyFactory có thể sử dụng. |

Không phải mọi đối tượng Key đều có thể xuất thành KeySpec. Khóa nằm trong HSM, smart card hoặc provider có chính sách không cho xuất có thể chỉ cung cấp một handle không chứa key material. Trong trường hợp đó, getEncoded có thể trả về null và getKeySpec có thể thất bại. Đây là đặc tính bảo vệ có chủ đích, không phải lỗi cần khắc phục bằng cách trích xuất bí mật.

## 7. Chuyển đổi khóa giữa các Provider

JCA cho phép nhiều provider cùng cung cấp triển khai cho một thuật toán. Đối tượng khóa được tạo bởi provider A có thể không được provider B chấp nhận trực tiếp. **translateKey** cho phép KeyFactory thử chuyển đổi đối tượng khóa sang dạng mà provider đích hỗ trợ:

~~~java
KeyFactory targetFactory = KeyFactory.getInstance("RSA");
Key translatedKey = targetFactory.translateKey(sourceKey);
~~~

Khả năng chuyển đổi phụ thuộc vào loại khóa, provider và khả năng xuất/nhập. Nếu khóa không thể xuất hoặc provider đích không hỗ trợ định dạng tương ứng, thao tác có thể thất bại. Không nên giả định translateKey luôn tạo bản sao tương đương hoặc giữ nguyên mọi thuộc tính bảo vệ của khóa phần cứng.

Khi tích hợp HSM, provider có thể trả về đối tượng khóa đại diện cho một khóa nằm trong thiết bị. Các thao tác ký hoặc giải mã có thể được thực hiện bên trong HSM mà không xuất private key. Nếu chuyển đổi sang provider khác làm mất ranh giới này hoặc buộc xuất key material, không thực hiện nếu chưa được chính sách bảo mật cho phép.

## 8. Phân biệt KeyFactory với các API liên quan

Các API JCA có tên gần nhau nhưng giải quyết những nhiệm vụ khác nhau:

| API | Nhiệm vụ chính | Ví dụ |
|---|---|---|
| KeyPairGenerator | Sinh cặp khóa công khai và khóa riêng mới. | Tạo cặp RSA hoặc EC. |
| KeyFactory | Tạo đối tượng PublicKey/PrivateKey từ KeySpec, hoặc chuyển đổi khóa. | Nạp RSA public key từ X509EncodedKeySpec. |
| SecretKeyFactory | Chuyển đổi KeySpec thành SecretKey hoặc ngược lại cho một số thuật toán bí mật. | Tạo SecretKey từ PBEKeySpec theo thuật toán được hỗ trợ. |
| KeyGenerator | Sinh khóa bí mật đối xứng mới. | Tạo khóa AES. |
| KeyStore | Lưu, tra cứu và quản lý khóa/chứng thư theo alias. | Nạp PrivateKeyEntry từ PKCS12. |
| CertificateFactory | Phân tích chứng thư và CRL. | Đọc X.509 certificate từ PEM/DER. |
| Cipher / Signature | Thực hiện mã hóa/giải mã hoặc ký/xác minh. | AES-GCM, RSA-OAEP, SHA256withRSA. |

Một quy trình thực tế có thể kết hợp nhiều API: CertificateFactory đọc chứng thư, ứng dụng xác minh chuỗi tin cậy, getPublicKey lấy khóa công khai, KeyFactory chuyển đổi nếu cần, rồi Signature kiểm tra chữ ký. Với khóa riêng được lưu trong KeyStore, ứng dụng có thể lấy đối tượng PrivateKey từ alias và dùng Signature mà không cần trích xuất khóa thành KeySpec.

## 9. Các thuật toán và khả năng tương thích

KeyFactory được lấy theo tên thuật toán mà provider đăng ký. Các thuật toán phổ biến gồm:

- **RSA**: khóa công khai và riêng RSA; thường dùng với chữ ký số và mã hóa khóa phiên.
- **EC**: khóa elliptic curve; thường dùng trong ECDSA và ECDH.
- **DSA**: thuật toán chữ ký số cũ, chỉ sử dụng khi yêu cầu tương thích và chính sách còn cho phép.
- **Ed25519**: chữ ký số Edwards curve trên các JDK/provider có hỗ trợ.

Tên thuật toán, KeySpec và định dạng mã hóa phải tương thích. Ví dụ, KeyFactory RSA không thể được yêu cầu tạo một khóa EC từ X509EncodedKeySpec. Provider cũng có thể từ chối khóa có độ dài hoặc tham số không được hỗ trợ.

Trước khi triển khai, cần kiểm tra:

1. Phiên bản JDK và provider có hỗ trợ thuật toán cần dùng không.
2. Định dạng đầu vào là X.509, PKCS#8 hay một định dạng riêng khác.
3. Độ dài khóa, đường cong và tham số có đáp ứng chính sách an toàn không.
4. Ứng dụng có cần xuất khóa hay chỉ cần sử dụng khóa qua provider.
5. Các môi trường phát triển, kiểm thử và sản xuất có cùng khả năng tương thích không.

## 10. Rủi ro và biện pháp bảo vệ

**Nhầm định dạng khóa.** PKCS#1, PKCS#8 và SubjectPublicKeyInfo là các cấu trúc khác nhau. Phải xác định đúng nhãn PEM và loại KeySpec trước khi parse. Không xử lý bằng cách xóa nhãn rồi mặc định mọi byte đều có cùng cấu trúc.

**Tin khóa công khai mà chưa xác minh.** Tạo được PublicKey chỉ chứng minh dữ liệu có thể được parse theo thuật toán. Cần xác minh khóa gắn với danh tính đúng qua chứng thư, chữ ký hoặc kênh phân phối đã xác thực.

**Để lộ khóa riêng khi xuất.** getEncoded hoặc getKeySpec có thể tạo bản sao dữ liệu khóa trong bộ nhớ. Hạn chế thao tác xuất, không ghi ra log, không gửi qua kênh không an toàn và xóa các buffer có thể kiểm soát sau khi dùng. Ưu tiên khóa không thể xuất trong HSM khi yêu cầu bảo vệ cao.

**Dùng khóa yếu hoặc sai tham số.** Kiểm tra độ dài RSA, đường cong EC, thuật toán và chính sách provider. Không tự tạo tham số mật mã tùy ý từ dữ liệu không đáng tin.

**Coi KeyFactory là nơi lưu khóa.** KeyFactory chỉ chuyển đổi biểu diễn. Việc lưu trữ, phân quyền, sao lưu, xoay vòng và hủy phải do KeyStore, KMS/HSM hoặc hệ thống quản lý khóa đảm nhiệm.

**Nhầm khóa riêng được mã hóa với PKCS8EncodedKeySpec.** PKCS8EncodedKeySpec nhận PrivateKeyInfo đã giải mã. Với EncryptedPrivateKeyInfo, cần giải mã trước bằng quy trình được hỗ trợ.

**Ép chuyển khóa HSM sang khóa có thể xuất.** translateKey không bảo đảm duy trì tính không thể xuất. Phải xác minh provider đích và chính sách thiết bị trước khi chuyển đổi.

## 11. KeyFactory trong vòng đời quản lý khóa

KeyFactory tham gia vào các bước tiếp nhận và sử dụng biểu diễn khóa, nhưng không sở hữu toàn bộ vòng đời:

| Giai đoạn | Vai trò của KeyFactory | Kiểm soát quản lý khóa |
|---|---|---|
| Tạo | Có thể dựng đối tượng từ KeySpec; việc sinh cặp khóa thuộc KeyPairGenerator hoặc KMS/HSM. | Sinh khóa bằng nguồn ngẫu nhiên và thuật toán được phê duyệt. |
| Cấp phát | Chuyển đổi khóa nhận từ chứng thư, PEM hoặc hệ thống khác. | Xác minh nguồn, danh tính, mục đích và quyền nhận khóa. |
| Lưu trữ | Không phải kho lưu trữ; có thể tạo đối tượng trước khi đưa vào KeyStore nếu cần. | Bảo vệ key material, phân quyền và quản lý bản sao. |
| Sử dụng | Cung cấp đối tượng khóa cho Signature, Cipher hoặc API liên quan. | Giới hạn quyền sử dụng và ưu tiên thao tác trong HSM/KMS khi phù hợp. |
| Xoay vòng | Parse hoặc chuyển đổi khóa mới khi triển khai. | Gắn phiên bản, chuyển tải sử dụng và duy trì khả năng tương thích cần thiết. |
| Thu hồi | Không tự thu hồi khóa hay chứng thư. | Ngừng sử dụng, cập nhật truststore/đối tác và xử lý chứng thư theo quy trình. |
| Hủy | Không tự xóa key material khỏi mọi bản sao. | Hủy trong KMS/HSM, xử lý bản sao, cache, tệp tạm và backup theo chính sách. |

Một ứng dụng nên lưu metadata về thuật toán, phiên bản khóa, nguồn gốc và mục đích sử dụng cùng đối tượng tham chiếu khóa. Không lưu khóa riêng trong metadata hoặc log. Khi định dạng khóa thay đổi, cần có quy trình chuyển đổi và kiểm thử để bảo đảm các ứng dụng phụ thuộc vẫn đọc được khóa hợp lệ.

## 12. Checklist khi sử dụng KeyFactory

- [ ] Đã xác định đúng thuật toán và provider cần sử dụng.
- [ ] Đã xác định chính xác định dạng đầu vào: X.509, PKCS#8, PKCS#1 hay định dạng khác.
- [ ] Đã chọn đúng KeySpec cho loại khóa và định dạng tương ứng.
- [ ] Đã kiểm tra nguồn gốc và danh tính gắn với khóa công khai.
- [ ] Khóa riêng được bảo vệ và không xuất nếu không cần thiết.
- [ ] Không ghi key material hoặc dữ liệu PEM nhạy cảm vào log.
- [ ] Đã kiểm tra độ dài khóa, tham số và khả năng tương thích của JDK/provider.
- [ ] Không giả định getEncoded/getKeySpec luôn hoạt động với khóa HSM.
- [ ] Đã phân biệt KeyFactory với KeyPairGenerator, SecretKeyFactory, KeyStore và CertificateFactory.
- [ ] Có quy trình cấp phát, xoay vòng, thu hồi và hủy khóa ở cấp hệ thống.

KeyFactory là cầu nối giữa biểu diễn khóa và đối tượng khóa mà các API JCA sử dụng. Nó giúp Java nạp, trích xuất hoặc chuyển đổi khóa theo chuẩn và theo khả năng của provider. Khi chọn đúng KeySpec, xác minh nguồn khóa và giữ nguyên ranh giới bảo vệ của HSM/KMS, ứng dụng có thể tích hợp khóa từ nhiều hệ thống mà vẫn duy trì kiểm soát trong toàn bộ vòng đời quản lý khóa.
