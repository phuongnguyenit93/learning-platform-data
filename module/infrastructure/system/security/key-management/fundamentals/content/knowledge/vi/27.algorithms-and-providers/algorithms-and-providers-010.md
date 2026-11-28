# Deprecated algorithm

Trong mật mã, một thuật toán được gọi là **deprecated** khi việc sử dụng nó cho mục đích mới đã bị khuyến cáo dừng lại hoặc đang được thay thế bởi lựa chọn an toàn hơn. Thuật toán có thể vẫn còn trong JDK, provider hoặc hệ thống đối tác để duy trì khả năng tương thích, nhưng điều đó không có nghĩa thuật toán còn phù hợp cho dữ liệu mới.

Trong Java Cryptography Architecture (JCA), nhiều thuật toán cũ vẫn có thể xuất hiện trong danh sách provider và một số lời gọi như `Signature.getInstance` hoặc `Cipher.getInstance` vẫn có thể tạo được đối tượng. Trạng thái đó chỉ cho biết implementation tồn tại. Ứng dụng vẫn phải áp dụng chính sách mật mã của tổ chức, giới hạn thuật toán theo từng mục đích, kiểm tra key size và tham số, đồng thời lập kế hoạch chuyển đổi dữ liệu và khóa cũ.

Bài học phân biệt deprecated, weak, legacy và disabled; giải thích cách Java áp dụng các security property theo từng ngữ cảnh; hướng dẫn kiểm kê thuật toán, thiết kế allowlist, di chuyển chữ ký và ciphertext cũ, quản lý tương thích và kiểm thử downgrade. Các ví dụ dùng Java 17.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích vì sao thuật toán vẫn được provider hỗ trợ nhưng không còn được khuyến nghị.
- Phân biệt deprecated, legacy, weak, disabled và prohibited.
- Nhận biết rủi ro của hash, chữ ký, mã hóa, MAC, KDF, key exchange và key size cũ.
- Hiểu phạm vi của các Java security property như `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms` và `jdk.jar.disabledAlgorithms`.
- Kiểm tra provider, thuật toán và security property trong runtime thực tế.
- Thiết kế allowlist theo operation, protocol, data classification và thời hạn.
- Chuyển đổi ứng dụng sang thuật toán mới mà vẫn xử lý được dữ liệu lịch sử có kiểm soát.
- Lập kế hoạch re-encrypt, re-sign, re-hash hoặc re-wrap phù hợp với từng loại dữ liệu.
- Tránh downgrade, fallback yếu và lựa chọn thuật toán do dữ liệu không tin cậy điều khiển.
- Thiết lập telemetry, kiểm thử và quy trình loại bỏ thuật toán cũ.

Phạm vi là quản lý thuật toán trong ứng dụng Java và hệ thống sử dụng JCA/provider. Bài không thay thế cryptographic standard, chính sách tuân thủ hoặc đánh giá bảo mật của tổ chức. Tính an toàn của một thuật toán còn phụ thuộc vào mode, padding, key size, nonce, cách dùng và threat model.

## 2. Deprecated algorithm là gì?

Deprecated algorithm là thuật toán đã bị khuyến cáo ngừng dùng cho một hoặc nhiều mục đích. Lý do có thể là:

- Có tấn công thực tế làm suy giảm mức an toàn.
- Không còn đáp ứng mức bảo mật tối thiểu hiện tại.
- Có lựa chọn mới an toàn hơn và được hỗ trợ rộng rãi hơn.
- Chuẩn hoặc cơ quan quản lý đã rút khuyến nghị.
- Triển khai phổ biến dễ cấu hình sai.
- Thuật toán không còn phù hợp với yêu cầu hiệu năng, khả năng liên thông hoặc vòng đời dữ liệu.

Từ deprecated không có một ý nghĩa kỹ thuật duy nhất áp dụng cho mọi API Java. Một thuật toán có thể bị deprecate trong một tiêu chuẩn nhưng vẫn có implementation; một provider có thể bỏ implementation; một runtime có thể chặn nó trong TLS hoặc PKIX; một tổ chức có thể cấm thuật toán đó bằng policy riêng.

Vì vậy, cần xác định rõ **thuật toán nào, operation nào, môi trường nào và thời điểm nào** đang bị hạn chế.

### Ví dụ

Một ứng dụng cũ ký file bằng SHA1withRSA. JDK vẫn có thể cung cấp implementation này để xác minh hoặc duy trì tương thích. Tuy nhiên, SHA-1 không còn phù hợp cho chữ ký số mới vì khả năng chống collision đã bị phá vỡ trên thực tế.

Một hệ thống có thể tiếp tục đọc một số chữ ký lịch sử trong quy trình lưu trữ có kiểm soát, nhưng không nên ký artifact mới bằng SHA1withRSA. Việc giữ khả năng xác minh lịch sử cần policy riêng và bằng chứng về thời điểm, nguồn gốc, trạng thái khóa cùng quy trình lưu trữ.

## 3. Phân biệt deprecated, legacy, weak, disabled và prohibited

Các thuật ngữ này thường bị dùng lẫn lộn. Chúng mô tả những trạng thái khác nhau:

| Thuật ngữ | Ý nghĩa thực tế | Cách xử lý |
|---|---|---|
| Deprecated | Được khuyến cáo ngừng sử dụng, thường hướng tới thay thế | Lập kế hoạch migration và ngừng tạo dữ liệu mới |
| Legacy | Còn tồn tại vì tương thích hoặc dữ liệu lịch sử | Giới hạn phạm vi và chỉ duy trì nhu cầu đã xác định |
| Weak | Mức an toàn không đủ cho threat model hiện tại | Loại khỏi operation nhạy cảm; thay thuật toán hoặc tham số |
| Disabled | Bị runtime, provider hoặc policy chặn trong một ngữ cảnh cụ thể | Xử lý theo phạm vi enforcement; không tìm cách né chặn |
| Prohibited | Bị chính sách hoặc yêu cầu bắt buộc cấm | Không sử dụng trong phạm vi bị cấm |

Một thuật toán có thể vừa legacy vừa weak. Một thuật toán disabled trong TLS chưa chắc bị chặn trong mọi API JCA. Một thuật toán deprecated không nhất thiết đã bị xóa khỏi JDK.

### Không đồng nhất với annotation @Deprecated

Annotation `@Deprecated` trong Java đánh dấu API hoặc thành phần Java đã bị deprecate. Nó không phải cơ chế đánh dấu phổ quát cho mọi tên thuật toán mật mã.

