# Security provider

Trong Java Cryptography Architecture (JCA), **Security provider** là thành phần cung cấp phần triển khai cụ thể cho các dịch vụ mật mã mà Java công bố qua API chuẩn. Provider có thể cung cấp thuật toán băm, chữ ký số, mã hóa, MAC, sinh khóa, trao đổi khóa, sinh số ngẫu nhiên, xử lý certificate hoặc truy cập kho khóa. Ứng dụng gọi API như Signature, Cipher, MessageDigest, KeyPairGenerator hay KeyStore; provider thực hiện thao tác mật mã ở phía dưới.

Provider có thể là thành phần đi kèm JDK, thư viện mật mã bên thứ ba, adapter tới HSM hoặc provider tích hợp với dịch vụ quản lý khóa. Một provider không nhất thiết chứa tất cả thuật toán, cũng không nhất thiết lưu vật liệu khóa. Ví dụ, provider PKCS#11 có thể chuyển yêu cầu ký đến HSM, nơi private key được giữ và sử dụng trong thiết bị.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Java Cryptography Architecture**. Nội dung kết nối provider với vòng đời khóa mật mã: tạo, cấp phát, lưu trữ, sử dụng, backup, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Vì sao JCA cần Security provider?

Java cần hỗ trợ nhiều thuật toán và nền tảng triển khai. Một ứng dụng có thể chạy trên nhiều hệ điều hành, dùng nhiều phiên bản JDK hoặc cần kết nối đến HSM khác nhau. Nếu ứng dụng phải tự cài đặt từng thuật toán và tự giao tiếp với từng thiết bị, mã nguồn sẽ phụ thuộc chặt vào nhà cung cấp và khó thay thế.

JCA tách **API sử dụng dịch vụ mật mã** khỏi **phần triển khai dịch vụ**:

- API chuẩn cung cấp cách gọi thống nhất cho ứng dụng.
- Provider đăng ký các dịch vụ và thuật toán mà nó hỗ trợ.
- JCA tìm provider phù hợp khi ứng dụng yêu cầu một dịch vụ.
- Provider thực hiện phép toán bằng thư viện phần mềm, thiết bị phần cứng hoặc backend từ xa.

Ví dụ, ứng dụng gọi Signature.getInstance("SHA256withRSA") để tạo đối tượng ký. JCA tìm provider có dịch vụ Signature cho thuật toán đó. Ứng dụng có thể tiếp tục dùng API initSign và sign mà không phải tự viết RSA hoặc SHA-256.

Tách lớp như vậy giúp ứng dụng có thể đổi backend trong nhiều trường hợp mà ít thay đổi mã nguồn. Tuy nhiên, khả năng thay thế không tuyệt đối: provider có thể khác nhau về thuật toán, tham số, key object, exportability, hiệu năng và cách xử lý lỗi.

## 2. JCA, JCE và Security provider

**JCA** là kiến trúc và tập API mật mã của Java. **Java Cryptography Extension (JCE)** bổ sung các API và chức năng như mã hóa, giải mã và quản lý khóa đối xứng; các thành phần này hiện được tích hợp trong nền tảng Java.

Provider là lớp triển khai cho các dịch vụ trong kiến trúc đó. Một provider có thể đăng ký nhiều loại service, ví dụ:

| Nhóm service | Engine class thường dùng | Ví dụ thuật toán hoặc chức năng |
|---|---|---|
| Message digest | MessageDigest | SHA-256, SHA-384 |
| Digital signature | Signature | SHA256withRSA, SHA256withECDSA, Ed25519 |
| Symmetric/asymmetric cipher | Cipher | AES/GCM/NoPadding, RSA |
| Message authentication code | Mac | HmacSHA256 |
| Key generation | KeyGenerator, KeyPairGenerator | AES, HmacSHA256, RSA, EC |
| Key agreement | KeyAgreement | ECDH |
| Random generation | SecureRandom | DRBG hoặc nguồn ngẫu nhiên của nền tảng |
| Key storage | KeyStore | PKCS12, JKS, PKCS11 |
| Certificate handling | CertificateFactory, CertPathValidator | X.509, PKIX |

Không phải provider nào cũng hỗ trợ tất cả các service hoặc thuật toán trên. Một provider có thể chuyên về HSM, chỉ cung cấp một số thuật toán được thiết bị hỗ trợ.

## 3. Engine class và Service Provider Interface (SPI)

JCA dùng mô hình **Engine Class / SPI**:

- Engine class là API công khai mà ứng dụng gọi, ví dụ Cipher, Signature hoặc MessageDigest.
- SPI (Service Provider Interface) là lớp trừu tượng mà provider triển khai để cung cấp hành vi thực tế.
- Provider đăng ký service type, tên thuật toán và lớp triển khai SPI tương ứng.

Ví dụ về quan hệ:

| Engine class | SPI tương ứng |
|---|---|
| Cipher | CipherSpi |
| Signature | SignatureSpi |
| MessageDigest | MessageDigestSpi |
| KeyStore | KeyStoreSpi |
| KeyPairGenerator | KeyPairGeneratorSpi |
| SecureRandom | SecureRandomSpi |
| Mac | MacSpi |

