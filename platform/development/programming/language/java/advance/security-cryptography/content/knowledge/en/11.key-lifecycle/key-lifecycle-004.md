# 11.4 Mã định danh khóa, phiên bản khóa và khả năng giải mã dữ liệu cũ

Khi một hệ thống Java mã hóa dữ liệu để lưu nhiều tháng hoặc nhiều năm, câu hỏi không chỉ là **“mã hóa bằng AES-GCM thế nào?”** mà còn là **“sau khi đổi khóa, làm sao xác định đúng khóa cũ để đọc bản mã đã lưu?”**. Nếu chỉ giữ một biến `CURRENT_KEY` và thay byte khóa mỗi lần triển khai, những ciphertext cũ thường **không thể giải mã** bằng khóa mới. Thêm một bản sao key mới không tự chuyển đổi được dữ liệu cũ.

Giải pháp cần một hợp đồng bền vững gồm **mã định danh khóa (key ID)**, **phiên bản/vòng đời khóa (key version)**, **phiên bản định dạng bản mã (envelope/format version)** và chính sách **giữ khả năng giải mã dữ liệu cũ (backward decryption)**. Hệ thống có thể dùng một khóa mới cho dữ liệu phát sinh, đồng thời duy trì quyền giải mã hạn chế cho bản ghi cũ cho đến khi chúng được chuyển đổi, hết hạn hoặc bị hủy theo chính sách.

Điều cốt lõi: **key ID là tham chiếu tới khóa, không phải khóa**; **số phiên bản không tự sinh ra khóa cũ**; và **giải mã bằng khóa đúng nhưng bỏ qua kiểm tra toàn vẹn/phân quyền vẫn không an toàn**. Bài này xây dựng tư duy quản lý khóa dài hạn trong Java, dùng AES-GCM như ví dụ cụ thể và có chương trình Java 17+ kiểm chứng quá trình rotation, giữ khóa cũ, re-encrypt và xử lý dữ liệu bị sửa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `keyId`, `keyVersion`, `formatVersion`, phiên bản dữ liệu nghiệp vụ và thuật toán mã hóa.
2. Thiết kế bản mã/envelope có đủ metadata để chọn đúng khóa về sau: định dạng, key ID, nonce, ciphertext, tag và ngữ cảnh xác thực.
3. Mô tả trạng thái **active-for-encryption**, **decrypt-only**, **disabled/revoked** và **destroyed**, không nhầm “không dùng mã hóa mới” với “không được giải mã nữa”.
4. Tạo chính sách “encrypt bằng phiên bản hiện hành, decrypt theo phiên bản gắn trên bản mã” mà không thử ngẫu nhiên tất cả khóa.
5. Hiểu cách dùng AES-GCM và `updateAAD` để ràng buộc thông tin header/key ID, chỉ sử dụng plaintext sau khi xác thực tag thành công.
6. So sánh rotation không chuyển dữ liệu, **lazy migration**, **batch re-encryption**, **rewrap DEK/KEK** và các giới hạn của mỗi cách.
7. Xây quy trình rollout, rollback, backup/restore, audit và thu hồi khóa mà không đánh mất dữ liệu ngoài ý muốn.
8. Viết test về khả năng đọc bản cũ, data migration, thiếu khóa, đổi key ID, sửa ciphertext/tag, đổi AAD và tính độc lập của từng tenant.

## 2. Khái niệm: key ID khác key bytes và key version

Giả sử một dịch vụ lưu tài liệu:

```text
Document A (2025)  -- encrypted with --> key version 1001
Document B (2026)  -- encrypted with --> key version 1002

Key registry:
  1001 -> Key material #1, status DECRYPT_ONLY
  1002 -> Key material #2, status ACTIVE
```

Khi đọc A, hệ thống lấy thông tin `keyId=1001` được lưu bên cạnh hoặc bên trong bản mã, tra đúng khóa #1 đã được cho phép và xác thực dữ liệu. Khi tạo C, hệ thống dùng khóa #2 và ghi `keyId=1002`. Không có lý do để bắt A phải giải mã bằng key #2 chỉ vì “đã đổi key hiện hành”.

| Thuật ngữ | Ý nghĩa | Ví dụ | Điều không được suy ra |
| --- | --- | --- | --- |
| **Key material** | Giá trị khóa bí mật thực sự, có thể nằm trong KMS/HSM | 32 byte khóa AES-256, key handle | Không thể tính lại từ key ID đơn thuần |
| **Key ID** | Định danh để tìm đúng khóa hoặc key reference | `document-prod/1002`, opaque UUID, số 1002 | Không phải secret; không tự chứng minh key đáng tin |
| **Key version** | Thế hệ/version của vật liệu khóa hoặc phiên bản trong một key resource | `v1`, `v2` hoặc provider key version | Không đồng nghĩa version định dạng ciphertext |
| **Active key** | Phiên bản được policy chọn để **mã hóa mới** | `1002` | Không có nghĩa mọi dữ liệu cũ đã dùng key 1002 |
| **Decrypt-only key** | Không dùng để mã hóa mới, vẫn có quyền giải mã dữ liệu hợp lệ trong phạm vi cho phép | `1001` | Không phải “key đã bị xóa” |
| **Envelope format version** | Phiên bản cấu trúc header/nonce/tag/serialization | `formatVersion=1` | Không phải tuổi/phiên bản khóa |
| **Algorithm/profile** | Thuật toán và tham số được phép | `AES/GCM/NoPadding`, nonce 12 byte, tag 128 bit | Không để request tự chọn thuật toán yếu hơn |
| **Data/schema version** | Cách hiểu plaintext nghiệp vụ | `documentSchema=4` | Không gắn trực tiếp với key rotation |
| **KEK / DEK** | Key-encryption key và data-encryption key trong envelope encryption | KEK tại KMS, DEK per object | Không tự động có rewrap nếu dùng một key mã hóa trực tiếp |

Một tên `keyId` có thể đã chứa version, hoặc hệ thống có thể lưu `keyAlias` + `keyVersion` thành hai trường. **Không bắt buộc tách thành hai field**, nhưng cần một tham chiếu **duy nhất và bất biến tới phiên bản vật liệu khóa**. Nếu alias “current” đổi sang phiên bản mới, bản mã cũ không thể chỉ lưu alias biến động rồi bỏ version.

### Tránh ba loại “v1” trùng nhau

Ví dụ một record có:

```json
{
  "envelopeVersion": 2,
  "keyId": "documents/production",
  "keyVersion": "7",
  "documentSchemaVersion": 4
}
```

Đây là **JSON mô tả metadata**, không phải format binary của chương trình ở mục 7. Giá trị `envelopeVersion=2` cho biết cách parse package; `keyVersion=7` là thế hệ key; `documentSchemaVersion=4` quyết định deserialize plaintext. Ba phiên bản có thể thay đổi **độc lập**. Đừng dùng cùng một field `version` cho cả ba mà không ghi rõ ý nghĩa.

### Key ID có cần bí mật không?

Thông thường **không**. Key ID là định danh hoặc tham chiếu, có thể hiện diện ở header của ciphertext. Tuy nhiên nó vẫn có thể tiết lộ tên hệ thống/tenant nếu dùng tên dễ đoán; dùng opaque identifier khi cần hạn chế lộ metadata. Dù công khai, **không bao giờ đưa raw key bytes, password hoặc secret token vào header**.

