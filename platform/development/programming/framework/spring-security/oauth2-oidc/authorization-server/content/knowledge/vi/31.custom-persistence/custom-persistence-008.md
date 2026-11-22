# Mã hóa dữ liệu nhạy cảm và kiểm thử tính tương thích giữa các instance

> **Chương: Lưu trữ tùy chỉnh.** Bài thuộc module **SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Trọng tâm là bảo vệ dữ liệu OAuth/OIDC trong persistence layer, quản lý khóa mã hóa và duy trì khả năng đọc dữ liệu giữa nhiều instance khi rolling deployment.

## 1. Vì sao custom persistence cần mã hóa dữ liệu?

Authorization Server lưu nhiều dữ liệu có giá trị cao: client registration, client secret đã encode, authorization code, access token, refresh token, ID Token, principal attributes, consent và metadata của grant. Một số giá trị là bearer credential; ai lấy được token còn hiệu lực có thể sử dụng token đó. Một số trường chứa thông tin định danh cá nhân, scope, tenant hoặc dữ liệu xác thực của người dùng.

Mã hóa dữ liệu ở database giúp giảm tác động khi backup, snapshot, disk hoặc bản dump bị truy cập trái phép. Tuy nhiên, cần phân biệt các lớp bảo vệ:

- **Mã hóa đường truyền:** TLS bảo vệ dữ liệu giữa application, database, cache, KMS và service khác.
- **Mã hóa storage:** database TDE, disk encryption và backup encryption bảo vệ file dữ liệu ở tầng hạ tầng.
- **Mã hóa trường ở application layer:** application mã hóa trường trước khi ghi; database chỉ nhìn thấy ciphertext.
- **Quản lý secret/configuration:** key, password và API credential được giữ trong secret manager/KMS, không nằm trong source code hoặc container image.

Các lớp này bổ trợ nhau. TDE không ngăn người có quyền query database đọc dữ liệu qua SQL; field-level encryption có thể giảm rủi ro đó, nhưng application đã được cấp quyền decrypt vẫn có thể đọc plaintext.

### 1.1. Threat model cần xác định trước

| Tình huống | Biện pháp có ích | Giới hạn |
|---|---|---|
| Database dump/backup bị lộ | TDE, backup encryption, field encryption | Nếu key nằm cùng dump thì lợi ích giảm mạnh |
| Người có quyền SQL đọc bảng | Field-level encryption và quyền DB tối thiểu | Application vẫn phải decrypt để xử lý protocol |
| Network traffic bị nghe lén | TLS giữa các thành phần | TLS không bảo vệ bản ghi sau khi lưu |
| Một pod bị xâm nhập | Least privilege, KMS policy, hạn chế plaintext và log | Pod có quyền decrypt vẫn có thể bị lạm dụng |
| Một instance dùng key/serializer khác | Key versioning, schema versioning, compatibility tests | Encryption không sửa được contract không tương thích |
| Log/APM ghi token | Redaction, log policy và secret scanning | Mã hóa DB không bảo vệ credential đã bị log |

Không nên mã hóa mọi cột theo phản xạ. Hãy phân loại dữ liệu, xác định ai cần đọc, query nào cần tìm kiếm và thời gian giữ dữ liệu. Dữ liệu không cần lưu thì không nên lưu.

## 2. Phân loại dữ liệu trong Spring Authorization Server

Spring Authorization Server tách các model theo mục đích. Thiết kế persistence phải nhận diện dữ liệu nhạy cảm trong từng model.

| Model/field | Dữ liệu | Cách bảo vệ thường phù hợp |
|---|---|---|
| RegisteredClient.clientId | Định danh OAuth client | Unique index; phân loại theo chính sách tổ chức |
| RegisteredClient.clientSecret | Credential dùng client authentication | One-way PasswordEncoder, không lưu plaintext |
| redirectUris, scopes | Cấu hình giao thức và quyền | Kiểm soát write access, audit; encrypt nếu có metadata nhạy cảm |
| clientSettings, tokenSettings | Cấu hình client/token | Serialization có version; encrypt nếu cần |
| OAuth2Authorization token values | Authorization code, access/refresh token, ID Token tùy grant | Field/document encryption và lookup index riêng |
| OAuth2Authorization.attributes | Principal, authorization request, claims, metadata | Minimize, lọc field, encrypt PII/credential-bearing attributes |
| OAuth2AuthorizationConsent.authorities | Scope/permission user đã chấp thuận | Access control, audit; encryption theo phân loại dữ liệu |
| Signing private key/JWK private parameters | Khóa ký token | HSM/KMS/secure keystore, không đưa vào authorization database |
| Audit event | Actor, client, action, thời gian | Chỉ lưu metadata cần thiết; không ghi token/secret |

