# Sinh key pair — Tạo cặp khóa công khai và bí mật an toàn

## 1. Key pair là gì và vì sao phải sinh đúng cách?

**Key pair (cặp khóa)** trong mật mã bất đối xứng gồm **public key (khóa công khai)** và **private key (khóa bí mật/khóa riêng)** có quan hệ toán học theo thuật toán. Public key có thể được phân phối rộng rãi qua một cơ chế đáng tin cậy; private key phải được bảo vệ để chỉ chủ thể được phép mới có thể thực hiện thao tác nhạy cảm.

Ví dụ, hệ thống Java phát hành chứng từ điện tử cần ký bằng private key và cho đối tác xác minh bằng public key. Việc **sinh key pair** là lúc tạo ra vật liệu khóa và các tham số cần thiết. Nhưng tạo ra hai đối tượng trong Java chỉ mới là **bước khởi đầu**: ứng dụng còn phải xác định mục đích, thuật toán, độ mạnh, nguồn ngẫu nhiên, nơi lưu private key, cách phân phối và xác thực public key, quyền sử dụng, xoay vòng và thu hồi.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, thuộc chương **Key generation**, sinh key pair là bước đầu trong vòng đời khóa **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Nếu khóa được sinh yếu, bị sao chép trái phép hoặc dùng sai mục đích, các lớp bảo vệ ở phía sau như **KMS/HSM, chữ ký số, TLS, envelope encryption và audit** không thể tự sửa mọi hậu quả.

**Ba nguyên tắc cốt lõi:**

1. **Private key là bí mật:** Không ghi vào log, source code, ticket, bản build hay message; nếu cần lưu hoặc chuyển, dùng cơ chế bảo vệ được phê duyệt.
2. **Public key có thể công khai nhưng phải xác thực nguồn:** Việc public key parse thành công không chứng minh nó thuộc đúng người nhận hoặc người ký.
3. **Sinh đúng theo key usage:** Một cặp khóa để **Sign/Verify**, một cặp để **Encrypt/Decrypt**, và cặp cho **key agreement** không có cùng giao diện hoặc giả định an toàn.

### 1.1. Khóa công khai và khóa bí mật làm gì?

| Nhiệm vụ | Private key dùng để | Public key dùng để | Điều không tự được bảo đảm |
| --- | --- | --- | --- |
| **Chữ ký số** | Ký thông điệp/tài liệu | Xác minh chữ ký | Verify đúng không tự xác định người ký có quyền nghiệp vụ |
| **Mã hóa bất đối xứng** | Giải mã bí mật được mã hóa cho mình | Mã hóa hoặc encapsulate bí mật cho người nhận | Public key phải đúng chủ thể nhận; không tự chống replay |
| **Thỏa thuận khóa** | Kết hợp với public key đối tác để tính shared secret | Được trao cho đối tác trong giao thức | DH/ECDH thuần túy không tự xác thực peer |

**Không có một phép toán chung “mã hóa bằng private key, giải mã bằng public key” cho mọi hệ mật mã.** Chữ ký số là primitive riêng với xác minh chữ ký, chứ không phải cách mã hóa dữ liệu nhạy cảm bằng private key.

### 1.2. Key pair khác DEK/KEK đối xứng

- **DEK (Data Encryption Key)** thường là khóa đối xứng như AES, dùng mã hóa dữ liệu lớn bằng AEAD, ví dụ AES-GCM.
- **KEK (Key Encryption Key)** bảo vệ DEK hoặc khóa con bằng key wrapping hay cơ chế thích hợp.
- **Key pair bất đối xứng** có thể giúp xác thực, bảo vệ một bí mật nhỏ hoặc thiết lập shared secret để dẫn xuất khóa đối xứng.

Trong **hybrid/envelope encryption**, một ứng dụng có thể tạo DEK AES mới, mã hóa dữ liệu bằng DEK, rồi bảo vệ DEK bằng khóa phù hợp ở KMS/HSM hoặc public key người nhận. **Không dùng RSA để mã hóa trực tiếp file lớn**; và **không coi ECDH là hàm mã hóa dữ liệu**.

## 2. Chọn thuật toán trước khi sinh key pair

Một API tên **KeyPairGenerator** chưa cho biết khóa dùng để làm gì. Cần chọn primitive dựa trên mục tiêu và tiêu chuẩn bảo mật hiện hành của tổ chức.

| Thuật toán / họ | Mục đích điển hình | Cặp khóa tạo ra | Lưu ý triển khai |
| --- | --- | --- | --- |
| **RSA** | RSA-PSS để ký; RSA-OAEP để bảo vệ bí mật nhỏ | RSA public modulus/exponent và private key | Dùng padding/parameters chuẩn; tách key usage nếu chính sách yêu cầu |
| **ECDSA trên P-256/P-384** | Chữ ký số | EC public point và private scalar | Cần curve hợp lệ; nonce ký ECDSA phải đúng, ưu tiên provider uy tín |
| **Ed25519** | Chữ ký số hiện đại | Ed25519 signing key pair | **Không phải X25519** và không dùng trực tiếp cho ECDH |
| **ECDH trên P-256/P-384** | Thỏa thuận khóa | EC private key và public point | Cần xác thực peer và sử dụng KDF |
| **X25519** | Thỏa thuận khóa kiểu Montgomery | Private scalar và public X25519 | Không phải Ed25519 signing; kiểm tra shared secret toàn số 0 |
| **X448** | Thỏa thuận khóa | Key pair X448 | Tương thích provider/giao thức và độ mạnh khác X25519 |
| **ML-KEM** | KEM hậu lượng tử để thiết lập bí mật | Encapsulation/public key và decapsulation/private key | Không phải Diffie-Hellman; cần thư viện, tiêu chuẩn và giao thức tương thích |
| **ML-DSA/SLH-DSA** | Chữ ký số hậu lượng tử | Cặp khóa ký/xác minh tương ứng | Không dùng như khóa ECDH hoặc RSA-OAEP |

**Lưu ý về hậu lượng tử:** Việc JDK hoặc KMS/HSM có hỗ trợ ML-KEM/ML-DSA hay không **phụ thuộc phiên bản và provider**. Không viết mã giả định mọi Java runtime đều có các thuật toán đó. Chọn tiêu chuẩn và giao thức theo chính sách **crypto agility** của tổ chức.

### 2.1. Độ dài khóa không thể so theo số byte đơn thuần

| Ví dụ cấu hình | Mức bảo mật cổ điển gần đúng | Ghi chú |
| --- | --- | --- |
| **RSA-2048** | Khoảng 112 bit | Một số môi trường chấp nhận cho tương thích; đánh giá vòng đời và chính sách |
| **RSA-3072** | Khoảng 128 bit | Lựa chọn minh họa cho hệ thống RSA hiện đại |
| **P-256 / X25519 / Ed25519** | Khoảng 128 bit | Khác nhau về phép toán và key usage, không phải khóa AES-256 |
| **P-384** | Khoảng 192 bit | Trade-off hiệu năng/tương thích khác P-256 |

Các con số là **ước lượng sức mạnh tấn công cổ điển**, không phải cam kết trước tấn công lượng tử. **AES-256** có key length 256 bit nhưng không có nghĩa public key 32 byte X25519 cho 256 bit security. Khóa RSA dài hàng nghìn bit cũng không thể so trực tiếp với khóa elliptic curve ngắn hơn.

### 2.2. Không dùng một cặp khóa tùy tiện cho mọi mục đích

Một cặp RSA có thể có nhiều primitive toán học liên quan, nhưng **dùng cùng private key cho ký và giải mã** làm phức tạp chính sách, phân quyền, rotation và phân tích an toàn. Nên tách key usage theo mục đích, nhất là đối với private key quan trọng.

**Ed25519 dùng ký**, **X25519 dùng thỏa thuận khóa**: chúng không thể thay thế cho nhau chỉ vì cùng liên quan đến họ Curve25519. Không tự chuyển đổi định dạng giữa private keys để tái sử dụng nếu không có một giao thức đã được đánh giá riêng.

## 3. Đặc tả yêu cầu trước khi sinh khóa

Trước một thao tác GenerateKeyPair, cần có **key generation request** mô tả rõ:

1. **Owner/tenant/environment:** Ai sở hữu, khóa dùng cho production hay test, vùng KMS nào và phạm vi dữ liệu.
2. **Purpose/allowed operations:** Sign, Verify, Decrypt, DeriveKey hoặc một phép toán khác. Hạn chế thao tác theo chính sách.
3. **Algorithm/parameters:** RSA 3072 với public exponent phù hợp, EC P-256, Ed25519 hoặc X25519; tránh mặc định provider mơ hồ.
4. **Security level/lifetime:** Độ mạnh, thời hạn hiệu lực và thời hạn dữ liệu cần bảo vệ. Khóa ký tài liệu cần xét khả năng xác minh lâu dài.
5. **Storage boundary:** Private key có thể xuất hay phải **non-exportable** trong HSM/KMS? Có backup được kiểm soát không?
6. **Provisioning/authentication:** Ai nhận public key, qua certificate/CSR, trusted JWKS hay pinning? Ai có quyền dùng private key?
7. **Rotation/revocation:** Bao giờ thay, ứng dụng xử lý key ID/version và chứng chỉ/keys cũ thế nào?
8. **Recovery/destruction:** Trường hợp mất private key, còn dữ liệu nào cần giải mã hoặc chữ ký nào cần Verify?
9. **Evidence/audit:** Làm sao biết khóa đã được sinh từ nguồn được duyệt và chỉ được sử dụng đúng phạm vi?

### 3.1. Ví dụ bản mô tả chính sách

~~~yaml
# Mẫu minh họa, không phải schema của một KMS cụ thể.
keyGenerationRequest:
  owner: billing-platform
  environment: production
  purpose: sign-invoice-event
  algorithm: Ed25519
  allowedOperations: [Sign]
  privateKeyLocation: managed-hsm
  exportPrivateKey: false
  publicKeyDistribution: trusted-signer-registry
  keyId: billing-signer-v3
  lifecycle:
    activationRequiresApproval: true
    rotationRunbook: billing-signing-rotation
    revocationOnCompromise: true
  audit:
    recordPrincipalAndKeyId: true
    neverLogPrivateKey: true
~~~

Phải hiểu **tính không xuất khóa** theo khả năng thực tế của dịch vụ; không phải nhà cung cấp nào cũng hỗ trợ Ed25519 hoặc private key non-exportable với cùng API. Nếu lựa chọn này không được hỗ trợ, thiết kế phải thay đổi phù hợp, không chuyển private key sang một file không được bảo vệ rồi giữ nguyên nhãn “HSM”.

## 4. Nguồn ngẫu nhiên và entropy

Private key không nên được chọn từ các giá trị dễ dự đoán. **Cryptographically Secure Pseudorandom Number Generator (CSPRNG)** hoặc **DRBG** được thẩm định là thành phần quan trọng khi sinh key pair.

### 4.1. Vì sao khóa mới có thể yếu ngay khi vừa tạo?

Một cặp khóa có thể đúng kích thước nhưng không đạt bảo mật nếu:

- Private key được tạo bằng **Math.random**, **java.util.Random**, timestamp hoặc một seed ngắn đoán được.
- Hệ thống tạo nhiều khóa bằng **cùng trạng thái RNG bị khôi phục từ snapshot** không được quản lý đúng.
- Generator/provider đã cấu hình sai hoặc thiếu nguồn entropy đáng tin cậy.
- Private exponent bị lưu vào log, crash dump hoặc CI artifact ngay trong quá trình tạo.
- Cặp khóa được **nhân bản sang nhiều tenant/môi trường** nhưng inventory ghi như các khóa độc lập.

**Không tự seed SecureRandom bằng thời gian hệ thống rồi coi đó là entropy tốt.** Trong Java hiện đại, để provider/hệ điều hành thực hiện việc khởi tạo RNG theo thiết kế; môi trường yêu cầu FIPS/HSM phải tuân thủ chính sách và tài liệu của provider được phê duyệt.

### 4.2. CSPRNG tốt không thay kiểm soát private key

Ngay cả khi KeyPairGenerator tạo private key khó đoán, một debug log ghi **private.getEncoded()** vẫn có thể làm lộ toàn bộ khóa. An toàn cần kết hợp **generation, storage, distribution, access control và audit**.

### 4.3. Test có cần khóa cố định không?

Một unit test có thể dùng **public test fixture** được quản lý riêng khi thật sự cần test vector tái lập. Tuy nhiên:

- Không đưa private key test vào production; không dùng khóa demo làm khóa thật.
- Không đưa custom deterministic RNG yếu vào code sinh khóa production.
- Kiểm thử đúng hơn là kiểm tra **API, key usage, generation errors, verification và rotation**, thay vì khẳng định hai lần chạy phải tạo cùng một private key.
- Không dùng **private key mới mỗi lần test** như bằng chứng duy nhất cho entropy. Đánh giá RNG/provider phải theo tiêu chuẩn và thiết kế thực tế.

## 5. Quy trình tạo và kích hoạt một key pair

Một key pair được sinh **không tự động trở thành khóa đang hoạt động**. Cần tách các bước tạo, xác minh, đăng ký và kích hoạt:

~~~mermaid
flowchart TD
    REQ["Yêu cầu sinh key pair<br/>owner, purpose, algorithm, environment"] --> REVIEW["Kiểm tra policy, provider,<br/>KMS/HSM và quyền phê duyệt"]
    REVIEW --> GEN["CSPRNG / KMS-HSM tạo key pair"]
    GEN --> PROTECT["Bảo vệ private key;<br/>chỉ công bố public material"]
    PROTECT --> TEST["Kiểm tra cấu trúc, self-test,<br/>key ID và key usage"]
    TEST --> REGISTER["Key inventory + trạng thái PRE_ACTIVE<br/>audit metadata"]
    REGISTER --> TRUST["Cấp phát public key có xác thực:<br/>certificate/JWKS/trusted registry"]
    TRUST --> ACT["Phê duyệt và ACTIVE<br/>cho đúng workload/operation"]
    ACT --> MON["Theo dõi usage, rotation,<br/>revocation và destruction"]
~~~

### 5.1. Sinh, kiểm tra, công bố, kích hoạt

**Sinh khóa:** KMS/HSM hoặc provider tạo cặp khóa theo thuật toán được chọn. Private key **không gửi qua đường mạng** nếu thiết kế non-exportable.

**Kiểm tra:** Xác minh thuật toán/curve, độ mạnh, key usage, khả năng thực hiện thử nghiệm Sign/Verify hoặc KeyAgreement và tính hợp lệ theo API. Không tự kiểm tra bằng cách xuất raw key khỏi HSM nếu HSM có API thử nghiệm phù hợp.

**Công bố:** Public key được đăng ký qua **kênh tin cậy**, có thể thành một CSR rồi được CA cấp chứng chỉ, hoặc được đưa vào JWKS/trust registry do issuer quản lý.

**Kích hoạt:** Chỉ workload được phép mới có thể Sign/Derive/Decrypt. Việc kích hoạt có thể gắn với chứng chỉ hợp lệ, phiên bản ứng dụng và mốc chuyển đổi.

**Ghi nhận:** Key inventory lưu **key ID/version, algorithm, environment, owner, state, resource reference, createdAt và policy**; không ghi raw private key hoặc shared secret.

## 6. Java 17: sinh RSA, EC, Ed25519 và X25519 key pair

Java cung cấp **Java Cryptography Architecture (JCA)** với **KeyPairGenerator**, **KeyPair**, **PublicKey** và **PrivateKey**. Với các provider hỗ trợ, ứng dụng có thể sinh cặp khóa trong bộ nhớ. Ví dụ sử dụng **Java 17+** để minh họa các loại khóa khác nhau; kiểm tra runtime/provider thực tế trước khi triển khai.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.RSAKeyGenParameterSpec;
import java.util.Base64;