ID được đọc từ bản mã chưa xác thực chỉ là **dữ liệu do input cung cấp**. Nó có thể giúp route tới key đã nằm trong allowlist, nhưng không được dùng làm quyết định quyền: attacker không thể được quyền giải mã key của tenant khác chỉ bằng cách thay header.

## 3. Mô hình vòng đời khóa và quyền thao tác

Một hệ thống lưu trữ dài hạn thường cần tách quyền **encrypt mới** khỏi quyền **decrypt cũ**. Bảng trạng thái minh họa:

| Trạng thái | Encrypt dữ liệu mới | Decrypt dữ liệu cũ | Quyết định vận hành |
| --- | --- | --- | --- |
| `PENDING` / `STAGED` | Chưa | Thường chưa | Phân phối key, cấu hình, kiểm thử mà chưa activate |
| `ACTIVE` | **Có** | **Có** | Key hiện hành; kiểm nonce uniqueness và giới hạn sử dụng |
| `DECRYPT_ONLY` | **Không** | **Có**, có điều kiện | Cho phép đọc bản mã cũ trong giai đoạn retention/migration |
| `SUSPENDED` / `DISABLED` | Không | Không trong thời gian khóa | Đóng tạm hoặc thu hồi quyền truy cập theo chính sách |
| `RETIRED` / `DESTROYED` | Không | Không; key đã mất có thể không thể khôi phục | Chỉ sau khi đã quyết định dữ liệu phụ thuộc không cần đọc nữa, hoặc đã migrate |

Tên trạng thái ở bảng là **ví dụ policy ứng dụng**, không phải tên bắt buộc của API Java hay mọi KMS. Một nhà cung cấp có thể có các trạng thái và chế độ rotation khác nhau. Đặc biệt **`DECRYPT_ONLY` phải được thực thi bằng quyền/logic thực tế**, không chỉ ghi một cột trạng thái rồi vẫn để mọi service gọi encrypt bằng khóa cũ.

Luồng rotation bình thường:

```text
giai đoạn 1:
   v1 ACTIVE -> vừa encrypt vừa decrypt

giai đoạn 2:
   v1 DECRYPT_ONLY
   v2 ACTIVE -> mọi ciphertext mới ghi keyVersion=v2

giai đoạn 3 (nếu cần):
   decrypt + authenticate record v1
   encrypt lại bằng v2 và nonce mới
   commit record v2 an toàn

giai đoạn 4:
   kiểm hết live objects, backups, snapshots, jobs, DR copies theo policy
   -> có thể disable/destroy v1 nếu không còn phụ thuộc và retention cho phép
```

Trường hợp **key bị nghi lộ** khác planned rotation. Việc giữ key cũ để decrypt có thể tiếp tục tạo rủi ro nếu kẻ tấn công cũng có key. Phải ưu tiên containment, chặn quyền không hợp lệ, đánh giá dữ liệu đã lộ, re-encrypt theo mức khẩn cấp, rotate dependencies và xử lý theo quy trình incident response. **Re-encrypt bây giờ không thể thu hồi plaintext mà attacker có thể đã đọc trong quá khứ**.

## 4. Vì sao ciphertext phải có key reference bất biến?

Ví dụ lỗi thường gặp:

```text
2025: encrypt(payload, System.getenv("APP_ENCRYPTION_KEY")) -> lưu nonce+ciphertext+tag
2026: thay APP_ENCRYPTION_KEY bằng giá trị khác, không lưu key ID/version
2027: gọi decrypt trên record 2025 với key mới -> tag thất bại
```

Trong AES-GCM, giải mã bằng sai key thường thất bại ở bước xác thực tag; ứng dụng không thể đoán key cũ từ ciphertext. Nếu key cũ không còn ở bất kỳ kho bảo mật/backup hợp lệ nào, **dữ liệu có thể mất vĩnh viễn**.

Mô hình đúng:

```text
record = {
  formatVersion,
  immutableKeyReference,  <-- đúng phiên bản vật liệu khóa
  nonce,
  ciphertext,
  authenticationTag
}

decrypt(record):
   parse+validate formatVersion
   resolve key via trusted key registry and authorization
   verify AEAD with nonce, ciphertext, tag and AAD
   only then interpret plaintext
```

**Không lưu key reference mơ hồ** như `keyId="current"` nếu tên đó sẽ trỏ sang key bytes khác sau rotation. Nếu provider dùng alias chuyển tiếp, cần lưu **version cụ thể** hoặc đủ metadata từ cryptographic service để provider tìm đúng phiên bản lịch sử mà không dựa vào alias hiện tại. Một số KMS quản lý version trong ciphertext nội bộ; không suy ra đó là tính năng phổ quát, cần kiểm contract API.

### Key registry cần đảm bảo điều gì?

Một registry/kho key thích hợp trả lời được:

- `keyRef` này thuộc **environment** nào (prod/staging), tenant/trust domain nào, ứng dụng và mục đích nào?
- Nó dùng thuật toán nào, có còn **decrypt permission** không, và key material có còn khả dụng không?
- Nó có phải **tham chiếu bất biến** tới key generation cần thiết không?
- Caller đã được xác thực và được cấp quyền trên **record cụ thể** chưa?
- Nếu key bị disabled/destroyed/expired, hệ thống từ chối như thế nào và phản hồi/log ra sao?
- Khi key rotation, có thể audit key version của mỗi record và đếm được record còn phụ thuộc vào key cũ không?

Key ID chỉ là **lookup key**. **Không** cho request chỉ định một path đến secret file hoặc một key URI tùy ý rồi sử dụng trực tiếp. Key registry cần allowlist và kiểm quyền server-side, tránh cross-tenant decryption và key-enumeration abuse.

## 5. Đóng gói key ID và version trong authenticated envelope

Để dễ minh họa, bài dùng một binary envelope **demo v1** cho AES-256-GCM:

```text
offset   length   field                      meaning
0        4        magic "KVR1"               marker định dạng
4        1        formatVersion = 1          phiên bản envelope
5        4        keyId (int32 big-endian)   1001 hoặc 1002 trong ví dụ
9        12       nonce                      IV/nonce GCM, sinh mới mỗi lần
21       N        ciphertext                ciphertext của N byte plaintext
21+N     16       authentication tag         tag GCM, 128 bit

header = magic || formatVersion || keyId || nonce
envelope = header || ciphertext || tag
```

Mỗi record dùng nonce 12 byte mới, tag 16 byte. `ByteBuffer` của Java mặc định **big-endian**, và spec phải cố định thứ tự byte. Đây là **định dạng do bài học định nghĩa**, không phải tiêu chuẩn tương thích tự động với mọi dịch vụ. Không dùng y nguyên cho sản xuất nếu chưa có security review, KMS integration, nonce allocation policy, giới hạn size và lộ trình migration.

