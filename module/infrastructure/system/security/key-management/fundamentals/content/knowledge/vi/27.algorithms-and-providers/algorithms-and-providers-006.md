# Key size và mức độ an toàn của khóa mật mã

**Key size** (kích thước khóa) là độ dài biểu diễn của khóa, thường được đo bằng bit. Đây là một yếu tố quan trọng khi lựa chọn thuật toán mật mã, nhưng không thể dùng riêng con số này để kết luận một khóa an toàn đến đâu. Mức độ an toàn thực tế còn phụ thuộc thuật toán, cấu trúc toán học, cách sinh khóa, tham số, provider, cách sử dụng và thời gian cần bảo vệ dữ liệu.

Trong quản lý khóa, lựa chọn kích thước phù hợp ảnh hưởng trực tiếp đến khả năng chống tấn công, hiệu năng, khả năng tương thích và kế hoạch xoay vòng. Khóa quá ngắn có thể bị phá bằng năng lực tính toán hiện có; khóa quá dài có thể làm tăng chi phí mà không đem lại mức bảo vệ tương xứng nếu thuật toán hoặc cách triển khai là điểm yếu.

## 1. Kích thước khóa và security strength

Kích thước khóa thường mô tả số bit trong khóa hoặc tham số chính của thuật toán. Ví dụ:

- AES-128 sử dụng khóa bí mật dài 128 bit.
- RSA-3072 có modulus dài 3072 bit.
- Đường cong elliptic P-256 sử dụng trường hữu hạn có kích thước 256 bit.

**Security strength** là mức độ khó ước tính để phá một cơ chế mật mã, thường được quy đổi thành số bit an toàn tương đương. Hai thuật toán có khóa dài 256 bit không nhất thiết cung cấp cùng mức an toàn. Tìm kiếm vét cạn khóa AES-128 có không gian khóa lý tưởng \(2^{128}\), trong khi phá RSA không phải là thử mọi chuỗi bit của modulus; nó liên quan đến bài toán phân tích thừa số nguyên.

Vì vậy, cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Key size | Độ dài khóa hoặc tham số khóa được biểu diễn bằng bit. |
| Key space | Số giá trị khóa có thể có; phụ thuộc cách sinh và cấu trúc khóa. |
| Security strength | Mức chống tấn công ước tính của thuật toán với kích thước và tham số cụ thể. |
| Block size | Kích thước khối dữ liệu mà thuật toán khối xử lý; không phải kích thước khóa. |
| Output/tag size | Độ dài đầu ra của hàm băm hoặc thẻ xác thực; không đồng nhất với độ dài khóa. |

Ví dụ AES luôn có block size 128 bit, dù khóa AES có thể dài 128, 192 hoặc 256 bit. Với RSA, con số 3072 bit là độ dài modulus, không phải mức an toàn 3072 bit. Với ECC, P-256 có tham số trường 256 bit nhưng mức an toàn cổ điển ước tính khoảng 128 bit.

## 2. Kích thước khóa tham khảo theo thuật toán

Các con số dưới đây là mốc tham khảo phổ biến cho hệ thống cổ điển. Chính sách tổ chức, tiêu chuẩn áp dụng, thời hạn bảo vệ dữ liệu và yêu cầu tương thích có thể yêu cầu lựa chọn khác. Luôn xác minh phiên bản tiêu chuẩn và cấu hình provider được dùng trong môi trường thực tế.

### Thuật toán đối xứng

| Thuật toán | Kích thước khóa | Mức an toàn và ghi chú |
|---|---:|---|
| AES-128 | 128 bit | Mức an toàn cổ điển xấp xỉ 128 bit; thường đáp ứng tốt nhiều hệ thống hiện đại. |
| AES-192 | 192 bit | Mức an toàn cổ điển xấp xỉ 192 bit; ít phổ biến hơn AES-128 và AES-256. |
| AES-256 | 256 bit | Mức an toàn cổ điển xấp xỉ 256 bit; thường được chọn khi cần biên an toàn lớn hoặc thời hạn bảo vệ dài. |

