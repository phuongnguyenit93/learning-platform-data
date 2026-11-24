# Tạo signing key

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **signing key** dùng để làm gì khi Authorization Server (AS) ký JWT/JWS, phân biệt **khóa ký**, **khóa xác minh**, **khóa mã hóa** và **secret dùng cho MAC**.
- Chọn mô hình **HMAC/HS256** hoặc **chữ ký số bất đối xứng RS256/PS256/ES256/EdDSA** theo trust boundary, policy mật mã và khả năng hỗ trợ của hệ thống.
- Hiểu lý do phải tạo khóa bằng **cryptographically secure random number generator (CSPRNG)** hoặc dịch vụ sinh khóa trong **HSM/KMS**, thay vì dùng password, timestamp, UUID hoặc pseudo-random generator không phù hợp.
- Tạo khóa thử nghiệm cho HMAC-SHA256, RSA, EC P-256 và Ed25519 bằng Java JCA, đồng thời biết giới hạn của ví dụ local so với sản xuất.
- Lập kế hoạch **key size/curve, key usage, alg allowlist, key ID (kid), issuer binding, activation time, expiry/retirement và rotation**.
- Biết chỉ công bố **public key** dưới dạng JWKS cho RS; không làm lộ private key hoặc symmetric HMAC secret.
- Thiết kế provisioning/backup/restore, phân quyền người vận hành, auditing và **least privilege** cho thao tác tạo và dùng khóa.
- Kiểm thử token ký bằng khóa mới, key lookup qua trusted JWKS, lỗi signature và cross-token/cross-issuer confusion.
- Mô tả cách phản ứng khi khóa ký bị lộ, việc key rotation ảnh hưởng tới JWT còn hạn và các rủi ro cache JWKS.
- Sử dụng bảng so sánh, Mermaid, Java và checklist để triển khai quy trình tạo signing key cho token bảo mật.

## 1. Signing key nằm ở đâu trong hệ thống token?

Một **signing key** là vật liệu mật mã mà thực thể có thẩm quyền sử dụng để tạo **authentication tag hoặc digital signature** cho token. Trong OAuth 2.0/OIDC, Authorization Server hoặc OpenID Provider thường phát JWT/JWS chứa claims như issuer, audience, subject, scope và thời hạn.

~~~text
AS kiểm grant và chính sách cấp quyền
    -> AS tạo JWS protected header và payload
    -> Signing service sử dụng signing key tạo chữ ký
    -> AS trả signed access token/ID token đúng profile
    -> Client đưa access token tới Resource Server
    -> Resource Server kiểm chữ ký bằng verification key đáng tin
    -> Resource Server kiểm issuer, audience, exp, scope và permission
~~~

**Chữ ký đúng không tự chứng minh token được phép sử dụng tại mọi API.** Nó bảo vệ nội dung đã ký theo khóa đáng tin. Resource Server vẫn phải kiểm quyền của token trên tài nguyên cụ thể.

### Phân biệt các loại khóa

| Loại vật liệu | Mục đích | Có nên công khai? |
| --- | --- | --- |
| **HMAC signing secret** | Ký/verify JWS HS256 bằng MAC đối xứng. | **Không**; mọi bên biết secret đều có thể tạo tag. |
| **Asymmetric signing private key** | Tạo chữ ký JWS RS256, PS256, ES256 hoặc EdDSA. | **Không**; phải bảo vệ chặt. |
| **Asymmetric public verification key** | RS xác minh chữ ký của AS. | Có thể công bố qua **JWKS đáng tin**, vì đây là public key. |
| **Encryption private/decryption key** | Giải mã JWE/TLS hoặc dữ liệu khác theo profile. | Không; mục đích riêng, không mặc định là signing key. |
| **Certificate/mTLS key** | Xác thực kết nối hoặc sender-constrained token. | Private key không công khai; không tự thay signing key của AS. |
| **HMAC logging key** | Tạo fingerprint cho audit/telemetry. | Không; nên tách khỏi signing secret. |

Trong chương này, **“Tạo signing key”** có nghĩa tạo đúng vật liệu mật mã, gắn nó với **issuer/purpose/alg/trust model** và chuẩn bị vòng đời sử dụng an toàn. Việc sinh bytes ngẫu nhiên chỉ là bước đầu.

## 2. Trước khi tạo: chọn trust model

Một hệ thống có thể có:

- AS: identity.example.test.
- OAuth client: dashboard-web.
- Resource Servers: Orders API, Payments API, Reports API.
- OpenID Connect Relying Party: Dashboard.

Câu hỏi kiến trúc quan trọng là **ai cần quyền ký token, và ai chỉ cần quyền xác minh?**

### Hai kiểu chính

**Kiểu A — HS256 (HMAC):** AS và những bên xác minh được cấp **cùng một secret**.

~~~mermaid
flowchart TD
    AS["Authorization Server giữ secret K"] -->|"HS256 JWT"| C["OAuth Client"]
    C --> O["Orders API có K để verify"]
    C --> P["Payments API có K để verify"]
    C --> R["Reports API có K để verify"]
    O -.->|"Bên biết K cũng có thể tạo HMAC hợp lệ"| P
~~~

**Hệ quả:** một Resource Server sở hữu secret để verify cũng **có khả năng tạo token HS256**. Đây là ranh giới tin cậy cần cân nhắc, không nhất thiết là điểm yếu của thuật toán HMAC.

**Kiểu B — chữ ký bất đối xứng:** AS giữ **private key**; các RS chỉ giữ **public verification key**.

~~~mermaid
flowchart TD
    AS["Authorization Server / private signing key"] -->|"Signed JWT"| C["OAuth Client"]
    C --> O["Orders API"]
    C --> P["Payments API"]
    C --> R["Reports API"]
    JWKS["Trusted JWKS: public verification key"] --> O
    JWKS --> P
    JWKS --> R
~~~

**Hệ quả:** RS có thể xác minh token mà không sở hữu signing private key. Đây thường là mô hình phù hợp khi có nhiều RS hoặc các miền tin cậy khác nhau.

### Bảng lựa chọn

| Tiêu chí | HMAC/HS256 | Asymmetric signing |
| --- | --- | --- |
| **Vật liệu tạo chữ ký** | Shared secret. | Private signing key. |
| **Vật liệu cần tại RS** | Chính shared secret đó. | Public verification key. |
| **RS có thể tự tạo token hợp lệ không?** | Có thể, nếu biết secret K. | Không, khi chỉ biết public key và private key an toàn. |
| **Phân phối khóa** | Phải phân phối bí mật an toàn tới từng verifier. | Có thể phân phối public key qua JWKS. |
| **Ảnh hưởng khi RS bị lộ verification material** | Có thể bị lộ signing secret. | Public key lộ không tự cho quyền ký. |
| **Độ phức tạp vận hành** | Secret rotation/replication và ACL. | Private key custody, JWKS, kid và rotation. |
| **Phù hợp nhiều RS** | Cần đánh giá trust domain rất cẩn thận. | Thường thuận lợi hơn về phân quyền ký/xác minh. |

**Không chọn HS256 chỉ vì ví dụ JWT library mặc định sinh secret ngắn.** Cũng không chọn RSA hoặc ECDSA chỉ vì “càng phức tạp càng an toàn”; phải căn cứ vào profile, vận hành, key custody và chính sách mật mã.

## 3. Phân biệt tạo khóa, ký token và xác minh

Ba hoạt động có trách nhiệm khác nhau:

~~~text
KEY GENERATION:
    sinh key material đủ entropy
    gắn issuer/purpose/algorithm
    lưu an toàn, đặt metadata/lifecycle

TOKEN SIGNING:
    kiểm grant/client/resource/scope
    tạo protected header + claims
    dùng signing key được phép và đang active

TOKEN VERIFICATION:
    chọn trusted issuer/key/algorithm
    verify JWS signature
    kiểm token type/aud/exp/scope/permission
~~~

**Tạo khóa không phải mint access token.** Một admin có quyền tạo signing key chưa chắc được phép cấp cho client quyền payments:approve. Ngược lại, signing service có private key nhưng không hiểu đầy đủ nghiệp vụ cần bị hạn chế **ai được yêu cầu nó ký dữ liệu nào**.

### Signing input quan trọng hơn JSON minh họa

Với JWS Compact thông thường:

~~~text
signingInput =
    BASE64URL(UTF8(protectedHeaderJson))
    + "."
    + BASE64URL(payloadBytes)
~~~

Chữ ký được tạo trên **bytes theo JWS profile**; không thể chỉ SHA256(payload JSON) rồi coi đó là JWT đã ký. Thư viện JOSE nên đảm nhiệm serialization và mật mã.

## 4. Chọn thuật toán signing key

