# Provider capability

Provider capability là tập hợp dịch vụ mật mã và khả năng thực thi mà một Java Security Provider cung cấp cho ứng dụng. Trong Java Cryptography Architecture (JCA) và Java Cryptography Extension (JCE), provider có thể triển khai các dịch vụ như MessageDigest, Signature, Cipher, Mac, KeyAgreement, KeyPairGenerator, KeyFactory, SecretKeyFactory và SecureRandom.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, hiểu provider capability giúp xác định ứng dụng có thể tạo, sử dụng và bảo vệ khóa bằng thuật toán nào, ở provider nào và trong ranh giới bảo mật nào. Một thuật toán có tên trong danh sách provider chưa đủ chứng minh rằng mọi key size, tham số, chế độ hoạt động hoặc thao tác đều được hỗ trợ. Cần kiểm tra capability thực tế trong đúng JDK, provider, thiết bị và cấu hình triển khai.

## 1. Java Security Provider là gì?

Provider là thành phần cài đặt một hoặc nhiều dịch vụ bảo mật theo API chuẩn của Java. Ứng dụng gọi API JCA/JCE theo tên dịch vụ và thuật toán; Java tìm provider có triển khai tương ứng rồi chuyển thao tác đến phần thực thi đó.

Ví dụ:

- MessageDigest.getInstance("SHA-256") yêu cầu một triển khai hàm băm SHA-256.
- Cipher.getInstance("AES/GCM/NoPadding") yêu cầu một triển khai mã hóa AES ở chế độ GCM.
- Signature.getInstance("SHA256withRSA") yêu cầu một triển khai chữ ký số RSA kết hợp SHA-256.
- KeyAgreement.getInstance("ECDH") yêu cầu một triển khai trao đổi khóa ECDH.

Provider có thể là thành phần phần mềm đi kèm JDK, thư viện bên thứ ba hoặc adapter kết nối tới thiết bị/phần cứng như HSM, smart card hay token PKCS#11. Một provider có thể hỗ trợ nhiều dịch vụ; các provider khác nhau cũng có thể triển khai cùng một thuật toán.