Điểm quan trọng là **header phải được authenticated**. Bên encrypt đưa chính byte header vào **AAD** của AES-GCM. Bên decrypt dùng lại chính byte header. Nếu ai đó đổi `keyId=1001` thành `1002` mà không có key và khả năng tạo tag hợp lệ, phép kiểm GCM phải thất bại. Ngay cả khi hai ID vô tình cùng trỏ tới cùng vật liệu khóa, việc đổi byte header đã được AAD ràng buộc sẽ làm tag thất bại.

Ví dụ profile v1:

```text
AAD = fixedDomain || headerBytes || uint32be(contextBytes.length) || contextBytes

fixedDomain = ASCII "document-envelope:v1"
contextBytes = ngữ cảnh đã được ứng dụng xác thực và serialize nhất quán
```

`fixedDomain` giúp phân tách mục đích sử dụng. `headerBytes` ràng buộc format, key ID và nonce. `contextBytes` có thể ràng buộc document/tenant vào ciphertext. **Dữ liệu AAD không được mã hóa**, nhưng được xác thực khi tag thành công; bên giải mã phải có đúng những byte đó.

Bài demo dùng một chuỗi context cố định `tenant-7/document-42` như opaque identifier. Với nhiều trường tùy ý từ user, không được nối text tùy tiện như `tenant + "/" + document` nếu các giá trị có thể chứa dấu phân cách. Cần **canonical framing từng field** (length-prefix, schema/version, charset UTF-8, null/empty) hoặc một serialization chuẩn đã được thỏa thuận.

**Quyền kiểm tra trước, tag kiểm sau:** header parse từ record chưa đáng tin; cần kiểm format, size, key namespace và authorization theo identity/resource đã được server xác lập **trước** khi lấy key. AEAD tag thành công mới chứng minh tính toàn vẹn ciphertext/AAD. Dù tag hợp lệ, vẫn phải kiểm quy tắc nghiệp vụ và chống replay/rollback khi cần.

## 6. Quy trình ghi và đọc trong hệ thống nhiều phiên bản

### 6.1 Ghi record mới

```text
1. Xác thực caller, tenant, quyền ghi và loại dữ liệu.
2. Chọn activeKeyRef từ cấu hình/trusted key registry của service.
3. Sinh nonce/IV đúng chính sách, độc nhất đối với cùng AES-GCM key.
4. Encode header chứa formatVersion, immutable key reference, nonce.
5. Canonicalize AAD từ metadata/ngữ cảnh đáng tin; cập nhật AAD.
6. Encrypt plaintext bằng AES-GCM -> ciphertext || tag.
7. Lưu toàn bộ envelope và metadata cần khôi phục AAD.
8. Ghi audit kỹ thuật (record ID, key version, result) không lộ secret.
```

**Không** nhận `activeKeyId` do client tùy ý yêu cầu; encrypt key phải do policy server chọn. Khi rollout, phân phối key mới và quyền truy cập cho các instance trước khi chuyển active pointer, tránh node cũ không giải mã được record vừa xuất hiện.

### 6.2 Đọc record cũ

```text
1. Xác thực caller, quyền đọc đúng record/tenant.
2. Nhận envelope có bounded length và kiểm version/profile.
3. Parse key ID như một untrusted routing hint.
4. Kiểm key ID thuộc allowed key namespace, không lấy key tùy ý.
5. Resolve đúng key material/version; nếu không còn thì fail closed.
6. Init AES-GCM bằng nonce; cung cấp authenticated header và context AAD.
7. Decrypt + xác minh toàn bộ tag trong doFinal.
8. Chỉ sau thành công mới trả plaintext, parse schema, thực thi nghiệp vụ.
```

**Không** vòng lặp “thử lần lượt v2, v1, v0 cho đến khi có text đọc được”. Cách thử brute-force keys làm lỗi vận hành mơ hồ, tăng attack surface, latency và có thể sinh decryption oracle. Thiết kế có key reference rõ ràng giúp **chọn chính xác một phiên bản được policy cho phép**.

Nếu record thiếu key ID (định dạng legacy), cần **migration path được xác định rõ theo nguồn/giai đoạn**, không coi đoán toàn bộ keyring là thiết kế dài hạn. Có thể có một đầu vào legacy-version-specific và key riêng phục vụ migration trong cửa sổ kiểm soát, nhưng phải giới hạn và tắt khi hoàn tất.

### 6.3 Tách nhận dạng key và xác minh AEAD

Key ID trên wire **không phải bằng chứng authentication**. Attacker có thể sửa key ID và làm tăng số yêu cầu KMS nếu service cho phép ID bất kỳ. Vì vậy:

- Chỉ chấp nhận format/version/ID nằm trong scope được cấu hình.
- Không dùng key ID trong input thay quyền kiểm tra tenant/resource dựa trên dữ liệu tin cậy.
- Không tiết lộ nguyên nhân chi tiết cho caller kiểu “key 1001 của tenant A có tồn tại hay không”.
- Đưa byte header vào AAD để ngăn tráo metadata không được xác thực.
- Coi `AEADBadTagException` / `GeneralSecurityException` là thất bại: không trả plaintext một phần, không fallback sang mode không xác thực.
- Với file lớn hoặc stream, không publish bất kỳ plaintext nào trước khi tag được xác minh; xem phần 11.

## 7. Ví dụ Java 17+ chạy được: rotation không làm mất dữ liệu cũ

Ví dụ dưới đây dùng:

- AES-256-GCM, IV ngẫu nhiên 12 byte, tag 128 bit.
- Một **keyring trong RAM** mô phỏng key registry: `1001` là v1, `1002` là v2.
- Record nhị phân có `formatVersion=1` khác với `keyId=1001/1002`.
- Header và context nằm trong AAD; mọi byte ciphertext/tag đều được xác thực trong `Cipher.doFinal`.
- Sau rotation, cả v1 và v2 còn trong keyring, nên **cả dữ liệu cũ và mới** đọc được. Khi migrate một record sang v2 rồi bỏ v1 khỏi map, record được migrate vẫn đọc được; record legacy v1 không còn đọc được.

**Khóa trong demo được sinh lại khi chạy**, không phải cấu hình lưu trữ thực. Chương trình chỉ mô phỏng retention của key trong một lần chạy. Ở hệ thống thật, key phải tồn tại và được quản lý bền vững trong KMS/HSM/keystore theo policy; không lưu key chỉ trong một `static Map` rồi kỳ vọng giải mã dữ liệu sau khi service restart.