OAuth2Authorization có thể giữ access token, refresh token, authorization code, ID Token và attributes của flow. Cần xem xét cả token metadata/claims và các object được serialize bên trong attributes, không chỉ cột token value nhìn thấy ở schema.

### 2.1. Hash, encrypt hay loại bỏ?

| Dữ liệu | Cách xử lý | Lý do |
|---|---|---|
| Client secret | PasswordEncoder (one-way) | Server chỉ cần xác minh secret caller gửi |
| User password | Password hashing chuyên dụng | Không có use case hợp lệ để khôi phục plaintext |
| Access/refresh token lưu trong authorization | Encrypt at rest; lookup index riêng nếu cần | Bảo vệ credential nhưng vẫn hỗ trợ tra cứu |
| Authorization code | Encrypt at rest, retention ngắn | Credential ngắn hạn nhưng có giá trị cao |
| PII/claims trong attributes | Minimize và encrypt theo field/document | Hạn chế lộ dữ liệu cá nhân |
| Client ID | Index dạng rõ nếu policy cho phép | Protocol lookup thường cần tìm theo client ID |
| Token lookup key | HMAC-SHA-256 với key riêng | Equality lookup mà không lưu token plaintext |
| Signing private key | KMS/HSM hoặc keystore riêng | Không cùng trust boundary với authorization records |
| Dữ liệu hết hạn/không cần giữ | Retention/cleanup | Giảm lượng dữ liệu nhạy cảm tồn tại |

Không nhầm PasswordEncoder với encryption. Hash không thể decrypt; encryption có thể decrypt khi có key. Nếu hệ thống cần giữ credential của upstream service để gửi lại, đó là loại dữ liệu khác: dùng secret manager hoặc envelope encryption với key purpose riêng.

## 3. Kiến trúc envelope encryption

Một thiết kế phổ biến là **envelope encryption**: application dùng Data Encryption Key (DEK) để mã hóa payload; Key Encryption Key (KEK) trong KMS/HSM bảo vệ DEK.

~~~mermaid
flowchart TD
    A["Authorization data / sensitive fields"] --> B["Serialize canonical payload"]
    B --> C["DEK: AES-GCM encrypt + AAD"]
    C --> D["Ciphertext + nonce + tag"]
    E["KMS / HSM KEK"] --> F["Wrap DEK"]
    F --> G["Wrapped DEK + key version"]
    D --> H["Encrypted persistence record"]
    G --> H
    H --> I["Database / Redis / backup"]
    I --> J["Authorized AS instance"]
    J --> K["KMS unwrap DEK"]
    K --> L["AES-GCM authenticate + decrypt"]
    L --> M["Deserialize versioned payload"]
~~~

- **DEK:** khóa dữ liệu dùng để mã hóa plaintext; có thể tạo theo record, tenant hoặc nhóm dữ liệu tùy hiệu năng và blast radius.
- **KEK:** khóa quản lý trong KMS/HSM dùng để wrap/unwrap DEK.
- **Ciphertext:** dữ liệu đã mã hóa và authentication tag.
- **Nonce/IV:** giá trị duy nhất theo key cho mỗi lần AES-GCM encryption.
- **AAD (Additional Authenticated Data):** metadata không cần mã hóa nhưng được xác thực cùng ciphertext, ví dụ tenant ID, record ID, field purpose và format version.
- **Key ID/version:** chỉ ra khóa/phiên bản cần dùng khi decrypt; không chứa key material.

Database có thể lưu wrapped DEK cạnh ciphertext. KEK thật phải nằm trong KMS/HSM hoặc trust boundary riêng. Mỗi instance chỉ giải mã được khi được cấp quyền KMS phù hợp.

### 3.1. Vì sao cần authenticated encryption?

Dữ liệu mã hóa cần cả bí mật và tính toàn vẹn. Nếu chỉ mã hóa mà không xác thực, attacker có thể sửa ciphertext và tạo lỗi khó phát hiện hoặc thay đổi plaintext sau decrypt.

Ưu tiên authenticated encryption như AES-GCM. GCM tạo authentication tag; decrypt phải thất bại nếu ciphertext, tag hoặc AAD bị sửa. Không tự thiết kế cipher, mode, padding hay protocol mã hóa riêng.

### 3.2. Nonce phải duy nhất với cùng một key

Với AES-GCM, **không được tái sử dụng cùng nonce/IV với cùng key trên các plaintext khác nhau**. Đây là yêu cầu an toàn cốt lõi. Khi nhiều pod dùng chung một DEK, nonce uniqueness là yêu cầu trên toàn cluster, không phải riêng từng JVM.

