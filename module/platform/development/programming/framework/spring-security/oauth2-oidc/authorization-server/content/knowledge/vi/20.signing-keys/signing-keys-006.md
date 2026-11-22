# Lưu khóa ổn định qua restart và chia sẻ khóa giữa các instance

## Mục tiêu bài học

Trong chương **JWK và quản lý khóa** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn thiết kế nơi lưu trữ và phân phối khóa ký JWT để **Spring Authorization Server** giữ được danh tính khóa qua restart và mọi instance trong cụm có thể xác minh token nhất quán. Nội dung tập trung vào **Spring Security**, **Spring Authorization Server** và ứng dụng **Spring Boot** chạy một hoặc nhiều replica.

Một Authorization Server không thể tạo một cặp khóa ký ngẫu nhiên mới mỗi lần khởi động rồi kỳ vọng các token cũ vẫn được Resource Server xác minh. Khóa private cần được bảo vệ và tồn tại ổn định; public key tương ứng phải được công bố qua JWKS, có định danh **kid** ổn định và được các Resource Server tin cậy. Khi triển khai nhiều instance, các instance phải dùng cùng tập khóa đang hoạt động và có chiến lược rotation đồng bộ.

Sau bài học, bạn có thể:

- Phân biệt private signing key, public verification key, JWK, JWK Set và JWKS endpoint.
- Hiểu vì sao tạo khóa mới khi startup làm token cũ hỏng sau restart hoặc rolling deployment.
- Thiết kế nơi lưu trữ bền vững bằng KMS/HSM, secret manager, keystore hoặc encrypted persistent storage.
- Cấu hình Spring Authorization Server dùng **JWKSource<SecurityContext>** và **NimbusJwtEncoder** từ khóa ổn định.
- Chia sẻ khóa đúng cách giữa nhiều Authorization Server instance, xử lý cache và đồng bộ rotation.
- Giữ public key cũ trong JWKS trong thời gian token cũ còn hiệu lực và cache có thể tồn tại.
- Kiểm thử restart, scale-out, rolling deploy, failover, key rotation và khôi phục dữ liệu.
- Bảo vệ private key, giới hạn quyền ký, audit và lập runbook khi khóa bị lộ.

> **Tình huống xuyên suốt:** Cụm Authorization Server có ba instance sau load balancer. Mỗi instance cấp JWT access token cho API nội bộ. Sau khi instance A restart hoặc request đi qua instance B, token đã cấp phải tiếp tục được xác minh. Khi rotation, token ký bằng khóa cũ vẫn hợp lệ trong thời gian chuyển tiếp, còn token mới dùng khóa mới.

## 1. Vì sao khóa phải ổn định qua restart?

JWT access token thường được ký bằng private key. Resource Server nhận JWT và dùng public key để xác minh chữ ký. Nếu mỗi lần Authorization Server khởi động lại tự sinh một cặp khóa mới, public key mà Resource Server từng dùng có thể không còn khớp với token đang lưu hành.

Ví dụ:

~~~mermaid
flowchart TD
    A[Instance A startup] --> K1[Generate key K1]
    K1 --> T1[Issue JWT signed by K1]
    T1 --> R1[Resource Server verifies with public K1]
    A --> X[Restart]
    X --> K2[Generate unrelated key K2]
    K2 --> T2[Issue JWT signed by K2]
    T1 --> F[Old token still in circulation]
    R1 -->|Only K2 published| E[Signature verification fails for T1]
~~~

Token T1 chưa hết hạn nhưng chữ ký không còn xác minh được nếu JWKS chỉ công bố public key K2. Người dùng có thể thấy API trả 401 ngay sau khi deploy, dù access token còn thời hạn.

Các tình huống tương tự xảy ra khi:

- Một pod mới được tạo và tự sinh khóa riêng.
- Auto-scaling tạo thêm instance với khóa khác.
- Instance A ký token nhưng Resource Server lấy JWKS từ instance B.
- Rolling deployment làm một số node dùng key set cũ, số khác dùng key set mới.
- Database/secret store phục hồi không đúng snapshot hoặc mất metadata của key ID.
- Public key cũ bị xóa khỏi JWKS trước khi token cũ và cache của Resource Server hết hạn.

**Nguyên tắc:** Khóa ký đang hoạt động phải được lưu bền vững và phân phối theo một nguồn tin cậy. Tất cả instance được phép ký phải chọn đúng cùng khóa active; tất cả instance công bố JWKS phải trả tập public key tương thích.

## 2. Phân biệt private key, public key, JWK và JWKS

