# Không hard-code key – Không nhúng khóa mật mã trực tiếp vào mã nguồn

**Không hard-code key** nghĩa là **không đặt vật liệu khóa bí mật (secret key, private key, seed hoặc secret có thể tái tạo khóa) thành hằng số, chuỗi ký tự hoặc dữ liệu cố định bên trong source code, script, cấu hình được đóng gói hay binary phân phối**. Khóa phải được **sinh từ nguồn ngẫu nhiên mật mã phù hợp, cấp phát và sử dụng qua cơ chế quản lý bí mật/khóa đáng tin cậy**, với quyền, phiên bản và vòng đời được kiểm soát.

Trong chương **Key generation** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, quy tắc này liên quan trực tiếp đến vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Một khóa AES-256 được sinh đúng thuật toán vẫn có thể trở thành điểm yếu nghiêm trọng nếu developer sao chép 32 byte khóa vào Git, Docker image hoặc ứng dụng di động. Ngược lại, tránh hằng số secret trong code **chưa đủ** nếu quyền KMS quá rộng, dữ liệu bị ghi log hoặc không có quy trình rotate.

> **Nguyên tắc:** **Source code và artifact triển khai không phải kho khóa bí mật.** Code nên biết *cách yêu cầu thao tác mật mã*, *key reference và policy được phép*; không nên chứa *giá trị bí mật dùng để thực hiện phép toán*.

## 1. Hard-code key là gì và tại sao nguy hiểm?

Một giá trị được gọi là **hard-coded** khi nó được nhúng vào chương trình như dữ liệu tĩnh thay vì được cấp qua cơ chế quản lý phù hợp ở thời điểm chạy. Với mật mã, những ví dụ thường gặp là:

~~~java
// SAI: khóa AES cố định trong source.
private static final byte[] AES_KEY =
        "0123456789abcdef0123456789abcdef".getBytes();

// SAI: private key hoặc secret HMAC được đóng trong cấu hình Java.
private static final String HMAC_SECRET = "same-secret-for-all-nodes";

// SAI: khóa vẫn là hằng số, chỉ được che bằng Base64.
private static final String ENCODED_KEY = "MDEyMzQ1Njc4OWFiY2RlZg==";

// SAI: nguồn giả ngẫu nhiên có seed biết trước để tạo secret.
java.util.Random random = new java.util.Random(123456L);
~~~

*Các chuỗi trên chỉ là giá trị giả minh họa, không phải khóa thật.*

**Base64, hex, XOR với hằng số, tách chuỗi rồi ghép lại, hoặc mã hóa/obfuscation trong binary không biến một khóa nhúng sẵn thành secret được bảo vệ.** Người có thể đọc source, artifact hoặc phân tích binary thường có thể khôi phục giá trị hoặc tìm đường chương trình sử dụng nó.

### 1.1. Những rủi ro cụ thể

| Rủi ro | Cách xảy ra | Hậu quả |
| --- | --- | --- |
| **Rò qua repository** | Key nằm trong Git commit, pull request, fork, mirror hoặc backup. | Người ngoài có thể giải mã dữ liệu/giả mạo chữ ký nếu khóa còn hiệu lực. |
| **Rò qua artifact** | Secret được nhúng vào JAR, Docker layer, build cache, image mobile. | Mọi người có artifact có thể phân tích và lấy khóa. |
| **Phạm vi ảnh hưởng lớn** | Cùng một khóa được dùng ở mọi tenant, instance hoặc môi trường. | Một lần lộ có thể ảnh hưởng toàn bộ dữ liệu/khách hàng. |
| **Không thể rotate nhanh** | Key được biên dịch cố định và cần deploy mọi consumer để thay. | Khóa bị lộ vẫn được chấp nhận trong cửa sổ chuyển đổi dài. |
| **Thiếu provenance** | Không biết ai sinh khóa, nguồn entropy, owner hoặc ngày kích hoạt. | Khó đánh giá độ tin cậy và điều tra sự cố. |
| **Lỗi dùng lại khóa** | Một key AES/HMAC được tái dùng cho nhiều purpose. | Lẫn ranh giới bảo mật, tăng tác động khi secret bị lộ. |
| **Không có audit key usage** | Ứng dụng dùng local key thay vì KMS Sign/Decrypt. | Không biết workload nào đã thực hiện thao tác quan trọng. |
| **Rủi ro khôi phục/hủy** | Không có key version, predecessor hoặc nơi quản lý chính thức. | Khó xác định dữ liệu phụ thuộc và không thể crypto-shred đáng tin. |

**Lỗi không nằm ở độ dài khóa.** Một AES-256 key cố định bị lộ vẫn là **khóa đã bị lộ**, dù thuật toán có mức bảo vệ cao. Mật mã không thể giữ bí mật cho dữ liệu nếu kẻ tấn công biết key.

### 1.2. “Không đẩy lên Git công khai” vẫn chưa đủ

Kho Git private cũng có quyền của nhiều người, runner CI, hệ backup, hệ thống code review và các tích hợp bên thứ ba. Một secret đã từng xuất hiện trong commit có thể tồn tại trong:

- Git history, tags, branches, forks hoặc clone trên máy cá nhân.
- CI/CD logs, job artifacts, build cache và image layers.
- Pull request diff, comment, hệ thống indexing và secret-scanning.
- Bản sao lưu repository hoặc kho lưu trữ của bên cung cấp dịch vụ.
- Binary đã phát hành cho khách hàng hoặc phiên bản cũ còn trong production.

Vì vậy **xóa dòng chứa key ở commit mới không đủ xử lý một key đã bị lộ**. Cần coi việc lộ secret là sự cố và **thu hồi/xoay khóa cùng đánh giá dữ liệu phụ thuộc**.

## 2. Phân biệt key material với key ID, public key và cấu hình

Không phải mọi chuỗi liên quan đến khóa đều là bí mật.