AES có block size cố định 128 bit. Tăng khóa từ 128 lên 256 bit làm tăng không gian tìm kiếm khóa lý tưởng, nhưng không làm block size tăng lên 256 bit. Khi sử dụng AES-GCM, ngoài kích thước khóa còn phải bảo đảm nonce duy nhất dưới cùng khóa và dùng thẻ xác thực đủ dài.

### Thuật toán bất đối xứng

| Họ thuật toán | Kích thước/tham số | Mức an toàn cổ điển tham khảo |
|---|---:|---:|
| RSA | 2048 bit modulus | Khoảng 112 bit |
| RSA | 3072 bit modulus | Khoảng 128 bit |
| RSA | 7680 bit modulus | Khoảng 192 bit |
| RSA | 15360 bit modulus | Khoảng 256 bit |
| ECC P-256 | Trường 256 bit | Khoảng 128 bit |
| ECC P-384 | Trường 384 bit | Khoảng 192 bit |
| ECC P-521 | Trường 521 bit | Khoảng 256 bit |
| Ed25519 | Bộ tham số cố định, khóa công khai mã hóa 32 byte | Khoảng 128 bit |

Các mức trên là quy đổi ước tính theo các nhóm tham số chuẩn phổ biến, không phải bảo đảm rằng mọi triển khai với cùng con số đều an toàn như nhau. RSA-2048 thường được xem là mức sàn cho nhiều triển khai hiện nay, còn RSA-3072 thường được chọn khi mục tiêu là khoảng 128 bit an toàn cổ điển. ECC có thể đạt mức an toàn tương đương với khóa ngắn hơn RSA, nhưng cần dùng đường cong được chuẩn hóa và provider đã được kiểm chứng.

Không nên tăng kích thước RSA tùy tiện để thay thế việc chọn đúng thuật toán. RSA-4096 không cung cấp mức an toàn gấp đôi RSA-2048, trong khi chi phí tạo khóa, ký, giải mã và bắt tay TLS tăng đáng kể. Nếu cần mức an toàn cao hơn, hãy chọn tham số dựa trên chuẩn và đánh giá hiệu năng.

### HMAC và khóa dùng cho MAC

Với HMAC-SHA-256, kích thước khóa là độ dài bí mật đầu vào cho HMAC, còn 256 bit là độ dài đầu ra băm. Một khóa ngẫu nhiên 256 bit thường là lựa chọn phù hợp cho nhiều mục đích HMAC-SHA-256. Không dùng chuỗi mật khẩu do người dùng chọn làm khóa HMAC trực tiếp; cần sinh khóa ngẫu nhiên hoặc dùng KDF phù hợp nếu đầu vào bắt buộc là mật khẩu.

Khi cắt ngắn thẻ MAC để tiết kiệm dung lượng, độ dài thẻ ảnh hưởng đến khả năng giả mạo và phải tuân theo tiêu chuẩn cùng chính sách của giao thức. Không suy ra độ an toàn của MAC chỉ từ độ dài khóa hoặc độ dài hash.

## 3. Vì sao không thể so sánh các con số trực tiếp?

Mỗi họ thuật toán dựa trên một bài toán toán học khác nhau:

- AES dựa trên việc chống tìm kiếm khóa và các dạng phân tích mật mã đối với mạng thay thế-hoán vị.
- RSA dựa trên độ khó phân tích thừa số của một số nguyên lớn.
- ECC dựa trên độ khó của bài toán logarithm rời rạc trên đường cong elliptic.
- HMAC dựa trên khóa bí mật kết hợp với hàm băm.

Do đó, AES-256 không phải là “mạnh gấp đôi” RSA-2048 chỉ vì con số 256 lớn hơn 2048 theo một cách so sánh đơn giản. Cần so sánh theo security strength ước tính và theo mô hình đe dọa. Bảng quy đổi trong tiêu chuẩn giúp chọn các tham số có mức bảo vệ tương đương.

Ngoài thuật toán, độ an toàn thực tế còn có thể bị giới hạn bởi:

- Khóa được sinh từ nguồn ngẫu nhiên yếu hoặc bị dự đoán.
- Khóa có cấu trúc, entropy thấp hoặc bị tái sử dụng sai mục đích.
- Nonce/IV bị lặp trong chế độ yêu cầu duy nhất.
- Khóa riêng bị xuất, sao chép hoặc lộ qua log và bộ nhớ.
- Provider có lỗi, thuật toán bị cấu hình sai hoặc tham số không phù hợp.
- Giao thức để lộ thông tin qua thông báo lỗi, timing hoặc side channel.