| Khái niệm | Nội dung | Ai được phép truy cập? |
|---|---|---|
| Private signing key | Thành phần bí mật dùng ký JWT. | Chỉ Authorization Server hoặc KMS/HSM được ủy quyền ký. |
| Public verification key | Thành phần công khai dùng kiểm chữ ký. | Resource Server và bên nhận token. |
| JWK | Biểu diễn một khóa theo JSON Web Key, có thể chứa public hoặc private material. | Public JWK có thể công bố; private JWK phải được bảo vệ nghiêm ngặt. |
| JWK Set | Một tập JWK trong object JSON có trường `keys`. | Tập công khai được công bố qua JWKS. |
| JWKS endpoint | HTTP endpoint trả public JWK Set, thường `/.well-known/jwks.json` theo metadata. | Client/resource server được phép tải public keys. |
| kid | Key ID trong JWS header, dùng chọn đúng public key trong JWKS. | Công khai, nhưng phải duy nhất trong tập khóa có liên quan. |

JWK có thể mô tả khóa RSA, EC hoặc loại khóa khác. Ví dụ public RSA JWK rút gọn:

~~~json
{
  "kty": "RSA",
  "kid": "auth-signing-2026-01",
  "use": "sig",
  "alg": "RS256",
  "n": "PUBLIC_MODULUS_BASE64URL",
  "e": "AQAB"
}
~~~

Đây là placeholder, không phải khóa sử dụng thật. **Không bao giờ công bố** các trường private như RSA `d`, `p`, `q`, `dp`, `dq`, `qi` hoặc EC private scalar `d`. Private JWK phải nằm trong hệ thống quản lý bí mật; JWKS công khai chỉ trả public parameters.

### 2.1. kid là định danh, không phải bí mật

JWS header thường có:

~~~json
{
  "alg": "RS256",
  "kid": "auth-signing-2026-01",
  "typ": "JWT"
}
~~~

Resource Server dùng `kid` để chọn khóa xác minh trong JWKS. `kid` phải ổn định cho cùng một key material và khác nhau giữa các khóa khác nhau đang được công bố. Không dùng thời gian hiện tại hoặc số ngẫu nhiên mỗi lần process khởi động làm `kid` cho cùng một private key.

**Không tin `alg` do JWT tự khai báo một cách mù quáng.** Resource Server phải giới hạn thuật toán được chấp nhận theo policy. Key ID chỉ giúp chọn khóa, không chứng minh token hợp lệ; chữ ký và các claims vẫn phải được xác minh.

## 3. Vì sao mỗi instance không được tự tạo khóa độc lập?

Một cluster có ba instance A, B, C cần đảm bảo:

- A có thể ký JWT và B/C không phát hành một khóa không được công bố.
- Bất kỳ Resource Server nào tải JWKS từ load balancer cũng nhận tập public key hợp lệ.
- Token được A ký vẫn xác minh được khi request sau đi tới C.
- Instance mới khi scale-out nạp cùng key set và trạng thái active.
- Restart không tạo key ID mới cho cùng một khóa hoặc mất private key đang ký.
- Rotation được triển khai theo một phiên bản key set có thứ tự và đồng bộ.

Sơ đồ kiến trúc:

~~~mermaid
flowchart TB
    subgraph Cluster[Authorization Server cluster]
        A[AS instance A]
        B[AS instance B]
        C[AS instance C]
    end
    S[(Shared secure key store / KMS / HSM)]
    A -->|load active key / sign| S
    B -->|load active key / sign| S
    C -->|load active key / sign| S
    A --> JWKS[JWKS public endpoint]
    B --> JWKS
    C --> JWKS
    JWKS --> R1[Resource Server 1]
    JWKS --> R2[Resource Server 2]
    A -->|JWT signed by active key| API[Protected API]
~~~

Tập public keys mà mỗi instance công bố phải nhất quán. Trong trường hợp dùng KMS/HSM, private key có thể không rời thiết bị ký; ứng dụng gọi API ký thông qua key handle. Trong trường hợp keystore/secret manager, ứng dụng có thể nạp private key vào memory theo quyền được cấp, nhưng không được lưu plaintext tùy tiện vào image hoặc filesystem tạm.

**Không nên dùng một khóa riêng cho mỗi pod** nếu tất cả token cùng issuer cần được Resource Server xác minh qua một JWKS chung, trừ khi kiến trúc đã thiết kế rõ key distribution, JWKS aggregation và rotation cho từng signing identity.

## 4. Chọn nơi lưu trữ khóa ổn định

Không có một nơi lưu khóa phù hợp mọi tổ chức. Chọn theo mức độ bảo mật, compliance, khả năng vận hành, khả năng backup và yêu cầu ký phân tán.

