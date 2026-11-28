# Algorithm name

Trong Java Cryptography Architecture (JCA), **algorithm name** là tên định danh mà ứng dụng dùng để yêu cầu một dịch vụ mật mã từ API Java và Security provider. Ví dụ, SHA-256 là tên thuật toán băm, SHA256withRSA là tên thuật toán chữ ký, AES/GCM/NoPadding là một transformation cho mã hóa, còn RSA là tên thuật toán khóa bất đối xứng thường dùng khi tạo hoặc xử lý key pair.

Tên thuật toán không chỉ là chuỗi để viết vào code. Nó xác định loại dịch vụ được yêu cầu, ảnh hưởng đến provider được chọn, cách tham số được truyền, loại key tương thích và khả năng liên thông giữa các hệ thống. Chọn nhầm tên hoặc hiểu nhầm ý nghĩa có thể khiến ứng dụng dùng sai thuật toán, sai mode, sai padding hoặc một cơ chế không đáp ứng chính sách bảo mật.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Algorithm và provider**. Nội dung kết nối tên thuật toán với vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, backup, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Tên thuật toán dùng để làm gì?

JCA cung cấp các engine class như MessageDigest, Signature, Cipher, Mac, KeyGenerator và KeyPairGenerator. Khi tạo một engine object, ứng dụng truyền tên thuật toán để yêu cầu loại dịch vụ cần dùng.

Ví dụ:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Signature signature = Signature.getInstance("SHA256withRSA");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Mac mac = Mac.getInstance("HmacSHA256");
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
~~~

Mỗi tên được hiểu trong ngữ cảnh của engine class:

- SHA-256 trong MessageDigest yêu cầu một hàm băm.
- SHA256withRSA trong Signature yêu cầu thuật toán chữ ký kết hợp SHA-256 và RSA.
- AES/GCM/NoPadding trong Cipher yêu cầu thuật toán mã hóa AES với mode GCM và không dùng padding kiểu block.
- HmacSHA256 trong Mac yêu cầu cơ chế xác thực thông điệp dựa trên HMAC và SHA-256.
- RSA trong KeyPairGenerator yêu cầu dịch vụ sinh cặp khóa RSA.

Một chuỗi giống nhau có thể mang nghĩa khác khi dùng với engine class khác. Vì vậy, khi đọc cấu hình, phải xem cả tên engine/service type và tên thuật toán.

## 2. Phân biệt các loại tên thường gặp

Không phải mọi chuỗi có vẻ giống tên thuật toán đều là algorithm name của JCA.

| Loại tên | Ví dụ | Ý nghĩa |
|---|---|---|
| Message digest | SHA-256 | Hàm băm tạo digest. |
| Signature algorithm | SHA256withRSA | Thuật toán ký và xác minh. |
| Cipher transformation | AES/GCM/NoPadding | Thuật toán mã hóa, mode và padding. |
| MAC algorithm | HmacSHA256 | Mã xác thực thông điệp. |
| Key algorithm | RSA, EC, AES, Ed25519 | Loại khóa hoặc thuật toán khóa. |
| Key derivation algorithm | PBKDF2WithHmacSHA256 | Dẫn xuất khóa từ đầu vào và salt. |
| KeyStore type | PKCS12, JKS, PKCS11 | Loại kho khóa hoặc backend. |
| TLS protocol | TLSv1.3 | Phiên bản giao thức bảo mật. |
| TLS cipher suite | TLS_AES_128_GCM_SHA256 | Bộ thuật toán được TLS thương lượng. |
| Object alias | payments-signing-key-v4 | Định danh một entry/key object trong hệ thống. |
| ASN.1 object identifier | 1.2.840.113549.1.1.11 | OID định danh thuật toán hoặc đối tượng trong cấu trúc ASN.1. |

Ví dụ, TLS_AES_128_GCM_SHA256 là tên cipher suite của TLS 1.3, không phải transformation để truyền trực tiếp cho Cipher.getInstance. Ngược lại, AES/GCM/NoPadding là transformation của JCA, không phải cipher suite TLS.

## 3. Tên thuật toán gắn với engine class

JCA định danh dịch vụ bằng cặp service type và algorithm name. Một số engine class quan trọng:

| Engine class | Ví dụ tên | Mục đích |
|---|---|---|
| MessageDigest | SHA-256 | Tạo digest. |
| Signature | SHA256withRSA, SHA256withECDSA, Ed25519 | Ký và xác minh. |
| Cipher | AES/GCM/NoPadding, RSA/ECB/OAEPWithSHA-256AndMGF1Padding | Mã hóa và giải mã. |
| Mac | HmacSHA256 | Tạo và kiểm tra MAC. |
| KeyGenerator | AES, HmacSHA256 | Sinh khóa đối xứng. |
| KeyPairGenerator | RSA, EC, Ed25519 | Sinh cặp khóa. |
| KeyFactory | RSA, EC, Ed25519 | Chuyển đổi key specification và key object. |
| KeyAgreement | ECDH | Thỏa thuận bí mật chung. |
| SecretKeyFactory | PBKDF2WithHmacSHA256 | Tạo secret key từ key specification. |
| AlgorithmParameters | GCM, OAEP, EC | Biểu diễn tham số thuật toán. |
| SecureRandom | DRBG | Sinh số ngẫu nhiên mật mã. |
| KeyStore | PKCS12, JKS, PKCS11 | Truy cập kho khóa. |

Tên sau dấu chấm trong getInstance thuộc ngữ cảnh engine class tương ứng. Không thể dùng SHA-256 với KeyPairGenerator hoặc dùng RSA làm tên MessageDigest.

## 4. Tên chuẩn và alias

**Tên chuẩn (canonical/standard name)** là tên được tài liệu JCA/JDK công bố cho một dịch vụ hoặc thuật toán. **Alias** là tên thay thế mà provider ánh xạ về cùng một service.

Ví dụ, một provider có thể công bố tên chuẩn SHA256withRSA và một hoặc nhiều alias tương thích. Alias có thể được giữ để hỗ trợ ứng dụng cũ, tên lịch sử hoặc quy ước của một thư viện khác.

Không nên tự suy ra alias chỉ từ cách viết. Một tên được một provider chấp nhận có thể không được provider khác hỗ trợ. Khi cần khả năng tương thích, hãy dùng tên chuẩn trong tài liệu Java Standard Algorithm Names hoặc tài liệu provider được phê duyệt.

Provider có thể công bố alias qua thuộc tính dạng Alg.Alias.<service-type>.<alias> hoặc qua metadata service. Service type và tên thuật toán trong framework JCA thường được so sánh không phân biệt hoa thường, nhưng cấu hình bên ngoài, thư viện khác và hệ thống PKI có thể có quy tắc riêng. Nên giữ cách viết chuẩn để cấu hình dễ đọc và dễ kiểm toán.

## 5. Cách JCA tra cứu tên thuật toán

Khi ứng dụng gọi:

~~~java
Signature signature = Signature.getInstance("SHA256withRSA");
~~~

JCA tìm provider đã đăng ký có service type Signature và algorithm tương ứng. Nếu không chỉ định provider, runtime áp dụng quy tắc lựa chọn provider theo cấu hình và khả năng hỗ trợ.

Có thể chỉ định provider tường minh:

~~~java
Signature signature =
        Signature.getInstance("SHA256withRSA", "SunRsaSign");
~~~

Hoặc truyền đối tượng Provider:

~~~java
Provider provider = java.security.Security.getProvider("SunRsaSign");
if (provider == null) {
    throw new IllegalStateException("Required provider is unavailable");
}

Signature signature = Signature.getInstance("SHA256withRSA", provider);
~~~

Nếu không tìm thấy service phù hợp, getInstance thường ném NoSuchAlgorithmException. Nếu chỉ định tên provider không tồn tại, overload tương ứng có thể ném NoSuchProviderException. Tạo được engine object chưa chứng minh key, tham số hoặc backend sẽ hoạt động; cần kiểm tra tiếp ở bước init và operation.

## 6. Tên thuật toán chữ ký số

Tên chữ ký thường biểu diễn thuật toán chữ ký và, với nhiều thuật toán, cả hàm băm được dùng trước khi ký.