Ứng dụng thường không gọi SPI trực tiếp. JCA tạo engine object, điều phối lời gọi đến SPI và provider phù hợp.

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B["Engine API: Signature / Cipher / KeyStore"]
    B --> C["JCA provider selection"]
    C --> D["Provider service descriptor"]
    D --> E["SPI implementation"]
    E --> F["Software library / HSM / KMS adapter"]
~~~

Việc phân lớp này cho phép provider thay đổi cách thực thi mà không bắt ứng dụng tự cài thuật toán. Tuy nhiên, API chuẩn không bảo đảm mọi provider có cùng hành vi ở các tính năng mở rộng hoặc cấu hình riêng.

## 4. Provider đăng ký service như thế nào?

Một Provider là lớp con của java.security.Provider. Provider công bố các service mà nó hỗ trợ. Mỗi service thường có:

- **Type:** loại engine, ví dụ Signature, Cipher, MessageDigest hoặc KeyStore.
- **Algorithm:** tên thuật toán hoặc loại dịch vụ, ví dụ SHA256withRSA hay PKCS12.
- **Implementation class:** lớp SPI mà provider dùng để thực hiện service.
- **Attributes:** thuộc tính bổ sung, có thể mô tả mode, padding, key size hoặc đặc điểm triển khai.
- **Aliases:** tên thay thế được provider ánh xạ đến tên service chính.

Ví dụ, một provider có thể đăng ký service type Signature, algorithm SHA256withRSA. Khi ứng dụng yêu cầu Signature.getInstance("SHA256withRSA"), JCA có thể chọn service đó nếu provider được đăng ký và đáp ứng yêu cầu.

Provider có thể đăng ký service qua cấu trúc thuộc tính tương thích hoặc API putService với đối tượng Provider.Service. Việc tự triển khai provider đòi hỏi hiểu SPI, quy tắc tham số, định dạng key, lỗi mật mã và yêu cầu bảo mật; không nên làm chỉ để bọc một lời gọi thư viện đơn giản.

## 5. Các provider thường gặp trong JDK

JDK có nhiều provider được tích hợp. Danh sách cụ thể phụ thuộc phiên bản, bản phân phối, hệ điều hành và cấu hình runtime.

| Provider | Vai trò khái quát |
|---|---|
| SUN | Cung cấp nhiều dịch vụ nền tảng như digest, signature, keystore và certificate theo phiên bản JDK. |
| SunRsaSign | Các dịch vụ chữ ký RSA. |
| SunEC | Các dịch vụ mật mã đường cong elliptic theo hỗ trợ của JDK. |
| SunJCE | Nhiều dịch vụ JCE như cipher, MAC, key generator và key agreement. |
| SunJSSE | Các dịch vụ TLS/SSL của Java Secure Socket Extension. |
| SunPKCS11 | Cầu nối tới thiết bị hoặc token mật mã qua thư viện PKCS#11. |
| SunMSCAPI | Tích hợp với Windows CryptoAPI/CNG tùy phiên bản và nền tảng. |

Tên và tập dịch vụ có thể thay đổi giữa các bản JDK. Không nên viết ứng dụng dựa trên giả định rằng một provider cụ thể luôn có mặt hoặc luôn cung cấp một thuật toán. Hãy kiểm tra runtime mục tiêu và tài liệu của JDK đang triển khai.

## 6. Liệt kê provider và service khả dụng

Ứng dụng hoặc công cụ vận hành có thể xem provider đã đăng ký:

~~~java
import java.security.Provider;
import java.security.Security;

for (Provider provider : Security.getProviders()) {
    System.out.println("Provider: " + provider.getName());
    System.out.println("Version: " + provider.getVersionStr());
    System.out.println("Info: " + provider.getInfo());
}
~~~

Để liệt kê các service của một provider:

~~~java
Provider provider = Security.getProvider("SunJCE");
if (provider != null) {
    for (Provider.Service service : provider.getServices()) {
        System.out.printf(
                "%s / %s -> %s%n",
                service.getType(),
                service.getAlgorithm(),
                service.getClassName());
    }
}
~~~

Có thể truy vấn tập thuật toán được runtime công bố cho một loại service:

~~~java
for (String algorithm : Security.getAlgorithms("Cipher")) {
    System.out.println(algorithm);
}
~~~

Kết quả liệt kê chỉ cho biết runtime/provider công bố service. Nó chưa chứng minh thuật toán hoạt động với mọi key type, key size, mode, padding hoặc cấu hình bảo mật. Cần chạy kiểm thử chức năng trên đúng môi trường triển khai.

## 7. JCA chọn provider như thế nào?

Khi ứng dụng gọi:

~~~java
Signature signature = Signature.getInstance("SHA256withRSA");
~~~

JCA tìm provider có service tương ứng trong danh sách provider đã đăng ký và áp dụng quy tắc lựa chọn của runtime. Thứ tự provider thường có ảnh hưởng, nhưng lựa chọn thực tế còn có thể chịu tác động bởi cấu hình ưu tiên và khả năng tương thích của service với tham số hoặc key object.