| Phương án | Private key được giữ ở đâu? | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|---|
| KMS/HSM | Thiết bị/dịch vụ quản lý khóa; ứng dụng gọi ký qua API. | Khóa có thể không xuất khỏi boundary bảo mật, audit và IAM rõ. | Cần latency, quota, HA, quyền KMS và tích hợp signer/JWK phù hợp. |
| Secret manager | Secret/keystore được mã hóa, phân phối tới instance. | Dễ tích hợp container/orchestrator và rotation. | Bảo vệ quyền đọc; không để secret lộ qua env dump/log hoặc filesystem. |
| PKCS#12/JKS trên persistent secret volume | Keystore chứa private key được mã hóa bằng password. | Có thể tích hợp Java KeyStore/JCA; dễ hiểu. | Password và volume cần bảo vệ; không bake vào container image. |
| Encrypted database/object storage | Private key/JWK mã hóa ở storage có access control. | Lưu metadata, key status, version và audit tập trung. | Phải mã hóa envelope bằng KMS, transaction/locking, backup và recovery. |
| File local trên persistent disk | Private key/keystore trên volume bền vững. | Đơn giản cho triển khai nhỏ. | Khó chia sẻ nhiều node, backup/permission/rotation phải tự quản lý. |
| Generate lúc startup | Mỗi process tự sinh cặp mới. | Không cần provisioning. | **Không phù hợp** cho issuer cần token sống qua restart hoặc multi-instance. |

### 4.1. Mô hình khuyến nghị

Một mô hình production thường gồm:

1. **Key generation/provisioning** thực hiện qua quy trình quản trị riêng, không tạo ngẫu nhiên mỗi lần app khởi động.
2. **Private key** nằm trong KMS/HSM hoặc secret store mã hóa; quyền ký chỉ cấp cho workload Authorization Server.
3. **Key metadata** lưu ổn định: key ID, algorithm, use, trạng thái active/retiring/revoked, thời điểm tạo/kích hoạt/ngừng ký và version.
4. **Public JWK** được công bố qua JWKS và có thể lưu cùng metadata.
5. **Active key selection** dùng một cấu hình/record có tính nhất quán, để mọi instance ký bằng cùng key trong một giai đoạn.
6. **Rotation workflow** tạo key mới, công bố public key, chuyển active signer, giữ key cũ để xác minh token cũ rồi mới gỡ.
7. **Backup/recovery** kiểm thử được; backup private key phải bảo vệ tương đương key gốc.

Không ghi private key vào Git, Docker image, Kubernetes ConfigMap, log, crash dump công khai hoặc file temp không được bảo vệ. Secret manager và KMS phải có IAM tối thiểu, audit và alert khi truy cập bất thường.

### 4.2. Mã hóa khi lưu và phân quyền

Nếu private key được lưu trong DB hoặc object storage, nên dùng **envelope encryption**: dữ liệu khóa mã hóa bằng data key, data key được KMS bảo vệ. Ứng dụng chỉ được quyền giải mã/ ký trong workload identity cần thiết. Tránh tự xây thuật toán mã hóa bằng một password hard-code.

Quyền đọc public JWK có thể rộng; quyền sử dụng private key để ký phải hẹp. Nếu ứng dụng cần chỉ ký mà không đọc/export private key, ưu tiên API ký của KMS/HSM khi tích hợp được với JWT encoder.

## 5. Tạo JWK ổn định một lần và lưu vào keystore

Đối với môi trường development hoặc triển khai nhỏ, có thể tạo RSA key pair **một lần** bằng quy trình provisioning, lưu trong PKCS#12/JKS được bảo vệ, sau đó mount keystore như secret volume. Mọi instance nạp cùng keystore/key ID.

### 5.1. Tạo keystore bằng keytool

Ví dụ tạo keystore test:

~~~bash
keytool -genkeypair \
  -alias authorization-signing-2026 \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -dname "CN=Authorization Server Signing Key" \
  -storetype PKCS12 \
  -keystore auth-signing.p12
~~~

Lệnh sẽ yêu cầu nhập password. Đây là thao tác **provisioning một lần** trong môi trường được bảo vệ, không chạy trong Docker entrypoint mỗi lần startup. Với production, key size/algorithm, validity, password policy và KMS/HSM cần theo chuẩn tổ chức và yêu cầu thuật toán hiện hành.

Private key alias là `authorization-signing-2026`. Không đưa file `auth-signing.p12` và password vào source control hoặc artifact công khai.

### 5.2. Nạp key pair từ PKCS#12 vào JWK

Ví dụ Java minh họa đọc keystore đã được mount từ secret volume, lấy private/public key và tạo RSA JWK:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;

RSAKey loadSigningJwk(
        Path keystorePath,
        char[] storePassword,
        char[] keyPassword) throws Exception {

    KeyStore keyStore = KeyStore.getInstance("PKCS12");
    try (InputStream input = Files.newInputStream(keystorePath)) {
        keyStore.load(input, storePassword);
    }

    String alias = "authorization-signing-2026";
    RSAPublicKey publicKey =
            (RSAPublicKey) keyStore.getCertificate(alias).getPublicKey();
    RSAPrivateKey privateKey =
            (RSAPrivateKey) keyStore.getKey(alias, keyPassword);

    return new RSAKey.Builder(publicKey)
            .privateKey(privateKey)
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .keyID("authorization-signing-2026")
            .build();
}
~~~