~~~mermaid
flowchart TD
    A[Ứng dụng Java] --> B[JCA/JCE API]
    B --> C[Provider selection]
    C --> D[Provider phần mềm]
    C --> E[Provider PKCS#11]
    D --> F[Thuật toán chạy trong JVM]
    E --> G[Token hoặc HSM]
    F --> H[Kết quả mật mã]
    G --> H
~~~

API chuẩn giúp ứng dụng ít phụ thuộc vào cách triển khai cụ thể, nhưng không có nghĩa mọi provider đều có cùng thuật toán, tham số, hiệu năng hoặc chính sách bảo vệ khóa.

## 2. Service, algorithm và provider capability

JCA phân loại triển khai theo service type. Mỗi service type có thể có nhiều thuật toán hoặc biến thể. Capability thực tế của một provider được biểu diễn qua các dịch vụ mà provider đăng ký.

| Service type | Ví dụ thuật toán | Công dụng |
|---|---|---|
| MessageDigest | SHA-256, SHA-384, SHA3-256 | Tạo digest để kiểm tra toàn vẹn |
| Signature | SHA256withRSA, SHA256withECDSA, Ed25519 | Ký và xác minh chữ ký số |
| Cipher | AES/GCM/NoPadding, AES/CBC/PKCS5Padding, RSA/ECB/OAEPWithSHA-256AndMGF1Padding | Mã hóa và giải mã |
| Mac | HmacSHA256, HmacSHA384 | Tạo và xác minh message authentication code |
| KeyAgreement | DiffieHellman, ECDH, XDH | Thiết lập shared secret |
| KeyPairGenerator | RSA, EC, Ed25519, X25519 | Sinh cặp public/private key |
| KeyGenerator | AES, HmacSHA256 | Sinh khóa bí mật |
| KeyFactory | RSA, EC, XDH | Chuyển đổi key specification và key object |
| SecretKeyFactory | PBKDF2WithHmacSHA256 | Tạo secret key từ key specification |
| SecureRandom | Tên implementation do provider đăng ký | Sinh số ngẫu nhiên mật mã |

Một provider có thể đăng ký thuật toán nhưng chỉ hỗ trợ một phần các biến thể. Ví dụ provider có Cipher.AES không nhất thiết hỗ trợ mọi mode/padding; hỗ trợ AES/GCM/NoPadding cũng không đảm bảo mọi tag length, IV length hoặc key size đều hợp lệ.

Capability còn phụ thuộc kiểu khóa. Provider có thể hỗ trợ Signature với khóa RSA phần mềm nhưng không hỗ trợ cùng thuật toán với khóa RSA nằm trên token. Vì vậy, phải kiểm tra đúng loại key, tham số và đường thực thi mà ứng dụng sẽ dùng.

## 3. Provider được chọn như thế nào?

Khi gọi getInstance mà không chỉ định provider, JCA tìm provider theo thứ tự ưu tiên đã đăng ký trong cấu hình bảo mật. Provider đầu tiên phù hợp với service và thuật toán thường được chọn. Thứ tự có thể được thay đổi bởi cấu hình JDK hoặc ứng dụng.

Có ba cách phổ biến để tạo engine:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
~~~

~~~java
Signature signature = Signature.getInstance(
        "SHA256withRSA",
        "ProviderName");
~~~

~~~java
Provider provider = Security.getProvider("ProviderName");
Cipher cipher = Cipher.getInstance(
        "AES/GCM/NoPadding",
        provider);
~~~

Hai cách sau chỉ định provider cụ thể. Cách này hữu ích khi ứng dụng cần provider HSM, provider được phê duyệt hoặc triển khai đã được kiểm thử. Tuy nhiên, tên provider phải có trong runtime và provider phải hỗ trợ đúng dịch vụ/thuật toán. Nếu không, getInstance sẽ ném NoSuchAlgorithmException hoặc NoSuchProviderException.

Không nên ép provider theo tên chỉ vì môi trường phát triển đang có provider đó. Hãy xác nhận provider được cài đặt và cấu hình giống production, đồng thời kiểm tra cơ chế fallback nếu hệ thống cho phép fallback.

## 4. Khám phá provider và dịch vụ bằng Java API

Lớp java.security.Security cung cấp các phương thức liệt kê provider đã đăng ký và thuật toán theo service type. Lớp Provider cho phép xem các service mà một provider công bố.

~~~java
import java.security.Provider;
import java.security.Security;

public class ListProviders {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName()
                    + " | version: " + provider.getVersionStr());

            for (Provider.Service service : provider.getServices()) {
                System.out.println("  " + service.getType()
                        + " : " + service.getAlgorithm());
            }
        }
    }
}
~~~

Security.getProviders() trả về các provider đang được đăng ký. Provider.getServices() trả về tập dịch vụ provider công bố. Có thể lọc theo service type hoặc thuật toán để tránh in toàn bộ danh sách trong ứng dụng lớn.

Ví dụ trên dùng getVersionStr(), có từ Java 9. Với runtime Java 8, có thể dùng getVersion() để đọc phiên bản provider theo API cũ.

Ví dụ tìm các thuật toán MessageDigest được runtime nhận diện:

~~~java
import java.security.Security;

Security.getAlgorithms("MessageDigest")
        .stream()
        .sorted()
        .forEach(System.out::println);
~~~

Danh sách này hữu ích để chẩn đoán môi trường, nhưng không phải bài kiểm thử đầy đủ. Tên thuật toán có thể là alias; việc một tên xuất hiện không chứng minh rằng mọi tham số, kiểu khóa và thao tác cần thiết đều hoạt động.

## 5. Kiểm tra một service cụ thể

Có thể tìm service trong một provider bằng Provider.getService(type, algorithm):

~~~java
import java.security.Provider;
import java.security.Security;

public class CheckProviderService {
    public static void main(String[] args) {
        Provider provider = Security.getProvider("ProviderName");
        if (provider == null) {
            throw new IllegalStateException("Provider is not installed");
        }

        Provider.Service service = provider.getService(
                "Cipher",
                "AES");

        if (service == null) {
            System.out.println("Cipher.AES service is not advertised");
            return;
        }

        System.out.println("Type: " + service.getType());
        System.out.println("Algorithm: " + service.getAlgorithm());
        System.out.println("Implementation: " + service.getClassName());
    }
}
~~~

Provider thường đăng ký service Cipher theo thuật toán cơ sở như AES. Transformation AES/GCM/NoPadding được xử lý ở bước tạo engine Cipher; do đó cần gọi Cipher.getInstance với transformation đầy đủ để xác nhận mode và padding thực sự dùng được.

