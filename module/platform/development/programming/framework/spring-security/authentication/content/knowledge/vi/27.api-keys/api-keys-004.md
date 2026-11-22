# Băm khóa khi chỉ cần đối chiếu và tách phần định danh khỏi bí mật

## 1. Vấn đề: API key là bí mật xác thực, nhưng máy chủ thường chỉ cần trả lời “có khớp không?”

Một API key thường là **bearer credential**: ai có chuỗi khóa hợp lệ thì có thể thực hiện những hành động mà khóa đó được cấp. Ví dụ một đối tác gọi API quản lý đơn hàng bằng header `X-API-Key` hoặc một integration gọi một endpoint nội bộ. Nếu bảng dữ liệu lưu nguyên văn API key, một lần lộ bản sao database có thể lập tức làm lộ **toàn bộ khóa đang hoạt động**. Khi cần xác thực request, server thường không cần biết bí mật gốc là gì; chỉ cần xác nhận giá trị client đưa đến có tương ứng với một credential đã phát hành và còn hiệu lực hay không.

Hai quyết định thiết kế quan trọng:

1. **Tách định danh khóa (`key_id`) khỏi phần bí mật (`secret`):** `key_id` phục vụ tra cứu, quản trị, audit, hiển thị và chỉ mục database. `secret` chỉ do client nắm giữ để chứng minh quyền sử dụng khóa.
2. **Lưu giá trị xác minh một chiều thay vì plaintext:** sinh secret có entropy cao, lưu hash/HMAC được tính từ secret, và so sánh lại khi client cung cấp credential. Chỉ hiển thị secret **một lần lúc phát hành**, không có chức năng “xem lại” bí mật đã băm.

Ví dụ cấu trúc khóa minh họa:

~~~text
ak_v1_m9u2Ujmt0V-2qGWl.3AF0eXlzh_8qd0C_g1LmdEX_sxfweTmO3t8yWgQ4d3M
|_____| |______________| |_________________________________________|
  prefix       key_id                 secret (ví dụ minh họa)

ak_v1_      = namespace/version format
key_id      = định danh công khai để tìm đúng bản ghi
secret      = chuỗi ngẫu nhiên, cần bảo vệ tuyệt đối
~~~

Đây chỉ là **cấu trúc minh họa**, không phải khóa thật. Trong thiết kế thực tế nên sinh **độc lập** `key_id` và `secret` từ bộ sinh số ngẫu nhiên mật mã. Ví dụ 12–16 byte cho ID công khai đủ tránh trùng khi có kiểm tra unique ở DB; phần secret có thể dùng **32 byte ngẫu nhiên (256 bit)**, mã hóa Base64url không padding để phù hợp header HTTP.

Với cấu trúc `ak_v1_<id>.<secret>`, server làm hai bước: lấy `id` để tìm một bản ghi; tính giá trị xác minh từ `secret` vừa được trình và so với giá trị lưu. **Không dùng `key_id` như bằng chứng xác thực** và không dùng đoạn prefix/4 ký tự cuối của secret để cấp quyền.

## 2. Định danh công khai và bí mật là hai thứ có vòng đời khác nhau

| Thành phần | Công khai? | Lưu vào database? | Vai trò |
|---|---|---|---|
| `key_id` | Có thể công khai | Có, có unique index | Tra cứu bản ghi khóa, thu hồi, báo cáo, rate-limit/audit theo khóa. |
| `secret` | Không | **Không** nếu chỉ cần đối chiếu | Bằng chứng để authenticate client. Chỉ trả cho client đúng một lần. |
| `secret_verifier` | Không nên công khai | Có | HMAC/hash một chiều để xác nhận secret khi trình lại. |
| `pepper_version` | Có thể là metadata | Có | Xác định khóa HMAC nào được dùng để tính verifier. |
| `owner_id` / `service_id` | Không phải credential | Có | Principal tài khoản/service mà key thuộc về. |
| `permissions` / `scopes` | Metadata nhạy cảm | Có, quản lý theo policy | Giới hạn quyền của key, không mã hóa tùy tiện trong secret. |
| `status`, `expires_at`, `revoked_at` | Metadata | Có | Khóa còn được chấp nhận hay không. |
| `created_at`, `last_used_at` | Metadata | Có | Quản trị, audit, phát hiện key không dùng lâu. |

**Tách ID khỏi bí mật không có nghĩa ID phải bí mật.** Một `key_id` bị lộ đơn lẻ không nên cho phép truy cập API. Tuy nhiên, tránh chứa trực tiếp email, tên khách hàng, tenant hoặc ID nội bộ có giá trị nhạy cảm trong `key_id`, vì nó có thể xuất hiện ở log, URL quản trị, screenshot hoặc hệ thống hỗ trợ khách hàng.

Nên chọn định danh ngẫu nhiên (hoặc mã định danh không tiết lộ thông tin), đủ tránh va chạm; DB áp dụng unique constraint và retry cấp ID mới nếu trùng. **Không tuần tự hóa ID theo cách làm lộ quy mô khách hàng** nếu không có yêu cầu rõ. `key_id` là identity của *credential*, khác với `owner_id` là identity của *người dùng/service*.

Một owner có thể có nhiều key độc lập để dễ phân loại ứng dụng và thu hồi riêng: `partner-a-integration`, `ci-pipeline`, `data-export`. Các nhãn hiển thị chỉ là metadata; không dùng nhãn làm secret.

## 3. Khi nào hash một chiều đủ, khi nào không đủ?

**Hash/HMAC một chiều phù hợp khi server chỉ cần làm phép so sánh:**

~~~text
Client trình API key  ──►  Server
                             |
                       parse key_id
                             |
                    lookup credential row
                             |
                      HMAC(secret) / hash
                             |
                   constant-time compare
                             |
                   owner + scope + status
                             |
                     allow hoặc deny
~~~

Không có bước giải mã secret gốc.

**Không phù hợp nếu server phải dùng lại secret để hành động:** ví dụ ứng dụng cần đọc một API key của nhà cung cấp bên thứ ba để gọi `https://vendor.example/api`; server phải có credential gốc để đặt vào Authorization header của request outbound. Nếu chỉ lưu hash, **không thể khôi phục secret**. Trường hợp này cần lưu secret **mã hóa có thể giải mã bằng KMS/secret manager với quyền truy cập tách biệt**, quản trị rotation và audit, hoặc dùng cơ chế delegation/OAuth để tránh lưu bearer secret dài hạn. Không lưu plaintext chỉ vì “cần dùng lại”.