Một khóa dài không thể bù đắp cho những lỗi thiết kế này.

## 4. Chọn kích thước khóa theo yêu cầu hệ thống

Khi chọn key size, cần xác định mục tiêu bảo vệ và giới hạn vận hành:

1. **Mức an toàn cần đạt:** xác định security strength mục tiêu theo chính sách và loại dữ liệu.
2. **Thời gian bảo vệ:** dữ liệu cần giữ bí mật nhiều năm có thể cần biên an toàn lớn hơn dữ liệu ngắn hạn.
3. **Thuật toán và giao thức:** chọn tham số nằm trong khuyến nghị của chuẩn và tương thích với TLS, chữ ký, mã hóa lưu trữ hoặc giao thức liên quan.
4. **Hiệu năng:** đánh giá chi phí tạo khóa, mã hóa, giải mã, ký, xác minh và trao đổi khóa.
5. **Khả năng tương thích:** kiểm tra JDK, provider, HSM, KMS, thư viện và các hệ thống đối tác.
6. **Vòng đời:** tính đến việc xoay vòng, di trú, giải mã dữ liệu cũ và hủy khóa.

Ví dụ định hướng:

| Nhu cầu | Lựa chọn thường gặp | Điều cần xác minh |
|---|---|---|
| Mã hóa dữ liệu ứng dụng | AES-128 hoặc AES-256 với GCM | Chính sách bảo vệ, nonce, tag và năng lực provider. |
| Chữ ký RSA tương thích rộng | RSA-3072 | Hỗ trợ của đối tác, thuật toán chữ ký và thời gian ký/xác minh. |
| Chữ ký hoặc trao đổi khóa EC | P-256 hoặc P-384 | Giao thức, đường cong được hỗ trợ và yêu cầu mức an toàn. |
| Chữ ký hiện đại với Ed25519 | Ed25519 | Phiên bản JDK/provider và khả năng tương thích hệ thống liên quan. |
| Xác thực thông điệp | HMAC-SHA-256 với khóa ngẫu nhiên | Độ dài khóa, độ dài tag và cách phân phối khóa. |

Đây là các điểm xuất phát để đánh giá, không phải cấu hình áp dụng tự động cho mọi hệ thống. Đặc biệt, tiêu chuẩn ngành hoặc yêu cầu chứng nhận có thể quy định bộ thuật toán và kích thước khóa cụ thể.

## 5. Tạo khóa với kích thước chỉ định trong Java

Trong JCA, mỗi loại khóa có API tạo riêng. Kích thước được truyền vào API phải phù hợp với thuật toán và provider.

### Tạo khóa AES

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class AesKeyCreation {
    public static SecretKey generateAes256()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        return generator.generateKey();
    }
}
~~~

Lệnh **generator.init(256)** yêu cầu khóa AES 256 bit. Provider có thể từ chối kích thước không hỗ trợ hoặc bị chính sách mật mã của runtime giới hạn. Ứng dụng không nên tự chuyển khóa thành chuỗi hoặc ghi khóa ra log để kiểm tra.

### Tạo cặp khóa RSA

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;

public class RsaKeyCreation {
    public static KeyPair generateRsa3072()
            throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072, new SecureRandom());
        return generator.generateKeyPair();
    }
}
~~~

Với RSA, **initialize(3072)** chỉ định độ dài modulus. Thời gian sinh khóa có thể đáng kể hơn so với khóa đối xứng. Trong môi trường thực tế, nếu khóa cần được bảo vệ trong HSM, hãy dùng cơ chế sinh khóa của thiết bị/provider thay vì sinh trong JVM rồi xuất khóa riêng vào thiết bị.

### Tạo cặp khóa EC theo đường cong chuẩn

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.ECGenParameterSpec;

public class EcKeyCreation {
    public static KeyPair generateP256()
            throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        return generator.generateKeyPair();
    }
}
~~~