Ví dụ, tên `SHA1withRSA` là một tên thuật toán được provider đăng ký. Không thể dựa vào reflection hoặc annotation để biết thuật toán đó có được policy bảo mật của tổ chức cho phép hay không.

Tương tự, `Cipher.getInstance("DES")` tạo được đối tượng không chứng minh DES phù hợp cho dữ liệu mới. Trạng thái phải được đánh giá từ tiêu chuẩn, runtime, provider và policy ứng dụng.

## 4. Vì sao thuật toán cũ trở thành rủi ro?

Mật mã có vòng đời. Một thuật toán được coi là đủ an toàn tại thời điểm thiết kế có thể mất dần biên an toàn khi xuất hiện tấn công mới, năng lực tính toán tăng lên hoặc tiêu chuẩn thay đổi.

Các rủi ro phổ biến:

- **Collision:** hai thông điệp khác nhau tạo cùng hash, ảnh hưởng đến chữ ký và nhận diện nội dung.
- **Preimage/second-preimage weakness:** làm suy yếu khả năng tìm thông điệp tương ứng với digest hoặc tạo thông điệp thay thế.
- **Key search:** key space quá nhỏ khiến brute force khả thi.
- **Protocol weakness:** thuật toán hoặc mode bị khai thác khi kết hợp với cách padding, nonce hoặc xác thực sai.
- **Parameter weakness:** key size, iteration count, curve hoặc nhóm Diffie-Hellman không đủ mạnh.
- **Implementation risk:** thuật toán cũ có nhiều cách triển khai và cấu hình không an toàn.
- **Lack of support:** provider hoặc thiết bị mới không còn hỗ trợ, gây áp lực bật lại cấu hình yếu.
- **Long-term exposure:** dữ liệu lưu trữ nhiều năm có thể bị giải mã trong tương lai nếu dùng thuật toán hoặc khóa không đủ bền.

Không phải mọi lỗi đều giống nhau. SHA-1 collision là rủi ro nổi bật với chữ ký số và certificate; DES có key size quá nhỏ; ECB làm lộ cấu trúc plaintext; CBC không có authentication riêng có thể tạo rủi ro sửa đổi hoặc padding oracle nếu protocol xử lý sai.

## 5. Những nhóm thuật toán thường cần rà soát

### Hash và chữ ký

| Thuật toán | Tình trạng cần lưu ý | Hướng lựa chọn cho thiết kế mới |
|---|---|---|
| MD2, MD4, MD5 | Đã lỗi thời; MD5 có collision thực tế | SHA-256 hoặc SHA-384 |
| SHA-1 | Collision đã được chứng minh thực tế; không dùng cho chữ ký mới | SHA-256 hoặc SHA-384 |
| SHA-224 | Có thể còn phù hợp ở một số policy, nhưng cần xem xét hệ sinh thái và mức an toàn | SHA-256 hoặc SHA-384 thường thuận tiện hơn |
| SHA-256/SHA-384 | Lựa chọn phổ biến hiện nay khi dùng đúng cách | Chọn theo policy và protocol |
| SHA-3 | Họ hash hiện đại | Dùng khi protocol/provider hỗ trợ |

Với chữ ký, cần xem cả thuật toán chữ ký, digest, padding, key size và cách xác minh. `SHA256withRSA` và `SHA1withRSA` không có cùng mức an toàn dù cùng dùng RSA.

### Mã hóa đối xứng

| Thuật toán/mode | Rủi ro hoặc trạng thái | Hướng xử lý |
|---|---|---|
| DES | Key space quá nhỏ, không an toàn | Thay bằng AES |
| RC2, RC4 | Thuật toán cũ, có điểm yếu nghiêm trọng | Không dùng cho dữ liệu mới |
| 3DES/TDEA | Legacy, hiệu năng thấp và đã bị loại khỏi nhiều policy | Lập kế hoạch chuyển sang AES |
| AES-ECB | Mode làm lộ mẫu và cấu trúc plaintext | Dùng AEAD như AES-GCM |
| AES-CBC | Không tự cung cấp authentication | Chỉ duy trì legacy khi có kiểm soát integrity và migration |
| AES-GCM | AEAD phổ biến | Dùng nonce duy nhất theo key và xác minh tag |
| ChaCha20-Poly1305 | AEAD hiện đại | Dùng khi provider/protocol hỗ trợ |

AES là thuật toán block cipher; ECB, CBC và GCM là mode hoạt động. Không nói “AES bị deprecated” chỉ vì một ứng dụng dùng AES-ECB. Cần xác định chính xác primitive và mode.

### MAC, KDF và key exchange

| Nhóm | Ví dụ cần rà soát | Hướng xử lý |
|---|---|---|
| MAC | HMAC-MD5, HMAC-SHA1 trong giao thức cũ | Ưu tiên HmacSHA256 trở lên theo policy |
| Password KDF | PBKDF2 với SHA-1 hoặc iteration count quá thấp; bcrypt cost cũ | Nâng tham số; dùng Argon2id/scrypt/PBKDF2 phù hợp policy |
| Key derivation | KDF tự viết hoặc dùng hash đơn giản | Dùng HKDF hoặc KDF chuẩn |
| Key agreement | DH group yếu, curve cũ hoặc tham số tự tạo | Dùng nhóm/curve được policy chấp nhận |
| Key size | RSA/DSA quá ngắn, EC curve yếu | Áp dụng ngưỡng key size/curve theo policy |

HMAC-SHA1 cần được đánh giá đúng bản chất: collision attack trên SHA-1 không trực tiếp chuyển thành tấn công HMAC giống như chữ ký hash. Tuy vậy, không nên mặc định dùng nó cho thiết kế mới; cần theo chuẩn và policy của giao thức.

## 6. Thuật toán, mode, padding và key size là các lớp khác nhau

Một cấu hình mật mã thường có nhiều thành phần:

- Primitive: AES, RSA, EC, SHA-256.
- Mode: GCM, CBC, ECB, CTR.
- Padding hoặc encoding: OAEP, PKCS#1 v1.5, PSS, PKCS5Padding.
- Key size hoặc curve: AES-128/256, RSA-2048/3072, P-256/P-384.
- Parameters: nonce, IV, salt, iteration count, MGF digest, tag length.
- Protocol context: TLS version, certificate policy, message format.

Không đánh giá một cấu hình chỉ bằng tên primitive.

Ví dụ:

- AES-256-ECB vẫn có thể không phù hợp dù AES-256 là primitive mạnh.
- RSA-4096 với PKCS#1 v1.5 encryption có thể vẫn không đáp ứng yêu cầu mới nếu protocol cần OAEP.
- SHA-256 với ECDSA không cứu được private key ECDSA nếu nonce bị tái sử dụng.
- PBKDF2-HMAC-SHA256 với iteration count quá thấp vẫn có thể yếu cho password storage.
- AES-GCM với nonce trùng dưới cùng một key có thể gây hậu quả nghiêm trọng.

Một crypto inventory phải ghi đủ cấu hình, không chỉ ghi “AES”, “RSA” hoặc “SHA”.

## 7. Thuật toán vẫn có trong provider không có nghĩa được phép dùng

JCA/provider cung cấp implementation. Policy quyết định ứng dụng có được dùng implementation đó cho operation cụ thể hay không.

~~~~mermaid
flowchart TD
    A[Ứng dụng yêu cầu thuật toán]
    B[Provider có implementation?]
    C[Policy ứng dụng cho phép?]
    D[Tham số và key có đạt ngưỡng?]
    E[Runtime/context có enforcement?]
    F[Thực hiện operation]
    X[Từ chối và ghi nhận]
    A --> B
    B -->|Không| X
    B -->|Có| C
    C -->|Không| X
    C -->|Có| D
    D -->|Không| X
    D -->|Có| E
    E -->|Bị chặn| X
    E -->|Cho phép| F
~~~~

Các câu hỏi phải được kiểm tra độc lập:

1. Provider có đăng ký thuật toán không?
2. Ứng dụng có allowlist thuật toán đó không?
3. Key size và parameters có đạt policy không?
4. Runtime có chặn thuật toán trong ngữ cảnh cụ thể không?
5. Giao thức đối tác có tương thích không?
6. Dữ liệu có phải dữ liệu mới hay dữ liệu lịch sử cần xử lý không?

Danh sách provider chỉ là inventory khả năng. Nó không phải danh sách thuật toán được phê duyệt.

## 8. Các Java security property quan trọng

JDK có nhiều security property để hạn chế thuật toán trong một số ngữ cảnh. Các property thường gặp:

| Property | Phạm vi chính |
|---|---|
| `jdk.tls.disabledAlgorithms` | Thuật toán, protocol, key size hoặc điều kiện bị hạn chế trong TLS |
| `jdk.certpath.disabledAlgorithms` | Thuật toán và điều kiện bị hạn chế khi xác minh certificate path |
| `jdk.jar.disabledAlgorithms` | Thuật toán bị hạn chế trong kiểm tra chữ ký JAR |
| `jdk.disabled.namedCurves` | Named curve bị vô hiệu hóa trong các ngữ cảnh JDK áp dụng property này |

Danh sách, cú pháp và mặc định thay đổi theo phiên bản JDK, bản cập nhật bảo mật, vendor và cấu hình triển khai. Đọc file security configuration của đúng runtime và tài liệu phát hành tương ứng.

Điểm quan trọng: các property này có phạm vi riêng. Ví dụ, thuật toán nằm trong `jdk.tls.disabledAlgorithms` có thể bị chặn khi TLS thương lượng cipher suite hoặc xác thực peer, nhưng không nên suy luận rằng mọi lời gọi trực tiếp đến `Signature.getInstance` hoặc `Cipher.getInstance` đều tự động bị chặn.

Không sửa property để làm một kết nối hoặc chữ ký cũ hoạt động mà chưa hiểu tác động. Thay đổi có thể làm suy yếu nhiều ứng dụng cùng dùng runtime.

### Đọc security property từ Java

~~~~java
import java.security.Security;
import java.util.List;

public class SecurityPropertyReport {
    public static void main(String[] args) {
        List<String> names = List.of(
                "jdk.tls.disabledAlgorithms",
                "jdk.certpath.disabledAlgorithms",
                "jdk.jar.disabledAlgorithms",
                "jdk.disabled.namedCurves"
        );

        for (String name : names) {
            String value = Security.getProperty(name);
            System.out.println(name + " = "
                    + (value == null ? "<not set>" : value));
        }
    }
}
~~~~

Kết quả phụ thuộc JDK và security configuration đang chạy. Hãy thu thập báo cáo từ đúng container, JVM flags và runtime image của production. Kết quả từ laptop developer không đủ để chứng minh production có cùng policy.

## 9. AlgorithmConstraints và phạm vi enforcement

Java có interface `java.security.AlgorithmConstraints` để kiểm tra một thuật toán, key hoặc parameters có được phép trong một ngữ cảnh cụ thể hay không. Một số API TLS dùng cơ chế constraints để giới hạn thuật toán trong quá trình handshake.

AlgorithmConstraints không phải một công tắc toàn cục tự động bảo vệ mọi lời gọi JCA. Ứng dụng có thể cần policy wrapper riêng cho các operation như ký, mã hóa, giải mã, KDF hoặc xác minh dữ liệu lưu trữ.

Khi thiết kế policy:

- Dùng allowlist rõ ràng theo operation.
- Kiểm tra key type và key size.
- Kiểm tra tham số như PSS salt length, GCM tag length, nonce và KDF iteration.
- Kiểm tra protocol version và peer capability.
- Từ chối khi không có lựa chọn giao nhau đạt policy.
- Ghi nhận quyết định mà không log key material hoặc secret.

Không dựa vào một danh sách tên thuật toán để bao quát mọi biến thể. Ví dụ, cho phép AES không có nghĩa cho phép ECB; cho phép RSA không có nghĩa cho phép mọi padding và mọi key size.

## 10. Kiểm tra thuật toán mà provider cung cấp

Có thể liệt kê service của provider để biết runtime có implementation nào. Đây là bước inventory, không phải bước phê duyệt.

~~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderAlgorithmInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName()
                    + " " + provider.getVersionStr());

            for (Provider.Service service : provider.getServices()) {
                String type = service.getType();

                if ("Cipher".equalsIgnoreCase(type)
                        || "Signature".equalsIgnoreCase(type)
                        || "MessageDigest".equalsIgnoreCase(type)
                        || "Mac".equalsIgnoreCase(type)
                        || "KeyAgreement".equalsIgnoreCase(type)
                        || "SecretKeyFactory".equalsIgnoreCase(type)) {
                    System.out.println("  " + type + ": "
                            + service.getAlgorithm());
                }
            }
        }
    }
}
~~~~

Một số lưu ý:

- Provider có thể cung cấp alias; tên hiển thị không nhất thiết bao quát mọi tên tương đương.
- Có implementation không có nghĩa mọi key hoặc parameter đều được hỗ trợ.
- Provider có thể được thêm hoặc đổi thứ tự khi ứng dụng khởi động.
- HSM provider có thể chỉ cung cấp một tập thuật toán khác provider phần mềm.
- Provider name và version cần được ghi nhận trong inventory để so sánh môi trường.

Không dùng kết quả liệt kê này làm allowlist tự động. Allowlist phải đến từ policy đã được đánh giá.

## 11. Tạo allowlist cho operation mới

Một ứng dụng nên kiểm tra policy trước khi yêu cầu provider thực hiện operation. Ví dụ dưới đây giới hạn thuật toán chữ ký mới theo allowlist của service.

~~~~java
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.Signature;
import java.util.Locale;
import java.util.Set;

public final class SigningPolicy {
    private static final Set<String> ALLOWED =
            Set.of("ED25519", "RSASSA-PSS");

    private SigningPolicy() {
    }

    public static Signature newSigner(
            String algorithm,
            PrivateKey privateKey
    ) throws GeneralSecurityException {
        String normalized = algorithm.toUpperCase(Locale.ROOT);

        if (!ALLOWED.contains(normalized)) {
            throw new GeneralSecurityException(
                    "Signature algorithm is not approved: " + algorithm
            );
        }

        Signature signature = Signature.getInstance(algorithm);
        signature.initSign(privateKey);
        return signature;
    }
}
~~~~

Đây chỉ là lớp kiểm soát tên thuật toán. Với RSASSA-PSS, ứng dụng còn phải cấu hình `PSSParameterSpec` thống nhất và kiểm tra loại/key size. Với Ed25519, cần kiểm tra provider và policy môi trường có cho phép hay không.

Trong production, không nhận trực tiếp tên thuật toán từ request rồi truyền vào getInstance. Client chỉ nên chọn một protocol version hoặc profile đã được server định nghĩa; server ánh xạ profile đó sang thuật toán và tham số được phê duyệt.

### Kiểm tra RSA key size

~~~~java
import java.security.GeneralSecurityException;
import java.security.interfaces.RSAKey;
import java.security.Key;

public class RsaKeyPolicy {
    public static void requireAtLeast2048Bits(Key key)
            throws GeneralSecurityException {
        if (!(key instanceof RSAKey rsaKey)) {
            throw new GeneralSecurityException("Expected an RSA key");
        }

        int bits = rsaKey.getModulus().bitLength();
        if (bits < 2048) {
            throw new GeneralSecurityException(
                    "RSA key is below the configured minimum"
            );
        }
    }
}
~~~~

Ngưỡng 2048 bit chỉ là ví dụ policy phổ biến cho nhiều hệ thống hiện tại. Một số tổ chức hoặc thời hạn bảo vệ dài có thể yêu cầu ngưỡng cao hơn. Không dùng ví dụ này thay cho policy chính thức, và không đánh giá key strength chỉ bằng modulus length nếu thuật toán hoặc parameters khác không phù hợp.

## 12. Ví dụ lựa chọn chữ ký mới

Khi tạo chữ ký mới, dùng profile đã được phê duyệt và lưu metadata phiên bản cùng dữ liệu. Ví dụ Ed25519:

~~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Base64;

public class ApprovedEd25519Signing {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair keyPair = generator.generateKeyPair();

        byte[] message = "artifact-version=12"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keyPair.getPrivate());
        signer.update(message);

        byte[] signatureBytes = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keyPair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signatureBytes)) {
            throw new SecurityException("Signature verification failed");
        }

        System.out.println(Base64.getEncoder()
                .encodeToString(signatureBytes));
    }
}
~~~~

Ví dụ sinh key pair trong bộ nhớ để minh họa. Production cần nạp private key từ KeyStore/HSM hoặc signing service; public key phải được xác thực qua certificate path, pinning hoặc registry được quản trị.

Đừng chọn Ed25519 chỉ vì code ngắn. Xem xét yêu cầu FIPS, HSM, protocol đối tác, JDK/provider và khả năng xác minh lâu dài.

## 13. Thuật toán cũ trong chữ ký lịch sử

Chữ ký đã tạo bằng thuật toán cũ đặt ra vấn đề khác với chữ ký mới.

Ví dụ, một kho tài liệu chứa chữ ký SHA1withRSA từ nhiều năm trước. Có thể cần xác minh tài liệu để phục vụ audit hoặc tranh chấp. Việc này cần đánh giá:

- Chữ ký được tạo khi nào và có timestamp tin cậy hay không?
- Certificate của signer có hợp lệ tại thời điểm ký không?
- Có bằng chứng về trạng thái thu hồi tại thời điểm liên quan không?
- Public key có nguồn gốc và identity binding đáng tin cậy không?
- Thuật toán có bị khai thác trong bối cảnh dữ liệu đó không?
- Nội dung và chữ ký có được lưu nguyên vẹn không?
- Quy trình lưu trữ có chống thay thế, rollback và giả mạo không?

Một chữ ký SHA-1 không trở nên an toàn trở lại chỉ vì ứng dụng xác minh được nó. Nếu không có bằng chứng thời điểm và nguồn gốc, kẻ tấn công có thể tạo một chữ ký mới bằng key bị lộ hoặc lợi dụng collision để làm sai lệch nội dung được xác nhận.

### Tách luồng ký mới và xác minh lịch sử

| Operation | Chính sách khuyến nghị |
|---|---|
| Ký dữ liệu mới | Chỉ thuật toán và parameters hiện hành |
| Xác minh giao dịch trực tuyến | Chỉ profile hiện hành; từ chối legacy |
| Xác minh archive lịch sử | Luồng riêng, key/policy rõ ràng, bằng chứng lịch sử và audit |
| Nhập chữ ký từ bên ngoài | Không tự bật thuật toán theo metadata không tin cậy |
| Chuyển đổi tài liệu | Giữ nguyên bản gốc, tạo bản mới được ký bằng profile hiện hành |

Không mở rộng allowlist trực tuyến chỉ để đọc archive. Nếu buộc phải hỗ trợ thuật toán legacy, cô lập verifier, giới hạn dữ liệu, key và mục đích, đồng thời có ngày kết thúc hỗ trợ.

## 14. Ciphertext cũ và migration sang AEAD

Ciphertext được tạo bằng thuật toán hoặc mode cũ có thể cần giải mã trong nhiều năm. Không thể chỉ xóa provider hoặc key cũ nếu dữ liệu vẫn cần đọc.

Quy trình migration điển hình:

1. Nhận diện format ciphertext, thuật toán, mode, padding, IV/nonce, tag/MAC và key version.
2. Xác định key cũ, nguồn lưu trữ và quyền giải mã.
3. Đưa decrypt legacy vào một service/worker có kiểm soát, giới hạn input và audit.
4. Xác minh integrity nếu format cũ có MAC hoặc signature.
5. Giải mã trong môi trường cô lập; không trả plaintext ra log hoặc telemetry.
6. Mã hóa lại bằng AEAD hiện hành, ví dụ AES-GCM, với nonce mới duy nhất dưới key tương ứng.
7. Ràng buộc metadata bằng AAD: tenant, object ID, schema version, purpose và key version.
8. Lưu ciphertext mới cùng version marker, cập nhật index nguyên tử và kiểm tra đọc lại.
9. Giữ bản cũ theo retention/rollback policy đã phê duyệt.
10. Chỉ retire hoặc destroy key cũ khi mọi dependency, backup và archive đã được xử lý.

Với CBC cũ không có MAC, plaintext sau decrypt chưa được xác thực. Không coi việc padding hợp lệ là bằng chứng ciphertext không bị sửa. Thiết kế migration phải hạn chế oracle, tránh trả lỗi chi tiết cho người gửi và kiểm tra integrity độc lập nếu có bằng chứng tin cậy.

### Versioned envelope

~~~~json
{
  "formatVersion": 2,
  "algorithm": "AES-256-GCM",
  "keyId": "payments-dek-2026-v2",
  "nonce": "BASE64_NONCE",
  "ciphertext": "BASE64_CIPHERTEXT_AND_TAG",
  "aadVersion": 1
}
~~~~

Envelope cần có schema rõ ràng và kiểm tra version trước khi giải mã. Không cho metadata không tin cậy tự quyết định algorithm hoặc keyId ngoài registry và allowlist. AAD phải được tái tạo đúng từ context đã xác thực; không tin tenant hoặc object ID chỉ vì chúng nằm trong envelope.

## 15. Re-encrypt, re-wrap và rotate là các công việc khác nhau

Khi thuật toán hoặc key cũ bị loại bỏ, phải xác định chính xác thao tác cần thực hiện:

| Thao tác | Thay đổi | Khi cần |
|---|---|---|
| Re-encrypt | Giải mã dữ liệu rồi mã hóa lại bằng thuật toán/key mới | Ciphertext dùng thuật toán hoặc mode cũ |
| Re-wrap | Giữ nguyên DEK/data ciphertext, chỉ bọc DEK bằng KEK mới | KEK cũ cần thay thế, DEK và data cipher vẫn đạt policy |
| Re-key | Tạo key material mới và chuyển dữ liệu sang key mới | Key cũ yếu, compromise hoặc policy yêu cầu |
| Re-sign | Tạo chữ ký mới trên nội dung được xác nhận | Chữ ký mới cần profile hiện hành |
| Re-hash password | Khi user đăng nhập hợp lệ, lưu password hash với KDF/parameters mới | Password hash legacy |
| Re-issue certificate | Cấp certificate mới theo thuật toán/key/policy hiện hành | Certificate hoặc CA profile cũ |

Re-wrap không sửa được thuật toán mã hóa dữ liệu nếu data ciphertext vẫn dùng DES hoặc AES-ECB. Re-encrypt dữ liệu không tự giải quyết việc private signing key cũ đã bị compromise. Mỗi migration phải xử lý đúng lớp crypto material.

## 16. Password hash cũ và nâng cấp KDF

Password hash thường không thể “giải mã” để chuyển đổi trực tiếp. Khi người dùng đăng nhập thành công, ứng dụng có thể kiểm tra password bằng KDF cũ rồi tính lại bằng KDF và parameters mới.

Một record password hash nên lưu:

- Tên KDF và phiên bản.
- Salt riêng, sinh ngẫu nhiên.
- Cost/iteration/memory/parallelism parameters.
- Output hash.
- Format version.

Luồng nâng cấp:

1. Đọc record và xác định KDF version bằng metadata.
2. Kiểm tra password với đúng KDF cũ và parameters cũ.
3. Nếu thất bại, từ chối đăng nhập như bình thường.
4. Nếu thành công, tạo salt mới và hash bằng profile hiện hành.
5. Ghi record mới theo transaction/CAS để tránh ghi đè thay đổi đồng thời.
6. Xóa hoặc retire format cũ theo chính sách và theo dõi số lượng account còn legacy.

Không tăng iteration count bằng cách sửa metadata nhưng giữ nguyên hash cũ. Muốn tăng cost phải tính lại từ password mà người dùng vừa cung cấp hoặc yêu cầu reset password.

Không lưu password plaintext để migration hàng loạt. Với tài khoản lâu không đăng nhập, có thể dùng reset flow hoặc giữ verifier legacy trong thời hạn có giới hạn theo policy.

## 17. Thuật toán cũ trong KeyStore và PKCS12

Keystore có thể chứa private key, certificate chain và tham số bảo vệ. Một file PKCS12 cũ có thể dùng PBE hoặc MAC algorithm yếu hơn profile mới.

Cần phân biệt:

- Thuật toán bảo vệ integrity của keystore.
- Thuật toán bảo vệ private key entry.
- Thuật toán của certificate signature.
- Thuật toán của public/private key.
- Thuật toán mà ứng dụng dùng khi ký hoặc mã hóa dữ liệu.

Một keystore được mở thành công không có nghĩa mọi certificate/key bên trong đều phù hợp policy. Ngược lại, một certificate có signature algorithm cũ không đồng nghĩa thuật toán bảo vệ container PKCS12 cũng là thuật toán đó.

Quy trình migration:

1. Inventory alias, entry type, certificate chain, key algorithm và key usage.
2. Xác định keystore integrity/PBE parameters và khả năng tương thích JDK.
3. Kiểm tra nguồn gốc trust của certificate.
4. Xác định key nào còn cần ký, decrypt hoặc verify dữ liệu lịch sử.
5. Tạo keystore mới theo profile được phê duyệt.
6. Chuyển key/certificate bằng công cụ được kiểm soát, giữ quyền truy cập tối thiểu.
7. Kiểm tra alias, chain, permissions và khả năng thực hiện operation.
8. Triển khai song song có thời hạn, theo dõi lỗi và sau đó retire file cũ.

Không xuất private key ra file tạm hoặc log để “chuyển nhanh”. Nếu key nằm trong HSM, dùng cơ chế migration/backup được HSM hỗ trợ và giữ nguyên non-exportability policy.

## 18. TLS và thuật toán bị disabled

