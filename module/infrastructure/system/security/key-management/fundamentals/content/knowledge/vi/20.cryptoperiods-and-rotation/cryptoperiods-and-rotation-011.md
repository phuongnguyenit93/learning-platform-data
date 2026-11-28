# Re-wrapping: thay lớp bảo vệ khóa mà không cần mã hóa lại dữ liệu

## 1. Bài toán: khi KEK hết cryptoperiod, có cần mã hóa lại hàng triệu hồ sơ?

Một hệ thống Java lưu mười triệu hồ sơ nhạy cảm. Mỗi hồ sơ được mã hóa bằng một **Data Encryption Key (DEK)** riêng theo **AES-GCM**. Bản thân DEK được mã hóa bằng **Key Encryption Key (KEK)** lưu trong KMS/HSM. Đến lịch rotation, tổ chức muốn ngừng dùng KEK-v1 để bảo vệ DEKs mới và chuyển sang KEK-v2.

Có hai phương án rất khác nhau:

- Giải mã toàn bộ dữ liệu rồi **Encrypt lại bằng DEK mới**. Điều này thay bản mã dữ liệu, tốn I/O, tăng thời gian plaintext hiện diện trong bộ nhớ và đòi hỏi kiểm soát migration phức tạp.
- Mở lớp bảo vệ của mỗi DEK dưới KEK-v1, sau đó **bọc cùng DEK** dưới KEK-v2. Nếu được thiết kế đúng, **data ciphertext, data nonce và data tag có thể giữ nguyên**.

Phương án thứ hai là **re-wrapping** (bọc khóa lại), chủ đề của bài học này.

**Re-wrapping** là thao tác chuyển bản biểu diễn **wrapped key material** từ một lớp bảo vệ khóa cũ sang lớp bảo vệ khóa mới, hoặc sang profile/metadata wrapping được phê duyệt, **mà không chủ đích thay chính key material được bọc**. Trong mô hình envelope encryption, thao tác điển hình là:

~~~text
Trước:
  DEK --------AES-GCM encrypt data-------> ciphertext-data
   |
   +--------Wrap với KEK-v1-------------> wrapped-DEK-v1

Sau re-wrapping:
  SAME DEK ---AES-GCM encrypt data-------> SAME ciphertext-data
   |
   +--------Wrap với KEK-v2-------------> wrapped-DEK-v2
~~~

Re-wrapping giúp triển khai **KEK rotation**, giới hạn sử dụng KEK cũ cho operations mới, chuyển nhà cung cấp KMS/HSM trong một số trường hợp, thay wrapping profile và tăng khả năng quản trị lifecycle của key hierarchy.

Tuy nhiên, **re-wrapping không làm DEK cũ trở thành DEK mới**, không xóa khả năng giải mã của attacker đã nắm DEK, và không khắc phục những bản wrapped DEK cũ đã bị sao chép cùng KEK cũ bị lộ.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nội dung này liên kết vòng đời khóa, **cryptoperiod**, AES-GCM, key hierarchy, envelope encryption, KMS/HSM, IAM, audit, backup/restore, rotation và incident response.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **re-wrapping, re-encryption, re-keying, key rotation, key import và KMS ReEncrypt**.
2. Giải thích vì sao re-wrapping có thể giữ nguyên data ciphertext và những điều kiện khiến nó không thể giữ nguyên.
3. Mô tả key hierarchy **DEK–KEK**, ranh giới tin cậy và nơi plaintext DEK có thể xuất hiện.
4. Thiết kế envelope metadata đủ để biết **old/new KEK references, key version, wrapping algorithm, nonce/tag, context/AAD, data format**.
5. Lập kế hoạch KEK rotation có **cryptoperiod, old-key read policy, migration, rollback, backup và key destruction gates**.
6. Biết khi nào dùng **KMS/HSM native rewrap**, khi nào dùng application-mediated unwrap/wrap và các rủi ro tương ứng.
7. Phân tích **atomicity, retry/idempotency, dual wrapped DEKs, concurrent writes và high-watermark của migration**.
8. Hiểu **compromise response**: vì sao rewrap không đủ nếu DEK hoặc KEK-v1 đã bị lộ cùng dữ liệu lịch sử.
9. Đọc ví dụ **Java 17** với AES-GCM data DEK và AES-GCM wrapping dưới hai KEKs riêng, xác minh rewrap mà không đổi ciphertext.
10. Áp dụng checklist, tình huống production và các câu hỏi tự kiểm tra để đánh giá an toàn.

## 2. Thuật ngữ: re-wrapping thay đổi tầng nào?

| Thành phần | Vai trò | Có đổi khi rewrap KEK? |
| --- | --- | --- |
| **Plaintext data** | Dữ liệu cần bảo vệ | **Không** cần đọc khi chỉ rewrap DEK |
| **DEK material** | Khóa mã hóa/giải mã dữ liệu | **Không**; vẫn là cùng raw key bytes |
| **Data ciphertext** | Dữ liệu mã hóa bằng DEK | **Không**, nếu format/AAD-data độc lập với KEK version |
| **Data nonce và tag** | Giá trị AEAD của data layer | **Không**, nếu data ciphertext không được mã hóa lại |
| **KEK material** | Khóa bảo vệ DEK | **Có thể đổi** từ KEK-v1 sang KEK-v2 |
| **Wrapped DEK** | DEK đã được bọc dưới KEK | **Có**, thường là blob mới |
| **Wrap nonce/tag/IV** | Metadata mật mã của wrapping layer | **Có thể đổi** theo cơ chế mới, cần tạo nonce mới khi dùng GCM |
| **KEK ID/version** | Chỉ ra khóa dùng Unwrap | **Có**, phải cập nhật nhất quán cùng blob |
| **Wrap context/AAD** | Ràng buộc purpose, tenant, key ID, version | **Có thể đổi**, cần dựng lại và xác thực |
| **DEK cryptoperiod/usage history** | Tuổi và số lần dùng DEK | **Không reset** vì DEK không đổi |
| **KEK cryptoperiod** | Thời hạn dùng KEK cho Wrap/Unwrap theo policy | Theo lifecycle của **mỗi KEK version** |

### 2.1. Ba cụm từ thường bị đánh đồng

**KEK rotation**: chuyển từ KEK cũ sang KEK mới cho thao tác Wrap mới. Re-wrapping các DEKs cũ có thể là phần của rotation, nhưng không phải mọi hệ thống buộc rewrap ngay tất cả DEKs.

**DEK rotation/re-keying**: tạo DEK material mới, thường yêu cầu **Decrypt dữ liệu cũ và Encrypt lại** dưới DEK mới hoặc cơ chế migration được phép.

**Re-encryption** có hai cách dùng tùy ngữ cảnh:

- Trong **data plane**, nó có thể là giải mã rồi mã hóa lại dữ liệu ứng dụng bằng DEK mới.
- Trong một số **KMS APIs mang tên ReEncrypt**, nó chỉ chuyển **ciphertext của một data key** từ khóa nguồn sang khóa đích, tức **rewrap** theo góc nhìn envelope encryption.

Vì vậy **không suy luận chỉ từ tên API**. Cần biết payload đầu vào là **wrapped DEK** hay **toàn bộ data ciphertext**.

### 2.2. Rewrap không nhất thiết làm thay key ownership

Một tổ chức có thể rewrap một DEK dưới KEK mới nhưng vẫn quản lý cùng ciphertext và cùng dữ liệu. Đây là thay đổi **key custody/protection**, không tự biến dữ liệu thành của một tenant mới hoặc cấp quyền cho principal mới. Quyền nghiệp vụ và trust binding vẫn phải được kiểm tra độc lập.

## 3. Sơ đồ vòng đời KEK và DEK

~~~mermaid
flowchart TD
    SOURCE["Approved DEK generation"] --> DATA["AES-GCM data ciphertext"]
    SOURCE --> W1["Wrapped DEK under KEK-v1"]
    W1 --> STORE[("Envelope storage")]
    DATA --> STORE
    K1["KEK-v1 cryptoperiod ending"] --> NEW["Create and validate KEK-v2"]
    NEW --> CUT["Switch NEW wrapping operations to KEK-v2"]
    CUT --> MIG["Rewrap existing DEKs KEK-v1 to KEK-v2"]
    STORE --> MIG
    MIG --> VERIFY["Verify wrapped blob + unchanged data ciphertext"]
    VERIFY --> RET["Old KEK-v1: restricted legacy Unwrap"]
    RET --> BACKUP["Inventory backups / restore tests / rollback window"]
    BACKUP --> DEL{"Any dependency on KEK-v1?"}
    DEL -->|Yes| RET
    DEL -->|No and approved| DEST["Controlled retirement / destruction"]
~~~

Phân biệt hai trục thời gian:

- **KEK operational cryptoperiod**: khi nào KEK được dùng **Wrap DEKs mới**? Có còn được **Unwrap DEKs lịch sử** trong giai đoạn chuyển tiếp không?
- **DEK operational cryptoperiod**: khi nào DEK được dùng **Encrypt dữ liệu mới**? DEK đó còn được dùng **Decrypt dữ liệu cũ** đến khi nào?

Các thời hạn phải được định nghĩa theo **operation và use case**. Một KEK có thể ngừng Wrap mới nhưng vẫn Unwrap legacy nếu key state/provider/IAM hỗ trợ điều đó. Không phải mọi KMS có native state tên “decrypt-only”; đôi khi cần enforce bằng IAM/grants, key selection hoặc service policy.

### 3.1. KEK rotation khác DEK replacement

Một ví dụ:

~~~text
DEK-17:
  original generation: ngày D0
  data Encrypt invocations: 400,000

KEK-v1:
  wraps DEK-17 until ngày D1

KEK-v2:
  rewraps SAME DEK-17 at ngày D1+1

DEK-17 vẫn có cùng material và 400,000 lượt sử dụng cũ.
~~~

**Không reset nonce counter, data usage count hay DEK cryptoperiod** sau rewrap. Nếu AES-GCM DEK đã vượt giới hạn hoặc có nonce reuse, phải xử lý **DEK/new data encryption**, không chỉ chuyển lớp KEK.

## 4. Điều kiện để data ciphertext thực sự không thay đổi

Một envelope điển hình:

~~~json
{
  "formatVersion": 2,
  "tenantId": "tenant-A",
  "objectId": "invoice-154",
  "dataProfile": "AES-256-GCM",
  "dataNonce": "<base64 nonce>",
  "dataCiphertextAndTag": "<base64 data blob>",
  "wrappedDek": {
    "kekRef": "kms://key-v1",
    "wrappingProfile": "KMS-APPROVED",
    "ciphertext": "<base64 wrapped DEK>"
  },
  "contextSchema": "billing-envelope-v2"
}
~~~

Đây là ví dụ metadata, không chứa raw secret.

Muốn rewrap mà **không đổi dataCiphertextAndTag**, phải giữ đúng:

1. **Cùng DEK material**, không tự tạo DEK mới khi rewrap.
2. **Cùng data ciphertext, nonce, tag** và data AEAD profile.
3. **AAD-data không phụ thuộc vào trường vừa thay**, như KEK version mới, nếu không việc thay header có thể làm tag-data không còn khớp.
4. Nếu data AAD chứa **envelope generation/version**, phải định nghĩa rõ đó là *data-format version bất biến* hay *wrapping version có thể cập nhật*. Không dùng một trường version mơ hồ cho cả hai.
5. **Context của wrapping layer** cần được dựng đúng cho KEK-v2 và metadata mới.
6. **Key reference resolver** phải ánh xạ old/new key IDs tới material đáng tin, không cho client chọn KEK tùy ý.
7. Cơ chế **anti-rollback** của record/version state phải xử lý old envelope được phát lại sau migration.

### 4.1. Domain separation giữa data AAD và wrap context

~~~text
AAD-data (không đổi trong rewrap):
  data-format-v2 | tenant-A | invoice-154 | data-purpose

AAD-wrap-v1:
  wrap-dek-v1 | tenant-A | invoice-154 | kek-id-v1

AAD-wrap-v2:
  wrap-dek-v1 | tenant-A | invoice-154 | kek-id-v2
~~~

Nếu data AAD chứa KEK ID cũ trong khi business yêu cầu đổi KEK ID trong header, dữ liệu có thể phải **re-encrypt hoặc dùng một header binding/format migration thiết kế khác**; không thể sửa AAD của bản mã đã xác thực mà giữ tag bất biến.

### 4.2. Không có nguyên tắc “chỉ lưu wrapped DEK là đủ”

Để mở dữ liệu sau nhiều năm, envelope/registry cần lưu đủ **key ID/version, wrapping profile, encryption context/AAD, wrap nonce/tag (nếu có), data nonce/tag/AAD schema, ciphertext, format version và quyền truy cập key material**. Một ciphertext hoàn toàn nguyên vẹn vẫn không thể giải mã khi metadata cần thiết bị mất.

## 5. Luồng rewrap từ KEK-v1 sang KEK-v2

~~~mermaid
sequenceDiagram
    participant P as Migration orchestrator
    participant DB as Envelope storage
    participant K as KMS/HSM
    participant A as Audit/evidence
    P->>DB: Read key metadata + wrappedDEK-v1
    P->>P: Authorize tenant/object and verify trusted key refs
    P->>K: Rewrap(oldKey, newKey, wrappedDEK, contexts)
    Note over K: Native operation nếu provider hỗ trợ
    K-->>P: New wrappedDEK-v2 + key reference
    P->>P: Validate new envelope metadata and unchanged data fields
    P->>DB: Atomic compare-and-swap update wrapping fields
    DB-->>P: Version updated / conflict
    P->>A: Audit success, source and destination refs, no secrets
    Note over P,K: Với client-mediated path, plaintext DEK có thể vào RAM ứng dụng
~~~

### 5.1. Các bước của một record

1. Xác định **record/object** và quyền của migration service.
2. Load envelope version cùng **old wrapped DEK, KEK ref, wrapping context**.
3. Kiểm tra key ID/material version với **trusted policy/registry** thay vì mù quáng tin header.
4. Yêu cầu provider **Unwrap/Decrypt source blob** hoặc thực hiện native key rewrap.
5. Bọc **same DEK** dưới KEK mới với wrapping profile/context phù hợp.
6. Tạo metadata version mới, thay **wrapped blob và wrapping key reference atomically**.
7. Xác minh key mới có thể Unwrap và DEK vẫn Decrypt **test/reference data** hợp lệ theo approved scope.
8. Lưu audit/evidence, trạng thái tiến trình và checkpoint.
9. Theo dõi lỗi/retry, không bỏ record failed rồi tuyên bố migration hoàn tất.

### 5.2. Source/target key IDs phải rõ

Không sử dụng alias thân thiện làm bằng chứng duy nhất. Alias có thể đổi đích giữa hai API calls. Migration nên resolve **immutable source key ID/version** và **immutable destination key ID/version** theo approved plan; ngăn lỗi TOCTOU nếu provider/API cho phép.

### 5.3. Rewrap có thể không cần data plaintext

Nếu chỉ xử lý wrapped DEK, **không cần Decrypt toàn bộ dữ liệu** trong đường migration. Với KMS native rewrap, provider có thể giải mã key blob rồi mã hóa lại **bên trong managed boundary** mà client không bao giờ nhận raw DEK. Tuy nhiên cần xác minh chính xác contract của provider, supported keys, grants, context và limits.

## 6. Các cách triển khai: local, KMS-native và HSM-to-HSM

| Mô hình | DEK plaintext xuất hiện ở đâu? | Khi nào phù hợp? | Lưu ý |
| --- | --- | --- | --- |
| **Native KMS rewrap/re-encrypt key blob** | Trong KMS/provider boundary theo API | Provider hỗ trợ chuyển key blob giữa nguồn/đích | Kiểm tra API semantics, authorization, source/destination contexts |
| **Client-mediated Unwrap → Wrap** | RAM ứng dụng migration | Không có native rewrap; policy cho phép raw DEK tạm thời | Tăng attack surface, cần giới hạn secret lifetime và logs |
| **HSM-internal UnwrapKey + WrapKey** | Có thể trong cryptographic module | Cần giữ key material non-exportable tại HSM | Vendor mechanism/attributes/partition limitations |
| **Secure HSM-to-HSM key migration** | Bảo vệ trong approved key block/transport protocol | Chuyển boundary/provider mà không xuất raw key | Trust/attestation/quorum và capability khác nhau |
| **Password-derived KEK rewrap** | Tùy client-side architecture | Đổi mật khẩu dùng để bảo vệ một DEK | KDF params, salt, password quality, recovery/old backups |
| **Asymmetric wrapping public key rotation** | Phụ thuộc workflow decrypt/re-encrypt small DEK | Public-key-encrypted DEKs cần key pair mới | New recipient trust, RSA-OAEP/EC-based approved protocol |

### 6.1. Native KMS API không phải tên gọi tiêu chuẩn chung

Một nhà cung cấp có thể gọi việc chuyển encrypted data key blob sang key khác là **ReEncrypt**. Nhà cung cấp khác có thể chỉ cung cấp **Decrypt + Encrypt**, hoặc chuyển material bằng API **WrapKey/UnwrapKey**.

Kiểm tra:

- Input thực chất là **data ciphertext** hay **encrypted DEK**?
- Source key/ref và target key/ref là gì?
- Có cần **source encryption context** và **target encryption context** riêng?
- Metadata wrapping nonce/tag được provider đóng gói như thế nào?
- API có chấp nhận keys khác region/account/partition không?
- Hoạt động có xuất plaintext DEK về client không?
- Quota, access logs, error behaviors và phí ra sao?
- Có thể rewrap blob chưa rõ version hoặc trạng thái disabled không?

**Không tự gọi API ReEncrypt rồi tuyên bố toàn bộ bảng dữ liệu đã được mã hóa lại.**

### 6.2. Trường hợp client-mediated

Nếu buộc phải đưa DEK vào application migration:

- Chạy workload trên môi trường trusted/hardened với **IAM time-bound** và network controls.
- Dùng đúng API Unwrap/Decrypt, không tự bỏ tag/AAD.
- Giới hạn plaintext DEK trong RAM và loại bỏ mọi logging/debug dumps.
- Dùng **new nonce** khi wrap lại dưới KEK-v2 nếu wrapping mode yêu cầu.
- Không cache hàng nghìn DEKs quá lâu để tăng throughput bằng mọi giá.
- Cần incident plan vì một máy migration bị chiếm có thể unwrap rất nhiều DEKs.
- Đừng coi Arrays.fill(byte[]) là đảm bảo xóa mọi bản copy của key trong JVM/provider.

### 6.3. Private signing key và giới hạn rewrap

Rewrap một private key bảo vệ trong PKCS#8/keystore có thể thay container password/KEK, **không nhất thiết thay private signing key material**. Nhưng nhiều HSM key objects được đánh dấu non-extractable và **không cho xuất dưới wrapped form**; cần kiểm tra provider mechanisms và policy. Nếu muốn đổi signer identity, phải **generate private key mới và cập nhật public verification trust**, không chỉ rewrap key container.