public final class GenerateKeyPairsDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private GenerateKeyPairsDemo() {}

    static KeyPair createRsa3072() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(
                new RSAKeyGenParameterSpec(
                        3072, RSAKeyGenParameterSpec.F4),
                RNG);
        return generator.generateKeyPair();
    }

    static KeyPair createEcP256() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
                new ECGenParameterSpec("secp256r1"), RNG);
        return generator.generateKeyPair();
    }

    static KeyPair createEd25519() throws Exception {
        // Chữ ký số Ed25519; provider quản lý việc sinh seed thích hợp.
        return KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
    }

    static KeyPair createX25519() throws Exception {
        // Thỏa thuận khóa X25519, KHÔNG dùng như key ký Ed25519.
        return KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();
    }

    static String publicKeyFingerprint(KeyPair pair) throws Exception {
        byte[] spki = pair.getPublic().getEncoded();
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(spki);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(digest);
    }

    static boolean signAndVerify(KeyPair pair, byte[] message)
            throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signed = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPair rsa = createRsa3072();
        KeyPair ec = createEcP256();
        KeyPair ed = createEd25519();
        KeyPair x = createX25519();

        System.out.println("RSA: " + rsa.getPublic().getAlgorithm());
        System.out.println("EC: " + ec.getPublic().getAlgorithm());
        System.out.println("Ed25519: " + ed.getPublic().getAlgorithm());
        System.out.println("X25519: " + x.getPublic().getAlgorithm());

        byte[] message = "Hoa don so 42"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Ed25519 verify: " +
                signAndVerify(ed, message));

        // Chỉ fingerprint PUBLIC KEY. Không log private key/seed.
        System.out.println("Public key fingerprint: " +
                publicKeyFingerprint(ed));
    }
}
~~~

**Kết quả minh họa:** Chương trình sinh bốn cặp khóa, thao tác **Ed25519 Verify trả true**, in tên thuật toán do provider biểu diễn và một fingerprint public key có thể khác mỗi lần chạy. Không có giá trị private key nào được in ra.

### 6.1. Giải thích từng API

1. **KeyPairGenerator.getInstance("RSA")** chọn dịch vụ sinh RSA key pair của provider.
2. **RSAKeyGenParameterSpec(3072, F4)** chỉ rõ kích thước RSA và public exponent thông dụng; không để mặc định kích thước theo provider.
3. **ECGenParameterSpec("secp256r1")** chọn **P-256**; không nhầm độ dài điểm public key với độ mạnh bảo mật.
4. **Ed25519** tạo cặp signing key dùng cho chữ ký số; đối với Java 17 phổ biến, provider nền tảng có hỗ trợ. Với FIPS hoặc HSM phải xác minh thuật toán được cho phép.
5. **X25519** tạo key pair cho key agreement, **không thay Ed25519 trong Signature**.
6. **Signature.initSign** dùng private Ed25519 key, **initVerify** dùng public key. Không tự lấy private bytes rồi ký bằng một phép băm tự chế.
7. **PublicKey.getEncoded()** thường tạo **SubjectPublicKeyInfo (SPKI)** cho các kiểu khóa JCA này. Đây là **định dạng vận chuyển public key**, không phải chứng chỉ hoặc bằng chứng ownership.
8. **SHA-256 fingerprint** giúp so sánh public key theo quy tắc encoding xác định, nhưng chỉ đáng tin nếu giá trị tham chiếu đã được lấy qua **kênh tin cậy**.

### 6.2. Ví dụ không được dùng như hệ thống cấp phát khóa production

Đoạn code minh họa sinh private key **trong process memory** để học API. Với production, nếu policy yêu cầu **non-exportable signing key**, hãy sinh khóa **ngay trong HSM/KMS** qua API hoặc provider thích hợp; ứng dụng chỉ giữ **key handle/resource ID** và quyền Sign, không lấy raw private key để ghi file.

Không sử dụng **getPrivate().getEncoded()** để in ra, lưu cấu hình YAML hoặc gửi cho client. PrivateKey được giữ trong JVM vẫn có thể bị lộ qua heap dump, debug, lỗi phân quyền hoặc backup nếu ứng dụng tự lưu.

### 6.3. Không so sánh hai private key bằng cách in bytes

Nếu muốn kiểm tra sinh khóa thành công:

- Với **signing key**, thực hiện **Sign/Verify** trên dữ liệu thử.
- Với **X25519**, thực hiện một vòng KeyAgreement với một cặp thứ hai được tạo hợp lệ.
- Kiểm tra **thuật toán, curve, key usage, định dạng public key và key ID/version** theo chính sách.
- Với KMS/HSM, dùng API **key metadata, test operation và attestation** nếu nhà cung cấp có hỗ trợ.

**Không cần xuất raw private key để chứng minh cặp khóa đúng.** Một kiểm thử sử dụng API đúng thường an toàn và phù hợp ranh giới hơn.

## 7. Java 17: kiểm thử cặp khóa X25519 bằng KeyAgreement