Trong JSON Web Algorithms (JWA), một số lựa chọn phổ biến:

| JWS alg | Cơ chế | Vật liệu khóa | Điều kiện cơ bản |
| --- | --- | --- | --- |
| **HS256** | HMAC với SHA-256. | Secret ngẫu nhiên, tối thiểu **256 bit** theo JWA. | Verifier nào biết secret cũng có thể tạo tag. |
| **RS256** | RSASSA-PKCS1-v1_5 với SHA-256. | Cặp RSA private/public key. | RSA modulus theo JWA ít nhất **2048 bit**; chọn mức lớn hơn nếu policy yêu cầu. |
| **PS256** | RSA-PSS với SHA-256. | Cặp RSA private/public key. | PSS parameters tuân JWA; không nhầm RS256. |
| **ES256** | ECDSA P-256 với SHA-256. | EC P-256 private/public key. | Curve và JWS signature encoding đúng profile. |
| **ES384** | ECDSA P-384 với SHA-384. | EC P-384. | Chọn khi profile/requirements cần. |
| **EdDSA** | Edwards-curve signature, ví dụ Ed25519 theo profile. | Ed25519 private/public key. | Java/JOSE/HSM/RS phải hỗ trợ. |

### Một vài lựa chọn thực tế

- **RS256** tương thích với nhiều hệ sinh thái JWT/JWKS, nhưng sử dụng PKCS#1 v1.5 signature scheme.
- **PS256** dùng RSA-PSS; cần cùng tham số hash, MGF1 và salt length đúng chuẩn JWA khi ký/xác minh.
- **ES256** có chữ ký ngắn hơn RSA trong nhiều trường hợp, nhưng key/curve, nonce khi ký và JOSE encoding phải được xử lý đúng.
- **Ed25519/EdDSA** có những ưu điểm thực thi nhất định, nhưng phải xác nhận tất cả components hỗ trợ.
- **HS256** có thể hợp lý trong một trust domain nhỏ, với key dài, ngẫu nhiên và được bảo vệ, nhưng tạo rủi ro nếu phân phối secret ký cho nhiều verifiers.

**Không có thuật toán nào được phép chấp nhận chỉ vì JWT header tự khai alg đó.** AS ký theo một cấu hình khóa/thuật toán đã phê duyệt; RS verify theo allowlist và key type tương ứng.

### Key size phải theo profile và security policy

Ví dụ định hướng:

- HS256: tối thiểu **32 bytes secret ngẫu nhiên** để có 256 bit key, theo yêu cầu JWA; không dùng câu passphrase con người.
- RSA: JWA quy định key size tối thiểu 2048 bit cho các thuật toán RSA được nêu. Trong nhiều thiết kế mới, **3072 bit** là lựa chọn khi chính sách muốn mức khoảng 128-bit classical security và chấp nhận chi phí tăng; phải kiểm FIPS/NIST và policy tổ chức hiện hành.
- ES256: dùng **P-256/secp256r1**, không thay bằng curve tùy ý có cùng số bit.
- Ed25519: dùng scheme/curve Ed25519, không tự lấy 256 bit bất kỳ làm JWK riêng nếu thư viện chưa xác định key format.

**Độ dài khóa không phải tiêu chí duy nhất**: entropy, thuật toán, tham số, private key custody, algorithm agility và khả năng cập nhật trust trên RS đều quan trọng.

## 5. CSPRNG và entropy: nguồn gốc của khóa

**CSPRNG (Cryptographically Secure Pseudorandom Number Generator)** là nguồn ngẫu nhiên được thiết kế cho bảo mật, khác bộ sinh số ngẫu nhiên dùng trong mô phỏng hoặc trò chơi.

Sai:

~~~java
// KHÔNG làm: dự đoán được, không dùng để tạo signing secret.
java.util.Random random = new java.util.Random(12345L);
byte[] key = new byte[32];
random.nextBytes(key);
~~~

Sai về kiến trúc:

~~~text
key = SHA256("company-name" + currentTimestamp)
key = bytesOfRandomUUID()
key = UTF8("my-super-secret")
key = SHA256(adminPassword)
~~~

- Timestamp, tên công ty và password có entropy thấp/dự đoán được.
- UUID tạo bởi cơ chế không được xác định đúng có thể không đủ độ dài/entropy yêu cầu của signing key.
- Hash một input dễ đoán **không biến nó thành bí mật có entropy cao**.
- Không dùng seed cố định để tạo signing keys lặp lại giữa các môi trường.

### Nguồn ngẫu nhiên phù hợp

- **HSM/KMS key-generation API** theo môi trường và chính sách tổ chức.
- **Java SecureRandom** hoặc **KeyGenerator/KeyPairGenerator** sử dụng provider an toàn, được hệ điều hành/provider seed đúng.
- **OS cryptographic RNG** qua thư viện đáng tin.

Không tự viết PRNG/entropy mixing. Không truyền seed cố định chỉ để “tái lập” khóa; khóa production phải **không thể dự đoán từ build artifact hoặc cấu hình**.

### Lưu ý với SecureRandom trong Java

~~~java
import java.security.SecureRandom;

SecureRandom rng = new SecureRandom();

byte[] demoSecret = new byte[32];
rng.nextBytes(demoSecret);
~~~

Mã sử dụng API đúng mục đích nhưng **không có nghĩa mọi provider/runtime và môi trường là tương đương**. Với yêu cầu FIPS/HSM, tuân theo provider và cơ chế entropy đã được phê duyệt. Không tự hardcode seed để thay entropy.

**Không in giá trị demoSecret ra console**. Trong ví dụ giáo dục, có thể kiểm độ dài/thuật toán mà không tiết lộ key bytes.

## 6. Thiết kế bản ghi signing key trước khi phát hành

Signing key không chỉ là private key bytes; cần metadata và quản trị vòng đời.

| Trường quản trị | Ví dụ | Vai trò |
| --- | --- | --- |
| **issuer_id** | https://identity.example.test | Ràng khóa với issuer đáng tin. |
| **key_id / kid** | as-jws-2026-11-a | Chọn key trong trust set của issuer. |
| **algorithm** | PS256 | Định nghĩa alg được phép ký/verify. |
| **key_type / curve** | RSA / EC P-256 | Ngăn nhầm loại khóa với thuật toán. |
| **purpose** | oauth-access-token-signing | Không dùng chéo làm TLS/JWE/log key. |
| **environment** | prod | Tránh dùng chung key giữa dev/staging/prod. |
| **state** | PREPARED, ACTIVE, VERIFY_ONLY, RETIRED | Quản lý phát hành/kiểm và rotation. |
| **activation_at** | mốc triển khai đã phê duyệt | Khi nào bắt đầu ký. |
| **stop_signing_at** | mốc ngừng ký | Khi nào không phát token mới bằng khóa này. |
| **last_token_expiry_bound** | theo TTL AT/ID token | Xác định thời gian cần tiếp tục verify nếu không compromise. |
| **owner / approvals** | nhóm Identity Platform | Trách nhiệm thao tác và audit. |
| **key handle** | tham chiếu KMS/HSM | Định danh khóa, không phải raw private key. |
| **verification distribution** | trusted JWKS URI | Cách RS nhận public verification key. |

**kid không phải secret**, có thể xuất hiện trong JWS protected header và public JWKS. Nhưng kid cũng **không phải trust anchor**: RS phải biết issuer/JWKS/key purpose từ nguồn được cấu hình đáng tin.

### Key ID phải duy nhất trong trust set

Một issuer có thể dùng:

~~~text
kid = as-access-2026-11-a
kid = as-access-2027-03-b
~~~

Không cần kid duy nhất toàn thế giới; phải tránh mơ hồ trong một issuer/key set và profile. Đừng tái sử dụng kid cho key material khác trong thời gian RS có thể cache/nhận token với kid cũ.

## 7. Key lifecycle: chuẩn bị từ lúc sinh

~~~mermaid
flowchart TD
    A["PLAN / chọn issuer, alg, purpose, key policy"] --> B["GENERATE trong HSM/KMS hoặc provider an toàn"]
    B --> C["REGISTER metadata, kid và audit"]
    C --> D["PREPARED / public key sẵn sàng"]
    D --> E["ACTIVATE để ký token mới"]
    E --> F["VERIFY_ONLY / ngừng ký nhưng còn token cũ"]
    F --> G["RETIRED / loại khỏi trust set sau TTL"]
    G --> H["DESTROY / xóa key material theo policy"]

    E --> I{"Private key compromised?"}
    I -->|Có| J["EMERGENCY DISABLE và loại trust khẩn"]
    J --> K["Phát key sạch, ứng phó incident, kiểm RS"]
~~~