Đoạn code là ví dụ nạp key; trong ứng dụng thực cần xử lý exception cụ thể, đóng/clear password char arrays khi có thể, cấp file permission, xác thực alias/certificate tồn tại, kiểm tra key pair khớp và tránh log object chứa private key. Không expose phương thức này qua endpoint công khai.

Nếu dùng cùng keystore trên nhiều instance, mọi instance phải nhận **cùng một version** của secret và password qua secret manager, với quyền truy cập tối thiểu. Việc cập nhật keystore phải có cơ chế version/rollout đồng bộ, không ghi đè file đang được process sử dụng mà không có kế hoạch reload.

### 5.3. Tạo JWKSource và JwtEncoder

Sau khi nạp JWK ổn định, có thể tạo JWK source:

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@Configuration(proxyBeanMethods = false)
class SigningKeyConfiguration {

    @Bean
    JWKSource<SecurityContext> jwkSource(RSAKey signingJwk) {
        return new ImmutableJWKSet<>(new JWKSet(signingJwk));
    }

    @Bean
    JwtEncoder jwtEncoder(JWKSource<SecurityContext> jwkSource) {
        return new NimbusJwtEncoder(jwkSource);
    }
}
~~~

Đây là cách dựng **JWKSource từ JWK Set đã nạp**. Cần bean cung cấp `RSAKey signingJwk` từ keystore/secret store như ví dụ trên. Với `ImmutableJWKSet`, JWK Set là snapshot được tạo khi ứng dụng khởi động; thay file/secret sau đó **không tự cập nhật** bean này. Muốn rotation không restart hoặc cần nhiều key cùng lúc, cần JWKSource có khả năng nạp/refresh tập khóa theo version, hoặc triển khai rotation bằng rolling restart có kiểm soát.

Không dùng cùng một `RSAKey` object có private parameters để trả qua JWKS endpoint. Endpoint JWKS chỉ nên trả public JWK. Spring Authorization Server có thể dùng cùng JWKSource để phục vụ metadata/JWKS; phải xác nhận public projection và cấu hình endpoint của phiên bản đang dùng không bao giờ serialize private parameters.

### 5.4. Vì sao ví dụ này không phải giải pháp HSM?

`NimbusJwtEncoder` cần lấy được JWK phù hợp để ký theo cơ chế encoder. Khi private key không thể export khỏi HSM/KMS, việc tích hợp có thể cần signer/encoder adapter dùng remote signing API, JCA provider hoặc cơ chế tương thích của nhà cung cấp. Không giả định chỉ cần đổi file keystore thành URI KMS là `NimbusJwtEncoder` tự ký từ xa.

Với HSM/KMS, giữ public JWK metadata (modulus/exponent hoặc EC public point), key ID và thuật toán trong JWKSource; thao tác ký được ủy quyền tới KMS/HSM. Adapter phải đảm bảo chữ ký trả về đúng JWS format/algorithm, xử lý timeout/retry/idempotency và không fallback sang khóa local không được phê duyệt.

## 6. Chia sẻ khóa giữa các instance

### 6.1. Mọi instance cần cùng key set và active key

Trong cluster, cách đơn giản là mỗi instance khởi động từ cùng phiên bản keystore được mount qua secret manager. Cách này phù hợp nếu rotation được triển khai theo đợt và restart có kiểm soát.

Với key store động hoặc KMS/HSM, các instance cùng truy cập một nguồn key metadata và có thể ký bằng cùng key ID. Cần đảm bảo:

- Active key ID được công bố từ nguồn có tính nhất quán.
- Tất cả instance nhận biết key mới trước khi bắt đầu ký bằng nó.
- Public key của key mới đã có trên JWKS trước khi phát token mới.
- Tất cả instance vẫn có public key cũ trong thời gian cần xác minh token cũ.
- Instance không được phép ký nếu không lấy được trạng thái key hợp lệ.
- Không có node tự sinh key thay thế khi key store/KMS tạm thời unavailable.

### 6.2. Tránh race condition khi rotation

Nếu active key được lưu trong database, không cho mỗi instance tự quyết định active key bằng “key mới nhất theo timestamp” mà không có transaction/version rõ ràng. Có thể lưu một record cấu hình active key với version tăng đơn điệu, thay đổi bằng thao tác quản trị có audit.

Ví dụ mô hình metadata (minh họa, không phải schema Spring Authorization Server cung cấp sẵn):

| key_id | algorithm | status | created_at | sign_from | sign_until | verify_until | version |
|---|---|---|---|---|---|---|---|
| auth-signing-2026-01 | RS256 | RETIRING | 2026-01-01 | 2026-01-01 | 2026-11-01 | 2026-11-02 | 7 |
| auth-signing-2026-11 | RS256 | ACTIVE | 2026-11-01 | 2026-11-01 | — | — | 8 |