Provider.Service còn cung cấp thông tin thuộc tính và phương thức supportsParameter. Phương thức này có thể giúp kiểm tra một đối tượng tham số/khóa có được service chấp nhận hay không, nhưng không thay thế việc thử khởi tạo và thực hiện thao tác thật theo tài liệu provider.

Một số provider công bố thuộc tính như SupportedKeyClasses, SupportedKeyFormats, KeySize, ImplementedIn hoặc thuộc tính riêng. Đây là metadata do provider cung cấp; cách đặt tên, ý nghĩa và độ chi tiết có thể khác nhau. Không suy ra một bảo đảm bảo mật chỉ từ tên thuộc tính.

## 6. Phân biệt capability được quảng bá và capability thực thi

Để kết luận một provider đáp ứng yêu cầu, cần kiểm tra theo nhiều lớp:

1. **Service có được đăng ký không?** Provider có công bố đúng service type và algorithm không?
2. **Engine có khởi tạo được không?** getInstance có tạo được đối tượng với provider được chọn không?
3. **Tham số có hợp lệ không?** Mode, padding, curve, digest, IV, tag length, key size hoặc parameter spec có được chấp nhận không?
4. **Loại khóa có được hỗ trợ không?** Khóa phần mềm, khóa token, khóa không xuất được hoặc key format cụ thể có hoạt động không?
5. **Thao tác có thành công không?** Có thể init, update, doFinal, sign, verify, generateSecret hoặc generateKey đúng yêu cầu không?
6. **Chính sách có cho phép không?** Thuật toán, kích thước khóa và provider có phù hợp yêu cầu vận hành, pháp lý hoặc chứng nhận không?
7. **Hành vi có đúng trong môi trường đích không?** Kiểm tra trên đúng JDK, hệ điều hành, provider version, HSM firmware, token policy và cấu hình production.

Ví dụ, provider có thể tạo được Cipher cho AES-GCM nhưng thiết bị HSM chỉ hỗ trợ một số key size hoặc tag length. Engine khởi tạo thành công với key phần mềm không chứng minh token có thể thực hiện cùng thao tác. Phải kiểm thử với key object được tạo hoặc nạp từ đúng token.

## 7. Kiểm tra khả năng thực tế của Cipher

Ví dụ sau kiểm tra provider có thể tạo engine AES-GCM, khởi tạo mã hóa với khóa AES 256 bit và IV 12 byte, rồi thực hiện một lần mã hóa. Đây là phép kiểm tra capability cơ bản cho môi trường thử nghiệm; trong production cần dùng key và provider đúng với kiến trúc triển khai.

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class ProbeAesGcm {
    public static void main(String[] args) throws Exception {
        Provider provider = Security.getProvider("ProviderName");
        if (provider == null) {
            throw new IllegalStateException("Provider is not installed");
        }

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES", provider);
        keyGenerator.init(256);
        SecretKey key = keyGenerator.generateKey();

        byte[] iv = new byte[12];
        java.security.SecureRandom.getInstanceStrong().nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", provider);
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        byte[] ciphertext = cipher.doFinal(
                "provider capability probe".getBytes(
                        java.nio.charset.StandardCharsets.UTF_8));

        System.out.println("Provider: " + cipher.getProvider().getName());
        System.out.println("Ciphertext bytes: " + ciphertext.length);
    }
}
~~~

Tên ProviderName cần được thay bằng tên provider thực tế. Ví dụ sinh key bằng KeyGenerator không bảo đảm key nằm trong HSM; nếu mục tiêu là kiểm tra HSM, phải tạo hoặc nạp key theo cơ chế của provider HSM và xác minh key object thuộc token đó. Không in key hoặc bí mật ra log.

Trong ứng dụng mã hóa thực tế, IV GCM phải duy nhất cho mỗi lần mã hóa dưới cùng một khóa theo quy tắc của giao thức. Probe này tạo IV ngẫu nhiên cho một lần thử; không được sao chép đoạn kiểm tra thành logic mã hóa sản xuất mà bỏ qua quản lý nonce.

## 8. Key size, parameters và giới hạn chính sách

Provider capability không chỉ là tên thuật toán. Một số thuộc tính quan trọng:

- **Key size:** provider có hỗ trợ khóa 128, 192, 256 bit hoặc kích thước khác không?
- **Parameter spec:** có hỗ trợ GCMParameterSpec, OAEPParameterSpec, ECGenParameterSpec hoặc tham số nhóm cụ thể không?
- **Mode và padding:** có hỗ trợ đúng transformation, chẳng hạn AES/GCM/NoPadding, không?
- **Digest/MGF:** với RSA-OAEP hoặc chữ ký, provider có hỗ trợ digest và mask generation function được yêu cầu không?
- **Key format và key class:** provider có nhận RAW, PKCS#8, X.509, khóa từ token hoặc đối tượng key không xuất được không?
- **Operation:** provider hỗ trợ encrypt/decrypt, sign/verify, wrap/unwrap, derive hay chỉ một phần?

Cipher.getMaxAllowedKeyLength(transformation) có thể cho biết giới hạn key size tối đa theo chính sách mật mã của runtime cho transformation được hỏi. Giá trị này không chứng minh provider cụ thể hoặc HSM hỗ trợ key size đó; vẫn cần kiểm tra provider và thử thao tác thực tế.

Với khóa được quản lý bởi KMS/HSM, khả năng sử dụng có thể bị giới hạn bởi policy của key object, quyền của principal, cơ chế login, cơ chế backup và thuộc tính không xuất được. Một provider hỗ trợ thuật toán không có nghĩa mọi key trong token đều được phép sử dụng với thuật toán đó.

## 9. Đăng ký và ưu tiên provider

Java cho phép provider được đăng ký thông qua cấu hình bảo mật hoặc bằng API. Hai phương thức thường gặp:

~~~java
Security.addProvider(provider);
~~~

~~~java
Security.insertProviderAt(provider, 1);
~~~

addProvider thêm provider vào cuối danh sách ưu tiên; insertProviderAt chèn provider vào vị trí được chỉ định và có thể thay đổi provider được chọn cho các lời gọi getInstance không chỉ định provider. Nếu provider cùng tên đã tồn tại, thao tác đăng ký có thể không thêm được bản sao.

Thay đổi thứ tự provider có thể ảnh hưởng toàn bộ ứng dụng và thư viện chạy trong cùng JVM. Một thư viện khác có thể bắt đầu dùng provider mới mà không được dự kiến. Vì vậy:

- Đăng ký provider theo cấu hình khởi động có kiểm soát.
- Tránh thay đổi thứ tự provider tùy tiện giữa các request.
- Chỉ định provider rõ ràng ở nơi yêu cầu ranh giới bảo mật cụ thể.
- Kiểm thử toàn bộ luồng mật mã khi thay provider hoặc nâng cấp phiên bản.
- Theo dõi provider name, version và cấu hình đã dùng trong môi trường chạy.

Không tải provider từ nguồn không xác thực. Provider là code có thể thực thi trong tiến trình ứng dụng và có quyền xử lý vật liệu khóa.

## 10. Provider phần cứng, PKCS#11 và HSM

Provider phần cứng thường đóng vai trò cầu nối giữa API Java và thiết bị mật mã. Với PKCS#11, provider Java chuyển các thao tác như tạo khóa, ký, giải mã hoặc key agreement đến token/HSM theo khả năng thiết bị.

Một số đặc điểm quan trọng:

- **Non-extractable key:** private key hoặc secret key có thể được tạo trong token và đánh dấu không cho xuất ra ngoài.
- **Hardware operation:** thao tác ký, giải mã hoặc dẫn xuất có thể chạy bên trong HSM.
- **Token login:** ứng dụng có thể cần xác thực với token trước khi truy cập key object.
- **Object attributes:** quyền sử dụng, mục đích, khả năng wrap/unwrap và khả năng xuất khóa được kiểm soát bằng thuộc tính của key object.
- **Audit và policy:** HSM có thể cung cấp log, phân quyền và cơ chế phê duyệt riêng.

Không phải mọi HSM đều hỗ trợ mọi thuật toán hoặc mọi mode. Ví dụ, một thiết bị có thể hỗ trợ RSA signing nhưng không hỗ trợ RSA-OAEP với mọi digest; có thể hỗ trợ AES-CBC nhưng không hỗ trợ AES-GCM; hoặc hỗ trợ ECDH chỉ trên một tập curve nhất định.

Khi đánh giá provider HSM, cần kiểm tra ma trận capability của đúng model, firmware, PKCS#11 library, provider Java và cấu hình token. Cũng cần xác minh khóa có thực sự được tạo trên thiết bị, có thuộc token mong muốn và không bị xuất ra JVM ngoài dự kiến.