| Giá trị | Có phải key material bí mật? | Có thể xuất hiện trong config/source? | Lưu ý |
| --- | --- | --- | --- |
| **AES DEK rõ** | **Có**. | **Không hard-code.** | Chỉ nhận từ KMS/nguồn sinh tin cậy khi cần, hạn chế thời gian hiện diện trong RAM. |
| **KEK/secret key HMAC** | **Có**. | **Không hard-code.** | Ưu tiên KMS/HSM non-exportable khi phù hợp; kiểm soát API dùng khóa. |
| **Private key Ed25519/RSA/EC** | **Có**. | **Không hard-code.** | Lưu trong HSM/KMS/keystore được bảo vệ theo chính sách. |
| **Seed hoặc recovery phrase sinh khóa** | **Có**, nếu có thể tái tạo secret. | **Không hard-code.** | Có thể có phạm vi ảnh hưởng lớn hơn một khóa con. |
| **Password/pepper/PSK** | **Có** (mức và cách bảo vệ tùy loại). | **Không hard-code.** | Password yếu còn cần KDF/PAKE phù hợp; pepper là secret. |
| **KMS key ID/ARN/reference** | Thông thường **không**. | Có thể lưu như **config** được quản lý. | Reference không phải quyền truy cập; vẫn cần IAM và phân vùng tenant. |
| **Public key để Verify** | **Không** về bí mật. | Có thể được phân phối/ghim theo chính sách tin cậy. | Phải xác thực nguồn, thuật toán, issuer và rotation. |
| **Public certificate X.509** | **Không** về bí mật. | Có thể lưu/phân phối theo mục đích. | Không nhầm certificate với private key. |
| **Salt của password hash** | **Không**. | Thường lưu cùng verifier record. | Nên khác nhau/được sinh phù hợp; không thay pepper. |
| **Nonce/IV của AES-GCM** | **Không**. | Thường lưu cùng ciphertext. | **Không được reuse dưới cùng key**; không dùng hằng nonce cho mọi lần encrypt. |
| **Wrapped DEK** | Là **ciphertext bảo vệ khóa**, không phải DEK rõ. | Có thể lưu cùng ciphertext. | Phải bảo vệ tính toàn vẹn, context và quyền Unwrap; không coi là vô hại. |

**Key ID được hard-code trong ví dụ không giống hard-code key material**. Tuy nhiên, một key ID production được đóng cố định vào JAR có thể làm **khó chuyển môi trường và rotate**. Thường nên để key reference trong **configuration quản lý theo môi trường** và kiểm tra nó theo allowlist/policy phía server.

**Public key có thể được pin** theo thiết kế, vì nó không bí mật. Nhưng nếu không có kế hoạch thay public key/chứng chỉ, việc pin một giá trị duy nhất có thể khiến dịch vụ ngừng hoạt động khi rotate hoặc revoke. Không dùng việc “key công khai” để biện minh cho việc chấp nhận public key do request chưa xác thực đưa tới.

## 3. Những hình thức hard-code gián tiếp dễ bị bỏ sót

Developer có thể xóa hằng `AES_KEY` nhưng bí mật vẫn bị đóng gói dưới hình thức khác:

1. **YAML/properties/JSON trong repository:** trường `encryption.key`, `jwt.privateKey`, `pepper` chứa raw secret.
2. **Dockerfile và container image:** `ENV SECRET=...`, `ARG` build-time hoặc `RUN echo...` có thể để lại dấu vết ở image layers/history.
3. **Kubernetes manifest:** ConfigMap không phải kho bí mật; Kubernetes Secret chỉ là cơ chế lưu secret, cần quyền, mã hóa at rest và kiểm soát truy cập theo cấu hình. Không commit giá trị bí mật vào manifest.
4. **Infrastructure as Code:** biến chứa secret có thể xuất hiện trong state, plan output, CI log hoặc diff nếu quản lý sai.
5. **Client/mobile/browser:** JavaScript frontend, Android APK và desktop binary thường có thể bị người sở hữu thiết bị phân tích. Không đặt **server-wide private key, DEK hoặc HMAC signing secret** trong client.
6. **Test fixture:** khóa mẫu vô tình dùng chung với production; test bị đóng vào artifact thật.
7. **Script khởi tạo database:** một migration ghi static key vào bảng cấu hình của mọi khách hàng.
8. **Obfuscation:** khóa được chia thành ba chuỗi, biến đổi XOR/Base64 rồi ghép lại lúc chạy.
9. **Fallback khi KMS lỗi:** có một local secret cố định để “dịch vụ không gián đoạn”.
10. **Mã sinh tự động và tài liệu:** copy secret thật vào notebook, prompt, issue, screenshot hoặc ví dụ nội bộ.

**Biến môi trường không tự biến secret thành an toàn.** Đây có thể là **kênh phân phối** do platform kiểm soát, nhưng giá trị vẫn có thể lộ qua process dump, log, quyền đọc môi trường hoặc cấu hình debug. Ưu tiên danh tính workload và cơ chế secret/key management phù hợp, không xem `System.getenv("SECRET")` là giải pháp đầy đủ.

### 3.1. Trường hợp đặc biệt: mã chạy trên thiết bị người dùng

Nếu **toàn bộ người dùng đều có cùng một bí mật nhúng trong ứng dụng** để xác thực với server, họ có thể trích xuất nó và mạo danh ứng dụng. Một API key được dùng trong frontend chỉ nên được coi là **public identifier** nếu thiết kế dịch vụ cho phép, kết hợp quota/domain/rate limit thích hợp; **không được coi nó là secret server-side**.

Các khóa lưu cục bộ phục vụ một người dùng có thể thuộc mô hình khác (ví dụ keystore bảo mật của OS/hardware-backed key). Khi đó phải giải thích rõ **ai là chủ khóa, khóa dùng để làm gì, khả năng export/backup và trust boundary**, chứ không dùng một constant chung trong binary.

## 4. Cách tiếp cận đúng: sinh và giữ khóa tại ranh giới tin cậy

### 4.1. Chọn nguồn sinh khóa phù hợp

- **CSPRNG/DRBG:** dùng nguồn ngẫu nhiên mật mã do OS/provider hỗ trợ, có entropy phù hợp; không sinh khóa bằng `Math.random()`, `java.util.Random`, timestamp hay PID.
- **KMS/HSM:** ưu tiên để provider sinh và giữ **private signing key, KEK hoặc root key** trong ranh giới đã phê duyệt khi khả năng sản phẩm đáp ứng.
- **KeyGenerator/KeyPairGenerator:** khi khóa được sinh cục bộ theo policy, sử dụng API mật mã chuẩn và có kế hoạch lưu giữ/cấp phát sau đó.
- **Tách mục đích:** không dùng cùng bytes khóa AES làm HMAC secret; dùng các key độc lập hoặc KDF chuẩn với domain separation nếu giao thức cho phép.
- **Metadata ngay khi sinh:** xác định algorithm, key length, owner, tenant, purpose, môi trường, version, cryptoperiod và trạng thái vòng đời.
- **Chống nhân bản trạng thái RNG:** đánh giá fork/VM restore/container snapshot; không đưa fixed seed vào image.