Nếu không chỉ định provider, ứng dụng giao việc lựa chọn cho JCA. Đây là cách phù hợp khi muốn dùng implementation mặc định được runtime hỗ trợ và không cần phụ thuộc nhà cung cấp cụ thể.

Khi yêu cầu một provider cụ thể:

~~~java
Provider provider = Security.getProvider("SunRsaSign");
if (provider == null) {
    throw new IllegalStateException("Required provider is unavailable");
}

Signature signature =
        Signature.getInstance("SHA256withRSA", provider);
~~~

Chỉ định provider giúp hành vi rõ ràng hơn, nhưng làm ứng dụng phụ thuộc provider đó. Nếu provider không có trên môi trường khác, không hỗ trợ key object hoặc không hỗ trợ thuật toán, thao tác sẽ thất bại. Không tự động fallback sang provider khác khi chính sách yêu cầu một implementation cụ thể; nếu có fallback, phải xác định rõ danh sách được phép và audit quyết định.

## 8. Không đồng nhất thứ tự provider với bảo đảm thuật toán

Provider được đăng ký theo thứ tự ưu tiên. Có thể xem danh sách bằng Security.getProviders(). Một số runtime còn có cấu hình ưu tiên service/provider riêng, nên không nên dựa vào giả định “provider đứng đầu luôn được dùng”.

Các yếu tố có thể ảnh hưởng lựa chọn:

- Provider đã đăng ký và vị trí của nó.
- Service type và algorithm được yêu cầu.
- Key class, key parameters và khả năng hỗ trợ của provider.
- Các thuộc tính hoặc cấu hình ưu tiên của runtime.
- Ràng buộc bảo mật của thuật toán và giao thức.

Để vận hành ổn định, hãy kiểm tra provider thực tế sau khi tạo engine object:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
System.out.println("Selected provider: " + cipher.getProvider().getName());
~~~

Kết quả cần được xác minh trong đúng JDK, container, OS và cấu hình production. Đừng dựa vào thứ tự quan sát được trên máy phát triển.

## 9. Đăng ký provider động

Có thể thêm provider trong lúc ứng dụng khởi động bằng Security.addProvider hoặc Security.insertProviderAt:

~~~java
import java.security.Provider;
import java.security.Security;

Provider vendorProvider = loadTrustedVendorProvider();
int position = Security.addProvider(vendorProvider);

if (position == -1) {
    Provider existing = Security.getProvider(vendorProvider.getName());
    if (existing == null) {
        throw new IllegalStateException("Provider registration failed");
    }
}
~~~

loadTrustedVendorProvider() trong ví dụ là hàm giả định của ứng dụng để nạp provider từ package đã được kiểm soát. Không nạp provider từ URL hoặc thư mục mà người dùng không tin cậy có thể ghi.

Security.addProvider thường thêm provider vào cuối danh sách và trả về vị trí đăng ký; nếu provider cùng tên đã tồn tại, kết quả có thể là -1. Security.insertProviderAt(provider, position) cho phép yêu cầu vị trí 1-based; kết quả âm cho biết không thêm được.

Provider list là trạng thái bảo mật dùng chung trong JVM. Thay đổi lúc runtime có thể ảnh hưởng các luồng và thư viện khác. Nên đăng ký provider một lần trong giai đoạn khởi tạo, trước khi ứng dụng tạo các engine object quan trọng.

## 10. Gỡ provider và rủi ro thay đổi cấu hình runtime

Security.removeProvider(name) gỡ provider khỏi danh sách đã đăng ký. Hành động này không nhất thiết làm mất hiệu lực các engine object đã được tạo trước đó, nhưng có thể ảnh hưởng các lần tra cứu service mới.

Không nên thêm/gỡ provider theo từng request. Việc thay đổi provider list trong khi hệ thống đang chạy có thể tạo hành vi không nhất quán giữa các luồng. Hãy quản lý provider như một phần cấu hình khởi động và kiểm soát thay đổi như thay đổi bảo mật.

Một số rủi ro:

- Thư viện khác có thể đang phụ thuộc provider hoặc thứ tự provider hiện tại.
- Một provider mới có thể chiếm ưu tiên và thay implementation mà ứng dụng không dự kiến.
- Provider không tương thích có thể làm lỗi khởi động hoặc thao tác mật mã.
- Gỡ provider có thể khiến service không còn được tìm thấy.
- Thay đổi không được audit khiến khó điều tra khác biệt giữa các môi trường.

Chỉ người quản trị cấu hình runtime hoặc thành phần bootstrap tin cậy mới nên được quyền thay đổi provider list.

## 11. Đăng ký provider tĩnh qua java.security

Provider có thể được khai báo trong file cấu hình bảo mật java.security của JDK. Các dòng cấu hình thường có dạng:

~~~properties
security.provider.1=ProviderClassOne
security.provider.2=ProviderClassTwo
security.provider.3=ProviderClassThree
~~~