Với EC, nên chỉ định tên đường cong chuẩn thay vì truyền một con số tùy ý. **secp256r1** còn được gọi là NIST P-256. Không phải mọi provider đều hỗ trợ cùng danh sách đường cong; hãy kiểm tra trên JDK và HSM đích.

## 6. Kiểm tra kích thước khóa trong Java

Kích thước cần được đọc theo loại khóa. Không thể dùng một phép đo chung cho mọi thuật toán.

### Kiểm tra modulus RSA

~~~java
import java.security.Key;
import java.security.interfaces.RSAKey;

public static int rsaModulusBits(Key key) {
    if (!(key instanceof RSAKey)) {
        throw new IllegalArgumentException("Không phải khóa RSA");
    }
    return ((RSAKey) key).getModulus().bitLength();
}
~~~

**getModulus().bitLength()** trả về độ dài modulus RSA. Có thể dùng cho khóa công khai hoặc khóa riêng triển khai giao diện RSAKey.

### Kiểm tra kích thước trường EC

~~~java
import java.security.Key;
import java.security.interfaces.ECKey;

public static int ecFieldBits(Key key) {
    if (!(key instanceof ECKey)) {
        throw new IllegalArgumentException("Không phải khóa EC");
    }
    return ((ECKey) key).getParams()
            .getCurve()
            .getField()
            .getFieldSize();
}
~~~

Đây là kích thước trường của tham số đường cong, không phải security strength. Ví dụ P-256 có field size 256 bit nhưng mức an toàn cổ điển khoảng 128 bit.

### Kiểm tra giới hạn độ dài khóa của Cipher

~~~java
import javax.crypto.Cipher;

int maxAllowedBits =
        Cipher.getMaxAllowedKeyLength("AES/GCM/NoPadding");
System.out.println("Maximum allowed AES key size: "
        + maxAllowedBits);
~~~

**getMaxAllowedKeyLength** trả về giới hạn tối đa được chính sách mật mã của runtime cho phép đối với transformation. Giá trị này không chứng minh provider hỗ trợ mọi độ dài nhỏ hơn, cũng không cho biết kích thước của một khóa cụ thể. Cần khởi tạo Cipher bằng khóa thực tế hoặc kiểm tra khả năng của provider để xác minh tương thích.

Với khóa bí mật, **SecretKey.getEncoded()** có thể trả về byte array chứa key material, nhưng cũng có thể trả về null nếu khóa không thể xuất. Không nên gọi getEncoded chỉ để đo kích thước đối với khóa nhạy cảm hoặc khóa nằm trong HSM. Hãy lưu metadata về thuật toán và kích thước đã yêu cầu/cấp phát tại thời điểm tạo khóa, hoặc dùng thuộc tính do KMS/HSM cung cấp.

## 7. Kích thước khóa ảnh hưởng đến hiệu năng và tương thích

Tăng kích thước khóa thường làm tăng chi phí tính toán hoặc kích thước dữ liệu giao thức, nhưng mức tăng phụ thuộc thuật toán:

- **AES:** khóa dài hơn có thể tăng số vòng xử lý và chi phí mã hóa; ảnh hưởng thực tế phụ thuộc CPU, phần cứng tăng tốc và provider.
- **RSA:** modulus lớn hơn làm các phép toán khóa riêng và một số thao tác khóa công khai tốn kém hơn; chữ ký và dữ liệu trao đổi cũng có thể lớn hơn.
- **ECC:** đường cong lớn hơn thường tăng chi phí phép toán điểm và kích thước khóa/chữ ký, nhưng thường nhỏ hơn RSA ở mức an toàn tương đương.
- **HMAC:** khóa dài hơn không nhất thiết làm mỗi lần tính MAC chậm hơn đáng kể; cần chọn độ dài phù hợp với hàm băm và chính sách.

Kích thước khóa cũng ảnh hưởng khả năng tương thích. Một hệ thống cũ có thể không hỗ trợ AES-256, đường cong EC mới hoặc thuật toán chữ ký hiện đại. Provider trong HSM có thể hỗ trợ một tập tham số hẹp hơn provider phần mềm. Vì vậy, cần kiểm thử end-to-end giữa các thành phần thay vì chỉ kiểm tra mã ứng dụng.