Nonce 96-bit được sinh bằng SecureRandom là một lựa chọn phổ biến nếu có quản lý usage volume và collision risk phù hợp. Với hệ thống throughput cao, cần thiết kế nonce allocation/usage limits có kiểm soát hoặc dùng KMS/library chịu trách nhiệm. Theo dõi số lần encrypt theo key và rotate trước giới hạn được xác định trong threat model/chuẩn áp dụng. Không tạo nonce bằng currentTimeMillis hoặc counter chỉ nằm trong RAM của từng pod.

## 4. Thiết kế record mã hóa có version

Không lưu ciphertext như một chuỗi không có metadata. Record cần đủ thông tin để mọi instance xác định cách giải mã:

| Field | Ví dụ | Mục đích |
|---|---|---|
| format_version | 1 | Version envelope/encoding |
| schema_version | 3 | Version payload schema |
| algorithm | AES-256-GCM | Thuật toán và mode |
| key_id | as-data-key-v4 | ID/version của KEK hoặc key profile |
| wrapped_dek | Base64 bytes | DEK đã được KEK wrap |
| nonce | Base64 12 bytes | GCM IV |
| ciphertext | Base64 bytes | Ciphertext kèm tag theo format |
| aad_version | 1 | Quy tắc tạo AAD |
| created_at | UTC timestamp | Audit/diagnostic |

Không lưu key plaintext vào record. algorithm, format_version và key_id phải được kiểm tra bằng allowlist; không để dữ liệu DB chọn một provider/class tùy ý.

### 4.1. AAD ràng buộc ciphertext với ngữ cảnh

AAD có thể bao gồm tenant/issuer đã xác minh, registration ID hoặc authorization ID, field name/purpose và envelope format version. Nếu attacker copy ciphertext của tenant A sang record tenant B, AAD khác nhau sẽ làm GCM authentication thất bại.

AAD phải được tạo theo canonical encoding giống nhau ở tất cả instance; tránh nối chuỗi mơ hồ có thể gây va chạm biểu diễn. Tenant ID phải đến từ issuer/tenant context đã xác minh, không dùng tenant từ request body. Khi thay tenant hoặc đổi AAD scheme, cần re-encrypt hoặc migration rõ ràng. Không đưa dữ liệu bí mật vào AAD vì AAD không được mã hóa.

## 5. Ví dụ AES-GCM bằng Java Cryptography Architecture

Đoạn code minh họa primitive AES-GCM với DEK 256-bit được cấp từ key management layer. Việc sinh, wrap, phân phối, cache và rotation DEK/KEK thuộc KMS/key service riêng của ứng dụng.

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class AesGcmPayloadCipher {

    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecureRandom secureRandom = new SecureRandom();

    EncryptedPayload encrypt(
            byte[] plaintext,
            SecretKey dek,
            byte[] associatedData,
            String keyId) throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_BYTES];
        secureRandom.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(associatedData);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new EncryptedPayload(1, keyId, nonce, ciphertextAndTag);
    }

    byte[] decrypt(
            EncryptedPayload payload,
            SecretKey dek,
            byte[] associatedData) throws GeneralSecurityException {

        if (payload.formatVersion() != 1) {
            throw new IllegalArgumentException("Unsupported envelope version");
        }

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, payload.nonce()));
        cipher.updateAAD(associatedData);

        // AEADBadTagException là integrity/authentication failure.
        return cipher.doFinal(payload.ciphertextAndTag());
    }

    record EncryptedPayload(
            int formatVersion,
            String keyId,
            byte[] nonce,
            byte[] ciphertextAndTag) {
    }
}
~~~

Đây là ví dụ primitive, chưa phải giải pháp persistence hoàn chỉnh. Ứng dụng cần:

1. Lấy DEK từ KMS/key service; không hardcode key trong class hoặc config.
2. Wrap DEK bằng KEK và lưu wrapped_dek cùng key_id.
3. Lưu nonce, ciphertext/tag và version fields.
4. Tạo AAD canonical từ tenant, record ID, purpose và version.
5. Khi decrypt, lấy đúng key theo key ID, tái tạo đúng AAD và xác minh tag.
6. Nếu decrypt thất bại, từ chối bản ghi và phát alert; không trả object rỗng hoặc bỏ qua lỗi tag.

Cipher là object mutable theo từng operation; không chia sẻ một instance Cipher giữa các thread. Trong production, dùng crypto/key-management library được duy trì và kiểm chứng, giới hạn quyền decrypt theo workload và có quy trình xử lý key compromise.

## 6. Tạo AAD ổn định giữa các instance

AAD là một phần của contract lưu trữ. Nếu pod A dùng tenant ID dạng uppercase còn pod B lowercase, hoặc một pod ghép field theo thứ tự khác, decrypt sẽ thất bại dù key và ciphertext đúng.