Các trạng thái là mô hình nội bộ, không phải enum chuẩn trong JWA. Hệ thống cần quy định rõ **khi nào key bắt đầu ký** và **khi nào RS còn được phép verify**.

### Hai mốc không trùng nhau

~~~text
Signing activation:
    AS bắt đầu dùng private K-new ký token.

Verification readiness:
    RS đã có public K-new và sẵn sàng verify.
~~~

Nếu AS bắt đầu ký trước khi RS nhận public key mới, request API có thể thất bại với unknown kid. Vì vậy quy trình thường cần **pre-publish verification key** hoặc cơ chế refresh JWKS an toàn.

### Retire không phải xóa private key tùy tiện

Key có thể cần được giữ hạn chế phục vụ rollback hợp lệ, audit hoặc compliance theo policy. Tuy nhiên, **kéo dài trust với key đã bị compromise là nguy hiểm**. Quy trình key destruction phải phân biệt:

- Key không còn dùng nhưng **không bị lộ**, có thể giữ verify-only public key tới khi token cũ hết hạn.
- Key **bị xâm phạm**, cần emergency stop/disable trust và phân tích ảnh hưởng.
- Private key backups/historical copies phải được quản lý cả khi key production đã rotate.

## 8. Signing key và token type/purpose separation

Một AS có thể phát:

- JWT **access token** cho RS.
- OIDC **ID token** cho Relying Party/client.
- **Client assertion** nếu AS/client sử dụng JWT cho client authentication.
- **Logout token** hoặc một loại JWT sự kiện theo profile.
- Internal service assertions nếu hệ thống riêng có hợp đồng.

**Không mặc định dùng cùng key cho mọi token type** chỉ vì tiện cấu hình.

### Khi nhiều token types dùng cùng signing key

Có thể triển khai hợp lệ theo profile nhưng tăng yêu cầu phân biệt token:

~~~text
Access token:
    typ = at+jwt
    aud = orders-api
    required claims theo access token profile

ID token:
    aud = dashboard-web
    required claims và OIDC validation riêng
~~~

Nếu RS chỉ kiểm chữ ký và issuer mà không kiểm token type/audience, một **ID token** có thể bị nhận sai như access token (cross-JWT confusion).

Các biện pháp phòng:

- Validator riêng cho từng purpose.
- Token type/profile và audience không thể nhầm.
- Key separation theo purpose khi phù hợp risk/kiến trúc.
- Không cấp signing capability của AS cho RS hoặc RP.
- Không coi ký đúng claims là quyền trên tài nguyên.

**Tạo signing key mới không tự giải quyết token substitution** nếu verifier vẫn chấp nhận mọi JWT cùng issuer.

## 9. Tạo khóa HMAC-SHA256 cho HS256

Với JWS **HS256**, khóa là một secret đối xứng. Chuẩn JWA yêu cầu khóa có ít nhất **256 bit** cho HS256.

### Java JCA: sinh secret ngẫu nhiên

~~~java
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSigningKeyDemo {

    public static void main(String[] args) throws Exception {
        // 32 bytes = 256 bits, phù hợp mức tối thiểu HS256.
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        // Demo: chứng minh secret dùng được với HmacSHA256.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));

        byte[] testMessage =
                "example-key-self-test".getBytes(
                        java.nio.charset.StandardCharsets.UTF_8);

        byte[] tag = mac.doFinal(testMessage);

        System.out.println("HMAC tag bytes: " + tag.length);
        System.out.println("Secret bytes: " + secret.length);

        // Best-effort cleanup cho mảng này.
        Arrays.fill(secret, (byte) 0);
        Arrays.fill(tag, (byte) 0);
    }
}
~~~

Ví dụ này **không tạo JWT** và không in secret. Key được tạo trong JVM chỉ phù hợp cho thử nghiệm/giải thích. Với production, lựa chọn key generation/secret storage nên gắn với KMS/HSM/secret management theo chính sách.

### Tại sao không dùng random password?

Không:

~~~text
HMAC secret = "password123"
HMAC secret = sha256("company-production")
HMAC secret = "2026-11-23" + deploymentRegion
~~~

Hashing một chuỗi dự đoán được **không tạo ra entropy mới**. Người tấn công có thể thử offline những giá trị dễ đoán khi có JWT HS256.

### Lưu và phân phối secret HS256

Đối với HS256:

- Secret phải được bảo vệ **ở AS và mọi verifier dùng secret**.
- Dùng secret manager/HSM hoặc cơ chế phù hợp; tránh đưa secret vào Git, CI logs, container image, config samples hoặc URL.
- Key rotation cần đồng bộ AS và những RS được phép verify.
- Không xuất secret sang dịch vụ không cần signing power.
- Phân tách secret theo issuer/environment/purpose; đừng chia một key giữa dev và production.
- Khi có nhiều RS, cân nhắc chữ ký số bất đối xứng để giảm số nơi lưu vật liệu có thể ký.

**JWK loại oct chứa symmetric key material là bí mật. Không bao giờ công khai JWK oct có trường k trong JWKS public.**

## 10. Tạo cặp khóa RSA cho RS256 hoặc PS256

Với chữ ký RSA, AS cần **private key** để ký và RS cần **public key** để verify.

### Java JCA: sinh RSA key pair

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.interfaces.RSAPublicKey;

public final class RsaSigningKeyGenerationDemo {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");

        // Ví dụ 3072-bit theo mục tiêu thiết kế.
        // Trong production, key có thể được tạo trong HSM/KMS.
        generator.initialize(3072, new SecureRandom());

        KeyPair pair = generator.generateKeyPair();

        RSAPublicKey publicKey =
                (RSAPublicKey) pair.getPublic();

        System.out.println(
                "RSA modulus bits: "
                + publicKey.getModulus().bitLength()
        );
        System.out.println(
                "Public exponent: "
                + publicKey.getPublicExponent()
        );

        // KHÔNG in hoặc xuất pair.getPrivate().
        // KHÔNG đặt private key trong public JWKS.
        // Dùng JCA Signature hoặc JOSE library để ký.
    }
}
~~~

**RSA 3072-bit chỉ là ví dụ lựa chọn mức khóa.** Kích thước và lifecycle phải theo profile, mức bảo mật, compliance và khả năng phần cứng. Với RS/PS algorithm trong JOSE, JWA quy định RSA modulus ít nhất 2048 bit; tổ chức có thể yêu cầu lớn hơn.

### RSA key pair không gắn chết vào một alg

Một RSA private key về mặt cấu trúc có thể được dùng bởi nhiều signature schemes, nhưng **đó không phải lý do cho phép một token tự chọn RS256 hoặc PS256 tùy ý**.

Từ lúc provisioning, hãy gắn:

~~~text
key_id:
    as-ps256-2026-11

approved_algorithm:
    PS256

purpose:
    oauth-access-token-signing

issuer:
    https://identity.example.test
~~~

Signing service phải kiểm thuật toán được phép cho key. RS phải chọn **verification algorithm phù hợp profile**, không “thử mọi RSA algorithm cho tới khi pass”.

### Tại sao không dùng RSA 1024-bit?

RSA 1024-bit không đáp ứng mức tối thiểu JWA cho RSA signing JWT và không thích hợp cho thiết kế mới. Đừng lấy các đoạn mã demo cũ dùng 1024-bit hoặc seed cố định rồi đưa vào production.

### Không in private key thành PEM trong logs

Mã demo thường có:

~~~text
printBase64(pair.getPrivate().getEncoded())
~~~

**Không làm trong production**: private key có thể bị copy vào terminal history, CI logs, support tickets và monitoring. Nếu HSM cung cấp **non-exportable private key**, không cố xuất key chỉ để dễ triển khai JWKS.

## 11. Tạo cặp khóa EC P-256 cho ES256

**ES256** dùng ECDSA trên **P-256/secp256r1** với SHA-256 theo JWA. Tạo đúng curve quan trọng hơn chỉ chọn kích thước 256.

### Java JCA: EC P-256 key pair

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;

public final class EcP256SigningKeyGenerationDemo {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("EC");

        generator.initialize(
                new ECGenParameterSpec("secp256r1"),
                new SecureRandom()
        );

        KeyPair pair = generator.generateKeyPair();

        ECPublicKey publicKey =
                (ECPublicKey) pair.getPublic();

        System.out.println(
                "EC field size bits: "
                + publicKey.getParams()
                        .getCurve()
                        .getField()
                        .getFieldSize()
        );

        // Không print private key.
        // Chữ ký JWS ES256 cần JOSE encoding r || s,
        // không copy ASN.1 DER signature thẳng vào JWS.
    }
}
~~~

### ECDSA cần nonce ký an toàn

