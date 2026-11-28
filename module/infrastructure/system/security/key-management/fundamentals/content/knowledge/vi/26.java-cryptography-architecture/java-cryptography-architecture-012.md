# KeyPairGenerator

Trong Java Cryptography Architecture (JCA), **KeyPairGenerator** là API dùng để sinh một cặp khóa bất đối xứng gồm khóa công khai (public key) và khóa riêng (private key). Hai khóa có quan hệ toán học với nhau nhưng đảm nhiệm vai trò khác nhau: khóa riêng phải được giữ bí mật, còn khóa công khai có thể phân phối cho các bên cần xác minh chữ ký hoặc thiết lập khóa chung.

Lớp **java.security.KeyPairGenerator** cung cấp giao diện thống nhất để ứng dụng yêu cầu sinh khóa cho các thuật toán như RSA, EC, Ed25519 hoặc X25519 khi provider hỗ trợ. Ứng dụng chọn thuật toán và tham số phù hợp, cung cấp nguồn ngẫu nhiên mật mã, rồi nhận về đối tượng **KeyPair**. Provider thực hiện phần sinh khóa thực tế.

Trong quản lý khóa, việc sinh được một cặp khóa mới chỉ là bước đầu. Hệ thống còn phải bảo vệ khóa riêng, phân phối khóa công khai có xác thực, gắn khóa với danh tính hoặc mục đích sử dụng, sao lưu khi phù hợp, xoay vòng và thu hồi khi khóa không còn an toàn.

## 1. Cặp khóa bất đối xứng là gì?

Một cặp khóa bất đối xứng gồm hai thành phần liên kết về mặt toán học:

- **Public key:** khóa công khai, có thể phân phối cho đối tác hoặc công bố trong chứng chỉ số.
- **Private key:** khóa riêng, chỉ chủ thể được cấp quyền mới được phép sử dụng. Việc lộ khóa riêng có thể làm mất khả năng bảo đảm danh tính hoặc bí mật mà hệ thống dựa vào khóa đó.

Tác vụ được phép thực hiện phụ thuộc thuật toán và mục đích của cặp khóa:

- Với **chữ ký số**, chủ thể dùng khóa riêng để ký; bên xác minh dùng khóa công khai tương ứng để kiểm tra chữ ký.
- Với **mã hóa khóa công khai kiểu RSA**, bên gửi có thể mã hóa bằng khóa công khai và bên nhận giải mã bằng khóa riêng, nếu dùng đúng scheme và padding an toàn.
- Với **trao đổi khóa hoặc thỏa thuận khóa**, các bên dùng cặp khóa phù hợp để tạo bí mật chung. Khóa công khai phải được xác thực để ngăn tấn công trung gian.
- Với **mật mã đường cong elliptic**, cùng họ đường cong có thể hỗ trợ các thuật toán khác nhau. Chẳng hạn Ed25519 dùng cho chữ ký, còn X25519 dùng cho thỏa thuận khóa; không thể thay thế vai trò của chúng cho nhau.

Không phải mọi cặp khóa đều dùng được cho mọi tác vụ. Khóa được tạo cho Ed25519 không phải khóa mã hóa RSA; khóa X25519 không phải khóa ký Ed25519. Ứng dụng cần gắn thuật toán, mục đích và chính sách sử dụng với từng khóa.

## 2. KeyPairGenerator trong kiến trúc JCA

JCA tách giao diện ứng dụng khỏi phần triển khai thuật toán. Với sinh cặp khóa, các thành phần chính gồm:

- **java.security.KeyPairGenerator:** engine class mà ứng dụng gọi để chọn thuật toán, khởi tạo tham số và sinh cặp khóa.
- **java.security.KeyPairGeneratorSpi:** lớp SPI (Service Provider Interface) mà nhà cung cấp mật mã kế thừa để triển khai chức năng sinh khóa.
- **java.security.Provider:** đăng ký dịch vụ KeyPairGenerator cùng tên thuật toán và lớp triển khai tương ứng.
- **java.security.KeyPair:** đối tượng chứa khóa công khai và khóa riêng được sinh ra.
- **PublicKey và PrivateKey:** các giao diện biểu diễn hai thành phần của cặp khóa.

Luồng xử lý cơ bản:

1. Ứng dụng gọi **KeyPairGenerator.getInstance("RSA")** hoặc tên thuật toán khác.
2. JCA tìm provider có đăng ký dịch vụ KeyPairGenerator cho thuật toán được yêu cầu.
3. Ứng dụng khởi tạo bộ sinh bằng kích thước khóa hoặc bộ tham số thuật toán.
4. Ứng dụng gọi **generateKeyPair()**.
5. Provider sinh khóa và trả về một đối tượng KeyPair.

Có thể chỉ định provider bằng overload của **getInstance** khi cần một triển khai cụ thể, ví dụ provider kết nối HSM. Nếu không có yêu cầu ràng buộc, để JCA lựa chọn theo cấu hình provider của môi trường giúp ứng dụng linh hoạt hơn. Dù chọn cách nào, cần kiểm tra provider thực tế trên môi trường triển khai vì khả năng hỗ trợ thuật toán và tham số có thể khác nhau.

## 3. Chọn thuật toán và tham số sinh khóa

Tên thuật toán truyền cho **getInstance** xác định họ khóa cần sinh. Tham số khởi tạo tiếp tục xác định kích thước hoặc bộ tham số toán học cụ thể.

| Thuật toán | Mục đích điển hình | Cách cấu hình thường dùng |
|---|---|---|
| **RSA** | Chữ ký số hoặc mã hóa khóa công khai theo scheme phù hợp | Kích thước modulus, ví dụ 2048 hoặc 3072 bit theo chính sách |
| **EC** | Chữ ký ECDSA hoặc thỏa thuận khóa ECDH | Tên đường cong, ví dụ secp256r1 |
| **Ed25519** | Chữ ký số EdDSA | Tham số cố định theo thuật toán; thường không cần chỉ định kích thước |
| **X25519** | Thỏa thuận khóa | Tham số cố định theo thuật toán; dùng với KeyAgreement |

Bảng trên mô tả các lựa chọn thường gặp, không phải cam kết mọi provider đều hỗ trợ tất cả thuật toán. Hãy kiểm tra phiên bản JDK, provider, chính sách mật mã và yêu cầu tương thích của hệ thống.

### 3.1. RSA

RSA sử dụng một cặp khóa dựa trên bài toán phân tích thừa số số nguyên. Kích thước khóa thường được biểu diễn bằng số bit của modulus. Ứng dụng cần chọn kích thước theo chính sách an toàn và thời gian bảo vệ dữ liệu. Kích thước 2048 bit vẫn được nhiều hệ thống hỗ trợ; 3072 bit có thể được chọn khi cần biên an toàn dài hơn hoặc theo yêu cầu tổ chức.

Không dùng RSA thô. Khi ký, dùng scheme chữ ký phù hợp như RSASSA-PSS nếu giao thức hỗ trợ. Khi mã hóa hoặc bọc khóa, dùng RSA-OAEP với tham số hash và MGF được thống nhất; RSA thường phù hợp để bảo vệ một lượng dữ liệu nhỏ như khóa phiên, còn dữ liệu lớn nên dùng mã hóa lai với thuật toán đối xứng. KeyPairGenerator chỉ sinh cặp khóa; nó không tự quyết định scheme ký hoặc mã hóa mà ứng dụng sẽ sử dụng.

### 3.2. Elliptic Curve (EC)

Với thuật toán **EC**, ứng dụng thường chọn đường cong bằng **ECGenParameterSpec** thay vì truyền một số nguyên biểu thị kích thước. Ví dụ secp256r1 là một đường cong được dùng phổ biến. Hai phía tham gia ECDH phải dùng tham số tương thích và xác thực khóa công khai của nhau.

Đường cong và thuật toán sử dụng khóa cần được chọn theo giao thức. Không tự tạo tham số đường cong tùy ý nếu không có chuyên môn và quy trình đánh giá phù hợp.

### 3.3. Ed25519 và X25519

Ed25519 là thuật toán chữ ký số thuộc họ Edwards-curve Digital Signature Algorithm. X25519 là cơ chế thỏa thuận khóa dựa trên Curve25519. Chúng có tên, mục đích và API sử dụng khác nhau dù cùng thuộc họ thuật toán đường cong elliptic hiện đại.

Với các thuật toán có tham số cố định như Ed25519 và X25519, provider thường biết bộ tham số từ tên thuật toán. Ứng dụng không nên cố áp dụng cách cấu hình kích thước RSA hoặc đường cong EC cho các thuật toán này.

## 4. SecureRandom và chất lượng ngẫu nhiên

Sinh khóa phụ thuộc vào số ngẫu nhiên mật mã. Nếu nguồn ngẫu nhiên có thể dự đoán, khóa có thể bị suy ra hoặc không đạt độ an toàn mong muốn dù thuật toán được chọn đúng.