### 4.2. Ví dụ Java 17: tạo khóa mới mà không nhúng secret

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class GenerateKeyExample {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        // Sinh AES-256 bằng provider, không dùng chuỗi hằng làm khóa.
        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(256, random);
        SecretKey dataKey = aesGenerator.generateKey();

        // Ví dụ cặp khóa ký số; đừng in/lưu private key dạng rõ.
        KeyPairGenerator signer = KeyPairGenerator.getInstance("Ed25519");
        KeyPair signingKeyPair = signer.generateKeyPair();

        System.out.println("DEK algorithm: " + dataKey.getAlgorithm());
        System.out.println("Signing algorithm: "
                + signingKeyPair.getPublic().getAlgorithm());
    }
}
~~~

Ví dụ chỉ chứng minh **cách gọi API sinh khóa**. Nó **không phải giải pháp lưu khóa sản xuất**: khóa AES và private key hiện vẫn nằm trong tiến trình Java, chưa có KMS/HSM custody, key registration, version, audit, quyền sử dụng hay backup. Việc sinh lại một DEK khi khởi động **không giúp giải mã ciphertext cũ** nếu không lưu đường phục hồi phù hợp.

### 4.3. Đừng tự mã hóa một hard-coded key rồi gọi đó là bảo vệ

~~~text
SAI:
  key thật --> Base64/XOR/mã hóa bằng một hằng khác --> nhúng vào JAR
  JAR có thuật toán + hằng giải mã --> khôi phục key thật

ĐÚNG HƯỚNG:
  workload identity --> KMS/HSM policy --> Key API theo mục đích
  ứng dụng giữ key reference và metadata; không hard-code secret
~~~

Nếu **khóa giải mã bí mật cũng nằm trong artifact**, kẻ tấn công có thể phân tích quy trình để khôi phục secret. Mã hóa key trong cấu hình chỉ hữu ích khi **khóa bảo vệ cấu hình được quản lý độc lập** và ranh giới truy cập được kiểm soát.

## 5. KMS/HSM và quản lý quyền: không hard-code secret cũng chưa đủ

Một thiết kế phổ biến:

~~~mermaid
flowchart TD
    APP["Ứng dụng đã xác thực bằng workload identity"] --> IAM["IAM / KMS policy"]
    IAM --> KMS["KMS/HSM giữ KEK hoặc private key"]
    KMS --> SIGN["Sign / Verify / Decrypt / Unwrap theo quyền"]
    KMS --> GEN["GenerateDataKey: DEK rõ tạm + wrapped DEK"]
    GEN --> ENC["Ứng dụng dùng AEAD với DEK tạm trong RAM"]
    ENC --> DB["Ciphertext + nonce/tag + wrapped DEK + key reference"]
    DB --> DEC["Ứng dụng được phép đọc"]
    DEC --> KMS
    APP --> AUDIT["Audit: actor, key ID, operation, result"]
    KMS --> AUDIT
~~~

**Đường trên là mô hình khái niệm**, không phải API duy nhất của mọi nhà cung cấp. Một KMS có thể không hỗ trợ trả DEK rõ hoặc có key operations/semantics khác. Ứng dụng phải chọn mô hình **được provider hỗ trợ và security team phê duyệt**.

### 5.1. Private key không xuất khỏi HSM

Với **Ed25519/ECDSA/RSA-PSS**, có thể thiết kế **Sign trong KMS/HSM**; ứng dụng gửi digest hoặc message theo API đã chọn, nhận chữ ký và không cần biết private key bytes. Với **RSA decrypt** hoặc key agreement, khả năng thực hiện trong HSM phụ thuộc nhà cung cấp, thuật toán và mode.

**Non-exportable** giúp giảm rủi ro rò private key từ ứng dụng, nhưng nếu workload có quyền `Sign` trên mọi dữ liệu, kẻ xâm nhập workload vẫn có thể tạo chữ ký giả. Do đó cần **key usage policy, phân quyền nghiệp vụ trước khi ký, rate limit, audit và theo dõi bất thường**.

### 5.2. Workload identity thay vì credential hard-coded

Không đặt static cloud access key trong code để gọi KMS. Sử dụng cơ chế **danh tính dịch vụ ngắn hạn** hoặc metadata/workload identity được platform hỗ trợ, cùng IAM giới hạn:

- Chỉ được dùng **đúng key ID hoặc key family** cho ứng dụng, tenant và environment.
- Chỉ được gọi operations cần thiết, ví dụ `GenerateDataKey` và `DecryptDataKey` đối với Billing.
- Không được tự ý `ExportKey`, `ScheduleKeyDeletion`, thay trust root hoặc mở rộng policy.
- Ghi lại actor, key reference, thời điểm, kết quả và request correlation ID.
- Tách **quyền vận hành KMS**, **quyền phê duyệt rotation/destruction** và **quyền dùng khóa**.

**KMS key ID không phải mật khẩu.** Biết key ID không cấp quyền nếu IAM đúng, nhưng key ID vẫn có thể tiết lộ kiến trúc và không nên được ghi công khai bừa bãi.

## 6. Envelope encryption: ứng dụng chỉ cầm DEK tạm thời

Trong **envelope encryption**, DEK được dùng để mã hóa dữ liệu; KEK bảo vệ DEK. Đây là một phương án quan trọng để không phải nhúng cùng AES key cố định vào mọi instance.

~~~mermaid
sequenceDiagram
    participant App as Billing Service
    participant KMS as KMS/HSM
    participant DB as Database
    App->>KMS: GenerateDataKey(approved KEK ref, context)
    KMS-->>App: plaintext DEK tạm thời + wrapped DEK
    Note over App: CSPRNG nonce, AES-GCM + AAD
    App->>DB: Ciphertext, nonce/tag, wrapped DEK, key refs
    Note over App: Dọn mảng DEK khi không còn cần
    App->>DB: Đọc bản ghi đã được cấp quyền
    DB-->>App: Ciphertext và metadata
    App->>KMS: DecryptDataKey(wrapped DEK, context)
    KMS-->>App: plaintext DEK tạm thời
    Note over App: Kiểm tra AEAD tag trước khi dùng plaintext