- ECDSA signature generation dùng giá trị nonce/k; dùng lại hoặc sinh yếu có thể làm lộ private key.
- Dùng JCA provider/HSM/JOSE library đáng tin, không tự chọn k hoặc sửa tham số ngẫu nhiên.
- Chữ ký ECDSA của một số JCA providers có thể được trả ở dạng **ASN.1 DER**, còn JWS ES256 dùng **R || S** kích thước cố định theo JWA.
- Đừng tự lưu bytes chữ ký ECDSA vào JWT compact mà không hiểu encoding; để JOSE library xử lý.

### ES256 không tự tương đương Ed25519

P-256 ECDSA và Ed25519 là các thuật toán/curve khác nhau. Không tạo P-256 key rồi khai **alg=EdDSA**, cũng không xem public key chỉ có 256 bit là bất kỳ EC key nào đều dùng được.

## 12. Tạo cặp khóa Ed25519 khi profile hỗ trợ

Ed25519 là signature scheme thuộc nhóm Edwards-curve; trong JOSE truyền thống thường gắn với **EdDSA** theo RFC 8037, tùy thư viện/profile.

Ví dụ Java JCA trên runtime hỗ trợ (như các bản JDK hiện đại):

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.nio.charset.StandardCharsets;

public final class Ed25519KeyGenerationDemo {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");

        KeyPair pair = generator.generateKeyPair();

        byte[] message =
                "example-message".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signature)) {
            throw new SecurityException("Ed25519 self-test failed");
        }

        System.out.println("Ed25519 self-test: PASS");

        // Không log hoặc xuất private key.
        // Đoạn này chưa phải JWS signing input/compact token.
    }
}
~~~

Đây chỉ là **local signing self-test**, chưa tạo JWT/JWS hay kid/JWKS. Trước khi chọn Ed25519, phải xác minh:

- JDK/provider và JOSE libraries ở AS/RS hỗ trợ key type và alg theo profile.
- HSM/KMS có thực sự hỗ trợ sinh và ký Ed25519 hay không.
- Algorithm đã được phép theo compliance/security policy.
- Cách biểu diễn public JWK (ví dụ OKP với crv=Ed25519) được mọi RS hiểu.
- Cơ chế rotation, backup, test và emergency disable tương thích.

Không tự chuyển đổi Ed25519 key bytes thành RSA/EC JWK để “tương thích tạm thời”.

## 13. Local JCA key khác HSM/KMS non-exportable key

Các ví dụ Java ở trên tạo private key trong **bộ nhớ tiến trình**. Điều đó có ích để học nhưng chưa đạt yêu cầu quản trị khóa của nhiều hệ thống production.

### Khác nhau về nơi lưu private key

| Mô hình | Private key xuất hiện ở đâu? | Điều cần lưu ý |
| --- | --- | --- |
| **Java KeyPairGenerator local** | Trong JVM/process memory. | Có thể xuất qua getEncoded tùy provider; rủi ro memory dump/backups/logging. |
| **Encrypted key file/KeyStore** | Trên filesystem/secret store được bảo vệ. | Cần khóa bảo vệ, quyền đọc, backup/restore, rotation. |
| **KMS managed signing key** | Trong dịch vụ quản lý khóa theo provider. | Quyền gọi Sign, key policy, algorithm, availability, audit. |
| **HSM non-exportable key** | Trong security boundary của HSM. | Key generation/sign API, ACL/roles, HSM backup/domain và khả năng phục hồi. |

**Non-exportable không có nghĩa không thể lạm dụng.** Nếu attacker chiếm quyền gọi KMS Sign, họ có thể khiến signing service ký dữ liệu không hợp lệ dù key bytes không bị lấy ra.

### Cần tách các quyền

- Quyền **GenerateKey/CreateKey**: ai được tạo signing key mới?
- Quyền **Activate**: ai được đưa key vào signer production?
- Quyền **Sign**: service nào được yêu cầu tạo chữ ký bằng key?
- Quyền **GetPublicKey/JWKS Publish**: hệ thống nào được lấy public key?
- Quyền **Disable/Rotate**: ai được ngừng ký hoặc rút trust?
- Quyền **Delete/Destroy/Backup/Restore**: ai được xử lý key material và recover?

Có thể dùng **dual control/approval** cho activate, export (nếu policy cho phép), destroy và key compromise response. Quản trị theo **least privilege, JIT elevation và audit**.

### Phân tách quyền AS và KMS

~~~mermaid
flowchart LR
    A["Grant/Policy Engine"] -->|"Authorized signing request"| S["AS Signing Service"]
    S -->|"Sign với key handle + allowed algorithm"| K["HSM / KMS"]
    K -->|"Signature bytes"| S
    S -->|"Signed JWT"| C["OAuth Client"]
    P["Operations Admin"] -->|"Create/disable theo approval"| K
    J["Public JWKS Service"] -->|"Get public key only"| K
~~~

Signing service phải kiểm issuer, audience, token type, scope và grants **trước** khi yêu cầu KMS ký signing input. KMS thường chỉ bảo đảm key/alg/ACL của thao tác cryptographic Sign, không tự biết token có nên cấp cho client không.

## 14. Quy trình tạo khóa trong HSM/KMS

Một quy trình minh họa ở mức trừu tượng:

~~~text
1. Choose:
       issuer = https://identity.example.test
       purpose = oauth-access-token-signing
       algorithm = PS256
       key_policy = non-exportable asymmetric signing

2. Authorize:
       security-admin + change approval / JIT role

3. Generate:
       HSM/KMS GenerateAsymmetricSigningKey(
           algorithm = RSA signing,
           key_size = approved_size,
           exportable = false
       )

4. Register:
       key_handle = provider-specific opaque identifier
       kid = issuer-unique stable identifier
       state = PREPARED
       created_at, owner, alg, purpose, audit ID

5. Publish public verification key:
       derive/export public component ONLY
       validate JWK and trusted JWKS metadata

6. Self-test:
       Sign controlled JWS signing input via signing service
       Verify via a separate RS/JWKS consumer
       Reject tampered payload, wrong alg, wrong aud

7. Activate:
       signer begins using K-new after RS readiness

8. Observe:
       issuance logs, JWKS cache, signature/unknown-kid metrics
~~~

Đây là **pseudocode không phụ thuộc vendor**, không phải câu lệnh KMS/HSM cụ thể. API, mức độ exportable, backup/restore, service identity và thuật toán phụ thuộc nhà cung cấp.

### Key handle không phải private key

Một giá trị như:

~~~text
key_handle = kms://identity-prod/signing/ps256-key-v3
~~~

là **tham chiếu** do triển khai định nghĩa. Nó không nên cho phép người bất kỳ ký JWT chỉ bằng việc biết chuỗi handle. Quyền gọi KMS Sign vẫn cần authenticated service identity, authorization policy và audit.

### Sign API thường nhận message hoặc digest

Các KMS providers khác nhau có thể yêu cầu:

- **RAW message bytes** để KMS tự hash và ký.
- **Digest bytes** đã được caller hash trước.
- **Signature algorithm ID** và key version.

Không gửi SHA-256 digest cho API đang đợi raw message nếu nó sẽ hash một lần nữa; cũng không gửi raw message cho chế độ đã chọn là digest. Cả hai có thể dẫn đến chữ ký không đúng signing input/profile.

**Đặc biệt với JWS ES256**: kiểm cách KMS biểu diễn ECDSA signature và chuyển đổi DER ↔ JOSE R||S bằng thư viện có kiểm chứng.

## 15. Public JWKS: cái gì được phép công bố?

**JSON Web Key Set (JWKS)** là tập các JWK. Với asymmetric signing, JWKS công khai cho RS có thể chứa **public verification parameters**.

Ví dụ JWKS **mang giá trị placeholder không đủ để verify thật**:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "as-ps256-2026-11",
      "use": "sig",
      "alg": "PS256",
      "n": "EXAMPLE_BASE64URL_RSA_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

**Không paste nguyên ví dụ này vào production**: trường n chỉ là placeholder, không phải modulus RSA hợp lệ. Public JWK thật phải được xuất **từ public key tương ứng với private signing key**.

### Các trường JWK thường gặp

| Trường | Ý nghĩa |
| --- | --- |
| **kty** | Loại key: RSA, EC, OKP hoặc oct theo profile. |
| **kid** | Key identifier, giúp RS tra trong trusted key set. |
| **use** | Mục đích dùng khóa: sig (signature) hoặc enc (encryption), khi được khai. |
| **key_ops** | Tập thao tác như sign/verify khi được khai; cần nhất quán với use. |
| **alg** | Thuật toán dùng cho key theo policy/profile. |
| **n, e** | Public modulus và exponent của RSA JWK. |
| **crv, x, y** | Curve và public point cho EC JWK. |
| **crv, x** | Curve và public key bytes cho OKP JWK như Ed25519. |
| **d** | **Private key component** trong nhiều JWK bất đối xứng; không xuất ở public JWKS. |
| **k** | **Symmetric key material** của oct JWK; không xuất ở public JWKS. |