Các trạng thái như ACTIVE/RETIRING/REVOKED là **quy ước của ứng dụng**, không phải enum built-in của JWK. Hãy định nghĩa chuyển trạng thái và quyền phê duyệt rõ. Khi có nhiều region, cần quy định propagation delay và thời điểm kích hoạt; không chuyển active trước khi tất cả Resource Server có thể tải public key mới theo SLA.

### 6.3. JWKS endpoint phải trả tập public key thống nhất

Ví dụ JWKS có hai public keys trong thời gian overlap:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "auth-signing-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "OLD_PUBLIC_MODULUS",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "auth-signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "NEW_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Trong ví dụ, JWKS trả public key cũ và mới để Resource Server xác minh token đang lưu hành. Không trả private fields. Nếu các instance sau load balancer trả JWKS khác nhau trong cùng giai đoạn, Resource Server có thể tải nhầm tập khóa và lỗi ngẫu nhiên theo node.

Resource Server có thể cache JWKS. Vì vậy sau khi thêm key mới, phải tính đến thời gian cache/refresh của Resource Server. Không phát token bằng key mới trước khi public key tương ứng được công bố và có thể được lấy; không xóa key cũ ngay khi dừng ký.

## 7. Rotation: thêm key mới trước, gỡ key cũ sau

Một quy trình rotation an toàn có ba pha chính:

~~~mermaid
flowchart LR
    A[Phase 1: Publish new public key] --> B[Phase 2: Switch active signer]
    B --> C[Phase 3: Retire old public key after overlap]
    A --> A1[Both public keys visible]
    B --> B1[New JWTs use new kid]
    C --> C1[Old tokens expired/cache window passed]
~~~

### 7.1. Pha 1 — Provision và công bố public key mới

1. Tạo key pair mới trong KMS/HSM/keystore qua quy trình quản trị.
2. Cấp key ID mới, ví dụ `auth-signing-2026-11`.
3. Lưu metadata, public JWK và private signing handle vào key store.
4. Cập nhật JWKS để công bố **public key mới**, vẫn giữ key cũ.
5. Đợi propagation và JWKS cache refresh theo SLA; kiểm tra từ các Resource Server/region.

Trong pha này, Authorization Server vẫn có thể ký bằng key cũ. Public key mới chưa được dùng để ký token cho đến khi chắc chắn consumer có thể xác minh.

### 7.2. Pha 2 — Chuyển active signer

1. Cập nhật active key ID bằng một thao tác có version/transaction.
2. Các instance nạp active key mới hoặc nhận event reload đáng tin cậy.
3. Kiểm tra JWT mới có header `kid` mới và chữ ký hợp lệ.
4. Xác nhận mọi instance đều ký bằng key mới; node chưa đồng bộ không được tiếp tục ký bằng trạng thái cũ nếu policy yêu cầu đồng nhất.
5. Giữ public key cũ trong JWKS để token cũ tiếp tục được xác minh.

Không rotate bằng cách thay private key trên một pod rồi kỳ vọng mọi node khác tự cập nhật. Dùng secret version, rollout đồng bộ hoặc cơ chế phân phối key có trạng thái rõ.

### 7.3. Pha 3 — Gỡ public key cũ

Chỉ xóa public key cũ khi:

- Token cuối cùng được ký bằng key cũ đã hết hạn theo TTL tối đa.
- Clock skew/leeway của Resource Server đã được tính.
- Các cache JWKS và cache introspection liên quan đã qua thời gian cần thiết.
- Không còn token/cookie/queue/job hợp lệ phụ thuộc token cũ.
- Không có rollback nào cần key cũ để xác minh token mới phát trong giai đoạn trước.

Ví dụ, nếu access token TTL tối đa là 15 phút và cho phép clock skew 2 phút, không xóa public key cũ ngay 15 phút sau lần ký cuối. Cần cộng thời gian propagation/cache và khoảng an toàn được vận hành thống nhất.

### 7.4. Rotation bình thường khác xử lý compromise

Nếu private key **bị lộ**, không chờ token cũ hết hạn theo quy trình bình thường. Cần incident response: dừng ký bằng key bị lộ, loại key khỏi tập tin cậy theo mức khẩn cấp, chuyển sang key sạch, xác định token có thể bị giả mạo, đánh giá thu hồi session/token, thông báo Resource Server refresh JWKS/denylist và lưu bằng chứng audit.

Xóa public key compromised khỏi JWKS có thể làm token hợp lệ đã ký trước đó thất bại, nhưng đây có thể là hành động cần thiết khi mức độ rủi ro yêu cầu. Quy trình khẩn cấp phải được diễn tập, có owner và phê duyệt sẵn.

## 8. Tách cấu hình ký token và công bố JWKS

Authorization Server cần hai khả năng liên quan nhưng khác nhau:

- **Signing path:** lấy private key hoặc key handle để ký token.
- **Verification/publication path:** cung cấp public key tương ứng qua JWKS.