TLS có thương lượng protocol version, cipher suite, signature scheme, group/key exchange và certificate chain. Một thuật toán có thể bị loại khỏi handshake bởi JDK security property hoặc policy của TLS provider.

Các property như `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` có thể ảnh hưởng tới các phần khác nhau của handshake:

- Protocol version quá cũ.
- Cipher suite hoặc bulk cipher yếu.
- Hash/signature algorithm không còn được phép.
- RSA key size hoặc DH group không đạt ngưỡng.
- Named curve bị loại.
- Certificate path chứa thuật toán hoặc key không được phép.

Một kết nối có thể thất bại dù ứng dụng gọi đúng hostname và trust store chứa CA. Cần đọc lỗi handshake, cấu hình TLS, certificate chain, server capability và security property.

Không giải quyết bằng cách bỏ toàn bộ `jdk.tls.disabledAlgorithms` hoặc bật TLS version cũ cho mọi kết nối. Nếu một đối tác legacy cần hỗ trợ tạm thời, tạo phạm vi ngoại lệ hẹp, có owner, giới hạn endpoint, thời hạn và kiểm toán. Tốt nhất là nâng cấp endpoint đối tác.

## 19. Crypto agility và protocol version

Crypto agility là khả năng thay đổi thuật toán và tham số mà không phải viết lại toàn bộ hệ thống hoặc làm mất khả năng đọc dữ liệu.

Một thiết kế có crypto agility cần:

- Version format và protocol.
- Algorithm identifier nằm trong registry/allowlist.
- Key identifier và key version rõ ràng.
- Parameters được định nghĩa chính xác.
- Quy tắc migration và retirement.
- Cơ chế tương thích có thời hạn.
- Test vectors và interoperability tests.
- Audit và telemetry về thuật toán đang được dùng.

Không để sender tự chọn tùy ý thuật toán bằng một trường JSON rồi verifier tin theo. Server phải kiểm tra algorithm ID trong policy đã cấu hình cho tenant, purpose và protocol version.

### Ngăn downgrade

Nếu client và server hỗ trợ nhiều profile, kẻ tấn công có thể cố ép hai bên chọn profile yếu hơn. Cần:

- Định nghĩa minimum acceptable version.
- Bảo vệ negotiation transcript theo thiết kế protocol.
- Không retry bằng thuật toán yếu hơn sau lỗi xác minh.
- Không dùng “thử lần lượt mọi thuật toán” làm chiến lược tương thích.
- Ghi nhận profile đã thương lượng và từ chối downgrade trái policy.

Fallback phải là quyết định cấu hình rõ ràng, không phải phản ứng tự động trước lỗi mật mã.

## 20. Lộ trình loại bỏ thuật toán deprecated

Một migration nên được chia thành các giai đoạn có thể đo lường.

~~~~mermaid
flowchart TD
    A[Inventory crypto usage]
    B[Classify risk and data]
    C[Define approved profiles]
    D[Deploy readers/verifiers for new format]
    E[Switch writers to new algorithm]
    F[Migrate stored data and keys]
    G[Measure legacy usage]
    H[Disable legacy operations]
    I[Retire old keys/providers]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~~

### Giai đoạn 1: Inventory

Tìm thuật toán trong:

- Source code và dependency.
- Configuration, environment và JVM flags.
- Keystore, trust store và certificate.
- Database metadata và ciphertext envelope.
- Message queue, event archive và backup.
- TLS endpoint, webhook và giao thức đối tác.
- HSM/KMS key policy và signing service.
- Password hash record và tài liệu ký số.

Ghi lại operation, algorithm, mode, padding, key size, parameters, provider, key ID, data owner, retention và consumer.

### Giai đoạn 2: Phân loại

Mỗi mục được phân loại theo:

- New write hay historical read.
- Mức nhạy cảm và thời gian cần bảo vệ.
- Có thể re-encrypt/re-sign/re-hash không.
- Key còn tồn tại và có thể truy cập không.
- Có phụ thuộc đối tác hoặc thiết bị không.
- Rủi ro khi tiếp tục hỗ trợ.
- Hạn cuối để loại bỏ.

### Giai đoạn 3: Triển khai reader mới

Deploy reader/verifier hỗ trợ format mới trước khi chuyển writer. Kiểm tra khả năng đọc cả format mới và format cũ theo policy. Không mở rộng legacy support ngoài đúng dataset hoặc endpoint đã inventory.

### Giai đoạn 4: Chuyển writer

Chuyển mọi dữ liệu mới sang profile hiện hành. Theo dõi telemetry để xác nhận không còn operation mới dùng thuật toán deprecated.

### Giai đoạn 5: Migration dữ liệu

Re-encrypt, re-wrap, re-sign hoặc re-hash theo đúng loại dữ liệu. Dùng batch, idempotency, version marker và compare-and-set để tránh mất dữ liệu khi worker chạy lại hoặc có ghi đồng thời.

### Giai đoạn 6: Disable và retire

Khi legacy usage bằng 0 hoặc nằm trong ngoại lệ được phê duyệt, disable operation cũ. Sau khi kiểm tra backup, archive, restore và legal hold, mới retire key/provider hoặc xóa dữ liệu theo policy.

## 21. Java migration example: chỉ cho phép profile hiện hành

Ví dụ sau minh họa cách ánh xạ protocol profile sang thuật toán được phép. Dữ liệu bên ngoài chỉ mang profile ID; server tự quyết định thuật toán.

~~~~java
import java.security.GeneralSecurityException;
import java.security.Signature;
import java.util.Map;

public final class SignatureProfileRegistry {
    private static final Map<String, String> APPROVED =
            Map.of(
                    "signature-v2-ed25519", "Ed25519",
                    "signature-v2-rsa-pss", "RSASSA-PSS"
            );

    private SignatureProfileRegistry() {
    }

    public static Signature create(String profileId)
            throws GeneralSecurityException {
        String algorithm = APPROVED.get(profileId);

        if (algorithm == null) {
            throw new GeneralSecurityException(
                    "Unknown or disallowed signature profile"
            );
        }

        return Signature.getInstance(algorithm);
    }
}
~~~~

Ví dụ chưa cấu hình tham số PSS hoặc kiểm tra key size. Đây là trách nhiệm bắt buộc của profile hoàn chỉnh. Registry thực tế nên chứa algorithm, parameter set, minimum key size, key purpose, data format version và trạng thái lifecycle.

Không cho phép request truyền chuỗi như `SHA1withRSA` để bypass registry. Nếu client yêu cầu profile cũ, server phải từ chối hoặc route sang archival verifier được cô lập và có policy riêng.