Java cung cấp **java.security.SecureRandom** để tạo dữ liệu ngẫu nhiên dùng trong các thao tác mật mã. Có thể truyền SecureRandom vào phương thức khởi tạo của KeyPairGenerator để chỉ rõ nguồn ngẫu nhiên cho quá trình sinh khóa.

Các nguyên tắc quan trọng:

- Dùng SecureRandom do JDK/provider tin cậy cung cấp hoặc nguồn ngẫu nhiên đã được môi trường bảo mật phê duyệt.
- Không dùng java.util.Random, timestamp, bộ đếm, UUID tự ghép hoặc dữ liệu dễ đoán làm nguồn sinh khóa.
- Không tự viết thuật toán sinh số ngẫu nhiên.
- Tránh tự gieo (seed) SecureRandom bằng dữ liệu ít entropy hoặc seed cố định.
- Trong môi trường HSM, để thiết bị và provider thực hiện việc sinh khóa trong vùng bảo vệ khi kiến trúc hỗ trợ.

Khi gọi overload **initialize(int, SecureRandom)** hoặc **initialize(AlgorithmParameterSpec, SecureRandom)**, ứng dụng đưa nguồn ngẫu nhiên vào bộ sinh. Nếu không truyền SecureRandom, provider sẽ dùng cơ chế mặc định của nó; điều này có thể hợp lệ nhưng cần hiểu cấu hình và chính sách của môi trường.

## 5. Các phương thức quan trọng

| Phương thức | Vai trò |
|---|---|
| **getInstance(algorithm)** | Lấy bộ sinh khóa cho thuật toán chỉ định |
| **getInstance(algorithm, provider)** | Lấy bộ sinh từ provider cụ thể |
| **initialize(keysize)** | Khởi tạo bằng kích thước khóa |
| **initialize(keysize, random)** | Khởi tạo kích thước khóa và nguồn ngẫu nhiên |
| **initialize(params)** | Khởi tạo bằng bộ tham số thuật toán |
| **initialize(params, random)** | Khởi tạo tham số và nguồn ngẫu nhiên |
| **generateKeyPair()** | Sinh và trả về một cặp khóa mới |
| **genKeyPair()** | Phương thức tiện ích tương đương generateKeyPair |
| **getAlgorithm()** | Trả về tên thuật toán |
| **getProvider()** | Trả về provider đang cung cấp triển khai |

Không phải mọi thuật toán đều hỗ trợ mọi kiểu initialize. Ví dụ, RSA thường nhận kích thước khóa dạng số nguyên, trong khi EC thường dùng **ECGenParameterSpec**. Nếu provider không hỗ trợ thuật toán hoặc tham số, ứng dụng có thể nhận **NoSuchAlgorithmException** hoặc **InvalidAlgorithmParameterException**.

Nếu không gọi initialize, provider có thể dùng giá trị mặc định riêng. Không nên phụ thuộc vào mặc định đó trong hệ thống yêu cầu cấu hình rõ ràng, trừ khi thuật toán có tham số cố định và provider quy định cách khởi tạo mặc định phù hợp.

## 6. Sinh cặp khóa RSA bằng Java

Ví dụ sau sinh cặp khóa RSA 3072 bit bằng SecureRandom. Kích thước thực tế phải tuân theo chính sách của hệ thống và yêu cầu tương thích với bên sử dụng khóa.

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;

public final class RsaKeyPairFactory {
    private RsaKeyPairFactory() {
    }

    public static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072, new SecureRandom());
        return generator.generateKeyPair();
    }
}
~~~

Quy trình gồm ba bước:

1. **getInstance("RSA")** yêu cầu JCA tìm provider hỗ trợ sinh khóa RSA.
2. **initialize(3072, new SecureRandom())** cấu hình kích thước modulus và nguồn ngẫu nhiên.
3. **generateKeyPair()** tạo cặp khóa mới.

Đối tượng trả về có thể được truy cập qua **getPublic()** và **getPrivate()**. Không nên in nội dung khóa ra console hoặc log để kiểm tra. Trong môi trường sản xuất, cần chuyển khóa riêng vào vùng lưu trữ được bảo vệ và phân phối khóa công khai qua một kênh có xác thực.

## 7. Sinh cặp khóa EC bằng đường cong chỉ định