Một JWK Set có thể chứa cả private và public parameters trong memory của signer, nhưng response JWKS chỉ được phép xuất public key. Khi dùng KMS/HSM, signer có thể giữ private key bên ngoài process trong khi JWKSource chỉ chứa public key metadata.

### 8.1. Kiểm tra JWKS endpoint

Sau khi cấu hình issuer và JWKSource, lấy metadata OIDC/OAuth2 Authorization Server tương ứng để tìm URL JWKS. URL có thể khác nhau theo phiên bản/cấu hình. Kiểm tra endpoint thực tế:

- Trả JSON JWK Set với top-level `keys`.
- Có public key cho từng `kid` đang được dùng để ký token.
- Không có RSA/EC private parameters.
- Không bị proxy cache quá lâu trong khi rotation cần refresh.
- HTTPS, hostname và issuer nhất quán.
- Tất cả instance sau load balancer trả tập public key tương thích.

Không hard-code JWKS URI của một node nội bộ trong Resource Server. Dùng issuer metadata/discovery hoặc cấu hình public JWKS URI đúng theo trust model của hệ thống.

### 8.2. Tạo token và kiểm tra kid

Lấy một access token JWT ở môi trường test, decode **header** để kiểm tra `kid` và `alg`; sau đó xác minh chữ ký bằng public JWKS. Decode payload không phải xác minh token. Resource Server phải kiểm cả `iss`, `aud`, `exp` và scope/claims.

Một token được ký bằng key ID không xuất hiện trong JWKS có thể bị từ chối cho đến khi key được công bố. Nếu token header có `kid` trùng nhưng key material bị thay, chữ ký vẫn phải fail; không tái sử dụng `kid` cho key khác.

## 9. Kiểm thử restart, scale-out và recovery

Kiểm thử một lần cấp token trên cùng instance là chưa đủ. Bài toán của chủ đề là **khóa tồn tại qua thay đổi vòng đời process và topology**.

### 9.1. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
|---|---|
| Cấp token, restart cùng instance | Token cũ vẫn xác minh; JWT mới dùng cùng active key nếu chưa rotation. |
| Cấp token ở A, verify qua B | Chữ ký hợp lệ, public key nằm trong JWKS chung. |
| Scale từ 1 lên 3 instance | Mọi node dùng cùng key set/active key ID. |
| Request JWKS qua load balancer nhiều lần | Không có node trả public key set thiếu/khác ngoài kế hoạch rotation. |
| Rolling deploy | Token ký bởi node cũ và node mới đều được xác minh trong overlap. |
| Rotation pha 1 | JWKS có key cũ và key mới, signer vẫn dùng key cũ. |
| Rotation pha 2 | JWT mới có kid mới; JWT cũ vẫn xác minh. |
| Rotation pha 3 | Public key cũ chỉ bị gỡ sau khi hết token/cache window. |
| KMS/HSM tạm unavailable | Server không fallback sang key không được phép; báo lỗi và metric. |
| Secret manager không truy cập được khi startup | Instance fail readiness/startup theo policy; không tự generate key mới. |
| Restore DB/keystore từ backup | Key ID, key material và active version khớp; token còn hạn vẫn verify. |
| Private key bị revoke/compromise | Runbook khẩn cấp dừng ký, cập nhật JWKS/trust và xử lý token liên quan. |
| Hai key cùng kid nhưng khác material | Test phát hiện và chặn; kid không được tái sử dụng. |

### 9.2. Ví dụ kiểm thử bằng Java

Đoạn test dưới mô tả ý tưởng: token ký trước restart phải xác minh bằng public JWK nạp lại từ cùng key store sau restart. Nó không phải test tích hợp hoàn chỉnh:

~~~java
@Test
void tokenSignedBeforeRestartRemainsVerifiable() throws Exception {
    RSAKey beforeRestart = keyStoreLoader.load("auth-signing-2026-01");
    JwtEncoder encoderBefore = new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(beforeRestart)));

    String token = issueTestJwt(encoderBefore, "inventory-api");

    // Mô phỏng process mới: nạp lại cùng key version từ persistent store.
    RSAKey afterRestart = keyStoreLoader.load("auth-signing-2026-01");
    JwtDecoder decoderAfter = decoderFor(afterRestart.toPublicJWK());

    assertThat(decoderAfter.decode(token).getSubject())
            .isEqualTo("inventory-worker");
}
~~~

`keyStoreLoader`, `issueTestJwt` và `decoderFor` là helper giả định cần triển khai trong test fixture. Trong integration test thật, nên khởi động lại application context/instance hoặc tạo hai app context độc lập với cùng key store; đừng chỉ dùng chung object trong memory vì như vậy không kiểm tra persistence.

### 9.3. Kiểm thử nhiều instance thực tế