Mỗi dòng chỉ định lớp provider và có thể có tham số cấu hình theo tài liệu provider. Thứ tự đánh số thường xác định thứ tự ưu tiên ban đầu. Đường dẫn file và cơ chế nạp cấu hình phụ thuộc JDK, runtime image và cách triển khai.

Không sửa trực tiếp file java.security của JDK dùng chung một cách tùy tiện. Nên quản lý cấu hình qua image/runtime configuration có version, review, kiểm thử và rollback. Một thay đổi provider có thể tác động nhiều ứng dụng cùng dùng JVM.

Với một số runtime, có thể bổ sung hoặc thay thế security properties bằng cơ chế cấu hình JVM được hỗ trợ. Cần đọc tài liệu của đúng bản JDK; không sao chép tham số cấu hình từ một phiên bản khác mà không kiểm tra.

## 12. Chỉ định provider cho từng thao tác

Hầu hết engine class JCA có overload cho phép chọn provider bằng tên hoặc đối tượng provider:

~~~java
import java.security.MessageDigest;
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

Provider provider = Security.getProvider("SunJCE");
if (provider == null) {
    throw new IllegalStateException("SunJCE is unavailable");
}

MessageDigest digest = MessageDigest.getInstance("SHA-256", provider);
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", provider);
~~~

Chỉ định provider ở từng thao tác hữu ích khi:

- Một thuật toán phải chạy trong provider đã được phê duyệt.
- Key object được tạo bởi HSM/provider cụ thể.
- Cần tránh phụ thuộc vào thay đổi thứ tự provider.
- Hệ thống cần đo lường và audit implementation được sử dụng.

Tuy nhiên, chỉ định provider không tự chứng minh provider được cấu hình an toàn, được chứng nhận hoặc đang chạy trong chế độ mong muốn. Phải xác minh phiên bản, nguồn gốc binary, cấu hình, security policy và trạng thái backend.

## 13. Ví dụ dùng provider cho ký số

Ứng dụng có thể chọn provider tường minh cho thao tác ký và xác minh:

Ví dụ giả định biến provider, privateKey và publicKey đã được lấy từ cấu hình/provider và KeyStore phù hợp; chúng không phải biến toàn cục do JCA tự tạo.

~~~java
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Provider;
import java.security.Signature;

byte[] message = "key lifecycle event".getBytes(java.nio.charset.StandardCharsets.UTF_8);

Signature signer = Signature.getInstance("SHA256withRSA", provider);
signer.initSign(privateKey);
signer.update(message);
byte[] signatureBytes = signer.sign();

Signature verifier = Signature.getInstance("SHA256withRSA", provider);
verifier.initVerify(publicKey);
verifier.update(message);
boolean valid = verifier.verify(signatureBytes);

if (!valid) {
    throw new SecurityException("Signature verification failed");
}
~~~

Ví dụ giả định provider hỗ trợ thuật toán và key type tương ứng. Nếu private key là HSM-backed, provider phải hỗ trợ key object đó và thực hiện ký trong HSM. Không lấy private key dạng rõ ra khỏi thiết bị chỉ để dùng một provider phần mềm khác.