Không nên tự hạ kích thước khóa để vượt qua lỗi tương thích trong sản xuất. Trước hết xác định thành phần nào từ chối thuật toán hoặc tham số, sau đó nâng cấp provider, runtime hoặc cấu hình giao thức theo lộ trình được phê duyệt.

## 8. Chính sách JDK và Provider

JDK có thể áp dụng chính sách giới hạn thuật toán và kích thước khóa. Các giới hạn này có thể đến từ:

- Chính sách mật mã của runtime và cấu hình triển khai.
- Provider đang được chọn cho transformation hoặc KeyPairGenerator.
- Provider HSM/KMS và chính sách quản trị thiết bị.
- Tiêu chuẩn chứng nhận hoặc chế độ vận hành đặc biệt.
- Quy tắc từ thư viện hoặc giao thức ở tầng ứng dụng.

Từ JDK 9, chính sách unlimited-strength thường được bật mặc định trong JDK tiêu chuẩn, nhưng cấu hình runtime, provider và bản phân phối cụ thể vẫn cần được xác minh. Với các phiên bản JDK cũ hơn hoặc môi trường đã tùy biến, giới hạn có thể khác.

Ứng dụng nên chỉ định thuật toán và tham số rõ ràng, kiểm tra khả năng trên môi trường đích, ghi nhận provider được dùng và có kiểm thử khi nâng cấp JDK. Không ép provider yếu hoặc bật lại thuật toán lỗi thời chỉ để duy trì khả năng tương thích.

## 9. Kích thước khóa và vòng đời quản lý khóa

Key size không chỉ là quyết định tại thời điểm tạo khóa. Nó ảnh hưởng đến toàn bộ vòng đời:

| Giai đoạn | Kiểm soát liên quan đến kích thước khóa |
|---|---|
| Tạo | Chọn thuật toán, độ dài và tham số được phê duyệt; sinh khóa bằng nguồn ngẫu nhiên phù hợp. |
| Cấp phát | Kiểm tra kích thước và thuật toán trước khi cấp cho dịch vụ hoặc đối tác. |
| Lưu trữ | Lưu metadata về thuật toán, kích thước, phiên bản và mục đích; bảo vệ key material. |
| Sử dụng | Provider phải hỗ trợ kích thước; theo dõi hiệu năng và số lần sử dụng theo chính sách. |
| Xoay vòng | Chuyển sang khóa mới có tham số phù hợp; duy trì khả năng xử lý dữ liệu được tạo bởi khóa cũ trong thời gian chuyển tiếp. |
| Thu hồi | Ngừng chấp nhận khóa hoặc chứng thư không còn đáp ứng chính sách; đánh giá dữ liệu và hệ thống phụ thuộc. |
| Hủy | Hủy key material và bản sao theo quy trình; lưu bằng chứng hoàn tất và metadata kiểm toán cần thiết. |

Khi chính sách tăng mức an toàn, không phải lúc nào cũng có thể chỉ tăng kích thước của khóa hiện tại. Có thể phải tạo cặp khóa mới, cấp chứng thư mới, cập nhật cấu hình giao thức và phân phối lại trust anchor. Với dữ liệu đã mã hóa bằng khóa đối xứng cũ, cần quyết định giải mã rồi mã hóa lại, hoặc duy trì khả năng đọc khóa cũ trong một thời gian được kiểm soát.

Đối với envelope encryption, DEK và KEK có vai trò khác nhau. Kích thước DEK cần phù hợp với thuật toán mã hóa dữ liệu; KEK cần đáp ứng chính sách bảo vệ khóa và khả năng của KMS/HSM. Khi thay KEK, dịch vụ có thể hỗ trợ rewrap DEK mà không phải mã hóa lại toàn bộ dữ liệu. Khi thay DEK, thường cần mã hóa lại dữ liệu hoặc duy trì cơ chế đọc các phiên bản cũ.

## 10. Kích thước khóa trong bối cảnh hậu lượng tử

Các mức security strength của RSA và ECC ở trên dựa trên giả định an toàn cổ điển. Máy tính lượng tử đủ lớn, có khả năng sửa lỗi, có thể dùng thuật toán Shor để phá các hệ mật mã khóa công khai dựa trên phân tích thừa số và logarithm rời rạc, bao gồm RSA và ECC. Tăng RSA từ 2048 lên 4096 bit không giải quyết được điểm yếu nền tảng này.