~~~

### 6.1. Những dữ liệu cần lưu cùng bản mã

| Trường | Vai trò | Lưu ý |
| --- | --- | --- |
| **Ciphertext + authentication tag** | Dữ liệu mã hóa có kiểm tra toàn vẹn. | Phải kiểm tra tag khi giải mã; không bỏ qua nếu lỗi. |
| **Nonce/IV** | Tham số AEAD, ví dụ 96-bit nonce AES-GCM. | Không trùng theo cùng key; bản thân nonce không cần bí mật. |
| **Wrapped DEK** | DEK đã được bảo vệ bởi KEK theo KMS. | Không phải DEK rõ; phải gắn với context và key reference. |
| **KEK/key reference và version** | Định vị khóa giải bọc theo khả năng provider. | Không chỉ dùng alias current nếu bản mã lịch sử cần phiên bản cũ. |
| **Schema/algorithm version** | Biết cách diễn giải ciphertext, AAD, encoding. | Hỗ trợ migration và backward compatibility. |
| **Encryption context/AAD** | Ràng buộc tenant, object, purpose và dữ liệu có ý nghĩa bảo mật. | Không chấp nhận context từ input chưa được xác thực. |

Một số KMS tự lưu key metadata trong encrypted blob. Developer phải hiểu cơ chế của provider và tránh tự giả định key version hiện diện dưới định dạng chung.

### 6.2. Lỗi “giữ DEK trong cache mãi mãi”

Nếu một DEK được tái sử dụng cho hàng triệu bản ghi, developer phải quản lý **nonce uniqueness, giới hạn số lần mã hóa và cryptoperiod**. Cache plaintext DEK không giới hạn làm tăng thời gian vật liệu khóa tồn tại trong RAM và tác động của một lần compromise.

Nếu dùng **data-key caching** theo SDK hoặc cơ chế đã phê duyệt, cần có giới hạn theo **thời gian, dung lượng dữ liệu, số lượt mã hóa, tenant/purpose** và cách vô hiệu hóa khi rotate/revoke. Không để mọi instance cùng một DEK rồi reset nonce counter về 0 sau restart.

**Rotate KEK không tự thay DEK**. Nếu DEK bị lộ, chỉ bọc lại cùng DEK dưới KEK mới không làm ciphertext cũ bí mật trở lại; có thể cần re-encrypt dưới DEK mới.

## 7. Java 17: mã ứng dụng dùng key reference thay vì hard-coded key

Ví dụ sau thể hiện ranh giới trách nhiệm:

- **KeyProvider** là adapter cho SDK KMS/HSM được đội platform cung cấp. Nó không được triển khai bằng local secret hard-coded.
- **KeyPolicy** lấy danh tính workload/tenant và quyết định key reference đang active cũng như các phiên bản cũ còn cho phép giải mã.
- **EnvelopeService** dùng DEK tạm để AES-GCM; ciphertext lưu wrapped DEK và metadata; code không biết **bytes của KEK**.
- Kiểm tra quyền trên dữ liệu diễn ra **trước khi gọi KMS**, không chỉ dựa vào `DecryptDataKey` thành công.

**Đây là đoạn mã minh họa có thể biên dịch với Java 17, nhưng không thể vận hành một mình:** cần adapter KMS/KeyPolicy và hệ thống authorization tin cậy, persistence, key inventory và kiểm thử tích hợp. Không đưa trực tiếp vào production khi chưa thực hiện các bước đó.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class NoHardcodedKeyExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int DEK_BYTES = 32;    // AES-256
    private static final int NONCE_BYTES = 12;  // 96-bit GCM nonce
    private static final int TAG_BITS = 128;

    public interface KeyProvider {
        // Provider sinh DEK mới và bọc dưới KEK theo keyRef.
        DataKey generateDataKey(String keyRef,
                                Map<String, String> context) throws Exception;

        // Provider giải bọc theo IAM/context; không xuất KEK.
        byte[] unwrapDataKey(String keyRef, byte[] wrappedDek,
                             Map<String, String> context) throws Exception;
    }

    public interface KeyPolicy {
        // Phải kiểm tra principal có quyền với tenant/object.
        void authorize(String principal, String tenant,
                       String objectId, String operation);

        // Key reference đáng tin đến từ cấu hình/registry của server.
        String activeKeyRef(String tenant);

        // Cho phép đọc bằng key version cũ theo chính sách.
        boolean approvedForDecryption(String tenant, String keyRef,
                                      String keyVersion);
    }

    public record DataKey(byte[] plaintextDek, byte[] wrappedDek,
                          String keyVersion) {}

    public record EncryptedObject(
            String tenant,
            String objectId,
            String keyRef,
            String keyVersion,
            byte[] wrappedDek,
            byte[] nonce,
            byte[] ciphertextWithTag) {}

    private final KeyProvider kms;
    private final KeyPolicy policy;

    public NoHardcodedKeyExample(KeyProvider kms, KeyPolicy policy) {
        this.kms = Objects.requireNonNull(kms);
        this.policy = Objects.requireNonNull(policy);
    }

    private static Map<String, String> context(String tenant,
                                                String objectId) {
        return Map.of("purpose", "billing-record-v1",
                "tenant", tenant, "object", objectId);
    }

    private static byte[] aad(String tenant, String objectId)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        for (String value : new String[] {
                "billing-record-v1", tenant, objectId }) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            out.writeInt(bytes.length);
            out.write(bytes);
        }
        out.flush();
        return buffer.toByteArray();
    }

    public EncryptedObject encrypt(String principal, String tenant,
                                   String objectId, byte[] plaintext)
            throws Exception {
        Objects.requireNonNull(plaintext);
        if (tenant == null || tenant.isBlank()
                || objectId == null || objectId.isBlank()) {
            throw new SecurityException("Invalid object identity");
        }

        // Authorization theo dữ liệu nghiệp vụ trước khi cấp DEK.
        policy.authorize(principal, tenant, objectId, "ENCRYPT");
        String keyRef = policy.activeKeyRef(tenant);
        if (keyRef == null || keyRef.isBlank()) {
            throw new SecurityException("No approved key reference");
        }

        DataKey dataKey = kms.generateDataKey(
                keyRef, context(tenant, objectId));
        if (dataKey == null || dataKey.plaintextDek() == null
                || dataKey.plaintextDek().length != DEK_BYTES
                || dataKey.wrappedDek() == null
                || dataKey.wrappedDek().length == 0
                || dataKey.keyVersion() == null
                || dataKey.keyVersion().isBlank()) {
            throw new SecurityException("Invalid KMS data key");
        }

        byte[] dek = dataKey.plaintextDek();
        try {
            // Một DEK mới cho mỗi đối tượng được mã hóa trong demo.
            byte[] nonce = new byte[NONCE_BYTES];
            RANDOM.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(tenant, objectId));
            byte[] ciphertext = cipher.doFinal(plaintext);

            // Lưu nhất quán: ciphertext, nonce, wrapped DEK và version.
            return new EncryptedObject(
                    tenant, objectId, keyRef, dataKey.keyVersion(),
                    dataKey.wrappedDek().clone(), nonce, ciphertext);
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    public byte[] decrypt(String principal, String tenant,
                          String objectId, EncryptedObject record)
            throws Exception {
        Objects.requireNonNull(record);
        policy.authorize(principal, tenant, objectId, "DECRYPT");

        if (!Objects.equals(tenant, record.tenant())
                || !Objects.equals(objectId, record.objectId())
                || record.keyRef() == null
                || record.keyVersion() == null
                || !policy.approvedForDecryption(
                        tenant, record.keyRef(), record.keyVersion())
                || record.wrappedDek() == null
                || record.wrappedDek().length == 0
                || record.nonce() == null
                || record.nonce().length != NONCE_BYTES
                || record.ciphertextWithTag() == null
                || record.ciphertextWithTag().length < TAG_BITS / 8) {
            throw new SecurityException("Untrusted encrypted record");
        }

        byte[] dek = kms.unwrapDataKey(
                record.keyRef(), record.wrappedDek(),
                context(tenant, objectId));
        if (dek == null || dek.length != DEK_BYTES) {
            throw new SecurityException("Invalid KMS data key");
        }

        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, record.nonce()));
            cipher.updateAAD(aad(tenant, objectId));

            // doFinal xác minh tag; lỗi => không trả plaintext.
            return cipher.doFinal(record.ciphertextWithTag());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }
}
~~~

