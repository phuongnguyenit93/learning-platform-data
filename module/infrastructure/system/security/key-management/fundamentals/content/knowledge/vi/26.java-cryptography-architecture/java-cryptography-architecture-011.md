# SecretKeyFactory

Trong chương **Java Cryptography Architecture** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích SecretKeyFactory và cách Java tạo, dẫn xuất hoặc chuyển đổi khóa bí mật thông qua JCA. SecretKeyFactory thường xuất hiện trong các luồng password-based key derivation như PBKDF2, khi ứng dụng cần biến mật khẩu thành khóa có độ dài phù hợp cho một thuật toán mật mã. Hiểu đúng vai trò của nó giúp tránh nhầm với KeyGenerator, KeyFactory hoặc cơ chế lưu trữ khóa trong KeyStore/KMS.

## 1. SecretKeyFactory là gì?

**SecretKeyFactory** là engine class của Java Cryptography Architecture, nằm trong package javax.crypto. Nó cung cấp giao diện để chuyển một KeySpec thành đối tượng SecretKey, lấy một dạng KeySpec từ SecretKey hoặc chuyển một khóa sang dạng mà provider hiện tại hỗ trợ.

Các thao tác chính:

- **generateSecret(KeySpec):** tạo đối tượng SecretKey từ một đặc tả khóa. Ví dụ, dùng PBEKeySpec để dẫn xuất khóa bằng PBKDF2.
- **getKeySpec(SecretKey, Class):** lấy một dạng đặc tả được yêu cầu từ khóa, nếu provider và khóa cho phép.
- **translateKey(SecretKey):** chuyển khóa sang dạng mà SecretKeyFactory/provider hiện tại có thể xử lý.

SecretKeyFactory không tự sinh một khóa ngẫu nhiên theo cách KeyGenerator thực hiện. Nó xử lý một đầu vào hoặc đặc tả đã có, chẳng hạn mật khẩu, salt, tham số KDF hoặc key material được cung cấp. Khả năng thực hiện cụ thể phụ thuộc thuật toán và provider.

Ví dụ, ứng dụng có thể yêu cầu:

~~~java
SecretKeyFactory factory =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
~~~

Sau đó truyền một PBEKeySpec chứa mật khẩu, salt, số vòng lặp và độ dài khóa để tạo ra khóa dẫn xuất. Ứng dụng dùng khóa này cho mã hóa hoặc, trong một thiết kế password storage, dùng kết quả dẫn xuất làm password verifier.

## 2. Vị trí của SecretKeyFactory trong JCA

JCA cung cấp các engine class với trách nhiệm riêng. SecretKeyFactory là một trong các engine của nhóm JCE, bên cạnh Cipher, Mac, KeyGenerator và KeyAgreement.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| SecretKeyFactory | Tạo/biến đổi SecretKey từ KeySpec | PBKDF2WithHmacSHA256 |
| KeyGenerator | Sinh khóa bí mật mới, thường bằng nguồn ngẫu nhiên mật mã | AES |
| KeyFactory | Tạo hoặc chuyển đổi khóa bất đối xứng | RSA, EC |
| Cipher | Mã hóa và giải mã dữ liệu | AES/GCM/NoPadding |
| Mac | Tạo và xác minh mã xác thực thông điệp | HmacSHA256 |
| KeyAgreement | Tạo shared secret từ thỏa thuận khóa | ECDH |
| KeyStore | Lưu và truy xuất key entry/certificate entry | PKCS12, JKS, PKCS11 |

Có thể hình dung luồng sử dụng như sau:

~~~mermaid
flowchart TD
    A[Password hoặc KeySpec] --> B[SecretKeyFactory]
    C[Provider] --> B
    B --> D[SecretKey]
    D --> E[Cipher hoặc Mac]
    F[KeyGenerator] --> G[SecretKey ngẫu nhiên]
    G --> E
    H[KeyStore / KMS / HSM] -->|Lưu hoặc cung cấp key handle| E
~~~