Sinh X25519 key pair chỉ mới tạo ra public/private vật liệu. Cần hiểu kết quả **KeyAgreement** là một **shared secret trung gian**, không phải khóa AES sẵn dùng và cũng **không tự xác thực đối tác**.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public final class X25519KeyPairCheck {
    static byte[] agree(PrivateKey mine, PublicKey theirs)
            throws Exception {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(mine);
        ka.doPhase(theirs, true);
        byte[] secret = ka.generateSecret();

        // Một số provider đã từ chối điểm đặc biệt này.
        // Kiểm tra bổ sung giúp không dùng shared secret toàn 0.
        int nonzero = 0;
        for (byte b : secret) {
            nonzero |= b & 0xff;
        }
        if (nonzero == 0) {
            Arrays.fill(secret, (byte) 0);
            throw new SecurityException("Invalid X25519 shared secret");
        }
        return secret;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = gen.generateKeyPair();
        KeyPair bob = gen.generateKeyPair();

        byte[] aSecret = agree(alice.getPrivate(), bob.getPublic());
        byte[] bSecret = agree(bob.getPrivate(), alice.getPublic());

        try {
            System.out.println("Same shared secret: " +
                    MessageDigest.isEqual(aSecret, bSecret));
        } finally {
            Arrays.fill(aSecret, (byte) 0);
            Arrays.fill(bSecret, (byte) 0);
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
Same shared secret: true
~~~

### 7.1. Vì sao ví dụ chưa phải một giao thức an toàn?

**Nguy cơ man-in-the-middle:** Nếu attacker thay public key của Bob bằng public key do mình tạo, Alice vẫn có thể tính shared secret, nhưng khóa đó thực chất dành cho Alice–attacker. Vì vậy, giao thức phải xác thực peer bằng **chứng chỉ/chữ ký/PSK** hoặc cơ chế đã chuẩn hóa.

**Cần KDF:** Không dùng trực tiếp raw X25519 shared secret như AES key. Giao thức chuẩn thường dùng **HKDF** hoặc key schedule để dẫn xuất khóa, có **domain separation, transcript binding và nhãn hướng truyền**.

**Cần xử lý kết quả đặc biệt:** X25519 có các public input đặc biệt khiến shared secret toàn số 0. Không chấp nhận secret đó làm bí mật phiên; provider có thể báo lỗi trước khi trả về.

**Cần nonce AEAD:** Nếu khóa phiên được dẫn xuất dùng với AES-GCM hoặc ChaCha20-Poly1305, phải quản lý nonce/IV đúng thuật toán. KDF đúng không tự sửa lỗi tái sử dụng nonce.

**Cần lifecycle:** Với ephemeral DH, private key tạm thời nên có thời gian sống ngắn theo giao thức. **Arrays.fill** chỉ xóa những byte arrays do ứng dụng kiểm soát; JVM/provider có thể giữ bản sao khác, không bảo đảm zeroization toàn bộ private key.

Khi xây hệ thống thật, ưu tiên **TLS 1.3, HPKE hoặc một giao thức authenticated key establishment được thẩm định** thay vì tự ghép các đoạn KeyPairGenerator, KeyAgreement, SHA-256 và AES thành giao thức mới.

## 8. Public key được phân phối và xác thực như thế nào?

**Public key không cần giữ bí mật**, nhưng không có nghĩa chấp nhận bất kỳ public key nào nhận được từ mạng. Nếu ứng dụng mã hóa DEK cho một public key do attacker thay, attacker có thể nhận được bí mật; nếu verifier tin public key giả, chữ ký giả có thể được chấp nhận.

### 8.1. Các định dạng phổ biến

| Dạng public key | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **SPKI / X.509 SubjectPublicKeyInfo** | Cấu trúc thuật toán và public key bytes | Không tự là chứng chỉ hoặc bằng chứng danh tính |
| **X.509 Certificate** | Public key gắn với subject và thông tin do CA ký | Phải kiểm tra chain, danh tính, validity, usage, trust/revocation |
| **JWK/JWKS** | Public key trong cấu trúc JSON theo tiêu chuẩn phù hợp | Phải ràng buộc issuer, key ID, thuật toán được phép và nguồn JWKS tin cậy |
| **SSH public key** | Public key theo định dạng và hệ sinh thái SSH | Kiểm tra host/user identity và nguồn/cách tin cậy |
| **Fingerprint** | Giá trị băm ngắn gọn của encoding public key | Chỉ là thông tin so khớp; nguồn fingerprint phải đáng tin |

Một public key **parse thành công không có nghĩa được cấp phát bởi đúng người**. Nếu certificate được ký hợp lệ nhưng danh tính/Key Usage/Extended Key Usage không phù hợp, ứng dụng vẫn phải từ chối.

### 8.2. CSR và quá trình xin chứng chỉ

**Certificate Signing Request (CSR)** thường chứa public key và thông tin yêu cầu cấp chứng chỉ, được chứng minh bằng chữ ký theo quy trình. Một luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant APP as Service / owner
    participant HSM as HSM/KMS
    participant CA as Certificate Authority
    participant PEER as Verifier / peer
    APP->>HSM: Sinh private/public signing key pair
    HSM-->>APP: Public key + key ID/handle
    APP->>HSM: Ký CSR/chứng minh sở hữu khóa khi API hỗ trợ
    APP->>CA: CSR + yêu cầu danh tính
    CA->>CA: Xác minh danh tính và chính sách cấp phát
    CA-->>APP: X.509 certificate
    APP->>PEER: Public certificate/chain qua kênh giao thức
    PEER->>PEER: Verify chain, identity, purpose và revocation
~~~

Không phải mọi KMS hỗ trợ **ký CSR** hoặc mọi public key đều được cấp chứng chỉ X.509. Với JWT/JWKS, issuer có thể phân phối public key từ một endpoint được tin cậy mà không dùng cơ chế CSR/CA tương tự.

### 8.3. Trust source và key substitution

Ứng dụng cần biết **public key được tin vì sao**:

- **PKI:** Chứng chỉ có chain hợp lệ tới trust anchor được cấu hình tin cậy; đúng hostname/identity và key usage.
- **Pinning/trusted registry:** Public key được cấp phát qua quy trình có xác thực và thay đổi có audit.
- **JWKS/OIDC:** Endpoint và issuer được tin cậy được cấu hình trước; không để một JWT chưa xác thực chỉ định URL public key tùy ý.
- **SSH known_hosts:** Bên kết nối phải biết hoặc xác minh host public key qua cơ chế tin cậy phù hợp.

Một **fingerprint** được truyền qua cùng kênh đang bị tấn công MITM **không tự bảo vệ trước MITM**. Cần kênh tham chiếu tin cậy hoặc một giao thức trust phù hợp.

## 9. Private key được sinh và lưu ở đâu?

Đây là một **quyết định kiến trúc** quan trọng hơn việc chỉ chọn câu lệnh Java. Sinh private key ở đâu quyết định **ai từng có khả năng đọc raw key**, có thể sao chép bao nhiêu lần và bằng chứng nào hỗ trợ điều tra.

| Cách sinh/lưu | Đặc điểm | Phù hợp hoặc cần lưu ý |
| --- | --- | --- |
| **Java process memory** | KeyPairGenerator trả về PrivateKey/PublicKey cho JVM | Thuận tiện khi học hoặc key ephemeral; cần quản lý memory dumps, persistence và lifecycle |
| **Java KeyStore / PKCS#12** | Lưu private key có bảo vệ bằng mật khẩu và file permissions | Có thể phù hợp trong một số môi trường nhưng đòi hỏi bảo vệ file, mật khẩu, backups và quyền truy cập |
| **Secret manager** | Lưu/cấp phát secret theo danh tính và chính sách | Kiểm tra quyền export, versioning, cache và rotation; không mặc nhiên đạt non-exportable |
| **Managed KMS asymmetric key** | Dịch vụ sinh và giữ private key, cung cấp key ID và API Sign/Decrypt/Derive nếu hỗ trợ | Cần đối chiếu thuật toán, giới hạn operation, IAM, vùng và trạng thái khóa |
| **HSM / PKCS#11** | Sinh key pair trong ranh giới HSM; private key có thể non-exportable theo cấu hình | Cần quản trị partition, PIN/role, backup, HA, attestation và audit |
| **Cloud/vault key import** | Nhập key material được tạo ở bên ngoài | Chỉ dùng khi có yêu cầu và quy trình an toàn; key đã xuất hiện ngoài HSM có phạm vi tin cậy rộng hơn |

### 9.1. Non-exportable có nghĩa gì?

**Non-exportable private key** là private key mà cơ chế lưu giữ **không cung cấp đường xuất vật liệu bí mật dạng rõ trong phạm vi bảo đảm của hệ thống**. Thay vì lấy private key bytes, ứng dụng sử dụng **key handle hoặc resource identifier** để yêu cầu HSM/KMS thực hiện phép toán được phép.

Tuy nhiên:

- Một **key object có getEncoded() trả null** có thể biểu thị không có encoding export qua API đó, nhưng không tự chứng minh mọi đường export trên thiết bị đều bị cấm.
- Một **HSM key non-exportable** vẫn có thể bị **lạm dụng qua API Sign/Decrypt/Derive** nếu principal được cấp quyền bị chiếm.
- **Backup/replication** có thể tuân theo cơ chế quản lý đặc biệt của nhà cung cấp, không giống xuất raw key qua API thông thường.
- Cần xác minh **hợp đồng bảo mật và key attributes** của dịch vụ, chứ không chỉ tên một trường cấu hình.

### 9.2. Sinh khóa trong HSM khác đưa khóa vào HSM sau khi sinh

Nếu Java tự sinh private key và sau đó **import** vào HSM, private key **đã từng tồn tại trong JVM**, có thể bị ghi vào dump, snapshot hoặc artifact. Bật chế độ non-exportable sau import không xóa sự thật rằng đã có **bản sao trước đó**.

Nếu mục tiêu yêu cầu **private key chưa từng rời khỏi HSM**, phải dùng **generate inside HSM** theo cơ chế và quy trình được phê duyệt. Khi không có tính năng này, cần đánh giá lại mô hình đe dọa và lưu bằng chứng về xuất xứ của key material.

### 9.3. Đừng giả định tất cả KMS đều giống nhau

Một số KMS hỗ trợ RSA/ECC asymmetric signing, một số có key agreement, một số chỉ cho các thao tác mã hóa hoặc MAC nhất định. API tạo **symmetric DEK** thường khác API tạo **asymmetric key pair**.

Nếu một nhà cung cấp trả về **public key** cùng **key resource ID** và giữ **private key non-exportable**, ứng dụng nên sử dụng đúng hai đối tượng đó. **Không viết code buộc KMS phải trả raw private key** chỉ để có thể dùng KeyPair theo kiểu JCA nếu chính sách cấm xuất.

### 9.4. Khóa trong file và bảo vệ mật khẩu

Nếu kiến trúc được phê duyệt sử dụng keystore:

- Đặt **file permissions, mã hóa at rest, quản lý mật khẩu qua secret manager**, và backup phù hợp.
- Phân biệt **keystore password**, private key protection password và IAM của tiến trình đọc file.
- Không lưu keystore hoặc password trong source repository/container image công khai.
- Kiểm tra đường truy cập qua backup, snapshot, crash dump và công cụ hỗ trợ vận hành.
- Không coi một tệp **PKCS#12 có mật khẩu yếu** tương đương HSM non-exportable.

**Không lưu private key dưới dạng Base64 trong cấu hình YAML/JSON rồi gọi đó là mã hóa.** Base64 chỉ là encoding.

## 10. Tích hợp key pair với key inventory và chính sách sử dụng

Ngay khi sinh key pair, hệ thống cần một **metadata record** mô tả vật liệu khóa, owner và trạng thái. Inventory được thiết kế để **truy xuất và điều phối**, không chứa private key.

~~~json
{
  "keyId": "billing-sign-prod-v3",
  "keyVersion": 3,
  "algorithm": "Ed25519",
  "type": "asymmetric-signing",
  "purpose": "sign-billing-event",
  "environment": "production",
  "owner": "billing-platform",
  "tenantScope": "billing-domain",
  "privateKeyLocation": "managed-hsm",
  "publicKeySource": "trusted-signer-registry",
  "keyState": "PRE_ACTIVE",
  "allowedOperations": ["Sign"],
  "createdAt": "2026-11-28T00:00:00Z",
  "activationRequiresApproval": true,
  "rotationPolicyId": "billing-signer-rotation",
  "incidentContact": "billing-security-oncall"
}
~~~

**Đây là mẫu nội bộ minh họa**, không phải schema chuẩn của KMS/HSM. Trường **type** nên phản ánh key usage thật. Nếu khóa dùng với RSA-PSS, hệ thống phải ghi rõ thuật toán/padding/parameters phù hợp; một tên chung “RSA” chưa đủ diễn đạt toàn bộ cách ký.

### 10.1. Key ID, version, public key và private key handle

| Thành phần | Ý nghĩa |
| --- | --- |
| **Key ID** | Định danh logic hoặc resource ID gắn với một vật liệu khóa/phiên bản theo thiết kế |
| **Key version** | Phân biệt các lần thay material; quan trọng khi dữ liệu/chữ ký cũ vẫn tồn tại |
| **Alias** | Tên tham chiếu có thể đổi mục tiêu; không nên coi alias là chứng cứ duy nhất về key material |
| **Public key bytes/certificate** | Vật liệu dùng để Verify/mã hóa theo thuật toán; phải có nguồn tin cậy |
| **Private key handle** | Tham chiếu đến vật liệu private key trong HSM/KMS |
| **State/usage policy** | ACTIVE, RETIRED, REVOKED, allowed operations, environment, owner |
| **Audit ID/change reference** | Liên kết với yêu cầu, phê duyệt, rotation và incident |

### 10.2. Khi nào public key được coi là active?

**Không kích hoạt một public verification key** chỉ vì nó đã được sinh. Phải chắc chắn:

1. Đúng **algorithm/curve, purpose, issuer/owner**.
2. Private key tương ứng thuộc ranh giới được quản lý đúng.
3. Các consumer đã nhận public key qua **trusted channel**.
4. Có mốc kích hoạt rõ cho producer và verifier.
5. Policy về key ID/version/cert và hiệu lực được cập nhật.

Với **planned signing-key rotation**, verifier có thể được cấp public key mới **trước** khi producer bắt đầu Sign bằng key mới. Đó là chiến lược giúp tránh gián đoạn nhưng phải có mốc trust/activation và giới hạn chấp nhận key cũ.

## 11. Vòng đời key pair sau khi sinh

Sinh khóa là một hành động tại thời điểm ban đầu; **an toàn của khóa phải được duy trì trong các hoạt động sau**.

| Giai đoạn | Private key / public key cần kiểm soát gì? | Ví dụ sai lầm |
| --- | --- | --- |
| **Generation** | CSPRNG/HSM phù hợp, thuật toán và độ mạnh, key usage | Seed yếu, tạo RSA nhỏ hoặc curve không được duyệt |
| **Provisioning** | Chỉ public key được phân phối công khai có xác thực; private key qua handle/quyền đúng | Gửi private key trong email để “triển khai nhanh” |
| **Storage** | HSM/KMS/keystore theo policy, backup, audit, không ghi log raw key | Copy private key vào Git hoặc container image |
| **Usage** | Phép Sign/Decrypt/Derive đúng purpose, IAM và authorization nghiệp vụ | Signing service có quyền Decrypt hoặc Delete không cần thiết |
| **Rotation** | Sinh cặp mới, key ID/version mới, tương thích consumer và dữ liệu cũ | Thay public key trước khi verifier có nguồn tin cậy |
| **Revocation** | Chặn Sign/Decrypt/Derive; thu hồi chứng chỉ/trust/credentials theo thiết kế | Disable HSM key nhưng JWKS cache vẫn tin token cũ |
| **Destruction** | Xác nhận hết dữ liệu/chữ ký phụ thuộc, backup và retention | Xóa private decryption key khi ciphertext cũ vẫn cần đọc |

### 11.1. Rotation của signing key

Ví dụ từ private signing key **v1** sang **v2**:

1. Sinh **key pair v2** trong đúng ranh giới lưu giữ.
2. Đăng ký **public key v2** qua trust registry/certificate/JWKS được xác thực.
3. Chuẩn bị verifier nhận v2; cần kiểm soát cache và versioning.
4. Chuyển Sign mới sang v2 sau mốc kích hoạt.
5. Theo dõi chữ ký/token v1 còn cần xác minh; planned rotation có thể cho phép giai đoạn chuyển tiếp.
6. Retire/revoke key v1 tùy chính sách và đánh giá compromise; hủy private v1 sau khi hết phụ thuộc được phép.

**Chữ ký được tạo bởi private v1 không tự biến thành chữ ký v2 khi rotate.** Với chứng từ dài hạn, có thể cần lưu public verification material, chứng chỉ, thông tin thời gian và bằng chứng tin cậy theo retention.

### 11.2. Rotation của private decryption key

Nếu dùng RSA-OAEP mã hóa DEK cho public v1, dữ liệu cũ có thể chỉ được giải bằng **private v1**. Trước khi hủy v1, phải:

- Giải bọc DEK bằng v1 trong ranh giới được phép và **rewrap/encapsulate** cho public v2 phù hợp.
- Ghi key ID/version của envelope mới.
- Kiểm thử đọc dữ liệu và DR/backups.
- Thu hồi quyền decrypt v1 sau khi hết nghĩa vụ, hoặc giữ đường recovery có phê duyệt nếu vẫn cần.

**Không chỉ đổi public key ở phía gửi và hủy private key cũ** khi còn ciphertext gửi cho v1.

### 11.3. Ephemeral X25519 và tính bí mật chuyển tiếp

Khi sinh cặp khóa X25519 **ephemeral**, mục tiêu là dùng cho một phiên/handshake. Trong một giao thức **authenticated ephemeral Diffie-Hellman** được thiết kế đúng, lộ private signing key dài hạn về sau **không tự giải mã các phiên cũ chỉ từ transcript đã ghi lại** (forward secrecy).

Điều kiện FS còn phụ thuộc **cách xác thực handshake, việc bảo vệ private ephemeral, session secret, RNG và giao thức**. KeyPairGenerator tạo ephemeral key không tự chứng minh ứng dụng có FS.

### 11.4. Revocation không đồng nghĩa xóa bí mật đã lộ

Nếu raw private key đã rò ra ngoài, **disable tại KMS/HSM không thu hồi bản sao đã bị lấy**. Với signing key, đối thủ có thể tạo chữ ký nếu verifier vẫn tin public key đó. Với decryption key, đối thủ có thể giải mã bản ciphertext cũ đã thu thập. Phải xử lý **trust propagation, rotation, dữ liệu và phạm vi sự cố**, không chỉ đổi một trạng thái.

## 12. Quan hệ giữa key pair và KMS/HSM, DEK/KEK, envelope encryption

Cặp khóa bất đối xứng có thể bảo vệ một bí mật để mã hóa lai; nhưng không phải mọi ứng dụng đều cần key pair cho việc mã hóa dữ liệu tại chỗ.

~~~mermaid
flowchart TD
    USER["Chính sách dữ liệu và quyền"] --> DEK["Sinh DEK đối xứng bằng KMS/CSPRNG"]
    DEK --> AEAD["Mã hóa dữ liệu bằng AEAD<br/>AES-GCM + nonce mới"]
    AEAD --> STORE["Lưu ciphertext, tag, IV và metadata"]
    DEK --> WRAP{"Cách bảo vệ DEK"}
    WRAP --> KMS["KEK trong KMS/HSM<br/>key wrapping được phép"]
    WRAP --> PUB["Public key RSA/HPKE<br/>đã xác thực người nhận"]
    KMS --> STORE
    PUB --> STORE
    STORE --> UNWRAP["Đọc đúng key ID/version<br/>giải bọc DEK theo quyền"]
    UNWRAP --> CHECK["Xác minh AAD/tag và authorization"]
~~~

### 12.1. Sinh key pair có cần thiết để bảo vệ dữ liệu trong DB?

Không nhất thiết. Nếu ứng dụng mã hóa dữ liệu at rest cho chính nó, **DEK/KEK đối xứng qua KMS** thường là mô hình phù hợp. Cặp khóa RSA/EC có thể có ích khi **bên gửi không cùng ranh giới tin cậy với bên nhận**, khi xác thực bằng chữ ký số hoặc trong giao thức thỏa thuận khóa.

Phải phân biệt **GenerateDataKey** (tạo vật liệu khóa đối xứng) với **GenerateKeyPair/CreateAsymmetricKey** (tạo cặp public/private) theo API của nhà cung cấp. Không áp dụng quy trình quản lý raw DEK giống private signing key non-exportable một cách máy móc.

### 12.2. Mã hóa bằng public key phải chọn primitive đúng

- **RSA-OAEP:** Có thể mã hóa một bí mật nhỏ như DEK dưới public RSA đã xác thực; giới hạn kích thước plaintext theo modulus và hàm băm OAEP. Không dùng RSA thô hoặc PKCS#1 v1.5 encryption trong thiết kế mới khi chính sách không cho phép.
- **ECDH/HPKE:** Thông thường thiết lập shared secret, dùng KDF và AEAD theo đặc tả. Không có thao tác “EC public key.encrypt(file)” chung.
- **KEM hậu lượng tử:** Có cơ chế encapsulate/decapsulate khác DH, phải chọn giao thức và key usage tương ứng.
- **AES-GCM:** Mã hóa payload, có nonce/IV và authentication tag, không được tái sử dụng nonce dưới cùng DEK.

### 12.3. KMS/HSM không thay lớp authorization

Một private key được bảo vệ trong HSM có thể vẫn bị lạm dụng qua **Sign API** nếu workload identity bị chiếm. Một quyền Unwrap/Decrypt tại KMS không tự chứng minh người dùng có quyền đọc bản ghi của tenant khác.

Cần đồng thời kiểm soát **principal, environment, tenant, purpose, trạng thái key, dữ liệu và nơi sử dụng**. Bản ghi audit nên có key ID, operation, caller, thời điểm và kết quả, không có private key hoặc plaintext.

## 13. Tình huống thực tế: sinh key pair cho dịch vụ ký hóa đơn Java

Một nền tảng thương mại điện tử có:

- **Billing Service** chạy trên Java, phát hành sự kiện hóa đơn cho đối tác.
- **Signing Service** có private key trong HSM để ký nội dung hóa đơn.
- **Verification Gateway** và các đối tác kiểm tra chữ ký qua public key đã được xác thực.
- **KMS** riêng để bọc DEK mã hóa dữ liệu hóa đơn at rest; **DEK/KEK không trùng private signing key**.
- **Security** quản lý chuẩn mật mã và sự cố; **Application owner** quản lý key inventory, tính tương thích và retention.

### 13.1. Quyết định trước khi triển khai

1. **Chọn signing algorithm:** Ví dụ **Ed25519** nếu HSM, SDK và bên xác minh đều hỗ trợ và policy cho phép. Nếu hệ sinh thái dùng RSA-PSS/ECDSA, chọn cấu hình được phê duyệt thay vì đổi tùy ý.
2. **Chọn key boundary:** Sinh private signing key bên trong HSM; không yêu cầu raw private key cho Billing Service.
3. **Định nghĩa purpose:** Chỉ Signing Service được gọi **Sign** đối với loại thông điệp đã kiểm tra authorization; không có quyền Export hoặc Destroy.
4. **Thiết kế public key trust:** Registry được bảo vệ hoặc chứng chỉ, định danh issuer, key ID/version và mốc kích hoạt.
5. **Thiết kế input ký:** Canonical bytes, serialization, version, tenant, invoice ID, purpose và các trường có thể bị thay đổi phải được xác định rõ. Chữ ký trên byte không bao phủ một trường nghiệp vụ quan trọng sẽ không xác thực được trường đó.
6. **Đặt rotation policy:** Thời điểm thay signing key, cách tiêu thụ v1/v2, cache invalidation và chữ ký lịch sử.
7. **Đặt incident plan:** Khi principal Sign bị chiếm, có thể chặn quyền, điều tra các chữ ký đã phát hành, cấp signer mới và làm verifier ngừng tin key cũ theo policy.

### 13.2. Luồng tạo khóa và chuẩn bị phát hành

~~~mermaid
sequenceDiagram
    participant AO as Application owner
    participant SEC as Security / Key custodian
    participant HSM as HSM
    participant REG as Trusted public-key registry
    participant APP as Billing / Signing Service
    participant V as Verifier
    AO->>SEC: Key request: purpose, algorithm, prod, version
    SEC->>HSM: Generate key pair theo policy
    HSM-->>SEC: Key handle + public key + metadata
    SEC->>REG: Đăng ký public key, key ID và trust context
    AO->>APP: Rollout key reference mới
    V->>REG: Nhận trusted public key + version
    REG-->>V: Key metadata được xác thực
    AO->>APP: Kích hoạt Sign sau khi verifier sẵn sàng
    APP->>HSM: Sign canonical invoice bytes bằng key ID
    HSM-->>APP: Digital signature
    APP->>V: Invoice, signature, key ID/version
    V->>V: Chọn trusted key, kiểm tra quyền + Verify
~~~

### 13.3. Những điểm phải xác minh trong kiến trúc

| Câu hỏi | Kết quả an toàn mong muốn |
| --- | --- |
| Billing Service có private key bytes không? | **Không**, nếu thiết kế HSM non-exportable; chỉ có quyền gọi Sign cần thiết |
| AI có thể thêm một public key vào registry? | Chỉ quy trình có danh tính/phê duyệt được kiểm soát và audit |
| Verifier có tin public key do invoice tự khai báo không? | **Không**; chọn từ nguồn tin cậy đã cấu hình, kiểm tra issuer/key ID |
| Một signature hợp lệ có chứng minh hóa đơn đúng giá? | Chỉ khi đúng bytes được ký và validation/authorization nghiệp vụ cũng đúng |
| Signing key v1 bị lộ thì sao? | Chặn Sign, update trust, đánh giá chữ ký v1, không chỉ tạo key v2 |
| Private key bị mất khi HSM lỗi? | Cơ chế HA/backup/recovery được phê duyệt; không có file raw key bí mật nằm ngoài kiểm soát |
| Sinh signer mới có làm mất dữ liệu hóa đơn không? | Không nếu mã hóa at rest dùng DEK/KEK riêng; việc Verify lịch sử phải được tính tới |

### 13.4. Khi nào có thể dùng key pair tự sinh trong Java?

**Ephemeral X25519 key** trong một giao thức phù hợp có thể được tạo trong process memory với thời gian sống ngắn. **Key pair demo/test** có thể dùng JCA tại runtime. Còn với **private signing key dài hạn của hệ thống production**, tổ chức thường đánh giá việc sinh và giữ key trong KMS/HSM hoặc keystore được bảo vệ mạnh.

Mức bảo vệ **không chỉ phụ thuộc câu lệnh sinh khóa** mà còn phụ thuộc độ nhạy cảm, thời gian sống, quyền, ranh giới tin cậy và hậu quả nếu private key bị lộ.

## 14. Những bài kiểm thử phải có trước khi đưa key pair vào production

Kiểm thử nên xem xét cả **chức năng mật mã**, **chính sách sử dụng** và **khả năng vận hành**.

### 14.1. Kiểm thử chức năng

| Bài kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Sinh key pair theo thuật toán/curve được phép | API thành công, key metadata đúng, private key được bảo vệ |
| Dùng private Ed25519 ký và public Ed25519 verify | Verify thành công với đúng message |
| Sửa một byte message hoặc signature | Verify thất bại |
| Verify bằng public key khác | Verify thất bại |
| X25519 hai bên sinh key pair hợp lệ | Raw shared secret khớp, không phải toàn số 0 |
| Thay public key bên thứ hai trong key agreement | Không được coi phiên xác thực thành công chỉ vì KeyAgreement chạy |
| Sinh RSA với tham số được phê duyệt | Đúng độ dài modulus, exponent và cấu hình thuật toán |
| Xuất SPKI public key, import lại từ trust source | Kết quả Verify/metadata đúng; nguồn vẫn phải xác thực |
| Gọi thuật toán không được provider hỗ trợ | Báo lỗi rõ, **không fallback** sang thuật toán yếu |

### 14.2. Kiểm thử policy và vòng đời

| Bài kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Dev workload gọi Sign bằng private key production | Bị IAM/KMS/HSM từ chối |
| Workload chỉ có Sign thử Export/Destroy | Không có quyền |
| Một tenant chọn key ID của tenant khác | Bị từ chối bởi authorization/policy |
| Key đang PRE_ACTIVE được gọi Sign | Bị từ chối đến khi kích hoạt |
| Key đã REVOKED được gọi Sign/Derive | Bị từ chối; không fallback sang key cũ |
| Private key non-exportable bị gọi API export | Bị từ chối theo hợp đồng provider/key attributes |
| Signer v2 kích hoạt, verifier chưa có v2 | Phát hiện trong readiness; tránh rollout gây mất khả năng Verify |
| Restore backup cũ sau khi thu hồi v1 | Không hồi sinh key policy/trust cũ |
| KMS/HSM gặp lỗi | Fail closed, cảnh báo; không dùng private key hardcode |
| Xóa private decryption key trong lúc còn DEK cũ | Destruction preflight chặn hoặc yêu cầu migration |

### 14.3. Không đánh giá entropy chỉ bằng cách sinh 100 khóa khác nhau

**Các cặp khóa tạo ra khác nhau trong một số lần chạy** là kiểm tra chức năng hữu ích, nhưng **không chứng minh** CSPRNG có entropy hoặc DRBG đạt bảo mật trong mọi môi trường. Cần đánh giá **provider, cấu hình, entropy source, trạng thái khi restart, key provenance và bằng chứng của nhà cung cấp**.

### 14.4. Kiểm thử lỗi và ranh giới bí mật

Thử trường hợp lỗi khi:

- Sinh key pair thất bại hoặc HSM hết khả năng cấp khóa.
- PrivateKey handle không truy cập được sau failover.
- Certificate/CSR bị từ chối hoặc public key không đúng thuật toán.
- Có phiên bản khóa bị cache sai trong JWKS/truststore.
- Audit service tạm không sẵn sàng, hoặc người dùng không đủ quyền Sign.
- Có yêu cầu dùng private key sai purpose, sai môi trường, sai tenant.

Xác minh **logs/metrics không chứa private key, seed, session secret hoặc password** kể cả khi provider ném exception.

## 15. Khi sinh khóa hoặc private key bị xâm phạm: ứng phó ra sao?

Một sự cố tại **thời điểm sinh key pair** thường có phạm vi nghiêm trọng vì mọi phép toán về sau đều phụ thuộc private key đó.

### 15.1. Các tình huống cần phân biệt

| Tình huống | Nguy cơ | Biện pháp cần cân nhắc |
| --- | --- | --- |
| Key pair sinh bằng RNG yếu | Private key có thể bị suy ra | Dừng dùng key, tạo key mới bằng RNG tin cậy, đánh giá toàn bộ key đã sinh trong khoảng |
| Private key được commit vào Git | Key material có thể đã bị sao chép | Coi là exposure, chặn dùng, thay key, điều tra lịch sử và bản sao |
| Private key ở HSM nhưng principal Sign bị chiếm | Kẻ tấn công có thể ký sai trái phép, chưa chắc raw key bị xuất | Thu hồi credential/grants, chặn Sign, điều tra chữ ký, cập nhật trust |
| Trusted public key registry bị thay | Verifier có thể chấp nhận signer của đối thủ | Khôi phục nguồn tin cậy, kiểm tra signature/token đã chấp nhận |
| RSA private decryption key bị lộ | Ciphertext/DEK đã mã hóa cho public key đó có thể bị đọc | Thay key pair, rewrap DEK, đánh giá dữ liệu đã bị sao chép |
| Static DH private key bị lộ | Shared secrets và phiên có thể bị ảnh hưởng theo giao thức | Chặn key, thay khóa và đánh giá phiên/lịch sử; không giả định FS |
| Ephemeral DH private key lộ trong một phiên | Bí mật và dữ liệu phiên có thể bị lộ | Cô lập phiên, tạo handshake mới, điều tra dump/log |

### 15.2. Playbook phản ứng

1. **Xác định khóa:** Key ID/version, owner, purpose, thuật toán, environment, thời điểm tạo và public key tương ứng.
2. **Cô lập:** Dừng thao tác mới bằng khóa nghi bị lộ hoặc quyền bị chiếm; revoke principal/grant và bảo toàn bằng chứng.
3. **Khoanh vùng:** Tìm các chữ ký/certificate, ciphertext, wrapped DEK, phiên DH và các dịch vụ phụ thuộc.
4. **Sinh key pair mới:** Từ nguồn và ranh giới đáng tin cậy; không tái sử dụng seed hoặc bản sao private key cũ.
5. **Phân phối public key mới có xác thực:** Đồng bộ certificate/JWKS/truststore, key ID/version và các bên xác minh.
6. **Chuyển dữ liệu và thao tác:** Rewrap DEK hoặc re-encrypt theo loại khóa và mức ảnh hưởng; không nhầm công việc kỹ thuật với phục hồi dữ liệu đã rò.
7. **Kiểm tra hiệu lực thu hồi:** Negative test cho Sign/Decrypt/Derive cũ và Verify/trust mới, kiểm tra cache và DR.
8. **Hủy key material cũ có kiểm soát:** Sau khi xử lý retention, backup và phụ thuộc; lưu audit, root cause và rủi ro tồn dư.

**Thu hồi khóa không làm đối thủ mất bản sao đã giữ.** Nếu họ có private signing key cũ, chữ ký giả có thể tiếp tục hợp lệ về mặt toán học; chỉ các bên Verify áp dụng **trust/revocation policy** mới có thể từ chối theo yêu cầu.

## 16. Kiểm toán hoạt động sinh key pair

Một hệ thống không nên chỉ biết “có key pair”. Cần trả lời **ai yêu cầu tạo, ai phê duyệt, thuật toán nào đã dùng, khóa sinh ở đâu và điều gì đã xảy ra sau khi sinh**.

### 16.1. Bằng chứng nên ghi

| Thông tin | Mục tiêu |
| --- | --- |
| **keyId/keyVersion** | Định vị chính xác khóa và phiên bản |
| **owner/environment/tenant/purpose** | Xác minh phạm vi trách nhiệm và sự tách biệt |
| **algorithm/parameters/provider** | Xác định khóa có đáp ứng security policy hay không |
| **keyStorageBoundary** | Biết private key sinh trong HSM/KMS hay process memory |
| **requestedBy/approvedBy** | Tách trách nhiệm và nhận diện hành động trái phép |
| **createdAt/activatedAt** | Liên kết việc tạo với chu kỳ phát hành và sự cố |
| **privateKeyExportPolicy** | Kiểm tra non-exportable/allowed operations theo chính sách |
| **publicKeyFingerprint** | Hỗ trợ nhận diện public key khi có nguồn tin cậy |
| **keyState/rotationPolicy** | Giúp kiểm soát hoạt động sau này |
| **requestId/changeId/incidentId** | Liên kết yêu cầu, approval, audit và sự cố |

**Không ghi raw private key, seed, password hoặc raw shared secret** vào audit log. Việc tạo chứng cứ không được tạo ra một sự cố rò rỉ mới.

### 16.2. Các cảnh báo hữu ích

- Production key pair được sinh **ngoài KMS/HSM được duyệt**, hoặc được import từ một môi trường không rõ nguồn.
- Private key export được bật bất ngờ sau khi khóa đã kích hoạt.
- Một principal vốn chỉ Verify bỗng được cấp quyền Sign hoặc key admin.
- Thuật toán hoặc độ dài không đáp ứng policy, ví dụ RSA nhỏ hơn mức được phê duyệt.
- Nhiều cặp khóa được sinh bất thường trong một khoảng ngắn, không có change record.
- Khóa được sinh trong **test** nhưng được phân phối như **production signing key**.
- Public key registry/JWKS đổi không qua workflow.
- Có raw secret, PEM private key hay keystore password xuất hiện trong log hoặc artifact.
- Key cũ vẫn được dùng sau mốc revoked/retired, hoặc DR restore khôi phục trust cũ.

### 16.3. Hành vi fail closed khi generation lỗi

Nếu provider không hỗ trợ curve, KMS/HSM không thể sinh key pair, entropy subsystem lỗi hoặc policy từ chối, hệ thống nên **báo lỗi và dừng đường sử dụng nhạy cảm**. Không tự:

- Chuyển sang RSA key size nhỏ.
- Dùng key pair test có sẵn.
- Copy private key giữa tenant/môi trường.
- Đổi thuật toán ký sang một cơ chế yếu không được phê duyệt.
- Bỏ kiểm tra chữ ký hoặc trust anchor để tiếp tục hoạt động.

Khả năng sẵn sàng cần được thiết kế từ trước bằng **provider redundancy, KMS/HSM HA, rotation schedule và DR** phù hợp; không khắc phục outage bằng cách giảm yêu cầu bảo mật một cách im lặng.

## 17. Những lỗi thường gặp khi sinh key pair

| Sai lầm | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Dùng **Random/Math.random/timestamp** để tạo private key | Giá trị bí mật có thể bị dự đoán | Dùng CSPRNG/provider/HSM đáng tin cậy |
| Không chỉ rõ RSA key size hoặc EC curve | Phụ thuộc mặc định, có thể không đáp ứng policy | Chỉ định tham số được duyệt và xác minh provider |
| Coi public key 32 byte là bảo mật 256 bit | Nhầm kích thước encoding với security strength | So độ mạnh theo primitive và tiêu chuẩn |
| Dùng **Ed25519 key** như X25519 key agreement | Trộn primitive ký và trao đổi khóa | Dùng đúng thuật toán/khóa và giao thức tương ứng |
| Dùng RSA không padding hoặc padding sai | Dễ dẫn tới lỗi mật mã | Chọn RSA-PSS/RSA-OAEP theo mục đích và đặc tả |
| Dùng cùng key pair cho mọi operation | Tăng blast radius và khó phân quyền/rotation | Tách key usage và hạn chế allowed operations |
| Sinh private key trong JVM rồi coi là HSM-non-exportable sau khi import | Đã có bản sao trong JVM/dump | Sinh trong HSM nếu chính sách yêu cầu |
| In **private.getEncoded()** để debug | Lộ raw key vào log/CI/ticket | Chỉ log key ID, fingerprint public key và audit metadata |
| Lưu private key Base64 trong YAML | Encoding không phải mã hóa | Dùng KMS/HSM hoặc keystore được bảo vệ |
| Tin public key từ request mà không xác thực | Key substitution/MITM/chấp nhận chữ ký giả | Chứng chỉ/JWKS/trusted registry với identity validation |
| Parse SPKI rồi kết luận peer hợp lệ | Parser chỉ kiểm tra encoding | Xác thực nguồn, danh tính và key usage |
| Dùng raw DH secret làm AES key | Thiếu KDF, domain separation và transcript binding | Dùng key schedule/giao thức chuẩn |
| Coi KeyAgreement thành công là đủ chống MITM | Attacker có thể thay public keys | Authenticated key establishment |
| Không kiểm tra X25519 shared secret toàn số 0 | Có thể dùng đầu ra không an toàn | Provider/check theo đặc tả và từ chối |
| Không xác định key ID/version trong metadata | Khó rotation, Verify/Decrypt sai key | Inventory, versioning, key selection đúng |
| Dùng chung signing key cho test/prod | Sự cố non-prod lan sang prod | Tách material, HSM partition/role và trust |
| Không kiểm tra IAM grants Sign/Decrypt | HSM vẫn có thể bị lạm dụng qua API | Least privilege, key policy và audit |
| Rotate signer nhưng không cập nhật verifier | Chữ ký mới không thể xác minh | Phân phối public key trước, theo dõi cache/ack |
| Destroy private RSA key khi còn encrypted DEK | Không mở được dữ liệu cần giữ | Rewrap/migration và restore test trước |
| Coi revoke KMS đã xóa private key bị lấy | Attacker vẫn có bản sao ngoài KMS | Thay key, xử lý trust và dữ liệu phụ thuộc |
| Khôi phục DR từ snapshot chứa key policy cũ | Khóa revoked có thể được tin lại | Trạng thái/tombstone và đối soát khi restore |
| Chỉ test key generation happy path | Bỏ qua lỗi provider, quyền, cache và migration | Kiểm thử tiêu cực, khả dụng và sự cố |

## 18. Checklist đánh giá quy trình sinh key pair

Trước khi đưa cơ chế tạo và sử dụng key pair vào production, hãy trả lời:

1. **Mục đích:** Cặp khóa dùng Sign/Verify, Encrypt/Decrypt hay key agreement? Có tách rõ key usage?
2. **Thuật toán:** Đã chọn RSA-PSS/RSA-OAEP, ECDSA, Ed25519, ECDH, X25519 hoặc KEM đúng với mục tiêu và policy?
3. **Độ mạnh:** RSA modulus, EC curve và security strength có đáp ứng thời gian bảo vệ dữ liệu?
4. **Nguồn ngẫu nhiên:** Private key được sinh qua CSPRNG/provider/KMS/HSM phù hợp, không seed yếu hoặc khôi phục RNG sai?
5. **Môi trường:** Dev/test/prod/DR có key material và quyền tách biệt, ngoại lệ được phê duyệt?
6. **Ranh giới sinh:** Private key có cần non-exportable và sinh **ngay trong HSM/KMS** không? Có xuất hiện ngoài ranh giới đó?
7. **Key attributes:** Key ID, version, algorithm, purpose, owner, state và allowed operations đã được ghi vào inventory?
8. **Bảo vệ private key:** File, memory, dump, backup, secret manager và IAM đã được đánh giá?
9. **Public key trust:** Bên nhận xác thực public key qua PKI/certificate/JWKS/pinning/trusted registry, không tin key từ input tùy ý?
10. **Self-test:** Có Sign/Verify, KeyAgreement và kiểm tra định dạng/tham số phù hợp mà không xuất raw private key?
11. **KDF và giao thức:** Với DH/ECDH, có authenticated handshake, KDF, transcript và khóa riêng theo hướng/mục đích?
12. **Authorization:** Workload được phép thực hiện operation nào? Có kiểm soát quyền tenant/resource ở ứng dụng?
13. **Rotation:** Có lịch thay key pair, public key rollout, compatibility, key version và test cache?
14. **Revocation:** Nếu private key bị lộ hoặc API Sign bị lạm dụng, có thể cô lập, thay key và làm verifier ngừng tin không?
15. **Dữ liệu phụ thuộc:** Nếu private decryption key bị hủy, đã xử lý ciphertext/wrapped DEK và retention?
16. **Backup/DR:** Có phục hồi hợp lệ mà không đưa raw key vào nơi không được phép và không hồi sinh revoked trust?
17. **Audit:** Có metadata, requester, approval, API result, key ID/version và incident link mà không ghi raw key?
18. **Kiểm thử lỗi:** Provider outage, thuật toán không hỗ trợ, public key sai, key revoked, cross-tenant và restore snapshot đã được thử?
19. **Crypto agility:** Có kế hoạch nâng thuật toán/độ mạnh hoặc tích hợp hậu lượng tử nếu yêu cầu tương lai thay đổi?
20. **Destruction:** Có bằng chứng hết phụ thuộc và trạng thái hủy thực thi đúng, không nhầm scheduled với destroyed?

## 19. Ghi nhớ

- **Sinh key pair** tạo một **private key** và **public key** có quan hệ toán học; public key có thể phân phối nhưng **phải xác thực nguồn**, còn private key cần được bảo vệ.
- **Chọn đúng primitive trước khi sinh:** RSA, ECDSA/Ed25519 và ECDH/X25519 có mục đích, tham số và API khác nhau. Không dùng một loại khóa tùy tiện cho mọi hoạt động.
- **CSPRNG, entropy source, provider và độ mạnh khóa** quyết định chất lượng vật liệu khóa từ bước đầu. Tăng key size không sửa được private key bị lộ hay RNG yếu.
- **KeyPairGenerator trong Java 17** thuận tiện để minh họa; production key dài hạn có thể cần sinh **trong KMS/HSM** để giới hạn việc xuất private key.
- **KMS/HSM non-exportable không miễn trừ IAM và audit:** kẻ chiếm workload vẫn có thể lạm dụng quyền Sign/Decrypt/Derive đã được cấp.
- **Public key không tự xác thực danh tính.** Phải dùng chứng chỉ, trust registry, JWKS issuer đáng tin cậy hoặc cơ chế chuẩn phù hợp để ngăn thay public key.
- **Key pair phải có vòng đời hoàn chỉnh:** key ID/version, purpose, owner, provisioning, activation, rotation, revocation, destruction, backup/DR và kiểm toán.
- **Hybrid/envelope encryption** thường dùng DEK đối xứng để mã hóa dữ liệu; key pair có thể dùng cho xác thực, bảo vệ bí mật nhỏ hoặc key agreement, không thay thế AEAD cho payload lớn.

Để đánh giá một quy trình **sinh key pair** an toàn, hãy hỏi ba câu: **“Cặp khóa này được sinh từ nguồn và tham số nào, để phục vụ phép toán gì?”, “Ai có thể sử dụng private key và bên nhận xác thực public key bằng cách nào?”, “Nếu phải thay, thu hồi hoặc hủy khóa, những chữ ký, phiên và bản mã nào sẽ chịu ảnh hưởng?”** Trả lời được bằng policy, inventory, cơ chế KMS/HSM và kết quả kiểm thử mới cho thấy việc tạo khóa thực sự an toàn trong hệ thống.