Cũng cần phân biệt **API key bearer thông thường** với **khóa dùng ký mỗi request**. Với một số giao thức request-signing, client tạo chữ ký HMAC trên method/path/body/timestamp và server cần một bí mật chia sẻ (hoặc cơ chế xác minh khóa công khai). Hash không thể tự thay thế bí mật dùng tính HMAC cho message tùy ý. Nếu là chữ ký bất đối xứng, server có thể lưu public key để verify, khác với HMAC shared-secret.

| Nhu cầu | Cách lưu phù hợp | Vì sao |
|---|---|---|
| So khớp API key client đưa vào header | HMAC/hash một chiều của secret có entropy cao | Không cần lấy lại secret. |
| Dùng secret để gọi API nhà cung cấp khác | Encrypt at rest bằng KMS/secret manager; phân quyền đọc chặt | Phải lấy lại secret hợp lệ khi gọi outbound. |
| Kiểm tra chữ ký HMAC mỗi HTTP request | Quản trị shared secret có thể dùng tại verifier, hoặc giải pháp key-management tương ứng | Hash của API key không tự tính được chữ ký cho thông điệp mới. |
| Verify chữ ký bất đối xứng của client | Public key/certificate được tin + policy | Không cần private key client. |
| User tự chọn key ngắn, dễ đoán | Tránh thiết kế này; nếu bất khả kháng dùng password-KDF như Argon2id với chính sách phù hợp | Secret có entropy thấp cần chống đoán offline, không được dùng SHA-256 nhanh tùy tiện. |

**Tính một chiều của hash là đặc tính bảo vệ dữ liệu**, không phải bất tiện cần “đảo ngược” sau này. Khi client mất key chỉ có phương án **tạo key mới và thu hồi key cũ**, nếu thiết kế chỉ lưu verifier.

## 4. Entropy: điều kiện để SHA-256/HMAC dùng được an toàn cho API key

API key **do server tự sinh** nên có secret dài và ngẫu nhiên bằng CSPRNG. Trong Java sử dụng `java.security.SecureRandom`:

~~~java
byte[] randomBytes = new byte[32];      // 256 bit ngẫu nhiên
new java.security.SecureRandom().nextBytes(randomBytes);
String secret = java.util.Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(randomBytes);
~~~

Đoạn trên là **snippet minh họa**, không phải chương trình Java độc lập. 32 byte đầu vào được Base64url không padding thành **43 ký tự ASCII**. Không suy diễn rằng chuỗi dài 43 ký tự ngẫu nhiên về mặt mật mã chỉ vì có đủ độ dài: nguồn tạo ngẫu nhiên mới là điều kiện quan trọng. Không dùng timestamp, username, `UUID.nameUUIDFromBytes`, `Math.random()`, mã tăng dần hay biến đổi một mật khẩu dễ đoán làm secret.

Với key được sinh ngẫu nhiên đủ mạnh, **SHA-256 của secret** là một verifier một chiều có thể chấp nhận theo threat model: kẻ chỉ có DB khó thử toàn bộ không gian 256 bit. Tuy nhiên, nếu dùng `SHA-256(secret)` không key, người có DB có thể kiểm tra các secret bị lộ hoặc secret yếu bằng hash nhanh; họ cũng có thể thực hiện dò nếu quá trình phát hành thực tế kém ngẫu nhiên.

Một thiết kế thường hữu ích là lưu **HMAC-SHA-256 với một server-side pepper**:

~~~text
verifier = HMAC-SHA-256(pepper, "api-key:v1:" || secret)
                                      ▲
                               domain separation

Database: key_id, verifier, pepper_version, owner, permissions, status...
Secret manager/KMS: pepper v1, v2, ...    (KHÔNG nằm cùng DB)
Client: api_key có secret gốc
~~~

**Pepper** là một khóa bí mật độc lập khỏi DB, dùng cho HMAC. Không hard-code pepper trong source, không đưa vào browser/mobile app, và không lưu pepper trong cùng bảng chứa verifier. Nếu chỉ DB bị lộ, attacker thiếu pepper nên khó xác minh một secret đoán được với HMAC. Nhưng nếu cả DB lẫn pepper bị lộ, lớp bảo vệ này mất tác dụng; với secret ngẫu nhiên 256 bit, entropy vẫn là lớp bảo vệ chính.

**Salt** và **pepper** không đồng nghĩa:

- **Salt** là giá trị ngẫu nhiên riêng từng bản ghi, thường không bí mật; đặc biệt quan trọng cho password hashing có entropy thấp.
- **Pepper** là khóa bí mật của hệ thống, quản trị ngoài DB; HMAC dùng pepper để biến verifier thành giá trị có khóa.
- Với API key đủ ngẫu nhiên, không nhất thiết phải thêm salt cho mỗi bản ghi vì secret đã duy nhất theo xác suất rất cao; nếu yêu cầu compliance hoặc có thuật toán cụ thể, định nghĩa rõ phiên bản và metadata thay vì trộn lẫn tùy tiện.

**Không dùng Argon2id cho mọi bearer API key như quy tắc bắt buộc.** Password-KDF được thiết kế cho credential con người có entropy thấp; với secret 256 bit sinh bằng CSPRNG, HMAC/SHA-256 có chi phí thấp hơn và độ khó dò vẫn rất lớn. Tùy mô hình tấn công hoặc yêu cầu vận hành, có thể cân nhắc KDF chậm, nhưng phải kiểm soát tải xác thực. Nếu key do con người tự chọn, không được suy luận như secret 256 bit.

## 5. Cấu trúc database: tra cứu theo `key_id`, không quét hash toàn bảng

Mẫu bảng SQL minh họa:

~~~sql
CREATE TABLE api_key_credentials (
    key_id           VARCHAR(64) PRIMARY KEY,
    owner_id         VARCHAR(80) NOT NULL,
    tenant_id        VARCHAR(80) NOT NULL,
    secret_verifier  BYTEA NOT NULL,              -- 32 byte HMAC-SHA-256
    pepper_version   SMALLINT NOT NULL,
    status           VARCHAR(16) NOT NULL,       -- ACTIVE / REVOKED / ...
    created_at       TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ,
    last_used_at     TIMESTAMPTZ,
    label            VARCHAR(128)
);
CREATE INDEX idx_api_key_credentials_owner
    ON api_key_credentials(owner_id);