SecretKeyFactory xử lý việc tạo hoặc chuyển đổi khóa. Cipher mới là thành phần thực hiện mã hóa/giải mã; KeyStore hoặc KMS/HSM mới đảm nhiệm lưu giữ và kiểm soát quyền truy cập khóa. Một ứng dụng có thể dùng các thành phần này cùng nhau trong một quy trình.

## 3. SecretKey, KeySpec và SecretKeyFactory

Ba khái niệm này tạo thành mô hình chính của API:

- **SecretKey:** interface đại diện cho khóa bí mật dùng trong thuật toán đối xứng hoặc thuật toán liên quan.
- **KeySpec:** đặc tả mô tả khóa hoặc dữ liệu đầu vào để tạo khóa. Nó có thể chứa raw key bytes, mật khẩu và tham số dẫn xuất.
- **SecretKeyFactory:** engine nhận KeySpec và tạo SecretKey, hoặc thực hiện chuyển đổi theo khả năng của provider.

Một số KeySpec thường gặp:

| KeySpec | Nội dung | Trường hợp sử dụng |
|---|---|---|
| PBEKeySpec | Password, salt, iteration count và key length | Dẫn xuất khóa dựa trên mật khẩu, ví dụ PBKDF2 |
| SecretKeySpec | Raw key bytes và tên thuật toán | Biểu diễn key bytes đã có thành SecretKey, ví dụ AES |
| DESKeySpec | Key bytes cho DES | Tương thích hệ thống cũ; DES không phù hợp cho thiết kế mới |
| DESedeKeySpec | Key bytes cho Triple DES | Tương thích hệ thống cũ theo policy |

Không phải mọi provider đều hỗ trợ mọi KeySpec hoặc mọi thuật toán. Một KeySpec cũng không bảo đảm dữ liệu đầu vào đủ an toàn: SecretKeySpec có thể đóng gói byte tùy ý, nhưng ứng dụng vẫn phải bảo đảm byte đó là khóa hợp lệ, được tạo đúng cách và có độ dài phù hợp.

## 4. Phân biệt SecretKeyFactory với KeyGenerator và KeyFactory

Tên các API khá giống nhau nhưng mục đích khác nhau:

| API | Loại khóa | Nguồn đầu vào điển hình | Kết quả |
|---|---|---|---|
| SecretKeyFactory | Khóa bí mật | PBEKeySpec, SecretKeySpec hoặc KeySpec khác | SecretKey |
| KeyGenerator | Khóa bí mật | Thuật toán, key size và SecureRandom | SecretKey mới được sinh |
| KeyFactory | Khóa công khai/riêng bất đối xứng | X509EncodedKeySpec, PKCS8EncodedKeySpec hoặc spec phù hợp | PublicKey hoặc PrivateKey |

Ví dụ:

- Tạo AES key ngẫu nhiên cho một phiên mã hóa mới: dùng KeyGenerator.
- Dẫn xuất AES key từ mật khẩu người dùng: dùng SecretKeyFactory với PBKDF2.
- Tạo RSA PublicKey từ dữ liệu X.509 encoded: dùng KeyFactory.

Không nên dùng PBKDF2 để thay cho bộ sinh khóa ngẫu nhiên khi hệ thống đã có nguồn entropy mật mã phù hợp. KDF dựa trên mật khẩu được thiết kế để làm chi phí đoán mật khẩu cao hơn; nó không thay thế CSPRNG.

## 5. Provider và SecretKeyFactorySpi

SecretKeyFactory là API cấp cao. Provider cung cấp phần triển khai thông qua SPI, cụ thể là lớp SecretKeyFactorySpi. Một provider có thể hỗ trợ một thuật toán KDF nhưng không hỗ trợ thuật toán khác hoặc không hỗ trợ mọi loại KeySpec.

Các phương thức SPI tương ứng với những thao tác chính:

| SPI method | Nhiệm vụ |
|---|---|
| engineGenerateSecret(KeySpec) | Tạo SecretKey từ KeySpec |
| engineGetKeySpec(SecretKey, Class) | Trả về KeySpec tương thích với khóa |
| engineTranslateKey(SecretKey) | Chuyển khóa sang dạng provider có thể sử dụng |