### 7.1. Vì sao ví dụ này không hard-code key?

1. **Không tồn tại hằng số chứa raw DEK/KEK**. KMS sinh DEK ở thời điểm cần và quản lý KEK.
2. Key reference được lấy qua **KeyPolicy tin cậy**, không lấy từ yêu cầu tùy ý của client.
3. Ứng dụng chỉ giữ **DEK rõ trong bộ nhớ ngắn hạn**, dùng và cố gắng xóa mảng khi hoàn tất.
4. **Tenant/object/purpose** đi vào cả KMS context và AAD theo một cách mã hóa xác định; giá trị phải đến từ nguồn đã được xác thực.
5. Ciphertext và wrapped DEK có **key reference và version**, giúp phục vụ rotation/restore.
6. **Không fallback** sang hằng khóa khi KMS lỗi; exception được xử lý ở lớp vận hành theo fail-closed.
7. API kiểm tra quyền trước thao tác; **KMS IAM vẫn phải kiểm tra độc lập** ở điểm thực thi.

### 7.2. Những giới hạn cần giải quyết trước production

- **Adapter KMS chưa có:** phải dùng SDK, workload identity, timeout, rate limit, audit và encryption context theo contract của provider.
- **KeyPolicy là đường tin cậy quan trọng:** cần tra cứu owner/tenant/key version từ nguồn server-side đã bảo vệ, không tin body hoặc header request.
- **Dữ liệu trong Java record chứa byte[] có thể bị thay đổi:** production nên dùng defensive copies, giới hạn dữ liệu và kiểm tra schema/version.
- **Arrays.fill không chứng minh xóa hết secret:** `SecretKeySpec`, provider và JVM có thể có bản sao trong bộ nhớ; tránh core dump và giảm thời gian sống của plaintext.
- **Nonce ngẫu nhiên vẫn có xác suất va chạm**, dù với một DEK mới cho mỗi đối tượng trong demo thì phạm vi dưới một key được hạn chế. Khi cache/reuse DEK cần chính sách key/nonce và ngân sách mã hóa chặt chẽ.
- **Không có pipeline backup/recovery** trong ví dụ: nếu KMS/key version cũ bị hủy, bản mã có thể không đọc được.
- **Lỗi logic/policy có thể vẫn xảy ra** nếu implementation của `authorize` hoặc `approvedForDecryption` sai; cần negative/integration tests.
- **KMS trả DEK rõ về ứng dụng** là một mô hình có cân nhắc rủi ro; với dữ liệu/khóa cần ranh giới cao hơn có thể dùng phép mã hóa trực tiếp trong KMS/HSM theo khả năng và hiệu năng của sản phẩm.
- Giao diện trả `keyVersion` là **abstraction của hệ thống**, không khẳng định mọi provider đều công khai material version; adapter phải cung cấp **tham chiếu xác thực được** theo đúng hợp đồng.

### 7.3. Ví dụ cấu hình: key reference, không phải secret

~~~properties
# Ví dụ cấu hình triển khai: key reference, không chứa raw key bytes.
billing.crypto.kekRef=kms://production/billing/approved-kek
billing.crypto.format=envelope-v1
~~~

Một property key reference không nên do end user sửa hoặc tự trỏ tới key ngoài phạm vi. Nếu dùng biến môi trường `BILLING_KEK_REF`, đó chỉ là **tham chiếu quản trị**, không phải nơi nạp raw KEK dưới dạng plaintext.

## 8. Làm thế nào để không hard-code khóa ký số?

Với private signing key, cấu trúc tốt là **KMS/HSM Sign-as-a-Service** thay vì `PrivateKey` được load từ một file PEM nhúng trong JAR:

~~~text
Payment Service
  -> kiểm tra quyền ký sự kiện và chuẩn hóa nội dung
  -> KMS/HSM Sign(keyRef, message/digest theo API)
  <- signature
  -> phát hành event + signature + key ID/version

Ledger Service
  -> nhận public key từ trust registry/JWKS/PKI đáng tin
  -> Verify + kiểm tra issuer, audience, tenant, event ID, replay
  -> ghi sổ nếu toàn bộ điều kiện hợp lệ