- Chạy ít nhất hai Authorization Server instance với cùng version key store.
- Gọi Token Endpoint qua instance A, rồi xác minh token ở Resource Server cấu hình lấy JWKS qua instance B.
- Lặp lại với load balancer phân phối JWKS request đến các node khác nhau.
- Thực hiện rotation khi đang có request cấp token; xác minh không phát token với kid chưa được công bố.
- Dừng một instance và kiểm tra node còn lại tiếp tục cấp token đúng key.
- Mô phỏng mất KMS/secret manager và kiểm tra readiness/alert.
- Restore backup trong staging rồi kiểm tra token cũ, key ID, JWKS và rotation state.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JWT cũ fail sau restart | Startup tự sinh key mới hoặc key store không persistent. | Nạp cùng key material và kid từ persistent source. |
| Token do A ký fail khi verify qua B | Mỗi instance có key riêng hoặc JWKS node không đồng nhất. | Dùng shared key source/metadata và kiểm public JWKS qua load balancer. |
| JWKS có key nhưng signature fail | Public key không khớp private key đang ký, kid bị tái sử dụng hoặc key sai. | Kiểm fingerprint/key pair, kid và signing configuration. |
| JWKS thiếu kid của token mới | Signer switch trước khi public key được publish/refresh. | Publish key trước, chờ propagation rồi chuyển active. |
| Token cũ fail ngay khi rotate | Public key cũ bị xóa quá sớm hoặc Resource Server cache không phù hợp. | Giữ overlap theo TTL + skew + cache window. |
| Instance mới không startup | Secret/KMS permission, key alias/password hoặc network sai. | Kiểm IAM, secret version, keystore alias và readiness logs đã redact. |
| Một node ký bằng key cũ sau cutover | Active key state không đồng bộ hoặc cache không reload. | Dùng version/coordination, drain node stale hoặc fail closed. |
| JWKS lộ private parameters | Serialize JWK private object thay vì public projection. | Chỉ publish public JWK; test response không có private fields. |
| KMS ký chậm/timeout | Quota, network hoặc HSM capacity. | Timeout, bulkhead, metric và capacity plan; không fallback key yếu. |
| Khôi phục backup nhưng token vẫn fail | Backup thiếu private key, key version hoặc metadata active. | Backup đồng bộ material/metadata; diễn tập recovery. |
| Resource Server không thấy key mới | JWKS cache lâu hoặc refresh strategy không chạy. | Điều chỉnh cache/refresh, publish key trước khi dùng. |
| Cùng kid nhưng key đổi | Kid không unique/stable. | Không tái sử dụng kid; cấp ID mới cho key material mới. |

## 11. Runbook vận hành và kiểm soát truy cập

### 11.1. Quyền truy cập tối thiểu

- Authorization Server runtime chỉ có quyền **sign** hoặc đọc đúng private key cần dùng; không cấp quyền quản trị/xóa key nếu không cần.
- Resource Server chỉ cần public JWKS hoặc quyền introspection; không bao giờ cần private signing key.
- CI/CD chỉ triển khai reference/version của secret; không đọc/export private key.
- Operator rotation có quyền được phê duyệt và audit, không dùng tài khoản ứng dụng hàng ngày.
- Backup operator và incident responder có quyền riêng, có MFA/approval và log.

### 11.2. Metric và alert nên có

- Key ID đang active theo từng instance (chỉ metadata công khai).
- Số JWT ký thành công/thất bại, latency và lỗi KMS/HSM.
- Thời điểm public JWK được publish và độ trễ propagation.
- Số instance đang dùng key version cũ sau cutover.
- JWKS response consistency/hash theo version (không hash private material vào log).
- Lần truy cập secret/key bất thường, export attempt, permission denied.
- Thời điểm key hết hạn/chứng chỉ hết hạn (nếu dùng certificate).

Không ghi private key, password keystore, KMS credentials hoặc raw JWT vào metric label. Không gửi key material qua chat/log để chẩn đoán.

### 11.3. Backup và disaster recovery

Backup phải bao gồm **khóa có thể khôi phục**, public metadata, key ID, trạng thái active/retiring, version và quy trình lấy quyền KMS. Với HSM không exportable, recovery phụ thuộc cơ chế backup/replication chính thức của thiết bị/dịch vụ; đừng giả định snapshot DB chứa đủ private key.

Diễn tập ít nhất:
1. Khôi phục key store trong môi trường cách ly.
2. Khởi động Authorization Server mới với key version đã backup.
3. Xác minh JWT còn hạn ký trước sự cố.
4. Cấp token mới và xác minh bằng Resource Server.
5. Kiểm tra JWKS, issuer, kid và active key state.
6. Xác nhận audit/permission sau restore.

## 12. Bài tập thực hành

**Bối cảnh:** Authorization Server ban đầu chạy một instance và dùng khóa RSA sinh khi startup. Sau khi triển khai ba replica sau Kubernetes Service, API đôi lúc trả 401 cho token vừa được cấp. Khi restart, phần lớn token đang hoạt động cũng fail.