Các cấu trúc chi tiết theo RFC 7517/7518/8037. Không trộn RSA public parameters với EC/OKP keys, hoặc gắn alg không phù hợp loại key.

### Ví dụ EC public JWK

~~~json
{
  "kty": "EC",
  "kid": "as-es256-2026-11",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "EXAMPLE_BASE64URL_PUBLIC_X",
  "y": "EXAMPLE_BASE64URL_PUBLIC_Y"
}
~~~

x/y ở đây là placeholder, không phải tọa độ elliptic curve hợp lệ. Private scalar **d** không xuất hiện.

### Tuyệt đối không đưa private fields lên public JWKS

Nguy hiểm:

~~~json
{
  "kty": "RSA",
  "kid": "public-server-key",
  "d": "EXAMPLE_PRIVATE_COMPONENT_DO_NOT_PUBLISH"
}
~~~

Với RSA, các private CRT parameters khác ngoài d như p/q/dp/dq/qi cũng phải được bảo vệ. Với symmetric **oct**, trường **k** là secret. Có một endpoint JWKS public vô tình chứa private fields là **sự cố lộ signing key**, không phải chỉ là một bug định dạng.

### JWKS không xác nhận token được phép dùng ở mọi API

RS lấy public key đúng issuer từ JWKS, verify signature rồi vẫn phải kiểm:

- JWT token type/profile.
- iss, aud, exp/nbf, scope/client_id/sub theo profile.
- permission trên resource/tenant.
- revocation policy và sender proof nếu có.

**Public key là phương tiện kiểm chữ ký, không là giấy phép chung cho mọi token có chữ ký đúng.**

## 16. kid, key selection và issuer binding

Một JWS header có thể có:

~~~json
{
  "alg": "PS256",
  "typ": "at+jwt",
  "kid": "as-ps256-2026-11"
}
~~~

RS dùng kid để **chọn trong trust set đã cấu hình cho issuer**, chứ không tin header như authority về khóa.

### Key selection an toàn

~~~text
trustedIssuer = https://identity.example.test

1. Parse token theo JWT/JWS profile.
2. Kiểm header structure, allowed alg/key type.
3. Tra kid trong JWKS/key registry thuộc trustedIssuer.
4. Verify signature.
5. Kiểm iss đúng trustedIssuer.
6. Kiểm aud/type/time/scope/permission.
~~~

**Lưu ý:** issuer claim trong token ban đầu cũng chưa được tin. Khi RS chấp nhận nhiều issuer, nó cần trusted issuer selection/validation được thiết kế đúng, không gửi token hoặc chọn remote keys từ các header tùy ý.

### Rủi ro kid trùng

~~~text
Issuer A:
    kid = key-1

Issuer B:
    kid = key-1
~~~

Hai key IDs trùng không phải vi phạm toàn cục. Nhưng **RS không được lấy key Issuer B để xác minh token dự kiến do Issuer A cấp**. Key lookup phải ràng với issuer.

### Rủi ro jku/x5u/jwk header injection

Không dùng một URL do JWT tự nêu để tải khóa verify nếu URL đó ngoài trust policy. Attacker có thể đặt:

~~~json
{
  "alg": "RS256",
  "jku": "https://attacker.example.test/keys.json",
  "kid": "attacker-key"
}
~~~

Nếu RS tin public key từ đó, attacker có thể ký JWT bằng private key của mình rồi làm API nhận nhầm. Các header jwk/x5u/x5c cũng cần chính sách tin cậy chặt, không được tự override trusted issuer JWKS.

### kid không phải đường dẫn file/SQL

Sai:

~~~text
readFile("/keys/" + jwt.header.kid)
sqlQuery("SELECT key FROM keys WHERE kid='" + jwt.header.kid + "'")
~~~

Có thể tạo path traversal/SQL injection/key confusion. Dùng trusted key map, parameterized query khi cần và giới hạn header size/format. Unknown kid xử lý **fail closed** hoặc refresh JWKS có giới hạn từ trusted URI, không tự đổi issuer.

## 17. Kiểm thử signing key trước khi activation

Một key vừa sinh không nên được đưa ngay vào production mà không kiểm **ký → phân phối public key → xác minh**.

### Ma trận self-test

| Test | Điều chứng minh |
| --- | --- |
| **Public/private match** | Signature tạo bằng private key được public key tương ứng verify. |
| **Wrong public key** | Chữ ký không verify bằng key của issuer/key version khác. |
| **Wrong alg** | Không dùng cùng key với thuật toán ngoài policy. |
| **Tampered payload** | Sửa một byte của JWS signing input khiến verify fail. |
| **Tampered header** | Sửa protected header khiến verify fail. |
| **JWKS public only** | Không chứa d, k hay RSA CRT private fields. |
| **Unknown kid** | RS không chấp nhận key không thuộc trusted set. |
| **Correct issuer** | RS verify token trong đúng issuer trust context. |
| **Wrong issuer/audience** | Chữ ký hợp lệ vẫn bị token validator từ chối. |
| **Expired token** | Token exp cũ bị từ chối. |
| **Wrong type** | ID token không được dùng thay access token. |
| **Signing disabled key** | AS không mint token mới khi key ở verify-only/disabled. |
| **RS readiness** | Mọi RS cần thiết đã tải public key và verify trước activation. |
| **Audit** | Có record ai tạo/duyệt/kích hoạt, key handle, alg, kid. |

**Tự ký và tự verify bằng cùng thư viện chưa chứng minh tích hợp thành công**: cần thử từ một RS sử dụng **public JWKS và decoder thật** theo policy.

### Không đưa private key vào bài test end-to-end ở RS

Một test RS nên nhận **public key/JWKS** và JWT thử được ký bởi signing service test. Nếu một bài test phải copy production private key sang RS mới chạy được, thiết kế đang phá trust boundary.

## 18. Signing service: ai được sử dụng khóa vừa tạo?

**Sinh private signing key an toàn không có nghĩa token issuance đã an toàn.** HSM/KMS có thể bảo đảm private key không xuất ra ngoài, nhưng một dịch vụ có quyền gọi Sign tùy ý vẫn có thể tạo JWT giả nếu nó không kiểm chính sách.

### Thiết kế sai

Không cho client Internet gửi bất kỳ claims nào tới một signing endpoint rồi để server ký:

~~~http
POST /internal/sign-jwt HTTP/1.1
Host: identity.example.test
Content-Type: application/json

{
  "iss": "https://identity.example.test",
  "aud": "payments-api",
  "scope": "payments:approve"
}
~~~

Nếu bất kỳ caller nào gửi claims này cũng được ký, **key non-exportable không thay việc kiểm grant, scope, audience và client authorization**.

### Pipeline có phân quyền

~~~text
OAuth Client
    -> AS Token Endpoint
    -> authenticate client, validate grant
    -> enforce issuer/client/resource/scope policy
    -> create claims under AS authority
    -> select ACTIVE signing key for intended token type
    -> Sign JWS signing input through controlled KMS/HSM
    -> return signed token
~~~

| Thực thể | Quyền phù hợp |
| --- | --- |
| **AS Token Service** | Sign với key ACTIVE thuộc issuer/purpose đã đăng ký. |
| **Orders/Payments RS** | GetPublicKey/verify, không có Sign permission. |
| **Key Administrator** | Generate/Register/Activate theo approval, không mặc định mint token. |
| **Deployment Operator** | Deploy/observe, không được đọc raw private key. |
| **Security Responder** | Emergency Disable theo incident policy và audit. |
| **Untrusted Client** | Xin token theo OAuth flow, không gọi internal signing API. |

### Kiểm soát signing service

- Service identity hoặc IAM role riêng cho Sign, không phát một API key chung cho mọi workload.
- Rate limits/quotas, request-level audit, sign-count anomaly detection.
- Không cho caller chỉ định issuer/kid/key handle tùy ý để vượt policy.
- Signature algorithm phải ràng với key type, không tự dùng giá trị alg do token header gửi.
- Khi key disabled, không fallback sang key đã compromised.
- Không log full signing input chứa PII, client credentials hoặc token raw.
- KMS signing key không tự đánh giá business policy; **AS phải kiểm trước khi ký**.

## 19. Kích hoạt khóa và xác nhận RS readiness

Các mốc cần phân biệt:

~~~text
T_generate: Private K-new được tạo an toàn.
T_publish: Public K-new đã có trong trusted JWKS.
T_ready: Required RS đã verify được test JWT bằng K-new.
T_activate: AS bắt đầu ký JWT thật bằng K-new.
~~~