| Tên JCA | Ý nghĩa khái quát | Loại key thường dùng |
|---|---|---|
| SHA256withRSA | SHA-256 kết hợp chữ ký RSA theo profile PKCS#1 v1.5 | RSA |
| SHA384withRSA | SHA-384 kết hợp chữ ký RSA PKCS#1 v1.5 | RSA |
| SHA256withECDSA | SHA-256 kết hợp ECDSA | EC |
| SHA384withECDSA | SHA-384 kết hợp ECDSA | EC |
| RSASSA-PSS | Chữ ký RSA-PSS; cần tham số PSS phù hợp | RSA |
| Ed25519 | Chữ ký EdDSA với Ed25519 | Ed25519 |

SHA256withRSA không đồng nghĩa RSASSA-PSS. SHA256withRSA thường chỉ RSA PKCS#1 v1.5 signature, còn RSA-PSS là scheme khác có salt và tham số riêng. Nếu giao thức yêu cầu PSS, phải chọn đúng thuật toán và cấu hình PSSParameterSpec; không đổi tên một cách tùy ý.

Ví dụ dùng SHA256withRSA:

~~~java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();

Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(publicKey);
verifier.update(message);
boolean valid = verifier.verify(signed);
~~~

Ví dụ giả định privateKey và publicKey là một cặp tương ứng, message được mã hóa theo quy ước chung và provider hỗ trợ key type này.

## 7. RSA-PSS và tham số chữ ký

RSASSA-PSS là một scheme chữ ký RSA có tham số, gồm hash algorithm, mask generation function, salt length và trailer field. Chỉ ghi tên RSASSA-PSS có thể chưa đủ để hai hệ thống tạo cùng kết quả hoặc xác minh tương thích.

Ví dụ cấu hình PSS với SHA-256:

~~~java
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256",
        "MGF1",
        MGF1ParameterSpec.SHA256,
        32,
        1);

Signature signer = Signature.getInstance("RSASSA-PSS");
signer.setParameter(pss);
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();
~~~

Provider có thể yêu cầu thiết lập tham số ở thời điểm khác hoặc kiểm tra thứ tự init/setParameter theo API và phiên bản. Phải kiểm thử với provider thực tế và cấu hình giống bên xác minh. Hai bên cần thống nhất hash, MGF, hash cho MGF1, salt length và trailer field.

Với Ed25519, tên thuật toán đã bao hàm scheme và không ghép thêm SHA256 như SHA256withRSA. Không tự băm thông điệp trước khi gọi Ed25519 trừ khi giao thức quy định một cơ chế prehash riêng như Ed25519ph.

## 8. Tên Cipher transformation

Đối với Cipher, chuỗi transformation thường có dạng:

~~~text
algorithm/mode/padding
~~~

Trong đó:

- algorithm chỉ thuật toán cơ sở, ví dụ AES hoặc RSA.
- mode chỉ chế độ vận hành, ví dụ GCM hoặc CBC.
- padding chỉ cơ chế padding, ví dụ NoPadding hoặc PKCS5Padding.

Ví dụ:

| Transformation | Ý nghĩa |
|---|---|
| AES/GCM/NoPadding | AES ở chế độ GCM, cung cấp mã hóa có xác thực (AEAD). |
| AES/CBC/PKCS5Padding | AES-CBC với padding kiểu PKCS5/PKCS7 theo block size; không tự cung cấp integrity. |
| AES/CTR/NoPadding | AES ở chế độ counter; cần cơ chế xác thực riêng nếu dùng bảo vệ dữ liệu. |
| RSA/ECB/OAEPWithSHA-256AndMGF1Padding | RSA-OAEP với SHA-256 trong tên transformation; cần kiểm tra đầy đủ tham số OAEP. |

Với RSA, phần ECB trong tên transformation là quy ước tên của API Cipher, không có nghĩa RSA vận hành theo block mode ECB như AES.

Không nên chỉ gọi Cipher.getInstance("AES") cho dữ liệu mới vì mode và padding có thể phụ thuộc provider/default. Hãy ghi rõ transformation và truyền tham số cần thiết.

## 9. AES-GCM và tên transformation

AES/GCM/NoPadding là lựa chọn phổ biến cho mã hóa có xác thực. GCM tạo ciphertext và authentication tag, giúp phát hiện sửa đổi dữ liệu. Ứng dụng phải quản lý nonce/IV đúng cách: không được tái sử dụng nonce với cùng một key.

Ví dụ:

~~~java
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import java.security.SecureRandom;

byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.ENCRYPT_MODE,
        aesKey,
        new GCMParameterSpec(128, nonce));