JCA tìm provider có dịch vụ SecretKeyFactory cho thuật toán được yêu cầu. Có thể để runtime chọn provider theo thứ tự ưu tiên hoặc chỉ định provider cụ thể nếu ứng dụng có yêu cầu rõ ràng.

~~~java
SecretKeyFactory factory =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");

System.out.println("Algorithm: " + factory.getAlgorithm());
System.out.println("Provider: " + factory.getProvider().getName());
~~~

Không giả định mọi JDK hoặc provider đều có cùng danh sách thuật toán. Trước khi triển khai, cần kiểm tra đúng phiên bản runtime, provider, chính sách thuật toán và môi trường phần cứng.

## 6. PBKDF2 và PBEKeySpec

PBKDF2 (Password-Based Key Derivation Function 2) là KDF dùng mật khẩu, salt, số vòng lặp và độ dài đầu ra để tạo khóa dẫn xuất. Hàm lặp nhiều lần nhằm tăng chi phí cho mỗi lần thử mật khẩu, khiến việc dò đoán hàng loạt tốn tài nguyên hơn.

Các đầu vào quan trọng:

- **Password:** mật khẩu dạng ký tự do người dùng cung cấp hoặc bí mật đầu vào được quản lý.
- **Salt:** giá trị ngẫu nhiên riêng cho từng bản ghi hoặc lần dẫn xuất; salt không cần giữ bí mật.
- **Iteration count:** số vòng lặp; càng cao thì việc dẫn xuất càng tốn thời gian.
- **Key length:** số bit đầu ra cần tạo.
- **PRF:** hàm giả ngẫu nhiên được PBKDF2 sử dụng, ví dụ HMAC-SHA-256.

PBEKeySpec mang các tham số này tới SecretKeyFactory:

~~~java
PBEKeySpec spec = new PBEKeySpec(
        passwordChars,
        salt,
        iterationCount,
        256
);
SecretKeyFactory factory =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
SecretKey derivedKey = factory.generateSecret(spec);
~~~

Iteration count không nên chọn tùy tiện hoặc sao chép một con số cố định mà không đo trên môi trường triển khai. Cần dùng policy hiện hành, benchmark trên phần cứng thực tế, đặt giới hạn tài nguyên và lưu tham số cùng phiên bản thuật toán để có thể nâng cấp sau này. Salt nên được tạo bằng SecureRandom, đủ dài và không tái sử dụng giữa các tài khoản hoặc bản ghi.

PBKDF2 phù hợp khi cần tương thích rộng hoặc môi trường có yêu cầu chuẩn hóa cụ thể. Với password storage, các hàm chuyên dụng chống GPU như Argon2id hoặc scrypt có thể phù hợp hơn nếu policy và thư viện triển khai cho phép. Không nên xem PBKDF2 là lựa chọn mặc định cho mọi bài toán KDF.

## 7. Ví dụ: dẫn xuất AES key từ mật khẩu

Ví dụ dưới đây dùng SecretKeyFactory với PBKDF2WithHmacSHA256 để tạo khóa AES 256 bit. Giá trị iterationCount phải được lấy từ cấu hình policy đã được benchmark và kiểm tra; ví dụ không gán một hằng số dùng cho mọi hệ thống.

~~~java
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public final class PasswordKeyDerivation {
    public static SecretKey deriveAesKey(
            char[] password,
            byte[] salt,
            int iterationCount) throws Exception {

        if (password == null || salt == null || salt.length < 16) {
            throw new IllegalArgumentException("Invalid password or salt");
        }
        if (iterationCount <= 0) {
            throw new IllegalArgumentException("Invalid iteration count");
        }

        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterationCount, 256);
        byte[] encoded = null;
        try {
            SecretKeyFactory factory =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            SecretKey derived = factory.generateSecret(spec);
            encoded = derived.getEncoded();
            if (encoded == null || encoded.length != 32) {
                throw new IllegalStateException(
                        "Provider did not return an exportable 256-bit key");
            }
            return new SecretKeySpec(encoded, "AES");
        } finally {
            spec.clearPassword();
            if (encoded != null) {
                Arrays.fill(encoded, (byte) 0);
            }
        }
    }
}
~~~