~~~mermaid
sequenceDiagram
    participant OPS as Key Operations
    participant KMS as HSM/KMS
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS
    participant RS as Resource Server

    OPS->>KMS: Generate K-new theo approved policy
    KMS-->>OPS: Key handle và public key
    OPS->>AS: Register kid, alg, issuer, PREPARED
    AS->>JWKS: Pre-publish public K-new
    RS->>JWKS: Refresh trusted issuer key set
    RS->>RS: Validate JWK và verify test JWT
    OPS->>AS: Activate K-new sau readiness checks
    AS->>KMS: Sign token mới bằng K-new
    KMS-->>AS: Signature
    AS-->>RS: Signed token
    RS->>RS: Verify + claims + permission
~~~

**Một khóa sinh thành công nhưng public JWKS chưa đến RS sẽ gây lỗi unknown kid** khi AS ký token mới.

### Checklist activation

1. Key sinh đúng algorithm/size/curve và đúng provider/HSM policy.
2. Private key không xuất hiện ở public JWKS/logs/build artifacts.
3. Metadata issuer, purpose, kid, alg, owner, state và activation schedule được ghi.
4. AS Sign permission chỉ cấp cho trusted signing service.
5. Public key được công bố qua JWKS của issuer đúng.
6. Các RS cần thiết có thể tải/verify public key K-new theo trusted metadata.
7. Tampered payload/header, wrong key, wrong alg, wrong issuer/audience đều bị từ chối.
8. Có rollback plan, metrics, change ID và approval/audit.

Nếu activation thất bại, **không tắt signature validation**. Có thể tạm ngừng ký bằng K-new hoặc dùng K-old chỉ khi K-old còn an toàn và policy cho phép.

## 20. Rotation: sinh khóa phải có kế hoạch thay khóa

~~~text
PREPARE:
    Generate K-new, register, self-test.

PUBLISH:
    Pre-publish K-new public verification key.

ACTIVATE:
    AS ký JWT mới bằng K-new.

VERIFY_ONLY:
    K-old không ký mới, public K-old có thể dùng verify
    các JWT còn hạn nếu key chưa bị compromised.

RETIRE:
    Loại K-old khỏi trusted RS key set theo TTL/policy.
~~~

### Vì sao giữ public key cũ?

Token được AS ký bằng K-old có thể vẫn còn hạn. Nếu K-old không bị lộ, RS cần public K-old cho đến khi token cuối cùng được phát bởi khóa đó hết hạn theo profile.

Công thức lập kế hoạch khái niệm:

~~~text
retireAfter >=
    lastIssuedAtWithOldKey
    + maximumTokenLifetimeAcrossRelevantProfiles
    + allowedClockSkew
    + keyDistributionMargin
~~~

Đây là **mô hình nội bộ**, không phải công thức RFC bất biến. Nếu private K-old bị xâm phạm, phải **rút trust khẩn cấp**, không chờ TTL.

### Không quên JWKS cache

Một RS có thể cache key lâu hơn dự kiến. Việc AS xóa K-old khỏi JWKS **chưa chứng minh RS đã loại key khỏi trust**. Dùng metrics, readiness probes và negative tests để xác nhận.

## 21. Backup, restore và khả năng sẵn sàng

Khi KMS/HSM không khả dụng, AS có thể không ký được JWT mới, ngay cả khi các RS vẫn verify token cũ.

| Vấn đề | Câu hỏi vận hành |
| --- | --- |
| **RTO/RPO** | Có thể ngừng phát token bao lâu? Metadata/audit có bị mất? |
| **Durability** | Key state sống qua restart/region outage không? |
| **Key backup** | Provider có hỗ trợ wrapped backup/non-exportable replication không? |
| **Restore approval** | Ai có quyền restore/import/activate key? |
| **JWKS consistency** | Sau failover public key nào cần được RS tin? |
| **Incident state** | Có vô tình restore key đã bị compromised không? |

**Không backup private key bằng cách copy plaintext PEM vào source repo hoặc shared storage**. Nếu HSM dùng non-exportable keys, không thiết kế DR dựa vào việc xuất raw private key trái policy.

Nếu DR tạo key mới, JWT ký bằng K-old **không tự verify bằng K-new**. Phải tính tới token re-issuance, trusted key rollover và session/client effects.

### Non-exportable không bảo đảm không thể bị lạm dụng

Nếu attacker có quyền gọi KMS Sign, họ có thể tạo signature hợp lệ mà không lấy được private bytes. Bảo vệ cả **key custody** và **authorization để sử dụng key**.

## 22. Tách khóa theo mục đích và trust domain

Các mục đích có thể cần key material độc lập:

~~~text
oauth-access-token-signing
oidc-id-token-signing
client-assertion-signing
webhook-hmac
logging-fingerprint-hmac
tls-server-private-key
data-encryption
~~~

Dùng chung HS256 secret cho nhiều RS khiến mọi nơi có signing capability. Dùng cùng key cho dev và prod tăng rủi ro cross-environment confusion. Dùng private OAuth key làm TLS key làm lẫn các vòng đời và policy.

**Đặt hai tên key khác nhau nhưng dùng cùng raw key bytes không tạo key separation thực sự.** Nên sinh độc lập. Nếu có kiến trúc dẫn xuất subkeys, cần KDF chuẩn như HKDF với label/context đúng và root key được bảo vệ, không tự nối chuỗi rồi hash.

JWK field use=sig hoặc key_ops=sign/verify chỉ là **metadata**; enforcement thực sự phải ở AS, KMS/HSM và RS.

## 23. Incident: signing key bị lộ

### HS256 secret bị lộ

Bất kỳ ai có secret có thể forge HMAC cho token. Cần disable/rotate secret cũ ở AS và mọi verifier, rà soát token giả, cùng kiểm issuer/audience/permission và dữ liệu đã truy cập.

**Chỉ tạo K-new nhưng RS vẫn tin K-old là chưa containment.**

### Private signing key bị lộ

Attacker có thể tự tạo JWT mới với sub/scope/exp/jti bất kỳ theo parser profile nếu các RS còn tin K-old.

1. Dừng signing bằng K-old.
2. Sinh K-new trong HSM/KMS môi trường sạch.
3. Công bố public K-new và triển khai signing mới.
4. **Loại K-old khỏi trusted RS key sets**, kể cả JWKS cache, gateway, edge và replicas.
5. Cấp lại token hợp lệ nếu cần, chấp nhận việc revoke key có thể ảnh hưởng nhiều user.
6. Điều tra request bất thường, token giả, root cause và các bản backup/private copies.
7. Đo enforcement SLO; chỉ báo xong khi các RS quan trọng thực sự từ chối K-old.

**Denylist jti đã biết không đủ** nếu attacker nắm private key, vì họ có thể tạo jti mới. Cần rút **trust anchor**.

## 24. Monitoring và audit key lifecycle

Metrics/events gợi ý:

~~~text
SIGNING_KEY_GENERATED
SIGNING_KEY_REGISTERED
SIGNING_KEY_PUBLIC_PUBLISHED
SIGNING_KEY_ACTIVATED
SIGNING_KEY_VERIFY_ONLY
SIGNING_KEY_RETIRED
SIGNING_KEY_DISABLED
SIGNING_KMS_ACCESS_DENIED
SIGNING_KMS_SIGN_ERROR
JWT_UNKNOWN_KID
JWT_SIGNATURE_INVALID
JWT_UNSUPPORTED_ALG
JWT_WRONG_ISSUER
JWKS_REFRESH_FAILURE
JWKS_CACHE_STALE
~~~

Theo dõi:

- Unknown kid/invalid signature rate sau key activation.
- Sign operation latency, volume, error rate và callers.
- Token còn được ký bằng K-old sau mốc stop-signing.
- Số RS chưa refresh K-new hoặc chưa rút K-old compromised.
- Administrative actions thiếu approval/ngoài change window.
- Signing key misuse, unusual token TTL/scope/audience.

### Audit không được làm lộ key

~~~text
timestamp
change_id / incident_id
actor_id / service_identity
issuer_id, environment
key_handle / kid
algorithm, purpose, action
approval_reference
result / error_code
~~~

Không log private key, HMAC secret, raw JWT/RT, client secret hoặc full signing input nhạy cảm. Nếu raw key xuất hiện trong logs, xử lý như **credential exposure incident**.

## 25. Kiểm khóa mới bằng Java: sign rồi verify