Với EC, nên chỉ rõ đường cong được giao thức hỗ trợ bằng **ECGenParameterSpec**.

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;

public final class EcKeyPairFactory {
    private EcKeyPairFactory() {
    }

    public static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");

        ECGenParameterSpec parameters =
            new ECGenParameterSpec("secp256r1");

        generator.initialize(parameters, new SecureRandom());
        return generator.generateKeyPair();
    }
}
~~~

Trong ví dụ, **ECGenParameterSpec** xác định tên đường cong. Provider phải hỗ trợ đường cong này. Nếu cần ECDSA, khóa được chuyển cho **Signature** với thuật toán chữ ký tương ứng; nếu cần ECDH, khóa được chuyển cho **KeyAgreement**. KeyPairGenerator không thực hiện ký hoặc thỏa thuận khóa.

## 8. Sinh khóa Ed25519

Ed25519 sử dụng bộ tham số cố định, vì vậy ví dụ thông thường không cần gọi initialize với kích thước khóa.

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;

public final class Ed25519KeyPairFactory {
    private Ed25519KeyPairFactory() {
    }

    public static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("Ed25519");

        return generator.generateKeyPair();
    }
}
~~~

Ed25519 được dùng với **Signature**, chẳng hạn chữ ký và xác minh bằng thuật toán Ed25519. Không dùng cặp khóa Ed25519 cho KeyAgreement hoặc mã hóa dữ liệu. Nếu ứng dụng cần thỏa thuận khóa trên Curve25519, hãy chọn X25519 và API KeyAgreement tương ứng.

Ví dụ sinh cặp khóa X25519:

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;

public final class X25519KeyPairFactory {
    private X25519KeyPairFactory() {
    }

    public static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("X25519");

        return generator.generateKeyPair();
    }
}
~~~

X25519 sinh khóa dùng cho thỏa thuận khóa. Sau khi có cặp khóa, ứng dụng dùng **KeyAgreement.getInstance("X25519")** để tính bí mật chung với public key đã được xác thực của bên kia. Bí mật chung thường được đưa qua KDF để tạo khóa phiên; không dùng trực tiếp như khóa mã hóa nếu giao thức yêu cầu dẫn xuất khóa.

## 9. Sử dụng KeyPair sau khi sinh

KeyPair chỉ đóng gói hai đối tượng khóa. Việc sử dụng khóa phụ thuộc mục đích và thuật toán.

~~~java
import java.security.KeyPair;
import java.security.PrivateKey;
import java.security.PublicKey;

public final class KeyPairAccess {
    private KeyPairAccess() {
    }

    public static void inspect(KeyPair pair) {
        PublicKey publicKey = pair.getPublic();
        PrivateKey privateKey = pair.getPrivate();

        String publicAlgorithm = publicKey.getAlgorithm();
        String privateAlgorithm = privateKey.getAlgorithm();

        System.out.println("Public algorithm: " + publicAlgorithm);
        System.out.println("Private algorithm: " + privateAlgorithm);
    }
}
~~~

Đoạn mã chỉ đọc tên thuật toán để minh họa việc truy cập hai thành phần. Trong hệ thống thật, tránh đưa thông tin nhạy cảm hoặc biểu diễn khóa riêng vào log. Có thể kiểm tra thuật toán và định dạng khóa để phát hiện cấu hình sai, nhưng không nên coi tên thuật toán là bằng chứng khóa đã được xác thực hoặc được cấp đúng danh tính.

Các API thường dùng tiếp theo:

- **Signature:** ký bằng PrivateKey và xác minh bằng PublicKey.
- **KeyAgreement:** tạo bí mật chung từ khóa riêng của một bên và khóa công khai của bên kia.
- **Cipher:** thực hiện thao tác mã hóa/giải mã phù hợp với thuật toán và scheme.
- **KeyFactory:** chuyển đổi giữa biểu diễn khóa chuẩn hóa và đối tượng PublicKey/PrivateKey khi khóa có thể xuất và provider hỗ trợ.

Không dùng KeyFactory để sinh một cặp khóa mới; nhiệm vụ đó thuộc KeyPairGenerator. Cũng không dùng KeyPairGenerator thay cho KeyGenerator, vì KeyGenerator sinh khóa bí mật đối xứng.

## 10. Lưu trữ và phân phối khóa

Sau khi sinh, khóa riêng cần được bảo vệ theo giá trị và mục đích sử dụng. Có một số mô hình phổ biến:

- **KeyStore:** lưu trữ khóa và chứng chỉ. Khi đã có chứng chỉ phù hợp, khóa riêng có thể được lưu trong **PrivateKeyEntry** cùng chuỗi chứng chỉ.
- **HSM hoặc token PKCS#11:** sinh và giữ khóa riêng trong phần cứng, có thể hạn chế hoặc cấm xuất khóa.
- **KMS:** quản lý quyền sử dụng, phiên bản, audit và vòng đời khóa. Cách biểu diễn cặp khóa phụ thuộc dịch vụ và provider tích hợp.
- **Kho bí mật của nền tảng:** chỉ phù hợp khi cơ chế đó có kiểm soát truy cập, mã hóa, sao lưu và kiểm toán đáp ứng yêu cầu của khóa.

Với KeyStore, một cặp khóa vừa sinh chưa tự có chuỗi chứng chỉ. Ứng dụng thường cần tạo yêu cầu ký chứng chỉ (CSR), gửi đến CA hoặc quy trình cấp chứng chỉ nội bộ, nhận chứng chỉ đã ký rồi lưu khóa riêng cùng chuỗi chứng chỉ trong PrivateKeyEntry.

Khóa công khai cần được phân phối có xác thực. Có thể dùng chứng chỉ X.509, cơ chế pinning hoặc một kênh trao đổi khóa đã được xác thực. Nếu kẻ tấn công thay khóa công khai bằng khóa của họ, các bên có thể xác minh chữ ký hoặc thiết lập khóa với nhầm chủ thể.

## 11. Khả năng xuất khóa và khóa trong HSM

Nhiều đối tượng khóa Java triển khai **Key** và có thể cung cấp các phương thức như **getAlgorithm()**, **getFormat()** và **getEncoded()**. Tuy nhiên, không nên giả định mọi khóa đều có thể xuất ra byte.

Với khóa phần mềm có thể xuất, khóa công khai thường có định dạng X.509 SubjectPublicKeyInfo; khóa riêng thường dùng PKCS#8. Với khóa được giữ trong HSM, **getEncoded()** có thể trả về null hoặc provider có thể chỉ cung cấp một đối tượng tham chiếu tới khóa bên trong thiết bị.

Khi khóa không thể xuất:

- Ứng dụng vẫn có thể truyền đối tượng PrivateKey cho Signature hoặc API mật mã tương thích.
- Provider thực hiện thao tác bên trong HSM và chỉ trả về kết quả như chữ ký.
- Việc sao lưu, phục hồi và hủy khóa phải tuân theo khả năng của thiết bị và chính sách vận hành.
- Không cố chuyển khóa thành byte bằng cách gọi getEncoded nhiều lần hoặc dùng cách trích xuất ngoài API được hỗ trợ.

Khả năng không xuất khóa giúp giảm nguy cơ lộ vật liệu khóa, nhưng không tự bảo vệ khỏi việc một tài khoản bị cấp quyền sử dụng khóa trái phép. Cần kiểm soát danh tính, quyền gọi, mục đích sử dụng, giới hạn thao tác và kiểm toán ở cả ứng dụng lẫn HSM/KMS.

## 12. Quản lý vòng đời cặp khóa

Cặp khóa phải được quản lý như một tài sản mật mã có vòng đời rõ ràng:

1. **Tạo:** chọn thuật toán, tham số, provider và nguồn ngẫu nhiên phù hợp. Sinh khóa trong phần mềm hoặc trực tiếp trong HSM theo yêu cầu bảo vệ.
2. **Đăng ký và gắn danh tính:** tạo CSR hoặc quy trình đăng ký tương ứng; xác thực chủ thể trước khi cấp chứng chỉ hay công bố khóa công khai.
3. **Lưu trữ:** giữ khóa riêng trong KeyStore, KMS hoặc HSM; giới hạn quyền sử dụng và bảo vệ bản sao lưu.
4. **Phân phối:** công bố khóa công khai hoặc chứng chỉ qua kênh đáng tin cậy. Gắn định danh khóa để các bên lựa chọn đúng khóa.
5. **Sử dụng:** chỉ dùng khóa cho mục đích được phê duyệt. Tách khóa ký, khóa thỏa thuận và khóa mã hóa theo chính sách.
6. **Xoay vòng:** sinh cặp khóa mới, cấp chứng chỉ hoặc cập nhật khóa công khai, chuyển các bên phụ thuộc sang phiên bản mới. Duy trì khóa cũ trong thời gian cần xác minh chữ ký hoặc xử lý dữ liệu cũ theo chính sách.
7. **Thu hồi:** thu hồi chứng chỉ hoặc vô hiệu hóa quyền sử dụng khi khóa riêng bị lộ, chủ thể thay đổi hoặc khóa không còn đáng tin cậy. Cập nhật các bên phụ thuộc và cơ chế kiểm tra trạng thái.
8. **Hủy:** loại bỏ khóa khỏi kho hoạt động, bản sao lưu, thiết bị và các nơi lưu trữ liên quan theo quy trình hủy. Cân nhắc tác động tới dữ liệu cần giải mã hoặc chữ ký cần xác minh trước khi hủy.