SecretKeySpec sao chép key bytes khi tạo đối tượng. Mảng encoded trung gian được xóa trong finally để giảm thời gian giữ thêm một bản sao do ứng dụng quản lý. Việc này không bảo đảm mọi bản sao trong heap, provider hoặc bộ nhớ native đã bị xóa vật lý. PBEKeySpec cũng giữ bản sao password nội bộ, vì vậy cần gọi clearPassword sau khi dùng.

Hàm trên không xóa mảng password do caller truyền vào vì quyền sở hữu mảng thuộc caller. Thành phần gọi cần quyết định thời điểm xóa mảng của mình sau khi hoàn tất. Tránh chuyển password sang String vì String bất biến và không thể chủ động xóa nội dung.

Nếu provider trả về SecretKey không exportable, getEncoded() có thể trả về null. Khi đó không thể tạo SecretKeySpec từ raw bytes theo cách minh họa. Cần dùng luồng provider hỗ trợ hoặc để phép toán tiếp tục trong HSM/KMS, không tìm cách ép xuất key material trái với policy.

## 8. Dùng PBKDF2 cho password storage

Khi lưu mật khẩu người dùng, mục tiêu là lưu một verifier để so sánh khi đăng nhập, không phải lưu mật khẩu hoặc khóa để giải mã mật khẩu về sau. Ứng dụng có thể dùng SecretKeyFactory để tạo giá trị dẫn xuất từ password và lưu:

- Tên thuật toán/KDF và PRF.
- Salt riêng cho từng tài khoản.
- Iteration count hoặc tham số chi phí.
- Độ dài đầu ra.
- Giá trị dẫn xuất (verifier).
- Phiên bản định dạng để hỗ trợ nâng cấp tham số.

Khi đăng nhập, ứng dụng đọc metadata, dẫn xuất lại từ password người dùng nhập và so sánh kết quả theo cách chống timing phù hợp. Không dùng một salt toàn hệ thống, không lưu password plaintext và không log verifier.

~~~java
import java.security.MessageDigest;
import java.util.Arrays;

public final class PasswordVerifier {
    public static boolean matches(byte[] expected, byte[] candidate) {
        return MessageDigest.isEqual(expected, candidate);
    }
}
~~~

Đoạn mã chỉ minh họa phép so sánh constant-time của JDK; việc tạo candidate cần dùng cùng KDF, salt, PRF, iteration count và key length đã lưu. Nếu tham số cũ không còn đạt policy, sau lần xác thực thành công có thể dẫn xuất và lưu lại verifier bằng tham số mới theo quy trình nâng cấp.

Password storage và password-based encryption có thể cùng dùng PBKDF2 nhưng khác mục tiêu. Với password storage, đầu ra là verifier để so sánh. Với mã hóa, đầu ra được dùng như khóa cho Cipher và cần quản lý nonce/IV, tag, định danh dữ liệu và vòng đời khóa.

## 9. Dẫn xuất khóa từ master secret và HKDF

Không phải mọi đầu vào của KDF đều là mật khẩu. Khi đầu vào là master secret ngẫu nhiên có entropy cao, hệ thống thường dùng KDF phù hợp như HKDF để tạo các khóa con theo mục đích. HKDF gồm bước extract và expand, dùng salt và context info để tách biệt khóa theo ứng dụng, tenant hoặc chức năng.

PBKDF2 được thiết kế để xử lý đầu vào có thể có entropy thấp như mật khẩu bằng cách tăng chi phí đoán. Dùng PBKDF2 cho một master key ngẫu nhiên không tự động làm hệ thống an toàn hơn; có thể chỉ làm tăng chi phí không cần thiết. Hãy chọn KDF theo loại đầu vào và yêu cầu của chuẩn.

Việc có API SecretKeyFactory cho một thuật toán KDF cụ thể phụ thuộc provider. Không giả định HKDF hoặc mọi biến thể PBKDF2 đều có sẵn trong mọi JDK. Cần kiểm tra provider và dùng thư viện/implementation được duy trì nếu thuật toán cần thiết không có sẵn trong runtime.

## 10. getKeySpec và translateKey

Ngoài generateSecret, SecretKeyFactory còn cung cấp hai thao tác phục vụ chuyển đổi.