Lưu thành file **`KeyVersionDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyVersionDemo {
    private static final int MAGIC = 0x4b565231; // KVR1
    private static final byte FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = 4 + 1 + 4 + NONCE_BYTES;
    private static final int MAX_RECORD_BYTES = 1_000_000;
    private static final byte[] DOMAIN =
            "document-envelope:v1".getBytes(StandardCharsets.US_ASCII);
    private static final SecureRandom RNG = new SecureRandom();

    private static SecretKey keyFor(Map<Integer, SecretKey> keys, int id)
            throws GeneralSecurityException {
        SecretKey result = keys.get(id);
        if (result == null) {
            throw new GeneralSecurityException("Key unavailable");
        }
        return result;
    }

    private static void setAad(Cipher cipher, byte[] header, byte[] context) {
        cipher.updateAAD(DOMAIN);
        cipher.updateAAD(header);
        cipher.updateAAD(ByteBuffer.allocate(4 + context.length)
                .putInt(context.length).put(context).array());
    }

    static byte[] encrypt(Map<Integer, SecretKey> keys, int activeKeyId,
                          byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        if (plaintext == null || context == null
                || plaintext.length > MAX_RECORD_BYTES - HEADER_BYTES - TAG_BYTES) {
            throw new GeneralSecurityException("Invalid input");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        byte[] header = ByteBuffer.allocate(HEADER_BYTES)
                .putInt(MAGIC).put(FORMAT_VERSION).putInt(activeKeyId)
                .put(nonce).array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, keyFor(keys, activeKeyId),
                new GCMParameterSpec(TAG_BITS, nonce));
        setAad(cipher, header, context);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(HEADER_BYTES + ciphertextAndTag.length)
                .put(header).put(ciphertextAndTag).array();
    }

    static byte[] decrypt(Map<Integer, SecretKey> keys, byte[] record,
                          byte[] context) throws GeneralSecurityException {
        if (record == null || context == null
                || record.length < HEADER_BYTES + TAG_BYTES
                || record.length > MAX_RECORD_BYTES) {
            throw new GeneralSecurityException("Invalid record length");
        }
        ByteBuffer input = ByteBuffer.wrap(record);
        if (input.getInt() != MAGIC || input.get() != FORMAT_VERSION) {
            throw new GeneralSecurityException("Unsupported format");
        }
        int keyId = input.getInt();
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);
        SecretKey key = keyFor(keys, keyId);

        byte[] header = Arrays.copyOfRange(record, 0, HEADER_BYTES);
        byte[] ciphertextAndTag = Arrays.copyOfRange(
                record, HEADER_BYTES, record.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        setAad(cipher, header, context);
        return cipher.doFinal(ciphertextAndTag);
    }

    static int recordKeyId(byte[] record) {
        return ByteBuffer.wrap(record, 5, 4).getInt();
    }

    @FunctionalInterface
    interface Attempt { void run() throws GeneralSecurityException; }

    static boolean rejected(Attempt attempt) {
        try {
            attempt.run();
            return false;
        } catch (GeneralSecurityException ex) {
            return true;
        }
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        Map<Integer, SecretKey> keyring = new HashMap<>();
        keyring.put(1001, generator.generateKey());
        keyring.put(1002, generator.generateKey());

        byte[] context = "tenant-7/document-42".getBytes(StandardCharsets.UTF_8);
        byte[] payload = "Archive data".getBytes(StandardCharsets.UTF_8);
        byte[] oldRecord = encrypt(keyring, 1001, payload, context);
        byte[] newRecord = encrypt(keyring, 1002, payload, context);

        byte[] tamperedId = oldRecord.clone();
        ByteBuffer.wrap(tamperedId, 5, 4).putInt(1002);
        byte[] tamperedData = oldRecord.clone();
        tamperedData[HEADER_BYTES] ^= 1;
        byte[] tamperedTag = oldRecord.clone();
        tamperedTag[tamperedTag.length - 1] ^= 1;

        byte[] migratedRecord =
                encrypt(keyring, 1002, decrypt(keyring, oldRecord, context), context);
        Map<Integer, SecretKey> newOnly = Map.of(1002, keyring.get(1002));

        System.out.println("Old record key ID: " + recordKeyId(oldRecord));
        System.out.println("New record key ID: " + recordKeyId(newRecord));
        System.out.println("Old readable after rotation: " +
                Arrays.equals(payload, decrypt(keyring, oldRecord, context)));
        System.out.println("New readable: " +
                Arrays.equals(payload, decrypt(keyring, newRecord, context)));
        System.out.println("Tampered key ID rejected: " +
                rejected(() -> decrypt(keyring, tamperedId, context)));
        System.out.println("Wrong context rejected: " +
                rejected(() -> decrypt(keyring, oldRecord,
                        "tenant-8/document-42".getBytes(StandardCharsets.UTF_8))));
        System.out.println("Modified ciphertext rejected: " +
                rejected(() -> decrypt(keyring, tamperedData, context)));
        System.out.println("Modified tag rejected: " +
                rejected(() -> decrypt(keyring, tamperedTag, context)));
        System.out.println("Migrated record key ID: " + recordKeyId(migratedRecord));
        System.out.println("Migrated plaintext preserved: " +
                Arrays.equals(payload, decrypt(newOnly, migratedRecord, context)));
        System.out.println("Old key unavailable blocks legacy record: " +
                rejected(() -> decrypt(newOnly, oldRecord, context)));
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 KeyVersionDemo.java
java KeyVersionDemo
```

**Stdout chính xác** (không in key/nonce/ciphertext ngẫu nhiên):

```text
Old record key ID: 1001
New record key ID: 1002
Old readable after rotation: true
New readable: true
Tampered key ID rejected: true
Wrong context rejected: true
Modified ciphertext rejected: true
Modified tag rejected: true
Migrated record key ID: 1002
Migrated plaintext preserved: true
Old key unavailable blocks legacy record: true
```

### 7.1 Giải thích luồng và bảo đảm thực sự

- `generator.generateKey()` tạo hai khóa AES khác nhau cho bản demo. Production phải có key registry/KMS bảo toàn vật liệu khóa và trạng thái version qua restart.
- `encrypt(..., 1001, ...)` ghi v1, `encrypt(..., 1002, ...)` ghi v2. **Format version đều bằng 1**; chỉ key generation khác nhau.
- `setAad` ràng buộc domain, header và length-prefixed context. Sửa `keyId` từ 1001 sang 1002 khiến service chọn key v2, nhưng không thể xác thực tag do key/AAD không phù hợp.
- `decrypt` kiểm kích thước, magic và format trước khi lấy key. Nó **chỉ return byte[] sau `Cipher.doFinal` thành công**, không publish plaintext chưa xác thực.
- Mã hóa lại `migratedRecord` **giải mã v1 đã xác thực rồi mã hóa lại bằng v2 và nonce mới**. Không chỉ cập nhật header key ID.
- Map `newOnly` mô phỏng v1 không còn sẵn cho caller. Record v1 bị từ chối, record đã migrate giải mã được. **Đây là mô phỏng thiếu khóa**, không phải thao tác KMS destroy hay xóa khóa thật.
- `recordKeyId` chỉ được dùng trong `main` với dữ liệu do chính chương trình sinh. Hàm này **không phải parser an toàn cho input bất kỳ** vì giả sử record đủ dài và đúng cấu trúc; code `decrypt` mới có kiểm tra tối thiểu.
- `rejected` bắt `GeneralSecurityException` để minh họa các lỗi parse/key/AEAD. Hệ sản xuất cần xử lý lỗi và audit rõ ràng, không phân biệt quá chi tiết cho client không tin cậy.
- Nonce ngẫu nhiên không được coi là cam kết toán học rằng **không bao giờ** trùng. Ứng dụng có tải lớn/nhiều node cần chính sách nonce uniqueness và giới hạn số lần mã hóa với cùng key, theo quy tắc AES-GCM.

### 7.2 Điều chương trình không khẳng định