~~~

**Không cần giữ private key trong mã nguồn hoặc mỗi container.** Tuy nhiên một signer có quyền gọi `Sign` vẫn có thể bị lạm dụng; cần policy về **nội dung được ký, caller identity, key usage, rate limit, approval khi cần và audit**.

### 8.1. Public key không bí mật nhưng phải đáng tin

Một public key Ed25519 trong file cấu hình có thể là **trust anchor** hoặc key pin hợp lệ theo kiến trúc. Nó không phải vi phạm “không hard-code secret”. Tuy nhiên khi verifier nhận một public key/JWKS URL từ token chưa xác thực, kẻ tấn công có thể tự tạo cặp khóa và chữ ký hợp lệ dưới chính public key giả đó.

Verifier cần gắn **issuer, domain/service identity, mục đích, thuật toán và key ID** với một **nguồn trust được cấp phát an toàn**. Rotation phải công bố S2 trước khi ký mới, và xử lý cửa sổ tin S1 theo chính sách.

### 8.2. Vì sao không dùng cùng HMAC secret cho mọi service?

HMAC/KMAC yêu cầu các bên biết cùng secret. Nếu một secret hard-coded được sao chép vào mười dịch vụ, **một dịch vụ bị chiếm quyền có thể giả mạo thông điệp như những dịch vụ khác** trong phạm vi chia sẻ. Nên:

- Tách key theo **service/tenant/purpose**.
- Dùng secret manager/KMS/HSM theo policy.
- Có **key ID/version** để bên nhận chọn đúng secret hợp lệ.
- Duy trì cửa sổ chấp nhận MAC cũ có giới hạn khi rotate.
- Không dùng cùng secret HMAC cho AES, password pepper hoặc JWT signing ngoài thiết kế đã được đánh giá.

## 9. Quy trình xoay vòng khóa khi phát hiện hard-code

Phát hiện key hard-coded trong repository không chỉ là công việc “sửa một dòng code”. Phải giả định rằng **một số bên ngoài phạm vi mong muốn có thể đã lấy được key** cho đến khi có bằng chứng đánh giá khác.

### 9.1. Trình tự ứng phó

1. **Xác định secret:** raw AES key, private key, HMAC secret, PSK, pepper, API token hay chỉ là key ID/public key? Không tự kết luận mọi chuỗi giống khóa đều là bí mật.
2. **Khoanh vùng:** repository, nhánh, commit, artifact, container, environment, tenant, service và thời gian khóa tồn tại.
3. **Đánh giá tác động:** key dùng cho ENCRYPT/DECRYPT, SIGN/VERIFY, MAC, WRAP/UNWRAP hay auth? Dữ liệu/chữ ký nào phụ thuộc?
4. **Chặn đường lộ tiếp:** ngừng log/đóng gói secret; kiểm soát truy cập kho bị ảnh hưởng; cô lập credential hoặc key usage theo quyết định incident commander.
5. **Tạo khóa thay thế từ nguồn đáng tin:** dùng KMS/HSM hoặc provider đúng, gắn owner/usage/version mới và quyền tối thiểu.
6. **Chuyển consumer:** cập nhật signer/verifier, dữ liệu encrypted, dịch vụ nội bộ và hệ thống có PSK theo kế hoạch migration.
7. **Thay vật liệu cần thay:** nếu **DEK** lộ, đánh giá re-encrypt; nếu **private signing key** lộ, điều tra chữ ký giả và cập nhật trust/revocation; nếu **KEK** lộ, đánh giá DEK được bọc và quyền unwrap.
8. **Thu hồi khóa cũ:** disable/revoke theo điều kiện an toàn, không tự destroy khi backup/ciphertext lịch sử còn phụ thuộc.
9. **Làm sạch nơi chứa secret:** Git history, CI logs/artifacts, image tags, tickets và backups **theo khả năng và quy trình hợp lệ**; không tuyên bố việc xóa này là đủ thay rotation.
10. **Theo dõi và hậu kiểm:** audit key usage, trạng thái revoke, những nơi còn sử dụng key version cũ, cập nhật secret scanning và thiết kế để lỗi không lặp lại.

**Không chép giá trị secret đã lộ vào ticket hay câu lệnh kiểm tra công khai**. Dùng fingerprint/định danh sự cố đã được phép và bằng chứng truy cập hạn chế; việc băm một key entropy thấp cũng cần thận trọng vì có thể hỗ trợ dò.

### 9.2. Phân biệt các loại rotation

| Khóa bị lộ | Chỉ đổi key reference đủ không? | Hành động cần xem xét |
| --- | --- | --- |
| **DEK AES mã hóa dữ liệu** | **Không.** | Sinh DEK mới, re-encrypt dữ liệu cần bảo vệ; đánh giá plaintext/backup đã bị đọc. |
| **KEK dùng wrap DEK** | **Không nhất thiết.** | Điều tra DEK có thể bị ảnh hưởng, rewrap/chuyển KEK và re-encrypt nếu DEK bị lộ. |
| **Private key ký số** | **Không.** | Thu hồi quyền ký và trust phù hợp, phát hành key mới, điều tra chữ ký lịch sử có nguy cơ giả. |
| **HMAC secret/PSK** | **Không.** | Cấp secret mới cho các bên, cắt cửa sổ chấp nhận cũ, vô hiệu hóa phiên/token bị ảnh hưởng. |
| **Key ID không bí mật** | Có thể **không cần** rotate vật liệu. | Sửa cấu hình/quyền hoặc ẩn metadata nếu có rủi ro riêng; xác minh không đi kèm secret. |
| **Public key/CA certificate** | Không tự vì là public. | Đánh giá nguồn trust, tính toàn vẹn và khả năng thay thế theo PKI/trust policy. |

Nếu một key đã được **dùng sai nonce AES-GCM**, việc thay key sau đó không khôi phục tính an toàn của ciphertext cũ. Cần đánh giá dữ liệu trong khoảng ảnh hưởng theo threat model.

### 9.3. Đừng hủy khóa cũ trước khi xác minh dependency