Ví dụ helper dùng length-prefix để tránh nhập nhằng khi ghép các trường:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

final class AadFactory {

    private AadFactory() {
    }

    static byte[] create(
            String tenantId,
            String recordId,
            String purpose,
            int formatVersion) {

        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            writeUtf8(out, tenantId);
            writeUtf8(out, recordId);
            writeUtf8(out, purpose);
            out.writeInt(formatVersion);
            out.flush();
            return bytes.toByteArray();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot build AAD", ex);
        }
    }

    private static void writeUtf8(DataOutputStream out, String value)
            throws IOException {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }
}
~~~

Tất cả instance phải dùng cùng canonicalization và encoding. Không thay đổi thuật toán canonicalization âm thầm trong rolling deployment.

## 7. Lookup token mà không lưu token plaintext

Custom OAuth2AuthorizationService.findByToken(token, tokenType) cần tra cứu theo token value. Nếu lưu raw token trong cột index, database dump có thể làm lộ bearer credential.

Một thiết kế là dùng **keyed HMAC index** tách biệt với encryption key:

~~~text
lookup_digest = HMAC-SHA-256(
    token_lookup_key,
    token_type || 0x00 || raw_token
)
~~~

Persistence record lưu token_lookup_key_id, token_lookup_digest và encrypted authorization payload. Khi nhận findByToken, adapter tính lại HMAC bằng key tương ứng rồi lookup theo digest. HMAC key phải độc lập với DEK/KEK và được quản lý/rotate riêng. Dùng encoding canonical cho token type và token bytes; không log raw token.

HMAC digest chỉ là lookup index, không thể khôi phục token và không thay thế ciphertext. Nếu cần trả lại OAuth2Authorization đầy đủ, phải decrypt payload sau khi tìm được record. Với JWT tự chứa, nếu chỉ cần tra cứu revocation theo jti đã xác minh, có thể thiết kế index theo jti; lựa chọn phụ thuộc protocol flow và query contract.

### 7.1. Rotation HMAC lookup key

Khi đổi HMAC key, digest cũ không thể tính lại từ digest. Các cách migration:

- Duy trì nhiều index version trong thời gian chuyển đổi; lookup thử key version hiện hành và các version còn đọc được.
- Backfill digest mới bằng cách decrypt record để lấy token value, tạo HMAC mới rồi ghi thêm index.
- Chuyển toàn bộ writer sang key mới sau khi mọi reader đã hiểu cả hai version.
- Xóa index/key cũ sau khi xác nhận migration, backup và retention policy.

Không đổi HMAC key rồi lập tức xóa key cũ khi database còn record chỉ có digest cũ.

## 8. Client secret và PasswordEncoder

RegisteredClient.clientSecret là giá trị đã được encode bằng PasswordEncoder. Nó cần được xác minh khi client authentication; server không cần giải mã secret gốc.

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;

String encodedSecret = passwordEncoder.encode(rawClientSecret);