Chương trình mô phỏng hai key với một map cục bộ; nó **không** dạy lưu private secret trong source code, không hỗ trợ persistence giữa hai lần chạy, không triển khai PKCS#11/KMS/HSM hoặc database migration, không có đa tenant isolation thực tế, không giải quyết khả năng mất key trong backup. Khi triển khai thật, phải thay `Map<Integer, SecretKey>` bằng bộ giải quyết key được xác thực/cấp quyền theo policy, thường là KMS/HSM hoặc keystore, và dùng immutable key version reference.

## 8. Những chiến lược rotation và bảo toàn dữ liệu cũ

Rotation không chỉ có một cách. Chọn tùy khối lượng, SLA, lưu trữ, compliance và mức độ rủi ro.

| Chiến lược | Dữ liệu cũ có phải đổi ngay? | Khóa cũ cần sẵn sàng decrypt? | Khi nào phù hợp? |
| --- | --- | --- | --- |
| **New-writes-only rotation** | Không | **Có** trong thời gian giữ bản mã v1 | Muốn đổi key ghi mới nhanh, volume cũ lớn |
| **Lazy re-encryption** | Đổi khi record được đọc/cập nhật | Có, cho đến khi toàn bộ records cũ được migrate/hết hạn | Trải tải migration, nhưng cần xử lý record ít truy cập |
| **Batch re-encryption** | Có, theo job có kiểm soát | Có trong suốt migration và rollback window | Muốn giảm phụ thuộc vào key cũ một cách chủ động |
| **Rewrap DEK bằng KEK mới** | Có thể **không** cần re-encrypt bulk payload | Cần key/KEK cũ đủ lâu để unwrap, trước khi rewrap hoàn tất | Hệ thống envelope encryption lưu wrapped DEK |
| **Xóa/hủy key cũ** | Không tự chuyển dữ liệu | **Không thể** decrypt bằng key đã mất | Crypto-shredding khi policy chấp nhận mất khả năng đọc |

### 8.1 New-writes-only: dễ triển khai nhưng kéo dài phụ thuộc

Thay active version `v1 -> v2` trong service. Mọi ciphertext mới chứa v2, nhưng tất cả ciphertext v1 vẫn tồn tại. Ưu điểm là rollout nhanh; nhược điểm là phải bảo vệ và giữ key v1 **miễn là còn dữ liệu hoặc backup cần giải mã**. Chính sách `DECRYPT_ONLY` hữu ích để tránh sản sinh thêm phụ thuộc vào v1.

Nếu giữ key 10 năm vì một object không bao giờ đọc, hệ thống có rủi ro vận hành và chi phí giữ khóa kéo dài. Cần inventory theo key version để ra quyết định có migrate hoặc cho hết hạn dữ liệu đó.

### 8.2 Lazy migration: đọc v1, ghi lại v2

Luồng:

```text
get(record v1)
   -> decrypt/authenticate with v1
   -> verify caller rights and business state
   -> re-encrypt with active v2 (fresh nonce, correct AAD)
   -> atomic compare-and-swap update if original version unchanged
   -> serve plaintext only after successful verification
```

Ưu điểm: tải migration dàn theo lưu lượng đọc. Rủi ro: record hiếm khi đọc không bao giờ tự chuyển; record bị cập nhật song song có thể bị overwrite nếu thiếu optimistic locking; migration không được làm ảnh hưởng latency hoặc vô tình phát event nghiệp vụ.

**Không** coi lazy migration là hoàn tất trước khi có báo cáo key-version inventory xác thực và kế hoạch cho những record chưa được truy cập.

### 8.3 Batch migration: phải idempotent và quan sát được

Một job migration tốt:

1. Snapshot/đọc **đúng record version** và metadata AAD cũ.
2. Lấy key v1 có quyền decrypt; `doFinal` phải xác thực thành công.
3. Mã hóa plaintext bằng key v2, IV mới và AAD/context theo policy mới.
4. Lưu ciphertext mới + key ID mới + nonce/tag + version/schema trong **một transaction hoặc atomic object replacement**.
5. Chỉ cập nhật checkpoint sau khi commit; nếu lỗi, bản v1 vẫn còn nguyên.
6. Đọc kiểm một phần hoặc toàn bộ records theo mức độ rủi ro; lưu metrics số lượng v1/v2 và lỗi.
7. Retry theo phiên bản ban đầu và optimistic lock; tránh mất cập nhật đồng thời.
8. Chỉ disable/delete v1 sau khi toàn bộ live data và backups/DR/archives phụ thuộc đã được đánh giá.

Nếu job bị ngắt giữa chừng, nó phải có thể chạy lại **không** biến record đã migrate thành bản không thể đọc. Với re-encryption, mỗi lần thử thành công tạo ciphertext mới vì nonce mới; nếu retry chưa commit, kết quả cũ chưa được coi là nguồn chính. Không lấy `keyId` trong request để quyết định key mà không đối chiếu registry/tenant đã tin cậy.

### 8.4 Rewrap: chỉ có khi kiến trúc tách DEK và KEK

**Envelope encryption** thường tạo một **DEK** để mã hóa nội dung và một **KEK** (thường do KMS giữ) để wrap/unwrap DEK:

```text
plaintext --encrypt with DEK--> ciphertext + tag
DEK ------wrap with KEK v1--> wrappedDEK-v1

record = ciphertext + nonce + tag + wrappedDEK + KEK reference + metadata
```

Khi thay KEK v1 bằng KEK v2:

```text
unwrap wrappedDEK-v1 using KEK v1 (có quyền)
   -> rewrap the same DEK with KEK v2
   -> update wrappedDEK + KEK reference atomically
   -> bulk ciphertext có thể giữ nguyên vì DEK không đổi
```

**Khác với re-encrypt:** nếu thay **DEK**, phải mã hóa lại nội dung bằng DEK mới và nonce/tag thích hợp. Nếu chỉ thay **KEK** theo cơ chế wrapping được hỗ trợ, ciphertext của dữ liệu có thể không đổi. Tuy nhiên:

- Phải giữ metadata/AD binding đúng, kiểm cơ chế key wrapping có integrity và quyền trước khi dùng DEK.
- Nếu ciphertext AAD trực tiếp ràng buộc KEK version/wrapped DEK metadata, chỉ rewrap có thể khiến tag cũ không khớp; format phải được thiết kế có chủ đích để hỗ trợ rewrap hoặc phải re-encrypt theo contract.
- KMS có thể hỗ trợ rotate/re-encrypt key hierarchy theo cách riêng; không giả định “đổi key alias” tự động chuyển bất kỳ record nào.
- Rewrap không giải quyết dữ liệu đã bị lộ do DEK/KEK cũ bị compromise trong thời gian trước đó; cần threat-model và incident response.

## 9. Ràng buộc metadata: đừng cho key ID mở đường đổi tenant

Một header có key ID là **untrusted input** cho đến khi phép xác thực mật mã thành công. Với SaaS đa tenant:

```text
Request identity -> trusted tenant & document permissions
                      |
                      v
Read object by trusted resource ID
                      |
                      v
Parse key reference (untrusted hint)
                      |
                      v
Check key reference belongs to allowed tenant/namespace
                      |
                      v
Decrypt + authenticate header/ciphertext/AAD
                      |
                      v
Validate plaintext schema and business authorization
```