Với thuật toán đối xứng như AES, thuật toán Grover có thể giảm bậc tìm kiếm khóa lý tưởng, nhưng tác động thực tế khác với việc phá RSA/ECC bằng Shor. AES-256 thường được xem xét khi cần biên an toàn dài hạn. Với dữ liệu cần bảo mật trong nhiều năm, tổ chức nên theo dõi lộ trình chuẩn hóa hậu lượng tử và lập kế hoạch di trú thuật toán.

Khóa của thuật toán hậu lượng tử có kích thước và đặc tính hoàn toàn khác RSA/ECC. Không so sánh trực tiếp số byte của public key, private key hoặc ciphertext hậu lượng tử với số bit khóa AES/RSA để suy ra security strength. Cần dùng bộ tham số chuẩn hóa và hướng dẫn chuyển đổi của tổ chức tiêu chuẩn, nhà cung cấp JDK/provider và nền tảng KMS/HSM.

## 11. Những sai lầm thường gặp

**Đánh đồng key size với security strength.** AES-256, RSA-3072 và P-256 không thể so sánh chỉ bằng con số bit. Hãy dùng bảng quy đổi security strength theo chuẩn phù hợp.

**Tăng kích thước khóa mà bỏ qua thuật toán.** Khóa dài không cứu được thuật toán lỗi thời, mode không an toàn hoặc triển khai sai. Cần đánh giá toàn bộ bộ thuật toán và giao thức.

**Dùng khóa ngắn để cải thiện hiệu năng mà không đánh giá rủi ro.** Việc giảm từ RSA-3072 xuống RSA-2048 hoặc từ AES-256 xuống AES-128 phải có căn cứ về security strength, thời hạn bảo vệ và chính sách.

**Đọc getEncoded để kiểm tra mọi khóa.** Khóa HSM có thể không xuất được; thao tác này có thể tạo bản sao key material trong bộ nhớ. Dùng metadata hoặc API quản trị khóa.

**Nhầm độ dài khóa với độ dài dữ liệu mã hóa.** AES-256 vẫn dùng block size 128 bit; ciphertext dài hơn bản rõ chủ yếu do nonce, tag, padding hoặc metadata của định dạng.

**Không kiểm tra giới hạn provider.** Một transformation có thể được JDK nhận diện nhưng provider cụ thể không hỗ trợ độ dài khóa cần thiết. Hãy thử trên đúng provider và thiết bị sản xuất.

## 12. Checklist lựa chọn và vận hành key size

- [ ] Đã xác định mức security strength mục tiêu và thời gian cần bảo vệ dữ liệu.
- [ ] Kích thước khóa phù hợp với thuật toán, chuẩn và chính sách tổ chức.
- [ ] Đã phân biệt key size với block size, output size và security strength.
- [ ] Khóa được sinh bằng API/provider và nguồn ngẫu nhiên phù hợp.
- [ ] JDK, provider, HSM/KMS và các đối tác hỗ trợ tham số đã chọn.
- [ ] Đã đo hiệu năng ở tải thực tế và kiểm tra kích thước dữ liệu giao thức.
- [ ] Metadata lưu thuật toán, kích thước, phiên bản và mục đích khóa.
- [ ] Có kế hoạch xoay vòng và di trú khi chính sách thay đổi.
- [ ] Có phương án xử lý khóa cũ, dữ liệu cũ, thu hồi và hủy.
- [ ] Đã đánh giá lộ trình hậu lượng tử nếu dữ liệu cần bảo vệ dài hạn.

Kích thước khóa là một tham số thiết kế quan trọng nhưng chỉ có ý nghĩa khi được đặt trong ngữ cảnh thuật toán và mô hình đe dọa. Trong Java, cần chọn kích thước qua API phù hợp, xác minh khả năng của JDK/provider, lưu metadata và quản lý việc nâng cấp theo vòng đời. Một quyết định đúng cân bằng được mức an toàn, hiệu năng, tương thích và khả năng duy trì bảo vệ dữ liệu lâu dài.