Nếu một DEK cũ mã hóa backup lịch sử, việc destroy khóa có thể làm mất khả năng giải mã vĩnh viễn. Key inventory cần ghi **material version, predecessor, ciphertext, wrapped DEK, backups, retention và consumer**. Ngược lại, nếu dùng **crypto-shredding**, phải xác minh tất cả bản sao key trong phạm vi đã bị hủy thì mới có thể khẳng định dữ liệu không còn đường giải mã tương ứng.

## 10. CI/CD, code review và phát hiện key hard-coded

**Phòng ngừa** nên bắt đầu trước khi secret vào Git, thay vì chỉ dựa vào cảnh báo sau deploy.

### 10.1. Những điểm kiểm soát đề xuất

- **Pre-commit/CI secret scanning:** phát hiện private key PEM, token, mật khẩu và entropy bất thường; dùng rule tùy loại key.
- **Git history và artifact scanning:** quét cả lịch sử và image/build output theo phạm vi được phép, không chỉ diff của PR hiện tại.
- **Static analysis/policy-as-code:** cấm API RNG không phù hợp trong đường tạo secret; phát hiện hằng `SecretKeySpec` hoặc chuỗi secret trong source.
- **Infrastructure review:** chặn `ENV SECRET=...`, plaintext IaC state không được bảo vệ và shared credentials rộng.
- **Environment isolation:** test/staging/prod dùng key references và IAM principals riêng; không cho runner dev quyền Decrypt production.
- **Mandatory review:** mọi thay đổi liên quan KMS key ID, trust store, signing key và encryption context cần người có năng lực bảo mật kiểm tra.
- **Dependency management:** dùng thư viện crypto/KMS SDK đã được phê duyệt; tránh lấy mã nguồn “encrypt util” tự viết không có kiểm chứng.
- **Observability:** đo KMS latency/errors, key usage, rotation readiness mà không ghi key material.
- **Response playbook:** khi scanner phát hiện secret thật, có owner được thông báo và đường xử lý rotate/revoke nhanh.

### 10.2. Không tin tuyệt đối vào scanner

Scanner có thể bỏ sót secret bị chia nhỏ, biến đổi, sinh từ seed cố định hoặc chèn ở runtime; cũng có thể báo nhầm một public key, key ID hoặc chuỗi test giả.

Vì vậy cần kết hợp **code review, IAM policy review, threat model, negative tests và kiểm tra thực tế khi chạy**. Tuyệt đối không paste một secret thật vào công cụ trực tuyến chưa được tổ chức phê duyệt chỉ để “xem nó có phải khóa không”.

### 10.3. Test không dùng khóa sản xuất

Trong unit test, có thể dùng **khóa thử nghiệm được tạo ngẫu nhiên cho mỗi lần chạy** hoặc fixed test vector **không có giá trị production** để kiểm tra thuật toán. Nếu dùng test vector cố định, cần ghi rõ **TEST ONLY**, cô lập môi trường và bảo đảm không thể được chọn làm fallback khi KMS production lỗi.

**Tính tái lập của test không phải lý do cho secret cố định trong production.** Có thể truyền dependency `KeyProvider` giả vào test để kiểm soát kết quả mà không viết hằng khóa vào mã triển khai.

## 11. Kiểm thử hành vi ứng dụng khi KMS/secret store gặp lỗi

Một pattern nguy hiểm:

~~~text
try:
    return KMS.GetKey(...)
catch:
    return BUILT_IN_DEFAULT_KEY   # SAI
~~~

Với dữ liệu nhạy cảm, **fail closed** là mặc định: không chuyển sang local key hard-coded và không bỏ xác thực khi KMS timeout.

| Tình huống | Kỳ vọng của ứng dụng |
| --- | --- |
| **KMS AccessDenied** | Từ chối thao tác; không fallback sang shared key. |
| **KMS tạm không sẵn sàng** | Retry có giới hạn và backoff; ghi lỗi an toàn, không bỏ mã hóa. |
| **Key reference không hợp lệ** | Từ chối; không cho caller chọn key khác ngoài scope. |
| **Alias chuyển version** | Dữ liệu mới dùng key active; dữ liệu cũ vẫn giải mã theo metadata/policy. |
| **Private signing key bị revoke** | Không thể ký mới; verifier nhận trust update và xử lý chữ ký cũ theo policy. |
| **AES-GCM tag sai** | Không trả plaintext, không lờ lỗi. |
| **Tenant mismatch** | Authorization từ chối trước khi Decrypt/Unwrap. |
| **DEK cache hết hạn/bị thu hồi** | Loại bỏ secret khỏi cache theo khả năng, không tiếp tục dùng trái policy. |
| **Backup có key version cũ** | Restore dùng đúng version/nguồn KMS có thẩm quyền, không “thử mọi key”. |
| **Production chạy bằng test key ID** | Phát hiện cấu hình sai và không khởi động/không cho xử lý nhạy cảm. |

Nếu cần tính sẵn sàng cao, hãy giải quyết qua **HA, provider recovery, key caching có giới hạn, DR và thiết kế error budget được phê duyệt**, không tạo cửa hậu mật mã.

## 12. Đoạn tình huống: Payment, Billing và Ledger

Giả sử nền tảng có ba dịch vụ:

- **Billing Service:** mã hóa hóa đơn bằng AES-GCM; DEK được KMS sinh/bọc dưới KEK.
- **Payment Service:** ký sự kiện thanh toán bằng Ed25519 private key trong HSM/KMS.
- **Ledger Service:** xác minh chữ ký bằng public key S1/S2 từ nguồn trust đáng tin.

### 12.1. Thiết kế sai ban đầu

~~~text
Billing Service:
  String BILLING_AES_KEY = "...";   // giống nhau mọi instance/tenant
  AES-GCM nonce = 12 byte 0;        // reuse dưới cùng key

Payment Service:
  Ed25519 private key ở file resources/private.pem trong JAR

Ledger Service:
  lấy public key từ payload event, rồi Verify chữ ký bằng key đó
~~~

**Có ba lỗi độc lập:**

1. Billing **lộ/nhân bản DEK** và đồng thời **reuse nonce**, khiến bảo mật AES-GCM bị ảnh hưởng nghiêm trọng.
2. Payment **nhúng private key ký** vào artifact, ai có JAR có thể tìm cách trích xuất và giả mạo chữ ký.
3. Ledger không có **trust anchor**; attacker có thể tự tạo key pair, ký event và cung cấp public key của chính họ.

### 12.2. Thiết kế sau cải thiện