Sau khi tạo cặp khóa, một **local self-test** giúp phát hiện key pair không tương ứng hoặc provider không hỗ trợ algorithm. Ví dụ sau dùng **RSA-PSS** với SHA-256 và tham số salt length 32 bytes (phù hợp nhóm tham số PS256 trong JOSE).

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class RsaPssSigningSelfTest {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator keys =
                KeyPairGenerator.getInstance("RSA");
        keys.initialize(3072, new SecureRandom());

        KeyPair pair = keys.generateKeyPair();

        // Dữ liệu demo, không phải JWS signing input thực tế.
        byte[] message =
                "new-signing-key-self-test".getBytes(
                        StandardCharsets.UTF_8);

        PSSParameterSpec ps256LikeParameters =
                new PSSParameterSpec(
                        "SHA-256",
                        "MGF1",
                        MGF1ParameterSpec.SHA256,
                        32,
                        1
                );

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(ps256LikeParameters);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(ps256LikeParameters);
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signature)) {
            throw new SecurityException("RSA-PSS self-test failed");
        }

        Signature tamperCheck = Signature.getInstance("RSASSA-PSS");
        tamperCheck.setParameter(ps256LikeParameters);
        tamperCheck.initVerify(pair.getPublic());
        tamperCheck.update(
                "tampered-self-test".getBytes(StandardCharsets.UTF_8)
        );

        if (tamperCheck.verify(signature)) {
            throw new SecurityException("Tampered content was accepted");
        }

        System.out.println("RSA-PSS key self-test: PASS");
    }
}
~~~

**Đây không phải code phát token PS256 production.** JWT ký một **JWS signing input** được định nghĩa chuẩn, với header/payload/encoding đúng JOSE. Cần dùng JOSE library để phát token, còn HSM/KMS signing API phải được nối theo đúng chế độ raw/digest và cách biểu diễn chữ ký.

### Bản self-test cần thêm những gì?

- **Wrong public key** không được verify signature.
- **Wrong algorithm** bị từ chối theo signer/verifier policy.
- **JOSE token** từ AS được một RS riêng verify qua trusted public JWKS.
- **Wrong issuer, wrong audience, wrong token type** bị từ chối dù signature đúng.
- **Expired/nbf/scope thiếu** bị từ chối theo token validation policy.
- **Disabled key** không thể ký JWT mới qua signing service.
- **Public JWKS** không có private fields.
- **Concurrent activation/rotation** không gây unknown kid hoặc fallback sang trust ngoài allowlist.

Self-test local chỉ là một tầng. **End-to-end test phải dùng các components và cấu hình issuer/RS thực tế** trong môi trường được phép, không copy private signing key sang Resource Server.

## 26. Các tình huống thiết kế thường gặp

### Case A — Startup tạo lại RSA key mỗi lần chạy

Một AS service có code tự sinh RSA key pair mới mỗi lần container khởi động. Các JWT đã phát trước restart dùng K-old, còn JWKS sau restart chỉ chứa K-new.

**Hậu quả:** RS có thể không còn verify được JWT cũ, user gặp 401 dù token chưa hết hạn. Nếu nhiều AS replicas tạo khóa riêng, cùng một issuer có thể phát token với kid/key material không đồng nhất.

**Cách thiết kế đúng:**

1. Tạo signing key qua **quy trình quản lý khóa tập trung**.
2. Lưu key handle/state và public key trong registry tin cậy, không phụ thuộc lifecycle container.
3. Các AS replicas dùng signing key/version theo cùng control-plane state.
4. Prepublish JWKS và rotation có kế hoạch.
5. Khi restart hoặc scale, không tự tạo key mới nếu chưa có một key-generation operation được duyệt.

### Case B — Hai môi trường dùng cùng HS256 secret

Staging và Production dùng cùng một HMAC key do copy cấu hình. Staging bị lộ config, attacker có thể giả token HS256 nếu production verifier dùng cùng key và policy issuer/audience lỏng.

**Bài học:** sinh key độc lập theo environment, issuer và purpose; không dựa chỉ vào biến APP_ENV trong claims để tạo tách biệt mật mã. Production RS phải kiểm issuer/aud/type chặt và không chấp nhận JWT staging.

### Case C — JWKS vô tình chứa private d

Một pipeline tự serialize full RSA JWK vào endpoint public JWKS và xuất trường d hoặc private CRT fields.

**Mức độ:** đây là **lộ private signing key**, không phải một lỗi hiển thị thông thường.

**Phản ứng:** khóa/rotate key, rút public trust với key đã lộ, điều tra bản sao JWKS trong caches/CDN/logs và áp incident playbook. Chỉ xóa field d khỏi response sau khi khóa đã lộ **không đủ**.

### Case D — Ký token mới trước khi RS biết kid

AS chuyển sang K-new; RS đang cache JWKS chỉ có K-old. JWT mới có kid K-new và bị từ chối.

**Cách sửa:** prepublish K-new, xác minh các RS đã hỗ trợ key/alg mới trước activation; refresh JWKS từ URI tin cậy và có throttling. Không lấy jku bất kỳ từ token để bỏ lỗi unknown kid.

### Case E — KMS non-exportable nhưng signing API mở quá rộng

Private key không thể export, nhưng internal signing API cho một service yếu quyền được phép ký claims tùy ý. Attacker chiếm service đó và yêu cầu ký JWT có scope admin.

**Bài học:** non-exportable chỉ bảo vệ **key material**, không bảo vệ mọi **signing operations**. Cần hạn chế caller, key purpose, TTL/scope/audience, issuance approvals và audit.

### Case F — Dùng public RSA key như HMAC secret

Một JWT verifier cho phép cả HS256 và RS256, chọn alg từ header, dùng cùng key bytes cho hai cách verify. Attacker dùng public key (không bí mật) để tạo HMAC tag trên token giả.

**Kết quả đúng:** verifier phải có allowlist và key-type binding; RS256-only endpoint **từ chối token HS256** dù HMAC dùng public key bytes có tag tương ứng.

### Case G — K-new được tạo trong HSM nhưng thuật toán chưa được RS hỗ trợ

AS chọn Ed25519, trong khi một số RS dùng JOSE library chưa hiểu OKP/EdDSA JWK. Token mới nhận 401.

**Cách làm:** test compatibility **trước activation**, hoặc chọn algorithm được cả AS/RS và compliance policy hỗ trợ. Không tự chuyển public Ed25519 key sang EC P-256 hay bỏ signature validation để “tương thích”.

### Case H — Signing key compromise và JWKS cache

Attacker có private K-old. AS rotate sang K-new và gỡ K-old khỏi JWKS, nhưng nhiều RS vẫn cache public K-old.

**Rủi ro:** attacker vẫn có thể ký JWT giả được các RS đó chấp nhận.

**Cách xử lý:** emergency trust removal, cache invalidation, kiểm từng RS/edge/replica, đo SLO và audit. Không chỉ nhìn trạng thái KMS DisableKey rồi tuyên bố đã ngăn forge.