~~~

Đây là SQL kiểu **PostgreSQL** (ví dụ `BYTEA`, `TIMESTAMPTZ`), chưa gồm đầy đủ foreign key, permission table và check constraint. Trong hệ thống thực, lưu quyền key ở bảng có ràng buộc `key_id`/scope/tenant hoặc một mô hình policy đã được phê duyệt. Nếu cần unique giữa nhiều môi trường, định nghĩa namespace/issuer/tenant cùng DB schema phù hợp.

Luồng verify:

1. Lấy credential qua HTTPS từ **header đã được chỉ định** (ví dụ `X-API-Key`), kiểm tra số lượng header, kích thước và cú pháp. Không đưa key vào URL/query string vì dễ bị ghi log/cache/referrer.
2. Tách prefix, version, `key_id`, `secret`; **không để client điều khiển tên thuật toán HMAC/key của server** bằng một giá trị không được allowlist.
3. Query bằng `key_id` có unique index, lấy `secret_verifier`, `pepper_version`, trạng thái và owner. Nếu không tìm thấy key, từ chối và chỉ log key ID đã rút gọn nếu cần.
4. Lấy đúng pepper theo phiên bản từ secret manager; tự tính HMAC trên secret vừa được trình (cùng format và cùng domain separator lúc phát hành).
5. So sánh tag kích thước cố định bằng thao tác không dừng sớm theo byte, ví dụ `MessageDigest.isEqual` với các mảng HMAC cùng độ dài. Việc tra DB và kiểm tra trạng thái chưa chắc constant-time toàn luồng; cần hạn chế enumeration, rate limit và phản hồi lỗi thống nhất.
6. Chỉ khi MAC đúng, kiểm tra `status=ACTIVE`, `expires_at`, `revoked_at`, owner active, tenant và quyền truy cập endpoint; tạo Authentication và để authorization của ứng dụng xử lý.
7. Cập nhật `last_used_at`/audit theo một cơ chế có giới hạn hoặc bất đồng bộ để giảm write amplification, không log toàn bộ key.

**Không query bằng `WHERE secret = ?`** vì không lưu secret. **Không query theo toàn bộ API key được hash ngẫu nhiên** khi có ID công khai giúp lookup O(1)/index; một số biến thể vẫn có thể lookup bằng hash được đánh chỉ mục nhưng tách `key_id` giúp quản trị, rotation và log rõ ràng mà không lộ phần bí mật.

### Ví dụ schema của khóa được cấp

~~~json
{
  "key_id": "m9u2Ujmt0V-2qGWl",
  "owner_id": "service-partner-42",
  "tenant_id": "tenant-acme",
  "status": "ACTIVE",
  "pepper_version": 3,
  "permissions": ["ORDERS_READ", "ORDERS_CREATE"],
  "expires_at": "2027-01-01T00:00:00Z"
}
~~~

JSON này là metadata của **credential record**, **không phải API key client phải gửi**. Trường `secret_verifier` không nên xuất hiện trong API quản trị hoặc response cho client. Một endpoint quản lý có thể hiển thị `key_id`, tên, scopes, trạng thái và ngày hết hạn để user tự tìm/thu hồi key.

## 6. Ví dụ Java 17 đầy đủ: cấp key, HMAC và đối chiếu an toàn

Chương trình Java 17 dưới đây dùng **Java Standard Library**, không phụ thuộc Spring, chạy bằng `javac`/`java`. Nó sinh ID ngẫu nhiên và secret riêng biệt, tạo HMAC của secret, không in khóa gốc, rồi thử bốn điều kiện xác thực. **Mã dùng pepper mẫu ngẫu nhiên trong RAM cho demo; sản phẩm thật phải lấy pepper ổn định, được quản lý từ KMS/secret manager.**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class ApiKeyHashingDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL_ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final String PREFIX = "ak_v1_";

    record StoredKey(String id, byte[] verifier, boolean active) {}
    record IssuedKey(String presented, StoredKey stored) {}

    static String randomUrlText(int bytes) {
        byte[] random = new byte[bytes];
        RANDOM.nextBytes(random);
        return URL_ENCODER.encodeToString(random);
    }

    static byte[] hmacSha256(byte[] pepper, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            String input = "api-key:v1:" + secret;  // domain separation
            return mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    static IssuedKey issue(byte[] pepper) {
        String publicId = randomUrlText(12);
        String secret = randomUrlText(32); // 256 bit bí mật
        String presented = PREFIX + publicId + "." + secret;
        StoredKey stored = new StoredKey(
                publicId, hmacSha256(pepper, secret), true);
        return new IssuedKey(presented, stored);
    }

    static boolean verify(String presented, StoredKey record, byte[] pepper) {
        if (presented == null || record == null
                || presented.length() > 160) {
            return false;
        }
        int dot = presented.indexOf('.');
        if (dot < 0 || dot != presented.lastIndexOf('.')) {
            return false;
        }
        String first = presented.substring(0, dot);
        if (!first.equals(PREFIX + record.id())) {
            return false;
        }
        String secret = presented.substring(dot + 1);
        if (!secret.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }
        byte[] actual = hmacSha256(pepper, secret);
        return record.active()
                && MessageDigest.isEqual(record.verifier(), actual);
    }

    public static void main(String[] args) {
        byte[] pepper = new byte[32];
        RANDOM.nextBytes(pepper);

        IssuedKey issued = issue(pepper);
        String apiKey = issued.presented();
        StoredKey record = issued.stored();

        int secretStart = apiKey.indexOf('.') + 1;
        char original = apiKey.charAt(secretStart);
        char different = original == 'A' ? 'B' : 'A';

        String wrongSecret = apiKey.substring(0, secretStart)
                + different + apiKey.substring(secretStart + 1);
        String wrongId = PREFIX + "another-id."
                + apiKey.substring(secretStart);
        StoredKey disabled = new StoredKey(
                record.id(), record.verifier(), false);

        System.out.println("correct: " + verify(apiKey, record, pepper));
        System.out.println("wrong secret: "
                + verify(wrongSecret, record, pepper));
        System.out.println("wrong id: "
                + verify(wrongId, record, pepper));
        System.out.println("disabled: "
                + verify(apiKey, disabled, pepper));
    }
}
~~~

Lưu đúng tên `ApiKeyHashingDemo.java`, sau đó chạy:

~~~bash
javac ApiKeyHashingDemo.java
java ApiKeyHashingDemo
~~~

**Stdout chính xác**, dù chuỗi khóa ngẫu nhiên mỗi lần chạy:

~~~text
correct: true
wrong secret: false
wrong id: false
disabled: false
~~~

Giải thích:

- `SecureRandom` tạo hai chuỗi độc lập; `randomUrlText(32)` tạo secret 256 bit trước khi Base64url.
- `IssuedKey.presented` chỉ tồn tại như một kết quả phát hành tạm thời để đưa cho client; record `StoredKey` chỉ giữ ID, verifier và trạng thái.
- HMAC xử lý cùng chuỗi `api-key:v1:<secret>` trong cả khi tạo và khi kiểm tra. Nếu đổi format/thuật toán, cần gắn version và chiến lược migration; không thay âm thầm.
- `MessageDigest.isEqual` so sánh hai byte array của HMAC; với các tag có chiều dài chuẩn 32 byte, cách này tránh so sánh ký tự tuần tự dừng sớm. **Toàn bộ hàm `verify` không hứa thời gian hoàn toàn không đổi**, vì parse/lookup/validation có nhánh logic.
- `wrongSecret` giữ đúng độ dài và cú pháp nhưng thay một ký tự; HMAC khác nên bị từ chối. `wrongId` trượt bước tìm đúng record. `disabled` cho thấy cryptographic match cũng chưa đủ khi credential bị khóa.
- Ví dụ để dễ hiểu, mã lưu mảng byte trong record và tạo pepper RAM mỗi lần chạy. Trong production cần defensive copies/giới hạn lifetime bộ nhớ cho byte array, quản trị pepper ngoài process/DB, lưu record trong DB với uniqueness và kiểm soát lifecycle. Không in `apiKey` trong log hay trả qua endpoint tra cứu thông thường.

**Ranh giới ví dụ:** chương trình minh họa API key hashing/verification; không tạo HTTP server, Spring filter, phân quyền, truy cập DB, audit hay KMS. Các phần tiếp theo giải thích cách ghép đúng vào Spring Security.

## 7. Vì sao HMAC có “pepper” khác chữ ký HMAC của request?

Từ HMAC có thể gây nhầm hai mục đích:

1. **HMAC làm verifier khi lưu API key:** `HMAC(serverPepper, secretPresented)`. Server không cần lấy lại `secretPresented`; client gửi bearer key trực tiếp trong header. HMAC chỉ được tính tại server để đối chiếu một chiều với record.
2. **HMAC ký request:** client có một shared secret và ký chuỗi canonical của HTTP method, path, timestamp/body, v.v. Server phải có cách tính/xác minh chữ ký bằng shared secret phù hợp, đồng thời có nonce/timestamp/replay protection. Không thể chỉ có verifier của một bearer key rồi mong nó tính được chữ ký request bất kỳ.

Hashing secret để đối chiếu không biến API key thành token có khả năng chống replay. **Một API key bearer bị đánh cắp vẫn có thể được dùng cho đến khi bị thu hồi/hết hạn**, dù database chỉ lưu verifier. Do đó TLS, giới hạn quyền, rate limit, rotate và kiểm soát log vẫn rất quan trọng.

### HMAC so với hash password

Một API key do server sinh 256 bit ngẫu nhiên có entropy cao; không có danh sách từ điển hiệu quả để thử như mật khẩu người dùng. `SHA-256` nhanh có thể đủ trong một số threat model; `HMAC-SHA-256` với pepper ngoài DB bổ sung rào cản khi DB lộ. Nếu credential lại là từ do người dùng tự nghĩ hoặc PIN ngắn, phải coi nó là **mật khẩu entropy thấp**, dùng Argon2id/scrypt/bcrypt phù hợp thay vì viện dẫn “API key” để dùng hash nhanh. Cách tốt nhất là **không cho user chọn secret dễ đoán**.

### Pepper rotation khó ở đâu?

Một record có `pepper_version=v1`, chỉ lưu `HMAC(v1, secret)`. Khi tạo v2, server **không thể tính `HMAC(v2, secret)` từ `HMAC(v1, secret)`** mà không có secret gốc. Có hai hướng:

- **Rehash khi key được trình hợp lệ:** giữ v1 hoạt động tạm theo chính sách, verify với pepper v1, sau đó trong một transaction cập nhật verifier sang v2 dựa trên secret vừa được client trình. Giới hạn phiên bản, concurrency và thời gian chuyển tiếp.
- **Yêu cầu phát hành khóa mới:** khi nghi ngờ v1 bị lộ hoặc cần bỏ v1 hoàn toàn, bắt buộc client thay key; thu hồi record cũ theo deadline.

Không xóa pepper cũ trước khi xử lý những key chưa được rehash, trừ khi chủ đích là vô hiệu hóa chúng. Nếu mất pepper mà chỉ còn verifier trong DB, không thể verify key cũ; phải khôi phục pepper từ cơ chế backup an toàn hoặc reissue credential. Pepper phải có version, secret-manager ACL, backup và quy trình khôi phục/rollout được kiểm soát.

## 8. Quy trình phát hành và trả API key một lần

1. Client có quyền tạo khóa ở API quản trị (đã xác thực bằng cơ chế phù hợp, yêu cầu MFA/step-up nếu key nhạy cảm) gửi request tạo key với label, scopes tối thiểu và expiry.
2. Server kiểm tra **ai có quyền phát hành** cho tenant/service đó; không cho requester tự chọn owner/role không được phép.
3. Tạo `key_id` và `secret` bằng CSPRNG, độc lập nhau. Định dạng version cho phép kiểm soát migration.
4. Tính `HMAC(pepperVersion, secret)`; lưu bản ghi có unique ID, owner, permissions, created/expiry/status trong transaction. **Không lưu secret gốc, kể cả tạm trong DB.**
5. Trả **full key một lần** trong HTTPS response tới caller đã được xác thực. Màn hình cần cảnh báo không hiển thị lại và yêu cầu người nhận cất vào secret manager; không đưa vào email, analytics, error reporting, browser history hoặc console log.
6. Sau response, ứng dụng chỉ cho xem metadata và một phần ID/label; khi mất key, tạo key mới và thu hồi key cũ.

Ví dụ response **minh họa cấu trúc, không phải credential thực**:

~~~json
{
  "key_id": "m9u2Ujmt0V-2qGWl",
  "api_key": "ak_v1_<public-id>.<secret-shown-once>",
  "label": "Partner order sync",
  "permissions": ["ORDERS_READ"],
  "expires_at": "2027-01-01T00:00:00Z",
  "warning": "Store this value securely; it will not be shown again."
}
~~~

**Chú ý:** cú pháp `<...>` ở đây là **ký hiệu chỗ điền giá trị trong ví dụ JSON**, không phải key hợp lệ để gửi request. Trong API thật, response chỉ có `api_key` khi tạo mới; các endpoint GET list/detail **không bao giờ** trả lại full key hoặc secret verifier. Client ứng dụng mobile/browser công khai thường không phù hợp để lưu API key tĩnh dài hạn vì khóa có thể bị trích xuất; cân nhắc OAuth2/PKCE hoặc mô hình token ngắn hạn.

## 9. Request đi qua Spring Security như thế nào?

Trong ứng dụng **Spring Boot 3.x + Spring Security 6.x (Servlet)**, có thể dùng một `OncePerRequestFilter` cho đường API key. Các bước logic:

~~~text
HTTP request /partner-api/orders
      |
      v
TLS (HTTPS) + gateway request policy
      |
      v
Spring Security FilterChain
      |
      +-- Lấy X-API-Key từ header (chặn trùng/sai format)
      +-- Parse: format version + key_id + secret
      +-- ApiKeyVerifier tra DB theo key_id
      +-- HMAC(server pepper, secret) + MessageDigest.isEqual
      +-- Kiểm tra ACTIVE, expiry, revocation, owner/tenant
      +-- Tạo Authentication(principal=owner, authorities=permissions)
      |
      v
Authorization: hasAuthority("ORDERS_READ"), tenant/resource policy
      |
      v
Controller/service
~~~

**Authentication** trả lời “key này chứng minh danh tính của integration/owner nào?”. **Authorization** trả lời “integration này có được phép truy cập tài nguyên cụ thể không?”. Đừng tạo một principal `ROLE_ADMIN` cho mọi API key hợp lệ.

Một số lưu ý Spring Security:

- `X-API-Key` là một header tự định nghĩa; gateway có thể có quy ước `Authorization: ApiKey ...`. Chọn một cách nhất quán, xử lý duplicated/combined headers và giới hạn độ dài.
- Tách parsing/crypto/repository vào service độc lập, filter chỉ điều phối và cập nhật `SecurityContext`.
- Với filter tự triển khai, dùng `HttpSecurity.addFilterAfter(filter, LogoutFilter.class)` hoặc vị trí auth thích hợp theo thứ tự filter chain. Authentication phải được thiết lập **trước `AuthorizationFilter`**. Tránh đăng ký cùng một filter vừa như servlet filter tự động vừa trong Spring Security, vì có thể chạy hai lần/sai thứ tự.
- Chỉ áp dụng chain API key cho path cần thiết bằng `securityMatcher("/partner-api/**")`; nếu cùng ứng dụng còn browser login/OIDC, dùng chain khác đúng phạm vi và thứ tự.
- Nếu API thuần header và không dựa trên cookie/session, cấu hình `SessionCreationPolicy.STATELESS`. Cân nhắc vô hiệu hóa CSRF **chỉ cho chain API thuần stateless không có credential browser tự gửi**, không tắt cho toàn website có form/cookie.
- Trả **401 Unauthorized** khi thiếu/sai credential và **403 Forbidden** khi credential hợp lệ nhưng thiếu quyền, thông thường không tiết lộ key_id có tồn tại hay không. Nếu filter tự trả lỗi, phải chủ động xử lý 401 vì lỗi phát sinh trước `ExceptionTranslationFilter` có thể không được dịch thành HTTP response như mong đợi.

### Ví dụ cấu hình Spring Security

Đoạn sau là **mã tích hợp trong ứng dụng**, giả định bạn có `ApiKeyVerifier`, `ApiKeyFilter` và mapping principal đúng. Đây không phải chương trình `javac` độc lập:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;

@Configuration
public class ApiKeySecurityConfig {

    @Bean
    SecurityFilterChain apiKeyChain(HttpSecurity http,
                                    ApiKeyVerifier verifier) throws Exception {
        http
            .securityMatcher("/partner-api/**")
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/partner-api/orders/create")
                    .hasAuthority("ORDERS_CREATE")
                .requestMatchers("/partner-api/orders/**")
                    .hasAuthority("ORDERS_READ")
                .anyRequest().authenticated())
            .addFilterAfter(new ApiKeyFilter(verifier), LogoutFilter.class);
        return http.build();
    }
}
~~~

Cấu hình trên **giả định API key là cơ chế authentication duy nhất của chain `/partner-api/**`** và không có cơ chế fallback trái policy. Ở ứng dụng nhiều `SecurityFilterChain`, cần đặt thứ tự match và catch-all chain rõ ràng; nếu không có chain phù hợp cho endpoint khác, có thể gây lỗ hổng. `ApiKeyFilter` phải tự trả lỗi thiếu/sai khóa hoặc để entry point xử lý, bảo đảm không cho qua endpoint chỉ vì header vắng mặt.