Không phải lúc nào cũng có thể hủy ngay khóa cũ sau khi tạo khóa mới. Ví dụ, khóa công khai cũ có thể cần giữ để xác minh chữ ký đã tạo trước thời điểm xoay vòng. Chính sách cần phân biệt việc ngừng ký mới, ngừng xác minh, thu hồi chứng chỉ và hủy vật liệu khóa riêng.

## 13. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Dùng Random hoặc timestamp để sinh khóa | Khóa có thể dự đoán được | Dùng SecureRandom và provider đáng tin cậy |
| Không cấu hình tham số khóa rõ ràng | Kết quả phụ thuộc mặc định provider hoặc không tương thích giữa môi trường | Khởi tạo bằng kích thước hoặc AlgorithmParameterSpec phù hợp |
| Dùng cùng một cặp khóa cho mọi mục đích | Tăng tác động khi lộ khóa và dễ vi phạm yêu cầu giao thức | Tách khóa theo thuật toán, dịch vụ và mục đích |
| Nhầm Ed25519 với X25519 | Gọi sai API hoặc dùng sai mục đích khóa | Ed25519 cho chữ ký; X25519 cho thỏa thuận khóa |
| Phân phối public key không xác thực | Kẻ tấn công có thể thay khóa và mạo danh chủ thể | Dùng chứng chỉ hoặc kênh phân phối đã xác thực |
| Cho rằng getEncoded luôn trả về dữ liệu | Lỗi khi dùng khóa HSM hoặc khóa không thể xuất | Thiết kế để sử dụng đối tượng Key trực tiếp |
| Ghi private key vào log hoặc cấu hình | Lộ vật liệu khóa | Giữ khóa trong vùng lưu trữ được bảo vệ và không log nội dung |
| Dùng RSA mà không chọn scheme an toàn | Có thể tạo lỗ hổng do padding hoặc cách sử dụng sai | Dùng scheme phù hợp như RSA-PSS hoặc RSA-OAEP theo mục đích |
| Hủy khóa cũ quá sớm | Không thể xác minh chữ ký hoặc truy cập dữ liệu cũ | Lập kế hoạch chuyển đổi, lưu giữ và hủy theo vòng đời |

## 14. Nguyên tắc triển khai an toàn

- Chọn thuật toán và tham số theo giao thức, chính sách mật mã và thời gian bảo vệ dữ liệu.
- Dùng SecureRandom và provider được tin cậy; không tự xây dựng bộ sinh khóa.
- Với RSA, chọn kích thước khóa và scheme an toàn; với EC, chỉ định đường cong chuẩn được hỗ trợ.
- Dùng đúng họ khóa cho đúng tác vụ: Ed25519 cho chữ ký, X25519 cho thỏa thuận khóa, RSA hoặc EC theo scheme tương ứng.
- Tạo khóa riêng trong HSM nếu yêu cầu bảo vệ cao và provider hỗ trợ.
- Xác thực public key trước khi sử dụng; không tin một khóa chỉ vì nó được nhận qua mạng.
- Giới hạn quyền sử dụng private key theo danh tính dịch vụ và mục đích; ghi nhận các thao tác quan trọng trong audit log.
- Thiết kế key ID, quy trình cấp chứng chỉ, xoay vòng, thu hồi, sao lưu và hủy trước khi đưa khóa vào vận hành.
- Không xuất hoặc sao chép private key nếu không cần thiết; không ghi nội dung khóa vào log, ticket hoặc mã nguồn.

KeyPairGenerator cung cấp bước sinh cặp khóa trong JCA. Để xây dựng hệ thống an toàn, ứng dụng cần kết hợp bộ sinh với provider phù hợp, nguồn ngẫu nhiên tin cậy, cơ chế lưu trữ và xác thực khóa công khai, cùng chính sách quản lý vòng đời khóa.