## 11. Provider, FIPS và chính sách mật mã

Một số môi trường yêu cầu sử dụng provider đã được đánh giá hoặc chứng nhận theo một chương trình cụ thể, chẳng hạn FIPS 140. Việc chỉ cài provider có tên hoặc tính năng FIPS không tự chứng minh toàn bộ ứng dụng đang hoạt động trong chế độ được chứng nhận.

Phải kiểm tra:

- Đúng phiên bản provider và module mật mã đã được chứng nhận.
- Cấu hình vận hành có bật đúng approved mode theo hướng dẫn nhà cung cấp.
- Thuật toán, key size, mode và tham số nằm trong phạm vi cho phép.
- Khóa được tạo và sử dụng trong ranh giới mật mã đã được đánh giá.
- Các thao tác ngoài module hoặc fallback sang provider khác không làm mất yêu cầu tuân thủ.

Chính sách bảo mật có thể cấm thuật toán dù provider vẫn công bố nó. Ví dụ, provider còn hỗ trợ SHA-1 để tương thích không có nghĩa ứng dụng mới được phép dùng SHA-1 cho chữ ký. Capability trả lời câu hỏi “có thể làm gì”; policy trả lời “được phép làm gì trong môi trường này”.

## 12. Xử lý lỗi và chẩn đoán provider

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| NoSuchAlgorithmException | Không có provider hỗ trợ service/algorithm được yêu cầu | Liệt kê provider, service và tên thuật toán; kiểm tra alias và version |
| NoSuchProviderException | Provider name chưa được đăng ký hoặc sai tên | Kiểm tra Security.getProvider(name) và cấu hình khởi động |
| InvalidKeyException | Key class, key size, key usage hoặc token policy không phù hợp | Kiểm tra nguồn key, thuộc tính key object và hỗ trợ của provider |
| InvalidAlgorithmParameterException | Parameter spec hoặc giá trị tham số không được hỗ trợ | Kiểm tra mode, curve, IV, tag length, OAEP/MGF và tài liệu provider |
| ProviderException | Lỗi bên trong provider, token hoặc thiết bị | Kiểm tra log provider/HSM, token login, kết nối và firmware |
| Hoạt động trên máy dev nhưng lỗi production | JDK, provider order, policy, token hoặc phiên bản khác nhau | So sánh cấu hình runtime và kiểm thử trên môi trường đích |
| Engine tạo được nhưng thao tác thất bại | Capability chỉ hỗ trợ một phần hoặc key không tương thích | Thực hiện probe với đúng key, parameters và operation |

Không nên bắt exception rồi tự động chuyển sang provider phần mềm yếu hơn nếu hệ thống yêu cầu thao tác phải nằm trong HSM hoặc provider đã phê duyệt. Fallback phải là quyết định kiến trúc được đánh giá và cấu hình rõ ràng.

## 13. Checklist đánh giá provider capability

- [ ] Ghi nhận JDK version, provider name/version và thứ tự provider trong runtime.
- [ ] Xác định service type và algorithm chính xác mà ứng dụng cần.
- [ ] Kiểm tra service được đăng ký và engine có thể khởi tạo.
- [ ] Thử đúng key size, parameter spec, mode, padding và key format.
- [ ] Kiểm thử operation thực tế: generate, init, sign, verify, encrypt, decrypt hoặc derive.
- [ ] Dùng key object đúng nguồn, nhất là khóa không xuất được từ HSM/token.
- [ ] Xác minh provider có chạy thao tác trong ranh giới phần cứng dự kiến hay không.
- [ ] Kiểm tra giới hạn policy, approved mode và yêu cầu chứng nhận.
- [ ] Không để fallback thay đổi ranh giới bảo vệ khóa ngoài dự kiến.
- [ ] Lặp lại kiểm thử sau khi nâng cấp JDK, provider, firmware hoặc cấu hình bảo mật.

Provider capability cho biết các dịch vụ mật mã mà Java runtime có thể cung cấp, nhưng khả năng thực tế còn phụ thuộc thuật toán, tham số, loại khóa, provider version, thiết bị và policy. Đánh giá đúng cần kết hợp khám phá metadata với phép thử trên cấu hình triển khai thực tế, đặc biệt khi private key được bảo vệ trong KMS/HSM.