### Phác thảo filter sử dụng một verifier có kiểm soát

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Collections;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {
    private final ApiKeyVerifier verifier;

    public ApiKeyFilter(ApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest req,
            HttpServletResponse res, FilterChain chain)
            throws ServletException, IOException {

        var headers = Collections.list(req.getHeaders("X-API-Key"));
        if (headers.size() != 1 || headers.get(0).isBlank()) {
            res.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        ApiKeyIdentity identity = verifier.authenticate(headers.get(0));
        if (identity == null) {
            res.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var authentication = new PreAuthenticatedAuthenticationToken(
            identity, null, identity.authorities());

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(req, res);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Giả định các hợp đồng do ứng dụng cài đặt:

~~~java
// Hợp đồng minh họa, cần triển khai thực tế:
public interface ApiKeyVerifier {
    // Trả null khi thiếu record, sai HMAC, revoked, expired,
    // owner disabled hoặc sai tenant; giới hạn thời gian/tải DB.
    ApiKeyIdentity authenticate(String presentedApiKey);
}

// Principal có ID khóa, owner, tenant và GrantedAuthority chính xác.
// Đây là ký hiệu hợp đồng, không phải class hoàn chỉnh có thể biên dịch riêng.
public interface ApiKeyIdentity {
    java.util.Collection<? extends
        org.springframework.security.core.GrantedAuthority> authorities();
}
~~~

**Không paste tất cả block Java này vào một file rồi mong biên dịch độc lập.** Các phần này mô tả cách bố trí lớp `ApiKeyFilter.java`, `ApiKeyVerifier.java` và `ApiKeyIdentity.java` cùng Spring Security 6.x. Ví dụ `ApiKeyFilter` xử lý thiếu/invalid header bằng `401`, xác lập authentication sau khi verifier đã kiểm tra mọi điều kiện, rồi dọn context. Với request bất đồng bộ hoặc cần dispatch khác, phải áp dụng cơ chế truyền security context phù hợp. Khi có header nhiều giá trị, proxy phải xử lý consistently; có thể chặn dấu phẩy/giá trị bất thường theo quy định format thực tế.

Các phương thức của Spring `AuthenticationManager`/`AuthenticationProvider` cũng là lựa chọn phù hợp cho triển khai lớn, vì cho phép thống nhất success/failure, account status và audit. Không bắt buộc thiết kế một hệ thống bảo mật riêng nếu framework đã có contract thích hợp.

## 10. Trình tự kiểm tra và ý nghĩa 401/403

Một verifier đúng phải có thứ tự hợp lý:

1. **Input limits:** nhận đúng header, một giá trị, giới hạn độ dài và ký tự hợp lệ. Chặn key gửi qua query parameter nếu contract cấm.
2. **Public lookup:** parse và query `key_id` trong DB bằng prepared statement/JPA repository; hạn chế lỗi phân biệt key không tồn tại và key sai secret.
3. **Cryptographic proof:** xác minh secret qua HMAC theo pepper version, so sánh byte array không dừng sớm.
4. **Credential lifecycle:** active, chưa hết hạn, chưa bị revoke, chưa vượt chính sách; owner/service account active.
5. **Internal authorization:** xác định tenant/scopes, có thể thêm IP allowlist, certificate-bound policy hoặc quota; kiểm tra resource cụ thể.
6. **Result:** tạo Authentication có principal/authorities, hoặc từ chối thống nhất.

| Tình huống | Kết quả HTTP thường phù hợp | Điều gì cần kiểm tra? |
|---|---|---|
| Thiếu `X-API-Key` trên endpoint bắt buộc | **401** | Không fallback vô tình sang Anonymous hoặc cookie. |
| `key_id` không tồn tại | **401** | Không cho client biết “ID tồn tại”. |
| ID đúng, secret sai | **401** | HMAC mismatch; audit/rate limit. |
| Key đã revoked/expired | **401** | Không còn credential hợp lệ; không dùng cached Authentication cũ. |
| Key hợp lệ, thiếu quyền `ORDERS_CREATE` | **403** | Authentication đúng nhưng authorization không đủ. |
| Key hợp lệ, sai tenant/resource | **403** hoặc phản hồi không tiết lộ tài nguyên theo policy | Không dựa vào tenant header do client gửi. |
| Database/pepper manager không sẵn sàng | **503** hoặc lỗi tạm theo chính sách fail closed | Không biến lỗi hạ tầng thành key được phép. |
| Request quá lớn hoặc sai cú pháp | **400/401/413/431** tùy API/gateway | Giới hạn parsing để tránh DoS. |

Mã HTTP là lựa chọn theo hợp đồng API. Điều bắt buộc là **không cấp quyền** khi verification/lifecycle thất bại; không nhất thiết mọi lỗi phải trả cùng một mã nếu hệ thống có lý do vận hành hợp lệ. Thông báo public nên tránh khác biệt “key_id đúng nhưng secret sai” giúp attacker dò key.

## 11. Rotation, thu hồi và quản trị nhiều khóa

**Rotation một API key không nên chỉ thay verifier trong DB** vì client đang giữ secret cũ sẽ không tự biết secret mới. Quy trình phổ biến:

1. Issue key mới có `key_id` và secret mới, gắn cùng owner nhưng có quyền theo policy và thời hạn riêng.
2. Trả secret mới **một lần** và yêu cầu client lưu vào secret manager, cập nhật cấu hình/deployment.
3. Cho phép **hai key song song** trong một khoảng chuyển tiếp ngắn có kiểm soát (nếu rủi ro chấp nhận), theo dõi `last_used_at`/audit.
4. Khi client xác nhận đang dùng key mới, revoke key cũ; nếu key cũ bị nghi lộ thì **revoke ngay**, không tiếp tục overlap.
5. Kiểm tra API không còn chấp nhận key cũ; giữ metadata/audit cần thiết theo retention, loại bỏ verifier khi không còn cần.

Các key thuộc cùng owner **không chia sẻ secret**. Key theo tích hợp, môi trường và scope riêng cho phép thu hồi granular và giới hạn blast radius. Khi thu hồi key hoặc khóa owner, các cache verifier/permission phải có **TTL, invalidation và consistency** theo yêu cầu. Nếu dùng nhiều instance, thay đổi trong DB phải được áp dụng đến các instance trong thời gian cho phép.

**Không nên copy API key production sang staging/dev.** Mỗi môi trường có namespace/trust domain, secret manager và quota riêng. Một prefix như `ak_live_` hay `ak_test_` giúp nhận biết môi trường nhưng **không phải biện pháp mật mã**.

## 12. Tổ chức secrets và chống lộ khóa

API key có thể lộ qua nhiều đường ngoài database:

- **Log HTTP:** reverse proxy, ingress, APM/tracing, error reporting, servlet logging hoặc debug tools có thể thu header. Định nghĩa redaction cụ thể cho `X-API-Key` và `Authorization`, bao gồm cả request dump.
- **URL/query:** key trong URL có thể xuất hiện ở access log, browser history, reverse proxy cache, referrer; ưu tiên header qua HTTPS.
- **Repository/CI:** không hard-code key vào Java, YAML, shell script, Dockerfile, GitHub Actions logs hay tài liệu. Secret scanning/detection và quy trình revoke khi bị lộ là bắt buộc cho môi trường sản phẩm.
- **Environment/containers:** secret trong env var có thể bị lộ qua process inspection/crash/log; dùng secret manager/file mount phù hợp quyền và platform, không assume env là vault hoàn hảo.
- **Người dùng:** khóa cấp một lần, không gửi qua email/chat công khai, không dán lên ticket/screenshot, chỉ đưa ID rút gọn vào hỗ trợ kỹ thuật.
- **Client/browser:** ứng dụng không tin cậy (SPA/mobile binary phát hành công khai) không thể giữ API key tĩnh dùng chung như bí mật lâu dài. Nên xem xét OAuth2/PKCE và token ngắn hạn.
- **TLS/gateway:** luôn dùng HTTPS; gateway không tự được phép bypass xác thực/ủy quyền vì TLS thành công.

Có thể cho phép log `key_id` hoặc prefix công khai để điều tra, nhưng cần đánh giá thông tin định danh/tenant được lộ và chống enumeration. Một giá trị “last 4” hiển thị từ secret chỉ là tiện ích nhận diện, **không phải dữ liệu dùng để xác thực**.

## 13. Thiết kế lưu key cho hệ thống nhiều tenant và nhiều dịch vụ

Trong môi trường multi-tenant:

~~~text
Client API key
   |
   +-- parse key_id
   +-- lookup exactly one key row
   +-- verify secret HMAC
   +-- obtain trusted key.tenant_id + owner_id + permissions
   |
   +-- request tries to access /tenant/{tenant}/orders
            |
            +-- compare requested resource tenant against authenticated tenant
            +-- evaluate permission and object-level policy
            +-- allow/deny
~~~

**Không lấy tenant từ header `X-Tenant-Id` do client gửi rồi coi là tenant đã xác thực.** Header có thể giúp client chọn ngữ cảnh, nhưng hệ thống phải so sánh với tenant/ủy quyền xác định từ verified credential. Mỗi API key chỉ được cấp quyền cụ thể theo owner/tenant. Nếu service account hỗ trợ nhiều tenant, cần mô hình delegation/allowlist riêng.

Với việc cấp quyền, tránh role quá rộng `ROLE_ADMIN` cho mọi key nội bộ. Ví dụ:

~~~text
key_id = abc123
owner  = integration_partner_42
tenant = tenant_acme
authorities:
   - ORDERS_READ
   - ORDERS_CREATE
quota:
   - 200 requests/minute
expiry:
   - 2027-01-01T00:00:00Z
~~~

Đây là metadata minh họa, không phải credential bí mật. Quyền trong DB là **nguồn dữ liệu chính sách**, còn khả năng sử dụng chúng phụ thuộc credential đã được HMAC verify và trạng thái còn hợp lệ.

## 14. Các lỗi phổ biến khi hash API key

| Lỗi | Tại sao nguy hiểm | Cách sửa |
|---|---|---|
| Lưu nguyên chuỗi `ak_v1_id.secret` | DB leak cho phép replay trực tiếp tất cả key | Chỉ lưu ID + verifier một chiều + metadata. |
| Chỉ lưu `secret` nhưng không có ID | Khó tra cứu/quản trị/thu hồi và audit chính xác | Thêm ID công khai ngẫu nhiên, unique index. |
| Dùng `Math.random()` hoặc timestamp | Secret đoán được/entropy thấp | Sinh bằng `SecureRandom` và đủ byte ngẫu nhiên. |
| Dùng SHA-256 nhanh cho key do người dùng tự chọn | Key yếu có thể bị brute force khi lộ hash | Sinh key ngẫu nhiên; với mật khẩu thấp entropy dùng password-KDF. |
| Tính HMAC nhưng cất pepper ngay trong DB | Mất lớp bảo vệ khi DB leak | Quản trị pepper ngoài DB với version/rotation. |
| So sánh secret bằng `String.equals`/so sánh từng ký tự | Có thể tạo timing side-channel theo vị trí lệch | So sánh **digest/tag fixed-length** bằng `MessageDigest.isEqual` hoặc primitive đáng tin. |
| Cho phép tra key bằng `key_id` rồi coi là authenticated | ID công khai không phải bằng chứng sở hữu secret | Bắt buộc verify secret và lifecycle. |
| Hiển thị lại key từ endpoint GET | Tăng rủi ro lộ credential | One-time reveal; key mất thì reissue. |
| Trộn key id với owner ID | Khó rotate key, lộ thông tin và lẫn phân quyền | Credential ID riêng; owner/tenant là metadata. |
| Parse key không giới hạn độ dài | DoS parser/DB và log flooding | Max length, whitelist alphabet, chặn header trùng. |
| Chọn tenant/scopes hoàn toàn theo request | Cross-tenant privilege escalation | Quyền lấy từ record của credential đã verify. |
| Revoked key vẫn được chấp nhận từ cache | Thu hồi không có hiệu lực | TTL/invalidation và recheck theo SLA. |
| Mọi lỗi authentication cho phép fallback sang session cookie | Downgrade/bypass ranh giới API key | SecurityFilterChain riêng với chính sách explicit. |
| Pepper rotate bằng cách HMAC lại giá trị HMAC cũ | Không tương đương HMAC với secret gốc; key cũ hỏng | Rehash trên secret được trình lại hoặc reissue. |
| Dùng `Base64` như phương pháp bảo mật | Base64 chỉ mã hóa biểu diễn, không bảo vệ bí mật | Dùng hash/HMAC/HTTPS đúng mục đích. |

## 15. Kiểm thử đúng điều cần chứng minh

Không chỉ kiểm tra “API trả 200 khi có key”; phải test hết các ranh giới:

| Test | Kỳ vọng |
|---|---|
| Tạo key thành công | Trả full key một lần; DB chỉ có ID/verifier/metadata. |
| Tra danh sách/detail key | Không xuất hiện secret hay secret verifier. |
| Key đúng ID + secret | HMAC match, owner/principal và authorities đúng. |
| Đúng ID, sai một ký tự secret nhưng vẫn đúng format | 401, không cấp quyền. |
| ID không tồn tại, secret nhìn hợp lệ | 401, không tiết lộ sự khác biệt ID đúng/sai. |
| Chỉ gửi ID, bỏ secret | Từ chối ở bước parse. |
| Key yếu hoặc quá ngắn, ký tự ngoài bảng mã | Từ chối, không thử rộng/normalize không rõ ràng. |
| Hai bản ghi khác ID dùng cùng owner | Key còn lại hoạt động khi thu hồi một key. |
| Key đã expired hoặc revoked | 401 ngay/đúng chính sách cache. |
| Owner disabled dù key vẫn active | Từ chối xác thực. |
| Đúng key nhưng thiếu `ORDERS_CREATE` | 403 trên endpoint tạo đơn, endpoint read vẫn theo quyền. |
| Key hợp lệ tenant A gọi resource tenant B | Từ chối theo tenant policy. |
| Pepper v1 và v2 được rollout | Verify đúng theo version; không dùng nhầm pepper. |
| Xóa pepper v1 khi còn key v1 | Phải có kế hoạch rehash/reissue; không tự cấp quyền. |
| DB/KMS lỗi | Fail closed, không “cho qua tạm” request. |
| Header trùng hoặc kết hợp bất thường | Từ chối theo canonical parsing policy. |
| Log/tracing/counter | Không chứa plaintext key. |
| Rotating key | Key mới được cấp, key cũ bị revoke đúng SLA. |
| Replay một bearer API key bị đánh cắp | Thực tế vẫn có thể authenticate trước khi revoke; cần TLS, phát hiện bất thường, thu hồi nhanh. |

**Test thời gian so sánh:** kiểm tra rằng code dùng digest fixed-length + primitive thích hợp; benchmark bên ngoài không đủ để khẳng định toàn HTTP path constant-time vì DB/cache/network luôn biến thiên. Không dựa vào “thử đo thấy giống nhau” để chứng minh an toàn tuyệt đối.

**Test Java demo:** kết quả `correct: true`, `wrong secret: false`, `wrong id: false`, `disabled: false` là ổn định dù ID/secret ngẫu nhiên. Khi tích hợp Spring, có thể dùng MockMvc để kiểm tra 401/403 và integration test với DB/secret manager giả lập để kiểm tra rotation, concurrency, không log key.

## 16. Tình huống thực tế: đối tác đồng bộ đơn hàng

Một đối tác được cấp key chỉ có quyền `ORDERS_READ` và `ORDERS_CREATE` trong tenant A. Khi đối tác gọi:

~~~http
POST /partner-api/orders/create HTTP/1.1
Host: api.company.example
X-API-Key: ak_v1_<public-id>.<secret>
Content-Type: application/json

{"externalOrderId": "EXT-2026-001"}
~~~

Request là **minh họa**, chuỗi chứa `<...>` không phải credential thật. Gateway/app nên thực hiện:

1. HTTPS và giới hạn request/header; không cho người ngoài xem secret ở log.
2. Parse `key_id`, lookup đúng record, HMAC secret và so sánh digest an toàn.
3. Chỉ cho phép nếu key còn ACTIVE, owner/tenant hợp lệ, có authority `ORDERS_CREATE`, quota chưa vượt và request đáp ứng validation.
4. Lưu `externalOrderId` theo ràng buộc idempotency/domain, thực thi rule nghiệp vụ trong service. API key không thay thế toàn bộ validation giao dịch.
5. Audit mã credential/owner và kết quả, không audit toàn bộ bearer key.
6. Khi nghi bị lộ, quản trị viên revoke đúng key và cấp key mới; không cần sửa toàn bộ tài khoản đối tác.

Nếu đối tác gọi `/partner-api/orders/delete-all`, dù key hợp lệ, request phải bị từ chối nếu thiếu authority tương ứng. Việc bảo vệ key trong DB là **bảo vệ credential lúc lưu**; quyền và giới hạn nghiệp vụ là lớp kiểm soát độc lập.

## 17. Checklist triển khai production

Trước khi đưa vào vận hành, xác nhận:

1. **Key generation:** secret ≥ 128 bit entropy thực, ưu tiên 256 bit CSPRNG; ID ngẫu nhiên độc lập, unique; format có version.
2. **At-rest verifier:** HMAC-SHA-256 với pepper quản trị ngoài DB (hoặc hash phù hợp threat model), không có plaintext, không expose verifier.
3. **Transport:** HTTPS bắt buộc; key chỉ trong header/cơ chế được phê duyệt, không trong URL/log.
4. **Lookup/compare:** parse chặt chẽ, query bằng key ID, HMAC cùng canonical input/version, `MessageDigest.isEqual` trên digest cố định.
5. **Principal/authority:** owner, tenant, scopes lấy từ record đã verify; không tạo admin mặc định.
6. **Lifecycle:** expiry, revoke, rotation overlap có giới hạn, cache invalidation, khóa owner và kiểm soát chủ thể tạo khóa.
7. **Pepper management:** KMS/secret manager, version, backup, migrate/reissue và cơ chế xử lý mất pepper.
8. **Monitoring:** audit key ID chứ không secret, rate limit/phát hiện abuse, last-used, anomaly alerts.
9. **Integration:** Spring Security filter đúng chain/order, stateless API policy rõ, không duplicate registration, 401/403 đúng.
10. **Incident response:** quy trình revoke khẩn, rà soát log/backups/CI và thông báo chủ khóa khi nghi lộ.

## 18. Kết luận

Khi server **chỉ cần đối chiếu** một API key từ client, cách thiết kế dễ quản trị và giảm thiểu thiệt hại là:

~~~text
public key_id + strong random secret (issued once)
             |
       store key_id + HMAC(secret) + owner/scopes/status
             |
    client presents key over HTTPS
             |
      lookup by key_id
             |
   HMAC + constant-time digest comparison
             |
    validate lifecycle and authorizations
~~~

**Tách `key_id` khỏi `secret`** giúp tìm đúng bản ghi và thu hồi từng credential mà không cần lộ bí mật. **Băm/HMAC một chiều** giúp hạn chế nguy cơ replay ngay từ bản sao database; bí mật server-side pepper bổ sung lớp bảo vệ nếu được quản lý tách biệt. Dù vậy, API key vẫn là bearer credential: bảo vệ đường truyền, hạn chế quyền, quản trị vòng đời và theo dõi lạm dụng là bắt buộc.

## Tài liệu tham khảo

- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ, phát hành, xoay vòng và audit secrets.
- [OWASP — Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): bảo vệ keys/peppers bằng hệ thống quản trị bí mật và lifecycle.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): CSPRNG, thuật toán mật mã và key management.
- [Spring Security — Servlet Architecture / Adding Custom Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html): thứ tự filter, `HttpSecurity.addFilterAfter` và cách tích hợp filter tự viết.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, authorization và filter chain.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): bộ sinh số ngẫu nhiên mật mã.
- [Java 17 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)): so sánh digest/tag.
- [Java 17 — Mac HmacSHA256](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HMAC theo JCA.
- [RFC 4648](https://www.rfc-editor.org/rfc/rfc4648): Base64 và Base64url encoding.