### 6.4. Password-based envelope

Nếu một DEK được bọc dưới **KEK dẫn xuất từ mật khẩu**, đổi mật khẩu có thể thực hiện:

- Dùng KDF cũ (Argon2id/scrypt/PBKDF2 theo profile) để dẫn xuất **old KEK**.
- Authenticated Unwrap DEK.
- Sinh salt và params cho KDF mới, dẫn xuất **new KEK**.
- Wrap same DEK dưới KEK mới, lưu metadata mới một cách nguyên tử.

Điều này **không đổi data ciphertext**, nhưng password sai hoặc mất old wrapping metadata có thể làm mất DEK. **Đổi mật khẩu không tự bảo vệ được các bản envelope cũ đã bị attacker sao chép cùng mật khẩu cũ**. Đừng dùng password thô hoặc SHA-256(password) làm KEK trực tiếp.
## 7. Cơ chế wrapping và những giới hạn cần biết

Re-wrapping gồm hai bước logic, dù nhà cung cấp có thể thực hiện trong một API và không xuất plaintext DEK:

~~~text
DEK = AuthenticatedUnwrap(
  oldKEK, oldWrappedDEK, oldWrappingContext
)

newWrappedDEK = AuthenticatedWrap(
  newKEK, SAME DEK, newWrappingContext
)
~~~

Điểm bất biến là **same DEK material**, không phải tên key hay chiều dài key. Integrity check ở tầng Unwrap phải đạt; nếu sai tag/OAEP/key block format, **fail closed**, không thử cơ chế mã hóa yếu hơn.

| Wrapping mechanism | Dùng cho | Điều kiện cần kiểm tra |
| --- | --- | --- |
| **KMS native ReEncrypt/rewrap** | Chuyển encrypted key blob giữa KMS keys | API semantics, grants, source/destination contexts, provider boundary |
| **AES-KW / AES-KWP** | Bọc material khóa theo cơ chế chuyên dụng | Key size, usage purpose, wrapping profile và integrity |
| **AES-GCM** | AEAD bọc DEK dưới KEK + AAD | Nonce-wrap duy nhất dưới cùng KEK, tag verification, context |
| **RSA-OAEP** | Bọc DEK nhỏ cho trusted public encryption key | Recipient trust, hash/MGF/label, payload bound |
| **HSM secure key block** | Import/export giữa cryptographic modules | Allowed mechanisms, attestation, wrapping domains, quorum |

**Không bọc DEK bằng AES-ECB, CBC thiếu authentication, XOR, hash một chiều hoặc Base64** rồi tự gọi là re-wrapping an toàn.

### 7.1. Nonce và key usage của hai tầng khác nhau

Nếu KEK dùng AES-GCM để Wrap nhiều DEKs, **nonce-wrap của mỗi phép Encrypt dưới cùng KEK phải duy nhất** theo đúng profile. Nonce-data của DEK là miền riêng:

~~~text
Data layer:
  DEK + nonce-data + AAD-data -> data ciphertext + data tag

Wrapping layer:
  KEK + nonce-wrap + AAD-wrap -> wrapped DEK + wrap tag
~~~

Với rewrap hàng triệu DEKs, cần đánh giá **usage limits, IV collision probability, quota, restart/failover và distributed nonce allocation**. Random IV 96 bit cho GCM không có nghĩa có thể sử dụng vô hạn. Nếu KMS dùng AES-KW/KWP hoặc provider-specific mechanism, áp đúng các giới hạn của **mechanism thực tế**, không áp giả định GCM cho mọi cách wrap.

### 7.2. Đối soát cùng DEK mà không log raw key

Có thể dùng **approved functional test**: wrapped DEK mới phải mở được một ciphertext thử nghiệm đã Encrypt dưới DEK cũ, đúng nonce/AAD/tag. Hoặc dựa trên KMS/HSM native rewrap contract với provider evidence và kiểm tra data sample được phép.

**Không xuất raw DEK/KEK chỉ để tính hash công khai hoặc đưa KCV vào log** nếu điều đó làm yếu security boundary. KCV/fingerprint nếu dùng cần thiết kế và approval tương ứng; KCV không chứng minh entropy, nguồn gốc hoặc quyền truy cập.

## 8. Rewrap và cryptoperiod: hai trục thời gian

Một KEK có thể ngừng dùng **Wrap mới** từ ngày D1 nhưng vẫn được phép **Unwrap legacy** trong thời gian migration/retention. Một DEK cũ có thể ngừng **Encrypt mới** nhưng vẫn được phép **Decrypt dữ liệu lịch sử**.

~~~text
D0     : KEK-v1 ACTIVE_FOR_WRAP
D1     : Activate KEK-v2 for NEW Wrap
D1..D2 : Rewrap wrapped DEKs v1 -> v2
D2..D3 : Old KEK-v1 restricted to approved legacy Unwrap
D3     : Dependency inventory + backup restore checks
D4     : Controlled destruction only when safe and approved
~~~

Không phải mọi provider có native state “decrypt-only”; có thể cần **KMS IAM, alias routing, application policy hoặc special grants**.

### 8.1. Những trigger thường gặp

| Trigger | Hướng quyết định |
| --- | --- |
| **KEK hết thời hạn dùng để Wrap mới** | Tạo KEK version mới, rewrap old DEKs theo policy |
| **Đổi KMS/HSM/region** | Rewrap nếu có secure transfer và compatible wrapping format |
| **Đổi password bọc DEK** | Dẫn xuất new KEK theo KDF profile, rewrap cùng DEK |
| **Đổi wrapping algorithm** | Rewrap theo approved migration; kiểm tra key attributes/metadata |
| **KEK-v1 bị lộ** | Không tự coi rewrap đủ; đánh giá old wrapped blobs và data impact |
| **DEK bị lộ hoặc GCM nonce reuse** | **DEK replacement + re-encrypt**, không chỉ đổi KEK |
| **IAM misuse** | Sửa grants, điều tra Unwrap/Decrypt và DEKs đã lấy |
| **Imported key material sắp hết hạn** | Rewrap/restore/migrate trước expiry, có backup plan |
| **Data retention kết thúc** | Quy trình key/data destruction riêng, kiểm tra dependencies |

**Cryptoperiod không chỉ là một cron job.** Usage limits, compromised material, source-copy exposure và key state có thể buộc xử lý trước lịch rotation.

### 8.2. Đừng reset DEK usage counter sau rewrap

Nếu DEK-v7 đã mã hóa 300.000 objects, rewrap nó bằng KEK-v2 không đổi raw key material. **AES-GCM nonce history và DEK cryptoperiod vẫn là của DEK-v7.** Nếu muốn có ngân sách Encrypt mới do vật liệu mới, cần generate **DEK-v8** và thực hiện re-encrypt data/use case thích hợp.

## 9. Quy trình rewrap production theo từng giai đoạn

### 9.1. Preflight

1. **Inventory** những DEKs đang được wrap bởi KEK-v1, gồm cold data và backups.
2. Xác định **source key ID/version, wrapping algorithm/context**, data format và tenant boundaries.
3. **Generate/validate KEK-v2** trong security boundary được duyệt; kiểm tra owner/custodian, algorithm, key usage, state và non-exportability.
4. Chọn **native KMS rewrap hoặc client-mediated**, đánh giá raw DEK residency.
5. Phê duyệt **IAM migration principal**, time-bound grants và operation scopes.
6. Chuẩn bị **atomic metadata update** và rollback/retry strategy.
7. Xác định **old KEK dependency window**, cryptoperiod, backup retention và planned destruction gate.
8. Ước tính request volume, throughput, KMS quotas/rates, provider billing và data scan cost.
9. Định nghĩa **verification evidence** và success criteria độc lập với job progress.
10. Có owner approval/security review và cảnh báo khi migration failure tăng.

### 9.2. Cutover new writes

Sau khi KEK-v2 sẵn sàng, chuyển **new DEK wrapping** sang v2. Nếu writers cũ vẫn ghi v1 sau khi migration scan kết thúc, sẽ có **new legacy blobs** không được xử lý.

- Active KEK reference phải đến từ trusted registry/config version.
- Đo các operations Wrap trên KEK-v1 sau cutover; alert/deny theo policy.
- Rà soát queued/offline writers, retry jobs và caches.
- Không tin key ID người dùng cung cấp để chọn KEK.
- Có rollback giới hạn phạm vi; không hạ cấp hệ thống về KEK yếu trong im lặng.

### 9.3. Migrate theo batch

Với mỗi record:

1. Đọc **envelope revision, old keyRef, old wrapped DEK, wrapping context**.
2. Xác minh resource/tenant, key ID và algorithm theo source of truth.
3. Thực hiện **KMS native rewrap** hoặc verified Unwrap → Wrap.
4. Tạo **new wrapped DEK, new KEK ref, new wrapping context/version**.
5. Ghi tất cả thay đổi **atomically với optimistic concurrency**.
6. Nếu CAS thua, đọc lại record; không overwrite state của writer khác.
7. Lưu audit/correlation ID/checkpoint sau commit.
8. Retry idempotent; nếu tạo wrap blob mới bằng AES-GCM, cấp nonce **mới**.
9. Đối soát số records còn v1, lỗi không giải quyết và migration coverage.

### 9.4. Verify và retire

- Test Decrypt sample với KEK-v2 và **expected data AAD**.
- Xác minh **data ciphertext/nonce/tag không đổi** nếu chính sách yêu cầu rewrap-only.
- Kiểm kê backup/offline archives còn KEK-v1; restore test bằng key version đúng.
- Review KMS IAM/grants, old-key state, replication và caching.
- Chỉ retire/destroy KEK-v1 khi không còn dependency hợp lệ, có approval và audit.