**getKeySpec** yêu cầu provider biểu diễn một SecretKey dưới dạng KeySpec cụ thể. Thao tác này có thể hữu ích khi cần xuất key material hoặc lưu một biểu diễn phù hợp, nhưng cũng có thể làm lộ raw key bytes. Nếu khóa được thiết kế non-exportable, provider có thể từ chối hoặc không cung cấp dạng spec yêu cầu.

**translateKey** chuyển một SecretKey sang dạng mà factory/provider hiện tại hỗ trợ. Nó hữu ích khi làm việc giữa các provider, nhưng không phải cơ chế wrapping, backup hay chuyển khóa qua mạng. Việc dịch khóa có thể yêu cầu truy cập key material tùy provider và loại key.

Ví dụ về kiểm tra khả năng export:

~~~java
byte[] encoded = secretKey.getEncoded();
if (encoded == null) {
    // Provider không cung cấp raw key bytes.
    // Tiếp tục dùng key handle qua provider nếu được hỗ trợ.
}
~~~

Không gọi getEncoded chỉ để debug hoặc log. Với khóa nhạy cảm, chỉ xuất key material khi có lý do được phê duyệt, có cơ chế bảo vệ và có kế hoạch xóa bản sao tạm.

## 11. SecretKeyFactory và SecretKeySpec

SecretKeySpec là một cách đóng gói raw key bytes đã có thành đối tượng SecretKey cho thuật toán chỉ định. Nó không dẫn xuất khóa, không kiểm tra nguồn entropy và không tự tạo khóa an toàn.

Ví dụ:

~~~java
byte[] keyBytes = obtainKeyBytesFromApprovedSource();
SecretKey aesKey = new SecretKeySpec(keyBytes, "AES");
~~~

Đoạn mã chỉ hợp lệ nếu keyBytes đã được tạo và bảo vệ đúng cách, có độ dài hợp lệ cho AES và nguồn cấp phát được phê duyệt. Nếu đầu vào là password, không được đưa trực tiếp password bytes vào SecretKeySpec để làm AES key. Hãy dùng KDF như PBKDF2 hoặc cơ chế phù hợp khác.

SecretKeyFactory có thể nhận SecretKeySpec như một KeySpec trong những provider hỗ trợ, nhưng không phải lúc nào cũng cần. Với raw key bytes đã có, tạo SecretKeySpec trực tiếp thường rõ ràng hơn. Với password-based derivation hoặc provider-specific translation, dùng SecretKeyFactory.

## 12. SecretKeyFactory và KeyStore/KMS/HSM

SecretKeyFactory không phải kho lưu trữ khóa và không tự quản lý quyền truy cập, rotation, backup hoặc destruction. Sau khi tạo SecretKey, ứng dụng cần quyết định nơi lưu và cách sử dụng.

| Thành phần | Trách nhiệm |
|---|---|
| SecretKeyFactory | Dẫn xuất hoặc chuyển đổi khóa bí mật |
| KeyStore | Lưu và truy xuất entry theo provider và loại store hỗ trợ |
| KMS | Quản lý key lifecycle, policy, version, audit và thao tác mật mã theo dịch vụ |
| HSM | Bảo vệ key material trong thiết bị phần cứng và thực hiện thao tác mật mã theo policy |
| Cipher/Mac | Sử dụng khóa cho mã hóa/giải mã hoặc xác thực thông điệp |

Với phần mềm, SecretKeyFactory có thể trả về khóa có thể export để ứng dụng truyền cho Cipher. Với HSM/KMS, provider có thể hỗ trợ khóa dạng handle hoặc dịch vụ dẫn xuất bên trong thiết bị. Không phải mọi HSM provider đều triển khai SecretKeyFactory cho mọi KDF.