byte[] ciphertext = cipher.doFinal(plaintext);
~~~

Đây là ví dụ tối giản; nonce phải được lưu cùng ciphertext để giải mã. Với hệ thống ghi dữ liệu lớn, cần cơ chế bảo đảm nonce duy nhất theo key trên nhiều instance và sau restore. Chỉ gọi SecureRandom không tự giải quyết bài toán uniqueness ở mọi quy mô.

## 10. RSA-OAEP và tham số mã hóa

Tên transformation RSA/ECB/OAEPWithSHA-256AndMGF1Padding thường được dùng cho RSA-OAEP. Tuy nhiên, tên transformation không phải lúc nào cũng thể hiện hết mọi tham số MGF1 mà provider áp dụng. Nếu yêu cầu tương thích nghiêm ngặt, hãy truyền OAEPParameterSpec tường minh.

~~~java
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import java.security.spec.MGF1ParameterSpec;

OAEPParameterSpec oaep = new OAEPParameterSpec(
        "SHA-256",
        "MGF1",
        MGF1ParameterSpec.SHA256,
        PSource.PSpecified.DEFAULT);

Cipher cipher = Cipher.getInstance(
        "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
cipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, oaep);
byte[] wrapped = cipher.doFinal(dataKeyBytes);
~~~

Ví dụ minh họa bọc một khóa dữ liệu ngắn; RSA-OAEP không dùng để mã hóa khối dữ liệu lớn. Trong envelope encryption, dữ liệu được mã hóa bằng DEK đối xứng, còn RSA-OAEP hoặc KEK/KMS có thể dùng để bọc DEK.

## 11. Tên hàm băm

MessageDigest dùng tên hàm băm. Một số tên thường gặp:

| Tên | Kết quả |
|---|---|
| SHA-256 | Digest 256 bit |
| SHA-384 | Digest 384 bit |
| SHA-512 | Digest 512 bit |
| SHA3-256 | Digest SHA-3 256 bit |
| SHA3-512 | Digest SHA-3 512 bit |

Ví dụ:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] fingerprint = digest.digest(certificate.getEncoded());
~~~

Không nhầm digest với chữ ký. SHA-256 tạo giá trị băm nhưng không chứng minh ai đã tạo dữ liệu. Để xác thực nguồn gốc, cần chữ ký số hoặc MAC theo threat model.

MD5 và SHA-1 có thể còn xuất hiện trong dữ liệu legacy hoặc compatibility API, nhưng không nên chọn cho thiết kế bảo mật mới. Việc một provider hỗ trợ tên thuật toán không có nghĩa thuật toán đó phù hợp chính sách hiện hành.

## 12. Tên MAC

MAC (Message Authentication Code) xác thực tính toàn vẹn và nguồn gốc dữ liệu giữa các bên cùng có secret key. Tên phổ biến là HmacSHA256 hoặc HmacSHA384.

~~~java
import javax.crypto.Mac;
import javax.crypto.SecretKey;

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(hmacKey);
byte[] tag = mac.doFinal(message);
~~~

HmacSHA256 là tên dịch vụ Mac, không phải tên MessageDigest. Không truyền HmacSHA256 vào MessageDigest.getInstance hoặc SHA-256 vào Mac.getInstance nếu muốn HMAC.

So sánh MAC phải dùng cách so sánh chống timing side-channel phù hợp, chẳng hạn MessageDigest.isEqual trong một số trường hợp Java. Không dùng String.equals cho secret/tag nếu yêu cầu bảo mật đòi hỏi constant-time comparison.

## 13. Tên thuật toán sinh khóa

KeyGenerator dùng tên thuật toán khóa đối xứng; KeyPairGenerator dùng tên thuật toán cặp khóa bất đối xứng.

~~~java
KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
aesGenerator.init(256);
SecretKey aesKey = aesGenerator.generateKey();

KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
rsaGenerator.initialize(3072);
KeyPair rsaPair = rsaGenerator.generateKeyPair();
~~~

Các tên thường gặp:

| Engine | Algorithm name | Ví dụ |
|---|---|---|
| KeyGenerator | AES | Sinh secret key AES. |
| KeyGenerator | HmacSHA256 | Sinh khóa HMAC-SHA-256. |
| KeyPairGenerator | RSA | Sinh RSA key pair. |
| KeyPairGenerator | EC | Sinh EC key pair, cần chỉ định curve/parameter. |
| KeyPairGenerator | Ed25519 | Sinh key pair Ed25519 trên runtime hỗ trợ. |