Trong thực tế, chữ ký cần định dạng thông điệp, thuật toán, tham số và encoding thống nhất giữa bên ký và bên xác minh. Với RSA, cần xác định padding/profile (ví dụ RSA-PSS hay PKCS#1 v1.5) theo giao thức; với ECDSA, cần thống nhất cách mã hóa chữ ký.

## 14. Thuật toán và transformation

Tên thuật toán được yêu cầu phải phù hợp với engine class:

| Engine | Ví dụ tên | Ý nghĩa |
|---|---|---|
| MessageDigest | SHA-256 | Hàm băm. |
| Signature | SHA256withRSA, Ed25519 | Chữ ký số. |
| Cipher | AES/GCM/NoPadding | Thuật toán, mode và padding. |
| Mac | HmacSHA256 | Message authentication code. |
| KeyGenerator | AES | Sinh khóa đối xứng. |
| KeyPairGenerator | RSA, EC, Ed25519 | Sinh cặp khóa bất đối xứng. |
| KeyAgreement | ECDH | Thỏa thuận bí mật chung. |
| SecureRandom | DRBG hoặc tên được runtime hỗ trợ | Sinh số ngẫu nhiên mật mã. |

Với Cipher, transformation thường có dạng algorithm/mode/padding. Chỉ ghi AES có thể để provider chọn mode/padding mặc định; điều đó làm cấu hình kém rõ ràng. Với dữ liệu mới, cần chọn mode được phê duyệt, ví dụ AES-GCM với nonce duy nhất theo key và quản lý authentication tag đúng cách.

Tên thuật toán và alias có thể khác giữa provider. Không tự tạo alias hoặc giả định tên rút gọn tương đương với transformation đầy đủ. Kiểm tra tài liệu provider và chạy kiểm thử trên runtime thực tế.

## 15. Kiểm tra provider có hỗ trợ thuật toán không

Có thể truy vấn service trực tiếp:

~~~java
Provider provider = Security.getProvider("SunJCE");
if (provider == null) {
    throw new IllegalStateException("Provider is missing");
}

Provider.Service service =
        provider.getService("Cipher", "AES/GCM/NoPadding");

if (service == null) {
    throw new IllegalStateException("Required cipher is unavailable");
}
~~~

Việc getService trả về service chỉ là bước kiểm tra khả dụng sơ bộ. Provider vẫn có thể từ chối key size, mode, padding, parameter hoặc key object cụ thể khi khởi tạo và thực hiện.

Một quy trình kiểm tra tốt gồm:

1. Xác nhận provider và phiên bản đã cài đặt.
2. Kiểm tra service type và algorithm.
3. Tạo engine object.
4. Khởi tạo với key và parameters dự kiến.
5. Chạy vector kiểm thử hoặc dữ liệu thử đã biết kết quả.
6. Kiểm tra output, lỗi, hiệu năng và audit.

## 16. Key object và provider compatibility

Một PrivateKey, PublicKey hoặc SecretKey là đối tượng Java có thể chứa vật liệu khóa hoặc chỉ là handle đến backend. Provider có thể tạo key object riêng, và không phải provider nào cũng hiểu mọi key object.

Các điểm cần chú ý:

- getEncoded() có thể trả về null đối với khóa không exportable.
- Key object HSM thường phụ thuộc provider và phiên/token.
- Provider ký cần hỗ trợ loại key object hoặc giao diện tương ứng.
- Chuyển key bytes giữa provider có thể làm mất thuộc tính non-exportable hoặc policy.
- Một key object có thể không dùng được sau khi session/token bị đóng hoặc thiết bị mất kết nối.

Không nên chuyển key object giữa provider bằng cách export private key nếu mục tiêu thiết kế là giữ khóa trong HSM. Hãy chọn provider có thể thao tác trực tiếp với key object hoặc dùng cơ chế tích hợp được nhà cung cấp hỗ trợ.

## 17. Provider và sinh khóa

Provider cũng cung cấp dịch vụ sinh khóa. Ví dụ:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA", provider);
rsa.initialize(3072, new SecureRandom());
KeyPair signingPair = rsa.generateKeyPair();

KeyGenerator aes = KeyGenerator.getInstance("AES", provider);
aes.init(256, new SecureRandom());
SecretKey dataKey = aes.generateKey();
~~~

Ví dụ minh họa lựa chọn provider cho RSA và AES; key size phải phù hợp với policy, provider và JDK. Khi sinh khóa trong HSM, cần dùng provider/parameter được thiết bị hỗ trợ để khóa được tạo bên trong HSM. Không tạo khóa trong heap rồi import vào HSM nếu mục tiêu là bảo đảm private key chưa từng rời vùng bảo vệ.

Nguồn ngẫu nhiên cũng là thành phần quan trọng. Provider có thể cung cấp SecureRandom riêng hoặc dựa vào nguồn entropy của hệ điều hành. Không tự tạo random bằng java.util.Random cho mục đích mật mã.

## 18. Provider cho KeyStore và HSM qua PKCS#11

PKCS#11 là giao diện phổ biến để ứng dụng sử dụng token mật mã và HSM. SunPKCS11 là provider cầu nối của một số JDK, chuyển các lời gọi JCA đến thư viện PKCS#11 của nhà cung cấp thiết bị.

Một file cấu hình minh họa:

~~~text
name = OrganizationHSM
library = /opt/vendor/lib/libpkcs11.so
slotListIndex = 0
~~~

Ứng dụng có thể cấu hình provider trong quá trình khởi động:

~~~java
import java.security.KeyStore;
import java.security.Provider;
import java.security.Security;

Provider base = Security.getProvider("SunPKCS11");
if (base == null) {
    throw new IllegalStateException("SunPKCS11 provider is unavailable");
}

Provider hsmProvider = base.configure("/etc/security/hsm-pkcs11.cfg");
int position = Security.addProvider(hsmProvider);

KeyStore hsmStore = KeyStore.getInstance("PKCS11", hsmProvider);
char[] pin = pinProvider.getPin();
try {
    hsmStore.load(null, pin);
} finally {
    java.util.Arrays.fill(pin, '\0');
}
~~~

Đường dẫn thư viện, slot, PIN, login role, thuật toán và quyền truy cập phải theo tài liệu HSM thực tế. Provider.configure trả về provider đã được cấu hình; không dùng đối tượng provider gốc chưa cấu hình để gọi service PKCS#11.

Với token/HSM, load(null, pin) thường mở phiên hoặc đăng nhập token; nó không có nghĩa tạo một file keystore rỗng. store và thao tác xóa/backup có semantics phụ thuộc provider và thiết bị.

## 19. Provider phần mềm, HSM và KMS

Provider có thể kết nối đến nhiều loại backend:

| Loại provider | Nơi thực hiện thao tác | Đặc điểm |
|---|---|---|
| Software provider | Trong tiến trình hoặc thư viện native | Thường nhanh và dễ triển khai; key material có thể nằm trong bộ nhớ ứng dụng. |
| PKCS#11 provider | Token hoặc HSM | Có thể giữ khóa trong phần cứng và thực hiện ký/mã hóa trong thiết bị. |
| KMS provider/adapter | Dịch vụ quản lý khóa qua API | Có thể dùng IAM, policy, versioning, audit và thao tác từ xa. |
| OS-backed provider | Kho khóa hệ điều hành hoặc phần cứng nền tảng | Tích hợp với user/device identity và cơ chế bảo vệ của OS. |

Một adapter KMS có thể biểu diễn key object bằng handle và gửi operation đến dịch vụ. Điều này không tự động có nghĩa API JCA hỗ trợ mọi tính năng KMS, như context, tenant binding, rotation hay asynchronous operation. Phải xác minh adapter cụ thể.

Độ trễ và lỗi mạng cũng ảnh hưởng thao tác mật mã khi provider gọi dịch vụ từ xa. Ứng dụng cần timeout, retry có giới hạn, xử lý idempotency nếu API hỗ trợ và quan sát được lỗi backend. Không retry vô hạn các thao tác có thể tạo tác dụng phụ hoặc tiêu thụ quota.

## 20. Provider và FIPS

Một provider có thể được thiết kế để sử dụng một cryptographic module đã được đánh giá theo FIPS 140, nhưng chỉ cài provider có tên hoặc quảng cáo “FIPS” không đủ để kết luận ứng dụng đang vận hành trong chế độ tuân thủ.

Khi có yêu cầu FIPS, cần xác minh:

- Module mật mã cụ thể có chứng nhận hợp lệ và đúng phiên bản.
- Phiên bản binary, firmware, hệ điều hành và môi trường vận hành nằm trong phạm vi được chứng nhận.
- Provider được cấu hình đúng theo security policy của module.
- Thuật toán, mode, key size và thao tác đang dùng nằm trong phạm vi được phép.
- Key generation, random, import/export và key storage tuân thủ ranh giới module.
- Ứng dụng không vô tình fallback sang provider hoặc thuật toán ngoài phạm vi.
- Có bằng chứng cấu hình, log, kiểm thử và quy trình vận hành.

FIPS là thuộc tính của cryptographic module trong cấu hình và môi trường được xác định; không phải thuộc tính tự động của toàn bộ ứng dụng Java hoặc mọi thuật toán mà provider công bố.

## 21. Provider order, thuật toán bị hạn chế và security properties

JDK có các security properties để điều chỉnh provider và hạn chế thuật toán trong một số ngữ cảnh. Ví dụ:

- jdk.tls.disabledAlgorithms giới hạn thuật toán trong TLS.
- jdk.certpath.disabledAlgorithms giới hạn thuật toán trong quá trình xác minh đường dẫn certificate.
- jdk.jar.disabledAlgorithms giới hạn thuật toán trong xác minh chữ ký JAR.
- Các thuộc tính provider trong java.security xác định provider được nạp và thứ tự ban đầu.

Các thuộc tính này có phạm vi khác nhau; một thuật toán bị chặn trong TLS không có nghĩa mọi lời gọi JCA trực tiếp đều tự động bị chặn trong cùng cách. Cần đọc tài liệu đúng phiên bản JDK và kiểm tra từng lớp sử dụng.

Không tắt kiểm tra thuật toán yếu chỉ để làm cho kết nối hoặc chữ ký cũ hoạt động. Nếu cần tương thích dữ liệu legacy, hãy cô lập phạm vi, đánh giá rủi ro, đặt thời hạn chuyển đổi và có phê duyệt.

## 22. Tích hợp provider trong ứng dụng: quy trình khởi động

Một quy trình bootstrap có thể gồm:

1. Đọc cấu hình provider từ nguồn được quản lý.
2. Xác minh package, phiên bản, chữ ký phân phối và đường dẫn thư viện native.
3. Nạp provider cần thiết và kiểm tra tên/phiên bản.
4. Đăng ký provider theo thứ tự đã phê duyệt.
5. Kiểm tra các service và thuật toán bắt buộc.
6. Khởi tạo HSM/KMS session hoặc kiểm tra kết nối backend.
7. Chạy self-test/known-answer test phù hợp với tài liệu provider.
8. Ghi audit cấu hình provider và kết quả kiểm tra.
9. Chỉ sau khi kiểm tra thành công mới cho phép workload nhận traffic.

~~~mermaid
flowchart TD
    A["Khởi động JVM"] --> B["Nạp cấu hình provider tin cậy"]
    B --> C["Đăng ký provider"]
    C --> D["Kiểm tra service/algorithm"]
    D --> E["Kiểm tra key và backend"]
    E --> F{"Health checks đạt?"}
    F -- "Có" --> G["Cho phép workload hoạt động"]
    F -- "Không" --> H["Fail startup hoặc trạng thái degraded theo policy"]
~~~

Không log PIN, password hoặc key material trong bootstrap. Nếu HSM không sẵn sàng, quyết định fail startup hay cho chạy degraded phải dựa trên mức độ quan trọng của thao tác mật mã; không tự động chuyển sang phần mềm nếu điều đó vi phạm policy.

## 23. Provider và vòng đời khóa mật mã

Provider có thể tham gia nhiều giai đoạn:

| Giai đoạn vòng đời | Dịch vụ/provider có thể tham gia | Điều cần kiểm soát |
|---|---|---|
| Tạo khóa | KeyGenerator, KeyPairGenerator, SecureRandom | Entropy, thuật toán, key size, nơi sinh khóa và exportability. |
| Cấp phát | KeyStore, provider HSM/KMS | Alias/key ID, owner, purpose, certificate và policy. |
| Lưu trữ | KeyStore, PKCS#11, KMS adapter | Bảo vệ key material, access control, backup và metadata. |
| Sử dụng | Cipher, Signature, Mac, KeyAgreement | Đúng operation, key version, tham số và tenant context. |
| Backup/restore | Provider-specific KeyStore/HSM/KMS API | Backup domain, quorum, wrapped package, restore test và audit. |
| Xoay vòng | Sinh key mới, lưu version mới, cập nhật certificate | Giữ khả năng đọc dữ liệu cũ, rewrap/re-encrypt và rollout. |
| Thu hồi | Certificate/PKI service, KMS policy | Revoke certificate, disable key hoặc ngăn operation theo policy. |
| Hủy | KeyStore/provider/HSM/KMS destruction API | Xử lý mọi bản sao, pending deletion, recovery path và bằng chứng. |

Không phải mọi engine class đều quản lý lifecycle. Ví dụ, Signature thực hiện ký/xác minh nhưng không tự thu hồi certificate hoặc hủy private key. Cần phối hợp provider với hệ thống PKI, KMS/HSM và quy trình vận hành.

## 24. Kiểm thử provider trước khi đưa vào production

Không chỉ kiểm tra rằng getInstance không ném exception. Hãy xác minh hành vi trên đúng môi trường:

| Nhóm kiểm thử | Nội dung |
|---|---|
| Availability | Provider có được nạp và đăng ký đúng không? |
| Algorithm support | Các service/algorithm cần thiết có sẵn không? |
| Known-answer test | Digest, MAC, cipher hoặc signature có kết quả đúng với vector kiểm thử không? |
| Key compatibility | Provider có dùng được key object từ KeyStore/HSM không? |
| Parameter handling | Nonce, IV, tag length, padding, curve và key size có đúng không? |
| Negative cases | Key sai, parameter sai, quyền thiếu hoặc certificate không hợp lệ có bị từ chối không? |
| HSM/KMS failure | Mất thiết bị, timeout, network partition và quota được xử lý thế nào? |
| Performance | Latency, throughput và concurrency đáp ứng mục tiêu không? |
| Rotation/DR | Khóa mới, key version cũ, backup và restore hoạt động ra sao? |
| Audit | Principal, provider, key ID, operation và kết quả có được ghi nhận không? |

Không tự chạy phép toán với khóa production chỉ để kiểm tra provider. Dùng khóa thử, dữ liệu thử và môi trường phù hợp; kiểm thử HSM/KMS phải theo quy trình của tổ chức.

## 25. Bảo mật khi cài đặt và vận hành provider

Provider là mã thực thi có quyền tham gia các thao tác mật mã nhạy cảm. Nếu provider bị thay bằng phiên bản độc hại, nó có thể ghi lại dữ liệu, key bytes, password hoặc kết quả operation tùy vị trí tích hợp.

Các nguyên tắc cần áp dụng:

- Chỉ cài provider từ nhà cung cấp hoặc nguồn phát hành được phê duyệt.
- Kiểm tra chữ ký package, checksum từ kênh tin cậy và phiên bản.
- Quản lý dependency và native library như thành phần bảo mật quan trọng.
- Giới hạn quyền ghi thư mục chứa provider và thư viện PKCS#11.
- Không tải provider từ vị trí người dùng có thể sửa.
- Ghi nhận provider name, version, source và cấu hình trong inventory.
- Kiểm soát thay đổi provider list và thứ tự ưu tiên qua review.
- Cập nhật bảo mật theo thông báo của nhà cung cấp, kiểm thử tương thích trước rollout.
- Không ghi secret, PIN hoặc vật liệu khóa vào log của ứng dụng hay provider.

Nếu dùng provider bên thứ ba, cần đánh giá cả thư viện Java lẫn native code mà nó nạp. Một provider wrapper an toàn không thể bù cho thư viện native hoặc firmware không đáng tin cậy.

## 26. Khi nào nên chỉ định provider và khi nào nên để JCA lựa chọn?

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Ứng dụng thông thường, không phụ thuộc implementation cụ thể | Để JCA lựa chọn provider theo cấu hình runtime đã được kiểm soát. |
| Private key nằm trong HSM cụ thể | Chọn provider HSM đã cấu hình và xác minh key compatibility. |
| Có yêu cầu compliance gắn với module được đánh giá | Chỉ định provider/module được phê duyệt và xác minh cấu hình vận hành. |
| Cần tương thích nhiều JDK/OS | Tránh hardcode provider name nếu không cần; kiểm thử service trên từng runtime. |
| Debug sự khác biệt giữa môi trường | Ghi nhận provider thực tế và so sánh service/configuration. |
| Có fallback provider | Chỉ cho phép danh sách provider được phê duyệt, định nghĩa điều kiện fallback và audit. |

Mục tiêu là chọn implementation có chủ đích. Không nên ép một provider cụ thể chỉ vì tên của nó quen thuộc, cũng không nên fallback tự do khi chính sách yêu cầu thao tác phải diễn ra trong HSM.

## 27. Những lỗi thường gặp

- Nghĩ JCA là một thuật toán hoặc một provider duy nhất.
- Cho rằng provider nào cũng hỗ trợ cùng thuật toán và tham số.
- Giả định provider đầu tiên luôn được chọn trong mọi trường hợp.
- Chỉ kiểm tra getInstance mà không thử khởi tạo và thực hiện operation.
- Thêm provider không tin cậy hoặc từ thư mục có quyền ghi rộng.
- Thay provider order giữa lúc ứng dụng đang xử lý request.
- Chỉ định provider HSM nhưng key object lại được tạo bởi provider khác không tương thích.
- Gọi getEncoded() và cố xuất private key non-exportable.
- Tự động fallback sang software provider khi HSM lỗi dù policy không cho phép.
- Cho rằng provider có nhãn FIPS đồng nghĩa ứng dụng đang tuân thủ FIPS.
- Không kiểm tra version, native library và firmware của provider.
- Không kiểm tra các security properties giới hạn thuật toán.
- Dùng transformation mơ hồ như AES thay vì mode/padding được xác định rõ.
- Không audit provider thực tế, key ID và operation.

## 28. Ví dụ thực tế: chọn provider cho dịch vụ ký

Một dịch vụ ký tài liệu dùng private key được giữ trong HSM. Đội phát triển cần bảo đảm thao tác ký luôn chạy qua HSM:

1. Chọn HSM và provider PKCS#11 đã được phê duyệt.
2. Cài native library từ package đã xác minh và khóa quyền ghi.
3. Cấu hình slot/token, login role và policy theo tài liệu nhà cung cấp.
4. Khởi tạo provider trong bootstrap và kiểm tra service Signature cần dùng.
5. Lấy key handle/entry từ HSM key store bằng alias hoặc key ID đã kiểm kê.
6. Tạo Signature với provider HSM tường minh.
7. Ký dữ liệu thử và xác minh bằng public key/certificate tương ứng.
8. Kiểm tra audit HSM ghi đúng principal, key ID và operation.
9. Đặt chính sách khi HSM mất kết nối: từ chối ký hoặc chuyển sang chế độ degraded đã phê duyệt; không âm thầm ký bằng private key phần mềm khác.
10. Diễn tập rotation, backup/restore và thu hồi quyền truy cập.

Trong mô hình này, provider là cầu nối giữa Java API và HSM. Bảo mật cuối cùng còn phụ thuộc policy HSM, bảo vệ PIN, IAM, firmware, backup domain, quy trình quản trị và kiểm toán.

## 29. Checklist Security provider

Trước khi triển khai provider trong production, hãy xác nhận:

- [ ] Đã hiểu service type, algorithm và engine class mà ứng dụng cần.
- [ ] Đã xác định provider name, version, nguồn phát hành và backend thực tế.
- [ ] Đã xác minh provider hỗ trợ đúng thuật toán, key type và parameters.
- [ ] Đã quyết định rõ để JCA chọn hay chỉ định provider tường minh.
- [ ] Đã kiểm tra provider order và security properties trên đúng runtime.
- [ ] Đã đăng ký provider ở bootstrap và kiểm soát thay đổi toàn JVM.
- [ ] Package Java và native library được xác minh nguồn gốc và quyền truy cập.
- [ ] Key object tương thích với provider; không export key trái policy.
- [ ] HSM/KMS session, PIN, IAM và timeout được quản lý an toàn.
- [ ] Có known-answer test và negative test cho operation cần dùng.
- [ ] Đã kiểm tra hiệu năng, lỗi backend, quota và failover.
- [ ] Có chính sách fallback rõ ràng; không bypass HSM ngoài ý muốn.
- [ ] Đã xác minh ranh giới module nếu có yêu cầu FIPS.
- [ ] Có audit provider, key ID/version, principal, operation và kết quả.
- [ ] Có kế hoạch cập nhật provider, rollback và diễn tập DR.

Security provider là lớp triển khai giúp JCA kết nối API mật mã với phần mềm, hệ điều hành, HSM hoặc KMS. Khi chọn provider, cần xác minh service thực tế, khả năng tương thích key, cấu hình bảo mật và backend. Kết hợp lựa chọn provider có chủ đích với quản lý vòng đời khóa, phân quyền và audit sẽ giúp ứng dụng Java sử dụng mật mã nhất quán và kiểm soát được rủi ro vận hành.