RegisteredClient registeredClient = RegisteredClient
        .withId("registration-orders-service")
        .clientId("orders-service")
        .clientSecret(encodedSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();
~~~

Không lưu raw client secret, không dùng NoOpPasswordEncoder ở production và không mã hóa reversible client secret chỉ để có thể xem lại. Nếu client mất secret, quy trình đúng thường là rotate và cấp secret mới.

Nếu hệ thống cần giữ credential của upstream service để gửi lại, dùng secret manager hoặc envelope encryption với key purpose riêng, audit và access policy riêng.

## 9. Serialization của Spring Authorization Server phải nhất quán

Mã hóa bytes không đủ nếu các instance deserialize cùng payload thành object khác nhau. Spring Authorization Server dùng các type như RegisteredClient, OAuth2Authorization, OAuth2AuthorizationConsent, token metadata, Spring Security Authentication và authorization request attributes.

Tài liệu JPA của Spring Authorization Server minh họa việc đăng ký các Jackson modules:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.Module;
import java.util.List;
import org.springframework.security.jackson2.SecurityJackson2Modules;
import org.springframework.security.oauth2.server.authorization.jackson2.OAuth2AuthorizationServerJackson2Module;

ObjectMapper objectMapper = new ObjectMapper();

ClassLoader classLoader = getClass().getClassLoader();
List<Module> securityModules =
        SecurityJackson2Modules.getModules(classLoader);

objectMapper.registerModules(securityModules);
objectMapper.registerModule(
        new OAuth2AuthorizationServerJackson2Module());
~~~

Đây là module registration minh họa. Ứng dụng phải cấu hình mapper phù hợp với model thực tế và dùng cùng contract khi ghi/đọc. Không giả định mọi POJO hoặc Authentication tùy chỉnh sẽ tự deserialize chỉ nhờ đăng ký module.

### 9.1. Tránh Java native serialization và unrestricted default typing

Không dùng Java native serialization của object tùy ý từ database/cache nếu có thể tránh. Không bật unrestricted Jackson default typing trên dữ liệu persistence không tin cậy: type metadata có thể mở rộng bề mặt deserialization.

Nên:

- Dùng DTO/payload model có schema rõ.
- Chỉ cho phép subtype cần thiết qua allowlist.
- Đăng ký Jackson modules chính thức của Spring Security/SAS.
- Kiểm soát custom Authentication/attribute type và serializer riêng.
- Giới hạn kích thước payload, nesting depth và input.
- Tách version serialization schema khỏi version encryption envelope.

### 9.2. Schema version và migration

Record nên có schema_version. Khi thêm field, ưu tiên thay đổi additive với default có nghĩa rõ ràng. Khi đổi tên/xóa field hoặc đổi kiểu dữ liệu, cần migration hoặc reader hỗ trợ version cũ.

Không deserialize dữ liệu cũ bằng cách âm thầm thay lỗi thành default object; điều đó có thể biến authorization thành cấu hình khác mà không ai nhận ra. Nếu payload version không hỗ trợ, fail closed, log correlation ID và đưa record vào quy trình repair/migration.

## 10. Tính tương thích giữa các instance trong cluster

Trong production, request có thể được xử lý bởi bất kỳ pod nào. Một pod ghi authorization; pod khác có thể đọc, introspect, refresh hoặc revoke record đó.

| Thành phần | Yêu cầu giữa các instance |
|---|---|
| Crypto envelope | Cùng format version, algorithm allowlist và encoding |
| Key access | Có quyền đọc key version cần thiết trong KMS/HSM |
| AAD | Cùng canonicalization, tenant/issuer resolution và field purpose |
| Serializer | Tương thích schema và Jackson modules |
| Custom type | Cùng allowlist và serializer/deserializer |
| Database schema | Mọi version app đang chạy đọc/ghi được schema trong rollout |
| Token lookup index | Cùng HMAC key versions và canonical token type |
| Time handling | UTC, clock synchronization và expiry policy nhất quán |
| Cache | Invalidation/TTL không giữ dữ liệu stale vượt policy |
| Issuer/tenant | Cùng mapping public issuer và tenant isolation |

### 10.1. Lỗi lệch key giữa pod

~~~mermaid
sequenceDiagram
    participant A as AS pod A
    participant DB as Shared database
    participant B as AS pod B
    A->>A: Encrypt record với key version v4
    A->>DB: Lưu key_id=v4 + ciphertext
    B->>DB: Đọc record
    B->>B: Chỉ có key v3
    B-->>B: Không decrypt được
    Note over A,B: Request fail dù database và ciphertext không hỏng
~~~

Lỗi này thường xuất hiện khi rollout một phần, một pod chưa nhận KMS permission hoặc key cache chưa được refresh. Không xử lý bằng cách bỏ qua lỗi decrypt hoặc thử key ngẫu nhiên. Cần bảo đảm key distribution/permission trước khi writer bắt đầu phát record bằng key mới.

### 10.2. Rolling deployment theo quy tắc reader-first

1. **Deploy reader tương thích trước:** phiên bản mới đọc được format cũ và mới, nhưng vẫn ghi format cũ.
2. **Xác nhận toàn cluster:** mọi pod đang chạy đều có key permission và code đọc format mới.
3. **Chuyển writer:** bật feature flag/config để ghi format/schema mới.
4. **Backfill:** migrate record cũ theo batch, có checkpoint và retry an toàn.
5. **Quan sát:** theo dõi decrypt failures, deserialization errors, unknown key ID, stale cache và latency.
6. **Retire reader cũ:** chỉ sau khi không còn record format cũ và backup/restore requirements được xử lý.

Nếu phiên bản cũ không thể đọc format mới, tuyệt đối không bật writer mới khi vẫn còn pod cũ nhận traffic. Dùng expand/contract migration để schema database cũng tương thích trong toàn bộ giai đoạn.

## 11. Key rotation và khả năng đọc dữ liệu cũ

Cần phân biệt:

- **KEK rotation:** thay key wrap DEK. Có thể re-wrap DEK dưới KEK mới mà không mã hóa lại payload nếu KMS hỗ trợ envelope model.
- **DEK rotation:** thay khóa mã hóa dữ liệu. Muốn dùng DEK mới cho ciphertext cũ thì phải decrypt và re-encrypt dữ liệu.

Record nên lưu key_id/version để biết cần gọi key nào khi đọc. Mọi instance cần quyền decrypt key version còn được dùng.

### 11.1. Quy trình rotation bình thường

1. Tạo key version mới trong KMS/HSM.
2. Cấp quyền decrypt key cũ và encrypt/wrap bằng key mới cho mọi instance cần thiết.
3. Deploy code/config có thể đọc cả version cũ và mới.
4. Chuyển writer sang key mới.
5. Re-wrap DEK hoặc re-encrypt payload theo chiến lược đã chọn.
6. Kiểm tra số lượng record cũ còn lại và kết quả decrypt.
7. Giữ key cũ đủ lâu để đọc backup/restore và record chưa migrate.
8. Chỉ retire/destroy key cũ sau khi retention, backup và disaster recovery cho phép.

### 11.2. Rotation khi key compromise

Nếu nghi ngờ key bị lộ, xác định phạm vi dữ liệu đã được bảo vệ bởi key đó. Có thể phải dừng encrypt mới bằng key cũ, cấp key mới, re-encrypt dữ liệu và xử lý access tới backup. Rotation định kỳ và incident response là hai quy trình khác nhau; compromise có thể cần hành động khẩn cấp.

Không xóa key cũ trước khi đánh giá backup còn cần decrypt. Ngược lại, giữ key bị compromise vô thời hạn cũng không an toàn. Cần quyết định rõ thời gian giữ, quyền truy cập và phương án cryptographic erasure.

### 11.3. Mọi pod phải dùng cùng key registry

Không để từng pod tự sinh AES key khi khởi động. Nếu pod A sinh key A và pod B sinh key B, dữ liệu do A ghi không thể đọc bởi B; restart còn có thể làm mất key duy nhất dùng để decrypt dữ liệu cũ.

Key phải được provision từ KMS/HSM/secure key service với ID/version rõ ràng. Các pod dùng chung key registry và policy; không nhất thiết phải nhận raw key material nếu KMS hỗ trợ thao tác mã hóa/giải mã từ xa.

## 12. Cấu hình secret và key ngoài application artifact

Không commit KEK, DEK, HMAC key, database password hoặc client secret vào source code, application YAML, container image hay Git history. Spring Boot hỗ trợ externalized configuration và configuration tree để nạp secret từ file mount; hệ thống lớn có thể tích hợp Vault/KMS qua cơ chế phù hợp.

Ví dụ cấu hình đọc secret từ mounted configuration tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Có thể bind cấu hình không nhạy cảm như key alias/version qua ConfigurationProperties, còn quyền truy cập key thực tế do KMS IAM policy quyết định. Configuration tree là phương tiện phân phối config/secret, không thay thế KMS; cần file permission và runtime isolation.

Các nguyên tắc:

- Tách key material khỏi database và application image.
- Dùng service identity riêng cho mỗi workload.
- Chỉ cấp encrypt/decrypt đúng key/tenant cần thiết.
- Audit các thao tác KMS, đặc biệt decrypt/unwrap.
- Có quy trình backup/restore key và kiểm thử khôi phục.
- Không in key, DEK, plaintext hay serialized token payload vào log.
- Dùng secret rotation có kiểm soát, không đổi key thủ công độc lập trên từng pod.

## 13. Kiểm thử tương thích và bảo mật giữa nhiều instance

Unit test một encrypt/decrypt trong cùng JVM chưa đủ. Cần chứng minh **instance khác**, với key registry và serializer độc lập, vẫn đọc được dữ liệu đã ghi.

### 13.1. Crypto tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Round trip | Encrypt ở pod A, decrypt ở pod B | Plaintext đúng |
| Ciphertext tamper | Sửa một byte ciphertext/tag | Decrypt thất bại |
| Nonce tamper | Sửa nonce | Decrypt thất bại |
| Wrong key | Dùng DEK khác | Decrypt thất bại |
| Wrong AAD | Thay tenant/record/field purpose | Decrypt thất bại |
| Unknown key ID | Pod không có key version | Fail closed và alert |
| Unsupported format | Record version không hỗ trợ | Không trả object mặc định |
| Nonce uniqueness | Sinh nonce trên nhiều pod cùng key | Không phát hiện reuse; theo dõi usage |
| Key rotation | Encrypt bằng v4, đọc bằng reader có v3/v4, re-encrypt v4 | Dữ liệu cũ đọc được, record mới dùng v4 |
| KMS unavailable | KMS timeout/denied | Không ghi plaintext fallback |

### 13.2. Serialization compatibility tests

| Test | Writer | Reader | Kỳ vọng |
|---|---|---|---|
| Baseline | App v1 | App v1 | Round trip |
| Backward read | App v1 | App v2 | v2 đọc được payload v1 |
| Forward compatibility | App v2 (field additive) | App v1 | Chỉ cho phép nếu contract bảo đảm unknown fields an toàn; nếu không, chưa bật v2 writer |
| Rolling deployment | Pod v1 và v2 cùng chạy | Shared DB | Không có record mà pod đang phục vụ không đọc được |
| Custom type | Serializer có custom Authentication | Instance khác | Type nằm trong allowlist và deserialize đúng |
| Corrupt JSON | Payload thiếu field/invalid type | Mọi pod | Báo lỗi, không tạo authorization rỗng |
| Schema migration | Old schema → new schema | New reader | Giá trị và semantics được bảo toàn |
| Module mismatch | Khác Jackson/SAS module version | Reader | Phát hiện incompatibility trước production |

### 13.3. Integration test với database/cache thật

Chạy ít nhất hai application context hoặc hai process độc lập cùng kết nối shared persistence và cùng KMS test key:

1. Pod A tạo RegisteredClient và lưu authorization chứa access/refresh token giả.
2. Pod B đọc bằng RegisteredClientRepository/OAuth2AuthorizationService.
3. Pod B kiểm tra token lookup, metadata, principal attributes và token active state.
4. Pod B refresh hoặc revoke theo flow test; pod A đọc lại trạng thái đã cập nhật.
5. Khởi động lại pod A với cache rỗng; dữ liệu vẫn đọc được.
6. Thu hồi KMS permission ở pod test; request phải thất bại rõ ràng, không fallback plaintext.
7. Chạy migration/rotation trong khi cả hai version app đang phục vụ request.
8. Restore một backup vào môi trường cô lập và xác minh key versions cần thiết vẫn decrypt được.

### 13.4. Test multi-tenant và isolation

- Ciphertext của tenant A không thể decrypt bằng AAD tenant B.
- Lookup theo tenant/issuer không trả record tenant khác.
- KMS policy giới hạn key/tenant theo workload.
- Key ID từ DB không được chọn tùy ý một KMS resource ngoài allowlist.
- Tenant context không có hoặc không xác minh được phải fail closed.
- Cache key phải bao gồm tenant/issuer nếu dữ liệu được partition theo tenant.

## 14. Troubleshooting và runbook thay đổi schema/key

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pod A ghi được, pod B không decrypt được | Key version/permission khác nhau | Đồng bộ KMS grants và key registry trước khi chuyển writer |
| AEADBadTagException | Ciphertext, nonce, tag hoặc AAD bị thay đổi; sai key | Kiểm tra record version, AAD canonicalization và key ID |
| Chỉ một tenant lỗi decrypt | Tenant context/normalization không đồng nhất | Chuẩn hóa tenant ID và kiểm tra AAD |
| Sau deploy, authorization không deserialize | Jackson module/custom type/version khác | Đồng bộ serializer config, schema migration và allowlist |
| Record cũ không đọc được sau rotation | Đã xóa key cũ quá sớm | Khôi phục key access hoặc restore từ backup key escrow hợp lệ |
| Pod mới ghi record, pod cũ lỗi | Writer-first rollout | Triển khai reader tương thích trước, sau đó mới bật writer |
| Token lookup chậm hoặc miss | HMAC key/version/index không khớp | Kiểm tra canonicalization và index migration |
| Client secret lộ trong DB | Lưu raw secret thay vì PasswordEncoder | Rotate secret và sửa write path |
| DB dump vẫn có token plaintext | Chỉ encrypt payload nhưng index/cột khác còn raw | Mã hóa lookup payload và dùng HMAC index |
| KMS latency tăng | Gọi KMS cho từng field/record không có cache policy | Dùng envelope DEK, pooling/retry/cache có kiểm soát |
| Database restore nhưng không decrypt được | Backup key/version thiếu | Kiểm thử backup key và quy trình disaster recovery |
| Ciphertext bị thay nhưng app trả object rỗng | Catch lỗi quá rộng và fallback | Fail closed, phân loại lỗi và phát alert |

### 14.1. Trước khi deploy

- Xác định record types, schema version, envelope version và key versions đang được dùng.
- Xác minh mọi instance hiện tại đọc được format sắp triển khai.
- Kiểm tra KMS permission trên từng service identity.
- Tạo backup và xác minh khả năng restore/decrypt trong môi trường cô lập.
- Chuẩn bị dashboard cho decrypt failures, unknown key IDs, deserialize errors, lookup misses và KMS latency.
- Viết migration có checkpoint, idempotency và rollback/forward-recovery plan.

### 14.2. Trong rollout

1. Deploy reader mới, chưa bật writer format mới.
2. Chờ toàn cluster healthy và xác minh cross-instance read.
3. Bật writer mới theo canary/feature flag.
4. Quan sát error rate và đọc lại dữ liệu từ pod khác.
5. Backfill theo batch có giới hạn tốc độ.
6. Giữ reader cũ/key cũ đến khi migration và backup policy cho phép retire.

### 14.3. Sau rollout

- Đếm record theo schema/key version.
- Xác nhận không còn record cũ cần reader/key cũ.
- Kiểm tra backup/restore với key versions được giữ lại.
- Thu hồi quyền key không còn dùng và audit thay đổi.
- Cập nhật runbook, inventory và test fixtures.
- Không xóa key cũ chỉ vì traffic production hiện tại không còn đọc nó; backup có thể vẫn cần key.

## 15. Checklist production và câu hỏi tự đánh giá

- [ ] Đã phân loại dữ liệu RegisteredClient, OAuth2Authorization, Consent, token, attributes và signing keys.
- [ ] Client secret/user password dùng one-way PasswordEncoder/password hashing, không lưu plaintext.
- [ ] Token/PII cần bảo vệ được mã hóa bằng authenticated encryption.
- [ ] AES-GCM nonce duy nhất theo key trên toàn cluster; có usage/rotation policy.
- [ ] AAD canonical, bao gồm tenant/record/purpose và version cần thiết.
- [ ] Envelope có format version, schema version và key ID.
- [ ] DEK và KEK tách biệt; KEK nằm trong KMS/HSM/secure key service.
- [ ] HMAC lookup key độc lập với encryption key; raw token không xuất hiện trong index/log.
- [ ] Key versions cũ vẫn đọc được trong giai đoạn migration/backup retention.
- [ ] Tất cả pod có key permission và serializer modules/allowlist tương thích.
- [ ] Jackson dùng Security/SAS modules cần thiết; không bật unrestricted default typing.
- [ ] Schema migration tuân thủ reader-first và expand/contract.
- [ ] Cache invalidation, issuer/tenant context và UTC/clock policy nhất quán.
- [ ] KMS/database outage không dẫn tới plaintext fallback hoặc object mặc định.
- [ ] Có crypto, tamper, wrong-key, wrong-AAD, key rotation, old/new serializer và multi-pod tests.
- [ ] Backup/restore đã kiểm tra khả năng lấy lại key cần thiết.
- [ ] Log, trace, metrics không chứa token, secret, plaintext payload hoặc key material.
- [ ] Có runbook xử lý key compromise, migration lỗi và rollback/forward recovery.

**Câu hỏi tự đánh giá**

1. Vì sao RegisteredClient.clientSecret nên được lưu bằng PasswordEncoder thay vì encryption reversible?
2. Khác nhau giữa TDE, field-level encryption và TLS là gì?
3. DEK và KEK có vai trò khác nhau như thế nào trong envelope encryption?
4. Vì sao AES-GCM cần nonce duy nhất với cùng một key?
5. Khi nhiều pod dùng chung DEK, nonce uniqueness phải được đảm bảo ở phạm vi nào?
6. AAD có thể ngăn ciphertext tenant A bị copy sang record tenant B như thế nào?
7. Vì sao không nên lưu raw access/refresh token trong cột lookup index?
8. HMAC lookup digest khác ciphertext ở điểm nào?
9. Khi rotate KEK, re-wrap DEK khác gì rotate DEK?
10. Vì sao mọi pod phải đọc được key version cũ trước khi pod mới ghi bằng key version mới?
11. SecurityJackson2Modules và OAuth2AuthorizationServerJackson2Module giải quyết vấn đề gì?
12. Vì sao unrestricted Jackson default typing có thể nguy hiểm với persistence data?
13. Khi schema v2 được ghi trong lúc pod v1 còn chạy, cần điều kiện compatibility nào?
14. Nếu decrypt thất bại do AEAD tag mismatch, vì sao không được trả authorization mặc định?
15. Cần test nào để chứng minh pod A ghi và pod B đọc được cùng authorization sau restart?
16. Vì sao backup encrypted data mà thiếu key backup có thể không khôi phục được dịch vụ?

## Tài liệu tham khảo

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, OAuth2Authorization, OAuth2AuthorizationConsent và token model.
- [Spring Authorization Server — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): serialization của RegisteredClient/OAuth2Authorization và Jackson modules.
- [Spring Authorization Server — How-to: Implement core services with Redis](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-redis.html): custom converters và Redis persistence.
- [Spring Security — Jackson Modules](https://docs.spring.io/spring-security/reference/servlet/integrations/jackson.html): SecurityJackson2Modules và hỗ trợ security objects.
- [Spring Security Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html): symmetric encryptors, AES-GCM và password encoding; API cần đối chiếu theo Spring Security version.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): external configuration, config trees và secret injection; Spring Boot không tự cung cấp property encryption.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): AEAD, key separation, DEK/KEK, key storage và rotation.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): quản lý key, rotation, backup và cryptoperiod.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): authenticated encryption và yêu cầu uniqueness của IV.