Tên thuật toán thường không chứa đầy đủ key size hoặc curve. Ví dụ, EC cần parameter spec hoặc named curve phù hợp; RSA cần key size. Phải cấu hình tham số rõ ràng theo policy thay vì dựa vào mặc định.

## 14. Tên thuật toán của KeyFactory và KeyAgreement

KeyFactory chuyển đổi giữa key specification và key object. KeyAgreement thực hiện thỏa thuận bí mật chung.

Ví dụ tên KeyFactory:

- RSA cho khóa RSA.
- EC cho khóa elliptic curve.
- Ed25519 cho khóa Ed25519 khi runtime/provider hỗ trợ.

Ví dụ tên KeyAgreement:

- ECDH cho Elliptic Curve Diffie-Hellman.
- DH cho Diffie-Hellman cổ điển.

Tên này mô tả thuật toán hoặc họ key, không chỉ ra mọi tham số. Với ECDH, hai bên phải dùng curve và tham số tương thích. Kết quả KeyAgreement cần được đưa qua KDF phù hợp trước khi dùng làm khóa ứng dụng, theo giao thức đã định nghĩa.

## 15. Tên KDF và SecretKeyFactory

SecretKeyFactory có thể cung cấp dịch vụ tạo secret key từ KeySpec. Ví dụ PBKDF2WithHmacSHA256 là tên thường gặp cho PBKDF2 dùng HMAC-SHA-256.

~~~java
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.util.Arrays;

char[] password = passwordProvider.getPassword();
byte[] salt = saltGenerator.createSalt();

PBEKeySpec spec = new PBEKeySpec(password, salt, iterationCount, 256);
try {
    SecretKeyFactory factory =
            SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
    byte[] derivedKey = factory.generateSecret(spec).getEncoded();
    // Bảo vệ derivedKey và xóa khi không còn cần thiết.
} finally {
    spec.clearPassword();
    Arrays.fill(password, '\0');
}
~~~

iterationCount và saltGenerator trong ví dụ được cung cấp bởi chính sách ứng dụng. Không lấy một con số lặp từ ví dụ làm chuẩn chung; cần chọn tham số theo hướng dẫn hiện hành, hiệu năng mục tiêu và yêu cầu bảo vệ password. PBKDF2 là KDF, không phải thuật toán mã hóa dữ liệu trực tiếp.

Tên KDF phải được hỗ trợ bởi provider. Các KDF như Argon2 có thể cần thư viện/provider bổ sung; không giả định mọi JDK đều cung cấp.

## 16. Tên AlgorithmParameters

Một số thuật toán cần tham số ngoài key, ví dụ IV, nonce, salt, curve hoặc OAEP parameters. JCA có engine AlgorithmParameters và AlgorithmParameterGenerator.

Một số tên thường gặp:

| Tên | Tham số liên quan |
|---|---|
| GCM | Nonce/IV và authentication tag length |
| OAEP | Hash, MGF, MGF parameters và label |
| EC | Curve/domain parameters |
| PBE | Salt và iteration count |
| DH | Prime, generator và các domain parameters |

Tên AlgorithmParameters không nhất thiết trùng với tên Cipher transformation. Ví dụ, Cipher transformation AES/GCM/NoPadding thường dùng GCMParameterSpec; engine AlgorithmParameters có thể dùng tên GCM tùy provider.

## 17. KeyStore type không phải tên thuật toán mật mã

KeyStore.getInstance nhận tên type để chọn cách lưu hoặc backend:

~~~java
KeyStore fileStore = KeyStore.getInstance("PKCS12");
KeyStore legacyStore = KeyStore.getInstance("JKS");
~~~

Các tên như PKCS12, JKS hoặc PKCS11 xác định loại keystore/provider service. Chúng không phải thuật toán mã hóa dùng để bảo vệ dữ liệu nghiệp vụ.

Tương tự, tên provider như SunJCE hoặc SunPKCS11 là tên provider, không phải algorithm name. Alias trong keystore như app-signing-key là định danh entry, không phải thuật toán.

## 18. Tên thuật toán và ASN.1 Object Identifier (OID)