Hãy thiết kế và triển khai kế hoạch khắc phục:

1. Mô tả nguyên nhân của việc mỗi pod có một cặp key độc lập.
2. Chọn KMS/HSM, secret manager hoặc PKCS#12 trên persistent secret volume; giải thích trade-off và quyền truy cập.
3. Provision một RSA key pair ổn định với key ID riêng; lưu private key an toàn và public JWK để công bố.
4. Tạo `JWKSource<SecurityContext>` và `JwtEncoder` dùng cùng key version ở mọi instance.
5. Xác minh JWKS chỉ chứa public parameters, mỗi key có kid ổn định.
6. Chạy hai instance, cấp token từ A và verify qua Resource Server truy cập JWKS qua B.
7. Restart/scale-out/rolling deploy; xác minh token cũ còn hạn vẫn hoạt động.
8. Thực hiện rotation ba pha: publish key mới, chuyển signer, gỡ key cũ sau overlap.
9. Mô phỏng KMS/secret manager unavailable; xác minh không tự sinh khóa fallback.
10. Viết runbook compromise key và diễn tập backup/recovery trong staging.

**Tiêu chí hoàn thành:** token đã cấp vẫn xác minh qua restart/replica; mọi node có cùng key set và active key; public JWKS không lộ private material; rotation không làm hỏng token còn hạn; recovery có thể khôi phục cả key lẫn metadata.

## 13. Checklist trước khi production

- [ ] Private signing key được provision ổn định, không generate mới ở mỗi startup.
- [ ] Có nơi lưu trữ bền vững và mã hóa; quyền ký được cấp theo least privilege.
- [ ] Public key được công bố qua JWKS; private parameters không xuất hiện trong response.
- [ ] kid ổn định cho cùng key và không tái sử dụng cho key material khác.
- [ ] JWKSource/JwtEncoder được cấu hình từ nguồn khóa tin cậy.
- [ ] Tất cả instance ký bằng active key nhất quán và công bố public key tương ứng.
- [ ] Instance mới/scale-out/restart nạp cùng key version.
- [ ] Immutable JWK Set snapshot được reload/restart có kiểm soát khi rotation.
- [ ] JWKS cache/propagation được tính trước khi bắt đầu ký bằng key mới.
- [ ] Public key cũ được giữ trong overlap đủ TTL, clock skew và cache window.
- [ ] Key compromise có quy trình emergency rotation/revocation riêng.
- [ ] KMS/HSM/secret manager có HA, quota, timeout, audit và cảnh báo.
- [ ] Backup/recovery bao gồm key material hoặc cơ chế HSM backup cùng metadata.
- [ ] Đã test token sau restart, giữa các instance, rolling deployment, rotation và failover.
- [ ] Resource Server xác minh signature, issuer, audience, expiry và policy.
- [ ] Không có private key, password, raw JWT hoặc secret trong Git/log/trace/image.

## Tổng kết

Khóa ký JWT phải **tồn tại ổn định qua vòng đời process** và được chia sẻ theo một nguồn tin cậy giữa các instance cùng issuer. Spring Authorization Server sử dụng **JWKSource** để cung cấp khóa cho **NimbusJwtEncoder** và phục vụ public JWK theo cấu hình. Framework không tự biến một khóa sinh trong memory khi startup thành kho khóa bền vững; ứng dụng phải thiết kế provisioning, storage, access control, active key selection, rotation và recovery.

Khi rotation, hãy **công bố public key mới trước**, chuyển signer sau khi consumer có thể xác minh, rồi chỉ gỡ public key cũ khi token cũ và cache không còn cần nó. KMS/HSM, secret manager hoặc encrypted keystore đều có thể phù hợp nếu quyền ký, đồng bộ, HA, audit và disaster recovery được thiết kế đầy đủ. Thành công của bài toán được chứng minh bằng kiểm thử token qua restart, scale-out, rolling deployment và failover, không chỉ bằng việc một instance tạo được JWT.

## Tài liệu tham khảo

1. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): JWKSource, NimbusJwtEncoder, JWT token generation và token customization.
2. [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình Authorization Server, issuer và JWKS endpoint.
3. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT và lấy public keys qua JWKS.
4. [Nimbus JOSE + JWT — JWK Set](https://connect2id.com/products/nimbus-jose-jwt/examples/jwk-set): biểu diễn JWK/JWK Set và public/private key material.
5. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set, key use, key operations và public/private key parameters.
6. [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS protected header, algorithm và kid.
7. [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán chữ ký và tham số khóa.
8. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata endpoint và jwks_uri.
9. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata và jwks_uri cho OIDC.
10. [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): vòng đời, bảo vệ, backup và rotation khóa mật mã.
11. [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): lưu trữ khóa và quản lý bí mật.