Nếu khóa cần non-exportable, không nên gọi getEncoded hoặc getKeySpec để cố lấy raw key. Hãy dùng API của provider để dẫn xuất hoặc sử dụng khóa bên trong thiết bị, đồng thời xác minh policy, quyền thao tác và audit.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| NoSuchAlgorithmException | Provider không hỗ trợ tên KDF/thuật toán | Kiểm tra tên chuẩn, JDK, provider và policy |
| NoSuchProviderException | Provider được chỉ định chưa cài hoặc không được nhận diện | Kiểm tra cấu hình provider và môi trường triển khai |
| InvalidKeySpecException | KeySpec sai loại, tham số không hợp lệ hoặc provider không hỗ trợ | Kiểm tra KeySpec, salt, iteration count và key length |
| InvalidKeyException | SecretKey không phù hợp với provider hoặc thuật toán đích | Kiểm tra algorithm, key length và khả năng translate |
| getEncoded trả null | Khóa không exportable hoặc provider không cung cấp encoding | Dùng key handle qua provider; không ép xuất khóa |
| Kết quả dẫn xuất khác nhau | Khác salt, PRF, iteration count, key length hoặc quy tắc xử lý password | Lưu đầy đủ metadata và chuẩn hóa encoding theo policy |
| Hiệu năng quá thấp | Iteration count quá cao hoặc quá nhiều tác vụ đồng thời | Benchmark, giới hạn tài nguyên và điều chỉnh policy có kiểm soát |
| Khóa dẫn xuất không dùng được với Cipher | Algorithm/key representation không tương thích | Tạo SecretKey đúng thuật toán hoặc dùng provider hỗ trợ trực tiếp |

Không nên bắt mọi lỗi rồi chuyển sang thuật toán yếu hơn hoặc giảm iteration count tự động. Nếu KDF không khả dụng, thao tác nhạy cảm nên thất bại an toàn và phát sinh cảnh báo cấu hình.

## 14. Rủi ro bảo mật khi dùng SecretKeyFactory

- **Salt cố định hoặc tái sử dụng:** làm các tài khoản có cùng password tạo ra cùng verifier, hỗ trợ tấn công bảng tính sẵn.
- **Iteration count thấp:** giảm chi phí đoán password của kẻ tấn công.
- **Dùng password trực tiếp làm key:** không có KDF và không bảo đảm độ dài/entropy.
- **Chọn sai KDF:** dùng password KDF cho master secret ngẫu nhiên hoặc ngược lại mà không có lý do.
- **Rò rỉ password/derived key:** log, exception hoặc dump có thể để lộ đầu vào và đầu ra nhạy cảm.
- **Không lưu metadata:** không thể tái tạo đúng verifier hoặc giải mã dữ liệu sau khi tham số thay đổi.
- **Xuất khóa không cần thiết:** getEncoded/getKeySpec tạo thêm bản sao key material.
- **Không xóa bản sao tạm:** password và byte array tồn tại lâu hơn cần thiết.
- **Bỏ qua giới hạn tài nguyên:** KDF tốn CPU có thể bị lạm dụng để gây cạn kiệt tài nguyên qua đăng nhập đồng thời.
- **Tin rằng SecretKeyFactory lưu khóa:** factory chỉ tạo/chuyển đổi; ứng dụng vẫn phải bảo vệ và quản lý vòng đời kết quả.

Khi xử lý password input, nên giới hạn tốc độ và số tác vụ KDF đồng thời để tránh denial of service. Tham số KDF cần đủ mạnh nhưng cũng phải được benchmark để hệ thống vẫn đáp ứng tải hợp lệ.

## 15. Vòng đời của khóa được dẫn xuất

Khóa tạo ra từ SecretKeyFactory vẫn là một cryptographic key và cần được quản lý như các khóa khác:

1. **Xác định mục đích:** dùng làm password verifier, AES key hay một khóa con có mục đích cụ thể.
2. **Chọn KDF:** dựa trên entropy đầu vào, chuẩn áp dụng và khả năng provider.
3. **Sinh salt/context:** dùng giá trị phù hợp, duy nhất theo đối tượng và không bí mật nếu thuật toán quy định.
4. **Dẫn xuất:** dùng SecretKeyFactory với tham số đã được policy phê duyệt.
5. **Sử dụng:** truyền SecretKey tới Cipher/Mac hoặc lưu verifier cùng metadata.
6. **Lưu trữ:** bảo vệ khóa hoặc verifier; không log key material.
7. **Nâng cấp:** khi policy thay đổi, dẫn xuất lại sau khi xác thực thành công hoặc re-encrypt dữ liệu theo kế hoạch.
8. **Hủy:** loại bỏ các bản key bytes, SecretKey object và dữ liệu phụ thuộc khi hết nhu cầu; nếu khóa có thể tái tạo từ password/master secret, xử lý cả nguồn và metadata theo mục tiêu xóa.