Trong certificate X.509, CSR, CMS/PKCS#7 và các cấu trúc ASN.1, thuật toán thường được định danh bằng **Object Identifier (OID)**. JCA thường dùng tên dạng chuỗi, còn cấu trúc ASN.1 dùng OID cùng tham số đi kèm.

Một số ví dụ:

| Thuật toán/đối tượng | Tên thường thấy | OID |
|---|---|---|
| RSA public key | rsaEncryption | 1.2.840.113549.1.1.1 |
| SHA-256 with RSA | sha256WithRSAEncryption | 1.2.840.113549.1.1.11 |
| EC public key | id-ecPublicKey | 1.2.840.10045.2.1 |
| ECDSA with SHA-256 | ecdsa-with-SHA256 | 1.2.840.10045.4.3.2 |
| Ed25519 | Ed25519 | 1.3.101.112 |

OID trong certificate có thể mô tả thuật toán ký certificate, thuật toán public key trong SubjectPublicKeyInfo hoặc thuật toán dùng trong một cấu trúc khác. Các vị trí đó có ý nghĩa khác nhau.

Ví dụ, certificate có thể chứa public key RSA trong SubjectPublicKeyInfo nhưng certificate lại được CA ký bằng ECDSA. Không được lấy OID public key để suy ra thuật toán chữ ký của issuer.

Tên JCA và OID không phải lúc nào cũng ánh xạ một-một nếu còn tham số. Với RSA-PSS, AlgorithmIdentifier chứa tham số PSS như hash, MGF và salt length. Khi chuyển đổi giữa JCA và ASN.1, cần giữ đúng cả OID lẫn tham số.

## 19. Tên thuật toán trong TLS

TLS sử dụng nhiều loại tên khác nhau:

- TLSv1.2 hoặc TLSv1.3 là tên protocol version.
- TLS_AES_128_GCM_SHA256 là tên cipher suite.
- RSA, ECDSA hoặc Ed25519 có thể mô tả loại khóa/chữ ký dùng trong xác thực.
- AES/GCM/NoPadding là transformation JCA cho Cipher.
- SHA-256 là tên digest.

Trong TLS 1.3, cipher suite như TLS_AES_128_GCM_SHA256 mô tả AEAD và hash cho HKDF/transcript; key exchange và certificate authentication được thương lượng theo các phần khác của handshake. Không đọc tên cipher suite như một tên transformation Cipher đầy đủ.

Trong Java, SSLContext.getInstance("TLS") yêu cầu dịch vụ TLS của JSSE; nó không phải tên thuật toán mã hóa dữ liệu trực tiếp.

## 20. Kiểm tra tên và service trên provider

Có thể xem thuật toán được runtime công bố:

~~~java
import java.security.Provider;
import java.security.Security;

for (String name : Security.getAlgorithms("Signature")) {
    System.out.println(name);
}

Provider provider = Security.getProvider("SunRsaSign");
if (provider != null) {
    Provider.Service service =
            provider.getService("Signature", "SHA256withRSA");
    System.out.println(service == null ? "not supported" : service.getAlgorithm());
}
~~~

Security.getAlgorithms trả về tập tên mà các provider đã đăng ký cho service type. Provider.getService kiểm tra một service cụ thể. Đây là cách kiểm tra khả dụng trước khi khởi tạo engine object.

Với Cipher, provider thường đăng ký service theo thuật toán cơ sở, chẳng hạn AES. Mode và padding được chỉ định ở transformation và cần kiểm tra bằng cách tạo Cipher với toàn bộ tên transformation:

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

Provider cipherProvider = Security.getProvider("SunJCE");
if (cipherProvider == null
        || cipherProvider.getService("Cipher", "AES") == null) {
    throw new IllegalStateException("AES cipher service is unavailable");
}

Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding", cipherProvider);
~~~

Để kiểm tra provider thực tế được chọn:

~~~java
Signature signature = Signature.getInstance("SHA256withRSA");
System.out.println(signature.getProvider().getName());
~~~

Không nên chỉ kiểm tra danh sách tên rồi kết luận thao tác sẽ chạy. Provider có thể từ chối key size, curve, parameter, mode hoặc key object khi init.

## 21. Kiểm thử algorithm name trên môi trường thực tế

Một quy trình kiểm thử nên gồm:

1. Xác định engine class và tên chuẩn cần dùng.
2. Xác định provider được phép và backend chứa key.
3. Kiểm tra service có tồn tại trong provider.
4. Tạo engine object bằng đúng tên và provider.
5. Khởi tạo với key và parameters thực tế.
6. Chạy known-answer test hoặc test vector đã được phê duyệt.
7. Kiểm tra kết quả, lỗi, encoding và khả năng liên thông.
8. Kiểm tra audit cho provider, key ID, operation và kết quả.

Ví dụ, với AES/GCM/NoPadding, không chỉ xác minh Cipher.getInstance thành công. Cần xác minh GCMParameterSpec được chấp nhận, nonce/tag được xử lý đúng và dữ liệu bị sửa sẽ bị từ chối khi giải mã.

Với chữ ký, phải ký và xác minh bằng đúng thuật toán, key type, tham số và định dạng chữ ký. Chữ ký RSA-PSS và RSA PKCS#1 v1.5 không thể thay thế cho nhau chỉ bằng cách đổi tên.

## 22. Tên thuật toán có thể khác giữa provider

Các provider có thể khác nhau về:

- Tên canonical và alias được đăng ký.
- Thuật toán, key size và curve được hỗ trợ.
- Transformation có mode/padding nào.
- Tham số mặc định và cách diễn giải tham số.
- Loại key object được chấp nhận.
- Phiên bản JDK hoặc thư viện native yêu cầu.
- Hành vi lỗi khi thuật toán bị vô hiệu hóa.

Một provider có thể hỗ trợ SHA256withRSA nhưng không hỗ trợ Ed25519; provider khác có thể hỗ trợ Ed25519 nhưng không hỗ trợ một transformation RSA cụ thể. Việc một thuật toán có trong Java Standard Names không bảo đảm mọi provider đều triển khai.

Không tự động đổi sang alias gần giống khi service không tồn tại. Nếu cần tương thích nhiều provider, xác định danh sách tên/provider được hỗ trợ, kiểm thử trên từng runtime và ghi nhận lựa chọn thực tế.

## 23. Thuật toán bị hạn chế bởi security policy

JDK có các security properties và chính sách provider để hạn chế thuật toán yếu hoặc không còn được chấp nhận. Ví dụ, TLS và certificate path validation có thể có danh sách thuật toán bị vô hiệu hóa riêng.

Tên thuật toán xuất hiện trong danh sách hỗ trợ không có nghĩa ứng dụng được phép sử dụng nó trong mọi ngữ cảnh. Thuật toán có thể bị chặn bởi:

- Security properties của JDK.
- Chính sách TLS hoặc certificate path.
- Cấu hình provider hoặc HSM.
- Yêu cầu FIPS hoặc tiêu chuẩn nội bộ.
- Policy của KMS/IAM theo key purpose.
- Quy định của giao thức hoặc đối tác.

Không hạ security policy hoặc bật thuật toán yếu chỉ để tương thích một hệ thống cũ. Hãy xác định dữ liệu và đối tác bị ảnh hưởng, lập phương án chuyển đổi có thời hạn và ghi nhận phê duyệt.

## 24. Đặt tên thuật toán trong cấu hình và inventory

Để tránh nhầm lẫn, cấu hình nên ghi riêng engine/service type, algorithm/transformation, provider, key reference và parameters:

~~~yaml
operation: sign
engine: Signature
algorithm: RSASSA-PSS
provider: ApprovedHsmProvider
keyId: document-signing-v7
parameters:
  digest: SHA-256
  mgf: MGF1
  mgfDigest: SHA-256
  saltLength: 32
~~~

Ví dụ trên là metadata minh họa, không chứa key material. Giá trị provider và key ID phải được xác định theo môi trường. Với một thao tác mã hóa AES-GCM, inventory nên lưu transformation, key ID/version, nonce policy và tag length; không ghi secret key hoặc nonce reuse state vào nơi không phù hợp.

Không dùng tên hiển thị tự do như "Strong RSA" thay cho algorithm name chính xác. Tên hiển thị có thể dùng cho UI, nhưng cấu hình vận hành cần giá trị chuẩn, tham số và provider rõ ràng.

## 25. Những lỗi thường gặp