1. Billing lấy **KEK reference có kiểm soát** từ cấu hình production; IAM chỉ cho workload Billing dùng API đúng.
2. Mỗi đối tượng được bảo vệ bằng **DEK đủ entropy** qua KMS; lưu wrapped DEK, nonce/tag, schema, AAD, key reference/version.
3. Trước Decrypt, Billing kiểm tra quyền truy cập của caller với tenant và invoice ID.
4. Payment sử dụng KMS/HSM `Sign` trên thông điệp được chuẩn hóa, không xuất private key.
5. Ledger dùng public key từ **issuer/JWKS/PKI đã tin cậy**, kiểm tra signature, audience, tenant, event ID và chống replay.
6. Khi rotate S1 → S2, Ledger nhận/trust S2 trước khi Payment ký mới; S1 được xử lý theo chính sách lịch sử và sự cố.
7. Key inventory ghi owner, version, predecessor và phụ thuộc, hỗ trợ rewrap, re-encrypt, thu hồi/hủy.
8. Audit ghi actor, key ID, operation, kết quả và reason code, **không ghi DEK, private key hoặc plaintext**.

### 12.3. Nếu đã phát hành binary chứa private key?

Không thể tin rằng việc xóa `private.pem` ở bản phát hành tiếp theo sẽ thu hồi những bản cũ mà khách hàng đã tải. Phải coi private key đã **có khả năng bị lộ**, đánh giá phạm vi chữ ký, thu hồi/thay key, cập nhật verifier trust và theo dõi sự kiện đáng ngờ. Mức độ ảnh hưởng phụ thuộc khóa dùng để ký gì, những bản phát hành nào có khóa và ai có thể tiếp cận binary.

## 13. Checklist trước khi merge hoặc triển khai

1. **Không có raw key, private key, PSK, pepper hoặc seed bí mật** trong source, test artifact, Dockerfile, IaC state công khai hay binary phân phối?
2. Key material được sinh bằng **CSPRNG/KMS/HSM** theo thuật toán và mức bảo vệ đã duyệt?
3. Code có phân biệt **key reference/public key** với **secret key material** không?
4. Workload identity có được cấp phát an toàn, không hard-code long-lived cloud credential?
5. IAM và KMS policy có giới hạn **resource, operation, environment, principal, tenant** theo khả năng?
6. Có tách DEK, KEK, signing private key, MAC key và session key theo purpose?
7. AES-GCM có **nonce uniqueness**, AAD, tag verification và giới hạn key usage phù hợp?
8. Ciphertext có **wrapped DEK, key reference/version, nonce/tag và schema** đủ để restore/rotate?
9. Public key xác minh chữ ký có đến từ trust store/JWKS/PKI tin cậy, không từ request tùy ý?
10. Ứng dụng có kiểm tra **authorization dữ liệu** trước khi KMS Decrypt/Sign?
11. Khi KMS lỗi, có **fail closed** thay vì fallback sang một secret cố định?
12. Trong cache/bộ nhớ/log, có giới hạn tồn tại key material và tránh ghi plaintext/DEK/private key?
13. Có kế hoạch **xoay vòng theo version, migration, revocation, kiểm kê backup và destruction**?
14. CI/CD có secret scanning, artifact scanning, quyền build theo môi trường và quy trình ứng phó cảnh báo?
15. Có negative tests cho ciphertext bị sửa, tenant sai, key ID sai, signature sai và key version bị revoke?
16. Có audit thao tác KMS và ứng dụng với actor, key ID, thời gian, kết quả mà không lộ secret?
17. Các key thử nghiệm có được cô lập hoàn toàn với production?
18. Owner của key và quy trình báo sự cố/cấp quyền khẩn cấp có rõ ràng không?

## 14. Câu hỏi tự kiểm tra

1. Vì sao một khóa AES-256 hard-coded vẫn không an toàn nếu kẻ khác có source hoặc binary?
2. Base64, hex hoặc obfuscation có biến secret nhúng sẵn thành bí mật không? Vì sao?
3. Một **KMS key ID** khác **DEK/KEK rõ** ở chỗ nào?
4. Public key nằm trong trust store có vi phạm nguyên tắc không hard-code secret không? Cần gì để tin nó?
5. Vì sao chỉ chuyển AES key từ Java constant sang environment variable vẫn chưa đủ?
6. Điều gì có thể xảy ra khi cùng một DEK/nonce được dùng ở nhiều instance?
7. **KeyGenerator** và **SecureRandom** giúp gì, và còn thiếu gì so với quản lý khóa production?
8. Vì sao không nên đóng private signing key vào Android APK hoặc JAR phát hành?
9. Khi một KMS key **non-exportable**, ai vẫn có thể lạm dụng quyền `Sign` hoặc `Decrypt`?
10. Trong envelope encryption, developer thường cần giữ **DEK rõ** trong bao lâu?
11. Khi một secret có trong Git history, vì sao commit xóa secret không đủ xử lý?
12. Nếu DEK đã lộ, chỉ rotate KEK/rewrap DEK có làm ciphertext cũ bí mật trở lại không?
13. Làm thế nào để rotate signing key S1 → S2 mà không làm consumer từ chối chữ ký mới?
14. Vì sao **secret scanner PASS** chưa chứng minh code không chứa hard-coded secret ở mọi nơi?
15. Nếu KMS `AccessDenied`, có được dùng khóa mặc định hard-coded để tránh gián đoạn không?
16. Trước khi hủy khóa cũ, key inventory phải tìm những dependency và backup nào?

**Ghi nhớ:** **Không hard-code key** là quy tắc nền tảng của **key generation và key management**: **không nhúng secret vào source, config, artifact hoặc client**, mà sinh và sử dụng khóa qua nguồn ngẫu nhiên mật mã, KMS/HSM hoặc cơ chế secret management được phê duyệt. Ứng dụng nên mang **key reference, policy, metadata và khả năng xử lý vòng đời**, trong khi quyền sử dụng khóa được giới hạn và kiểm toán. Khi khóa đã lộ, phải **thu hồi/xoay vật liệu và đánh giá dữ liệu phụ thuộc**, không chỉ xóa chuỗi khỏi repository. An toàn cuối cùng đòi hỏi **phân quyền đúng, AEAD/nonce đúng, chữ ký được xác thực, rotation/recovery và bằng chứng audit** xuyên suốt vòng đời khóa.