Không cho user lấy ciphertext từ tenant A, sửa key ID thành một ID của tenant B, rồi buộc service gọi KMS với quyền tenant B. Kể cả tag sẽ thất bại, hành vi đó có thể tạo key-access side effects, tiết lộ tồn tại key hoặc vượt scope IAM nếu registry không kiểm.

Cần cân nhắc:

- KMS permission per workload/tenant, chặn cross-tenant key use từ identity tin cậy.
- AAD chứa tenant/document/usage theo một serialization không nhập nhằng.
- Record ID/version trong dữ liệu xác thực nếu cần chống tráo object.
- Domain separation giữa các mục đích mã hóa (document, token, backup), thay vì dùng một key không phân biệt.
- Kiểm key ID có đúng **loại thuật toán, mục đích và vùng** trước khi dùng; không chấp nhận bất kỳ ID format nào do attacker đặt.
- Tag hợp lệ không tự thay thế RBAC/ABAC; chỉ đảm bảo integrity cho byte đã được đưa vào phạm vi AEAD.

### “Rollback” khác “tampering”

GCM có thể chứng minh một ciphertext và AAD là hợp lệ dưới key đã chọn, **nhưng không tự chứng minh ciphertext đó là phiên bản mới nhất**. Một attacker có quyền thay object trong storage có thể phục hồi nguyên ciphertext/tag cũ mà vẫn hợp lệ, nếu ứng dụng không gắn một nguồn **trusted monotonic version** hoặc state kiểm rollback.

Nếu nghiệp vụ cần chống phục hồi phiên bản cũ (ví dụ số dư, quyền truy cập, thứ tự sự kiện), nên có object version/sequence/state được lưu trong DB tin cậy hay một cơ chế chống rollback có kiểm soát. Đưa objectVersion vào AAD chỉ hữu ích nếu giá trị phiên bản kỳ vọng được lấy từ nguồn **không thể bị rollback cùng ciphertext**.

## 10. Metadata cần lưu để giải mã sau nhiều năm

Một bản mã phải tự đủ dữ liệu công khai hoặc có khả năng truy ra chúng qua metadata bền vững để thực hiện:

1. Chọn parser đúng `formatVersion` và crypto profile.
2. Tìm **immutable key ID/version** hoặc wrapped DEK + KEK reference.
3. Lấy nonce và tag đúng độ dài.
4. Khôi phục **chính xác byte AAD** theo cùng policy/version đã dùng khi encrypt.
5. Đưa ciphertext vào AEAD đúng trình tự, chỉ lấy plaintext khi tag hợp lệ.
6. Biết cách deserialize plaintext theo schema version phù hợp.
7. Kiểm phân quyền trên record và mục đích sử dụng.

Ví dụ mô hình dữ liệu khái niệm (không phải schema bắt buộc):

```text
EncryptedObject {
    objectId: UUID
    tenantId: trusted identifier
    objectRevision: integer
    formatVersion: integer
    cryptoProfile: allowlisted identifier
    immutableKeyRef: opaque string
    nonce: byte[]
    ciphertextAndTag: byte[]
    aadSchemaVersion: integer
    schemaVersion: integer
    state: LIVE | MIGRATING | ARCHIVED | DELETED
}
```

Nếu key reference nằm trong **header AAD**, không được update riêng trong database mà bỏ qua việc tái tạo tag. Nếu metadata AAD nằm ngoài ciphertext, cần bảo đảm việc đọc lại nguyên giá trị và cách serialize không thay đổi sau migration. Đừng để thư viện JSON khác phiên bản sửa thứ tự field hoặc Unicode normalization rồi làm tag fail. Với dữ liệu dài hạn, nên lưu byte AAD đã xác thực hoặc một versioned canonical representation đủ để tái tạo 100%.

**Tag và IV không phải bí mật**, nhưng không được bỏ hoặc chỉnh sửa. **Key bytes phải bảo vệ riêng**, không đưa vào record hay log. Nếu dùng wrapped DEK, wrapped blob không phải plaintext key và vẫn cần bảo vệ thông tin truy cập, integrity và metadata theo thiết kế.

## 11. An toàn khi decrypt: chỉ đưa plaintext ra ngoài sau khi tag đúng

Khi dùng Java `Cipher` với `AES/GCM/NoPadding`:

```java
// Minh họa trong method đã có SecretKey key, byte[] nonce,
// byte[] authenticatedHeader, byte[] trustedContext và byte[] ciphertextAndTag.
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
cipher.updateAAD(authenticatedHeader);
cipher.updateAAD(trustedContext);
byte[] plaintext = cipher.doFinal(ciphertextAndTag);
```

Đoạn trên **không độc lập**; AAD và format cụ thể phải giống phía mã hóa. `doFinal` thất bại khi tag sai có thể ném `AEADBadTagException` (một dạng `BadPaddingException`) hoặc lỗi tương ứng; ứng dụng **không được trả byte được giải mã một phần** trong catch branch.

Một số provider/mode streaming có thể cho `Cipher.update` trả output **trước khi tag cuối được kiểm**. Tuyệt đối không ghi những byte đó vào HTTP response, event bus, database, log, cache hoặc file mà component khác có thể đọc. Nếu cần xử lý file rất lớn, cân nhắc staging được cô lập và atomic publish sau xác thực, hoặc định dạng **record-based AEAD** có tag cho từng record và commitment về thứ tự/EOF/truncation; không lấy một ví dụ in-memory rồi kéo dài tùy tiện để stream plaintext chưa xác thực.

**Lưu ý `CipherInputStream`:** tài liệu Java cảnh báo class này có thể bắt một số exception kiểm tra integrity, ví dụ `BadPaddingException`, và không tái ném. Nó **có thể không thích hợp** khi ứng dụng bắt buộc biết đầy đủ lỗi xác thực. Cần đánh giá API streaming được dùng và kiểm thử end-to-end việc không phát plaintext khi tag sai.

### Đơn vị độ dài

`new GCMParameterSpec(128, nonce)` dùng **128 bit tag**, tức **16 byte**. IV demo 12 byte. Metadata phải ghi rõ đơn vị và thuật toán. Đừng giả định mọi provider/giao thức đặt tag ở cùng vị trí; profile Java demo dùng `ciphertext || tag` từ `Cipher.doFinal`.

## 12. Kiểm soát nonce uniqueness qua nhiều thế hệ khóa

Đối với AES-GCM, **không được tái sử dụng cùng nonce với cùng key**. Rotation tạo key mới có thể giúp tách phạm vi nonce, nhưng **không** cho phép thiết kế nonce tùy tiện hoặc bỏ qua collision risk. Trong ví dụ, `SecureRandom` tạo IV 96-bit mới mỗi lần; ứng dụng thực tế phải đánh giá số lượng bản tin trên mỗi key, nhiều node cùng encrypt, snapshot restore, counter rollback và key lifetime theo chuẩn/khuyến nghị.

Những tình huống cần cảnh giác:

- Nhiều instance dùng chung key và cùng counter khởi động từ 0.
- VM snapshot restore khiến sequence/counter lặp.
- Retry mã hóa dùng lại nonce với **plaintext/AAD khác** trên cùng key.
- Job migration tái sử dụng nonce v1 khi re-encrypt v2 mà không có policy bảo đảm uniqueness; tốt hơn sinh IV mới theo profile.
- Một key version cũ vẫn được dùng để encrypt ở node chưa update sau switch sang decrypt-only.
- Key alias được reset trỏ lại key bytes cũ, làm hệ thống tưởng đó là key mới nhưng thực ra cùng key/nonce domain.
- Hệ thống dùng random 96-bit nonce ở quy mô vượt ngân sách message count đã được đánh giá, làm collision probability không còn được chấp nhận.

Trong luồng key rotation, mỗi key generation phải có **usage limits, nonce allocation model và metrics** độc lập. Với cơ chế counter, phải đồng bộ đa node và chống rollback; với nonce ngẫu nhiên, có giới hạn cryptoperiod/message count và chính sách rotation hợp lý.

## 13. Rollout và rollback khi nhiều service cùng đọc/ghi

Thay `activeKeyVersion` không chỉ là đổi một config:

**Giai đoạn chuẩn bị:**

1. Tạo key v2 trong KMS/keystore với đúng policy và quyền.
2. Cập nhật consumer/decryptor trước để **có khả năng resolve v2**, nhưng vẫn đọc v1.
3. Kiểm end-to-end test/health, khả năng encrypt/decrypt ở staging, failover region và backup service.
4. Chốt `formatVersion`/AAD schema để không vô tình đổi nhiều thứ cùng lúc.

**Giai đoạn kích hoạt:**

1. Chuyển active encrypt version sang v2 theo cơ chế cấu hình tin cậy.
2. Đảm bảo chỉ có **một chính sách chọn key được công bố**; với distributed rollout cần xử lý thời gian hệ thống có cả v1/v2 writer.
3. Xác nhận record mới chứa v2 và decrypt được trên các node hiện hành; không dùng v1 cho new writes sau khi đã chuyển hoàn tất.
4. Giữ v1 ở chế độ decrypt-only cho đến khi bảo đảm retention và migration.

**Giai đoạn hậu kiểm:**

1. Đếm live records theo key reference, theo tenant và theo môi trường; kiểm failed decrypt theo version.
2. Kiểm backup, DR, job chậm, message queue, archive và batch export.
3. Chạy migration có checkpoint/transaction nếu cần.
4. Đưa v1 vào trạng thái disabled/destroyed **chỉ sau khi có bằng chứng không còn phụ thuộc cần đọc** hoặc khi chính sách rủi ro buộc từ chối.

**Rollback:** Nếu writer v2 gặp lỗi, đừng xóa/disable v2 ngay — **những ciphertext đã được ghi bằng v2 có thể cần key v2 để đọc**. Quay lại writer v1 (nếu policy cho phép) chỉ thay đổi key dùng ghi mới, **không đảo ngược các record v2 đã tồn tại**. Kế hoạch rollback phải giữ cả bộ key versions mà dữ liệu đã tham chiếu.

### Multi-region và backup

Một bản backup dữ liệu chỉ hữu ích nếu có cách lấy đúng key để giải mã **theo quyền và chính sách**. Hệ thống phải có recovery plan cho metadata/key reference, availability của KMS, trust domain, quyền IAM, và lịch sử key versions.

Khi restore backup 6 tháng trước, các records có thể còn tham chiếu v1 dù production hiện tại đã chuyển v2. Nếu v1 bị hủy, có thể không restore được. Ngược lại, backup một cách bừa bãi toàn bộ plaintext key material lại phá vỡ mục tiêu quản lý khóa. Cần quy trình escrow/backup/restore trong vùng bảo vệ được kiểm soát, với audit và business continuity requirements.

**Kiểm thử restore thực tế**, không chỉ kiểm rằng file backup tồn tại.

## 14. Xóa khóa có thể đồng nghĩa xóa khả năng đọc dữ liệu

Khóa bị xóa/disable không còn dùng decrypt được. Nếu tất cả các bản sao DEK/KEK hoặc key material liên quan bị hủy thật và không có cách khôi phục, ciphertext tương ứng có thể trở thành **không thể giải mã** — đây là nguyên tắc *cryptographic erasure* trong một số thiết kế.

Tuy nhiên, không nên khẳng định “đã crypto-erase” chỉ vì xóa một entry khỏi config:

- Có thể còn bản sao key trong backup, cache, log, snapshot, instance sống hoặc hệ KMS khác.
- Có thể còn plaintext và bản sao dữ liệu đã được xuất ra.
- Với envelope encryption, xóa KEK có thể ảnh hưởng nhiều wrapped DEK; cần hiểu key hierarchy.
- Key rotation và xóa key không thay thế hủy dữ liệu, truy cập hạn chế và chính sách retention.
- Khi key bị compromise, xóa khỏi service không làm các bản ciphertext attacker đã sao chép trở lại an toàn.

Do đó, trước khi **destroy** key cũ phải có bằng chứng kiểm kê record dependencies, backup retention và quyết định pháp lý/nghiệp vụ. Nếu vẫn còn dữ liệu cần đọc mà key đã mất hoàn toàn, **không có thao tác Java nào tự tái tạo được key chỉ từ key ID hoặc ciphertext**.

## 15. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng duy nhất `CURRENT_KEY` để decrypt mọi record | Đổi key làm record cũ fail tag | Lưu immutable key reference trên mỗi record |
| Lưu alias `latest` nhưng không version | Alias chuyển hướng sang key khác | Lưu version cụ thể hoặc blob KMS tự định tuyến lịch sử theo contract |
| Coi key ID là secret hoặc đưa key bytes vào ID | Lộ key hoặc nhầm trust boundary | Key ID chỉ là tham chiếu; secret trong key manager |
| Dùng chung một `version` cho format, key và schema | Không biết cần parse/dùng key nào | Tách ý nghĩa/version field |
| Tự động thử toàn bộ keyring khi decrypt | Lỗi mơ hồ, tốn tài nguyên, mở oracle | Lookup đúng một key version theo metadata/registry |
| Cho client chọn key tùy ý | Cross-tenant lookup/key abuse | Scope theo tenant, identity và IAM/allowlist server |
| Không xác thực key ID/header bằng AEAD | Metadata có thể bị tráo | Đưa header vào AAD, validate profile/key scope |
| Giữ v1 ACTIVE ở node cũ sau rotation | Dữ liệu mới tiếp tục phụ thuộc key cũ | Triển khai trạng thái decrypt-only và quan sát writers |
| Chỉ đổi header v1 thành v2 khi migrate | Ciphertext/tag vẫn gắn key/nonce/AAD cũ | Decrypt + verify rồi encrypt lại với v2 + nonce mới |
| Xóa v1 ngay khi đổi active v2 | Mất khả năng đọc/restore bản mã cũ | Retain decrypt-only tới khi hết phụ thuộc |
| Quên backup/DR/queue khi đếm key usage | Restore thất bại hoặc job còn dùng key cũ | Inventory đầy đủ theo nơi lưu và thời hạn |
| Migration ghi key ID mới trước ciphertext/tag | State nửa vời, mất dữ liệu | Atomic transaction/object replace/compare-and-swap |
| Rewrap KEK nhưng format AAD chứa KEK metadata | Tag payload có thể không còn đúng | Thiết kế envelope để rewrap đúng contract hoặc re-encrypt |
| Re-encrypt nhưng dùng lại nonce trên cùng key | Nguy cơ phá bảo mật GCM | Nonce uniqueness toàn vòng đời key |
| Coi tag hợp lệ là record mới nhất | Replay/rollback ciphertext cũ | Trusted monotonic revision hoặc anti-rollback state |
| Công bố plaintext từ `Cipher.update` trước tag | Dữ liệu chưa xác thực thoát khỏi vùng tin cậy | Chỉ commit/publish sau `doFinal` thành công |
| Đổi active pointer rồi rollback nhưng xóa key v2 | Record vừa tạo bằng v2 không đọc được | Retain mọi key version đã ghi dữ liệu |
| In key, plaintext, raw wrapped DEK vào log | Lộ dữ liệu nhạy cảm | Audit metadata có làm sạch và kiểm quyền |