## 22. Ví dụ migration ciphertext theo version

Ví dụ minh họa envelope có version và allowlist thuật toán. Phần giải mã legacy cần được triển khai trong service migration riêng; code không tự động chọn thuật toán tùy ý từ dữ liệu.

~~~~java
import java.security.GeneralSecurityException;
import java.util.Map;

public final class CiphertextFormatPolicy {
    private static final Map<Integer, String> APPROVED_NEW_FORMATS =
            Map.of(
                    2, "AES/GCM/NoPadding"
            );

    private CiphertextFormatPolicy() {
    }

    public static String requireNewWriteAlgorithm(int formatVersion)
            throws GeneralSecurityException {
        String algorithm = APPROVED_NEW_FORMATS.get(formatVersion);

        if (algorithm == null) {
            throw new GeneralSecurityException(
                    "Format version is not approved for new writes"
            );
        }

        return algorithm;
    }

    public static void requireReadableVersion(
            int formatVersion,
            boolean archivalMigrationContext
    ) throws GeneralSecurityException {
        if (formatVersion == 2) {
            return;
        }

        if (formatVersion == 1 && archivalMigrationContext) {
            return;
        }

        throw new GeneralSecurityException(
                "Legacy format is not accepted in this context"
        );
    }
}
~~~~

Đoạn code chỉ là policy gate, không phải implementation mã hóa. Production phải xác minh format metadata, key reference, AAD, nonce/tag, tenant và authorization. Một flag boolean từ request không đủ để chứng minh caller được phép vào archival migration context; quyền đó phải đến từ service identity và policy server-side.

## 23. Xử lý key cũ và key compromise

Thuật toán yếu và key bị compromise là hai vấn đề khác nhau:

- Thuật toán deprecated có thể vẫn dùng được để giải mã dữ liệu cũ nếu key chưa bị lộ và policy cho phép.
- Key compromise có thể khiến ciphertext, chữ ký hoặc MAC bị mất tính tin cậy dù thuật toán vẫn mạnh.
- Một thuật toán mạnh không cứu được key có entropy thấp hoặc bị lộ.
- Re-wrap một DEK không khắc phục việc chính DEK đã bị lộ.
- Re-sign bằng key mới không tự chứng minh tài liệu gốc chưa bị sửa trước migration.

Khi key cũ bị compromise, cần incident response:

1. Xác định key ID, provider, operation và thời gian bị ảnh hưởng.
2. Cô lập quyền sử dụng key và ngăn tạo dữ liệu mới.
3. Xác định ciphertext, signature, MAC, backup và archive phụ thuộc.
4. Đánh giá tính toàn vẹn và nguồn gốc của dữ liệu cũ.
5. Tạo key mới theo policy và cập nhật key registry.
6. Re-encrypt hoặc re-sign dữ liệu có thể phục hồi từ nguồn tin cậy.
7. Thu hồi certificate hoặc key binding nếu phù hợp.
8. Lưu evidence, audit và quyết định xử lý lịch sử.

Không xóa key cũ ngay nếu dữ liệu lịch sử vẫn cần decrypt hoặc verify, trừ khi compromise yêu cầu cô lập/destruction theo incident policy. Có thể cần giữ bản sao trong vùng recovery được kiểm soát, với quyền sử dụng hạn chế và audit nghiêm ngặt.

## 24. Telemetry và bằng chứng migration

Để loại bỏ thuật toán cũ, cần đo được việc sử dụng thực tế.

Các metric hữu ích:

- Số operation theo algorithm/profile/provider.
- Số lần ký mới bằng profile hiện hành.
- Số lần verifier gặp signature legacy.
- Số object/ciphertext còn theo format cũ.
- Số password hash còn dùng KDF version cũ.
- Số key cũ còn decrypt/unwrap.
- Tỷ lệ migration thành công/thất bại.
- Số lỗi interoperability theo đối tác.
- Số request bị từ chối do deprecated algorithm hoặc downgrade.
- Số endpoint TLS còn thương lượng protocol/cipher yếu.

Log nên ghi algorithm ID, profile version, key ID đã được phép log, operation, caller identity và kết quả. Không log raw key, password, secret, plaintext hoặc toàn bộ dữ liệu nhạy cảm.

Một migration chỉ nên đóng khi đã kiểm tra cả primary data, replica, backup, archive, DR restore và consumer ít hoạt động. Một dashboard không có traffic trong 30 ngày chưa chắc chứng minh không còn dữ liệu cần giải mã sau nhiều năm.