Đối với password verifier, nâng cấp thường có thể thực hiện khi người dùng đăng nhập thành công: xác minh bằng tham số cũ, sau đó tạo verifier mới bằng tham số hiện hành. Đối với khóa mã hóa dữ liệu, không thể đơn giản thay salt hoặc iteration count rồi bỏ khóa cũ nếu ciphertext vẫn cần giải mã. Phải giữ khả năng giải mã hoặc re-encrypt dữ liệu trước khi hủy.

## 16. Ví dụ luồng ứng dụng: mã hóa dữ liệu với khóa dẫn xuất

Một ứng dụng desktop cần mã hóa một tệp bằng mật khẩu do người dùng nhập. Quy trình ở mức khái niệm:

1. Tạo salt ngẫu nhiên mới cho lần mã hóa.
2. Dùng SecretKeyFactory với PBKDF2 để dẫn xuất AES key từ password và salt.
3. Tạo nonce mới, duy nhất cho lần mã hóa bằng AES-GCM.
4. Dùng Cipher mã hóa tệp và xác thực metadata bằng AAD nếu phù hợp.
5. Lưu salt, KDF parameters, nonce, ciphertext và authentication tag cùng metadata phiên bản.
6. Khi mở tệp, đọc metadata, dẫn xuất lại khóa với đúng tham số và xác minh tag trước khi dùng plaintext.
7. Khi đổi password, dẫn xuất khóa mới và re-encrypt dữ liệu hoặc dùng thiết kế envelope phù hợp.

Trong hệ thống server, không nên dùng mật khẩu người dùng trực tiếp làm master key cho toàn bộ dữ liệu của nhiều tài khoản. Cần thiết kế phân tách khóa, kiểm soát quyền và khả năng phục hồi. Nếu dùng KMS/HSM, có thể tạo DEK ngẫu nhiên rồi bọc bằng KEK; password KDF là một bài toán khác với quản lý KEK tập trung.

## 17. Checklist sử dụng SecretKeyFactory

- [ ] Đã xác định rõ mục đích: password verifier, password-based encryption hay chuyển đổi khóa.
- [ ] Đã chọn SecretKeyFactory thay vì KeyGenerator/KeyFactory đúng với loại công việc.
- [ ] Tên thuật toán và provider được kiểm tra trên đúng JDK triển khai.
- [ ] PBEKeySpec có password, salt, iteration count và key length phù hợp.
- [ ] Salt được sinh ngẫu nhiên và riêng cho từng đối tượng/lần dẫn xuất.
- [ ] Tham số KDF được benchmark, lưu metadata và có kế hoạch nâng cấp.
- [ ] Không dùng password trực tiếp làm key bytes.
- [ ] Password và mảng byte trung gian được giới hạn thời gian tồn tại và xóa khi có thể.
- [ ] Không gọi getEncoded/getKeySpec nếu không cần export key material.
- [ ] Khóa không exportable được dùng qua provider/HSM/KMS phù hợp.
- [ ] Password verifier được so sánh theo cách chống timing và không lưu plaintext.
- [ ] KDF workload có rate limit và giới hạn đồng thời.
- [ ] Rotation, recovery, retention và destruction của khóa dẫn xuất đã được xác định.

SecretKeyFactory là engine class dùng để tạo hoặc chuyển đổi khóa bí mật từ các đặc tả khóa thông qua provider của JCA. Nó đặc biệt hữu ích cho PBKDF2 và các luồng password-based derivation, nhưng không thay thế KeyGenerator, Cipher hay hệ thống quản lý khóa. Khi chọn đúng KDF, lưu đầy đủ tham số, hạn chế export và kiểm soát vòng đời kết quả, ứng dụng Java có thể dẫn xuất khóa nhất quán mà vẫn bảo vệ password và key material.