## 16. Checklist kiểm thử và chấp nhận rotation

Bộ test tối thiểu nên chạy tự động trong CI/staging trước mỗi rollout:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Ghi v1 rồi chuyển ACTIVE sang v2 | Record v1 vẫn decrypt với v1 nếu policy còn cho phép |
| Ghi record mới sau switch | Envelope chứa immutable v2 key ref; decrypt với v2 |
| v1 chuyển DECRYPT_ONLY | Không tạo new writes bằng v1; record v1 vẫn đọc được |
| v1 key bị disabled/mất | Record v1 bị từ chối rõ ràng, không thử key khác |
| Đổi key ID v1 thành v2 trong header | AEAD authentication thất bại |
| Đổi IV, ciphertext hoặc tag | Bị từ chối; không trả plaintext |
| Đổi tenant/document context AAD | Tag fail; không dùng plaintext |
| Format version không hỗ trợ | Parser từ chối, không fallback yếu |
| Migrate v1 -> v2 | Decrypt/authenticate v1 rồi encrypt v2 bằng IV mới, nội dung không đổi |
| Migration bị ngắt trước commit | Bản v1 còn nguyên; retry idempotent |
| Hai migration workers đụng cùng record | Optimistic lock/CAS chặn ghi đè phiên bản mới |
| Rollback writer sau khi đã có v2 records | v2 records vẫn decrypt được |
| Backup/DR restore | Hệ khôi phục đúng key version theo policy và role |
| Còn legacy record trong archive | Không được destroy key cũ nếu archive còn phải phục hồi |
| Tenant A header trỏ key tenant B | Scope authorization từ chối trước key use |
| Key ID giả/cực dài/không tồn tại | Bounded parsing, lookup từ chối, không lộ thông tin key |
| Nonce reuse attempt với cùng key | Test/quy trình nonce allocation và limits phát hiện/prevent theo thiết kế |
| Record cũ hợp lệ được replay | Anti-replay/anti-rollback policy xử lý theo state tin cậy |
| Performance migration | Có quota/rate limit, backoff, checkpoint và audit |
| Audit | Ghi record ID, key reference, migration result; không lộ key/plaintext |

**Điều kiện hoàn thành rotation:** không chỉ là “mã hóa mới được bằng v2”. Cần có bằng chứng decrypt các record v1/v2 đúng theo policy, migration không làm hỏng dữ liệu, backup có thể restore, old-key retirement không phá retention và không có key access ngoài quyền.

## 17. Bài tập thực hành

### Bài 1 — Phân biệt loại version

Cho record có `formatVersion=2`, `keyRef=orders/prod`, `keyVersion=5`, `documentSchemaVersion=3`. Hãy mô tả từng version quyết định phương thức nào, giá trị nào được phép đổi khi re-encrypt, và vì sao không thể chỉ đọc `keyRef=orders/prod` nếu alias trỏ tới key material mới.

### Bài 2 — Phân tích output chương trình

Chạy `KeyVersionDemo` và giải thích từng dòng stdout. Bổ sung test đổi một byte nonce/header, đổi một bit tag, thiếu toàn bộ record, và record có `formatVersion` chưa được allowlist. Chứng minh method `decrypt` không trả plaintext khi tag không hợp lệ.

### Bài 3 — Lập chính sách vòng đời

Một hệ thống có 3 triệu bản ghi v1, 10.000 bản ghi v2, snapshot hàng tuần giữ 180 ngày, archive giữ 7 năm. Hãy đề xuất states ACTIVE/DECRYPT_ONLY/DISABLED, KPI theo key version, kế hoạch batch migration và khi nào được phép destroy v1. Phân biệt số live records với số bản nằm trong backup còn phải restore.

### Bài 4 — Lazy migration và optimistic lock

Thiết kế bảng `EncryptedDocument(id, revision, keyVersion, encryptedEnvelope)`. Hai request đồng thời đọc record v1, cả hai muốn migrate sang v2. Viết giả mã transaction/CAS để chỉ một lần cập nhật được commit, request còn lại không được ghi đè revision mới hơn. Mô tả cách retry và bảo đảm không phát side effects nghiệp vụ.

### Bài 5 — Rewrap DEK và KEK

Một service mã hóa từng object bằng DEK riêng; KMS dùng KEK v1 để wrap DEK. Khi KEK chuyển sang v2, phần nào có thể được giữ nguyên và phần nào phải được cập nhật? Giải thích vì sao điều này khác trường hợp hệ thống dùng **một AES key trực tiếp mã hóa mọi object**, và xử lý ra sao nếu AAD của ciphertext bao gồm KEK version.

### Bài 6 — Khôi phục thảm họa

Sau khi đổi active key v2, một region bị lỗi và đội vận hành restore backup chứa cả v1/v2 ciphertext. Viết danh sách key versions, quyền IAM, metadata AAD, key availability và phiên bản code cần có. Nêu những tình huống mà restore không thể hoàn tất dù file backup còn nguyên.

### Bài 7 — Compromise và cryptographic erasure

Một key v1 bị nghi lộ khi vẫn còn 100.000 records phụ thuộc. Hãy lập thứ tự ưu tiên containment, kiểm phạm vi dữ liệu có thể bị lộ, migration, key disable/revoke, backup/key retention và thông báo sự cố theo policy. Tại sao re-encrypt không thể làm “bí mật trở lại” nếu đối thủ đã lấy plaintext trước đó?

**Kết quả mong đợi:** bạn có thể nhìn một ciphertext và xác định **đúng khóa cần dùng, đúng phiên bản format, metadata nào phải xác thực, cách đọc dữ liệu cũ khi rotation**, và khi nào **không được hủy key**. Một triển khai đạt yêu cầu luôn có test cho thiếu/sai key, tampering, replay/rollback theo threat model và migration transaction safety.

## 18. Tài liệu tham khảo

- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `init`, `updateAAD`, `doFinal` và AEAD.
- [Java SE 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV/nonce và độ dài tag tính bằng bit.
- [Java SE 17 — KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): sinh secret key theo thuật toán/provider.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn byte ngẫu nhiên mật mã.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): vòng đời và quản lý khóa.
- [NIST SP 800-38D — Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): AEAD và yêu cầu IV/nonce.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): quản lý khóa, dữ liệu và rotation.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): lifecycle, storage, access control và rotation.