## 25. Lỗi phổ biến khi loại bỏ thuật toán cũ

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getInstance` thành công nhưng security review từ chối | Provider có implementation nhưng policy cấm | Thêm allowlist và kiểm tra key/parameters |
| TLS handshake thất bại sau nâng JDK | Disabled algorithm hoặc protocol policy thay đổi | Đọc security property và nâng cấp peer |
| Chữ ký archive không xác minh được | Digest/signature cũ hoặc certificate chain không còn hợp lệ | Dùng archival validation policy và evidence lịch sử |
| Không giải mã được dữ liệu cũ | Key version hoặc provider cũ không còn | Khôi phục dependency và chạy migration có kiểm soát |
| Migration tạo ciphertext không đọc được | AAD, nonce, tag hoặc format version không nhất quán | Chuẩn hóa envelope và test round-trip |
| Password hash cũ vẫn tồn tại | Account chưa đăng nhập lại | Dùng reset flow hoặc deadline theo policy |
| Đối tác ép thuật toán yếu | Negotiation cho phép downgrade | Giới hạn profile và từ chối retry yếu |
| HSM không hỗ trợ thuật toán mới | Capability hoặc firmware/provider chưa phù hợp | Nâng cấp thiết bị/provider hoặc thiết kế phương án thay thế được phê duyệt |
| Một service vẫn ký bằng thuật toán cũ | Config/secret alias chưa được cập nhật | Inventory runtime, deploy policy và monitor operation |
| Rollback release làm bật lại thuật toán cũ | Legacy config được khôi phục cùng application | Tách policy control khỏi release rollback và bảo vệ minimum version |

Không sửa lỗi bằng cách bật lại tất cả thuật toán cũ. Xác định chính xác operation, peer, data format và key dependency trước khi quyết định ngoại lệ.

## 26. Checklist triển khai

### Inventory và policy

- [ ] Liệt kê thuật toán trong code, config, protocol, key store, KMS/HSM và dữ liệu lưu trữ.
- [ ] Ghi đủ primitive, mode, padding, key size và parameters.
- [ ] Phân loại deprecated, legacy, weak, disabled và prohibited.
- [ ] Có owner, data classification và retention cho mỗi dependency.
- [ ] Có allowlist theo operation và protocol version.
- [ ] Có ngưỡng key size, curve, nonce, tag và KDF cost.
- [ ] Đọc đúng Java security property của runtime production.

### Migration

- [ ] Reader mới được triển khai và kiểm thử trước writer.
- [ ] Writer mới chỉ dùng profile hiện hành.
- [ ] Ciphertext có format version, key ID và AAD rõ ràng.
- [ ] Password hash có migration-on-login hoặc reset plan.
- [ ] Chữ ký lịch sử được xử lý trong luồng archival riêng.
- [ ] Re-encrypt, re-wrap, re-sign và re-key được phân biệt.
- [ ] Migration có batch, idempotency, CAS và kiểm tra round-trip.
- [ ] Có rollback plan không làm tái bật thuật toán yếu.

### Vận hành và loại bỏ

- [ ] Telemetry cho biết còn operation legacy hay không.
- [ ] Kiểm tra replica, backup, archive và DR.
- [ ] Có kế hoạch cho đối tác và thiết bị HSM/KMS.
- [ ] Có deadline và owner cho ngoại lệ.
- [ ] Có test ngăn downgrade và fallback yếu.
- [ ] Chỉ retire key/provider khi dependency đã được xử lý.
- [ ] Lưu audit evidence và quyết định phê duyệt.

## 27. Câu hỏi tự kiểm tra

**1. Deprecated algorithm có nghĩa là JDK đã xóa implementation không?**

Không. Thuật toán có thể vẫn tồn tại để tương thích; trạng thái deprecated là tín hiệu cần ngừng dùng cho mục đích mới.

**2. `Signature.getInstance("SHA1withRSA")` thành công có chứng minh SHA1withRSA được phép không?**

Không. Nó chỉ cho biết provider tìm được implementation. Ứng dụng cần policy và runtime enforcement riêng.

**3. Deprecated khác disabled thế nào?**

Deprecated là trạng thái khuyến cáo ngừng dùng; disabled là bị chặn trong một phạm vi runtime hoặc policy cụ thể.

**4. Vì sao MD5 và SHA-1 không phù hợp cho chữ ký mới?**

Collision attack làm suy yếu khả năng ràng buộc chữ ký với đúng nội dung dự kiến.

**5. AES có bị deprecated chỉ vì ứng dụng dùng ECB không?**

Không. AES là primitive; ECB là mode. Cần thay mode không an toàn bằng AEAD phù hợp.

**6. `jdk.tls.disabledAlgorithms` có chặn mọi lời gọi Cipher trong JCA không?**

Không. Property này chủ yếu áp dụng trong ngữ cảnh TLS; không phải allowlist toàn cục cho mọi JCA operation.

**7. Provider inventory có phải allowlist bảo mật không?**

Không. Inventory mô tả implementation có sẵn; allowlist phải được phê duyệt theo policy.

**8. Vì sao cần kiểm tra key size và parameters ngoài tên thuật toán?**

Cùng thuật toán có thể dùng key hoặc parameters không đủ mạnh.

**9. Có thể tiếp tục xác minh chữ ký SHA-1 lịch sử không?**

Chỉ khi có policy archival riêng, nguồn gốc và bằng chứng lịch sử phù hợp; không mở nó cho giao dịch mới.

**10. Re-wrap có thay đổi data ciphertext không?**

Thông thường không. Re-wrap thay lớp bảo vệ DEK bằng KEK mới; nếu data cipher cũ yếu thì cần re-encrypt.

**11. Có thể chuyển password hash cũ bằng cách thay tên KDF trong database không?**

Không. Phải có password người dùng sau lần xác thực thành công hoặc yêu cầu reset để tính hash mới.

**12. Vì sao không bật lại mọi thuật toán yếu khi TLS handshake thất bại?**

Làm vậy mở rộng bề mặt tấn công cho mọi kết nối dùng runtime và có thể cho phép downgrade.

**13. Vì sao phải version ciphertext format?**

Để xác định đúng algorithm, parameters, key reference và quy trình giải mã/migration.

**14. Metadata algorithm do client gửi có thể được tin trực tiếp không?**

Không. Server phải kiểm tra profile trong allowlist và áp dụng policy theo context.

**15. Khi nào được retire key cũ?**

Khi mọi dependency gồm primary data, replica, backup, archive và DR đã được xử lý hoặc có ngoại lệ được phê duyệt.

**16. Key compromise khác thuật toán deprecated như thế nào?**

Deprecated là vấn đề của primitive/profile; compromise là bí mật hoặc quyền sử dụng key đã bị lộ. Cách xử lý có thể khác nhau.

**17. Vì sao cần triển khai reader mới trước writer mới?**

Để mọi consumer có thể đọc format mới trước khi dữ liệu mới được tạo ra.

**18. Crypto agility là gì?**

Khả năng thay thuật toán, key và parameters theo policy mà không làm mất khả năng đọc dữ liệu hoặc liên thông.

**19. Fallback sang thuật toán yếu hơn sau lỗi có an toàn không?**

Không. Fallback phải được cấu hình và phê duyệt rõ; không tự động hạ cấp khi có lỗi.

**20. Khi nào migration được coi là hoàn tất?**

Khi writer mới đã chuyển đổi, legacy usage được xử lý, dữ liệu/backup/archive được kiểm tra và các operation cũ đã được disable theo kế hoạch.

## 28. Tài liệu tham khảo

- Java SE 17 Security Developer's Guide: JCA, provider, security properties và thuật toán.
- Java Cryptography Architecture (JCA) Reference Guide: provider architecture và API.
- Java Security Standard Algorithm Names: tên chuẩn cho Cipher, Signature, MessageDigest, Mac và KeyAgreement.
- Java SE 17 `java.security.AlgorithmConstraints`: kiểm tra thuật toán, key và parameters trong các ngữ cảnh hỗ trợ.
- NIST SP 800-131A Rev. 2 — Transitioning the Use of Cryptographic Algorithms and Key Lengths.
- NIST SP 800-57 Part 1 — Recommendation for Key Management.
- NIST SP 800-56A/56B — Recommendation for Pair-Wise Key-Establishment Schemes.
- RFC 8017 — PKCS #1: RSA Cryptography Specifications.
- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3.
- Tài liệu JDK vendor/provider/HSM đang triển khai, đặc biệt về disabled algorithms, key size và compatibility.