## 27. Negative tests cho quy trình tạo signing key

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| **HS256 256-bit secret** | Tạo 32 bytes bằng CSPRNG. | Key đáp ứng tối thiểu HS256 theo JWA. |
| **HMAC secret ngắn** | 8 bytes hoặc passphrase. | Bị policy từ chối. |
| **Fixed-seed RNG** | Dùng deterministic seed dễ đoán cho production key. | Security review/test từ chối. |
| **Same key after restart** | AS khởi động lại. | Không tự rotate/mint key ngoài change process. |
| **Two replicas** | Hai AS instances cùng issuer. | Ký bằng key/version được registry đồng bộ. |
| **RSA key quá ngắn** | 1024-bit RSA cho RS256. | Từ chối theo JWA/policy. |
| **RSA wrong alg** | Key PS256 được dùng ký RS256 trái policy. | Signer từ chối. |
| **RSA private/public match** | Sign với private K-new, verify với public K-new. | Thành công. |
| **RSA wrong public key** | Verify bằng K-other. | Thất bại. |
| **RSA payload tamper** | Sửa signing input sau ký. | Verify thất bại. |
| **PSS wrong salt/hash params** | Parameters lệch profile PS256. | Verify thất bại. |
| **EC wrong curve** | Key P-384 dùng cho ES256. | Bị từ chối theo alg/curve policy. |
| **ECDSA bad nonce** | Provider/test harness dùng nonce cố định. | Không chấp nhận implementation yếu. |
| **ECDSA bad JOSE encoding** | Dùng raw DER signature trong ES256 JWS. | Decoder từ chối. |
| **Ed25519 unsupported** | RS/JOSE library không hiểu EdDSA. | Không activate trước readiness; không bỏ verify. |
| **KMS unauthorized Generate** | Caller không có GenerateKey permission. | Access denied, audit. |
| **KMS unauthorized Sign** | RS cố gọi Sign. | Bị từ chối. |
| **KMS signing service overgrant** | Untrusted caller yêu cầu ký scope admin. | Sign bị chặn bởi issuance policy. |
| **KMS unavailable** | Sign timeout/throttle. | Không fallback ký bằng compromised key. |
| **Public JWKS only** | Export public RSA/EC/OKP fields. | Không có private d, p, q, dp, dq, qi hoặc symmetric k. |
| **Symmetric JWK leak** | JWK oct có k xuất ra public endpoint. | Fail build/deploy security gate; incident nếu đã xuất. |
| **Unknown kid** | Token nêu kid không thuộc trusted JWKS. | RS từ chối/refresh trusted JWKS có giới hạn. |
| **kid duplicate** | Hai keys cùng issuer/key set trùng kid. | Registry từ chối mơ hồ. |
| **kid reused** | Key mới dùng kid cũ còn trong cache. | Không activate cấu hình gây nhầm key. |
| **Same kid across issuers** | Issuer A và B cùng kid. | RS không dùng key sai issuer. |
| **Untrusted jku** | JWT chỉ tới JWKS attacker. | RS không tải/tin key đó. |
| **Embedded private JWK** | Header/endpoint chứa private material. | Từ chối và báo sự cố. |
| **alg=none** | JWT không chữ ký. | RS từ chối. |
| **HS/RS confusion** | HS256 tag được tạo từ public RSA key bytes. | RS256-only verifier từ chối. |
| **Wrong key use** | Encryption key được dùng để ký. | Signer từ chối theo policy. |
| **Wrong environment** | Key staging ký token prod. | Production RS từ chối. |
| **Wrong token type** | ID token đưa đến Orders API. | RS từ chối type/aud. |
| **Wrong issuer** | JWT ký bởi issuer khác. | RS từ chối. |
| **Wrong audience** | JWT Payments tới Orders. | RS từ chối dù chữ ký đúng. |
| **Expired token** | exp trong quá khứ. | RS từ chối. |
| **Missing scope** | AT không có orders:read. | RS từ chối endpoint. |
| **Cross-tenant** | Token hợp lệ nhưng tài nguyên sai tenant. | RS từ chối permission. |
| **K-new prepublish** | K-new vào JWKS trước activation. | RS verify được canary token. |
| **Unknown key after activation** | Một RS chưa refresh JWKS. | Rollout phát hiện, không giảm bảo mật. |
| **Old key verify-only** | AS bị yêu cầu ký bằng K-old. | Từ chối Sign; RS có thể verify token cũ hợp lệ. |
| **Compromised key disabled** | K-old bị lộ. | Mọi RS bắt buộc rút trust đúng SLO. |
| **JWKS cache stale** | RS còn tin K-old compromised. | Test phát hiện fail containment. |
| **Backup restore compromised** | DR thử phục hồi K-old đã bị đánh dấu compromised. | Bị ngăn theo policy. |
| **Private key in logs** | Debug ghi private PEM. | Security gate phát hiện, xử lý lộ key. |
| **Secret in CI config** | HMAC key bị commit vào repo. | Secret scanning phát hiện, rotate. |
| **Audit missing approval** | Admin activate key trái policy. | Bị chặn và audit. |
| **Key deletion without review** | Xóa key còn JWT chưa hết hạn. | Bị chặn hoặc yêu cầu approval theo policy. |
| **Repeated activation request** | Retry idempotency. | Không tạo nhiều key versions trái ý định. |
| **Signer algorithm fallback** | PS256 Sign fail, service thử RS256 tùy tiện. | Bị chặn, không tự đổi alg. |
| **Signing burst** | Caller sign số lượng bất thường. | Rate limit/alert; không lộ private key. |

### Bộ test nhỏ bắt buộc

~~~text
A. Sign with private K-new -> verify with public K-new: PASS.
B. Tamper payload -> verify signature: FAIL.
C. Use public K-other or wrong algorithm -> verify: FAIL.
D. Use valid signature but wrong audience/type -> RS DENY.
E. Disable signing key -> AS cannot mint using it.
F. Publish only public JWK; reject leaked private JWK.
~~~

## 28. Checklist production cho bài “Tạo signing key”

1. **Issuer:** Key thuộc issuer và trust domain nào?
2. **Purpose:** Có mục đích cụ thể như AT, ID token, client assertion không?
3. **Trust model:** Ai ký, ai verify? Có cần private/public separation?
4. **Algorithm:** HS256, RS256, PS256, ES256 hoặc EdDSA được profile/policy cho phép?
5. **Key strength:** HMAC secret, RSA modulus hoặc EC curve đáp ứng yêu cầu?
6. **Entropy:** Sinh từ CSPRNG/HSM/KMS, không dùng seed cố định/password/timestamp?
7. **Environment:** Không dùng chung key giữa staging và production khi policy yêu cầu tách?
8. **Key custody:** Private key/non-exportable secret được giữ trong boundary an toàn?
9. **No export:** Có ngăn private material xuất ra debug, logs, build artifact, JWKS?
10. **Access control:** AS signing service mới có quyền Sign? RS chỉ lấy public key?
11. **MFA/JIT/approval:** Key administrators có bước phê duyệt phù hợp rủi ro?
12. **Metadata:** Key được đăng ký issuer, kid, alg, kty, use, purpose, owner, state?
13. **kid uniqueness:** Không trùng mơ hồ trong issuer key set, không reuse tùy tiện?
14. **JWKS:** Chỉ công bố public parameters, không chứa d/k/private CRT fields?
15. **Trusted JWKS:** RS tải từ issuer đã cấu hình, không tin jku/jwk bất kỳ?
16. **Key type binding:** Không dùng HS256 secret làm RSA public verification key hoặc ngược lại?
17. **Algorithm allowlist:** alg=none và thuật toán ngoài policy bị từ chối?
18. **Self-test:** Sign/verify với private/public match và tampering fail?
19. **End-to-end:** RS verify qua JWKS thật, không cần copy private key?
20. **Claims:** Token vẫn bị kiểm issuer, audience, exp, type, scope và permission?
21. **Token separation:** ID/AT/assertion/logout validators không bị trộn?
22. **Activation:** Đã prepublish public key và kiểm RS readiness?
23. **Rotation:** Có mốc stop-signing, verify-only, retirement theo TTL?
24. **Compromise:** Có emergency disable và rút trust khỏi JWKS caches/RS?
25. **Backups:** Có DR/recovery theo key custody policy, không backup plaintext?
26. **Disabled key:** Signing service không mint token bằng key không còn ACTIVE?
27. **Observability:** Có metrics unknown kid, invalid signature, KMS errors, activation lag?
28. **Audit:** Có actor, approver, key handle, action, time và outcome mà không log secret?
29. **Rate limits:** KMS Sign không bị lạm dụng bởi service bị chiếm?
30. **Key separation:** Không tái sử dụng signing key cho webhook, logging, TLS hoặc encryption vô tội vạ?
31. **SLO:** Có thể xác nhận mọi RS đã trust K-new hoặc rút K-old theo yêu cầu?
32. **Negative tests:** Đã test key confusion, jku, wrong alg, wrong issuer/aud, cache stale và compromise?

## Kết luận

**Tạo signing key** là một quyết định kiến trúc về **nguồn entropy, thuật toán, trách nhiệm ký, phạm vi tin cậy và vòng đời**, không chỉ là gọi KeyPairGenerator hoặc tạo một secret 32 bytes.

- Với **HS256**, cần HMAC secret ngẫu nhiên đủ mạnh và phải hiểu **mọi verifier biết secret đều có thể tạo MAC hợp lệ**.
- Với **RS256/PS256/ES256/EdDSA**, cần tạo đúng key pair/curve trong provider được phê duyệt, giữ **private key** tại Authorization Server/HSM/KMS và công bố **public verification key** qua JWKS đáng tin.
- Một key vừa tạo phải có **issuer, kid, alg, purpose, activation state, ownership và rotation plan**. Chỉ activate sau khi RS sẵn sàng xác minh chữ ký.
- Signing API phải được **ủy quyền và kiểm soát**; key không xuất được vẫn có thể bị lạm dụng để ký claims sai khi AS bị compromise.
- **Chữ ký hợp lệ chỉ là một bước**: RS vẫn phải kiểm token type, issuer, audience, thời hạn, scope, principal, revocation và business permission.

Một hệ thống token an toàn phải coi signing key như **gốc tin cậy có vòng đời đầy đủ**: sinh đúng, bảo vệ, công bố public key đúng, giới hạn quyền ký, giám sát, rotation, backup/restore và xử lý khẩn khi khóa bị lộ.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8037 — CFRG Elliptic Curve EdDSA for JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-133 Rev. 2 — Recommendation for Cryptographic Key Generation](https://csrc.nist.gov/pubs/sp/800/133/r2/final)
- [NIST SP 800-90A Rev. 1 — Recommendation for Random Number Generation Using Deterministic Random Bit Generators](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final)
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [OWASP JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)