## 10. Cập nhật metadata nguyên tử và retry idempotent

### 10.1. Lỗi cập nhật nửa chừng

Nếu envelope đầu tiên là:

~~~text
wrappedDek = ciphertext under KEK-v1
kekRef = KEK-v1
~~~

mà worker ghi keyRef trước rồi crash:

~~~text
wrappedDek = ciphertext under KEK-v1
kekRef = KEK-v2  <-- mismatch, không mở được
~~~

**Wrapped DEK + KEK ID/version + wrap profile/context phải được ghi thành một đơn vị nguyên tử.**

### 10.2. Ví dụ optimistic locking

~~~sql
-- PSEUDO SQL: cú pháp/transaction tùy storage engine.
UPDATE encrypted_objects
SET wrapped_dek = :wrapped_v2,
    kek_ref = :kek_v2,
    wrap_context_version = :context_v2,
    envelope_revision = envelope_revision + 1
WHERE tenant_id = :tenant
  AND object_id = :object
  AND envelope_revision = :observed_revision
  AND kek_ref = :expected_kek_v1;
~~~

Chỉ tính completed nếu transaction commit. Nếu update 0 rows hoặc kết quả uncertain, **đọc lại trạng thái hiện tại** trước khi retry; không tự ghi đè payload/ciphertext.

### 10.3. Hai workers cùng rewrap

Hai workers A và B có thể cùng đọc v1, tạo **hai wrapped blobs dưới v2** bằng các nonce-wrap khác nhau. Chỉ một CAS được thắng. Worker thua bỏ blob, đọc lại state. Cả hai lần wrapping đã thực hiện vẫn được tính vào **KEK-v2 usage count**; không tái cấp nonce.

### 10.4. Retry sau timeout

Nếu KMS rewrap thành công nhưng database update bị timeout:

- Record có thể đã ở v2 hoặc vẫn v1.
- Nếu v2 và metadata hợp lệ, đánh dấu completed dựa trên trusted state.
- Nếu vẫn v1, rewrap lại theo provider policy, không reuse nonce cũ.
- Nếu state khác expected, chuyển sang reconciliation, không thử mọi key để tìm một blob mở được.

Idempotency key nên bao gồm **migration plan ID, record ID, source revision, source KEK version và destination KEK version**. Nó giúp kiểm soát business workflow, **không tự làm GCM nonce duy nhất**.

## 11. Dual-wrapped DEKs: khi nào giữ cả v1 và v2?

Trong migration lớn, có thể tạm lưu hai blobs:

~~~json
{
  "dataCiphertextAndTag": "<unchanged>",
  "dataNonce": "<unchanged>",
  "envelopeRevision": 28,
  "wrappingCandidates": [
    {"kekRef": "kms://KEK-v1", "state": "LEGACY_READ_ONLY", "blob": "<old>"},
    {"kekRef": "kms://KEK-v2", "state": "PREFERRED", "blob": "<new>"}
  ]
}
~~~

Ưu điểm là hỗ trợ rollback/khôi phục trong một khoảng được phê duyệt. Nhược điểm: kéo dài khả năng Unwrap qua KEK cũ, tăng metadata/logic phức tạp và **không giảm rủi ro nếu old KEK đã lộ**.

**Không thử mọi KEK trong hệ thống cho tới khi unwrap thành công**. Dùng trusted keyRef/allowlist/state, policy expiry và audit. Nếu old blob sai tag, **reject**, không fallback sang thuật toán yếu hoặc tenant khác.

Plan cần có ngày loại bỏ old candidates, old-key restricted grants và acceptance criteria để tránh “dual-wrapping vĩnh viễn”.

## 12. KMS/HSM, IAM và separation of duties

| Vai trò | Quyền cần theo scope | Không nên mặc định có |
| --- | --- | --- |
| **Application writer** | Wrap bằng active KEK-v2 | Unwrap mọi DEKs lịch sử hoặc đổi KMS policy |
| **Application reader** | Unwrap đúng DEK sau business authorization | Rewrap hàng loạt hoặc Export KEK |
| **Migration worker** | KMS ReEncrypt/Unwrap/Wrap giữa v1/v2 có thời hạn | Decrypt/Sign mọi dữ liệu, quyền thường trực |
| **Key owner** | Phê duyệt purpose/cryptoperiod/cutover | Raw KEK/DEK |
| **Key custodian** | Quản lý key lifecycle/recovery theo change | Business plaintext và quyền xóa audit |
| **KMS administrator** | Key state/policy/grants theo approval | Tự cấp Decrypt mọi key |
| **Security reviewer/auditor** | Xem metadata, grants, evidence | Unwrap, Sign, Export |

Review **effective IAM** gồm key resource policy, role assumption, grants, CreateGrant/ChangePolicy và cross-account paths. **KEK non-exportable không ngăn API misuse**: workload có Decrypt/Unwrap có thể nhận plaintext DEK nếu provider API cho phép.

### 12.1. Encryption context và business authorization

Nếu KMS yêu cầu context tenant/purpose, phải dựng từ **trusted session/resource registry**. Context nguồn/đích có thể khác; data AAD vẫn là domain riêng. Rewrap không cấp quyền đọc hóa đơn của tenant A cho tenant B chỉ vì họ cùng dùng một KEK.

### 12.2. Approval và audit

Root/KEK rủi ro cao có thể yêu cầu **dual control, quorum, key ceremony** và independent review. Không để cùng identity có quyền tạo KEK mới, tự cấp Unwrap, chạy migration, destroy KEK cũ và xóa evidence.

## 13. Backup, recovery và kiểm tra trước khi destroy old KEK

Sau khi main database rewrap xong, các nơi này vẫn có thể cần KEK-v1:

- Object storage snapshots và cold archives.
- Offline backups chưa restore sau rotation.
- CDC/replicas chưa bắt kịp thay đổi metadata.
- Stale writer queues hoặc export packages.
- Old schema/legacy clients còn wrapped DEKs v1.
- Provider imported-key material có expiry hoặc source key chưa được restore ở vùng DR.

Một bộ backup cần tối thiểu:

~~~text
data ciphertext + data nonce/tag + AAD/schema
wrapped DEK + wrapping context/profile + KEK ID/version
trusted key mapping + authorization to Unwrap
source KEK material còn tồn tại hoặc đường recovery hợp lệ
~~~

**Backup checksum đúng không chứng minh Decrypt thành công.** Restore test phải thực sự Unwrap DEK và xác minh data authentication tag với dữ liệu kiểm thử đã được phép.

Trước destroy KEK-v1:

1. Inventory mọi DEK/backup và key dependencies.
2. Confirm new KEK-v2 path ở mọi nơi phải giữ.
3. Test recovery và rollback cutover.
4. Confirm không còn producer tạo old wrapping blobs.
5. Xem legal hold, retention, imported key expiry và provider pending deletion.
6. Owner/custodian/security approval, audit và post-deletion monitoring.

**Xóa KEK dùng chung để hủy một object có thể làm hỏng toàn bộ dataset dùng KEK đó.** Crypto-shredding cần tính cả bản sao old KEK/DEK, caches, plaintext đã xuất và backup snapshots.
## 14. Java 17: rewrap cùng DEK, giữ nguyên data ciphertext

### 14.1. Mục đích của ví dụ

Đoạn Java 17 sau sử dụng JCA/JCE chuẩn để mô phỏng:

1. Sinh **DEK AES-256** và **hai KEK AES-256 khác nhau**.
2. Data được mã hóa bằng **DEK + AES-GCM**, với AAD-data gắn tenant/object.
3. DEK được **wrap dưới KEK-v1** bằng AES-GCM, nonce-wrap và AAD-wrap riêng.
4. Đọc data thành công khi unwrap DEK dưới KEK-v1.
5. **Unwrap same DEK** bằng KEK-v1, rồi **Wrap lại** dưới KEK-v2.
6. **Data ciphertext/nonce/tag bất biến**, chỉ wrapped blob/KEK reference/revision đổi.
7. Đọc data thành công bằng KEK-v2; thử sai tenant và sửa wrap tag phải bị từ chối.

**Chủ ý của demo:** KEK raw được tạo trong JVM nên **không phải KMS/HSM non-exportable**. Production nên dùng native rewrap/WrapKey/UnwrapKey APIs của provider theo policy, thay vì để KEK raw trong process.

### 14.2. Mã Java độc lập