- Nhầm tên digest SHA-256 với tên chữ ký SHA256withRSA.
- Dùng HmacSHA256 với MessageDigest thay vì Mac.
- Dùng TLS_AES_128_GCM_SHA256 như Cipher transformation.
- Chỉ gọi Cipher.getInstance("AES") và để mode/padding phụ thuộc mặc định.
- Nhầm SHA256withRSA với RSASSA-PSS.
- Chọn RSA nhưng không cấu hình key size hoặc OAEP/PSS parameters theo policy.
- Nghĩ mọi provider đều hỗ trợ cùng tên và alias.
- Dùng alias nội bộ của provider làm tên thuật toán portable.
- Nhầm PKCS12/JKS là thuật toán mã hóa dữ liệu.
- Nhầm tên provider SunJCE/SunRsaSign với algorithm name.
- Chỉ kiểm tra getInstance mà không init và chạy operation.
- Bỏ qua OID parameters khi xử lý certificate hoặc CMS.
- Chuyển đổi tên thuật toán nhưng làm mất salt length, MGF digest, IV hoặc tag length.
- Chọn thuật toán yếu chỉ vì provider vẫn công bố nó.
- Không ghi provider và key version thực tế vào audit.

## 26. Ví dụ thực tế: chọn tên thuật toán cho một dịch vụ

Một dịch vụ cần ba chức năng: mã hóa dữ liệu, ký metadata và xác thực thông điệp giữa hai workload.

Thiết kế có thể xác định:

1. Mã hóa dữ liệu: Cipher với AES/GCM/NoPadding, DEK AES, nonce duy nhất theo key và tag length được thống nhất.
2. Bọc DEK: KMS/HSM dùng KEK hoặc RSA-OAEP theo profile đã phê duyệt; lưu key ID/version và tham số cần thiết.
3. Ký metadata: Signature với RSASSA-PSS hoặc thuật toán chữ ký khác được hai bên hỗ trợ; xác định rõ PSS parameters.
4. Xác thực workload: Mac với HmacSHA256 và secret key riêng cho phạm vi workload.
5. Băm fingerprint: MessageDigest với SHA-256.
6. Kiểm tra provider: xác nhận provider hỗ trợ đúng engine, algorithm, key type và parameter.
7. Audit: ghi engine, algorithm/transformation, provider, key ID/version, principal và operation; không ghi key bytes.

Mỗi chức năng có mục đích và loại key riêng. Không dùng một key hoặc một tên thuật toán chung cho mọi operation chỉ để đơn giản cấu hình.

## 27. Checklist chọn algorithm name

Trước khi cấu hình hoặc gọi một dịch vụ mật mã, hãy xác nhận:

- [ ] Đã xác định đúng engine class/service type.
- [ ] Đã chọn tên chuẩn theo tài liệu JCA/JDK hoặc provider được phê duyệt.
- [ ] Đã phân biệt algorithm name, alias, transformation, key type, OID và protocol/cipher suite.
- [ ] Với Cipher, đã chỉ rõ algorithm, mode và padding.
- [ ] Với Signature, đã xác định hash, scheme và tham số cần thiết.
- [ ] Với RSA-PSS/OAEP, đã xác định đầy đủ hash, MGF, salt length hoặc label.
- [ ] Với AES-GCM, đã có nonce policy và tag length rõ ràng.
- [ ] Đã xác định key type, key size, curve và key version tương thích.
- [ ] Đã xác định provider/backend được phép.
- [ ] Đã kiểm tra service thực sự tồn tại trên runtime mục tiêu.
- [ ] Đã init engine với key/parameters và chạy test phù hợp.
- [ ] Đã kiểm tra security properties, compliance và policy nội bộ.
- [ ] Đã xác minh ánh xạ OID/parameters nếu trao đổi certificate hoặc ASN.1.
- [ ] Đã ghi engine, algorithm, provider, key ID/version và operation vào inventory/audit.
- [ ] Không tự fallback sang thuật toán yếu hoặc alias không được phê duyệt.

Algorithm name là hợp đồng giữa ứng dụng, JCA provider và hệ thống trao đổi dữ liệu. Để dùng an toàn, phải xác định đúng service type, tên chuẩn, tham số, key type và provider. Khi các thông tin này được quản lý cùng key ID/version và audit, tổ chức có thể triển khai thuật toán nhất quán, thay provider có kiểm soát và duy trì khả năng tương thích trong suốt vòng đời khóa.