Lưu ví dụ vào tệp thực hành tên `KeyRewrappingDemo.java` trong môi trường học tập, không thêm file đó vào module theo STEP 4.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class KeyRewrappingDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int DEK_BYTES = 32;

    // Byte arrays are cloned when constructed/read.
    // Production should also impose serialized size limits.
    record GcmBlob(byte[] nonce, byte[] ciphertextAndTag) {
        GcmBlob {
            if (nonce == null || nonce.length != NONCE_BYTES
                    || ciphertextAndTag == null
                    || ciphertextAndTag.length < TAG_BITS / 8) {
                throw new IllegalArgumentException(
                    "Invalid GCM blob");
            }
            nonce = nonce.clone();
            ciphertextAndTag = ciphertextAndTag.clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }

        @Override
        public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    record WrappedDek(String kekId, GcmBlob blob) {}

    record Envelope(
            String tenantId,
            String objectId,
            GcmBlob dataBlob,
            WrappedDek wrappedDek,
            long revision) {}

    private static void require(boolean ok, String reason) {
        if (!ok) {
            throw new SecurityException(reason);
        }
    }

    private static SecretKey aes256() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    private static byte[] nonce() {
        byte[] result = new byte[NONCE_BYTES];
        RNG.nextBytes(result);
        return result;
    }

    // Length-prefixed UTF-8 prevents ambiguous concatenation.
    private static byte[] aad(
            String domain, String tenant,
            String object, String context) throws Exception {

        ByteArrayOutputStream buffer =
            new ByteArrayOutputStream();
        try (DataOutputStream out =
                new DataOutputStream(buffer)) {
            for (String value : new String[] {
                    domain, tenant, object, context }) {
                byte[] bytes =
                    value.getBytes(StandardCharsets.UTF_8);
                out.writeInt(bytes.length);
                out.write(bytes);
            }
        }
        return buffer.toByteArray();
    }

    private static GcmBlob encryptAead(
            SecretKey key, byte[] plaintext,
            byte[] associatedData) throws Exception {
        byte[] iv = nonce();
        Cipher cipher =
            Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(associatedData);
        return new GcmBlob(iv, cipher.doFinal(plaintext));
    }

    private static byte[] decryptAead(
            SecretKey key, GcmBlob blob,
            byte[] associatedData) throws Exception {
        Cipher cipher =
            Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, blob.nonce()));
        cipher.updateAAD(associatedData);
        return cipher.doFinal(blob.ciphertextAndTag());
    }

    private static WrappedDek wrap(
            byte[] rawDek, SecretKey kek, String kekId,
            String tenant, String object) throws Exception {
        require(rawDek != null
                && rawDek.length == DEK_BYTES,
            "Unexpected DEK size");

        GcmBlob blob = encryptAead(
            kek, rawDek,
            aad("wrap-dek-v1", tenant, object, kekId));
        return new WrappedDek(kekId, blob);
    }

    private static byte[] unwrap(
            WrappedDek wrapped, SecretKey kek,
            String approvedKekId,
            String tenant, String object) throws Exception {
        require(wrapped != null
                && approvedKekId.equals(wrapped.kekId()),
            "Unapproved wrapping key reference");

        byte[] raw = decryptAead(kek, wrapped.blob(),
            aad("wrap-dek-v1", tenant, object, approvedKekId));
        if (raw.length != DEK_BYTES) {
            Arrays.fill(raw, (byte) 0);
            throw new SecurityException("Invalid DEK length");
        }
        return raw;
    }

    private static void checkContext(
            Envelope envelope, String tenant, String object) {
        require(envelope != null
                && tenant.equals(envelope.tenantId())
                && object.equals(envelope.objectId()),
            "Wrong trusted tenant/object context");
    }

    static Envelope encryptData(
            byte[] plaintext, SecretKey dek,
            SecretKey kek, String kekId,
            String tenant, String object) throws Exception {

        // Business authorization must happen before this call.
        GcmBlob data = encryptAead(dek, plaintext,
            aad("billing-data-v1", tenant, object, "AES-256-GCM"));
        byte[] rawDek = dek.getEncoded(); // Demo-only.
        require(rawDek != null, "DEK not exportable in demo");
        try {
            WrappedDek wrapped = wrap(
                rawDek, kek, kekId, tenant, object);
            return new Envelope(
                tenant, object, data, wrapped, 1L);
        } finally {
            Arrays.fill(rawDek, (byte) 0); // Best effort.
        }
    }

    static Envelope rewrap(
            Envelope old, SecretKey oldKek, String oldId,
            SecretKey newKek, String newId,
            String trustedTenant, String trustedObject)
            throws Exception {

        checkContext(old, trustedTenant, trustedObject);
        require(!oldId.equals(newId),
            "New KEK reference must differ");

        byte[] rawDek = unwrap(
            old.wrappedDek(), oldKek, oldId,
            trustedTenant, trustedObject);
        try {
            WrappedDek newWrapped = wrap(
                rawDek, newKek, newId,
                trustedTenant, trustedObject);

            // No data decrypt. Same data nonce/tag/ciphertext.
            // Storage must atomically update wrapped blob + ref.
            return new Envelope(
                old.tenantId(), old.objectId(),
                old.dataBlob(), newWrapped,
                old.revision() + 1);
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    static byte[] decryptData(
            Envelope envelope, SecretKey kek,
            String expectedKekId,
            String trustedTenant, String trustedObject)
            throws Exception {

        checkContext(envelope, trustedTenant, trustedObject);
        byte[] rawDek = unwrap(
            envelope.wrappedDek(), kek, expectedKekId,
            trustedTenant, trustedObject);
        try {
            SecretKey dataKey = new SecretKeySpec(rawDek, "AES");
            return decryptAead(dataKey, envelope.dataBlob(),
                aad("billing-data-v1", trustedTenant,
                    trustedObject, "AES-256-GCM"));
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey dek = aes256();
        SecretKey kekV1 = aes256();
        SecretKey kekV2 = aes256();

        String tenant = "tenant-A";
        String object = "invoice-154";
        byte[] plaintext = "non-sensitive-demo-data"
            .getBytes(StandardCharsets.UTF_8);

        Envelope before = encryptData(
            plaintext, dek, kekV1, "billing-kek-v1",
            tenant, object);

        byte[] firstRead = decryptData(
            before, kekV1, "billing-kek-v1", tenant, object);
        require(MessageDigest.isEqual(plaintext, firstRead),
            "Initial Decrypt mismatch");

        Envelope after = rewrap(
            before, kekV1, "billing-kek-v1",
            kekV2, "billing-kek-v2", tenant, object);

        require(Arrays.equals(
                before.dataBlob().ciphertextAndTag(),
                after.dataBlob().ciphertextAndTag()),
            "Data ciphertext unexpectedly changed");
        require(Arrays.equals(
                before.dataBlob().nonce(),
                after.dataBlob().nonce()),
            "Data nonce unexpectedly changed");

        byte[] secondRead = decryptData(
            after, kekV2, "billing-kek-v2", tenant, object);
        require(MessageDigest.isEqual(plaintext, secondRead),
            "Data Decrypt after rewrap mismatch");
        require(after.revision() == before.revision() + 1,
            "Revision was not incremented");

        System.out.println("Old KEK Decrypt: PASS");
        System.out.println("New KEK Decrypt: PASS");
        System.out.println("Data ciphertext unchanged: PASS");

        try {
            decryptData(after, kekV2, "billing-kek-v2",
                "tenant-B", object);
            throw new AssertionError("Cross-tenant access");
        } catch (SecurityException expected) {
            System.out.println("Wrong tenant: REJECTED");
        }

        GcmBlob originalWrap = after.wrappedDek().blob();
        byte[] modifiedBytes = originalWrap.ciphertextAndTag();
        modifiedBytes[modifiedBytes.length - 1] ^= 1;
        Envelope tampered = new Envelope(
            after.tenantId(), after.objectId(),
            after.dataBlob(),
            new WrappedDek("billing-kek-v2", new GcmBlob(
                originalWrap.nonce(), modifiedBytes)),
            after.revision());

        try {
            decryptData(tampered, kekV2, "billing-kek-v2",
                tenant, object);
            throw new AssertionError("Tampered wrapped DEK");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampered wrap tag: REJECTED");
        }

        // Never log raw DEK/KEK or production plaintext.
    }
}
~~~

Kết quả dự kiến:

~~~text
Old KEK Decrypt: PASS
New KEK Decrypt: PASS
Data ciphertext unchanged: PASS
Wrong tenant: REJECTED
Tampered wrap tag: REJECTED
~~~

### 14.3. Ví dụ thể hiện đúng những gì?

- **DEK và KEK có mục đích khác nhau** và không reuse cùng raw key.
- **Rewrap dùng same DEK**, không Decrypt data ciphertext trên đường migration.
- **Wrap nonce mới** được sinh cho mỗi phép Encrypt key material dưới GCM KEK.
- **AAD-data không đổi**, khác **AAD-wrap** chứa KEK reference mới.
- **Envelope revision** tăng sau rewrap; không có chuyện DEK usage history reset.
- **Negative tests** chứng minh sai tenant hoặc sai wrap tag sẽ bị từ chối.
- **Không log secrets**; các mảng raw DEK ứng dụng trực tiếp nắm được xóa best-effort.

### 14.4. Giới hạn của ví dụ

**Chương trình này không phải thư viện encryption production hoặc SDK KMS.**

1. KEK raw nằm trong JVM. Production nhạy cảm nên dùng native KMS/HSM key operations, giữ KEK non-exportable.
2. `getEncoded`, `SecretKeySpec` và providers có thể tạo **bản sao DEK trên heap/native memory**; `Arrays.fill` không đảm bảo xóa hết.
3. GCM wrapping random nonce 96-bit chỉ minh họa ít operations; không đảm bảo uniqueness vô hạn ở quy mô lớn.
4. Không có **IAM, provider key state, active cryptoperiod, key inventory hoặc KMS encryption context**.
5. Không có **database transaction/CAS** thật để ghi wrapping metadata atomically.
6. Không có **replay/rollback ledger**, limits trên serialized envelope hoặc rate limits.
7. Không mô phỏng **distributed cache invalidation, offline backups, streaming data**.
8. Không chứng minh entropy của nguồn RNG hoặc approved provider certification.
9. Không có **DEK rotation/re-encryption** khi raw DEK compromised.
10. Business authorization trước thao tác được **giả định** ở trustedTenant/object; AAD không thay quyền nghiệp vụ.

## 15. Acceptance gates và bằng chứng sau rewrap

Một migration job báo “success: 100%” không đủ nếu chỉ đếm HTTP 200.

| Gate | Điều kiện cần đạt | Evidence |
| --- | --- | --- |
| **Source** | Đúng KEK-v1 và old wrapping context | Trusted inventory/key IDs |
| **Destination** | KEK-v2 đúng algorithm, state, key usage | Provider key attributes và approval |
| **Cryptography** | Same DEK material có thể Unwrap dưới v2 | Native provider evidence/functional test |
| **Data invariance** | Data ciphertext, nonce/tag không đổi | Authorized metadata checks |
| **Tenant/purpose binding** | Context đúng resource/tenant | Business auth + AAD/KMS context review |
| **Atomicity** | Key ref/context/blob/version cập nhật cùng transaction | DB CAS/commit audit |
| **Coverage** | Migration không bỏ sót records/archives nằm trong scope | Checkpoint, failed-record inventory |
| **Recovery** | Backup v1/v2 restore được theo policy | Restore test result |
| **Lifecycle** | Old/new KEK grants và cryptoperiod chính xác | IAM snapshot + owner review |
| **Audit** | Evidence có principal, time, source/destination key IDs | Protected event refs |

### 15.1. Những kết luận không được suy ra

- Data ciphertext không đổi **không** chứng minh KEK cũ chưa lộ.
- Một ciphertext giải mã được **không** xác nhận caller đã được phân quyền.
- Key v2 được KMS Enabled **không** đồng nghĩa grants/cryptoperiod đã được review.
- DB main đã migrate 100% **không** có nghĩa backups/offline data đã an toàn.
- Một key dùng được hôm nay **không** đảm bảo imported-key material sẽ còn sau expiry.
- Một hash backup khớp **không** chứng minh Unwrap key material còn khả dụng.

## 16. AEAD chống sửa đổi nhưng không tự chống rollback

Giả sử attacker giữ envelope revision 41 dùng KEK-v1, rồi rewrap tạo revision 42 dùng KEK-v2. Nếu attacker có quyền thay storage và đưa revision 41 trở lại, **old authentication tag vẫn có thể đúng**.

Bảo vệ freshness khi threat model yêu cầu:

- Trusted object revision/sequence ledger không bị attacker rollback cùng database.
- Key selection/allowlist theo migration state, không thử mọi KEK khi tag fail.
- Vô hiệu old Wrap và hạn chế old Unwrap trên production path.
- Audit change history và key-policy changes có integrity.
- Phân biệt **approved restore of historical backup** với **trả dữ liệu cũ trong API production**.
- Với trường hợp cần mạnh hơn, dùng external state witness hoặc cơ chế chống rollback được đánh giá.

**Rewrap không phải biện pháp chống replay/rollback tự thân.**
## 17. Threat model: rewrapping giải quyết và không giải quyết điều gì?

| Tình huống | Rewrap giúp gì? | Giới hạn và hành động bổ sung |
| --- | --- | --- |
| **KEK đến hạn rotation, chưa có dấu hiệu lộ** | Chuyển lớp bảo vệ DEK sang KEK mới, data ciphertext không đổi | Kiểm tra backups, old key state, IAM, restore |
| **Một DEK raw bị lộ** | Không phục hồi confidentiality | **New DEK + re-encrypt data** và đánh giá exfiltration |
| **KEK-v1 raw bị lộ cùng old wrapped DEKs** | Bảo vệ bản DEK hiện tại dưới KEK-v2 cho tương lai | Attacker có thể mở **old copies**; cân nhắc thay DEK/data theo risk assessment |
| **KMS Unwrap API bị lạm dụng** | Có thể giảm future usage của old KEK qua IAM/rotation | Phải điều tra DEKs/plaintext đã được unwrap, sửa grants |
| **Migration service bị chiếm** | Native KMS rewrap có thể giảm raw DEK exposure nếu API thực sự không trả plaintext | Quyền rewrap vẫn nhạy cảm, cần IAM/time bounds/audit |
| **Database ciphertext bị sao chép, KEK còn bí mật** | Wrapped DEK vẫn bảo vệ data key | Metadata có thể nhạy cảm; backup/provider misuse và future key compromise |
| **Sai source key ID/context** | Không; phải fail-closed | Trusted key registry, context matching, no fallback |
| **Data GCM nonce reuse** | Không | DEK replacement, re-encrypt và incident assessment |
| **Envelope bị phát lại bản cũ hợp lệ** | Không tự chống rollback | External revision/anti-replay controls và old-path restrictions |
| **KMS unavailable khi migration** | Không tự tạo availability | Resume/checkpoint/backoff, safe degraded mode |
| **Old KEK bị xóa sớm** | New blobs có thể mở được | Backup cũ vẫn mất khả năng Unwrap; restore trước deletion |
| **Alias thay đích nhưng job không biết** | Không; có thể migrate nhầm | Resolve immutable key versions, approval/CAS |
| **Tenant B nhận wrapped DEK của A** | AAD/context có thể chống nhầm ngữ cảnh | Phải có business authorization/IAM đúng resource |
| **Source HSM key không export được** | KMS/HSM native rewrap có thể hỗ trợ nếu provider có mechanism thích hợp | Không tự phá non-extractability vì mục tiêu migration |
| **Password cũ đã bị đoán từ backup** | New password KEK giúp bảo vệ bản lưu mới | Old backups có thể tiếp tục bị giải mã; không thu hồi được bản đã sao chép |

### 17.1. Old wrapped blob là một hiện vật nhạy cảm

Wrapped DEK không phải raw key, nhưng một blob cũ **vẫn có giá trị với người nắm KEK cũ**. Vì vậy:

- Hạn chế việc sao chép blobs trong logs, tickets, exports không cần thiết.
- Bảo vệ metadata key ID/version và tenant mapping.
- Review old snapshots có thể tồn tại tới khi nào.
- Khi nghi lộ KEK, tìm liệu attacker có **old wrapped DEKs và ciphertext** không.
- Không tuyên bố rewrap đã “thu hồi quyền giải mã mọi bản copy lịch sử”.

### 17.2. Rewrap không nhất thiết làm data re-encryption rẻ hơn về rủi ro mọi trường hợp

Nếu data ciphertext đã được mã hóa bằng **DEK yếu, sai nonce, thuật toán deprecated hoặc bị lộ**, rewrap chỉ thay lớp ngoài. Chuyển sang KEK mạnh hơn **không tăng entropy của DEK** và không sửa tính toàn vẹn data encryption sai thiết kế.

**Chọn rewrap hay re-encrypt phải dựa trên threat model**, không chỉ dựa trên chi phí tính toán.

## 18. Tình huống A: KEK-v1 hết hạn, 12 triệu records cần migration

### Bối cảnh

BillingService có nhiều triệu hóa đơn, mỗi record có DEK riêng, các DEKs được Wrap dưới cùng KEK-v1. KEK-v1 đến hạn ngừng **Wrap mới**; không có dấu hiệu compromised material.

### Quy trình đúng

1. Tạo **KEK-v2** trong KMS/HSM theo approved profile.
2. Kiểm tra key state, owner/custodian, IAM và capacity.
3. Chuyển new DEK wrapping sang KEK-v2.
4. Rewrap old DEKs theo batches/checkpoints, dùng native KMS API nếu có.
5. Update từng record **wrappedDEK + KEK reference/context + revision** atomically.
6. Giữ data ciphertext/nonce/tag nguyên vẹn.
7. Đối soát residual old blobs, failures và offline snapshots.
8. Restore test old/new backups; chỉ retire KEK-v1 sau dependency review.

### Sai lầm thường thấy

- Xử lý toàn bộ data plaintext dù không cần thay DEK.
- Chỉ thay key ID trong header, không thực hiện crypto rewrap.
- Đếm 12 triệu API successes thành 100% migration dù nhiều records CAS conflict.
- Xóa KEK-v1 trước khi backup đã rewrap hoặc old-key restore hết hạn.

**Kết luận:** Rewrap có thể giảm data-plane I/O rất lớn, nhưng tính đúng của **metadata, IAM và backup dependencies** là bắt buộc.

## 19. Tình huống B: KEK-v1 bị lộ cùng snapshot encrypted data

### Bối cảnh

Attacker lấy được raw KEK-v1 từ bản export trái phép và snapshot storage chứa **wrapped DEK-v1 + data ciphertext**. Đội vận hành tạo KEK-v2 và rewrap tất cả DEKs ở database chính.

### Điều đã được và chưa được bảo vệ

- Những **wrapped DEKs mới** trong database chính được bảo vệ bằng KEK-v2 nếu KEK-v2 còn bí mật.
- Attacker có **old KEK-v1 + old wrapped DEKs**, nên vẫn có khả năng unwrap DEKs tương ứng từ snapshot.
- Nếu attacker đã lấy raw DEKs/plaintext, không có rotation nào khiến họ “quên” nội dung cũ.
- Đổi KEK không đổi DEK bytes, nên old data ciphertext vẫn có thể được giải bằng old DEKs.

### Ứng phó

1. Contain source of KEK compromise và grants/credentials liên quan.
2. Inventory old wrapped blobs, data copies, DEK scopes và dữ liệu đã lộ.
3. Xác định liệu cần **thay DEKs và re-encrypt** data hiện tại/retained backups.
4. Xem audit KMS Decrypt/Unwrap và hành vi account/role.
5. Quyết định key retirement/destruction có cân nhắc backup availability.
6. Thông báo/xử lý sự cố theo quy định và business impact tương ứng.

**Không báo “đã khắc phục compromise” chỉ bằng tỷ lệ 100% rewrap.**

## 20. Tình huống C: hai migration workers ghi đè metadata

### Bối cảnh

Hai workers A và B cùng load record revision 18 đang dùng KEK-v1. Cả hai gọi KMS rewrap rồi tạo wrappedDEK-v2. Worker A ghi v2 thành công. Worker B chậm hơn, ghi kết quả dựa trên snapshot cũ và ghi đè một thay đổi nghiệp vụ mới trên record.

### Vì sao nguy hiểm?

- Nếu storage update bao gồm nhiều fields, worker B có thể ghi **data ciphertext cũ** đè ciphertext mới.
- Nếu keyRef/context cập nhật lệch với blob, record có thể **không Decrypt được**.
- Nếu worker B cố retry bằng old blob sau khi schema migration khác xảy ra, nó có thể **downgrade** record.
- Nếu dùng cùng nonce-wrap trong retry AES-GCM, có thể vi phạm yêu cầu nonce uniqueness dưới KEK.

### Khắc phục

- Tách wrapping fields khỏi data fields hoặc cập nhật theo transaction có predicate.
- Dùng **envelope_revision + expected source KEK** trong CAS.
- Worker thua phải đọc lại state, không blind overwrite.
- Chỉ đánh dấu completed khi commit thành công.
- Ghi audit correlation ID, per-record status, retry reason.
- Có reconciliation queue cho conflicts không tự giải quyết được.

**Rewrap ciphertext hợp lệ chưa đủ nếu lưu trữ có thể phá tính nhất quán.**

## 21. Tình huống D: KEK-v1 bị hủy nhưng backup 5 năm vẫn cần

### Bối cảnh

Sau khi đã chuyển KEK-v2, dashboard cho thấy 0 bản wrapped-DEK-v1 trong database production. Một người quản trị hủy KEK-v1. Sáu tháng sau, đội recovery tìm thấy một snapshot offline có wrapped DEKs dưới KEK-v1; key material không còn đường khôi phục.

### Hậu quả

- Data ciphertext trong snapshot vẫn có checksum hợp lệ.
- AES-GCM vẫn an toàn về mặt thuật toán.
- Nhưng **không có DEK plaintext** vì KEK-v1 không còn Unwrap được.
- Backup trở nên không dùng được hoặc dẫn đến mất dữ liệu nghiêm trọng.

### Cách phòng ngừa

1. Dependency inventory bao phủ **data stores, archives, replicas, backups**.
2. Restore test thật dùng **wrapped DEK + KEK version + context + data nonce/tag/AAD**.
3. Owner/custodian approval trước destruction và pending-deletion alerts.
4. Giữ legacy KEK trong scope kiểm soát khi retention còn cần.
5. Nếu policy yêu cầu xóa old key, migrate/rewrap backups tương ứng trước.
6. Có audit evidence cho quyết định không còn phụ thuộc.

**Key retirement và key destruction không phải một nút bấm có thể quyết định chỉ bằng một dashboard.**

## 22. Tình huống E: đổi password để bảo vệ DEK của người dùng

### Bối cảnh

Một ứng dụng lưu dữ liệu client-side được mã hóa bằng DEK. DEK bọc dưới KEK dẫn xuất từ mật khẩu qua **Argon2id** (hoặc KDF đã được phê duyệt). Người dùng đổi mật khẩu.

### Rewrap đúng

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Client application
    participant S as Encrypted storage
    U->>C: Authorized password change
    C->>S: Read old wrapped DEK + KDF params + ciphertext
    S-->>C: Envelope
    C->>C: Derive old KEK and authenticated Unwrap DEK
    C->>C: New random salt + approved KDF params -> new KEK
    C->>C: Authenticated Wrap SAME DEK under new KEK
    C->>S: Atomic update wrapped DEK + salt + KDF params + version
    C-->>U: Password wrapping updated
    Note over C,S: Data ciphertext can remain unchanged
~~~

Các điều kiện:

- KDF salt, cost, version, encryption context và wrap nonce/tag của old/new envelope phải đầy đủ.
- Không coi password thô hoặc `SHA-256(password)` là KEK.
- Phải phân biệt **đổi mật khẩu đăng nhập** với **đổi khóa bảo vệ dữ liệu**; verifier/hash đăng nhập không được dùng làm DEK.
- Nếu attacker đã giữ old envelope và biết password cũ, rewrap hiện tại **không thu hồi được old copy**.
- Nếu mật khẩu cũ mất và hệ thống là zero-knowledge không có recovery path, DEK có thể không mở được; cần giải thích rõ cho người dùng trước.
- Xác thực phiên và quyền yêu cầu đổi mật khẩu phải độc lập với primitive unwrap.

## 23. Các anti-pattern trong rewrapping

| Anti-pattern | Tác hại | Cách đúng |
| --- | --- | --- |
| **Chỉ sửa `kekId` trong header** | Wrapped DEK vẫn dưới old KEK | Authenticated Unwrap/Wrap hoặc native ReEncrypt key blob |
| **Nhầm KMS ReEncrypt với data re-encrypt** | Không đổi raw DEK/data ciphertext như mong muốn | Kiểm tra API payload và semantics |
| **Rewrap DEK đã lộ rồi coi an toàn** | Attacker vẫn có raw DEK | New DEK, re-encrypt theo incident assessment |
| **Reset DEK usage count sau KEK rotation** | Key/nonce history không thay | Per-DEK material version counter |
| **Data AAD chứa KEK ID có thể thay** | Data GCM tag fail dù ciphertext unchanged | Tách immutable AAD-data và AAD-wrap version |
| **Không lưu wrapping context v1** | Không Unwrap được legacy DEK | Versioned context/metadata |
| **Tin alias thay vì key material ref** | TOCTOU và wrong-key migration | Immutable source/dest key version |
| **Thử tất cả KEKs khi Unwrap lỗi** | Cross-tenant/key confusion | Trusted registry, allowed versions |
| **Log raw DEK để so sánh** | Tăng nguy cơ lộ key | Functional/provider evidence không lộ secret |
| **Client unwrap qua máy yếu bảo mật** | DEK plaintext lộ trong migration | Native KMS/HSM rewrap nếu hỗ trợ |
| **KEK non-exportable nên IAM không cần review** | Attacker gọi Unwrap/Decrypt API | Effective grants và least privilege |
| **Reuse wrap nonce khi retry AES-GCM** | Có thể phá AEAD dưới KEK | Nonce unique mỗi Encrypt |
| **Không cập nhật blob và keyRef atomically** | Lost decryption hoặc wrong metadata | Transaction/CAS |
| **Blind retry ghi đè record** | Lost updates / downgrade | Idempotency và revision guard |
| **Migration 100% trên main DB = toàn bộ dữ liệu** | Bỏ sót offline backups | Dependency scan + restore test |
| **Xóa old KEK ngay sau cutover** | Legacy records/backups không Unwrap được | Controlled retirement/destroy gate |
| **Old workers vẫn ghi KEK-v1** | Population legacy tiếp tục tăng | Active version enforcement |
| **Dual-wrap vĩnh viễn** | Kéo dài dependency/risk old KEK | Có expiry và cleanup milestones |
| **Không xét KMS key material expiration** | Imported key có thể biến mất khi cần restore | Expiry monitoring và recovery |
| **Rewrap để xóa một object dưới shared KEK** | Có thể ảnh hưởng nhiều objects | Object-level DEK/crypto-erasure policy |
| **Tin tag đúng là chống rollback** | Old valid envelope vẫn phát lại được | Revision/anti-rollback ledger |
| **Không giới hạn quyền migration worker** | Một lỗi credential làm lộ nhiều DEKs | Scoped/time-bound operations, audit |
| **Kết luận bất cứ output nào là proof** | Thiếu evidence source/trust | Provider audit + approval + verification |

## 24. Checklist triển khai re-wrapping an toàn

### Xác định mục tiêu và phạm vi

1. Có phân biệt KEK rotation, DEK re-encrypt và data key compromise?
2. Có xác định đúng **DEK material** sẽ giữ nguyên sau rewrap?
3. Key source/destination được resolve bằng immutable key ID/version?
4. Có approved algorithm/wrapping profile, cryptoperiod và purpose?
5. Có biết data ciphertext/nonce/tag/AAD có thể giữ nguyên không?
6. Data AAD không vô tình phụ thuộc KEK reference có thể đổi?
7. Old/new wrapping context/AAD được version hóa rõ?
8. Có inventory tất cả wrapped DEKs, records, tenants và backups?
9. Có xác định native KMS/HSM rewrap hay client-mediated path?
10. Có đánh giá nơi raw DEK có thể xuất hiện và secret lifetime?

### Mật mã và kiểm soát quyền

11. Authenticated Unwrap phải PASS trước khi Wrap mới?
12. Sai tag/OAEP/key blob bị fail closed, không fallback?
13. Nếu AES-GCM Wrap, nonce-wrap được cấp mới đúng profile?
14. Có đếm KEK Wrap usage và giới hạn theo policy?
15. Không dùng raw KEK trực tiếp Encrypt bulk data ngoài purpose?
16. DEK/KEK material độc lập và usage counts không bị trộn?
17. Không export raw KEK/DEK chỉ để test nếu policy cấm?
18. KMS encryption context được dựng từ trusted resource?
19. Có tenant/business authorization trước thao tác?
20. IAM least privilege giới hạn key IDs, operation, service/region?
21. Migration grants có time-bound và independent approval?
22. Quyền CreateGrant/ChangePolicy/Destroy có SoD?
23. KMS/HSM key state, origin/non-exportability được review?
24. KMS API ReEncrypt thực sự chuyển key blob chứ không phải data?

### Migration và tính nhất quán

25. Cutover new writes sang KEK-v2 đã được thực thi?
26. Offline writers/queues còn tạo v1 được theo dõi và xử lý?
27. Wrapped blob + KEK ref/context + revision được update atomically?
28. Có optimistic CAS chống lost update giữa migration workers?
29. Retry idempotent không blind overwrite?
30. AES-GCM wrap retry không dùng lại nonce đã có thể sử dụng?
31. Có checkpoint và reconciliation queue cho failed/conflicted records?
32. Có theo dõi **old-KEK residual population** theo toàn bộ scope?
33. Có plan và expiry nếu dùng dual-wrapped DEKs?
34. Có anti-rollback/version control khi threat model yêu cầu?
35. Rewrap được xác minh giữ data ciphertext/nonce/tag bất biến?
36. Có thử Unwrap/Decrypt authorized test data dưới KEK-v2?
37. Có kiểm soát KMS quota/rate/latency/cost và outage backoff?

### Vòng đời, recovery và sự cố

38. Có phân biệt active Wrap cryptoperiod với legacy Unwrap period?
39. KEK-v1 còn phục vụ backup/restore theo policy khi cần?
40. Có backup dependency index đầy đủ, kể cả cold archives?
41. Restore tests thực sự Unwrap DEK và xác thực data tag?
42. Có xét imported material expiry và provider pending deletion?
43. Không destroy KEK cũ trước owner/custodian/security approval?
44. Khi raw DEK lộ, có DEK replacement/re-encrypt plan?
45. Khi raw KEK lộ, có đánh giá old blobs attacker đã sao chép?
46. Khi IAM bị lạm dụng, có điều tra DEKs/plaintext đã unwrap?
47. Có audit từ source/destination KMS và migration service?
48. Evidence không chứa raw DEK/KEK, password hoặc plaintext?
49. Có monitor anomaly Unwrap/Decrypt sau cutover?
50. Có post-migration sign-off và runbook hồi phục khi key bị xóa nhầm?

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Re-wrapping khác re-encryption dữ liệu thế nào?

**Đáp án:** Rewrap thay lớp bảo vệ của **same DEK** dưới KEK mới, có thể giữ nguyên data ciphertext/nonce/tag. Data re-encryption dùng DEK mới hoặc profile mới để tạo data ciphertext mới.

**Câu 2.** Trong rewrap KEK-v1→v2, có cần đọc plaintext data không?

**Đáp án:** Không nếu rewrap chỉ xử lý encrypted DEK và format/AAD-data độc lập với KEK version. Native KMS có thể chuyển key blob ngay trong provider boundary.

**Câu 3.** Rewrap thành công có làm DEK có ngân sách nonce AES-GCM mới không?

**Đáp án:** Không. Raw DEK và cryptographic history không đổi. Muốn key material mới cần generate **DEK mới**, thực hiện Encrypt data lại khi phù hợp.

**Câu 4.** Vì sao `kekRef` và wrapped DEK phải được cập nhật atomically?

**Đáp án:** Nếu metadata trỏ KEK-v2 nhưng blob còn dưới v1, Unwrap có thể thất bại và dữ liệu không thể đọc. Cần transaction/CAS và version guard.

**Câu 5.** KMS API tên ReEncrypt có nhất thiết mã hóa lại data ciphertext không?

**Đáp án:** Không. Nhiều API chỉ chuyển **encrypted data key blob** từ KMS key nguồn sang đích. Phải xem provider contract và payload thực tế.

**Câu 6.** Khi raw KEK-v1 và old wrapped DEKs cùng bị sao chép, rewrap main DB có khắc phục hết không?

**Đáp án:** Không. Attacker có thể Unwrap old copies. Cần đánh giá DEK/data impact và có thể phải tạo DEKs mới, re-encrypt; dữ liệu đã lấy không thể thu hồi bằng rotation.

**Câu 7.** Nếu raw DEK đã lộ, chỉ rewrap dưới KEK mạnh có đủ không?

**Đáp án:** Không. Same DEK vẫn mở được data ciphertext cũ. Cần **new DEK + re-encrypt** và xử lý sự cố liên quan.

**Câu 8.** Data AAD bao gồm KEK version, liệu có luôn giữ data ciphertext khi đổi KEK không?

**Đáp án:** Không. Nếu KEK version là thành phần được xác thực bởi data tag và phải đổi, tag-data có thể không hợp lệ. Nên tách **immutable AAD-data** khỏi **mutable wrapping metadata** hoặc thiết kế migration khác.

**Câu 9.** Vì sao không thử tất cả KEKs khi Unwrap lỗi?

**Đáp án:** Làm mờ key/tenant mapping, tăng rủi ro cross-tenant, downgrade hoặc oracle. Dùng **trusted registry, allowlist và key state**; sai tag phải fail closed.

**Câu 10.** KEK-v2 non-exportable có ngăn người có grants Unwrap lấy DEK không?

**Đáp án:** Không mặc định. Provider có thể trả plaintext DEK qua API được cho phép. Cần IAM least privilege, business authorization và audit.

**Câu 11.** Một migration worker tạo new wrappedDEK-v2 thành công nhưng CAS update bị conflict. Có được ghi đè tiếp không?

**Đáp án:** Không. Phải đọc lại record, xác minh source revision/current key state và retry idempotent; nếu AES-GCM wrapping lại, dùng nonce mới.

**Câu 12.** Rewrap có tự chặn replay một old envelope hợp lệ không?

**Đáp án:** Không. AEAD tag có thể vẫn hợp lệ ở old revision. Cần **anti-rollback state/ledger và key-policy constraints** nếu threat model yêu cầu.

**Câu 13.** Vì sao main DB đã 100% KEK-v2 nhưng không nên destroy KEK-v1 ngay?

**Đáp án:** Backups/offline snapshots hoặc writers cũ vẫn có thể chứa wrappedDEK-v1. Cần dependency review, restore test và owner approval.

**Câu 14.** Cryptoperiod Wrap và legacy Unwrap có bắt buộc kết thúc cùng ngày không?

**Đáp án:** Không. KEK cũ có thể ngừng tạo lớp bảo vệ mới nhưng vẫn cần Unwrap dữ liệu cũ theo policy. Cần IAM/state kiểm soát riêng.

**Câu 15.** Với password-wrapped DEK, đổi mật khẩu có thể không đổi data ciphertext không?

**Đáp án:** Có. Unwrap DEK bằng old password-derived KEK, dẫn xuất new KEK qua KDF và salt mới rồi Wrap same DEK. Nhưng old backup đã bị copy có thể vẫn mở bằng old password.

**Câu 16.** KMS key Enabled có chứng minh migration đã đạt compliance không?

**Đáp án:** Không. Cần kiểm tra cryptoperiod, grants, source/destination keys, data/backup coverage, evidence và recovery.

**Câu 17.** Khi KEK-v1 bị lộ, dual-wrapping old/new có luôn hữu ích không?

**Đáp án:** Không. Giữ old blob có thể kéo dài rủi ro nếu attacker có KEK-v1. Quyết định phải theo incident scope và recovery requirements.

**Câu 18.** Vì sao rewrap nhiều DEKs dưới một KEK AES-GCM cần quản lý nonce riêng?

**Đáp án:** Mỗi phép Wrap là một AEAD Encrypt dưới cùng KEK; nonce reuse có thể gây mất bí mật/toàn vẹn. Phải dùng đúng GCM usage profile và cơ chế cấp IV duy nhất.

**Câu 19.** Chỉ kiểm tra checksum ciphertext của backup có chứng minh restore được không?

**Đáp án:** Không. Phải còn KEK material/version, wrapped DEK, context, data nonce/tag/AAD và quyền Unwrap; test Decrypt thật theo scope.

**Câu 20.** Khi nào hoàn thành rewrap production?

**Đáp án:** Khi **old/new material refs đúng, wrapping blobs hợp lệ, atomic updates và migrations được kiểm chứng, data ciphertext bất biến theo policy, all dependencies/backup restore được xử lý, IAM/audit đạt và old-key lifecycle có owner approval**.

## 26. Kết luận

**Re-wrapping là cách thay lớp bảo vệ của một DEK mà không nhất thiết thay DEK hoặc mã hóa lại dữ liệu.** Nó rất phù hợp cho KEK rotation theo cryptoperiod, chuyển wrapping profile, đổi password bọc DEK hoặc di chuyển key custody khi API/provider hỗ trợ.

Giá trị của rewrap nằm ở việc **giảm data-plane I/O và plaintext exposure**, đồng thời tách key management khỏi data encryption. Nhưng thiết kế chỉ đúng khi **same DEK, authenticated wrapping, nonce/context/AAD chính xác, key IDs/version đáng tin, atomic metadata updates, IAM least privilege và backup/restore dependencies** đều được kiểm soát.

Với Java, có thể mô phỏng hai tầng AES-GCM và rewrap trong một JVM để hiểu primitive, nhưng production nên sử dụng **KMS/HSM-native rewrap** khi khả thi, giữ raw KEK trong security boundary và có bằng chứng vận hành. Nếu **DEK hoặc old KEK cùng old wrapped data đã bị lộ**, cần đánh giá re-encryption và incident response; chỉ rewrap không thu hồi được bí mật đã bị sao chép.

**Re-wrapping thành công không chỉ là có một wrapped DEK mới: đó là một chuyển đổi vòng đời khóa có thể kiểm chứng, có khả năng khôi phục và không làm mất dữ liệu hoặc che giấu rủi ro của khóa cũ.**
